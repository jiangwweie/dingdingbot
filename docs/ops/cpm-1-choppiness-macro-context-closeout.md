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

# CPM-1 Choppiness And Macro Context Attribution Closeout

**Task ID**: CPM-1-CHOPPINESS-MACRO-CONTEXT-CLOSEOUT
**Date**: 2026-05-08
**Status**: Completed / docs-only attribution closeout
**Classification**: BOUNDARY_ATTRIBUTION_PARTIAL_KEEP_RESEARCH_ONLY
**CPM-1 Classification**: CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT (unchanged)

---

## 0. Boundary

This is a docs/report-only attribution closeout for CPM-1 unresolved failure modes. It integrates the prior continuation-proxy result and examines two remaining theory-backed OHLCV attribution directions: choppiness (CHOP) and 1D/3D macro trend context.

It is not:
- A gate proposal or gate definition
- A backtest or empirical run
- A parameter sweep or strategy rescue
- CPM-MOD-003, CPM-2, or E4 experiment
- Runtime or small-live authorization
- A decision to proceed with any empirical work

It may compute read-only features at existing CPM position entry timestamps and compare group distributions. It does not transform those findings into a trading rule.

---

## 1. Inputs Inspected

| Source | Type | Read-only |
|--------|------|-----------|
| `docs/ops/cpm-1-continuation-failure-preobservable-proxy-attribution.md` | Prior report | Yes |
| `reports/cpm-1-continuation-proxy-attribution/continuation_proxy_summary.json` | Prior summary | Yes |
| `reports/cpm-1-continuation-proxy-attribution/continuation_proxy_summary.md` | Prior summary | Yes |
| `docs/ops/cpm-1-applicability-boundary-hypothesis-inspect.md` | Prior inspect | Yes |
| `docs/ops/cpm-1-readonly-feature-context-extraction-report.md` | Feature extraction | Yes |
| `reports/cpm-1-readonly-feature-context-extraction/position_feature_context.csv` | Position features (329 positions) | Yes |
| `reports/cpm-1-readonly-feature-context-extraction/feature_group_summary.md` | Group distributions | Yes |
| `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md` | Methodology standard | Yes |
| `data/v3_dev.db` — klines table | ETH/USDT:USDT OHLCV (1h, 4h, 1d) | Yes |

No database writes. No strategy execution. No signal generation.

---

## 2. Prior Continuation-Proxy Conclusion

The continuation-proxy attribution (`CONTINUATION_PROXY_POST_HOC_ONLY`, 2026-05-08) established:

1. **No credible pre-observable continuation proxy was found.** Seven candidate proxies were evaluated. None achieved stronger than PLAUSIBLE classification.
2. **Bar range percentile is post-hoc only.** It has the largest empirical gap (25.9 points between 2024 winners and 2023 losers) but no prior hypothesis predicted it. It is contradicted by 2025 winners (41.2%) and 2024 top-5 winners (41.8%).
3. **2023 failure remains largely invisible before entry.** The dominant failure dimension is continuation (MFE magnitude 401.9), which has no clean pre-observable signature.
4. **H1 remains PLAUSIBLE_BUT_INCOMPLETE.** ATR percentile is plausible (pre-registered in CPM-MOD-002) but does not explain 2022 or separate 2023 from 2024.
5. **No frozen diagnostic is justified.** Recommendation D: continue attribution only.

This closeout does not reverse that conclusion unless CHOP or macro context provides clear new evidence.

---

## 3. Feature Definitions

### 3.1 CHOP / Choppiness features

Computed at each position entry timestamp using closed bars only (the last closed bar at or before the signal decision time).

**Formula**: `CHOP(n) = 100 * log10(sum(TR over n bars) / (highest high - lowest low over n bars)) / log10(n)`

CHOP ranges from 0 to 100. Higher values indicate more choppiness (range-bound, overlapping candles). Lower values indicate trending behavior (directional movement with less overlap).

| Feature | Source | Lookback |
|---------|--------|----------|
| h1_chop14 | 1h bars | 14 bars (14 hours) |
| h1_chop20 | 1h bars | 20 bars (20 hours) |
| h1_chop50 | 1h bars | 50 bars (50 hours) |
| h4_chop14 | 4h bars | 14 bars (56 hours) |
| h4_chop20 | 4h bars | 20 bars (80 hours) |
| h4_chop50 | 4h bars | 50 bars (200 hours) |

**Availability**: 100% across all 329 positions (sufficient warmup in all timeframes).

**CHOP theoretical motivation for H2**: If choppiness (range-bound overlapping action) is the underlying cause of 2023's continuation failure, then CHOP should distinguish 2023 losers (high CHOP, choppy) from 2024 winners (low CHOP, trending). This would provide theoretical support for the post-hoc bar_range clue by grounding it in a standard technical analysis concept.

