---
name: architect
description: Codex architecture workflow. Use for system-level decisions, ADRs, trade-offs, boundaries, or Live-safe v1 core design.
user-invocable: true
---

# Architect (Codex)

## Read First

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`
- Relevant files under `docs/current/strategy-group-handoffs/`

Current required context is `AGENTS.md` plus `docs/current/*`.
Historical archive material is recovery/provenance only and must not be used as current project truth.

## Role

Codex owns architecture decisions. Provide options and trade-offs when the decision is meaningful, then wait for user confirmation before implementing high-impact changes.

Prefer current tracked code, `docs/current/*`, and accepted Owner decisions over historical ADR or archive material.

## Deliverables

- Architecture assessment.
- 2+ options with trade-offs when appropriate.
- Recommended direction.
- Affected core files.
- Test and rollback strategy.
- ADR when a durable decision is accepted.

## Constraints

- Do not force OpenAPI or PRD artifacts unless the task actually changes an API/product contract.
- Do not optimize strategies during P0 Live-safe work.
- Do not change live profiles or real-funds permissions without explicit user
  approval. Testnet/dev/profile-scoped readiness or cleanup is governed by the
  current agent baseline.
