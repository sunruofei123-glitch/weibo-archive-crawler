# Weibo Yearly Archive Crawler / 微博年度归档爬虫

## 中文

这个项目用于抓取 `weibo_accounts.json` 中配置的微博账号，并把微博内容保存为年度文本文件。它支持：

- 首次抓取最近 5 年微博。
- 之后每次只抓取上一个自然月。
- 按作者分文件夹、按年份生成一个 `.txt` 文件。
- 刷新本次抓取月份的数据，按微博 ID 去重，并按发布时间倒序整理。
- 可选：自动登录微博、同步归档到 Google Drive。

当前归档结构：

```text
archive/
  刘晓光Savvy/
    2026.txt
  王盐Charles/
    2026.txt
```

### 运行环境

必需：

- Windows 10/11、macOS 或 Linux。
- Python 3.10 或更新版本。当前项目在 Python 3.13 上测试通过。
- 可访问微博网页接口的网络环境。
- 一个可登录的微博账号，用于获取登录 Cookie。

可选：

- Git：用于克隆和管理代码。
- Playwright Chromium：用于自动打开浏览器登录微博。
- rclone：用于把本地归档同步到 Google Drive。
- Google 账号：仅当需要上传 Google Drive 时使用。
- Windows 任务计划程序、cron、systemd timer 或其他调度器：用于无人值守的月度任务。

### 如何获取代码

安装 Git 后克隆仓库：

```powershell
git clone https://github.com/sunruofei123-glitch/weibo-archive-crawler.git
cd weibo-archive-crawler
```

也可以在 GitHub 页面点击 `Code` -> `Download ZIP` 下载源码压缩包。

### 如何获取 Python

从 Python 官网下载安装：

- https://www.python.org/downloads/

安装时建议勾选 `Add python.exe to PATH`。安装完成后确认版本：

```powershell
python --version
```

建议创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Linux/macOS 示例：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### Python 依赖

核心爬虫 `weibo_crawler.py` 只使用 Python 标准库，不需要安装额外 Python 包。

如果要使用自动登录脚本 `weibo_login.py`，需要安装 Playwright：

```powershell
python -m pip install -r requirements-login.txt
python -m playwright install chromium
```

如果希望 Playwright 浏览器下载到项目目录，Windows PowerShell 可以这样设置：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.playwright-browsers"
python -m playwright install chromium
```

### 配置微博账号

编辑 `weibo_accounts.json`：

```json
{
  "output_dir": "archive",
  "monthly_max_pages": 300,
  "bootstrap_years": 5,
  "accounts": [
    {
      "uid": "2492465520",
      "folder": "刘晓光Savvy"
    },
    {
      "uid": "5659598386",
      "folder": "王盐Charles"
    }
  ]
}
```

主要字段：

- `output_dir`: 归档目录。
- `max_pages`: `all` 模式或手动覆盖时的默认页数。
- `monthly_max_pages`: 月度抓取上限页数。
- `bootstrap_max_pages`: 首次近 5 年抓取上限页数。
- `bootstrap_years`: 首次抓取最近几年，默认 5。
- `request_delay_seconds`: 每页之间的随机等待秒数，降低触发风控概率。
- `request_timeout_seconds`: 单次请求超时秒数。
- `request_retries`: 网络超时或连接失败时的重试次数。
- `accounts`: 要抓取的账号列表，`uid` 是微博 UID，`folder` 是本地文件夹名。

### 配置微博登录态

微博网页接口通常需要登录态。推荐用登录脚本生成 `weibo_secrets.json`：

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.playwright-browsers"
python .\weibo_login.py
```

脚本会打开一个独立 Chromium 浏览器窗口。你在窗口里扫码或输入账号登录后，脚本会把 Cookie 保存到：

```text
weibo_secrets.json
```

这个文件包含登录态，不能提交到 GitHub。它已经在 `.gitignore` 中。

也可以复制示例文件后手动填写：

