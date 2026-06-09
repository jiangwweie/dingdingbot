---
title: BRC_TARGET_SEMANTICS
status: CURRENT_CANON
authority: owner-semantic-audit + code-verification
last_verified: 2026-06-09
source_of_truth:
  - docs/canon/PROJECT_BASELINE_CURRENT.md
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
| StrategyRuntimeInstance | shadow implemented | Shadow governance model, PG table, repository, lifecycle events, and readmodel/API inspection exist; execution is disabled and shadow_mode is enforced | Running bounded strategy instance that generates evaluations |
| SignalEvaluation | shadow implemented | Shadow model, PG table, repository, service, and inspection API exist; no executable trigger | Per-instance signal evaluation within risk boundaries |
| OrderCandidate | shadow implemented | Shadow candidate model and PG table exist; candidate_executable=false and not_execution_intent=true are enforced | Executable order candidate from signal evaluation |
| FinalGate | implemented + runtime preview | FinalGate exists as hard one-shot execution gate; runtime-aware preview/dry-run exists for OrderCandidate inspection only | Pre-execution safety validation |
| ExecutionIntent | partially implemented | Execution permission system has 5 levels; source-native recorded intent audit, Owner submit authorization record, controlled-submit plan, submit-time FinalGate preflight, preflight-gated controlled-submit result, non-mutating attempt reservation preview, pending attempt reservation audit record, controlled runtime attempt mutation record, runtime-native protection plan preview/record, runtime OrderLifecycle handoff draft record, non-executing OrderLifecycle adapter preview gate, and non-executing submit adapter preview exist in the local working tree for `brc_runtime_order_candidate`; `recorded` is not submit-ready, not deployed, and the bridge does not create orders, submit orders, or call OrderLifecycle | Bounded execution intent from order candidate |
| OrderLifecycle | implemented | Order lifecycle service handles order placement and tracking | Order lifecycle management with strategy semantic IDs |
| Order / Position | implemented | Order and position management through exchange gateway | Live order and position tracking |
| Reconciliation | implemented | Reconciliation service exists | PG / exchange consistency verification |
| Review | partially implemented | Review Ledger design exists; limited production review data | Full review with strategy semantic traceability |

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
  mandatory hard stop, strict `max_active_positions`, and
  Owner-confirm-each-entry until explicitly upgraded.
- `RMR-001`: range/chop regime classifier first, not the first trading
  strategy. RMR may downgrade CPM/BRF to observe-only or raise review
  requirements, but stale or missing RMR output must not act as execution
  authority.
- `FCO-001`: funding / open-interest / crowding backlog family until data
  facts and freshness semantics are available.

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
  confirmations are missing. Lack of proven alpha is a warning limiting
  economic/autonomy admission, not a semantic blocker.
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
  does not create a recorded ExecutionIntent, local order, OrderLifecycle call,
  or exchange request.
- `src/interfaces/api_trading_console.py` has an internal service factory that
  wires the B0 runtime strategy signal planner with PG active-position facts
  and cached account facts. This is an application assembly point only; no
  public strategy-signal write endpoint is exposed by this slice.
- This is not proven-alpha approval, not execution authority, and not a real
  OrderLifecycle adapter. Live fact readers, BRF/RMR concrete evaluator
  details, FCO funding/OI/crowding data coverage, and runtime promotion remain
  Owner/Codex-gated before promotion beyond shadow binding.

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

Current Review Ledger does not carry strategy semantic IDs through the chain.
This is a known gap (see `docs/canon/TECH_DEBT_BASELINE.md`).

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
- `src/interfaces/api_brc_console.py` exposes narrow
  `/api/brc/owner-capital-adjustments` record/list APIs for Owner external
  capital facts only. They do not initiate withdrawal, transfer, order,
  exchange call, runtime budget mutation, strategy PnL mutation, or risk event.
- `src/application/readmodels/trading_console.py` and
  `trading-console/src/pages/ReviewState.tsx` surface Owner capital records and
  withdrawal-adjusted capital-base review in the Trading Console analysis page.
  Missing account-equity / capital-base inputs remain explicit instead of being
  inferred.
- `tests/unit/test_owner_capital_adjustment_review.py` verifies manual
  withdrawals and profit extraction do not become strategy losses or risk
  events, capital injection and capital-base reset are separate review facts,
  missing Owner records leave equity drops unresolved, and no withdrawal,
  transfer, order, or exchange instruction is created.
- `tests/unit/test_owner_capital_adjustment_repository.py` verifies PG
  persistence roundtrip preserves no-action flags. Trading Console readmodel
  tests verify recorded Owner withdrawal can explain equity drop without
  strategy loss attribution.

Future Review should emphasize right-tail asymmetric evaluation, including
MFE, MAE, R multiple, tail win size, small loss count, winner hold time, runner
giveback, whether the runner was capped too early, stop effectiveness, and
whether the attempt deserved continuation. Review must not reduce strategy
performance to win rate, average return, or short-term PnL only.
