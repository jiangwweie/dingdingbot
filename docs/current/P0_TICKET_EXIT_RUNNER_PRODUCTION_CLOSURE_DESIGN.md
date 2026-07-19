---
title: P0_TICKET_EXIT_RUNNER_PRODUCTION_CLOSURE_DESIGN
status: PROPOSED_AWAITING_OWNER_CONFIRMATION
authority: docs/current/P0_TICKET_EXIT_RUNNER_PRODUCTION_CLOSURE_DESIGN.md
last_verified: 2026-07-19
design_branch: codex/budget-model-review-20260714
local_head: 3e0c265550cb62491adf8d05af3dd598151006c4
production_head: 1aa05462795b0ae26d51837d73c3a90f9a86f19c
production_schema_count: 138
owner_decision: PENDING
implementation_authority: NOT_GRANTED
deployment_authority: NOT_GRANTED_BY_THIS_DOCUMENT
exchange_write_authority: NOT_CHANGED
---

# P0 Ticket Exit Runner Production Closure Design

## 1. Decision Summary

### 1.1 Core conclusion

**The current Ticket exit chain has a sound durable-command and protection
foundation, but the approved versioned Runner policy is not production-closed.**

The current implementation can:

1. create an exchange-native reduce-only SL;
2. create a reduce-only LIMIT GTC TP1 with no market fallback;
3. derive TP1 from actual entry fill and actual stop distance;
4. resize stop quantity after a TP1 partial fill;
5. move protection to a cost-adjusted break-even floor after TP1 completion;
6. submit a new Runner stop before cancelling the old stop;
7. stop and reconcile on unknown submit or cancel outcomes;
8. reconcile and finalize ordinary SL, TP1, protection and lifecycle outcomes.

The current implementation cannot yet prove the complete approved path:

~~~text
TP1 completion
-> immediate cost-adjusted break-even floor
-> 15m structural / ATR Runner facts
-> monotonic Runner stop improvement
-> invalidation or time-stop final exit
-> command-bound final fill
-> protection cleanup
-> lifecycle / settlement / review closure
~~~

The first production blocker is:

~~~text
ticket_exit_market fact producer exists
-> production lifecycle runner never invokes it
-> Tokyo PG contains zero ticket_exit_market facts
-> structural trailing, invalidation and time stop never receive due facts
~~~

The second blocker remains even after scheduling is connected:

~~~text
dynamic market fact contains closed candles only
-> consumer expects static strategy reference values in the same fact
-> reference values are absent
-> the entire market fact is discarded
~~~

The repair must close the whole problem class. It must not add a narrow
SOR-001-only alias, a second exchange writer, a per-position daemon, a file
sidecar, or a manual Owner operation.

### 1.2 Is Runner an independent thread?

**No. Runner is not currently an independent thread, and this design explicitly
rejects a dedicated per-position Runner thread or daemon.**

The production model remains:

~~~text
systemd timer every 30 seconds
-> start one short-lived lifecycle process
-> select bounded due work from PG
-> perform timeout-bounded exchange/public reads outside PG transactions
-> persist facts and decisions in short PG transactions
-> prepare at most one durable exchange command
-> command worker performs at most one exchange mutation
-> process exits
~~~

Inside one process, asynchronous I/O may be used for bounded reads. That is an
implementation detail, not an independent authority thread.

The 15-minute Runner cadence is represented by:

- closed-candle watermark;
- next_evaluation_not_before_ms;
- one immutable fact row per Ticket and closed-candle identity;
- idempotent evaluation against the current Ticket projection.

It is not represented by sleeping threads, in-memory timers, or one daemon per
position.

### 1.3 How moving stop works

Moving a stop is a durable state transition, not a direct Runner API call:

~~~text
closed 15m fact becomes due
-> evaluate frozen Ticket policy and reference facts
-> prove proposed stop is tick-aligned and improves by minimum ticks
-> insert deterministic place-new-RUNNER_SL command in PG
-> command worker claims and commits the command
-> exchange accepts the new reduce-only stop
-> PG records the new exchange order id
-> insert deterministic cancel-old-SL command
-> command worker cancels the exact old stop
-> reconciliation proves the new stop is live and the old stop is terminal
-> current projection advances active_runner_generation
~~~

At no point may the fact producer, evaluator, scheduler, read model, or Runner
policy service call the exchange directly.

## 2. Authority And Document Relationship

### 2.1 Authority order

This design follows:

1. Owner confirmation of this design;
2. current tracked code and git status;
3. current Tokyo PG, exchange-read and systemd evidence;
4. current documents under docs/current;
5. historical material only as provenance.

