# Runtime First Real Submit Action Authorization Packet - 2026-06-12

## Scope

This stage adds a non-executing action authorization packet after the first
real submit final review packet.

It is not a live submit. It does not call the Trading Console API, exchange,
`OrderLifecycle`, or any order registration path.

## Local Stage

- Worktree: `/Users/jiangwei/Documents/final-sprint6-integration`
- Branch: `program/live-safe-v1`
- Base head before stage: `7d64f733ef2c3eb71b2cc13f34deeba3bcc08835`

Added:

- `scripts/build_runtime_first_real_submit_action_authorization_packet.py`
- `tests/unit/test_runtime_first_real_submit_action_authorization_packet.py`

Updated:

- `scripts/build_runtime_first_real_submit_final_review_packet.py`
- `tests/unit/test_runtime_first_real_submit_final_review_packet.py`

## Behavior

The final review packet now carries:

```text
first_real_submit_action_context.submit_authorization_id
```

The new action authorization packet:

- reads the final review packet;
- inherits the submit authorization id when present;
- computes the exact required `OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT`
  value;
- emits disabled-smoke and execute command previews;
- stays `packet_build_only`;
- marks `action_authorized=false` until the exact Owner confirmation value is
  supplied out of band.

Generated local evidence:

```text
output/first-real-submit-action-authorization/20260612Taction-auth-e778/action-authorization-packet.json
```

Current generated status:

```text
status=waiting_for_owner_first_real_submit_action_authorization
ready_for_owner_action_authorization=true
action_authorized=false
authorization_id=runtime-submit-authorization-intent_rt_1d7d7a346233063607e711f5
```

Required future confirmation value if Owner chooses to run the official execute
step:

```text
OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT=runtime-submit-authorization-intent_rt_1d7d7a346233063607e711f5:first-real-submit:real_gateway_action
```

## Verification

```text
python3 -m py_compile scripts/build_runtime_first_real_submit_final_review_packet.py scripts/build_runtime_first_real_submit_action_authorization_packet.py
pytest -q tests/unit/test_runtime_first_real_submit_action_authorization_packet.py tests/unit/test_runtime_first_real_submit_final_review_packet.py tests/unit/test_runtime_first_real_submit_api_flow.py
```

Result:

```text
24 passed
```

Tokyo observation loop latest checked state during this stage:

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

## Safety

This stage does not authorize or execute:

- real runtime submit;
- exchange order placement;
- `OrderLifecycle` submit;
- local order registration;
- attempt or budget mutation;
- withdrawal or transfer.

Real submit remains a separate Owner action.
