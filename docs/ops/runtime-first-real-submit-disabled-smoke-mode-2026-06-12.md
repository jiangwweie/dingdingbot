# Runtime First Real Submit Disabled Smoke Mode - 2026-06-12

## Scope

This stage adds a `disabled-smoke` mode to the guarded first-real-submit API
flow.

It is a non-executing action-wrapper reachability check. It does not prepare a
candidate, create a new submit authorization, consume an attempt, mutate
runtime budget, record local registration, arm the exchange adapter, call
`OrderLifecycle`, call exchange, create orders, submit orders, withdraw, or
transfer funds.

## Why

The default `arm` preview correctly stops before attempt consumption unless
`--record-attempt-consumption` is explicitly supplied. That is the right safety
boundary, but it means a disabled first-real-submit action smoke cannot reach
the action wrapper without doing attempt/budget mutation first.

The new mode lets Owner/Codex verify the first-real-submit action wrapper itself
with:

```text
owner_confirmed_for_first_real_submit_action=false
```

without entering the arm chain.

## Command Shape

```text
python3 scripts/runtime_first_real_submit_api_flow.py \
  --mode disabled-smoke \
  --authorization-id <authoritative_tokyo_pg_submit_authorization_id>
```

The mode calls only:

```text
POST /api/trading-console/runtime-execution-first-real-submit-actions/authorizations/{authorization_id}?owner_confirmed_for_first_real_submit_action=false
```

It does not set `--execute-real-submit` and does not require or consume
`OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT`.

## Verification

```text
python3 -m py_compile scripts/runtime_first_real_submit_api_flow.py
pytest -q tests/unit/test_runtime_first_real_submit_api_flow.py tests/unit/test_runtime_first_real_submit_action_authorization_packet.py tests/unit/test_runtime_first_real_submit_final_review_packet.py
```

Result:

```text
27 passed
```

Added tests prove:

- `disabled-smoke` requires an explicit authorization id;
- it calls the first-real-submit action wrapper with
  `owner_confirmed_for_first_real_submit_action=false`;
- it does not call attempt reservation / mutation / outcome policy;
- it does not call local registration authorization;
- it does not call exchange adapter result;
- `ready_for_real_submit_action=false`.

## Safety

This is a smoke/probe mode only. A real submit still requires:

- authoritative Tokyo PG submit authorization id;
- exact Owner confirmation value;
- `--mode execute`;
- `--execute-real-submit`;
- matching `OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT`;
- official action endpoint returning no blockers.
