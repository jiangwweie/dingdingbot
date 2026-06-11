# Runtime First-Real-Submit Attempt Handoff Safety Tokyo Smoke

Date: 2026-06-11

## Scope

This record captures the stage that keeps the runtime first-real-submit API
flow from consuming a runtime attempt before the OrderLifecycle handoff draft
has cleared.

This was a safety/ordering correction only. It did not authorize a live
exchange submit.

## Code

- Branch: `program/live-safe-v1`
- Commit: `a7c56da4 fix(runtime): defer attempt mutation until handoff draft clears`

Changed behavior:

- explicit arm / execute flow records the OrderLifecycle handoff draft before
  applying attempt mutation;
- attempt reservation, mutation, and outcome-policy recording stop immediately
  when blockers appear;
- default arm preview still stops before handoff and does not consume attempts.

## Local Verification

Commands:

```text
python3 -m py_compile scripts/runtime_first_real_submit_api_flow.py
pytest -q tests/unit/test_runtime_first_real_submit_api_flow.py
pytest -q tests/unit/test_runtime_first_real_submit_api_flow.py tests/unit/test_runtime_next_attempt_observation_monitor.py tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py tests/unit/test_b0_strategy_runtime_fact_overlay.py
```

Results:

```text
13 passed
34 passed
```

## Tokyo Deployment

Release:

```text
/home/ubuntu/brc-deploy/releases/brc-runtime-governance-a7c56da4-20260611Tattempt-handoff-safe
```

Current symlink after deploy:

```text
/home/ubuntu/brc-deploy/app/current -> /home/ubuntu/brc-deploy/releases/brc-runtime-governance-a7c56da4-20260611Tattempt-handoff-safe
```

Deploy report:

```text
output/tokyo-deploy-a7c56da4/git-deploy-apply-report.json
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

## Arm Preview Smoke

Report:

```text
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-sample-prepare-disabled-submit/20260611Tattempt-handoff-safe/arm-preview.json
```

Result:

```text
mode=arm
ready_for_real_submit_action=false
blockers=["attempt_consumption_required_before_order_lifecycle_handoff"]
warnings=["next_attempt_gate_check_skipped_symbol_missing","attempt_consumption_not_recorded_in_arm_preview"]
handoff_called=false
attempt_reservation_called=false
attempt_mutation_called=false
first_real_submit_called=false
```

## Live Observation Smoke

Runtime:

```text
strategy-runtime-95655873b76c
BTPC-001 / BTPC-001-v0
AVAX/USDT:USDT short
```

Report:

```text
/home/ubuntu/brc-deploy/reports/runtime-live-next-attempt-observation/20260611Tafter-attempt-handoff-safe/live-monitor-once.json
```

Result:

```text
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

BTPC had no current entry signal. The monitor stayed observe-only and did not
create a shadow candidate, prepare authorization, order, OrderLifecycle call,
or exchange action.

