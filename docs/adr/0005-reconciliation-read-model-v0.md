# ADR-0005: Reconciliation Read Model v0

**Status:** Accepted  
**Date:** 2026-04-30  
**Scope:** LS-003a — read-only reconciliation discovery and reporting  

---

## 1. Context

LS-001 made real-time order updates available to the local lifecycle path. LS-002 made daily risk limits enforceable within the runtime. However, the system still has no mechanism to observe whether local order state, position state, and protection order state remain consistent with the exchange's actual state during runtime.

Startup reconciliation (`StartupReconciliationService`) runs once at boot and advances local orders against exchange state, but it does not check positions, protection coverage, or orphan orders. The more comprehensive `ReconciliationService` exists but was not wired into the runtime, and its local order query was a stub returning an empty list.

Protection order coverage has relied entirely on correct placement at entry time and accurate WebSocket updates. There is no independent read model that can detect a protection gap after a WebSocket disconnection, restart, or missed update.

## 2. Decision

LS-003a establishes a minimal, read-only reconciliation read model as the foundation for future runtime reconciliation.

Changes:

- `ExchangeGateway.fetch_open_orders(symbol)` — thin wrapper around `rest_exchange.fetch_open_orders` that keeps reconciliation callers off the raw exchange object.
- `ReconciliationService.build_read_model(symbol)` — read-only path that fetches local and exchange state, compares them, and returns a structured result.
- `ReconciliationMismatch` — lightweight dataclass representing a single discovered inconsistency.
- `ReconciliationReadModelResult` — aggregated result with mismatch list, `is_consistent`, `severe_count`, `warning_count` properties.
- `_get_local_open_orders(symbol)` — completed from stub to real PG query using `order_repository.get_open_orders()` and `get_orders_by_status()`.
- Three comparison methods: `_compare_positions_for_read_model`, `_compare_orders_for_read_model`, `_check_protection_coverage_for_read_model`.

The output is a mismatch list. No runtime state is mutated.

## 3. Semantics

### 3.1 Read-only model

`build_read_model()` is a pure observation path:

- Reads local positions via `position_mgr.list_active(symbol)` or `get_open_positions(symbol)`.
- Reads local open orders via `order_repository.get_open_orders(symbol)` and `get_orders_by_status(status, symbol)`.
- Reads exchange positions via `gateway.fetch_positions(symbol)`.
- Reads exchange open orders via `gateway.fetch_open_orders(symbol)`.
- Returns `ReconciliationReadModelResult` containing all discovered mismatches.

It does not:

- Advance order lifecycle state.
- Modify position projections.
- Block any symbol.
- Create recovery tasks.
- Place or cancel orders.
- Write to the reconciliation report repository.

### 3.2 Order mismatch

| Condition | mismatch_type | severity |
|-----------|--------------|----------|
| Local open order not found on exchange | `local_order_missing_on_exchange` | WARNING |
| Exchange open order not found locally | `exchange_order_missing_locally` | WARNING |
| Local and exchange status differ for same order | `order_status_mismatch` | WARNING |
| Local and exchange quantity differ for same order | `order_qty_mismatch` | WARNING |
| Failed to fetch local state | `local_state_fetch_failed` | SEVERE |
| Failed to fetch exchange state | `exchange_state_fetch_failed` | SEVERE |

v0 does not automatically correct order status differences.

### 3.3 Position mismatch

| Condition | mismatch_type | severity |
|-----------|--------------|----------|
| Local position exists but exchange has none | `local_position_missing_on_exchange` | SEVERE |
| Exchange position exists but local has none | `exchange_position_missing_locally` | SEVERE |
| Position quantity differs beyond dust tolerance | `position_qty_mismatch` | WARNING |

Dust tolerance: `Decimal("0.00000001")`.

v0 does not automatically repair position projections.

### 3.4 Protection coverage

| Condition | mismatch_type | severity |
|-----------|--------------|----------|
| Active position with no SL and no TP | `missing_any_protection` | SEVERE |
| Active position with SL but no TP | `missing_tp_protection` | WARNING |
| Active position with no SL (TP may exist) | `missing_sl_protection` | SEVERE |

