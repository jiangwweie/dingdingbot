# OrderLifecycle Adapter Enablement Packet

Date: 2026-06-10

Status: accepted as a non-executing readiness packet. Follow-up implementation
slice added a default-disabled OrderLifecycle adapter result skeleton and a
schema-readiness migration for local `CREATED` order registration.

## Purpose

This stage narrows the previous coarse blocker:

```text
order_lifecycle_adapter_disabled
```

into an auditable split between:

```text
ready_for_non_executing_order_lifecycle_adapter_implementation_task
```

and:

```text
ready_for_runtime_adapter_enablement = false
```

The packet is intentionally not a runtime enablement action and not execution
authority.

## Current Evidence

Command:

```bash
/opt/homebrew/bin/python3 scripts/build_order_lifecycle_adapter_enablement_packet.py \
  --json \
  --deployed-head 6a39509565471aa56be7945f8b04ce8d5e18460a
```

Observed status:

```text
ready_for_non_executing_order_lifecycle_adapter_implementation_task
```

Observed readiness:

```text
technical_rehearsal_ready = true
submit_boundary_ready = true
registration_draft_chain_ready = true
entry_registration_draft_ready = true
hard_stop_registration_draft_ready = true
ready_for_runtime_adapter_enablement = false
```

Remaining runtime enablement blockers include:

```text
runtime_not_live_execution_enabled
order_lifecycle_adapter_disabled
persistent_duplicate_submit_lock_not_implemented
execution_intent_status_transition_after_registration_not_implemented
protection_order_failure_recovery_not_implemented
owner_real_submit_authorization_missing
owner_live_runtime_enablement_authorization_missing
```

When the two Owner readiness flags are passed for accounting only, the packet
still keeps:

```text
ready_for_runtime_adapter_enablement = false
```

because the implementation work items remain unresolved.

## Adapter Result Skeleton

`RuntimeExecutionOrderLifecycleAdapterResult` now exists as a default-disabled
adapter skeleton:

- default call returns `order_lifecycle_adapter_disabled`;
- no `Order` objects are constructed by default;
- no local orders are registered by default;
- explicit adapter enablement, local-registration enablement, and duplicate
  submit lock evidence are required before registration;
- when explicitly enabled in application tests, it constructs local
  `Order(status=CREATED)` objects from typed registration drafts and calls
  `OrderLifecycleService.register_created_order`;
- it still does not submit exchange orders, call exchange, change
  ExecutionIntent status, or create withdrawal/transfer instructions.

Migration `067_allow_created_order_status` aligns the historical `orders`
table status check with the current domain/ORM status model so future local
registration of `Order(status=CREATED)` does not fail at the PG constraint
layer. This migration is schema readiness only; it does not enable runtime
adapter registration, submit, exchange access, or live trading.

## Safety Boundary

The packet does not:

- write PG;
- mutate a runtime;
- change ExecutionIntent status;
- construct Order objects by default;
- register local orders by default;
- call OwnerBoundedExecution;
- call OrderLifecycle by default;
- call exchange;
- create withdrawal or transfer instructions.

## Tests

Command:

```bash
/opt/homebrew/bin/pytest -q \
  tests/unit/test_runtime_order_lifecycle_adapter_result.py \
  tests/unit/test_order_lifecycle_adapter_enablement_packet.py \
  tests/unit/test_runtime_first_real_submit_owner_packet.py \
  tests/unit/test_runtime_submit_rehearsal_pre_live_packet.py \
  tests/unit/test_script_risk_classifier.py
```

Result:

```text
29 passed
```

Additional focused verification for the adapter skeleton, migration gap, and
Tokyo deploy/postdeploy planning guards:

```text
55 passed
```
