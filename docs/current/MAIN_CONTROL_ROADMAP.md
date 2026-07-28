---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-07-28
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

The target remains one complete multi-StrategyGroup, multi-position trading
system. New ENTRY admission is globally serialized; protected Tickets in
different Netting Domains progress concurrently.

## Current Verified State

| Area | Verified state |
| --- | --- |
| Branch | `codex/trading-kernel-rebuild-20260722` |
| Production commit | `1365356797b350f00c345b9f6e66915a0ad53097` |
| Production tag | `tokyo-runtime-2026.07.28.1`; annotated, immutable, and verified on `origin` |
| Production-commit certification | `427 passed`; architecture checks and production file-I/O audit pass |
| Runtime ownership | Observation, Lifecycle, and Reconciliation are active at zero restarts; Entry is intentionally fenced during runner-recovery observation |
| Scheduling model | Long-running systemd services; timer-based Python cold starts are retired and must not return |
| PostgreSQL | The guarded flat-runtime reset removed all prior runtime/trade facts after exchange-flat verification; Registry, Policy, Capability, schema metadata, and the 33-table `0001_initial` baseline remain authoritative |
| Strategy capability | Six registered Events, deterministic detectors, closed-candle Observation, Live/Replay parity, and real StrategySignal production |
| Ticket capability | CapacityClaim, immutable Ticket, budget reservation, Netting Domain hold, event, aggregate, and durable ENTRY command commit atomically |
| Dynamic policy | Three concurrent Tickets; `0.03` planned stop risk; demand-based remaining margin; fixed exchange `5x`; max `10x` safety ceiling; `cross` margin |
| Entry authority | `new_entry_submit_enabled` applies only before ENTRY; existing exposure retains frozen safety authority |
| Runtime fence | Commit/schema drift records an Incident; an exact but disabled command capability is a controlled readonly fence, not an Incident |
| Historical runtime/trade facts | Reset after verified exchange-flat state by explicit Owner authorization; no historical Ticket, command, Incident, Review, position, reservation, or observation fact remains as runtime authority |
| Terminal-recovery repair | Exact cancel namespace/purpose, atomic Ticket-incident closure, and external-flat unavailable Review are deployed in the active Kernel |
| Current live acceptance | AVAXUSDT `SOR-001 / SOR-SHORT` remains `position_protected`; BTCUSDT and SOLUSDT completed TP1 and are `runner_protected`. BTC runner Stop moved from `64624.6` to `63729.5`; SOL runner Stop moved from `75.47` to `74.17`. All three Tickets have zero open Incident and zero unresolved command. One ETHUSDT short ENTRY was authoritatively rejected for `wallet_risk_drift` and created no position |
| Exchange postflight | Three Netting Domains are non-flat and protected: AVAX retains Stop plus TP1; BTC and SOL retain exact runner Stops after their original full-quantity Stops were cancelled. The other nine domains are flat; all six supported instruments are configured at `5x` |
| Hourly supervision | Observation, Lifecycle, and Reconciliation are active at zero restarts; Entry is intentionally fenced while the recovered runners are observed, and current capacity remains occupied by the three protected Tickets |
| Full capability | `promote-full` not yet completed |

## Current Performance Snapshot

The following readonly post-release sample was captured on 2026-07-24. It is a
measured snapshot, not a replacement for the limits in
`TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`.

| Area | Measured state | Contract interpretation |
| --- | --- | --- |
| Host CPU | 2 vCPU; load average `0.10 / 0.10 / 0.12` | Substantial idle headroom |
| Host memory | 3.3 GiB total; about 1.8 GiB available; no swap | Above the 1 GiB review boundary; no swap remains a host risk |
| BRC worker slice | 1 CPU quota; 1 GiB maximum; about 450 MiB current | About 44% of memory limit |
| Idle worker CPU | About 0.61% of one CPU over a 10-second sample | Indicative headroom; future comparisons must state sample duration |
| Slice tasks | 6 of 128 | Below the 50% review boundary |
| Worker stability | Four services active; restart count zero for each | No restart-loop evidence |
| PostgreSQL container | About 45.6 MiB memory and 0.10% CPU | Small relative to host capacity |
| Filesystem | 53% used; about 27 GiB available | Below the 80% review boundary |
| Scheduling | Observation/Reconciliation 5-second polls; Entry/Lifecycle 2-second polls; no BRC timer | Matches persistent-worker contract |

The snapshot source is readonly host, systemd, process, filesystem, and Docker
state. It does not authorize a deployment or exchange mutation.

The current host is sufficient for the observed middle/low-frequency workload.
Performance acceptance must be repeated after runtime, dependency, cadence,
instrument-scope, or server-size changes.

## Remaining Critical Path

| Order | Work | Exit condition |
| ---: | --- | --- |
| 1 | Protected lifecycle | A new natural acceptance Ticket reaches terminal state through the official Lifecycle worker |
| 2 | External truth closure | Exchange is flat and has no residual ENTRY, protection, TP, EXIT, or cancel order |
| 3 | Internal truth closure | Ticket terminal, budget released, Netting Domain released, Reconciliation matched |
| 4 | Economics closure | Settlement and Review persist exact realized economics, including explicit funding availability |
| 5 | Incident audit | Zero open runtime incident and zero unknown command outcome |
| 6 | Full policy promotion | Run and certify `promote-full` only after steps 1-5 pass |
| 7 | Final requirement audit | Re-run local and Tokyo evidence and close every acceptance item |

## Current Stop Conditions

Exchange writes remain fail-closed for wrong identity, invalid account mode,
stale or contradictory facts, same-domain occupancy, missing budget or Initial
Stop, duplicate or unknown command outcome, schema/code mismatch, old-writer
overlap, or official-path bypass.

The rebuild is not complete merely because Tokyo is deployed or Observation is
healthy. Completion requires one new natural acceptance Ticket, terminal
flatness, no residual orders,
released budget, successful Reconciliation, Settlement, Review, zero Incident,
certified `promote-full`, and the final requirement audit.
