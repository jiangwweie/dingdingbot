# Reconciliation Read Model Persistence — Design Plan

**Date**: 2026-05-06
**Status**: Inspect + Plan (no implementation)
**Scope**: LS-003b-RM-PERSIST

---

## 1. Inspect Summary

### 1.1 Current Reconciliation Path

**`ReconciliationService.build_read_model(symbol)`** returns `ReconciliationReadModelResult`:
- `symbol: str`
- `checked_at: int` (epoch ms)
- `mismatches: List[ReconciliationMismatch]`
- Computed properties: `is_consistent`, `severe_count`, `warning_count`

**`ReconciliationMismatch`**:
- `symbol: str`, `mismatch_type: str`, `severity: str` ("SEVERE"/"WARNING"), `reason: str`
- `local_ref: Optional[str]`, `exchange_ref: Optional[str]`
- `metadata: Dict[str, Any]`

**Mismatch types** (from `build_read_model`):

| Type | Source |
|------|--------|
| `local_state_fetch_failed` | Local state fetch failure |
| `exchange_state_fetch_failed` | Exchange state fetch failure |
| `local_position_missing_on_exchange` | Position comparison |
| `exchange_position_missing_locally` | Position comparison |
| `position_qty_mismatch` | Position comparison |
| `local_order_missing_on_exchange` | Order comparison |
| `order_status_mismatch` | Order comparison |
| `order_qty_mismatch` | Order comparison |
| `exchange_order_missing_locally` | Order comparison |
| `missing_any_protection` | Protection coverage |
| `missing_sl_protection` | Protection coverage |
| `missing_tp_protection` | Protection coverage |

### 1.2 Periodic Loop (`periodic_reconciliation.py`)

- Runs every 300s, 30s startup delay
- Calls `build_read_model(symbol)` for each symbol
- Only calls `_log_reconciliation_result(result)` — no persistence, no action
- Exceptions caught and logged, loop continues
- Strictly report-only

### 1.3 main.py Assembly (Phase 7.5)

```python
periodic_reconciliation_service = ReconciliationService(
    gateway=_exchange_gateway,
    position_mgr=_position_repo,
    order_repository=_order_repo,
)
```
- No `reconciliation_repository` injected — no persistence capability
- No `order_mgr` injected — no mutation capability
- No `lock` injected — no concurrency control

### 1.4 Existing Reconciliation Repository (startup path, NOT read model)

**Critical finding**: `PGReconciliationReportORM` / `PGReconciliationDetailORM` already exist in `pg_models.py`, and `PgReconciliationRepository` is already implemented. However, these are for the **startup reconciliation** (`ReconciliationReport` domain model) which has a different structure:
- Startup model: `ghost_orders`, `orphan_orders`, `imported_orders`, `canceled_orphan_orders`, `actions_taken`, `resolved`
- Read model: `mismatch_type`, `severity`, `local_ref`, `exchange_ref`, `metadata` — no actions, no resolution

**The two models are structurally incompatible.** The startup repo stores action/resolution state; the read model is purely observational. We **cannot reuse** `PGReconciliationReportORM` / `PGReconciliationDetailORM` for read model results — different semantics, different columns.

### 1.5 LS-002b Pattern (Daily Risk Stats)

- Dual table: aggregate + event ledger
- Idempotent writes via `event_key` uniqueness
- Fail-closed on persistence failure (blocks new trading entries)
- Factory: `create_runtime_daily_risk_stats_repository()` → `PgDailyRiskStatsRepository()`
- Migration: revision 007 (current head)

### 1.6 Migration Chain

Head = `007`. Next revision = `008`. File: `2026-05-06-008_create_read_model_reconciliation_tables.py`.

### 1.7 Retention Policy

**None exists** in the codebase. No time-based cleanup, no automated pruning. Closest is `ReconciliationRepository.clear_reports()` (manual, no time filter).

---

## 2. Minimal Persistence Design

### 2.1 Table Structure

**Recommendation: Two tables — report aggregate + mismatch detail.**

Consistent with LS-002b pattern but simpler (no event sourcing, no idempotent deltas — each loop iteration is a simple insert).

