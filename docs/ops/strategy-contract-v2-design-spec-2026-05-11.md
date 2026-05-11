# Strategy Contract v2 Design Spec

Last updated: 2026-05-11

## 0. Boundary

This is a design/spec document only.

- No code change is authorized.
- No config change is authorized.
- No runtime profile change is authorized.
- No Direction A implementation is authorized.
- No paper, testnet, live, small-live, or runtime activation is authorized.
- No strategy, risk, parameter, or order-sizing change is authorized.
- No backtest, adapter, parameter sweep, or experiment is authorized.
- No LLM automation is authorized.
- No Claude task card is created.

The purpose is to design a next strategy contract that can represent both current local pattern strategies and future lifecycle strategies such as Direction A, without contaminating runtime execution semantics.

## 1. Current Contract Problem

The current strategy interface is effectively:

```text
Strategy.detect(kline: KlineData) -> Optional[PatternResult]
```

This fits Pinbar / Engulfing because they are local pattern detectors. Their output can be summarized as:

- pattern name
- direction
- score
- diagnostic details

It does not fit Direction A because Direction A is not a one-bar pattern. It is a lifecycle strategy:

- entry depends on a 4h Donchian20 breakout over required history
- exit depends on an EMA60 close-break lifecycle rule after position entry
- it is long-only
- it does not naturally use fixed multi-TP
- it still needs an initial protective stop as capital protection / catastrophic-loss boundary

The current fallback in `SignalPipeline._build_execution_strategy()` can derive an `OrderStrategy` from a `SignalResult`, but `OrderStrategy` is an execution/order-chain contract, not a complete strategy semantics contract. It should not become the place where lifecycle-exit semantics are hidden.

## 2. Should `PatternResult` Be Retained?

**Yes.**

`PatternResult` should remain as the local output of `PatternStrategy`.

Recommended boundary:

| Model | Scope | Should contain |
|---|---|---|
| `PatternResult` | Local pattern-detection result | candle geometry, local pattern direction, local pattern score, diagnostic calculation details |
| `StrategySignal v2` | Strategy-level trade-intent candidate | strategy identity, symbol/timeframe, direction, entry/stop/TP/lifecycle policies, required history, score, metadata |
| `OrderStrategy` | Execution order-chain recipe | TP level structure, OCO behavior, trailing-stop mechanics, initial order-chain settings |

`PatternResult.details` must not become the carrier for formal trading semantics such as stop policy, lifecycle exit, permission state, strategy runtime identity, or execution profile selection. Details remain diagnostic, not contractual.

## 3. New Model: `StrategySignal v2`

Strategy Contract v2 should introduce a formal strategy signal model. The model is design-only here.

### Proposed fields

| Field | Required | Meaning |
|---|---:|---|
| `signal_id` | optional at strategy layer | Runtime or pipeline may assign this later. |
| `strategy_id` | yes | Stable strategy identity, e.g. `direction_a_donchian20_ema60_v0`. |
| `strategy_family` | recommended | `pattern`, `lifecycle`, `breakout`, `pullback`, etc. Useful for compatibility and reporting, not routing. |
| `symbol` | yes | Trade symbol, e.g. `ETH/USDT:USDT`. |
| `timeframe` | yes | Signal timeframe, e.g. `4h`. |
| `direction` | yes | `LONG`, `SHORT`, or future enum if needed. Direction A maps to `LONG` only. |
| `entry_policy` | yes | Structured entry semantics. |
| `stop_policy` | yes | Structured protective stop semantics. |
| `take_profit_policy` | yes | Structured TP policy, including no fixed TP. |
| `lifecycle_exit_policy` | optional but explicit | Structured lifecycle exit semantics if the strategy owns a non-TP lifecycle exit. |
| `required_history` | yes | Minimum bars/indicator warmup required for the signal to be valid. |
| `score` | optional | Strategy-local confidence/quality score, not cross-strategy capital weight. |
| `metadata` | yes, diagnostic only | Non-authoritative evidence, calculation snapshots, source references, and debug data. |
| `created_at_ms` | recommended | Signal creation time. |
| `source_context_id` | optional | Correlation to input market context / trace. |

### Policy submodels

`entry_policy` should be structured:

```text
EntryPolicy
  kind: market_next_open | market_on_close | limit | stop_market | signal_only
  trigger: donchian_breakout | pattern_confirmed | manual_replay | ...
  parameters: typed strategy parameters
  reference_price: optional Decimal
  valid_after_ms: optional
  valid_until_ms: optional
```

