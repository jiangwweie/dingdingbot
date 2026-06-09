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

# NSC-012 — Trend Failure / False Breakout Avoidance Companion Inspect

**Task ID:** NSC-012
**Date:** 2026-05-06
**Status:** Proposed / Companion Direction Inspect Only
**Scope:** Docs-only direction inspect
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document inspects Direction E as a companion research direction for
Direction A. It does not authorize experiments, code, adapters, strategy
implementation, runtime/profile/risk changes, backtester/research engine core
changes, promotion, small-live readiness, or live deployment.

This task did not run backtests, write code, create adapters, implement
strategies, tune parameters, modify runtime, modify profiles, modify risk
rules, or touch `src/`, `configs/`, `tests/`, or `migrations/`.

Inspected material:

- `docs/ops/strategy-candidate-direction-map-v1.md`
- `docs/ops/nsc-011-4h-main-trend-lifecycle-capture-direction-inspect.md`
- `docs/ops/nsc-010-t1a-thin-sample-fragility-closure-review.md`
- `reports/nsc-009-t1a-4h-main-trend-capture/**`
- related T1/T1-R/C1/C2 historical evidence under `archive/**`

---

## 1. Current State

| Field | State |
| --- | --- |
| CPM-1 | Remains paused; not a small-live candidate |
| CPM-2 Candidate A/B | Closed as research proxy insufficient |
| Candidate C | Reserve-only; not automatically started |
| T1-A frozen rule | Paused; `INSUFFICIENT_EVIDENCE_THIN_SAMPLE`; top-winner fragility failed |
| T1-B | Reserve-only; not executed |
| Direction A | NSC-011 conclusion: `PROCEED_TO_EXPERIMENT_PLAN` |
| Direction E | This companion inspect |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |

---

## 2. Direction E Identity

Direction E is:

- a companion research direction for Direction A;
- a local signal-quality / trend-failure rule family;
- a possible pre-entry skip, post-entry early exit, or diagnostic overlay;
- intended to reduce obvious bad signals or average loser size without
  deleting the main trend profit source.

Direction E is not:

- an independent strategy;
- a regime system;
- a portfolio or multi-strategy prerequisite;
- a broad market-state classifier;
- a complex ML classifier;
- a replacement for Direction A baseline;
- a rescue path for T1-A, CPM-1, or CPM-2 A/B.

Direction E earns nothing by itself. It can only be evaluated by whether it
improves the losing side of a frozen Direction A-style trend strategy while
preserving the sparse large-winner source.

---

## 3. Questions Direction E Must Answer

Direction E should answer four narrow questions:

1. Which 4h breakout / trend-continuation signals are more likely to fail?
2. Which failures can be identified before entry and therefore skipped?
3. Which failures can only be identified after entry and therefore belong to
   early exit, not filtering?
4. Which judgments require hindsight or future candles and must be forbidden?

The key distinction is timing. A feature observed after the signal cannot be
used to decide whether the signal should have been entered. It may only define
a post-entry early-exit hypothesis or a diagnostic label.

---

## 4. Lessons From NSC-009 / T1-A Failure Shape

NSC-009 showed that 4h trend-following is not signal-free, but the losing side
was not managed well enough.

| Evidence | Read |
| --- | --- |
| Closed positions | 85 |
| Net PnL | +368.18597 |
| PF | 1.07107 |
| Win rate | 42.35% |
| Losing trades | 49 of 85 |
| Trades where trailing never activated | 49 of 85 |
| Top 1 winner share | 98.47% of absolute total net |
| Net excluding top 3 | -663.37 |
| Negative years | 2022 and 2025 |
| Classification | `INSUFFICIENT_EVIDENCE_THIN_SAMPLE` |

Interpretation:

- Direction A / T1-style 4h trend capture has some trend signal.
- Most trades either lose before becoming a real runner or fail to contribute
  enough after costs/funding.
- The top winners are doing too much of the work.
- The obvious research question is not "how do we raise win rate at any
  cost?" but "can we reduce clearly bad entries or cut failed breakouts
  earlier without killing the few main-trend winners?"

Direction E may help if it reduces average loser size or skips visibly poor
signals. It should not be allowed to flatten the strategy into a smooth,
low-payoff system that misses the main trend.

Historical T1-R and C1/C2 evidence reinforces the same caution:

- corrected T1/T1-R evidence remained positive after lookahead fixes but was
  fragile;
- C1/C2 portfolio proxy evidence can warn about fragility and correlation, but
  cannot validate T1-lite standalone;
- portfolio improvements must not be used to justify portfolio engine,
  multi-strategy runtime, or T1 + CPM-1 combination work.

---

## 5. Candidate Failure / False-breakout Rule Directions

These are direction-level candidates only. They are not experiment rules and
do not authorize execution.

| ID | Direction | Timing Type | Core Idea | First-pass Fit |
| --- | --- | --- | --- | --- |
| E-A | Breakout failure after signal | Post-entry early exit | Exit if the next closed 4h bar quickly reclaims below the breakout level | Best optional overlay candidate |
| E-B | Overextension / exhaustion | Pre-entry skip or diagnostic | Avoid signals after excessive recent extension or far distance from EMA60 | Diagnostic first |
| E-C | Volatility spike / noisy breakout | Diagnostic or pre-entry skip | Identify unusually large breakout bars / ATR expansion as noisy signals | Diagnostic first |
| E-D | Weak follow-through | Post-entry confirmation or early exit | Require or react to follow-through after breakout | Not first-round; sample-risk high |
| E-E | EMA60 proximity / trend quality | Pre-entry skip or diagnostic | Distinguish healthy trend structure from late chase around EMA60 | Possible later, not first-round |
| E-F | Choppy market / range-bound warning | Diagnostic-only | Warn when local 4h structure repeatedly crosses EMA60 or failed breakouts cluster | Diagnostic-only |

---

## 6. Direction-level Comparison

### 6.1 E-A — Breakout Failure After Signal

Definition family:

- After a 4h breakout signal is entered, inspect the next fully closed 4h
  candle.
- If that candle closes back below the breakout level, the breakout has failed.
- This is an early-exit hypothesis, not a pre-entry filter, because the
  follow-up candle is not known at entry time.

| Dimension | Assessment |
| --- | --- |
| Type | Post-entry early exit |
| Failure targeted | Immediate failed breakout before trend develops |
| May reduce top-winner fragility? | Possibly, by reducing average loser and cost of false starts |
| May kill big winners? | Moderate risk if many real trends retest the breakout level before continuing |
| New data needed | No; 4h OHLCV and breakout level are already available |
| Regime / portfolio / feature store risk | None if kept as local signal rule |
| Overfit risk | Low if frozen as one-bar close-back rule; higher if bar count or buffer is searched |
| NSC-013 first-round fit | Possible only as one optional frozen overlay |
| Priority | P0 companion candidate |

Boundary:

- no sweep of one bar vs two bars vs three bars;
- no buffer sweep around the breakout level;
- no use of intrabar path after entry except under a pre-declared execution
  convention;
- no after-the-fact selection based on best PnL.

### 6.2 E-B — Overextension / Exhaustion

Definition family:

- signal occurs after unusually high recent return;
- price is too far above EMA60 at signal;
- breakout follows consecutive large bullish 4h candles.

| Dimension | Assessment |
| --- | --- |
| Type | Pre-entry skip or diagnostic |
| Failure targeted | Late chase after an already extended move |
| May reduce top-winner fragility? | Unclear; may remove bad late entries, but also likely removes strong trend starts |
| May kill big winners? | High risk |
| New data needed | No |
| Regime / portfolio / feature store risk | None if kept local |
| Overfit risk | High because recent-return and EMA-distance thresholds are tunable |
| NSC-013 first-round fit | No; diagnostic-only unless a single frozen threshold is justified before results |
| Priority | P2 diagnostic |

Boundary:

- no recent-return threshold sweep;
- no EMA-distance threshold sweep;
- no consecutive-candle count sweep;
- no using 2022/2025 failure years to backfit a cutoff.

### 6.3 E-C — Volatility Spike / Noisy Breakout

Definition family:

- breakout bar range is unusually large;
- ATR expands too quickly into the signal;
- signal may reflect liquidation/noise rather than trend initiation.

| Dimension | Assessment |
| --- | --- |
| Type | Diagnostic first; possible pre-entry skip later |
| Failure targeted | Breakouts driven by one-off volatility spike |
| May reduce top-winner fragility? | Unclear; true trend breakouts often start with range expansion |
| May kill big winners? | High risk |
| New data needed | No |
| Regime / portfolio / feature store risk | None if kept local |
| Overfit risk | High because range/ATR thresholds are tunable |
| NSC-013 first-round fit | No |
| Priority | P2 diagnostic |

