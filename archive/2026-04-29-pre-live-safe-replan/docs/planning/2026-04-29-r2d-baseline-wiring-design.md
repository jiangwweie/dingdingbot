# R2d Baseline 真源接线方案设计

> **日期**: 2026-04-29
> **任务**: 设计"如何把 baseline 语义真正注入 Backtester 会消费的入口"
> **约束**: 不改代码，不跑搜索，不跑 smoke

---

## 1. 一句话结论

**R2 应通过 `request.strategies` 注入 baseline profile 的 `strategy_definition`（含 ATR filter `enabled=False`），并通过 `request.order_strategy` 注入 execution 参数，而非依赖 `runtime_overrides.max_atr_ratio=None`**

---

## 2. 推荐路径

### 2.1 Dynamic Strategy Path vs Legacy Path

| 路径 | 触发条件 | 策略消费方式 | ATR filter 支持 | 推荐度 |
|------|---------|-------------|----------------|--------|
| **Dynamic Strategy Path** | `request.strategies is not None and len(request.strategies) > 0` | `StrategyDefinition` → `FilterFactory.create_chain()` → `FilterBase` | ✅ 支持 `enabled` 字段 | ⭐⭐⭐ |
| **Legacy Path** | `request.strategies is None` | `IsolatedStrategyConfig` → `IsolatedStrategyRunner` | ❌ 不支持 `enabled` 字段 | ⭐ |

### 2.2 推荐：Dynamic Strategy Path

**原因**：

1. **策略定义与参数解耦**：`StrategyDefinition` 包含完整的 trigger + filters 定义，包括 `enabled` 字段
2. **ATR filter `enabled=False` 被正确消费**：`FilterFactory.create()` 会读取 `filter_config.enabled`，若 `False` 则创建 `enabled=False` 的 filter 实例
3. **`AtrFilterDynamic.check()` 会跳过 disabled filter**：直接返回 `passed=True, reason="filter_disabled"`
4. **参数注入由 `resolved_params` 控制**：`FilterFactory.create()` 支持 `resolved_params` 覆盖 filter 参数，但 `enabled` 字段优先从 `filter_config` 读取

### 2.3 Legacy Path 的问题

1. **不支持 `enabled` 字段**：`IsolatedStrategyRunner` 硬编码了 `EmaTrendFilter`、`MtfFilter`、`AtrFilter`
2. **ATR filter 始终启用**：无法通过配置关闭
3. **参数注入路径不同**：`_build_strategy_config()` 从 `resolved_params` 读取参数，但无法关闭 ATR filter

---

## 3. 最小接线方案

### 3.1 策略层（Strategy Source of Truth）

**从哪里来**：`BACKTEST_ETH_BASELINE_PROFILE.strategy.to_strategy_definition()`

**放到哪里**：`request.strategies`

**高层伪代码**：

```python
# ❌ 当前实现（Legacy Path）
request = BacktestRequest(
    symbol="ETH/USDT:USDT",
    timeframe="1h",
    start_time=start_time,
    end_time=end_time,
    mode="v3_pms",
    risk_overrides=risk_overrides,
    # strategies=None → Legacy Path
)

# ✅ 修正实现（Dynamic Strategy Path）
profile = BACKTEST_ETH_BASELINE_PROFILE
strategy_definition = profile.strategy.to_strategy_definition(
    strategy_id=f"{profile.name}_strategy",
    name=f"{profile.name}_strategy",
    market=profile.market,
)

request = BacktestRequest(
    symbol="ETH/USDT:USDT",
    timeframe="1h",
    start_time=start_time,
    end_time=end_time,
    mode="v3_pms",
    risk_overrides=risk_overrides,
    strategies=[strategy_definition],  # ✅ Dynamic Strategy Path
)
```

**关键点**：
- `profile.strategy.to_strategy_definition()` 会生成包含 `filters` 的 `StrategyDefinition`
- `filters` 中包含 `FilterConfig(type="atr", enabled=False, ...)`
- `FilterFactory.create()` 会读取 `enabled=False`，创建 `AtrFilterDynamic(enabled=False)`
- `AtrFilterDynamic.check()` 会直接返回 `passed=True, reason="filter_disabled"`

