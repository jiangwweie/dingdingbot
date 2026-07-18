---
title: P0_RUNTIME_OBSERVATION_TRUTH_AND_FORENSICS_REMEDIATION_IMPLEMENTATION_PLAN
status: CURRENT_IMPLEMENTATION_PLAN
authority: docs/current/P0_RUNTIME_OBSERVATION_TRUTH_AND_FORENSICS_REMEDIATION_IMPLEMENTATION_PLAN.md
implements: docs/current/P0_RUNTIME_OBSERVATION_TRUTH_AND_FORENSICS_REMEDIATION_DESIGN.md
last_verified: 2026-07-18
repair_branch: codex/dual-position-account-risk-remediation-v1
repair_worktree: /Users/jiangwei/Documents/final/.worktrees/dual-position-account-risk-remediation-v1
repair_baseline_head: 473be8113a34c35082798a18019f758bf57bf120
prior_certified_source_commit: e4f49dcfa77932f6ec440b3a869943eb2ade73a1
exact_certified_source_commit: bf634a7e2695e397adcc4a7107d4a48cb33ac98c
implementation_state: LOCAL_EXACT_HEAD_CERTIFIED_AWAITING_T09
release_gate: LOCAL_REMEDIATION_CERTIFIED_AWAITING_TOKYO_CANARY
deployment_state: DEPLOYMENT_NO_GO
production_state: UNCHANGED
policy_activation: NOT_PERFORMED
exchange_write: 0
---

# P0 Runtime Observation Truth And Forensics Remediation Implementation Plan

## 1. Goal

Repair the current merge branch so one production-shaped watcher cycle
preserves the same blocker and health truth from Trading Console through compact
transport, PG coverage, current projections, Owner monitoring, signal forensics,
and official reconciliation.

The plan directly implements:

```text
docs/current/P0_RUNTIME_OBSERVATION_TRUTH_AND_FORENSICS_REMEDIATION_DESIGN.md
```

## 2. Why This Is P0

The demonstrated defect blocks **19 of 22** production candidate lanes, records
false healthy liveness, invalidates market-absence conclusions, and causes the
forensics reducer to replace exact Invocation blockers with a generic missing
promotion conclusion.

This is a pre-trade truth failure. It does not change strategy quality or
trading policy, but it prevents the system from knowing whether a strategy was
observed and why a signal stopped.

## 3. Frozen Scope And Authority

### 3.1 Required branch

| Property | Required value | Verification |
| --- | --- | --- |
| **Worktree** | `/Users/jiangwei/Documents/final/.worktrees/dual-position-account-risk-remediation-v1` | `pwd` |
| **Branch** | `codex/dual-position-account-risk-remediation-v1` | `git branch --show-current` |
| **Repair start** | `473be8113a34c35082798a18019f758bf57bf120` or its docs-only descendant | `git merge-base --is-ancestor` |
| **Prior certified code** | `e4f49dcfa77932f6ec440b3a869943eb2ade73a1` | ancestry and diff |
| **Worktree state before implementation** | only approved documentation changes | `git status --short` |
| **Production state** | unchanged until T09 | Tokyo release manifest and systemd status |

The old release branch is not an implementation target and must not receive
cherry-picked parallel fixes.

### 3.2 Global Authority Model

```text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade.
Runtime Safety State answers live-submit safety.
Review updates strategy governance.
```

This program changes engineering truth only. It does not change Owner policy,
runtime profile, strategy semantics, candidate scope, capital, leverage,
notional, attempt cap, or exchange-write authority.

### 3.3 Hard stops

Stop the affected task immediately if it requires:

- a FinalGate or Operation Layer bypass;
- a live profile, sizing, capital, leverage, notional, symbol, or side change;
- a withdrawal, transfer, credential, or secret mutation;
- manual SQL against production order/lifecycle rows;
- a second watcher/coverage/forensics authority;
- production fallback to JSON/MD/output files;
- a new migration without a design amendment;
- exchange cancellation without exact PG/Ticket/order identity proof;
- edits outside the task card's allowed files.

## 4. Live Enablement Transition

### 4.1 Before

```text
chain_position: pretrade_candidate_readiness
stage: active_observation
first_blocker: schema_invalid
runtime result: 19/22 lanes return HTTP 400
coverage result: selected scope may still appear covered/active
forensics result: missing promotion may hide Invocation blocker
market wait: not validated
```

### 4.2 After

```text
chain_position: pretrade_candidate_readiness
stage: active_observation_truth_certified
first_blocker: per-lane exact business, market, runtime, or safety blocker
runtime result: 22/22 lanes return typed observation result or explicit failed liveness
coverage result: actual observation result backs liveness
forensics result: Signal -> Invocation -> Process Outcome -> downstream lineage
market wait: allowed only after complete 22-lane checklist
```

### 4.3 Capability unlocked

**`observation_truth_certified`**: every active lane can be classified as
computed, business-blocked, technically unavailable, or missing scope without
false market-wait compression.

## 5. Execution Order

