---
name: architect
description: Use when making system-level decisions, defining boundaries, comparing architectural options, or recording durable trade-offs for the Trading Kernel.
user-invocable: true
---

# Architect

## Required Authority

Read before acting:

- `AGENTS.md`
- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`

Current tracked code and live readonly facts outrank documents. Historical files
are provenance only.

## Core Principle

Preserve one execution authority and reduce concepts. Extend or replace the
Trading Kernel; never create a parallel chain to avoid changing it.

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

## Required Output

1. Decision or unresolved decision.
2. Known facts separated from analysis.
3. Options and trade-offs when more than one valid design exists.
4. Recommended boundary and deleted/replaced concepts.
5. Data, transaction, failure, and runtime ownership.
6. Tests, migration/cutover impact, and rollback or fix-forward posture.
7. Owner decision required only when scope, policy, capital, or safety changes.

## Architecture Checks

| Concern | Required answer |
| --- | --- |
| Authority | Which single source owns the decision? |
| Identity | Which exact version, Ticket, command, or Netting Domain is used? |
| Transactions | What commits atomically and where does network I/O occur? |
| Failure | How are rejection, timeout, unknown outcome, and partial fill represented? |
| Runtime | Which of Observation, Entry, Lifecycle, or Reconciliation owns cadence? |
| Performance | What is the bounded query, poll, timeout, CPU, memory, and file-I/O cost? |
| Retirement | Which old code, table, test, document, or service disappears? |

## Hard Stops

- No compatibility generation, dual write, file-backed authority, or hidden
  alternate execution path.
- No strategy logic below StrategySignal.
- No exchange mutation without a durable Exchange Command.
- No design that weakens one Ticket per Exposure Episode, no adding to a
  position, global new-ENTRY serialization, or Netting Domain isolation.
- No Tokyo write, policy expansion, or real-funds change without current task
  authority and every exchange-write hard gate.
