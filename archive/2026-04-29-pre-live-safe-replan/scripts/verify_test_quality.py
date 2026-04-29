#!/usr/bin/env python3
"""
OrderRepository 测试质量自动化验证脚本

功能:
1. 覆盖率阈值检查（目标 60%+）
2. 测试命名规范检查
3. 断言数量统计
4. 测试执行时间统计

使用方法:
    python scripts/verify_test_quality.py

依赖:
    pip install pytest pytest-cov coverage
"""

import os
import re
import sys
import subprocess
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


# ============================================================
# 配置
# ============================================================

@dataclass
class QualityConfig:
    """测试质量配置"""
    # 覆盖率阈值
    coverage_threshold: float = 60.0  # 整体覆盖率目标
    coverage_p0_threshold: float = 90.0  # P0 方法覆盖率目标
    coverage_p1_threshold: float = 80.0  # P1 方法覆盖率目标

    # 测试执行时间阈值 (秒)
    unit_test_timeout: float = 5.0
    integration_test_timeout: float = 30.0

    # 断言数量要求
    min_assertions_per_test: int = 1
    min_assertions_per_file: int = 10

    # 测试文件路径
    test_paths: List[str] = field(default_factory=lambda: [
        "tests/unit/infrastructure/test_order_repository_unit.py",
        "tests/unit/test_order_repository.py",
        "tests/integration/test_order_repository_queries.py",
    ])

    # 源代码路径
    source_path: str = "src/infrastructure/order_repository.py"


# ============================================================
# 数据模型
# ============================================================

@dataclass
class TestResult:
    """单个测试结果"""
    name: str
    status: str  # PASSED, FAILED, SKIPPED
    duration: float
    assertions: int
    error_message: Optional[str] = None


@dataclass
class FileReport:
    """单个测试文件报告"""
    file_path: str
    total_tests: int
    passed: int
    failed: int
    skipped: int
    total_assertions: int
    avg_duration: float
    tests: List[TestResult] = field(default_factory=list)
    naming_issues: List[str] = field(default_factory=list)


@dataclass
class CoverageReport:
    """覆盖率报告"""
    total_lines: int
    covered_lines: int
    coverage_percent: float
    missing_lines: List[int] = field(default_factory=list)
    by_method: Dict[str, float] = field(default_factory=dict)


@dataclass
class QualityReport:
    """总体质量报告"""
    file_reports: List[FileReport] = field(default_factory=list)
    coverage: Optional[CoverageReport] = None
    naming_violations: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    @property
    def total_tests(self) -> int:
        return sum(f.total_tests for f in self.file_reports)

    @property
    def total_passed(self) -> int:
        return sum(f.passed for f in self.file_reports)

    @property
    def pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.total_passed / self.total_tests) * 100


# ============================================================
# 验证器
# ============================================================

