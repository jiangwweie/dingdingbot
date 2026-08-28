---
title: EXIT_PROFILE_AUTHORITY_V1_PRODUCTION_DESIGN
status: DESIGN_REVIEW_REQUIRED
date: 2026-08-28
program: EX-P1
base_candidate: 1c57b407c8f7ae5dcd2a15b40fb4f49366012b00
implementation_authority: NONE
production_authority: NONE
---

# ExitProfile Authority V1 Production Design

## 1. Decision

The Trading Kernel will replace Event-bound runtime ExitPolicy authority with
an immutable **ExitProfile Catalog** plus versioned **EventExitBinding**
authority:

```text
EventSpec
    ↓ exact active EventExitBinding
ExitProfile
    ↓ frozen into CapacityClaim
immutable Ticket
    ↓ exact Profile identity only
Lifecycle Worker
```

The first release installs Owner-frozen V1 parameters directly. There is no
Replay, Shadow, optimization or research gate. This is an explicit
loss-capable production hypothesis, not a claim of statistically optimal exit
parameters.

The design preserves the existing execution chain:

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

It does not add a second lifecycle engine, strategy-specific exit branch,
additional position, second TP tranche, position add, second Stop owner or new
persistent Worker.

## 2. Owner-Frozen Inputs

The following decisions are final inputs to this design:

1. no YAML/YML configuration or runtime file authority;
2. no Replay or Shadow gate before installing V1 parameters;
3. EventSpec and ExitProfile require independent version identities;
4. CapacityClaim and Ticket freeze both Binding and Profile identity;
5. ExitProfile semantic content is immutable;
6. retired Profile remains exact-loadable for an already-issued Ticket;
7. illegal TP1/Runner materialization fails closed and never changes the
   Profile fraction;
8. holding bars start from real `EntryFilled` exposure and count only closed
   venue candles;
9. PR #4 and candidate `1c57b407` remain frozen and independent;
10. the migration revision is named `NEXT_AFTER_0006` until the integration
    lane assigns its final Alembic number.

## 3. Current Tracked Facts

### 3.1 Existing capability

The current Kernel already freezes:

```text
TradeTicket.exit_policy_id
TradeTicket.exit_policy_semantic_hash
```

and Lifecycle exact-loads that identity before evaluating exits. CapacityClaim
already carries the same Profile-shaped identity, and current sizing derives
one TP1 quantity plus one Runner quantity.

### 3.2 Current coupling

Current ExitPolicy authority is Event-bound in four places:

1. `registered_exit_policies()` creates one Policy from every Strategy
   Contract through `_policy_for_contract()`;
2. `brc_exit_policies.event_spec_id` is non-null and unique;
3. Lifecycle requires `policy.event_spec_id == ticket.event_spec_id`;
4. retiring a StrategyVersion also retires its Event Policies.

This allows versioned Policy lookup but does not permit independent Profile
assignment or reuse.

### 3.3 Current pre-TP1 gap

When TP1 has not filled, Lifecycle returns `NO_CHANGE` immediately if both SOR
reclaim and session-expiry references are absent. Consequently a future MI or
BRF2 `time_stop` cannot run before TP1 even though the pure ExitPolicy engine
already supports time stops.

### 3.4 Current time basis gap

Lifecycle currently passes `Ticket.created_at_ms` as exposure start. The exact
`EntryFilled` event is already loaded by Lifecycle but its timestamp is not used
for holding-bar identity.

The venue adapter also fetches only:

```text
max(atr_period + 2, structure_window_bars + 1)
```

candles. That is sufficient for the current rolling runner, but it cannot prove
a 96-closed-bar absolute cap.

### 3.5 Current runner semantic mismatch

The current names `confirmed_higher_low` and `confirmed_lower_high` actually
compute the minimum low or maximum high over a rolling window plus/minus an ATR
buffer. No confirmed swing pivot exists.

## 4. Goals

1. make PRE_TP1 and ABSOLUTE time stops generic Exit Engine behavior;
2. create immutable, strategy-neutral ExitProfile identities;
3. create exactly one current versioned EventExitBinding authority per active,
   entry-eligible EventSpec and zero for retired EventSpecs;
4. freeze Binding and Profile in CapacityClaim and Ticket without TOCTOU;
5. support Profile retirement without breaking issued Tickets;
6. enforce exact two-leg materialization at CapacityClaim time;
7. install the Owner-frozen V1 parameter catalog;
8. preserve one TP1 + one Runner reducer semantics;
9. keep runtime network calls bounded and outside PostgreSQL transactions;
10. deploy only through a stopped, exact-flat, forward-only R4 cutover.

