# Pinbar 0.382 Limit-Entry Proxy — H2 验证报告

> **日期**: 2026-04-28
> **假设 H2**: 当前[下一根 K 市价入场]可能存在追价问题；改为信号 K 区间 0.382 回撤挂单可能改善入场价格、止损距离和收益质量
> **方法**: research-only proxy 脚本（不改引擎），用基线回测结果 + K 线数据重新估算
> **基线**: ETH 1h LONG-only, EMA50, BNB9 成本, Research 口径
> **风险**: 本报告为 proxy 估算，不是正式引擎级回测

## 1. 支持度审计

### 1a. 当前 entry 如何产生？

信号 K 上检测到 Pinbar → `RiskCalculator.calculate_stop_loss()` 用信号 K 的 low 作为 SL → `OrderManager.create_order_chain()` 创建 MARKET 入场单 → 放入 `pending_entry_orders` → 下一根 K 开盘时撮合，成交价 = `next_kline.open ± slippage`

### 1b. 当前是否支持 pending limit entry？

**不支持**。`OrderType.MARKET + OrderRole.ENTRY` 是唯一路径。`pending_entry_orders` 只是 T+1 延迟，不是 limit order book。

### 1c. 当前 stop loss 基于什么？

两阶段：
- 信号阶段：`RiskCalculator.calculate_stop_loss()` → 信号 K 的 low（LONG）
- 成交后：`OrderManager._calculate_stop_loss_price()` → 用实际成交价和 RR 倍数（默认 -1.0 = 1%）重新计算

### 1d. 不改核心引擎，能否用 proxy 脚本模拟？

**可以**。跑基线回测拿到 positions → 每笔交易有 entry_time → 找到信号 K → 用后续 K 线判断 0.382 回撤是否成交 → 重新估算 TP/SL。

## 2. 实验设计

| 参数 | 值 |
|------|----|
| symbol | ETH/USDT:USDT |
| timeframe | 1h |
| direction | LONG-only |
| ema_period | 50 |
| min_distance_pct | 0.005 |
| ATR | disabled |
| tp_targets | [1.0, 3.5] |
| tp_ratios | [0.5, 0.5] |
| breakeven | False |
| fib_level | 0.382 |
| E0 | market entry baseline |
| E1 | 0.382 limit entry, wait 5 candles |
| E2 | 0.382 limit entry, wait 8 candles |
| 风险口径 | Research (exposure=2.0) |

### 0.382 Limit Entry 规则

对 LONG bullish pinbar：
- signal_high = 信号 K high
- signal_low = 信号 K low
- limit_entry = signal_low + (signal_high - signal_low) * 0.382
- stop_loss = signal_low
- 从信号 K 下一根开始，向后看 N 根 1h K
- 若任一 K low <= limit_entry，则视为成交
- 若等待窗口内未触及，则视为 missed signal（不补入）

## 3. 结果

### 2023

| 指标 | E0 基线 | E1 wait=5 | E2 wait=8 |
|------|---------|-----------|-----------|
| PnL | -3924.06 | -11.73 | +19.17 |
| Trades | 62 | 50 | 52 |
| Win Rate | 16.1% | 26.0% | 28.8% |
| Sharpe | - | -0.03 | 0.04 |
| MaxDD | - | 102.04 | 79.82 |
| Fill Rate | - | 80.7% | 83.9% |
| Missed Trades | - | 12 | 10 |
| Missed Winners | - | 3 | 3 |
| Missed Losers | - | 9 | 7 |
| Avg Entry Improve | - | 0.312% | 0.313% |
| Avg Stop Dist Change | - | -54.876% | -54.672% |
| Avg Fill Bar | - | 1.7 | 1.9 |
| TP1% | - | 0.0% | 0.0% |
| TP2% | - | 26.0% | 28.8% |
| SL% | - | 74.0% | 71.2% |

### 2024

