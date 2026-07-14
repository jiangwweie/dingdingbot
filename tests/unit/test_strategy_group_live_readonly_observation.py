from __future__ import annotations

import importlib.util
import sqlite3
from decimal import InvalidOperation
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.runtime_strategy_signal_scheduler_assembly import (
    RuntimeStrategySignalSchedulerReadiness,
    RuntimeStrategySignalSchedulerReadinessStatus,
)
from src.application.runtime_strategy_signal_scheduler_planning_service import (
    RuntimeStrategySignalSchedulerPlanningResult,
    RuntimeStrategySignalSchedulerPlanningStatus,
)
from src.application.strategy_group_live_readonly_observation import (
    InMemoryStrategyGroupObservationSink,
    LOCAL_SQLITE_READ_ONLY_SOURCE_TYPE,
    MI001MomentumImpulseReadOnlyEvaluator,
    RecentCandle,
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
from src.domain.strategy_family_signal import (
    SignalSide,
    SignalType,
    StrategyFamilySignalInput,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.infrastructure.binance_public_kline_market_source import BinancePublicKlineMarketSource
from src.infrastructure.local_sqlite_observation_market_source import (
    LocalSqliteObservationMarketSource,
)
from src.infrastructure.pg_models import PGBrcStrategyGroupForwardReviewORM, PGBrcStrategyGroupObservationORM
from src.infrastructure.pg_strategy_group_forward_review_repository import PgStrategyGroupForwardReviewRepository
from src.infrastructure.pg_strategy_group_observation_repository import PgStrategyGroupObservationRepository
from src.application.strategy_group_observation_case_queue import build_observation_case_queue
from src.application.strategy_group_readonly_observation_scheduler import (
    StrategyRuntimeObservationResolutionError,
    StrategyRuntimeObservationResolver,
    run_scheduled_readonly_observation_once,
)


class _CaptureRunSyncConnection:
    def __init__(self) -> None:
        self.calls = []

    async def run_sync(self, fn, *args, **kwargs):
        self.calls.append((getattr(fn, "__self__", None), kwargs))


class _CaptureEngine:
    def __init__(self) -> None:
        self.connection = _CaptureRunSyncConnection()

    def begin(self):
        connection = self.connection

        class _Context:
            async def __aenter__(self):
                return connection

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return _Context()


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


@pytest.mark.asyncio
async def test_observation_repository_initialize_only_creates_observation_table(monkeypatch):
    import src.infrastructure.pg_strategy_group_observation_repository as repository_module

    engine = _CaptureEngine()
    monkeypatch.setattr(repository_module, "get_pg_engine", lambda: engine)
    monkeypatch.setattr(repository_module, "get_pg_session_maker", lambda: object())

    await PgStrategyGroupObservationRepository().initialize()

    assert engine.connection.calls == [
        (PGBrcStrategyGroupObservationORM.__table__, {"checkfirst": True})
    ]


@pytest.mark.asyncio
async def test_forward_review_repository_initialize_only_creates_forward_review_table(monkeypatch):
    import src.infrastructure.pg_strategy_group_forward_review_repository as repository_module

    engine = _CaptureEngine()
    monkeypatch.setattr(repository_module, "get_pg_engine", lambda: engine)
    monkeypatch.setattr(repository_module, "get_pg_session_maker", lambda: object())

    await PgStrategyGroupForwardReviewRepository().initialize()

    assert engine.connection.calls == [
        (PGBrcStrategyGroupForwardReviewORM.__table__, {"checkfirst": True})
    ]


def test_live_readonly_observation_v1_exposes_mi_cpm_and_brf_without_execution_fields():
    payload = build_strategy_group_live_readonly_observation_v1()

    candidate_ids = {item.candidate_id for item in payload.candidates}
    assert {
        "MI-001-SOL-LONG",
        "MI-001-BNB-LONG",
        "CPM-RO-001",
        "BRF-001-BTC-SHORT",
    } <= candidate_ids
    assert payload.runner_mapping["strategy_specific_signal_evaluator_glue_wired"] is True
    assert payload.live_observation_active is False
    assert payload.live_ready is False
    assert len(payload.current_signals) == 8
    brf = next(
        record
        for record in payload.current_signals
        if record.candidate_id == "BRF-001-BTC-SHORT"
    )
    assert brf.side == "short"
    assert brf.signal_type == "would_enter"
    assert brf.not_order is True
    assert brf.not_execution_intent is True
    assert payload.sink_summary["pg_observation_sink"] == "blocked_schema_gap_no_live_observation_table_found"
    assert payload.input_source_summary["external_exchange_write"] is False
    assert payload.review_hook_summary["review_hook_status"] == "records_include_pending_forward_outcome_windows"
    assert payload.runtime_signal_planning_summary["scheduler_level_readiness"] is True
    assert payload.runtime_signal_planning_summary["planner_call_performed"] is False
    assert payload.runtime_signal_planning_summary["order_candidate_created"] is False
    assert payload.runtime_signal_planning_summary["execution_intent_created"] is False
    assert payload.runtime_signal_planning_summary["exchange_called"] is False
    assert payload.runtime_signal_planning_summary["not_execution_authority"] is True
    assert "runtime_instance_required_for_scheduler_planning" in (
        payload.runtime_signal_planning_summary["blockers"]
    )
    assert payload.non_permissions["no_execution_intent"] is True
    assert payload.non_permissions["no_order_permission"] is True
    assert all(
        candidate.runtime_signal_planning_readiness
        for candidate in payload.candidates
    )

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

    assert len(payload.current_signals) == 8
    assert len(payload.signal_history) == 8
    assert payload.sink_summary["sink_status"] == "process_local_sink_recording_enabled"
    assert payload.sink_summary["writes_execution_or_order_tables"] is False
    assert all(record.not_order is True for record in payload.signal_history)
    assert all(record.not_execution_intent is True for record in payload.signal_history)
    assert all(record.no_runtime_start is True for record in payload.signal_history)
    assert all(record.runtime_signal_planning_readiness for record in payload.signal_history)
    assert all(
        record.runtime_signal_planning_readiness["planner_call_performed"] is False
        for record in payload.signal_history
    )


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


def test_binance_public_kline_source_supports_sor_15m_closed_bars():
    now_ms = 1_800_000_000_000
    interval_ms = 15 * 60 * 1000
    requested_urls: list[str] = []

    def transport(url: str, timeout: float) -> list:
        requested_urls.append(url)
        assert timeout == 10.0
        return [
            [
                now_ms - 2 * interval_ms,
                "100",
                "102",
                "99",
                "101",
                "1234",
                now_ms - interval_ms - 1,
            ],
            [
                now_ms - interval_ms,
                "101",
                "103",
                "100",
                "102",
                "1234",
                now_ms - 1,
            ],
            [
                now_ms,
                "102",
                "104",
                "101",
                "103",
                "1234",
                now_ms + interval_ms - 1,
            ],
        ]

    source = BinancePublicKlineMarketSource(now_ms=lambda: now_ms, transport=transport)

    candles = source.latest_closed_candles(
        symbol="ETH/USDT:USDT",
        timeframe="15m",
        limit=2,
    )

    assert "symbol=ETHUSDT" in requested_urls[0]
    assert "interval=15m" in requested_urls[0]
    assert [candle.close_time_ms for candle in candles] == [
        now_ms - interval_ms - 1,
        now_ms - 1,
    ]


def test_live_market_source_records_observe_only_history_with_live_source_metadata():
    now_ms = 1_800_000_000_000

    def transport(url: str, _timeout: float) -> list:
        interval_ms = 4 * 60 * 60 * 1000 if "interval=4h" in url else 60 * 60 * 1000
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

    source = BinancePublicKlineMarketSource(now_ms=lambda: now_ms, transport=transport)
    payload = run_strategy_group_live_readonly_observation_once(
        market_source=source,
        sink=InMemoryStrategyGroupObservationSink(),
    )
    latest_1h_open_time_ms = now_ms - 60 * 60 * 1000
    latest_1h_close_time_ms = now_ms - 1

    assert len(payload.current_signals) == 8
    assert payload.input_source_summary["source_type"] == "live_market_read_only"
    assert payload.input_source_summary["is_live_read_only"] is True
    assert payload.input_source_summary["fallback_used"] is False
    assert all(record.source_type == "live_market_read_only" for record in payload.signal_history)
    assert all(record.market_source == "binance_usdm_public_klines_read_only" for record in payload.signal_history)
    assert all(record.market_bar_timestamp_ms == latest_1h_close_time_ms for record in payload.signal_history)
    assert all(record.market_bar_timestamp_ms != latest_1h_open_time_ms for record in payload.signal_history)
    assert all(
        record.signal_input_snapshot["trigger_candle_close_time_ms"] == latest_1h_close_time_ms
        for record in payload.signal_history
    )
    assert all(record.not_order is True for record in payload.signal_history)
    assert all(record.not_execution_intent is True for record in payload.signal_history)


def test_local_sqlite_source_type_is_read_only_not_fallback():
    source = LocalSqliteObservationMarketSource()

    assert source.source_type == LOCAL_SQLITE_READ_ONLY_SOURCE_TYPE


def test_local_sqlite_missing_db_uses_sample_fallback_as_read_only_evidence(tmp_path):
    source = LocalSqliteObservationMarketSource(tmp_path / "missing.db")

    candles = source.latest_closed_candles(
        symbol="SOL/USDT:USDT",
        timeframe="1h",
        limit=3,
    )

    assert len(candles) == 3
    assert source.fallback_used is True


def test_local_sqlite_bad_numeric_data_does_not_use_sample_fallback(tmp_path):
    db_path = tmp_path / "bad-klines.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE klines (
                timestamp INTEGER,
                open TEXT,
                high TEXT,
                low TEXT,
                close TEXT,
                volume TEXT,
                symbol TEXT,
                timeframe TEXT,
                is_closed INTEGER
            )
            """
        )
        for index in range(3):
            conn.execute(
                """
                INSERT INTO klines (
                    timestamp, open, high, low, close, volume, symbol, timeframe, is_closed
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    index,
                    "not-a-decimal" if index == 0 else "100",
                    "101",
                    "99",
                    "100",
                    "10",
                    "SOL/USDT:USDT",
                    "1h",
                ),
            )

    source = LocalSqliteObservationMarketSource(db_path)

    with pytest.raises(InvalidOperation):
        source.latest_closed_candles(
            symbol="SOL/USDT:USDT",
            timeframe="1h",
            limit=3,
        )

    assert source.fallback_used is False


