---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-07-23
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
| Production commit | `f9fda21c91482b050e2a630e163f3213386ae6d7` |
| Production anchor | `tokyo-runtime-2026.07.23.1`, fixed to `f9fda21c` |
| Local certification | `331 passed`; Ruff clean; Mypy clean; production file-I/O audit clean |
| Runtime ownership | Four persistent workers: Observation, Entry, Lifecycle, and Reconciliation |
| Scheduling model | Long-running systemd services; timer-based Python cold starts are retired and must not return |
| PostgreSQL | BRC data was deleted without backup by explicit Owner decision, then rebuilt from the single 33-table `0001_initial` baseline |
| Strategy capability | Six registered Events, deterministic detectors, closed-candle Observation, Live/Replay parity, and real StrategySignal production |
| Ticket capability | CapacityClaim, immutable Ticket, budget reservation, Netting Domain hold, event, aggregate, and durable ENTRY command commit atomically |
| Acceptance Ticket | `ticket:c1ebc24a178a3ae4d87978e2fa1204ae`; natural `SOR-001 / SOR-SHORT / SOLUSDT`; verified state `position_protected` |
| Accepted exchange effects | ENTRY, Initial Stop, and TP1 accepted for the acceptance Ticket |
| Hourly supervision | Active, read-only production observation automation |
| Full capability | `promote-full` not yet completed |

## Remaining Critical Path

| Order | Work | Exit condition |
| ---: | --- | --- |
| 1 | Protected lifecycle | Acceptance Ticket reaches a terminal state through the official Lifecycle worker |
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

The rebuild is not complete merely because Tokyo is deployed or the current
Ticket is protected. Completion requires terminal flatness, no residual orders,
released budget, successful Reconciliation, Settlement, Review, zero Incident,
certified `promote-full`, and the final requirement audit.
