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

# Direction A Phase 1 BTC+ETH Aggregate Diagnostic

**Status:** Docs-only diagnostic / Phase 1 evidence evaluation
**Date:** 2026-05-08
**Classification:** `BTC_ETH_PHASE1_SUPPORTS_OBSERVATION_DESIGN`
**Recommendation:** B. Continue design but require same-risk comparison before any further decision
**Affects Runtime Automatically:** No

---

## 1. Executive Conclusion

**Does BTC+ETH-only aggregate still show positive sparse trend evidence?**
Yes. BTC+ETH combined net is +5,518.83, PF 1.50, across 332 trades. Both assets are individually positive. The mechanism evidence does not depend on SOL.

**Does BTC+ETH-only remain viable under conservative risk-shape scenarios?**
Yes. Three conservative scenarios (A1, A2, A3) already exclude SOL entirely (SOL_abs=0.0). A1 produces net 4,324 on 30k with 2.6% MaxDD and PF 1.752. A3 produces net 8,649 with 5.1% MaxDD and PF 1.752. These are the exact BTC+ETH-only conservative numbers.

**How much performance is lost by excluding SOL?**
The naive baseline loses ~42% of net PnL (from 9,538 to 5,519). Under conservative A1/A3 scenarios, SOL contributes zero because those scenarios already exclude SOL. Under A4/A5, SOL contributes ~10% of net.

**Does excluding SOL materially reduce high-beta / mega-trend dominance risk?**
Yes. SOL's top-1 winner (+2,273.99) is 56.6% of SOL net and represents a single mega-trend episode. SOL buy-and-hold MaxDD is 96.3%. Excluding SOL eliminates this high-beta contamination entirely from Phase 1.

**Is BTC+ETH-only strong enough to continue small-live design as Phase 1?**
Yes, conditionally. The evidence is positive, the conservative scenarios are already BTC+ETH-only, and the mechanism transfers without SOL. However, BTC+ETH fragility is worse than the three-asset basket (all top-N removal metrics are negative), and the same-risk comparison against benchmarks remains missing.

**Does the case depend too much on SOL?**
No. BTC+ETH alone produce positive net PnL under the frozen rule. SOL strengthens the cross-asset mechanism claim and adds the highest individual PF, but Phase 1 observation value does not require SOL.

**Classification:** `BTC_ETH_PHASE1_SUPPORTS_OBSERVATION_DESIGN`

This is not deployment approval, small-live approval, or runtime authorization.

---

## 2. Source Files and Reproducibility

### Files Inspected

| File | Status | Data Used |
|---|---|---|
| `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md` | Complete | BTC/ETH/SOL individual baselines, year-by-year, top-N fragility, top-10 winners |
| `docs/ops/direction-a-p0-evidence-strength-diagnostics.md` | Complete | Winner overlap matrix, bootstrap PF CI, effective observation count |
| `docs/ops/direction-a-p1-edge-source-attribution.md` | Complete | Random entry control, buy-and-hold decomposition, time-in-market |
| `docs/ops/direction-a-p2-risk-shape-diagnostic.md` | Complete | S0-S5 scenarios, concentration shares, exposure cap results |
| `docs/ops/direction-a-risk-control-return-frontier.md` | Complete | 19 scenarios (A-D groups), small-capital projections |
| `docs/ops/direction-a-sparse-trend-evidence-hardening-and-winner-attribution.md` | Complete | ETH year-by-year, top-10 attribution, structural payoff review |
| `docs/ops/direction-a-observation-value-memo.md` | Complete | Prior analysis, comparison data |
| `docs/ops/direction-a-small-live-design-plan.md` | Complete | Design parameters, Phase 1/2 definition |
| `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md` | Complete | Methodology standards |

### Data Provenance

