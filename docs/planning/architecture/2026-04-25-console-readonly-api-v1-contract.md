# Console Readonly API v1 Contract

> Date: 2026-04-25
> Status: Planning
> Scope: first backend contract set for the frontend console to replace mock data page by page

---

## 1. Goal

Provide a stable, read-only API surface for the new console.

This contract is intentionally page-oriented:

1. keep frontend replacement from mock to backend low-risk
2. avoid raw table-shaped API design
3. keep runtime truth aligned with Sim-1
4. avoid write paths, hot change paths, or review write-back

---

## 2. Current decisions

1. API v1 is read-only only.
2. Runtime domain comes first, then Research domain, then Config Snapshot.
3. Response shape should stay close to the current frontend mock contract where that contract is already workable.
4. If current mock fields are toy-level or misleading, backend contract wins and frontend mock should be updated once.
5. `src/interfaces/api.py` remains the compatibility host for now, but new console routes should be grouped so they can later move into smaller modules.

---

## 3. Domain order

### P0 - Runtime observation

1. `GET /api/runtime/overview`
2. `GET /api/runtime/portfolio`
3. `GET /api/runtime/positions`
4. `GET /api/runtime/events`
5. `GET /api/runtime/health`

### P1 - Runtime details and research entry

1. `GET /api/runtime/signals`
2. `GET /api/runtime/attempts`
3. `GET /api/runtime/execution/intents`
4. `GET /api/runtime/execution/orders`
5. `GET /api/research/candidates`
6. `GET /api/research/candidates/{candidate_name}`
7. `GET /api/research/candidates/{candidate_name}/review-summary`
8. `GET /api/research/replay/{candidate_name}`

### P2 - Research depth and config preview

1. `GET /api/research/backtests`
2. `GET /api/research/backtests/{report_id}`
3. `GET /api/research/compare/candidates`
4. `GET /api/research/compare/backtests`
5. `GET /api/config/snapshot`

---

## 4. Contract rules

### 4.1 Common rules

1. All responses are read-only projections.
2. All timestamps must be ISO-8601 strings in UTC.
3. Monetary and ratio fields returned to frontend may be numbers for display, but backend internal computation remains `Decimal`.
4. Every page-level response must be self-sufficient enough to render that page without extra N+1 calls in v1.
5. Empty state is valid and must not be treated as error.

### 4.2 Freshness rules

`runtime/overview` and `runtime/health` must expose:

1. `server_time`
2. `last_runtime_update_at`
3. `last_heartbeat_at`
4. `freshness_status`

Allowed `freshness_status` values:

- `Fresh`
- `Stale`
- `Possibly Dead`

### 4.3 Health rules

`breaker_summary` and `recovery_summary` must remain separate objects.

Do not collapse them into one health number.

### 4.4 Replay rules

`research/replay/{candidate_name}` means replay context only.

It does not imply candle playback or chart replay in v1.

---

## 5. Endpoint contracts

### 5.1 `GET /api/runtime/overview`

Purpose:

- render Runtime / Overview hero and health summary

Response:

```json
{
  "profile": "sim1_eth_runtime",
  "version": "1",
  "hash": "0279ca9c45b37fad",
  "frozen": true,
  "symbol": "ETH/USDT:USDT",
  "timeframe": "1h",
  "mode": "SIM-1",
  "backend_summary": "intent=postgres, order=sqlite, position=sqlite",
  "exchange_health": "OK",
  "pg_health": "OK",
  "webhook_health": "OK",
  "breaker_count": 0,
  "reconciliation_summary": "candidate_orders=0 failed_orders=0",
  "server_time": "2026-04-25T01:00:00Z",
  "last_runtime_update_at": "2026-04-25T00:59:58Z",
  "last_heartbeat_at": "2026-04-25T00:59:59Z",
  "freshness_status": "Fresh"
}
```

Suggested source of truth:

1. runtime config provider
2. startup reconciliation service
3. breaker / recovery state service
4. notifier / exchange / pg connectivity summary

