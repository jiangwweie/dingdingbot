# TE-001 - Sparse Trend Edge Evidence Review & Fragility Gate Recalibration

**Task ID:** TE-001
**Date:** 2026-05-07
**Status:** Proposed / Evidence Review Only
**Scope:** Docs-only evidence review
**Affects Runtime Automatically:** No

---

## 0. Boundary

This document is an evidence review and proposed gate recalibration only.

It is not:

- experiment authorization;
- adapter authorization;
- code authorization;
- strategy implementation approval;
- official validation approval;
- promotion review;
- small-live readiness review;
- live deployment advice;
- runtime/profile/risk/backtester-core change approval.

No D2/D3/D4 experiment, new 1h entry rule, new exit variant, new overlay, or
parameter sweep is authorized by this document.

Allowed scope for TE-001:

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

Current project state remains:

| Field | State |
| --- | --- |
| Deployable small-live strategy candidate | None |
| Small-live readiness gate | Remains unmet |
| Runtime/profile/risk impact | None |
| Strategy promotion conclusion | None |

---

## 1. Reviewed Evidence Chain

Primary inspected evidence:

- `docs/ops/crypto-pullback-module-v1-oos-failure-classification.md`
- `docs/ops/nsc-006-cpm2-ab-insufficiency-closure.md`
- `docs/ops/nsc-015-direction-a-pause-fragile-evidence-review.md`
- `docs/ops/nsc-018-ea-rejection-direction-a-next-decision-closure-review.md`
- `docs/ops/nsc-019-direction-b-4h-trend-1h-entry-timing-minimal-experiment-plan.md`
- `reports/nsc-014-direction-a-4h-main-trend-lifecycle-clean-baseline/experiment_report.md`
- `reports/nsc-017-ea-post-entry-early-exit-overlay/experiment_report.md`
- `reports/nsc-020-direction-b-d1-4h-trend-1h-follow-through-entry/experiment_report.md`
- `docs/ops/strategy-candidate-direction-map-v1.md`
- `docs/ops/project-roadmap-v2.md`

TE-001 uses these artifacts as research evidence only. It does not convert
research-only standalone adapter evidence into official validation evidence.

---

## 2. Research Chain Recap

### 2.1 Why CPM Closed

CPM-1 is paused because the OOS evidence challenged the module thesis rather
than only the cost model:

- 2022 OOS was negative in a bear / unfavorable reference year.
- 2021 OOS was also materially negative in a bull / favorable reference year.
- The 2021 failure included negative gross edge, so costs amplified the loss
  but did not fully explain it.
- The result blocked CPM-1 small-live candidate review and stopped the
  promotion path.

CPM-2 Candidate A/B closed because the frozen A/B proxy path did not meet the
minimum evidence gate:

| Candidate | Closed positions | Net PnL | PF | Closure |
| --- | ---: | ---: | ---: | --- |
| Candidate A - one-bar continuation reclaim | 56 | -973.0352 | 0.74997 | `INSUFFICIENT_EVIDENCE` |
| Candidate B - Donchian-location pullback confirmation | 135 | -5682.2921 | 0.50660 | `INSUFFICIENT_EVIDENCE` |

This closes CPM-2 A/B as the current mainline. It does not prove every
pullback-continuation idea is invalid, but it does block CPM rescue work,
threshold sweeps, reclaim variants, and Candidate C auto-start.

### 2.2 Why Direction A Is Not Reject

Direction A clean baseline produced positive-but-fragile evidence:

| Metric | Direction A |
| --- | ---: |
| Closed positions | 172 |
| Net PnL | +2332.5122 |
| Gross PnL before costs | +3369.1730 |
| PF | 1.42270 |
| Win rate | 19.19% |
| Realized MaxDD | 6.08% |
| MTM MaxDD | 8.33% |
| Top 1 net excluding | +1029.57 |
| Top 3 net excluding | -935.73 |
| Top 5 net excluding | -1812.81 |
| Classification | `PAUSE_FRAGILE` |

Direction A is not reject because:

- trade floors were met;
- gross expectancy was positive;
- net after fees, slippage, and funding was positive;
- PF was materially above 1.0;
- drawdown was moderate in the research proxy;
- low win rate plus high payoff ratio matches the Owner's sparse trend thesis;
- the rule captured multi-day 4h trend lifecycle moves, not only local
  intraday segments.

