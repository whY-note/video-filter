#!/usr/bin/env python3
"""Delete data outside accepted trajectory directories and matching .vla files."""

import argparse
import json
from pathlib import Path
import re
import shutil


def cleanup_plan(directory):
    """Validate the complete keep list before returning any deletion targets."""
    if not directory.is_dir():
        raise ValueError(f'数据目录不存在或不是目录: {directory}')
    progress_path = directory / 'progress.json'
    with progress_path.open(encoding='utf-8') as stream:
        progress = json.load(stream)
    if not isinstance(progress, dict) or not isinstance(progress.get('accepted'), list):
        raise ValueError('progress.json 必须包含 accepted 数组')

    keep = {'progress.json'}
    for name in progress['accepted']:
        if not isinstance(name, str) or not re.fullmatch(r'traj_[0-9]+_videos', name):
            raise ValueError(f'accepted 中的轨迹目录名无效: {name!r}')
        vla_name = name[:-len('_videos')] + '.vla'
        if not (directory / name).is_dir():
            raise ValueError(f'accepted 中的轨迹目录不存在或不是目录: {name}')
        if not (directory / vla_name).is_file():
            raise ValueError(f'accepted 对应的 .vla 文件不存在或不是文件: {vla_name}')
        keep.update((name, vla_name))

    targets = sorted(
        (path for path in directory.iterdir() if path.name not in keep),
        key=lambda path: path.name,
    )
    return (len(keep) - 1) // 2, targets


def main():
    parser = argparse.ArgumentParser(
        description='根据 progress.json，仅保留 accepted 轨迹目录、对应 .vla 和 progress.json；删除目录内其余内容。',
    )
    parser.add_argument('data_dir', type=Path, help='包含 progress.json 的数据目录')
    parser.add_argument('--dry-run', action='store_true', help='仅列出待删除项，不执行删除')
    args = parser.parse_args()

    try:
        directory = args.data_dir.expanduser().resolve()
        accepted_count, targets = cleanup_plan(directory)
        for path in targets:
            if args.dry_run:
                print(f'[待删除] {path}')
                continue
            # Unlink directory symlinks without traversing their targets.
            if path.is_symlink() or not path.is_dir():
                path.unlink()
            else:
                shutil.rmtree(path)
            print(f'[已删除] {path}')
    except (OSError, ValueError, UnicodeError) as error:
        parser.exit(1, f'error: {error}\n')

    action = '待删除' if args.dry_run else '已删除'
    print(f'保留 {accepted_count} 条 accepted 轨迹及对应 .vla；{action} {len(targets)} 个顶层条目。')


if __name__ == '__main__':
    main()
