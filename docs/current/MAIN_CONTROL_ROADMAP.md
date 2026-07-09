---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
authority: docs/current/MAIN_CONTROL_ROADMAP.md
last_verified: 2026-07-09
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
| 1 | **Operation Layer / Exchange Capability Boundary** | P0 | `docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md` |
| 2 | **Ticket-Bound Lifecycle Safety Core** | P0 | `docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md` |
| 3 | **Full Chain Simulation Harness** | P0 | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` and `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` |
| 4 | **Official Runner SL Mutation + Protection Reconciler** | P0 | `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` |
| 5 | **Post-Submit First Tick + Recovery Command Matrix** | P0 | `docs/current/POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md` |
| 6 | **Scope Freeze Pre-Submit Gate** | P0 | `docs/current/POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md` |
| 7 | **Live Outcome Ledger** | P0/P1 | `docs/current/LIVE_OUTCOME_LEDGER_CONTRACT.md` |
| 8 | **Continuous Reconciliation Tick** | P0/P1 | `docs/current/POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md` |
| 9 | **Risk Reservation v0** | P1 | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |
| 10 | **Owner Explanation Read Model** | P1 | `docs/current/OWNER_EXPLANATION_READ_MODEL_CONTRACT.md` |
| 11 | **Performance And Retention Control** | P1 | `docs/current/PRODUCTION_RUNTIME_FILE_IO_ELIMINATION_DESIGN.md` |
| 12 | **Frontend Read Model Integration** | P2 | frontend read-model contracts |
| 13 | **Advanced Capital Risk Allocation** | P2 | `docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md` |

## Current Verified Progress

| Area | Current fact |
| --- | --- |
| **Integration branch** | `dev` and `origin/dev` are aligned to `4b0b8a272814b2458fafc1913f8d7c63219ff321` |
| **Tokyo release** | Tokyo current release head is `4b0b8a272814b2458fafc1913f8d7c63219ff321` |
| **Deployment method** | Server-side `git fetch + git archive export`; no local upload package is required for normal deploy |
| **PG migration** | Tokyo is at `alembic=101` after post-submit first tick deployment |
| **Postdeploy acceptance** | Passed; warning only that release identity comes from `.brc-release-manifest.json` because git archive releases have no `.git` directory |
| **Backend / watcher / monitor** | Active after deploy verification |
| **Real gateway submit-boundary test** | Deployed `110e680c` includes local impact coverage proving constructed PG fresh signal can reach `real_gateway_action -> gateway.place_order(...)` boundary with controlled test-gateway stop |
| **Post-submit first tick** | Deployed `4b0b8a27` includes `brc_ticket_bound_reconciliation_ticks`, `brc_ticket_bound_scope_freezes`, first post-submit tick selection, TP1 degraded recovery, retry limit, and scope freeze writes |
| **Current first blocker** | `scope_freeze_pre_submit_gate_missing`; scope freeze rows exist, but active freezes must still become hard blockers before promotion, lane, ticket, Runtime Safety State, FinalGate preflight, and protected submit |

## Current Next Execution Order

This is the current remaining order after Tokyo release `4b0b8a27`.

| Order | Work | Priority | Done when |
| --- | --- | --- | --- |
| 1 | **Scope freeze pre-submit hard blocker** | P0 | Active scope freeze blocks matching `strategy_group_id + symbol + side` before promotion, lane, ticket, Runtime Safety State, FinalGate preflight, and protected submit |
| 2 | **Live Outcome Ledger** | P0 | Every real ticket has one structured outcome row or one exact hard-blocked outcome row |
| 3 | **Continuous reconciliation tick** | P0 | After first tick, scheduled/event-driven reconciliation continues until lifecycle closure, exact recovery command, or hard stop |
| 4 | **Risk-at-stop reservation** | P1 | Ticket computes and reserves `risk_at_stop = abs(entry_price - stop_price) * quantity` before FinalGate-ready submit |
| 5 | **Owner Explanation Read Model** | P1 | Owner sees waiting, processing, blocked, protected, recovered, and closed states without decoding internal blocker codes |
| 6 | **Frontend read-model integration** | P2 | Frontend only displays backend explanation/read models and does not infer blockers, facts, lanes, tickets, or submit authority |
| 7 | **Trading quality / capital budget / portfolio risk model** | P2 | Advanced allocation improves exposure quality without weakening per-ticket safety, stop-risk reservation, or lifecycle reconciliation |

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
| **P0-G** | **Post-submit first tick and recovery command determinism** | immediate exchange-truth first tick and one recovery command or hard stop for every unsafe lifecycle blocker | every real protected submit result reaches matched/protected, pending visibility, deterministic recovery command, or exact hard stop |
| **P0-H** | **Live outcome ledger** | real tickets become structured result and learning rows | every real ticket has one outcome row or one exact hard-blocked outcome |
| **P0-I** | **Scope freeze pre-submit gate** | active lifecycle/reconciliation freeze blocks the same StrategyGroup + symbol + side before another submit path can form | promotion, lane, ticket, Runtime Safety State, FinalGate preflight, and protected submit all reject frozen scopes |
| **P0-J** | **Continuous reconciliation tick** | keep exchange-truth reconciliation alive after the first tick | lifecycle reaches closure, exact recovery command, or hard stop without recurring report files |

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
