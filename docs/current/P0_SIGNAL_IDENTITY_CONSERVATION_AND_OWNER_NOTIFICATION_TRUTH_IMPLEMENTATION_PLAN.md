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

- [ ] Add failing tests proving a ready count without PG signal IDs becomes `runtime_signal_identity_gap`.
- [ ] Add failing tests proving named PG signals remain opportunity-ready.
- [ ] Implement the minimum classification changes.
- [ ] Run the targeted tests and preserve non-authority safety invariants.

### Task 2: Plain Owner Notification Truth

**Files:**
- Modify: `scripts/runtime_signal_watcher_tick.py`
- Test: `tests/unit/test_runtime_signal_watcher_tick.py`

- [ ] Add a failing reproduction of the 2026-07-13 10:00 shape.
- [ ] Assert the notification names no opportunity when `signal_event_ids=[]`.
- [ ] Assert the identity-gap text is plain Chinese and says no order was placed.
- [ ] Assert a named PG signal message includes StrategyGroup, symbol, and direction.
- [ ] Assert internal terms and `memory:*` refs are absent from Owner text.
- [ ] Implement message generation from `post_signal_auto_resume` and PG signal diagnostics.

### Task 3: Durable Signal-Materialization Outcome

**Files:**
- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify: `src/application/runtime_process_outcome.py` only if classification needs a typed signal-materialization status
- Test: `tests/unit/test_runtime_active_observation_monitor.py`
- Test: `tests/unit/test_runtime_process_outcome.py`

- [ ] Add failing tests for lane-scoped failure persistence.
- [ ] Add failing tests for same-lane success replacement and expired-event noop.
- [ ] Implement bounded process-outcome upserts in the existing PG transaction.
- [ ] Prove no-candidate ticks create no process outcome.

### Task 4: Regression, Governance, And Deployment

**Files:**
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Test: existing watcher, monitor, notification, Event Spec, Ticket, deploy, and audit suites.

- [ ] Run targeted watcher and process-outcome tests.
- [ ] Run six-Event-Spec and Action-Time regression suites.
- [ ] Run `validate_current_docs_authority.py`, output-scope validation, and production file-I/O audit.
- [ ] Commit the focused branch, integrate into `dev`, and push.
- [ ] Run Tokyo deploy dry-run and apply.
- [ ] Verify exact release head, PG migration count, watcher/monitor health, no-signal zero-write behavior, and plain notification dry-run shapes.
- [ ] Mark this plan complete only from fresh verification evidence.
