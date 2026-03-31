#!/usr/bin/env python3
"""
批量重命名 MD 文件 - 移除多余空格

macOS 文件系统对中文文件名的空格处理不一致，导致读取失败。
此脚本将所有 MD 文件名中的多余空格移除，统一命名格式。

使用前请确保：
1. 已提交当前所有更改到 git
2. 已备份重要文件

使用方法:
    python3 scripts/standardize_filenames.py docs/
"""

import os
import unicodedata
import sys
from pathlib import Path


def standardize_filename(filename: str) -> str:
    """
    标准化文件名：
    1. NFC 规范化
    2. 移除多余空格（保留必要的单个空格）
    3. 统一连字符格式
    """
    # NFC 规范化
    normalized = unicodedata.normalize('NFC', filename)

    # 移除文件名中的空格（中文之间不需要空格）
    # 但保留扩展名前的空格（如果有）
    name, ext = os.path.splitext(normalized)

    # 移除所有空格
    no_space_name = name.replace(' ', '')

    return no_space_name + ext


def needs_standardization(filename: str) -> bool:
    """
    检查文件名是否需要标准化。
    """
    return ' ' in filename or unicodedata.normalize('NFC', filename) != filename


def standardize_directory(directory: str, dry_run: bool = True) -> list:
    """
    标准化目录中的所有 MD 文件名。

    Args:
        directory: 目标目录
        dry_run: 如果为 True，只显示预览不实际重命名

    Returns:
        需要重命名的文件列表
    """
    changes = []

    for root, dirs, files in os.walk(directory):
        # 跳过隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for filename in files:
            if filename.endswith('.md'):
                if needs_standardization(filename):
                    old_path = os.path.join(root, filename)
                    new_filename = standardize_filename(filename)
                    new_path = os.path.join(root, new_filename)

                    # 检查目标文件是否已存在
                    if os.path.exists(new_path):
                        print(f"⚠️  跳过 {filename} - 目标文件已存在：{new_filename}")
                        continue

                    changes.append((old_path, new_path, filename, new_filename))

    return changes


def main():
    if len(sys.argv) < 2:
        print("Usage: python standardize_filenames.py <directory> [--apply]")
        print("\nArguments:")
        print("  <directory>  要处理的目录")
        print("  --apply      实际执行重命名（默认只预览）")
        print("\nExample:")
        print("  python standardize_filenames.py docs/           # 预览变更")
        print("  python standardize_filenames.py docs/ --apply   # 实际执行")
        sys.exit(1)

    directory = sys.argv[1]
    apply_changes = '--apply' in sys.argv

    if not os.path.isdir(directory):
        print(f"Error: {directory} is not a valid directory")
        sys.exit(1)

    print(f"Scanning MD files in {directory}...")
    print("=" * 60)

    changes = standardize_directory(directory, dry_run=not apply_changes)

    if not changes:
        print("✓ No files need standardization")
        return

    print(f"\nFound {len(changes)} file(s) to rename:\n")

    for old_path, new_path, old_name, new_name in changes:
        print(f"  {old_name}")
        print(f"    → {new_name}")
        print()

    if not apply_changes:
        print("-" * 60)
        print("This is a DRY RUN. To apply changes, run with --apply flag:")
        print(f"  python3 {sys.argv[0]} {directory} --apply")
    else:
        print("-" * 60)
        print("Applying changes...\n")

        # Git check
        has_git = os.path.exists(os.path.join(directory, '..', '.git'))

        for old_path, new_path, old_name, new_name in changes:
            try:
                os.rename(old_path, new_path)
                print(f"✓ Renamed: {old_name} → {new_name}")

                # Git add if available
                if has_git:
                    os.system(f"git add -A \"{new_path}\" 2>/dev/null")
                    if os.path.exists(old_path):
                        os.system(f"git rm -f \"{old_path}\" 2>/dev/null")

            except Exception as e:
                print(f"✗ Failed to rename {old_name}: {e}")

        print("\n" + "=" * 60)
        if has_git:
            print("Changes staged in git. Review with: git status")
            print("Commit with: git commit -m 'chore: standardize MD filenames'")
        else:
            print("✓ Done!")


if __name__ == '__main__':
    main()
