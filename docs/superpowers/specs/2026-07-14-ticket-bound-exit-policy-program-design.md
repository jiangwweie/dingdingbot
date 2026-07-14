# Ticket-Bound Exit Policy Program Design

Status: **proposed for Owner review; no implementation authorized by this document**

Date: **2026-07-14**

Program: **one bounded lifecycle task with three independently releasable units**

Supersedes for future implementation:
`docs/superpowers/specs/2026-07-14-sor-runner-recovery-and-structural-trailing-design.md`.
The predecessor remains historical design provenance. Its `3 bars / ATR(14) /
0.5 ATR` values are reclassified here as replay candidates, not production
defaults.

## Executive Decision

The selected design is a **Ticket-frozen, versioned Exit Policy Core** built on
the existing ticket-bound lifecycle, reconciliation, settlement, and durable
exchange-command authority.

The program contains three release units:

| Release unit | Purpose | Live behavior after release | Owner decision gate |
| --- | --- | --- | --- |
| **Release A — Lifecycle and TP1 Execution Safety Repair** | Restore runner maintenance, deterministic active-protection selection, external-close recovery, and TP1 passive-limit correctness | Existing strategy meaning is unchanged; TP1 cannot silently become market; no new trailing policy | **None** inside the already approved scope |
| **Release B — Versioned Exit Policy Core** | Add immutable Ticket policy snapshots, typed evaluation, PG current projection, fact cadence, and generation-safe mutation | Capability is deployed **disabled** for new strategy exits; legacy Tickets are not reinterpreted | **None** while capability remains disabled |
| **Release C — Strategy Exit Activation** | Replay, select, version, and activate one exit policy per Event Spec for future Tickets | One approved Event Spec at a time gains structural trailing, invalidation, or time-stop behavior | **Required** for exact parameter versions and production activation |

The design does **not** create a second scheduler, a second order ledger, a
second exchange-write authority, a fixed TP2 for every strategy, or a hidden
fallback from limit TP1 to market execution.

## Owner Decisions Already Captured

The following are treated as explicit **Owner policy** and are not returned for
another confirmation inside Release A or Release B:

1. The current server release may continue admitting new entries until the
   ordinary maintenance/deploy window; no forced intervention is introduced by
   this design.
2. A currently open Ticket may be manually closed and then recovered through
   strict `EXTERNAL_CLOSE` attribution before deployment.
3. Future right-tail strategies should use **TP1 plus a moving protective
   runner**, not an automatic universal fixed TP2.
4. A runner stop is monotonic: long stops only move upward; short stops only
   move downward.
5. No strategy parameter, notional, leverage, symbol, side, runtime profile, or
   exchange permission is silently expanded.
6. **TP1 is a reduce-position limit order, never a market order.** The system
   may not silently downgrade it to market to force a fill.

## Verified Objective Facts

### Current TP1 behavior

The tracked branch currently constructs TP1 in
`src/application/action_time/protected_submit_attempt.py` with:

- `gateway_order_type = "limit"`;
- a concrete target `price`;
- `reduce_only = true` at the normalized command boundary;
- deterministic Ticket/client-order identity.

The current gateway in `src/infrastructure/exchange_gateway.py` does **not**
carry explicit `time_in_force`, `post_only`, or an execution-style capability
through the ticket-bound command. Therefore the current order is an ordinary
limit order, not a maker-guaranteed order.

A marketable limit order can execute immediately as taker. Consequently, an
observed taker fee does not by itself prove that the submitted order type was
`MARKET`; the production evidence must include the exact submitted type,
time-in-force, maker flag, exchange fill liquidity role, and fee.

### Current runner behavior

The current strategy catalog declares the five active StrategyGroups as
right-tail runner strategies with **TP1 at 1R for 50%** and a lifecycle exit
kind named `TRAILING_ATR`. The active Ticket lifecycle, however, implements only:

```text
entry
-> exchange-native SL + TP1
-> TP1 fill
-> one fixed RUNNER_SL based on the original stop
-> terminal fill or external close
```

The versioned catalog name is not consumed as an executable post-entry exit
policy. Strategy-specific invalidation logic in the signal evaluators is entry
or candidate logic, not continuous position-management authority.

### Current scheduler defect

`src/application/action_time/lifecycle_maintenance_scheduler.py` omits
`runner_protected` from both its maintainable and snapshot status sets. A
Ticket can transition to `runner_protected` and declare
`continue_runner_monitoring`, but the timer no longer selects it.

### Current order-selection defect

