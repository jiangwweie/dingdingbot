# CPM-1 Applicability Boundary Hypothesis Inspect

**Task ID**: CPM-1-APPLICABILITY-BOUNDARY-HYPOTHESIS-INSPECT
**Date**: 2026-05-08
**Status**: Completed / docs-only hypothesis inspect
**Classification**: BOUNDARY_HYPOTHESIS_PARTIAL_NEEDS_ATTRIBUTION

---

## 0. Boundary

This is a docs-only applicability-boundary hypothesis inspect for CPM-1.

It is not:
- A gate proposal or gate definition
- A backtest or empirical run
- A parameter sweep or strategy rescue
- CPM-MOD-003 or E4 experiment
- Runtime or small-live authorization
- A decision to proceed with any empirical work

It formulates candidate boundary hypotheses and defines what would need to be frozen before any future empirical diagnostic. It does not choose final thresholds or authorize execution.

---

## 1. CPM-1 Current Evidence State

**Identity**: CPM-1 is an ETH/USDT:USDT perpetual LONG-only pullback-continuation module. Entry trigger: 1h Pinbar (min_wick_ratio=0.6). Trend filter: 1h EMA50. MTF confirmation: 4h EMA60. Exit: TP1 1.0R 50%, TP2 3.5R 50%, SL -1.0R.

**Evidence summary**:

| Year | Positions | Winners | Win Rate | Total PnL | Evidence Quality |
|------|-----------|---------|----------|-----------|-----------------|
| 2021 baseline | 79 | 15 | 19.0% | -1,765 | Hostile: high-volatility bull-year failure |
| 2021 OOS | 74 | 12 | 16.2% | -1,939 | Hostile: confirms baseline failure |
| 2022 baseline | 43 | 8 | 18.6% | -764 | Hostile: cost/bear-year failure |
| 2022 OOS | 51 | 17 | 33.3% | -972 | Hostile: cost-dominated |
| 2023 baseline | 18 | 3 | 16.7% | -785 | Hostile: continuation failure, unresolved boundary |
| 2024 baseline | 31 | 13 | 41.9% | +969 | Favorable: strongest evidence year |
| 2025 baseline | 33 | 9 | 27.3% | +322 | Favorable but structurally fragile |

**Classification**: `CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT`. Not runtime. Not small-live.

**Maximum common blocker** (from SRR-002): No module has a validated, pre-observable applicability boundary.

---

## 2. Pre-entry Features vs Post-entry Labels

### 2.1 Pre-observable features

These are computable from OHLCV data available at or before the entry decision point.

| Feature | Definition | 2024 Winners Median | 2023 Losers Median | 2021 Losers Median |
|---------|-----------|--------------------|--------------------|--------------------|
| h1_atr14_pct90d | 1h ATR14 rolling percentile (90d) | 25.6% | 43.4% | 61.5% |
| h4_atr14_pct90d | 4h ATR14 rolling percentile (90d) | 31.1% | 34.9% | 59.8% |
| h1_bar_range_pct90d | 1h bar range percentile (90d) | 24.5% | 50.5% | 48.6% |
| h1_ema50_slope_20 | 1h EMA50 slope over 20 bars | 0.96 | 0.98 | 3.11 |
| h4_ema60_slope_20 | 4h EMA60 slope over 20 bars | 0.40 | 1.19 | 3.47 |
| h1_close_dist_ema50_pct | Entry distance to 1h EMA50 (%) | 1.37% | 1.52% | 3.06% |
| h4_close_dist_ema60_pct | Entry distance to 4h EMA60 (%) | 2.15% | 3.00% | 8.11% |
| h1_pullback_depth_pct | Pullback depth from 20-bar high (%) | 0.73% | 0.98% | 1.61% |
| h4_dc20_normalized | Donchian20 normalized position | 0.77 | 0.76 | 0.82 |
| loc_1h_norm_position_20bar | Normalized position in 1h 20-bar range | 0.73 | 0.62 | 0.74 |
| h1_ret_7d | 1h return over prior 7 days (%) | 4.96% | 4.81% | 10.87% |
| h4_ret_18bars | 4h return over prior 18 bars (%) | 1.55% | 3.14% | 7.06% |
| h1_rv_72h | 1h realized volatility (72h) | 0.0047 | 0.0034 | 0.0088 |

### 2.2 Post-entry diagnostic labels

These are computable only after the position has been closed. They diagnose failure type but **cannot be used directly as pre-observable boundary inputs**.

