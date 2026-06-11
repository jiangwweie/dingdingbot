---
title: BRC_TARGET_SEMANTICS
status: CURRENT_CANON
authority: owner-semantic-audit + code-verification
last_verified: 2026-06-11
source_of_truth:
  - docs/canon/PROJECT_BASELINE_CURRENT.md
  - docs/canon/STRATEGY_RUNTIME_GUIDE.md
  - owner semantic audit 2026-06-09
  - tracked code verification
---

# BRC Target Semantics

This document defines the target semantic chain for BRC and maps each node to
its current code status.

---

## 1. Target Principle

BRC authorization object should be:

```text
bounded StrategyRuntimeInstance
```

Not:

```text
single trade order
```

The Owner should authorize a strategy running within risk boundaries, not one
immediate trade.

BRC uses small experimental risk capital to pursue right-tail asymmetric
returns. Runtime governance should allow budgeted small losses and failed
experiments while preventing loss of control, unauditable orders, boundary
breach, and automatic asset management behavior.

Strategy readiness is not a single yes/no gate:

- Semantic Admission asks whether a strategy can be expressed, audited,
  constrained, and reviewed. Lack of proven alpha is not a blocker here.
- Economic Admission asks whether a strategy deserves larger budget, lower
  Owner confirmation burden, or more autonomy. Lack of proven alpha restricts
  this layer.
- Execution Admission asks whether one concrete OrderCandidate can pass runtime
  boundary, FinalGate, Owner authorization, protection readiness, account facts,
  idempotency, and deployment readiness.

---

## 2. Target Chain

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

---

## 3. Current Status by Node

| Node | Current Status | Current Code Reality | Target Meaning |
| ---- | -------------- | -------------------- | -------------- |
| StrategyFamily | metadata only | Strategy family classification exists as metadata / admission | Strategy identity and risk profile |
| StrategyFamilyVersion | metadata only | Strategy specification document; not bound to executable strategy code | Versioned executable strategy definition |
| AdmissionDecision | partially implemented | Admission gate metadata operations (Phase 1-17) complete | Formal admission pass/fail with evidence |
| OwnerRiskAcceptance | partially implemented | OwnerRiskAcknowledgement exists for single-use authorization | Owner acceptance of strategy runtime risk |
| TrialBinding | metadata only | Audit binding record; not a running strategy instance | Binding between admitted strategy and runtime instance |
| StrategyRuntimeInstance | shadow implemented | Shadow governance model, PG table, repository, lifecycle events, and readmodel/API inspection exist; execution is disabled and shadow_mode is enforced; a fully confirmed profile proposal snapshot can create a shadow draft boundary from TrialBinding without enabling execution | Running bounded strategy instance that generates evaluations |
| SignalEvaluation | shadow implemented | Shadow model, PG table, repository, service, and inspection API exist; no executable trigger | Per-instance signal evaluation within risk boundaries |
| OrderCandidate | shadow implemented | Shadow candidate model and PG table exist; candidate_executable=false and not_execution_intent=true are enforced | Executable order candidate from signal evaluation |
| FinalGate | implemented + runtime preview | FinalGate exists as hard one-shot execution gate; runtime-aware preview/dry-run exists for OrderCandidate inspection only | Pre-execution safety validation |
| ExecutionIntent | partially implemented | Execution permission system has 6 levels; source-native recorded intent audit, Owner submit authorization record, controlled-submit plan, submit-time FinalGate preflight, preflight-gated controlled-submit result, non-mutating attempt reservation preview, pending attempt reservation audit record, controlled runtime attempt mutation record, runtime-native protection plan preview/record, runtime protection-failure policy gate, runtime OrderLifecycle handoff draft record, non-executing OrderLifecycle adapter preview gate, typed local order registration draft preview, first-real-submit local-registration gate, evidence-based local-registration enablement decision, default-disabled adapter result, explicit local-order linkage to `local_orders_registered`, non-executing submit adapter preview, non-mutating submit rehearsal aggregate, exchange-submit packet/enablement/action evidence, default-disabled exchange-submit adapter/execution result stages, a canonical first-real-submit action wrapper, post-submit outcome accounting evidence, post-submit settlement persistence-path evidence, PG-persisted post-submit budget settlement, and a read-only first-real-submit final review packet exist in the local working tree for `brc_runtime_order_candidate`; `recorded` is not submit-ready, `local_orders_registered` is not exchange-submitted, final-review readiness is not action authorization, first-real-submit readiness can prove settlement persistence path `runtime-post-submit-budget-settlement-persistence-084` without requiring a prior settlement record, and exchange calls remain blocked unless explicit first-real-submit action confirmation plus action-point prerequisite evidence revalidation pass | Bounded execution intent from order candidate |
| OrderLifecycle | implemented | Order lifecycle service handles order placement and tracking | Order lifecycle management with strategy semantic IDs |
| Order / Position | implemented | Order and position management through exchange gateway | Live order and position tracking |
| Reconciliation | implemented | Reconciliation service exists | PG / exchange consistency verification |
| Review | partially implemented | Review Ledger design exists; limited production review data; first-real-submit outcome accounting can record submit outcome review and derive attempt-outcome policy when local order facts plus post-submit reconciliation evidence are resolved; missing reconciliation evidence or severe mismatch blocks accounting, while warning-only mismatch is recorded as warning; PG-persisted post-submit budget settlement can release no-fill/rejected reserved budget or record held/consumed reserved budget for filled outcomes without order/exchange side effects | Full review with strategy semantic traceability |

