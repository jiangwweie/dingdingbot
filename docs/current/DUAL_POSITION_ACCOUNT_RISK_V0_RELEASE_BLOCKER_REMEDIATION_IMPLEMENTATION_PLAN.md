---
title: DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_IMPLEMENTATION_PLAN
status: LOCAL_MERGE_CERTIFIED_NOT_DEPLOYED
authority: docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_IMPLEMENTATION_PLAN.md
implements: docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md
last_verified: 2026-07-17
deployment_state: LOCAL_ONLY_NO_DEPLOY
integration_state: LOCAL_MERGE_CERTIFIED_NOT_DEPLOYED
production_state: UNCHANGED
policy_activation: NOT_PERFORMED
exchange_write: 0
migration_head: 133_LOCAL_ONLY
---

# Dual-Position Account Risk V0 Release-Blocker Remediation Implementation Plan

> **For agentic workers:** Execute inline in the existing isolated worktree. Repository policy prohibits subagent implementation. Every production change follows a failing targeted test, minimal fix, and immediate targeted regression.

**Goal:** Close the account-risk release blockers so an account-capacity-adjusted Action-Time Ticket has conserved risk, policy authorization, protection coverage, margin, and PG concurrency semantics.

**Architecture:** Keep Ticket as the sole trade lifecycle owner and PG current projections as runtime truth. Extend the existing budget reservation into the persisted Account Capacity Claim; do not add a second risk engine, runtime file authority, or live execution path.

**Tech Stack:** Python 3, Pydantic, `Decimal`, SQLAlchemy, Alembic, PostgreSQL, pytest.

## Global Constraints

- Financial values use `Decimal`; no float arithmetic is introduced.
- Runtime state remains PG/current authority; no JSON, Markdown, YAML, JSONL, or local-file fallback is added.
- No exchange write, production migration apply, policy activation, deployment, or StrategyGroup scope change is part of this plan.
- Full-account exchange I/O stays outside the PG capacity lock.
- Existing positions remain protected, reconciled, exited, and settled during policy rollback; only new entry claims are invalidated.
- The full suite is run only after targeted unit and PostgreSQL integration gates are green.

---

### Task 1: Risk Vocabulary And Ticket-Valid Capacity Sizing

**Files:**
- Modify: `src/application/action_time/account_capacity_reservation.py`
- Modify: `tests/unit/test_account_capacity_reservation.py`
- Modify: `tests/unit/test_action_time_ticket_materialization.py`

**Interfaces:**
- Consumes: `ExecutionSizingDecision`, `AccountCapacityReservationResult`.
- Produces: a capacity-adjusted sizing decision where `planned_stop_risk_budget` is the ceiling, `planned_stop_risk` is actual rounded stop risk, and the existing stop-distance reservation basis remains valid.

- [ ] Write a failing unit test using entry `150`, stop `147.13`, capacity quantity `5.22`, and risk ceiling `15`; assert actual risk is `14.9814`, not `15`.
- [ ] Run `python3 -m pytest -q tests/unit/test_account_capacity_reservation.py -k rounded` and verify it fails because the current adapter copies allocated risk.
- [ ] Change `apply_account_capacity_to_sizing` to calculate `abs(entry_reference_price - protective_stop_price) * intended_qty`, retain the base valid `risk_reservation_basis`, and reject a capacity result whose actual risk exceeds its allocated ceiling.
- [ ] Run the same unit test and verify it passes.
- [ ] Write a failing Ticket-materialization test that feeds the capacity-adjusted valid basis through `sizing_risk_decision_from_budget` and asserts no `risk_reservation_basis_missing_or_invalid` blocker.
- [ ] Run the focused Ticket test, implement only any required shared basis handling, and rerun it green.

### Task 2: Immutable Policy Event Binding And FinalGate Invalidation

**Files:**
- Create: `migrations/versions/2026-07-17-130_add_account_capacity_claim_policy_event.py`
- Modify: `src/application/action_time/account_risk_policy.py`
- Modify: `src/application/action_time/account_capacity_reservation.py`
- Modify: `src/application/action_time/finalgate_preflight.py`
- Modify: `scripts/ops/set_account_risk_policy.py`
- Modify: `tests/unit/test_account_risk_policy.py`
- Modify: `tests/unit/test_account_capacity_finalgate_guard.py`

**Interfaces:**
- Consumes: current policy `source_event_id`, active reservation, Action-Time budget.
- Produces: `account_risk_policy_event_id` stored on every account-capacity claim and compared at FinalGate.

- [ ] Write a failing policy test that issues activate then rollback under the same semantic version and asserts distinct immutable event IDs and two event rows.
- [ ] Run `python3 -m pytest -q tests/unit/test_account_risk_policy.py -k event` and verify deterministic overwrite behavior fails the new assertion.
- [ ] Add migration 125 with nullable upgrade columns `account_risk_policy_event_id`, `allowed_risk_budget`, and `margin_accounting_state`; add an active-claim scope index including policy event identity.
- [ ] Change policy append to accept an explicit operation ID, create a unique immutable event per operation, and reject overwrite of an existing event ID with different contents.
- [ ] Add `--operation-id` to the policy script; default to a generated UUID only once per invocation and include the resulting event ID in its JSON response.
- [ ] Bind the current policy event ID into the capacity result/reservation; extend FinalGate to reject a claim whose event ID differs from current policy `source_event_id`.
- [ ] Run policy and FinalGate focused tests green.

