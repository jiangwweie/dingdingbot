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

Per parent scope, no broad full-suite, Tokyo, production, systemd, deployment,
or exchange check was run.

## Final Boundary

Task 8 stops with per-scope warm readiness. It does not activate a Universe,
switch current pointers, enable Entry, replay a warming trigger, call
certification, create a Signal for a warming scope, or implement Task 10.
