---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-07-30
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
| Branch | `codex/strategy-universe-operability-repair-20260729` |
| Production commit | `6d8e0c8f56bd91b37e96db4ea4c819ccf7e65885` |
| Production tag | `tokyo-runtime-2026.07.30.1`; annotated, immutable, and verified on `origin` |
| Production-commit certification | `759 passed`; full-repository Ruff, Mypy, runtime file-I/O and diff checks pass |
| Local clean-rebuild rehearsal | Empty PostgreSQL baseline, six-Event bootstrap, Entry-promotion rehearsal and repeatability all completed without Tokyo or exchange mutation |
| Runtime ownership | Observation, Entry, Lifecycle, and Reconciliation are active at zero restarts |
| Scheduling model | Long-running systemd services; timer-based Python cold starts are retired and must not return |
| PostgreSQL | Destructive flat-only cutover completed: `public` was rebuilt from `0001_trading_kernel_baseline_v2`; Registry, Policy, Capability and exact runtime identity match the production commit |
| StrategyUniverse deployment | Six current Active Universes, 42 Active Scopes and seven approved instruments: BTC, ETH, SOL, BNB, XRP, DOGE and ADA; zero Warming Universe; AVAX excluded |
| Strategy capability | Six registered Events, deterministic detectors, closed-candle Observation, Live/Replay parity, and real StrategySignal production |
| Ticket capability | CapacityClaim, immutable Ticket, budget reservation, Netting Domain hold, event, aggregate, and durable ENTRY command commit atomically |
| Dynamic policy | Three concurrent Tickets; `0.03` planned stop risk; demand-based remaining margin; fixed exchange `5x`; max `10x` safety ceiling; `cross` margin |
| Entry authority | `new_entry_submit_enabled` applies only before ENTRY; existing exposure retains frozen safety authority |
| Runtime fence | Commit/schema drift records an Incident; an exact but disabled command capability is a controlled readonly fence, not an Incident |
| Historical runtime/trade facts | Reset after verified exchange-flat state by explicit Owner authorization; no historical Ticket, command, Incident, Review, position, reservation, or observation fact remains as runtime authority |
| Terminal-recovery repair | Exact cancel namespace/purpose, atomic Ticket-incident closure, and external-flat unavailable Review are deployed in the active Kernel |
| Current live acceptance | Entry was promoted only after six Active Universes, seven fresh certifications, internal flatness, external flatness and all four healthy Workers. No natural acceptance Ticket has yet occurred |
| Exchange postflight | Account is `independent_sides` and `cross`; all seven approved instruments are `5x`; zero position domains and zero open-order domains |
| Short post-release observation | Four Workers active at zero restarts; Entry unfenced; zero Ticket, Exchange Command and open Incident |
| Full capability | `promote-full` not yet completed |

## Current Performance Snapshot

The following short readonly post-release sample was captured on 2026-07-30.
It verifies release stability, not a full host-capacity benchmark.

| Area | Measured state | Contract interpretation |
| --- | --- | --- |
| Worker stability | Four services active; restart count zero for each | No restart-loop evidence |
| Entry authority | Policy version `2`, command capability enabled and fence absent | Promotion completed through official path |
| Internal truth | Zero Ticket, Exchange Command and open Incident | No residual deployment work |
| External truth | Zero positions and zero open orders; seven instruments at `5x`, `cross`, independent sides | Current deployment flatness gate passes |
| Scheduling | Four persistent services; no timer worker introduced | Matches persistent-worker contract |

The snapshot source is readonly host, systemd, process, filesystem, and Docker
state. It does not authorize a deployment or exchange mutation.

The full host-capacity benchmark must be repeated after a representative idle
window; this short deployment observation does not replace it.

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
