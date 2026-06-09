> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical research artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# Direction A Same-Risk Capital-Efficiency Comparison

**Status:** Docs-only diagnostic / Owner decision memo
**Date:** 2026-05-08
**Classification:** `DIRECTION_A_LOWER_RETURN_BUT_LOWER_DRAWDOWN_WORTH_REVIEW`
**Recommendation:** B. Continue design but require 1D spot robustness before execution decision
**Affects Runtime Automatically:** No

---

## 1. Executive Conclusion

**Does 4h Direction A deserve continued docs-only small-live design work?**
Yes. At matched MaxDD, Direction A produces comparable or higher risk-adjusted returns than buy-and-hold and 1D spot trend benchmarks, with materially lower drawdown and lower time in market. The operational complexity is justified by the drawdown reduction.

**Does buy-and-hold or 1D spot clearly dominate at same risk?**
No. Buy-and-hold dominates on raw return but requires 76-79% MaxDD. When risk-scaled to Direction A's 2.6-5.1% MaxDD band, buy-and-hold produces lower net returns and lower Calmar ratios. 1D spot trend has higher PF on BTC but much higher MaxDD (47.5%); when risk-scaled to match Direction A's MaxDD, 1D spot BTC produces similar or slightly lower net. 1D spot ETH does not outperform at any risk level.

**Is more benchmark evidence needed?**
Yes. 1D spot trend has no IS/OOS temporal robustness, no BTC+ETH aggregate, and no ex-SOL decomposition. The 1D spot comparison is preliminary only. Direction A design should continue in parallel, but the execution decision should wait for 1D spot robustness validation.

**Classification:** `DIRECTION_A_LOWER_RETURN_BUT_LOWER_DRAWDOWN_WORTH_REVIEW`

---

## 2. Source Files and Data Quality

### Files Inspected

| File | Status | Data Used |
|---|---|---|
| `docs/ops/direction-a-observation-value-memo.md` | Complete | Prior comparison data, missing diagnostic list |
| `docs/ops/direction-a-phase1-btc-eth-aggregate-diagnostic.md` | Complete | BTC+ETH aggregate baseline, A1/A3 scenarios, sleeve projections |
| `docs/ops/direction-a-risk-control-return-frontier.md` | Complete | 19 scenarios (A-D groups), small-capital projections |
| `docs/ops/direction-a-small-live-design-plan.md` | Complete | Design parameters, Phase 1/2 definition |
| `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md` | Complete | BTC/ETH/SOL individual baselines, year-by-year, top-N fragility |
| `docs/ops/direction-a-p0-evidence-strength-diagnostics.md` | Complete | Winner overlap, bootstrap PF, effective observation count |
| `docs/ops/direction-a-p1-edge-source-attribution.md` | Complete | Random entry control, buy-and-hold decomposition, time-in-market |
| `docs/ops/direction-a-p2-risk-shape-diagnostic.md` | Complete | S0-S5 scenarios, concentration shares |
| `docs/ops/one-day-spot-trend-vs-buy-hold-benchmark.md` | Complete | 1D trend and buy-and-hold results (perp proxy) |
| `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md` | Complete | Methodology standards |

### Missing Artifacts

| Artifact | Status | Impact |
|---|---|---|
| 1D spot IS/OOS (2021-2023 / 2024-2025) | **Missing** | 1D spot temporal robustness unknown |
| 1D spot BTC+ETH aggregate | **Missing** | Cannot compare 1D spot basket vs Direction A BTC+ETH |
| 1D spot ex-SOL decomposition | **Missing** | Cannot assess 1D spot without SOL contamination |
| 1D spot yearly breakdown (per asset) | **Missing** | Cannot assess 1D spot year concentration |
| 1D spot ex-largest-episode | **Missing** | Cannot assess 1D spot fragility |
| Buy-and-hold BTC+ETH aggregate | **Missing** | Cannot compare buy-and-hold basket vs Direction A BTC+ETH |
| Trade-level CSV/JSONL files | **Missing** | All metrics from documented diagnostics |

### Data Provenance

