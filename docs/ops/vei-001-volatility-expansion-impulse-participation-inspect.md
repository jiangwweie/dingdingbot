# VEI-001: Volatility Expansion / Impulse Participation Inspect

**Task ID:** VEI-001
**Level:** 1/2 docs-only inspect
**Date:** 2026-05-07
**Status:** COMPLETE
**Classification:** MARGINAL — conditional RECOMMEND_LEVEL_2_FROZEN_EXPERIMENT_PLAN with heavy caveats

---

## 1. Context

### Why This Inspect Exists

SRD-002 ranked "volatility expansion / impulse participation" as the next non-pullback direction to inspect after:
- Direction A (Donchian20 + EMA60) → PAUSE_FRAGILE
- Direction C (volatility contraction / re-expansion) → INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE
- Direction D (structured pullback) → REJECTED_FROZEN_BASELINE
- Short-side breakdown continuation (SSD-003) → REJECTED_FROZEN_BASELINE
- CPM-1 (pullback module) → paused, not runtime, not small-live
- CPM-MOD-002 (volatility regime gate) → HYPOTHESIS_STRENGTHENED but 2023 unexplained
- Pullback-continuation family → lower priority, all paused

SRD-002 identified VEI as Rank 1, noting it must define impulse using "a concept other than Donchian breakout or contraction/resumption."

### Upstream State

- No runtime candidate exists.
- No deployable small-live strategy.
- Small-live readiness gate: NOT MET.
- Live-safe foundation has been substantially completed; however, live-safe completion does not equal strategy readiness. No runtime candidate / deployable small-live strategy currently exists; the small-live readiness gate remains unmet.
- CPM-1 failed OOS gate; frozen and paused.
- All prior directions show: top-winner fragility, year instability, cost drag, no validated pre-observable applicability boundary.

---

## 2. Concept Definition

### What Is "Impulse Participation"?

**Core idea:** Detect a volatility expansion event on a 4h bar and enter to capture the directional continuation (follow-through) that follows a high-energy impulse bar.

**Notation:**
- "Impulse bar": a 4h bar where (High - Low) significantly exceeds the recent N-bar average range, AND the close is located in the upper portion of the bar (for longs) indicating directional control.
- "Follow-through": the next 4h bar closes in the same direction as the impulse bar's close, confirming the impulse has continuation energy rather than exhaustion.

### Structural Mechanism (OHLCV-Only Candidate)

| Component | Definition | Data Source |
|-----------|-----------|-------------|
| Volatility expansion detection | Current bar range > K × rolling N-bar average range | OHLCV (High-Low, SMA of ranges) |
| Close location filter | Close in upper P% of bar range (long) | OHLCV (Close, High, Low) |
| Follow-through confirmation | Next bar close > impulse bar close (long) | OHLCV |
| Entry | Open of bar after follow-through confirmation | OHLCV |
| Trend context (optional) | Price above EMA-N | OHLCV |

**Critical design choice:** This mechanism enters on an impulse bar with follow-through, NOT at a Donchian channel breakout and NOT after a contraction-then-re-expansion cycle.

### What This Is NOT

| Concept | Why VEI Is Not This |
|---------|-------------------|
| Direction A rescue | Direction A enters at Donchian20 high breakout; VEI enters at bar-level impulse detection. Different trigger. |
| Direction C rescue | Direction C waits for ATR ratio to contract below 0.7 then re-expand above 1.2x; VEI detects raw expansion from recent baseline, no contraction precondition. |
| Direction D / pullback | No value-zone touch, no pullback ending detection, no EMA reclaim confirmation. |
| CPM rescue | No Pinbar, no 1h entry, no fixed TP, no pullback-ending question. |

---

## 3. Profit Source Analysis

### Candidate Profit Sources

