---
title: P0_CAPITAL_SAFETY_CLOSURE_DESIGN
status: CURRENT_DESIGN
authority: docs/current/P0_CAPITAL_SAFETY_CLOSURE_DESIGN.md
last_verified: 2026-07-09
---

# P0 Capital Safety Closure Design

## Purpose

This document defines the P0 capital-safety closure program after the PG-backed
pre-trade chain and ticket-bound lifecycle work.

The goal is:

```text
fresh signal
-> Action-Time Ticket
-> protected submit
-> exchange truth reconciliation
-> deterministic recovery or hard stop
-> lifecycle closure
-> Live Outcome Ledger
```

This is not a strategy optimization program. It does not authorize live profile
expansion, order-sizing expansion, FinalGate bypass, Operation Layer bypass,
withdrawal, transfer, credential mutation, or runtime decisions from
repo/output/report JSON or Markdown files.

## Owner-Confirmed Decisions

| Decision | Rule |
| --- | --- |
| **Scope freeze grain** | `strategy_group_id + symbol + side` |
| **Freeze strength** | Hard block only while the same scope has unresolved real capital risk |
| **Risk-based blocking** | Block new trades only when current facts imply unresolved real capital risk or unknown live exchange risk |
| **Stale local state** | Stale PG/local/monitor residue must become cleanup, reconciliation, or outcome work; it must not mechanically block future trades after current risk is disproved |
| **Unknown exchange-only order** | Do not auto-adopt or auto-cancel; freeze matching scope only when the order can create current risk |
| **Recovery mutation scope** | Only ticket-bound, PG-linked, known protection refs may be mutated automatically |
| **Reconciliation cadence** | Event-triggered first; periodic tick as bounded fallback; no active lifecycle means no heavy work |
| **Deployment** | Tokyo deploy requires explicit Owner approval |

## Core Risk Reality Rule

Capital safety blockers must be based on **current real risk**, not stale local
records, historical blockers, dirty projections, or engineering residue.

The general rule is:

```text
block when current facts prove risk or unknown live exchange exposure;
reconcile when facts disagree;
clean up when only local residue remains;
record outcome when lifecycle is over;
do not block new valid opportunities after current risk is disproved.
```

The system must distinguish:

| Example state | Current risk? | Required behavior |
| --- | ---: | --- |
| PG says SL/TP1 exists, exchange position is open, matching protection is missing | Yes | Freeze scope and create recovery command |
| PG says SL/TP1 exists, exchange position is flat, no matching open protection order exists | No | Do not block new trade; write cleanup/outcome state |
| PG says SL/TP1 exists, exchange position is flat, PG-linked reduce-only protection is still open | Operational risk | Run bounded PG-linked cleanup; freeze only until cleanup/hard stop |
| Exchange has unknown open order for the same symbol/side context | Unknown risk | Freeze matching scope and notify; do not auto-cancel or auto-adopt |
| Exchange has unrelated historical closed order | No | Do not block new trade |

These are examples, not an exhaustive whitelist. Any future blocker must prove
which current risk it protects against. If it cannot name a current risk, it is
a cleanup/reconciliation/read-model problem, not a pre-submit trading blocker.

This rule prevents the system from turning old PG residue, stale monitor state,
historical attempts, report leftovers, or vague engineering uncertainty into a
permanent trading blocker.

## Current Objective Facts

| Fact | Evidence |
| --- | --- |
| **Pre-trade chain is PG-backed** | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| **Ticket-bound lifecycle and TP1/runner semantics exist** | `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` |
| **Post-submit first tick and recovery design exists** | `docs/current/POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md` |
| **Live Outcome Ledger contract exists** | `docs/current/LIVE_OUTCOME_LEDGER_CONTRACT.md` |
| **Production file authority is forbidden** | `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` |
| **Current implementation state** | Scope freeze pre-submit guard, scheduled reconciliation tick, and Live Outcome Ledger PG projection are implemented locally on `codex/p0-capital-safety-closure` |
| **Current first blocker** | `review_validation_and_deploy_approval_pending` |

## Program Scope

P0 capital safety closure contains four work packages:

| Order | Work package | Goal |
| ---: | --- | --- |
| **1** | Scope Freeze Pre-Submit Gate | Prevent unresolved real-risk scopes from creating another trade intent |
| **2** | Continuous Reconciliation Tick | Keep PG lifecycle state aligned with exchange truth until closure |
| **3** | Recovery Command Matrix Hardening | Convert every unsafe lifecycle state into one recovery command or one hard stop |
| **4** | Live Outcome Ledger Integration | Preserve each real ticket result as structured governance input |