- **4h Direction A metrics:** From `direction-a-cross-asset-frozen-diagnostic-result.md`, `direction-a-sparse-trend-evidence-hardening-and-winner-attribution.md`, and `direction-a-risk-control-return-frontier.md`.
- **1D spot trend metrics:** From `one-day-spot-trend-vs-buy-hold-benchmark.md`. Labeled `PERP_PROXY_FOR_SPOT` — funding excluded but perp-symbol OHLCV used.
- **Buy-and-hold metrics:** From `one-day-spot-trend-vs-buy-hold-benchmark.md`. Same perp-proxy limitation.
- **Risk-scaled calculations:** Linear approximation assuming proportional scaling of MaxDD with capital allocation.

---

## 3. Same-Capital Raw Comparison

### Raw Metrics (30k research capital, 2021-2025)

| Strategy | Net | Return | MaxDD | PF | Trades | Time in Mkt | Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| **4h DA A1 (BTC+ETH)** | 4,324 | 14.4% | 2.6% | 1.752 | 490 | ~38% | 5.54 |
| **4h DA A3 (BTC+ETH)** | 8,649 | 28.8% | 5.1% | 1.752 | 490 | ~38% | 5.65 |
| **Buy-hold BTC** | 60,429 | 201.4% | 76.7% | -- | 1 | 100% | 0.32 |
| **Buy-hold ETH** | 90,400 | 301.3% | 79.4% | -- | 1 | 100% | 0.40 |
| **1D trend BTC** | 65,034 | 216.8% | 47.5% | 2.044 | 41 | 47.6% | 0.54 |
| **1D trend ETH** | 18,374 | 61.2% | 67.9% | 1.384 | 40 | 44.0% | 0.10 |

### Raw Comparison Interpretation

**Raw return:** Buy-and-hold and 1D trend produce vastly higher raw returns. Buy-and-hold BTC returns 201% vs Direction A A1's 14%. 1D trend BTC returns 217%.

**Raw drawdown:** Direction A's 2.6-5.1% MaxDD is an order of magnitude lower than buy-and-hold (76-79%) and 1D trend (48-68%).

**Raw comparison is misleading:** The strategies use the same 30k notional but take radically different risk. Buy-and-hold deploys 100% of capital for 100% of the time. Direction A deploys ~38% of the time with active risk management. Comparing raw net PnL without adjusting for risk is not meaningful.

**The correct comparison requires risk-scaling** (Section 4).

---

## 4. Matched MaxDD Comparison

### Methodology

To compare strategies at matched risk, buy-and-hold and 1D trend are scaled down by allocating a fraction of the 30k total capital such that the MaxDD on total capital matches Direction A's MaxDD.

**Scaling formula:**
- Allocation fraction = Direction A MaxDD / Benchmark MaxDD
- Scaled net = Benchmark net × allocation fraction
- Scaled return on total capital = Scaled net / 30,000

**Assumption:** MaxDD scales linearly with allocation. This is a linear approximation. Actual MaxDD may be slightly different due to compounding effects, but the approximation is reasonable for small allocation fractions.

### 2.6% MaxDD Band (Matching Direction A A1)

| Strategy | Alloc % | Scaled Net | Scaled Return | Calmar | vs DA A1 Net |
|---|---:|---:|---:|---:|---:|
| **4h DA A1** | 100% | 4,324 | 14.4% | 5.54 | -- |
| **Buy-hold BTC** | 3.4% | 2,048 | 6.8% | 2.62 | -52.6% |
| **Buy-hold ETH** | 3.3% | 2,961 | 9.9% | 3.80 | -31.5% |
| **1D trend BTC** | 5.5% | 3,557 | 11.9% | 4.56 | -17.7% |
| **1D trend ETH** | 3.8% | 704 | 2.3% | 0.91 | -83.7% |

**At the 2.6% MaxDD band:** Direction A A1 produces the highest net (4,324). All benchmarks produce less when risk-scaled to the same drawdown. Buy-and-hold BTC produces 53% less. 1D trend BTC produces 18% less. 1D trend ETH produces 84% less.

### 5.1% MaxDD Band (Matching Direction A A3)

