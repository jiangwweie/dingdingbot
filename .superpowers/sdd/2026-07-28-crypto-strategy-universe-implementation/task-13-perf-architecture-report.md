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

It proves the exact production lifecycle rather than manufacturing rows: six
registered Events each go through `configure -> readonly certification ->
Observation warm-up -> advance`, then one Event receives a separately configured
ten-member warming replacement. The resulting shape has 60 active, warmed scopes
and 10 warming scopes, across six active Universe versions.

It then claims one scope through the real
`claim_next_observation_scope` repository call, captures that emitted SQL and
its real binds, and validates its PostgreSQL index reachability with that exact
statement under `EXPLAIN (FORMAT JSON)` and `enable_seqscan = off`. This is an
index-availability proof, not a timing benchmark; at the intended 70-row ceiling
PostgreSQL may validly prefer a sequential scan. It also instruments activation's
real SQL and proves every member/scope SELECT it emits uses the
`MAX_UNIVERSE_MEMBERS + 1` (11-row) cardinality guard.

The architecture audit proves:

- Registry has no candidate membership/rank fields and metadata has no legacy
  candidate-scope table.
- Runtime has no Universe priority, US-equity, correlation/clustering, or
  dynamic-downsize surface.
- Install, advance, certify, comparative-projection, and read-status application
  modules cannot import Ticket dispatch or venue-adapter paths and cannot invoke
  order or exchange-setting APIs.
- The precise Universe authority surface (application, Registry, PostgreSQL
  persistence/seed, and configure/read-status scripts) contains no legacy,
  compatibility, fallback, or dual-read/write path. The audit intentionally does
  not scan venue parsing, where non-authority parsing fallbacks are legitimate.
- The venue adapter imports no PostgreSQL layer; domain imports no infrastructure
  or operating-system client layer.
- Systemd remains the exact four Worker services plus its shared slice, and
  Universe application modules add no runtime file authority.

## RED / GREEN record

This is a final acceptance expansion over behaviors already implemented by
Tasks 8--10. The first executions of the new tests were GREEN, so this report
does not misrepresent them as a new production-behavior RED. No production
source was changed by this work.

During the review repair, the real lifecycle test first exposed an incorrect
test assumption: asyncpg returns the captured `EXPLAIN (FORMAT JSON)` result as
a one-element Python list, while the test treated it as a JSON string. The test
was corrected to consume the actual result shape while retaining the exact
production selector statement and binds. This is a test-harness RED/GREEN, not
a Kernel behavior change.

## Verification

Focused new acceptance:

```text
python3 -m pytest -q \
  tests/trading_kernel/integration/test_strategy_universe_query_bounds.py \
  tests/trading_kernel/architecture/test_strategy_universe_architecture.py
9 passed in 5.25s
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

Mypy is not green at repository scope. There are two distinct results:

- The focused two-file invocation imports existing dependencies and reports
  **23 baseline errors in 8 existing files**. After the raw-connection guard and
  fixture/literal annotations, the two Task 13 test files add no diagnostics of
  their own.
- `uvx --with-requirements requirements-dev.txt --from 'mypy>=1.16.0' mypy
  src/trading_kernel` reports **32 baseline errors in 11 source files** (85
  files checked). This includes existing `instrument_entry_health.py`,
  `account_entry_health.py`, `capacity.py`, `reducer.py`, runtime/recovery,
  PostgreSQL, and venue-adapter typing debt.

This Task does not hide, suppress, or misstate either baseline.

## Boundary confirmation

- Did not modify `scripts/trading_kernel/certify_readonly.py`.
- Did not modify `tests/trading_kernel/full_chain/test_crypto_universe_failure_recovery.py`.
- Did not touch `docs/current/*`.
- Did not use Tokyo PostgreSQL, systemd, production seed, Entry, or exchange
  mutation.