Status legend:

- **implemented**: exists in tracked code and functional
- **shadow implemented**: exists in tracked code as non-executable
  governance/inspection state only
- **partially implemented**: exists but incomplete or scoped
- **metadata only**: data model exists but no runtime behavior
- **readmodel only**: read-only projection, not executable
- **legacy path**: exists but not connected to target chain
- **missing**: does not exist in current code
- **target only**: defined as goal but no code artifact

---

## 4. One-shot Execution Is Historical Short Path

OwnerBoundedExecutionService is a valuable one-shot execution asset:

- It implements Owner authorization -> FinalGate -> Entry -> TP/SL ->
  Order -> Reconciliation -> Review.
- It is not the final target BRC architecture.
- It may remain as legacy / manual / safe trial path until the strategy
  runtime path is built.
- It does not generate signals or order candidates from a running strategy
  instance.
- It must not be deleted or behaviorally changed merely because the runtime
  path exists in shadow form.

---

## 5. Strategy Semantics

`docs/canon/STRATEGY_RUNTIME_GUIDE.md` is the durable guide for strategy
implementation, entry/protection/exit binding, payoff-specific exits, strategy
fact modeling, attempt/budget defaults, leverage boundaries, and near-term
candidate strategy coverage. This section summarizes the BRC target chain; the
guide governs implementation details when future tasks add or wire strategies.

- **EntryPolicy / ExitPolicy** should belong to strategy semantics, not be
  ad-hoc per-trade decisions.
- **ProtectionPolicy** (TP/SL) is minimum safety protection, not the whole
  exit strategy.
- **StrategyContractV2** (EntryPolicy / StopPolicy / TakeProfitPolicy /
  LifecycleExitPolicy / StrategySignalV2) is a candidate asset for future
  strategy semantic contracts.
- **SignalPipeline** is a candidate signal evaluation engine, not the final
  BRC runtime by itself.
- **BudgetedAutonomy** has multiple attempted boundary models, but current
  code is metadata_only / action_allowed=False.
- Runtime budget semantics should express trial capital: max_attempts,
  max_loss_budget / total_budget, budget_reserved, max_notional_per_attempt,
  max_active_positions, max_leverage, protection requirement, and review
  requirement. The purpose is bounded loss and no runaway, not avoiding every
  loss. `max_notional_per_attempt` controls exposure size; runtime
  `budget_reserved` should prefer concrete max-loss evidence
  (`risk_preview.max_loss_reference`) and use notional only as a conservative
  fallback when loss-budget evidence is absent.
