# R2c Baseline Profile 接入验证报告

> **日期**: 2026-04-29
> **任务**: 验证 R2 是否可以直接引用 baseline profile 保证 baseline 语义一致
> **结论**: ✅ **baseline profile 语义正确，但 R2 未正确引用**

---

## 1. 一句话结论

**R2 下一步应改为基于 baseline profile，而非手工设置 `runtime_overrides.max_atr_ratio=None`**

---

## 2. 当前 baseline profile 核对表

| 字段 | baseline profile 值 | 期望值 | 是否一致 |
|------|---------------------|--------|---------|
| **symbol** | ETH/USDT:USDT | ETH/USDT:USDT | ✅ 一致 |
| **timeframe** | 1h | 1h | ✅ 一致 |
| **allowed_directions** | [Direction.LONG] | LONG-only | ✅ 一致 |
| **ema period** | 50 | 50 | ✅ 一致 |
| **min_distance_pct** | 0.005 | 0.005 | ✅ 一致 |
| **mtf ema period** | 60 | 60 | ✅ 一致 |
| **ATR filter** | enabled=False | disabled | ✅ 一致 |
| **tp_targets** | [1.0, 3.5] | [1.0, 3.5] | ✅ 一致 |
| **tp_ratios** | [0.5, 0.5] | [0.5, 0.5] | ✅ 一致 |
| **breakeven_enabled** | False | False | ✅ 一致 |

**结论**: ✅ `BACKTEST_ETH_BASELINE_PROFILE` 已具备正确 baseline 语义

---

## 3. R2 当前接入缺口

### 3.1 R2 脚本当前实现

```python
# scripts/run_r2a_baseline_smoke.py
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
```

### 3.2 缺口分析

| 问题 | 影响 | 根因 |
|------|------|------|
| **未引用 baseline profile** | 所有参数手工设置，易遗漏 | R2 脚本直接构建 `Backtester`，未使用 `BacktestConfigResolver` |
| **`max_atr_ratio=None` 被丢弃** | 回退到默认值 0.01 | `resolve_decimal()` 无法区分"未传入"和"显式传入 None" |
| **`BASELINE_RUNTIME_OVERRIDES` 不一致** | `max_atr_ratio=0.01`，与 profile `enabled=False` 冲突 | `research_control_plane.py:35` 硬编码了错误值 |

### 3.3 当前 R2 走的路径

```
R2 脚本
  ↓ 直接构建 Backtester（未使用 BacktestConfigResolver）
  ↓ 传入 runtime_overrides.max_atr_ratio=None
  ↓ resolve_decimal() 检查 "if override_val is not None"
  ↓ None 不满足条件 → 跳过
  ↓ kv_configs 无 strategy.atr.max_atr_ratio（ATR filter disabled）
  ↓ 回退到 BACKTEST_PARAM_DEFAULTS["max_atr_ratio"] = 0.01
  ↓ ATR 过滤器被意外启用
  ↓ trades 飙升、PnL 失真
```

---

## 4. 最小修复方案

### 方案 A（推荐，脚本层）：引用 baseline profile

**核心思路**：R2 脚本不再手工设置 `runtime_overrides`，改为引用 baseline profile

**修改方向**：

```python
# ❌ 当前实现（手工设置 runtime_overrides）
backtester = Backtester(gateway)
report = await backtester.run_backtest(
    request=request,
    runtime_overrides=runtime_overrides,  # ❌ max_atr_ratio=None 被丢弃
)

# ✅ 修正实现（引用 baseline profile）
resolver = BacktestConfigResolver(profile_provider=DEFAULT_BACKTEST_PROFILE_PROVIDER)
resolved_config = await resolver.resolve(
    profile_name="backtest_eth_baseline",
    request=request,
    runtime_overrides=None,  # ✅ 不传入 max_atr_ratio
)
# risk / exposure 只通过 request.risk_overrides 搜索
# baseline strategy / execution / filter 由 profile 提供
```

**修改文件**：
- `scripts/run_r2a_baseline_smoke.py`
- `scripts/run_r2_capital_allocation_search.py`

**修改内容**：
1. 导入 `BacktestConfigResolver` 和 `DEFAULT_BACKTEST_PROFILE_PROVIDER`
2. 使用 `resolver.resolve()` 替代直接构建 `Backtester`
3. 移除 `runtime_overrides` 中的 `max_atr_ratio=None`
4. 只通过 `request.risk_overrides` 设置 exposure 和 risk

### 方案 B（需谨慎，src 层）：修改参数解析链

**修改 `resolve_decimal()` 支持显式 None 语义**

这属于核心代码修复，需要：
1. 区分「未传入」和「显式传入 None」
2. 可能需要引入 sentinel 值（如 `UNSET = object()`）
3. 影响面广，需全面回归测试

**暂不推荐**：先确认方案 A 是否可行。

### 方案 C（补充，src 层）：修复 `BASELINE_RUNTIME_OVERRIDES`

**修改 `research_control_plane.py` 中的 `BASELINE_RUNTIME_OVERRIDES`**

