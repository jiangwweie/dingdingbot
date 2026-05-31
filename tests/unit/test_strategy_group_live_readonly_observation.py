from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.strategy_group_live_readonly_observation import (
    InMemoryStrategyGroupObservationSink,
    MI001MomentumImpulseReadOnlyEvaluator,
    SampleStrategyGroupMarketBarSource,
    build_strategy_group_live_readonly_observation_v1,
    run_strategy_group_live_readonly_observation_once,
    _market_snapshot,
    _sample_mi_candles,
    _sample_signal_input,
)
from src.application.strategy_group_forward_review import (
    StrategyGroupForwardReviewRecord,
    calculate_forward_reviews_for_observation,
)
from src.domain.strategy_family_signal import SignalSide, SignalType
from src.infrastructure.binance_public_kline_market_source import BinancePublicKlineMarketSource
from src.infrastructure.pg_models import PGBrcStrategyGroupForwardReviewORM, PGBrcStrategyGroupObservationORM
from src.infrastructure.pg_strategy_group_forward_review_repository import PgStrategyGroupForwardReviewRepository
from src.infrastructure.pg_strategy_group_observation_repository import PgStrategyGroupObservationRepository
from src.application.strategy_group_observation_case_queue import build_observation_case_queue
from src.application.strategy_group_readonly_observation_scheduler import (
    run_scheduled_readonly_observation_once,
)


@pytest_asyncio.fixture()
async def observation_repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcStrategyGroupObservationORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgStrategyGroupObservationRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture()
async def forward_review_repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcStrategyGroupForwardReviewORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgStrategyGroupForwardReviewRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


def test_live_readonly_observation_v1_exposes_mi_and_cpm_without_execution_fields():
    payload = build_strategy_group_live_readonly_observation_v1()

    candidate_ids = {item.candidate_id for item in payload.candidates}
    assert {"MI-001-SOL-LONG", "MI-001-BNB-LONG", "CPM-RO-001"} <= candidate_ids
    assert payload.runner_mapping["strategy_specific_signal_evaluator_glue_wired"] is True
    assert payload.live_observation_active is False
    assert payload.live_ready is False
    assert len(payload.current_signals) == 3
    assert payload.sink_summary["pg_observation_sink"] == "blocked_schema_gap_no_live_observation_table_found"
    assert payload.input_source_summary["external_exchange_write"] is False
    assert payload.review_hook_summary["review_hook_status"] == "records_include_pending_forward_outcome_windows"
    assert payload.non_permissions["no_execution_intent"] is True
    assert payload.non_permissions["no_order_permission"] is True

    raw = payload.model_dump(mode="json")
    text = str(raw)
    assert "execution_permission_granted" not in text
    assert "order_permission_granted" not in text
    assert "trial_started" not in text


def test_run_once_records_observe_only_signal_history_without_runtime_effect():
    sink = InMemoryStrategyGroupObservationSink()
    payload = run_strategy_group_live_readonly_observation_once(
        market_source=SampleStrategyGroupMarketBarSource(),
        sink=sink,
    )

    assert len(payload.current_signals) == 3
    assert len(payload.signal_history) == 3
    assert payload.sink_summary["sink_status"] == "process_local_sink_recording_enabled"
    assert payload.sink_summary["writes_execution_or_order_tables"] is False
    assert all(record.not_order is True for record in payload.signal_history)
    assert all(record.not_execution_intent is True for record in payload.signal_history)
    assert all(record.no_runtime_start is True for record in payload.signal_history)


def test_binance_public_kline_source_returns_only_closed_public_bars():
    now_ms = 1_800_000_000_000
    rows = []
    for index in range(6):
        open_time = now_ms - (6 - index) * 60 * 60 * 1000
        rows.append(
            [
                open_time,
                "100",
                "102",
                "99",
                str(100 + index),
                "1234",
                open_time + 60 * 60 * 1000 - 1,
            ]
        )
    rows.append(
        [
            now_ms,
            "200",
            "202",
            "199",
            "201",
            "999",
            now_ms + 60 * 60 * 1000 - 1,
        ]
    )
    requested_urls: list[str] = []

    def transport(url: str, timeout: float) -> list:
        requested_urls.append(url)
        assert timeout == 10.0
        return rows

    source = BinancePublicKlineMarketSource(now_ms=lambda: now_ms, transport=transport)

    candles = source.latest_closed_candles(symbol="SOL/USDT:USDT", timeframe="1h", limit=3)

    assert "symbol=SOLUSDT" in requested_urls[0]
    assert "interval=1h" in requested_urls[0]
    assert source.source_type == "live_market_read_only"
    assert source.is_live_read_only is True
    assert [str(candle.close) for candle in candles] == ["103", "104", "105"]
    assert all(candle.is_closed is True for candle in candles)


