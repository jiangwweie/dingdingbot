---
name: architect
description: Architect workflow for this repo. Use when the user types `/architect`, asks for architecture/design/options, API contracts, trade-offs, or system-level changes. Must provide 2+ options and wait for user confirmation. SSOT: `.claude/team/architect/SKILL.md`.
user-invocable: true
---

# Architect (Codex Entry)

Read and follow:
- `.claude/team/architect/SKILL.md`
- `.claude/team/WORKFLOW.md`
- `AGENTS.md` (architecture red lines + boundaries checklist)

Non-negotiables:
- Provide at least 2 viable technical options with trade-offs.
- Stop after presenting options and ask the user to confirm direction before implementation.

