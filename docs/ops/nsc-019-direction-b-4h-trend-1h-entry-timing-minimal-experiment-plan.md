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

# NSC-019 — Direction B 4h Trend + 1h Entry Timing Minimal Experiment Plan

**Task ID:** NSC-019
**Date:** 2026-05-06
**Status:** Proposed / Experiment Plan Only
**Scope:** Docs-only minimal experiment plan
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is a proposed experiment plan only. It does not authorize
running experiments, writing code, creating adapters, implementing strategies,
changing runtime profiles, changing risk rules, modifying production strategy
paths, modifying backtester / research engine core, making promotion
conclusions, making small-live conclusions, or giving live deployment advice.

This task did not run backtests, write code, create adapters, implement
strategies, tune parameters, modify runtime, modify profiles, modify risk
rules, or touch `src/`, `configs/`, `tests/`, or `migrations/`.

Allowed scope for this task:

- `docs/ops/**`
- `reports/**` inspect-only
- `archive/**` inspect-only

Forbidden scope:

- `src/**`
- `configs/**`
- `tests/**`
- `migrations/**`
- runtime profiles
- production strategy implementation
- risk rules
- backtester / research engine core

---

## 1. Current State

| Field | State |
| --- | --- |
| CPM-1 | Remains paused; not a small-live candidate |
| CPM-2 Candidate A/B | Closed as research proxy insufficient |
| Candidate C | Reserve-only; not automatically started |
| T1-A frozen rule | Paused; `INSUFFICIENT_EVIDENCE_THIN_SAMPLE`; top-winner fragility failed |
| Direction A clean baseline | `PAUSE_FRAGILE` from NSC-014 |
| E-A overlay | `REJECT_OVERFILTERS` from NSC-017; closed by NSC-018 |
| Direction B | Docs-only plan in this document; not executed |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |

NSC-014 showed that the 4h main-trend thesis is not empty:

- signal / closed positions: 172 / 172;
- net PnL: +2332.5122;
- gross PnL before costs: +3369.1730;
- PF: 1.42270;
- win rate: 19.19%;
- realized MaxDD: 6.08%;
- MTM MaxDD: 8.33%;
- trade floors met.

But NSC-014 remained fragile:

- top 1 net excluding: +1029.57;
- top 3 net excluding: -935.73;
- top 5 net excluding: -1812.81;
- classification: `PAUSE_FRAGILE`.

NSC-017 tested the lowest-freedom Direction E overlay, E-A one-bar post-entry
close-back early exit. It was rejected as `REJECT_OVERFILTERS` because it cut
part of the main winner cluster and worsened net, gross, PF, drawdown, and
top-winner fragility versus NSC-014.

NSC-018 therefore recommended that if research continues inside the 4h trend
thesis, the next docs-only step should inspect Direction B: 4h trend plus 1h
entry timing.

---

## 2. Direction B Identity

Direction B is an entry timing extension of Direction A.

Direction B is:

- a 4h main-trend lifecycle candidate;
- a test of whether 1h timing can improve entry quality inside a prequalified
  4h trend context;
- a comparison against the NSC-014 Direction A clean baseline;
- research-only until separately approved and executed.

Direction B is not:

- an independent 1h strategy;
- CPM-1 rescue;
- CPM-2 rescue;
- CPM-style local segment strategy;
- fixed short-TP pullback module;
- T1 + CPM-1 portfolio leg;
- Direction E / false-breakout overlay;
- portfolio, regime, or multi-strategy pre-work;
- runtime implementation path.

The primary decision layer must remain 4h. 1h is allowed only as validation
proxy or entry timing after a 4h trend qualification has already occurred.

---

## 3. Core Hypothesis

> Direction A clean baseline shows a positive but fragile 4h trend signal.
> Some fragility may come from the coarse 4h breakout entry: entering at the
> next 4h open can chase extended price, accept a wide initial stop distance,
> and include weak follow-through breakouts. A low-freedom 1h timing layer may
> improve entry quality and initial exposure while preserving the 4h trend
> lifecycle as the only intended profit source.

