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

# BRC Production Strategy-Family Admission Sprint - 2026-06-04

Status: PASS_WITH_CONSTRAINT

This artifact records the current production-admission state for the three
Owner-requested strategy families. It is a bridge/dry-run/proposal package, not
a live execution record. No runtime was started and no live order/cancel/replace
/flatten/retry-protection action was executed while producing this package.

## Scope Boundary

Allowed chain:

```text
StrategyFamily
-> StrategyGroup
-> Carrier
-> RiskDisclosure
-> AuthorizationDraft
-> BoundedLiveAuthorization
-> ExecutionIntent
-> Entry
-> TP/SL
-> Review
```

Live production execution remains blocked for every new candidate in this
artifact because no candidate has a complete explicit Owner scope containing all
of:

```text
symbol, side, quantity, max_notional, leverage, max_attempts,
protection_mode, review_requirement
```

The prior BNB one-shot authorization and closeout evidence must not be reused as
generic action permission.

## Current Repo Evidence

| Area | Current evidence |
| --- | --- |
| Production admission builder | `src/application/production_strategy_family_admission.py` builds structured family rows, `BlockerRecord`, `BudgetEnvelopeDraft`, `FinalGateDryRun`, `ProtectionPlanDraft`, and `ReviewContract` without side effects. |
| Trading Console read model | `src/application/readmodels/trading_console.py` exposes GET-only read models and reports `is_actionable` from backend authorization state. |
| Trading Console API | `src/interfaces/api_trading_console.py` exposes only `/api/trading-console/*` GET endpoints. |
| Production admission read model | `GET /api/trading-console/strategy-family-admission-state` maps the three sprint families, their blockers, bridge artifacts, backend actionability state, and optional read-only Owner scope dry-run. |
| Production baseline context | `production_baseline_context` records prior BNB-only execute/closeout and post-close flat report references as historical context only; it grants no new strategy-family authorization and requires fresh PG/exchange evidence before any future live action. |
| Admission/risk-control summary | `admission_risk_control_matrix` aggregates admission level, risk disclosure, budget, authorization, final gate, TP/SL, review, audit, blockers, and retry conditions per family without enabling actions. |
| Owner bounded execution | `src/application/owner_bounded_execution.py` is the production action path used by prior scoped BNB evidence. |
| BRC admission | `src/domain/brc_admission.py` and `src/application/brc_admission_service.py` provide admission decision, constraint, risk acceptance, binding, preflight, and non-executable trial-trade intent records. |
| Strategy registry | `src/domain/strategy_family_registry.py` now contains Trend, Volatility Breakout, and Mean Reversion metadata candidates. |
| Runtime-bound schema | Alembic head includes revision `042` for runtime `signals` schema reproducibility. |

## Family Mapping

| Family | StrategyFamily | StrategyGroup | Carrier candidate | Admission level | Current classification |
| --- | --- | --- | --- | --- | --- |
| Trend | `TF-001-live-readonly-v0` | Major trend continuation / trend following | `TF-001-live-readonly-v0` carrier-validation playbook | Observation carrier validation | dry-run-only |
| Volatility expansion | `VB-001-live-readonly-v0` | Volatility contraction / breakout release | `VB-001-live-readonly-v0` hypothesis playbook | Hypothesis intake | blocked |
| Mean reversion | `MR-001-live-readonly-v0` | Range stretch / snapback | `MR-001-live-readonly-v0` hypothesis playbook | Hypothesis intake | blocked |

Legacy note: `CPM-RO-001` remains in the registry as pullback continuation
revalidation. It is not used as the mean-reversion family for this sprint.

## Chain State By Family

### Trend

| Stage | State | Evidence / bridge |
| --- | --- | --- |
| StrategyFamily | available | `TF-001-live-readonly-v0` registry seed |
| StrategyGroup | mapped | Trend following / major trend continuation |
| Carrier | dry-run-only | Existing carrier-validation playbook, no new live authorization |
| RiskDisclosure | draft-required | Strategy warnings: weak current alpha proof, regime uncertainty, false continuation |
| AuthorizationDraft | proposal-only | Needs new scoped Owner authorization; prior BNB auth is consumed/scope-specific |
| BoundedLiveAuthorization | blocked | Missing complete numeric production scope |
| ExecutionIntent | not-created | No official action path invoked for new Trend candidate |
| Entry | not-executed | Blocked before live action |
| TP/SL | protection-plan-draft-only | Mandatory TP/SL requirement preserved |
| Review | review-contract-draft | Review required before any admission promotion |
| Audit | audit-chain-gap-recorded | No new action audit exists because no action occurred |

