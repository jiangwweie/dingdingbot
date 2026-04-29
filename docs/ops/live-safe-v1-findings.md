# Live-safe v1 Findings

Use this file for program-local findings that matter during Live-safe v1.

Long-lived architecture decisions and durable collaboration rules belong in Memory MCP and `docs/adr/`.

## 2026-04-29

- Current system is treated as Sim-ready, not live-ready.
- The next priority is live-safe execution and account-level risk closure, not strategy-return optimization.
- `watch_orders` startup is the first P0 execution-chain blocker.
