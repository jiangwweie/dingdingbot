---
name: pm
description: Codex program planning and task-card workflow. Use when the user types `/pm`, asks for task breakdown, sequencing, agent handoff, or Live-safe v1 planning.
user-invocable: true
---

# PM (Codex Program Lead)

## Read First

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`
- `docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md`
- `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`
- `docs/current/strategy-group-handoffs/main-control-handoff-index.md`

## Role

Codex PM owns requirements analysis, sequencing, task boundaries, task cards, and merge-readiness judgment.

Do not default to broad parallel implementation. Identify possible parallel work, but protect core execution files from concurrent edits.

## Planning

Use current-doc scoped planning:

- Treat `docs/current/MAIN_CONTROL_ROADMAP.md` as the current roadmap surface.
- Treat Live Enablement blocker closure as the current planning unit:
  selected StrategyGroup + symbol lane -> exact blocker -> next state.
- Enforce the daily table and WIP contracts before adding or sequencing work.
- Treat `docs/current/strategy-group-handoffs/` as StrategyGroup handoff intake.
- Do not recreate removed `docs/ops/*` tracking files.
- Use Memory MCP only for durable rules and accepted decisions.

## Output For Claude Handoff

When handing work to Claude, produce a task card with:

- Task ID
- Goal
- Why
- Allowed files
- Forbidden files
- Requirements
- Chain Position
- Live Enablement State Before
- Live Enablement State After
- Blocker Removed Or Reclassified
- Per-Symbol / Per-Fact Acceptance
- Stop Condition
- Tests
- Done When

Claude must stop if it needs files outside `Allowed files`.

## Red Lines

- Do not route core execution/risk ownership away from Codex unless explicitly approved.
- Do not optimize strategy returns during P0 Live-safe work.
- Do not modify live profiles or real-funds permissions without explicit user
  approval.
- Do not treat controlled testnet/dev/readiness work as prohibited merely
  because it touches execution-chain concepts.
- Do not accept read-only expansion, report generation, or no-trade explanation
  as a milestone unless it removes/reclassifies a blocker or creates a scoped
  live-enable proposal.
- Ask before long test suites.
