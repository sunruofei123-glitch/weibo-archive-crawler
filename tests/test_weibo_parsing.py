import unittest

from weibo_crawler import parse_weibo_post, strip_html


class WeiboParsingTests(unittest.TestCase):
    def test_strip_html_keeps_readable_text_and_unescapes_entities(self):
        html = '<a href="/n/test">@test</a>&nbsp;你好<br />世界<span class="url-icon"></span>'
        self.assertEqual(strip_html(html), '@test 你好\n世界')

    def test_parse_weibo_post_extracts_core_fields(self):
        payload = {
            'id': '502000001',
            'mblogid': 'PxYz123',
            'created_at': 'Wed Apr 29 09:15:00 +0800 2026',
            'text': '<p>带链接的正文&nbsp;<a href="https://t.cn/test">网页链接</a></p>',
            'source': '<a href="https://weibo.com">微博网页版</a>',
            'reposts_count': 4,
            'comments_count': 5,
            'attitudes_count': 6,
            'pic_infos': {
                'a': {'large': {'url': 'https://wx1.sinaimg.cn/large/a.jpg'}},
                'b': {'original': {'url': 'https://wx2.sinaimg.cn/original/b.jpg'}},
            },
            'page_info': {
                'page_title': '文章标题',
                'page_url': 'https://weibo.com/ttarticle/example',
            },
            'retweeted_status': {
                'user': {'screen_name': '原作者'},
                'text_raw': '原微博内容',
            },
        }

        post = parse_weibo_post('5659598386', payload)

        self.assertEqual(post.post_id, '502000001')
        self.assertEqual(post.mblogid, 'PxYz123')
        self.assertEqual(post.text, '带链接的正文 网页链接')
        self.assertEqual(post.source, '微博网页版')
        self.assertEqual(post.local_created_at.strftime('%Y-%m-%d %H:%M'), '2026-04-29 09:15')
        self.assertEqual(post.image_urls, (
            'https://wx1.sinaimg.cn/large/a.jpg',
            'https://wx2.sinaimg.cn/original/b.jpg',
        ))
        self.assertEqual(post.card_urls, ('文章标题: https://weibo.com/ttarticle/example',))
        self.assertEqual(post.retweeted_text, '@原作者: 原微博内容')


if __name__ == '__main__':
    unittest.main()
