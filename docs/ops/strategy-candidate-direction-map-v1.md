# Strategy Candidate Direction Map v1

**Task ID:** SCDM-001
**Date:** 2026-05-06
**Status:** Proposed / Direction Map Only
**Scope:** Baseline Strategy Module Stabilization — strategy research direction map

This document is a research roadmap. It is not experiment authorization, not
runtime promotion approval, not parameter tuning approval, not live enablement
approval, and not a backtest execution request.

**No code, no backtest, no adapter, no runtime change, no profile change, no
risk-rule change, no promotion conclusion, and no small-live conclusion follows
from this document.**

---

## 1. Purpose

Summarize all closed strategy directions, codify the Owner's strategy research
thesis, establish a candidate direction pool for future main-trend-capture
research, define evaluation principles for sparse trend profits, and recommend
next-step priorities.

This map replaces no existing governance document. It sits between the closed
NSC series and any future NSC that might open a new candidate direction.

---

## 2. Closed Directions Summary

| Direction | ID | Closure Classification | Key Evidence | Date Closed |
|-----------|----|----------------------|--------------|-------------|
| CPM-1 (ETH 1h Pinbar pullback-continuation) | CPM-1 | Paused — favorable-regime profit hypothesis failure | 2021 OOS -21.54% (gross negative), 2022 OOS -9.72% (cost-dominated) | 2026-05-06 |
| CPM-2 Candidate A (one-bar continuation reclaim) | NSC-005 | INSUFFICIENT_EVIDENCE | 56 positions, -973 net | 2026-05-06 |
| CPM-2 Candidate B (Donchian-location pullback confirmation) | NSC-005 | INSUFFICIENT_EVIDENCE | 135 positions, -5682 net | 2026-05-06 |
| CPM-2 Candidate C (two-candle pullback-end) | NSC-001 | Reserve-only, never activated | Not tested | — |
| T1-A (4h main-trend capture, ATR trailing exit) | NSC-009/010 | INSUFFICIENT_EVIDENCE_THIN_SAMPLE | Net +368, PF 1.07, but top-1 winner = 98.47% of net; 2023-2025 trade floor not met (54 vs 60) | 2026-05-06 |
| T1-B (4h qualification + 1h entry) | NSC-008 | Reserve-only, never activated | Not tested | — |

**Current state: No deployable small-live strategy candidate exists. Small-live
readiness gate remains unmet.**

---

## 3. Owner Strategy Research Thesis

### 3.1 Core Thesis: Main Trend Lifecycle Capture

The Owner's research preference converges on capturing the lifecycle of main
trends rather than trading local pullback segments. This is a structural
departure from the CPM family.

| Dimension | CPM Family | Main Trend Capture |
|-----------|-----------|-------------------|
| Primary timeframe | 1h | 4h |
| Strategy type | Pullback-continuation (local segment) | Trend-lifecycle (full move or major portion) |
| What it tries to earn | Pullback reversal into continuation | Trend initiation, trend middle, or trend continuation after pullback |
| Typical hold | Short (hours to 1-2 days) | Longer (days to weeks) |
| Win rate expectation | Moderate (30-40%) | Low (20-35% acceptable) |
| Profit distribution | Many small wins, few large losses | Few large wins, many small losses |
| Exit philosophy | Fixed TP/SL or ATR trailing | Trend-structure break, EMA close-break, or trailing |

### 3.2 Accepted Trade-offs

The Owner explicitly accepts:

- **Low win rate** — 20-35% is acceptable if payoff ratio compensates.
- **Sparse profits** — Revenue concentration in few trades is expected, not a
  defect, provided concentration risk is monitored.
- **Profit giveback** — Holding through retracements within a trend is
  acceptable; some profit giveback is the cost of capturing the full move.
- **High payoff ratio** — Winners must be significantly larger than losers;
  payoff ratio > 2.5 is the structural expectation.

### 3.3 Evaluation Shift

Evaluation focus moves from CPM-era metrics to trend-lifecycle metrics:

| From (CPM era) | To (Trend lifecycle) |
|----------------|---------------------|
| Win rate, profit factor | MFE/MAE, giveback ratio, top-winner concentration |
| Smooth equity curve | Trend profit shape (lumpy is acceptable) |
| Monthly consistency | Year-by-year explainability |
| Trade count per year | Sufficient sample across market regimes |
| Fixed TP hit rate | Exit family comparison (structure vs indicator vs time) |
| Gross edge before costs | Net edge after funding, slippage, and real cost model |

### 3.4 Research-to-Runtime Firewall

Research results — however promising — must not directly enter runtime,
profile, risk, or promotion decisions. The research-to-runtime path requires:

1. Frozen rule definition before experiment.
2. Pre-registered pass/pause/reject gates.
3. OOS validation on unseen data.
4. Owner review before any state change.
5. No parameter rescue after seeing results.

---

## 4. Candidate Direction Pool

### Direction A: 4h Main Trend Lifecycle Capture

**Strategy hypothesis:** A 4h candle close above a structural level (EMA,
swing high, breakout level) signals trend initiation or continuation. Enter
with the trend and hold until the trend structure breaks.

**What it earns:** Trend initiation (entering early in a new trend) and trend
middle (capturing the bulk of a sustained move).

**What CPM/T1-A failure it addresses:** CPM-1 failed because 1h pullback
continuation has no edge in unfavorable regimes and negative gross edge even in
favorable regimes. T1-A showed a positive signal but was dominated by a single
winner and failed the trade-floor gate. Direction A targets the same trend
moves but with a different entry mechanism (structure break vs Pinbar pullback)
and a different exit philosophy (trend-lifecycle exit vs ATR trailing).

**4h and 1h roles:** 4h is the sole decision timeframe. 1h is not used.

**New data capability needed:** No. 4h OHLCV is already available.

**Portfolio / regime / multi-strategy / multi-asset:** No. Standalone only.

**Validation cost:** Low. Single timeframe, single asset, frozen rule.

**Sample size risk:** Moderate. 4h produces fewer signals than 1h. Trade count
floors must be adjusted accordingly (see Section 10).

**Overfit risk:** Low-Moderate. Fewer parameters than CPM family. Main risk is
exit parameter selection.

**Closure ease:** High. If the frozen rule fails the evidence gate, the
direction is cleanly paused or rejected.

**Current-stage fit:** High. This is the most direct continuation of the T1-A
signal with a different exit family.

**Recommended priority:** **P0** — most natural next step from T1-A evidence.

---

### Direction B: 4h Main Trend + 1h Retrace/Entry Optimization

**Strategy hypothesis:** Use 4h to qualify trend state (direction, strength,
phase), then use 1h to time entry on a retrace within the 4h trend. The 4h
trend governs; 1h is a timing tool only.

**What it earns:** Trend continuation after pullback — entering at a better
price within an established trend, reducing initial risk.

**What CPM/T1-A failure it addresses:** CPM-1's failure was not about
pullback timing per se — it was about 1h pullback continuation having no
structural edge. Direction B keeps pullback logic but subordinates it to 4h
trend qualification, changing the structural relationship from "1h pullback is
the strategy" to "4h trend is the strategy, 1h pullback is the entry."

**4h and 1h roles:** 4h = trend qualification (direction filter, phase
identification). 1h = entry timing (retrace to structure, value-zone entry).
1h must not re-become the primary decision layer.

**New data capability needed:** No. Both timeframes already available.

**Portfolio / regime / multi-strategy / multi-asset:** No. Standalone only.

**Validation cost:** Moderate. Two-timeframe logic adds complexity. Must
prevent 1h from dominating.

**Sample size risk:** Moderate-High. 1h entry conditions may over-filter,
reducing trade count below floors.

**Overfit risk:** Moderate-High. Two-timeframe systems have more degrees of
freedom. Must freeze 1h entry rules before experiment.

**Closure ease:** Moderate. If 1h adds no value over pure 4h (Direction A),
the 1h layer is removed. If 1h dominates, the direction violates the 4h-first
principle and must be reclassified.

**Current-stage fit:** Moderate. T1-B was reserve-only for this reason. The
risk of 1h re-dominating is real and must be structurally guarded.