## 5. Non-Goals

- parameter optimization, Replay, Shadow or Forward test;
- automatic Profile selection by market state;
- YAML, JSON, Markdown or cache-file configuration;
- multiple TP targets or tranche accounting;
- adding to a position;
- rank-loss, momentum-loss or detector-driven exits;
- Profile edits in place;
- active-position Schema handover;
- dual reads from EventSpec and Binding authority;
- runtime fallback to historical Event-bound Policy;
- new Owner risk, leverage, concurrency or instrument scope.

## 6. Authority Model

### 6.1 Single decision owner

The active Profile for a new Claim is owned only by PostgreSQL
`EventExitBindingCurrent`:

```text
event_spec_id
→ exit_binding_id
→ exit_profile_id + exit_profile_semantic_hash
```

`brc_event_specs.exit_policy_id` becomes legacy, non-authoritative data. After
cutover no runtime query may use it to resolve a Profile.

### 6.2 Typed Python Registry

Repository code owns immutable install semantics through frozen Pydantic
catalogs:

```python
registered_exit_profiles() -> tuple[ExitProfile, ...]
registered_event_exit_bindings() -> tuple[EventExitBinding, ...]
```

There is no YAML loader, environment-driven parameter override or per-host
configuration file.

### 6.3 PostgreSQL authority

PostgreSQL owns:

- immutable Profile rows;
- immutable Binding rows;
- current Event-to-Binding pointers;
- append-only Binding activation/retirement events;
- Claim/Ticket frozen Binding and Profile lineage.

### 6.4 Runtime separation

| Runtime boundary | Responsibility |
| --- | --- |
| Entry | Resolve current Binding/Profile, size exact exit legs, freeze Claim/Ticket lineage |
| Lifecycle | Exact-load Ticket Profile, evaluate PRE_TP1/Runner exits, create normal durable Commands |
| Reconciliation | Continue resolving Command/position/order truth without current Binding lookup |
| Observation | No ExitProfile authority or new work |

No new systemd service or logical lease is added.

## 7. Domain Contracts

### 7.1 Runner rule identity

```python
class RunnerRuleKind(StrEnum):
    ROLLING_EXTREME_ATR = "rolling_extreme_atr"
```

The V1 rule freezes:

```text
timeframe
lookback_bars
atr_period
atr_buffer_multiple
minimum_improvement_ticks
```

Direction comes from the Profile's exact `position_side`:

```text
long  -> min(last N lows) - ATR buffer
short -> max(last N highs) + ATR buffer
```

Future confirmed swing logic must use a different rule identity such as
`confirmed_swing_atr`; it cannot reuse this semantic hash.

### 7.2 TimeStopMode

```python
class TimeStopMode(StrEnum):
    PRE_TP1 = "pre_tp1"
    ABSOLUTE = "absolute"
```

```python
class TimeStopRule(BaseModel):
    max_holding_bars: int
    mode: TimeStopMode
```

`PRE_TP1` applies only while TP1 completed fill quantity is zero. Once TP1 is
fully filled, it is permanently inactive for that Ticket.

`ABSOLUTE` applies both before TP1 and during Runner management.

### 7.3 PreTp1GuardKind

```python
class PreTp1GuardKind(StrEnum):
    RECLAIM_REFERENCE = "reclaim_reference"
    SESSION_EXPIRY = "session_expiry"
```

Strategy/Event semantics may provide lifecycle reference values, but the
ExitProfile decides whether those values have exit behavior. A Ticket field is
not an implicit instruction to exit.

### 7.4 ExitProfile

```python
class ExitProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_profile_id: str
    exit_profile_version: int
    profile_schema_version: Literal["exit_profile_v1"]
    position_side: Literal["long", "short"]
    tp1: TakeProfitRule
    break_even_floor: BreakEvenFloorRule
    runner: RollingExtremeAtrRunnerRule
    time_stop: TimeStopRule | None
    pre_tp1_guards: tuple[PreTp1GuardKind, ...]
```

The semantic hash includes every field. A Profile ID/version/hash tuple is
permanently immutable. Parameter change always creates a new Profile ID or
version; `UPDATE policy JSON` is forbidden.

### 7.5 EventExitBinding

```python
class EventExitBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_binding_id: str
    binding_version: int
    event_spec_id: str
    exit_profile_id: str
    exit_profile_semantic_hash: str
    binding_semantic_hash: str
    activation_reason: str
    created_at_ms: int
```

Binding semantic hash covers:

```text
binding_version
event_spec_id
exit_profile_id
exit_profile_semantic_hash
activation_reason
```