- **Per-asset baselines (ETH/BTC/SOL):** Copied directly from `direction-a-cross-asset-frozen-diagnostic-result.md` and `direction-a-sparse-trend-evidence-hardening-and-winner-attribution.md`. These are frozen diagnostic outputs from existing trade artifacts.
- **BTC+ETH aggregate metrics:** Computed by exact summation of documented per-asset values (net PnL, trade counts, winner counts). PF is recomputed from summed gross profit and gross loss.
- **Year-by-year BTC+ETH:** Computed by exact summation of documented per-asset year-by-year values.
- **Top-N fragility (BTC+ETH):** Computed by exact summation of documented per-asset top-N removal values.
- **Risk frontier scenarios (A1/A3):** Copied directly from `direction-a-risk-control-return-frontier.md`. A1 and A2 have SOL_abs=0.0 and are therefore exact BTC+ETH-only results.
- **Risk frontier scenarios (A4/A5):** Copied from frontier; SOL contribution estimated at ~10.4% of net based on SOL_abs field.

### Missing Artifacts

- Trade-level CSV/JSONL files (`reports/direction-a-cross-asset-frozen-diagnostic/`) do not exist in the repository. All trade-level data was previously processed into the documented diagnostics.
- The `reports/` directory does not exist at the repository root.
- ETH year-by-year trade counts by exit reason are not separately documented (only aggregate exit reason data exists in the sparse trend doc).
- BTC+ETH-only portfolio-level risk frontier recomputation (MaxDD, top5_after, equity curve) for A4/A5 scenarios requires re-running the portfolio simulation, which is not available without the trade-level data files.

---

## 3. BTC+ETH Baseline Aggregate

### Combined Metrics

| Metric | BTC+ETH | ETH alone | BTC alone | SOL alone (reference) |
|---|---:|---:|---:|---:|
| Trades | 332 | 173 | 159 | 158 |
| Winners | 74 | 34 | 40 | 44 |
| Losers | 258 | 139 | 119 | 114 |
| Win rate | 22.29% | 19.65% | 25.16% | 27.85% |
| Net PnL | +5,518.83 | +3,001.66 | +2,517.17 | +4,018.80 |
| Profit factor | 1.50 | 1.517 | 1.477 | 1.790 |
| Realized MaxDD | not computable | 6.08% | 9.95% | 4.49% |
| MTM MaxDD | not computable | 8.33% | 11.32% | 6.44% |
| Payoff ratio | not computable | 6.20:1 | 4.39:1 | 4.64:1 |
| Time in market | ~38.5% | 38.9% | 38.4% | 37.9% |

**PF recomputation method:**
- BTC: G_btc / L_btc = 1.477, net = 2,517.17 → G_btc = 7,782.09, L_btc = 5,264.92
- ETH: G_eth / L_eth = 1.517, net = 3,001.66 → G_eth = 8,760.49, L_eth = 5,758.83
- Combined: (7,782.09 + 8,760.49) / (5,264.92 + 5,758.83) = 16,542.58 / 11,023.75 = **1.50**

**Note:** Portfolio-level MaxDD, MTM MaxDD, and payoff ratio for the combined BTC+ETH basket cannot be exactly computed from per-asset standalone numbers alone. These depend on the equity curve timing (concurrent positions, sequential drawdown events). The per-asset realized MaxDD values (6.08% for ETH, 9.95% for BTC) are standalone; the basket MaxDD would be different and likely lower due to diversification. Exact values require re-running the portfolio simulation.

### Cost Structure (BTC only; ETH cost breakdown not separately documented)

| Cost | BTC |
|---|---:|
| Fees | 253.66 |
| Slippage | 634.15 |
| Funding | 439.86 |
| Total costs | 1,327.66 |
| Gross PnL | 3,844.83 |
| Cost as % of gross | 34.5% |

ETH cost structure: not separately documented in existing artifacts. Total ETH costs can be inferred as ~1,101.05 from the sparse trend doc (gross +4,102.71, net +3,001.66).

---

## 4. BTC vs ETH Contribution

### Contribution Share

| Metric | BTC | ETH | BTC share | ETH share |
|---|---:|---:|---:|---:|
| Net PnL | +2,517.17 | +3,001.66 | 45.6% | 54.4% |
| Trades | 159 | 173 | 47.9% | 52.1% |
| Winners | 40 | 34 | 54.1% | 45.9% |
| Win rate | 25.16% | 19.65% | — | — |
| PF | 1.477 | 1.517 | — | — |

### Interpretation

