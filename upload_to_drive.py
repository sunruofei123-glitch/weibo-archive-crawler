from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_FILE = Path('upload_config.json')
DEFAULT_SOURCE_DIR = Path('archive')
DEFAULT_RCLONE_EXE = Path('.tools') / 'rclone' / 'rclone.exe'
DEFAULT_RCLONE_CONFIG = Path('.rclone') / 'rclone.conf'
SAFE_REMOTE_PATTERN = re.compile(r'^[A-Za-z0-9_.-]+$')
VALID_MODES = {'copy', 'sync'}


@dataclass(frozen=True)
class UploadConfig:
    enabled: bool = False
    remote: str = 'gdrive'
    destination: str = '微博归档'
    mode: str = 'copy'
    create_empty_src_dirs: bool = True
    progress: bool = True

    def __post_init__(self) -> None:
        if not SAFE_REMOTE_PATTERN.match(self.remote):
            raise ValueError('rclone remote 名称只能包含字母、数字、下划线、点和横线')
        if self.mode not in VALID_MODES:
            raise ValueError(f'mode 必须是: {", ".join(sorted(VALID_MODES))}')
        if '\x00' in self.destination or '\n' in self.destination or '\r' in self.destination:
            raise ValueError('Google Drive 目标路径不能包含控制字符')


def load_upload_config(path: Path) -> UploadConfig:
    if not path.exists():
        return UploadConfig()
    with path.open('r', encoding='utf-8') as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f'{path} 必须是 JSON 对象')
    return UploadConfig(
        enabled=bool(raw.get('enabled', False)),
        remote=str(raw.get('remote', 'gdrive')),
        destination=str(raw.get('destination', '微博归档')),
        mode=str(raw.get('mode', 'copy')),
        create_empty_src_dirs=bool(raw.get('create_empty_src_dirs', True)),
        progress=bool(raw.get('progress', True)),
    )


def destination_path(config: UploadConfig) -> str:
    destination = config.destination.strip().strip('/').replace('\\', '/')
    return f'{config.remote}:{destination}' if destination else f'{config.remote}:'


def build_rclone_command(
    source_dir: Path,
    config: UploadConfig,
    rclone_executable: Path | str = 'rclone',
    rclone_config: Path | None = None,
    dry_run: bool = False,
) -> list[str]:
    command = [
        str(rclone_executable),
        config.mode,
        str(source_dir),
        destination_path(config),
    ]
    if rclone_config is not None:
        command.extend(['--config', str(rclone_config)])
    if config.create_empty_src_dirs:
        command.append('--create-empty-src-dirs')
    if config.progress:
        command.append('--progress')
    if dry_run:
        command.append('--dry-run')
    return command


def find_rclone_executable(
    project_local: Path = DEFAULT_RCLONE_EXE,
    path_lookup: Any = shutil.which,
) -> Path | str:
    if project_local.exists():
        return project_local
    found = path_lookup('rclone')
    if found:
        return found
    return project_local


def ensure_rclone_available(rclone_executable: Path | str) -> None:
    if not Path(rclone_executable).exists() and shutil.which(str(rclone_executable)) is None:
        raise RuntimeError(
            f'未找到 rclone。请先安装 rclone 到 {DEFAULT_RCLONE_EXE}，或把 rclone 加入 PATH。'
        )


def run_upload(config_path: Path, source_dir: Path, dry_run: bool = False, force: bool = False) -> int:
    config = load_upload_config(config_path)
    if not config.enabled and not force:
        print(f'上传未启用：请把 {config_path} 里的 enabled 改成 true。')
        return 0
    if not source_dir.exists():
        raise RuntimeError(f'源目录不存在: {source_dir}')
    rclone_executable = find_rclone_executable()
    ensure_rclone_available(rclone_executable)
    rclone_config = DEFAULT_RCLONE_CONFIG if DEFAULT_RCLONE_CONFIG.exists() else None
    command = build_rclone_command(
        source_dir,
        config,
        rclone_executable=rclone_executable,
        rclone_config=rclone_config,
        dry_run=dry_run,
    )
    print('执行:', ' '.join(command))
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f'rclone 上传失败，退出码 {completed.returncode}')
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='使用 rclone 将微博归档上传到 Google Drive。')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG_FILE), help='上传配置 JSON 文件')
    parser.add_argument('--source', default=str(DEFAULT_SOURCE_DIR), help='要上传的本地归档目录')
    parser.add_argument('--dry-run', action='store_true', help='预演上传，不实际写入 Drive')
    parser.add_argument('--force', action='store_true', help='忽略 enabled=false，强制执行')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        return run_upload(
            config_path=Path(args.config),
            source_dir=Path(args.source),
            dry_run=args.dry_run,
            force=args.force,
        )
    except Exception as exc:
        print(f'上传失败: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