The current pointer is not part of the immutable Binding hash.

### 7.6 CapacityClaim lineage

CapacityClaim adds:

```text
exit_binding_id
exit_binding_semantic_hash
exit_binding_authority_version
```

The existing `exit_policy_id` and `exit_policy_semantic_hash` physical fields
remain data-compatible and are interpreted as frozen Profile identity in V1.
No duplicate Profile columns are added merely to rename the concept.

### 7.7 Ticket lineage

TradeTicket adds the same exact Binding fields and copies the complete frozen
Binding authority and Profile lineage from CapacityClaim:

```text
Claim.exit_binding_id == Ticket.exit_binding_id
Claim.exit_binding_semantic_hash == Ticket.exit_binding_semantic_hash
Claim.exit_binding_authority_version == Ticket.exit_binding_authority_version
Claim.exit_policy_id == Ticket.exit_policy_id
Claim.exit_policy_semantic_hash == Ticket.exit_policy_semantic_hash
```

Ticket issuance must not resolve a different current Binding or Profile.

## 8. Binding Resolution And TOCTOU

### 8.1 Claim build

`build_capacity_claim()` performs one short PostgreSQL read transaction:

1. lock/read exact current Binding pointer for `event_spec_id`;
2. exact-load immutable Binding;
3. exact-load immutable Profile by ID/hash;
4. require Binding and Profile active for new Claim authority;
5. require Profile side equals Signal/Ticket Netting Domain side;
6. calculate TP1/Runner materialization;
7. freeze Binding/Profile identity and current pointer `projection_version`
   into CapacityClaim;
8. commit the Claim with its existing admission snapshot lineage.

There is no network I/O in this transaction.

### 8.2 Ticket issuance

Ticket issuance does not re-resolve a replacement Profile. It locks the current
Binding pointer and requires:

```text
current_binding_id == claim.exit_binding_id
current_binding_hash == claim.exit_binding_semantic_hash
current_projection_version == claim.exit_binding_authority_version
```

If the Binding changed after sizing, Admission is terminally rejected with:

```text
exit_binding_changed
```

The version check closes `A -> B -> A` ABA. The Kernel must not silently
rebuild the Claim or substitute the new Profile.

If the Binding remains exact, Ticket copies Claim lineage atomically with the
Reservation, Netting Domain hold, Aggregate and durable ENTRY Command.

### 8.3 Lifecycle

Lifecycle loads only:

```text
ticket.exit_profile_id/physical exit_policy_id
ticket.exit_profile_semantic_hash/physical exit_policy_semantic_hash
```

It does not read current Binding or current Profile status. A Profile retired
after Ticket issuance remains valid for that Ticket's complete protected
lifecycle.

Binding identity remains on Ticket for causality and Review but is not a
mutable lifecycle gate.

## 9. Profile And Binding Lifecycle

### 9.1 Profile lifecycle

Profile status has only this meaning:

| Status | New Binding | Issued Ticket exact-load |
| --- | ---: | ---: |
| `active` | allowed | allowed |
| `retired` | forbidden | allowed |

Profile retirement changes status only. Semantic fields, JSON payload and hash
remain immutable. Retirement fails if an active current Binding still points
to the Profile.

### 9.2 Binding facts and current projection

Use three ownership surfaces:

```text
brc_event_exit_profile_bindings          immutable facts
brc_event_exit_profile_binding_current   one pointer per active EventSpec
brc_event_exit_profile_binding_events    append-only transitions
```

Binding rows are never updated. Switching Profile is one PostgreSQL transaction:

1. exact-load the durable OwnerAuthorization;
2. require TOTP step-up, purpose `exit_profile_bind`, expected current pointer
   version and canonical idempotency key;
3. lock current pointer;
4. validate expected current Binding/version;
5. validate new immutable Binding/Profile and active Profile status;
6. append `BINDING_RETIRED` event for previous identity;
7. append `BINDING_ACTIVATED` event for new identity;
8. CAS current pointer to the new Binding;
9. commit.

Initial migration bindings use a typed `system_migration` authorization source.
Every later production switch uses the Owner control boundary; direct SQL and
repository-only pointer mutation are forbidden.

One immutable Binding may be activated at most once and retired at most once.
A retired Binding can never become current again; any future return to the same
Profile requires a new Binding identity and higher binding version. This rule,
together with Claim-frozen pointer projection version, eliminates ABA.

The current table has exactly one row per currently active/entry-eligible
EventSpec. Retired EventSpecs have zero current rows. PostgreSQL
unique/FK/check constraints prevent two current bindings or mismatched Profile
hashes.

