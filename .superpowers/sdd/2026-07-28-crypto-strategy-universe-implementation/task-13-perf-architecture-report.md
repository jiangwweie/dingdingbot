# Task 13 Performance And Architecture Acceptance

Date: 2026-07-29
Scope: local disposable PostgreSQL, static source audit, no Tokyo or exchange writes.

## Delivered coverage

New files:

- `tests/trading_kernel/integration/test_strategy_universe_query_bounds.py`
- `tests/trading_kernel/architecture/test_strategy_universe_architecture.py`

The query-bound acceptance creates the actual maximum steady-state shape:

```text
6 Events x 10 active scopes
+ 1 warming replacement x 10 scopes
= 70 scopes
```

It proves one Observation cadence claims exactly one scope, and validates the
due-selector's PostgreSQL index reachability with `EXPLAIN (FORMAT JSON)` and
`enable_seqscan = off`. The latter is deliberately an index-availability proof,
not a timing benchmark; at the intended 70-row ceiling PostgreSQL may validly
prefer a sequential scan. It also instruments activation's real SQL and proves
all member/scope read selectors use the `MAX_UNIVERSE_MEMBERS + 1` (11-row)
cardinality guard.

The architecture audit proves:

- Registry has no candidate membership/rank fields and metadata has no legacy
  candidate-scope table.
- Runtime has no Universe priority, US-equity, correlation/clustering, or
  dynamic-downsize surface.
- Install/advance/comparative application modules cannot import Ticket dispatch
  or venue-adapter paths and cannot invoke order or exchange-setting APIs.
- The venue adapter imports no PostgreSQL layer; domain imports no infrastructure
  or operating-system client layer.
- Systemd remains the exact four Worker services plus its shared slice, and
  Universe application modules add no runtime file authority.

## RED / GREEN record

This is a final acceptance expansion over behaviors already implemented by
Tasks 8--10. The first executions of the new tests were GREEN, so this report
does not misrepresent them as a new behavioral RED. No production source was
changed by this work. The original behavior RED evidence remains in the Task
8--10 reports and their committed tests; the new tests expose regression gates
for the final Task 13 suite.

## Verification

Focused new acceptance:

```text
python3 -m pytest -q \
  tests/trading_kernel/integration/test_strategy_universe_query_bounds.py \
  tests/trading_kernel/architecture/test_strategy_universe_architecture.py
8 passed in 1.98s
```

Related performance, activation, fault, and architecture acceptance:

```text
python3 -m pytest -q \
  tests/trading_kernel/integration/test_universe_market_call_bounds.py \
  tests/trading_kernel/integration/test_comparative_universe_projection.py
11 passed in 10.38s

python3 -m pytest -q \
  tests/trading_kernel/integration/test_strategy_universe_activation.py \
  tests/trading_kernel/architecture
52 passed in 17.36s

python3 -m pytest -q \
  tests/trading_kernel/integration/test_strategy_universe_activation_faults.py
3 passed in 2.67s
```

Static gates:

```text
uvx --from 'ruff>=0.15.0' ruff check --select E4,E7,E9,F,I,UP037 \
  tests/trading_kernel/integration/test_strategy_universe_query_bounds.py \
  tests/trading_kernel/architecture/test_strategy_universe_architecture.py
All checks passed!

python3 -m py_compile [both new tests]
passed

git diff --check
passed
```

Mypy was not green at repository scope. Running it with the repository dev
requirements found 23 pre-existing errors in 8 imported existing files,
including `capacity.py`, `reducer.py`, `reconcile_leverage_command.py`,
`runtime_fence.py`, `pg_repositories.py`, `recover_unknown_command.py`,
`runtime_authority_seed.py`, and the shared universe test support. The two new
test files contributed no remaining Mypy diagnostics after their fixture and
literal annotations were tightened. This Task does not hide or suppress that
baseline type debt.

## Boundary confirmation

- Did not modify `scripts/trading_kernel/certify_readonly.py`.
- Did not modify `tests/trading_kernel/full_chain/test_crypto_universe_failure_recovery.py`.
- Did not touch `docs/current/*`.
- Did not use Tokyo PostgreSQL, systemd, production seed, Entry, or exchange
  mutation.
