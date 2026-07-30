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
| Branch | `codex/review-owner-terminal-repair-20260730` |
| Production commit | `d2acb3ec596562f00c2291ed8b83b5e740e21167` |
| Production tag | `tokyo-runtime-2026.07.30.4`; annotated, immutable, and verified on `origin` |
| Production-commit certification | `834 passed`; Ruff, Mypy (108 source files), compileall, runtime file-I/O audit and diff checks pass |
| Local clean-rebuild rehearsal | Empty PostgreSQL baseline, operation-owned rebuild, Batch-before-worker, pending-Batch recovery, six-Event bootstrap, root Promotion boundary and repeatability all passed without exchange mutation |
| Runtime ownership | Observation, Entry, Lifecycle and Reconciliation are active and enabled at zero restarts; Entry fence is absent after completed Promotion |
| Scheduling model | Long-running systemd services; timer-based Python cold starts are retired and must not return |
| PostgreSQL | Cutover `tokyo-v4-batch-priority-20260730-d2acb3ec` completed; `public` was clean-rebuilt from `0001_trading_kernel_baseline_v4`; Registry, Policy, Capability and exact runtime identity match the production commit |
| StrategyUniverse deployment | Six current Active Universes, 42 Active Scopes and seven approved instruments: BTC, ETH, SOL, BNB, XRP, DOGE and ADA; zero Warming Universe; AVAX excluded |
| Strategy capability | Six registered Events, deterministic detectors, closed-candle Observation, Live/Replay parity, and real StrategySignal production |
| Cross-margin bracket coverage | Finite Binance maintenance-margin terminal brackets are accepted only when every candidate stress evaluation point is covered; an out-of-range point remains an explicit fail-closed rejection |
| Ticket capability | CapacityClaim, immutable Ticket, budget reservation, Netting Domain hold, event, aggregate, and durable ENTRY command commit atomically |
| Dynamic policy | Policy version `2`; three concurrent Tickets; per-Ticket stop risk `0.03`; account stop risk `0.06`; per-Ticket initial margin `0.45`; account initial margin `0.90`; fixed exchange `5x`; max `10x` safety ceiling; `cross` margin |
| Entry authority | `new_entry_submit_enabled` applies only before ENTRY; existing exposure retains frozen safety authority |
| Runtime fence | Commit/schema drift records an Incident; an exact but disabled command capability is a controlled readonly fence, not an Incident |
| Historical runtime/trade facts | Reset after verified exchange-flat state by explicit Owner authorization; current PostgreSQL has zero Ticket, Budget Reservation, Exchange Command and open Incident |
| Terminal-recovery repair | Exact cancel namespace/purpose, atomic Ticket-incident closure, and external-flat unavailable Review are deployed in the active Kernel |
| Deployment operability | New operation cannot skip clean rebuild on same revision; Batch is prepared before workers; pending Batch members override normal certification cadence; Promotion uses an allowlisted root control-plane runner while workers remain non-privileged |
| Current live acceptance | Entry acceptance is armed and awaiting the first natural post-release Ticket; current Ticket, position, order, Command and Incident counts are zero |
| Exchange postflight | Account is `independent_sides` and `cross`; all seven approved instruments are configured at `5x`; exchange has zero non-flat domain and zero open-order domain |
| Short post-release observation | All four workers are active/enabled at zero restarts; release identity, Policy v2, Capability, six Universes, 42 Scopes and the seven-member Batch are exact |
| Full capability | Acceptance authority is armed; `promote-full` remains pending one reviewed natural Ticket closure |

## Current Performance Snapshot

The following short readonly post-release sample was captured on 2026-07-30.
It verifies release stability, not a full host-capacity benchmark.

| Area | Measured state | Contract interpretation |
| --- | --- | --- |
| Worker stability | Observation, Entry, Lifecycle and Reconciliation active/enabled; restart count zero | Persistent runtime cadence is healthy immediately after cutover |
| Entry authority | Policy version `2`, `new_entry_submit_enabled=true`, command capability enabled, Entry fence absent | Official Promotion completed; normal in-scope ENTRY may proceed |
| Internal truth | Zero Ticket, Budget Reservation, Exchange Command, unresolved outcome and open Incident | Clean runtime is ready for natural acceptance |
| External truth | Zero position and open-order domain; seven instruments at `5x`, `cross`, independent sides | Flat postflight and exchange identity gates pass |
| Scheduling | Four persistent services; no timer worker introduced | Matches persistent-worker contract |

The snapshot source is readonly host, systemd, process, filesystem, and Docker
state. It does not authorize a deployment or exchange mutation.

The full host-capacity benchmark must be repeated after a representative idle
window; this short deployment observation does not replace it.

## Remaining Critical Path

| Order | Work | Exit condition |
| ---: | --- | --- |
| 1 | Natural acceptance | A new in-scope signal creates one Ticket and protected position through the official Entry path |
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

The production deployment and acceptance arming are complete. The broader
rebuild program is not final until one new natural acceptance Ticket reaches
terminal flatness with no residual orders, released budget, successful
Reconciliation, Settlement, Review, zero Incident, certified `promote-full`,
and the final requirement audit.