| Order | Task | Priority | Dependency | Completion result |
| --- | --- | --- | --- | --- |
| T00 | Documentation and certification reopen | P0 | none | current docs name the repair and deployment no-go |
| T01 | Production-shaped RED fixtures | P0 | T00 | current branch fails on the exact demonstrated shapes |
| T02 | Typed compact blocker and HTTP semantics | P0 | T01 | structured blockers return HTTP 200; internal projection failures return 500 |
| T03 | Observation-result-backed coverage/liveness | P0 | T02 | PG liveness reflects actual API result |
| T04 | Current projection and Resume ownership | P0 | T03 | no layer emits market wait without full checklist |
| T05 | Forensics causal lineage v2 | P0 | T03 | Invocation and Process Outcome determine earliest blocker |
| T06 | Ghost-order official closure proof | P0 safety | T03/T05 | five PG ghost rows are officially closed or remain exact safety blockers |
| T07 | Cross-layer PostgreSQL certification | P0 | T02-T06 | 22-lane positive/negative matrix passes |
| T08 | Full branch re-certification | P0 | T07 | one exact source commit passes all gates |
| T09 | Tokyo canary, deploy, and read-only acceptance | P0 deploy | T08 | production observes 22 lanes without false healthy state |
| T10 | Production reconciliation closure and document acceptance | P0 closure | T09 | ghost state closed, docs and roadmap reflect deployed truth |

### 5.1 Local execution evidence — 2026-07-18

| Task | Local status | Evidence |
| --- | --- | --- |
| **T00–T03** | complete | Typed compact blockers, HTTP failure semantics, and actual-result-backed coverage passed the focused watcher matrix. |
| **T04** | complete | Resume Dispatcher returns neutral `no_actionable_pg_ticket`; failed/degraded watcher liveness cannot be projected as active scope. |
| **T05** | complete | Forensics stdout contract is `brc.runtime_signal_forensics.v2`; persisted Invocation and Process Outcome win over a missing Promotion. |
| **T06** | complete in rehearsal | Exact Ticket-bound PG ghost protection rows terminalize only after flat-position plus absent-order proof; audit payload records `exchange_write_called=false`. Production apply remains T10. |
| **T07** | complete | Disposable PostgreSQL causal-integrity suite passed **15 tests**, including the new v2 forensics lineage case. |
| **T08** | complete locally | Exact source commit `bf634a7e2695e397adcc4a7107d4a48cb33ac98c` passed focused P0 **334**, causal PostgreSQL **15**, Dual-Position PostgreSQL **33**, Action-Time impact **84**, and complete isolated PostgreSQL **3626 passed, 1 skipped, 5 warnings**. Linux/amd64 CPython 3.10 installed the unchanged version/hash lock through a transient Tencent mirror index, imported the required modules, and returned `pip check: No broken requirements found`. Docs authority, output scope, diff, and file-I/O gates passed; `performance_risk.status=clear`. |
| **T09–T10** | not started by design | Tokyo deployment, production read-only acceptance, and production ghost closure require the later explicit deploy decision. |

All evidence above is local/disposable only. It does not change production state,
Owner policy, runtime profile, migration state, or exchange-write authority.

### 5.2 Exact-head certification record — 2026-07-18

| Gate | Result | Evidence boundary |
| --- | --- | --- |
| **Source commit** | `bf634a7e2695e397adcc4a7107d4a48cb33ac98c` | This is the certified code head; the following C08 commit is documentation-only. |
| **Focused and causal gates** | **334 + 15 + 33 + 84 passed** | P0 focused suite, P0 causal PostgreSQL suite, Dual-Position mandatory PostgreSQL gate, and Action-Time impact suite. |
| **Complete regression** | **3626 passed, 1 skipped, 5 warnings** | Isolated disposable PostgreSQL suite; no production database or exchange was contacted. |
| **Linux runtime lock** | **passed** | Clean Linux/amd64 CPython 3.10 container ran `pip install --require-hashes`, the required imports, and `pip check`. The repository lock was read-only and unchanged; only a temporary container copy substituted the download index with `https://mirrors.cloud.tencent.com/pypi/simple`, while all pinned versions and SHA-256 hashes remained enforced. |
| **Current-doc authority** | **passed** | `current_docs_authority_valid`. |
| **Runtime file-I/O and output scope** | **passed** | `suspicious_runtime_file_authority=0`, `frequent_report_write=0`, and `output_artifact_scope_valid`; `performance_risk.status=clear`. |
| **Diff integrity** | **passed** | `git diff --check` returned zero findings before the documentation-only C08 update. |

The exact-head local certification removes the branch-level test-certification
blocker only. It does **not** claim Tokyo observation recovery, close production
ghost rows, authorize a production exchange write, or replace
`DEPLOYMENT_NO_GO`. T09 remains the first deployment action.

Tasks are sequential where they share watcher/API/readmodel files. No parallel
writer may edit `api_trading_console.py`, `runtime_active_observation_monitor.py`,
or current projection files at the same time.

## 6. Task Cards

## T00 — Documentation And Certification Reopen

### Task ID

**P0-ROT-T00**

### Goal

Create the design and implementation plan and mark whole-branch deployment
certification as reopened.

### Why

The prior Dual-Position component certification did not cover the discovered
watcher compact, liveness, status, and forensics defect class.

### Allowed files

```text
docs/current/P0_RUNTIME_OBSERVATION_TRUTH_AND_FORENSICS_REMEDIATION_DESIGN.md
docs/current/P0_RUNTIME_OBSERVATION_TRUTH_AND_FORENSICS_REMEDIATION_IMPLEMENTATION_PLAN.md
docs/current/MAIN_CONTROL_ROADMAP.md
docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md
docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md
docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_IMPLEMENTATION_PLAN.md
```

### Forbidden files

All `src/**`, `scripts/**`, `tests/**`, migrations, deployment units, and
production state.

### Requirements

1. Preserve the prior component evidence.
2. Add the new P0 before any Dual-Position deployment decision.
3. State `LOCAL_REMEDIATION_CERTIFICATION_REOPENED` and `DEPLOYMENT_NO_GO`.
4. Preserve production unchanged and exchange write zero.

