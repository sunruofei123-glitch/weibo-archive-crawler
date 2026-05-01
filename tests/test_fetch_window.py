import shutil
import unittest
from datetime import datetime, timezone
from pathlib import Path

from weibo_crawler import (
    Account,
    FetchWindow,
    WeiboPost,
    filter_posts_for_window,
    filter_accounts_by_uids,
    last_years_window,
    load_run_state,
    page_is_before_window,
    previous_month_window,
    resolve_fetch_window,
    save_run_state,
    split_window_into_chunks,
)


def post_at(post_id: str, created_at: datetime) -> WeiboPost:
    return WeiboPost(
        uid='5659598386',
        post_id=post_id,
        mblogid=post_id,
        created_at=created_at,
        text=post_id,
        source='',
        reposts_count=0,
        comments_count=0,
        attitudes_count=0,
        image_urls=(),
        card_urls=(),
        retweeted_text=None,
    )


class FetchWindowTests(unittest.TestCase):
    def test_previous_month_window_uses_calendar_month(self):
        now = datetime(2026, 4, 29, 21, 50, tzinfo=timezone.utc)

        window = previous_month_window(now)

        self.assertEqual(window.start.isoformat(), '2026-03-01T00:00:00+08:00')
        self.assertEqual(window.end.isoformat(), '2026-04-01T00:00:00+08:00')
        self.assertEqual(window.label, 'previous-month:2026-03')

    def test_last_years_window_starts_at_local_midnight(self):
        now = datetime(2026, 4, 29, 21, 50, tzinfo=timezone.utc)

        window = last_years_window(now, years=5)

        self.assertEqual(window.start.isoformat(), '2021-04-30T00:00:00+08:00')
        self.assertEqual(window.end.isoformat(), '2026-04-30T05:50:00+08:00')
        self.assertEqual(window.label, 'bootstrap:last-5-years')

    def test_auto_mode_bootstraps_until_state_is_marked_complete(self):
        now = datetime(2026, 4, 29, 9, 0, tzinfo=timezone.utc)

        bootstrap = resolve_fetch_window('auto', {}, now, years=5)
        monthly = resolve_fetch_window('auto', {'bootstrap_completed': True}, now, years=5)

        self.assertEqual(bootstrap.label, 'bootstrap:last-5-years')
        self.assertTrue(bootstrap.mark_bootstrap_completed)
        self.assertEqual(monthly.label, 'previous-month:2026-03')
        self.assertFalse(monthly.mark_bootstrap_completed)

    def test_filter_posts_for_window_keeps_only_posts_inside_range(self):
        window = FetchWindow(
            start=datetime(2026, 3, 1, tzinfo=timezone.utc),
            end=datetime(2026, 4, 1, tzinfo=timezone.utc),
            label='test',
            mark_bootstrap_completed=False,
        )
        posts = [
            post_at('too_new', datetime(2026, 4, 1, tzinfo=timezone.utc)),
            post_at('inside', datetime(2026, 3, 15, tzinfo=timezone.utc)),
            post_at('too_old', datetime(2026, 2, 28, 23, 59, tzinfo=timezone.utc)),
        ]

        filtered = filter_posts_for_window(posts, window)

        self.assertEqual([post.post_id for post in filtered], ['inside'])

    def test_page_is_before_window_only_when_every_post_is_older(self):
        window = FetchWindow(
            start=datetime(2026, 3, 1, tzinfo=timezone.utc),
            end=datetime(2026, 4, 1, tzinfo=timezone.utc),
            label='test',
            mark_bootstrap_completed=False,
        )

        self.assertFalse(page_is_before_window([post_at('new', datetime(2026, 3, 5, tzinfo=timezone.utc))], window))
        self.assertTrue(page_is_before_window([post_at('old', datetime(2026, 2, 1, tzinfo=timezone.utc))], window))

    def test_run_state_round_trips_json(self):
        output_root = Path.cwd() / 'test-output'
        shutil.rmtree(output_root, ignore_errors=True)
        try:
            state_file = output_root / '.weibo_crawler_state.json'
            save_run_state(
                state_file,
                {
                    'bootstrap_completed': True,
                    'accounts': [Account(uid='5659598386', folder='王盐Charles').uid],
                },
            )

            state = load_run_state(state_file)
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

        self.assertTrue(state['bootstrap_completed'])
        self.assertEqual(state['accounts'], ['5659598386'])

    def test_filter_accounts_by_uids_keeps_requested_accounts(self):
        accounts = [
            Account(uid='2492465520', folder='刘晓光Savvy'),
            Account(uid='5659598386', folder='王盐Charles'),
        ]

        filtered = filter_accounts_by_uids(accounts, ['5659598386'])

        self.assertEqual([account.uid for account in filtered], ['5659598386'])

    def test_filter_accounts_by_uids_rejects_unknown_uid(self):
        accounts = [Account(uid='2492465520', folder='刘晓光Savvy')]

        with self.assertRaises(ValueError):
            filter_accounts_by_uids(accounts, ['missing'])

    def test_split_window_into_chunks_uses_contiguous_ranges(self):
        window = FetchWindow(
            start=datetime(2026, 3, 1, tzinfo=timezone.utc),
            end=datetime(2026, 3, 26, tzinfo=timezone.utc),
            label='test',
            mark_bootstrap_completed=False,
        )

        chunks = split_window_into_chunks(window, days=10)

        self.assertEqual(
            [(start.isoformat(), end.isoformat()) for start, end in chunks],
            [
                ('2026-03-01T00:00:00+00:00', '2026-03-11T00:00:00+00:00'),
                ('2026-03-11T00:00:00+00:00', '2026-03-21T00:00:00+00:00'),
                ('2026-03-21T00:00:00+00:00', '2026-03-26T00:00:00+00:00'),
            ],
        )


if __name__ == '__main__':
    unittest.main()
