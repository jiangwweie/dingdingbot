---
title: P0_SIGNAL_IDENTITY_CONSERVATION_AND_OWNER_NOTIFICATION_TRUTH_IMPLEMENTATION_PLAN
status: CURRENT_IMPLEMENTATION_PLAN
authority: docs/current/P0_SIGNAL_IDENTITY_CONSERVATION_AND_OWNER_NOTIFICATION_TRUTH_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-13
---

# P0 Signal Identity Conservation And Owner Notification Truth Implementation Plan

> **For agentic workers:** Execute inline under Codex ownership. Do not dispatch subagents in the current session. Steps use checkbox syntax for tracking.

**Goal:** Make named PG signal identity the only source of opportunity language while durably conserving anonymous-ready materialization failures.

**Architecture:** Extend the existing watcher, PG live-signal materializer, runtime process-outcome model, and static Owner notification path. Do not add a bridge, file artifact, report directory, or new runtime authority.

**Tech Stack:** Python, SQLAlchemy, PostgreSQL current projections, Pydantic, pytest, systemd watcher and Feishu webhook.

## Global Constraints

- No strategy, capital, leverage, symbol, side, profile, FinalGate, Operation Layer, or exchange-write authority change.
- PG/current services remain production truth.
- No recurring JSON/MD writes; no-signal ticks create zero files and zero signal-process rows.
- Use targeted TDD before implementation and run production file-I/O audit before completion.

---

### Task 1: Authoritative Signal Classification

**Files:**
- Modify: `scripts/build_runtime_strategy_signal_watch_evidence.py`
- Modify: `scripts/build_runtime_observation_operator_evidence.py`
- Modify: `scripts/build_runtime_observation_wakeup_evidence.py`
- Test: `tests/unit/test_runtime_strategy_signal_watch_evidence.py`
- Test: `tests/unit/test_runtime_observation_operator_evidence.py`
- Test: `tests/unit/test_runtime_observation_wakeup_evidence.py`

- [x] Add failing tests proving a ready count without PG signal IDs becomes `runtime_signal_identity_gap`.
- [x] Add failing tests proving named PG signals remain opportunity-ready.
- [x] Implement the minimum classification changes.
- [x] Run the targeted tests and preserve non-authority safety invariants.

### Task 2: Retire Watcher Notification And Use Server Monitor Truth

**Files:**
- Modify: `scripts/runtime_signal_watcher_tick.py`
- Modify: `scripts/run_tokyo_runtime_server_monitor.py`
- Test: `tests/unit/test_runtime_signal_watcher_tick.py`
- Test: `tests/unit/test_tokyo_runtime_server_monitor.py`

- [x] Add a failing reproduction of the 2026-07-13 10:00 shape.
- [x] Assert the watcher never sends production Owner Feishu directly.
- [x] Assert the server monitor names no opportunity when `signal_event_ids=[]`.
- [x] Assert the identity-gap card is plain Chinese and says no order was placed.
- [x] Assert a named PG signal card includes StrategyGroup, symbol, and direction.
- [x] Assert internal terms and `memory:*` refs are absent from Owner text.
- [x] Implement server-monitor message generation from PG signal/process outcomes.

### Task 3: Durable Signal-Materialization Outcome

**Files:**
- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify: `src/application/runtime_process_outcome.py` only if classification needs a typed signal-materialization status
- Test: `tests/unit/test_runtime_active_observation_monitor.py`
- Test: `tests/unit/test_runtime_process_outcome.py`

- [x] Add failing tests for lane-scoped failure persistence.
- [x] Add failing tests for same-lane success replacement and expired-event noop.
- [x] Implement bounded process-outcome upserts in the existing PG transaction.
- [x] Prove no-candidate ticks create no process outcome.

### Task 4: Regression, Governance, And Deployment

**Files:**
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Test: existing watcher, monitor, notification, Event Spec, Ticket, deploy, and audit suites.

- [x] Run targeted watcher and process-outcome tests.
- [x] Run six-Event-Spec and Action-Time regression suites.
- [x] Run `validate_current_docs_authority.py`, output-scope validation, and production file-I/O audit.
- [ ] Commit the focused branch, integrate into `dev`, and push.
- [ ] Run Tokyo deploy dry-run and apply.
- [ ] Verify exact release head, PG migration count, watcher/monitor health, no-signal zero-write behavior, and plain notification dry-run shapes.
- [ ] Mark this plan complete only from fresh verification evidence.
