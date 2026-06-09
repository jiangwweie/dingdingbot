---
title: TD_GOVERNANCE_AND_REFACTOR_PLAN_2026_06
status: OPERATING_PLAN
authority: owner-task + docs/canon/*
created: 2026-06-09
scope: global technical debt governance and refactor planning
---

# Technical Debt Governance & Refactor Plan - 2026-06

This document is a global technical debt governance and refactor plan for BRC.
It is not a StrategyRuntimeInstance-only design document and does not authorize
implementation by itself.

This is a documentation-only plan. It does not authorize code, migration, API,
test, runtime, database, exchange, or external-service changes.

Authoritative baseline:

- `docs/canon/PROJECT_BASELINE_CURRENT.md`
- `docs/canon/BRC_TARGET_SEMANTICS.md`
- `docs/canon/TECH_DEBT_BASELINE.md`
- `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
- `docs/canon/AGENT_WORKSPACE_RULES.md`
- `docs/canon/DOCUMENT_GOVERNANCE.md`

---

## 0. Verified Progress Update - 2026-06-09

Codex verified the local working tree on 2026-06-09:

- Sprint 1 StrategyRuntimeInstance shadow backbone is implemented locally.
- Sprint 2 nullable runtime audit ID spine is implemented locally.
- Sprint 3 SignalEvaluation / OrderCandidate shadow path is implemented
  locally.
- Sprint 4 Runtime-aware FinalGate preview / dry-run is implemented locally.
- Sprint 5 pre-integration has begun with RuntimeExecutionPlan,
  RuntimeExecutionIntentDraft, RuntimeExecutionIntent adapter preview, and a
  source-native recorded ExecutionIntent audit path. It now also has a
  non-submitting submit-readiness preview, Owner submit authorization record,
  controlled submit plan preview, pre-submit runtime FinalGate preflight, and
  default-disabled controlled submit adapter boundary for recorded runtime
  intents. It also has a non-mutating runtime attempt/budget reservation
  preview, a runtime attempt reservation audit record, a runtime attempt/budget
  mutation record, a runtime-native protection plan preview, a runtime-native
  protection plan audit record, a runtime OrderLifecycle handoff draft audit
  record, a non-executing OrderLifecycle adapter preview gate, and a
  non-executing submit adapter preview that expose missing
  OrderLifecycle/protection/budget inputs before any future submit adapter or
  local order registration adapter is implemented. Controlled submit results,
  runtime attempt reservations, runtime attempt mutations, runtime protection
  plans, and runtime OrderLifecycle handoff drafts are now recorded in their
  own audit tables.
  RuntimeExecutionIntentDraft can be recorded in its own audit table. The
  draft and source-native intent payload preserve the candidate entry price,
  risk preview, and protection preview snapshots for later audit/review. The
  adapter can record
  `ExecutionIntent(status=recorded)` with
  `source_type=brc_runtime_order_candidate` without projecting OrderCandidate
  into legacy `SignalResult`. Owner submit authorization can be recorded as
  `approved_pending_controlled_submit`. A controlled submit plan and submit-time
  runtime FinalGate preflight can reach `ready_for_controlled_submit_adapter`.
  RuntimeExecutionAttemptReservation can record
  `pending_runtime_mutation` from a ready reservation preview while keeping
  runtime budget unmutated and attempts unconsumed. The preview and reservation
  prefer `risk_preview.max_loss_reference` as the trial-loss budget amount and
  fall back to `intended_notional` only when max-loss evidence is absent.
  RuntimeExecutionAttemptMutation can then apply that pending reservation to
  runtime state by incrementing attempts and `budget_reserved` using the same
  budget basis, while still not changing ExecutionIntent status, creating
  orders, calling OwnerBoundedExecution, calling
  OrderLifecycle, or calling exchange. RuntimeExecutionProtectionPlan can record
  concrete stop/take-profit snapshots from the runtime intent source payload as
  a non-order, non-exchange-payload audit fact.
  RuntimeExecutionOrderLifecycleHandoffDraft can freeze the entry/protection
  order input facts and Order-model-compatible draft snapshots a future
  OrderLifecycle adapter would need, but it records
  `order_lifecycle_adapter_implemented=false`, `order_created=false`,
  `order_lifecycle_called=false`, and `exchange_called=false`.
  RuntimeExecutionOrderLifecycleAdapterPreview can then verify those handoff
  facts and return `inputs_ready_registration_not_enabled` or `blocked` while
  keeping `local_order_registration_enabled=false`,
  `order_lifecycle_adapter_implemented=false`, `order_created=false`,
  `order_lifecycle_called=false`, and `exchange_called=false`. The adapter boundary returns
  `submit_adapter_not_enabled` by default and `submit_adapter_not_implemented`
  if explicitly enabled before implementation, but the result now consumes the
  submit-time FinalGate preflight and records `blocked` when that preflight is
  not ready. It does not submit orders or call exchange.

Validation performed:

```text
python3 -m pytest -q tests/unit/test_strategy_runtime_backbone.py \
  tests/unit/test_td2_audit_id_spine.py \
  tests/unit/test_td3_signal_evaluation_order_candidate_shadow.py \
  tests/unit/test_td4_runtime_final_gate_preview.py \
tests/unit/test_td5_runtime_execution_plan.py
120 passed

python3 -m compileall -q <runtime/shadow/preview/adapter modules>
passed

python3 -m alembic heads
058 (head)

git diff --check
passed

B0 context builder follow-up validation:

python3 -m pytest -q tests/unit/test_b0_strategy_evaluation_context_builder.py \
  tests/unit/test_b0_strategy_semantics_binding.py \
  tests/unit/test_td3_signal_evaluation_order_candidate_shadow.py \
  tests/unit/test_td4_runtime_final_gate_preview.py \
  tests/unit/test_td5_runtime_execution_plan.py \
  tests/unit/test_strategy_runtime_backbone.py
128 passed

python3 -m compileall -q src/application/strategy_evaluation_context_builder.py \
  src/application/strategy_semantics_shadow_binding_service.py \
  src/domain/strategy_semantics.py \
  tests/unit/test_b0_strategy_evaluation_context_builder.py \
  tests/unit/test_b0_strategy_semantics_binding.py
passed
```

Deployment note:

```text
tokyo deployment: commit 415d398 / Alembic head 044
local branch: codex/td3-signal-evaluation-order-candidate-shadow-v1
local head: 651ec2aa
local working tree includes migrations 045, 046, 047, 048, 049, 050, 051, 052, 053, 054, 055, 056, 057, 058
```

Therefore the local working tree is ahead of tokyo deployment. Do not describe
remote deployment as having Sprint 1-4 runtime governance until deployed and
verified.

Owner objective update:

```text
small experimental risk capital
-> bounded StrategyRuntimeInstance
-> accept many small losses / failed experiments inside budget
-> capture rare right-tail gains
-> Owner manually withdraws profits outside the system
```

This is not a stable-yield, low-drawdown compounding, automatic asset
management, or automatic withdrawal system.

Runtime execution work after Sprint 4 must treat "bounded loss and no runaway"
as the safety target. Loss inside budget is acceptable; budget breach,
unauditable orders, stale account facts, runaway attempts, and unauthorized
exchange writes are not.

Owner compatibility principle:

```text
Historical table/data compatibility is not required for this single-user
project. If target semantics are clearer with an aggressive schema change,
prefer the target semantics over legacy compatibility, while preserving live
order/exchange safety gates.
```

---

## 1. Purpose

The purpose of this plan is to govern technical debt refactor work while BRC
evolves from:

```text
Owner authorizes one trade
```

to:

```text
Owner authorizes a bounded StrategyRuntimeInstance
```

The plan must advance that target without breaking the current one-shot live
path. The existing one-shot path is a valuable asset and remains the current
implemented execution reality until tracked code proves otherwise.

This plan covers all current technical debt classes:

- **S0 target semantic debt**: gaps between current code semantics and target
  strategy runtime governance.
- **S1 execution / audit semantic debt**: missing traceability, execution
  semantics, runtime IDs, and policy integration.
- **S2 maintainability / product interpretation debt**: confusing boundaries,
  oversized files, config/profile drift, console semantics, and naming debt.
- **S3 cleanup debt**: legacy scripts, sandbox remnants, stale physical docs
  organization, and duplicate support assets.

StrategyRuntimeInstance is the first mainline. It is not the whole technical
debt program. Config, Console, scripts, readmodels, API decomposition, legacy
cleanup, and document reorganization must remain visible and sequenced instead
of being forgotten behind the runtime backbone.

---

## 2. Current Code Reality

Current executable path is the one-shot OwnerBoundedExecution short chain:

```text
OwnerRiskAcknowledgement
-> AuthorizationDraft
-> BoundedLiveTrialAuthorization
-> FinalGate
-> OwnerBoundedExecutionService
-> Entry / TP / SL
-> Order / Reconciliation / Review
```

Current local working-tree facts:

- Current implemented execution is one-shot `OwnerBoundedExecution`.
- `BoundedLiveTrialAuthorization` is single-use trade authorization.
- Current code contains a shadow `StrategyRuntimeInstance` governance backbone.
  It is not executable.
- `AdmissionTrialBinding` is not currently a running strategy instance.
- `StrategyFamilyVersion` does not currently bind to a real
  StrategyImplementation.
- `CandidateAction` / `BudgetedAutonomy` are currently readmodel / preview /
  policy evaluation, not executable chains.
- `SignalEvaluation` / `OrderCandidate` shadow records exist in the local
  working tree, but they do not create ExecutionIntent records or orders.
- Runtime-aware FinalGate preview exists in the local working tree, but it is
  dry-run inspection only.
- `SignalPipeline` is a legacy real-time signal system. It can be considered a
  future SignalEvaluation engine candidate, but it is not currently connected
  to the BRC StrategyFamily runtime governance chain.
- The current one-shot path is valuable and must not be broken by refactor
  work.

The target semantic chain remains:

```text
StrategyFamily
-> StrategyFamilyVersion
-> AdmissionDecision
-> OwnerRiskAcceptance
-> TrialBinding
-> StrategyRuntimeInstance
-> SignalEvaluation
-> OrderCandidate
-> FinalGate
-> ExecutionIntent
-> OrderLifecycle
-> Order / Position
-> Reconciliation
-> Review
```

No sprint may describe a target node as implemented until tracked code and
Codex review verify that fact.

---

## 3. Refactor Strategy

The refactor strategy is:

```text
long sprint
+ strong boundary
+ additive-only
+ shadow path
```

### Long Sprint

Codex can run long tasks when the objective is coherent. The program does not
need to split every refactor into tiny tasks if doing so would lose semantic
continuity.

Each long sprint still needs one primary outcome, explicit boundaries, and a
clear review point before the next sprint begins.

### Strong Boundary

Every sprint must define:

- allowed files;
- forbidden files;
- whether migrations are allowed;
- whether APIs are allowed;
- whether execution/order code is allowed;
- whether runtime/project/test execution is allowed;
- whether the output is shadow-only or executable;
- exact stop conditions.

If the sprint needs to cross its boundary, the sprint stops and reports.

### Additive-only

Default mode is additive-only:

- add models, tables, nullable fields, repositories, services, readmodels, and
  tests where approved;
- preserve old data and old behavior;
- keep new runtime semantics optional until proven;
- avoid broad renames;
- avoid deletion until replacement behavior is stable and explicitly promoted.

Destructive migrations, irreversible cleanup, and broad replacement work
require separate approval after evidence exists.

### Shadow Path

New runtime governance must first exist as a shadow path:

- no order placement;
- no order cancel / close / replace;
- no exchange calls;
- no live/testnet connection;
- no automatic execution intent creation unless a later sprint explicitly
  allows it;
- no change to current one-shot execute API behavior;
- no FinalGate execute trigger from Sprint 1 runtime state.

Shadow artifacts should be inspectable, auditable, and comparable before any
controlled execution integration.

---

## 4. Non-negotiable Invariants

These invariants apply across all sprints:

1. Do not delete `OwnerBoundedExecutionService`.
2. Do not replace `BoundedLiveTrialAuthorization`.
3. Do not change current one-shot execute API behavior.
4. Do not change exchange order placement behavior.
5. Do not let `StrategyRuntimeInstance` place orders in Sprint 1.
6. Do not let `SignalPipeline` automatically trigger runtime execution.
7. Do not force old `ExecutionIntent` / `Order` / `Review` records to have
   runtime IDs.
8. Do not prematurely change frontend action APIs.
9. Do not run live or testnet.
10. Do not perform destructive migrations.
11. Do not bypass or weaken FinalGate.
12. Do not bypass the Operation Layer.
13. Do not output secrets or secret-adjacent values.
14. Do not optimize strategy returns or tune ETH Pinbar parameters as part of
    technical debt refactor.
15. Do not treat readmodel, preview, metadata, or design-only objects as
    executable authority.
16. Do not proceed from non-executing runtime execution pre-integration to a
    real OrderLifecycle adapter or controlled runtime execution before Mega
    Block B0 Strategy Semantics / Entry-Exit Policy Binding is accepted.

---

## 5. Technical Debt Coverage Matrix

| Debt Class | Debt | Covered By | Timing | Notes |
| ---------- | ---- | ---------- | ------ | ----- |
| S0 | Owner authorizes trade vs Owner authorizes StrategyRuntimeInstance | Runtime backbone, shadow path, controlled integration | Sprint 1, Sprint 5 | Current one-shot path remains intact while target semantics are introduced. |
| S0 | StrategyRuntimeInstance missing | Domain model, repository, service, lifecycle, readmodel/API inspection | Sprint 1 | Shadow-only in Sprint 1; no execution. |
| S0 | TrialBinding is not runtime instance | Runtime draft from TrialBinding | Sprint 1 | TrialBinding remains binding/evidence, not itself runtime. |
| S0 | Admission pass does not produce StrategyRuntimeInstanceDraft | Runtime draft creation path | Sprint 1 | Additive path only; does not replace admission behavior. |
| S0 | StrategyFamilyVersion does not bind real StrategyImplementation | Mega Block B0 Strategy Semantics / implementation adapter plan | B0 before Sprint 5 promotion | Do not overclaim execution binding before implementation exists. |
| S1 | runtime_instance_id / trial_binding_id / strategy_family_version_id do not cross ExecutionIntent / Order / Review | Nullable audit ID spine | Sprint 2 | Additive, nullable, backward compatible. |
| S1 | signal_evaluation_id / order_candidate_id missing from audit chain | Audit ID spine and shadow candidate models | Sprint 2, Sprint 3 | Old records are not forced to backfill IDs. |
| S1 | SignalEvaluation missing | SignalEvaluation model and adapters | Sprint 3 | Shadow-only; no exchange call. |
| S1 | OrderCandidate missing | OrderCandidate model and candidate readmodel | Sprint 3 | Does not create ExecutionIntent in Sprint 3. |
| S1 | EntryPolicy / ExitPolicy not connected to BRC execution | Mega Block B0 EntryPolicy / ExitPolicy / ProtectionPolicy binding | B0 before Sprint 5 promotion | ProtectionPolicy remains minimum safety, not full exit semantics. |
| S1 | FinalGate lacks runtime mode | Runtime-aware FinalGate checks | Sprint 4 | Adds checks; does not replace existing FinalGate. |
| S1 | Review / Reconciliation cannot trace full strategy runtime chain | Audit ID spine through Review / Reconciliation | Sprint 2, Sprint 5 | Improves traceability without breaking existing reviews. |
| S1 | TP/SL exit projection may be incomplete | Protection and runtime execution review | Sprint 4, Sprint 5 | Audit before runtime execution promotion. |
| S1 | attempt / budget consumption semantics are under-specified | Mega Block B0 attempt and budget semantics | B0 before Sprint 5 promotion | Must distinguish budgeted small losses from runaway behavior. |
| S2 | Runtime Profile / ConfigManager multi-track drift | Runtime/config/safety boundary consolidation | Sprint 7 | Deferred until runtime semantics are clearer. |
| S2 | ExecutionPermission / CapitalProtection coverage inconsistent | Coverage review and consolidation | Sprint 7 | Must preserve current safety boundaries. |
| S2 | scripts bypass risk | Script risk classification and containment | Sprint 7, Sprint 9 | Do not run scripts during governance planning. |
| S2 | Trading Console readmodel and action semantics are not unified | Console runtime productization and API truth-source cleanup | Sprint 6, Sprint 8 | Console must not overclaim unavailable capabilities. |
| S2 | API / readmodel files too large | API / readmodel decomposition | Sprint 8 | Decompose after semantic model stabilizes. |
| S2 | CandidateAction / BudgetedAutonomy naming is misleading | Product/readmodel semantics cleanup | Sprint 6, Sprint 8 | Keep them readmodel/preview until code changes prove otherwise. |
| S3 | legacy scripts / sandbox / dead paths | Legacy scripts / sandbox cleanup | Sprint 9 | Risk-grade before deleting. |
| S3 | old research engineering remnants | Sandbox and dead-path cleanup | Sprint 9 | Preserve useful evidence where needed. |
| S3 | docs/ops physical directory is crowded | Documentation/evidence reorganization | Sprint 10 | Non-blocking; last-phase cleanup. |
| S3 | duplicate agent / skill / support files | Documentation/support cleanup | Sprint 10 | Must respect current agent authority rules. |

---

## 6. Sprint Roadmap

### Sprint 1: StrategyRuntimeInstance Backbone + Shadow Path

Scope:

- domain model;
- additive-only migration;
- repository;
- service;
- runtime draft from TrialBinding;
- runtime lifecycle;
- readmodel / API inspection;
- tests;
- ADR / design note.

Required properties:

- StrategyRuntimeInstance is introduced as shadow runtime governance
  infrastructure.
- Runtime draft can be derived from TrialBinding without treating TrialBinding
  as the running instance.
- Lifecycle vocabulary distinguishes draft, active shadow, paused, completed,
  failed, revoked, and other states as appropriate.
- Current one-shot path remains unchanged.

Forbidden:

- no real execution connection;
- no FinalGate execute trigger;
- no order placement;
- no replacement of one-shot path.

### Sprint 2: Audit ID Spine

Scope:

- nullable runtime semantic IDs;
- `runtime_instance_id`;
- `trial_binding_id`;
- `strategy_family_version_id`;
- `signal_evaluation_id`;
- `order_candidate_id`.

Gradual propagation targets:

- `ExecutionIntent`;
- `Order`;
- `Review`;
- `Reconciliation`.

Principles:

- additive-only;
- nullable;
- backward compatible;
- old `ExecutionIntent` / `Order` / `Review` records are not forced to carry
  runtime IDs.

### Sprint 3: SignalEvaluation / OrderCandidate Shadow Path

Scope:

- SignalEvaluation model;
- OrderCandidate model;
- StrategyContractV2 adapter;
- SignalPipeline adapter;
- candidate readmodel.

Required properties:

- SignalPipeline can feed shadow evaluation only through an explicit adapter.
- CandidateAction / BudgetedAutonomy remain readmodel / preview / policy
  evaluation.
- OrderCandidate remains shadow-only in this sprint.

Forbidden:

- no order placement;
- no ExecutionIntent creation;
- no exchange call.

### Sprint 4: Runtime-aware FinalGate

Scope:

- runtime status check;
- attempts remaining;
- budget remaining;
- allowed symbol / side;
- max leverage;
- active positions;
- protection requirement.

Required properties:

- Runtime-aware FinalGate adds validation context.
- Existing one-shot FinalGate behavior remains unchanged.
- Passing FinalGate still does not automatically place orders.

Forbidden:

- no replacement of existing FinalGate;
- no automatic execution;
- no behavior change to one-shot FinalGate.

### Mega Block B0: Strategy Semantics / Entry-Exit Policy Binding

Status:

```text
MANDATORY_GATE_BEFORE_CONTROLLED_RUNTIME_EXECUTION
```

This began as a planning correction and now has a local B0 implementation
slice. The local implementation is still shadow-only and does not authorize
real OrderLifecycle adapter work, local order registration, exchange submit, or
live runtime execution promotion.

Current local B0 implementation slice:

- `src/domain/strategy_semantics.py` defines StrategyImplementationBinding,
  StrategyEvaluationContext, RequiredFacts, fact freshness/missing behavior,
  ProtectionPolicy, ExitPolicy, initial CPM / BRF / RMR / FCO semantics, and
  right-tail review metrics.
- `src/application/strategy_evaluation_context_builder.py` builds
  StrategyEvaluationContext from read-only `StrategyFamilySignalInput`,
  `StrategyFamilySignalOutput`, and optional `StrategyRuntimeInstance`
  snapshots. It maps available OHLCV, price-action, account, runtime-boundary,
  position-projection, funding, range, volatility, and crowding-related facts,
  and explicitly marks absent facts as missing rather than inferring them.
- `src/application/strategy_semantics_shadow_binding_service.py` can create
  only shadow OrderCandidate records after RequiredFacts pass. It can now
  consume `StrategyFamilySignalOutput`, persist a shadow SignalEvaluation, and
  then create a semantically bound shadow OrderCandidate when the output is
  `WOULD_ENTER`, the side is supported, RequiredFacts pass, and concrete
  protection is present. It also has a B0 signal-pair orchestration method that
  accepts `StrategyFamilySignalInput` + `StrategyFamilySignalOutput`, builds
  StrategyEvaluationContext from read-only facts, and applies the same
  shadow-only gate.
- `tests/unit/test_b0_strategy_semantics_binding.py` verifies catalog
  semantics, missing/stale fact blocking, BRF shadow candidate binding, RMR
  non-trading classifier behavior, mandatory concrete stop enforcement, CPM
  StrategyFamilySignalOutput orchestration, CPM short rejection, non-entry
  output rejection, and PG-backed shadow repository integration.
- `tests/unit/test_b0_strategy_evaluation_context_builder.py` verifies that
  complete CPM input/output/runtime facts can feed the semantic shadow binding,
  missing 4h CPM context blocks binding, BRF does not invent missing
  short-squeeze risk facts, FCO keeps open-interest/crowding dependencies
  missing until explicit sources exist, and observation-only account facts do
  not satisfy account RequiredFacts. It also verifies that the binding service
  can build context from a signal input/output pair without requiring the caller
  to hand-assemble StrategyEvaluationContext.

Remaining B0 work:

- Owner/Codex-gated BRF evaluator details;
- RMR regime classifier implementation details;
- live/runtime fact-source integration beyond current
  StrategyFamilySignalInput / StrategyFamilySignalOutput /
  StrategyRuntimeInstance snapshots, especially trusted account, active
  position, funding, open-interest, and crowding readers;
- explicit real-submit attempt / budget release-or-consume acceptance before
  runtime promotion. Local reservation/mutation now uses a max-loss-first budget
  basis, but promotion still requires Owner/Codex confirmation of when
  reservation is released, confirmed consumed, or handled after submit failure.

Problem statement:

The current runtime execution pre-integration work is stronger than the current
strategy semantics binding. Continuing toward a real OrderLifecycle adapter
before strategy semantics are bound would risk creating a system with a strong
execution chain but under-specified strategy family, strategy implementation,
entry, exit, and attempt semantics.

This gate must be resolved before any real OrderLifecycle adapter, local order
registration, controlled runtime execution, exchange submit, or live runtime
execution promotion.

Required B0 decisions:

1. Define how `StrategyFamilyVersion` binds to a concrete
   `StrategyImplementation`.
2. Define `StrategyEvaluationContext`: market facts, account facts, runtime
   boundary facts, position facts, funding/crowding facts if used, and evidence
   references available to a strategy evaluation.
3. Define EntryPolicy mapping from `SignalEvaluation` to `OrderCandidate`,
   including candidate order type, quantity/notional proposal, entry price
   reference, invalidation conditions, and review requirements.
4. Define ExitPolicy separately from ProtectionPolicy. ProtectionPolicy is the
   minimum bounded-loss safety layer; ExitPolicy is the strategy's profit-taking,
   trailing, time-stop, invalidation, and lifecycle exit semantics.
5. Define attempt and budget consumption semantics: when an attempt is consumed,
   when notional/loss budget is reserved, how rejected/expired/canceled entries
   are treated, and how small budgeted losses differ from runaway behavior.
6. Define the first strategy families eligible for runtime execution.
7. Define right-tail objective implications for each eligible strategy family:
   small bounded losses are acceptable, right-tail winners must not be
   prematurely capped by generic safety defaults, Owner manual withdrawals are
   outside automated strategy control, and the system must not assume automatic
   compounding or automatic withdrawal.

Admission layering:

- Semantic Admission means the strategy can be represented, audited,
  constrained, and reviewed by the system. Lack of proven alpha is not a
  Semantic Admission blocker.
- Economic Admission means the strategy is eligible for larger budgets, lower
  Owner confirmation burden, or higher autonomy. Lack of proven alpha must
  limit Economic Admission.
- Execution Admission means one concrete candidate passes runtime boundary,
  FinalGate, Owner authorization, protection readiness, account facts, and
  deployment readiness checks.

Initial strategy-family reference candidates:

- `CPM-001` / pullback continuation is the long-only price-action reference
  implementation candidate. It is not a proven-alpha production strategy.
- `BRF-001` / bear rally failure short is the short-side price-action reference
  implementation candidate. It is not a proven-alpha production strategy.
- `RMR-001` / range or chop recognition is initially a regime classifier, not
  the first trading strategy.
- `FCO-001` / funding, open interest, and crowding remains a data-dependent
  backlog family until RequiredFacts and market-data freshness semantics are
  available.

RequiredFacts boundary:

- Every `StrategyImplementation` must declare `required_facts`,
  `optional_facts`, `freshness_requirement`, and `missing_fact_behavior`.
- Missing or stale facts must resolve explicitly to `NO_ACTION`,
  `OBSERVE_ONLY`, `BLOCK_MISSING_FACTS`, or `BLOCK_STALE_DATA`.
- Codex must not infer missing price, volume, funding, open-interest, account,
  position, or runtime facts in order to allow execution.

RMR boundary:

- RMR is a regime classifier first. It may emit market-state evidence such as
  `TREND_UP`, `TREND_DOWN`, `CHOP`, `RANGE`, or `UNCERTAIN`.
- RMR must not become a broad hard filter that silently blocks all strategies
  before its confidence, freshness, and failure modes are reviewed.
- High-confidence chop may downgrade CPM/BRF to observe-only or raise review
  requirements. Stale or missing RMR output must not be used as execution
  authority.

BRF short-side boundary:

- BRF requires a more conservative execution profile than long-only CPM:
  lower leverage, smaller notional, mandatory hard stop, strict
  `max_active_positions`, and Owner-confirm-each-entry until explicitly
  upgraded.
- BRF must not submit without concrete protection readiness. Short-side squeeze
  risk must be part of the strategy evidence and review semantics.

Right-tail review metrics:

- B0 review semantics must include MFE, MAE, R multiple, tail win size, small
  loss count, winner hold time, runner giveback, whether the runner was capped
  too early, stop effectiveness, and whether the attempt deserved continuation.
- Review must not reduce strategy performance to win rate, average return, or
  short-term PnL only.

Owner confirmation required:

- first eligible StrategyFamily / StrategyFamilyVersion;
- concrete StrategyImplementation source or adapter boundary;
- entry signal family and required evidence facts;
- initial entry policy;
- initial exit policy;
- protection policy;
- attempt consumption rule;
- budget reservation rule;
- whether runtime attempts are Owner-confirm-each-entry or budget-bounded
  automatic attempts for the first controlled execution profile.

Additional confirmation required before the first real submit:

- when an attempt is consumed;
- when budget reservation is released or confirmed consumed;
- how protection order creation failure is handled;
- how duplicate submit is blocked and audited;
- active position / account fact source and stale-fact behavior;
- deployment readiness, including whether the path is still local-only or tokyo
  has been verified.

Codex constraints:

- Codex must not invent strategy implementation details, signal rules, entry
  logic, exit logic, or attempt semantics without Owner confirmation.
- Codex may document architecture options, implementation boundaries, and
  validation gates.
- Codex may inspect existing strategy-related code and evidence to inform the
  options.
- Codex must not continue toward real OrderLifecycle adapter implementation
  until B0 is accepted.

Forbidden in B0:

- no code changes;
- no strategy optimization;
- no backtest parameter tuning;
- no real or testnet execution;
- no OrderLifecycle adapter implementation;
- no local order registration;
- no exchange submit;
- no automatic withdrawal or transfer design.

### Sprint 5: Controlled Runtime Execution Integration

Sprint 5 is gated by Mega Block B0. The non-executing execution
pre-integration artifacts listed below may remain as audit/preview facts, but
they must not be promoted into real OrderLifecycle adapter behavior or
controlled runtime execution until Strategy Semantics / Entry-Exit Policy
Binding is accepted by Owner.

Current execution pre-integration status already present locally:

- `RuntimeExecutionPlan` exists as a non-executable plan layer.
- `RuntimeExecutionIntentDraft` exists as a non-executable draft layer and can
  be recorded in `runtime_execution_intent_drafts`. It preserves candidate
  entry price, risk preview, and protection preview snapshots.
- `RuntimeExecutionIntentCreationPreview` exists as a non-executing adapter
  bridge. It uses `source_type=brc_runtime_order_candidate` and `source_id`
  rather than projecting OrderCandidate into legacy `SignalResult`, and carries
  the candidate entry/risk/protection snapshots in source payload.
- `ExecutionIntent` is source-native locally: `symbol` is first-class,
  `signal_id` / `signal_payload` are nullable legacy fields, and source-native
  runtime intents require `source_type` / `source_id`.
- Runtime OrderCandidate can be recorded as
  `ExecutionIntent(status=recorded, source_type=brc_runtime_order_candidate)`.
  The `recorded` status is not submit-ready and has no ExecutionOrchestrator
  transition edges.
- `RuntimeExecutionSubmitReadiness` exists as a non-submitting gate. It can
  inspect a recorded runtime intent and return
  `owner_submit_authorization_required`, but it does not authorize submit,
  create orders, call OwnerBoundedExecution, call OrderLifecycle, or call
  exchange.
- `RuntimeExecutionSubmitAuthorization` exists as a non-submitting Owner
  authorization record. It can record
  `approved_pending_controlled_submit` after explicit Owner submit confirmation,
  but it does not execute submit, create orders, call OwnerBoundedExecution,
  call OrderLifecycle, or call exchange.
- `RuntimeExecutionControlledSubmitPlan` exists as a non-submitting plan
  preview. It validates the submit authorization and recorded runtime intent can
  consistently reach `ready_for_controlled_submit_adapter`, but it does not
  execute submit, create orders, call OwnerBoundedExecution, call OrderLifecycle,
  or call exchange.
- `RuntimeExecutionControlledSubmitPreflight` exists as a non-submitting
  submit-time runtime FinalGate check. It reruns runtime-aware FinalGate with
  local active-position facts, `owner_reviewed=true`, and no explicit
  active-position query override. It can block submit-time drift without
  creating orders, calling OwnerBoundedExecution, calling OrderLifecycle, or
  calling exchange.
- `RuntimeExecutionControlledSubmitResult` exists as the default-disabled
  submit adapter boundary. It returns `submit_adapter_not_enabled` by default
  and `submit_adapter_not_implemented` if `submit_enabled=true` is requested
  before implementation only after the submit-time FinalGate preflight is ready.
  If the preflight is blocked, the result records `blocked` with the preflight
  status and FinalGate verdict. It does not execute submit, create orders, call
  OwnerBoundedExecution, call OrderLifecycle, or call exchange. Controlled submit
  results can be recorded in `runtime_execution_controlled_submit_results` so
  disabled / blocked / not-implemented submit attempts are auditable.
- `RuntimeExecutionSubmitAdapterPreview` exists as a non-executing adapter
  readiness preview. It consumes the submit-time preflight and recorded intent
  source payload, exposes missing OrderLifecycle/protection inputs such as
  `concrete_stop_price_missing`, and does not mutate runtime budget, consume an
  attempt, change ExecutionIntent status, create orders, call
  OwnerBoundedExecution, call OrderLifecycle, or call exchange.
- `RuntimeExecutionProtectionPlanPreview` exists as a runtime-native,
  non-executing protection readiness preview. It is derived from the recorded
  runtime intent source payload, not from one-shot `BoundedLiveTrialAuthorization`,
  and can reach `ready_for_submit_adapter` only when concrete stop price and
  candidate risk/protection snapshots are present.
- `RuntimeExecutionProtectionPlan` exists as a runtime-native protection plan
  audit record. It can record ready or blocked protection facts in
  `runtime_execution_protection_plans`, preserves concrete stop/take-profit
  snapshots when present, and remains `not_order=true` and
  `not_exchange_payload=true`.
- `RuntimeExecutionOrderLifecycleHandoffDraft` exists as a runtime-native,
  non-executing OrderLifecycle adapter input audit record. It can record ready
  or blocked handoff facts in
  `runtime_execution_order_lifecycle_handoff_drafts`, freezes the entry order
  draft, protection order draft, and Order-model-compatible draft facts a
  future OrderLifecycle adapter would need, and keeps
  `order_lifecycle_adapter_implemented=false`,
  `execution_intent_status_changed=false`, `order_created=false`,
  `exchange_called=false`, `owner_bounded_execution_called=false`, and
  `order_lifecycle_called=false`.
- `RuntimeExecutionOrderLifecycleAdapterPreview` exists as a non-executing
  local order registration gate. It consumes a recorded OrderLifecycle handoff
  draft, verifies Order-model-compatible draft facts, and returns
  `inputs_ready_registration_not_enabled` or `blocked` while keeping
  `local_order_registration_enabled=false`,
  `order_lifecycle_adapter_implemented=false`,
  `local_order_registration_executed=false`, `order_created=false`,
  `exchange_called=false`, `owner_bounded_execution_called=false`, and
  `order_lifecycle_called=false`.
- `RuntimeExecutionAttemptReservationPreview` exists as a non-mutating
  attempts/budget reservation preview. It computes attempts and budget
  before/after from `StrategyRuntimeInstance.boundary`, can reach
  `ready_to_reserve_attempt`, and keeps `reservation_recorded=false`,
  `runtime_budget_mutated=false`, and `attempt_consumed=false`. Its budget
  basis prefers `risk_preview.max_loss_reference` and falls back to
  `intended_notional` only when max-loss evidence is missing; `intended_notional`
  still remains the exposure value checked against `max_notional_per_attempt`.
- `RuntimeExecutionAttemptReservation` exists as a pending audit record. It can
  record `pending_runtime_mutation` from a ready reservation preview in
  `runtime_execution_attempt_reservations`, while keeping
  `runtime_budget_mutated=false`, `attempt_consumed=false`,
  `execution_intent_status_changed=false`, `order_created=false`, and
  `exchange_called=false`.
- `RuntimeExecutionAttemptMutation` exists as a controlled runtime state update
  record. It can apply a pending reservation to `StrategyRuntimeInstance` by
  incrementing `attempts_used` and `budget_reserved` using the reservation's
  max-loss-first budget basis, and records the mutation in
  `runtime_execution_attempt_mutations`. It blocks stale attempt/budget
  state drift and does not change ExecutionIntent status, create orders, call
  OwnerBoundedExecution, call OrderLifecycle, or call exchange.
- Current B0/B1 work may write a recorded `execution_intents` audit row. It
  may also write runtime submit authorization, controlled submit result, and
  attempt reservation / mutation / protection plan audit rows. It must not call
  OwnerBoundedExecution, call OrderLifecycle, submit orders, or call exchange.

Scope:

```text
StrategyRuntimeInstance
-> SignalEvaluation
-> OrderCandidate
-> FinalGate
-> ExecutionIntent
```

Required properties:

- Reuse existing safety boundaries.
- Execution is Owner-gated only.
- ExecutionIntent creation must occur through the approved path.
- Current one-shot OwnerBoundedExecution remains available.

Forbidden:

- no Operation Layer bypass;
- no real-funds or live-profile enablement by refactor;
- no runtime self-elevation;
- no unbounded symbol, side, leverage, notional, or attempt expansion.

### Sprint 6: Trading Console Runtime Productization

Scope:

- runtime shelf;
- runtime detail;
- signal evaluations;
- order candidates;
- attempts remaining;
- budget remaining;
- runtime review.

Required properties:

- Trading Console becomes an Owner operating surface for runtime governance.
- UI distinguishes readmodel, preview, shadow, candidate, authorized, gated,
  executable, active, paused, revoked, completed, and reviewed states where
  applicable.
- Product wording must not overclaim capabilities not implemented in tracked
  code.

### Sprint 7: Runtime / Config / Safety Boundary Consolidation

Scope:

- Runtime Profile / ConfigManager multi-track governance;
- ExecutionPermission coverage;
- CapitalProtection enforcement review;
- scripts bypass containment.

Required properties:

- Consolidate authority boundaries without changing live runtime profile or
  live trading config by default.
- Identify gaps between permission, capital protection, runtime profile, and
  script entry points.
- Contain bypass risk before broad cleanup.

### Sprint 8: API / ReadModel Decomposition

Scope:

- large API/readmodel file decomposition;
- Trading Console API truth-source cleanup;
- readmodel/action semantics layering.

Required properties:

- Split for maintainability after core semantic model is stable.
- Preserve frontend behavior unless an explicit UI/API task approves changes.
- Keep action APIs distinct from readmodel and preview APIs.

### Sprint 9: Legacy Scripts / Sandbox Cleanup

Scope:

- scripts risk grading;
- sandbox / research engineering downgrade;
- dead path cleanup.

Required properties:

- Grade scripts by exchange/database/runtime risk before cleanup.
- Preserve evidence needed for current canon or ADR traceability.
- Delete only after replacement or irrelevance is verified.

### Sprint 10: Documentation / Evidence Physical Reorganization

Scope:

- move appropriate docs/ops physical evidence to docs/evidence;
- organize archive structure;
- reduce docs/ops crowding.

Required properties:

- Non-blocking and last-phase.
- Canon remains the current fact source.
- Historical evidence remains available but cannot override canon.
- Agent instruction files are not re-authorized by physical movement.

---

## 7. Per-Sprint Review Checklist

Each sprint must review:

1. Was the sprint objective completed?
2. Were any forbidden changes violated?
3. Was the one-shot path broken or behaviorally changed?
4. Did the sprint produce any non-additive migration?
5. Did the sprint touch execution/order path?
6. Is a `docs/canon` update needed?
7. Were tests added where the sprint allowed implementation?
8. Were there any unstated API or DB behavior changes?
9. Can the program safely enter the next sprint?
10. Does the next sprint need a narrower scope?
11. Are metadata, readmodel, preview, shadow, and executable states still
    clearly separated?
12. Are secrets and secret-adjacent values masked?
13. Did agents stay inside allowed files?
14. Did the work preserve FinalGate and Operation Layer boundaries?

---

## 8. Stop Conditions

Stop and report if any sprint requires:

- modifying exchange order placement;
- replacing `OwnerBoundedExecutionService`;
- changing current one-shot execute behavior;
- destructive migration;
- live/testnet connection;
- allowing `StrategyRuntimeInstance` to place orders directly;
- allowing `SignalPipeline` to automatically enter execution;
- promoting runtime execution pre-integration into real OrderLifecycle adapter
  behavior before Mega Block B0 is accepted;
- completing the sprint only by breaking the old one-shot chain;
- resolving a canon/code fact conflict without Codex/Owner review;
- outputting secrets;
- changing live runtime profile, live trading config, credentials, or
  real-funds order-sizing defaults;
- bypassing or weakening FinalGate;
- bypassing the Operation Layer.

---

## 9. What Is Explicitly Deferred

These items are intentionally deferred, not forgotten:

- Runtime Profile / ConfigManager consolidation.
- Script bypass cleanup.
- API/readmodel decomposition.
- Trading Console runtime productization.
- `docs/ops` physical reorganization.
- Legacy sandbox cleanup.
- Full runtime execution integration.

The reason for deferral is sequencing: the program must first establish the
runtime semantic backbone, audit ID spine, and shadow candidate path before
consolidating surrounding surfaces.

---

## 10. Codex Execution Report Format

Each sprint must end with:

```text
# Sprint Report

## 1. Summary
## 2. Branch / Commits
## 3. Files Changed
## 4. What Was Implemented
## 5. What Was Not Changed
## 6. Boundary Compliance
## 7. Tests / Validation
## 8. Migration Safety
## 9. Risks / Open Questions
## 10. Recommended Next Sprint
```

The report must explicitly state whether the sprint was shadow-only or touched
an executable path. It must also state whether canon updates are required.

---

## 11. Canon Update Rules

`docs/canon` is the current fact source and should not grow into a sprint log.

Rules:

- Sprint plans and execution records live in `docs/ops`.
- Sprint reports cannot override canon.
- Update `docs/canon` only when current facts or target semantics have changed
  in a stable way.
- Stable changes require tracked code verification, explicit Owner decision,
  accepted ADR, or a verified report that does not conflict with code.
- Do not update canon from proposals, unmerged work, shadow-only intentions, or
  historical docs.
- Do not mark `StrategyRuntimeInstance` as implemented until tracked code
  implements it and Codex verifies the behavior.
- Do not mark one-shot OwnerBoundedExecution as final architecture.
- If a sprint discovers conflict between canon and code fact, stop and report.

Likely canon files affected after future implementation sprints:

- `docs/canon/PROJECT_BASELINE_CURRENT.md`
- `docs/canon/BRC_TARGET_SEMANTICS.md`
- `docs/canon/TECH_DEBT_BASELINE.md`
- `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
- `docs/canon/AGENT_WORKSPACE_RULES.md`

Canon should remain short, factual, and free of implementation diaries.
