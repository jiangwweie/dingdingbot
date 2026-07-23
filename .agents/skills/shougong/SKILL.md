---
name: shougong
description: Use when the user says 收工, 结束, 下班, or requests a durable session handoff and verified repository status.
user-invocable: true
---

# Shougong

## Required Authority

Read:

- `AGENTS.md`
- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`
- `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`

## Workflow

1. Re-read the task requirements and inspect the final diff/status.
2. Run fresh verification appropriate to the claims being handed off.
3. Update current documents only when the task requires durable state changes.
4. State completed work, incomplete work, exact blockers, production state,
   tests run, and git identity.
5. Keep runtime and exchange facts separate from local implementation evidence.

## Handoff Contract

- Never call protected exposure, deployment, or partial tests “complete”.
- Preserve the immutable production tag and identify any newer unpromoted commit.
- Record whether `promote-full` remains pending.
- Do not create retired planning, packet, report, or compatibility artifacts.
