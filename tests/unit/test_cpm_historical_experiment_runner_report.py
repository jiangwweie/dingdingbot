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

from src.application.cpm_historical_experiment_runner import (
    CPMHistoricalExperimentRunRequest,
    CPMHistoricalExperimentRunner,
)
from src.application.historical_signal_evaluation_service import CPMHistoricalExperimentService
from src.application.historical_signal_input_builder import (
    HistoricalMarketSnapshotBuilder,
    HistoricalStrategyFamilySignalInputBuilder,
)
from src.domain.cpm_historical_evaluator import CPMRO001HistoricalEvaluator
from src.domain.historical_ohlcv import (
    HistoricalDataQualityStatus,
    HistoricalOhlcvBar,
    HistoricalOhlcvDatasetMetadata,
    HistoricalOhlcvStorageKind,
)
from src.domain.historical_signal_evaluation import HistoricalExperimentVerdict
from src.domain.strategy_family_signal import SignalType
from src.infrastructure.pg_historical_ohlcv_catalog_repository import PgHistoricalOhlcvCatalogRepository
from src.infrastructure.pg_historical_signal_evaluation_repository import (
    PgHistoricalSignalEvaluationRepository,
)
from src.infrastructure.pg_models import (
    PGBrcHistoricalForwardOutcomeORM,
    PGBrcHistoricalOhlcvDatasetORM,
    PGBrcHistoricalSignalEvaluationRunORM,
    PGBrcHistoricalSignalOutputORM,
    PGBrcStrategyFamilyPlaybookORM,
    PGBrcStrategyFamilyRegistryORM,
    PGKlineORM,
)
from src.infrastructure.pg_strategy_family_registry_repository import PgStrategyFamilyRegistryRepository


BASE_TS = 1704067200000
HOUR_MS = 60 * 60 * 1000
FOUR_HOURS_MS = 4 * HOUR_MS
NOW_MS = 1770000000000


