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

# NSC-018 — E-A Overlay Rejection & Direction A Next Decision Closure Review

**Task ID:** NSC-018
**Date:** 2026-05-06
**Status:** Closed / Research Evidence Closure Review
**Scope:** Docs-only evidence / closure review
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document closes the NSC-017 E-A overlay evidence and frames next Owner
decision options for Direction A. It is not an experiment authorization,
promotion review, small-live readiness review, runtime implementation approval,
risk-rule approval, or live deployment recommendation.

This task did not run backtests, write code, create adapters, implement
strategies, tune parameters, modify runtime, modify profiles, modify risk
rules, or touch `src/`, `configs/`, `tests/`, `migrations/`, production
strategy paths, or backtester / research engine core.

Inspected material:

- `reports/nsc-017-ea-post-entry-early-exit-overlay/**`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/**`
- `docs/ops/nsc-015-direction-a-pause-fragile-evidence-review.md`
- `docs/ops/nsc-016-ea-post-entry-early-exit-overlay-minimal-experiment-plan.md`

---

## 1. Current State

| Field | State |
| --- | --- |
| CPM-1 | Remains paused; not a small-live candidate |
| CPM-2 Candidate A/B | Closed as research proxy insufficient |
| Candidate C | Reserve-only; not automatically started |
| T1-A frozen rule | Paused; `INSUFFICIENT_EVIDENCE_THIN_SAMPLE`; top-winner fragility failed |
| Direction A clean baseline | `PAUSE_FRAGILE` |
| E-A overlay | `REJECT_OVERFILTERS` |
| Other Direction E overlays | Not enabled |
| T1-B / Direction B | Reserve; not executed |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |

---

## 2. NSC-017 Result Summary

Primary report:

- `reports/nsc-017-ea-post-entry-early-exit-overlay/experiment_report.md`

NSC-017 executed one frozen E-A overlay:

- baseline: NSC-014 Direction A clean baseline;
- E-A trigger: first eligible fully closed 4h candle after entry closes below
  original breakout level;
- E-A execution: next 4h open;
- no buffer;
- no threshold;
- no multi-bar waiting;
- no other Direction E overlays;
- no T1-B / 1h entry timing;
- no parameter sweep.

Key comparison:

| Metric | NSC-014 Baseline | NSC-017 E-A | E-A Delta |
| --- | ---: | ---: | ---: |
| Net PnL | +2332.5122 | +1956.4039 | -376.1083 |
| Gross PnL before costs | +3369.1730 | +2991.8895 | -377.2835 |
| PF | 1.42270 | 1.36523 | Worse |
| Win rate | 19.19% | 17.49% | Worse |
| Realized MaxDD | 6.08% | 7.00% | Worse |
| MTM MaxDD | 8.33% | 8.68% | Worse |
| Top 3 net excluding | -935.73 | -1024.43 | -88.70 |
| Top 5 net excluding | -1812.81 | -1880.88 | -68.07 |

E-A event quality:

| Metric | Value |
| --- | ---: |
| E-A checked count | 161 |
| E-A triggered count | 33 |
| E-A early-exit trade count | 33 |
| E-A improved trades | 27 |
| Improved-trade delta | +550.60 |
| E-A worsened trades | 3 |
| Worsened-trade delta | -1449.08 |
| Cut baseline top5 signal timestamps | 1647360000000, 1751990400000 |
| Classification | `REJECT_OVERFILTERS` |

---

## 3. What NSC-017 Really Means

E-A did identify and improve some losing / weak trades. That part of the
hypothesis was not imaginary:

- 33 trades triggered E-A;
- 27 triggered trades improved relative to the NSC-014 baseline;
- those improvements added +550.60 versus baseline on those trades.

But this is not enough for a sparse trend strategy.

The failure is structural:

- 3 E-A-triggered trades worsened by -1449.08;
- E-A cut two baseline top-5 signal timestamps;
- net PnL fell by -376.11 versus baseline;
- gross PnL fell by -377.28 versus baseline;
- PF and win rate declined;
- realized and MTM drawdown increased;
- top 3 / top 5 excluding metrics got worse;
- fragility did not improve.

For trend-following, cutting a few main winners is more dangerous than saving
many small losers. NSC-017 shows that the simple close-back early exit can
remove part of the winner cluster that pays for the strategy.

Therefore `REJECT_OVERFILTERS` is correct.

---

## 4. E-A Closure

E-A is closed as a tested and rejected post-entry early-exit overlay.

E-A does not enter:

- evidence review as a continuation candidate;
- runtime implementation;
- promotion path;
- small-live candidate path;
- official validation;
- default Direction A overlay status.

E-A should be archived as:

> Tested post-entry one-bar close-back-below-breakout-level early exit;
> rejected because it overfilters / cuts main trend winners and worsens net,
> gross, drawdown, and fragility versus NSC-014 baseline.

---

## 5. E-A Rescue Prohibitions

The following E-A rescue paths are not allowed:

- multi-bar waiting;
- buffer threshold;
- breakout level redefinition;
- close-back condition modification;
- partial early exit;
- after-the-fact keeping only the 27 improved trades and excluding the 3
  worsened trades;
- E-A plus other Direction E rules;
- E-A parameter sweep;
- E-A as future default overlay;
- E-A runtime implementation.

If a future failure-avoidance concept is proposed, it must be a new direction
or hypothesis with a separate docs-only inspect/plan. It must not be labeled
as E-A rescue.

---

## 6. Direction A Clean Baseline Status

E-A rejection does not equal Direction A rejection.

Direction A clean baseline remains `PAUSE_FRAGILE`.

Why it is not reject:

- sample count is sufficient;
- gross PnL is positive;
- net PnL is positive;
- PF is above 1.0;
- realized / MTM drawdown are moderate in the research proxy;
- it shows 4h main trend lifecycle signal.

Why it is not pass:

- top 3 / top 5 removal remains negative;
- the result still depends on a small cluster of winners;
- research-only proxy evidence is not official validation;
- no small-live readiness gate has been met.

E-A rejection only tells us:

> A simple one-bar close-back early exit is not compatible with the current
> sparse trend profit source.

It does not prove the broader 4h Main Trend Lifecycle Capture direction is
dead.

---

## 7. Sparse Trend Edge Principle

NSC-017 reinforces the Sparse Trend Edge Principle:

- low win rate can be acceptable;
- sparse profits can be acceptable;
- profit giveback can be acceptable;
- high winner concentration can be acceptable to a degree;
- protecting the winner source is more important than mechanically reducing
  loser count;
- improving many small losers is not sufficient if a rule damages a few major
  winners;
- a smoother-looking rule can be worse if it cuts the strategy's payoff tail.

For Direction A, the winner cluster is not a nuisance. It is the strategy's
primary return engine. Any overlay that damages that engine must be rejected,
even if it looks sensible as a false-breakout rule.

---

## 8. Owner Decision Options

### Option A — Pause Direction A Clean Baseline

Keep Direction A clean baseline as positive-but-fragile evidence. Do not run
more experiments immediately.

Use this if Owner wants to stop the current research chain and preserve the
evidence without adding complexity.

### Option B — Draft Direction B Docs-only Plan

Study whether 4h trend + 1h entry timing can improve entry quality while
preserving the 4h trend profit source.

Boundary:

- 4h remains the main trend judgment layer;
- 1h is only entry timing / validation proxy;
- 1h must not become CPM-style local segment strategy;
- no direct experiment;
- no Direction E overlay;
- first step must be docs-only minimal experiment plan.

### Option C — Return To Strategy Candidate Direction Map

Reopen direction-level comparison across remaining candidate directions.

Boundary:

- do not reopen CPM-1;
- do not reopen CPM-2 A/B;
- do not auto-start Candidate C;
- do not jump to portfolio / regime / multi-strategy;
- next step remains inspect-only.

### Option D — Longer-window / Data Availability Inspect

Inspect whether more history or shadow-style validation can clarify Direction A
without changing the rule.

Boundary:

- no new asset;
- no new timeframe;
- no new direction;
- no parameter sweep;
- no execution without separate approval.

### Option E — Close Current Direction A Frozen Variant

Close the current Direction A frozen variant while preserving 4h Main Trend
Lifecycle Capture as a long-term direction.

Use this if Owner judges that the current Donchian20 + EMA60 shape is too
fragile but the broader thesis remains interesting.

---

## 9. Recommended Next Step

Recommended path:

1. Close E-A as `REJECT_OVERFILTERS`.
2. Keep Direction A clean baseline at `PAUSE_FRAGILE`.
3. Do not continue Direction E overlay experiments immediately.
4. Draft a separate **Direction B docs-only minimal experiment plan** if Owner
   wants one more research step inside the 4h trend thesis.
5. Otherwise pause strategy experiments and return to Strategy Candidate
   Direction Map.

Reasoning:

- E-A was the lowest-freedom Direction E overlay. It failed by cutting winners.
- Other Direction E overlays are likely higher freedom and higher overfit risk.
- Direction B tests a different question: entry quality while preserving 4h
  trend as the profit source.
- Direction B still needs strict guardrails to avoid becoming CPM-style local
  segment repair.

---

## 10. Not-now List

The following are explicitly not authorized:

- CPM-1 rescue;
- CPM-2 A/B rescue;
- Candidate C automatic start;
- T1-A parameter rescue;
- Direction A Donchian / EMA / stop lookback sweep;
- E-A rescue;
- E-B / E-C / E-D / E-E / E-F direct experiment;
- T1-B / Direction B direct experiment;
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

## 11. Final Closure

Final NSC-018 conclusions:

- E-A classification remains `REJECT_OVERFILTERS`.
- E-A is closed and should not be rescued by tuning.
- Direction A clean baseline remains `PAUSE_FRAGILE`.
- E-A rejection does not reject the broader Direction A thesis.
- Current project still has no deployable small-live strategy candidate.
- Small-live readiness gate remains unmet.
- Any next step requires a separate Owner-approved task card and must remain
  within research/runtime isolation.

Recommended next task card:

- **NSC-019 — Direction B 4h Trend + 1h Entry Timing Docs-only Minimal
  Experiment Plan**, if Owner wants to continue within the 4h trend thesis.

Alternative:

- Pause active strategy experiments and return to Strategy Candidate Direction
  Map for inspect-only selection.

---

## 12. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-06 | Initial E-A rejection and Direction A next-decision closure review | Codex |
