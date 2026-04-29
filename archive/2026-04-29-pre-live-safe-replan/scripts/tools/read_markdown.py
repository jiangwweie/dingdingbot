#!/usr/bin/env python3
"""
读取 Markdown 文件的包装器 - 处理中文路径问题

macOS 文件系统使用 NFD 格式存储 Unicode 文件名，而大多数工具使用 NFC 格式。
此外，文件名中的空格差异也会导致读取失败。

此脚本提供：
1. Unicode 规范化 (NFC/NFD) 自动转换
2. 文件名模糊匹配（忽略多余空格）
3. 路径自动修正

使用方法:
    from read_markdown import read_md_file, find_md_file

    # 方法 1: 读取文件（自动处理路径问题）
    content = read_md_file("/path/to/中文文件.md")

    # 方法 2: 查找文件（模糊匹配）
    path = find_md_file("/path/to/dir", "文件名.md")
"""

import os
import unicodedata
from pathlib import Path
from typing import Optional, Union, List


def normalize_text(text: str) -> str:
    """
    规范化文本：NFC 规范化 + 移除多余空格。

    用于文件名比较，忽略 Unicode 格式和空格差异。
    """
    # NFC 规范化
    normalized = unicodedata.normalize('NFC', text)
    # 移除所有空格
    no_space = normalized.replace(' ', '')
    return no_space


def normalize_path(path: Union[str, Path]) -> str:
    """
    规范化文件路径：NFC 规范化。
    """
    return unicodedata.normalize('NFC', str(path))


def find_md_file(search_path: str, filename: str) -> Optional[str]:
    """
    在目录中查找 Markdown 文件（模糊匹配，忽略空格和 Unicode 格式）。

    Args:
        search_path: 搜索目录
        filename: 目标文件名

    Returns:
        完整路径（如果找到），否则 None
    """
    if not os.path.isdir(search_path):
        return None

    normalized_target = normalize_text(filename)

    for root, dirs, files in os.walk(search_path):
        for f in files:
            if f.endswith('.md'):
                normalized_f = normalize_text(f)
                if normalized_f == normalized_target:
                    return os.path.join(root, f)

    return None


def read_md_file(path: str, encoding: str = 'utf-8') -> str:
    """
    读取 Markdown 文件，自动处理路径问题。

    尝试顺序：
    1. 直接使用原始路径
    2. NFC 规范化路径
    3. NFD 规范化路径
    4. 模糊匹配（忽略空格）

    Args:
        path: 文件路径
        encoding: 文件编码，默认 utf-8

    Returns:
        文件内容
    """
    # 尝试 1: 直接读取
    if os.path.exists(path):
        with open(path, 'r', encoding=encoding) as f:
            return f.read()

    # 尝试 2: NFC 规范化
    nfc_path = normalize_path(path)
    if os.path.exists(nfc_path):
        with open(nfc_path, 'r', encoding=encoding) as f:
            return f.read()

    # 尝试 3: NFD 规范化（macOS 文件系统）
    nfd_path = unicodedata.normalize('NFD', path)
    if os.path.exists(nfd_path):
        with open(nfd_path, 'r', encoding=encoding) as f:
            return f.read()

    # 尝试 4: 模糊匹配（忽略空格）
    parent = os.path.dirname(path)
    basename = os.path.basename(path)

    if parent and os.path.isdir(parent):
        matched = find_md_file(parent, basename)
        if matched:
            with open(matched, 'r', encoding=encoding) as f:
                return f.read()

    raise FileNotFoundError(f"Cannot read file: {path}")


def list_md_files(directory: str) -> List[str]:
    """
    列出目录中的所有 Markdown 文件（规范化路径）。

    Args:
        directory: 目标目录

    Returns:
        规范化路径列表
    """
    results = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if f.endswith('.md'):
                full_path = os.path.join(root, f)
                results.append(normalize_path(full_path))
    return sorted(results)


# ============================================================
# CLI Usage
# ============================================================
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python read_markdown.py <path1> [path2] ...")
        print("\nExample:")
        print("  python read_markdown.py 'docs/tasks/叮盘狗 - 系统演进全景路线图.md'")
        print("  python read_markdown.py 'docs/tasks/叮盘狗 - 系统演进全景路线图.md'  # 有空格也能读")
        sys.exit(1)

    for input_path in sys.argv[1:]:
        print(f"\n{'='*60}")
        print(f"Input path:  {repr(input_path)}")

        try:
            content = read_md_file(input_path)
            print(f"✓ Successfully read file")
            print(f"Content preview: {content[:200]}...")
        except Exception as e:
            print(f"✗ Error: {e}")