| Label | Definition | 2024 Winners Median | 2023 Losers Median | 2021 Losers Median |
|-------|-----------|--------------------|--------------------|--------------------|
| mfe | Maximum favorable excursion | 406.17 | 4.26 | 9.86 |
| mae | Maximum adverse excursion | -56.37 | -23.10 | -45.84 |
| giveback | MFE - realized_pnl | 318.24 | 91.54 | 87.62 |
| bars_to_mfe | Bars to reach MFE | 207 | 2 | 0 |
| bars_to_mae | Bars to reach MAE | 326 | 8 | 1 |

**Critical distinction**: The largest numerical separation between 2024 winners and hostile-year losers is in post-entry labels (MFE, bars-to-MFE), not pre-entry features. The dominant failure dimension for 2023 is continuation (magnitude 401.9), which is post-entry. This means the most visible difference is not directly usable as a boundary input.

---

## 3. Candidate Boundary Hypotheses

### H1: Low-to-moderate volatility continuation state

**Name**: H1-VOL-CONTINUATION

**Intuition**: CPM-1 works when entry volatility is low-to-moderate. High-volatility entries produce immediate reversals (2021 pattern), and moderate-volatility entries in choppy/bar-range-elevated states produce weak continuation (2023 pattern).

**Supporting evidence**:

- 2024 winners h1 ATR percentile median: 25.6% vs 2021 losers: 61.5% (58% relative difference)
- 2024 winners h4 ATR percentile median: 31.1% vs 2021 losers: 59.8% (48% relative difference)
- CPM-MOD-002 ATR > 60% gate improves 2021 by +933 while preserving 2024/2025
- 2024 winners h1 bar range percentile: 24.5% vs 2023 losers: 50.5% (51% relative difference)
- 2024 winners h1 bar range percentile: 24.5% vs 2021 losers: 48.6% (50% relative difference)
- Bar range percentile separates 2024 winners from both 2023 and 2021 losers
- ATR percentile and bar range percentile are correlated but not identical; bar range captures choppiness that ATR may not

**Contradicting evidence**:

- 2023 losers have moderate ATR percentile (median 43.4%) — not high by 2021 standards
- 47% of 2021 losers have ATR <= 60%, so volatility alone does not explain all 2021 losses
- 2025 winners enter at ATR percentile 47.2% — higher than 2023 losers' 43.4%, yet 2025 wins
- The ATR percentile distributions overlap: 2024 winners p75 = 52.0%, 2023 losers p25 = 31.1%
- 2022 has similar ATR percentile to 2024 (median 25.7%) but is a losing year

**Pre-observable**: Yes. ATR percentile and bar range percentile are computable from closed OHLCV before entry.

**Post-hoc fitting risk**: MODERATE. The ATR > 60% threshold was pre-registered in CPM-MOD-002 and tested frozen. However, extending to bar range percentile or adjusting the threshold below 60% would be post-hoc. The observation that bar range percentile separates 2023 from 2024 was made after examining extracted features.

**What it explains**:
- 2021 high-volatility losses (via ATR percentile)
- 2023 continuation failure partially (via bar range percentile / choppiness)
- Why 2024/2025 are preserved (low-to-moderate entry volatility)

**What it fails to explain**:
- 2022 failure (similar ATR percentile to 2024 but loses)
- 47% of 2021 losses at moderate ATR
- Why 2025 wins at ATR percentile 47% while 2023 loses at 43%
- The non-volatility hostile states in 2021

**What would need to be frozen before any future empirical diagnostic**:
- Exact feature: h1_atr14_pct90d (primary), h1_bar_range_pct90d (secondary)
- Exact threshold selection policy: pre-registered before execution, not optimized from results
- Timestamp policy: evaluated at signal bar close, before signal-to-order
- Valid state: ATR percentile below threshold AND bar range percentile below threshold
- Invalid state: either above its threshold
- No-trade semantics: module disabled, existing positions continue
- Cost model: frozen CPM-1 baseline cost model
- Reporting metrics: net PnL, trade count, winner count, PF, MaxDD, fragility
- Failure closure: if diagnostic fails, no threshold adjustment, no composite score, no parameter rescue
- No variants if failed

---

### H2: Gentle continuation / low-bar-range state

**Name**: H2-LOW-BAR-RANGE

**Intuition**: CPM-1 works when pullback signals occur in lower bar-range / smoother continuation states. High bar-range percentile indicates choppier price action that disrupts pullback continuation even when ATR is moderate.

**Supporting evidence**:

- 2024 winners h1 bar range percentile: 24.5% vs 2023 losers: 50.5% — the largest pre-observable separation between 2024 winners and 2023 losers
- 2024 winners h1 bar range percentile: 24.5% vs 2021 losers: 48.6% — also separates from 2021
- 2023 has moderate ATR but elevated bar range percentile, explaining why ATR gate misses 2023
- Bar range percentile captures intrabar choppiness that ATR (an average) may smooth over
- 2024 winners p75 for bar range percentile is 41.8%; 2023 losers p25 is 22.5% — significant but overlapping

**Contradicting evidence**:

- 2025 winners have bar range percentile 41.2% — close to 2023 losers' 50.5%, yet 2025 wins
- 2022 has bar range percentile 28.9% — close to 2024, yet 2022 loses
- The overlap between 2024 winners and 2023 losers is substantial (2024 p75 41.8% vs 2023 p25 22.5%)
- Choosing a threshold from the 2024/2023 gap would be post-hoc
- Bar range percentile alone does not explain 2022 failure

**Pre-observable**: Yes. Bar range percentile is computable from closed OHLCV before entry.

**Post-hoc fitting risk**: HIGH. The observation that bar range percentile separates 2023 from 2024 was made during this inspect, after examining extracted features. No prior hypothesis predicted this specific feature. Any threshold chosen from the 2024/2023 gap would be fitted to the data.

**What it explains**:
- 2023 continuation failure better than ATR alone
- Partial explanation of 2021 (bar range also elevated)

**What it fails to explain**:
- 2022 failure (low bar range but loses)
- Why 2025 wins at elevated bar range
- The overlap between favorable and hostile distributions

**What would need to be frozen before any future empirical diagnostic**:
- Exact feature: h1_bar_range_pct90d
- Exact threshold: pre-registered, not chosen from 2024/2023 gap
- All other freeze requirements same as H1

---

### H3: Trend-strength plus pullback-quality composite state

**Name**: H3-TREND-PULLBACK-COMPOSITE

**Intuition**: CPM-1 may require a joint state: trend exists but is not overextended, pullback is shallow/moderate, price is not too close to recent high, and volatility is not hostile. No single feature explains all failures; a composite may.

**Supporting evidence**:

- 2021 losers have higher EMA slope (1h: 3.11 vs 0.96; 4h: 3.47 vs 0.40) — overextended trends
- 2021 losers have deeper pullbacks (1.61% vs 0.73%) — entering from deeper retracements in volatile trends
- 2021 losers have larger distance to 4h EMA60 (8.11% vs 2.15%) — price far above trend
- 2023 losers have slightly deeper pullbacks than 2024 winners (0.98% vs 0.73%)
- 2022 losers have deep pullbacks (1.64%) and large 4h EMA60 distance (5.98%)
- No single feature explains all failures; the hostile states differ across years

**Contradicting evidence**:

- 2023 losers have similar EMA slope to 2024 winners (1h: 0.98 vs 0.96; 4h: 1.19 vs 0.40) — trend slope does not separate 2023 from 2024
- 2023 losers have similar Donchian position to 2024 winners (0.76 vs 0.77) — price location does not separate 2023 from 2024
- Composite state risks overfitting: with 13+ pre-entry features, many composite combinations could be constructed post-hoc
- SRR-002 Section 5 requires that conditional module evidence avoid post-hoc no-trade gate prevention
- SRR-002 Section 2 imposes post-hoc fitting penalty rules

**Pre-observable**: Yes, if the composite is defined from pre-observable features only.

**Post-hoc fitting risk**: VERY HIGH. Constructing a composite from multiple features after examining which features separate favorable from hostile years is textbook post-hoc fitting. The composite would be designed to explain known failures, not predict unknown ones.

**What it explains**:
- Potentially all failure modes if enough features are combined
- 2021 via volatility + trend overextension + deep pullback
- 2023 via bar range + moderate pullback
- 2022 via deep pullback + trend distance

**What it fails to explain**:
- Whether the composite generalizes beyond the observed years
- Whether the composite is anything more than a fitted no-trade score

**What would need to be frozen before any future empirical diagnostic**:
- Exact feature set and weights: pre-registered, not optimized
- Exact composite formula: defined before execution
- All SRR-002 Section 2 boundary validation checklist items (13 checks)
- All SRR-002 Section 5 conditional module evidence requirements
- Post-hoc fitting penalty applied to any threshold chosen from existing data
- Failure closure: if composite fails, no feature addition, no weight adjustment, no variant