| Source | Description | Feasibility Assessment |
|--------|-------------|----------------------|
| **Directional impulse continuation** | Enter after high-energy bar; capture continuation move | Primary candidate. Requires distinguishing continuation from exhaustion. |
| Momentum ignition | Price movement triggers further buying/selling | Requires OI/liquidation data to confirm cascading liquidations. OHLCV-only cannot verify. |
| Volatility regime transition | Market shifting from low-vol to high-vol trending state | Partially observable in OHLCV (range expansion). But transition detection is what Direction C already tested. |

### Honest Assessment

The profit source is **directional impulse continuation**: participating in a move that has already started (detected via bar-level range expansion + close location) and has confirmation (follow-through bar) that it has continuation energy.

This is structurally a **trend participation** concept. Direction A also participates in trends, but through a different mechanism:
- **Direction A:** enters when price reaches the N-bar high (Donchian breakout) — price-level extreme detection
- **VEI:** enters when a bar shows volatility expansion with directional close and follow-through — bar-level energy detection

**The profit source overlaps with Direction A at the conceptual level (both capture trend moves).** The question is whether the entry mechanism produces a structurally distinct signal set.

### Overlap Risk Assessment

| Scenario | Direction A Signal? | VEI Signal? | Overlap? |
|----------|-------------------|-------------|----------|
| Strong trend breakout to new high on expanding range | Yes | Yes | OVERLAP |
| New high on low-volatility drift (no impulse) | Yes | No (no expansion) | DISTINCT |
| Expanding-range impulse bar not at Donchian high | No | Yes | DISTINCT |
| Impulse bar that exhausts (spike + reversal) | No | Filtered by follow-through | N/A |
| Low-vol breakout above channel (Direction A only) | Yes | No | DISTINCT for Direction A |

**Estimated structural overlap: 40-60% depending on parameters.** This is below the 80% variant threshold but above the "clearly distinct" threshold of 20-30%.

**Verdict:** The profit source is real (participation in continuation after volatility expansion) but the entry mechanism is a **partial re-expression** of the same trend-capture intuition that powers Direction A, using bar-level energy instead of price-level extremes.

---

## 4. Old-Path Drift Assessment

### Direction A Drift Check

**Test:** Is VEI just "Direction A with a volatility filter"?

**Analysis:**
- Direction A enters at Donchian20 high. VEI enters at impulse bar + follow-through. Different trigger object.
- BUT: when price breaks to a new high on an expanding-range bar, both fire. This is the dominant overlap case.
- If VEI's top winners are a subset of Direction A's top winners, VEI adds no independent signal value.
- If VEI adds signals that Direction A misses (expansion bars not at channel extremes), those must be independently profitable.

**Drift risk: MEDIUM-HIGH.** The most likely profitable overlap scenario (strong trending breakout) is where both directions fire. The distinct scenarios (expansion not at extremes) may be noise-driven.

**Required gate:** Direction A signal overlap must be measured. If >50%, classify as "Direction A partial variant" and stop.

### Direction C Drift Check

**Test:** Is VEI just "Direction C with different thresholds"?

**Analysis:**
- Direction C: ATR ratio < 0.7 (contraction) → ratio > 1.2x (re-expansion) → enter.
- VEI: range expansion > K × recent baseline → close in upper P% → follow-through → enter.
- Both detect "volatility expands from a quiet baseline." The precondition differs: Direction C requires prior contraction, VEI does not.
- If VEI fires without a prior contraction period (i.e., volatility was already moderate), it's structurally distinct from C.
- If VEI's signals cluster in the same bars that Direction C would fire, drift is confirmed.

**Drift risk: MEDIUM.** The "expansion from baseline" component is shared DNA. The distinction (no mandatory contraction phase) is real but thin.

**Required gate:** Direction C signal overlap must be measured. If >50%, reclassify.

### Pullback-Continuation Drift Check

**Test:** Does VEI implicitly wait for a pullback ending?