| Strategy | Alloc % | Scaled Net | Scaled Return | Calmar | vs DA A3 Net |
|---|---:|---:|---:|---:|---:|
| **4h DA A3** | 100% | 8,649 | 28.8% | 5.65 | -- |
| **Buy-hold BTC** | 6.6% | 4,008 | 13.4% | 2.62 | -53.7% |
| **Buy-hold ETH** | 6.4% | 5,786 | 19.3% | 3.78 | -33.1% |
| **1D trend BTC** | 10.7% | 6,973 | 23.2% | 4.55 | -19.4% |
| **1D trend ETH** | 7.5% | 1,378 | 4.6% | 0.90 | -84.1% |

**At the 5.1% MaxDD band:** Direction A A3 produces the highest net (8,649). Buy-and-hold BTC produces 54% less. 1D trend BTC produces 19% less. 1D trend ETH produces 84% less.

### 5.9% MaxDD Band (Matching Prior A5 Context)

| Strategy | Alloc % | Scaled Net | Scaled Return | Calmar | vs DA A5 Net |
|---|---:|---:|---:|---:|---:|
| **4h DA A5** | 100% | 9,378 | 31.3% | 5.31 | -- |
| **Buy-hold BTC** | 7.7% | 4,642 | 15.5% | 2.62 | -50.5% |
| **Buy-hold ETH** | 7.4% | 6,712 | 22.4% | 3.78 | -28.4% |
| **1D trend BTC** | 12.4% | 8,075 | 26.9% | 4.55 | -13.9% |
| **1D trend ETH** | 8.7% | 1,597 | 5.3% | 0.90 | -83.0% |

**At the 5.9% MaxDD band:** Direction A A5 produces 9,378. 1D trend BTC is closest at 8,075 (14% less). Buy-and-hold BTC is 51% less.

### Risk-Scaling Summary

| Benchmark | vs A1 (2.6% DD) | vs A3 (5.1% DD) | vs A5 (5.9% DD) |
|---|---|---|---|
| Buy-hold BTC | -53% | -54% | -51% |
| Buy-hold ETH | -32% | -33% | -28% |
| 1D trend BTC | -18% | -19% | -14% |
| 1D trend ETH | -84% | -84% | -83% |

**Direction A produces higher risk-adjusted returns than all benchmarks when compared at matched MaxDD.** The advantage is largest vs buy-and-hold (51-54%) and moderate vs 1D trend BTC (14-19%). 1D trend ETH is consistently the worst performer.

### Capital Efficiency Metric: Net per 1% MaxDD

| Strategy | Net per 1% MaxDD |
|---|---:|
| 4h DA A1 | 1,663 |
| 4h DA A3 | 1,696 |
| Buy-hold BTC | 788 |
| Buy-hold ETH | 1,138 |
| 1D trend BTC | 1,369 |
| 1D trend ETH | 271 |

Direction A produces 1,663-1,696 of net per 1% MaxDD. Buy-and-hold BTC produces 788 (53% less). 1D trend BTC produces 1,369 (18% less). Direction A is the most capital-efficient strategy.

---

## 5. 4h Direction A Capital Efficiency

### Conservative Scenarios (30k research capital)

| Scenario | Net | MaxDD | PF | Net/DD | Trades | Time in Mkt |
|---|---:|---:|---:|---:|---:|---:|
| A1_low_vol_norm_max2 | 4,324 | 2.6% | 1.752 | 5.54 | 490 | ~38% |
| A3_hybrid_050_vol_adj_max2 | 8,649 | 5.1% | 1.752 | 5.65 | 490 | ~38% |

### Key Capital Efficiency Properties

**PF 1.752:** Both A1 and A3 have the same PF, indicating the risk-shaping preserves the underlying edge quality. This is higher than the unshaped baseline PF (1.50 for BTC+ETH) because conservative sizing reduces the impact of high-risk trades.

**Time in market ~38%:** Direction A is out of the market ~62% of the time. This means capital is available for other uses during idle periods. Buy-and-hold uses 100% of time. 1D trend uses ~45%.

**Top-winner fragility:** Top-5_after for A1 is 297.71 (positive). This means even after removing the top 5 winners, the conservative scenario still has positive residual — better than the unshaped baseline (negative after top-5 removal). Risk shaping partially addresses fragility.

**Year concentration:** 2023 contributes 2,677.88 of 4,324.46 (62%) in A1. This is above the 60% SRR-002 disclosure threshold but below the deployment blocker level. The conservative scenarios reduce year concentration from the unshaped baseline (95.7% for BTC alone, 60.3% for BTC+ETH combined).

