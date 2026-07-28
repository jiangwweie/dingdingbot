# Task 13 Checkpoint 3: Readonly Universe integrity

Date: 2026-07-29
Scope: local disposable PostgreSQL only

## RED

A configured two-member warming Universe caused `certify_readonly.py` to fail
solely because the script still required `runtime_scope_count == 0`.

## GREEN

Readonly certification now reports and validates:

- Universe version, current pointer, member, and runtime scope counts;
- exact member-to-scope completeness;
- scope Event, semantic digest, and lifecycle agreement with its version;
- current pointer agreement with one active version;
- absence of an active version without its current pointer.

A coherent two-member warming Universe passes. Deleting one member Scope
produces exactly one integrity violation and fails closed.

## Fresh verification

```text
python3 -m pytest -q \
  tests/trading_kernel/integration/test_strategy_universe_scripts.py \
  tests/trading_kernel/integration/test_cutover_state_machine.py
34 passed in 12.66s
```

Focused Ruff, `py_compile`, and `git diff --check` passed.

This checkpoint does not claim complete Task 13 acceptance. Dedicated
replacement/failure/query/architecture files and the final complete suite
remain.
