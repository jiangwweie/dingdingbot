---
title: Multi-Position Dynamic Budget And Leverage Design
status: OWNER_REVIEW_REQUIRED
date: 2026-07-23
revision: 2
---

# Multi-Position Dynamic Budget And Leverage Design

## Objective

Replace the current fixed-USDT capacity envelope with one versioned,
balance-relative budget model that supports up to three concurrent
capital-owning Tickets while older flat Tickets may finish Settlement/Review,
without creating a second execution chain.

The design must:

- size each new Ticket from fresh account balance and its Initial Stop;
- preserve margin capacity for the remaining Ticket slots;
- select a bounded leverage that is sufficient for the allocated slot rather
  than blindly using either the smallest account-wide leverage or a fixed 10x;
- keep one globally serialized new-ENTRY lane while existing protected Tickets
  progress concurrently;
- remove retired fixed gross-notional and fixed-USDT stop-risk policy semantics;
- keep all runtime authority in PostgreSQL and all production execution under
  `src/trading_kernel`;
- remain readable, typed, auditable, and fail-closed.

This program changes capacity, sizing, leverage application, persistence, and
certification. It adds one bounded post-fill risk disposition before normal
protected lifecycle. It does not change strategy definitions, signal detectors,
registered exit policies, settlement formulas, or normal TP1/runner semantics.

## Owner Decisions

The following decisions are final for this design:

| Decision | Final value |
| --- | --- |
| Planned Stop Risk per Ticket | `totalWalletBalance * 0.03` |
| Maximum concurrent capital-owning Tickets | `3` |
| Account-wide gross stop-risk cap | None |
| Account-wide gross notional cap | None |
| Strategy-cluster risk cap | None |
| Maximum configured leverage | `10x` |
| Maximum account initial-margin utilization | `0.90` |
| Margin allocation | Slot-aware across remaining Ticket capacity |
| Quantity when full risk cannot fit | Shrink to the executable capacity |
| Minimum economic utilization threshold | None beyond venue minimums and an executable frozen protection/exit plan |
| Adding to an existing position | Forbidden |
| New ENTRY scheduling | Globally serialized |
| Existing Ticket lifecycle | Concurrent across independent Netting Domains |
| Production writes during implementation | Disabled until certification and controlled re-enable |

Fees, funding, and realized slippage remain separate economics. The 3% value
is the planned price loss from entry reference to Initial Stop, not a guarantee
that realized loss cannot exceed 3% in a gap, rejection, or venue-failure case.

## Owner Decisions Still Required

The conflict, capacity, and leverage ownership semantics are now complete.
Three real-funds decisions remain intentionally unresolved and must not be
guessed during implementation:

| Decision | Options | Recommendation |
| --- | --- | --- |
| Supported margin mode | Cross only; or Cross plus Isolated | **Cross only** for this account-wide shared budget model |
| Pre-entry liquidation safety | No explicit proof; fixed distance rule; or venue-bracket-derived proof | **Venue-bracket-derived proof** with a configurable stop-to-liquidation safety ratio |
| Post-fill stop-risk overrun | Continue and report; immediately flatten; or protect then conditionally flatten | **Install protection first, then controlled-flatten when typed tolerance is exceeded** |

The concrete recommended values are:

```text
supported_margin_mode = cross
min_liquidation_distance_to_stop_distance_ratio = 2.0
max_post_fill_stop_risk_overrun_fraction = 0.10
```

`2.0` means the conservative projected liquidation distance must be at least
twice the Initial Stop distance. `0.10` is a relative tolerance on the frozen
3% budget, so the hard post-fill ceiling would be 3.3% of
`total_wallet_balance_at_claim`; it does not mean ten percentage points of the
account. These values need explicit Owner approval before the implementation
plan is final. They belong in versioned Owner Policy, not in code constants or
environment variables.

Position mode and margin mode are separate facts:

| Fact | Required value | Meaning |
| --- | --- | --- |
| Position mode | `independent_sides` | Venue Hedge Mode; long and short position rows can coexist |
| Margin mode | Proposed `cross` | All supported Tickets consume one account-wide shared margin pool |

Independent long/short support does not prove Cross margin. Both facts must be
read and verified independently.

## Known Current State

Current tracked code has the correct multi-position execution architecture but
the wrong capacity policy for this target:

- `CapacityPolicy` uses fixed `max_gross_notional`,
  `max_gross_risk_at_stop`, and `max_ticket_risk_at_stop` values;
- `target_leverage` is one fixed value, currently seeded as 2x;
- capacity uses all fresh available margin multiplied by that fixed leverage;
- the Ticket and CapacityClaim already freeze notional, leverage, and stop risk;
- the global ENTRY lane is released only after Initial Stop confirmation, so a
  second Ticket cannot allocate margin while the first ENTRY outcome or
  protection installation is unresolved;
- the current venue adapter creates orders but does not set and verify the
  Ticket leverage before ENTRY.

Historical commits are provenance, not runtime authority:

| Commit | Reusable evidence | Treatment |
| --- | --- | --- |
| `2df39c1c` | Wallet-fraction stop sizing, quantity rounding, leverage ceiling, margin capacity | Re-express as pure Trading Kernel domain behavior |
| `7f4a5253` | `set_leverage`, signed read-back, mismatch refusal | Re-implement inside the current venue boundary |
| `e5a8ed72` / `b3aedb2c` / `a5d72996` | Versioned risk authority and atomic account capacity | Reuse invariants and tests only |

No retired module, table generation, migration chain, compatibility reader, or
alternate application service may be restored.

## Alternatives Considered

| Approach | Concurrency | Liquidation buffer | Simplicity | Decision |
| --- | --- | --- | --- | --- |
| Keep fixed-USDT Envelope and only raise limits | Weakly related to balance | Unchanged | Superficially simple, semantically wrong | Rejected |
| Always configure 10x | Maximizes margin efficiency | Smallest | Simple but unnecessarily aggressive | Rejected |
| Choose the minimum leverage against all available margin | First Ticket consumes the most margin | Largest | Reuses historical algorithm unchanged | Rejected |
| Allocate margin by remaining slots, evaluate every permitted leverage, then choose the lowest full-target or largest safe shrunk candidate | Preserves multi-Ticket capacity | Explicit venue-derived safety proof | Moderate, deterministic | Selected |

The selected approach changes the optimization target from “minimize the
leverage of the current Ticket” to “use the lowest leverage that fits the
current Ticket inside its fair share of remaining account margin.”

## Authoritative Chain