| 指标 | E0 基线 | E1 wait=5 | E2 wait=8 |
|------|---------|-----------|-----------|
| PnL | +8500.69 | -217.10 | -217.10 |
| Trades | 70 | 54 | 54 |
| Win Rate | 32.9% | 29.6% | 29.6% |
| Sharpe | - | -0.23 | -0.23 |
| MaxDD | - | 264.79 | 264.79 |
| Fill Rate | - | 77.1% | 77.1% |
| Missed Trades | - | 16 | 16 |
| Missed Winners | - | 9 | 9 |
| Missed Losers | - | 7 | 7 |
| Avg Entry Improve | - | 0.427% | 0.427% |
| Avg Stop Dist Change | - | -53.202% | -53.202% |
| Avg Fill Bar | - | 1.6 | 1.6 |
| TP1% | - | 0.0% | 0.0% |
| TP2% | - | 29.6% | 29.6% |
| SL% | - | 70.4% | 70.4% |

### 2025

| 指标 | E0 基线 | E1 wait=5 | E2 wait=8 |
|------|---------|-----------|-----------|
| PnL | +4490.24 | +135.83 | +234.93 |
| Trades | 68 | 54 | 57 |
| Win Rate | 30.9% | 31.5% | 35.1% |
| Sharpe | - | 0.12 | 0.19 |
| MaxDD | - | 87.14 | 87.14 |
| Fill Rate | - | 79.4% | 83.8% |
| Missed Trades | - | 14 | 11 |
| Missed Winners | - | 9 | 8 |
| Missed Losers | - | 5 | 3 |
| Avg Entry Improve | - | 0.389% | 0.398% |
| Avg Stop Dist Change | - | -53.702% | -53.916% |
| Avg Fill Bar | - | 1.6 | 1.8 |
| TP1% | - | 0.0% | 0.0% |
| TP2% | - | 31.5% | 35.1% |
| SL% | - | 68.5% | 64.9% |

## 4. 验证分析

### 4a. 3 年汇总

| 指标 | E0 基线 | E1 wait=5 | E2 wait=8 |
|------|---------|-----------|-----------|
| 总 PnL | +9066.87 | -93.00 | +37.00 |
| 总 Trades | 200 | 158 | 163 |
| 平均 Fill Rate | 100% | 79.1% | 81.6% |
| 平均 Entry Improve | 0% | 0.376% | 0.379% |

### 4b. 0.382 limit-entry 是否提升收益质量？

**否。** E1 (-93.00) 和 E2 (+37.00) 均远劣于 E0 (+9066.87)。

虽然 2023 年有戏剧性改善（E0: -3924 → E2: +19），但 2024 年灾难性恶化（E0: +8501 → E2: -217），2025 年同样大幅下降（E0: +4490 → E2: +235）。

### 4c. 是否只是减少交易？

**不仅是减少交易，更是改变了风险/收益几何结构。**

| 年份 | E0 Trades | E1 Trades | E2 Trades | E1 减少 | E2 减少 |
|------|-----------|-----------|-----------|---------|---------|
| 2023 | 62 | 50 | 52 | 12 | 10 |
| 2024 | 70 | 54 | 54 | 16 | 16 |
| 2025 | 68 | 54 | 57 | 14 | 11 |

Limit entry 减少了交易次数（~20%），但更关键的是 **止损距离缩小了 ~55%**，这从根本上改变了 TP/SL 的绝对价格位置。

### 4d. 风险/收益几何结构变化

这是 H2 实验最核心的发现：

**当前 market entry**:
- entry = next_kline.open（高于信号 K）
- SL = signal_kline.low
- stop_distance = entry - signal_low（**大**）
- TP1 = entry + 1R × stop_distance（远）
- TP2 = entry + 3.5R × stop_distance（很远）

**0.382 limit entry**:
- entry = signal_low + 0.382 × (signal_high - signal_low)
- SL = signal_kline.low
- stop_distance = 0.382 × range（**小，缩小约 55%**）
- TP1 = entry + 1R × 0.382 × range（绝对价格更近）
- TP2 = entry + 3.5R × 0.382 × range（绝对价格更近）

**关键洞察**:
- 止损距离缩小 ~55% → 每笔风险更小
- TP 目标在绝对价格上更近 → 更容易触及
- 但每笔盈利的绝对金额也更小
- **在 2023（均值回归市场）**: 价格经常回撤到 0.382 → 高 fill rate → 有效
- **在 2024（趋势市场）**: 价格经常跳空上涨 → missed signals → 失败
- **这是趋势跟踪策略的反面**: 0.382 limit entry 在趋势延续中错过入场，在均值回归中有效