Several lifecycle services independently select the first row matching a role.
That is safe only while each role has one historical row. It becomes ambiguous
when runner stops are replaced across generations.

### Current authority boundaries

The existing system already has:

- one ticket-bound lifecycle run;
- one exit-protection set and order ledger;
- one durable exchange-command table with deterministic command generations;
- exact exchange snapshot, reconciliation, finalization, settlement, and Live
  Outcome paths;
- a 30-second production lifecycle maintenance timer;
- PG-backed current runtime truth.

These are the authorities to extend. The Exit Policy Core must not duplicate
them.

## Analysis Based On The Facts

### Root problem class

The observed SOR runner defect is not only a missing status constant. It exposes
three shared invariant gaps:

1. **Maintenance continuity:** every non-terminal lifecycle state must have an
   explicit maintenance owner and cadence.
2. **Protection generation identity:** a role name such as `RUNNER_SL` is not a
   sufficient identity after replacement begins.
3. **Strategy-to-lifecycle binding:** post-entry exit semantics must be frozen
   into each Ticket and evaluated independently from current registry defaults.

### TP1 fee problem class

The TP1 requirement contains two different guarantees:

1. **Order-type guarantee:** TP1 must be `LIMIT`, never `MARKET`.
2. **Liquidity-role guarantee:** fee-sensitive TP1 should rest passively and
   should not silently cross the book as taker.

An ordinary limit order satisfies the first guarantee but not the second. The
selected architecture therefore models TP1 execution style explicitly and
records actual liquidity-role evidence.

## Alternatives Considered

| Alternative | Short-term benefit | Structural cost | Decision |
| --- | --- | --- | --- |
| **SOR-only trailing patch** | Smallest diff around the observed trade | Leaves five strategies without versioned exit semantics; preserves duplicate role lookup | **Rejected** |
| **Global trailing toggle** | One feature flag appears reusable | Hides strategy/event/side differences and can reinterpret open Tickets | **Rejected** |
| **Separate trailing daemon and order table** | Operational isolation | Creates conflicting schedulers, ledgers, and exchange-write authorities | **Rejected** |
| **Ticket-frozen Exit Policy Core on the existing lifecycle** | Shared invariants, versioned behavior, future asset-class support | Requires schema and full lifecycle certification | **Selected** |

## Program Boundaries

### In scope

1. Runner lifecycle maintenance and external-close closure.
2. Exact active exit-protection generation selection.
3. TP1 passive-limit execution contract and maker/taker evidence.
4. Typed, immutable Exit Policy snapshots attached to future Tickets.
5. Closed-market-fact evaluation, structural trailing, invalidation, and time
   stops through the existing lifecycle.
6. Replay and activation design for all active Event Specs.
7. Production cadence, performance, notification, deploy, rollback, and
   certification rules.

### Out of scope

1. Entry signal or detector changes.
2. Capital allocation, notional, leverage, symbol, side, or account expansion.
3. A generic portfolio optimizer.
4. Tick-by-tick local synthetic stops without exchange-native protection.
5. Automated emergency market close policy.
6. Historical Ticket reinterpretation.
7. New runtime JSON/Markdown readers or recurring report writers.

## Unified Authority Flow

```text
StrategyGroup + Event Spec + side
-> current versioned Exit Policy in PG
-> immutable ExitPolicySnapshot frozen into a newly created Ticket
-> entry + exchange-native SL + passive TP1 through FinalGate/Operation Layer
-> existing ticket-bound lifecycle and reconciliation
-> TP1 fill
-> exchange-native RUNNER_SL
-> due closed-market-fact snapshot
-> pure Exit Policy evaluator
-> no-op / runner-stop replacement / runner close
-> existing durable exchange command authority
-> exact exchange reconciliation
-> settlement / Live Outcome / Review
```

No policy evaluation may directly call the exchange. It returns a typed
decision. Only the existing application lifecycle service may prepare an
exchange command, and only the official gateway executor may dispatch it.

## Domain Model

### Exit policy families

The new pure domain module is
`src/domain/ticket_exit_policy.py`. It uses frozen Pydantic models,
`decimal.Decimal`, discriminated unions, and no I/O imports.

| Policy family | TP behavior | Residual-position behavior | Intended use |
| --- | --- | --- | --- |
| **RIGHT_TAIL_RUNNER** | One or more versioned partial TP legs; current baseline is TP1 1R/50% | Structural/volatility trail, strategy invalidation, optional time stop; no fixed profit cap by default | CPM, MPG, MI, SOR, BRF2 |
| **FIXED_TARGETS** | Versioned TP1/TP2/etc. legs | Terminal after last target or explicit stop/time rule | Future mean-reversion/Event Specs |
| **LIFECYCLE_ONLY** | Optional or absent | Initial protection and explicit lifecycle closure only | Compatibility or strategies without runner semantics |