### 3.2 执行层（Execution Source of Truth）

**从哪里来**：`BACKTEST_ETH_BASELINE_PROFILE.execution`

**放到哪里**：`request.order_strategy`

**高层伪代码**：

```python
# ❌ 当前实现（依赖 runtime_overrides）
runtime_overrides = BacktestRuntimeOverrides(
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    breakeven_enabled=False,
)

# ✅ 修正实现（从 profile.execution 提供）
order_strategy = profile.execution.to_order_strategy(
    strategy_id=f"{profile.name}_execution",
    resolved_params=resolved_params,  # 可选，用于参数注入
)

request = BacktestRequest(
    ...
    order_strategy=order_strategy,  # ✅ 执行层真源
)
```

**关键点**：
- `profile.execution.to_order_strategy()` 会生成 `OrderStrategy` 对象
- 包含 `tp_targets=[1.0, 3.5]`、`tp_ratios=[0.5, 0.5]`、`breakeven_enabled=False`
- `BacktestConfigResolver.resolve()` 会优先使用 `request.order_strategy`（若存在）

### 3.3 参数层（Runtime Params）

**从哪里来**：脚本显式锁定

**放到哪里**：`runtime_overrides`

**高层伪代码**：

```python
# ✅ 修正实现（显式锁定 baseline 参数）
runtime_overrides = BacktestRuntimeOverrides(
    # 策略参数（baseline 锁定）
    ema_period=50,
    min_distance_pct=Decimal("0.005"),
    mtf_ema_period=60,
    # ❌ 不再传 max_atr_ratio=None（由 profile.strategy.filters.enabled=False 控制）

    # 订单参数（baseline 锁定）
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    breakeven_enabled=False,

    # 诊断参数
    allowed_directions=["LONG"],

    # 成本参数
    fee_rate=BNB9_FEE_RATE,
    slippage_rate=BNB9_SLIPPAGE,
    tp_slippage_rate=Decimal("0"),
)
```

**关键点**：
- `runtime_overrides` 仍显式锁定 baseline 参数，确保可复现性
- `max_atr_ratio` 不再传入，避免被 `resolve_decimal()` 丢弃
- `max_atr_ratio` 的控制权交给 `profile.strategy.filters.enabled=False`

### 3.4 完整接线图