Boundary:

- no ATR spike threshold sweep;
- no multi-threshold "noise filter" search;
- no direct filter use until the diagnostic proves it does not remove the
  main winners.

### 6.4 E-D — Weak Follow-through

Definition family:

- require additional 4h close confirmation after breakout;
- or exit if follow-through does not appear within a frozen short window.

| Dimension | Assessment |
| --- | --- |
| Type | Post-entry early exit or delayed-confirmation entry |
| Failure targeted | Breakouts that do not attract continuation demand |
| May reduce top-winner fragility? | Possibly, but only if it cuts losers without reducing signal count too much |
| May kill big winners? | Moderate-High risk due to delayed entry or extra confirmation |
| New data needed | No |
| Regime / portfolio / feature store risk | None |
| Overfit risk | Moderate-High because confirmation windows are tunable |
| NSC-013 first-round fit | No; may worsen thin sample |
| Priority | P1/P2 later |

Boundary:

- do not require extra confirmation in NSC-013 first pass unless Direction A
  baseline is explicitly designed around it;
- do not search confirmation bar count;
- treat it as separate from E-A unless frozen before execution.

### 6.5 E-E — EMA60 Proximity / Trend Quality

Definition family:

- signal must occur in a healthy relation to EMA60;
- price above EMA60 may qualify trend state;
- excessive distance from EMA60 may indicate late chase.

| Dimension | Assessment |
| --- | --- |
| Type | Pre-entry skip or diagnostic |
| Failure targeted | False breakout outside healthy trend structure, or late overextended chase |
| May reduce top-winner fragility? | Maybe; depends on whether winners occur near or far from EMA60 |
| May kill big winners? | Moderate-High risk |
| New data needed | No |
| Regime / portfolio / feature store risk | Low if local; rises if it becomes broad market-state classifier |
| Overfit risk | Moderate-High because EMA period/distance thresholds are tunable |
| NSC-013 first-round fit | No, except Direction A baseline may already use EMA60 as trend state / exit |
| Priority | P1 diagnostic / later overlay |

Boundary:

- no EMA period sweep;
- no EMA-distance threshold sweep;
- no turning EMA60 proximity into a regime system;
- avoid duplicating Direction A's EMA60 exit logic as a separate fitted filter.

### 6.6 E-F — Choppy Market / Range-bound Warning

Definition family:

- recent 4h closes cross EMA60 repeatedly;
- recent Donchian breakouts fail repeatedly;
- local structure shows range-bound behavior.

| Dimension | Assessment |
| --- | --- |
| Type | Diagnostic-only |
| Failure targeted | Breakouts inside local chop/range |
| May reduce top-winner fragility? | Possibly, but only after diagnostic evidence |
| May kill big winners? | High if used as broad filter |
| New data needed | No |
| Regime / portfolio / feature store risk | Moderate if it expands into market-state classification |
| Overfit risk | High because cross-count and lookback windows are tunable |
| NSC-013 first-round fit | No |
| Priority | Diagnostic-only |

Boundary:

- this is not a regime system;
- do not classify whole years or broad market phases;
- do not delete 2022/2025 by labeling them "choppy";
- use only as local signal-quality warning unless a future frozen plan
  justifies one simple rule.

---

## 7. Sparse Trend Edge Principle

Direction E must follow the Sparse Trend Edge Principle:

- low win rate is acceptable;
- large-winner concentration is acceptable to a degree;
- profit giveback is part of trend capture;
- the goal is not a smooth equity curve;
- the goal is not to maximize win rate;
- the goal is to reduce obvious bad signals or average loser size;
- any filter or early-exit rule must prove it does not delete the main trend
  profit source.

The most dangerous Direction E failure mode is false comfort: a filter that
removes many losing trades, improves win rate, and also removes the few trades
that pay for the strategy. Any future overlay must report:

- net PnL with and without top 1/top 3/top 5 winners;
- removed-trade analysis;
- whether removed trades included later top winners;
- average loser change;
- gross and net expectancy change;
- trade count impact;
- year-by-year impact, including 2022 and 2025.

---

## 8. Direction E And Direction A Integration Boundary