@pytest_asyncio.fixture()
async def repos():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcStrategyFamilyRegistryORM.__table__.create)
        await conn.run_sync(PGBrcStrategyFamilyPlaybookORM.__table__.create)
        await conn.run_sync(PGBrcHistoricalOhlcvDatasetORM.__table__.create)
        await conn.run_sync(PGBrcHistoricalSignalEvaluationRunORM.__table__.create)
        await conn.run_sync(PGBrcHistoricalSignalOutputORM.__table__.create)
        await conn.run_sync(PGBrcHistoricalForwardOutcomeORM.__table__.create)
        await conn.run_sync(PGKlineORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield (
            PgStrategyFamilyRegistryRepository(session_maker=session_maker),
            PgHistoricalOhlcvCatalogRepository(session_maker=session_maker),
            PgHistoricalSignalEvaluationRepository(session_maker=session_maker),
        )
    finally:
        await engine.dispose()


def _dataset(symbol: str, timeframe: str) -> HistoricalOhlcvDatasetMetadata:
    return HistoricalOhlcvDatasetMetadata(
        dataset_id=f"test-{symbol}-{timeframe}-2021-2026",
        source="unit_test",
        market="um_futures",
        symbol=symbol,
        timeframe=timeframe,
        start_time_ms=1609459200000,
        end_time_ms=1798761600000,
        row_count=100,
        storage_kind=HistoricalOhlcvStorageKind.PG_TABLE,
        storage_ref="klines",
        timezone="UTC",
        data_quality_status=HistoricalDataQualityStatus.OK,
        missing_intervals=[],
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
        notes="test catalog metadata",
    )


def _bar(
    symbol: str,
    timeframe: str,
    open_time_ms: int,
    close: Decimal,
    *,
    high: Decimal | None = None,
    low: Decimal | None = None,
) -> HistoricalOhlcvBar:
    return HistoricalOhlcvBar(
        source="test",
        market="historical",
        symbol=symbol,
        timeframe=timeframe,
        open_time_ms=open_time_ms,
        open=close,
        high=high or close + Decimal("0.2"),
        low=low or close - Decimal("0.2"),
        close=close,
        volume=Decimal("100"),
        quote_volume=None,
        close_time_ms=open_time_ms + (HOUR_MS if timeframe == "1h" else FOUR_HOURS_MS) - 1,
        created_at_ms=NOW_MS,
    )


def _long_setup_bars(symbol: str, timestamp_ms: int) -> list[HistoricalOhlcvBar]:
    bars: list[HistoricalOhlcvBar] = []
    first_1h = timestamp_ms - 20 * HOUR_MS
    for index in range(20):
        close = Decimal("100") + Decimal(index) * Decimal("0.2")
        bars.append(_bar(symbol, "1h", first_1h + index * HOUR_MS, close))
    bars.append(_bar(symbol, "1h", timestamp_ms, Decimal("105"), high=Decimal("105.2"), low=Decimal("102")))
    first_4h = timestamp_ms - 20 * FOUR_HOURS_MS
    for index in range(21):
        close = Decimal("100") + Decimal(index) * Decimal("0.3")
        bars.append(_bar(symbol, "4h", first_4h + index * FOUR_HOURS_MS, close))
    return bars


def _future_bars(symbol: str, timestamp_ms: int) -> list[HistoricalOhlcvBar]:
    return [
        _bar(symbol, "1h", timestamp_ms + HOUR_MS, Decimal("106"), high=Decimal("107"), low=Decimal("104")),
        _bar(symbol, "1h", timestamp_ms + 2 * HOUR_MS, Decimal("104"), high=Decimal("106"), low=Decimal("103")),
        _bar(symbol, "1h", timestamp_ms + 3 * HOUR_MS, Decimal("108"), high=Decimal("109"), low=Decimal("105")),
        _bar(symbol, "1h", timestamp_ms + 4 * HOUR_MS, Decimal("107"), high=Decimal("108"), low=Decimal("106")),
    ]


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


async def _build_runner(repos):
    registry_repo, ohlcv_repo, eval_repo = repos
    await registry_repo.upsert_initial_seed(now_ms=NOW_MS)
    market_builder = HistoricalMarketSnapshotBuilder(
        repository=ohlcv_repo,
        primary_lookback=64,
        context_lookback=64,
        atr_period=14,
    )
    service = CPMHistoricalExperimentService(
        evaluation_repository=eval_repo,
        ohlcv_repository=ohlcv_repo,
        signal_input_builder=HistoricalStrategyFamilySignalInputBuilder(market_snapshot_builder=market_builder),
        evaluator=CPMRO001HistoricalEvaluator(),
        now_ms=lambda: NOW_MS,
    )
    return CPMHistoricalExperimentRunner(
        registry_repository=registry_repo,
        dataset_repository=ohlcv_repo,
        evaluation_repository=eval_repo,
        experiment_service=service,
        now_ms=lambda: NOW_MS,
    )


def test_runner_request_rejects_unbounded_or_unsupported_inputs():
    with pytest.raises(ValueError, match="unsupported symbols"):
        CPMHistoricalExperimentRunRequest(
            symbols=["DOGE/USDT:USDT"],
            start_time_ms=BASE_TS,
            end_time_ms=BASE_TS + HOUR_MS,
        )
    with pytest.raises(ValueError, match="primary_timeframe=1h"):
        CPMHistoricalExperimentRunRequest(
            symbols=["BTC/USDT:USDT"],
            primary_timeframe="5m",
            start_time_ms=BASE_TS,
            end_time_ms=BASE_TS + HOUR_MS,
        )
    with pytest.raises(ValueError):
        CPMHistoricalExperimentRunRequest(
            symbols=["BTC/USDT:USDT"],
            start_time_ms=BASE_TS,
            end_time_ms=BASE_TS + HOUR_MS,
            sample_limit=10001,
        )


def test_migration_adds_owner_report_column():
    migration_025_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-28-025_create_historical_signal_evaluation.py"
    )
    migration_026_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-28-026_add_historical_signal_owner_report.py"
    )
    spec_025 = importlib.util.spec_from_file_location("historical_signal_eval_025", migration_025_path)
    spec_026 = importlib.util.spec_from_file_location("historical_signal_eval_026", migration_026_path)
    assert spec_025 is not None and spec_025.loader is not None
    assert spec_026 is not None and spec_026.loader is not None
    migration_025 = importlib.util.module_from_spec(spec_025)
    migration_026 = importlib.util.module_from_spec(spec_026)
    spec_025.loader.exec_module(migration_025)
    spec_026.loader.exec_module(migration_026)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _migrate() -> list[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                old_025 = migration_025.op
                old_026 = migration_026.op
                migration_025.op = Operations(MigrationContext.configure(sync_conn))
                migration_026.op = Operations(MigrationContext.configure(sync_conn))
                try:
                    migration_025.upgrade()
                    migration_026.upgrade()
                    return [
                        column["name"]
                        for column in inspect(sync_conn).get_columns("brc_historical_signal_evaluation_runs")
                    ]
                finally:
                    migration_025.op = old_025
                    migration_026.op = old_026

            return await conn.run_sync(upgrade)

    columns = asyncio.run(_migrate())
    asyncio.run(engine.dispose())

    assert "owner_report" in columns


@pytest.mark.asyncio
async def test_runner_executes_bounded_cpm_experiment_and_persists_owner_report(repos):
    _registry_repo, ohlcv_repo, eval_repo = repos
    timestamp_ms = BASE_TS + 20 * HOUR_MS
    for timeframe in ["1h", "4h"]:
        await ohlcv_repo.upsert_dataset_metadata(_dataset("BTC/USDT:USDT", timeframe))
    await ohlcv_repo.upsert_bars(_long_setup_bars("BTC/USDT:USDT", timestamp_ms))
    await ohlcv_repo.upsert_bars(_future_bars("BTC/USDT:USDT", timestamp_ms))
    runner = await _build_runner(repos)

    result = await runner.run(
        CPMHistoricalExperimentRunRequest(
            symbols=["BTC/USDT:USDT"],
            context_timeframes=["4h"],
            start_time_ms=timestamp_ms,
            end_time_ms=timestamp_ms,
            sampling_interval_bars=1,
            sample_limit=1,
            run_label="unit-cpm-report",
        )
    )
    records = await eval_repo.list_signal_outputs(result.run_id)
    outcomes = await eval_repo.list_forward_outcomes(result.run_id)
    persisted_report = await eval_repo.get_owner_review_report(result.run_id)

    assert result.dataset_ids == ["test-BTC/USDT:USDT-1h-2021-2026", "test-BTC/USDT:USDT-4h-2021-2026"]
    assert result.summary.total_evaluations == 1
    assert result.summary.signal_counts_by_type[SignalType.WOULD_ENTER.value] == 1
    assert len(records) == 1
    assert records[0].not_order is True
    assert records[0].not_execution_intent is True
    assert len(outcomes) == 4
    assert persisted_report is not None
    assert persisted_report.run_id == result.run_id
    assert persisted_report.total_evaluations == 1
    assert persisted_report.would_enter_count == 1
    assert persisted_report.symbol_breakdown["BTC/USDT:USDT"][SignalType.WOULD_ENTER.value] == 1
    assert "4h" in persisted_report.forward_outcome_by_window
    assert Decimal(str(persisted_report.forward_outcome_by_window["4h"]["mean_mfe_pct"])) == Decimal("3.80950000")
    assert Decimal(str(persisted_report.forward_outcome_by_window["4h"]["mean_abs_mae_pct"])) == Decimal("1.90480000")
    assert Decimal(str(persisted_report.forward_outcome_by_window["4h"]["follow_through_rate"])) == Decimal("1.00000000")
    assert Decimal(str(persisted_report.forward_outcome_by_window["4h"]["invalidation_hit_rate"])) == Decimal("0E-8")
    assert persisted_report.return_time_curve_summary["4h"][0]["bar"] == 1
    assert persisted_report.advisory_verdict in {
        HistoricalExperimentVerdict.PARK,
        HistoricalExperimentVerdict.NEEDS_REFINEMENT,
        HistoricalExperimentVerdict.CONTINUE,
    }
    assert persisted_report.verdict_reasons
    assert not _contains_forbidden_key(persisted_report.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_runner_requires_registered_datasets_when_enabled(repos):
    runner = await _build_runner(repos)

    with pytest.raises(ValueError, match="registered historical datasets missing"):
        await runner.run(
            CPMHistoricalExperimentRunRequest(
                symbols=["BTC/USDT:USDT"],
                context_timeframes=["4h"],
                start_time_ms=BASE_TS,
                end_time_ms=BASE_TS,
                sample_limit=1,
            )
        )


def test_runner_exposes_no_execution_order_or_router_methods():
    forbidden_terms = [
        "execution_intent",
        "trial_trade_intent",
        "order",
        "router",
        "route",
        "cancel",
        "close",
        "flatten",
        "sizing",
        "leverage",
        "venue",
    ]
    public_methods = [
        name
        for name, value in py_inspect.getmembers(CPMHistoricalExperimentRunner, predicate=py_inspect.isfunction)
        if not name.startswith("_")
    ]
    assert public_methods == ["run"]
    for method_name in public_methods:
        assert all(term not in method_name for term in forbidden_terms)