### 5.2 `GET /api/runtime/portfolio`

Purpose:

- render Runtime / Portfolio

Response:

```json
{
  "total_equity": 10000.0,
  "available_balance": 8200.0,
  "unrealized_pnl": 120.5,
  "total_exposure": 1800.0,
  "daily_loss_used": 150.0,
  "daily_loss_limit": 1000.0,
  "max_total_exposure": 10000.0,
  "leverage_usage": 1.0,
  "positions": [
    {
      "symbol": "ETH/USDT:USDT",
      "direction": "LONG",
      "quantity": 0.5,
      "entry_price": 3200.0,
      "current_price": 3240.0,
      "unrealized_pnl": 20.0,
      "pnl_percent": 0.0125,
      "leverage": 2
    }
  ]
}
```

Suggested source of truth:

1. account snapshot service
2. v3 position / account repositories or exchange snapshot
3. capital protection derived limits

### 5.3 `GET /api/runtime/positions`

Purpose:

- render Runtime / Positions detail page

Suggested response:

Use the same position item shape as `portfolio.positions`, plus:

1. `position_id`
2. `margin_used`
3. `tp_status`
4. `sl_status`
5. `opened_at`
6. `updated_at`

### 5.4 `GET /api/runtime/events`

Purpose:

- render operator timeline

Response:

```json
[
  {
    "id": "evt_001",
    "timestamp": "2026-04-25T00:58:00Z",
    "category": "EXECUTION",
    "severity": "SUCCESS",
    "message": "ENTRY filled for ETH/USDT:USDT",
    "related_entities": ["intent_001", "order_001"]
  }
]
```

Allowed categories:

- `STARTUP`
- `RECONCILIATION`
- `BREAKER`
- `RECOVERY`
- `WARNING`
- `ERROR`
- `SIGNAL`
- `EXECUTION`

### 5.5 `GET /api/runtime/health`

Purpose:

- render Runtime / Health

Response:

```json
{
  "pg_status": "OK",
  "exchange_status": "OK",
  "notification_status": "OK",
  "recent_warnings": [],
  "recent_errors": [],
  "startup_markers": {
    "runtime_config": "PASSED",
    "exchange_gateway": "PASSED",
    "permission_check": "PASSED",
    "startup_reconciliation": "PASSED",
    "breaker_rebuild": "PASSED",
    "signal_pipeline": "PASSED"
  },
  "breaker_summary": {
    "total_tripped": 0,
    "active_breakers": [],
    "last_trip_time": null
  },
  "recovery_summary": {
    "pending_tasks": 0,
    "completed_tasks": 0,
    "last_recovery_time": null
  }
}
```

### 5.6 `GET /api/runtime/signals`

Purpose:

- render recent fired signals

Minimum item:

1. `id`
2. `symbol`
3. `timeframe`
4. `direction`
5. `strategy_name`
6. `score`
7. `status`
8. `created_at`

### 5.7 `GET /api/runtime/attempts`

Purpose:

- render recent attempts and filter outcomes

Minimum item:

1. `id`
2. `symbol`
3. `timeframe`
4. `direction`
5. `strategy_name`
6. `final_result`
7. `filter_results_summary`
8. `reject_reason`
9. `timestamp`

### 5.8 `GET /api/runtime/execution/intents`

Minimum item:

1. `intent_id`
2. `signal_id`
3. `symbol`
4. `status`
5. `created_at`
6. `updated_at`

### 5.9 `GET /api/runtime/execution/orders`

Minimum item:

1. `order_id`
2. `role`
3. `symbol`
4. `status`
5. `quantity`
6. `price`
7. `updated_at`

### 5.10 `GET /api/research/candidates`

Purpose:

- render candidate list

Minimum item:

1. `candidate_name`
2. `generated_at`
3. `source_profile`
4. `git_commit`
5. `objective`
6. `review_status`
7. `strict_gate_result`
8. `warnings`

