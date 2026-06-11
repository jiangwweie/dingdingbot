from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.runtime_exchange_gateway_readiness_service import (
    RuntimeExchangeGatewayReadinessService,
)
from src.domain.runtime_execution_exchange_gateway_readiness import (
    GATEWAY_BINDING_ENABLED_ENV,
    RuntimeExecutionExchangeGatewayReadinessStatus,
)
from src.infrastructure.pg_models import (
    PGRuntimeExecutionExchangeGatewayReadinessORM,
)
from src.infrastructure.pg_runtime_execution_exchange_gateway_readiness_repository import (
    PgRuntimeExecutionExchangeGatewayReadinessRepository,
)


class _ReadinessRepo:
    def __init__(self) -> None:
        self.records = []

    async def create(self, readiness):
        self.records.append(readiness)
        return readiness


def _ready_env(**overrides):
    env = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "order_allowed",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        GATEWAY_BINDING_ENABLED_ENV: "true",
        "EXCHANGE_NAME": "binance",
        "EXCHANGE_API_KEY": "unit-key",
        "EXCHANGE_API_SECRET": "unit-secret",
    }
    env.update(overrides)
    return env


@pytest.mark.asyncio
async def test_runtime_exchange_gateway_readiness_blocks_by_default():
    repo = _ReadinessRepo()
    service = RuntimeExchangeGatewayReadinessService(
        repository=repo,
        env={},
    )

    readiness = await service.record_readiness(
        owner_operator_id="owner",
        reason="default env should block",
    )

    assert readiness.status == RuntimeExecutionExchangeGatewayReadinessStatus.BLOCKED
    assert "trading_env_not_live" in readiness.blockers
    assert "exchange_credentials_missing" in readiness.blockers
    assert "runtime_exchange_submit_gateway_binding_not_enabled" in (
        readiness.blockers
    )
    assert "owner_gateway_readiness_review_missing" in readiness.blockers
    assert readiness.gateway_injected is False
    assert readiness.exchange_called is False
    assert readiness.exchange_order_submitted is False
    assert readiness.order_lifecycle_submit_called is False
    assert "unit-key" not in str(readiness.model_dump(mode="json"))
    assert repo.records == [readiness]


@pytest.mark.asyncio
async def test_runtime_exchange_gateway_readiness_ready_with_explicit_owner_review():
    repo = _ReadinessRepo()
    service = RuntimeExchangeGatewayReadinessService(
        repository=repo,
        env=_ready_env(),
    )

    readiness = await service.record_readiness(
        owner_confirmed_gateway_readiness_review=True,
        owner_operator_id="owner",
        reason="owner reviewed runtime gateway binding readiness",
        owner_confirmation_reference="manual-runtime-gateway-review-1",
    )

    assert readiness.status == (
        RuntimeExecutionExchangeGatewayReadinessStatus
        .READY_FOR_MANUAL_GATEWAY_BINDING
    )
    assert readiness.blockers == []
    assert readiness.runtime_exchange_submit_gateway_binding_enabled is True
    assert readiness.exchange_credentials_present is True
    assert readiness.gateway_injected is False
    assert readiness.exchange_called is False
    assert readiness.exchange_order_submitted is False
    assert readiness.order_lifecycle_submit_called is False
    assert readiness.owner_bounded_execution_called is False
    assert readiness.withdrawal_or_transfer_created is False
    assert readiness.metadata["does_not_inject_gateway"] is True


@pytest.mark.asyncio
async def test_pg_runtime_exchange_gateway_readiness_repository_round_trips():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            PGRuntimeExecutionExchangeGatewayReadinessORM.__table__.create
        )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    repo = PgRuntimeExecutionExchangeGatewayReadinessRepository(
        session_maker=session_maker
    )
    service = RuntimeExchangeGatewayReadinessService(
        repository=_ReadinessRepo(),
        env=_ready_env(),
    )
    readiness = await service.record_readiness(
        owner_confirmed_gateway_readiness_review=True,
        owner_operator_id="owner",
        reason="owner reviewed runtime gateway binding readiness",
    )

    await repo.create(readiness)
    loaded = await repo.get(readiness.readiness_id)

    await engine.dispose()

    assert loaded is not None
    assert loaded.readiness_id == readiness.readiness_id
    assert loaded.status == (
        RuntimeExecutionExchangeGatewayReadinessStatus
        .READY_FOR_MANUAL_GATEWAY_BINDING
    )
    assert loaded.gateway_injected is False
    assert loaded.exchange_called is False


@pytest.mark.asyncio
async def test_runtime_exchange_gateway_readiness_migration_creates_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-11-078_create_runtime_exchange_gateway_readiness.py"
    )
    spec = importlib.util.spec_from_file_location(
        "runtime_exchange_gateway_readiness_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:

        def upgrade(sync_conn):
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(sync_conn))
            try:
                migration.upgrade()
                inspector = inspect(sync_conn)
                assert inspector.has_table(
                    "runtime_execution_exchange_gateway_readiness"
                )
                columns = {
                    column["name"]
                    for column in inspector.get_columns(
                        "runtime_execution_exchange_gateway_readiness"
                    )
                }
                sync_conn.exec_driver_sql(
                    """
                    INSERT INTO runtime_execution_exchange_gateway_readiness (
                        readiness_id,
                        status,
                        exchange_name,
                        trading_env,
                        exchange_testnet,
                        execution_permission_max,
                        runtime_control_api_enabled,
                        runtime_test_signal_injection_enabled,
                        runtime_exchange_submit_gateway_binding_enabled,
                        exchange_credentials_present,
                        owner_confirmed_gateway_readiness_review,
                        owner_operator_id,
                        reason,
                        required_gateway_methods,
                        blockers,
                        warnings,
                        gateway_injected,
                        exchange_called,
                        exchange_order_submitted,
                        order_lifecycle_submit_called,
                        execution_intent_status_changed,
                        owner_bounded_execution_called,
                        withdrawal_or_transfer_created,
                        created_at_ms,
                        metadata,
                        payload
                    ) VALUES (
                        'runtime-gateway-readiness-1',
                        'ready_for_manual_gateway_binding',
                        'binance',
                        'live',
                        'false',
                        'order_allowed',
                        'false',
                        'false',
                        1,
                        1,
                        1,
                        'owner',
                        'reviewed',
                        '["place_order"]',
                        '[]',
                        '[]',
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        1781090000000,
                        '{}',
                        '{}'
                    )
                    """
                )
                row = sync_conn.exec_driver_sql(
                    "SELECT status, gateway_injected, exchange_called "
                    "FROM runtime_execution_exchange_gateway_readiness"
                ).one()
                migration.downgrade()
                inspector = inspect(sync_conn)
                assert not inspector.has_table(
                    "runtime_execution_exchange_gateway_readiness"
                )
                return columns, row
            finally:
                migration.op = old_op

        columns, row = await conn.run_sync(upgrade)
    await engine.dispose()

    assert "readiness_id" in columns
    assert "runtime_exchange_submit_gateway_binding_enabled" in columns
    assert "exchange_credentials_present" in columns
    assert row[0] == "ready_for_manual_gateway_binding"
    assert row[1] == 0
    assert row[2] == 0