**Analysis:**
- VEI enters ON the impulse bar (or next bar), not after a pullback to a value zone.
- No EMA reclaim, no zone touch, no Pinbar, no pullback-ending detection.
- The follow-through confirmation is a directional bar, not a pullback resumption.

**Drift risk: LOW.** VEI is structurally non-pullback as long as the entry rule does not incorporate any pullback-detection component.

### Combined Drift Risk

| Drift Vector | Risk Level | Gate |
|-------------|-----------|------|
| Direction A variant | MEDIUM-HIGH | Signal overlap < 50% |
| Direction C variant | MEDIUM | Signal overlap < 50% |
| Pullback-continuation | LOW | Entry rule must not contain pullback detection |
| Direction D rescue | LOW | No EMA zone / resumption logic |
| CPM rescue | LOW | No Pinbar / 1h / fixed TP |

**Overall old-path drift risk: MEDIUM-HIGH.** The concept lives in the same neighborhood as Direction A and Direction C. Structural distinctness depends entirely on empirical signal overlap, which cannot be assessed without a Level 3 run.

---

## 5. Direction Scope

### Long-Only vs Short-Only vs Directional-Agnostic

| Option | Pros | Cons | Assessment |
|--------|------|------|-----------|
| Long-only | Aligns with existing positive evidence (Direction A long-only, positive); lower complexity | Risk: just another long-side trend capture variant | DEFAULT |
| Short-only | Would be genuinely distinct from all prior work | SSD-003 short-side was rejected; no positive evidence base; higher failure risk | NOT NOW |
| Directional-agnostic (both sides) | Captures impulse in both directions | Requires router/regime layer to decide direction; explicitly forbidden by task constraints | STOP |

**Decision: Long-only.** Rationale:
1. Direction A long-only has the only positive (though fragile) evidence base.
2. Short-side breakdown was rejected (SSD-003); no positive short-side evidence exists.
3. Two-sided requires router/regime, which is explicitly out of scope.
4. Long-only keeps the signal set smaller, making fragility assessment cleaner.

**Caveat:** If VEI long-only passes Level 2, short-side could be a separate future inspect. Not in this task.

---

## 6. Timeframe Scope

### 4h as Primary

The 4h timeframe is the primary concept level for all prior directions. VEI operates at 4h because:
- Impulse detection (range expansion) is meaningful at 4h (8-16 candles per day).
- Follow-through confirmation on the next 4h bar provides a natural confirmation delay.
- All prior frozen baselines use 4h; consistency enables overlap measurement.

### 1h Role

1h is explicitly **excluded from VEI-001**. Per LTF-001 and LTF-002:
- 1h cannot independently produce direction.
- 1h is a candidate execution-timing layer under a frozen 4h thesis.
- VEI-001 is a concept inspect, not an entry-timing search.

**1h is a future consideration only if VEI 4h passes Level 2.** Any 1h work requires a separate task with LTF-002 caveat handling.

### 15m Role

15m is **out of scope**. Not considered, not referenced, not used.

---

## 7. Data Dependency

### OHLCV Sufficiency for Level 1/2

| Mechanism Component | OHLCV Available? | Notes |
|-------------------|-----------------|-------|
| Bar range (High - Low) | Yes | |
| Rolling N-bar average range | Yes | SMA of (H-L) |
| Close location value | Yes | (Close - Low) / (High - Low) |
| Multi-bar directional move | Yes | Rolling sum of returns |
| Follow-through bar | Yes | Next bar Close vs impulse bar Close |
| EMA trend context | Yes | Close-based EMA |
| ATR percentile | Yes | Derived from OHLCV |

**All Level 1/2 concept components are computable from 4h OHLCV.** Current data covers 2020-01 through 2026-03 (v3_dev.db klines table).

### Data That Would Improve the Concept (Future)