- Leverage is a risk amplifier and margin-efficiency tool, not a
  loss-budget expansion mechanism. StrategyFamily / StrategyImplementation may
  propose leverage-sensitive risk semantics, stop/invalidation, expected risk
  shape, and protection requirements, but runtime risk and FinalGate own the
  final leverage decision. Leveraged candidates must satisfy all active runtime
  constraints at once: `max_loss_reference <= max_loss_per_attempt`,
  `intended_notional <= max_notional_per_attempt`, `proposed_leverage <=
  max_leverage`, margin usage remains within the runtime/account cap, the
  liquidation boundary remains beyond the hard stop with buffer, and protection
  is concrete and submit-ready. A strategy must never use leverage to enlarge
  allowed loss, bypass protection, self-authorize execution, or expand runtime
  budget.
- Runtime profile proposals may translate Owner risk-capital intent into
  reviewable boundary defaults, but a proposal is not a
  StrategyRuntimeInstance, not Owner/Codex confirmation, not live-profile
  enablement, and not execution authority. The current 30U proposal path is a
  non-executing input to later confirmation and runtime creation/promotion
  decisions.

Before controlled runtime execution, BRC must pass a Strategy Semantics /
Entry-Exit Policy Binding gate:

```text
StrategyFamilyVersion
  -> StrategyImplementation
  -> RequiredFacts
  -> StrategyEvaluationContext
  -> EntryPolicy
  -> ProtectionPolicy
  -> ExitPolicy
  -> OrderCandidate
```

Every StrategyImplementation must declare `required_facts`, `optional_facts`,
`freshness_requirement`, and `missing_fact_behavior`. Missing or stale facts
must resolve explicitly to `NO_ACTION`, `OBSERVE_ONLY`,
`BLOCK_MISSING_FACTS`, or `BLOCK_STALE_DATA`. The system must not infer missing
price, volume, funding, open-interest, account, position, or runtime facts to
allow execution.

Initial strategy-semantics reference candidates:

- `CPM-001`: long-only pullback-continuation price-action reference
  implementation candidate; not a proven-alpha production strategy.
- `BRF-001`: short-side bear-rally-failure price-action reference
  implementation candidate; not a proven-alpha production strategy. BRF uses a
  more conservative profile than CPM: lower leverage, smaller notional,
  mandatory hard stop, strict `max_active_positions`, and confirmed
  runtime-bounded automatic attempts. BRF should not require Owner confirmation
  for every entry once the runtime/profile boundaries are confirmed.
- `BTPC-001` / `LSR-001` / `RBR-001` / `VCB-001`: near-term candidate
  strategy semantics for bear-trend pullback continuation, liquidity-sweep
  reversal, range-boundary reversion, and volatility-compression breakout.
  They are not proven-alpha production strategies. They must preserve
  payoff-specific exits: trend/right-tail strategies use hard stop + TP1 +
  runner + trailing/invalidation/time-stop semantics, while range/mean-reversion
  strategies use hard stop + fixed RR or range targets + stricter time-stop
  semantics.
- `RMR-001`: range/chop regime classifier first, not the first trading
  strategy. RMR may downgrade CPM/BRF to observe-only or raise review
  requirements, but stale or missing RMR output must not act as execution
  authority. A pure closed-candle RMR classifier now exists for regime evidence
  only.
- `FCO-001`: funding / open-interest / crowding backlog family until
  deployment-backed fact coverage, freshness semantics, and Owner strategy
  semantics are confirmed. A Binance USD-M public/read-only derivative fact
  source now exists as infrastructure, but that does not promote FCO to a
  runtime strategy by itself.

Current local B0 implementation slice:

- `src/domain/strategy_semantics.py` defines StrategyImplementationBinding,
  StrategyEvaluationContext, RequiredFacts, fact freshness/missing behavior,
  ProtectionPolicy, ExitPolicy, initial CPM / BRF / RMR / FCO semantics, and
  right-tail review metrics.
- `src/application/strategy_evaluation_context_builder.py` builds
  StrategyEvaluationContext from read-only `StrategyFamilySignalInput`,
  `StrategyFamilySignalOutput`, and optional `StrategyRuntimeInstance`
  snapshots. It maps existing OHLCV, price-action, account, runtime-boundary,
  position-projection, funding, range, volatility, and crowding-related facts
  when explicit evidence exists, and marks missing facts explicitly instead of
  allowing strategy semantics to guess.
