#!/usr/bin/env python3
"""
R1 Baseline Capital Allocation Search - 基于 R1b 审计结果

目标：
在 MaxDD <= 50% 约束下（按年度独立判定），搜索最优资金管理参数。

约束：
- 年度独立判定：所有三年 MaxDD 都 <= 50% 才算可行
- 不重新运行回测，直接复用 R1b 审计结果
"""
import json
from pathlib import Path
from datetime import datetime

# 读取 R1b 审计结果
r1b_path = Path("reports/research/r1b_capital_allocation_audit_v2_2026-04-29.json")
with open(r1b_path) as f:
    r1b_data = json.load(f)

print("=" * 80)
print("R1 Baseline Capital Allocation Search")
print("=" * 80)
print(f"日期: 2026-04-29")
print(f"约束: MaxDD <= 50%（按年度独立判定）")
print(f"数据来源: R1b 审计结果（56 组配置）")

# ============================================================
# 1. Baseline 验证（exposure=1.0, risk=1%）
# ============================================================
print("\n" + "=" * 80)
print("1. Baseline 验证（exposure=1.0, risk=1.0%）")
print("=" * 80)

baseline = None
for result in r1b_data['audit_results']:
    if result['exposure'] == 1.0 and abs(result['risk_pct'] - 0.01) < 0.0001:
        baseline = result
        break

if baseline:
    print(f"\nTotal PnL: {baseline['total_pnl']:.2f} USDT")
    print(f"MaxDD (debug_curve): {baseline['debug_curve_max_dd']:.2f}%")
    print(f"MaxDD (realized_curve): {baseline['realized_curve_max_dd']:.2f}%")
    print(f"Trades: {baseline['trades']}")
    print(f"\n年度表现:")
    for year in sorted(baseline['yearly_pnl'].keys()):
        print(f"  {year}: PnL={baseline['yearly_pnl'][year]:.2f} USDT, "
              f"MaxDD={baseline['yearly_max_dd'][year]['max_dd_pct']:.2f}%")

# ============================================================
# 2. 筛选可行配置（年度独立判定）
# ============================================================
print("\n" + "=" * 80)
print("2. 筛选可行配置（年度独立判定：所有三年 MaxDD <= 50%）")
print("=" * 80)

feasible_configs = []
for result in r1b_data['audit_results']:
    yearly_max_dd = result['yearly_max_dd']

    # 检查所有三年是否都 <= 50%
    all_years_ok = all(
        max_dd['max_dd_pct'] <= 50.0
        for max_dd in yearly_max_dd.values()
    )

    if all_years_ok:
        # 计算 Calmar
        calmar = result['total_pnl'] / (result['debug_curve_max_dd'] * 100) if result['debug_curve_max_dd'] > 0 else 0

        feasible_configs.append({
            **result,
            'calmar': calmar,
        })

print(f"\n可行配置数量: {len(feasible_configs)} / 56")

# ============================================================
# 3. 最优配置
# ============================================================
print("\n" + "=" * 80)
print("3. 最优配置")
print("=" * 80)

if not feasible_configs:
    print("\n❌ 无可行配置（所有配置都有至少一年 MaxDD > 50%）")
