# Crypto Pullback Module v1 — Promotion / Rejection Criteria Draft

**Task ID:** CPM-CRITERIA-001  
**Date:** 2026-05-06  
**Status:** Criteria draft; current CPM-1 state is Paused  
**Scope:** Baseline Strategy Module Stabilization governance

This document is a criteria draft for Owner review. It is not promotion approval,
experiment approval, runtime change approval, live enablement approval, or a
strategy implementation task.

It defines how future evidence should be interpreted before CPM-1 is continued,
paused, rejected, sent through a 2022 OOS gate, or considered a small-live
candidate. It does not approve running 2022 OOS.

---

## 1. Status

Current status:

- CPM-1 remains a frozen baseline strategy module.
- CPM-1 remains the only priority strategy module under Baseline Strategy Module
  Stabilization.
- CPM-1 is not the system-level strategy.
- 2021 and 2022 OOS have both been run and are negative.
- CPM-1 is paused after CPM-OOS-FAILURE-CLASSIFY-001.
- CPM-1 is not a Small-live Candidate or canary-live candidate.
- CPM-1's promotion path is stopped unless Owner explicitly approves a separate
  reclassification or bounded research path.
- Research results must not automatically change runtime profile, strategy
  parameters, risk rules, or live enablement.

This criteria draft exists to reduce after-the-fact interpretation risk. Future
OOS results, runtime observation, or evidence consolidation should be judged
against pre-written decision states instead of being retrofitted into a tuning
story.

---

## 2. Decision States

| State | Meaning | Allowed Follow-up | Not Allowed |
| --- | --- | --- | --- |
| Continue Observation | Keep CPM-1 frozen and continue documentation or runtime observation. | Longer observation window, evidence matrix cleanup, Owner criteria review. | Runtime parameter changes, live promotion, research-to-runtime changes. |
| Require 2022 OOS Gate | Owner decides that CPM-1 cannot become a small-live candidate without 2022 OOS. | Create an inspect plan and request explicit Owner approval before any run. | Running OOS automatically, tuning after seeing results. |
| Pause CPM-1 | Stop treating CPM-1 as an active candidate while preserving evidence. | Diagnose pause cause, decide whether to resume, reject, or reopen research. | Silent continued observation as if status were unchanged. |
| Reject CPM-1 as Current Baseline | Current frozen baseline is not worth carrying as a candidate. | Archive criteria outcome; optionally define a separate CPM-2 research question. | Rebranding rejection as parameter tuning without a new approval. |
| Small-live Candidate | CPM-1 has enough evidence and operational readiness to be considered by Owner for a possible small-live decision. | Owner review of live enablement, capital, risk, and runtime readiness. | Treating candidate status as approval to trade real funds. |
| Reopen Research | Open a bounded research question because evidence identifies a specific unresolved mechanism. | New research plan with fixed question, allowed data, and no runtime effect. | Open-ended parameter search or rescue tuning. |

---

## 3. Evidence Dimensions

| Dimension | What Must Be Clear | Decision Use |
| --- | --- | --- |
| Evidence completeness | Which years, cost model, same-bar policy, funding assumptions, and report semantics are covered. | Prevents incomplete evidence from being treated as promotion-ready. |
| OOS requirement | Whether 2022 OOS is required before candidate status. | Separates evidence gap from experiment authorization. |
| 2023-style boundary cost acceptance | Whether Owner accepts 2023-style failure as applicable-boundary cost. | Determines whether CPM-1 can continue despite known regime mismatch. |
| Performance consistency | Whether positive evidence comes from stable behavior or one narrow window. | Helps distinguish module viability from accidental period fit. |
| Drawdown interpretation | MaxDD must be read with correct report semantics and cost assumptions. | Prevents hard-coding drawdown targets as architecture constraints. |
| Trade count sufficiency | Evidence must have enough trades to be interpretable under the tested window. | Avoids promoting thin samples or over-filtered variants. |
| Same-bar policy clarity | Same-bar handling must be stated for any performance evidence. | Prevents execution-timing ambiguity from contaminating conclusions. |
| Cost / funding assumptions | Fee model and funding treatment must be explicit or caveated. | Prevents comparing mixed historical/proxy results as equivalent. |
| Market-boundary clarity | Applicable and not-applicable markets must be stated. | Prevents using CPM-1 as a general crypto strategy. |
| Runtime observation separation | Runtime observation can validate operational behavior, not strategy edge. | Keeps execution stability separate from research conclusions. |
| Live-safe readiness dependency | Small-live candidate status depends on live-safe guardrails remaining credible. | Prevents strategy readiness from bypassing execution safety. |
| Research/runtime isolation | Research evidence may inform Owner decisions but never mutates runtime by itself. | Protects runtime profile, risk rules, and live enablement from automatic changes. |

