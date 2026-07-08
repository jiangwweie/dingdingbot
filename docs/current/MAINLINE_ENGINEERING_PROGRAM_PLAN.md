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
| **PG current state is the runtime source** | `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`, `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| **Repo/output/report files are not runtime authority** | `docs/current/REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md`, `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` |
| **Five StrategyGroups are active WIP** | `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`, PG candidate scope seed |
| **Multi-symbol and side-specific action-time path exists** | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md`, `docs/current/MULTI_STRATEGY_MULTI_SYMBOL_MULTI_SIDE_ACTION_TIME_EVOLUTION_DESIGN.md` |
| **Ticket identity and TP1 are PG-backed** | `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` |
| **Initial order lifecycle/protection PG objects exist** | `brc_ticket_bound_*` tables and current ticket-bound materializers |
| **Runner dynamic management is locally closed** | `runner_mutation_command`, `runner_mutation_executor`, `runner_protection_adjuster`, and lifecycle tests cover TP1 filled -> old SL cancel -> RUNNER_SL submit -> runner proof |
| **Exchange protection reconciliation is locally covered** | `protection_reconciler` compares PG protection rows with caller-provided exchange snapshots, including missing order, side mismatch, qty mismatch, orphan reduce-only order, TP1-fill runner gap, and flat-position live protection |
| **Trading quality / capital risk allocation is designed but not implemented** | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |

## Program Map

| Program | Priority | Goal | Primary design docs | Main acceptance |
| --- | --- | --- | --- | --- |
| **P0-A Full Chain Simulation Harness** | P0 | Construct raw inputs and run the entire L2-L9 chain locally without real exchange writes | `L1_L9_OPTIMIZATION_EXECUTION_PLAN.md`, `PRE_TRADE_RUNTIME_CONTRACT.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | All active StrategyGroup event specs can reach mock protected submit and post-submit lifecycle closure |
| **P0-B Ticket-Bound Lifecycle Safety Core** | P0 | Close sequential submit recovery, official runner mutation, exchange protection reconciliation, and lifecycle closure as one state machine | `TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`, `TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | A submitted ticket can prove ENTRY, SL, TP1, RUNNER_SL, final exit, reconciliation, settlement, and review, or stop at one exact lifecycle hard blocker |
| **P1-C Owner Explanation Read Model** | P1 | Make no-trade, signal, ticket, submit, runner, and closure states human-readable | `OWNER_EXPLANATION_READ_MODEL_CONTRACT.md`, `RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE.md` | Owner can see whether the system is waiting, processing, blocked, protected, or closed without decoding internal terms |
| **P1-D Performance And Retention Control** | P1 | Keep no-signal ticks, monitor runs, PG rows, logs, and reports bounded | `SERVER_SIDE_RUNTIME_MONITOR_CONTRACT.md`, `REPO_FILE_SOURCE_ELIMINATION_GOVERNANCE_PLAN.md`, `PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` | No recurring report growth; no restart storm; PG/file-authority validators remain clear |
| **P2-E Capital Risk Allocation** | P2 | Allocate budget by loss-at-stop, portfolio exposure, StrategyGroup sleeve, and symbol/side cap | `TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md`, `RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | Ticket cannot reach FinalGate-ready without a current risk estimate and active budget reservation |
| **P2-F Frontend Read Model Integration** | P2 | Build frontend against backend explanation/read models, not raw PG internals | `OWNER_EXPLANATION_READ_MODEL_CONTRACT.md`, frontend `OWNER_EXPLANATION_READ_MODEL_FRONTEND_CONTRACT.md` | UI shows runtime health, signal progress, account state, ticket status, and why-no-trade from backend read models |

## Priority Order

| Order | Program | Reason |
| --- | --- | --- |
| 1 | **P0-A Full Chain Simulation Harness** | It exposes real chain defects before waiting for live market events |
| 2 | **P0-B Ticket-Bound Lifecycle Safety Core** | Runner mutation, protection reconciliation, submit recovery, and closure are one post-submit safety core |
| 3 | **P1-C Owner Explanation Read Model** | The Owner surface must explain the chain without exposing raw internal blockers |
| 4 | **P1-D Performance And Retention Control** | Server health must remain stable while watcher/monitor run continuously |
| 5 | **P2-E Capital Risk Allocation** | Sizing and portfolio quality should govern scale after lifecycle mechanics are hard |
| 6 | **P2-F Frontend Read Model Integration** | Frontend becomes durable only after backend read models are stable |

## Program Details

### P0-A Full Chain Simulation Harness

#### Goal

Build a deterministic local harness that starts from constructed market/fact
inputs and runs the current chain:

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
-> reconciliation / settlement / review proof
```

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
| **All active event specs covered** | CPM long, MPG long, MI long, SOR long, SOR short, BRF2 short fixtures pass |
| **No exchange write** | Harness uses explicit mock official-path results |
| **No file authority** | Harness uses PG/in-memory typed fixtures, not repo/output/report JSON |
| **Ticket identity stable** | Each run records StrategyGroup, symbol, side, profile, policy versions, facts, and protection refs |
| **Negative paths covered** | Missing TP1, missing SL, unsupported side, stale fact, duplicate lane, missing runner SL all fail closed |

