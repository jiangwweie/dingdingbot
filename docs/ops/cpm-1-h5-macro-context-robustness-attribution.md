# CPM-1 H5 Macro-Context Robustness Attribution Review

**Task ID**: CPM-1-H5-MACRO-CONTEXT-ROBUSTNESS-ATTRIBUTION
**Date**: 2026-05-08
**Status**: Completed / docs-only robustness attribution review
**Classification**: H5_PARTIAL_BUT_INCOMPLETE
**CPM-1 Classification**: CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT (unchanged)

---

## 0. Boundary

This is a docs/report-only robustness attribution review for the H5-MACRO-LONG-BIAS-CONTEXT hypothesis. It determines whether H5 is a robust, theory-backed explanation for CPM-1's 2022 low-volatility LONG-only failure and 2021 moderate-ATR loss subset, or whether it is only a one-year separation artifact.

It is not:
- A gate proposal or gate definition
- A backtest or empirical run
- A parameter sweep or strategy rescue
- CPM-MOD-003, CPM-2, or E4 experiment
- Runtime or small-live authorization
- A decision to proceed with any empirical work
- A frozen diagnostic

It may read existing reports, inspect generated artifacts, compute descriptive statistics from already-generated data, and produce one docs report. It does not transform findings into a trading rule.

---

## 1. Inputs Inspected

| Source | Type | Read-only |
|--------|------|-----------|
| `docs/ops/cpm-1-choppiness-macro-context-closeout.md` | Prior closeout | Yes |
| `reports/cpm-1-choppiness-macro-context-closeout/position_context_chop_macro.csv` | Per-position features (329 rows) | Yes |
| `reports/cpm-1-choppiness-macro-context-closeout/position_context_chop_macro.jsonl` | Per-position features (JSONL) | Yes |
| `reports/cpm-1-choppiness-macro-context-closeout/chop_macro_group_summary.json` | Group distributions | Yes |
| `reports/cpm-1-choppiness-macro-context-closeout/chop_macro_group_summary.md` | Group distributions (markdown) | Yes |
| `docs/ops/cpm-1-continuation-failure-preobservable-proxy-attribution.md` | Prior proxy attribution | Yes |
| `docs/ops/cpm-1-applicability-boundary-hypothesis-inspect.md` | Boundary hypothesis inspect | Yes |
| `docs/ops/cpm-1-readonly-feature-context-extraction-report.md` | Feature extraction | Yes |
| `docs/ops/srr-002-research-methodology-and-applicability-boundary-upgrade.md` | Methodology standard | Yes |

No database reads, writes, backtests, strategy execution, or signal generation.

---

## 2. H5 Restatement

### 2.1 Hypothesis definition

**H5-MACRO-LONG-BIAS-CONTEXT**

CPM-1 is a LONG-only 1h pullback-continuation module with 4h confirmation. It may require a non-hostile 1D/3D macro trend context. Local 1h/4h long signals may fail when they occur inside a hostile daily/3D bearish regime or after excessive bullish macro extension.

### 2.2 Scope limitations (must be stated upfront)

**H5 is not a complete CPM boundary.**

- H5 does not explain 2023 continuation failure. 2023 entries are 73.3% above 1D EMA200, 60% with golden cross — macro context was non-hostile. Yet 83.3% of 2023 positions lost. H5 cannot explain this.
- H5 may explain 2022 low-volatility failure (bearish macro regime).
- H5 may partially explain 2021 moderate-ATR losses (bullish overextension).
- H5 addresses only two of the three unresolved failure modes (2022, 2021 moderate-ATR). The third (2023) remains outside H5's explanatory scope.

### 2.3 Two distinct hostile states

H5 posits two hostile macro states for CPM-1 LONG entries:

1. **Bearish hostile state (2022 type)**: Price below daily/3D EMA200, death-cross regime, declining EMA slopes. LONG-only pullback continuation fails because macro selling pressure absorbs local bullish momentum.

2. **Bullish overextension state (2021 type)**: Price far above daily/3D EMA200, aggressive prior returns, steep EMA slopes. LONG entries in a severely extended trend fail because pullback continuation cannot overcome mean-reversion pressure.

These are opposite macro conditions that produce the same outcome: CPM-1 LONG failure.

---

## 3. Feature Reliability and Warmup Audit

### 3.1 Data source

OHLCV start date: 2020-01-01 (ETH/USDT:USDT 1h bars: 54,768 bars).

### 3.2 1D features warmup

| Feature | Bars needed | Calendar days | Available from |
|---------|------------|---------------|----------------|
| d1_ema50 | 50 1d bars | 50 days | ~2020-02-19 |
| d1_ema200 | 200 1d bars | 200 days | ~2020-07-18 |
| d1_ema50_slope_20d | 220 1d bars | 220 days | ~2020-08-07 |
| d1_ema200_slope_20d | 220 1d bars | 220 days | ~2020-08-07 |
| d1_dist_ema200_pct | 200 1d bars | 200 days | ~2020-07-18 |
| d1_ret_30d | 30 1d bars | 30 days | ~2020-01-31 |

**1D warmup verdict**: All 1D features have sufficient warmup for 2021+ positions. The earliest CPM-1 positions are from 2021. All 1D EMA200-based features are reliable for the full analysis period.

**Missing data for 1D features by year:**

