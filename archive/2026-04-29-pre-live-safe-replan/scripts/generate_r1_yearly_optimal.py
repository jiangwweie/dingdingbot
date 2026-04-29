#!/usr/bin/env python3
"""
R1 Baseline Capital Allocation Search - 每年独立最优配置

目标：
在 MaxDD <= 50% 约束下（每年独立判定），找到每年的最优配置。

约束：
- 2023 年：MaxDD_2023 <= 50%
- 2024 年：MaxDD_2024 <= 50%
- 2025 年：MaxDD_2025 <= 50%

成本：BNB9（fee_rate=0.000405, slippage=0.0001, tp_slippage=0）
"""
import json
from pathlib import Path
from datetime import datetime

# 读取 R1b 审计结果
r1b_path = Path("reports/research/r1b_capital_allocation_audit_v2_2026-04-29.json")
with open(r1b_path) as f:
    r1b_data = json.load(f)

# 提取所有配置的年度数据
configs_by_year = {
    '2023': [],
    '2024': [],
    '2025': [],
}

for result in r1b_data['audit_results']:
    exposure = result['exposure']
    risk_pct = result['risk_pct']
    yearly_pnl = result['yearly_pnl']
    yearly_max_dd = result['yearly_max_dd']

    # 提取每年的数据
    for year in ['2023', '2024', '2025']:
        if year in yearly_pnl and year in yearly_max_dd:
            configs_by_year[year].append({
                'exposure': exposure,
                'risk_pct': risk_pct,
                'pnl': yearly_pnl[year],
                'max_dd': yearly_max_dd[year]['max_dd_pct'],
                'trades': yearly_max_dd[year].get('trades', 0),
                'max_dd_usdt': yearly_max_dd[year].get('max_dd_usdt', 0),
            })

# 每年独立筛选
yearly_best = {}
for year in ['2023', '2024', '2025']:
    # 筛选可行配置
    feasible = [c for c in configs_by_year[year] if c['max_dd'] <= 50.0]

    if feasible:
        # 按 PnL 降序排序
        feasible_sorted = sorted(feasible, key=lambda x: x['pnl'], reverse=True)
        yearly_best[year] = {
            'best': feasible_sorted[0],
            'top3': feasible_sorted[:3],
            'feasible_count': len(feasible),
            'total_count': len(configs_by_year[year]),
        }
    else:
        yearly_best[year] = None

# 保存结果
output = {
    "title": "R1: Baseline Capital Allocation Search (Yearly Independent)",
    "date": "2026-04-29",
    "constraint": "MaxDD <= 50%（每年独立判定）",
    "cost": "BNB9 (fee=0.0405%, slippage=0.01%, tp_slippage=0)",
    "yearly_best": {},
}

for year in ['2023', '2024', '2025']:
    if yearly_best[year]:
        output['yearly_best'][year] = {
            'best_config': yearly_best[year]['best'],
            'top3': yearly_best[year]['top3'],
            'feasible_count': yearly_best[year]['feasible_count'],
            'total_count': yearly_best[year]['total_count'],
        }
    else:
        output['yearly_best'][year] = None

output_path = Path("reports/research/r1_yearly_optimal_config_2026-04-29.json")
output_path.parent.mkdir(parents=True, exist_ok=True)
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"[保存] {output_path}")