#### Table: `reconciliation_read_model_reports`

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | Integer Identity | PK | Surrogate key |
| `report_id` | String(128) | UNIQUE NOT NULL | `{checked_at_ms}:{symbol}` |
| `symbol` | String(64) | NOT NULL | Trading pair |
| `checked_at_ms` | BIGINT | NOT NULL | Epoch ms of the check |
| `is_consistent` | Boolean | NOT NULL DEFAULT true | No mismatches found |
| `total_count` | Integer | NOT NULL DEFAULT 0 | Total mismatch count |
| `severe_count` | Integer | NOT NULL DEFAULT 0 | SEVERE mismatch count |
| `warning_count` | Integer | NOT NULL DEFAULT 0 | WARNING mismatch count |
| `is_fetch_failure` | Boolean | NOT NULL DEFAULT false | True if build_read_model itself threw |
| `fetch_failure_reason` | Text | NULL | Exception message if is_fetch_failure |
| `created_at` | BIGINT | NOT NULL | Epoch ms of row creation |

Indexes:
- `idx_rdmr_symbol_time` on (`symbol`, `checked_at_ms`) — primary query pattern
- `idx_rdmr_consistent` on (`is_consistent`) — filter inconsistent reports
- `idx_rdmr_time` on (`checked_at_ms`) — time range queries

#### Table: `reconciliation_read_model_mismatches`

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| `id` | Integer Identity | PK | Surrogate key |
| `report_id` | String(128) | NOT NULL | FK to report |
| `symbol` | String(64) | NOT NULL | Redundant, for independent queries |
| `mismatch_type` | String(64) | NOT NULL | e.g. `position_qty_mismatch` |
| `severity` | String(16) | NOT NULL | "SEVERE" or "WARNING" |
| `reason` | Text | NOT NULL | Human-readable explanation |
| `local_ref` | String(128) | NULL | Local order/position identifier |
| `exchange_ref` | String(128) | NULL | Exchange order/position identifier |
| `metadata` | JSONB | NULL | Structured context (quantities, tolerances, statuses) |
| `created_at` | BIGINT | NOT NULL | Epoch ms of row creation |

Indexes:
- `idx_rdmr_mismatches_report` on (`report_id`) — detail lookup
- `idx_rdmr_mismatches_type` on (`mismatch_type`) — filter by type
- `idx_rdmr_mismatches_severity` on (`severity`) — filter by severity

### 2.2 Design Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| Report aggregate table? | Yes | Enables fast "last N checks" query without joining details |
| Mismatch detail table? | Yes | Individual mismatches must be queryable for root cause analysis |
| `report_id` generation? | `{checked_at_ms}:{symbol}` | Simple, deterministic, unique per symbol per millisecond (no collision possible) |
| `metadata` as JSONB? | Yes | Consistent with existing PG patterns (`actions_taken`, `local_data`, `exchange_data` all use JSONB) |
| `cycle_id` / `run_id`? | No | Adds complexity with no current use case. A single symbol check is the atomic unit. `checked_at_ms` approximates cycle identity if needed later. |
| Retention policy? | No (not in v1) | No existing retention mechanism in codebase. Adding one would be out of scope. Owner can decide later. |
| Repository port? | Yes, Protocol in `repository_ports.py` | Consistent with LS-002b pattern. Enables test doubles. |
| Consistent reports also saved? | **Yes** | Critical for trend analysis (consistent → inconsistent → consistent transitions). Without it, you cannot distinguish "no inconsistencies for 5 minutes" from "no checks for 5 minutes". |
| Fetch failure reports also saved? | **Yes** | Records when `build_read_model` itself throws an exception. Stores `is_fetch_failure=True` and `fetch_failure_reason`. Critical for observability. |

### 2.3 Periodic Loop Write Timing

After `_log_reconciliation_result(result)`, immediately in the same `try` block:

```python
try:
    result = await reconciliation_service.build_read_model(symbol)
    _log_reconciliation_result(result)
    await _persist_reconciliation_result(result, repository)  # NEW
except asyncio.CancelledError:
    raise
except Exception as e:
    logger.error(...)
    await _persist_reconciliation_failure(symbol, e, repository)  # NEW
```

Write is fire-and-forget (caught and logged on failure, never blocks the loop).

### 2.4 Persistence Failure Handling