else:
    # 3.1 Total PnL 最高
    print("\n3.1 Total PnL 最高")
    print("-" * 80)
    best_pnl = max(feasible_configs, key=lambda x: x['total_pnl'])
    print(f"\nexposure={best_pnl['exposure']}, risk={best_pnl['risk_pct']*100:.2f}%")
    print(f"Total PnL: {best_pnl['total_pnl']:.2f} USDT")
    print(f"MaxDD: {best_pnl['debug_curve_max_dd']:.2f}%")
    print(f"Trades: {best_pnl['trades']}")
    print(f"Calmar: {best_pnl['calmar']:.2f}")
    print(f"\n年度表现:")
    for year in sorted(best_pnl['yearly_pnl'].keys()):
        print(f"  {year}: PnL={best_pnl['yearly_pnl'][year]:.2f} USDT, "
              f"MaxDD={best_pnl['yearly_max_dd'][year]['max_dd_pct']:.2f}%")

    # 3.2 Sharpe 最高（暂无数据）
    print("\n\n3.2 Sharpe 最高")
    print("-" * 80)
    print("⚠️ R1b 审计未计算 Sharpe ratio")

    # 3.3 Calmar 最高
    print("\n\n3.3 Calmar 最高")
    print("-" * 80)
    best_calmar = max(feasible_configs, key=lambda x: x['calmar'])
    print(f"\nexposure={best_calmar['exposure']}, risk={best_calmar['risk_pct']*100:.2f}%")
    print(f"Total PnL: {best_calmar['total_pnl']:.2f} USDT")
    print(f"MaxDD: {best_calmar['debug_curve_max_dd']:.2f}%")
    print(f"Calmar: {best_calmar['calmar']:.2f}")
    print(f"Trades: {best_calmar['trades']}")

    # 3.4 Conservative（MaxDD <= 25%）
    print("\n\n3.4 Conservative（MaxDD <= 25%）")
    print("-" * 80)
    conservative = [c for c in feasible_configs if c['debug_curve_max_dd'] <= 25.0]
    if conservative:
        best_conservative = max(conservative, key=lambda x: x['total_pnl'])
        print(f"\nexposure={best_conservative['exposure']}, risk={best_conservative['risk_pct']*100:.2f}%")
        print(f"Total PnL: {best_conservative['total_pnl']:.2f} USDT")
        print(f"MaxDD: {best_conservative['debug_curve_max_dd']:.2f}%")
        print(f"Trades: {best_conservative['trades']}")
    else:
        print("\n❌ 无 Conservative 配置（MaxDD <= 25%）")

# ============================================================
# 4. 可行配置统计
# ============================================================
print("\n\n" + "=" * 80)
print("4. 可行配置统计")
print("=" * 80)

print(f"\n总配置数: 56")
print(f"可行配置（年度独立判定）: {len(feasible_configs)}")
print(f"Conservative（MaxDD <= 25%）: {len([c for c in feasible_configs if c['debug_curve_max_dd'] <= 25.0])}")

# ============================================================
# 5. 风险收益关系
# ============================================================
print("\n" + "=" * 80)
print("5. 风险收益关系")
print("=" * 80)

risk_groups = {}
for config in feasible_configs:
    risk = config['risk_pct']
    if risk not in risk_groups:
        risk_groups[risk] = []
    risk_groups[risk].append(config)

print("\n按 risk 分组统计:")
for risk in sorted(risk_groups.keys()):
    configs = risk_groups[risk]
    avg_pnl = sum(c['total_pnl'] for c in configs) / len(configs)
    avg_maxdd = sum(c['debug_curve_max_dd'] for c in configs) / len(configs)
    print(f"\nrisk={risk*100:.2f}%:")
    print(f"  可行配置数: {len(configs)}")
    print(f"  平均 PnL: {avg_pnl:.2f} USDT")
    print(f"  平均 MaxDD: {avg_maxdd:.2f}%")

# ============================================================
# 6. 保存结果
# ============================================================
output = {
    "title": "R1: Baseline Capital Allocation Search",
    "date": "2026-04-29",
    "constraint": "MaxDD <= 50%（按年度独立判定）",
    "data_source": "R1b 审计结果",
    "total_configs": 56,
    "feasible_configs": len(feasible_configs),
    "best_configs": {
        "max_pnl": best_pnl if feasible_configs else None,
        "max_calmar": best_calmar if feasible_configs else None,
        "conservative": best_conservative if conservative else None,
    },
    "all_feasible_configs": feasible_configs,
}

output_path = Path("reports/research/r1_baseline_capital_allocation_search_2026-04-29.json")
output_path.parent.mkdir(parents=True, exist_ok=True)
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"\n\n[保存] {output_path}")