### 3.2 1D macro trend features

| Feature | Definition | Availability |
|---------|-----------|-------------|
| d1_close | Last closed daily close at entry | 99.1% |
| d1_ema50 | Daily EMA(50) | 90.6% |
| d1_ema200 | Daily EMA(200) | 70.5% (2022+: 100%) |
| d1_dist_ema50_pct | (entry_price - d1_ema50) / d1_ema50 * 100 | 90.6% |
| d1_dist_ema200_pct | (entry_price - d1_ema200) / d1_ema200 * 100 | 70.5% (2022+: 100%) |
| d1_price_above_ema200 | 1 if entry_price > d1_ema200, else 0 | 70.5% (2022+: 100%) |
| d1_ema50_above_ema200 | 1 if d1_ema50 > d1_ema200, else 0 (golden cross) | 70.5% (2022+: 100%) |
| d1_ema50_slope_5d | (ema50_today - ema50_5d_ago) / ema50_5d_ago * 100 | 89.4% |
| d1_ema50_slope_20d | (ema50_today - ema50_20d_ago) / ema50_20d_ago * 100 | 86.9% |
| d1_ema200_slope_20d | (ema200_today - ema200_20d_ago) / ema200_20d_ago * 100 | 68.1% (2022+: 100%) |
| d1_ret_7d | 7-day return | 99.1% |
| d1_ret_30d | 30-day return | 95.4% |

### 3.3 3D macro trend features

Derived by resampling 1d bars into non-overlapping 3-day bars. 3D EMA200 requires 200 3-day bars (600 days) of warmup, becoming available from ~August 2022 onward.

| Feature | Definition | Availability |
|---------|-----------|-------------|
| d3_ema50 | 3D EMA(50) | 73.6% (2022+: 100%) |
| d3_ema200 | 3D EMA(200) | 30.7% (2023+: 100%, 2021: 0%, 2022: 20.2%) |
| d3_dist_ema50_pct | (entry_price - d3_ema50) / d3_ema50 * 100 | 73.6% |
| d3_dist_ema200_pct | (entry_price - d3_ema200) / d3_ema200 * 100 | 30.7% |
| d3_ema50_slope_5 | 3D EMA50 slope over 5 bars (15 days) | 73.6% |
| d3_ema50_slope_20 | 3D EMA50 slope over 20 bars (60 days) | 69.9% |
| d3_ret_10bars | 3D return over 10 bars (~30 days) | 95.4% |
| d3_ret_30bars | 3D return over 30 bars (~90 days) | 83.9% |

**Note**: 3D EMA200 is missing for all 2021 positions and 79.8% of 2022 positions. Where 3D EMA200 is unavailable, 3D EMA50 and 3D returns are used instead. Findings based on 3D EMA200 are restricted to 2023+ unless noted.

### 3.4 Hurst exponent (exploratory)

| Feature | Definition | Availability |
|---------|-----------|-------------|
| hurst_1h_50 | R/S Hurst over 1h 50-bar window | 100% |
| hurst_1h_100 | R/S Hurst over 1h 100-bar window | 100% |

**Critical caveat**: Hurst is window-sensitive, computed via simplified R/S analysis, and is exploratory only. It is not used as a primary conclusion.

---

## 4. CHOP / Choppiness Attribution

### 4.1 CHOP distributions by group

| Group | n | h1_chop14 | h1_chop20 | h1_chop50 | h4_chop14 | h4_chop20 | h4_chop50 |
|-------|---|-----------|-----------|-----------|-----------|-----------|-----------|
| 2023 losers | 15 | 47.51 | 46.41 | 45.71 | 46.84 | 45.18 | 50.02 |
| 2023 winners | 3 | 51.66 | 43.81 | 46.65 | 49.37 | 49.79 | 44.86 |
| 2024 winners | 13 | 49.74 | 45.56 | 48.48 | 49.78 | 55.77 | 50.44 |
| 2024 losers | 18 | 55.21 | 52.76 | 48.93 | 48.41 | 50.44 | 46.10 |
| 2024 top-5 | 5 | 45.27 | 48.73 | 51.36 | 51.07 | 56.04 | 51.84 |
| 2025 winners | 9 | 42.95 | 41.44 | 48.71 | 41.91 | 47.07 | 52.64 |
| 2025 top-5 | 5 | 42.95 | 40.84 | 40.07 | 35.78 | 38.25 | 47.65 |
| 2022 all | 94 | 52.09 | 49.43 | 43.99 | 43.51 | 47.01 | 48.96 |
| 2022 losers | 77 | 52.55 | 48.17 | 43.53 | 43.21 | 46.56 | 48.76 |
| 2022 winners | 17 | 45.73 | 49.95 | 49.03 | 51.05 | 48.66 | 50.44 |
| 2021 losers | 126 | 51.44 | 47.70 | 46.39 | 45.52 | 48.28 | 50.66 |
| 2021 high-ATR losers | 66 | 50.99 | 46.34 | 46.39 | 44.51 | 47.17 | 49.57 |
| 2021 mod-ATR losers | 60 | 52.01 | 50.40 | 47.10 | 45.90 | 48.96 | 50.98 |

