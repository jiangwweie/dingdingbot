# Direction A P2 Risk-Shape And Vol-Normalized Sizing Diagnostic

**Status:** Completed / empirical risk-shape diagnostics only  
**Date:** 2026-05-08  
**Classification:** `P2_RISK_SHAPE_IMPROVES_BUT_NON_RUNTIME`  
**Future Path Classification:** `ELIGIBLE_FOR_SMALL_LIVE_DESIGN_PLAN`  
**Recommendation:** B. Proceed to docs-only small-live design plan  
**Affects Runtime Automatically:** No

---

## 1. Boundary

This report executes only the Owner-authorized Direction A P2 risk-shape diagnostic. It uses existing ETH/BTC/SOL Direction A trades and timestamps. It does not generate new signals, change Donchian/EMA/stop/exit rules, add assets, optimize targets, implement a portfolio/router, modify runtime/backtester core, or interpret results as live or small-live readiness.

## 2. Inputs Inspected

- `docs/ops/direction-a-p1-edge-source-attribution.md`
- `reports/direction-a-p1-edge-source-attribution/p1_summary.json`
- `docs/ops/direction-a-p0-evidence-strength-diagnostics.md`
- `reports/direction-a-p0-evidence-strength-diagnostics/p0_summary.json`
- `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md`
- `reports/direction-a-cross-asset-frozen-diagnostic/btc_trades.csv`
- `reports/direction-a-cross-asset-frozen-diagnostic/sol_trades.csv`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/trades.jsonl`
- `reports/direction-a-cross-asset-frozen-diagnostic/btc_result.json`
- `reports/direction-a-cross-asset-frozen-diagnostic/sol_result.json`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/summary.json`
- `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md`


ETH trade artifact format differed from BTC/SOL CSV, so ETH was normalized read-only from the existing NSC-014 JSONL trade artifact. ETH was not rerun.

## 3. Current Direction A State After P0/P1

`CROSS_ASSET_SMART_BETA_TREND_TIMING / POSITIVE_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME`

Completed diagnostics:

- Cross-asset frozen diagnostic: ETH/BTC/SOL all positive under identical frozen Direction A rule.
- P0: `P0_EVIDENCE_STRENGTH_INCONCLUSIVE`; winner overlap partially shared; PF confidence inconclusive.
- P1: `P1_MIXED_EDGE_SOURCE`; random entry shows partial entry alpha; buy-and-hold decomposition shows smart beta timing across ETH/BTC/SOL.

## 4. Scenario Methodology

All scenarios use the same existing Direction A trades. Only sizing or signal acceptance changes.

- S0: existing reported PnL baseline, aggregated across three standalone 10k-equivalent asset runs.
- S1: equal capital per asset basket; ETH/BTC/SOL each represent a 10k allocation inside a 30k research capital context; all signals accepted.
- S2: fixed risk per trade at 0.25%, 0.50%, and 1.00% of total 30k research capital, using existing initial stop distance to derive trade R.
- S3: volatility-normalized sizing with predeclared 20-day realized volatility estimator. Low target uses 50% annualized target capped at 0.25% risk/trade; moderate target uses 80% annualized target capped at 0.50% risk/trade. No target was selected by performance.
- S4: exposure cap overlay on existing trades only. Max 1, 2, or 3 concurrent positions. Deterministic policy: earliest signal keeps priority; later signals are skipped while cap is full.
- S5: asset exposure cap diagnostic using S2 0.50% as base and capping any asset's cumulative risk contribution at 40% by proportional scaling.

Portfolio curves are realized-at-exit research curves. Portfolio MTM was not reconstructed from OHLCV because the required artifact surface is trade-level and this task prohibits changing backtester/runtime core.

## 5. Baseline And Naive Basket Results