### Chain Position

`pretrade_candidate_readiness`

### Live Enablement State Before

Untracked design decision in chat and conflicting certification documents.

### Live Enablement State After

One current design and one current bounded implementation plan.

### Blocker Removed Or Reclassified

Reclassifies branch state from deploy-candidate ambiguity to explicit
`schema_invalid` remediation.

### Per-Symbol / Per-Fact Acceptance

The documents name all **22 lanes**, the **19 failed lanes**, and the SOR/BTC
structured blocker reproduction without changing runtime scope.

### Stop Condition

All current planning surfaces reference the same P0 and deployment no-go state.

### Capability Unlocked

`implementation_task_cards_ready`

### Next Engineering Bottleneck

Production-shaped RED tests.

### Rehearsal/Simulation Boundary

Documentation only; no runtime process.

### Tests

- Markdown link/path validation;
- `git diff --check`;
- document authority/status cross-check.

### Done When

The six allowed documents contain no contradictory branch-level deployment
state.

### Hard Stop

Any requested runtime or production mutation.

## T01 — Production-Shaped RED Fixtures

### Task ID

**P0-ROT-T01**

### Goal

Add failing tests that reproduce the exact production-shaped defect before
changing implementation.

### Why

The existing compact tests use `list[str]` and therefore prove a privileged
fixture rather than the real producer contract.

### Allowed files

```text
tests/unit/test_watcher_decision_fact_projection.py
tests/integration/test_watcher_action_time_compact_parity.py
tests/unit/test_runtime_active_observation_monitor.py
tests/unit/test_runtime_signal_forensics.py
tests/unit/test_runtime_signal_forensics_repository.py
tests/unit/test_runtime_signal_watcher_resume_dispatcher.py
tests/unit/test_strategy_live_candidate_pool.py
tests/unit/test_strategygroup_runtime_goal_status.py
tests/unit/test_strategygroup_tradeability_decision.py
tests/unit/test_tokyo_runtime_server_monitor.py
```

### Forbidden files

All implementation files, production DB, exchange adapters, and test fixtures
that inject downstream-ready authority not produced by the tested boundary.

### Requirements

Create RED cases for:

1. `NEXT-ATTEMPT-POSITION-ORDER-CONFLICT` as a structured blocker;
2. compact API route returning the current incorrect status;
3. HTTP 500/timeout observation incorrectly appearing covered/active;
4. no lane/Ticket incorrectly producing `waiting_for_market`;
5. Signal + Invocation + business-blocked Process Outcome + no Promotion;
6. historical coverage with one failed lane;
7. PG OPEN/exchange-flat ghost protection classification.

### Chain Position

`pretrade_candidate_readiness`

### Live Enablement State Before

Tests green while production-shaped blocker fails.

### Live Enablement State After

Deterministic RED coverage proves every demonstrated escape.

### Blocker Removed Or Reclassified

Reclassifies green-suite confidence as an explicit producer-consumer test gap.

### Per-Symbol / Per-Fact Acceptance

Include at least:

- `SOR-001 / BTCUSDT / long` structured position-order blocker;
- one computed-not-satisfied lane;
- one HTTP failure lane;
- one Invocation business-blocked signal;
- one ghost SL and one ghost TP1 role.

### Stop Condition

Every new test fails for the expected reason and not from fixture/schema setup.

### Capability Unlocked

`production_shape_regression_gate`

### Next Engineering Bottleneck

Typed compact blocker implementation.

### Rehearsal/Simulation Boundary

In-memory/SQLite or disposable PostgreSQL only; no network or exchange write.

### Tests

Only the new focused RED tests.

### Done When

Failure messages identify the exact current defects.

### Hard Stop

A test requires editing production rows or bypassing an official API boundary.

## T02 — Typed Compact Blocker And HTTP Semantics

### Task ID

**P0-ROT-T02**

### Goal

Make compact transport accept bounded typed blockers and return correct HTTP
status classes.

### Why

This removes the first production blocker: `schema_invalid` at watcher compact
projection.

### Allowed files

```text
src/application/readmodels/watcher_decision_fact_projection.py
src/interfaces/api_trading_console.py
scripts/runtime_active_observation_monitor.py
tests/unit/test_watcher_decision_fact_projection.py
tests/integration/test_watcher_action_time_compact_parity.py
tests/unit/test_canary_readonly_api.py
tests/unit/test_runtime_active_observation_monitor.py
```

### Forbidden files

Execution orchestrator, FinalGate, Operation Layer, exchange gateway, lifecycle
core, policy/profile files, and migrations.

### Requirements

1. Implement `WatcherCompactBlocker` as a named Pydantic model.
2. Normalize string and dict blocker inputs without `str(dict)`.
3. Preserve first blocker and typed stage/severity.
4. Keep warnings as bounded strings.
5. Return HTTP 200 for valid business-blocked observations.
6. Return 500 for compact projection defects, 503 for runtime dependency
   failure, 404 for missing runtime, and 400/422 only for client contract errors.
7. Keep response and cardinality limits from the design.
8. Mask sensitive detail.

### Chain Position

`pretrade_candidate_readiness`

### Live Enablement State Before

Structured blocker produces HTTP 400 and no valid observation result.

### Live Enablement State After

Structured blocker returns HTTP 200 with bounded typed decision truth.

### Blocker Removed Or Reclassified

Removes `schema_invalid`; exposes the next real business or runtime blocker.

### Per-Symbol / Per-Fact Acceptance

