# L2-L7 Pre-Trade Chain Reset Temporary Draft

Status: temporary working draft, not a final project constraint.
Recorded at: 2026-07-04
Owner source: explicit Owner correction in current Codex thread.

## Purpose

This document temporarily records the Owner's current direction before it is
converted into durable project constraints, PG schema constraints, or runtime
contracts.

It exists to prevent chat-memory drift during the L2-L7 pre-trade chain reset.
It must not be treated as a final authority until the Owner confirms the final
wording and target contract locations.

## Owner Decisions Recorded

### 1. Multi-Symbol And Long/Short Target

The desired system shape is:

```text
multi-symbol + long/short capable
```

But long/short capability must be derived from each StrategyGroup's real
strategy semantics.

The system must not assume every StrategyGroup can trade both long and short.

### 2. No Forced Long/Short Mirroring

The Owner does not authorize mechanical side mirroring.

Invalid interpretation:

```text
Strategy supports long
-> automatically create short version
```

Required interpretation:

```text
Strategy-specific semantics
-> supported side scope
-> side-specific facts
-> side-specific fresh signal
-> side-specific runtime coverage
-> side-specific action-time ticket
```

### 3. Strategy-by-Strategy Review Required

The L2-L7 reset must be discussed one StrategyGroup at a time.

Current active WIP StrategyGroups:

| StrategyGroup | Preliminary side stance | Confirmation status |
| --- | --- | --- |
| CPM-RO-001 | long only; short requires a new StrategyGroup or strategy variant | confirmed in Owner Confirmation Round 2 |
| MPG-001 | long only; short requires a new StrategyGroup or strategy variant | confirmed in Owner Confirmation Round 3 |
| MI-001 | long only / long-first; short requires a new StrategyGroup or strategy variant | confirmed in Owner Confirmation Round 4 |
| SOR-001 | long and short capable only through explicit side-specific event specs | confirmed in Owner Confirmation Round 5 |
| BRF2-001 | short only; long requires a new StrategyGroup or strategy variant | confirmed in Owner Confirmation Round 6 |

### 4. No MVP / Transitional Runtime Design

The Owner explicitly rejects MVP or temporary transition designs for this reset.

Invalid justification:

```text
Do a lightweight JSON/file bridge first
Move to PG later
Temporary output source is acceptable
```

Required direction:

```text
Design the durable PG-backed model directly
Put runtime/trading constraints into database-enforced structures where possible
Do not depend on repo MD/JSON for runtime or trading decisions
Do not create temporary paths that become historical debt
```

### 5. Current Focus Is L2-L7

The current focus is not FinalGate or Operation Layer first.

The reset scope is:

| Layer | Chinese name | Reset concern |
| --- | --- | --- |
| L2 Candidate Universe | 候选交易范围 | StrategyGroup + symbol + side scope must come from strategy semantics and Owner policy |
| L3 Runtime Coverage | 服务器运行覆盖 | Runtime must cover the exact StrategyGroup + symbol + side |
| L4 Market Facts | 市场事实 | Facts must declare which side they support |
| L5 Fresh Signal | 新鲜交易信号 | Fresh signal must have real market event identity and timestamp |
| L6 Candidate Pool | 候选池 | Promotion must consume only clean L2-L5 inputs |
| L7 Action-Time Ticket | 交易前正式票据 | One unique machine ticket must identify the exact candidate trade |

## Owner Confirmation Round 1

Recorded after the first L2-L7 grilling exchange.

### Known Owner Answers

The Owner provided the following confirmations:

| Item | Owner answer | Temporary interpretation |
| --- | --- | --- |
| 1 | 系统能力 | Multi-symbol and long/short capability is a system capability target, not proof that every StrategyGroup supports every side |
| 2 | 没问题 | No forced long/short mirroring remains accepted |
| 3 | PG 理解没问题 | PG should be treated as the durable constraint authority, not just a storage layer |
| 4 | 没问题 | Strategy-by-strategy side/symbol review remains accepted |
| 5 | 新策略 | If a side is not native to a StrategyGroup, it should become a new StrategyGroup or strategy variant, not a mirrored side on the old one |
| 6 | 没问题 | Side-specific facts and side-specific fresh signal requirements remain accepted |
| 7 | 没问题 | Action-Time Ticket uniqueness remains accepted |
| 8 | 没问题 | Repo MD/JSON must not be runtime or trading decision truth in the target design |

### Important Interpretation Boundary

This round confirms the design direction, but it does not yet finalize the
side/symbol scope for each individual StrategyGroup.

The next grilling step must still resolve each StrategyGroup explicitly:

```text
CPM-RO-001
MPG-001
MI-001
SOR-001
BRF2-001
```

For each StrategyGroup, the system must separately confirm:

```text
supported symbols
supported sides
side-specific facts
fresh signal definition
promotion rule
Action-Time Ticket requirements
whether unsupported opposite-side behavior must become a new StrategyGroup
```

## Owner Confirmation Round 2 - CPM-RO-001

Recorded after the Owner confirmed the proposed CPM-RO-001 scope.

### Confirmed CPM-RO-001 Scope

| Dimension | Confirmed decision |
| --- | --- |
| StrategyGroup | CPM-RO-001 |
| Candidate symbols | ETHUSDT, SOLUSDT, AVAXUSDT, SUIUSDT |
| Supported side | long only |
| Unsupported side behavior | short must not be mirrored automatically |
| Short-side future path | a separate StrategyGroup or strategy variant is required |
| Fresh signal source | real market event time only |
| Invalid fresh signal source | artifact generated_at time, report refresh time, or file write time |

### CPM-RO-001 L2-L7 Temporary Rule

For CPM-RO-001, a candidate may move forward only when the chain proves:

```text
CPM-RO-001
+ one of ETHUSDT / SOLUSDT / AVAXUSDT / SUIUSDT
+ long
+ side-specific CPM long facts satisfied
+ real market-event fresh signal timestamp
+ server runtime coverage for that StrategyGroup + symbol + long scope
+ unique Action-Time Ticket identity
```

The chain must reject:

```text
CPM-RO-001 + short
CPM-RO-001 + unsupported symbol
CPM-RO-001 + generated_at-only freshness
CPM-RO-001 + action-time ticket without exact strategy/symbol/side/signal identity
```

### PG Constraint Implication

The target PG design must make CPM-RO-001 side scope enforceable as data, not as
an informal convention.

Required constraint meaning:

```text
CPM-RO-001 may produce L6 Candidate Pool rows only for allowed symbols and long side.
CPM-RO-001 may produce L7 Action-Time Tickets only from those valid L6 rows.
CPM-RO-001 short candidates require a different StrategyGroup or strategy variant id.
```

## Grilling Method Adjustment

Recorded after the Owner corrected the questioning style.

### Required Discussion Format

The L2-L7 grilling process must not ask the Owner abstract open questions
without a concrete recommendation.

Each StrategyGroup discussion must use this format:

```text
1. Codex recommendation
2. Plain-language reason
3. Risk if this recommendation is wrong
4. Owner confirmation or correction points
5. Temporary document update after each round
```

### Reason

The Owner understands the high-level chain direction, but does not need to know
every implementation field before making governance decisions.

Therefore Codex must translate implementation complexity into concrete
strategy-governance choices:

```text
what I recommend
why it fits the strategy
what it would block or allow
what needs a new StrategyGroup instead of forced mirroring
what PG constraints should later enforce
```

### Invalid Grilling Style

```text
What are the supported sides?
What facts are side-specific?
What event creates a fresh signal?
```

This is invalid when asked without a recommendation, because it pushes
implementation interpretation back to the Owner.

### Required Grilling Style

```text
My recommendation: this StrategyGroup should be long only for now.
Reason: the current strategy semantics describe a rebound / continuation entry,
not a symmetric short model.
Impact: long candidates can progress; short candidates must be rejected unless a
new StrategyGroup variant is created.
Owner decision needed: confirm or correct this side boundary.
```

## Grilling Method Adjustment 2

Recorded after the Owner asked Codex to keep grilling without waiting for
manual "continue" prompts.

### Continuous Grilling Rule

Codex must continue the L2-L7 grilling sequence automatically until no material
open design question remains.

Required behavior:

```text
Owner answers one round
-> Codex records that round into this temporary document
-> Codex immediately advances to the next unresolved design point
-> Codex includes its recommendation before asking for confirmation
-> Repeat until the chain has no unresolved L2-L7 question
```

This does not mean Codex should make unconfirmed Owner policy decisions. It
means Codex should actively propose the next concrete decision instead of
waiting for the Owner to say "continue".

### Current Remaining Grilling Sequence

The remaining sequence is:

```text
1. Define event specs:
   CPM-LONG
   MPG-LONG
   MI-LONG
   SOR-LONG
   SOR-SHORT
   BRF2-SHORT

2. Define PG constraints:
   strategy side scope
   event specs
   required facts
   live signal events
   candidate pool rows
   action-time tickets

3. Define rejection rules:
   no generated_at freshness
   no unsupported side
   no generic fresh signal
   no candidate without exact event_id
   no ticket without candidate row

4. Define migration targets:
   which old code/json/md semantics must be replaced or corrected
   which generated artifacts become exports only
   which PG projections become decision truth
```

## Owner Confirmation Round 3 - MPG-001

Recorded after the Owner confirmed that the Codex recommendation matches MPG
understanding.

### Confirmed MPG-001 Scope

| Dimension | Confirmed decision |
| --- | --- |
| StrategyGroup | MPG-001 |
| Candidate symbols | OPUSDT, SOLUSDT, AVAXUSDT, SUIUSDT |
| Supported side | long only |
| Unsupported side behavior | short must not be mirrored automatically |
| Short-side future path | a separate StrategyGroup or strategy variant is required |
| Fresh signal source | real market event time only |
| Invalid fresh signal source | artifact generated_at time, report refresh time, or file write time |

### MPG-001 L2-L7 Temporary Rule

For MPG-001, a candidate may move forward only when the chain proves:

```text
MPG-001
+ one of OPUSDT / SOLUSDT / AVAXUSDT / SUIUSDT
+ long
+ side-specific MPG long facts satisfied
+ real market-event fresh signal timestamp
+ server runtime coverage for that StrategyGroup + symbol + long scope
+ unique Action-Time Ticket identity
```

The chain must reject:

```text
MPG-001 + short
MPG-001 + unsupported symbol
MPG-001 + generated_at-only freshness
MPG-001 + action-time ticket without exact strategy/symbol/side/signal identity
```

### PG Constraint Implication

The target PG design must make MPG-001 side scope enforceable as data, not as
an informal convention.

Required constraint meaning:

```text
MPG-001 may produce L6 Candidate Pool rows only for allowed symbols and long side.
MPG-001 may produce L7 Action-Time Tickets only from those valid L6 rows.
MPG-001 short candidates require a different StrategyGroup or strategy variant id.
```

## Owner Confirmation Round 4 - MI-001

Recorded after the Owner confirmed the Codex recommendation for MI-001.

### Confirmed MI-001 Scope

| Dimension | Confirmed decision |
| --- | --- |
| StrategyGroup | MI-001 |
| Candidate symbols | AVAXUSDT, ETHUSDT, SOLUSDT |
| Supported side | long only / long-first |
| Unsupported side behavior | short must not be mirrored automatically |
| Short-side future path | a separate StrategyGroup or strategy variant is required |
| Fresh signal source | real market event time only |
| Invalid fresh signal source | artifact generated_at time, report refresh time, or file write time |

### MI-001 L2-L7 Temporary Rule

For MI-001, a candidate may move forward only when the chain proves:

```text
MI-001
+ one of AVAXUSDT / ETHUSDT / SOLUSDT
+ long
+ side-specific MI long facts satisfied
+ real market-event fresh signal timestamp
+ server runtime coverage for that StrategyGroup + symbol + long scope
+ unique Action-Time Ticket identity
```

The chain must reject:

```text
MI-001 + short
MI-001 + unsupported symbol
MI-001 + generated_at-only freshness
MI-001 + action-time ticket without exact strategy/symbol/side/signal identity
```

### PG Constraint Implication

The target PG design must make MI-001 side scope enforceable as data, not as an
informal convention.

Required constraint meaning:

```text
MI-001 may produce L6 Candidate Pool rows only for allowed symbols and long side.
MI-001 may produce L7 Action-Time Tickets only from those valid L6 rows.
MI-001 short candidates require a different StrategyGroup or strategy variant id.
```

## Owner Confirmation Round 5 - SOR-001 Direction And Event Gap

Recorded after the Owner accepted SOR-001 as potentially long and short capable,
then challenged whether the independent long/short events were actually clear.

### Confirmed SOR-001 Scope Direction

| Dimension | Confirmed decision |
| --- | --- |
| StrategyGroup | SOR-001 |
| Candidate symbols | ETHUSDT, SOLUSDT, AVAXUSDT, BTCUSDT |
| Supported side direction | long and short capable in principle |
| Mirroring rule | long and short must not share one mirrored event definition |
| Fresh signal source | real market event time only |
| Invalid fresh signal source | artifact generated_at time, report refresh time, or file write time |
| Owner confirmation | accepted after reviewing the event-definition gap and proposed side-specific split |

### Current Event Definition Gap

The Owner's challenge is valid: SOR-001 long and short independent events are
not yet sufficiently closed as machine-governed strategy semantics.

Known current code facts:

```text
src/domain/strategy_semantics.py registers SOR-001 with supported_sides=["long", "short"]
but its trigger/reference_role is session_opening_range_breakdown / session_opening_range_short.

src/domain/reference_price_action_evaluators.py implements SOR-001 as a short
opening-range breakdown evaluator.

scripts/build_sor_session_scope_detector.py detects an above-range session
breakout/follow-through shape, but the detector artifact does not establish a
separate side-specific SOR-LONG vs SOR-SHORT event contract.

older tradeability/replay paths reference SOR-LONG, but this is not enough to
make long and short independent PG-constrained events.
```

### Temporary SOR Event Recommendation

SOR-001 may remain conceptually bidirectional, but PG-backed promotion must not
allow either side until side-specific event specs exist.

Recommended event split:

| Event id | Side | Plain meaning | Required machine meaning |
| --- | --- | --- | --- |
| SOR-LONG | long | opening range high breaks upward and holds | closed session opening range, close above range high, follow-through confirmed, invalidation above range low held, public facts ready |
| SOR-SHORT | short | opening range low breaks downward and holds | closed session opening range, close below range low, bearish follow-through confirmed, invalidation below range high held or no reclaim, public facts ready |

### SOR-001 L2-L7 Temporary Rule

Until those event specs are represented as strategy semantics and later PG
constraints, the chain must not treat generic SOR freshness as enough.

Required proof before SOR can create a valid L6 Candidate Pool promotion:

```text
SOR-001
+ one of ETHUSDT / SOLUSDT / AVAXUSDT / BTCUSDT
+ exact side: long or short
+ exact event id: SOR-LONG or SOR-SHORT
+ side-specific event facts satisfied
+ real market-event fresh signal timestamp
+ server runtime coverage for that StrategyGroup + symbol + side scope
```

Required proof before SOR can create a valid L7 Action-Time Ticket:

```text
candidate_pool_row_id
+ SOR-001
+ symbol
+ side
+ event_id
+ event_time_utc
+ detector/fact snapshot refs
+ runtime coverage ref
+ no active position/open order conflict
```

The chain must reject:

```text
SOR-001 + generic fresh_session_range_signal without side
SOR-001 + long using short breakdown facts
SOR-001 + short using long breakout facts
SOR-001 + generated_at-only freshness
SOR-001 + action-time ticket without event_id and event_time_utc
```

### PG Constraint Implication

The target PG design must treat SOR side events as first-class rows, not as free
text or inferred side labels.

Required constraint meaning:

```text
SOR-001 Candidate Pool rows require a valid strategy_side_event_spec row.
SOR-001 Action-Time Tickets require a candidate row with exact side and event_id.
No detector row may satisfy both SOR-LONG and SOR-SHORT unless it explicitly
stores two separate event rows with separate fact snapshots and timestamps.
```

## Owner Confirmation Round 6 - BRF2-001

Recorded after the Owner confirmed the Codex recommendation for BRF2-001.

### Confirmed BRF2-001 Scope

| Dimension | Confirmed decision |
| --- | --- |
| StrategyGroup | BRF2-001 |
| Candidate symbols | BTCUSDT, AVAXUSDT, ETHUSDT |
| Supported side | short only |
| Unsupported side behavior | long must not be mirrored automatically |
| Long-side future path | a separate StrategyGroup or strategy variant is required |
| Fresh signal source | real market event time only |
| Invalid fresh signal source | artifact generated_at time, report refresh time, or file write time |

### Current Code/Design Correction Needed Later

Current code and docs contain a known over-wide side signal:

```text
src/domain/strategy_semantics.py currently registers BRF2-001 with supported_sides=["long", "short"].
```

The Owner-confirmed target semantics are narrower:

```text
BRF2-001 = short only
```

This must be corrected in the durable PG-backed design and later runtime
constraints. The system must not keep BRF2 long as an allowed runtime side just
because an old semantics row listed both directions.

### BRF2-001 L2-L7 Temporary Rule

For BRF2-001, a candidate may move forward only when the chain proves:

```text
BRF2-001
+ one of BTCUSDT / AVAXUSDT / ETHUSDT
+ short
+ BRF2-SHORT event identity
+ bear-rally-failure / bearish reversal follow-through facts satisfied
+ short-squeeze disable / squeeze-risk facts acceptable
+ real market-event fresh signal timestamp
+ server runtime coverage for that StrategyGroup + symbol + short scope
+ unique Action-Time Ticket identity
```

The chain must reject:

```text
BRF2-001 + long
BRF2-001 + unsupported symbol
BRF2-001 + generated_at-only freshness
BRF2-001 + action-time ticket without exact strategy/symbol/side/event/signal identity
```

### PG Constraint Implication

The target PG design must make BRF2-001 short-only behavior enforceable as data,
not as an informal convention.

Required constraint meaning:

```text
BRF2-001 may produce L6 Candidate Pool rows only for allowed symbols and short side.
BRF2-001 may produce L7 Action-Time Tickets only from those valid L6 rows.
BRF2-001 long candidates require a different StrategyGroup or strategy variant id.
```

### BRF2 Plain-Language Meaning

BRF2-001 is not a general reversal strategy. It is currently a bearish setup:

```text
market rallies
-> rally weakens or fails
-> bearish rejection / follow-through appears
-> short-squeeze risk is acceptable
-> short candidate may be considered
```

The strategy must not be interpreted as:

```text
market rallies
-> therefore long is also allowed
```

## Owner Confirmation Round 7 - Event-Driven Fresh Signal Rule

Recorded after the Owner confirmed that the desired model is event-driven.

### Confirmed Fresh Signal Definition

Fresh Signal must mean a real strategy event, not an artifact refresh.

Confirmed rule:

```text
Fresh Signal
= strategy_group_id
+ symbol
+ side
+ event_id
+ event_time_utc
+ side-specific fact snapshot
+ freshness window
```

Plain-language meaning:

```text
The market just produced the exact event this StrategyGroup is designed to eat.
```

### Invalid Freshness Sources

The following timestamps must never become the source of signal freshness:

```text
generated_at
report_updated_at
file_written_at
monitor_refresh_time
local cache refresh time
Codex run time
```

They may prove when the system noticed, computed, or exported a state. They do
not prove when the market opportunity happened.

### Required Event-Driven Chain Shape

The L2-L7 chain must use this event-driven order:

```text
L2 Candidate Universe
-> allowed StrategyGroup + symbol + side
-> L3 Runtime Coverage
-> server is actually watching that StrategyGroup + symbol + side
-> L4 Market Facts
-> side-specific facts are computed from real market/account-safe inputs
-> L5 Fresh Signal
-> a concrete event_id occurred at real event_time_utc
-> L6 Candidate Pool
-> only event-backed candidates may be promoted
-> L7 Action-Time Ticket
-> one exact candidate trade identity is persisted
```

### PG Constraint Implication

The target PG design should not model signal freshness as one boolean field.

Required durable concepts:

| PG concept | Meaning |
| --- | --- |
| strategy_side_event_specs | Defines which events each StrategyGroup + side is allowed to produce |
| strategy_event_required_facts | Defines which facts must satisfy each event |
| live_signal_events | Records real market event occurrences with event_time_utc |
| live_signal_fact_snapshots | Records the facts used to prove the event |
| candidate_pool_rows | May reference only valid live_signal_events |
| action_time_tickets | May reference only valid candidate_pool_rows |

### Global Rejection Rule

