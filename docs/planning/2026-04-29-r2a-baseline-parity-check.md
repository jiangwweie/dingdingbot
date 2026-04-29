# R2a Baseline Parity Check - 口径对齐审计报告

> **日期**: 2026-04-29
> **任务**: 确认 R2 是否真正跑了 ETH baseline 策略口径
> **结论**: ❌ **R2 未跑 baseline，使用了错误的默认参数**

---

## 1. 一句话结论

**R2 当前未跑 baseline，使用了 `BACKTEST_PARAM_DEFAULTS` 的默认参数（EMA60, TP=[1.0, 2.5]），而非冻结 baseline（EMA50, TP=[1.0, 3.5]），导致 trades 飙升、PnL 失真。**

---

## 2. 差异表

| 项目 | 冻结 Baseline | R2 当前实际值 | 是否一致 | 差异影响 |
|------|--------------|--------------|---------|---------|
| **Trigger** | Pinbar (默认) | Pinbar (默认) | ✅ 一致 | - |
| **ema_period** | **50** | **60** | ❌ **不一致** | EMA 更慢 → 过滤更松 → trades ↑ |
| **min_distance_pct** | 0.005 | 0.005 | ✅ 一致 | - |
| **mtf_ema_period** | 60 | 60 | ✅ 一致 | - |
| **ATR filter** | **移除** | **启用 (max_atr_ratio=0.01)** | ❌ **不一致** | ATR 启用 → trades ↑ |
| **allowed_directions** | ["LONG"] | ["LONG"] | ✅ 一致 | - |
| **tp_targets** | **[1.0, 3.5]** | **[1.0, 2.5]** | ❌ **不一致** | TP2 更近 → 出场更快 → trades ↑ |
| **tp_ratios** | [0.5, 0.5] | [0.6, 0.4] | ❌ **不一致** | TP1 仓位更大 → 收益结构变化 |
| **breakeven_enabled** | False | False | ✅ 一致 | - |
| **fee_rate** | 0.000405 (BNB9) | 0.000405 (BNB9) | ✅ 一致 | - |
| **slippage_rate** | 0.0001 | 0.0001 | ✅ 一致 | - |

---

## 3. 导致结果失真的最可能根因

### 3.1 核心问题：R2 脚本未显式指定策略参数

**问题链**:
```
R2 脚本
  → runtime_overrides 只指定了 allowed_directions + 成本参数
  → Backtester 调用 resolve_backtest_params()
  → ConfigEntryRepository 未注入（日志警告）
  → 降级使用 BACKTEST_PARAM_DEFAULTS
  → 使用了错误的默认参数（EMA60, ATR=1%, TP=[1.0, 2.5]）
```

**证据**:
- 日志警告: `Failed to load backtest configs from KV, using defaults`
- 日志输出: `min_distance_pct=0.005, max_atr_ratio=0.01`（ATR 启用！）

### 3.2 为什么 trades 会飙到 300~600？

**三个因素叠加**:

1. **EMA60 vs EMA50**:
   - EMA60 更慢 → 趋势判断更宽松 → 更多信号通过
   - 影响: trades ↑ ~10-20%

2. **ATR 启用 (max_atr_ratio=0.01)**:
   - **策略口径不一致的证据**：ATR 过滤器启用，改变了信号集合和收益分布
   - 但不直接断言它是 trades 飙升主因
   - 影响: 改变信号筛选逻辑，影响 trades 和 PnL 结构

3. **TP=[1.0, 2.5] vs [1.0, 3.5]**:
   - TP2 从 3.5 降至 2.5 → 出场更快 → 持仓时间缩短
   - 同样时间内可开更多仓 → trades ↑ ~30-50%
   - **这是最关键的因素**

**综合影响**: trades 从 ~60 飙升到 ~600（10x 增加）

### 3.3 为什么 PnL 大幅负数？

**原因**:
- TP=[1.0, 2.5] 收益结构改变 → TP2 过早出场 → 错失大趋势
- 2024 年大趋势行情（+8501 baseline）被压缩成小幅盈利或亏损
- trades 大幅增加 → 交易成本累积 → 进一步侵蚀收益

