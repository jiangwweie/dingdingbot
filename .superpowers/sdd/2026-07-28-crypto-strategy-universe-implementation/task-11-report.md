# Task 11 implementation report

## Status

Implemented locally on disposable PostgreSQL only. No Tokyo, production
PostgreSQL, systemd, exchange, U.S.-equity, installation, certification,
warming, or activation action was performed.

The implementation now:

- freezes required `universe_version_id` and
  `universe_semantic_digest` through `StrategySignal`,
  `CapacityClaim`, `TradeTicket`, PostgreSQL persistence, and dispatch
  preflight;
- admits Signals and ready candidates only when runtime Scope, active current
  pointer, digest, and eligible member agree exactly;
- removes candidate-scope rank from arbitration and PostgreSQL selection;
- revalidates and row-locks the current Universe/member before Ticket issuance;
- rejects a switched Universe before Entry dispatch with zero fake-Venue
  mutation.

## TDD RED evidence

### Collection and domain lineage

1. Command:
   `python3 -m pytest --collect-only -q
   tests/trading_kernel/unit/test_arbitration.py
   tests/trading_kernel/integration/test_issue_ticket.py`
   - Result: exit 2.
   - Expected failure:
     `ImportError: cannot import name 'strategy_candidate_scopes'`;
     `0002` had removed the table while the Signal repository still imported
     it.
2. Command:
   `python3 -m pytest -q tests/trading_kernel/unit/test_signal.py
   tests/trading_kernel/unit/test_arbitration.py`
   - Result: 5 failed, 3 passed.
   - Expected failure: `StrategySignal` rejected explicit
     `universe_version_id` and `universe_semantic_digest` as extra fields.
3. Command:
   `python3 -m pytest -q tests/trading_kernel/unit/test_capacity.py
   tests/trading_kernel/unit/test_entry_dispatch_preflight.py`
   - Result: 4 failed.
   - Expected failure: `CapacityClaim` and `TradeTicket` had no frozen
     Universe identity.

### PostgreSQL current-pointer behavior

1. Command:
   `python3 -m pytest -q
   tests/trading_kernel/integration/test_universe_signal_eligibility.py`
   - Result: 1 failed.
   - Expected behavior-level failure: after the current pointer switched, old
     lineage ingestion returned `CANDIDATE_READY` rather than
     `SCOPE_OR_POLICY_MISMATCH`.
2. Command:
   `python3 -m pytest -q
   tests/trading_kernel/integration/test_issue_ticket.py::test_current_universe_switch_committing_before_issue_rejects_old_claim`
   - Result: 1 failed.
   - Expected race failure: an uncommitted current-pointer update held the row
     lock, but the old plain read saw the previous pointer and returned
     `ISSUED`.
3. Command:
   `python3 -m pytest -q
   tests/trading_kernel/integration/test_command_dispatch.py::test_current_universe_switch_before_entry_dispatch_causes_zero_venue_mutations`
   - Result: 1 failed under the deliberate removal of the WIP current-Universe
     comparison.
   - Expected mutation failure: dispatch returned `ACCEPTED` and reached the
     fake Venue. Restoring the current-pointer assertion was therefore
     behaviorally necessary, not source-only coverage.

## Minimal GREEN

- `PostgresSignalRepository.get_active_universe_member` performs an exact
  current-pointer/member query. Ticket issue uses `FOR UPDATE OF
  brc_strategy_universe_current, brc_strategy_universe_members`.
- Ticket issue locks Universe authority before locked runtime Scope authority,
  establishing a consistent future activation lock order and avoiding the
  scope-then-pointer deadlock shape.
- Signal, Claim, and Ticket fields are required, non-blank, and use exact
  SHA-256 digest validation without defaults or nullable fallback.
- PostgreSQL Signal, Claim, and Ticket encoders/decoders persist the same
  frozen identity.
- Entry selection joins current Universe and member authority and orders only
  by Owner Policy priority, occurrence time, observed time, and Signal ID.
- Dispatch loads the active current pointer/member and rejects a mismatch
  before Venue execution.

## Focused verification evidence

1. Two new race tests:
   - Result: **2 passed**.
2. Ticket issue integration:
   `python3 -m pytest -q
   tests/trading_kernel/integration/test_issue_ticket.py`
   - Result: **14 passed**.
3. Command dispatch integration:
   `python3 -m pytest -q
   tests/trading_kernel/integration/test_command_dispatch.py`
   - Result: **19 passed**.
4. Task 11 domain and Universe eligibility group:
   - Result: **27 passed**.
   - Files: Signal, arbitration, capacity, Ticket, entry preflight,
     live/replay lineage, and PostgreSQL Universe signal eligibility.
5. Extended persistence chain:
   - Result: **20 passed**.
   - Files: `test_signal_to_ticket.py` (12),
     `test_capacity_claim_to_ticket.py` (2), and
     `test_pg_unit_of_work.py` (6).
6. Combined focused rerun:
   - Result: **80 passed in 46.96s**.

## Static and diff evidence

1. `python3 -m ruff ...`
   - Environment failure: the default Python 3.14 environment has no installed
     `ruff` module. No environment was changed.
2. `/tmp/brc-p1-static/bin/ruff check --select E4,E7,E9,F ...`
   - Found the pre-existing **F842** baseline at
     `src/trading_kernel/domain/capacity.py:647-648`: unreachable local
     annotations `venue_id` and `exchange_instrument_id`.
   - `git diff --unified=0` confirms Task 11 did not touch those lines.
