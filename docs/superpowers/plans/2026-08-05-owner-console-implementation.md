# Owner Console Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the authenticated, manually refreshed, read-only Owner Console for overview, signals, trades, trade causality, and deterministic review without adding any exchange mutation or background runtime.

**Architecture:** A single-process FastAPI service reads bounded PostgreSQL facts through an independent read-only role and fetches public Binance USD-M candles through the existing credential-free market source. A Vite-built React SPA consumes typed OpenAPI responses, owns only presentation state, and is served by the existing Nginx instance. PostgreSQL remains the internal runtime authority; public candles remain display-only; the browser never computes economic or lifecycle conclusions.

**Tech Stack:** Python, FastAPI, Pydantic v2, SQLAlchemy Core, asyncpg, Uvicorn, argon2-cffi, PyOTP, itsdangerous, TypeScript strict, React, Vite, React Router, TanStack Query, TanStack Table, Radix UI Primitives, Tailwind CSS, TradingView Lightweight Charts, React Hook Form, Zod, openapi-typescript, openapi-fetch, Vitest, React Testing Library, MSW, Playwright, pnpm, Corepack, Nginx, systemd

## Global Constraints

- Scope is **Phase 1 only**: no StrategyGroup pause/resume, StrategyUniverse mutation, controlled exit, order entry, order cancellation, or exchange write endpoint.
- The Read API must not import or call `controlled_exit`, `dispatch_exchange_command`, venue mutation adapters, or Binance private credential factories.
- The Read API uses one independent PostgreSQL role with `default_transaction_read_only=on`, `statement_timeout=3000ms`, `pool_size=1`, and `max_overflow=1`.
- Every page Read Model is assembled inside one short `REPEATABLE READ READ ONLY` transaction; Binance public candle I/O never occurs inside that transaction.
- No PostgreSQL migration, database view, analysis projection, refresh worker, Redis, WebSocket, SSE, runtime JSON/Markdown output, or automatic network refresh is added.
- Lists default to 50 rows and reject limits above 100; candles default to 300 rows and reject limits above 500.
- Signal list defaults to a 7-day window; trade and review lists default to a 30-day window. Every list accepts a shifted bounded window no wider than 90 days.
- The overview may show only the latest CapacityClaim account snapshot, labeled `Latest Admission Snapshot` with its timestamp. It must never label that value as current or real-time account equity.
- The browser preserves money, prices, PnL, risk, and R multiples as strings. Numeric conversion is allowed only inside the chart adapter for visual coordinates and cannot feed business conclusions.
- TanStack Query sets `refetchInterval=false`, `refetchOnWindowFocus=false`, `refetchOnReconnect=false`, `retry=false`, `staleTime=Infinity`, and `gcTime=Infinity`.
- The only network requests after first load are explicit Owner actions: page refresh, first chart expansion, and chart refresh.
- Session Cookie properties are `HttpOnly`, `Secure`, `SameSite=Strict`; one new login invalidates the previous Session; API restart invalidates all Sessions.
- Owner username, Argon2id password hash, TOTP seed, Session signing key, and database DSN come from exact systemd encrypted credentials. The application package does not read repository configuration files.
- UI uses the confirmed B specification: `#0B0E11` background, `#181A20` content, `#2B3139` dividers, `#EAECEF` primary text, `#848E9C` secondary text, `#F0B90B` emphasis, `#0ECB81` success, and `#F6465D` danger.
- Layout maximum width is 1160px; top navigation is 44px; table rows are 38px; table headers are 30px; buttons and inputs are 30–32px.
- Owner API budget is one process, `CPUQuota=25%`, `MemoryMax=256M`, `TasksMax=32`, zero background tasks, and at most two PostgreSQL connections.
- Existing Observation, Entry, Lifecycle, and Reconciliation services, their slice, and their exchange authority remain unchanged.

## Source Documents

- Design: `docs/superpowers/specs/2026-08-05-owner-console-and-programmatic-review-design.md`
- Owner language: `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- Kernel invariants: `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`
- Data authority: `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- Deployment resource contract: `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`

## File Structure

### Backend application and infrastructure

| Path | Responsibility |
|---|---|
| `src/trading_kernel/application/owner_console/models.py` | Frozen requests, fact records, response models, cursors, evidence references, and envelopes |
| `src/trading_kernel/application/owner_console/overview.py` | Overview classification and aggregation |
| `src/trading_kernel/application/owner_console/signals.py` | Signal list/detail assembly |
| `src/trading_kernel/application/owner_console/trades.py` | Trade list assembly |
| `src/trading_kernel/application/owner_console/causality.py` | Lifecycle stages and chart annotations |
| `src/trading_kernel/application/owner_console/programmatic_review.py` | Deterministic review classification and templates |
| `src/trading_kernel/infrastructure/pg_owner_read_repository.py` | All bounded SQL and read-only transaction handling |
| `src/trading_kernel/infrastructure/owner_market_data.py` | Public candle request and serialization boundary |

### HTTP and authentication

| Path | Responsibility |
|---|---|
| `src/trading_kernel/interfaces/owner_console_http/app.py` | FastAPI factory, lifespan, middleware, and router registration |
| `src/trading_kernel/interfaces/owner_console_http/auth.py` | Password/TOTP verification, login throttling, signed cookie, and single Session store |
| `src/trading_kernel/interfaces/owner_console_http/dependencies.py` | Settings, engine/repository dependency, auth dependency, and clock |
| `src/trading_kernel/interfaces/owner_console_http/errors.py` | Stable API error envelope and exception mapping |
| `src/trading_kernel/interfaces/owner_console_http/routes/*.py` | Auth, overview, signals, tickets, review, and candles endpoints |
| `scripts/owner_console/run_api.py` | Exact systemd credential loading and Uvicorn Unix Socket startup |
| `scripts/owner_console/export_openapi.py` | Deterministic OpenAPI export for generated frontend types |

### Frontend

| Path | Responsibility |
|---|---|
| `frontend/owner-console/src/app/*` | Router, providers, authenticated shell, navigation, and query client |
| `frontend/owner-console/src/api/*` | Generated schema, typed client, response helpers, and MSW fixtures |
| `frontend/owner-console/src/components/ui/*` | B-spec primitives with no SaaS default styling |
| `frontend/owner-console/src/components/tables/*` | Dense tables, inline expansion, cursor controls, and empty/error states |
| `frontend/owner-console/src/components/charts/*` | Lazy-loaded Lightweight Charts adapter |
| `frontend/owner-console/src/features/*` | Overview, signals, trades, review, and auth feature modules |
| `frontend/owner-console/src/pages/*` | Route boundaries, URL parsing, Suspense, and feature-page composition |
| `frontend/owner-console/src/styles/*` | CSS variables, reset, typography, density, and layout |
| `frontend/owner-console/e2e/*` | Playwright login, routing, manual refresh, and no-auto-request tests |

### Deployment and verification

| Path | Responsibility |
|---|---|
| `requirements-owner-console.txt` | Owner API production-only Python dependencies |
| `deploy/owner-console/systemd/*` | Independent API unit and resource slice |
| `deploy/owner-console/nginx/*` | Existing HTTPS server include and login rate-limit zone |
| `deploy/owner-console/postgresql/owner-console-read-role.sql` | Idempotent read-role grants and read-only defaults |
| `deploy/owner-console/README.md` | Installation, credential rotation, verification, and rollback |
| `tests/trading_kernel/architecture/test_owner_console_architecture.py` | Read-only and isolation guardrails |
| `tests/trading_kernel/integration/test_owner_console_read_repository.py` | PostgreSQL query, transaction, cursor, and consistency verification |
| `tests/trading_kernel/unit/owner_console/*` | Pure assembler, review, auth, and market-data tests |
| `tests/trading_kernel/interfaces/test_owner_console_http.py` | ASGI authentication and route contract tests |

---

### Task 1: Lock the Phase 1 package and architecture boundaries

**Files:**
- Create: `requirements-owner-console.txt`
- Modify: `requirements-dev.txt`
- Create: `src/trading_kernel/application/owner_console/__init__.py`
- Create: `src/trading_kernel/interfaces/owner_console_http/__init__.py`
- Create: `src/trading_kernel/interfaces/owner_console_http/routes/__init__.py`
- Create: `scripts/owner_console/__init__.py`
- Create: `tests/trading_kernel/architecture/test_owner_console_architecture.py`

**Interfaces:**
- Consumes: Existing `src/trading_kernel` package and `deploy/systemd` four-worker boundary.
- Produces: Importable Owner Console packages and permanent tests forbidding mutation authority.

- [ ] **Step 1: Write the failing architecture tests**

```python
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OWNER_ROOTS = (
    REPO_ROOT / "src/trading_kernel/application/owner_console",
    REPO_ROOT / "src/trading_kernel/interfaces/owner_console_http",
)

FORBIDDEN = (
    "application.controlled_exit",
    "application.dispatch_exchange_command",
    "build_binance_usdm_venue_adapter",
    "TRADING_KERNEL_API_KEY",
    "TRADING_KERNEL_API_SECRET",
)


def test_owner_console_packages_exist_and_have_no_exchange_write_authority() -> None:
    for root in OWNER_ROOTS:
        assert root.is_dir()
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN:
                assert marker not in source, f"{path}: {marker}"


def test_kernel_systemd_directory_remains_four_workers_plus_slice() -> None:
    expected = {
        "brc-trading-kernel.slice",
        "brc-trading-kernel-observation-worker.service",
        "brc-trading-kernel-entry-worker.service",
        "brc-trading-kernel-lifecycle-worker.service",
        "brc-trading-kernel-reconciliation-worker.service",
    }
    assert {path.name for path in (REPO_ROOT / "deploy/systemd").iterdir()} == expected
```

- [ ] **Step 2: Run the tests and verify the missing packages fail**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/architecture/test_owner_console_architecture.py -v
```

Expected: FAIL because the Owner Console package directories do not exist.

- [ ] **Step 3: Add the package skeleton and dependency manifests**

`requirements-owner-console.txt`:

```text
-r requirements.txt

argon2-cffi>=23.1.0,<26.0.0
fastapi>=0.116.0,<1.0.0
itsdangerous>=2.2.0,<3.0.0
pyotp>=2.9.0,<3.0.0
uvicorn>=0.35.0,<1.0.0
```

Append to `requirements-dev.txt`:

```text
httpx>=0.28.0,<1.0.0
```

Each new `__init__.py` contains only a one-line package docstring and no imports with side effects.

- [ ] **Step 4: Run focused architecture and dependency checks**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/architecture/test_owner_console_architecture.py -v
.venv/bin/ruff check tests/trading_kernel/architecture/test_owner_console_architecture.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add requirements-owner-console.txt requirements-dev.txt src/trading_kernel/application/owner_console src/trading_kernel/interfaces/owner_console_http scripts/owner_console tests/trading_kernel/architecture/test_owner_console_architecture.py
git commit -m "build(console): establish read-only package boundaries"
```

### Task 2: Define immutable API models, exact serialization, and bounded cursors

**Files:**
- Create: `src/trading_kernel/application/owner_console/models.py`
- Create: `tests/trading_kernel/unit/owner_console/__init__.py`
- Create: `tests/trading_kernel/unit/owner_console/factories.py`
- Create: `tests/trading_kernel/unit/owner_console/test_models.py`

**Interfaces:**
- Consumes: Pydantic v2 and existing string identities.
- Produces: `ApiEnvelope[T]`, `Freshness`, `EvidenceRef`, `PageCursor`, list queries, page facts, all public Read Models, and named test fact factories consumed by later tasks.

- [ ] **Step 1: Write failing serialization and cursor tests**

```python
from decimal import Decimal

import pytest

from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    Freshness,
    MoneyMetric,
    PageCursor,
    decode_cursor,
    encode_cursor,
)


def test_money_and_evidence_serialize_without_float_conversion() -> None:
    metric = MoneyMetric(value=Decimal("3.5100"), unit="USDT")
    evidence = EvidenceRef(kind="review", identity="review:ticket-1", occurred_at_ms=5)

    assert metric.model_dump(mode="json", exclude_none=True) == {"value": "3.5100", "unit": "USDT"}
    assert evidence.kind == "review"


def test_cursor_round_trip_is_exact_and_rejects_invalid_input() -> None:
    encoded = encode_cursor(PageCursor(sort_ms=1_800_000_000_000, identity="ticket:1"))
    assert decode_cursor(encoded) == PageCursor(
        sort_ms=1_800_000_000_000,
        identity="ticket:1",
    )
    with pytest.raises(ValueError, match="cursor"):
        decode_cursor("not-base64")


def test_freshness_values_are_closed() -> None:
    assert [item.value for item in Freshness] == [
        "fresh",
        "stale",
        "unavailable",
        "contradictory",
    ]
```

- [ ] **Step 2: Run the tests and verify the models are missing**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_models.py -v
```

Expected: FAIL with `ModuleNotFoundError` or missing model imports.

- [ ] **Step 3: Implement the model contract**

The file must use frozen models with forbidden extra fields:

```python
from __future__ import annotations

import base64
import json
from decimal import Decimal
from enum import StrEnum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    CONTRADICTORY = "contradictory"