---

### H4: 2024-specific long-duration continuation state

**Name**: H4-LONG-DURATION-CONTINUATION

**Intuition**: 2024 winners represent a distinct long-duration continuation regime. CPM-1's favorable evidence may be specific to this regime, and 2025's weaker/fragile evidence may indicate the regime is narrowing.

**Supporting evidence**:

- 2024 winners: MFE 406, bars-to-MFE 207, giveback 318 — long-duration, large excursion
- 2025 winners: MFE 193, bars-to-MFE 37, giveback 27 — shorter, smaller
- 2023 losers: MFE 4.26, bars-to-MFE 2 — near-zero continuation
- 2021 losers: MFE 9.86, bars-to-MFE 0 — immediate reversal
- 2024 top-5 winners have MFE 323, bars-to-MFE 206
- 2025 top-5 winners have MFE 116, bars-to-MFE 53
- 2024 survives top-N removal better than 2025

**Contradicting evidence**:

- MFE, bars-to-MFE, and giveback are **post-entry labels** — not pre-observable
- No pre-entry proxy for "long-duration continuation regime" has been identified
- 2024 winners' pre-entry states are not uniquely different from other years on continuation-relevant features
- This hypothesis labels the outcome but does not predict it

**Pre-observable**: No. The defining features (MFE, bars-to-MFE, giveback) are post-entry.

**Post-hoc fitting risk**: COMPLETE. This hypothesis describes what happened, not what will happen. It cannot be used as a boundary hypothesis because its defining features are not available at entry time.

**What it explains**:
- Why 2024 is stronger than 2025 (longer continuation, larger MFE)
- Why 2023 fails (near-zero continuation)
- Why 2021 fails (immediate reversal)

**What it fails to explain**:
- How to predict continuation before entry
- How to distinguish a future 2024-like state from a 2023-like state at signal time

**What would need to be frozen before any future empirical diagnostic**:
- A pre-observable proxy for continuation potential, if one can be identified
- Without such a proxy, this hypothesis cannot be tested as a boundary

---

## 4. Hypothesis Classification

| Hypothesis | Classification | Rationale |
|------------|---------------|-----------|
| H1-VOL-CONTINUATION | `PLAUSIBLE_FOR_FUTURE_INSPECT` | Pre-observable, partially pre-registered (ATR gate), explains 2021 materially and 2023 partially via bar range. Incomplete but strongest candidate. |
| H2-LOW-BAR-RANGE | `PARTIAL_BUT_INCOMPLETE` | Pre-observable and captures 2023 better than ATR alone, but high post-hoc risk (no prior hypothesis predicted this), and 2025 wins at similar levels to 2023. |
| H3-TREND-PULLBACK-COMPOSITE | `POST_HOC_RISK_HIGH` | Pre-observable in principle but constructing a composite from observed separations is textbook post-hoc fitting. Violates SRR-002 Section 2 and 5. |
| H4-LONG-DURATION-CONTINUATION | `NOT_SUPPORTED` | Not pre-observable. Defines boundary using post-entry labels. Cannot be used as a boundary hypothesis. |

---

## 5. What A Future Diagnostic Would Need To Freeze

Only H1-VOL-CONTINUATION is classified as plausible. If Owner authorizes a future empirical diagnostic for H1, the following must be frozen before execution:

### 5.1 Feature set

Primary: `h1_atr14_pct90d` (1h ATR14 rolling percentile over prior 90 calendar days, 2160-bar window)

Secondary candidate: `h1_bar_range_pct90d` (1h bar range rolling percentile over prior 90 calendar days)

No other features. No composite score. No E4 label.

### 5.2 Threshold selection policy

The ATR percentile threshold must be pre-registered before execution. CPM-MOD-002 already tested 0.60 frozen. Any future test must either:
- Re-use the 0.60 threshold (most conservative, already partially validated), or
- Pre-register a single alternative threshold with justification independent of the 2024/2023 gap

The bar range percentile threshold, if tested, must be pre-registered with justification independent of the extracted feature distributions. **Choosing a threshold from the observed 2024/2023 gap would be post-hoc fitting.**

### 5.3 Timestamp policy

Gate evaluated at the close of the signal bar, before signal-to-order creation. Only closed-bar OHLCV used. No future information.

### 5.4 Valid/invalid state definitions

- Valid state: ATR percentile below threshold (and bar range percentile below its threshold, if secondary gate is included)
- Invalid state: either feature above its threshold
- Warmup: module remains enabled during warmup (insufficient history for percentile computation)