def test_sqlite_source_without_explicit_type_infers_read_only_not_fallback():
    class _SqliteReadOnlySource:
        source_id = "unit_sqlite_closed_klines_read_only"

        def latest_closed_candles(
            self,
            *,
            symbol: str,
            timeframe: str,
            limit: int,
        ) -> list[RecentCandle]:
            return SampleStrategyGroupMarketBarSource().latest_closed_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )

    payload = build_strategy_group_live_readonly_observation_v1(
        market_source=_SqliteReadOnlySource()
    )

    assert payload.input_source_summary["source_type"] == LOCAL_SQLITE_READ_ONLY_SOURCE_TYPE
    assert payload.input_source_summary["fallback_used"] is False
    assert all(
        record.source_type == LOCAL_SQLITE_READ_ONLY_SOURCE_TYPE
        for record in payload.current_signals
    )


def test_readonly_observation_market_source_error_becomes_blocked_candidate():
    class _FailingMarketSource:
        source_id = "unit_failing_market_source"
        source_type = LOCAL_SQLITE_READ_ONLY_SOURCE_TYPE

        def latest_closed_candles(
            self,
            *,
            symbol: str,
            timeframe: str,
            limit: int,
        ) -> list[RecentCandle]:
            raise RuntimeError(f"closed candles unavailable for {symbol} {timeframe}")

    payload = build_strategy_group_live_readonly_observation_v1(
        market_source=_FailingMarketSource()
    )

    assert payload.current_signals == []
    assert payload.sink_summary["sink_status"] == "source_blocked_no_recording"
    assert payload.input_source_summary["source_blockers"] == [
        "market_source_evaluation_failed"
    ]
    assert all(
        candidate.readiness_status == "blocked_market_source_or_context_unavailable"
        for candidate in payload.candidates
    )
    assert all(
        candidate.latest_signal_preview["reason_codes"]
        == ["observation_source_unavailable"]
        for candidate in payload.candidates
    )


