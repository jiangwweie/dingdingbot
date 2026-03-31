#!/usr/bin/env python3
"""
批量重命名文件，移除文件名中的空格

macOS 文件系统使用 NFD 格式存储 Unicode 文件名，
而大多数工具期望 NFC 格式。此外，文件名中的空格
会导致 shell 命令和工具读取失败。

此脚本将：
1. 将 NFD 文件名转换为 NFC 格式
2. 移除文件名中的所有空格
3. 保持文件内容不变
"""
import os
import unicodedata
from pathlib import Path


def normalize_filename(filepath: str) -> str:
    """
    规范化文件名：
    1. Unicode NFC 规范化
    2. 移除所有空格
    """
    path = Path(filepath)

    # Unicode NFC 规范化
    normalized_name = unicodedata.normalize('NFC', path.name)

    # 移除所有空格
    normalized_name = normalized_name.replace(' ', '')

    return str(path.parent / normalized_name)


def fix_directory(directory: str) -> list[tuple[str, str]]:
    """
    修复目录下所有文件的命名

    Returns:
        list of (old_path, new_path) tuples
    """
    renames = []

    for filename in os.listdir(directory):
        old_path = os.path.join(directory, filename)
        if not os.path.isfile(old_path):
            continue

        new_path = normalize_filename(old_path)

        if old_path != new_path:
            if os.path.exists(new_path):
                print(f"⚠️  跳过：{filename}")
                print(f"   目标文件已存在：{os.path.basename(new_path)}")
            else:
                renames.append((old_path, new_path))

    return renames


def main():
    """主函数"""
    # 项目根目录
    project_root = Path(__file__).parent.parent

    # 需要修复的目录
    dirs_to_fix = [
        project_root / 'docs',
        project_root / 'docs/tasks',
        project_root / 'docs/arch',
    ]

    all_renames = []

    for dir_path in dirs_to_fix:
        if dir_path.exists():
            renames = fix_directory(str(dir_path))
            all_renames.extend(renames)

    if not all_renames:
        print("✅ 所有文件名已规范化，无需修改")
        return

    print(f"发现 {len(all_renames)} 个文件需要重命名:\n")

    for old_path, new_path in all_renames:
        old_name = os.path.basename(old_path)
        new_name = os.path.basename(new_path)
        print(f"  {old_name}")
        print(f"    ↓")
        print(f"  {new_name}")
        print()

    # 执行重命名
    print("执行重命名...")
    for old_path, new_path in all_renames:
        try:
            os.rename(old_path, new_path)
            print(f"✅ {os.path.basename(old_path)} → {os.path.basename(new_path)}")
        except Exception as e:
            print(f"❌ 失败：{os.path.basename(old_path)} - {e}")

    print(f"\n✅ 完成！重命名了 {len(all_renames)} 个文件")


if __name__ == '__main__':
    main()
