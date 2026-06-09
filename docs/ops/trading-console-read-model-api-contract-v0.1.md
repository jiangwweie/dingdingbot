> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# Trading Console Read-Model API Contract v0.1

Date: 2026-06-04

> [!IMPORTANT]
> 2026-06-08 current-product scope note:
> This document defines the read-only `/api/trading-console/*` read-model
> namespace only. It must not be read as "Trading Console is a read-only
> product." The current product model is governed by
> `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`: Owner-facing
> bounded-live operations through `ActionCandidate -> ActionSpec -> FinalGate
> -> Operation Layer -> protection -> Review Ledger`.

Namespace: `/api/trading-console/*`

Mode: operator-authenticated, read-only backend aggregation. No endpoint in this
namespace places, cancels, replaces, flattens, retries protection, starts
runtime, grants auto execution, or mutates PG.

## Shared Envelope

Every endpoint returns:

```json
{
  "read_model": "dashboard_state",
  "generated_at_ms": 1780500000000,
  "source": "trading_console_read_model_v1",
  "freshness_status": "not_live_connected",
  "warnings": [],
  "blockers": [],
  "unavailable": [],
  "data": {},
  "no_action_guarantee": {
    "places_order": false,
    "cancels_order": false,
    "replaces_order": false,
    "flattens_position": false,
    "retries_protection": false,
    "starts_runtime": false,
    "grants_auto_execution": false,
    "mutates_pg": false
  },
  "live_ready": false
}
```

Freshness values:

- `fresh`: all requested sources available and no warnings.
- `warning`: sources available but warning facts exist.
- `degraded`: one or more requested sources failed or are unavailable.
- `not_live_connected`: default state when exchange reads were not requested.

Common query parameters:

- `symbol`: optional symbol filter.
- `include_exchange`: optional bool, default `false`. When true, performs
  read-only account snapshot lookup if configured, `fetch_positions`, normal
  `fetch_open_orders`, and conditional/stop
  `fetch_open_orders(..., params={"stop": true})` through the configured
  gateway. When false, the Trading Console namespace does not call exchange or
  account snapshot readers.
- `limit`: optional bounded result limit where applicable.

## Endpoints

### `GET /api/trading-console/dashboard-state`

Purpose: one backend-owned homepage state, so the frontend does not infer
safety-critical state by stitching unrelated APIs.

`data` fields:

- `environment`
- `guards`
- `account_snapshot_summary`
- `positions.pg`
- `positions.exchange`
- `orders.pg_open`
- `orders.exchange_open`
- `orders.open_intents`
- `consistency`
- `authorization`
- `freshness`

### `GET /api/trading-console/account-risk`

Purpose: full-account risk snapshot with ownership/protection hints.

`data` fields:

- `risk_state`
- `account`
- `positions`
- `open_orders`
- `margin_facts`
- `protection_ownership`
- `freshness`

Unavailable fields remain `not_available` or appear in `unavailable`.

### `GET /api/trading-console/order-ledger`

Purpose: PG/exchange order ledger and protection grouping.

`data` fields:

- `orders`: classified order rows.
- `groups`: entry/protection groups by parent order.
- `classification_counts`
- `unavailable_fields`

Classifications:

- `matched`
- `pg_unchecked`
- `pg_only`
- `exchange_only`
- `mismatch`
- `orphan_protection`
- `unknown`

### `GET /api/trading-console/protection-health`

Purpose: front-end-safe protection state.

`data` fields:

- `status`: `protected`, `partially_protected`, `unprotected`, `unknown`, or
  `orphaned`
- `protection_orders`
- `tp_count`
- `sl_count`
- `findings`
- `actions_exposed`
- `deferred_actions`

### `GET /api/trading-console/recovery-exception-state`

Purpose: read-only recovery and exception visibility.

`data` fields:

- `recovery_tasks`
- `recovery_task_counts`
- `mismatches`
- `manual_action_required`
- `read_only_actions`
- `deferred_actions`

### `GET /api/trading-console/authorization-state`

Purpose: explicit authorization lifecycle read model.

`data` fields:

- `carrier_id`
- `authorization_id`
- `status`
- `is_actionable`
- `is_consumed`
- `is_expired`
- `is_cancelled`
- `scope_match`
- `blocking_reason`
- `scope`
- `future_action_slots`

### `GET /api/trading-console/execution-control-state`

Purpose: read-only execution-control state without wrapping execute.

`data` fields:

- `hard_gate.status`
- `hard_gate.gates`
- `execution_preview`
- `deferred_execute_endpoint`

This endpoint never creates an `ExecutionIntent` and never submits orders.

### `GET /api/trading-console/review-state`

Purpose: review records and stored trade/result facts.

`data` fields:

- `reviews`
- `filled_order_facts`
- `positions`
- `unavailable_fields`