| Feature | 2021 valid | 2022 valid | 2023 valid | 2024 valid | 2025 valid |
|---------|-----------|-----------|-----------|-----------|-----------|
| d1_dist_ema200_pct | 56/153 (36.6%) | 94/94 (100%) | 18/18 (100%) | 31/31 (100%) | 33/33 (100%) |
| d1_ema200_slope_20d | 48/153 (31.4%) | 94/94 (100%) | 18/18 (100%) | 31/31 (100%) | 33/33 (100%) |
| d1_price_above_ema200 | 56/153 (36.6%) | 94/94 (100%) | 18/18 (100%) | 31/31 (100%) | 33/33 (100%) |
| d1_ema50_above_ema200 | 56/153 (36.6%) | 94/94 (100%) | 18/18 (100%) | 31/31 (100%) | 33/33 (100%) |
| d1_ret_30d | 138/153 (90.2%) | 94/94 (100%) | 18/18 (100%) | 31/31 (100%) | 33/33 (100%) |

**2021 caveat**: 1D EMA200-based features are available for only 36.6% (56 of 153) of 2021 positions. These 56 positions are the latest 2021 entries (approximately from August 2021 onward). The earlier 2021 entries lack 1D EMA200 because the 200-day warmup window extends back before the 2020-01-01 data start. Findings about 2021 based on 1D EMA200 apply only to the later-2021 subset. The 2021 moderate-ATR losers have 24 valid positions (of 60), so any 1D EMA200-based finding for this group represents 40% of the group.

### 3.3 3D features warmup

3D bars are constructed by resampling 1d bars into non-overlapping 3-day bars. 3D EMA200 requires 200 3-day bars = 600 calendar days of warmup.

| Feature | Bars needed | Calendar days | Available from |
|---------|------------|---------------|----------------|
| d3_ema50 | 50 3d bars | 150 days | ~2020-05-29 |
| d3_ema200 | 200 3d bars | 600 days | ~2021-08-12 |
| d3_ema50_slope_20 | 70 3d bars | 210 days | ~2020-07-28 |
| d3_ret_30bars | 30 3d bars | 90 days | ~2020-03-30 |

**3D EMA200 availability by year:**

| Year | Positions | Valid d3_ema200 | Valid % |
|------|-----------|----------------|---------|
| 2021 | 153 | 0 | **0.0%** |
| 2022 | 94 | 19 | **20.2%** |
| 2023 | 18 | 18 | 100.0% |
| 2024 | 31 | 31 | 100.0% |
| 2025 | 33 | 33 | 100.0% |

**Critical warning**: 3D EMA200 is **unavailable for all 2021 positions and 79.8% of 2022 positions**. The 19 valid 2022 positions are the entries from approximately August 2022 onward. The earlier 2022 entries (including those in the deepest bear-market phase) lack 3D EMA200 values.

**3D EMA50 availability:**

| Year | Positions | Valid d3_ema50 | Valid % |
|------|-----------|---------------|---------|
| 2021 | 153 | 66 | 43.1% |
| 2022 | 94 | 94 | 100.0% |
| 2023 | 18 | 18 | 100.0% |
| 2024 | 31 | 31 | 100.0% |
| 2025 | 33 | 33 | 100.0% |

**3D return features availability:**

| Year | Valid d3_ret_30bars | Valid % |
|------|-------------------|---------|
| 2021 | 100 | 65.4% |
| 2022 | 94 | 100.0% |
| 2023 | 18 | 100.0% |
| 2024 | 31 | 100.0% |
| 2025 | 33 | 100.0% |

### 3.4 Warmup impact assessment

**1D features are reliable** for all years from 2022 onward. For 2021, 1D EMA200 features are available for the later subset only (36.6% of positions).

**3D EMA200 is unreliable for 2021 and early 2022**. Any conclusion about 2022 that depends on d3_dist_ema200_pct is restricted to 20.2% of 2022 positions (19 of 94). The 75 positions without 3D EMA200 values are likely those from January through July 2022 — which includes the deepest bear-market phase (Terra/Luna crash, 3AC collapse).

**3D EMA50 is reliable** from 2022 onward (100% coverage) and partially available for 2021 (43.1%).

**3D return features are reliable** from 2022 onward and partially available for 2021 (65.4%).

**Conclusion**: All conclusions based on 3D EMA200 for 2021 or early 2022 must be marked **CAVEATED_BY_WARMUP**. 1D features and 3D EMA50/return features are reliable and carry no warmup caveat for the 2022+ analysis.

---

## 4. 2022 Robustness Review

### 4.1 H5 feature set: 2022 context

| Feature | 2022 All (n=94) | 2022 Losers (n=77) | 2022 Winners (n=17) | Assessment |
|---------|----------------|--------------------|--------------------|-----------|
| d1_dist_ema200_pct | -16.95 | -16.87 | -22.19 | Consistently far below EMA200 |
| d1_price_above_ema200 | 13.8% | 14.3% | 11.8% | ~86% below EMA200 |
| d1_ema50_above_ema200 | 2.1% | 2.6% | 0.0% | 98% death-cross |
| d1_ema50_slope_20d | -5.56 | -5.87 | -4.59 | Strongly negative |
| d1_ema200_slope_20d | -4.68 | -4.60 | -5.25 | Strongly negative |
| d1_ret_30d | 11.26% | 9.76% | 12.77% | Positive (rally within bear) |
| d3_dist_ema50_pct | -14.02 | -14.01 | -15.69 | Below 3D EMA50 |
| d3_ema50_slope_20 | -13.69 | -13.68 | -14.69 | Strongly negative |
| d3_ret_30bars | -27.44% | -27.44% | -22.62% | Negative 90-day return |

### 4.2 Is 2022 consistently in hostile macro regime?

**Yes.** Across all 1D macro indicators:

