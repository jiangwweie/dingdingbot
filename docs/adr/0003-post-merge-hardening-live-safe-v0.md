# ADR-0003 Post-merge Hardening For Live-safe v0

## Status

Proposed

## Context

The first live-safe v0 feature set is now landed:

- Decision Trace Backbone v0
- LS-001 Order Watch Runtime Closure
- LS-002 Daily Risk Limits Runtime Closure

These changes are aligned with the current roadmap:

- thin core
- live-safe first
- non-invasive runtime hardening
- traceability without broad platform expansion

Post-merge review found that the current implementation direction is sound, but a small set of hardening items should be treated as explicit next-step work instead of being left as implicit technical debt.

The goal of this ADR is not to reopen the design of the landed features. It is to record which follow-up items are required before multi-symbol runtime expansion or live progression, and which items are acceptable v0 debt for now.

## Decision

The project should treat the following items as explicit hardening backlog for the next iteration.

### Next-iteration fixes

1. `decision_trace.py` should stop importing `src.infrastructure.logger` directly.
   - The `application` layer should use a local standard logger instead of depending on infrastructure logging helpers.

2. `src/infrastructure/exchange_gateway.py` should remove the duplicate `watch_orders` definition.
   - The duplicate definition is currently dead code because Python keeps the later definition.
   - It is not a current blocker, but it increases ambiguity and maintenance risk.

3. Order-watch runtime state should be hardened before multi-symbol expansion.
   - The current shared `_order_ws_running` pattern is acceptable only for the present single-symbol runtime assumption.
   - Before enabling broader runtime symbol scope, order-watch stop/run state must no longer allow one watcher to stop others unintentionally.

### Must-solve before live expansion

4. Daily risk stats persistence must be added before live expansion.
   - `LS-002` v0 intentionally uses process-local in-memory daily stats.
   - This is acceptable for the current hardening phase.
   - It is not acceptable for live expansion because process restart resets daily loss and daily trade counters.
   - This follow-up should be treated as `LS-002b`.

### Acceptable v0 debt

5. `JsonlTraceSink` may remain synchronous for now.
   - This is a hot-path performance concern and should be tracked.
   - It is not currently treated as a correctness blocker because trace is best-effort observability, not a runtime dependency.

6. `PositionProjectionService.project_exit_fill()` may remain dense for now.
   - Internal splitting is reasonable later if behavior stays stable.
   - It should not force an immediate refactor while the runtime semantics are still being hardened.

7. Error-path and concurrency test coverage should continue to expand, but missing edge-path tests alone do not invalidate the current v0 feature direction.

## Consequences

### Positive

- Makes the live-safe v0 follow-up backlog explicit.
- Separates current correctness issues from acceptable temporary debt.
- Preserves the thin-core roadmap by preventing opportunistic scope growth.
- Clarifies what must happen before multi-symbol runtime expansion and before live progression.

### Constraints

- Do not reopen feature scope unless a hardening item requires it.
- Keep follow-up tasks focused:
  - trace boundary cleanup
  - order-watch runtime hardening
  - daily stats persistence
- Do not use these hardening tasks as a reason to introduce Regime, Portfolio, Multi-strategy, or Data Feature abstractions.
