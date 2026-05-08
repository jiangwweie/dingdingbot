# CPM-MOD-001: CPM-1 Applicability / Dynamic Enablement Inspect

**Task ID:** CPM-MOD-001
**Date:** 2026-05-07
**Authorization Level:** Level 1/2 — inspect + docs-only analysis
**Status:** Inspect complete
**Affects Runtime Automatically:** No

**Prohibitions (active throughout):**
No backtest execution. No code changes. No parameter tuning. No parameter sweep. No E4 hard filter experiment. No runtime/profile/risk/backtester core modification. No CPM-2 activation. No strategy router design. No portfolio engine. No small-live or canary-live candidate output.

---

## 0. Task Context

Owner has adjusted the strategy research posture: a strategy module need not perform well across all years. Modules may be conditionally enabled under specific, observable market conditions. The current question is not "rescue CPM-1" but "does CPM-1 have research value as an enable/disable module?"

This document is an inspect-only assessment. It synthesizes existing evidence to determine whether a Dynamic Enablement research path warrants a Level 3 frozen diagnostic.

---

## 1. CPM-1 Current Identity

### 1.1 What CPM-1 Is

CPM-1 is **Crypto Pullback Module v1**: a trend-pullback continuation module on ETH/USDT 1h (4h MTF confirmation) that enters LONG when a pullback within an established uptrend shows signs of ending.

**Identity hierarchy** (per scope note SSOT):

| Layer | Component | Role |
|-------|-----------|------|
| Module | CPM-1 | Trend-pullback continuation on ETH 1h |
| Entry trigger | Pinbar (wick/body geometry) | Detects pullback-ending moment |
| Trend filter | EMA50 distance + 4h EMA60 slope | Confirms established uptrend |
| MTF confirmation | 4h EMA60 rising | Ensures higher-timeframe alignment |
| Exit profile | TP1 1.0R / TP2 3.5R, SL -1.0R, OCO | Fixed R-multiple geometry |

Pinbar is the entry trigger, not the module definition. CPM-1's structural identity is **pullback-continuation-with-trend-confirmation**. A different trigger (inside bar, hammer, demand zone test) within the same structural framework would be CPM-2, not CPM-1.

### 1.2 What CPM-1 Is Not

- It is not "the system strategy."
- It is not a general-purpose crypto trading module.
- It is not a mean-reversion module.
- It is not a volatility-breakout module.
- It is not a trend-start or trend-reversal detector.

### 1.3 Profit Source

CPM-1 earns from **trend-pullback-continuation**: confirming that an existing trend is intact and entering at a discount during a pullback. The structural edge requires:

1. An established uptrend exists (EMA50 rising, 4h EMA60 rising).
2. Price pulls back within the trend (creating the pinbar wick).
3. The pullback ends and trend resumes (pinbar body confirms rejection).
4. Continuation carries price to TP targets.

This is distinct from breakout (entering on new highs), reversal (entering against trend), and volatility expansion (entering on range expansion).

### 1.4 Current Governance State

| Field | State |
|-------|-------|
| Baseline | Frozen (all parameters locked) |
| Promotion status | Paused — OOS gate failure (2021 + 2022 both negative) |
| Small-live candidate | No |
| OOS evidence | 2021: -21.54% (favorable-regime profit hypothesis failure); 2022: -9.72% (cost-dominated) |
| In-sample evidence | 2023: -39.24%; 2024: +85.01%; 2025: +44.90% |
| Failure classification | 2021 = signal-level failure in favorable regime; 2023 = boundary cost / regime mismatch |

---

## 2. Why 2024/2025 Warrant Re-Discussion

### 2.1 Positive Evidence Summary

| Year | PnL (USDT) | Win Rate | Sharpe | MaxDD | Classification |
|------|------------|----------|--------|-------|----------------|
| 2024 | +8,501 | 32.3% | 1.91 | 17.39% | In-sample, positive |
| 2025 | +4,490 | 31.7% | 2.01 | 11.56% | In-sample, positive |
| 2026 Q1 | +777 | — | — | — | Forward (testnet), small sample |

These are the only years in the entire evidence set where CPM-1 produces positive returns with coherent profit-hypothesis alignment. The win rates (~31–32%), Sharpe ratios (~1.9–2.0), and MaxDD figures (11–17%) are consistent with a working pullback-continuation module operating in its applicable market.

