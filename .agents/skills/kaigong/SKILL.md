---
name: kaigong
description: Session start workflow (kaigong). Use when the user types `/kaigong` or says "开工/开始/继续". Aligns with Claude kaigong workflow but runs in Codex. SSOT references: `AGENTS.md`, `.claude/team/WORKFLOW.md`, and `docs/planning/*`.
user-invocable: true
---

# Kaigong (Codex Entry)

## SSOT

Read:
- `AGENTS.md` (red lines + planning-with-files)
- `.claude/team/WORKFLOW.md`
- `docs/planning/task_plan.md`
- `docs/planning/findings.md`
- `docs/planning/progress.md`

## Output

- Print current git branch/status summary.
- List 3-7 suggested next tasks with dependencies and which roles can run in parallel.
- If new requirements are involved, stop and route to Architect to present 2 options before implementing.