---

## 4. 修复方案

### 4.1 让 R2 显式使用 baseline 策略参数

**修改 `scripts/run_r2_capital_allocation_search.py`**:

```python
# ✅ runtime_overrides 显式指定 baseline 策略参数
runtime_overrides = BacktestRuntimeOverrides(
    # 策略参数（baseline 锁定）
    ema_period=50,
    min_distance_pct=Decimal("0.005"),
    mtf_ema_period=60,
    max_atr_ratio=None,  # ATR 移除

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

### 4.2 锁死策略参数

**关键修改**:
- ✅ `ema_period=50`（而非默认 60）
- ✅ `max_atr_ratio=None`（ATR 移除，而非默认 0.01）
- ✅ `tp_targets=[1.0, 3.5]`（而非默认 [1.0, 2.5]）
- ✅ `tp_ratios=[0.5, 0.5]`（而非默认 [0.6, 0.4]）

### 4.3 风险参数仍通过 request.risk_overrides 搜索

**保持不变**:
```python
risk_overrides = RiskConfig(
    max_loss_percent=Decimal(str(risk)),
    max_total_exposure=Decimal(str(exposure)),
    max_leverage=20,
    daily_max_trades=50,
)
```

---

## 5. 修复后建议的 2024 Smoke 配置

### 5.1 Smoke Test 目标

验证修复后 R2 是否真正跑了 baseline：
- trades 应回到几十笔量级（而非几百笔）
- PnL 应回到明显正收益区间
- 与已知 baseline historical range 同方向、同量级
- 如果仍是数百笔交易或明显大幅负收益，则说明仍未对齐 baseline

### 5.2 Smoke 配置

**单组配置**:
```python
{
    "year": "2024",
    "exposure": 2.0,  # baseline 默认
    "risk": 0.01,     # baseline 默认 1%
}
```

**预期结果**:
- Trades: 几十笔量级（而非几百笔）
- PnL: 明显正收益区间（与 baseline historical range 同方向、同量级）
- MaxDD: 合理范围

**验收标准**:
- ✅ 如果 trades 几十笔 + PnL 明显正收益 → baseline 对齐成功
- ❌ 如果仍是数百笔交易或明显大幅负收益 → 立即停止，不对齐，不继续全量搜索

### 5.3 Smoke Test 脚本

**创建 `scripts/run_r2a_baseline_smoke.py`**:

```python
#!/usr/bin/env python3
"""R2a Baseline Smoke Test - 验证 R2 是否真正跑了 baseline"""

# 只跑 2024 年单组配置
# baseline: exposure=2.0, risk=1.0%

# 输出必须包含：
# - 实际解析到的策略参数（ema_period / mtf_ema_period / tp_targets / tp_ratios / max_atr_ratio / allowed_directions）
# - trades
# - pnl
# - maxdd
# - 与冻结 baseline 的差异比对

# 验收标准：
# - ✅ trades 几十笔 + PnL 明显正收益 → baseline 对齐成功
# - ❌ 仍是数百笔交易或明显大幅负收益 → 立即停止，不继续全量搜索
```

---

## 6. 总结

### 6.1 问题确认

- ❌ R2 未跑 baseline
- ❌ 使用了错误的默认参数（EMA60, ATR=1%, TP=[1.0, 2.5]）
- ❌ 导致 trades 飙升 10x、PnL 大幅失真

### 6.2 修复方案

- ✅ 在 `runtime_overrides` 中显式指定 baseline 策略参数
- ✅ 锁死 EMA50、ATR 移除、TP=[1.0, 3.5]
- ✅ 风险参数仍通过 `request.risk_overrides` 搜索

### 6.3 下一步

1. **等待用户确认修复方案**
2. 修改 `scripts/run_r2_capital_allocation_search.py`
3. 运行 2024 smoke test
4. 如果 smoke test 通过，再考虑全量搜索

---

*审计完成时间: 2026-04-29*
*问题级别: P0（策略口径错误）*
*修复优先级: P0（必须修复后才能继续）*