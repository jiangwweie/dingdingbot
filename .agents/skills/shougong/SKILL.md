---
name: shougong
description: Codex session wrap-up workflow. Use when the user types `/shougong` or says "收工/结束/下班".
user-invocable: true
---

# Shougong (Codex Session Wrap-up)

## Read

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`
- `docs/current/strategy-group-handoffs/main-control-handoff-index.md`

## Do

- Update current docs only when explicitly asked or when the task card requires a durable artifact.
- Write Memory MCP only for durable rules or accepted decisions.
- Return a concise handoff note in chat.

Do not recreate removed `docs/ops/*`, `docs/canon/*`, or `docs/planning/*` files.
