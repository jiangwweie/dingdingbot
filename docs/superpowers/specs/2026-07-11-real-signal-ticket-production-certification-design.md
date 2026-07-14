# P0-RT Real-Signal Ticket Closure And Production-Shaped Certification

Status: approved for implementation by standing Owner direction

Date: 2026-07-11

Scope: production execution-input closure plus five-StrategyGroup trading-door certification

## Objective

Close the first shared engineering blocker discovered after real production
signals reached Action-Time lanes, and make the same class of boundary defect
detectable before deployment:

```text
Binance public facts
-> PG pretrade_public fact snapshot
-> action-time normalized execution pricing
-> one sizing and stop-risk decision
-> promotion eligibility and capital arbitration
-> budget reservation
-> Action-Time Ticket
-> FinalGate
-> Operation Layer handoff
-> Runtime Safety State
-> disabled-smoke protected submit request
```

The implementation must certify every current executable Event Spec using the
same nested public-fact shape written by the production collector. It must not
grant exchange-write authority or treat synthetic inputs as live facts.

## Verified Starting State

- Tokyo release `12feb47e2cd777a93c314c781dbafdcd69930cfc` runs
  Alembic migration `112`.
- Five current StrategyGroups own six current executable Event Specs and
  twenty-two active candidate scopes.
- The first watcher cycle after that release produced seven fresh trial-grade
  signals, seven promotions, and six real-submit Action-Time lanes.
- The same production cycle produced zero Action-Time Tickets and zero current
  Runtime Safety State rows.
- Replaying the Ticket consumer against each of the six lanes produced the
  same blockers:

```text
risk_reservation_entry_reference_price_missing
risk_reservation_intended_qty_invalid
risk_at_stop_invalid
```

- The public-fact collector already obtains `mark_price`, `bid_price`,
  `ask_price`, `qty_step`, and `min_notional` and persists them beneath the
  nested `facts` object in PG.
- The action-time materializer deep-merges the public row but only exports
  selected top-level price aliases. The Ticket risk helper searches those
  loose aliases and never consumes the nested production price shape.
- Promotion converts an invalid stop-risk reservation into numeric zero and
  does not classify zero as a blocker. It can therefore create a lane that the
  Ticket consumer must reject.
- Existing integration fixtures inject top-level `last_price` and downstream-
  ready values. They prove downstream behavior after the defective boundary,
  not the production producer-to-consumer contract.

## Root Cause

This is not a strategy dictionary defect and not six independent strategy
failures. It is one system-design failure with four manifestations:

1. **Shape ownership is implicit.** A producer writes a nested typed market
   shape while a consumer searches an undocumented alias list.
2. **Sizing has more than one owner.** Promotion estimates risk, Ticket
   recomputes it, and protected submit computes quantity again.
3. **Invalid inputs are collapsed to zero.** The zero value loses the reason
   why a decision cannot be computed and allows a later lifecycle object to be
   created.
4. **Tests start after the risky boundary.** Hand-built fixtures are
   semantically complete but structurally unlike production.

The systemic correction is therefore a typed execution-input boundary plus a
production-shaped certification gate, not another alias patch in a single
strategy.

## Architecture Decision

### 1. Normalize execution pricing once at Action-Time

Introduce a named, Decimal-backed `ActionTimePricingReference` model owned by
the Action-Time application layer. It is derived only from the current PG
`pretrade_public` snapshot and carries:

- `entry_reference_price`;
- `entry_reference_kind`;
- `mark_price`, `bid_price`, and `ask_price`;
- `qty_step` and `min_notional`;
- source snapshot identity and validity window.

The side-specific reference is deterministic:

| Side | Entry reference | Reason |
| --- | --- | --- |
| `long` | current positive best ask | conservative executable-side estimate |
| `short` | current positive best bid | conservative executable-side estimate |

Mark price remains a sanity and valuation fact. It is not a silent fallback
for a missing side quote. Missing, stale, malformed, or non-positive execution
pricing is an engineering/runtime-data blocker before lane creation.