### 9.3 Strategy retirement

Retiring a StrategyVersion:

```text
retire StrategyVersion
retire its EventSpecs
remove/retire their current Binding pointers through the Binding application boundary
do not retire ExitProfiles
```

Shared Profiles continue serving other Bindings and issued Tickets.

### 9.4 Control-plane write serialization

ExitProfile Authority mutations are rare Owner control-plane actions. All of
the following acquire one shared PostgreSQL transaction-scoped advisory lock
before reading or changing authority facts:

```text
Binding activation
Binding retirement
Binding switch
Profile retirement
```

The lock identity is one tracked Python constant, not configuration:

```text
EXIT_PROFILE_AUTHORITY_WRITE_LOCK
```

The PostgreSQL adapter acquires it with the equivalent of:

```sql
SELECT pg_advisory_xact_lock(:canonical_lock_key)
```

The transaction then performs normal row validation, current-pointer locking
and CAS. Transaction completion automatically releases the advisory lock.

This coarse serialization is intentionally absent from:

```text
Claim Binding/Profile reads
Ticket issuance
Lifecycle
Reconciliation
Observation
```

Trading-path concurrency remains governed by current-pointer row locking,
Claim-frozen `exit_binding_authority_version` and Ticket issuance CAS. The
advisory lock adds no trading hot-path latency, lease, Worker, distributed lock
or retry framework.

## 10. Generic Exit Evaluation

### 10.1 PRE_TP1 stage definition

PRE_TP1 means:

```text
aggregate.status == position_protected
AND tp1_filled_quantity == 0
```

It does not mean that market price has not touched the TP1 level. Only exact
venue fill truth changes the stage.

Partial TP1 fill remains outside current supported semantics and follows the
existing fail-closed Incident/reconciliation behavior.

### 10.2 Deterministic precedence

For one final closed candle before TP1:

```text
1. SESSION_EXPIRY
2. RECLAIM_FAILURE
3. ABSOLUTE_TIME_STOP
4. PRE_TP1_TIME_STOP
5. NO_CHANGE
```

Session deadline has precedence over price-thesis attribution when multiple
conditions become true on the same candle.

`SESSION_EXPIRY` is evaluated only when the Profile contains
`PreTp1GuardKind.SESSION_EXPIRY`; `RECLAIM_FAILURE` is evaluated only when the
Profile contains `PreTp1GuardKind.RECLAIM_REFERENCE`. Claim construction
requires the corresponding Strategy lifecycle reference when a guard is
enabled. Missing required reference fails closed rather than silently disabling
the guard.

Profiles with `pre_tp1_guards=()` do not consume Strategy-provided reclaim or
session references.

### 10.3 Runner stage precedence

For `runner_protected`:

```text
1. closed-candle/watermark validation
2. ABSOLUTE_TIME_STOP
3. rolling_extreme_atr candidate
4. break-even floor
5. minimum-improvement check
6. MOVE_STOP or NO_CHANGE
```

`PRE_TP1_TIME_STOP` has no effect after TP1 complete fill.

### 10.4 Reason codes

Canonical exit reasons are:

```text
session_expired
failed_breakout_reclaimed
failed_breakdown_reclaimed
absolute_time_stop_hit
pre_tp1_time_stop_hit
```

Existing SOR reason meanings are preserved; only the generic TimeStop reasons
become explicit.

## 11. Holding-Bar Identity

### 11.1 Exposure start

The only start identity is:

```text
EntryFilled.occurred_at_ms
```

Lifecycle already loads the exact `EntryFilled` event. It must pass that time to
`LifecycleFactsRequest.exposure_started_at_ms`; `Ticket.created_at_ms` is no
longer a valid holding-period basis.

### 11.2 Closed-bar count

For a fill at 10:23 on a 1h Profile:

```text
11:00 close -> bar 1
12:00 close -> bar 2
...
22:00 close -> bar 12
```

A holding bar is one final venue candle whose close timestamp is **strictly
later** than `EntryFilled.occurred_at_ms`. The candle is not required to have
opened after EntryFilled. Therefore the partially exposed 10:00–11:00 candle
in the example counts when its 11:00 close becomes final.

Signal, Claim, Ticket creation and Command dispatch timestamps never count.

### 11.3 Bounded market window

`LifecycleFactsRequest` adds the applicable time-stop bar requirement. The
venue candle limit is:

```text
max(
  atr_period + 2,
  structure_window_bars + 1,
  max_holding_bars + 1 when a TimeStop is applicable
)
```

