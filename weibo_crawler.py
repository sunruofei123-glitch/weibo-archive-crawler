from __future__ import annotations

import argparse
import html
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


CHINA_TZ = timezone(timedelta(hours=8))
WINDOWS_RESERVED_CHARS = r'<>:"/\|?*'
DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'
)
DEFAULT_CONFIG = {
    'output_dir': 'archive',
    'max_pages': 10,
    'monthly_max_pages': 300,
    'bootstrap_max_pages': 3000,
    'bootstrap_years': 5,
    'request_timeout_seconds': 45,
    'request_retries': 3,
    'request_delay_seconds': [1.5, 3.5],
    'accounts': [
        {'uid': '2492465520', 'folder': '刘晓光Savvy'},
        {'uid': '5659598386', 'folder': '王盐Charles'},
    ],
}


@dataclass(frozen=True)
class Account:
    uid: str
    folder: str | None = None
    name: str | None = None

    @property
    def folder_name(self) -> str:
        return sanitize_folder_name(self.folder or self.name or self.uid)


@dataclass(frozen=True)
class WeiboPost:
    uid: str
    post_id: str
    mblogid: str
    created_at: datetime
    text: str
    source: str
    reposts_count: int
    comments_count: int
    attitudes_count: int
    image_urls: tuple[str, ...]
    card_urls: tuple[str, ...]
    retweeted_text: str | None

    @property
    def local_created_at(self) -> datetime:
        return self.created_at.astimezone(CHINA_TZ)

    @property
    def url(self) -> str:
        return f'https://weibo.com/{self.uid}/{self.mblogid}'


@dataclass(frozen=True)
class FetchWindow:
    start: datetime | None
    end: datetime | None
    label: str
    mark_bootstrap_completed: bool = False


def sanitize_folder_name(value: str) -> str:
    sanitized = ''.join('_' if char in WINDOWS_RESERVED_CHARS else char for char in value)
    sanitized = sanitized.strip().rstrip('.')
    return sanitized or 'unknown'


