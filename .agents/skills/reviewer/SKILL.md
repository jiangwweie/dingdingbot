---
name: reviewer
description: Codex code review workflow. Use when the user types `/reviewer`, requests a review, or wants risk/regression assessment.
user-invocable: true
---

# Reviewer (Codex)

## Read First

- `AGENTS.md`
- `docs/ops/live-safe-v1-program.md`
- `docs/ops/agent-working-rules.md`
- Relevant task card and diff

## Review Stance

Findings first. Prioritize bugs, behavioral regressions, safety gaps, architecture boundary violations, runtime/profile risk, and missing tests.

Do not patch code during review unless the user explicitly asks.

## Must Check

- Did the change stay inside `Allowed files`?
- Did it touch a Codex-owned core file?
- Did it modify runtime/live profiles or strategy parameters?
- Were tests appropriate and approved?
- Are Decimal, logging, async, and domain purity constraints preserved?
