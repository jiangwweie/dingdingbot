# Runtime Local Registration Guard Tokyo Evidence - 2026-06-12

## Scope

This stage deployed the script-level local-registration confirmation guard to
Tokyo and verified it with the authoritative current submit authorization.

It does not authorize, execute, or imply:

- exchange submit adapter arm;
- first-real-submit action;
- real exchange order placement;
- `OrderLifecycle` submit;
- withdrawal or transfer.

## Deployed Release

Worktree:

```text
/Users/jiangwei/Documents/final-sprint6-integration
```

Branch:

```text
program/live-safe-v1
```

Deployed commit:

```text
0fdc00380dba231a51ee8a5cc45935b0e354f795
```

Tokyo release:

```text
/home/ubuntu/brc-deploy/releases/brc-runtime-governance-0fdc0038-20260612Tlocal-registration-guard
```

Deploy result:

```text
status=applied
commands_executed=16
commands_planned=16
database_backup_created=true
migrations_run=true
services_restarted=true
exchange_called=false
execution_intent_created=false
order_created=false
order_lifecycle_called=false
```

Postdeploy verification:

```text
status=postdeploy_acceptance_passed
blockers=[]
```

## Guard Behavior

`runtime_first_real_submit_api_flow.py` now requires the exact environment
confirmation before an `arm` flow can continue into attempt consumption or local
order registration:

```text
OWNER_APPROVED_RUNTIME_LOCAL_REGISTRATION_PREP=
<authorization_id>:attempt-local-registration:no-exchange-submit
```

This guard is separate from the real first-submit guard:

```text
OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT=
<authorization_id>:first-real-submit:real_gateway_action
```

The local-registration guard only covers the intermediate prep action. It does
not authorize first-real-submit or exchange order placement.

## Tokyo Guard Smoke

Command shape tested on Tokyo:

```text
runtime_first_real_submit_api_flow.py
  --mode arm
  --authorization-id runtime-submit-authorization-intent_rt_e8037454b07d3ab8cc5d8dd8
  --record-attempt-consumption
  --skip-exchange-arm
```

No `OWNER_APPROVED_RUNTIME_LOCAL_REGISTRATION_PREP` value was supplied.

Result:

```text
blocker=owner_runtime_local_registration_env_confirmation_missing
expected_OWNER_APPROVED_RUNTIME_LOCAL_REGISTRATION_PREP=
runtime-submit-authorization-intent_rt_e8037454b07d3ab8cc5d8dd8:attempt-local-registration:no-exchange-submit
```

The smoke stopped before:

```text
attempt reservation
attempt mutation
order lifecycle handoff draft
local registration action authorization
exchange submit adapter result
first-real-submit action
```

Remote evidence:

```text
/home/ubuntu/brc-deploy/reports/local-registration-guard-smoke/20260612T0fdc0038/arm-without-local-registration-confirmation.json
```

## Authorization Packet

Tokyo generated the local-registration authorization packet from the latest
disabled-smoke evidence:

```text
/home/ubuntu/brc-deploy/reports/local-registration-authorization-packet/20260612T0fdc0038/local-registration-auth-packet.json
```

Result:

```text
status=waiting_for_owner_local_registration_authorization
ready=true
authorized=false
blockers=[]
authorized_command_available=false
required_value=runtime-submit-authorization-intent_rt_e8037454b07d3ab8cc5d8dd8:attempt-local-registration:no-exchange-submit
```

The packet correctly marks the next action as unavailable until the exact Owner
confirmation value is supplied out of band.

## Safety Check

Authoritative submit authorization after deploy and guard smoke:

```text
authorization_id=runtime-submit-authorization-intent_rt_e8037454b07d3ab8cc5d8dd8
submit_executed=false
order_created=false
exchange_called=false
owner_bounded_execution_called=false
order_lifecycle_called=false
```

Observation loop after deploy:

```text
release=brc-runtime-governance-0fdc0038-20260612Tlocal-registration-guard
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

## Current Boundary

The next controlled step is not real submit.

The next possible Owner decision is whether to authorize:

```text
attempt reservation
attempt mutation
attempt outcome policy
order lifecycle handoff draft
local registration action authorization
local registration enablement preview
local order registration result
```

That action still excludes:

```text
exchange submit adapter arm
first-real-submit action
real exchange order placement
OrderLifecycle submit
withdrawal or transfer
```

Until the exact `OWNER_APPROVED_RUNTIME_LOCAL_REGISTRATION_PREP` value is
supplied, the script blocks before attempt or budget mutation.