The chain must reject any promotion or Action-Time Ticket when:

```text
event_id is missing
event_time_utc is missing
event_time_utc comes only from generated_at/report/file time
side-specific facts are missing
facts do not match the event side
candidate tries to use a StrategyGroup side that is not allowed
```

### Event Specs To Define Next

The next grilling rounds must define the event specs:

```text
CPM-LONG
MPG-LONG
MI-LONG
SOR-LONG
SOR-SHORT
BRF2-SHORT
```

## Owner Confirmation Round 8 - CPM-LONG Event Spec

Recorded after the Owner confirmed the proposed CPM-LONG event definition.

### Confirmed CPM-LONG Event Definition

| Dimension | Confirmed decision |
| --- | --- |
| Event id | CPM-LONG |
| StrategyGroup | CPM-RO-001 |
| Side | long |
| Candidate symbols | ETHUSDT, SOLUSDT, AVAXUSDT, SUIUSDT |
| Plain-language event | 4h uptrend remains intact, 1h pullback is normal, and 1h reclaim confirms continuation |
| Event time source | real closed 1h trigger candle confirmation time |
| Invalid event time source | generated_at, report refresh time, file write time, monitor refresh time |
| Freshness window | 1h, or at most until the next 1h candle closes |
| Protection reference | pullback_low_reference must exist |

### CPM-LONG Required Facts

The event may exist only when these facts are true:

```text
htf_trend_intact = true
pullback_depth_normal = true
reclaim_confirmed = true
pullback_low_reference exists
public_facts_ready = true
```

### CPM-LONG Event Time Rule

The event time must be the market confirmation time, not the artifact time.

Required event-time interpretation:

```text
trigger_candle_open_time_utc = the opening time of the 1h candle that confirms reclaim
trigger_candle_close_time_utc = the close time of that 1h candle
event_time_utc = trigger_candle_close_time_utc
```

Reason:

```text
A reclaim is not confirmed when the 1h candle opens.
It is confirmed only when the candle closes.
```

### CPM-LONG Rejection Rule

The chain must reject CPM-LONG when:

```text
4h trend is not up / intact
pullback depth is abnormal
1h reclaim close is not confirmed
pullback_low_reference is missing
event_time_utc is generated_at/report/file time
side is not long
symbol is outside ETHUSDT / SOLUSDT / AVAXUSDT / SUIUSDT
```

### PG Constraint Implication

The target PG design must enforce:

```text
CPM-RO-001 + CPM-LONG + long
-> only allowed symbols
-> only closed 1h market-event time
-> only side-specific CPM long facts
-> only candidate rows that reference the valid live_signal_event
-> only Action-Time Tickets that reference the valid candidate row
```

## Owner Confirmation Round 9 - MPG-LONG Event Spec

Recorded after the Owner confirmed the proposed MPG-LONG event definition.

### Confirmed MPG-LONG Event Definition

| Dimension | Confirmed decision |
| --- | --- |
| Event id | MPG-LONG |
| StrategyGroup | MPG-001 |
| Side | long |
| Candidate symbols | OPUSDT, SOLUSDT, AVAXUSDT, SUIUSDT |
| Plain-language event | 4h context is upward, 1h momentum is persistently positive, and a closed 1h candle confirms continuation/breakout |
| Event time source | real closed 1h momentum-persistence trigger candle confirmation time |
| Invalid event time source | generated_at, report refresh time, file write time, monitor refresh time |
| Freshness window | 1h, or at most until the next 1h candle closes |
| Protection/reference requirement | momentum_floor_reference must exist |
| Required disables | overextension_disable=false and momentum_exhaustion=false |

### MPG-LONG Required Facts

The event may exist only when these facts are true:

```text
htf_trend_up = true
one_hour_momentum_positive = true
breakout_close_confirmed = true
consecutive_higher_closes >= threshold
momentum_floor_reference exists
volume_or_range_confirmation = true
overextension_disable = false
momentum_exhaustion = false
public_facts_ready = true
```

### MPG-LONG Event Time Rule

The event time must be the market confirmation time, not the artifact time.

Required event-time interpretation:

```text
trigger_candle_open_time_utc = the opening time of the 1h candle that confirms momentum persistence
trigger_candle_close_time_utc = the close time of that 1h candle
event_time_utc = trigger_candle_close_time_utc
```

Reason:

```text
MPG-LONG is not confirmed when momentum starts moving.
It is confirmed only when the closed 1h candle proves continuation.
```

### MPG-LONG Rejection Rule

The chain must reject MPG-LONG when:

```text
side is not long
symbol is outside OPUSDT / SOLUSDT / AVAXUSDT / SUIUSDT
1h trigger candle is not closed
event_time_utc is generated_at/report/file time
momentum is only a single spike without persistence
overextension_disable = true
momentum_exhaustion = true
momentum_floor_reference is missing
```

### PG Constraint Implication

The target PG design must enforce:

```text
MPG-001 + MPG-LONG + long
-> only allowed symbols
-> only closed 1h market-event time
-> only side-specific MPG long facts
-> only event rows where overextension and exhaustion disables are false
-> only candidate rows that reference the valid live_signal_event
-> only Action-Time Tickets that reference the valid candidate row
```

## Owner Confirmation Round 10 - MI-LONG Event Spec

Recorded after the Owner confirmed the proposed MI-LONG event definition.

### Confirmed MI-LONG Event Definition

| Dimension | Confirmed decision |
| --- | --- |
| Event id | MI-LONG |
| StrategyGroup | MI-001 |
| Side | long |
| Candidate symbols | AVAXUSDT, ETHUSDT, SOLUSDT |
| Plain-language event | A strong 12h close-to-close momentum impulse appears in an allowed high-beta asset and may continue over later windows |
| Event time source | real closed 1h impulse-confirmation candle time |
| Invalid event time source | generated_at, report refresh time, file write time, monitor refresh time |
| Freshness window | 1h, or at most until the next 1h candle closes |
| Required future hard fact | relative_strength_confirmed must become a hard PG/runtime fact |
| Required disables | momentum_exhaustion=false and fast_reversal_after_impulse=false |

### MI-LONG Required Facts

The event may exist only when these facts are true:

```text
twelve_hour_close_to_close_return_pct >= threshold
closed_1h_candle_count >= 13
symbol_in_allowed_scope = true
relative_strength_confirmed = true
momentum_exhaustion = false
fast_reversal_after_impulse = false
public_facts_ready = true
```

Free-text exceptions such as `explicit_not_required_for_v0` are invalid for
production PG semantics. Only a future versioned event spec or RequiredFacts
version may change this rule.

### MI-LONG Event Time Rule

The event time must be the market confirmation time, not the artifact time.

Required event-time interpretation:

```text
trigger_candle_open_time_utc = the opening time of the latest 1h candle used in the 12h impulse calculation
trigger_candle_close_time_utc = the close time of that 1h candle
event_time_utc = trigger_candle_close_time_utc
```

Reason:

```text
MI-LONG is a 12h close-to-close impulse.
The impulse is confirmed only when the latest 1h candle in the 12h window closes.
```

### MI-LONG Rejection Rule

The chain must reject MI-LONG when:

```text
side is not long
symbol is outside AVAXUSDT / ETHUSDT / SOLUSDT
12h impulse return is below threshold
closed 1h candle count is insufficient
event_time_utc is generated_at/report/file time
relative strength is missing after PG semantics requires it
momentum_exhaustion = true
fast_reversal_after_impulse = true
```

### PG Constraint Implication

The target PG design must enforce:

```text
MI-001 + MI-LONG + long
-> only allowed symbols
-> only closed 1h market-event time
-> only side-specific MI long facts
-> relative_strength_confirmed as a hard fact once PG semantics owns the rule
-> only event rows where exhaustion and fast-reversal disables are false
-> only candidate rows that reference the valid live_signal_event
-> only Action-Time Tickets that reference the valid candidate row
```

## Owner Confirmation Round 11 - SOR-LONG Event Spec

Recorded after the Owner confirmed the proposed SOR-LONG event definition.

### Confirmed SOR-LONG Event Definition

| Dimension | Confirmed decision |
| --- | --- |
| Event id | SOR-LONG |
| StrategyGroup | SOR-001 |
| Side | long |
| Candidate symbols | ETHUSDT, SOLUSDT, AVAXUSDT, BTCUSDT |
| Plain-language event | The session opening range has formed, price breaks above the opening range high, follow-through confirms, and price does not fall back below the invalidation level |
| Event time source | real closed 15m session-breakout confirmation candle time |
| Invalid event time source | candle open time, generated_at, report refresh time, file write time, monitor refresh time |
| Freshness window | 15m, or at most until the next 15m candle closes |
| Lane validity | same session only |
| Required confirmations | follow_through_confirmed=true and invalidation_level_held=true |

### SOR-LONG Required Facts

The event may exist only when these facts are true:

```text
session_window_active = true
closed_opening_range = true
opening_range_high exists
opening_range_low exists
breakout_level_crossed = true
follow_through_confirmed = true
invalidation_level_held = true
post_open_decay_clear = true
liquidity_ok = true
funding_not_extreme = true
public_facts_ready = true
```

### SOR-LONG Event Time Rule

The event time must be the market confirmation time, not the candle open time or
artifact time.

Required event-time interpretation:

```text
trigger_candle_open_time_utc = the opening time of the 15m candle that confirms the session breakout
trigger_candle_close_time_utc = the close time of that 15m candle
event_time_utc = trigger_candle_close_time_utc
```

Reason:

```text
SOR-LONG is a closed-candle session breakout.
The breakout is confirmed only when the 15m candle closes above the opening range high and follow-through/invalidation facts hold.
```

### SOR-LONG Rejection Rule

The chain must reject SOR-LONG when:

```text
side is not long
symbol is outside ETHUSDT / SOLUSDT / AVAXUSDT / BTCUSDT
opening range is not closed
15m trigger candle is not closed
breakout is only an intrabar wick
follow_through_confirmed = false
invalidation_level_held = false
post_open_decay_active = true
event_time_utc is candle open time or generated_at/report/file time
signal is outside the same session validity window
```

### PG Constraint Implication

The target PG design must enforce:

```text
SOR-001 + SOR-LONG + long
-> only allowed symbols
-> only closed 15m market-event time
-> only same-session valid candidates
-> only side-specific SOR long breakout facts
-> only event rows where follow-through and invalidation facts are true
-> only candidate rows that reference the valid live_signal_event
-> only Action-Time Tickets that reference the valid candidate row
```

## Owner Confirmation Round 12 - SOR-SHORT Event Spec

Recorded after the Owner confirmed the proposed SOR-SHORT event definition.

### Confirmed SOR-SHORT Event Definition

| Dimension | Confirmed decision |
| --- | --- |
| Event id | SOR-SHORT |
| StrategyGroup | SOR-001 |
| Side | short |
| Candidate symbols | ETHUSDT, SOLUSDT, AVAXUSDT, BTCUSDT |
| Plain-language event | The session opening range has formed, price breaks below the opening range low, bearish follow-through confirms, and price does not reclaim the invalidation level |
| Event time source | real closed 15m session-breakdown confirmation candle time |
| Invalid event time source | candle open time, generated_at, report refresh time, file write time, monitor refresh time |
| Freshness window | 15m, or at most until the next 15m candle closes |
| Lane validity | same session only |
| Required confirmations | bearish_follow_through_confirmed=true and reclaim_not_confirmed=true |

### Timeframe Decision

The Owner confirmed option A:

```text
SOR-SHORT uses 15m session breakdown.
```

This means SOR-LONG and SOR-SHORT share one event family:

```text
closed 15m session opening-range event
```

The older 1h short evaluator remains useful as historical/reference context,
but it must not become the final PG authority for SOR-SHORT unless a separate
future event such as SOR-SHORT-1H is explicitly created.

### SOR-SHORT Required Facts

The event may exist only when these facts are true:

```text
session_window_active = true
closed_opening_range = true
opening_range_high exists
opening_range_low exists
breakdown_level_crossed = true
bearish_follow_through_confirmed = true
reclaim_not_confirmed = true
invalidation_level_held = true
post_open_decay_clear = true
liquidity_ok = true
funding_not_extreme = true
public_facts_ready = true
```

### SOR-SHORT Event Time Rule

The event time must be the market confirmation time, not the candle open time or
artifact time.

Required event-time interpretation:

```text
trigger_candle_open_time_utc = the opening time of the 15m candle that confirms the session breakdown
trigger_candle_close_time_utc = the close time of that 15m candle
event_time_utc = trigger_candle_close_time_utc
```

Reason:

```text
SOR-SHORT is a closed-candle session breakdown.
The breakdown is confirmed only when the 15m candle closes below the opening range low and bearish follow-through/reclaim facts hold.
```

### SOR-SHORT Rejection Rule

The chain must reject SOR-SHORT when:

```text
side is not short
symbol is outside ETHUSDT / SOLUSDT / AVAXUSDT / BTCUSDT
opening range is not closed
15m trigger candle is not closed
breakdown is only an intrabar wick
bearish_follow_through_confirmed = false
reclaim_not_confirmed = false
invalidation_level_held = false
post_open_decay_active = true
event_time_utc is candle open time or generated_at/report/file time
signal is outside the same session validity window
```

### PG Constraint Implication

The target PG design must enforce:

```text
SOR-001 + SOR-SHORT + short
-> only allowed symbols
-> only closed 15m market-event time
-> only same-session valid candidates
-> only side-specific SOR short breakdown facts
-> only event rows where bearish follow-through and no-reclaim facts are true
-> only candidate rows that reference the valid live_signal_event
-> only Action-Time Tickets that reference the valid candidate row
```

## Owner Confirmation Round 13 - BRF2-SHORT Event Spec

Recorded after the Owner confirmed the proposed BRF2-SHORT event definition.

### Confirmed BRF2-SHORT Event Definition

| Dimension | Confirmed decision |
| --- | --- |
| Event id | BRF2-SHORT |
| StrategyGroup | BRF2-001 |
| Side | short |
| Candidate symbols | BTCUSDT, AVAXUSDT, ETHUSDT |
| Plain-language event | A weak or non-strong-uptrend market rallies, the rally fails, rejection/follow-through confirms, and short-squeeze risk remains acceptable |
| Event time source | real closed 1h rally-failure confirmation candle time |
| Invalid event time source | candle open time, generated_at, report refresh time, file write time, monitor refresh time |
| Freshness window | 1h, or at most until the next 1h candle closes |
| Required context | strong_htf_uptrend=false |
| Required squeeze boundary | squeeze_risk_extreme=false |
| Required protection/reference | rally_high_reference must exist |

### BRF2-SHORT Required Facts

The event may exist only when these facts are true:

```text
strong_htf_uptrend = false
rally_extension_confirmed = true
rejection_confirmed = true
failure_reversal_confirmed = true
rally_high_reference exists
short_squeeze_risk_reviewed = true
squeeze_risk_extreme = false
liquidity_ok = true
funding_not_extreme = true
public_facts_ready = true
```

### BRF2-SHORT Event Time Rule

The event time must be the market confirmation time, not the candle open time or
artifact time.

Required event-time interpretation:

```text
trigger_candle_open_time_utc = the opening time of the 1h candle that confirms rally failure
trigger_candle_close_time_utc = the close time of that 1h candle
event_time_utc = trigger_candle_close_time_utc
```

Reason:

```text
BRF2-SHORT is not "price went down, so short".
It is confirmed only when a closed 1h candle proves rally failure/rejection and squeeze-risk facts remain acceptable.
```

### BRF2-SHORT Rejection Rule

The chain must reject BRF2-SHORT when:

```text
side is not short
symbol is outside BTCUSDT / AVAXUSDT / ETHUSDT
strong_htf_uptrend = true
rally_extension_confirmed = false
rejection_confirmed = false
failure_reversal_confirmed = false
squeeze_risk_extreme = true
rally_high_reference is missing
1h trigger candle is not closed
event_time_utc is candle open time or generated_at/report/file time
```

### PG Constraint Implication

The target PG design must enforce:

```text
BRF2-001 + BRF2-SHORT + short
-> only allowed symbols
-> only closed 1h market-event time
-> only side-specific BRF2 short rally-failure facts
-> only event rows where strong-uptrend and squeeze-extreme blockers are false
-> only event rows with rally_high_reference
-> only candidate rows that reference the valid live_signal_event
-> only Action-Time Tickets that reference the valid candidate row
```

## Owner Confirmation Round 14 - PG Event Constraint Layer

Recorded after the Owner confirmed the proposed PG event constraint layer.

### Confirmed PG Event Constraint Direction

The event-driven Fresh Signal model must be represented as PG-enforced
constraints, not as informal strings in files or generated JSON.

Confirmed new or strengthened concepts:

| PG concept | Confirmed role |
| --- | --- |
| `brc_strategy_side_event_specs` | Defines allowed StrategyGroup + side + event_id specs |
| `brc_strategy_event_required_facts` | Defines required facts and disable facts for each event spec |
| `brc_candidate_scope_event_bindings` | Binds allowed candidate scopes to allowed event specs |
| `brc_live_signal_events` | Stores real market event occurrences and must reference event spec/scope/facts |
| `brc_promotion_candidates` | Must reference a valid live signal event for event-backed promotion |
| `brc_action_time_lane_inputs` | Must reference valid promotion and signal lineage for action-time paths |

### Required Event Spec Rows

The target PG seed/migration must create these current event specs:

| Event id | StrategyGroup | Side | Symbols | Event time |
| --- | --- | --- | --- | --- |
| CPM-LONG | CPM-RO-001 | long | ETHUSDT, SOLUSDT, AVAXUSDT, SUIUSDT | closed 1h candle close time |
| MPG-LONG | MPG-001 | long | OPUSDT, SOLUSDT, AVAXUSDT, SUIUSDT | closed 1h candle close time |
| MI-LONG | MI-001 | long | AVAXUSDT, ETHUSDT, SOLUSDT | closed 1h candle close time |
| SOR-LONG | SOR-001 | long | ETHUSDT, SOLUSDT, AVAXUSDT, BTCUSDT | closed 15m candle close time |
| SOR-SHORT | SOR-001 | short | ETHUSDT, SOLUSDT, AVAXUSDT, BTCUSDT | closed 15m candle close time |
| BRF2-SHORT | BRF2-001 | short | BTCUSDT, AVAXUSDT, ETHUSDT | closed 1h candle close time |

### Required Live Signal Event Strengthening

`brc_live_signal_events` must not rely on a free-text `signal_type` alone.

Required fields or equivalent constraints:

```text
event_spec_id
candidate_scope_id
event_id
event_time_ms
trigger_candle_open_time_ms
trigger_candle_close_time_ms
fact_snapshot_id
```

Required invariant:

```text
event_time_ms = trigger_candle_close_time_ms
```

for the six confirmed event specs above.

### Required Candidate/Action-Time Lineage

The chain must enforce:

```text
no event spec -> no live signal event
no live signal event -> no promotion candidate
no promotion candidate -> no action-time lane input
no action-time lane input -> no Action-Time Ticket
```

This means event-backed promotion and action-time paths must not allow nullable
lineage for:

```text
signal_event_id
promotion_candidate_id
candidate_scope_id
event_spec_id
```

where the lane is intended for action-time rehearsal, live-submit candidate, or
real-submit candidate.

### Required Rejection Rules

The PG-backed chain must reject:

```text
unsupported StrategyGroup + side
unsupported StrategyGroup + symbol
unsupported candidate_scope_id + event_spec_id
generated_at/report/file/monitor time as event_time_ms
candidate rows without signal_event_id
action-time rows without promotion_candidate_id or signal_event_id
event rows whose facts do not match the side-specific event spec
```

### Current Design Gap To Patch Later

Current `RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` already has broad tables for
candidate scope, fact snapshots, live signal events, promotion candidates, and
action-time lane inputs, but it does not yet explicitly define:

```text
brc_strategy_side_event_specs
brc_strategy_event_required_facts
brc_candidate_scope_event_bindings
```

It also does not yet make event identity and event-backed lineage strong enough
for the Owner-confirmed L2-L7 reset.

## Owner Confirmation Round 15 - Action-Time Ticket

Recorded after the Owner confirmed the proposed Action-Time Ticket model.

### Confirmed Action-Time Ticket Direction

The system must introduce a formal machine ticket for the exact candidate trade:

```text
brc_action_time_tickets
```

Plain-language meaning:

```text
This ticket is the machine identity of "which exact trade is being checked".
```

It is distinct from `brc_action_time_lane_inputs`:

| Concept | Meaning |
| --- | --- |
| `brc_action_time_lane_inputs` | Which opportunity entered the action-time lane |
| `brc_action_time_tickets` | The exact candidate trade identity that FinalGate may inspect |