The hypothesis is not that 1h has standalone edge. It is not that a local 1h
reclaim should become the strategy. Direction B only asks whether a small,
frozen 1h timing requirement improves the NSC-014 4h trend baseline without
deleting the main trend winners that fund the strategy.

Expected improvement targets:

- reduce average loser or initial adverse exposure;
- avoid some weak 4h signals that never show 1h follow-through;
- preserve the top winner source better than E-A did;
- keep year-by-year behavior explainable;
- avoid turning sparse trend profits into a local scalp / segment system.

---

## 4. Mandatory 4h Primary Layer

Direction B must obey these structural rules:

1. 4h trend qualification must occur before any 1h entry can be considered.
2. 1h signals are invalid outside the active 4h trend setup window.
3. 1h signals cannot open standalone positions.
4. Exit remains governed by the 4h trend-lifecycle exit.
5. Direction B must compare against NSC-014 Direction A clean baseline.
6. Any 1h layer that becomes the main profit logic must be rejected or
   reclassified outside Direction B.

The default 4h layer for first-round planning is inherited from NSC-014:

| Component | Frozen Source |
| --- | --- |
| 4h setup | Donchian20 close breakout |
| 4h signal | Fully closed 4h candle close > previous 20 closed 4h high |
| Previous high window | Previous 20 closed 4h bars; signal bar excluded |
| Original breakout level | The previous-20 closed 4h high broken by the signal |
| Baseline entry | NSC-014 used next 4h open; Direction B replaces this only with a frozen 1h timing entry |
| Initial stop source | Previous 20 closed 4h low; signal bar excluded |
| Lifecycle exit | Fully closed 4h candle close below EMA60 |
| Lifecycle exit execution | Next 4h bar open |

N=20 and EMA60 are first-round fixed baselines inherited from Direction A.
They are not claimed to be optimal. No Donchian, EMA, or stop lookback sweep
is allowed.

---

## 5. Candidate 1h Entry Timing Families

This section compares possible 1h timing families at the planning level only.
No experiment is authorized here, and NSC-020 must not compare multiple
families after the fact.

| Family | Strategy hypothesis | How it may improve Direction A | 4h source preserved? | CPM-style drift risk | New data? | Complexity | First-round fit | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A. 1h pullback-then-reclaim | After a 4h trend setup, wait for a 1h pullback and reclaim of local structure before entering | May reduce chase entries and improve entry price | Mixed; 4h context can remain primary, but 1h reclaim can dominate | High; close to CPM / CPM-2 reclaim rescue | No | Moderate | Poor for first round | P3 |
| B. 1h higher-low continuation | After a 4h trend setup, enter only after a 1h higher-low structure confirms continuation | May reduce weak breakouts and improve risk location | Possible if higher-low definition is frozen | Medium; local structure can become subjective | No | Moderate-High | Not first round unless structure is objectively frozen | P2 |
| C. 1h volatility contraction then expansion | After a 4h trend setup, require 1h contraction followed by upside expansion | May avoid noisy chase and enter after short consolidation | Possible, but 1h volatility rules can dominate | Medium | No | High | Poor for first round due parameter freedom | P4 |
| D. 1h delayed breakout confirmation | After a 4h breakout signal, require near-term 1h follow-through above the original 4h breakout level before entry | May avoid 4h signals with no immediate follow-through while staying close to Direction A | Strong; 1h only validates the 4h breakout level | Low-Medium; not a pullback / reclaim module if kept to original 4h breakout level | No | Low | Best first-round fit | P1 |

Planning conclusion:

- Family A is too close to CPM-style reclaim repair for a first Direction B
  experiment.
- Family B is directionally plausible but needs a more objective higher-low
  definition before it can be frozen without subjectivity.