def test_readonly_observation_evaluator_error_is_not_source_fallback(monkeypatch):
    def _raise_evaluator_bug(self, signal_input):
        raise RuntimeError("unit evaluator bug")

    monkeypatch.setattr(
        MI001MomentumImpulseReadOnlyEvaluator,
        "evaluate",
        _raise_evaluator_bug,
    )

    with pytest.raises(RuntimeError, match="unit evaluator bug"):
        build_strategy_group_live_readonly_observation_v1(
            market_source=SampleStrategyGroupMarketBarSource()
        )


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
        candidate_ids=[
            "MI-001-SOL-LONG",
            "MI-001-BNB-LONG",
            "CPM-RO-001",
            "BRF-001-BTC-SHORT",
        ],
    )

    assert len(recent) == 8
    assert [record.candidate_id for record in current] == [
        "MI-001-SOL-LONG",
        "MI-001-BNB-LONG",
        "CPM-RO-001",
        "BRF-001-BTC-SHORT",
    ]
    assert all(record.sink_status == "recorded_pg" for record in recent)
    assert all(record.not_order is True for record in recent)
    assert all(record.not_execution_intent is True for record in recent)
    assert all(record.no_execution_permission is True for record in recent)
    assert all(record.no_order_permission is True for record in recent)
    assert all(record.no_runtime_start is True for record in recent)
    assert all(record.signal_input_snapshot for record in recent)
    assert all(
        record.signal_input_snapshot["strategy_family_id"] == record.strategy_group_id
        for record in recent
    )


