---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
authority: docs/current/MAIN_CONTROL_ROADMAP.md
last_verified: 2026-07-08
---

# Main Control Roadmap

## Purpose

This roadmap is the current planning surface for the **StrategyGroup
pre-trade runtime**.

It is not a historical packet index, report catalogue, or proof-chain archive.
Historical roadmap material belongs in archive-only recovery records. Current
work must follow:

```text
PG/current services decide.
Generated JSON/MD exports summarize.
Archives preserve provenance only.
```

## Current Direction

The current mainline target is:

```text
five active StrategyGroups
-> multiple candidate symbols per StrategyGroup
-> PG-backed watcher coverage and fact snapshots
-> PG-backed readiness / promotion / action-time lane rows
-> PG Action-Time Ticket identity
-> ticket-bound Runtime Safety State / FinalGate / Operation Layer handoff
-> protected submit only inside official boundaries
-> protection / reconciliation / settlement / review
```

The system must not depend on repo MD/JSON, `output/**`, or report-dir JSON as
runtime or trading decision sources.

The program-level execution map for the next engineering phase is
`docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`. That document is the
current ordering surface for large workstreams and links each program to its
design documents and acceptance proof.

## Current Program Order

| Order | Program | Priority | Primary design surface |
| --- | --- | --- | --- |
| 1 | **Operation Layer / Exchange Capability Audit** | P0 | `docs/current/OPERATION_LAYER_EXCHANGE_CAPABILITY_AUDIT.md` |
| 2 | **Ticket-Bound Lifecycle Safety Core** | P0 | `docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md` |
| 3 | **Full Chain Simulation Harness** | P0 | `docs/current/L1_L9_OPTIMIZATION_EXECUTION_PLAN.md` |
| 4 | **Official Runner SL Mutation + Protection Reconciler** | P0 | `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` |
| 5 | **Live Outcome Ledger** | P0/P1 | `docs/current/LIVE_OUTCOME_LEDGER_CONTRACT.md` |
| 6 | **Risk Reservation v0** | P1 | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |
| 7 | **Owner Explanation Read Model** | P1 | `docs/current/OWNER_EXPLANATION_READ_MODEL_CONTRACT.md` |
| 8 | **Performance And Retention Control** | P1 | `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` |
| 9 | **Advanced Capital Risk Allocation** | P2 | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |
| 10 | **Frontend Read Model Integration** | P2 | frontend read-model contracts |

## Current Verified Progress

| Area | Current fact |
| --- | --- |
| **Integration branch** | `dev` and `origin/dev` are aligned to `4f813a16e32930fefb67590283d041b1fead207f` |
| **Tokyo release** | Tokyo current release head is `4f813a16e32930fefb67590283d041b1fead207f` |
| **Deployment method** | Server-side `git fetch + git archive export`; no local upload package is required for normal deploy |
| **PG migration** | Tokyo is at `alembic=097` after lifecycle migration repair |
| **Postdeploy acceptance** | Passed; warning only that release identity comes from `.brc-release-manifest.json` because git archive releases have no `.git` directory |
| **Backend / watcher / monitor** | Active after deploy verification |
| **Recent market/action events** | No recent signal, promotion, lane, ticket, or attempt after the latest postdeploy health check |
| **Current first blocker** | `no_recent_fresh_signal` for live action; back-half local engineering first blocker moves to `full_chain_failure_matrix_not_complete` after the orphan protection cleanup command branch |

## Authority Boundary

| Layer | Current authority | Not authority |
| --- | --- | --- |
| Strategy semantics | PG strategy registry/current versions | historical handoff JSON as runtime source |
| Owner policy | PG owner policy events/current projection | repo policy JSON as runtime source |
| Candidate universe | PG candidate scopes and runtime scope bindings | Candidate Pool JSON export |
| Facts | PG runtime fact snapshots | `latest-*facts.json` exports |
| Readiness/promotion | PG readiness rows and promotion candidates | Daily Table / Candidate Pool JSON exports |
| Action-time identity | PG action-time lane and Action-Time Ticket rows | resume pack or dispatch JSON identity |
| Safety | Runtime Safety State over PG/current facts | dry-run audit or closure evidence file |
| Owner explanation | backend read model over current projections | frontend or MD/JSON self-interpretation |