class MoneyMetric(FrozenModel):
    value: Decimal | None
    unit: Literal["USDT", "R", "count", "fraction"]
    unavailable_reason: str | None = None

    @field_serializer("value")
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class EvidenceRef(FrozenModel):
    kind: Literal["signal", "admission", "ticket", "event", "command", "incident", "settlement", "review"]
    identity: str
    occurred_at_ms: int


LifecycleStageKey = Literal[
    "signal",
    "admission",
    "entry",
    "protection",
    "tp_runner",
    "exit",
    "reconciliation",
    "review",
]


class PageCursor(FrozenModel):
    sort_ms: int
    identity: str


DataT = TypeVar("DataT")


class ApiEnvelope(FrozenModel, Generic[DataT]):
    snapshot_id: str
    generated_at: str
    source_watermark: str | None
    freshness: Freshness
    data: DataT
```

`encode_cursor` serializes `PageCursor.model_dump(mode="json")` using sorted compact JSON and URL-safe Base64 without padding. `decode_cursor` restores padding, validates the JSON through `PageCursor.model_validate`, and raises `ValueError("invalid page cursor")` for every malformed input.

Add these exact request bounds:

```python
class BoundedWindowQuery(FrozenModel):
    from_ms: int
    to_ms: int
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = None

    @model_validator(mode="after")
    def _validate_window(self) -> "BoundedWindowQuery":
        if self.to_ms <= self.from_ms:
            raise ValueError("time window must be increasing")
        if self.to_ms - self.from_ms > 90 * 86_400_000:
            raise ValueError("time window exceeds 90 days")
        return self
```

Define all response and internal fact models named in the design: `OwnerOverview`, `SignalListItem`, `SignalAdmissionDetail`, `TradeListItem`, `TradeCausalityDetail`, `LifecycleStageView`, `ChartAnnotation`, `ProgrammaticTradeReview`, and `ReviewCenterSummary`. Every conclusion-bearing model includes `evidence: tuple[EvidenceRef, ...]`.

`factories.py` defines explicit helpers `overview_facts`, `signal_item_facts`, `trade_item_facts`, `trade_causality_facts`, and `programmatic_review_facts`. Each helper constructs a complete valid frozen fact model and applies only named `model_copy(update=...)` overrides; production models do not expose test-only `example()` methods.

- [ ] **Step 4: Run model tests and static checks**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_models.py -v
.venv/bin/ruff check src/trading_kernel/application/owner_console/models.py tests/trading_kernel/unit/owner_console/test_models.py
.venv/bin/mypy src/trading_kernel/application/owner_console/models.py tests/trading_kernel/unit/owner_console/test_models.py
```

Expected: PASS with Decimal values serialized as strings and invalid cursors rejected.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/application/owner_console/models.py tests/trading_kernel/unit/owner_console
git commit -m "feat(console): define immutable read models"
```

### Task 3: Establish the read-only PostgreSQL engine and transaction boundary

**Files:**
- Create: `src/trading_kernel/infrastructure/pg_owner_read_repository.py`
- Create: `tests/trading_kernel/integration/owner_console_support.py`
- Create: `tests/trading_kernel/integration/test_owner_console_read_repository.py`

**Interfaces:**
- Consumes: SQLAlchemy `AsyncEngine` and existing `pg_models` tables.
- Produces: `create_owner_read_engine(dsn: str) -> AsyncEngine`, `owner_read_transaction(engine)`, and `PostgresOwnerReadRepository(connection)`.

- [ ] **Step 1: Write failing integration tests for role and transaction settings**

```python
import sqlalchemy as sa
import pytest
from sqlalchemy.exc import DBAPIError

from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    create_owner_read_engine,
    owner_read_transaction,
)


async def test_owner_read_transaction_is_repeatable_read_and_read_only(owner_read_dsn: str) -> None:
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        async with owner_read_transaction(engine) as connection:
            read_only = await connection.scalar(sa.text("SHOW transaction_read_only"))
            isolation = await connection.scalar(sa.text("SHOW transaction_isolation"))
            timeout = await connection.scalar(sa.text("SHOW statement_timeout"))
        assert read_only == "on"
        assert isolation == "repeatable read"
        assert timeout == "3s"
    finally:
        await engine.dispose()


async def test_owner_read_role_cannot_insert(owner_read_dsn: str) -> None:
    engine = create_owner_read_engine(owner_read_dsn)
    try:
        with pytest.raises(DBAPIError):
            async with owner_read_transaction(engine) as connection:
                await connection.execute(
                    sa.text("INSERT INTO brc_monitor_current "
                            "(monitor_key, owner_status, summary, intervention, updated_at_ms, projection_version) "
                            "VALUES ('forbidden', 'running', 'x', 'x', 1, 1)")
                )
    finally:
        await engine.dispose()
```

`owner_console_support.py` creates a disposable database, applies Alembic head, creates a login role with SELECT grants, sets the three role defaults, yields an encoded DSN, then drops the database and role.

- [ ] **Step 2: Run the integration tests and verify the boundary is absent**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/integration/test_owner_console_read_repository.py -v
```

Expected: FAIL because `create_owner_read_engine` and `owner_read_transaction` do not exist.

- [ ] **Step 3: Implement the engine and transaction context**

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


def create_owner_read_engine(dsn: str) -> AsyncEngine:
    return create_async_engine(
        dsn,
        pool_size=1,
        max_overflow=1,
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "application_name": "brc_owner_console",
                "default_transaction_read_only": "on",
                "statement_timeout": "3000",
            }
        },
    )