`fee`, `fee_asset`, `funding`, and `slippage` are `not_available` in v1 unless
already stored by an injected service.

### `GET /api/trading-console/audit-chain`

Purpose: technical audit aggregation.

Query fields:

- `authorization_id`
- `intent_id`
- `order_id`
- `exchange_order_id`
- `symbol`
- `limit`

`data` fields:

- `query`
- `authorization`
- `intents`
- `orders`
- `positions`
- `reviews`
- `audit_events`
- `raw_payload_policy`

### `GET /api/trading-console/carrier-availability`

Purpose: backend-owned carrier shelf availability.

`data` fields:

- `carriers`
- `sample_data_policy`

V1 exposes the current active carrier surface and records block reasons without
front-end inference.

### `GET /api/trading-console/strategy-family-admission-state`

Purpose: production strategy-family admission read model for Owner review.

Optional query fields for read-only Owner scope review:

- `family`
- `strategy_family_id`
- `carrier_id`
- `symbol`
- `side`
- `quantity`
- `max_notional`
- `leverage`
- `max_attempts`
- `protection_mode`
- `review_requirement`

`data` fields:

- `admission_contract.chain`
- `admission_contract.required_owner_scope_fields`
- `admission_contract.backend_action_policy`
- `production_baseline_context`
- `scope_review`
- `families`
- `family_completion_matrix`
- `admission_risk_control_matrix`
- `production_capital_boundary_matrix`
- `full_chain_evidence_matrix`
- `protection_review_audit_matrix`
- `blocker_retry_matrix`
- `owner_authorization_packet_matrix`
- `owner_review_handoff_matrix`
- `official_api_request_draft_matrix`
- `live_action_eligibility_matrix`
- `final_gate_readiness_matrix`
- `production_action_decision_matrix`
- `classification_counts`
- `trading_console_authorization_readiness`
- `bridge_artifacts`
- `bridge_artifact_statuses`
- `objective_acceptance_audit_matrix`
- `acceptance_evidence_matrix`
- `blocker_records`
- `pre_execution_blocked_review`
- `audit_chain_gap_report`
- `live_actions_taken`
- `pg_exchange_evidence`
- `pg_exchange_evidence_matrix`
- `family_evidence_collection_matrix`
- `evidence_collection_summary_matrix`
- `scoped_dry_run_examples`
- `official_action_api_inventory`
- `api_backed_authorization_flow`
- `official_transition_readiness_matrix`
- `sprint_acceptance_verdict`
- `family_final_report_matrix`
- `final_report_package`

