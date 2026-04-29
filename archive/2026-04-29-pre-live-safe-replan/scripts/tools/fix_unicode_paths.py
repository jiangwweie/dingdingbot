#!/usr/bin/env python3
"""
Unicode 路径规范化修复脚本

macOS 文件系统使用 NFD (Normalized Form Decomposed) 存储 Unicode 文件名，
但大多数工具期望 NFC (Normalized Form Composed) 格式。

此脚本提供路径规范化功能，确保文件路径正确匹配。

使用方法:
    from fix_unicode_paths import normalize_path, read_md_file

    # 方法 1: 规范化路径
    path = normalize_path("/path/to/中文文件.md")

    # 方法 2: 直接读取中文文件名的 MD 文件
    content = read_md_file("/path/to/中文文件.md")
"""

import os
import unicodedata
from pathlib import Path
from typing import Optional, Union


def normalize_to_nfc(path: Union[str, Path]) -> str:
    """
    将路径转换为 NFC 规范化形式。

    macOS 文件系统存储文件名为 NFD 格式，但 Python 和大多数工具期望 NFC。
    """
    return unicodedata.normalize('NFC', str(path))


def normalize_to_nfd(path: Union[str, Path]) -> str:
    """
    将路径转换为 NFD 规范化形式（macOS 文件系统格式）。
    """
    return unicodedata.normalize('NFD', str(path))


def normalize_path(path: Union[str, Path]) -> str:
    """
    智能规范化路径，尝试找到实际存在的文件。

    优先使用 NFC，如果文件不存在则尝试 NFD。
    """
    path_str = str(path)

    # 首先尝试 NFC（标准格式）
    nfc_path = normalize_to_nfc(path_str)
    if os.path.exists(nfc_path):
        return nfc_path

    # 尝试 NFD（macOS 文件系统格式）
    nfd_path = normalize_to_nfd(path_str)
    if os.path.exists(nfd_path):
        return nfd_path

    # 如果都不存在，尝试在目录中搜索相似文件
    parent = os.path.dirname(path_str)
    basename = os.path.basename(path_str)

    if parent and os.path.isdir(parent):
        # 规范化 basename 后搜索
        nfc_basename = normalize_to_nfc(basename)
        for filename in os.listdir(parent):
            if normalize_to_nfc(filename) == nfc_basename:
                return os.path.join(parent, filename)

    # 返回原始路径（让调用者处理错误）
    return path_str


def read_md_file(path: Union[str, Path], encoding: str = 'utf-8') -> str:
    """
    读取 Markdown 文件，自动处理 Unicode 路径规范化。

    Args:
        path: 文件路径
        encoding: 文件编码，默认 utf-8

    Returns:
        文件内容
    """
    normalized_path = normalize_path(path)

    with open(normalized_path, 'r', encoding=encoding) as f:
        return f.read()


def find_md_files(directory: Union[str, Path], pattern: str = '*.md') -> list:
    """
    查找目录中的所有 Markdown 文件，返回规范化路径。

    Args:
        directory: 搜索目录
        pattern: 匹配模式，默认 '*.md'

    Returns:
        规范化路径列表
    """
    directory = normalize_path(str(directory))
    results = []

    for root, dirs, files in os.walk(directory):
        for filename in files:
            if filename.endswith('.md'):
                full_path = os.path.join(root, filename)
                results.append(normalize_path(full_path))

    return results


# ============================================================
# CLI Usage
# ============================================================
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python fix_unicode_paths.py <path1> [path2] ...")
        print("\nExample:")
        print("  python fix_unicode_paths.py docs/tasks/叮盘狗 - 系统演进全景路线图.md")
        sys.exit(1)

    for input_path in sys.argv[1:]:
        print(f"\nInput path:  {repr(input_path)}")
        normalized = normalize_path(input_path)
        print(f"Normalized:  {repr(normalized)}")
        print(f"Exists:      {os.path.exists(normalized)}")

        if normalized.endswith('.md'):
            try:
                content = read_md_file(normalized)
                print(f"Content preview: {content[:100]}...")
            except Exception as e:
                print(f"Read error: {e}")