### 2.2 Negative Evidence Summary

| Year | PnL (USDT) | Win Rate | Sharpe | MaxDD | Classification |
|------|------------|----------|--------|-------|----------------|
| 2021 OOS | -2,154 | 29.5% | -2.47 | 22.18% | Favorable-regime profit hypothesis failure |
| 2022 OOS | -972 | 31.1% | -1.40 | 10.48% | Cost-dominated failure in unfavorable regime |
| 2023 | -3,924 | 16.1% | -2.63 | 49.19% | Regime mismatch / boundary cost |

The aggregate 3-year in-sample (2023–2025) is +9,067 USDT, but this is positive only because 2024/2025 offset 2023. The 3-year Sharpe is 0.31 — marginal.

### 2.3 What 2024/2025 Evidence Means

**2024/2025 are applicable-market evidence, not deployment permission.**

They demonstrate that the pullback-continuation mechanism can work in specific market conditions. They do not demonstrate:

- That the mechanism works across a full market cycle (it does not — 2021, 2022, 2023 are all negative).
- That the positive conditions will recur (in-sample period, no OOS validation of the positive regime itself).
- That the module is deployable as-is (promotion path is stopped by OOS failures).

**Correct interpretation:** 2024/2025 show CPM-1 has a conditional edge in a specific regime. The research question is whether that regime can be identified ex-ante. This is the Dynamic Enablement Hypothesis.

---

## 3. Dynamic Enablement Hypothesis

### 3.1 Core Question

> Can CPM-1 be conditionally enabled — trading only when observable market conditions match the regime where it historically profits — and disabled otherwise?

### 3.2 Can 2024/2025 Profits Be Described by Ex-Ante Observable Conditions?

**Suggestive, but not confirmed.**

The M0 Strategy Ecology Map (proxy model, 2023–2025) identifies the following conditions associated with CPM-1 profit:

| Condition | Observable? | Ex-Ante? | Evidence |
|-----------|-------------|----------|----------|
| Low ema_4h_slope (gentle uptrend) | Yes | Yes (rolling EMA slope is computable before entry) | M0 Tier 1: low slope → +656; high slope → -12,243 |
| Low recent_72h_return (no recent surge) | Yes | Yes (trailing return is computable) | M0 Tier 1: low return → +990; high return → -11,555 |
| Low realized_volatility_24h | Yes | Yes (rolling volatility is computable) | M0 Tier 1: low vol → -397 (least bad); high vol → -10,778 |
| Price not near Donchian 20 high | Yes | Yes (distance is computable) | M0 Tier 1: mid distance → +654; near top → -11,682 |
| Low ATR percentile (overall volatility) | Yes | Yes (rolling ATR percentile) | M0: 2023 ATR percentile 0.625; 2024/25: 0.531 |

These features are all computable from OHLCV data before a trading decision. They are ex-ante observable in principle. The M0 finding that CPM-1 earns in "low-slope, low-volatility uptrends with price below recent highs" is a coherent regime description.

### 3.3 Can 2023 Losses Be Described by Ex-Ante Observable Conditions?

**Suggestive, with a specific quantitative signal.**

| Condition | 2023 Value | 2024/2025 Value | Separable? |
|-----------|------------|-----------------|------------|
| ATR percentile (rolling) | 0.625 | 0.531 | Directionally yes — 2023 is higher-volatility |
| ema_4h_slope | 0.115 | 0.139 | **No** — 2023 has *lower* slope (should be favorable) |
| recent_72h_return | 0.035 | 0.050 | **No** — 2023 has *lower* return (should be favorable) |

The M0 finding is that ATR's negative effect dominated in 2023 despite slope and return being nominally favorable. This means the regime that produces losses in 2023 is primarily a **volatility regime**, not a slope or momentum regime.

**Key observation:** 2023 and 2024/2025 differ on ATR (volatility) but not on slope or return. This is a single-feature regime distinction, not a multi-feature one.

### 3.4 Would These Conditions Degenerate Into Post-Hoc Fitting?

**This is the central risk.** Several structural concerns:

