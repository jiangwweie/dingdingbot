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

# Direction A-1H Compressed Variant Sandbox Diagnostic

**Status:** Completed / off-mainline sandbox diagnostic  
**Date:** 2026-05-08  
**Classification:** `1H_COMPRESSED_VARIANT_PARTIAL_BUT_WEAK`  
**Recommendation:** B. Preserve as sandbox evidence only; no next task  
**Affects Runtime Automatically:** No

---

## 1. Boundary

This is one isolated sandbox diagnostic for a compressed 1h variant inspired by Direction A. It is explicitly off-mainline. It does not modify Direction A classification, small-live design, SMA primary roadmap, runtime status, or the current Direction A 4h evidence chain.

It does not authorize Direction A mainline changes, 4h replacement, parameter tuning, additional variants, runtime, small-live, portfolio work, TE execution, CPM reopening, or strategy rescue.

## 2. Inputs Inspected

- `docs/ops/direction-a-p2-risk-shape-diagnostic.md`
- `docs/ops/direction-a-p1-edge-source-attribution.md`
- `docs/ops/direction-a-p0-evidence-strength-diagnostics.md`
- `docs/ops/direction-a-cross-asset-frozen-diagnostic-result.md`
- `docs/ops/direction-a-sparse-trend-evidence-hardening-and-winner-attribution.md`
- `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md`
- `data/v3_dev.db`


## 3. Why This Is Off-mainline

Mainline Direction A is a 4h smart-beta trend timing mechanism with positive sparse trend evidence and pause-fragile non-runtime status. The 1h compressed variant is not a rescue, replacement, timing overlay, or small-live path. It only tests whether the same frozen logic survives timeframe compression without optimization.

## 4. 1h Data Coverage

| asset | earliest | latest | expected | actual | missing | gaps_gt_6h | dups | ohlc_bad | zero_vol | class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETH | 2020-01-01 | 2026-03-31 | 43824 | 43824 | 0 | 0 | 0 | 0 | 1 | 1H_DATA_READY |
| BTC | 2021-01-01 | 2026-03-31 | 43824 | 43824 | 0 | 0 | 0 | 0 | 1 | 1H_DATA_READY |
| SOL | 2021-01-01 | 2026-03-31 | 43824 | 43704 | 120 | 2 | 0 | 0 | 1 | 1H_DATA_PARTIAL_BUT_USABLE |


## 5. Frozen 1h Rule Confirmation

- Timeframe: 1h.
- Entry: close > highest close of prior 20 closed 1h bars.
- Entry execution: next 1h open after signal close, plus 0.1% slippage.
- Initial stop: previous 20 closed 1h low, signal bar excluded, active intrabar.
- Exit: fully closed 1h candle close below EMA60.
- Exit execution: next 1h open, less 0.1% slippage.
- Donchian lookback: 20.
- EMA period: 60.
- Funding: 0.0001 per 8h.
- No asset-specific changes.

## 6. ETH 1h Result

| metric | value |
| --- | --- |
| classification | 1H_NOT_SUPPORTED |
| trades | 1039 |
| winners / losers | 210 / 829 |
| win rate | 0.2021 |
| net PnL | -4692.42 |
| PF | 0.811 |
| realized MaxDD | 0.5743 |
| MTM MaxDD | 0.5839 |
| payoff ratio | 3.202 |
| avg hold winners / losers | 58.0h / 8.5h |
| fees / slippage / funding | 2302.81 / 5757.02 / 503.24 |
| cost as % gross | 2.212 |
| 1h vs 4h trade multiple | 6.01 |
| median holding hours | 5.0 |
| same-day exits | 798 |
| under 6h / under 24h | 528 / 788 |
| net after top-5 removal | -7976.56 |
| 2023 contribution | -2428.84 |

Year-by-year:

| year | trades | winners | losers | net | pf | win_rate | top1 | interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2021 | 190 | 53 | 137 | 1307.53 | 1.277 | 0.279 | 889.31 | positive sparse/churn year |
| 2022 | 190 | 39 | 151 | -1672.04 | 0.687 | 0.205 | 511.62 | negative or cost-churn year |
| 2023 | 213 | 34 | 179 | -2428.84 | 0.625 | 0.16 | 869.48 | negative or cost-churn year |
| 2024 | 223 | 38 | 185 | -588.11 | 0.87 | 0.17 | 551.4 | negative or cost-churn year |
| 2025 | 223 | 46 | 177 | -1310.95 | 0.653 | 0.206 | 360.55 | negative or cost-churn year |


## 7. BTC 1h Result

| metric | value |
| --- | --- |
| classification | 1H_NOT_SUPPORTED |
| trades | 1044 |
| winners / losers | 188 / 856 |
| win rate | 0.1801 |
| net PnL | -4686.83 |
| PF | 0.807 |
| realized MaxDD | 0.5351 |
| MTM MaxDD | 0.5414 |
| payoff ratio | 3.675 |
| avg hold winners / losers | 62.1h / 8.6h |
| fees / slippage / funding | 2730.48 / 6826.21 / 601.8 |
| cost as % gross | 1.857 |
| 1h vs 4h trade multiple | 6.57 |
| median holding hours | 6.0 |
| same-day exits | 817 |
| under 6h / under 24h | 519 / 807 |
| net after top-5 removal | -9286.72 |
| 2023 contribution | 68.82 |

Year-by-year:

| year | trades | winners | losers | net | pf | win_rate | top1 | interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2021 | 198 | 45 | 153 | -528.88 | 0.892 | 0.227 | 533.62 | negative or cost-churn year |
| 2022 | 211 | 29 | 182 | -2739.94 | 0.472 | 0.137 | 408.02 | negative or cost-churn year |
| 2023 | 208 | 36 | 172 | 68.82 | 1.012 | 0.173 | 921.83 | positive sparse/churn year |
| 2024 | 217 | 42 | 175 | -107.79 | 0.974 | 0.194 | 673.65 | negative or cost-churn year |
| 2025 | 210 | 36 | 174 | -1379.04 | 0.686 | 0.171 | 1218.54 | negative or cost-churn year |


## 8. SOL 1h Result

| metric | value |
| --- | --- |
| classification | 1H_PARTIAL_EVIDENCE_BUT_NOISY |
| trades | 1039 |
| winners / losers | 247 / 792 |
| win rate | 0.2377 |
| net PnL | 1933.81 |
| PF | 1.06 |
| realized MaxDD | 0.2665 |
| MTM MaxDD | 0.2786 |
| payoff ratio | 3.399 |
| avg hold winners / losers | 52.0h / 7.4h |
| fees / slippage / funding | 2341.52 / 5853.8 / 504.82 |
| cost as % gross | 0.818 |
| 1h vs 4h trade multiple | 6.58 |
| median holding hours | 5.0 |
| same-day exits | 803 |
| under 6h / under 24h | 536 / 793 |
| net after top-5 removal | -3413.35 |
| 2023 contribution | 3148.94 |

Year-by-year:

| year | trades | winners | losers | net | pf | win_rate | top1 | interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2021 | 175 | 54 | 121 | 4473.32 | 1.974 | 0.309 | 1282.97 | positive sparse/churn year |
| 2022 | 222 | 39 | 183 | -3525.74 | 0.468 | 0.176 | 241.1 | negative or cost-churn year |
| 2023 | 199 | 46 | 153 | 3148.94 | 1.495 | 0.231 | 1162.74 | positive sparse/churn year |
| 2024 | 221 | 52 | 169 | -1442.7 | 0.804 | 0.235 | 708.28 | negative or cost-churn year |
| 2025 | 222 | 56 | 166 | -720.01 | 0.9 | 0.252 | 714.89 | negative or cost-churn year |


## 9. 1h vs 4h Comparison

