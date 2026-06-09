from __future__ import annotations

import asyncio
import importlib.util
from decimal import Decimal
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, Integer, MetaData, String, Table, inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.readmodels.trading_console import (
    TradingConsoleDependencies,
    TradingConsoleReadModelService,
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.live_lifecycle_review import BrcLiveLifecycleReviewRecord
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType, SignalResult
from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository
from src.infrastructure.pg_live_lifecycle_review_repository import (
    PgLiveLifecycleReviewRepository,
)
from src.infrastructure.pg_models import (
    PGBrcLiveLifecycleReviewORM,
    PGExecutionIntentORM,
    PGOrderORM,
    PGReconciliationReadModelMismatchORM,
    PGReconciliationReadModelReportORM,
)
from src.infrastructure.pg_order_repository import PgOrderRepository
from src.infrastructure.pg_reconciliation_read_model_repository import (
    PgReconciliationReadModelRepository,
)
from src.infrastructure.repository_ports import (
    ReconciliationReadModelMismatch,
    ReconciliationReadModelReport,
)


NOW_MS = 1780496665000
AUDIT_VALUES = {
    "runtime_instance_id": "runtime-1",
    "trial_binding_id": "binding-1",
    "strategy_family_id": "family-1",
    "strategy_family_version_id": "version-1",
    "signal_evaluation_id": "signal-eval-1",
    "order_candidate_id": "order-candidate-1",
}
AUDIT_COLUMNS = tuple(AUDIT_VALUES)


def _signal() -> SignalResult:
    return SignalResult(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        direction=Direction.LONG,
        entry_price=Decimal("2500"),
        suggested_stop_loss=Decimal("2450"),
        suggested_position_size=Decimal("0.01"),
        current_leverage=2,
        risk_reward_info="unit test",
    )


def _intent(**overrides) -> ExecutionIntent:
    values = {
        "id": "intent-1",
        "signal_id": "signal-1",
        "signal": _signal(),
        "status": ExecutionIntentStatus.PENDING,
        "created_at": NOW_MS,
        "updated_at": NOW_MS,
    }
    values.update(overrides)
    return ExecutionIntent(**values)


def _order(**overrides) -> Order:
    values = {
        "id": "order-1",
        "signal_id": "signal-1",
        "exchange_order_id": None,
        "symbol": "ETH/USDT:USDT",
        "direction": Direction.LONG,
        "order_type": OrderType.LIMIT,
        "order_role": OrderRole.ENTRY,
        "price": Decimal("2500"),
        "trigger_price": None,
        "requested_qty": Decimal("0.01"),
        "filled_qty": Decimal("0"),
        "average_exec_price": None,
        "status": OrderStatus.PENDING,
        "created_at": NOW_MS,
        "updated_at": NOW_MS,
    }
    values.update(overrides)
    return Order(**values)


def _review(**overrides) -> BrcLiveLifecycleReviewRecord:
    values = {
        "review_id": "review-1",
        "authorization_id": "auth-1",
        "carrier_id": "carrier-1",
        "strategy_family_id": "family-1",
        "symbol": "ETH/USDT:USDT",
        "side": "long",
        "quantity": "0.01",
        "lifecycle_status": "pending_open",
        "review_status": "pending_open",
        "created_at_ms": NOW_MS,
        "updated_at_ms": NOW_MS,
    }
    values.update(overrides)
    return BrcLiveLifecycleReviewRecord(**values)


def test_execution_intent_audit_ids_are_optional_and_carriable():
    legacy = _intent()
    traced = _intent(**AUDIT_VALUES)

    assert legacy.runtime_instance_id is None
    assert legacy.semantic_ids.runtime_instance_id is None
    assert traced.runtime_instance_id == "runtime-1"
    assert traced.semantic_ids.order_candidate_id == "order-candidate-1"


def test_order_audit_ids_are_optional_and_carriable():
    legacy = _order()
    traced = _order(**AUDIT_VALUES)

    assert legacy.runtime_instance_id is None
    assert legacy.semantic_ids.trial_binding_id is None
    assert traced.runtime_instance_id == "runtime-1"
    assert traced.semantic_ids.signal_evaluation_id == "signal-eval-1"


def test_live_lifecycle_review_audit_ids_are_optional_and_carriable():
    legacy = _review()
    traced = _review(**AUDIT_VALUES)

    assert legacy.runtime_instance_id is None
    assert traced.runtime_instance_id == "runtime-1"
    assert traced.order_candidate_id == "order-candidate-1"
    assert traced.places_order is False


def test_migration_adds_nullable_audit_columns_and_keeps_old_inserts_valid():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-046_add_strategy_runtime_audit_ids.py"
    )
    spec = importlib.util.spec_from_file_location("td2_audit_id_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    def _create_old_tables(sync_conn):
        metadata = MetaData()
        Table("execution_intents", metadata, Column("id", String(64), primary_key=True))
        Table("orders", metadata, Column("id", String(64), primary_key=True))
        Table("brc_live_lifecycle_reviews", metadata, Column("review_id", String(128), primary_key=True))
        Table(
            "reconciliation_read_model_reports",
            metadata,
            Column("id", Integer, primary_key=True),
        )
        Table(
            "reconciliation_read_model_mismatches",
            metadata,
            Column("id", Integer, primary_key=True),
        )
        metadata.create_all(sync_conn)

    async def _run() -> dict[str, list[dict]]:
        async with engine.begin() as conn:
            await conn.run_sync(_create_old_tables)

            def upgrade(sync_conn):
                old_op = migration.op
                migration.op = Operations(MigrationContext.configure(sync_conn))
                try:
                    migration.upgrade()
                    return {
                        table: inspect(sync_conn).get_columns(table)
                        for table in [
                            "execution_intents",
                            "orders",
                            "brc_live_lifecycle_reviews",
                            "reconciliation_read_model_reports",
                            "reconciliation_read_model_mismatches",
                        ]
                    }
                finally:
                    migration.op = old_op

            columns = await conn.run_sync(upgrade)
            await conn.execute(text("INSERT INTO execution_intents (id) VALUES ('intent-old')"))
            await conn.execute(text("INSERT INTO orders (id) VALUES ('order-old')"))
            return columns

    columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    for table_columns in columns.values():
        by_name = {column["name"]: column for column in table_columns}
        for column_name in AUDIT_COLUMNS:
            assert column_name in by_name
            assert by_name[column_name]["nullable"] is True


async def _repo_engine(*tables):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(table.create)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_execution_intent_repository_persists_null_and_present_audit_ids():
    engine, session_maker = await _repo_engine(PGExecutionIntentORM.__table__)
    repo = PgExecutionIntentRepository(session_maker=session_maker)
    try:
        await repo.save(_intent(id="intent-legacy"))
        await repo.save(_intent(id="intent-traced", **AUDIT_VALUES))

        legacy = await repo.get("intent-legacy")
        traced = await repo.get("intent-traced")

        assert legacy is not None and legacy.runtime_instance_id is None
        assert traced is not None and traced.runtime_instance_id == "runtime-1"
        assert traced.order_candidate_id == "order-candidate-1"
    finally:
        await engine.dispose()


async def test_order_repository_persists_null_and_present_audit_ids():
    engine, session_maker = await _repo_engine(PGOrderORM.__table__)
    repo = PgOrderRepository(session_maker=session_maker)
    try:
        await repo.save(_order(id="order-legacy"))
        await repo.save(_order(id="order-traced", **AUDIT_VALUES))

        legacy = await repo.get_order("order-legacy")
        traced = await repo.get_order("order-traced")

        assert legacy is not None and legacy.runtime_instance_id is None
        assert traced is not None and traced.runtime_instance_id == "runtime-1"
        assert traced.signal_evaluation_id == "signal-eval-1"
    finally:
        await engine.dispose()


async def test_live_lifecycle_review_repository_persists_audit_ids():
    engine, session_maker = await _repo_engine(PGBrcLiveLifecycleReviewORM.__table__)
    repo = PgLiveLifecycleReviewRepository(session_maker=session_maker)
    try:
        await repo.append(_review(review_id="review-legacy"))
        await repo.append(_review(review_id="review-traced", **AUDIT_VALUES))

        rows = await repo.list(symbol="ETH/USDT:USDT", limit=10)
        by_id = {row.review_id: row for row in rows}

        assert by_id["review-legacy"].runtime_instance_id is None
        assert by_id["review-traced"].runtime_instance_id == "runtime-1"
        assert by_id["review-traced"].strategy_family_version_id == "version-1"
    finally:
        await engine.dispose()


async def test_reconciliation_readmodel_repository_persists_audit_ids_without_matching_changes():
    engine, session_maker = await _repo_engine(
        PGReconciliationReadModelReportORM.__table__,
        PGReconciliationReadModelMismatchORM.__table__,
    )
    repo = PgReconciliationReadModelRepository(session_maker=session_maker)
    try:
        await repo.save_report(
            ReconciliationReadModelReport(
                report_id="report-1",
                symbol="ETH/USDT:USDT",
                checked_at_ms=NOW_MS,
                is_consistent=False,
                total_count=1,
                severe_count=1,
                runtime_instance_id="runtime-1",
                trial_binding_id="binding-1",
            ),
            [
                ReconciliationReadModelMismatch(
                    report_id="report-1",
                    symbol="ETH/USDT:USDT",
                    mismatch_type="order_status_mismatch",
                    severity="SEVERE",
                    reason="unit test",
                    local_ref="order-1",
                    runtime_instance_id="runtime-1",
                    order_candidate_id="order-candidate-1",
                )
            ],
        )

        reports = await repo.get_recent_reports(symbol="ETH/USDT:USDT", limit=10)
        mismatches = await repo.get_mismatches("report-1")

        assert reports[0].runtime_instance_id == "runtime-1"
        assert reports[0].trial_binding_id == "binding-1"
        assert mismatches[0].runtime_instance_id == "runtime-1"
        assert mismatches[0].order_candidate_id == "order-candidate-1"
    finally:
        await engine.dispose()


async def test_trading_console_readmodel_exposes_and_filters_audit_ids():
    traced_order = _order(**AUDIT_VALUES)
    traced_intent = _intent(order_id=traced_order.id, **AUDIT_VALUES)

    class _OrderRepo:
        async def get_orders(self, symbol=None, limit=50, offset=0):
            return {"items": [traced_order], "total": 1}

        async def get_open_orders(self, symbol=None):
            return [traced_order]

    class _IntentRepo:
        async def list(self):
            return [traced_intent]

    service = TradingConsoleReadModelService(
        TradingConsoleDependencies(
            order_repo=_OrderRepo(),
            execution_intent_repo=_IntentRepo(),
        )
    )

    order_ledger = await service.order_ledger(symbol="ETH/USDT:USDT", limit=10)
    audit_chain = await service.audit_chain(runtime_instance_id="runtime-1", limit=10)

    assert order_ledger.data["orders"][0]["runtime_instance_id"] == "runtime-1"
    assert order_ledger.data["orders"][0]["order_candidate_id"] == "order-candidate-1"
    assert audit_chain.data["orders"][0]["runtime_instance_id"] == "runtime-1"
    assert audit_chain.data["intents"][0]["signal_evaluation_id"] == "signal-eval-1"