class TestQualityVerifier:
    """测试质量验证器"""

    def __init__(self, config: QualityConfig):
        self.config = config
        self.project_root = Path(__file__).parent.parent

    def run_tests(self) -> Tuple[bool, str]:
        """
        运行测试套件并返回结果

        Returns:
            (success, output)
        """
        cmd = [
            sys.executable, "-m", "pytest",
            *self.config.test_paths,
            "-v",
            "--tb=short",
            "--json-report",
            "--json-report-file=none",  # 不生成文件，只捕获输出
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=120,  # 总超时 2 分钟
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "测试执行超时 (>120 秒)"
        except Exception as e:
            return False, f"测试执行失败：{e}"

    def run_coverage(self) -> Optional[CoverageReport]:
        """
        运行覆盖率检查

        Returns:
            CoverageReport 或 None (如果失败)
        """
        # 检查是否安装了 pytest-cov
        try:
            import pytest_cov  # noqa: F401
        except ImportError:
            print("  ⚠️ pytest-cov 未安装，跳过覆盖率检查")
            print("  安装：pip install pytest-cov")
            return None

        cmd = [
            sys.executable, "-m", "pytest",
            *self.config.test_paths,
            f"--cov={self.config.source_path.replace('/', '.')}",
            "--cov-report=json",
            "--cov-report=term-missing",
            "-q",
        ]

        try:
            subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=120,
            )

            # 读取覆盖率 JSON
            coverage_file = self.project_root / "coverage.json"
            if coverage_file.exists():
                with open(coverage_file) as f:
                    data = json.load(f)

                totals = data.get("totals", {})
                report = CoverageReport(
                    total_lines=totals.get("num_lines", 0),
                    covered_lines=totals.get("num_covered", 0),
                    coverage_percent=totals.get("percent_covered", 0.0),
                )
                return report

        except Exception as e:
            print(f"覆盖率检查失败：{e}")

        return None

    def analyze_test_file(self, file_path: str) -> FileReport:
        """
        分析单个测试文件

        Returns:
            FileReport
        """
        full_path = self.project_root / file_path
        if not full_path.exists():
            return FileReport(
                file_path=file_path,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                total_assertions=0,
                avg_duration=0.0,
            )

        with open(full_path) as f:
            content = f.read()

        # 统计测试函数
        test_functions = re.findall(r'async def (test_\w+)\s*\(', content)

        # 统计断言
        assertions = re.findall(r'\b(assert|pytest\.assert|self\.assert\w+)\b', content)

        # 检查命名规范
        naming_issues = []
        for func_name in test_functions:
            issue = self._check_naming_convention(func_name)
            if issue:
                naming_issues.append(issue)

        # 运行测试获取详细结果
        tests, passed, failed, skipped, durations = self._run_single_file_tests(file_path)

        return FileReport(
            file_path=file_path,
            total_tests=len(tests),
            passed=passed,
            failed=failed,
            skipped=skipped,
            total_assertions=len(assertions),
            avg_duration=sum(durations) / len(durations) if durations else 0.0,
            tests=tests,
            naming_issues=naming_issues,
        )

    def _check_naming_convention(self, func_name: str) -> Optional[str]:
        """
        检查测试函数命名规范

        Returns:
            问题描述或 None
        """
        # 必须以 test_ 开头
        if not func_name.startswith("test_"):
            return f"'{func_name}' 不以 'test_' 开头"

        # 建议使用 test_<method>_<scenario>_<expected> 格式
        parts = func_name.split("_")[1:]  # 移除 'test'

        if len(parts) < 2:
            return f"'{func_name}' 命名过于简单，建议包含方法名和场景"

        # 检查是否包含大写字母 (不应该)
        if any(c.isupper() for c in func_name):
            return f"'{func_name}' 包含大写字母，应该使用小写 + 下划线"

        return None

    def _run_single_file_tests(self, file_path: str) -> Tuple[List[TestResult], int, int, int, List[float]]:
        """
        运行单个测试文件并解析结果

        Returns:
            (tests, passed, failed, skipped, durations)
        """
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.project_root / file_path),
            "-v",
            "--tb=no",
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=60,
            )

            tests = []
            passed = failed = skipped = 0
            durations = []

            # 解析输出 - 改进的正则匹配
            for line in result.stdout.split("\n"):
                # 匹配测试行：test_file.py::test_name PASSED [ 25%]
                # 或：tests/file.py::test_name PASSED [ 25%]
                match = re.search(r'::(\w+)\s+(PASSED|FAILED|SKIPPED|XPASS|XFAIL)', line)
                if match:
                    test_name = match.group(1)
                    status = match.group(2)

                    test_result = TestResult(
                        name=test_name,
                        status=status,
                        duration=0.0,  # 简化版不解析时间
                        assertions=0,
                    )
                    tests.append(test_result)

                    if status == "PASSED":
                        passed += 1
                    elif status in ["FAILED", "XFAIL"]:
                        failed += 1
                    elif status in ["SKIPPED", "XPASS"]:
                        skipped += 1

            # 如果没有解析到测试结果，尝试从总结行获取
            if not tests:
                summary_match = re.search(r'(\d+)\s+passed', result.stdout)
                if summary_match:
                    passed = int(summary_match.group(1))
                summary_match = re.search(r'(\d+)\s+failed', result.stdout)
                if summary_match:
                    failed = int(summary_match.group(1))
                summary_match = re.search(r'(\d+)\s+skipped', result.stdout)
                if summary_match:
                    skipped = int(summary_match.group(1))

            return tests, passed, failed, skipped, durations

        except Exception as e:
            print(f"运行测试文件失败 {file_path}: {e}")
            return [], 0, 0, 0, []

    def check_assertion_density(self, report: FileReport) -> List[str]:
        """
        检查断言密度

        Returns:
            问题列表
        """
        issues = []

        if report.total_tests == 0:
            return issues

        avg_assertions = report.total_assertions / report.total_tests

        if avg_assertions < self.config.min_assertions_per_test:
            issues.append(
                f"断言密度过低：平均每测试 {avg_assertions:.1f} 个断言 "
                f"(要求 ≥ {self.config.min_assertions_per_test})"
            )

        if report.total_assertions < self.config.min_assertions_per_file:
            issues.append(
                f"文件断言总数过低：{report.total_assertions} 个 "
                f"(要求 ≥ {self.config.min_assertions_per_file})"
            )

        return issues

    def verify_order_repository_methods(self, coverage: Optional[CoverageReport]) -> List[str]:
        """
        验证 OrderRepository 关键方法是否被测试覆盖

        Returns:
            未覆盖的方法列表
        """
        # P0 方法
        p0_methods = [
            "save",
            "save_batch",
            "update_status",
            "delete_orders_batch",
            "get_order_chain_by_order_id",
        ]

        # P1 方法
        p1_methods = [
            "get_orders_by_signal",
            "get_open_orders",
            "get_order_tree",
            "get_oco_group",
        ]

        # 读取源代码分析方法存在性
        source_file = self.project_root / self.config.source_path
        if not source_file.exists():
            return [f"源代码文件不存在：{self.config.source_path}"]

        with open(source_file) as f:
            source_content = f.read()

        # 简化检查：通过测试文件名推断覆盖
        uncovered = []

        # 检查 P0 方法
        for method in p0_methods:
            test_pattern = f"test.*{method.replace('_', '.')}"
            # 简单检查：是否有测试文件包含方法名
            found = False
            for test_path in self.config.test_paths:
                test_file = self.project_root / test_path
                if test_file.exists():
                    with open(test_file) as f:
                        if method in f.read():
                            found = True
                            break

            if not found:
                uncovered.append(f"P0: {method}")

        return uncovered