**Risk 1: H3a feature overlap.** The 2023 rescue research (H0–H3a) tested pre-entry feature prediction specifically to separate 2023 bad trades from 2024/2025 good trades. The finding was decisive: "absolute feature levels overlapped between 2023 and 2024/2025; no threshold separates them." The best single feature (price_dist_ema_1h, 27.9pp discrimination) still could not produce a usable decision boundary. This is evidence that **trade-level feature classification fails**, even if module-level classification might differ.

**Risk 2: H0 coarse regime gate failure.** H0 tested EMA250/200 as a coarse regime gate to separate 2023 from 2024/2025. It failed because "coarse classification kills good-year trades." Any regime gate that blocks 2023 must not also block 2024/2025 profitable periods. H0 demonstrates this is non-trivial.

**Risk 3: Single-feature regime on limited data.** The ATR distinction (0.625 vs 0.531) is observed on a single 3-year window. There is no OOS validation of this regime boundary. The threshold that separates 2023 from 2024/2025 in-sample may not generalize. With only 3 data points (2023, 2024, 2025), any regime boundary is inherently fragile.

**Risk 4: Module-level vs trade-level mismatch.** Even if a module-level regime gate correctly identifies "2023 was a bad year for CPM-1," it must also not disable CPM-1 during the profitable sub-periods within bad years or the loss-producing sub-periods within good years. The 2021 OOS evidence shows that a bull year (2021) contained both profitable sub-regimes (Jan, Apr, Jul) and catastrophic sub-regimes (Aug–Oct: 16 consecutive losses). A module-level gate that disables for the full year would have avoided 2021 losses but also sacrificed the 3 profitable months.

**Risk 5: M0 is a proxy model.** The ecology map uses a random forest classifier as a proxy for understanding loss patterns. Feature importance from tree-based models can be unstable across seeds and hyperparameters. M0 identifies candidate risk factors, not confirmed causal mechanisms.

### 3.5 Dynamic Enablement Hypothesis Verdict

**The hypothesis has a coherent structure and suggestive evidence, but is not confirmed.**

| Assessment Dimension | Status | Confidence |
|---------------------|--------|------------|
| Coherent regime description exists | Yes — low-slope, low-volatility, moderate-slope uptrend | Medium |
| Regime features are ex-ante observable | Yes — all computable from OHLCV | High |
| Regime boundary is quantified | Partially — ATR 0.625 vs 0.531, single data window | Low |
| Trade-level classification works | No — H3a found feature overlap, no usable threshold | High (negative) |
| Module-level classification tested | No — H0 tested one implementation (EMA250/200), failed | N/A (untested) |
| OOS validation of regime boundary | No — regime boundary defined in-sample only | N/A (unvalidated) |
| 2021 OOS explained by regime | Partially — high-slope/high-volatility sub-regimes, but co-occurred with favorable sub-regimes | Low-Medium |

**The critical gap:** The only tested regime gate implementation (H0: EMA250/200) failed. The only tested trade-level classification (H3a) failed due to feature overlap. The suggestive regime signals (M0 ecology, ATR difference) have not been tested as an actionable gate. The hypothesis remains at the "worth investigating" level, not the "likely to work" level.

---

## 4. Existing Risk-State Clues — Document Review

This section reviews existing evidence on each named risk feature. No new experiments are run.

### 4.1 ema_4h_slope

**M0 finding (E-ECO-001):** Tier 1 feature. PnL spread: 12,899 USDT. Low slope → +656; high slope → -12,243. The single strongest diagnostic feature.

**Paradox for enablement:** 2023 had *lower* ema_4h_slope (0.115) than 2024/2025 (0.139). This means slope alone does not separate 2023 from the good years. Slope separates good trades from bad trades within each year (low-slope periods profit, high-slope periods lose), but the year-level averages point the wrong direction.

**E-FILT-001:** E1 (ema_4h_slope filter) failed under M1b parity — over-filters, kills 2024/2025 trades.

**Conclusion:** Strong trade-level diagnostic. Weak year-level regime separator. As a hard filter, already tested and failed.

### 4.2 recent_72h_return

**M0 finding (E-ECO-001):** Tier 1 feature. PnL spread: 12,545 USDT. Low return → +990; high return → -11,555.

**Paradox for enablement:** 2023 had *lower* recent_72h_return (0.035) than 2024/2025 (0.050). Same paradox as slope — the feature separates within-year but not across years.