### 2. Compute one quantity and stop-risk reservation

Introduce one Decimal-backed `TicketSizingRiskDecision` computed during
promotion, when owner policy, Event Spec protection, Action-Time pricing, and
exchange quantity rules are all available.

```text
target_notional
/ side-specific entry reference
-> raw quantity
-> floor to qty_step
-> validate min_notional
-> validate protective stop side
-> risk_at_stop = abs(entry - stop) * intended_qty
```

The selected decision is persisted into the existing PG budget-reservation
columns before the lane is opened. Ticket materialization validates and
consumes that reservation; it does not recompute a divergent quantity.
Protected submit uses the same persisted `intended_qty` for entry and stop.
TP1 starts from the pre-existing one-half split and is floored to the same
`qty_step`, so no order leg can reintroduce an exchange-invalid quantity. No
sizing default, leverage, notional, or capital scope is expanded.

### 3. Materialize facts, reservation, lane, and Ticket atomically

Replace the four production subprocess boundaries for Action-Time fact
materialization, current projection refresh, promotion/lane creation, and
Ticket creation with one PG application sequence. The sequence uses one outer
transaction and one rollback-capable action savepoint:

```text
read current signal/public/account facts
-> materialize action-time fact snapshot
-> refresh only PG pretrade readiness inside the same connection
-> compute and persist reservation
-> create promotion and lane
-> create Ticket
-> validate shortest TTL against completion time
-> commit the complete unit
```

If any step after promotion fails, the savepoint rolls back the action-time
fact, promotion, reservation, lane, and partial Ticket as one unit. The outer
transaction then persists structured process outcomes with the exact first
blocker for every affected `StrategyGroup + symbol + side`. A lane without its
corresponding valid Ticket is no longer a committable state, and one failed
lane cannot hide concurrent failures in other strategies.

Candidate Pool, Daily Table, Goal Status, and Owner snapshots are published
after the critical path. They are not built inside the Ticket savepoint. A
persisted business blocker keeps the watcher process healthy, remains visible
during no-signal periods, and yields to a fresh signal long enough for the same
lane to re-certify and clear the blocker.

The sequence is event-triggered and subprocess-timeout bounded. FinalGate,
Operation Layer handoff, and Runtime Safety State remain separate consumers
that revalidate the committed Ticket and its TTL; they do not join the Ticket
transaction or weaken their own gates.

### 4. Move execution-input failure before the Action-Time lane

Promotion eligibility must preserve the exact failure reason. The following
conditions block the candidate before arbitration and lane creation:

- missing or invalid side-specific entry quote;
- missing or invalid quantity step;
- rounded quantity less than or equal to zero;
- rounded notional below exchange minimum;
- missing or invalid stop reference;
- stop on the wrong side of entry;
- risk at stop less than or equal to zero;
- risk at stop exceeding the Owner-authorized loss unit.

These are not `waiting_for_market` and not strategy semantic failures. They are
typed execution-input, exchange-rule, protection, or capital-scope blockers.

### 5. Add a production-shaped certification gate

The gate starts from a producer-shaped nested public row, not from a manually
flattened Action-Time object. It runs the six current Event Specs through PG
and asserts that every one reaches the non-executing trading door.

| StrategyGroup | Event Spec | Certification side |
| --- | --- | --- |
| `CPM-RO-001` | `CPM-LONG` | long |
| `MPG-001` | `MPG-LONG` | long |
| `MI-001` | `MI-LONG` | long |
| `SOR-001` | `SOR-LONG` | long |
| `SOR-001` | `SOR-SHORT` | short |
| `BRF2-001` | `BRF2-SHORT` | short |

Each case must prove:

1. the public snapshot contains nested production `facts` and no injected
   top-level `last_price`;
2. action-time materialization emits the typed pricing reference;
3. promotion persists a positive, step-normalized sizing/risk reservation;
4. Ticket, FinalGate, Operation Layer handoff, and Runtime Safety State are
   materialized with matching lineage;
