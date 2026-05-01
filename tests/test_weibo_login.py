import json
import os
import shutil
import unittest
from pathlib import Path

from weibo_login import (
    build_cookie_header,
    extract_xsrf_token,
    filter_weibo_cookies,
    has_required_login_cookies,
    ensure_playwright_browsers_path,
    save_secrets,
)


class WeiboLoginTests(unittest.TestCase):
    def test_filter_weibo_cookies_keeps_only_weibo_domains(self):
        cookies = [
            {'name': 'SUB', 'value': 'sub-value', 'domain': '.weibo.com'},
            {'name': 'XSRF-TOKEN', 'value': 'xsrf-value', 'domain': 'weibo.com'},
            {'name': 'OTHER', 'value': 'ignored', 'domain': 'example.com'},
            {'name': '', 'value': 'ignored', 'domain': '.weibo.com'},
        ]

        filtered = filter_weibo_cookies(cookies)

        self.assertEqual([cookie['name'] for cookie in filtered], ['SUB', 'XSRF-TOKEN'])

    def test_build_cookie_header_serializes_name_value_pairs(self):
        cookies = [
            {'name': 'SUB', 'value': 'sub-value', 'domain': '.weibo.com'},
            {'name': 'XSRF-TOKEN', 'value': 'xsrf-value', 'domain': 'weibo.com'},
        ]

        self.assertEqual(build_cookie_header(cookies), 'SUB=sub-value; XSRF-TOKEN=xsrf-value')

    def test_extract_xsrf_token_returns_cookie_value_when_present(self):
        cookies = [
            {'name': 'SUB', 'value': 'sub-value', 'domain': '.weibo.com'},
            {'name': 'XSRF-TOKEN', 'value': 'xsrf-value', 'domain': 'weibo.com'},
        ]

        self.assertEqual(extract_xsrf_token(cookies), 'xsrf-value')

    def test_has_required_login_cookies_rejects_visitor_cookie_only(self):
        visitor_cookies = [
            {'name': 'SUB', 'value': 'visitor-sub', 'domain': '.weibo.com'},
            {'name': 'SUBP', 'value': 'visitor-subp', 'domain': '.weibo.com'},
            {'name': 'WBPSESS', 'value': 'visitor-session', 'domain': '.weibo.com'},
        ]
        login_cookies = visitor_cookies + [
            {'name': 'SSOLoginState', 'value': 'login-state', 'domain': '.weibo.com'},
        ]

        self.assertFalse(has_required_login_cookies(visitor_cookies))
        self.assertTrue(has_required_login_cookies(login_cookies))

    def test_save_secrets_writes_cookie_and_xsrf_without_passwords(self):
        output_root = Path.cwd() / 'test-output'
        shutil.rmtree(output_root, ignore_errors=True)
        try:
            path = output_root / 'weibo_secrets.json'
            save_secrets(path, 'SUB=sub-value; XSRF-TOKEN=xsrf-value', 'xsrf-value')
            data = json.loads(path.read_text(encoding='utf-8'))
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

        self.assertEqual(data['WEIBO_COOKIE'], 'SUB=sub-value; XSRF-TOKEN=xsrf-value')
        self.assertEqual(data['WEIBO_XSRF_TOKEN'], 'xsrf-value')
        self.assertNotIn('password', json.dumps(data).lower())

    def test_ensure_playwright_browsers_path_uses_requested_directory(self):
        old_value = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
        try:
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = 'C:\\old-playwright-cache'
            resolved = ensure_playwright_browsers_path(Path('.playwright-browsers'))
            self.assertEqual(os.environ['PLAYWRIGHT_BROWSERS_PATH'], str(resolved))
            self.assertTrue(str(resolved).endswith('.playwright-browsers'))
        finally:
            if old_value is None:
                os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)
            else:
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = old_value


if __name__ == '__main__':
    unittest.main()