### 5.5 No-trade semantics

When invalid, CPM-1 does not open new positions. Existing open positions continue under the frozen CPM-1 lifecycle. Exits are not changed.

### 5.6 Cost model

Frozen CPM-1 baseline: fee_rate=0.0004, entry slippage=0.001, TP slippage=0.0005, funding enabled at 0.0001 per 8h.

### 5.7 Reporting metrics

Net PnL, trade count, winner count, profit factor, MaxDD (MTM and realized), top-N fragility (top-1/3/5 removal), MFE/MAE/giveback averages.

### 5.8 Failure closure

If the diagnostic fails:
- No threshold adjustment
- No additional feature added
- No composite score constructed
- No parameter rescue
- No E4 label
- No CPM-MOD-003
- The hypothesis is closed and CPM-1 remains at current classification

### 5.9 No variants if failed

A failed H1 diagnostic does not authorize trying H2, H3, or H4 as alternatives. Each would require separate Owner authorization with its own frozen spec.

---

## 6. SRR-002 Compliance Check

### H1-VOL-CONTINUATION

| SRR-002 Requirement | Assessment |
|---------------------|-----------|
| Pre-observable? | Yes. ATR percentile and bar range percentile use only closed OHLCV before entry. |
| Motivated post-hoc? | Partially. ATR gate was pre-registered in CPM-MOD-002. Bar range observation is post-hoc from this inspect. |
| Risk of no-trade gate fitted to losing years? | Moderate. ATR > 60% was pre-registered and frozen. Adding bar range or lowering threshold would increase this risk. |
| Explains both valid and invalid states? | Partially. Explains 2021 invalid and 2024 valid. Does not fully explain 2023 invalid or 2022 invalid. |
| Invalid state non-empty? | Yes. 2021 has 42/79 positions with ATR > 60%. |
| Requires new empirical evidence? | Yes, if bar range percentile is added as a secondary gate. |
| Avoids runtime interpretation? | Yes. Module-level enable/disable, no runtime scoring. |

**SRR-002 compliance**: Partial. The ATR component satisfies pre-observable and was pre-registered. The bar range component is post-hoc and would need its own frozen spec before any empirical test.

### H2-LOW-BAR-RANGE

| SRR-002 Requirement | Assessment |
|---------------------|-----------|
| Pre-observable? | Yes. |
| Motivated post-hoc? | Fully. No prior hypothesis predicted bar range percentile as a CPM-1 boundary feature. |
| Risk of no-trade gate fitted to losing years? | High. Threshold would be chosen from observed 2024/2023 distributions. |
| Explains both valid and invalid states? | Partially. Better for 2023 than ATR, but fails on 2022 and 2025. |
| Invalid state non-empty? | Yes. |
| Requires new empirical evidence? | Yes. |
| Avoids runtime interpretation? | Yes. |

**SRR-002 compliance**: Weak. Fully post-hoc motivation. Would need strong independent justification before any empirical test.

### H3-TREND-PULLBACK-COMPOSITE

| SRR-002 Requirement | Assessment |
|---------------------|-----------|
| Pre-observable? | Yes, in principle. |
| Motivated post-hoc? | Fully. Composite designed from observed separations. |
| Risk of no-trade gate fitted to losing years? | Very high. Designed to explain known failures. |
| Explains both valid and invalid states? | Appears to, but only because it was constructed from the data. |
| Invalid state non-empty? | Yes. |
| Requires new empirical evidence? | Yes. |
| Avoids runtime interpretation? | Uncertain. Composite scoring risks runtime interpretation. |

**SRR-002 compliance**: Fails. Violates SRR-002 Section 2 (post-hoc fitting penalty) and Section 5 (conditional module evidence standard). Not admissible without independent prior hypothesis.

### H4-LONG-DURATION-CONTINUATION

| SRR-002 Requirement | Assessment |
|---------------------|-----------|
| Pre-observable? | No. |
| All other requirements | N/A — fails the most basic requirement. |

**SRR-002 compliance**: Fails. Not pre-observable.

---

## 7. Recommended Next Step

**Recommendation: D — Proceed to additional attribution only.**

Rationale:

- H1 is the only plausible hypothesis, but it is incomplete: it does not explain 2023 or 2022, and adding bar range percentile to address 2023 introduces post-hoc risk.
- C (proceed to frozen diagnostic plan) would be justified only if the inspect identifies one small, pre-observable, non-composite hypothesis with clear information gain and failure closure. H1 does not meet this bar because:
  1. The ATR-only component (already tested in CPM-MOD-002) does not explain 2023.
  2. Adding bar range percentile is post-hoc and would need its own independent justification.
  3. The combined ATR + bar range hypothesis has not been pre-registered or frozen.
