Current implementation-state note:

- `docs/product/brc-owner-console-current-state.md`

> [!IMPORTANT]
> 2026-06-08 scope note:
> This refactor spec predates the current productized bounded-live operations
> correction. Use `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`
> as the product boundary. Reuse this document only as historical design input.

下面是可直接保存到项目中的规格书内容。建议路径：

```text
docs/product/brc-owner-console-full-refactor.md
```

------

~~~markdown
# BRC Owner Console Full Refactor Specification

## 1. Product Goal

BRC Owner Console is an Owner-driven, rule-gated, audit-first local control console for BRC bounded-risk campaign operations.

It is not:

- a generic trading terminal
- an exchange UI
- an LLM trading assistant
- an unrestricted strategy execution platform
- an arbitrary order execution API
- a live/mainnet switch
- a withdrawal or transfer interface

The product goal is to make the following chain the primary system path for key Owner operations:

```text
Owner input
-> backend Operation preflight
-> backend returns decision summary
-> Owner one-time confirmation
-> backend rechecks safety gates
-> execute / block / fail / expire / cancel
-> write audit / campaign event / review evidence
-> frontend refreshes state and result
~~~

The Owner Console should support the current testnet/rehearsal stage while being designed toward L2 Live Gated delivery.

L2 Live Gated means:

```text
The system may model future live-gated operation,
but real live/mainnet execution remains unavailable unless explicitly enabled by future production-grade safety gates.
```

Current refactor goal:

```text
Complete the frontend workbench and backend Operation Layer so Owner Console operations have a consistent preflight / confirmation / execution / audit model.
```

------

## **2. Current Backend / Frontend Facts**

### **2.1 Current frontend facts**

The frontend already has a Phase 0 BRC Owner Console IA.

Current primary pages:

```text
Command Center
Markets & Orders
Campaign
Review / Evidence
Fixed Rehearsal
```

Current Phase 0 frontend principles:

- `LLM Copilot` is not a primary page.
- `Runtime Control` is not a primary executable control page.
- `Workflow` is not exposed as a generic workflow product page.
- `Fixed Rehearsal` may use workflow APIs underneath, but UI must not present this as an LLM trading workflow.
- `Markets & Orders` is currently a local BRC BTC/ETH PG summary, not a full exchange account page.
- `Action Card Summary` is not backend Operation Preflight.

### **2.2 Current backend facts**

Current backend can support:

- readiness aggregation
- local markets/orders summary
- current campaign lookup
- audit trail
- review packet
- evidence packet
- next eligibility
- review decisions
- fixed testnet rehearsal through existing workflow carrier
- readiness `action_cards`
- readiness `global_cutoff_controls`

Known current endpoints include:

```text
GET  /api/brc/readiness
GET  /api/brc/markets-orders
GET  /api/brc/campaigns/current
GET  /api/brc/audit-trail
GET  /api/brc/review-packet
GET  /api/brc/evidence
GET  /api/brc/next-eligibility
POST /api/brc/review-decisions
GET  /api/brc/review-decisions*
POST /api/brc/llm/workflows
POST /api/brc/llm/workflows/{workflow_run_id}/confirm
```

Current backend does not yet provide a complete unified Operation Layer.

Missing or incomplete capabilities:

```text
Unified Operation Preflight / Confirm / Execute
Persistent PreflightSnapshot
Confirm-once bound to operation_id + preflight_id
Unified execution envelope
Runtime state transitions through Operation
Complete exchange account truth read model
Complete order history / fill history
Mounted Operation execution for Flatten / Stop / GKS
Generic strategy switch workflow
Live gated execution
```

This does not mean the product goal should be dropped. It means the backend must be refactored to support the target Owner Console chain safely.

------

## **3. Target Core Flow**

All key Owner operations should use this flow:

```text
1. Owner chooses or submits an operation.
2. Frontend sends operation_type and input_params to backend.
3. Backend creates an Operation.
4. Backend builds and persists a PreflightSnapshot.
5. Backend returns an Owner-readable decision summary.
6. Owner confirms once, using the required confirmation phrase if applicable.
7. Backend verifies operation_id, preflight_id, idempotency, TTL, confirmation phrase, and safety gates.
8. Backend executes, blocks, fails, expires, cancels, or no-ops the operation.
9. Backend writes Operation result and audit/campaign/review references.
10. Frontend refreshes Command Center, Campaign, Audit, Review/Evidence, and related pages.
```

The frontend must not decide whether an operation is allowed. It only displays backend decisions and submits Owner confirmation.

------

## **4. Core Architectural Principles**

### **4.1 Operation is the backend authorization source**

The new Operation Layer is the backend authorization source for Owner Console actions.

```text
Operation Layer = authorization + preflight + confirmation + execution + audit boundary
```

### **4.2 Readiness is not authorization**

`/api/brc/readiness` remains a state aggregation and presentation endpoint.

It may provide:

- current state
- risk summaries
- action cards
- cutoff control summaries
- latest audit
- latest campaign

But it must not be treated as the source of authorization for state-changing operations.

### **4.3 LLM is not authorization**

LLM-related workflows may provide:

- explanation
- summary
- proposal
- legacy workflow carrier for fixed testnet rehearsal

But LLM must not directly:

- execute operations
- modify runtime
- switch playbooks
- place orders
- authorize live actions
- bypass Owner confirmation

### **4.4 Frontend is not authorization**

The frontend must not:

- decide whether an operation is safe
- simulate backend policy as the source of truth
- mark unavailable actions as executable
- convert readiness action cards into real Operation Preflight
- present mock account/order facts as exchange truth

### **4.5 Audit and evidence are first-class**

Every important operation result must be persisted in an audit/ledger trail.

This includes:

- executed
- blocked
- failed
- expired
- cancelled
- noop

Blocked or failed operations are still important facts.

------

## **5. Operation Layer Requirements**

The backend should implement a unified Operation Layer with:

```text
OperationRegistry / OperationPolicy
OperationService
PreflightBuilder
ExecutionAdapter
AuditWriter
OperationRepository
PreflightSnapshotRepository
```

Equivalent names are acceptable if they fit the existing codebase style.

### **5.1 OperationRegistry / OperationPolicy**

Defines each operation type:

```text
operation_type
display_name
risk_level
allowed_environments
confirmation_policy
executor_adapter
capability_status
current_reason
```

Capability status values should include:

```text
available
enabled
requires_operation_layer
design_surface
unavailable
forbidden
not_implemented
```

### **5.2 OperationService**

Responsible for:

```text
preflight
confirm
cancel
get
list
```

It should coordinate:

- operation creation
- preflight snapshot persistence
- confirmation validation
- safety gate recheck
- execution adapter invocation
- result persistence
- audit references

### **5.3 PreflightBuilder**

Builds an Owner-readable preflight decision summary.

It should collect or derive:

```text
runtime summary
account/order summary
campaign summary
playbook summary
risk summary
environment boundary
audit writable status
target state
warnings
blockers
confirmation requirement
```

### **5.4 ExecutionAdapter**

Executes operation-specific logic.

Adapters must be explicit per operation type.

No generic arbitrary trade execution adapter is allowed.

### **5.5 AuditWriter**

Writes or links operation results to:

```text
operation ledger
audit trail
campaign event
workflow run
review decision
evidence packet
```

as applicable.

------

## **6. Supported Operation Types**

### **6.1 Must be fully supported**

The following should be implemented as real executable Operation flows if existing safety boundaries allow:

```text
switch_playbook
start_review
write_review_decision
run_fixed_testnet_rehearsal
enter_observe
enter_pause
enter_strategy_or_monitor
```

If an operation cannot be safely executed because supporting backend state transitions are not ready, it must return `unavailable` or `not_implemented` through capabilities and/or preflight.

Do not fake success.

### **6.2 May be supported as safety-limited operations**

These may be implemented only if safe backend execution paths exist:

```text
pause_new_entries
emergency_stop_runtime
emergency_flatten
```

Rules:

- They cannot bypass backend validation.
- They cannot bypass audit.
- They can have a shorter confirmation path if policy allows.
- They must still write Operation result.
- If unsupported, return `design_surface` or `unavailable`.

### **6.3 Must be modeled as forbidden or unavailable**

These must not be executable from Owner Console:

```text
live_execution
unrestricted_order_execution
withdrawal
transfer
arbitrary_symbol_order
arbitrary_strategy_router
arbitrary_side_size_order
llm_direct_execution
```

They may appear only in capability metadata as `forbidden` or `unavailable`, if useful for explicit boundary reporting.

They must not appear as executable UI actions.

------

## **7. Important Operation Semantics**

### **7.1 switch_playbook**

`switch_playbook` is the first required MVP Operation.

It must support:

```text
preflight
confirm
execute
audit/campaign event refs
readiness refresh
```

Constraints:

- Must not place orders.
- Must not reset attempts.
- Must not reset PnL.
- Must not reset loss lock.
- Must not bypass campaign rules.
- Must check target playbook is known/allowlisted.
- Must persist operation result.
- Must write or link audit/campaign event.

### **7.2 start_review / write_review_decision**

Review actions should enter the Operation chain.

They may reuse current review decision APIs internally, but the final result should be linked to `operation_id`.

### **7.3 run_fixed_testnet_rehearsal**

Fixed testnet rehearsal may continue to use the existing workflow carrier internally.

But the Owner Console authorization path should be:

```text
Operation preflight
-> Owner confirm
-> ExecutionAdapter invokes fixed rehearsal carrier
-> Operation result persisted
```

UI must call this `Fixed Testnet Rehearsal`, not LLM workflow.

### **7.4 enter_observe**

Entering observe mode means:

- no new trading action
- monitor account/orders/risk
- write runtime transition / audit

It must not place orders.

### **7.5 enter_pause**

Entering pause mode means:

- stop new strategy actions
- preserve monitoring
- do not automatically flatten
- do not automatically cancel all orders unless explicitly requested and supported

It must write runtime transition / audit.

### **7.6 enter_strategy_or_monitor**

This operation must not become an automatic trading switch.

If full strategy runner safety is not ready, it should degrade to monitor/armed-observe/playbook-carrier semantics.

Allowed meaning:

```text
Load or activate an Owner-selected playbook in a controlled monitor/strategy carrier state.
```

Forbidden meaning:

```text
Start unrestricted automatic trading.
```

------

## **8. Backend API Contract**

The API names may follow project conventions, but these semantics must exist.

### **8.1 Capabilities**

```text
GET /api/brc/operations/capabilities
```

Returns capability metadata for operation types.

Each item should include:

```json
{
  "operation_type": "switch_playbook",
  "status": "enabled",
  "display_name": "Switch Playbook",
  "risk_level": "medium",
  "allowed_env": ["testnet", "local"],
  "confirmation_required": true,
  "backend_executor": "brc_switch_playbook",
  "current_reason": "Operation Preflight available"
}
```

Capability statuses:

```text
available
enabled
operation_preflight_available
legacy_dev_path
requires_operation_layer
design_surface
unavailable
forbidden
not_implemented
```

The exact enum may be normalized, but frontend must be able to distinguish:

```text
executable through Operation
available through legacy path
summary/design only
unavailable
forbidden
```

### **8.2 Preflight**

```text
POST /api/brc/operations/preflight
```

Request example:

```json
{
  "operation_type": "switch_playbook",
  "requested_by": "owner",
  "input_params": {
    "target_playbook_id": "PB-004-BRC-CONTROLLED-TESTNET"
  },
  "source": {
    "kind": "ui"
  }
}
```

Response must include:

```json
{
  "operation_id": "op_xxx",
  "preflight_id": "pre_xxx",
  "operation_type": "switch_playbook",
  "decision": "allow",
  "summary": "Switch playbook to PB-004 after owner confirmation.",
  "before": {},
  "after": {},
  "account_order_summary": {},
  "runtime_summary": {},
  "campaign_summary": {},
  "playbook_summary": {},
  "risk_summary": {
    "passed": [],
    "warnings": [],
    "blockers": []
  },
  "confirmation_requirement": {
    "required": true,
    "phrase": "CONFIRM_SWITCH_PLAYBOOK",
    "expires_at_ms": 123456789,
    "totp_freshness_required": false
  },
  "idempotency_key": "idem_xxx",
  "status": "awaiting_confirmation"
}
```

### **8.3 Confirm**

```text
POST /api/brc/operations/{operation_id}/confirm
```

Request:

```json
{
  "preflight_id": "pre_xxx",
  "confirmation_phrase": "CONFIRM_SWITCH_PLAYBOOK",
  "idempotency_key": "idem_xxx"
}
```

Response:

```json
{
  "operation_id": "op_xxx",
  "preflight_id": "pre_xxx",
  "status": "executed",
  "rechecked": true,
  "result_summary": {},
  "audit_refs": [],
  "campaign_refs": [],
  "review_refs": [],
  "next_state": {}
}
```

### **8.4 Cancel**

```text
POST /api/brc/operations/{operation_id}/cancel
```

Should mark the operation as cancelled if still cancellable.

Cancelled operations should be persisted.

### **8.5 Get**

```text
GET /api/brc/operations/{operation_id}
```

Returns operation state, current preflight, result, and refs.

### **8.6 List**

```text
GET /api/brc/operations
```

Returns recent operations.

Useful for Recent Operation Results.

------

## **9. Data Model Requirements**

The implementation may reuse existing persistence conventions, but these concepts must exist.

### **9.1 Operation**

Required fields or equivalents:

```text
operation_id
operation_type
requested_by
requested_at_ms
source_type
source_ref
input_params_json
environment
risk_level
status
current_preflight_id
confirmed_by
confirmed_at_ms
executed_at_ms
result_status
result_summary_json
created_audit_refs_json
```

### **9.2 PreflightSnapshot**

Required fields or equivalents:

```text
preflight_id
operation_id
created_at_ms
expires_at_ms
current_state_snapshot_json
target_state_json
account_snapshot_json
order_snapshot_json
runtime_snapshot_json
campaign_snapshot_json
playbook_snapshot_json
risk_result_json
decision
warnings_json
blockers_json
confirmation_requirement_json
snapshot_hash
idempotency_key
```

### **9.3 ExecutionResult**

Required fields or equivalents:

```text
operation_id
preflight_id
status
recheck_result_json
adapter_result_json
blocked_reason
failed_reason
audit_refs_json
campaign_refs_json
review_refs_json
final_state_snapshot_json
```

### **9.4 Audit references**

Audit references should support:

```text
operation
campaign_event
workflow_run
review_decision
runtime_transition
```

------

## **10. Decision and Status Enums**

### **10.1 Preflight decision**

```text
allow
warn
block
unavailable
expired
```

### **10.2 Operation status**

```text
draft
awaiting_confirmation
executing
executed
blocked
failed
cancelled
expired
noop
```

### **10.3 Execution status**

```text
executed
blocked
failed
cancelled
expired
noop
```

### **10.4 Capability status**

```text
enabled
available
operation_preflight_available
legacy_dev_path
requires_operation_layer
design_surface
unavailable
forbidden
not_implemented
```

Exact names may differ, but frontend semantics must be preserved.

------

## **11. Confirm / Execute Safety Rules**

Confirm must not blindly trust preflight snapshot.

Confirm must check:

```text
operation_id exists
preflight_id matches operation current_preflight_id
preflight has not expired
operation status is awaiting_confirmation
idempotency_key matches
confirmation phrase matches
environment boundary remains valid
live/mainnet remains forbidden unless explicitly allowed by future production policy
operation_type is not withdrawal or transfer
audit writable is still true
GKS / startup guard / runtime safety state
campaign state still allows the transition
target playbook is known / allowlisted
account/order facts have not drifted in a critical way
operation policy remains enabled
```

If any critical check fails:

```text
Do not execute target action.
Persist operation as blocked / expired / failed.
Return unified execution envelope.
Write audit / ledger.
```

Double confirmation must not execute twice.

Expired preflight must not execute.

Wrong confirmation phrase must not execute.

------

## **12. Frontend Requirements**

The frontend should preserve the current Phase 0 IA:

```text
Command Center
Markets & Orders
Campaign
Review / Evidence
Fixed Rehearsal
```

### **12.1 Command Center**

Must show:

```text
readiness status
runtime_state
risk_decision
runtime_summary
risk_account_summary
strategy_playbook_summary
markets_summary
latest_campaign
latest_audit
action_cards
global_cutoff_controls
Operation Layer status
operation capabilities
```

### **12.2 Operation Layer Status**

Command Center should clearly show:

```text
Operation Layer enabled for specific operations
Actions still requiring Operation Layer
Design surfaces
Unavailable capabilities
Forbidden capabilities
```

### **12.3 Two modal types**

#### **Action Card Summary**

For actions not yet backed by Operation Layer.

Required wording:

```text
Phase 0 Action Card Summary.
This is assembled from current readiness data.
Generic backend Operation Preflight is not enabled for this action yet.
```

Do not call this Preflight Review.

#### **Operation Preflight**

For actions backed by Operation Layer.

Required wording:

```text
This operation is authorized through the backend Operation layer.
Confirmation is one-time and bound to this preflight snapshot.
```

Operation Preflight modal must show:

```text
operation_type
decision
summary
before
after
account_order_summary
runtime_summary
campaign_summary
playbook_summary
risk_summary
confirmation phrase
expires_at
confirm
cancel
```

Confirm behavior:

```text
Submit confirm request once.
Disable duplicate clicks.
Close or update modal after result.
Refresh readiness.
Refresh campaign.
Refresh audit/review/evidence.
Show executed / blocked / failed / expired / cancelled / noop.
```

### **12.4 CapabilityBadge**

Frontend should support badges for:

```text
Available now
Operation Preflight available
Legacy/dev path
Requires Operation Layer
Design surface
Unavailable
Forbidden
```

### **12.5 Markets & Orders**

Must remain honest about data source.

Required wording unless a real account truth model is added:

```text
Phase 0 / current view shows local BRC BTC/ETH PG summary only.
It is not a generic exchange trading terminal.
It is not a complete exchange account, order history, or fill history view.
```

If account truth is added, display:

```text
source = local_pg | exchange_testnet | exchange_live | mixed
truth_level = summary | exchange_read | reconciled
```

Do not mock full balance, fills, or exchange truth.

### **12.6 Fixed Testnet Rehearsal**

UI page name remains:

```text
Fixed Testnet Rehearsal
```

Do not rename it to LLM workflow.

If Operation Layer supports rehearsal, use Operation Preflight.

If not, show as legacy workflow carrier.

Required wording:

```text
Runs the fixed BRC ETH/BTC testnet rehearsal through the existing workflow carrier.
This is not a generic LLM trading workflow.
```

------

## **13. Safety / Audit / Review Requirements**

### **13.1 Safety**

The refactor must preserve and strengthen:

```text
testnet-first
no unrestricted live
no withdrawal/transfer
no LLM direct execution
Owner confirmation
audit-first
bounded-risk campaign controls
runtime safety gates
```

### **13.2 Audit**

Every operation result should be recorded.

This includes:

```text
executed
blocked
failed
expired
cancelled
noop
```

Audit trail should be usable as the source for Recent Operation Results.

### **13.3 Review / Evidence**

Where applicable, operation results should link to:

```text
campaign events
review decisions
evidence packets
workflow runs
runtime transitions
```

Review decisions should be able to reference operation IDs if implemented.

------

## **14. Forbidden Capabilities**

The following are out of scope and must not be implemented as executable Owner Console actions:

```text
arbitrary order execution
arbitrary symbol / side / size order
unrestricted live execution
mainnet execution
withdrawal
transfer
LLM direct execution
LLM direct runtime modification
LLM direct order placement
strategy pool auto-router
automatic trend recognition -> strategy group auto-load -> live execution
free-form parameter editing for live strategy
generic exchange terminal behavior
```

If these appear in capabilities, they must be:

```text
forbidden
unavailable
not_implemented
```

They must not show executable confirmation UI.

------

## **15. Acceptance Criteria**

### **15.1 Backend acceptance**

Must satisfy:

```text
/api/brc/operations/capabilities works
/api/brc/operations/preflight works
/api/brc/operations/{operation_id}/confirm works
/api/brc/operations/{operation_id}/cancel works
/api/brc/operations/{operation_id} works
/api/brc/operations list works
Operation is persisted
PreflightSnapshot is persisted
Preflight has TTL
Preflight has idempotency_key
Confirm binds operation_id + preflight_id
Confirm prevents duplicate execution
Confirm reruns safety gates
Unified execution statuses exist
Blocked / failed / expired / cancelled are persisted
switch_playbook is fully supported
start_review or write_review_decision is supported or explicitly unavailable with reason
fixed_testnet_rehearsal is supported through Operation or explicitly shown as legacy carrier
runtime transitions are supported or explicitly unavailable with reason
No live/mainnet/withdrawal/transfer execution path exists
No LLM direct execute path exists
```

### **15.2 Frontend acceptance**

Must satisfy:

```text
Primary nav remains 5 pages
Command Center shows readiness and capabilities
Command Center shows Operation Layer status
Markets & Orders does not claim complete exchange truth
Campaign remains business view
Review / Evidence shows audit/review/evidence
Fixed Rehearsal is not presented as LLM page
Operation-backed actions use Operation Preflight modal
Non-operation actions use Action Card Summary or unavailable/design surface
Confirm is one-time
Confirm prevents duplicate clicks
Confirm result refreshes readiness/campaign/audit
Flatten / Stop / GKS do not show real confirm unless backend supports them
Enter Strategy is not shown as auto trading switch
Live execution is unavailable / forbidden
Withdrawal / transfer are not exposed as executable
```

### **15.3 Test acceptance**

Backend tests should cover:

```text
capabilities endpoint
preflight success
unknown operation
unknown playbook
wrong confirmation phrase
expired preflight
double confirm
audit writable false
safety gate recheck
cancel operation
get operation
list operations
switch_playbook audit/campaign refs
forbidden live/withdrawal/transfer impossible
```

Frontend checks should cover:

```text
typecheck
build
Command Center renders readiness
capabilities render
Operation Preflight modal works for supported action
Action Card Summary used for unsupported action
Fixed Rehearsal is not presented as LLM
no TypeScript errors
```

------

## **16. Quality Commands**

Run available project quality commands.

Frontend:

```text
npm run lint
npm run build
```

Backend:

```text
Run BRC / operation / campaign / API related tests.
Run lint/typecheck if available.
```

If a command fails, report:

```text
failed command
key error
whether failure is caused by this change
unresolved risk
```

------

## **17. Out of Scope**

This refactor should not attempt to complete:

```text
full production live trading
exchange-wide account dashboard
complete fill history unless backend truth exists
strategy pool auto-router
trend detection engine
risk envelope orchestration across arbitrary strategies
Feishu / cloud production approval loop
withdrawal / transfer controls
unrestricted live execution
```

------

## **18. Implementation Guidance**

This is a full refactor goal, but safety boundaries override apparent completeness.

If an operation cannot be safely implemented:

```text
Do not fake it.
Return unavailable / forbidden / design_surface.
Explain reason in capability response and final report.
Keep UI honest.
```

Minimum required full chain:

```text
switch_playbook:
preflight -> confirm -> execute/block -> audit/campaign refs -> frontend refresh
```

Other operations may be implemented if safe. Otherwise they must be modeled truthfully.

Do not let this refactor become a generic trading terminal backend.

The correct boundary is:

```text
Owner-driven
rule-gated
audit-first
BRC-scoped
testnet/current-stage honest
L2 Live Gated target, not live-enabled now
```
