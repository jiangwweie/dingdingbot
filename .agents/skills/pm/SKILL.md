---
name: pm
description: Use when breaking down work, sequencing a program, defining task cards, identifying decisions, or evaluating remaining Trading Kernel scope.
user-invocable: true
---

# PM

## Required Authority

Read:

- `AGENTS.md`
- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`

## Planning Principle

Plan by the earliest unfinished transition in the single authoritative chain:

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

Do not create document work, reports, compatibility, or parallel orchestration
as substitutes for closing the actual transition.

## Required Plan Shape

| Field | Requirement |
| --- | --- |
| Objective | Concrete observable outcome |
| Known state | Current code, test, PG, exchange, and deployment facts |
| Gap | Earliest missing capability or acceptance evidence |
| Tasks | Ordered, bounded changes with one owner each |
| Dependencies | Explicit data/code/runtime predecessor |
| Tests | RED condition and proportional verification |
| Hard stops | Safety, scope, and authority boundaries |
| Done | Exact terminal evidence, not activity |

## Task Card

Every delegated implementation card states Task ID, goal, allowed files,
forbidden files, requirements, tests, done condition, and hard stops. It must
not authorize production mutation unless the Owner's active scope does.

## Sequencing Rules

- Protect shared kernel and schema files from concurrent edits.
- Separate readonly diagnosis from implementation and deployment.
- Strategy research changes require a separate Owner decision; registered
  producer maintenance stays above StrategySignal.
- Production completion requires terminal flatness, no residual orders,
  released budget/domain, Reconciliation, Settlement, Review, zero Incident,
  full policy promotion, and final audit.

## Hard Stops

No plan may expand capital, sizing, credentials, instruments, or exchange-write
scope by implication. No task may restore retired program or database authority.