### Required typed models

```python
class TpExecutionStyle(str, Enum):
    LIMIT_GTC = "limit_gtc"
    PASSIVE_LIMIT_GTX = "passive_limit_gtx"


class TicketTakeProfitLeg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    role: Literal["TP1", "TP2", "TP3", "TP4", "TP5"]
    reward_multiple: Decimal
    quantity_fraction: Decimal
    execution_style: TpExecutionStyle
    market_fallback_allowed: Literal[False] = False


class StructuralAtrRunnerRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["structural_atr"]
    timeframe: str
    structure_rule: str
    structure_window_bars: int
    atr_period: int
    atr_buffer_multiple: Decimal
    minimum_improvement_ticks: int


class TicketExitPolicySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    exit_policy_id: str
    exit_policy_version: str
    strategy_group_id: str
    strategy_version: str
    event_spec_id: str
    event_spec_version: str
    side: Literal["long", "short"]
    policy_family: str
    take_profit_legs: tuple[TicketTakeProfitLeg, ...]
    invalidation_rules: tuple[object, ...]
    time_stop_rule: object | None
    runner_rule: object | None
    payload_hash: str
```

The production implementation replaces the illustrative `object` types with
named discriminated models. Unstructured parameter dictionaries are forbidden.

### Evaluation input and output

```python
class ExitDecisionKind(str, Enum):
    NOOP = "noop"
    MOVE_RUNNER_STOP = "move_runner_stop"
    CLOSE_RUNNER = "close_runner"
    BLOCKED = "blocked"


class ExitEvaluationInput(BaseModel):
    policy: TicketExitPolicySnapshot
    ticket_id: str
    exchange_instrument_id: str
    side: Literal["long", "short"]
    position_qty: Decimal
    current_runner_stop: Decimal | None
    active_runner_generation: int | None
    market_fact: object
    evaluated_watermark_ms: int


class ExitDecision(BaseModel):
    kind: ExitDecisionKind
    reason_code: str
    source_watermark_ms: int
    proposed_stop: Decimal | None = None
    close_qty: Decimal | None = None
    blockers: tuple[str, ...] = ()
```

### Evaluation priority

The pure evaluator applies this order:

1. If the lifecycle/exchange position is already terminal, the existing
   lifecycle owns finalization; the policy evaluator returns `NOOP`.
2. If the position is open but exact protection identity is missing or
   contradictory, return `BLOCKED`; never trade through ambiguity.
3. If a versioned strategy invalidation rule is satisfied, return
   `CLOSE_RUNNER`.
4. If a versioned time-stop rule is satisfied, return `CLOSE_RUNNER`.
5. If a structural/volatility candidate improves the stop monotonically by at
   least the versioned minimum tick distance, return `MOVE_RUNNER_STOP`.
6. Otherwise return `NOOP`.

`CLOSE_RUNNER` is a strategy exit decision and must still use the existing
durable reduce-position command path. It is not an emergency bypass.

## TP1 Passive-Limit Contract

### Mandatory invariants

Every TP1 command must prove:

```text
order_role = TP1
order_type = LIMIT
time_in_force = GTC or GTX according to frozen execution style
market_fallback_allowed = false
reduce_intent = reduce_position
exact position bucket is bound
quantity is step-aligned and does not exceed the remaining position
price is tick-aligned and derived from the frozen Ticket policy
```

The baseline execution style for future right-tail policy candidates is
**PASSIVE_LIMIT_GTX**. At the Binance adapter boundary it maps to the
venue-supported post-only time-in-force. A venue without a certified passive
limit capability blocks that policy; it must not silently use ordinary limit
or market.

### Marketable-at-submit behavior

If TP1 is marketable when the exchange evaluates a post-only request:

1. An authoritative post-only rejection is recorded against the durable
   command.
2. The current SL remains exchange-native and unchanged.
3. The system obtains a bounded fresh best-bid/best-ask fact.
4. It prepares the next deterministic TP1 command generation at a tick-aligned
   passive price that is no worse than the strategy target in the profit
   direction.
5. It retries on the maintenance cadence with a bounded attempt count per tick.
6. It never falls back to `MARKET`.

