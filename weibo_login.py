from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_LOGIN_URL = 'https://weibo.com/login.php'
DEFAULT_SECRETS_FILE = Path('weibo_secrets.json')
DEFAULT_PROFILE_DIR = Path('.weibo_browser_profile')
DEFAULT_BROWSERS_DIR = Path('.playwright-browsers')
WEIBO_DOMAIN_SUFFIXES = ('weibo.com', 'weibo.cn')
REQUIRED_COOKIE_NAMES = {'SUB'}
LOGIN_MARKER_COOKIE_NAMES = {'ALF', 'SSOLoginState', 'SCF'}
XSRF_COOKIE_NAMES = ('XSRF-TOKEN', 'XSRF_TOKEN')


def filter_weibo_cookies(cookies: list[dict[str, Any]]) -> list[dict[str, str]]:
    filtered = []
    for cookie in cookies:
        name = str(cookie.get('name') or '')
        value = str(cookie.get('value') or '')
        domain = str(cookie.get('domain') or '').lstrip('.').lower()
        if not name or not value:
            continue
        if not any(domain == suffix or domain.endswith(f'.{suffix}') for suffix in WEIBO_DOMAIN_SUFFIXES):
            continue
        filtered.append({'name': name, 'value': value, 'domain': domain})
    return filtered


def build_cookie_header(cookies: list[dict[str, Any]]) -> str:
    return '; '.join(f"{cookie['name']}={cookie['value']}" for cookie in cookies)


def extract_xsrf_token(cookies: list[dict[str, Any]]) -> str:
    for cookie in cookies:
        if cookie.get('name') in XSRF_COOKIE_NAMES:
            return str(cookie.get('value') or '')
    return ''


def save_secrets(path: Path, cookie_header: str, xsrf_token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    secrets = {
        'WEIBO_COOKIE': cookie_header,
        'WEIBO_XSRF_TOKEN': xsrf_token,
    }
    with path.open('w', encoding='utf-8') as handle:
        json.dump(secrets, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def has_required_login_cookies(cookies: list[dict[str, Any]]) -> bool:
    names = {cookie.get('name') for cookie in cookies}
    return REQUIRED_COOKIE_NAMES.issubset(names) and bool(LOGIN_MARKER_COOKIE_NAMES & names)


def ensure_playwright_browsers_path(browsers_dir: Path) -> Path:
    resolved = browsers_dir.resolve()
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(resolved)
    return resolved


def run_browser_login(
    secrets_file: Path,
    profile_dir: Path,
    browsers_dir: Path,
    login_url: str,
    timeout_seconds: int,
) -> int:
    resolved_browsers_dir = ensure_playwright_browsers_path(browsers_dir)
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            '缺少 Playwright。请先运行：\n'
            '  python -m pip install playwright\n'
            f'  $env:PLAYWRIGHT_BROWSERS_PATH = "{resolved_browsers_dir}"\n'
            '  python -m playwright install chromium',
            file=sys.stderr,
        )
        return 2

    profile_dir.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={'width': 1280, 'height': 900},
        )
        page = browser.new_page()
        page.goto(login_url, wait_until='domcontentloaded')
        print('浏览器已打开。请在窗口里完成微博登录；登录成功后脚本会自动保存 Cookie。')

        cookies: list[dict[str, Any]] = []
        try:
            while time.monotonic() < deadline:
                cookies = filter_weibo_cookies(browser.cookies())
                if has_required_login_cookies(cookies):
                    break
                try:
                    page.wait_for_timeout(1000)
                except PlaywrightTimeoutError:
                    pass
            else:
                print('等待登录超时，没有检测到微博登录 Cookie。', file=sys.stderr)
                return 1

            cookie_header = build_cookie_header(cookies)
            xsrf_token = extract_xsrf_token(cookies)
            save_secrets(secrets_file, cookie_header, xsrf_token)
            print(f'已保存微博登录态到 {secrets_file}')
            return 0
        finally:
            browser.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='打开浏览器完成微博登录，并保存本项目使用的 Cookie。')
    parser.add_argument('--secrets', default=str(DEFAULT_SECRETS_FILE), help='输出的 secrets JSON 文件')
    parser.add_argument('--profile', default=str(DEFAULT_PROFILE_DIR), help='独立浏览器用户数据目录')
    parser.add_argument('--browsers', default=str(DEFAULT_BROWSERS_DIR), help='Playwright 浏览器目录')
    parser.add_argument('--login-url', default=DEFAULT_LOGIN_URL, help='微博登录页 URL')
    parser.add_argument('--timeout', type=int, default=600, help='等待登录完成的秒数')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return run_browser_login(
        secrets_file=Path(args.secrets),
        profile_dir=Path(args.profile),
        browsers_dir=Path(args.browsers),
        login_url=args.login_url,
        timeout_seconds=args.timeout,
    )


if __name__ == '__main__':
    raise SystemExit(main())