| Scenario | Behavior |
|----------|----------|
| Repository write raises exception | Log error, continue loop. No retry. |
| Repository unavailable (connection error) | Same as above. Loop continues, logs only. |
| Repository not injected (None) | Skip persistence entirely, log only (current behavior). |
| Persistence failure counter? | No. Log only. Counter implies observability infrastructure, which is out of scope. |

**Key invariant**: Persistence failure **never** affects trading, blocks a symbol, creates a recovery task, cancels an order, or places an order.

---

## 3. Failure Policy

| Rule | Enforcement |
|------|-------------|
| Persistence failure must not affect trading | Repository write wrapped in try/except, exception only logged |
| Persistence failure must not block symbol | Periodic loop continues to next symbol after persistence error |
| Persistence failure must not create recovery task | No recovery logic, no task manager |
| Persistence failure must not cancel/place orders | Repository has no reference to execution path |
| `build_read_model` failure also recorded as failure report | Yes — `is_fetch_failure=True`, `fetch_failure_reason` = exception message |
| If repository unavailable, runtime continues log-only | Yes — `repository=None` graceful degradation |
| Error counter? | No — log only, no counter, no metrics, no control |

---

## 4. Boundaries (Explicitly Excluded)

- No LS-003c implementation (control path)
- No block symbol
- No create recovery task
- No auto-fix protection order
- No cancel orphan exchange order
- No place protection order
- No modify local order lifecycle
- No modify position projection
- No modify risk rules
- No modify strategy
- No modify runtime profile
- No extend Decision Trace schema
- No frontend
- No Owner Console
- No notification / P0 alert
- No portfolio / multi-asset abstraction
- No full task manager
- No reuse/modify existing `PGReconciliationReportORM` / `PGReconciliationDetailORM` (these are for startup path)
- No retention policy / cleanup
- No `cycle_id` / `run_id`
- No REST API query endpoint (out of scope)

---

## 5. Recommended Scheme

### 5.1 Table Structure

As specified in Section 2.1.

### 5.2 Repository Port

```python
# In repository_ports.py

@dataclass(frozen=True)
class ReconciliationReadModelReport:
    report_id: str
    symbol: str
    checked_at_ms: int
    is_consistent: bool
    total_count: int
    severe_count: int
    warning_count: int
    is_fetch_failure: bool = False
    fetch_failure_reason: Optional[str] = None

@dataclass(frozen=True)
class ReconciliationReadModelMismatch:
    report_id: str
    symbol: str
    mismatch_type: str
    severity: str
    reason: str
    local_ref: Optional[str] = None
    exchange_ref: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@runtime_checkable
class ReconciliationReadModelRepositoryPort(Protocol):
    async def initialize(self) -> None: ...
    async def save_report(
        self,
        report: ReconciliationReadModelReport,
        mismatches: List[ReconciliationReadModelMismatch],
    ) -> None: ...
    async def get_recent_reports(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[ReconciliationReadModelReport]: ...
    async def get_mismatches(
        self,
        report_id: str,
    ) -> List[ReconciliationReadModelMismatch]: ...
```

### 5.3 Runtime Assembly Points

1. **`main.py` Phase 7.5**: Create repository, call `initialize()`, inject into periodic task
2. **`periodic_reconciliation.py`**: Accept `Optional[ReconciliationReadModelRepositoryPort]`, call `save_report()` when not None
3. **`core_repository_factory.py`**: Add `create_runtime_reconciliation_read_model_repository()`

### 5.4 Persistence Failure Strategy

- Repository write wrapped in try/except in periodic loop
- Exception only logged, never propagated
- `repository=None` = log-only (current behavior, zero risk)
- No retry, no counter, no circuit breaker

### 5.5 Test Checklist

| Test | Description |
|------|-------------|
| `test_save_consistent_report` | Save report with `is_consistent=True`, no mismatch details |
| `test_save_mismatch_report` | Save report with 2+ mismatches, verify detail rows |
| `test_save_fetch_failure_report` | Save report with `is_fetch_failure=True`, verify `fetch_failure_reason` |
| `test_report_id_format` | Verify `{checked_at_ms}:{symbol}` format |
| `test_metadata_jsonb` | Verify metadata dict survives round-trip |
| `test_get_recent_reports_by_symbol` | Query by symbol, verify order and limit |
| `test_get_mismatches_by_report_id` | Query details, verify all fields |
| `test_persistence_failure_does_not_raise` | Mock repository raising exception, verify loop continues |
| `test_repository_none_skips_persistence` | `repository=None`, verify log-only |
| `test_orm_column_mapping` | Verify ORM column mapping matches port dataclasses |

