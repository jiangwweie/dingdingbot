# Direction A Risk-Control Return Frontier Diagnostic

**Status:** Completed / diagnostic only  
**Date:** 2026-05-08  
**Classification:** `RETURN_FRONTIER_SHOWS_USABLE_CONSERVATIVE_RANGE`  
**Historical Max Classification:** `HISTORICAL_MAX_ONLY_NOT_RECOMMENDED`  
**Small-live Relevance:** `SUPPORTS_SMALL_LIVE_DESIGN_CONSERVATIVE`  
**Recommendation:** A. Continue with docs-only small-live design using conservative scenario  
**Affects Runtime Automatically:** No

---

## 1. Boundary

This report estimates the historical return/risk envelope of Direction A under pre-declared risk-control and sizing scenarios. It uses only existing ETH/BTC/SOL Direction A trade artifacts. It does not change Direction A entry/exit rules, assets, signals, stops, Donchian/EMA parameters, or runtime behavior.

It does not authorize risk module implementation, runtime use, small-live use, live execution, capital allocation, Direction A changes, parameter optimization, portfolio/router work, TE execution, CPM reopening, or strategy rescue.

## 2. Inputs Inspected

- `docs/ops/direction-a-p2-risk-shape-diagnostic.md`
- `reports/direction-a-p2-risk-shape-diagnostic/p2_summary.json`
- `reports/direction-a-p2-risk-shape-diagnostic/risk_shape_scenarios.json`
- `reports/direction-a-p2-risk-shape-diagnostic/portfolio_equity_curves.csv`
- `reports/direction-a-p2-risk-shape-diagnostic/portfolio_drawdown_summary.json`
- `reports/direction-a-p2-risk-shape-diagnostic/risk_contribution_summary.json`
- `docs/ops/direction-a-p1-edge-source-attribution.md`
- `docs/ops/direction-a-p0-evidence-strength-diagnostics.md`
- `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/trades.jsonl`
- `reports/direction-a-cross-asset-frozen-diagnostic/btc_trades.csv`
- `reports/direction-a-cross-asset-frozen-diagnostic/sol_trades.csv`


## 3. Why This Is Not Optimization

The scenario set was declared before execution and limited to the requested A/B/C/D groups. No entry/exit rule was changed. No regime filters, asset additions, parameter sweeps, or signal reruns were performed. The highest historical return is treated as a diagnostic endpoint, not a selected deployment configuration.

## 4. Scenario Definitions

Scenario groups:

- Group A conservative: observation-friendly fixed/vol/hybrid risk with max 2 concurrent positions.
- Group B moderate: higher return while retaining concentration controls.
- Group C aggressive historical envelope: explicitly `NOT_ELIGIBLE_FOR_SMALL_LIVE_DEFAULT`.
- Group D drawdown throttle: fixed drawdown thresholds only, no tuning.

## 5. Historical Maximum Return

| metric | scenario | net | dd | group |
| --- | --- | --- | --- | --- |
| highest_net_pnl | C3_fixed_200_max3 | 53696.17 | 0.21 | C |
| highest_return_on_sleeve | C3_fixed_200_max3 | 53696.17 | 0.21 | C |
| highest_pf | A1_low_vol_norm_max2 | 4324.46 | 0.026 | A |
| highest_return_dd_below_5 | A4_fixed_025_max2 | 4688.75 | 0.031 | A |
| highest_return_dd_below_8 | B1_fixed_050_max3 | 13424.04 | 0.074 | B |
| highest_return_max2 | B2_fixed_100_max2 | 18755.01 | 0.108 | B |
| highest_return_excluding_aggressive | B2_fixed_100_max2 | 18755.01 | 0.108 | B |


Highest historical return scenario is `C3_fixed_200_max3` and is classified as `HISTORICAL_MAX_ONLY_NOT_RECOMMENDED`. It must not be treated as a recommendation unless it also satisfies conservative risk constraints.

## 6. Risk-Adjusted Frontier

