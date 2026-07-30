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
| Production commit | `8b8bddc818aa6bc961336390fccde6c10f3d7837` |
| Production tag | `tokyo-runtime-2026.07.30.3`; annotated, immutable, and verified on `origin` |
| Production-commit certification | `765 passed`; Ruff, Mypy (89 source files), runtime file-I/O audit and diff checks pass |
| Local clean-rebuild rehearsal | Empty PostgreSQL baseline, six-Event bootstrap, Entry-promotion rehearsal and repeatability all completed without Tokyo or exchange mutation |
| Runtime ownership | Observation, Lifecycle and Reconciliation are active at zero restarts; Entry is disabled and write-fenced during protected-Ticket handover |
| Scheduling model | Long-running systemd services; timer-based Python cold starts are retired and must not return |
| PostgreSQL | Destructive flat-only cutover completed: `public` was rebuilt from `0001_trading_kernel_baseline_v2`; Registry, Policy, Capability and exact runtime identity match the production commit |
| StrategyUniverse deployment | Six current Active Universes, 42 Active Scopes and seven approved instruments: BTC, ETH, SOL, BNB, XRP, DOGE and ADA; zero Warming Universe; AVAX excluded |
| Strategy capability | Six registered Events, deterministic detectors, closed-candle Observation, Live/Replay parity, and real StrategySignal production |
| Cross-margin bracket coverage | Finite Binance maintenance-margin terminal brackets are accepted only when every candidate stress evaluation point is covered; an out-of-range point remains an explicit fail-closed rejection |
| Ticket capability | CapacityClaim, immutable Ticket, budget reservation, Netting Domain hold, event, aggregate, and durable ENTRY command commit atomically |
| Dynamic policy | Three concurrent Tickets; `0.03` planned stop risk; demand-based remaining margin; fixed exchange `5x`; max `10x` safety ceiling; `cross` margin |
| Entry authority | `new_entry_submit_enabled` applies only before ENTRY; existing exposure retains frozen safety authority |
| Runtime fence | Commit/schema drift records an Incident; an exact but disabled command capability is a controlled readonly fence, not an Incident |
| Historical runtime/trade facts | Reset after verified exchange-flat state by explicit Owner authorization; the current BNB Ticket, Reservation, position and protection lineage are now PostgreSQL runtime authority |
| Terminal-recovery repair | Exact cancel namespace/purpose, atomic Ticket-incident closure, and external-flat unavailable Review are deployed in the active Kernel |
| Current live acceptance | One BNBUSDT long Ticket `ticket:f48f00ecbf90c8ce8335229b42a66cb7` is `position_protected`; its active Budget Reservation, position, Stop and TP1 are exact, with zero Incident and unresolved command |
| Exchange postflight | Account is `independent_sides` and `cross`; all seven approved instruments are `5x`; one BNB long position domain has the exact full Stop and TP1 protection |
| Short post-release observation | The protected handover completed at `8b8bddc8`; Lifecycle completed an exchange-fact maintenance read with `no_change`; three safety workers are active at zero restarts and Entry remains fenced pending fresh certification |
| Full capability | `promote-full` not yet completed |

## Current Performance Snapshot

The following short readonly post-release sample was captured on 2026-07-30.
It verifies release stability, not a full host-capacity benchmark.

| Area | Measured state | Contract interpretation |
| --- | --- | --- |
| Worker stability | Observation, Lifecycle and Reconciliation active; restart count zero; Entry disabled | Protected handover safety cadence is healthy while new ENTRY remains fenced |
| Entry authority | Policy version `2`, command capability enabled, Entry fence present; fresh certification count is `0` | Entry promotion is correctly blocked by the official gate |
| Internal truth | One protected Ticket and one active Budget Reservation; zero Exchange Command and open Incident | Existing exposure retains frozen lifecycle authority |
| External truth | One BNB long position with exact Stop and TP1; seven instruments at `5x`, `cross`, independent sides | Protected-handover exchange gate passes |
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