@asynccontextmanager
async def owner_read_transaction(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as raw:
        connection = await raw.execution_options(isolation_level="REPEATABLE READ")
        transaction = await connection.begin()
        try:
            await connection.execute(sa.text("SET TRANSACTION READ ONLY"))
            yield connection
            await transaction.commit()
        except BaseException:
            await transaction.rollback()
            raise
```

`PostgresOwnerReadRepository` stores only the active `AsyncConnection`. It exposes no `insert`, `update`, `delete`, `commit`, or runtime projection refresh method.

- [ ] **Step 4: Verify isolation, connection limits, and existing integration tests**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/integration/test_owner_console_read_repository.py -v
.venv/bin/pytest tests/trading_kernel/integration/test_pg_unit_of_work.py -v
.venv/bin/ruff check src/trading_kernel/infrastructure/pg_owner_read_repository.py tests/trading_kernel/integration/owner_console_support.py tests/trading_kernel/integration/test_owner_console_read_repository.py
```

Expected: PASS; the read role cannot write and the existing kernel Unit of Work remains unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/infrastructure/pg_owner_read_repository.py tests/trading_kernel/integration/owner_console_support.py tests/trading_kernel/integration/test_owner_console_read_repository.py
git commit -m "feat(console): add bounded read-only postgres boundary"
```

### Task 4: Build the overview facts query and deterministic Owner conclusion

**Files:**
- Create: `src/trading_kernel/application/owner_console/overview.py`
- Modify: `src/trading_kernel/application/owner_console/models.py`
- Modify: `src/trading_kernel/infrastructure/pg_owner_read_repository.py`
- Create: `tests/trading_kernel/unit/owner_console/test_overview.py`
- Modify: `tests/trading_kernel/integration/test_owner_console_read_repository.py`

**Interfaces:**
- Consumes: `PostgresOwnerReadRepository.read_overview_facts(day_start_ms, now_ms)`.
- Produces: `build_owner_overview(facts: OverviewFacts, now_ms: int) -> OwnerOverview`.

- [ ] **Step 1: Write failing tests for intervention priority and account snapshot labeling**

```python
from decimal import Decimal

from src.trading_kernel.application.owner_console.overview import build_owner_overview
from tests.trading_kernel.unit.owner_console.factories import overview_facts


def test_overview_never_labels_claim_snapshot_as_realtime_balance() -> None:
    overview = build_owner_overview(
        overview_facts(
            latest_wallet_balance_at_claim=Decimal("100.00"),
            latest_available_margin_at_claim=Decimal("76.00"),
            latest_claim_created_at_ms=1_800_000_000_000,
        ),
        now_ms=1_800_000_010_000,
    )

    assert overview.account_snapshot.label == "Latest Admission Snapshot"
    assert overview.account_snapshot.is_realtime is False
    assert overview.account_snapshot.wallet_balance.value == Decimal("100.00")


def test_open_owner_incident_wins_over_normal_monitor_rows() -> None:
    facts = overview_facts(
        open_owner_incident_id="incident:1",
        monitor_statuses=("running", "waiting_for_opportunity"),
    )
    overview = build_owner_overview(facts, now_ms=1_800_000_010_000)

    assert overview.conclusion.level == "intervention"
    assert overview.conclusion.evidence[0].identity == "incident:1"
```

- [ ] **Step 2: Run unit tests and verify the overview contract is missing**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_overview.py -v
```

Expected: FAIL because `OverviewFacts` and `build_owner_overview` do not exist.

- [ ] **Step 3: Implement bounded overview SQL and pure classification**

`read_overview_facts` executes these bounded selects inside one transaction:

1. Current Owner Policy and `account_exposure_current` for the configured venue/account.
2. Latest `capacity_claims` row ordered by `created_at_ms DESC` with `LIMIT 1`.
3. Open `runtime_incidents` ordered by `opened_at_ms DESC` with `LIMIT 20`.
4. Current `monitor_current` rows ordered by `updated_at_ms DESC` with `LIMIT 100`.
5. Active Tickets joined to aggregates ordered by `updated_at_ms DESC` with `LIMIT 20`.
6. Today’s Signal and AdmissionDecision counts using `occurred_at_ms >= day_start_ms` and `decided_at_ms >= day_start_ms`.
7. Today’s current Review rows by joining `trade_aggregates.review_id = trade_reviews.review_id`.

The account snapshot model has this exact shape:

```python
class AdmissionAccountSnapshot(FrozenModel):
    label: Literal["Latest Admission Snapshot"]
    is_realtime: Literal[False] = False
    captured_at_ms: int | None
    wallet_balance: MoneyMetric
    available_margin: MoneyMetric
```

Conclusion priority is:

```text
open needs-intervention Incident
-> contradictory required facts
-> needs_intervention Monitor
-> stale required current projection
-> attention-only Incident or evidence gap
-> no action
```

No latest CapacityClaim produces `MoneyMetric(value=None, unavailable_reason="no_capacity_claim")`. Capacity is always computed separately as `max_concurrent_tickets - active_ticket_count` from current PostgreSQL projections.

- [ ] **Step 4: Run overview unit and integration tests**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_overview.py -v
.venv/bin/pytest tests/trading_kernel/integration/test_owner_console_read_repository.py -k overview -v
.venv/bin/ruff check src/trading_kernel/application/owner_console/overview.py src/trading_kernel/application/owner_console/models.py src/trading_kernel/infrastructure/pg_owner_read_repository.py tests/trading_kernel/unit/owner_console/test_overview.py
```

Expected: PASS with no private exchange call and no write side effect.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/application/owner_console/overview.py src/trading_kernel/application/owner_console/models.py src/trading_kernel/infrastructure/pg_owner_read_repository.py tests/trading_kernel/unit/owner_console/test_overview.py tests/trading_kernel/integration/test_owner_console_read_repository.py
git commit -m "feat(console): assemble owner overview read model"
```

### Task 5: Build bounded Signal list and exact Signal detail

**Files:**
- Create: `src/trading_kernel/application/owner_console/signals.py`
- Modify: `src/trading_kernel/application/owner_console/models.py`
- Modify: `src/trading_kernel/infrastructure/pg_owner_read_repository.py`
- Create: `tests/trading_kernel/unit/owner_console/test_signals.py`
- Modify: `tests/trading_kernel/integration/test_owner_console_read_repository.py`

**Interfaces:**
- Consumes: `SignalListQuery` and exact `signal_event_id`.
- Produces: `build_signal_page(facts) -> SignalListPage` and `build_signal_detail(facts) -> SignalAdmissionDetail`.

- [ ] **Step 1: Write failing tests for admitted and rejected Signal semantics**

```python
from decimal import Decimal

from src.trading_kernel.application.owner_console.signals import build_signal_item
from tests.trading_kernel.unit.owner_console.factories import signal_item_facts


def test_rejected_signal_has_first_blocker_and_no_ticket_link() -> None:
    item = build_signal_item(
        signal_item_facts(
            decision_status="rejected",
            first_blocker="gross_stop_risk_capacity_exhausted",
            ticket_id=None,
            shadow_status="completed",
            shadow_mfe_r="1.25",
            shadow_mae_r="-0.40",
        )
    )

    assert item.first_blocker == "gross_stop_risk_capacity_exhausted"
    assert item.ticket_id is None
    assert item.shadow_summary.mfe_r == Decimal("1.25")


def test_admitted_signal_links_exact_ticket_and_never_uses_shadow_as_execution() -> None:
    item = build_signal_item(
        signal_item_facts(
            decision_status="admitted",
            first_blocker=None,
            ticket_id="ticket:1",
            shadow_status=None,
        )
    )

    assert item.ticket_id == "ticket:1"
    assert item.shadow_summary is None
```

- [ ] **Step 2: Run tests and verify the Signal assembler is absent**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_signals.py -v
```

Expected: FAIL on missing `signals.py` symbols.

- [ ] **Step 3: Implement cursor SQL, list assembly, and detail facts**

The list query joins `signal_events` to `admission_decisions` and left joins `shadow_outcomes_current`. It filters:

```text
occurred_at_ms >= from_ms
occurred_at_ms < to_ms
optional StrategyGroup
optional Instrument
optional Side
optional decision_status
(occurred_at_ms, signal_event_id) < decoded cursor
ORDER BY occurred_at_ms DESC, signal_event_id DESC
LIMIT requested_limit + 1
```

The extra row determines `next_cursor` and is never returned. Detail uses exact `signal_event_id` and reads:

- one `signal_events` row;
- its one `admission_decisions` row;
- all `signal_fact_snapshots` ordered by `fact_definition_id` with a hard assertion of at most 256 rows;
- zero or one `shadow_outcomes_current` row.

The assembler returns the exact first blocker stored in AdmissionDecision. It never infers a blocker from Shadow Outcome or current capacity.

- [ ] **Step 4: Verify cursor stability, hard bounds, and detail identity**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_signals.py -v
.venv/bin/pytest tests/trading_kernel/integration/test_owner_console_read_repository.py -k signal -v
.venv/bin/ruff check src/trading_kernel/application/owner_console/signals.py src/trading_kernel/infrastructure/pg_owner_read_repository.py tests/trading_kernel/unit/owner_console/test_signals.py
```

Expected: PASS; page boundaries remain stable when two Signals share the same timestamp.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/application/owner_console/signals.py src/trading_kernel/application/owner_console/models.py src/trading_kernel/infrastructure/pg_owner_read_repository.py tests/trading_kernel/unit/owner_console/test_signals.py tests/trading_kernel/integration/test_owner_console_read_repository.py
git commit -m "feat(console): add signal admission read models"
```

### Task 6: Build the unified active and terminal Trade list

**Files:**
- Create: `src/trading_kernel/application/owner_console/trades.py`
- Modify: `src/trading_kernel/application/owner_console/models.py`
- Modify: `src/trading_kernel/infrastructure/pg_owner_read_repository.py`
- Create: `tests/trading_kernel/unit/owner_console/test_trades.py`
- Modify: `tests/trading_kernel/integration/test_owner_console_read_repository.py`

**Interfaces:**
- Consumes: `TradeListQuery`.
- Produces: `aggregate_stage(status: str) -> LifecycleStageKey`, `build_trade_page(facts: TradePageFacts) -> TradeListPage`, and exact `TradeListItem` rows.

- [ ] **Step 1: Write failing tests for current Review pointer and active rows**

```python
from decimal import Decimal

from src.trading_kernel.application.owner_console.trades import build_trade_item
from tests.trading_kernel.unit.owner_console.factories import trade_item_facts


def test_trade_list_uses_aggregate_current_review_pointer() -> None:
    item = build_trade_item(
        trade_item_facts(
            ticket_id="ticket:1",
            aggregate_status="terminal",
            aggregate_review_id="review:2",
            review_id="review:2",
            review_revision=2,
            net_pnl_quote="3.51",
        )
    )

    assert item.review_id == "review:2"
    assert item.net_pnl.value == Decimal("3.51")


def test_active_ticket_has_stage_but_no_final_economic_conclusion() -> None:
    item = build_trade_item(
        trade_item_facts(
            aggregate_status="position_protected",
            aggregate_review_id=None,
            review_id=None,
        )
    )

    assert item.lifecycle_stage == "protection"
    assert item.net_pnl.value is None
    assert item.net_pnl.unavailable_reason == "ticket_active"
```

- [ ] **Step 2: Run tests and verify the Trade assembler is absent**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_trades.py -v
```

Expected: FAIL because `trades.py` has not been created.

- [ ] **Step 3: Implement the cursor query and economic summary rules**

The repository joins:

```text
brc_trade_tickets
INNER JOIN brc_trade_aggregates USING (ticket_id)
LEFT JOIN brc_trade_reviews
  ON brc_trade_reviews.review_id = brc_trade_aggregates.review_id
LEFT JOIN bounded open-Incident summary by ticket_id
```

Filters use `created_at_ms`, optional StrategyGroup, Instrument, Side, aggregate status, and exact cursor `(created_at_ms, ticket_id)`. The query orders descending and fetches `limit + 1`.

`build_trade_item`:

- maps aggregate status through `aggregate_stage` defined in this task;
- reads Net PnL, Net R, Fees, Funding, and completeness from only the current Review metrics;
- returns explicit unavailable reasons for active, missing Review, funding unavailable, and external exit unavailable;
- never sums Review revisions;
- never computes PnL from entry/exit prices in the browser-facing layer.

- [ ] **Step 4: Run Trade list unit and integration tests**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_trades.py -v
.venv/bin/pytest tests/trading_kernel/integration/test_owner_console_read_repository.py -k trade_list -v
.venv/bin/ruff check src/trading_kernel/application/owner_console/trades.py src/trading_kernel/infrastructure/pg_owner_read_repository.py tests/trading_kernel/unit/owner_console/test_trades.py
```

Expected: PASS with active and terminal Tickets in one stable cursor page.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/application/owner_console/trades.py src/trading_kernel/application/owner_console/models.py src/trading_kernel/infrastructure/pg_owner_read_repository.py tests/trading_kernel/unit/owner_console/test_trades.py tests/trading_kernel/integration/test_owner_console_read_repository.py
git commit -m "feat(console): add unified trade list read model"
```

### Task 7: Build the exact Ticket causality and lifecycle workbench

**Files:**
- Create: `src/trading_kernel/application/owner_console/causality.py`
- Modify: `src/trading_kernel/application/owner_console/models.py`
- Modify: `src/trading_kernel/infrastructure/pg_owner_read_repository.py`
- Create: `tests/trading_kernel/unit/owner_console/test_causality.py`
- Modify: `tests/trading_kernel/integration/test_owner_console_read_repository.py`

**Interfaces:**
- Consumes: exact `ticket_id`, `TradeCausalityFacts`, and `aggregate_stage` from Task 6.
- Produces: `build_trade_causality(facts) -> TradeCausalityDetail`.

- [ ] **Step 1: Write failing lifecycle and evidence tests**

```python
from src.trading_kernel.application.owner_console.causality import (
    build_trade_causality,
)
from tests.trading_kernel.unit.owner_console.factories import (
    trade_causality_facts,
)


def test_causality_has_eight_business_stages_and_ordered_raw_evidence() -> None:
    detail = build_trade_causality(
        trade_causality_facts(
            event_types=(
                "TicketIssued",
                "EntryFilled",
                "InitialStopConfirmed",
                "TakeProfitFilled",
                "ExitRequested",
                "PositionFlatConfirmed",
                "BudgetSettled",
                "ReviewRecorded",
            )
        )
    )

    assert [stage.key for stage in detail.stages] == [
        "signal",
        "admission",
        "entry",
        "protection",
        "tp_runner",
        "exit",
        "reconciliation",
        "review",
    ]
    assert [event.sequence for event in detail.raw_events] == sorted(
        event.sequence for event in detail.raw_events
    )


def test_exit_reason_comes_from_exit_event_not_candle_shape() -> None:
    detail = build_trade_causality(
        trade_causality_facts(
            exit_requested_reason="initial_stop_triggered",
            candle_pattern_hint="failed_breakout",
        )
    )

    assert detail.exit_reason.label == "Initial Stop"
    assert all(ref.kind == "event" for ref in detail.exit_reason.evidence)
```

- [ ] **Step 2: Run tests and verify the causality module is missing**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_causality.py -v
```

Expected: FAIL on missing `causality.py`.

- [ ] **Step 3: Implement exact-detail SQL, stage mapping, and chart annotations**

The repository performs exact-key reads:

1. Ticket and Aggregate by `ticket_id`.
2. Signal and AdmissionDecision by the Ticket’s frozen identities.
3. Trade Events ordered by `sequence ASC` with a hard maximum of 512.
4. Exchange Commands ordered by `created_at_ms ASC, command_id ASC` with a hard maximum of 128.
5. Incidents ordered by `opened_at_ms ASC` with a hard maximum of 64.
6. Current Review by `trade_aggregates.review_id`.

Return `None` when the exact Ticket does not exist. Raise a typed `ContradictoryFacts` error when Ticket, Aggregate, Signal, AdmissionDecision, or Review identities disagree.

Event-to-stage mapping is a constant dictionary over persisted Event class names and uses the aggregate fallback from Task 6. Unknown Event types are retained under that aggregate stage with `classification="unmapped"`; they are never silently discarded.

Chart annotations come only from:

- Signal reference price and frozen stop plan;
- `EntryFilled.average_fill_price`;
- `InitialStopConfirmed` plus Ticket `initial_stop_price`;
- `TakeProfitFilled.average_fill_price`;
- `ProtectionReplacementConfirmed.stop_price`;
- exit fill prices stored in current Review order attribution.

K-line rows are not accepted by `build_trade_causality` and cannot create annotations or exit reasons.

- [ ] **Step 4: Verify exact identity, sequence order, and contradiction handling**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_causality.py -v
.venv/bin/pytest tests/trading_kernel/integration/test_owner_console_read_repository.py -k causality -v
.venv/bin/ruff check src/trading_kernel/application/owner_console/causality.py src/trading_kernel/infrastructure/pg_owner_read_repository.py tests/trading_kernel/unit/owner_console/test_causality.py
```

Expected: PASS; nonexistent Ticket returns `None` and mismatched identity raises `ContradictoryFacts`.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/application/owner_console/causality.py src/trading_kernel/application/owner_console/models.py src/trading_kernel/infrastructure/pg_owner_read_repository.py tests/trading_kernel/unit/owner_console/test_causality.py tests/trading_kernel/integration/test_owner_console_read_repository.py
git commit -m "feat(console): build ticket causality workbench model"
```

### Task 8: Implement deterministic per-Ticket review and the Review Center

**Files:**
- Create: `src/trading_kernel/application/owner_console/programmatic_review.py`
- Modify: `src/trading_kernel/application/owner_console/models.py`
- Modify: `src/trading_kernel/infrastructure/pg_owner_read_repository.py`
- Create: `tests/trading_kernel/unit/owner_console/test_programmatic_review.py`
- Modify: `tests/trading_kernel/integration/test_owner_console_read_repository.py`

**Interfaces:**
- Consumes: `ProgrammaticReviewFacts` and `ReviewListQuery`.
- Produces: `build_programmatic_review(facts) -> ProgrammaticTradeReview` and `build_review_center(facts) -> ReviewCenterSummary`.

- [ ] **Step 1: Write failing rule and evidence-completeness tests**

```python
from decimal import Decimal

from src.trading_kernel.application.owner_console.programmatic_review import (
    build_programmatic_review,
)
from tests.trading_kernel.unit.owner_console.factories import (
    programmatic_review_facts,
)


def test_complete_review_uses_fixed_template_and_exact_evidence() -> None:
    review = build_programmatic_review(
        programmatic_review_facts(
            aggregate_status="terminal",
            economics_completeness="complete",
            gross_realized_pnl_quote="4.10",
            trading_fees_quote="0.40",
            funding_quote="-0.19",
            net_pnl_quote="3.51",
            planned_r_multiple="0.48",
            incident_statuses=(),
        )
    )

    assert review.execution_classification == "complete"
    assert review.economic_summary.net_pnl.value == Decimal("3.51")
    assert review.sentences[0].template_id == "execution_complete"
    assert all(sentence.evidence for sentence in review.sentences)


def test_funding_unavailable_does_not_become_zero_or_net_r() -> None:
    review = build_programmatic_review(
        programmatic_review_facts(
            aggregate_status="terminal",
            economics_completeness="funding_unavailable",
            funding_quote=None,
            net_pnl_quote=None,
            planned_r_multiple=None,
        )
    )

    assert review.economic_summary.funding.value is None
    assert review.economic_summary.net_pnl.value is None
    assert review.economic_summary.net_r.value is None
    assert "0" not in review.sentences[-1].text


def test_active_ticket_has_progress_summary_not_final_review() -> None:
    review = build_programmatic_review(
        programmatic_review_facts(aggregate_status="position_protected")
    )

    assert review.execution_classification == "in_progress"
    assert review.final_conclusion is None
```

- [ ] **Step 2: Run tests and verify the deterministic review is absent**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_programmatic_review.py -v
```

Expected: FAIL because `programmatic_review.py` does not exist.

- [ ] **Step 3: Implement closed rules, templates, and Review Center query**

Use these exact execution classifications:

```python
ExecutionClassification = Literal[
    "complete",
    "recovered_incident",
    "evidence_incomplete",
    "in_progress",
    "waiting_review",
]
```

Use template IDs and no free-form generator:

```python
TEMPLATES = {
    "execution_complete": "执行链完整。{entry_summary}；{exit_summary}。",
    "execution_recovered": "执行链已终态，但发生并恢复了异常：{incident_summary}。",
    "economics_complete": "Net PnL 为 {net_pnl} U，Net R 为 {net_r}R；订单、费用、Funding 与 Review 证据完整。",
    "economics_incomplete": "{reason}；因此不计算 Net PnL 与 Net R。",
    "review_waiting": "Ticket 已终态，当前仍在等待 Review。",
    "ticket_in_progress": "Ticket 尚未终态，当前阶段为 {stage}。",
}
```

Every rendered sentence is a `ReviewSentence(template_id, text, evidence)`. Formatting inserts only typed values or pre-approved factual labels.

The Review Center query returns only terminal Tickets in the bounded window, joins the Aggregate’s current Review pointer, and includes resolved/open Incidents required for classification. It groups by StrategyGroup only to show `sample_count` and evidence state `observe_only` or `no_evidence`; it does not rank, score, recommend, or show a full-width small-sample banner.

- [ ] **Step 4: Run review tests and scan for prohibited generation**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_programmatic_review.py -v
.venv/bin/pytest tests/trading_kernel/integration/test_owner_console_read_repository.py -k review -v
rg -n "openai|anthropic|llm|prompt|completion" src/trading_kernel/application/owner_console
```

Expected: tests PASS and `rg` returns no matches.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/application/owner_console/programmatic_review.py src/trading_kernel/application/owner_console/models.py src/trading_kernel/infrastructure/pg_owner_read_repository.py tests/trading_kernel/unit/owner_console/test_programmatic_review.py tests/trading_kernel/integration/test_owner_console_read_repository.py
git commit -m "feat(console): add deterministic programmatic review"
```

### Task 9: Add the credential-free public candle boundary

**Files:**
- Create: `src/trading_kernel/infrastructure/owner_market_data.py`
- Modify: `src/trading_kernel/application/owner_console/models.py`
- Create: `tests/trading_kernel/unit/owner_console/test_owner_market_data.py`
- Modify: `tests/trading_kernel/architecture/test_owner_console_architecture.py`

**Interfaces:**
- Consumes: existing `CcxtBinancePublicMarketSource.fetch_closed_candles`.
- Produces: `OwnerMarketData.read_candles(request: CandleQuery) -> CandleSeries` and `close()`.

- [ ] **Step 1: Write failing bound, closure, and serialization tests**

```python
async def test_owner_market_data_returns_closed_string_candles() -> None:
    source = FakeClosedCandleSource(
        candles=(closed_candle(open_time_ms=100, close_time_ms=200, close="101.25"),)
    )
    market = OwnerMarketData(source)

    series = await market.read_candles(
        CandleQuery(
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            timeframe="15m",
            limit=300,
            closed_at_ms=200,
        )
    )

    assert series.candles[0].close == "101.25"
    assert source.requests[0].limit == 300


def test_candle_query_rejects_more_than_500_rows() -> None:
    with pytest.raises(ValidationError):
        CandleQuery(
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            timeframe="15m",
            limit=501,
            closed_at_ms=200,
        )
```

- [ ] **Step 2: Run tests and verify the adapter is absent**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_owner_market_data.py -v
```

Expected: FAIL on missing `OwnerMarketData`.

- [ ] **Step 3: Implement the narrow public adapter**

`CandleQuery` permits only `15m` and `1h`, defaults to 300, caps at 500, and requires a positive `closed_at_ms`. `OwnerMarketData` converts each existing domain `ClosedCandle` to:

```python
class CandleView(FrozenModel):
    open_time_ms: int
    close_time_ms: int
    open: str
    high: str
    low: str
    close: str
    volume: str
```

The adapter owns no database engine, private credential, cache, file path, retry loop, or scheduler. `close()` delegates once to the existing market source.

Extend the architecture test so `owner_market_data.py` may import `build_binance_usdm_market_source` or `CcxtBinancePublicMarketSource` but may not import `ProductionRuntimeSettings` or `build_binance_usdm_venue_adapter`.

- [ ] **Step 4: Run market and architecture tests**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_owner_market_data.py tests/trading_kernel/unit/test_binance_public_market_source.py -v
.venv/bin/pytest tests/trading_kernel/architecture/test_owner_console_architecture.py -v
.venv/bin/ruff check src/trading_kernel/infrastructure/owner_market_data.py tests/trading_kernel/unit/owner_console/test_owner_market_data.py
```

Expected: PASS with no database or private venue dependency.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/infrastructure/owner_market_data.py src/trading_kernel/application/owner_console/models.py tests/trading_kernel/unit/owner_console/test_owner_market_data.py tests/trading_kernel/architecture/test_owner_console_architecture.py
git commit -m "feat(console): expose bounded public candle data"
```

### Task 10: Implement password, TOTP, throttle, signed cookie, and one Session

**Files:**
- Create: `src/trading_kernel/interfaces/owner_console_http/auth.py`
- Create: `tests/trading_kernel/unit/owner_console/test_auth.py`

**Interfaces:**
- Consumes: `OwnerAuthSettings` and a millisecond clock.
- Produces: `OwnerAuthService.login`, `validate_cookie`, `logout`, and `session_status`.

- [ ] **Step 1: Write failing authentication state tests**

```python
import pytest

from src.trading_kernel.interfaces.owner_console_http.auth import (
    InvalidCredentials,
    LoginThrottled,
)


async def test_login_requires_password_and_totp_and_invalidates_old_session() -> None:
    service, valid_totp = auth_service_fixture()

    first = await service.login(
        username="owner",
        password="correct horse",
        totp_code=valid_totp,
        source_ip="127.0.0.1",
        now_ms=1_000,
    )
    second = await service.login(
        username="owner",
        password="correct horse",
        totp_code=valid_totp,
        source_ip="127.0.0.1",
        now_ms=2_000,
    )

    assert await service.validate_cookie(first.cookie, now_ms=2_001) is None
    assert await service.validate_cookie(second.cookie, now_ms=2_001) is not None


async def test_idle_and_absolute_expiry_are_enforced() -> None:
    service, valid_totp = auth_service_fixture(idle_ms=30 * 60_000, absolute_ms=12 * 60 * 60_000)
    session = await service.login(
        username="owner",
        password="correct horse",
        totp_code=valid_totp,
        source_ip="127.0.0.1",
        now_ms=1_000,
    )

    assert await service.validate_cookie(session.cookie, now_ms=30 * 60_000 + 1_001) is None


async def test_five_failures_trigger_fifteen_minute_cooldown() -> None:
    service, _ = auth_service_fixture()
    for attempt in range(5):
        with pytest.raises(InvalidCredentials):
            await service.login(
                username="owner",
                password="wrong",
                totp_code="000000",
                source_ip="203.0.113.8",
                now_ms=attempt,
            )

    with pytest.raises(LoginThrottled):
        await service.login(
            username="owner",
            password="wrong",
            totp_code="000000",
            source_ip="203.0.113.8",
            now_ms=10,
        )
```

The same test file defines `auth_service_fixture()` with a fixed TOTP seed, an Argon2id hash for `correct horse`, and codes generated for the supplied `now_ms`; it does not depend on wall-clock time.

- [ ] **Step 2: Run tests and verify auth types are missing**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_auth.py -v
```

Expected: FAIL because `OwnerAuthService` is undefined.

- [ ] **Step 3: Implement the single-Owner security state**

`OwnerAuthSettings` contains only:

```python
class OwnerAuthSettings(FrozenModel):
    username: str
    password_hash: str
    totp_seed: str
    session_signing_key: str
    idle_timeout_ms: int = 30 * 60_000
    absolute_timeout_ms: int = 12 * 60 * 60_000
```

Use:

- `argon2.PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16)`;
- `pyotp.TOTP(seed, interval=30).verify(code, for_time=now_ms / 1000, valid_window=1)`;
- `itsdangerous.URLSafeSerializer(signing_key, salt="brc-owner-console-session-v1")`;
- `secrets.token_urlsafe(32)` as the random Session ID;
- one in-memory `SessionRecord(session_id, issued_at_ms, last_seen_at_ms)`;
- one in-memory failure map keyed by normalized username plus trusted source IP;
- five failures in 15 minutes followed by a 15-minute cooldown;
- one external `InvalidCredentials` response for username, password, and TOTP failures.

Password verification runs through `anyio.to_thread.run_sync`. Session replacement and throttle mutation are protected by one `asyncio.Lock`. Cookie payload contains only the random Session ID.

- [ ] **Step 4: Run auth tests and static checks**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_auth.py -v
.venv/bin/ruff check src/trading_kernel/interfaces/owner_console_http/auth.py tests/trading_kernel/unit/owner_console/test_auth.py
.venv/bin/mypy src/trading_kernel/interfaces/owner_console_http/auth.py tests/trading_kernel/unit/owner_console/test_auth.py
```

Expected: PASS; a new `OwnerAuthService` instance has no Session, proving restart invalidation.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/interfaces/owner_console_http/auth.py tests/trading_kernel/unit/owner_console/test_auth.py
git commit -m "feat(console): add single-owner password and totp sessions"
```

### Task 11: Create the FastAPI application shell and authentication endpoints

**Files:**
- Create: `src/trading_kernel/interfaces/owner_console_http/dependencies.py`
- Create: `src/trading_kernel/interfaces/owner_console_http/errors.py`
- Create: `src/trading_kernel/interfaces/owner_console_http/app.py`
- Create: `src/trading_kernel/interfaces/owner_console_http/routes/auth.py`
- Create: `tests/trading_kernel/interfaces/test_owner_console_http.py`

**Interfaces:**
- Consumes: `OwnerAuthService` and injected engine/market-data factories.
- Produces: `create_owner_console_app(settings, *, engine=None, market_data=None, clock_ms=None) -> FastAPI` and the three authentication routes.

- [ ] **Step 1: Write failing ASGI tests for login and cookie semantics**

```python
from httpx import ASGITransport, AsyncClient


async def test_login_sets_strict_secure_http_only_cookie(owner_console_app) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=owner_console_app),
        base_url="https://owner.example.test",
    ) as client:
        response = await client.post(
            "/api/owner/v1/auth/login",
            json={"username": "owner", "password": "correct horse", "totp_code": "123456"},
        )

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "brc_owner_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie


async def test_unauthenticated_session_and_data_share_one_401_shape(owner_console_app) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=owner_console_app),
        base_url="https://owner.example.test",
    ) as client:
        session = await client.get("/api/owner/v1/auth/session")
        overview = await client.get("/api/owner/v1/overview")

    assert session.status_code == 401
    assert overview.status_code == 401
    assert session.json()["error"]["code"] == "unauthorized"
    assert overview.json()["error"]["code"] == "unauthorized"
```

- [ ] **Step 2: Run the HTTP tests and verify the app factory is absent**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/interfaces/test_owner_console_http.py -v
```

Expected: FAIL because the app, settings, and auth route modules do not exist.

- [ ] **Step 3: Implement settings, errors, app lifespan, and auth routes**

`OwnerConsoleSettings` is a frozen Pydantic model:

```python
class OwnerConsoleSettings(FrozenModel):
    database_dsn: str
    auth: OwnerAuthSettings
    venue_id: Literal["binance-usdm"] = "binance-usdm"
    account_id: str
    position_mode: Literal["independent_sides"] = "independent_sides"
    market_timeout_seconds: float = 5.0
    cookie_name: Literal["brc_owner_session"] = "brc_owner_session"
```

`errors.py` defines one response shape:

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Authentication required"
  }
}
```

`create_owner_console_app`:

- creates no engine or external source at module import time;
- initializes exactly one engine, market adapter, and auth service in lifespan;
- opens one startup transaction and fails closed unless `transaction_read_only=on`, `transaction_isolation=repeatable read`, and `statement_timeout=3s`;
- disposes the engine and closes the public market source on shutdown;
- adds no CORS middleware and no scheduled task;
- exposes `/healthz` only through the Unix Socket and returns process health without database or exchange calls;
- registers exception handlers for invalid credentials, throttle, not found, contradictory facts, query timeout, and public market failure.

Auth routes:

```text
POST /api/owner/v1/auth/login   -> 204 + Session Cookie
POST /api/owner/v1/auth/logout  -> 204 + expired Session Cookie
GET  /api/owner/v1/auth/session -> 200 {"authenticated": true}
```

Login accepts one JSON body with `username`, `password`, and six-digit `totp_code`. Logout and session require the existing cookie. The same-origin API does not accept credentials in query strings or headers.

- [ ] **Step 4: Run HTTP, auth, and architecture tests**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/interfaces/test_owner_console_http.py tests/trading_kernel/unit/owner_console/test_auth.py -v
.venv/bin/pytest tests/trading_kernel/architecture/test_owner_console_architecture.py -v
.venv/bin/ruff check src/trading_kernel/interfaces/owner_console_http tests/trading_kernel/interfaces/test_owner_console_http.py
```

Expected: PASS with no CORS header and one stable 401 shape.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/interfaces/owner_console_http tests/trading_kernel/interfaces/test_owner_console_http.py
git commit -m "feat(console): add fastapi shell and owner authentication"
```

### Task 12: Expose the bounded read routes and OpenAPI contract

**Files:**
- Create: `src/trading_kernel/interfaces/owner_console_http/routes/overview.py`
- Create: `src/trading_kernel/interfaces/owner_console_http/routes/signals.py`
- Create: `src/trading_kernel/interfaces/owner_console_http/routes/tickets.py`
- Create: `src/trading_kernel/interfaces/owner_console_http/routes/review.py`
- Create: `src/trading_kernel/interfaces/owner_console_http/routes/market.py`
- Modify: `src/trading_kernel/interfaces/owner_console_http/app.py`
- Modify: `src/trading_kernel/interfaces/owner_console_http/dependencies.py`
- Modify: `tests/trading_kernel/interfaces/test_owner_console_http.py`

**Interfaces:**
- Consumes: application assemblers from Tasks 4–9.
- Produces: all `/api/owner/v1` data routes with typed `ApiEnvelope` responses.

- [ ] **Step 1: Write failing route contract and transaction-count tests**

```python
async def test_overview_uses_one_read_transaction_and_envelope(owner_console_client, repository_spy) -> None:
    response = await owner_console_client.get("/api/owner/v1/overview")

    assert response.status_code == 200
    assert response.json()["freshness"] in {"fresh", "stale"}
    assert response.json()["data"]["account_snapshot"]["label"] == "Latest Admission Snapshot"
    assert repository_spy.transaction_count == 1


async def test_candles_do_not_open_database_transaction(owner_console_client, repository_spy) -> None:
    response = await owner_console_client.get(
        "/api/owner/v1/market/candles",
        params={
            "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
            "timeframe": "15m",
            "limit": 300,
            "closed_at_ms": 1_800_000_000_000,
        },
    )

    assert response.status_code == 200
    assert repository_spy.transaction_count == 0


async def test_list_limit_above_hard_cap_returns_422(owner_console_client) -> None:
    response = await owner_console_client.get(
        "/api/owner/v1/signals",
        params={"limit": 101},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run the route tests and verify endpoints return 404**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/interfaces/test_owner_console_http.py -k "overview or candles or hard_cap" -v
```

Expected: FAIL because the data routers are not registered.

- [ ] **Step 3: Implement routes and envelope construction**

Routes are:

```text
GET /api/owner/v1/overview
GET /api/owner/v1/signals
GET /api/owner/v1/signals/{signal_event_id}
GET /api/owner/v1/tickets
GET /api/owner/v1/tickets/{ticket_id}/causality
GET /api/owner/v1/review
GET /api/owner/v1/market/candles
```

Each PostgreSQL page route:

1. validates filters into its frozen query model;
2. opens exactly one `owner_read_transaction`;
3. constructs `PostgresOwnerReadRepository(connection)`;
4. reads all page facts;
5. closes the transaction;
6. assembles the pure Read Model;
7. returns `ApiEnvelope`.

Use `snapshot_id=f"snap:{uuid4().hex}"` and UTC ISO-8601 strings. `source_watermark` is the maximum relevant persisted timestamp, not a claim that old terminal data is stale. Only overview freshness uses current projection age: up to 30 seconds is `fresh`, 30 seconds through 5 minutes is `stale`, missing required current rows is `unavailable`, and identity conflict is `contradictory`.

Default windows are generated from the injected clock:

```text
Signals: now - 7 days -> now
Tickets: now - 30 days -> now
Review:  now - 30 days -> now
```

The candles route calls only `OwnerMarketData` and returns `502 market_data_unavailable` for timeout or malformed public response.

- [ ] **Step 4: Verify the full ASGI contract and generated OpenAPI**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/interfaces/test_owner_console_http.py -v
```

Expected: tests PASS. The ASGI test suite asserts that OpenAPI contains exactly the health route plus the ten auth/data routes, with no mutation route.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/interfaces/owner_console_http/routes src/trading_kernel/interfaces/owner_console_http/app.py src/trading_kernel/interfaces/owner_console_http/dependencies.py tests/trading_kernel/interfaces/test_owner_console_http.py
git commit -m "feat(console): expose bounded owner read api"
```

### Task 13: Add exact credential loading, Unix Socket startup, and OpenAPI export

**Files:**
- Create: `scripts/owner_console/run_api.py`
- Create: `scripts/owner_console/export_openapi.py`
- Create: `tests/trading_kernel/unit/owner_console/test_owner_console_runner.py`
- Modify: `tests/trading_kernel/architecture/test_owner_console_architecture.py`

**Interfaces:**
- Consumes: systemd `CREDENTIALS_DIRECTORY` and `create_owner_console_app`.
- Produces: `load_settings(environ) -> OwnerConsoleSettings`, Uvicorn Unix Socket startup, and deterministic JSON OpenAPI on stdout.

- [ ] **Step 1: Write failing credential and startup tests**

```python
def test_runner_reads_only_exact_systemd_credentials(tmp_path: Path) -> None:
    write_credentials(
        tmp_path,
        owner_username="owner",
        owner_password_hash="$argon2id$...",
        owner_totp_seed="JBSWY3DPEHPK3PXP",
        session_signing_key="s" * 64,
        database_dsn="postgresql+asyncpg://owner:secret@127.0.0.1/brc",
        account_id="subaccount-test",
    )

    settings = load_settings(
        {
            "CREDENTIALS_DIRECTORY": str(tmp_path),
        }
    )

    assert settings.auth.username == "owner"
    assert settings.account_id == "subaccount-test"


def test_runner_requires_unix_socket_and_one_worker(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: captured.update(kwargs))

    run(settings_fixture(), uds="/run/brc-owner-console/api.sock")

    assert captured["uds"] == "/run/brc-owner-console/api.sock"
    assert captured["workers"] == 1
    assert "host" not in captured
    assert "port" not in captured
```

- [ ] **Step 2: Run tests and verify the scripts are missing**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_owner_console_runner.py -v
```

Expected: FAIL on missing `run_api.py`.

- [ ] **Step 3: Implement narrow credential loading and startup**

The runner reads exactly these files from `CREDENTIALS_DIRECTORY`:

```text
owner_username
owner_password_hash
owner_totp_seed
session_signing_key
database_dsn
account_id
```

It rejects missing files, symlinks, empty values, group/world-readable modes, and any unexpected credential name. It reads no Markdown, JSON, environment file, repository secret, or Binance private credential.

The only non-secret environment input is:

```text
OWNER_CONSOLE_MARKET_TIMEOUT_SECONDS=5
```

`run` calls:

```python
uvicorn.run(
    create_owner_console_app(settings),
    uds="/run/brc-owner-console/api.sock",
    workers=1,
    proxy_headers=False,
    access_log=True,
)
```

`export_openapi.py` constructs the app with non-secret test settings and stub dependencies, serializes `app.openapi()` with sorted keys and compact separators, and writes only JSON to stdout. It does not start a server or connect to PostgreSQL.

- [ ] **Step 4: Run runner, architecture, and OpenAPI determinism tests**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console/test_owner_console_runner.py tests/trading_kernel/architecture/test_owner_console_architecture.py -v
.venv/bin/python scripts/owner_console/export_openapi.py > /tmp/brc-owner-console-openapi-a.json
.venv/bin/python scripts/owner_console/export_openapi.py > /tmp/brc-owner-console-openapi-b.json
cmp /tmp/brc-owner-console-openapi-a.json /tmp/brc-owner-console-openapi-b.json
```

Expected: PASS and `cmp` exits zero. The temporary files are disposable and are not committed.

- [ ] **Step 5: Commit**

```bash
git add scripts/owner_console/run_api.py scripts/owner_console/export_openapi.py tests/trading_kernel/unit/owner_console/test_owner_console_runner.py tests/trading_kernel/architecture/test_owner_console_architecture.py
git commit -m "feat(console): add encrypted credential api runner"
```

### Task 14: Scaffold the strict Vite frontend and lock UI system B

**Files:**
- Create: `frontend/owner-console/package.json`
- Create: `frontend/owner-console/pnpm-lock.yaml`
- Create: `frontend/owner-console/tsconfig.json`
- Create: `frontend/owner-console/tsconfig.app.json`
- Create: `frontend/owner-console/vite.config.ts`
- Create: `frontend/owner-console/tailwind.config.ts`
- Create: `frontend/owner-console/postcss.config.cjs`
- Create: `frontend/owner-console/index.html`
- Create: `frontend/owner-console/src/main.tsx`
- Create: `frontend/owner-console/src/styles/tokens.css`
- Create: `frontend/owner-console/src/styles/base.css`
- Create: `frontend/owner-console/src/app/App.tsx`
- Create: `frontend/owner-console/src/app/router.tsx`
- Create: `frontend/owner-console/src/components/ui/Button.tsx`
- Create: `frontend/owner-console/src/components/ui/StatusTag.tsx`
- Create: `frontend/owner-console/src/components/ui/Panel.tsx`
- Create: `frontend/owner-console/src/test/setup.ts`
- Create: `frontend/owner-console/src/components/ui/ui-system.test.tsx`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: confirmed UI tokens and desktop Owner layout.
- Produces: buildable React shell, strict TypeScript, B-spec primitives, and frontend test commands.

- [ ] **Step 1: Create the failing UI system test**

```tsx
import { render, screen } from "@testing-library/react";
import { Button } from "./Button";
import { StatusTag } from "./StatusTag";

it("renders dense b-spec controls without saas card defaults", () => {
  render(
    <>
      <Button>刷新当前页</Button>
      <StatusTag tone="success">正常</StatusTag>
    </>,
  );

  expect(screen.getByRole("button")).toHaveClass("h-8");
  expect(screen.getByText("正常")).toHaveAttribute("data-tone", "success");
});
```

- [ ] **Step 2: Initialize the package and verify the test fails**

Run:

```bash
corepack enable
cd frontend/owner-console
pnpm init
pnpm add --save-exact react react-dom react-router-dom @tanstack/react-query @tanstack/react-table @radix-ui/react-alert-dialog @radix-ui/react-dialog @radix-ui/react-dropdown-menu @radix-ui/react-popover @radix-ui/react-scroll-area @radix-ui/react-tabs @radix-ui/react-tooltip lightweight-charts react-hook-form zod openapi-fetch lucide-react
pnpm add --save-dev --save-exact typescript vite @vitejs/plugin-react tailwindcss@3.4.17 postcss autoprefixer openapi-typescript vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom msw @playwright/test
pnpm exec vitest run
```

Expected: FAIL because the UI components and Vitest configuration are not implemented. Commit the generated exact `pnpm-lock.yaml`; do not hand-edit resolved versions.

- [ ] **Step 3: Implement strict configuration and visual tokens**

`package.json` scripts:

```json
{
  "scripts": {
    "build": "tsc -b && vite build",
    "typecheck": "tsc -b --pretty false",
    "test": "vitest",
    "test:run": "vitest run",
    "e2e": "playwright test",
    "generate:api": "node scripts/generate-api.mjs"
  },
  "packageManager": "pnpm@10.14.0",
  "engines": {
    "node": ">=22.12.0"
  }
}
```

`tsconfig.app.json` enables:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noEmit": true,
    "jsx": "react-jsx"
  }
}
```

`tokens.css` defines the exact color, height, spacing, and maximum-width variables from Global Constraints. `base.css` uses `#0B0E11` on `html, body, #root`, primary text `#EAECEF`, tabular numeric variants, 44px top navigation, flat borders, zero decorative shadow, and maximum content width 1160px.

