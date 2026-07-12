---
title: P0_REAL_SIGNAL_EXECUTABILITY_AND_BLOCKER_TRUTH_DESIGN
status: IMPLEMENTED_PENDING_DEPLOYMENT
authority: docs/current/P0_REAL_SIGNAL_EXECUTABILITY_AND_BLOCKER_TRUTH_DESIGN.md
last_verified: 2026-07-12
---

# P0 Real-Signal Executability And Blocker Truth Design

## Decision

The next medium-scale program is a bounded re-certification of **P0-RT Real
Signal -> Ticket Closure**:

```text
P0-RT-X Execution Feasibility And Blocker Truth Closure
```

It preempts Strategy Opportunity / Replay-Live Calibration because a natural
CPM signal proved that the market supplied an eligible strategy event while the
current pre-trade projection incorrectly described an impossible sizing scope
as `market_wait_validated`, then erased the action-time business blocker after
the signal expired.

This program is infrastructure shared by all active StrategyGroups. It does
not change CPM semantics, add a strategy, expand a symbol/side scope, call
FinalGate, call Operation Layer, or grant exchange-write authority.

## Production Incident Evidence

Tokyo PG and journals recorded this chain on 2026-07-12:

| Field | Value |
| --- | --- |
| Strategy event | `CPM-RO-001 / ETHUSDT / long / CPM-LONG` |
| Signal | `signal:7dce92f66756ee63fa5612b45cee3ebb` |
| Event time | `1783828799999` |
| Observed time | `1783829348983` |
| Expiry | `1783829620002` |
| Action-time sequence duration | `23088 ms` |
| Ask | `1809.65` |
| Quantity step | `0.001` |
| Exchange minimum notional | `20` |
| Current target/cap | `20` |
| Floored quantity/notional | `0.011 / 19.90615` |
| Minimum executable quantity/notional | `0.012 / 21.71580` |
| Process outcome | `business_blocked / temporarily_unavailable` |
| First technical blocker | `risk_reservation_rounded_notional_below_exchange_minimum` |
| Promotion / lane / Ticket | none; atomic savepoint rolled back correctly |
| Watcher / monitor notification | sent |
| Later current projection | incorrectly returned `waiting_for_signal` with no blocker |

The current 22-scope audit found 8 scope rows mechanically incompatible with
the current `20 USDT` hard cap: CPM ETH, MI ETH, SOR ETH both sides, SOR BTC
both sides, BRF2 ETH, and BRF2 BTC. The remaining 14 rows pass only this
specific entry sizing check; they still require strategy, account, protection,
FinalGate, and Operation Layer facts at action time.

## Root Cause

The failure class is:

```text
one owner-policy max_notional value used as both target and cap
+ multiple sizing/feasibility implementations with different rounding semantics
+ public-fact readiness proves rule presence, not policy/rule compatibility
+ atomic action-time rollback leaves only a lane-scoped process outcome
+ current read models suppress that unresolved process outcome after signal expiry
+ monitor sees fresh signal but not the terminal business blocker
-> rare real opportunity reaches action time before an impossible scope is detected
   and later status incorrectly returns to waiting for market
```

The relevant duplicated paths are currently:

- `src/application/action_time/pricing_sizing.py`;
- `src/application/notional_sizing.py`;
- `src/application/phase5e_rehearsal_feasibility.py`;
- local quantity checks in protected-submit and read-model consumers.

The design replaces entry sizing truth rather than adding another adapter.

## Owner Policy Decision

The Owner confirmed that the entire futures subaccount is already isolated,
reviewed, loss-capable experiment capital. The earlier fixed values
`max_notional=20`, `leverage=2`, and `loss_unit=10` were introduced by
`codex_seed`; they were not derived from account state or an explicit Owner
risk formula and must not remain live sizing authority.

The replacement Owner policy is:

```text
planned_stop_risk_fraction = 0.03
max_initial_margin_utilization = 0.90
max_leverage = 10
attempt_cap = 1
```

`totalWalletBalance` is the dynamic risk-capital base. `availableBalance` is
the dynamic margin-capacity base. Both values must come from a fresh signed
read-only account fact at Action-Time and remain numeric in the PG fact
snapshot; presence/positive booleans are not sufficient.

Fees, funding, and slippage are excluded from the pre-submit hard risk amount.
They are measured from actual fills and income rows after execution. The
pre-submit value is therefore named `planned_stop_risk`, not `maximum_loss` or
`worst_case_loss`.