- `src/domain/rmr_regime_classifier.py` classifies explicit closed-candle
  windows into `TREND_UP`, `TREND_DOWN`, `CHOP`, `RANGE`, or `UNCERTAIN` and
  emits range / volatility / strategy-effect evidence with
  `not_execution_authority=true`, `hard_filter=false`, and no order/execution
  permissions. `StrategyEvaluationContextBuilder` can use that output for
  RMR-001 `range_structure`, `volatility_state`, and `market_state` facts.
- `src/domain/brf_price_action_evaluator.py` evaluates explicit closed-candle
  bear-rally-failure evidence for `BRF-001` / `BRF-001-v0`. It can emit
  observe-only short-side `StrategyFamilySignalOutput` evidence with
  `price_action_structure` and `short_squeeze_risk` facts so B0 semantics can
  distinguish reviewed short-side squeeze risk from missing facts. It is not an
  execution source and carries no sizing, leverage, venue, route, order, or
  execution instruction fields.
- `src/domain/reference_price_action_evaluators.py` evaluates explicit
  closed-candle OHLCV evidence for `BTPC-001`, `LSR-001`, `RBR-001`, and
  `VCB-001`. These are reference implementations for short-side continuation,
  liquidity-sweep reversal, range-boundary reversion, and volatility
  compression breakout. Their outputs may carry typed `candidate_semantics`
  snapshots but remain observe-only strategy-family signals: no sizing,
  leverage, venue, route, order, candidate creation, intent creation, or
  exchange calls. The Trading Console read-only observation surface now includes
  these four reference candidates with scheduler-level readiness metadata.
- `src/application/strategy_semantics_shadow_binding_service.py` fact-checks a
  SignalEvaluation against those semantics and can create only a shadow
  OrderCandidate through SignalEvaluationShadowService. It can also consume a
  `StrategyFamilySignalOutput`, persist a shadow SignalEvaluation, and then
  create a semantically bound shadow OrderCandidate when the output is
  `WOULD_ENTER`, the side is supported, RequiredFacts pass, and concrete
  protection is present. It also exposes a B0 orchestration method for a
  coherent `StrategyFamilySignalInput` + `StrategyFamilySignalOutput` pair:
  the service builds StrategyEvaluationContext from read-only facts and then
  applies the same shadow-only RequiredFacts gate.
- `src/application/strategy_runtime_fact_overlay_service.py` provides an
  optional non-executing read-only overlay before B0 planning. When injected, it
  replaces caller-provided account/position allow facts with trusted local or
  read-only sources, marks unavailable/stale facts through SignalDataQuality,
  and keeps missing trusted facts as B0 blockers instead of allowing manual
  active-position counts to pass.
- `src/domain/strategy_runtime_promotion_gate.py` provides a pure non-executing
  promotion gate for the remaining Owner/Codex decisions. It blocks promotion
  beyond shadow/preview if strategy semantics, runtime profile, fact sources,
  attempt/budget rules, BRF short-side conservative profile, or first-real-submit
  confirmations are missing. Its result also carries the strategy
  `runtime_confirmation_mode`, so downstream agents can distinguish
  runtime-bounded automatic attempts from legacy owner-confirm-each-entry
  operation. Lack of proven alpha is a warning limiting economic/autonomy
  admission, not a semantic blocker.
- `src/domain/experimental_runtime_profile_proposal.py` provides a pure
  non-executing profile proposal for the isolated 30U experimental capital
  shape. It can propose CPM/right-tail-long, BRF/conservative-short, and
  mean-reversion runtime boundaries with max attempts, loss budget, notional,
  leverage, margin, liquidation-buffer, protection, review, and fact-source
  confirmation keys. The Trading Console preview endpoint returns those
  proposal facts only; it does not create a runtime, confirm a profile, create
  an ExecutionIntent, create orders, or call exchange.