`vite.config.ts` enables `build.manifest=true` so Task 19 can prove that `lightweight-charts` is isolated to a lazy chunk.

Add `frontend/owner-console/dist/` and `frontend/owner-console/.openapi/` to `.gitignore`. Do not ignore `src/api/schema.d.ts` or `pnpm-lock.yaml`.

- [ ] **Step 4: Run UI tests, typecheck, and production build**

Run:

```bash
pnpm --dir frontend/owner-console test:run
pnpm --dir frontend/owner-console typecheck
pnpm --dir frontend/owner-console build
```

Expected: PASS and `frontend/owner-console/dist/index.html` exists.

- [ ] **Step 5: Commit**

```bash
git add .gitignore frontend/owner-console
git commit -m "feat(console): scaffold strict dark owner frontend"
```

### Task 15: Generate typed API bindings and implement manual query/auth state

**Files:**
- Create: `frontend/owner-console/scripts/generate-api.mjs`
- Create: `frontend/owner-console/src/api/schema.d.ts`
- Create: `frontend/owner-console/src/api/client.ts`
- Create: `frontend/owner-console/src/api/errors.ts`
- Create: `frontend/owner-console/src/app/queryClient.ts`
- Create: `frontend/owner-console/src/app/providers.tsx`
- Create: `frontend/owner-console/src/features/auth/schema.ts`
- Create: `frontend/owner-console/src/features/auth/api.ts`
- Create: `frontend/owner-console/src/features/auth/LoginPage.tsx`
- Create: `frontend/owner-console/src/features/auth/AuthBoundary.tsx`
- Create: `frontend/owner-console/src/pages/LoginRoute.tsx`
- Create: `frontend/owner-console/src/features/auth/auth.test.tsx`
- Create: `frontend/owner-console/src/api/query-behavior.test.tsx`
- Modify: `frontend/owner-console/src/app/App.tsx`
- Modify: `frontend/owner-console/src/app/router.tsx`

