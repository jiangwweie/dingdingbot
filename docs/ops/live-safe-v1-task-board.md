# Live-safe v1 Task Board

Status values: `TODO`, `SPEC`, `IMPLEMENTING`, `TESTING`, `REVIEW`, `MERGED`, `BLOCKED`, `REJECTED`.

## P0

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| LS-001 | Start `watch_orders` | MERGED | Codex | Main runtime order-watch enabled with isolated WS state; `api.py` out of scope; duplicate `watch_orders` definition remains as later cleanup. |
| LS-002 | Make daily max loss/trades effective | TODO | Codex + Claude tests | Codex owns design and core wiring. |
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

## P2

| ID | Task | Status | Owner | Notes |
| --- | --- | --- | --- | --- |
| LS-201 | Funding data ingestion | TODO | TBD | Not P0. |
| LS-202 | Open interest ingestion | TODO | TBD | Not P0. |
| LS-203 | Multi-asset universe manager | TODO | TBD | Not P0. |
