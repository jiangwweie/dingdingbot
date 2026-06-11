# Runtime Disabled First-Real-Submit Smoke Readiness - 2026-06-12

## Scope

This records a non-executing readiness clarification for the runtime submit
rehearsal packet.

The goal is to distinguish:

```text
disabled first-real-submit smoke is ready
```

from:

```text
real first-real-submit is authorized and ready
```

The former may be exercised without live exchange order placement. The latter
remains separately Owner-gated.

## Change

Commit under preparation adds the explicit check:

```text
checks.disabled_first_real_submit_smoke_ready
```

It becomes `true` only when:

- local registration pre-exchange rehearsal is ready;
- exchange-submit adapter pre-execution rehearsal is ready;
- disabled execution result has no blockers;
- disabled execution does not call exchange;
- disabled execution does not submit exchange orders;
- disabled execution does not call `OrderLifecycle.submit`;
- disabled execution does not mutate `ExecutionIntent`;
- disabled execution does not create withdrawal or transfer.

It does not change:

```text
checks.ready_for_first_real_submit
```

## Verification

Focused tests:

```text
pytest -q tests/unit/test_runtime_submit_rehearsal_pre_live_packet.py tests/unit/test_runtime_first_real_submit_owner_packet.py tests/unit/test_runtime_first_real_submit_final_review_packet.py tests/unit/test_order_lifecycle_adapter_enablement_packet.py
```

Result:

```text
23 passed
```

Default smoke:

```text
status=blocked_before_first_real_submit
ready_for_first_real_submit=false
exchange_submit_adapter_pre_execution_ready=false
disabled_first_real_submit_smoke_ready=false
```

Pre-execution disabled smoke:

```text
status=blocked_before_first_real_submit
ready_for_first_real_submit=false
exchange_submit_adapter_pre_execution_ready=true
disabled_first_real_submit_smoke_ready=true
submit_rehearsal_status=ready_for_owner_live_action_review
```

Safety proof for the disabled smoke:

```text
exchange_called=false
exchange_submit_disabled_execution_exchange_called=false
exchange_submit_disabled_execution_exchange_order_submitted=false
exchange_submit_disabled_execution_order_lifecycle_submit_called=false
exchange_submit_disabled_execution_real_adapter_executed=false
withdrawal_or_transfer_created=false
```

## Interpretation

The system can now report that the disabled first-real-submit smoke boundary is
ready without implying that real submit is authorized or ready.

Remaining real-submit gates include deployment readiness evidence and explicit
Owner real-submit / live-runtime enablement authorization for the concrete live
action.
