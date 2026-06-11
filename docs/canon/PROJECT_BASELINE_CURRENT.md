---
title: PROJECT_BASELINE_CURRENT
status: CURRENT_CANON
authority: owner-correction + code-verification + semantic-audit
last_verified: 2026-06-11
supersedes:
  - docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md (for canon reading order)
source_of_truth:
  - docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md
  - docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md
  - docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md
  - docs/canon/STRATEGY_RUNTIME_GUIDE.md
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

Strategy implementation and runtime wiring must follow
`docs/canon/STRATEGY_RUNTIME_GUIDE.md`. In particular, the target is bounded
free trading inside an Owner-approved StrategyRuntimeInstance, not repeated
per-entry manual approval forever. The Owner-supplied isolated subaccount
capital is already risk-scoped experimental capital; system risk control should
prevent loss of control, not suppress every losing trade.

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

Current strategy-semantics guideposts are:

- CPM is a long-only pullback-continuation price-action reference
  implementation candidate, not a proven-alpha production strategy.
- BRF is a short-side bear-rally-failure price-action reference implementation
  candidate, not a proven-alpha production strategy.
- BTPC / LSR / RBR / VCB are near-term candidate strategy semantics for
  short-side continuation, liquidity-sweep reversal, range-boundary reversion,
  and volatility-compression breakout coverage. They must enter through typed
  StrategyImplementation / RequiredFacts / EntryPolicy / ProtectionPolicy /
  ExitPolicy semantics, not hard-coded execution logic.
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
- **StrategyRuntimeInstance** now exists as a local working-tree runtime
  governance record with PG persistence and lifecycle events. It defaults to a
  non-executing shadow record (`execution_enabled=false`, `shadow_mode=true`).
  A 065 migration and domain/service mutation path now allow an Owner/Codex
  gated live-runtime enablement mutation to flip an ACTIVE runtime to
  `execution_enabled=true`, `shadow_mode=false`; that mutation is not order
  authority and still does not create candidates, intents, orders,
  OrderLifecycle calls, or exchange calls. The application service can create a
  shadow runtime draft from a TrialBinding plus a fully confirmed runtime
  profile proposal snapshot, copying the proposal boundary while keeping
  execution disabled.
  The BRC Console exposes a narrow operator-auth API for this draft creation
  path under
  `/api/brc/strategy-runtime-promotion-confirmations/{confirmation_id}/runtime-drafts`;
  it does not create candidates, intents, orders, OrderLifecycle calls, or
  exchange calls. The BRC Console also exposes a narrow shadow lifecycle API
  for `activate_shadow`, `pause_shadow`, and `revoke_shadow`; it mutates only
  runtime status and preserves `execution_enabled=false` / `shadow_mode=true`.
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
- **Reference Price Action Evaluators** now exist locally for `BTPC-001`,
  `LSR-001`, `RBR-001`, and `VCB-001`. They are closed-candle OHLCV reference
  implementations for bear-trend pullback continuation, liquidity-sweep
  reversal, range-boundary reversion, and volatility-compression breakout.
  Each can emit non-executing `StrategyFamilySignalOutput` evidence with a
  typed `candidate_semantics` snapshot for entry, protection, exit, payoff
  profile, and quality. Trend/right-tail strategies use TP1 + runner semantics;
  range/mean-reversion strategies use fixed RR/range-target semantics. They do
  not prove alpha, size orders, choose leverage, create candidates by
  themselves, create intents, or call exchange. Trading Console read-only
  strategy observation now surfaces BTPC / LSR / RBR / VCB candidates and their
  typed `candidate_semantics` snapshots alongside CPM / BRF readiness.
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
  evaluation and optional shadow candidate creation. The scheduled read-only
  observation runner can now preserve the full signal input snapshot and, when
  explicitly injected with `StrategyRuntimeObservationResolver` plus
  scheduler-planning service, resolve exactly one ACTIVE shadow runtime from
  `StrategyRuntimeInstanceService` before handing the observed signal to the
  non-executing shadow planner. Missing, ineligible, expired, side-mismatched,
  or ambiguous runtime matches do not call the planner. Tokyo autonomous
  scheduling / triggering remains disabled unless separately wired and
  authorized. The local scheduled-observation CLI remains observation-only by
  default; it can opt into this non-executing resolver/planner wiring with
  `--shadow-plan`, and can only allow shadow candidate creation with the
  additional `--allow-shadow-candidate-creation` flag. If no trusted account
  facts source is configured, shadow planning blocks instead of fabricating
  readiness. Trading Console also exposes an operator-auth manual
  `POST /api/trading-console/strategy-observations/scheduled-runs` endpoint for
  the same non-executing scheduled observation path; it is not an autonomous
  scheduler and not submit authority. A local in-memory verifier,
  `scripts/verify_strategy_observation_shadow_planning_rehearsal.py`, exercises
  the real scheduled-observation resolver/planner path with static read-only
  facts and proves CPM can create one shadow candidate while execution intent,
  order, OrderLifecycle, exchange, and withdrawal/transfer flags remain false.
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
  execution. `StrategyRuntimePromotionGateConfirmationRecord` can now freeze an
  accepted runtime profile proposal snapshot as structured audit evidence while
  preserving no-action flags; the snapshot still does not create a runtime,
  mutate live config, or authorize submit.
