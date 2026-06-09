---
title: PROJECT_BASELINE_CURRENT
status: CURRENT_CANON
authority: owner-correction + code-verification + semantic-audit
last_verified: 2026-06-09
supersedes:
  - docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md (for canon reading order)
source_of_truth:
  - docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md
  - docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md
  - docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md
  - tracked code verification
  - owner semantic audit 2026-06-09
---

# Project Baseline Current

This is the authoritative project baseline for agent reading. It distills
verified facts from the knowledge-pack sources. For detailed evidence, consult
the source_of_truth files listed above.

---

## 1. Current Project Definition

BRC is a personal quantitative strategy runtime governance system.

Current code implements an Owner-controlled bounded-live research and execution
system plus a shadow StrategyRuntimeInstance governance backbone. The current
executable path remains one-shot Owner-authorized single trade execution.

Current governance direction is converging on Strategy Runtime Governance:
Owner should authorize a bounded StrategyRuntimeInstance, not one immediate
trade.

Current Owner objective is small experimental risk capital pursuing right-tail
asymmetric returns. The system should optimize for bounded downside, traceable
experiments, and right-tail opportunity capture. It should not optimize for
stable yield, low-volatility compounding, automatic asset management, or
automatic profit withdrawal.

Strategy admission must be layered:

- Semantic Admission: a strategy can be represented, audited, constrained, and
  reviewed by the system. Lack of proven alpha is not a Semantic Admission
  blocker.
- Economic Admission: a strategy is eligible for larger budget, lower Owner
  confirmation burden, or higher autonomy. Lack of proven alpha must restrict
  this layer.
- Execution Admission: one concrete candidate passes runtime boundary,
  FinalGate, Owner authorization, protection readiness, account facts, and
  deployment readiness checks.

Current first strategy-semantics reference candidates are CPM / BRF / RMR /
FCO:

- CPM is a long-only pullback-continuation price-action reference
  implementation candidate, not a proven-alpha production strategy.
- BRF is a short-side bear-rally-failure price-action reference implementation
  candidate, not a proven-alpha production strategy.
- RMR is initially a range/chop regime classifier, not the first trading
  strategy.
- FCO is a funding / open-interest / crowding backlog family until data facts,
  freshness, and missing-fact behavior are defined.

---

## 2. Current Code Reality

Current executable path is one-shot Owner authorization:

```text
OwnerRiskAcknowledgement
-> AuthorizationDraft
-> BoundedLiveTrialAuthorization
-> FinalGate
-> OwnerBoundedExecutionService
-> Entry / TP / SL
-> Order / Reconciliation / Review
```

Key facts:

- **BoundedLiveTrialAuthorization** is single-use trade authorization. It is
  not a strategy runtime authorization.
- **StrategyRuntimeInstance** now exists as a local working-tree shadow governance
  record with PG persistence and lifecycle events. It is not executable:
  `execution_enabled=false` and `shadow_mode=true` are enforced by domain and
  migration constraints.
- **SignalEvaluation / OrderCandidate** now exist as local working-tree shadow
  records with PG persistence and Trading Console inspection endpoints. They do
  not create submit-ready ExecutionIntent records, orders, FinalGate execution
  triggers, or exchange calls.
- **StrategySemantics / StrategySemanticsShadowBindingService** now exist as
  local working-tree B0 pure model and application binding layers. They declare
  CPM / BRF / RMR / FCO reference/backlog semantics, RequiredFacts,
  freshness/missing-fact behavior, EntryPolicy, ProtectionPolicy, ExitPolicy,
  and right-tail review metrics, and can create only shadow OrderCandidate
  records after fact checks pass. They can consume `StrategyFamilySignalOutput`
  and persist a shadow SignalEvaluation plus semantically bound shadow
  OrderCandidate through the existing shadow repository path. They do not
  implement real execution, create ExecutionIntent records, call OrderLifecycle,
  call exchange, or prove alpha.
