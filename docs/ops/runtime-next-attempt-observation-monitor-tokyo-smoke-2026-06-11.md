# Runtime Next-Attempt Observation Monitor Tokyo Smoke - 2026-06-11

Status: PASSED_WAITING_FOR_SIGNAL

## Scope

This smoke verifies the non-executing runtime next-attempt observation monitor
after deploying commit `dd12fe41` to Tokyo.

The monitor is an operator tool for the flat-after-close waiting period. It
does not authorize real submit, does not arm local registration, does not call
OrderLifecycle, and does not place exchange orders.

## Local Stage Commit

```text
branch=program/live-safe-v1
commit=dd12fe41b751114b5f0c5fff6ed7defc40e69eb9
message=feat(ops): monitor runtime next attempt observation
```

## Deployment

```text
release=/home/ubuntu/brc-deploy/releases/brc-runtime-governance-dd12fe41-20260611Tnext-attempt-monitor
previous_release=/home/ubuntu/brc-deploy/releases/brc-runtime-governance-b274ffb6-20260611Tdisabled-action-docs
deploy_status=applied
commands_executed=16
blockers=[]
```

Deployment effects:

```json
{
  "database_backup_created": true,
  "exchange_called": false,
  "execution_intent_created": false,
  "migrations_run": true,
  "order_created": false,
  "order_lifecycle_called": false,
  "remote_files_modified": true,
  "secrets_read_by_codex": false,
  "services_restarted": true
}
```

## Smoke Command

```bash
python scripts/runtime_next_attempt_observation_monitor.py \
  --env-file /home/ubuntu/brc-deploy/env/live-readonly.env \
  --api-base http://127.0.0.1:18080 \
  --runtime-instance-id strategy-runtime-95655873b76c \
  --symbol AVAX/USDT:USDT \
  --side short \
  --strategy-family-id BTPC-001 \
  --carrier-id BTPC-001-v0 \
  --source live_market \
  --include-exchange \
  --max-cycles 1
```

Report:

```text
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-observation-monitor/20260611Tnext-attempt-monitor/monitor-once.json
```

## Smoke Result

```text
status=waiting_for_signal
cycles_completed=1
ready_for_prepare=false
ready_for_final_gate_preflight=false
blockers=strategy_signal_not_ready_for_shadow_candidate_prepare
next_step=wait_for_next_observation_cycle
exchange_write_called=false
order_created=false
```

## Interpretation

The runtime is flat and eligible to keep observing, but the current live market
observation is not ready for a fresh shadow candidate. The correct next action
is to wait for another observation cycle or closed candle, not to reuse stale
authorization evidence.

No real submit authorization was consumed or implied by this smoke.

## Sample Rehearsal Check

A second non-executing sample-source check verified that the monitor can
surface a ready prepare state without creating prepare records by default.

Report:

```text
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-observation-monitor/20260611Tnext-attempt-monitor-sample/monitor-sample-once.json
```

Result:

```text
status=ready_for_prepare
ready_for_prepare=true
blockers=[]
next_step=rerun_with_allow_prepare_records_after_owner_review
creates_shadow_candidate=false
exchange_write_called=false
order_created=false
```

Interpretation:

```text
sample source can prove the ready-for-prepare branch;
default monitor mode still does not create shadow candidates or orders;
prepare record creation remains explicit via --allow-prepare-records.
```