### P0-B Ticket-Bound Lifecycle Safety Core

#### Goal

Implement one post-submit lifecycle safety core that covers:

```text
sequential ENTRY / SL / TP1 submit recovery
-> protection reconciliation against exchange truth
-> TP1 fill handling
-> official runner SL mutation
-> final exit / settlement / review closure
```

#### Associated Design Docs

| Doc | Role |
| --- | --- |
| `docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md` | Implementation plan and acceptance matrix |
| `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` | Architecture and PG lifecycle/protection tables |
| `docs/current/ACTIVE_STRATEGYGROUP_SEMANTICS_REVIEW_AND_OPTIMIZATION_PLAN.md` | StrategyGroup-specific runner and exit intent |
| `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` | Defines PG constraints and lineage |

#### Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **Sequential failure classified and recoverable** | ENTRY reject/unknown/orphan/partial, SL failure, TP1 failure, and duplicate submit map to lifecycle states; missing SL/TP1 recovery can be executed locally through an injected gateway |
| **Protection reconciled** | PG SL/TP1/RUNNER_SL rows match exchange open orders, fills, position, and OrderLifecycle |
| **Runner mutation official** | Old SL cancel/replace and RUNNER_SL submit go through ticket-bound Operation Layer path |
| **No invented protection** | Proof rows cannot stand in for missing exchange truth |
| **Lifecycle closes cleanly** | Final exit, flat-position proof, reconciliation, settlement, and review are all bound before `lifecycle_closed` |
| **Ops health surfaces blockers** | Current lifecycle hard blockers appear in readonly health checks |

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

### P2-E Capital Risk Allocation

#### Goal

Add a capital/risk layer between Action-Time Ticket and FinalGate:

```text
ticket
-> risk-at-stop estimate
-> portfolio exposure check
-> StrategyGroup sleeve
-> symbol/side/event cap
-> budget reservation
-> FinalGate-ready sizing input
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
| **Risk measured at stop** | Notional derives from entry, stop, loss budget, filters, and leverage |
| **Reservation required** | No FinalGate-ready ticket without active budget reservation |
| **Concentration checked** | Same symbol/side/cluster caps enforced |
| **Policy versioned** | Ticket binds capital policy/sleeve/cap versions |
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
stage: healthy_waiting_plus_ticket_bound_lifecycle_safety_core
first_blocker: none for current pre-trade chain; remaining lifecycle gap is production wiring and real exchange-read/write acceptance behind explicit deploy approval
evidence: PG pre-trade/action-time chain exists; local lifecycle safety core now covers full-chain simulation, sequential submit recovery, protection reconciliation, runner mutation, and final closure without file authority
next_action: complete local verification gates, review diff, then request Owner approval before any Tokyo deploy or production wiring activation
stop_condition: each program reaches its acceptance proof without file authority or safety-boundary regression
owner_action_required: no
authority_boundary: no FinalGate bypass, no Operation Layer bypass, no exchange write bypass, no live profile or sizing mutation
```
