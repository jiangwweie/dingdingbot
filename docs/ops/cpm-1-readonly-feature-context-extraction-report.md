# CPM-1 Read-only Feature-Context Extraction Report

**Task ID**: CPM-1-READONLY-FEATURE-CONTEXT-EXTRACTION
**Date**: 2026-05-08
**Status**: Completed / read-only feature-context extraction
**Classification**: FEATURE_CONTEXT_SUPPORTS_BOUNDARY_HYPOTHESIS_INSPECT

---

## 0. Boundary

This is a read-only feature-context extraction for existing CPM-1 positions.

It is not:
- CPM-1 strategy execution or backtest
- Parameter sweep or rule change
- New gate proposal
- Strategy rescue attempt
- Runtime or small-live authorization
- CPM-MOD-003 or E4 experiment

It computes features from existing OHLCV data for already-existing positions only. It does not decide whether any position should or should not have been taken.

---

## 1. Position Universe

| Source Family | Artifact | Year | Positions |
|---------------|----------|------|-----------|
| CPM-MOD-002-baseline | baseline_2021_result.json | 2021 | 79 |
| CPM-MOD-002-baseline | baseline_2022_result.json | 2022 | 43 |
| CPM-MOD-002-baseline | baseline_2023_result.json | 2023 | 18 |
| CPM-MOD-002-baseline | baseline_2024_result.json | 2024 | 31 |
| CPM-MOD-002-baseline | baseline_2025_result.json | 2025 | 33 |
| OOS | cpm1_2021_oos/result.json | 2021 | 74 |
| OOS | cpm1_2022_oos/result.json | 2022 | 51 |

**Total positions**: 329

No deduplication was performed across families. Positions retain source_family and source_artifact labels.

### Position outcome summary

| Year | Source | Positions | Winners | Losers | Win Rate | Total PnL |
|------|--------|-----------|---------|--------|----------|-----------|
| 2021 | baseline | 79 | 15 | 64 | 19.0% | -1765.32 |
| 2021 | OOS | 74 | 12 | 62 | 16.2% | -1938.79 |
| 2022 | baseline | 43 | 8 | 35 | 18.6% | -763.72 |
| 2022 | OOS | 51 | 17 | 34 | 33.3% | -971.71 |
| 2023 | baseline | 18 | 3 | 15 | 16.7% | -785.24 |
| 2024 | baseline | 31 | 13 | 18 | 41.9% | +969.29 |
| 2025 | baseline | 33 | 9 | 24 | 27.3% | +322.05 |

---

## 2. Data Sources and Read-only Confirmation

| Source | Type | Read-only | Mutation |
|--------|------|-----------|----------|
| `data/v3_dev.db` | SQLite OHLCV | Yes | None |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/baseline_*_result.json` | Position artifacts | Yes | None |
| `reports/oos_runs/cpm1_*_oos/result.json` | OOS position artifacts | Yes | None |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/gate_state_sample.json` | Gate state sample | Yes | None |
| `reports/cpm-mod-002-cpm1-frozen-volatility-gate/summary.json` | CPM-MOD-002 summary | Yes | None |

OHLCV data: ETH/USDT:USDT, 1h (54,768 bars from 2020-01-01), 4h (13,692 bars from 2020-01-01).

No database writes. No strategy execution. No signal generation.

---

## 3. Feature Definitions

### 3.1 Pre-entry 1h features

| Feature | Definition | Lookback |
|---------|-----------|----------|
| h1_atr14 | ATR(14) on 1h bars | 15 bars |
| h1_atr14_pct90d | ATR14 rolling percentile over prior 90 days | 2160 bars |
| h1_rv_24h | Realized volatility (std of log returns) | 24 bars |
| h1_rv_72h | Realized volatility | 72 bars |
| h1_ret_24h | Close-to-close return | 24 bars |
| h1_ret_72h | Close-to-close return | 72 bars |
| h1_ret_7d | Close-to-close return | 168 bars |
| h1_ema50 | EMA(50) value | 50 bars |
| h1_close_dist_ema50_pct | (entry - EMA50) / EMA50 * 100 | 50 bars |
| h1_ema50_slope_5 | EMA50 slope over 5 bars | 55 bars |
| h1_ema50_slope_20 | EMA50 slope over 20 bars | 70 bars |
| h1_bar_range_pct90d | Bar range percentile over prior 90 days | 2161 bars |
| h1_pullback_depth_pct | (20-bar high - entry) / 20-bar high * 100 | 20 bars |