**Interfaces:**
- Consumes: deterministic FastAPI OpenAPI JSON.
- Produces: generated `paths` types, `apiClient`, `ownerQueryClient`, login flow, authenticated route guard, and manual-only request behavior.

- [ ] **Step 1: Write failing query and authentication tests**

```tsx
it("does not refetch on focus, reconnect, retry, or elapsed time", async () => {
  const calls = vi.fn().mockResolvedValue({ snapshot_id: "s1", data: {} });
  renderQueryProbe(calls);

  await screen.findByText("loaded");
  window.dispatchEvent(new Event("focus"));
  window.dispatchEvent(new Event("online"));
  await new Promise((resolve) => setTimeout(resolve, 50));

  expect(calls).toHaveBeenCalledTimes(1);
});


it("preserves last known good data when manual refresh fails", async () => {
  const calls = vi
    .fn()
    .mockResolvedValueOnce({ snapshot_id: "s1", data: { active_tickets: 1 } })
    .mockRejectedValueOnce(new Error("offline"));
  renderManualQueryProbe(calls);

  expect(await screen.findByText("1 active")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "刷新当前页" }));

  expect(await screen.findByText("1 active")).toBeInTheDocument();
  expect(screen.getByText("刷新失败")).toBeInTheDocument();
});
```