### 2.2 Relationship to existing lifecycle documents

This document integrates and corrects the production behavior defined by:

- P0_ACTIVE_TICKET_EXIT_POLICY_ADOPTION_AND_RUNNER_RELIABILITY_DESIGN.md;
- TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md;
- P0_C_PRODUCTION_LIFECYCLE_SCHEDULER_AND_SNAPSHOT_SOURCE_DESIGN.md;
- P0_LIFECYCLE_PRODUCTION_CERTIFICATION_AND_CLOSURE_DESIGN.md;
- POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md.

Those documents remain component contracts where they do not conflict with
this integration design.

For the following subjects, this document becomes the current integration
authority after Owner confirmation:

- production scheduling of exit market facts;
- ownership of static Ticket exit references;
- TP1 cumulative completion across order generations;
- TP1 cancel/reprice partial-fill behavior;
- command-bound strategy final exit;
- terminalization of brc_ticket_exit_policy_current.

## 3. Known Objective Facts

### 3.1 Version and runtime baseline

| Surface | Verified value | Source |
| --- | --- | --- |
| Local branch | codex/budget-model-review-20260714 | current git |
| Local HEAD | 3e0c265550cb62491adf8d05af3dd598151006c4 | current git |
| Tokyo release | 1aa05462795b0ae26d51837d73c3a90f9a86f19c | release manifest |
| Tokyo migration | 138 | production PG |
| Lifecycle timer | active, about every 30 seconds | systemd |
| Durable mutation capability | enabled | production PG and journal |
| Maintainable lifecycle now | none | production lifecycle journal |
| Nonterminal lifecycle exchange commands | zero | production PG |
| ticket_exit_market facts | zero | production PG |

The current branch has no stop-profit implementation diff against the deployed
Tokyo release. The defects described here therefore exist in both baselines.

### 3.2 Current approved SOR-LONG policy

| Policy dimension | Current value |
| --- | --- |
| StrategyGroup | SOR-001 |
| Event Spec | SOR-LONG v2 |
| Side | long |
| TP1 | actual-entry 1R |
| TP1 quantity | 50% |
| TP1 execution | LIMIT GTC |
| TP1 market fallback | forbidden |
| Runner floor | entry fee + conservative exit fee + two-tick slippage buffer |
| Runner | confirmed 15m higher-low minus 0.5 ATR |
| Minimum improvement | two ticks |
| Invalidation reference | opening_range_high |
| Time stop | 96 closed 15m bars |

### 3.3 Exact static reference lineage already available

Production PG proves that the Ticket-bound signal payload already contains:

~~~text
signal_event_id
-> signal_payload.signal_summary.evidence_payload.opening_range_high
-> exact StrategyGroup / Event Spec / side / symbol / instrument identity
~~~

For the inspected SOR-LONG SOLUSDT Ticket:

- opening_range_high = 75.5800;
- opening_range_low = 75.3000;
- the Ticket binds the exact signal_event_id;
- the policy invalidation reference_key is opening_range_high.

The missing reference is therefore not a market-data problem. It is a missing
Ticket-bound freeze and handoff.

### 3.4 Existing production outcome evidence

Historical PG contains a legacy lifecycle in which:

~~~text
ETHUSDT long
-> TP1 filled
-> RUNNER_SL materialized
-> remaining position closed
~~~

This proves the legacy TP1 and Runner protection mechanics can reach the venue.
It does not certify the current versioned policy, because that Ticket did not
exercise the current actual-entry-R, immediate-floor, 15m structural-fact and
command-bound final-exit path.

## 4. Problem Statement

### 4.1 Systemic defects

The review identified five connected defects:

| Priority | Defect | Current consequence |
| --- | --- | --- |
| P0 | Exit market fact service is not called by production lifecycle cadence | no structural Runner, invalidation or time stop |
| P0 | Static policy references are expected in dynamic candle facts | due facts would still be discarded |
| P1 | TP1 cancel/reprice partial-fill race has no residual-target transition | projection can remain partial without a live TP1 |
| P1 | Strategy final-close command has no first-class final-order lineage | normal close can fall back to EXTERNAL_CLOSE inference |
| P2 | Closed lifecycle does not terminalize exit-policy current state | stale active quantity and blockers remain in PG current |

### 4.2 Why this is one design problem

These are not five unrelated local bugs. They share one missing invariant:

**A Ticket-bound exit policy needs one durable state machine spanning immutable
entry/reference truth, dynamic closed-market facts, all TP1 generations, active
protection generation, final exit command identity and terminal current state.**