## Core Model

### One Typed Decision

Create one pure typed decision used by pre-trade readiness and action-time
materialization:

```text
ExecutionInstrumentRules
+ ExecutionSizingPolicy
+ side-aware price
+ optional protective stop price
-> ExecutionSizingDecision
```

`ExecutionInstrumentRules` owns:

- canonical symbol and exchange instrument identity;
- order rule surface (`market_entry` for current entry path);
- executable price reference and source fact snapshot;
- minimum quantity;
- quantity step;
- minimum notional;
- observation and validity times.

`ExecutionSizingPolicy` owns:

- Owner `planned_stop_risk_fraction` (`0.03`);
- Owner `max_initial_margin_utilization` (`0.90`);
- Owner `max_leverage` (`10` for the current crypto USD-M pilot);
- attempt cap and policy version references.

`ExecutionAccountCapacity` owns:

- fresh `total_wallet_balance`;
- fresh `available_balance`;
- account fact snapshot identity and validity.

`ExecutionSizingDecision` returns:

- raw target quantity;
- desired floored quantity;
- minimum executable quantity;
- intended quantity;
- effective notional;
- stop risk when a protective stop is available;
- exact feasibility state and blocker reasons;
- rule, policy, and price lineage.

### Quantity And Leverage Algorithm

The algorithm sizes from the Owner loss policy, then chooses the lowest
sufficient integer leverage without exceeding Owner or exchange authority:

```text
planned_stop_risk_budget = total_wallet_balance * 0.03
per_unit_stop_risk = abs(entry_price - protective_stop_price)
risk_qty = floor(planned_stop_risk_budget / per_unit_stop_risk, qty_step)

margin_capacity = available_balance * 0.90
risk_notional = risk_qty * entry_price
required_leverage = ceil(risk_notional / margin_capacity)
selected_leverage = min(max(required_leverage, 1), 10, exchange_max_leverage)

margin_qty = floor(margin_capacity * selected_leverage / entry_price, qty_step)
intended_qty = min(risk_qty, margin_qty)
minimum_qty = ceil(max(min_qty, min_notional / entry_price), qty_step)
```

If the leverage required to use the complete risk budget exceeds `10`, the
system uses `10` and automatically shrinks quantity. It must not increase
leverage beyond policy merely to consume the full three-percent budget.

The decision is valid only when:

- every numeric value is finite and positive;
- quantity is step-aligned and at least the exchange minimum;
- effective entry notional satisfies exchange minimum;
- selected leverage is the lowest sufficient integer not above Owner and
  exchange limits;
- required initial margin does not exceed ninety percent of fresh available
  balance;
- the stop is protective for the side and produces positive
  `planned_stop_risk` not exceeding three percent of fresh wallet balance;
- rules and price facts remain fresh.

No consumer may recompute intended entry quantity from loose dictionaries.

### Exchange Leverage Application

`selected_leverage` is not merely descriptive Ticket metadata. The ENTRY
exchange command persists it as `desired_leverage`. The single ticket-bound
Exchange Command Worker performs this sequence outside any open PG transaction:

```text
claim durable ENTRY command
-> Binance set_leverage(desired_leverage, symbol)
-> create ENTRY order with deterministic client_order_id
-> persist authoritative result or outcome_unknown
```

Only ENTRY may carry `desired_leverage`; protection and exit commands that try
to mutate leverage fail before an exchange write. A timeout in either leverage
or order dispatch becomes `exchange_command_outcome_unknown` and freezes the
netting domain until exchange reconciliation resolves it.

## Instrument Rule Ownership

The Binance public collector already reads `LOT_SIZE`, `MARKET_LOT_SIZE`, and
`MIN_NOTIONAL`, but current PG fact values retain only `qty_step` and
`min_notional`. Extend the existing `pretrade_public` fact values with:

```text
min_qty
qty_step
min_notional
quantity_rule_source
order_rule_surface
```

Do not create a file-backed instrument-rule store. The live public fact
snapshot remains the freshness owner for pre-trade and action-time pricing.
`brc_exchange_instruments` remains identity/static metadata and must not be
treated as fresh rule authority while its precision fields are null.

The typed model is asset-class neutral. Future venues and asset classes provide
their own `ExecutionInstrumentRules` adapters, including session, contract,
precision, settlement, and order-type semantics, without copying sizing logic.

## Pre-Trade Feasibility