- 86.2% of entries below 1D EMA200
- 97.9% with death-cross (EMA50 below EMA200)
- 1D EMA50 slope = -5.56% (strong sustained downtrend)
- 1D EMA200 slope = -4.68% (the 200-day average itself was declining)
- 3D EMA50 slope = -13.69% (severe multi-week decline)

This is consistent across losers AND winners. The few 2022 winners (17 of 94) do NOT escape the hostile regime: 0% have golden cross, 88% are below EMA200. They succeed despite the hostile macro, not because they avoid it.

### 4.3 Do 2022 winners differ from 2022 losers?

| Feature | 2022 Winners | 2022 Losers | Direction |
|---------|-------------|------------|-----------|
| d1_dist_ema200_pct | -22.19 | -16.87 | Winners even deeper below EMA200 |
| d1_ema50_above_ema200 | 0.0% | 2.6% | Winners: pure death cross |
| d1_ema200_slope_20d | -5.25 | -4.60 | Winners: steeper 200-day decline |
| h1_atr14_pct90d | 5.77 | 29.29 | Winners: dramatically lower ATR |
| h1_bar_range_pct90d | 12.96 | 30.83 | Winners: dramatically lower bar range |

**Key finding**: 2022 winners do not escape H5's hostile regime. They succeed in rare calm microstates (extreme low ATR 5.77%, low bar range 12.96%) within the bear market. Macro context does not distinguish 2022 winners from 2022 losers; microstate calmness does. This weakens H5 as a within-year filter but does not weaken it as a cross-year separator.

### 4.4 Does 2022 differ from 2024 winners across multiple features?

**Yes, across all 1D features simultaneously:**

| Feature | 2022 All | 2024 Winners | Gap | Direction |
|---------|---------|-------------|-----|-----------|
| d1_dist_ema200_pct | -16.95 | +15.01 | 31.96 | 2022 far below, 2024 above |
| d1_price_above_ema200 | 13.8% | 76.9% | 63.1 pp | |
| d1_ema50_above_ema200 | 2.1% | 76.9% | 74.8 pp | |
| d1_ema50_slope_20d | -5.56 | +0.25 | 5.81 | 2022 declining, 2024 flat |
| d1_ema200_slope_20d | -4.68 | +2.87 | 7.54 | 2022 declining, 2024 rising |
| d3_dist_ema50_pct | -14.02 | +11.22 | 25.24 | |
| d3_ema50_slope_20 | -13.69 | +11.11 | 24.80 | |
| d3_ret_30bars | -27.44% | +16.34% | 43.78 pp | |

The separation is not confined to a single feature. It spans distance, slope, cross-state, and return features across both 1D and 3D timeframes. This is multi-dimensional separation, not a single-feature artifact.

### 4.5 Does macro context explain 2022 better than ATR, CHOP, or bar range?

**Yes.** ATR percentile fails as an explanation for 2022:

| Feature | 2022 All | 2024 Winners | Gap |
|---------|---------|-------------|-----|
| h1_atr14_pct90d | 25.7 | 25.6 | 0.1 (identical) |
| h1_bar_range_pct90d | 28.9 | 24.5 | 4.4 (small) |

2022 has the same ATR percentile as 2024 winners. CHOP was already classified POST_HOC_OR_REDUNDANT. Macro context is the only feature family that cleanly separates 2022 from 2024 with near-zero overlap on 3D distance to EMA200.

The mechanism is clear: low ATR in a bearish macro trend is not the same as low ATR in a bullish macro trend. ATR measures volatility magnitude, not direction. Macro context captures the directional environment that ATR is blind to.

### 4.6 Does 2025 contradict H5?

**Partially.** 2025 winners are heterogeneous:

| Feature | 2025 Winners (n=9) | 2025 Top-5 (n=5) |
|---------|-------------------|-----------------|
| d1_dist_ema200_pct | +26.34 | -19.36 |
| d1_price_above_ema200 | 66.7% | 40.0% |
| d1_ema50_above_ema200 | 66.7% | 40.0% |
| d1_ema50_slope_20d | +1.96 | -3.27 |
| d1_ema200_slope_20d | +5.85 | -5.44 |

2025 winners (all 9) enter in a moderately bullish macro context (66.7% above EMA200, positive slopes). This supports H5.

However, 2025 top-5 winners (the best trades) enter in a hostile macro context: 60% below EMA200, death cross for 60%, EMA200 slope -5.44%. These excellent trades occur in a 2022-like hostile regime.

This contradiction is structurally identical to the 2024 top-5 contradiction: the best trades sometimes occur in hostile macro conditions. This means macro context cannot serve as a clean gate without filtering out some of CPM-1's best trades.

---

## 5. 3D EMA200 Separation Check

### 5.1 The reported "0% overlap" finding

The closeout reported 0% overlap between 2022 and 2024 winners on `d3_dist_ema200_pct`. Let us audit this carefully.

### 5.2 Feature provenance

Feature: `d3_dist_ema200_pct` — distance from entry price to 3D EMA(200), as a percentage of 3D EMA(200).

Computed by: resampling 1d bars into non-overlapping 3-day bars, computing EMA(200) on 3-day closes, then calculating `(entry_price - d3_ema200) / d3_ema200 * 100`.

### 5.3 Sample sizes

| Group | Total positions | Valid d3_dist_ema200_pct | Valid % |
|-------|----------------|------------------------|---------|
| 2022 all | 94 | 19 | **20.2%** |
| 2022 losers | 77 | 14 | 18.2% |
| 2022 winners | 17 | 5 | **29.4%** |
| 2023 losers | 15 | 15 | 100% |
| 2024 winners | 13 | 13 | 100% |
| 2024 all | 31 | 31 | 100% |
| 2025 winners | 9 | 9 | 100% |
| 2025 top-5 | 5 | 5 | 100% |
| 2021 all | 153 | 0 | **0.0%** |

