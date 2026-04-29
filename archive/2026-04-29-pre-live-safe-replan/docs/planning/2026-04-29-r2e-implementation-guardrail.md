# R2e Baseline 真源接线 - 实现防线补充（修正版）

> **日期**: 2026-04-29
> **任务**: 补充 R2d 方案的实现防线，确认类型安全和序列化方案
> **约束**: 不改代码，不跑搜索，不跑 smoke

---

## 1. `request.strategies` 的正式期望类型

### 1.1 类型定义

```python
# src/domain/models.py:661
strategies: Optional[List[Dict[str, Any]]] = Field(
    default=None,
    description="Dynamic strategy definitions with filter chains (overrides legacy params)"
)
```

**正式期望类型**: `Optional[List[Dict[str, Any]]]`

### 1.2 v3_pms dynamic path 消费方式

```python
# src/application/backtester.py:735-749
def _build_dynamic_runner(
    self,
    strategy_definitions: List[StrategyDefinition],  # ⚠️ 类型注解是 StrategyDefinition
    resolved_params: Optional[ResolvedBacktestParams] = None,
) -> DynamicStrategyRunner:
    # 手动反序列化为 StrategyDefinition 对象
    # 因为 BacktestRequest.strategies 使用 List[Dict] 而非 List[StrategyDefinition]
    strategies = []
    for strat_def in strategy_definitions:
        if isinstance(strat_def, StrategyDefinition):
            strategies.append(strat_def)
        else:
            # 从 dict 反序列化
            try:
                strategies.append(StrategyDefinition(**strat_def))
            except Exception as e:
                logger.warning(f"Failed to deserialize strategy: {e}")
                continue

    return create_dynamic_runner(strategies, resolved_params=resolved_params)
```

**结论**:
- `BacktestRequest.strategies` 类型是 `List[Dict[str, Any]]`
- `_build_dynamic_runner` 会从 dict 反序列化为 `StrategyDefinition` 对象
- 但如果传入的是 `StrategyDefinition` 对象，它会被直接使用（不反序列化）

---

## 2. 推荐方案：profile 真源 + 安全序列化 dict + re-validate 自检

### 2.1 为什么不能直接传对象

- `BacktestRequest.strategies` 在模型层正式定义仍是 `Optional[List[Dict[str, Any]]]`
- 当前契约不是 `List[StrategyDefinition]`
- 直接塞对象属于依赖隐式行为，不适合作为防线

### 2.2 推荐方案

**profile 真源 + 安全序列化 dict + re-validate 自检** 更安全。

**步骤**：
1. 从 baseline profile 生成 `StrategyDefinition` 对象
2. 安全序列化为 dict（使用 `model_dump()`）
3. 立即做本地反序列化自检：`StrategyDefinition(**strategy_dict)`
4. 自检通过后再放进 `request.strategies`

---

## 3. 安全序列化方案

### 3.1 方案 A（推荐）：`model_dump()` + 反序列化自检

```python
from src.application.backtest_config import BACKTEST_ETH_BASELINE_PROFILE
from src.domain.models import StrategyDefinition

profile = BACKTEST_ETH_BASELINE_PROFILE

# 1. 从 baseline profile 生成 StrategyDefinition 对象
strategy_definition = profile.strategy.to_strategy_definition(
    strategy_id=f"{profile.name}_strategy",
    name=f"{profile.name}_strategy",
    market=profile.market,
)

# 2. 安全序列化为 dict
strategy_dict = strategy_definition.model_dump()

# 3. 立即做本地反序列化自检
try:
    reconstructed = StrategyDefinition(**strategy_dict)
    print(f"✅ 反序列化自检成功")
except Exception as e:
    print(f"❌ 反序列化自检失败: {e}")
    raise  # 停止，不运行 smoke

# 4. 自检通过后再放进 request.strategies
request = BacktestRequest(
    ...
    strategies=[strategy_dict],  # ✅ 使用 dict
)
```

### 3.2 `model_dump()` 行为分析

```python
# model_dump() 会序列化所有字段
dump = strategy_definition.model_dump()
print(list(dump.keys()))
# ['id', 'name', 'logic_tree', 'triggers', 'trigger_logic', 'trigger', 'filters', 'filter_logic', 'is_global', 'apply_to']
```

**结论**:
- `model_dump()` 会序列化所有字段，包括旧字段（`triggers`、`filters`、`trigger` 等）
- 反序列化自检成功，`filters[2].enabled` 仍然是 `False`（ATR filter disabled）
- legacy 字段不会影响 `logic_tree` 的使用

---

## 4. ATR filter 自检方式

### 4.1 不要用固定下标 `filters[2]`

- 固定下标假设 ATR filter 总是在第 3 个位置
- 如果 profile 配置变更，下标会失效
- 应该动态查找 `type == "atr"` 的 filter

### 4.2 推荐方式：查找 `type == "atr"` 的 filter