### 5.6 Migration / Rollback Path

- **Migration**: `2026-05-06-008_create_read_model_reconciliation_tables.py` (revision 008, down_revision 007)
- Creates 2 tables, 6 indexes
- **Rollback**: Drop indexes in reverse order, then drop tables (mismatches first since reports are referenced by `report_id`)
- **ORM auto-creation**: `init_pg_core_db()` via `PGCoreBase.metadata.create_all` already auto-creates all `PGCoreBase` models — migration is required for production explicitness, but ORM models will also work in dev via `init_pg_core_db()`

### 5.7 ADR Update

- **Required**: Yes. Create `docs/adr/ADR-XXX-reconciliation-read-model-persistence.md`
- Document: why new tables vs reusing existing tables, why save consistent reports, why no cycle_id, why no retention policy

### 5.8 Owner Must-Decide Questions

| # | Question | Options | Recommendation |
|---|----------|---------|---------------|
| 1 | Save consistent reports too? | (a) Yes, save all reports (b) No, only mismatches | **(a)** — critical for trend analysis |
| 2 | Save fetch failure reports too? | (a) Yes (b) No, log only | **(a)** — critical for observability |
| 3 | Retention policy? | (a) Not now (b) Add N-day retention | **(a)** — decide later, no existing pattern |
| 4 | Add query endpoint to REST API? | (a) Not in this task (b) Include | **(a)** — out of scope, Owner Console is separate epic |

---

## 6. Alternative Schemes

### 6.1 Save Only Mismatches, Not Consistent Reports

**Pro**: Less storage (consistent reports are ~99% of rows)
**Con**: Cannot distinguish "no inconsistencies" from "no checks". Cannot plot consistency trend. Cannot detect gaps in check intervals.
**Verdict**: Not recommended. Consistent reports are lightweight (1 row per symbol per 5 min = 288 rows/symbol/day). Storage cost is negligible.

### 6.2 Save Report Summary + Mismatch Detail (Recommended)

**Pro**: Fast summary queries, detailed root cause analysis, consistent with LS-002b dual-table pattern
**Con**: Two tables, two ORM classes, slightly more code
**Verdict**: Recommended. Complexity is minimal, query flexibility is significant.

### 6.3 Write JSONL Instead of PG

**Pro**: No migration, no ORM, no connection pool risk, simple append-only write
**Con**: No query capability (need grep/jq), no Owner Console foundation, no future API integration, no indexes, no transaction safety, no integration with existing PG observability stack
**Verdict**: Not recommended. JSONL is appropriate for decision traces (low volume, append-only, human inspection only). Reconciliation reports need structured queries for root cause analysis and future Owner Console.

### 6.4 Go Straight to Frontend/API

**Why not now**: Owner Console needs its own UX design, API versioning, auth, and rate limiting. Coupling reconciliation persistence with Owner Console creates a large, indivisible delivery. Persistence is the foundation; Console is the consumer. Ship the foundation first.

---

## 7. Implementation Task Card Draft

