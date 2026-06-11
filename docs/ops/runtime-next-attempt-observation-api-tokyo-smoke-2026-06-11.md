# Runtime Next-attempt Observation API Tokyo Smoke - 2026-06-11

## Scope

This note records deployment and Tokyo smoke verification for the
runtime-scoped next-attempt observation API:

```text
POST /api/trading-console/strategy-runtimes/{runtime_instance_id}/next-attempt-observation-cycle
```

The API is an Owner/operator observation entry. It checks the runtime
next-attempt lifecycle gate and evaluates fresh strategy signal input. It does
not create prepare records, shadow candidates, `ExecutionIntent` records,
orders, or exchange writes.

## Deployment

- Worktree: `/Users/jiangwei/Documents/final-sprint6-integration`
- Branch: `program/live-safe-v1`
- Deployed head: `541cb0326909430fa46a48595d07f661aecb9b35`
- Release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-541cb032-20260611Tobscycleapi`
- Previous release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c0710ae1-20260611Tobscycle`
- Backup:
  `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-541cb032-20260611Tobscycleapi.pgdump`

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

## API Smoke

Target:

```text
runtime=strategy-runtime-95655873b76c
symbol=AVAX/USDT:USDT
strategy=BTPC-001 / BTPC-001-v0
request={source: live_market, include_exchange: true, non_executing: true}
```

Remote artifacts:

```text
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-observation-cycle-api/avax-btpc-api-smoke.json
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-observation-cycle-api/avax-btpc-api-prepare-flag-reject.json
```

Observed result:

```text
http_status=200
cycle_status=waiting_for_signal
blocked_stage=strategy_signal
gate_status=clear_for_preflight
signal_status=observe_only
signal_eval_status=observe_only
creates_shadow_candidate=false
creates_execution_intent=false
order_created=false
exchange_write_called=false
next_step=observe_only_or_wait_for_next_closed_bar
```

Prepare-record flag rejection:

```text
request.allow_prepare_records=true
http_status=400
message=next-attempt observation API is non-executing; use the official runtime_next_attempt_prepare_api_flow after ready_for_prepare
```

## Decision

The Tokyo API smoke is accepted.

The runtime lifecycle is clear for next-attempt preflight, but current market
facts still do not satisfy BTPC entry semantics. The correct product behavior
is to wait for the next closed-bar observation and not force candidate
planning.

## Safety Invariants

- No real submit was authorized or attempted.
- No prepare records were created by this API.
- No shadow candidate was created.
- No `ExecutionIntent` was created.
- No `OrderLifecycle` call occurred.
- No exchange write occurred.
- No order was created.
- No attempt counter or runtime budget was mutated by the observation API.
- No withdrawal or transfer instruction was created.
