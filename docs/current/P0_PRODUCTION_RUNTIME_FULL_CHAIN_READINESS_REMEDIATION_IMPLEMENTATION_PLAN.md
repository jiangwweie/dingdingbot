---
title: P0_PRODUCTION_RUNTIME_FULL_CHAIN_READINESS_REMEDIATION_IMPLEMENTATION_PLAN
status: SUPERSEDED_ACTIVE_WORK_RETAINED_COMPONENT_PLAN
authority: docs/current/P0_PRODUCTION_RUNTIME_FULL_CHAIN_READINESS_REMEDIATION_IMPLEMENTATION_PLAN.md
implements: docs/current/P0_PRODUCTION_RUNTIME_FULL_CHAIN_READINESS_REMEDIATION_DESIGN.md
last_verified: 2026-07-20
repair_branch: codex/budget-model-review-20260714
production_head: 386cc3d761f17231a6c35d2bc96b347153cbd907
implementation_state: SUPERSEDED_BY_P0_ACH
owner_decision: CONFIRMED_2026-07-18
deployment_state: NO_CHANGE
exchange_write: 0
---

# P0 Production Runtime Full-Chain Readiness Remediation Implementation Plan

> **Current authority note:** this plan is not independently executable. Its remaining
> tasks are sequenced and accepted only through the current P0-ACH implementation plan.

## 1. Goal

Implement the approved design so Tokyo can:

- observe and compute every active candidate lane independently of submit
  occupancy;
- use one lifecycle-authoritative position/order gate at action time;
- keep core order and ticket-bound lifecycle projections converged;
- project Candidate Pool, Goal Status and monitor state from current causal
  truth;
- react automatically to a natural eligible signal through the official
  FinalGate and Operation Layer when all real-time facts allow it.

Owner confirmed implementation on **2026-07-18**. Code, additive migration,
bounded production projection repair, and Tokyo deployment may proceed only in
the sequence and authority boundary defined below.

## 2. Global Authority Model