| Data | Potential Value | Current Status |
|------|----------------|---------------|
| Funding rate | Distinguish liquidation-driven impulse from organic impulse | No pipeline authorized (BACKLOG) |
| Open interest change | Confirm if expansion is new positioning vs. liquidation cascade | No pipeline authorized (BACKLOG) |
| Liquidation data | Directly measure cascading stops / forced selling | No pipeline authorized (BACKLOG) |
| Taker buy/sell ratio | Confirm directional aggression | No pipeline authorized (BACKLOG) |

### Data Classification

**VEI concept: OHLCV-only is sufficient for Level 1/2 inspect and a possible Level 2 frozen experiment.**

The concept does NOT require new data for its core mechanism. Funding/OI would enhance but are not prerequisites. If the OHLCV-only concept fails, adding data is a separate hypothesis, not a rescue of this one.

---

## 8. Applicability and Failure Boundaries

### Pre-Observable Applicability States

An impulse participation strategy should work in markets where:

| Applicability State | Observable Indicator | Direction A? | Direction C? |
|-------------------|---------------------|-------------|-------------|
| Volatility expansion from low baseline with directional follow-through | Range > K×avg AND close location AND next-bar continuation | Captures via Donchian (price extreme) | Captures via contraction/expansion (ATR ratio) |
| Strong trending market start (first impulse) | Expansion bar after quiet period | Partially (if at channel high) | Partially (if preceded by contraction) |
| High-energy directional move | Large range bar, directional close | Via price extreme | Via ATR re-expansion |

**The applicability states overlap significantly with Direction A and C.** VEI's distinctness comes from the trigger mechanism (bar-level), not from a distinct market state.

### Pre-Observable Failure States

| Failure State | Observable Before Entry | Impact |
|--------------|------------------------|--------|
| **Exhaustion spike** | Large impulse bar + next bar reversal (close < open, counter-direction) | Follow-through filter should catch this. If follow-through bar also fails (spike-reversal-spike), still lose. |
| **Liquidation wick reversal** | Long lower wick on impulse bar, close near mid-bar | Close-location filter should reject. But wick + close-high scenario is ambiguous. |
| **Low-volatility false expansion** | Very low recent average range makes normal bars look like "expansion" | Parameter sensitivity: if N-bar avg range is too low, false signals increase. |
| **Drift into Direction A overlap** | Top winners are Direction A top winners | Structural: no independent value added. |
| **Year concentration** | Positive PnL concentrated in 1-2 years | Structural: same as all prior directions. |
| **Cost drag** | Gross PnL < execution costs | High-frequency signals with low win rate. |
| **Top-winner fragility** | Removing top 1/3/5 winners turns system negative | Structural to all sparse-trend-capture strategies. |

### Parameter Sensitivity Risks

| Parameter | Risk | Mitigation |
|-----------|------|-----------|
| Expansion threshold K | Too low = too many signals (noise); too high = too few (fragility) | One frozen value; no sweep |
| Lookback period N | Too short = volatile baseline; too long = slow adaptation | One frozen value; no sweep |
| Close location P% | Too loose = exhaustion bars pass; too tight = misses moves | One frozen value; no sweep |
| Trend EMA period | If included: too short = noise; too long = lag | Optional; if used, one frozen value |

**The number of parameters (3-4) creates a moderate overfitting risk.** Each parameter choice narrows or widens the signal set significantly. This is a genuine concern and must be flagged as a failure mode.

---

## 9. Specific Failure Scenarios

### Scenario A: Concept Is Direction A Variant (>50% Signal Overlap)

**What happens:** Top winners overlap with Direction A. Net PnL after removing overlapping winners is negative. VEI adds no independent value.

**Implication:** Closes the hypothesis that "bar-level impulse detection is a distinct profit source from price-level breakout detection."

### Scenario B: Concept Is Direction C Variant (>50% Signal Overlap)

**What happens:** VEI fires in the same bars Direction C would fire. The "no contraction precondition" distinction is empirically irrelevant.

**Implication:** Closes the hypothesis that "volatility expansion detection without contraction precondition is structurally different from contraction/re-expansion."

