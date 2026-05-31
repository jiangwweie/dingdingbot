# Live Read-only Observation Persistence v1 Result

## 1. Summary

Implemented PG-backed live read-only observation persistence v1 for MI and CPM candidates.

The observation chain is now:

`read-only closed candle source -> MI/CPM evaluator -> observe-only signal record -> brc_strategy_group_observations PG table/repository when PG is available -> API current/history -> Owner Console current/history display`

This is not trial start, not execution, not an order, not an execution intent, and not runtime readiness.

## 2. Path Chosen

Path B: added a minimal PG observation evidence table/repository.

Existing historical signal tables are scoped to historical experiment runs and forward-outcome evaluation. Reusing them for live read-only observations would blur historical experiment evidence with current observation evidence. A dedicated `brc_strategy_group_observations` table keeps the boundary explicit and enforces non-permission flags.

No migration upgrade/downgrade was run in this task.

## 3. Observation Coverage

| candidate | evaluator_status | market_source | sink_status | api_status | console_status | current_signal | blockers |
|---|---|---|---|---|---|---|---|
| MI-001 SOL long | wired read-only v1 | local SQLite closed 1h fallback | PG repository when available, fallback marked if unavailable | GET current, POST run-once write | current/history table shown | latest local bars currently evaluable | true live market source missing |
| MI-001 BNB long | wired read-only v1 | local SQLite closed 1h fallback | PG repository when available, fallback marked if unavailable | GET current, POST run-once write | current/history table shown | latest local bars currently evaluable | true live market source missing |
| CPM-RO-001 | wired read-only v1 | local SQLite closed 1h + derived 4h fallback | PG repository when available, fallback marked if unavailable | GET current, POST run-once write | current/history table shown | latest local bars currently evaluable | true live market source missing; not proven alpha |

## 4. Market Source

Current source:

- `LocalSqliteObservationMarketSource`
- source id: `local_sqlite_v3_dev_closed_klines_read_only`
- source type: `local_sqlite_fallback`
- reads closed bars from `data/v3_dev.db`
- does not call exchange APIs
- does not call exchange write methods
- does not start runtime

This is not a true live market source. Remaining blocker: `true_live_market_source_missing`.

## 5. PG Sink / Evidence

Added PG-backed observation evidence:

- migration: `migrations/versions/2026-05-31-028_create_strategy_group_observations.py`
- ORM: `PGBrcStrategyGroupObservationORM`
- repository: `PgStrategyGroupObservationRepository`
- table: `brc_strategy_group_observations`

The table stores:

- observation id and observed timestamp
- strategy group / candidate / symbol / side
- signal type: `no_action`, `would_enter`, or `invalid`
- reason codes, evidence payload, signal snapshot, invalidation conditions
- market source and market bar timestamp/close
- review windows and review status
- non-permission flags

Hard constraints:

- `not_order IS TRUE`
- `not_execution_intent IS TRUE`
- `no_execution_permission IS TRUE`
- `no_order_permission IS TRUE`
- `no_runtime_start IS TRUE`

## 6. API / Console

Updated API behavior:

- `GET /api/brc/strategy-groups/live-readonly-observation/v1`
  - computes current read-only signals from the closed-bar source
  - reads PG current/history when PG is available
  - falls back with explicit `blocked_pg_observation_unavailable` if PG is not configured
- `POST /api/brc/strategy-groups/live-readonly-observation/v1/run-once`
  - records current observe-only signals to PG when PG is available
  - does not write execution/order/runtime tables

Updated Owner Console:

- shows current signals by candidate
- shows recent history rows
- shows sink status (`recorded_pg`, `read_pg_history`, or explicit PG unavailable blocker)
- shows market bar timestamp
- preserves non-permissions text

## 7. Review Hook

Observation records persist review windows:

- MI: `24h`, `72h`, `7d`
- CPM: `4h`, `24h`, `72h`, `7d`

Review status is stored in `review_status` JSON. Current status is pending future outcome capture where the signal requires review, and `not_required_for_no_action_or_invalid` otherwise.

Forward-outcome review calculation is not implemented in this task.

## 8. Safety Check

- 是否启动 trial？no
- 是否启动 runtime execution？no
- 是否下单？no
- 是否取消订单？no
- 是否创建 execution intent？no
- 是否授予 execution permission？no
- 是否修改杠杆？no
- 是否 set_leverage？no
- 是否转账/提现？no
- 是否修改 exchange_gateway？no
- 是否把 signal 当 order？no
- 是否把 observation 当 execution readiness？no
- 是否运行 migration upgrade/downgrade？no

## 9. Tests / Validation

Passed:

- `python3 -m compileall -q src scripts`
- `python3 -m pytest -q tests/unit/test_strategy_group_live_readonly_observation.py tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py`
- `python3 -m pytest -q tests/unit/test_strategy_family_signal_contract.py tests/unit/test_cpm_historical_evaluator_and_experiment.py tests/unit/test_historical_ohlcv_catalog_and_builders.py tests/unit/test_strategy_signal_v2_observe_writer.py tests/unit/test_strategy_signal_v2_observe_bootstrap.py tests/unit/test_signal_pipeline_strategy_signal_v2_observe_wiring.py`
- `cd gemimi-web-front && npm run lint`
- `cd gemimi-web-front && npx vitest run`
- `cd gemimi-web-front && npm run build`
- `git diff --check`
- `git diff --cached --check`

## 10. Remaining Work

- Apply migration in the appropriate dev/test PG environment.
- Wire a true live/public read-only closed-bar source if Owner wants current market rather than local SQLite fallback.
- Add scheduled or operator-triggered observation cadence.
- Implement persisted forward-outcome review capture for 24h/72h/7d windows.

## 11. Next Recommended Task

Apply the observation persistence migration in dev/test PG and run `POST /api/brc/strategy-groups/live-readonly-observation/v1/run-once` against PG.