The existing chain remains the only production path:

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> fresh account and instrument facts
-> slot-aware CapacityClaim
-> immutable Ticket
-> durable ENTRY Exchange Command
-> leverage set/read-back when permitted
-> ENTRY order
-> exact fill and post-fill safety disposition
-> Initial Stop
-> concurrent protected lifecycle
-> reconciliation
-> settlement
-> review
```

Strategy code still ends at `StrategySignal`. It cannot provide quantity,
notional, leverage, account balance, margin allocation, or exchange commands.

## Conflict Domains And Direction Semantics

Multi-position does not mean that every Signal may create an independent
position. Admission is governed by four explicit scopes:

| Scope | Identity | Owns |
| --- | --- | --- |
| Global ENTRY Lane | One runtime-wide lane | Serializes all new ENTRY admission until the prior Ticket is protected or terminal |
| Account Capacity Domain | `venue + account` | Three-capital-owning-Ticket count and account-wide margin budget |
| Leverage Domain | `venue + account + instrument` | Leverage configuration and both-side instrument health |
| Netting Domain | `venue + account + instrument + position_side` | One active Ticket and one Exposure Episode for one direction |

`Leverage Domain` is a derived value identity, not a new persistence authority.
It is computed from existing canonical Ticket fields. The global lane already
serializes BRC leverage mutation; no second scheduler or lock service is added.

The three-capital-owning-Ticket limit and slot budget apply per exact Account
Capacity Domain, not per bare `account_id` string and not across unrelated
accounts. PostgreSQL keys and repository reads therefore use
`venue_id + account_id` together.

### Same Instrument And Same Direction

Only one active Ticket may exist in a Netting Domain. This rule is independent
of StrategyGroup identity:

```text
SOR / SOLUSDT / long
CPM / SOLUSDT / long
```

The first issued Ticket owns `binance-usdm + account + SOLUSDT + long`. Every
later same-direction Signal is refused while that Ticket owns the domain. It is
not merged, queued, retried, or treated as permission to add to the position.

After the prior Exposure Episode is exchange-flat, free of residual orders,
reconciliation-matched, and its budget/count/Netting Domain are atomically
released, a new market event may create a new Signal and a new Exposure Episode.
Settlement and Review for the old Ticket may finish afterward. The old blocked
Signal is never revived.

### Same Instrument And Opposite Directions

Long and short are independent Netting Domains and may coexist by default on a
supported independent-sides account:

```text
SOLUSDT long  -> Ticket A
SOLUSDT short -> Ticket B
```

They remain separate Tickets with separate Entry, Initial Stop, take-profit,
runner, exit, Settlement, and Review lineage. The system does not net, merge,
reverse, cancel, or compare the strategy strength of the two directions.

They share one Leverage Domain. Ticket B may enter only when Ticket A is
healthy, BRC-owned, protected, free of unknown outcomes, and the exact current
instrument leverage is valid for Ticket B. Ticket B adopts that leverage and
must not mutate it while either side is open.

### Conflict Matrix

| Existing exact-instrument state | New Signal | Admission result |
| --- | --- | --- |
| Active BRC Ticket in the same direction | Same direction, any StrategyGroup | Refuse: active Netting Domain |
| Healthy protected BRC Ticket in the opposite direction | Opposite direction | Allow after fresh capacity and leverage checks |
| Opposite BRC Ticket is entering or installing Initial Stop | Opposite direction | Global lane blocks until protected or terminal |
| Opposite BRC Ticket has an unknown mutation outcome | Either direction | Global new ENTRY block |
| Opposite BRC Ticket has protection shortfall or safety Incident | Either direction | Global new ENTRY block until protection or flatness is proven |
| BRC position is flat but owned protection/exit residue remains | Either direction | Instrument block until exact cleanup and reconciliation |
| Unowned/manual position exists on the account | Either direction | Account new-ENTRY block; BRC does not adopt external exposure |
| Unowned or unknown open order exists on the account | Either direction | Account new-ENTRY block and Incident |
| Existing leverage is missing or above Owner/venue maximum | Opposite direction | Instrument block |
| Existing leverage is valid but cannot carry the full target | Opposite direction | Shrink using existing leverage |
| Exact instrument is flat, order-free, Incident-free, and unowned exposure is absent | Either supported direction | Normal arbitration and capacity evaluation |
| Different instrument has a healthy Ticket | Any supported direction | No instrument conflict; account count and margin still apply |

### Instrument Ownership And Health

The Entry boundary must classify exact-instrument facts, not rely on raw order
counts. A typed `InstrumentEntryHealth` decision distinguishes:

```text
owned active Tickets and their sides
owned open positions and quantities
owned expected protection/exit orders
owned residual orders after flatness
unowned positions
unowned or unknown orders
open Incident kinds
unknown Exchange Command outcomes
configured leverage
observed_at_ms / valid_until_ms / digest
```

A separate typed `AccountEntryHealth` validates every currently open position
and order returned for the exact `venue + account` and matches BRC-owned rows to
current Ticket/command identities. It distinguishes owned healthy exposure,
owned recovery work, unowned exposure, unowned orders, and contradictory or
incomplete venue truth. This is a bounded current-state snapshot, not a history
scan and not a new persistence authority.

Expected protection orders belonging to a healthy opposite-side BRC Ticket do
not by themselves block coexistence. Because the proposed model is Cross margin,
an unowned position or order anywhere in the exact Account Capacity Domain
blocks all new ENTRY until external ownership is removed or explicitly brought
under a separate future contract. Owned residual orders after flatness or a
leverage contradiction block the exact Leverage Domain.

No BRC Ticket may adopt, resize, protect, cancel, or close an externally owned
manual position or order as part of normal admission.

### Entry Blocking Scope

An occupied domain is not automatically an Incident. The kernel distinguishes
normal admission conflicts from unresolved safety failures and gives every open
Incident an explicit new-ENTRY blocking scope:

| Condition | Block scope | New ENTRY effect | Existing Ticket effect |
| --- | --- | --- | --- |
| Active Ticket in the same Netting Domain | Exact Netting Domain; normal occupancy | Refuse that candidate | Existing Ticket continues normally |
| Healthy protected Ticket in another domain | None beyond count and margin | May admit after fresh checks | Lifecycle remains concurrent |
| Schema/commit mismatch or duplicate writer authority | Runtime | Block every new ENTRY | Existing exposure remains fail-closed under the current recovery contract |
| Unknown exchange mutation outcome on any active Ticket | Exact Account Capacity Domain | Block all new ENTRY for the account | Reconciliation resolves exact external truth |
| Partial fill, unprotected exposure, protection shortfall, controlled flatten, or any unowned account position/order | Exact Account Capacity Domain | Block all new ENTRY for the account | Lifecycle/recovery retains write authority only for BRC-owned exposure |
| Residual owned order after flatness or leverage contradiction | Exact Leverage Domain | Block both directions of that instrument | Other healthy instruments may continue |
| Flat Ticket with Settlement or Review unavailable | None | Does not block new ENTRY by itself | Audit completion remains required for that Ticket |

The existing `brc_runtime_incidents` table gains typed
`entry_block_scope` and `entry_block_key` fields. Allowed scopes are
`runtime`, `account_capacity`, `leverage_domain`, and `none`. The key is the
canonical identity for that scope. Blocking is derived from open typed Incident
rows; worker code may not infer safety scope from free-form text or JSON.

```text
runtime          -> global
account_capacity -> venue_id:account_id
leverage_domain  -> venue_id:account_id:exchange_instrument_id
none             -> null
```

Database constraints enforce those scope/key shapes.

Authoritative rejection, ordinary budget exhaustion, stale Signal, and active
Netting Domain occupancy are terminal admission outcomes but are not runtime
Incidents. Resolved Incidents cease blocking only after the same reconciliation
transaction records the external proof and resolution.

## Deterministic Signal Arbitration

When multiple fresh Signals are ready, the existing deterministic order remains
authoritative:

```text
owner_policy_priority
-> candidate_scope_priority
-> occurred_at_ms
-> observed_at_ms
-> signal_event_id
```

Only the first ranked candidate may attempt the current global ENTRY lane. A
candidate refused for stale facts, occupied Netting Domain, instrument-health
conflict, or exhausted capacity is marked blocked and is not automatically
retried. A later trade requires a new valid StrategySignal from a new market
event.

Simultaneous long and short Signals for one instrument are therefore processed
serially. The second direction is reevaluated from fresh balance, margin,
position, order, Incident, and leverage facts only after the first Ticket is
protected or terminal.

## Capacity Authorities

### Owner Policy

PostgreSQL `brc_owner_policy_current` is the only runtime authority for the
capital policy. Production code must not use environment variables, Markdown,
or hidden constants for these values.

One policy row is bound to an exact Account Capacity Domain through its scope.
The current system has one live account, but the model must not silently combine
two venues whose local account identifiers happen to be equal.

The policy model becomes:

```text
owner_policy_id
policy_version
enabled
real_submit_enabled
priority_rank
max_concurrent_tickets
planned_stop_risk_fraction
max_initial_margin_utilization
max_leverage
supported_margin_mode
min_liquidation_distance_to_stop_distance_ratio
max_post_fill_stop_risk_overrun_fraction
scope
updated_at_ms
```

The committed deterministic seed installs `3`, `0.03`, `0.90`, and `10`. The
supported margin mode and two remaining safety ratios are installed only after
explicit Owner approval. Policy literals may exist in the seed and its exact
tests, but not inside the domain calculation or worker orchestration.

### Fresh Exchange Facts

Action-time account facts must distinguish loss capacity from margin capacity:

| Fact | Meaning | Use |
| --- | --- | --- |
| `total_wallet_balance` | Wallet balance excluding temporary unrealized PnL | Planned Stop Risk budget |
| `total_margin_balance` | Current signed cross-margin balance | Account initial-margin ceiling |
| `total_initial_margin` | Margin already committed by current positions/orders | Remaining account margin capacity |
| `total_maintenance_margin` | Current signed maintenance requirement across account exposure | Liquidation proof and contradiction checks |
| `available_margin` | Venue-reported currently available margin | Final executable margin bound |
| `mark_price` | Current signed exact-instrument mark price | Venue-consistent maintenance and liquidation calculation |
| `margin_mode` | Exact Cross or Isolated account/instrument mode | Supported-mode admission gate |
| `configured_leverage` | Exact account/instrument leverage read-back | Existing-position leverage constraint |
| `instrument_open_position_count` | Both long and short rows for the exact instrument | Whether leverage mutation is allowed |
| `instrument_entry_health` | Typed owned/unowned position, order, Incident, and unknown-outcome classification | Direction and leverage-domain admission |
| `account_entry_health` | Typed ownership classification across all current account positions and orders | Cross-margin account admission fence |
| `maintenance_margin_brackets` | Signed current venue tiers for the exact instrument | Conservative liquidation proof |

All values are fresh, bounded, identity-matched, and included in the
action-facts digest. Missing, stale, non-finite, negative, or contradictory
facts block the CapacityClaim.

The design currently assumes an account-wide Cross-margin model because its
slot allocation uses shared `total_margin_balance` and `total_initial_margin`.
Until the Owner confirms Cross-only support or defines isolated-margin
allocation, an Isolated fact must fail closed.

### Instrument Rules

`brc_instrument_rules_current` remains the current projection for executable
venue constraints. It gains a typed `exchange_max_leverage` value and the
venue leverage/maintenance-margin facts required to estimate a conservative
pre-entry liquidation boundary. Quantity step, minimum quantity, minimum
notional, price tick, leverage limit, maintenance facts, observed time, expiry,
and projection version must belong to the same exact instrument projection.
Its identity is `venue_id + exchange_instrument_id`, never a bare symbol that
could collide across venues.

Multi-tier maintenance data is stored as one schema-versioned typed payload with
a canonical digest. It is decoded into frozen models before domain calculation;
the domain never reads an unvalidated loose JSON dictionary.

The selected maximum is always:

```text
permitted_max_leverage
= min(owner_policy.max_leverage, instrument_rules.exchange_max_leverage)
```

The system never assumes that every instrument supports 10x merely because the
Owner policy allows 10x.

## Slot-Aware Budget Algorithm

### Step 1: Validate Capacity Count

```text
active_ticket_count < max_concurrent_tickets
remaining_slots = max_concurrent_tickets - active_ticket_count
```

For admission, `active_ticket_count` means the number of Tickets that still own
capital/exposure authority. It includes ENTRY, open position, protection,
exit/recovery, and pre-match reconciliation states. It excludes a flat,
order-free, reconciliation-matched Ticket whose budget, count, and Netting
Domain have already been released even if Settlement or Review is still
pending. Any Ticket with incomplete release remains counted regardless of its
display status.

### Step 2: Compute Planned Stop Risk

```text
planned_stop_risk_budget
= total_wallet_balance * planned_stop_risk_fraction