### Scenario C: Exhaustion Dominance

**What happens:** Many impulse bars reverse on the follow-through bar. The follow-through filter reduces signals but does not improve win rate. Net PnL negative.

**Implication:** Closes the hypothesis that "OHLCV-only impulse detection can distinguish continuation from exhaustion." Note: funding/OI data might help (different hypothesis), but VEI OHLCV-only is closed.

### Scenario D: Thin Evidence (Direction C Repeat)

**What happens:** Fewer than 55 trades or fewer than 15 winners. Top-1 > 70% of net. Cannot make meaningful fragility assessment.

**Implication:** Same as Direction C: INSUFFICIENT_EVIDENCE. Concept is too selective or the market provides too few impulse opportunities on 4h.

### Scenario E: Cost Drag

**What happens:** Gross PnL positive but costs exceed gross. Net negative. PF < 1.0.

**Implication:** Closes the hypothesis that "impulse continuation capture has enough edge per trade to overcome execution costs."

### Scenario F: Year Instability

**What happens:** 2021 positive, 2022 negative, 2023 negative, 2024 positive, 2025 negative (or similar pattern). No pre-observable boundary separates good years from bad.

**Implication:** Same failure mode as all prior directions. Does not uniquely close VEI but contributes to the meta-hypothesis that "OHLCV-only strategies on ETH 4h have no stable applicability."

---

## 10. Level 3 Pre-Conditions (Frozen Before Run)

If VEI passes Level 2 concept inspection and Owner authorizes Level 3, the following must be frozen before the run:

| Element | What Must Be Frozen |
|---------|-------------------|
| **Entry trigger** | Exact impulse detection formula (expansion threshold, lookback, close-location) |
| **Follow-through definition** | Exact confirmation bar rule |
| **Same-bar vs next-bar policy** | Enter on impulse-bar close or next-bar open |
| **Trend context** | Whether EMA filter is used; if so, exact period and rule |
| **Stop mechanism** | Fixed-bar, ATR-based, or swing-low stop |
| **Exit lifecycle** | Trailing stop, fixed hold, or trend-following exit |
| **Cost model** | 0.04% fee, 0.1% slippage, 0.01%/8h funding (frozen from prior baselines) |
| **Direction A overlap threshold** | <50% to maintain distinct classification |
| **Direction C overlap threshold** | <50% to maintain distinct classification |
| **Trade floor** | Minimum 55 trades |
| **Winner floor** | Minimum 15 winners |
| **Top-N fragility** | Top-1, top-3, top-5 removal analysis |
| **Year concentration** | Year-by-year PnL breakdown |
| **MFE/MAE** | Mean favorable/adverse excursion per trade |
| **MTM DD** | Mark-to-market max drawdown |
| **Funding caveat** | Constant funding approximation applied; documented as caveat |
| **Failure closure** | Defined in Section 11 below |

---

## 11. Failure Closure

### If Level 3 Fails, The Following Are Closed

| Closed Hypothesis | What It Means |
|------------------|---------------|
| Bar-level impulse detection is a distinct profit source from Direction A price-level breakout | If signal overlap >50% OR independent signals unprofitable |
| Volatility expansion without contraction precondition is structurally different from Direction C | If signal overlap >50% OR same failure pattern |
| OHLCV-only impulse can distinguish continuation from exhaustion | If follow-through filter does not save the concept |
| Impulse participation reduces top-winner fragility vs. existing directions | If top-N fragility is same or worse |

### If Level 3 Fails, The Following Are NOT Allowed

