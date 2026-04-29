# Mock API Contract

This file defines the first-version mock API surface for the frontend scaffold.

The frontend should not call a real backend in the first iteration.

## Runtime Domain

### `getRuntimeOverview()`

Returns:

- `profile`
- `version`
- `hash`
- `frozen`
- `symbol`
- `timeframe`
- `mode`
- `backend_summary`
- `exchange_health`
- `pg_health`
- `webhook_health`
- `breaker_count`
- `reconciliation_summary`
- `server_time`
- `last_runtime_update_at`
- `last_heartbeat_at`
- `freshness_status` (`Fresh` | `Stale` | `Possibly Dead`)

### `getRuntimeSignals()`

Returns recent signals:

- `id`
- `symbol`
- `timeframe`
- `direction`
- `strategy_name`
- `score`
- `status`
- `created_at`

### `getRuntimeAttempts()`

Returns recent attempts:

- `id`
- `symbol`
- `timeframe`
- `direction`
- `strategy_name`
- `final_result`
- `filter_results_summary`
- `reject_reason`
- `timestamp`

### `getRuntimeExecutionIntents()`

Returns recent execution intents:

- `intent_id`
- `signal_id`
- `symbol`
- `status`
- `created_at`
- `updated_at`

### `getRuntimeOrders()`

Returns recent orders:

- `order_id`
- `role`
- `symbol`
- `status`
- `quantity`
- `price`
- `updated_at`

### `getRuntimeHealth()`

Returns:

- `pg_status`
- `exchange_status`
- `notification_status`
- `recent_warnings`
- `recent_errors`
- `startup_markers`
- `breaker_summary`
- `recovery_summary`

## Research Domain

### `getCandidates()`

Returns candidate list:

- `candidate_name`
- `generated_at`
- `source_profile`
- `git_commit`
- `objective`
- `review_status`
- `strict_gate_result`
- `warnings`

### `getCandidateDetail(candidateName)`

Returns:

- `candidate_name`
- `metadata`
- `best_trial`
- `top_trials`
- `fixed_params`
- `runtime_overrides`
- `constraints`
- `resolved_request`
- `rubric_evaluation`

### `getReplayContext(candidateName)`

Returns:

- `candidate_name`
- `reproduce_cmd`
- `metadata`
- `resolved_request`
- `runtime_overrides`

## Mock Data Notes

### Candidates data source assumption

The first version may assume candidate list data conceptually comes from:

- `reports/optuna_candidates/*.json`

But the generated frontend should use mock fixtures instead of reading files directly.

### Runtime staleness

The mock data should include multiple freshness examples:

1. `Fresh`
2. `Stale`
3. `Possibly Dead`

This is important because the first UI version uses manual refresh.
