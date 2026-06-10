---
title: PROJECT_BASELINE_CURRENT
status: CURRENT_CANON
authority: owner-correction + code-verification + semantic-audit
last_verified: 2026-06-10
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
  strategy. It now has a pure closed-candle classifier implementation for
  regime evidence only.
- FCO is a funding / open-interest / crowding backlog family until
  deployment-backed fact coverage, freshness, missing-fact behavior, and Owner
  strategy semantics are confirmed. A Binance USD-M public derivative fact
  reader now exists as B0 infrastructure, but FCO is not promoted by that alone.

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
  call exchange, or prove alpha. The binding service also has a B0
  non-executing orchestration path that accepts a coherent
  `StrategyFamilySignalInput` + `StrategyFamilySignalOutput` pair, builds the
  StrategyEvaluationContext, and then applies the same RequiredFacts gate before
  shadow candidate creation.
- **StrategyEvaluationContextBuilder** now exists as a local non-executing B0
  application mapper from `StrategyFamilySignalInput`,
  `StrategyFamilySignalOutput`, and optional `StrategyRuntimeInstance` snapshots
  into RequiredFacts. It can surface available OHLCV, price-action, account,
  runtime-boundary, position-projection, funding, range, volatility, and
  crowding-related facts while marking absent data as missing instead of
  inventing it. It intentionally blocks or downgrades cases such as missing 4h
  CPM context, observation-only account facts, BRF without explicit
  short-squeeze risk facts, and FCO without open-interest/crowding sources.
- **RMR Regime Classifier** now exists as a pure closed-candle classifier for
  `TREND_UP`, `TREND_DOWN`, `CHOP`, `RANGE`, and `UNCERTAIN`. The context
  builder can use RMR-001 classifier output to populate `range_structure`,
  `volatility_state`, and `market_state` facts. RMR output is observe/downgrade
  evidence only: it is not an order candidate, execution intent, hard execution
  filter, or trading authority.
- **BRF Price Action Evaluator** now exists as a pure closed-candle
  bear-rally-failure evaluator for `BRF-001` / `BRF-001-v0`. It can emit
  short-side `StrategyFamilySignalOutput` review evidence with explicit
  `price_action_structure` and `short_squeeze_risk` facts, allowing B0
  required-fact checks to pass when the evidence is present. It remains
  observe-only and cannot create sizing, leverage, venue, route, order, or
  execution instructions.
- **StrategyRuntimeFactOverlayService** now exists as a local non-executing
  read-only fact overlay before B0 strategy signal planning. When explicitly
  injected, it replaces caller-provided account/position/market allow facts
  with trusted local/read-only sources, marks missing/stale account, position,
  funding, open-interest, or crowding facts through `SignalDataQuality`, and
  lets B0 RequiredFacts fail closed rather than trusting owner/user-supplied
  active-position counts or manually supplied derivative-market facts.
  `BinanceUsdmDerivativeMarketFactSource` can supply trusted public/read-only
  funding, open-interest, and global long/short account-ratio crowding facts,
  and Trading Console can opt into that source via
  `TRADING_CONSOLE_PUBLIC_MARKET_FACTS_ENABLED=true`. Scheduler-level readiness
  and an explicit non-executing scheduler-to-planner handoff now exist for
  automatic evaluation binding. Trading Console now exposes an operator-auth
  explicit non-executing shadow-plan POST for server-side strategy signal
  evaluation and optional shadow candidate creation, but deployment automation
  and scheduler-backed ingestion are not yet productized.
- **StrategyRuntimePromotionGate** now exists as a pure non-executing domain
  gate for promotion beyond B0 shadow/preview work. It turns missing
  Owner/Codex strategy, runtime, fact-source, runtime safety boundary,
  BRF short-profile, and first real submit confirmations into explicit
  blockers. The runtime safety confirmations now separately cover max-loss
  budget, max-notional boundary, max-leverage boundary, margin usage boundary,
  liquidation-buffer boundary, protection-readiness source, stale-fact
  behavior, trusted account facts, and trusted active-position facts while
  preserving
  `not_execution_authority=true`, `execution_intent_created=false`,
  `order_created=false`, and `exchange_called=false`. A small application
  service can evaluate the gate by `StrategyFamilyVersion` from the semantics
  catalog without guessing unknown bindings. Trading Console exposes a read-only
  promotion-gate preview endpoint for this result, including a runtime-id route
  that resolves `StrategyFamilyVersion` from `StrategyRuntimeInstance`; it does
  not record strategy signals, create candidates, create intents, or authorize
  execution.
- **StrategyRuntimeSafetyReadiness** now exists as a pure non-executing runtime
  boundary fact-readiness model and Trading Console GET endpoint. It inspects a
  `StrategyRuntimeInstance.boundary` and reports whether symbol/side,
  attempts, max-loss budget, max notional, max active positions, max leverage,
  max margin, liquidation buffer, protection requirement, review requirement,
  trusted fact-source needs, and stale-fact behavior are present or still need
  Owner/Codex confirmation. It does not confirm those facts by itself, mutate
  runtime state, create candidates, create intents, create orders, or call
  exchange.
