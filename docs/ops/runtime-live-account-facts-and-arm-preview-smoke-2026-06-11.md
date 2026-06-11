# Runtime Live Account Facts And Arm Preview Smoke - 2026-06-11

Status: PASSED_WITH_ARM_PREVIEW_STOPPED_BEFORE_ATTEMPT_CONSUMPTION

## Scope

This report records the Tokyo verification for:

- live read-only account facts as the trusted account source for runtime
  strategy planning;
- sample next-attempt prepare reaching fresh preflight records;
- arm preview no longer consuming runtime attempts;
- repair of one prior sample rehearsal mutation that consumed an attempt before
  the arm-preview fix.

No real submit was authorized or executed.

## Commits

```text
eb37b9d8 feat(runtime): support live read-only account facts for strategy planning
2c2e8122 fix(runtime): treat live read-only account facts as fresh
bfc51c5e fix(runtime): keep arm preview from consuming attempts
47327706 fix(runtime): stop arm preview before handoff without attempt policy
```

Current deployed release:

```text
/home/ubuntu/brc-deploy/releases/brc-runtime-governance-47327706-20260611Tarm-preview-clear-blocker
```

Deploy effects for the latest release:

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

Tokyo env now includes:

```text
TRADING_CONSOLE_RUNTIME_ACCOUNT_FACTS_SOURCE=live_read_only
```

This selects a read-only account facts source for runtime strategy planning.
It reads account balance through the Trading Console read-only gateway and
does not expose order, submit, withdrawal, or transfer authority.

## Prepare Smoke

Report:

```text
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-sample-prepare-disabled-submit/20260611Tsample-prepare-after-attempt-repair/monitor-sample-allow-prepare.json
```

Result:

```text
status=ready_for_final_gate_preflight
authorization_id=runtime-submit-authorization-intent_rt_e8037454b07d3ab8cc5d8dd8
blockers=[]
warnings=trusted_market_fact_source_not_configured_optional_only
```

Interpretation:

```text
The sample ready signal can now pass the trusted account facts requirement and
create fresh shadow candidate / intent draft / ExecutionIntent / submit
authorization / protection plan records.
```

## Prior Sample Attempt Repair

Before the arm-preview fix, a sample arm rehearsal consumed one runtime attempt
before final readiness. The mutation was retained for audit, and only the
current runtime boundary was restored to the previous applied mutation state.

Repair result:

```text
runtime_instance_id=strategy-runtime-95655873b76c
restored_attempts_used=2
restored_budget_reserved=0.166864220000000000
bad_mutation_id=runtime-attempt-mutation-runtime-attempt-reservation-runtime-submit-authorization-intent_rt_b72470f6a8c79d84206567d0
exchange_called=false
order_created=false
order_lifecycle_called=false
```

The repair note was written into `strategy_runtime_instances.metadata` as
`last_sample_arm_preview_attempt_repair`.

## Arm Preview Smoke

Report:

```text
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-sample-prepare-disabled-submit/20260611Tsample-arm-preview-clear-blocker/arm-preview.json
```

Result:

```text
mode=arm
ready_for_real_submit_action=false
blockers=attempt_consumption_required_before_order_lifecycle_handoff
warnings=attempt_consumption_not_recorded_in_arm_preview
attempt_mutation_called=false
attempt_reservation_called=false
handoff_called=false
disabled_action_called=false
before={"attempts_used": 2, "budget_reserved": "0.166864220000000000"}
after={"attempts_used": 2, "budget_reserved": "0.166864220000000000"}
```

Interpretation:

```text
Arm preview now stops before handoff when no attempt outcome policy exists.
This avoids consuming attempts or reserved budget during disabled preview /
operator rehearsal. Real execute remains separately guarded by CLI + env owner
confirmation and is not authorized by this smoke.
```

## Remaining Live Path

For a true live attempt, the system still needs:

```text
fresh live strategy signal
fresh prepare authorization from that live signal
explicit Owner real-submit confirmation
execute-mode attempt consumption
official first-real-submit action
post-submit accounting/review
```

This report does not claim CPM/BRF alpha, does not authorize order placement,
and does not change the right-tail small-risk-capital objective.
