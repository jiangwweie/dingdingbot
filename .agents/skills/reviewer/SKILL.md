---
name: reviewer
description: Codex code review workflow. Use when the user types `/reviewer`, requests a review, or wants risk/regression assessment.
user-invocable: true
---

# Reviewer (Codex)

## Read First

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
- Relevant task card and diff

## Review Stance

Findings first. Prioritize bugs, behavioral regressions, safety gaps, architecture boundary violations, runtime/profile risk, and missing tests.

Do not patch code during review unless the user explicitly asks.

## Must Check

- Did the change stay inside `Allowed files`?
- Did it touch a Codex-owned core file?
- Did it modify live profiles, real-funds permissions, or strategy parameters?
- Did it add packet, bridge, adapter, readiness, evidence, compatibility, or
  other glue code without proving the main abstraction is still right, naming a
  removal/demotion condition, and deleting or downgrading an old path?
- If it touched testnet/dev/profile-scoped execution-chain code, did it stay
  inside the allowed scoped safety gates?
- Were tests appropriate and approved?
- Are Decimal, logging, async, and domain purity constraints preserved?
