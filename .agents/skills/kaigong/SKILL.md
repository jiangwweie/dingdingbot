---
name: kaigong
description: Codex session start workflow. Use when the user types `/kaigong` or says "开工/开始/继续".
user-invocable: true
---

# Kaigong (Codex Session Start)

## Read

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`
- `docs/current/strategy-group-handoffs/main-control-handoff-index.md`

## Output

- Current git branch and status summary.
- Current runtime-governance roadmap or handoff summary.
- Whether the task should stay with Codex or be handed to Claude via task card.
- Current hard blockers, if any.
- Safety boundary summary.

Do not recreate removed `docs/ops/*`, `docs/canon/*`, or `docs/planning/*` as active state.
Do not output a next recommended task. The project controller decides
sequencing.