```python
# ATR filter 自检
atr_filter = None
for f in strategy_definition.filters:
    if f.type == "atr":
        atr_filter = f
        break

if atr_filter is None:
    print("❌ ATR filter 不存在，停止 smoke")
    raise ValueError("ATR filter not found")

if atr_filter.enabled != False:
    print(f"❌ ATR filter enabled={atr_filter.enabled}，停止 smoke")
    raise ValueError("ATR filter should be disabled")

print(f"✅ ATR filter disabled，继续 smoke")
```

### 4.3 也可以检查 `strategy_dict` 中的 ATR filter

```python
# 在 strategy_dict 中查找 type == "atr" 的 filter
atr_filter_dict = None
for f in strategy_dict.get("filters", []):
    if f.get("type") == "atr":
        atr_filter_dict = f
        break

if atr_filter_dict is None:
    print("❌ ATR filter 不存在，停止 smoke")
    raise ValueError("ATR filter not found")

if atr_filter_dict.get("enabled") != False:
    print(f"❌ ATR filter enabled={atr_filter_dict.get('enabled')}，停止 smoke")
    raise ValueError("ATR filter should be disabled")

print(f"✅ ATR filter disabled，继续 smoke")
```

---

## 5. 修正后的最小 smoke 执行方案

### 5.1 执行顺序

1. **修改 R2 smoke 脚本接线**
   - 导入 `BACKTEST_ETH_BASELINE_PROFILE`
   - 使用 `profile.strategy.to_strategy_definition()` 生成 `strategy_definition`
   - 使用 `profile.execution.to_order_strategy()` 生成 `order_strategy`
   - 移除 `runtime_overrides` 中的 `max_atr_ratio=None`

2. **加入 strategy serialization self-check**
   - 使用 `model_dump()` + 反序列化自检
   - ATR filter 自检使用动态查找（查找 `type == "atr"` 的 filter）

3. **只跑 2024 单年 smoke**
   - exposure=2.0
   - risk=1.0%

4. **不做全量搜索**

### 5.2 修改文件

- `scripts/run_r2a_baseline_smoke.py`

### 5.3 修改内容

```python
# ❌ 当前实现
request = BacktestRequest(
    symbol="ETH/USDT:USDT",
    timeframe="1h",
    start_time=start_time,
    end_time=end_time,
    mode="v3_pms",
    risk_overrides=risk_overrides,
    # strategies=None → Legacy Path
)

runtime_overrides = BacktestRuntimeOverrides(
    ema_period=50,
    min_distance_pct=Decimal("0.005"),
    mtf_ema_period=60,
    max_atr_ratio=None,  # ❌ 问题所在
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    breakeven_enabled=False,
    allowed_directions=["LONG"],
    fee_rate=BNB9_FEE_RATE,
    slippage_rate=BNB9_SLIPPAGE,
    tp_slippage_rate=Decimal("0"),
)

# ✅ 修正实现
from src.application.backtest_config import BACKTEST_ETH_BASELINE_PROFILE
from src.domain.models import StrategyDefinition

profile = BACKTEST_ETH_BASELINE_PROFILE

# 1. 策略层：从 baseline profile 生成 StrategyDefinition 对象
strategy_definition = profile.strategy.to_strategy_definition(
    strategy_id=f"{profile.name}_strategy",
    name=f"{profile.name}_strategy",
    market=profile.market,
)

# 2. 安全序列化为 dict
strategy_dict = strategy_definition.model_dump()

# 3. 立即做本地反序列化自检
try:
    reconstructed = StrategyDefinition(**strategy_dict)
    print(f"✅ 反序列化自检成功")
except Exception as e:
    print(f"❌ 反序列化自检失败: {e}")
    raise  # 停止，不运行 smoke

# 4. ATR filter 自检（动态查找 type == "atr" 的 filter）
atr_filter_dict = None
for f in strategy_dict.get("filters", []):
    if f.get("type") == "atr":
        atr_filter_dict = f
        break

if atr_filter_dict is None:
    print("❌ ATR filter 不存在，停止 smoke")
    raise ValueError("ATR filter not found")

if atr_filter_dict.get("enabled") != False:
    print(f"❌ ATR filter enabled={atr_filter_dict.get('enabled')}，停止 smoke")
    raise ValueError("ATR filter should be disabled")

print(f"✅ ATR filter disabled，继续 smoke")

# 5. 执行层：从 baseline profile 生成 order_strategy
order_strategy = profile.execution.to_order_strategy(
    strategy_id=f"{profile.name}_execution",
    resolved_params=None,
)

# 6. 构建 request
request = BacktestRequest(
    symbol="ETH/USDT:USDT",
    timeframe="1h",
    start_time=start_time,
    end_time=end_time,
    mode="v3_pms",
    risk_overrides=risk_overrides,
    strategies=[strategy_dict],  # ✅ Dynamic Strategy Path（使用 dict）
    order_strategy=order_strategy,  # ✅ 执行层真源
)

# 7. 参数层：显式锁定 baseline 参数
runtime_overrides = BacktestRuntimeOverrides(
    ema_period=50,
    min_distance_pct=Decimal("0.005"),
    mtf_ema_period=60,
    allowed_directions=["LONG"],
    # ❌ 不传 max_atr_ratio=None
    fee_rate=BNB9_FEE_RATE,
    slippage_rate=BNB9_SLIPPAGE,
    tp_slippage_rate=Decimal("0"),
)
```