def test_live_market_source_records_observe_only_history_with_live_source_metadata():
    def transport(url: str, _timeout: float) -> list:
        interval_ms = 4 * 60 * 60 * 1000 if "interval=4h" in url else 60 * 60 * 1000
        now_ms = 1_800_000_000_000
        rows = []
        for index in range(140):
            open_time = now_ms - (140 - index) * interval_ms
            close = 100 + index * 0.1
            rows.append(
                [
                    open_time,
                    str(close - 0.2),
                    str(close + 0.3),
                    str(close - 0.4),
                    str(close),
                    "500",
                    open_time + interval_ms - 1,
                ]
            )
        return rows

    source = BinancePublicKlineMarketSource(now_ms=lambda: 1_800_000_000_000, transport=transport)
    payload = run_strategy_group_live_readonly_observation_once(
        market_source=source,
        sink=InMemoryStrategyGroupObservationSink(),
    )

    assert len(payload.current_signals) == 3
    assert payload.input_source_summary["source_type"] == "live_market_read_only"
    assert payload.input_source_summary["is_live_read_only"] is True
    assert payload.input_source_summary["fallback_used"] is False
    assert all(record.source_type == "live_market_read_only" for record in payload.signal_history)
    assert all(record.market_source == "binance_usdm_public_klines_read_only" for record in payload.signal_history)
    assert all(record.not_order is True for record in payload.signal_history)
    assert all(record.not_execution_intent is True for record in payload.signal_history)


@pytest.mark.asyncio
async def test_pg_observation_repository_round_trip(observation_repo):
    payload = run_strategy_group_live_readonly_observation_once(
        market_source=SampleStrategyGroupMarketBarSource(),
        sink=InMemoryStrategyGroupObservationSink(),
    )

    for record in payload.current_signals:
        await observation_repo.record(record)

    recent = await observation_repo.list_recent(limit=10)
    current = await observation_repo.list_current_by_candidate(
        candidate_ids=["MI-001-SOL-LONG", "MI-001-BNB-LONG", "CPM-RO-001"],
    )

    assert len(recent) == 3
    assert [record.candidate_id for record in current] == [
        "MI-001-SOL-LONG",
        "MI-001-BNB-LONG",
        "CPM-RO-001",
    ]
    assert all(record.sink_status == "recorded_pg" for record in recent)
    assert all(record.not_order is True for record in recent)
    assert all(record.not_execution_intent is True for record in recent)
    assert all(record.no_execution_permission is True for record in recent)
    assert all(record.no_order_permission is True for record in recent)
    assert all(record.no_runtime_start is True for record in recent)


@pytest.mark.asyncio
async def test_scheduled_readonly_observation_is_idempotent_by_closed_bar(observation_repo):
    first = await run_scheduled_readonly_observation_once(
        source_name="local_sqlite_fallback",
        market_source=SampleStrategyGroupMarketBarSource(),
        repository=observation_repo,
    )
    second = await run_scheduled_readonly_observation_once(
        source_name="local_sqlite_fallback",
        market_source=SampleStrategyGroupMarketBarSource(),
        repository=observation_repo,
    )

    assert first.inserted_count == 3
    assert first.skipped_duplicate_count == 0
    assert first.failed_count == 0
    assert second.inserted_count == 0
    assert second.skipped_duplicate_count == 3
    assert second.failed_count == 0
    assert all(item.existing_record_id for item in second.candidate_results)

    recent = await observation_repo.list_recent(limit=10)
    assert len(recent) == 3
    assert all(record.not_order is True for record in recent)
    assert all(record.not_execution_intent is True for record in recent)
    assert all(record.no_order_permission is True for record in recent)