Suggested source:

1. `reports/optuna_candidates/*.json`
2. optional future index cache

### 5.11 `GET /api/research/candidates/{candidate_name}`

Purpose:

- render candidate detail

Minimum fields:

1. `candidate_name`
2. `metadata`
3. `best_trial`
4. `top_trials`
5. `fixed_params`
6. `runtime_overrides`
7. `constraints`
8. `resolved_request`
9. `rubric_evaluation`

### 5.12 `GET /api/research/candidates/{candidate_name}/review-summary`

Purpose:

- render Candidate Review page

Response:

```json
{
  "candidate_name": "optuna_candidate_opt_xxx",
  "review_status": "PASS_STRICT_WITH_WARNINGS",
  "strict_v1": {
    "total_trades": {"value": 144, "threshold": 100, "status": "PASS"},
    "sharpe_ratio": {"value": 1.36, "threshold": 1.0, "status": "PASS"},
    "total_return": {"value": 0.4888, "threshold": 0.30, "status": "PASS"},
    "max_drawdown": {"value": 0.2173, "threshold": 0.25, "status": "PASS"},
    "win_rate": {"value": 0.4792, "threshold": 0.45, "status": "PASS"},
    "params_at_boundary": {"value": false, "threshold": false, "status": "PASS"}
  },
  "warnings": ["sortino_ratio_missing_or_suspect"],
  "notes": []
}
```

### 5.13 `GET /api/research/replay/{candidate_name}`

Purpose:

- render replay context page

Minimum fields:

1. `candidate_name`
2. `reproduce_cmd`
3. `metadata`
4. `resolved_request`
5. `runtime_overrides`

### 5.14 `GET /api/research/backtests`

Purpose:

- render backtest list

Minimum item:

1. `id`
2. `candidate_ref`
3. `symbol`
4. `timeframe`
5. `start_date`
6. `end_date`
7. `status`
8. `metrics`

### 5.15 `GET /api/research/backtests/{report_id}`

Purpose:

- render backtest detail

Minimum fields:

1. list item base fields
2. summary metrics
3. order summary
4. artifact metadata

### 5.16 `GET /api/research/compare/candidates`

Purpose:

- render candidate comparison page

Minimum response:

```json
[
  {
    "metric": "sharpe_ratio",
    "baseline": 1.0,
    "candidateA": 1.36,
    "candidateB": 1.12,
    "diffA": 0.36,
    "diffB": 0.12
  }
]
```

### 5.17 `GET /api/research/compare/backtests`

Purpose:

- render backtest comparison page

Use the same compare row shape as candidate compare.

### 5.18 `GET /api/config/snapshot`

Purpose:

- render Config / Snapshot

Minimum fields:

1. `identity`
2. `market`
3. `strategy`
4. `risk`
5. `execution`
6. `backend`
7. `source_of_truth_hints`

---

## 6. Backend module split target

v1 does not require a full API rewrite, but new console API should move toward:

1. `src/interfaces/api_console_runtime.py`
2. `src/interfaces/api_console_research.py`
3. `src/interfaces/api_console_config.py`
4. `src/application/readmodels/...`

`src/interfaces/api.py` may keep re-exporting or mounting these routers during transition.

---

## 7. Current execution plan

### Step 1

Freeze the field names shared between:

1. `gemimi-gemimi-web-front/src/types/index.ts`
2. this contract
3. backend response models

### Step 2

Implement P0 Runtime read models first.

### Step 3

Expose P0 runtime endpoints.

### Step 4

Switch Runtime / Overview first from mock to backend.

### Step 5

Switch Portfolio, Positions, Events, Health after Overview is stable.

### Step 6

Implement Research list/detail/replay endpoints.

### Step 7

Implement Config Snapshot endpoint.

---

## 8. Non-goals

1. No write API.
2. No review write-back.
3. No config editing.
4. No runtime hot reload.
5. No one-shot `api.py` rewrite.