---

## 4. Promotion Criteria Draft

CPM-1 may be labeled **Small-live Candidate** only if all of the following are
true. Candidate status means "eligible for Owner live review," not "approved for
live trading."

1. The frozen baseline identity is unchanged: ETH 1h, 4h MTF confirmation,
   LONG-only, current trigger/filter/exit profile, no hidden parameter changes.
2. Evidence documents clearly state data window, cost model, funding treatment
   when relevant, same-bar policy, trade count, and drawdown semantics.
3. Owner has made an explicit decision on whether 2022 OOS is required before
   candidate status.
4. If Owner requires 2022 OOS, the OOS result has been reviewed under the rules
   in this document and does not create an unresolved fatal evidence gap.
5. 2023-style failure is either explicitly accepted by Owner as boundary cost,
   or classified into a bounded research question without changing runtime.
6. Evidence supports a coherent profit/failure hypothesis: trend-pullback
   continuation works in defined market boundaries and fails in understood
   invalid boundaries.
7. Drawdown and loss behavior are understandable as module risk, not symptoms
   of a data bug, execution bug, or hidden look-ahead assumption.
8. Trade count is sufficient for the evidence window being used; over-filtered
   variants or thin samples cannot define candidate status.
9. Runtime observation, if used, shows no unexplained strategy-related behavior
   such as unexpected signal cadence, malformed orders, or inconsistent exit
   lifecycle tied to CPM-1 behavior.
10. Live-safe dependencies remain acceptable: order watch, daily risk limits,
    periodic reconciliation observation, shutdown behavior, and protection
    handling are not degraded.
11. Research/runtime isolation remains intact: no research result has directly
    changed runtime profile, parameters, risk rules, or live enablement.
12. Owner explicitly acknowledges that candidate status is not permission to
    activate real funds.

This draft intentionally avoids fixed return or annualized performance targets.
Returns are evaluation outputs, not architecture constraints or automatic gates.

---

## 5. Pause Criteria Draft

CPM-1 should be paused, rather than simply kept under observation, if any of the
following occurs:

1. New evidence directly undermines the core profit hypothesis and cannot be
   explained as known boundary cost.
2. Owner-approved OOS exposes loss behavior that is outside accepted risk
   boundaries or inconsistent with the documented failure hypothesis.
3. Evidence reveals a data issue, same-bar policy issue, cost/funding mismatch,
   or report semantic error large enough to make current conclusions unreliable.
4. Runtime observation shows strategy-related behavior that cannot be explained
   from the frozen baseline and current execution design.
5. Live-safe dependencies regress in a way that makes continued CPM-1
   observation misleading or unsafe.
6. The baseline is no longer actually frozen because runtime/profile/code
   changes have drifted from the CPM-1 SSOT.
7. Owner has not decided a required gate, such as 2022 OOS, but downstream
   planning starts treating CPM-1 as promotion-ready anyway.

Pause means "stop promotion movement until classified." It does not automatically
mean strategy rejection.

---

## 6. Rejection Criteria Draft

Rejecting CPM-1 as the current baseline should be considered when evidence shows
that continued observation is unlikely to be useful under the frozen profile.

### 6.1 Module Hypothesis Failure

Reject as current baseline if trend-pullback continuation no longer has a
coherent supported profit/failure story after evidence review, or if positive
periods are not tied to the documented applicable market.

### 6.2 Parameter Profile Failure

Reject the frozen baseline profile if evidence indicates the module concept may
be valid but the current trigger/filter/exit profile is structurally inadequate.
This does not authorize tuning. It means a new, bounded research task would be
needed before any alternative profile can be considered.

### 6.3 Data / Cost Assumption Failure

Reject current conclusions, not necessarily the module, if cost model, funding,
same-bar, data quality, or MaxDD semantics are materially wrong. The correct
state may be Pause or Reopen Research, depending on whether the evidence can be
reconstructed cleanly.

### 6.4 Live-safe Execution Environment Issue

