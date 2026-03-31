#!/usr/bin/env python3
"""
验证信号 291 是否符合配置的 Pinbar 阈值
"""
from decimal import Decimal

# 信号 291 的 K 线数据
open_p = Decimal("619.51")
high = Decimal("621.21")
low = Decimal("618.96")
close = Decimal("618.97")

# 配置文件阈值 (core.yaml)
CFG_MIN_WICK = Decimal("0.5")
CFG_MAX_BODY = Decimal("0.35")
CFG_TOLERANCE = Decimal("0.3")

# 代码默认阈值 (strategy_engine.py)
CODE_MIN_WICK = Decimal("0.6")
CODE_MAX_BODY = Decimal("0.3")
CODE_TOLERANCE = Decimal("0.1")

print("=" * 80)
print("信号 291 K 线分析")
print("=" * 80)
print(f"O:{open_p} H:{high} L:{low} C:{close}")
print()

# 计算
candle_range = high - low
body_size = abs(close - open_p)
body_ratio = body_size / candle_range
upper_wick = high - max(open_p, close)
lower_wick = min(open_p, close) - low
dominant_wick = max(upper_wick, lower_wick)
wick_ratio = dominant_wick / candle_range

# Body position
body_center = (open_p + close) / Decimal(2)
body_position = (body_center - low) / candle_range

print(f"K 线范围：{candle_range}")
print(f"实体：{body_size} ({body_ratio:.2%})")
print(f"上影线：{upper_wick} ({upper_wick_ratio:.2%})" if (upper_wick_ratio := upper_wick/candle_range) else "")
print(f"下影线：{lower_wick} ({lower_wick_ratio:.2%})" if (lower_wick_ratio := lower_wick/candle_range) else "")
print(f"主导影线：{'上' if dominant_wick == upper_wick else '下'} ({wick_ratio:.2%})")
print(f"实体位置：{body_position:.4f} (0=底部，1=顶部)")
print()

# 检查 Pinbar 基础条件
print("=" * 80)
print("Pinbar 基础检测")
print("=" * 80)

# 配置文件阈值
wick_pass_cfg = wick_ratio >= CFG_MIN_WICK
body_pass_cfg = body_ratio <= CFG_MAX_BODY
pinbar_pass_cfg = wick_pass_cfg and body_pass_cfg

print(f"配置文件阈值 (core.yaml):")
print(f"  影线比 >= {CFG_MIN_WICK:.2%}: {'✅' if wick_pass_cfg else '❌'} ({wick_ratio:.2%})")
print(f"  实体比 <= {CFG_MAX_BODY:.2%}: {'✅' if body_pass_cfg else '❌'} ({body_ratio:.2%})")
print(f"  → Pinbar 基础：{'✅ 通过' if pinbar_pass_cfg else '❌ 不通过'}")
print()

# 代码默认阈值
wick_pass_code = wick_ratio >= CODE_MIN_WICK
body_pass_code = body_ratio <= CODE_MAX_BODY
pinbar_pass_code = wick_pass_code and body_pass_code

print(f"代码默认阈值 (strategy_engine.py):")
print(f"  影线比 >= {CODE_MIN_WICK:.2%}: {'✅' if wick_pass_code else '❌'} ({wick_ratio:.2%})")
print(f"  实体比 <= {CODE_MAX_BODY:.2%}: {'✅' if body_pass_code else '❌'} ({body_ratio:.2%})")
print(f"  → Pinbar 基础：{'✅ 通过' if pinbar_pass_code else '❌ 不通过'}")
print()

# 方向检测
print("=" * 80)
print("方向检测 (看涨 LONG)")
print("=" * 80)

# 使用配置文件阈值
threshold_cfg = Decimal(1) - CFG_TOLERANCE - body_ratio / 2
pass_cfg_dir = body_position >= threshold_cfg

# 使用代码默认阈值
threshold_code = Decimal(1) - CODE_TOLERANCE - body_ratio / 2
pass_code_dir = body_position >= threshold_code

print(f"配置文件阈值 (tolerance={CFG_TOLERANCE:.2%}):")
print(f"  body_position >= {threshold_cfg:.4f}: {'✅' if pass_cfg_dir else '❌'} (actual: {body_position:.4f})")
print(f"  → 方向检测：{'✅ LONG' if pass_cfg_dir else '❌ 非 LONG'}")
print()

print(f"代码默认阈值 (tolerance={CODE_TOLERANCE:.2%}):")
print(f"  body_position >= {threshold_code:.4f}: {'✅' if pass_code_dir else '❌'} (actual: {body_position:.4f})")
print(f"  → 方向检测：{'✅ LONG' if pass_code_dir else '❌ 非 LONG'}")
print()

# 总结
print("=" * 80)
print("总结")
print("=" * 80)
print(f"使用配置文件阈值：完整检测 {'✅ 通过' if (pinbar_pass_cfg and pass_cfg_dir) else '❌ 不通过'}")
print(f"使用代码默认阈值：完整检测 {'✅ 通过' if (pinbar_pass_code and pass_code_dir) else '❌ 不通过'}")
print()
print("⚠️ 核心问题：")
if not wick_pass_code:
    print(f"  - 下影线仅 {lower_wick_ratio:.2%}，远低于 60% 标准阈值")
    print(f"  - 配置文件阈值 50% 也未能阻止信号生成（因为实际是上影线主导）")
if dominant_wick == upper_wick:
    print(f"  - 这是上影线 K 线，但生成了 LONG 信号！方向逻辑可能有误")
