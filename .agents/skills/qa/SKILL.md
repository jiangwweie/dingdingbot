---
name: qa
description: Use when designing tests, adding regression coverage, verifying a task, triaging failures, or defining release and production acceptance evidence.
user-invocable: true
---

# QA

## Required Authority

Read:

- `AGENTS.md`
- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`
- the relevant requirement and changed files

## Test Discipline

1. Convert each required behavior into one observable assertion.
2. Run the new test before implementation and confirm the expected failure.
3. Add the minimum behavior needed to pass.
4. Cover negative, stale, duplicate, timeout, rejection, unknown, partial-fill,
   and identity-mismatch cases where relevant.
5. Run targeted tests, then the proportional integration/full-chain suite,
   Ruff, Mypy, and architecture audits.
6. Report exact commands, counts, failures, and skipped checks.

## Required Coverage By Boundary

| Boundary | Required evidence |
| --- | --- |
| StrategySignal | Registry/version/scope/fact/freshness validation and Live/Replay parity |
| CapacityClaim | current account, budget, domain, instrument, price, stop, and arbitration facts |
| Ticket | atomic issuance, one ENTRY generation, global serialization |
| Exchange Command | durable-before-dispatch, terminal rejection, unknown reconciliation |
| Lifecycle | Initial Stop, TP1/runner, controlled exit, partial-fill Incident |
| Multi-position | independent Netting Domains and same-domain exclusion |
| Closure | flatness, no residual order, released budget/domain, Reconciliation, Settlement, Review |
| Architecture | no retired path, table, service, document reference, file authority, or fallback |

## Rules

- Tests must encode current semantics, not preserve retired behavior.
- Use typed in-memory fixtures or disposable PostgreSQL, never report files as
  runtime authority.
- Do not change business behavior while supposedly writing tests.
- Do not claim a production lifecycle complete from fixture-only evidence.
