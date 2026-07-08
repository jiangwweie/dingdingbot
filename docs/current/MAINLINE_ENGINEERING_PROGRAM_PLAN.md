---
title: MAINLINE_ENGINEERING_PROGRAM_PLAN
status: CURRENT_PROGRAM_PLAN
authority: docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md
last_verified: 2026-07-08
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
| **dev and Tokyo are aligned on lifecycle-safety-core repair** | `dev`, `origin/dev`, and Tokyo release head are `4f813a16e32930fefb67590283d041b1fead207f`; Tokyo postdeploy acceptance passed; PG migration is at `alembic=097` |
| **PG current state is the runtime source** | `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`, `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| **Repo/output/report files are not runtime authority** | `docs/current/REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md`, `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` |
| **Five StrategyGroups are active WIP** | `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`, PG candidate scope seed |
| **Multi-symbol and side-specific action-time path exists** | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md`, `docs/current/MULTI_STRATEGY_MULTI_SYMBOL_MULTI_SIDE_ACTION_TIME_EVOLUTION_DESIGN.md` |
| **Ticket identity and TP1 are PG-backed** | `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` |
| **Initial order lifecycle/protection PG objects exist** | `brc_ticket_bound_*` tables and current ticket-bound materializers |
| **Runner dynamic management is code-covered and deployed as lifecycle repair** | `runner_mutation_command`, `runner_mutation_executor`, `runner_protection_adjuster`, lifecycle tests, and Tokyo release `4f813a16` cover TP1 filled -> old SL cancel -> RUNNER_SL submit -> runner proof through official-path records |
| **Exchange protection reconciliation is code-covered and deployed as readonly comparison logic** | `protection_reconciler` compares PG protection rows with caller-provided exchange snapshots, including missing order, side mismatch, qty mismatch, orphan reduce-only order, TP1-fill runner gap, and flat-position live protection |
| **No recent postdeploy signal or ticket exists** | Latest server health after deploy showed `recent signals/promotions/lanes/tickets/attempts = 0`; this is market/no-event state, not a current engineering blocker |
| **Trading quality / capital risk allocation is designed but not fully implemented** | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md`; `risk_at_stop` must be split into an earlier reservation layer before advanced allocation |

## Program Map

| Program | Priority | Goal | Primary design docs | Main acceptance |
| --- | --- | --- | --- | --- |
| **P0-0 Operation Layer / Exchange Capability Audit** | P0 | Confirm the real official-path exchange capabilities that lifecycle, runner, recovery, and reconciliation may rely on | `OPERATION_LAYER_EXCHANGE_CAPABILITY_AUDIT.md`, `TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | ENTRY, SL, TP1, reduce-only, query open orders/fills/position, cancel, idempotent client order id, and runner SL capability are explicitly mapped to supported / unsupported / recovery-required |
| **P0-1 Ticket-Bound Lifecycle Safety Core** | P0 | Keep lifecycle state machine, hard invariants, sequential submit recovery, runner mutation, exchange protection reconciliation, and closure under one model | `TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | A submitted ticket can prove ENTRY, SL, TP1, RUNNER_SL, final exit, reconciliation, settlement, and review, or stop at one exact lifecycle hard blocker |
| **P0-2 Full Chain Simulation Harness** | P0 | Verify the lifecycle model with constructed raw inputs, two golden paths, and a failure matrix without real exchange writes | `L1_L9_OPTIMIZATION_EXECUTION_PLAN.md`, `PRE_TRADE_RUNTIME_CONTRACT.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | AVAX short and CPM long golden paths plus failure matrix prove lifecycle correctness; broader active event specs remain impact coverage |
| **P0-3 Official Runner SL Mutation + Protection Reconciler** | P0 | Keep TP1-filled remaining position protected through official cancel/replace/submit and exchange truth comparison | `TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | TP1 filled -> old SL cancel / RUNNER_SL submit / PG result / exchange reconciliation can prove `runner_protected` or exact hard blocker |
| **P0/P1 Live Outcome Ledger** | P0/P1 | Turn real tickets and orders into structured strategy-learning rows | `LIVE_OUTCOME_LEDGER_CONTRACT.md`, `STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md` | Every real ticket can bind entry, stop, TP1, runner, final exit, fees, funding, PnL, MAE/MFE, R multiple, lifecycle defects, and review decision |
| **P1 Risk Reservation v0** | P1 | Require ticket-level stop-risk estimate and budget reservation before FinalGate-ready state | `TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md`, `RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | `risk_at_stop = abs(entry_price - stop_price) * quantity` is computed and reserved before FinalGate-ready submit |
| **P1-C Owner Explanation Read Model** | P1 | Make no-trade, signal, ticket, submit, runner, and closure states human-readable | `OWNER_EXPLANATION_READ_MODEL_CONTRACT.md`, `RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE.md` | Owner can see whether the system is waiting, processing, blocked, protected, or closed without decoding internal terms |
| **P1-D Performance And Retention Control** | P1 | Keep no-signal ticks, monitor runs, PG rows, logs, and reports bounded | `SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md`, `REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md`, `PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` | No recurring report growth; no restart storm; PG/file-authority validators remain clear |
| **P2-E Advanced Capital Risk Allocation** | P2 | Allocate capital by portfolio exposure, StrategyGroup sleeve, symbol/side cap, cluster exposure, cooldown, and drawdown state | `TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md`, `RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | Multi-strategy / multi-symbol allocation can scale or pause exposure without changing per-ticket safety facts |
| **P2-F Frontend Read Model Integration** | P2 | Build frontend against backend explanation/read models, not raw PG internals | `OWNER_EXPLANATION_READ_MODEL_CONTRACT.md`, frontend `OWNER_EXPLANATION_READ_MODEL_FRONTEND_CONTRACT.md` | UI shows runtime health, signal progress, account state, ticket status, and why-no-trade from backend read models |

## Priority Order

| Order | Program | Reason |
| --- | --- | --- |
| 1 | **P0-0 Operation Layer / Exchange Capability Audit** | Lifecycle and runner plans must be grounded in what the official gateway can actually submit, cancel, query, and reconcile |
| 2 | **P0-1 Ticket-Bound Lifecycle Safety Core** | State machine, invariants, and failure states define what the harness must prove |
| 3 | **P0-2 Full Chain Simulation Harness** | It verifies the lifecycle model with constructed market/fact/order inputs before waiting for live market events |
| 4 | **P0-3 Official Runner SL Mutation + Protection Reconciler** | TP1-filled residual position protection is the highest post-entry funds-safety risk |
| 5 | **P0/P1 Live Outcome Ledger** | Real trade results must become structured learning data, not narrative review only |
| 6 | **P1 Risk Reservation v0** | A ticket must express max stop loss before FinalGate-ready submit |
| 7 | **P1-C Owner Explanation Read Model** | The Owner surface must explain the chain without exposing raw internal blockers |
| 8 | **P1-D Performance And Retention Control** | Server health must remain stable while watcher/monitor run continuously without deleting trade lineage |
| 9 | **P2-E Advanced Capital Risk Allocation** | Portfolio-level sizing and capital quality should scale only after per-ticket lifecycle mechanics are hard |
| 10 | **P2-F Frontend Read Model Integration** | Frontend becomes durable only after backend read models are stable |

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
| **Audit complete** | `docs/current/OPERATION_LAYER_EXCHANGE_CAPABILITY_AUDIT.md` |
| **Gateway readiness method gap closed** | Runtime gateway readiness now requires lifecycle methods, not only `place_order` |
| **Recent fills wrapper added** | `ExchangeGateway.fetch_my_trades` is available as a read-only capability |
| **Remaining first blocker** | `full_chain_failure_matrix_not_complete` after local orphan protection cleanup command implementation |
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
| `docs/current/L1_L9_OPTIMIZATION_EXECUTION_PLAN.md` | Defines L1-L9 implementation batches and hard stops |
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

### P0-3 Official Runner SL Mutation + Protection Reconciler

#### Goal

Keep every TP1-filled residual position protected through the official path:

```text
TP1 fill detected
-> remaining_qty computed
-> old SL cancel or replace command
-> RUNNER_SL submit
-> PG result event
-> exchange truth reconciliation
-> runner_protected or exact blocker
```

#### Current Progress

| Area | Current state |
| --- | --- |
| **Runner command preparation** | Implemented in PG command records |
| **Runner command execution** | Implemented through injected gateway and deployed as lifecycle repair code |
| **Runner proof materialization** | Implemented by runner protection adjuster after official runner SL ref exists |
| **Protection reconciliation** | Implemented over caller-provided exchange snapshots |
| **Production exchange snapshot fetch / scheduler wiring** | Still a controlled integration task, not an implicit deploy-side authority change |

#### Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **TP1 fill starts runner transition** | Lifecycle enters `tp1_filled` / `runner_mutation_pending` |
| **Old SL mutation is official** | Cancel/replace command binds `ticket_id`, `exit_protection_set_id`, and old SL ref |
| **RUNNER_SL is official** | New runner SL exchange ref is produced through injected/official gateway path |
| **Reconciliation closes it** | `runner_protected` only after exchange and PG refs match |
| **Failure is visible** | Cancel failure, runner submit failure, and exchange mismatch update lifecycle blocker and ops health |

### P0/P1 Live Outcome Ledger

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
| `docs/current/REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md` | File/output governance |
| `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` | Runtime file I/O elimination |
| `docs/current/RUNTIME_CONTROL_STATE_MAINLINE_FILE_IO_MAP.md` | Mainline file I/O inventory |

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
stage: lifecycle_safety_core_deployed_waiting_for_real_signal
first_blocker: no_recent_fresh_signal_for_real_lifecycle_acceptance
evidence: dev/origin-dev/Tokyo are aligned on 4f813a16; PG alembic is 097; lifecycle safety core repair is deployed; latest health showed no recent signal/promotion/lane/ticket/attempt
next_action: run Operation Layer / Exchange Capability Audit, strengthen full-chain harness around two golden paths plus failure matrix, implement Live Outcome Ledger, and keep watcher/monitor readonly observation active
stop_condition: future real ticket proves entry, protection, TP1, runner, final exit, reconciliation, settlement, live outcome, and review, or stops at one exact lifecycle hard blocker
owner_action_required: no
authority_boundary: no FinalGate bypass, no Operation Layer bypass, no exchange write bypass, no live profile or sizing mutation
```
