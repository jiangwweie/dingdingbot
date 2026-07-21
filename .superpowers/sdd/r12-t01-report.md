# P0-ACH-R12-T01 — Production-shaped RED report

## Status

**DONE_WITH_CONCERNS.** This task adds exactly four test-only RED regressions;
no production module, migration, runtime policy, credentials, profile, sizing,
Tokyo state, or exchange network path was changed.

## Changed files

- `tests/unit/test_ticket_bound_exchange_command_worker.py`
  - ENTRY crosses Ticket TTL: asserts durable ENTRY, submitted Ticket, and
    same-source SL dispatch.
  - Competing protected-submit sources: materializes distinct Ticket, Attempt,
    and command rows and declares exact primary source/attempt/role selection.
  - Restart after committed ENTRY: expires the Ticket after the committed ENTRY
    result, closes the original SQLAlchemy connection, and requires the next
    worker to dispatch only the same-source SL.
- `tests/unit/test_ticket_bound_lifecycle_global_deadline.py`
  - Invocation-owned `absolute_deadline_at`: ENTRY consumes the deadline and
    must not renew a full budget for the Initial Stop drain.

## Individual RED evidence

1. `ENTRY` across TTL

   ```text
   .venv/bin/pytest -q tests/unit/test_ticket_bound_exchange_command_worker.py::test_entry_effect_crossing_ticket_ttl_submits_ticket_and_drains_its_initial_stop
   FAILED: assert False is True
   ```

   Current result has `initial_protection_complete=false`; the expected contract
   also asserts Ticket `submitted`, ENTRY `confirmed_submitted`, and the exact
   Attempt/source SL `confirmed_submitted`.

2. Competing sources

   ```text
   .venv/bin/pytest -q tests/unit/test_ticket_bound_exchange_command_worker.py::test_initial_protection_drain_is_pinned_to_the_primary_attempt_source
   FAILED: TypeError: run_one_ticket_bound_exchange_command() got an unexpected keyword argument 'source_command_id'
   ```

   The setup has two durable, eligible protected-submit Attempts/sources. The
   declared corrected contract requires `source_command_id`,
   `protected_submit_attempt_id`, and `allowed_roles`; the foreign SL remains
   `prepared` while the primary SL is confirmed.

3. Absolute deadline

   ```text
   .venv/bin/pytest -q tests/unit/test_ticket_bound_lifecycle_global_deadline.py::test_entry_drain_uses_the_invocation_absolute_deadline_without_resetting_budget
   FAILED: TypeError: run_one_ticket_bound_exchange_command() got an unexpected keyword argument 'absolute_deadline_at'
   ```

   The test uses a monotonic clock where ENTRY consumes the interval to
   `109.999` of an absolute `110.0` deadline and requires no reset-budget SL
   dispatch.

4. Restart after committed ENTRY

   ```text
   .venv/bin/pytest -q tests/unit/test_ticket_bound_exchange_command_worker.py::test_restart_after_entry_result_commit_recovers_same_source_initial_stop
   FAILED: assert 'no_prepared_command' == 'command_confirmed'
   ```

   ENTRY is committed with complete typed fill facts, the Ticket is then
   expired, the original SQLAlchemy connection is closed, and the next worker
   must recover the same-source SL without a second ENTRY.

## Baseline preservation

```text
.venv/bin/pytest -q tests/unit/test_ticket_bound_exchange_command_worker.py tests/unit/test_ticket_bound_lifecycle_global_deadline.py -k 'not entry_effect_crossing_ticket_ttl_submits_ticket_and_drains_its_initial_stop and not initial_protection_drain_is_pinned_to_the_primary_attempt_source and not restart_after_entry_result_commit_recovers_same_source_initial_stop and not entry_drain_uses_the_invocation_absolute_deadline_without_resetting_budget'
27 passed, 4 deselected
```

The required focused command reports only the four new failures:

```text
4 failed, 27 passed
```

`git diff --check` and `ruff check` on both changed test modules pass.

## Self-review

- The tests use the existing SQLAlchemy durable command/Ticket/Attempt fixture,
  query durable identities/states, and use complete accepted ENTRY response
  facts.
- No mock-only behavior is asserted; test gateways model the exchange boundary
  while PG-shaped state remains the assertion authority.
- The source and deadline cases deliberately fail at explicit missing public API
  boundaries, as allowed by the task card; their full PG-shaped setup and
  post-correction contract are declared before the call.
- The PostgreSQL RCI service is available locally. An attempted RCI process
  variant was not retained because the existing RCI setup is blocked before
  command materialization by unrelated
  `account_capacity_base_fact_snapshot_missing` / `not_safe` FinalGate fixture
  drift. The retained restart regression uses the repository fixture already
  used by the focused worker baseline, closes the original SQLAlchemy
  connection, and fails at the intended expired-Ticket claim predicate.

## Commit

`HEAD` — `test: reproduce entry-expiry source-drain and deadline failures`
