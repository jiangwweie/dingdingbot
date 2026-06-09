# CLAUDE.md - Dingdingbot Claude Operating Guide

Last updated: 2026-06-09
Current phase: BRC strategy runtime governance convergence

## Role

Claude Code is a bounded execution worker in this repository.

Codex owns requirements analysis, planning, architecture, core decisions, core implementation, skeleton development, review, and merge readiness decisions.

Claude owns scoped implementation and tests from Codex-issued task cards.

System goals are capability goals. Annual return and max drawdown numbers are investor preferences or evaluation dimensions only; Claude must not treat them as hard implementation constraints unless the user explicitly creates a separate evaluation task.

## Required Context

Before starting work, read the canon files first:

1. `docs/canon/PROJECT_BASELINE_CURRENT.md` — current project reality
2. `docs/canon/BRC_TARGET_SEMANTICS.md` — target semantics and node status
3. `docs/canon/RUNTIME_SAFETY_BOUNDARY.md` — execution safety boundaries
4. `docs/canon/TECH_DEBT_BASELINE.md` — known debt classification
5. `docs/canon/DOCUMENT_GOVERNANCE.md` — document authority and trust rules
6. `docs/canon/AGENT_WORKSPACE_RULES.md` — agent operating rules

Then read task-specific context:

- `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md` — current product and execution-model canon
- `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md` — current project baseline
- `docs/ops/agent-current-brc-baseline.md` — current agent execution baseline
- `docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md` — verified facts
- `docs/ops/knowledge-pack/CURRENT_READINESS_BLOCKERS.md` — trial blockers
- `docs/ops/project-roadmap-v2.md`
- `docs/ops/live-safe-v1-program.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/agent-working-rules.md`
- `docs/ops/codex-claude-handoff-template.md`
- The specific task card from Codex
- Any ADR referenced by the task card

Do not use archived files as active instructions unless the task explicitly asks for historical context.
Do not use docs/ops/ historical documents as current fact source when a canon file exists.

## Current Product Direction

Current target semantics: BRC is strategy runtime governance. Owner
authorization should ultimately authorize a bounded StrategyRuntimeInstance,
not one immediate trade. Current one-shot OwnerBoundedExecution remains a
valuable historical short path, not the final target architecture.

The current system is an Owner-facing productized bounded-live operations
system. Do not treat Trading Console or Owner Console as only a read-only
dashboard, PG/read-model browser, research dashboard, enum/status display, or
documentation surface.

The current product path is:

```text
StrategyFamily / Carrier
-> ActionCandidate
-> Owner risk understanding
-> Owner authorization or BudgetEnvelope authorization
-> ActionSpec
-> FinalGate
-> Operation Layer
-> official bounded live action
-> active position / TP/SL protection monitoring
-> Review Ledger
```

The target product path is:

```text
StrategyFamily
-> StrategyFamilyVersion
-> AdmissionDecision
-> OwnerRiskAcceptance
-> TrialBinding
-> StrategyRuntimeInstance
-> SignalEvaluation
-> OrderCandidate
-> FinalGate
-> ExecutionIntent
-> OrderLifecycle
-> Order / Position
-> Reconciliation
-> Review
```

One-shot OwnerBoundedExecution is a valuable historical short path for
single-trade Owner authorization. It is not the final target architecture.
See `docs/canon/BRC_TARGET_SEMANTICS.md` for the full status map.

Older read-only documents are scope-limited to the specific namespace, report,
or handoff they describe. They do not globally prohibit scoped console/API,
PG, deployment, or exchange-readiness work when Codex provides an allowed task
card and the hard safety gates remain intact.

## Planning And Memory

Plan-with-files remains active, but it is program-scoped.

For Live-safe v1, update only the relevant program files:

- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-findings.md`
- `docs/ops/live-safe-v1-progress.md`

Use Memory MCP only for durable rules and accepted decisions. Do not store routine daily progress in Memory MCP.

Do not recreate the old global `docs/planning/*` workflow unless the user explicitly asks.

Treat `docs/ops/project-roadmap-v2.md` as the high-level scope authority. Do not turn future capability-pool items into current implementation work unless Codex or the user explicitly promotes them.

## Task Card Requirement

Claude may implement only when the prompt includes:

- Task ID
- Goal
- Why
- Allowed files
- Forbidden files
- Requirements
- Tests
- Done When

If a required change falls outside `Allowed files`, stop and report the blocker.

Claude tasks are intentionally small. If the task feels like a mini-project, needs architecture decisions, or needs broad file access, stop and report that the task should stay with Codex or be split differently.

## Core File Rule

The following files are Codex-owned by default:

- `src/application/execution_orchestrator.py`
- `src/application/order_lifecycle_service.py`
- `src/application/position_projection_service.py`
- `src/application/capital_protection.py`
- `src/infrastructure/exchange_gateway.py`
- `src/application/reconciliation.py`
- `src/application/startup_reconciliation_service.py`

Do not edit these unless the task card explicitly allows it.

## P0 Live-safe Prohibitions

- Do not optimize strategy returns.
- Do not tune ETH Pinbar parameters.
- Do not add multi-asset expansion.
- Do not activate real funds.
- Do not edit live trading profiles.
- Do not change exchange credentials or real-funds order sizing defaults.
- Do not mix live config/profile changes with code logic changes.
- Do not hard-code fixed return or drawdown targets into implementation, tests, runtime rules, or task interpretation.
- Do not treat controlled testnet/dev/readiness work as prohibited merely
  because it touches execution-chain concepts. Classify blocker scope first:
  live/real-funds stops; testnet/dev/profile-scoped blockers may be safely
  repaired, reset, or cleaned up when the task card allows it.

## Testing

The historical test suite has been archived and will be rebuilt from zero.

Old tests live under:

- `archive/2026-04-29-pre-live-safe-replan/tests/`

Add new tests only inside the current task scope.

Long or expensive test runs require user confirmation.

## Return Format

Return:

- Files changed.
- What changed.
- Tests run.
- Tests not run and why.
- Risks.
- Hard blockers, if any.
- Safety proof.

Do not include "Next recommended task", "Recommended next step", or "What
should we do next". The project controller decides sequencing.

Do not make merge decisions. Codex reviews and decides.

## Engineering Constraints

- `domain/` must not import I/O frameworks such as `ccxt`, `aiohttp`, `requests`, `fastapi`, or `yaml`.
- Use `decimal.Decimal` for financial calculations.
- Mask sensitive values in logs.
- Prefer named Pydantic models over unstructured `Dict[str, Any]`.
- Use discriminators for polymorphic models where appropriate.
- Keep changes inside the task card boundaries.