Local patches would leave competing interpretations:

- fill projector completion versus reconciler completion;
- dynamic market facts versus static entry references;
- exchange command result versus protection-order lineage;
- closed lifecycle versus nonterminal exit-policy projection.

The repair must define one owner for each transition and make all consumers use
that owner.

## 5. Goals And Non-Goals

### 5.1 Goals

1. Keep one production lifecycle scheduler and one exchange-command writer.
2. Produce due 15m exit facts automatically without a dedicated Runner thread.
3. Freeze static invalidation references from the exact Ticket-bound signal
   before real exchange submit.
4. Evaluate structural/ATR, invalidation and time-stop behavior from current PG
   truth.
5. Count TP1 fills across all generations and exact exchange order lineage.
6. Preserve the approved 50% TP1 target during cancel/reprice races.
7. Resize stop quantity immediately after every TP1 fill delta.
8. Apply the cost-adjusted floor immediately after TP1 target completion.
9. Keep every stop movement monotonic and at least two ticks better.
10. Give strategy invalidation/time-stop exits a first-class FINAL_EXIT identity.
11. Complete cleanup, settlement and review from exact command/fill lineage.
12. Terminalize exit-policy current state when position truth becomes flat.
13. Produce zero recurring JSON/Markdown files.
14. Keep all network operations outside PG transactions and within bounded
    timeouts.

### 5.2 Non-goals

- No new entry strategy or strategy parameter tuning.
- No change to TP1 reward multiple, quantity fraction or Runner formula.
- No new StrategyGroup, symbol, side, leverage, notional or exposure authority.
- No FinalGate or Operation Layer bypass.
- No replacement of exchange-native SL protection.
- No TP1 market fallback.
- No fixed TP2 for the right-tail policy.
- No per-position Runner thread or long-lived daemon in this release.
- No second exchange mutation worker.
- No repo JSON/Markdown runtime source or report-sidecar state.
- No destructive deletion of historical Ticket, order, fill or lifecycle rows.

## 6. Options Considered

### 6.1 Scheduling options

| Option | Restart safety | Authority clarity | Operational cost | Decision |
| --- | --- | --- | --- | --- |
| Dedicated thread per active position | low | low | persistent memory and race handling | rejected |
| Separate long-lived Runner daemon | medium | creates another scheduler owner | persistent process and deployment complexity | rejected for current release |
| Separate 15m systemd fact timer | high | introduces a second cadence owner | extra unit and cross-timer races | valid fallback, not recommended |
| Extend existing 30s lifecycle oneshot with a due-fact stage | high | one orchestration owner | zero work when not due | recommended |

### 6.2 Static reference options

| Option | Auditability | Extensibility | Decision |
| --- | --- | --- | --- |
| Recompute opening range from later candles | low; historical window can drift | strategy-specific | rejected |
| Hard-code opening_range_high aliases in application code | low | fails future StrategyGroups | rejected |
| Copy reference into every 15m market fact | medium; duplicates immutable truth | unnecessary PG growth | rejected |
| Freeze typed reference snapshot from exact signal lineage into Ticket exit current | high | reference-key based and asset-neutral | recommended |

### 6.3 TP1 partial race options

| Option | Policy conservation | Risk | Decision |
| --- | --- | --- | --- |
| Treat any partial fill as complete TP1 | violates 50% target | early Runner transition | rejected |
| Leave cancelled partial TP1 without replacement | violates target and can wedge | no future completion | rejected |
| Re-submit the full original TP1 quantity | may over-reduce | exposure error | rejected |
| Submit only residual target quantity and keep cumulative target authority | exact | bounded durable reprice | recommended |

### 6.4 Final-exit identity options

| Option | Lineage | Result | Decision |
| --- | --- | --- | --- |
| Continue using RUNNER_SL role for market close | ambiguous role/type | fill projector cannot distinguish stop from active close | rejected |
| Treat strategy close as EXTERNAL_CLOSE | inference-based | normal system action looks manual | rejected |
| Add explicit FINAL_EXIT command/order role | exact command/fill ownership | deterministic closure | recommended |

## 7. Recommended Runtime Architecture

### 7.1 Single orchestration owner

The existing brc-ticket-lifecycle-maintenance.timer remains the only production
orchestrator for Ticket-bound exit work.