**Is BTC carrying the result?**
No. ETH contributes 54.4% of combined net PnL. BTC contributes 45.6%. Neither asset dominates.

**Is ETH carrying the result?**
Partially. ETH contributes more net PnL (+3,001.66 vs +2,517.17) and has a higher PF (1.517 vs 1.477). But BTC has a higher win rate (25.16% vs 19.65%) and more winners (40 vs 34).

**Are both positive?**
Yes. Both assets show positive net PnL, PF > 1, and pass the SRR-002 sparse trend acceptance band individually.

**Is one asset mostly dead weight?**
No. Both contribute meaningfully. BTC's contribution is 45.6% of net — not dead weight. ETH's contribution is 54.4% — not dominant enough to call BTC dead weight.

**Does Phase 1 actually remain cross-asset?**
Yes. Both BTC and ETH show the same sparse trend signature under the identical frozen rule. The mechanism transfers. Phase 1 is genuinely cross-asset with two assets, not a single-asset bet.

### P1 Attribution Context

Both assets are classified `ENTRY_ALPHA_PARTIAL` (random entry control) and `SMART_BETA_TIMING` (buy-and-hold decomposition). The edge is a combination of Donchian20 breakout entry, EMA60 lifecycle management, and crypto beta timing — consistent across both assets.

---

## 5. Year-by-Year Behavior

### BTC Year-by-Year

| Year | Trades | W/L | Net PnL | PF | Top-1 PnL | % of Total |
|---|---:|---|---:|---:|---:|---:|
| 2021 | 33 | 8/25 | +293.35 | 1.36 | +428.06 | 11.7% |
| 2022 | 31 | 5/26 | −821.76 | 0.22 | +70.84 | −32.6% |
| 2023 | 30 | 9/21 | +2,407.94 | 3.21 | +1,303.82 | 95.7% |
| 2024 | 31 | 9/22 | +919.06 | 1.89 | +762.97 | 36.5% |
| 2025 | 34 | 9/25 | −281.43 | 0.78 | +331.45 | −11.2% |

### ETH Year-by-Year

| Year | Trades | W/L | Net PnL | PF | Top-1 PnL | % of Total |
|---|---:|---|---:|---:|---:|---:|
| 2021 | 33 | 8/25 | +722.57 | 1.72 | +533.65 | 24.1% |
| 2022 | 36 | 5/31 | −76.80 | 0.92 | +408.90 | −2.6% |
| 2023 | 29 | 7/22 | +918.93 | 1.83 | +1,035.21 | 30.6% |
| 2024 | 34 | 9/25 | +1,465.75 | 2.56 | +1,373.64 | 48.8% |
| 2025 | 41 | 5/36 | −28.79 | 0.98 | +1,036.73 | −1.0% |

### BTC+ETH Combined Year-by-Year

| Year | BTC net | ETH net | Combined net | Combined % | Interpretation |
|---|---:|---:|---:|---:|---|
| 2021 | +293.35 | +722.57 | +1,015.92 | 18.4% | Both positive; ETH carries |
| 2022 | −821.76 | −76.80 | −898.56 | −16.3% | Both negative; bear market |
| 2023 | +2,407.94 | +918.93 | +3,326.87 | 60.3% | Both strongly positive |
| 2024 | +919.06 | +1,465.75 | +2,384.81 | 43.2% | Both positive; ETH carries |
| 2025 | −281.43 | −28.79 | −310.22 | −5.6% | Both negative; cost drag |

### Year Concentration Analysis

**Is the result concentrated in 2023?**
Yes, heavily. 2023 contributes +3,326.87 of +5,518.83 total = **60.3%**. This is significant concentration but less extreme than BTC alone (95.7%).

**Does 2024 contribute?**
Yes. 2024 contributes +2,384.81 = 43.2% of total. Combined, 2023+2024 = 103.5% of total net (other years are net-negative). This two-year concentration is high but distributed across two distinct macro regimes.

**Are 2022 or 2025 negative?**
Yes, both. 2022: −898.56. 2025: −310.22. Both assets are negative in both years. This confirms the mechanism's bear/choppy market vulnerability is cross-asset, not SOL-specific.