For the frozen V1 catalog the maximum is **97 rows**. The extra row permits the
latest still-open candle to be excluded while retaining 96 final closed bars.

The count uses actual returned final venue candles, so unavailable TradFi
session intervals are not fabricated as bars.

No full-history scan, file cache or report artifact is allowed.

### 11.4 Market-fact requirement

Lifecycle requests market facts when any of these is true:

```text
Runner stage
OR reclaim/session evaluation requires a closed candle
OR applicable PRE_TP1/ABSOLUTE TimeStop exists
```

TimeStop cannot be silently skipped because a Strategy lacks reclaim fields.

## 12. Exit-Leg Materialization

### 12.1 Exact split

Capacity sizing computes:

```text
tp1_qty = floor_to_step(total_qty * profile.tp1.quantity_fraction)
runner_qty = total_qty - tp1_qty
```

No fallback fraction, nearest ratio, 50/50 substitution or hidden quantity
repair is permitted.

### 12.2 Required checks

Both legs require:

```text
quantity > 0
quantity % step_size == 0
quantity >= min_quantity
leg_notional >= min_notional
```

The conservative notional bases are frozen as:

| Leg | Notional price basis |
| --- | --- |
| TP1 | frozen TP1 limit price |
| Runner protection | frozen Initial Stop price |

Using the lower planned executable notional basis prevents a leg from being
accepted only because entry price was higher.

Failure produces terminal Admission blocker:

```text
exit_leg_materialization_unmet
```

and creates no Ticket, Reservation or Exchange Command.

### 12.3 Profile semantic integrity

MPG `Decimal("0.33")` means exactly 33%, not one third. Floor-to-step residue
belongs to Runner. The exact fraction remains part of the Profile semantic
hash.

## 13. Owner-Frozen V1 Catalog

Six semantic families require eight side-bound immutable Profile records.

Every V1 Profile freezes these shared hashed fields explicitly:

| Field | Frozen value |
| --- | --- |
| `profile_schema_version` | `exit_profile_v1` |
| `tp1.reward_multiple` | `Decimal("1")` |
| `tp1.execution_style` | `limit_gtc` |
| `tp1.market_fallback_allowed` | `false` |
| `break_even_floor.exit_fee_basis` | `conservative_taker` |
| `break_even_floor.slippage_buffer_ticks` | `2` |
| `break_even_floor.minimum_improvement_ticks` | `2` |
| `runner.kind` | `rolling_extreme_atr` |
| `runner.atr_period` | `14` |
| `runner.minimum_improvement_ticks` | `2` |

Profile-specific hashed fields are:

| Profile record | Side | TP1 fraction | Runner timeframe | Lookback | ATR buffer | TimeStop | Pre-TP1 guards |
| --- | --- | ---: | --- | ---: | ---: | --- | --- |
| `exit-profile:trend-continuation:1h:long:v1` | long | `0.50` | `1h` | 4 | `0.50` | none | `()` |
| `exit-profile:momentum-tail:1h:long:v1` | long | `0.33` | `1h` | 5 | `0.75` | none | `()` |
| `exit-profile:impulse-decay:1h:long:v1` | long | `0.50` | `1h` | 4 | `0.50` | `PRE_TP1 / 12` | `()` |
| `exit-profile:failure-reversal:1h:short:v1` | short | `0.50` | `1h` | 4 | `0.50` | `PRE_TP1 / 12` | `()` |
| `exit-profile:orb-crypto:15m:long:v1` | long | `0.50` | `15m` | 4 | `0.50` | `ABSOLUTE / 96` | `(RECLAIM_REFERENCE, SESSION_EXPIRY)` |
| `exit-profile:orb-crypto:15m:short:v1` | short | `0.50` | `15m` | 4 | `0.50` | `ABSOLUTE / 96` | `(RECLAIM_REFERENCE, SESSION_EXPIRY)` |
| `exit-profile:orb-us:15m:long:v1` | long | `0.50` | `15m` | 4 | `0.50` | `ABSOLUTE / 8` | `(RECLAIM_REFERENCE, SESSION_EXPIRY)` |
| `exit-profile:orb-us:15m:short:v1` | short | `0.50` | `15m` | 4 | `0.50` | `ABSOLUTE / 8` | `(RECLAIM_REFERENCE, SESSION_EXPIRY)` |

No constructor default is allowed to supply a hashed Profile field. Catalog
tests compare the complete canonical payload and semantic hash.

Current Event bindings are:

| Strategy/Event | Profile |
| --- | --- |
| CPM LONG | trend-continuation long |
| MPG LONG | momentum-tail long |
| MI LONG | impulse-decay long |
| BRF2 SHORT | failure-reversal short |
| Crypto SOR LONG/SHORT | matching orb-crypto side |
| SOR-US LONG/SHORT | matching orb-us side |

The parameter economics are Owner authority. Engineering certification proves
identity, materialization and runtime correctness only.

## 14. PostgreSQL Design

### 14.1 Existing physical Profile table

The physical table `brc_exit_policies` is retained to preserve terminal
lineage and minimize migration risk. It becomes the physical ExitProfile store.

Migration changes:

1. drop `UNIQUE(event_spec_id)`;
2. make legacy `event_spec_id` nullable;
3. add `profile_schema_version`;
4. preserve all historical rows byte-for-byte except additive nullable/default
   metadata required by the target Schema;
5. insert V1 ExitProfile rows with `event_spec_id=NULL`;
6. install immutability triggers over Profile identity, version, side, payload
   and semantic hash;
7. add `UNIQUE(exit_policy_id, semantic_hash)` for exact composite references;
8. permit only `active -> retired` status transition.

Historical event-bound rows remain provenance only. Current Lifecycle does not
fallback to their payload type after cutover.

### 14.2 Binding facts

`brc_event_exit_profile_bindings`:

```text
exit_binding_id PK
binding_version
event_spec_id FK
exit_profile_id FK
exit_profile_semantic_hash
binding_semantic_hash
activation_reason
created_at_ms
```

Constraints:

- unique `(event_spec_id, binding_version)`;
- unique `(exit_binding_id, binding_semantic_hash)`;
- canonical SHA-256 hashes;
- composite FK `(exit_profile_id, exit_profile_semantic_hash)` to
  `brc_exit_policies(exit_policy_id, semantic_hash)`;
- immutable row trigger.

### 14.3 Current pointer

`brc_event_exit_profile_binding_current`:

```text
event_spec_id PK
exit_binding_id UNIQUE FK
binding_semantic_hash
projection_version
activated_at_ms
```

The pointer uses composite FK `(exit_binding_id, binding_semantic_hash)` to the
immutable Binding fact. The pointer row is the sole new-Claim authority.

### 14.4 Binding events

`brc_event_exit_profile_binding_events` is append-only:

```text
binding_event_id PK
event_spec_id
exit_binding_id
binding_version
operation = ACTIVATED | RETIRED
authorization_source
owner_authorization_id nullable FK
reason
created_at_ms
```

Constraints include:

```text
UNIQUE(exit_binding_id, operation)
```

so one Binding has at most one `ACTIVATED` and one `RETIRED` event and cannot be
reactivated.

### 14.5 Claim and Ticket columns

Add nullable historical-safe columns to:

```text
brc_capacity_claims.exit_binding_id
brc_capacity_claims.exit_binding_semantic_hash
brc_capacity_claims.exit_binding_authority_version
brc_trade_tickets.exit_binding_id
brc_trade_tickets.exit_binding_semantic_hash
brc_trade_tickets.exit_binding_authority_version
```

Target runtime requires them for every newly issued Claim/Ticket. Existing
terminal rows remain nullable. New Claim/Ticket rows use composite Binding and
Profile FKs where the preserved source data permits exact constraints.
AdmissionDecision retains its exact Claim/Ticket
and digest lineage rather than duplicating all Profile fields.

### 14.6 Legacy EventSpec column

`brc_event_specs.exit_policy_id` remains present for one migration generation
as `LEGACY_NON_AUTHORITATIVE` data. Production code has zero reads from it after
cutover. Architecture tests enforce that rule. A later reviewed migration may
drop it; this design does not rely on that later cleanup.

## 15. Migration And Cutover

### 15.1 Revision identity

Design-time identity:

```text
NEXT_AFTER_0006_exit_profile_authority_v1
```

The final Alembic number is assigned only when the branch is integrated and the
forward head is known.

### 15.2 Source gate

The migration is R4 and requires:

```text
source schema = exact 0006 head
zero nonterminal Ticket
zero non-flat PostgreSQL Position
zero Binance position
zero open order/protection residue
zero active Reservation/Netting Domain
zero unresolved Command
zero open Incident
all exposure-bearing terminal Tickets reviewed
Entry fenced and all writers stopped
```

There is no active-position handover. Existing protected Tickets must finish on
their original release before migration.

### 15.3 Preservation

The preservation manifest covers all source tables/columns and terminal
lineage. Historical Event-bound Policy rows and Ticket policy IDs/hashes remain
unchanged. New target rows are excluded from source digest comparison by exact
revision ownership.

