# Runtime Active Observation Monitor Tokyo Smoke - 2026-06-12

## Scope

Owner authorized overnight non-executing observation and prepare for currently
ACTIVE strategy runtimes.

Allowed:

- live read-only observation for current ACTIVE runtimes;
- shadow `SignalEvaluation` / shadow `OrderCandidate` / prepare authorization
  records only when a real strategy signal becomes ready for prepare;
- `FinalGate` preview, arm preview, and disabled first-real-submit smoke.

Forbidden:

- real exchange order;
- `OrderLifecycle` submit;
- executable first-real-submit;
- withdrawal or transfer.

## Local Stage

- Worktree: `/Users/jiangwei/Documents/final-sprint6-integration`
- Branch: `program/live-safe-v1`
- Commit: `6f7ea48bed0199b570e2ffdb614c737230db2d4c`
- Commit message: `feat(ops): monitor active runtimes for next attempts`

Verification:

```text
python3 -m py_compile scripts/runtime_active_observation_monitor.py scripts/runtime_next_attempt_observation_monitor.py
pytest -q tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_runtime_next_attempt_observation_monitor.py tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py tests/unit/test_runtime_next_attempt_observation_cycle.py tests/unit/test_runtime_next_attempt_observation_cycle_api.py tests/unit/test_runtime_next_attempt_prepare_api_flow.py
```

Result:

```text
30 passed
```

## Tokyo Deploy

- Previous release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-6a721b36-20260611Tmonitor-output-json`
- New release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-6f7ea48b-20260612Tactive-monitor`
- Current deployed head:
  `6f7ea48bed0199b570e2ffdb614c737230db2d4c`
- Migration count: `84`
- Latest migration:
  `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`
- Backend service: `active`
- Health endpoint:
  `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`
- Postdeploy status: `postdeploy_acceptance_passed`

Deployment effects:

```text
database_backup_created=true
migrations_run=true
services_restarted=true
exchange_called=false
execution_intent_created=false
order_created=false
order_lifecycle_called=false
withdrawal_or_transfer_created=false
```

## Active Monitor Smoke

Command class:

```text
scripts/runtime_active_observation_monitor.py --source live_market --allow-prepare-records
```

Observed ACTIVE runtimes:

```text
strategy-runtime-95655873b76c AVAX/USDT:USDT short BTPC-001/BTPC-001-v0
strategy-runtime-e6138ad7c88f BNB/USDT:USDT long CPM-001/CPM-001-v0
```

Smoke result:

```text
status=waiting_for_signal
active_runtime_count=2
monitored_runtime_count=2
prepare_records_created=false
exchange_write_called=false
order_created=false
order_lifecycle_called=false
attempt_counter_mutated=false
runtime_budget_mutated=false
withdrawal_or_transfer_created=false
```

Blockers:

```text
strategy-runtime-95655873b76c:strategy_signal_not_ready_for_shadow_candidate_prepare
strategy-runtime-e6138ad7c88f:strategy_signal_not_ready_for_shadow_candidate_prepare
```

## Overnight Loop

- Report root:
  `/home/ubuntu/brc-deploy/reports/runtime-active-observation-monitor/20260612Tovernight`
- Loop PID at start: `3831711`
- Interval: `300s`
- Max iterations: `96`
- Stop condition:
  - status changes away from `waiting_for_signal`; or
  - monitor process returns non-zero; or
  - max iterations exhausted.

First verified loop status:

```text
process=running
status=waiting_for_signal
prepare_records_created=false
ready_for_final_gate_preflight=false
```

## Safety Note

This stage does not authorize or execute real submit. If a runtime becomes
ready for prepare overnight, the loop may create shadow/prepare records and
then stops for operator review. Real submit remains separately Owner-gated.

## Python Loop Replacement

Follow-up commit:

```text
451b68fdd5e76be146781ae9219e91186bc00609
feat(ops): add bounded active observation loop
```

Additional local verification:

```text
python3 -m py_compile scripts/runtime_active_observation_loop.py scripts/runtime_active_observation_monitor.py
pytest -q tests/unit/test_runtime_active_observation_loop.py tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_runtime_next_attempt_observation_monitor.py tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py tests/unit/test_runtime_next_attempt_observation_cycle.py tests/unit/test_runtime_next_attempt_observation_cycle_api.py tests/unit/test_runtime_next_attempt_prepare_api_flow.py
```

Result:

```text
33 passed
```

Tokyo was updated from:

```text
/home/ubuntu/brc-deploy/releases/brc-runtime-governance-6f7ea48b-20260612Tactive-monitor
```

to:

```text
/home/ubuntu/brc-deploy/releases/brc-runtime-governance-451b68fd-20260612Tactive-loop
```

Postdeploy status:

```text
postdeploy_acceptance_passed
service=active
health={"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}
```

The earlier ad-hoc shell loop was stopped:

```text
stopped_old_pid=3831711
```

The deployed Python loop smoke produced:

```text
status=waiting_for_signal
active_runtime_count=2
monitored_runtime_count=2
prepare_records_created=false
exchange_write_called=false
order_created=false
order_lifecycle_called=false
attempt_counter_mutated=false
runtime_budget_mutated=false
withdrawal_or_transfer_created=false
```

The durable Python overnight loop is now running:

```text
report_root=/home/ubuntu/brc-deploy/reports/runtime-active-observation-loop/20260612Tovernight-python
pid=3836605
interval_seconds=300
max_iterations=96
initial_status=waiting_for_signal
```
