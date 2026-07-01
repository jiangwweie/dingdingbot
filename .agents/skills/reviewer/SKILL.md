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
- `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`
- `docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md`
- `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`
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
  replacement/removal condition, and replacing, removing, or retiring an old
  path?
- If it touched detector, watcher, replay/live parity, scope, or Tradeability,
  did it classify blockers with `BLOCKER_CLASSIFICATION_CONTRACT.md` instead of
  broad `waiting_for_market`, `missing_fact`, or
  `live_detector_artifact_missing` labels?
- Did it include per-symbol / per-fact evidence where facts were computed?
- Did it avoid marking artifact-only or no-trade explanation work as complete?
- Did it preserve the daily table shape when changing daily status?
- Did it respect active WIP limits and stop rules when adding or advancing
  StrategyGroup lanes?
- If it touched testnet/dev/profile-scoped execution-chain code, did it stay
  inside the allowed scoped safety gates?
- Were tests appropriate and approved?
- Are Decimal, logging, async, and domain purity constraints preserved?