### Volatility Expansion

| Stage | State | Evidence / bridge |
| --- | --- | --- |
| StrategyFamily | available | `VB-001-live-readonly-v0` registry seed |
| StrategyGroup | mapped | Contraction followed by breakout/release |
| Carrier | candidate-only | No runner/evaluator activation |
| RiskDisclosure | draft-required | Failure modes: fake breakout, news wick, low-volume breakout |
| AuthorizationDraft | proposal-only | Needs scoped symbol/side/quantity/notional/leverage/attempts |
| BoundedLiveAuthorization | blocked | No explicit Owner numeric scope |
| ExecutionIntent | not-created | No official action path invoked |
| Entry | not-executed | Blocked before live action |
| TP/SL | protection-plan-draft-only | Must define stop basis and TP before any actionability |
| Review | review-contract-draft | Must review false breakout and follow-through metrics |
| Audit | audit-chain-gap-recorded | No live audit because no action occurred |

### Mean Reversion

| Stage | State | Evidence / bridge |
| --- | --- | --- |
| StrategyFamily | available | `MR-001-live-readonly-v0` registry seed |
| StrategyGroup | mapped | Range stretch / snapback |
| Carrier | candidate-only | Metadata-only, no evaluator activation |
| RiskDisclosure | draft-required | Failure modes: catching falling knife, range break into trend, liquidity wick |
| AuthorizationDraft | proposal-only | Needs scoped symbol/side/quantity/notional/leverage/attempts |
| BoundedLiveAuthorization | blocked | No explicit Owner numeric scope |
| ExecutionIntent | not-created | No official action path invoked |
| Entry | not-executed | Blocked before live action |
| TP/SL | protection-plan-draft-only | Stop must dominate range-break risk before any actionability |
| Review | review-contract-draft | Must review snapback follow-through and trend-break failures |
| Audit | audit-chain-gap-recorded | No live audit because no action occurred |

## BlockerRecords

```json
[
  {
    "id": "BRC-PROD-ADMIT-20260604-TREND-001",
    "stage": "BoundedLiveAuthorization",
    "blocked_path": "Trend -> TF-001-live-readonly-v0 -> production entry",
    "evidence": "No complete new Owner scope exists for symbol, side, quantity, max_notional, leverage, max_attempts, protection_mode, review_requirement.",
    "severity": "hard_blocker",
    "bridge_method": "AuthorizationDraftProposal",
    "next_retry_condition": "Owner provides explicit Trend candidate production scope and backend final gate returns actionable=true."
  },
  {
    "id": "BRC-PROD-ADMIT-20260604-VOL-001",
    "stage": "CarrierReadinessReport",
    "blocked_path": "Volatility expansion -> VB-001-live-readonly-v0 -> production entry",
    "evidence": "Candidate is registered_hypothesis_only with no runner/evaluator activation and no complete Owner numeric scope.",
    "severity": "hard_blocker",
    "bridge_method": "CarrierReadinessReport",
    "next_retry_condition": "Evaluator/readiness evidence exists and Owner provides explicit scoped production authorization."
  },
  {
    "id": "BRC-PROD-ADMIT-20260604-MR-001",
    "stage": "CarrierCandidate",
    "blocked_path": "Mean reversion -> MR-001-live-readonly-v0 -> production entry",
    "evidence": "Mean-reversion candidate is metadata-only and lacks evaluator/readiness evidence plus complete Owner numeric scope.",
    "severity": "hard_blocker",
    "bridge_method": "CarrierCandidate",
    "next_retry_condition": "MR evaluator/readiness evidence exists and Owner provides explicit scoped production authorization."
  }
]
```

## Bridge Artifacts

