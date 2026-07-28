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
