# Donchian Distance Filter 提交前小修

**日期**: 2026-04-28
**修改范围**: 仅 `filter_factory.py` + 测试文件
**状态**: ✅ 完成

---

## 修改项

### 1. 参数验证 (P0)

#### lookback 必须 >= 1

```python
if lookback < 1:
    raise ValueError(f"lookback must be >= 1, got {lookback}")
```

**原因**: lookback=0 或负数无意义，会导致 Donchian 通道计算错误。

**测试**:
- `test_lookback_must_be_positive`: 验证 lookback=0 和 -1 抛出 ValueError
- `test_lookback_minimum_valid`: 验证 lookback=1 合法

#### max_distance_to_high_pct / max_distance_to_low_pct 必须 <= 0

```python
if max_distance_to_high_pct is not None and max_distance_to_high_pct > 0:
    raise ValueError(
        f"max_distance_to_high_pct must be <= 0 (distance is always negative or zero), "
        f"got {max_distance_to_high_pct}"
    )
```

**原因**:
- 距离公式: `distance = (close - dc_high) / dc_high`，总是 ≤ 0
- 阈值必须是负数或零，正数无意义
- 例如: `-0.016809` 表示价格距上轨 < 1.68% 即过滤

**测试**:
- `test_max_distance_high_must_be_negative_or_zero`: 验证正数抛出 ValueError
- `test_max_distance_low_must_be_negative_or_zero`: 验证正数抛出 ValueError
- `test_zero_distance_threshold_valid`: 验证 0 合法（过滤精确触碰边界）
- `test_negative_distance_threshold_valid`: 验证负数合法

---

### 2. 文档增强

#### Class Docstring 生命周期说明

```python
"""
Donchian distance filter for filtering signals too close to channel boundaries.

Stateful: Maintains rolling high/low windows per symbol/timeframe.
Purpose: Avoid Pinbar signals near Donchian channel extremes (toxic states).

Lifecycle Assumptions:
    1. update_state(kline) is called BEFORE check() for every bar
    2. check() excludes the last bar in rolling window (current K-line) to prevent look-ahead
    3. If history < lookback+1 bars, returns passed=True with reason="insufficient_history" (safe degradation)

Look-ahead Prevention:
    - Current K-line is appended to window in update_state()
    - check() uses only previous N bars: window[-(lookback+1):-1]
    - This ensures Donchian high/low are computed from completed bars only
"""
```

**关键说明**:
1. **生命周期假设**: 明确 `update_state()` 先于 `check()` 调用
2. **未来函数防护**: 明确排除当前 K 线的机制
3. **安全降级**: 历史不足时返回 `passed=True`，不过滤

#### __init__ Docstring 参数约束

```python
Args:
    lookback: Number of bars for Donchian channel (default 20, must be >= 1)
    max_distance_to_high_pct: Max distance to Donchian high for LONG signals (e.g., -0.016809, must be <= 0)
    max_distance_to_low_pct: Max distance to Donchian low for SHORT signals (must be <= 0)
    enabled: Whether filter is active (default False for safety)

Raises:
    ValueError: If lookback < 1 or distance thresholds are positive
```

---

## 测试结果

### 新增测试 (6 个)

| 测试 | 验证内容 |
|------|----------|
| `test_lookback_must_be_positive` | lookback=0 和 -1 抛出 ValueError |
| `test_lookback_minimum_valid` | lookback=1 合法 |
| `test_max_distance_high_must_be_negative_or_zero` | 正数阈值抛出 ValueError |
| `test_max_distance_low_must_be_negative_or_zero` | 正数阈值抛出 ValueError |
| `test_zero_distance_threshold_valid` | 阈值=0 合法 |
| `test_negative_distance_threshold_valid` | 负数阈值合法 |

### 完整测试结果

```
tests/unit/test_donchian_distance_filter.py
  ✓ 19 passed in 0.04s

tests/unit/test_filter_factory.py
  ✓ 43 passed in 0.04s

总计: 62 个测试全部通过，无回归
```

---

## 风险评估

### ✅ 已消除风险

1. **参数合法性**: lookback < 1 和正数阈值现在会立即抛出 ValueError，防止运行时错误
2. **文档清晰度**: 生命周期假设和未来函数防护机制已明确说明
3. **边界条件**: 零阈值和最小 lookback 已测试

### ⚠️ 潜在风险（已缓解）

1. **FilterFactory.create() 未验证参数**
   - 当前 FilterFactory 不会在创建过滤器前验证参数
   - 如果配置传入非法参数，会在过滤器 `__init__` 时抛出 ValueError
   - **缓解**: ValueError 会立即暴露问题，不会导致静默错误

2. **Decimal 类型转换**
   - FilterFactory.create() 中已处理 Decimal 转换
   - 如果传入字符串 `"-0.016809"`，会正确转换为 Decimal
   - **缓解**: 已有测试覆盖字符串参数

### ✅ 无风险项

1. **现有 runtime 不受影响**: `enabled=False` 安全默认
2. **无回归**: 所有现有过滤器测试通过
3. **架构一致性**: 完全符合 FilterBase 设计

---

## 修改文件

| 文件 | 修改类型 | 行数变化 |
|------|----------|----------|
| `src/domain/filter_factory.py` | 参数验证 + 文档 | +30 行 |
| `tests/unit/test_donchian_distance_filter.py` | 新增测试 | +44 行 |

**未修改文件** ✅:
- `strategy_engine.py`
- `backtester.py`
- Runtime profiles
- `sim1_eth_runtime`

---

## 总结

✅ **参数验证完成**: lookback >= 1, distance thresholds <= 0
✅ **文档增强完成**: 生命周期假设、未来函数防护、安全降级
✅ **测试覆盖完整**: 19 个测试全部通过
✅ **无回归**: 43 个现有过滤器测试通过
✅ **风险可控**: ValueError 立即暴露非法参数

**建议**: 可以提交到代码库，无已知风险。
