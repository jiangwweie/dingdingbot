# ADR-0004 Daily Risk Limits Runtime Closure v0

## Status

Accepted

## Context

Before LS-002, the system already had daily risk limit configuration and pre-order checks for:

- `daily_max_loss`
- `daily_max_trades`

However, the daily stats state that powered those checks was not connected to the runtime execution path.

In practice this meant:

- the check logic existed
- the runtime daily stats stayed at their initialized defaults
- the limits appeared to exist, but did not truly become effective during runtime

Live-safe hardening required these daily risk limits to become real runtime controls rather than dead-path checks.

LS-001 already enabled exchange order updates to flow into the local order lifecycle, which created the missing foundation for updating runtime daily stats from exit fills.

## Decision

LS-002 v0 introduces runtime daily risk limit closure with the following behavior:

- `pre_order_check()` performs a UTC day-boundary reset before evaluating daily limits
- daily PnL is accumulated from exit-delta projected realized PnL
- daily trade count increases only when a position lifecycle reaches its first full close
- partial exits affect daily PnL but do not increase daily trade count
- `PositionProjectionService.project_exit_fill()` exposes a lightweight `ExitProjectionResult`
- `ExecutionOrchestrator` updates `CapitalProtectionManager` daily stats immediately after exit projection
- duplicate or replayed exit updates do not produce duplicate accounting
- v0 uses process-local in-memory state only

## Semantics

### `daily_max_loss`

`daily_max_loss` in LS-002 v0 is based on runtime position projection semantics.

- It uses projected realized PnL, not full account-true daily loss
- It is accumulated incrementally from each exit delta
- Partial TP and partial SL realized PnL are included as they happen
- It does not claim to fully include funding, entry fees, or every exchange-side account cost

This is intentional for v0. The goal is to activate runtime daily loss control using the current execution truth available inside the live-safe path, not to solve the complete account PnL problem.

### `daily_max_trades`

`daily_max_trades` in LS-002 v0 counts completed position lifecycles.

- One position lifecycle reaching its first complete close counts as one daily trade
- TP1, TP2, and other partial exits do not increase daily trade count on their own
- Replay of an already-processed close must not increase the count again

This means the count is tied to full lifecycle completion, not to each exit leg.

### UTC reset

LS-002 v0 uses UTC day boundaries.

- `pre_order_check()` resets daily stats if a new UTC day is detected
- daily stats recording also resets before applying new values
- no local timezone is introduced
- no exchange-local timezone is introduced

UTC is the current system-wide time baseline and remains the day-splitting rule for v0.

### storage

LS-002 v0 uses in-memory process-local daily stats.

- runtime restart resets daily stats to zero
- this is a known v0 limitation, not treated as a bug
- persistent recovery belongs to future `LS-002b`

## Current Scope

LS-002 v0 only solves:

- runtime daily stats wiring
- making daily loss and daily trade count effective within a single runtime process
- defining the intended semantics for exit-delta PnL and full-close trade counting

It does not attempt to become a full account risk subsystem.

## Non-goals

LS-002 v0 does not implement:

- PG or SQLite persistence
- rebuilding daily stats from historical orders or positions
- a full account risk state machine
- complete funding and fee-inclusive daily loss accounting
- portfolio-level daily risk
- Regime, Portfolio, Multi-strategy, or Data Feature abstractions
- frontend display work
- Decision Trace schema expansion
- runtime profile changes
- strategy logic changes
- backtester or research changes

## Safety Boundaries

LS-002 v0 stays within these boundaries:

- it does not change strategy signals
- it does not change single-trade risk sizing
- it does not change runtime profile semantics
- it does not change TP or SL logic
- it does not change the backtest engine
- daily stats only influence the pre-order daily limit checks
- restart-reset behavior remains an accepted v0 limitation

The feature is intentionally limited to live-safe runtime risk closure, not broader trading behavior changes.

## Consequences

### Positive

- daily limits move from "checks exist but stats are dead" to "runtime effective inside one process"
- partial exit and full close semantics become explicit
- live-safe capability is strengthened
- the system gains a practical base for future account-level risk evolution

### Tradeoffs

- v0 daily PnL is not full account-true daily loss
- v0 has no persistence, so restart resets daily stats
- the "full close equals one trade" rule may need review if future workflows support add-ons or multi-entry lifecycles
- fee and funding semantics may need future enhancement

## Future Extensions

Future extensions may include, but are not part of LS-002 v0:

- `LS-002b`: PG persistence and restart recovery for daily stats
- a more complete account daily PnL definition
- explicit funding and fee inclusion
- account risk state machine integration
- frontend display of daily risk state
- reuse of Decision Trace for daily limit rejection explanation, but only when a concrete need exists

## Open Questions

Owner decisions that may be needed later:

- When does daily stats persistence become mandatory?
- Should funding and broader fee accounting be included in daily loss?
- If future workflows support add-ons or multi-entry lifecycles, does one position lifecycle still equal one daily trade?
- Should daily risk state be shown in the frontend?
- Should daily limit rejection be represented explicitly in Decision Trace?
