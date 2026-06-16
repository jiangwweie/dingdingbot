---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
authority: docs/current/MAIN_CONTROL_ROADMAP.md
last_verified: 2026-06-16
---

# Main Control Roadmap

## Purpose

This is the short planning table for the main runtime window.

The main goal is still the StrategyGroup runtime pilot:

```text
Owner enables a StrategyGroup.
The system observes, checks, executes inside official boundaries, protects,
reconciles, settles, records, and reports Owner-readable state.
```

This file is not a research backlog, frontend design spec, or historical packet
index.

## Current Tracks

| Track | Owner outcome | Current owner | Current status | Next checkpoint |
| --- | --- | --- | --- | --- |
| P0 Runtime Product State Repair | Owner Console can read one stable source-readiness state instead of interpreting packets | Main runtime window | active | Produce `owner-console-source-readiness.json` and `GET /api/trading-console/owner-console-source-readiness` |
| P0 Runtime Pilot Liveness | Fresh signal can continue to candidate/auth/FinalGate/Operation Layer evidence prep without accidental watcher-side attempt burn | Main runtime window | active | Rerun fresh signal chain through standing-authorized evidence prep, action-time FinalGate, and official Operation Layer only |
| P0 Runtime Dry-Run Audit Chain | Main chain can expose evidence/endpoint/gate breakage without waiting for market opportunity | Main runtime window | queued | Produce `runtime-dry-run-audit-chain.json` after deploy liveness repair |
| P0 Safe Tokyo Operations | Tokyo watcher stays current, alive, bounded, and auditable | Main runtime window | active | Verify watcher reports and bounded deploys after each runtime-code change |
| P1 Owner Console Mainline Stabilization | Owner sees simple state, not raw gate vocabulary | Main runtime window | mainline integrated | Keep source-readiness API/packet stable while UI refinements continue from the mainline contract |
| P1 StrategyGroup Research Handoff | Strategy research enters main control only through reviewed handoff packs | Strategy research window | active separately | Keep research artifacts out of main runtime worktree except reviewed handoff input |
| P2 Historical Debt Reduction | Historical docs/code do not obscure current pilot behavior | Main runtime window | pending | Compress/archive only after P0 source and runtime state are stable |
| P2 LLM Assistance | LLM supports audit/readiness/notification without changing execution authority | Main runtime window | pending | Start with read-only audit summaries and Feishu notification text only |
| P2 External Information Capture | External information can inform research/watch context without becoming execution authority | Strategy/research window first | pending | Treat as research input, not live-submit permission |

## P0 Subgoal: Owner Console Source Readiness Productization

### Current State

Owner Console exploration is no longer treated as an isolated authority source.
The main runtime branch now owns the source-readiness contract and exposes the
machine-readable packet/API that the console consumes.

### Scope

Build one stable Owner Console source-readiness surface from main runtime facts:

```text
StrategyGroup catalog
runtime pilot status
watcher status
live facts readiness
account funds
orders
positions
protection
reconciliation detail state
operation audit detail state
```

### Required Artifacts

| Artifact | Path |
| --- | --- |
| Human confirmation | `docs/current/OWNER_CONSOLE_SOURCE_READINESS_CONFIRMATION.md` |
| Machine-readable packet | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/owner-console-source-readiness.json` |
| API surface | `GET /api/trading-console/owner-console-source-readiness` |
| Watcher refresh hook | `scripts/refresh_strategygroup_runtime_product_state_packets.py` |

### Acceptance

| Requirement | Expected result |
| --- | --- |
| StrategyGroup catalog ready | Owner Console can show MPG / TEQ / FBS / PMR / SOR even if runtime overlay degrades |
| Runtime source reachable | Source status is `ready` or `degraded`, not an empty strategy list |
| Orders source readable and empty | Source status is `ready_empty`, Owner language is `暂无订单` |
| Positions source readable and empty | Source status is `ready_empty`, Owner language is `暂无持仓` |
| Account facts readable | Source status is `ready`, Owner language is `资金正常` |
| Watcher waiting for signal | Owner state is `waiting_for_opportunity`, Owner language is `等待机会` |
| Reconciliation/audit detail missing | Detail degrades without hiding StrategyGroups |
| Safety | No order, exchange write, FinalGate bypass, Operation Layer bypass, secret mutation, profile expansion, sizing change, withdrawal, or transfer |

## P0 Subgoal: Runtime Liveness Repair

### Current State

The watcher has reached the post-signal boundary where the fresh StrategyGroup
signal, candidate, grant, authorization, and FinalGate preview can exist, but
the official Operation Layer submit path still depends on prepared evidence
IDs. The previous blocker language was still tied to old per-chat Owner
confirmation for attempt consumption and local registration.

### Correct Current Path

```text
fresh signal
-> standing-authorized scoped evidence preparation
-> action-time FinalGate
-> official Operation Layer action only
-> post-submit finalize / reconciliation / budget settlement
```

### Acceptance

| Requirement | Expected result |
| --- | --- |
| Default arm preview | Still stops before attempt consumption |
| Standing evidence prep | Records bounded attempt/local-registration/exchange-arm evidence only when explicitly enabled |
| Disabled smoke | Can prove the action endpoint without exchange write |
| FinalGate | Must rerun at action time before real Operation Layer action |
| Operation Layer | Must use official endpoint and required evidence IDs |
| Safety | No secret mutation, profile expansion, sizing change, withdrawal, transfer, stale-fact execution, duplicate submit, or conflicting position/order execution |

## P0 Subgoal: Runtime Dry-Run Audit Chain

### Purpose

The real market path should not be the only way to discover evidence relay,
FinalGate, Operation Layer, or source-readiness breakage. A dry-run audit chain
must exercise the same semantics without creating real orders or exchange
writes.

### Target Chain

```text
mock fresh signal
-> RequiredFacts readiness
-> candidate / authorization evidence
-> action-time FinalGate dry-run / preflight
-> Operation Layer evidence prep
-> disabled submit smoke
-> fake or non-executing post-submit finalize shape check
-> unified audit packet
```

### Required Artifact

| Artifact | Path |
| --- | --- |
| Unified audit packet | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/runtime-dry-run-audit-chain.json` |

### Scenario Matrix

| Scenario | Expected result |
| --- | --- |
| No signal | `waiting_for_signal`; no candidate, authorization, FinalGate, or Operation Layer |
| Mock fresh signal pass | Evidence IDs connect; dangerous action flags remain false |
| RequiredFacts missing | Clear `missing_fact` blocker before Operation Layer |
| Active position or open-order conflict | Clear conflict blocker before FinalGate or Operation Layer action |

### Safety

The dry-run chain must not call exchange write, create real orders, mutate
secrets, mutate live profile, expand order sizing, create withdrawals or
transfers, treat disabled smoke as real execution proof, or mark missing
evidence as ready.

## Boundaries

- Keep UI experiments outside mainline until reviewed, but the Owner Console
  source-readiness contract is now mainline-owned in `/Users/jiangwei/Documents/final`.
- Keep strategy research in `/Users/jiangwei/Documents/final-strategy-research`.
- Keep main runtime work in `/Users/jiangwei/Documents/final`.
- Do not expose internal gate names as Owner homepage labels.
- Do not treat weak strategy evidence as a live-safety blocker.
- Do not treat missing audit detail as a reason to hide StrategyGroups.
