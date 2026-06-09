> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# Trading Console Backend Dependency Sync v0.1

Date: 2026-06-04

Source mapping: this ops copy is derived from
`docs/product/交易控制台后端依赖同步单 v0.1`. The product file remains the
original dependency note; this ops file exists because the Trading Console
backend sprint references `docs/ops/trading-console-backend-dependency-sync-v0.1.md`
as its dependency source.

This document is a dependency reference, not an action authorization. It records
read-only backend facts needed by the Trading Console frontend and separates
safe read models from future action APIs.

## Read-Model Objects

### `dashboard_state`

Needs:

- environment/profile/account scope
- GKS and startup guard status
- account snapshot summary
- open positions, open orders, and open intents
- PG/exchange consistency
- current authorization/action status
- `last_updated_at`, `exchange_snapshot_at`, `freshness_status`,
  `exchange_error`

Backend status:

- Implemented as `GET /api/trading-console/dashboard-state`.
- Defaults to non-live-connected aggregation. Exchange reads require
  `include_exchange=true`.

### `account_risk`

Needs:

- full-account positions
- balances, margin, PnL fields where available
- ownership/protection summary
- degraded/unknown/not_available semantics

Backend status:

- Implemented as `GET /api/trading-console/account-risk`.
- Uses PG/cached facts by default and optional read-only exchange positions.

### `order_ledger`

Needs:

- PG orders and safe exchange open orders
- entry/TP/SL grouping through `parent_order_id` and `oco_group_id`
- `pg_only`, `exchange_only`, `matched`, `mismatch`,
  `unknown_unmanaged`, `orphan_protection`
- `filled_qty` and `average_exec_price` where stored

Backend status:

- Implemented as `GET /api/trading-console/order-ledger`.
- `client_order_id`, fees, funding, and slippage remain `not_available`.

### `protection_health`

Needs:

- `protected`, `partially_protected`, `unprotected`, `unknown`, `orphaned`
- findings from protection-health logic where available
- no retry/cancel/replace action

Backend status:

- Implemented as `GET /api/trading-console/protection-health`.
- Current v1 derives health from order/position visibility and warnings.

### `recovery_exception_state`

Needs:

- recovery tasks if repository/table exists
- reconciliation mismatch summary
- ghost/orphan/unmanaged order visibility
- manual action required flags
- no live recovery action

Backend status:

- Implemented as `GET /api/trading-console/recovery-exception-state`.
- Missing recovery tables/services are returned as `unavailable`, not as clean
  state.

### `authorization_state`

Needs:

- active/consumed/actionable/blocking state
- carrier, strategy family, symbol, side, cap/max notional, profile/env if
  available
- future void/cancel slot documented but not implemented

Backend status:

- Implemented as `GET /api/trading-console/authorization-state`.
- Does not create, void, cancel, or modify authorizations.

### `execution_control_state`

Needs:

- final hard gate summary and per-gate status where available
- blockers/warnings/unknowns
- safe execution preview metadata only
- no execute wrapper in this sprint

Backend status:

- Implemented as `GET /api/trading-console/execution-control-state`.
- Execute action remains deferred and absent from this namespace.

### `review_state`

Needs:

- current/historical review records
- entry/protection/review chain
- realized PnL, average fill, and filled qty where already stored
- fee/funding/slippage as `not_available` unless stored

Backend status:

- Implemented as `GET /api/trading-console/review-state`.

### `audit_chain`

Needs:

- query by `authorization_id`, `intent_id`, `order_id`, `exchange_order_id`
- authorization -> intent -> order -> TP/SL -> position -> review -> audit
  event chain
- no credential or unsafe raw payload leakage

Backend status:

- Implemented as `GET /api/trading-console/audit-chain`.
- Raw payload policy is `masked_or_omitted`.

### `carrier_availability`

Needs:

- carrier list
- availability/block reason
- symbol/side/cap/max-notional where available
- recent authorization/execution/protection state
- no sample data as truth source

Backend status:

- Implemented as `GET /api/trading-console/carrier-availability`.
- v1 reports the current active BNB carrier and marks sample data as not used.

### `signal_marker_feed`

Needs:

- signal, authorization, entry, fill, TP/SL, recovery, close, review markers
- chart-ready feed for later TradingView/lightweight-charts integration

Backend status:

- Implemented as `GET /api/trading-console/signal-marker-feed`.
- Chart adapter remains backend-feed-only; frontend chart dependency is out of
  scope.

### `api_classification`

Needs:

- allowed Trading Console v1 endpoints
- internal/legacy/testnet/dev-only API classification
- action API deferral policy

Backend status:

- Implemented as `GET /api/trading-console/api-classification`.

## Deferred Action APIs

The following are not part of the read-only sprint:

- execute live trial
- cancel order
- replace order
- flatten position
- retry missing protection
- retry/resolve recovery task
- void/cancel authorization
- runtime start
- auto-execution enablement
- credential or API-key update

## Safety Semantics

- `include_exchange=false` is the default for live-safe read models.
- `include_exchange=true` performs only read-only exchange calls where a gateway
  is already configured.
- BNB TP/SL, orphan protection, stale data, and PG/exchange drift are warnings
  and degraded facts, not sprint-stopping conditions.
- Unknown or unavailable sources are explicitly represented in each response.