- [ ] **Step 2: Generate types and verify missing client behavior fails**

Run:

```bash
pnpm --dir frontend/owner-console generate:api
pnpm --dir frontend/owner-console test:run -- src/api/query-behavior.test.tsx src/features/auth/auth.test.tsx
```

Expected: OpenAPI type generation succeeds; tests FAIL because client, providers, and auth components are absent.

- [ ] **Step 3: Implement generation, client, query defaults, and auth guard**

`generate-api.mjs`:

1. creates `.openapi/`;
2. executes repository Python `scripts/owner_console/export_openapi.py`;
3. writes `.openapi/owner-console.json`;
4. executes local `openapi-typescript`;
5. writes `src/api/schema.d.ts`;
6. exits non-zero if generated paths contain any route outside the approved list.

`client.ts`:

```ts
import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const apiClient = createClient<paths>({
  baseUrl: "",
  credentials: "include",
});
```

`queryClient.ts`:

```ts
export const ownerQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      retry: false,
      staleTime: Infinity,
      gcTime: Infinity,
    },
    mutations: { retry: false },
  },
});
```

`LoginPage` uses React Hook Form and Zod for username, non-empty password, and exactly six TOTP digits. It calls only the login endpoint. `LoginRoute` owns route error rendering and composes `LoginPage`. `AuthBoundary` calls `GET /auth/session` once on first protected navigation, redirects 401 to `/login`, and does not poll.

- [ ] **Step 4: Run generated-type, auth, query, and build checks**

Run:

```bash
pnpm --dir frontend/owner-console generate:api
pnpm --dir frontend/owner-console test:run -- src/api/query-behavior.test.tsx src/features/auth/auth.test.tsx
pnpm --dir frontend/owner-console typecheck
pnpm --dir frontend/owner-console build
cp frontend/owner-console/src/api/schema.d.ts /tmp/brc-owner-console-schema-before.d.ts
pnpm --dir frontend/owner-console generate:api
cmp /tmp/brc-owner-console-schema-before.d.ts frontend/owner-console/src/api/schema.d.ts
```

Expected: PASS and the generated schema is deterministic.

- [ ] **Step 5: Commit**

```bash
git add frontend/owner-console/scripts frontend/owner-console/src/api frontend/owner-console/src/app frontend/owner-console/src/features/auth frontend/owner-console/src/pages/LoginRoute.tsx
git commit -m "feat(console): add typed manual query and auth flow"
```

### Task 16: Implement the shared shell and Owner Overview page

**Files:**
- Create: `frontend/owner-console/src/app/AppShell.tsx`
- Create: `frontend/owner-console/src/components/ui/PageHeader.tsx`
- Create: `frontend/owner-console/src/components/ui/ManualRefreshButton.tsx`
- Create: `frontend/owner-console/src/components/ui/DataAge.tsx`
- Create: `frontend/owner-console/src/components/ui/UnavailablePanel.tsx`
- Create: `frontend/owner-console/src/features/overview/api.ts`
- Create: `frontend/owner-console/src/features/overview/OverviewPage.tsx`
- Create: `frontend/owner-console/src/features/overview/OverviewPage.test.tsx`
- Create: `frontend/owner-console/src/pages/OverviewRoute.tsx`
- Modify: `frontend/owner-console/src/app/router.tsx`

**Interfaces:**
- Consumes: `GET /api/owner/v1/overview`.
- Produces: 44px top navigation, manual refresh pattern, data-age display, and confirmed C3 compact overview.

- [ ] **Step 1: Write the failing overview layout and semantics test**

```tsx
it("renders intervention first and labels account values as admission snapshot", async () => {
  server.use(http.get("/api/owner/v1/overview", () => HttpResponse.json(overviewFixture)));
  renderOverview();

  expect(await screen.findByText("需要介入")).toBeInTheDocument();
  expect(screen.getByText("Latest Admission Snapshot")).toBeInTheDocument();
  expect(screen.queryByText("实时余额")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "刷新当前页" })).toBeInTheDocument();
});


it("data age clock changes text without issuing another request", async () => {
  renderOverview();
  await screen.findByText("无需操作");
  vi.useFakeTimers();
  vi.advanceTimersByTime(60_000);
  expect(overviewRequestCount()).toBe(1);
  vi.useRealTimers();
});
```

- [ ] **Step 2: Run the overview test and verify components are missing**

Run:

```bash
pnpm --dir frontend/owner-console test:run -- src/features/overview/OverviewPage.test.tsx
```

Expected: FAIL because `OverviewPage` and shell components do not exist.

- [ ] **Step 3: Implement the shell and compact overview**

Top navigation is exactly:

```text
BRC OWNER | 总览 | 信号 | 交易 | 复盘                       PROD · 状态 · 数据时间
```

The page order is:

1. system conclusion and Owner Action;
2. latest admission account snapshot and current Ticket capacity;
3. today Net PnL, Net R, and Signal count;
4. active Tickets;
5. opportunity and admission summary;
6. execution quality;
7. automatic attention summary.

Use flat `Panel` sections with aligned edges, 8/12/16px spacing, no decorative icon tile, no avatar, and no shadow. `DataAge` may use a local `setInterval` to update visible age text, but it receives no query callback and performs no fetch.

`ManualRefreshButton` calls `query.refetch()` only on click. While a refresh fails, render the error time and retain the last successful `data`.

- [ ] **Step 4: Run overview, query behavior, and type checks**

Run:

```bash
pnpm --dir frontend/owner-console test:run -- src/features/overview/OverviewPage.test.tsx src/api/query-behavior.test.tsx
pnpm --dir frontend/owner-console typecheck
```

Expected: PASS; no test observes a second request without a click.

- [ ] **Step 5: Commit**

```bash
git add frontend/owner-console/src/app/AppShell.tsx frontend/owner-console/src/components/ui frontend/owner-console/src/features/overview frontend/owner-console/src/pages/OverviewRoute.tsx frontend/owner-console/src/app/router.tsx
git commit -m "feat(console): build compact owner overview"
```

### Task 17: Implement Signal funnel, table, and inline causal expansion

**Files:**
- Create: `frontend/owner-console/src/components/tables/DenseTable.tsx`
- Create: `frontend/owner-console/src/components/tables/CursorPagination.tsx`
- Create: `frontend/owner-console/src/components/tables/InlineDetailRow.tsx`
- Create: `frontend/owner-console/src/features/signals/api.ts`
- Create: `frontend/owner-console/src/features/signals/searchParams.ts`
- Create: `frontend/owner-console/src/features/signals/SignalPage.tsx`
- Create: `frontend/owner-console/src/features/signals/SignalPage.test.tsx`
- Create: `frontend/owner-console/src/pages/SignalsRoute.tsx`
- Modify: `frontend/owner-console/src/app/router.tsx`

**Interfaces:**
- Consumes: Signal list and Signal detail routes.
- Produces: URL-owned filters, admission funnel, dense decision table, admitted Ticket links, and rejected inline facts.

- [ ] **Step 1: Write the failing inline-detail and URL-state tests**

```tsx
it("opens rejected signal detail inline and does not render a right drawer", async () => {
  renderSignals("/signals?decision_status=rejected");
  await userEvent.click(await screen.findByRole("button", { name: /展开 SOR-LONG/ }));

  expect(await screen.findByText("gross_stop_risk_capacity_exhausted")).toBeInTheDocument();
  expect(screen.getByText("Shadow Outcome")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});


it("links admitted signal to its exact ticket", async () => {
  renderSignals("/signals");
  const link = await screen.findByRole("link", { name: "查看 Ticket" });
  expect(link).toHaveAttribute("href", "/trades/ticket%3A1");
});
```

- [ ] **Step 2: Run the Signal page test and verify the feature is absent**

Run:

```bash
pnpm --dir frontend/owner-console test:run -- src/features/signals/SignalPage.test.tsx
```

Expected: FAIL because the table and Signal feature modules do not exist.

- [ ] **Step 3: Implement table density, bounded filters, and inline expansion**

`DenseTable` has a 30px header and 38px rows. It uses TanStack Table without virtualization. Signal URL parameters are validated with Zod:

```text
from_ms
to_ms
strategy_group_id
exchange_instrument_id
position_side
decision_status
cursor
```

The page renders:

- admitted/rejected funnel counts;
- Signal, StrategyGroup, Instrument, Side, time, decision, first blocker, and Shadow status columns;
- one expanded row at a time;
- rejected expansion sections “发生了什么 / 为什么没有 Ticket / Shadow Outcome”;
- admitted exact Ticket link;
- no Event × Instrument opportunity matrix;
- no right-side drawer.

First row expansion calls Signal detail once. Collapse/reopen uses the cached detail and performs no second request until explicit page refresh.

- [ ] **Step 4: Run Signal tests, typecheck, and accessibility roles**

Run:

```bash
pnpm --dir frontend/owner-console test:run -- src/features/signals/SignalPage.test.tsx
pnpm --dir frontend/owner-console typecheck
```

Expected: PASS with a valid table structure and no dialog/drawer.

- [ ] **Step 5: Commit**

```bash
git add frontend/owner-console/src/components/tables frontend/owner-console/src/features/signals frontend/owner-console/src/pages/SignalsRoute.tsx frontend/owner-console/src/app/router.tsx
git commit -m "feat(console): add inline signal causality page"
```

### Task 18: Implement the multi-Ticket Trade list and list-to-detail navigation

**Files:**
- Create: `frontend/owner-console/src/features/trades/api.ts`
- Create: `frontend/owner-console/src/features/trades/searchParams.ts`
- Create: `frontend/owner-console/src/features/trades/TradeListPage.tsx`
- Create: `frontend/owner-console/src/features/trades/TradeListPage.test.tsx`
- Create: `frontend/owner-console/src/pages/TradesRoute.tsx`
- Modify: `frontend/owner-console/src/app/router.tsx`

**Interfaces:**
- Consumes: `GET /tickets`.
- Produces: one dense active/terminal Ticket table, inline summary, exact detail links, and preserved list context.

- [ ] **Step 1: Write the failing multi-row and navigation-context tests**

```tsx
it("renders active and terminal tickets in one table", async () => {
  renderTrades("/trades?position_side=long");

  expect(await screen.findByText("POSITION_PROTECTED")).toBeInTheDocument();
  expect(screen.getByText("TERMINAL")).toBeInTheDocument();
  expect(screen.getAllByRole("row")).toHaveLength(3);
});


it("preserves filters when navigating to exact ticket detail", async () => {
  renderTrades("/trades?strategy_group_id=SOR-001&position_side=long");
  await userEvent.click(await screen.findByRole("link", { name: /BNBUSDT LONG/ }));

  expect(currentLocation()).toContain("/trades/ticket%3A1");
  expect(currentLocation()).toContain("return=");
});
```

- [ ] **Step 2: Run tests and verify the Trade list page is missing**

Run:

```bash
pnpm --dir frontend/owner-console test:run -- src/features/trades/TradeListPage.test.tsx
```

Expected: FAIL because `TradeListPage` does not exist.

- [ ] **Step 3: Implement summary strip, dense rows, and exact navigation**

Top summary shows Ticket count, active count, Net PnL, Net R, Fees, and Funding from API strings. The table columns are:

```text
Instrument / Side
StrategyGroup
Status
Lifecycle
Exit Reason
Net PnL
Net R
Attention
Created
```

Clicking the row-expansion control shows a compact summary under the row. Clicking the Instrument/Side link navigates to `/trades/:ticketId` and stores the current query string in a URL-safe `return` parameter. The detail page later uses this value for “返回交易列表”.

No row derives PnL, exit reason, or attention from chart data.

- [ ] **Step 4: Run Trade list tests and typecheck**

Run:

```bash
pnpm --dir frontend/owner-console test:run -- src/features/trades/TradeListPage.test.tsx
pnpm --dir frontend/owner-console typecheck
```