## Non-Goals

This program must not:

- tune strategy entries or exits;
- add new StrategyGroups, symbols, or mirrored sides;
- lower or expand live profile authority;
- change default order sizing or leverage;
- create a new execution path outside FinalGate and Operation Layer;
- introduce current JSON/Markdown/report file readers;
- create recurring report files during no-signal or no-active-lifecycle ticks;
- turn Live Outcome Ledger rows into submit authority.

## Package 1: Scope Freeze Pre-Submit Gate

### Definition

A scope freeze is a current PG state saying:

```text
strategy_group_id + symbol + side has unresolved lifecycle or exchange-risk state
```

It must block new trade-intent formation for that exact scope while the risk is
current.

### Required Query

Create one typed service boundary:

```text
CapitalSafetyGuard.current_scope_status(strategy_group_id, symbol, side)
```

It returns:

| Field | Meaning |
| --- | --- |
| `scope_key` | `strategy_group_id + symbol + side` |
| `status` | `clear`, `frozen`, `cleanup_only`, or `unknown_risk` |
| `first_blocker` | Current blocker code when not clear |
| `risk_present` | True only when exchange/PG facts imply current capital risk |
| `cleanup_required` | True when stale local cleanup is required after current risk is disproved |
| `recovery_command_id` | Current command when available |
| `explanation_code` | Owner/read-model-safe reason code |

### Blocking Consumers

The guard must be consumed before:

| Consumer | Required behavior |
| --- | --- |
| Promotion projector | Do not create promotion for `frozen` or `unknown_risk` |
| Action-time lane arbitration | Do not select frozen scope |
| Action-Time Ticket issuer | Do not create ticket for frozen scope |
| Runtime Safety State projector | `submit_allowed=false` when frozen |
| FinalGate preflight materializer | Do not mark preflight ready when frozen |
| Protected submit attempt materializer | Do not create real submit attempt when frozen |
| Server monitor / Owner read model | Explain freeze in plain language |

### Blocker Vocabulary

Initial blocker codes:

```text
scope_frozen_for_lifecycle_recovery
scope_frozen_for_exchange_unknown_risk
scope_cleanup_pending_no_current_risk
scope_freeze_projection_stale
```

Only the first two block new trade intent. `scope_cleanup_pending_no_current_risk`
is visible but not submit-blocking after exchange truth proves flat/no-risk.

### Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| Active real-risk freeze blocks pre-submit path | Promotion, lane, ticket, safety, preflight, and submit tests all stop |
| No-risk stale residue does not block | Fixtures with stale local residue proceed after cleanup/outcome projection proves no current risk |
| Unknown exchange-only order is fail-closed | Matching scope freezes and notifies without cancel/adopt |
| Scope is exact | Other symbols/sides/StrategyGroups are not blocked |
| No file authority | Tests use PG/in-memory typed fixtures, not report JSON |

## Package 2: Continuous Reconciliation Tick

### Definition

Continuous reconciliation keeps ticket-bound PG state aligned with exchange
truth after the first tick:

```text
first_post_submit tick
-> scheduled / event tick
-> recovery_check tick
-> closed / recovered / hard_stopped
```

### Trigger Policy

| Trigger | Cadence |
| --- | --- |
| Real submit result recorded | Immediate first tick |
| Active lifecycle not terminal | Bounded periodic tick |
| Recovery command executed | Immediate recovery_check tick |
| TP1 fill or runner event observed | Event tick |
| No active lifecycle | No heavy reconciliation work |

### Snapshot Source

The production scheduler must collect exchange truth through official gateway
read methods only:

```text
open orders
recent fills
positions
account facts when needed
```

Snapshots must be compact PG facts or typed in-memory test values. They must
not be report files.

### State Outcomes

| Observation | Outcome |
| --- | --- |
| ENTRY accepted/open and SL/TP1 match | `matched` |
| ENTRY filled/open position and SL missing | `recovery_required:submit_missing_sl` |
| SL exists and TP1 missing | `recovery_required:submit_missing_tp1` |
| TP1 filled and runner SL missing | `recovery_required:replace_runner_sl` |
| Position flat and PG-linked protection still open | `cleanup_required:cleanup_pg_linked_orphan_protection` |
| Position flat and no open protection risk | `closed_or_cleanup_only` |
| Unknown exchange-only order present | `hard_attention:exchange_unknown_risk` |