### 5.4 Percentile distributions

| Group | n_valid | p25 | Median | p75 | Range |
|-------|--------|-----|--------|-----|-------|
| 2022 all | 19 | -43.51 | -43.05 | -36.97 | [-45.24, -31.44] |
| 2022 losers | 14 | -43.39 | -43.05 | -37.47 | [-45.24, -31.44] |
| 2022 winners | 5 | -43.60 | -38.08 | -38.08 | [-43.60, -35.86] |
| 2023 losers | 15 | -20.74 | -7.07 | -4.49 | [-41.74, 10.10] |
| 2024 winners | 13 | 18.84 | 24.02 | 39.10 | [-7.36, 59.75] |
| 2024 all | 31 | 11.80 | 27.52 | 38.39 | [-7.36, 62.88] |
| 2024 top-5 | 5 | -5.06 | 1.85 | 48.29 | [-7.36, 52.92] |
| 2025 winners | 9 | -24.24 | 42.76 | 50.56 | [-35.14, 57.13] |
| 2025 top-5 | 5 | -26.99 | -24.24 | 46.12 | [-35.14, 50.56] |

### 5.5 Overlap analysis

**Range overlap with 2024 winners' range [-7.36, +59.75]:**

| Group | n_valid | Overlap count | Overlap % |
|-------|--------|--------------|-----------|
| 2022 all | 19 | 0 | **0.0%** |
| 2022 losers | 14 | 0 | 0.0% |
| 2022 winners | 5 | 0 | 0.0% |
| 2023 losers | 15 | 8 | **53.3%** |
| 2024 all | 31 | 29 | 93.5% |
| 2025 winners | 9 | 6 | **66.7%** |
| 2025 top-5 | 5 | 2 | **40.0%** |

The 0% overlap is confirmed: all 19 available 2022 positions fall below the minimum 2024 winner value (-7.36). The separation is real for the available sample.

### 5.6 Warmup caveat

However, only 19 of 94 (20.2%) 2022 positions have valid 3D EMA200 values. These 19 positions are from approximately August 2022 onward — the later portion of the bear market. The 75 positions without values (79.8%) are from the earlier bear phase (January-July 2022), which includes the most severe drawdown periods.

The missing 79.8% of 2022 positions cannot be used for or against the 0% overlap claim. The claim is true for the available 19 positions, but the sample represents only 20% of the year.

### 5.7 Is the separation robust to 2022 winners vs all?

**Yes, within the available sample.** All 5 available 2022 winners have d3_dist_ema200_pct in [-43.60, -35.86], fully below the 2024 winner range. All 14 available losers are in [-45.24, -31.44], also fully below. The separation holds for both winners and losers.

### 5.8 Does 2025 support or weaken the separation?

**Weakens it.** 2025 winners (n=9) have d3_dist_ema200_pct median +42.76, within the 2024 winner range. But 2025 top-5 (n=5) have median -24.24, well below the 2024 winner range. Two of the top 5 trades enter at 3D distances below -24%, in hostile territory by H5.

2025 shows that CPM-1 can produce wins across a wide range of 3D macro contexts (from -35.14 to +57.13). The 0% overlap is specific to 2022-vs-2024; it does not generalize to "all favorable entries are above 3D EMA200."

### 5.9 Does 2023 sit closer to 2022 or 2024?

**Closer to 2024, but overlapping both.** 2023 losers have d3_dist_ema200_pct median -7.07, range [-41.74, +10.10]. This range spans from deeply hostile (2022 territory) to slightly above zero (2024 territory). 53.3% of 2023 losers fall within the 2024 winner range.

2023 is not cleanly hostile by 3D EMA200 — it has heterogeneous macro context. This is another reason H5 does not explain 2023.

### 5.10 3D EMA200 separation classification

**`CAVEATED_BY_WARMUP_OR_SAMPLE`**

Rationale:
1. The 0% overlap between 2022 and 2024 winners is confirmed for the available 19 positions.
2. However, the available 19 positions represent only 20.2% of 2022 entries.
3. The 79.8% missing positions include the deepest bear-market phase and may or may not share the same extreme negative values.
4. 1D features (d1_dist_ema200_pct, d1_ema50_above_ema200) provide the same directional information with 100% coverage and are more reliable as primary evidence.
5. The 3D EMA200 finding is an amplification of the 1D finding, not independent evidence.
6. 2025 top-5 winners enter in hostile 3D macro context, further weakening any gate potential.

The 3D EMA200 separation should not be used as primary evidence for H5. It should be cited as supporting evidence caveated by warmup limitations, with 1D features as the primary evidence base.

---

## 6. 2021 Moderate-ATR Loss Review

### 6.1 Context

60 of 126 2021 losers (47.6%) occurred at ATR percentile <= 60%. These are the "unexplained" 2021 losses that the ATR gate (CPM-MOD-002) cannot address.

### 6.2 Macro feature distributions

| Feature | 2021 Mod-ATR Losers (n=60) | 2024 Winners (n=13) | 2025 Winners (n=9) |
|---------|--------------------------|--------------------|--------------------|
| d1_dist_ema200_pct | +38.18 (n=24) | +15.01 | +26.34 |
| d1_price_above_ema200 | 100% (n=24) | 76.9% | 66.7% |
| d1_ema50_above_ema200 | 100% (n=24) | 76.9% | 66.7% |
| d1_ema50_slope_20d | +8.52 (n=52) | +0.25 | +1.96 |
| d1_ema200_slope_20d | +8.72 (n=22) | +2.87 | +5.85 |
| d1_ret_30d | +12.16% | +3.20% | -0.79% |
| d3_dist_ema50_pct | +23.62 (n=32) | +11.22 | +18.80 |
| d3_ema50_slope_20 | +21.61 (n=22) | +11.11 | +16.10 |
| d3_ret_30bars | +35.29% (n=44) | +16.34% | +79.35% |