NSC-013 can proceed without Direction E. Direction A first round should remain
a clean baseline unless Direction E produces a very simple, frozen,
low-freedom rule before the plan is drafted.

Integration rules:

- Direction A baseline remains the control.
- Direction E, if used, is an optional overlay, not a replacement baseline.
- Only one E rule may be included in a first overlay test.
- No E rules may be stacked.
- No after-the-fact choice of the best E rule.
- No E rule may change Direction A's core entry, initial stop, or EMA60
  close-break exit hypothesis unless the plan explicitly defines a separate
  candidate.
- If the E rule cannot be frozen cleanly, NSC-013 should use Direction A only.

Recommended integration posture:

| Path | Recommendation |
| --- | --- |
| NSC-013 Direction A baseline | Proceed without Direction E by default |
| NSC-013 optional overlay | Allow only E-A if Owner wants one frozen companion overlay |
| NSC-014 or later | More appropriate place for Direction E overlay after baseline evidence |
| Diagnostic-only E-B/E-C/E-E/E-F | Keep as later analysis, not first execution |

---

## 9. Explicit Prohibitions

The following are not authorized:

- parameter sweep;
- recent return threshold sweep;
- EMA distance threshold sweep;
- EMA period sweep;
- ATR spike threshold sweep;
- Donchian / ATR / EMA / lookback rescue;
- multi-rule filter search;
- stacking E rules;
- using 2022 / 2025 losses to reverse-engineer a filter;
- deleting 2022 / 2025 from evidence windows;
- relaxing cost, funding, fee, or slippage;
- converting Direction E into a regime system;
- converting Direction E into an ML classifier;
- treating Direction E as portfolio / multi-strategy prerequisite;
- modifying runtime/profile/risk;
- modifying backtester or research engine core;
- promotion conclusion;
- small-live conclusion;
- live deployment advice.

---

## 10. Inspect Conclusion

Direction E is worth keeping as companion research, but it should not block
Direction A baseline.

| Field | Value |
| --- | --- |
| Direction | E — Trend Failure / False Breakout Avoidance |
| Identity | Companion overlay / diagnostic for Direction A |
| Standalone strategy? | No |
| Regime / portfolio / ML? | No |
| Inspect conclusion | `DEFER_TO_OPTIONAL_OVERLAY_OR_SECOND_PASS` |
| Should NSC-013 wait for Direction E? | No |
| Should NSC-013 baseline include Direction E? | No, baseline should stay clean |
| If NSC-013 includes one optional overlay | E-A only: one-bar post-entry breakout failure early exit |
| Recommended main path | Direction A clean baseline first; Direction E as NSC-014/second-pass overlay |
| Small-live conclusion | None |

Recommended ranking:

1. **E-A Breakout failure after signal** — best candidate if a single
   low-freedom optional overlay is desired. It must be framed as post-entry
   early exit, not pre-entry filter.
2. **E-E EMA60 proximity / trend quality** — useful diagnostic/later overlay,
   but high drift risk due to EMA distance thresholds.
3. **E-D Weak follow-through** — possible later, but may worsen thin sample.
4. **E-B Overextension / exhaustion** — diagnostic only for now; high winner
   deletion risk.
5. **E-C Volatility spike / noisy breakout** — diagnostic only for now; true
   trends often start with volatility expansion.
6. **E-F Choppy market / range-bound warning** — diagnostic only; highest risk
   of becoming regime logic.

Final recommendation:

- NSC-013 should proceed as a Direction A clean baseline experiment plan:
  4h Donchian breakout entry, 4h EMA60 close-break exit, previous N-bar 4h
  structure low initial stop, no 1h.
- Direction E should usually be deferred to NSC-014 or a later second-pass
  overlay.
- If Owner wants Direction E in NSC-013, include only one frozen optional
  overlay: **E-A one-bar post-entry close-back-below-breakout-level early
  exit**, with Direction A baseline still reported separately.

---

## 11. Final Boundary

This file is not experiment authorization.

It does not authorize:

- running NSC-013;
- running Direction E;
- running T1-B;
- creating an adapter;
- implementing a runtime strategy;
- changing runtime/profile/risk;
- changing backtester/research engine core;
- promotion;
- small-live candidate status;
- live deployment.

Current project still has no deployable small-live strategy candidate.
Small-live readiness gate remains unmet.

---

## 12. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-06 | Initial Direction E companion inspect | Codex |