| scenario | net | ret | dd | trades | win_rate | pf | top5_after | avg_sim | max_sim | 2023 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0_existing_baseline_sum | 9537.63 | 0.318 | 0.055 | 490 | 0.241 | 1.59 | 2411.15 | 1.152 | 3 | 6159.67 |
| S1_equal_capital_per_asset | 9537.63 | 0.318 | 0.055 | 490 | 0.241 | 1.59 | 2411.15 | 1.152 | 3 | 6159.67 |


Naive combination improves breadth versus a single asset but does not remove shared-regime dependence. The basket remains carried by the same crypto-wide trend windows, especially 2023, and simultaneous exposure reaches three concurrent positions.

## 6. Fixed-Risk Sizing Results

| scenario | net | ret | dd | trades | win_rate | pf | top5_after | avg_sim | max_sim | 2023 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S2_fixed_risk_0.25pct_total_capital | 6712.02 | 0.224 | 0.04 | 490 | 0.241 | 1.659 | 1787.81 | 1.152 | 3 | 4275.5 |
| S2_fixed_risk_0.50pct_total_capital | 13424.04 | 0.447 | 0.074 | 490 | 0.241 | 1.659 | 3575.62 | 1.152 | 3 | 8551.0 |
| S2_fixed_risk_1.00pct_total_capital | 26848.08 | 0.895 | 0.131 | 490 | 0.241 | 1.659 | 7151.25 | 1.152 | 3 | 17101.99 |


Fixed-risk sizing makes per-trade loss more explicit and scalable. It preserves trend payoff because trade R is positive across the full sample, but 1% of total capital per trade is aggressive for a small 3wU context: it magnifies shared-episode exposure and drawdown without solving top-winner dependence.

## 7. Vol-Normalized Sizing Results

| scenario | net | ret | dd | trades | win_rate | pf | top5_after | avg_sim | max_sim | 2023 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S3_vol_normalized_low_target_50ann_max0.25pct | 5802.36 | 0.193 | 0.031 | 490 | 0.241 | 1.78 | 1229.32 | 1.152 | 3 | 3860.22 |
| S3_vol_normalized_moderate_target_80ann_max0.50pct | 12197.15 | 0.407 | 0.074 | 490 | 0.241 | 1.65 | 2348.73 | 1.152 | 3 | 8416.9 |


Volatility normalization reduces some SOL and high-volatility dominance by scaling risk down when 20-day annualized realized volatility is high. It improves tolerability directionally, but it also compresses large trend winners. The sparse payoff survives, but top-N dependence remains visible.

## 8. Exposure Cap Results

| scenario | net | ret | dd | trades | win_rate | pf | top5_after | avg_sim | max_sim | 2023 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S4_exposure_cap_max1_earliest_priority | 3794.54 | 0.126 | 0.025 | 213 | 0.225 | 1.587 | -1086.78 | 0.469 | 1 | 2125.27 |
| S4_exposure_cap_max2_earliest_priority | 6496.39 | 0.217 | 0.042 | 373 | 0.236 | 1.539 | 608.69 | 0.854 | 2 | 3758.61 |
| S4_exposure_cap_max3_earliest_priority | 9537.63 | 0.318 | 0.055 | 490 | 0.241 | 1.59 | 2411.15 | 1.152 | 3 | 6159.67 |
| S5_asset_risk_contribution_cap_40pct_on_S2_0.50 | 13424.04 | 0.447 | 0.074 | 490 | 0.241 | 1.659 | 3575.62 | 1.152 | 3 | 8551.0 |


ETH/BTC/SOL signals are often simultaneous during crypto-wide trend windows. Max 1 concurrent position reduces exposure but skips too many winners. Max 2 concurrent positions is more balanced than max 1, but it still skips some important winners and does not eliminate shared-regime concentration. Max 3 is effectively the all-signals basket.

## 9. Concentration And Top-N Fragility Review

