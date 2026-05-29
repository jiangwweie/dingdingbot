from __future__ import annotations

import asyncio
import importlib.util
import inspect as py_inspect
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.historical_research_sampling_service import (
    HistoricalResearchSamplingService,
)
from src.application.historical_signal_input_builder import (
    HistoricalMarketSnapshotBuilder,
    HistoricalStrategyFamilySignalInputBuilder,
)
from src.domain.historical_ohlcv import HistoricalOhlcvBar
from src.domain.historical_research_sampling import (
    HistoricalResearchSamplingPoint,
    HistoricalResearchSamplingPointStatus,
    HistoricalResearchSamplingRun,
    HistoricalResearchSamplingStatus,
    HistoricalResearchSamplingSummary,
    compute_sampling_summary,
)
from src.domain.strategy_family_registry import initial_strategy_family_registry_seed
from src.domain.strategy_family_signal import SignalDataQualityStatus
from src.infrastructure.pg_historical_ohlcv_catalog_repository import (
    PgHistoricalOhlcvCatalogRepository,
)
from src.infrastructure.pg_historical_research_sampling_repository import (
    PgHistoricalResearchSamplingRepository,
)
from src.infrastructure.pg_models import (
    PGBrcHistoricalResearchSamplingPointORM,
    PGBrcHistoricalResearchSamplingRunORM,
    PGKlineORM,
)


BASE_TS = 1704067200000
HOUR_MS = 60 * 60 * 1000
FOUR_HOURS_MS = 4 * HOUR_MS
DAY_MS = 24 * HOUR_MS
NOW_MS = 1770000000000