3. `/tmp/brc-p1-static/bin/ruff check --select E4,E7,E9,F --ignore F842 ...`
   - Result: **All checks passed** across every Task 11 touched source and test
     file.
4. `git diff --check`
   - Result: **passed** with no whitespace errors.

## Concerns and boundaries

- Dispatch current-pointer verification is fresh before the venue call and the
  tested pre-existing switch is rejected with zero Venue writes. A database
  row lock cannot remain open across network I/O; future atomic activation must
  serialize its pointer switch against the existing global ENTRY lane/durable
  claimed-command boundary to close a switch occurring after preflight but
  before the external mutation.
- The F842 pair is an unrelated baseline and remains unchanged.
- Universe installation, certification, warming, activation, and their older
  runtime-authority/observation consumers remain outside Task 11.

## Review fix round 1/5

### Status

All three Important findings and the issue-race P2 finding were fixed locally.
No Tokyo, production PostgreSQL, systemd, exchange, U.S.-equity, installer,
warming, or activation action was performed.

### RED evidence

1. Observation integration before fixture/source repair:
   `python3 -m pytest -q
   tests/trading_kernel/integration/test_observation_to_signal.py`
   - Result: **5 failed**.
   - Exact first failure: canonical 0002 metadata rejected the deleted
     `enabled` fixture column.
   - After migrating the fixture, the real producer failed first on deleted
     `RuntimeScopeSnapshot.enabled`, then the six-event test failed on deleted
     Registry `candidate_instruments`.
2. Missing action-time facts:
   - Command: the two new ENTRY/SET_LEVERAGE no-facts tests.
   - Result: **2 failed**.
   - Both commands incorrectly returned `ACCEPTED` and reached the fake Venue.
3. Preflight-to-Venue Universe race:
   - Command: the new controlled dispatch race test.
   - Result: **1 failed**.
   - A direct current-pointer update committed after the preflight transaction
     closed and before Venue dispatch; the expected database fence was absent.

### GREEN behavior

- ENTRY and SET_LEVERAGE always run action-time preflight. A missing
  `EntryFactsSource` returns `RUNTIME_FENCED`, records a rejected command, and
  performs zero Venue mutations. Non-entry lifecycle dispatch remains
  independent of Entry facts.
- `brc_strategy_universe_current` now owns a PostgreSQL statement-level
  INSERT/UPDATE/DELETE trigger. The trigger atomically creates and locks the
  existing global Entry lane and rejects every pointer mutation while the lane
  is non-idle with SQLSTATE `55000`. This is an executable database contract
  for Task 10 and direct SQL, not a future facade convention.
- The trigger uses statement-level `BEFORE` execution, preserving the global
  `Entry lane -> Universe pointer` lock order and holding no transaction across
  Venue I/O.
- The controlled race pauses exactly after the dispatch preflight UoW has
  closed and before Venue invocation. PostgreSQL rejects the concurrent direct
  pointer update, dispatch then reaches Venue once under unchanged frozen
  authority, and the current pointer remains unchanged.
- Observation uses lifecycle state, `observation_enabled`, `entry_enabled`,
  exact active pointer/digest/member authority, and typed PostgreSQL active
  Universe membership for comparative peers. The real six-event
  Observation-to-Signal integration creates Signals without Ticket or Exchange
  Command side effects.
- Observation scheduling now uses canonical
  `next_observation_due_at_ms`/`lease_expires_at_ms`/`lease_owner` columns.
- The issue race no longer guesses with `asyncio.sleep(0.05)`. It records both
  PostgreSQL backend PIDs, waits until `pg_blocking_pids(issue_pid)` proves the
  switch transaction is blocking issue, asserts issue is unfinished, commits
  the switch, then verifies the replacement pointer is reread and no Claim,
  Ticket, Command, Reservation, or lane claim was persisted.

### Review-fix verification

1. Observation integration:
   `python3 -m pytest -q
   tests/trading_kernel/integration/test_observation_to_signal.py`
   - Result: **5 passed**.
2. Dispatch integration:
   `python3 -m pytest -q
   tests/trading_kernel/integration/test_command_dispatch.py`
   - Result: **21 passed**.
3. Ticket issue integration:
   `python3 -m pytest -q
   tests/trading_kernel/integration/test_issue_ticket.py`
   - Result: **14 passed**.
4. Schema/migration group:
   `test_strategy_universe_schema.py`,
   `test_schema_migration_postgres.py`, and `test_schema_baseline.py`
   - Result: **23 passed**.
5. Combined Task 11 focused group:
   - Result: **87 passed in 51.07s**.
   - Includes dispatch, issue, Observation-to-Signal, Universe eligibility,
     Live/Replay parity, persistence chain, PostgreSQL UoW, and affected domain
     unit tests.
6. Focused Ruff:
   `/tmp/brc-p1-static/bin/ruff check --select E4,E7,E9,F ...`
   - Result: **All checks passed** across all review-fix source and test files.
7. `git diff --check`
   - Result: **passed** with no whitespace errors.

### Remaining boundary

- The database trigger deliberately supersedes the retired test shape that
  mutated the current pointer after Ticket issuance and expected dispatch to
  notice later. Such a switch is now rejected at the mutation boundary; the
  stronger controlled preflight-to-Venue race proves that contract directly.
- Production runtime-authority installation and activation remain later-task
  work and were not implemented here.