---

## 6. 2024 Smoke 验证方案（9 项）

### 6.1 配置

| 参数 | 值 | 来源 |
|------|-----|------|
| **year** | 2024 | 固定 |
| **exposure** | 2.0 | `request.risk_overrides.max_total_exposure` |
| **risk** | 1.0% | `request.risk_overrides.max_loss_percent` |
| **profile** | backtest_eth_baseline | `BACKTEST_ETH_BASELINE_PROFILE` |
| **strategy_definition** | profile.strategy.to_strategy_definition() | 从 profile 生成 |
| **strategy_dict** | strategy_definition.model_dump() | 安全序列化 |
| **order_strategy** | profile.execution.to_order_strategy() | 从 profile 生成 |

### 6.2 验证字段（9 项）

| # | 验证项 | 期望值 | 验证方式 |
|---|--------|--------|---------|
| 1 | **ATR filter enabled** | **False** | `strategy_dict.filters[type="atr"].enabled == False` |
| 2 | **tp_targets** | **[1.0, 3.5]** | `order_strategy.tp_targets == [1.0, 3.5]` |
| 3 | **tp_ratios** | **[0.5, 0.5]** | `order_strategy.tp_ratios == [0.5, 0.5]` |
| 4 | **breakeven_enabled** | **False** | `order_strategy.breakeven_enabled == False` |
| 5 | **allowed_directions** | **["LONG"]** | `params.allowed_directions == ["LONG"]` |
| 6 | **trades** | **几十笔** | `< 100` |
| 7 | **pnl** | **明显正收益** | `> 0` |
| 8 | **strategy_dict 反序列化成功** | **True** | `StrategyDefinition(**strategy_dict)` 成功 |
| 9 | **request.strategies 确实进入 dynamic strategy path** | **True** | `use_dynamic = request.strategies is not None and len(request.strategies) > 0` |

### 6.3 验收标准

```
✅ PASS:
  - ATR filter enabled=False
  - tp_targets=[1.0, 3.5], tp_ratios=[0.5, 0.5], breakeven_enabled=False
  - allowed_directions=["LONG"]
  - trades < 100（几十笔量级）
  - pnl > 0（明显正收益）
  - strategy_dict 反序列化成功
  - request.strategies 确实进入 dynamic strategy path

❌ FAIL:
  - ATR filter enabled=True
  - trades >= 100（仍是数百笔）
  - pnl <= 0（明显负收益）
  - strategy_dict 反序列化失败
  - request.strategies 未进入 dynamic strategy path
  → 立即停止，不继续全量搜索
```

---

## 7. 总结

### 7.1 `request.strategies` 的正式期望类型

- **类型**: `Optional[List[Dict[str, Any]]]`
- **v3_pms dynamic path 消费方式**: 从 dict 反序列化为 `StrategyDefinition` 对象

### 7.2 推荐方案

**profile 真源 + 安全序列化 dict + re-validate 自检** 更安全。

**步骤**：
1. 从 baseline profile 生成 `StrategyDefinition` 对象
2. 安全序列化为 dict（使用 `model_dump()`）
3. 立即做本地反序列化自检：`StrategyDefinition(**strategy_dict)`
4. 自检通过后再放进 `request.strategies`

### 7.3 ATR filter 自检方式

- 不要用固定下标 `filters[2]`
- 动态查找 `type == "atr"` 的 filter
- 验证其 `enabled == False`

### 7.4 修正后的最小 smoke 执行方案

1. 修改 R2 smoke 脚本接线
2. 加入 strategy serialization self-check
3. ATR filter 自检使用动态查找
4. 只跑 2024 单年 smoke
5. 不做全量搜索

### 7.5 等待确认后再跑

**请确认以下内容后再运行 smoke**：

1. ✅ `request.strategies` 类型是 `Optional[List[Dict[str, Any]]]`
2. ✅ 推荐方案是 "profile 真源 + 安全序列化 dict + re-validate 自检"
3. ✅ ATR filter 自检使用动态查找（查找 `type == "atr"` 的 filter）
4. ✅ 2024 smoke 验证方案（9 项）已确认

---

*防线补充完成时间: 2026-04-29*
*方案状态: ✅ 待执行*
*下一步: 确认后运行 2024 Smoke Test*