**Recommended priority:** **P1** — testable after Direction A baseline is
established, to measure whether 1h timing adds value.

---

### Direction C: Volatility Contraction / Re-expansion Within Trend

**Strategy hypothesis:** Within an established trend, volatility contracts
(narrow range bars, decreasing ATR, Bollinger squeeze) before the next
impulse. Enter on the breakout from contraction, in the direction of the
trend.

**What it earns:** Trend continuation — specifically the impulse phase that
follows a consolidation within a trend.

**What CPM/T1-A failure it addresses:** CPM-1 entered on Pinbar (a single-candle
pattern) which is noise-prone on 1h. Direction C uses a multi-candle
contraction pattern which is structurally more robust and occurs at 4h scale.

**4h and 1h roles:** 4h identifies trend direction and contraction. 1h may
confirm breakout but must not be the primary trigger.

**New data capability needed:** No. ATR, Bollinger, or range calculations are
derivable from OHLCV.

**Portfolio / regime / multi-strategy / multi-asset:** No. Standalone only.

**Validation cost:** Moderate. Contraction definition must be frozen. Multiple
contraction metrics (ATR ratio, Bollinger width, range contraction) could
create parameter space.

**Sample size risk:** High. Contraction-then-expansion events are infrequent.
Trade count may be very low.

**Overfit risk:** Moderate-High. Contraction threshold and duration are
tunable parameters. Must freeze before experiment.

**Closure ease:** Moderate. If contraction patterns don't predict direction
reliably, the hypothesis is cleanly falsified.

**Current-stage fit:** Moderate. Interesting structural hypothesis but sample
size risk is significant.

**Recommended priority:** **P1** — worth a docs-only inspect after Direction A
has a baseline, but sample size may make it impractical.

---

### Direction D: Non-Pinbar Structured Pullback / Value-Zone Entry

**Strategy hypothesis:** Instead of Pinbar (which CPM-1 showed has no
structural edge), use a structured pullback definition: price retraces to a
value zone (EMA zone, previous structure level, Fibonacci zone) within a 4h
trend, then resumes. Entry on confirmation of resumption, not on the candle
pattern itself.

**What it earns:** Trend continuation after pullback — similar to Direction B
but with a different pullback definition (zone-based vs candle-pattern-based).

**What CPM/T1-A failure it addresses:** CPM-1's Pinbar trigger was identified
as noise-prone and regime-sensitive. Direction D replaces the trigger with a
zone-based approach that is less dependent on single-candle morphology.

**4h and 1h roles:** 4h defines the value zone and trend. 1h may confirm
resumption but must not be the primary trigger.

**New data capability needed:** No. EMA, swing levels, and Fibonacci ratios
are derivable from OHLCV.

**Portfolio / regime / multi-strategy / multi-asset:** No. Standalone only.

**Validation cost:** Moderate. Value-zone definition must be frozen. Multiple
zone definitions could create parameter space.

**Sample size risk:** Moderate. Value-zone touches within trends are more
frequent than contraction events but less frequent than 1h Pinbar signals.

**Overfit risk:** Moderate. Zone width and confirmation rules are tunable.
Must freeze before experiment.

**Closure ease:** High. If value-zone entries don't outperform random entries
within trends, the hypothesis is cleanly falsified.

**Current-stage fit:** Moderate-High. Directly addresses CPM-1's trigger
weakness while staying in the pullback-entry family.

**Recommended priority:** **P1** — worth a docs-only inspect; may compete with
Direction B for the "pullback within trend" slot.

---

### Direction E: Trend Failure / False Breakout Avoidance Rule

**Strategy hypothesis:** Not a standalone entry strategy. Instead, a filter or
exit rule that identifies when a trend is failing (false breakout, momentum
divergence, structure break against position) and either prevents entry or
triggers early exit.

**What it earns:** Loss avoidance — reducing the cost of being wrong about a
trend, rather than earning from being right.

**What CPM/T1-A failure it addresses:** T1-A's top-1 winner was 98.47% of net
profit, meaning most trades were losers or near-breakeven. Direction E targets
the losing trades: if trend failures can be identified earlier, the loss per
failed trade decreases, and the net edge improves without needing more winners.