Do not reject CPM-1 because the execution environment is temporarily not ready.
If the strategy evidence remains coherent but live-safe readiness regresses, the
correct state is Pause CPM-1 or Continue Observation without promotion movement.

### 6.5 Current Baseline Rejection Triggers

The current baseline should be rejected as a candidate if:

1. Owner does not accept the known boundary cost and no approved research path
   can separate that boundary without destroying good-year behavior.
2. Owner-approved OOS fails in a way classified as module/profile failure rather
   than acceptable boundary cost or data-assumption failure.
3. Evidence remains too incomplete for candidate status and additional evidence
   is not worth acquiring.
4. Trade count or performance concentration is too thin to support future
   operator confidence under the frozen baseline.
5. The only plausible improvement path is open-ended parameter search, runtime
   regime expansion, cross-asset expansion, or hard filtering that violates
   current scope.

---

## 7. 2022 OOS Interpretation Rules

2022 is an OOS candidate, not an approved task. Running it requires explicit
Owner approval and a separate bounded plan.

If Owner approves a 2022 OOS run later, interpret the result as follows:

1. The run must use the frozen CPM-1 baseline unless Owner approves a different
   research question before the run.
2. The run must state data source, cost model, funding assumption, same-bar
   policy, trade count, and drawdown semantics.
3. The result must not trigger automatic parameter search.
4. The result must not modify runtime profile, strategy parameters, risk rules,
   or live enablement.
5. OOS failure does not automatically mean "rebuild the strategy." First classify
   whether the failure is:
   - known boundary cost,
   - new module hypothesis failure,
   - frozen parameter profile failure,
   - data/cost/funding assumption failure,
   - insufficient trade count,
   - execution or backtest methodology issue.
6. OOS success does not automatically mean runtime promotion. It only reduces
   the evidence-completeness gap and may support Owner review for Small-live
   Candidate status.
7. Mixed results should be classified before action. A profitable but
   concentrated, thin, or assumption-sensitive OOS does not automatically pass.
8. A failed OOS may still support Continue Observation if failure matches an
   Owner-accepted boundary cost and live-safe/runtime evidence remains clean.

---

## 8. Owner Decision Questions

1. Does Owner accept 2023-style failure as CPM-1 applicable-boundary cost?
2. Should 2022 OOS become a required promotion gate before Small-live Candidate
   status?
3. Should the current baseline remain frozen through any OOS and observation
   period?
4. Should Small-live Candidate status require additional live-safe observation
   conditions beyond the current LS-002b and LS-003d state?
5. What specific evidence should trigger Pause rather than Continue Observation?
6. What evidence would be enough to reject the current frozen baseline?
7. If 2022 OOS fails, which failure classifications should lead to rejection
   versus pause versus reopen research?
8. If 2022 OOS succeeds, what additional non-research gates are required before
   candidate status?
9. Is future E4 work allowed only as a risk-state label / position-sizing
   research question, never as a hard filter under CPM-1?
10. Is runtime observation intended to judge only operational correctness, or
    should it also define a minimum observation duration before candidate status?

---

## 9. Not-Now List

The following are explicitly not authorized by this criteria draft:

- No parameter change.
- No E4 hard filter.
- No SHORT runtime.
- No BTC/SOL expansion.
- No ETH 15m or 4h primary-timeframe expansion.
- No cross-asset or cross-timeframe expansion.
- No regime system.
- No portfolio engine.
- No multi-strategy routing.
- No runtime profile change.
- No research-to-runtime promotion.
- No live-safe change.
- No frontend control.
- No backtester or research engine change.
- No 2022 OOS run without Owner approval.
- No live enablement or small-live approval.

---

## 10. Next-step Recommendation

Recommended next step is Owner review of this criteria draft before any new
research or observation task is approved.

After review, Owner may choose one of these paths:

1. **Owner review criteria:** accept, edit, or reject the decision states and
   criteria in this document.
2. **2022 OOS gate inspect plan:** create a no-run plan describing exact data,
   assumptions, acceptance interpretation, and failure classification for a
   possible future OOS.
3. **Longer runtime observation criteria:** define observation duration and
   operational signals that matter for CPM-1 without changing strategy logic.
4. **Pause after documentation consolidation:** stop CPM-1 work temporarily
   after SSOT/criteria cleanup and return to Live-safe or other approved tasks.

No path above is automatically approved by this document.

---

## 11. Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-05-06 | Initial CPM-1 promotion/rejection criteria draft | Codex |
