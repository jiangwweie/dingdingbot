#!/usr/bin/env python3
"""
生成项目进度报告

包括:
- 燃尽图数据
- 任务完成趋势
- 阻塞事项统计
- 阶段流转记录
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import re


def parse_task_plan(filepath: Path) -> dict:
    """解析 task_plan.md 文件"""
    if not filepath.exists():
        return {'tasks': [], 'phases': {}}

    content = filepath.read_text(encoding='utf-8')

    tasks = []
    current_phase = None
    phases = defaultdict(list)

    # 解析任务表格
    task_pattern = r'\|\s*(\w+)\s*\|\s*([^|]+)\s*\|\s*(P\d+)\s*\|\s*([\d.]+)h?\s*\|\s*([✅☐⏳]+)\s*\|'

    for line in content.splitlines():
        match = re.search(task_pattern, line)
        if match:
            task_id, task_name, priority, hours, status = match.groups()
            tasks.append({
                'id': task_id.strip(),
                'name': task_name.strip(),
                'priority': priority.strip(),
                'hours': float(hours.strip()),
                'status': status.strip(),
            })

            if current_phase:
                phases[current_phase].append(tasks[-1])

        # 检测阶段标题
        phase_match = re.search(r'###?\s*(阶段[\d零一二三四五六七八九十]+|Phase\s*\d+):?\s*(.+)', line)
        if phase_match:
            current_phase = phase_match.group(2).strip()

    return {'tasks': tasks, 'phases': dict(phases)}


def parse_progress_log(filepath: Path) -> list[dict]:
    """解析 progress.md 文件"""
    if not filepath.exists():
        return []

    content = filepath.read_text(encoding='utf-8')
    entries = []

    # 解析日期标题
    date_pattern = r'##\s*(\d{4}-\d{2}-\d{2})\s*[-:]\s*(.+)'
    current_date = None
    current_status = None

    for line in content.splitlines():
        date_match = re.match(date_pattern, line)
        if date_match:
            current_date = date_match.group(1)
            current_status = date_match.group(2).strip()
            continue

        if current_date and line.strip():
            entries.append({
                'date': current_date,
                'status': current_status,
                'content': line.strip()[:200],
            })

    return entries


def generate_report(task_plan: dict, progress_log: list, handoff_dir: Path) -> str:
    """生成进度报告"""
    report = []
    report.append("# 项目进度报告")
    report.append(f"\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 任务统计
    tasks = task_plan.get('tasks', [])
    total = len(tasks)
    completed = sum(1 for t in tasks if '✅' in t['status'])
    in_progress = sum(1 for t in tasks if '⏳' in t['status'])
    pending = sum(1 for t in tasks if '☐' in t['status'])

    report.append("## 📊 任务统计\n")
    report.append(f"| 状态 | 数量 | 百分比 |")
    report.append(f"|------|------|--------|")
    report.append(f"| 已完成 | {completed} | {completed/total*100:.1f}% |" if total > 0 else "| 已完成 | 0 | 0% |")
    report.append(f"| 进行中 | {in_progress} | {in_progress/total*100:.1f}% |" if total > 0 else "| 进行中 | 0 | 0% |")
    report.append(f"| 待开始 | {pending} | {pending/total*100:.1f}% |" if total > 0 else "| 待开始 | 0 | 0% |")
    report.append(f"| **总计** | **{total}** | **100%** |")

    # 按优先级统计
    by_priority = defaultdict(lambda: {'total': 0, 'completed': 0})
    for task in tasks:
        by_priority[task['priority']]['total'] += 1
        if '✅' in task['status']:
            by_priority[task['priority']]['completed'] += 1

    report.append("\n## 🎯 按优先级\n")
    report.append("| 优先级 | 总计 | 已完成 | 完成率 |")
    report.append("|--------|------|--------|--------|")
    for priority in ['P0', 'P1', 'P2']:
        if priority in by_priority:
            data = by_priority[priority]
            rate = data['completed'] / data['total'] * 100 if data['total'] > 0 else 0
            report.append(f"| {priority} | {data['total']} | {data['completed']} | {rate:.1f}% |")

    # 阶段进度
    phases = task_plan.get('phases', {})
    if phases:
        report.append("\n## 📋 阶段进度\n")
        for phase, phase_tasks in phases.items():
            phase_completed = sum(1 for t in phase_tasks if '✅' in t['status'])
            phase_total = len(phase_tasks)
            rate = phase_completed / phase_total * 100 if phase_total > 0 else 0
            progress_bar = '█' * int(rate / 10) + '░' * (10 - int(rate / 10))
            report.append(f"- **{phase}**: `{progress_bar}` {rate:.0f}% ({phase_completed}/{phase_total})")

    # 最近进度
    if progress_log:
        report.append("\n## 📝 最近进度\n")
        report.append("| 日期 | 状态 | 内容 |")
        report.append("|------|------|------|")
        for entry in progress_log[:7]:
            content = entry['content'][:50] + '...' if len(entry['content']) > 50 else entry['content']
            report.append(f"| {entry['date']} | {entry['status']} | {content} |")

    # 预估完成时间
    if total > 0:
        completion_rate = completed / total
        if completion_rate > 0 and completion_rate < 1:
            report.append("\n## 🔮 预估完成时间\n")
            report.append(f"当前完成率：{completion_rate*100:.1f}%")
            report.append(f"按此速度，预计还需 {(1-completion_rate)/completion_rate:.1f} 倍已用时间")

    return '\n'.join(report)


def main():
    """主函数"""
    docs_dir = Path('docs/planning')
    if not docs_dir.exists():
        print("错误：docs/planning 目录不存在")
        sys.exit(1)

    # 解析文件
    task_plan = parse_task_plan(docs_dir / 'task_plan.md')
    progress_log = parse_progress_log(docs_dir / 'progress.md')

    # 生成报告
    report = generate_report(task_plan, progress_log, docs_dir)

    # 保存报告
    report_path = docs_dir / 'progress-report.md'
    report_path.write_text(report, encoding='utf-8')

    # 输出摘要
    tasks = task_plan.get('tasks', [])
    completed = sum(1 for t in tasks if '✅' in t['status'])
    total = len(tasks)

    print(f"\n生成进度报告:")
    print(f"任务总数：{total}")
    print(f"已完成：{completed} ({completed/total*100:.1f}%)")
    print(f"报告路径：{report_path}")


if __name__ == '__main__':
    main()
