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

# CPM-1 Continuation-Failure Pre-Observable Proxy Attribution

**Task ID**: CPM-1-CONTINUATION-FAILURE-PREOBSERVABLE-PROXY-ATTRIBUTION
**Date**: 2026-05-08
**Status**: Completed / docs-only attribution study
**Classification**: CONTINUATION_PROXY_POST_HOC_ONLY
**CPM-1 Classification**: CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT (unchanged)

---

## 0. Boundary

This is a docs/report-only attribution study. It investigates whether CPM-1's post-entry continuation failure has any credible pre-observable proxy.

It is not:
- A gate proposal or gate definition
- A backtest or empirical run
- A parameter sweep or strategy rescue
- CPM-MOD-003 or E4 experiment
- Runtime or small-live authorization
- A decision to proceed with any empirical work

It may analyze whether existing features correlate with continuation outcomes. It does not transform those findings into a trading rule.

---

## 1. Continuation Failure Labels

### 1.1 Label definitions

Using post-entry diagnostics only, positions are classified into four descriptive labels:

| Label | Definition | Diagnostic inputs |
|-------|-----------|-----------------|
| immediate_failure | MFE in R < 0.3, or MFE < 15 and bars_to_mfe <= 3, and TP1 not reached | mfe, mfe_r, bars_to_mfe, tp1_reached |
| weak_continuation | Some MFE but TP1 not reached, and not immediate_failure | mfe, tp1_reached |
| normal_continuation | TP1 reached but TP2 not reached | tp1_reached, tp2_reached |
| strong_continuation | TP2 reached | tp2_reached |

**Critical statement**: Continuation labels are used to study failure type. They are not available before entry and cannot be used directly as gates.

### 1.2 Label distribution

| Label | Count | Percentage |
|-------|-------|-----------|
| immediate_failure | 139 | 42.2% |
| weak_continuation | 38 | 11.6% |
| normal_continuation | 83 | 25.2% |
| strong_continuation | 69 | 21.0% |

### 1.3 Label distribution by year

| Year | Positions | Immediate | Weak | Normal | Strong |
|------|-----------|-----------|------|--------|--------|
| 2021 | 153 | 70 (45.8%) | 24 (15.7%) | 32 (20.9%) | 27 (17.6%) |
| 2022 | 94 | 36 (38.3%) | 9 (9.6%) | 32 (34.0%) | 17 (18.1%) |
| 2023 | 18 | 12 (66.7%) | 2 (11.1%) | 1 (5.6%) | 3 (16.7%) |
| 2024 | 31 | 10 (32.3%) | 1 (3.2%) | 7 (22.6%) | 13 (41.9%) |
| 2025 | 33 | 11 (33.3%) | 2 (6.1%) | 11 (33.3%) | 9 (27.3%) |

**Key finding**: 2023 has the highest immediate_failure rate (66.7%) of any year. 2024 has the highest strong_continuation rate (41.9%). The continuation label distribution cleanly separates hostile and favorable years.

---

## 2. 2023 Continuation Failure Shape

### 2.1 Failure composition

| Category | Count | Detail |
|----------|-------|--------|
| Total positions | 18 | |
| Immediate failures | 12 | 80% of losers |
| Weak continuation | 2 | 13% of losers |
| Normal continuation | 1 | 7% of losers (reached TP1 then SL) |
| Strong continuation | 3 | All 3 winners (TP2 reached) |
| TP1 reached | 4 | 3 winners + 1 loser |
| TP2 reached | 3 | All winners |
| SL reached | 15 | All losers |

### 2.2 Post-entry diagnostics

| Metric | 2023 All | 2023 Losers | 2023 Winners |
|--------|----------|-------------|--------------|
| MFE median | 8.14 | 4.26 | 48.44 |
| MAE median | -22.61 | -23.10 | -11.80 |
| Giveback median | 91.40 | 91.54 | -125.54 |
| bars_to_mfe median | 3 | 2 | 28 |
| bars_to_mae median | 10 | 8 | 17 |
| mfe_r median | 0.21 | 0.21 | N/A (n=3) |

### 2.3 Failure shape assessment

2023 is **broadly hostile**, not concentrated in a few trades:

- 15 of 18 positions are losers (83.3% loss rate)
- 12 of 15 losers are immediate failures (80%)
- Only 1 loser reached TP1 (and then hit SL)
- Median MFE for losers is 4.26 — price barely moves favorably
- Median bars_to_mfe for losers is 2 — continuation fails within 2 hours of entry
- The 3 winners have MFE 43-99 and bars_to_mfe 25-43, showing that continuation *is* possible in 2023 but is rare