| scenario | group | class | net | ret | dd | pf | pnl/dd | top5_after | 2023 | SOL_abs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C3_fixed_200_max3 | C | AGGRESSIVE_HISTORICAL_ENVELOPE | 53696.17 | 1.79 | 0.21 | 1.659 | 8.52 | 14302.5 | 34203.98 | 0.406 |
| C5_compound_fixed_100_max3 | C | AGGRESSIVE_HISTORICAL_ENVELOPE | 38444.25 | 1.281 | 0.161 | 1.537 | 7.95 | 7046.92 | 24212.89 | 0.383 |
| C2_fixed_150_max3 | C | AGGRESSIVE_HISTORICAL_ENVELOPE | 40272.13 | 1.342 | 0.175 | 1.659 | 7.68 | 10726.87 | 25652.99 | 0.406 |
| C1_fixed_100_max3 | C | AGGRESSIVE_HISTORICAL_ENVELOPE | 26848.08 | 0.895 | 0.131 | 1.659 | 6.85 | 7151.25 | 17101.99 | 0.406 |
| C4_high_vol_norm_max3 | C | AGGRESSIVE_HISTORICAL_ENVELOPE | 26038.21 | 0.868 | 0.131 | 1.649 | 6.61 | 6341.37 | 17145.15 | 0.385 |
| B1_fixed_050_max3 | B | MODERATE_RESEARCH_CANDIDATE | 13424.04 | 0.447 | 0.074 | 1.659 | 6.02 | 3575.62 | 8551.0 | 0.406 |
| D2_fixed_100_max2_reduce50_after_dd5 | D | MODERATE_RESEARCH_CANDIDATE | 15813.91 | 0.527 | 0.088 | 1.565 | 5.99 | 2302.83 | 7728.98 | 0.143 |
| B2_fixed_100_max2 | B | MODERATE_RESEARCH_CANDIDATE | 18755.01 | 0.625 | 0.108 | 1.613 | 5.8 | 2326.08 | 10961.39 | 0.104 |
| A3_hybrid_050_vol_adj_max2 | A | CONSERVATIVE_OBSERVATION_CANDIDATE | 8648.92 | 0.288 | 0.051 | 1.752 | 5.67 | 595.42 | 5355.77 | 0.0 |
| A1_low_vol_norm_max2 | A | CONSERVATIVE_OBSERVATION_CANDIDATE | 4324.46 | 0.144 | 0.026 | 1.752 | 5.54 | 297.71 | 2677.88 | 0.0 |
| A2_hybrid_025_vol_adj_max2 | A | CONSERVATIVE_OBSERVATION_CANDIDATE | 4324.46 | 0.144 | 0.026 | 1.752 | 5.54 | 297.71 | 2677.88 | 0.0 |
| B4_moderate_vol_norm_max3 | B | MODERATE_RESEARCH_CANDIDATE | 12197.15 | 0.407 | 0.074 | 1.65 | 5.47 | 2348.73 | 8416.9 | 0.36 |
| A5_fixed_050_max2 | A | CONSERVATIVE_OBSERVATION_CANDIDATE | 9377.5 | 0.313 | 0.059 | 1.613 | 5.32 | 1163.04 | 5480.7 | 0.104 |
| D3_fixed_050_max2_pause_after_dd8 | D | MODERATE_RESEARCH_CANDIDATE | 9377.5 | 0.313 | 0.059 | 1.613 | 5.32 | 1163.04 | 5480.7 | 0.104 |
| A4_fixed_025_max2 | A | CONSERVATIVE_OBSERVATION_CANDIDATE | 4688.75 | 0.156 | 0.031 | 1.613 | 5.08 | 581.52 | 2740.35 | 0.104 |
| D1_fixed_050_max2_reduce50_after_dd5 | D | MODERATE_RESEARCH_CANDIDATE | 8694.73 | 0.29 | 0.057 | 1.578 | 5.06 | 1009.37 | 4769.11 | 0.115 |
| B5_hybrid_100_vol_adj_max2 | B | MODERATE_RESEARCH_CANDIDATE | 17126.4 | 0.571 | 0.115 | 1.601 | 4.98 | 697.47 | 10683.38 | 0.007 |
| B3_moderate_vol_norm_max2 | B | MODERATE_RESEARCH_CANDIDATE | 8563.2 | 0.285 | 0.061 | 1.601 | 4.67 | 348.74 | 5341.69 | 0.007 |
| D4_fixed_100_max2_pause_after_dd8 | D | OVERFIT_OR_UNACCEPTABLE_RISK | 2957.97 | 0.099 | 0.082 | 1.289 | 1.2 | -3414.7 | 0 | 0.508 |


## 7. Conservative / Moderate / Aggressive Scenario Split

