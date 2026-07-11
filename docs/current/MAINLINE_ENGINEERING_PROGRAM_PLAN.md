---
title: MAINLINE_ENGINEERING_PROGRAM_PLAN
status: CURRENT_PROGRAM_PLAN
authority: docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md
last_verified: 2026-07-11
---

# Mainline Engineering Program Plan

## Purpose

This document is the current program-level execution map after the PG-backed
pre-trade runtime and ticket-bound protection work.

It answers:

```text
Which large engineering programs exist?
Which design documents define each program?
What priority order should implementation follow?
What acceptance proves each program is actually closed?
```

It does not authorize live profile expansion, order sizing expansion,
FinalGate bypass, Operation Layer bypass, exchange writes outside the official
path, withdrawal, transfer, credential mutation, or runtime decisions from
repo MD/JSON/output/report files.

## Known Objective Facts

| Fact | Current evidence |
| --- | --- |
| **Current Tokyo release line** | Tokyo follows focused branch `codex/p0-real-signal-ticket-closure`; the immutable deployed head is recorded by `.brc-release-manifest.json`; PG migration is `112` |
| **PG current state is the runtime source** | `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`, `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| **Repo/output/report files are not runtime authority** | `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` |
| **Five StrategyGroups are active WIP** | `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`, PG candidate scope seed |
| **Multi-symbol and side-specific action-time path exists** | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| **Ticket identity and TP1 are PG-backed** | `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` |
| **Initial order lifecycle/protection PG objects exist** | `brc_ticket_bound_*` tables and current ticket-bound materializers |
| **Runner dynamic management is code-covered and deployed as lifecycle repair** | `runner_mutation_command`, `runner_mutation_executor`, `runner_protection_adjuster`, lifecycle tests, and the current Tokyo release cover TP1 filled -> RUNNER_SL submit -> old SL cleanup -> runner proof through official-path records |
| **Exchange protection reconciliation is code-covered and deployed as readonly comparison logic** | `protection_reconciler` compares PG protection rows with caller-provided exchange snapshots, including missing order, side mismatch, qty mismatch, orphan reduce-only order, TP1-fill runner gap, and flat-position live protection |
| **First tick and recovery-command defaults are deployed** | The current Tokyo release includes `brc_ticket_bound_reconciliation_ticks`, `brc_ticket_bound_scope_freezes`, first post-submit tick selection, TP1 degraded recovery, max 3 recovery attempts, and scope freeze records at `strategy_group_id + symbol + side` |
| **Scope freeze pre-submit hard blocker is deployed** | `381aed34` blocks active real-risk freezes across promotion, lane, ticket, Runtime Safety State, FinalGate preflight, Operation Layer handoff, submit-mode decision, and protected submit; stale/no-risk freezes resolve through reconciliation/cleanup |
| **Typed pricing / sizing / reservation closure is implemented** | Action-time facts now own a side-aware executable price, Decimal normalized quantity, and positive risk-at-stop reservation; promotion, Ticket, and protected submit reuse the same lineage rather than recomputing loose dictionary values |
| **Atomic Ticket sequence is implemented** | Action-time facts, lightweight readiness, promotion, reservation, lane, and Ticket run under one savepoint and roll back together when any blocker or TTL boundary fails |
| **Production-shaped certification exists** | Five StrategyGroups, 22 candidate scopes, and six current Event Specs have positive, missing, stale, malformed, conflict, and production-shaped raw-source chain coverage without exchange write |
| **Production temporal-truth acceptance found a second defect class** | A repeated watcher observation of the same closed-candle signal preserved the same `signal_event_id`; its prior promotion/lane identity was terminal, but sequence aggregation incorrectly converted child `arbitration_lost` rows into successful process outcomes and hid the parent terminal blocker |
| **Temporal-truth correction is implemented on the focused branch** | Duplicate signal identity now preserves the first event row without mutating fact lineage or TTL; a failed parent promotion forces every affected lane outcome to remain `business_blocked`; the full suite passes with `2720 passed, 1 skipped` |
| **Test escape is proven** | Unit/full-chain fixtures inject `last_price`, `mark_price`, or `entry_price` directly, while production fact materialization does not guarantee the same typed field; downstream-complete dictionary fixtures therefore bypassed the missing producer handoff |
| **Advanced trading quality / capital allocation remains future work** | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md`; portfolio sleeve allocation, cluster exposure, cooldown, and drawdown controls remain above the per-ticket safety layer |

## Program Map