```text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade.
Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

No task may:

- change current Owner policy values;
- expand the live profile or order-sizing defaults;
- create exchange write authority from a test, canary, replay, or detector fact;
- bypass FinalGate, Operation Layer, protection, reconciliation, or review;
- delete trading history or silently repair ambiguous production state.

## 3. Live Enablement State

### 3.1 Before

```text
chain_position: pretrade_candidate_readiness
stage: active_observation
first_blocker: active_position_resolution / observation-gate coupling
runtime result: 19 selected watcher instances stop before detector computation
projection result: healthy coverage can still become false market_wait_validated
goal result: historical submitted attempt remains current after lifecycle closure
real_submit result: not ready
owner_action_required: false
```

### 3.2 After

```text
chain_position: pretrade_candidate_readiness
stage: armed_observation with current detector decisions
first_blocker: per-lane computed_not_satisfied, exact engineering blocker, or current action-time safety state
runtime result: 22/22 lanes produce current typed observation outcomes
projection result: coverage, computation, readiness, and submit safety are distinct
goal result: terminal lifecycle falls back to current pretrade state
real_submit result: engineering-ready and conditional on natural fresh signal plus action-time gates
owner_action_required: false unless policy or abnormal safety intervention is genuinely required
```

## 4. Work Packages

| Order | Task | Priority | Capability unlocked |
| ---: | --- | --- | --- |
| 1 | **FRR-T00 Reproduction and contract freeze** | P0 | exact regression matrix |
| 2 | **FRR-T01 Lifecycle occupancy typed boundary** | P0 | one submit-blocking truth |
| 3 | **FRR-T02 Core order terminal projection convergence** | P0 safety | no recurring stale protection rows |
| 4 | **FRR-T03 Observation/action-time separation** | P0 | wide observation continues while submit blocks |
| 5 | **FRR-T04 Durable detector decision facts** | P0 | actual computed/failed-fact truth per lane |
| 6 | **FRR-T05 Candidate Pool and readiness correction** | P0 | no false market wait |
| 7 | **FRR-T06 Goal Status and monitor terminal-state correction** | P0 | current Owner product state |
| 8 | **FRR-T07 Deploy probe baseline correction** | P1 ops | no stale migration false blocker |
| 9 | **FRR-T08 PostgreSQL/full regression certification** | P0 gate | exact-head deploy candidate |
| 10 | **FRR-T09 Tokyo canary and projection repair** | P0 deploy | production observation restored |
| 11 | **FRR-T10 Full-chain postdeploy acceptance** | P0 closure | natural-signal-capable production state |

### 4.1 Implementation progress as of 2026-07-19

| Work package | Local state | Evidence | Remaining release gate |
| --- | --- | --- | --- |
| FRR-T01 / T02 | implemented | typed `LifecycleOccupancySnapshot`, exact terminal core-order projector and dry-run/apply repair command | disposable-PostgreSQL migration and production dry-run |
| FRR-T03 / T04 | implemented | observation proceeds before Action-Time blocking; watcher writes `pretrade_strategy` detector facts | Tokyo canary verifies all active lanes |
| FRR-T05 / T06 | implemented | Candidate Pool no longer treats public facts as detector computation; Goal Status retires closed attempts | current projection consistency check after canary |
| FRR-T07 | implemented | generic readonly probe has no stale head/schema defaults; postdeploy requires exact target values | target release plan review |
| FRR-T08 | in progress | focused regression suites, migration 137 and production file-I/O audit are green | full local certification and disposable PostgreSQL apply |
| FRR-T09 / T10 | pending | no production mutation has occurred | deploy, dry-run projection repair, canary and natural-signal readiness validation |

## 5. FRR-T00 Reproduction And Contract Freeze

### Goal

Convert the current Tokyo facts into deterministic failing tests before changing
implementation.

### Allowed files

- focused unit/integration tests;
- PG test fixtures for `orders`, positions and ticket-bound lifecycle tables;
- this design and implementation plan.

### Requirements

1. Reproduce one flat account with a stale core protection order and terminal
   ticket-bound lifecycle.
2. Prove current code returns `NEXT-ATTEMPT-POSITION-ORDER-CONFLICT` before
   detector evaluation.
3. Prove current Candidate Pool can report market wait without a detector
   decision fact.
4. Prove current Goal Status remains `real_order_submitted` after terminal
   post-submit closure.
5. Prove the old ghost-order regression asserts only the ticket-bound table.

### Tests

- `tests/unit/test_runtime_next_attempt_observation_cycle.py`;
- `tests/unit/test_ticket_bound_protection_reconciler.py`;
- `tests/unit/test_strategy_live_candidate_pool.py`;
- `tests/unit/test_strategygroup_runtime_goal_status.py`;
- one disposable-PostgreSQL causal integration scenario.

### Done when

All four defects fail for the expected reason on the current deployed code
shape, with no exchange effect.

## 6. FRR-T01 Lifecycle Occupancy Typed Boundary

### Goal

Create one typed current lifecycle/account occupancy answer for action-time and
next-submit safety.

### Proposed files

- `src/application/action_time/lifecycle_occupancy.py` or an equivalent existing
  lifecycle current-state module;
- `src/application/readmodels/trading_console.py`;
- `src/infrastructure/runtime_control_state_repository.py` if a bounded typed
  repository profile is required;
- focused tests.

### Requirements

1. Model states: `flat_and_clear`, `open_protected`, `recovery_required`,
   `unknown_fail_closed`.
2. Bind exact account, venue, instrument, side/netting domain and Ticket/lifecycle
   identity.
3. Prefer current ticket-bound lifecycle/reconciliation/closure truth over
   generic core order counts.
4. Treat stale or ambiguous exchange/account facts as fail-closed for submit.
5. Keep observation authority false and exchange write false.

### Blocker removed or reclassified

`NEXT-ATTEMPT-POSITION-ORDER-CONFLICT` becomes either:

- no blocker when terminal lifecycle and flat current facts agree;
- `active_position_resolution` with exact lifecycle/account evidence;
- `hard_safety_stop` for unknown/contradictory authority state.

### Stop condition

Stop if the typed snapshot cannot conserve exact account or canonical instrument
identity without a schema migration.

## 7. FRR-T02 Core Order Terminal Projection Convergence

### Goal

Ensure terminal ticket-bound lifecycle truth updates matching core `orders`
projection rows exactly once.

### Proposed files

- `src/application/action_time/ticket_bound_lifecycle_finalizer.py`;
- `src/application/action_time/lifecycle_maintenance_service.py`;
- `src/infrastructure/pg_order_repository.py`;
- migration `137` if indexes/constraints are required;
- focused unit and PostgreSQL tests.

### Requirements

1. One owner function performs terminal convergence.
2. Match exact local order, exchange order, ticket, role, symbol and parent
   identity.
3. Map ticket-bound statuses to core terminal statuses deterministically.
4. Append audit lineage before/with each correction.
5. Repeated calls are idempotent.
6. Never downgrade a terminal core order or overwrite a contradictory live
   exchange state.
7. Do not delete rows.

### Per-symbol acceptance

| Symbol | Expected corrected core state |
| --- | --- |
| AVAX | SL becomes `CANCELED` |
| BTC | SL becomes `FILLED` |
| ETH | replaced SL becomes `CANCELED` |
| SOL | SL becomes `FILLED`; TP1 becomes `CANCELED` |

### Capability unlocked

`lifecycle_projection_converged`

## 8. FRR-T03 Observation And Action-Time Separation

### Goal

Make detector observation independent from new-submit occupancy while keeping
action-time fail-closed.

### Proposed files

- `src/interfaces/api_trading_console.py`;
- `scripts/runtime_active_observation_monitor.py`;
- `src/application/readmodels/watcher_decision_fact_projection.py`;
- focused API/watcher tests.

### Requirements

1. Resolve runtime lane identity before detector evaluation.
2. Run market-source and detector computation even when lifecycle occupancy is
   `open_protected` or `recovery_required`.
3. Return separate typed sections:
   - `observation_result`;
   - `detector_decision`;
   - `action_time_readiness`;
   - `safety_invariants`.
4. A fresh signal may create durable signal observation/promotion input, but
   action-time lane, Ticket and real submit remain blocked by occupancy.
5. Compact projection retains exact first blocker without exceeding size caps.

### Required scenarios

| Scenario | Observation | Action time |
| --- | --- | --- |
| flat and clear | compute | may continue |
| open protected | compute | block new submit |
| stale PG/order mismatch | compute | recovery required |
| technical HTTP failure | unavailable | block |
| computed false facts | computed-not-satisfied | no action |
| fresh signal + conflict | signal recorded | block lane/Ticket/submit |

### Capability unlocked

`wide_observation_with_fail_closed_action_time`

## 9. FRR-T04 Durable Detector Decision Facts

### Goal

Persist actual per-lane detector computation so read models no longer infer it
from public facts or technical coverage.

### Proposed files

- `scripts/runtime_active_observation_monitor.py`;
- `src/application/action_time/runtime_pg_fact_snapshots.py` or a new bounded
  detector-fact writer in the same fact-snapshot family;
- `src/application/readmodels/watcher_decision_fact_projection.py`;
- migration/index tests if required.

### Requirements

1. Use `fact_surface='pretrade_strategy'`.
2. Stable ID includes lane identity, evaluator/event version and trigger candle
   close.
3. Upsert repeated ticks for the same event identity.
4. Preserve failed facts, event time authority, signal grade and execution mode.
5. Technical failure does not write a computed detector fact.
6. No-signal ticks create zero JSON/MD files.
7. Retention is PG-owned and bounded.

### Performance acceptance

- maximum one current/upsert decision row per lane per closed-candle identity;
- no unbounded per-process trace rows;
- existing 60-second API cap and watcher global deadline remain.

### Capability unlocked

`detector_decision_truth_durable`

## 10. FRR-T05 Candidate Pool And Readiness Correction

### Goal

Project one precise first blocker per lane from distinct technical coverage,
public inputs, detector decision and action-time safety.

### Proposed files

- `src/application/readmodels/strategy_live_candidate_pool.py`;
- `scripts/publish_runtime_control_current_projections.py`;
- `src/application/readmodels/daily_live_enablement_table.py` if mapping changes;
- Tradeability/current projection tests.

### Requirements

1. `detector_attached/computed` comes only from a current detector decision or
   typed detector capability declaration plus current result.
2. `watcher_state` comes only from watcher coverage.
3. `public_facts_state` comes only from public input facts.
4. `market_wait_validated` requires the full blocker contract checklist.
5. An action-time-only deferred blocker must not overwrite the detail of the
   current market blocker.
6. `brc_pretrade_readiness_rows` remains single-owner projected state.
7. Candidate Pool, Daily Table and Tradeability agree on first blocker and
   source watermark.

### Negative acceptance

- healthy coverage + no detector fact => `detector_not_attached`, not market wait;
- detector computed false => `computed_not_satisfied`;
- detector fresh signal + occupancy conflict => signal present with
  `active_position_resolution` at action time;
- technical failure => `watcher_tick_missing`.

### Capability unlocked

`market_wait_truth_validated`

## 11. FRR-T06 Goal Status And Monitor Terminal Correction

### Goal

Make current product status depend on unresolved current lineage, not the latest
historical submitted attempt.

### Proposed files

- `src/application/readmodels/strategygroup_runtime_goal_status.py`;
- `scripts/run_tokyo_runtime_server_monitor.py`;
- current projection and notification tests.

### Requirements

1. Join submitted attempt to lifecycle and post-submit closure.
2. `real_order_submitted` remains current only while closure is unresolved.
3. Closed attempts remain audit evidence but do not own current status.
4. Candidate Pool and Goal Status use the same current projection run/watermark.
5. Monitor notification dedupe key changes only when current product state or
   exact blocker changes.
6. Current observation-only engineering blockers do not ask Owner to operate
   internal gates.

### Capability unlocked

`owner_status_current_and_closure_aware`

## 12. FRR-T07 Deploy Probe Baseline Correction

### Goal

Remove false deployment blockers caused by hard-coded migration expectations.

### Proposed files

- `scripts/probe_tokyo_runtime_governance_readonly.py`;
- `scripts/verify_tokyo_runtime_governance_postdeploy.py`;
- `scripts/plan_tokyo_runtime_governance_git_deploy.py`;
- deploy tests.

### Requirements

1. Deploy plan supplies exact expected remote and target migration identities.
2. Postdeploy verifier requires the target release count/latest migration.
3. Generic readonly probe without expected baseline reports facts, not mismatch.
4. Exact target-head mismatch remains a blocker.

## 13. FRR-T08 PostgreSQL And Full Regression Certification

### Test groups

1. Focused unit and API tests.
2. Real disposable-PostgreSQL lifecycle/order projection tests.
3. Repeated-cadence tests across the same candle identity.
4. Candidate Pool/Goal Status/Monitor consistency tests.
5. Ticket/FinalGate/Operation Layer non-executing rehearsal tests.
6. Full isolated suite.
7. Output scope and production file-I/O audit.
8. Linux/amd64 runtime dependency/hash-lock validation when deployment content
   changes.

### Exact-head gates

| Gate | Required result |
| --- | --- |
| Git status | only intended tracked changes |
| Migration | 137 applies to disposable PostgreSQL |
| Focused tests | all pass |
| Full tests | all pass, existing justified skips only |
| File-I/O audit | `performance_risk.status=clear` |
| Output artifact scope | no tracked/generated output violations |
| Safety sentinel | zero forbidden effect |
| Source identity | one exact full SHA used by deploy plan and verification |

### Stop condition

No Tokyo deployment if any current projection disagreement, test-created legacy
report authority, migration ambiguity or forbidden exchange effect remains.

## 14. FRR-T09 Tokyo Canary And Projection Repair

### Phase A: readonly preflight

- verify exact current release, services, schema, disk and PG health;
- capture current positions, open orders, lifecycle, closures and watcher rows;
- run signed GET-only account/position/open-order facts;
- confirm writer fence state and official runtime capability boundary.

### Phase B: deploy and canary

1. Apply migration and exact release through the approved git/export deploy
   path.
2. Start backend and run readonly health checks.
3. Run watcher canary with exchange writes disabled.
4. Require typed observation results for all selected lanes.
5. Confirm detector decision facts are written with zero Ticket/order creation.
6. Publish current projections and inspect first-blocker matrix.

### Phase C: production projection repair

1. Execute stale-order repair in dry-run mode.
2. Require exactly the proven terminal lineage set.
3. Apply bounded core-order status convergence in one transaction.
4. Append audit events.
5. Refresh watcher, Candidate Pool, Goal Status and Monitor.

### Hard stop

Stop before apply if any of these appear:

- exchange position quantity is non-zero for an affected symbol;
- matching exchange protection order remains open;
- ticket/core/exchange IDs do not match;
- a new live signal or active action-time lane appears during the maintenance
  transaction;
- an unknown exchange outcome exists.

## 15. FRR-T10 Full-Chain Postdeploy Acceptance

### Immediate acceptance

| Check | Required result |
| --- | --- |
| Backend | active and HTTP 200 |
| Timers | watcher, monitor, lifecycle active |
| Observation | 22/22 typed current results |
| Detector truth | per-lane current detector decisions |
| Core orders | no stale OPEN rows for terminal lifecycles |
| Candidate Pool | precise blocker matrix, no false market wait |
| Goal Status | not stuck at terminal historical submit |
| Monitor | current notification decision only |
| Exchange effects | zero during canary/repair |

### Action-time capability acceptance

Use a production-shaped non-executing rehearsal to prove:

```text
fresh-like typed detector event
-> PG signal identity
-> promotion candidate
-> one action-time lane
-> exact Ticket
-> Runtime Safety State
-> FinalGate preflight
-> durable Operation Layer command preparation
-> stop before gateway.place_order()
```

This rehearsal proves engineering capability only. It must not be inserted as a
live market signal and must not grant runtime order authority.

### Natural-signal acceptance

The next naturally occurring eligible signal is the final live calibration:

- if all current gates pass, the official chain may submit inside existing
  standing authorization;
- if a genuine action-time blocker appears, it must persist with exact Ticket
  and fact lineage;
- no additional Owner confirmation is required for ordinary in-boundary
  execution;
- any policy/profile/scope expansion still requires Owner authority.

## 16. Rollback Plan

### Code rollback

- retain previous release directory;
- switch current symlink only after stopping mixed-generation timer execution;
- restart backend and timers on the previous exact head;
- verify schema compatibility and health.

### Data rollback

Terminal core-order corrections are evidence-backed current projection repairs.
They are not automatically reversed. Recovery requires new contradictory
exchange evidence plus a dedicated audited repair decision.

Migration 137 must be additive so old code can ignore new indexes/fields safely.

### Notification rollback

If Goal Status/monitor projection is wrong after deploy, disable only the new
notification decision path while keeping watcher observation and trade safety
fail-closed. Do not fall back to local JSON/cache authority.

## 17. Completion Definition

The task is complete only when:

1. the exact root-cause regressions are green;
2. 22/22 production candidate lanes have current detector truth;
3. core order and ticket-bound lifecycle projections agree;
4. one current first blocker is conserved across Candidate Pool, Tradeability,
   Daily Table, Goal Status and Monitor;
5. the deployed program is ready to react to a natural eligible signal through
   the official real-order chain;
6. no safety, authority, profile, sizing or file-I/O boundary regresses;
7. Tokyo exact-head and schema evidence is captured;
8. production acceptance records zero unauthorized exchange effects.

## 18. Owner Confirmation Gate

Implementation, migration creation, production data repair and deployment remain
stopped until the Owner confirms this design and plan.