@pytest_asyncio.fixture()
async def repos():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcHistoricalResearchSamplingRunORM.__table__.create)
        await conn.run_sync(PGBrcHistoricalResearchSamplingPointORM.__table__.create)
        await conn.run_sync(PGKlineORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield (
            PgHistoricalResearchSamplingRepository(session_maker=session_maker),
            PgHistoricalOhlcvCatalogRepository(session_maker=session_maker),
        )
    finally:
        await engine.dispose()


def _run(**overrides: Any) -> HistoricalResearchSamplingRun:
    payload: dict[str, Any] = {
        "run_id": "hist-sampling-run-001",
        "strategy_family_id": "TF-001-live-readonly-v0",
        "strategy_family_version_id": "TF-001-live-readonly-v0",
        "playbook_id": "TF-001-live-readonly-v0",
        "dataset_ids": ["binance-um-BTCUSDT-1h-2021-2026"],
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "primary_timeframe": "1h",
        "context_timeframes": ["4h", "1d"],
        "start_time_ms": BASE_TS,
        "end_time_ms": BASE_TS + 15 * HOUR_MS,
        "sampling_method": "explicit_timestamps",
        "sampling_interval_bars": 1,
        "sample_limit": 10,
        "status": HistoricalResearchSamplingStatus.PENDING,
        "created_at_ms": NOW_MS,
        "updated_at_ms": NOW_MS,
        "notes": "compact coverage metadata only",
    }
    payload.update(overrides)
    return HistoricalResearchSamplingRun.model_validate(payload)


def _point(
    symbol: str,
    status: HistoricalResearchSamplingPointStatus,
    *,
    missing_fields: list[str] | None = None,
) -> HistoricalResearchSamplingPoint:
    return HistoricalResearchSamplingPoint(
        point_id=f"hist-sampling-run-001:{symbol}:{BASE_TS}",
        run_id="hist-sampling-run-001",
        symbol=symbol,
        timestamp_ms=BASE_TS,
        primary_timeframe="1h",
        context_timeframes=["4h", "1d"],
        point_status=status,
        market_snapshot_status=status,
        signal_input_status=(
            HistoricalResearchSamplingPointStatus.INVALID
            if status == HistoricalResearchSamplingPointStatus.INVALID
            else HistoricalResearchSamplingPointStatus.OK
        ),
        data_quality_status=(
            SignalDataQualityStatus.INVALID
            if status == HistoricalResearchSamplingPointStatus.INVALID
            else SignalDataQualityStatus.DEGRADED
        ),
        missing_fields=missing_fields or [],
        atr_available=status != HistoricalResearchSamplingPointStatus.INVALID,
        candle_context_available=status == HistoricalResearchSamplingPointStatus.OK,
        input_contract_valid=status != HistoricalResearchSamplingPointStatus.INVALID,
        created_at_ms=NOW_MS,
    )


def _bar(symbol: str, timeframe: str, index: int, step_ms: int) -> HistoricalOhlcvBar:
    open_price = Decimal("100") + Decimal(index)
    return HistoricalOhlcvBar(
        source="binance_vision",
        market="um_futures",
        symbol=symbol,
        timeframe=timeframe,
        open_time_ms=BASE_TS + index * step_ms,
        open=open_price,
        high=open_price + Decimal("2"),
        low=open_price - Decimal("1"),
        close=open_price + Decimal("0.5"),
        volume=Decimal("10") + Decimal(index),
        quote_volume=None,
        close_time_ms=BASE_TS + (index + 1) * step_ms - 1,
        created_at_ms=NOW_MS,
    )


def _contains_forbidden_key(value: Any) -> bool:
    forbidden = {
        "quantity",
        "notional",
        "leverage",
        "order_type",
        "client_order_id",
        "order_id",
        "venue",
        "reduce_only",
        "router_target",
        "cancel_instruction",
        "close_instruction",
        "flatten_instruction",
    }
    if isinstance(value, dict):
        return any(str(key) in forbidden or _contains_forbidden_key(nested) for key, nested in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _tf_seed():
    seed = initial_strategy_family_registry_seed(now_ms=NOW_MS)
    family = next(item for item in seed.families if item.family_id == "TF-001-live-readonly-v0")
    playbook = next(item for item in seed.playbooks if item.playbook_id == "TF-001-live-readonly-v0")
    return family, playbook


def test_sampling_domain_models_accept_tf_run_and_points():
    run = _run()
    points = [
        _point("BTCUSDT", HistoricalResearchSamplingPointStatus.OK),
        _point("ETHUSDT", HistoricalResearchSamplingPointStatus.DEGRADED, missing_fields=["candle_context.4h"]),
        _point("SOLUSDT", HistoricalResearchSamplingPointStatus.INVALID, missing_fields=["last_price"]),
    ]
    summary = compute_sampling_summary(run_id=run.run_id, points=points)

    assert run.strategy_family_id == "TF-001-live-readonly-v0"
    assert run.symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert summary.total_points == 3
    assert summary.valid_points == 1
    assert summary.degraded_points == 1
    assert summary.invalid_points == 1
    assert summary.by_symbol["BTCUSDT"]["ok"] == 1


def test_sampling_domain_models_reject_forbidden_execution_order_fields():
    payload = _run().model_dump(mode="python")
    payload["summary_json"] = {"nested": {"quantity": "must_not_exist"}}

    with pytest.raises(ValueError, match="forbidden execution/order field"):
        HistoricalResearchSamplingRun.model_validate(payload)

    point_payload = _point("BTCUSDT", HistoricalResearchSamplingPointStatus.OK).model_dump(mode="python")
    point_payload["order_id"] = "must_not_exist"
    with pytest.raises(ValueError):
        HistoricalResearchSamplingPoint.model_validate(point_payload)


def test_migration_creates_historical_research_sampling_tables():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-28-024_create_historical_research_sampling.py"
    )
    spec = importlib.util.spec_from_file_location("historical_research_sampling_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _migrate() -> set[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                old_op = migration.op
                migration.op = Operations(MigrationContext.configure(sync_conn))
                try:
                    migration.upgrade()
                    return set(inspect(sync_conn).get_table_names())
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    tables = asyncio.run(_migrate())
    asyncio.run(engine.dispose())

    assert "brc_historical_research_sampling_runs" in tables
    assert "brc_historical_research_sampling_points" in tables


@pytest.mark.asyncio
async def test_sampling_repository_round_trip_and_summary(repos):
    sampling_repo, _ohlcv_repo = repos
    run = await sampling_repo.create_sampling_run(_run(status=HistoricalResearchSamplingStatus.RUNNING))
    points = [
        await sampling_repo.record_sampling_point(_point("BTCUSDT", HistoricalResearchSamplingPointStatus.OK)),
        await sampling_repo.record_sampling_point(
            _point("ETHUSDT", HistoricalResearchSamplingPointStatus.DEGRADED, missing_fields=["candle_context.4h"])
        ),
        await sampling_repo.record_sampling_point(
            _point("SOLUSDT", HistoricalResearchSamplingPointStatus.INVALID, missing_fields=["last_price"])
        ),
    ]
    summary = compute_sampling_summary(run_id=run.run_id, points=points)
    completed = await sampling_repo.complete_sampling_run(
        run_id=run.run_id,
        summary=summary,
        updated_at_ms=NOW_MS + 1,
    )

    fetched = await sampling_repo.get_sampling_run(run.run_id)
    listed_runs = await sampling_repo.list_sampling_runs()
    listed_points = await sampling_repo.list_sampling_points(run.run_id)
    fetched_summary = await sampling_repo.get_sampling_summary(run.run_id)

    assert completed.status == HistoricalResearchSamplingStatus.COMPLETED
    assert fetched is not None
    assert fetched.summary_json["total_points"] == 3
    assert [item.run_id for item in listed_runs] == [run.run_id]
    assert [item.symbol for item in listed_points] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert isinstance(fetched_summary, HistoricalResearchSamplingSummary)
    assert fetched_summary.valid_points == 1
    assert fetched_summary.degraded_points == 1
    assert fetched_summary.invalid_points == 1


@pytest.mark.asyncio
async def test_sampling_service_records_ok_degraded_invalid_points(repos):
    sampling_repo, ohlcv_repo = repos
    await ohlcv_repo.upsert_bars([_bar("BTCUSDT", "1h", index, HOUR_MS) for index in range(16)])
    await ohlcv_repo.upsert_bars([_bar("BTCUSDT", "4h", index, FOUR_HOURS_MS) for index in range(4)])
    await ohlcv_repo.upsert_bars([_bar("BTCUSDT", "1d", index, DAY_MS) for index in range(2)])
    await ohlcv_repo.upsert_bars([_bar("ETHUSDT", "1h", index, HOUR_MS) for index in range(16)])
    family, playbook = _tf_seed()

    market_builder = HistoricalMarketSnapshotBuilder(
        repository=ohlcv_repo,
        primary_lookback=16,
        context_lookback=4,
        atr_period=14,
    )
    input_builder = HistoricalStrategyFamilySignalInputBuilder(market_snapshot_builder=market_builder)
    service = HistoricalResearchSamplingService(
        sampling_repository=sampling_repo,
        ohlcv_repository=ohlcv_repo,
        market_snapshot_builder=market_builder,
        signal_input_builder=input_builder,
        now_ms=lambda: NOW_MS,
    )

    summary = await service.run_sampling(
        run_id="hist-sampling-service-001",
        strategy_family_metadata=family,
        playbook_metadata=playbook,
        dataset_ids=["dataset-BTCUSDT", "dataset-ETHUSDT", "dataset-SOLUSDT"],
        symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        primary_timeframe="1h",
        context_timeframes=["4h", "1d"],
        start_time_ms=BASE_TS,
        end_time_ms=BASE_TS + 15 * HOUR_MS,
        explicit_timestamps=[BASE_TS + 15 * HOUR_MS],
        sample_limit=10,
    )
    points = await sampling_repo.list_sampling_points("hist-sampling-service-001")
    by_symbol = {point.symbol: point for point in points}
    stored_summary = await sampling_repo.get_sampling_summary("hist-sampling-service-001")

    assert summary.total_points == 3
    assert summary.valid_points == 1
    assert summary.degraded_points == 1
    assert summary.invalid_points == 1
    assert stored_summary is not None
    assert stored_summary.total_points == 3
    assert by_symbol["BTCUSDT"].point_status == HistoricalResearchSamplingPointStatus.OK
    assert by_symbol["BTCUSDT"].atr_available is True
    assert by_symbol["BTCUSDT"].candle_context_available is True
    assert by_symbol["BTCUSDT"].input_contract_valid is True
    assert "quote_volume" in by_symbol["BTCUSDT"].missing_fields
    assert by_symbol["ETHUSDT"].point_status == HistoricalResearchSamplingPointStatus.DEGRADED
    assert by_symbol["ETHUSDT"].candle_context_available is False
    assert "candle_context.4h" in by_symbol["ETHUSDT"].missing_fields
    assert by_symbol["SOLUSDT"].point_status == HistoricalResearchSamplingPointStatus.INVALID
    assert by_symbol["SOLUSDT"].market_snapshot_status == HistoricalResearchSamplingPointStatus.INVALID
    assert by_symbol["SOLUSDT"].signal_input_status == HistoricalResearchSamplingPointStatus.INVALID
    assert "last_price" in by_symbol["SOLUSDT"].missing_fields
    assert not _contains_forbidden_key([point.model_dump(mode="json") for point in points])
    assert not _contains_forbidden_key(summary.model_dump(mode="json"))


def test_sampling_service_exposes_no_execution_order_or_router_methods():
    forbidden_terms = [
        "execution_intent",
        "trial_trade_intent",
        "signal_output",
        "order",
        "router",
        "route",
        "cancel",
        "close",
        "flatten",
        "evaluate_strategy",
        "backtest",
    ]
    for cls in (HistoricalResearchSamplingService, PgHistoricalResearchSamplingRepository):
        public_methods = [
            name
            for name, value in py_inspect.getmembers(cls, predicate=py_inspect.isfunction)
            if not name.startswith("_")
        ]
        assert public_methods
        for method_name in public_methods:
            assert all(term not in method_name for term in forbidden_terms)