**Conclusion:** Strong trade-level diagnostic. Not a year-level regime separator.

### 4.3 realized_volatility_24h

**M0 finding (E-ECO-001):** Tier 1 feature. PnL spread: 10,381 USDT. Low vol → -397; high vol → -10,778.

**No paradox:** 2023 had higher ATR percentile (0.625) than 2024/2025 (0.531). This is consistent with volatility as the primary regime separator.

**However:** No volatility-based regime gate has been tested as an actionable filter or enable/disable condition. The ATR filter is frozen as disabled in the current baseline.

**Conclusion:** Most promising regime-level signal. Untested as an actionable gate.

### 4.4 distance_to_donchian_20_high

**M0 finding (E-ECO-001):** Tier 1 feature. PnL spread: 12,337 USDT. Mid distance → +654; near top → -11,682.

**E4 (donchian_distance) filter trajectory:**

| Test | Environment | Result | Key Finding |
|------|-------------|--------|-------------|
| M1 (proxy) | Single-position sequential | PASS | 2023 loss reduction 71.3%; MaxDD 18.04% |
| M1b (parity) | Single-position sequential, aligned params | PASS | 3yr PnL improvement +6,191 (41.6%) |
| P0 (official) | Concurrent positions, compounding | **FAIL** | 3yr PnL deterioration 150.8%; 2024/2025 converted from profitable to losing |

**Why P0 failed:** E4 filtered 70.3% of all trades. In the official backtester with concurrent positions and compounding, each filtered-out profitable trade in 2024/2025 had outsized negative impact on the equity curve. The filter's over-aggressive behavior was masked in single-position proxy engines.

**E-FILT-004:** "E4 is an effective risk factor (correctly identifies high-loss regimes) but over-filters as a hard binary gate." E4's value as a risk-state label or position-weight factor is explicitly not ruled out by P0 failure.

**Conclusion:** Proven effective as a risk-state signal. Proven failed as a hard binary gate. The distinction between hard filter and soft risk-state label has never been tested. This is the most explicitly preserved research thread from the existing evidence.

### 4.5 ATR / Volatility State

**M0 year-level finding:** ATR percentile in 2023 was 0.625 vs 0.531 in 2024/2025. This is the only year-level feature where the "bad year" and "good years" point in the expected direction (higher volatility = worse CPM-1 performance).

**Scope note (Section 6, Not-Applicable Market):** "High-volatility regimes: ATR percentile above ~0.6 (2023-like conditions)" is listed as not-applicable.

**ATR filter status:** Frozen as disabled. Was validated as redundant under the previous (broader) applicable market definition. Under the narrower regime-aware framing, its status may differ — but this has not been tested.

**Conclusion:** The most promising single-feature regime separator at the year level. Untested as an actionable gate.

### 4.6 Donchian-Distance / E4 as Risk Label (Not Hard Gate)

**P0 official validation (E-FILT-003/004):** E4 fails as a hard gate but is an effective risk factor. The evidence interpretation note explicitly states: "E4's value as a risk-state label or position-weight-reduction factor is not ruled out; only hard-gate usage is rejected."

**No research has tested E4 as a soft risk label.** The entire M1/M1b/P0 research arc treats E4 as a binary on/off gate. The concept of using donchian_distance as a graduated input (position sizing, confidence scoring, multi-factor weighting) exists only as a stated future possibility, not as tested evidence.

**CPM-1 scope note (Section 7, Future treatment candidates):** "E4 (donchian_distance) as risk-state label / position-weight-reduction factor (not hard gate)" is listed as a future treatment candidate requiring owner decision.

### 4.7 Risk-State Clues Summary

| Feature | Trade-Level Diagnostic | Year-Level Separator | Tested as Gate | Result |
|---------|----------------------|---------------------|----------------|--------|
| ema_4h_slope | Strong (Tier 1) | Weak (2023 lower than 2024/25) | Yes (E1 hard filter) | FAIL |
| recent_72h_return | Strong (Tier 1) | Weak (2023 lower than 2024/25) | No | — |
| realized_volatility_24h | Strong (Tier 1) | Promising (2023 higher) | No (ATR filter frozen disabled) | — |
| distance_to_donchian_20_high | Strong (Tier 1) | Unknown | Yes (E4 hard filter) | FAIL as hard gate; risk-label untested |
| ATR percentile (aggregate) | — | Promising (0.625 vs 0.531) | No | — |