risk_per_unit
= abs(entry_reference_price - initial_stop_price)

risk_quantity
= floor_to_step(planned_stop_risk_budget / risk_per_unit)

risk_target_notional
= risk_quantity * entry_reference_price
```

The rounded final `planned_stop_risk` must be positive and must not exceed the
frozen `planned_stop_risk_budget`.

### Step 3: Compute Account Margin Capacity

The 90% policy is an account-wide initial-margin ceiling, not permission for
each Ticket to consume 90% independently.

```text
account_initial_margin_limit
= total_margin_balance * max_initial_margin_utilization

remaining_policy_margin
= max(account_initial_margin_limit - total_initial_margin, 0)

remaining_executable_margin
= min(available_margin, remaining_policy_margin)
```

The global ENTRY lane prevents another Claim from being issued while a prior
ENTRY or Initial Stop is unresolved. Existing accepted positions are already
represented by signed `total_initial_margin` and `available_margin`; they must
not be subtracted a second time from PostgreSQL reservations.

### Step 4: Allocate One Slot

```text
ticket_margin_budget
= remaining_executable_margin / remaining_slots
```

Unused prior-slot margin remains visible through the next fresh account facts
and is redistributed across the then-remaining slots. There is no fixed symbol,
strategy, or Ticket-specific quota.

### Step 5: Build Permitted Leverage Candidates

The arithmetic lower bound for carrying the full risk target is:

```text
required_leverage
= ceil(risk_target_notional / ticket_margin_budget)
```

When the exact account/instrument is flat, candidate leverage values are every
integer from `1` through `permitted_max_leverage`. When either side already has
an open position, no leverage mutation is permitted and the only candidate is
the exact current `configured_leverage`. A missing, non-positive, fractional, or
above-policy configured leverage blocks the new opposite-side Ticket.

### Step 6: Evaluate Quantity And Liquidation Safety Per Candidate

For each permitted leverage candidate `L`:

```text
margin_quantity(L)
= floor_to_step(
    ticket_margin_budget * L / entry_reference_price
  )

