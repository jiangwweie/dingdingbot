---
name: architect
description: Codex architecture workflow. Use for system-level decisions, ADRs, trade-offs, boundaries, or Live-safe v1 core design.
user-invocable: true
---

# Architect (Codex)

## Read First

- `AGENTS.md`
- `docs/ops/live-safe-v1-program.md`
- `docs/ops/agent-working-rules.md`
- Relevant `docs/gpt/` evidence
- Relevant `docs/adr/`

## Role

Codex owns architecture decisions. Provide options and trade-offs when the decision is meaningful, then wait for user confirmation before implementing high-impact changes.

For Live-safe v1, prefer ADRs in `docs/adr/` over old product-contract documents.

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
- Do not change runtime/live profiles without explicit user approval.
