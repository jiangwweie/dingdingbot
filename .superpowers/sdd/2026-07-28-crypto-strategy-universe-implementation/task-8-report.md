# Task 8 Report — Warming Observation Without Entry

## Scope

Implemented only Task 8 from
`docs/superpowers/plans/2026-07-28-crypto-strategy-universe-implementation.md`.

- The existing Observation path now distinguishes `warming` from `active`.
- `warming` reuses the same market snapshot, detector, and typed Fact path,
  then persists a version/digest/fact-bound `WarmReadiness`.
- `warming` returns `ObservationStatus.WARMED` before StrategySignal
  production or ingestion.
- `active` retains the existing Signal producer and ingestion semantics.
- No activation, installer, certification, new worker, deployment, systemd,
  Tokyo, production, Ticket, Exchange Command, or exchange mutation behavior
  was added.

The existing Observation worker and CLI needed no new configuration: the worker
already carries `ObservationStatus` in its result and schedules the next closed
bar after any non-invalid observation. The new explicit `WARMED` status therefore
flows through the existing worker without a second worker or producer.

## Invariants

- A warming scope must be `observation_enabled=true`,
  `entry_enabled=false`, and `lifecycle_state=warming`.
- An active scope must remain `observation_enabled=true`,
  `entry_enabled=true`, and current for its Event.
- Observation resolves the exact PostgreSQL Universe version dynamically; it
  does not read a Registry candidate list or static instrument map.
- The exact version/member query reads at most eleven rows to enforce the hard
  ten-member invariant and rejects a result larger than ten.
- The canonical Universe model revalidates strategy group, Event, sorted member
  set, and semantic digest before market I/O.
- A warm proof binds scope version, Event, instrument, Universe version,
  Universe semantic digest, immutable Fact digest, ready time, and validity.
- Missing, incomplete, stale, future-dated, duplicate, or identity-inconsistent
  facts cannot produce warm readiness.
- A failed warming observation clears any prior `warm_*` projection; an older
  retry cannot overwrite or clear a newer proof.
- Warm persistence uses an exact PostgreSQL identity guard. A scope lifecycle,
  version, digest, instrument, or permission change during market I/O prevents
  persistence.
- Market I/O occurs after the authority-read transaction closes.
- Warming creates zero Signal, Ticket, and Exchange Command rows.

## RED Evidence

### Typed readiness

Command:

```text
uv run pytest -q \
  tests/trading_kernel/unit/test_observe_strategy_scope.py::test_warm_readiness_digest_is_bound_to_universe_version_and_digest
```

Valid RED:

```text
1 failed
AssertionError: observe_strategy_scope had no build_warm_readiness
```

### Disposable PostgreSQL warming

Command:

```text
uv run pytest -q \
  tests/trading_kernel/integration/test_universe_warming.py::test_all_warming_members_become_ready_without_signal_chain -x
```

Valid RED:

```text
1 failed
actual first.status.value == "invalid"
expected "warmed"
```

The current use case rejected a valid warming scope before market I/O, which
was the missing Task 8 behavior.

## GREEN Evidence

The first PostgreSQL GREEN used the same command and returned:

```text
1 passed in 1.15s
```

That case also made `PostgresSignalRepository.add` forbidden, asserted no open
PostgreSQL transaction during typed market reads, required both installed
members to obtain their own readiness, and asserted:

```text
Signal = 0
Ticket = 0
Exchange Command = 0
Facts current = 6
```

Additional disposable PostgreSQL cases prove:

- one of two scopes ready is not an all-member-ready set;
- comparative warming is blocked when one exact Universe member lacks market
  data and succeeds only after all member data is present;
- missing or stale closed-market input clears prior readiness;
- changed Universe version/digest cannot overwrite a valid readiness;
- a crashed claim remains unavailable before lease expiry and is reclaimed
  exactly at expiry without a Signal;
- active scopes still produce normal no-signal, signal, duplicate, timeout,
  and six-Event outcomes.

## Final Focused Verification

Command:

```text
uv run pytest -q \
  tests/trading_kernel/unit/test_observe_strategy_scope.py \
  tests/trading_kernel/integration/test_universe_warming.py \
  tests/trading_kernel/integration/test_observation_to_signal.py \
  tests/trading_kernel/integration/test_strategy_universe_repository.py::test_install_inserts_one_complete_warming_universe_and_reads_sorted \
  tests/trading_kernel/integration/test_universe_certification_worker.py
```

Result:

```text
19 passed in 12.65s
```

Focused static verification:

```text
uvx ruff check --select E4,E7,E9,F,I <Task 8 source and test files>
All checks passed!

uv run --with mypy mypy --follow-imports=skip \
  src/trading_kernel/application/observe_strategy_scope.py \
  src/trading_kernel/infrastructure/pg_signal_repository.py
Success: no issues found in 2 source files

git diff --check
exit 0
```

## Second Review Fix — Same-Bar Observation Generation

The first review fix still allowed equal timestamps. Two workers observing the
same closed bar could both satisfy the `updated_at_ms <= trigger` predicate, so
an older same-bar success could restore a proof after a newer invalid result,
or an older same-bar failure could clear a newer valid proof.