`SOR-001 / BTCUSDT / long` preserves
`NEXT-ATTEMPT-POSITION-ORDER-CONFLICT`, `pre_next_attempt`, and
`hard_blocker`. Computed-false lanes preserve exact failed fact codes.

### Stop Condition

Full and compact projections have equal watcher decision semantics and compact
payloads remain bounded.

### Capability Unlocked

`typed_watcher_compact_transport`

### Next Engineering Bottleneck

Actual observation-result-backed liveness.

### Rehearsal/Simulation Boundary

Non-executing observation API only; all safety flags remain false.

### Tests

- compact unit tests;
- API route status tests;
- full/compact integration parity;
- canary readonly contract tests.

### Done When

The original one-line reproduction no longer raises and the exact typed output
is asserted.

### Hard Stop

Any implementation change that coerces dicts to strings or removes blocker
identity to make the test pass.

## T03 — Observation-Result-Backed Coverage And Liveness

### Task ID

**P0-ROT-T03**

### Goal

Publish PG watcher liveness only after the actual observation API result is
known.

### Why

Scope attachment is not proof that the watcher executed successfully.

### Allowed files

```text
scripts/runtime_active_observation_monitor.py
src/infrastructure/runtime_control_state_repository.py
tests/unit/test_runtime_active_observation_monitor.py
tests/unit/test_strategy_live_candidate_pool.py
tests/unit/test_strategygroup_runtime_goal_status.py
tests/unit/test_strategygroup_tradeability_decision.py
```

### Forbidden files

New coverage tables, JSON/MD outputs as authority, FinalGate/Operation Layer,
exchange/lifecycle core, and migrations unless the design is amended.

### Requirements

1. Build one typed observation result per selected runtime.
2. Move/enrich coverage projection after API completion.
3. Keep `coverage_state` for scope and `liveness_state` for execution health.
4. Treat HTTP 200 business blockers and computed false facts as healthy.
5. Treat HTTP errors, invalid bodies, timeouts, and global deadline as failed or
   degraded.
6. Preserve immutable lane identity and exact runtime instance.
7. Write all lane rows in one bounded transaction.
8. Keep current cadence and zero JSON/MD write behavior.

### Chain Position

`pretrade_candidate_readiness`

### Live Enablement State Before

Selected scope can become covered/active before observation succeeds.

### Live Enablement State After

Every covered lane has explicit healthy/degraded/failed liveness from its
actual observation attempt.

### Blocker Removed Or Reclassified

Removes false healthy coverage and reclassifies technical failures as
`watcher_tick_missing` or precise runtime unavailability rather than market.

### Per-Symbol / Per-Fact Acceptance

For all 22 lanes:

- HTTP 200 + computed false -> covered/healthy;
- HTTP 200 + active-position blocker -> covered/healthy;
- HTTP 500 -> covered/failed;
- deadline -> covered/degraded/failed;
- identity missing -> not_covered/identity_missing.

### Stop Condition

No test can construct an HTTP/timeout failure and obtain healthy liveness.

### Capability Unlocked

`observation_result_backed_liveness`

### Next Engineering Bottleneck

Market-wait/current-projection ownership.

### Rehearsal/Simulation Boundary

Fake API client and disposable PG only; no production service mutation.

### Tests

- active monitor unit matrix;
- repository current-row selection;
- Candidate Pool and Goal Status liveness-negative tests.

### Done When

The production-shaped 19-failure/3-success fixture produces 19 failed and 3
healthy lane rows, never 22 healthy rows.

### Hard Stop

Extending fact TTL or timeout values to make missing observations look current.

## T04 — Current Projection And Resume Ownership

### Task ID

**P0-ROT-T04**

### Goal

Ensure only PG-backed readiness/Tradeability/Goal Status may declare validated
market wait.

### Why

The Resume Dispatcher knows execution identity, not market or watcher health.

### Allowed files

```text
scripts/runtime_signal_watcher_resume_dispatcher.py
src/application/readmodels/strategy_live_candidate_pool.py
src/application/readmodels/strategygroup_runtime_goal_status.py
src/application/readmodels/daily_live_enablement_table.py
scripts/build_strategygroup_tradeability_decision.py
scripts/run_tokyo_runtime_server_monitor.py
scripts/publish_runtime_control_current_projections.py
tests/unit/test_runtime_signal_watcher_resume_dispatcher.py
tests/unit/test_strategy_live_candidate_pool.py
tests/unit/test_strategygroup_runtime_goal_status.py
tests/unit/test_daily_live_enablement_table.py
tests/unit/test_strategygroup_tradeability_decision.py
tests/unit/test_tokyo_runtime_server_monitor.py
```

### Forbidden files

New Owner-state table, file-backed projections, frontend interpretation, and
execution core.

### Requirements

1. Replace no-lane/no-Ticket resume result with neutral
   `no_actionable_pg_ticket`.
2. Remove `waiting_for_market` and `waiting_for_opportunity` from that neutral
   dispatcher result.
3. Apply the design's blocker priority in current projections.
4. Require complete healthy coverage before `market_wait_validated`.
5. Preserve active-position/order resolution ahead of market wait.
6. Keep Owner action false for engineering/runtime repair unless an abnormal
   safety intervention is required.

### Chain Position

`tradeability_first_blocker`

### Live Enablement State Before

No open Ticket can be compressed to market wait despite unhealthy watcher.

### Live Enablement State After

Resume is identity-only; current projectors own market classification.

### Blocker Removed Or Reclassified

