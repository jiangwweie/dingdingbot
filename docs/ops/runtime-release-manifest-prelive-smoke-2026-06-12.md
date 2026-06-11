# Runtime Release Manifest Pre-live Smoke - 2026-06-12

## Scope

Tokyo releases are deployed from `git archive`, so the release directory does
not contain `.git`. The pre-live verifier now falls back to
`.brc-release-manifest.json` for release identity.

This keeps current-head deployment readiness verifiable from the deployed
release itself.

## Local Commit

```text
e778f0ced812edfd687074793b8866c4b94be45f
fix(ops): read pre-live release identity from manifest
```

Focused verification:

```text
python3 -m py_compile scripts/verify_runtime_submit_rehearsal_pre_live_packet.py
pytest -q tests/unit/test_runtime_submit_rehearsal_pre_live_packet.py tests/unit/test_runtime_first_real_submit_owner_packet.py tests/unit/test_runtime_first_real_submit_final_review_packet.py tests/unit/test_order_lifecycle_adapter_enablement_packet.py
```

Result:

```text
24 passed
```

## Tokyo Deploy

Deployed release:

```text
/home/ubuntu/brc-deploy/releases/brc-runtime-governance-e778f0ce-20260612Tmanifest-prelive-smoke
```

Current deployed head:

```text
e778f0ced812edfd687074793b8866c4b94be45f
```

Postdeploy result:

```text
postdeploy_acceptance_passed
service=active
health={"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}
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
```

## Deployed Pre-live Smoke

Command class:

```text
scripts/verify_runtime_submit_rehearsal_pre_live_packet.py \
  --deployed-head e778f0ced812edfd687074793b8866c4b94be45f \
  --owner-real-submit-authorized \
  --owner-live-runtime-enable-authorized \
  --exercise-exchange-submit-adapter-pre-execution
```

Result from the deployed release archive:

```text
status=ready_for_owner_controlled_first_real_submit_review
current_head_deployed=true
ready_for_first_real_submit=true
exchange_submit_adapter_pre_execution_ready=true
disabled_first_real_submit_smoke_ready=true
submit_rehearsal_status=ready_for_owner_live_action_review
```

Safety proof:

```text
exchange_called=false
exchange_submit_disabled_execution_exchange_called=false
exchange_submit_disabled_execution_exchange_order_submitted=false
exchange_submit_disabled_execution_order_lifecycle_submit_called=false
exchange_submit_disabled_execution_real_adapter_executed=false
withdrawal_or_transfer_created=false
```

The full JSON report is stored on Tokyo at:

```text
/home/ubuntu/brc-deploy/reports/brc-runtime-governance-e778f0ce-20260612Tmanifest-prelive-smoke/disabled-first-submit-smoke.json
```

## Active Observation Loop

The active runtime observation loop remains running:

```text
pid=3836605
latest_status=waiting_for_signal
iteration=3
prepare_records_created=false
exchange_write_called=false
order_created=false
order_lifecycle_called=false
attempt_counter_mutated=false
runtime_budget_mutated=false
withdrawal_or_transfer_created=false
```

## Interpretation

The deployed release can now prove the disabled first-real-submit smoke and
deployment-readiness identity from its own manifest. This does not perform a
real exchange submit. Real submit remains a separate live action boundary.
