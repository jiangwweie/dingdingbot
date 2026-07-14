---
title: P1_REAL_TRADE_FACT_TRUTH_AND_VENUE_LINEAGE_IMPLEMENTATION_PLAN
status: CURRENT
authority: docs/current/P1_REAL_TRADE_FACT_TRUTH_AND_VENUE_LINEAGE_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-14
---

# P1 Real-Trade Fact Truth And Venue Lineage Implementation Plan

> **For agentic workers:** Execute inline with test-driven development. Subagents are disabled for this repository task.

**Goal:** Make every real Ticket conserve exact entry, TP1, SL/runner, external-close, fee, funding, PnL, and terminal-status facts without changing strategy, risk, sizing, profile, or exchange-write authority.

**Architecture:** Extend the existing ticket-bound Fill Projector instead of adding another lifecycle model. The read-only exchange snapshot carries Binance conditional parent-to-actual-order lineage; the projector binds fills to protection roles, Outcome reduces canonical lifecycle fill events, reconciliation emits only state changes, and lifecycle closure makes the Ticket terminal.

**Tech Stack:** Python 3.10, SQLAlchemy, PostgreSQL, Decimal, pytest, Binance USDT-M read-only exchange facts.

## Global Constraints

- PG and exchange read facts remain the only current authority; no JSON/Markdown runtime source or recurring report writer.
- No strategy, symbol, side, risk fraction, leverage, notional, profile, FinalGate, Operation Layer, withdrawal, transfer, or exchange-write expansion.
- Financial calculations use `decimal.Decimal`.
- Exchange reads remain timeout-bounded and outside PG transactions in the production worker.
- Reconciliation writes lifecycle events only when business state or exact fact identity changes.
- A conditional fill is attributed to a protection role only through exact `algoId -> actualOrderId` lineage.

---

### Task 1: Canonical conditional-order fill lineage

**Files:**
- Modify: `src/infrastructure/exchange_gateway.py`
- Modify: `src/application/action_time/exchange_snapshot_provider.py`
- Modify: `scripts/run_ticket_bound_lifecycle_maintenance_once.py`
- Test: `tests/unit/test_ticket_bound_exchange_snapshot_provider.py`

**Interfaces:**
- Produces: `fetch_conditional_order_lineage(symbol, parent_exchange_order_ids)` returning read-only parent/actual/client/status facts.
- Produces: normalized fills containing `parent_exchange_order_id` only when the exchange proves the relation.

- [x] Write a failing test showing an `algoId=400...` and `actualOrderId=395...` response annotates the matching fill with `parent_exchange_order_id=400...`.
- [x] Run the exact test and verify failure is caused by missing conditional lineage.
- [x] Implement the bounded read and normalization without exchange mutation.
- [x] Run the exact test and verify it passes.

### Task 2: Existing filled-order backfill and exact protection-role attribution

**Files:**
- Modify: `src/application/action_time/ticket_bound_fill_projector.py`
- Modify: `src/application/action_time/protection_reconciler.py`
- Modify: `src/application/action_time/external_close_attribution.py`
- Test: `tests/unit/test_ticket_bound_protection_reconciler.py`
- Test: `tests/unit/test_live_outcome_ledger.py`

**Interfaces:**
- Consumes: normalized direct or parent-bound fill identity.
- Produces: one idempotent `tp1_filled` or `final_exit_detected` event per exact exchange fill.

- [x] Write a failing test proving a PG order already marked `filled` but lacking its lifecycle fill event is backfilled.
- [x] Write a failing test proving an SL parent order and its actual child fill are classified as `SL`, never `EXTERNAL_CLOSE`.
- [x] Run both tests and verify the expected failures.
- [x] Implement exact parent/direct matching and preserve conflicting-fill hard stops.
- [x] Run both tests and verify they pass.

### Task 3: Change-only reconciliation events and terminal Ticket state

**Files:**
- Modify: `src/application/action_time/protection_reconciler.py`
- Modify: `src/application/action_time/ticket_bound_lifecycle_finalizer.py`
- Test: `tests/unit/test_ticket_bound_protection_reconciler.py`
- Test: `tests/unit/test_ticket_bound_lifecycle_finalizer.py`

**Interfaces:**
- Produces: one reconciliation transition event for unchanged protected truth.
- Produces: `brc_action_time_tickets.status='closed'` after exact lifecycle closure.

- [x] Write a failing test that repeats an identical reconciliation snapshot and expects the event count to remain one.
- [x] Write a failing test that finalizes a lifecycle whose Ticket is `submitted` or historical `expired` and expects Ticket `closed`.
- [x] Run both tests and verify the expected failures.
- [x] Implement semantic event identity and terminal Ticket synchronization.
- [x] Run both tests and verify they pass.

### Task 4: Incomplete closed-Outcome repair and three-ticket acceptance

**Files:**
- Modify: `src/application/action_time/lifecycle_maintenance_scheduler.py`
- Modify: `src/application/action_time/live_outcome_ledger.py`
- Test: `tests/unit/test_ticket_bound_lifecycle_scheduler.py`
- Test: `tests/unit/test_live_outcome_ledger.py`

**Interfaces:**
- Produces: bounded selection of closed lifecycles whose structured Outcome lacks exact fill economics.
- Produces: complete fee, funding availability, realized PnL, net PnL, and R from canonical fills.

- [x] Write a failing test that selects one closed lifecycle with incomplete Outcome and stops selecting it after exact fills are projected.
- [x] Write a failing regression fixture for the first SOL fee total `0.0510812` and net PnL `0.7089188` excluding funding.
- [x] Run both tests and verify the expected failures.
- [x] Implement bounded repair selection and strict completeness metadata.
- [x] Run both tests and verify they pass.

### Task 5: Release certification and production acceptance

**Files:**
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`

- [x] Run targeted unit and PostgreSQL integration tests.
- [x] Run `python3 scripts/audit_production_runtime_file_io.py` and require `performance_risk.status=clear`.
- [x] Run `python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked`.
- [x] Run the complete Release suite once and require zero failures.
- [x] Commit and push the focused branch.
- [x] Deploy through the Tokyo deployment contract and run read-only PG/runtime acceptance.
- [x] Verify the three real Tickets: first SOL exact economics, AVAX exact SL lineage, and latest SOL automatic terminal Outcome when closed.
- [x] Create and push `release/brc-real-trade-fact-truth-20260714-r0` and annotated tag `brc-real-trade-fact-truth-20260714-r0` from the certified commit.

## Stop Condition

Stop this mainline when the three real Ticket facts are internally consistent, unchanged reconciliation creates no duplicate business event, Tokyo acceptance passes, and the release branch/tag point to the deployed certified commit. Do not expand into multi-position budget design inside this task.