### 6.3 Are 2021 moderate-ATR losers macro-overextended?

**Yes, on multiple dimensions.** Compared to 2024 winners:

- Price is 38.18% above 1D EMA200 vs 15.01% (23.17 pp higher)
- 30-day return is +12.16% vs +3.20% (8.96 pp higher)
- EMA50 slope is +8.52% per 20 days vs +0.25% (8.27 pp steeper)
- 3D EMA50 slope is +21.61 vs +11.11 (10.50 pp steeper)
- 3D 90-day return is +35.29% vs +16.34% (18.95 pp higher)

The extension is visible on both 1D and 3D features, covering distance, slope, and return dimensions.

### 6.4 Is this "late bullish extension mean-reversion"?

**Plausibly, yes.** 2021 moderate-ATR losers enter:
- 100% above 1D EMA200 (bullish context — correct direction for LONG)
- 100% with golden cross (bullish structure — correct)
- But at extreme distance: 38% above EMA200 (vs 15% for 2024 winners)
- With aggressive momentum: +12% 30-day return, +8.5% EMA50 slope

The macro trend is bullish (correct direction for CPM-1) but severely stretched. CPM-1 enters on pullback signals, expecting continuation of the bullish trend. But the trend is so extended that pullbacks become mean-reversion events, not continuation discounts. The pullback-continuation mechanism fails when the underlying trend has run too far.

### 6.5 Is this the "upper-extension hostile state"?

**Partially supported.** The upper-extension hostile state is the mirror image of the 2022 bearish hostile state:

| Dimension | 2022 hostile | 2021 mod-ATR hostile |
|-----------|-------------|---------------------|
| Direction | Bearish (below EMA200) | Bullish (38% above EMA200) |
| Cross state | Death cross | Golden cross |
| Slopes | Strongly negative | Strongly positive |
| Distance | -17% from EMA200 | +38% from EMA200 |
| Return | Negative 90d return | +35% 90d return |
| Mechanism | Macro selling absorbs momentum | Mean-reversion overcomes continuation |

Both produce CPM-1 LONG failure but through different mechanisms. This is conceptually compelling: CPM-1 requires a "Goldilocks" macro context — neither too bearish nor too extended.

### 6.6 Important caveat

The 2021 moderate-ATR overextension finding is based on only 24 of 60 positions with valid 1D EMA200 data (40%). The remaining 36 positions (earlier 2021) lack 1D EMA200 values. For 3D features, coverage is better: 32/60 for 3D EMA50, 44/60 for 3D returns.

The finding is directionally supported by 3D features with higher coverage, so it is not solely dependent on the 1D EMA200 subset. But the limited 1D coverage means that specific 1D EMA200 comparisons (38% above, 100% above) apply to the later-2021 subset only.

### 6.7 Classification

The 2021 moderate-ATR loss macro overextension is **PARTIALLY_EXPLAINED**. Evidence:
- Multiple macro features show consistent overextension across 1D and 3D
- The mechanism (mean-reversion in extended trend) is theoretically coherent
- But: limited 1D coverage (40%), post-hoc observation, and not pre-registered
- The finding supports H5's "two hostile states" framework but does not validate it independently

---

## 7. H5 Contradiction Review

### 7.1 Required checks

| # | Contradiction | Evidence | Severity | Interpretation |
|---|--------------|----------|----------|---------------|
| C1 | 2024 top-5 winners in hostile macro context | d1_dist_ema200_pct = -8.43, 40% above EMA200, death cross for 60%, EMA200 slope = -2.41 | **SEVERE** | The 5 best 2024 trades enter near/below daily EMA200 in a hostile macro regime. H5 would filter these out. |
| C2 | 2025 top-5 winners in hostile macro context | d1_dist_ema200_pct = -19.36, 40% above EMA200, death cross for 60%, EMA200 slope = -5.44 | **SEVERE** | The 5 best 2025 trades enter at 19% below EMA200 in a 2022-like hostile regime. Identical pattern to C1. |
| C3 | 2023 in non-hostile macro context but loses | d1_dist_ema200_pct = +10.66, 73.3% above EMA200, 60% golden cross, EMA200 slope = +1.49 | **SEVERE** | 2023 entries are in a non-hostile macro context. 83.3% lose. H5 cannot explain 2023 at all. |
| C4 | 2025 winners heterogeneous across macro states | 2025 winners range: d1_dist_ema200_pct from -32.89 to +42.74 | **MODERATE** | CPM-1 wins in both hostile and non-hostile 2025 macro states. The macro context is not necessary for success. |
| C5 | 2022 winners do not escape hostile regime | 0% golden cross, 88% below EMA200 | **LOW** (not a contradiction) | Winners succeed through rare calm microstates, not macro escape. This is consistent with H5 being a cross-year separator, not a within-year filter. |
| C6 | 3D EMA200 0% overlap is warmup-limited | Only 19 of 94 (20.2%) 2022 positions have valid values | **MODERATE** | The headline separation is real for the available sample but covers only 20% of 2022 entries. |

### 7.2 Contradiction severity summary

- **SEVERE**: 3 contradictions (C1, C2, C3)
- **MODERATE**: 2 contradictions (C4, C6)
- **LOW**: 1 non-contradiction (C5)

