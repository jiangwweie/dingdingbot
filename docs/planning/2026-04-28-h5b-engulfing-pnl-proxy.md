# H5b: Engulfing PnL Proxy

> **日期**: 2026-04-28
> **性质**: research-only
> **目标**: 验证 Engulfing + EMA50 + MTF EMA60 在完整成本与 backtester 撮合下是否存在可交易 alpha
> **约束**: 不改 runtime profile，不改 sim1_eth_runtime，不做参数搜索，不新增 ATR

---

## 1. 实验背景

H5a-v2 已确认：

- Engulfing trigger 可正常检测。
- `kline_history` 修复后，Backtester 能支持 `detect_with_history()`。
- 4h MTF EMA60 数据对齐可用，且使用 `4h close_time <= 1h signal_time` 避免前瞻。

H5a-v2.1 信号质量切片显示：

- 3 年 MTF 后信号数约 1,458。
- +1R reach rate 约 76.8%。
- +3.5R reach rate 约 38.1%。

因此进入 H5b：检查这些信号在真实成本、敞口限制、分批止盈与回测撮合下是否仍能转化为收益。

---

## 2. 实验配置

| 项 | 配置 |
|----|------|
| Symbol | ETH/USDT:USDT |
| Timeframe | 1h |
| Years | 2023 / 2024 / 2025 |
| Primary EMA | 50 |
| MTF EMA | 60 |
| TP | [1.0R, 3.5R] |
| TP Ratios | [0.5, 0.5] |
| Breakeven | False |
| Trailing | False |
| Fee | 0.000405 |
| Entry Slippage | 0.0001 |
| TP Slippage | 0 |
| max_total_exposure | 2.0 |
| daily_max_trades | 50 |

> 注：第一次脚本试跑时 `max_total_exposure` 被错误放入 `BacktestRuntimeOverrides`，实际未生效，日志显示 `max=0.8`。已修正为通过 `BacktestRequest.risk_overrides=RiskConfig(...)` 传入，复跑日志确认 `max=2.0`。

---

## 3. 实验组

| 实验 | 说明 |
------|------|
| E0 | Pinbar + EMA50 + MTF EMA60，LONG-only，对照组 |
| E1 | Engulfing + EMA50 + MTF EMA60，LONG-only |
| E2 | Engulfing + EMA50 + MTF EMA60，SHORT-only |
| E3 | Engulfing + EMA50 + MTF EMA60，LONG+SHORT shadow |

---

## 4. 结果汇总

| 实验 | 2023 PnL | 2024 PnL | 2025 PnL | 3yr PnL | Trades | WR |
|------|----------|----------|----------|---------|--------|----|
| E0 Pinbar LONG | -5185.30 | +6729.99 | +3422.33 | +4967.02 | 254 | 39.0% |
| E1 Engulfing LONG | -5048.77 | -3879.67 | -992.31 | -9920.75 | 708 | 39.1% |
| E2 Engulfing SHORT | -3882.77 | -315.28 | -3454.32 | -7652.36 | 653 | 37.2% |
| E3 Engulfing L/S | -6971.14 | -4062.90 | -4105.80 | -15139.84 | 1361 | 38.2% |

---

## 5. 年度细节

### E0: Pinbar LONG Baseline

| 年份 | PnL | Trades | WR | Sharpe | MaxDD |
|------|-----|--------|----|--------|-------|
| 2023 | -5185.30 | 71 | 22.5% | -2.6104 | 56.96% |
| 2024 | +6729.99 | 93 | 46.2% | 1.9464 | 15.79% |
| 2025 | +3422.33 | 90 | 44.4% | 1.4471 | 12.76% |

### E1: Engulfing LONG-only

| 年份 | PnL | Trades | WR | Sharpe | MaxDD |
|------|-----|--------|----|--------|-------|
| 2023 | -5048.77 | 215 | 36.3% | -1.2899 | 58.58% |
| 2024 | -3879.67 | 253 | 38.3% | -1.0754 | 49.77% |
| 2025 | -992.31 | 240 | 42.5% | -0.1473 | 34.66% |

