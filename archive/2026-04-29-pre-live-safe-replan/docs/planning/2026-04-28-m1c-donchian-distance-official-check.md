# M1c E4 Donchian Distance Toxic Filter — Official Parity Check

**日期**: 2026-04-28
**假设**: E4 Donchian distance toxic filter 在 official/continuous 口径下稳定提升 Pinbar baseline
**类型**: Parity check（proxy matching official Backtester v3_pms parameters, continuous compounding）
**判定**: **PASS** — E4 全部 5 项标准通过，skipped trades 确认为有毒

---

## 实验目标

M1 proxy 证明 E4 filter PASS。M1b parity 在 year-by-year 口径下 E4 仍保留有效。本实验验证 E4 在 continuous compounding 口径下是否能稳定提升 Pinbar baseline — 这是 C2 组合验证暴露的 Pinbar 底座弱点（continuous PnL 太低）的直接回应。

---

## 口径说明

| 维度 | 值 | 来源 |
|------|----|----|
| Symbol | ETH/USDT:USDT | Sim-1 baseline |
| Timeframe | 1h bars | Sim-1 baseline |
| EMA 1h period | 60 | Official Backtester |
| EMA 4h period | 60 (MTF) | Official Backtester |
| TP targets | [1.0, 2.5] | Official Backtester |
| TP split | [0.6, 0.4] | Official Backtester (partial close) |
| Breakeven | OFF | Official Backtester |
| Entry slippage | 0.10% | Official Backtester |
| TP slippage | 0.05% | Official Backtester |
| Fee rate | 0.0400% | Official Backtester |
| Max loss % | 1% | Official Backtester |
| Exposure cap | 2.0x | Research profile |
| Direction | LONG only | Sim-1 baseline |
| Equity mode | **Continuous compounding** | 本实验特有 |
| Concurrent positions | NO (single position) | Proxy 限制 |
| E4 threshold | distance_to_donchian_20_high < -0.016809 | M0 tercile boundary |

**与 Official Backtester 的差异**:
- Proxy simulation（backtester 不支持 donchian filter）
- Single position（无 concurrent positions）
- Same-bar policy: SL checked before TP (pessimistic)

---

## 单策略结果

### E0: Pinbar Baseline (no filter, continuous)

| 指标 | 值 |
|------|-----|
| 3yr PnL (continuous) | **-7,230** |
| 2023 PnL | -4,254 |
| 2024 PnL | -2,116 |
| 2025 PnL | -860 |
| MaxDD MTM | 72.89% |
| MaxDD Realized | 72.78% |
| Total Trades | 203 |
| Sharpe | -2.517 |
| Sortino | -2.154 |
| WR (2023/2024/2025) | 15.6% / 32.4% / 24.6% |

**E0 全年亏损**: Continuous compounding 下 proxy E0 全部三年为负。这与 Official Baseline (+9,066) 差距极大，根因：
1. Proxy 单仓位 vs Official concurrent positions
2. 2023 大亏后 equity 缩水，2024/2025 position sizing 过小
3. Entry slippage 0.10% (official) vs 0.01% (old proxy)

### E4: Pinbar + Donchian Distance Toxic Filter

| 指标 | 值 |
|------|-----|
| 3yr PnL (continuous) | **-4,024** |
| 2023 PnL | -2,777 |
| 2024 PnL | -299 |
| 2025 PnL | -947 |
| MaxDD MTM | 40.48% |
| MaxDD Realized | 40.24% |
| Total Trades | 148 |
| Total Signals | 1,435 |
| Filtered | 69 (4.8% of signals) |
| Sharpe | -1.961 |
| Sortino | -1.831 |
| WR (2023/2024/2025) | 15.2% / 37.9% / 25.0% |

---

## PASS 标准验证

| 标准 | 结果 | 详情 |
|------|------|------|
| 3yr PnL > E0 | ✅ PASS | -4,024 > -7,230 (Δ=+3,206, +44.4%) |
| 2023 loss reduction >= 25% | ✅ PASS | 34.7% loss reduction |
| MaxDD MTM < E0 | ✅ PASS | 40.48% < 72.89% (-32.41pp) |
| 2024/25 profit retention/loss reduction | ✅ PASS | 58.1% loss reduction (E0 baseline negative) |
| Trade reduction <= 40% | ✅ PASS | 27.1% (148 vs 203) |

**全部 5 项 PASS。**

---

## Skipped Trade Quality 分析

被 E4 filter 跳过的 69 笔交易的反事实分析（如果做了会怎样）：

| 年份 | 跳过数 | 反事实 PnL | 平均 PnL | 说明 |
|------|--------|-----------|----------|------|
| 2023 | 23 | **-1,932** | -84.02 | 确认有毒，净亏 |
| 2024 | 20 | **-1,157** | -57.84 | 确认有毒，净亏 |
| 2025 | 26 | **+203** | +7.82 | 微正，filter 在此年有轻微过度过滤 |
| **Total** | **69** | **-2,886** | **-41.83** | |

**反事实 Win Rate**: 44.93%（高于 E0 平均 WR ~24%）

**关键发现**:
1. 被跳过的交易 WR 很高（44.9%）但总 PnL 为负（-2,886）—— 说明这些交易赢多亏少但赢小亏大，典型 toxic pattern
2. 2023/2024 跳过的交易确认有毒（合计 -3,089）
3. 2025 跳过的交易微正（+203），说明 filter 在 2025 年有轻微过度过滤，但影响很小
4. 总体：filter 移除的 69 笔交易如果做了，会额外亏 -2,886。filter 有效减少了亏损来源