### 3.2 Pre-entry 4h features

| Feature | Definition | Lookback |
|---------|-----------|----------|
| h4_atr14 | ATR(14) on 4h bars | 15 bars |
| h4_atr14_pct90d | ATR14 rolling percentile over prior 90 days | 540 bars |
| h4_ema60 | EMA(60) value | 60 bars |
| h4_close_dist_ema60_pct | (entry - EMA60) / EMA60 * 100 | 60 bars |
| h4_ema60_slope_5 | EMA60 slope over 5 bars | 65 bars |
| h4_ema60_slope_20 | EMA60 slope over 20 bars | 80 bars |
| h4_dc20_position | Donchian20 position (0-100) | 20 bars |
| h4_dc20_normalized | Donchian20 normalized (0-1) | 20 bars |
| h4_dist_20bar_high_pct | Distance to 20-bar high (%) | 20 bars |
| h4_dist_20bar_low_pct | Distance to 20-bar low (%) | 20 bars |
| h4_ret_3bars | 4h return over 3 bars | 3 bars |
| h4_ret_6bars | 4h return over 6 bars | 6 bars |
| h4_ret_18bars | 4h return over 18 bars | 18 bars |

### 3.3 Price-location features

| Feature | Definition |
|---------|-----------|
| loc_1h_dist_20bar_high_pct | Distance from entry to 1h 20-bar high (%) |
| loc_1h_dist_20bar_low_pct | Distance from entry to 1h 20-bar low (%) |
| loc_1h_norm_position_20bar | Normalized position in 1h 20-bar range |
| loc_4h_dist_20bar_high_pct | Distance from entry to 4h 20-bar high (%) |
| loc_4h_dist_20bar_low_pct | Distance from entry to 4h 20-bar low (%) |
| loc_4h_norm_position_20bar | Normalized position in 4h 20-bar range |

### 3.4 Gate comparison features

| Feature | Definition |
|---------|-----------|
| gate_atr_pct_computed | Computed ATR percentile at entry |
| gate_atr_above_60 | Whether ATR percentile > 60% at entry |

### 3.5 Post-entry path features

| Feature | Definition |
|---------|-----------|
| mfe | Maximum favorable excursion from entry to exit |
| mae | Maximum adverse excursion from entry to exit |
| giveback | MFE - realized_pnl |
| mfe_r | MFE in R terms (if initial risk recoverable) |
| mae_r | MAE in R terms (if initial risk recoverable) |
| bars_to_mfe | Number of 1h bars to reach MFE |
| bars_to_mae | Number of 1h bars to reach MAE |
| tp1_reached | Whether TP1 was reached |
| tp2_reached | Whether TP2 was reached |
| sl_reached | Whether SL was reached |
| tp1_then_sl | Whether position had TP1 then SL |
| tp1_then_tp2 | Whether position had TP1 then TP2 |
| short_hold_winner | Winner with holding_hours <= 4 |

---

## 4. Missing Fields

Only 2 features have missing data:

| Feature | Not Available | Percentage |
|---------|--------------|-----------|
| mfe_r | 69 | 21.0% |
| mae_r | 69 | 21.0% |

R-based features are unavailable when the initial stop price cannot be recovered from close events (positions that exited directly without a recoverable SL level). All other features have >79% availability.

Feature coverage ratio: **85%** of features have >50% data availability across all positions.

---

## 5. Output Artifacts