This endpoint is GET-only and never creates an admission request, owner
authorization, execution intent, order, protection order, review, runtime start,
or PG mutation. `families[*].backend_actionable` and
`families[*].frontend_action_enabled` must remain false unless a future scoped
backend final gate explicitly returns actionable state for that candidate.
`production_baseline_context` records the prior BNB-only execute/closeout and
post-close flat report references as historical baseline context. It is not an
authorization source and must keep
`reusable_for_strategy_family_authorization=false`,
`grants_execution_permission=false`, `grants_order_permission=false`,
`frontend_action_enabled=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `starts_runtime=false`,
`starts_strategy_execution=false`, `places_order=false`, `mutates_pg=false`,
and `exchange_write_action=false`. Any future live action must collect fresh
pre-action PG and exchange evidence through the official action path.
Each family row includes structured `budget_envelope_draft`,
`authorization_draft_proposal`, `risk_disclosure_contract`,
`strategy_group_mapping`, `carrier_candidate`, `carrier_readiness_report`,
`action_api_compatibility`, `action_candidate`,
`observation_bridge`, `chain_stage_states`, `pre_post_evidence_contract`,
`gate_blocker_records`, `api_request_drafts`, `admission_verdict`,
`final_gate_dry_run`, `pre_execution_blocked_review`,
`protection_plan_draft`, `review_contract`, and `blocker_record` fields for
Owner review and frontend disabled-state rendering.
`bridge_artifact_statuses` is the top-level bridge coverage matrix. It has one
row for each bridge method in `bridge_artifacts` and exposes `status`,
`families`, per-family `row_statuses`, evidence, and the next retry condition.
The status matrix is read-only summary evidence only: every row must keep
`action_allowed=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `places_order=false`, and `mutates_pg=false`.
It is intended for frontend handoff/audit coverage checks, not action
enablement.
`family_completion_matrix` is the per-family completion summary for final
handoff/reporting. Each row includes family, strategy family id, strategy
group, carrier id, classification, completion status, completed/blocked chain
stages, blocked stage statuses, blocker ids, bridge methods, evidence refs, and
next retry conditions. It mirrors the `StrategyFamily -> StrategyGroup ->
Carrier -> RiskDisclosure -> AuthorizationDraft -> BoundedLiveAuthorization ->
ExecutionIntent -> Entry -> TP/SL -> Review` chain without enabling execution;
rows must keep `backend_actionable=false`, `frontend_action_enabled=false`,
`may_execute_live=false`, `creates_execution_intent=false`,
`places_order=false`, and `mutates_pg=false`.
`admission_risk_control_matrix` is the per-family admission/risk-control
summary for frontend handoff and sprint reporting. Each row aggregates family,
strategy family id, strategy group, carrier id, admission level,
classification, scope-review verdict, risk disclosure status, budget envelope
status, authorization draft status, bounded live authorization status, action
API status, final-gate status/reason, protection-plan status, review-contract
status, audit-chain status, blocker ids, and next retry conditions. It is a
summary of existing row contracts only. Rows must keep
`backend_actionable=false`, `frontend_action_enabled=false`,
`may_execute_live=false`, `action_allowed=false`,
`creates_authorization=false`, `creates_execution_intent=false`,
`starts_runtime=false`, `starts_strategy_execution=false`,
`places_order=false`, and `mutates_pg=false`.
`production_capital_boundary_matrix` is the per-family Production Capital
Boundary table. It mirrors the required Owner scope fields
`symbol`, `side`, `quantity`, `max_notional`, `leverage`, `max_attempts`,
`protection_mode`, and `review_requirement`, records which fields were
provided or missing, and copies only Owner-supplied numeric scope values from
`budget_envelope_draft`. It must not infer or fabricate quantity, notional,
leverage, attempts, protection, or review values. Rows must keep
`scope_expansion_allowed=false`, `symbol_expansion_allowed=false`,
`side_expansion_allowed=false`, `quantity_expansion_allowed=false`,
`notional_expansion_allowed=false`, `leverage_expansion_allowed=false`,
`max_attempts_expansion_allowed=false`, `action_allowed=false`,
`creates_authorization=false`, `creates_execution_intent=false`,
`starts_runtime=false`, `starts_strategy_execution=false`,
`places_order=false`, `mutates_pg=false`, and `exchange_write_action=false`.
`full_chain_evidence_matrix` is the top-level per-family chain evidence table.
At this revision it has one row per family and chain stage: `StrategyFamily`,
`StrategyGroup`, `Carrier`, `RiskDisclosure`, `AuthorizationDraft`,
`BoundedLiveAuthorization`, `ExecutionIntent`, `Entry`, `TP/SL`, and `Review`.
Each row includes stage order, status, bridge method, human-readable evidence,
required evidence refs, blocker ids, and next retry conditions. It is a
reporting/readiness artifact only. Rows must keep `backend_actionable=false`,
`frontend_action_enabled=false`, `may_execute_live=false`,
`creates_authorization=false`, `creates_execution_intent=false`,
`starts_runtime=false`, `starts_strategy_execution=false`,
`places_order=false`, and `mutates_pg=false`.
`protection_review_audit_matrix` is the per-family TP/SL + Review + Audit
readiness table. Each row aggregates `protection_plan_draft`,
`review_contract`, and `audit_chain_gap_report` into Owner/report-facing
status: required protection components, missing/unavailable protection fields,
review required/missing evidence, audit present/missing evidence, audit
sources, blocker ids, and retry conditions. It must not fabricate TP/SL prices
or exchange protection order ids, and must keep `action_allowed=false`,
`creates_order=false`, `records_review=false`,
`creates_execution_intent=false`, `places_order=false`, and `mutates_pg=false`.
`blocker_retry_matrix` is the family-preserving blocker/retry table. Unlike
top-level `blocker_records`, which is de-duplicated by blocker id, this matrix
expands each primary and gate blocker per family and includes blocker id,
stage, blocked path, severity, bridge method, evidence, next retry condition,
and concrete retry requirements. It is a report/readiness artifact only: every
row has `retry_ready=false`, `action_allowed=false`,
`creates_authorization=false`, `creates_execution_intent=false`,
`starts_runtime=false`, `starts_strategy_execution=false`,
`places_order=false`, and `mutates_pg=false`.
`owner_authorization_packet_matrix` is the Owner-facing authorization review
packet table. Each row aggregates the risk disclosure status, budget envelope
status, authorization draft status, required confirmation phrase, official API
request draft names, draft endpoints, unresolved refs, requirements before
submit, blocker ids, and retry conditions for a family. It proves the frontend
can show what the Owner would review and which official API-backed flow would
be used, without submitting any draft. Rows must keep
`not_authorization=true`, `not_execution_permission=true`,
`not_order_permission=true`, `creates_authorization=false`,
`creates_execution_intent=false`, `starts_runtime=false`,
`starts_strategy_execution=false`, `places_order=false`, and
`mutates_pg=false`.
`owner_review_handoff_matrix` is the top-level Owner/frontend handoff for risk
and scope review. Each row aggregates the risk disclosure, Owner-scope verdict,
budget envelope status, authorization draft status, confirmation phrase,
read-only review endpoint, official admission/risk-acceptance endpoints,
Operation Layer preflight/confirm endpoints, operation-chain bounds,
unresolved refs, blockers, and retry conditions. It proves that the frontend
can present an API-backed authorization path for review while the read model
itself submits nothing. Rows must keep `frontend_action_enabled=false`,
`action_enablement_source=backend_actionable_only`,
`not_authorization=true`, `not_execution_permission=true`,
`not_order_permission=true`, `read_model_submits_authorization=false`,
`creates_authorization=false`, `creates_execution_intent=false`,
`starts_runtime=false`, `starts_strategy_execution=false`,
`places_order=false`, `mutates_pg=false`, and `exchange_write_action=false`.
`official_api_request_draft_matrix` is the top-level per-family expansion of
the nested `families[*].api_request_drafts`. It lets the frontend and evidence
report display the official admission/Operation Layer request ladder without
drilling into family rows. At this revision it contains one row per family and
request draft:
`create_admission_evidence_packet`, `create_owner_regime_input`,
`create_admission_request`, `create_owner_risk_acceptance`, and
`operation_preflight_create_gated_trial_from_admission`. Each row includes the
family, strategy family id, carrier id, draft name, method, endpoint,
Owner-scope verdict, unresolved refs, requirements before submit, and payload
template keys. It is a review matrix only: every row must keep
`status=proposal_only_not_submitted`, `not_submitted=true`,
`action_allowed=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `starts_runtime=false`,
`starts_strategy_execution=false`, `places_order=false`,
`mutates_pg=false`, and `mutates_exchange=false`.
`live_action_eligibility_matrix` is the per-family hard-gate table for deciding
whether any sprint candidate may proceed to live action. It exposes checks for
complete Owner scope, official action API candidate support, backend final gate
actionability, pre-action PG/exchange snapshots, mandatory TP/SL plan,
execution intent, Review contract, and audit chain readiness. At this revision
each row has `eligibility=not_eligible`; rows must keep
`backend_actionable=false`, `frontend_action_enabled=false`,
`may_execute_live=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `starts_runtime=false`,
`starts_strategy_execution=false`, `places_order=false`, and `mutates_pg=false`.
`final_gate_readiness_matrix` is the frontend/report-facing final-gate summary
for each family. It includes the final-gate dry-run endpoint, execute endpoint,
current final-gate reason, Owner-scope verdict, reused eligibility checks,
blocking chain stages, blocker ids, and retry conditions. It is not a
final-gate call and does not execute the dry run. Every row must keep
`status=blocked`, `backend_actionable=false`,
`frontend_action_enabled=false`, `may_execute_live=false`,
`creates_authorization=false`, `creates_execution_intent=false`,
`starts_runtime=false`, `starts_strategy_execution=false`,
`places_order=false`, `mutates_pg=false`, and
`exchange_write_action=false`.
`production_action_decision_matrix` is the top-level per-family live-action
selection decision. It answers whether any candidate may proceed to production
execution. At this revision every row has `decision=do_not_execute` and
`selection_status=not_selected_for_live_action`, with the reason derived from
Owner scope, official action API support, and backend final-gate state. It
lists missing official evidence such as `final_gate_actionable_true`,
`execution_intent`, entry, TP/SL, post-action Review, and audit events. It is
the direct evidence that no live action is taken by this read model. Every row
must keep `live_action_taken=false`, `backend_actionable=false`,
`frontend_action_enabled=false`, `may_execute_live=false`,
`creates_authorization=false`, `creates_execution_intent=false`,
`starts_runtime=false`, `starts_strategy_execution=false`,
`places_order=false`, `mutates_pg=false`, and
`exchange_write_action=false`.
`objective_acceptance_audit_matrix` is the requirement-by-requirement audit of
the sprint objective. It maps strategy-family scope, full-chain adaptation,
Trading Console authorization path, StrategyGroup/Carrier alignment,
admission/risk control, Production Capital Boundary, live-action decision,
PG/exchange evidence, blocker/bridge coverage, final-report package, and
safety proof to `PASS`, `PASS_WITH_CONSTRAINT`, `DEFERRED`, or `BLOCKED`.
Rows include verification scope, completion evidence classification, evidence
refs, blocker ids, and retry condition. It is an audit artifact only and must
keep `action_allowed=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `starts_runtime=false`,
`starts_strategy_execution=false`, `places_order=false`, `mutates_pg=false`,
and `exchange_write_action=false`.
`acceptance_evidence_matrix` is the objective-level evidence matrix for this
production admission sprint. It maps explicit acceptance areas such as strategy
family candidates, StrategyGroup/Carrier mapping, Owner risk/scope review,
API-backed authorization flow, frontend action disablement, production capital
boundary, official action API support, backend final gate, PG/exchange
evidence, mandatory TP/SL, Review/Audit, and live action execution to
`PASS`, `PASS_WITH_CONSTRAINT`, `DEFERRED`, or `BLOCKED`. The matrix is evidence
and reporting material only: every row must keep `action_allowed=false`,
`creates_authorization=false`, `creates_execution_intent=false`,
`places_order=false`, and `mutates_pg=false`.
For the Trend row, `observation_bridge.bridge_method=TrendObservation` is a
first-class observation bridge only. It must keep `starts_runner=false`,
`creates_signal=false`, `creates_trade_intent=false`,
`creates_execution_intent=false`, `places_order=false`, and `mutates_pg=false`.
`risk_disclosure_contract` is a structured `RiskDisclosureDraft` for Owner
review. It lists failure modes and required acknowledgement context, while
keeping `not_authorization=true`, `not_execution_permission=true`, and
`not_order_permission=true`. The legacy `risk_disclosure_draft` string remains
available as summary copy.
`strategy_group_mapping` is a structured `StrategyGroupMappingProposal` that
binds family, strategy family id/type, strategy group, carrier id, admission
level, and classification. `carrier_candidate` is a structured
`CarrierCandidate` metadata bridge. It must keep `starts_runner=false`,
`creates_signal=false`, `creates_trade_intent=false`,
`creates_execution_intent=false`, `places_order=false`, and `mutates_pg=false`.
`carrier_readiness_report` is a structured `CarrierReadinessReport` with
readiness checks and blockers. Both mapping/readiness contracts must keep
`creates_execution_intent=false`, `places_order=false`, and `mutates_pg=false`;
`carrier_readiness_report.backend_actionable=false` and
`carrier_readiness_report.frontend_action_enabled=false` until backend
actionability is proven.
`budget_envelope_draft` is a structured `BudgetEnvelopeDraft` bridge for the
Production Capital Boundary. It exposes required scope fields, sanitized Owner
scope, provided/missing scope fields, validation checks, and owner-supplied
`symbol`, `side`, `quantity`, `max_notional`, `leverage`, `max_attempts`,
`protection_mode`, and `review_requirement`. It must use
`numbers_source=owner_scope_only_no_fabrication`; missing numeric values remain
null and are not inferred by the read model. It must keep
`not_authorization=true`, `not_execution_permission=true`,
`action_allowed=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `places_order=false`, and `mutates_pg=false`.
If a complete matching scope is supplied through query fields, the endpoint may
mark `scope_review.verdict` as `complete_dry_run_only` and
`final_gate_dry_run.gates[0]` as pass, while `backend_actionable` and
`frontend_action_enabled` remain false until a separate backend final gate and
official action contract exist.
`authorization_draft_proposal.not_authorization`,
`authorization_draft_proposal.not_execution_permission`, and
`authorization_draft_proposal.not_order_permission` must all remain true.
`candidate_pipeline_standard` records the BRC StrategyFamily to ActionCandidate
standard. It defines AdmissionLevel `L0` through `L4`, the warning vs hard
blocker split, the required spec order
`StrategyFamilySpec -> StrategyGroupSpec -> CarrierSpec -> RiskDisclosureSpec
-> ReviewTemplate -> ActionCandidateSpec`, and the official action path. It
must keep `no_action_guarantee.creates_authorization=false`,
`no_action_guarantee.creates_execution_intent=false`,
`no_action_guarantee.places_order=false`, `no_action_guarantee.starts_runtime=false`,
and `no_action_guarantee.mutates_pg=false`.
`candidate_output` is the concise Trading Console read-only candidate list for
Owner/UI consumption. Each row includes family, strategy family id, carrier id,
AdmissionLevel, candidate state, ActionCandidate status, action-registry support,
warning count, hard-blocker count, and owner decision text. At this revision
Trend may appear as `L3` / `bounded_live_candidate`; Volatility expansion and
Mean reversion remain `L2` / `proposal`. All rows must keep
`frontend_action_enabled=false` and `may_execute_live=false` until the official
backend final gate and action path return an auditable executable result.
`strategy_family_specs`, `strategy_group_specs`, `carrier_specs`,
`risk_disclosure_specs`, `review_templates`, and `action_candidate_specs` expose
the full standard artifacts for frontend documentation and future generic
ActionSpec work. Weak strategy evidence, incomplete signal markers,
fee/funding/slippage gaps, incomplete review UI, and non-core read-model
degradation are warnings/risk disclosure items, not live-action hard blockers.
Hard blockers for live action are restricted to missing Owner execute
authorization, scope mismatch, unreadable/conflicting exposure, unavailable
TP/SL plan, unavailable intent/order/review/audit recording, runtime/profile/env
or credential guard blocks, or a carrier that cannot produce a valid
ActionCandidate.

