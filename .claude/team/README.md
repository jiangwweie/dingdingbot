# Claude Team

This team is configured for the Live-safe v1 workflow.

## Operating Model

Codex is the program lead. Claude roles are bounded executors.

Use Claude roles only when the work has a clear task card, file boundary, test expectation, and definition of done.

## Active Docs

- `docs/ops/live-safe-v1-program.md`
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-findings.md`
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/agent-working-rules.md`
- `docs/adr/`

Archived historical docs are not active instructions.

## Role Map

| Role | Use For | Do Not Use For |
| --- | --- | --- |
| product-manager | Requirement clarification requested by Codex | Broad PRD generation by default |
| architect | Options, trade-offs, ADR support | Owning final architecture decisions |
| project-manager | Task board and task-card coordination | Automatic broad parallel dispatch |
| backend-dev | Scoped backend implementation | Expanding architecture or scope |
| frontend-dev | Scoped readonly console work | Inventing backend semantics |
| qa-tester | Scoped tests and verification | Running long suites without approval |
| code-reviewer | Review and risk reports | Direct implementation |
| diagnostic-analyst | Root-cause analysis | Production code edits |

## Task Card Required

Implementation tasks must include:

- Task ID
- Goal
- Why
- Allowed files
- Forbidden files
- Requirements
- Tests
- Done When

## Memory MCP

Use Memory MCP for durable decisions and rules only. Use program files for progress.