| scenario | risk_share | abs_pnl_share | SOL_dom |
| --- | --- | --- | --- |
| S1_equal_capital_per_asset | {"BTC": 0.308, "ETH": 0.346, "SOL": 0.346} | {"BTC": 0.312, "ETH": 0.349, "SOL": 0.339} | False |
| S2_fixed_risk_0.50pct_total_capital | {"BTC": 0.324, "ETH": 0.353, "SOL": 0.322} | {"BTC": 0.326, "ETH": 0.353, "SOL": 0.321} | False |
| S3_vol_normalized_low_target_50ann_max0.25pct | {"BTC": 0.39, "ETH": 0.362, "SOL": 0.248} | {"BTC": 0.387, "ETH": 0.372, "SOL": 0.241} | False |
| S4_exposure_cap_max2_earliest_priority | {"BTC": 0.381, "ETH": 0.367, "SOL": 0.252} | {"BTC": 0.395, "ETH": 0.399, "SOL": 0.206} | False |


Across scenarios, top-winner and 2023 concentration remain central. Combining assets reduces single-asset dependence but introduces cross-asset episode dependence. Naive multi-asset does not transform 15 raw top-5 winners into 15 independent observations; P0's shared-episode caveat remains binding.

Worst simultaneous drawdown events are recorded in `risk_contribution_summary.json`. The primary practical risk is correlated loss/exposure clustering, not market depth.

## 10. Small-Capital Interpretation

Owner context is small capital around 3wU and mid/low frequency. Market depth/capacity is not the primary blocker, but risk shape still matters.

Practical interpretation:

- Plausible per-trade risk bands are closer to 0.25%-0.50% of total capital than 1.00% while evidence remains pause-fragile.
- No-leverage or low-leverage is realistic; leverage is not needed to test the mechanism and would amplify correlated drawdowns.
- Funding and slippage remain material because winners hold for many days and losers churn frequently.
- Position sizing granularity is likely viable at 3wU for ETH/BTC/SOL, but risk controls must account for exchange minimums and fee drag before any future design work.
- Psychological drawdown tolerance remains a blocker: sparse trend systems can spend long periods losing while waiting for shared crypto-wide payoff episodes.
- A future small-live design plan would need explicit risk bands, exposure caps, kill criteria, funding/slippage assumptions, and operator stop rules. This report does not recommend or authorize small-live.

## 11. P2 Classification

P2 classification: `P2_RISK_SHAPE_IMPROVES_BUT_NON_RUNTIME`.

Future path classification: `ELIGIBLE_FOR_SMALL_LIVE_DESIGN_PLAN`.

Reasoning:

- Risk shaping helps directionally, especially with low fixed-risk / vol-normalized sizing and exposure caps.
- Improvements are partial: top-winner dependence and shared crypto-wide episode concentration remain.
- Multi-asset Direction A improves breadth but does not eliminate correlated exposure risk.
- The result remains non-runtime and does not satisfy small-live readiness.

## 12. Recommendation

B. Proceed to docs-only small-live design plan

Rationale: improvements are not strong enough to claim live readiness or directly recommend implementation. If the Owner wants to continue, the next step should be a separate decision, not automatic runtime work.

## 13. Explicit Prohibitions

This report does not authorize:

- Direction A changes;
- Direction A variants;
- parameter optimization;
- portfolio implementation;
- runtime;
- small-live;
- TE execution;
- CPM reopening;
- strategy rescue.

## 14. Owner Summary

P2 shows that conservative risk shaping can make Direction A more tolerable, but only partially. Fixed-risk and volatility-normalized sizing provide better risk framing for a small-capital, mid/low-frequency context, and exposure caps reduce simultaneous crypto-wide exposure. However, the same sparse trend and shared-episode concentration remains. Direction A should remain research evidence unless the Owner separately authorizes a docs-only design step.

Direction A P2 risk-shape diagnostic does not authorize Direction A changes, variants, parameter optimization, portfolio implementation, runtime use, small-live use, TE execution, CPM reopening, or strategy rescue. Any future empirical work or small-live design requires separate Owner approval and must satisfy SRR-002.
