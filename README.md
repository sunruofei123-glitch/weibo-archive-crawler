# Weibo Yearly Archive Crawler / 微博年度归档爬虫

## 中文

这个项目用于抓取 `weibo_accounts.json` 中配置的微博账号，并把微博内容归档到本地年度文本文件。当前归档结构是：

```text
archive/
  刘晓光Savvy/
    2026.txt
  王盐Charles/
    2026.txt
```

每条微博会写入发布时间、微博 ID、链接、来源、互动数、正文、转发原文、图片链接和卡片链接。归档逻辑会按微博 ID 去重，并按发布时间倒序整理。同一次运行抓到的月份会刷新年度文件中对应整月的数据，因此月度自动任务可以覆盖上个月的旧数据。

### 抓取模式

默认是 `auto` 模式：

- 第一次成功执行：抓取最近 5 年的微博，并写入 `archive/.weibo_crawler_state.json` 标记首次归档已完成。
- 之后每月执行：只抓取上一个自然月的微博。例如 2026-05-02 执行时，只抓取 2026-04-01 00:00 到 2026-05-01 00:00 之间的内容。
- `--dry-run` 不会写状态文件，所以预演不会消耗“第一次执行”。

### 使用

```powershell
python .\weibo_crawler.py
```

常用参数：

```powershell
python .\weibo_crawler.py --config weibo_accounts.json
python .\weibo_crawler.py --mode previous-month
python .\weibo_crawler.py --mode bootstrap --years 5
python .\weibo_crawler.py --mode bootstrap --uid 5659598386
python .\weibo_crawler.py --dry-run
```

### 登录微博

微博网页接口有时需要登录态。如果遇到 `401`、`403`、返回登录页或风控页，可以用登录脚本打开一个独立浏览器窗口：

```powershell
python -m pip install -r requirements-login.txt
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.playwright-browsers"
python -m playwright install chromium
python .\weibo_login.py
python .\weibo_crawler.py
```

`weibo_login.py` 会等待你在浏览器里扫码或输入账号完成登录，然后把微博 Cookie 保存到 `weibo_secrets.json`。它使用独立浏览器 profile `.weibo_browser_profile/`，并默认从 `.playwright-browsers/` 读取 Playwright 浏览器。脚本不会保存微博密码，也不会读取你现有浏览器的 Cookie。

也可以手动创建本地文件 `weibo_secrets.json`：

```json
{
  "WEIBO_COOKIE": "SUB=...; XSRF-TOKEN=...;",
  "WEIBO_XSRF_TOKEN": "..."
}
```

### 配置

`weibo_accounts.json` 中可以调整：

- `output_dir`: 归档目录。
- `max_pages`: `all` 模式或手动覆盖时的默认页数。
- `monthly_max_pages`: 月度抓取上限页数。
- `bootstrap_max_pages`: 首次近 5 年抓取上限页数。
- `bootstrap_years`: 首次抓取最近几年，默认 5。
- `request_delay_seconds`: 每页之间的随机等待秒数，降低触发风控概率。
- `request_timeout_seconds`: 单次请求超时秒数。
- `request_retries`: 网络超时或连接失败时的重试次数。
- `accounts`: 要抓取的账号列表，`uid` 是微博 UID，`folder` 是本地文件夹名。

### 上传到 Google Drive

项目使用 `rclone` 将本地 `archive` 同步到 Google Drive。真实授权文件 `.rclone/rclone.conf` 不应提交到 GitHub。

复制示例配置并按需修改：

```powershell
Copy-Item .\upload_config.example.json .\upload_config.json
```

示例配置：

```json
{
  "enabled": false,
  "remote": "gdrive",
  "destination": "微博归档",
  "mode": "sync",
  "create_empty_src_dirs": true,
  "progress": false
}
```

预演上传：

```powershell
python .\upload_to_drive.py --dry-run --force
```

正式上传：

```powershell
python .\upload_to_drive.py
```

`mode: sync` 会让 Google Drive 目标目录镜像本地 `archive`。如果只想上传和更新文件、不删除云端已有文件，可以改成 `copy`。

### 测试

```powershell
python -m unittest discover -s tests
```

### 安全说明

以下内容包含登录态、授权 token、归档数据或本机缓存，默认不会提交：

