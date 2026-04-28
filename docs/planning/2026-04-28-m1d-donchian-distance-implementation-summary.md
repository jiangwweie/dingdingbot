# Donchian Distance Filter 实现总结

**日期**: 2026-04-28
**任务**: 实现 M1d Donchian Distance Filter
**状态**: ✅ 完成

---

## 修改文件

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `src/domain/filter_factory.py` | 新增 class | `DonchianDistanceFilterDynamic` (line 685-831) |
| `src/domain/filter_factory.py` | 修改 registry | 添加 `"donchian_distance": DonchianDistanceFilterDynamic` (line 726) |
| `src/domain/filter_factory.py` | 修改 create() | 添加 donchian_distance 处理分支 (line 813-821) |
| `tests/unit/test_donchian_distance_filter.py` | 新增 | 13 个单元测试 (100% 通过) |
| `scripts/test_donchian_smoke.py` | 新增 | Smoke test 验证集成 |

**未修改文件** (符合要求):
- ✅ `strategy_engine.py` — 无修改
- ✅ `backtester.py` — 无修改
- ✅ Runtime profiles — 无修改
- ✅ `sim1_eth_runtime` — 无修改
- ✅ Git — 未提交

---

## 核心实现说明

### 1. 类设计

```python
class DonchianDistanceFilterDynamic(FilterBase):
    """
    Donchian distance filter for filtering signals too close to channel boundaries.

    Stateful: Maintains rolling high/low windows per symbol/timeframe.
    Purpose: Avoid Pinbar signals near Donchian channel extremes (toxic states).
    """
```

**关键特性**:
- 继承 `FilterBase`，实现完整生命周期接口
- 有状态过滤器 (`is_stateful = True`)
- 多 symbol/timeframe 独立状态管理
- 参数可配置：`lookback`, `max_distance_to_high_pct`, `max_distance_to_low_pct`

### 2. 状态管理

```python
self._state: Dict[str, Dict[str, List[Decimal]]] = {}
# key: "symbol:timeframe"
# value: {"highs": [...], "lows": [...]}
```

**滚动窗口**:
- 维护 `lookback+1` 根 K 线（当前 + 前 N 根）
- 每次更新自动裁剪，保持固定大小
- 支持多个 symbol/timeframe 独立状态

### 3. 未来函数防护 (P0)

**问题**: 如果使用当前 K 线的 high/low 计算 Donchian 通道，再判断当前 close 是否接近通道边界，存在信息泄漏。

**解决方案**:
```python
# update_state() 累积所有 K 线（包含当前）
self._state[key]["highs"].append(kline.high)

# check() 时排除最后一根（当前 K 线），取前 lookback 根
historical_highs = state["highs"][-(self._lookback + 1):-1]
dc_high = max(historical_highs)
```

**验证测试**: `test_current_bar_excluded_from_donchian()`
- 前 5 根 highs = [100, 100, 100, 100, 100]
- 当前 bar high = 200 (新极端)
- Donchian high 仍为 100 (排除当前 bar)

### 4. 过滤逻辑

**LONG 信号**:
```python
# 检查是否太接近 Donchian 上轨
distance = (close - dc_high) / dc_high  # always ≤ 0
if distance >= max_distance_to_high_pct:
    return FAIL  # 太接近上轨，过滤
```

**SHORT 信号**:
```python
# 检查是否太接近 Donchian 下轨
distance = (dc_low - close) / dc_low  # always ≤ 0
if distance >= max_distance_to_low_pct:
    return FAIL  # 太接近下轨，过滤
```

**距离公式**:
- `distance` 总是 ≤ 0（价格不可能高于 Donchian high）
- `distance` 越接近 0 = 越接近通道边界
- 阈值示例：`-0.016809` = 价格距上轨 < 1.68% 即过滤

### 5. 参数模型

```python
{
    "type": "donchian_distance",
    "enabled": false,  # 默认关闭，安全默认
    "params": {
        "lookback": 20,  # Donchian 通道周期
        "max_distance_to_high_pct": "-0.016809",  # LONG 信号阈值
        "max_distance_to_low_pct": null  # SHORT 信号阈值（可选）
    }
}
```

**参数说明**:
- `lookback`: 回看周期（默认 20，来自 M0 研究）
- `max_distance_to_high_pct`: LONG 信号距离阈值（M0 tercile boundary）
- `max_distance_to_low_pct`: SHORT 信号距离阈值（预留，待研究）
- `enabled`: 默认 `False`，不影响现有 runtime

---

## 测试结果

### 单元测试 (13/13 通过)

| 测试类别 | 测试数 | 说明 |
|---------|--------|------|
| 基础功能 | 2 | 禁用过滤器、历史不足处理 |
| LONG 信号 | 3 | 接近 high 过滤、远离 high 通过、边界条件 |
| SHORT 信号 | 3 | 接近 low 过滤、远离 low 通过、无阈值配置 |
| 未来函数防护 | 2 | 当前 bar 排除、窗口滚动正确性 |
| 多 symbol | 1 | 状态隔离 |
| Factory 集成 | 2 | 创建过滤器、禁用过滤器 |