### Operational Complexity

- 490 trades over 5 years = ~98 trades/year = ~2 trades/week
- Signal cadence: 4h bar close evaluation
- Execution: next 4h open
- Monitoring: position tracking, drawdown, funding, slippage
- Kill switches: 5% pause, 8% hard stop, 8 consecutive losses pause

This is moderate complexity. It requires a running 4h bar monitor, order execution loop, and reconciliation. It is not trivial but is feasible for a single operator.

### 1500U Sleeve Projections (A1, pure BTC+ETH)

| Metric | Value |
|---|---:|
| Net | 216U |
| MaxDD | 39U |
| Worst month | -14U |
| Largest loss | -4U |
| Duration | 5 years historical |
| Annualized net | ~43U/year |

The 1500U sleeve under A1 produces ~43U/year with ~39U max drawdown. This is modest but survivable. The learning value (execution integrity, reconciliation, kill-switch testing) is high relative to capital risk.

---

## 6. Buy-and-Hold Comparison

### Raw Buy-and-Hold Results (30k, 2021-2025)

| Asset | Net | Return | MaxDD | CAGR | Calmar |
|---|---:|---:|---:|---:|---:|
| BTC | 60,429 | 201.4% | 76.7% | 24.7% | 0.32 |
| ETH | 90,400 | 301.3% | 79.4% | 32.0% | 0.40 |

### Buy-and-Hold Advantages

1. **Simplicity:** 1 trade, no monitoring, no execution loop, no kill switches.
2. **Raw return:** 201-301% vs Direction A's 14-31%.
3. **No signal risk:** No false breakouts, no stop-outs, no churn.
4. **No operational risk:** No exchange API, no order execution, no reconciliation.

### Buy-and-Hold Disadvantages

1. **MaxDD 76-79%:** At 3wU total capital, a 76.7% drawdown = ~23,000U loss. This is not tolerable for observation or for most operators.
2. **100% time in market:** Capital is fully exposed for the entire period. No ability to redeploy during drawdowns.
3. **No risk management:** You absorb the full bear market (2022: BTC -32,235U, ETH -104,255U).
4. **Full crypto beta:** Correlated to the entire crypto market cycle. No downside protection.

### Scaled Allocation Required to Match Direction A DD

To match Direction A A1's 2.6% MaxDD:
- Buy-hold BTC: allocate 3.4% of capital (1,020U of 30k)
- Buy-hold ETH: allocate 3.3% of capital (990U of 30k)

This means 96.6% of capital sits idle. The opportunity cost is the foregone return on the idle capital (which could earn risk-free rate or be deployed elsewhere).

### Does Simplicity Offset Drawdown?

**No, for the Owner's context.** At 3wU total capital, a 76.7% drawdown is catastrophic. The simplicity advantage of buy-and-hold does not offset the drawdown burden. Even at 3.4% allocation (matching Direction A DD), buy-and-hold BTC produces 53% less net than Direction A A1.

**However,** buy-and-hold is the correct benchmark for evaluating whether active management adds value. Direction A's risk-adjusted outperformance vs buy-and-hold (53% higher net at matched DD) is the core justification for the operational complexity.

---

## 7. 1D Spot Trend Comparison

### Raw 1D Spot Trend Results (30k, 2021-2025, perp proxy)

| Asset | Net | Return | MaxDD | PF | Trades | Time in Mkt | Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | 65,034 | 216.8% | 47.5% | 2.044 | 41 | 47.6% | 0.54 |
| ETH | 18,374 | 61.2% | 67.9% | 1.384 | 40 | 44.0% | 0.10 |
| Equal-weight | 1,571,835 | 5,239.5% | 96.0% | -- | 114 | ~45% | 1.27 |

### 1D Spot Advantages

1. **Higher PF on BTC:** 2.044 vs Direction A's 1.477 (unshaped) or 1.752 (conservative). 1D spot BTC has better trade quality.
2. **Fewer trades:** 41 trades over 5 years = ~8/year. Lower operational burden than Direction A's 98/year.
3. **Lower frequency:** Daily bar evaluation vs 4h. Simpler monitoring.
4. **Higher raw return:** 217% for BTC vs Direction A's 14-31%.

### 1D Spot Disadvantages

