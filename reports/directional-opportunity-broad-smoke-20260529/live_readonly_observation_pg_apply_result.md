# Live Read-only Observation PG Apply Result

## 1. Summary

This task attempted the required preflight for applying the strategy-group live read-only observation persistence migration to a real dev/test PostgreSQL target and then running observation v1 for:

- MI-001 SOL long
- MI-001 BNB long
- CPM-RO-001

The apply was blocked before mutation. The current shell has no `PG_DATABASE_URL`, Alembic is configured to the local SQLite database, and `probe_pg_connectivity()` returned `False`. No migration was applied, no PostgreSQL table was created, and no observation rows were written to PG in this task.

This was not a trial start, not runtime execution, not an order, and not an execution intent.

## 2. Path Chosen

Path C: blocked PG apply.

Reason: the target database was not clearly a dev/test/local PostgreSQL database. `alembic.ini` currently points at `sqlite:///./data/v3_dev.db`, `python3 -m alembic current` reported `SQLiteImpl`, and no `PG_DATABASE_URL` was present in the current environment. Running `alembic upgrade head` in this state would apply migration 028 to SQLite, not to the requested PG source-of-truth target.

## 3. Migration Result

| check | result | evidence | notes |
|---|---:|---|---|
| Alembic head | pass | `python3 -m alembic heads` -> `028 (head)` | Revision 028 is present locally. |
| Current Alembic target | blocked | `python3 -m alembic current` -> `Context impl SQLiteImpl` | Not a PG migration target. |
| Configured URL | blocked | `alembic.ini` -> `sqlalchemy.url = sqlite:///./data/v3_dev.db` | Default migration target is local SQLite. |
| PG DSN present | blocked | `PG_DATABASE_URL=None` | No explicit PostgreSQL target in this shell. |
| PG connectivity | blocked | `probe_pg_connectivity()` -> `False` | Repository cannot connect to PG without DSN. |
| Migration 028 applied to PG | no | preflight failed | No `alembic upgrade head` was run. |
| `brc_strategy_group_observations` verified in PG | no | no PG target | Table existence was not checked against PG because no PG connection exists. |
| Affected tables | none | no mutation | No SQLite or PG schema mutation was performed. |

## 4. Run-once Result

Because the PG migration was not applied and PG connectivity is unavailable, run-once observation was not executed against PG.

| candidate | run_once_status | market_source | sink_status | current_signal | blockers |
|---|---|---|---|---|---|
| MI-001 SOL long | not run against PG | not invoked in this task | blocked_pg_target_unavailable | not written | dev/test PG target not configured |
| MI-001 BNB long | not run against PG | not invoked in this task | blocked_pg_target_unavailable | not written | dev/test PG target not configured |
| CPM-RO-001 | not run against PG | not invoked in this task | blocked_pg_target_unavailable | not written | dev/test PG target not configured |

The existing code path can still run with local SQLite closed-bar fallback and process-local or injected test sinks, but that is not the durable PG apply requested here.

## 5. API / Console Verification

No live API server or Owner Console verification was performed for a PG-backed observation run because the PG apply preflight failed.

Relevant implemented API paths remain:

- `GET /api/brc/strategy-groups/live-readonly-observation/v1`
- `POST /api/brc/strategy-groups/live-readonly-observation/v1/run-once`

Current expected behavior without PG configuration: API logic should fall back or surface `blocked_pg_observation_unavailable` rather than claiming durable PG observation history.

## 6. Safety Check

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
- 是否运行 migration upgrade/downgrade？no
- 是否写 PG observation rows？no
- 是否写 SQLite schema/table？no
- 是否把 signal 当 order？no
- 是否把 observation 当 execution readiness？no

## 7. Tests / Validation

Validation run in this task:

- `git status --short`
- `git log --oneline -12`
- `git diff --stat`
- `python3 -m alembic heads`
- `python3 -m alembic current`
- environment variable inspection for `DATABASE_URL` / `PG_DATABASE_URL` / core backend routing
- `probe_pg_connectivity()` check
- `python3 -m compileall -q src scripts`
- `python3 -m pytest -q tests/unit/test_strategy_group_live_readonly_observation.py tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py`
- `git diff --check`
- `git diff --cached --check`

## 8. Remaining Work

- Provide an explicit dev/test/local PostgreSQL DSN through `PG_DATABASE_URL`.
- Ensure Alembic is pointed at that PG target before running migration 028.
- Run `python3 -m alembic upgrade head` only after the target is verified as dev/test/local PG.
- Verify `brc_strategy_group_observations` exists in PG.
- Run observation v1 once for MI-001 SOL, MI-001 BNB, and CPM-RO-001 with PG sink enabled.
- Verify API current/history reads persisted PG records.

## 9. Next Recommended Task

Configure and confirm the dev/test `PG_DATABASE_URL` target for observation migration apply.
