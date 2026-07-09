---
title: MAINLINE_ENGINEERING_PROGRAM_PLAN
status: CURRENT_PROGRAM_PLAN
authority: docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md
last_verified: 2026-07-09
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
| **dev and Tokyo are aligned on post-submit first tick** | `dev`, `origin/dev`, and Tokyo release head are `4b0b8a272814b2458fafc1913f8d7c63219ff321`; Tokyo postdeploy acceptance passed; PG migration is at `alembic=101` |
| **PG current state is the runtime source** | `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`, `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| **Repo/output/report files are not runtime authority** | `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` |
| **Five StrategyGroups are active WIP** | `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`, PG candidate scope seed |
| **Multi-symbol and side-specific action-time path exists** | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| **Ticket identity and TP1 are PG-backed** | `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` |
| **Initial order lifecycle/protection PG objects exist** | `brc_ticket_bound_*` tables and current ticket-bound materializers |
| **Runner dynamic management is code-covered and deployed as lifecycle repair** | `runner_mutation_command`, `runner_mutation_executor`, `runner_protection_adjuster`, lifecycle tests, and Tokyo release `4b0b8a27` cover TP1 filled -> RUNNER_SL submit -> old SL cleanup -> runner proof through official-path records |
| **Exchange protection reconciliation is code-covered and deployed as readonly comparison logic** | `protection_reconciler` compares PG protection rows with caller-provided exchange snapshots, including missing order, side mismatch, qty mismatch, orphan reduce-only order, TP1-fill runner gap, and flat-position live protection |
| **First tick and recovery-command defaults are deployed** | Tokyo release `4b0b8a27` creates `brc_ticket_bound_reconciliation_ticks`, `brc_ticket_bound_scope_freezes`, first post-submit tick selection, TP1 degraded recovery, max 3 recovery attempts, and scope freeze records at `strategy_group_id + symbol + side` |
| **Scope freeze is not yet a full pre-submit hard blocker** | Scope freeze rows are written by first tick / reconciler / recovery command paths, but promotion, lane, ticket, Runtime Safety State, FinalGate preflight, and protected submit must still reject active frozen scopes before the freeze can be considered fully enforced |
| **No recent postdeploy signal or ticket exists** | Latest server health after deploy showed `recent signals/promotions/lanes/tickets/attempts = 0`; this is market/no-event state, not a current engineering blocker |
| **Trading quality / capital risk allocation is designed but not fully implemented** | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md`; `risk_at_stop` must be split into an earlier reservation layer before advanced allocation |

## Program Map

