# Runtime Observation Monitor Output JSON Tokyo Smoke

Date: 2026-06-11

## Scope

This record captures the stage that made
`scripts/runtime_next_attempt_observation_monitor.py` write an explicit JSON
report file with `--output-json` while keeping stdout as JSON.

The change supports auditable repeated runtime observation. It does not create
execution authority or submit orders.

## Branch And Commit

```text
branch=program/live-safe-v1
commit=6a721b36 feat(ops): let runtime observation monitor write json reports
```

## Verification

Local commands:

```text
python3 -m py_compile scripts/runtime_next_attempt_observation_monitor.py
pytest -q tests/unit/test_runtime_next_attempt_observation_monitor.py
pytest -q tests/unit/test_runtime_next_attempt_observation_monitor.py tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py tests/unit/test_runtime_next_attempt_observation_cycle.py tests/unit/test_runtime_next_attempt_observation_cycle_api.py tests/unit/test_runtime_next_attempt_prepare_api_flow.py
```

Results:

```text
6 passed
26 passed
```

## Tokyo Deployment

Release:

```text
/home/ubuntu/brc-deploy/releases/brc-runtime-governance-6a721b36-20260611Tmonitor-output-json
```

Current symlink:

```text
/home/ubuntu/brc-deploy/app/current -> /home/ubuntu/brc-deploy/releases/brc-runtime-governance-6a721b36-20260611Tmonitor-output-json
```

Deploy report:

```text
output/tokyo-deploy-6a721b36/git-deploy-apply-report.json
```

Deploy effects:

```text
database_backup_created=true
migrations_run=true
services_restarted=true
exchange_called=false
execution_intent_created=false
order_created=false
order_lifecycle_called=false
secrets_read_by_codex=false
```

Service check:

```text
brc-owner-console-backend.service active
GET /api/health -> {"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}
```

## Tokyo Smoke

Runtime:

```text
strategy-runtime-95655873b76c
BTPC-001 / BTPC-001-v0
AVAX/USDT:USDT short
```

Reports:

```text
/home/ubuntu/brc-deploy/reports/runtime-live-next-attempt-observation/20260611Tmonitor-output-json/live-monitor-once.json
/home/ubuntu/brc-deploy/reports/runtime-live-next-attempt-observation/20260611Tmonitor-output-json/live-monitor-stdout.json
```

Result:

```text
file_equals_stdout=true
status=waiting_for_signal
ready_for_prepare=false
ready_for_final_gate_preflight=false
blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"]
exchange_write_called=false
order_created=false
order_lifecycle_called=false
attempt_counter_mutated=false
runtime_budget_mutated=false
prepare_records_created=false
```

Interpretation:

The monitor is now suitable for an auditable repeated observation run. The live
BTPC runtime still has no current entry signal, so no shadow candidate, prepare
record, order, OrderLifecycle call, runtime budget mutation, or exchange write
was created.

