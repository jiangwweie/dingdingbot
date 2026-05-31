# Live Read-only Observation PG Apply Result

## 1. Summary

Applied the strategy-group live read-only observation persistence DDL to the local dev PostgreSQL target and ran one observe-only evaluation cycle for:

- MI-001 SOL long
- MI-001 BNB long
- CPM-RO-001

Result: `brc_strategy_group_observations` now exists in local dev PG and contains one persisted observe-only row for each required candidate. The API helper path can read current/history from PG.

This was not a trial start, not runtime execution, not an order, not an execution intent, and not execution readiness.

Important migration-chain note: this local PG has no `alembic_version` table. To avoid running the entire migration chain or stamping unrelated history, revision 028 DDL was applied directly through the revision module against the verified local PG connection. No Alembic version stamp was written in this task.

## 2. Dev/Test PG Target

| field | value | notes |
|---|---|---|
| source | `.env.local` + `docker-compose.pg.yml` | `.env.local` is not tracked and was not committed. |
| scheme | `postgresql+asyncpg` | PostgreSQL async driver. |
| host | `localhost` | Local-only target. |
| port | `5432` | Docker port mapping. |
| db | `dingdingbot` | Local dev database from compose. |
| user | `dingdingbot` | Password masked and not reported. |
| container | `dingdingbot-pg` | `postgres:16-alpine`, healthy. |
| production check | dev/test/local | Host is local and compose file is labeled "Local PostgreSQL for Development". |

No credentials were committed or printed in full.

## 3. Migration Result

| check | before | after | status | notes |
|---|---|---|---|---|
| Alembic head | `028 (head)` | `028 (head)` | pass | Revision exists locally. |
| PG Alembic current | no revision output | no revision output | known gap | Local PG has no `alembic_version`; did not stamp. |
| Alembic target type with PG config | `PostgresqlImpl` | `PostgresqlImpl` | pass | Verified using `.env.local` DSN in-memory, masked. |
| observation table | missing | exists | pass | `brc_strategy_group_observations` created. |
| added tables | n/a | `brc_strategy_group_observations` | pass | Only the observation table was added by this task. |
| expected columns | n/a | present | pass | Includes candidate, signal, evidence, review, and non-permission fields. |
| execution/order/runtime table migration | none | none | pass | Did not run full `alembic upgrade head`; did not alter execution/order/runtime schemas. |

Observed columns:

`observation_id`, `observed_at_ms`, `strategy_group_id`, `candidate_id`, `symbol`, `side`, `signal_type`, `confidence`, `reason_codes`, `evidence_payload`, `signal_snapshot`, `invalidation_conditions`, `human_summary`, `source_type`, `market_source`, `market_bar_timestamp_ms`, `market_bar_close`, `review_windows`, `review_status`, `input_refs`, `not_order`, `not_execution_intent`, `no_execution_permission`, `no_order_permission`, `no_runtime_start`, `created_at_ms`.

## 4. Run-once Result

The run-once path used the existing safe closed-candle source:

- market source: `local_sqlite_v3_dev_closed_klines_read_only`
- source type: local SQLite fallback / dev closed bars
- external exchange write: no
- runtime start: no
- order/execution write: no

| candidate | signal_type | pg_rows | latest_observed_at_ms | market_source | sink | non_permission_flags | review_windows |
|---|---|---:|---:|---|---|---|---|
| MI-001 SOL long | `no_action` | 1 | `1779318000000` | `local_sqlite_v3_dev_closed_klines_read_only` | `recorded_pg` | all true | `24h`, `72h`, `7d` |
| MI-001 BNB long | `no_action` | 1 | `1779318000000` | `local_sqlite_v3_dev_closed_klines_read_only` | `recorded_pg` | all true | `24h`, `72h`, `7d` |
| CPM-RO-001 | `no_action` | 1 | `1779318000000` | `local_sqlite_v3_dev_closed_klines_read_only` | `recorded_pg` | all true | `4h`, `24h`, `72h`, `7d` |

Verified non-permission flags in PG:

- `not_order = true`
- `not_execution_intent = true`
- `no_execution_permission = true`
- `no_order_permission = true`
- `no_runtime_start = true`

## 5. API Verification

Verified by calling the existing application helper used by the API endpoints with `PG_DATABASE_URL` set from `.env.local`:

- `POST /api/brc/strategy-groups/live-readonly-observation/v1/run-once` path:
  - `sink_status = recorded_pg`
  - current signal count = 3
- `GET /api/brc/strategy-groups/live-readonly-observation/v1` path:
  - `sink_status = read_pg_history`
  - current signal count = 3
  - history count = 3

No web server or strategy runtime was started for this verification.

## 6. Safety Check

- 是否启动 trial？no
- 是否启动 runtime execution？no
- 是否下单？no
- 是否取消订单？no
- 是否创建 ExecutionIntent？no
- 是否授予 execution permission？no
- 是否修改杠杆？no
- 是否 set_leverage？no
- 是否转账/提现？no
- 是否修改 exchange_gateway？no
- 是否修改 execution/order/live runner？no
- 是否提交 credentials？no
- 是否把 signal 当 order？no
- 是否把 observation 当 execution readiness？no
- 是否写 execution/order 表？no
- 是否运行完整 Alembic migration chain？no

## 7. Tests / Validation

Validation run:

- `git status --short`
- `git log --oneline -12`
- `git diff --stat`
- `env | grep -E "PG|DATABASE|POSTGRES" || true`
- `.env.local` and compose inspection with secrets masked
- `docker ps`
- `python3 -m alembic heads`
- `python3 -m alembic current`
- PG Alembic current check through in-memory PG config
- PG table inventory before/after 028 DDL
- PG observation row verification query
- API helper verification for record/read current/history
- `python3 -m compileall -q src scripts`
- `python3 -m pytest -q tests/unit/test_strategy_group_live_readonly_observation.py tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py`
- `git diff --check`
- `git diff --cached --check`

## 8. Remaining Work

- Resolve local PG Alembic version governance. The local PG has no `alembic_version`, so future Alembic operations should not blindly run `upgrade head` until history is reconciled or safely stamped.
- Wire a true live/public read-only closed-bar source if Owner wants current market bars rather than local SQLite fallback.
- Add scheduled or operator-triggered observe-only cadence.
- Implement persisted forward-outcome review capture for 24h/72h/7d windows.

## 9. Next Recommended Task

True live market source integration for read-only observation.