For Direction A:

```text
entry_policy.kind = market_next_open
entry_policy.trigger = donchian20_breakout
entry_policy.parameters = {lookback_bars: 20, breakout_side: "high"}
```

Timing clarification:

- `market_next_open` in this design means the next executable market opportunity after a confirmed closed-bar signal.
- It does not necessarily mean the system must submit exactly at the exchange's next kline open.
- More precise names for the intended semantics would be `market_after_confirmed_close` or `market_next_executable_opportunity`, but this document keeps the current field value as a local design label for now.
- If future runtime requires strict next-bar-open scheduling, execution scheduling must be designed separately.
- Backtest next-bar-open semantics must not be misread as a guarantee that live runtime will submit precisely on the next kline open.

`stop_policy` should be structured. `StopPriceHint` should not live in `details`.

```text
StopPolicy
  kind: fixed_price | prior_bar_low | donchian_invalidated | atr_multiple | none
  price: optional Decimal
  reference: optional structured reference
  required: bool
  notes: optional
```

`take_profit_policy` should support at least:

```text
TakeProfitPolicy
  kind: multi_tp_rr | no_fixed_tp | lifecycle_only
  levels: optional list[{rr, position_ratio}]
  oco_required: optional bool
```

`lifecycle_exit_policy` should be separate:

```text
LifecycleExitPolicy
  kind: none | ema_close_break | trailing_atr | time_stop | custom_named
  timeframe: string
  parameters: typed parameters
  applies_to: existing_position_only
  emits: ExitSignal
```

## 4. Should `detect(kline)` Become `detect(context: StrategyContext)`?

**Yes, for Strategy Contract v2.**

The v2 strategy entrypoint should be:

```text
detect(context: StrategyContext) -> Optional[StrategySignal]
```

For pattern compatibility, current `detect(kline)` can remain on `PatternStrategy`, and an adapter can wrap it later:

```text
PatternStrategyAdapter.detect(context):
  pattern = pattern_strategy.detect(context.current_kline, optional atr)
  if pattern is None: return None
  return pattern_to_strategy_signal(pattern, context)
```

The design should not force all existing pattern strategies to rewrite immediately.

## 5. `StrategyContext` Fields

`StrategyContext` should contain market and runtime observation context needed to evaluate a strategy signal, not execution authority.

### Should contain

| Field | Meaning |
|---|---|
| `current_kline` | The closed/evaluable kline for the strategy timeframe. |
| `history` | Bounded ordered OHLCV history for the same symbol/timeframe. |
| `indicators` | Precomputed indicator snapshots keyed by name/period/timeframe, e.g. `ema60`, `donchian20_high`. |
| `symbol` | Symbol being evaluated. |
| `timeframe` | Timeframe being evaluated. |
| `strategy_id` | Optional context hint for adapter/warmup lookup. |
| `market_clock` | Timestamp / close-time context for reproducible decisions. |
| `runtime_profile_ref` | Optional read-only reference or hash, not mutable profile contents. |
| `data_quality` | Optional status: missing bars, warmup incomplete, stale data. |
| `trace_context` | Optional correlation ID for Decision Trace. |

### Should not contain

`StrategyContext` must not contain:

- exchange credentials
- order-sizing authority
- mutable runtime profile object
- account balance as a direct sizing input unless a separate risk contract approves it
- permission state that the strategy can override
- GKS / human-gate controls
- execution gateway handles
- order repository handles
- live/paper activation flag used by the strategy to change rules
- LLM decision output

Runtime profile reference may be included only as immutable provenance, e.g. `runtime_profile_name`, `runtime_profile_hash`, or `strategy_config_version`. The strategy must not mutate or reinterpret profile state.

## 6. Compatibility Plan for Existing `PatternStrategy`

Pinbar / Engulfing should remain compatible through a two-layer bridge:

1. Keep current `PatternStrategy.detect(kline, ...) -> PatternResult`.
2. Introduce a later adapter that converts `PatternResult` into `StrategySignal v2`.
3. Keep `PatternResult.details` as diagnostics only.
4. Map existing pattern `score` to `StrategySignal.score`.
5. Derive default policy fields from existing execution defaults only in the adapter layer, not inside `PatternResult`.

Example mapping:

| Existing | v2 mapping |
|---|---|
| `PatternResult.strategy_name` | `strategy_id` or `strategy_family` with versioned adapter ID |
| `PatternResult.direction` | `StrategySignal.direction` |
| `PatternResult.score` | `StrategySignal.score` |
| `PatternResult.details` | `StrategySignal.metadata.pattern_details` |
| existing TP fields from `SignalResult.take_profit_levels` | `take_profit_policy.kind = multi_tp_rr` |
| current fixed SL hint | `stop_policy.kind = fixed_price` or adapter-specific default |

This preserves current Pinbar / Engulfing behavior while creating a proper path for non-pattern lifecycle strategies.

## 7. Direction A Mapping

Direction A should map to Strategy Contract v2 as a lifecycle strategy, not as a `PatternResult`.

```text
StrategySignal v2
  strategy_id: direction_a_donchian20_ema60_v0
  strategy_family: lifecycle_breakout
  symbol: ETH/USDT:USDT or BTC/USDT:USDT
  timeframe: 4h
  direction: LONG
  entry_policy:
    kind: market_next_open
    trigger: donchian20_breakout
    parameters:
      lookback_bars: 20
      breakout_side: high
      confirmation: closed_4h_bar
  stop_policy:
    kind: fixed_price or structure_reference
    required: true
    reference: frozen Direction A initial stop definition
  take_profit_policy:
    kind: lifecycle_only or no_fixed_tp
    levels: []
  lifecycle_exit_policy:
    kind: ema_close_break
    timeframe: 4h
    parameters:
      ema_period: 60
      exit_timing: next_open_after_close_break
    applies_to: existing_position_only
  required_history:
    bars:
      same_timeframe: at least 60 plus warmup margin
    indicators:
      donchian20: required
      ema60: required
  score:
    optional, non-sizing, non-permission
  metadata:
    donchian_high
    ema60
    breakout_bar_timestamp
    evidence_state
```

Protective SL is still needed. It is not the lifecycle exit. It is the initial capital-protection / catastrophic-loss boundary for a new position. Direction A's payoff engine remains EMA60 lifecycle exit, but the system should not open a position without a defined protective stop policy unless a separate Owner-approved risk exception exists.

Protective SL caveat:

- Protective SL is a capital-protection / catastrophic-loss boundary, not Direction A's payoff-engine exit.
- EMA60 close-break remains Direction A's lifecycle exit in this design.
- If the frozen historical Direction A baseline did not use an equivalent protective SL, then adding one is an execution-safety adaptation.
- This document must not claim that Direction A with an added protective SL is fully equivalent to the historical baseline.
- Protective SL distance, trigger semantics, exchange/order behavior, and whether it can cut off sparse payoff tails must be defined later in a separate Owner-approved risk/execution spec.
- This document only requires a clear protective stop policy before execution eligibility. It does not define the protective stop price, distance, trigger condition, or parameters.

## 8. Is `LifecycleStrategy` Needed?

**Yes, but only as a design target for future implementation.**

Direction A needs a strategy interface that separates entry detection from existing-position exit evaluation:

```text
LifecycleStrategy
  detect_entry(context: StrategyContext) -> Optional[StrategySignal]
  check_exit(context: PositionStrategyContext) -> Optional[ExitSignal]
```

`ExitSignal` should be structured:

```text
ExitSignal
  strategy_id
  position_id
  signal_id
  symbol
  direction
  exit_policy
  reason_code
  trigger_timeframe
  trigger_kline_timestamp
  desired_action: close_position | reduce_position
  quantity_policy: full_position | percent | fixed_qty
  metadata
```

For Direction A v0 design, `desired_action` should be `close_position` and `quantity_policy` should be `full_position`, but this is a future design statement only, not implementation authorization.

## 9. Who Should Call `check_exit()`?

### Option A: `ExitMonitor`

Dedicated component that receives closed klines, loads active positions by strategy, evaluates `LifecycleStrategy.check_exit()`, and emits `ExitSignal`.

Pros:

- Clean separation from order lifecycle updates.
- Natural place for strategy-owned lifecycle exit evaluation.
- Does not overload `DynamicRiskManager`.
- Easier to make report-only / no-order first.

Cons:

- New runtime loop / task lifecycle if implemented.
- Needs clear ordering with reconciliation and order watch.
- Needs active-position strategy metadata to be reliable.

### Option B: `DynamicRiskManager` extension

