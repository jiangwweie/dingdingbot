from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.periodic_reconciliation import (
    _build_report_id,
    run_periodic_reconciliation,
)
from src.infrastructure.pg_models import (
    PGReconciliationReadModelMismatchORM,
    PGReconciliationReadModelReportORM,
)
from src.infrastructure.pg_reconciliation_read_model_repository import (
    PgReconciliationReadModelRepository,
)
from src.infrastructure.repository_ports import (
    ReconciliationReadModelMismatch,
    ReconciliationReadModelReport,
)


SYMBOL = "ETH/USDT:USDT"


@dataclass
class _Mismatch:
    symbol: str = SYMBOL
    mismatch_type: str = "missing_sl_protection"
    severity: str = "SEVERE"
    reason: str = "No SL protection."
    local_ref: str | None = "local-order"
    exchange_ref: str | None = "exchange-order"
    metadata: dict = field(default_factory=lambda: {"qty": "1.0", "nested": {"ok": True}})


@dataclass
class _Result:
    symbol: str = SYMBOL
    checked_at: int = 1770000000123
    mismatches: list[_Mismatch] = field(default_factory=list)


class _FakeService:
    def __init__(
        self,
        shutdown_event: asyncio.Event,
        *,
        result: _Result | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.shutdown_event = shutdown_event
        self.result = result or _Result()
        self.failure = failure
        self.calls: list[str] = []

    async def build_read_model(self, symbol: str) -> _Result:
        self.calls.append(symbol)
        self.shutdown_event.set()
        if self.failure is not None:
            raise self.failure
        return self.result


class _FailingRepository:
    async def initialize(self) -> None:
        return None

    async def save_report(self, report, mismatches) -> None:
        raise RuntimeError("persistence unavailable")

    async def get_recent_reports(self, symbol=None, limit=100):
        return []

    async def get_mismatches(self, report_id: str):
        return []


class _CapturingRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[ReconciliationReadModelReport, list[ReconciliationReadModelMismatch]]] = []

    async def initialize(self) -> None:
        return None

    async def save_report(self, report, mismatches) -> None:
        self.saved.append((report, mismatches))

    async def get_recent_reports(self, symbol=None, limit=100):
        return [item[0] for item in self.saved[:limit]]

    async def get_mismatches(self, report_id: str):
        for report, mismatches in self.saved:
            if report.report_id == report_id:
                return mismatches
        return []


class _CancelledService:
    async def build_read_model(self, symbol: str) -> _Result:
        raise asyncio.CancelledError()


@pytest_asyncio.fixture()
async def read_model_repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGReconciliationReadModelReportORM.__table__.create)
        await conn.run_sync(PGReconciliationReadModelMismatchORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgReconciliationReadModelRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


def _report(
    *,
    report_id: str = "1770000000123:ETH/USDT:USDT",
    symbol: str = SYMBOL,
    checked_at_ms: int = 1770000000123,
    is_consistent: bool = True,
    total_count: int = 0,
    severe_count: int = 0,
    warning_count: int = 0,
    is_fetch_failure: bool = False,
    fetch_failure_reason: str | None = None,
) -> ReconciliationReadModelReport:
    return ReconciliationReadModelReport(
        report_id=report_id,
        symbol=symbol,
        checked_at_ms=checked_at_ms,
        is_consistent=is_consistent,
        total_count=total_count,
        severe_count=severe_count,
        warning_count=warning_count,
        is_fetch_failure=is_fetch_failure,
        fetch_failure_reason=fetch_failure_reason,
        created_at=checked_at_ms,
    )


def _persisted_mismatch(report_id: str = "1770000000123:ETH/USDT:USDT"):
    return ReconciliationReadModelMismatch(
        report_id=report_id,
        symbol=SYMBOL,
        mismatch_type="missing_sl_protection",
        severity="SEVERE",
        reason="No SL protection.",
        local_ref="local-order",
        exchange_ref="exchange-order",
        metadata={"qty": "1.0", "nested": {"ok": True}},
        created_at=1770000000123,
    )


@pytest.mark.asyncio
async def test_save_consistent_report(read_model_repo):
    await read_model_repo.save_report(_report(), [])

    reports = await read_model_repo.get_recent_reports(SYMBOL)

    assert len(reports) == 1
    assert reports[0].is_consistent is True
    assert reports[0].total_count == 0


@pytest.mark.asyncio
async def test_save_mismatch_report(read_model_repo):
    report = _report(is_consistent=False, total_count=1, severe_count=1)

    await read_model_repo.save_report(report, [_persisted_mismatch()])

    reports = await read_model_repo.get_recent_reports(SYMBOL)
    mismatches = await read_model_repo.get_mismatches(report.report_id)
    assert reports[0].is_consistent is False
    assert reports[0].severe_count == 1
    assert mismatches[0].mismatch_type == "missing_sl_protection"


@pytest.mark.asyncio
async def test_save_fetch_failure_report(read_model_repo):
    report = _report(
        is_consistent=False,
        is_fetch_failure=True,
        fetch_failure_reason="RuntimeError: exchange unavailable",
    )

    await read_model_repo.save_report(report, [])

    saved = (await read_model_repo.get_recent_reports(SYMBOL))[0]
    assert saved.is_fetch_failure is True
    assert saved.fetch_failure_reason == "RuntimeError: exchange unavailable"


def test_report_id_format():
    assert _build_report_id(1770000000123, SYMBOL) == "1770000000123:ETH/USDT:USDT"


@pytest.mark.asyncio
async def test_metadata_jsonb_roundtrip(read_model_repo):
    report = _report(is_consistent=False, total_count=1, severe_count=1)

    await read_model_repo.save_report(report, [_persisted_mismatch()])

    mismatch = (await read_model_repo.get_mismatches(report.report_id))[0]
    assert mismatch.metadata == {"qty": "1.0", "nested": {"ok": True}}


@pytest.mark.asyncio
async def test_get_recent_reports_by_symbol(read_model_repo):
    await read_model_repo.save_report(_report(symbol=SYMBOL), [])
    await read_model_repo.save_report(
        _report(
            report_id="1770000000124:BTC/USDT:USDT",
            symbol="BTC/USDT:USDT",
            checked_at_ms=1770000000124,
        ),
        [],
    )

    reports = await read_model_repo.get_recent_reports(SYMBOL)

    assert [report.symbol for report in reports] == [SYMBOL]


@pytest.mark.asyncio
async def test_get_recent_reports_limit_and_order(read_model_repo):
    for index in range(3):
        checked_at_ms = 1770000000123 + index
        await read_model_repo.save_report(
            _report(
                report_id=f"{checked_at_ms}:{SYMBOL}",
                checked_at_ms=checked_at_ms,
            ),
            [],
        )

    reports = await read_model_repo.get_recent_reports(SYMBOL, limit=2)

    assert [report.checked_at_ms for report in reports] == [1770000000125, 1770000000124]


@pytest.mark.asyncio
async def test_get_mismatches_by_report_id(read_model_repo):
    first = _report(report_id=f"1770000000123:{SYMBOL}")
    second = _report(report_id=f"1770000000124:{SYMBOL}", checked_at_ms=1770000000124)
    await read_model_repo.save_report(first, [_persisted_mismatch(first.report_id)])
    await read_model_repo.save_report(second, [])

    mismatches = await read_model_repo.get_mismatches(first.report_id)

    assert len(mismatches) == 1
    assert mismatches[0].report_id == first.report_id


@pytest.mark.asyncio
async def test_persistence_failure_does_not_raise_or_stop_loop(caplog):
    shutdown_event = asyncio.Event()
    service = _FakeService(shutdown_event)
    caplog.set_level("ERROR")

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            [SYMBOL],
            shutdown_event,
            read_model_repository=_FailingRepository(),
            startup_delay_seconds=0,
            interval_seconds=60,
        ),
        timeout=1,
    )

    assert service.calls == [SYMBOL]
    assert "persistence failed" in caplog.text