| Bridge method | Artifact in this sprint |
| --- | --- |
| TrendObservation | Trend row first-class observation bridge; observation only, no runner start, signal, trade intent, execution intent, order, or PG mutation |
| StrategyGroupMappingProposal | Structured family -> strategy group -> carrier mapping row for each candidate |
| CarrierCandidate | Structured carrier metadata candidate for each family; no runner, signal, intent, order, or PG mutation |
| CarrierReadinessReport | Structured carrier readiness checks and blockers, with backend/frontend action disabled |
| ActionCandidate | Structured disabled-action candidate review; lists official endpoints, required gates, and blockers without creating authorization or orders |
| RiskDisclosureDraft | Structured Owner-review risk disclosure by family, including failure modes and explicit non-authorization flags |
| AuthorizationDraftProposal | Structured `authorization_draft_proposal` rows with confirmation phrase, sanitized scope, risk disclosure, and explicit non-permission flags |
| OwnerReviewHandoffMatrix | Top-level Owner/frontend handoff for risk/scope review and API-backed authorization path visibility; no submit, no authorization creation, no intent, no order |
| ApiBackedAuthorizationFlow | Existing BRC admission + Operation Layer endpoint ladder for metadata-backed Owner review/confirmation |
| OfficialTransitionReadinessMatrix | Ordered official API transition readiness rows for proposal-only admission/risk acceptance, metadata-available Operation Layer preflight, and blocked final-gate/execute transitions |
| OfficialActionApiInventory | Current official action API endpoints and supported carrier registry; currently BNB-only for `MI-001-BNB-LONG` |
| ChainStageState | Per-family StrategyFamily -> Review state list for frontend and audit evidence |
| PrePostEvidenceContract | Required PG/exchange pre/post evidence contract for any future live action |
| PgExchangeEvidenceMatrix | Top-level pre/post PG table, exchange read, and audit source matrix; all evidence rows remain required/not collected by the read model |
| FamilyEvidenceCollectionMatrix | Per-family expansion of the PG/exchange/audit evidence requirements for Entry and Review stages; all rows remain required/not collected |
| EvidenceCollectionSummaryMatrix | Per-family summary of required/not-collected PG, exchange, and audit evidence |
| ScopedDryRunExamples | Per-family read-only Owner-scope query examples for frontend/API verification; examples are not authorization and cannot enable action |
| GateBlockerRecords | First-class blocker rows for scope, action API, final gate, evidence, TP/SL, and review gates |
| ApiRequestDrafts | Proposal-only official API payload templates with unresolved refs and no execution authority |
| OfficialApiRequestDraftMatrix | Top-level per-family official API draft summary; 3 families x 5 request drafts, all proposal-only and not submitted |
| AdmissionVerdict | Per-family acceptance/readiness verdict and remaining requirements |
| SprintAcceptanceVerdict | Top-level sprint completion status and global remaining requirements |
| FamilyFinalReportMatrix | Per-family final-report row for Owner/report handoff across all acceptance areas |
| BudgetEnvelopeDraft | Structured Production Capital Boundary bridge with sanitized Owner scope, provided/missing scope fields, validation checks, owner-supplied symbol/side/quantity/max_notional/leverage/max_attempts/protection/review fields, no numeric fabrication, and no authorization/intent/order/PG mutation |
| ProductionCapitalBoundaryMatrix | Top-level per-family Production Capital Boundary summary; copies only Owner-supplied scope values, records missing fields, and keeps all scope/action expansion flags false |
| FinalGateDryRun | Blocked before final gate because scope is incomplete |
| FinalGateReadinessMatrix | Per-family final-gate hard-gate summary for frontend/reporting; blocked, no dry-run execution, no order |
| ProductionActionDecisionMatrix | Per-family live-action selection decision; all rows `do_not_execute`, no live action taken |
| PreExecutionBlockedReview | Structured top-level and per-family pre-execution review; summarizes scope, action API, final gate, evidence, TP/SL, and Review checks while keeping action disabled |
| ProtectionPlanDraft | Structured mandatory TP/SL draft with validation checks, missing TP/SL prices, no fabricated exchange order ids, and no order placement |
| ReviewContract | Structured post-action review draft with required/missing evidence, promotion disabled, and no review PG write |
| AuditChainGapReport | Structured top-level and per-family audit gap report; proposal evidence is present, official action/audit evidence remains missing because no new live action was taken |