| scenario | group | class | net | ret | dd | pf | pnl/dd | top5_after | 2023 | SOL_abs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1_low_vol_norm_max2 | A | CONSERVATIVE_OBSERVATION_CANDIDATE | 4324.46 | 0.144 | 0.026 | 1.752 | 5.54 | 297.71 | 2677.88 | 0.0 |
| A2_hybrid_025_vol_adj_max2 | A | CONSERVATIVE_OBSERVATION_CANDIDATE | 4324.46 | 0.144 | 0.026 | 1.752 | 5.54 | 297.71 | 2677.88 | 0.0 |
| A3_hybrid_050_vol_adj_max2 | A | CONSERVATIVE_OBSERVATION_CANDIDATE | 8648.92 | 0.288 | 0.051 | 1.752 | 5.67 | 595.42 | 5355.77 | 0.0 |
| A4_fixed_025_max2 | A | CONSERVATIVE_OBSERVATION_CANDIDATE | 4688.75 | 0.156 | 0.031 | 1.613 | 5.08 | 581.52 | 2740.35 | 0.104 |
| A5_fixed_050_max2 | A | CONSERVATIVE_OBSERVATION_CANDIDATE | 9377.5 | 0.313 | 0.059 | 1.613 | 5.32 | 1163.04 | 5480.7 | 0.104 |
| B1_fixed_050_max3 | B | MODERATE_RESEARCH_CANDIDATE | 13424.04 | 0.447 | 0.074 | 1.659 | 6.02 | 3575.62 | 8551.0 | 0.406 |
| B2_fixed_100_max2 | B | MODERATE_RESEARCH_CANDIDATE | 18755.01 | 0.625 | 0.108 | 1.613 | 5.8 | 2326.08 | 10961.39 | 0.104 |
| B3_moderate_vol_norm_max2 | B | MODERATE_RESEARCH_CANDIDATE | 8563.2 | 0.285 | 0.061 | 1.601 | 4.67 | 348.74 | 5341.69 | 0.007 |
| B4_moderate_vol_norm_max3 | B | MODERATE_RESEARCH_CANDIDATE | 12197.15 | 0.407 | 0.074 | 1.65 | 5.47 | 2348.73 | 8416.9 | 0.36 |
| B5_hybrid_100_vol_adj_max2 | B | MODERATE_RESEARCH_CANDIDATE | 17126.4 | 0.571 | 0.115 | 1.601 | 4.98 | 697.47 | 10683.38 | 0.007 |
| C1_fixed_100_max3 | C | AGGRESSIVE_HISTORICAL_ENVELOPE | 26848.08 | 0.895 | 0.131 | 1.659 | 6.85 | 7151.25 | 17101.99 | 0.406 |
| C2_fixed_150_max3 | C | AGGRESSIVE_HISTORICAL_ENVELOPE | 40272.13 | 1.342 | 0.175 | 1.659 | 7.68 | 10726.87 | 25652.99 | 0.406 |
| C3_fixed_200_max3 | C | AGGRESSIVE_HISTORICAL_ENVELOPE | 53696.17 | 1.79 | 0.21 | 1.659 | 8.52 | 14302.5 | 34203.98 | 0.406 |
| C4_high_vol_norm_max3 | C | AGGRESSIVE_HISTORICAL_ENVELOPE | 26038.21 | 0.868 | 0.131 | 1.649 | 6.61 | 6341.37 | 17145.15 | 0.385 |
| C5_compound_fixed_100_max3 | C | AGGRESSIVE_HISTORICAL_ENVELOPE | 38444.25 | 1.281 | 0.161 | 1.537 | 7.95 | 7046.92 | 24212.89 | 0.383 |
| D1_fixed_050_max2_reduce50_after_dd5 | D | MODERATE_RESEARCH_CANDIDATE | 8694.73 | 0.29 | 0.057 | 1.578 | 5.06 | 1009.37 | 4769.11 | 0.115 |
| D2_fixed_100_max2_reduce50_after_dd5 | D | MODERATE_RESEARCH_CANDIDATE | 15813.91 | 0.527 | 0.088 | 1.565 | 5.99 | 2302.83 | 7728.98 | 0.143 |
| D3_fixed_050_max2_pause_after_dd8 | D | MODERATE_RESEARCH_CANDIDATE | 9377.5 | 0.313 | 0.059 | 1.613 | 5.32 | 1163.04 | 5480.7 | 0.104 |
| D4_fixed_100_max2_pause_after_dd8 | D | OVERFIT_OR_UNACCEPTABLE_RISK | 2957.97 | 0.099 | 0.082 | 1.289 | 1.2 | -3414.7 | 0 | 0.508 |