@pytest.mark.asyncio
async def test_forward_review_calculates_completed_and_pending_windows(forward_review_repo):
    observation = next(
        record
        for record in run_strategy_group_live_readonly_observation_once(
            market_source=SampleStrategyGroupMarketBarSource(),
            sink=InMemoryStrategyGroupObservationSink(),
        ).current_signals
        if record.candidate_id == "MI-001-BNB-LONG"
    ).model_copy(
        update={
            "record_id": "case-1",
            "signal_type": "would_enter",
            "side": "long",
            "market_bar_timestamp_ms": 1_000_000_000_000,
            "market_bar_close": "100",
        }
    )

    class ForwardSource:
        source_id = "unit_test_public_closed_bars"

        def latest_closed_candles(self, *, symbol: str, timeframe: str, limit: int):
            assert symbol == "BNB/USDT:USDT"
            assert timeframe == "1h"
            return [
                _candle(1_000_000_000_000, "99", "101", "98", "100"),
                _candle(1_000_003_600_000, "100", "103", "97", "102"),
            ]

    reviews = calculate_forward_reviews_for_observation(
        observation,
        market_source=ForwardSource(),
        windows=["1h", "4h"],
        now_ms=1_000_007_200_000,
    )
    recorded = await forward_review_repo.record_many(reviews)
    loaded = await forward_review_repo.list_by_observation_id("case-1")

    assert [review.review_window for review in loaded] == ["1h", "4h"]
    one_hour = loaded[0]
    assert one_hour.review_status == "completed"
    assert one_hour.forward_return_pct == "2.00000000"
    assert one_hour.mfe_pct == "3.00000000"
    assert one_hour.mae_pct == "-3.00000000"
    assert loaded[1].review_status == "pending"
    assert all(review.not_order is True for review in recorded)
    assert all(review.not_execution_intent is True for review in recorded)
    assert all(review.no_order_permission is True for review in recorded)


def test_observation_case_queue_includes_bnb_would_enter_and_excludes_cpm_no_action():
    payload = run_strategy_group_live_readonly_observation_once(
        market_source=SampleStrategyGroupMarketBarSource(),
        sink=InMemoryStrategyGroupObservationSink(),
    )
    bnb = next(record for record in payload.current_signals if record.candidate_id == "MI-001-BNB-LONG").model_copy(
        update={
            "record_id": "MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000",
            "signal_type": "would_enter",
            "side": "long",
            "market_bar_timestamp_ms": 1_780_196_400_000,
            "market_bar_close": "672.90",
            "review_windows": ["1h", "4h", "12h", "24h", "72h"],
        }
    )
    cpm_no_action = next(
        record for record in payload.current_signals if record.candidate_id == "CPM-RO-001"
    ).model_copy(update={"signal_type": "no_action"})
    reviews = [
        _review(bnb, "1h", "completed", 1_780_203_600_000, "-0.7593", "0.3121", "-1.1483"),
        _review(bnb, "4h", "completed", 1_780_214_400_000, "-0.9821", "0.3121", "-1.5512"),
        _review(bnb, "12h", "pending", 1_780_243_200_000),
        _review(bnb, "24h", "pending", 1_780_286_400_000),
        _review(bnb, "72h", "pending", 1_780_459_200_000),
    ]

    queue = build_observation_case_queue([cpm_no_action, bnb], reviews)

    assert queue.case_count == 1
    case = queue.cases[0]
    assert case.case_id == "MI-001-BNB-LONG-live-case-001"
    assert case.observation_id == bnb.record_id
    assert case.case_status == "pending_forward_review"
    assert case.completed_review_windows == ["1h", "4h"]
    assert case.pending_review_windows == ["12h", "24h", "72h"]
    assert "local_exhaustion_watch" in case.risk_tags
    assert "no_chase_required" in case.risk_tags
    assert "wait_for_confirmation_required" in case.risk_tags
    assert "CPM-RO-001" in queue.supported_future_cases
    assert queue.non_permissions["no_order_permission"] is True
    assert case.not_order is True
    assert case.not_execution_intent is True


def test_observation_case_queue_supports_future_cpm_would_enter_with_special_risk_tags():
    cpm = next(
        record
        for record in run_strategy_group_live_readonly_observation_once(
            market_source=SampleStrategyGroupMarketBarSource(),
            sink=InMemoryStrategyGroupObservationSink(),
        ).current_signals
        if record.candidate_id == "CPM-RO-001"
    ).model_copy(
        update={
            "record_id": "CPM-RO-001:future-would-enter:1780196400000",
            "signal_type": "would_enter",
            "side": "long",
            "human_summary": "CPM owner-special observation would-enter preview.",
        }
    )

    queue = build_observation_case_queue([cpm], [])

    assert queue.case_count == 1
    case = queue.cases[0]
    assert case.candidate_id == "CPM-RO-001"
    assert "owner_special_observation" in case.risk_tags
    assert "historical_oos_negative_warning" in case.risk_tags
    assert "not_proven_alpha" in case.risk_tags
    assert "not_runtime_eligible_by_default" in case.risk_tags
    assert case.no_execution_permission is True
    assert case.no_order_permission is True