| asset | 1h_trades | 4h_trades | 1h_net | 4h_net | 1h_pf | 4h_pf | 1h_win | 4h_win | 1h_payoff | 4h_payoff | 1h_cost_drag | 4h_cost_drag | 1h_med_hold | top5_after | class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETH | 1039 | 173 | -4692.42 | 3001.66 | 0.811 | 1.517 | 0.202 | 0.1965 | 3.202 | 6.2 | 2.212 | 0.268 | 5.0 | -7976.56 | 1H_NOT_SUPPORTED |
| BTC | 1044 | 159 | -4686.83 | 2517.17 | 0.807 | 1.477 | 0.18 | 0.2516 | 3.675 | 4.39 | 1.857 | 0.345 | 6.0 | -9286.72 | 1H_NOT_SUPPORTED |
| SOL | 1039 | 158 | 1933.81 | 4018.8 | 1.06 | 1.79 | 0.238 | 0.2785 | 3.399 | 4.64 | 0.818 | 0.16 | 5.0 | -3413.35 | 1H_PARTIAL_EVIDENCE_BUT_NOISY |


The 1h variant should not be rewarded for higher trade count. The key question is whether sparse trend payoff survives. In this sandbox, compression increases trade frequency and cost exposure materially. Any positive evidence must be discounted for churn and weaker top-N behavior relative to the 4h mechanism.

## 10. Frequency / Churn Analysis

The 1h variant increases trades per asset materially versus the 4h baseline and produces many same-day exits. Median holding time is much shorter than the 4h lifecycle. This is evidence that timeframe compression changes the behavior from patient lifecycle capture toward faster breakout churn.

## 11. Top Winner Attribution

| asset | rank | entry | exit | hold_h | net | mfe | mae | behavior |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETH | 1 | 2021-01-02 | 2021-01-08 | 134.0 | 889.31 | 1358.98 | -8.08 | real trend capture |
| ETH | 2 | 2023-01-06 | 2023-01-18 | 288.0 | 869.48 | 1191.57 | -19.26 | real trend capture |
| ETH | 3 | 2024-11-06 | 2024-11-12 | 161.0 | 551.4 | 725.14 | -11.08 | real trend capture |
| ETH | 4 | 2022-07-14 | 2022-07-20 | 149.0 | 511.62 | 682.66 | -10.39 | real trend capture |
| ETH | 5 | 2024-05-20 | 2024-05-24 | 85.0 | 462.35 | 648.6 | -7.78 | real trend capture |
| BTC | 1 | 2025-09-28 | 2025-10-07 | 210.0 | 1218.54 | 1508.15 | -11.33 | real trend capture |
| BTC | 2 | 2023-01-06 | 2023-01-18 | 284.0 | 921.83 | 1094.86 | -11.94 | real trend capture |
| BTC | 3 | 2023-10-19 | 2023-10-26 | 175.0 | 899.75 | 1302.92 | -4.56 | real trend capture |
| BTC | 4 | 2023-03-12 | 2023-03-21 | 206.0 | 886.13 | 1035.49 | -12.68 | real trend capture |
| BTC | 5 | 2024-02-07 | 2024-02-13 | 142.0 | 673.65 | 918.41 | -2.07 | real trend capture |
| SOL | 1 | 2021-08-13 | 2021-08-21 | 208.0 | 1282.97 | 1592.05 | -1.08 | real trend capture |
| SOL | 2 | 2023-12-20 | 2023-12-26 | 144.0 | 1162.74 | 1658.0 | -11.05 | real trend capture |
| SOL | 3 | 2021-10-20 | 2021-10-23 | 82.0 | 1087.12 | 1768.97 | -2.58 | real trend capture |
| SOL | 4 | 2023-10-19 | 2023-10-24 | 133.0 | 943.7 | 1381.04 | -23.83 | real trend capture |
| SOL | 5 | 2023-10-29 | 2023-11-02 | 105.0 | 870.62 | 1748.5 | -18.53 | real trend capture |


Top winners that hold multiple days are still recognizable trend captures. Shorter winners are less persuasive and are classified as noisy breakouts when MFE/MAE and hold duration do not support lifecycle behavior.