### Task 3: Conservative Protection Segments And Current Ownership Scope

**Files:**
- Modify: `src/infrastructure/binance_usdm_account_risk_snapshot.py`
- Modify: `src/application/action_time/account_exchange_ownership.py`
- Modify: `src/application/action_time/account_exposure_current.py`
- Modify: `tests/unit/test_account_exposure_current.py`
- Modify: `tests/unit/test_account_exchange_ownership.py`

**Interfaces:**
- Consumes: typed open-order side, position-side, reduce-only, quantity, and trigger facts plus nonterminal Ticket identity.
- Produces: conservative per-quantity protection risk and current-only position ownership.

- [ ] Write a failing exposure test for a long `1 @ 100` with `0.5 @ 90` and `0.5 @ 105` stops; assert held directional risk is `5`, not `0`.
- [ ] Run `python3 -m pytest -q tests/unit/test_account_exposure_current.py -k multiple_stop` and verify the first-stop collapse fails the assertion.
- [ ] Extend normalized order facts with order side and close-position semantics; classify eligible stop orders only when they are opposite-side, correct position-side, live, owned, and reduce-only/close-position protective orders.
- [ ] Implement worst-loss-first capped quantity allocation and mark uncovered or ambiguous quantity as protection-missing fail-closed exposure.
- [ ] Write a failing ownership test with two closed Tickets that historically traded the same instrument and one current Ticket; assert only the current Ticket claims it.
- [ ] Run the focused ownership test, centralize nonterminal Ticket filtering, scope identity evidence by account/exchange, and remove symbol-fabricated instrument fallback from current ownership paths.
- [ ] Run both focused test files green.

### Task 4: Lock-First Claim Materialization And Margin Conservation

**Files:**
- Modify: `src/application/action_time/account_capacity_materialization.py`
- Modify: `src/application/action_time/account_capacity_reservation.py`
- Modify: `src/application/action_time/account_budget_current.py`
- Modify: `src/application/action_time/account_exposure_current.py`
- Modify: `tests/integration/test_account_capacity_postgres.py`
- Modify: `tests/unit/test_account_budget_current.py`

**Interfaces:**
- Consumes: prefetched `FullAccountRiskSnapshot`, locked current budget row, active reservation claims.
- Produces: lock-first capacity arbitration with `reserved_unreflected`, `exchange_reflected`, `unknown`, and `released` margin states.

- [ ] Write a failing PostgreSQL integration test that starts two full materialization transactions, commits the first, and asserts the second recomputes from the first claim rather than overwriting its pre-lock projection.
- [ ] Run `python3 -m pytest -q tests/integration/test_account_capacity_postgres.py -k full_materialization` and verify the current pre-lock budget write fails the assertion.
- [ ] Refactor materialization so it first locks the existing account-budget row, then reprojects, computes, reserves, and returns the claim without exchange I/O under the lock.
- [ ] Write a failing budget test with an active `reserved_unreflected` claim of margin `100`; assert `unreflected_pending_margin == 100` and available margin capacity decreases by `100`.
- [ ] Run `python3 -m pytest -q tests/unit/test_account_budget_current.py -k unreflected` and verify the current zero projection fails.
- [ ] Add margin-state-aware aggregation, preserve no-double-count behavior after exchange reflection, and fail closed for `unknown` reflection state.
- [ ] Run the focused PostgreSQL and budget suites green.

### Task 5: Claim-to-Ticket Chain Certification And Release Evidence

**Files:**
- Modify: `src/application/action_time/action_time_ticket.py`
- Modify: `tests/unit/test_action_time_ticket_materialization_sequence.py`
- Modify: `tests/unit/test_dual_position_account_risk_release_acceptance.py`
- Create or modify: focused full-chain account-risk test under `tests/integration/`
- Modify: `docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md`

**Interfaces:**
- Consumes: valid Account Capacity Claim and current policy/budget projections.
- Produces: a non-executing proof from dynamic account snapshot to Ticket, FinalGate, lifecycle release, and capacity recovery.

- [ ] Write a failing full-chain test covering snapshot, downsize, reservation, Ticket materialization, FinalGate, terminal lifecycle release, and a subsequent capacity claim.
- [ ] Run the focused chain test and verify it fails at the current disconnected contract boundary.
- [ ] Bind new claim fields when Ticket reservation is consumed; require all fields at ticket creation and FinalGate revalidation.
- [ ] Run the focused full-chain test green.
- [ ] Run the targeted unit and PostgreSQL suites named in Tasks 1-4; record exact command output.
- [ ] Run `git diff --check`, `python3 scripts/validate_current_docs_authority.py`, and `python3 scripts/audit_production_runtime_file_io.py`.
- [ ] Run the repository full test suite once after all focused suites are green, then update the remediation design status only with observed results.

## Stop Condition

Stop immediately and report rather than bypass a failed invariant, a migration incompatibility, a non-account-risk regression, an unclear Ticket schema dependency, or a test that requires exchange writes. Deployment remains out of scope even when all local certification gates pass.