`bridge_artifact_statuses` now provides the top-level bridge coverage matrix:
one row per bridge method, families covered, per-family row statuses, evidence,
and next retry condition. The matrix is summary evidence only and keeps
`action_allowed=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `places_order=false`, and `mutates_pg=false`.

`acceptance_evidence_matrix` now provides the objective-level acceptance
evidence matrix for final reporting. It covers strategy family candidate
presence, StrategyGroup/Carrier mapping, Owner risk/scope review, API-backed
authorization flow, frontend action disablement, production capital boundary,
official action API support, backend final gate, PG/exchange evidence,
mandatory TP/SL, Review/Audit, and live action execution. Rows are classified
as `PASS`, `PASS_WITH_CONSTRAINT`, `DEFERRED`, or `BLOCKED`; the matrix is not
an action source and keeps authorization/intent/order/PG mutation flags false.

`objective_acceptance_audit_matrix` now provides the requirement-by-requirement
audit against the sprint objective. It covers the strategy-family scope,
per-family full chain, Trading Console authorization path, family/group/carrier
alignment, admission/risk control, Production Capital Boundary, live-action
decision, PG/exchange evidence, blocker/bridge coverage, final-report package,
and safety proof. It is audit evidence only and keeps action/authorization/
intent/runtime/order/PG/exchange-write flags false.

`family_completion_matrix` provides the per-family final-report summary:
family, strategy family id, strategy group, carrier id, classification,
completion status, completed/blocked stages, blocker ids, bridge methods,
evidence refs, and retry conditions. It is summary evidence only and keeps
backend/frontend action disabled.

`scoped_dry_run_examples` provides one complete bounded-scope query example per
family:

```text
Trend -> TF-001-live-readonly-v0
Volatility expansion -> VB-001-live-readonly-v0
Mean reversion -> MR-001-live-readonly-v0
```

These examples are frontend/API verification fixtures only. They can be
replayed against `GET /api/trading-console/strategy-family-admission-state` to
prove a complete matching Owner scope is rendered as
`complete_dry_run_only`, while final gate remains blocked with
`official_action_api_candidate_not_supported`. They must keep
`not_owner_authorization=true`, `action_allowed=false`,
`creates_authorization=false`, `creates_execution_intent=false`,
`starts_runtime=false`, `starts_strategy_execution=false`,
`places_order=false`, and `mutates_pg=false`.

`evidence_collection_summary_matrix` summarizes the required PG/exchange/audit
evidence per family. It compresses the detailed
`family_evidence_collection_matrix` into one row per family with total required
evidence, collected count, required-not-collected count, phase counts,
source-type counts, official collection paths, and missing source keys. At this
revision every family remains `blocked_required_not_collected`, with no
collected live-action evidence and no PG/exchange mutation by the read model.
Rows keep `read_only=true`, `creates_authorization=false`,
`creates_execution_intent=false`, `exchange_write_action=false`,
`places_order=false`, and `mutates_pg=false`.

`official_api_request_draft_matrix` provides the top-level Owner authorization
route evidence. It expands each family row's `api_request_drafts` into 15
summary rows:

```text
3 families x 5 draft requests
create_admission_evidence_packet
create_owner_regime_input
create_admission_request
create_owner_risk_acceptance
operation_preflight_create_gated_trial_from_admission
```

The matrix is an official API review ladder, not a submitter. Rows expose
method, endpoint, unresolved refs, requirements before submit, Owner-scope
verdict, and payload template keys while keeping
`status=proposal_only_not_submitted`, `not_submitted=true`,
`action_allowed=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `starts_runtime=false`,
`starts_strategy_execution=false`, `places_order=false`, `mutates_pg=false`,
and `mutates_exchange=false`.