Removes false `waiting_for_market`; reclassifies to exact liveness, process, or
active-position blocker.

### Per-Symbol / Per-Fact Acceptance

One failed lane prevents strategy-level validated wait. A healthy 22-lane matrix
with computed false facts may produce validated wait.

### Stop Condition

Repository-wide tests prove no current Owner surface receives market wait solely
from absent lane/Ticket identity.

### Capability Unlocked

`single_owner_market_wait_projection`

### Next Engineering Bottleneck

Causal forensics and historical coverage proof.

### Rehearsal/Simulation Boundary

Projection-only tests; no Ticket or submit creation.

### Tests

Focused Resume, Candidate Pool, Tradeability, Daily Table, Goal Status, and
Server Monitor tests.

### Done When

The 19-failure/3-success state is `temporarily_unavailable`/developer attention,
not `waiting_for_opportunity`.

### Hard Stop

Adding a second Owner-state projector or making the dispatcher query/write
trading authority.

## T05 — Runtime Signal Forensics V2

### Task ID

**P0-ROT-T05**

### Goal

Explain every signal from its persisted Invocation and Process Outcome before
using missing downstream objects.

### Why

All 36 captured signals had Invocations, while the current reducer reported 34
generic promotion handoff gaps.

### Allowed files

```text
src/application/runtime_signal_forensics.py
src/infrastructure/runtime_signal_forensics_repository.py
scripts/ops/query_runtime_signal_forensics.py
.agents/skills/runtime-signal-forensics/SKILL.md
tests/unit/test_runtime_signal_forensics.py
tests/unit/test_runtime_signal_forensics_repository.py
tests/unit/test_query_runtime_signal_forensics.py
```

### Forbidden files

Production writes, signal/promotion mutation, JSON report output, policy,
FinalGate, Operation Layer, and exchange code.

### Requirements

1. Query ActionTimeInvocation, Runtime Process Outcome, and effective candidate
   scope rows.
2. Bind process outcomes by invocation identity first, then exact typed lane
   identity where needed.
3. Select the earliest causal blocker by stage, not by whichever object is
   missing first in the old reducer.
4. Replace stdout schema v1 with v2; no dual schema.
5. Add Invocation, Promotion, Lane, Ticket, process name/state identities to
   findings.
6. Prove historical coverage by interval and required lane set.
7. Keep the command read-only, stdout-only, time-window bounded, and limit
   bounded.
8. Update the repository skill so Owner explanations use v2 without exposing
   internal codes as primary language.

### Chain Position

`tradeability_first_blocker`

### Live Enablement State Before

Missing Promotion is classified without reading Invocation/process truth.

### Live Enablement State After

Signal findings preserve exact first blocker and full nearest lineage.

### Blocker Removed Or Reclassified

Reclassifies 33 signals to `active_position_clear`, one to
`build_account_safe_facts_failed`, and keeps true handoff gaps only when PG
lineage proves them.

### Per-Symbol / Per-Fact Acceptance

The captured SOR/BTC and CPM/SUI shapes retain strategy, symbol, side,
Invocation, process state, first blocker, and downstream IDs where present.

### Stop Condition

No finding reports `promotion_candidate_missing` when an earlier blocking
Invocation process outcome exists.

### Capability Unlocked

`causal_runtime_signal_forensics_v2`

### Next Engineering Bottleneck

Official production ghost-order closure and integrated certification.

### Rehearsal/Simulation Boundary

Read-only PG queries and in-memory reducer tests only.

### Tests

- reducer causal matrix;
- repository bounded/read-only tests;
- PostgreSQL relation tests;
- CLI schema and zero-file-write tests;
- skill wording/contract checks.

### Done When

The production 36-signal query shape yields the expected exact blocker
distribution.

### Hard Stop

Any forensics path attempts to repair, promote, create Tickets, or write files.

## T06 — Ghost-Order Official Closure Proof

### Task ID

**P0-ROT-T06**

### Goal

Prove and, after deployment authorization, execute the official closure path for
the five PG OPEN/exchange-absent protection rows.

### Why

After compact transport is fixed, these rows correctly become
`active_position_resolution` and may block eligible next attempts.

### Allowed files

Initial proof scope:

```text
scripts/run_ticket_bound_lifecycle_maintenance_once.py
scripts/ops/check_tokyo_runtime_ops_health_once.py
src/application/action_time/lifecycle_maintenance_scheduler.py
src/application/action_time/lifecycle_maintenance_service.py
src/application/action_time/protection_reconciler.py
src/application/action_time/orphan_protection_cleanup_command.py
tests/unit/test_ticket_bound_lifecycle_maintenance_service.py
tests/unit/test_ticket_bound_orphan_protection_cleanup_command.py
tests/unit/test_order_lifecycle_service_pending_updates.py
```

Conditional Codex-owned files, only if the official path is proven incomplete:

```text
src/application/reconciliation.py
src/application/order_lifecycle_service.py
src/application/startup_reconciliation_service.py
src/infrastructure/reconciliation_repository.py
```

### Forbidden files

Ad hoc SQL scripts, direct PG shell mutations, generic exchange cancellation,
strategy/policy/profile files, and any cleanup without Ticket/order identity.

### Requirements

1. Reproduce PG-open/exchange-flat classification in disposable PG.
2. Prove the official path terminalizes only PG ghost rows and writes audit
   truth.
3. Prove zero exchange cancel/write when the exchange order is absent.
4. Preserve Ticket, symbol, role, parent/child, and conditional-order lineage.
5. Handle SL and TP1 roles across BTC, ETH, AVAX, and SOL.
6. Keep ambiguous exchange truth fail-closed.
7. Separate code proof from later production apply.

