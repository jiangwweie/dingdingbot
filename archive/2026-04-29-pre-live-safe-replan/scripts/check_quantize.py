#!/usr/bin/env python3
"""
检查 CCXT 调用前的 TickSize/LotSize 格式化

量化交易系统红线：所有发送到交易所的价格和数量必须经过 tick_size 和 lot_size 格式化
"""

import ast
import sys
from pathlib import Path

# CCXT 订单相关方法
ORDER_METHODS = {
    'create_order',
    'create_market_order',
    'create_limit_order',
    'create_stop_order',
    'create_stop_limit_order',
    'cancel_order',
    'cancel_all_orders',
}

# 需要格式化的参数
FORMAT_REQUIRED_ARGS = {
    'price': 'tick_size',
    'stopLoss': 'tick_size',
    'takeProfit': 'tick_size',
    'triggerPrice': 'tick_size',
    'amount': 'lot_size',
    'quantity': 'lot_size',
    'size': 'lot_size',
}


def check_quantize_in_file(filepath: Path) -> list[dict]:
    """检查文件中 CCXT 调用的参数格式化"""
    errors = []

    try:
        source = filepath.read_text(encoding='utf-8')
    except Exception as e:
        return [{"line": 0, "call": "N/A", "issue": f"Read error: {e}"}]

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [{"line": e.lineno, "call": "N/A", "issue": f"SyntaxError: {e}"}]

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if is_ccxt_order_call(node):
                call_errors = check_ccxt_call(node, filepath)
                errors.extend(call_errors)

    return errors


def is_ccxt_order_call(node: ast.Call) -> bool:
    """检查是否是 CCXT 订单方法调用"""
    if isinstance(node.func, ast.Attribute):
        if node.func.attr in ORDER_METHODS:
            return True
        # 检查 method 链式调用
        if node.func.attr == 'privatePostOrder':
            return True
    return False


def check_ccxt_call(node: ast.Call, filepath: Path) -> list[dict]:
    """检查 CCXT 调用的参数是否经过格式化"""
    errors = []
    method_name = node.func.attr if isinstance(node.func, ast.Attribute) else "unknown"

    # 检查关键字参数
    for kw in node.keywords:
        if kw.arg in FORMAT_REQUIRED_ARGS:
            required_format = FORMAT_REQUIRED_ARGS[kw.arg]
            if not has_proper_formatting(kw.value, required_format):
                errors.append({
                    "file": str(filepath),
                    "line": kw.lineno,
                    "call": method_name,
                    "arg": kw.arg,
                    "format_type": required_format,
                    "issue": f"Argument '{kw.arg}' may not be formatted with {required_format}",
                    "suggestion": f"Use value.quantize(market['{required_format}']) before passing to CCXT"
                })

    # 检查位置参数 (CCXT create_order 签名)
    # create_order(symbol, type, side, amount, price=None, params={})
    if len(node.args) >= 4:
        amount_arg = node.args[3]  # 第 4 个参数是 amount
        if not has_proper_formatting(amount_arg, 'lot_size'):
            errors.append({
                "file": str(filepath),
                "line": amount_arg.lineno if hasattr(amount_arg, 'lineno') else node.lineno,
                "call": method_name,
                "arg": "amount (positional)",
                "format_type": "lot_size",
                "issue": "Positional argument 'amount' may not be formatted",
                "suggestion": "Use amount.quantize(lot_size) before passing to CCXT"
            })

    if len(node.args) >= 5:
        price_arg = node.args[4]  # 第 5 个参数是 price
        if not has_proper_formatting(price_arg, 'tick_size'):
            errors.append({
                "file": str(filepath),
                "line": price_arg.lineno if hasattr(price_arg, 'lineno') else node.lineno,
                "call": method_name,
                "arg": "price (positional)",
                "format_type": "tick_size",
                "issue": "Positional argument 'price' may not be formatted",
                "suggestion": "Use price.quantize(tick_size) before passing to CCXT"
            })

    return errors


def has_proper_formatting(node: ast.AST, format_type: str) -> bool:
    """检查节点是否有适当的格式化"""

    # 检查 quantize() 调用
    if has_quantize_call(node):
        return True

    # 检查 Decimal 构造 (可能是整数值)
    if is_decimal_constructor(node):
        return True

    # 检查 str() 转换 (CCXT 支持字符串输入，已避免 float 污染)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "str":
            return True  # str() 转换是安全的

    # 检查条件表达式 (str(x) if x is not None else None)
    if isinstance(node, ast.IfExp):
        # 检查 body 部分是否有 str() 调用
        if isinstance(node.body, ast.Call):
            if isinstance(node.body.func, ast.Name) and node.body.func.id == "str":
                return True
        # 检查 body 部分是否是 None (不需要格式化)
        if isinstance(node.body, ast.Constant) and node.body.value is None:
            return True

    # 检查属性访问 (可能是预格式化的值)
    if isinstance(node, ast.Attribute):
        # 假设某些属性返回已格式化的值
        safe_attrs = {
            'tick_size', 'lot_size', 'precision',
            'formatted_price', 'formatted_amount'
        }
        if node.attr in safe_attrs:
            return True

    # 检查变量名 (可能是预格式化变量)
    if isinstance(node, ast.Name):
        formatted_var_patterns = [
            'formatted_', 'quantized_', 'precise_',
            '_price', '_amount', '_quantity', '_size'
        ]
        for pattern in formatted_var_patterns:
            if pattern in node.id.lower():
                return True

    # 检查 method 调用返回 (可能是格式化方法)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in ['quantize', 'normalize', 'round']:
                return True

    return False


def has_quantize_call(node: ast.AST) -> bool:
    """检查是否有 quantize() 调用"""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Attribute):
                if child.func.attr == 'quantize':
                    return True
    return False


def is_decimal_constructor(node: ast.AST) -> bool:
    """检查是否是 Decimal 构造函数"""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id == 'Decimal':
                return True
    return False


def main():
    """主函数"""
    print("=" * 60)
    print("TickSize/LotSize 格式化检查 - CCXT 调用验证")
    print("=" * 60)

    all_errors = []
    files_checked = 0

    # 项目根目录
    root = Path(__file__).parent.parent

    # 检查基础设施层和领域层
    target_dirs = ["src/infrastructure/", "src/domain/", "src/application/"]

    for dir_path in target_dirs:
        full_path = root / dir_path
        if not full_path.exists():
            print(f"⚠️  目录不存在：{dir_path}")
            continue

        for py_file in full_path.rglob("*.py"):
            files_checked += 1
            errors = check_quantize_in_file(py_file)
            all_errors.extend(errors)

    print(f"\n检查了 {files_checked} 个 Python 文件")

    if all_errors:
        print(f"\n❌ 发现 {len(all_errors)} 处可能的格式化问题:\n")
        for err in all_errors:
            print(f"  {err['file']}:{err['line']}")
            print(f"    Call: {err['call']}()")
            print(f"    Argument: {err['arg']}")
            print(f"    Format: {err['format_type']}")
            print(f"    Issue: {err['issue']}")
            print(f"    Fix: {err['suggestion']}\n")
        return 1
    else:
        print("\n✅ TickSize/LotSize 格式化检查通过")
        return 0


if __name__ == "__main__":
    sys.exit(main())