class WeiboClient:
    base_url = 'https://weibo.com'

    def __init__(
        self,
        cookie: str = '',
        xsrf_token: str = '',
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_seconds: int = 20,
        max_retries: int = 3,
        delay_seconds: tuple[float, float] = (1.5, 3.5),
    ) -> None:
        self.cookie = cookie
        self.xsrf_token = xsrf_token
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, max_retries)
        self.delay_seconds = delay_seconds

    def fetch_profile_name(self, uid: str) -> str | None:
        data = self._get_json('/ajax/profile/info', {'uid': uid}, referer=f'{self.base_url}/u/{uid}')
        user = data.get('data', {}).get('user') or data.get('user') or {}
        return user.get('screen_name') or user.get('name')

    def fetch_posts(
        self,
        account: Account,
        max_pages: int,
        window: FetchWindow | None = None,
    ) -> list[WeiboPost]:
        if window and window.start and window.end:
            return self.fetch_posts_by_search(account, max_pages, window)

        posts: list[WeiboPost] = []
        for page in range(1, max_pages + 1):
            payload = self._get_json(
                '/ajax/statuses/mymblog',
                {'uid': account.uid, 'page': page, 'feature': 0},
                referer=f'{self.base_url}/u/{account.uid}',
            )
            if payload.get('ok') in (0, '0', False):
                message = payload.get('msg') or payload.get('message') or '微博接口返回失败'
                raise RuntimeError(f'{message}。请检查 WEIBO_COOKIE 是否有效。')
            statuses = payload.get('data', {}).get('list') or []
            if not statuses:
                if page == 1:
                    raise RuntimeError(
                        '第一页没有返回任何微博。目标账号公开页有内容时，这通常表示缺少有效 '
                        'WEIBO_COOKIE，或当前请求被微博风控。'
                    )
                break
            page_posts = []
            for status in statuses:
                status = self._with_long_text(status)
                page_posts.append(parse_weibo_post(account.uid, status))
            posts.extend(filter_posts_for_window(page_posts, window))
            if page_is_before_window(page_posts, window):
                break
            if page < max_pages:
                self._sleep_between_requests()
        return posts

    def fetch_posts_by_search(
        self,
        account: Account,
        max_pages: int,
        window: FetchWindow,
    ) -> list[WeiboPost]:
        posts: list[WeiboPost] = []
        pages_used = 0
        for chunk_start, chunk_end in split_window_into_chunks(window, days=10):
            page = 1
            while pages_used < max_pages:
                payload = self._get_json(
                    '/ajax/statuses/searchProfile',
                    {
                        'uid': account.uid,
                        'page': page,
                        'hasori': 1,
                        'hastext': 1,
                        'haspic': 1,
                        'hasvideo': 1,
                        'hasmusic': 1,
                        'hasret': 1,
                        'starttime': int(chunk_start.timestamp()),
                        'endtime': int(chunk_end.timestamp()),
                    },
                    referer=f'{self.base_url}/u/{account.uid}',
                )
                pages_used += 1
                if payload.get('ok') in (0, '0', False):
                    message = payload.get('msg') or payload.get('message') or '微博接口返回失败'
                    raise RuntimeError(f'{message}。请检查 WEIBO_COOKIE 是否有效。')
                statuses = payload.get('data', {}).get('list') or []
                if not statuses:
                    break
                page_posts = []
                for status in statuses:
                    status = self._with_long_text(status)
                    page_posts.append(parse_weibo_post(account.uid, status))
                posts.extend(filter_posts_for_window(page_posts, window))
                page += 1
                if pages_used < max_pages:
                    self._sleep_between_requests()
            if pages_used >= max_pages:
                break
            self._sleep_between_requests()
        return posts

    def _with_long_text(self, status: dict[str, Any]) -> dict[str, Any]:
        if not status.get('isLongText'):
            return status
        mblogid = status.get('mblogid') or status.get('id') or status.get('idstr')
        if not mblogid:
            return status
        try:
            data = self._get_json(
                '/ajax/statuses/longtext',
                {'id': mblogid},
                referer=f"{self.base_url}/{status.get('user', {}).get('id', '')}/{mblogid}",
            )
        except RuntimeError:
            return status
        long_text = data.get('data', {}).get('longTextContent')
        if not long_text:
            return status
        copied = dict(status)
        copied['text'] = long_text
        copied['text_raw'] = strip_html(long_text)
        return copied

    def _get_json(self, path: str, params: dict[str, Any], referer: str) -> dict[str, Any]:
        url = f'{self.base_url}{path}?{urlencode(params)}'
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': referer,
            'User-Agent': self.user_agent,
            'X-Requested-With': 'XMLHttpRequest',
        }
        if self.cookie:
            headers['Cookie'] = self.cookie
        if self.xsrf_token:
            headers['X-XSRF-TOKEN'] = self.xsrf_token

        raw = ''
        for attempt in range(1, self.max_retries + 1):
            request = Request(url, headers=headers)
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    charset = response.headers.get_content_charset() or 'utf-8'
                    raw = response.read().decode(charset, errors='replace')
                break
            except HTTPError as exc:
                raise RuntimeError(
                    f'微博接口返回 HTTP {exc.code}。如果是 401/403，请设置有效的 WEIBO_COOKIE。URL: {url}'
                ) from exc
            except (TimeoutError, URLError, OSError) as exc:
                if attempt >= self.max_retries:
                    reason = getattr(exc, 'reason', exc)
                    raise RuntimeError(f'无法连接微博接口：{reason}') from exc
                self._sleep_between_requests()

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            preview = raw[:120].replace('\n', ' ')
            raise RuntimeError(f'微博接口没有返回 JSON，可能被登录页或风控页拦截：{preview!r}') from exc

    def _sleep_between_requests(self) -> None:
        low, high = self.delay_seconds
        if high <= 0:
            return
        time.sleep(random.uniform(max(0, low), max(low, high)))


def archive_posts(output_root: Path, account: Account, posts: Iterable[WeiboPost]) -> None:
    grouped: dict[str, list[WeiboPost]] = {}
    for post in posts:
        local_time = post.local_created_at
        year = f'{local_time.year:04d}'
        grouped.setdefault(year, []).append(post)

    for year, year_posts in grouped.items():
        account_dir = output_root / account.folder_name
        account_dir.mkdir(parents=True, exist_ok=True)
        year_file = account_dir / f'{year}.txt'

        existing = year_file.read_text(encoding='utf-8') if year_file.exists() else ''
        replacement_months = {post.local_created_at.strftime('%Y-%m') for post in year_posts}
        existing_ids = existing_post_ids_outside_months(existing, replacement_months)
        seen_ids = set(existing_ids)
        new_posts = []
        for post in sorted(year_posts, key=lambda item: item.local_created_at, reverse=True):
            if post.post_id in seen_ids:
                continue
            new_posts.append(post)
            seen_ids.add(post.post_id)

        if not new_posts:
            continue

        new_blocks = [format_post(post) for post in new_posts]
        if existing:
            content = merge_archive_content(existing, new_blocks, replacement_months)
        else:
            content = build_year_header(account, year) + '\n\n' + '\n\n'.join(new_blocks) + '\n'
        year_file.write_text(content, encoding='utf-8')