- **StrategyRuntimeSafetyReadiness** now exists as a pure non-executing runtime
  boundary fact-readiness model and Trading Console GET endpoint. It inspects a
  `StrategyRuntimeInstance.boundary` and reports whether symbol/side,
  attempts, max-loss budget, max notional, max active positions, max leverage,
  max margin, liquidation buffer, protection requirement, review requirement,
  trusted fact-source needs, and stale-fact behavior are present or still need
  Owner/Codex confirmation. It does not confirm those facts by itself, mutate
  runtime state, create candidates, create intents, create orders, or call
  exchange.
- **ExperimentalRuntimeProfileProposal** now exists as a pure non-executing
  small-capital runtime profile proposal. It translates the Owner's 30U
  experimental-risk-capital intent into reviewable `StrategyRuntimeBoundary`
  values for eligible strategy semantics, including conservative BRF/short and
  mean-reversion envelopes. The Trading Console exposes it as
  `GET /api/trading-console/strategy-runtime-profile-proposals`. It is not a
  runtime record, not Owner/Codex confirmation, not live-profile enablement, not
  an ExecutionIntent, and not order/exchange authority. Only a separate
  promotion confirmation record plus TrialBinding can feed a shadow runtime
  draft, and that draft remains non-executable.
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
  record / runtime protection-failure policy gate / runtime OrderLifecycle
  handoff draft audit record / non-executing OrderLifecycle adapter preview
  gate / typed local order registration draft preview / first-real-submit
  local-registration gate / evidence-based local registration enablement
  decision / default-disabled OrderLifecycle adapter
  result skeleton / ExecutionIntent local-order linkage
  gate / submit adapter readiness preview / runtime submit rehearsal aggregate /
  exchange-submit packet preview / exchange-submit enablement decision /
  exchange-submit action authorization / default-disabled exchange-submit
  adapter and execution results**
  now exist in
  tracked code as bounded bridge layers. Deployment state must be verified from
  the current release manifest and postdeploy reports, not inferred from this
  canon paragraph.
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
  preflight: it returns `blocked` when the preflight is not ready,
  `submit_adapter_not_enabled` by default, and
  `order_lifecycle_adapter_disabled` if explicit submit is requested before
  the OrderLifecycle adapter is enabled. Controlled submit results are recorded
  in their own audit table. RuntimeExecutionSubmitAdapterPreview now reaches
  `inputs_ready_dry_run_adapter_only` when submit inputs are complete, while
  keeping `real_submit_enabled=false`, `order_lifecycle_adapter_enabled=false`,
  `order_created=false`, `order_lifecycle_called=false`, and
  `exchange_called=false`. RuntimeExecutionProtectionPlanPreview is derived from
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
  RuntimeExecutionOrderRegistrationDraftPreview can additionally type-check the
  local entry/protection registration draft facts as
  `inputs_ready_registration_draft_only` while keeping
  `order_objects_constructed=false`, `local_order_registration_executed=false`,
  `order_created=false`, `order_lifecycle_called=false`, and
  `exchange_called=false`.
  RuntimeExecutionLocalRegistrationGate can require Owner real-submit
  authorization evidence, trusted submit facts, submit idempotency evidence,
  attempt-outcome policy evidence, protection-failure policy evidence,
  adapter/local-registration enablement, and an explicit scoped
  local-registration action authorization before any local
  `Order(status=CREATED)` registration. It is not real-submit authority and
  cannot call exchange or change ExecutionIntent status. The pre-live verifier
  can now explicitly exercise this pre-exchange local-registration path in
  memory: it registers local CREATED entry/protection orders and reaches
  exchange-submit packet-preview readiness while still keeping exchange submit
  disabled.
  RuntimeExecutionIntentLocalOrderLinkage can separately mark a source-native
  ExecutionIntent as `local_orders_registered` and link the entry local
  `order_id` after a successful adapter result plus explicit linkage enablement.
  It keeps `exchange_order_id=null` and is not exchange-submit authority.
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
  inputs without mutating runtime budget or creating orders.
  RuntimeExecutionSubmitRehearsal aggregates submit-readiness, controlled-submit
  plan, submit-time preflight, protection preview, attempt reservation preview,
  and submit adapter preview into one operator-facing non-mutating rehearsal
  result. It does not record reservations, apply attempt mutations, record
  protection plans, record OrderLifecycle handoff drafts, create orders, call
  OwnerBoundedExecution, call OrderLifecycle, or call exchange. These upstream
  rehearsal layers do not call OwnerBoundedExecution, call OrderLifecycle, place
  orders, or call the exchange.
  RuntimeExecutionExchangeSubmitPacketPreview and
  RuntimeExecutionExchangeSubmitEnablementDecision can prove local registered
  orders are structurally ready for exchange submit without calling exchange or
  OrderLifecycle submit. RuntimeExecutionExchangeSubmitActionAuthorization is
  scoped first-real-submit / exchange-stage action evidence. Exchange-submit
  adapter/result and execution paths are default-disabled; when explicitly
  enabled, the application service revalidates persisted first-real-submit
  prerequisite evidence at the action point before acquiring duplicate-submit
  locks or calling the exchange gateway. The adapter-result stage must not call
  exchange. The execution-result stage may call the exchange gateway only after
  explicit execution enablement, gateway readiness, recovery/idempotency checks,
  protection-failure policy, Owner/deployment evidence, and scoped action
  authorization all validate.
  `scripts/verify_runtime_submit_rehearsal_pre_live_packet.py` now exercises
  that chain with in-memory repositories and reports a first-real-submit packet:
  the staged submit chain can be available without treating the legacy monolithic
  submit adapter as a missing implementation blocker. With explicit Owner flags
  and `--exercise-local-registration-pre-exchange`, it can also prove the
  pre-exchange local-registration segment: scoped local-registration action
  authorization, local CREATED entry/protection order registration, intent
  local-order binding, and exchange-submit packet-preview readiness. First real
  submit still remains blocked by exchange-submit enablement, scoped exchange
  submit action authorization, gateway/recovery readiness, and action-time
  revalidation unless the explicit exchange-submit pre-execution rehearsal is
  requested. With `--exercise-exchange-submit-adapter-pre-execution`, the same
  verifier can assemble in-memory gateway readiness, scoped exchange-submit
  action authorization, exchange-submit enablement, and an exchange-submit
  adapter-result duplicate-submit lock. It also proves the true execution
  result entrypoint remains disabled unless explicitly enabled, returning
  `exchange_submit_execution_disabled` without gateway or OrderLifecycle submit
  calls. That path intentionally stops at
  `exchange_submit_adapter_armed` /
  `exchange_submit_execution_disabled`: it does not call exchange, submit an
  order, call OrderLifecycle submit, execute the real exchange adapter, or
  change ExecutionIntent status. A shadow / execution-disabled runtime is the
  expected source state before a live-runtime enablement mutation, not itself
  proof of a missing implementation. With the additional
  `--exercise-in-memory-exchange-execution-simulation` flag, the verifier can
  run the enabled execution-result branch against an in-memory fake exchange
  gateway and in-memory OrderLifecycle only, proving entry/protection submit
  result wiring without Binance, network, credentials, deployment mutation, or
  real-funds order placement. The OrderLifecycle adapter enablement packet now
  treats local CREATED order registration capability as implemented separately
  from action-time enablement evidence: without explicit local-registration
  rehearsal it blocks on `local_registration_pre_exchange_not_ready`, and with
  Owner flags plus `--exercise-local-registration-pre-exchange` it can report
  `ready_for_runtime_order_lifecycle_adapter_enablement` while still not
  authorizing exchange submit. The Owner first-real-submit decision packet and
  OrderLifecycle adapter enablement packet can also surface these exchange
  pre-execution / fake-gateway simulation evidence fields without making them
  live submit authority. The Owner first-real-submit packet now exposes an
  explicit `first_real_submit_action_boundary` so
  `packet_ready_for_owner_decision=true` is not confused with
  `ready_for_first_real_submit=true`; local registration readiness, exchange
  pre-execution readiness, and true exchange-submit action readiness remain
  separate facts.