**Key finding:** The two features that separate years (volatility-related: realized_volatility_24h, ATR percentile) have not been tested as actionable gates. The two features that have been tested as gates (ema_4h_slope via E1, donchian_distance via E4) failed. The untested features are the most promising for module-level enablement, but the tested features' failure provides no confidence that untested ones will succeed.

---

## 5. Hard Filter vs Soft Enablement

### 5.1 Taxonomy

| Mechanism | Definition | CPM-1 Status | Allowed in This Task |
|-----------|-----------|--------------|---------------------|
| Hard filter | Binary: skip trade if condition met | E1 (slope) FAIL; E4 (Donchian) FAIL as hard gate | May discuss; not implement |
| Module validity gate | Binary: enable/disable entire module for a period based on regime | Untested (H0 tested one implementation, failed) | May discuss; primary research question |
| Position weight reduction | Graduated: reduce exposure when risk-state elevated | Untested (E4 mentioned as candidate) | May discuss; not design |
| Portfolio / router | Multi-module capital allocation across regimes | Not applicable | **Not allowed** |

### 5.2 What Has Been Tested

Only **hard filters** (trade-level binary gates) have been tested:

- E1 (ema_4h_slope): FAIL — over-filters, kills good trades.
- E4 (donchian_distance): FAIL as hard gate in P0 official — over-filters under compounding.

One **module-level gate** was tested:

- H0 (EMA250/200 coarse regime gate): FAIL — "coarse classification kills good-year trades."

### 5.3 What Has Not Been Tested

| Mechanism | Specific Implementation | Why It Might Differ from Failures |
|-----------|------------------------|----------------------------------|
| Module gate via ATR percentile | Rolling 90-day ATR percentile > threshold → disable | ATR is the only year-level separator; not tested as gate |
| Module gate via composite M0 score | Multi-feature regime score from M0 ecology features | Combines weak individual signals into potentially stronger composite |
| E4 as soft risk label | donchian_distance → position weight (0.0–1.0) | Avoids binary over-filtering; preserves partial exposure |
| Module gate via volatility regime | Realized vol 24h rolling percentile | Directly targets the feature M0 identifies as most different across years |

### 5.4 Why Hard Filter Failure Does Not Preclude Module Gate Success

Hard filters operate at trade level: they block individual signals based on entry-time features. Module gates operate at regime level: they enable/disable the entire module for extended periods based on rolling market state.

These are structurally different:

- A hard filter must distinguish good trades from bad trades within the same regime (H3a showed this fails due to feature overlap).
- A module gate must distinguish regimes (favorable vs unfavorable periods), not individual trades. Even if individual trades within a regime have mixed outcomes, the regime-level aggregate may be positive or negative.

**However:** H0's failure demonstrates that module-level gates are not automatically easier. A gate that is too coarse kills good periods along with bad ones.

### 5.5 Current Scope Constraint

This task allows discussing hard filters and module validity gates. It does **not** allow designing position weight reduction or portfolio/router systems. Discussion of soft enablement is limited to conceptual framing; no implementation design is in scope.

---

## 6. Relationship to MTC Directions

### 6.1 CPM-1 Is a Pullback Module

CPM-1's structural identity is trend-pullback-continuation. It asks: "Has the pullback within an uptrend ended?" It enters on candle morphology (Pinbar) at the pullback termination point.

### 6.2 Direction C Is Volatility Contraction / Re-Expansion

Direction C (MTC-003) asks a different question: "Has volatility contracted within an established trend, and is it re-expanding in the trend direction?" It enters on range expansion after compression, not on pullback ending.

**Key structural differences:**

| Dimension | CPM-1 (Pullback) | Direction C (Contraction) |
|-----------|------------------|--------------------------|
| Entry trigger | Candle pattern at pullback end | Range expansion after compression |
| What it filters for | Candle morphology | Volatility state |
| Retracement required | Yes — price must pull back | No — contraction can occur without retracement |
| Timeframe focus | 1h with 4h MTF | 4h primary |
| Trend context | Assumed (EMA/MTF context) | Required (established trend) |