v0 checks local orders only (from PG, which carry real `order_role` values). The `association_scope: "symbol_role_v0"` metadata declares this is symbol-level, not position-level.

v0 does not:

- Perform position-to-order-chain association.
- Validate `reduce_only` flag on exchange-side orders.
- Validate TP/SL price reasonableness.
- Auto-place missing protection orders.

## 4. Current Scope

LS-003a solves:

- Building a structured, read-only reconciliation snapshot for a single symbol.
- Comparing local open orders against exchange open orders.
- Comparing local active positions against exchange active positions.
- Detecting basic protection order coverage gaps.
- Providing the foundation for future periodic runtime reconciliation.

## 5. Non-goals

LS-003a explicitly does not:

- Start a periodic reconciliation loop in `main.py`.
- Launch runtime reconciliation tasks.
- Block symbols on mismatch.
- Create recovery tasks.
- Auto-place missing protection orders.
- Auto-cancel orphan exchange orders.
- Advance order lifecycle state.
- Repair position projections.
- Extend the frontend.
- Extend the Decision Trace schema.
- Modify runtime profiles, strategy logic, risk rules, backtester, or research.
- Introduce Regime, Portfolio, Multi-strategy, or Data Feature abstractions.

## 6. Safety Boundaries

- This change does not alter trading behavior under any code path.
- `build_read_model()` has no write side effects; this was verified via AST static analysis during pre-submit review.
- Mismatch severity levels are risk indicators, not automated execution triggers.
- Orphan, ghost, and protection coverage findings from this read model have no path into runtime action until LS-003b (periodic loop) and LS-003c (blocking / recovery) are implemented.
- The read model must not be mistaken for a complete reconciliation repair system.

## 7. Consequences

### Positive

- Reconciliation capability extends from boot-only recovery into an independent observation layer.
- Local orders, positions, and protection order coverage can be inspected in a structured, typed format.
- Provides the data foundation for runtime periodic reconciliation (LS-003b).
- Provides the data foundation for a future Owner Console reconciliation display.
- Trading behavior remains completely unchanged.

### Tradeoffs

- v0 protection coverage is symbol + order_role granularity; it cannot distinguish protection orders belonging to different positions within the same symbol.
- v0 does not validate `reduce_only` flags on exchange-side orders.
- v0 does not validate TP/SL price reasonableness.
- v0 produces no automated corrective action.
- v0 is not wired into the runtime loop.
- Exchange order role mapping via `_parse_ccxt_order` is coarse (all `reduce_only=True` orders map to `TP1`), but this only affects metadata display and does not trigger any action.

## 8. Future Extensions

The following are explicitly deferred and require separate task cards and owner approval:

| Item | Task | Prerequisite |
|------|------|-------------|
| Runtime periodic reconciliation loop | LS-003b | This ADR |
| Severe mismatch triggers symbol block | LS-003c | LS-003b |
| Recovery task creation from mismatch | LS-003c | LS-003b |
| Protection order `reduce_only` validation | LS-003 follow-up | LS-003b |
| Position/order chain precise association | LS-003 follow-up | Design review |
| Frontend read-only reconciliation display | Owner Console | Backend API |
| Decision Trace records reconciliation mismatch | Trace expansion | Owner approval |
| Automated repair | Requires separate review | All above |

## 9. Open Questions for Owner

1. **Periodic interval:** Should LS-003b use a 5-minute reconciliation interval, or is a longer cadence sufficient?
2. **Blocking threshold:** Should a single grace-confirmed mismatch trigger symbol block, or should consecutive multi-round mismatches be required first?
3. **Recovery task creation:** When should reconciliation be allowed to create recovery tasks — immediately in LS-003b, or only after a manual confirmation step?
4. **Orphan protection orders:** Should orphan TP/SL orders always remain report-only, or should the system eventually allow operator-confirmed cancellation?
5. **Position/order chain precision:** When does symbol-level protection coverage become insufficient and position-level association becomes necessary?
6. **Frontend visibility:** Should reconciliation results be displayed in a future Owner Console, and if so, at what point in the LS-003 progression?