Before a candidate row may use `market_wait_validated`, the Candidate Pool
projector must compute an entry feasibility decision from:

```text
current PG owner policy
+ current runtime scope binding
+ fresh pretrade_public fact snapshot
```

If the minimum executable quantity cannot fit the current planned-stop-risk or
margin capacity:

```text
readiness_state = blocked
promotion_state = blocked
first_blocker_class = execution_gate_gap
first_blocker_detail = minimum_executable_quantity_exceeds_planned_stop_risk_budget
  or minimum_executable_quantity_exceeds_margin_capacity
next_action = preserve observation and wait for a compatible account/price/stop state
```

The exact desired quantity, minimum executable quantity, effective notional,
hard cap, and cap shortfall remain developer/audit detail. The primary Owner
surface says the instrument is temporarily unavailable under the current
capital range.

This is not `computed_not_satisfied`: strategy facts may be true while the
execution profile is mechanically incompatible. It is not
`hard_safety_stop`: observation and engineering may continue, but real submit
must fail closed.

## Action-Time Parity

Promotion and Ticket materialization must consume the same typed decision at a
fresh action-time price and protection reference. Action time may still block
for a changed price, stale rule, account fact, stop direction, risk budget,
position/order conflict, leverage bracket, or protection fact.

The atomic savepoint remains. A failed candidate must not leave partial
promotion, lane, reservation, or Ticket rows. Its lane-scoped
`brc_runtime_process_outcomes` row is the durable failure truth.

## Blocker Conservation And Resolution

An unresolved lane-scoped action-time outcome must participate in current
readiness even after its source signal expires.

The current blocker remains relevant until one of these occurs with a newer
watermark:

1. a successful execution-feasibility certification under the current policy
   and current instrument rules;
2. a successful Action-Time Ticket sequence for a distinct fresh signal;
3. a policy version explicitly removes or changes the affected scope;
4. a runtime-scope binding is paused, revoked, or expired.

A no-signal/global noop outcome must not overwrite or suppress a lane-scoped
business blocker. A historical blocker from a superseded policy/rule version
must not block a newly certified scope.

Reuse `brc_runtime_process_outcomes`; do not add another evidence table or
current projection. Signal expiry is not a blocker TTL. Resolution occurs only
when the same process/lane current row is replaced by a successful sequence or
by `certify_action_time_blocker_resolution`, which requires the exact current
outcome id, exact expected blocker, runtime head, and non-empty certification
reference. The certification surface creates no signal, Ticket, grant, order,
or exchange authority.

## Read Models And Notification

Candidate Pool, Daily Table, Tradeability Decision, Goal Status, and Server
Monitor must conserve the same first blocker and source watermark.

Owner mapping:

| Internal state | Owner state | Owner sentence |
| --- | --- | --- |
| minimum quantity exceeds risk or margin capacity | `temporarily_unavailable` | `当前止损与资金条件无法形成合规仓位，暂不可用` |
| compatible scope, no signal | `waiting_for_opportunity` | `等待机会` |
| action-time sequence running | `processing` | `系统自动处理中` |
| newer certification resolves blocker | `running` or `waiting_for_opportunity` | `无需操作` |

Server Monitor sends one transition notification when a scope becomes
unavailable and one resolution notification when it becomes compatible. It
must not mark watcher infrastructure failed for a business blocker.

## Alternatives

| Alternative | Result | Decision |
| --- | --- | --- |
| Patch ETH by rounding up locally | Fixes one symptom; preserves duplicate truth and hidden blocker | Reject |
| Remove ETH/BTC from observation | Reduces useful signal feedback and hides policy incompatibility | Reject as engineering design; Owner may narrow live scope separately |
| Add a new feasibility packet/read model | Adds another state owner and source drift | Reject |
| One typed decision plus existing PG readiness/outcome projections | Closes the class and supports future allocation/assets | Accept |

## Data And Migration

Migration `115` replaces the legacy sizing-policy meaning with explicit fields:

```text
brc_owner_policy_current.planned_stop_risk_fraction = 0.03
brc_owner_policy_current.max_initial_margin_utilization = 0.90
brc_owner_policy_current.max_leverage = 10
```

Legacy `max_notional`, `leverage`, and `loss_unit` remain readable only for
historical lineage during the migration window and are not consulted by the
new sizing decision. A follow-up cleanup migration may remove them after every
producer and consumer is certified. There is no runtime fallback to the old
values.

