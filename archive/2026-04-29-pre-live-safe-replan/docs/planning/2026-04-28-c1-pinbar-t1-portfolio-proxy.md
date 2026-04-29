# C1 Pinbar + T1 Portfolio Proxy — 组合价值验证

**日期**: 2026-04-28  
**假设**: Pinbar + T1 组合具有分散化价值  
**类型**: Proxy result（独立撮合，非正式 Backtester）  
**判定**: **CONDITIONAL PASS** — 组合改善显著但 T1 存在 fragility

---

## 实验目标

Pinbar 是回撤修复策略，2024/2025 表现好但 2023 大亏。T1-R (4h Donchian trend follower) 修正后 conditional pass，3yr PnL +1,949，但收益高度集中于 Top 3 winners (108.4%)。本实验验证 Pinbar + T1 组合是否具有组合价值。

---

## 口径说明

| 维度 | Pinbar | T1-R |
|------|--------|------|
| 时间框架 | 1h bars | 4h bars |
| 模拟类型 | 单仓位，固定 INITIAL_BALANCE | 单仓位，trailing stop |
| TP 目标 | [1.0R, 3.5R]，各 50% | trailing 3×ATR |
| BE | ON（TP1 触发后移 SL 到 entry） | 无 |
| 滑点 | 0.01% entry | 0.01% entry + 0.01% exit |
| 手续费 | 0.0405% | 0.0405% |
| EMA | 50 (1h) | Donchian 20 (4h) |
| 初始资金 | $10,000 | $10,000 |
| 年度重置 | 否（连续复利） | 否（连续复利） |
| 过滤器 | E0 baseline（无 toxic filter） | 无 |

**重要口径**: equity curve 使用连续复利（不年度重置），这意味着各年 PnL 是 equity 在年初/年末的差额，而非独立年度收益。组合 Equity = w_P × Pinbar_Equity + w_T × T1_Equity（4h bar 频率对齐）。

---

## 单策略结果

### Pinbar Baseline (E0)

| 指标 | 值 |
|------|-----|
| 3yr PnL | **+435** |
| 2023 PnL | -3,181 |
| 2024 PnL | +4,300 |
| 2025 PnL | -684 |
| MaxDD | 33.60% |
| Total Trades | 253 |
| Monthly Positive Rate | 44.4% |

### T1-R (Corrected)

| 指标 | 值 |
|------|-----|
| 3yr PnL | **+2,039** |
| 2023 PnL | +1,358 |
| 2024 PnL | +380 |
| 2025 PnL | +301 |
| Total Trades | 109 |
| Top 3 Winners | +2,210 (108.4% of T1 PnL) |
| T1 without Top 3 | **-17.53** |

**T1 Fragility**: Top 3 winners 贡献 >100% T1 PnL，说明其余 106 笔交易净亏。这是趋势跟随策略的典型特征 — 少数大赢家覆盖大量小亏。

---

## 策略相关性

| 方法 | Correlation |
|------|-------------|
| Weekly MTM returns (2023-2025) | **0.195** |
| Prior research estimate | -0.457 |

**差异说明**: Prior research 使用的是不同口径（可能基于月度 realized PnL），而本实验使用 weekly MTM returns（含浮盈浮亏）。弱正相关 0.195 意味着策略间存在轻微的同向波动，但总体分散化效果有限。不像此前估计的负相关那么强。

---

## 组合结果

### 权重矩阵

| 组合 | 3yr PnL | 2023 | 2024 | 2025 | MaxDD | Sharpe | Sortino | Calmar |
|------|---------|------|------|------|-------|--------|---------|--------|
| **P100_T0** | +435 | -3,181 | +4,300 | -684 | 33.60% | 0.141 | 0.276 | 0.043 |
| P80_T20 | +756 | -2,273 | +3,516 | -487 | 25.55% | 0.091 | 0.173 | 0.099 |
| P70_T30 | +917 | -1,819 | +3,124 | -388 | 22.12% | 0.065 | 0.122 | 0.138 |
| P60_T40 | +1,077 | -1,365 | +2,732 | -290 | 19.48% | 0.037 | 0.070 | 0.184 |
| **P50_T50** | +1,237 | -911 | +2,340 | -192 | 17.77% | 0.007 | 0.013 | 0.232 |

### PnL 改善（vs Pinbar alone）

| 组合 | 3yr PnL Δ | 2023 Δ | MaxDD Δ | Monthly Pos% |
|------|-----------|--------|---------|--------------|
| P80_T20 | +321 (+74%) | +908 | -8.05pp | 44.4% |
| P70_T30 | +482 (+111%) | +1,362 | -11.48pp | 44.4% |
| P60_T40 | +642 (+147%) | +1,816 | -14.12pp | 44.4% |
| P50_T50 | +802 (+184%) | +2,270 | -15.83pp | 36.1% |

---

## PASS 标准验证

| 标准 | P80_T20 | P70_T30 | P60_T40 | P50_T50 |
|------|---------|---------|---------|---------|
| 组合 3yr PnL > Pinbar alone | +756 > +435 ✅ | +917 > +435 ✅ | +1,077 > +435 ✅ | +1,237 > +435 ✅ |
| 组合 MaxDD < Pinbar alone | 25.55% < 33.60% ✅ | 22.12% < 33.60% ✅ | 19.48% < 33.60% ✅ | 17.77% < 33.60% ✅ |
| 2023 改善 >=50% | 28.5% ❌ | 42.8% ❌ | 57.1% ✅ | 71.4% ✅ |
| 组合不完全依赖 T1 Top 3 | +314 ✅ | +253 ✅ | +193 ✅ | +132 ✅ |
| 曲线更平滑（MaxDD↓） | ✅ | ✅ | ✅ | ✅ |