## Current P0 Workstreams

| Priority | Workstream | Goal | Done when |
| --- | --- | --- | --- |
| **P0-A** | **File-authority elimination** | remove production/current reads from repo MD/JSON, `output/**`, and report-dir proof files | validators reject reintroduced runtime file authority |
| **P0-B** | **PG current projection closure** | make Goal Status, Candidate Pool, Daily Table, Runtime Safety State, Action-Time Ticket, and Owner Explanation read from PG/current services | one owner projector per current projection |
| **P0-C** | **Action-time ticket path** | fresh satisfied signal becomes one explicit PG Action-Time Ticket before FinalGate / Operation Layer | ticket identity contains StrategyGroup, symbol, side, profile, policy versions, facts, risk scope |
| **P0-D** | **Server monitor ownership** | server-side readonly monitor classifies quiet / notify from PG/current state | no production dependency on local heartbeat or local cache |
| **P0-E** | **Performance and retention** | no-signal ticks stay quiet and bounded in disk / CPU / PG rows | report growth and restart storms are structurally prevented |
| **P0-F** | **Ticket-bound lifecycle hardening** | post-submit lifecycle state machine, runner mutation, protection reconciliation, and failure recovery remain one safety core | every submitted ticket reaches protected/closed state or one exact lifecycle hard blocker |
| **P0-G** | **Live outcome ledger** | real tickets become structured result and learning rows | every real ticket has one outcome row or one exact hard-blocked outcome |

## Active Runtime Loop

```text
StrategyGroup candidate scope
-> watcher coverage
-> public/account/action-time facts
-> per-symbol readiness row
-> promotion candidate
-> single action-time lane
-> Action-Time Ticket
-> Runtime Safety State
-> FinalGate
-> Operation Layer
-> protected submit
-> post-submit lifecycle
-> review outcome
```

## Blocker Language

Current planning must use blocker classes from
`docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`.

Valid current conclusions include:

| State | Meaning |
| --- | --- |
| `market_wait_validated` | system is ready for that lane and only current market event is absent |
| `computed_not_satisfied` | detector/watcher/facts ran, but strategy facts are false |
| `scope_not_attached` | strategy/symbol/side is not bound to runtime scope |
| `action_time_boundary_not_reproduced` | fresh/live-like event cannot reach action-time chain |
| `execution_gate_gap` | official safety/execution gate blocks submit |
| `hard_safety_stop` | exchange write would violate a hard boundary |

Generic `waiting_for_market`, stale proof-chain files, or dry-run audit pass
must not stand in for current tradeability.

## Deleted Current Paths

These names are no longer current runtime surfaces:

```text
runtime_dry_run_audit_chain.py
runtime_execution_chain_closure_status.py
runtime_live_cutover_readiness.py
runtime_live_closure_evidence*.json
runtime_first_bounded_live_order_completion_audit.py
run_strategygroup_runtime_local_monitor_sequence.py
run_strategygroup_runtime_goal_progress_audit.py
```

If historical evidence is valuable, preserve it only as archive/provenance. Do
not reintroduce these names as production blockers, readiness checks, Owner
surfaces, or file inputs.

## Non-Negotiable Constraints

1. **No production runtime decision from repo MD/JSON**.
2. **No production runtime decision from `output/**` latest files**.
3. **No production runtime decision from dry-run / closure evidence files**.
4. **No fallback chain that silently revives old file authority**.
5. **No frontend interpretation of blockers, facts, lanes, tickets, or submit authority**.
6. **No FinalGate, Operation Layer, exchange write, live profile, or sizing expansion through cleanup work**.

## Near-Term Acceptance

The next stable checkpoint is:

```text
server watcher and monitor run from PG/current state
-> no-signal tick has bounded writes
-> fresh signal creates PG promotion / lane / ticket rows
-> Action-Time Ticket can continue through lifecycle-safe protected submit
-> TP1 / runner / final-exit lifecycle states are reconciled against exchange truth
-> real submitted tickets produce Live Outcome Ledger rows
-> Risk Reservation v0 records stop-risk before FinalGate-ready state
-> Owner Explanation can explain why no trade, why blocked, or what happened after submit
-> old MD/JSON proof-chain readers are deleted or archive-only
-> validators prevent regression
```