final_quantity(L)
= min(risk_quantity, margin_quantity(L))

final_notional(L)
= final_quantity(L) * entry_reference_price

reserved_margin(L)
= final_notional(L) / L

planned_stop_risk(L)
= final_quantity(L) * risk_per_unit
```

The exact candidate quantity, leverage, current account exposure, margin mode,
and typed venue maintenance brackets then produce a conservative projected
liquidation boundary. The candidate remains eligible only when:

```text
projected_liquidation_distance(L)
>= stop_distance * min_liquidation_distance_to_stop_distance_ratio
```

The prices must also be directionally ordered:

```text
long:  projected_liquidation_price(L) < initial_stop_price < entry_reference_price
short: entry_reference_price < initial_stop_price < projected_liquidation_price(L)
```

The calculation may not use a generic `entry_price / leverage` shortcut as
exchange truth. Missing or stale bracket facts, unsupported margin mode, an
unprovable boundary, a quantity below venue minimum, a notional below venue
minimum, zero stop risk, an unsplittable TP1/runner plan, or a policy violation
removes that candidate. Initial Stop quantity and every frozen TP/exit leg must
also satisfy the venue rules applicable to that order kind.

### Step 7: Select One Deterministic Candidate

Selection follows two ordered goals:

1. If one or more eligible candidates carry the full `risk_quantity`, choose
   the lowest leverage among them.
2. Otherwise choose the eligible candidate with the greatest
   `planned_stop_risk`; break equal-risk ties by lowest leverage.

This preserves the lowest sufficient leverage when the 3% target fits, while
still shrinking deterministically when margin or liquidation safety prevents
the full target. For an instrument with an existing opposite-side position,
only its current configured leverage can win; the system never changes leverage
to improve the second Ticket.

If no candidate remains, the Claim is refused. There is no separate minimum
percentage of the 3% budget: a smaller valid Ticket may proceed when venue
minimums and liquidation safety are satisfied.

The selected projected liquidation price, bracket identity, calculated
distance, and ratio are frozen into the Claim. They are a conservative
pre-entry safety proof, not a promise that a Cross-margin liquidation boundary
can never move after other positions, PnL, fees, or venue rules change. The
exact safety ratio remains an Owner decision and is versioned in policy; the
recommended value is `2.0`.

## Immutable CapacityClaim

The CapacityClaim becomes the complete audit record for one action-time capital
decision. It freezes:

```text
capacity_claim_id
ticket_identity
account_capacity_domain_key
leverage_domain_key
owner_policy_id / owner_policy_version
runtime_scope_id / runtime_scope_version
fact_digest / action_facts_digest
account_entry_health_digest
instrument_entry_health_digest
instrument_rules_projection_version
total_wallet_balance_at_claim
total_margin_balance_at_claim
total_initial_margin_at_claim
total_maintenance_margin_at_claim
available_margin_at_claim
mark_price_at_claim
position_mode_at_claim / margin_mode_at_claim
active_ticket_count_at_claim
remaining_slots_at_claim
planned_stop_risk_fraction
planned_stop_risk_budget
max_post_fill_stop_risk_overrun_fraction
post_fill_stop_risk_limit
max_initial_margin_utilization
min_liquidation_distance_to_stop_distance_ratio
ticket_margin_budget
required_leverage
selected_leverage
configured_leverage_at_claim
exchange_max_leverage
reserved_margin
entry_reference_price
quantity / notional / risk_at_stop
maintenance_margin_bracket_identity
projected_liquidation_price / projected_liquidation_distance
projected_liquidation_distance_to_stop_distance_ratio
entry and protection plan
decision_digest
created_at_ms / expires_at_ms
```

Every financial value uses `Decimal`. Leverage and count fields use integers.
The decision digest covers the complete typed decision and prevents consumers
from silently recomputing or replacing one component.

## Immutable Ticket

The Ticket remains one Exposure Episode’s immutable execution contract. It
adds an explicit `capacity_claim_id` and freezes the selected outputs required
after the action-time facts expire:

```text
planned_stop_risk_budget
post_fill_stop_risk_limit
selected_leverage
reserved_margin
risk_reservation_basis
margin_mode
min_liquidation_distance_to_stop_distance_ratio
projected_liquidation_price
projected_liquidation_distance_to_stop_distance_ratio
```

The existing `notional`, `risk_at_stop`, quantity, entry plan, stop plan, and
take-profit plan remain. The old generic `leverage` field is renamed to
`selected_leverage` and becomes an integer.

No lifecycle service may resize the Ticket, change leverage, add to the
position, or consume a new balance snapshot after issuance.

## Budget Reservation

`brc_budget_reservations` remains one Ticket-bound reservation. It stores:

```text
venue_id / account_id
reserved_notional
reserved_risk
reserved_margin
planned_stop_risk_budget
risk_reservation_basis
status
created_at_ms
released_at_ms
```

The reservation protects the atomic issue transaction and provides an auditable
release record. Fresh exchange margin facts remain the action-time authority
for subsequent Ticket sizing.

## ENTRY Leverage Application

No new business table or parallel command chain is introduced.

The existing durable ENTRY command payload gains:

```text
desired_leverage
leverage_policy_version
leverage_fact_digest
```

The existing command result payload records:

```text
selected_leverage
exchange_configured_leverage
leverage_verified_at_ms
leverage_verification_digest
```

For a flat exact account/instrument, the command worker executes outside any
open PostgreSQL transaction:

```text
claim durable ENTRY command
-> complete fresh dispatch preflight with zero venue mutations
-> set_leverage(selected_leverage)
-> signed exact-instrument leverage read-back
-> require exact equality
-> create_order with deterministic client_order_id
-> persist accepted, rejected, or outcome_unknown result
```

For an instrument with an existing position, `set_leverage` is skipped and the
command revalidates that the current configured leverage equals the Ticket’s
selected leverage before `create_order`.

Protection, take-profit, exit, cancel, replacement, and controlled-flatten
commands never carry leverage mutation intent.

### Dispatch-Time Revalidation

Ticket issuance and exchange dispatch are separate transactions, and a crash may
delay a prepared command. Immediately before the first exchange mutation, the
Entry worker performs one fresh read-only preflight. It verifies:

```text
Ticket and durable command are still the one applicable ENTRY generation
-> Claim and command deadline remain current
-> exact Owner Policy version is still current, enabled, and write-authorized
-> exact Runtime Scope version is still current and enabled
-> runtime commit/schema capability still matches
-> position mode is independent_sides and margin mode is supported
-> no runtime/account/instrument Incident fence applies
-> same Netting Domain is externally flat and order-free
-> exact instrument ownership and opposite-side health remain consistent
-> frozen risk_at_stop remains within current wallet-relative policy
-> frozen reserved_margin still fits current executable margin
-> fresh executable quote keeps the stop on the protective side
-> frozen quantity at the fresh quote remains within post-fill risk tolerance
-> liquidation safety still passes with fresh mark/account/maintenance facts
-> configured leverage state still matches the flat/open instrument branch
```

For the already-issued Ticket, the executable-margin check is:

```text
dispatch_policy_margin
= max(
    total_margin_balance * max_initial_margin_utilization
    - total_initial_margin,
    0,
  )