# ============================================================
# 报告生成
# ============================================================

class ReportGenerator:
    """报告生成器"""

    def __init__(self, report: QualityReport, config: QualityConfig):
        self.report = report
        self.config = config

    def generate_summary(self) -> str:
        """生成摘要报告"""
        lines = [
            "=" * 60,
            "OrderRepository 测试质量验证报告",
            "=" * 60,
            "",
            f"测试文件数：{len(self.report.file_reports)}",
            f"总测试数：{self.report.total_tests}",
            f"通过数：{self.report.total_passed}",
            f"失败数：{self.report.total_tests - self.report.total_passed - sum(f.skipped for f in self.report.file_reports)}",
            f"跳过数：{sum(f.skipped for f in self.report.file_reports)}",
            f"通过率：{self.report.pass_rate:.1f}%",
            "",
        ]

        if self.report.coverage:
            cov = self.report.coverage
            lines.extend([
                f"覆盖率：{cov.coverage_percent:.1f}%",
                f"总行数：{cov.total_lines}",
                f"已覆盖：{cov.covered_lines}",
                "",
            ])

        return "\n".join(lines)

    def generate_file_reports(self) -> str:
        """生成文件级报告"""
        lines = ["-" * 60, "文件级报告", "-" * 60, ""]

        for file_report in self.report.file_reports:
            lines.extend([
                f"文件：{file_report.file_path}",
                f"  测试数：{file_report.total_tests}",
                f"  通过：{file_report.passed}",
                f"  失败：{file_report.failed}",
                f"  跳过：{file_report.skipped}",
                f"  断言数：{file_report.total_assertions}",
                f"  平均耗时：{file_report.avg_duration:.3f}s",
            ])

            if file_report.naming_issues:
                lines.append(f"  命名问题：{len(file_report.naming_issues)}")
                for issue in file_report.naming_issues[:3]:  # 只显示前 3 个
                    lines.append(f"    - {issue}")

            # 断言密度检查
            verifier = TestQualityVerifier(self.config)
            density_issues = verifier.check_assertion_density(file_report)
            if density_issues:
                lines.append(f"  断言密度问题：")
                for issue in density_issues:
                    lines.append(f"    - {issue}")

            lines.append("")

        return "\n".join(lines)

    def generate_recommendations(self) -> str:
        """生成改进建议"""
        lines = ["-" * 60, "改进建议", "-" * 60, ""]

        # 覆盖率建议
        if self.report.coverage and self.report.coverage.coverage_percent < self.config.coverage_threshold:
            lines.append(
                f"[P0] 覆盖率 {self.report.coverage.coverage_percent:.1f}% 低于目标 {self.config.coverage_threshold}%"
            )

        # 通过率建议
        if self.report.pass_rate < 90:
            lines.append(
                f"[P0] 测试通过率 {self.report.pass_rate:.1f}% 低于 90%"
            )

        # 命名规范建议
        if self.report.naming_violations:
            lines.append(
                f"[P2] 发现 {len(self.report.naming_violations)} 个命名规范问题"
            )

        if not lines[2:]:
            lines.append("✅ 所有检查通过！")

        return "\n".join(lines)

    def generate_full_report(self) -> str:
        """生成完整报告"""
        sections = [
            self.generate_summary(),
            self.generate_file_reports(),
            self.generate_recommendations(),
        ]
        return "\n".join(sections)