### `GET /api/trading-console/action-entry-readiness`

Purpose: read-only bridge from `ActionCandidateSpec` to a generic official
action-entry contract for Owner review and frontend disabled-state rendering.

Optional query fields include Owner market input and the same read-only Owner
scope review fields as `strategy-family-admission-state`:

- `market_regime`
- `symbol_preference`
- `risk_tier`
- `note`

- `family`
- `strategy_family_id`
- `carrier_id`
- `symbol`
- `side`
- `quantity`
- `max_notional`
- `leverage`
- `max_attempts`
- `protection_mode`
- `review_requirement`

`data` fields:

- `owner_market_input`
- `selected_candidate`
- `risk_review`
- `authorization_draft_path`
- `final_gate_result`
- `action_state`
- `post_action_state`
- `generic_final_gate_adapter_contract`
- `generic_action_specs`
- `action_entry_payload_contracts`
- `action_entry_output`
- `candidate_output`

`owner_market_input` is normalized from query parameters only and must keep
`persisted=false`. It does not create an Owner authorization, execution intent,
or PG record. `selected_candidate` resolves the current candidate from
`candidate_output`, `generic_action_specs`, `action_entry_payload_contracts`,
and `action_entry_output`, and includes `scope_review` for exact Owner scope
matching.

`risk_review` separates warnings from hard blockers. Weak strategy evidence
remains `warning_not_hard_blocker`. `authorization_draft_path` exposes whether
an official service path exists for a future draft but must keep
`creates_authorization=false`, `creates_execution_intent=false`, and
`places_order=false`. `final_gate_result` exposes pass/block/proposal status,
blocker ids, retry conditions, and evidence status while keeping
`may_execute_live=false` and `frontend_action_enabled=false` in this read-only
revision.

