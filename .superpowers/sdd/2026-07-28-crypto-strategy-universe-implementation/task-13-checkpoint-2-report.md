# Task 13 Checkpoint 2: Complete-suite authority convergence

Date: 2026-07-29
Scope: local disposable PostgreSQL only

## Full-suite RED inventory

The first complete Task 13 baseline run executed:

```text
python3 -m pytest -q \
  tests/trading_kernel/unit \
  tests/trading_kernel/integration \
  tests/trading_kernel/full_chain \
  tests/trading_kernel/architecture
```

Result:

```text
621 passed, 46 failed in 218.91s
```

The 46 failures reduced to four fixture/authority roots:

- 27 cutover tests still froze the retired `0001_initial` revision;
- 16 unknown-outcome tests attempted ENTRY or SET_LEVERAGE without the current
  action-time preflight inputs;
- two runtime selector tests inserted Tickets without their frozen Universe
  identity;
- one order-attribution repository test inserted a Ticket without its frozen
  Universe identity.

## TDD production correction

After the cutover tests were updated to the current revision, all 27 remained
RED because `CutoverPlan` itself rejected
`0002_crypto_strategy_universe`. This isolated a production validation gap.

The minimal production correction changes the cutover plan's only accepted
target revision from `0001_initial` to
`0002_crypto_strategy_universe`. No fallback or dual-revision compatibility was
added.

## Current-authority fixture corrections

- Unknown ENTRY and SET_LEVERAGE scenarios now first pass runtime identity,
  active Universe, capability, admission snapshot, and instrument-rule
  preflight. The fake venue timeout then creates the intended durable unknown
  outcome.
- Direct repository/selector tests install the Ticket's frozen Universe
  identity before inserting the Ticket.
- Cutover table count derives from current SQLAlchemy metadata rather than the
  retired 33-table count.
- Clean runtime authority correctly expects zero scopes before Owner Universe
  configuration.

## Fresh focused verification

```text
python3 -m pytest -q \
  tests/trading_kernel/integration/test_cutover_state_machine.py \
  tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py \
  tests/trading_kernel/integration/test_order_attribution_repository.py \
  tests/trading_kernel/integration/test_runtime_fact_workers.py
55 passed in 28.76s
```

Static gates:

- focused Ruff `E4,E7,E9,F,I,UP037`: passed;
- `python3 -m py_compile` on all five changed files: passed;
- `git diff --check`: passed.

This checkpoint does not claim complete Task 13 acceptance. Dedicated
replacement, failure-injection, query-bound, architecture, and final complete
suite gates remain.