Expected: PASS with multiple Tickets leading to independent detail URLs.

- [ ] **Step 5: Commit**

```bash
git add frontend/owner-console/src/features/trades frontend/owner-console/src/pages/TradesRoute.tsx frontend/owner-console/src/app/router.tsx
git commit -m "feat(console): add multi-ticket trade list"
```

### Task 19: Implement the lazy Ticket causality workbench and chart

**Files:**
- Create: `frontend/owner-console/src/components/charts/CausalityChart.tsx`
- Create: `frontend/owner-console/src/components/charts/chartAdapter.ts`
- Create: `frontend/owner-console/src/features/trades/TradeCausalityPage.tsx`
- Create: `frontend/owner-console/src/features/trades/TradeCausalityPage.test.tsx`
- Create: `frontend/owner-console/src/features/trades/chartAdapter.test.ts`
- Create: `frontend/owner-console/src/pages/TradeCausalityRoute.tsx`
- Modify: `frontend/owner-console/src/app/router.tsx`

**Interfaces:**
- Consumes: exact causality detail and candles routes.
- Produces: three-column workbench, eight-stage lifecycle, on-demand candles, evidence panels, and route-aware previous/next navigation.

- [ ] **Step 1: Write failing stage, chart-load, and evidence tests**

```tsx
it("shows eight stages before requesting candles", async () => {
  renderCausality("/trades/ticket%3A1");

  expect(await screen.findAllByTestId("lifecycle-stage")).toHaveLength(8);
  expect(candleRequestCount()).toBe(0);

  await userEvent.click(screen.getByRole("button", { name: "展开 K 线" }));
  expect(await screen.findByTestId("causality-chart")).toBeInTheDocument();
  expect(candleRequestCount()).toBe(1);
});


it("keeps lifecycle facts visible when public candles fail", async () => {
  failCandleRequest();
  renderCausality("/trades/ticket%3A1");
  await userEvent.click(await screen.findByRole("button", { name: "展开 K 线" }));

  expect(await screen.findByText("公共行情不可用")).toBeInTheDocument();
  expect(screen.getByText("InitialStopConfirmed")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run causality tests and verify components are missing**

Run:

```bash
pnpm --dir frontend/owner-console test:run -- src/features/trades/TradeCausalityPage.test.tsx src/features/trades/chartAdapter.test.ts
```

Expected: FAIL because the workbench and chart adapter do not exist.

- [ ] **Step 3: Implement the workbench and display-only chart adapter**

Desktop layout uses:

```text
3 columns:
left  3/12 lifecycle
center 6/12 chart
right 3/12 selected-stage facts
bottom 12/12 orders, economics, incidents, events, signal facts
```

The right facts column is bounded to the viewport and scrolls internally; it must not create a page-height drawer.

`CausalityChart` is imported only through:

```tsx
const CausalityChart = lazy(() => import("../../components/charts/CausalityChart"));
```

The chart adapter converts API price strings to finite JavaScript numbers only while constructing Lightweight Charts series and markers:

```ts
export function toChartNumber(value: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error("invalid chart coordinate");
  return parsed;
}
```

These numbers are never returned to business components. Signal, ENTRY, Stop, TP, and Exit markers come only from API `ChartAnnotation` rows. The initial chart request defaults to 300 candles and no automatic refresh.

At widths below 1024px, stack lifecycle, chart, and facts vertically while keeping dense tables horizontally scrollable. Mobile-specific trading controls are not introduced.

- [ ] **Step 4: Run causality tests, typecheck, and chunk inspection**

Run:

```bash
pnpm --dir frontend/owner-console test:run -- src/features/trades/TradeCausalityPage.test.tsx src/features/trades/chartAdapter.test.ts
pnpm --dir frontend/owner-console typecheck
pnpm --dir frontend/owner-console build
rg -n "lightweight-charts" frontend/owner-console/dist/.vite/manifest.json
```

Expected: PASS; `lightweight-charts` appears only in a lazy chunk that is not an entry or shared initial dependency.

- [ ] **Step 5: Commit**

```bash
git add frontend/owner-console/src/components/charts frontend/owner-console/src/features/trades frontend/owner-console/src/pages/TradeCausalityRoute.tsx frontend/owner-console/src/app/router.tsx
git commit -m "feat(console): build lazy ticket causality workbench"
```

### Task 20: Implement the Review Center without a global sample warning

**Files:**
- Create: `frontend/owner-console/src/features/review/api.ts`
- Create: `frontend/owner-console/src/features/review/searchParams.ts`
- Create: `frontend/owner-console/src/features/review/ReviewPage.tsx`
- Create: `frontend/owner-console/src/features/review/ReviewPage.test.tsx`
- Create: `frontend/owner-console/src/pages/ReviewRoute.tsx`
- Modify: `frontend/owner-console/src/app/router.tsx`

**Interfaces:**
- Consumes: `GET /api/owner/v1/review`.
- Produces: completed Ticket review table, economics, execution classification, local evidence state, and exact causal links.

- [ ] **Step 1: Write failing review evidence and no-banner tests**

```tsx
it("renders deterministic review sentences and evidence links", async () => {
  renderReview();

  expect(await screen.findByText(/执行链完整/)).toBeInTheDocument();
  expect(screen.getByText("+3.51 U")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "review:ticket:1" })).toBeInTheDocument();
});