### Required Ticket Lineage

An Action-Time Ticket must bind:

```text
action_time_lane_input_id
promotion_candidate_id
signal_event_id
event_spec_id
candidate_scope_id
runtime_scope_binding_id
strategy_group_id
symbol
side
event_id
event_time_ms
trigger_candle_close_time_ms
runtime_profile_id
public_fact_snapshot_id
action_time_fact_snapshot_id
account_safe_fact_snapshot_id
notional
leverage
protection_ref
expires_at_ms
status
authority_boundary
ticket_hash
```

### Required Ticket Invariants

The target PG design must enforce:

```text
no action_time_lane_input -> no ticket
no promotion_candidate -> no ticket
no signal_event -> no ticket
no event_spec -> no ticket
strategy_group / symbol / side / event_id are consistent across lineage refs
event_time_ms = trigger_candle_close_time_ms
generated_at / report / file / monitor time cannot be event_time_ms
one open action_time_lane_input has at most one active ticket
ticket cannot create orders
ticket cannot bypass FinalGate
ticket cannot bypass Operation Layer
```

### FinalGate Source Rule

FinalGate must consume the Action-Time Ticket identity.

Confirmed rule:

```text
FinalGate may inspect a ticket_id.
FinalGate must not directly consume Candidate Pool rows as trade identity.
FinalGate must not directly consume loose live_signal_events as trade identity.
FinalGate must not directly consume JSON artifacts as trade identity.
```

### Authority Boundary

An Action-Time Ticket is not order authority.

It may unlock:

```text
non-executing preflight
candidate/auth evidence checking
FinalGate inspection
```

It must not unlock:

```text
FinalGate bypass
Operation Layer bypass
exchange write
order creation
live profile expansion
order sizing expansion
```

### Current Design Gap To Patch Later

Current `brc_action_time_lane_inputs` is necessary but insufficient because it
does not fully answer:

```text
which exact candidate trade is this?
```

The target design must add `brc_action_time_tickets` and make later execution
preflight consume ticket identity instead of reconstructing trade identity from
multiple generated artifacts or loose projection rows.

## Owner Confirmation Round 16 - Old Semantics Must Be Deleted Or Rewritten

Recorded after the Owner corrected the migration stance: old incompatible
semantics must not be merely downgraded, deprecated, or treated as lower
priority.

### Confirmed Rule

Incompatible old StrategyGroup side/symbol/event semantics must be deleted or
rewritten.

Invalid compromise:

```text
Keep old semantics as lower-priority source
Keep old supported_sides but let PG override it
Keep DEFAULT_SIDE_SCOPE but mark it legacy
Keep old tests but add new tests beside them
Keep old JSON as diagnostic source that can still shape runtime scope
```

Required direction:

```text
Remove or rewrite incompatible old semantics.
Remove or rewrite incompatible old tests.
Remove or rewrite broad DEFAULT_SIDE_SCOPE behavior.
Make PG event specs and bindings the only current runtime semantics source.
Do not preserve a second semantic path that can later re-expand scope.
```

### Stronger Migration Interpretation

The earlier "fail closed" language is only acceptable as an import-time safety
behavior while incompatible input is being removed.

The final accepted target is stronger:

```text
old incompatible source appears
-> migration/import fails
-> source must be deleted or rewritten
-> no runtime path keeps reading it as current truth
```

### Known Old Semantics To Remove Or Rewrite

The current codebase contains examples that conflict with the Owner-confirmed
L2-L7 event model:

| Source | Current old shape | Required action |
| --- | --- | --- |
| `src/domain/strategy_semantics.py` | MI-001 and BRF2-001 still list `supported_sides=["long", "short"]` | Rewrite to confirmed side/event semantics |
| `scripts/runtime_active_observation_monitor.py` | `DEFAULT_SIDE_SCOPE` grants all WIP lanes long/short | Remove from main path; read PG bindings |
| `scripts/build_strategy_live_candidate_pool.py` | broad `DEFAULT_SIDE_SCOPE` and partial side overrides | Remove broad fallback; require event-bound candidate scope |
| `tests/unit/test_b0_strategy_semantics_binding.py` | asserts CPM supports long/short | Rewrite to assert CPM-LONG only and reject CPM short |
| `tests/unit/test_bootstrap_strategygroup_runtime_pilot.py` | expects missing MPG short runtime to bootstrap | Rewrite to reject MPG short as unsupported |

### No Compatibility Escape Hatch

The target architecture must not keep a long-term compatibility path where:

```text
PG says one thing
legacy code/constants/docs say another
runtime chooses based on availability or fallback
```

For the L2-L7 reset, incompatible legacy semantics are not lower authority.
They are defects to remove.

### Acceptance Meaning

PG化 is accepted only when:

```text
current runtime/trading decisions do not depend on old MD/JSON/code side scope
unsupported sides cannot be emitted by seed/import/projector/runtime builders
old tests no longer encode forced long/short mirroring
legacy exports cannot expand symbol/side/event scope
```

## Owner Confirmation Round 17 - PG And Code Responsibility Split

Recorded after the Owner confirmed the proposed PG/code responsibility split
and identified that it makes the chain clearer and each responsibility more
single-purpose.

### Confirmed Responsibility Split

The target L2-L7 chain should use this separation:

```text
PG defines whether something is allowed.
Code computes whether market facts/events exist.
Projection summarizes current state.
Ticket fixes the exact candidate trade identity.
FinalGate checks whether the ticket can proceed.
Operation Layer performs the official submit path only after gates pass.
```

### Plain-Language Meaning

The system should no longer allow runtime builders to invent scope from code
fallbacks, generated files, or old semantics.

Correct shape:

```text
PG says MPG-001 + OPUSDT + long + MPG-LONG is allowed.
Evaluator computes whether MPG-LONG occurred.
Candidate Pool promotes only the event-backed candidate.
Action-Time Ticket records the exact trade identity.
FinalGate checks that ticket.
Operation Layer submits only if the official path passes.
```

Incorrect shape:

```text
Code sees DEFAULT_SIDE_SCOPE=("long", "short").
Code creates MPG short scope.
Candidate Pool treats it as available.
FinalGate later has to guess whether that side was allowed.
```

### Confirmed Layer Duties

| Layer | Confirmed responsibility | Forbidden responsibility |
| --- | --- | --- |
| PG event specs | Define allowed StrategyGroup + side + event_id + timeframe + freshness | Compute market facts |
| PG candidate scope | Define allowed StrategyGroup + symbol + side scope | Expand from old JSON or fallback constants |
| Evaluator/detector code | Compute facts and detect event occurrences | Decide supported side/symbol/event scope |
| Candidate Pool | Consume only PG-authorized event-backed live signals | Promote fallback or generic signals |
| Action-Time Ticket | Persist exact candidate trade identity | Create orders or bypass gates |
| FinalGate | Check a ticket against safety facts and authority | Reinterpret strategy semantics or read loose JSON as trade identity |
| Operation Layer | Submit through official path after gates pass | Accept direct signal/candidate JSON as submit authority |

### Architecture Simplification

The confirmed design is simpler because each layer answers one question:

| Question | Owning layer |
| --- | --- |
| Is this strategy/symbol/side/event allowed? | PG event/scope constraints |
| Did the market event happen? | Evaluator/detector |
| Is this candidate closest to action-time? | Candidate Pool projection |
| Which exact trade is being checked? | Action-Time Ticket |
| Is this exact trade safe and authorized to proceed? | FinalGate |
| Should an order be submitted through the official path? | Operation Layer |

This replaces the current mixed model where JSON files, code constants,
generated projections, and runtime scripts can all partially answer the same
question.

## Owner Confirmation Round 18 - Projection Layer Boundary

Recorded after the Owner confirmed the projection-layer recommendation.

### Confirmed Projection Rule

Projection layers are read models only.

They may summarize PG-backed current state, but they must not become a second
decision system.

Confirmed rule:

```text
Daily Table
Candidate Pool
Goal Status
Server Monitor
Owner Console projections
```

must not decide:

```text
which StrategyGroup supports which side
which symbol is authorized
which event_id is allowed
whether generated_at is a signal time
whether unsupported side can be bootstrapped
whether old JSON should override PG current state
```

### Projection Duties

Projection layers may answer:

```text
what is currently running
what is currently waiting
what fresh event exists
which candidate is closest
which blocker is first
which ticket is active
whether Owner action is required
```

They must compute those answers from PG-owned current state:

```text
strategy/event specs
candidate scope bindings
runtime scope bindings
watcher coverage
fact snapshots
live signal events
promotion candidates
action-time tickets
runtime safety state
```

### Invalid Projection Behavior

The target architecture must reject projection behavior like:

```text
Candidate Pool creates a side because DEFAULT_SIDE_SCOPE says long/short.
Goal Status reports scope mismatch from old pilot JSON after PG coverage is current.
Daily Table reads stale latest-* files and changes first blocker.
Server Monitor treats file refresh time as signal freshness.
Owner Console infers tradeability from generated JSON instead of PG current projection.
```

### Current Projection Ownership Rule

Every current projection must have exactly one owner projector.

Required shape:

```text
one model_type + one projection_scope_key -> one owner_projector
```

Projection outputs may still export JSON/MD for audit or compatibility, but
those exports are not runtime/trading truth.

### Plain-Language Summary

The confirmed chain is:

```text
PG decides what is allowed.
Code computes what happened.
Projection explains where the system is.
Ticket identifies the exact candidate trade.
FinalGate checks the ticket.
Operation Layer submits only through the official path.
```

## Owner Confirmation Round 19 - PG Migration Acceptance And Old Source Disposition

Recorded after the Owner confirmed the PG migration acceptance direction and
corrected the handling of old semantics.

### Confirmed Acceptance Standard

PG migration must be accepted by constraint behavior, not by the mere existence
of tables, scripts, exports, or passing happy-path tests.

The target chain must prove:

```text
unsupported side cannot enter the chain
unsupported symbol cannot enter the chain
unsupported event_id cannot enter the chain
generated_at/report/file/monitor time cannot become event_time_ms
no event spec -> no live signal event
no live signal event -> no promotion candidate
no promotion candidate -> no Action-Time Ticket
no Action-Time Ticket -> no FinalGate input
Projection layers cannot re-decide semantics or override PG current state
```

### Confirmed Old Source Handling

Old semantics, old JSON/MD, old constants, and old tests must be classified by
whether they have reusable value.

Required rule:

```text
valuable old content -> convert into the new PG/event/ticket model
non-valuable or conflicting old content -> delete, clean, or archive
old content must not remain as runtime/trading decision source
```

### Invalid Old Source Handling

The target architecture must not:

```text
keep old semantics as a lower-priority runtime source
keep old side/symbol defaults as fallback
keep old JSON as a current control-plane input
keep old tests that encode forced mirroring
keep old code paths that can silently expand symbol/side/event scope
```

### Required Migration Disposition Categories

Every old source touched by the migration must be classified into exactly one
of these outcomes:

| Outcome | Meaning | Runtime authority |
| --- | --- | --- |
| convert | Valuable semantics are rewritten into PG event specs, required facts, candidate scope, or ticket constraints | New PG model only |
| delete | Conflicting or obsolete code/test/file is removed | None |
| clean | Existing source is rewritten so it no longer expresses obsolete semantics | New PG model only |
| archive | Historical evidence is preserved outside current runtime authority | None |

No source may stay in a mixed state where it is both historical and current.

### Negative Acceptance Tests

The migration must include negative tests proving at least:

```text
CPM-RO-001 short -> rejected
MPG-001 short -> rejected
MI-001 short -> rejected
BRF2-001 long -> rejected
SOR-001 generic fresh signal without SOR-LONG or SOR-SHORT -> rejected
generated_at as event_time_ms -> rejected
live_signal_event without event_spec_id -> rejected
promotion_candidate without signal_event_id -> rejected
action_time_ticket without promotion_candidate_id -> rejected
FinalGate preflight without ticket_id -> rejected
```

### Plain-Language Acceptance Meaning

PG化 is not complete until the system no longer requires the Owner to ask:

```text
which coin can enter?
which side can enter?
which event triggered?
which market time proves it?
why was there no ticket?
what exact trade is FinalGate checking?
```

Those answers must be enforced by PG constraints and the Action-Time Ticket
lineage.

## Owner Confirmation Round 20 - Durable Document Landing

Recorded after the Owner confirmed the proposed durable documentation landing
plan.

### Confirmed Landing Rule

This temporary document must not become a long-term authority document by
accident.

Confirmed flow:

```text
temporary grilling draft
-> final summary
-> split into existing durable project constraints
-> update PG table design
-> update agent/worker constraints
-> issue PG implementation task prompt
```

### Durable Landing Targets

| Confirmed content | Durable target |
| --- | --- |
| L2-L7 responsibility split | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| Strategy side/symbol/event semantics | `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` and PG event seed specification |
| PG event/ticket constraints | `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| Projection read-model boundary | `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md` |
| Old MD/JSON/code source cleanup | `docs/current/REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md` |
| Agent and worker execution constraints | `docs/current/AI_AGENT_CONSTRAINTS.md` and `CLAUDE.md` |
| Owner-facing operating language | `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |

### Temporary Document Authority Boundary

This file remains:

```text
working draft
conversation ledger
pre-final synthesis source
```

It must not remain as:

```text
runtime source of truth
PG migration authority after durable docs are updated
parallel strategy contract
parallel agent instruction contract
```

### Finalization Requirement

Before PG implementation is issued as a task, Codex must produce a final
summary that maps every confirmed decision in this temporary draft into its
durable target document or explicitly marks it as temporary-only context.

## Owner Confirmation Round 21 - PG Execution Boundary

Recorded after the Owner confirmed the proposed PG execution boundary.

### Confirmed Execution Boundary

PG化 must replace the current L2-L7 runtime decision path, not run beside it as
a long-term parallel path.

Confirmed rule:

```text
L2-L7 current truth moves to PG.
JSON/MD becomes export only.
Old code constants cannot decide runtime scope.
Old supported_sides cannot decide runtime side.
Old artifacts cannot decide signal, candidate, ticket, or FinalGate identity.
FinalGate consumes Action-Time Ticket identity.
```

### Must-Close Same-Batch Chain

The PG migration must close these layers as one coherent chain:

| Layer | Confirmed requirement |
| --- | --- |
| L2 Candidate Universe | PG defines allowed StrategyGroup + symbol + side + event |
| L3 Runtime Coverage | watcher coverage binds to PG candidate scope |
| L4 Market Facts | fact snapshots bind to StrategyGroup + symbol + side + event context |
| L5 Fresh Signal | live signal events bind event spec and real market event time |
| L6 Candidate Pool | promotion consumes only PG live signal events |
| L7 Action-Time Ticket | ticket binds signal, promotion, lane, profile, facts, notional/leverage, and protection refs |
| Projection | Daily Table, Goal Status, Monitor, and Owner surfaces summarize PG current projections only |

### Rejected Transitional Shapes

The target design must reject:

```text
PG tables exist but Candidate Pool still reads JSON as the main source.
PG event specs exist but DEFAULT_SIDE_SCOPE still creates long/short scope.
PG tickets exist but FinalGate can still consume loose JSON identity.
PG scope exists but watcher still reads Candidate Pool export as its universe.
PG facts exist but generated_at can still become event_time_ms.
PG chain exists but old file/code chain remains a runtime fallback.
```

### Replacement Principle

The implementation principle is:

```text
replace, not parallel
```

Plain-language meaning:

```text
Replace the old runtime decision chain.
Do not preserve two active chains that can disagree.
```

## Owner Confirmation Round 22 - Historical Signal Boundary

Recorded after the Owner confirmed the boundary for historical, replay, and old
artifact signals.

### Confirmed Rule

Historical replay events, old JSON detector outputs, old artifacts, and old
missed opportunities must not become current fresh live signal events.

Confirmed separation:

```text
live_signal_events = current server/live detector events only
historical/replay evidence = strategy review and event-spec calibration only
```

### Live Signal Event Boundary

`brc_live_signal_events` may represent a fresh signal only when:

```text
server watcher or live detector produced it
current real market data produced it
event_time_ms is a real market event time
event_time_ms is inside the event's freshness window
status = facts_validated
freshness_state = fresh
event_spec_id and candidate_scope_id are valid
```

### Historical Evidence Boundary

Historical/replay signals may be converted into:

```text
strategy review evidence
event specification calibration samples
replay parity diagnostics
strategy promote / revise / park / kill evidence
```

They must not be converted into:

```text
fresh live_signal_events
promotion_candidates
action_time_tickets
FinalGate input
Operation Layer input
```

### Required Historical Evidence Tables Or Equivalent

The target PG design should keep historical learning separate from current live
actionability through tables such as:

```text
brc_strategy_event_replay_evidence
brc_strategy_event_calibration_samples
brc_strategy_review_evidence
```

Names may change during final table design, but the authority boundary must not
change.

### Required Rejection Rules

The PG-backed chain must reject:

```text
replay event -> live_signal_event with status=facts_validated and freshness_state=fresh
historical event -> promotion_candidate
historical event -> action_time_ticket
generated replay timestamp -> live freshness
review evidence -> FinalGate input
review evidence -> Operation Layer input
```

### Plain-Language Meaning

Historical evidence can teach the strategy what to look for next.

It cannot tell the runtime:

```text
trade now
```

## Owner Confirmation Round 23 - Runtime Coverage Boundary

Recorded after the Owner confirmed the runtime coverage recommendation.

### Confirmed Rule

Runtime Coverage must be PG-backed and event-aware.

Confirmed direction:

```text
watcher reads PG candidate scope and event bindings
-> watcher covers exact StrategyGroup + symbol + side + event spec
-> watcher writes coverage proof back into PG
-> projection exports may summarize coverage
```

The watcher must not infer observation scope from generated JSON exports,
Candidate Pool files, old code defaults, or stale strategy semantics.

### Plain-Language Meaning

Runtime Coverage means:

```text
服务器确实在看这条策略、这个币、这个方向、这个事件。
```

It is not enough to say:

```text
服务器在跑一个 watcher
```

The required proof must be precise:

```text
CPM-RO-001 + ETHUSDT + long + CPM-LONG is covered
MPG-001 + OPUSDT + long + MPG-LONG is covered
SOR-001 + ETHUSDT + short + SOR-SHORT is covered
```

### Required Coverage Grain

The target PG model must track coverage at least at this grain:

```text
strategy_group_id
symbol
side
event_spec_id
candidate_scope_id
runtime_instance_id
watcher_instance_id
coverage_status
last_seen_at_ms
coverage_heartbeat_at_ms
coverage_source
```

Exact column names may change, but the authority boundary must not change.

### Required Rejection Rules

The PG-backed chain must reject promotion or action-time progression when:

```text
no runtime coverage exists for the exact StrategyGroup + symbol + side + event spec
coverage only exists for the opposite side
coverage only exists for a different event spec
coverage only exists in JSON export but not PG
coverage is stale beyond the accepted heartbeat window
coverage was inferred from Candidate Pool output instead of PG bindings
```

### Watcher Scope Source Rule

The production watcher must use:

```text
brc_candidate_scope_event_bindings
brc_runtime_scope_bindings
brc_strategy_side_event_specs
```

or their final equivalent tables as its source of observation scope.

It must not use:

```text
latest-strategy-live-candidate-pool.json
latest-daily-live-enablement-table.json
old DEFAULT_SIDE_SCOPE constants
old supported_sides defaults
repo MD files
Codex-generated task packets
```

as runtime scope authority.

### Projection Boundary

Candidate Pool, Daily Table, Goal Status, Server Monitor, and Owner Console may
display runtime coverage state, but they must not create coverage authority.

Correct flow:

```text
PG scope/event bindings
-> watcher observes exact scope
-> watcher writes PG coverage proof
-> projections summarize PG coverage
```

Incorrect flow:

```text
Candidate Pool JSON says a symbol is interesting
-> watcher starts treating it as covered
-> action-time chain accepts it
```

### PG Constraint Implication

The target PG design must make this invariant enforceable:

```text
no PG-backed runtime coverage for exact scope/event
-> no promotion candidate
-> no action-time lane input
-> no Action-Time Ticket
```

## Owner Confirmation Round 24 - Event-Specific Fact Snapshot Boundary

Recorded after the Owner confirmed the Fact Snapshot / RequiredFacts
recommendation.

### Confirmed Rule

Fact Snapshot must be event-specific, side-specific, symbol-specific, and
PG-backed.

Confirmed direction:

```text
event spec defines RequiredFacts
-> evaluator computes event-specific facts
-> fact snapshot binds exact StrategyGroup + symbol + side + event spec
-> live signal event references that snapshot
-> promotion candidate references the live signal event
-> action-time lane input references the promotion
-> Action-Time Ticket references fresh action-time snapshots
```

### Plain-Language Meaning

Fact Snapshot means:

```text
系统判断“这次机会是否成立”时使用的那一份事实记录。
```

It must answer:

```text
哪个策略
哪个币
哪个方向
哪个事件
哪根触发K线
哪些事实满足
哪些事实不满足
这份事实是否仍然新鲜
```

### Required Snapshot Layers

The target model must separate at least two snapshot layers:

| Snapshot layer | Chinese name | Responsibility |
| --- | --- | --- |
| `public_fact_snapshot` | 公开市场事实快照 | Proves whether the strategy event happened |
| `action_time_fact_snapshot` | 交易前事实快照 | Proves whether the candidate remains safe and executable near submit time |

Additional account-safe / exchange-safe snapshots may exist, but they must
remain bound to the same ticket lineage rather than becoming loose JSON facts.

### Required Binding Grain

Every promotion-capable public fact snapshot must bind:

```text
strategy_group_id
symbol
side
event_spec_id
event_id
event_time_ms
trigger_candle_close_time_ms
fact_snapshot_id
freshness_window
```

Every action-time fact snapshot used for a ticket must bind:

```text
action_time_lane_input_id
promotion_candidate_id
signal_event_id
candidate_scope_id
runtime_profile_id
account / position / open-order safety refs
notional / leverage / protection refs
snapshot_time_ms
expires_at_ms
```

Exact column names may change in final table design, but the lineage and
authority boundary must not change.

### Required Rejection Rules

The PG-backed chain must reject:

```text
no event-specific fact snapshot -> no live signal event
no live signal event -> no promotion candidate
no promotion candidate -> no action-time lane input
no fresh action-time fact snapshot -> no Action-Time Ticket
fact side does not match event side -> reject
fact event_spec_id does not match signal event_spec_id -> reject
stale public facts -> reject promotion
stale action-time facts -> reject ticket or FinalGate preflight
FinalGate reading loose JSON facts instead of ticket-bound snapshot ids -> reject
```

### Strategy-Specific Fact Grain

The current active StrategyGroups must use this fact grain:

| StrategyGroup | Required fact grain |
| --- | --- |
| CPM-RO-001 | CPM-LONG / long / closed 1h reclaim confirmation facts |
| MPG-001 | MPG-LONG / long / closed 1h momentum persistence facts |
| MI-001 | MI-LONG / long / 12h impulse facts anchored by latest closed 1h candle |
| SOR-001 | SOR-LONG or SOR-SHORT / closed 15m session event facts |
| BRF2-001 | BRF2-SHORT / short / closed 1h rally-failure facts |

### PG Constraint Implication

RequiredFacts should be owned by event specs, not by generated reports.

Target shape:

```text
brc_strategy_side_event_specs
-> brc_strategy_event_required_facts
-> brc_fact_snapshots
-> brc_live_signal_events
-> brc_promotion_candidates
-> brc_action_time_lane_inputs
-> brc_action_time_tickets
```

### Current Design Gap To Patch Later

Current code and artifacts can still let different consumers interpret facts
from different files or generated summaries. The PG migration must remove that
mixed-source behavior.

Required target:

```text
downstream layers reference fact_snapshot_id
downstream layers do not reconstruct trade facts from repo MD / JSON / output files
```

## Owner Confirmation Round 25 - Promotion Arbitration Boundary

Recorded after the Owner confirmed the promotion arbitration recommendation.

### Confirmed Rule

Multiple live signals and promotion candidates may coexist, but only one
real-submit action-time lane may be open for the same account / runtime profile
scope.

Confirmed direction:

```text
multiple live_signal_events may exist
multiple promotion_candidates may exist
PG-backed arbitration selects the real-submit candidate
at most one open real_submit_candidate action-time lane exists
projections display the arbitration result
```

### Plain-Language Meaning

The market may produce several opportunities at the same time:

```text
SOR-001 / ETHUSDT / long
MPG-001 / SOLUSDT / long
BRF2-001 / BTCUSDT / short
```

The system may record all valid opportunities, but the narrow path near real
submit must select one exact candidate.

This prevents:

```text
multiple candidates fighting for the same capital
multiple candidates reaching FinalGate without one exact trade identity
duplicate submit risk
unclear Owner-facing explanation of which trade was checked
```

### Required Arbitration Shape

Promotion arbitration must be deterministic and PG-backed.

Recommended priority order:

| Priority | Chinese name | Meaning |
| ---: | --- | --- |
| 1 | 硬安全排除 | Reject active position conflict, open-order conflict, unsupported scope, stale facts |
| 2 | 事件新鲜度 | Prefer the candidate with the freshest valid market event |
| 3 | 策略优先级 | Use Owner / PG strategy priority policy |
| 4 | 信号质量分 | Use strategy-specific signal strength only after hard eligibility |
| 5 | 资金占用适配 | Prefer candidates whose notional / leverage / protection can close cleanly |
| 6 | 稳定排序 | Use deterministic event_time / strategy_group_id / symbol / side tie-breaker |

Exact scoring formulas may change, but the arbitration must not depend on JSON
refresh order or nondeterministic watcher timing.

### Lane Scope Requirement

`brc_action_time_lane_inputs` or its final equivalent must distinguish lane
scope.

Required scopes:

```text
rehearsal
paper
real_submit_candidate
```

Plain-language meaning:

```text
非执行演练可以更宽。
真实提交前候选必须非常窄。
```

Rehearsal / paper lanes must not masquerade as real-submit lanes.

### Required PG Constraint

The target PG design must enforce an equivalent of:

```text
partial unique:
  same account / runtime profile / authority scope
  status in opened / facts_refreshing / ticket_pending / ticket_created
  lane_scope = real_submit_candidate
  -> at most one row
```

These statuses are the only real-submit lane states that may proceed toward
ticket creation, FinalGate preflight, or real order action.

### Required Rejection Rules

The PG-backed chain must reject:

```text
Candidate Pool JSON deciding the real-submit lane by itself
Daily Table rank becoming trade authority
Goal Status opening a lane because fresh_signal=true
multiple open real_submit_candidate lanes in the same account/profile scope
old artifact opportunity competing with current live event
rehearsal lane being consumed as real-submit identity
```

### Projection Boundary

Candidate Pool, Daily Table, Goal Status, Server Monitor, and Owner Console may
display:

```text
eligible promotion candidates
arbitration winner
why other candidates did not enter the narrow lane
current open action-time lane
```

They must not create the real-submit winner outside PG arbitration.

### PG Constraint Implication

The target chain must enforce:

```text
valid live_signal_event
-> valid promotion_candidate
-> PG arbitration winner
-> one open real_submit_candidate lane
-> one active Action-Time Ticket
```

This ensures the system can explain:

```text
哪些机会出现了
哪些机会只是候选
哪一个被选进真实提交前窄门
其他候选为什么没进去
```

## Owner Confirmation Round 26 - Owner Policy / Runtime Profile / Notional-Leverage Scope

Recorded after the Owner confirmed the policy, runtime profile, sizing, leverage,
and protection-scope recommendation.

### Confirmed Rule

Before an Action-Time Ticket can be created, PG must prove that the exact
candidate trade is inside current Owner policy and runtime scope.

Confirmed required proof:

```text
strategy_group_id allowed
symbol allowed
side allowed
event_spec_id allowed
runtime_profile_id bound
notional allowed
leverage allowed
protection_ref exists
```

### Plain-Language Meaning

A strategy signal only proves:

```text
市场给了机会。
```

Owner Policy and runtime scope prove:

```text
这类机会被 Owner 授权给系统处理。
系统知道用哪套运行配置处理。
系统知道金额、杠杆、保护条件没有越界。
```

If any of these are missing, the result is not generic no-trade. It is a precise
non-market blocker.

### Required Current-State Source

Owner policy, runtime profile, notional, leverage, and protection scope must be
current PG state.

The runtime must not use:

```text
repo MD files
generated JSON files
old packets
old chat decisions
stale artifacts
code fallback defaults
```

as current authorization.

### Required Ticket Precondition

Before creating `brc_action_time_tickets`, the chain must prove:

```text
strategy enabled by current Owner policy
candidate scope authorized by current Owner policy
runtime profile bound to candidate scope
notional / leverage within current scope
protection reference generated and valid
account / open-order / active-position facts fresh
```

### Example

For:

```text
MPG-001 / SOLUSDT / long / MPG-LONG
```

the ticket precondition must prove:

```text
MPG-001 is enabled
SOLUSDT is authorized for MPG-001
long is authorized for MPG-001
MPG-LONG is an allowed event spec
runtime_profile_id is bound
notional cap exists
leverage cap exists
protection_ref exists
```

If market facts are satisfied but one of these is missing, the chain must report
a precise blocker such as:

```text
owner_policy_scope_missing
runtime_profile_scope_missing
symbol_side_notional_leverage_scope
protection_reference_missing
```

instead of reporting only:

```text
no trade
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
ticket creation without current Owner policy match
ticket creation without runtime_profile_id
ticket creation without notional / leverage scope
ticket creation without protection_ref
chat authorization as runtime authority
MD / JSON / artifact policy as runtime authority
code default sizing as ticket authority
```

### PG Constraint Implication

The target design must make these boundaries enforceable through PG current
state and constraints:

```text
brc_owner_policy_current
brc_runtime_profile_bindings
brc_candidate_scope_event_bindings
brc_symbol_side_notional_leverage_scope
brc_protection_references
brc_action_time_tickets
```

Exact table names may change, but the invariant must not:

```text
no current policy/runtime/sizing/protection scope
-> no Action-Time Ticket
```

## Owner Confirmation Round 27 - Action-Time Ticket Lifecycle

Recorded after the Owner confirmed the Action-Time Ticket lifecycle
recommendation.

### Confirmed Rule

Action-Time Tickets must be short-lived, unique, invalidatable, and auditable.

Confirmed direction:

```text
ticket created
-> preflight_pending
-> finalgate_ready or rejected
-> submitted or expired / superseded / closed / invalidated
```

The system must not allow:

```text
yesterday's ticket being reused for today's order
old signal ticket being revived by a later monitor refresh
ticket state being silently overwritten without audit trail
submitted ticket being submitted again
```

### Plain-Language Meaning

An Action-Time Ticket is not a strategy setting and not a long-term
authorization.

It is the machine identity of one exact candidate trade from one exact market
event.

If the market event expires, account facts change, protection becomes invalid,
or a better arbitration winner replaces it, the ticket must stop being usable.

### Required Statuses

The target PG design must support statuses equivalent to:

| Status | Chinese name | May proceed |
| --- | --- | --- |
| `created` | 票据刚生成 | yes |
| `preflight_pending` | 等待交易前检查 | yes |
| `finalgate_ready` | 可交给 FinalGate 检查 | yes |
| `finalgate_rejected` | FinalGate 拒绝 | no |
| `expired` | 超过有效窗口 | no |
| `superseded` | 被更新鲜或更高优先级候选替代 | no |
| `submitted` | 已通过官方路径提交 | no duplicate submit |
| `closed` | 正常关闭，无后续动作 | no |
| `invalidated` | 事实反转、保护缺失、账户状态变化 | no |

Exact names may change, but the lifecycle categories must not disappear.

### Required Expiry / Invalidation Conditions

A ticket must become unusable when any of these happen:

```text
signal freshness window expired
event session expired
public facts stale
action-time facts stale
active position appears
open order appears
notional / leverage policy changes
runtime profile changes
protection_ref invalid
new arbitration winner supersedes it
server coverage lost
```

### Required PG Constraints

The target PG model must enforce:

```text
one open real_submit_candidate lane -> at most one active ticket
ticket requires expires_at_ms
ticket_hash covers strategy / symbol / side / event / event_time / profile / notional / leverage / protection
expired / rejected / invalidated / closed tickets cannot enter FinalGate
submitted ticket cannot be submitted again
ticket status changes emit append-only audit events
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
ticket without expires_at_ms
ticket without lineage refs
ticket without ticket_hash
stale ticket entering FinalGate
ticket whose public facts or action-time facts are stale
ticket whose active position / open order facts changed
ticket whose protection_ref is no longer valid
ticket reused after submitted
ticket state mutation without audit event
```

### PG Constraint Implication

The target design must include a ticket lifecycle and audit trail, such as:

```text
brc_action_time_tickets
brc_action_time_ticket_events
```

Exact table names may change, but the invariant must not:

```text
only active, fresh, ticket-bound candidates may reach FinalGate
```

## Owner Confirmation Round 28 - FinalGate Input Boundary

Recorded after the Owner confirmed the FinalGate input-boundary recommendation.

### Confirmed Rule

FinalGate must consume Action-Time Ticket identity only.

Confirmed direction:

```text
Action-Time Ticket
-> FinalGate checks ticket-bound lineage and facts
-> FinalGate emits pass / reject evidence
-> Operation Layer consumes ticket_id + FinalGate pass
```

FinalGate must not reconstruct trade identity from projections, generated JSON,
repo MD, loose parameters, or old artifacts.

### Plain-Language Meaning

FinalGate answers:

```text
这张交易前正式票据是否仍然安全、完整、未过期、在授权范围内。
```

It must not answer:

```text
这个策略支持什么方向
这个币是否允许
这个事件是否存在
这笔交易的金额杠杆该怎么拼
```

Those answers must already exist in PG-backed lineage before FinalGate is
called.

### Allowed FinalGate Checks

FinalGate may check:

```text
ticket is active
ticket is not expired
ticket lineage is complete
strategy / symbol / side / event are consistent across lineage refs
public facts are fresh
action-time facts are fresh
account has no active position conflict
account has no open order conflict
notional / leverage remain within current PG policy
protection_ref is valid
Operation Layer route is official
duplicate-submit guard passes
```

### Forbidden FinalGate Behavior

FinalGate must not:

```text
decide supported StrategyGroup symbol / side
reinterpret event_id
read Candidate Pool / Daily Table / Goal Status as trade identity
read repo MD / generated JSON / output artifacts as trade identity
use generated_at as event_time
submit directly
expand notional / leverage
expand live profile
bypass Operation Layer
```

### Required API / Service Boundary

FinalGate API or service input must be equivalent to:

```text
ticket_id
```

It must not accept loose authority inputs as the source of truth:

```text
strategy_group_id
symbol
side
amount
leverage
runtime_profile
```

Those values may appear only as ticket-bound data loaded through the ticket
lineage.

### Required Output Boundary

FinalGate pass does not create an order.

It may produce:

```text
finalgate_passed evidence
finalgate_rejected evidence
reason codes
audit event
```

It must not produce:

```text
exchange write
order creation
Operation Layer bypass
profile mutation
sizing mutation
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
FinalGate call without ticket_id
FinalGate call using loose candidate JSON as identity
FinalGate call using Candidate Pool / Daily Table row as identity
FinalGate call for expired / rejected / invalidated ticket
FinalGate pass without complete ticket lineage
Operation Layer call without ticket_id + FinalGate pass
```

### PG / Runtime Constraint Implication

The target architecture must enforce:

```text
FinalGate input = ticket_id
FinalGate checks = ticket-bound facts and current safety state
FinalGate output = pass / reject evidence
Operation Layer input = ticket_id + FinalGate pass
```

This prevents PG-backed L2-L7 constraints from being bypassed at the final
pre-submit boundary.

## Owner Confirmation Round 29 - Operation Layer Handoff

Recorded after the Owner confirmed the Operation Layer handoff recommendation.

### Confirmed Rule

Operation Layer may consume only:

```text
ticket_id
+ finalgate_pass_id
```

as authority input for a real submit path.

It must not consume loose JSON, Candidate Pool rows, Daily Table ranks,
Goal Status summaries, old artifacts, or manually assembled order parameters as
trade authority.

### Plain-Language Meaning

Before Operation Layer, the system may still discuss:

```text
is this an opportunity?
is this candidate eligible?
is this ticket safe?
```

Operation Layer must only execute:

```text
this exact ticket has passed FinalGate through the official path.
```

### Correct Handoff Shape

The target chain is:

```text
Action-Time Ticket
-> FinalGate pass evidence
-> Operation Layer official submit command
-> exchange gateway
-> protection
-> reconciliation
-> settlement / review
```

### Forbidden Handoff Shape

The target architecture must reject:

```text
strategy_group_id + symbol + side + amount
-> Operation Layer builds order identity by itself
```

and:

```text
Candidate Pool / Daily Table / Goal Status / JSON artifact
-> Operation Layer submit
```

### Allowed Operation Layer Duties

Operation Layer may:

```text
read ticket_id
verify finalgate_pass_id belongs to the same ticket
verify ticket is still active / not expired / not submitted
generate official submit command
call exchange gateway
write order lifecycle state
start protection
start reconciliation
record settlement / review lineage
```

### Forbidden Operation Layer Duties

Operation Layer must not:

```text
choose StrategyGroup
choose symbol / side
recompute notional / leverage as authority
reinterpret event_id
read repo MD / JSON / output artifacts as trade identity
bypass FinalGate
submit without protection_ref
submit the same ticket twice
expand runtime profile
expand sizing
expand leverage
```

### Required PG Constraints

The target PG model must enforce:

```text
operation submit command requires ticket_id
operation submit command requires finalgate_pass_id
ticket_id and finalgate_pass_id must share lineage
one ticket may have at most one accepted submit command
accepted submit command must create order lifecycle row
protection_ref missing -> submit command cannot be accepted
reconciliation must trace order back to ticket
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
Operation Layer submit without ticket_id
Operation Layer submit without finalgate_pass_id
Operation Layer submit where finalgate_pass_id belongs to another ticket
Operation Layer submit from loose strategy/symbol/side/amount params
Operation Layer submit from JSON/candidate projection identity
Operation Layer duplicate submit for the same ticket
Operation Layer submit without protection_ref
```

### Authority Boundary

Operation Layer is the official submit path, but it is not a strategy
interpreter.

Confirmed invariant:

```text
Operation Layer executes only an already-authorized ticket path.
It does not decide what is tradable.
```

## Owner Confirmation Round 30 - Protection / Reconciliation / Review Lineage

Recorded after the Owner confirmed the protection, reconciliation, and review
lineage recommendation.

### Confirmed Rule

After a real submit command is accepted, order lifecycle, protection,
reconciliation, and review must all trace back to the same ticket lineage.

Confirmed chain:

```text
live_signal_event
-> promotion_candidate
-> action_time_lane_input
-> action_time_ticket
-> finalgate_pass
-> operation_submit_command
-> exchange_order
-> protection_state
-> reconciliation_state
-> review_outcome
```

### Plain-Language Meaning

After a real order exists, the system must still answer:

```text
这笔单为什么下了
它来自哪个策略信号
保护有没有挂上
交易所账户和系统记录是否一致
策略事后表现如何
```

The order must not become an isolated exchange artifact detached from the signal
and ticket that created it.

### Required Post-Submit Lineage

The target PG model must enforce:

```text
accepted submit command -> order lifecycle row
exchange order -> ticket_id lineage
protection_state -> ticket_id + order_id lineage
reconciliation_state -> ticket_id + order_id + exchange_order_id lineage
review_outcome -> signal_event_id + ticket_id + order_id lineage
```

If this lineage cannot be established, the submit path must not be treated as a
complete success.

### Required Protection Blockers

Protection must block or mark incomplete when:

```text
protection_ref missing
protection order failed
stop / invalidation reference missing
position opened but protection not confirmed
protection stale or detached
```

These are post-submit safety blockers, not market blockers.

### Required Reconciliation Blockers

Reconciliation must block or mark incomplete when:

```text
local order exists but exchange order missing
exchange order exists but local lifecycle missing
position size mismatch
open order mismatch
fill mismatch
unknown exchange state
```

These are reconciliation blockers, not strategy blockers.

### Required PG Tables Or Equivalent

The target design must include equivalent structures for:

```text
operation_submit_commands(ticket_id, finalgate_pass_id)
order_lifecycle(ticket_id, submit_command_id, exchange_order_id)
protection_states(ticket_id, order_id, protection_ref, status)
reconciliation_states(ticket_id, order_id, exchange_order_id, status)
strategy_review_outcomes(signal_event_id, ticket_id, order_id, outcome)
```

Exact table names may change, but the lineage must not.

### Required Rejection Rules

The PG-backed chain must reject:

```text
accepted submit command without order lifecycle row
exchange order that cannot trace to ticket_id
protection state that cannot trace to ticket_id and order_id
reconciliation state that cannot trace to ticket_id / order_id / exchange_order_id
review outcome based on loose JSON or human explanation instead of signal_event + ticket + order lineage
complete-success status without protection confirmation
complete-runtime-closure status without reconciliation confirmation
```

### Final Invariant

Confirmed rule:

```text
real submit is not complete until protection and reconciliation are linked back
to the ticket lineage.
```

## Owner Confirmation Round 31 - Server Monitor / Owner Notification

Recorded after the Owner confirmed the server monitor and Owner notification
recommendation.

### Confirmed Rule

Production monitoring must read Tokyo PG current state, not local files, local
heartbeat, generated JSON exports, or Codex session state.

Confirmed direction:

```text
Tokyo server timer
-> read PG current state
-> classify quiet / notify
-> Feishu notify only when needed
```

### Plain-Language Meaning

Server Monitor answers:

```text
系统是否健康等待机会
是否出现 fresh signal / promotion / ticket / action-time event
是否有工程、安全、保护、对账问题需要 Owner 知道
```

If the system is healthy and only waiting for the market, it should stay quiet.

### Correct Production Monitor Source

The production monitor must read PG current state for:

```text
runtime coverage
live_signal_events
promotion_candidates
action_time_tickets
finalgate_evidence
operation_submit_commands
protection_states
reconciliation_states
owner_intervention_required flags
```

It must not use:

```text
local Codex heartbeat
local output JSON
Daily Table export as authority
Candidate Pool export as authority
Goal Status JSON as authority
local cache refresh time
repo MD files
```

as production monitoring truth.

### Notification Rules

Confirmed notification behavior:

| Scenario | Behavior |
| --- | --- |
| Healthy waiting for opportunity | quiet |
| Fresh signal appears | notify |
| Promotion candidate generated | notify with dedupe as configured |
| Action-Time Ticket generated | notify |
| FinalGate pass / reject | notify |
| Real submit accepted | notify |
| Protection failure | must notify |
| Reconciliation abnormality | must notify |
| Watcher / coverage / PG projection abnormality | must notify |
| Pure JSON export stale | export issue only, not production trading failure |

### Required Dedupe State

Feishu or equivalent Owner notification must have dedupe state equivalent to:

```text
dedupe_key
first_seen_at_ms
last_notified_at_ms
notification_status
owner_action_required
```

This prevents repeated noise when the system is already reporting the same
issue.

### Required Rejection Rules

The target architecture must reject:

```text
local heartbeat deciding production notification
local stale JSON becoming production blocker
Daily Table export overriding PG monitor state
Candidate Pool export overriding PG monitor state
Goal Status JSON overriding PG monitor state
healthy waiting generating repeated Owner alerts
protection / reconciliation abnormality staying silent
```

### Owner Interface Boundary

Owner should be notified for:

```text
policy / risk / abnormal intervention
fresh opportunity or ticket milestones
submit / protection / reconciliation events
runtime coverage or monitor failures
```

Owner should not be pulled into:

```text
ordinary healthy waiting
manual artifact interpretation
manual RequiredFacts assembly
manual ticket construction
manual gate operation
```

### PG Constraint Implication

The target design must include server-side notification state, such as:

```text
brc_server_monitor_runs
brc_owner_notifications
brc_owner_notification_dedupe
```

Exact table names may change, but the invariant must not:

```text
production monitor reads PG current state only
local files are not production monitoring truth
```

## Owner Confirmation Round 32 - Old Source Disposition

Recorded after the Owner confirmed the old source disposition recommendation.

### Confirmed Rule

PG migration must include an old-source disposition inventory.

It is not enough to add PG tables while old MD, JSON, output artifacts, code
fallbacks, and old tests remain able to shape runtime or trading decisions.

Confirmed direction:

```text
every old source -> convert / delete / clean / archive
old source must not remain as runtime fallback
repo MD / JSON / output must not be runtime or trading decision truth
```

### Plain-Language Meaning

PG化 must not create two active truth systems:

```text
PG says one thing
old JSON / MD / code fallback says another
runtime chooses whichever exists
```

The target system must have one current truth path:

```text
PG current state
-> runtime process
-> projections / exports
```

### Required Disposition Categories

Every old source touched by the migration must be classified into exactly one
outcome:

| Outcome | Chinese name | Meaning | Example |
| --- | --- | --- | --- |
| `convert` | 转换 | Valuable content becomes PG event / scope / ticket / review data | strategy event definitions, RequiredFacts, calibration samples |
| `delete` | 删除 | Conflicting or valueless source is removed | DEFAULT_SIDE_SCOPE, forced long/short mirror tests |
| `clean` | 清理 | Source remains but no longer expresses authority | Candidate Pool builder becomes PG projector |
| `archive` | 归档 | Historical evidence preserved outside current authority | old reports, old packets, old replay artifacts |

No source may stay in a mixed current/historical state.

### Required Source Handling

The migration must handle these source classes:

| Source class | Required handling |
| --- | --- |
| strategy semantics code | no longer defines runtime side/symbol truth; convert to PG seed or pure computation semantics |
| DEFAULT_SIDE_SCOPE | delete; no fallback |
| Candidate Pool JSON | export only, not input |
| Daily Table JSON | export only, not input |
| Goal Status JSON | export only, not input |
| Single Lane Packet | no longer runtime decision input; task export only or delete |
| MD strategy packs | convert to registry / PG seed or archive |
| old tests | rewrite into negative PG constraint tests |
| output/** | commit only approved fixed control snapshots; never runtime truth |

### Forbidden Fallbacks

The target architecture must reject:

```text
PG missing -> fallback to old JSON
PG missing -> fallback to MD
PG missing -> fallback to DEFAULT_SIDE_SCOPE
new tests pass while old tests still assert obsolete semantics
old artifact influences Candidate Pool
old artifact influences FinalGate
old artifact influences Operation Layer
```

### Required Acceptance Proof

PG化 must prove:

```text
system still runs when old JSON / MD runtime inputs are removed
old artifacts absent does not break runtime decision path
unsupported side is rejected
unsupported symbol is rejected
generated_at cannot be event_time_ms
FinalGate without ticket_id is rejected
Operation Layer without ticket_id + finalgate_pass_id is rejected
```

### Final Invariant

Confirmed rule:

```text
PG migration is not complete until old source authority is eliminated.
```

## Owner Confirmation Round 33 - PG Cutover / Initial Seed

Recorded after the Owner confirmed the PG cutover and initial seed
recommendation.

### Confirmed Rule

The initial PG seed must contain only the newly confirmed clean semantics from
this L2-L7 reset.

It must not bulk-import old MD, JSON, output artifacts, replay opportunities,
old packets, generated timestamps, or broad code defaults as current state.

Confirmed direction:

```text
confirmed strategy semantics
-> curated PG seed
-> constraint validation
-> runtime reads PG current state
```

Rejected direction:

```text
scan old JSON / MD / output
-> import everything into PG
-> old semantics become database debt
```

### Plain-Language Meaning

PG化 must not move old file debt into the database.

The first seed is the first real authority boundary. If old wide semantics are
imported there, PG becomes a copy of the old conflict rather than a replacement
for it.

### Required Initial Seed Content

The initial PG seed must include:

| Seed class | Required content |
| --- | --- |
| StrategyGroup | CPM-RO-001, MPG-001, MI-001, SOR-001, BRF2-001 |
| Candidate Scope | Confirmed StrategyGroup + symbol + side scope |
| Event Spec | CPM-LONG, MPG-LONG, MI-LONG, SOR-LONG, SOR-SHORT, BRF2-SHORT |
| RequiredFacts | Required and disable facts for each event spec |
| Runtime Profile Binding | Allowed runtime profile for each candidate scope |
| Owner Policy Current | Current enable / observe / ticket / submit boundaries |
| Sizing Scope | Symbol / side / notional / leverage caps |
| Protection Rule | Protection reference rules per event |
| Projection Ownership | One owner projector per current projection |

### Forbidden Initial Seed Content

The initial PG seed must not include:

```text
old artifact fresh signal
old replay opportunity
old output action_time_lane
old packet closure task
old generated_at as market event time
old DEFAULT_SIDE_SCOPE
old broad supported_sides
old human explanation as current authorization
```

These may only go to:

```text
review evidence
calibration samples
archive
```

They must not go to:

```text
live_signal_events
promotion_candidates
action_time_tickets
current owner policy
```

### Required Current Live Signal Boundary

Initial seed must not pre-create current fresh live signals.

Confirmed rule:

```text
current live_signal_events must come from future live watcher / live detector events.
```

Historical or replay opportunities may teach the event specs, but they cannot
become fresh runtime opportunities.

### Required Rejection Rules

The target migration must reject:

```text
importing old DEFAULT_SIDE_SCOPE into current candidate scope
importing old supported_sides into current side authority
importing old generated_at as event_time_ms
importing replay opportunity as live_signal_event
importing old packet as action-time authority
importing old JSON as current Owner policy
```

### Acceptance Meaning

PG cutover is accepted only when:

```text
initial seed reflects confirmed L2-L7 semantics
old broad side/symbol/event semantics cannot enter current state
current live_signal_events start empty or live-only
negative constraints prove unsupported old semantics are rejected
runtime reads PG current state after cutover
```

## Owner Confirmation Round 34 - Migration Validation / Negative Tests

Recorded after the Owner confirmed the migration validation and negative-test
recommendation.

### Confirmed Rule

PG migration acceptance must be centered on negative constraints, not only happy
paths.

Confirmed direction:

```text
prove invalid paths cannot enter
+ prove valid paths can advance
```

It is not enough to prove:

```text
tables exist
seed exists
happy-path ticket can be created
```

The migration must prove:

```text
old broad semantics cannot re-enter
old file/json sources cannot decide runtime state
unsupported side / symbol / event is rejected
ticket bypass is rejected
FinalGate / Operation Layer cannot consume loose identity
```

### Required Negative Tests

The migration must include negative tests for:

| Test | Expected result |
| --- | --- |
| CPM-RO-001 short | rejected |
| MPG-001 short | rejected |
| MI-001 short | rejected |
| BRF2-001 long | rejected |
| SOR-001 generic signal without SOR-LONG or SOR-SHORT | rejected |
| unsupported symbol | rejected |
| generated_at as event_time_ms | rejected |
| live_signal_event without event_spec_id | rejected |
| promotion_candidate without signal_event_id | rejected |
| action_time_ticket without promotion_candidate_id | rejected |
| ticket without expires_at_ms | rejected |
| FinalGate without ticket_id | rejected |
| Operation Layer without ticket_id + finalgate_pass_id | rejected |
| replay event as fresh live signal | rejected |
| Candidate Pool JSON as authority input | rejected |

### Required Positive Tests

The migration must also include positive tests for:

| Test | Expected result |
| --- | --- |
| CPM-LONG allowed scope | can create live_signal_event |
| MPG-LONG allowed scope | can create live_signal_event |
| MI-LONG allowed scope | can create live_signal_event |
| SOR-LONG explicit event | can create long side-specific candidate |
| SOR-SHORT explicit event | can create short side-specific candidate |
| BRF2-SHORT allowed scope | can create short candidate |
| PG arbitration winner | creates only one real_submit_candidate lane |
| complete ticket lineage | can enter FinalGate preflight |
| FinalGate pass + ticket_id | can create Operation submit command |
| submit accepted | order / protection / reconciliation / review lineage is traceable |

### Required Old-Source Removal Validation

The migration must prove:

```text
system still runs after old JSON / MD runtime inputs are removed
legal long/short events still work after DEFAULT_SIDE_SCOPE is deleted
Candidate Pool / Daily Table / Goal Status are projection/export only
FinalGate and Operation Layer do not depend on old output artifacts
old tests no longer assert obsolete forced mirroring semantics
```

### Acceptance Meaning

PG化 is accepted only when:

```text
invalid paths cannot enter
valid paths can advance
old authority is eliminated
runtime reads PG current state
FinalGate and Operation Layer require ticket lineage
```

The acceptance standard is:

```text
错误进不来 + 合法能前进
```

## Owner Confirmation Round 35 - Schema Ownership / Projector Ownership

Recorded after the Owner confirmed the schema ownership and projector ownership
recommendation.

### Confirmed Rule

Every current state and current projection must have one owner writer.

Confirmed direction:

```text
PG current tables
-> one owner projector per projection
-> JSON / MD export
```

The system must not allow multiple scripts, post-steps, export builders, or
legacy refresh paths to overwrite the same current state or projection with
different inputs.

### Plain-Language Meaning

PG化 does not solve state conflict if many writers can still modify the same
current state.

The target is:

```text
谁负责写，必须唯一。
谁只能读，必须明确。
谁只能导出，不能反写。
```

### Required Ownership Mapping

The target system must assign unique writers equivalent to:

| Object | Owner writer |
| --- | --- |
| strategy/event specs | seed / migration owner |
| candidate scope bindings | policy/scope admin path |
| runtime coverage | watcher coverage writer |
| fact snapshots | evaluator/fact writer |
| live_signal_events | live detector writer |
| promotion_candidates | promotion projector |
| action_time_lane_inputs | arbitration projector |
| action_time_tickets | ticket issuer |
| finalgate_evidence | FinalGate service |
| operation_submit_commands | Operation Layer |
| protection_states | protection service |
| reconciliation_states | reconciliation service |
| Daily Table export | daily table projector |
| Goal Status export | goal status projector |
| Server Monitor state | server monitor service |

### Forbidden Write Patterns

The target architecture must reject:

```text
multiple projectors writing the same projection_scope_key
server post-step rewriting current state through multiple paths
export builder writing runtime truth
Goal Status re-deciding Candidate Pool
Daily Table re-deciding Action-Time Lane
monitor reading JSON export and writing PG truth from it
legacy refresh path overwriting a PG current projection
```

### Required PG Constraints

The target PG model must include an equivalent of:

```text
brc_current_projection_ownership:
  model_type
  projection_scope_key
  owner_projector
  unique(model_type, projection_scope_key)

brc_projection_runs:
  projection_id
  owner_projector
  input_state_version
  output_state_hash
  started_at_ms
  completed_at_ms
  status
```

Exact table names may change, but ownership uniqueness must not.

### Required Rejection Rules

The PG-backed chain must reject:

```text
non-owner writer updating current projection
export builder mutating runtime truth
post-step writing a current projection without ownership
old refresh script replacing PG current state
projection run without recorded input_state_version and output_state_hash
```

### Final Invariant

Confirmed rule:

```text
one current state / current projection -> one owner writer.
Non-owner paths may write audit or diagnostic records only.
```

## Owner Confirmation Round 36 - Strategy Intake Pipeline

Recorded after the Owner confirmed the Strategy Intake Pipeline
recommendation.

### Confirmed Rule

New strategies must complete PG-backed intake before entering watcher scope,
Candidate Pool, promotion, ticket, or submit eligibility.

Confirmed direction:

```text
strategy research
-> strategy handoff
-> event spec
-> RequiredFacts
-> candidate scope
-> runtime profile / policy / sizing / protection
-> watcher coverage
-> live_signal_event eligibility
```

Rejected direction:

```text
interesting strategy idea
-> handwritten JSON / MD / watcher config
-> Candidate Pool observes it
-> semantics filled in later
```

### Plain-Language Meaning

A new strategy may be interesting in research, but it is not runtime-capable
until the system can answer:

```text
which symbols are allowed
which sides are allowed
which event creates a fresh signal
which facts prove the event
which runtime profile applies
which policy / sizing / protection bounds apply
whether watcher coverage exists
whether ticket lineage can be created
```

### Required Intake Stages

The target PG model must support stages equivalent to:

| Stage | Chinese name | Required output |
| --- | --- | --- |
| `research_only` | 研究中 | Research evidence only; no runtime authority |
| `handoff_ready` | 策略交接完成 | Strategy handoff, risk notes, samples, draft event idea |
| `pg_semantics_ready` | PG 语义就绪 | StrategyGroup, event specs, RequiredFacts |
| `scope_authorized` | 范围授权完成 | Symbol / side / event scope |
| `runtime_observable` | 可被 watcher 观察 | Runtime coverage target |
| `promotion_eligible` | 可生成 promotion candidate | Live signal event rules closed |
| `ticket_eligible` | 可生成 Action-Time Ticket | Policy / profile / sizing / protection closed |
| `submit_eligible` | 可进入真实提交窄门 | FinalGate / Operation Layer preconditions closed |

Exact stage names may change, but the gate order must not allow critical steps
to be skipped.

### Forbidden Intake Shortcuts

The target architecture must reject:

```text
new strategy directly entering watcher
new strategy directly entering Candidate Pool
fresh_signal without event_spec
promotion_candidate without RequiredFacts
Action-Time Ticket without policy / profile / sizing / protection
MD handoff as runtime authority
research backtest as live_signal_event
```

### Required PG Tables Or Equivalent

The target design must include equivalent structures for:

```text
brc_strategy_intake_cases
brc_strategy_group_versions
brc_strategy_side_event_specs
brc_strategy_event_required_facts
brc_candidate_scope_event_bindings
brc_owner_policy_current
brc_runtime_profile_bindings
brc_strategy_intake_stage_events
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
watcher scope for strategy without PG semantics
Candidate Pool row for strategy without event spec
promotion candidate for strategy without live_signal_event eligibility
ticket for strategy below ticket_eligible
submit lane for strategy below submit_eligible
research or handoff document used as runtime authority
```

### Final Invariant

Confirmed rule:

```text
strategy research and handoff may feed PG intake.
Only PG-backed intake stages may grant runtime capability.
```

## Owner Confirmation Round 37 - Policy Change / Revocation

Recorded after the Owner confirmed the policy-change and revocation
recommendation.

### Confirmed Rule

When current Owner policy, runtime profile, sizing policy, or protection rules
change, all affected promotion candidates, action-time lanes, and tickets must
be revalidated or invalidated.

Confirmed direction:

```text
Owner policy changed
-> affected promotion_candidates rechecked
-> affected action_time_lane_inputs invalidated or reclassified
-> affected action_time_tickets expired / invalidated
-> FinalGate / Operation Layer cannot use old authorization
```

### Plain-Language Meaning

Authorization is not timeless.

If a ticket was created under old authorization, it must not continue toward
FinalGate or Operation Layer after the current authorization changes unless it
is explicitly revalidated under the new current version.

### Required Impact By Change Type

The target PG model must enforce impacts equivalent to:

| Change type | Required impact |
| --- | --- |
| StrategyGroup paused | related promotion / lane / ticket invalidated |
| symbol removed | related candidate / lane / ticket invalidated |
| side disabled | related candidate / lane / ticket invalidated |
| event_spec disabled | related live signal cannot be promoted |
| runtime_profile disabled | related ticket invalidated |
| notional / leverage reduced | ticket exceeding new scope invalidated |
| protection rule changed | protection_ref must be revalidated |
| submit permission disabled | real-submit lane and ticket cannot proceed |

### Required Version Binding

Tickets must bind the current policy versions used when they were created:

```text
owner_policy_version
runtime_profile_version
sizing_policy_version
protection_rule_version
```

or equivalent references.

When current versions change:

```text
ticket version != current version
-> ticket must be revalidated or invalidated
```

### Forbidden Behavior

The target architecture must reject:

```text
old ticket entering FinalGate under old authorization
old candidate entering action-time under old scope
watcher continuing old scope after policy change
ticket staying active after runtime profile is disabled
ticket exceeding new notional / leverage scope
ticket using protection_ref after protection rule change without revalidation
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
FinalGate call for ticket with stale policy version
Operation Layer submit for ticket with stale policy version
active real-submit lane after submit permission disabled
promotion candidate after side / symbol / event disabled
ticket whose runtime profile is no longer current
```

### Final Invariant

Confirmed rule:

```text
current authorization must be current at execution time, not only at ticket
creation time.
```

## Owner Confirmation Round 38 - Data Retention / Audit / Archive

Recorded after the Owner confirmed the data retention, audit, and archive
recommendation.

### Confirmed Rule

The repo must not retain long-term runtime state, but PG must retain current
state and append-only audit events.

Confirmed direction:

```text
PG current state
-> append-only audit events
-> periodic archive / cold storage
-> JSON / MD export only for viewing and diagnostics
```

Rejected direction:

```text
output/ stores runtime truth
docs/ stores historical runtime decisions
runtime reads those files back as current authority
```

### Plain-Language Meaning

Cleaning repo files must not mean losing traceability.

The system must still be able to answer:

```text
when a ticket was created
who changed policy
which projector wrote a current projection
why FinalGate rejected
whether Operation Layer submitted
why protection failed
when reconciliation recovered
```

Those answers must come from PG audit events, not MD / JSON / output artifacts.

### Required Data Classification

The target architecture must classify data like this:

| Data type | Current truth | Audit | Archive |
| --- | --- | --- | --- |
| Owner policy | PG current | policy events | historical versions |
| event spec | PG current / versioned | migration / seed events | historical versions |
| fact snapshot | PG current / recent | snapshot events / hash | cold archive |
| live_signal_event | PG current / recent | signal events | historical signal library |
| ticket | PG current / recent | ticket lifecycle events | historical ticket |
| order lifecycle | PG current | order events | permanent or long-term |
| protection / reconciliation | PG current | safety events | long-term |
| JSON / MD export | not current truth | export run event | deletable / regenerable |
| old artifacts | not current truth | archive index | cold archive or delete |

### Required Audit Events

The target PG design must retain append-only audit events equivalent to:

```text
policy_changed
scope_changed
event_spec_seeded
runtime_coverage_updated
fact_snapshot_written
live_signal_detected
promotion_created
arbitration_selected
action_time_lane_opened
ticket_created
ticket_invalidated
finalgate_passed
finalgate_rejected
submit_command_created
exchange_order_seen
protection_confirmed
protection_failed
reconciliation_matched
reconciliation_mismatch
review_recorded
projection_exported
```

Exact event names may change, but the audit coverage must not.

### Forbidden Retention Patterns

The target architecture must reject:

```text
git commit as runtime state retention
output JSON as the only audit fact
MD document as current policy
artifact file deciding whether a historical ticket exists
file deletion making PG state changes unauditable
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
current-state mutation without audit event
ticket lifecycle mutation without audit event
policy change without audit event
projection export without export run event
order lifecycle change without order event
protection / reconciliation state change without safety event
```

### Final Invariant

Confirmed rule:

```text
repo files are not long-term runtime truth.
PG current state plus append-only audit events are the traceability backbone.
```

## Owner Confirmation Round 39 - Blocker Classification / No-Trade Explanation

Recorded after the Owner confirmed the blocker classification and no-trade
explanation recommendation.

### Confirmed Rule

Every no-trade, no-ticket, or no-submit conclusion must resolve to one unique
first blocker, with clear separation between market blockers, engineering
blockers, policy blockers, and safety blockers.

Confirmed direction:

```text
stage reached
-> exact first blocker
-> plain-language reason
-> next system action
-> owner_action_required only when truly needed
```

Rejected direction:

```text
no trade
reason: not ready / waiting / unknown
```

### Plain-Language Meaning

The system must answer:

```text
市场有没有给机会
如果有，系统推到了哪一步
为什么没有交易
这是市场条件不满足，还是工程 / 授权 / 安全链路没闭合
```

This must be system output, not a repeated manual investigation by the Owner.

### Required Blocker Taxonomy

The target PG-backed blocker taxonomy must include categories equivalent to:

| Blocker | Chinese name | Example |
| --- | --- | --- |
| `market_not_satisfied` | 市场条件不满足 | facts computed false |
| `fresh_signal_absent` | 没有新鲜事件 | no event-backed signal |
| `runtime_coverage_missing` | 服务器没覆盖 | watcher not covering exact scope/event |
| `fact_snapshot_missing` | 事实缺失 | no event-specific snapshot |
| `policy_scope_missing` | 授权缺失 | symbol / side / event not authorized |
| `runtime_profile_missing` | 运行配置缺失 | no profile binding |
| `sizing_scope_missing` | 金额杠杆缺失 | notional / leverage not closed |
| `protection_missing` | 保护缺失 | no protection_ref |
| `arbitration_lost` | 仲裁未选中 | valid opportunity lost to higher-priority candidate |
| `ticket_missing` | 票据缺失 | no formal Action-Time Ticket |
| `ticket_invalidated` | 票据失效 | expired, stale, or superseded |
| `finalgate_rejected` | FinalGate 拒绝 | final safety check failed |
| `operation_blocked` | 执行层阻断 | no pass, duplicate submit, or missing protection |
| `reconciliation_blocked` | 对账阻断 | exchange/local state mismatch |

Exact names may change, but the classification boundaries must not collapse
back into generic waiting language.

### Required Explanation Shape

Every StrategyGroup + symbol + side row must be able to output:

```text
strategy_group_id
symbol
side
event_spec_id
stage_reached
fresh_signal_status
promotion_status
ticket_status
first_blocker
blocker_owner
plain_language_reason
next_system_action
owner_action_required
evidence_refs
```

### Required Rejection Rules

The target architecture must reject:

```text
multiple competing first_blockers without one selected first blocker
market_not_satisfied used for missing engineering chain
waiting_for_market used when policy / runtime / protection / ticket is missing
Owner action required for ordinary engineering work
Owner action required for healthy market waiting
plain explanation sourced from loose JSON instead of PG lineage
```

### Final Invariant

Confirmed rule:

```text
no-trade explanation must be a first-class PG-backed product capability.
```

## Owner Confirmation Round 40 - Concurrency / Idempotency / Locking

Recorded after the Owner confirmed the concurrency, idempotency, and locking
recommendation.

### Confirmed Rule

All critical L5-L7 writes must be idempotent, uniqueness-constrained, and
transaction-safe.

Confirmed direction:

```text
critical write
-> idempotency key
-> PG unique / partial unique constraint
-> transaction or lock around narrow gates
-> retry returns existing semantic row
```

The system must not rely on code-only "select then insert" checks for critical
state.

### Plain-Language Meaning

Multiple workers may process the same market event at nearly the same time.

The result must still be:

```text
one live signal event
one promotion candidate for that signal
one arbitration winner
one real-submit lane
one active ticket
one accepted submit command
```

Retries must be safe. Repeating the same job must not create a second semantic
truth.

### Critical Writes Requiring Idempotency

The target PG-backed chain must protect at least:

```text
live_signal_event creation
promotion_candidate creation
arbitration winner selection
real_submit_candidate lane opening
Action-Time Ticket creation
FinalGate pass recording
Operation submit command acceptance
protection state creation
reconciliation state creation
```

### Required Unique Keys Or Equivalent

The target PG design must enforce uniqueness equivalent to:

| Object | Required uniqueness |
| --- | --- |
| live_signal_event | strategy_group_id + symbol + side + event_spec_id + event_time_ms |
| promotion_candidate | signal_event_id |
| real_submit lane | at most one open real_submit_candidate per account/profile/scope |
| action_time_ticket | action_time_lane_input_id or ticket_hash |
| finalgate_pass | ticket_id + gate_version |
| submit command | at most one accepted submit per ticket_id |
| protection state | ticket_id + order_id |
| reconciliation state | ticket_id + order_id + exchange_order_id |

Exact key names may change, but duplicate semantic state must not be possible.

### Required Locking / Transaction Behavior

The target runtime must use transaction-safe behavior for narrow gates:

```text
arbitration winner selection
real-submit lane opening
ticket issuance
FinalGate pass recording
submit command acceptance
```

This may use row locks, advisory locks, serializable transactions, partial
unique constraints, or an equivalent proven mechanism.

### Forbidden Behavior

The target architecture must reject:

```text
select-then-insert without unique constraint
worker retry creating a second ticket
same event_time creating multiple fresh signal events
same ticket creating multiple accepted submit commands
two arbitration workers opening two real-submit lanes
monitor or export triggering semantic state writes
duplicate-key handling that creates new meaning instead of returning existing row
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
duplicate live_signal_event for the same event identity
duplicate promotion_candidate for the same signal_event_id
second open real_submit_candidate in the same scope
second active ticket for the same lane
second accepted submit command for the same ticket
state mutation from monitor/export path
```

### Final Invariant

Confirmed rule:

```text
worker retry must be safe, and narrow gates must be protected by PG constraints
or equivalent transaction locks.
```

## Owner Confirmation Round 41 - Failure Mode / Recovery / Manual Intervention

Recorded after the Owner confirmed the failure mode, recovery, and manual
intervention recommendation.

### Confirmed Rule

When critical trade facts cannot be confirmed, the trading path must fail
closed. Read-only observation, diagnostics, and recovery may continue.

Confirmed direction:

```text
critical trade fact unavailable
-> no ticket / FinalGate / submit progression
-> write blocker / audit event
-> server monitor notifies when needed
-> recovery worker refreshes the missing facts
```

Rejected direction:

```text
PG or exchange state unavailable
-> use old JSON / cache / artifact to keep advancing
```

### Plain-Language Meaning

The system may continue watching, explaining, and recovering when something
breaks.

It must not continue toward real submit when the facts required to prove safety,
authorization, or account state are unknown.

### Required Fail-Closed Cases

The target runtime must fail closed for ticket, FinalGate, or submit progression
when:

| Failure | Required handling |
| --- | --- |
| PG current state unreadable | stop ticket / FinalGate / submit |
| PG write failed | do not treat state as advanced |
| watcher coverage lost | do not create new promotion / ticket |
| fact snapshot write failed | do not create live_signal_event |
| exchange account facts unreadable | do not enter FinalGate / submit |
| active position / open order unknown | do not submit |
| protection_ref unknown | do not submit |
| post-submit protection failed | enter protection incident and notify |
| reconciliation mismatch | stop further auto submit and notify |
| Feishu notification failed | retry and audit; do not alter trading safety |

### Auto-Recoverable Actions

The system may automatically attempt:

```text
re-read PG current state
refresh watcher coverage
recompute fact snapshot
query exchange orders / positions / open orders
confirm protection state
rerun reconciliation
regenerate projection export
retry failed notification
```

Recovery must not use old JSON, MD, output artifacts, or local cache as runtime
truth.

### Owner Notification Boundary

Owner must be notified for:

```text
real submit accepted
protection failed
reconciliation mismatch
PG current state unavailable
runtime coverage lost for active scope
FinalGate rejected for non-market safety reason
ticket invalidated after fresh signal
submit blocked after FinalGate pass
```

Owner should not be notified for:

```text
healthy waiting
ordinary market_not_satisfied
ordinary fresh_signal_absent
JSON export stale
local cache stale
rehearsal-only failure that does not affect current runtime
```

### Required Incident Categories

The target PG model must distinguish:

```text
auto_recoverable
owner_intervention_required
hard_safety_stop
diagnostic_only
```

### Required PG Tables Or Equivalent

The target design must include equivalent structures for:

```text
brc_runtime_incidents
brc_recovery_runs
brc_owner_intervention_cases
brc_notification_retries
brc_safety_halts
```

Exact names may change, but failure/recovery/intervention classification must
not be lost.

### Required Rejection Rules

The PG-backed chain must reject:

```text
ticket creation while critical PG current state is unavailable
FinalGate while exchange account facts are unavailable
Operation Layer submit while active position / open order state is unknown
Operation Layer submit while protection_ref is unknown
using local cache / JSON / MD / artifact as recovery truth
marking post-submit path complete without protection and reconciliation recovery
```

### Final Invariant

Confirmed rule:

```text
unknown critical safety or authority fact -> no real-submit progression.
Observation, diagnosis, and recovery remain allowed.
```

## Owner Confirmation Round 42 - Exchange / Account Authority Boundary

Recorded after the Owner confirmed the exchange and account authority boundary
recommendation.

### Confirmed Rule

Read-only account fact access must be separated from real exchange-write
authority.

Confirmed direction:

```text
watcher / monitor / fact writer
-> read-only account facts

FinalGate
-> inspect ticket-bound facts

Operation Layer
-> only official exchange write path
```

Rejected direction:

```text
worker detects signal
-> worker can read account
-> worker can directly write exchange order
```

### Plain-Language Meaning

PG化 decides current truth and exact trade identity.

Exchange authority boundary decides:

```text
谁有资格把一个候选状态变成真实交易所订单。
```

Only the official Operation Layer path may perform real exchange writes.

### Required Capability Separation

The target architecture must separate permissions like this:

| Layer | Allowed | Forbidden |
| --- | --- | --- |
| watcher | read market, write coverage / signal facts | exchange write |
| fact writer | write PG fact snapshot | submit order, modify position, modify leverage |
| server monitor | read PG / systemd / account-safe state, send notification | submit order, mutate profile |
| FinalGate | check ticket-bound safety facts | create order directly |
| Operation Layer | official submit / protection / lifecycle | reinterpret strategy semantics, bypass ticket |
| reconciliation | read exchange state, repair local lifecycle | create new trade intent |
| review | write review outcome | mutate current submit authority directly |

### Required Exchange-Write Binding

Every real exchange write must bind:

```text
ticket_id
finalgate_pass_id
operation_submit_command_id
```

and must be traceable through:

```text
operation_submit_command
-> exchange_order
-> order_lifecycle
-> protection
-> reconciliation
```

### Forbidden Authority Bypasses

The target architecture must reject:

```text
watcher directly calling exchange write
monitor directly calling Operation Layer submit
Candidate Pool directly submitting an order
Goal Status directly triggering an order
FinalGate directly creating an order
reconciliation creating a new trade intent
review result directly changing current ticket
any non-Operation Layer path writing to exchange
```

### Required Credential Boundary

Credential and secret mutation must remain outside the automatic trading chain.

Confirmed rule:

```text
credential / secret mutation is never authorized by signal, ticket, FinalGate,
Operation Layer, monitor, or recovery automation.
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
exchange write without operation_submit_command_id
exchange write without ticket_id
exchange write without finalgate_pass_id
exchange write from watcher / monitor / projector / Candidate Pool / Goal Status / FinalGate
exchange write that cannot be traced to official Operation Layer path
credential mutation from runtime automation
```

### Final Invariant

Confirmed rule:

```text
read-only account facts may inform decisions.
Only Operation Layer official path may create real exchange writes.
```

## Owner Confirmation Round 43 - Environment / Deployment / Cutover Safety

Recorded after the Owner confirmed the environment, deployment, and cutover
safety recommendation.

### Confirmed Rule

PG cutover must close schema, seed, runtime readers, old-source removal,
FinalGate ticket input, and Operation Layer ticket handoff in the same coherent
batch.

Confirmed direction:

```text
local PG full validation
-> migration + seed
-> runtime reads PG
-> old file authority removed
-> Tokyo deploy acceptance
```

Rejected direction:

```text
PG tables deployed
runtime still reads JSON authority
FinalGate still accepts loose params
Operation Layer can still bypass ticket
old chain remains as fallback
```

### Plain-Language Meaning

PG化 must not become a permanent half-cutover.

Temporary dual-write or comparison may exist only as migration verification,
not as the production runtime shape.

Production runtime shape must be:

```text
PG current state is the runtime truth.
JSON / MD / output are exports only.
old chain is deleted, cleaned, archived, or made non-authority.
```

### Required Environment Boundaries

The target operating model must distinguish:

| Environment | Role | Allowed | Forbidden |
| --- | --- | --- | --- |
| local PG | full development and validation | schema, seed, negative tests, migration rehearsal | production fact source |
| test PG | optional integration validation | end-to-end simulation, concurrency tests | real exchange submit |
| Tokyo PG | production current truth | runtime current state, audit, monitor | old JSON fallback |
| exchange account | real trading account | writes only through Operation Layer | any bypass write |

### Required Cutover Acceptance

PG cutover acceptance must prove:

```text
runtime readers no longer use old JSON / MD as authority
watcher scope comes from PG
Candidate Pool comes from PG
Action-Time Ticket comes from PG
FinalGate consumes ticket_id only
Operation Layer consumes ticket_id + finalgate_pass_id only
old fallback tests are removed or rewritten
server monitor reads PG
```

### Rollback Principle

Code may roll back and schema may be repaired by forward-fix, but production
must not roll back to old file authority as fallback.

Confirmed rollback boundary:

```text
if PG cutover has a critical failure
-> stop or disable trading progression
-> diagnose / forward-fix
-> do not revive old JSON / MD / output authority
```

### Forbidden Production Shapes

The target architecture must reject:

```text
long-term production dual-read PG + JSON
long-term production dual-write PG + JSON
PG failure fallback to old output
Tokyo monitor inferring production state from local cache
old FinalGate loose-parameter path retained
old Operation Layer loose-submit path retained
```

### Required Rejection Rules

The PG-backed runtime must reject:

```text
runtime authority read from repo MD / JSON / output
FinalGate call through old loose params
Operation Layer submit through old loose params
watcher scope from Candidate Pool export
server monitor production decision from local cache
fallback to old chain after PG read failure
```

### Final Invariant

Confirmed rule:

```text
PG cutover means replacement of runtime authority, not permanent coexistence
with the old file chain.
```

## Owner Confirmation Round 44 - Owner Surface / Explanation Product

Recorded after the Owner confirmed the Owner Surface and explanation product
recommendation.

### Confirmed Rule

Owner-facing surfaces must show product semantics and plain-language
explanations, while every explanation remains traceable to PG lineage.

Confirmed direction:

```text
Owner sees product state and plain-language reason
-> developer / audit detail can show internal technical lineage
-> every explanation can trace back to PG facts, ticket, and audit events
```

Rejected direction:

```text
Owner sees raw FinalGate / Operation Layer / RequiredFacts / artifact paths
-> Owner manually judges whether the system is healthy
```

### Plain-Language Meaning

The Owner should be able to understand:

```text
昨天市场有没有给机会
系统有没有抓到
有没有理论上该交易但没交易
没交易是市场原因、工程原因、授权原因还是安全原因
下一步谁处理
是否需要 Owner 授权或介入
```

without manually reading JSON, MD, logs, artifacts, or code-review summaries.

### Required Owner Fields

Owner-facing product surfaces must expose fields equivalent to:

| Field | Chinese meaning |
| --- | --- |
| `product_state` | 运行中 / 等待机会 / 处理中 / 暂不可用 / 需要介入 |
| `strategy_group_id` | 策略组 |
| `symbol` | 币种 |
| `side` | 方向 |
| `plain_event` | 人话信号描述 |
| `stage_reached` | 推进到哪一步 |
| `why_no_trade` | 为什么没交易 |
| `first_blocker` | 第一阻断 |
| `owner_action_required` | 是否需要 Owner 动作 |
| `next_system_action` | 系统下一步做什么 |
| `audit_ref` | 可追溯引用，不作为主展示 |

### Internal Terms Hidden From Main Owner Surface

These terms may appear in developer detail or audit views, but should not be
primary Owner language:

```text
FinalGate
Operation Layer
RequiredFacts
candidate
authorization evidence
preflight
proof chain
refId
raw artifact path
blocker code
runtime grant
```

Primary Owner language should translate them into:

```text
最终安全检查
官方提交路径
必需事实
候选机会
授权证据
交易前检查
审计链路
追溯编号
运行阻断
运行授权
```

### Required Notification Language

Owner notifications should map internal states to plain language:

| Internal state | Owner language |
| --- | --- |
| `fresh_signal_detected` | 检测到一个新机会 |
| `promotion_candidate_created` | 机会已通过策略条件，等待进入交易前检查 |
| `ticket_created` | 已生成交易前正式记录 |
| `finalgate_rejected` | 最终安全检查未通过 |
| `submit_accepted` | 已通过官方路径提交 |
| `protection_failed` | 订单保护异常，需要关注 |
| `reconciliation_mismatch` | 账户对账异常，需要关注 |
| `market_not_satisfied` | 市场条件还没满足 |
| `healthy_waiting` | 系统正常等待机会 |

### Forbidden Owner Surface Behavior

The target architecture must reject:

```text
Owner main surface requiring JSON / MD / artifact reading
Owner notification sending blocker code without plain explanation
ordinary engineering gap being packaged as Owner action
healthy waiting being packaged as abnormal
FinalGate / Operation Layer becoming primary Owner language
```

### Final Invariant

Confirmed rule:

```text
Owner-facing explanation is a product capability backed by PG lineage, not a
manual artifact-reading workflow.
```

## Owner Confirmation Round 45 - Agent / Skill Constraint

Recorded after the Owner confirmed the AI agent and skill constraint
recommendation.

### Confirmed Rule

All AI agents, skills, and task prompts must treat PG current state and audit
lineage as the explanation authority after PG cutover.

Confirmed direction:

```text
agent / skill
-> read PG current state and audit lineage
-> explain stage_reached / first_blocker / why_no_trade
-> cite ticket / signal / policy / audit refs
```

Rejected direction:

```text
agent / skill
-> read latest JSON files
-> infer runtime truth
-> produce explanation
```

### Plain-Language Meaning

PG化 must not be undermined by collaboration tools that continue reading old
exports as production truth.

If a skill or agent reads JSON/MD/output as authority after cutover, it becomes
a new legacy entry point.

### Required Agent / Skill Constraints

The target collaboration model must constrain:

| Object | Constraint |
| --- | --- |
| Codex planning | planning must use PG current state and durable docs |
| Claude implementation | must not add JSON fallback or old side scope |
| reviewer skill | must check PG lineage, negative tests, and old-source deletion |
| runtime-signal-forensics skill | no-trade explanation must read PG signal / ticket / blocker lineage |
| chain-position skill | chain position must come from PG projection, not old latest-* JSON truth |
| server monitor | must read Tokyo PG current state |
| task prompts | must forbid old JSON / MD / output authority |

### Forbidden Agent / Skill Behavior

The target constraints must reject:

```text
skill reading latest-*.json as production truth
agent treating MD as current policy
review checking happy path only while skipping negative constraints
Claude retaining DEFAULT_SIDE_SCOPE for compatibility
forensics explaining artifact state instead of PG lineage
task prompt allowing transitional fallback
```

### Required Documents / Skills To Update

The durable landing must update:

```text
docs/current/AI_AGENT_CONSTRAINTS.md
CLAUDE.md
docs/current/OWNER_RUNTIME_OPERATING_MODEL.md
docs/current/PRE_TRADE_RUNTIME_CONTRACT.md
runtime-signal-forensics/SKILL.md
chain-position/SKILL.md
reviewer/SKILL.md
```

or their final equivalent locations.

### Required Rejection Rules

The target collaboration model must reject:

```text
PG implementation task without explicit no-fallback rule
review conclusion that does not inspect old-source authority removal
forensics conclusion based on JSON exports when PG lineage exists
chain-position conclusion based on latest output artifacts when PG projection exists
skill update that keeps JSON-first behavior as production mode
```

### Final Invariant

Confirmed rule:

```text
AI agents and skills must explain the PG-backed system, not resurrect the old
file-backed system.
```

## Owner Confirmation Round 46 - Cutover Runtime Bootstrap

Recorded after the Owner confirmed the cutover runtime bootstrap recommendation.

### Confirmed Rule

Initial PG seed must not import old fresh signals, old action-time lanes, old
packets, or old runtime artifacts as current live state. After cutover, runtime
current facts must be rebuilt from real Tokyo runtime, watcher, live detector,
account reader, and server monitor sources.

Confirmed direction:

```text
PG seed:
strategy semantics / scope / policy / profile / sizing / protection

cutover bootstrap:
Tokyo watcher status
runtime coverage
exchange account facts
active position
open orders
balance
systemd / service health
```

Rejected direction:

```text
old output/latest-*.json
-> imported into PG current state
-> old file state becomes new database truth
```

### Plain-Language Meaning

PG seed may define what the system is allowed to do.

It must not pretend old file artifacts prove what is happening now.

Current runtime state after cutover must be refreshed from real sources:

```text
Tokyo watcher
live detector
exchange account reader
server monitor
PG-owned projectors
```

### Seed Versus Bootstrap Boundary

The target cutover must distinguish:

| Data type | May initial seed write it | Required source |
| --- | ---: | --- |
| strategy semantics | yes | confirmed L2-L7 semantics |
| Owner policy | yes | current authorized policy seed |
| historical replay / old signal | no | review / calibration / archive only |
| current account facts | no from old files | exchange / account reader at bootstrap |
| current watcher coverage | no from old JSON | watcher writes PG coverage |
| active position / open order | no from artifact | exchange confirmation |

### Required Bootstrap Actions

Cutover bootstrap must perform:

```text
read Tokyo PG migration version
start watcher from PG scope/event bindings
watcher writes runtime coverage
fact writer writes event-specific snapshots
account fact reader fetches balance / active position / open orders
server monitor writes monitor run
projection owners generate Candidate Pool / Daily Table / Goal Status exports
verify no old JSON / MD participates in current decision
```

### Forbidden Bootstrap Imports

The target architecture must reject importing:

```text
old SOR action_time_lane as current active lane
old Single Lane Packet as current task truth
old Candidate Pool action_time row as ticket
old Goal Status fresh_signal_processing as live_signal_event
old exchange/account artifact as current account fact
```

### Required Cutover Acceptance

Cutover acceptance must prove:

```text
current runtime coverage was written by watcher
current account facts were written by account reader
current live_signal_events are live-only
current projections are PG exports
no old latest-* JSON / packet / artifact entered PG current state
```

### Final Invariant

Confirmed rule:

```text
PG seed defines allowed semantics and policy.
Runtime bootstrap refreshes current facts from real runtime sources.
Old files do not seed current live state.
```

## Owner Confirmation Round 47 - Time / Candle / Market Data Authority

Recorded after the Owner confirmed the time, candle, and market data authority
recommendation.

### Confirmed Rule

All `event_time_ms` values must come from exchange market data closed-candle
time, not local machine time, file generation time, PG write time, monitor
refresh time, or export time.

Confirmed direction:

```text
exchange market data
-> closed candle
-> trigger_candle_close_time_ms
-> event_time_ms
-> live_signal_event
```

Rejected direction:

```text
script generated_at
-> event_time_ms
```

### Plain-Language Meaning

The important question is not when the system noticed or exported a signal.

The important question is:

```text
市场在哪一根已收盘K线确认了这次策略事件。
```

### Required Time Separation

The target PG model must keep these timestamps separate:

| Field | Authority |
| --- | --- |
| `event_time_ms` | trigger candle close time |
| `trigger_candle_open_time_ms` | exchange candle open time |
| `trigger_candle_close_time_ms` | exchange candle close time |
| `detected_at_ms` | system detection time |
| `written_at_ms` | PG write time |
| `exported_at_ms` | JSON / MD export time |

For the confirmed event specs, the invariant is:

```text
event_time_ms = trigger_candle_close_time_ms
```

### Required Signal Bindings

Every `live_signal_event` must bind:

```text
market_data_source_id
candle_snapshot_id
trigger_candle_open_time_ms
trigger_candle_close_time_ms
event_time_ms
```

### Required Market Data Quality Handling

The target chain must fail closed when:

| Condition | Blocker |
| --- | --- |
| trigger candle not closed | no event created |
| candle missing | `data_gap` |
| market data delayed beyond accepted window | `stale_market_data` |
| exchange/local clock skew too large | `clock_skew` |
| conflicting sources for same symbol/timeframe | `market_data_conflict` |

### Forbidden Time Behavior

The target architecture must reject:

```text
detected_at_ms replacing event_time_ms
written_at_ms replacing event_time_ms
exported_at_ms replacing event_time_ms
local system time replacing exchange candle time
unclosed candle creating fresh live_signal_event
same candle creating duplicate event identity
signal creation during market data gap
```

### Required PG Tables Or Equivalent

The target design must include equivalent structures for:

```text
brc_market_data_sources
brc_candle_snapshots
brc_market_data_quality_events
```

and uniqueness equivalent to:

```text
unique(symbol, timeframe, trigger_candle_open_time_ms, source)
```

Exact names may change, but candle and event-time authority must not.

### Required Rejection Rules

The PG-backed chain must reject:

```text
live_signal_event without candle_snapshot_id
live_signal_event without market_data_source_id
live_signal_event where event_time_ms != trigger_candle_close_time_ms
live_signal_event from unclosed candle
freshness decision based on detected_at / written_at / exported_at
```

### Final Invariant

Confirmed rule:

```text
Freshness is measured from market event time, not system processing time.
```

## Owner Confirmation Round 48 - Symbol / Instrument Authority

Recorded after the Owner confirmed the symbol and exchange instrument authority
recommendation.

### Confirmed Rule

PG must own the mapping between canonical strategy symbols and exchange
instruments.

Confirmed direction:

```text
canonical_symbol = ETHUSDT
exchange = binance
market_type = perpetual
exchange_instrument = ETH/USDT:USDT
settlement = USDT
```

Rejected direction:

```text
ETHUSDT / ETH-USDT / ETH/USDT:USDT
-> runtime guesses equivalence by string replacement
```

### Plain-Language Meaning

The system must know exactly:

```text
策略说的这个币
对应交易所哪个真实合约
```

It must not infer that relationship from naming conventions.

### Required Runtime Binding

The target PG-backed runtime must enforce:

```text
strategy scope uses canonical_symbol
exchange access uses exchange_instrument_id
ticket binds both canonical_symbol and exchange_instrument_id
Operation Layer uses ticket-bound exchange_instrument_id
reconciliation traces exchange order back to canonical_symbol
```

### Required PG Tables Or Equivalent

The target design must include equivalent structures for:

```text
brc_symbols
brc_exchange_instruments
brc_symbol_instrument_mappings
```

with fields equivalent to:

```text
canonical_symbol
base_asset
quote_asset
exchange_id
market_type
settlement_asset
exchange_instrument
instrument_status
price_precision
quantity_precision
min_notional
tick_size
lot_size
```

Exact names may change, but instrument identity authority must not.

### Required Rejection Rules

The PG-backed chain must reject:

```text
runtime string replacement to infer instrument
watcher inventing symbol format
ticket without exchange_instrument_id
Operation Layer using symbol not bound to ticket
exchange_order that cannot trace to canonical_symbol
candidate scope without active instrument mapping
multiple active instrument mappings without deterministic policy
```

### Required Fail-Closed Cases

The chain must fail closed when:

```text
canonical_symbol cannot map to exchange_instrument_id
mapping is inactive
mapping is ambiguous
instrument precision is missing
instrument min_notional / tick_size / lot_size is missing
exchange reports instrument unavailable
```

### Final Invariant

Confirmed rule:

```text
canonical_symbol and exchange_instrument must be explicitly mapped in PG.
No runtime path may guess instrument identity from strings.
```

## Owner Confirmation Round 49 - Price / Quantity / Precision Authority

Recorded after the Owner confirmed the price, quantity, and precision authority
recommendation.

### Confirmed Rule

Ticket may carry target notional, leverage, side, and protection intent, but
final order quantity and price normalization must be computed from PG-owned
instrument specs, exchange rules, and Decimal arithmetic before Operation Layer
submit.

Confirmed direction:

```text
ticket notional / leverage / side
+ PG instrument precision
+ exchange min_notional / tick_size / lot_size
+ current price reference
-> normalized order quantity / price
-> operation_submit_command
```

Rejected direction:

```text
ticket has notional
-> float math computes quantity
-> submit directly
```

### Plain-Language Meaning

The trading signal may be valid, and the ticket may be authorized, but exchange
submit still requires an order shape the exchange will accept:

```text
quantity satisfies lot size
price satisfies tick size
notional satisfies minimum notional
precision is within exchange limits
```

### Required Calculation Rules

The target runtime must enforce:

```text
all financial amount / price / quantity calculations use Decimal
instrument precision / tick_size / lot_size / min_notional comes from PG instrument mapping
Operation Layer normalizes quantity and price before accepted submit command
normalized order intent is persisted in PG
rounding policy is explicit and shared
min_notional / precision / lot_size failure blocks submit
```

### Required Submit Command Fields

The target PG-backed submit command must record fields equivalent to:

```text
ticket_id
exchange_instrument_id
side
order_type
target_notional
leverage
price_reference
raw_quantity
normalized_quantity
normalized_price
rounding_policy
min_notional_check
tick_size_check
lot_size_check
precision_check
```

Exact column names may change, but normalized intent must remain auditable.

### Forbidden Behavior

The target architecture must reject:

```text
float financial calculations
different scripts choosing their own rounding behavior
Operation Layer bypassing instrument precision
submit command without normalized quantity
submit command without precision checks
exchange rejection treated as submit accepted
submit when min_notional is not satisfied
```

### Required Fail-Closed Cases

The chain must fail closed when:

```text
instrument precision is missing
tick_size is missing
lot_size is missing
min_notional is missing
quantity cannot normalize into valid lot size
price cannot normalize into valid tick size
target notional cannot satisfy min_notional
price reference is stale or missing
```

### Final Invariant

Confirmed rule:

```text
Operation Layer submits only normalized, Decimal-computed, instrument-valid
orders.
```

## Owner Confirmation Round 50 - Order Type / Time-In-Force / Reduce-Only Boundary

Recorded after the Owner confirmed the order type, time-in-force, and
reduce-only boundary recommendation.

### Confirmed Rule

Order type, time-in-force, reduce-only, post-only, close-position, slippage, and
submit-deadline semantics must come from PG execution policy and ticket-bound
execution intent, not Operation Layer script defaults.

Confirmed direction:

```text
runtime profile / execution policy
-> ticket-bound execution intent
-> FinalGate checks execution intent
-> Operation Layer submit command
```

Rejected direction:

```text
Operation Layer sees side=long
-> defaults to market order
-> defaults time_in_force
-> defaults reduce_only=false
```

### Plain-Language Meaning

The strategy and ticket decide what kind of execution is allowed.

Operation Layer only submits the already-approved execution intent. It must not
invent order behavior at the last step.

### Required Execution Policy Binding

The target PG-backed runtime must enforce:

```text
execution policy binds runtime_profile / strategy / event / side
Action-Time Ticket references execution_policy_version
FinalGate checks execution intent against current policy
Operation Layer executes only ticket-bound execution intent
order_type / time_in_force / reduce_only / post_only / close_position are persisted
script defaults cannot fill missing execution authority fields
```

### Required Execution Intent Fields

The target submit command or ticket-bound execution intent must record fields
equivalent to:

```text
execution_policy_id
execution_policy_version
order_type
time_in_force
reduce_only
post_only
close_position
allowed_slippage_bps
price_protection_mode
submit_deadline_ms
cancel_if_not_filled_policy
```

Exact names may change, but execution semantics must remain explicit and
auditable.

### Forbidden Behavior

The target architecture must reject:

```text
Operation Layer defaulting to market order by itself
submit while time_in_force is missing
submit while reduce_only is undefined
post_only / close_position decided by script default
open-position ticket executed as close-position order
protection order execution semantics diverging from the approved protection policy
```

### Required Fail-Closed Cases

The chain must fail closed when:

```text
execution_policy_id is missing
execution_policy_version is stale
order_type is not allowed by current policy
time_in_force is missing or disallowed
reduce_only conflicts with ticket intent
post_only / close_position conflicts with ticket intent
submit_deadline_ms has expired
slippage policy cannot be checked
```

### Final Invariant

Confirmed rule:

```text
Operation Layer may normalize and submit an approved execution intent.
It must not invent execution semantics.
```

## Owner Confirmation Round 51 - Margin / Position Mode / Leverage Mutation

Recorded after the Owner confirmed the margin mode, position mode, and leverage
mutation recommendation.

### Confirmed Rule

Margin mode, position mode, and leverage must be defined by PG runtime profile
and confirmed by account facts before submit. Operation Layer must not mutate
exchange account mode or leverage inside the signal submit path.

Confirmed direction:

```text
PG runtime profile
-> expected margin mode / position mode / leverage
-> account reader confirms exchange actual state
-> ticket binds confirmed account mode snapshot
-> FinalGate checks expected == actual
-> Operation Layer submits
```

Rejected direction:

```text
prepare to submit
-> leverage or account mode differs
-> Operation Layer mutates exchange settings
-> submit continues
```

### Plain-Language Meaning

Exchange account mode is not a small execution parameter. It changes how risk,
position direction, and liquidation behavior work.

The system may submit only when the expected account mode and actual exchange
account mode already match.

### Required Runtime Profile Binding

The target PG-backed runtime must enforce:

```text
runtime_profile defines expected margin_mode
runtime_profile defines expected position_mode
runtime_profile defines leverage policy
account fact reader reads actual exchange mode
ticket binds account_mode_snapshot_id
FinalGate checks expected mode equals actual mode
Operation Layer does not mutate margin / position / leverage in submit path
```

If automatic leverage or account-mode mutation is ever allowed, it must be a
separate policy-governed administrative action, not part of the signal submit
path.

### Required Account Mode Fields

The target ticket or ticket-bound account snapshot must record fields equivalent
to:

```text
runtime_profile_id
expected_margin_mode
expected_position_mode
expected_leverage
actual_margin_mode
actual_position_mode
actual_leverage
position_side
account_mode_snapshot_id
mode_checked_at_ms
```

Exact names may change, but account-mode proof must remain auditable.

### Forbidden Behavior

The target architecture must reject:

```text
set leverage immediately before submit
change isolated / cross immediately before submit
switch one-way / hedge mode immediately before submit
ticket without account_mode_snapshot_id
FinalGate skip of actual account mode check
Operation Layer defaulting position_side
signal submit path mutating account configuration
```

### Required Fail-Closed Cases

The chain must fail closed when:

```text
actual margin mode cannot be read
actual position mode cannot be read
actual leverage cannot be read
expected margin mode != actual margin mode
expected position mode != actual position mode
expected leverage policy not satisfied
position_side cannot be determined from ticket and account mode
```

### Final Invariant

Confirmed rule:

```text
Signal submit may use only an already-compatible exchange account mode.
It must not mutate exchange account configuration to make a signal executable.
```

## Owner Confirmation Round 52 - Capital / Exposure Budget

Recorded after the Owner confirmed the capital, exposure, and budget reservation
recommendation.

### Confirmed Rule

Before an Action-Time Ticket can move toward real submit, it must have a
PG-backed budget reservation. The reservation must be short-lived, releasable,
auditable, and bound to current policy versions.

Confirmed direction:

```text
promotion winner
-> budget reservation
-> Action-Time Ticket
-> FinalGate checks reservation still valid
-> Operation Layer submit consumes reservation
```

Rejected direction:

```text
multiple candidates see available balance
-> each creates ticket
-> candidates race for the same account budget
```

### Plain-Language Meaning

Multi-strategy and multi-symbol observation is wide.

Real-submit budget must be narrow:

```text
Owner defines budget boundaries.
System reserves budget for the selected candidate.
Other candidates cannot spend the same budget at the same time.
```

This is not a conservative slowdown. It is the machine form of the Owner's
already-authorized risk boundary.

### Required Budget Reservation Rules

The target PG-backed runtime must enforce:

```text
Owner policy defines account / runtime profile / StrategyGroup / symbol / side budget scope
only promotion arbitration winner may request real-submit budget reservation
same account/profile budget cannot be double-reserved by multiple active tickets
reservation requires expires_at_ms
reservation is initially scoped to promotion_candidate_id and action_time_lane_input_id
ticket references budget_reservation_id
reservation may backfill ticket_id after ticket creation
FinalGate checks reservation is active and not expired
Operation Layer submit consumes reservation
ticket expired / rejected / invalidated releases reservation
```

### Required Reservation Fields

The target PG model must record fields equivalent to:

```text
budget_reservation_id
promotion_candidate_id
action_time_lane_input_id
ticket_id nullable unique
signal_event_id
event_spec_id
runtime_profile_id
account_id
strategy_group_id
symbol
side
target_notional
leverage
reserved_margin
reserved_at_ms
expires_at_ms
status
release_reason
policy_version
```

Exact names may change, but reservation lineage and lifecycle must not.
The reservation must not require `ticket_id` at initial insert. Otherwise the
schema creates a circular dependency because the ticket itself must reference an
already active reservation.

### Forbidden Behavior

The target architecture must reject:

```text
available_balance check without budget reservation
multiple active tickets spending the same account budget
ticket without budget_reservation_id
submit after reservation expiry
FinalGate skipping reservation check
submit failure leaving reservation locked forever
policy shrink while old reservation remains valid without revalidation
```

### Required Fail-Closed Cases

The chain must fail closed when:

```text
budget reservation cannot be created
reservation expired
reservation policy_version is stale
reserved margin exceeds current budget
available balance cannot be confirmed
reservation status is not active
ticket and reservation lineage do not match
```

### Final Invariant

Confirmed rule:

```text
real-submit candidate must reserve budget before ticket / FinalGate / Operation
Layer can proceed.
Available balance alone is not sufficient.
```

## Owner Confirmation Round 53 - Protection Reference / Stop Authority

Recorded after the Owner confirmed the protection reference and stop authority
recommendation.

### Confirmed Rule

Every Action-Time Ticket must bind a strategy-event-derived protection reference.
Operation Layer must not invent stop or invalidation levels at submit time.

Confirmed direction:

```text
event-specific facts
-> protection_ref
-> ticket
-> FinalGate checks protection_ref
-> Operation Layer submits main order
-> protection service attaches protection
```

Rejected direction:

```text
no protection price before submit
-> Operation Layer guesses a percent stop
-> submit continues
```

### Plain-Language Meaning

The signal belongs to a strategy event, so the protection must also come from
that strategy event's facts.

The system must not create a valid strategy ticket and then attach a stop level
that was guessed by execution code.

### Strategy-Specific Protection References

The current event specs must define protection references equivalent to:

| Strategy / Event | Protection reference |
| --- | --- |
| CPM-RO-001 / CPM-LONG | pullback_low_reference |
| MPG-001 / MPG-LONG | momentum_floor_reference |
| MI-001 / MI-LONG | impulse invalidation / fast reversal threshold |
| SOR-001 / SOR-LONG | opening_range_low / session invalidation |
| SOR-001 / SOR-SHORT | opening_range_high / reclaim invalidation |
| BRF2-001 / BRF2-SHORT | rally_high_reference |

Exact field names may change, but each event spec must have a defined
protection source.

### Required Protection Flow

The target PG-backed runtime must enforce:

```text
event_spec defines protection_ref type
fact_snapshot produces the corresponding protection_ref
ticket binds protection_ref_id
FinalGate checks protection_ref is fresh / valid / side-consistent
Operation Layer rejects submit without protection_ref
protection service links protection state to ticket_id + order_id
complete submit success requires protection confirmation
```

### Required Protection Fields

The target PG model must record fields equivalent to:

```text
protection_ref_id
event_spec_id
strategy_group_id
symbol
side
reference_type
reference_price
invalidation_condition
stop_order_type
stop_time_in_force
protection_policy_version
source_fact_snapshot_id
expires_at_ms
```

Exact names may change, but protection authority and lineage must not.

### Forbidden Behavior

The target architecture must reject:

```text
ticket creation without protection_ref
FinalGate entry without protection_ref
Operation Layer guessing stop price
long protection_ref used for short
short protection_ref used for long
protection_ref sourced from old JSON / MD / artifact
main order accepted while detached protection is still marked complete success
```

### Required Fail-Closed Cases

The chain must fail closed when:

```text
protection_ref cannot be generated from event-specific facts
protection_ref is stale
protection_ref side does not match ticket side
protection_ref event_spec_id does not match ticket event_spec_id
reference_price cannot satisfy exchange precision
protection order cannot be attached
protection state cannot trace to ticket_id and order_id
```

### Final Invariant

Confirmed rule:

```text
Signal, ticket, submit, protection, and review must share one event-derived
protection lineage.
```

## Owner Confirmation Round 54 - Strategy / Event Spec Versioning

Recorded after the Owner confirmed the strategy, event spec, RequiredFacts,
policy, execution, and protection versioning recommendation.

### Confirmed Rule

StrategyGroup, event specs, RequiredFacts, Owner policy, execution policy, and
protection policy must be versioned. Signals, promotions, tickets, orders, and
reviews must bind the versions that were current when they were created.

Confirmed direction:

```text
strategy_group_version
event_spec_version
required_facts_version
policy_version
execution_policy_version
protection_policy_version
-> live_signal_event
-> promotion_candidate
-> action_time_ticket
-> order
-> review
```

Rejected direction:

```text
event spec changes today
-> yesterday's signal / ticket / review is reinterpreted under today's rules
```

### Plain-Language Meaning

Strategies will evolve. A later strategy definition must not rewrite what was
true at the time an old signal, ticket, order, or review was created.

Historical review must answer:

```text
under the strategy and policy versions that existed then, was this event valid
and what happened afterward?
```

It must not answer:

```text
under today's changed strategy definition, should the old signal be treated as
if it never existed?
```

### Required Version Bindings

The target PG-backed runtime must bind fields equivalent to:

```text
strategy_group_version_id
event_spec_version_id
required_facts_version_id
owner_policy_version
runtime_profile_version
sizing_policy_version
execution_policy_version
protection_policy_version
created_under_versions_hash
```

Exact names may change, but version lineage must not disappear.

### Required Version Behavior

The target architecture must enforce:

```text
live_signal_event binds event_spec_version and required_facts_version
promotion_candidate inherits live_signal_event versions
Action-Time Ticket binds policy / runtime / sizing / execution / protection versions
order lifecycle inherits ticket version lineage
review uses the versions bound to signal / ticket / order
new versions affect only future events
old active tickets must revalidate or invalidate after relevant version changes
retired versions remain readable for historical lineage
```

### Forbidden Behavior

The target architecture must reject:

```text
event_spec update rewriting old live_signal_event meaning
RequiredFacts update rewriting old fact satisfaction
deleting old versions so historical tickets cannot be explained
review evaluating old order under current strategy definition
FinalGate checking old active ticket under new versions without revalidation
policy version change leaving old active ticket usable without revalidation
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
live_signal_event without event_spec_version_id
promotion_candidate without inherited version lineage
ticket without policy / runtime / sizing / execution / protection versions
FinalGate call for ticket with stale relevant version
Operation Layer submit for ticket with stale relevant version
review record without signal / ticket / order version lineage
```

### Final Invariant

Confirmed rule:

```text
new versions affect future runtime behavior.
historical evidence is interpreted under the versions that created it.
active tickets must revalidate or invalidate when relevant versions change.
```

## Owner Confirmation Round 55 - Live Signal / Promotion / Lane State Machines

Recorded after the Owner confirmed the Live Signal, Promotion Candidate, and
Action-Time Lane state-machine recommendation.

### Confirmed Rule

Live Signal, Promotion Candidate, Action-Time Lane, and Action-Time Ticket must
be independent state machines. They must not collapse into one broad
`ready=true` flag.

Confirmed direction:

```text
live_signal_event.status
-> promotion_candidate.status
-> action_time_lane_input.status
-> action_time_ticket.status
```

Rejected direction:

```text
fresh_signal=true
-> system vaguely treats it as near-tradable
```

### Plain-Language Meaning

These are different stages:

```text
Live Signal = 市场喊了一声“有机会”
Promotion Candidate = 系统说“这个机会有资格排队”
Action-Time Lane = 系统说“这一个候选先进窄门”
Action-Time Ticket = 系统说“这笔具体交易是谁”
```

Fresh signal does not mean ready to submit. Promotion candidate does not mean a
ticket exists. Action-time lane does not mean FinalGate passed.

### Required Live Signal Statuses

The target PG model must support statuses equivalent to:

| Status | Chinese name | Meaning |
| --- | --- | --- |
| `detected` | 已检测 | Market event was detected by live detector |
| `facts_validated` | 事实已验证 | RequiredFacts are satisfied |
| `stale` | 已过期 | Freshness window expired |
| `rejected` | 已拒绝 | Event invalid or facts mismatch |
| `superseded` | 被替代 | Newer equivalent event appeared |

### Required Promotion Candidate Statuses

The target PG model must support statuses equivalent to:

| Status | Chinese name | Meaning |
| --- | --- | --- |
| `eligible` | 可升级 | Signal, scope, coverage, and policy allow candidate entry |
| `blocked` | 被阻断 | Candidate has one clear first_blocker |
| `arbitration_pending` | 等待仲裁 | Candidate waits for PG arbitration |
| `arbitration_won` | 仲裁胜出 | Candidate selected into narrow lane |
| `arbitration_lost` | 仲裁落选 | Candidate lost to higher-priority candidate |
| `expired` | 已过期 | Candidate expired |

### Required Action-Time Lane Statuses

The target PG model must support statuses equivalent to:

| Status | Chinese name | Meaning |
| --- | --- | --- |
| `opened` | 已打开 | Arbitration winner entered action-time lane |
| `facts_refreshing` | 刷新交易前事实 | Account, price, protection, and budget facts are refreshing |
| `ticket_pending` | 等待票据 | Ticket issuance is in progress |
| `ticket_created` | 票据已生成 | Formal Action-Time Ticket exists |
| `closed` | 已关闭 | Lane ended normally |
| `expired` | 已过期 | Lane exceeded valid window |
| `invalidated` | 已失效 | Policy, facts, account, coverage, or version changed |

Exact names may change, but the stage separation must not.

### Required Legal Transitions

The final PG specification must define legal transition graphs, not only status
names.

| State machine | Allowed transitions |
| --- | --- |
| `brc_live_signal_events` | `detected -> facts_validated`; `detected -> rejected`; `facts_validated -> stale`; `facts_validated -> superseded`; `detected -> stale` |
| `brc_promotion_candidates` | `eligible -> arbitration_pending`; `eligible -> blocked`; `arbitration_pending -> arbitration_won`; `arbitration_pending -> arbitration_lost`; `eligible/arbitration_pending/arbitration_won/arbitration_lost -> expired` |
| `brc_action_time_lane_inputs` | `opened -> facts_refreshing`; `facts_refreshing -> ticket_pending`; `ticket_pending -> ticket_created`; open states may move to `closed`, `expired`, or `invalidated` according to expiry and revalidation rules |
| `brc_action_time_tickets` | `created -> preflight_pending`; `preflight_pending -> finalgate_ready`; `preflight_pending -> finalgate_rejected`; `finalgate_ready -> submitted`; `created/preflight_pending/finalgate_ready -> expired/superseded/invalidated`; `submitted -> closed` |

Forbidden examples:

```text
expired -> finalgate_ready
finalgate_rejected -> submitted
submitted -> submitted
closed -> preflight_pending
arbitration_lost -> arbitration_won
rejected live signal -> facts_validated
```

### Required Transition Audit

Every state transition must write an append-only event equivalent to:

```text
from_status
to_status
transition_reason
trigger_ref
writer
occurred_at_ms
```

### Forbidden Behavior

The target architecture must reject:

```text
fresh_signal=true directly meaning order-ready
promotion_candidate directly meaning ticket exists
action_time_lane without lifecycle status
expired lane with still-active ticket
arbitration_lost candidate generating real-submit ticket
projection layer advancing state by itself
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
promotion without valid live_signal_event state
action-time lane without arbitration_won promotion
ticket creation from expired / blocked / arbitration_lost candidate
FinalGate entry from expired / invalidated lane
submit path from ticket whose upstream lane is expired / invalidated
state transition without audit event
```

### Final Invariant

Confirmed rule:

```text
each stage advances only from a valid previous stage, and each transition is
auditable.
```

## Owner Confirmation Round 56 - Review To Strategy Governance

Recorded after the Owner confirmed the review-to-strategy-governance
recommendation.

### Confirmed Rule

Review outcomes may produce strategy governance recommendations and decisions,
but they must not directly mutate current submit authority or active tickets.

Confirmed direction:

```text
signal / ticket / order / no-trade outcome
-> review outcome
-> strategy governance decision
-> new policy / event_spec / scope version
-> future runtime behavior
```

Rejected direction:

```text
positive review
-> automatically expands symbol / side / leverage / live submit
```

### Plain-Language Meaning

Review teaches the strategy and governance layer what to do next.

It does not bypass the authority model. Any real change to runtime behavior must
enter through versioned policy, event spec, RequiredFacts, scope, sizing,
execution, or protection changes.

### Required Review Lineage

The target PG-backed review model must record:

```text
signal_event_id
ticket_id
order_id
stage_reached
first_blocker
market_after_event
execution_outcome
strategy_learning
governance_recommendation
owner_action_required
created_under_versions_hash
```

When no order exists, review must still bind the no-trade lineage:

```text
signal_event_id
promotion_candidate_id
action_time_lane_input_id
first_blocker
stage_reached
```

as applicable.

### Required Governance Actions

The target model must support governance actions equivalent to:

| Action | Chinese name | Directly changes submit authority |
| --- | --- | ---: |
| `keep_observing` | 继续观察 | no |
| `revise_event_spec` | 修改事件定义 | no; creates new version |
| `revise_required_facts` | 修改必需事实 | no; creates new version |
| `narrow_scope` | 缩小币种/方向范围 | via policy version |
| `pause_strategy` | 暂停策略 | via policy version |
| `retire_strategy` | 下线策略 | via policy version |
| `promote_stage` | 升级阶段 | requires Owner policy version |
| `expand_scope` | 扩大范围 | requires Owner policy version and negative tests |
| `increase_budget` | 增加预算 | requires Owner policy version |

### Required Governance Flow

The target architecture must enforce:

```text
review_outcome -> recommendation
recommendation -> governance_decision
governance_decision -> policy/spec/scope version change
version change -> future runtime
```

### Forbidden Behavior

The target architecture must reject:

```text
review automatically expanding symbol scope
review automatically enabling unsupported side
review automatically increasing leverage / notional
review skipping event_spec versioning
review directly writing current policy
review directly changing active ticket
review using current strategy version to judge old order without historical version lineage
```

### Required PG Tables Or Equivalent

The target design must include equivalent structures for:

```text
brc_strategy_review_outcomes
brc_strategy_governance_decisions
brc_strategy_governance_decision_events
brc_strategy_policy_change_requests
```

Exact names may change, but review-to-governance separation must not.

### Final Invariant

Confirmed rule:

```text
review informs future governance through versioned changes.
It does not directly grant current submit authority.
```

## Owner Confirmation Round 57 - Owner Policy Operations

Recorded after the Owner confirmed the Owner policy operations recommendation.

### Confirmed Rule

Owner operations must be PG policy events that create new policy versions. They
must not be chat conclusions, MD edits, JSON patches, or agent memory.

Confirmed direction:

```text
Owner decision
-> policy change request
-> validation
-> new policy version
-> affected tickets / lanes revalidated or invalidated
```

Rejected direction:

```text
Owner says "this is ok" in chat
-> agent remembers it
-> runtime treats it as current authorization
```

### Plain-Language Meaning

Owner sets boundaries. The system runs inside those boundaries.

When boundaries change, the change must be versioned, auditable, validated, and
propagated to affected candidates, lanes, and tickets.

### Required Owner Operations

The target PG-backed policy model must support operations equivalent to:

| Operation | Chinese name | Effect |
| --- | --- | --- |
| `enable_strategy` | 启用策略 | Allow observation / candidacy |
| `pause_strategy` | 暂停策略 | Block new promotion / ticket |
| `resume_strategy` | 恢复策略 | Allow runtime under policy again |
| `retire_strategy` | 下线策略 | Close future runtime |
| `narrow_scope` | 缩小范围 | Remove symbol / side / event scope |
| `expand_scope` | 扩大范围 | Add symbol / side / event scope after validation |
| `enable_ticket_eligibility` | 允许生成 ticket | Allow formal pre-trade ticket stage |
| `disable_ticket_eligibility` | 禁止生成 ticket | Observation / candidacy only |
| `enable_real_submit` | 允许真实提交 | Allow real-submit narrow lane |
| `disable_real_submit` | 关闭真实提交 | Block FinalGate-to-submit progression |
| `set_budget` | 设置预算 | Set notional / leverage / margin scope |
| `set_runtime_profile` | 设置运行配置 | Bind account / environment / execution policy |
| `set_notification_policy` | 设置通知策略 | Configure Feishu / Owner notification rules |

Exact operation names may change, but these governance capabilities must remain
first-class.

### Required Validation Rules

The target policy operation path must validate:

```text
expand_scope -> event_spec / RequiredFacts / negative tests exist
enable_real_submit -> ticket / FinalGate / Operation Layer / protection / reconciliation closed
set_budget -> within account / profile / strategy caps
set_runtime_profile -> exchange account mode confirmed
disable / pause -> affected active tickets revalidated or invalidated
```

### Forbidden Behavior

The target architecture must reject:

```text
chat authorization as runtime policy
MD edit as current policy
JSON patch directly changing submit authority
agent automatically expanding scope
review automatically opening real_submit
enable of unvalidated scope
policy change that does not affect old active tickets
```

### Required Rejection Rules

The PG-backed chain must reject:

```text
policy operation without audit event
policy operation without new policy version
policy operation that bypasses validation
ticket using policy version superseded by an incompatible operation
real-submit enable without closed ticket / gate / operation / protection / reconciliation path
```

### Final Invariant

Confirmed rule:

```text
Owner authority becomes runtime authority only through validated PG policy
events and versions.
```

## Owner Confirmation Round 58 - Implementation Boundaries / Durable Doc Landing

Recorded after the Owner confirmed the implementation boundaries and durable
document landing recommendation.

### Confirmed Rule

This temporary draft must not remain as a long-term authority. After the
grilling session is complete, confirmed decisions must be split into durable
project documents, PG table design, agent constraints, skill constraints, and
the PG implementation task prompt.

Confirmed direction:

```text
temporary draft
-> final synthesis
-> durable docs
-> PG table design
-> agent / skill constraints
-> PG implementation task prompt
```

Rejected direction:

```text
temporary draft remains as authority
durable docs stay stale
new implementation branch reads both old docs and temporary draft
two design authorities reappear
```

### Plain-Language Meaning

The temporary draft is a conversation ledger and synthesis source.

It must not become another competing contract. Once confirmed, the durable docs
must become the single design source for the PG implementation branch.

### Required Durable Landing Targets

Confirmed content must land in:

| Content | Target document |
| --- | --- |
| L2-L7 chain responsibilities | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| Five StrategyGroup symbol / side / event semantics | `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` |
| PG tables and constraints | `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| PG architecture and source-of-truth boundary | `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md` |
| Old MD / JSON / output cleanup | `docs/current/REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md` |
| Owner operations and plain language | `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| Agent / Claude / skill constraints | `docs/current/AI_AGENT_CONSTRAINTS.md`, `CLAUDE.md`, and relevant skills |
| Deployment and cutover | `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` |
| Server-side monitoring | `docs/current/SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md` |

### Required PG Implementation Scope

The PG implementation task must cover the coherent chain in one design:

```text
schema
seed
migration validation
negative tests
runtime readers
watcher scope from PG
Candidate Pool from PG
ticket issuer
FinalGate ticket input
Operation Layer ticket handoff
old-source removal
server monitor PG-first
agent / skill constraint update
```

### Forbidden Implementation Shapes

The target implementation must reject:

```text
only creating tables without cutting runtime readers
only seeding PG while keeping old fallback
only updating Candidate Pool while leaving Goal Status / monitor / forensics old-source based
happy-path tests without negative constraint tests
JSON fallback retained for later cleanup
loose FinalGate parameter path retained
loose Operation Layer submit path retained
```

### Required Rejection Rules

The PG implementation must reject:

```text
runtime decision source from repo MD / JSON / output
dual long-term truth between PG and old files
FinalGate input without ticket_id
Operation Layer input without ticket_id + finalgate_pass_id
watcher scope from Candidate Pool export
agent / skill explanation from JSON exports when PG lineage exists
```

### Final Invariant

Confirmed rule:

```text
PG implementation must be driven by durable docs, not by a temporary chat draft.
No long-term fallback, MVP, or dual-source runtime authority is accepted.
```

## Temporary Glossary

| English term | Chinese term | Plain explanation |
| --- | --- | --- |
| Candidate Universe | 候选交易范围 | 哪些策略、币种、方向允许被观察和推进 |
| Runtime Coverage | 服务器运行覆盖 | 服务器是否真的在跑这条策略/币种/方向 |
| Market Facts | 市场事实 | 市场条件是否已经按策略规则计算 |
| Fresh Signal | 新鲜交易信号 | 真实市场刚刚出现的可交易机会 |
| Candidate Pool | 候选池 | 多个机会里选择哪个最接近交易前链路 |
| Promotion Candidate | 可升级候选 | 可以继续往交易前链路推进的机会 |
| Action-Time Lane | 临近交易通道 | 被系统选中的一条最接近交易的通道 |
| Action-Time Ticket | 交易前正式票据 | 唯一说明“这笔交易是谁”的机器记录 |
| Scope | 范围 | 允许的策略、币种、方向、资金、杠杆边界 |
| Side | 交易方向 | long 做多，short 做空 |

## Resolved Grilling Decisions

The grilling session resolved these decisions at design level:

| Decision area | Resolution | Durable landing place |
| --- | --- | --- |
| StrategyGroup side and symbol scope | Five active StrategyGroups have explicit symbol and side scopes; unsupported opposite sides are rejected, not mirrored | `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` |
| Fresh signal definition | Fresh signal is a real strategy event with market event time, not artifact refresh time | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| PG persistence before action-time | Event spec, candidate scope binding, runtime coverage, fact snapshot, live signal, promotion, lane, budget, protection, and ticket lineage are required | `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| Forced side mirroring prevention | Candidate scope and event bindings come from PG, not broad side defaults | `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| Action-Time Ticket proof | FinalGate consumes only `ticket_id`; Operation Layer consumes only `ticket_id + finalgate_pass_id` | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |

Remaining work is implementation-detail specification only: exact migration file
ordering, exact service entrypoints, exact repository method names, and exact
validator command names. These must not reopen the resolved strategy semantics.

## Non-Authority Boundary

This draft does not authorize:

```text
FinalGate bypass
Operation Layer bypass
exchange write
live profile expansion
order sizing expansion
forced side expansion
repo MD/JSON runtime decision source
```