Direction A is also not pass because top 3 / top 5 winner removal turns net
negative and the evidence remains research-only.

### 2.3 Why E-A Rejects

E-A tested a simple post-entry early exit: after entry, exit if the first
eligible fully closed 4h candle closes below the original breakout level.

E-A rejected because it overfiltered the trend payoff tail:

| Metric | Direction A baseline | E-A | Delta |
| --- | ---: | ---: | ---: |
| Net PnL | +2332.5122 | +1956.4039 | -376.1083 |
| Gross PnL | +3369.1730 | +2991.8895 | -377.2835 |
| PF | 1.42270 | 1.36523 | Worse |
| Realized MaxDD | 6.08% | 7.00% | Worse |
| MTM MaxDD | 8.33% | 8.68% | Worse |
| Top 3 net excluding | -935.73 | -1024.43 | Worse |
| Top 5 net excluding | -1812.81 | -1880.88 | Worse |

E-A improved many small trades but worsened a few important winners. For sparse
trend strategies, cutting the payoff tail is more damaging than reducing a
moderate number of weak trades. Therefore `REJECT_OVERFILTERS` is correct and
E-A must not be reopened through buffers, waiting periods, partial exits, or
other rescue variants.

### 2.4 Why Direction B-D1 Is Mixed Partial

Direction B-D1 preserved Direction A's 4h trend thesis and added a frozen 1h
first-window follow-through entry condition.

| Metric | Direction A | Direction B-D1 | Delta |
| --- | ---: | ---: | ---: |
| Closed positions | 172 | 164 | -8 |
| Net PnL | +2332.5122 | +2440.6325 | +108.1203 |
| Gross PnL | +3369.1730 | +3414.0799 | +44.9069 |
| PF | 1.42270 | 1.45473 | +0.03203 |
| Win rate | 19.19% | 20.12% | +0.94 pp |
| Realized MaxDD | 6.08% | 5.84% | Better |
| MTM MaxDD | 8.33% | 7.84% | Better |
| Top 1 net excluding | +1029.57 | +1155.60 | Better |
| Top 3 net excluding | -935.73 | -744.07 | Better but still negative |
| Top 5 net excluding | -1812.81 | -1792.56 | Slightly better but still negative |

D1 is `MIXED_PARTIAL` because it preserved the baseline top-5 winners and
slightly improved net/PF/DD, but it did not clearly improve entry quality:

- average entry price was worse than baseline;
- entry-to-stop distance was wider than baseline;
- average loser was worse than baseline;
- top 3 / top 5 removal remained negative;
- the same underlying winner-cluster fragility remains unresolved.

Therefore D1 can be retained as positive-but-fragile evidence, but not as a
pass, promotion path, or authorization to search more 1h rules.

### 2.5 Why Current Micro-tuning Should Stop

The research chain has reached a gate-design problem, not a rule-search
problem.

Continuing D2/D3/D4, new 1h entry variants, exit variants, overlays, or
parameter sweeps would be poorly timed because:

- Direction A and B-D1 both point to the same core issue: sparse trend payoff
  tail versus fragility interpretation.
- E-A showed that intuitive false-breakout filtering can destroy the payoff
  source.
- More small rule edits increase overfit risk before the evidence standard is
  clarified.
- The current top-winner gate may be too mechanical for trend-following, but
  removing it entirely would be too permissive.
- No current artifact is official validation evidence or small-live evidence.

The next step should recalibrate the evidence gate before additional strategy
experiments are proposed.

---

## 3. Sparse Trend Edge Acceptance Principle

Sparse Trend Edge is a strategy-evidence category for low-frequency trend
capture where returns are expected to be lumpy.

Allowed characteristics:

- low win rate;
- sparse profits;
- profit giveback;
- high payoff ratio;
- large-winner contribution;
- multi-day or multi-week holds;
- negative or near-flat years if market regime is explainable and losses are
  controlled.

Not allowed:

- a conclusion supported by one anomalous year only;
- a conclusion supported by one exchange/event artifact only;
- a conclusion supported by a few accidental spikes unrelated to the strategy
  hypothesis;