`final_gate_readiness_matrix` gives the frontend and report a direct per-family
hard-gate summary. It records the final-gate dry-run endpoint, execute endpoint,
final-gate reason, Owner-scope verdict, eligibility checks, blocking chain
stages, blocker ids, and retry conditions. It does not invoke final gate and
does not execute. Rows remain `status=blocked` and keep
`backend_actionable=false`, `frontend_action_enabled=false`,
`may_execute_live=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `starts_runtime=false`,
`starts_strategy_execution=false`, `places_order=false`, `mutates_pg=false`,
and `exchange_write_action=false`.

`production_action_decision_matrix` records the final per-family action
selection decision. At this revision all rows are
`decision=do_not_execute` and `selection_status=not_selected_for_live_action`.
The reason is derived from scope completeness, official action API support, and
backend final-gate state; missing evidence includes the absent final-gate
actionable decision, execution intent, entry, TP/SL orders, Review, and audit
events. This matrix is the report-facing proof that no sprint candidate was
selected for production execution. Rows keep `live_action_taken=false`,
`backend_actionable=false`, `frontend_action_enabled=false`,
`may_execute_live=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `starts_runtime=false`,
`starts_strategy_execution=false`, `places_order=false`, `mutates_pg=false`,
and `exchange_write_action=false`.

`family_final_report_matrix` is the per-family final-report handoff row. It
compresses completed work, StrategyGroup/Carrier mapping, admission/risk
control, Trading Console authorization readiness, live-action decision,
PG/exchange evidence, blockers, bridge methods, retry conditions, evidence
refs, and safety proof into one row per family. It is derived from the detailed
matrices and must keep `live_action_taken=false`, `runtime_started=false`,
`backend_actionable=false`, `frontend_action_enabled=false`,
`may_execute_live=false`, `creates_authorization=false`,
`creates_execution_intent=false`, `starts_strategy_execution=false`,
`places_order=false`, `mutates_pg=false`, and `exchange_write_action=false`.

`admission_risk_control_matrix` provides the per-family admission/risk-control
handoff row:

```text
family
strategy_family_id
strategy_group
carrier_id
admission_level
classification
scope_review_verdict
risk_disclosure_status
budget_envelope_status
authorization_draft_status
bounded_live_authorization_status
action_api_status
final_gate_status / final_gate_reason
protection_plan_status
review_contract_status
audit_chain_status
blocker_ids
next_retry_conditions
```

It is derived from existing family row contracts only. It must keep:

```text
backend_actionable = false
frontend_action_enabled = false
may_execute_live = false
action_allowed = false
creates_authorization = false
creates_execution_intent = false
starts_runtime = false
starts_strategy_execution = false
places_order = false
mutates_pg = false
```

`full_chain_evidence_matrix` provides the top-level family/stage evidence
matrix for final reporting. It contains one row per family and chain stage:

```text
StrategyFamily
StrategyGroup
Carrier
RiskDisclosure
AuthorizationDraft
BoundedLiveAuthorization
ExecutionIntent
Entry
TP/SL
Review
```

Each row carries stage order, status, bridge method, evidence, required
evidence refs, blocker ids, and next retry conditions. It lets the report show
exactly where the chain advances and where it stops without traversing each raw
family payload. It is not an action source and keeps authorization, intent,
runtime, strategy execution, order, and PG mutation flags false.

`protection_review_audit_matrix` provides the per-family TP/SL + Review +
Audit readiness row. It aggregates mandatory protection components, missing
TP/SL fields, unavailable exchange protection order ids, review required and
missing evidence, audit present/missing evidence, audit sources, blockers, and
retry conditions. It makes the protection/review/audit gap explicit without
creating protection orders, recording a review, or writing audit evidence.

`blocker_retry_matrix` provides the family-preserving blocker/retry table. It
expands each primary blocker and gate blocker with family, strategy family id,
carrier id, stage, bridge method, evidence, next retry condition, and concrete
retry requirements. This is the table to use for final report retry
conditions; it keeps `retry_ready=false` and does not start runtime, create
authorization, create execution intent, place orders, or mutate PG.

`owner_authorization_packet_matrix` provides the per-family Owner review packet
for the Trading Console authorization path. Each row aggregates:

```text
risk_disclosure_status
budget_envelope_status
authorization_draft_status
confirmation_phrase_required
api_request_draft_names
draft_endpoints
unresolved_refs
required_before_submit
blocker_ids
next_retry_conditions
```

