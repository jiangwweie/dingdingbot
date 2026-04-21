# 回测参数完整清单

> **Last updated**: 2026-04-22
> **Status**: ETH 1h LONG-only 最优配置已锁定

---

## 1. 固定参数（强先验，未搜索）

| 参数 | 值 | 来源 | 说明 |
|------|-----|------|------|
| symbol | ETH/USDT:USDT | 回测配置 | 交易对 |
| timeframe | 1h | 回测配置 | K线周期 |
| mode | v3_pms | 回测配置 | 撮合引擎模式 |
| direction | LONG-only | 回测配置 | 只做多 |
| breakeven_enabled | False | 搜索锁定 | 不启用保本止损 |
| tp_ratios | [0.5, 0.5] | 搜索调整 | 两级止盈比例 |
| tp_targets | [1.0, 3.5] | 搜索调整 | 两级止盈目标（R倍数） |
| slippage_rate | 0.001 | 代码默认 | 入场滑点 0.1% |
| tp_slippage_rate | 0.0005 | 代码默认 | 止盈滑点 0.05% |
| fee_rate | 0.0004 | 代码默认 | 手续费 0.04% |
| initial_balance | 10000 USDT | 代码默认 | 初始资金 |

---

## 2. 搜索参数（弱先验）

| 参数 | 搜索范围 | 系统默认 | 最优值 | 敏感性 | 结论 |
|------|----------|----------|--------|--------|------|
| ema_period | 30→150 | 60 | **50** | 高敏感 | 更快响应趋势 |
| max_atr_ratio | 0.004→0.025 | 0.01 | **移除** | 不敏感 | 已验证冗余 |
| min_distance_pct | 0.005→0.012 | 0.005 | **0.005** | 中等敏感 | 与默认一致 |

---

## 3. 未搜索参数（使用默认值）

### 3.1 Pinbar 形态参数

| 参数 | 默认值 | 来源 | 说明 |
|------|--------|------|------|
| pinbar_min_wick_ratio | 0.6 | CoreConfig | 影线占比下限 |
| pinbar_max_body_ratio | 0.3 | CoreConfig | 实体占比上限 |
| pinbar_body_position_tolerance | 0.1 | CoreConfig | 实体位置容差 |

### 3.2 MTF 参数

| 参数 | 默认值 | 来源 | 说明 |
|------|--------|------|------|
| mtf_ema_period | 60 | SystemConfig | 高周期 EMA 周期 |
| mtf_mapping | {"15m":"1h","1h":"4h","4h":"1d","1d":"1w"} | 代码默认 | 周期映射 |

### 3.3 风控参数

| 参数 | 默认值 | 来源 | 说明 |
|------|--------|------|------|
| max_loss_percent | 1% | RiskConfig | 单笔最大损失 |
| max_leverage | 10 | RiskConfig | 最大杠杆 |
| max_total_exposure | 80% | RiskConfig | 最大总敞口 |
| max_position_percent | 20% | RiskConfig | 单次最大仓位 |
| daily_max_loss | 5% | RiskConfig | 每日最大回撤 |
| daily_max_trades | 50 | RiskConfig | 每日最大交易次数 |
| min_balance | 100 USDT | RiskConfig | 最低余额保留 |

### 3.4 其他参数

| 参数 | 默认值 | 来源 | 说明 |
|------|--------|------|------|
| signal_cooldown_seconds | 14400 | CoreConfig | 信号冷却时间（4小时） |
| warmup_history_bars | 100 | CoreConfig | EMA 预热 K 线数 |

---

## 4. 成本配置对比

| 配置 | slippage_rate | tp_slippage_rate | fee_rate | 说明 |
|------|---------------|------------------|----------|------|
| **stress（悲观）** | 0.001 | 0.0005 | 0.0004 | 保守估算 |
| **BNB9（实盘推荐）** | 0.0001 | 0 | 0.000405 | BNB 9折手续费 |

---

## 5. 最优配置完整清单