- Family C has too much threshold / duration freedom for this stage.
- Family D is the cleanest first-round choice because it changes only entry
  timing while preserving Direction A's 4h breakout level as the reference.

---

## 6. Recommended NSC-020 Frozen Candidate

Recommended first-round candidate:

> **Direction B-D1 — 4h Donchian20 breakout with first-window 1h
> follow-through confirmation.**

NSC-020 should proceed only if the Owner accepts this single frozen candidate.
If the Owner does not accept D1 as frozen, Direction B should pause rather than
open a multi-rule 1h entry search.

### 6.1 4h Trend Qualification

| Field | Frozen Definition |
| --- | --- |
| 4h setup family | Direction A Donchian20 breakout / continuation context |
| Signal timeframe | 4h |
| Signal candle | Fully closed 4h candle |
| Signal condition | 4h close > previous 20 closed 4h high |
| Previous high window | Previous 20 closed 4h bars; signal bar excluded |
| Original breakout level | The previous-20 closed 4h high broken by the signal |
| 4h signal timestamp | Timestamp of the fully closed 4h signal candle |

The 4h signal is the only source of trend permission. A 1h candle cannot
create a trade without this 4h setup.

### 6.2 1h Entry Timing

| Field | Frozen Definition |
| --- | --- |
| Timing family | 1h delayed breakout confirmation |
| Eligible 1h window | The first four fully closed 1h candles after the 4h signal close |
| 1h confirmation condition | First eligible fully closed 1h candle close > original breakout level |
| Entry execution | Next 1h bar open after the confirming 1h candle |
| Skip rule | If no eligible 1h candle closes > original breakout level in the first four 1h candles, skip that 4h signal |
| Same-bar entry | Not allowed |
| Pullback / reclaim search | Not allowed |
| 1h local structure | Not used |
| Buffer / threshold | Not allowed |
| Waiting-period sweep | Not allowed |

The four-candle window is not a tunable parameter in the experiment. It is the
fixed 1h decomposition of the next 4h block after the signal, chosen to avoid
turning Direction B into a variable waiting-period search.

### 6.3 Initial Stop

First-round Direction B-D1 should keep the NSC-014 4h initial stop:

| Field | Frozen Definition |
| --- | --- |
| Stop family | Previous 20 closed 4h structure low / Donchian low |
| Stop window | Previous 20 closed 4h bars |
| Signal bar in stop window | Excluded |
| 1h stop redesign | Not allowed in first round |
| Stop comparison | Not allowed |

Rationale:

- keeping the 4h stop isolates the effect of 1h entry timing;
- it avoids adding a second degree of freedom;
- the future report should still measure entry-to-stop distance, average loser,
  MAE, and initial risk exposure to see whether 1h timing helps despite using
  the same structural stop.

If a later task wants a 1h-defined stop, it must be a separate docs-only plan.

### 6.4 Exit

First-round Direction B-D1 must not redesign exits.

| Field | Frozen Definition |
| --- | --- |
| Lifecycle exit | 4h EMA60 close-break |
| Exit trigger | Fully closed 4h candle close below EMA60 |
| Intrabar EMA60 touch | Does not trigger exit |
| Exit execution | Next 4h bar open after the close-break trigger |
| Initial stop | Remains active |
| ATR trailing | Not allowed |
| Direction E overlay | Not allowed |
| E-A overlay | Not allowed |
| 1h exit | Not allowed |

This keeps the comparison focused on entry timing against the NSC-014 clean
baseline.

---

## 7. Anti-lookahead Requirements

NSC-020, if approved, must prove the following timing chain:

1. The 4h signal uses only a fully closed 4h candle.
2. The previous-20 high and low exclude the 4h signal bar.
3. The original breakout level is fixed at signal time and never recomputed
   from future candles.
