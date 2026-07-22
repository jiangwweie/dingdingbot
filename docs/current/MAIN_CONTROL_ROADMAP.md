---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
last_verified: 2026-07-22
---

# Main Control Roadmap

## Final Target

```text
multi-StrategyGroup typed observation
-> serial new-Ticket issuance
-> concurrent protected multi-position lifecycle
-> durable exchange truth
-> settlement and review
-> one Owner supervision surface
```

## Current Verified Local State

| Area | Current evidence |
| --- | --- |
| Branch | `codex/trading-kernel-rebuild-20260722` |
| Kernel lifecycle | Implemented under `src/trading_kernel` |
| Retired production code | Deleted in `d570018a` |
| Multi-position certification | Included in the current `303 passed` full trading-kernel suite |
| StrategySignal boundary | Immutable Fact Bundle, append-only lineage, and candidate persistence implemented; direct Signal-to-Ticket authority removed |
| Six Event detectors | Pure deterministic CPM-LONG, MPG-LONG, MI-LONG, SOR-LONG, SOR-SHORT, and BRF2-SHORT calculations implemented from committed old main-program semantics |
| Observation and signal production | Closed-candle public market reads, bounded current Fact upserts, deterministic Signal identity, six-Event observation matrix, and Live/Replay detector parity verified |
| Candidate arbitration and Capacity | Owner Policy Priority → Candidate Scope Priority → Event Time → Observed Time → Signal ID; bounded 64-candidate selector; fresh bid/ask, equity, margin, current reservations, instrument rules, same-domain truth, and exact stop risk produce one immutable CapacityClaim |
| Atomic Ticket issuance | CapacityClaim, budget reservation, account exposure, global ENTRY lane, immutable Ticket, first event, aggregate, and durable ENTRY command commit in one PostgreSQL transaction |
| Venue Truth and unknown recovery | ENTRY, Initial Stop, EXIT, Controlled Flatten, and exact-target Cancel reconcile through one timeout-bounded authority; Unknown never redispatches and identity contradiction remains a hard incident |
| Protected lifecycle and Review | Initial Stop, TP1, Break-Even, structural ATR runner, controlled exits, settlement, exact-order Review Economics, and explicit `funding_unavailable` semantics implemented |
| Runtime ownership | Four unique workers: Observation, Entry, Lifecycle, and Reconciliation |
| Destructive cutover tooling | Local state machine and disposable-PG rehearsal pass |
| Database | One `0001_initial`, 33 target tables, downgrade/upgrade certified |
| Local certification | `303 passed in 78.65s` |
| Static checks | Ruff pass; production Mypy zero errors across 68 source files |
| Runtime file authority | Suspicious readers and recurring report writers both zero |
| Tokyo | Owner-authorized for destructive BRC-only cutover, small real-funds Ticket, post-acceptance write enablement, and hourly observation; no Tokyo mutation claimed yet |

## Critical Path

| Order | Work | Exit condition |
| --- | --- | --- |
| 1 | Current documentation retirement | Only the rebuilt-kernel authority allowlist remains |
| 2 | StrategySignal to CapacityClaim to frozen Ticket | Typed observation persists without capital authority; action-time facts create the only Ticket-capable Claim |
| 3 | Destructive cutover tooling | Crash-safe and resume-safe rehearsal passes every refusal case |
| 4 | Strategy refactor decision and implementation | Complete for the six registered Events without retired semantics |
| 5 | Tokyo cutover | Exact commit/schema/seed/services verified with retired tables absent |
| 6 | Controlled real-funds lifecycle | One Ticket reaches terminal review and final flatness |
| 7 | Completion audit | Every final requirement has direct current evidence |

## Stop Conditions

An active safety incident interrupts ordinary work. Exchange write stays
disabled for identity mismatch, invalid account mode, stale facts, same-domain
occupancy, missing budget/protection, unknown outcome, writer overlap, or
code/schema mismatch.

Missing implementation, documentation debt, or difficult migration work is not
a reason to narrow the final target. The next action remains the earliest
unfinished critical-path capability.

Tokyo deployment, BRC-only destructive cleanup, and one controlled real-funds
acceptance Ticket are authorized. Exchange writes remain fail-closed until the
Tokyo commit, schema, seed, account mode, flatness, writer fence, and protection
gates all pass. Full write capability follows only after the small Ticket closes
flat, reconciled, settled, and reviewed with no residual orders or incidents.