- `StrategyRuntimePromotionGateConfirmationRecord` can carry a structured
  `runtime_profile_proposal_snapshot` for the Owner/Codex-confirmed proposal
  evidence. The domain rejects blocked or mismatched proposal snapshots. This is
  audit evidence only; by itself it does not turn the proposal into runtime
  creation, submit authorization, or exchange authority.
- `StrategyRuntimeInstanceService.create_draft_from_profile_confirmation()` can
  create a shadow runtime draft only when TrialBinding, StrategyFamilyVersion,
  confirmation facts, and proposal snapshot all align. It copies the confirmed
  proposal boundary into `StrategyRuntimeInstance.boundary` while preserving
  `execution_enabled=false`, `shadow_mode=true`, and no order/exchange
  authority. The BRC Console exposes this as a narrow operator-auth runtime
  draft API from a promotion confirmation ID plus TrialBinding ID; the endpoint
  returns no-action guarantees and does not create candidates, intents, orders,
  OrderLifecycle calls, or exchange calls. The companion shadow lifecycle API
  can activate, pause, or revoke that runtime for shadow planning while keeping
  execution disabled.
- `src/application/strategy_runtime_promotion_gate_service.py` exposes that
  gate by `StrategyFamilyVersion` from the semantics catalog. It fails closed
  for unknown bindings and remains non-executing.
- `src/interfaces/api_trading_console.py` exposes a read-only
  `/strategy-runtime-promotion-gate` preview endpoint plus
  `/strategy-runtimes/{runtime_instance_id}/promotion-gate` for runtime-bound
  inspection. Both endpoints return blockers/warnings only; they do not write
  strategy signals, create OrderCandidates, create ExecutionIntents, or
  authorize execution.
- `src/application/runtime_strategy_signal_planning_service.py` bridges the B0
  signal-pair path into the existing non-executing runtime planning path:
  strategy signal pair -> semantically bound shadow OrderCandidate ->
  RuntimeExecutionPlan / RuntimeExecutionIntentDraft. It can apply the trusted
  runtime fact overlay before semantic binding when explicitly configured. It
  can replace caller-provided account/position facts and trusted
  funding/OI/crowding market facts with injected read-only overlays, and keeps
  RequiredFacts fail-closed when those trusted sources are missing or stale. It
  also reads StrategySemantics RequiredFacts before overlay application, so a
  strategy requiring funding, open-interest, or crowding cannot rely on
  caller-supplied market facts or a missing overlay. It does not create a
  recorded ExecutionIntent, local order, OrderLifecycle call, or exchange
  request.
- `src/interfaces/api_trading_console.py` has an internal service factory that
  wires the B0 runtime strategy signal planner with PG active-position facts
  and cached account facts. It can also opt into
  `BinanceUsdmDerivativeMarketFactSource` via
  `TRADING_CONSOLE_PUBLIC_MARKET_FACTS_ENABLED=true` for public/read-only
  funding, open-interest, and crowding facts. Trading Console also exposes an
  operator-auth non-executing shadow-plan POST that runs server-side evaluation
  before delegating to this planner; this is a shadow SignalEvaluation /
  OrderCandidate trigger only, not execution authority.
- `src/application/runtime_strategy_signal_scheduler_assembly.py` provides the
  scheduler-level readiness gate before automatic runtime signal binding. It
  previews whether a strategy signal pair has B0 semantics, a matching shadow
  runtime, trusted active-position/account fact sources, and
  strategy-required trusted market facts. Read-only strategy group observation
  and scheduled observation outputs now surface this readiness, but the gate
  does not call the runtime planner, create SignalEvaluation or OrderCandidate
  records, create ExecutionIntent records, create orders, call OrderLifecycle,
  or call exchange.