Conservative scenarios show a usable historical range, but the range remains evidence-limited by P0/P1/P2 findings. Aggressive scenarios primarily show a historical upper envelope and are not eligible as small-live defaults.

## 8. Concentration And Top-N Fragility

Top-5 removal, 2023 contribution, SOL dependence, and largest shared episode contribution are included in `risk_control_return_frontier.json`. High-return scenarios amplify the same sparse trend payoff structure. Any scenario with negative top-5 removal or excessive 2023 dependence should be treated as fragile even if net PnL is high.

## 9. 2023 / Shared Episode Dependence

P0 showed winner episodes are partially shared. The largest shared episode metric in this report maps scenario PnL to P0 loose episode windows. High-return scenarios generally amplify those shared windows rather than creating independent observations. Result excluding 2023 and excluding the largest shared episode are therefore mandatory caution fields.

## 10. Small-Capital Projection

Projected historical U terms for selected scenarios:

| sleeve | scenario | net_U | maxDD_U | worst_month_U | largest_loss_U | tolerable |
| --- | --- | --- | --- | --- | --- | --- |
| 1500 | A1_low_vol_norm_max2 | 216.22 | 39.0 | -14.37 | -3.91 | True |
| 1500 | A5_fixed_050_max2 | 468.88 | 88.11 | -32.93 | -7.98 | True |
| 1500 | B2_fixed_100_max2 | 937.75 | 161.7 | -65.87 | -15.97 | False |
| 1500 | C3_fixed_200_max3 | 2684.81 | 315.25 | -185.01 | -31.94 | False |
| 3000 | A1_low_vol_norm_max2 | 432.45 | 78.01 | -28.74 | -7.81 | True |
| 3000 | A5_fixed_050_max2 | 937.75 | 176.22 | -65.87 | -15.97 | True |
| 3000 | B2_fixed_100_max2 | 1875.5 | 323.41 | -131.74 | -31.94 | False |
| 3000 | C3_fixed_200_max3 | 5369.62 | 630.5 | -370.02 | -63.88 | False |
| 4500 | A1_low_vol_norm_max2 | 648.67 | 117.01 | -43.11 | -11.72 | True |
| 4500 | A5_fixed_050_max2 | 1406.63 | 264.33 | -98.8 | -23.95 | True |
| 4500 | B2_fixed_100_max2 | 2813.25 | 485.11 | -197.61 | -47.91 | False |
| 4500 | C3_fixed_200_max3 | 8054.43 | 945.74 | -555.03 | -95.82 | False |


These are historical projections only. They are not expected returns and do not authorize allocation.

## 11. Overfit And SRR-002 Risk Review

P0 evidence strength was inconclusive, PF confidence was inconclusive, and winner episodes were partially shared. Risk-control tuning can overfit just like strategy parameter tuning. The best historical risk-control scenario may simply magnify a few favorable crypto-wide trend episodes. SRR-002 still requires separate review before any live interpretation.

## 12. Classification

Overall classification: `RETURN_FRONTIER_SHOWS_USABLE_CONSERVATIVE_RANGE`.

Historical max scenario classification: `HISTORICAL_MAX_ONLY_NOT_RECOMMENDED`.

Small-live relevance: `SUPPORTS_SMALL_LIVE_DESIGN_CONSERVATIVE`.

## 13. Recommendation

A. Continue with docs-only small-live design using conservative scenario

This recommendation does not authorize execution. It preserves the frontier as a decision aid for Owner review and future docs-only design work.

## 14. Explicit Prohibitions

This report does not authorize:

- Direction A changes;
- risk module implementation;
- parameter optimization;
- portfolio implementation;
- runtime;
- small-live;
- live execution;
- capital allocation;
- TE execution;
- CPM reopening;
- strategy rescue.

## 15. Owner Summary

The return frontier shows that Direction A has a usable conservative historical range and a much higher aggressive envelope. The aggressive envelope is not a live candidate; it mainly illustrates the maximum historical payoff available by taking more risk on the same sparse, shared trend episodes. Conservative scenarios are more relevant to the existing docs-only small-live design, but they still inherit P0/P1/P2 evidence limits.

Direction A risk-control return frontier is diagnostic only. It estimates historical return/risk envelopes under pre-declared risk-control scenarios, but does not authorize risk module implementation, runtime use, small-live use, capital allocation, Direction A changes, parameter optimization, portfolio work, TE execution, CPM reopening, or strategy rescue.