`action_state` is the frontend action-slot contract. The action slot may render
as enabled only when backend returned actionability flags are true; current v1
readiness responses keep `enabled=false`, `may_execute_live=false`,
`frontend_action_enabled=false`, `places_order=false`, and `mutates_pg=false`.
`post_action_state` summarizes existing intent, entry, TP/SL, review, and audit
facts when present; it must not fabricate missing post-action evidence.

`generic_action_specs` is the first-class generic action contract layer. Trend
may expose `TF-001-live-readonly-v0` as `status=valid_blocked_final_gate` with
exact scope `SOL/USDT:USDT`, `long`, qty `0.1`, max notional `20`, leverage `1`,
max attempts `1`, and `protection_mode=single_tp_plus_sl`. Mean reversion may
expose `MR-001-live-readonly-v0` as a complete proposal template with exact
scope `ETH/USDT:USDT`, `long`, qty `0.01`, max notional `20`, leverage `1`, max
attempts `1`, and `protection_mode=single_tp_plus_sl`, but it must remain
`status=proposal_non_action`, `action_registry_supported=false`, and
`frontend_action_enabled=false` unless explicitly added to the official action
registry in a later sprint. Volatility expansion remains a proposal/non-action
candidate unless advanced later.

`generic_final_gate_adapter_contract` defines the hard live-action gates:
exact Owner execute authorization, scope match, readable and non-conflicting PG
and exchange exposure, valid mandatory TP/SL plan, intent/order/review/audit
recording readiness, and runtime/profile/env/credential guard pass. Weak
strategy evidence, incomplete signal markers, fee/funding/slippage gaps,
incomplete review UI, and non-core read-model degradation are warnings, not hard
blockers.