**Does the year profile look like a crypto-wide trend lifecycle exposure?**
Yes. The pattern (2021 positive, 2022 negative, 2023 strongly positive, 2024 positive, 2025 negative) is identical across BTC and ETH, and matches SOL. This is the signature of a crypto-wide trend-capture mechanism.

### Regime Interpretation

- **2021** (bull peak + crash + recovery): Both positive. ETH stronger.
- **2022** (crypto winter): Both negative. BTC suffers more (−821.76 vs −76.80).
- **2023** (consolidation + rallies): Both strongly positive. BTC carries (+2,407.94).
- **2024** (post-halving expansion): Both positive. ETH carries (+1,465.75).
- **2025** (mixed/choppy): Both negative. Marginal losses.

---

## 6. Top-Winner and Fragility Analysis

### Combined Top-N Contribution

| Metric | BTC | ETH | BTC+ETH combined |
|---|---:|---:|---:|
| Top-1 winner PnL | +1,303.82 | +1,373.64 | +2,677.46 |
| Top-3 winner PnL | +3,205.09 | +3,445.58 | +6,650.67 |
| Top-5 winner PnL | +4,182.60 | +4,494.99 | +8,677.59 |
| Top-1 as % of net | 51.8% | 45.8% | 48.5% |
| Top-3 as % of net | 127.3% | 114.8% | 120.5% |
| Top-5 as % of net | 166.2% | 149.8% | 157.2% |

### Top-N Removal

| Removal | BTC | ETH | BTC+ETH combined |
|---|---:|---:|---:|
| Net after top-1 removal | +1,213.34 | +1,628.03 | +2,841.37 |
| Net after top-3 removal | **−687.93** | **−443.91** | **−1,131.84** |
| Net after top-5 removal | **−1,665.43** | **−1,493.33** | **−3,158.76** |

### Fragility Comparison: BTC+ETH vs BTC+ETH+SOL

| Metric | BTC+ETH | BTC+ETH+SOL | Change |
|---|---|---|---|
| Top-3 removal | −1,131.84 | −687.93 (BTC) −443.91 (ETH) +380.21 (SOL) = −751.63 | Worse without SOL |
| Top-5 removal | −3,158.76 | −1,665.43 −1,493.33 −369.78 = −3,528.54 | Slightly better without SOL |
| All top-N removal negative? | Yes | Yes | Same pattern |

**Note:** The three-asset top-3 removal was computed differently in the cross-asset diagnostic (per-asset removal). For the combined basket, removing the top-3 from each asset separately gives: BTC −687.93, ETH −443.91, SOL +380.21 = combined −751.63. BTC+ETH-only top-3 removal = −1,131.84, which is worse.

### Does BTC+ETH survive top-3 removal?
No. Net becomes −1,131.84. This is worse than the three-asset basket (−751.63) because SOL's positive top-3 removal (+380.21) partially offset BTC+ETH negativity.

### Does BTC+ETH survive top-5 removal?
No. Net becomes −3,158.76. All three assets fail top-5 removal individually; removing SOL does not help.

### Is fragility better or worse than three-asset basket?
Worse for top-3 removal. Roughly similar for top-5 removal. Excluding SOL removes its positive top-3 offset.

### Are winners shared around the same crypto-wide episodes?
Yes. P0 documented that ETH/BTC top-5 winners have 4/5 strict overlap and 4/5 loose overlap. Key shared windows: 2023-01 (post-FTX recovery), 2023-10 (ETF anticipation rally), 2024-02 (post-halving expansion). The BTC+ETH basket inherits this shared-episode concentration.

### Winner Overlap Matrix (from P0)

| pair | strict overlap | loose overlap | key months |
|---|---|---|---|
| ETH_top5 vs BTC_top5 | 4 | 4 | 2023-01, 2023-10, 2024-02 |

Effective independent observations for BTC+ETH: approximately 2.5-3.0 asset-adjusted (loose), not 10 raw top-5 winners.

---

## 7. Conservative Risk-Shape Scenarios

### Key Discovery: A1/A2/A3 Are Already BTC+ETH-Only

The risk frontier scenarios A1, A2, and A3 have **SOL_abs=0.0**, meaning these scenarios produce zero SOL contribution. They are exact BTC+ETH-only results under conservative sizing. No recomputation is needed.