def merge_archive_content(existing: str, new_blocks: list[str], replacement_months: set[str] | None = None) -> str:
    header, existing_blocks = split_archive_content(existing)
    if replacement_months:
        existing_blocks = [
            block for block in existing_blocks if archive_block_month(block) not in replacement_months
        ]
    blocks = unique_archive_blocks(existing_blocks + new_blocks)
    blocks.sort(key=archive_block_time, reverse=True)
    return header.rstrip() + '\n\n' + '\n\n'.join(blocks) + '\n'


def split_archive_content(content: str) -> tuple[str, list[str]]:
    header, separator, body = content.partition('\n\n---\n')
    if not separator:
        return content.rstrip(), []
    body_with_first_marker = '---\n' + body
    blocks = [block.strip() for block in re.split(r'\n(?=---\n)', body_with_first_marker) if block.strip()]
    return header.rstrip(), blocks


def unique_archive_blocks(blocks: list[str]) -> list[str]:
    seen_ids: set[str] = set()
    unique_blocks: list[str] = []
    for block in blocks:
        post_id = archive_block_id(block)
        if post_id:
            if post_id in seen_ids:
                continue
            seen_ids.add(post_id)
        unique_blocks.append(block)
    return unique_blocks


def existing_post_ids_outside_months(content: str, replacement_months: set[str]) -> set[str]:
    _, existing_blocks = split_archive_content(content)
    return {
        post_id
        for block in existing_blocks
        if archive_block_month(block) not in replacement_months
        for post_id in [archive_block_id(block)]
        if post_id
    }


def archive_block_id(block: str) -> str:
    match = re.search(r'^微博ID:\s*(\S+)\s*$', block, flags=re.MULTILINE)
    return match.group(1) if match else ''


def archive_block_month(block: str) -> str:
    match = re.search(r'^时间:\s*(\d{4}-\d{2})-', block, flags=re.MULTILINE)
    return match.group(1) if match else ''


def archive_block_time(block: str) -> datetime:
    match = re.search(r'^时间:\s*(.+?)\s*$', block, flags=re.MULTILINE)
    if not match:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S %z')
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def build_year_header(account: Account, year: str) -> str:
    account_label = account.name or account.folder or account.uid
    return f'# {year} 微博归档\n\n账号: {account_label}\nUID: {account.uid}'


def format_post(post: WeiboPost) -> str:
    local_time = post.local_created_at.strftime('%Y-%m-%d %H:%M:%S %z')
    lines = [
        '---',
        f'时间: {local_time}',
        f'微博ID: {post.post_id}',
        f'链接: {post.url}',
    ]
    if post.source:
        lines.append(f'来源: {post.source}')
    lines.append(
        f'互动: 转发 {post.reposts_count} | 评论 {post.comments_count} | 赞 {post.attitudes_count}'
    )
    lines.extend(['', '正文:', post.text.strip() or '(空)'])

    if post.retweeted_text:
        lines.extend(['', '转发原文:', post.retweeted_text.strip()])
    if post.image_urls:
        lines.extend(['', '图片:'])
        lines.extend(f'- {url}' for url in post.image_urls)
    if post.card_urls:
        lines.extend(['', '链接卡片:'])
        lines.extend(f'- {url}' for url in post.card_urls)

    return '\n'.join(lines)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'br':
            self.parts.append('\n')
        if tag == 'img':
            self._append_img_alt(attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'br':
            self.parts.append('\n')
        if tag == 'img':
            self._append_img_alt(attrs)

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f'&{name};')

    def handle_charref(self, name: str) -> None:
        self.parts.append(f'&#{name};')

    def _append_img_alt(self, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        alt = attr_map.get('alt')
        if alt:
            self.parts.append(alt)


def strip_html(value: str | None) -> str:
    if not value:
        return ''
    parser = _HTMLTextExtractor()
    parser.feed(value)
    text = html.unescape(''.join(parser.parts)).replace('\xa0', ' ')
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def parse_weibo_post(uid: str, payload: dict[str, Any]) -> WeiboPost:
    post_id = str(payload.get('id') or payload.get('idstr') or payload.get('mid') or '')
    mblogid = str(payload.get('mblogid') or post_id)
    created_at = parse_weibo_datetime(str(payload.get('created_at') or ''))
    text = strip_html(payload.get('text_raw') or payload.get('text') or '')
    source = strip_html(payload.get('source') or '')
    retweeted_text = parse_retweeted_text(payload.get('retweeted_status'))
    return WeiboPost(
        uid=uid,
        post_id=post_id,
        mblogid=mblogid,
        created_at=created_at,
        text=text,
        source=source,
        reposts_count=parse_count(payload.get('reposts_count')),
        comments_count=parse_count(payload.get('comments_count')),
        attitudes_count=parse_count(payload.get('attitudes_count')),
        image_urls=extract_image_urls(payload),
        card_urls=extract_card_urls(payload),
        retweeted_text=retweeted_text,
    )


def parse_weibo_datetime(value: str) -> datetime:
    if not value:
        raise ValueError('微博返回的 created_at 为空')
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CHINA_TZ)
    return parsed


