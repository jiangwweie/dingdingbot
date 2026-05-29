from __future__ import annotations

import asyncio
import importlib.util
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

from src.application.historical_signal_input_builder import (
    HistoricalMarketSnapshotBuilder,
    HistoricalStrategyFamilySignalInputBuilder,
)
from src.domain.historical_ohlcv import (
    HistoricalDataQualityStatus,
    HistoricalOhlcvBar,
    HistoricalOhlcvDatasetMetadata,
    HistoricalOhlcvStorageKind,
)
from src.domain.strategy_family_registry import initial_strategy_family_registry_seed
from src.domain.strategy_family_signal import (
    MarketSnapshot,
    SignalDataQualityStatus,
    StrategyFamilySignalInput,
)
from src.infrastructure.pg_historical_ohlcv_catalog_repository import (
    PgHistoricalOhlcvCatalogRepository,
)
from src.infrastructure.pg_models import PGBrcHistoricalOhlcvDatasetORM, PGKlineORM


BASE_TS = 1704067200000
HOUR_MS = 60 * 60 * 1000
FOUR_HOURS_MS = 4 * HOUR_MS
DAY_MS = 24 * HOUR_MS


@pytest_asyncio.fixture()
async def repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcHistoricalOhlcvDatasetORM.__table__.create)
        await conn.run_sync(PGKlineORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgHistoricalOhlcvCatalogRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


def _dataset(symbol: str, timeframe: str = "1h") -> HistoricalOhlcvDatasetMetadata:
    return HistoricalOhlcvDatasetMetadata(
        dataset_id=f"binance-um-{symbol}-{timeframe}-2021-2026",
        source="binance_vision",
        market="um_futures",
        symbol=symbol,
        timeframe=timeframe,
        start_time_ms=1609459200000,
        end_time_ms=1798761600000,
        row_count=43824,
        storage_kind=HistoricalOhlcvStorageKind.PG_TABLE,
        storage_ref="klines",
        timezone="UTC",
        data_quality_status=HistoricalDataQualityStatus.OK,
        missing_intervals=[],
        created_at_ms=1770000000000,
        updated_at_ms=1770000000000,
        notes="BRC historical OHLCV catalog metadata only.",
    )


def _bar(symbol: str, timeframe: str, index: int, step_ms: int) -> HistoricalOhlcvBar:
    open_price = Decimal("100") + Decimal(index)
    close = open_price + Decimal("0.5")
    return HistoricalOhlcvBar(
        source="binance_vision",
        market="um_futures",
        symbol=symbol,
        timeframe=timeframe,
        open_time_ms=BASE_TS + index * step_ms,
        open=open_price,
        high=open_price + Decimal("2"),
        low=open_price - Decimal("1"),
        close=close,
        volume=Decimal("10") + Decimal(index),
        quote_volume=None,
        close_time_ms=BASE_TS + (index + 1) * step_ms - 1,
        created_at_ms=1770000000000,
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


def test_migration_creates_historical_ohlcv_catalog_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-28-023_create_brc_historical_ohlcv_catalog.py"
    )
    spec = importlib.util.spec_from_file_location("historical_ohlcv_catalog_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run() -> set[str]:
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

    tables = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "brc_historical_ohlcv_datasets" in tables


def test_dataset_catalog_model_accepts_btc_eth_sol_2021_2026_metadata():
    btc = _dataset("BTCUSDT")
    eth = _dataset("ETHUSDT")
    sol = _dataset("SOLUSDT")

    assert btc.symbol == "BTCUSDT"
    assert eth.start_time_ms == 1609459200000
    assert sol.end_time_ms == 1798761600000
    assert btc.storage_kind == HistoricalOhlcvStorageKind.PG_TABLE


def test_dataset_catalog_rejects_forbidden_execution_order_fields():
    payload = _dataset("BTCUSDT").model_dump(mode="python")
    payload["missing_intervals"] = [{"quantity": "must_not_exist"}]

    with pytest.raises(ValueError, match="forbidden execution/order field"):
        HistoricalOhlcvDatasetMetadata.model_validate(payload)


@pytest.mark.asyncio
async def test_repository_upserts_datasets_and_lists_by_symbol_timeframe(repo):
    await repo.upsert_dataset_metadata(_dataset("BTCUSDT"))
    await repo.upsert_dataset_metadata(_dataset("ETHUSDT"))
    await repo.upsert_dataset_metadata(_dataset("SOLUSDT"))

    fetched = await repo.get_dataset_metadata("binance-um-BTCUSDT-1h-2021-2026")
    listed = await repo.list_datasets(symbol="BTCUSDT", timeframe="1h")

    assert fetched is not None
    assert fetched.symbol == "BTCUSDT"
    assert [item.dataset_id for item in listed] == ["binance-um-BTCUSDT-1h-2021-2026"]


@pytest.mark.asyncio
async def test_repository_inserts_and_fetches_ohlcv_bars(repo):
    bars = [_bar("BTCUSDT", "1h", index, HOUR_MS) for index in range(5)]

    inserted = await repo.upsert_bars(bars)
    duplicate_inserted = await repo.upsert_bars(bars)
    by_range = await repo.fetch_bars(
        symbol="BTCUSDT",
        timeframe="1h",
        start_time_ms=BASE_TS,
        end_time_ms=BASE_TS + 4 * HOUR_MS,
    )
    recent = await repo.fetch_recent_bars_ending_at(
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp_ms=BASE_TS + 4 * HOUR_MS,
        limit=3,
    )

    assert inserted == 5
    assert duplicate_inserted == 0
    assert [bar.open_time_ms for bar in by_range] == [bar.open_time_ms for bar in bars]
    assert [bar.open_time_ms for bar in recent] == [BASE_TS + 2 * HOUR_MS, BASE_TS + 3 * HOUR_MS, BASE_TS + 4 * HOUR_MS]


@pytest.mark.asyncio
async def test_historical_market_snapshot_builder_builds_market_snapshot(repo):
    await repo.upsert_bars([_bar("BTCUSDT", "1h", index, HOUR_MS) for index in range(16)])
    await repo.upsert_bars([_bar("BTCUSDT", "4h", index, FOUR_HOURS_MS) for index in range(4)])
    await repo.upsert_bars([_bar("BTCUSDT", "1d", index, DAY_MS) for index in range(2)])

    builder = HistoricalMarketSnapshotBuilder(repository=repo, primary_lookback=16, atr_period=14)
    snapshot = await builder.build(
        symbol="BTCUSDT",
        timestamp_ms=BASE_TS + 15 * HOUR_MS,
        primary_timeframe="1h",
        context_timeframes=["4h", "1d"],
    )

    assert isinstance(snapshot, MarketSnapshot)
    assert snapshot.source == "historical_ohlcv"
    assert snapshot.last_price == Decimal("115.5")
    assert snapshot.mark_price == Decimal("115.5")
    assert snapshot.volume == Decimal("25")
    assert snapshot.atr == Decimal("3")
    assert "1h" in snapshot.candle_context["windows"]
    assert "4h" in snapshot.candle_context["windows"]
    assert "1d" in snapshot.candle_context["windows"]
    assert "quote_volume" in snapshot.missing_fields
    assert not _contains_forbidden_key(snapshot.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_historical_market_snapshot_builder_degrades_without_atr(repo):
    await repo.upsert_bars([_bar("BTCUSDT", "1h", index, HOUR_MS) for index in range(3)])

    builder = HistoricalMarketSnapshotBuilder(repository=repo, primary_lookback=3, atr_period=14)
    snapshot = await builder.build(
        symbol="BTCUSDT",
        timestamp_ms=BASE_TS + 2 * HOUR_MS,
        primary_timeframe="1h",
        context_timeframes=["4h", "1d"],
    )

    assert snapshot.atr is None
    assert "atr" in snapshot.missing_fields
    assert "candle_context.4h" in snapshot.missing_fields
    assert "candle_context.1d" in snapshot.missing_fields


@pytest.mark.asyncio
async def test_historical_signal_input_builder_builds_tf_001_input_skeleton(repo):
    await repo.upsert_bars([_bar("BTCUSDT", "1h", index, HOUR_MS) for index in range(16)])
    await repo.upsert_bars([_bar("BTCUSDT", "4h", index, FOUR_HOURS_MS) for index in range(4)])
    await repo.upsert_bars([_bar("BTCUSDT", "1d", index, DAY_MS) for index in range(2)])
    seed = initial_strategy_family_registry_seed(now_ms=1770000000000)
    family = next(item for item in seed.families if item.family_id == "TF-001-live-readonly-v0")
    playbook = next(item for item in seed.playbooks if item.playbook_id == "TF-001-live-readonly-v0")

    market_builder = HistoricalMarketSnapshotBuilder(repository=repo, primary_lookback=16, atr_period=14)
    input_builder = HistoricalStrategyFamilySignalInputBuilder(market_snapshot_builder=market_builder)
    signal_input = await input_builder.build(
        strategy_family_metadata=family,
        playbook_metadata=playbook,
        symbol="BTCUSDT",
        timestamp_ms=BASE_TS + 15 * HOUR_MS,
        primary_timeframe="1h",
        context_timeframes=["4h", "1d"],
        evaluation_id="hist-eval-001",
    )

    assert isinstance(signal_input, StrategyFamilySignalInput)
    assert signal_input.evaluation_id == "hist-eval-001"
    assert signal_input.strategy_family_id == "TF-001-live-readonly-v0"
    assert signal_input.account_facts_snapshot.source == "historical_research"
    assert signal_input.account_facts_snapshot.positions == []
    assert signal_input.account_facts_snapshot.open_orders == []
    assert signal_input.execution_permission_resolution["final_permission"] == "signal_only"
    assert signal_input.execution_permission_resolution["final_permission"] != "order_allowed"
    assert signal_input.source == "historical_ohlcv_research"
    assert signal_input.input_quality.status == SignalDataQualityStatus.DEGRADED
    assert not _contains_forbidden_key(signal_input.model_dump(mode="json"))