```
┌─────────────────────────────────────────────────────────────┐
│                    Baseline Profile                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  BACKTEST_ETH_BASELINE_PROFILE                        │  │
│  │                                                       │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │ strategy = BacktestStrategyProfile               │  │  │
│  │  │   filters = [                                    │  │  │
│  │  │     FilterConfig(type="ema", enabled=True, ...)  │  │  │
│  │  │     FilterConfig(type="mtf", enabled=True, ...)  │  │  │
│  │  │     FilterConfig(type="atr", enabled=False, ...) │  │  │
│  │  │   ]                                              │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │                                                       │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │ execution = BacktestExecutionProfile             │  │  │
│  │  │   tp_targets = [1.0, 3.5]                        │  │  │
│  │  │   tp_ratios = [0.5, 0.5]                         │  │  │
│  │  │   breakeven_enabled = False                      │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    R2 Script                                 │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  request = BacktestRequest(                           │  │
│  │    symbol="ETH/USDT:USDT",                            │  │
│  │    timeframe="1h",                                    │  │
│  │    mode="v3_pms",                                     │  │
│  │    strategies=[profile.strategy.to_strategy_definition()],  │  │
│  │    order_strategy=profile.execution.to_order_strategy(),   │  │
│  │    risk_overrides=RiskConfig(max_total_exposure=2.0, ...) │  │
│  │  )                                                    │  │
│  │                                                       │  │
│  │  runtime_overrides = BacktestRuntimeOverrides(         │  │
│  │    ema_period=50,                                      │  │
│  │    min_distance_pct=0.005,                             │  │
│  │    mtf_ema_period=60,                                  │  │
│  │    allowed_directions=["LONG"],                        │  │
│  │    # ❌ 不传 max_atr_ratio=None                        │  │
│  │  )                                                    │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Backtester.run_backtest(request, runtime_overrides)         │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  v3_pms path                                          │  │
│  │    ↓                                                   │  │
│  │  kv_configs = cm.get_backtest_configs()                │  │
│  │    ↓                                                   │  │
│  │  resolved_params = resolve_backtest_params(            │  │
│  │    runtime_overrides=runtime_overrides,                │  │
│  │    request=request,                                    │  │
│  │    kv_configs=kv_configs,                              │  │
│  │  )                                                     │  │
│  │    ↓                                                   │  │
│  │  use_dynamic = request.strategies is not None          │  │
│  │  if use_dynamic:                                       │  │
│  │    runner = _build_dynamic_runner(                     │  │
│  │      request.strategies,                               │  │
│  │      resolved_params,                                  │  │
│  │    )                                                   │  │
│  │    ↓                                                   │  │
│  │  FilterFactory.create_chain(                           │  │
│  │    filters_config,                                     │  │
│  │    resolved_params=resolved_params,                    │  │
│  │  )                                                     │  │
│  │    ↓                                                   │  │
│  │  AtrFilterDynamic(enabled=False)                       │  │
│  │    ↓                                                   │  │
│  │  AtrFilterDynamic.check() → passed=True, reason="filter_disabled" │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 字段来源分类

### 4.1 必须由 Profile 提供

| 字段 | Profile 字段 | 说明 |
|------|-------------|------|
| **strategy_definition** | `profile.strategy.to_strategy_definition()` | 包含 filters（含 ATR `enabled=False`） |
| **ATR filter enabled** | `profile.strategy.filters[type="atr"].enabled` | 核心 baseline 语义 |
| **tp_targets** | `profile.execution.tp_targets` | 订单执行参数 |
| **tp_ratios** | `profile.execution.tp_ratios` | 订单执行参数 |
| **breakeven_enabled** | `profile.execution.breakeven_enabled` | 订单执行参数 |
| **initial_stop_loss_rr** | `profile.execution.initial_stop_loss_rr` | 订单执行参数 |

### 4.2 可以由脚本覆盖

| 字段 | 脚本字段 | 说明 |
|------|---------|------|
| **ema_period** | `runtime_overrides.ema_period` | 策略参数（搜索用） |
| **min_distance_pct** | `runtime_overrides.min_distance_pct` | 策略参数（搜索用） |
| **mtf_ema_period** | `runtime_overrides.mtf_ema_period` | 策略参数（搜索用） |
| **allowed_directions** | `runtime_overrides.allowed_directions` | 策略参数（搜索用） |
| **fee_rate** | `runtime_overrides.fee_rate` | 成本参数（搜索用） |
| **slippage_rate** | `runtime_overrides.slippage_rate` | 成本参数（搜索用） |
| **tp_slippage_rate** | `runtime_overrides.tp_slippage_rate` | 成本参数（搜索用） |

### 4.3 禁止由脚本覆盖

| 字段 | 原因 |
|------|------|
| **max_atr_ratio** | 由 `profile.strategy.filters[type="atr"].enabled=False` 控制，脚本不应覆盖 |
| **ATR filter enabled** | baseline 核心语义，脚本不应覆盖 |

---

## 5. 2024 Smoke 最终验证方案

### 5.1 配置

| 参数 | 值 | 来源 |
|------|-----|------|
| **year** | 2024 | 固定 |
| **exposure** | 2.0 | `request.risk_overrides.max_total_exposure` |
| **risk** | 1.0% | `request.risk_overrides.max_loss_percent` |
| **profile** | backtest_eth_baseline | `BACKTEST_ETH_BASELINE_PROFILE` |
| **strategy_definition** | profile.strategy.to_strategy_definition() | 从 profile 生成 |
| **order_strategy** | profile.execution.to_order_strategy() | 从 profile 生成 |

### 5.2 验证字段

#### 1. ATR filter 确实 disabled

| 验证项 | 期望值 | 验证方式 |
|--------|--------|---------|
| `strategy_definition.filters[type="atr"].enabled` | **False** | 打印 `resolved_config.strategy_definition.filters` |
| `AtrFilterDynamic._enabled` | **False** | 打印 filter 实例的 `_enabled` 属性 |

#### 2. TP 结构正确

| 验证项 | 期望值 | 验证方式 |
|--------|--------|---------|
| `order_strategy.tp_targets` | **[1.0, 3.5]** | 打印 `resolved_config.order_strategy.tp_targets` |
| `order_strategy.tp_ratios` | **[0.5, 0.5]** | 打印 `resolved_config.order_strategy.tp_ratios` |
| `order_strategy.breakeven_enabled` | **False** | 打印 `resolved_config.order_strategy.breakeven_enabled` |

#### 3. LONG-only

| 验证项 | 期望值 | 验证方式 |
|--------|--------|---------|
| `params.allowed_directions` | **["LONG"]** | 打印 `resolved_config.params.allowed_directions` |

#### 4. Trades 回到几十笔量级

| 验证项 | 期望值 | 验证标准 |
|--------|--------|---------|
| `trades` | **几十笔** | `< 100` |

#### 5. PnL 回到正收益区间

| 验证项 | 期望值 | 验证标准 |
|--------|--------|---------|
| `pnl` | **明显正收益** | `> 0` |

### 5.3 验收标准

```
✅ PASS:
  - ATR filter enabled=False
  - tp_targets=[1.0, 3.5], tp_ratios=[0.5, 0.5], breakeven_enabled=False
  - allowed_directions=["LONG"]
  - trades < 100（几十笔量级）
  - pnl > 0（明显正收益）