### 4.2 Key comparison: 2023 losers vs 2024 winners

| Feature | 2023 Losers | 2024 Winners | Gap | Overlap |
|---------|------------|-------------|-----|---------|
| h1_chop14 | 47.51 | 49.74 | +2.23 | 43.1% |
| h1_chop20 | 46.41 | 45.56 | -0.86 | 46.7% |
| h1_chop50 | 45.71 | 48.48 | +2.77 | — |
| h4_chop14 | 46.84 | 49.78 | +2.94 | 42.1% |
| h4_chop20 | 45.18 | 55.77 | +10.59 | 28.7% |
| h4_chop50 | 50.02 | 50.44 | +0.42 | — |
| **h1_bar_range_pct90d** | **50.46** | **24.54** | **-25.93** | **28.6%** |
| **h1_atr14_pct90d** | **43.43** | **25.63** | **-17.80** | **44.3%** |

**Key finding**: CHOP does not distinguish 2023 losers from 2024 winners. The gaps are small (0.4 to 10.6 CHOP points) and inconsistent in direction. Overlap ranges from 28.7% to 46.7%. By contrast, raw bar_range_pct90d has a 25.9-point gap.

The only CHOP feature with a gap exceeding 10 points is h4_chop20 (10.59), but this gap is in the **opposite direction** from the choppiness hypothesis: 2024 winners enter at *higher* CHOP (55.77 vs 45.18), meaning 2024 winners enter in *choppier* 4h conditions than 2023 losers.

### 4.3 CHOP vs bar_range and ATR correlation

| Pair | Pearson r |
|------|-----------|
| h1_chop14 vs h1_bar_range_pct90d | -0.1264 |
| h1_chop14 vs h1_atr14_pct90d | -0.1131 |
| h1_chop14 vs h1_rv_72h | 0.1216 |
| h1_chop20 vs h1_bar_range_pct90d | -0.1327 |
| h1_chop20 vs h1_atr14_pct90d | -0.1618 |

**Key finding**: CHOP has near-zero correlation with bar_range, ATR, and realized volatility (|r| < 0.20 in all cases). CHOP measures a fundamentally different market property: the ratio of true range to directional range, which captures trending vs ranging behavior. It does not measure raw volatility magnitude.

This means CHOP cannot rescue the bar_range post-hoc classification by providing a theoretical foundation. The bar_range clue captures something about candle body extremity relative to smoothed average. CHOP captures something about directional persistence. These are different constructs.

### 4.4 CHOP by continuation label

| Label | n | h1_chop14 | h1_chop20 | MFE median |
|-------|---|-----------|-----------|-----------|
| immediate_failure | 139 | 50.01 | 48.31 | 5.30 |
| weak_continuation | 38 | 54.87 | 50.93 | 22.14 |
| normal_continuation | 83 | 51.74 | 48.99 | 46.32 |
| strong_continuation | 69 | 47.81 | 49.62 | 145.03 |

**Key finding**: CHOP does not predict continuation quality. Strong continuation trades (large MFE, TP2 reached) have the **lowest** CHOP values, but the difference from immediate failures is only 2.2 CHOP points. CHOP is not correlated with near-zero MFE or immediate failure.

### 4.5 Contradictions

**2025 winners contradiction**: 2025 winners enter at h1_chop14 = 42.95, lower than 2024 winners' 49.74. If lower CHOP (more trending) were favorable, 2025 should outperform 2024. But 2024 is materially stronger (PnL +969 vs +322, win rate 41.9% vs 27.3%).

**2024 top-5 contradiction**: 2024 top-5 winners enter at h1_chop14 = 45.27 and h4_chop20 = 56.04. This is higher than 2024 losers' h4_chop20 of 50.44. The best 2024 trades entered in choppier conditions.

**2022 winners vs losers**: 2022 winners have lower h1_chop14 (45.73 vs 52.55) but this is confounded by their dramatically lower ATR (5.77% vs 29.29%) and bar range (12.96% vs 30.83%).

### 4.6 CHOP classification

**`POST_HOC_OR_REDUNDANT`**