~~~mermaid
flowchart TD
    A["systemd timer: every 30 seconds"] --> B["Select bounded PG lifecycle and due-fact scopes"]
    B --> C{"Any active or pending work?"}
    C -- "No" --> Z["Exit: zero exchange/public calls, zero files"]
    C -- "Yes" --> D["Fetch exchange snapshot outside PG transaction"]
    D --> E{"15m fact due?"}
    E -- "Yes" --> F["Fetch closed candles outside PG transaction"]
    E -- "No" --> G["Skip public fact fetch"]
    F --> H["Persist one Ticket exit fact by watermark"]
    G --> I["Short PG lifecycle transaction"]
    H --> I
    I --> J["Project fills and reconcile protection"]
    J --> K["Evaluate TP1 / floor / Runner / invalidation / time stop"]
    K --> L{"Durable command required?"}
    L -- "No" --> M["Update current projection and exit"]
    L -- "Yes" --> N["Insert deterministic prepared command"]
    N --> O["Command worker on this or next invocation"]
    O --> P["Exchange mutation outside PG transaction"]
    P --> Q["Record accepted / rejected / unknown result"]
    Q --> R["Reconcile exact order identity"]
~~~

### 7.2 Two clocks, one state machine

The design distinguishes two clocks:

| Clock | Purpose | Authority |
| --- | --- | --- |
| 30-second lifecycle cadence | exchange truth, fills, commands, reconciliation and cleanup | systemd lifecycle timer |
| closed-candle policy cadence | structural Runner, invalidation and time stop | PG watermark plus policy timeframe |

The 15-minute clock does not create a new thread. The 30-second scheduler checks
whether the closed-candle clock is due and performs no extra market read when it
is not due.

### 7.3 Network and transaction boundary

Production sequence must preserve:

~~~text
short PG selection
-> close transaction
-> timeout-bounded exchange/public reads
-> short PG fact projection
-> short PG lifecycle evaluation
-> close transaction
-> at most one durable exchange command dispatch
-> short PG outcome projection
~~~

No SQLAlchemy connection or transaction may remain open while waiting for:

- exchange open orders;
- exchange fills;
- exchange position rows;
- public candles;
- command placement;
- command cancellation.

## 8. Data Ownership And Schema Design

### 8.1 Static Ticket exit reference snapshot

Migration 139 adds these columns to brc_ticket_exit_policy_current:

| Column | Rule |
| --- | --- |
| exit_reference_schema_version | required for versioned active policies |
| exit_reference_snapshot | typed immutable JSONB |
| exit_reference_hash | canonical SHA-256 |
| exit_reference_bound_at_ms | bind timestamp |
| terminal_at_ms | null until current position becomes terminal |

No new current-state table is introduced.

### 8.2 Typed reference model

The proposed domain model is:

~~~text
TicketExitReferenceSnapshot
  schema_version
  ticket_id
  signal_event_id
  strategy_group_id
  strategy_version
  event_spec_id
  event_spec_version
  exchange_instrument_id
  side
  values[]

TicketExitReferenceValue
  reference_key
  decimal_value
  source_kind
  source_ref
~~~

For the current SOR-LONG policy:

~~~text
reference_key = opening_range_high
decimal_value = signal_payload.signal_summary.evidence_payload.opening_range_high
source_kind = bound_live_signal_evidence
source_ref = exact signal_event_id
~~~

### 8.3 Binding time

Reference binding occurs during Action-Time Ticket exit-policy projection
initialization, before FinalGate can authorize real submit.

Binding must prove:

1. Ticket signal_event_id exists and is exact;
2. signal StrategyGroup, strategy version, Event Spec, version, side, symbol,
   instrument and lane identity match the Ticket;
3. every invalidation reference_key required by the policy exists;
4. every value is finite Decimal and positive when it represents a price;
5. canonical hash matches the persisted snapshot;
6. repeating the same binding is idempotent;
7. a different value or source for the same Ticket hard-stops.

Missing static exit references become an action-time execution-gate blocker.
They cannot be deferred until after the position is open.

### 8.4 Dynamic market fact ownership

brc_runtime_fact_snapshots with fact_surface=ticket_exit_market owns only:

- Ticket and instrument identity;
- timeframe;
- closed-candle watermark;
- bounded candle window;
- final/closed status;
- observed and valid-until timestamps.

It does not own static opening-range references, entry fill, fees, current
position quantity, active stop identity or exchange-command results.

### 8.5 FINAL_EXIT role

Migration 139 expands exact role constraints to include FINAL_EXIT in:

- durable Ticket-bound exchange commands;
- Ticket-bound protection/final-exit order projection;
- fill projection and lifecycle events.

FINAL_EXIT rules:

- command kind: place_order;
- order type: market for the current Binance USD-M implementation;
- gateway side: exact close side;
- reduce intent: reduce_position;
- position side: exact Ticket bucket;
- amount: current reconciled remaining position quantity;
- market fallback concept: not applicable because the decision itself is an
  explicit final market exit;
- parent: active Runner protection order;
- deterministic client order id;
- no leverage or sizing mutation.

FINAL_EXIT is not a new submit authority. It is an explicit role inside the
existing durable lifecycle writer.

### 8.6 Due-scope index

Migration 139 may add one partial index if the current query plan requires it:

~~~text
brc_ticket_exit_policy_current
  state
  next_evaluation_not_before_ms
  updated_at_ms
~~~

The index is accepted only when EXPLAIN on production-shaped data proves a
bounded due-scope selection benefit.

## 9. TP1 Completion State Machine

### 9.1 One completion reducer

One shared pure reducer becomes the only authority for TP1 completion:

~~~text
target_qty
+ tolerance_qty
+ all distinct TP1 fill events across all generations
+ current position quantity
+ order terminal states
-> unfilled | partial_open | partial_cancelled | complete | contradictory
~~~

Fill projector, protection reconciler and exit-policy service must consume this
same result. The reconciler must not treat the existence of any TP1 fill as
equivalent to complete TP1.

### 9.2 Cumulative fill identity

TP1 fill accumulation includes all Ticket-bound TP1 generations and recognizes:

- exchange_trade_id when present;
- actual exchange order id;
- conditional parent exchange order id when relevant;
- deterministic fallback fill identity;
- duplicate/restart idempotency.

It must never reset cumulative quantity when a replacement TP1 receives a new
exchange order id.

### 9.3 Partial fill with live remainder

When a TP1 order is partially filled and remains open:

1. project the fill delta;
2. update cumulative target progress;
3. update remaining position quantity from exchange truth;
4. resize SL/RUNNER_SL to exact remaining position quantity;
5. keep the existing TP1 remainder live;
6. do not improve stop until quantity synchronization is confirmed.

### 9.4 Partial fill during cancel/reprice

When cancellation is confirmed after a partial fill:

1. recompute cumulative TP1 fill across all generations;
2. resize protection to current remaining position first;
3. compute residual_tp1_qty = frozen_target_qty - cumulative_filled_qty;
4. round residual quantity down to venue step;
5. if residual quantity is within the configured completion tolerance, classify
   TP1 complete;
6. otherwise submit only the residual quantity at the frozen policy TP1 price;
7. keep Runner target quantity equal to entry quantity minus frozen TP1 target,
   not entry quantity minus the last order quantity.

No branch may return to a stable partial state with both:

- no live TP1 order;
- residual target quantity above tolerance.

### 9.5 TP1 complete

TP1 complete requires:

~~~text
cumulative_filled_qty + tolerance >= frozen_target_qty
AND remaining position agrees with frozen runner target within tolerance
AND active stop quantity is synchronized to remaining position
~~~

Only then may the immediate cost-adjusted Runner floor be applied.

## 10. Runner Stop State Machine

### 10.1 States

~~~text
execution_bound
-> tp1_unfilled
-> tp1_partial
-> tp1_complete
-> runner_floor_pending
-> runner_floor_place_pending
-> runner_floor_cancel_old_pending
-> runner_protected
-> runner_trailing
-> runner_close_pending
-> final_exit_detected
-> terminal
~~~

### 10.2 Immediate floor

The floor remains independent of public-candle availability.

After TP1 completion:

1. allocate entry fee to the remaining Runner quantity;
2. include conservative exit taker fee;
3. include configured slippage ticks;
4. round long floor upward and short floor downward;
5. require tick alignment;
6. require at least the configured minimum improvement.

### 10.3 Structural / ATR candidate

For the current SOR-LONG policy:

~~~text
candidate =
  lowest low of confirmed four-bar structural window
  - 0.5 * ATR(14)
~~~

The candidate uses only final closed 15m candles.

The effective proposed stop after TP1 is:

~~~text
long: max(structural_candidate, break_even_floor)
short: min(structural_candidate, break_even_floor)
~~~

### 10.4 Monotonic movement

The evaluator must return NOOP unless:

~~~text
long proposed_stop - current_stop >= minimum_ticks * price_tick
short current_stop - proposed_stop >= minimum_ticks * price_tick
~~~

No rounding, restart, stale fact, duplicate fact or reference change may move a
stop in the adverse direction.

### 10.5 Replacement order

For Binance USD-M hedge mode:

~~~text
prepare new reduce-intent RUNNER_SL
-> exchange confirms new stop
-> reconciliation proves exact positionSide and close side
-> prepare cancel exact old stop
-> exchange confirms cancellation
-> activate new generation in PG
~~~