- `src/application/runtime_strategy_signal_scheduler_planning_service.py`
  provides the explicit non-executing handoff after scheduler readiness. It
  calls the shadow runtime planner only when readiness is
  `READY_FOR_NON_EXECUTING_PLANNER` and the caller explicitly sets
  `allow_shadow_candidate_creation=true`; otherwise it performs no planner
  call. This can create only shadow SignalEvaluation / OrderCandidate records
  through the B0 planner. The Trading Console endpoint
  `POST /api/trading-console/strategy-runtimes/{runtime_instance_id}/strategy-signal-shadow-plans`
  is the explicit operator-auth trigger for this non-executing handoff. It is
  not an ExecutionIntent adapter, not an OrderLifecycle adapter, and not
  execution authority.
- This is not proven-alpha approval, not execution authority, and not a real
  OrderLifecycle adapter. Scheduler-level fact-source readiness is now visible,
  and explicit non-executing planner handoff now exists, but deployment-backed
  triggering, BRF runtime-profile confirmation, deployment-backed FCO
  funding/OI/crowding coverage, and runtime promotion remain Owner/Codex-gated
  before promotion beyond shadow binding.

ProtectionPolicy and ExitPolicy must stay separate:

- ProtectionPolicy is the bounded-loss / no-runaway safety boundary.
- ExitPolicy is the strategy-owned profit-taking, runner, trailing,
  invalidation, time-stop, or lifecycle exit behavior.
- Generic fixed TP/SL must not silently replace strategy exit semantics or
  prematurely cap right-tail winners.

---

## 6. Review Semantics

Future Review should be able to trace the full semantic chain:

```text
StrategyFamilyVersion
TrialBinding
StrategyRuntimeInstance
SignalEvaluation
OrderCandidate
ExecutionIntent
Order
Review
```

Current Review Ledger does not yet carry the full strategy semantic chain
automatically from order/exchange facts. First-real-submit outcome accounting
can now record submit outcome review evidence and derive an attempt-outcome
policy when local order facts plus post-submit reconciliation evidence are
resolved, but broader lifecycle review
orchestration remains a known gap (see `docs/canon/TECH_DEBT_BASELINE.md`).

Future Review should distinguish trading PnL from Owner manual withdrawal,
capital injection, capital base reset, and strategy performance. Manual profit
withdrawal is a review/account-baseline fact, not a strategy loss or automatic
fund movement instruction.

Current local review/account-baseline implementation slice:

- `src/domain/owner_capital_adjustment.py` defines Owner-recorded manual
  withdrawal, manual profit extraction, capital injection, and capital base
  reset semantics. These records are external Owner facts only; they cannot
  create withdrawal, transfer, order, runtime-budget, strategy-PnL, risk-event,
  or exchange instructions.
- `src/application/owner_capital_adjustment_review_service.py` can classify
  read-only account-equity movement against realized trading PnL plus
  Owner-recorded capital adjustments. It marks unexplained account-equity
  deltas unresolved instead of guessing whether they are strategy losses or
  withdrawals.
- `src/infrastructure/pg_owner_capital_adjustment_repository.py` and migration
  `059` persist Owner capital adjustment records with hard no-withdrawal,
  no-transfer, no-order, no-exchange, no-runtime-budget, no-strategy-PnL, and
  no-risk-event constraints.
- `src/domain/owner_capital_baseline_snapshot.py`,
  `src/infrastructure/pg_owner_capital_baseline_snapshot_repository.py`, and
  migration `061` persist account-equity / capital-base baseline snapshots for
  review. These snapshots can supply previous account equity and starting
  capital base to Trading Console review when the Owner does not provide query
  inputs, but they cannot create withdrawal, transfer, order, exchange,
  runtime-budget, strategy-PnL, or risk-event instructions.
- `src/interfaces/api_brc_console.py` exposes narrow
  `/api/brc/owner-capital-adjustments` and
  `/api/brc/owner-capital-baseline-snapshots` record/list APIs for Owner
  external capital facts and review baseline facts only. They do not initiate
  withdrawal, transfer, order, exchange call, runtime budget mutation, strategy
  PnL mutation, or risk event.
- `src/application/readmodels/trading_console.py` and
  `trading-console/src/pages/ReviewState.tsx` surface Owner capital records and
  withdrawal-adjusted capital-base review in the Trading Console analysis page.
  If query inputs are absent, the readmodel can use the latest recorded baseline
  snapshot for previous account equity and starting capital base; missing
  current account-equity facts remain explicit instead of being inferred.
