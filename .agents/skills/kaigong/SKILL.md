---
name: kaigong
description: Use when the user says 开工, 开始, 继续, or requests a fresh session orientation for this repository.
user-invocable: true
---

# Kaigong

## Required Authority

Read:

- `AGENTS.md`
- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`
- `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`

## Workflow

1. Inspect current branch, HEAD, upstream, and worktree without mutating them.
2. Read the active roadmap and production identity.
3. If runtime facts matter, use readonly PostgreSQL/exchange/service evidence.
4. State the current phase, unfinished acceptance condition, active hard stops,
   and exact task boundary.
5. Continue the active task unless the user replaced it.

## Output

- Git identity and cleanliness.
- Current production commit and deployment phase.
- Active Ticket or runtime blocker when relevant.
- Work authorized for this session.
- Verification required before completion.

Do not recreate retired planning files, invent a new roadmap lane, or imply
`promote-full` is complete without current evidence.
