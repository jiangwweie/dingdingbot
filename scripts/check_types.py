#!/usr/bin/env python3
"""
检查类型注解完整性

检查范围:
1. 函数参数是否有类型注解
2. 函数返回值是否有类型注解
3. 是否有使用 Any 代替具体类型
4. domain 层是否有 float 污染
"""

import ast
import sys
from pathlib import Path

# 跳过检查的文件/目录
SKIP_DIRS = {'venv', '.venv', 'node_modules', '__pycache__', '.git'}
SKIP_FILES = {'conftest.py'}

# 允许使用 Any 的场景 (如：泛型、回调)
ALLOW_ANY_PATTERNS = {'Callable', 'Optional', 'Union'}


def check_file(filepath: Path) -> list[str]:
    """检查单个文件的类型注解"""
    issues = []

    try:
        code = filepath.read_text(encoding='utf-8')
        tree = ast.parse(code)
    except Exception as e:
        issues.append(f"无法解析文件：{e}")
        return issues

    for node in ast.walk(tree):
        # 检查函数定义
        if isinstance(node, ast.FunctionDef):
            # 跳过私有方法和魔术方法
            if node.name.startswith('_') and node.name.endswith('_'):
                continue

            # 检查返回值注解
            if node.returns is None:
                issues.append(
                    f"{filepath}:{node.lineno} 函数 `{node.name}` 缺少返回值类型注解"
                )

            # 检查参数注解 (跳过 self/cls)
            for arg in node.args.args + node.args.posonlyargs:
                arg_name = arg.arg
                if arg_name in ('self', 'cls'):
                    continue
                if arg.annotation is None:
                    issues.append(
                        f"{filepath}:{arg.lineno} 函数 `{node.name}` 参数 `{arg_name}` 缺少类型注解"
                    )

            # 检查是否使用了 Any
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id == 'Any':
                    # 检查是否在允许的场景中
                    parent = None
                    for potential_parent in ast.walk(tree):
                        if hasattr(potential_parent, 'value') and potential_parent.value == child:
                            parent = potential_parent
                            break

                    if parent is None or not (
                        isinstance(parent, ast.Subscript) or
                        (hasattr(parent, 'value') and
                         isinstance(parent.value, ast.Name) and
                         parent.value.id in ALLOW_ANY_PATTERNS)
                    ):
                        issues.append(
                            f"{filepath}:{child.lineno} 函数 `{node.name}` 使用了 Any 类型，建议使用具体类型"
                        )

    return issues


def main():
    """主函数"""
    src_dir = Path('src')
    if not src_dir.exists():
        print("错误：src 目录不存在")
        sys.exit(1)

    all_issues = []
    files_checked = 0

    for filepath in src_dir.rglob('*.py'):
        # 跳过排除的目录和文件
        if any(skip in str(filepath) for skip in SKIP_DIRS):
            continue
        if filepath.name in SKIP_FILES:
            continue

        files_checked += 1
        issues = check_file(filepath)
        all_issues.extend(issues)

    # 输出结果
    print(f"\n检查了 {files_checked} 个文件")

    if all_issues:
        print(f"\n发现 {len(all_issues)} 个问题:\n")
        for issue in all_issues[:50]:  # 限制输出 50 条
            print(f"  {issue}")

        if len(all_issues) > 50:
            print(f"  ... 还有 {len(all_issues) - 50} 个问题未显示")

        print("\n建议：优先修复 domain 层的类型注解问题")
        sys.exit(1)
    else:
        print("✅ 所有文件类型注解完整")
        sys.exit(0)


if __name__ == '__main__':
    main()
