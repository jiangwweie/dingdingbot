from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import AsyncGenerator
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4

import asyncpg
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.certify_universe_instrument import (
    InstrumentCertificationReadRequest,
    InstrumentCertificationSnapshot,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    install_strategy_universe,
)
from src.trading_kernel.application.ports import (
    LeverageTruthRequest,
    LeverageTruthSnapshot,
    VenueTruthRequest,
)
from src.trading_kernel.application.runtime_facts import (
    InstrumentRulesFacts,
    PositionSnapshotRequest,
)
from src.trading_kernel.domain.cross_margin_stress import MaintenanceMarginBracket
from src.trading_kernel.domain.instrument_certification import (
    InstrumentCertificationFacts,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.domain.venue_truth import VenueTruthSnapshot
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    OWNER_POLICY_ID,
    RUNTIME_PROFILE_ID,
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")
CONTRACT = registered_strategy_contracts()[0]
MEMBERS = (
    "binance-usdm:BTCUSDT:perpetual",
    "binance-usdm:SOLUSDT:perpetual",
)
NOW_MS = 1_800_000_010_000
RUNTIME_COMMIT = "task-7-test"
SCHEMA_REVISION: Literal["0001_trading_kernel_baseline_v4"] = (
    "0001_trading_kernel_baseline_v4"
)


@pytest_asyncio.fixture
async def certification_engine() -> AsyncGenerator[AsyncEngine, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    engine: AsyncEngine | None = None
    try:
        _run_alembic(database_url, "upgrade", "head")
        engine = create_async_engine(database_url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="subaccount-certification-test",
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 10_000,
                ),
            )
            installed = await install_strategy_universe(
                uow,
                UniverseInstallRequest(
                    event_spec_id=CONTRACT.event_spec_id,
                    runtime_profile_id=RUNTIME_PROFILE_ID,
                    owner_policy_id=OWNER_POLICY_ID,
                    exchange_instrument_ids=MEMBERS,
                    installed_at_ms=NOW_MS - 1_000,
                ),
            )
            assert installed.universe is not None
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "UPDATE brc_runtime_capabilities_current "
                    "SET enabled = true "
                    "WHERE capability_key = 'exchange_commands'"
                )
            )
        yield engine
    finally:
        if engine is not None:
            await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


class RecordingReadonlyCertificationSource:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        changes: dict[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.engine = engine
        self.changes = changes or {}
        self.error = error
        self.requests: list[InstrumentCertificationReadRequest] = []
        self.mutation_calls: list[str] = []

    async def read_instrument_certification(
        self, request: InstrumentCertificationReadRequest
    ) -> InstrumentCertificationSnapshot:
        self.requests.append(request)
        async with self.engine.connect() as connection:
            idle_in_transaction = int(
                (
                    await connection.exec_driver_sql(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() "
                        "AND state = 'idle in transaction'"
                    )
                ).scalar_one()
            )
        assert idle_in_transaction == 0
        if self.error is not None:
            raise self.error
        instrument_id = request.target.exchange_instrument_id
        observed_at_ms = request.observed_at_ms
        facts = InstrumentCertificationFacts(
            runtime_profile_id=request.target.runtime_profile_id,
            exchange_instrument_id=instrument_id,
            product_status="trading",
            tick_size=Decimal("0.1"),
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal(5),
            position_mode="independent_sides",
            margin_mode="cross",
            configured_leverage=5,
            notional_coefficient_certified=True,
            unowned_position_qty=Decimal(0),
            unowned_open_order_count=0,
            observed_at_ms=observed_at_ms,
        ).model_copy(update=self.changes)
        return InstrumentCertificationSnapshot(
            facts=facts,
            instrument_rules=InstrumentRulesFacts(
                exchange_instrument_id=instrument_id,
                quantity_step=Decimal("0.001"),
                price_tick=Decimal("0.1"),
                min_quantity=Decimal("0.001"),
                min_notional=Decimal(5),
                exchange_max_leverage=125,
                maintenance_margin_brackets=(
                    MaintenanceMarginBracket(
                        bracket_id="1",
                        notional_floor=Decimal(0),
                        notional_cap=Decimal(50000),
                        maintenance_margin_rate=Decimal("0.004"),
                        maintenance_amount=Decimal(0),
                    ),
                ),
                maintenance_margin_brackets_digest=(
                    "sha256:"
                    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                ),
                notional_coefficient=Decimal(1),
                notional_coefficient_certified=True,
                observed_at_ms=observed_at_ms,
                valid_until_ms=observed_at_ms + request.valid_for_ms,
            ),
        )

    async def set_leverage(self, *args, **kwargs):
        del args, kwargs
        self.mutation_calls.append("set_leverage")
        raise AssertionError("certification must remain readonly")

    async def set_margin_mode(self, *args, **kwargs):
        del args, kwargs
        self.mutation_calls.append("set_margin_mode")
        raise AssertionError("certification must remain readonly")

    async def set_position_mode(self, *args, **kwargs):
        del args, kwargs
        self.mutation_calls.append("set_position_mode")
        raise AssertionError("certification must remain readonly")


class NoTicketVenueTruth:
    """Strict fake proving certification cadence does not inspect Tickets."""

    async def lookup_command_truth(
        self, request: VenueTruthRequest
    ) -> VenueTruthSnapshot:
        del request
        raise AssertionError("certification-only cadence must not read order truth")

    async def read_configured_leverage(
        self, request: LeverageTruthRequest
    ) -> LeverageTruthSnapshot:
        del request
        raise AssertionError("certification-only cadence must not read leverage truth")


class NoTicketPositionSource:
    """Strict fake proving certification cadence does not inspect positions."""

    async def read_position_snapshot(
        self, request: PositionSnapshotRequest
    ) -> PositionSnapshot:
        del request
        raise AssertionError("certification-only cadence must not read position")


class NoInstrumentCertificationSource:
    """Strict fake for a cadence whose certification selector is monkeypatched."""

    async def read_instrument_certification(
        self, request: InstrumentCertificationReadRequest
    ) -> InstrumentCertificationSnapshot:
        del request
        raise AssertionError("monkeypatched certification selector must own this test")


def worker_request(now_ms: int):
    from src.trading_kernel.interfaces.reconciliation_worker import (
        ReconciliationWorkerRequest,
    )

    return ReconciliationWorkerRequest(
        worker_id="reconciliation-worker-certification-test",
        runtime_commit=RUNTIME_COMMIT,
        schema_revision=SCHEMA_REVISION,
        now_ms=now_ms,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=2_000,
        certification_lease_ms=60_000,
        certification_max_wait_ms=120_000,
        certification_valid_for_ms=600_000,
        certification_eligible_check_interval_ms=300_000,
        certification_owner_action_check_interval_ms=300_000,
        certification_transient_retry_interval_ms=30_000,
    )


def _database_url(database_name: str) -> str:
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"


def _run_alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