### Performance Boundary

| Area | Rule |
| --- | --- |
| No active lifecycle | No exchange scan loop |
| Active lifecycle tick | Timeout-bounded gateway reads |
| PG writes | One tick row plus current projection update |
| Logs | Summary line only |
| Reports | Zero recurring JSON/MD report files |
| Retention | Keep lifecycle lineage; compact bulky snapshots |

## Package 3: Recovery Command Matrix Hardening

### Definition

Every unsafe non-terminal lifecycle state must map to exactly one:

```text
recovery command
or hard stop
```

### Command Matrix

| State | Command | Mutation allowed? | Safety rule |
| --- | --- | ---: | --- |
| ENTRY rejected, no position | `close_failed_ticket` | No | Close ticket, no freeze after clear |
| ENTRY unknown after timeout | `query_by_client_order_id` | No | Freeze until resolved |
| Position open, SL missing | `submit_missing_sl` | Yes | Existing ticket/position only |
| SL exists, TP1 missing | `submit_missing_tp1` | Yes | Existing ticket/position only |
| TP1 filled, runner SL missing | `replace_runner_sl` | Yes | Submit new runner SL before old SL cancel |
| New runner SL confirmed, old SL open | `cancel_old_sl_after_runner` | Yes | PG-linked old SL only |
| Flat position, PG-linked protection open | `cleanup_pg_linked_orphan_protection` | Yes | PG-linked reduce-only protection only |
| No current risk after stale local residue | `mark_cleanup_only_closed` | No | Must not block new trade |
| Unknown exchange-only order | `freeze_new_submits_for_scope` | No | Notify, no auto-cancel/adopt |
| Unsupported unsafe state | `mark_hard_stopped` | No | Requires Owner/developer intervention |

### Retry Rule

Recovery commands are ticket-bound and idempotent:

```text
same command
same ticket
same scope
max 3 attempts
then hard stop
```

Retries must not create duplicate ENTRY orders.

## Package 4: Live Outcome Ledger Integration

### Definition

Every real ticket that crosses submit boundary must produce either:

```text
one live outcome row
or one exact hard-blocked outcome row
```

### Creation Conditions

| Condition | Row type |
| --- | --- |
| Final exit and settlement complete | `lifecycle_closed` |
| Hard stop after exchange interaction | `hard_blocked_outcome` |
| Manual recovery closes incident | `recovered_outcome` |
| Ticket expires before submit boundary | No live outcome row required |
| Disabled smoke attempt | No live outcome row required |

### Required Bindings

Outcome rows must bind:

```text
ticket_id
strategy_group_id
symbol
side
runtime_profile_id
strategy_version_id
policy_version_id
signal_time_ms
entry / stop / TP1 / runner / final exit refs
fees / funding / realized PnL when available
lifecycle defects
review decision when available
```

### Authority Boundary

Live Outcome Ledger is governance input only:

```text
outcome may inform future Owner policy
outcome must not unlock submit
outcome must not bypass safety
outcome must not mutate strategy scope directly
```

## End-to-End State Machine

```text
pre_submit_clear
-> ticket_submitted
-> first_tick_matched | first_tick_recovery_required | first_tick_hard_attention
-> continuous_reconciliation
-> recovery_command_prepared
-> recovery_command_executed
-> recovery_check_tick
-> protected | cleanup_only | hard_stopped
-> lifecycle_closed
-> live_outcome_recorded
```

`cleanup_only` is not a trading hard blocker unless a current exchange risk
remains.

## Owner Explanation Requirements

| Internal state | Owner explanation |
| --- | --- |
| `scope_frozen_for_lifecycle_recovery` | This strategy/symbol/side has an unresolved protection or reconciliation risk, so new trades are paused for this scope |
| `scope_cleanup_pending_no_current_risk` | Old local records or stale projections need cleanup, but current facts show no live capital risk |
| `scope_frozen_for_exchange_unknown_risk` | The exchange shows an unknown live order/risk that the system will not guess or auto-cancel |
| `recovery_required:submit_missing_sl` | A position exists without the required stop protection, so the system is repairing protection |
| `cleanup_required:cleanup_pg_linked_orphan_protection` | The position is flat but a linked reduce-only protection order remains, so the system is cleaning it |
| `live_outcome_recorded` | The trade lifecycle has a structured result row for review |

## Validation Plan

### Focused Tests