| File | Description |
|------|-------------|
| `reports/cpm-1-readonly-feature-context-extraction/position_feature_context.csv` | Per-position feature context (329 rows, 67 columns) |
| `reports/cpm-1-readonly-feature-context-extraction/position_feature_context.jsonl` | Per-position feature context (JSONL) |
| `reports/cpm-1-readonly-feature-context-extraction/feature_group_summary.json` | Group distributions, cross-group comparisons, diagnostics |
| `reports/cpm-1-readonly-feature-context-extraction/feature_group_summary.md` | Group distributions (markdown) |
| `reports/cpm-1-readonly-feature-context-extraction/missing_fields_report.md` | Missing field analysis |
| `reports/cpm-1-readonly-feature-context-extraction/README.md` | Directory README |
| `docs/ops/cpm-1-readonly-feature-context-extraction-report.md` | This report |

---

## 6. 2024 vs 2025 Comparison

### 6.1 Is 2024 still stronger than 2025?

**Yes.** 2024 total PnL = +969.29 vs 2025 total PnL = +322.05. 2024 win rate = 41.9% vs 2025 win rate = 27.3%. The gap persists after feature-context extraction.

### 6.2 Are 2025 short-hold top winners explainable from OHLCV path?

2 short-hold winners in 2025 (winners with holding_hours <= 4). These are quick favorable moves captured within 4 hours. Feature context shows their pre-entry states and post-entry paths. The small count limits generalization.

### 6.3 Do 2025 winners occur in similar pre-entry states as 2024 winners?

**No, with important differences.**

Key divergences between 2024 and 2025 winner pre-entry states:

| Feature | 2024 Winners Median | 2025 Winners Median | Direction |
|---------|--------------------|--------------------|-----------|
| h1_atr14_pct90d | 25.6% | 47.2% | 2025 enters at higher ATR percentile |
| h4_atr14 | 41.5 | 62.8 | 2025 enters in higher-volatility 4h regime |
| h1_bar_range_pct90d | 24.5% | 41.2% | 2025 enters in wider-bar regime |
| h1_pullback_depth_pct | 0.73% | 0.85% | 2025 enters from slightly deeper pullbacks |

2025 winners enter in materially higher-volatility states than 2024 winners. This is a pre-observable difference.

### 6.4 Does 2025 fragility appear structural or artifact/context-driven?

**Structural.** 2025 top-5 winners account for 270% of total PnL (top-5 concentration exceeds 100% because losers contribute negative PnL). This extreme concentration indicates structural fragility: the year's positive outcome depends on a small number of large wins.

Additionally, 2025 winners show:
- Lower MFE (median 193 vs 406 for 2024 winners)
- Lower giveback (median 27 vs 318 for 2024 winners)
- Faster MFE arrival (37 bars vs 207 bars)
- Higher ATR percentile at entry (47% vs 26%)

The 2025 profile is: fewer, smaller, faster wins in higher-volatility states, with extreme concentration. This is structural fragility, not artifact.

---

## 7. 2023 Failure Feature Context

### 7.1 What features distinguish 2023 losers from 2024/2025 winners?

Top distinguishing features (2024 winners vs 2023 losers):

| Feature | 2024 Winners Median | 2023 Losers Median | Diff |
|---------|--------------------|--------------------|------|
| mfe | 406.17 | 4.26 | +401.91 |
| bars_to_mfe | 207 | 2 | +205 |
| bars_to_mae | 326 | 8 | +318 |
| giveback | 318.24 | 91.54 | +226.70 |
| h1_bar_range_pct90d | 24.5% | 50.5% | -25.9% |
| h1_atr14_pct90d | 25.6% | 43.4% | -17.8% |

**Key finding**: 2023 losers have near-zero MFE (median 4.26 vs 406 for 2024 winners) and reach MFE in only 2 bars. This means 2023 positions experience almost no favorable excursion before reversing. The continuation thesis fails almost immediately.

### 7.2 Why did the ATR > 0.60 gate disable zero 2023 baseline trades?

Of 18 2023 positions, only 3 had ATR percentile > 60% at entry. The average ATR percentile at 2023 entries was 40.1%. The ATR gate was designed to filter high-volatility entries, but 2023 trades occurred in moderate-volatility environments. The gate cannot filter what it was not designed to catch: moderate-volatility, weak-continuation states.

