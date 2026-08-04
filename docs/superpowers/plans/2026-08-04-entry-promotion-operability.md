# Entry Promotion Operability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore permanent official Entry-promotion operability for the deployed Policy v4 runtime and complete Tokyo Entry activation.

**Architecture:** Keep shared exchange-command capability enabled for safety workers and use Policy plus service fencing as the new-ENTRY boundary. Refresh an expired Certification Batch directly from the exact Active Universe manifest without creating replacement Universe versions.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy Core async, PostgreSQL, pytest, systemd, Binance readonly adapters.

## Global Constraints

- No strategy, capital, leverage, credential, account, instrument or market-scope change.
- No manual SQL lifecycle mutation or direct exchange write.
- Entry remains inactive/disabled/fenced until official promotion final postflight.
- Every production code change follows RED/GREEN TDD.
- New Release Commit must pass the fixed six-stage release certification.

---

### Task 1: Compatible capability promotion gate

**Files:**
- Modify: `scripts/trading_kernel/certify_readonly.py`
- Test: `tests/trading_kernel/integration/test_entry_promotion_gate.py`

**Interfaces:**
- `entry_promotion_pass` accepts a current boolean `exchange_commands` capability when Policy still has `new_entry_submit_enabled=false`.
- Existing identity, Batch, flatness, Incident and command gates remain unchanged.

- [ ] Add a production-shaped test with `exchange_commands=true` before promotion.
- [ ] Run the exact test and confirm `entry_promotion_pass` is false.
- [ ] Remove the incorrect disabled-capability requirement.
- [ ] Re-run the test and related promotion tests.

### Task 2: Exact Active Universe Batch refresh

**Files:**
- Modify: `scripts/trading_kernel/bootstrap_strategy_universes.py`
- Test: `tests/trading_kernel/unit/test_bootstrap_strategy_universes.py`
- Test: `tests/trading_kernel/integration/test_entry_promotion_gate.py`

**Interfaces:**
- Add `refresh_active_certification_batch(database_url, runtime_profile_id, now_ms)` returning the exact Batch id.
- Add CLI flag `--refresh-active-certification-batch-only`.
- Validate six exact Active current Universes, seven exact members, no Warming Universe and exact runtime authority.
- Reuse `_ensure_certification_batch`; do not call `configure_strategy_universe`.

- [ ] Add RED parser/unit tests for the new mode and mutually exclusive preparation modes.
- [ ] Add RED PostgreSQL test proving no Universe/version/scope count changes.
- [ ] Implement exact Active-manifest validation and Batch creation.
- [ ] Re-run unit and integration tests.

### Task 3: Candidate verification and release

**Files:**
- Modify only tests/documents required by the two behaviors above.

- [ ] Run targeted promotion, bootstrap and certification tests.
- [ ] Run Ruff, Mypy and `git diff --check`.
- [ ] Commit the candidate and run `certify_release_candidate.py` for the exact SHA.

### Task 4: Tokyo regular deployment and promotion

- [ ] Refresh PostgreSQL, systemd and Binance readonly facts.
- [ ] Deploy the certified SHA through regular release mode without enabling Entry.
- [ ] Run Active Universe Batch refresh and wait for completion.
- [ ] Run official `promote_entry.py` on the server.
- [ ] Verify Policy armed, Entry active/enabled, fence absent, four workers stable, identity exact, zero Incident/Command and Binance still flat.
- [ ] Create the next immutable Tokyo tag and update only volatile production authority in the Roadmap through a separate documentation commit.