### 15.4 Seed and activation

Migration/target identity installation:

1. create/alter Profile and Binding Schema;
2. preserve historical rows;
3. insert eight immutable V1 Profiles;
4. insert eight initial Bindings for the eight active EventSpecs;
5. create exactly eight current pointers and zero for retired EventSpecs;
6. add Claim/Ticket lineage columns;
7. rotate Registry/Schema/Seed identity with global new ENTRY paused;
8. start safety workers;
9. certify exact Profile/Binding manifest and zero runtime activity;
10. restore Entry/Strategy controls only through existing postflight gates.

The first resumed new Ticket uses the Owner-frozen V1 Profiles. No Replay or
Shadow gate exists.

### 15.5 Failure recovery

Any failure after target Schema commit remains fenced and fix-forwards on the
target Schema. No downgrade, old runtime restart, dual read, dual write or
manual Binding DML is permitted.

## 16. Transaction Ownership

| Transaction | Atomic facts |
| --- | --- |
| Registry seed | Profile rows, Binding facts, current pointers, semantic identity |
| Binding switch/Profile retirement | shared authority advisory lock, OwnerAuthorization when applicable, events/status, current pointer CAS |
| Claim build | exact Binding/Profile identity, pointer authority version and sized exit legs |
| Ticket issuance | Claim lineage, Ticket, Reservation, Domain hold, Aggregate, ENTRY Command |
| Lifecycle mutation | existing Trade Event/Aggregate/Command effects only |

Venue/candle/position/order I/O remains outside PostgreSQL transactions.

## 17. Failure Semantics

| Failure | Result |
| --- | --- |
| Current Binding missing | terminal Admission rejection; no Claim/Ticket |
| Binding/Profile hash mismatch | fail closed; Registry/Authority incident |
| Profile retired before Claim | no new Claim |
| Binding changed after Claim | `exit_binding_changed`; no Ticket |
| Binding switch lacks exact Owner authorization | no pointer mutation |
| Profile retire races Binding activation | authority write lock serializes; one operation revalidates and rejects |
| Two Binding switches race | authority write lock serializes; exactly one expected-version sequence commits |
| Profile retired after Ticket | lifecycle continues exact Profile |
| Profile side differs | hard rejection |
| TP1/Runner quantity or notional invalid | `exit_leg_materialization_unmet` |
| Lifecycle exact Profile missing | no exchange mutation; runtime Incident/fenced Ticket lifecycle diagnosis |
| Market candle unavailable | retain protection; retry next bounded cadence |
| Unknown EXIT/Stop outcome | existing durable Command reconciliation; no resend |

## 18. Runtime And Performance

1. no new persistent Worker or timer;
2. maximum active Tickets remains Policy-owned;
3. Profile/Binding reads use exact IDs or one EventSpec current pointer;
4. lifecycle candle request remains one bounded API call, maximum 97 rows for
   the frozen catalog;
5. no full-history query or file cache;
6. no periodic JSON/Markdown/YAML output;
7. no YAML parser or hot reload;
8. existing network timeouts and Worker resource slice remain authoritative.

## 19. No-YAML Architecture Rule

The implementation must add architecture coverage proving:

```text
src/trading_kernel/** imports no YAML loader
production scripts do not read *.yaml or *.yml
ExitProfile/Binding runtime does not read repository files
no generated YAML/JSON/Markdown becomes authority
```

Documentation may use tables or pseudocode, but no YAML example is treated as
an implementation contract.

## 20. Test Contract

### 20.1 Pure domain

- TimeStopMode validation;
- PRE_TP1 at 11/12 closed bars;
- ABSOLUTE before and after TP1;
- deterministic session/reclaim/time-stop precedence;
- reclaim/session guards included in Profile hash and selectively consumed;
- rolling-extreme long/short calculations;
- Profile and Binding deterministic semantic hashes;
- complete V1 Catalog payload/hash parity with zero constructor defaults;
- Profile mutation rejected.

### 20.2 Capacity and lineage

- Claim freezes exact Binding/Profile IDs, hashes and pointer authority version;
- Ticket copies Claim identities byte-for-byte;
- Binding switch between Claim/Ticket rejects without re-sizing;
- `A/v10 -> B/v11 -> A-new/v12` ABA rejects the v10 Claim;
- Profile side mismatch rejects;
- 33/67 normal split;
- TP1 below minQty/minNotional;
- Runner below minQty/minNotional;
- step floor residue belongs to Runner;
- no fallback to 50/50.

### 20.3 Lifecycle

