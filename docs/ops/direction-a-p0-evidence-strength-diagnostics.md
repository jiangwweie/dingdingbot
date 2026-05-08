# Direction A P0 Evidence-Strength Diagnostics

**Status:** Completed / empirical diagnostics only  
**Date:** 2026-05-08  
**Classification:** `P0_EVIDENCE_STRENGTH_INCONCLUSIVE`  
**Recommendation:** E. Owner decision required  
**Affects Runtime Automatically:** No

---

## 1. Boundary

This report executes only the Owner-authorized Direction A P0 evidence-strength diagnostics:

1. Cross-asset winner timing overlap.
2. Bootstrap PF confidence interval.

It uses existing ETH/BTC/SOL Direction A trade artifacts only. It does not rerun ETH/BTC/SOL, add assets, change Direction A, tune parameters, create a portfolio, modify risk shape, or interpret results as runtime or small-live readiness.

## 2. Inputs Inspected

- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/trades.jsonl`
- `reports/direction-a-cross-asset-frozen-diagnostic/btc_trades.jsonl`
- `reports/direction-a-cross-asset-frozen-diagnostic/sol_trades.jsonl`
- `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md`
- `reports/direction-a-cross-asset-frozen-diagnostic/btc_result.json`
- `reports/direction-a-cross-asset-frozen-diagnostic/sol_result.json`
- `reports/direction-a-cross-asset-frozen-diagnostic/btc_trades.csv`
- `reports/direction-a-cross-asset-frozen-diagnostic/sol_trades.csv`
- `reports/direction-a-cross-asset-frozen-diagnostic/btc_trades.jsonl`
- `reports/direction-a-cross-asset-frozen-diagnostic/sol_trades.jsonl`
- `reports/direction-a-cross-asset-frozen-diagnostic/cross_asset_summary.json`
- `reports/direction-a-cross-asset-frozen-diagnostic/cross_asset_summary.md`
- `docs/ops/direction-a-sparse-trend-evidence-hardening-and-winner-attribution.md`
- `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md`
- `docs/ops/sma-001-strategy-module-applicability-map.md`


ETH trade artifact was not present in the cross-asset diagnostic folder, so the existing NSC-014 Direction A ETH trade artifact was used. No ETH backtest was regenerated.

## 3. Current Direction A Cross-Asset State

`POSITIVE_CROSS_ASSET_SPARSE_TREND_EVIDENCE / PAUSE_FRAGILE / NON_RUNTIME`

- ETH: 173 trades, 34 winners, net +3,001.66, PF 1.517, payoff ratio 6.20:1.
- BTC: 159 trades, 40 winners, net +2,517.17, PF 1.477, payoff ratio 4.39:1.
- SOL: 158 trades, 44 winners, net +4,018.80, PF 1.790, payoff ratio 4.64:1.
- Overall verdict before P0: `CROSS_ASSET_SUPPORTS_MECHANISM`.
- Known blockers remain: no pre-observable applicability boundary, universal top-5 removal failure, BTC/SOL 2023 concentration, and no runtime/small-live readiness.

## 4. Winner Universe

Top-10 winners by asset are recorded in `reports/direction-a-p0-evidence-strength-diagnostics/winner_overlap_matrix.json` and summarized below.

| asset | rank | entry | exit | hold_h | net | mfe | mae | year | exit_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETH | 1 | 2024-02-06 | 2024-03-14 | 884.0 | 1373.64 | 1646.45 | -24.69 | 2024 | ema60_close_break_next_open |
| ETH | 2 | 2025-07-08 | 2025-08-01 | 556.0 | 1036.73 | 1301.74 | -20.27 | 2025 | ema60_close_break_next_open |
| ETH | 3 | 2023-01-02 | 2023-01-25 | 544.0 | 1035.21 | 1468.55 | -30.58 | 2023 | ema60_close_break_next_open |
| ETH | 4 | 2021-01-02 | 2021-01-11 | 208.0 | 533.65 | 1048.74 | -26.67 | 2021 | ema60_close_break_next_open |
| ETH | 5 | 2023-10-20 | 2023-11-14 | 608.0 | 515.77 | 776.87 | -31.35 | 2023 | ema60_close_break_next_open |
| ETH | 6 | 2022-03-15 | 2022-04-06 | 512.0 | 408.9 | 573.84 | -35.28 | 2022 | ema60_close_break_next_open |
| ETH | 7 | 2025-05-08 | 2025-05-18 | 256.0 | 403.36 | 684.12 | -7.47 | 2025 | ema60_close_break_next_open |
| ETH | 8 | 2022-10-22 | 2022-11-03 | 272.0 | 294.1 | 531.81 | -26.42 | 2022 | ema60_close_break_next_open |
| ETH | 9 | 2021-07-23 | 2021-08-18 | 620.0 | 287.27 | 395.55 | -19.87 | 2021 | ema60_close_break_next_open |
| ETH | 10 | 2021-04-26 | 2021-05-13 | 416.0 | 286.61 | 478.97 | -22.57 | 2021 | ema60_close_break_next_open |
| BTC | 1 | 2023-10-16 | 2023-11-14 | 716.0 | 1303.82 | 1889.96 | -7.39 | 2023 | ema60_close_break_next_open |
| BTC | 2 | 2023-01-09 | 2023-02-05 | 664.0 | 1138.3 | 1411.64 | -5.21 | 2023 | ema60_close_break_next_open |
| BTC | 3 | 2024-02-26 | 2024-03-15 | 420.0 | 762.97 | 1072.27 | -4.85 | 2024 | ema60_close_break_next_open |
| BTC | 4 | 2024-02-07 | 2024-02-24 | 388.0 | 549.44 | 763.34 | -0.01 | 2024 | ema60_close_break_next_open |
| BTC | 5 | 2021-02-02 | 2021-02-23 | 488.0 | 428.06 | 613.41 | -10.71 | 2021 | ema60_close_break_next_open |
| BTC | 6 | 2021-10-01 | 2021-10-22 | 512.0 | 382.75 | 551.05 | -1.82 | 2021 | ema60_close_break_next_open |
| BTC | 7 | 2025-05-07 | 2025-05-28 | 520.0 | 331.45 | 537.35 | -38.29 | 2025 | ema60_close_break_next_open |
| BTC | 8 | 2023-11-28 | 2023-12-11 | 300.0 | 302.83 | 536.16 | -53.16 | 2023 | ema60_close_break_next_open |
| BTC | 9 | 2024-11-06 | 2024-11-26 | 476.0 | 302.12 | 423.97 | -27.58 | 2024 | ema60_close_break_next_open |
| BTC | 10 | 2025-09-29 | 2025-10-10 | 280.0 | 214.94 | 494.07 | -21.7 | 2025 | ema60_close_break_next_open |
| SOL | 1 | 2023-10-16 | 2023-11-21 | 856.0 | 2273.99 | 3097.43 | -12.85 | 2023 | ema60_close_break_next_open |
| SOL | 2 | 2021-07-29 | 2021-08-25 | 640.0 | 832.68 | 1174.3 | -33.8 | 2021 | ema60_close_break_next_open |
| SOL | 3 | 2021-08-27 | 2021-09-13 | 408.0 | 531.91 | 983.56 | -16.88 | 2021 | ema60_close_break_next_open |
| SOL | 4 | 2023-01-02 | 2023-01-25 | 544.0 | 398.46 | 537.67 | -8.68 | 2023 | ema60_close_break_next_open |
| SOL | 5 | 2021-01-24 | 2021-02-16 | 560.0 | 351.54 | 498.38 | -24.46 | 2021 | ema60_close_break_next_open |
| SOL | 6 | 2022-03-17 | 2022-04-06 | 496.0 | 327.33 | 603.06 | -38.11 | 2022 | ema60_close_break_next_open |
| SOL | 7 | 2023-06-29 | 2023-07-21 | 524.0 | 306.36 | 685.22 | -46.49 | 2023 | ema60_close_break_next_open |
| SOL | 8 | 2023-12-20 | 2023-12-28 | 196.0 | 300.25 | 672.42 | -9.88 | 2023 | ema60_close_break_next_open |
| SOL | 9 | 2024-07-15 | 2024-07-31 | 404.0 | 280.72 | 468.13 | -6.65 | 2024 | ema60_close_break_next_open |
| SOL | 10 | 2021-03-27 | 2021-04-14 | 440.0 | 266.12 | 385.67 | -18.2 | 2021 | ema60_close_break_next_open |


## 5. Cross-Asset Winner Timing Overlap

Overlap windows were pre-specified:

- Strict overlap: holding windows overlap in calendar time.
- Loose overlap: entry timestamps are within +/-14 days or holding windows overlap within +/-14 days.

| pair | strict | loose | months | combined_pair_pnl_sum |
| --- | --- | --- | --- | --- |
| ETH_top5_vs_BTC_top5 | 4 | 4 | 2023-01, 2023-10, 2024-02 | 8052.788668 |
| ETH_top5_vs_SOL_top5 | 2 | 3 | 2021-01, 2023-01, 2023-10 | 5108.618974 |
| BTC_top5_vs_SOL_top5 | 3 | 3 | 2021-01, 2021-02, 2023-01, 2023-10 | 5894.175541 |


Top-10 all-pair overlap count: strict 12, loose 18.

Winner overlap classification: `WINNER_EVIDENCE_PARTIALLY_SHARED`.

Interpretation: Direction A's cross-asset winners are not three fully independent evidence streams. Several of the largest ETH/BTC/SOL winners cluster into shared crypto-wide trend windows, especially 2021-Q1, 2023-Q1, 2023-Q4, and 2024-Q1. The result is not one single episode, but the effective evidence count is materially lower than the raw winner count.

## 6. Effective Independent Episode Count

- Raw top-5 winner count: 15.
- Strict unique top-5 episode count: 8.
- Loose unique top-5 episode count: 6.
- Asset-adjusted strict effective observations: 5.667.
- Asset-adjusted loose effective observations: 3.500.
- Raw top-10 winner count: 30.
- Strict unique top-10 episode count: 20.
- Loose unique top-10 episode count: 15.

The loose top-5 result is the key conservative read: effective independent evidence is closer to 3.5 asset-adjusted observations than 15 raw top-5 trades.

## 7. Bootstrap Method

Trade-level bootstrap:

- 10,000 bootstrap samples per asset and pooled all-assets view.
- Resampled closed trade net PnL with replacement.
- Reported PF, net PnL, win rate, payoff ratio, probability PF > 1, probability net PnL > 0, and probabilities that top-3 / top-5 removal remains positive.

Conservative alternative:

- Year-level bootstrap was also computed using annual blocks for each asset and pooled all-assets view.
- It is coarse because only five years are available, but it better reflects sparse-trend year/regime concentration than independent trade resampling.

Max drawdown bootstrap was not computed because trade-level resampling destroys chronological order and would create an order-dependent statistic that is not interpretable here.

## 8. Bootstrap PF Confidence Intervals

Trade-level bootstrap classification: `PF_CONFIDENCE_INCONCLUSIVE`.

| asset | obs_pf | pf_p5 | pf_p25 | pf_p50 | pf_p75 | pf_p95 | p_pf_gt_1 | p_net_gt_0 | p_top3_pos | p_top5_pos |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETH | 1.517 | 0.878 | 1.21 | 1.487 | 1.811 | 2.336 | 0.893 | 0.893 | 0.441 | 0.201 |
| BTC | 1.477 | 0.831 | 1.172 | 1.456 | 1.775 | 2.314 | 0.872 | 0.872 | 0.37 | 0.144 |
| SOL | 1.79 | 1.001 | 1.408 | 1.753 | 2.165 | 2.876 | 0.95 | 0.95 | 0.626 | 0.405 |
| POOLED_ALL_ASSETS_WITH_CAVEATS | 1.59 | 1.17 | 1.405 | 1.58 | 1.773 | 2.095 | 0.993 | 0.993 | 0.912 | 0.774 |


Year-level conservative bootstrap:

| asset | pf_p5 | pf_p50 | pf_p95 | p_pf_gt_1 | p_net_gt_0 |
| --- | --- | --- | --- | --- | --- |
| ETH | 1.107 | 1.517 | 2.045 | 0.989 | 0.989 |
| BTC | 0.749 | 1.477 | 2.348 | 0.831 | 0.831 |
| SOL | 0.866 | 1.79 | 2.966 | 0.925 | 0.925 |
| POOLED_ALL_ASSETS_WITH_CAVEATS | 0.96 | 1.59 | 2.317 | 0.941 | 0.941 |


## 9. Sparse Trend Caveats

Trade-level bootstrap may overstate confidence because sparse trend systems are not built from fully independent trades. Winners cluster by crypto-wide trend regimes, as shown by the overlap diagnostic. Year-level bootstrap is more conservative but has too few annual blocks for precise inference. The correct interpretation is therefore conservative: PF confidence is positive at trade level, but effective evidence is reduced by shared regime clustering.

## 10. Combined P0 Interpretation

Combined classification: `P0_EVIDENCE_STRENGTH_INCONCLUSIVE`.

Reasoning:

- Cross-asset mechanism evidence remains positive across ETH/BTC/SOL.
- Winner overlap is partially shared across crypto-wide regimes, reducing independent observation count.
- Trade-level PF bootstrap is generally supportive, but top-3/top-5 removal probabilities remain weak and year-level results expose regime dependence.
- The result supports preserving Direction A as research evidence and conditionally considering P1, but it does not solve pre-observable applicability, fragility, or deployment readiness.

## 11. Recommendation

E. Owner decision required

Rationale: P0 is not strong enough to promote, deploy, or jump to P2 risk-shape work. It is sufficient to ask the next attribution question only if the Owner wants to continue: whether the observed edge comes from breakout entry, EMA60 exit management, beta timing, or some combination. P2 should not be recommended directly from P0.

## 12. Explicit Prohibitions

This report does not authorize:

- Direction A changes;
- Direction A variants;
- parameter optimization;
- new backtests;
- more asset diagnostics;
- random entry controls;
- buy-and-hold decomposition;
- vol targeting;
- portfolio/router work;
- runtime;
- small-live;
- TE execution;
- CPM reopening;
- strategy rescue.

## 13. Owner Summary

Direction A P0 improves the evidence map but does not change deployment status. ETH/BTC/SOL support the same sparse trend lifecycle mechanism, but top winners partially synchronize around shared crypto-wide regimes. Bootstrap PF is supportive at trade level, yet the sparse-trend caveat is binding because effective independent observations are materially fewer than the raw trade count. The next empirical stage, if authorized separately, should be P1 edge-source attribution, not P2 vol targeting or portfolio work.

Direction A P0 evidence-strength diagnostics do not authorize Direction A changes, variants, additional backtests, parameter optimization, portfolio work, runtime use, small-live use, TE execution, CPM reopening, or strategy rescue. Any future empirical work requires separate Owner approval and must satisfy SRR-002.
