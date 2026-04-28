# C2 Pinbar + T1 Portfolio Official Parity Check — 官方口径组合验证

**日期**: 2026-04-28
**假设**: C1 组合价值在官方 Backtester v3_pms 口径下仍然成立
**类型**: Parity check（Pinbar via official Backtester, T1-R matched compounding）
**判定**: **CONDITIONAL FAIL** — 组合 PnL↑/DD↓ 仍成立，但移除 T1 Top 3 后 P60_T40/P50_T50 变负

---

## 实验目标

C1 Proxy 证明了 Pinbar + T1 组合具有分散化价值（P60_T40/P50_T50 全部 PASS）。本实验在官方 Backtester v3_pms 口径下验证：Pinbar 使用 official backtester（compounding, concurrent positions, MTM equity），T1-R 使用 matched compounding simulation。

---

## 口径说明

| 维度 | Pinbar (Official) | T1-R (Matched) |
|------|-------------------|-----------------|
| 引擎 | Backtester v3_pms | Matched compounding simulation |
| 时间框架 | 1h bars | 4h bars |
| Compounding | YES (official) | YES (matched) |
| Concurrent positions | YES (exposure-capped) | NO (single position) |
| max_total_exposure | 2.0 | 2.0 |
| max_loss_pct | 1% | 1% |
| max_leverage | 20x | 20x |
| fee_rate | 0.0405% | 0.0405% |
| entry_slippage | 0.01% | 0.01% |
| exit_slippage | 0.01% | 0.01% |
| MTM equity | YES | YES |
| 策略 | Pinbar + EMA50 + MTF + ATR | Donchian 20 breakout, trailing 3×ATR |
| 初始资金 | $10,000 | $10,000 |
| 年度处理 | year-by-year restart | 连续跨年 |

**口径差异 vs C1**: Pinbar 从 proxy 单仓位固定余额改为 official compounding + concurrent positions + DynamicRiskManager。T1-R 保持 matched compounding simulation。

---

## 单策略结果

### Pinbar (Official v3_pms, year-by-year restart)

| 指标 | 值 |
|------|-----|
| 3yr PnL (yearly sum) | **+1,492** |
| 3yr PnL (continuous equity) | **+74.89** |
| 2023 PnL | -5,233 |
| 2024 PnL | +3,701 |
| 2025 PnL | +3,024 |
| MaxDD (continuous) | 67.94% |
| Total Trades | 225 (93+76+56) |

**关键差异 vs C1 Proxy**: Pinbar 3yr PnL 从 C1 的 +435 提升到 +1,492（yearly sum）或 +74.89（continuous equity）。Continuous equity 远低于 yearly sum，说明 compounding 下 2023 的大亏严重拖累了后续年份的复利基数。

### Pinbar Baseline 对比

| 口径 | 3yr PnL | 2023 | 2024 | 2025 |
|------|---------|------|------|------|
| C1 Proxy (单仓位固定余额) | +435 | -3,181 | +4,300 | -684 |
| C2 Official year-by-year | +1,492 | -5,233 | +3,701 | +3,024 |
| C2 Official continuous | +75 | -5,791* | +3,280* | +2,585* |
| Official Baseline (research) | +9,066 | -3,924 | +8,501 | +4,490 |

*C2 continuous 年度值为 equity 在年初/年末的差额，受前年亏损的复利拖累。

**C2 vs Official Baseline 差距**: C2 (+1,492) vs Official (+9,066)。差距可能来自：data source differences、funding rate、engine implementation differences。但 C2 内部组合比较是自洽的。

### T1-R (Matched Compounding)

| 指标 | 值 |
|------|-----|
| 3yr PnL | **+2,039** |
| 2023 PnL | +1,358 |
| 2024 PnL | +380 |
| 2025 PnL | +301 |
| Total Trades | 109 |
| Top 3 Winners PnL | +2,210 (108.4% of total) |
| T1 without Top 3 | **-171.16** |
| Fragile? | **YES** |

T1-R 结果与 C1 完全一致（same simulation engine）。

---

## 策略相关性

| 方法 | C2 | C1 |
|------|----|----|
| Weekly MTM returns | **0.050** | 0.195 |