❌ FAIL:
  - ATR filter enabled=True
  - trades >= 100（仍是数百笔）
  - pnl <= 0（明显负收益）
  → 立即停止，不继续全量搜索
```

---

## 6. 总结

### 6.1 一句话结论

**R2 应通过 `request.strategies` 注入 baseline profile 的 `strategy_definition`（含 ATR filter `enabled=False`），并通过 `request.order_strategy` 注入 execution 参数，而非依赖 `runtime_overrides.max_atr_ratio=None`**

### 6.2 推荐路径

- **Dynamic Strategy Path**（`request.strategies is not None`）
- 原因：支持 `StrategyDefinition` 中的 `filters.enabled` 字段，ATR filter 可被正确关闭

### 6.3 最小接线方案

| 层级 | 从哪里来 | 放到哪里 |
|------|---------|---------|
| **策略层** | `profile.strategy.to_strategy_definition()` | `request.strategies` |
| **执行层** | `profile.execution.to_order_strategy()` | `request.order_strategy` |
| **参数层** | 脚本显式锁定 | `runtime_overrides`（不含 `max_atr_ratio`） |
| **风控层** | `RiskConfig(max_total_exposure=2.0, ...)` | `request.risk_overrides` |

### 6.4 下一步

1. **修改 `scripts/run_r2a_baseline_smoke.py`**
   - 导入 `BACKTEST_ETH_BASELINE_PROFILE`
   - 使用 `profile.strategy.to_strategy_definition()` 生成 `strategies`
   - 使用 `profile.execution.to_order_strategy()` 生成 `order_strategy`
   - 移除 `runtime_overrides` 中的 `max_atr_ratio=None`

2. **修改 `scripts/run_r2_capital_allocation_search.py`**
   - 同上

3. **运行 2024 Smoke Test**
   - 验证 ATR filter enabled=False
   - 验证 TP 结构正确
   - 验证 trades 回到几十笔量级
   - 验证 pnl 回到正收益区间

---

*方案设计完成时间: 2026-04-29*
*方案状态: ✅ 待执行*
*下一步: 修改 R2 脚本，运行 2024 Smoke Test*