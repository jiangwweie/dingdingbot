# NSC-015 — Direction A PAUSE_FRAGILE Evidence Review & Next Decision Gate

**Task ID:** NSC-015
**Date:** 2026-05-06
**Status:** Proposed / Owner Evidence Review
**Scope:** Docs-only evidence review
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document reviews NSC-014 research-only evidence and frames Owner decision
options. It is not an experiment authorization, promotion review, small-live
readiness review, runtime implementation approval, risk-rule approval, or live
deployment recommendation.

This task did not run backtests, write code, create adapters, implement
strategies, tune parameters, modify runtime, modify profiles, modify risk
rules, or touch `src/`, `configs/`, `tests/`, `migrations/`, production
strategy paths, or backtester / research engine core.

Inspected material:

- `docs/ops/nsc-011-4h-main-trend-lifecycle-capture-direction-inspect.md`
- `docs/ops/nsc-012-trend-failure-false-breakout-avoidance-companion-inspect.md`
- `docs/ops/nsc-013-direction-a-4h-main-trend-lifecycle-clean-baseline-minimal-experiment-plan.md`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/**`
- `docs/ops/project-roadmap-v2.md`

Research/runtime isolation remains binding. Research may produce reports,
candidates, diagnostics, suggestions, and hypotheses. Research must not directly
produce runtime profile changes, strategy promotion, risk overrides, or
automatic live enablement.

---

## 1. Current State

| Field | State |
| --- | --- |
| CPM-1 | Remains paused; not a small-live candidate |
| CPM-2 Candidate A/B | Closed as research proxy insufficient |
| Candidate C | Reserve-only; not automatically started |
| T1-A frozen rule | Paused; `INSUFFICIENT_EVIDENCE_THIN_SAMPLE`; top-winner fragility failed |
| Direction A clean baseline | `PAUSE_FRAGILE` after NSC-014 |
| Direction E / E-A | Not enabled in NSC-014; future optional overlay only |
| T1-B / 1h entry timing | Reserve; not executed |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |

---

## 2. NSC-014 Result Summary

Primary report:

- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/experiment_report.md`

Frozen rule:

- 4h Donchian20 close breakout;
- next 4h open entry;
- previous-20 low initial stop;
- EMA60 close-break trend-lifecycle exit;
- next 4h open exit after EMA60 close-break trigger;
- no intrabar EMA60 touch exit;
- no Direction E / E-A overlay;
- no T1-B / 1h entry timing;
- no parameter sweep.

Key results:

| Metric | Value |
| --- | ---: |
| Harness feasibility | `FEASIBLE_STANDALONE_ADAPTER` |
| Signal count / closed positions | 172 / 172 |
| Gross PnL before costs | +3369.1730 |
| Net PnL | +2332.5122 |
| PF | 1.42270 |
| Win rate | 19.19% |
| Avg winner / avg loser | 237.90 / 39.70 |
| Approx payoff ratio | 5.99 |
| Realized MaxDD | 6.08% |
| MTM MaxDD | 8.33% |
| MFE / MAE | +1561.71 / -106.54 |
| Maximum giveback | 400.97 |
| Average / median / max hold hours | 97.93 / 48 / 884 |
| Funding cost / intervals | 315.83 / 2061 |
| Fee cost / slippage cost | 205.95 / 514.88 |
| Trade floors | Met: 68 / 104 / 172 |
| Top 1 net excluding | +1029.57 |
| Top 3 net excluding | -935.73 |
| Top 5 net excluding | -1812.81 |
| Classification | `PAUSE_FRAGILE` |

---

## 3. What NSC-014 Really Means

Direction A clean baseline is no longer a thin-sample result.

Evidence improved materially versus T1-A:

- closed positions rose from T1-A's 85 to Direction A's 172;
- 2023+2024+2025 floor was met at 104 trades;
- gross expectancy was positive;
- net after costs was positive;
- PF improved to 1.42;
- realized and MTM drawdown were lower than the prior T1-A research result;
- EMA60 close-break exit created a structurally different trade lifecycle from
  T1-A's ATR trailing exit;
- low win rate paired with high payoff ratio is consistent with Owner's sparse
  trend thesis.

But Direction A still does not pass the minimum evidence gate:

- top 1 removal remains positive, so it is not as fragile as NSC-009/T1-A;
- top 3 removal is negative;
- top 5 removal is more negative;
- 2023 and 2024 carry most of the net profit;
- 2022 and 2025 are slightly negative after costs;
- research-only standalone adapter evidence is not official validation.

Therefore Direction A clean baseline cannot enter:

- promotion;
- small-live candidate status;
- runtime implementation;
- production strategy implementation;
- official backtester integration as a promoted strategy.

---

## 4. Why PAUSE_FRAGILE

### 4.1 Why Not REJECT

Direction A should not be rejected at this point because:

- trade count floors are met;
- gross PnL is positive;
- net after costs is positive;
- PF is materially above 1.0;
- drawdowns are moderate in this research proxy;
- the average winner is nearly 6x the average loser;
- the rule captures multi-day 4h trend segments rather than only local
  intraday moves;
- 2023 and 2024 are strongly positive.

This is meaningful positive-but-fragile research evidence.

### 4.2 Why Not PASS

Direction A should not pass because:

- top 3 winners exceed total net PnL and net excluding top 3 is negative;
- top 5 removal is more negative;
- the result is still highly dependent on a small number of large trend
  captures;
- year-level concentration is visible: 2023 and 2024 provide most of the net;
- 2022 and 2025 do not independently validate robustness;
- research-only proxy evidence cannot become official validation.

PASS would overstate the confidence of the evidence.

### 4.3 Why PAUSE_FRAGILE Is Correct

`PAUSE_FRAGILE` is the right classification because Direction A has a real
positive signal, but the signal has not yet proven robustness under the
pre-registered fragility gates.

The correct owner-level interpretation:

> Continue treating Direction A as promising but not deployable. Any next step
> must be a new docs-only plan, not immediate execution or runtime promotion.

---

## 5. Top-winner Fragility Analysis

NSC-014 improved the fragility shape versus NSC-009:

| Fragility Metric | T1-A / NSC-009 | Direction A / NSC-014 |
| --- | ---: | ---: |
| Net PnL | +368.19 | +2332.51 |
| Top 1 net excluding | +5.64 | +1029.57 |
| Top 3 net excluding | -663.37 | -935.73 |
| Top 5 net excluding | -1158.15 | -1812.81 |

Interpretation:

- Direction A is not fully dependent on one trade. That is a meaningful
  improvement.
- Direction A is still dependent on the top cluster of winners.
- This dependency is consistent with trend-following mechanics up to a point:
  few large winners pay for many small losses.
- It fails the current gate because the conclusion still does not survive top
  3 / top 5 removal.

Sparse Trend Edge Principle allows rare winners and low win rate. It does not
allow a research conclusion to be fully supported by a small top-winner cluster.

---

## 6. Year-by-year Behavior

Year-by-year results:

| Year | Trades | Net PnL | Gross PnL | PF | Win Rate | MTM MaxDD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2021 | 32 | +170.71 | +287.35 | 1.18 | 21.88% | 4.18% |
| 2022 | 36 | -72.85 | +80.78 | 0.92 | 13.89% | 6.52% |
| 2023 | 29 | +871.63 | +1142.31 | 1.83 | 24.14% | 8.33% |
| 2024 | 34 | +1390.32 | +1636.18 | 2.56 | 26.47% | 5.89% |
| 2025 | 41 | -27.30 | +222.55 | 0.98 | 12.20% | 7.31% |

Interpretation:

- 2021/2022 are stress / OOS-style references. Combined net remains positive
  because 2021 offsets 2022, but 2022 is weak after costs.
- 2023/2024/2025 are the recent reference window. Combined net is positive,
  with 2023 and 2024 carrying most of the result.
- 2025 is near breakeven after costs but negative net, which is explainable as
  a choppy or failed-trend year, not automatically fatal.
- There is no single-year-only dependency because both 2023 and 2024 are
  positive, and 2021 is also positive.
- There is still a two-year concentration concern: 2023/2024 dominate the
  full-window result.

This year shape supports continued research but blocks small-live readiness.

---

## 7. Trade Quality

Low win rate is expected for trend-following. NSC-014's 19.19% win rate is
low, but not disqualifying because the payoff ratio is high:

- winners: 33 trades;
- losers: 139 trades;
- average winner: about +237.90;
- average loser: about -39.70;
- approximate payoff ratio: 5.99.

MFE / MAE also supports a main-trend capture profile:

- maximum favorable excursion: +1561.71;
- maximum adverse excursion: -106.54;
- maximum giveback: 400.97.

Hold duration:

- average hold: 97.93 hours;
- median hold: 48 hours;
- max hold: 884 hours;
- distribution: 59 `<1 day`, 45 `1-3 days`, 33 `3-7 days`, 25 `7-14 days`,
  10 `>14 days`.

Funding / cost:

- funding cost: 315.83 across 2061 intervals;
- fee cost: 205.95;
- slippage cost: 514.88.

Interpretation:

- The strategy is not merely local segment capture; it does hold meaningful
  multi-day trends.
- Giveback is expected, but still must be monitored because top winners are
  carrying the result.
- Funding exposure appears interpretable in this research proxy; it does not
  by itself reject the result.
- Costs are material and must not be relaxed.

---

## 8. Explicit Rescue Prohibitions

The following are not allowed as rescue work:

- Donchian N sweep;
- EMA period sweep;
- initial stop lookback sweep;
- E-A overlay after-the-fact comparison;
- enabling E-A and choosing the better of baseline vs overlay after seeing
  results;
- T1-B / 1h entry timing direct experiment without a docs-only plan;
- cost / funding / slippage relaxation;
- deleting negative years;
- retaining only top winners;
- rewriting research-only adapter evidence as official validation;
- runtime/profile/risk changes;
- production strategy implementation;
- backtester / research engine core changes;
- portfolio engine;
- regime system;
- multi-strategy runtime;
- live deployment advice.

---

## 9. Owner Decision Options

### Option A — Pause Direction A Clean Baseline

Keep Direction A as positive-but-fragile evidence. Do not run the next
experiment immediately.

Use this if Owner wants to avoid another research iteration until the
fragility bar is reconsidered.

### Option B — Draft NSC-016 Docs-only E-A Overlay Experiment Plan

Goal:

- test whether one-bar post-entry close-back-below-breakout-level early exit
  can reduce bad signals / average loser without deleting the main winners.

Boundaries:

- E-A must be post-entry early exit, not pre-entry filter;
- no multiple overlays;
- no stacked Direction E rules;
- no after-the-fact baseline-vs-overlay selection;
- clean baseline must remain reported separately;
- execution would require a later Owner-approved task card.

### Option C — Draft NSC-016 Docs-only Direction B / 1h Entry Timing Plan

Goal:

- test whether 1h timing can improve entry quality while 4h remains the main
  trend decision layer.

Boundaries:

- 4h remains the profit source and trend judgment layer;
- 1h is timing only;
- no CPM-style local segment repair;
- no 1h pullback/reclaim search without frozen rules;
- execution would require a later Owner-approved task card.

### Option D — Draft NSC-016 Docs-only Extended Evidence Review

Goal:

- inspect whether a longer historical window or shadow-style validation is
  available and useful.

Boundaries:

- no added assets;
- no added timeframes;
- no new direction;
- no parameter changes;
- no selective-year inclusion;
- no execution without later approval.

### Option E — Retire Current Direction A Frozen Baseline

Use this if Owner judges that top-winner fragility remains unacceptable even
with improved sample size, positive expectancy, and lower drawdown.

Next step would be returning to Strategy Candidate Direction Map.

---

## 10. Recommendation

Recommended owner path:

1. Keep Direction A as the P0 research direction, but keep the clean baseline
   classification at `PAUSE_FRAGILE`.
2. Draft **NSC-016 docs-only E-A overlay experiment plan** as the next task
   card.
3. Do not execute E-A yet.
4. Keep Direction B / 1h entry timing as second priority, because it opens more
   rule freedom and has higher CPM-style drift risk.

Reasoning:

- Direction A improved meaningfully versus T1-A and is not rejected.
- The remaining blocker is losing-side / false-breakout management, which is
  exactly the companion problem Direction E was meant to inspect.
- E-A is lower freedom than Direction B and does not introduce 1h.
- If E-A cannot reduce fragility without deleting main winners, Owner can then
  decide between Direction B, extended evidence review, or retiring the frozen
  baseline.

---

## 11. Final Boundary

NSC-015 is not:

- experiment authorization;
- promotion review;
- small-live readiness review;
- runtime implementation approval;
- live deployment advice.

Any future NSC-016 must be a separate Owner-approved task card. Any future
experiment must remain within research/runtime isolation and may only produce
research reports, candidates, diagnostics, suggestions, and hypotheses.

Current conclusions:

- Direction A clean baseline classification remains `PAUSE_FRAGILE`.
- Current project still has no deployable small-live strategy candidate.
- CPM-1 remains paused.
- CPM-2 Candidate A/B remain closed.
- Candidate C remains reserve-only.
- Direction E / E-A has not been executed.
- T1-B remains reserve.
- Small-live readiness gate remains unmet.

---

## 12. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-06 | Initial Direction A PAUSE_FRAGILE evidence review | Codex |