@pytest.mark.asyncio
async def test_repository_none_skips_persistence():
    shutdown_event = asyncio.Event()
    service = _FakeService(shutdown_event)

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            [SYMBOL],
            shutdown_event,
            read_model_repository=None,
            startup_delay_seconds=0,
            interval_seconds=60,
        ),
        timeout=1,
    )

    assert service.calls == [SYMBOL]


@pytest.mark.asyncio
async def test_build_read_model_failure_persisted_best_effort():
    shutdown_event = asyncio.Event()
    service = _FakeService(shutdown_event, failure=RuntimeError("exchange unavailable"))
    repository = _CapturingRepository()

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            [SYMBOL],
            shutdown_event,
            read_model_repository=repository,
            startup_delay_seconds=0,
            interval_seconds=60,
        ),
        timeout=1,
    )

    report, mismatches = repository.saved[0]
    assert report.symbol == SYMBOL
    assert report.is_fetch_failure is True
    assert report.is_consistent is False
    assert report.fetch_failure_reason == "RuntimeError: exchange unavailable"
    assert mismatches == []


@pytest.mark.asyncio
async def test_cancelled_error_is_reraised():
    shutdown_event = asyncio.Event()

    with pytest.raises(asyncio.CancelledError):
        await run_periodic_reconciliation(
            _CancelledService(),
            [SYMBOL],
            shutdown_event,
            read_model_repository=_CapturingRepository(),
            startup_delay_seconds=0,
            interval_seconds=60,
        )


def test_orm_column_mapping():
    report_columns = PGReconciliationReadModelReportORM.__table__.columns
    mismatch_columns = PGReconciliationReadModelMismatchORM.__table__.columns

    assert set(
        [
            "id",
            "report_id",
            "symbol",
            "checked_at_ms",
            "is_consistent",
            "total_count",
            "severe_count",
            "warning_count",
            "is_fetch_failure",
            "fetch_failure_reason",
            "created_at",
        ]
    ).issubset(report_columns.keys())
    assert "metadata" in mismatch_columns.keys()
    assert PGReconciliationReadModelMismatchORM.metadata_json.property.columns[0].name == "metadata"


def test_alembic_single_head():
    config = Config(str(Path("alembic.ini").resolve()))
    script = ScriptDirectory.from_config(config)

    assert len(script.get_heads()) == 1


def test_clean_temp_db_migration_upgrade_downgrade_upgrade(tmp_path, monkeypatch):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    db_path = tmp_path / "ls003d_migration.db"
    config = Config()
    config.set_main_option("script_location", str(Path("migrations").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(config, "106")

    from scripts import seed_runtime_control_state_foundation as seed
    from sqlalchemy import create_engine

    bootstrap_engine = create_engine(f"sqlite:///{db_path}")
    with bootstrap_engine.begin() as connection:
        seed.seed_runtime_control_state_foundation(
            connection,
            migration_baseline_revision="106",
        )
    bootstrap_engine.dispose()

    command.upgrade(config, "head")
    command.downgrade(config, "007")
    command.upgrade(config, "106")
    bootstrap_engine = create_engine(f"sqlite:///{db_path}")
    with bootstrap_engine.begin() as connection:
        seed.seed_runtime_control_state_foundation(
            connection,
            migration_baseline_revision="106",
        )
    bootstrap_engine.dispose()
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        inspector = inspect(engine)
        assert "reconciliation_read_model_reports" in inspector.get_table_names()
        assert "reconciliation_read_model_mismatches" in inspector.get_table_names()
    finally:
        engine.dispose()
