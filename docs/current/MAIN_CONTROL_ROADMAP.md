---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-10-13
---

# Main Control Roadmap

## Final Target

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

One PostgreSQL-backed kernel serializes new ENTRY while protected Tickets
continue concurrently across independent Netting Domains.

## Current Verified State

### Dynamic engineering repair deployed; complete activation remains pending

| Area | Directly verified state |
| --- | --- |
| Integration branch | `dev` |
| Repair branch | `codex/dynamic-close-handover` in isolated worktree; main workspace remains clean `dev` |
| Snapshot time | 2026-10-13 18:00-18:04 Asia/Shanghai; bounded PostgreSQL, service and journal reads after deployment |
| Production commit | `57ad9fcc6ac86a88e0fd6f468c9ccb5f38d4205a` |
| Production tag | `tokyo-runtime-2026.10.13.2`; local immutable annotated tag points to exact runtime commit; no remote publication claimed |
| Production-commit certification | Exact R3 PASS: 1,618 Unit/Architecture, 1,655 Integration, 54 Full-chain; Ruff, Mypy193 and diff PASS. Exact R2 Owner API certification PASS |
| Kernel / schema | Kernel and API identify the exact production commit; Alembic/runtime schema `0010_dynamic_intent_v1`; this repair is same-schema R3. Earlier `0009_capacity_policy_v0` ->0010 function migration preserved original Dynamic authorization |
| Seed / Registry | Seed `sha256:896c67c4b7df31b42d02272fe4468c0383d44186606275ef5978986a4c5320c6`; exact source/target integrity and preservation gates PASS |
| Owner controls | Policy version `21` has `new_entry_submit_enabled=true`; genuine Resume/TOTP proof retained. Capacity B and capital, stop-risk, margin, leverage and strategy scope unchanged |
| Runtime ownership | Observation, Entry, Lifecycle, Reconciliation and API active; Entry fence absent; official promoter returned `promoted`; all five NRestarts0 at18:03 |
| Owner API / Console | Exact R2 API deployment and smoke PASS; static frontend was not redeployed in this backend repair |
| Entry restoration | Official same-schema deployment then `promote_entry.py`; no extra Policy write or Owner TOTP required |
| Dynamic Selection postflight | All four selectors have successful 24-Ready Snapshots. CPM first activated13:06 and remains Dynamic but is now under FALLBACK_PREVIOUS recovery after a failed old attempt. MPG/MI/BRF2 remain Static with original pending Dynamic intent. MPG/MI next period is DESIRED without Vacuum; complete four-family takeover is NOT PASSED |
| PostgreSQL activity | Latest flat deployment gate17:51: zero active Tickets, positions, commands and incidents; current recovery readiness PASS. This snapshot is not an assurance that later authorized runtime remains flat |
| Exchange postflight | Official deployment probes confirmed no exposure/open orders, independent sides, cross margin and configured leverage5. No manual exchange mutation or flatten was dispatched |
| ExitProfile postflight | Existing frozen Profile authority retained by exact source/target deployment preservation checks; no Profile switch or retirement performed |
| SOR retirement | Crypto SOR remains permanently Entry-disabled; TradFi SOR remains paused. Historical Dynamic metadata is not permission to resume |
| Deferred evidence | Full long-run soak, offline MAE/MFE projector, full GS-13 acceptance and new Generic live economics remain unclaimed |

Sources: exact local certification manifests; official Kernel R3 deployment
PASS, Owner API R2 deployment/smoke PASS, official Entry promotion; fresh Tokyo
PostgreSQL, systemd and journal inspection. Documents are not runtime authority.

### Current Dynamic acceptance boundary

| Strategy | Selection result | Actual mode and authority | Remaining evidence |
| --- | --- | --- | --- |
| CPM | Ready24 / selected16 | Dynamic; FALLBACK_PREVIOUS after old target failed | Real recovery rebase and later successful period takeover |
| MPG | Ready24 / selected16 at current snapshot | Static; original Dynamic intent; DESIRED, no Vacuum | Real rebase, unconsumed close, successful current Universe/Authority |
| MI | Ready24 / selected16 | Static; original Dynamic intent; DESIRED, no Vacuum | Real rebase, unconsumed close, successful current Universe/Authority |
| BRF2 | Ready24 / selected16 | Static; original Dynamic intent; FALLBACK_PREVIOUS, no Vacuum | Real rebase and later legal four-hour period takeover |

18:00 production journals prove real Observation and current-fact refresh have
resumed. Old attempts were cleaned by the existing timeout/recovery path, without
manual data repair. Recovery requires an actual future NOT_TRIGGERED close on
the overlapping members; Snapshot success, DESIRED or process liveness alone is
not activation success. No unconditional guarantee for the next period is made.

At18:03, actual recovery checkpoints were ARMED on MPG5/7, MI2/7, BRF24/7
and CPM9/16 members. This is partial recovery progress, not full takeover.

## Repair Evidence

Production evidence identified and local regressions repaired these defects:

1. Old Static Observation consumed selected members' due close before queued
   first Dynamic activation. Exact same-epoch precommitted current Snapshot now
   coordinates observation deferral and bounded retry; born Signals keep their
   existing authority path.
2. Switching Vacuum opened before prior recovery checkpoints were ARMED, blocking
   the very recovery observations needed to progress. DESIRED now checks actual
   recovery and unconsumed close before taking the slot or opening Vacuum.
3. Consumed-close or unarmed-recovery queue heads starved eligible work. Bounded
   eligible FIFO filtering preserves the single warming slot and Owner pause.
4. Reconciliation and activation locked Certification/Instrument in opposite
   order, producing the16:12 production deadlock. Both use Instrument then
   Certification in canonical order; real PostgreSQL concurrency test PASS.
5. STAGED members were excluded by both certification scheduler preview and
   claim, causing CERTIFICATION_STALE while waiting. Both now refresh those
   members through the existing readonly certification path. Regression proves
   no activation, Observation permission, Entry permission or Exchange Command.

No schema change, SQL repair, forged ARMED, consumed-close reuse, timeout
extension, capital expansion or safety-boundary bypass. Original Owner intents
and terminal lineage remain preserved.

## Remaining Critical Path

1. Prove each family's real current-epoch Universe/Authority takeover after
   recovery and the next legal boundary; current complete activation gate is open.
2. Follow naturally admitted Tickets through protection, exit, reconciliation,
   settlement and review without forced trades or risk expansion.
3. Keep long-run evidence, offline projector and complete live economics deferred.

## Current Stop Conditions

No exchange write under wrong identity, stale/contradictory action-time facts,
unknown outcome, same-domain occupancy, missing stop/budget, schema mismatch or
old-writer overlap. Existing exposure retains its frozen lifecycle. Crypto SOR
must remain Entry-disabled. No manual repair of recovery/cursors to manufacture
activation evidence.

## Historical Evidence

Prior roadmap snapshots are preserved in
[historical roadmap](../archive/2026-10-12-main-control-roadmap-history.md).
Historical PASS belongs only to its exact candidate and scope. The earlier
repository publication `release-2026.10.12.1` is not this server deployment.
