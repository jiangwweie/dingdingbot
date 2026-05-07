# NSC-016 — E-A Post-entry Early Exit Overlay Minimal Experiment Plan

**Task ID:** NSC-016
**Date:** 2026-05-06
**Status:** Proposed / Experiment Plan Only
**Scope:** Docs-only minimal experiment plan
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is a proposed experiment plan only. It does not authorize
running experiments, writing code, creating adapters, implementing strategies,
changing runtime profiles, changing risk rules, modifying backtester /
research engine core, making promotion conclusions, making small-live
conclusions, or giving live deployment advice.

This task did not run backtests, write code, create adapters, implement
strategies, tune parameters, modify runtime, modify profiles, modify risk
rules, or touch `src/`, `configs/`, `tests/`, `migrations/`, production
strategy paths, or backtester / research engine core.

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
| Direction A clean baseline | NSC-014 classification: `PAUSE_FRAGILE` |
| Direction E / E-A | Planned here as optional overlay only |
| T1-B / 1h entry timing | Reserve; not executed |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |

---

## 2. E-A Identity

E-A is:

- an optional overlay experiment plan for Direction A clean baseline;
- a post-entry early-exit hypothesis;
- a local false-breakout / trend-failure diagnostic translated into one
  frozen execution rule;
- a research-only candidate for evidence review.

E-A is not:

- an independent strategy;
- a pre-entry filter;
- a regime system;
- a portfolio / multi-strategy prerequisite;
- an ML classifier;
- a Direction A promotion path;
- a runtime implementation path;
- a small-live readiness path.

E-A earns nothing by itself. It can only be evaluated against the NSC-014
Direction A clean baseline to determine whether it reduces bad-trade exposure
without deleting the main trend winners.

---

## 3. Core Hypothesis

NSC-014 showed that Direction A clean baseline is not a thin-sample failure:

- 172 closed positions;
- positive gross and net expectancy;
- PF 1.42270;
- realized MaxDD 6.08%;
- MTM MaxDD 8.33%;
- trade floors met.

The blocker was top-winner fragility:

- top 1 removal remained positive;
- top 3 removal turned negative;
- top 5 removal turned more negative.

E-A hypothesis:

> Some failed Direction A breakouts reveal themselves immediately after entry.
> If the first fully closed 4h candle after entry closes back below the
> original breakout level, the breakout may have failed. Exiting at the next
> 4h open may reduce average loser / bad trade exposure without materially
> deleting the main trend winners.

E-A is not designed to maximize win rate or smooth the equity curve. It is
designed only to test whether an obvious post-entry false-breakout condition
can reduce downside fragility while preserving the sparse trend profit source.

---

## 4. Frozen Baseline Under Test

The baseline remains the NSC-013 / NSC-014 Direction A clean baseline.

| Component | Frozen Definition |
| --- | --- |
| Entry family | 4h Donchian20 breakout / continuation entry |
| Signal | Fully closed 4h candle close above previous 20 closed 4h high |
| Previous window | Previous 20 closed 4h candles; signal bar excluded |
| Entry execution | Next 4h bar open after signal close |
| Initial risk stop | Previous 20 closed 4h low; signal bar excluded |
| Trend lifecycle exit | Fully closed 4h candle close below EMA60 |
| EMA60 exit execution | Next 4h bar open after EMA60 close-break trigger |
| Direction E overlays | None except the single E-A overlay planned here |
| 1h involvement | None |

No Direction A baseline parameter may be changed in this plan.

---

## 5. Frozen E-A Overlay Rule

E-A is frozen as one post-entry rule:

| Field | Frozen Definition |
| --- | --- |
| Overlay type | Post-entry early exit |
| Check timing | Only the first fully closed 4h candle after entry |
| Breakout level | Original previous-20 closed 4h high that the signal bar broke |
| Trigger | First post-entry closed 4h candle close < original breakout level |
| Execution | Next 4h bar open after E-A trigger close |
| Intrabar touch | Not allowed |
| Buffer / threshold | None |
| Multiple-bar waiting | Not allowed |
| Recheck after first bar | Not allowed |
| Other overlays | Not allowed |