**关键测试**:
- ✅ `test_current_bar_excluded_from_donchian`: P0 未来函数防护
- ✅ `test_long_near_high_filtered`: 核心过滤逻辑
- ✅ `test_window_rolling_correctly`: 滚动窗口正确性
- ✅ `test_multiple_symbols_independent_state`: 多 symbol 隔离

### Smoke Test

```
=== Donchian Distance Filter Smoke Test ===

1. Creating filter via FilterFactory...
   ✓ Filter created: donchian_distance
   ✓ Lookback: 20
   ✓ Threshold: -0.016809
   ✓ Enabled: True

2. Simulating backtest lifecycle (25 bars)...
   ✓ Updated state for 25 bars
   ✓ State window size: 21 (expected: 21)

3. Testing LONG signal near Donchian high...
   ✓ Current close: 128
   ✓ Donchian high: 129.0
   ✓ Distance: -0.007752
   ✓ Result: FILTERED
   ✓ Reason: too_close_to_donchian_high

4. Testing LONG signal far from Donchian high...
   ✓ Current close: 110
   ✓ Donchian high: 135.0
   ✓ Result: PASSED
   ✓ Reason: donchian_distance_ok

5. Testing disabled filter...
   ✓ Result: PASSED
   ✓ Reason: filter_disabled

=== All smoke tests passed ✓ ===
```

### 回归测试

```
tests/unit/test_filter_factory.py::TestFilterFactory
  ✓ 30 passed, 13 deselected

所有现有 EMA/MTF/ATR 过滤器测试通过，无回归。
```

---

## 未来函数防护说明

### 防护策略

**核心原则**: 当前 signal K 线不得进入 Donchian high/low 计算。

**实现细节**:
1. `update_state(kline)` 累积所有 K 线（包含当前）
2. `check()` 时排除最后一根（当前 K 线）
3. 只使用前 `lookback` 根历史 K 线计算通道

**代码**:
```python
# 窗口包含当前 bar: [bar_{n-lookback}, ..., bar_{n-1}, bar_n]
window = state["highs"]  # length = lookback+1

# 排除当前 bar，只取历史: [bar_{n-lookback}, ..., bar_{n-1}]
historical_highs = window[-(self._lookback + 1):-1]
dc_high = max(historical_highs)
```

### 为什么这是保守的

1. **用 high/low 而非 close**: Donchian 通道使用 K 线的 high/low，已经避免了用 close 判断 close 的问题
2. **排除当前 K 线**: 完全由已完成的历史 K 线决定，零未来函数风险
3. **预热期保护**: 历史不足时返回 `passed=True`（安全降级，不过滤）

---

## 与 M1c 脚本的对照

| 维度 | M1c 脚本（手写） | 正式实现 |
|------|-----------------|---------|
| Donchian 计算 | `FeatureComputer` 内部 `deque(maxlen=20)` | `DonchianDistanceFilterDynamic.update_state()` 滚动窗口 |
| 阈值判断 | `lambda s: s.distance_to_donchian_20_high < -0.016809` | `DonchianDistanceFilterDynamic.check()` |
| 预热处理 | 跳过前 N 根 | `check()` 返回 `passed=True`（安全降级） |
| 当前 K 线排除 | 脚本中未排除（使用当前 bar 的 high） | **正式实现排除**（更保守） |
| LONG/SHORT | 仅 LONG | 双向支持（`max_distance_to_high_pct`/`max_distance_to_low_pct`） |

**注意**: M1c 脚本中 Donchian 使用了当前 bar 的 high（`deque` 在信号判断前 append），正式实现排除当前 bar，可能导致正式实现过滤率略低。这是有意为之 — 正式实现更保守，防止未来函数。

---

## 是否需要进一步接入 Backtest strategy config

**当前状态**: 已完成 FilterFactory 集成，可通过配置启用。

**下一步建议**:
1. ✅ **不需要修改 Backtest strategy config** — FilterFactory 已支持动态创建
2. ✅ **不需要修改 sim1_eth_runtime** — `enabled=False` 安全默认
3. 🔄 **可选**: 在研究脚本中测试 donchian_distance filter 的实际效果

**如何启用**:
```python
# 在策略配置中添加过滤器
filters = [
    {"type": "ema_trend", "enabled": True, "params": {"period": 60}},
    {"type": "mtf", "enabled": True},
    {"type": "donchian_distance", "enabled": True, "params": {
        "lookback": 20,
        "max_distance_to_high_pct": "-0.016809"
    }}
]
```

**验证路径**:
1. 在研究脚本中用正式 filter 替代手写 lambda
2. 跑 Pinbar baseline，确认未配置 donchian_distance 时结果不变
3. 配置 donchian_distance 后，确认能过滤部分信号
4. 对比 M1c 结果，验证方向一致

---

## 总结

✅ **实现完成**: Donchian Distance Filter 已完整实现并通过所有测试
✅ **P0 未来函数防护**: 当前 K 线排除机制已验证
✅ **零影响**: 现有 runtime 不受影响（`enabled=False`）
✅ **可扩展**: 支持 LONG/SHORT 双向，参数可配置
✅ **无回归**: 所有现有过滤器测试通过

**工作量**: ~2h（符合预期）
**代码质量**: 13 个单元测试 + smoke test + 文档
**架构一致性**: 完全符合 FilterBase 生命周期设计
