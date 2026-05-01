import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path

from weibo_crawler import Account, WeiboPost, archive_posts, sanitize_folder_name


class ArchiveLogicTests(unittest.TestCase):
    def test_sanitize_folder_name_removes_windows_reserved_characters(self):
        self.assertEqual(sanitize_folder_name('王盐:Charles/2026?'), '王盐_Charles_2026_')

    def test_archive_posts_groups_by_person_year_and_merges_without_duplicates(self):
        account = Account(uid='5659598386', folder='王盐Charles')
        first_post = WeiboPost(
            uid='5659598386',
            post_id='P1',
            mblogid='AbCd1',
            created_at=datetime(2026, 4, 2, 8, 30, tzinfo=timezone.utc),
            text='第一条微博',
            source='微博网页版',
            reposts_count=1,
            comments_count=2,
            attitudes_count=3,
            image_urls=('https://example.test/a.jpg',),
            card_urls=(),
            retweeted_text=None,
        )
        duplicate_post = WeiboPost(
            uid='5659598386',
            post_id='P1',
            mblogid='AbCd1',
            created_at=datetime(2026, 4, 2, 8, 30, tzinfo=timezone.utc),
            text='第一条微博',
            source='微博网页版',
            reposts_count=1,
            comments_count=2,
            attitudes_count=3,
            image_urls=('https://example.test/a.jpg',),
            card_urls=(),
            retweeted_text=None,
        )
        newer_post = WeiboPost(
            uid='5659598386',
            post_id='P2',
            mblogid='EfGh2',
            created_at=datetime(2026, 5, 1, 8, 30, tzinfo=timezone.utc),
            text='second post',
            source='web',
            reposts_count=4,
            comments_count=5,
            attitudes_count=6,
            image_urls=(),
            card_urls=(),
            retweeted_text=None,
        )

        output_root = Path.cwd() / 'test-output'
        shutil.rmtree(output_root, ignore_errors=True)
        try:
            archive_posts(output_root, account, [first_post])
            archive_posts(output_root, account, [duplicate_post])
            archive_posts(output_root, account, [newer_post])

            year_file = output_root / '王盐Charles' / '2026.txt'
            old_year_dir = output_root / '王盐Charles' / '2026'
            self.assertTrue(year_file.exists())
            self.assertFalse(old_year_dir.exists())
            content = year_file.read_text(encoding='utf-8')
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

        self.assertEqual(content.count('微博ID: P1'), 1)
        self.assertEqual(content.count('微博ID: P2'), 1)
        self.assertLess(content.index('微博ID: P2'), content.index('微博ID: P1'))
        self.assertIn('# 2026 微博归档', content)
        self.assertIn('第一条微博', content)
        self.assertIn('https://weibo.com/5659598386/AbCd1', content)

    def test_archive_posts_refreshes_month_when_same_post_changes(self):
        account = Account(uid='5659598386', folder='王盐Charles')

        def make_post(post_id: str, mblogid: str, created_at: datetime, text: str) -> WeiboPost:
            return WeiboPost(
                uid='5659598386',
                post_id=post_id,
                mblogid=mblogid,
                created_at=created_at,
                text=text,
                source='web',
                reposts_count=1,
                comments_count=2,
                attitudes_count=3,
                image_urls=(),
                card_urls=(),
                retweeted_text=None,
            )

        old_april_post = make_post('P1', 'AbCd1', datetime(2026, 4, 2, 8, 30, tzinfo=timezone.utc), 'old text')
        updated_april_post = make_post(
            'P1',
            'AbCd1',
            datetime(2026, 4, 2, 8, 30, tzinfo=timezone.utc),
            'updated text',
        )
        march_post = make_post('P2', 'EfGh2', datetime(2026, 3, 2, 8, 30, tzinfo=timezone.utc), 'march text')

        output_root = Path.cwd() / 'test-output'
        shutil.rmtree(output_root, ignore_errors=True)
        try:
            archive_posts(output_root, account, [old_april_post, march_post])
            archive_posts(output_root, account, [updated_april_post])

            year_file = output_root / '王盐Charles' / '2026.txt'
            content = year_file.read_text(encoding='utf-8')
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

        self.assertEqual(content.count('微博ID: P1'), 1)
        self.assertIn('updated text', content)
        self.assertNotIn('old text', content)
        self.assertIn('march text', content)


if __name__ == '__main__':
    unittest.main()