- **Runtime-aware FinalGate preview** now exists as read-only dry-run
  inspection for runtime order candidates. It does not mutate runtime state,
  create ExecutionIntent records, place orders, or call the exchange.
- **RuntimeExecutionPlan / RuntimeExecutionIntentDraft / RuntimeExecutionIntent
  adapter preview / recorded ExecutionIntent audit / submit-readiness preview /
  Owner submit authorization record / controlled submit plan preview /
  pre-submit runtime FinalGate preflight / default-disabled controlled submit
  adapter boundary / non-mutating attempt reservation preview /
  runtime attempt reservation audit record / runtime attempt mutation record /
  runtime-native protection plan preview / runtime-native protection plan audit
  record / runtime OrderLifecycle handoff draft audit record / non-executing
  OrderLifecycle adapter preview gate / submit adapter readiness preview** now
  exist in the local working tree as non-submitting bridge layers. They are not
  deployed to tokyo.
  RuntimeExecutionIntentDraft has its own audit table. The adapter can record
  `ExecutionIntent(status=recorded, source_type=brc_runtime_order_candidate)`
  without projecting OrderCandidate into legacy `SignalResult`. Drafts and
  source payloads preserve candidate entry price, risk preview, and protection
  preview snapshots for later audit/review. Submit-readiness can inspect that
  recorded intent and require Owner submit authorization.
  RuntimeExecutionSubmitAuthorization can record
  `approved_pending_controlled_submit` after explicit Owner submit
  confirmation. RuntimeExecutionControlledSubmitPlan can preview
  `ready_for_controlled_submit_adapter`. RuntimeExecutionControlledSubmitPreflight
  reruns runtime-aware FinalGate at submit time using local active-position
  facts. RuntimeExecutionControlledSubmitResult consumes that submit-time
  preflight: it returns `blocked` when the preflight is not ready, otherwise
  `submit_adapter_not_enabled` by default and `submit_adapter_not_implemented`
  if enabled before implementation. Controlled submit results are recorded in
  their own audit table. RuntimeExecutionProtectionPlanPreview is derived from
  recorded runtime intent source payload rather than one-shot authorization, and
  exposes whether concrete stop price / candidate protection facts are present.
  RuntimeExecutionProtectionPlan can record ready or blocked runtime-native
  protection facts, including concrete stop/take-profit snapshots when present,
  while remaining `not_order=true` and `not_exchange_payload=true`.
  RuntimeExecutionOrderLifecycleHandoffDraft can record ready or blocked
  handoff facts and freeze the entry/protection order draft inputs plus
  Order-model-compatible draft snapshots a future OrderLifecycle adapter would
  need, while keeping
  `order_lifecycle_adapter_implemented=false`, `order_created=false`,
  `order_lifecycle_called=false`, and `exchange_called=false`.
  RuntimeExecutionOrderLifecycleAdapterPreview can verify those handoff facts
  and returns `inputs_ready_registration_not_enabled` or `blocked` while
  keeping `local_order_registration_enabled=false`,
  `order_lifecycle_adapter_implemented=false`, `order_created=false`,
  `order_lifecycle_called=false`, and `exchange_called=false`.
  RuntimeExecutionAttemptReservationPreview computes attempts/budget before and
  after from StrategyRuntimeInstance boundary while keeping
  `reservation_recorded=false`, `runtime_budget_mutated=false`, and
  `attempt_consumed=false`.
  RuntimeExecutionAttemptReservation can record `pending_runtime_mutation` as
  an audit fact while still keeping `runtime_budget_mutated=false`,
  `attempt_consumed=false`, `execution_intent_status_changed=false`,
  `order_created=false`, and `exchange_called=false`.
  RuntimeExecutionAttemptMutation can apply that pending reservation to runtime
  state by incrementing `attempts_used` and `budget_reserved`. It blocks stale
  attempt/budget drift and still keeps `execution_intent_status_changed=false`,
  `order_created=false`, `exchange_called=false`,
  `owner_bounded_execution_called=false`, and `order_lifecycle_called=false`.
  RuntimeExecutionSubmitAdapterPreview exposes missing OrderLifecycle/protection
  inputs without mutating runtime budget or creating orders. These layers do not
  call OwnerBoundedExecution, call OrderLifecycle, place orders, or call the
  exchange.
