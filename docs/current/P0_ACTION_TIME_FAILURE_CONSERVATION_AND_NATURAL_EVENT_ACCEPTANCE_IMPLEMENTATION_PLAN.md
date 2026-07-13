---
title: P0_ACTION_TIME_FAILURE_CONSERVATION_AND_NATURAL_EVENT_ACCEPTANCE_IMPLEMENTATION_PLAN
status: CURRENT_IMPLEMENTATION_PLAN
authority: docs/current/P0_ACTION_TIME_FAILURE_CONSERVATION_AND_NATURAL_EVENT_ACCEPTANCE_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-13
---

# P0 Action-Time Failure Conservation And Natural-Event Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conserve triggered Action-Time refresh failures in PG and certify the six 2026-07-12 CPM events through the current pre-exchange boundary without exchange writes.

**Architecture:** Extend the existing PG process-outcome current projection for the outer refresh sequence and extend the existing production-shaped full-chain simulation harness with a stop-before-gateway acceptance runner. Historical identities remain typed provenance only; the isolated runner generates new acceptance lineage under a fixed event clock.

**Tech Stack:** Python 3, SQLAlchemy, Pydantic/dataclasses, PostgreSQL current projections, SQLite in-memory acceptance fixtures, pytest.

## Global Constraints

- PG/current remains the only production runtime authority.
- No new JSON/Markdown runtime reader or recurring writer.
- No production PG mutation during historical acceptance.
- No exchange gateway call, order lifecycle call, profile change, sizing-default change, withdrawal, or transfer.
- Financial values use `Decimal`.
- No-signal ticks create zero acceptance rows and zero files.
- Triggered Action-Time refresh remains governed by the 30-second engineering latency budget.

---

### Task 1: Outer Refresh Failure Conservation

**Files:**
- Modify: `scripts/run_server_product_state_refresh_sequence.py`
- Test: `tests/unit/test_server_product_state_refresh_sequence.py`

**Interfaces:**
- Consumes: `action_time_trigger_state`, per-step `CommandResult`, `PG_DATABASE_URL`.
- Produces: one `action_time_refresh_sequence` row through `materialize_runtime_process_outcome(...)` for a triggered run.

- [x] Write failing tests proving a required-step timeout conserves stage, lane, source watermark, and timing.
- [x] Run the focused test and observe the expected missing-outcome failure.
- [x] Implement trigger identity lookup, exact failure extraction, and one bounded PG outcome upsert.
- [x] Add a failing test proving no-trigger ticks write no outcome.
- [x] Implement the no-trigger zero-write rule and rerun focused tests.

### Task 2: Read-Model And Monitor Failure Authority

**Files:**
- Modify: `src/application/action_time/process_outcome_relevance.py`
- Modify: `src/application/readmodels/strategy_live_candidate_pool.py`
- Modify: `scripts/run_tokyo_runtime_server_monitor.py`
- Test: `tests/unit/test_runtime_process_outcome.py`
- Test: `tests/unit/test_strategy_live_candidate_pool.py`
- Test: `tests/unit/test_tokyo_runtime_server_monitor.py`

**Interfaces:**
- Consumes: current PG `action_time_ticket_sequence` and `action_time_refresh_sequence` outcomes.
- Produces: `action_time_boundary_not_reproduced` until the same process/lane has a newer success.

- [x] Write failing tests for refresh timeout authority and later-success clearance.
- [x] Run tests and observe market-wait/ignored-outcome failures.
- [x] Generalize process outcome relevance without changing non-Action-Time processes.
- [x] Rerun focused read-model and monitor tests.

### Task 3: Fixed-Clock Pre-Exchange Acceptance Harness

**Files:**
- Modify: `src/application/action_time/full_chain_simulation_harness.py`
- Test: `tests/unit/test_action_time_full_chain_impact.py`

**Interfaces:**
- Consumes: `HistoricalActionTimeAcceptanceCase`, isolated SQLAlchemy connection, current production materializers.
- Produces: typed acceptance payload ending with prepared `brc_ticket_bound_exchange_commands` and `exchange_write_called=false`.

- [x] Write a failing test for one historical case reaching durable exchange-command preparation without a gateway call.
- [x] Implement the bounded pre-exchange runner by reusing current materializers.
- [x] Add failure-stage conservation and fixed-clock assertions.
- [x] Rerun focused harness tests.

### Task 4: Six Historical Event Acceptance Matrix

**Files:**
- Test: `tests/unit/test_action_time_historical_event_acceptance.py`

**Interfaces:**
- Consumes: six typed PG-provenance cases from 2026-07-12.
- Produces: five Ticket acceptances plus one dynamic-sizing control result.

- [x] Encode the six exact signal/Ticket identities and historical fact observations as typed in-memory fixtures.
- [x] Run the five Ticket cases through durable exchange-command preparation.
- [x] Run the sixth signal through current dynamic sizing and assert prepared commands or one exact legitimate sizing blocker.
- [x] Assert every case has fixed historical time, no exchange write, no gateway call, and no production identity reuse.

### Task 5: Contracts, Audit, Regression, And Integration

**Files:**
- Modify: `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/P0_ACTION_TIME_FAILURE_CONSERVATION_AND_NATURAL_EVENT_ACCEPTANCE_IMPLEMENTATION_PLAN.md`

**Interfaces:**
- Consumes: verified tests and audit output.
- Produces: current contract/roadmap status and an integration-ready commit.

- [x] Run focused Action-Time, Candidate Pool, server monitor, and process-outcome tests.
- [x] Run `python3 scripts/audit_production_runtime_file_io.py --fail-on-risk`.
- [x] Run current-document and output-scope validators.
- [x] Run compile/lint equivalents available in the workspace.
- [x] Review the diff for authority leakage and mark plan checkboxes complete.
- [x] Commit, integrate into `dev`, push, deploy through the official Tokyo path, and run read-only postdeploy acceptance.