**CPM-1 must not be reframed as Direction C.** They address different structural questions with different mechanisms.

### 6.3 Direction D Is Structured Pullback / Value-Zone

Direction D (MTC-002, SCDM-001) asks: "Has price retraced to a value zone (EMA zone, structure level) within a trend and resumed?" It is the closest structural relative to CPM-1 but replaces candle morphology with zone-based entry.

**Key guard:** "Direction D must not become CPM-style pullback-continuation. The value zone must be defined within a 4h trend context, not as a standalone 1h pullback pattern."

### 6.4 CPM-1 in a Multi-Module Context

In a future multi-module system, CPM-1 could serve as one candidate module among several, each operating in its applicable regime:

- **CPM-1 (pullback continuation):** Applicable in gentle, low-volatility uptrends with shallow pullbacks.
- **Direction C (volatility contraction):** Applicable in consolidation phases within trends.
- **Direction D (value-zone pullback):** Applicable when structured support/resistance levels exist within trends.

This multi-module framing is the conceptual home for the Dynamic Enablement Hypothesis. CPM-1 is not "the strategy that must work in all markets" but "one module that works in its specific market."

**However:** No multi-module routing, portfolio allocation, or strategy switching mechanism is in scope. The current question is only whether CPM-1's applicable regime can be identified ex-ante.

---

## 7. Level 3 Recommendation

### 7.1 Evidence Summary for Recommendation

**Evidence supporting Level 3:**

| # | Evidence | Weight |
|---|----------|--------|
| S1 | M0 ecology shows clear regime separation (4 Tier 1 features, PnL spreads >10k USDT) | Medium — proxy model, not causal |
| S2 | ATR percentile separates 2023 (0.625) from 2024/2025 (0.531) | Medium — single data window, in-sample |
| S3 | 2024/2025 show coherent positive performance (Sharpe ~2.0, WR ~32%) | Medium — in-sample, not OOS |
| S4 | E4 is explicitly preserved as risk-state-label candidate (not ruled out by P0 failure) | Medium — untested as label |
| S5 | Owner reframing permits conditional module enablement | High — governance shift |
| S6 | Volatility-related features (untested as gates) are the most promising year-level separators | Low-Medium — untested |

**Evidence against Level 3:**

| # | Evidence | Weight |
|---|----------|--------|
| N1 | 2021 OOS: signal-level failure in favorable regime (gross edge negative) | **High** — directly challenges profit hypothesis |
| N2 | H3a: trade-level feature overlap between good and bad years | **High** — no usable threshold exists |
| N3 | H0: coarse regime gate (EMA250/200) fails — kills good-year trades | **High** — only tested module gate failed |
| N4 | P0: E4 hard gate fails under official backtester | Medium — hard gate only, not soft label |
| N5 | Positive evidence (2024/2025) is entirely in-sample | Medium — no OOS validation of the positive regime |
| N6 | Only 3 year-level data points (2023, 2024, 2025) for regime boundary definition | Medium — inherently fragile |

### 7.2 The 2021 Problem

The 2021 OOS failure is the most serious counter-evidence. It shows that even within a bull year (structurally favorable), CPM-1 can produce signal-level failure with negative gross edge. The failure is concentrated in high-slope, high-volatility sub-regimes (M0 ecology finding, OOS failure classification Q10).

**Implication for Dynamic Enablement:** A module-level regime gate that disables CPM-1 during high-volatility periods would have avoided the 2023-style losses. But would it have avoided the 2021 losses? The 2021 losses concentrated in Aug–Oct (post-ATH decline, high volatility) and Feb–Mar (correction, moderate volatility). A volatility gate might have caught Aug–Oct but potentially not Feb–Mar.

More critically: the 2021 profitable months (Jan, Apr, Jul) occurred in "gentle uptrend" sub-regimes. A module gate that disables for "high volatility" must preserve these gentle periods. H0's failure shows this balance is non-trivial.

### 7.3 Recommendation

**RECOMMEND_LEVEL_3_INSPECT_RUN** — with the following specific framing:

A single frozen diagnostic run to test whether a **module-level volatility regime gate** can separate CPM-1's applicable market (2024/2025-like gentle uptrends) from its non-applicable market (2023-like high-volatility, 2021-like aggressive sub-regimes) using only ex-ante observable conditions.