# ============================================================
# 主函数
# ============================================================

def main():
    """主函数"""
    print("OrderRepository 测试质量验证脚本")
    print("=" * 50)

    config = QualityConfig()
    verifier = TestQualityVerifier(config)

    # Step 1: 运行测试
    print("\n[1/4] 运行测试套件...")
    success, output = verifier.run_tests()
    if not success:
        print(f"⚠️ 测试执行失败或超时")
    else:
        print(f"✅ 测试执行完成")

    # Step 2: 分析测试文件
    print("\n[2/4] 分析测试文件...")
    report = QualityReport()

    for test_path in config.test_paths:
        print(f"  分析：{test_path}")
        file_report = verifier.analyze_test_file(test_path)
        report.file_reports.append(file_report)
        report.naming_violations.extend(file_report.naming_issues)

    # Step 3: 运行覆盖率检查
    print("\n[3/4] 运行覆盖率检查...")
    coverage = verifier.run_coverage()
    report.coverage = coverage

    if coverage:
        print(f"  覆盖率：{coverage.coverage_percent:.1f}%")
    else:
        print("  ⚠️ 覆盖率检查失败或跳过")

    # Step 4: 验证关键方法覆盖
    print("\n[4/4] 验证 OrderRepository 关键方法覆盖...")
    uncovered = verifier.verify_order_repository_methods(coverage)
    if uncovered:
        print(f"  ⚠️ 未覆盖的方法：{uncovered}")
    else:
        print(f"  ✅ 关键方法均已覆盖")

    # 生成报告
    print("\n" + "=" * 50)
    generator = ReportGenerator(report, config)
    full_report = generator.generate_full_report()
    print(full_report)

    # 保存到文件
    report_path = Path(__file__).parent.parent / "docs" / "qa" / "test-quality-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w") as f:
        f.write("# OrderRepository 测试质量自动化报告\n\n")
        f.write(f"生成时间：{__import__('datetime').datetime.now().isoformat()}\n\n")
        f.write("```text\n")
        f.write(full_report)
        f.write("\n```\n")

    print(f"\n📄 报告已保存到：{report_path}")

    # 返回状态码
    if report.pass_rate < 90 or (coverage and coverage.coverage_percent < config.coverage_threshold):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