| Prohibited Follow-Up | Rationale |
|---------------------|-----------|
| Expansion threshold variants | Parameter rescue of failed concept |
| Lookback period variants | Parameter rescue |
| Close-location variants | Parameter rescue |
| Direction A breakout rescue | Old-path drift; concept was supposed to be distinct |
| Direction C re-expansion rescue | Old-path drift |
| Pullback-entry rescue | Concept was explicitly non-pullback |
| 1h/15m timing search | Timeframe scope creep; LTF-001/002 constraints |
| Funding/OI rescue | Different hypothesis; requires separate authorization |
| Router/portfolio/regime | Infrastructure, not strategy |
| Bearish/short-side mirror | Different direction scope; requires separate inspect |
| Trend EMA period sweep | Parameter rescue |

---

## 12. Relationship to Prior Directions

### Structural Comparison Matrix

| Dimension | Direction A | Direction C | VEI (proposed) |
|-----------|------------|------------|---------------|
| Entry trigger | Donchian20 high breakout | ATR ratio contraction → re-expansion | Bar range expansion + close location + follow-through |
| Price-level vs bar-level | Price-level (channel extreme) | Ratio-level (volatility state) | Bar-level (energy detection) |
| Requires prior contraction? | No | Yes (ATR < 0.7) | No |
| Requires channel breakout? | Yes (new 20-bar high) | No | No |
| Requires follow-through? | No (enters on breakout bar) | No (enters on re-expansion) | Yes (next-bar confirmation) |
| Pullback component | No | No | No |
| Direction A overlap | Self | 14.3% (measured) | Est. 40-60% (to be measured) |
| EMA trend context | EMA60 | EMA60 | Optional |
| Exit | EMA60 exit | EMA60 exit | TBD (frozen in Level 3) |

**Key distinction:** VEI uses bar-level energy detection (range + close location + follow-through) rather than price-level extremes (Direction A) or volatility ratio states (Direction C). Whether this distinction produces a meaningfully different signal set is an empirical question that cannot be answered at Level 1/2.

### What VEI Would Need to Prove

To be worth Level 3, VEI must demonstrate at Level 2:
1. The entry mechanism is definable without referencing Donchian channels, ATR contraction thresholds, or pullback zones.
2. The follow-through confirmation is a natural part of the concept (not an ad-hoc filter).
3. The concept does not require more than 4 parameters.
4. The estimated signal set is plausibly <50% overlapping with Direction A and Direction C.
5. The failure modes are pre-observable (exhaustion, cost drag, year instability, top-N fragility).

---

## 13. OHLCV Sufficiency Final Assessment

### Is OHLCV Enough?

**For Level 1/2 concept inspect: YES.** All components (range, close location, follow-through, EMA) are derivable from OHLCV.

**For a Level 2 frozen experiment plan: YES, with caveats.** The concept can be fully specified and its signal characteristics estimated from OHLCV alone.

**For a robust Level 3: MARGINAL.** OHLCV-only impulse detection cannot distinguish:
- Organic trend continuation from liquidation-driven cascades
- Momentum ignition from genuine directional shift
- High conviction moves from short-covering spikes

These distinctions require funding/OI/liquidation data, which is not authorized.

**Classification: OHLCV-only is sufficient for a limited Level 2 frozen experiment. If the OHLCV-only concept shows promise but fails on exhaustion/cost, a separate BACKLOG_DATA_DEPENDENT hypothesis can be registered for funding/OI-informed impulse detection.**

---

## 14. Classification Decision

### Evaluation Against SRD-001 Level 3 Admission Conditions

| Condition | Status | Notes |
|-----------|--------|-------|
| 1. Mechanism structure clear | PARTIAL | Entry mechanism defined; exit lifecycle TBD |
| 2. Structurally different from A, C, CPM-1, D, 15m | UNCERTAIN | Depends on signal overlap; plausibly 40-60% with A |
| 3. No parameter search | PASS | One frozen concept; no sweep |
| 4. Uses current OHLCV | PASS | |
| 5. Applicability boundaries pre-observable | PARTIAL | Defined conceptually; must be validated empirically |
| 6. Stop conditions explicit | PASS | Defined in Section 11 |
| 7. Information gain | MEDIUM | Would confirm/reject impulse distinctness hypothesis |
| 8. Failure closes hypothesis | PASS | Section 11 |
| 9. No runtime changes | PASS | |
| 10. Cannot be interpreted as runtime approval | PASS | |

