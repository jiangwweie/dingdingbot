# MTC-003 — Direction C Volatility Contraction / Re-expansion Inspect v0

**Task ID:** MTC-003
**Date:** 2026-05-07
**Status:** Proposed / Direction Inspect Only
**Scope:** Docs-only direction inspect + minimal experiment plan draft
**Affects Runtime Automatically:** No
**Authorization Level:** Level 1/2 — inspect + docs-only plan; no execution

---

## 0. Boundary

This document inspects Direction C as a candidate Main Trend Capture
direction. It is a direction-level inspect and a proposed minimal experiment
plan only.

This document does not authorize:

- running experiments or backtests;
- writing code or creating adapters;
- implementing strategies;
- changing runtime profiles, risk rules, or backtester / research engine
  core;
- making promotion, small-live, or live deployment conclusions;
- parameter sweeps;
- data pipeline construction.

This task did not run backtests, write code, create adapters, implement
strategies, tune parameters, modify runtime, modify profiles, modify risk
rules, or touch `src/`, `configs/`, `tests/`, `migrations/`, production
strategy paths, or backtester / research engine core.

Inspected material:

- `docs/ops/strategy-candidate-direction-map-v1.md` (Direction C definition)
- `docs/ops/mtc-002-strategy-direction-map-refresh.md`
- `docs/ops/mtc-001-main-trend-capture-fragility-evaluation-framework-v0.md`
- `docs/ops/nsc-013-direction-a-4h-main-trend-lifecycle-clean-baseline-minimal-experiment-plan.md`
- `docs/ops/nsc-015-direction-a-pause-fragile-evidence-review.md`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/experiment_report.md`
- `docs/ops/project-roadmap-v2.md`

---

## 1. Current State

| Field | State |
|-------|-------|
| CPM-1 | Paused; not a small-live candidate |
| CPM-2 Candidate A/B | Closed; research proxy insufficient |
| Candidate C (CPM) | Reserve-only; not activated |
| Direction A (Donchian20 + EMA60) | PAUSE — Do not reopen |
| Direction B (4h + 1h entry timing) | Reserve; not executed |
| Direction E (overlay family) | Closed |
| Direction C (this inspect) | Inspect only |
| Direction D (value-zone entry) | Available for inspect |
| Deployable small-live candidate | None |
| Small-live readiness gate | Unmet |

---

## 2. Direction C Identity

### 2.1 What Direction C Is

Direction C is a Main Trend Capture direction that uses volatility
contraction as a structural entry condition within an established trend.

The core idea:

> Within a 4h trend that is already underway, volatility contracts
> (narrowing ranges, decreasing ATR, compressed price movement). This
> contraction represents a consolidation / energy-building phase. When
> volatility re-expands in the trend direction, the impulse phase begins.
> Enter on the re-expansion, not on the raw price breakout.

Direction C targets the **impulse phase after consolidation within a trend**.
It does not target the trend initiation (that is Direction A's domain) or
the pullback entry (that is CPM / Direction D territory).

### 2.2 What Direction C Is Not

- Not Direction A with a filter.
- Not a Donchian parameter variant.
- Not CPM-style pullback-continuation.
- Not a value-zone / dip-buying entry.
- Not a regime system.
- Not a standalone volatility strategy (it requires trend context).
- Not an overlay on Direction A.

### 2.3 Relationship To Main Trend Capture Thesis

Direction C belongs to the Main Trend Capture family because:

- It targets trend continuation profit, not local pullback segments.
- It accepts low win rate, sparse profits, and high payoff ratio.
- The primary timeframe is 4h.
- The profit source is the impulse phase of a sustained trend move.
- The exit philosophy is trend-structure break, not fixed TP.

Direction C differs from CPM because it does not ask "has the pullback
ended?" It asks "has volatility compressed enough that the next impulse
is likely?"

---

## 3. Strategy Hypothesis

> ETH 4h trends exhibit a volatility cycle: after an initial impulse,
> volatility contracts during consolidation, then re-expands for the next
> impulse phase. Entering on the re-expansion — specifically when a 4h
> candle's range or ATR expands after a period of contraction, in the
> direction of the established trend — captures the continuation impulse
> with a structurally different signal distribution than raw Donchian
> breakout. The contraction filter may reduce false breakouts that occur
> in noisy, non-contracting conditions, producing fewer but higher-quality
> signals with a potentially wider winner distribution.

### 3.1 What It Captures

Direction C captures the **second (or subsequent) impulse** within an
established trend. The first impulse establishes the trend. The contraction
phase is the consolidation. The re-expansion is the next leg.

This is different from Direction A, which enters on any Donchian breakout
regardless of volatility state. Direction A enters both the first impulse
and continuation impulses with the same rule. Direction C specifically
targets continuation impulses that follow volatility compression.

### 3.2 What It Earns

The profit source is the same as Direction A: the continuation of a
sustained 4h trend move. But the entry mechanism selects a different
subset of those continuation signals — specifically, those preceded by
volatility contraction.

The hypothesis is that contraction-filtered continuation signals have:

- fewer false breakouts (noise reduction);
- better entry prices (entering after consolidation, not at extended
  levels);
- potentially wider winner distribution (higher signal quality may mean
  more trades survive to become winners, not fewer).

---

## 4. Mechanism Boundary: Contraction And Re-expansion

This section defines the mechanism concepts. No parameters are frozen here.
Parameters are frozen only in the experiment plan (Section 8) after Owner
approval of the inspect.

### 4.1 Trend Context (Precondition)

Before any contraction signal is valid, an established trend must exist.

Concept: price is in a directional trend on the 4h timeframe. The trend
context is the precondition that makes a contraction signal meaningful.
Without trend context, a contraction is just a range — and trading ranges
is Direction G, not Direction C.

Possible trend-context definitions (concept-level only, not frozen):

- Price above a 4h moving average (e.g., EMA60, consistent with Direction A's
  lifecycle indicator).
- Recent 4h Donchian breakout occurred and has not been invalidated.
- Price structure shows higher highs / higher lows on 4h.

The trend context must be objectively defined and frozen before experiment.
It must not be a discretionary or multi-condition filter.

### 4.2 Contraction Definition (Concept)

Contraction means: volatility has compressed relative to its recent norm.

Concept-level contraction could be expressed as:

- **ATR ratio**: recent-period ATR is materially below a longer-period ATR.
  Short ATR / Long ATR < threshold. The "short" period captures the current
  consolidation; the "long" period captures the recent norm.
- **Range contraction**: recent 4h candle ranges are materially narrower than
  a longer-period average range.
- **Bollinger bandwidth**: Bollinger band width (upper - lower) has compressed
  relative to a longer-period average.

These are concept-level definitions. Only one will be frozen for experiment.
The inspect does not choose which one — that is the experiment plan's job.

**Critical constraint**: Contraction must be defined objectively from OHLCV
data. No discretionary judgment, no multi-condition scoring, no regime
classification.

### 4.3 Re-expansion / Confirmation (Concept)

Re-expansion means: after contraction, a 4h candle shows material volatility
expansion in the trend direction.

Concept-level re-expansion could be expressed as:

- A 4h candle's range exceeds a multiple of the recent (contraction-period)
  average range.
- A 4h candle's body (close - open) is materially larger than recent bodies.
- ATR of the most recent candle exceeds the contraction-period ATR by a
  defined ratio.

The re-expansion must also be in the trend direction: bullish expansion in
an uptrend, bearish expansion in a downtrend (if short-side is included).

**Critical constraint**: Re-expansion must be objectively defined and
frozen. No after-the-fact selection of which expansions to trade.

### 4.4 Entry Timing

Entry execution occurs at the next 4h bar open after the re-expansion
candle closes. This is consistent with Direction A's next-bar policy and
prevents same-bar lookahead.

### 4.5 Exit Rule

For the first-round experiment, the exit rule should be inherited from
Direction A: **EMA60 close-break trend-lifecycle exit** on 4h.

Rationale:

- The purpose of the first experiment is to isolate the entry mechanism
  effect. Using a different exit would confound the comparison.
- EMA60 close-break was already tested in Direction A and produced a
  positive-but-fragile result. If Direction C's entry mechanism changes
  the signal distribution, the same exit may produce a different fragility
  shape.
- A different exit hypothesis (structure trailing, partial TP + runner,
  N-bar low) can be tested in a later pass if Direction C shows promise.

The initial risk stop should also be inherited from Direction A's
structural approach: a recent-period structure low, frozen before
experiment.

### 4.6 Data Requirement

Direction C depends only on 4h OHLCV data. ATR, range, and moving average
calculations are all derivable from OHLCV.

No funding data, OI data, orderbook data, or external data is required for
the first-round experiment.

**Funding exposure**: Funding cost will be calculated using the same
frozen funding model as Direction A (funding_rate_per_8h = 0.0001). If
the experiment report shows funding cost is material (> 15% of gross PnL),
this must be flagged as a fragility dimension but does not by itself block
classification.

---

## 5. What Direction C Addresses From Direction A

### 5.1 Top-Winner Fragility

Direction A's top-3 exclusion is -935. The winner cluster is narrow (3
trades carry 115% of net PnL).

Direction C's hypothesis: contraction-filtered signals are higher quality,
potentially producing more winners and a wider winner distribution. If the
contraction filter removes noisy breakouts that produce small losers
without removing the main winners, the top-3 exclusion could improve.

**This is the primary testable question.** If Direction C has the same
or worse top-3 exclusion as Direction A, the entry mechanism does not
address fragility.

### 5.2 Noise Breakout

Direction A enters on every Donchian20 breakout. Some of these breakouts
fail immediately — they are noise breakouts in non-trending or
high-volatility choppy conditions.

Direction C's contraction filter may reduce noise breakouts because:

- Contraction implies energy building, not random noise.
- Breakouts from compressed volatility may have higher continuation
  probability.
- Non-contracting breakouts (Direction A signals that Direction C would
  skip) may be disproportionately the losing trades.

**This is testable:** compare Direction A's skipped signals (those that
Direction C would filter) against Direction C's actual trades.

### 5.3 Late Entry

Direction A enters at the next 4h open after a Donchian breakout, which
can be at an extended price level. Direction C's contraction filter means
entry occurs after consolidation, potentially at a less extended price.

**Effect:** may reduce entry-to-stop distance and average loser, improving
initial risk.

### 5.4 Weak Continuation

Some Donchian breakouts in Direction A show weak follow-through — the
breakout occurs but the trend does not continue. These are the trades that
hit the initial stop or produce small losers.

Direction C's contraction filter may reduce these because weak-continuation
breakouts may be less likely to follow compression.

### 5.5 Trade Count / Statistical Grounding

Direction A produced 173 trades over 2021-2025. Direction C will produce
fewer signals because contraction events are less frequent than raw
Donchian breakouts.

**Risk:** If Direction C produces fewer than 55 trades (MTC-001 floor),
the result is INSUFFICIENT_EVIDENCE regardless of other metrics. This is
the primary feasibility risk.

### 5.6 Year-by-Year And Regime Explainability

Direction A's year-by-year showed 2023/2024 dominant. Direction C may show
a different year-by-year shape because contraction events may cluster in
different market phases.

If contraction events are more evenly distributed across years, Direction C
may show better year-by-year robustness. If they cluster in the same years
as Direction A's winners, no improvement.

---

## 6. Boundary With Direction D And CPM

### 6.1 Direction C Is Not Pullback Entry

Direction C's contraction is not a pullback. A pullback is a price
retracement to a value zone (EMA zone, structure level, Fibonacci zone).
Contraction is a volatility state — price may not retrace at all; it may
simply narrow its range while maintaining position.

Key distinction:

| Dimension | Direction C (Contraction) | Direction D (Value-Zone Pullback) | CPM (Pinbar Pullback) |
|-----------|--------------------------|-----------------------------------|----------------------|
| Entry trigger | Volatility expansion after compression | Price touching a value zone + resumption confirmation | Candle pattern at pullback end |
| What it filters for | Volatility state | Price location | Candle morphology |
| Trend context | Required (established trend) | Required (established trend) | Assumed (EMA/MTF context) |
| Retracement required | No — contraction can occur without price retracement | Yes — price must retrace to zone | Yes — price must pull back |
| Parameter freedom | Contraction threshold | Zone width, zone type | Candle body/wick ratios |

If the frozen experiment plan requires a price retracement to a value zone
as part of the entry condition, that is Direction D, not Direction C. The
experiment plan must not include zone-based entry conditions.

### 6.2 Direction C Is Not CPM Rescue

Direction C does not:

- Ask "has the pullback ended?" (CPM's question).
- Use Pinbar or candle pattern confirmation.
- Target 1h local segments.
- Require a lower-timeframe reversal confirmation.
- Use fixed TP/SL geometry.

If the frozen entry rule includes any CPM-style element (Pinbar, pullback
confirmation, fixed TP, 1h segment logic), the inspect must classify the
direction as CPM variant and stop.

### 6.3 Direction C Is Not A Filter On Direction A

Direction C is a structurally different entry mechanism. The contraction
condition is not a filter applied to Donchian breakout — it is the primary
signal source.

If the frozen entry rule is "Donchian20 breakout AND contraction condition"
(i.e., Direction A with an added contraction gate), that is a Direction A
variant, not Direction C. The inspect must flag this and the experiment plan
must choose one framing:

- **Standalone entry**: contraction + re-expansion IS the entry signal.
  Donchian breakout is not used. This is the preferred framing.
- **Donchian + contraction**: Donchian20 breakout filtered by contraction.
  This is a Direction A variant and should be classified as such.

The inspect recommends the standalone entry framing to maintain structural
separation from Direction A.

---

## 7. Minimum Experiment Plan Draft

This section defines a proposed experiment plan. It is not execution
authorization. Execution requires a separate Owner-approved task card at
Level 3.

### 7.1 Frozen Rule Definition

#### Entry

| Field | Frozen Definition |
|-------|-------------------|
| Entry family | Volatility contraction then re-expansion in trend direction |
| Trend context | Price above 4h EMA60 (uptrend) at time of contraction signal |
| Contraction metric | **ATR ratio**: 6-period ATR / 20-period ATR on 4h closes |
| Contraction condition | ATR ratio < frozen threshold (to be specified before execution) |
| Contraction window | 6 most recent closed 4h bars for short ATR; 20 most recent closed 4h bars for long ATR |
| Re-expansion condition | Current closed 4h candle range > frozen multiple of 6-period average range |
| Re-expansion direction | Close > Open (bullish candle in uptrend) |
| Entry execution | Next 4h bar open after re-expansion candle closes |
| Same-bar entry | Not allowed |
| Signal bar | The re-expansion candle; must be fully closed before entry decision |

The ATR ratio is the first-round contraction metric because:

- It is derivable from OHLCV only.
- It has a single threshold (ATR ratio cutoff), minimizing parameter freedom.
- It measures volatility compression objectively.
- It does not require Bollinger bandwidth calculation or subjective range
  assessment.

Alternative contraction metrics (Bollinger bandwidth, range contraction)
are not tested in the first round. Testing multiple metrics would be a
parameter search.

#### Initial Stop

| Field | Frozen Definition |
|-------|-------------------|
| Stop family | Lowest low of the 6 most recent closed 4h bars at entry time |
| Signal bar in stop window | Excluded |
| Stop status | Active throughout the trade |
| Stop execution | Stop / risk exit under documented pessimistic ordering |

The 6-bar lookback is chosen to be consistent with the contraction window.
It provides a structural stop below the consolidation range, not below the
Donchian channel.

#### Exit

| Field | Frozen Definition |
|-------|-------------------|
| Exit family | 4h EMA60 close-break trend-lifecycle exit |
| EMA period | 60 (closed 4h candles) |
| Exit trigger | Fully closed 4h candle close below EMA60 |
| Intrabar EMA60 touch | Does not trigger exit |
| Exit execution | Next 4h bar open after exit trigger close, less exit slippage |
| Trailing stop | Not included |
| Overlay | Not included |

#### Parameters

| Parameter | Value | Frozen |
|-----------|-------|--------|
| EMA period (trend context) | 60 | Yes |
| ATR short period | 6 | Yes |
| ATR long period | 20 | Yes |
| ATR ratio threshold | **To be frozen before execution** | Pending |
| Re-expansion multiple | **To be frozen before execution** | Pending |
| Stop lookback | 6 | Yes |
| Timeframe | 4h | Yes |
| Symbol | ETH/USDT:USDT | Yes |

**The ATR ratio threshold and re-expansion multiple are the two pending
parameters.** They must be frozen before execution. The inspect does not
recommend specific values — that is the experiment plan's job. The inspect
requires that:

- Values are chosen before seeing any result.
- No threshold sweep is allowed.
- Values must be justified by a structural rationale (e.g., "ATR ratio <
  0.5 means recent ATR is less than half of the norm"), not by
  backfitting.

### 7.2 Data Window

| Window | Period | Authority |
|--------|--------|-----------|
| Base window | 2021-01-01 00:00:00 UTC to 2025-12-31 20:00:00 UTC | Primary evidence |
| Year-by-year | 2021, 2022, 2023, 2024, 2025 individually | Year concentration check |

No supplemental window. No 2019/2020 data. No pre-2021 window.

### 7.3 Cost Model

Inherited verbatim from NSC-013 / NSC-014 / CPM-1 OOS SSOT:

| Parameter | Value |
|-----------|-------|
| fee_rate | 0.0004 |
| entry_slippage_rate | 0.001 |
| stop_or_ema_exit_slippage_rate | 0.001 |
| funding_enabled | True |
| funding_rate_per_8h | 0.0001 |

Cost model must not be relaxed.

### 7.4 Same-Bar / Next-Bar Policy

- Signal decisions use fully closed 4h candles only.
- Entry occurs at next 4h bar open after signal candle close.
- Initial stop is active intrabar and checked before EMA60 close-break on
  same bar (pessimistic ordering).
- EMA60 exit requires fully closed 4h candle close below EMA60.
- EMA60 exit execution occurs at next 4h bar open after trigger.
- No same-bar entry from signal close.
- No exit decision from unclosed candles.

### 7.5 Anti-Lookahead Requirements

- ATR and range calculations use only prior closed 4h candles and exclude
  the signal bar.
- EMA60 is computed from closed 4h candles only.
- No signal, entry, or exit decision may use future candles.
- The contraction window and re-expansion comparison use only bars up to
  and including the signal bar.

### 7.6 MTC-001 Fragility Gates

Pre-registered from MTC-001:

| Gate | Threshold |
|------|-----------|
| Trade count: total minimum | >= 55 |
| Trade count: 2023+2024+2025 minimum | >= 40 |
| Trade count: 2021+2022 minimum | >= 15 |
| Winner count | >= 15 |
| Top-1 net excluding | > 0 for PASS; >= 0 for PAUSE_FRAGILE; < 0 for REJECT |
| Top-3 net excluding | > 0 for PASS; < 0 for PAUSE_FRAGILE |
| Top-5 net excluding | Reported; near 0 or positive for PASS |
| Net PnL after costs | > 0 for any non-REJECT classification |
| PF after costs | > 1.0 for any non-REJECT classification |
| Year-by-year | >= 2 years independently positive after costs; no year > 60% of total net |
| MFE / MAE / Giveback | Reported per MTC-001 Section 4.4 |
| MTM MaxDD | Reported per MTC-001 Section 4.5 |
| Funding exposure | Reported; flagged if > 15% of gross PnL |

### 7.7 Classification Rules

Apply MTC-001 Section 5 classification flow:

1. Trade count floors not met → `INSUFFICIENT_EVIDENCE`
2. Net PnL < 0 or PF < 1.0 after costs → `REJECT`
3. Top-1 net excluding < 0 → `REJECT` (single-trade dependent)
4. Top-3 net excluding < 0 → `PAUSE_FRAGILE`
5. Top-3 net excluding > 0 + top-5 near 0 or positive + year-by-year OK
   → `RESEARCH_PASS`
6. `RESEARCH_PASS` + OOS validation (separate task) → `RUNTIME_CANDIDATE`

### 7.8 Required Output Metrics

The experiment report must include:

- Signal count and closed position count.
- Net PnL, gross PnL, PF, win rate.
- Payoff ratio (avg winner / avg loser).
- Realized MaxDD, MTM MaxDD.
- MFE, MAE, maximum giveback.
- Average / median / max hold hours.
- Hold duration distribution.
- Funding cost, fee cost, slippage cost (aggregate and per trade).
- Top-1, top-3, top-5 net excluding.
- Year-by-year breakdown (all metrics above per year).
- Winner count.
- Direction A comparison table (same metrics, side by side).
- Skipped-signal analysis: how many Direction A signals were filtered by
  the contraction condition, and what was their PnL distribution.
- Winner attribution: for top-5 winners, market condition and whether the
  frozen rule naturally captured the trade.
- Final classification with MTC-001 gate results.

---

## 8. Direction A Comparison Requirement

The experiment report must include a direct comparison against the
NSC-014 Direction A clean baseline.

This comparison must answer:

| Question | How Answered |
|----------|-------------|
| Did Direction C reduce false breakouts? | Compare number of losing trades and average loser |
| Did Direction C preserve the main winners? | Compare top-3 and top-5 winners; check if Direction A's top winners are included in Direction C |
| Did Direction C improve top-winner fragility? | Compare top-1, top-3, top-5 net excluding |
| Did Direction C improve year-by-year distribution? | Compare year-by-year PnL shape |
| Did Direction C meet trade count floors? | Compare trade count |
| Is Direction C a Direction A subset? | Count overlapping signals; if > 80% of Direction C signals are a subset of Direction A signals, flag as variant |

If Direction C is a strict subset of Direction A (> 80% signal overlap with
fewer total signals), the inspect must classify it as a Direction A variant,
not a new direction. This is a stop condition.

---

## 9. Risk And Stop Conditions

### 9.1 Stop: Direction A Variant

**Condition:** If the frozen contraction filter simply removes Direction A
signals without producing any new signals, and > 80% of Direction C's
trades overlap with Direction A's trades.

**Action:** Classify as Direction A variant. Do not proceed to Level 3.
The contraction filter is a Direction A refinement, not a new direction.

### 9.2 Stop: Parameter Search Required

**Condition:** If the ATR ratio threshold and re-expansion multiple cannot
be frozen with a single structural rationale, and the experiment plan
requires testing multiple threshold combinations.

**Action:** Stop. Parameter search is prohibited by MTC-001 sparse trend
profit principles.

### 9.3 Stop: Trade Count Below Floor

**Condition:** If the frozen rule produces fewer than 55 total trades or
fewer than 40 trades in 2023-2025.

**Action:** Classify as `INSUFFICIENT_EVIDENCE`. Direction C is not viable
at 4h with this contraction definition. Consider whether a different
contraction metric or different timeframe would produce more signals (but
that requires a new docs-only plan, not a parameter adjustment).

### 9.4 Stop: New Data Required

**Condition:** If the frozen rule requires funding rate, OI, orderbook, or
other data not available in the current 4h OHLCV pipeline.

**Action:** Stop and return to Owner. Direction C must remain OHLCV-only
for the first round. Data dependency moves Direction C to backlog.

### 9.5 Stop: Winner Attribution Failure

**Condition:** If top-5 winners cannot be explained by the contraction +
re-expansion mechanism — e.g., winners are driven by event spikes, liquidation
cascades, or data artifacts that the frozen rule did not structurally
identify.

**Action:** Do not upgrade classification beyond PAUSE_FRAGILE regardless
of other metrics. Winner attribution is a required MTC-001 dimension.

### 9.6 Stop: CPM / Pullback Drift

**Condition:** If the frozen entry rule requires price retracement to a
value zone, Pinbar confirmation, or any CPM-style element.

**Action:** Reclassify as Direction D or CPM variant. Direction C is not
pullback entry.

### 9.7 Stop: Overlay Stacking

**Condition:** If the experiment plan includes Direction E overlays,
multiple contraction metrics, or stacked filters.

**Action:** Stop. First-round must be clean baseline only. Overlay testing
requires separate approval after baseline evidence.

---

## 10. Feasibility Assessment

### 10.1 Primary Risk: Signal Count

Direction A produced 173 signals over 2021-2025 (~35/year). Direction C
will produce fewer because contraction events are less frequent than raw
Donchian breakouts.

The MTC-001 floor is 55 total trades. This requires approximately 11
trades per year on average.

Estimation approach (concept-level):

- Direction A's 35 signals/year include breakouts from both contracting
  and non-contracting conditions.
- If 30-50% of Direction A's signals occur during contraction conditions,
  Direction C would produce 10-18 signals/year.
- At 10 signals/year, Direction C produces ~50 total trades — below the
  55-trade floor.
- At 18 signals/year, Direction C produces ~90 total trades — above the
  floor.

The signal count depends on the ATR ratio threshold. A lower threshold
(stricter contraction) produces fewer signals. A higher threshold (looser
contraction) produces more but approaches Direction A.

**This is the central feasibility question.** The inspect cannot answer it
without running the experiment. The experiment plan must include a signal
count check as the first gate.

### 10.2 Secondary Risk: Winner Overlap

If Direction C's winners are a strict subset of Direction A's winners,
the fragility shape will be similar or worse (same winners, fewer trades,
higher concentration). In this case, Direction C does not address the core
problem.

The skipped-signal analysis (Section 8) is designed to detect this.

### 10.3 Tertiary Risk: Threshold Sensitivity

The ATR ratio threshold is the key parameter. If the result is highly
sensitive to small changes in the threshold, the edge may not be robust.

The experiment plan freezes one threshold. No sweep is allowed. But the
report should note whether the chosen threshold is in a stable region
(conceptual assessment only, not a sweep).

---

## 11. Connection To MTC-001 And MTC-002

| Document | Connection |
|----------|-----------|
| MTC-001 | This inspect adopts MTC-001 as the fragility framework. All gates in Section 7.6 are from MTC-001. |
| MTC-002 | This inspect implements MTC-002's recommended next step: Direction C inspect as P0 priority. |
| Direction Map v1 | This inspect evaluates Direction C as defined in SCDM-001 Section 4. |
| Direction Map v2 | This inspect evaluates Direction C as recommended in MTC-002 Section 6. |

---

## 12. Explicit Non-Goals

- This document does not authorize running experiments or backtests.
- This document does not authorize code, adapters, or strategy implementation.
- This document does not authorize runtime/profile/risk/backtester-core changes.
- This document does not authorize parameter sweeps.
- This document does not make a promotion, small-live, or live deployment
  conclusion.
- This document does not reopen Direction A.
- This document does not continue 1h entry rule search (Direction B).
- This document does not reopen Direction E overlay family.
- This document does not rescue CPM-1 or CPM-2.
- This document does not introduce funding/OI data pipelines.
- This document does not establish Direction C as a runtime candidate.
- This document does not override MTC-001 classification gates.

---

## 13. Not-Now List

- No Direction A rescue or continuation.
- No Direction B D2/D3/D4 1h family search.
- No Direction E overlay experiments.
- No CPM-1 / CPM-2 rescue.
- No Candidate C (CPM) auto-start.
- No parameter sweep of any kind.
- No contraction metric comparison (ATR ratio vs Bollinger vs range).
- No multi-metric contraction scoring.
- No 1h timeframe involvement.
- No overlay stacking.
- No cost / funding / slippage relaxation.
- No regime system.
- No portfolio / multi-strategy / multi-asset.
- No ML or complex classifiers.
- No runtime/profile/risk/backtester-core changes.
- No data pipeline construction.
- No promotion or small-live conclusions.

---

## 14. Owner Summary

### 14.1 Recommendation

**Recommended: Upgrade to Level 3 research-only experiment.**

Direction C is worth testing because:

1. It uses a structurally different entry mechanism (volatility contraction +
   re-expansion) from Direction A (Donchian breakout). It is not a parameter
   variant or filter on Direction A.

2. It targets the same Main Trend Capture profit source (4h trend
   continuation impulse) but may produce a different signal distribution with
   potentially wider winner cluster.

3. The primary feasibility risk (signal count) can only be resolved by
   running the experiment. The inspect cannot answer it.

4. If Direction C fails, the failure is cleanly classifiable under MTC-001
   (INSUFFICIENT_EVIDENCE if too few trades, REJECT if negative, PAUSE_FRAGILE
   if fragile). There is no ambiguity.

5. Direction C does not require new data, infrastructure, or platform
   expansion.

### 14.2 Conditions For Level 3 Authorization

Before execution, the following must be completed in a separate docs-only
experiment plan:

- Freeze ATR ratio threshold with structural rationale (no backfitting).
- Freeze re-expansion multiple with structural rationale.
- Confirm trend context definition (EMA60 or alternative).
- Confirm stop lookback.
- Register all MTC-001 gates from Section 7.6.
- Confirm no parameter sweep, no overlay, no 1h involvement.

### 14.3 Owner Decision Required

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Approve Direction C inspect conclusion? | Yes / No / Modify | Yes |
| Approve upgrading to Level 3 experiment plan? | Yes / No / Need more info | Yes, pending frozen threshold specification |
| Direction D in parallel? | Yes / No / After C result | After C result — if C is INSUFFICIENT_EVIDENCE, D becomes next |
| Contraction metric choice? | ATR ratio / Bollinger / Range | ATR ratio — lowest parameter freedom, most interpretable |
| Exit rule? | EMA60 (inherit Direction A) / New exit hypothesis | EMA60 — isolate entry mechanism effect |

### 14.4 Prohibitions Remain

All prohibitions from MTC-002 Section 9 remain in force. This inspect does
not relax any prohibition.

---

## 15. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-07 | Initial Direction C inspect v0 | Claude |
