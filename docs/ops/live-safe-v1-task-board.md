# Live-safe v1 Task Board

Status values: `TODO`, `SPEC`, `IMPLEMENTING`, `TESTING`, `REVIEW`, `MERGED`, `BLOCKED`, `REJECTED`.

## Milestones

- `Decision Trace Backbone v0` completed: minimal decision trace backbone added; risk decisions can be written to JSONL without affecting trading behavior on trace failure.
- `ADR-0002` completed: documented Decision Trace Backbone v0 semantics, scope, and non-goals.
- `LS-001` completed: main runtime order-watch enabled with isolated WS state; `api.py` out of scope; duplicate `watch_orders` definition remains as later cleanup.
- `LS-002` completed: runtime daily risk limits now update from projected exit deltas and full position closes; UTC reset and replay-safe accounting are active; v0 remains process-local in-memory state.

## P0

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| LS-001 | Start `watch_orders` | MERGED | Codex | Main runtime order-watch enabled with isolated WS state; `api.py` out of scope; duplicate `watch_orders` definition remains as later cleanup. |
| LS-002 | Make daily max loss/trades effective | MERGED | Codex + Claude tests | Runtime projected daily PnL and full-close trade counts now drive daily limit rejects; persistence deferred to LS-002b. |
| LS-003 | Structured runtime logs | TODO | Claude | Requires Codex task card first. |
| LS-004 | Daily equity snapshot | TODO | Claude | Requires Codex task card first. |
| LS-005 | Periodic reconciliation | TODO | Codex | Core execution safety. |
| LS-006 | Account risk state machine | TODO | Codex | ADR required before implementation. |
| LS-007 | Liquidation distance and margin safety checks | TODO | Codex | Best-effort exchange field handling. |

## P1

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| LS-101 | Recovery retry worker | TODO | TBD | After P0 state foundations. |
| LS-102 | Orphan order detector | TODO | TBD | Likely part of reconciliation. |
| LS-103 | Protection order coverage checker | TODO | TBD | Likely part of reconciliation. |
| LS-104 | Runtime health dashboard updates | TODO | TBD | After backend signals are stable. |
| LS-105 | Trace backbone boundary cleanup | TODO | Codex | Fix `decision_trace.py` logger dependency direction; keep v0 semantics stable. |
| LS-106 | Order watch hardening for multi-symbol runtime | TODO | Codex | Remove duplicate `watch_orders` definition and replace shared order-watch running flag before multi-symbol expansion. |
| LS-107 | Daily stats persistence hardening | TODO | Codex | LS-002b: persist or checkpoint daily risk stats before live expansion. |

## P2

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| LS-201 | Funding data ingestion | TODO | TBD | Not P0. |
| LS-202 | Open interest ingestion | TODO | TBD | Not P0. |
| LS-203 | Multi-asset universe manager | TODO | TBD | Not P0. |