- **StrategyRuntimeLiveEnablementPreview** now exists as a pure non-executing
  pre-live gate. It combines concrete runtime safety readiness, first-real-submit
  promotion gate status, current-head deployment status, Owner live-runtime
  enablement authorization, Owner real-submit authorization, submit rehearsal
  status, staged submit-chain availability, and forbidden execution flags into
  explicit blockers. A ready result means only
  `ready_for_live_runtime_enablement_mutation_design`; it does not by itself
  mutate `StrategyRuntimeInstance`, enable `execution_enabled`, create
  ExecutionIntent/order records, call OwnerBoundedExecution, call OrderLifecycle,
  call exchange, or authorize real-funds submit. A separate
  `StrategyRuntimeLiveEnablementMutation` domain/application path can now apply
  the live-runtime flag transition after a ready preview and explicit Owner
  live-runtime plus real-submit authorization IDs. The mutation records a
  `live_runtime_enabled` runtime event and flips only the runtime governance
  flags; it preserves no-order/no-exchange/no-OrderLifecycle invariants.
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
- **Tokyo deployment note:** current Tokyo deployment was verified on
  commit `ae9b209e` / Alembic head
  `2026-06-10-064_add_runtime_profile_proposal_snapshot.py` with
  `runtime_bound=true` and `live_ready=false`. This is a non-executing
  runtime-governance deployment; it is not live-submit authorization, not order
  authority, and not an Owner approval for real-funds trading. Local release
  work after that deployment now includes migration 065 for Owner-gated
  live-runtime flag persistence; it is not deployed to Tokyo yet.

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
- Do not treat an ExperimentalRuntimeProfileProposal as a confirmed
  StrategyRuntimeInstance, live runtime profile, Owner/Codex confirmation,
  ExecutionIntent, or order authority.
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