```powershell
Copy-Item .\weibo_secrets.example.json .\weibo_secrets.json
```

格式：

```json
{
  "WEIBO_COOKIE": "SUB=...; XSRF-TOKEN=...;",
  "WEIBO_XSRF_TOKEN": "..."
}
```

也可以用环境变量传入：

```powershell
$env:WEIBO_COOKIE = "SUB=...; XSRF-TOKEN=...;"
$env:WEIBO_XSRF_TOKEN = "..."
```

### 运行爬虫

首次执行，抓取最近 5 年：

```powershell
python .\weibo_crawler.py --config weibo_accounts.json --mode auto
```

首次成功后，脚本会写入：

```text
archive/.weibo_crawler_state.json
```

之后继续使用 `auto`，就只会抓取上一个自然月：

```powershell
python .\weibo_crawler.py --config weibo_accounts.json --mode auto
```

常用命令：

```powershell
python .\weibo_crawler.py --mode previous-month
python .\weibo_crawler.py --mode bootstrap --years 5
python .\weibo_crawler.py --mode bootstrap --uid 5659598386
python .\weibo_crawler.py --dry-run
```

### 上传到 Google Drive

上传功能依赖 rclone。获取方式：

- 官方下载：https://rclone.org/downloads/
- Windows 用户也可以用 Scoop、Chocolatey 或 winget 等包管理器安装。
- macOS 用户可以用 Homebrew：`brew install rclone`。
- Linux 用户可以使用发行版包管理器或 rclone 官方安装脚本。

安装后确认：

```powershell
rclone version
```

配置 Google Drive remote：

```powershell
rclone config
```

建议 remote 名称使用：

```text
gdrive
```

如果想把 rclone 配置保存在项目目录，可以使用：

```powershell
rclone --config .\.rclone\rclone.conf config
```

真实授权文件 `.rclone/rclone.conf` 包含 OAuth token，不能提交到 GitHub，已经在 `.gitignore` 中。

复制上传配置：

```powershell
Copy-Item .\upload_config.example.json .\upload_config.json
```

编辑 `upload_config.json`：

```json
{
  "enabled": true,
  "remote": "gdrive",
  "destination": "微博归档",
  "mode": "sync",
  "create_empty_src_dirs": true,
  "progress": false
}
```

字段说明：

- `enabled`: 是否启用上传。正式使用请改为 `true`。
- `remote`: rclone remote 名称，通常是 `gdrive`。
- `destination`: Google Drive 中的目标文件夹。
- `mode`: `sync` 会让云端目标目录镜像本地 `archive`；`copy` 只上传和更新，不删除云端多余文件。
- `create_empty_src_dirs`: 是否在云端创建空目录。
- `progress`: 是否显示 rclone 进度。

预演上传：

```powershell
python .\upload_to_drive.py --dry-run --force
```

正式上传：

```powershell
python .\upload_to_drive.py
```

### 月度自动任务

月度任务应该按这个顺序执行：

```powershell
python -m unittest discover -s tests
python .\weibo_crawler.py --config weibo_accounts.json --mode auto
python .\upload_to_drive.py
```

在 Windows 任务计划程序中，可以创建每月 2 日 09:00 执行的任务，工作目录设为本项目目录，命令使用 PowerShell 或 Python。核心命令是：

```powershell
python .\weibo_crawler.py --config weibo_accounts.json --mode auto
python .\upload_to_drive.py
```

Linux/macOS 可以用 cron 或 systemd timer 执行同样的命令。确保任务运行用户能读取：

- Python 虚拟环境。
- `weibo_secrets.json`。
- `.rclone/rclone.conf` 或系统级 rclone 配置。
- 本项目目录下的 `archive/`。

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

公开仓库前建议检查：

```powershell
git status --ignored
git ls-tree -r --name-only HEAD
```

### 常见问题

如果微博接口返回 `401`、`403`、登录页或风控页，重新运行：