def parse_count(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def parse_retweeted_text(retweeted_status: Any) -> str | None:
    if not isinstance(retweeted_status, dict):
        return None
    text = strip_html(retweeted_status.get('text_raw') or retweeted_status.get('text') or '')
    user = retweeted_status.get('user') or {}
    screen_name = user.get('screen_name') or user.get('name')
    if screen_name and text:
        return f'@{screen_name}: {text}'
    return text or None


def extract_image_urls(payload: dict[str, Any]) -> tuple[str, ...]:
    urls: list[str] = []
    pic_infos = payload.get('pic_infos') or {}
    if isinstance(pic_infos, dict):
        for info in pic_infos.values():
            if not isinstance(info, dict):
                continue
            url = first_url_from_picture_info(info)
            if url:
                urls.append(url)
    return tuple(dedupe(urls))


def first_url_from_picture_info(info: dict[str, Any]) -> str | None:
    for key in ('largest', 'large', 'original', 'mw2000', 'mw1024'):
        candidate = info.get(key)
        if isinstance(candidate, dict) and candidate.get('url'):
            return str(candidate['url'])
    if info.get('url'):
        return str(info['url'])
    return None


def extract_card_urls(payload: dict[str, Any]) -> tuple[str, ...]:
    cards: list[str] = []
    page_info = payload.get('page_info')
    if isinstance(page_info, dict):
        page_url = page_info.get('page_url')
        if page_url:
            title = strip_html(page_info.get('page_title') or page_info.get('content1') or '')
            cards.append(f'{title}: {page_url}' if title else str(page_url))

    for item in payload.get('url_struct') or []:
        if not isinstance(item, dict):
            continue
        long_url = item.get('long_url') or item.get('ori_url')
        if not long_url:
            continue
        title = strip_html(item.get('url_title') or '')
        cards.append(f'{title}: {long_url}' if title else str(long_url))

    return tuple(dedupe(cards))


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return DEFAULT_CONFIG
    with path.open('r', encoding='utf-8') as handle:
        config = json.load(handle)
    return {**DEFAULT_CONFIG, **config}


def accounts_from_config(config: dict[str, Any]) -> list[Account]:
    accounts = []
    for item in config.get('accounts') or []:
        uid = str(item.get('uid') or '').strip()
        if not uid:
            continue
        accounts.append(
            Account(
                uid=uid,
                folder=item.get('folder'),
                name=item.get('name'),
            )
        )
    if not accounts:
        raise ValueError('配置里没有可抓取的 accounts')
    return accounts


def filter_accounts_by_uids(accounts: list[Account], uids: list[str] | None) -> list[Account]:
    if not uids:
        return accounts
    wanted = {uid.strip() for uid in uids if uid.strip()}
    filtered = [account for account in accounts if account.uid in wanted]
    missing = wanted - {account.uid for account in filtered}
    if missing:
        raise ValueError(f'配置里找不到这些 UID: {", ".join(sorted(missing))}')
    return filtered


def parse_delay(config: dict[str, Any]) -> tuple[float, float]:
    value = config.get('request_delay_seconds', [1.5, 3.5])
    if isinstance(value, (int, float)):
        delay = float(value)
        return (delay, delay)
    if isinstance(value, list) and len(value) == 2:
        return (float(value[0]), float(value[1]))
    return (1.5, 3.5)


def previous_month_window(now: datetime) -> FetchWindow:
    local_now = now.astimezone(CHINA_TZ)
    this_month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if this_month_start.month == 1:
        start = this_month_start.replace(year=this_month_start.year - 1, month=12)
    else:
        start = this_month_start.replace(month=this_month_start.month - 1)
    return FetchWindow(
        start=start,
        end=this_month_start,
        label=f'previous-month:{start.year:04d}-{start.month:02d}',
    )


def last_years_window(now: datetime, years: int) -> FetchWindow:
    local_now = now.astimezone(CHINA_TZ)
    start = subtract_years(local_now, years).replace(hour=0, minute=0, second=0, microsecond=0)
    return FetchWindow(
        start=start,
        end=local_now,
        label=f'bootstrap:last-{years}-years',
        mark_bootstrap_completed=True,
    )


def subtract_years(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, month=2, day=28)


def resolve_fetch_window(mode: str, state: dict[str, Any], now: datetime, years: int) -> FetchWindow | None:
    if mode == 'all':
        return None
    if mode == 'previous-month':
        return previous_month_window(now)
    if mode == 'bootstrap':
        return last_years_window(now, years)
    if mode == 'auto':
        if state.get('bootstrap_completed'):
            return previous_month_window(now)
        return last_years_window(now, years)
    raise ValueError(f'Unknown fetch mode: {mode}')


def filter_posts_for_window(posts: Iterable[WeiboPost], window: FetchWindow | None) -> list[WeiboPost]:
    if window is None:
        return list(posts)
    filtered = []
    for post in posts:
        created_at = post.local_created_at
        if window.start is not None and created_at < window.start:
            continue
        if window.end is not None and created_at >= window.end:
            continue
        filtered.append(post)
    return filtered


def page_is_before_window(posts: Iterable[WeiboPost], window: FetchWindow | None) -> bool:
    if window is None or window.start is None:
        return False
    page_posts = list(posts)
    if not page_posts:
        return False
    return all(post.local_created_at < window.start for post in page_posts)


def split_window_into_chunks(window: FetchWindow, days: int) -> list[tuple[datetime, datetime]]:
    if window.start is None or window.end is None:
        raise ValueError('window must have both start and end')
    if days <= 0:
        raise ValueError('days must be greater than zero')
    chunks = []
    current = window.start
    step = timedelta(days=days)
    while current < window.end:
        chunk_end = min(current + step, window.end)
        chunks.append((current, chunk_end))
        current = chunk_end
    return chunks


def load_run_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open('r', encoding='utf-8') as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f'{path} must contain a JSON object')
    return raw