Account-safe PG facts add exact numeric `total_wallet_balance` and
`available_balance`, with their source timestamp and expiry. Budget and Ticket
rows persist `planned_stop_risk_budget`, `planned_stop_risk`,
`selected_leverage`, `effective_notional`, and `reserved_margin` so downstream
consumers validate lineage instead of recomputing it. Exchange commands persist
ENTRY-only `desired_leverage`.

Live Outcome persists actual fill commission and signed entry slippage versus
the Action-Time entry reference. Actual fill PnL already contains execution
price impact, so slippage is not subtracted a second time. Funding remains
nullable until a ticket-time-bounded Binance income row is ingested; it is not
estimated and never blocks entry.

## Cadence And Performance

| Dimension | Required behavior |
| --- | --- |
| Cadence | Lightweight feasibility runs during the existing bounded public-fact/current-projection tick; exact stop-risk decision runs only for fresh action-time candidates |
| File writes | `0` JSON/MD files on no-signal and signal ticks |
| PG writes | Existing readiness current rows are updated; process outcomes remain one current row per process/scope; budget, Ticket, and durable command carry sizing lineage; no per-tick append-only feasibility table |
| CPU | Decimal arithmetic is linear in 22 bounded scope rows; no heavy report builder enters the Ticket transaction |
| Timeout | Existing public API and Action-Time subprocess timeouts remain bounded; Action-Time must finish before the shortest fact/signal expiry |
| Disk | No sidecar, packet, proof, trace, or report file is introduced |
| Retention | Existing runtime fact/process retention applies; no new archive cadence |

## Verification

Required test matrix:

- exact CPM/ETH incident numbers under dynamic account capacity;
- the `100 USDT / 3% / 90% / 0.5% stop` example selects `7x`, `600 USDT`
  notional, and `3 USDT` planned risk;
- the same example with a policy maximum below required leverage shrinks
  quantity without exceeding planned risk;
- all 22 active scope rows under fresh dynamic account facts;
- missing/stale/malformed min quantity, step, min notional, price, policy target,
  wallet balance, available balance, and leverage bracket;
- long and short protective stop direction and positive stop risk;
- same typed decision reused by promotion, budget, Ticket, and submit lineage;
- signal expiry does not erase a lane business blocker;
- newer policy/rule certification resolves the blocker;
- global no-signal outcome cannot overwrite lane truth;
- monitor transition notification and resolution dedupe;
- six current Event Specs and 22-scope production-shaped impact suite;
- full regression, docs/output/file-I/O validators, and Tokyo postdeploy
  acceptance.

## Deployment And Rollback

Deployment follows the existing bounded Tokyo git-export path with a short
maintenance window. Migration and code deploy together; there is no PG/file or
old/new sizing dual authority in production.

Rollback must fail closed. It may stop watcher progression, disable affected
ticket materialization, and forward-fix PG/code. It must not restore old sizing
logic as a fallback, lower or increase Owner policy silently, or read JSON/MD
authority.

## Completion

The program is complete when:

1. one typed decision owns entry sizing, planned stop risk, margin capacity,
   and selected leverage;
2. the old fixed `20/2x/10` seed is no longer runtime sizing authority;
3. all 22 scope rows expose truthful feasibility before market wait;
4. incompatible rows cannot emit a real-submit promotion/lane/Ticket;
5. compatible fresh signals use the same decision through Ticket lineage;
6. unresolved lane blockers persist across signal expiry and appear in every
   current read model and monitor decision;
7. a newer successful certification resolves the blocker deterministically;
8. tests, audits, and Tokyo postdeploy acceptance pass;
9. only a natural market signal/live venue outcome remains for live calibration.

## Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: CPM-RO-001
symbol: ETHUSDT
side: long
stage: fresh_signal_detected_then_action_time_sequence_business_blocked
first_blocker: execution_gate_gap
first_blocker_detail: legacy fixed-notional policy prevented an exchange-valid dynamic risk decision
signal_event_id: signal:7dce92f66756ee63fa5612b45cee3ebb
promotion_candidate_id: none
action_time_lane_input_id: none
ticket_id: none
next_action: implement one dynamic risk decision and conserve its blocker in PG current projections
stop_condition: 22 scopes are truthfully certified and the next eligible natural signal reaches Ticket or one genuine action-time safety blocker
owner_action_required: no; risk fraction, margin utilization, and maximum leverage are confirmed
authority_boundary: no FinalGate bypass, no Operation Layer bypass, no stale-signal submit, no leverage above 10x
```