| Program | Priority | Goal | Primary design docs | Main acceptance |
| --- | --- | --- | --- | --- |
| **P0-RT Real Signal -> Ticket Closure** | P0 | Unify action-time pricing, normalized sizing, positive stop-risk reservation, and Ticket materialization inside freshness bounds | `PRE_TRADE_RUNTIME_CONTRACT.md`, `TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md`, this program plan | An eligible production-shaped signal creates one PG Ticket and Runtime Safety State, or stops before lane readiness at one producer-owned blocker |
| **P0-PC Production-Shaped Chain Certification** | P0 | Replace privileged downstream dictionary fixtures with raw-source-to-PG certification for all current Event Specs | `PRE_TRADE_RUNTIME_CONTRACT.md`, `RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`, `BLOCKER_CLASSIFICATION_CONTRACT.md` | Six Event Specs pass positive and negative raw-source chain cases; current projections agree on the same blocker and watermark |
| **P0-0 Operation Layer / Exchange Capability Boundary** | P0 | Confirm the real official-path exchange capabilities that lifecycle, runner, recovery, and reconciliation may rely on | `TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | ENTRY, SL, TP1, reduce-only, query open orders/fills/position, cancel, idempotent client order id, and runner SL capability are explicitly mapped to supported / unsupported / recovery-required |
| **P0-1 Ticket-Bound Lifecycle Safety Core** | P0 | Keep lifecycle state machine, hard invariants, sequential submit recovery, runner mutation, exchange protection reconciliation, and closure under one model | `TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md`, `POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md` | A submitted ticket can prove ENTRY, SL, TP1, RUNNER_SL, final exit, reconciliation, settlement, and review, or stop at one exact lifecycle hard blocker |
| **P0-2 Full Chain Simulation Harness** | P0 | Verify the lifecycle model with constructed raw inputs, two golden paths, and a failure matrix without real exchange writes | `PRE_TRADE_RUNTIME_CONTRACT.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | AVAX short and CPM long golden paths plus failure matrix prove lifecycle correctness; broader active event specs remain impact coverage |
| **P0-C Production Lifecycle Wiring** | P0 | Wire existing lifecycle, first reconciliation tick, recovery, runner mutation, reconciler, and cleanup services into production cadence without adding a second lifecycle path | `TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md`, `P0_C_PRODUCTION_LIFECYCLE_SCHEDULER_AND_SNAPSHOT_SOURCE_DESIGN.md`, `POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md` | ENTRY, SL, TP1, RUNNER_SL, final exit, first tick, recovery, cleanup, and reconciliation are event/startup/periodic wired and stop at exact lifecycle blockers |
| **P0-E Scope Freeze Pre-Submit Gate** | P0 | Turn active real-risk scope freezes into hard blockers before any new promotion, lane, ticket, Runtime Safety State, FinalGate preflight, or protected submit can proceed | `P0_CAPITAL_SAFETY_CLOSURE_DESIGN.md`, `POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md`, `BLOCKER_CLASSIFICATION_CONTRACT.md`, `PRE_TRADE_RUNTIME_CONTRACT.md` | An active real-risk `brc_ticket_bound_scope_freezes` row blocks the exact `strategy_group_id + symbol + side`; stale no-risk residue becomes cleanup/outcome and does not block |
| **P0-D Live Outcome Ledger** | P0 | Turn real tickets and orders into structured strategy-learning rows without becoming submit authority | `P0_CAPITAL_SAFETY_CLOSURE_DESIGN.md`, `LIVE_OUTCOME_LEDGER_CONTRACT.md`, `STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md` | Every real ticket can bind entry, stop, TP1, runner, final exit, fees, funding, PnL, MAE/MFE, R multiple, lifecycle defects, and review decision |
| **P0-F Continuous Reconciliation Tick** | P0 | Continue exchange-truth reconciliation after the first post-submit tick until lifecycle closure, exact recovery, or hard stop | `P0_CAPITAL_SAFETY_CLOSURE_DESIGN.md`, `POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md`, `P0_C_PRODUCTION_LIFECYCLE_SCHEDULER_AND_SNAPSHOT_SOURCE_DESIGN.md` | Scheduled/event-driven ticks refresh open orders, fills, positions, protection refs, runner state, and final exit without creating report files or duplicate lifecycle actions |
| **P1 Risk Reservation v0** | P1 | Require ticket-level stop-risk estimate and budget reservation before FinalGate-ready state | `TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md`, `RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | Consumer calculation is deployed; closure now requires RT-1 to prove the production price/quantity producer chain and a positive reservation before Ticket creation |
| **P1-C Owner Explanation Read Model** | P1 | Make no-trade, signal, ticket, submit, runner, and closure states human-readable | `OWNER_EXPLANATION_READ_MODEL_CONTRACT.md`, `RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE.md` | Owner can see whether the system is waiting, processing, blocked, protected, or closed without decoding internal terms |
| **P1-D Performance And Retention Control** | P1 | Keep no-signal ticks, monitor runs, PG rows, logs, and reports bounded | `SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md`, `PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` | No recurring report growth; no restart storm; PG/file-authority validators remain clear |
| **P2-E Advanced Capital Risk Allocation** | P2 | Allocate capital by portfolio exposure, StrategyGroup sleeve, symbol/side cap, cluster exposure, cooldown, and drawdown state | `TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md`, `RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | Multi-strategy / multi-symbol allocation can scale or pause exposure without changing per-ticket safety facts |
| **P2-F Frontend Read Model Integration** | P2 | Build frontend against backend explanation/read models, not raw PG internals | `OWNER_EXPLANATION_READ_MODEL_CONTRACT.md`, frontend `OWNER_EXPLANATION_READ_MODEL_FRONTEND_CONTRACT.md` | UI shows runtime health, signal progress, account state, ticket status, and why-no-trade from backend read models |

