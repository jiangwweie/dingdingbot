---
title: P1_TRADE_FEEDBACK_CORE_CONSOLIDATION_IMPLEMENTATION_PLAN
status: CURRENT_IMPLEMENTATION_PLAN
authority: docs/current/P1_TRADE_FEEDBACK_CORE_CONSOLIDATION_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-12
---

# P1 Trade Feedback Core Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace duplicate post-Ticket lifecycle interpretation with one typed reducer consumed by production callers, production-shaped rehearsal, replay-shaped tests, and Tokyo Owner feedback without changing PG schema or trading authority.

**Architecture:** Extend the existing pure `lifecycle_safety_core.py` into the single lifecycle decision model. Existing mutation services retain their PG and durable-command responsibilities but obtain status/event/recovery/Owner interpretation from the reducer. The deployed migration-114 vocabulary remains the compatibility output for this phase.

**Tech Stack:** Python 3.14, frozen dataclasses and string enums, SQLAlchemy, PostgreSQL/SQLite-compatible tests, pytest.

## Global Constraints

- PG/current services remain the only runtime truth; no JSON/Markdown runtime input or recurring output.
- No FinalGate, Operation Layer, exchange gateway, runtime profile, strategy parameter, sizing, credential, withdrawal, or transfer changes.
- No production code is written before its failing test is observed.
- No new exchange read/write call, no new recurring PG row, and no no-signal file output.
- Existing 31-value migration-114 lifecycle vocabulary remains the persisted compatibility contract.
- A different-identity natural fresh signal interrupts engineering at the next committed transaction boundary for live acceptance.

---

### Task 1: Typed Lifecycle Decision Model

**Files:**
- Modify: `src/application/action_time/lifecycle_safety_core.py`
- Create: `tests/unit/test_ticket_bound_lifecycle_decision_reducer.py`

**Interfaces:**
- Produces: `LifecyclePhase`, `ProtectionState`, `ReconciliationState`, `LifecycleControlState`, `OwnerLifecycleState`, `LifecycleDecision`, `lifecycle_decision_for_status(...)`, and `reduce_lifecycle_decision(...)`.
- Preserves: `.status`, `.event_type`, `.next_action`, `.first_blocker`, and `.blockers` on existing classification results.

- [x] Write parameterized failing tests covering all 31 migration-114 statuses and exact typed projections for normal, recovery, unknown-outcome, and terminal states.
- [x] Run `python3 -m pytest -q tests/unit/test_ticket_bound_lifecycle_decision_reducer.py` and verify import/API failures.
- [x] Implement string enums, the frozen decision model, the complete status specification map, fail-closed unknown mapping, and compatibility properties.
- [x] Add failing tests for `lifecycle_closed` regression, hard-stop-without-blocker normalization, explicit next-action override, and Owner-required derivation.
- [x] Implement `reduce_lifecycle_decision` with terminal monotonicity and blocker invariants.
- [x] Run the reducer tests and the existing protection/submit/runner classifier tests until green.

### Task 2: Reconciliation And Recovery Consumers

**Files:**
- Modify: `src/application/action_time/protection_reconciler.py`
- Modify: `src/application/action_time/protection_recovery_command.py`
- Modify: `tests/unit/test_ticket_bound_protection_reconciler.py`
- Modify: `tests/unit/test_ticket_bound_protection_recovery_command.py`

**Interfaces:**
- Consumes: `reduce_lifecycle_decision(...)`.
- Produces: existing PG rows and result payloads with unchanged compatibility status plus typed `lifecycle_decision` diagnostic payloads.

- [x] Add failing tests proving reconciler and recovery status, event, next action, phase, protection, reconciliation, and control state come from the common reducer.
- [x] Run the two focused test files and verify failures identify missing reducer consumption.
- [x] Replace reconciler-local event/next-action mapping and recovery-local failed/partial status mapping with reducer decisions.
- [x] Preserve existing netting holds, scope freezes, retry limits, durable commands, and exchange-call counts.
- [x] Run focused tests until green.

### Task 3: Runner, Fill, And Finalizer Consumers