If the first fully closed 4h candle after entry closes at or above the original
breakout level:

- E-A is deactivated for that trade;
- the trade continues under Direction A clean baseline rules only;
- initial stop remains active;
- EMA60 close-break exit remains active.

Forbidden E-A variations:

- checking the second, third, or multiple confirmation bars;
- adding a close-back buffer;
- using a percentage or ATR threshold;
- searching different waiting periods;
- adjusting the condition after seeing results;
- using intrabar high/low/touch as the close-back trigger.

---

## 6. Breakout Level Definition

The breakout level must equal the signal bar's prior Donchian high:

```text
breakout_level = max(high of previous 20 closed 4h candles before signal bar)
```

Requirements:

- the previous-20 window must exclude the signal bar;
- the breakout level is fixed at signal time;
- E-A must not recompute the breakout level using future candles;
- E-A must not replace the original breakout level with the entry bar high,
  signal bar high, EMA level, or later Donchian high.

This preserves the original Direction A signal geometry and avoids hindsight.

---

## 7. Anti-lookahead Timing

The timing chain must be:

1. Signal bar closes.
2. Signal is evaluated using only fully closed 4h data.
3. Entry executes at the next 4h open.
4. The first post-entry 4h candle fully closes.
5. E-A checks whether that closed candle close is below the original breakout
   level.
6. If E-A triggers, early exit executes at the next 4h open.

Forbidden timing:

- same-bar signal and entry;
- same-bar entry and E-A judgment;
- same-bar E-A judgment and E-A exit;
- intrabar EMA60 touch exit;
- intrabar breakout-level touch as E-A trigger;
- any future candle access.

The execution report must record:

- signal bar timestamp;
- breakout level;
- entry timestamp and entry bar;
- first post-entry check bar timestamp;
- first post-entry check close;
- E-A trigger status;
- E-A exit execution timestamp and price convention when triggered.

---

## 8. Baseline Comparison Boundary

NSC-016 does not execute the comparison.

If NSC-017 is later approved, its predeclared comparison object must be the
NSC-014 clean baseline:

- Direction A clean baseline remains the control;
- E-A overlay result is a research overlay result;
- both must be reported;
- the owner must not choose the better result after the fact and treat it as
  promotion evidence;
- E-A can only show whether the overlay deserves evidence review;
- no additional Direction E rules may be added.

If E-A improves headline metrics but deletes major trend winners, it must be
classified as failure or pause, not promoted.

---

## 9. Required Future Report Outputs

Any future NSC-017 execution report must include:

- harness / adapter feasibility;
- exact cost model;
- same-bar / next-bar convention;
- anti-lookahead proof;
- signal count;
- E-A triggered count;
- E-A early-exit trade count;
- trades saved / trades worsened analysis;
- impact on net PnL versus NSC-014 baseline;
- impact on gross PnL before costs;
- impact on PF;
- impact on win rate;
- impact on realized MaxDD;
- impact on MTM MaxDD;
- impact on MFE / MAE;
- impact on maximum giveback;
- impact on average / median / max hold duration;
- impact on funding cost and funding intervals;
- impact on fee and slippage cost;
- impact on top 1 / top 3 / top 5 winner concentration;
- net excluding top 1 / top 3 / top 5;
- year-by-year comparison versus NSC-014 baseline;
- whether E-A reduces bad trades without deleting main winners;
- final classification.

Trades saved / worsened analysis must report:

- count and net PnL of trades where E-A improved the outcome versus baseline;
- count and net PnL of trades where E-A worsened the outcome versus baseline;
- whether any top 1 / top 3 / top 5 baseline winners were cut by E-A;
- average loser change;
- average winner change;
- trade count and hold-duration impact.

---

## 10. Classification Gates

Every future E-A execution report must end with one classification.

| Classification | Meaning |
| --- | --- |
| `PASS_TO_EVIDENCE_REVIEW` | E-A improves fragility / downside quality without materially deleting main trend winners; evidence review only |
| `PAUSE_FRAGILE` | E-A remains positive but top-winner concentration still fails |
| `REJECT_OVERFILTERS` | E-A materially deletes main trend winners or reduces expectancy by killing valid trend trades |
| `REJECT_NO_IMPROVEMENT` | E-A does not improve downside, fragility, or net quality versus clean baseline |
| `INSUFFICIENT_EVIDENCE` | E-A triggered count is too small to judge |
| `HARNESS_INFEASIBLE` | Frozen overlay cannot be expressed without forbidden modifications |

