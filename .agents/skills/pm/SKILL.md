---
name: pm
description: Project manager workflow router for this repo. Use when the user types `/pm`, says "项目经理", wants task breakdown, parallel clusters + dependencies, cross-role coordination, progress tracking, or end-to-end delivery. Mirrors Claude Code PM rules (SSOT: `.claude/team/project-manager/SKILL.md`).
user-invocable: true
---

# PM (Codex Entry)

## SSOT (Do Not Re-define)

Read and follow:
- `.claude/team/project-manager/SKILL.md`
- `.claude/team/WORKFLOW.md`
- `AGENTS.md` (red lines + planning-with-files)

## Execution Notes

- For new requirements: do brainstorming first, then ask the Architect for 2 options, then wait for user confirmation before implementation.
- For any non-trivial task: identify parallel clusters and dependencies explicitly (frontend/backend/qa/docs).
- Keep planning-with-files updated in `docs/planning/task_plan.md`, `docs/planning/findings.md`, `docs/planning/progress.md`.

