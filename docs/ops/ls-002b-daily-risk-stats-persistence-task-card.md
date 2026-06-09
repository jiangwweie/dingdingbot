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

# Task ID
LS-002b / LS-107 Daily Risk Stats Persistence

## Goal
Persist `CapitalProtectionManager` daily risk stats to PG so runtime restarts restore the current UTC day's projected daily realized PnL and closed-trade count instead of resetting them to process-local memory defaults.

This task implements the Owner-approved design:

- PG aggregate + event ledger.
- Single v0 scope key: `runtime:default`.
- No portfolio or multi-account semantics.
- No Decision Trace schema expansion.
- Fail closed for new entries when daily stats restore or write-through is unavailable.

## Background
LS-002 made daily max loss and daily trade count effective during one runtime process by updating `CapitalProtectionManager` from exit projection results:

- projected realized PnL accumulates from exit-fill deltas
- daily trade count increments only when a position lifecycle first reaches full close
- UTC day boundaries reset stats
- duplicate/replayed exit updates do not double count while the process remains alive

The remaining LS-002b gap is restart safety. Today, restart recreates `DailyTradeStats()` in memory, so daily loss and trade count can be undercounted after a process restart. Live-safe v1 needs persistence before further live expansion.

## Non-goals
Do not implement or modify:

- strategy logic or strategy parameters
- backtest or research behavior
- runtime profile semantics or live trading config
- order sizing defaults
- risk rule semantics beyond persistence availability fail-closed
- frontend, dashboard, or console display work
- reconciliation behavior, LS-003c, or account risk state machine work
- multi-asset, portfolio, multi-account, or exchange-account semantics
- funding-inclusive or full account-true daily PnL reconstruction
- historical rebuild from old exchange orders or archived tests
- Decision Trace schema expansion
- a cross-repository transaction that includes both position projection save and daily stats persistence

## Context
- Current program: Live-safe v1.
- Codex owns architecture, core execution files, merge readiness, and ADR updates.
- This task is core execution/risk work and should not be delegated as one broad Claude task.
- Claude may only receive bounded subtasks later if Codex creates smaller cards with explicit file ownership.
- Return/drawdown numbers are evaluation dimensions, not hard constraints.

## Allowed files
Implementation may touch only the files needed for this persistence slice:

- `src/application/capital_protection.py`
- `src/application/execution_orchestrator.py`
- `src/application/position_projection_service.py`
- `src/domain/models.py`
- `src/infrastructure/repository_ports.py`
- `src/infrastructure/pg_models.py`
- `src/infrastructure/pg_daily_risk_stats_repository.py` (new)
- `src/infrastructure/core_repository_factory.py`
- `src/main.py`
- `migrations/versions/<new_ls002b_daily_risk_stats_revision>.py`
- `tests/unit/test_ls002b_daily_risk_stats_persistence.py` (new)
- `tests/unit/test_ls002_daily_risk_limits.py`
- `tests/unit/test_tm002_exit_projection_observability.py`
- `docs/adr/0004-daily-risk-limits-runtime-closure-v0.md`
- `docs/adr/<new_ls002b_daily-risk-stats-persistence_adr>.md` if Codex chooses a separate ADR
- `docs/ops/live-safe-v1-task-board.md`
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/live-safe-v1-findings.md`

## Forbidden files
Do not modify:

- `src/application/order_lifecycle_service.py`
- `src/infrastructure/exchange_gateway.py`
- `src/application/reconciliation.py`
- `src/application/startup_reconciliation_service.py`
- `src/application/runtime_config.py`
- `src/application/config_manager.py`
- `src/application/backtester.py`
- `src/application/backtest_config.py`
- `src/application/strategy_optimizer.py`
- `src/application/signal_pipeline.py`
- `src/domain/strategy*.py`
- `src/interfaces/`
- frontend files
- runtime profile files or config seed files
- exchange credential, live trading, or order-sizing defaults
- archived tests under `archive/`

## Data Table Design
Add two PG tables.

### `daily_risk_stats_aggregates`
Purpose: fast restore and pre-order checks for one UTC risk day.

Columns:

- `scope_key TEXT NOT NULL`
- `stats_date DATE NOT NULL`
- `realized_pnl NUMERIC(38, 18) NOT NULL DEFAULT 0`
- `trade_count INTEGER NOT NULL DEFAULT 0`
- `last_event_key TEXT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints and indexes:

- primary key: `(scope_key, stats_date)`
- check: `trade_count >= 0`
- index: `(scope_key, updated_at)`

### `daily_risk_stats_events`
Purpose: idempotent event ledger for exit projection accounting.

Columns:

- `event_key TEXT PRIMARY KEY`
- `scope_key TEXT NOT NULL`
- `stats_date DATE NOT NULL`
- `source TEXT NOT NULL` with v0 value `exit_projection`
- `position_id TEXT NOT NULL`
- `signal_id TEXT NOT NULL`
- `exit_order_id TEXT NOT NULL`
- `delta_exit_qty NUMERIC(38, 18) NOT NULL DEFAULT 0`
- `delta_realized_pnl NUMERIC(38, 18) NOT NULL DEFAULT 0`
- `trade_count_delta INTEGER NOT NULL DEFAULT 0`
- `occurred_at TIMESTAMPTZ NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints and indexes:

- unique event id via primary key `event_key`
- check: `trade_count_delta IN (0, 1)`
- check: `delta_exit_qty >= 0`
- index: `(scope_key, stats_date, created_at)`
- index: `(position_id, exit_order_id)`

Notes:

- Store `Decimal` values as `NUMERIC`, never `float`.
- Do not store sensitive values.
- Do not introduce `portfolio_id`, `account_id`, or exchange-account columns in v0.
- `scope_key` is always `runtime:default` in LS-002b.

## Repository Interface Design
Add a narrow repository port, preferably in `src/infrastructure/repository_ports.py`.

Recommended domain/application-facing shapes:

- `DailyRiskStatsSnapshot`
  - `scope_key: str`
  - `stats_date: date`
  - `realized_pnl: Decimal`
  - `trade_count: int`
- `DailyRiskStatsEvent`
  - `event_key: str`
  - `scope_key: str`
  - `stats_date: date`
  - `position_id: str`
  - `signal_id: str`
  - `exit_order_id: str`
  - `delta_exit_qty: Decimal`
  - `delta_realized_pnl: Decimal`
  - `trade_count_delta: int`
  - `occurred_at: datetime`
- `DailyRiskStatsWriteResult`
  - `snapshot: DailyRiskStatsSnapshot`
  - `inserted: bool`

Required repository methods:

- `initialize() -> None`
- `restore_or_create(scope_key: str, stats_date: date) -> DailyRiskStatsSnapshot`
- `record_event(event: DailyRiskStatsEvent) -> DailyRiskStatsWriteResult`
- `get(scope_key: str, stats_date: date) -> Optional[DailyRiskStatsSnapshot]`

Repository behavior:

- `record_event(...)` must insert the event and update the aggregate in one PG transaction.
- Duplicate `event_key` must not double count.
- On duplicate event, return the current aggregate snapshot with `inserted=False`.
- Aggregate update uses `realized_pnl += delta_realized_pnl` and `trade_count += trade_count_delta`.
- Repository must not depend on exchange gateway, strategy, runtime profile, reconciliation, or frontend code.

## CapitalProtection Interface Design
Update `CapitalProtectionManager` around one write-through entrypoint:

- Add optional daily risk stats repository injection.
- Add restore method or constructor-time restore path controlled by `main.py`.
- Add `record_exit_projection(...)` as the single atomic application entrypoint for daily stats updates.
- Keep existing `record_projected_realized_pnl_delta(...)` and `record_closed_trade(...)` only if needed for backward compatibility/tests, but orchestrator must stop calling them directly.

Recommended `record_exit_projection(...)` input:

- `position_id`
- `signal_id`
- `exit_order_id`
- `delta_exit_qty`
- `delta_realized_pnl`
- `just_closed`
- `occurred_at`
- idempotency `event_key`

Behavior:

- Reset/choose current UTC stats date before applying.
- Write event + aggregate through repository if available.
- Mirror the returned aggregate into in-memory `DailyTradeStats`.
- If repository write fails, mark daily stats persistence unhealthy and fail closed for future new entries.
- If no repository is configured in runtime mode, treat daily stats persistence as unavailable and fail closed for new entries.

## Runtime Assembly Order
In `src/main.py`, assemble daily stats before `CapitalProtectionManager` begins accepting new entry checks:

1. Initialize exchange gateway and account snapshot as today.
2. Build runtime-driven `CapitalProtectionConfig` as today.
3. Create PG session maker as today.
4. Create and initialize `PgDailyRiskStatsRepository`.
5. Restore or create today's aggregate for `scope_key="runtime:default"` using UTC date.
6. Instantiate `CapitalProtectionManager` with:
   - restored snapshot
   - daily stats repository
   - `scope_key="runtime:default"`
   - trace service and config hash as today
7. If restore fails:
   - continue runtime startup only if existing execution, exits, protection handling, shutdown, and reconciliation can still operate
   - mark `CapitalProtectionManager` daily stats persistence unavailable
   - block new entries through `pre_order_check`
8. Construct `ExecutionOrchestrator`.
9. Inject `PositionProjectionService` as today.
10. Keep startup reconciliation and circuit-breaker rebuild order unchanged.

Do not move startup reconciliation into daily stats restore. Do not make reconciliation responsible for restoring daily risk stats.

## Failure Policy
Required policy:

- Daily stats restore failure must fail closed for new entries.
- Daily stats write-through failure must fail closed for new entries after the failed write.
- Fail-closed must use existing `pre_order_check` deny behavior so the existing Decision Trace deny path records the rejection.
- Do not extend Decision Trace schema.

The fail-closed state must not block:

- exits
- protection order placement or handling
- order lifecycle updates
- shutdown
- startup or periodic reconciliation
- circuit-breaker rebuild

Recommended deny reason:

- `DAILY_RISK_STATS_UNAVAILABLE`

Recommended message:

- daily risk stats persistence is unavailable; new entries are blocked until restore/write-through recovers.

Implementation note:

- This task does not need automatic recovery after a write failure. A later hardening task may add retry/recovery if needed. For LS-002b, fail closed and make the condition observable through logs and existing deny trace.

## Idempotency Event Key Design
Use a deterministic event key for each projected exit accounting event:

```text
daily-risk:v1:{scope_key}:{stats_date}:{position_id}:{exit_order_id}:{projected_exit_qty_after}
```

Where:

- `scope_key` is always `runtime:default`.
- `stats_date` is the UTC risk date used for aggregate accounting.
- `position_id` is the local projected position id.
- `exit_order_id` is the local exit order id.
- `projected_exit_qty_after` is the cumulative projected exit quantity for that exit order after applying this projection.

Rationale:

- Replaying the same exit update after a successful stats write produces the same key and does not double count.
- Later cumulative fills for the same exit order produce a different `projected_exit_qty_after` and can apply only the new delta.
- The key does not require exchange order ids or account semantics.

Required supporting change:

- `ExitProjectionResult` may need to expose `exit_order_id` and `projected_exit_qty_after` so the orchestrator or `CapitalProtectionManager` can build the key without re-reading position internals.

Known limitation:

- If position projection save succeeds and daily stats event/aggregate write fails before the event is recorded, a replay may see the exit as already projected and may not be able to reconstruct the missing stats event from the current v0 result alone. This crash/write window is accepted for LS-002b because Owner approved not placing position projection save and daily stats persistence in the same DB transaction.

Future hardening path:

- Move position projection and daily stats event/aggregate update into a single transaction boundary when both repositories share a unit of work.
- Or add a recovery scanner that compares `positions.projected_exit_fills` against `daily_risk_stats_events` and backfills missing events with explicit operator-visible audit logs.
- Or persist a pending daily-stats event before/with projection and finalize aggregate after projection save.

## Migration Design
Add one Alembic migration.

Upgrade:

- create `daily_risk_stats_aggregates`
- create `daily_risk_stats_events`
- add the indexes and checks listed above

Downgrade:

- drop event indexes
- drop aggregate indexes
- drop `daily_risk_stats_events`
- drop `daily_risk_stats_aggregates`

Migration constraints:

- Additive only.
- No data migration from old in-memory state.
- No historical rebuild.
- No runtime profile/config changes.
- No seed values beyond rows created by runtime repository restore.

## Tests
Add targeted tests only. Do not run long suites without Owner confirmation.

Required unit tests:

- repository `restore_or_create(...)` creates an empty aggregate for today's UTC date.
- repository `restore_or_create(...)` restores existing aggregate values as `Decimal` and `int`.
- repository `record_event(...)` inserts event and updates aggregate in one operation.
- duplicate `event_key` does not double count PnL or trade count.
- second cumulative fill for same exit order with different `projected_exit_qty_after` applies only the new delta.
- `CapitalProtectionManager` initializes from restored stats and daily limit checks use restored values.
- restore failure marks daily stats persistence unavailable and `pre_order_check` denies new entries.
- write-through failure in `record_exit_projection(...)` marks daily stats persistence unavailable and later `pre_order_check` denies new entries.
- deny from persistence unavailable reuses existing risk decision trace path and does not require schema changes.
- orchestrator calls only `record_exit_projection(...)` for daily stats after exit projection.
- exit projection failures still do not update daily stats.
- exits/protection handling path is not blocked by daily stats persistence unavailable.
- UTC day boundary creates/uses a new aggregate and resets in-memory stats for the new day.

Suggested targeted commands:

```bash
pytest tests/unit/test_ls002b_daily_risk_stats_persistence.py
pytest tests/unit/test_ls002_daily_risk_limits.py
pytest tests/unit/test_tm002_exit_projection_observability.py
```

Migration verification:

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Run migration verification only when the local PG/Alembic environment is available and approved if it is long or environment-mutating.

## Rollback Path
Code rollback:

- Revert the repository injection and `record_exit_projection(...)` write-through changes.
- Restore LS-002 in-memory daily stats behavior if needed.
- Keep the new PG tables unused; they are additive and safe to leave in place during emergency code rollback.

Database rollback:

- If no deployed runtime depends on the tables, run the Alembic downgrade for the LS-002b revision.
- If runtime has already written rows, prefer leaving tables in place until an operator confirms no diagnostic/audit value is needed.

Operational rollback:

- If daily stats persistence fails in production-like sim, new entries should remain blocked.
- Existing exits, protection orders, shutdown, and reconciliation should continue.
- Operator may restart after fixing PG connectivity; restore should unblock new entries only after successful aggregate restore.

## ADR Update Requirements
Update ADR documentation before merge:

- Either extend `docs/adr/0004-daily-risk-limits-runtime-closure-v0.md` with an LS-002b section or create a new ADR and link it from ADR-0004.
- Document Owner decisions:
  - PG aggregate + event ledger.
  - `scope_key="runtime:default"`.
  - no portfolio / multi-account semantics.
  - accepted non-transactional crash window between position projection save and daily stats write.
  - fail-closed for new entries on restore/write-through failure.
  - fail-closed must not block exits, protection handling, shutdown, or reconciliation.
  - no Decision Trace schema expansion.
- Document the known limitation and future hardening paths.
- Preserve LS-002 daily stats semantics: projected realized PnL, full-close trade count, UTC day boundary.

## Done When
- Daily stats restore from PG occurs before new entry checks can pass.
- Exit projection daily stats updates are persisted through event ledger + aggregate.
- Duplicate events do not double count.
- Restart restores today's aggregate into `CapitalProtectionManager`.
- Restore/write-through failure blocks new entries via `pre_order_check`.
- Exits, protection handling, shutdown, and reconciliation remain outside the block.
- Existing Decision Trace deny path records fail-closed new-entry denials without schema expansion.
- Tests listed above pass.
- ADR is updated with the accepted limitation and hardening path.
- No forbidden files changed.

## Stop And Ask If
- Implementation requires changing strategy, backtest, research, runtime profiles, frontend, reconciliation, LS-003c, exchange credentials, or order sizing defaults.
- Implementation needs to add portfolio, account, exchange-account, or multi-asset semantics.
- A cross-repository transaction becomes necessary to satisfy tests.
- Existing order/position repository boundaries make the repository atomicity impossible without a broader unit-of-work decision.
- The implementation needs a new Decision Trace event type or schema field.

## Owner Still Needs To Confirm
1. Should `DAILY_RISK_STATS_UNAVAILABLE` be the accepted deny reason code for restore/write-through fail-closed, or should it reuse an existing daily limit reason?
2. Should LS-002b account events to the current UTC runtime date at write time, or to `exit_order.filled_at` UTC date when available? Recommendation for v0: current UTC runtime date, preserving LS-002 reset semantics.
3. Should app startup continue in no-new-entry mode when PG daily stats restore fails, or should startup become fatal? Recommendation: continue startup with new entries blocked so exits/protection/reconciliation can still run.
4. Is keeping the additive PG tables during emergency code rollback acceptable, with downgrade reserved for explicit operator cleanup?
5. Should LS-002b include any manual operator command to inspect daily stats, or defer all visibility work to later console/ops tasks?