1. **MaxDD 47.5% (BTC), 67.9% (ETH):** Still far higher than Direction A's 2.6-5.1%. At 3wU, a 47.5% drawdown = ~14,250U loss.
2. **Basket MaxDD 96.0%:** Essentially no drawdown improvement over buy-and-hold at basket level.
3. **ETH does not outperform buy-and-hold:** 1D trend ETH has CAGR 10.0% vs buy-and-hold ETH CAGR 32.0%. ETH 1D trend timing hurts.
4. **No IS/OOS validation:** Full 2021-2025 window only. No temporal robustness check.
5. **No BTC+ETH aggregate:** Individual asset results exist but no combined basket.
6. **No ex-SOL decomposition:** SOL may be driving basket results (SOL 1D trend: +4,632,098 net, 81,492x cumulative return).
7. **Perp proxy limitation:** All 1D spot results use perp-symbol OHLCV with funding excluded. Not true spot data.
8. **No year-by-year breakdown per asset:** Cannot assess year concentration.
9. **No fragility analysis:** No top-N removal, no episode attribution.

### 1D Spot Classification

**Descriptive evidence only, not robustness evidence.** The 1D spot benchmark exists as a single full-window (2021-2025) result without IS/OOS split, yearly breakdown, ex-SOL decomposition, or fragility analysis. It cannot be used for strong conclusions about capital efficiency.

### Risk-Scaled 1D Spot vs Direction A

At matched MaxDD (Section 4), 1D spot BTC produces 14-19% less net than Direction A. 1D spot ETH produces 83-84% less. Direction A is more capital-efficient than 1D spot at matched risk.

### What Would Make 1D Spot More Competitive

If 1D spot BTC's higher PF (2.044) survives IS/OOS validation and ex-SOL decomposition, it would be a strong alternative. But currently:
- The PF advantage is unvalidated (no OOS check).
- The MaxDD disadvantage is large (47.5% vs 2.6-5.1%).
- The risk-scaled net is 14-19% lower than Direction A.

---

## 8. SOL Exclusion and Contamination Control

### SOL Not Included in Phase 1 Decision

Phase 1 = BTC+ETH only. SOL is Phase 2 optional with ≤25% risk share cap. This comparison uses only BTC and ETH for Direction A.

### SOL Contamination in Benchmarks

**Buy-and-hold:** The buy-and-hold equal-weight basket includes SOL. SOL's 81.5x cumulative return (vs BTC 2.0x, ETH 3.0x) massively dominates the basket. The basket net of 865,195 is almost entirely SOL-driven. Buy-and-hold BTC and ETH are individually reported and are the relevant comparison points.

**1D spot trend:** The 1D spot equal-weight basket includes SOL. SOL's 1D trend net of 4,632,098 dominates the basket net of 1,571,835. The BTC and ETH 1D trend results are individually reported and are the relevant comparison points. However, the 1D spot benchmark document does not provide a BTC+ETH-only aggregate.

### Whether Benchmarks Are Contaminated by SOL

The per-asset benchmark results (BTC buy-hold, ETH buy-hold, BTC 1D trend, ETH 1D trend) are not contaminated by SOL. They are standalone per-asset results.

The basket-level benchmark results (equal-weight buy-hold, equal-weight 1D trend) are contaminated by SOL. These basket results should not be used for Phase 1 comparison.

### Whether ex-SOL Evidence Is Missing

**Yes.** No BTC+ETH-only 1D spot trend aggregate exists. No BTC+ETH-only buy-and-hold aggregate exists. The comparison in this diagnostic uses per-asset results, which is sufficient for the primary question but does not provide a basket-level comparison.

---

## 9. Operational Complexity vs Return Tradeoff

### Complexity Comparison

| Dimension | 4h DA (conservative) | 1D spot trend | Buy-and-hold |
|---|---|---|---|
| Trades over 5 years | 490 | 41 (BTC) / 40 (ETH) | 1 |
| Trades per year | ~98 | ~8 | 0.2 |
| Signal cadence | 4h bar close | Daily bar close | None |
| Monitoring frequency | Every 4h | Daily | None |
| Execution loop | Required (next 4h open) | Required (next daily open) | None |
| Kill switches | 5+ rules | None documented | None |
| Reconciliation | Required | Not documented | None |
| Data requirements | 4h OHLCV + EMA60 | Daily OHLCV + EMA60 + Donchian20 | None |
| Operational risk | Moderate | Low | None |

