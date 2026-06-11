# Runtime First Real Submit Attempt Ordering Fix - 2026-06-12

## Scope

This stage fixes the guarded API flow ordering for first-real-submit arm /
execute preparation.

It does not deploy, run a remote attempt mutation, call `OrderLifecycle`, call
exchange, create orders, submit orders, withdraw, or transfer funds.

## Finding

Tokyo disabled-smoke with the current authoritative submit authorization reached
controlled submit plan and protection plan, then stopped before handoff:

```text
authorization_id=runtime-submit-authorization-intent_rt_e8037454b07d3ab8cc5d8dd8
blocker=attempt_consumption_required_before_order_lifecycle_handoff
submit_executed=false
order_created=false
exchange_called=false
owner_bounded_execution_called=false
order_lifecycle_called=false
```

Code inspection showed a real ordering bug in:

```text
scripts/runtime_first_real_submit_api_flow.py
```

When `record_attempt_consumption=true`, the flow attempted to record
`runtime-execution-order-lifecycle-handoff-drafts` before recording the attempt
reservation / mutation / outcome policy. The server-side handoff service
requires an existing `RuntimeExecutionAttemptMutation`, so the executable path
would block before handoff.

## Fix

For explicitly enabled attempt consumption only, the flow now records:

```text
attempt reservation
-> attempt mutation
-> attempt outcome policy
-> machine evidence refresh
-> order lifecycle handoff draft
```

Default `arm` preview still stops before attempt consumption and does not mutate
attempts or budgets.

## Verification

```text
python3 -m py_compile scripts/runtime_first_real_submit_api_flow.py
pytest -q tests/unit/test_runtime_first_real_submit_api_flow.py tests/unit/test_runtime_first_real_submit_action_authorization_packet.py tests/unit/test_runtime_first_real_submit_final_review_packet.py
```

Result:

```text
25 passed
```

Updated tests prove:

- default arm preview still stops before attempt consumption;
- explicit attempt consumption records mutation before handoff;
- a handoff blocker after explicit attempt consumption does not proceed to local
  registration, exchange adapter, or first-real-submit action;
- execute still requires the exact
  `OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT` value.

## Tokyo State Checked

The active overnight observation loop remained non-executing:

```text
status=waiting_for_signal
active_runtime_count=2
prepare_records_created=false
exchange_write_called=false
order_created=false
order_lifecycle_called=false
attempt_counter_mutated=false
runtime_budget_mutated=false
withdrawal_or_transfer_created=false
```

No remote command with `--record-attempt-consumption` was run in this stage.

## Safety

This stage only makes the already-guarded execute/explicit-arm path internally
consistent. Real submit still requires:

- authoritative Tokyo PG submit authorization id;
- exact Owner confirmation value;
- `--execute-real-submit`;
- `OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT`;
- official Trading Console API path;
- no exchange/order/OrderLifecycle blockers.