4. Eligible 1h confirmation candles begin only after the 4h signal close.
5. The 1h confirmation uses only a fully closed 1h candle.
6. Entry occurs at the next 1h bar open after confirmation.
7. The 4h EMA60 exit uses only fully closed 4h candles.
8. EMA60 exit execution occurs at the next 4h bar open after the trigger.
9. No signal, entry, confirmation, or exit decision may be made from an
   unclosed candle.
10. No 1h candle may be used if its close timestamp is not strictly after the
    4h signal close and strictly before the entry execution timestamp.

If the harness cannot express 4h / 1h alignment, fixed breakout level,
next-1h-open entry, next-4h-open exit, and closed-candle-only decisions
without modifying forbidden runtime/profile/risk/backtester core paths, the
classification must be `HARNESS_INFEASIBLE`.

---

## 8. Cost Model And Data Windows

The cost model must match the NSC-014 / CPM-1 official OOS report SSOT
research convention and must record exact values in any future report.

Minimum report fields:

- fee rate;
- entry slippage rate;
- stop / EMA exit slippage rate;
- funding enabled / disabled;
- funding rate and funding interval convention;
- total fee cost;
- total slippage cost;
- total funding cost;
- funding intervals.

No cost, funding, or slippage relaxation is allowed.

Required data windows:

- 2021 and 2022 as stress / OOS-style historical references;
- 2023, 2024, and 2025 as recent reference years;
- aggregate full-window result;
- continuous indicator state across years unless the execution report
  explicitly proves a different convention is frozen before running.

The future report must compare Direction B-D1 directly against the NSC-014
Direction A clean baseline.

---

## 9. Future Experiment Report Requirements

If NSC-020 is separately approved, the execution report must include at least:

- harness / adapter feasibility;
- frozen rule definition;
- exact cost model;
- same-bar / next-bar convention;
- anti-lookahead proof;
- 4h signal count;
- 1h qualified entry count;
- closed positions count;
- skipped 4h signals count;
- skipped 4h signal reason summary;
- net PnL;
- gross PnL before costs;
- PF;
- win rate;
- realized MaxDD;
- MTM MaxDD;
- MFE / MAE;
- maximum giveback;
- average / median / max hold duration;
- hold duration distribution;
- funding cost and funding intervals;
- fee and slippage cost;
- year-by-year results;
- 2021 / 2022 behavior explanation;
- 2023 / 2024 / 2025 behavior explanation;
- top 1 / top 3 / top 5 winner concentration;
- net excluding top 1 / top 3 / top 5;
- average entry-to-stop distance versus NSC-014 where comparable;
- average loser and MAE versus NSC-014 where comparable;
- comparison against NSC-014 Direction A clean baseline;
- whether 1h timing improves entry quality without deleting main trend
  winners;
- classification.

Suggested artifacts, if NSC-020 is approved and feasible:

- `experiment_report.md`;
- `summary.json`;
- `signals.jsonl`;
- `trades.jsonl`;
- `equity_curve.jsonl`;
- `mtm_equity_curve.jsonl` or equivalent;
- `entry_timing_events.jsonl`, recording each 4h signal, original breakout
  level, eligible 1h candles, confirmation status, skipped status, entry bar,
  and entry price convention.

Artifacts should be placed under a future reports subdirectory, not in runtime
or production paths.

---

## 10. Classification Gates

| Classification | Gate |
| --- | --- |
| `PASS_TO_EVIDENCE_REVIEW` | 1h timing improves downside / entry quality / fragility versus NSC-014 without materially deleting main trend winners. This only permits evidence review; it is not promotion. |
| `PAUSE_FRAGILE` | Result remains positive but top-winner concentration or net excluding top winners still fails the gate. |
| `REJECT_OVERFILTERS` | 1h timing deletes too many main trend winners, significantly reduces expectancy, or turns a trend system into an overfiltered entry filter. |
| `REJECT_NO_IMPROVEMENT` | Direction B-D1 does not improve downside quality, fragility, entry quality, or net quality versus NSC-014. |
| `INSUFFICIENT_EVIDENCE` | Sample count, 1h qualified entries, triggered trades, or year coverage is too thin to judge. |
| `HARNESS_INFEASIBLE` | The frozen Direction B-D1 rule cannot be expressed without modifying forbidden runtime/profile/risk/production/backtester core paths. |