- **RuntimeStrategySignalPlanningService** now exists as a local non-executing
  bridge from strategy signals into the runtime planning path. It can run:
  `StrategyFamilySignalInput + StrategyFamilySignalOutput ->
  StrategyEvaluationContext -> shadow OrderCandidate -> RuntimeExecutionPlan /
  RuntimeExecutionIntentDraft`, while preserving `not_order=true`,
  `not_execution_intent=true`, `execution_intent_created=false`,
  `order_created=false`, and `exchange_called=false`. It can also evaluate a
  raw `StrategyFamilySignalInput` through `RuntimeStrategySignalEvaluationService`
  before creating a shadow candidate, but only when the evaluator returns
  `READY_FOR_SEMANTIC_BINDING`. In that path it generates a non-executing
  planning proposal with entry price, structure/ATR stop reference, runtime
  notional/leverage/loss preview, TP1 1R partial, and runner/trailing metadata
  for CPM long and BRF short. If a trusted runtime fact overlay is injected, it
  applies that overlay before semantic binding and blocks candidate planning
  when trusted account/position/runtime boundary facts are missing. It now
  reads StrategySemantics RequiredFacts and automatically requires trusted
  market facts for required funding, open-interest, or crowding facts; if no
  overlay is available for such a strategy, planning fails closed. It does not
  expose owner-supplied active-position counts as an allow fact; runtime
  FinalGate must use configured local active-position facts or block when
  unavailable. Trading Console now has an internal non-endpoint service factory
  that wires this planner with PG active-position facts and cached account facts;
  the only public Trading Console trigger added for this path is the
  operator-auth non-executing shadow-plan POST described below.
- **RuntimeStrategySignalSchedulerAssemblyService** now exists as a pure
  non-executing scheduler-level readiness layer. It evaluates whether a
  `StrategyFamilySignalInput` + `StrategyFamilySignalOutput` pair has strategy
  semantics, a matching shadow runtime, trusted active-position/account fact
  sources, and strategy-required trusted market facts before a scheduler may
  hand it to the existing B0 runtime signal planner. The read-only strategy
  group observation and scheduled observation outputs now include
  `runtime_signal_planning_readiness` / `runtime_signal_planning_summary`.
  This layer does not call RuntimeStrategySignalPlanningService, create
  SignalEvaluation records, create OrderCandidate records, create
  ExecutionIntent records, create orders, call OrderLifecycle, or call exchange.
- **RuntimeStrategySignalSchedulerPlanningService** now exists as an explicit
  non-executing scheduler handoff layer. It preserves the scheduler assembly as
  readiness-only, then calls the shadow runtime strategy planner only when
  readiness is `READY_FOR_NON_EXECUTING_PLANNER` and the caller explicitly sets
  `allow_shadow_candidate_creation=true`. Without that explicit enablement it
  returns `explicit_enable_required` and performs no planner call. It can create
  only the same shadow SignalEvaluation / OrderCandidate records as the B0
  planner. Trading Console exposes this as
  `POST /api/trading-console/strategy-runtimes/{runtime_instance_id}/strategy-signal-shadow-plans`;
  the endpoint runs server-side evaluation first, uses configured runtime /
  account / active-position fact sources, and remains non-executing. It does
  not create ExecutionIntent records, create orders, call OrderLifecycle, call
  exchange, or provide execution authority.
- **RightTailReview** now exists as pure review logic plus Trading Console
  read-only presentation. It calculates MFE, MAE, R multiple, tail-win size,
  small-loss count, winner hold time, runner giveback / early cap, stop
  effectiveness, and attempt-continuation quality only from explicit
  `live_lifecycle_review.metadata.right_tail_trade_path` facts. Missing trade
  path facts remain `review_inputs_required`; the readmodel does not infer from
  orders or exchange and does not create execution, order, budget, strategy-PnL,
  exchange, or withdrawal authority.
- **RuntimeSemanticReviewPacket** now exists as a pure non-executing packet
  generator for `BrcLiveLifecycleReviewRecord`. It preserves runtime / trial /
  strategy-version / signal-evaluation / order-candidate / execution-intent IDs
  when present, marks missing semantic trace explicitly, reviews right-tail
  facts only from explicit lifecycle metadata, and is surfaced in Trading
  Console `right_tail_review.closed_trade_review_packets`. It does not create
  orders, ExecutionIntent records, exchange calls, runtime-budget mutations,
  strategy-PnL mutations, or withdrawal instructions.
- **Position runtime semantic ID propagation** now exists as an additive local
  slice. `Position` and PG `positions` can carry nullable runtime / trial /
  strategy-version / signal-evaluation / order-candidate IDs; entry-fill
  projection inherits them from the entry `Order` while preserving existing
  IDs when a later entry update lacks them; Trading Console position readmodels
  surface these IDs for active-position and review traceability. This does not
  create orders, call exchange, or alter one-shot execution authority.
- **Runtime-aware FinalGate preview** now exists as read-only dry-run
  inspection for runtime order candidates. It does not mutate runtime state,
  create ExecutionIntent records, place orders, or call the exchange. Its
  budget check now separates notional exposure from loss budget:
  `max_notional_per_attempt` checks candidate notional, while runtime budget
  remaining prefers `risk_preview.max_loss_reference` and falls back to notional
  only when max-loss evidence is missing.
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
  `attempt_consumed=false`. Budget reservation now prefers
  `risk_preview.max_loss_reference` as the trial-loss budget amount; it falls
  back to `intended_notional` only when max-loss evidence is missing, while
  still checking `intended_notional` against `max_notional_per_attempt`.
  RuntimeExecutionAttemptReservation can record `pending_runtime_mutation` as
  an audit fact while still keeping `runtime_budget_mutated=false`,
  `attempt_consumed=false`, `execution_intent_status_changed=false`,
  `order_created=false`, and `exchange_called=false`.
  RuntimeExecutionAttemptMutation can apply that pending reservation to runtime
  state by incrementing `attempts_used` and `budget_reserved` using the same
  max-loss-first budget basis. It blocks stale attempt/budget drift and still
  keeps `execution_intent_status_changed=false`,
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
- Owner profit withdrawal is manual. The system can record Owner external
  withdrawal/capital-base adjustment facts and account-equity/capital-base
  baseline snapshots for review and Trading Console capital-base
  classification, but must not initiate withdrawals, transfers, or fund
  movement.
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