## Priority Order

| Order | Program | Reason |
| --- | --- | --- |
| 1 | **P0-RT Real Signal -> Ticket Closure** | Natural production signals have already proven that Ticket pricing/risk inputs are the first real blocker |
| 2 | **P0-PC Production-Shaped Chain Certification** | The same fixture escape can recur at FinalGate, Operation Layer, protection, and reconciliation unless producer-to-consumer proof becomes a release gate |
| 3 | **P0-0 Operation Layer / Exchange Capability Audit** | Lifecycle and runner plans must remain grounded in official gateway capabilities |
| 4 | **P0-1 Ticket-Bound Lifecycle Safety Core** | State machine, invariants, and failure states define downstream behavior after Ticket creation |
| 5 | **P0-2 Full Chain Simulation Harness** | The harness must be upgraded from downstream-complete fixtures to production-shaped producer-chain proof |
| 6 | **P0-C Production Lifecycle Wiring** | Post-entry protection and recovery remain the highest funds-safety risks after Ticket closure |
| 7 | **P0-E Scope Freeze Pre-Submit Gate** | Current real-risk scopes must block duplicate or conflicting progression |
| 8 | **P0-D Live Outcome Ledger** | Real results must become structured learning data |
| 9 | **P0-F Continuous Reconciliation Tick** | Reconciliation must continue until closure, recovery, or hard stop |
| 10 | **P1-C Owner Explanation Read Model** | Owner surfaces must explain persisted blockers without decoding internals |
| 11 | **P1-D Performance And Retention Control** | Continuous runtime must remain bounded |
| 12 | **P2-F Frontend Read Model Integration** | Frontend follows stable backend read models |
| 13 | **P2-E Advanced Capital Risk Allocation** | Portfolio allocation scales only after per-ticket mechanics and real outcomes are hard |

## Current Next Execution Order

This is the authoritative remaining sequence for the focused
`codex/p0-real-signal-ticket-closure` release line.
It supersedes ad hoc task ordering in chat summaries.

| Order | Next work | Priority | Acceptance |
| --- | --- | --- | --- |
| 1 | **RT-5 Temporal Truth Postdeploy Acceptance** | P0 | Repeated same-candle input cannot mutate the original signal event; parent terminal blocker remains visible per lane; services stay healthy and no exchange write occurs |
| 2 | **Production lifecycle wiring and continuous reconciliation** | P0 | Non-market-dependent post-Ticket lifecycle work continues through protection, scheduled reconciliation, deterministic recovery, settlement, and review |
| 3 | **RT-4 Next-Distinct-Signal Acceptance** | P0 | The next distinct eligible `signal_event_id` creates one Ticket and Runtime Safety State or stops at one genuine current safety/account/position/protection blocker; it preempts lower work when it arrives |
| 4 | **Live Outcome validation** | P0/P1 | The first real ticket produces one structured outcome or one exact hard-blocked outcome row |
| 5 | **Owner Explanation, frontend, and capital allocation** | P1/P2 | Product surfaces and portfolio allocation build on stable backend truth after the first real lifecycle outcome |

## P0-RT Real Signal -> Ticket Closure

### Root Cause

The observed failure is not merely a missing dictionary key. The exact chain is:

```text
production source values
-> action-time fact materializer does not persist canonical entry reference
-> promotion computes requested_risk_at_stop = 0
-> zero risk is not classified as a blocker
-> real-submit lane is created
-> Ticket risk reservation rejects missing price / quantity / risk
-> action-time sequence fails and lane expires
-> later no-signal projection hides the engineering blocker
```

Production acceptance then exposed a second, temporal state-machine chain:

```text
same closed candle is observed again
-> stable signal_event_id conflicts with the existing event
-> writer mutates the existing event's fact lineage / timing fields
-> prior promotion and lane identity is terminal and cannot reopen
-> promotion returns one parent terminal blocker
-> per-candidate arbitration_lost rows are projected as success
-> PG process outcome says processing instead of preserving the blocker
```

The systemic issue is broader than dictionaries: release tests did not exercise
**the same identity across repeated production cadence**, and aggregation tests
did not require **parent failure conservation**.

### Task Packages