PASS does not mean promotion, small-live candidate status, runtime
implementation approval, or live deployment readiness.

---

## 11. Sparse Trend Edge Principle

Direction B must be interpreted under the same sparse trend edge principles as
Direction A:

- low win rate can be acceptable;
- sparse returns can be acceptable;
- profit giveback can be acceptable;
- high winner concentration can be acceptable to a degree;
- a few large winners may be the intended payoff source;
- a 1h timing layer must not kill the main winner source just to improve win
  rate or reduce small losers;
- local 1h gains must not be misread as 4h main-trend lifecycle edge;
- costs, funding, and slippage must not be relaxed;
- smoother equity is not a valid goal if it deletes trend payoff tails.

The key question is not whether 1h timing makes the strategy prettier. The key
question is whether it improves entry quality while preserving the 4h trend
profit engine.

---

## 12. Not-now List

The following are explicitly not authorized:

- CPM-1 rescue;
- CPM-2 A/B rescue;
- Candidate C automatic start;
- Direction A Donchian / EMA / stop lookback sweep;
- Direction A ATR trailing rescue;
- E-A rescue;
- other Direction E overlays;
- multiple 1h entry rule comparison;
- 1h parameter sweep;
- 1h independent strategy;
- fixed short-TP local segment strategy;
- 1h pullback / reclaim rescue path;
- T1-B direct execution without a separate approved task;
- T1 + CPM-1 portfolio combination;
- portfolio engine;
- regime system;
- multi-strategy runtime;
- multi-asset expansion;
- full data feature store;
- complex ML;
- tick / orderbook simulator;
- cost / funding / slippage relaxation;
- runtime/profile/risk changes;
- production strategy implementation;
- backtester / research engine core changes;
- promotion conclusion;
- small-live conclusion;
- live deployment advice.

---

## 13. NSC-020 Boundary

If the Owner approves NSC-020, it must be a separate minimal experiment
execution gate.

NSC-020 must:

1. Inspect this NSC-019 plan and the NSC-014 baseline artifacts first.
2. Run harness feasibility before implementation or execution.
3. Stop as `HARNESS_INFEASIBLE` if the frozen Direction B-D1 rule requires
   modifying runtime, profiles, risk rules, production strategy paths,
   migrations, configs, or backtester / research engine core.
4. Use a standalone reports adapter only if feasible without forbidden
   changes.
5. Execute only Direction B-D1.
6. Compare only against the predeclared NSC-014 clean baseline.
7. Avoid all parameter sweeps and after-the-fact rule selection.
8. Report research-only evidence; no runtime implementation follows from the
   result.

---

## 14. Recommendation

Recommended next step:

- Proceed to **NSC-020 — Direction B-D1 4h Donchian20 + first-window 1h
  follow-through confirmation minimal experiment execution gate**, but only as
  a separate Owner-approved task card.

Recommended first-round frozen candidate:

- **Direction B-D1**, not families A/B/C and not a multi-rule comparison.

Reasoning:

- D1 is the lowest-freedom way to test whether 1h timing improves Direction A.
- D1 preserves the 4h breakout level as the reference and avoids CPM-style
  pullback / reclaim repair.
- D1 changes entry timing while leaving the Direction A stop and EMA60
  lifecycle exit intact.
- D1 can fail cleanly if it overfilters, lacks sample, or damages the main
  winner source.

If D1 is not acceptable to the Owner, Direction B should pause and the program
should return to the Strategy Candidate Direction Map rather than open a broad
1h entry search.

Current small-live readiness gate remains unmet. There is still no deployable
small-live strategy candidate.

---

## 15. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-06 | Initial Direction B docs-only minimal experiment plan | Codex |