2023 winners differ from 2023 losers in post-entry path (MFE 48 vs 4, bars_to_mfe 28 vs 2) but **not** in pre-entry features (see Section 3). The 2023 winners enter at very low ATR percentile (median 10.7%) and very low bar range percentile (median 19.3%), suggesting they found rare calm states in an otherwise choppy year.

**Conclusion**: 2023 is uniformly hostile for CPM-1. The few valid CPM-1 behaviors occur in unusually low-volatility microstates. No pre-observable feature cleanly separates the 3 winners from the 15 losers within 2023 itself (sample too small and feature distributions overlap).

---

## 3. Continuation Labels vs Pre-entry Features

### 3.1 Pre-entry feature distributions by continuation label

#### 1h features

| Feature | Immediate (n=139) | Weak (n=38) | Normal (n=83) | Strong (n=69) |
|---------|-------------------|-------------|----------------|----------------|
| h1_atr14_pct90d | 42.8 | 59.2 | 37.0 | 29.9 |
| h1_bar_range_pct90d | 42.2 | 42.8 | 39.8 | 31.3 |
| h1_rv_72h | 0.0073 | 0.0088 | 0.0075 | 0.0071 |
| h1_ret_7d | 8.2 | 9.7 | 11.8 | 7.7 |
| h1_close_dist_ema50_pct | 2.17 | 2.02 | 2.68 | 1.97 |
| h1_ema50_slope_20 | 2.21 | 3.66 | 2.32 | 1.43 |
| h1_pullback_depth_pct | 1.40 | 1.48 | 1.42 | 0.98 |
| loc_1h_norm_position_20bar | 0.67 | 0.69 | 0.72 | 0.73 |

#### 4h features

| Feature | Immediate (n=139) | Weak (n=38) | Normal (n=83) | Strong (n=69) |
|---------|-------------------|-------------|----------------|----------------|
| h4_atr14_pct90d | 41.2 | 54.1 | 34.9 | 35.4 |
| h4_close_dist_ema60_pct | 6.01 | 7.18 | 6.21 | 5.16 |
| h4_ema60_slope_20 | 2.09 | 4.21 | 2.92 | 2.54 |
| h4_dc20_normalized | 0.78 | 0.85 | 0.86 | 0.82 |
| h4_ret_18bars | 4.81 | 7.43 | 5.69 | 5.06 |

### 3.2 Strongest pre-entry differences by continuation label

Ranked by absolute median difference between strong_continuation and immediate_failure:

| Rank | Feature | Strong | Immediate | Diff | Direction |
|------|---------|--------|-----------|------|-----------|
| 1 | h1_atr14_pct90d | 29.9 | 42.8 | -12.9 | Lower ATR percentile favors continuation |
| 2 | h1_bar_range_pct90d | 31.3 | 42.2 | -10.9 | Lower bar range percentile favors continuation |
| 3 | h1_ema50_slope_20 | 1.43 | 2.21 | -0.78 | Gentler trend slope favors continuation |
| 4 | h1_pullback_depth_pct | 0.98 | 1.40 | -0.42 | Shallower pullback favors continuation |
| 5 | h4_atr14_pct90d | 35.4 | 41.2 | -5.8 | Lower 4h ATR percentile favors continuation |
| 6 | h4_close_dist_ema60_pct | 5.16 | 6.01 | -0.85 | Closer to 4h EMA favors continuation |
| 7 | h1_close_dist_ema50_pct | 1.97 | 2.17 | -0.20 | Closer to 1h EMA favors continuation |

### 3.3 Weakest / non-separating features

| Feature | Strong | Immediate | Diff | Assessment |
|---------|--------|-----------|------|-----------|
| h1_rv_24h | 0.0068 | 0.0072 | -0.0004 | Does not separate |
| h1_ret_24h | 2.04 | 2.99 | -0.95 | Weak, overlapping |
| loc_1h_norm_position_20bar | 0.73 | 0.67 | +0.06 | Does not separate |
| h4_dc20_normalized | 0.82 | 0.78 | +0.04 | Does not separate |

### 3.4 Intuitive market meaning

The features that best separate continuation outcomes have clear intuitive meaning:

- **ATR percentile**: High-volatility entries produce immediate reversals. Low-volatility entries allow continuation. This is the most established finding (CPM-MOD-002).
- **Bar range percentile**: Elevated bar range indicates choppier intrabar price action that disrupts pullback continuation. Distinct from ATR because ATR is an average while bar range percentile captures the current bar's relative disorder.
- **EMA slope**: Steeper trends (higher slope) indicate overextension. Entries in gentler-trending environments have more room for continuation.
- **Pullback depth**: Deeper pullbacks in volatile environments are more likely to be reversals than discounts.
- **Distance to EMA**: Entries far above the trend mean are overextended.

**However**: These differences are between *aggregate* continuation groups across all years. They do not establish that within a given year, pre-entry features can predict continuation outcome.

---

## 4. 2023 vs 2024 Continuation Contrast

### 4.1 Pre-entry feature comparison

| Feature | 2023 Losers | 2024 Winners | Diff | Overlap% | Separates? |
|---------|-------------|--------------|------|----------|-----------|
| h1_bar_range_pct90d | 50.5 | 24.5 | -25.9 | 28.6% | Best separator |
| h1_atr14_pct90d | 43.4 | 25.6 | -17.8 | 44.3% | Moderate |
| h4_close_dist_ema60_pct | 3.00 | 2.15 | -0.86 | 32.5% | Moderate |
| h4_ema60_slope_20 | 1.19 | 0.40 | -0.79 | 29.5% | Moderate |
| h1_pullback_depth_pct | 0.98 | 0.73 | -0.25 | 26.5% | Weak |
| h1_ema50_slope_5 | 0.78 | 1.13 | +0.35 | 34.1% | Weak (reversed) |
| h1_close_dist_ema50_pct | 1.52 | 1.37 | -0.15 | 71.7% | Does not separate |
| h1_ema50_slope_20 | 0.98 | 0.96 | -0.02 | 55.1% | Does not separate |
| h4_dc20_normalized | 0.76 | 0.77 | +0.01 | 58.4% | Does not separate |
| h1_rv_24h | 0.004 | 0.004 | ~0 | 49.1% | Does not separate |

### 4.2 Assessment

**Which features best distinguish 2023 losers from 2024 winners?**

1. h1_bar_range_pct90d (25.9 percentile point gap, 28.6% overlap)
2. h1_atr14_pct90d (17.8 percentile point gap, 44.3% overlap)

**Are the differences large enough to be meaningful?**

Bar range percentile shows the largest gap (25.9 points) with the lowest overlap (28.6%). This is the strongest pre-observable separation between 2023 losers and 2024 winners. ATR percentile has a meaningful gap (17.8 points) but higher overlap (44.3%).

**Are the distributions overlapping?**

Yes, substantially. Even for bar range percentile, 28.6% overlap means the IQR ranges intersect. For ATR percentile, 44.3% overlap is significant. No threshold cleanly separates 2023 losers from 2024 winners without misclassifying a meaningful fraction of both groups.

**Are the differences theoretically interpretable?**

Bar range percentile: partially. Elevated bar range in 2023 could indicate choppier intrabar action that disrupts pullback continuation. But 2025 winners also enter at elevated bar range (median 41.2%) close to 2023 losers (50.5%), which weakens the theoretical case.

ATR percentile: yes. This is the established CPM-MOD-002 finding. Lower ATR percentile at entry is associated with better continuation.

**Are they merely post-hoc observations?**

Yes. The observation that bar range percentile separates 2023 from 2024 was made during the feature-context extraction, after examining the data. No prior hypothesis predicted this specific feature. The ATR percentile separation was partially pre-registered in CPM-MOD-002, but the specific 2024/2023 gap observation is post-hoc.

### 4.3 2024 top-5 winners

2024 top-5 winners enter at:
- ATR percentile median 49.4% (higher than 2024 all-winners 25.6%)
- Bar range percentile median 41.8% (higher than 2024 all-winners 24.5%)

This is important: the largest 2024 wins occur in *elevated* volatility and bar range states. Any gate that filters elevated bar range or ATR would also filter some of CPM-1's best trades. This is a fundamental tension.

---

## 5. 2022 Failure Attribution

### 5.1 2022 continuation label distribution

| Label | Count | Percentage |
|-------|-------|-----------|
| immediate_failure | 36 | 38.3% |
| weak_continuation | 9 | 9.6% |
| normal_continuation | 32 | 34.0% |
| strong_continuation | 17 | 18.1% |