### Monitoring Burden

**4h Direction A:** Requires 4h bar monitoring, order execution, position tracking, drawdown monitoring, funding/slippage tracking, kill-switch enforcement. Estimated 15-30 minutes per day during active periods.

**1D spot trend:** Requires daily bar monitoring, order execution. Estimated 5-10 minutes per day. No documented kill switches or reconciliation.

**Buy-and-hold:** Zero monitoring. Buy once, hold.

### Observation Learning Value

**4h Direction A:** High. Tests execution integrity, reconciliation, kill-switch testing, order fill quality, signal-to-order audit. These are the exact skills needed for any future active strategy.

**1D spot trend:** Moderate. Tests daily execution but with fewer operational requirements.

**Buy-and-hold:** None. No operational learning.

### Is the Extra Complexity Justified?

**Yes, by drawdown reduction.** Direction A's 2.6-5.1% MaxDD vs buy-and-hold's 76-79% and 1D spot's 47-68% is the primary justification. The operational complexity of 490 trades over 5 years is a reasonable cost for reducing drawdown by 15-30x.

**Partially, by capital efficiency.** At matched MaxDD, Direction A produces 14-53% more net than benchmarks. The risk-adjusted return justifies the complexity.

**Yes, by learning value.** The observation sleeve (1500U, maxDD 39U) is a low-cost way to build operational capability for any future active strategy.

---

## 10. Decision Implications for Direction A Design

### Continue Design

Direction A's risk-adjusted outperformance vs benchmarks at matched MaxDD supports continued docs-only small-live design. The conservative scenarios (A1/A3) are the most capital-efficient strategies in the comparison.

### What Must Be True Before Execution Decision

1. **1D spot IS/OOS validation.** The 1D spot benchmark must be validated with IS (2021-2023) and OOS (2024-2025) split. If 1D spot BTC's PF advantage (2.044) survives OOS, it strengthens the benchmark case. If it does not, Direction A's position improves further.

2. **1D spot ex-SOL decomposition.** The 1D spot benchmark must show BTC+ETH-only results. If SOL dominates the 1D spot basket, the benchmark is not a valid Phase 1 comparison.

3. **1D spot year-by-year breakdown.** The 1D spot benchmark must show yearly behavior. If 1D spot is also concentrated in 2023 (like Direction A), the concentration argument against Direction A weakens.

4. **Operational rehearsal.** The small-live design plan specifies paper/live-safe rehearsal before any execution. This rehearsal must succeed before any capital deployment.

5. **Owner approval.** The small-live design plan requires explicit Owner approval for capital sleeve, symbols, risk per trade, exposure caps, and stop conditions.

### What Must NOT Happen

- Do not execute without 1D spot robustness validation.
- Do not scale beyond conservative scenarios (A1/A3) without Owner approval.
- Do not add SOL to Phase 1.
- Do not treat this comparison as deployment authorization.

---

## 11. Final Recommendation

### Classification

**B. Continue design but require 1D spot robustness before execution decision**

### Rationale

1. **Direction A is the most capital-efficient strategy at matched MaxDD.** At 2.6% and 5.1% MaxDD bands, Direction A produces 14-53% more net than all benchmarks. This is the strongest argument for continued design.

2. **Buy-and-hold is not a viable alternative.** At 76-79% MaxDD, buy-and-hold is intolerable for the Owner's capital context. When risk-scaled, it produces 51-54% less net than Direction A.

3. **1D spot trend is a preliminary benchmark only.** No IS/OOS, no BTC+ETH aggregate, no ex-SOL decomposition, no year-by-year. The comparison cannot be finalized until these robustness checks exist.

4. **1D spot BTC has higher PF but lower capital efficiency.** 1D spot BTC's PF of 2.044 is higher than Direction A's 1.752, but when risk-scaled to matched MaxDD, 1D spot BTC produces 14-19% less net. The PF advantage does not overcome the MaxDD disadvantage.

5. **1D spot ETH does not outperform.** 1D spot ETH has PF 1.384, MaxDD 67.9%, and produces 83-84% less net than Direction A at matched MaxDD. ETH 1D trend timing is not competitive.