For a long position, the replacement sell price must remain at or above both
the policy target and the first non-marketable price. For a short position, the
replacement buy price must remain at or below both. If that cannot be proved,
the state is `tp1_passive_placement_pending` while the full position remains
protected by SL.

### Fee and liquidity truth

The exchange snapshot and fill projection add:

- normalized `liquidity_role = maker | taker | unknown`;
- exact fee amount and fee asset;
- submitted order type and time-in-force;
- target price, submitted price, and realized fill price;
- a lifecycle defect when `PASSIVE_LIMIT_GTX` fills as taker or when exchange
  evidence cannot reconcile the submitted execution style.

The Live Outcome and Review surfaces report actual fee truth. They do not infer
maker status only from the word `LIMIT`.

## PostgreSQL Data Model

### `brc_strategy_exit_policies`

This is the versioned strategy-policy authority.

| Column group | Required fields | Rule |
| --- | --- | --- |
| Identity | `exit_policy_id`, `exit_policy_version` | Immutable composite identity |
| Strategy binding | `strategy_group_id`, `strategy_version`, `event_spec_id`, `event_spec_version`, `side` | No symbol or venue hidden constants |
| Semantics | `policy_family`, typed `policy_payload`, `payload_hash` | Payload validates through the domain model before persistence |
| Governance | `status`, `approved_by`, `approved_at_ms`, `created_at_ms` | `draft`, `certified_disabled`, `current`, `retired` |

Only one `current` policy may exist per exact
`StrategyGroup + strategy version + Event Spec + side`. A policy becoming
current affects only Tickets created afterward.

### Ticket extension

`brc_action_time_tickets` gains:

- `exit_policy_id`;
- `exit_policy_version`;
- `exit_policy_snapshot`;
- `exit_policy_hash`.

The exit-policy identity and hash enter both the Ticket identity hash and
`created_under_versions_hash`. A newly created Ticket cannot proceed when its
Event Spec requires a policy and no exact current policy exists.

Historical rows are backfilled only with explicit `legacy_unbound` metadata.
No historical strategy meaning is synthesized from the latest registry.

### `brc_ticket_exit_policy_current`

This is the single PG current projection owned by the new application service.

| Field group | Fields | Purpose |
| --- | --- | --- |
| Identity | `ticket_id`, `exit_protection_set_id`, policy identity/hash | Exact frozen authority |
| Evaluation | `state`, `last_evaluated_watermark_ms`, `next_evaluation_not_before_ms`, `last_decision_kind`, `last_reason_code` | One evaluation per eligible market watermark |
| Runner | `active_runner_order_id`, `active_runner_generation`, `active_runner_stop` | Current exact protection |
| Replacement | `pending_runner_order_id`, `pending_generation`, `replaced_runner_order_id` | Crash-recoverable submit-new-before-cancel-old sequence |
| Status | `first_blocker`, `updated_at_ms` | Product/readmodel projection |

### Exit-protection order generation

`brc_ticket_bound_exit_protection_orders` gains a non-null `generation` column,
backfilled as `1`. The active selection index covers:

```text
exit_protection_set_id + role + generation + status
```

The existing `replaces_exit_protection_order_id` remains the lineage link.
There is no new order ledger.

### Lifecycle events

The existing lifecycle event ledger adds typed events such as:

- `exit_policy_bound`;
- `tp1_passive_placement_pending`;
- `tp1_passive_order_confirmed`;
- `exit_policy_evaluated`;
- `runner_replacement_prepared`;
- `runner_replacement_confirmed`;
- `runner_prior_generation_cancelled`;
- `strategy_exit_prepared`.

No second audit-event table is introduced.

## Active Protection Resolver

All lifecycle modules use one shared resolver. The resolver receives all rows
for one exact exit-protection set and returns one of:

| Result | Meaning | Required action |
| --- | --- | --- |
| **ACTIVE_ONE** | Exactly one confirmed active generation | Continue reconciliation/evaluation |
| **REPLACEMENT_IN_PROGRESS** | New generation confirmed while prior exact generation is cancel-pending within grace | Continue exact cancellation and reconciliation |
| **MISSING** | Position open but no active runner | Hard safety stop; do not evaluate a new trail until reconciled |
| **CONTRADICTORY** | Multiple unexplained active generations or broken lineage | Hard safety stop and exact reconciliation |
| **TERMINAL** | Position flat or lifecycle terminal | Finalizer owns closure |

The resolver replaces duplicated first-role selection in the runner adjuster,
runner command builder, lifecycle maintenance service, protection reconciler,
and Live Outcome ledger.

## Runner Replacement Protocol

The selected sequence is **submit new, confirm new, cancel old**:

```text
pure evaluator proposes improved stop
-> persist decision and next generation
-> prepare deterministic place_order command
-> dispatch through existing exchange-command executor
-> prove exact new exchange order identity and open status
-> mark replacement grace state
-> prepare exact cancel_order command for prior exchange_order_id
-> prove cancel effect or prior terminal fill
-> select one active generation
-> publish current projection
```

The runner remains protected during replacement. A temporary overlap is
allowed only for the exact linked generations and bounded grace window. A
network timeout creates `UNKNOWN_OUTCOME`; no new generation or cancellation is
issued until client-order-id reconciliation resolves it.

## Closed-Market-Fact Service

### Fact boundary

`src/application/action_time/ticket_exit_market_fact_service.py` uses an
injected read-only `ClosedCandleSource`. The current Binance public-kline
adapter can implement the first venue binding; the core model remains based on
`exchange_instrument_id`, asset class, venue, session, and policy timeframe.

The service persists a typed fact snapshot to the existing
`brc_runtime_fact_snapshots` surface with:

- `fact_surface = ticket_exit_market`;
- Ticket, policy, Event Spec, instrument, side, venue, and timeframe identity;
- exact final closed-candle watermark;
- candle/ATR/structure inputs and source timestamps;
- `observed_at_ms`, `valid_until_ms`, and payload hash.

Generated JSON/Markdown is not a runtime source.

### Cadence and performance

The 30-second lifecycle timer remains the only scheduler. It first reads
`next_evaluation_not_before_ms` from PG.

| Lifecycle state | PG work per tick | Market/API work | File output |
| --- | --- | --- | --- |
| No due runner | One bounded selector/current-projection query | **None** | **Zero** |
| Healthy runner before next candle close | Current projection/reconciliation query | Existing signed lifecycle snapshot only when already required | **Zero** |
| First tick after a policy candle closes | Claim evaluation watermark, then persist fact/decision | One timeout-bounded public candle fetch per exact instrument/timeframe batch | **Zero** |
| Replacement pending | Existing command reconciliation queries | Exact place/cancel lookup only | **Zero** |

Public market calls occur outside long PG transactions, use explicit timeouts,
and are coalesced for Tickets sharing the same exact instrument/timeframe
watermark. Production no-signal/no-due ticks write no JSON/Markdown files.

## Release A — Lifecycle And TP1 Execution Safety Repair

### A1. Scheduler continuity

Add `runner_protected` to both scheduler status sets and prove:

- an open runner is selected;
- signed read-only exchange facts are collected;
- a healthy runner creates no exchange command;
- terminal fill, missing protection, and external close continue into the
  existing lifecycle actions.

### A2. Shared active-protection resolver

Introduce the resolver and replace all arbitrary first-role lookups. Release A
supports the current single-generation runner plus exact historical rows. It
fails closed on ambiguous active generations.

### A3. TP1 limit and maker-preservation boundary

Release A makes the current intended behavior explicit:

1. Extend the normalized ticket-bound command with typed `time_in_force`,
   `post_only`, and `market_fallback_allowed=false` fields.
2. Require every TP1 to use `LIMIT`.
3. Map the selected passive style to the venue adapter; no business layer emits
   raw Binance keys.
4. Add authoritative negative tests proving TP1 cannot be `MARKET`, cannot omit
   price, cannot expand quantity, and cannot silently downgrade after a
   post-only rejection.
5. Capture normalized liquidity role and actual fee from exchange fills.

Release A does not alter the current TP1 target formula or fraction. It repairs
execution semantics and evidence only.

### A4. Manual close recovery

After an Owner manual reduce-only close, the existing strict attribution path
must prove account, venue, instrument, position bucket, side, quantity, time,
exchange order identity, and unique Ticket ownership. It then performs exact
orphan cleanup, terminal lifecycle closure, budget settlement, Live Outcome,
and notification.

Symbol-wide cancellation and heuristic ownership are forbidden.

### A5. Release gate

Release A may deploy only when:

```text
exchange position is flat
and no residual PG-linked conditional order remains
and current lifecycle is terminal
and active_real_lifecycles = 0
and ordinary deploy quiescence passes
```

There is no active-lifecycle bypass.

## Release B — Versioned Exit Policy Core

### B1. Capability state

Release B deploys schema, typed domain logic, projection ownership, and
production-shaped certification with `ticket_exit_policy_v1` in
**certified_disabled** state.

No current strategy policy is activated. New and historical Tickets continue
to use their explicitly bound prior behavior until Release C creates a future
policy version.

