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
first_real_submit_action_context.submit_authorization_id_source
first_real_submit_action_context.submit_authorization_id_authoritative_for_remote_execution
```

When the id is inferred from owner-packet rehearsal evidence, it is a hint only
and is not authoritative for remote execution.

The new action authorization packet:

- reads the final review packet;
- requires an explicit submit authorization id, unless a future packet marks
  its action-context id authoritative for remote execution;
- carries a non-authoritative authorization id hint when present;
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
status=blocked_before_first_real_submit_action_authorization
ready_for_owner_action_authorization=false
action_authorized=false
authorization_id=null
authorization_id_hint=runtime-submit-authorization-intent_rt_1d7d7a346233063607e711f5
blocker=submit_authorization_id_missing_for_action_plan
```

The rehearsal-derived hint is not used for command generation.

When an explicit authoritative Tokyo PG submit authorization id is supplied,
the packet can produce a command preview while still requiring a separate Owner
confirmation value. Example generated with the latest Tokyo PG authorization:

```text
authorization_id=runtime-submit-authorization-intent_rt_e8037454b07d3ab8cc5d8dd8
status=waiting_for_owner_first_real_submit_action_authorization
ready_for_owner_action_authorization=true
action_authorized=false
OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT=runtime-submit-authorization-intent_rt_e8037454b07d3ab8cc5d8dd8:first-real-submit:real_gateway_action
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

## Follow-up Correction

Tokyo disabled-smoke probing showed that the rehearsal-derived authorization id
is not necessarily present in the deployed PG fact set. The action packet must
therefore treat rehearsal-inferred ids as non-authoritative hints and require an
explicit authoritative authorization id before command previews can be used for
remote action.

Remote evidence:

```text
/home/ubuntu/brc-deploy/reports/first-real-submit-disabled-action-smoke/20260612Taction-auth-e778/disabled-first-real-submit-smoke.json
```

Result:

```text
authorization_id=runtime-submit-authorization-intent_rt_1d7d7a346233063607e711f5
status=blocked
blocker=hydrate_controlled_submit_plan_http_404
```

The endpoint existed; the id was not present in current Tokyo PG controlled
submit facts.

Authoritative Tokyo PG fact check found latest submit authorization:

```text
authorization_id=runtime-submit-authorization-intent_rt_e8037454b07d3ab8cc5d8dd8
runtime_instance_id=strategy-runtime-95655873b76c
symbol=AVAX/USDT:USDT
side=short
strategy_family_id=BTPC-001
strategy_family_version_id=BTPC-001-v0
candidate_shadow_mode=true
candidate_not_order=true
candidate_not_execution_intent=true
candidate_execution_enabled=false
submit_executed=false
order_created=false
exchange_called=false
order_lifecycle_called=false
```

Disabled first-real-submit smoke with that authoritative id:

```text
/home/ubuntu/brc-deploy/reports/first-real-submit-disabled-action-smoke/20260612Taction-auth-e778-authoritative/disabled-first-real-submit-smoke.json
```

Result:

```text
mode=arm
ready_for_real_submit_action=false
blocker=attempt_consumption_required_before_order_lifecycle_handoff
hydrated_controlled_submit_plan=true
recorded_protection_plan=true
first_real_submit_action_endpoint_called=false
submit_executed=false
order_created=false
exchange_called=false
owner_bounded_execution_called=false
order_lifecycle_called=false
```

The smoke stayed inside the authorized non-executing boundary. It did not reach
the disabled first-real-submit action wrapper because arm preview stopped before
OrderLifecycle handoff without attempt consumption.
