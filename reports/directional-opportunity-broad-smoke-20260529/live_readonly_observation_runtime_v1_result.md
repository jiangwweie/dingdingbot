# Strategy Group Live Read-only Observation Runtime v1 Result

## 1. Summary

Implemented a safe read-only observation v1 chain for MI and CPM strategy groups:

`local closed candle source -> strategy signal evaluator -> observe-only signal contract -> process-local observation sink -> Owner Console current signal/history view -> pending 24h/72h/7d review hooks`

This does not start a trial, start runtime, create an execution intent, place or cancel orders, grant execution permission, modify leverage, transfer, withdraw, or touch exchange write paths.

## 2. Path Chosen

Path A with a bounded sink caveat.

The MI and CPM evaluator glue was already present, local closed OHLCV data was safely readable from `data/v3_dev.db`, and the API/frontend surfaces already existed. I implemented the missing one-shot observation runtime service, read-only SQLite market source, process-local observe-only sink, API run-once path, and console current/history rendering.

I did not write a PG observation sink because no dedicated live observation table/repository was found and adding a migration was outside this iteration. The response explicitly marks `pg_observation_sink = blocked_schema_gap_no_live_observation_table_found`.

## 3. Observation Coverage

| candidate | source | evaluator | current signal | sink | status | blockers |
|---|---|---|---|---|---|---|
| MI-001 SOL long | local SQLite closed 1h klines | `MI001MomentumImpulseReadOnlyEvaluator` | available, latest local bars currently `no_action` | process-local observe-only sink | one-shot observation ready | PG observation sink schema gap; scheduler not started |
| MI-001 BNB long | local SQLite closed 1h klines | `MI001MomentumImpulseReadOnlyEvaluator` | available, latest local bars currently `no_action` | process-local observe-only sink | one-shot observation ready | PG observation sink schema gap; scheduler not started; Owner review of repaired BNB evidence still pending |
| CPM-RO-001 | local SQLite closed 1h klines + derived 4h bars | `CPMRO001HistoricalEvaluator` wrapper | available, latest local bars currently `no_action` | process-local observe-only sink | one-shot observation ready | PG observation sink schema gap; scheduler not started; not proven alpha |

## 4. Signal Contract

The signal contract remains observe-only:

- allowed signal types: `no_action`, `would_enter`, `invalid`
- outputs include `not_order = true`
- outputs include `not_execution_intent = true`
- records include `no_execution_permission = true`
- records include `no_order_permission = true`
- records include `no_runtime_start = true`
- confidence is review sorting only, not order authorization

## 5. Sink / Evidence

Implemented:

- `InMemoryStrategyGroupObservationSink` for process-local observe-only history
- `StrategyGroupObservationRecord` for current/history records
- `run_strategy_group_live_readonly_observation_once()` for one-shot observe-only recording
- local read-only candle input via `LocalSqliteObservationMarketSource`

Not implemented:

- PG live observation sink, because no safe existing table/repository was found and no migration was run.
- scheduler/runner binding, because this task does not start runtime or live observation loops.

## 6. Console / API

Backend:

- `GET /api/brc/strategy-groups/live-readonly-observation/v1` now returns current observe-only signals from read-only local closed candles.
- `POST /api/brc/strategy-groups/live-readonly-observation/v1/run-once` records one observe-only snapshot into the process-local sink.

Frontend:

- `/strategy-groups` shows market source, sink status, current signals, and recent signal history.
- The console text explicitly says the panel does not start runtime or create execution intent.
- No trading action labels are exposed.

## 7. Review Hook

Each observation record carries forward review windows:

- MI: `24h`, `72h`, `7d`
- CPM: `4h`, `24h`, `72h`, `7d`

Current hook status is `pending_future_outcome_capture`. No future outcome calculation was run in this task.

## 8. Safety Check

- 是否 push？no
- 是否启动 trial？no
- 是否启动 runtime？no
- 是否启动 live runner？no
- 是否下单？no
- 是否取消订单？no
- 是否创建 execution intent？no
- 是否授予 execution permission？no
- 是否修改杠杆 / set_leverage？no
- 是否转账 / 提现？no
- 是否调用 exchange write method？no
- 是否触碰 `exchange_gateway`？no
- 是否触碰 execution/order/live runner/core files？no
- 是否把 signal 当作 order？no
- 是否把 observation 当作 execution readiness？no

## 9. Tests / Validation

Passed:

- `python3 -m compileall -q src scripts`
- `python3 -m pytest -q tests/unit/test_strategy_group_live_readonly_observation.py tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py`
- `cd gemimi-web-front && npm run lint`
- `cd gemimi-web-front && npx vitest run`
- `cd gemimi-web-front && npm run build`

Known existing warning:

- `tests/unit/test_brc_console_api_surface.py::test_strategy_group_reviewability_api_exposes_safe_shelf` still emits an SQLAlchemy coroutine cleanup warning unrelated to this observation implementation.

## 10. Remaining Work

- Add a real PG live observation/evidence sink table/repository if Owner wants observation history to become PG-backed source of truth.
- Bind the one-shot observation function to a safe scheduler or operator-triggered cadence.
- Add forward outcome capture for 24h/72h/7d review windows.
- Complete Owner review of repaired BNB evidence before any admission decision.

## 11. Next Recommended Task

BNB data coverage repair plan.
