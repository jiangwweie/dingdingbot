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
| Multi-position certification | `104 passed` at commit `5946cbf1` |
| Database | One `0001_initial`, 29 target tables, downgrade/upgrade certified |
| Static checks | Ruff pass; production Mypy zero errors |
| Runtime file authority | Suspicious readers and recurring report writers both zero |
| Tokyo | Still requires destructive cutover to the new kernel |

## Critical Path

| Order | Work | Exit condition |
| --- | --- | --- |
| 1 | Current documentation retirement | Only the rebuilt-kernel authority allowlist remains |
| 2 | Typed signal to frozen Ticket | Production-shaped typed input can persist, queue, serialize, and issue Tickets |
| 3 | Destructive cutover tooling | Crash-safe and resume-safe rehearsal passes every refusal case |
| 4 | Tokyo cutover | Exact commit/schema/seed/services verified with retired tables absent |
| 5 | Controlled real-funds lifecycle | One Ticket reaches terminal review and final flatness |
| 6 | Completion audit | Every final requirement has direct current evidence |

## Stop Conditions

An active safety incident interrupts ordinary work. Exchange write stays
disabled for identity mismatch, invalid account mode, stale facts, same-domain
occupancy, missing budget/protection, unknown outcome, writer overlap, or
code/schema mismatch.

Missing implementation, documentation debt, or difficult migration work is not
a reason to narrow the final target. The next action remains the earliest
unfinished critical-path capability.
