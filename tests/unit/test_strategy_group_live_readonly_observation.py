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
from src.domain.strategy_family_signal import SignalSide, SignalType
from src.infrastructure.pg_models import PGBrcStrategyGroupObservationORM
from src.infrastructure.pg_strategy_group_observation_repository import PgStrategyGroupObservationRepository


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