it("does not render a full-width insufficient-sample warning", async () => {
  renderReview();

  await screen.findByText("Observe Only");
  expect(screen.queryByText("样本不足 · 当前仅支持观察性结论")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toHaveTextContent("样本不足");
});
```

- [ ] **Step 2: Run the Review page test and verify the feature is missing**

Run:

```bash
pnpm --dir frontend/owner-console test:run -- src/features/review/ReviewPage.test.tsx
```

Expected: FAIL because `ReviewPage` does not exist.

- [ ] **Step 3: Implement review summary, table, and local evidence state**

The top strip shows completed Ticket count, Net PnL, Net R, Fees, Funding, complete evidence count, and attention count. Rows show:

```text
Instrument / Side
StrategyGroup
Execution Classification
Exit Reason
Net PnL
Net R
Fees
Funding
Evidence Completeness
Attention
```

Expanding a row shows only server-provided fixed-template sentences and their EvidenceRef links. StrategyGroup evidence state appears inside its local group summary as `Observe Only` or `No Evidence`. No ranking, score, recommendation, or full-width sample-size alert is rendered.

Values with `unavailable_reason` display an em dash plus the exact reason; they never display zero.

- [ ] **Step 4: Run Review, typecheck, and regression tests**

Run:

```bash
pnpm --dir frontend/owner-console test:run -- src/features/review/ReviewPage.test.tsx
pnpm --dir frontend/owner-console typecheck
rg -n "样本不足 · 当前仅支持观察性结论" frontend/owner-console/src
```

Expected: tests PASS and `rg` returns no matches.

- [ ] **Step 5: Commit**

```bash
git add frontend/owner-console/src/features/review frontend/owner-console/src/pages/ReviewRoute.tsx frontend/owner-console/src/app/router.tsx
git commit -m "feat(console): add evidence-linked review center"
```

### Task 21: Add frontend integration fixtures, Playwright paths, and no-auto-request proof

**Files:**
- Create: `frontend/owner-console/src/api/fixtures.ts`
- Create: `frontend/owner-console/src/api/handlers.ts`
- Create: `frontend/owner-console/src/api/server.ts`
- Create: `frontend/owner-console/playwright.config.ts`
- Create: `frontend/owner-console/e2e/owner-console.spec.ts`
- Create: `frontend/owner-console/e2e/no-auto-refresh.spec.ts`
- Create: `frontend/owner-console/e2e/responsive.spec.ts`
- Modify: `frontend/owner-console/src/test/setup.ts`

**Interfaces:**
- Consumes: completed frontend routes and generated API contract.
- Produces: deterministic mock scenarios and browser-level proof of the approved interaction model.

- [ ] **Step 1: Write failing Playwright scenarios**

```ts
test("login and navigate through all four primary pages", async ({ page }) => {
  await installApiRoutes(page);
  await page.goto("/login");
  await page.getByLabel("用户名").fill("owner");
  await page.getByLabel("密码").fill("correct horse");
  await page.getByLabel("验证码").fill("123456");
  await page.getByRole("button", { name: "登录" }).click();

  await expect(page).toHaveURL(/\/overview$/);
  for (const label of ["信号", "交易", "复盘"]) {
    await page.getByRole("link", { name: label }).click();
    await expect(page.getByRole("heading", { name: label })).toBeVisible();
  }
});


test("focus reconnect and elapsed time issue no request", async ({ page }) => {
  const counts = await installCountingApiRoutes(page);
  await page.goto("/overview");
  await page.waitForTimeout(2_000);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.context().setOffline(true);
  await page.context().setOffline(false);
  await page.waitForTimeout(2_000);

  expect(counts.overview).toBe(1);
});
```

- [ ] **Step 2: Run Playwright and verify missing fixtures fail**

Run:

```bash
pnpm --dir frontend/owner-console build
pnpm --dir frontend/owner-console e2e
```

Expected: FAIL because browser API routes and Playwright configuration are missing.

- [ ] **Step 3: Implement typed fixtures and browser scenarios**

Fixtures cover:

- healthy overview;
- intervention overview;
- stale overview;
- admitted and rejected Signals;
- active and terminal Tickets;
- complete, funding unavailable, and external exit unavailable Reviews;
- public candle success and failure;
- authentication success, invalid credentials, and expired Session.

Playwright intercepts `/api/owner/v1/**` with exact JSON matching the generated OpenAPI types. Tests prove:

1. login and logout;
2. top navigation;
3. Signal inline detail;
4. Trade list to exact detail and back with filters;
5. first chart expansion and manual chart refresh;
6. Review Center no-banner behavior;
7. Last Known Good after a failed manual refresh;
8. no request on time, focus, reconnect, or browser invisibility;
9. 1024px and 1440px layouts have no page-wide horizontal overflow;
10. tables may scroll within their own container below 1024px.

- [ ] **Step 4: Run all frontend verification**

Run:

```bash
pnpm --dir frontend/owner-console generate:api
pnpm --dir frontend/owner-console test:run
pnpm --dir frontend/owner-console typecheck
pnpm --dir frontend/owner-console build
pnpm --dir frontend/owner-console e2e
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/owner-console/src/api frontend/owner-console/src/test frontend/owner-console/e2e frontend/owner-console/playwright.config.ts
git commit -m "test(console): verify owner browser workflows"
```

### Task 22: Add isolated PostgreSQL, systemd, Nginx, and release-preservation assets

**Files:**
- Create: `deploy/owner-console/postgresql/owner-console-read-role.sql`
- Create: `deploy/owner-console/systemd/brc-owner-console.slice`
- Create: `deploy/owner-console/systemd/brc-owner-console-api.service`
- Create: `deploy/owner-console/nginx/00-brc-owner-console-limit.conf`
- Create: `deploy/owner-console/nginx/owner-console.locations.conf`
- Create: `deploy/owner-console/README.md`
- Modify: `scripts/trading_kernel/deploy_tokyo_release.py`
- Modify: `tests/trading_kernel/unit/test_deploy_tokyo_release.py`
- Create: `tests/trading_kernel/architecture/test_owner_console_deployment.py`

**Interfaces:**
- Consumes: built Vite `dist/`, `requirements-owner-console.txt`, existing HTTPS server block, and systemd encrypted credentials.
- Produces: independent API resource boundary, read role, Unix Socket, same-origin Nginx routes, and preservation across regular Kernel release directory swaps.

- [ ] **Step 1: Write failing deployment-asset and release-preservation tests**

```python
def test_owner_console_service_is_unix_socket_only_and_resource_bounded() -> None:
    service = read("deploy/owner-console/systemd/brc-owner-console-api.service")
    resource_slice = read("deploy/owner-console/systemd/brc-owner-console.slice")

    assert "--uds /run/brc-owner-console/api.sock" in service
    assert "EnvironmentFile=" not in service
    assert "TRADING_KERNEL_API_KEY" not in service
    assert "LoadCredentialEncrypted=database_dsn:" in service
    assert "LoadCredentialEncrypted=account_id:" in service
    assert "CPUQuota=25%" in resource_slice
    assert "MemoryMax=256M" in resource_slice
    assert "TasksMax=32" in resource_slice


def test_owner_console_nginx_include_is_same_origin_and_manual_cache_safe() -> None:
    source = read("deploy/owner-console/nginx/owner-console.locations.conf")
    assert "try_files $uri $uri/ /index.html" in source
    assert "proxy_pass http://unix:/run/brc-owner-console/api.sock" in source
    assert "location = /api/owner/v1/auth/login" in source
    assert "proxy_no_cache 1" in source


def test_regular_release_declares_exact_owner_console_artifact_pairs() -> None:
    assert preserved_owner_console_artifacts(
        current_release="/opt/brc/current",
        target_release="/opt/brc/releases/a",
    ) == (
        (
            "/opt/brc/current/.venv-owner-console",
            "/opt/brc/releases/a/.venv-owner-console",
        ),
        (
            "/opt/brc/current/frontend/owner-console/dist",
            "/opt/brc/releases/a/frontend/owner-console/dist",
        ),
    )
```

- [ ] **Step 2: Run deployment tests and verify assets are absent**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/architecture/test_owner_console_deployment.py tests/trading_kernel/unit/test_deploy_tokyo_release.py -v
```

Expected: FAIL because the assets and preservation behavior do not exist.

- [ ] **Step 3: Implement the deployment contract**

`owner-console-read-role.sql` is idempotent and performs:

```sql
\set ON_ERROR_STOP on

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'brc_owner_console') THEN
        CREATE ROLE brc_owner_console LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

ALTER ROLE brc_owner_console SET default_transaction_read_only = on;
ALTER ROLE brc_owner_console SET statement_timeout = '3s';
ALTER ROLE brc_owner_console SET application_name = 'brc_owner_console';
DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO brc_owner_console',
        current_database()
    );
END
$$;
GRANT USAGE ON SCHEMA public TO brc_owner_console;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO brc_owner_console;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO brc_owner_console;
```

The runbook sets the role password interactively with `psql \password brc_owner_console` and then stores the encoded DSN as a systemd encrypted credential. No plaintext password appears in repository files or shell history.

`brc-owner-console.slice` contains:

```ini
[Slice]
CPUAccounting=true
MemoryAccounting=true
CPUQuota=25%
MemoryMax=256M
TasksMax=32
```

`brc-owner-console-api.service` uses:

```ini
[Service]
Type=simple
User=brc
Group=brc
WorkingDirectory=/opt/brc/current
RuntimeDirectory=brc-owner-console
RuntimeDirectoryMode=0750
UMask=0077
Slice=brc-owner-console.slice
LoadCredentialEncrypted=owner_username:/etc/credstore.encrypted/brc-owner-console-owner-username
LoadCredentialEncrypted=owner_password_hash:/etc/credstore.encrypted/brc-owner-console-owner-password-hash
LoadCredentialEncrypted=owner_totp_seed:/etc/credstore.encrypted/brc-owner-console-owner-totp-seed
LoadCredentialEncrypted=session_signing_key:/etc/credstore.encrypted/brc-owner-console-session-signing-key
LoadCredentialEncrypted=database_dsn:/etc/credstore.encrypted/brc-owner-console-database-dsn
LoadCredentialEncrypted=account_id:/etc/credstore.encrypted/brc-owner-console-account-id
ExecStart=/opt/brc/current/.venv-owner-console/bin/python scripts/owner_console/run_api.py --uds /run/brc-owner-console/api.sock
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
```

`00-brc-owner-console-limit.conf` defines:

```nginx
limit_req_zone $binary_remote_addr zone=brc_owner_login:1m rate=10r/m;
```

The Nginx locations include is inserted into the existing HTTPS server block. It serves `/opt/brc/current/frontend/owner-console/dist`, uses SPA fallback, proxies `/api/` to the Unix Socket, disables API caching, sets `X-Real-IP` from `$remote_addr`, and applies `limit_req zone=brc_owner_login burst=5 nodelay` only to login.

The include sets:

```nginx
add_header Strict-Transport-Security "max-age=31536000" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "no-referrer" always;
add_header Content-Security-Policy "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
```

`index.html` and API responses use `Cache-Control: no-store`. Fingerprinted `/assets/` files use `Cache-Control: public, max-age=31536000, immutable`.

`preserved_owner_console_artifacts(current_release, target_release)` returns the two exact source/target pairs tested above. `deploy_tokyo_release.py` conditionally copies each existing source into every new release directory before switching `/opt/brc/current`. Missing artifacts do not block a Kernel-only release. Existing `deploy/systemd` unit membership remains unchanged.

- [ ] **Step 4: Run deployment, architecture, and Nginx syntax checks**

Run locally:

```bash
.venv/bin/pytest tests/trading_kernel/architecture/test_owner_console_deployment.py tests/trading_kernel/architecture/test_no_retired_execution.py tests/trading_kernel/unit/test_deploy_tokyo_release.py -v
.venv/bin/ruff check scripts/trading_kernel/deploy_tokyo_release.py tests/trading_kernel/architecture/test_owner_console_deployment.py
```

Run on a disposable Nginx validation host or Tokyo before reload:

```bash
sudo nginx -t
sudo systemd-analyze verify deploy/owner-console/systemd/brc-owner-console.slice deploy/owner-console/systemd/brc-owner-console-api.service
```

Expected: PASS; Nginx and systemd configuration validate without touching the four Kernel worker services.

- [ ] **Step 5: Commit**

```bash
git add deploy/owner-console scripts/trading_kernel/deploy_tokyo_release.py tests/trading_kernel/unit/test_deploy_tokyo_release.py tests/trading_kernel/architecture/test_owner_console_deployment.py
git commit -m "deploy(console): isolate owner api behind nginx"
```

### Task 23: Run full local acceptance and close documentation

**Files:**
- Modify: `deploy/owner-console/README.md`
- Modify: `docs/superpowers/specs/2026-08-05-owner-console-and-programmatic-review-design.md` only if verified implementation requires a factual correction
- Create: `docs/superpowers/specs/2026-08-05-owner-console-acceptance-checklist.md`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: one reproducible local acceptance record and an exact production checklist without volatile production claims.

- [ ] **Step 1: Write the acceptance checklist before running the suite**

The checklist contains these closed gates:

```text
[ ] Four primary pages and exact Ticket detail route exist
[ ] Password plus TOTP is mandatory
[ ] New login invalidates the old Session
[ ] API restart invalidates all Sessions
[ ] Every data route rejects unauthenticated access
[ ] Read role cannot write
[ ] Each page opens one bounded read-only transaction
[ ] Candles open no database transaction
[ ] No automatic network refresh exists
[ ] Last Known Good survives failed manual refresh
[ ] Active Ticket has no final review conclusion
[ ] Missing Funding or external exit facts do not become zero
[ ] Every deterministic sentence has evidence references
[ ] CapacityClaim account values are labeled Latest Admission Snapshot
[ ] No Strategy control or exchange write route exists
[ ] Frontend initial bundle excludes lightweight-charts
[ ] API idle resource use fits 25% CPU / 256M / 32-task budget
[ ] Four Trading Kernel workers remain unchanged
```

- [ ] **Step 2: Run the complete backend verification**

Run:

```bash
.venv/bin/pytest tests/trading_kernel/unit/owner_console tests/trading_kernel/interfaces/test_owner_console_http.py tests/trading_kernel/integration/test_owner_console_read_repository.py tests/trading_kernel/architecture/test_owner_console_architecture.py tests/trading_kernel/architecture/test_owner_console_deployment.py -v
.venv/bin/pytest tests/trading_kernel/architecture -v
.venv/bin/ruff check src/trading_kernel scripts/owner_console tests/trading_kernel
.venv/bin/mypy src/trading_kernel scripts/owner_console tests/trading_kernel
```

Expected: PASS.

- [ ] **Step 3: Run the complete frontend verification**

Run:

```bash
pnpm --dir frontend/owner-console generate:api
pnpm --dir frontend/owner-console test:run
pnpm --dir frontend/owner-console typecheck
pnpm --dir frontend/owner-console build
pnpm --dir frontend/owner-console e2e
```

Expected: PASS and generated API types remain unchanged.

- [ ] **Step 4: Run local process and resource acceptance**

Start the API against the disposable read-only PostgreSQL role and a temporary Unix Socket, then verify:

```bash
curl --unix-socket /tmp/brc-owner-console-test.sock http://localhost/healthz
ps -o pid,rss,%cpu,command -p "$OWNER_CONSOLE_TEST_PID"
.venv/bin/python scripts/audit_production_runtime_file_io.py --fail-on-risk --max-blocking-cleanup-required 0
git diff --check
```

Expected:

- health returns 200;
- idle RSS is below 204 MiB, which is 80% of `MemoryMax=256M`;
- idle CPU is near zero after startup;
- no periodic request or file output appears;
- runtime file-I/O audit and diff check pass.

Record commands and observed values in the acceptance checklist without copying a production commit, Ticket ID, or transient Tokyo state.

- [ ] **Step 5: Commit**

```bash
git add deploy/owner-console/README.md docs/superpowers/specs/2026-08-05-owner-console-and-programmatic-review-design.md docs/superpowers/specs/2026-08-05-owner-console-acceptance-checklist.md
git commit -m "docs(console): record phase one acceptance procedure"
```

### Task 24: Deploy and verify the Owner Console on Tokyo

**Files:**
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md` only after direct deployment evidence exists and only if Owner Console state belongs in the current runtime snapshot.
- Modify: `deploy/owner-console/README.md` only for verified command corrections.

**Interfaces:**
- Consumes: reviewed commit, built frontend, encrypted credentials, existing Nginx HTTPS server, and the production PostgreSQL database.
- Produces: authenticated public Owner Console with no effect on trading authority.

- [ ] **Step 1: Perform preflight without production mutation**

Verify:

```bash
git status --short
git rev-parse HEAD
pnpm --dir frontend/owner-console build
.venv/bin/pytest tests/trading_kernel/architecture/test_owner_console_deployment.py -v
ssh tokyo 'systemctl is-active nginx postgresql'
ssh tokyo 'systemd-creds --version && systemd-analyze --version'
ssh tokyo 'systemctl is-active brc-trading-kernel-observation-worker.service brc-trading-kernel-entry-worker.service brc-trading-kernel-lifecycle-worker.service brc-trading-kernel-reconciliation-worker.service'
```

Expected: clean intended change scope, build/tests PASS, Nginx/PostgreSQL active, and all four Kernel workers active.

- [ ] **Step 2: Install the read role, venv, static assets, credentials, and units**

Follow `deploy/owner-console/README.md` exactly:

1. apply `owner-console-read-role.sql` to the BRC database;
2. set the role password interactively;
3. create `/opt/brc/current/.venv-owner-console` and install `requirements-owner-console.txt`;
4. copy the verified Vite `dist` into `/opt/brc/current/frontend/owner-console/dist`;
5. install encrypted credentials with mode owned by root;
6. install the Owner Console slice and service;
7. include the two Nginx fragments in the existing HTTPS configuration;
8. run `nginx -t` and `systemd-analyze verify` before reload/start.

No Trading Kernel worker is stopped, restarted, or reconfigured.

- [ ] **Step 3: Start the API and verify authentication/read-only behavior**

Run:

```bash
ssh tokyo 'sudo systemctl daemon-reload && sudo systemctl enable --now brc-owner-console-api.service'
ssh tokyo 'sudo nginx -t && sudo systemctl reload nginx'
ssh tokyo 'sudo systemctl is-active brc-owner-console-api.service'
```

Expected: service active. Successful startup proves the application’s read-only preflight observed `transaction_read_only=on`, `transaction_isolation=repeatable read`, and `statement_timeout=3s` without exposing the DSN in interactive shell history.

- [ ] **Step 4: Verify browser paths, resources, and Kernel isolation**

Verify through the public HTTPS domain:

```text
unauthenticated request -> login
wrong password/TOTP -> one generic error
correct password/TOTP -> overview
overview -> signals -> trades -> exact Ticket -> review
manual refresh -> one request
idle/focus/reconnect -> zero requests
logout -> protected pages return to login
```

Read resource and isolation evidence:

```bash
ssh tokyo 'systemctl show brc-owner-console-api.service -p ActiveState -p NRestarts -p MemoryCurrent -p TasksCurrent -p CPUUsageNSec'
ssh tokyo 'systemctl show brc-owner-console.slice -p CPUQuotaPerSecUSec -p MemoryMax -p TasksMax'
ssh tokyo 'systemctl is-active brc-trading-kernel-observation-worker.service brc-trading-kernel-entry-worker.service brc-trading-kernel-lifecycle-worker.service brc-trading-kernel-reconciliation-worker.service'
```

Expected: Console stays within its resource boundary and all four workers remain active with no restart growth attributable to deployment.

- [ ] **Step 5: Record verified state and commit only factual documentation changes**

```bash
git add docs/current/MAIN_CONTROL_ROADMAP.md deploy/owner-console/README.md
git commit -m "docs(console): record verified tokyo deployment"
```

Skip this commit when no tracked documentation changed. Never copy secrets, Session IDs, full database DSNs, or authentication seeds into Git.

## Final Acceptance Commands

```bash
.venv/bin/pytest tests/trading_kernel/architecture -v
.venv/bin/pytest tests/trading_kernel/unit/owner_console tests/trading_kernel/interfaces/test_owner_console_http.py tests/trading_kernel/integration/test_owner_console_read_repository.py -v
.venv/bin/ruff check src/trading_kernel scripts/owner_console tests/trading_kernel
.venv/bin/mypy src/trading_kernel scripts/owner_console tests/trading_kernel
pnpm --dir frontend/owner-console generate:api
pnpm --dir frontend/owner-console test:run
pnpm --dir frontend/owner-console typecheck
pnpm --dir frontend/owner-console build
pnpm --dir frontend/owner-console e2e
git diff --check
```

All commands must pass before Phase 1 is described as complete.
