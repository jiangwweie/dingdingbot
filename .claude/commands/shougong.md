# Shougong

Use this command to wrap up a Live-safe v1 session.

Read:
- `CLAUDE.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/live-safe-v1-findings.md`

Do:
1. Summarize changed files and task status.
2. Update `docs/ops/live-safe-v1-progress.md` when asked or when the session state should persist.
3. Update `docs/ops/live-safe-v1-findings.md` for program-local findings.
4. Write Memory MCP only for durable rules or accepted decisions.
5. Return a concise handoff note.

Do not recreate old `docs/planning/*` files.
