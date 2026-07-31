---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-07-31
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
| Integration branch | `dev` |
| Production commit | `25933926db75f79878bd281746be79b7e5f6cde1` |
| Production tag | `tokyo-runtime-2026.07.31.1`; annotated, immutable, and verified on `origin` |
| Production release | `/opt/brc/releases/brc-trading-kernel-25933926db75` |
| Production-commit certification | `890 passed`; 49 architecture tests, Ruff, Mypy (111 source files), production file-I/O audit and diff checks pass |
| Local compatible-upgrade rehearsal | Empty PostgreSQL base-to-head, production-shaped `0001 -> 0002`, exact v4-column preservation, state-machine recovery, six-Event bootstrap and Entry-last Promotion all passed without exchange mutation |
| Runtime ownership | Observation, Entry, Lifecycle and Reconciliation are active and enabled at zero restarts; Entry fence is absent after completed Promotion |
| Scheduling model | Long-running systemd services; timer-based Python cold starts are retired and must not return |
| PostgreSQL | Exact `0001_trading_kernel_baseline_v4 -> 0002_sor_v3_strategy_group_capacity` compatible upgrade completed; runtime commit, schema and seed `sha256:41fd206e80c40ebe0f68ce79b52184566d45a06dc367cd019b70e847e7f3629c` agree |
| History preservation | Exact v4-column digest remained `sha256:3b03b821238d6925878c4c3d09b11d250f0b5d094c36f34354709cce82ab6652`; terminal Ticket, Command, Reservation, Settlement and Review lineage was preserved without an old-schema runtime reader |
| StrategyUniverse deployment | Six current Active Universes and 42 Active Scopes cover BTC, ETH, SOL, BNB, XRP, DOGE and ADA; 14 retired SOR v2 Scopes remain historical lineage; zero Warming Universe; AVAX excluded |
| Strategy capability | Six registered Events, SOR v3 episode and lifecycle semantics, deterministic detectors, closed-candle Observation, Live/Replay parity, and real StrategySignal production |
| Cross-margin bracket coverage | Finite Binance maintenance-margin terminal brackets are accepted only when every candidate stress evaluation point is covered; an out-of-range point remains an explicit fail-closed rejection |
| Ticket capability | CapacityClaim, immutable Ticket, budget reservation, Netting Domain hold, event, aggregate, and durable ENTRY command commit atomically |
| Dynamic policy | Policy version `3`; three account Tickets and two Tickets per StrategyGroup; per-Ticket stop risk `0.03`; account stop risk `0.06`; per-Ticket initial margin `0.45`; account initial margin `0.90`; fixed exchange `5x`; max `10x` safety ceiling; `cross` margin |
| Entry authority | `new_entry_submit_enabled` applies only before ENTRY; existing exposure retains frozen safety authority |
| Runtime fence | Commit/schema drift records an Incident; an exact but disabled command capability is a controlled readonly fence, not an Incident |
| Current PostgreSQL activity | Zero active Ticket, active Budget Reservation, unresolved Exchange Command, non-flat Position and open Incident; all four preserved Budget Reservations are released |
| Terminal-recovery repair | Exact cancel namespace/purpose, atomic Ticket-incident closure, and external-flat unavailable Review are deployed in the active Kernel |
| Deployment operability | Compatible upgrade is flat, stopped, forward-only and preservation-gated; safety workers start first, one bounded six-Event bootstrap completes, and Entry starts last after exact postflight |
| Upgrade blocker repair | Non-SOR v2 Event identity uses the exact frozen v4 Contract shape, and Registry replacement bootstrap tracks the exact newly installed `universe_version_id`; arbitrary hashes and event-only identity shortcuts remain rejected |
| Current live acceptance | Entry acceptance is armed and awaiting the first natural post-release Ticket; active Ticket, non-flat position, open order, unresolved Command and open Incident counts are zero |
| Exchange postflight | Account is `independent_sides` and `cross`; all seven approved instruments are configured at `5x`; exchange has zero non-flat domain and zero open-order domain |
| Short post-release observation | All four workers remained active/enabled at zero restarts; release identity, Policy v3, Capability, six current Universes, 42 Active Scopes and 14 retired historical Scopes remained exact; the seven-member deployment Batch passed Promotion and later expired by design while all seven action-time certifications remained fresh and eligible |
| Full capability | Acceptance authority is armed; `promote-full` remains pending one reviewed natural Ticket closure |

## Current Performance Snapshot

The following readonly post-release sample was captured on 2026-07-31 after
the workers had remained active for approximately ten minutes.
It verifies release stability, not a full host-capacity benchmark.

| Area | Measured state | Contract interpretation |
| --- | --- | --- |
| Worker stability | Observation, Entry, Lifecycle and Reconciliation active/enabled; restart count zero | Persistent runtime cadence is healthy immediately after cutover |
| Entry authority | Policy version `3`, `new_entry_submit_enabled=true`, command capability enabled, Entry fence absent | Official Promotion completed; normal in-scope ENTRY may proceed |
| Internal truth | Zero active Ticket, active Budget Reservation, unresolved Exchange Command, non-flat Position and open Incident | Clean runtime is ready for natural acceptance |
| External truth | Zero position and open-order domain; seven instruments at `5x`, `cross`, independent sides | Flat postflight and exchange identity gates pass |
| Scheduling | Four persistent services; no timer worker introduced | Matches persistent-worker contract |
| Worker slice | Approximately 509 MB, 10 tasks and 2.4% of one CPU over a 15-second idle sample | Below the 1 GiB memory, 128 task and 100% CPU limits |
| Host | Approximately 1.77 GiB available memory and 65% filesystem use | Above the 1 GiB memory warning floor and below the 80% disk warning ceiling |
| Runtime output and logs | No JSON/Markdown file appeared after worker startup; no warning-or-higher worker journal entry appeared | Healthy cadence remains file-free and has no observed runtime warning |

The snapshot source is readonly host, systemd, process, filesystem, and Docker
state. It does not authorize a deployment or exchange mutation.

The full host-capacity benchmark must be repeated after a representative idle
window; this short deployment observation does not replace it.

## Remaining Critical Path

| Order | Work | Exit condition |
| ---: | --- | --- |
| 1 | Natural acceptance | A new in-scope SOR v3 or other enabled signal creates one Ticket and protected position through the official Entry path |
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