@pytest.mark.asyncio
async def test_scheduled_readonly_observation_is_idempotent_by_closed_bar(observation_repo):
    first = await run_scheduled_readonly_observation_once(
        source_name="local_sqlite_read_only",
        market_source=SampleStrategyGroupMarketBarSource(),
        repository=observation_repo,
    )
    second = await run_scheduled_readonly_observation_once(
        source_name="local_sqlite_read_only",
        market_source=SampleStrategyGroupMarketBarSource(),
        repository=observation_repo,
    )

    assert first.inserted_count == 8
    assert first.skipped_duplicate_count == 0
    assert first.failed_count == 0
    assert second.inserted_count == 0
    assert second.skipped_duplicate_count == 8
    assert second.failed_count == 0
    assert all(item.existing_record_id for item in second.candidate_results)
    assert all(item.runtime_signal_planning_readiness for item in first.candidate_results)
    assert all(
        item.runtime_signal_planning_readiness["order_candidate_created"] is False
        for item in first.candidate_results
    )

    recent = await observation_repo.list_recent(limit=10)
    assert len(recent) == 8
    assert all(record.not_order is True for record in recent)
    assert all(record.not_execution_intent is True for record in recent)
    assert all(record.no_order_permission is True for record in recent)
    assert all(record.runtime_signal_planning_readiness for record in recent)
    assert all(record.signal_input_snapshot for record in recent)