### Chain Position

`tradeability_first_blocker`

### Live Enablement State Before

`active_position_resolution` from five PG ghost protection rows.

### Live Enablement State After

PG and exchange order/position truth agree, or one exact unresolved lifecycle
hard blocker remains.

### Blocker Removed Or Reclassified

Removes proven PG-only ghost protection residue without hiding real active
positions/orders.

### Per-Symbol / Per-Fact Acceptance

| Symbol | Required role coverage |
| --- | --- |
| BTCUSDT | SL |
| ETHUSDT | SL |
| AVAXUSDT | SL |
| SOLUSDT | SL and TP1 |

### Stop Condition

All five identities are deterministically terminalized in rehearsal with zero
exchange write, or the first missing official capability is named.

### Capability Unlocked

`official_pg_ghost_order_closure`

### Next Engineering Bottleneck

Cross-layer PostgreSQL certification.

### Rehearsal/Simulation Boundary

Disposable PG plus fake/read-only exchange snapshot. Production apply occurs
only in T10 after deploy acceptance.

### Tests

Lifecycle maintenance, reconciliation reducer, PG persistence, idempotency, and
zero-exchange-effect tests.

### Done When

Repeated closure is idempotent and does not create a new business event.

### Hard Stop

Exchange identity appears, protection may still be live, or cleanup requires
manual SQL.

## T07 — Cross-Layer PostgreSQL Certification

### Task ID

**P0-ROT-T07**

### Goal

Exercise the real producer-to-current-projection chain in disposable
PostgreSQL.

### Why

Unit tests alone allowed the original cross-layer contract mismatch to escape.

### Allowed files

```text
tests/integration/test_watcher_action_time_compact_parity.py
tests/integration/test_runtime_causal_integrity_postgres.py
tests/integration/test_runtime_observation_truth_postgres.py
tests/unit/test_l2_l7_mainline_chain_invariants.py
test support required by those tests
```

The new integration file may be added. It must use typed in-memory/fake HTTP
inputs and real disposable PostgreSQL, not JSON fixture files.

### Forbidden files

Production PG, exchange gateway writes, legacy report fixture files, and
privileged downstream state injection that skips the producer boundary.

### Requirements

Certify these matrices:

| Matrix | Cases |
| --- | --- |
| Compact blocker | string, structured business blocker, invalid object, oversize, truncation |
| API | 200 computed, 200 business blocked, 404, 500, 503, timeout |
| Coverage | healthy, failed, degraded, missing, identity mismatch |
| Projection | Candidate Pool, Tradeability, Goal Status, Daily Table, Monitor priority agreement |
| Forensics | no Invocation, business block, retryable failure, hard failure, success/no Promotion, downstream Ticket/lifecycle |
| Historical window | 22 healthy lanes, one failed lane, cadence gap, missing lane |
| Reconciliation | PG ghost SL/TP1, exchange-present ambiguity, repeated idempotent closure |

### Chain Position

`pretrade_candidate_readiness`

### Live Enablement State Before

Individual components pass without one producer-to-consumer proof.

### Live Enablement State After

One PostgreSQL test chain proves observation and causal explanation truth.

### Blocker Removed Or Reclassified

Removes the certification coverage gap.

### Per-Symbol / Per-Fact Acceptance

All **six Event Specs** and **22 lanes** appear in either positive execution or
identity/coverage impact cases; unsupported opposite sides remain rejected.

### Stop Condition

All matrix cases pass and no test writes exchange state or legacy files.

### Capability Unlocked

`postgres_observation_truth_certification`

### Next Engineering Bottleneck

Full branch re-certification.

### Rehearsal/Simulation Boundary

Disposable PostgreSQL and fake API/exchange only.

### Tests

The integration matrix plus affected current-projection unit suites.

### Done When

A single command can reproduce the complete P0 observation-truth gate.

### Hard Stop

Any test depends on production network, production PG, or current JSON/MD
artifacts.

## T08 — Full Branch Re-Certification

### Task ID

**P0-ROT-T08**

### Goal

Re-certify the complete current merge branch at one exact source commit.

### Why

The branch combines Dual-Position remediation with this P0 repair; neither may
be deployed from a different unverified head.

### Allowed files

Tests, validators, certification scripts, runtime lock, and docs status only.
Dependency versions/hashes may not change unless a separate dependency defect
is proven and approved.

### Forbidden files

Production mutation, policy activation, exchange write, and weakening/skipping
tests to obtain green status.

### Requirements

Run in this order:

1. focused P0-ROT unit and integration gates;
2. existing Dual-Position PostgreSQL no-skip gates;
3. affected consumer/current-projection matrix;
4. deployment state-machine and runtime-lock gates;
5. production runtime file-I/O audit;
6. complete repository regression in disposable PostgreSQL;
7. clean Linux/amd64 CPython 3.10 `--require-hashes` install/import/`pip check`;
8. exact-head documentation update.

The main controller must schedule/approve the long full-suite run after focused
gates are green.

### Chain Position

`pretrade_candidate_readiness`

### Live Enablement State Before

Implementation locally focused-green but whole-branch deployment no-go.

### Live Enablement State After

One locally certified, exact-head deployment candidate.

### Blocker Removed Or Reclassified

Removes branch-level certification reopening only if every gate passes.

### Per-Symbol / Per-Fact Acceptance

The 22-lane observation matrix and six Event Specs remain intact beside all
Dual-Position account-risk invariants.

### Stop Condition