def save_run_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def state_file_for_output(output_root: Path) -> Path:
    return output_root / '.weibo_crawler_state.json'


def page_limit_for_window(config: dict[str, Any], window: FetchWindow | None, max_pages: int | None) -> int:
    if max_pages:
        return max_pages
    if window and window.mark_bootstrap_completed:
        return int(config.get('bootstrap_max_pages') or config.get('max_pages') or 3000)
    if window and window.label.startswith('previous-month:'):
        return int(config.get('monthly_max_pages') or config.get('max_pages') or 300)
    return int(config.get('max_pages') or 10)


def update_successful_run_state(
    state_file: Path,
    existing_state: dict[str, Any],
    window: FetchWindow | None,
    now: datetime,
    accounts: list[Account],
) -> None:
    state = dict(existing_state)
    if window and window.mark_bootstrap_completed:
        state['bootstrap_completed'] = True
        state['bootstrap_completed_at'] = now.astimezone(CHINA_TZ).isoformat()
    state['last_successful_run'] = now.astimezone(CHINA_TZ).isoformat()
    state['last_window'] = {
        'label': window.label if window else 'all',
        'start': window.start.isoformat() if window and window.start else None,
        'end': window.end.isoformat() if window and window.end else None,
    }
    state['accounts'] = [account.uid for account in accounts]
    save_run_state(state_file, state)