This endpoint is GET-only and never creates an authorization, execution intent,
order, protection order, review, runtime start, or PG mutation. Every row in
`generic_action_specs`, `action_entry_payload_contracts`, and
`action_entry_output` must keep `frontend_action_enabled=false`,
`may_execute_live=false`, and write/action flags false until a future official
final gate returns an auditable executable result.
`official_action_api_inventory` records the current official BRC action API
inventory for transition review. At this revision it supports
`MI-001-BNB-LONG` and exact Trend carrier `TF-001-live-readonly-v0`;
`trading_console_action_api_exposed=false`.
`action_api_compatibility.compatible=false` for sprint candidates that are not
supported by the current Owner trial-flow and bounded-execution registries.
`action_candidate` is a structured `ActionCandidate` bridge for disabled action
review. It lists official action endpoints, required gates, and blockers, while
keeping `action_allowed=false`, `backend_actionable=false`,
`frontend_action_enabled=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `places_order=false`, and `mutates_pg=false`.
`protection_plan_draft` is a structured `ProtectionPlanDraft`. It must require
`TP` and `SL`, expose validation checks, list missing `take_profit_price` and
`stop_loss_price`, and mark exchange protection order ids as
`not_created_by_read_model`. It must not fabricate TP/SL prices or protection
order ids, and must keep `action_allowed=false`, `creates_order=false`,
`places_order=false`, and `mutates_pg=false`.
`review_contract` is a structured `ReviewContract` draft. It lists required
post-action evidence and missing evidence such as execution intent, entry
order, TP/SL orders, post-action PG/exchange snapshots, and audit log events.
It must keep `promotion_allowed=false`, `records_review=false`,
`creates_execution_intent=false`, `places_order=false`, and `mutates_pg=false`.
`api_backed_authorization_flow` records the existing BRC admission and Operation
Layer API ladder for metadata-backed Owner review and confirmation. The ladder
uses `/api/brc/admissions/*` and `/api/brc/operations/*`; every listed step in
this read model must have `creates_execution_intent=false` and
`places_order=false`. It is an authorization/admission bridge, not a Trading
Console direct action API.
`pg_exchange_evidence_matrix` enumerates required pre-action and post-action PG
tables, exchange read sources, and audit sources for a future official live
action. At this revision every row has `status=required_not_collected`,
`evidence_ref=null`, and
`collection_policy=official_service_or_api_path_only_no_manual_pg_edits`.
Rows must keep `read_only=true`, `mutates_pg=false`,
`exchange_write_action=false`, and `places_order=false`.
`family_evidence_collection_matrix` expands those same evidence requirements
per family. Each row includes family, strategy family id, carrier id, phase,
required chain stage, source type, source, collection policy, evidence ref,
official collection path, and retry condition. At this revision every row has
`status=required_not_collected` and `evidence_ref=null`. It is a future
evidence collection contract only; rows must keep `read_only=true`,
`creates_authorization=false`, `creates_execution_intent=false`,
`exchange_write_action=false`, `places_order=false`, and `mutates_pg=false`.
`evidence_collection_summary_matrix` is the per-family summary of those
required evidence rows. Each family summary includes total required evidence,
collected count, required-not-collected count, phase counts, source-type
counts, official collection paths, and missing source keys. At this revision
each family has no collected live-action evidence and remains
`blocked_required_not_collected`; rows must keep `read_only=true`,
`creates_authorization=false`, `creates_execution_intent=false`,
`exchange_write_action=false`, `places_order=false`, and `mutates_pg=false`.
`scoped_dry_run_examples` contains one read-only Owner-scope query example per
strategy family. The examples are contract/test fixtures for frontend handoff
and API verification: they demonstrate that a complete bounded scope can be
reviewed as `complete_dry_run_only`, while the candidate still remains blocked
by official action API support and backend final-gate actionability. They are
not Owner authorization, not execution permission, and not an order template.
Every example must keep `not_owner_authorization=true`,
`action_allowed=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `starts_runtime=false`,
`starts_strategy_execution=false`, `places_order=false`, and
`mutates_pg=false`.
`official_transition_readiness_matrix` expands that ladder into ordered
transition readiness rows. It includes proposal-only admission request and
risk-acceptance API transitions, metadata-available Operation Layer preflight
transitions, and blocked `final_gate_dry_run` / `execute_authorization` rows.
Every row must keep `action_allowed=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `starts_runtime=false`,
`starts_strategy_execution=false`, `places_order=false`, and `mutates_pg=false`.
The matrix is route/readiness evidence only; it does not submit admission,
operation, final-gate, or execution requests.
`chain_stage_states` must cover the full
StrategyFamily -> StrategyGroup -> Carrier -> RiskDisclosure ->
AuthorizationDraft -> BoundedLiveAuthorization -> ExecutionIntent -> Entry ->
TP/SL -> Review chain. `pre_post_evidence_contract` lists required PG tables and
exchange read-only evidence for any future live action; this read model does not
collect live action evidence and must keep `mutation_allowed_by_read_model=false`.
`gate_blocker_records` are first-class `BlockerRecord` rows for active
scope/action-api/final-gate/evidence/protection/review blockers. Top-level
`blocker_records` aggregates the family blocker and gate blockers.
`pre_execution_blocked_review` is a structured `PreExecutionBlockedReview`,
exposed both top-level and per family. It summarizes the owner scope,
official action API compatibility, backend final gate, pre-action PG/exchange
evidence, mandatory TP/SL, and review-contract checks. It must keep
`status=blocked`, `action_allowed=false`, `frontend_action_enabled=false`,
`creates_execution_intent=false`, `places_order=false`, and `mutates_pg=false`.
`audit_chain_gap_report` is a structured `AuditChainGapReport`, exposed both
top-level and per family. It must report `gap_open_no_live_action_evidence`,
list present proposal evidence, list missing official action/audit evidence,
and keep `live_action_evidence_present=false`, `creates_execution_intent=false`,
`places_order=false`, and `mutates_pg=false`.
`api_request_drafts` contains proposal-only payload templates for the BRC
admission and Operation Layer APIs. They must keep `not_submitted=true`,
`creates_execution_intent=false`, `places_order=false`, and include unresolved
reference fields rather than fabricated IDs.
`admission_verdict` and `sprint_acceptance_verdict` are acceptance/readiness
summaries only. They must keep `may_execute_live=false`,
`live_execution_ready=false`, and `frontend_action_enabled=false` until backend
actionability and evidence are proven by official state.
`family_final_report_matrix` is the per-family final-report row set. Each row
compresses completed work, StrategyGroup/Carrier mapping, admission/risk
control, Trading Console authorization readiness, live-action decision,
PG/exchange evidence, blockers, retry conditions, bridge methods, evidence
refs, and safety flags into one Owner/report-facing object. It is a summary of
the detailed matrices and must keep `live_action_taken=false`,
`runtime_started=false`, `backend_actionable=false`,
`frontend_action_enabled=false`, `may_execute_live=false`,
`creates_authorization=false`, `creates_execution_intent=false`,
`starts_strategy_execution=false`, `places_order=false`, `mutates_pg=false`,
and `exchange_write_action=false`.
`final_report_package` is the top-level final-report handoff summary. It
groups report sections for completed work by family, StrategyGroup/Carrier
mapping, admission/risk-control changes, Trading Console authorization
readiness, live actions, PG/exchange evidence, BlockerRecords and bridge
artifacts, checks, retry conditions, and safety proof. It references the
structured matrices in this response rather than duplicating all rows. It is a
reporting artifact only and must keep `live_actions_taken=false`,
`runtime_started=false`, `pg_mutation=false`, `exchange_write_action=false`,
`credentials_changed=false`, `deploy_performed=false`, and
`push_performed=false`.

### `GET /api/trading-console/owner-action-flow`

Purpose: Owner-facing read-only superset of `action-entry-readiness` for the
Console action-flow page. It keeps the same query fields as
`action-entry-readiness` and returns the same underlying action-entry data plus
`data.owner_action_flow`.

`data.owner_action_flow` fields:

- `status`: `actionable` only if backend action-state flags are true; otherwise
  `not_actionable`.
- `unsafe_action_enabled`: must remain `false` unless a future backend
  executable state is explicitly returned through the official path.
- `flow_steps`: structured stages for `market_input`, `candidate_selection`,
  `risk_disclosure`, `authorization_draft`, `final_gate`, `action_state`, and
  `post_action_evidence`.
- `timeline`: compact post-action evidence counts for intents, entry orders,
  TP/SL orders, review, audit events, and retry safety.

This endpoint is GET-only. It does not create Owner market input,
authorization drafts, execution intents, orders, reviews, audit events, runtime
starts, or PG mutations. The frontend may use it as the primary Action Entry /
Owner Action Flow truth source because it is a superset of the existing
readiness contract.

### `GET /api/trading-console/signal-marker-feed`

Purpose: backend event marker feed for future chart integration.

`data` fields:

- `markers`
- `chart_adapter`

### `GET /api/trading-console/api-classification`

Purpose: namespace governance and frontend migration support.

`data` fields:

- `trading_console_v1_allowed`
- `internal_or_legacy`
- `action_api_policy`
- `sample_data_policy`

## Known Gaps

- No fills table.
- No stored `client_order_id`.
- No stored fee/funding/slippage fields in the v1 order ledger.
- Optional recovery/audit tables may be absent in a deployment; absence is
  reported as `unavailable`, not as clean state.
- Chart rendering and TradingView/lightweight-charts frontend integration are
  out of scope for this backend sprint.

## Warning Policy

Post-live TP/SL open orders, orphan protection, stale facts, and PG/exchange
drift are represented as warnings/degraded facts and do not stop read-model
generation.

## Gate 2 Frontend Constraints

- `/api/trading-console/*` is the only allowed frontend namespace for Trading
  Console read-model facts in Gate 2.
- `/api/brc/*`, `/api/runtime/*`, and `/api/dev/testnet/brc/*` are internal,
  legacy, or dev/testnet-only surfaces for Trading Console frontend purposes.
- `not_live_connected` must not be displayed as account-safe or exchange-clean;
  it only means exchange reads were not requested.
- `unavailable` must never be treated as clean state by the frontend.
- `deferred_actions`, `future_action_slots`, and `deferred_execute_endpoint`
  are disabled/unavailable UI states, not callable actions.
- Carrier Shelf v1 is the current BNB-first carrier surface. It is not the
  final multi-carrier product shelf.
- Signal marker feed is available as a backend feed for later chart work, but
  chart rendering and TradingView/lightweight-charts integration are not Gate 2
  P0 requirements.