@pytest.mark.asyncio
async def test_scheduled_observation_can_handoff_to_non_executing_shadow_planner(
    observation_repo,
):
    class _RuntimeResolver:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def resolve_runtime_for_signal(self, signal_input, observation):
            self.calls.append(observation.record_id)
            return _shadow_runtime_for_signal(signal_input)

    class _PlanningService:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def plan_signal_input_if_ready(self, signal_input, **kwargs):
            runtime = kwargs["runtime"]
            self.calls.append(
                {
                    "evaluation_id": signal_input.evaluation_id,
                    "runtime_instance_id": runtime.runtime_instance_id,
                    "candidate_id": kwargs["candidate_id"],
                    "allow_shadow_candidate_creation": (
                        kwargs["allow_shadow_candidate_creation"]
                    ),
                    "context_id": kwargs["context_id"],
                    "metadata": kwargs["metadata"],
                }
            )
            return RuntimeStrategySignalSchedulerPlanningResult(
                planning_id=f"scheduled-plan-{signal_input.evaluation_id}",
                runtime_instance_id=runtime.runtime_instance_id,
                strategy_family_id=signal_input.strategy_family_id,
                strategy_family_version_id=signal_input.strategy_family_version_id,
                symbol=signal_input.symbol,
                status=(
                    RuntimeStrategySignalSchedulerPlanningStatus.SHADOW_CANDIDATE_CREATED
                ),
                readiness=RuntimeStrategySignalSchedulerReadiness(
                    candidate_id=kwargs["candidate_id"],
                    evaluation_id=signal_input.evaluation_id,
                    signal_id=f"scheduled-signal-{signal_input.evaluation_id}",
                    strategy_family_id=signal_input.strategy_family_id,
                    strategy_family_version_id=signal_input.strategy_family_version_id,
                    symbol=signal_input.symbol,
                    side=runtime.side,
                    signal_type="would_enter",
                    status=(
                        RuntimeStrategySignalSchedulerReadinessStatus.READY_FOR_NON_EXECUTING_PLANNER
                    ),
                    runtime_instance_id=runtime.runtime_instance_id,
                    runtime_bound=True,
                    scheduler_can_call_runtime_planner=True,
                ),
                planner_call_performed=True,
                signal_evaluation_created=True,
                order_candidate_created=True,
            )

    resolver = _RuntimeResolver()
    planning_service = _PlanningService()

    result = await run_scheduled_readonly_observation_once(
        source_name="local_sqlite_read_only",
        market_source=SampleStrategyGroupMarketBarSource(),
        repository=observation_repo,
        runtime_resolver=resolver,
        runtime_signal_planning_service=planning_service,
        allow_shadow_candidate_creation=True,
    )

    assert result.inserted_count == 8
    assert len(planning_service.calls) == 8
    assert len(resolver.calls) == 8
    assert all(
        item.shadow_planning_action == "shadow_candidate_created"
        for item in result.candidate_results
    )
    assert all(item.planner_call_performed is True for item in result.candidate_results)
    assert all(item.signal_evaluation_created is True for item in result.candidate_results)
    assert all(item.order_candidate_created is True for item in result.candidate_results)
    assert all(item.execution_intent_created is False for item in result.candidate_results)
    assert all(item.order_created is False for item in result.candidate_results)
    assert all(item.order_lifecycle_called is False for item in result.candidate_results)
    assert all(item.exchange_called is False for item in result.candidate_results)
    assert all(item.not_order is True for item in result.candidate_results)
    assert all(item.not_execution_intent is True for item in result.candidate_results)
    assert planning_service.calls[0]["allow_shadow_candidate_creation"] is True
    assert planning_service.calls[0]["metadata"]["scheduled_readonly_observation"] is True