**Rationale for Level 3 (not Reject):**

1. The regime description is coherent and the features are ex-ante observable (S1, S2, S6).
2. The most promising features (volatility-related) have not been tested as actionable gates. The tested gates (E1 slope, E4 Donchian, H0 EMA250/200) used different features or different mechanisms.
3. E4 is explicitly preserved as a research thread by existing governance (S4).
4. Owner's reframing creates a legitimate research question that the existing evidence does not close (S5).
5. A single frozen diagnostic can produce a definitive answer: if the gate works, the hypothesis gains support; if it fails, the hypothesis is closed.

**Rationale for Level 3 (not Proceed):**

1. 2021 OOS failure directly challenges the profit hypothesis (N1).
2. H3a feature overlap undermines trade-level classification confidence (N2).
3. H0 module-gate failure shows the approach is non-trivial (N3).
4. All positive evidence is in-sample (N5).

### 7.4 Level 3 Constraints (If Authorized)

If Owner authorizes Level 3, the following constraints must apply:

| Constraint | Rationale |
|-----------|-----------|
| Single frozen diagnostic run | Not a parameter sweep or iterative search |
| Official backtester (v3_pms) | P0 showed proxy engines mask compounding effects |
| Module-level gate only (not trade-level filter) | H3a showed trade-level classification fails; module-level is the untested path |
| Pre-registered gate definition | Gate must be defined before seeing results to prevent post-hoc fitting |
| Features must be ex-ante observable | Rolling window computations only; no look-ahead |
| Acceptance criteria pre-registered | Define PASS/FAIL before run; no retroactive reinterpretation |
| No parameter changes to CPM-1 baseline | Gate is external to the frozen strategy; baseline parameters remain locked |
| Results do not automatically change runtime | Diagnostic only; Owner decides next state |

### 7.5 Suggested Level 3 Scope (If Authorized)

**Hypothesis to test:** A module-level gate based on rolling realized volatility or ATR percentile can disable CPM-1 during unfavorable regimes (2023, high-volatility 2021 sub-periods) without disabling it during favorable regimes (2024, 2025, low-volatility 2021 sub-periods).

**Candidate gate features (pre-registered):**

1. Rolling 90-day ATR percentile on ETH 1h (threshold TBD, but must be set before run).
2. Rolling 90-day realized volatility percentile (alternative to ATR).
3. Composite: ATR percentile + ema_4h_slope (multi-feature regime score).

**Acceptance criteria (pre-registered):**

- 2023 net PnL must improve vs baseline (reduced loss, not necessarily positive).
- 2024 net PnL must not deteriorate by more than 15% vs baseline.
- 2025 net PnL must not deteriorate by more than 15% vs baseline.
- 2021 net PnL must improve vs baseline (reduced loss).
- Trade count in favorable years must remain above 40 positions/year.
- 3-year aggregate (2023–2025) must improve vs baseline.

**If all criteria pass:** Hypothesis gains support. Consider further validation (OOS on 2020, longer observation).
**If any criterion fails:** Hypothesis is weakened. If 2024/2025 sacrifice exceeds tolerance, close the dynamic enablement path for CPM-1.
**If all fail:** Close the dynamic enablement path. CPM-1 remains paused with boundary-cost classification.

---

## 8. Owner Summary

### 8.1 Is CPM-1 Worth Studying as an Enable/Disable Module?

**Yes, with significant caveats.** The M0 ecology evidence provides a coherent regime description (low-slope, low-volatility uptrends) and identifies specific ex-ante observable features. The 2024/2025 positive evidence demonstrates that the mechanism works in this regime. The question is whether the regime can be reliably identified and gated ex-ante — this has not been tested.

The caveats are serious: 2021 OOS failure challenges the profit hypothesis even in favorable conditions; H3a found trade-level feature overlap; H0's coarse regime gate failed. The hypothesis is suggestive, not strong.

### 8.2 Meaning of 2024/2025 Evidence

2024/2025 are **applicable-market evidence**: they demonstrate that CPM-1's pullback-continuation mechanism produces positive expectancy in a specific regime (gentle, low-volatility uptrends). They are not deployment permission. They cannot be used to justify live trading, small-live candidacy, or parameter changes. They can be used to justify asking whether the regime is identifiable and gateable.