| Task | Scope | Acceptance | Stop condition |
| --- | --- | --- | --- |
| **RT-1 Typed Action-Time Pricing And Sizing** | Define one typed entry reference with source, side, observed time, validity, and instrument; derive Decimal quantity from PG policy and quantize through PG exchange-instrument rules | Ticket, risk reservation, and protected submit consume the same normalized quantity and price lineage; no component recomputes identity from loose dictionaries | Stop if this requires changing Owner notional, leverage, loss unit, symbol/side scope, or execution order type |
| **RT-2 Atomic Ticket Materialization And TTL** | Collapse action-time fact refresh, lightweight readiness refresh, sizing/risk reservation, and Ticket creation into one bounded application service/transaction; move Candidate Pool, Daily Table, Goal Status, and Owner snapshots after the critical path | Critical path completes before the shortest trusted fact expiry; timeouts fail with lane-scoped PG process outcomes; no JSON/MD output | Stop on multiple open real-submit lanes, stale facts, missing account facts, or PG transaction ambiguity |
| **RT-3 Blocker Truth And Monitor Closure** | Reuse PG runtime process outcomes and state events with signal/lane scope; project unresolved engineering blocker into Readiness, Tradeability, Goal Status, and Monitor | Every affected signal/lane has one first blocker and watermark across all views; no-signal ticks do not erase unresolved repair state; fresh signals may re-certify and clear it; business blockers do not mark watcher infrastructure failed | Stop when a newer successful certification for the same capability clears the blocker |
| **RT-4 Natural-Signal Acceptance** | Observe the next eligible production signal after deployment | Signal creates Ticket and Runtime Safety State or stops at a genuine action-time safety/account/position/protection blocker | Do not bypass FinalGate, Operation Layer, protection, or exchange-write authority |
| **RT-5 Temporal Identity And Outcome Truth** | Make signal-event identity immutable across repeated watcher ticks and conserve parent blockers across per-candidate outcome aggregation | Same closed-candle input is idempotent; terminal identity never appears as successful processing; every affected lane persists the exact parent blocker | Stop on any duplicate-submit ambiguity or any need to reopen a terminal real-submit identity |

### RT-5 Cadence And Performance Boundary

| Dimension | Required behavior |
| --- | --- |
| **Cadence** | Runs only for watcher summaries that contain a `would_enter` signal and for the bounded Action-Time sequence |
| **File writes** | **0** JSON/MD files for no-signal and duplicate-signal ticks |
| **PG writes** | First distinct signal inserts one event; a duplicate event inserts **0** signal rows and performs one bounded current-state read; process outcomes remain bounded to affected lanes |
| **CPU** | Stable ID hashing and per-candidate aggregation are linear in the bounded candidate set; no broad report builder runs in the critical transaction |
| **Timeout** | The existing server Action-Time sequence remains bounded by the **45-second** subprocess timeout and the shortest trusted-fact TTL |
| **Retention** | The original signal event and lifecycle transitions remain PG provenance; no per-run sidecar file is created |

## P0-PC Production-Shaped Chain Certification

### Certification Rule

Tests must start before the field producer boundary. A fixture may model raw
venue/account/strategy observations, but it may not pre-fill the exact
downstream dictionary keys whose production materialization is under test.

### Mandatory Matrix

| Dimension | Required cases |
| --- | --- |
| **Event Specs** | CPM-LONG, MPG-LONG, MI-LONG, SOR-LONG, SOR-SHORT, BRF2-SHORT |
| **Price facts** | valid best-side reference, stale, missing, malformed, cross-source conflict |
| **Sizing facts** | valid precision, below minimum quantity, step-size rounding, invalid notional, missing instrument mapping |
| **Protection facts** | valid stop direction, missing stop, wrong-side stop, expired protection, missing TP1 |
| **Account facts** | fresh safe account, stale, open-order conflict, active-position conflict, unavailable private facts |
| **Projection truth** | success, computed-not-satisfied, engineering blocker, runtime safety blocker, later no-signal tick |
| **Cadence and identity** | first observation, repeated same-candle observation, post-expiry observation, next distinct candle, terminal prior progression |
| **Outcome aggregation** | one parent success with one arbitration loser, parent business blocker, parent retryable failure, candidate-specific blocker, multi-lane mixed result |

### Release Gate

Completion requires all of the following:

1. No consumer-required runtime field exists only in test fixtures.
2. Every field has typed producer ownership, PG lineage, observed time, and validity.
3. A missing field blocks at the earliest responsible stage, before a later consumer fails.
4. Six Event Specs reach Ticket and Runtime Safety State in non-exchange-write certification.
5. Candidate Pool, Readiness, Tradeability, Goal Status, Server Monitor, and process outcomes agree.
6. No-signal cadence writes zero JSON/MD files; heavy work is event-triggered and timeout-bounded.
7. Postdeploy acceptance verifies PG lineage, not only service health and test-suite success.
8. Repeating an identical event identity cannot change its first fact reference,
   authority fields, observed time, expiry, or lifecycle state.