**4h and 1h roles:** 4h identifies trend failure. 1h may provide earlier
failure signal but must not become a separate strategy layer.

**New data capability needed:** No. Structure breaks, momentum divergence, and
EMA crossovers are derivable from OHLCV.

**Portfolio / regime / multi-strategy / multi-asset:** No. This is a rule, not
a strategy.

**Validation cost:** Low-Moderate. Can be tested as an overlay on existing T1-A
data.

**Sample size risk:** Low. Failure events are common (most trades in T1-A were
failures).

**Overfit risk:** Moderate. Failure criteria must be frozen. Risk of
hindsight-driven failure definition.

**Closure ease:** High. If the rule doesn't reduce average loss per failed
trade, it's cleanly removed.

**Current-stage fit:** High. Directly addresses T1-A's biggest weakness
(concentration risk) by improving the losing side.

**Recommended priority:** **P0** — should be developed in parallel with
Direction A, as an exit/filter family member.

---

### Direction F: Funding / OI / Crowding-Aware Trend Filter

**Strategy hypothesis:** Trend-following in crypto is crowded. When funding
rates are extreme, OI is at local highs, and crowd positioning is one-sided,
the risk of a squeeze or reversal increases. Use funding/OI/crowding data as
a filter on trend entries: reduce position size, widen stops, or skip entries
when crowding metrics are extreme.

**What it earns:** Loss avoidance during crowded trend setups that are more
likely to reverse or squeeze.

**What CPM/T1-A failure it addresses:** CPM-1's 2021 loss was concentrated in
Aug-Oct, which included the post-May-crash choppy period where trend-following
was crowded and unprofitable. Direction F could have filtered some of these
periods.

**4h and 1h roles:** Neither. Funding/OI data is timeframe-independent. It
acts as a regime overlay on any entry.

**New data capability needed:** **Yes.** Funding rate, open interest, and
possibly long/short ratio data are not currently in the research pipeline.
This requires new data ingestion and storage.

**Portfolio / regime / multi-strategy / multi-asset:** This is a regime-aware
filter, which touches the regime capability pool. Must remain a simple filter,
not a regime system.

**Validation cost:** High. Requires new data pipeline before any experiment.

**Sample size risk:** Moderate. Extreme funding/OI events are infrequent but
identifiable.

**Overfit risk:** Moderate. Thresholds for "extreme" are tunable. Must freeze
before experiment.

**Closure ease:** Moderate. If the filter doesn't improve risk-adjusted
returns, it's removed. But the data pipeline cost is sunk.

**Current-stage fit:** Low. New data capability needed. This is a later-stage
enhancement, not a first candidate.

**Recommended priority:** **P2** — mark as future direction. Do not start
until a baseline trend strategy (Direction A) has evidence.

---

### Direction G: Range / Consolidation Module

**Strategy hypothesis:** Markets spend significant time in ranges. A range
module could earn during non-trending periods by buying support and selling
resistance within a defined range.

**What it earns:** Mean-reversion profits during consolidation.

**What CPM/T1-A failure it addresses:** None directly. This is a different
market regime entirely.

**4h and 1h roles:** Either timeframe could define the range. 1h may be more
appropriate for range trading than for trend trading.

**New data capability needed:** No. Range detection is derivable from OHLCV.

**Portfolio / regime / multi-strategy / multi-asset:** This is a separate
strategy module, which touches the multi-strategy capability pool. Must remain
research-only.

**Validation cost:** Moderate. Range definition and exit rules must be frozen.

**Sample size risk:** Moderate. Range periods are common but defining them
precisely is difficult.

**Overfit risk:** High. Range boundaries are highly tunable.

**Closure ease:** Moderate.

**Current-stage fit:** Low. The Owner's thesis is trend capture, not range
trading. This direction is explicitly not the current主线.

**Recommended priority:** **P2** — future direction, not current主线. Marked
for completeness only.

---

## 5. 1h Timeframe Positioning

The 1h timeframe has a specific and bounded role in the direction map:

| Role | Allowed | Not Allowed |
|------|---------|-------------|
| Validation proxy for 4h trend state | Yes | — |
| Entry timing within 4h-qualified trend | Yes | — |
| Confirmation of 4h signal (e.g., 4h breakout + 1h follow-through) | Yes | — |
| Primary decision timeframe | — | No |
| Standalone strategy layer | — | No |
| CPM-style local segment strategy | — | No |
| Re-dominating strategy logic | — | No |

**Guard rail:** If 1h results cannot be mapped back to 4h trend logic, the
1h component must be flagged as a separate strategy and evaluated
independently. It must not be silently absorbed into the 4h strategy.

---

## 6. Exit Research Priority

Exit research is not subordinate to entry research. Both are first-class.

### 6.1 Exit Family

The following exit mechanisms form the exit family for trend-lifecycle
strategies:

| Exit | Type | Hypothesis | Status |
|------|------|-----------|--------|
| EMA60 close-break exit | Trend-structure exit | When price closes below EMA60 on 4h, the trend is over or weakening. Exit. | **Priority 1** — this is a trend-lifecycle exit hypothesis, not a T1-A ATR trailing parameter rescue |
| ATR trailing stop | Volatility trailing | Trail stop at N×ATR from peak. Captures most of the move but gives back on volatility spikes. | Tested in T1-A; insufficient alone. May combine with structure exit. |
| Structure trailing (swing-low trailing) | Structure trailing | Trail stop below the most recent 4h swing low. Adapts to market structure. | Not yet tested. |
| N-bar low exit | Time-structure exit | Exit if price makes a new N-bar low. Simple, no parameter tuning. | Not yet tested. |
| Partial TP + runner | Hybrid | Take partial profit at a defined level (e.g., 1R or 2R), let remainder run with trailing. | Not yet tested. Balances profit capture with trend capture. |

### 6.2 Exit Priority Rules

1. **EMA60 close-break exit is the primary trend-lifecycle exit hypothesis.**
   It must be tested first, as a standalone exit, not as a parameter variant
   of ATR trailing.

2. **ATR trailing is a secondary exit.** It was tested in T1-A and showed
   concentration risk. It may be combined with structure exit but must not be
   the sole exit.

3. **Structure trailing and N-bar low are alternative hypotheses.** They
   should be tested after EMA60 close-break has a baseline.

4. **Partial TP + runner is a hybrid.** It should be tested last, as it
   introduces the most parameters (TP level, runner exit rule).

5. **No exit parameter sweep.** Each exit variant must be frozen before
   experiment. No post-result optimization of exit parameters.

---

## 7. Sparse Trend Profit Principles

These principles govern evaluation of all trend-lifecycle candidates:

| # | Principle | Rationale |
|---|-----------|-----------|
| 1 | Low win rate is acceptable | Trend strategies are inherently low-frequency; payoff ratio must compensate |
| 2 | Profit concentration is expected | Few large winners are the structural profit source, not a defect |
| 3 | Profit giveback is acceptable | Holding through retracements is the cost of capturing full moves |
| 4 | No single-anomaly-year dependency | A strategy that works only in one exceptional year (e.g., 2021 bull) is not robust. Year-by-year explainability is required. |
| 5 | Top-winner fragility must be tested | Removing the top-1 or top-3 winners must not make the strategy net-negative. If it does, the edge is not structural. |
| 6 | Cost/funding/slippage must not be relaxed | Realistic cost model is non-negotiable. Funding, slippage, and fees must be included at SSOT rates. |
| 7 | No parameter sweep to rescue a strategy | If a frozen rule fails, classify the failure. Do not search parameter space for a passing configuration. |
| 8 | Research-only proxy must not become official validation | Research adapters produce proxy evidence, not promotion-grade evidence. The evidence hierarchy (Official > Proxy, Full-window > Single-year) must be respected. |

---

## 8. Candidate Direction Priority Ranking

### P0 — Most Worth Next Docs-Only Inspect / Plan