- The 2023 failure remains the key unresolved problem. 2023 losers enter in moderate-volatility, moderate-bar-range states that overlap with 2024/2025 winner states. No pre-observable feature cleanly separates them.
- Additional attribution work should focus on:
  - Whether bar range percentile has independent theoretical motivation (not just empirical separation)
  - Whether 2022 failure has a pre-observable explanation distinct from volatility
  - Whether the 2023 continuation failure has any pre-observable proxy
- Until these attribution gaps are resolved, a frozen diagnostic plan would risk testing an incomplete hypothesis.

---

## 8. Classification

**BOUNDARY_HYPOTHESIS_PARTIAL_NEEDS_ATTRIBUTION**

Rationale:

- One hypothesis (H1) is plausible but incomplete
- The strongest pre-observable separation (ATR percentile) was already tested in CPM-MOD-002 and does not explain 2023
- The next-best separation (bar range percentile) is post-hoc
- No single pre-observable feature cleanly separates all hostile states from all favorable states
- The dominant failure dimension (continuation) is post-entry and not directly usable as a boundary
- Composite hypotheses are post-hoc and violate SRR-002
- Additional attribution is needed before a frozen diagnostic plan is justified

CPM-1 classification remains: `CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT`

---

## 9. Explicit Prohibitions

This report does not authorize:

- CPM-1 changes
- CPM-MOD-003
- Any new gate
- Backtest
- Parameter sweep
- Runtime
- Small-live
- Strategy rescue
- Lower-timeframe rescue
- Extra-data rescue
- Router/regime/portfolio work

---

## 10. Owner Summary

### Is there a plausible CPM applicability boundary hypothesis?

Partially. H1 (low-to-moderate volatility continuation state) is plausible for 2021 but incomplete for 2023 and 2022. No single hypothesis explains all failure modes with pre-observable features.

### Which hypothesis is strongest?

H1-VOL-CONTINUATION. It has the most supporting evidence, was partially pre-registered in CPM-MOD-002, and uses pre-observable features. However, it is incomplete: it explains 2021 well but 2023 poorly.

### Which hypothesis is weakest?

H4-LONG-DURATION-CONTINUATION. It is not pre-observable and cannot be used as a boundary hypothesis. It is a diagnostic label, not a predictive boundary.

### What does 2023 teach us?

2023 teaches that CPM-1 can fail in moderate-volatility, moderate-bar-range states where continuation simply does not materialize. The failure is post-entry (near-zero MFE in 2 bars) but the pre-entry state is not clearly distinguishable from favorable states. This is the hardest problem for CPM-1 boundary research: the most damaging failure mode may not have a pre-observable signature.

### What does 2021 teach us?

2021 teaches that high-volatility entries are reliably hostile for CPM-1. The ATR > 60% gate works for 2021. But 2021 also teaches that volatility alone is insufficient: 47% of 2021 losses occur at moderate ATR, and 2022 has similar ATR to 2024 but loses. Volatility is a necessary but not sufficient condition for CPM-1 failure.

### Why is this still not runtime or small-live?

- No validated applicability boundary exists
- The strongest hypothesis (H1) is incomplete
- 2023 failure has no pre-observable explanation
- 2025 evidence is structurally fragile (top-5 concentration 270%)
- SRR-002 Level 3 admission gate has 10 requirements; CPM-1 satisfies none
- Any empirical work requires separate Owner authorization

### What is the next legitimate step, if any?

Additional attribution. Specifically:
1. Investigate whether bar range percentile has independent theoretical motivation beyond empirical separation
2. Investigate whether 2022 failure has a pre-observable explanation (similar ATR to 2024 but loses — why?)
3. Investigate whether any pre-observable proxy for continuation potential exists
4. If and only if attribution resolves these gaps, then proceed to a frozen diagnostic plan (C)

This is not a recommendation to stop CPM research. It is a recommendation that the next step must be attribution, not empirical testing, because the current hypotheses are insufficient for a frozen spec.

---

> CPM-1 remains non-runtime and non-small-live. This hypothesis inspect does not authorize CPM-1 changes, gates, empirical runs, runtime use, or strategy rescue. Any future empirical work requires separate Owner approval and must satisfy SRR-002.
