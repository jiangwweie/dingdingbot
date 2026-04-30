# Live-safe v1 Progress

Use this file for session progress and handoff notes.

## 2026-04-29

- Archived pre-live-safe docs, tests, scripts, and generated artifacts.
- Established new program-scoped planning model under `docs/ops/`.
- Adopted Codex-led, Claude-bounded execution workflow.

## 2026-04-30

- Landed `Decision Trace Backbone v0` as a minimal, non-blocking trace backbone for risk decision JSONL output.
- Added `ADR-0002` to document Decision Trace Backbone v0 semantics, scope, and non-goals.
- Landed `LS-001` so the main runtime starts isolated order-watch tasks and exchange order updates can enter the local lifecycle path in real time.
- Kept scope tight: no `api.py` order-watch coverage, no trace expansion, no strategy/risk/profile changes.
- Deferred known follow-ups instead of expanding scope: duplicate `watch_orders` definition cleanup and re-evaluation of one-task-per-symbol if runtime symbol count grows.

## Next

- Do not expand trace or order-watch immediately after LS-001.
- Inspect and plan `LS-002` before any code changes: confirm the real daily stats call chain, where close events are produced, where trade recording belongs, and whether persistence is needed.
