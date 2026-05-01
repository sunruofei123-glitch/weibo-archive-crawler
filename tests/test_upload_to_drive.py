import unittest
import shutil
from pathlib import Path

from upload_to_drive import (
    UploadConfig,
    build_rclone_command,
    destination_path,
    find_rclone_executable,
    load_upload_config,
)


class UploadToDriveTests(unittest.TestCase):
    def test_destination_path_joins_remote_and_folder(self):
        config = UploadConfig(remote='gdrive', destination='微博归档')

        self.assertEqual(destination_path(config), 'gdrive:微博归档')

    def test_destination_path_allows_nested_folder(self):
        config = UploadConfig(remote='gdrive', destination='archive/weibo')

        self.assertEqual(destination_path(config), 'gdrive:archive/weibo')

    def test_build_rclone_command_uses_argument_list(self):
        config = UploadConfig(remote='gdrive', destination='微博归档', mode='copy')

        command = build_rclone_command(
            Path('archive'),
            config,
            rclone_executable=Path('.tools/rclone/rclone.exe'),
            rclone_config=Path('.rclone/rclone.conf'),
            dry_run=True,
        )

        self.assertEqual(
            command,
            [
                '.tools\\rclone\\rclone.exe',
                'copy',
                'archive',
                'gdrive:微博归档',
                '--config',
                '.rclone\\rclone.conf',
                '--create-empty-src-dirs',
                '--progress',
                '--dry-run',
            ],
        )

    def test_load_upload_config_defaults_to_disabled(self):
        config = load_upload_config(Path('missing-upload-config.json'))

        self.assertFalse(config.enabled)
        self.assertEqual(config.remote, 'gdrive')
        self.assertEqual(config.destination, '微博归档')

    def test_rejects_unsafe_remote_name(self):
        with self.assertRaises(ValueError):
            UploadConfig(remote='gd; rm -rf /', destination='微博归档')

    def test_find_rclone_executable_prefers_project_local_binary(self):
        output_root = Path.cwd() / 'test-output'
        shutil.rmtree(output_root, ignore_errors=True)
        try:
            local_binary = output_root / '.tools' / 'rclone' / 'rclone.exe'
            local_binary.parent.mkdir(parents=True)
            local_binary.write_text('', encoding='utf-8')

            found = find_rclone_executable(
                project_local=local_binary,
                path_lookup=lambda name: 'C:\\Windows\\rclone.exe',
            )
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

        self.assertEqual(found, local_binary)


if __name__ == '__main__':
    unittest.main()