**C2 相关性更低** (0.050 vs 0.195)：Pinbar 使用 official compounding 后 equity curve 形态改变，导致与 T1 的相关性进一步降低。接近零相关意味着更好的分散化效果。

---

## 组合结果

### 权重矩阵

| 组合 | 3yr PnL | 2023 | 2024 | 2025 | MaxDD | Sharpe | Sortino | Calmar |
|------|---------|------|------|------|-------|--------|---------|--------|
| **P100_T0** | +75 | -5,791 | +3,280 | +2,585 | 67.94% | 0.075 | 0.114 | 0.004 |
| P80_T20 | +468 | -4,361 | +2,700 | +2,129 | 53.40% | -0.005 | -0.007 | 0.029 |
| P70_T30 | +664 | -3,646 | +2,410 | +1,900 | 46.32% | -0.040 | -0.060 | 0.048 |
| P60_T40 | +861 | -2,931 | +2,120 | +1,672 | 39.36% | -0.074 | -0.110 | 0.073 |
| **P50_T50** | +1,057 | -2,216 | +1,830 | +1,443 | 32.65% | -0.108 | -0.159 | 0.108 |

### PnL 改善（vs Pinbar alone）

| 组合 | 3yr PnL Δ | 2023 Δ (abs) | MaxDD Δ | 2023 改善% |
|------|-----------|-------------|---------|-----------|
| P80_T20 | +393 | +1,430 | -14.54pp | 24.7% |
| P70_T30 | +589 | +2,145 | -21.62pp | 37.0% |
| P60_T40 | +786 | +2,860 | -28.58pp | 49.4% |
| P50_T50 | +982 | +3,575 | -35.29pp | 61.7% |

---

## PASS 标准验证

| 标准 | P80_T20 | P70_T30 | P60_T40 | P50_T50 |
|------|---------|---------|---------|---------|
| 组合 3yr PnL > Pinbar alone | +468 > +75 ✅ | +664 > +75 ✅ | +861 > +75 ✅ | +1,057 > +75 ✅ |
| 组合 MaxDD < Pinbar alone | 53.40% < 67.94% ✅ | 46.32% < 67.94% ✅ | 39.36% < 67.94% ✅ | 32.65% < 67.94% ✅ |
| 2023 loss reduction >= 40% | 24.7% ❌ | 37.0% ❌ | **49.4%** ✅ | **61.7%** ✅ |
| 移除 T1 Top 3 后组合不崩 | +26 ⚠️ | +1 ⚠️ | **-24** ❌ | **-48** ❌ |
| 曲线更平滑（MaxDD↓） | ✅ | ✅ | ✅ | ✅ |

**P60_T40 和 P50_T50 在前 3 项标准 PASS，但移除 T1 Top 3 后 FAIL。**
**P80_T20 和 P70_T30 移除 Top 3 后勉强正但 2023 改善不达标。**

---

## T1 Fragility 分析（移除 Top 3 Winners）

| 组合 | 原始 PnL | 移除 Top 3 后 | Delta | PASS? |
|------|----------|---------------|-------|-------|
| P100_T0 (Pinbar) | +75 | +75 | N/A | — |
| P80_T20 | +468 | +26 | -94% | ⚠️ 勉强正 |
| P70_T30 | +664 | +1 | -99.8% | ⚠️ 勉强正 |
| P60_T40 | +861 | **-24** | -103% | ❌ 变负 |
| P50_T50 | +1,057 | **-48** | -105% | ❌ 变负 |

**关键发现**: 与 C1 Proxy 相比，C2 移除 Top 3 后的结果显著恶化：

| 组合 | C1 移除 Top 3 后 | C2 移除 Top 3 后 | 差异 |
|------|------------------|------------------|------|
| P80_T20 | +314 | +26 | -92% |
| P70_T30 | +253 | +1 | -99.6% |
| P60_T40 | +193 | **-24** | 从正变负 |
| P50_T50 | +132 | **-48** | 从正变负 |

**根因**: C1 Pinbar 3yr PnL = +435，C2 Pinbar continuous equity PnL = +74.89。Pinbar 的绝对 PnL 大幅下降，导致组合对 T1 Top 3 的依赖度急剧上升。在 C1 中，Pinbar 贡献的独立 PnL 足以吸收 T1 Top 3 移除的冲击；在 C2 中，Pinbar continuous PnL 太低，无法承担这个角色。