@pytest.mark.asyncio
async def test_scheduled_observation_resolves_active_shadow_runtime_before_handoff(
    observation_repo,
):
    preview = build_strategy_group_live_readonly_observation_v1(
        market_source=SampleStrategyGroupMarketBarSource()
    )
    matching_record = next(
        record
        for record in preview.current_signals
        if record.candidate_id == "CPM-RO-001"
    )
    signal_input = StrategyFamilySignalInput.model_validate(
        matching_record.signal_input_snapshot
    )
    matching_runtime = _shadow_runtime_for_signal(
        signal_input,
        side=matching_record.side,
    )

    class _RuntimeService:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def list_runtimes(self, *, status=None, limit=100):
            self.calls.append({"status": status, "limit": limit})
            return [matching_runtime]

    class _PlanningService:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def plan_signal_input_if_ready(self, signal_input, **kwargs):
            runtime = kwargs["runtime"]
            self.calls.append(signal_input.evaluation_id)
            return RuntimeStrategySignalSchedulerPlanningResult(
                planning_id=f"scheduled-plan-{signal_input.evaluation_id}",
                runtime_instance_id=runtime.runtime_instance_id,
                strategy_family_id=signal_input.strategy_family_id,
                strategy_family_version_id=signal_input.strategy_family_version_id,
                symbol=signal_input.symbol,
                status=(
                    RuntimeStrategySignalSchedulerPlanningStatus.SHADOW_CANDIDATE_CREATED
                ),
                readiness=RuntimeStrategySignalSchedulerReadiness(
                    candidate_id=kwargs["candidate_id"],
                    evaluation_id=signal_input.evaluation_id,
                    signal_id=f"scheduled-signal-{signal_input.evaluation_id}",
                    strategy_family_id=signal_input.strategy_family_id,
                    strategy_family_version_id=signal_input.strategy_family_version_id,
                    symbol=signal_input.symbol,
                    side=runtime.side,
                    signal_type="would_enter",
                    status=(
                        RuntimeStrategySignalSchedulerReadinessStatus.READY_FOR_NON_EXECUTING_PLANNER
                    ),
                    runtime_instance_id=runtime.runtime_instance_id,
                    runtime_bound=True,
                    scheduler_can_call_runtime_planner=True,
                ),
                planner_call_performed=True,
                signal_evaluation_created=True,
                order_candidate_created=True,
            )

    runtime_service = _RuntimeService()
    resolver = StrategyRuntimeObservationResolver(
        runtime_service=runtime_service,
        now_ms_source=lambda: signal_input.timestamp_ms,
    )
    planning_service = _PlanningService()

    result = await run_scheduled_readonly_observation_once(
        source_name="local_sqlite_read_only",
        market_source=SampleStrategyGroupMarketBarSource(),
        repository=observation_repo,
        runtime_resolver=resolver,
        runtime_signal_planning_service=planning_service,
        allow_shadow_candidate_creation=True,
    )

    assert runtime_service.calls
    assert all(
        call["status"] == StrategyRuntimeInstanceStatus.ACTIVE
        for call in runtime_service.calls
    )
    assert planning_service.calls == [signal_input.evaluation_id]
    created = [
        item
        for item in result.candidate_results
        if item.shadow_planning_action == "shadow_candidate_created"
    ]
    blocked = [
        item
        for item in result.candidate_results
        if item.shadow_planning_action == "runtime_not_resolved"
    ]
    assert len(created) == 1
    assert created[0].candidate_id == "CPM-RO-001"
    assert created[0].runtime_instance_id == matching_runtime.runtime_instance_id
    assert len(blocked) == 7
    assert all(item.planner_call_performed is False for item in blocked)
    assert all(item.execution_intent_created is False for item in result.candidate_results)
    assert all(item.order_created is False for item in result.candidate_results)
    assert all(item.exchange_called is False for item in result.candidate_results)


@pytest.mark.asyncio
async def test_observation_runtime_resolver_ignores_ineligible_runtime_states():
    record = next(
        record
        for record in build_strategy_group_live_readonly_observation_v1(
            market_source=SampleStrategyGroupMarketBarSource()
        ).current_signals
        if record.candidate_id == "CPM-RO-001"
    )
    signal_input = StrategyFamilySignalInput.model_validate(record.signal_input_snapshot)
    matching_runtime = _shadow_runtime_for_signal(signal_input, side=record.side)

    class _RuntimeService:
        def __init__(self, runtimes):
            self.runtimes = runtimes

        async def list_runtimes(self, *, status=None, limit=100):
            return self.runtimes

    paused_runtime = matching_runtime.model_copy(
        update={"status": StrategyRuntimeInstanceStatus.PAUSED}
    )
    expired_runtime = matching_runtime.model_copy(
        update={"runtime_instance_id": "runtime-expired", "expires_at_ms": 10}
    )
    wrong_side_runtime = matching_runtime.model_copy(
        update={"runtime_instance_id": "runtime-short", "side": "short"}
    )
    resolver = StrategyRuntimeObservationResolver(
        runtime_service=_RuntimeService(
            [paused_runtime, expired_runtime, wrong_side_runtime]
        ),
        now_ms_source=lambda: 11,
    )

    resolved = await resolver.resolve_runtime_for_signal(signal_input, record)

    assert resolved is None


@pytest.mark.asyncio
async def test_observation_runtime_resolver_fails_on_ambiguous_active_runtime():
    record = next(
        record
        for record in build_strategy_group_live_readonly_observation_v1(
            market_source=SampleStrategyGroupMarketBarSource()
        ).current_signals
        if record.candidate_id == "CPM-RO-001"
    )
    signal_input = StrategyFamilySignalInput.model_validate(record.signal_input_snapshot)
    matching_runtime = _shadow_runtime_for_signal(signal_input, side=record.side)
    duplicate_runtime = matching_runtime.model_copy(
        update={"runtime_instance_id": "runtime-duplicate"}
    )

    class _RuntimeService:
        async def list_runtimes(self, *, status=None, limit=100):
            return [matching_runtime, duplicate_runtime]

    resolver = StrategyRuntimeObservationResolver(
        runtime_service=_RuntimeService(),
        now_ms_source=lambda: signal_input.timestamp_ms,
    )

    with pytest.raises(
        StrategyRuntimeObservationResolutionError,
        match="multiple_matching_active_shadow_runtimes",
    ):
        await resolver.resolve_runtime_for_signal(signal_input, record)


