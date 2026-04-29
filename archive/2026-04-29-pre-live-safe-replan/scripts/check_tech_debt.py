#!/usr/bin/env python3
"""
检查技术债

扫描代码中的 TODO/FIXME/HACK 等标记，生成技术债报告。
"""

import re
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# 跳过检查的目录
SKIP_DIRS = {'venv', '.venv', 'node_modules', '__pycache__', '.git', 'tests', 'build', 'dist'}

# 技术债标记
DEBT_PATTERNS = {
    'TODO': r'#\s*TODO[:\s]*(.*)',
    'FIXME': r'#\s*FIXME[:\s]*(.*)',
    'HACK': r'#\s*HACK[:\s]*(.*)',
    'XXX': r'#\s*XXX[:\s]*(.*)',
    'DEPRECATED': r'#\s*DEPRECATED[:\s]*(.*)',
    'OPTIMIZE': r'#\s*OPTIMIZE[:\s]*(.*)',
}

# 技术债优先级
PRIORITY_MAP = {
    'FIXME': 'P0',
    'XXX': 'P0',
    'HACK': 'P1',
    'TODO': 'P2',
    'OPTIMIZE': 'P2',
    'DEPRECATED': 'P1',
}


def scan_file(filepath: Path) -> list[dict]:
    """扫描单个文件的技术债"""
    debts = []

    try:
        lines = filepath.read_text(encoding='utf-8').splitlines()
    except Exception:
        return debts

    for line_num, line in enumerate(lines, 1):
        for marker, pattern in DEBT_PATTERNS.items():
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                debts.append({
                    'file': str(filepath),
                    'line': line_num,
                    'marker': marker,
                    'priority': PRIORITY_MAP.get(marker, 'P2'),
                    'description': match.group(1).strip() if match.group(1) else '',
                    'code': line.strip()[:100],
                })

    return debts


def generate_report(debts: list[dict]) -> str:
    """生成技术债报告"""
    report = []
    report.append("# 技术债扫描报告")
    report.append(f"\n**扫描时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 统计
    total = len(debts)
    by_priority = defaultdict(int)
    by_marker = defaultdict(int)
    by_file = defaultdict(int)

    for debt in debts:
        by_priority[debt['priority']] += 1
        by_marker[debt['marker']] += 1
        by_file[str(debt['file'].parent)] += 1

    # 摘要
    report.append("## 摘要\n")
    report.append(f"- **技术债总数**: {total}")
    report.append(f"- **P0 紧急**: {by_priority.get('P0', 0)}")
    report.append(f"- **P1 重要**: {by_priority.get('P1', 0)}")
    report.append(f"- **P2 一般**: {by_priority.get('P2', 0)}\n")

    # 按优先级排序
    report.append("## 技术债清单 (按优先级)\n")

    sorted_debts = sorted(debts, key=lambda x: (x['priority'], x['marker']))

    for debt in sorted_debts[:50]:  # 限制显示 50 条
        report.append(f"### [{debt['priority']}] {debt['marker']} - {debt['file']}:{debt['line']}\n")
        report.append(f"```python")
        report.append(f"{debt['code']}")
        report.append(f"```\n")
        if debt['description']:
            report.append(f"{debt['description']}\n")
        report.append("---\n")

    if len(sorted_debts) > 50:
        report.append(f"\n*还有 {len(sorted_debts) - 50} 条技术债未显示，请查看完整扫描*\n")

    # 分布
    report.append("\n## 分布统计\n")
    report.append("### 按目录")
    for dir, count in sorted(by_file.items(), key=lambda x: -x[1])[:10]:
        report.append(f"- `{dir}`: {count} 条")

    report.append("\n### 按类型")
    for marker, count in sorted(by_marker.items(), key=lambda x: -x[1]):
        report.append(f"- `{marker}`: {count} 条")

    return '\n'.join(report)


def main():
    """主函数"""
    src_dir = Path('src')
    if not src_dir.exists():
        print("错误：src 目录不存在")
        sys.exit(1)

    all_debts = []
    files_scanned = 0

    print("扫描技术债...")

    for filepath in src_dir.rglob('*.py'):
        if any(skip in str(filepath) for skip in SKIP_DIRS):
            continue

        files_scanned += 1
        debts = scan_file(filepath)
        all_debts.extend(debts)

    # 生成报告
    report = generate_report(all_debts)

    # 保存报告
    report_path = Path('docs/reports/tech-debt-report.md')
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(report, encoding='utf-8')

    # 输出摘要
    print(f"\n扫描了 {files_scanned} 个文件")
    print(f"发现 {len(all_debts)} 条技术债")

    p0_count = sum(1 for d in all_debts if d['priority'] == 'P0')
    p1_count = sum(1 for d in all_debts if d['priority'] == 'P1')

    if p0_count > 0:
        print(f"\n❌ P0 紧急技术债：{p0_count} 条")
    if p1_count > 0:
        print(f"⚠️ P1 重要技术债：{p1_count} 条")

    print(f"\n📄 完整报告：{report_path}")

    # 如果有 P0 技术债，返回错误
    if p0_count > 0:
        print("\n建议优先修复 P0 级技术债!")
        sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