## 12. Worst Loser Attribution

| asset | rank | entry | exit | hold_h | net | mfe | mae | behavior |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ETH | 1 | 2021-10-26 | 2021-10-26 | 1.0 | -131.28 | 8.66 | -68.83 | false breakout |
| ETH | 2 | 2022-04-16 | 2022-04-16 | 0.0 | -130.86 | 53.1 | -131.8 | false breakout |
| ETH | 3 | 2021-12-25 | 2021-12-26 | 6.0 | -125.72 | 43.68 | -65.82 | false breakout |
| ETH | 4 | 2021-12-10 | 2021-12-10 | 0.0 | -125.35 | 10.3 | -126.34 | false breakout |
| ETH | 5 | 2022-04-10 | 2022-04-10 | 5.0 | -124.01 | 59.05 | -15.69 | trend death |
| BTC | 1 | 2021-04-15 | 2021-04-16 | 8.0 | -115.14 | 33.61 | -51.54 | false breakout |
| BTC | 2 | 2021-10-28 | 2021-10-28 | 9.0 | -108.47 | 53.62 | -6.69 | trend death |
| BTC | 3 | 2021-02-14 | 2021-02-15 | 20.0 | -108.43 | 31.59 | -48.48 | false breakout |
| BTC | 4 | 2021-11-01 | 2021-11-01 | 1.0 | -108.2 | 10.75 | -19.01 | false breakout |
| BTC | 5 | 2021-09-13 | 2021-09-13 | 0.0 | -104.16 | 5.35 | -140.08 | false breakout |
| SOL | 1 | 2024-02-26 | 2024-02-26 | 2.0 | -152.36 | 5.93 | -62.47 | false breakout |
| SOL | 2 | 2024-02-28 | 2024-02-28 | 8.0 | -145.59 | 168.38 | -25.76 | trend death |
| SOL | 3 | 2024-03-05 | 2024-03-05 | 4.0 | -141.51 | 81.85 | -129.48 | false breakout |
| SOL | 4 | 2023-12-02 | 2023-12-04 | 52.0 | -141.47 | 184.1 | -36.09 | trend death |
| SOL | 5 | 2024-12-27 | 2024-12-27 | 0.0 | -139.66 | 7.81 | -150.12 | false breakout |


Worst losers are interpreted as false breakouts, cost churn, or trend death depending on hold duration, MFE, and MAE.

## 13. Cost Drag Review

Cost drag is structurally more important at 1h because trade count rises and holding periods compress. Even when net PnL remains positive, the compressed variant is more vulnerable to fees, slippage, and funding assumptions than the 4h baseline.

## 14. Sandbox Classification

Overall classification: `1H_COMPRESSED_VARIANT_PARTIAL_BUT_WEAK`.

Per-asset classifications:

- ETH: `1H_NOT_SUPPORTED`
- BTC: `1H_NOT_SUPPORTED`
- SOL: `1H_PARTIAL_EVIDENCE_BUT_NOISY`


## 15. Recommendation

B. Preserve as sandbox evidence only; no next task

This recommendation is sandbox-only. It does not authorize continuation, optimization, or mainline adoption.

## 16. Explicit Prohibitions

This report does not authorize:

- Direction A mainline changes;
- 4h Direction A replacement;
- parameter tuning;
- 1h variants;
- more timeframe experiments;
- portfolio work;
- runtime;
- small-live;
- TE execution;
- CPM reopening;
- strategy rescue.

## 17. Owner Summary

The 1h compressed variant is an off-mainline diagnostic. It tests whether the 4h Direction A structure survives mechanical timeframe compression. The result is preserved only as sandbox evidence and must not affect the 4h evidence chain or small-live design path unless the Owner separately requests a review.

Direction A-1H compressed variant is an off-mainline sandbox diagnostic only. It does not authorize Direction A mainline changes, parameter tuning, additional variants, runtime use, small-live use, portfolio work, TE execution, CPM reopening, or strategy rescue. Any future work requires separate Owner approval and must satisfy SRR-002.
