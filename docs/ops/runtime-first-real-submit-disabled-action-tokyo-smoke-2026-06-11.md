# Runtime First-real-submit Disabled Action Tokyo Smoke - 2026-06-11

## Scope

This note records Tokyo smoke verification for the official
first-real-submit action wrapper in disabled mode.

The goal was to prove that the Trading Console action endpoint is reachable
from the operator CLI with real Tokyo operator auth loaded from the deployment
environment, while keeping real exchange submit disabled.

## Deployment

- Worktree: `/Users/jiangwei/Documents/final-sprint6-integration`
- Branch: `program/live-safe-v1`
- Deployed head: `9587ab78f1f385d26080dd71e243117219638f3b`
- Release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-9587ab78-20260611Tdisabled-action-preview`
- Previous release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-5bab422d-20260611Tfinal-docs-align`
- Backup:
  `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-9587ab78-20260611Tdisabled-action-preview.pgdump`

Deploy effects:

```text
database_backup_created=true
migrations_run=true
services_restarted=true
remote_files_modified=true
exchange_called=false
execution_intent_created=false
order_created=false
order_lifecycle_called=false
secrets_read_by_codex=false
```

## CLI / Auth Smoke

Remote artifact:

```text
/home/ubuntu/brc-deploy/reports/runtime-first-real-submit-disabled-action/20260611T225202/inspect.json
```

Observed result:

```text
blockers=[]
warnings=[]
steps=[
  ("list_strategy_runtimes", 200),
  ("list_order_candidates", 200)
]
```

This verifies `scripts/runtime_first_real_submit_api_flow.py --env-file ...`
can load Tokyo operator auth for the official Trading Console API.

## Disabled Action Wrapper Smoke

Remote artifact:

```text
/home/ubuntu/brc-deploy/reports/runtime-first-real-submit-disabled-action/20260611T225244-arm-disabled/arm-disabled-action-preview.json
```

Target authorization:

```text
authorization_id=runtime-submit-authorization-intent_rt_6ca3cecd63fafbd1d25760df
runtime=strategy-runtime-95655873b76c
symbol=AVAX/USDT:USDT
strategy=BTPC-001 / BTPC-001-v0
```

Observed action-wrapper result:

```text
step=preview_disabled_first_real_submit_action
http_status=200
status=exchange_submit_execution_disabled
execution_result_id=runtime-exchange-submit-execution-result-runtime-submit-authorization-intent_rt_6ca3cecd63fafbd1d25760df
ready_for_real_submit_action=false
```

The wrapper was reachable and returned the expected disabled execution result.

The existing authorization is not a clean real-submit candidate:

```text
trusted_submit_fact_snapshot_not_ready
trusted_submit_fact_snapshot_not_fresh_enough
local_registration_enablement_decision_not_ready
local_order_status_not_created
local_order_exchange_artifact_present
exchange_submit_packet_preview_not_ready
exchange_submit_action_authorization_not_approved
exchange_submit_gate_not_ready
exchange_submit_enablement_decision_not_ready
runtime_execution_enabled_false_current_shadow_boundary
runtime_shadow_mode_current_boundary
```

These blockers are accepted. They prevent stale or shadow-boundary evidence
from being reused as real-submit authority.

## Fresh Observation Check

Remote artifact:

```text
/home/ubuntu/brc-deploy/reports/runtime-first-real-submit-disabled-action/20260611T225351-fresh-observation/observation-prepare-default.json
```

Observed result:

```text
flow_status=waiting_for_signal
blocked_stage=strategy_signal
observation_http_status=200
prepare_packet=false
blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"]
next_step=observe_only_or_wait_for_next_closed_bar
```

This means the current live market observation does not produce a fresh
`ready_for_prepare` candidate. The correct behavior is to wait for the next
closed-bar opportunity rather than force the old authorization toward submit.

## Decision

Accepted.

The official first-real-submit action wrapper is deployed and reachable in
disabled mode. The current old BTPC authorization is correctly blocked by stale
facts and shadow-boundary evidence. The next real progression should start from
a fresh `ready_for_prepare` observation, then use the official prepare / arm /
FinalGate / first-real-submit action path.

## Safety Invariants

- No `--execute-real-submit` flag was used.
- No `OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT` env confirmation was set.
- The first-real-submit action wrapper was called with
  `owner_confirmed_for_first_real_submit_action=false`.
- Exchange execution returned `exchange_submit_execution_disabled`.
- No exchange order was submitted.
- No withdrawal or transfer instruction was created.
