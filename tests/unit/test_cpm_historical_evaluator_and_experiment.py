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

from src.application.historical_signal_evaluation_service import CPMHistoricalExperimentService
from src.application.historical_signal_input_builder import (
    HistoricalMarketSnapshotBuilder,
    HistoricalStrategyFamilySignalInputBuilder,
)
from src.domain.cpm_historical_evaluator import CPM_FAMILY_ID, CPMRO001HistoricalEvaluator
from src.domain.forward_outcome_review import calculate_forward_outcomes
from src.domain.historical_ohlcv import HistoricalOhlcvBar
from src.domain.historical_signal_evaluation import (
    HistoricalExperimentVerdict,
    HistoricalForwardOutcomeStatus,
    HistoricalSignalEvaluationRun,
    HistoricalSignalEvaluationStatus,
    compute_historical_signal_summary,
    signal_output_record_from_output,
)
from src.domain.strategy_candidate_semantics import (
    EntrySetupKind,
    ExitPlanKind,
    StrategyArchetype,
    StrategyCandidateSemantics,
    StrategyPayoffProfile,
)
from src.domain.strategy_family_registry import initial_strategy_family_registry_seed
from src.domain.strategy_family_signal import SignalSide, SignalType
from src.infrastructure.pg_historical_ohlcv_catalog_repository import PgHistoricalOhlcvCatalogRepository
from src.infrastructure.pg_historical_signal_evaluation_repository import (
    PgHistoricalSignalEvaluationRepository,
)
from src.infrastructure.pg_models import (
    PGBrcHistoricalForwardOutcomeORM,
    PGBrcHistoricalSignalEvaluationRunORM,
    PGBrcHistoricalSignalOutputORM,
    PGKlineORM,
)


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
        await conn.run_sync(PGBrcHistoricalSignalEvaluationRunORM.__table__.create)
        await conn.run_sync(PGBrcHistoricalSignalOutputORM.__table__.create)
        await conn.run_sync(PGBrcHistoricalForwardOutcomeORM.__table__.create)
        await conn.run_sync(PGKlineORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield (
            PgHistoricalSignalEvaluationRepository(session_maker=session_maker),
            PgHistoricalOhlcvCatalogRepository(session_maker=session_maker),
        )
    finally:
        await engine.dispose()


def _cpm_seed():
    seed = initial_strategy_family_registry_seed(now_ms=NOW_MS)
    family = next(item for item in seed.families if item.family_id == CPM_FAMILY_ID)
    playbook = next(item for item in seed.playbooks if item.family_id == CPM_FAMILY_ID)
    return family, playbook


def _tf_seed():
    seed = initial_strategy_family_registry_seed(now_ms=NOW_MS)
    family = next(item for item in seed.families if item.family_id == "TF-001-live-readonly-v0")
    playbook = next(item for item in seed.playbooks if item.family_id == "TF-001-live-readonly-v0")
    return family, playbook


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
    bars.append(
        _bar(
            symbol,
            "1h",
            timestamp_ms,
            Decimal("105"),
            high=Decimal("105.2"),
            low=Decimal("102"),
        )
    )
    first_4h = timestamp_ms - 20 * FOUR_HOURS_MS
    for index in range(21):
        close = Decimal("100") + Decimal(index) * Decimal("0.3")
        bars.append(_bar(symbol, "4h", first_4h + index * FOUR_HOURS_MS, close))
    return bars


def _short_setup_bars(symbol: str, timestamp_ms: int) -> list[HistoricalOhlcvBar]:
    bars: list[HistoricalOhlcvBar] = []
    first_1h = timestamp_ms - 20 * HOUR_MS
    for index in range(20):
        close = Decimal("105") - Decimal(index) * Decimal("0.2")
        bars.append(_bar(symbol, "1h", first_1h + index * HOUR_MS, close))
    bars.append(
        _bar(
            symbol,
            "1h",
            timestamp_ms,
            Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99.8"),
        )
    )
    first_4h = timestamp_ms - 20 * FOUR_HOURS_MS
    for index in range(21):
        close = Decimal("106") - Decimal(index) * Decimal("0.3")
        bars.append(_bar(symbol, "4h", first_4h + index * FOUR_HOURS_MS, close))
    return bars


def _flat_setup_bars(symbol: str, timestamp_ms: int) -> list[HistoricalOhlcvBar]:
    bars: list[HistoricalOhlcvBar] = []
    first_1h = timestamp_ms - 20 * HOUR_MS
    first_4h = timestamp_ms - 20 * FOUR_HOURS_MS
    for index in range(21):
        bars.append(_bar(symbol, "1h", first_1h + index * HOUR_MS, Decimal("100")))
        bars.append(_bar(symbol, "4h", first_4h + index * FOUR_HOURS_MS, Decimal("100")))
    return bars


def _future_bars(symbol: str, start_time_ms: int) -> list[HistoricalOhlcvBar]:
    closes = [Decimal("101"), Decimal("99"), Decimal("103"), Decimal("102")]
    highs = [Decimal("102"), Decimal("101"), Decimal("104"), Decimal("103")]
    lows = [Decimal("99"), Decimal("98"), Decimal("100"), Decimal("101")]
    return [
        _bar(
            symbol,
            "1h",
            start_time_ms + (index + 1) * HOUR_MS,
            close,
            high=highs[index],
            low=lows[index],
        )
        for index, close in enumerate(closes)
    ]


async def _build_input(repo, symbol: str, timestamp_ms: int, *, family=None, playbook=None):
    resolved_family, resolved_playbook = (family, playbook) if family is not None else _cpm_seed()
    market_builder = HistoricalMarketSnapshotBuilder(
        repository=repo,
        primary_lookback=64,
        context_lookback=64,
        atr_period=14,
    )
    input_builder = HistoricalStrategyFamilySignalInputBuilder(market_snapshot_builder=market_builder)
    return await input_builder.build(
        strategy_family_metadata=resolved_family,
        playbook_metadata=resolved_playbook,
        symbol=symbol,
        timestamp_ms=timestamp_ms,
        primary_timeframe="1h",
        context_timeframes=["4h"],
        evaluation_id=f"eval-{symbol}-{timestamp_ms}",
    )


def _run() -> HistoricalSignalEvaluationRun:
    return HistoricalSignalEvaluationRun(
        run_id="cpm-hist-run-001",
        strategy_family_id=CPM_FAMILY_ID,
        strategy_family_version_id=CPM_FAMILY_ID,
        playbook_id=CPM_FAMILY_ID,
        symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        primary_timeframe="1h",
        context_timeframes=["4h"],
        start_time_ms=BASE_TS,
        end_time_ms=BASE_TS + 20 * HOUR_MS,
        sampling_method="explicit_timestamps",
        sampling_interval_bars=1,
        sample_limit=10,
        status=HistoricalSignalEvaluationStatus.RUNNING,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
        notes="historical CPM compact run",
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


@pytest.mark.asyncio
async def test_cpm_evaluator_invalid_wrong_family_and_missing_context(repos):
    _eval_repo, ohlcv_repo = repos
    timestamp_ms = BASE_TS + 20 * HOUR_MS
    await ohlcv_repo.upsert_bars(_long_setup_bars("BTCUSDT", timestamp_ms))
    tf_family, tf_playbook = _tf_seed()
    wrong_family_input = await _build_input(
        ohlcv_repo,
        "BTCUSDT",
        timestamp_ms,
        family=tf_family,
        playbook=tf_playbook,
    )
    wrong_output = CPMRO001HistoricalEvaluator().evaluate(wrong_family_input)
    assert wrong_output.signal_type == SignalType.INVALID
    assert "cpm_invalid_wrong_family" in wrong_output.reason_codes

    cpm_family, cpm_playbook = _cpm_seed()
    await ohlcv_repo.upsert_bars([bar for bar in _long_setup_bars("ETHUSDT", timestamp_ms) if bar.timeframe == "1h"])
    missing_4h_input = await _build_input(
        ohlcv_repo,
        "ETHUSDT",
        timestamp_ms,
        family=cpm_family,
        playbook=cpm_playbook,
    )
    missing_output = CPMRO001HistoricalEvaluator().evaluate(missing_4h_input)
    assert missing_output.signal_type == SignalType.INVALID
    assert "cpm_invalid_missing_4h_context" in missing_output.reason_codes

    sol_bars = _long_setup_bars("SOLUSDT", timestamp_ms)
    await ohlcv_repo.upsert_bars(
        [bar for bar in sol_bars if bar.timeframe == "1h"][:10]
        + [bar for bar in sol_bars if bar.timeframe == "4h"][:10]
    )
    insufficient_input = await _build_input(ohlcv_repo, "SOLUSDT", timestamp_ms)
    insufficient_output = CPMRO001HistoricalEvaluator().evaluate(insufficient_input)
    assert insufficient_output.signal_type == SignalType.INVALID
    assert "cpm_invalid_insufficient_candles" in insufficient_output.reason_codes


@pytest.mark.asyncio
async def test_cpm_evaluator_no_action_for_trend_ambiguous(repos):
    _eval_repo, ohlcv_repo = repos
    timestamp_ms = BASE_TS + 20 * HOUR_MS
    await ohlcv_repo.upsert_bars(_flat_setup_bars("BTCUSDT", timestamp_ms))
    signal_input = await _build_input(ohlcv_repo, "BTCUSDT", timestamp_ms)

    output = CPMRO001HistoricalEvaluator().evaluate(signal_input)

    assert output.signal_type == SignalType.NO_ACTION
    assert output.side == SignalSide.NONE
    assert "cpm_no_action_trend_ambiguous" in output.reason_codes
    assert output.not_order is True
    assert output.not_execution_intent is True


@pytest.mark.asyncio
async def test_cpm_evaluator_would_enter_long_and_short(repos):
    _eval_repo, ohlcv_repo = repos
    timestamp_ms = BASE_TS + 20 * HOUR_MS
    await ohlcv_repo.upsert_bars(_long_setup_bars("BTCUSDT", timestamp_ms))
    await ohlcv_repo.upsert_bars(_short_setup_bars("ETHUSDT", timestamp_ms))

    long_output = CPMRO001HistoricalEvaluator().evaluate(
        await _build_input(ohlcv_repo, "BTCUSDT", timestamp_ms)
    )
    short_output = CPMRO001HistoricalEvaluator().evaluate(
        await _build_input(ohlcv_repo, "ETHUSDT", timestamp_ms)
    )

    assert long_output.signal_type == SignalType.WOULD_ENTER
    assert long_output.side == SignalSide.LONG
    assert {
        "cpm_long_htf_trend_intact",
        "cpm_long_pullback_depth_normal",
        "cpm_long_reclaim_confirmed",
    }.issubset(set(long_output.reason_codes))
    assert short_output.signal_type == SignalType.WOULD_ENTER
    assert short_output.side == SignalSide.SHORT
    assert {
        "cpm_short_htf_trend_intact",
        "cpm_short_bounce_depth_normal",
        "cpm_short_loss_confirmed",
    }.issubset(set(short_output.reason_codes))
    candidate_semantics = StrategyCandidateSemantics.model_validate(
        long_output.evidence_payload["candidate_semantics"]
    )
    assert candidate_semantics.archetype == StrategyArchetype.LONG_PULLBACK_CONTINUATION
    assert candidate_semantics.payoff_profile == StrategyPayoffProfile.RIGHT_TAIL
    assert candidate_semantics.entry.kind == EntrySetupKind.PULLBACK_RECLAIM
    assert candidate_semantics.entry.side == "long"
    assert candidate_semantics.protection.stop_price_reference == Decimal("99.8")
    assert candidate_semantics.exit.plan_kind == ExitPlanKind.PARTIAL_TP_PLUS_RUNNER
    assert candidate_semantics.exit.runner is not None
    assert candidate_semantics.exit.runner.preserve_right_tail is True
    assert "candidate_semantics" not in short_output.evidence_payload
    assert long_output.not_order is True
    assert long_output.not_execution_intent is True
    assert not _contains_forbidden_key(long_output.model_dump(mode="json"))
    assert not _contains_forbidden_key(short_output.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_high_confidence_does_not_authorize_execution(repos):
    _eval_repo, ohlcv_repo = repos
    timestamp_ms = BASE_TS + 20 * HOUR_MS
    await ohlcv_repo.upsert_bars(_long_setup_bars("BTCUSDT", timestamp_ms))
    output = CPMRO001HistoricalEvaluator().evaluate(
        await _build_input(ohlcv_repo, "BTCUSDT", timestamp_ms)
    )

    assert output.confidence == Decimal("0.70")
    assert output.required_execution_mode == "observe_only"
    assert output.not_order is True
    assert output.not_execution_intent is True
    assert "authorization" in output.confidence_semantics


@pytest.mark.asyncio
async def test_forward_outcome_calculator_long_short_and_incomplete(repos):
    _eval_repo, ohlcv_repo = repos
    timestamp_ms = BASE_TS + 20 * HOUR_MS
    await ohlcv_repo.upsert_bars(_long_setup_bars("BTCUSDT", timestamp_ms))
    await ohlcv_repo.upsert_bars(_short_setup_bars("ETHUSDT", timestamp_ms))
    long_output = CPMRO001HistoricalEvaluator().evaluate(
        await _build_input(ohlcv_repo, "BTCUSDT", timestamp_ms)
    )
    short_output = CPMRO001HistoricalEvaluator().evaluate(
        await _build_input(ohlcv_repo, "ETHUSDT", timestamp_ms)
    )
    long_entry = _bar("BTCUSDT", "1h", timestamp_ms, Decimal("100"))
    short_entry = _bar("ETHUSDT", "1h", timestamp_ms, Decimal("100"))
    long_outcome = calculate_forward_outcomes(
        run_id="run",
        signal_output=long_output,
        entry_bar=long_entry,
        future_bars=_future_bars("BTCUSDT", timestamp_ms),
        created_at_ms=NOW_MS,
        windows={"4h": 4, "24h": 24},
    )
    short_future = [
        _bar("ETHUSDT", "1h", timestamp_ms + HOUR_MS, Decimal("99"), high=Decimal("101"), low=Decimal("98")),
        _bar("ETHUSDT", "1h", timestamp_ms + 2 * HOUR_MS, Decimal("102"), high=Decimal("104"), low=Decimal("101")),
        _bar("ETHUSDT", "1h", timestamp_ms + 3 * HOUR_MS, Decimal("97"), high=Decimal("99"), low=Decimal("96")),
        _bar("ETHUSDT", "1h", timestamp_ms + 4 * HOUR_MS, Decimal("98"), high=Decimal("100"), low=Decimal("97")),
    ]
    short_outcome = calculate_forward_outcomes(
        run_id="run",
        signal_output=short_output,
        entry_bar=short_entry,
        future_bars=short_future,
        created_at_ms=NOW_MS,
        windows={"4h": 4, "24h": 24},
    )

    assert long_outcome[0].status == HistoricalForwardOutcomeStatus.COMPLETE
    assert long_outcome[0].mfe_pct == Decimal("4.0000")
    assert long_outcome[0].mae_pct == Decimal("-2.0000")
    assert long_outcome[0].time_to_mfe_bars == 3
    assert long_outcome[0].time_to_mae_bars == 2
    assert long_outcome[1].status == HistoricalForwardOutcomeStatus.INCOMPLETE
    assert short_outcome[0].mfe_pct == Decimal("4.0000")
    assert short_outcome[0].mae_pct == Decimal("-4.0000")
    assert short_outcome[0].time_to_mfe_bars == 3
    assert short_outcome[0].time_to_mae_bars == 2


def test_migration_creates_historical_signal_evaluation_tables():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-28-025_create_historical_signal_evaluation.py"
    )
    spec = importlib.util.spec_from_file_location("historical_signal_evaluation_migration", migration_path)
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

    assert "brc_historical_signal_evaluation_runs" in tables
    assert "brc_historical_signal_outputs" in tables
    assert "brc_historical_forward_outcomes" in tables


@pytest.mark.asyncio
async def test_historical_signal_evaluation_repository_round_trip(repos):
    eval_repo, ohlcv_repo = repos
    timestamp_ms = BASE_TS + 20 * HOUR_MS
    await ohlcv_repo.upsert_bars(_long_setup_bars("BTCUSDT", timestamp_ms))
    output = CPMRO001HistoricalEvaluator().evaluate(
        await _build_input(ohlcv_repo, "BTCUSDT", timestamp_ms)
    )
    record = signal_output_record_from_output(run_id="cpm-hist-run-001", output=output, created_at_ms=NOW_MS)
    outcomes = calculate_forward_outcomes(
        run_id="cpm-hist-run-001",
        signal_output=output,
        entry_bar=_bar("BTCUSDT", "1h", timestamp_ms, Decimal("100")),
        future_bars=_future_bars("BTCUSDT", timestamp_ms),
        created_at_ms=NOW_MS,
        windows={"4h": 4},
    )

    await eval_repo.create_evaluation_run(_run())
    await eval_repo.record_signal_output(record)
    await eval_repo.record_forward_outcome(outcomes[0])
    summary = compute_historical_signal_summary(
        run_id="cpm-hist-run-001",
        signal_records=[record],
        outcomes=outcomes,
    )
    await eval_repo.complete_evaluation_run(
        run_id="cpm-hist-run-001",
        summary=summary,
        updated_at_ms=NOW_MS + 1,
    )

    fetched_run = await eval_repo.get_evaluation_run("cpm-hist-run-001")
    fetched_records = await eval_repo.list_signal_outputs("cpm-hist-run-001")
    fetched_outcomes = await eval_repo.list_forward_outcomes("cpm-hist-run-001")
    fetched_summary = await eval_repo.get_evaluation_summary("cpm-hist-run-001")

    assert fetched_run is not None
    assert fetched_run.status == HistoricalSignalEvaluationStatus.COMPLETED
    assert fetched_records[0].signal_type == SignalType.WOULD_ENTER
    assert fetched_records[0].not_order is True
    assert fetched_records[0].not_execution_intent is True
    assert fetched_outcomes[0].mfe_pct == Decimal("4.00000000")
    assert fetched_summary is not None
    assert fetched_summary.would_enter_count == 1


@pytest.mark.asyncio
async def test_cpm_historical_experiment_service_persists_outputs_and_outcomes(repos):
    eval_repo, ohlcv_repo = repos
    timestamp_ms = BASE_TS + 20 * HOUR_MS
    await ohlcv_repo.upsert_bars(_long_setup_bars("BTCUSDT", timestamp_ms))
    await ohlcv_repo.upsert_bars(_flat_setup_bars("ETHUSDT", timestamp_ms))
    await ohlcv_repo.upsert_bars(_future_bars("BTCUSDT", timestamp_ms))
    family, playbook = _cpm_seed()
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

    summary = await service.run_experiment(
        run_id="cpm-service-run-001",
        strategy_family_metadata=family,
        playbook_metadata=playbook,
        symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        primary_timeframe="1h",
        context_timeframes=["4h"],
        start_time_ms=BASE_TS,
        end_time_ms=timestamp_ms,
        explicit_timestamps=[timestamp_ms],
        sample_limit=10,
    )
    records = await eval_repo.list_signal_outputs("cpm-service-run-001")
    outcomes = await eval_repo.list_forward_outcomes("cpm-service-run-001")
    stored_summary = await eval_repo.get_evaluation_summary("cpm-service-run-001")

    assert summary.total_evaluations == 3
    assert summary.signal_counts_by_type[SignalType.WOULD_ENTER.value] == 1
    assert summary.signal_counts_by_type[SignalType.NO_ACTION.value] == 1
    assert summary.signal_counts_by_type[SignalType.INVALID.value] == 1
    assert len(records) == 3
    assert len(outcomes) == 4
    assert all(outcome.signal_id == records[0].signal_id for outcome in outcomes)
    assert stored_summary is not None
    assert stored_summary.suggested_verdict in {
        HistoricalExperimentVerdict.PARK,
        HistoricalExperimentVerdict.NEEDS_REFINEMENT,
    }
    assert not _contains_forbidden_key([record.model_dump(mode="json") for record in records])
    assert not _contains_forbidden_key([outcome.model_dump(mode="json") for outcome in outcomes])


def test_experiment_service_exposes_no_execution_order_or_router_methods():
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
    for cls in (
        CPMHistoricalExperimentService,
        PgHistoricalSignalEvaluationRepository,
        CPMRO001HistoricalEvaluator,
    ):
        public_methods = [
            name
            for name, value in py_inspect.getmembers(cls, predicate=py_inspect.isfunction)
            if not name.startswith("_")
        ]
        assert public_methods
        for method_name in public_methods:
            assert all(term not in method_name for term in forbidden_terms)