- a rule that works only after post-result selection of winners;
- relaxation of costs, slippage, or funding assumptions to make the result
  pass;
- parameter rescue after seeing fragility diagnostics.

Sparse trend evidence should not be judged as if it were a high-frequency or
high-win-rate mean-reversion strategy. But it still needs evidence that the
winner tail is structurally connected to the rule and not merely accidental.

---

## 4. Top-winner Concentration Gate Review

### 4.1 Should Top 3 / Top 5 Removal Automatically Block Pass?

Current answer: it should block deployability and official validation
readiness, but it should not automatically convert a sparse trend candidate
from positive evidence to reject.

For a trend strategy, the top winners are not noise by default. They may be the
expected payoff tail. A mechanical rule that says "net excluding top 3 or top 5
must remain positive" can wrongly reject a valid trend-following shape,
especially when the Owner explicitly accepts low win rate, sparse returns, and
large winner contribution.

However, top-winner removal must remain a serious fragility signal. If the
result collapses after removing top winners, the candidate should not pass
small-live readiness and should not be promoted. The question becomes whether
the winner concentration is structurally explainable or accidental.

### 4.2 Proposed Layered Winner Concentration Review

Top-winner concentration should be evaluated through layered questions:

| Layer | Question | Interpretation |
| --- | --- | --- |
| A. Cross-year occurrence | Do top winners appear across multiple years? | Cross-year winners reduce single-year anomaly risk. |
| B. Regime context | Do top winners occur in recognizable trend regimes? | Winners should match the main-trend lifecycle thesis. |
| C. Signal context | Were top winners naturally captured by the frozen rule? | Winners should not require after-the-fact explanation or discretionary exception. |
| D. Event anomaly | Are winners caused by isolated data/exchange/event spikes? | Event-spike dependence should move toward reject. |
| E. Residual loss | Is net excluding top winners negative but controlled? | Controlled residual loss may support pause, not pass. |
| F. Gross structure | Does gross expectancy remain structurally plausible? | Gross evidence helps separate cost drag from signal failure. |
| G. Cost explanation | Are funding, fees, and slippage still explainable? | Net edge must survive realistic costs without relaxation. |
| H. Symmetry check | What happens excluding worst losers? | Helps identify whether a few losses also distort the result. |
| I. Year concentration | Does one year carry nearly all net? | Single-year dependence should block pass. |

### 4.3 Reframed Gate Meaning

Top 3 / top 5 removal after costs should be treated as:

- **automatic blocker for deployability / small-live readiness** when negative;
- **strong fragility flag** for evidence review;
- **not automatic reject** if winners are cross-year, rule-consistent,
  regime-consistent, and residual losses are controlled;
- **reject signal** if winners are single-year, event-spike driven,
  rule-accidental, or only explainable after result inspection.

---

## 5. Revised Evidence Gate Draft

These classifications are proposed for future sparse trend research reports.
They are not retroactive promotion decisions.

### 5.1 `PASS_TO_EVIDENCE_REVIEW`

Meaning:

- candidate has enough research evidence to justify an official validation
  readiness review;
- not a promotion decision;
- not small-live readiness;
- not runtime implementation approval.

Minimum expectations:

- frozen rule defined before execution;
- trade count floors met for the configured window;
- gross expectancy positive;
- net after fees, slippage, and funding positive;
- PF above 1.0 with explainable drawdown;
- winner tail is cross-year or cross-regime enough to avoid single-anomaly
  dependence;
- top winners match the main-trend lifecycle thesis;
- net excluding top winners is either positive or negative but bounded and
  explicitly explainable;
- yearly concentration does not rely on one anomalous year;
- funding exposure is explainable.

### 5.2 `PAUSE_FRAGILE`

Meaning:

- positive evidence exists;
- the candidate is not deployable;
- fragility blocks pass until clarified by better attribution, longer window,
  or official validation design.

Typical conditions:

- net/PF/DD are promising;
- top winners are plausible trend winners;
- top 3 / top 5 removal is negative;
- residual loss excluding winners is meaningful but not catastrophic;
- year contribution is concentrated but not single-year only;
- evidence remains research-only.

