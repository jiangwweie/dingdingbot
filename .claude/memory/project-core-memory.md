---
name: 项目核心记忆
description: Live-safe v1 工作方式、角色边界、质量红线
type: project
---

# Project Core Memory

Updated: 2026-04-29

## Current Phase

The project is in Live-safe v1 replanning and execution-safety hardening.

The current target is to move from Sim-ready toward full-auto small-live safety. The next work is execution safety, account-level risk, reconciliation, observability, and runtime guardrails.

Long-term direction: evolve from an ETH single-strategy research system into a full-auto, multi-asset, multi-direction, low-frequency portfolio platform.

Return and drawdown numbers are investor preference signals and evaluation dimensions. They must not become hard-coded architecture constraints, runtime rules, or agent instructions.

## Operating Model

Codex owns:

- Requirements analysis.
- Planning and sequencing.
- Architecture decisions and ADRs.
- Core implementation and skeleton development.
- Review and merge readiness.

Claude Code owns:

- Bounded implementation from Codex task cards.
- Scoped tests.
- Local docs updates when requested.

Claude does not own global direction or architecture.

## Active Planning Files

- `docs/ops/live-safe-v1-program.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-findings.md`
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/agent-working-rules.md`
- `docs/adr/`

The old global `docs/planning/*` workflow is not active unless explicitly requested.

## Durable Quality Rules

- `domain/` must not import I/O frameworks such as `ccxt`, `aiohttp`, `requests`, `fastapi`, or `yaml`.
- Financial calculations must use `decimal.Decimal`.
- Sensitive values must be masked in logs.
- Core parameters should use named Pydantic models where practical.
- Live/runtime profile changes require explicit user approval and a separate task.

## Live-safe v1 Non-goals

- Do not optimize strategy returns.
- Do not tune ETH Pinbar parameters.
- Do not expand multi-asset support.
- Do not activate real funds.
- Do not rewrite the architecture.
- Do not hard-code fixed annual return or max drawdown targets as system constraints.