- `src/domain/right_tail_review.py` defines pure right-tail trade-path review
  metrics for explicit trade facts: MFE, MAE, R multiple, tail win size, small
  loss count, winner hold time, runner giveback / early cap, stop
  effectiveness, and attempt-continuation quality. It cannot create execution,
  order, exchange, runtime-budget, strategy-PnL, or withdrawal instructions.
- `src/application/readmodels/trading_console.py` exposes
  `review-state.right_tail_review` plus
  `/api/trading-console/right-tail-review`; `trading-console/src/pages/ReviewState.tsx`
  surfaces right-tail wins, small losses, max R, MFE, and single-tail-win
  coverage. The source policy is explicit
  `live_lifecycle_review.metadata.right_tail_trade_path` only; missing path
  facts stay `review_inputs_required` rather than inferred from orders or
  exchange.
- `src/domain/runtime_semantic_review_packet.py` builds non-executing closed
  trade semantic review packets from `BrcLiveLifecycleReviewRecord`. Packets
  preserve available runtime / trial / strategy-version / signal-evaluation /
  order-candidate / execution-intent IDs, mark incomplete semantic trace
  explicitly, and evaluate right-tail facts only from explicit lifecycle
  metadata. Trading Console right-tail review now includes
  `closed_trade_review_packets` and a packet summary.
- `Position` / PG `positions` now carry nullable runtime semantic IDs, and
  `PositionProjectionService.project_entry_fill()` propagates them from entry
  orders into local active-position projection without creating orders or
  changing exchange state. Trading Console position readmodels surface these
  IDs for active-position and closed-trade review traceability.
- `src/domain/runtime_live_position_monitor.py`,
  `src/application/runtime_live_position_monitor_service.py`, and
  `scripts/runtime_live_position_monitor.py` define a read-only runtime-native
  live-position monitor packet for the post-submit state. It joins
  StrategyRuntimeInstance boundary facts, local active position/open order
  facts, exchange position/stop-order facts, and reconciliation mismatches into
  a single Owner/Codex review surface. Missing TP is classified as a
  right-tail exit-policy warning when a hard stop is present, not as a runaway
  risk blocker; missing hard stop or severe reconciliation mismatch requires
  Owner action. The packet cannot submit, cancel, amend, close, mutate runtime
  state, call OrderLifecycle, withdraw, or transfer.
- `tests/unit/test_owner_capital_adjustment_review.py` verifies manual
  withdrawals and profit extraction do not become strategy losses or risk
  events, capital injection and capital-base reset are separate review facts,
  missing Owner records leave equity drops unresolved, and no withdrawal,
  transfer, order, or exchange instruction is created.
- `tests/unit/test_owner_capital_adjustment_repository.py` verifies PG
  persistence roundtrip preserves no-action flags.
  `tests/unit/test_owner_capital_baseline_snapshot_repository.py` verifies
  baseline snapshot persistence, BRC API record/list behavior, and no-action
  flags. Trading Console readmodel tests verify recorded Owner withdrawal can
  explain equity drop without strategy loss attribution and that latest
  baseline snapshots can supply missing previous-equity / starting-base review
  inputs.
- `tests/unit/test_right_tail_review.py` verifies long/short right-tail metrics,
  payoff asymmetry, explicit missing-input behavior, and no-action guarantees.
  Trading Console readmodel tests verify explicit lifecycle metadata can surface
  right-tail review without creating any action authority.

Future Review still needs automatic scheduled account-equity baseline capture,
fuller review-source orchestration, and richer source readers. The first
baseline snapshot repository/API/readmodel slice now exists, but automatic
capture from account facts remains future work. Order, review, and position
records now have local nullable semantic-ID support, but end-to-end source
orchestration from real order/position/exchange facts into review packets
remains incomplete. Closed-trade semantic packet generation now exists as a
non-executing first slice, but it remains explicit-metadata/readmodel driven
rather than automated from order/exchange facts. Review must not reduce strategy
performance to win rate, average return, or short-term PnL only.