Two concurrent disposable PostgreSQL tests reproduced both directions before
the fix:

```text
test_same_bar_old_success_cannot_resurrect_after_new_invalid
Failed: DID NOT RAISE RuntimeError

test_same_bar_old_failure_cannot_clear_new_success
Failed: DID NOT RAISE RuntimeError
```

Each runtime scope now owns a nonnegative, monotonic
`observation_generation`. Worker claim increments it atomically and carries
the generation into `ObservationRequest`; direct application observations use
the same repository claim operation. `WarmReadiness`, its digest, save CAS,
and clear CAS all bind that exact generation.

Consequently, two attempts with the same Event close still have distinct
generations. Once the newer attempt claims generation `g + 1`, any save or
clear from generation `g` fails. Because Fact upsert, warm projection CAS, and
readiness projection update share one PostgreSQL transaction, the stale
attempt's Fact/readiness changes roll back together. The concurrent tests
compare the complete scope warm projection, readiness row, and current Fact
rows before and after the rejected stale attempt.

Lease scheduling uses the same generation fence in addition to worker identity.
This prevents an expired attempt from releasing or rescheduling a lease that a
later generation obtained under the same stable worker id.

The existing observation-time CAS remains as a second monotonic guard for
out-of-order closed bars. Scope identity, lifecycle, permission, Universe
version/digest, generation, and observation time must all agree.

Second-review focused gate:

```text
46 passed in 31.62s

Ruff E4/E7/E9/F/I: All checks passed!
Mypy focused 5 source files: Success, no issues found
git diff --check: exit 0
```

The gate covers Task 8 unit/integration behavior, active Observation behavior,
Universe schema and repository migration behavior, entry-preflight scope model
construction, and detector replay parity. Task 9's O(N) test remains a valid
RED: each of eight members is still read eight times for one MPG closed bar.

Per parent scope, no broad full-suite, Tokyo, production, systemd, deployment,
or exchange check was run.

## Final Boundary

Task 8 stops with per-scope warm readiness. It does not activate a Universe,
switch current pointers, enable Entry, replay a warming trigger, call
certification, create a Signal for a warming scope, or implement Task 10.

## Independent Review Fix — Causal Fencing And Drift Cleanup

The independent review found three Task 8 defects. They were fixed before any
Task 9 production implementation.

### Monotonic warm projection

A real PostgreSQL RED proved that an old successful observation could restore
`warm_*` after a later invalid observation had cleared it:

```text
test_old_warm_success_cannot_resurrect_after_later_invalid_clear
Failed: DID NOT RAISE RuntimeError
```

Both `save_warm_readiness` and `clear_warm_readiness` now use the scope row's
`updated_at_ms` as the shared monotonic observation-time CAS. A successful
write advances `updated_at_ms`; an older worker can therefore neither restore
an invalidated proof nor clear a newer successful proof.

The clear fence also binds the exact runtime scope, scope version, Event,
instrument, Universe version, Universe semantic digest, and warming lifecycle.
It deliberately does not require valid warming permissions, so an exactly
identified warming row with corrupted permissions can clear its own stale
proof. A mismatched scope identity remains rejected.

### Fail-closed warming drift

A parameterized disposable PostgreSQL RED first warmed a scope and then
introduced Event, Registry contract, or permission drift. The Event case
demonstrated the defect:

```text
test_identified_warming_scope_drift_clears_prior_readiness[event]
assert not True
```

Every early fail-closed return after an exact warming scope is identified now
clears its prior warm projection. The permission case intentionally removes
the disposable database's lifecycle-permission check before corrupting the row;
this proves application-level fail-closed behavior without weakening the
production schema invariant.

### Active retry semantics

A real PostgreSQL worker RED injected a detector `RuntimeError` into an active
scope:

```text
expected RETRY_SCHEDULED
actual OBSERVED / warm_facts_invalid
```

Detector exception conversion is now limited to warming. Active detector
exceptions propagate to the existing worker boundary, which schedules a retry
and writes no `warm_facts_invalid` readiness projection.

### Review-fix verification

Focused Task 8 verification:

```text
uv run pytest -q \
  tests/trading_kernel/unit/test_observe_strategy_scope.py \
  tests/trading_kernel/integration/test_universe_warming.py \
  tests/trading_kernel/integration/test_observation_to_signal.py -x

22 passed in 16.62s
```

Task 9 remained RED and its production behavior was not implemented:

```text
test_eight_mpg_scopes_read_each_member_once_per_closed_bar
expected each of 8 members to be read once
actual each member was read 8 times
```

Static gates:

```text
uvx ruff check --select E4,E7,E9,F,I <Task 8 source/tests and Task 9 RED>
All checks passed!

uv run --with mypy mypy --follow-imports=skip \
  src/trading_kernel/application/observe_strategy_scope.py \
  src/trading_kernel/application/ports.py \
  src/trading_kernel/infrastructure/pg_signal_repository.py
Success: no issues found in 3 source files

git diff --check
exit 0
```