dispatch_executable_margin
= min(available_margin, dispatch_policy_margin)

reserved_margin <= dispatch_executable_margin
```

The Ticket is already counted in PostgreSQL, but its unsubmitted order is not
assumed to be present in exchange `total_initial_margin`. The frozen reservation
is compared once; it is not subtracted and then compared again.

If preflight fails before any exchange mutation, the durable ENTRY command is
authoritatively refused with a typed reason, the unexposed Ticket becomes
terminal, and its lane, reservation, count, and Netting Domain are released in
the normal reducer path. The Signal and Ticket are not retried.

Preflight never resizes or reprices the immutable Ticket. A favorable quote may
pass with lower projected stop risk; an unfavorable quote that breaches the
frozen hard risk or liquidation boundary is refused before exposure.

Once `set_leverage` or `create_order` may have reached the venue, timeout or
process loss is an unknown mutation outcome. It must be reconciled from exact
leverage, order, fill, and position truth before release. A successfully changed
flat-instrument leverage is not restored merely because the later ENTRY order is
authoritatively rejected; it is harmless configuration state and may be changed
by a later flat-instrument Ticket.

### Post-Fill Stop-Risk Reconciliation

The Ticket is sized from an entry reference, but market execution produces an
actual average fill price and an actual venue position-risk state. On exact
full-fill reconciliation, typed facts use the frozen rounded Initial Stop to
calculate:

```text
actual_stop_risk_at_fill
= quantity * abs(average_fill_price - initial_stop_price)

post_fill_stop_risk_limit
= planned_stop_risk_budget
   * (1 + max_post_fill_stop_risk_overrun_fraction)