`PASS_TO_EVIDENCE_REVIEW` does not mean:

- promotion;
- small-live candidate;
- runtime implementation approval;
- official validation;
- live deployment.

Minimum evidence shape for `PASS_TO_EVIDENCE_REVIEW`:

- net after costs remains positive;
- gross expectancy is not materially damaged;
- top 3 / top 5 fragility improves versus NSC-014 baseline;
- average loser or bad-trade exposure improves;
- main trend winners are not materially deleted;
- trade count remains interpretable;
- year-by-year behavior remains explainable.

---

## 11. Sparse Trend Edge Principle

E-A must respect the Sparse Trend Edge Principle:

- low win rate can be acceptable;
- sparse profits can be acceptable;
- profit giveback can be acceptable;
- large winners can contribute a high share of profits;
- E-A's goal is not to make returns smooth;
- E-A's goal is not to raise win rate by itself;
- E-A must prove it does not kill the main trend profit source;
- E-A must not delete most winners simply to reduce drawdown.

The key test is not "does E-A improve win rate?" The key test is:

> Does E-A reduce obvious false-breakout loss exposure while preserving the
> winner cluster that pays for the trend strategy?

---

## 12. Not-now List

The following are explicitly not authorized:

- Direction A clean baseline parameter rescue;
- Donchian N sweep;
- EMA period sweep;
- initial stop lookback sweep;
- E-A multi-bar waiting period;
- E-A buffer threshold;
- E-A threshold or percentage search;
- E-B / E-C / E-D / E-E / E-F;
- multiple overlays;
- stacked Direction E rules;
- T1-B / 1h entry timing execution;
- CPM-1 rescue;
- CPM-2 A/B rescue;
- Candidate C automatic start;
- T1 + CPM-1 portfolio combination;
- portfolio engine;
- regime system;
- multi-strategy runtime;
- multi-asset expansion;
- full data feature store;
- complex ML;
- tick / orderbook simulator;
- cost/funding/slippage relaxation;
- promotion conclusion;
- small-live conclusion;
- live deployment advice.

---

## 13. NSC-017 Execution Gate Requirements

NSC-017 requires a separate Owner-approved task card.

If approved, NSC-017 may only be a minimal experiment execution gate:

1. Inspect whether the current research/backtest harness can express the
   frozen E-A overlay without modifying forbidden files.
2. If expressing E-A requires runtime/profile/risk/production strategy or
   backtester core changes, stop and report `HARNESS_INFEASIBLE`.
3. If standalone execution is feasible, use a reports-only research adapter or
   read-only harness call to produce research-only evidence.
4. Compare E-A against the predeclared NSC-014 clean baseline.
5. Output artifacts under a dedicated `reports/nsc-017-*` directory.

NSC-017 must not:

- implement runtime strategy;
- modify production code;
- modify config/profile/risk;
- modify backtester/research engine core;
- enable other Direction E overlays;
- run T1-B;
- run parameter sweeps;
- give promotion, small-live, or live deployment conclusions.

---

## 14. Final Boundary

This file is not experiment authorization.

It only defines the proposed E-A overlay plan:

- baseline remains Direction A clean baseline;
- E-A checks only the first fully closed 4h candle after entry;
- E-A triggers only if that candle closes below the original breakout level;
- E-A exits at the next 4h open;
- no intrabar touch;
- no buffer;
- no threshold;
- no multi-bar waiting;
- no other overlays;
- no 1h.

Any future result can only enter evidence review. It cannot by itself become
promotion evidence, small-live candidate evidence, runtime implementation
approval, official validation, or live deployment advice.

Current project still has no deployable small-live strategy candidate.
Small-live readiness gate remains unmet.

---

## 15. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-06 | Initial E-A post-entry early-exit overlay minimal experiment plan | Codex |