| Program | Priority | Goal | Primary design docs | Main acceptance |
| --- | --- | --- | --- | --- |
| **P0-0 Operation Layer / Exchange Capability Boundary** | P0 | Confirm the real official-path exchange capabilities that lifecycle, runner, recovery, and reconciliation may rely on | `TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | ENTRY, SL, TP1, reduce-only, query open orders/fills/position, cancel, idempotent client order id, and runner SL capability are explicitly mapped to supported / unsupported / recovery-required |
| **P0-1 Ticket-Bound Lifecycle Safety Core** | P0 | Keep lifecycle state machine, hard invariants, sequential submit recovery, runner mutation, exchange protection reconciliation, and closure under one model | `TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md`, `POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md` | A submitted ticket can prove ENTRY, SL, TP1, RUNNER_SL, final exit, reconciliation, settlement, and review, or stop at one exact lifecycle hard blocker |
| **P0-2 Full Chain Simulation Harness** | P0 | Verify the lifecycle model with constructed raw inputs, two golden paths, and a failure matrix without real exchange writes | `PRE_TRADE_RUNTIME_CONTRACT.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | AVAX short and CPM long golden paths plus failure matrix prove lifecycle correctness; broader active event specs remain impact coverage |
| **P0-C Production Lifecycle Wiring** | P0 | Wire existing lifecycle, first reconciliation tick, recovery, runner mutation, reconciler, and cleanup services into production cadence without adding a second lifecycle path | `TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md`, `P0_C_PRODUCTION_LIFECYCLE_SCHEDULER_AND_SNAPSHOT_SOURCE_DESIGN.md`, `POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md` | ENTRY, SL, TP1, RUNNER_SL, final exit, first tick, recovery, cleanup, and reconciliation are event/startup/periodic wired and stop at exact lifecycle blockers |
| **P0-E Scope Freeze Pre-Submit Gate** | P0 | Turn active real-risk scope freezes into hard blockers before any new promotion, lane, ticket, Runtime Safety State, FinalGate preflight, or protected submit can proceed | `P0_CAPITAL_SAFETY_CLOSURE_DESIGN.md`, `POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md`, `BLOCKER_CLASSIFICATION_CONTRACT.md`, `PRE_TRADE_RUNTIME_CONTRACT.md` | An active real-risk `brc_ticket_bound_scope_freezes` row blocks the exact `strategy_group_id + symbol + side`; stale no-risk residue becomes cleanup/outcome and does not block |
| **P0-D Live Outcome Ledger** | P0 | Turn real tickets and orders into structured strategy-learning rows without becoming submit authority | `P0_CAPITAL_SAFETY_CLOSURE_DESIGN.md`, `LIVE_OUTCOME_LEDGER_CONTRACT.md`, `STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md` | Every real ticket can bind entry, stop, TP1, runner, final exit, fees, funding, PnL, MAE/MFE, R multiple, lifecycle defects, and review decision |
| **P0-F Continuous Reconciliation Tick** | P0 | Continue exchange-truth reconciliation after the first post-submit tick until lifecycle closure, exact recovery, or hard stop | `P0_CAPITAL_SAFETY_CLOSURE_DESIGN.md`, `POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md`, `P0_C_PRODUCTION_LIFECYCLE_SCHEDULER_AND_SNAPSHOT_SOURCE_DESIGN.md` | Scheduled/event-driven ticks refresh open orders, fills, positions, protection refs, runner state, and final exit without creating report files or duplicate lifecycle actions |
| **P1 Risk Reservation v0** | P1 | Require ticket-level stop-risk estimate and budget reservation before FinalGate-ready state | `TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md`, `RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | `risk_at_stop = abs(entry_price - stop_price) * quantity` is computed and reserved before FinalGate-ready submit |
| **P1-C Owner Explanation Read Model** | P1 | Make no-trade, signal, ticket, submit, runner, and closure states human-readable | `OWNER_EXPLANATION_READ_MODEL_CONTRACT.md`, `RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE.md` | Owner can see whether the system is waiting, processing, blocked, protected, or closed without decoding internal terms |
| **P1-D Performance And Retention Control** | P1 | Keep no-signal ticks, monitor runs, PG rows, logs, and reports bounded | `SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md`, `PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` | No recurring report growth; no restart storm; PG/file-authority validators remain clear |
| **P2-E Advanced Capital Risk Allocation** | P2 | Allocate capital by portfolio exposure, StrategyGroup sleeve, symbol/side cap, cluster exposure, cooldown, and drawdown state | `TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md`, `RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | Multi-strategy / multi-symbol allocation can scale or pause exposure without changing per-ticket safety facts |
| **P2-F Frontend Read Model Integration** | P2 | Build frontend against backend explanation/read models, not raw PG internals | `OWNER_EXPLANATION_READ_MODEL_CONTRACT.md`, frontend `OWNER_EXPLANATION_READ_MODEL_FRONTEND_CONTRACT.md` | UI shows runtime health, signal progress, account state, ticket status, and why-no-trade from backend read models |

## Priority Order