9. A parent-stage failure cannot be downgraded by child candidate rows; every
   affected lane must preserve the parent first blocker.

### Pre-Market Engineering Discovery Gate

This gate exists specifically so engineering blockers are found before a rare
market event reaches them.

| Gate | Required proof before release |
| --- | --- |
| **Producer ownership** | Every downstream-required value has one typed producer, one PG owner, one freshness rule, and no fixture-only alias |
| **Raw-source chain** | Tests start from venue/account/strategy source shape and traverse the same projectors used in production |
| **Temporal metamorphic replay** | The same input is run once, repeatedly, after expiry, and after a distinct event; state changes must match the declared state machine |
| **Parent-child truth conservation** | Parent failure, retryable failure, and hard stop can never become child success during fan-out/fan-in aggregation |
| **Fault injection by boundary** | Missing, stale, malformed, conflicting, timeout, rollback, duplicate, and terminal-identity cases are injected at every L2-L7 handoff |
| **Production-shaped postdeploy** | One no-exchange-write acceptance run verifies PG row counts, lineage, first blocker, service health, and zero recurring JSON/MD output |

This gate is a release constraint, not a one-time task. A new StrategyGroup,
instrument class, side, Event Spec, capital allocator, or lifecycle transition
must extend the same matrix before it can be called execution-capable.

## Program Details

### P0-0 Operation Layer / Exchange Capability Audit

#### Goal

Confirm the real official exchange capability boundary before extending
lifecycle automation:

```text
ENTRY submit
SL submit
TP1 submit
reduce-only support
query open orders
query fills
cancel order
modify order or cancel+new replacement
runner SL submit
position query
idempotent client order id
```

#### Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **Capability map exists** | Each capability is marked supported, unsupported, or recovery-required for the active exchange/profile |
| **No authority expansion** | Audit is readonly except explicitly authorized mock/local tests |
| **Lifecycle dependencies mapped** | Every lifecycle transition that needs exchange data or mutation names its official operation dependency |
| **Unsupported paths fail closed** | Missing amend/cancel/query support maps to lifecycle blocker or recovery path, not silent fallback |

#### Current Result

| Result | Evidence |
| --- | --- |
| **Audit complete and absorbed** | Capability boundary is reflected in `docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md` and `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md`; original audit packet is archived under `docs/archive/2026-07-09-docs-current-consolidation/OPERATION_LAYER_EXCHANGE_CAPABILITY_AUDIT.md` |
| **Gateway readiness method gap closed** | Runtime gateway readiness now requires lifecycle methods, not only `place_order` |
| **Recent fills wrapper added** | `ExchangeGateway.fetch_my_trades` is available as a read-only capability |
| **Remaining first blocker** | `action_time_fact_blocked_outcome_marks_watcher_failed`; the lifecycle path is deployed, but fact-blocked fresh signals must not terminate watcher health |
| **Orphan protection cleanup command** | Deployed through migration `098`, `orphan_protection_cleanup_command`, and focused tests |

### P0-1 Ticket-Bound Lifecycle Safety Core

#### Goal

Maintain one post-submit lifecycle safety core that covers:

```text
state machine and hard invariants
-> sequential ENTRY / SL / TP1 submit recovery
-> protection reconciliation against exchange truth
-> TP1 fill handling
-> official runner SL mutation
-> final exit / settlement / review closure
```

#### Current Progress

| Area | Current state |
| --- | --- |
| **State/failure vocabulary** | Documented in `TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md` |
| **Sequential submit failure classification** | Code-covered and deployed in lifecycle repair path |
| **Protection recovery command** | Code-covered through injected gateway; production scheduling remains explicit wiring work |
| **Protection reconciler** | Code-covered over caller-provided exchange snapshots |
| **Runner mutation command/executor** | Code-covered and deployed; official production scheduling/API activation remains controlled |
| **Ops health visibility** | Code-covered readonly lifecycle corruption / attention checks |

#### Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **Sequential failure classified and recoverable** | ENTRY reject/unknown/orphan/partial, SL failure, TP1 failure, and duplicate submit map to lifecycle states; missing SL/TP1 recovery can be executed locally through an injected gateway |
| **Protection reconciled** | PG SL/TP1/RUNNER_SL rows match exchange open orders, fills, position, and OrderLifecycle |
| **Runner mutation official** | Old SL cancel/replace and RUNNER_SL submit go through ticket-bound Operation Layer path |
| **No invented protection** | Proof rows cannot stand in for missing exchange truth |
| **Lifecycle closes cleanly** | Final exit, flat-position proof, reconciliation, settlement, and review are all bound before `lifecycle_closed` |
| **Ops health surfaces blockers** | Current lifecycle hard blockers appear in readonly health checks |

### P0-2 Full Chain Simulation Harness

#### Goal

Build a deterministic local harness that starts from constructed market/fact
inputs and verifies the current chain against the lifecycle state machine:

```text
candidate scope
-> runtime coverage
-> fact snapshot
-> live signal event
-> promotion candidate
-> action-time lane
-> Action-Time Ticket
-> Runtime Safety State
-> FinalGate preflight
-> Operation Layer handoff
-> protected submit attempt
-> mocked ENTRY / SL / TP1 exchange result
-> entry fill
-> exit protection set
-> TP1 fill
-> runner protection
-> final exit
-> reconciliation / settlement / live outcome / review proof
```

The harness must not become a five-strategy happy-path demonstration. Its
first acceptance shape is:

```text
2 golden paths
+ failure matrix
+ broader active-scope impact coverage
```

Golden paths:

| Path | Why it is first |
| --- | --- |
| **AVAX 1h short** | It matches recent real short signal behavior and exercises BRF/SOR short-side protection semantics |
| **CPM long** | It exercises the current long-only CPM path and prevents short-side fixes from biasing the harness |

#### Associated Design Docs

| Doc | Role |
| --- | --- |
| `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` | Defines candidate, promotion, lane, and ticket chain |
| `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | Defines post-submit lifecycle and protection states |
| `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` | Defines PG tables and constraints |

#### Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **Golden paths covered** | AVAX short and CPM long pass from constructed raw inputs to mocked lifecycle closure |
| **Failure matrix covered** | ENTRY accepted / SL failed, TP1 missing, TP1 filled / runner missing, runner submit failed, old SL cancel failed, PG protected / exchange missing, duplicate TP1 fill, and partial fill all stop at exact lifecycle states |
| **Active event specs impact-covered** | CPM long, MPG long, MI long, SOR long, SOR short, BRF2 short fixtures remain covered by lighter impact tests |
| **No exchange write** | Harness uses explicit mock official-path results |
| **No file authority** | Harness uses PG/in-memory typed fixtures, not repo/output/report JSON |
| **Ticket identity stable** | Each run records StrategyGroup, symbol, side, profile, policy versions, facts, and protection refs |
| **No lifecycle shortcut** | Harness assertions use lifecycle state machine and hard invariants, not raw success strings |

#### Current Result

| Result | Evidence |
| --- | --- |
| **P0-2 closed locally** | `tests/unit/test_action_time_full_chain_impact.py` covers 22 active scopes through mock real submit/closure and 9 failure scenarios through exact lifecycle states |
| **Failure scenarios covered** | ENTRY accepted / SL failed, SL ok / TP1 failed, entry partial fill, TP1 filled / runner missing, old SL cancel failed, runner submit failed after old SL cancel, PG protected / exchange missing, flat-position live-protection cleanup, duplicate TP1 fill idempotency |
| **Authority boundary preserved** | Harness asserts no real exchange write and no repo JSON/MD authority |

### P0-C Production Lifecycle Wiring

#### Goal

Wire the already implemented lifecycle components into the production path
without creating a parallel runner, recovery, or reconciliation authority.

The target is:

```text
submitted ticket
-> ENTRY fill/reject/unknown/partial classification
-> initial SL/TP1 protection proof or recovery
-> TP1 fill detection
-> runner mutation plan selection
-> official runner mutation execution
-> PG result event
-> exchange truth reconciliation
-> cleanup/recovery when flat or mismatched
-> runner_protected / lifecycle_closed / exact hard blocker
```

#### Current Progress

| Area | Current state |
| --- | --- |
| **Runner command preparation** | Implemented in PG command records |
| **Runner command execution** | Implemented through injected gateway and deployed as lifecycle repair code |
| **Runner proof materialization** | Implemented by runner protection adjuster after official runner SL ref exists |
| **Protection reconciliation** | Implemented over caller-provided exchange snapshots |
| **Orphan protection cleanup** | Implemented and deployed through migration `098`; cleanup only cancels PG-linked reduce-only protection refs after flat-position proof |
| **Lifecycle maintenance API wiring** | Implemented locally through `run_ticket_bound_lifecycle_maintenance` and `/api/trading-console/runtime-ticket-bound-lifecycle-maintenance`; it can materialize protection, prepare/execute recovery, prepare/execute runner mutation, materialize runner proof, and execute linked orphan cleanup |
| **Production exchange snapshot fetch / scheduler wiring** | Still a controlled integration task; the maintenance service accepts caller-provided exchange snapshots and does not fetch exchange truth on its own |
| **Runner mutation plan safety** | Default `submit_new_runner_sl_then_cancel_old` is implemented locally; scheduler/live use still needs explicit cadence, exchange snapshot source, and postdeploy acceptance |
| **First post-submit reconciliation tick** | Designed in `POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md`; implementation pending |
| **Recovery command determinism** | Owner-confirmed matrix exists; implementation must ensure every unsafe lifecycle blocker maps to one recovery command or hard stop |

#### Runner Mutation Plan Policy

The production runner path must not hard-code a single mutation order. It must
choose one **ProtectionMutationPlan** from current PG state, exchange open
orders, position qty, and exchange capability facts.

| Plan | Allowed when | Required result |
| --- | --- | --- |
| **keep_existing_sl** | Existing SL still validly protects remaining position and is not worse than runner policy | Record runner state as protected-by-existing-SL without exchange write |
| **submit_new_runner_sl_then_cancel_old** | Exchange allows overlapping reduce-only protection and qty cannot exceed current remaining position | Submit RUNNER_SL first, confirm it, then cleanup old SL |
| **cancel_old_then_submit_runner_sl** | Exchange forbids overlapping reduce-only protection and old SL cannot remain | Cancel old SL, submit RUNNER_SL, and mark any submit failure as critical runner defect |
| **emergency_reduce** | Remaining position cannot be protected by SL within allowed retry window | Submit only through the official recovery path and record critical defect |
| **manual_intervention_required** | PG/exchange identity or qty conflict cannot be safely resolved automatically | Freeze related new submits and notify Owner |

The current code already has `runner_mutation_command` and
`runner_mutation_executor`. P0-C must extend these components rather than add a
new parallel runner mutation service.

#### Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **TP1 fill starts runner transition** | Lifecycle enters `tp1_filled` / `runner_mutation_pending` |
| **Old SL mutation is official** | Cancel/replace command binds `ticket_id`, `exit_protection_set_id`, and old SL ref |
| **RUNNER_SL is official** | New runner SL exchange ref is produced through injected/official gateway path |
| **Reconciliation closes it** | `runner_protected` only after exchange and PG refs match |
| **Failure is visible** | Cancel failure, runner submit failure, and exchange mismatch update lifecycle blocker and ops health |
| **No cancel-first assumption** | Tests prove plan selection, including `keep_existing_sl`, `submit_new_runner_sl_then_cancel_old`, and cancel-first only when forced by exchange capability |
| **Maintenance entry is bounded** | API defaults `allow_exchange_mutation=false`; exchange mutation requires explicit request plus official runtime exchange gateway binding |
| **First tick is immediate and bounded** | Real protected submit result creates one first reconciliation tick; disabled smoke creates none; no active lifecycle creates no exchange calls or no-op rows |
| **Recovery matrix is deterministic** | SL missing, TP1 missing, runner SL missing, old SL cancel failure, unknown exchange-only order, and retry exhaustion each produce one recovery command or hard stop |

### P0-D Live Outcome Ledger

#### Goal

Create a structured live-outcome ledger for every real ticket/order lifecycle.
This is separate from broad strategy opportunity review.

#### Associated Design Docs

| Doc | Role |
| --- | --- |
| `docs/current/LIVE_OUTCOME_LEDGER_CONTRACT.md` | Defines ticket-bound live outcome fields and review decisions |
| `docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md` | Existing strategy-level review/governance context |
| `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | Provides lifecycle refs and protection refs |

#### Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **Every real ticket can produce one outcome row** | Outcome binds ticket, strategy, symbol, side, signal time, entry, stop, TP1, runner, final exit, fees, funding, and PnL |
| **Quality fields are structured** | MAE, MFE, R multiple, lifecycle defects, and stage reached are explicit fields |
| **Review decision is bounded** | Decision uses an allowed enum, not free-form narrative |
| **No policy mutation by review** | Review may recommend policy change; only Owner policy events change future scope |
| **PG current projection exists** | `LIVE_OUTCOME_LEDGER_CONTRACT.md` is implemented as one current PG row per ticket plus append-only event/defect rows |
| **No report authority** | Outcome materializer consumes PG lifecycle/order/fill/protection/reconciliation facts, not JSON/MD/report files |

### P1 Risk Reservation v0

#### Goal

Split the required stop-risk reservation from advanced portfolio allocation.
Before a ticket becomes FinalGate-ready, it must express:

```text
risk_at_stop = abs(entry_price - stop_price) * quantity
```

#### Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **Stop-risk estimate exists** | Ticket/risk row stores entry, stop, quantity, and calculated risk-at-stop |
| **Budget reservation exists** | No FinalGate-ready ticket without active reservation matching ticket scope |
| **Exposure conflict checked** | Same symbol, same side, and same strategy open-risk checks run before reservation |
| **Versioned policy bound** | Ticket binds risk policy and budget/sleeve version used at creation |
| **Production producer bound** | Entry reference and quantity come from typed, fresh, production-shaped action-time pricing/sizing producers rather than fixture-only dictionary keys |

### P1-C Owner Explanation Read Model

#### Goal

Expose Owner-facing status as product language:

```text
running
waiting_for_opportunity
processing_signal
candidate_trade_prepared
submit_blocked
position_protected
runner_pending
runner_protected
lifecycle_closed
needs_intervention
```

#### Associated Design Docs