2022 has a materially different continuation profile from 2023:
- 2022 has 18.1% strong continuation (vs 2023's 16.7%) — similar
- 2022 has 34.0% normal continuation (vs 2023's 5.6%) — much higher
- 2022 has 38.3% immediate failure (vs 2023's 66.7%) — much lower

**2022 is not a continuation-failure year.** It is a cost-dominated year where continuation exists but is insufficient to overcome costs.

### 5.2 2022 losers post-entry diagnostics

| Metric | 2022 Losers | 2023 Losers | 2024 Winners |
|--------|-------------|-------------|--------------|
| MFE median | 16.10 | 4.26 | 406.17 |
| MAE median | -34.02 | -23.10 | -56.37 |
| Giveback median | 85.47 | 91.54 | 318.24 |
| bars_to_mfe median | 1 | 2 | 207 |

2022 losers have MFE 16.10 vs 2023 losers' 4.26. 2022 losers experience *some* favorable excursion (3.8x more than 2023), but it is far too small to reach TP1 (1.0R). The continuation exists but is weak — price moves favorably for 1 bar then reverses.

### 5.3 2022 vs 2024 winners pre-entry comparison

| Feature | 2024 Winners | 2022 All | Diff | Assessment |
|---------|--------------|----------|------|-----------|
| h1_atr14_pct90d | 25.6 | 25.7 | -0.1 | **Identical** |
| h1_bar_range_pct90d | 24.5 | 28.9 | -4.4 | Small |
| h4_close_dist_ema60_pct | 2.15 | 5.98 | -3.83 | Moderate |
| h1_pullback_depth_pct | 0.73 | 1.64 | -0.91 | Moderate |
| h1_ret_7d | 4.96 | 10.96 | -6.00 | Large |
| h4_ret_18bars | 1.55 | 5.93 | -4.39 | Large |
| h4_ema60_slope_20 | 0.40 | 1.92 | -1.52 | Moderate |

### 5.4 2022 failure explanation

2022 failure is **not** primarily a volatility problem. ATR percentile at 2022 entries (median 25.7%) is nearly identical to 2024 winners (25.6%). Bar range percentile (28.9%) is close to 2024 winners (24.5%).

2022 failure is best explained as a **low-trend-payoff** problem:

1. **Cost-dominated**: 2022 losers have median MFE 16.10 — some continuation exists but is insufficient to cover costs and reach TP1. The median PnL of 2022 losers is -73.11.
2. **Weak continuation despite moderate volatility**: Unlike 2023 where continuation fails immediately, 2022 continuation starts but dies quickly (bars_to_mfe = 1).
3. **Deeper pullbacks in lower-trend environment**: 2022 pullback depth (1.64%) is materially higher than 2024 winners (0.73%), suggesting entries from deeper retracements that may not recover.
4. **Larger distance to 4h EMA60**: 2022 entries are 5.98% above 4h EMA60 vs 2.15% for 2024 winners, suggesting more overextended entry positions.
5. **Bear-market long-only directional headwind**: 2022 was a bear year for ETH. Long-only pullback-continuation faces a structural headwind when the broader trend is down.

### 5.5 Does 2022 have a pre-observable explanation distinct from volatility?

**Yes.** The pre-observable features that best distinguish 2022 from 2024 are:

1. **h1_ret_7d** (7-day return): 2022 median 10.96% vs 2024 4.96%. 2022 entries occur after larger recent rallies, suggesting overextension.
2. **h4_ret_18bars** (4h 18-bar return): 2022 median 5.93% vs 2024 1.55%. Same pattern — entries after larger recent moves.
3. **h1_pullback_depth_pct**: 2022 median 1.64% vs 2024 0.73%. Deeper pullbacks.
4. **h4_close_dist_ema60_pct**: 2022 median 5.98% vs 2024 2.15%. More overextended from trend.

These are pre-observable features with intuitive meaning: entering after larger recent moves, from deeper pullbacks, when price is far above the trend, produces weaker continuation. However, these are also post-hoc observations from this attribution study.

---

## 6. Bar Range Theoretical Motivation

### 6.1 What bar range percentile might represent

h1_bar_range_pct90d measures where the current 1h bar's range falls in the rolling 90-day distribution of bar ranges. Elevated percentile means the current bar has an unusually wide range relative to recent history.

Possible interpretations:

1. **Choppiness / local disorder**: An unusually wide bar suggests price is moving aggressively in both directions within a single bar, indicating disorderly price action that disrupts clean pullback continuation.

2. **Unstable pullback**: If the bar containing the entry signal has an unusually wide range, the Pinbar pattern may be less reliable — the wick-to-body ratio could be distorted by intrabar noise.

3. **Intrabar liquidation noise**: Wide bars in moderate-ATR environments could indicate forced liquidations or large market orders that create temporary dislocations, which reverse quickly.

4. **Exhaustion rather than continuation**: An unusually wide bar at the pullback low could indicate selling exhaustion (capitulation) rather than the start of continuation. CPM-1's thesis requires orderly continuation, not exhaustion spikes.

5. **Information content distinct from ATR**: ATR is a 14-bar average that smooths over recent history. Bar range percentile captures the *current* bar's relative extremity. A moderate ATR with an elevated bar range percentile means: "average volatility is normal, but this specific bar is extreme." This is a different informational state than high ATR.

### 6.2 How bar range differs from ATR percentile

| Dimension | ATR Percentile | Bar Range Percentile |
|-----------|---------------|---------------------|
| Lookback | 14-bar average | Single bar |
| Smoothing | High (14-bar EMA) | None (current bar) |
| Captures | Sustained volatility regime | Current bar extremity |
| 2023 vs 2024 gap | 17.8 percentile points | 25.9 percentile points |
| 2025 contradiction | 2025 wins at ATR 47% while 2023 loses at 43% | 2025 wins at bar range 41% while 2023 loses at 50% |
| Pre-registered? | Partially (CPM-MOD-002) | No |

### 6.3 Why bar range might capture 2023 better than ATR

2023 has moderate ATR (percentile 43.4%) but elevated bar range (percentile 50.5%). This means: the *average* volatility is not extreme, but individual bars are unusually wide. This is consistent with a choppy, mean-reverting market where individual bars have large ranges but the 14-bar average is moderated by alternating directions. ATR smooths this out; bar range percentile does not.

### 6.4 Why 2025 winning at elevated bar range weakens it

2025 winners enter at bar range percentile 41.2%, which is close to 2023 losers' 50.5%. The gap is only 9.3 percentile points, and the distributions overlap substantially. If bar range percentile were a clean continuation proxy, 2025 winners should enter at low bar range — but they don't. This means either:
- Bar range percentile is not a clean separator (it captures some but not all continuation failure)
- 2025 is a different regime where elevated bar range does not prevent continuation
- The 2023/2024 separation is partially coincidental

### 6.5 Classification

**BAR_RANGE_IS_POST_HOC_CLUE_ONLY**

Rationale:

- Bar range percentile has *some* theoretical motivation: it captures current-bar extremity distinct from average volatility, and choppiness is a plausible continuation disruptor.
- However, the observation that it separates 2023 from 2024 was made after examining the data, with no prior hypothesis.
- 2025 winning at elevated bar range materially weakens the case.
- The overlap between favorable and hostile distributions is substantial (28.6%).
- No threshold can be chosen from the data without post-hoc fitting.
- The theoretical motivation is suggestive but not strong enough to overcome the post-hoc origin.

Bar range percentile should remain an attribution clue. It is not eligible for a frozen hypothesis without independent prior prediction.

---

## 7. Candidate Pre-Observable Continuation Proxies

### 7.1 Proxy: Low bar-range percentile

**Definition**: Entry bar range percentile below some threshold.

| Criterion | Assessment |
|-----------|-----------|
| Pre-observable | Yes |
| Theoretical motivation | Partial: choppiness disrupts continuation |
| Empirical separation | Best single feature (25.9 point gap) |
| Contradicted by | 2025 wins at 41.2%; 2024 top-5 wins at 41.8% |
| Post-hoc risk | High: no prior hypothesis predicted this |
| Overlap | 28.6% between 2024 winners and 2023 losers |

**Classification: POST_HOC**

### 7.2 Proxy: Moderate ATR + low bar-range

**Definition**: ATR percentile below threshold AND bar range percentile below threshold.

| Criterion | Assessment |
|-----------|-----------|
| Pre-observable | Yes |
| Theoretical motivation | Partial: combines two related volatility dimensions |
| Empirical separation | Stronger than either alone |
| Contradicted by | 2025 wins at ATR 47% + bar range 41%; 2024 top-5 at ATR 49% + bar range 42% |
| Post-hoc risk | Very high: composite constructed from observed separations |
| SRR-002 compliance | Fails Section 2 (post-hoc fitting penalty) |

**Classification: POST_HOC**

### 7.3 Proxy: Not overextended from EMA

**Definition**: Entry price close to 1h EMA50 and 4h EMA60 (small distance percentage).

| Criterion | Assessment |
|-----------|-----------|
| Pre-observable | Yes |
| Theoretical motivation | Strong: overextension from trend is a well-known continuation risk |
| Empirical separation | Moderate: h4_close_dist_ema60_pct gap 0.86 between 2024W and 2023L |
| Contradicted by | 2022 has similar distance to 2024 but loses; overlap is 32.5% |
| Post-hoc risk | Moderate: overextension is a known concept, but the specific threshold is post-hoc |

**Classification: PLAUSIBLE**

This is the only proxy with independent theoretical motivation that does not rely on a post-hoc feature discovery. Overextension from trend mean is a well-established concept in trend-following literature. However, it does not cleanly separate 2023 from 2024 (overlap 32.5%), and it does not explain 2022 failure (2022 has higher distance but similar ATR to 2024).

### 7.4 Proxy: Favorable recent return profile

**Definition**: Recent returns (7d, 72h) not too large — entry not after a large recent rally.

| Criterion | Assessment |
|-----------|-----------|
| Pre-observable | Yes |
| Theoretical motivation | Moderate: entering after a large rally increases reversal risk |
| Empirical separation | h1_ret_7d gap 6.0 between 2024W and 2022All; weaker for 2023 |
| Contradicted by | 2021 losers have high returns but so do 2021 winners |
| Post-hoc risk | Moderate |

**Classification: WEAK**

### 7.5 Proxy: Shallow but not too shallow pullback

**Definition**: Pullback depth in a moderate band — not too deep (reversal risk) and not too shallow (no real pullback).

| Criterion | Assessment |
|-----------|-----------|
| Pre-observable | Yes |
| Theoretical motivation | Moderate: pullback depth is part of CPM-1's thesis |
| Empirical separation | 0.25 gap between 2024W and 2023L; 0.91 gap between 2024W and 2022All |
| Contradicted by | 2022 winners have pullback depth 1.16% (deeper than 2024 winners 0.73%) |
| Post-hoc risk | Moderate |

**Classification: WEAK**

### 7.6 Proxy: Trend slope band

**Definition**: EMA slope in a moderate band — not too steep (overextension) and not too flat (no trend).

| Criterion | Assessment |
|-----------|-----------|
| Pre-observable | Yes |
| Theoretical motivation | Moderate: trend strength is part of CPM-1's thesis |
| Empirical separation | h4_ema60_slope_20 gap 0.79 between 2024W and 2023L |
| Contradicted by | 2021 losers have high slope; 2023 losers have similar slope to 2024 winners on 1h |
| Post-hoc risk | Moderate |

**Classification: WEAK**

### 7.7 Proxy: Price not too close to local high

**Definition**: loc_1h_norm_position_20bar not too high — entry not at the top of the recent range.

| Criterion | Assessment |
|-----------|-----------|
| Pre-observable | Yes |
| Theoretical motivation | Weak: CPM-1 enters on pullback, so position should be mid-range |
| Empirical separation | 0.11 gap between 2024W and 2023L — very small |
| Contradicted by | Distributions heavily overlap |
| Post-hoc risk | Low, but separation is too weak |

**Classification: NOT_SUPPORTED**

### 7.8 Summary of proxy classifications

| Proxy | Classification | Key weakness |
|-------|---------------|--------------|
| Low bar-range percentile | POST_HOC | 2025 wins at elevated bar range; no prior hypothesis |
| Moderate ATR + low bar-range | POST_HOC | Composite violates SRR-002; 2024 top-5 filtered |
| Not overextended from EMA | PLAUSIBLE | Overlap 32.5%; does not explain 2022 |
| Favorable recent return profile | WEAK | Does not separate 2023 from 2024 |
| Shallow pullback | WEAK | 2022 winners have deeper pullbacks |
| Trend slope band | WEAK | 1h slope does not separate 2023 from 2024 |
| Price not at local high | NOT_SUPPORTED | Gap too small, heavy overlap |

**No proxy achieves PLAUSIBLE with clean separation.** The only PLAUSIBLE proxy (not overextended from EMA) has substantial overlap and does not explain 2022 failure. All other proxies are POST_HOC, WEAK, or NOT_SUPPORTED.

---

## 8. H1-VOL-CONTINUATION Status After Attribution

### 8.1 What this attribution adds to H1

H1-VOL-CONTINUATION previously stated: CPM-1 works when entry volatility is low-to-moderate, and fails when volatility is high (2021) or bar range is elevated (2023).

This attribution adds:

1. **Continuation failure is the dominant failure dimension**: For 2023, continuation failure (MFE magnitude 401.9) overwhelms pre-entry feature differences (17.8 for ATR, 25.9 for bar range). The most visible difference between favorable and hostile outcomes is post-entry, not pre-entry.

2. **Bar range percentile has theoretical motivation but is post-hoc**: The attribution confirms that bar range captures something ATR does not (current-bar extremity vs. smoothed average), but the observation was made after examining data, and 2025 contradicts a clean separation.

3. **2022 failure is not a volatility problem**: H1 does not explain 2022 because 2022 has similar ATR and bar range to 2024. 2022 failure is a low-trend-payoff / cost-dominated problem. This is a new gap in H1 that was not previously articulated.

4. **No pre-observable continuation proxy exists**: The dominant failure dimension (continuation) has no credible pre-observable proxy. The best proxies (bar range, ATR) capture only the pre-entry conditions that *sometimes* precede continuation failure, but they do not predict continuation itself.

### 8.2 Classification

**PLAUSIBLE_BUT_INCOMPLETE**

H1 remains plausible because:
- ATR percentile was partially pre-registered (CPM-MOD-002)
- Low-to-moderate volatility is associated with better continuation
- The ATR > 60% gate works for 2021

H1 remains incomplete because:
- It does not explain 2023 (moderate ATR, continuation failure)
- It does not explain 2022 (similar ATR to 2024, cost-dominated failure)
- Adding bar range percentile to address 2023 introduces post-hoc risk
- No pre-observable continuation proxy has been identified
- 2025 wins at ATR/bar range levels similar to 2023 losers

H1 is not strengthened by this attribution because no new pre-observable feature with independent theoretical motivation was found that cleanly separates hostile from favorable states.

H1 is not weakened to the point of rejection because the ATR component remains valid for 2021 and the theoretical motivation for low-volatility continuation is sound.

---

## 9. Recommendation

**D — Continue attribution only.**

Rationale:

- No single pre-observable hypothesis with clear information gain and failure closure has been identified.
- The only PLAUSIBLE proxy (not overextended from EMA) has substantial overlap and does not explain 2022.
- Bar range percentile is the strongest empirical separator but is post-hoc and contradicted by 2025.
- Recommendation C (proceed to frozen diagnostic plan) requires one small, pre-observable, non-composite hypothesis with independent theoretical motivation, clear information gain, and failure closure. No such hypothesis exists after this attribution.
- The 2023 continuation failure remains the key unresolved problem, and it appears to be largely invisible before entry under the current CPM-1 feature set.

Additional attribution work should focus on:
1. Whether the "not overextended from EMA" proxy can be strengthened with independent theoretical support from trend-following literature
2. Whether 2022's low-trend-payoff failure has any pre-observable signature beyond what was identified here
3. Whether any feature not yet extracted could serve as a continuation proxy (e.g., higher-timeframe trend health, volume profile, order flow imbalance) — but this would require new data extraction, which is beyond the scope of this docs-only study

---

## 10. Classification

**CONTINUATION_PROXY_POST_HOC_ONLY**

Rationale:

- The strongest pre-observable separation (bar range percentile, 25.9 point gap) is post-hoc
- The only theoretically motivated proxy (not overextended from EMA) has substantial overlap (32.5%) and does not explain 2022
- No pre-observable continuation proxy with clean separation, independent motivation, and no contradiction has been found
- The dominant failure dimension (continuation) is post-entry and not directly usable as a boundary
- All candidate proxies are either POST_HOC, WEAK, or NOT_SUPPORTED
- CPM-1's most damaging failure mode (2023 continuation failure) appears to be largely invisible before entry

CPM-1 classification remains: **CONDITIONAL_EDGE_CANDIDATE / APPLICABILITY_RESEARCH_OBJECT**

No evidence from this attribution requires downgrade. The classification accurately reflects that CPM-1 has conditional edge in some states but no validated applicability boundary.

---

## 11. Explicit Prohibitions

This report does not authorize:

- CPM-1 changes
- CPM-MOD-003
- Any new gate
- Backtest
- Empirical diagnostic
- Parameter sweep
- Runtime
- Small-live
- Strategy rescue
- Lower-timeframe rescue
- Extra-data rescue
- Router/regime/portfolio work

---

## 12. Owner Summary

### Did we find any credible pre-observable proxy for continuation failure?

No. The strongest empirical separator (bar range percentile) is post-hoc and contradicted by 2025. The only theoretically motivated proxy (not overextended from EMA) has substantial overlap and does not explain 2022. The dominant failure dimension — continuation itself — appears to be largely invisible before entry under the current CPM-1 feature set.

### What does 2023 teach us now?

2023 teaches that CPM-1 can fail in a mode that is nearly undetectable before entry: moderate volatility, moderate bar range, reasonable trend slope, normal pullback depth — and then continuation simply does not materialize. 66.7% of 2023 positions are immediate failures (MFE near zero within 2 bars). The 3 winners in 2023 entered at unusually low ATR/bar range states, suggesting that 2023's rare favorable microstates are detectable only in the extreme low end of the distribution, not by a threshold that generalizes.

### What does 2022 teach us now?

2022 teaches a different lesson: CPM-1 can fail even when pre-entry features look similar to favorable years. 2022 has nearly identical ATR percentile (25.7%) and bar range percentile (28.9%) to 2024 winners (25.6%, 24.5%), yet loses. 2022 failure is cost-dominated with weak continuation (MFE 16 vs 406 for 2024 winners), not a volatility or bar-range problem. 2022's pre-observable signature is overextension: larger recent returns, deeper pullbacks, and greater distance from EMA. But these features also overlap with favorable states.

### Is bar range meaningful or just post-hoc?

Bar range percentile has partial theoretical motivation (current-bar extremity captures choppiness that ATR smooths over), and it produces the largest pre-observable separation between 2023 losers and 2024 winners (25.9 percentile points). However, it is classified as POST_HOC_CLUE_ONLY because: (1) no prior hypothesis predicted this feature, (2) 2025 wins at elevated bar range (41.2%), weakening the separation, (3) any threshold would be fitted to the data, and (4) 2024 top-5 wins also occur at elevated bar range (41.8%). Bar range should remain an attribution clue, not a frozen hypothesis.

### Is H1 stronger or still incomplete?

Still incomplete. H1-VOL-CONTINUATION remains PLAUSIBLE_BUT_INCOMPLETE. This attribution did not strengthen H1 because no new pre-observable feature with independent theoretical motivation was found. H1 still does not explain 2023 (continuation failure at moderate volatility) or 2022 (cost-dominated failure at favorable volatility). Adding bar range percentile to H1 would increase its empirical coverage but introduce post-hoc risk that violates SRR-002.

### Why is CPM-1 still not runtime/small-live?

- No validated applicability boundary exists
- The strongest hypothesis (H1) is incomplete
- 2023 continuation failure has no pre-observable explanation
- 2022 failure is not explained by volatility-based boundaries
- 2025 evidence is structurally fragile (top-5 concentration 270%)
- SRR-002 Level 3 admission gate has 10 requirements; CPM-1 satisfies none
- The dominant failure dimension (continuation) is post-entry and cannot be gated pre-entry
- Any empirical work requires separate Owner authorization

### What should not be done next?

- Do not create a bar-range gate from the observed 2024/2023 gap — this is post-hoc fitting
- Do not construct a composite ATR + bar-range score — this violates SRR-002
- Do not proceed to CPM-MOD-003 — no frozen hypothesis supports it
- Do not attempt lower-timeframe timing rescue — the failure is continuation, not timing
- Do not attempt funding/OI/liquidation rescue — these are different failure modes
- Do not authorize small-live or runtime — no validated boundary exists

### What is the next legitimate step, if any?

Continue attribution only. Specifically:

1. Investigate whether "not overextended from EMA" can be strengthened with independent theoretical support from trend-following literature (this is the only PLAUSIBLE proxy)
2. Investigate whether 2022's low-trend-payoff failure has a pre-observable signature that could complement H1
3. If and only if attribution resolves these gaps with a single, small, pre-observable, non-composite hypothesis that has independent theoretical motivation, clear information gain, and failure closure — then proceed to a frozen diagnostic plan (C)

This is not a recommendation to stop CPM research. It is a recommendation that the next step must remain attribution, not empirical testing, because no hypothesis currently meets the bar for a frozen spec.

---

> CPM-1 remains non-runtime and non-small-live. This continuation-proxy attribution does not authorize CPM-1 changes, gates, empirical diagnostics, runtime use, or strategy rescue. Any future empirical work requires separate Owner approval and must satisfy SRR-002.