The most damaging contradictions are:
1. The best trades in both 2024 and 2025 enter in hostile macro context (C1, C2)
2. 2023 has non-hostile context but fails anyway (C3)

### 7.3 What C1 and C2 mean

The 2024 and 2025 top-5 winners occurring in hostile macro states means that any macro-based gate would filter out some of CPM-1's most profitable trades. This is a fundamental tension:

- Macro context separates 2022 (hostile, bad) from 2024 all-winners (non-hostile, good) on average.
- But the best individual trades within favorable years occur in hostile macro states.
- A macro gate trades expected-value improvement for asymmetric-loss truncation.

This does not invalidate H5 as an attribution finding, but it substantially limits H5's potential as a gate.

### 7.4 What C3 means

2023 is the unresolvable contradiction for H5. 2023 entries have:
- 73.3% above 1D EMA200 (favorable)
- 60% golden cross (favorable)
- EMA200 slope +1.49 (slightly positive)
- 3D EMA50 slope +4.50 (positive)

If H5 were a complete boundary, 2023 should be a favorable year. It is not. The dominant failure dimension (continuation, MFE magnitude 401.9) is invisible to macro features.

This confirms: H5 addresses the macro-directional failure mode but not the continuation-environment failure mode. These are different failure dimensions.

---

## 8. SRR-002 Risk Review

### 8.1 H5 against SRR-002 criteria

| SRR-002 Criterion | Assessment | Risk Level |
|-------------------|-----------|-----------|
| **Pre-observable** | All H5 features (1D EMA distance, slope, cross-state, returns; 3D EMA distance, slope, returns) are computable from closed OHLCV before entry. | **PASS** |
| **Not post-hoc selected** | H5 was formulated after examining 2022 data during the choppiness closeout. It was motivated by the 2022 ATR-paradox observation (identical ATR to 2024 but loses). The specific features (1D/3D EMA200 distance, cross-state, slopes) were chosen after seeing which features separated 2022 from 2024. Post-hoc fitting penalty applies. | **FAIL** (post-hoc penalty) |
| **Explains valid and invalid states** | H5 explains 2022 invalid (bearish macro) and 2024 valid (bullish macro). It also partially explains 2021 moderate-ATR invalid (overextension). But it does not explain 2023 invalid (non-hostile context but fails). Both partitions are non-empty, but the invalid partition has an unresolved region. | **PARTIAL** |
| **Risk of no-trade gate fitted to 2022** | **HIGH**. H5 is derived from the 2022 failure. Any macro threshold (what distance to EMA200 is "hostile"?) would be chosen from the 2022 data. This is classic no-trade gate fitting. | **HIGH RISK** |
| **Independent theoretical motivation** | **PARTIAL**. "LONG-only pullback continuation requires non-hostile macro trend" is conceptually sound and has literature support (trend-following strategies need trend alignment across timeframes). But the specific feature choices (1D/3D EMA200 distance, cross-state) were selected post-hoc. | **PARTIAL** |
| **Requires new empirical evidence** | **YES**. H5 cannot be validated without at least one additional hostile-macro year in the dataset. Currently, only 2022 represents the bearish hostile state. | **YES** |
| **Avoids runtime interpretation** | H5 is defined as a module-level no-trade filter, not a runtime score. | **PASS** |

### 8.2 Is H5 pre-observable?

**Yes.** All features are computable from closed OHLCV bars before the entry decision. This is the strongest SRR-002 property of H5.

### 8.3 Is H5 post-hoc?

**Yes, with moderate penalty.** H5 was formulated during the choppiness closeout after examining the 2022 macro data. The specific observation (2022 entries are 86% below EMA200, 98% death-cross) was made after computing features for existing positions. The hypothesis that "LONG-only strategies need non-hostile macro context" has independent theoretical motivation, but the specific feature selection is post-hoc.

Under SRR-002 Section 2.2, H5 carries a post-hoc fitting penalty: the boundary must be tested on at least one period not used in its formulation. Currently, only 2022 was used to formulate H5. No independent validation period exists.

### 8.4 Does H5 risk becoming a no-trade filter fitted to 2022?

**Yes, this is the primary risk.** If a macro threshold is derived from the 2022/2024 separation (e.g., "block trades when price is >X% below 1D EMA200"), the threshold would be fitted to explain 2022 specifically. This would be a textbook no-trade gate: designed to skip the losing year.

The 2021 overextension finding partially mitigates this by showing H5 addresses a second failure mode with the same framework. But the 2021 finding is also post-hoc.

### 8.5 Does H5 have independent theoretical motivation?

**Partially.** The general principle — that trend-following strategies require trend alignment across timeframes — is well-established. A LONG-only pullback-continuation strategy should work better when the daily trend is also bullish. This is not controversial.

However, the specific claim — that 1D/3D EMA200 distance and cross-state are the right macro features — was derived from the data. Other macro features (e.g., 1D EMA50 distance, 3D close-to-close returns, or price vs VWAP) were not tested. The feature selection is empirical, not theoretically predetermined.

### 8.6 Does H5 require new empirical evidence?

**Yes.** H5 was formulated on the 2022 data. It cannot be validated on the 2022 data alone (SRR-002 post-hoc penalty). It needs at least one additional hostile-macro period to serve as validation. No such period exists in the current 2021-2025 dataset (2021 has bullish overextension but no bearish regime other than 2022).

### 8.7 Does H5 avoid runtime/small-live interpretation?

**Yes.** H5 is defined as a module-level no-trade filter. When the macro context is hostile, CPM-1 is disabled. When non-hostile, CPM-1 operates under its frozen rules. No runtime scoring, no dynamic parameter adjustment.

