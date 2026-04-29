---
name: shougong
description: Codex session wrap-up workflow. Use when the user types `/shougong` or says "收工/结束/下班".
user-invocable: true
---

# Shougong (Codex Session Wrap-up)

## Read

- `AGENTS.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/live-safe-v1-findings.md`

## Do

- Update `docs/ops/live-safe-v1-progress.md` with session progress.
- Update `docs/ops/live-safe-v1-findings.md` if there are program-local findings.
- Update `docs/ops/live-safe-v1-task-board.md` if task status changed.
- Write Memory MCP only for durable rules or accepted decisions.
- Return a concise handoff note in chat.

Do not recreate old `docs/planning/*` files.
