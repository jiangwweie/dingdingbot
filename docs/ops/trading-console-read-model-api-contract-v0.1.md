# Trading Console Read-Model API Contract v0.1

Date: 2026-06-04

Namespace: `/api/trading-console/*`

Mode: operator-authenticated, read-only backend aggregation. No endpoint in this
namespace places, cancels, replaces, flattens, retries protection, starts
runtime, grants auto execution, or mutates PG.

## Shared Envelope

Every endpoint returns:

```json
{
  "read_model": "dashboard_state",
  "generated_at_ms": 1780500000000,
  "source": "trading_console_read_model_v1",
  "freshness_status": "not_live_connected",
  "warnings": [],
  "blockers": [],
  "unavailable": [],
  "data": {},
  "no_action_guarantee": {
    "places_order": false,
    "cancels_order": false,
    "replaces_order": false,
    "flattens_position": false,
    "retries_protection": false,
    "starts_runtime": false,
    "grants_auto_execution": false,
    "mutates_pg": false
  },
  "live_ready": false
}
```

Freshness values:

- `fresh`: all requested sources available and no warnings.
- `warning`: sources available but warning facts exist.
- `degraded`: one or more requested sources failed or are unavailable.
- `not_live_connected`: default state when exchange reads were not requested.

Common query parameters:

- `symbol`: optional symbol filter.
- `include_exchange`: optional bool, default `false`. When true, performs
  read-only account snapshot lookup if configured, `fetch_positions`, normal
  `fetch_open_orders`, and conditional/stop
  `fetch_open_orders(..., params={"stop": true})` through the configured
  gateway. When false, the Trading Console namespace does not call exchange or
  account snapshot readers.
- `limit`: optional bounded result limit where applicable.

## Endpoints

### `GET /api/trading-console/dashboard-state`

Purpose: one backend-owned homepage state, so the frontend does not infer
safety-critical state by stitching unrelated APIs.

`data` fields:

- `environment`
- `guards`
- `account_snapshot_summary`
- `positions.pg`
- `positions.exchange`
- `orders.pg_open`
- `orders.exchange_open`
- `orders.open_intents`
- `consistency`
- `authorization`
- `freshness`

### `GET /api/trading-console/account-risk`

Purpose: full-account risk snapshot with ownership/protection hints.

`data` fields:

- `risk_state`
- `account`
- `positions`
- `open_orders`
- `margin_facts`
- `protection_ownership`
- `freshness`

Unavailable fields remain `not_available` or appear in `unavailable`.

### `GET /api/trading-console/order-ledger`

Purpose: PG/exchange order ledger and protection grouping.

`data` fields:

- `orders`: classified order rows.
- `groups`: entry/protection groups by parent order.
- `classification_counts`
- `unavailable_fields`

Classifications:

- `matched`
- `pg_unchecked`
- `pg_only`
- `exchange_only`
- `mismatch`
- `orphan_protection`
- `unknown`

### `GET /api/trading-console/protection-health`

Purpose: front-end-safe protection state.

`data` fields:

- `status`: `protected`, `partially_protected`, `unprotected`, `unknown`, or
  `orphaned`
- `protection_orders`
- `tp_count`
- `sl_count`
- `findings`
- `actions_exposed`
- `deferred_actions`

### `GET /api/trading-console/recovery-exception-state`

Purpose: read-only recovery and exception visibility.

`data` fields:

- `recovery_tasks`
- `recovery_task_counts`
- `mismatches`
- `manual_action_required`
- `read_only_actions`
- `deferred_actions`

### `GET /api/trading-console/authorization-state`

Purpose: explicit authorization lifecycle read model.

`data` fields:

- `carrier_id`
- `authorization_id`
- `status`
- `is_actionable`
- `is_consumed`
- `is_expired`
- `is_cancelled`
- `scope_match`
- `blocking_reason`
- `scope`
- `future_action_slots`

### `GET /api/trading-console/execution-control-state`

Purpose: read-only execution-control state without wrapping execute.

`data` fields:

- `hard_gate.status`
- `hard_gate.gates`
- `execution_preview`
- `deferred_execute_endpoint`

This endpoint never creates an `ExecutionIntent` and never submits orders.

### `GET /api/trading-console/review-state`

Purpose: review records and stored trade/result facts.

`data` fields:

- `reviews`
- `filled_order_facts`
- `positions`
- `unavailable_fields`

`fee`, `fee_asset`, `funding`, and `slippage` are `not_available` in v1 unless
already stored by an injected service.

### `GET /api/trading-console/audit-chain`

Purpose: technical audit aggregation.

Query fields:

- `authorization_id`
- `intent_id`
- `order_id`
- `exchange_order_id`
- `symbol`
- `limit`

`data` fields:

- `query`
- `authorization`
- `intents`
- `orders`
- `positions`
- `reviews`
- `audit_events`
- `raw_payload_policy`

### `GET /api/trading-console/carrier-availability`

Purpose: backend-owned carrier shelf availability.

`data` fields:

- `carriers`
- `sample_data_policy`

V1 exposes the current active carrier surface and records block reasons without
front-end inference.

### `GET /api/trading-console/signal-marker-feed`

Purpose: backend event marker feed for future chart integration.

`data` fields:

- `markers`
- `chart_adapter`

### `GET /api/trading-console/api-classification`

Purpose: namespace governance and frontend migration support.

`data` fields:

- `trading_console_v1_allowed`
- `internal_or_legacy`
- `action_api_policy`
- `sample_data_policy`

## Known Gaps

- No fills table.
- No stored `client_order_id`.
- No stored fee/funding/slippage fields in the v1 order ledger.
- Optional recovery/audit tables may be absent in a deployment; absence is
  reported as `unavailable`, not as clean state.
- Chart rendering and TradingView/lightweight-charts frontend integration are
  out of scope for this backend sprint.

## Warning Policy

Post-live TP/SL open orders, orphan protection, stale facts, and PG/exchange
drift are represented as warnings/degraded facts and do not stop read-model
generation.