| Direction | Why P0 | Next Step |
|-----------|--------|-----------|
| **A: 4h Main Trend Lifecycle Capture** | Most direct continuation of T1-A signal; addresses CPM-1 structural failure; lowest validation cost; cleanest closure | Docs-only inspect: define frozen rule with EMA60 close-break exit as primary exit, specify trade count floors adjusted for 4h, specify evidence gates |
| **E: Trend Failure / False Breakout Avoidance Rule** | Directly addresses T1-A's concentration risk; can be tested as overlay on existing T1-A data; complements Direction A | Docs-only inspect: define failure criteria, specify how it integrates with Direction A entry+exit |

### P1 — Available as Backup

| Direction | Why P1 | Next Step |
|-----------|--------|-----------|
| **B: 4h Main Trend + 1h Retrace/Entry** | Natural extension of Direction A; tests whether 1h timing adds value; but 1h re-dominance risk must be guarded | Pause until Direction A has baseline evidence. Then docs-only plan with 1h guard rails. |
| **C: Volatility Contraction / Re-expansion** | Interesting structural hypothesis; but sample size risk is significant | Docs-only inspect after Direction A baseline. Assess sample feasibility before experiment plan. |
| **D: Non-Pinbar Structured Pullback / Value-Zone** | Directly addresses CPM-1 trigger weakness; but overlaps with Direction B | Docs-only inspect. May compete with Direction B for the "pullback within trend" slot. |

### P2 — Reserved, Not Started

| Direction | Why P2 | Next Step |
|-----------|--------|-----------|
| **F: Funding / OI / Crowding-Aware Filter** | Needs new data pipeline; touches regime capability pool; high validation cost | Mark as future direction. Do not start until Direction A has evidence and data pipeline is available. |
| **G: Range / Consolidation Module** | Different regime entirely; not aligned with Owner's trend-capture thesis | Mark as future direction. Not current主线. |

### Not-Now — Explicitly Not Done

| Item | Why Not-Now |
|------|------------|
| Continue rescuing CPM-1 | Favorable-regime profit hypothesis failure; 2021 OOS gross negative; no path forward |
| Continue rescuing CPM-2 A/B | INSUFFICIENT_EVIDENCE closed; both candidates net-negative |
| Auto-start Candidate C | Reserve-only; no activation trigger |
| T1-A parameter rescue | Frozen rule failed evidence gate; no post-result parameter sweep |
| Donchian / ATR / EMA / lookback sweep | Parameter sweep is explicitly prohibited by sparse trend profit principles |
| T1 + CPM-1 portfolio combination | Portfolio engine is Not-Now; combination does not fix structural failure |
| Portfolio engine | Capability pool item; not current active track |
| Regime system | Capability pool item; not current active track |
| Multi-strategy runtime | Capability pool item; not current active track |
| Multi-asset expansion | Capability pool item; not current active track |
| Full data feature store | Infrastructure expansion; not driven by current strategy need |
| Complex ML | Overfit risk too high for current sample sizes; not aligned with explainability requirement |
| Tick / orderbook simulator | Infrastructure expansion; not driven by current strategy need |
| Promotion or small-live conclusion | No candidate has passed evidence gates; small-live readiness gate remains unmet |

---

## 9. Recommended Next Steps

### 9.1 Top 2-3 Research Directions

1. **Direction A (4h Main Trend Lifecycle Capture) with EMA60 close-break
   exit** — This is the most natural next step. It directly continues the T1-A
   signal with a different exit hypothesis. The frozen rule should specify:
   - 4h entry condition (trend qualification)
   - EMA60 close-break as primary exit
   - Trade count floors adjusted for 4h (lower than 1h floors)
   - Same cost model SSOT as NSC-008
   - Fragility gate (top-winner removal test)
   - Year-by-year explainability requirement

2. **Direction E (Trend Failure Avoidance Rule)** — This should be developed
   in parallel with Direction A. It targets the losing side of trend trading
   and can be tested as an overlay on existing T1-A data before being applied
   to Direction A.

3. **Direction B (4h + 1h Entry Timing)** — Reserve for after Direction A
   baseline. The key question is whether 1h timing adds value over pure 4h
   entry, and the answer requires Direction A as the control.

### 9.2 Next Step Type per Direction