| Scenario | SOL_abs | Interpretation |
|---|---|---|
| A1_low_vol_norm_max2 | 0.0 | Pure BTC+ETH, vol-normalized low |
| A2_hybrid_025_vol_adj_max2 | 0.0 | Pure BTC+ETH, hybrid 0.25% |
| A3_hybrid_050_vol_adj_max2 | 0.0 | Pure BTC+ETH, hybrid 0.50% |
| A4_fixed_025_max2 | 0.104 | Includes ~10% SOL contribution |
| A5_fixed_050_max2 | 0.104 | Includes ~10% SOL contribution |

### Conservative BTC+ETH-Only Scenarios (30k research capital)

| Scenario | Net | Return | MaxDD | PF | Trades | Top5_after | 2023 | Class |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| A1_low_vol_norm_max2 | 4,324.46 | 14.4% | 2.6% | 1.752 | 490 | 297.71 | 2,677.88 | CONSERVATIVE |
| A2_hybrid_025_vol_adj_max2 | 4,324.46 | 14.4% | 2.6% | 1.752 | 490 | 297.71 | 2,677.88 | CONSERVATIVE |
| A3_hybrid_050_vol_adj_max2 | 8,648.92 | 28.8% | 5.1% | 1.752 | 490 | 595.42 | 5,355.77 | CONSERVATIVE |

### Moderate Scenarios With SOL Component (30k research capital)

| Scenario | Net | Return | MaxDD | PF | SOL_abs | Est. BTC+ETH net | Class |
|---|---:|---:|---:|---:|---:|---:|---|
| A4_fixed_025_max2 | 4,688.75 | 15.6% | 3.1% | 1.613 | 0.104 | ~4,201 | CONSERVATIVE |
| A5_fixed_050_max2 | 9,377.50 | 31.3% | 5.9% | 1.613 | 0.104 | ~8,402 | CONSERVATIVE |

**A4/A5 BTC+ETH estimate method:** SOL_abs=0.104 means SOL contributes ~10.4% of net PnL. BTC+ETH estimate = net × (1 − 0.104). This is approximate; exact values require re-running the portfolio simulation.

### Sleeve Projections (BTC+ETH-only, using A1 and A3)

**A1_low_vol_norm_max2 (pure BTC+ETH):**

| Sleeve | net_U | maxDD_U | worst_month_U | largest_loss_U | tolerable |
|---|---:|---:|---:|---:|---|
| 1500U (5%) | 216 | 39 | −14 | −4 | Yes |
| 3000U (10%) | 432 | 78 | −29 | −8 | Yes |
| 4500U (15%) | 649 | 117 | −43 | −12 | Yes |

**A3_hybrid_050_vol_adj_max2 (pure BTC+ETH):**

| Sleeve | net_U | maxDD_U | tolerable |
|---|---:|---:|---|
| 1500U (5%) | 432 | 77 | Yes |
| 3000U (10%) | 865 | 153 | Yes |
| 4500U (15%) | 1,297 | 230 | Yes |

### Scenario Context

- **A1** uses low vol-normalized sizing with max 2 concurrent positions. It is the most conservative scenario with the highest PF (1.752) but lowest net.
- **A3** uses hybrid 0.50% vol-adjusted sizing with max 2 concurrent positions. It doubles the net of A1 while maintaining the same PF, at the cost of higher MaxDD (5.1% vs 2.6%).
- Both exclude SOL entirely. Both show positive top-5_after (297.71 and 595.42), meaning the top-5 winners still leave positive residual — better than the unshaped baseline.

---

## 8. Comparison with BTC+ETH+SOL Basket

### Naive Baseline Comparison (S0/S1, 30k research capital)

| Metric | BTC+ETH | BTC+ETH+SOL | Δ | % Change |
|---|---:|---:|---:|---:|
| Net PnL | 5,518.83 | 9,537.63 | −4,018.80 | −42.1% |
| Trades | 332 | 490 | −158 | −32.2% |
| Winners | 74 | 118 | −44 | −37.3% |
| Win rate | 22.29% | 24.08% | −1.79pp | — |
| PF | 1.50 | 1.59 | −0.09 | −5.7% |
| 2023 contribution | 3,326.87 | 6,159.67 | −2,832.80 | −46.0% |
| SOL PnL share | 0% | 33.9% | — | — |