| Order | Program | Reason |
| --- | --- | --- |
| 1 | **P0-0 Operation Layer / Exchange Capability Audit** | Lifecycle and runner plans must be grounded in what the official gateway can actually submit, cancel, query, and reconcile |
| 2 | **P0-1 Ticket-Bound Lifecycle Safety Core** | State machine, invariants, and failure states define what the harness must prove |
| 3 | **P0-2 Full Chain Simulation Harness** | It verifies the lifecycle model with constructed market/fact/order inputs before waiting for live market events |
| 4 | **P0-C Production Lifecycle Wiring** | TP1-filled residual position protection and post-entry recovery are the highest post-entry funds-safety risks |
| 5 | **P0-E Scope Freeze Pre-Submit Gate** | A current-risk frozen scope must stop new promotion / ticket / submit before the same lifecycle defect can recur; stale no-risk residue must not block valid opportunities |
| 6 | **P0-D Live Outcome Ledger** | Real trade results must become structured learning data, not narrative review only |
| 7 | **P0-F Continuous Reconciliation Tick** | First tick catches immediate exchange truth; continued ticks are required until closure, recovery, or hard stop |
| 8 | **P1 Risk Reservation v0** | A ticket must express max stop loss before FinalGate-ready submit |
| 9 | **P1-C Owner Explanation Read Model** | The Owner surface must explain the chain without exposing raw internal blockers |
| 10 | **P1-D Performance And Retention Control** | Server health must remain stable while watcher/monitor run continuously without deleting trade lineage |
| 11 | **P2-F Frontend Read Model Integration** | Frontend becomes durable only after backend read models are stable |
| 12 | **P2-E Advanced Capital Risk Allocation** | Portfolio-level sizing and capital quality should scale only after per-ticket lifecycle mechanics are hard |

## Current Next Execution Order

This is the authoritative remaining sequence after Tokyo release `4b0b8a27`.
It supersedes ad hoc task ordering in chat summaries.

| Order | Next work | Priority | Acceptance |
| --- | --- | --- | --- |
| 1 | **P0 Capital Safety Closure design-to-implementation** | P0 | `P0_CAPITAL_SAFETY_CLOSURE_DESIGN.md` is implemented: current-risk freeze blocks, stale no-risk residue does not block, reconciliation continues, recovery is deterministic, and outcome rows are produced |
| 2 | **Scope freeze pre-submit hard blocker** | P0 | Active real-risk `brc_ticket_bound_scope_freezes` blocks matching `strategy_group_id + symbol + side` before promotion, lane, ticket, Runtime Safety State, FinalGate preflight, and protected submit |
| 3 | **Continuous reconciliation tick** | P0 | After first tick, scheduled/event-driven reconciliation continues until lifecycle closure, exact recovery command, or hard stop |
| 4 | **Live Outcome Ledger** | P0 | Every real ticket has one structured outcome row or one exact hard-blocked outcome row |
| 5 | **Risk-at-stop reservation** | P1 | `risk_at_stop = abs(entry_price - stop_price) * quantity` is computed and reserved before FinalGate-ready submit |
| 6 | **Owner Explanation Read Model** | P1 | Owner can read why the system waited, processed, blocked, protected, recovered, or closed without interpreting internal blocker codes |
| 7 | **Frontend read-model integration** | P2 | Frontend displays backend-provided explanation/read models only; it does not classify blockers, facts, lanes, tickets, or submit authority |
| 8 | **Trading quality / capital budget / portfolio risk model** | P2 | Advanced allocation can adjust exposure quality without weakening per-ticket hard safety, stop-risk reservation, or lifecycle reconciliation |

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
| **Remaining first blocker** | `production_lifecycle_wiring_and_live_outcome_ledger_not_complete` after local P0-2 failure-matrix closure |
| **Orphan protection cleanup command** | Implemented locally on the P0-1 branch through migration `098`, `orphan_protection_cleanup_command`, and focused tests; deploy remains Owner-approved |

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
stage: p0_3_p0_4_design_confirmed
first_blocker: scope_freeze_pre_submit_gate_missing
evidence: dev/origin-dev/Tokyo are aligned on 4b0b8a27; PG alembic is 101; first post-submit tick, TP1 degraded recovery, retry limit, and scope freeze writes are deployed; active freezes are not yet enforced across every pre-submit consumer
next_action: implement scope freeze pre-submit hard blocker, then Live Outcome Ledger, continuous reconciliation tick, Risk-at-stop reservation, Owner Explanation Read Model, frontend read-model integration, and trading-quality capital allocation
stop_condition: active brc_ticket_bound_scope_freezes blocks matching StrategyGroup + symbol + side before promotion, lane, ticket, Runtime Safety State, FinalGate preflight, and protected submit
owner_action_required: no
authority_boundary: no FinalGate bypass, no Operation Layer bypass, no exchange write bypass, no live profile or sizing mutation
```