### 5.3 `PAUSE_NEEDS_LONGER_WINDOW`

Meaning:

- existing evidence is directionally interesting but the historical window is
  too short or regime coverage is too narrow.

Typical conditions:

- sparse trend thesis requires more years to distinguish structural payoff tail
  from event luck;
- top winners are plausible but too few;
- yearly contribution concentration cannot be resolved inside current data;
- no new rule variants should be tested until the data-window question is
  answered.

### 5.4 `REJECT_OVERFITTED_WINNER_DEPENDENCE`

Meaning:

- apparent edge is mostly explained by accidental or overfit winner selection.

Typical conditions:

- top winners are concentrated in one year or one event;
- top winners do not match the strategy thesis;
- winners require post-hoc discretionary explanations;
- a small rule change or realistic cost treatment removes the full edge;
- residual net excluding top winners is deeply negative and not controlled;
- parameter or overlay choices appear selected to preserve known winners.

### 5.5 `REJECT_NO_EDGE`

Meaning:

- the candidate does not show positive structural evidence.

Typical conditions:

- gross expectancy is negative;
- net after realistic costs is negative;
- PF is below 1.0 without a compelling structural explanation;
- drawdown is disproportionate to the evidence;
- winners do not compensate for losses even before fragility checks.

### 5.6 `INSUFFICIENT_EVIDENCE`

Meaning:

- evidence volume, feasibility, or cleanliness is too weak to classify edge.

Typical conditions:

- trade floors not met;
- harness/proxy limitations prevent reliable interpretation;
- key diagnostics are missing;
- cost or execution assumptions are unresolved;
- result may be positive or negative but cannot support a research conclusion.

---

## 6. Required Diagnostics For Future Trend Reports

Future sparse trend reports must add or strengthen these analyses:

1. Winner attribution.
2. Top winner year / regime / signal context.
3. MFE / MAE distribution, not only max values.
4. Giveback distribution and giveback ratio.
5. Hold duration distribution.
6. Funding exposure by trade and by year.
7. Net excluding top 1 / top 3 / top 5 winners.
8. Net excluding worst 1 / worst 3 / worst 5 losers.
9. Yearly contribution concentration.
10. Whether winners match the main-trend lifecycle thesis.
11. Whether top winners were naturally captured by the frozen rule.
12. Whether top winners depend on isolated abnormal candles, exchange events,
    or data artifacts.
13. Cost bridge from gross to net, including fees, slippage, and funding.
14. Residual-loss interpretation after removing top winners.
15. Comparison against the frozen baseline without after-the-fact rule choice.

Reports should make a clear distinction between:

- "the payoff tail is expected and structurally captured";
- "the result is accidentally supported by a few spikes."

---

## 7. Current Owner-level Interpretation

### 7.1 Direction A

Recommended interpretation:

- retain as positive-but-fragile evidence;
- keep status at `PAUSE_FRAGILE`;
- do not reject solely because top 3 / top 5 removal is negative;
- do not pass to promotion, runtime, or small-live readiness;
- consider longer-window inspect before official validation readiness;
- keep as a reference baseline for future trend evidence, not as a deployable
  strategy candidate.

Direction A is worth preserving because it shows the right broad trend shape:
low win rate, high payoff, positive net, positive gross, moderate drawdown, and
multi-day trend capture. The unresolved issue is whether the winner tail is
structural enough across years and regimes.

### 7.2 Direction B-D1

Recommended interpretation:

- retain as positive-but-fragile / mixed-partial evidence;
- keep status at `PAUSE_FRAGILE` with entry-quality result
  `MIXED_PARTIAL`;
- do not continue automatically into D2/D3/D4;
- do not use D1 as justification for a multi-rule 1h search;
- consider only after the evidence gate is clarified and longer-window /
  attribution needs are defined.

B-D1 is useful because it preserved baseline top winners and modestly improved
net/PF/DD. It is not sufficient because entry quality did not clearly improve
and top-winner fragility remained.

### 7.3 Official Validation Later

Direction A and B-D1 are not ready for official validation now.

They may become candidates for official validation readiness review later only
if a separate task first defines:

