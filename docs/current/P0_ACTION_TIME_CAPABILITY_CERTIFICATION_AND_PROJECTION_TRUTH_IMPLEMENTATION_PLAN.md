---
title: P0_ACTION_TIME_CAPABILITY_CERTIFICATION_AND_PROJECTION_TRUTH_IMPLEMENTATION_PLAN
status: APPROVED_FOR_IMPLEMENTATION
authority: docs/current/P0_ACTION_TIME_CAPABILITY_CERTIFICATION_AND_PROJECTION_TRUTH_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-12
---

# P0 Action-Time Capability Certification And Projection Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind the production-shaped Action-Time capability to the deployed release and current PG lane identity, then make all current projections conserve one first blocker.

**Architecture:** Reuse `brc_runtime_process_outcomes` for one release-bound certification row per lane. One pure application reducer computes identity/currentness and is consumed by Candidate Pool, Tradeability, Daily Table, Goal Status, projection publishing, and Server Monitor.

**Tech Stack:** Python 3.10+, Pydantic v2, `decimal.Decimal`, SQLAlchemy 2, PostgreSQL, pytest.

## Global Constraints

- PG/current is production truth; no JSON/MD/output/report authority.
- No new table, strategy semantics, Owner policy, runtime scope, sizing, leverage, FinalGate, Operation Layer, or exchange-write authority.
- Certification is deploy/version cadence only and upserts at most 22 bounded process-outcome rows.
- A stale head or lineage fails closed to `action_time_boundary_not_reproduced`.
- Every behavior change follows RED -> GREEN -> REFACTOR.

### Task 1: Typed Capability Identity And Currentness Reducer

**Files:**
- Create: `src/application/action_time/capability_certification.py`
- Create: `tests/unit/test_action_time_capability_certification.py`

**Interfaces:**
- Produces: `ActionTimeCapabilityIdentity`, `ActionTimeCapabilityTruth`, `build_action_time_capability_identities(...)`, and `current_action_time_capability_truth_by_lane(...)`.
- Consumes: PG/current registry, EventSpec, RequiredFacts, candidate scope, runtime binding, Owner policy, process outcomes, and current runtime head.

- [ ] Write failing tests for 22 identities, stable lineage hash, matching certification, missing certification, head drift, lineage drift, and incomplete identity.
- [ ] Run the focused test and verify RED for the missing module.
- [ ] Implement deterministic typed identity and currentness reduction with no I/O.
- [ ] Run focused tests and verify GREEN.

### Task 2: Transactional PG Certification Command

**Files:**
- Modify: `src/application/action_time/capability_certification.py`
- Create: `scripts/certify_action_time_capability.py`
- Create: `tests/unit/test_certify_action_time_capability.py`

**Interfaces:**
- Produces: one `action_time_capability_certification` process outcome per active lane.
- Requires: exact `runtime_head`, non-empty `certification_ref`, and complete current identities.

- [ ] Write failing tests proving 22 bounded upserts, exact runtime head/watermark, atomic rollback, and forbidden-effect flags.
- [ ] Verify RED.
- [ ] Implement one transaction-bounded PG command using `materialize_runtime_process_outcome(...)`.
- [ ] Prove the command creates no signal, promotion, lane, Ticket, Runtime Safety State, exchange command, order, profile, sizing, or policy mutation.
- [ ] Verify GREEN and idempotent recertification.

### Task 3: Candidate Pool And Tradeability Consume Shared Truth

**Files:**
- Modify: `src/application/readmodels/strategy_live_candidate_pool.py`
- Modify: `scripts/build_strategygroup_tradeability_decision.py`
- Test: `tests/unit/test_strategy_live_candidate_pool.py`
- Test: `tests/unit/test_strategygroup_tradeability_decision.py`

**Interfaces:**
- Candidate rows expose `action_time_capability` and use its blocker before `market_wait_validated`.
- Tradeability removes its private capability inference and consumes the same reducer.

- [ ] Write failing tests for matching, missing, stale-head, and lineage-drift certifications.
- [ ] Verify current code incorrectly permits or rejects market wait.
- [ ] Integrate the shared reducer and preserve per-lane evidence/next action.
- [ ] Verify both projections return the same first blocker.

### Task 4: Daily Table, Goal Status, And Publisher Conservation

**Files:**
- Modify: `src/application/readmodels/daily_live_enablement_table.py`
- Modify: `src/application/readmodels/strategygroup_runtime_goal_status.py`
- Modify: `scripts/publish_runtime_control_current_projections.py`
- Test: `tests/unit/test_daily_live_enablement_table.py`
- Test: `tests/unit/test_strategygroup_runtime_goal_status.py`
- Test: `tests/unit/test_runtime_control_current_projection_publish.py`

**Interfaces:**
- Daily Table separates current event readiness from certified deployed capability.
- Goal Status retains canonical non-market blockers.
- Publisher rejects cross-projection blocker disagreement before persistence.

- [ ] Write failing projection-consistency and no-signal tests.
- [ ] Verify RED against current conflicting behavior.
- [ ] Implement shared blocker conservation and pre-persistence consistency validation.
- [ ] Verify `market_wait_validated` only when certification is current.

### Task 5: Server Monitor And Deploy Gate

**Files:**
- Modify: `scripts/run_tokyo_runtime_server_monitor.py`
- Modify: `scripts/plan_tokyo_runtime_governance_git_deploy.py`
- Test: `tests/unit/test_tokyo_runtime_server_monitor.py`
- Test: `tests/unit/test_tokyo_lifecycle_phase_two_deploy.py`

**Interfaces:**
- Server Monitor classifies stale/missing certification as engineering progress, not service failure or market wait.
- Deploy acceptance runs the production-shaped matrix, certifies the exact head, republishes current projections, and performs readonly postdeploy checks.

- [ ] Write failing monitor/deploy sequencing tests.
- [ ] Verify RED.
- [ ] Add the bounded certification step after release switch and before final projection acceptance.
- [ ] Verify no exchange write and no heavy work in watcher cadence.

### Task 6: Regression, Deploy, And PG Acceptance

**Files:**
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Modify: this design and plan with final evidence.

- [ ] Run capability, Candidate Pool, Tradeability, Daily, Goal, publisher, monitor, and 22-scope production-shaped tests.
- [ ] Run the full suite.
- [ ] Run current-doc, output-scope, runtime-file-authority, production file-I/O, and diff validators.
- [ ] Commit and push the exact focused branch.
- [ ] Deploy through the bounded git-export path without exchange write.
- [ ] Certify all 22 lanes for the exact deployed head and republish PG/current projections.
- [ ] Verify projection consistency, timers, zero synthetic execution rows, and zero exchange writes.

## Done When

The deployed head has 22 current lane capability certifications; all six
EventSpecs retain production-shaped disabled-smoke coverage; Candidate Pool,
Tradeability, Daily Table, Goal Status, and Server Monitor agree on one first
blocker; market wait cannot be claimed with stale/missing certification; all
tests and validators pass; and only a natural Live event remains for venue
outcome calibration.
