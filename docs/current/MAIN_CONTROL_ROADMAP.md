---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-07-24
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
| Production commit | `44c3d7a00e2250689295d597ba8e05a675c16fc5` |
| Local certification | `401 passed`; production file-I/O and current-document authority audits pass |
| Runtime ownership | **Acceptance-armed**: Observation, Lifecycle, and Reconciliation are active; Entry is intentionally disabled pending leverage-mutation diagnosis |
| Scheduling model | Long-running systemd services; timer-based Python cold starts are retired and must not return |
| PostgreSQL | BRC data was deleted without backup by explicit Owner decision, then rebuilt from the single 33-table `0001_initial` baseline |
| Strategy capability | Six registered Events, deterministic detectors, closed-candle Observation, Live/Replay parity, and real StrategySignal production |
| Ticket capability | CapacityClaim, immutable Ticket, budget reservation, Netting Domain hold, event, aggregate, and durable ENTRY command commit atomically |
| Dynamic policy | Three concurrent Tickets; `0.03` planned stop risk; `0.90` initial-margin utilization; max `10` leverage; `cross` margin |
| Entry authority | `new_entry_submit_enabled` applies only before ENTRY; existing exposure retains frozen safety authority |
| Runtime fence | Commit/schema drift records an Incident; an exact but disabled command capability is a controlled readonly fence, not an Incident |
| Acceptance Ticket | `ticket:e5c125d947e36f906b03f76dbea35b56` safely reached `leverage_rejected`; no ENTRY, order, or position was created |
| Hourly supervision | Observation, Lifecycle, and Reconciliation active; Entry disabled |
| Full capability | `promote-full` not yet completed |

## Remaining Critical Path

| Order | Work | Exit condition |
| ---: | --- | --- |
| 1 | Leverage mutation diagnosis | Preserve and classify the authoritative Binance rejection before re-enabling Entry |
| 2 | Protected lifecycle | A new natural acceptance Ticket reaches terminal state through the official Lifecycle worker |
| 3 | External truth closure | Exchange is flat and has no residual ENTRY, protection, TP, EXIT, or cancel order |
| 4 | Internal truth closure | Ticket terminal, budget released, Netting Domain released, Reconciliation matched |
| 5 | Economics closure | Settlement and Review persist exact realized economics, including explicit funding availability |
| 6 | Incident audit | Zero open runtime incident and zero unknown command outcome |
| 7 | Full policy promotion | Run and certify `promote-full` only after steps 1-6 pass |
| 8 | Final requirement audit | Re-run local and Tokyo evidence and close every acceptance item |

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