Extend current risk manager to evaluate lifecycle exits.

Pros:

- Existing backtest code already has risk-management concepts.
- May reuse some trailing/TP/SL logic.

Cons:

- Blurs strategy exit with risk protection.
- High risk of treating EMA60 lifecycle exit as a trailing stop variant.
- Makes future strategy-specific exits harder to reason about.

### Option C: `PositionLifecycleService`

New service responsible for position-level lifecycle decisions, separate from order-state lifecycle.

Pros:

- Name matches domain: position lifecycle, not order lifecycle.
- Can own active-position strategy metadata and exit decisions.
- Can emit trace before execution.

Cons:

- Larger design surface than GKS or StrategySignal.
- Could overlap with `OrderLifecycleService` unless boundaries are strict.

### Option D: `OrderLifecycleService`

Have existing order lifecycle service call `check_exit()`.

Pros:

- Already receives order updates and owns order state transitions.

Cons:

- Wrong responsibility. Order lifecycle reacts to exchange/order state; it should not decide strategy exits from market data.
- High conflict risk with TP/SL and protection-order semantics.

**Recommendation:** Design toward Option A or C. For first implementation later, prefer an `ExitMonitor` in report-only/no-order mode before any execution wiring. Do not place `check_exit()` inside `OrderLifecycleService`.

## 10. Avoiding Conflicts With TP/SL, DynamicRiskManager, and `OrderStrategy`

Lifecycle exits must be treated as a distinct exit family.

| Mechanism | Responsibility |
|---|---|
| Protective SL | Capital protection / catastrophic-loss boundary; can exist for lifecycle strategies. |
| Fixed TP / multi-TP | Order-chain profit-taking geometry for pattern/local-segment strategies. |
| DynamicRiskManager | Dynamic protection logic such as trailing stops, if enabled and explicitly configured. |
| Lifecycle exit | Strategy-owned invalidation/exit rule, e.g. EMA60 close-break. |
| OrderStrategy | Execution recipe for order-chain generation; should not be the sole carrier of strategy lifecycle semantics. |

Conflict prevention rules:

1. `take_profit_policy.kind = lifecycle_only` means no fixed TP orders should be generated from the strategy signal.
2. `lifecycle_exit_policy.kind != none` means exit evaluation must be handled by lifecycle-exit architecture, not by `PatternResult.details`.
3. `stop_policy.required = true` means initial protective SL remains required unless Owner separately approves an exception.
4. `OrderStrategy` may receive an execution projection derived from `StrategySignal`, but it must not erase the source lifecycle policy.
5. If both fixed TP and lifecycle exit are present in a future strategy, precedence and quantity interaction must be specified explicitly before implementation.

## 11. Stop Policy Design

`StopPriceHint` should become a structured `stop_policy`, not a free-form `details` value.

Rationale:

- stop price affects capital risk
- stop semantics must be auditable
- stop policy is needed before order creation
- stop policy must not be silently changed by strategy diagnostics

Minimum `stop_policy` should include:

| Field | Meaning |
|---|---|
| `kind` | `fixed_price`, `prior_bar_low`, `atr_multiple`, `structure_reference`, `none` |
| `price` | Optional explicit stop price. |
| `reference` | Structured reference when price is derived. |
| `required` | Whether execution must reject if stop is absent. |
| `risk_notes` | Optional human-readable caveat. |

For Direction A, `required=true`.

## 12. Take-Profit Policy Design

`take_profit_policy` must support:

| Kind | Meaning | Example |
|---|---|---|
| `multi_tp_rr` | Fixed RR-based multi-take-profit ladder. | Current Pinbar/Engulfing style. |
| `no_fixed_tp` | No strategy-defined fixed TP orders. | Strategy may still have protective SL. |
| `lifecycle_only` | Profit realization is governed by lifecycle exit, not fixed TP. | Direction A EMA60 close-break. |

`no_fixed_tp` and `lifecycle_only` are close but not identical:

- `no_fixed_tp` says no fixed TP orders are generated.
- `lifecycle_only` says the intended exit engine is the lifecycle exit policy.

Direction A should use `lifecycle_only`.

## 13. StrategyPermissionRegistry Design Note

StrategyPermissionRegistry is design-only here.

Recommended permission key:

```text
strategy_id + symbol + timeframe
```

Rationale:

- `strategy_id` alone is too broad if a strategy is acceptable on BTC 4h but not ETH 4h.
- `symbol` is needed because evidence and operational readiness differ by market.
- `timeframe` is needed because Direction A semantics are 4h-specific.
- Direction is usually implied by `strategy_id` for long-only strategies, but future two-sided strategies may need either separate strategy IDs or an optional `direction` dimension.

Do not bind permission to individual signal IDs by default. That would turn permission into per-trade manual approval and blur it with human gating.

Recommended future permission states:

| State | New entries |
|---|---|
| `DISABLED` | Denied. |
| `OBSERVE_ONLY` | No orders; signal/report only. |
| `PAPER_ALLOWED` | Paper only, if separately approved. |
| `TESTNET_ALLOWED` | Testnet only, if separately approved. |
| `LIVE_ALLOWED` | Live only, if separately approved. |

This design does not authorize any state implementation.

### StrategyPermissionRegistry vs OwnerGateState

`StrategyPermissionRegistry` and `OwnerGateState` are separate layers.

`StrategyPermissionRegistry` answers whether a specific `strategy_id + symbol + timeframe` is eligible in a mode, such as `OBSERVE_ONLY`, `PAPER_ALLOWED`, `TESTNET_ALLOWED`, or `LIVE_ALLOWED`.

`OwnerGateState` answers whether the Owner currently allows that eligible strategy to receive new entries, such as `ON_ALLOWED`, `WAIT`, `PAUSE_NEW_ENTRIES`, or `TURN_OFF`.

They are not the same permission state:

| StrategyPermissionRegistry | OwnerGateState | Result |
|---|---|---|
| `PAPER_ALLOWED` | `WAIT` | No new entries. The strategy may be eligible for paper, but Owner has not allowed entries now. |
| `LIVE_ALLOWED` | `ON_ALLOWED` | Eligible for execution only if GKS is off, the applicable human/owner gate passes, and CapitalProtection passes. |

Future implementations must not let an LLM automatically toggle either layer.

## 14. Gate Ordering

Recommended new-entry gate order:

```text
Strategy emits StrategySignal v2
  -> Global Kill Switch
  -> StrategyPermissionGate
  -> HumanGate / OwnerGate
  -> CapitalProtection.pre_order_check()
  -> OrderLifecycleService.create_order()
  -> ExchangeGateway.place_order()
```

Rationale:

1. GKS is system-wide emergency stop-all-new-entries and should short-circuit first.
2. StrategyPermissionGate checks whether this strategy/symbol/timeframe is allowed in the current mode.
3. HumanGate / OwnerGate is a manual permission layer for eligible candidates.
4. CapitalProtection is the final account/order risk gate before local order creation.

Existing per-symbol circuit breaker remains a system-level safety gate in the execution path. In the current runtime, it sits before GKS inside `ExecutionOrchestrator`; that ordering is acceptable because circuit breaker is symbol-specific recovery safety and GKS is global new-entry safety. A future unified permission pipeline can document the exact ordering as:

```text
CircuitBreaker / recovery block
  -> GKS
  -> StrategyPermissionGate
  -> HumanGate
  -> CapitalProtection
```

### Evaluation Permission vs Execution Permission

Strategy permission may need two future read points:

1. **Evaluation permission**: whether the strategy may run detection, generate observation signals, and produce reports.
2. **Execution permission**: whether a generated `StrategySignal v2` may enter the order path.

Minimum mode semantics:

| Permission state | Evaluation | Execution |
|---|---|---|
| `DISABLED` | Denied | Denied |
| `OBSERVE_ONLY` | Allowed for no-order observation/reporting | Denied |
| `PAPER_ALLOWED` | Allowed | Eligible only for paper mode, and still subject to OwnerGate, GKS, HumanGate, and CapitalProtection |
| `TESTNET_ALLOWED` | Allowed | Eligible only for testnet mode, and still subject to OwnerGate, GKS, HumanGate, and CapitalProtection |
| `LIVE_ALLOWED` | Allowed | Eligible only for live mode, and still subject to OwnerGate, GKS, HumanGate, and CapitalProtection |

Mode eligibility does not bypass any gate. This split allows no-order / observe-only workflows without accidentally routing a strategy signal into runtime order creation.

## 15. What Is Designable Now vs Slow-Path Later

### Can be designed now