| Direction | Next Step | Rationale |
|-----------|-----------|-----------|
| A | **Docs-only inspect** | Define frozen rule, exit hypothesis, evidence gates, trade count floors. Not yet ready for experiment plan — need to specify the 4h entry condition precisely. |
| E | **Docs-only inspect** | Define failure criteria, integration with Direction A. Can be done in parallel with Direction A inspect. |
| B | **Pause** | Wait for Direction A baseline. |
| C | **Pause** | Wait for Direction A baseline; then assess sample feasibility. |
| D | **Pause** | Wait for Direction A baseline; then compare with Direction B. |
| F | **Pause** | Wait for data pipeline and Direction A evidence. |
| G | **Pause** | Not current主线. |

### 9.3 Task Card Recommendation

If the Owner approves Direction A and E as next priorities:

- **NSC-011**: Docs-only inspect for Direction A (4h Main Trend Lifecycle
  Capture with EMA60 close-break exit). Scope: define frozen rule, specify
  entry condition, specify exit family, specify evidence gates, specify trade
  count floors for 4h.

- **NSC-012**: Docs-only inspect for Direction E (Trend Failure Avoidance
  Rule). Scope: define failure criteria, specify overlay test on T1-A data,
  specify integration with Direction A.

These should be separate task cards, not bundled.

### 9.4 Small-Live Readiness Gate

**Small-live readiness gate remains unmet.** No candidate has passed minimum
evidence gates. This document does not change that status.

---

## 10. Trade Count Floor Adjustment for 4h

4h candles produce fewer signals than 1h. The NSC-008 trade count floors were
designed for T1-A which uses 4h entry. For future 4h-based candidates:

| Metric | NSC-008 Floor (T1-A) | Proposed 4h Floor | Rationale |
|--------|---------------------|-------------------|-----------|
| 2021+2022 minimum | 20 positions | 15 positions | 4h produces fewer signals; 2-year window at 4h is a reasonable minimum |
| 2023+2024+2025 minimum | 60 positions | 40 positions | Same rationale; must still demonstrate repeatability |
| Total minimum | 80 positions | 55 positions | Must still be sufficient for meaningful statistics |
| Fragility gate | Top-1 removal must keep net positive | Same | Non-negotiable regardless of timeframe |

These are proposed starting points for the Direction A inspect. They must be
confirmed or adjusted in the inspect document before any experiment.

---

## 11. Relationship to Existing Governance

| Document | Relationship |
|----------|-------------|
| project-roadmap-v2.md | High-level scope authority; this map stays within Baseline Strategy Module Stabilization track |
| live-safe-v1-program.md | No live-safe code, runtime, or risk-rule changes |
| agent-working-rules.md | Claude task card rules apply; this map is not a task card |
| codex-claude-handoff-template.md | Any future implementation requires a Codex-issued task card |
| NSC-007 | This map supersedes NSC-007's direction recommendation; T1-lite is now part of the broader Direction A |
| NSC-008 | T1-A experiment plan is closed; Direction A is a new candidate, not a continuation of T1-A |
| NSC-009/010 | T1-A closure evidence feeds into Direction A and E design |
| CPM-OOS-FAILURE-CLASSIFY-001 | CPM-1 failure classification is the primary motivation for departing from pullback-continuation |
| CPM-CRITERIA-001 | Promotion/rejection criteria framework still applies to any future candidate |

---

## 12. Not-Now List (Consolidated)

The following are explicitly not authorized by this direction map:

- No code implementation.
- No backtest execution.
- No adapter creation.
- No strategy implementation.
- No runtime change.
- No profile change.
- No risk-rule change.
- No backtester or research engine core change.
- No promotion conclusion.
- No small-live conclusion.
- No live deployment suggestion.
- No CPM-1 rescue.
- No CPM-2 A/B rescue.
- No Candidate C auto-start.
- No T1-A parameter rescue.
- No Donchian / ATR / EMA / lookback sweep.
- No T1 + CPM-1 portfolio combination.
- No portfolio engine.
- No regime system.
- No multi-strategy runtime.
- No multi-asset expansion.
- No full data feature store.
- No complex ML.
- No tick / orderbook simulator.

---

## 13. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-05-06 | Initial Strategy Candidate Direction Map v1 | Codex (SCDM-001) |