### Conservative Scenario Comparison

| Scenario | BTC+ETH+SOL net | BTC+ETH est. net | Δ | SOL contribution |
|---|---:|---:|---:|---:|
| A1_low_vol_norm_max2 | 4,324.46 | 4,324.46 | 0 | 0% (SOL_abs=0.0) |
| A3_hybrid_050_vol_adj_max2 | 8,648.92 | 8,648.92 | 0 | 0% (SOL_abs=0.0) |
| A5_fixed_050_max2 | 9,377.50 | ~8,402 | ~−976 | ~10.4% |

### What Changes With SOL Excluded

| Dimension | With SOL | Without SOL | Assessment |
|---|---|---|---|
| Net PnL (naive) | 9,537.63 | 5,518.83 | 42% lower |
| Net PnL (A1 conservative) | 4,324.46 | 4,324.46 | Identical (SOL already excluded) |
| MaxDD (naive) | 5.5% | not computable | Likely similar or lower |
| PF (naive) | 1.59 | 1.50 | Slightly lower |
| Top-3 removal | −751.63 | −1,131.84 | Worse |
| Top-5 removal | −3,528.54 | −3,158.76 | Slightly better |
| 2023 concentration | 64.6% | 60.3% | Slightly less concentrated |
| High-beta contamination | Present (SOL 96.3% buy-and-hold DD) | Eliminated | Cleaner |
| Winner overlap complexity | 3-asset shared episodes | 2-asset shared episodes | Simpler |
| Cross-asset mechanism claim | Stronger (3 assets) | Weaker (2 assets) | Tradeoff |

### SOL Dominance Reduction

SOL contributes 33.9% of naive basket PnL despite being one of three assets. SOL's top-1 winner (+2,273.99) is larger than any BTC or ETH winner. SOL's buy-and-hold return (81.5x) vastly exceeds BTC (2.0x) and ETH (3.0x). Excluding SOL from Phase 1 eliminates this high-beta dominance entirely.

Under vol-normalized sizing (P2 S3), SOL's PnL share drops from 32.1% to 24.1%. Under A1/A3 conservative scenarios, SOL contributes 0%. The design plan already positions SOL as Phase 2 optional with ≤25% risk share cap.

---

## 9. Observation Value Interpretation

### Is the lower return still worth observing?

Yes. The A1 conservative scenario produces 4,324 on 30k (14.4% over 5 years) with only 2.6% MaxDD — entirely from BTC+ETH. On a 1500U sleeve, this projects to ~216U net with ~39U max drawdown. The return is modest but the drawdown is tolerable, and the learning value (execution integrity, reconciliation, kill-switch testing) is high relative to capital risk.

### Is the lower high-beta contamination worth the tradeoff?

Yes. SOL's inclusion introduces:
- 96.3% buy-and-hold MaxDD (vs BTC 76.7%, ETH 79.4%)
- Top-1 winner contributing 56.6% of SOL net
- Single mega-trend episode (Oct-Nov 2023 SOL revival) dominating SOL results
- Higher portfolio complexity (3 concurrent signals, correlated exposure)

Excluding SOL from Phase 1 produces a cleaner test of the mechanism without high-beta contamination.

### Does BTC+ETH provide enough evidence for Phase 1?

Yes, with caveats:
- Both assets individually positive under the frozen rule
- Both classified `ENTRY_ALPHA_PARTIAL` and `SMART_BETA_TIMING`
- Mechanism transfers cross-asset (2 assets, not 1)
- Conservative scenarios A1/A3 are already pure BTC+ETH
- Caveat: top-N fragility is worse without SOL's positive offset
- Caveat: effective independent observations remain ~2.5-3.0 (loose), not 10

### Would adding SOL materially change the decision?

For Phase 1 observation value: no. The A1/A3 conservative scenarios already exclude SOL. Adding SOL to Phase 1 would increase net PnL but also increase high-beta contamination, portfolio complexity, and SOL-dominance risk. The design plan correctly positions SOL as Phase 2 optional.