---

## E4 vs E0 年度对比

| 年份 | E0 PnL | E4 PnL | Δ | E0 WR | E4 WR | E0 trades | E4 trades |
|------|--------|--------|---|-------|-------|-----------|-----------|
| 2023 | -4,254 | -2,777 | +1,477 | 15.6% | 15.2% | 64 | 46 |
| 2024 | -2,116 | -299 | +1,817 | 32.4% | 37.9% | 74 | 58 |
| 2025 | -860 | -947 | -87 | 24.6% | 25.0% | 65 | 44 |
| **3yr** | **-7,230** | **-4,024** | **+3,206** | — | — | **203** | **148** |

**2023**: 亏损减少 34.7%，46 vs 64 笔交易（-28%），filter 移除了 23 笔有毒交易
**2024**: 亏损大幅减少 85.8%，58 vs 74 笔交易，WR 从 32.4% 升到 37.9%
**2025**: 微幅恶化（-87），44 vs 65 笔交易，filter 有轻微过度过滤但影响极小

---

## Sharpe/Sortino 改善

| 指标 | E0 | E4 | 改善 |
|------|----|----|------|
| Sharpe | -2.517 | -1.961 | +0.556 |
| Sortino | -2.154 | -1.831 | +0.323 |

虽然两者均为负（proxy 口径下整体亏损），E4 的 risk-adjusted 指标明显更好。

---

## 与 M1/M1b 跨口径一致性

| 口径 | E0 PnL | E4 PnL | Δ | E4 判定 |
|------|--------|--------|---|---------|
| M1 Proxy (固定余额, year-by-year) | -2,158 | +1,042 | +3,200 | PASS |
| M1b Parity (固定余额, year-by-year) | -14,886 | -8,695 | +6,191 | PASS |
| **M1c Continuous (复利, 跨年)** | **-7,230** | **-4,024** | **+3,206** | **PASS** |

**E4 在三种口径下均 PASS**，改善幅度一致（+3,200 ~ +6,191）。这是目前唯一跨口径稳定有效的 toxic-state filter。

---

## Proxy vs Official Baseline 差距说明

| 口径 | 3yr PnL | 说明 |
|------|---------|------|
| M1c Proxy E0 (continuous) | -7,230 | 本实验 baseline |
| Official Baseline (research) | +9,066 | 正式回测器 |
| M1b Proxy E0 (year-by-year) | -14,886 | M1b parity |

M1c E0 (-7,230) vs Official (+9,066) 差距 16,296。根因：
1. **Concurrent positions**: Official 支持多仓位并行（daily_max_trades=50），proxy 只有单仓位
2. **Position sizing**: Official compounding 与 proxy compounding 行为不同
3. **Data source**: 可能存在 K 线数据微小差异

**重要**: 这个差距不影响 E4 的相对有效性判断。E4 的价值在于 "相对于同一 baseline 的改善"，而非绝对 PnL 水平。

---

## 判定

### 结论

1. **E4 PASS 全部 5 项标准** — 在 continuous compounding 口径下，E4 filter 稳定提升 Pinbar baseline

2. **改善来源确认为有毒交易移除** — 被跳过的 69 笔交易反事实 PnL = -2,886，平均 PnL = -41.83。Win rate 虽高 (44.9%) 但盈亏比极差

3. **跨口径一致**: E4 在 M1 (proxy)、M1b (parity year-by-year)、M1c (parity continuous) 三种口径下均 PASS

4. **2025 轻微过度过滤**: 被跳过的 2025 交易微正 (+203)，但影响极小（E4 的 2025 PnL 只比 E0 差 -87）

5. **MaxDD 大幅改善**: 72.89% → 40.48% (-32.41pp)，这是对 C2 组合验证中 "Pinbar MaxDD 太高" 问题的直接回应

### E4 是否保留为 Pinbar 稳定性增强候选

**是，强烈推荐**。E4 是目前唯一在三种不同口径下均 PASS 的 toxic-state filter。它直接解决了 C2 暴露的两个核心问题：
- Pinbar continuous PnL 太弱 → E4 将 3yr PnL 改善 44.4%
- Pinbar MaxDD 太高 → E4 将 MaxDD 从 72.89% 降到 40.48%

### 是否允许后续重新做 Pinbar(E4) + T1 组合

**是，建议**。但前提：
1. E4 需要在正式 Backtester 中实现（当前 backtester 不支持 donchian filter，需要新增 filter type 或用 proxy）
2. 先在 official 口径下单独验证 E4 的 continuous PnL（当前 proxy 和 official 有 16k 差距）
3. 如果 E4 在 official 口径下 continuous PnL 为正，则 Pinbar(E4) + T1 组合的 "移除 T1 Top 3 后崩塌" 风险可能显著降低

### 如果失败，A 线是否暂停

本实验 PASS，A 线（Pinbar 稳定性增强）继续推进。下一步建议：
1. 在正式 Backtester 中实现 donchian distance filter（新增 filter type）
2. 用 official backtester 跑 E4 continuous baseline
3. 如果 official E4 continuous PnL > 0，做 Pinbar(E4) + T1 组合验证

---

## 产出文件

| 文件 | 说明 |
|------|------|
| `scripts/run_m1c_donchian_distance_official_check.py` | M1c 实验脚本 |
| `reports/research/m1c_donchian_distance_official_check_2026-04-28.json` | 完整结果 JSON |
| `docs/planning/2026-04-28-m1c-donchian-distance-official-check.md` | 本报告 |