```powershell
python .\weibo_login.py
```

如果 Google Drive 上传失败，检查：

- `rclone version` 是否可用。
- `upload_config.json` 的 `enabled` 是否为 `true`。
- `remote` 是否和 `rclone config` 中的名称一致。
- `.rclone/rclone.conf` 是否存在并仍然有效。

## English

This project crawls the Weibo accounts configured in `weibo_accounts.json` and stores posts as yearly text archives. It supports:

- Initial backfill for the latest 5 years.
- Later runs that fetch only the previous calendar month.
- One folder per author and one `.txt` file per year.
- Month refresh, Weibo ID deduplication, and descending publish-time ordering.
- Optional Weibo login automation and Google Drive sync.

Archive layout:

```text
archive/
  LiuXiaoguangSavvy/
    2026.txt
  WangYanCharles/
    2026.txt
```

### Runtime Requirements

Required:

- Windows 10/11, macOS, or Linux.
- Python 3.10 or newer. The project is tested with Python 3.13.
- Network access to Weibo web APIs.
- A Weibo account that can be used to obtain login cookies.

Optional:

- Git, for cloning and managing the source code.
- Playwright Chromium, for interactive Weibo login.
- rclone, for syncing archives to Google Drive.
- A Google account, only if Google Drive upload is needed.
- Windows Task Scheduler, cron, systemd timer, or another scheduler for unattended monthly runs.

### Getting The Code

Install Git and clone:

```powershell
git clone https://github.com/sunruofei123-glitch/weibo-archive-crawler.git
cd weibo-archive-crawler
```

You can also download a ZIP from GitHub with `Code` -> `Download ZIP`.

### Getting Python

Download Python from:

- https://www.python.org/downloads/

On Windows, select `Add python.exe to PATH` during installation. Verify:

```powershell
python --version
```

Recommended virtual environment setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### Python Dependencies

The core crawler `weibo_crawler.py` uses only the Python standard library.

The login helper `weibo_login.py` requires Playwright:

```powershell
python -m pip install -r requirements-login.txt
python -m playwright install chromium
```

To keep Playwright browsers inside the project directory on Windows PowerShell:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.playwright-browsers"
python -m playwright install chromium
```

### Configuring Weibo Accounts

Edit `weibo_accounts.json`:

```json
{
  "output_dir": "archive",
  "monthly_max_pages": 300,
  "bootstrap_years": 5,
  "accounts": [
    {
      "uid": "2492465520",
      "folder": "LiuXiaoguangSavvy"
    },
    {
      "uid": "5659598386",
      "folder": "WangYanCharles"
    }
  ]
}
```

Important fields:

- `output_dir`: archive directory.
- `max_pages`: default page limit for `all` mode or manual overrides.
- `monthly_max_pages`: page limit for monthly fetches.
- `bootstrap_max_pages`: page limit for the initial multi-year backfill.
- `bootstrap_years`: number of years for bootstrap mode. Default: 5.
- `request_delay_seconds`: randomized delay between pages to reduce anti-abuse risk.
- `request_timeout_seconds`: request timeout in seconds.
- `request_retries`: retry count for network failures.
- `accounts`: account list. `uid` is the Weibo UID, and `folder` is the local archive folder name.

### Configuring Weibo Login State

The Weibo web API usually requires a logged-in session. The recommended path is:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.playwright-browsers"
python .\weibo_login.py
```

The script opens an isolated Chromium window. After you log in, it writes cookies to:

```text
weibo_secrets.json
```

This file contains login state and must not be committed. It is already ignored by `.gitignore`.

You can also copy the example and fill it manually:

```powershell
Copy-Item .\weibo_secrets.example.json .\weibo_secrets.json
```

Format:

```json
{
  "WEIBO_COOKIE": "SUB=...; XSRF-TOKEN=...;",
  "WEIBO_XSRF_TOKEN": "..."
}
```

Environment variables are also supported:

