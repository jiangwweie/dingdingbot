# Runtime Observation API Prepare Flow Tokyo Smoke - 2026-06-11

## Scope

This note records deployment and Tokyo smoke verification for:

```text
scripts/runtime_next_attempt_observation_api_prepare_flow.py
```

The script bridges the runtime-scoped observation API to the official
`runtime_next_attempt_prepare_api_flow`. Its default mode only calls the
observation API and writes embedded signal input JSON. It creates prepare
records only with `--allow-prepare-records`, and only after the observation API
returns `ready_for_prepare`.

## Deployment

- Worktree: `/Users/jiangwei/Documents/final-sprint6-integration`
- Branch: `program/live-safe-v1`
- Deployed head: `9a1c70279f6ce7b3ec6b2f2d3ffa882453199894`
- Release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-9a1c7027-20260611Tobsapiprepare`
- Previous release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-541cb032-20260611Tobscycleapi`
- Backup:
  `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-9a1c7027-20260611Tobsapiprepare.pgdump`

Git deploy result:

```text
status=applied
commands_executed=16
database_backup_created=true
migrations_run=true
services_restarted=true
exchange_called=false
execution_intent_created=false
order_created=false
order_lifecycle_called=false
```

## Tokyo Smoke

Target:

```text
runtime=strategy-runtime-95655873b76c
symbol=AVAX/USDT:USDT
strategy=BTPC-001 / BTPC-001-v0
source=live_market
include_exchange=true
```

Remote artifacts:

```text
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-observation-api-prepare-flow/avax-btpc-default-flow.json
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-observation-api-prepare-flow/avax-btpc-signal-input.json
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-observation-api-prepare-flow/avax-btpc-allow-prepare-observe-only.json
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-observation-api-prepare-flow/avax-btpc-signal-input-allow-prepare.json
```

Default-mode result:

```text
flow_status=waiting_for_signal
blocked_stage=strategy_signal
observation_http_status=200
signal_input_json=/home/ubuntu/brc-deploy/reports/runtime-next-attempt-observation-api-prepare-flow/avax-btpc-signal-input.json
signal_input_exists=true
prepare_packet=false
prepare_records_created=false
order_created=false
exchange_write_called=false
order_lifecycle_called=false
next_step=observe_only_or_wait_for_next_closed_bar
observation_status=waiting_for_signal
signal_status=observe_only
signal_eval_status=observe_only
```

Explicit allow-prepare in observe-only state:

```text
allow_prepare_records=true
flow_status=waiting_for_signal
blocked_stage=strategy_signal
prepare_packet=false
prepare_records_created=false
order_created=false
exchange_write_called=false
```

## Decision

The Tokyo smoke is accepted.

The deployed bridge reaches the observation API, persists the embedded signal
input for operator review, and does not create prepare records while the
strategy signal remains `observe_only`. When a future closed-bar observation
returns `ready_for_prepare`, the same bridge can be rerun with
`--allow-prepare-records` to use the existing official prepare flow.

## Safety Invariants

- No real submit was authorized or attempted.
- No prepare records were created in the current observe-only state.
- No shadow candidate was created.
- No `ExecutionIntent` was created.
- No `OrderLifecycle` call occurred.
- No exchange write occurred.
- No order was created.
- No attempt counter or runtime budget was mutated.
- No withdrawal or transfer instruction was created.
