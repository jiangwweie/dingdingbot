#!/usr/bin/env python3
"""
检查循环导入

检测模块间是否存在循环依赖，确保 Clean Architecture 分层正确。
"""

import ast
import sys
from pathlib import Path
from collections import defaultdict

# 跳过检查的目录
SKIP_DIRS = {'venv', '.venv', 'node_modules', '__pycache__', '.git', 'tests'}


def extract_imports(filepath: Path) -> list[str]:
    """提取文件的所有导入"""
    imports = []

    try:
        code = filepath.read_text(encoding='utf-8')
        tree = ast.parse(code)
    except Exception:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return imports


def build_dependency_graph(src_dir: Path) -> dict[str, set[str]]:
    """构建依赖关系图"""
    graph = defaultdict(set)
    module_paths = {}

    # 建立模块名到文件路径的映射
    for filepath in src_dir.rglob('*.py'):
        if any(skip in str(filepath) for skip in SKIP_DIRS):
            continue

        # 将文件路径转换为模块名
        rel_path = filepath.relative_to(src_dir)
        module_name = str(rel_path.with_suffix('')).replace('/', '.')
        module_paths[module_name] = filepath
        module_paths[filepath.stem] = filepath  # 简单映射

    # 构建依赖图
    for filepath in src_dir.rglob('*.py'):
        if any(skip in str(filepath) for skip in SKIP_DIRS):
            continue

        rel_path = filepath.relative_to(src_dir)
        current_module = str(rel_path.with_suffix('')).replace('/', '.')

        imports = extract_imports(filepath)
        for imp in imports:
            # 只关注项目内部导入
            if imp.startswith('src.'):
                dep_module = imp.replace('src.', '')
                graph[current_module].add(dep_module)

    return graph


def detect_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """检测循环依赖"""
    cycles = []
    visited = set()
    rec_stack = set()

    def dfs(node: str, path: list[str]) -> None:
        if node in rec_stack:
            # 找到循环
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            cycles.append(cycle)
            return

        if node in visited:
            return

        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            dfs(neighbor, path.copy())

        rec_stack.remove(node)

    for node in graph:
        if node not in visited:
            dfs(node, [])

    return cycles


def check_layer_violations(graph: dict[str, set[str]]) -> list[str]:
    """检查 Clean Architecture 分层违规"""
    violations = []

    # 定义分层依赖规则 (上层不能依赖下层)
    layer_order = ['domain', 'application', 'infrastructure', 'interfaces']
    layer_index = {layer: i for i, layer in enumerate(layer_order)}

    for module, deps in graph.items():
        # 确定当前模块的层
        current_layer = None
        for layer in layer_order:
            if module.startswith(layer):
                current_layer = layer
                break

        if current_layer is None:
            continue

        current_index = layer_index[current_layer]

        # 检查是否依赖了上层
        for dep in deps:
            for layer in layer_order:
                if dep.startswith(layer):
                    dep_index = layer_index[layer]
                    # domain 不能依赖 application/infrastructure/interfaces
                    if current_index > dep_index:
                        violations.append(
                            f"分层违规：{module} ({current_layer}) 依赖 {dep} ({layer})"
                        )

    return violations


def main():
    """主函数"""
    src_dir = Path('src')
    if not src_dir.exists():
        print("错误：src 目录不存在")
        sys.exit(1)

    print("构建依赖关系图...")
    graph = build_dependency_graph(src_dir)

    print("检测循环依赖...")
    cycles = detect_cycles(graph)

    print("检查分层违规...")
    violations = check_layer_violations(graph)

    # 输出结果
    print(f"\n检查完成:")

    if cycles:
        print(f"\n❌ 发现 {len(cycles)} 个循环依赖:")
        for i, cycle in enumerate(cycles, 1):
            print(f"  {i}. {' -> '.join(cycle)}")

    if violations:
        print(f"\n❌ 发现 {len(violations)} 个分层违规:")
        for v in violations[:20]:
            print(f"  - {v}")
        if len(violations) > 20:
            print(f"  ... 还有 {len(violations) - 20} 个违规未显示")

    if not cycles and not violations:
        print("✅ 无循环依赖，分层正确")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