### Final Classification

**RECOMMEND_LEVEL_2_FROZEN_EXPERIMENT_PLAN — with the following mandatory gates:**

1. **Direction A signal overlap < 50%** — if overlap ≥ 50%, reclassify as "Direction A partial variant" and stop.
2. **Direction C signal overlap < 50%** — if overlap ≥ 50%, reclassify as "Direction C partial variant" and stop.
3. **Both overlap checks must pass** for VEI to proceed as a distinct direction.
4. **Exit lifecycle must be frozen** at Level 2 before any Level 3 consideration.
5. **One frozen concept version** — no variants, no alternative trigger definitions, no parameter search.

**If gates pass:** VEI proceeds to a Level 3 frozen experiment (one frozen version, OHLCV-only, long-only, 4h, with all elements from Section 10 frozen).

**If gates fail:** VEI is classified as OLD_PATH_DRIFT and closed. No rescue variants.

### Alternative Classifications Considered

| Alternative | Why Not |
|-------------|---------|
| REJECT_AS_OLD_PATH_DRIFT | Too early — concept is structurally distinct at mechanism level; overlap must be measured empirically |
| BACKLOG_DATA_DEPENDENT | Data dependency is a future enhancement, not a prerequisite |
| PAUSE_UNCLEAR_BOUNDARY | Boundaries are definable; unclear element is signal overlap, which requires Level 3 |
| DO_NOT_CONTINUE | Would prematurely close the last non-pullback candidate direction |

---

## 15. Owner Summary

### 1. Continue VEI Direction?

**Yes, conditionally.** VEI is the last remaining non-pullback, non-old-rescue candidate direction in SRD-002's ranked list. Closing it without a Level 2 frozen experiment plan would leave the strategy research pipeline completely empty. However, the concept has MEDIUM-HIGH old-path drift risk and must pass Direction A and Direction C overlap gates before any Level 3.

### 2. Long-Only / Short-Only / Directional?

**Long-only.** Rationale:
- All existing positive evidence (Direction A, Direction C, CPM-1) is long-side.
- Short-side breakdown (SSD-003) was rejected.
- Two-sided requires router/regime (forbidden).
- Long-only keeps signal set smaller for fragility assessment.

### 3. OHLCV Sufficient?

**Yes for Level 1/2 and Level 2 frozen experiment.** All mechanism components are OHLCV-derivable. Funding/OI would enhance exhaustion detection but are not prerequisites. If OHLCV-only concept fails, funding/OI version is a separate hypothesis (BACKLOG_DATA_DEPENDENT).

### 4. Biggest Old-Path Drift Risk?

**Direction A variant drift.** The most profitable scenario for both Direction A and VEI is the same: strong trending breakout on expanding range. If VEI's top winners are Direction A's top winners, VEI adds no independent value. Signal overlap measurement is the critical gate.

### 5. Worth Level 2 Frozen Experiment Plan?

**Yes, with mandatory gates.** The concept is the last non-pullback candidate. It has a plausible mechanism (bar-level energy detection vs. price-level breakout). But it must pass the overlap gates to justify Level 3. The Level 2 plan should be a docs-only frozen spec, not a backtest.

### 6. Small-Live Readiness Gate?

**Still not met.** VEI-001 is a Level 1/2 concept inspect. Even if VEI proceeds through Level 2 and Level 3 successfully, it would be one frozen-baseline result — not a small-live candidate. The following remain unaddressed:
- No runtime candidate from any direction
- Live-safe P0: 5/7 tasks incomplete
- No validated pre-observable applicability boundary from any direction
- No exit lifecycle tested
- No cost-robust evidence base

**VEI-001 does not change the project's deployment readiness.** It is a research document that expands the direction map.