This matrix shows that the Owner can review the proposed scope/risk and the
API-backed admission/Operation Layer route, while also showing why no
authorization has been created. It keeps `not_authorization=true`,
`not_execution_permission=true`, `not_order_permission=true`,
`creates_authorization=false`, `creates_execution_intent=false`,
`starts_runtime=false`, `starts_strategy_execution=false`,
`places_order=false`, and `mutates_pg=false`.

`live_action_eligibility_matrix` provides the per-family hard-gate decision
table. It checks Owner scope, official action API support, backend final gate,
pre-action PG/exchange snapshots, mandatory TP/SL, execution intent, Review
contract, and audit chain readiness. Current rows are `not_eligible`; this is
the explicit reason no live action is executed by the sprint read model.

`pg_exchange_evidence_matrix` provides top-level evidence collection
requirements for final reporting. It enumerates pre/post PG tables, pre/post
exchange reads, and audit sources. Current rows are `required_not_collected`
with `evidence_ref=null`; the collection policy remains
`official_service_or_api_path_only_no_manual_pg_edits`.

`family_evidence_collection_matrix` expands that evidence contract per family.
For each of Trend, Volatility expansion, and Mean reversion it lists the
required pre-action PG/exchange evidence for `Entry`, post-action PG/exchange
evidence for `Review`, and audit sources for `Review`. Current rows are
`required_not_collected` with `evidence_ref=null`; the read model does not
collect evidence, write PG, place orders, or perform exchange write actions.

`official_transition_readiness_matrix` provides ordered route evidence for the
official API path. Admission request and risk acceptance rows are
`proposal_only`; Operation Layer rows are `metadata_available`; final-gate and
execute rows are `blocked`. The matrix is not an action trigger and keeps
authorization, runtime, strategy execution, intent, order, and PG mutation flags
false.

## Trading Console Authorization Readiness

The current Trading Console contract is safe for product display:

- `GET /api/trading-console/strategy-family-admission-state` exposes the
  strategy-family admission state for Owner review;
- the same endpoint accepts optional scope query fields for read-only dry-run
  review and never creates authorization, intent, order, or PG mutation;
- frontend action state must remain disabled unless backend returns
  `is_actionable=true`;
- `/api/trading-console/authorization-state` is read-only;
- `/api/trading-console/execution-control-state` is read-only and not an
  execute endpoint;
- generic Trading Console action APIs are not exposed;
- future actions remain deferred until a scoped backend action contract exists.

The official action API inventory is present but not generic:

```text
supported_owner_trial_flow_carrier_ids = [MI-001-BNB-LONG]
supported_owner_bounded_execution_carrier_ids = [MI-001-BNB-LONG]
trading_console_action_api_exposed = false
```

The existing official action endpoints remain the BRC Owner trial-flow path:

```text
POST /api/brc/owner-trial-flow/risk-acknowledgement
POST /api/brc/owner-trial-flow/authorization-draft
POST /api/brc/owner-trial-flow/authorization-draft/{draft_id}/activate-live-authorization
POST /api/brc/owner-trial-flow/live-execution-bridge/dry-run
POST /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute
```

The three admission sprint candidates are not marked action-compatible with
that registry in this read model. Even with a complete Owner scope, the dry-run
final gate records `official_action_api_candidate_supported=block` unless the
candidate carrier is supported by the current Owner trial-flow and bounded
execution registries.

The API-backed authorization/admission ladder is present through BRC admission
and Operation Layer APIs:

```text
POST /api/brc/admissions/requests
POST /api/brc/admissions/requests/{admission_request_id}/evaluate
POST /api/brc/admissions/risk-acceptances
GET  /api/brc/operations/capabilities
POST /api/brc/operations/preflight
POST /api/brc/operations/{operation_id}/confirm
```

The read-model exposes the following metadata operation chain for Owner review:

```text
create_gated_trial_from_admission
create_campaign_from_admission_binding
install_runtime_constraints_from_admission_campaign
prepare_runtime_carrier_from_admission_campaign
prepare_runtime_start_from_admission_carrier
evaluate_trial_trade_intent
prepare_runtime_handoff_from_admission_campaign
start_runtime_from_admission_handoff
prepare_strategy_activation_from_admission_runtime
activate_strategy_from_admission_runtime
prepare_signal_loop_from_admission_strategy
start_signal_loop_from_admission_strategy
evaluate_signal_from_admission_strategy
record_trial_trade_intent_from_signal_evaluation
```