def run(
    config_path: Path,
    output_dir: str | None,
    max_pages: int | None,
    dry_run: bool,
    mode: str,
    years: int | None,
    uids: list[str] | None = None,
) -> int:
    config = load_config(config_path)
    accounts = filter_accounts_by_uids(accounts_from_config(config), uids)
    output_root = Path(output_dir or config.get('output_dir') or 'archive')
    state_file = state_file_for_output(output_root)
    state = load_run_state(state_file)
    now = datetime.now(CHINA_TZ)
    bootstrap_years = years or int(config.get('bootstrap_years') or 5)
    window = resolve_fetch_window(mode, state, now, bootstrap_years)
    page_limit = page_limit_for_window(config, window, max_pages)
    cookie, xsrf_token = resolve_credentials(config_path)
    client = WeiboClient(
        cookie=cookie,
        xsrf_token=xsrf_token,
        timeout_seconds=int(config.get('request_timeout_seconds') or 45),
        max_retries=int(config.get('request_retries') or 3),
        delay_seconds=parse_delay(config),
    )

    if not client.cookie:
        print(
            '提示: 未设置 WEIBO_COOKIE，也没有找到 weibo_secrets.json；'
            '若接口返回 401/403，请登录微博后提供 Cookie。'
        )

    total_posts = 0
    if window:
        start = window.start.isoformat() if window.start else '-∞'
        end = window.end.isoformat() if window.end else '+∞'
        print(f'抓取范围: {window.label} [{start}, {end})')
    else:
        print('抓取范围: all')
    for account in accounts:
        resolved_account = account
        if not resolved_account.folder and not resolved_account.name:
            profile_name = client.fetch_profile_name(account.uid)
            resolved_account = Account(uid=account.uid, name=profile_name)
        print(f'抓取 {resolved_account.folder_name} ({resolved_account.uid})，最多 {page_limit} 页...')
        posts = client.fetch_posts(resolved_account, page_limit, window=window)
        total_posts += len(posts)
        if dry_run:
            print(f'  预演: 抓到 {len(posts)} 条，不写入文件。')
            continue
        archive_posts(output_root, resolved_account, posts)
        print(f'  已归档 {len(posts)} 条到 {output_root / resolved_account.folder_name}')

    if not dry_run:
        update_successful_run_state(state_file, state, window, now, accounts)
    print(f'完成：本次共处理 {total_posts} 条微博。')
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='抓取指定微博账号，并按 人/YYYY.txt 归档。')
    parser.add_argument('--config', default='weibo_accounts.json', help='账号配置 JSON 文件路径')
    parser.add_argument('--output', help='覆盖配置里的输出目录')
    parser.add_argument('--max-pages', type=int, help='每个账号最多抓取多少页')
    parser.add_argument(
        '--mode',
        choices=('auto', 'bootstrap', 'previous-month', 'all'),
        default='auto',
        help='抓取模式：auto 首次近几年、之后上月；bootstrap 近几年；previous-month 上月；all 不限日期',
    )
    parser.add_argument('--years', type=int, help='bootstrap 模式抓取最近几年，默认读取配置里的 bootstrap_years')
    parser.add_argument('--uid', action='append', help='只抓取指定 UID，可重复传入')
    parser.add_argument('--dry-run', action='store_true', help='只抓取和打印数量，不写文件')
    return parser


def resolve_credentials(config_path: Path) -> tuple[str, str]:
    secret_path = os.environ.get('WEIBO_SECRETS_FILE')
    if secret_path:
        secrets_file = Path(secret_path)
    else:
        secrets_file = config_path.parent / 'weibo_secrets.json'
    secrets = load_secrets(secrets_file)
    cookie = os.environ.get('WEIBO_COOKIE') or secrets.get('WEIBO_COOKIE') or secrets.get('cookie') or ''
    xsrf_token = (
        os.environ.get('WEIBO_XSRF_TOKEN')
        or secrets.get('WEIBO_XSRF_TOKEN')
        or secrets.get('xsrf_token')
        or ''
    )
    return cookie, xsrf_token


def load_secrets(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open('r', encoding='utf-8') as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f'{path} 必须是 JSON 对象')
    return {str(key): str(value) for key, value in raw.items() if value is not None}


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        return run(Path(args.config), args.output, args.max_pages, args.dry_run, args.mode, args.years, args.uid)
    except Exception as exc:
        print(f'失败: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