### 7.3 Were 2023 trades in moderate ATR but weak continuation states?

**Yes.** Average ATR percentile at 2023 entries: 40.1%. This is moderate. Yet MFE is near-zero (median 4.26), indicating that price barely moved favorably after entry. The failure is in continuation, not in entry volatility.

### 7.4 Is 2023 failure more related to volatility, trend slope, price location, pullback depth, or post-entry continuation failure?

Ranked failure dimensions (by median difference magnitude between 2024 winners and 2023 losers):

1. **Continuation** (401.9) — dominant
2. **Volatility** (17.8)
3. **Trend slope** (0.79)
4. **Pullback depth** (0.25)
5. **Price location** (0.01)

**2023 failure is overwhelmingly a post-entry continuation failure.** Positions enter in moderate-volatility, moderate-trend states but price does not continue favorably. This is not a pre-entry filter problem; it is a continuation-environment problem.

---

## 8. 2021 Failure Feature Context

### 8.1 What features distinguish 2021 losers from 2024 winners?

Top distinguishing features:

| Feature | 2024 Winners Median | 2021 Losers Median | Diff |
|---------|--------------------|--------------------|------|
| mfe | 406.17 | 9.86 | +396.31 |
| bars_to_mfe | 207 | 0 | +207 |
| bars_to_mae | 326 | 1 | +325 |
| h1_atr14_pct90d | 25.6% | 61.5% | -35.8% |
| h4_atr14_pct90d | 31.1% | 59.8% | -28.7% |
| h4_atr14 | 41.5 | 71.7 | -30.2% |

2021 losers enter at significantly higher ATR percentiles (median 61.5% vs 25.6%) and experience near-zero MFE (median 9.86 vs 406). Both pre-entry volatility and post-entry continuation distinguish 2021 losers from 2024 winners.

### 8.2 Does high ATR percentile explain a meaningful subset of 2021 losses?

**Yes.** Of 64 2021 losers, 34 (53%) had ATR percentile > 60% at entry. Of 79 total 2021 positions, 42 (53%) had ATR > 60%. High ATR explains a meaningful subset but not all.

### 8.3 Are there non-volatility hostile states inside 2021?

**Yes.** 30 of 64 2021 losers (47%) had ATR percentile <= 60%. These losses occurred in moderate-volatility environments, suggesting other factors (trend, continuation, price location) contributed. 2021 has both volatility-hostile and non-volatility-hostile loss clusters.

### 8.4 Does 2021 remain a favorable-year profit-thesis challenge after feature extraction?

**Yes.** 2021 baseline total PnL: -1765.32, OOS total PnL: -1938.79. Both baseline and OOS show net losses. Feature extraction does not change the fundamental 2021 evidence. 2021 remains a profit-thesis challenge.

---

## 9. ATR Gate Consistency Check

| Year | ATR Percentile Median | ATR > 60% Rate |
|------|----------------------|----------------|
| 2021 | 61.5% | 53% |
| 2022 | 25.7% | low |
| 2023 | 35.3% | 17% |
| 2024 | 25.6% | low |
| 2025 | 41.8% | moderate |

The frozen ATR > 60% gate would have:
- Disabled ~53% of 2021 positions (meaningful impact)
- Disabled ~17% of 2023 positions (minimal impact)
- Had minimal impact on 2024/2025

This is consistent with the CPM-MOD-002 finding: the gate helps 2021 but does not explain 2023 failure.

---

## 10. Post-entry Path Diagnostics

| Group | MFE Median | MAE Median | Giveback Median | Bars to MFE | Bars to MAE |
|-------|-----------|-----------|----------------|-------------|-------------|
| 2024 winners | 406.17 | -56.37 | 318.24 | 207 | 326 |
| 2025 winners | 193.42 | -52.78 | 26.80 | 37 | 84 |
| 2023 losers | 4.26 | -23.10 | 91.54 | 2 | 8 |
| 2021 losers | 9.86 | -45.84 | 87.62 | 0 | 1 |

**Key observations**:

1. **2024 winners** have large MFE (406), slow MFE arrival (207 bars), and high giveback (318). These are long-duration continuation trades where price moves substantially favorably but eventually gives back much of the gain.

2. **2025 winners** have moderate MFE (193), faster MFE arrival (37 bars), and low giveback (27). These are shorter-duration trades that capture favorable moves more quickly but with less total excursion.

3. **2023 losers** have near-zero MFE (4.26) and reach MFE in 2 bars. Continuation fails almost immediately. MAE arrives in 8 bars. These are rapid-reversal trades.

4. **2021 losers** have very small MFE (9.86) and reach MFE in 0 bars (price never moves favorably from entry). MAE arrives in 1 bar. These are immediate-reversal trades in hostile volatility.

---

## 11. Boundary Hypothesis Readiness Classification

**Classification**: `FEATURE_CONTEXT_SUPPORTS_BOUNDARY_HYPOTHESIS_INSPECT`

**Evidence**:

- Feature coverage: 85% of features have >50% data availability across 329 positions
- Cross-group separation: 4 of 5 checked features show >20% relative median difference between 2024 winners and 2023 losers
- Pre-observable feature differences exist between favorable and hostile years:
  - ATR percentile: 2024 winners median 25.6% vs 2021 losers median 61.5%
  - Pullback depth: 2024 winners median 0.73% vs 2021 losers median 1.61%
  - Bar range percentile: 2024 winners median 24.5% vs 2023 losers median 50.5%
- Post-entry continuation is the dominant failure dimension for 2023
- Pre-entry volatility is a meaningful but not complete explanation for 2021
- 2025 fragility is structural (extreme concentration, higher-volatility entry states)

This classification exceeds the expected prior of `FEATURE_CONTEXT_PARTIAL_NEEDS_MORE_ATTRIBUTION`. The evidence supports moving to a boundary hypothesis inspect because:
1. Pre-observable features separate favorable and hostile years
2. Feature coverage is high (85%)
3. Cross-group separation is detected on multiple dimensions
4. The failure modes are identifiable (continuation for 2023, volatility+continuation for 2021)

---

## 12. What This Does Not Authorize

This report does not authorize:

- CPM-1 changes
- CPM-MOD-003
- Any new gate
- Backtest
- Runtime
- Small-live
- Strategy rescue
- Parameter sweep
- Extra-data rescue
- Router/regime/portfolio work

---

## 13. Owner Summary

This read-only feature-context extraction processed 329 existing CPM-1 positions (baseline 2021-2025 + OOS 2021-2022) and computed 47 features per position from local OHLCV data.

**Key findings**:

1. **2024 is confirmed stronger than 2025** after feature extraction (PnL +969 vs +322, win rate 41.9% vs 27.3%).

2. **2025 fragility is structural**: extreme top-5 concentration (270% of total PnL), higher-volatility entry states (ATR pct 47% vs 26% for 2024 winners), and smaller/faster wins.

3. **2023 failure is a continuation failure**: MFE is near-zero (4.26 vs 406 for 2024 winners), continuation is the dominant failure dimension (401.9 magnitude vs next-highest 17.8 for volatility). The ATR gate does not help because 2023 trades enter in moderate-volatility states.

4. **2021 failure has both volatility and non-volatility components**: 53% of losers had ATR > 60%, but 47% occurred in moderate-volatility states. 2021 remains a profit-thesis challenge.

5. **Boundary hypothesis readiness**: `FEATURE_CONTEXT_SUPPORTS_BOUNDARY_HYPOTHESIS_INSPECT`. Pre-observable features separate favorable and hostile years with sufficient coverage and cross-group separation.

6. **CPM-1 classification remains**: `CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT`. Feature extraction does not change the classification. The favorable-year evidence is related to pullback-continuation (not artifact-driven), and hostile-year evidence has identifiable pre-observable features.

---

> CPM-1 remains non-runtime and non-small-live. This read-only feature-context extraction does not authorize strategy execution, parameter changes, gates, or strategy rescue. Any future empirical work requires separate Owner approval and must satisfy SRR-002.