```powershell
$env:WEIBO_COOKIE = "SUB=...; XSRF-TOKEN=...;"
$env:WEIBO_XSRF_TOKEN = "..."
```

### Running The Crawler

First run, backfill the latest 5 years:

```powershell
python .\weibo_crawler.py --config weibo_accounts.json --mode auto
```

After a successful first run, the crawler writes:

```text
archive/.weibo_crawler_state.json
```

Later `auto` runs fetch only the previous calendar month:

```powershell
python .\weibo_crawler.py --config weibo_accounts.json --mode auto
```

Common commands:

```powershell
python .\weibo_crawler.py --mode previous-month
python .\weibo_crawler.py --mode bootstrap --years 5
python .\weibo_crawler.py --mode bootstrap --uid 5659598386
python .\weibo_crawler.py --dry-run
```

### Uploading To Google Drive

Google Drive upload uses rclone. Get it from:

- Official downloads: https://rclone.org/downloads/
- Windows package managers such as Scoop, Chocolatey, or winget.
- Homebrew on macOS: `brew install rclone`.
- Linux distribution packages or the official rclone install script.

Verify:

```powershell
rclone version
```

Create a Google Drive remote:

```powershell
rclone config
```

Recommended remote name:

```text
gdrive
```

To store rclone config in the project directory:

```powershell
rclone --config .\.rclone\rclone.conf config
```

The real `.rclone/rclone.conf` contains OAuth tokens and must not be committed.

Copy the upload config:

```powershell
Copy-Item .\upload_config.example.json .\upload_config.json
```

Edit `upload_config.json`:

```json
{
  "enabled": true,
  "remote": "gdrive",
  "destination": "微博归档",
  "mode": "sync",
  "create_empty_src_dirs": true,
  "progress": false
}
```

Fields:

- `enabled`: set to `true` for real uploads.
- `remote`: rclone remote name, usually `gdrive`.
- `destination`: target folder in Google Drive.
- `mode`: `sync` mirrors local `archive`; `copy` uploads/updates without deleting extra remote files.
- `create_empty_src_dirs`: create empty source directories on the remote.
- `progress`: show rclone progress.

Dry run:

```powershell
python .\upload_to_drive.py --dry-run --force
```

Real upload:

```powershell
python .\upload_to_drive.py
```

### Monthly Automation

A monthly job should run these commands in order:

```powershell
python -m unittest discover -s tests
python .\weibo_crawler.py --config weibo_accounts.json --mode auto
python .\upload_to_drive.py
```

On Windows, create a Task Scheduler task for the 2nd day of each month at 09:00. Set the working directory to this project directory. The core commands are:

```powershell
python .\weibo_crawler.py --config weibo_accounts.json --mode auto
python .\upload_to_drive.py
```

On Linux/macOS, use cron or a systemd timer with the same commands. Make sure the scheduled user can read:

- the Python virtual environment,
- `weibo_secrets.json`,
- `.rclone/rclone.conf` or the system rclone config,
- the project `archive/` directory.

### Tests

```powershell
python -m unittest discover -s tests
```

### Security Notes

These local files and folders may contain login state, OAuth tokens, archived data, or machine cache, and are ignored by default:

- `weibo_secrets.json`
- `upload_config.json`
- `.rclone/`
- `.tools/`
- `.weibo_browser_profile/`
- `.playwright-browsers/`
- `archive/`
- `tmp*/`
- `__pycache__/`

Before publishing, inspect:

```powershell
git status --ignored
git ls-tree -r --name-only HEAD
```

### Troubleshooting

If the Weibo API returns `401`, `403`, a login page, or an anti-abuse page, run:

```powershell
python .\weibo_login.py
```

If Google Drive upload fails, check:

- `rclone version` works.
- `upload_config.json` has `enabled: true`.
- `remote` matches the name from `rclone config`.
- `.rclone/rclone.conf` exists and is still authorized.
