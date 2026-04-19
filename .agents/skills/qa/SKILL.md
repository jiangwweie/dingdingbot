---
name: qa
description: QA tester workflow. Use when the user types `/qa`, wants tests, regression coverage, or verification plans. SSOT: `.claude/team/qa-tester/SKILL.md`.
user-invocable: true
---

# QA Tester (Codex Entry)

Read and follow:
- `.claude/team/qa-tester/SKILL.md`
- `.claude/team/WORKFLOW.md`
- `AGENTS.md` (edge-case checklist)

Important:
- If you discover a business-logic bug, do not silently fix it in-place; report it and ask PM to route it, unless the user explicitly asks you to patch it directly.
- Follow the repo red line: ask user confirmation before running long test suites.