### E2: Engulfing SHORT-only

| 年份 | PnL | Trades | WR | Sharpe | MaxDD |
|------|-----|--------|----|--------|-------|
| 2023 | -3882.77 | 155 | 29.7% | -0.9506 | 47.83% |
| 2024 | -315.28 | 232 | 44.0% | 0.0683 | 30.70% |
| 2025 | -3454.32 | 266 | 35.7% | -1.2344 | 38.88% |

### E3: Engulfing LONG+SHORT

| 年份 | PnL | Trades | WR | Sharpe | MaxDD |
|------|-----|--------|----|--------|-------|
| 2023 | -6971.14 | 370 | 33.5% | -1.5957 | 74.31% |
| 2024 | -4062.90 | 485 | 41.0% | -0.7689 | 55.10% |
| 2025 | -4105.80 | 506 | 38.9% | -0.9480 | 54.88% |

---

## 6. 核心发现

### 6.1 H5a 的 reach rate 没有转化成 PnL

H5a-v2.1 的 +1R / +3.5R reach rate 看起来健康，但 H5b 显示完整撮合后仍明显亏损。

这说明：

- 单个信号后的价格运动幅度存在。
- 但真实交易链中的入场、止损、成本、持仓重叠、敞口限制和信号密度共同破坏了收益。
- reach rate 只能说明“有后续波动”，不能等同于策略正期望。

### 6.2 Engulfing 信号过密导致收益质量下降

Engulfing 3 年交易数显著高于 Pinbar：

- Pinbar LONG: 254 trades
- Engulfing LONG: 708 trades
- Engulfing SHORT: 653 trades
- Engulfing L/S: 1361 trades

信号密度高，但胜率和收益没有同步提高，说明过滤后仍有大量噪声交易。

### 6.3 SHORT 没有形成有效补充

SHORT-only 在 2024 接近持平，但：

- 2023 仍亏损。
- 2025 明显亏损。
- 3 年累计为 -7652.36。

因此 Engulfing SHORT 不足以作为 2023 修复或组合对冲子策略。

### 6.4 LONG+SHORT 组合进一步恶化

双向组合并未平滑曲线，反而放大亏损：

- 3 年 PnL = -15139.84。
- MaxDD 最高达到 74.31%。

这说明 LONG 与 SHORT 并非互补 alpha，而是共同增加噪声和风险暴露。

---

## 7. 判定

**H5b 判定: 不通过**

结论：

- 不进入 Engulfing 主线。
- 不进入 runtime。
- 不做 Engulfing 参数搜索。
- 不做 Engulfing + ATR 优化。
- 不把 Engulfing 作为 2023 修复路径。

理由：

1. LONG-only、SHORT-only、LONG+SHORT 三组 3 年累计均明显为负。
2. 亏损不是单一年份问题，而是跨年普遍存在。
3. 信号质量切片的积极结果无法在完整撮合下兑现。
4. 继续加过滤器容易进入“先失败后找过滤器救策略”的过拟合路径。

---

## 8. 后续原则

Engulfing 本轮研究链可以收口：

- H5a-v2：工程链路通过。
- H5a-v2.1：信号质量切片通过。
- H5b：完整 PnL proxy 不通过。

保留的工程价值：

- Backtester 已修复 `kline_history` 支持。
- 多 K 线策略研究基础设施被解锁。

策略层结论：

- Engulfing 不适合作为当前 ETH 1h + 4h MTF 趋势跟随组合的新子策略。
- 下一轮策略扩展不应继续在 Engulfing 上调参，应转向不同策略家族，例如 Breakout / Donchian / trend continuation。

---

## 9. 一句话结论

> Engulfing 形态能被系统正确识别，也确实有后续波动，但在完整交易几何、成本和敞口约束下无法转化为正收益，因此本轮不进入后续参数搜索或 runtime 设计。