```python
# ETH/USDT:USDT 1h LONG-only 最优配置
{
    # === 回测框架 ===
    "symbol": "ETH/USDT:USDT",
    "timeframe": "1h",
    "mode": "v3_pms",
    "initial_balance": Decimal("10000"),

    # === 成本参数（BNB9 实盘口径）===
    "slippage_rate": Decimal("0.0001"),      # 0.01%
    "tp_slippage_rate": Decimal("0"),        # 0%
    "fee_rate": Decimal("0.000405"),         # 0.0405%

    # === 策略参数（搜索优化）===
    "ema_period": 50,                         # 系统60 → 优化50
    "min_distance_pct": Decimal("0.005"),    # 与系统一致
    "max_atr_ratio": None,                    # 移除（冗余）

    # === 止盈参数（搜索调整）===
    "tp_ratios": [Decimal("0.5"), Decimal("0.5")],   # 系统[0.6,0.4]
    "tp_targets": [Decimal("1.0"), Decimal("3.5")],  # 系统[1.0,2.5]
    "breakeven_enabled": False,

    # === MTF 参数（未搜索）===
    "mtf_ema_period": 60,
    "mtf_mapping": {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"},

    # === Pinbar 参数（未搜索）===
    "pinbar_min_wick_ratio": Decimal("0.6"),
    "pinbar_max_body_ratio": Decimal("0.3"),
    "pinbar_body_position_tolerance": Decimal("0.1"),

    # === 风控参数（未搜索）===
    "max_loss_percent": Decimal("0.01"),     # 1%
    "max_leverage": 10,
    "max_total_exposure": Decimal("0.8"),    # 80%
}
```

---

## 6. 参数调整汇总

| 参数 | 系统默认 | 最优配置 | 变化 | 影响 |
|------|----------|----------|------|------|
| ema_period | 60 | **50** | ↓ 17% | 更快响应趋势 |
| max_atr_ratio | 0.01 | **移除** | - | 简化逻辑 |
| min_distance_pct | 0.005 | 0.005 | = | 无变化 |
| tp_ratios | [0.6, 0.4] | **[0.5, 0.5]** | 调整 | 第二笔更激进 |
| tp_targets | [1.0, 2.5] | **[1.0, 3.5]** | ↑ 40% | 第二目标更远 |

---

## 7. 性能表现

### BNB9 成本下（推荐实盘口径）

| 年份 | PnL | 交易数 | Max DD | Sharpe |
|------|-----|--------|--------|--------|
| 2023 | -4437 | 60 | 49.2% | -2.63 |
| 2024 | **+5952** | 80 | 15.8% | 1.91 |
| 2025 | **+4399** | 77 | 11.6% | 2.01 |
| **总计** | **+5913** | 217 | - | 0.43 |

### stress 成本下（悲观口径）

| 年份 | PnL | 交易数 | Max DD | Sharpe |
|------|-----|--------|--------|--------|
| 2024 | +5168 | 82 | 17.6% | 1.69 |
| 2025 | +1645 | 75 | 13.3% | 0.91 |

---

## 8. 搜索历史

| 轮次 | ema_period | max_atr_ratio | min_distance_pct | 结论 |
|------|------------|---------------|------------------|------|
| 第一轮 | [90, 150] | [0.004, 0.008] | [0.005, 0.012] | ema=120 最优 |
| 第二轮 | [110, 130] | [0.005, 0.008] | [0.007, 0.008] | ema=120, dist=0.007 |
| EMA 60-100 | [60, 100] | 固定 0.006 | 固定 0.007 | ema=60 更优 |
| 稳健性 | [55, 65] | 固定 0.006 | [0.006, 0.008] | ema=55 可能更优 |
| 大区间 | [30, 50, 70, 100] | [0.008, 0.012, 0.018, 0.025] | [0.005, 0.008, 0.012] | **ema=50 最优** |

---

## 9. 跨币种/跨周期验证结果

| 币种/周期 | 可行解 | 结论 |
|-----------|--------|------|
| **ETH 1h** | **有** | ✅ 唯一可行，最优配置已锁定 |
| ETH 4h | 0/48 | ❌ 交易太少 (~17/年) |
| ETH 15m | 0/48 | ❌ 交易过多 (~140/年)，信号质量差 |
| BTC 1h | 0/48 | ❌ 2024 全负 |
| SOL 1h | 0/48 | ❌ 两年皆负 |

---

## 10. 关键验证结论

1. **ATR 过滤器冗余**：有无 ATR 结果完全相同，可安全移除
2. **2023 失败非出场问题**：测试 4 种出场变体全部恶化，是市场环境不匹配
3. **参数敏感性**：ema_period 高敏感，max_atr_ratio 不敏感，min_distance_pct 中等敏感
4. **币种/周期适用性**：仅 ETH 1h 适用