---

## 9. H5 Final Classification

### 9.1 Evidence inventory

**Supporting H5:**
1. 2022 entries are 86.2% below 1D EMA200, 97.9% death-cross — consistent hostile macro regime
2. 2022 vs 2024 separation spans multiple features across both 1D and 3D timeframes
3. 3D dist_ema200_pct shows 0% overlap between 2022 and 2024 winners (caveated by warmup)
4. Macro context explains the ATR paradox (identical ATR percentile but different outcomes)
5. 2021 moderate-ATR losers show consistent macro overextension (partial, post-hoc)
6. The mechanism is theoretically coherent (LONG-only needs non-hostile macro direction)
7. All features are pre-observable

**Weakening H5:**
1. Derived from one year only (2022) — no out-of-sample validation
2. 2024 top-5 winners enter in hostile macro context (-8.43% below EMA200, 60% death cross)
3. 2025 top-5 winners enter in hostile macro context (-19.36% below EMA200, 60% death cross)
4. 2023 has non-hostile context but 83.3% of positions lose — H5 cannot explain this
5. 3D EMA200 "0% overlap" is based on only 20.2% of 2022 positions
6. 2021 EMA200-based findings are based on 36.6% of positions (limited warmup)
7. 2022 winners do not escape hostile macro context — they succeed through calm microstates, not macro alignment
8. Post-hoc fitting penalty applies under SRR-002
9. Any macro threshold would be fitted to the 2022 data
10. H5 does not explain the dominant failure mode (2023 continuation failure)

### 9.2 Classification

**`H5_PARTIAL_BUT_INCOMPLETE`**

Rationale:
- H5 has clear theoretical motivation and multi-dimensional empirical support for 2022
- It partially explains 2021 moderate-ATR losses (macro overextension)
- All features are pre-observable
- But: derived from one year, post-hoc penalty applies, 3D EMA200 evidence is caveated by warmup
- The most damaging contradictions (2024 top-5, 2025 top-5, 2023) show H5 is not a sufficient boundary
- H5 addresses the macro-directional failure mode but not the continuation-environment failure mode
- No out-of-sample validation is possible without a second hostile-macro year
- H5 is the strongest individual hypothesis axis in the CPM-1 boundary research, but it is incomplete

This classification is one step above the closeout's `PLAUSIBLE_FOR_FUTURE_INSPECT` because the robustness review confirms multi-dimensional separation and coherent mechanism, but it is not upgraded to `STRONG_ATTRIBUTION` because the contradictions are severe and the warmup limitations are significant.

### 9.3 What H5 is and is not

**H5 is**: A robust partial attribution axis for 2022 macro-directional failure and 2021 overextension. It identifies a coherent mechanism (LONG-only strategy needs non-hostile macro trend) supported by multi-dimensional pre-observable features.

**H5 is not**: A complete CPM-1 boundary, a validated gate, a frozen diagnostic candidate, or an explanation for 2023 continuation failure.

---

## 10. Overall CPM Implication

### 10.1 Attribution progress after H5 robustness review

| Failure mode | Attribution status | Primary explanation | Classification |
|-------------|-------------------|-------------------|----------------|
| 2021 high-volatility | Addressed | ATR percentile > 60% | CPM-MOD-002 (frozen) |
| 2021 moderate-volatility | Partially explained | Macro overextension | H5 partial (post-hoc, warmup-limited) |
| 2022 low-vol LONG failure | Partially explained | Macro-directional hostile | H5 partial (one year, warmup-limited) |
| 2023 continuation failure | Unexplained | None found | Invisible under OHLCV features |
| 2024 favorable | Confirmed | Low ATR + non-hostile macro | Reference year |
| 2025 fragile favorable | Confirmed | Heterogeneous macro, structural fragility | Structural |

### 10.2 What H5 robustness adds to the closeout

The robustness review confirms:
1. H5's 2022 separation is multi-dimensional (not a single-feature artifact)
2. The 1D features provide reliable primary evidence (no warmup caveat)
3. The 3D EMA200 "0% overlap" is real but caveated by 20.2% sample coverage
4. The mechanism is coherent and partially supported for 2021
5. The contradictions are severe (top-5 trades in hostile context, 2023 unexplained)

The robustness review does NOT change:
1. H5 does not explain 2023
2. H5 is post-hoc
3. No threshold can be justified without fitting
4. No out-of-sample validation exists

### 10.3 Overall CPM boundary research classification

**`CPM_BOUNDARY_RESEARCH_HAS_ONE_ROBUST_PARTIAL_AXIS`**

Rationale:
- H5 is the first hypothesis with multi-dimensional, pre-observable, theory-backed evidence for a specific failure mode (2022 macro-directional)
- It has a coherent mechanism that partially extends to 2021
- But: it is partial (one year, post-hoc), incomplete (does not explain 2023), and the contradictions are severe
- The 2023 continuation failure remains the dominant unresolved problem
- The overall CPM boundary research remains incomplete because the most damaging failure mode (2023) has no pre-observable explanation
- H5 is a robust partial axis; it is not a complete boundary

---

## 11. Recommendation

### 11.1 Decision: D or E

**D — Continue attribution only**, with **E — Owner decision required** as the fallback if D cannot produce further information gain.

### 11.2 Evaluation of all options

**A (Stop CPM line here)**: Not warranted. H5 provides genuine multi-dimensional attribution for 2022. Stopping would discard the first theory-backed partial axis without exploring its limits.

**B (Preserve CPM only; no next task)**: Close to D. The difference is whether a further docs-only attribution cycle is justified. H5 is strong enough to warrant one more investigation if it can be designed with clear information gain.