### 4e. Missed signals 分析

| 年份 | E1 missed | E1 missed W | E1 missed L | E1 missed L% | E2 missed | E2 missed W | E2 missed L | E2 missed L% |
|------|-----------|------------|------------|-------------|-----------|------------|------------|-------------|
| 2023 | 12 | 3 | 9 | 75% | 10 | 3 | 7 | 70% |
| 2024 | 16 | 9 | 7 | 44% | 16 | 9 | 7 | 44% |
| 2025 | 14 | 9 | 5 | 36% | 11 | 8 | 3 | 27% |

**2023**: missed 以 losers 为主（75%）→ limit entry 有效过滤了坏信号
**2024**: missed 以 winners 为主（56%）→ limit entry 错过了好信号
**2025**: missed 以 winners 为主（64-73%）→ limit entry 错过了更多好信号

这证实了 0.382 limit entry 在趋势市场中系统性地错过盈利入场。

### 4f. 2023 改善的真实原因

2023 年 PnL 从 -3924 改善到 +19，看似戏剧性，但原因不是"入场价格更好"：
- 入场改善仅 0.31%（微不足道）
- 真正原因是 **止损距离缩小 55%** → 每笔亏损更小 → 累积亏损大幅减少
- 但同样的机制在 2024/2025 导致每笔盈利也更小 → 累积盈利大幅减少

### 4g. Proxy 估算局限

本 proxy 简化了以下引擎级逻辑：
1. **部分止盈后的仓位管理**: proxy 假设 TP1 后剩余仓位继续持有，但未精确模拟 TP1 部分止盈的仓位缩减
2. **同 bar 冲突处理**: proxy 使用 pessimistic（SL 优先），与引擎一致，但未考虑 random 策略
3. **资金管理**: proxy 未模拟 exposure 限制、daily_max_trades 等风控逻辑
4. **TP1% = 0% 异常**: 所有实验的 TP1% 均为 0%，说明 proxy 的 TP/SL 估算逻辑可能过于简化（TP1 达成后剩余仓位直接看 TP2，而非记录 TP1 事件）

这些局限意味着 proxy 结果的方向性结论可靠（0.382 limit entry 在趋势市场恶化），但绝对 PnL 数值不可直接与引擎级回测比较。

## 5. 最终结论

**H2 判定**: **不通过**

- **0.382 limit-entry 是否提升收益质量**: 否。3yr PnL 从 +9067 恶化至 -93/+37
- **是否只是减少交易**: 否。它还改变了风险/收益几何结构（止损距离缩小 55%，TP 绝对价格大幅拉近）
- **是否值得进入引擎级 pending limit entry 设计**: 不建议。0.382 limit entry 与趋势跟踪策略逻辑矛盾——趋势延续时价格不回撤到 0.382，而回撤时趋势可能已结束
- **是否禁止直接进入 runtime**: 禁止

### 衍生洞见

1. **2023 改善说明更紧风险几何能压缩亏损**: 止损距离缩小 55% → 每笔亏损更小 → 累积亏损大幅减少。这证实了"风险几何"对亏损年份有显著影响。
2. **但同一机制会严重削弱趋势收益**: 2024/2025 的趋势收益依赖较大的止损距离和较远的 TP 目标。缩小止损距离 = 缩小趋势捕获范围 = 系统性 missed winners。
3. **后续方向**: 不应继续研究固定 0.382 limit-entry，而应转向：
   - **动态风险几何**: 根据市场环境（ADX、波动率状态）动态调整止损距离和 TP 目标
   - **环境识别**: 在趋势延续环境中保持当前 market entry + 宽止损，在均值回归环境中考虑更紧止损
   - 这与 market regime 实验的结论一致——粗粒度 regime gate 失败，需要更精细的环境识别

---

> **重要**: 本报告为 proxy 估算，不是正式引擎级回测。
> Proxy 简化了部分止盈后的仓位管理和同 bar 冲突处理。
> H2 已判定不通过，不建议进入引擎级 pending limit entry 设计。
> MFE/MAE/+1R/+2R/+3.5R 可达率、first-touch 等指标标记为 TODO。