### B2. Ticket binding

The Ticket materializer queries the exact current policy for its Event Spec,
validates it, hashes it, and stores the immutable snapshot. If a strategy
version declares that exit policy v1 is required but no exact policy exists,
Ticket creation fails closed with a typed policy blocker.

### B3. Evaluation and mutation

The scheduler delegates to the exit-policy application service only when:

- capability is enabled for the exact policy version;
- lifecycle is runner-eligible;
- protection resolver is non-contradictory;
- the policy watermark is due;
- the market fact is closed, fresh, and exact-scope.

The service evaluates purely and prepares commands through the existing durable
exchange-command authority. It does not dispatch directly.

### B4. Production-shaped matrix

Certification covers all six active Event Specs, both directions where
applicable, long/short monotonicity, missing/duplicate protection, stale facts,
unknown outcomes, partial fills, restart at every replacement boundary, manual
close, and fee/liquidity evidence.

No privileged fixture may grant live-submit authority.

## Release C — Strategy Exit Activation

### Research boundary

Strategy replay implementation belongs in a clean isolated worktree of:

```text
/Users/jiangwei/Documents/final-strategy-research
```

Research output is evidence for Owner policy selection. It is never read by the
production runtime. Accepted policy values are re-entered as typed PG policy
versions in the main repository after Owner approval.

### Candidate semantics by StrategyGroup

The following are **research candidates**, not approved production facts:

| StrategyGroup / Event Spec | Direction and timeframe | Candidate primary exit | Candidate runner | Parameter decision needed after replay |
| --- | --- | --- | --- | --- |
| **CPM-RO-001 / CPM-LONG** | Long, closed 1h entry context with 4h regime | Pullback-structure failure or 4h trend invalidation | Raise stop under confirmed higher pullback structure with volatility buffer | Structure confirmation, buffer, 4h invalidation threshold, time stop |
| **MPG-001 / MPG-LONG** | Long, closed 1h | Momentum-floor failure or no-continuation timeout | Raise stop under momentum floor / higher low | Floor definition, continuation window, buffer, timeout |
| **MI-001 / MI-LONG** | Long, closed 1h anchored to 12h impulse | Impulse invalidation or fast reversal | Faster structural trail after TP1 | Impulse reference, reversal threshold, structure window, buffer |
| **SOR-001 / SOR-LONG** | Long, closed 15m | Opening-range reclaim failure/session invalidation | Trail under higher low plus ATR buffer | Window, ATR period/multiple, session rule, timeout |
| **SOR-001 / SOR-SHORT** | Short, closed 15m | Opening-range reclaim failure/session invalidation | Trail over lower high plus ATR buffer | Window, ATR period/multiple, session rule, timeout |
| **BRF2-001 / BRF2-SHORT** | Short, closed 1h | Rally-high reclaim or squeeze invalidation | Trail over lower-high/rally structure | Canonical rally reference, squeeze threshold, window, buffer |

The BRF2 replay must first resolve the existing wording drift between
`rally_high_reference`, `squeeze_reclaim_or_atr_reference`, and
`rally_high_or_atr_reference`. One canonical versioned term must be selected
before activation.

### TP and runner candidate baseline

The current catalog baseline **TP1 = 1R, 50%** remains a candidate for each
right-tail Event Spec. Release C must independently test:

- TP1 fraction and target;
- `LIMIT_GTC` versus `PASSIVE_LIMIT_GTX` fill/fee behavior;
- no fixed TP2 versus strategy-specific fixed-target alternatives;
- structural trail family and parameter grid;
- invalidation and time-stop priority.

A universal hard TP2 is not assumed.

### Replay acceptance metrics

| Dimension | Required metrics | Reason |
| --- | --- | --- |
| Return shape | Net R, median/mean R, tail-winner contribution, profit giveback | Preserve the right tail rather than optimize only win rate |
| Risk | MFE, MAE, stop distance, worst rolling window, false-breakout loss | Prove bounded downside and adverse behavior |
| Cost | Maker/taker fill rate, actual/simulated fee, slippage, funding | Evaluate the TP1 fee decision explicitly |
| Operations | Stop-update count, rejected passive orders, order churn, time in trade, capital-slot occupancy | Bound runtime and venue pressure |
| Robustness | Symbol matrix, long/short separation, regime buckets, out-of-sample windows | Avoid one-sample overfit |

Replay must use realistic bar-touch ambiguity rules and conservative fill
assumptions. A passive TP1 may not be counted filled merely because a bar high
or low touched the price without sufficient ordering evidence.