If new stop submission is unknown, do not cancel the old stop.

If old stop cancellation is unknown, keep both identities visible, freeze new
mutation for the exact netting domain and reconcile.

## 11. Strategy Final Exit

### 11.1 Trigger conditions

A FINAL_EXIT decision may be created only from:

- a configured invalidation rule hit on a final closed candle;
- a configured time stop reached on a final closed candle;
- a future versioned exit rule explicitly allowed by the Ticket policy.

It may not be created by monitor wording, stale facts, replay, synthetic facts,
manual evidence files or an unbound strategy reference.

### 11.2 Order sequence

The safe default is:

~~~text
keep existing SL / Runner protection live
-> prepare reduce-only FINAL_EXIT market command
-> dispatch with deterministic client order id
-> reconcile accepted / rejected / unknown result
-> project exact FINAL_EXIT fill
-> prove position flat
-> cancel remaining PG-linked SL / TP1 / RUNNER_SL orders
-> terminalize lifecycle and exit-policy projection
~~~

Protection is not cancelled before the final market exit is confirmed.

### 11.3 Unknown result

If the FINAL_EXIT write result is unknown:

1. stop all further exit mutation for the exact netting domain;
2. query the exact command-required view by client order id;
3. reconcile submitted, absent or contradictory truth;
4. never submit a second final exit while the first outcome is unknown.

### 11.4 Fill projection

FINAL_EXIT fills must be projected from:

- command id;
- local order id;
- client order id;
- exchange order id;
- Ticket id;
- exact account/instrument/position bucket;
- fill trade identities.

Normal FINAL_EXIT must never be labelled EXTERNAL_CLOSE.

EXTERNAL_CLOSE remains reserved for a genuinely exchange-side close not owned by
any Ticket-bound command or protection order.

## 12. Terminal Projection

### 12.1 Terminalization rule

When authoritative exchange and reconciliation truth prove the position flat:

~~~text
remaining_position_qty = 0
tp1 state = preserved terminal truth
active_runner_order_id = null
active_runner_generation = null
active_runner_stop = null
pending_runner_order_id = null
pending_generation = null
replaced_runner_order_id = null
state = terminal
first_blocker = null
terminal_at_ms = current time
~~~

### 12.2 Closed-history compatibility

Historical v1 projections remain audit provenance. They may be terminalized by
a bounded PG repair only when:

- the lifecycle is closed;
- post-submit closure is closed;
- exchange/account truth is flat or current closure evidence is exact;
- no prepared, dispatching or unknown command exists.

The repair is non-destructive and idempotent. It does not rewrite Ticket,
policy, fill, order or review history.

## 13. Failure Matrix

| Failure | Required behavior | Exchange effect |
| --- | --- | --- |
| Static exit reference missing before submit | block Ticket live-submit readiness | none |
| Static reference hash contradiction | hard stop exact Ticket | none |
| Closed-candle source unavailable | keep current protection, retry after 30 seconds | none |
| Candle stale or non-final | ignore and retain current stop | none |
| TP1 partial fill | resize protection before any stop improvement | one durable replacement when required |
| TP1 cancel result unknown | do not place residual TP1 | none after unknown |
| Residual TP1 below tolerance | classify complete and proceed to floor | no TP1 replacement |
| Runner place unknown | keep old stop, freeze further mutation | one unknown write only |
| Runner old-stop cancel unknown | retain both identities and reconcile | no additional write |
| FINAL_EXIT rejected | retain protection and record blocker | one rejected write |
| FINAL_EXIT outcome unknown | reconcile by client order id; no duplicate | one unknown write only |
| Position flat with live protection | durable orphan cleanup | bounded exact cancels |
| Lifecycle closed but projection nonterminal | PG-only terminal projection repair | none |
| Unknown exchange-only order | freeze exact scope, do not cancel or adopt | none |

## 14. Cadence And Performance Budget

### 14.1 No-active lifecycle

Required behavior:

- bounded PG scope selection only;
- zero gateway binding when no scope or pending command exists;
- zero exchange requests;
- zero public candle requests;
- zero JSON/Markdown files;
- process exits well inside the 28-second deadline.

### 14.2 Active lifecycle, market fact not due

Required additional fact cost:

- zero closed-candle requests;
- one PG due check;
- normal exchange snapshot cadence remains unchanged.

### 14.3 Active lifecycle, market fact due

Budget:

| Resource | Limit |
| --- | --- |
| Public candle request | one per unique instrument + venue + timeframe group |
| Candle timeout | 5 seconds |
| Exchange snapshot timeout | existing 8 seconds |
| Global lifecycle deadline | existing 28 seconds |
| Mutation commands per invocation | at most one |
| Active lifecycle scopes per invocation | bounded by current CLI limit |
| JSON/Markdown file growth | zero |

### 14.4 PG growth

For the current 15m and 96-bar time-stop policy:

- maximum about 96 due fact rows per Ticket before time stop, excluding
  idempotent retries;
- one current projection row per Ticket;
- one command row per actual mutation intent;
- one fill event per distinct exchange trade identity;
- no per-tick trace rows when no watermark or state changes.

### 14.5 Disk and retention

Production cadence writes only PG rows and stdout/journal.

No report directories, dynamic evidence JSON, Markdown status files or JSONL
sidecars are introduced.

Historical cleanup remains a manual, Owner-scoped, retention-bounded ops task.

## 15. Owner And Monitor Semantics

### 15.1 Healthy states

Owner-facing product state remains:

| Internal condition | Owner wording |
| --- | --- |
| protected position before TP1 | 持仓处理中，保护正常 |
| TP1 partial and protection resizing | 系统处理中，保护正常 |
| TP1 complete and floor moving | 系统处理中，保护正常 |
| Runner active | 持仓处理中，保护正常 |
| waiting for next 15m closed candle | 持仓处理中，保护正常 |
| final exit and cleanup | 系统处理中 |
| lifecycle terminal | 已完成 |

### 15.2 Abnormal states

Owner intervention is not required for ordinary retries.

Notify or request intervention only for:

- repeated command rejection after bounded retry policy;
- unresolved unknown exchange outcome;
- missing active protection;
- contradictory static reference truth;
- position/order ownership ambiguity;
- cleanup failure leaving live protection after flat position.

## 16. Security And Authority Boundary

This design preserves:

~~~text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade.
Runtime Safety State answers live-submit safety.
Review updates strategy governance.
~~~

This design does not authorize:

- new entry;
- new StrategyGroup or symbol scope;
- leverage, notional or exposure expansion;
- FinalGate bypass;
- Operation Layer bypass;
- exchange write from facts or replay;
- credential mutation;
- withdrawal or transfer;
- manual file-based runtime authority;
- duplicate final exit;
- protection cancellation before replacement or flat confirmation.

## 17. Test And Certification Strategy

### 17.1 Pure domain tests

- long and short break-even floor;
- tick rounding and minimum improvement;
- static reference hash and identity;
- TP1 cumulative reducer across generations;
- partial, completion tolerance and contradiction;
- structural/ATR candidate;
- invalidation and time stop;
- monotonic stop negative cases.

### 17.2 PostgreSQL component tests

- bind references from exact signal event;
- reject missing/wrong StrategyGroup, Event Spec, side, symbol and instrument;
- due watermark idempotency;
- no duplicate fact rows;
- fill accumulation across TP1 generations;
- partial cancel/reprice residual order;
- Runner place-before-cancel sequence;
- FINAL_EXIT command/order/fill lineage;
- terminal current projection.

### 17.3 Worker and gateway tests

- TP1 remains LIMIT GTC;
- FINAL_EXIT is exact reduce intent;
- Binance hedge mode preserves positionSide;
- no leverage on exit commands;
- unknown result creates domain hold;
- dispatch timeout is bounded;
- no network inside PG transaction.

### 17.4 Full-chain scenarios

| Scenario | Required terminal result |
| --- | --- |
| TP1 never fills, SL fills | closed by SL |
| TP1 fills completely, floor then SL fills | closed by RUNNER_SL |
| TP1 partial then completes | floor and Runner activate once |
| TP1 cancel/reprice partial race | residual TP1 only, no wedge |
| structural stop improves twice | two monotonic generations |
| invalidation fires | FINAL_EXIT exact lineage |
| 96-bar time stop fires | FINAL_EXIT exact lineage |
| Runner place unknown | old protection retained and scope frozen |
| FINAL_EXIT unknown then found | one close only |
| final flat with live orders | exact cleanup then terminal |
| restart at every command state | idempotent continuation |

### 17.5 Production-shaped negative proof

Acceptance begins from the exact producer boundary:

~~~text
bound signal payload
-> static exit reference snapshot
-> closed candle source
-> PG exit fact
-> policy decision
-> durable command
-> worker result
-> fill/reconciliation
-> terminal projection
~~~

Tests may not inject downstream-ready reference dictionaries while bypassing the
actual signal-to-reference binder.

