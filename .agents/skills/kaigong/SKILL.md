---
name: kaigong
description: Codex session start workflow. Use when the user types `/kaigong` or says "开工/开始/继续".
user-invocable: true
---

# Kaigong (Codex Session Start)

## Read

- `AGENTS.md`
- `docs/ops/agent-current-brc-baseline.md`
- `docs/ops/live-safe-v1-program.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/live-safe-v1-findings.md`
- `docs/ops/agent-working-rules.md`
- Relevant ADRs

## Output

- Current git branch and status summary.
- Current Live-safe v1 task board summary.
- Whether the task should stay with Codex or be handed to Claude via task card.
- Current hard blockers, if any.
- Safety boundary summary.

Do not use old `docs/planning/*` as active state.
Do not output a next recommended task. The project controller decides
sequencing.