### Activation sequence

After replay, Release C stops at the Owner gate with a versioned comparison and
recommended parameters. Only approved values may proceed:

```text
Owner approves exact Event Spec policy version
-> create new strategy/event/policy version for future Tickets
-> keep historical Tickets unchanged
-> activate one Event Spec
-> one-Ticket canary
-> prove snapshot, TP1, runner, replacement/invalidation, settlement, fee truth
-> expand only within the already approved exact scope
```

SOR is the recommended first activation because the real lifecycle incident
exposed its runner gap. This recommendation does not pre-authorize parameters.

## Failure Matrix

| Failure | Classification | Exchange-write rule | Owner-facing state |
| --- | --- | --- | --- |
| TP1 passive request authoritatively rejected | Recoverable placement state | Retry deterministic passive generation; no market fallback | **running** unless retry budget/capability is exhausted |
| TP1 command outcome unknown | Durable command unknown outcome | Reconcile by client order identity; no duplicate | **temporarily unavailable** if unresolved |
| Runner missing while position open | Protection degradation | No policy evaluation; recover protection through existing authority | **needs intervention** only if automation cannot recover |
| Two unexplained active runner generations | Reconciliation mismatch | Freeze mutation; exact reconciliation | **temporarily unavailable** |
| Exit market fact stale/missing | Fact availability blocker | Keep existing exchange stop; no synthetic local action | **running** or **temporarily unavailable** by duration |
| New runner placed, old cancel outcome unknown | Replacement recovery | Keep both exact linked stops until reconciliation | **processing** |
| Strategy close command outcome unknown | Durable command unknown outcome | No duplicate close; reconcile exact command | **temporarily unavailable** |
| Manual external close | External action requiring attribution | No heuristic write; exact cleanup after flat proof | **processing**, then **completed** |

## Owner-Facing Language

Normal notifications use product states, not internal proof names:

- **running** — position protected and policy monitoring healthy;
- **processing** — TP1, stop replacement, or final exit is reconciling;
- **temporarily unavailable** — exact exchange outcome or protection identity
  cannot yet be proved;
- **needs intervention** — automation exhausted its bounded recovery path;
- **completed** — lifecycle, settlement, and review closed.

Maker/taker, command generation, policy hash, and blocker codes remain developer
or audit detail unless they create a real Owner action.

## Security And Safety Invariants

1. **No silent authority upgrade:** a policy snapshot cannot grant submit
   authority beyond Ticket, FinalGate, Operation Layer, account, instrument,
   side, profile, and Owner scope.
2. **No historical reinterpretation:** policy updates affect only future
   Tickets.
3. **No unprotected replacement:** the old runner stop is cancelled only after
   the new exact order is confirmed.
4. **No duplicate submit:** all place/cancel actions use deterministic durable
   commands and unknown-outcome reconciliation.
5. **No market TP1 fallback:** passive placement failure does not authorize
   market execution.
6. **No direct file authority:** runtime decisions use PG/current services and
   exact exchange facts only.
7. **No hidden crypto assumption:** core models use canonical instrument,
   venue capability, session/calendar, side, and quantity/price rules.
8. **No automatic emergency close expansion:** emergency behavior remains
   outside this program until separately authorized.

## Test And Certification Strategy

### Unit tests

- typed policy validation and hashing;
- long/short monotonic trailing;
- invalidation and time-stop priority;
- active generation resolver;
- TP1 type/time-in-force/post-only mapping;
- maker/taker normalization and fee propagation;
- exact command idempotency and unknown outcomes.

### PostgreSQL integration tests

- policy uniqueness and future-only Ticket binding;
- historical `legacy_unbound` behavior;
- current projection ownership and watermark claims;
- replacement crash recovery at every step;
- external-close attribution and orphan cleanup;
- one Live Outcome and one settlement result.

### Full-chain simulation

Run all six Event Specs through:

```text
signal -> Ticket -> entry -> SL + passive TP1 -> TP1 fill
-> runner -> evaluation -> replacement or strategy close
-> reconciliation -> settlement -> review
```

Negative cases include partial entry, TP1 rejection, TP1 partial fill, stale
fact, missing protection, duplicate active generation, exchange timeout,
restart, manual close, long/short inversion, and venue capability absence.

### Production release certification

Each release requires:

- targeted tests;
- complete unit and PG integration suites appropriate to the touched boundary;
- `scripts/audit_production_runtime_file_io.py` with
  `performance_risk.status = clear`;
