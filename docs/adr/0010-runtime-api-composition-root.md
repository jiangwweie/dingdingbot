# ADR-0010 Runtime/API Composition Root Boundary

## Status

Accepted

Date: 2026-05-25

Runtime effect: architecture governance only

Trading permission effect: no runtime profile, strategy parameter, or real-live permission change

## Context

Phase 4 runtime/testnet smoke exposed a lifecycle ownership debt between
`src/main.py` and `src/interfaces/api.py`.

Before this ADR, `main.py` assembled the execution runtime for embedded API
mode, while `api.py` also assembled an execution runtime in standalone uvicorn
lifespan mode. That created two practical composition roots for exchange
gateways, repositories, services, orchestration, startup reconciliation, and
shutdown cleanup.

The API/frontend surface is currently lower priority. The current priority is
runtime safety and lifecycle clarity before P4-005 or any later
tiny-live-style rehearsal design.

## Decision

`src/main.py` is the only execution-runtime composition root.

The embedded runtime path owns creation and shutdown for:

- exchange gateway;
- runtime repositories;
- account/capital/campaign/GKS/startup-guard services;
- execution orchestrator;
- startup reconciliation and protection-health checks;
- background runtime tasks;
- embedded uvicorn server handle.

The API process receives this runtime through a `RuntimeContext` bound to
`app.state.runtime`. Existing API module globals remain as a compatibility
adapter for older endpoints and tests, but they are populated from the
main-owned context. `RuntimeContext.start()` / `RuntimeContext.shutdown()`
record the active owner state and route shutdown requests through the
main-owned shutdown event and startup-guard reset; detailed resource cleanup
remains in `main.py`, which created those resources.

Standalone `uvicorn src.interfaces.api:app` is intentionally degraded to an
HTTP/config/read-only shell. It must not create exchange gateways,
capital-protection managers, execution orchestrators, startup reconciliation,
or protection-health execution state. Runtime control and execution endpoints
return unavailable when no embedded runtime context is bound.

## Consequences

- Embedded API is the primary runtime control path.
- Standalone API is not a second runtime owner.
- Shutdown ownership is explicit: objects created by `main.py` are shut down by
  `main.py`.
- `api_console_runtime.py` should read runtime state through the bound context
  first. Its remaining module-global reads are compatibility behavior, not the
  target architecture.
- This ADR does not authorize real live trading, exchange-account actions,
  runtime profile changes, sizing changes, or strategy optimization.

## Follow-ups

- If API/frontend work becomes active again, convert remaining route modules
  from module-global helpers to FastAPI request/state dependencies.
- If standalone API needs runtime authority in the future, it must call the
  same runtime builder used by `main.py`; it must not reintroduce local
  execution wiring inside `api.py`.