- EntryFilled timestamp, not Ticket creation, owns exposure start;
- a final close strictly later than EntryFilled counts even when its candle
  opened before the fill;
- fill 10:23 produces 11:00 as holding boundary 1;
- MI/BRF2 12 PRE_TP1 bars request EXIT;
- MI/BRF2 after TP1 ignore PRE_TP1 time stop;
- Crypto SOR ABSOLUTE 96 applies before and after TP1;
- SOR-US ABSOLUTE 8 applies before and after TP1;
- reclaim/session semantics remain exact;
- retired Profile continues an issued Ticket;
- current Binding is never read by Lifecycle.

### 20.4 PostgreSQL and Migration

- empty and production-shaped `0006 -> NEXT`;
- source non-flat rejection;
- historical Policy/Ticket preservation;
- eight immutable Profile rows and eight Binding pointers;
- exactly one current Binding per active EventSpec and zero per retired EventSpec;
- Profile and Binding current composite FKs reject hash drift;
- one ACTIVATED and one RETIRED event maximum per Binding;
- retired Binding reactivation rejected;
- Profile content immutability;
- active Binding blocks Profile retirement;
- Binding switch atomicity and crash rollback;
- concurrent Profile retire/Binding activate cannot commit a retired-current pair;
- concurrent Binding switches produce exactly one valid authority sequence;
- Claim/Ticket paths do not acquire the Authority advisory lock;
- Strategy retirement does not retire shared Profile;
- EventSpec legacy column has zero runtime read path;
- downgrade rejected.

### 20.5 Full chain

```text
Signal
→ current Binding/Profile
→ CapacityClaim sized legs
→ Ticket frozen lineage
→ ENTRY/protection
→ PRE_TP1 or Runner exit
→ durable EXIT Command
→ reconciliation
→ settlement
→ review
```

### 20.6 Architecture/static

- no second lifecycle or strategy-specific exit branch;
- no YAML/YML runtime source;
- no EventSpec exit-policy runtime resolution;
- no Profile fallback parser;
- no file authority;
- Ruff, repository Mypy and `git diff --check`.

## 21. Release Certification

The exact candidate is R4. Certification includes:

1. full Unit/Architecture;
2. full PostgreSQL Integration;
3. full-chain;
4. empty and production-shaped Migration/preservation;
5. Profile/Binding manifest parity;
6. no-YAML and no-legacy-read architecture gates;
7. Ruff/Mypy/diff.

Any change after certification invalidates the manifest.

## 22. Deleted Or Replaced Concepts

The target implementation removes or stops using:

- `_policy_for_contract()` runtime/catalog generation;
- EventSpec `exit_policy_id` as current authority;
- StrategyVersion-driven Profile retirement;
- `confirmed_higher_low/lower_high` as names for rolling extremes;
- `Ticket.created_at_ms` as holding-period start;
- pre-TP1 reclaim/session short-circuit that skips TimeStop;
- implicit full-position minNotional as proof that both exit legs are valid;
- YAML/YML configuration examples as implementation artifacts.

## 23. Hard Stops

Stop implementation review if any solution requires:

1. modifying PR #4 or its certified candidate;
2. runtime YAML/JSON/Markdown authority;
3. direct SQL Profile/Binding switch;
4. active-position handover;
5. compatibility fallback to EventSpec Policy;
6. Profile mutation in place;
7. hidden fraction adjustment;
8. Lifecycle reading current Binding;
9. detector/rank facts below StrategySignal;
10. new exchange mutation outside durable Commands;
11. Multi-TP, adding or position merge;
12. risk, leverage, capacity or instrument expansion.

## 24. Done Contract

Design implementation is complete only when:

```text
exactly one current EventExitBinding per active/entry-eligible EventSpec
AND zero current EventExitBinding per retired EventSpec
AND immutable ExitProfile content
AND Binding/Profile identity and pointer authority version frozen in CapacityClaim and Ticket
AND Ticket issuance never substitutes current Binding
AND retired Binding can never be activated again
AND retired Profile serves issued Ticket
AND exact two-leg materialization passes
AND holding boundaries are final venue closes strictly after EntryFilled
AND Profile hash covers reclaim/session guard behavior and every Catalog field
AND PRE_TP1/ABSOLUTE semantics and precedence are deterministic
AND Lifecycle keeps one TP1 + Runner reducer
AND EventSpec exit_policy_id has zero runtime authority
AND no YAML/YML runtime source exists
AND stopped-flat R4 certification passes
```

Even after all implementation gates pass, production deployment remains a
separate Owner authorization and requires fresh exact-flat PostgreSQL, systemd
and exchange facts.