---

## C1 vs C2 关键对比

| 指标 | C1 Proxy | C2 Official Parity | 变化 |
|------|----------|-------------------|------|
| Pinbar 3yr PnL | +435 | +75 (continuous) | -83% |
| T1 3yr PnL | +2,039 | +2,039 | 不变 |
| Correlation | 0.195 | 0.050 | 更低（更好） |
| P60_T40 3yr PnL | +1,077 | +861 | -20% |
| P60_T40 MaxDD | 19.48% | 39.36% | +19.88pp（更差） |
| P60_T40 移除 Top 3 | +193 | **-24** | 从正变负 |
| P50_T50 移除 Top 3 | +132 | **-48** | 从正变负 |

**MaxDD 大幅上升**: C1 Pinbar MaxDD 33.6% → C2 Pinbar MaxDD 67.94%。Official compounding + concurrent positions 在 2023 产生了远超 proxy 的回撤。

---

## Sharpe/Sortino 趋势分析

| 指标 | P100 | P80_T20 | P70_T30 | P60_T40 | P50_T50 |
|------|------|---------|---------|---------|---------|
| Sharpe | 0.075 | -0.005 | -0.040 | -0.074 | -0.108 |
| Sortino | 0.114 | -0.007 | -0.060 | -0.110 | -0.159 |
| Calmar | 0.004 | 0.029 | 0.048 | 0.073 | 0.108 |

Sharpe/Sortino 全线为负或接近零，说明 risk-adjusted returns 在官方口径下不理想。Calmar 持续改善（MaxDD 下降主导），但绝对水平很低。

---

## 判定

### 结论

1. **组合 PnL↑ 和 DD↓ 仍成立** — 所有权重组合均优于 Pinbar alone，C2 相关性更低 (0.050)

2. **但 T1 依赖度急剧上升** — C2 Pinbar continuous PnL (+74.89) 远低于 C1 (+435)，导致：
   - P60_T40 移除 T1 Top 3 后变负 (-24)
   - P50_T50 移除 T1 Top 3 后变负 (-48)
   - P80_T20/P70_T30 勉强正但接近零

3. **Pinbar continuous PnL 太低是核心问题** — C2 Official Pinbar 在 compounding + concurrent positions 下，2023 大亏 (-5,233) 严重拖累后续复利，3yr continuous 仅 +75。这导致组合的 Pinbar "独立贡献" 不足以吸收 T1 fragility 冲击。

4. **T1 fragility 在 official 口径下更致命** — C1 中 T1 Top 3 移除后组合仍显著正；C2 中组合接近零或变负。Official 口径放大了 T1 fragility 的影响。

5. **Correlation 0.050** — 接近零相关，分散化效果理论上更好，但被 Pinbar 低绝对 PnL 抵消。

### 是否进入下一轮

**不建议以当前参数组合继续推进**。核心阻塞：

- T1 fragility (108.4% from Top 3) 在 official 口径下让组合对少数大赢家的依赖过高
- Pinbar continuous PnL 太低（compounding 下 2023 大亏的复利拖累）
- 没有任何权重组合能同时满足 "2023 改善 >=40%" 和 "移除 T1 Top 3 后不崩"

### 后续方向

1. **如果要继续组合研究**: 需要先解决 T1 fragility —— 寻找不依赖 Top 3 winners 的趋势跟随策略
2. **如果单独优化 Pinbar**: M1/M1b 已证明 E4 donchian_dist filter 在 proxy 口径下有效，可降低 2023 亏损，从而提高 Pinbar continuous PnL
3. **Pinbar 基线差距需调查**: C2 (+1,492) vs Official (+9,066) 差距 6x，根因待查（data source / funding / engine differences）

---

## 产出文件

| 文件 | 说明 |
|------|------|
| `scripts/run_c2_pinbar_t1_portfolio_parity.py` | C2 组合验证脚本 |
| `reports/research/c2_pinbar_t1_portfolio_parity_2026-04-28.json` | 完整结果 JSON |
| `docs/planning/2026-04-28-c2-pinbar-t1-portfolio-parity.md` | 本报告 |
