#!/usr/bin/env python3
"""对比两次回测的配置差异"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 80)
print("两次回测配置对比")
print("=" * 80)

# 这次回测（validate_long_baseline.py）
this_time = {
    "脚本": "validate_long_baseline.py",
    "mtf_ema_period": "未显式设置（使用默认值或 ConfigManager）",
    "mtf_mapping": "未显式设置（使用默认值或 ConfigManager）",
    "ema_period": 90,
    "max_atr_ratio": 0.0059,
    "min_distance_pct": 0.0080,
    "allowed_directions": "LONG（通过 direction_filter）",
    "tp_ratios": [0.5, 0.5],
    "tp_targets": "未显式设置（使用 tp1_ratio=1.0, tp2_ratio=3.5）",
    "slippage": 0.001,
    "tp_slippage": 0.0005,
    "fee": 0.0004,
    "时间范围": "2024-01-01 ~ 2024-12-31, 2025-01-01 ~ 2025-12-31",
    "mode": "v3_pms",
    "是否 v3_pms": "是",
}

# 上一轮 TP2=3.5R 回测（validate_tp2_neighborhood.py）
last_time = {
    "脚本": "validate_tp2_neighborhood.py",
    "mtf_ema_period": "未显式设置（使用默认值或 ConfigManager）",
    "mtf_mapping": "未显式设置（使用默认值或 ConfigManager）",
    "ema_period": 111,
    "max_atr_ratio": 0.0059,
    "min_distance_pct": 0.0080,
    "allowed_directions": "LONG（通过 allowed_directions）",
    "tp_ratios": [0.5, 0.5],
    "tp_targets": "[1.0, 3.5]（通过 tp_targets 参数）",
    "slippage": 0.001,
    "tp_slippage": 0.0005,
    "fee": 0.0004,
    "时间范围": "2024-01-01 ~ 2024-12-31, 2025-01-01 ~ 2025-12-31",
    "mode": "v3_pms",
    "是否 v3_pms": "是",
}

# 输出对比表
print(f"\n{'配置项':<25} {'这次回测':<40} {'上一轮 TP2=3.5R':<40}")
print("-" * 105)

all_keys = set(this_time.keys()) | set(last_time.keys())
differences = []

for key in sorted(all_keys):
    this_val = this_time.get(key, "N/A")
    last_val = last_time.get(key, "N/A")
    
    if this_val != last_val:
        differences.append(key)
        marker = " ❌"
    else:
        marker = " ✅"
    
    print(f"{key:<25} {str(this_val):<40} {str(last_val):<40} {marker}")

print("\n" + "=" * 80)
print("差异项汇总")
print("=" * 80)

if differences:
    print(f"\n发现 {len(differences)} 个差异项：")
    for i, diff in enumerate(differences, 1):
        print(f"{i}. {diff}")
        print(f"   这次: {this_time[diff]}")
        print(f"   上轮: {last_time[diff]}")
else:
    print("\n✅ 所有配置项完全一致")

print("\n" + "=" * 80)
print("最可能差异原因")
print("=" * 80)

if "ema_period" in differences:
    print("\n1. ema_period 差异（90 vs 111）")
    print("   - 这是最关键的差异项")
    print("   - EMA 周期直接影响趋势判断和入场信号")
    print("   - 90 和 111 的差异可能导致完全不同的信号集")

if "tp_targets" in differences:
    print("\n2. tp_targets 设置方式差异")
    print("   - 这次使用 tp1_ratio=1.0, tp2_ratio=3.5")
    print("   - 上轮使用 tp_targets=[1.0, 3.5]")
    print("   - 可能导致止盈逻辑不同")

print("\n" + "=" * 80)
print("结论")
print("=" * 80)

if differences:
    print(f"\n❌ 配置不一致，主要差异：ema_period（90 vs 111）")
    print(f"   这是最可能导致结果差异的原因")
else:
    print(f"\n✅ 配置一致，需要检查其他因素")
    print(f"   - 数据窗口是否完全相同")
    print(f"   - ConfigManager 是否正确读取")
    print(f"   - MTF 配置是否一致")

print("\n" + "=" * 80)