### 8.3 Is 2023 Still a Boundary Cost?

**Yes, and this is confirmed, not changed by this inspect.** Five rescue experiments (H0–H3a) exhausted all reasonable adjustment dimensions. 2023 is a regime-mismatch cost. The Dynamic Enablement framing does not "fix" 2023 — it asks whether 2023-like conditions can be identified ex-ante so the module can be disabled during them.

### 8.4 Are There Ex-Ante Identifiable Enable/Disable Condition Clues?

**Suggestive clues exist, but no confirmed actionable condition.**

- **Most promising clue:** ATR percentile / realized volatility. 2023 ATR percentile (0.625) vs 2024/2025 (0.531) is the only year-level feature where the direction is correct. This has never been tested as an actionable gate.
- **Tested and failed clues:** E1 (ema_4h_slope hard filter) — FAIL. E4 (donchian_distance hard gate) — FAIL. H0 (EMA250/200 coarse gate) — FAIL.
- **Untested clue:** E4 as a soft risk-state label (not hard gate). Explicitly preserved by P0 failure classification.
- **Structural limitation:** Only 3 year-level data points. Any regime boundary is inherently fragile and unvalidated OOS.

### 8.5 Level 3 Recommendation

**RECOMMEND_LEVEL_3_INSPECT_RUN** — one frozen diagnostic testing a module-level volatility regime gate against pre-registered acceptance criteria.

This is the minimum viable test of the Dynamic Enablement Hypothesis. If it passes, the hypothesis gains credibility and warrants further validation. If it fails, the hypothesis is closed for CPM-1 and the module remains paused with boundary-cost classification.

### 8.6 Next Steps and Prohibitions

**Recommended next steps:**

1. Owner reviews this inspect document and decides whether to authorize Level 3.
2. If authorized: create a Level 3 inspect plan with pre-registered gate definition, features, thresholds, and acceptance criteria.
3. If not authorized: CPM-1 remains paused. Dynamic Enablement path is closed. No further CPM-1 research unless Owner reopens.

**Prohibitions (remain active):**

| Prohibition | Status |
|-------------|--------|
| No parameter changes to CPM-1 baseline | Active |
| No E4 hard filter experiment | Active |
| No parameter sweep | Active |
| No CPM-2 activation | Active |
| No strategy router design | Active |
| No portfolio engine | Active |
| No runtime/profile/risk/backtester core modification | Active |
| No live enablement or small-live approval | Active |
| No interpreting 2024/2025 as deployment permission | Active |
| No rescuing 2023 through parameter tuning | Active |

---

## 9. Evidence Source Registry

| Evidence ID | Source Document | Key Finding Used |
|------------|----------------|------------------|
| E-PERF-001 | External Quant Review §2 | 2024: +8,501; 2025: +4,490 |
| E-PERF-002 | External Quant Review §2 | 2023: -3,924 (WR 16.1%, MaxDD 49.19%) |
| E-PERF-003 | External Quant Review §2 | Aggregate 3yr: +9,067, Sharpe 0.31 |
| E-ECO-001 | M0 Strategy Ecology Map | 4 Tier 1 features; counter-trend classification |
| E-ECO-002 | M0 Strategy Ecology Map | ATR percentile: 2023=0.625, 2024/25=0.531 |
| E-FILT-001 | M1b Parity Report | E1 (ema_4h_slope): FAIL |
| E-FILT-003 | P0 Official Validation | E4 (donchian_distance): FAIL as hard gate |
| E-FILT-004 | P0 Official Validation | E4 effective risk factor, not ruled out as soft label |
| E-RES-001 | 2023 Rescue Closure | H0 (EMA250/200): FAIL |
| E-RES-005 | 2023 Rescue Closure | H3a: feature overlap, no usable threshold |
| — | CPM-OOS-FAILURE-CLASSIFY-001 | 2021: favorable-regime profit hypothesis failure |
| — | CPM-1 Scope Note | Module identity, frozen baseline, applicable market |
| — | MTC-003 | Direction C definition; CPM boundary table |
| — | MTC-002 | Direction D definition; closed directions |

---

## 10. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-07 | Initial CPM-MOD-001 inspect document | Claude Code (CPM-MOD-001) |