**Files:**
- Modify: `src/application/action_time/runner_mutation_command.py`
- Modify: `src/application/action_time/ticket_bound_fill_projector.py`
- Modify: `src/application/action_time/ticket_bound_lifecycle_finalizer.py`
- Modify: `tests/unit/test_ticket_bound_runner_mutation_command.py`
- Modify: `tests/unit/test_ticket_bound_runner_mutation_executor.py`
- Modify: `tests/unit/test_ticket_bound_lifecycle_finalizer.py`
- Modify: `tests/unit/test_ticket_bound_production_lifecycle_certification.py`

**Interfaces:**
- Consumes: `reduce_lifecycle_decision(...)`.
- Produces: current lifecycle rows/events and typed decision diagnostics without a second side-effect path.

- [x] Add failing tests for Runner pending/failure, final-exit detection, reconciliation matched, budget settled, review recorded, and lifecycle closed decisions.
- [x] Run focused tests and verify reducer-consumption failures.
- [x] Route normal and abnormal transitions through the reducer while retaining existing PG writers and durable command ordering.
- [x] Add source assertions that the migrated modules no longer own duplicate lifecycle event/recovery lookup maps.
- [x] Run focused tests until green.

### Task 4: Rehearsal And Replay Decision Parity

**Files:**
- Modify: `src/application/action_time/full_chain_simulation_harness.py`
- Modify: `tests/unit/test_ticket_bound_production_lifecycle_certification.py`
- Modify: `tests/unit/test_action_time_full_chain_impact.py`

**Interfaces:**
- Consumes: persisted lifecycle rows through `lifecycle_decision_for_status(...)`.
- Produces: `lifecycle_decision` in success/failure simulation payloads; no new authority.

- [x] Add failing tests asserting the successful golden path projects `closed/completed` and failure scenarios project the same typed decision as direct reducer replay.
- [x] Run the focused certification tests and observe missing projection failures.
- [x] Add reducer projection to simulation results without writing PG or changing exchange mocks.
- [x] Run golden-path, nine failure-scenario, six-Event-Spec, and 22-scope impact tests until green.

### Task 5: Owner Feedback In Standard Ops Path

**Files:**
- Modify: `src/application/readmodels/owner_projection.py`
- Modify: `scripts/ops/check_tokyo_runtime_ops_health_once.py`
- Create: `tests/unit/test_ticket_bound_lifecycle_owner_projection.py`
- Modify: `tests/unit/test_runtime_ops_scripts.py`
- Modify: `tests/unit/test_tokyo_runtime_ops_health_lifecycle.py`

**Interfaces:**
- Consumes: `LifecycleDecision` or a migration-114 lifecycle row.
- Produces: one non-authority `lifecycle_owner_feedback` object in the existing Tokyo L2-L7 summary.

- [x] Add failing tests for processing, automatic recovery, temporary unavailability, Owner-required, completed, and unknown lifecycle feedback.
- [x] Run Owner/Ops focused tests and observe missing projection failures.
- [x] Implement the pure Owner projection and compose it from at most the existing 20 attention rows.
- [x] Prove the projection never reports submit authority, never mutates PG, and creates no file output.
- [x] Run Owner/Ops focused tests until green.

### Task 6: Planning, Regression, And Completion Audit

**Files:**
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Modify: `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md`
- Modify: `docs/current/strategy-group-handoffs/main-control-handoff-index.md`
- Modify: `docs/current/P1_TRADE_FEEDBACK_CORE_CONSOLIDATION_DESIGN.md`
- Modify: `docs/current/P1_TRADE_FEEDBACK_CORE_CONSOLIDATION_IMPLEMENTATION_PLAN.md`

**Interfaces:**
- Consumes: verified code/test/runtime evidence.
- Produces: one current project order and one current chain-position statement.

- [x] Update the roadmap to mark P0-LC deployed, define `Live Candidate Baseline`, make P1-TFC the sole medium-scale mainline, and retain natural fresh signal as the P0 interrupt.
- [x] Run targeted lifecycle, Owner, Ops, six-event, and 22-scope tests.
- [ ] Run the full pytest suite authorized by the accepted goal.
- [ ] Run `python3 scripts/validate_current_docs_authority.py`, `python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked`, `python3 scripts/audit_production_runtime_file_io.py`, and `git diff --check`.
- [ ] Review `git diff`, map every design requirement to fresh evidence, and record exact tests run and skipped.
- [ ] Mark every completed checkbox only after its command evidence exists; leave market-only R1B calibration explicitly open.