**C (Proceed to frozen diagnostic plan)**: **Not justified**, even though H5 is the strongest hypothesis axis. Reasons:
1. H5 is post-hoc (formulated on 2022 data). Under SRR-002, a post-hoc boundary must be validated on a period not used in its formulation. No such period exists.
2. H5 does not explain 2023 (the dominant failure mode). A frozen diagnostic for H5 would test a partial boundary that leaves the most damaging failure untouched.
3. Any macro threshold would be fitted to the 2022/2024 gap. This is no-trade gate fitting.
4. The 2024 and 2025 top-5 contradictions mean any macro gate would filter some of CPM-1's best trades.
5. The 3D EMA200 evidence is warmup-limited (20.2% of 2022).
6. Recommendation C requires "clear information gain without threshold optimization." H5's information gain is limited because: if the diagnostic passes, it only confirms what we already know (2022 was hostile); if it fails, the post-hoc penalty prevents closing the hypothesis cleanly.

**D (Continue attribution only)**: **Recommended.** The next attribution cycle should focus on:
1. Whether H5's 1D macro features have information gain independent of the existing ATR gate (cross-feature analysis)
2. Whether any earlier hostile-macro period can be identified in the pre-2021 data (if available)
3. Whether H5's "two hostile states" framework can be tested against a forward-looking dataset (future entries)
4. Whether the 2023 continuation failure has any macro-detectable signature that the current features miss

This remains docs-only attribution. No empirical work is authorized.

**E (Owner decision required)**: A valid alternative if the Owner determines that further OHLCV-only attribution has reached diminishing returns. At this point, the three failure modes are:
- 2021 high-volatility: addressed (CPM-MOD-002)
- 2022 macro-directional: partially explained (H5)
- 2023 continuation: unexplained and possibly unexplainable under OHLCV

If the Owner judges that OHLCV-only attribution cannot resolve 2023, then E may be more appropriate than D. This is an Owner judgment call, not a research determination.

### 11.3 What should NOT be done next

- Do not create a macro gate from the 2022/2024 separation — this is post-hoc fitting
- Do not combine H5 with ATR gate to create a composite — this violates SRR-002
- Do not proceed to CPM-MOD-003 — no frozen hypothesis supports it
- Do not use 3D EMA200 as primary evidence — warmup limitations make it unreliable for 2021 and early 2022
- Do not interpret H5 as a complete boundary — it does not explain 2023
- Do not authorize runtime, small-live, or strategy rescue

---

## 12. Explicit Prohibitions

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

## 13. Owner Summary

### What is H5?

H5-MACRO-LONG-BIAS-CONTEXT is the hypothesis that CPM-1 LONG-only pullback continuation requires a non-hostile 1D/3D macro trend context. It posits two hostile states: bearish macro regime (2022 type) and bullish overextension (2021 type).

### Is H5 robust?

Partially. The 2022 separation is multi-dimensional and consistent across 1D features (distance to EMA200, cross-state, slopes). The mechanism is theoretically coherent. But: derived from one year, post-hoc, 3D EMA200 evidence is warmup-limited, and the contradictions are severe (2024/2025 top-5 trades enter in hostile macro context).

### What are the key contradictions?

1. The 5 best 2024 trades enter at -8.43% below EMA200 with 60% death cross — hostile by H5
2. The 5 best 2025 trades enter at -19.36% below EMA200 with 60% death cross — hostile by H5
3. 2023 has non-hostile macro context (73.3% above EMA200) but 83.3% of positions lose

These contradictions mean H5 cannot serve as a gate without filtering some of CPM-1's best trades.

### What does the warmup audit show?

1D features are reliable for 2022+ (100% coverage). 3D EMA200 is unavailable for all 2021 positions and 79.8% of 2022 positions. The "0% overlap" on 3D distance to EMA200 is confirmed for the available 19 positions (20.2% of 2022), but the missing 79.8% include the deepest bear-market phase. 1D features should be used as primary evidence.

### Does H5 explain all CPM-1 failures?

No. H5 addresses 2022 (bearish hostile) and partially addresses 2021 moderate-ATR (overextension). It does not explain 2023 continuation failure. This makes H5 a partial boundary at best.

### What is H5's classification?

`H5_PARTIAL_BUT_INCOMPLETE`. It is the strongest individual hypothesis axis in the CPM-1 boundary research but is incomplete and contradicted by top-5 trades in both favorable years.

### What is the overall CPM implication?

`CPM_BOUNDARY_RESEARCH_HAS_ONE_ROBUST_PARTIAL_AXIS`. H5 is a genuine partial axis with multi-dimensional, pre-observable, theory-backed evidence. But CPM boundary research remains incomplete because 2023 is unresolved.

### What is the recommendation?

**D — Continue attribution only** (primary) or **E — Owner decision required** (fallback). C (frozen diagnostic) is not justified because H5 is post-hoc, does not explain 2023, and any threshold would be fitted to the 2022 data.

### Why is CPM-1 still not runtime/small-live?

- No validated complete applicability boundary exists
- H5 is partial and incomplete (does not explain 2023)
- 2023 continuation failure has no pre-observable explanation
- The best trades in 2024 and 2025 occur in hostile macro context by H5
- SRR-002 Level 3 admission gate has 10 requirements; CPM-1 satisfies none
- Any empirical work requires separate Owner authorization

---

> CPM-1 remains non-runtime and non-small-live. This H5 macro-context robustness attribution does not authorize CPM-1 changes, gates, empirical diagnostics, runtime use, or strategy rescue. Any future empirical work requires separate Owner approval and must satisfy SRR-002.