This is not a Trading Console direct action API. The listed steps are exposed as
metadata/admission/Operation Layer bridge state in this sprint artifact; they do
not create execution intents or place orders from the Trading Console read
model.

## Chain Stage State And Evidence Contract

Each family row exposes `chain_stage_states` for:

```text
StrategyFamily
StrategyGroup
Carrier
RiskDisclosure
AuthorizationDraft
BoundedLiveAuthorization
ExecutionIntent
Entry
TP/SL
Review
```

This is the frontend/audit-facing chain proof for the sprint. Current states are
non-executable: authorization is proposal/dry-run only, bounded live
authorization is blocked, execution intent is not created, entry is not
executed, TP/SL is draft-required, and review is a contract draft.

Each family row also exposes `pre_post_evidence_contract`. Any future live
action must collect pre/post evidence through official service/API paths, not
manual PG edits:

```text
PG: orders, positions, execution_intents, authorizations,
    protection_price_plans, recovery_tasks, audit_logs, campaign_events
Exchange reads: account_balance, positions, open_orders, order_detail
Audit sources: audit_logs, campaign_events, operation_results
```

For this artifact:

```text
live_action_evidence_present = false
mutation_allowed_by_read_model = false
collection_policy = official_service_or_api_path_only_no_manual_pg_edits
```

## Gate Blocker Matrix

Each family row exposes `gate_blocker_records` in addition to its primary
`blocker_record`. These records use the same `BlockerRecord` contract and are
aggregated into top-level `blocker_records`.

Current active blocker families:

| Gate | Stage | Bridge method | Meaning |
| --- | --- | --- | --- |
| Scope | AuthorizationDraft | AuthorizationDraftProposal | Owner scope is missing, incomplete, or not matched to the candidate. |
| Action API | BoundedLiveAuthorization | ActionCandidate | Candidate carrier is not supported by current official action API registry. |
| Final gate | BoundedLiveAuthorization | FinalGateDryRun | Backend final gate has not returned `actionable=true`. |
| Evidence | PreExecutionBlockedReview | PreExecutionBlockedReview | Required pre-action PG/exchange snapshots do not exist. |
| Protection | TP/SL | ProtectionPlanDraft | Mandatory TP/SL plan is draft-only. |
| Review | Review | ReviewContract | Review contract is draft-only until live action evidence exists. |

For a complete matching Owner scope, the Scope blocker is omitted for the
matched row, but Action API, Final gate, Evidence, Protection, and Review
blockers remain active unless separately satisfied by official backend state.

`blocker_retry_matrix` preserves that same rule with family detail: it includes
primary family blockers plus gate blockers, and maps each bridge method to the
requirements that must be satisfied before retry. Rows are never executable
permission.

## API Request Drafts

Each family row exposes `api_request_drafts` for the official API chain. These
are payload templates only and are not submitted by the read model:

```text
POST /api/brc/admissions/evidence-packets
POST /api/brc/admissions/owner-regime-inputs
POST /api/brc/admissions/requests
POST /api/brc/admissions/risk-acceptances
POST /api/brc/operations/preflight
```

All draft rows preserve:

```text
not_submitted = true
creates_execution_intent = false
places_order = false
mutates_exchange = false
```

Templates intentionally keep unresolved refs such as `evidence_packet_id`,
`owner_market_regime_input_id`, `admission_decision_id`,
`constraint_snapshot_id`, `owner_risk_acceptance_id`, and
`pre_action_account_facts_snapshot_ref`. They must be resolved by official
service/API calls before any Operation confirmation can be considered.

## Acceptance Verdicts

Each family row exposes `admission_verdict`. It summarizes the row for Owner
and frontend handoff:

```text
may_execute_live = false
frontend_action_enabled = false
completed_stages = currently satisfied read-model/proposal stages
blocked_stages = stages blocked by gate_blocker_records
remaining_requirements = concrete retry requirements
next_retry_conditions = blocker retry conditions
```

The top-level `sprint_acceptance_verdict` remains:

```text
status = in_progress_pass_with_constraint
completed_family_count = 0
actionable_family_count = 0
live_execution_ready = false
frontend_action_enabled = false
```

