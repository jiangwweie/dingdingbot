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
| Production commit | `4749174c64a6b369930ed91f09d7b9eba1fa0e7a` |
| Local certification | `407 passed`; focused Ruff and Mypy checks pass |
| Runtime ownership | **Acceptance-armed**: Observation, Entry, Lifecycle, and Reconciliation are enabled and active |
| Scheduling model | Long-running systemd services; timer-based Python cold starts are retired and must not return |
| PostgreSQL | BRC data was deleted without backup by explicit Owner decision, then rebuilt from the single 33-table `0001_initial` baseline |
| Strategy capability | Six registered Events, deterministic detectors, closed-candle Observation, Live/Replay parity, and real StrategySignal production |
| Ticket capability | CapacityClaim, immutable Ticket, budget reservation, Netting Domain hold, event, aggregate, and durable ENTRY command commit atomically |
| Dynamic policy | Three concurrent Tickets; `0.03` planned stop risk; demand-based remaining margin; fixed exchange `5x`; max `10x` safety ceiling; `cross` margin |
| Entry authority | `new_entry_submit_enabled` applies only before ENTRY; existing exposure retains frozen safety authority |
| Runtime fence | Commit/schema drift records an Incident; an exact but disabled command capability is a controlled readonly fence, not an Incident |
| Historical safety Tickets | Three safely reached `leverage_rejected`; no ENTRY, order, or position was created |
| Hourly supervision | All four persistent workers active; Entry globally serialized |
| Full capability | `promote-full` not yet completed |

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