```
Task ID: LS-003b-RM-PERSIST
Goal: Persist periodic reconciliation read model results (report + mismatches) to PG
Why: Current results are log-only, lost after each loop iteration. Persistence enables root cause analysis, trend analysis, and future Owner Console / LS-003c evaluation.

--- Non-Goals ---
- LS-003c control path (block, recover, auto-fix)
- Frontend / Owner Console / REST API query endpoint
- Notification / P0 alert
- Retention policy / cleanup
- Decision Trace schema extension
- Reuse/modify existing PGReconciliationReportORM / PGReconciliationDetailORM

--- Allowed Files ---
- src/infrastructure/repository_ports.py (add port dataclasses + protocol)
- src/infrastructure/pg_models.py (add 2 ORM classes)
- src/infrastructure/pg_reconciliation_read_model_repository.py (new file)
- src/infrastructure/core_repository_factory.py (add factory function)
- src/application/periodic_reconciliation.py (add repository param + persistence call)
- src/main.py (Phase 7.5 repository assembly)
- migrations/versions/2026-05-06-008_create_read_model_reconciliation_tables.py (new)
- tests/unit/test_ls003b_reconciliation_read_model_persistence.py (new)
- docs/adr/ADR-XXX-reconciliation-read-model-persistence.md (new)

--- Forbidden Files ---
- src/application/reconciliation.py (core file, Codex-owned)
- src/application/reconciliation_repository.py (startup path repo)
- src/infrastructure/pg_reconciliation_repository.py (startup path PG repo)
- src/application/capital_protection.py (core file)
- src/application/execution_orchestrator.py (core file)
- src/application/order_lifecycle_service.py (core file)
- src/domain/* (no domain layer changes)

--- Data Model ---

Table: reconciliation_read_model_reports
  - id: Integer Identity PK
  - report_id: String(128) UNIQUE NOT NULL  -- "{checked_at_ms}:{symbol}"
  - symbol: String(64) NOT NULL
  - checked_at_ms: BIGINT NOT NULL
  - is_consistent: Boolean NOT NULL DEFAULT true
  - total_count: Integer NOT NULL DEFAULT 0
  - severe_count: Integer NOT NULL DEFAULT 0
  - warning_count: Integer NOT NULL DEFAULT 0
  - is_fetch_failure: Boolean NOT NULL DEFAULT false
  - fetch_failure_reason: Text NULL
  - created_at: BIGINT NOT NULL

Table: reconciliation_read_model_mismatches
  - id: Integer Identity PK
  - report_id: String(128) NOT NULL
  - symbol: String(64) NOT NULL
  - mismatch_type: String(64) NOT NULL
  - severity: String(16) NOT NULL
  - reason: Text NOT NULL
  - local_ref: String(128) NULL
  - exchange_ref: String(128) NULL
  - metadata: JSONB NULL
  - created_at: BIGINT NOT NULL

--- Repository Port ---

ReconciliationReadModelReport (frozen dataclass)
ReconciliationReadModelMismatch (frozen dataclass)
ReconciliationReadModelRepositoryPort (Protocol):
  - initialize() -> None
  - save_report(report, mismatches) -> None
  - get_recent_reports(symbol?, limit) -> List[Report]
  - get_mismatches(report_id) -> List[Mismatch]

--- Runtime Integration ---

1. main.py Phase 7.5: Create repository, initialize(), inject into periodic task
2. periodic_reconciliation.py: Accept Optional[RepositoryPort]
   - After _log_reconciliation_result(), call save_report()
   - On build_read_model exception, call save_report() with is_fetch_failure=True
   - Persistence failure logged only, never propagated

--- Failure Policy ---

- Persistence failure must not affect trading
- Persistence failure must not block symbol
- Persistence failure must not create recovery task
- Persistence failure must not cancel/place orders
- repository=None → log-only (current behavior)
- No retry, no counter, no circuit breaker

--- Tests ---

- test_save_consistent_report
- test_save_mismatch_report
- test_save_fetch_failure_report
- test_report_id_format
- test_metadata_jsonb
- test_get_recent_reports_by_symbol
- test_get_mismatches_by_report_id
- test_persistence_failure_does_not_raise
- test_repository_none_skips_persistence
- test_orm_column_mapping

--- Migration ---

Revision 008, down_revision 007
Upgrade: create 2 tables, 6 indexes
Downgrade: drop 6 indexes, 2 tables (mismatches first)

--- Rollback ---

alembic downgrade 007
Remove ORM classes, port classes, repository file, factory function, periodic integration

--- ADR / Docs Update ---

- docs/adr/ADR-XXX-reconciliation-read-model-persistence.md
- Document: why new tables vs reusing existing, why save consistent reports, why no cycle_id, why no retention policy

--- Owner Open Questions ---

1. Save consistent reports too? (Recommended: Yes)
2. Save fetch failure reports too? (Recommended: Yes)
3. Retention policy? (Recommended: Not in v1)
4. REST API query endpoint? (Recommended: Not in this task)

--- Done When ---

- Periodic loop persists all reports (consistent + mismatch + fetch failure) to PG
- Persistence failure never blocks trading or periodic loop
- repository=None gracefully degrades to log-only
- Migration 008 creates tables and indexes
- All 10 tests pass
- ADR written
- Existing startup reconciliation path unchanged
```