- `scripts/validate_output_artifact_scope.py --git-status --git-tracked`;
- deploy-plan dry run;
- Tokyo read-only preflight;
- exact deployed virtualenv Python in the postdeploy verifier;
- postdeploy read-only lifecycle and command reconciliation;
- zero tracked/generated runtime output committed.

### External adapter references

- Binance USD-M defines **GTX** as Good Till Crossing: the order is cancelled
  when it cannot become the maker. Source:
  `https://developers.binance.com/zh-CN/docs/products/derivatives-trading-usds-futures/common-definition`.
- The CCXT manual treats post-only support as a feature-detected capability and
  notes that unified post-only time-in-force support varies by exchange.
  Source: `https://github.com/ccxt/ccxt/wiki/manual`.

The implementation therefore verifies the exact pinned CCXT **4.5.56** adapter
payload and does not infer support from generic `create_order` availability.

## Deployment And Rollback

### Release A

Deploy only after zero active real lifecycles. Rollback to the prior release is
allowed only after the same quiescence check. Release A deploys additive
migration **121** for protection generation and TP1 execution/fee truth. Legacy
time-in-force remains unknown rather than being synthesized; additive columns
are backfilled only with fail-safe values that old code can ignore.

### Release B

Deploy migration **122** and code with capability disabled. Rollback may switch
application code only while no Ticket has a non-legacy active exit-policy
snapshot. Once a future policy is activated, rollback to code unaware of that
policy is forbidden; use forward-fix or pause new Ticket creation.

### Release C

After Owner approval, migration **123** creates only the accepted future policy
version. Activation rollback means:

1. stop creating new Tickets for the affected policy version;
2. keep already-created Tickets on their frozen version;
3. keep their exchange-native stop and existing lifecycle maintenance active;
4. forward-fix or complete them under the frozen semantics;
5. never cancel a live protective stop merely to roll back a policy.

## WIP And Live-Enablement Position

This program is one **P0 lifecycle work item**, not six independent WIP lanes.
The Event Specs remain the existing pre-trade management units; Release C
activates them sequentially.

| Stage | Chain position before | Chain position after | First blocker removed | Next blocker |
| --- | --- | --- | --- | --- |
| **A** | Runner can become unmaintained; TP1 execution style is under-specified | Existing lifecycle continuously supervised; TP1 cannot silently downgrade | Lifecycle continuity and order-style ambiguity | Generic policy capability absent |
| **B** | Strategy exit names are not executable Ticket authority | Typed future-only policy capability exists, disabled | Missing shared exit abstraction | Strategy evidence and Owner activation |
| **C** | Exit parameters are candidates only | One approved Event Spec at a time is active for future Tickets | Strategy-specific exit-policy blocker | Natural production outcome calibration |

## Owner Decision Gates

### No decision required before Release A

Release A repairs shared invariants and enforces the already stated TP1 limit
policy. It does not change target, fraction, leverage, notional, or scope.

### No decision required before Release B

Release B installs disabled capability and proves it in rehearsal. It grants no
new production behavior.

### Mandatory stop inside Release C

Implementation must stop after replay and before any `current` policy or live
activation is written. The Owner decision package must contain:

1. exact policy version per Event Spec;
2. TP1 target/fraction/execution style;
3. invalidation and time-stop definitions;
4. runner structure, timeframe, buffer, and minimum improvement;
5. maker/taker fill and fee comparison;
6. tail-return, drawdown, order-churn, and robustness evidence;
7. recommended first canary Event Spec.

This is the only currently known Owner policy decision required by the design.

## Program Acceptance Criteria

The design is fully implemented only when:

1. **Release A** is deployed and an open `runner_protected` lifecycle remains
   continuously selectable and reconcilable.
2. TP1 durable commands and exchange evidence prove **LIMIT**, explicit
   time-in-force, no market fallback, liquidity role, and fee truth.
3. All lifecycle services resolve active protection by exact generation and
   lineage, not first role match.
4. **Release B** binds a typed immutable Exit Policy snapshot into future
   Tickets without reinterpreting historical Tickets.
5. Exit evaluation is pure and all mutations flow through the existing durable
   exchange-command authority.
6. Replacement survives restart and unknown outcomes without duplicate submit
   or a protection gap.
7. Production no-due ticks create zero JSON/Markdown files and bounded runtime
   work.
8. All six Event Specs pass the production-shaped positive and negative matrix.
9. **Release C** stops for Owner approval before exact strategy parameter
   activation.
10. Each activated Event Spec proves one future Ticket end to end through
    settlement, fee truth, and review before wider in-scope activation.