Rationale:
1. CHOP does not distinguish 2023 losers from 2024 winners (gaps < 11 points, overlaps 29-47%)
2. CHOP has near-zero correlation with bar_range and ATR (|r| < 0.20) — it measures a different property and cannot provide theoretical grounding for the bar_range clue
3. CHOP does not predict continuation labels or near-zero MFE
4. CHOP is contradicted by 2025 winners (lower CHOP but worse performance) and 2024 top-5 (higher CHOP but best performance)
5. No coherent threshold direction emerges from the data

CHOP measures trending vs ranging behavior, which is a theoretically interesting concept for a trend-following strategy. But the empirical evidence shows it does not separate favorable from hostile CPM-1 conditions under current entry/exit rules.

---

## 5. Hurst Exploratory Observation

| Group | n | H50 (1h 50-bar) | H100 (1h 100-bar) |
|-------|---|-----------------|-------------------|
| 2023 losers | 15 | 0.551 | 0.535 |
| 2023 winners | 3 | 0.529 | 0.492 |
| 2024 winners | 13 | 0.519 | 0.529 |
| 2024 losers | 18 | 0.502 | 0.509 |
| 2024 top-5 | 5 | 0.519 | 0.534 |
| 2025 winners | 9 | 0.496 | 0.504 |
| 2022 all | 94 | 0.526 | 0.523 |
| 2022 losers | 77 | 0.526 | 0.527 |
| 2022 winners | 17 | 0.535 | 0.504 |
| 2021 losers | 126 | 0.526 | 0.515 |
| 2021 mod-ATR losers | 60 | 0.544 | 0.526 |

**Observation**: Hurst exponents cluster tightly around 0.50 across all groups, with a range of only 0.055 (0.496 to 0.551). All values are near the random-walk boundary (H = 0.50). No group separation is detectable.

**Caveat**: Hurst is computed via simplified R/S analysis over short windows (50-100 bars). It is window-sensitive and exploratory. These values do not support any conclusion about market regime or CPM-1 applicability.

---

## 6. H2 Update: H2-LOW-BAR-RANGE

### 6.1 Prior state

