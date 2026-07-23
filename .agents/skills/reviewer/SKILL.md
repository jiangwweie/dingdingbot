---
name: reviewer
description: Use when reviewing code, tests, migrations, deployment changes, or runtime behavior for defects, regressions, safety gaps, and architecture drift.
user-invocable: true
---

# Reviewer

## Required Authority

Read before reviewing:

- `AGENTS.md`
- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`
- relevant task requirements, diff, tests, and live facts

## Review Stance

Findings first. Report only actionable defects or material residual risk. Do not
patch during a review unless the user also asked for implementation.

## Required Checks

| Area | Review question |
| --- | --- |
| Scope | Did the change stay within authorized files and behavior? |
| Chain | Does it preserve Observation → StrategySignal → Readiness/Authority → CapacityClaim → Ticket → Exchange Command → lifecycle → reconciliation → settlement → review? |
| Authority | Is there exactly one current source for each decision? |
| Ticket semantics | One Exposure Episode, no adding, one ENTRY generation, global ENTRY serialization? |
| Exchange safety | Durable command before write, terminal rejection, no blind resend, exact unknown recovery? |
| Position safety | Netting Domain isolation, independent long/short, Initial Stop, partial-fill Incident? |
| Transactions | Short PG transactions and network I/O outside them? |
| Runtime | Exactly one persistent owner for Observation, Entry, Lifecycle, and Reconciliation? |
| Performance | Bounded queries, polling, timeouts, memory/CPU, and zero idle report-file growth? |
| Retirement | No old code path, table, migration, test, document, service, fallback, or dual authority? |
| Tests | Was RED observed, are negative/fault cases covered, and did proportional verification run? |

## Finding Format

Each finding contains severity, exact file/line, failing scenario, consequence,
and smallest correct direction. Separate findings from assumptions and open
questions.

## Hard Stops

- Treat any exchange-write bypass, unknown-outcome redispatch, missing Initial
  Stop, same-domain overlap, identity mismatch, or old-writer overlap as P0/P1.
- Treat a protected but nonterminal acceptance Ticket as incomplete.
- Do not accept tests that reintroduce retired semantics to make the suite pass.