- StrategySignal v2 schema.
- StrategyContext schema.
- PatternStrategy compatibility adapter design.
- Direction A mapping.
- LifecycleStrategy interface concept.
- ExitSignal model concept.
- Lifecycle exit architecture options.
- Permission state keying model.
- Gate ordering.
- Risk boundary and non-goals.

### Becomes runtime/capital-risk slow path once implementation starts

- Adding `StrategySignal v2` to domain/runtime code.
- Changing `SignalPipeline` to consume `StrategySignal`.
- Wiring `StrategyPermissionGate`.
- Persisting permission state.
- Implementing `LifecycleStrategy`.
- Implementing `ExitMonitor` or `PositionLifecycleService`.
- Generating exit orders from `ExitSignal`.
- Changing `OrderStrategy` derivation.
- Allowing `lifecycle_only` to suppress TP order creation.
- Introducing Direction A to runtime.
- Any paper/testnet/live mode activation.
- Any risk/profile/order-sizing change.

All slow-path items require separate Owner approval, focused branch, task card, tests, and review.

## 16. Risk / Execution Boundary

Strategy Contract v2 must preserve these boundaries:

- Strategy decides candidate semantics, not permission to trade.
- Permission gates decide whether new entries are allowed, not how to size or exit.
- CapitalProtection decides account/order risk admissibility.
- OrderLifecycleService manages order state, not strategy market logic.
- Lifecycle exit evaluation must not cancel/replace existing TP/SL unless a later execution design explicitly authorizes and tests that behavior.
- Research evidence remains separate from runtime activation.

Direction A remains non-runtime until separately approved. This spec only makes it representable.

## 17. Risk Triage

| Item | Severity | Treatment |
|---|---|---|
| Current `PatternResult` cannot express lifecycle strategies cleanly | HIGH | Introduce `StrategySignal v2`; keep `PatternResult` local. |
| Formal trading semantics in `PatternResult.details` | BLOCKER | Explicitly prohibited. Details are diagnostics only. |
| Lifecycle exit hidden as an `OrderStrategy` flag | HIGH | Separate `lifecycle_exit_policy` and future `LifecycleStrategy.check_exit()`. |
| Direction A mapping is design-only | SUFFICIENT | No runtime implementation or activation. |
| Stop semantics affect capital risk | HIGH | Use structured `stop_policy`; no free-form stop hints. |
| Pinbar / Engulfing compatibility | MODERATE | Use adapter path; no immediate rewrite. |
| `ExitMonitor` implementation would create runtime task surface | HIGH | Future slow-path task only, report-only first if authorized. |
| StrategyPermissionRegistry granularity | MODERATE | Recommend `strategy_id + symbol + timeframe`; Owner can adjust before implementation. |
| Gate ordering across GKS / strategy permission / human gate / risk | SUFFICIENT | Proposed ordering is coherent; implementation later requires tests. |
| LLM automation / strategy router temptation | BLOCKER if introduced | Explicitly out of scope. |
| Paper/testnet/live implication | BLOCKER if implied | This spec does not authorize activation. |

No BLOCKER exists for this document as a design artifact. BLOCKER applies if a future implementation attempts to smuggle execution semantics into `details`, runtime activation, router behavior, or LLM automation.

## 18. Minimum Next Step

1. Owner reviews Strategy Contract v2 proposal.
2. Owner confirms whether `StrategySignal v2` is the right top-level signal contract.
3. Owner confirms the compatibility plan: keep `PatternResult`, add adapter later.
4. Owner confirms Direction A mapping: `lifecycle_only` TP policy plus EMA60 lifecycle exit and required protective SL.
5. Owner chooses preferred lifecycle-exit architecture direction: `ExitMonitor` vs `PositionLifecycleService`.
6. Owner confirms permission key granularity: `strategy_id + symbol + timeframe`.
7. If accepted, promote this design to an ADR or implementation planning note later. No implementation task is created now.

## 19. What Not To Do

- Do not implement StrategySignal v2.
- Do not modify `src`.
- Do not modify configs or runtime profiles.
- Do not implement Direction A.
- Do not implement lifecycle exits.
- Do not add an ExitMonitor runtime task.
- Do not modify `OrderStrategy` behavior.
- Do not create a StrategyPermissionRegistry implementation.
- Do not generate a Claude task card.
- Do not run backtests, adapters, or sweeps.
- Do not design automatic strategy routing.
- Do not design LLM automatic switching.
- Do not treat this design as paper/testnet/live approval.