H2-LOW-BAR-RANGE was classified as POST_HOC_CLUE_ONLY in the continuation-proxy attribution:
- No prior hypothesis predicted bar_range as a CPM-1 filter
- 2025 winners enter at bar_range 41.2% (close to 2023 losers' 50.5%)
- 2024 top-5 winners enter at bar_range 41.8%
- The clue is real but unsubstantiated by theory

### 6.2 Does CHOP upgrade H2?

**No.** CHOP does not provide theoretical support for H2 because:

1. CHOP and bar_range have near-zero correlation (r = -0.13). They measure different properties. CHOP cannot serve as the theoretical foundation for a bar_range-based filter.

2. CHOP does not distinguish the groups that bar_range distinguishes. The gap between 2023 losers and 2024 winners is 25.9 points for bar_range but only 0.4-10.6 points for CHOP features. If CHOP were the underlying cause, it should show at least comparable separation.

3. CHOP's own contradictions (2025, 2024 top-5) mirror bar_range's contradictions, suggesting both features capture noise rather than a stable market property.

4. The gap direction is inconsistent: for h4_chop20, 2024 winners have HIGHER choppiness than 2023 losers — the opposite of what a choppiness-causes-failure theory would predict.

### 6.3 Should H2 be reframed as CHOP/choppiness?

**No.** Reframing would require CHOP to show stronger or more consistent separation than raw bar_range. It shows weaker and less consistent separation.

### 6.4 H2 classification

**`H2_REMAINS_POST_HOC_ONLY`**

CHOP provides neither empirical improvement nor theoretical rescue for the bar_range clue. H2 remains a post-hoc empirical observation that is contradicted by 2025 and 2024 top-5 winners.

---

## 7. 1D / 3D Macro Trend Attribution

### 7.1 Macro trend distributions by group

| Group | n | dist_EMA200% | above_EMA200 | EMA50>EMA200 | EMA50_slope_20d | EMA200_slope_20d | ret_30d |
|-------|---|-------------|-------------|-------------|----------------|-----------------|--------|
| 2022 all | 94 | -16.95 | 13.8% | 2.1% | -5.56 | -4.68 | 11.26 |
| 2022 losers | 77 | -16.87 | 14.3% | 2.6% | -5.87 | -4.60 | 9.76 |
| 2022 winners | 17 | -22.19 | 11.8% | 0.0% | -4.59 | -5.25 | 12.77 |
| 2024 all | 31 | 13.01 | 74.2% | 74.2% | -2.16 | 2.80 | 0.49 |
| 2024 winners | 13 | 15.01 | 76.9% | 76.9% | 0.25 | 2.87 | 3.20 |
| 2024 losers | 18 | 12.91 | 72.2% | 72.2% | -2.84 | 2.80 | -0.27 |
| 2023 losers | 15 | 10.66 | 73.3% | 60.0% | -0.01 | 1.49 | 3.39 |
| 2025 winners | 9 | 26.34 | 66.7% | 66.7% | 1.96 | 5.85 | -0.79 |

### 7.2 2022 macro context: the hostile daily downtrend

2022 CPM-1 entries occurred inside a severe daily downtrend:

- **86.2% of entries below 1D EMA200**: Price was below the long-term trend average at nearly all 2022 entries.
- **97.9% with EMA50 below EMA200**: The golden cross was absent. The 50-day average was below the 200-day average, confirming a death-cross regime.
- **1D EMA50 slope = -5.56%**: The 50-day average was declining at 5.6% per 20 days — a sustained downtrend.
- **1D EMA200 slope = -4.68%**: Even the 200-day average was declining, indicating a deep and persistent bearish regime.
- **Price 16.95% below EMA200**: The median entry was nearly 17% below the long-term average, in deeply oversold territory within a bearish trend.

### 7.3 2022 vs 2024 macro separation

| Feature | 2022 All | 2024 Winners | Gap | Overlap |
|---------|---------|-------------|-----|---------|
| d1_dist_ema200_pct | -16.95 | +15.01 | 31.96 | 27.3% |
| d1_price_above_ema200 | 13.8% | 76.9% | — | — |
| d1_ema50_above_ema200 | 2.1% | 76.9% | — | — |
| d1_ema50_slope_20d | -5.56 | +0.25 | 5.81 | 50.0% |
| d1_ema200_slope_20d | -4.68 | +2.87 | 7.54 | 27.3% |
| d3_dist_ema50_pct | -14.02 | +11.22 | 25.25 | 34.0% |
| d3_dist_ema200_pct | -43.05 | +24.02 | 67.07 | **0.0%** |
| d3_ema50_slope_20 | -13.69 | +11.11 | 24.80 | 23.1% |

**Key finding**: Macro trend features provide the strongest separation between 2022 and 2024 of any feature family examined across both the continuation-proxy and this closeout.

- **d3_dist_ema200_pct**: 0.0% overlap. Complete separation. 2022 entries are 43% below 3D EMA200; 2024 winners are 24% above. No threshold needed — the distributions do not touch.
- **d1_dist_ema200_pct**: 27.3% overlap, 31.96-point gap.
- **d1_price_above_ema200**: Only 13.8% of 2022 entries vs 76.9% of 2024 entries are above the daily EMA200.
- **d1_ema50_above_ema200**: Only 2.1% of 2022 entries vs 76.9% of 2024 entries have the golden cross active.

### 7.4 Were 2022 entries hostile long signals inside a bearish macro regime?

**Yes.** CPM-1 is a LONG-only pullback-continuation strategy. It enters on local 1h Pinbar signals confirmed by 4h EMA60 trend. In 2022:

1. Local 1h/4h signals triggered normally (no local filter blocked them).
2. But the daily trend was firmly bearish: price below EMA200, EMA50 below EMA200, both averages declining.
3. The 3D context was even more hostile: 43% below 3D EMA200, 3D EMA50 declining at -13.7% per 20 bars.
4. 2022 long entries were local bullish signals against a macro bearish backdrop.

### 7.5 Does macro context explain why low ATR was insufficient in 2022?

**Yes.** The continuation-proxy attribution noted that 2022 has nearly identical ATR percentile to 2024 winners (25.7% vs 25.6%) but loses. The macro context explains this paradox:

- Low ATR in 2022 reflects low realized volatility within a bearish trend, not a calm bullish environment.
- Low ATR is necessary but not sufficient for CPM-1 success. It indicates low local volatility but says nothing about macro trend direction.
- In 2024, low ATR coincides with price above EMA200 and a bullish macro structure — the strategy works.
- In 2022, low ATR coincides with price 17% below EMA200 and a death-cross regime — the strategy fails despite favorable local volatility.

The ATR gate (CPM-MOD-002, threshold > 60%) was designed for high-volatility entries (2021 type). It correctly addresses 2021 but is silent on 2022 because 2022's failure mode is macro-directional, not volatility-based.

### 7.6 2022 winners vs losers: macro context

| Feature | 2022 Winners (n=17) | 2022 Losers (n=77) |
|---------|--------------------|--------------------|
| d1_dist_ema200_pct | -22.19 | -16.87 |
| d1_price_above_ema200 | 11.8% | 14.3% |
| d1_ema50_above_ema200 | 0.0% | 2.6% |
| d1_ret_30d | 12.77% | 9.76% |
| h1_atr14_pct90d | 5.77 | 29.29 |
| h1_bar_range_pct90d | 12.96 | 30.83 |

2022 winners do not escape the hostile macro regime (0% have golden cross, 88% below EMA200). They succeed despite it, entering at dramatically lower ATR (5.77% vs 29.29%) and bar range (12.96% vs 30.83%). This suggests that within a hostile macro regime, only the very calmest microstates produce viable CPM-1 entries — but these are rare (17 of 94 entries, 18.1%).

---

## 8. H5 Macro-Context Hypothesis

### 8.1 Hypothesis definition

**H5-MACRO-LONG-BIAS-CONTEXT**

CPM-1 LONG-only pullback-continuation requires not only local 1h/4h uptrend confirmation but also a non-hostile 1D/3D macro trend context. Local long signals generated against a macro downtrend produce losses because continuation is structurally impeded by higher-timeframe selling pressure.

### 8.2 Evidence

**Supporting**:
- 2022 entries occur 86.2% below 1D EMA200, with 97.9% death-cross regime
- 2022 vs 2024 macro separation is the strongest of any feature family (d3_dist_ema200_pct overlap: 0%)
- 2022 failure mode (low ATR, weak continuation, cost-dominated) is consistent with macro downtrend pressure absorbing local bullish momentum
- CPM-1's 4h EMA60 confirmation is insufficient to capture daily/3D trend direction
- 2022 winners are not macro-exempt: 0% have golden cross, but they enter at extreme low ATR/bar_range (rare calm microstates)

**Weakening**:
- 2022 is a small sample (94 positions, 17 winners)
- 2022 is one year — the hypothesis is derived from one hostile regime
- The hypothesis does not predict 2023 failure (2023 entries are 73.3% above EMA200, 60% with golden cross — macro was non-hostile)
- 2024 top-5 winners enter at d1_dist_ema200_pct = -8.43 and only 40% above EMA200 — these excellent trades occur near or below the daily EMA200
- Without a second hostile-macro year in the dataset, the hypothesis cannot be validated out-of-sample

### 8.3 H5 classification

**`PLAUSIBLE_FOR_FUTURE_INSPECT`**

Rationale:
- Has clear theoretical motivation (LONG-only strategy needs non-hostile macro trend)
- Has strong empirical separation for 2022 (0% overlap on d3_dist_ema200_pct)
- Explains why low ATR was insufficient in 2022 (a previously unexplained paradox)
- But: derived from one year only, does not explain 2023, and has 2024 top-5 contradiction
- Is not eligible for frozen diagnostic (requires multi-year hostile-macro validation)

---

## 9. 2021 Moderate-ATR Loss Review

### 9.1 Context

The feature-context extraction found that 47% of 2021 losses (60 of 128 losers) occurred at ATR percentile ≤ 60%. These are the "unexplained" 2021 losses that the ATR gate cannot address.

### 9.2 CHOP context

| Group | n | h1_chop14 | h1_chop20 |
|-------|---|-----------|-----------|
| 2021 high-ATR losers | 66 | 50.99 | 46.34 |
| 2021 mod-ATR losers | 60 | 52.01 | 50.40 |
| 2024 winners (ref) | 13 | 49.74 | 45.56 |

2021 moderate-ATR losers have similar CHOP values to 2021 high-ATR losers and 2024 winners. CHOP does not explain the moderate-ATR 2021 losses.

### 9.3 Macro context

| Feature | 2021 mod-ATR Losers | 2024 Winners | Gap |
|---------|--------------------|--------------------|-----|
| d1_dist_ema200_pct | +38.18 | +15.01 | -23.17 |
| d1_price_above_ema200 | 100.0% | 76.9% | — |
| d1_ema50_above_ema200 | 100.0% | 76.9% | — |
| d1_ema50_slope_20d | +8.52 | +0.25 | -8.27 |
| d1_ret_30d | +12.16 | +3.20 | -8.96 |
| d3_dist_ema50_pct | +23.62 | +11.22 | -12.39 |
| d3_ret_30bars | +35.29 | +16.34 | -18.96 |

**Key finding**: 2021 moderate-ATR losers occur in a strongly bullish macro context (100% above EMA200, 100% golden cross) but at extreme macro extension:

- Price is 38.18% above daily EMA200 (vs 15.01% for 2024 winners)
- 30-day return is +12.16% (vs +3.20% for 2024 winners)
- 3D return over 90 days is +35.29% (vs +16.34% for 2024 winners)
- EMA50 slope is +8.52% per 20 days (vs +0.25% for 2024 winners)

2021 moderate-ATR losses are macro-overextension losses. The macro trend is bullish (correct direction for CPM-1 LONG) but stretched far beyond mean. CPM-1 entries at extreme macro extension fail because pullback-continuation cannot overcome the mean-reversion pressure from a severely extended trend.

### 9.4 Classification

2021 moderate-ATR losses are **partially explained by macro overextension**. CHOP does not contribute. The macro context provides a plausible mechanism (extended trend → mean-reversion pressure → continuation failure) but this is a separate failure mode from 2022 (hostile direction) and 2023 (invisible continuation failure).

---

## 10. Overall CPM Boundary Status

### 10.1 Attribution progress

| Failure mode | Attribution status | Pre-observable feature | Classification |
|-------------|-------------------|----------------------|----------------|
| 2021 high-volatility | Partial | ATR percentile > 60% | Addressed by CPM-MOD-002 (frozen) |
| 2021 moderate-volatility | Partial | Macro overextension (distance to EMA200, 30d return) | Post-hoc insight |
| 2022 low-vol LONG failure | Strengthened | 1D/3D macro downtrend (below EMA200, death cross, declining slopes) | H5 PLAUSIBLE |
| 2023 continuation failure | Unchanged | None found | Invisible under current features |
| 2024 favorable | Confirmed | Low ATR, non-hostile macro | Reference year |
| 2025 fragile favorable | Confirmed | Higher ATR, higher-volatility entry states | Structural fragility |

### 10.2 What CHOP added

Nothing. CHOP does not distinguish favorable from hostile years, does not correlate with the post-hoc bar_range clue, and does not predict continuation quality. It measures a different market property (trending vs ranging behavior) that is empirically irrelevant to CPM-1 outcomes under current rules.

### 10.3 What macro context added

Macro context partially explains 2022 failure. This is the first pre-observable feature family that cleanly separates 2022 from 2024 with near-zero overlap on 3D distance to EMA200. It also provides a coherent mechanism: CPM-1 LONG entries inside a hostile daily downtrend fail because continuation is structurally impeded by macro selling pressure.

However, macro context does not help with 2023 (the most damaging failure mode), and the hypothesis is derived from one year only.

### 10.4 Remaining gaps

1. **2023 continuation failure remains unexplained.** No pre-observable feature family — including CHOP and macro context — separates 2023 losers from 2024 winners. The dominant failure dimension (continuation) is invisible before entry.

2. **2021 moderate-ATR losses are partially explained** (macro overextension) but this insight is post-hoc and not pre-registered.

3. **H5 requires out-of-sample validation** that cannot occur without a second hostile-macro year in the dataset.

### 10.5 Boundary classification

**`BOUNDARY_ATTRIBUTION_PARTIAL_KEEP_RESEARCH_ONLY`**

Rationale:
- Macro context adds genuine information for 2022 (H5 is PLAUSIBLE)
- CHOP adds no information (POST_HOC_OR_REDUNDANT)
- 2023 remains unexplained (dominant failure mode invisible)
- 2021 partially explained (overextension, post-hoc)
- No single hypothesis reaches the strength needed for frozen diagnostic
- Research should continue but only along the H5 macro-direction axis if further work is authorized

---

## 11. SRR-002 Risk Review

| SRR-002 Criterion | Status |
|-------------------|--------|
| Pre-observable features only | CHOP and macro features are all pre-observable (computable from closed bars before entry) |
| No post-entry label leakage | No continuation labels, MFE, or MAE used as inputs |
| No composite fitting | Each feature examined independently; no multi-feature threshold search |
| No threshold optimization | No thresholds defined or optimized |
| Prior hypothesis | CHOP was motivated by theoretical support for bar_range (failed). H5 was motivated by 2022 paradox (partially supported). |
| Out-of-sample validation | H5 cannot be validated out-of-sample (one hostile year only) |
| Post-hoc penalty | CHOP findings are post-hoc (no prior hypothesis for CHOP specifically). H5 findings have moderate post-hoc risk (derived from 2022 data). |

**SRR-002 compliance**: This closeout is compliant. No empirical work was performed. No gates, thresholds, or frozen diagnostics are proposed. All features are pre-observable. H5 is classified PLAUSIBLE, not actionable.

---

## 12. Recommendation

**D — Continue attribution only**

### Evaluation of other options

**A (Stop CPM line)**: Not warranted. H5 provides genuine new information about 2022. Stopping would discard a plausible, theory-backed direction without investigation.

**B (Preserve only)**: Close to D. The difference is that H5 has enough theoretical grounding to justify one more attribution cycle if the Owner wishes. But no empirical work is justified yet.

**C (Frozen diagnostic)**: Not justified. Requires one small, theory-backed, pre-observable hypothesis that is clearly stronger, does not rely on post-entry labels, does not require composite fitting, and has clear information gain. H5 does not meet these criteria:
- Derived from one year only (2022)
- Does not explain 2023 (the dominant failure mode)
- Has 2024 top-5 contradiction (best trades at -8.43% below EMA200)
- Cannot be validated out-of-sample without another hostile-macro year
- Would require threshold definition (what macro state is "hostile"?), which is fitting

**E (Owner decision)**: Not needed. Attribution can continue under D without new authorization.

### Rationale for D

H5-MACRO-LONG-BIAS-CONTEXT is the first new theory-backed finding since CPM-MOD-002. It partially explains 2022 (the most stubborn unexplained failure) and has a clear mechanism (LONG-only strategy against macro downtrend). But it is early-stage: one year, no out-of-sample, 2024 top-5 contradiction, and does not address 2023.

If the Owner authorizes further work, the most productive direction would be:
- Test H5 against additional hostile-macro periods (if available in longer data history)
- Examine whether macro filters have information gain independent of the existing ATR gate
- Assess whether combining macro context with ATR percentile improves boundary definition

No such work is authorized by this report.

---

## 13. Explicit Prohibitions

This report does not authorize:

- CPM-1 changes
- CPM-MOD-003
- CPM-2
- Any new gate
- Backtest
- Empirical diagnostic
- Parameter sweep
- Threshold optimization
- Runtime
- Small-live
- Strategy rescue
- Lower-timeframe rescue
- Extra-data rescue
- CVD/order-flow data work
- Router/regime/portfolio work

---

## 14. Output Artifacts

| File | Description |
|------|-------------|
| `reports/cpm-1-choppiness-macro-context-closeout/position_context_chop_macro.csv` | Per-position CHOP + macro features (329 rows) |
| `reports/cpm-1-choppiness-macro-context-closeout/position_context_chop_macro.jsonl` | Per-position CHOP + macro features (JSONL) |
| `reports/cpm-1-choppiness-macro-context-closeout/chop_macro_group_summary.json` | Group distributions, classifications, key findings |
| `docs/ops/cpm-1-choppiness-macro-context-closeout.md` | This report |

---

## 15. Owner Summary

This closeout attribution examined CHOP/choppiness and 1D/3D macro trend context for CPM-1's unresolved failure modes. 329 positions were enriched with 6 CHOP features, 12 daily macro features, 9 3-day macro features, and 2 Hurst features.

**CHOP/choppiness**: Adds nothing. CHOP does not distinguish 2023 losers from 2024 winners (gaps < 11 CHOP points, overlaps 29-47%). It has near-zero correlation with bar_range and ATR (|r| < 0.20), meaning it cannot provide theoretical support for the post-hoc bar_range clue. CHOP is contradicted by 2025 winners (lower CHOP but worse performance) and 2024 top-5 winners (higher CHOP but best performance). Classification: `POST_HOC_OR_REDUNDANT`. H2 remains `H2_REMAINS_POST_HOC_ONLY`.

**Hurst**: Exponents cluster around 0.50 across all groups with no separation. Exploratory only, no conclusion.

**1D/3D macro context**: Partially explains 2022. In 2022, 86% of entries are below daily EMA200, 98% have death-cross regime, and both EMA50/EMA200 slopes are negative. The 3D distance to EMA200 shows 0% overlap between 2022 and 2024 winners — the strongest separation found in any feature family across all CPM-1 attribution work. This explains the previously paradoxical finding that 2022 has identical ATR to 2024 but loses: low ATR in a bearish macro trend is not the same as low ATR in a bullish macro trend. Classification: `PLAUSIBLE_FOR_FUTURE_INSPECT`.

**2021 moderate-ATR losses**: Not explained by CHOP. Partially explained by macro overextension (38% above EMA200, +12% 30-day return vs +3% for 2024 winners). These are mean-reversion losses in an extended bullish trend.

**H5-MACRO-LONG-BIAS-CONTEXT**: Defined as a docs-only hypothesis. CPM-1 LONG-only requires non-hostile macro trend context. Supported by 2022 evidence but not yet validated out-of-sample.

**Overall boundary status**: `BOUNDARY_ATTRIBUTION_PARTIAL_KEEP_RESEARCH_ONLY`. The dominant 2023 failure mode remains invisible. 2022 is partially explained by macro context. CHOP adds no value.

**CPM-1 classification**: `CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT` — unchanged.

**Recommendation**: **D — Continue attribution only.** H5 is worth one more investigation cycle if authorized. Frozen diagnostic is not justified.

---

> CPM-1 remains non-runtime and non-small-live. This choppiness and macro-context closeout does not authorize CPM-1 changes, gates, empirical diagnostics, runtime use, or strategy rescue. Any future empirical work requires separate Owner approval and must satisfy SRR-002.