- `weibo_secrets.json`
- `upload_config.json`
- `.rclone/`
- `.tools/`
- `.weibo_browser_profile/`
- `.playwright-browsers/`
- `archive/`
- `tmp*/`
- `__pycache__/`

## English

This project crawls the Weibo accounts configured in `weibo_accounts.json` and archives posts into yearly text files. The current archive layout is:

```text
archive/
  LiuXiaoguangSavvy/
    2026.txt
  WangYanCharles/
    2026.txt
```

Each post includes publish time, Weibo ID, URL, source, engagement counts, text, reposted text, image URLs, and card URLs. Archive files are deduplicated by Weibo ID and sorted by publish time in descending order. When a run fetches a month, that whole month is refreshed inside the yearly file, so the monthly automation can overwrite stale data from the previous month.

### Crawl Modes

The default mode is `auto`:

- First successful run: crawl the latest 5 years and write `archive/.weibo_crawler_state.json` to mark the bootstrap as complete.
- Later monthly runs: crawl only the previous calendar month. For example, a run on 2026-05-02 fetches posts from 2026-04-01 00:00 to 2026-05-01 00:00.
- `--dry-run` does not write the state file, so it does not consume the first bootstrap run.

### Usage

```powershell
python .\weibo_crawler.py
```

Common commands:

```powershell
python .\weibo_crawler.py --config weibo_accounts.json
python .\weibo_crawler.py --mode previous-month
python .\weibo_crawler.py --mode bootstrap --years 5
python .\weibo_crawler.py --mode bootstrap --uid 5659598386
python .\weibo_crawler.py --dry-run
```

### Weibo Login

The Weibo web API may require a logged-in session. If you see `401`, `403`, a login page, or an anti-abuse page, use the login helper:

```powershell
python -m pip install -r requirements-login.txt
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.playwright-browsers"
python -m playwright install chromium
python .\weibo_login.py
python .\weibo_crawler.py
```

`weibo_login.py` opens an isolated browser profile and waits for you to log in. It then saves the cookie header to `weibo_secrets.json`. The script does not save your Weibo password and does not read cookies from your normal browser.

You can also create `weibo_secrets.json` manually:

```json
{
  "WEIBO_COOKIE": "SUB=...; XSRF-TOKEN=...;",
  "WEIBO_XSRF_TOKEN": "..."
}
```

### Configuration

You can tune these fields in `weibo_accounts.json`:

- `output_dir`: archive directory.
- `max_pages`: default page limit for `all` mode or manual overrides.
- `monthly_max_pages`: page limit for monthly fetches.
- `bootstrap_max_pages`: page limit for the initial multi-year backfill.
- `bootstrap_years`: number of years for bootstrap mode. Default: 5.
- `request_delay_seconds`: randomized delay between pages to reduce anti-abuse risk.
- `request_timeout_seconds`: request timeout in seconds.
- `request_retries`: retry count for network failures.
- `accounts`: account list. `uid` is the Weibo UID, and `folder` is the local archive folder name.

### Uploading To Google Drive

The project uses `rclone` to sync the local `archive` directory to Google Drive. The real OAuth config `.rclone/rclone.conf` must not be committed to GitHub.

Copy the example config:

```powershell
Copy-Item .\upload_config.example.json .\upload_config.json
```

Example:

```json
{
  "enabled": false,
  "remote": "gdrive",
  "destination": "微博归档",
  "mode": "sync",
  "create_empty_src_dirs": true,
  "progress": false
}
```

Dry-run upload:

```powershell
python .\upload_to_drive.py --dry-run --force
```

Real upload:

```powershell
python .\upload_to_drive.py
```

`mode: sync` mirrors the local `archive` directory into the Google Drive destination. Use `copy` if you only want to upload or update files without deleting extra remote files.

### Tests

```powershell
python -m unittest discover -s tests
```

### Security Notes

The following local files and folders may contain login state, OAuth tokens, archived data, or machine cache, and are ignored by default:

- `weibo_secrets.json`
- `upload_config.json`
- `.rclone/`
- `.tools/`
- `.weibo_browser_profile/`
- `.playwright-browsers/`
- `archive/`
- `tmp*/`
- `__pycache__/`