```python
# ❌ 当前实现
BASELINE_RUNTIME_OVERRIDES = BacktestRuntimeOverrides(
    max_atr_ratio=Decimal("0.01"),  # ❌ 与 profile enabled=False 冲突
    min_distance_pct=Decimal("0.005"),
    ema_period=50,
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    breakeven_enabled=False,
    allowed_directions=["LONG"],
)

# ✅ 修正实现（移除 max_atr_ratio）
BASELINE_RUNTIME_OVERRIDES = BacktestRuntimeOverrides(
    min_distance_pct=Decimal("0.005"),
    ema_period=50,
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],
    tp_targets=[Decimal("1.0"), Decimal("3.5")],
    breakeven_enabled=False,
    allowed_directions=["LONG"],
)
```

**修改文件**：`src/application/research_control_plane.py:35`

**修改内容**：移除 `max_atr_ratio=Decimal("0.01")`

---

## 5. 2024 Smoke 验证方案

### 5.1 配置

| 参数 | 值 | 来源 |
|------|-----|------|
| **year** | 2024 | 固定 |
| **exposure** | 2.0 | `request.risk_overrides.max_total_exposure` |
| **risk** | 1.0% | `request.risk_overrides.max_loss_percent` |
| **profile** | backtest_eth_baseline | `resolver.resolve()` |

### 5.2 验证字段

#### 1. Resolved Params

| 字段 | 期望值 | 验证方式 |
|------|--------|---------|
| ema_period | 50 | `resolved_config.params.ema_period` |
| min_distance_pct | 0.005 | `resolved_config.params.min_distance_pct` |
| mtf_ema_period | 60 | `resolved_config.params.mtf_ema_period` |
| max_atr_ratio | **None 或不存在** | `resolved_config.params.max_atr_ratio` 应为 None 或不触发 ATR 过滤 |
| tp_targets | [1.0, 3.5] | `resolved_config.params.tp_targets` |
| tp_ratios | [0.5, 0.5] | `resolved_config.params.tp_ratios` |
| breakeven_enabled | False | `resolved_config.params.breakeven_enabled` |
| allowed_directions | ["LONG"] | `resolved_config.params.allowed_directions` |

#### 2. Strategy Definition Filters

| Filter | 期望状态 | 验证方式 |
|--------|---------|---------|
| **ATR filter** | **enabled=False** | `resolved_config.strategy_definition.filters` 中 `type=atr` 的 `enabled` 字段 |
| EMA filter | enabled=True | `resolved_config.strategy_definition.filters` 中 `type=ema` 的 `enabled` 字段 |
| MTF filter | enabled=True | `resolved_config.strategy_definition.filters` 中 `type=mtf` 的 `enabled` 字段 |

#### 3. Order Strategy

| 字段 | 期望值 | 验证方式 |
|------|--------|---------|
| tp_levels | 2 | `resolved_config.order_strategy.tp_levels` |
| tp_targets | [1.0, 3.5] | `resolved_config.order_strategy.tp_targets` |
| tp_ratios | [0.5, 0.5] | `resolved_config.order_strategy.tp_ratios` |
| initial_stop_loss_rr | -1.0 | `resolved_config.order_strategy.initial_stop_loss_rr` |
| breakeven_enabled | False | `resolved_config.order_strategy.breakeven_enabled` |

#### 4. Trades 数量

| 指标 | 期望值 | 验证标准 |
|------|--------|---------|
| **trades** | **几十笔** | `< 100` |

#### 5. PnL

| 指标 | 期望值 | 验证标准 |
|------|--------|---------|
| **pnl** | **明显正收益** | `> 0` |

### 5.3 验收标准

```
✅ PASS:
  - resolved_config.params.max_atr_ratio 为 None 或 ATR filter enabled=False
  - trades < 100（几十笔量级）
  - pnl > 0（明显正收益）

❌ FAIL:
  - trades >= 100（仍是数百笔）
  - pnl <= 0（明显负收益）
  → 立即停止，不继续全量搜索
```

---

## 6. 总结

### 6.1 一句话结论

**R2 下一步应改为基于 baseline profile，而非手工设置 `runtime_overrides.max_atr_ratio=None`**

### 6.2 下一步行动

1. **修改 `scripts/run_r2a_baseline_smoke.py`**
   - 导入 `BacktestConfigResolver` 和 `DEFAULT_BACKTEST_PROFILE_PROVIDER`
   - 使用 `resolver.resolve()` 替代直接构建 `Backtester`
   - 移除 `runtime_overrides` 中的 `max_atr_ratio=None`
   - 只通过 `request.risk_overrides` 设置 exposure 和 risk

2. **修改 `scripts/run_r2_capital_allocation_search.py`**
   - 同上

3. **修复 `src/application/research_control_plane.py:35`**
   - 移除 `BASELINE_RUNTIME_OVERRIDES` 中的 `max_atr_ratio=Decimal("0.01")`

4. **运行 2024 Smoke Test**
   - 验证 resolved params、strategy definition filters、order strategy、trades、pnl

---

*验证完成时间: 2026-04-29*
*验证结果: ✅ baseline profile 语义正确，但 R2 未正确引用*
*下一步: 修改 R2 脚本引用 baseline profile*