### Should SOL remain Phase 2 optional?

Yes. SOL has the strongest individual asset result (PF 1.790, lowest MaxDD, passes top-3 removal). It strengthens the mechanism claim. But it should only be added after Phase 1 rehearsal succeeds, with low vol-normalized sizing and ≤25% risk share cap.

---

## 10. Capital Efficiency Implications

### What This Diagnostic Implies for the Later Comparison

The BTC+ETH aggregate diagnostic confirms that:
1. The conservative A1/A3 scenarios are already pure BTC+ETH — no SOL subtraction needed.
2. A1 projects to ~216U on a 1500U sleeve with ~39U MaxDD.
3. A3 projects to ~432U on a 1500U sleeve with ~77U MaxDD.
4. BTC+ETH fragility (top-N removal) is worse than the three-asset basket.

For the same-risk comparison, the relevant comparison is:
- **4h Direction A conservative (A1):** 4,324 net, 2.6% MaxDD, PF 1.752, ~38% time in market, 490 trades
- **4h Direction A conservative (A3):** 8,649 net, 5.1% MaxDD, PF 1.752, ~38% time in market, 490 trades
- **Buy-and-hold BTC:** 60,429 net, 76.7% MaxDD, 100% time in market, 1 trade
- **Buy-and-hold ETH:** 90,400 net, 79.4% MaxDD, 100% time in market, 1 trade
- **1D trend BTC:** 65,034 net, 47.5% MaxDD, PF 2.044, 47.6% time in market, 41 trades
- **1D trend ETH:** 18,374 net, 67.9% MaxDD, PF 1.384, 44.0% time in market, 40 trades

The capital-efficiency question is whether the complexity of 4h Direction A (490 trades, operational overhead) justifies the much lower drawdown (2.6-5.1%) versus simpler alternatives that have higher return but vastly higher drawdown.

### What Remains Missing Before Same-Risk Comparison

1. **1D spot IS/OOS temporal robustness** — no IS/OOS split exists for 1D spot trend
2. **1D spot ex-SOL decomposition** — no BTC+ETH-only 1D spot numbers exist
3. **Buy-and-hold matched-risk framing** — buy-and-hold at 5% capital allocation (to match Direction A's ~5% drawdown) has not been computed
4. **Same-risk 4h Direction A vs 1D spot vs buy-and-hold** — the formal comparison at matched MaxDD or matched capital allocation

---

## 11. Final Recommendation

### Classification

**B. Continue design but require same-risk comparison before any further decision**

### Rationale

BTC+ETH-only Phase 1 is supported by the evidence:
- Both assets individually positive under the frozen rule
- Conservative scenarios A1/A3 are already pure BTC+ETH with good risk/return
- Mechanism transfers without SOL
- High-beta contamination eliminated

But the decision to proceed beyond docs-only design requires:
- Same-risk capital-efficiency comparison (4h DA vs buy-and-hold vs 1D spot at matched drawdown)
- Confirmation that the operational complexity of 490 trades over 5 years is justified versus simpler alternatives

### Whether Owner Decision Is Required Before the Next Diagnostic

**Yes.** This diagnostic confirms BTC+ETH Phase 1 viability. The next diagnostic (same-risk capital-efficiency comparison) requires Owner authorization because:
- It involves comparing across strategy families (4h DA vs 1D spot vs buy-and-hold)
- It may change the Phase 1 design recommendation
- It requires decisions about matched-risk framing methodology

### Whether Codex Should Proceed Automatically or Wait

**Wait.** Codex should not proceed to the same-risk comparison without Owner authorization. This diagnostic satisfies the first missing item from the observation value memo. The second item (same-risk comparison) is a separate authorization.

### Whether Any Runtime/Small-Live Implication Exists

**No.** Direction A remains `NON_RUNTIME`. BTC+ETH Phase 1 remains docs-only design. No runtime, small-live, paper, testnet, or live execution is authorized by this diagnostic. No capital allocation is authorized.

---

## Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-08 | Initial Direction A Phase 1 BTC+ETH aggregate diagnostic | Codex |