| Doc | Role |
| --- | --- |
| `docs/current/OWNER_EXPLANATION_READ_MODEL_CONTRACT.md` | Backend explanation contract |
| `docs/current/RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE.md` | Terminology governance |
| `docs/current/SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md` | Monitor quiet/notify behavior |
| `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md` | Source authority rules |

#### Acceptance

| Internal state | Owner explanation requirement |
| --- | --- |
| No signal | Healthy waiting, no Owner action |
| Computed not satisfied | Market condition false, not system failure |
| Promotion/ticket exists | Exact strategy/symbol/side/stage shown |
| Submit blocked | Reason and safety boundary shown |
| TP1 historical blocker | Historical event scope, not current blocker |
| Runner pending | Remaining position protection action shown |

### P1-D Performance And Retention Control

#### Goal

Keep production runtime quiet and bounded when markets are inactive.

#### Associated Design Docs

| Doc | Role |
| --- | --- |
| `docs/current/SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md` | Server monitor cadence and notification boundary |
| `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` | Runtime file I/O elimination and performance boundary |

#### Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **No report growth** | No recurring watcher/report files in healthy waiting |
| **PG bounded growth** | Retention/current projection policy documented and enforced |
| **No restart storm** | systemd restart limits and app unavailable behavior verified |
| **Strict audit clear** | `validate_no_runtime_file_authority.py` passes |
| **Output governance clear** | `validate_output_artifact_scope.py --git-status --git-tracked` passes |

### P2-E Advanced Capital Risk Allocation

#### Goal

Add portfolio-level allocation on top of **Risk Reservation v0**:

```text
active reserved tickets and positions
-> StrategyGroup sleeve allocation
-> symbol / side / cluster exposure caps
-> drawdown state
-> cooldown state
-> multi-strategy conflict resolution
-> right-tail runner preservation rules
```

#### Associated Design Docs

| Doc | Role |
| --- | --- |
| `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` | Primary capital/risk design |
| `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | Current experiment boundary |
| `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` | Owner budget/profile authority |
| `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` | PG schema target |

#### Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **Portfolio exposure checked** | Open risk, pending reserved risk, and current positions are evaluated together |
| **Strategy sleeve enforced** | Each StrategyGroup can be capped or paused without changing strategy semantics |
| **Symbol/side/cluster caps enforced** | Concentrated exposure can block or downsize new tickets |
| **Drawdown/cooldown state enforced** | Recent losses can reduce or pause allocation through policy, not ad hoc code |
| **Policy versioned** | Ticket binds capital policy, sleeve, cap, and allocation versions |
| **Review feedback separated** | Trade review recommends policy change; it does not mutate policy directly |

### P2-F Frontend Read Model Integration

#### Goal

Build frontend surfaces from backend read models, not from raw chain internals.

#### Associated Design Docs

| Doc | Role |
| --- | --- |
| `docs/current/OWNER_EXPLANATION_READ_MODEL_CONTRACT.md` | Backend explanation source |
| `/Users/jiangwei/Documents/trading-console/docs/frontend/OWNER_EXPLANATION_READ_MODEL_FRONTEND_CONTRACT.md` | Frontend display contract |
| `/Users/jiangwei/Documents/trading-console/docs/frontend/READ_MODEL_SOURCE_MAP.md` | Frontend source map |

#### Acceptance

| Surface | Required source |
| --- | --- |
| Runtime health | Backend status/read model |
| Signal progress | Backend explanation projection |
| Why no trade | Backend explanation projection |
| Account / capital | Backend portfolio/capital read model |
| Ticket/lifecycle | Backend ticket lifecycle read model |

## Shared Hard Stops

Every program must stop if it introduces:

```text
FinalGate bypass
Operation Layer bypass
exchange write outside official path
live profile expansion
order sizing expansion
credential mutation
withdrawal or transfer
runtime decision from repo MD/JSON/output/report files
unsupported side mirroring
generated_at as signal event time
replay event as fresh live signal
```

## Current Chain Position

```text
chain_position: daily_live_enablement_status
strategy_group_id: active 5 StrategyGroups
symbol: active candidate scopes
stage: production_real_signal_reached_l7_ticket_blocked
first_blocker: risk_reservation_entry_reference_price_missing
evidence: `12feb47e` at migration 112 recorded 7 fresh signals, 7 promotions, and 6 real-submit lanes after deployment; every observed lane produced 0 Ticket and the reconstructed Ticket consumer returned missing entry reference, invalid intended quantity, and invalid risk-at-stop
next_action: execute RT-1 through RT-3, then run PC-1 six-event certification before waiting for another natural market signal
stop_condition: six current Event Specs pass raw-source-to-Ticket and Runtime Safety State certification without downstream dictionary injection; unresolved Ticket blockers persist across no-signal ticks; the next eligible natural signal no longer stops at Ticket materialization
owner_action_required: no
authority_boundary: no FinalGate bypass, no Operation Layer bypass, no exchange write bypass, no live profile or sizing mutation
```