## 18. Deployment And Rollback Design

### 18.1 Deployment prerequisites

- Owner confirms this design and implementation plan;
- no unresolved unknown exchange command;
- active positions, if any, have exact exchange-native protection;
- migration 139 passes disposable-PostgreSQL upgrade;
- production file-I/O audit reports performance_risk.status=clear;
- focused and full regression suites pass;
- release manifest and lifecycle capability bind the exact target HEAD.

### 18.2 Deployment sequence

~~~text
quiesce watcher and lifecycle mutation units
-> prove current active position/protection/command truth
-> deploy exact release and migration 139
-> bind/backfill exact exit references for any active versioned Ticket
-> run no-write reference and due-scope probe
-> restore lifecycle timer
-> run no-active or active-protected canary
-> restore watcher
-> verify PG, journal and Owner read models
~~~

### 18.3 Rollback

Rollback must preserve active exchange protection.

Safe rollback sequence:

1. stop new lifecycle mutation claims;
2. reconcile every dispatching or unknown command;
3. prove current SL/RUNNER_SL protection;
4. switch code to the predecessor release;
5. leave additive migration 139 in place unless downgrade is proven safe;
6. mark new fact/FINAL_EXIT capability disabled for new decisions;
7. continue protection reconciliation and cleanup through the predecessor path;
8. never delete new rows during rollback.

If a FINAL_EXIT or Runner command outcome is unknown, rollback stops until
exchange truth is resolved.

## 19. Live Enablement Chain Position

~~~text
chain_position: action_time_boundary
strategy_group_id: SOR-001
symbol: current SOR-LONG candidate symbol
stage: ticket_bound_post_submit_lifecycle
first_blocker: event_execution_capability_not_certified
evidence: production scheduler never creates ticket_exit_market facts; static reference handoff and final-exit lineage are incomplete
next_action: implement and certify the single-scheduler Ticket exit Runner closure defined by this document
stop_condition: one production-shaped versioned Ticket can progress from TP1 through floor, due Runner fact, exact mutation, final fill, cleanup and terminal PG state with no duplicate or authority bypass
owner_action_required: true for confirmation of this design only; no new strategy, capital or live-profile decision is requested
authority_boundary: design and future bounded implementation only; no FinalGate bypass, Operation Layer bypass, forced order, profile expansion, sizing change, withdrawal, transfer or credential mutation
signal_event_id: none for implementation acceptance
promotion_candidate_id: none for implementation acceptance
action_time_lane_input_id: none for implementation acceptance
ticket_id: synthetic/local only until a natural production Ticket exists
~~~

## 20. Owner Decisions Requested

Owner confirmation of this document approves these engineering decisions:

1. **Runner remains scheduler-driven and is not implemented as an independent
   thread or daemon.**
2. **The existing 30-second lifecycle oneshot receives a due 15m fact stage.**
3. **Static invalidation references are frozen from exact Ticket-bound signal
   lineage before real submit.**
4. **TP1 partial cancel/reprice preserves the approved total target by submitting
   only the residual target quantity.**
5. **FINAL_EXIT becomes an explicit durable command/order role.**
6. **Missing static exit references fail closed before live submit.**
7. **Migration 139 is additive and historical rows are terminalized only through
   exact, non-destructive reconciliation evidence.**

Confirmation does not change:

- current StrategyGroup scope;
- current policy values;
- TP1 ratio;
- Runner formula;
- capital, leverage, notional or exposure limits;
- real-submit authority boundaries.

## 21. Acceptance Definition

The design is implemented only when all of the following are true:

1. Tokyo production cadence can generate a fresh ticket_exit_market fact when a
   versioned active Ticket reaches a due closed candle.
2. The fact consumer loads immutable reference truth from the Ticket exit
   reference snapshot, not from the dynamic candle fact.
3. TP1 cumulative completion is identical in fill projector, reconciler and
   policy service.
4. A cancel/reprice partial fill cannot leave residual target without a live TP1.
5. A Runner stop is always placed and confirmed before the old stop is cancelled.
6. Strategy invalidation/time-stop close uses FINAL_EXIT and never normal
   EXTERNAL_CLOSE inference.
7. Position-flat truth terminalizes exit-policy current state.
8. Restart and unknown outcomes produce no duplicate TP1, Runner or final exit.
9. No-signal and no-active ticks create zero JSON/Markdown files.
10. Production file-I/O and performance audits remain clear.
11. No Owner manual operation is required during normal in-boundary lifecycle.

Until Owner confirms this document, implementation and deployment remain
unauthorized by this design.
