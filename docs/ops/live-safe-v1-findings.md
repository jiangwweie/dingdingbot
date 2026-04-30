# Live-safe v1 Findings

Use this file for program-local findings that matter during Live-safe v1.

Long-lived architecture decisions and durable collaboration rules belong in Memory MCP and `docs/adr/`.

## 2026-04-29

- Current system is treated as Sim-ready, not live-ready.
- The next priority is live-safe execution and account-level risk closure, not strategy-return optimization.
- `watch_orders` startup is the first P0 execution-chain blocker.

## 2026-04-30

- `Decision Trace Backbone v0` fits the current roadmap because it is thin-core, non-invasive, and trace-oriented rather than a broad audit platform.
- `LS-001` fits the current roadmap because it closes a live-safe runtime credibility gap without changing strategy logic, risk rules, or runtime profiles.
- Current known leftovers after `LS-001`:
  - `api.py` does not start order watch.
  - `src/infrastructure/exchange_gateway.py` still contains duplicate `watch_orders` definitions for later cleanup.
  - One order-watch task per symbol is acceptable for now but should be re-evaluated if runtime symbol count grows.
- The next real live-safe gap is `LS-002`, but it should begin with inspect + plan rather than direct implementation.
