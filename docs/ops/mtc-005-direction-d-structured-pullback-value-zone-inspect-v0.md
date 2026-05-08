# MTC-005 — Direction D Structured Pullback / Value-Zone Entry Inspect v0

**Task ID:** MTC-005
**Date:** 2026-05-07
**Status:** Proposed / Direction Inspect Only
**Scope:** Docs-only direction inspect + minimal experiment plan draft
**Affects Runtime Automatically:** No
**Authorization Level:** Level 1/2 — inspect + docs-only plan; no execution

---

## 0. Boundary

This document inspects Direction D as a candidate Main Trend Capture
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
- zone definition search;
- Fibonacci ratio sweep;
- EMA zone sweep;
- CPM-style pullback rescue.

This task did not run backtests, write code, create adapters, implement
strategies, tune parameters, modify runtime, modify profiles, modify risk
rules, or touch `src/`, `configs/`, `tests/`, `migrations/`, production
strategy paths, or backtester / research engine core.

Inspected material:

- `docs/ops/strategy-candidate-direction-map-v1.md` (Direction D definition)
- `docs/ops/mtc-002-strategy-direction-map-refresh.md`
- `docs/ops/mtc-001-main-trend-capture-fragility-evaluation-framework-v0.md`
- `docs/ops/mtc-003-direction-c-volatility-contraction-inspect-v0.md`
- `docs/ops/mtc-004-direction-c-frozen-baseline-research-report.md`
- `docs/ops/crypto-pullback-module-v1-scope-note.md`
- `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md`
- `docs/ops/nsc-001-cpm-2-candidate-direction-inspect.md`
- `docs/ops/nsc-007-next-strategy-candidate-direction-inspect.md`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/summary.json`
- `reports/mtc-004-direction-c-frozen-baseline/summary.json`
- `docs/ops/project-roadmap-v2.md`

---

## 1. Current State

| Field | State |
|-------|-------|
| CPM-1 | Paused; OOS failure classified; not a small-live candidate |
| CPM-2 Candidate A/B | Closed; research proxy insufficient |
| Candidate C (CPM) | Reserve-only; not activated |
| Direction A (Donchian20 + EMA60) | PAUSE_FRAGILE — Do not reopen |
| Direction B (4h + 1h entry timing) | MIXED_PARTIAL; reserve |
| Direction C (volatility contraction) | INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE |
| Direction E (overlay family) | Closed |
| Direction D (this inspect) | Inspect — no evidence yet |
| Deployable small-live candidate | None |
| Small-live readiness gate | Unmet |

### 1.1 Direction C Precedent

Direction C (MTC-004) was inspected, frozen, and run. Key results:

- 63 trades over 5 years (2021-2025); 14 in 2021+2022 (floor: 15).
- Classification: INSUFFICIENT_EVIDENCE.
- Top-1 = 82.25% of net (worse than Direction A's 45.76%).
- Top-3 exclusion = -2471 (Direction A: -443.91).
- MTM MaxDD = 15.01% (Direction A: 8.33%).
- 14.3% signal overlap with Direction A — structurally different entry.
- Owner conclusion: INSUFFICIENT_EVIDENCE / PAUSE_THIN_FRAGILE; not
  upgraded, not rejected, not continued.

Direction C demonstrated that volatility contraction as a standalone entry
mechanism is structurally different from Donchian breakout but produced too
few signals with too-high concentration. Direction D is the next priority.

---

## 2. Direction D Identity

### 2.1 What Direction D Is

Direction D is a Main Trend Capture direction that uses zone-based pullback
entry within an established 4h trend. Instead of entering on a breakout to
new highs (Direction A) or on volatility state change (Direction C),
Direction D enters when price retraces to a structural value zone within
the trend and then shows signs of resumption.

The core idea:

> Within a 4h uptrend (price above EMA60), price pulls back toward the
> EMA60 trend-lifecycle level. This pullback is the value zone. When price
> resumes the trend direction — specifically, when a subsequent 4h bar
> closes back above EMA20 — the pullback is structurally confirmed as
> ended. Enter on the resumption, not on the initial pullback touch.

Direction D targets the **resumption leg after a pullback within a trend**.
It does not target trend initiation (Direction A), volatility contraction
impulse (Direction C), or 1h candle-pattern reversal (CPM-1).

### 2.2 What Direction D Is Not

- Not Direction A with a filter.
- Not a Donchian parameter variant.
- Not a value-zone dip-buying or mean-reversion entry.
- Not a regime system.
- Not a standalone pullback strategy (it requires trend context).
- Not an overlay on Direction A.
- Not CPM-1 rescue.
- Not a 1h candle-pattern trigger.

### 2.3 Relationship To Main Trend Capture Thesis

Direction D belongs to the Main Trend Capture family because:

- It targets trend continuation profit, not local pullback segments.
- It accepts low win rate, sparse profits, and high payoff ratio.
- The primary timeframe is 4h.
- The profit source is the resumption leg of a sustained trend move.
- The exit philosophy is trend-structure break (EMA60 close-break), not
  fixed TP.

Direction D shares the MTC operating assumptions:

- Sparse signals, few winners, large-winner dependency.
- Each direction must independently satisfy MTC-001 fragility gates.
- No portfolio combination, regime routing, or multi-strategy framework.

---

## 3. Strategy Hypothesis

> ETH 4h trends exhibit recurring pullback-resumption cycles. After an
> initial impulse establishes the trend, price periodically retraces toward
> the trend-lifecycle moving average (EMA60) before resuming. These
> pullback-to-resumption sequences represent opportunities to enter the
> trend at better prices than breakout entries. By entering on structural
> resumption confirmation (EMA20 reclaim after EMA60 touch) rather than on
> candle patterns (CPM-1 Pinbar) or breakouts (Direction A Donchian20),
> Direction D captures continuation profit with potentially improved entry
> price, tighter initial risk, and a wider winner distribution than
> breakout-based entry.

### 3.1 What It Captures

Direction D captures the **resumption leg after a pullback within an
established trend**. The trend is already underway (price above EMA60).
Price pulls back to the EMA60 zone. The pullback ends (confirmed by EMA20
reclaim). The trend resumes. Direction D enters on the resumption.

This is different from:

- **Direction A**: enters on breakouts to new highs (after the impulse has
  already started).
- **Direction C**: enters on volatility expansion after contraction
  (volatility state, not price location).
- **CPM-1**: enters on Pinbar candle pattern at pullback end (single-candle
  geometry, not structural zone + resumption).

### 3.2 What It Earns

The profit source is trend continuation — the same fundamental source as
Direction A and Direction C. But the entry mechanism selects a different
subset of continuation signals: those preceded by a pullback to a value
zone, with structural resumption confirmation.

The hypothesis is that pullback-resumption signals have:

- Better entry prices (entering after retracement, not at extended levels);
- Tighter initial risk (stop below recent swing low, not Donchian channel
  low);
- Potentially more signals (pullbacks within trends are frequent);
- Potentially wider winner distribution (better entry price may allow more
  trades to survive to meaningful profit).

---

## 4. What Direction D Addresses From Direction A

### 4.1 Late Breakout Entry

Direction A's primary structural weakness is late entry. Donchian20 breakout
occurs after price has already moved to a new high — the entry is at an
extended level. This creates:

- Wide initial stop (previous 20-bar low, often far from entry);
- High initial risk per trade;
- Dependence on continuation beyond the already-extended level.

Direction D enters during a pullback to EMA60 — a level that is by
definition below the current trend price. The entry price is lower, the
initial stop (recent swing low below EMA60) is tighter, and the trade
requires continuation from a less extended level.

**Testable implication:** Direction D's average entry-to-stop distance
should be materially smaller than Direction A's, and average loser should
be smaller.

### 4.2 Top-Winner Fragility

Direction A's top-3 exclusion is -443.91 (3 trades carry 115% of net PnL).
The winner cluster is extremely narrow.

Direction D's hypothesis: pullback entries at structural levels produce a
more distributed set of winners because:

- Entry at a better price gives more room for profit before the next
  resistance;
- More entries (pullbacks are frequent) means more chances for winners;
- The resumption confirmation may filter out failed pullbacks that produce
  Direction A's small losers.

**This is the primary testable question.** If Direction D's top-3 exclusion
is still negative, pullback entry does not improve winner concentration
relative to breakout entry.

### 4.3 Noise Breakout

Direction A enters on every Donchian20 breakout. Some breakouts fail
immediately (false breakouts in choppy conditions). Direction D skips these
entirely because it does not enter on breakouts — it enters on pullbacks
within established trends.

**Testable implication:** Direction D's loss rate on failed breakouts should
be zero (by construction). Its losses should instead come from pullbacks
that turn into trend reversals.

### 4.4 What Direction D Does NOT Address

Direction D does not address:

- **Winner-cluster concentration at the mechanism level**: if the pullback-
  resumption mechanism still produces a narrow winner cluster, the
  fragility is structural to trend-continuation, not specific to breakout
  entry.
- **Direction A's winning trades**: Direction D misses the strongest trend
  initiations where price never pulls back. In aggressive uptrends
  (e.g., 2021 May rally, 2024 Q1 rally), Direction A captures the
  breakout; Direction D waits for a pullback that may not come.
- **Same-bar execution risk**: both directions use next-bar entry. Same-bar
  risk is equivalent.

---

## 5. What Direction D Addresses From Direction C

### 5.1 Thin Sample

Direction C produced only 63 trades over 5 years (14 in 2021+2022). The
thin sample made MTC-001 evaluation unreliable and triggered
INSUFFICIENT_EVIDENCE.

Direction D's zone-touch mechanism is structurally more frequent than
Direction C's volatility contraction:

- Zone touches (price near EMA60) occur during every meaningful pullback in
  a trend.
- Volatility contraction (ATR ratio < 0.7) is a less common state.
- Direction D requires an additional resumption confirmation (EMA20 reclaim),
  which filters some zone touches, but the base rate of zone touches is
  higher.

**Expected signal count:** 100-200 trades over 5 years. This is above the
MTC-001 floor of 100 total / 60 recent-regime if confirmed.

**Testable implication:** Direction D's trade count should materially exceed
Direction C's 63.

### 5.2 High Concentration

Direction C's top-1 = 82.25% of net (one trade carries 82% of all profit).
Direction D's hypothesis: more signals with better entry prices produce a
wider winner distribution.

**Testable implication:** Direction D's top-1 and top-3 concentration should
be lower than Direction C's.

### 5.3 Direction C Is Not Direction D

The distinction from MTC-003 Section 6.1 remains valid:

| Dimension | Direction C (Contraction) | Direction D (Value-Zone Pullback) |
|-----------|--------------------------|-----------------------------------|
| Entry trigger | Volatility expansion after compression | Price touching value zone + resumption confirmation |
| What it filters for | Volatility state | Price location |
| Retracement required | No — contraction can occur without retracement | Yes — price must retrace to zone |
| Parameter freedom | Contraction threshold | Zone type, confirmation method |

Direction D requires price retracement. Direction C does not. They are
structurally different entry mechanisms.

---

## 6. Boundary With CPM-1

This is the critical section of this inspect. Direction D's relationship to
CPM-1 must be explicitly analyzed because pullback-continuation is the
CPM family's conceptual territory.

### 6.1 Direction D Is Conceptually Pullback-Continuation

Direction D asks the same fundamental question as CPM-1: **has the pullback
ended and has the trend resumed?**

| Dimension | CPM-1 | Direction D |
|-----------|-------|-------------|
| Family | Pullback-continuation | Pullback-continuation |
| Core question | Has the pullback ended? | Has the pullback ended? |
| Timeframe | 1h primary, 4h MTF confirmation | 4h primary |
| Trend context | EMA50 + 4h EMA60 rising | 4h EMA60 (price above) |
| Zone definition | None (Pinbar fires at any pullback level) | EMA60 zone (defined structural level) |
| Entry trigger | Pinbar candle pattern (wick ratio, body ratio) | EMA20 reclaim (structural close) |
| Confirmation type | Single-candle geometry (lower wick) | Multi-bar structural behavior (close above EMA20) |
| Stop | Pinbar candle low (-1.0R) | Recent 6-bar swing low |
| Exit | Fixed TP (1.0R / 3.5R) | EMA60 close-break (trend lifecycle) |
| Profit source | Local pullback segment (1-3R target) | Trend continuation (open-ended) |

### 6.2 Why This Distinction Matters

CPM-1 failed because:

1. **Signal-level failure in 2021**: gross edge negative in a favorable bull
   year.
2. **EMA lag**: EMA50 remained elevated during corrections, causing entries
   in hostile sub-regimes.
3. **Weak confirmation**: Pinbar lower-wick did not reliably confirm
   pullback ending.
4. **Counter-trend in high-slope environments** (M0 ecology finding).
5. **Fixed TP capped winners**: TP1 1.0R / TP2 3.5R limited upside.

Direction D modifies three structural elements:

1. **Timeframe**: 4h instead of 1h. 4h bars carry more structural weight;
   entries are not triggered by 1h noise.
2. **Zone**: EMA60 zone is a defined structural level. CPM-1 had no zone —
   Pinbar could fire at any price level in the pullback.
3. **Confirmation**: EMA20 reclaim is a structural close above a faster
   moving average. This is stronger than a single-candle lower-wick
   pattern.

These are meaningful structural changes, not parameter-level adjustments.
However:

**The core question is the same.** Both CPM-1 and Direction D attempt to
identify when a pullback has ended. CPM-1 could not answer this question
reliably. Direction D's modifications may or may not overcome this
fundamental limitation.

### 6.3 What Would Prove Direction D Is Structurally Different From CPM-1

The experiment can test this directly:

| Evidence | Interpretation |
|----------|---------------|
| Direction D positive in 2021 (CPM-1 was -21.54%) | Strong evidence that 4h/structural modifications overcome CPM-1 failure |
| Direction D negative in 2021 with similar loss clustering | Evidence that the pullback-ending question itself is flawed, regardless of mechanism |
| Direction D has different year-by-year profile than CPM-1 | Evidence that the mechanism produces a different signal distribution |
| Direction D loss clustering does not match CPM-1's sub-regime pattern | Evidence that the zone/confirmation changes alter which market conditions produce losses |

### 6.4 CPM Drift Check

At experiment completion, the following check must be performed:

1. **2021 comparison**: Is Direction D's 2021 gross edge positive or
   negative? If negative, the pullback-ending problem persists.
2. **Loss clustering**: Do Direction D's losses cluster in the same
   sub-regimes as CPM-1 (mid-year correction, post-ATH decline)? If yes,
   the mechanism does not overcome CPM-1's regime sensitivity.
3. **Win rate pattern**: Is Direction D's year-by-year win rate pattern
   similar to CPM-1's? If yes, the signal distribution is similar despite
   different specifications.
4. **2023 comparison**: CPM-1 was -39.24% in 2023 (boundary cost). Does
   Direction D also lose in 2023, or does the 4h/structural approach
   perform differently?

If three or more of these checks show CPM-1-like behavior, Direction D
should be reclassified as a CPM variant and the inspect should stop.

### 6.5 Direction D Is Not CPM Rescue

Direction D must not become a vehicle for rescuing CPM-1 under a different
name. The following are prohibited:

- Using Pinbar or any candle-pattern confirmation.
- Using 1h as the primary timeframe.
- Using fixed TP geometry (1.0R / 3.5R).
- Framing the experiment as "CPM-1 with better entry."
- Reopening CPM-1 parameters under Direction D's label.

If the frozen entry rule includes any CPM-style element, the inspect must
classify Direction D as a CPM variant and stop.

---

## 7. Critical Question: Can The Pullback-Ending Confirmation Work?

This is the central question that the experiment must answer, and that the
inspect must acknowledge.

### 7.1 The CPM-1 Evidence

CPM-1's OOS failure classification found:

- 2021 (bull year): -21.54%, gross edge negative, loss clusters in
  Feb-Mar and Aug-Oct.
- The EMA50 uptrend filter remained active during corrections, causing
  entries in hostile sub-regimes.
- The Pinbar lower-wick confirmation did not prove the pullback had ended.
- The M0 ecology map showed CPM-1 earns in low-slope, low-volatility
  environments and loses in high-slope, high-volatility environments.

**Root cause**: The pullback-ending confirmation (Pinbar lower-wick) was
too weak. EMA lag caused entries during corrections within uptrends. The
applicable market was narrower than documented.

### 7.2 Why Direction D Might Succeed Where CPM-1 Failed

Three structural differences could matter:

**Difference 1: 4h timeframe instead of 1h.**

4h bars aggregate more price information. A 4h EMA60 touch represents a
multi-hour pullback, not a single-hour oscillation. The resumption
confirmation (EMA20 reclaim on 4h) requires a meaningful price recovery,
not a single-candle pattern. This filters out minor 1h noise that may have
produced false Pinbar signals in CPM-1.

**Difference 2: Zone-based location instead of candle pattern.**

CPM-1 entered wherever a Pinbar formed within the EMA50 uptrend — there
was no requirement that price had reached a structural level. This means
CPM-1 could enter on shallow pullbacks that were pauses, not real
retracements. Direction D requires price to reach the EMA60 zone — a
defined structural level — before the entry is valid. This filters out
shallow-pullback entries that have lower resumption probability.

**Difference 3: Structural confirmation instead of candle geometry.**

CPM-1's Pinbar confirmation depended on the wick ratio and body position
of a single candle. The M0 ecology map found this has weak predictive
power (wick_ratio correlation with win rate: +0.0583). Direction D's
EMA20 reclaim confirmation depends on a 4h close above a moving average
— a structural level, not a candle shape. This is a stronger confirmation
signal because it represents actual price behavior (recovery to a faster
trend mean), not candle geometry.

### 7.3 Why Direction D Might Fail Despite These Differences

Three risks remain:

**Risk 1: EMA lag is unchanged.**

Direction D uses EMA60 as the zone. EMA60 lags price. In a correction
within an uptrend, EMA60 remains elevated while price falls. The zone
"descends" slowly. If the correction is deep enough, price touches EMA60
while the correction is still in progress — the same failure mode as
CPM-1's EMA50 lag.

In 2021, ETH experienced sharp corrections within the bull trend (May
crash: -60% in 12 days; Jul correction: -40% in 3 weeks). During these
corrections, EMA60 would have remained elevated, and Direction D entries
at the EMA60 zone would have been falling-knife entries — exactly CPM-1's
failure pattern.

**Risk 2: The M0 ecology finding may generalize.**

M0 found that CPM-1 is structurally counter-trend in high-slope,
high-volatility environments. This may be inherent to pullback-continuation
strategies, not specific to Pinbar or 1h timeframes. If the
counter-trend tendency is a property of pullback-continuation as a family,
Direction D would share it regardless of its specific mechanism.

**Risk 3: EMA20 reclaim may be too loose or too tight.**

If EMA20 is close to EMA60 (weak trend), the confirmation is easy to
achieve — price barely needs to recover. This may produce too many signals
in weak trends where pullback-continuation is least likely to work.

If EMA20 is far from EMA60 (strong trend), the confirmation requires a
meaningful recovery. This is a stronger filter but may reject signals in
strong trends where the pullback is shallow and the resumption is quick —
exactly the conditions where pullback-continuation works best.

### 7.4 Inspect Verdict

The inspect cannot answer whether the pullback-ending confirmation works.
This is an empirical question that requires a frozen experiment.

What the inspect can establish:

1. Direction D is **conceptually pullback-continuation** — same core
   question as CPM-1.
2. Direction D has **three meaningful structural differences** (4h
   timeframe, zone-based location, structural confirmation) that are
   not parameter-level adjustments.
3. Direction D addresses **different problems** than CPM-1 was designed
   for (Direction A's late breakout, Direction C's thin sample).
4. The risk of CPM-1-like failure **is real and cannot be dismissed**
   from the inspect alone.
5. The experiment is justified **if** the Owner accepts that the mechanism
   is plausibly different and the CPM drift check is mandatory.

**Recommendation:** Approve inspect. Authorize Level 3 experiment with
mandatory CPM drift check. Do not promote past PAUSE_FRAGILE without
passing the CPM drift check.

---

## 8. Frozen Specification (Draft)

This section proposes a frozen specification for a Level 3 research-only
experiment. No parameters are frozen until Owner approves the inspect and
authorizes the experiment.

### 8.1 Asset, Timeframe, Window

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Asset | ETH/USDT:USDT | Consistent with all MTC experiments |
| Primary timeframe | 4h | Main Trend Capture standard |
| Data window | 2021-01-01 to 2025-12-31 | 5-year window; same as Direction A/C |
| Data source | `data/v3_dev.db`, table `klines` | Same database as all MTC experiments |

### 8.2 Trend Context

| Parameter | Value |
|-----------|-------|
| Trend indicator | 4h EMA60 |
| Trend condition | Fully closed 4h close > EMA60 |
| Trend direction | LONG-only |

The trend must be established before any pullback signal is valid. The
trend condition is checked on the fully closed 4h bar, not intrabar.

### 8.3 Value Zone Definition

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Zone type | EMA60 zone | Inherited from Direction A's trend-lifecycle indicator |
| Zone touch condition | 4h bar low <= EMA60 (intrabar touch counts) | Price reaches the structural level during the bar |
| Zone must be touched while trend is active | Close > EMA60 on the same bar OR on a bar within the prior 3 bars | Prevents stale zone touches after trend has broken |

**Why EMA60:** EMA60 is already established as the trend-lifecycle
indicator in Direction A. Using it as the pullback zone creates a coherent
experiment: the zone where pullbacks find support in an uptrend is the
same level that defines trend lifecycle. This is not a parameter search —
EMA60 is inherited from the established MTC infrastructure.

**Why not other zone types:** Structure levels, Fibonacci zones, and
Donchian channel zones are valid alternatives. They are excluded from the
first-round experiment to prevent zone-definition parameter search. If
EMA60 produces promising results, alternative zones can be tested in a
separate frozen experiment — not as sensitivity analysis on this one.

### 8.4 Resumption Confirmation

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Confirmation indicator | 4h EMA20 |
| Confirmation condition | A 4h bar fully closes above EMA20, after the most recent zone touch | Structural recovery, not candle pattern |
| Confirmation bar must be after zone touch bar | Yes — confirmation cannot precede the zone touch | Prevents lookahead |

**Why EMA20:** EMA20 represents the short-term trend mean. A close above
EMA20 after an EMA60 touch means price has recovered from the deep
pullback level (EMA60) to the short-term trend mean (EMA20). This is a
structural signal that the pullback has ended and the trend is resuming.

**Why not candle patterns:** Pinbar, engulfing, hammer, and other
candle patterns are excluded because CPM-1 demonstrated that single-candle
geometry has weak predictive power. Direction D must use structural
confirmation.

**Why not swing-high reclaim:** Reclaiming a prior swing high is a
stronger confirmation but would require additional parameters (swing
lookback period) and would significantly reduce signal count. EMA20
reclaim is a minimal structural confirmation that can be tested first.

### 8.5 Entry Execution

| Parameter | Value |
|-----------|-------|
| Entry timing | Next 4h bar open after confirmation bar closes |
| Entry price | Next 4h open + entry slippage |
| Same-bar policy | No same-bar zone touch and confirmation; no same-bar confirmation and entry |

### 8.6 Initial Stop

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Stop type | Lowest low of prior 6 closed 4h bars at signal time | Consistent with Direction A/C |
| Stop execution | Assumed hit at stop level (worst-case) | Conservative |

The 6-bar lookback is inherited from Direction A and Direction C. It is
not a zone-specific parameter.

**Note on stop width:** Direction D's stop should be tighter than
Direction A's (which uses Donchian20 low — the lowest low of 20 bars).
If the experiment shows Direction D's stop is frequently too tight (high
stop-out rate), this is an observation for a future experiment pass — not
a parameter to adjust in the current run.

### 8.7 Exit Rule

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Exit trigger | Fully closed 4h close below EMA60 | Inherited from Direction A; trend lifecycle exit |
| Exit execution | Next 4h open after EMA close-break trigger, less exit slippage | Consistent with Direction A/C |
| Intrabar EMA touch exit | No | Consistent with Direction A/C |

### 8.8 Cost Model

Inherited verbatim from Direction A / CPM-1 OOS SSOT:

| Parameter | Value |
|-----------|-------|
| Fee rate | 0.0004 (each side) |
| Entry slippage rate | 0.001 |
| Exit slippage rate | 0.001 |
| Funding enabled | Yes |
| Funding rate per 8h | 0.0001 |

### 8.9 Position Sizing

| Parameter | Value |
|-----------|-------|
| Initial balance | 10,000 USDT |
| Risk fraction | 0.01 (1% of equity per trade) |
| Max exposure | 2.0x |

### 8.10 Same-Bar Policy

| Scenario | Rule |
|----------|------|
| Signal bar | Fully closed 4h bar with zone touch and/or confirmation |
| Zone touch and confirmation on same bar | Allowed — zone touch is intrabar (low <= EMA60), confirmation is close-based (close > EMA20). Both can occur on the same bar. Signal bar is the confirmation bar. Entry at next bar open. |
| Confirmation and EMA exit on same bar | Initial stop checked before EMA close-break trigger. If stop is hit first, trade is a loser. If EMA exit triggers first, trade exits. Intrabar EMA touch ignored. |
| Zone touch, confirmation, and EMA exit on same bar | Extremely rare. Treat as: confirmation and EMA exit same-bar case. |

### 8.11 Direction A Overlap Measurement

The research adapter must compute signal overlap with Direction A:

1. Load Direction A signals from
   `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/signals.jsonl`.
2. For each Direction D signal, check if a Direction A signal exists
   within +/- 2 bars (8 hours).
3. Report: overlap count, overlap percentage (of Direction D),
   overlap percentage (of Direction A).
4. Classify: < 20% overlap = structurally independent; 20-50% = partial
   overlap; > 50% = largely overlapping.

### 8.12 Output

| Output | Path |
|--------|------|
| Research report | `docs/ops/mtc-005-direction-d-value-zone-research-report.md` |
| Adapter | `reports/mtc-005-direction-d-value-zone/mtc_005_direction_d_research_adapter.py` |
| Summary | `reports/mtc-005-direction-d-value-zone/summary.json` |
| Signals | `reports/mtc-005-direction-d-value-zone/signals.jsonl` |
| Trades | `reports/mtc-005-direction-d-value-zone/trades.jsonl` |
| Equity curve | `reports/mtc-005-direction-d-value-zone/equity_curve.jsonl` |

### 8.13 Year Windows

| Year | Start (ms) | End (ms) |
|------|-----------|----------|
| 2021 | 1609459200000 | 1640995200000 |
| 2022 | 1640995200000 | 1672531200000 |
| 2023 | 1672531200000 | 1704067200000 |
| 2024 | 1704067200000 | 1735689600000 |
| 2025 | 1735689600000 | 1767225600000 |

---

## 9. Pre-Registered MTC-001 Fragility Gates

All gates from MTC-001 Section 4 and Section 5 are pre-registered as the
default evaluation framework. No deviations.

### 9.1 Trade Count Floors (Dimension 6)

| Gate | Minimum |
|------|---------|
| Total closed trades | >= 100 |
| 2023+2024+2025 trade floor | >= 60 |
| Independent positive years | >= 2 |
| Winner count | >= 15 |

If any floor is not met: INSUFFICIENT_EVIDENCE.

### 9.2 Top-N Removal (Dimension 1)

| Gate | PASS | PAUSE_FRAGILE | REJECT |
|------|------|--------------|--------|
| Top-1 net excluding | > 0 | >= 0 marginally | < 0 |
| Top-3 net excluding | > 0 | Near 0 (within 10% of net) | < 0 |
| Top-5 net excluding | > 0 | Near 0 | < 0, magnitude > 50% of net |

Primary gate: **Top-3 net excluding > 0** for PASS.

### 9.3 Year-by-Year (Dimension 2)

- At least 2 years independently positive after costs.
- No single year contributing > 60% of total net PnL.
- Single year > 80% triggers REJECT.

### 9.4 Winner Attribution (Dimension 3)

For each top-5 winner: market condition, structural vs anomalous,
frozen-rule reproducibility. Requires Owner judgment.

### 9.5 MFE / MAE / Giveback (Dimension 4)

- MFE should be materially larger than realized winner.
- MAE should be bounded by initial stop.
- Maximum giveback should not exceed 2x average winner.

### 9.6 Drawdown (Dimension 5)

- MTM MaxDD up to 15% acceptable for research evidence.
- Realized MaxDD reported separately.

### 9.7 Funding (Dimension 7)

- Report aggregate and per-trade funding cost.
- Flag if funding > 20% of gross PnL.

### 9.8 Classification Flow

1. Trade count floors met? No -> INSUFFICIENT_EVIDENCE.
2. Net PnL > 0? No -> REJECT.
3. PF > 1.0? No -> REJECT.
4. Top-1 net excluding > 0? No -> REJECT.
5. Top-3 net excluding > 0? No -> PAUSE_FRAGILE.
6. Top-5 + year-by-year evaluation -> PASS / Owner judgment / REJECT.

### 9.9 CPM Drift Gate (Direction D Specific)

In addition to the standard MTC-001 gates, the following Direction D
specific gate applies:

| Check | PASS | FAIL |
|-------|------|------|
| 2021 gross edge | Positive | Negative (same as CPM-1) |
| Loss clustering | Different from CPM-1's sub-regime pattern | Same sub-regimes as CPM-1 |
| Year-by-year profile | Different from CPM-1 | Similar to CPM-1 |

If 2+ of 3 checks fail, reclassify as CPM variant and stop.

---

## 10. Risks And Stop Conditions

### 10.1 Risk: CPM Variant Drift

**Risk:** Direction D is conceptually pullback-continuation. If the frozen
experiment produces CPM-1-like results (2021 failure, similar loss
clustering, similar year profile), this is evidence that the mechanism is
not structurally different despite the 4h/structural modifications.

**Stop condition:** 2+ of 3 CPM drift checks fail.

**Action:** Reclassify as CPM variant. Do not continue parameter search.
Archive result. Return to Strategy Direction Map.

### 10.2 Risk: Thin Signal Count

**Risk:** Direction D's combined zone-touch + resumption-confirmation
condition may produce fewer signals than expected, especially if the
EMA20 reclaim confirmation is restrictive. If signal count falls below
the MTC-001 floor (100 total), the experiment is INSUFFICIENT_EVIDENCE.

**Stop condition:** Total closed trades < 80 (early stop, before full
5-year run completes).

**Action:** Stop. Report INSUFFICIENT_EVIDENCE. Do not loosen the
confirmation condition (that would be parameter rescue).

### 10.3 Risk: Inflated Signal Count

**Risk:** In weak trends where EMA20 is close to EMA60, the resumption
confirmation is easily achieved. This may produce many signals in weak
trends where pullback-continuation has low probability of success.

**Diagnostic:** If signal count > 300, flag as potentially inflated.
Review the year-by-year signal distribution. If > 50% of signals occur
in years with EMA60 slope near zero, the signal quality is suspect.

**Action:** Report the finding. Do not tighten the confirmation condition
(that would be parameter rescue in the other direction).

### 10.4 Risk: Fragility Not Improved

**Risk:** Direction D's top-3 exclusion is negative (same as Direction
A's -443.91 or worse). Pullback entry does not improve winner
concentration relative to breakout entry.

**Stop condition:** Top-3 net excluding < -500 (worse than Direction A).

**Action:** Classification per MTC-001 gates. If PAUSE_FRAGILE, Owner
decides whether to continue or archive.

### 10.5 Risk: Worse Drawdown Than Direction A

**Risk:** Direction D's MTM MaxDD exceeds Direction A's 8.33% materially.
Pullback entries during corrections may produce larger open losses than
breakout entries.

**Diagnostic:** If MTM MaxDD > 20%, flag as materially worse than
Direction A (8.33%) and Direction C (15.01%).

**Action:** Report the finding. Classification per MTC-001 gates (15%
threshold for research evidence).

### 10.6 Risk: High Overlap With Direction A

**Risk:** Direction D's signals substantially overlap with Direction A's,
meaning the two directions are capturing the same trades from different
entry points. If overlap > 50%, Direction D is not a structurally
independent direction — it is a Direction A entry-timing variant.

**Stop condition:** Overlap with Direction A > 50%.

**Action:** Reclassify as Direction A variant. Stop. Return to Strategy
Direction Map.

---

## 11. Owner Questions

### Q1: Is Direction D Worth The Experiment?

Direction D is conceptually pullback-continuation — the same family as
CPM-1. CPM-1 failed. Direction D has three structural modifications (4h
timeframe, zone-based location, structural confirmation) that are
meaningful but unproven.

The experiment is justified if the Owner accepts:

- The mechanism is plausibly different (not proven different).
- The CPM drift check is mandatory.
- The experiment may confirm that pullback-continuation as a family is
  flawed, not just CPM-1's specific implementation.

If the Owner judges that CPM-1's failure is sufficient evidence against
pullback-continuation as a family, Direction D should be classified as
REJECT_BY_FAMILY without experiment.

### Q2: Should Direction D Be Tested Before Or After Direction A Validation?

Direction A has an ongoing validation path (TE-007a). Direction D is
untested. If the Owner wants to prioritize evidence accumulation:

- **Test Direction D first**: more information about whether pullback
  entry works at all, before committing to Direction A validation.
- **Complete Direction A validation first**: establish the breakout
  baseline before testing alternatives.
- **Parallel**: run both if resources allow, but Direction D requires a
  new research adapter (Level 3 authorization).

### Q3: What If Direction D Shows Promise But The CPM Drift Check Fails?

If Direction D has positive net PnL and PF > 1.0, but the CPM drift
check shows CPM-1-like behavior (2021 failure, similar clustering), the
Owner must decide:

- **Accept as pullback-continuation with narrow applicable market**: the
  mechanism works in specific conditions (like CPM-1 in 2024/2025) but
  fails in others (like CPM-1 in 2021). This is a PAUSE_FRAGILE result
  with an explicit applicable-market boundary.
- **Reject as CPM variant**: the pullback-ending question itself is
  flawed. Archive and move to a non-pullback direction.

### Q4: Should Alternative Zone Definitions Be Reserved For Future Experiments?

The current inspect freezes EMA60 as the zone. Other zone types
(structure levels, Fibonacci zones, Donchian channel levels) are valid
alternatives. If the Owner approves Direction D:

- **Reserve alternative zones for future experiments only if EMA60
  produces RESEARCH_PASS or PAUSE_FRAGILE with positive net.**
- **Do not run alternative zones as sensitivity analysis on the current
  experiment** (that would be zone-definition parameter search).

---

## 12. Recommendation

### 12.1 Inspect Classification

| Field | Value |
|-------|-------|
| Direction | D — Structured Pullback / Value-Zone Entry |
| Mechanism | 4h EMA60 pullback + EMA20 resumption confirmation |
| MTC family | Main Trend Capture (pullback-continuation variant) |
| Relationship to CPM-1 | Conceptually same family; structurally different mechanism |
| Evidence | None (direction-level concept only) |
| MTC-001 classification | Not yet evaluated |
| Allowed next | Level 3 experiment (with Owner approval) |

### 12.2 Recommendation

**Approve inspect. Propose Level 3 experiment with conditions.**

Rationale:

1. Direction D addresses a real problem (Direction A's late breakout, thin
   winner distribution) with a mechanism that is structurally different
   from both Direction A (breakout) and Direction C (contraction).
2. The 4h/zone/structural modifications are meaningful — not parameter
   tweaks — and deserve empirical evaluation.
3. The CPM drift check provides a clear stop condition if the mechanism
   turns out to be CPM-1 repackaged on 4h.
4. The experiment is self-contained: one frozen zone definition, one
   confirmation method, no parameter sweep.

Conditions for Level 3 experiment:

1. Owner approves the inspect.
2. CPM drift check is mandatory.
3. One frozen zone definition (EMA60); no alternatives in this run.
4. One frozen confirmation method (EMA20 reclaim); no alternatives in
   this run.
5. Direction A overlap measurement is mandatory.
6. No parameter sweep, sensitivity analysis, or zone-definition search.
7. No runtime/profile/risk/backtester changes.

### 12.3 What If The Owner Decides Not To Approve

If the Owner judges that pullback-continuation as a family is not worth
testing after CPM-1's failure:

- Classify Direction D as REJECT_BY_FAMILY.
- Move to Direction F (backlog) or define a new non-pullback direction.
- The Main Trend Capture research continues with breakout-based and
  state-based entries only.

### 12.4 No Promotion Conclusion

This inspect does not provide a promotion conclusion. Direction D is not a
small-live candidate. The project still has no deployable small-live
strategy candidate. The small-live readiness gate remains unmet.

---

## 13. Explicit Prohibitions

The following are not authorized under this inspect:

- No backtest execution.
- No code or adapter implementation.
- No parameter sweep.
- No zone-definition search (EMA, Fibonacci, structure, Donchian).
- No EMA period sweep (EMA20, EMA50, EMA100, etc.).
- No confirmation-method search (swing-high reclaim, inside bar, etc.).
- No CPM-1 parameter rescue.
- No CPM-2 auto-start.
- No Candidate C (CPM) activation.
- No Direction A reopening.
- No Direction C parameter adjustment.
- No runtime/profile/risk/backtester changes.
- No strategy router, portfolio engine, or regime system.
- No multi-asset or multi-timeframe expansion.
- No live deployment or small-live approval.
- No strategy implementation.
- No backtester or research engine modification.

---

## 14. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-07 | Initial Direction D inspect v0 | Claude Code (MTC-005) |