One exact commit has green targeted, PostgreSQL, full-suite, Linux, deploy, and
file-I/O evidence.

### Capability Unlocked

`local_deployment_candidate_recertified`

### Next Engineering Bottleneck

Tokyo canary/deploy acceptance.

### Rehearsal/Simulation Boundary

Local/disposable environments only.

### Tests

All gates above; no xfail or new skip in P0-ROT/PG mandatory gates.

### Done When

Docs record exact commit, counts, migration head, hash-lock result, and
`performance_risk.status=clear`.

### Hard Stop

Any required gate fails, hangs beyond its bound, changes lock content, or
reports production file authority.

## T09 — Tokyo Canary, Deploy, And Read-Only Acceptance

### Task ID

**P0-ROT-T09**

### Goal

Deploy the exact locally certified head through the existing immutable Tokyo
release state machine and validate observation truth before normal cadence.

### Why

The defect is production-shaped and must be proven against the real backend,
systemd, PG schema, and active 22-lane scope.

### Allowed files

Existing Tokyo deploy planning/execution/verification scripts, systemd units if
implementation changed their contract, and acceptance docs.

### Forbidden files

Manual upload outside the deployment contract, ad hoc server edits, synthetic
production signals/Tickets, policy activation, profile expansion, and exchange
write during canary/read-only acceptance.

### Requirements

1. Verify exact local/remote commit and migration head.
2. Stop or isolate normal watcher cadence during canary.
3. Run one bounded canary observation cycle against all 22 lanes.
4. Confirm structured business blockers return HTTP 200.
5. Confirm technical failure, if injected only through test-local canary means,
   records failed liveness and no market wait.
6. Confirm no-signal tick creates zero JSON/MD files.
7. Confirm PG coverage, current projections, Server Monitor, and forensics agree.
8. Confirm FinalGate, Operation Layer, exchange write, order creation, policy,
   profile, and sizing effects remain zero.
9. Restore the normal timer only after canary acceptance.

### Chain Position

`pretrade_candidate_readiness`

### Live Enablement State Before

Locally certified but not deployed.

### Live Enablement State After

Tokyo watcher has valid observation truth for all current lanes.

### Blocker Removed Or Reclassified

Removes environment/deploy uncertainty; per-lane business blockers may remain.

### Per-Symbol / Per-Fact Acceptance

All 22 active lanes return one actual result. The three historically healthy
lanes and nineteen historically failing lanes are re-evaluated rather than
assumed.

### Stop Condition

Backend, watcher, monitor, lifecycle, timer, PG current rows, and forensics are
healthy at the exact deployed head.

### Capability Unlocked

`tokyo_observation_truth_accepted`

### Next Engineering Bottleneck

Official production ghost-order closure and post-cleanup recheck.

### Rehearsal/Simulation Boundary

Canary/read-only observation has no exchange-write authority. Normal official
submit remains governed by existing policy and action-time gates after timer
restoration.

### Tests

Deploy preflight, canary, postdeploy verifier, PG read-only queries, journal,
systemd, and file-I/O audit.

### Done When

Tokyo evidence proves no false healthy coverage and no false market wait.

### Hard Stop

Commit/schema mismatch, mixed-generation service, unknown exchange outcome,
unprotected position, active exchange order ambiguity, or any forbidden effect.

## T10 — Production Reconciliation Closure And Acceptance

### Task ID

**P0-ROT-T10**

### Goal

Close the known five PG ghost orders through the deployed official path and
publish final current truth.

### Why

After observation is repaired, stale PG orders become the correct next blocker
for affected lanes.

### Allowed operations

- read-only exchange and PG identity checks;
- official lifecycle/reconciliation maintenance against exact Ticket/order
  identities;
- PG writes produced by that official path;
- current projection refresh;
- final documentation updates.

### Forbidden operations

- manual SQL update/delete;
- generic exchange cancel;
- scope/profile/policy change;
- new order or submit attempt;
- credential mutation, withdrawal, or transfer.

### Requirements

1. Re-query the five expected identities immediately before apply.
2. Abort if exchange truth differs from the accepted flat/absent proof.
3. Run the official closure path once per exact lifecycle/Ticket scope.
4. Re-run idempotently and prove zero duplicate event/effect.
5. Refresh Candidate Pool, Tradeability, Goal Status, Server Monitor, and
   forensics.
6. Record remaining first blocker per affected lane.
7. Update roadmap/program/design/plan status to the exact deployed result.

### Chain Position

`tradeability_first_blocker`

### Live Enablement State Before

Observation truth accepted; five PG ghost rows may still block next attempts.

### Live Enablement State After

PG/exchange order truth agrees and each lane exposes its next genuine blocker.

### Blocker Removed Or Reclassified

Removes `active_position_resolution` only for proven PG-only ghost rows.

### Per-Symbol / Per-Fact Acceptance

BTC, ETH, AVAX, and SOL SL/TP1 identities are all reconciled and no unrelated
position/order is changed.

### Stop Condition

Five expected ghost rows are terminal/closed through official lineage, exchange
remains unchanged, and current projections no longer cite them.

### Capability Unlocked

`production_observation_and_order_truth_closed`

### Next Engineering Bottleneck

Per-lane computed market facts, a future fresh signal, or another exact
engineering/safety blocker revealed by the repaired chain.

### Rehearsal/Simulation Boundary

Production mutation is limited to official reconciliation PG state for rows
already proven absent at the exchange. No exchange write is expected or allowed.

### Tests

Pre/post PG hashes, exchange read-only snapshot, official command result,
idempotent second pass, current projection refresh, and journal review.