actual_liquidation_distance_to_stop_distance_ratio
= actual_liquidation_distance / actual_stop_distance
```

The actual liquidation proof uses the signed current position/account risk
snapshot and the same frozen policy ratio as pre-entry. It must preserve the
correct price ordering. Missing or contradictory liquidation evidence is not
treated as safety success merely because the Initial Stop price exists.

The result has five typed outcomes:

| Outcome | Condition | Lifecycle action |
| --- | --- | --- |
| Within budget | `actual_stop_risk_at_fill <= planned_stop_risk_budget` | Install Initial Stop and continue normally |
| Tolerated overrun | Budget exceeded but hard limit not exceeded | Record exact variance, install Initial Stop, continue normally |
| Hard overrun | `actual_stop_risk_at_fill > post_fill_stop_risk_limit` | Open account-scoped Incident, install Initial Stop, then controlled-flatten without placing TP1 |
| Liquidation safety degraded or unprovable | Actual price ordering fails, actual ratio is below the frozen minimum, or signed risk evidence is unavailable | Open account-scoped Incident, install valid Initial Stop, then controlled-flatten without placing TP1 |
| Protection direction invalid | Long stop is not below fill, or short stop is not above fill | Open account-scoped Incident and controlled-flatten immediately because the frozen stop is no longer valid protection |

For any protect-then-flatten outcome, `EntryFilled` still prepares the Initial
Stop and freezes a `flatten_after_protection` disposition.
`InitialStopConfirmed` then prepares the durable controlled-flatten command
instead of TP1. If Initial Stop is rejected or unknown, the existing
emergency-exit and reconciliation semantics remain authoritative.

After confirmed flatness, Reconciliation cancels the exact owned stop residue,
resolves the Incident, and releases capacity through the normal
ReconciliationMatched path.
The immutable Ticket and its planned reservation are never rewritten to hide
slippage; actual fill risk, actual liquidation evidence, and disposition are
append-only event evidence and current aggregate fields.

## Transaction Ownership

### Claim Construction

Network facts are gathered before opening a database transaction. The
application then reads exact current policy, active Ticket count, Netting Domain
occupancy, and instrument-rule projection in bounded queries.

Pure domain calculation performs no SQLAlchemy, CCXT, filesystem, subprocess,
or logging work.

### Ticket Issue

The existing short issue transaction remains atomic:

```text
lock global ENTRY lane
-> lock exact venue + account exposure row
-> re-read current Owner Policy
-> re-read exact Runtime Scope and applicable open Incident fences
-> verify Claim identity, version, digest, and expiry
-> verify active Ticket count remains below current policy
-> verify exact Netting Domain remains unoccupied
-> verify current instrument ownership projection remains compatible
-> persist CapacityClaim
-> persist immutable Ticket
-> persist Budget Reservation
-> reserve account exposure count and display aggregates
-> claim Netting Domain
-> create Trade Aggregate and first Trade Event
-> persist durable ENTRY command
-> commit
```

No venue call occurs inside this transaction.

### Release

Budget, Account Capacity count, and Netting Domain release together when exact
Reconciliation proves the position flat, all owned orders absent, all unknown
mutation outcomes resolved, and no exposure-safety Incident remains. The same
short transaction records `ReconciliationMatched`, releases those three
authorities exactly once, and moves the Ticket to Settlement. Settlement and
Review remain mandatory audit work but do not consume a position slot or block
a new Ticket in the released domain. A manually changed database row is never a
normal runtime release path.

## Policy, Scope, And Strategy Changes

Policy changes affect future capital authority but must not rewrite an Exposure
Episode that already exists. The boundary depends on whether exchange mutation
may already have occurred:

| Ticket point | Policy/scope change result | Exchange-write authority |
| --- | --- | --- |
| No Ticket issued | Latest current policy and scope apply | No old authority exists |
| Ticket issued; ENTRY command still prepared and no venue mutation attempted | Any policy-version mismatch, policy disable, write disable, scope-version mismatch, or scope disable terminally supersedes ENTRY and releases the unexposed Ticket | No ENTRY is sent |
| ENTRY command claimed and mutation outcome is uncertain | Do not assume cancellation | Reconciliation alone determines whether exposure exists |
| ENTRY filled or an open position exists | Ticket keeps its frozen policy, strategy version, Event Spec, exit policy, quantity, stop, and leverage evidence | Protection, recovery, exit, reconciliation, Settlement, and Review continue through terminal completion |
| Reconciliation matched; Settlement or Review pending | Capital and Netting Domain authority are already released; audit retains frozen identity | No exposure write remains; later Tickets use current policy |
| Ticket terminal and released | No retained execution authority | A later market event uses only the latest current policy and scope |

Raising policy limits never expands an existing Ticket. Lowering limits does not
resize or automatically flatten an already protected Ticket. It blocks or sizes
only later Tickets unless the Owner invokes a separate explicit emergency
flatten operation within the existing durable command chain.

`real_submit_enabled=false` is a new-ENTRY authority fence. It must not disable
Initial Stop, protection repair, exit, controlled flatten, cancellation, or
reconciliation writes needed to make existing exposure safe and flat. A total
service/write fence is valid only after external flatness and zero open orders
are proved, or as a deliberate emergency intervention with separately managed
exchange risk.

Disabling a Runtime Scope or StrategyGroup immediately stops new observation and
new ENTRY from that scope. Ready Signals are superseded rather than queued. An
unsubmitted Ticket is released under the table above; an exposed Ticket finishes
under its frozen identity. Strategy kill becomes final only after every owned
Ticket for that strategy is terminal, exchange-flat, order-free, reconciled,
settled, and reviewed.

## Failure Semantics

| Failure | Result |
| --- | --- |
| Missing/stale account facts | No CapacityClaim |
| Missing/stale instrument rules | No CapacityClaim |
| Unsupported or contradictory margin mode | No CapacityClaim |
| Invalid or non-protective stop | No CapacityClaim |
| Quantity cannot support the frozen TP1/runner plan | No CapacityClaim |
| Three capital-owning Tickets | Capacity exhausted |
| Same Netting Domain occupied | Admission refused |
| Open account/runtime Incident fence | Admission refused for the applicable scope |
| External position/order or residual exact-instrument order | Leverage Domain blocked; no adoption or cancellation |
| Existing instrument leverage above policy maximum | Admission refused |
| Existing instrument leverage insufficient for full target | Shrink using existing leverage |
| Liquidation proof missing, stale, or below policy ratio | No CapacityClaim |
| Policy or Runtime Scope version changes before dispatch | Unexposed Ticket terminally superseded and released |
| Fresh margin or wallet budget no longer carries frozen Ticket | Pre-dispatch ENTRY refusal; no venue mutation |
| Fresh quote breaks protection direction, risk tolerance, or liquidation safety | Pre-dispatch ENTRY refusal; no venue mutation |
| `set_leverage` rejected | ENTRY command rejected; no order submit |
| Leverage read-back missing or mismatched | No order submit; fail-closed |
| Timeout after any exchange mutation | `outcome_unknown`; never blind resend |
| ENTRY authoritative rejection | Terminal; release budget and lane |
| Partial ENTRY fill | Existing Incident and controlled-flatten contract |
| Actual fill risk exceeds hard tolerance | Protect first, then controlled-flatten; no TP1 |
| Frozen stop is no longer protective relative to fill | Immediate controlled-flatten Incident |
| Initial Stop unresolved | Global ENTRY lane remains held |

Leverage mutation and order submission form one durable ENTRY intent. Exact
reconciliation must distinguish “no order exists,” “order exists,” and
“external outcome remains unknown” without generating a second ENTRY.

Refusal classifications remain specific. `budget_exhausted` is used only for
count, wallet-risk, margin, or venue-minimum exhaustion. Margin-mode mismatch,
instrument ownership conflict, active Incident fence, liquidation proof failure,
policy/scope drift, leverage mismatch, and stale facts keep distinct typed
statuses so Owner-facing blockers and tests cannot collapse unrelated failures
into one generic capacity result.

## PostgreSQL Changes

No new business table is required.

| Existing table | Change |
| --- | --- |
| `brc_owner_policy_current` | Replace fixed gross/fixed-ticket fields and `target_leverage` with risk fraction, margin utilization, max leverage, supported margin mode, safety ratios, and count policy |
| `brc_instrument_rules_current` | Key by `venue_id + exchange_instrument_id`; add `exchange_max_leverage`, typed maintenance-margin bracket payload, schema version, and digest |
| `brc_capacity_claims` | Add frozen account, slot, margin, instrument-health, liquidation-proof, tolerance, and selected-leverage decision fields |
| `brc_trade_tickets` | Add Claim identity and frozen budget/safety outputs; rename leverage semantics |
| `brc_trade_aggregates` | Add actual stop risk, actual liquidation evidence at fill, and typed post-fill risk disposition |
| `brc_budget_reservations` | Add exact venue/account identity, reserved margin, planned budget, and risk basis |
| `brc_account_exposure_current` | Key the projection by exact `venue_id + account_id`; retain current count and display aggregates |
| `brc_runtime_incidents` | Add typed `entry_block_scope` and canonical `entry_block_key` |

`brc_owner_policy_events` and `brc_exchange_commands` already use typed identity
plus JSON payloads and do not need new tables. `brc_account_exposure_current`
retains gross notional and gross stop risk as observability projections, but
they are no longer admission caps. `active_ticket_count` remains authoritative
for the configured Ticket count boundary. The baseline keeps the same business
table set; this program changes columns and constraints, not table count.

Because the current program uses one clean baseline and the Owner authorized a
forward-only BRC rebuild, implementation modifies `0001_initial` directly and
rebuilds the isolated BRC PostgreSQL database after exact flatness and
write-fence checks. No compatibility migration or old-column fallback is
created.

## Code Structure And Coding Standards

The implementation keeps responsibilities narrow:

| File or module | Responsibility |
| --- | --- |
| `domain/capacity.py` | Frozen capacity facts, policy, Claim, statuses, and decision identities |
| `domain/capacity_sizing.py` | Pure slot allocation, leverage selection, quantity rounding, and refusal reasons |
| `domain/account_entry_health.py` | Pure account-wide current ownership and Cross-margin admission classification |
| `domain/instrument_entry_health.py` | Pure owned/unowned position, order, leverage-domain, and conflict classification |
| `domain/incident_blocking.py` | Typed Incident-to-entry-fence scope without free-form string inference |
| `domain/post_fill_risk.py` | Pure actual fill risk calculation and lifecycle disposition |
| `application/build_capacity_claim.py` | Gather typed inputs and invoke the pure decision |
| `application/issue_ticket.py` | Revalidate and atomically issue one Ticket |
| `application/revalidate_entry_dispatch.py` | Perform fresh read-only preflight before the first exchange mutation |
| `application/runtime_facts.py` | Frozen action-time, account-health, maintenance, dispatch, and post-fill risk facts |
| `application/ports.py` | Named repository and venue contracts |
| `infrastructure/pg_models.py` | SQLAlchemy table declarations matching the single baseline |
| `infrastructure/pg_repositories.py` | Exact typed persistence mapping |
| `infrastructure/venue_adapter.py` | Signed account facts, leverage set/read-back, and venue order mutation |
| `infrastructure/runtime_authority_seed.py` | Deterministic versioned policy bootstrap |

Required coding rules:

- use frozen Pydantic models with `extra="forbid"` at every core boundary;
- use `Decimal` for all financial arithmetic and explicit floor/ceiling modes;
- use integer leverage values and reject booleans or fractional leverage;
- keep domain modules free of infrastructure imports and side effects;
- avoid loose dictionaries between application and domain layers;
- use exact identity and bounded current-state queries;
- key account capacity by `venue_id + account_id`, never by a potentially
  ambiguous bare account string;
- represent Incident entry fences with typed scope and canonical identity;
- keep venue I/O outside transactions and timeout-bounded;
- persist every exchange mutation under a durable command identity;
- delete fixed-Envelope tests and fields instead of preserving compatibility;
- place policy literals only in deterministic seed/test authority;
- log identities and refusal classifications, never credentials or full signed
  exchange payloads;
- do not add a generic rules engine, plugin system, or strategy-specific budget
  branch for this program.

## Hardcoding Retirement

The following production semantics disappear:

```text
max_gross_notional admission gate
max_gross_risk_at_stop admission gate
max_ticket_risk_at_stop fixed-USDT gate
target_leverage fixed for every Ticket
Acceptance=1 Ticket / Full=2 Tickets fixed envelope
20/40 USDT production notional defaults
10/20 USDT fixed risk defaults
```

The following remain explicit by design:

- one global ENTRY lane;
- one Ticket per Exposure Episode;
- one active Ticket per Netting Domain;
- maximum three capital-owning Tickets from Owner Policy;
- 3%, 90%, and 10x in the committed policy seed;
- exact six-strategy Registry scope outside this capacity program.

## Runtime Ownership And Performance

The four persistent workers remain unchanged:

| Worker | Ownership |
| --- | --- |
| Observation | Market observation and StrategySignal production |
| Entry | Candidate arbitration, fresh facts, CapacityClaim, Ticket issue, dispatch preflight, leverage application, and ENTRY dispatch |
| Lifecycle | Post-fill risk disposition, Initial Stop, TP1, runner, exit, flatten, and terminal transitions |
| Reconciliation | External truth, unknown outcomes, ownership/residue, Incident resolution, Settlement, and Review handoff |

Each Entry cadence performs only bounded queries for one candidate, one policy,
one account projection, one current account position/order snapshot, one exact
instrument rule, and one exact Netting Domain. Venue account snapshots contain
only currently open rows and are timeout-bounded. No full-history scan,
generated file, or timer cold start is introduced.

## Test Strategy

### Pure Domain Tests

Tests must prove:

- `totalWalletBalance * 0.03` produces the exact Decimal budget;
- active counts 0, 1, and 2 allocate across 3, 2, and 1 remaining slots;
- active count 3 refuses capacity;
- account-wide initial-margin utilization never exceeds 90%;
- the selected leverage is the lowest safe integer that fits the full risk
  target inside the slot budget;
- the selected leverage never exceeds Owner or venue maximum;
- when no leverage carries the full target, selection maximizes safe planned
  stop risk and breaks ties toward lower leverage;
- a 10x-insufficient target shrinks rather than consuming another slot;
- venue quantity step and minimums are applied after both risk and margin caps;
- a quantity that cannot produce the registered TP1 leg and positive runner is
  rejected as an unexecutable exit plan, not accepted as a small Ticket;
- existing configured leverage is adopted without mutation;
- same-instrument same-direction Signals conflict regardless of StrategyGroup;
- a healthy opposite-side Ticket is compatible only through the shared
  Leverage Domain and exact existing leverage;
- external/manual account ownership classifies to the Account Capacity Domain,
  while owned residue and leverage contradiction classify to the exact
  Leverage Domain;
- runtime, account, instrument, and non-blocking Incident scopes classify
  deterministically;
- Cross and independent-sides facts are validated separately;
- liquidation price ordering and the configured distance ratio pass on the
  exact boundary and fail immediately below it;
- stale or contradictory maintenance brackets fail closed;
- post-fill risk classifies within-budget, tolerated-overrun, hard-overrun, and
  invalid-protection-direction boundaries exactly;
- actual post-fill liquidation safety classifies valid, below-ratio, wrong-side,
  missing, and contradictory evidence exactly;
- non-finite, stale, negative, or contradictory inputs fail closed.

### PostgreSQL Tests

Tests must prove:

- the empty baseline retains the exact 33-table business set and contains only
  the new policy fields and constraints;
- fixed Envelope columns are absent;
- Claim, Ticket, and Budget Reservation persist exact Decimal and integer values;
- policy versions are monotonic and events preserve the full payload;
- Account Capacity projections and reservations use exact venue/account keys;
- instrument-rule projections use exact venue/instrument keys;
- Incident entry-block scope and canonical key are constrained and queryable;
- actual stop risk and post-fill disposition persist without mutating the
  immutable Ticket;
- three Tickets can exist across independent Netting Domains;
- opposite long/short Tickets for one instrument coexist while a third Ticket
  uses another instrument;
- same-instrument same-direction Tickets cannot commit across strategies;
- a fourth Ticket cannot commit;
- concurrent issue attempts serialize on the global lane and exact account row;
- ReconciliationMatched atomically releases budget, Account Capacity count, and
  Netting Domain exactly once while Settlement/Review may remain pending.

### Venue And Command Tests

Tests must prove:

- flat instrument calls `set_leverage`, then signed read-back, then
  `create_order`;
- dispatch preflight occurs before `set_leverage` or `create_order`;
- stale policy/scope, an Incident fence, external ownership, insufficient fresh
  wallet risk, insufficient fresh margin, or unsafe fresh quote causes zero
  venue mutations;
- read-back mismatch emits no order;
- either-side existing position emits no leverage mutation;
- existing matching leverage permits order submit;
- a successful flat-instrument leverage change followed by authoritative order
  rejection does not issue a compensating leverage mutation;
- protection and exit commands never set leverage;
- timeout and unknown outcomes never create a second ENTRY generation.

### Lifecycle And Policy Tests

Tests must prove:

- a normal or tolerated fill installs Initial Stop and proceeds to TP1;
- a hard stop-risk overrun installs Initial Stop and then controlled-flattens
  without creating TP1;
- degraded or unprovable actual liquidation safety follows the same
  protect-then-flatten path;
- an invalid post-fill stop direction immediately requests controlled flatten;
- policy or scope disable before any venue mutation terminally releases the
  unexposed Ticket;
- policy or strategy disable after fill does not suppress protection, exit,
  recovery, reconciliation, Settlement, or Review;
- a policy limit increase does not resize an existing Ticket and a decrease does
  not automatically flatten a protected Ticket;
- StrategyGroup kill becomes final only after all owned Tickets are terminal and
  flat.

### Full-Chain Certification

Full-chain tests must prove:

- three natural StrategySignals in distinct Netting Domains can create three
  serial Tickets and then progress concurrently;
- two of those Tickets may be opposite sides of one instrument, but two
  same-direction Signals from different strategies cannot create two Tickets;
- the slot algorithm preserves capacity for later Tickets;
- an account-scoped unknown outcome or unowned exposure blocks every later
  ENTRY, while an instrument-scoped owned residue/leverage conflict leaves
  unrelated instruments eligible;
- a blocked or superseded Signal is never revived after capacity or domain state
  changes; a later trade requires a new market event;
- post-fill hard overrun reaches protected-then-flat terminal recovery with no
  residual stop order;
- each Ticket owns one immutable Claim, reservation, command lineage, position,
  settlement, and review;
- no strategy detector contains capital or leverage decisions;
- no retired fixed-Envelope name remains in production code, schema, seed,
  tests, or current documents;
- healthy idle cadence creates no JSON or Markdown output.

## Deployment And Cutover

Implementation and deployment proceed fix-forward:

```text
keep Tokyo exchange writes disabled
-> freeze the three remaining Owner safety decisions in the committed design
-> implement and certify locally from an empty PostgreSQL database
-> prove current exchange flatness and zero open orders
-> fence all BRC writers
-> rebuild only the isolated BRC PostgreSQL database from revised 0001_initial
-> seed the exact versioned dynamic and safety policy with real_submit_enabled=false
-> deploy the exact committed release
-> start the four persistent workers
-> run readonly schema, seed, position-mode, margin-mode, balance, maintenance,
   leverage, ownership, Incident-fence, and scope probes