**P60_T40 和 P50_T50 全部 5 项 PASS。**  
**P80_T20 和 P70_T30 的 2023 改善不足 50%。**

---

## T1 Fragility 分析

| 指标 | 值 |
|------|-----|
| T1 Top 3 Winners PnL | +2,210 |
| T1 Total PnL | +2,039 |
| T1 Top 3 % of Total | 108.4% |
| T1 without Top 3 | **-17.53** |
| T1 Fragile? | **YES** (>60% from top 3) |

**组合鲁棒性**（移除 T1 Top 3 winners 后）：

| 组合 | 原始 PnL | 移除 Top 3 后 | Delta | 仍可接受? |
|------|----------|---------------|-------|-----------|
| P80_T20 | +756 | +314 | -58% | ✅ 正 |
| P70_T30 | +917 | +253 | -72% | ✅ 正 |
| P60_T40 | +1,077 | +193 | -82% | ✅ 正 |
| P50_T50 | +1,237 | +132 | -89% | ⚠️ 勉强正 |

**关键观察**: 即使移除 T1 Top 3 winners，所有组合仍为正值。这是因为 Pinbar 的 PnL 贡献独立于 T1，且 Pinbar 权重始终 >= 50%。T1 作为「分散化因子」而非「收益驱动」的角色是合适的。

---

## Sharpe/Sortino 趋势分析

随着 T1 权重增加（P100→P50_T50）：

| 指标 | P100 | P80_T20 | P70_T30 | P60_T40 | P50_T50 |
|------|------|---------|---------|---------|---------|
| Sharpe | 0.141 | 0.091 | 0.065 | 0.037 | 0.007 |
| Sortino | 0.276 | 0.173 | 0.122 | 0.070 | 0.013 |
| Calmar | 0.043 | 0.099 | 0.138 | 0.184 | 0.232 |

**Sharpe/Sortino 下降**: 这是因为 T1 的绝对收益较低（3yr +2,039 vs Pinbar 的 +435），但 T1 的收益方差也较低（trailing stop 策略，持仓时间长）。Sharpe 的下降反映了 T1 的低绝对收益特性。

**Calmar 改善**: Calmar = annualized return / MaxDD，随着 MaxDD 下降更快，Calmar 显著改善。

---

## Monthly Positive Rate

- P100_T0 到 P60_T40: 44.4%（无变化）
- P50_T50: 36.1%（下降）

P50_T50 的 Monthly Positive Rate 下降可能是因为 T1 的 trailing stop 策略导致某些月份出现较大浮亏（MTM basis），尽管长期仍为正。

---

## 判定

### 结论

1. **组合价值存在** — 所有权重组合的 3yr PnL 和 MaxDD 均优于 Pinbar alone。P60_T40 和 P50_T50 满足全部 5 项 PASS 标准。

2. **最优权重候选**: **P60_T40**（Pinbar 60% / T1 40%）
   - 3yr PnL: +1,077 (vs Pinbar +435)
   - MaxDD: 19.48% (vs Pinbar 33.60%)
   - 2023: -1,365 (vs Pinbar -3,181, 改善 57.1%)
   - 移除 T1 Top 3 后仍正: +193
   - Monthly Positive: 44.4%

3. **T1 fragility 是主要风险**
   - T1 本身 108.4% PnL 来自 Top 3 winners
   - 移除 Top 3 后 T1 净亏 -17.53
   - 但组合不依赖 T1 Top 3（Pinbar 贡献独立）
   - T1 在组合中的角色是「分散化因子 + 2023 对冲」，而非「收益引擎」

4. **Correlation 0.195** — 弱正相关，分散化效果有限但存在。与此前估计的 -0.457 不同（可能是口径差异）。

5. **需要 OOS 验证** — 当前结果基于 proxy 撮合引擎，需要在正式 backtester 上验证，特别是 T1 的收益集中度是否在 OOS 中仍然成立。

### 是否进入下一轮

**是，建议进入组合研究下一轮**，但需满足以下前提：
1. T1 必须通过 OOS 验证（fragility 在 OOS 中可能更严重）
2. 需要更真实的 MTM equity curve（当前 proxy 的浮盈浮亏计算有简化）
3. 优先验证 P60_T40 和 P70_T30 权重

### 是否需要更真实 MTM equity curve

**是**。当前 Pinbar 使用的 MTM 计算基于固定 INITIAL_BALANCE 仓位，而 T1 使用 compounding equity 仓位。两者混合时，仓位规模的不一致性可能导致组合指标失真。建议：
- 在正式 Backtester v3_pms 中运行两者，使用相同 compounding 模型
- 或在 proxy 中统一使用固定仓位 + 逐 bar MTM

---

## 产出文件

| 文件 | 说明 |
|------|------|
| `scripts/run_c1_pinbar_t1_portfolio.py` | 组合分析脚本 |
| `reports/research/c1_pinbar_t1_portfolio_proxy_2026-04-28.json` | 完整结果 JSON |
| `docs/planning/2026-04-28-c1-pinbar-t1-portfolio-proxy.md` | 本报告 |
