#!/usr/bin/env python3
"""
检测 domain 层和应用层的 float 使用

量化交易系统红线：所有金融计算必须使用 Decimal，禁止 float
"""

import ast
import sys
from pathlib import Path

# 允许使用 float 的场景 (非金融计算)
ALLOWED_FUNCTION_NAMES = {
    # 评分相关
    "calculate_score", "score", "pattern_score",
    # 阈值相关
    "threshold", "ratio", "percentage", "percent",
    # 技术指标
    "ema", "sma", "rsi", "macd", "atr",
    # 工具函数
    "to_float", "as_float", "float",
}

# 允许的变量名模式 (非金融计算)
ALLOWED_VAR_PATTERNS = {
    "score", "ratio", "threshold", "percentage",
    "min_wick_ratio", "max_body_ratio", "body_position_tolerance",
    "loss_percent", "max_loss_percent", "trailing_threshold",
    "smooth_factor", "weight", "alpha", "beta",
}

# 禁止 float 的目录 (核心业务逻辑)
STRICT_DIRS = ["src/domain/", "src/application/"]


def check_float_in_file(filepath: Path) -> list[dict]:
    """检查文件中的 float 使用"""
    violations = []

    try:
        source = filepath.read_text(encoding='utf-8')
    except Exception as e:
        return [{"line": 0, "issue": f"Read error: {e}"}]

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [{"line": e.lineno, "issue": f"SyntaxError: {e}"}]

    for node in ast.walk(tree):
        violation = check_node_for_float(node, filepath)
        if violation:
            violations.append(violation)

    return violations


def check_node_for_float(node: ast.AST, filepath: Path) -> dict | None:
    """检查节点是否违反 float 规则"""

    # 检测 float() 调用
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "float":
            # 检查是否在 isinstance 调用中 (允许)
            parent = get_parent_node(node)
            if parent and isinstance(parent, ast.Call):
                if isinstance(parent.func, ast.Name) and parent.func.id == "isinstance":
                    return None  # 允许 isinstance(x, float)

            return {
                "file": str(filepath),
                "line": node.lineno,
                "issue": "float() function call",
                "suggestion": "Use Decimal() instead for financial calculations"
            }

    # 检测 float 类型注解
    elif isinstance(node, ast.AnnAssign):
        if is_float_annotation(node.annotation):
            # 检查变量名是否在允许列表中
            if isinstance(node.target, ast.Name):
                if node.target.id.lower() in ALLOWED_VAR_PATTERNS:
                    return None  # 允许的变量 (如 ratio, threshold)
            return {
                "file": str(filepath),
                "line": node.lineno,
                "issue": "float type annotation",
                "suggestion": "Use Decimal instead for financial values"
            }

    # 检测函数返回值注解
    elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
        # 检查函数名是否在允许列表中
        if node.name.lower() in ALLOWED_FUNCTION_NAMES:
            return None  # 允许的函数 (如 calculate_score)

        if node.returns and is_float_annotation(node.returns):
            return {
                "file": str(filepath),
                "line": node.lineno,
                "issue": f"float return type annotation in {node.name}()",
                "suggestion": "Use Decimal instead for financial calculations"
            }

        # 检查参数注解
        for arg in node.args.args + node.args.kwonlyargs:
            if arg.annotation and is_float_annotation(arg.annotation):
                # 检查参数名是否在允许列表中
                if arg.arg.lower() in ALLOWED_VAR_PATTERNS:
                    return None  # 允许的参数 (如 score, ratio)
                return {
                    "file": str(filepath),
                    "line": arg.lineno,
                    "issue": f"float parameter type annotation in {node.name}({arg.arg}: float)",
                    "suggestion": "Use Decimal instead for financial values"
                }

    # 检测 float 字面量赋值
    elif isinstance(node, ast.Assign):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, float):
            # 检查是否是金融相关变量
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if is_financial_variable(target.id):
                        return {
                            "file": str(filepath),
                            "line": node.lineno,
                            "issue": f"float literal assigned to {target.id}",
                            "suggestion": "Use Decimal() for financial values"
                        }

    return None


def is_float_annotation(annotation: ast.AST) -> bool:
    """检查是否是 float 类型注解"""
    if isinstance(annotation, ast.Name):
        return annotation.id == "float"
    if isinstance(annotation, ast.Constant):
        return annotation.value == "float"
    return False


def is_financial_variable(name: str) -> bool:
    """判断变量名是否与金融计算相关"""
    financial_keywords = [
        "price", "cost", "value", "amount", "balance",
        "pnl", "profit", "loss", "fee", "commission",
        "entry", "exit", "stop_loss", "take_profit",
        "quantity", "size", "position", "order"
    ]
    name_lower = name.lower()
    return any(kw in name_lower for kw in financial_keywords)


def get_parent_node(node: ast.AST) -> ast.AST | None:
    """获取父节点 (简化实现)"""
    # 完整实现需要维护父节点映射
    # 这里返回 None 表示不检查上下文
    return None


def main():
    """主函数"""
    print("=" * 60)
    print("float 使用检测 - 量化系统精度检查")
    print("=" * 60)

    all_violations = []
    files_checked = 0

    # 项目根目录
    root = Path(__file__).parent.parent

    for dir_path in STRICT_DIRS:
        full_path = root / dir_path
        if not full_path.exists():
            print(f"⚠️  目录不存在：{dir_path}")
            continue

        for py_file in full_path.rglob("*.py"):
            files_checked += 1
            violations = check_float_in_file(py_file)
            all_violations.extend(violations)

    print(f"\n检查了 {files_checked} 个 Python 文件")

    if all_violations:
        print(f"\n❌ 发现 {len(all_violations)} 处 float 使用:\n")
        for v in all_violations:
            print(f"  {v['file']}:{v['line']}")
            print(f"    Issue: {v['issue']}")
            print(f"    Fix: {v['suggestion']}\n")
        return 1
    else:
        print("\n✅ float 检测通过 (domain/application 层无违规)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
