# Task 13 Checkpoint 1: Full-chain baseline convergence

Date: 2026-07-29
Scope: local disposable PostgreSQL and fake venue only

## Purpose

Before adding the Task 13 replacement, recovery, query-bound, and architecture
acceptance groups, converge the eight disclosed failures in the existing
`tests/trading_kernel/full_chain` baseline without restoring retired schema or
weakening current dispatch authority.

## RED evidence

Command:

```text
python3 -m pytest -q \
  tests/trading_kernel/full_chain/test_six_event_system_certification.py \
  tests/trading_kernel/full_chain/test_multi_position_certification.py
```

Result:

```text
8 failed in 8.13s
```

The failures were:

- six Event parameterizations attempted to insert the deleted
  `runtime_scopes_current.enabled` column;
- two multi-position parameterizations omitted the mandatory action-time ENTRY
  preflight inputs, so current dispatch correctly returned `SUPERSEDED`.

While converging those failures, the three-Ticket case exposed one additional
retired fixture assumption: one `universe_version_id` was reused across two
different Event specifications, violating the current unique Universe identity
contract.

## GREEN changes

The six-Event full chain now starts from current production boundaries:

```text
seed runtime authority
-> configure StrategyUniverse
-> immutable install
-> readonly instrument certification
-> warming Observation
-> automatic activation
-> active Observation / Signal
-> Claim / Ticket / durable ENTRY
-> fill and protected lifecycle
-> Settlement / Review
```

The multi-position full chain now supplies:

- current runtime commit and schema identity;
- enabled `exchange_commands` capability;
- active Universe authority;
- fresh admission snapshot and instrument rules;
- the existing preflight path before each ENTRY venue mutation.

No production source or migration was changed. No retired column, fallback,
compatibility adapter, alternate producer, or new exchange mutation kind was
added.

## Fresh verification

Complete full-chain suite:

```text
python3 -m pytest -q tests/trading_kernel/full_chain
32 passed in 29.59s
```

Focused static checks:

```text
uvx --from 'ruff>=0.15.0' ruff check \
  --select E4,E7,E9,F,I,UP037 \
  tests/trading_kernel/full_chain/test_six_event_system_certification.py \
  tests/trading_kernel/full_chain/test_multi_position_certification.py
All checks passed!
```

Additional gates:

- `python3 -m py_compile` on both changed tests: passed;
- `git diff --check`: passed.

## Remaining Task 13 scope

This checkpoint does not claim Task 13 completion. The dedicated Universe
replacement full chain, injected failure recovery, 10/70 query bounds,
`EXPLAIN`, architecture audit, `certify_readonly.py` extension, and complete
Trading Kernel/static verification remain to be implemented.