6. **Operational complexity is justified.** 490 trades over 5 years (~2/week) with 4h monitoring is moderate complexity. The drawdown reduction (2.6-5.1% vs 47-79%) and learning value justify the cost.

7. **SOL exclusion is validated.** The comparison uses only BTC and ETH for Direction A. SOL contamination in benchmarks is identified and controlled.

### Whether Owner Decision Is Required Before the Next Diagnostic

**Yes.** The next step is 1D spot robustness validation (IS/OOS, ex-SOL, year-by-year). This requires Owner authorization because:
- It involves running new empirical work on the 1D spot strategy.
- It may change the benchmark comparison.
- It requires decisions about IS/OOS methodology.

### Whether Codex Should Proceed Automatically or Wait

**Wait.** Codex should not proceed to 1D spot robustness validation without Owner authorization. This comparison satisfies the second missing item from the observation value memo. The third item (1D spot robustness) is a separate authorization.

### Whether Any Runtime/Small-Live Implication Exists

**No.** Direction A remains `NON_RUNTIME`. This comparison does not authorize execution, capital allocation, or live trading. It supports continued docs-only design as the most capital-efficient approach, but execution requires 1D spot robustness validation and Owner approval.

---

## Appendix A: Risk-Scaling Methodology

### Linear Approximation

All risk-scaled calculations assume MaxDD scales linearly with allocation:

```
Scaled_MaxDD = Benchmark_MaxDD × (Allocated_Capital / Total_Capital)
```

This is a linear approximation. Actual MaxDD may differ slightly due to:
- Compounding effects (returns/losses affect the base)
- Position sizing interactions
- Drawdown timing vs allocation timing

For small allocation fractions (3-12%), the linear approximation is reasonable. For larger allocations, the error grows.

### Direction A Is Not Scaled Upward

Direction A is used at its documented conservative scenario levels (A1, A3, A5). It is not scaled upward beyond these levels. The comparison asks: "If you had 30k and wanted 2.6% MaxDD, which strategy produces the most net?"

### Capital Allocation Interpretation

The allocation fraction represents the portion of total capital deployed in the benchmark strategy. The remaining capital sits idle (earning zero in this analysis). In practice, idle capital could earn risk-free rate or be deployed in uncorrelated strategies, which would improve the benchmark's total return. However, this improvement is not quantified here.

---

## Appendix B: Calmar Ratio Comparison

Calmar = CAGR / MaxDD. Higher is better.

| Strategy | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|
| 4h DA A1 | 2.9% | 2.6% | 1.12 |
| 4h DA A3 | 5.8% | 5.1% | 1.14 |
| Buy-hold BTC | 24.7% | 76.7% | 0.32 |
| Buy-hold ETH | 32.0% | 79.4% | 0.40 |
| 1D trend BTC | 25.9% | 47.5% | 0.55 |
| 1D trend ETH | 10.0% | 67.9% | 0.15 |

Direction A's Calmar ratio (1.12-1.14) is 2-3x higher than buy-and-hold (0.32-0.40) and 1D trend (0.15-0.55). This confirms Direction A's superior risk-adjusted capital efficiency.

---

## Appendix C: Time-in-Market Efficiency

Net return per 1% time in market:

| Strategy | Net | Time in Mkt | Net per 1% TIM |
|---|---:|---:|---:|
| 4h DA A1 | 4,324 | 38% | 113.8 |
| 4h DA A3 | 8,649 | 38% | 227.6 |
| Buy-hold BTC | 60,429 | 100% | 604.3 |
| Buy-hold ETH | 90,400 | 100% | 904.0 |
| 1D trend BTC | 65,034 | 47.6% | 1,366.3 |
| 1D trend ETH | 18,374 | 44.0% | 417.6 |

By time-in-market efficiency, 1D trend BTC produces the most net per unit of market exposure (1,366). Direction A produces 114-228. Buy-and-hold produces 604-904. This metric favors 1D trend BTC because it captures large moves with few trades.

However, time-in-market efficiency does not account for drawdown. When drawdown is factored in (Calmar ratio), Direction A is superior.

---

## Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-08 | Initial same-risk capital-efficiency comparison | Codex |
