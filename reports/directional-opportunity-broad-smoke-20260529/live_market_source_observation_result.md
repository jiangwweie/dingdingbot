# Live Market Source Observation Result

## 1. Summary

Integrated a true live read-only market source for strategy group observation v1 and ran one observe-only cycle into local dev PG.

The new source reads Binance USD-M public klines only. It does not use API keys, private account APIs, `exchange_gateway`, order methods, execution intents, leverage changes, transfers, withdrawals, runtime start, or trial start.

Current result:

- `POST /api/brc/strategy-groups/live-readonly-observation/v1/run-once?source=live_market` can evaluate MI/CPM candidates from latest closed Binance public 1h/4h klines.
- PG observation rows were written with `source_type = live_market_read_only`.
- `GET /api/brc/strategy-groups/live-readonly-observation/v1` reads current/history from PG and returns the latest live-market rows where available.

## 2. Path Chosen

Path B: added a minimal public kline source.

Reason: no existing safe market source exposed only public closed candles without order/private-account capabilities. The new adapter is isolated in infrastructure and has only one method: `latest_closed_candles`.

## 3. Market Source

| field | value |
|---|---|
| source id | `binance_usdm_public_klines_read_only` |
| source type | `live_market_read_only` |
| endpoint | Binance USD-M public `/fapi/v1/klines` |
| auth | none |
| API key used | no |
| private account API used | no |
| exchange gateway used | no |
| order methods exposed | no |
| timeframes used | `1h`; `4h` for CPM context |
| closed-bar handling | fetches extra bars and filters by close time; still-forming bars are excluded |
| fallback retained | `local_sqlite_v3_dev_closed_klines_read_only` |

Latest observed public-bar timestamp in the run:

- `market_bar_timestamp_ms = 1780196400000`
- source freshness: `latest_closed_public_kline`
- fallback used: `false`

## 4. Run-once Result

Ran the application helper equivalent of:

`POST /api/brc/strategy-groups/live-readonly-observation/v1/run-once?source=live_market`

| candidate | signal_type | source_type | market_source | latest_bar_close | sink | review_windows |
|---|---|---|---|---:|---|---|
| MI-001 SOL long | `no_action` | `live_market_read_only` | `binance_usdm_public_klines_read_only` | `83.1800` | `recorded_pg` | `24h`, `72h`, `7d` |
| MI-001 BNB long | `would_enter` | `live_market_read_only` | `binance_usdm_public_klines_read_only` | `740.200` | `recorded_pg` | `24h`, `72h`, `7d` |
| CPM-RO-001 | `no_action` | `live_market_read_only` | `binance_usdm_public_klines_read_only` | `2032.66` | `recorded_pg` | `4h`, `24h`, `72h`, `7d` |

Signal meaning remains observe-only:

- `no_action` means current observation does not satisfy the signal condition.
- `would_enter` means the read-only evaluator saw a potential entry signal if the strategy were later approved for trading; this task only records evidence.
- no signal creates order permission or execution permission.

## 5. PG Sink Verification

Verified rows in `brc_strategy_group_observations`.

Current PG groups include both previous local fallback rows and new live-market rows:

| candidate | source_type | signal_type | row_count | non_permission_flags |
|---|---|---|---:|---|
| MI-001 SOL long | `live_market_read_only` | `no_action` | 1 | all true |
| MI-001 BNB long | `live_market_read_only` | `would_enter` | 1 | all true |
| CPM-RO-001 | `live_market_read_only` | `no_action` | 1 | all true |
| MI-001 SOL long | `local_sqlite_fallback` | `no_action` | 1 | all true |
| MI-001 BNB long | `local_sqlite_fallback` | `no_action` | 1 | all true |
| CPM-RO-001 | `local_sqlite_fallback` | `no_action` | 1 | all true |

Verified flags:

- `not_order = true`
- `not_execution_intent = true`
- `no_execution_permission = true`
- `no_order_permission = true`
- `no_runtime_start = true`

## 6. API / Console Impact

API changes:

- `POST /api/brc/strategy-groups/live-readonly-observation/v1/run-once`
  - now accepts `source=local_sqlite_fallback` or `source=live_market`
  - default remains `local_sqlite_fallback` for deterministic local/dev behavior
- `GET /api/brc/strategy-groups/live-readonly-observation/v1`
  - reads current/history from PG when PG is available
  - after the live run, current/history include `source_type = live_market_read_only`

Console impact:

- Existing Owner Console current/history display receives the persisted record fields.
- It can show live market source, latest closed bar timestamp, signal type, sink status, and non-permissions from the API payload.
- No actionable trading labels or order/runtime permissions are introduced.

## 7. Safety Check

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
- 是否修改 execution/order/live runner？no
- 是否使用 private account API？no
- 是否提交 credentials？no
- 是否把 signal 当 order？no
- 是否把 observation 当 execution readiness？no

## 8. Tests / Validation

Validation run:

- `git status --short`
- `git log --oneline -12`
- `git diff --stat`
- `rg` checks for market data and forbidden execution/order paths
- public Binance kline source smoke for SOL/BNB/ETH latest closed 1h bars
- application helper run-once with `source_name='live_market'` and local dev PG
- PG verification query for live-market rows and non-permission flags
- `python3 -m compileall -q src scripts`
- `python3 -m pytest -q tests/unit/test_strategy_group_live_readonly_observation.py`
- `python3 -m pytest -q tests/unit/test_strategy_group_live_readonly_observation.py tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py`
- `git diff --check`
- `git diff --cached --check`

## 9. Remaining Work

- Scheduled or operator-triggered cadence is still not enabled.
- Forward-outcome review capture for 24h/72h/7d windows remains to be implemented.
- Local PG Alembic version governance remains unresolved from the previous PG apply task.

## 10. Next Recommended Task

Scheduled read-only observation runner.