- **StrategyFamily / Admission** exists as metadata, admission classification,
  and evidence chain. It does not bind to executable strategy code.
- **CandidateAction / BudgetedAutonomy** are readmodel / preview / policy
  evaluation. They are not execution chains.
- **SignalPipeline** is the current legacy real-time signal system. It is a
  candidate asset for a future SignalEvaluation engine, but it is not connected
  as an executable BRC StrategyRuntimeInstance trigger.
- **OwnerBoundedExecutionService** is a valuable one-shot real-closed-loop
  execution asset. It is not the final target BRC architecture.
- **Order / Reconciliation / Review** infrastructure is reusable. Nullable
  runtime semantic audit IDs and source-native ExecutionIntent metadata have
  been added to selected execution and review tables. Runtime execution submit
  has not yet been integrated.
- **Tokyo deployment note:** current tokyo deployment was verified still on
  commit `415d398` / Alembic head `044`, so it does not yet contain the local
  Sprint 1-4 runtime governance shadow code.

---

## 3. Current Target Direction

BRC should become strategy runtime governance:

- Owner should authorize a bounded StrategyRuntimeInstance.
- StrategyRuntimeInstance should generate SignalEvaluation / OrderCandidate
  within risk boundaries.
- Runtime execution should allow budgeted small experimental losses while
  preventing runaway behavior, budget breach, unauditable orders, and boundary
  expansion.
- Before controlled runtime execution promotion, strategy semantics must bind
  StrategyFamilyVersion to StrategyImplementation, RequiredFacts,
  StrategyEvaluationContext, EntryPolicy, ProtectionPolicy, ExitPolicy, attempt
  consumption, budget reservation, and right-tail review metrics.
- Owner profit withdrawal is manual. The system may record withdrawal/capital
  base adjustment facts for review, but must not initiate withdrawals,
  transfers, or fund movement.
- The target chain is defined in `docs/canon/BRC_TARGET_SEMANTICS.md`.

---

## 4. Do Not Misread

- Do not treat one-shot OwnerBoundedExecution as final architecture.
- Do not treat TrialBinding as an already-running strategy instance.
- Do not treat StrategyFamilyVersion as executable strategy code.
- Do not treat shadow StrategyRuntimeInstance, SignalEvaluation, or
  OrderCandidate records as execution authority.
- Do not treat CPM / BRF reference implementation admission as proven-alpha or
  production-strategy approval.
- Do not let RMR become a broad hard execution filter before its confidence,
  freshness, and failure modes are reviewed.
- Do not treat CandidateAction as executable.
- Do not treat BudgetedAutonomy as auto trading.
- Do not treat budgeted strategy losses as system failure when they remain
  inside runtime boundaries and are auditable.
- Do not treat archived docs as current truth.
- Do not treat old read-only / research-only docs as current constraints.
- Do not treat docs/ops/ historical documents as current canon.

---

## 5. Authoritative Reading Order

For agents joining this project, read in this order:

1. `CLAUDE.md` / `AGENTS.md` — root entry points
2. `docs/canon/PROJECT_BASELINE_CURRENT.md` — this file
3. `docs/canon/BRC_TARGET_SEMANTICS.md` — target semantics and status map
4. `docs/canon/RUNTIME_SAFETY_BOUNDARY.md` — execution safety boundaries
5. `docs/canon/TECH_DEBT_BASELINE.md` — known debt classification
6. `docs/canon/DOCUMENT_GOVERNANCE.md` — how to read and trust documents

For detailed evidence and historical context, consult:

- `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`
- `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md`
- `docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md`
- `docs/ops/knowledge-pack/CURRENT_READINESS_BLOCKERS.md`
- `docs/ops/agent-current-brc-baseline.md`
- `docs/ops/agent-working-rules.md`