5. disabled-smoke builds the protected submit request from the reserved
   quantity;
6. `exchange_write_called`, `order_created`, and live profile mutation remain
   false.

This gate becomes release-blocking for changes to the public-fact producer,
Action-Time normalization, promotion, Ticket, protection, sizing, FinalGate,
Operation Layer, or protected submit boundary.

### 6. Preserve the engineering blocker in PG current truth

A later no-signal tick must not erase an unresolved engineering defect and
replace it with `waiting_for_market`. The current projection must distinguish:

```text
market condition absent after all prerequisites are certified
```

from:

```text
market condition currently absent, but the latest attempted eligible chain
failed on an unresolved engineering prerequisite
```

The latter remains the first blocker until a successful production-shaped
certification or a later successful live chain proves it closed. Historical
evidence stays append-only; current truth stays in PG projections.

## Data And Authority Boundaries

- PG/current services remain runtime truth.
- No new JSON, Markdown, JSONL, YAML, report directory, or file-backed runtime
  authority is introduced.
- Strategy RequiredFacts remain evaluator-owned; execution pricing and
  exchange quantity rules are infrastructure facts, not strategy semantics.
- Owner policy continues to own notional, leverage, loss unit, symbol/side,
  runtime profile, and production-stage authority.
- FinalGate, Operation Layer, duplicate-submit, position/open-order,
  protection, reconciliation, and settlement controls remain mandatory.
- Disabled-smoke and synthetic certification cannot grant exchange-write
  authority.

## Error Handling And Fail-Closed Rules

- Missing `facts` object: block before promotion.
- Missing best ask for long or best bid for short: block before promotion.
- Mark-only data: block; do not infer an executable quote.
- Future, stale, malformed, non-positive, NaN, or infinite numeric values:
  block and preserve an exact reason.
- Invalid `qty_step`: block; do not emit an unrounded quantity.
- Quantity rounding to zero: block.
- Rounded notional below `min_notional`: block.
- Stop on the wrong side of entry or zero stop distance: block.
- Reservation/Ticket/submit quantity mismatch: hard stop.
- Expired pricing or reservation: hard stop; never refresh by mutating the
  original decision.
- Ticket sequence reaches its shortest source TTL before completion: roll back
  the action savepoint and persist only the exact timeout blocker.

## Performance And Cadence

| Dimension | Decision |
| --- | --- |
| Cadence | normalization occurs only inside the existing signal/action-time path |
| PG writes | existing fact, promotion, budget, lane, Ticket, and safety rows only |
| No-signal file writes | `0` JSON/MD files |
| CPU | bounded Decimal parsing and one quantity quantization per eligible candidate |
| External calls | no new API or subprocess call |
| Timeouts | unchanged existing collector/API timeouts |
| Retention | existing PG retention and append-only lifecycle evidence |

## Deployment And Acceptance

Acceptance requires:

1. focused red-green tests for normalization, rounding, risk, early blocker,
   Ticket consumption, and submit quantity lineage;
2. the six-Event-Spec production-shaped certification matrix;
3. all related action-time, runtime-control, FinalGate, Operation Layer, and
   protected-submit tests;
4. full repository tests and production file-I/O audit with
   `performance_risk.status=clear`;
5. a focused commit pushed to the remote branch;
6. git-based Tokyo deployment at the exact pushed commit and migration `112`;
7. healthy backend and recurring timers;
8. PG proof that all five StrategyGroups are certified to the non-executing
   trading door and current blocker truth no longer hides execution-input
   defects as market wait.

Natural market opportunity is not required for engineering certification. A
real order remains conditional on a future fresh live signal and all current
action-time safety facts.

## Rollback

No schema migration is expected. Rollback atomically repoints the Tokyo
`app/current` symlink to the previous release and restarts the backend and
timers. Existing PG lifecycle evidence remains append-only; no destructive
cleanup is included.