-> arm one controlled Ticket under the new model
-> prove ENTRY leverage, Initial Stop, terminal flatness, release, Settlement,
   Review, and zero Incident
-> enable normal three-Ticket authority only after certification
```

Non-quantitative services, databases, containers, nginx configuration, and
program data remain outside the mutable allowlist.

## Acceptance Criteria

The program is complete only when all of the following are current and direct:

1. Owner Policy is versioned in PostgreSQL with `3`, `0.03`, `0.90`, and `10`.
2. Supported margin mode, liquidation-distance ratio, and post-fill overrun
   tolerance are explicitly Owner-approved and versioned in the same policy.
3. Fixed gross-notional, fixed gross-risk, fixed per-Ticket USDT risk, and fixed
   target-leverage semantics are absent from production authority.
4. Capacity uses fresh signed wallet, margin, initial-margin, available-margin,
   maintenance-margin, mark-price, position-mode, margin-mode, account-health,
   instrument-health, maintenance-bracket, and configured-leverage facts.
5. Account Capacity uses exact `venue_id + account_id`; same-direction,
   opposite-direction, external-ownership, and Incident conflicts follow the
   typed scope matrix.
6. Slot-aware sizing preserves remaining Ticket capacity and uses no more than
   the account-wide initial-margin policy.
7. Claim, Ticket, reservation, event, and command retain exact versioned audit
   identity; ReconciliationMatched releases budget/count/domain exactly once
   without waiting for Settlement or Review.
8. Three independent Tickets issue serially and progress concurrently,
   including healthy opposite sides of one instrument.
9. A same-direction second Ticket and a fourth capital-owning Ticket are refused
   without exchange side effects.
10. Same-instrument leverage is never mutated while either side is open.
11. ENTRY is submitted only after fresh dispatch preflight and exact leverage
    equality are proven.
12. Policy/scope changes before dispatch release unexposed Tickets, while
    exposed Tickets retain lifecycle and recovery authority under frozen terms.
13. Post-fill actual stop risk and liquidation evidence are recorded; hard
    overrun or degraded liquidation safety protects then flattens and leaves no
    TP or stop residue.
14. Unknown outcomes, rejection, and partial fill retain current fail-closed
    lifecycle semantics.
15. The clean baseline rebuilds from zero, keeps the same business-table set,
    and contains no compatibility path.
16. Targeted tests, full Trading Kernel tests, Ruff, Mypy, schema certification,
    document authority checks, retired-semantics scans, and `git diff --check`
    pass.
17. Tokyo runs the exact release with writes initially disabled and one
    controlled terminal Ticket proves the new budget model before full
    three-Ticket authority is enabled.

## Final Decision

This design extends the existing Trading Kernel rather than restoring the old
account-risk system. It introduces no new business table and no parallel
execution path. The core architectural change is one pure, slot-aware capacity
decision whose complete inputs and outputs are frozen into the existing Claim,
Ticket, reservation, and durable command lineage. Conflict ownership,
dispatch-time drift, post-fill risk, policy change, and StrategyGroup disable
semantics are explicit. Only the three Owner safety values listed above remain
outside final authority.
