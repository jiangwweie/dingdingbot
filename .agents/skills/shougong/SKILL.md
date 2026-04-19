---
name: shougong
description: Session wrap-up workflow (shougong). Use when the user types `/shougong` or says "收工/结束/下班". Aligns with Claude shougong goals but runs in Codex. SSOT references: `AGENTS.md`, `.claude/team/WORKFLOW.md`, and `docs/planning/*`.
user-invocable: true
---

# Shougong (Codex Entry)

Read:
- `AGENTS.md` (planning-with-files requirements)
- `.claude/team/WORKFLOW.md`

Do:
- Update `docs/planning/progress.md` with what changed this session.
- Update `docs/planning/findings.md` if there are new technical learnings/decisions.
- Update `docs/planning/task_plan.md` phase/status if scope changed.
- Prepare a concise handoff note (in chat) describing next actions and any blockers.