- the longer data window or data-availability path;
- required winner attribution format;
- official validation checklist;
- pass/pause/reject gates using the revised sparse trend framework;
- a rule-freeze boundary that prevents parameter rescue.

### 7.4 Direction Map

If Owner does not want a longer-window / official-validation-readiness inspect,
the correct alternative is to return to `strategy-candidate-direction-map-v1`
for direction-level selection. That should be inspect-only first, not an
immediate experiment chain.

---

## 8. Explicit Non-authorization List

The following are not authorized:

- D2 experiment;
- D3 experiment;
- D4 experiment;
- new 1h entry rule;
- new exit variant;
- new overlay;
- parameter sweep;
- CPM rescue;
- E-A reopen;
- Direction A parameter sweep;
- Direction B multi-rule search;
- portfolio / regime / multi-strategy work;
- multi-asset work;
- complex ML;
- feature store;
- runtime/profile/risk changes;
- production strategy implementation;
- backtester / research engine core changes;
- promotion conclusion;
- small-live conclusion;
- live deployment advice.

The following are specifically not allowed as research rescue paths:

- continuing to rescue CPM;
- reopening E-A with buffers, waiting periods, thresholds, or partial exits;
- sweeping Donchian / EMA / stop lookback for Direction A;
- testing multiple 1h entry variants for Direction B after seeing D1;
- relaxing fees, slippage, or funding assumptions;
- selecting years after results are known;
- treating research-only adapter evidence as official validation evidence.

---

## 9. Final Recommendation

Recommended immediate decision:

1. Pause active strategy experiments.
2. Do not run D2/D3/D4 or any new overlay / entry / exit variant.
3. Treat Direction A and Direction B-D1 as positive-but-fragile evidence, not
   deployable candidates.
4. Recalibrate sparse trend evidence gates before more strategy experiments.
5. Inspect whether a longer historical window is available and useful.
6. Draft an official validation readiness checklist only after the evidence
   gate is accepted.
7. If Owner does not want longer-window inspection, return to the Strategy
   Candidate Direction Map for inspect-only direction selection.

Current hard conclusion:

> There is still no deployable small-live strategy candidate. Small-live
> readiness gate remains unmet.

---

## 10. Recommended Next Task Card - Not Executed

```markdown
# Task ID
TE-002

## Goal
Draft a docs-only Sparse Trend Official Validation Readiness Checklist and
longer-window inspect plan for Direction A / Direction B-D1 evidence.

## Why
TE-001 concludes that top-winner concentration should not mechanically reject
sparse trend strategies, but it remains a serious fragility blocker. Before
running new experiments, the project needs a checklist for winner attribution,
longer-window feasibility, and official validation readiness.

## Allowed files
- docs/ops/**
- reports/** inspect-only
- archive/** inspect-only

## Forbidden files
- src/**
- configs/**
- tests/**
- migrations/**
- runtime profiles
- production strategy implementation
- risk rules
- backtester / research engine core

## Requirements
1. Do not run experiments.
2. Do not write code or create adapters.
3. Define official validation readiness criteria for Sparse Trend Edge.
4. Define longer-window data availability questions without adding assets or
   changing timeframes unless separately approved.
5. Specify required diagnostics: winner attribution, top winner context,
   MFE/MAE distribution, giveback, hold duration, funding exposure, net
   excluding top winners and worst losers, yearly contribution concentration,
   and thesis fit.
6. Preserve research/runtime isolation.
7. State clearly that Direction A and Direction B-D1 remain non-deployable
   until separate Owner decisions.

## Tests
- Docs-only review; no tests.

## Done When
- A proposed validation readiness checklist exists under docs/ops/.
- The checklist states what evidence would allow `PASS_TO_EVIDENCE_REVIEW`
  versus `PAUSE_FRAGILE`, `PAUSE_NEEDS_LONGER_WINDOW`,
  `REJECT_OVERFITTED_WINNER_DEPENDENCE`, `REJECT_NO_EDGE`, or
  `INSUFFICIENT_EVIDENCE`.
- The document explicitly says it is not experiment authorization.
- The document explicitly says there is no deployable small-live strategy
  candidate and small-live readiness gate remains unmet.
```

---

## 11. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-07 | Initial Sparse Trend Edge evidence review and fragility gate draft | Codex |