def test_strategy_group_observation_migration_creates_observe_only_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-31-028_create_strategy_group_observations.py"
    )
    spec = importlib.util.spec_from_file_location("strategy_group_observation_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            operations = Operations(context)
            original_op = module.op
            module.op = operations
            try:
                module.upgrade()
            finally:
                module.op = original_op

        inspector = inspect(engine)
        assert "brc_strategy_group_observations" in inspector.get_table_names()
        columns = {column["name"] for column in inspector.get_columns("brc_strategy_group_observations")}
        assert {
            "observation_id",
            "candidate_id",
            "signal_type",
            "evidence_payload",
            "review_windows",
            "not_order",
            "not_execution_intent",
            "no_execution_permission",
            "no_order_permission",
            "no_runtime_start",
        } <= columns
    finally:
        engine.dispose()


def test_strategy_group_forward_review_migration_creates_observe_only_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-31-029_create_strategy_group_forward_reviews.py"
    )
    spec = importlib.util.spec_from_file_location("strategy_group_forward_review_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            operations = Operations(context)
            original_op = module.op
            module.op = operations
            try:
                module.upgrade()
            finally:
                module.op = original_op

        inspector = inspect(engine)
        assert "brc_strategy_group_forward_reviews" in inspector.get_table_names()
        columns = {column["name"] for column in inspector.get_columns("brc_strategy_group_forward_reviews")}
        assert {
            "review_id",
            "observation_id",
            "review_window",
            "review_due_at_ms",
            "review_status",
            "forward_return_pct",
            "mfe_pct",
            "mae_pct",
            "not_order",
            "not_execution_intent",
            "no_execution_permission",
            "no_order_permission",
            "no_runtime_start",
        } <= columns
    finally:
        engine.dispose()


def test_mi001_readonly_evaluator_returns_would_enter_for_impulse_preview():
    market_snapshot = _market_snapshot(
        symbol="SOL/USDT:USDT",
        candles=_sample_mi_candles(),
        timestamp_ms=1770000000000,
    )
    signal_input = _sample_signal_input(
        family_id="MI-001",
        version_id="MI-001-smoke-v0",
        playbook_id="MI-001-SOL-LONG-BT-001",
        symbol="SOL/USDT:USDT",
        side=SignalSide.LONG,
        market_snapshot=market_snapshot,
    )

    output = MI001MomentumImpulseReadOnlyEvaluator().evaluate(signal_input)

    assert output.signal_type == SignalType.WOULD_ENTER
    assert output.side == SignalSide.LONG
    assert output.required_execution_mode == "observe_only"
    assert output.not_order is True
    assert output.not_execution_intent is True
    assert "impulse_return_pct" in output.evidence_payload


def test_mi001_readonly_evaluator_returns_invalid_for_missing_context():
    market_snapshot = _market_snapshot(
        symbol="SOL/USDT:USDT",
        candles=_sample_mi_candles()[:2],
        timestamp_ms=1770000000000,
    )
    signal_input = _sample_signal_input(
        family_id="MI-001",
        version_id="MI-001-smoke-v0",
        playbook_id="MI-001-SOL-LONG-BT-001",
        symbol="SOL/USDT:USDT",
        side=SignalSide.LONG,
        market_snapshot=market_snapshot,
    )

    output = MI001MomentumImpulseReadOnlyEvaluator().evaluate(signal_input)

    assert output.signal_type == SignalType.INVALID
    assert "mi001_invalid_insufficient_candles" in output.reason_codes
    assert output.not_order is True
    assert output.not_execution_intent is True


def _candle(open_time_ms: int, open_: str, high: str, low: str, close: str):
    from decimal import Decimal

    from src.application.strategy_group_live_readonly_observation import RecentCandle

    return RecentCandle(
        open_time_ms=open_time_ms,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("1"),
        close_time_ms=open_time_ms + 3_600_000 - 1,
        is_closed=True,
    )


def _review(
    observation,
    window: str,
    status: str,
    due_at_ms: int,
    forward_return_pct: str | None = None,
    mfe_pct: str | None = None,
    mae_pct: str | None = None,
) -> StrategyGroupForwardReviewRecord:
    return StrategyGroupForwardReviewRecord(
        review_id=f"{observation.record_id}:{window}",
        observation_id=observation.record_id,
        candidate_id=observation.candidate_id,
        symbol=observation.symbol,
        side=observation.side,
        signal_type=observation.signal_type,
        market_bar_timestamp_ms=observation.market_bar_timestamp_ms,
        review_window=window,
        review_due_at_ms=due_at_ms,
        review_status=status,
        forward_return_pct=forward_return_pct,
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
        source="unit_test_forward_reviews",
        calculated_at_ms=due_at_ms if status == "completed" else None,
        notes=f"{status} unit test review",
    )