It is an acceptance summary, not a permission source. Only backend
`actionable=true` with official PG/exchange evidence can change frontend action
enablement.

`final_report_package` is the top-level report handoff package for this sprint.
It references the structured matrices rather than duplicating every row:

```text
completed_work_by_family -> family_completion_matrix, full_chain_evidence_matrix, family_final_report_matrix
strategy_group_carrier_mappings -> strategy_group_mapping, carrier_candidate, carrier_readiness_report
admission_risk_control_changes -> admission_risk_control_matrix, production_capital_boundary_matrix, owner_authorization_packet_matrix, protection_review_audit_matrix
trading_console_authorization_readiness -> trading_console_authorization_readiness, owner_review_handoff_matrix, api_backed_authorization_flow, official_api_request_draft_matrix, final_gate_readiness_matrix, official_transition_readiness_matrix
live_actions_taken -> live_actions_taken=[], production_baseline_context, production_action_decision_matrix
pg_exchange_evidence -> pg_exchange_evidence_matrix, family_evidence_collection_matrix, evidence_collection_summary_matrix
blocker_records_and_bridge_artifacts -> blocker_records, blocker_retry_matrix, bridge_artifact_statuses, objective_acceptance_audit_matrix
tests_checks -> required_validation_commands, objective_acceptance_audit_matrix
next_retry_conditions -> blocker_retry_matrix
safety_proof -> production_baseline_context, final_report_package safety flags
```

It must keep:

```text
live_actions_taken = false
runtime_started = false
pg_mutation = false
exchange_write_action = false
credentials_changed = false
deploy_performed = false
push_performed = false
```

For this sprint, Trading Console authorization readiness is
`PASS_WITH_CONSTRAINT`: read-only state can display candidates and blockers, but
new live production actionability is blocked until a complete scoped
authorization exists for a concrete candidate.

## Owner Scope Dry-Run

The production admission read model supports a scope review query using:

```text
family, strategy_family_id, carrier_id, symbol, side, quantity, max_notional,
leverage, max_attempts, protection_mode, review_requirement
```

If these fields are complete and match a candidate, the response may mark:

```text
scope_review.verdict = complete_dry_run_only
final_gate_dry_run.gates[owner_scope_complete] = pass
authorization_draft_proposal.status = scope_reviewed_dry_run_only
protection_plan_draft.status = scope_reviewed_draft_only
```

It still keeps:

```text
backend_actionable = false
frontend_action_enabled = false
execution_intent_state = not_created
entry_state = not_executed
final_gate_dry_run.reason = official_action_api_candidate_not_supported
```

because the backend final gate and official action contract are separate and
not connected by this read-only endpoint.

## Authorization Draft Proposal

Each family row includes `authorization_draft_proposal`. It is for review only:

```text
not_authorization = true
not_execution_permission = true
not_order_permission = true
official_api_transition_plan.authorization_endpoint =
  deferred_until_backend_action_contract
```

When a matching complete scope is supplied, the draft can include the sanitized
scope and budget envelope. It still cannot grant permission or submit an action.

## Live Actions

None.

No new production entry, TP, SL, cancel, replace, flatten, retry-protection,
runtime start, deployment, credential change, PG repair, Alembic upgrade, or
Alembic downgrade was executed for this artifact.

## PG / Exchange Evidence

This sprint did not perform live PG mutation or exchange action. Evidence is
limited to repo/code inspection and local tests. Any future live path must
capture pre/post PG and exchange snapshots through the official API path before
and after execution.

## Verification

Targeted verification for this artifact:

```bash
python3 -m pytest -q tests/unit/test_trading_console_readmodels.py
python3 -m pytest -q tests/unit/test_production_strategy_family_admission.py
python3 -m pytest -q tests/unit/test_strategy_family_registry.py
python3 -m pytest -q tests/unit/test_historical_ohlcv_catalog_and_builders.py tests/unit/test_historical_research_sampling.py tests/unit/test_cpm_historical_evaluator_and_experiment.py
python3 -m py_compile src/application/production_strategy_family_admission.py src/application/readmodels/trading_console.py src/interfaces/api_trading_console.py src/domain/strategy_family_registry.py
python3 -m alembic heads
git diff --check
```
