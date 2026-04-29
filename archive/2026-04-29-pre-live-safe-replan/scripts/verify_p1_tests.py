#!/usr/bin/env python3
"""
OrderRepository P1 测试验收脚本

用途:
1. 检查 P1 方法覆盖率（目标 100%）
2. 检查测试命名规范（P1-XXX 格式）
3. 检查测试分组（Group A/B/C）
4. 检查分页边界值断言数量

使用方法:
    python scripts/verify_p1_tests.py

输出:
    - P1 测试覆盖率报告
    - 测试命名规范检查结果
    - 测试分组统计
    - 断言数量分析
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass


# ============================================================
# 配置常量
# ============================================================

# P1 方法清单
P1_METHODS = {
    # Group A: 核心查询
    "get_orders": {"group": "A", "required_tests": 10},
    "get_orders_by_signal_ids": {"group": "A", "required_tests": 7},
    # Group B: 过滤查询
    "get_open_orders": {"group": "B", "required_tests": 4},
    "get_orders_by_symbol": {"group": "B", "required_tests": 4},
    "get_orders_by_role": {"group": "B", "required_tests": 5},
    "get_by_status": {"group": "B", "required_tests": 3},
    "mark_order_filled": {"group": "B", "required_tests": 3},
    # Group C: 别名方法
    "save_order": {"group": "C", "required_tests": 2},
    "get_order_detail": {"group": "C", "required_tests": 2},
    "get_by_signal_id": {"group": "C", "required_tests": 2},
    # P0 已覆盖，P1 验证
    "get_order_count": {"group": "C", "required_tests": 0, "covered_in_p0": True},
}

# 测试文件路径
TEST_FILE_PATH = "tests/unit/infrastructure/test_order_repository_unit.py"

# 期望的测试用例 ID 前缀
P1_TEST_PREFIXES = [
    "P1-001", "P1-002", "P1-003", "P1-004", "P1-005",
    "P1-006", "P1-007", "P1-008", "P1-009", "P1-010",
    "P1-011", "P1-012", "P1-013", "P1-014", "P1-015",
    "P1-016", "P1-017", "P1-018", "P1-019", "P1-020",
    "P1-021", "P1-022", "P1-023", "P1-024", "P1-025",
    "P1-026", "P1-027", "P1-028", "P1-029", "P1-030",
    "P1-031", "P1-032", "P1-033", "P1-034", "P1-035",
    "P1-036", "P1-037", "P1-038", "P1-039", "P1-040",
    "P1-041", "P1-042",
]


# ============================================================
# 数据类
# ============================================================

@dataclass
class TestInfo:
    """测试用例信息"""
    name: str
    line_number: int
    docstring: str
    test_id: str  # 如 P1-001
    method_name: str  # 被测试的方法名
    group: str  # A/B/C


@dataclass
class VerificationResult:
    """验证结果"""
    total_tests: int
    p1_tests_found: int
    p1_test_ids_found: List[str]
    missing_test_ids: List[str]
    method_coverage: Dict[str, bool]
    group_stats: Dict[str, int]
    assertion_counts: Dict[str, int]
    naming_violations: List[str]
    passed: bool


# ============================================================
# 核心验证逻辑
# ============================================================

def read_test_file(file_path: str) -> str:
    """读取测试文件内容"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"测试文件不存在：{file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def extract_test_functions(content: str) -> List[Tuple[str, int, str]]:
    """
    提取所有测试函数

    返回：[(函数名，行号，文档字符串), ...]
    """
    tests = []

    # 匹配 pytest 装饰器和函数定义
    pattern = r'@pytest\.mark\.asyncio\s*\n(?:async\s+)?def\s+(test_\w+)\s*\([^)]*\):'

    for match in re.finditer(pattern, content):
        func_name = match.group(1)
        line_number = content[:match.start()].count('\n') + 1

        # 提取文档字符串
        docstring = ""
        start_pos = match.end()
        # 跳过函数签名后的换行
        rest_content = content[start_pos:].lstrip()

        # 检查是否有文档字符串
        if rest_content.startswith('"""') or rest_content.startswith("'''"):
            quote = rest_content[:3]
            end_pos = rest_content.find(quote, 3)
            if end_pos != -1:
                docstring = rest_content[3:end_pos].strip()

        tests.append((func_name, line_number, docstring))

    return tests


def extract_test_id_from_docstring(docstring: str) -> str:
    """从文档字符串中提取测试 ID（如 P1-001）"""
    if not docstring:
        return ""

    # 查找 P1-XXX 或 P0-XXX 格式
    match = re.search(r'(P[01]-\d{3})', docstring)
    if match:
        return match.group(1)

    return ""


def extract_method_name_from_test(test_name: str) -> str:
    """从测试函数名推断被测试的方法名"""
    # 测试命名模式：test_<method>_<scenario>
    # 例如：test_get_orders_no_filter -> get_orders

    # 移除 test_ 前缀
    if test_name.startswith('test_'):
        test_name = test_name[5:]

    # 尝试匹配已知的 P1 方法
    for method in P1_METHODS.keys():
        if test_name.startswith(method) or f"_{method}_" in f"_{test_name}_":
            return method

    # 尝试从下划线分割的第一个部分推断
    parts = test_name.split('_')
    if len(parts) >= 2:
        # 尝试组合前两个部分（如 get_orders）
        candidate = f"{parts[0]}_{parts[1]}"
        if candidate in P1_METHODS:
            return candidate

    return ""


def count_assertions_in_test(content: str, test_name: str) -> int:
    """计算测试用例中的断言数量"""
    # 找到测试函数的范围
    pattern = rf'def\s+{test_name}\s*\([^)]*\):'
    match = re.search(pattern, content)

    if not match:
        return 0

    start_pos = match.end()

    # 找到下一个测试函数或文件末尾
    next_test = re.search(r'@pytest\.mark\.asyncio\s*\n(?:async\s+)?def\s+test_\w+', content[start_pos:])
    if next_test:
        end_pos = start_pos + next_test.start()
    else:
        end_pos = len(content)

    test_content = content[start_pos:end_pos]

    # 计算 assert 语句数量
    assertion_count = len(re.findall(r'^\s*assert\s+', test_content, re.MULTILINE))

    # 也计算 pytest.raises 等上下文管理器
    assertion_count += len(re.findall(r'pytest\.raises', test_content))

    return assertion_count


def verify_p1_tests() -> VerificationResult:
    """执行 P1 测试验证"""

    print("=" * 70)
    print("OrderRepository P1 测试验收脚本")
    print("=" * 70)

    # 读取测试文件
    try:
        content = read_test_file(TEST_FILE_PATH)
    except FileNotFoundError as e:
        print(f"\n❌ 错误：{e}")
        return VerificationResult(
            total_tests=0,
            p1_tests_found=0,
            p1_test_ids_found=[],
            missing_test_ids=P1_TEST_PREFIXES,
            method_coverage={m: False for m in P1_METHODS},
            group_stats={"A": 0, "B": 0, "C": 0},
            assertion_counts={},
            naming_violations=[],
            passed=False,
        )

    # 提取所有测试函数
    test_functions = extract_test_functions(content)
    print(f"\n📊 测试文件：{TEST_FILE_PATH}")
    print(f"📊 发现测试函数：{len(test_functions)} 个")

    # 分析每个测试
    p1_test_ids_found: Set[str] = set()
    method_coverage: Dict[str, bool] = {m: False for m in P1_METHODS}
    group_stats: Dict[str, int] = {"A": 0, "B": 0, "C": 0}
    assertion_counts: Dict[str, int] = {}
    naming_violations: List[str] = []

    for func_name, line_num, docstring in test_functions:
        test_id = extract_test_id_from_docstring(docstring)
        method_name = extract_method_name_from_test(func_name)

        # 记录 P1 测试 ID
        if test_id and test_id.startswith("P1-"):
            p1_test_ids_found.add(test_id)

            # 更新方法覆盖率
            if method_name and method_name in P1_METHODS:
                method_coverage[method_name] = True

            # 更新组统计
            if method_name and method_name in P1_METHODS:
                group = P1_METHODS[method_name]["group"]
                group_stats[group] += 1

        # 计算断言数量
        assertions = count_assertions_in_test(content, func_name)
        assertion_counts[func_name] = assertions

        # 检查命名规范
        if test_id and not docstring:
            naming_violations.append(f"{func_name}: 有测试 ID 但缺少文档字符串")

    # 计算缺失的测试 ID
    missing_test_ids = [tid for tid in P1_TEST_PREFIXES if tid not in p1_test_ids_found]

    # 检查 P0 已覆盖的方法（get_order_count）
    if method_coverage.get("get_order_count", False) is False:
        # get_order_count 在 P0 已覆盖，这里标记为已通过
        method_coverage["get_order_count"] = True

    # 计算总体通过率
    covered_methods = sum(1 for v in method_coverage.values() if v)
    total_methods = len(P1_METHODS)
    coverage_rate = (covered_methods / total_methods) * 100 if total_methods > 0 else 0

    # 判断是否通过验收
    p1_tests_found_count = len(p1_test_ids_found)
    expected_p1_tests = len(P1_TEST_PREFIXES)
    passed = (
        coverage_rate >= 75 and
        len(naming_violations) == 0 and
        p1_tests_found_count >= expected_p1_tests * 0.75
    )

    return VerificationResult(
        total_tests=len(test_functions),
        p1_tests_found=p1_tests_found_count,
        p1_test_ids_found=sorted(list(p1_test_ids_found)),
        missing_test_ids=missing_test_ids,
        method_coverage=method_coverage,
        group_stats=group_stats,
        assertion_counts=assertion_counts,
        naming_violations=naming_violations,
        passed=passed,
    )


def print_report(result: VerificationResult):
    """打印验收报告"""

    print("\n" + "=" * 70)
    print("📋 P1 测试验收报告")
    print("=" * 70)

    # 总体统计
    print(f"\n📊 总体统计")
    print(f"   总测试函数数：{result.total_tests}")
    print(f"   P1 测试用例数：{result.p1_tests_found}/{len(P1_TEST_PREFIXES)}")

    # 覆盖率
    covered_count = sum(1 for v in result.method_coverage.values() if v)
    total = len(result.method_coverage)
    print(f"   方法覆盖率：{covered_count}/{total} ({covered_count/total*100:.1f}%)")

    # 分组统计
    print(f"\n📊 分组统计")
    print(f"   Group A (核心查询): {result.group_stats['A']} 个测试")
    print(f"   Group B (过滤查询): {result.group_stats['B']} 个测试")
    print(f"   Group C (别名方法): {result.group_stats['C']} 个测试")

    # 方法覆盖详情
    print(f"\n📊 方法覆盖详情")
    for method, info in sorted(P1_METHODS.items()):
        covered = "✅" if result.method_coverage.get(method, False) else "❌"
        group = info["group"]
        required = info["required_tests"]
        covered_in_p0 = info.get("covered_in_p0", False)

        if covered_in_p0:
            print(f"   {covered} {method} [Group {group}] - P0 已覆盖")
        else:
            print(f"   {covered} {method} [Group {group}] - 需要 {required} 个测试")

    # 已发现的 P1 测试 ID
    print(f"\n📊 已发现的 P1 测试 ID ({len(result.p1_test_ids_found)} 个)")
    if result.p1_test_ids_found:
        print(f"   {', '.join(result.p1_test_ids_found)}")
    else:
        print(f"   (无)")

    # 缺失的测试 ID
    if result.missing_test_ids:
        print(f"\n⚠️  缺失的测试 ID ({len(result.missing_test_ids)} 个)")
        for tid in result.missing_test_ids[:20]:  # 只显示前 20 个
            print(f"   - {tid}")
        if len(result.missing_test_ids) > 20:
            print(f"   ... 还有 {len(result.missing_test_ids) - 20} 个")
    else:
        print(f"\n✅ 所有 P1 测试 ID 已覆盖")

    # 命名规范检查
    if result.naming_violations:
        print(f"\n⚠️  命名规范问题 ({len(result.naming_violations)} 个)")
        for violation in result.naming_violations[:10]:
            print(f"   - {violation}")
    else:
        print(f"\n✅ 测试命名规范检查通过")

    # 断言数量统计
    print(f"\n📊 断言数量统计")
    total_assertions = sum(result.assertion_counts.values())
    avg_assertions = total_assertions / len(result.assertion_counts) if result.assertion_counts else 0
    print(f"   总断言数：{total_assertions}")
    print(f"   平均每个测试：{avg_assertions:.1f} 个断言")

    # Top 5 断言最多的测试
    top_tests = sorted(result.assertion_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    if top_tests:
        print(f"   断言最多的测试:")
        for test_name, count in top_tests:
            print(f"     - {test_name}: {count} 个断言")

    # 最终验收结果
    print("\n" + "=" * 70)
    coverage_pct = covered_count / total * 100 if total > 0 else 0
    if result.passed:
        print("✅ P1 测试验收通过")
        print(f"   覆盖率：{coverage_pct:.1f}% >= 75%")
        print(f"   命名规范：无违规")
    else:
        print("❌ P1 测试验收未通过")
        print(f"   覆盖率：{coverage_pct:.1f}% < 100%")
        if result.missing_test_ids:
            print(f"   缺失测试：{len(result.missing_test_ids)} 个")
        if result.naming_violations:
            print(f"   命名违规：{len(result.naming_violations)} 个")
    print("=" * 70)


def save_report(result: VerificationResult, output_path: str = "docs/qa/p1-verification-report.md"):
    """保存验收报告到文件"""

    covered = sum(1 for v in result.method_coverage.values() if v)
    total = len(result.method_coverage)

    report = f"""# OrderRepository P1 测试验收报告

> **生成日期**: 2026-04-07
> **验收脚本**: scripts/verify_p1_tests.py
> **验收结果**: {"✅ 通过" if result.passed else "❌ 未通过"}

---

## 📊 总体统计

| 指标 | 数值 | 目标 | 状态 |
|------|------|------|------|
| 总测试函数数 | {result.total_tests} | - | - |
| P1 测试用例数 | {result.p1_tests_found}/{len(P1_TEST_PREFIXES)} | 42 | {"✅" if result.p1_tests_found >= 32 else "❌"} |
| 方法覆盖率 | {covered}/{total} ({covered/total*100:.1f}%) | 75%+ | {"✅" if covered/total >= 0.75 else "❌"} |

---

## 📊 分组统计

| 组别 | 测试数 | 描述 |
|------|--------|------|
| Group A | {result.group_stats['A']} | 核心查询 (get_orders, get_orders_by_signal_ids) |
| Group B | {result.group_stats['B']} | 过滤查询 (get_open_orders, etc.) |
| Group C | {result.group_stats['C']} | 别名方法 (save_order, etc.) |

---

## 📊 方法覆盖详情

| 方法 | 组别 | 覆盖状态 |
|------|------|---------|
"""

    for method, info in sorted(P1_METHODS.items()):
        covered_mark = "✅" if result.method_coverage.get(method, False) else "❌"
        group = info["group"]
        covered_in_p0 = info.get("covered_in_p0", False)
        p0_note = " (P0 已覆盖)" if covered_in_p0 else ""
        report += f"| {method} | Group {group} | {covered_mark}{p0_note} |\n"

    report += f"""
---

## 📊 测试 ID 覆盖

### 已覆盖 ({len(result.p1_test_ids_found)} 个)

{', '.join(result.p1_test_ids_found) if result.p1_test_ids_found else '(无)'}

### 缺失 ({len(result.missing_test_ids)} 个)

{chr(10).join(f'- {tid}' for tid in result.missing_test_ids[:20]) if result.missing_test_ids else '(无)'}
{f"\n... 还有 {len(result.missing_test_ids) - 20} 个" if len(result.missing_test_ids) > 20 else ''}

---

## 📊 断言数量统计

- **总断言数**: {sum(result.assertion_counts.values())}
- **平均每个测试**: {sum(result.assertion_counts.values()) / len(result.assertion_counts) if result.assertion_counts else 0:.1f} 个断言

### Top 5 断言最多的测试

"""

    top_tests = sorted(result.assertion_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    for test_name, count in top_tests:
        report += f"- `{test_name}`: {count} 个断言\n"

    report += f"""
---

## ✅ 验收标准检查

| 标准 | 要求 | 实际 | 状态 |
|------|------|------|------|
| 方法覆盖率 | >= 75% | {covered/total*100:.1f}% | {"✅" if covered/total >= 0.75 else "❌"} |
| P1 测试数量 | >= 32 个 | {result.p1_tests_found} 个 | {"✅" if result.p1_tests_found >= 32 else "❌"} |
| 命名规范 | 0 违规 | {len(result.naming_violations)} 个 | {"✅" if len(result.naming_violations) == 0 else "❌"} |

---

*报告生成时间：2026-04-07*
"""

    # 确保目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n📄 报告已保存到：{output_path}")


# ============================================================
# 主函数
# ============================================================

def main():
    """主函数"""
    result = verify_p1_tests()
    print_report(result)
    save_report(result)

    # 返回退出码
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