| Test family | Required cases |
| --- | --- |
| Scope freeze gate | frozen scope blocks promotion/lane/ticket/safety/preflight/submit |
| No-risk cleanup | Stale local residue + current facts proving no live risk does not block new trade |
| Unknown risk | exchange-only unknown order freezes and notifies without cancel/adopt |
| Reconciliation | first/scheduled/recovery_check ticks reach matched/recovery/hard stop |
| Recovery commands | each matrix row maps to one command or hard stop |
| Outcome ledger | real submitted ticket creates one outcome or hard-blocked outcome |

### Impact Tests

| Scope | Requirement |
| --- | --- |
| Active 5 StrategyGroups | Non-frozen scopes remain eligible |
| Multi-symbol | Freeze one symbol does not freeze another symbol |
| Multi-side | Freeze short does not freeze long unless exchange risk requires it |
| No-signal cadence | No recurring report files and no heavy reconciliation work |
| File authority | `audit_production_runtime_file_io.py` remains clear |

### Required Commands

```text
python3 scripts/validate_current_docs_authority.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
python3 scripts/audit_production_runtime_file_io.py
```

Implementation branches must also run focused lifecycle and pre-trade tests
for the files they touch.

## Rollback Strategy

| Layer | Rollback |
| --- | --- |
| Scope freeze gate | Disable new gate projector only if it blocks clear scopes; do not bypass protected submit safety |
| Reconciliation scheduler | Stop scheduler/timer; keep PG lifecycle rows |
| Recovery command executor | Disable execution; leave command preparation/read model active |
| Outcome ledger | Stop materializer; do not delete existing outcome rows |

Rollback must not delete ticket, order, protection, reconciliation, recovery,
or outcome lineage.

## Acceptance

P0 capital safety closure is complete when:

| Requirement | Acceptance proof |
| --- | --- |
| **Frozen real-risk scope cannot submit again** | Every pre-submit consumer blocks matching active risk freeze |
| **No-risk stale residue does not block** | Current-risk-disproved test proceeds and records cleanup/outcome |
| **Continuous reconciliation is active** | Active lifecycle ticks until protected, recovered, closed, or hard stopped |
| **Recovery is deterministic** | Every unsafe state maps to one command or one hard stop |
| **Outcome is structured** | Every real submitted ticket has one outcome or hard-blocked outcome |
| **No file authority regression** | Strict file authority audits stay clear |
| **No performance regression** | No-signal and no-active-lifecycle ticks create zero JSON/MD reports and no heavy exchange work |

## Implementation Notes

As of the local `codex/p0-capital-safety-closure` branch:

| Package | Local state | Evidence |
| --- | --- | --- |
| **Scope Freeze Pre-Submit Gate** | Implemented | `capital_safety_guard` is consumed before promotion, lane, ticket, Runtime Safety State, FinalGate preflight, Operation Layer handoff, submit-mode decision, and protected submit |
| **Continuous Reconciliation Tick** | Implemented for current projection | `first_post_submit`, `scheduled`, and `recovery_check` tick kinds share the same PG materializer; `recovery_check` requires a post-recovery exchange snapshot |
| **Recovery Command Matrix Hardening** | Covered by existing recovery, runner, orphan cleanup, and failure-matrix tests | Recovery stays ticket-bound and idempotent; stale/no-risk residue is cleanup/outcome, not a new submit blocker |
| **Live Outcome Ledger Integration** | Implemented as PG projection | `brc_live_outcome_ledger` has one unique row per real submitted ticket; disabled smoke and pre-submit paths do not create outcome rows |

The remaining acceptance step is review, validation, commit, and Owner-approved
deployment. Deploy remains explicitly gated by Owner approval.

## Chain Position

```text
chain_position: post_submit_capital_safety_boundary
strategy_group_id: active 5 StrategyGroups
symbol: active candidate scopes
stage: P0 capital safety closure local implementation
first_blocker: review_validation_and_deploy_approval_pending
evidence: local branch implements scope freeze guard, scheduled/recovery reconciliation tick materialization, and Live Outcome Ledger PG projection with focused and impact tests
next_action: finish validation, self-review, commit, and wait for explicit Owner deployment approval
stop_condition: every real-risk frozen scope blocks new submit intent, stale local residue does not block after current risk is disproved, every active lifecycle continues reconciliation, and every real submitted terminal ticket produces one outcome row
owner_action_required: no
authority_boundary: no FinalGate bypass / no Operation Layer bypass / no exchange write outside official ticket-bound recovery / no live profile or sizing change
```