### Done When

Final documents carry the deployed commit, migration head, 22-lane acceptance,
forensics distribution, ghost-order outcome, and authority boundary.

### Hard Stop

Any exchange order/position appears, identity is ambiguous, official closure
would issue an exchange command, or the affected scope has an unprotected or
unknown lifecycle.

## 7. Test Commands And Gate Families

Exact commands may be adjusted to repository conventions during execution, but
the gate families are fixed.

### 7.1 Focused unit and integration

```text
tests/unit/test_watcher_decision_fact_projection.py
tests/integration/test_watcher_action_time_compact_parity.py
tests/unit/test_runtime_active_observation_monitor.py
tests/unit/test_runtime_signal_watcher_resume_dispatcher.py
tests/unit/test_runtime_signal_forensics.py
tests/unit/test_runtime_signal_forensics_repository.py
tests/unit/test_query_runtime_signal_forensics.py
tests/unit/test_strategy_live_candidate_pool.py
tests/unit/test_strategygroup_runtime_goal_status.py
tests/unit/test_strategygroup_tradeability_decision.py
tests/unit/test_daily_live_enablement_table.py
tests/unit/test_tokyo_runtime_server_monitor.py
tests/unit/test_ticket_bound_lifecycle_maintenance_service.py
```

### 7.2 PostgreSQL mandatory gate

The gate must fail if PostgreSQL is unavailable and must not skip P0-ROT cases.
It includes the existing Dual-Position mandatory PostgreSQL tests and the new
observation-truth integration matrix.

### 7.3 Negative constraints

Tests must prove rejection or non-authority for:

- arbitrary compact blocker objects;
- dict-to-string compatibility;
- HTTP 500 represented as healthy coverage;
- absent Ticket represented as market wait without coverage proof;
- missing Promotion overriding Invocation Process Outcome;
- historical coverage proof from only the latest current row;
- manual/file-backed forensics input;
- ghost-order cleanup without exact identity;
- exchange write from watcher, monitor, forensics, or PG-ghost closure;
- new recurring JSON/MD output.

### 7.4 Performance and file-I/O gate

Run:

```text
python3 scripts/audit_production_runtime_file_io.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
```

Acceptance requires:

```text
performance_risk.status=clear
frequent_report_write=0
no-signal JSON/MD files=0
```

## 8. Commit And Review Boundaries

Recommended bounded commit sequence:

| Commit | Content |
| --- | --- |
| **C00** | design, plan, roadmap, certification reopen |
| **C01** | RED tests only |
| **C02** | typed compact blocker and API semantics |
| **C03** | observation result and PG liveness |
| **C04** | market-wait/Resume/current projection ownership |
| **C05** | forensics v2 and repository/skill update |
| **C06** | ghost-order official closure proof or bounded core repair |
| **C07** | PostgreSQL cross-layer certification |
| **C08** | exact-head recertification docs |

Every implementation commit must be reviewable and must not combine unrelated
Dual-Position policy changes.

## 9. Rollback Plan

### 9.1 Local

Revert the bounded P0-ROT commits in reverse order while deployment remains
disabled. Preserve the design documents and failure evidence.

### 9.2 Tokyo

Use the immutable-release state machine to return to the previous exact release,
pause watcher cadence if the old release would publish false health, and keep
trading progression fail-closed. Never restore JSON/file authority.

### 9.3 Production PG reconciliation

Do not reverse official reconciliation with manual SQL. If a terminalization is
later contradicted by exchange evidence, create a new audited recovery incident
and stop the affected scope.

## 10. Final Done Definition

The program is complete only when:

1. current branch code implements the design;
2. **22/22** lanes have result-backed liveness;
3. structured business blockers return HTTP 200;
4. internal projection failures return HTTP 500 and fail liveness;
5. all current projections agree on first blocker;
6. Resume Dispatcher no longer declares market wait;
7. forensics v2 reads Invocation and Process Outcome and reproduces the known
   33/1 missing-promotion blocker distribution;
8. the five PG ghost orders are officially closed or remain one exact unresolved
   safety blocker;
9. targeted, PostgreSQL, complete regression, Linux/amd64 lock, deployment, and
   file-I/O gates pass at one exact commit;
10. Tokyo canary and read-only acceptance pass with zero forbidden effects;
11. final docs replace `DEPLOYMENT_NO_GO` only with evidence from that exact
    deployed source commit.

## 11. Chain Position

```text
chain_position: pretrade_candidate_readiness
strategy_group_id: SOR-001
symbol: BTCUSDT
stage: local_exact_head_certified_awaiting_tokyo_canary
first_blocker: deployment_not_started
evidence: exact code head bf634a7e2695e397adcc4a7107d4a48cb33ac98c passed local watcher, PostgreSQL, full-regression, Linux hash-lock, docs, and file-I/O certification; Tokyo remains at its prior release and has not observed this code
next_action: execute P0-ROT-T09 through the immutable Tokyo deployment state machine, then perform read-only 22-lane observation acceptance
stop_condition: Tokyo canary observes all active lanes with result-backed liveness and no forbidden production effect; T10 then applies only official Ticket-bound ghost closure where exact proof exists
owner_action_required: false
signal_event_id: none
promotion_candidate_id: none
action_time_lane_input_id: none
ticket_id: none
authority_boundary: implementation remains inside official non-executing observation, PG current projection, read-only forensics, and ticket-bound reconciliation boundaries; no FinalGate bypass, Operation Layer bypass, policy expansion, or unauthorized exchange write
```