@pytest.mark.asyncio
async def test_scheduled_observation_planner_requires_runtime_resolver(observation_repo):
    class _PlanningService:
        async def plan_signal_input_if_ready(self, signal_input, **kwargs):
            raise AssertionError("planner must not be called without runtime resolver")

    result = await run_scheduled_readonly_observation_once(
        source_name="local_sqlite_read_only",
        market_source=SampleStrategyGroupMarketBarSource(),
        repository=observation_repo,
        runtime_signal_planning_service=_PlanningService(),
        allow_shadow_candidate_creation=True,
    )

    assert result.inserted_count == 8
    assert all(
        item.shadow_planning_action == "runtime_resolver_missing"
        for item in result.candidate_results
    )
    assert all(item.planner_call_performed is False for item in result.candidate_results)
    assert all(item.order_candidate_created is False for item in result.candidate_results)
    assert all(item.execution_intent_created is False for item in result.candidate_results)


@pytest.mark.asyncio
async def test_scheduled_observation_surfaces_runtime_resolver_error(observation_repo):
    class _RuntimeResolver:
        async def resolve_runtime_for_signal(self, signal_input, observation):
            raise RuntimeError("resolver_modeling_defect")

    class _PlanningService:
        async def plan_signal_input_if_ready(self, signal_input, **kwargs):
            raise AssertionError("planner must not be called after resolver error")

    with pytest.raises(RuntimeError, match="resolver_modeling_defect"):
        await run_scheduled_readonly_observation_once(
            source_name="local_sqlite_read_only",
            market_source=SampleStrategyGroupMarketBarSource(),
            repository=observation_repo,
            runtime_resolver=_RuntimeResolver(),
            runtime_signal_planning_service=_PlanningService(),
            allow_shadow_candidate_creation=True,
        )


@pytest.mark.asyncio
async def test_scheduled_observation_surfaces_shadow_planner_error(observation_repo):
    class _RuntimeResolver:
        async def resolve_runtime_for_signal(self, signal_input, observation):
            return _shadow_runtime_for_signal(signal_input)

    class _PlanningService:
        async def plan_signal_input_if_ready(self, signal_input, **kwargs):
            raise RuntimeError("shadow_planner_modeling_defect")

    with pytest.raises(RuntimeError, match="shadow_planner_modeling_defect"):
        await run_scheduled_readonly_observation_once(
            source_name="local_sqlite_read_only",
            market_source=SampleStrategyGroupMarketBarSource(),
            repository=observation_repo,
            runtime_resolver=_RuntimeResolver(),
            runtime_signal_planning_service=_PlanningService(),
            allow_shadow_candidate_creation=True,
        )


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


def _shadow_runtime_for_signal(signal_input, *, side: str | None = None):
    selected_side = side or signal_input.trial_constraints_snapshot.get("side", "long")
    return StrategyRuntimeInstance(
        runtime_instance_id=f"runtime-{signal_input.strategy_family_id}-{signal_input.symbol}",
        trial_binding_id=f"trial-{signal_input.strategy_family_id}",
        admission_decision_id=f"admission-{signal_input.strategy_family_id}",
        strategy_family_id=signal_input.strategy_family_id,
        strategy_family_version_id=signal_input.strategy_family_version_id,
        symbol=signal_input.symbol,
        side=selected_side,
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("9"),
            allowed_symbols=[signal_input.symbol],
            allowed_sides=[selected_side],
            max_leverage=Decimal("1"),
            max_margin_per_attempt=Decimal("10"),
            min_liquidation_stop_buffer=Decimal("25"),
            requires_protection=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=signal_input.timestamp_ms,
        updated_at_ms=signal_input.timestamp_ms,
    )


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
