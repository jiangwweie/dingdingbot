from __future__ import annotations

import asyncio
import importlib.util
import inspect as py_inspect
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.owner_trial_flow import BoundedLiveTrialAuthorization
from src.application.signal_evaluation_shadow_service import SignalEvaluationShadowService
from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateProtectionPreview,
    OrderCandidateRiskPreview,
    OrderCandidateStatus,
    SignalEvaluation,
    SignalEvaluationDecision,
    SignalEvaluationStatus,
)
from src.domain.strategy_family_signal import (
    SignalSide,
    SignalType,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.infrastructure.pg_models import PGOrderCandidateORM, PGSignalEvaluationORM
from src.infrastructure.pg_signal_evaluation_repository import PgSignalEvaluationRepository
from src.interfaces import api as api_module
from src.interfaces.api_trading_console import (
    get_order_candidate,
    get_signal_evaluation,
    list_order_candidates,
    list_signal_evaluations,
)


NOW_MS = 1780496665000
AUDIT_VALUES = {
    "runtime_instance_id": "runtime-1",
    "trial_binding_id": "binding-1",
    "strategy_family_id": "family-1",
    "strategy_family_version_id": "version-1",
}


def _evaluation(**overrides) -> SignalEvaluation:
    values = {
        "signal_evaluation_id": "signal-eval-1",
        **AUDIT_VALUES,
        "source_signal_id": "signal-1",
        "symbol": "ETH/USDT:USDT",
        "side": "long",
        "status": SignalEvaluationStatus.EVALUATED,
        "decision": SignalEvaluationDecision.CANDIDATE,
        "reason_codes": ["unit_test"],
        "rationale": "shadow evaluation",
        "evaluated_at_ms": NOW_MS,
        "created_at_ms": NOW_MS,
        "updated_at_ms": NOW_MS,
    }
    values.update(overrides)
    return SignalEvaluation(**values)


def _candidate(**overrides) -> OrderCandidate:
    values = {
        "order_candidate_id": "order-candidate-1",
        "signal_evaluation_id": "signal-eval-1",
        **AUDIT_VALUES,
        "symbol": "ETH/USDT:USDT",
        "side": "long",
        "candidate_order_type": "market",
        "proposed_quantity": Decimal("0.01"),
        "intended_notional": Decimal("25"),
        "entry_price_reference": Decimal("2500"),
        "risk_preview": OrderCandidateRiskPreview(
            intended_notional=Decimal("25"),
            proposed_quantity=Decimal("0.01"),
        ),
        "protection_preview": OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="shadow_stop_reference",
        ),
        "rationale": "candidate for owner review",
        "created_at_ms": NOW_MS,
        "updated_at_ms": NOW_MS,
    }
    values.update(overrides)
    return OrderCandidate(**values)


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-1",
        trial_binding_id="binding-1",
        admission_decision_id="admission-1",
        strategy_family_id="family-1",
        strategy_family_version_id="version-1",
        symbol="ETH/USDT:USDT",
        side="long",
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=2,
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=["long"],
        ),
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _strategy_family_signal_output() -> StrategyFamilySignalOutput:
    return StrategyFamilySignalOutput(
        signal_id="signal-1",
        evaluation_id="source-eval-1",
        strategy_family_id="family-1",
        strategy_family_version_id="version-1",
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        timeframe="1h",
        signal_type=SignalType.WOULD_ENTER,
        side=SignalSide.LONG,
        confidence=Decimal("0.7"),
        reason_codes=["pattern_confirmed"],
        human_summary="tracked-code signal output adapter input",
    )


async def _repo_engine(*tables):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(table.create)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_domain_models_are_shadow_only_and_reject_execution_fields():
    evaluation = _evaluation()
    candidate = _candidate()

    assert evaluation.execution_enabled is False
    assert evaluation.shadow_mode is True
    assert evaluation.not_order is True
    assert evaluation.not_execution_intent is True
    assert candidate.execution_enabled is False
    assert candidate.candidate_executable is False
    assert candidate.not_order is True
    assert candidate.not_execution_intent is True

    with pytest.raises(ValueError, match="forbidden execution/order field"):
        _evaluation(evidence_snapshot={"order_id": "not-allowed"})

    with pytest.raises(ValueError, match="forbidden execution/order field"):
        _candidate(metadata={"exchange_payload": {"symbol": "ETH/USDT:USDT"}})

    with pytest.raises(ValueError, match="no_action signal evaluation"):
        _evaluation(side="long", decision=SignalEvaluationDecision.NO_ACTION)


def test_migration_creates_shadow_tables_and_downgrades_cleanly():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-047_create_signal_evaluations_order_candidates.py"
    )
    spec = importlib.util.spec_from_file_location("td3_signal_evaluation_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run() -> tuple[set[str], set[str]]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                old_op = migration.op
                migration.op = Operations(MigrationContext.configure(sync_conn))
                try:
                    migration.upgrade()
                    inspector = inspect(sync_conn)
                    assert inspector.has_table("signal_evaluations")
                    assert inspector.has_table("order_candidates")
                    signal_columns = {
                        column["name"] for column in inspector.get_columns("signal_evaluations")
                    }
                    candidate_columns = {
                        column["name"] for column in inspector.get_columns("order_candidates")
                    }
                    migration.downgrade()
                    inspector = inspect(sync_conn)
                    assert not inspector.has_table("order_candidates")
                    assert not inspector.has_table("signal_evaluations")
                    return signal_columns, candidate_columns
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    signal_columns, candidate_columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "signal_evaluation_id" in signal_columns
    assert "execution_enabled" in signal_columns
    assert "order_candidate_id" in candidate_columns
    assert "candidate_executable" in candidate_columns
    assert "exchange_order_id" not in candidate_columns
    assert "client_order_id" not in candidate_columns


async def test_repository_roundtrips_null_and_present_audit_ids():
    engine, session_maker = await _repo_engine(
        PGSignalEvaluationORM.__table__,
        PGOrderCandidateORM.__table__,
    )
    repo = PgSignalEvaluationRepository(session_maker=session_maker)
    try:
        await repo.create_signal_evaluation(_evaluation(signal_evaluation_id="eval-legacy", **{
            key: None for key in AUDIT_VALUES
        }))
        traced_eval = await repo.create_signal_evaluation(_evaluation(signal_evaluation_id="eval-traced"))
        traced_candidate = await repo.create_order_candidate(
            _candidate(
                order_candidate_id="candidate-traced",
                signal_evaluation_id=traced_eval.signal_evaluation_id,
            )
        )

        legacy = await repo.get_signal_evaluation("eval-legacy")
        evaluations = await repo.list_signal_evaluations(runtime_instance_id="runtime-1")
        candidates = await repo.list_order_candidates(signal_evaluation_id="eval-traced")
        updated_candidate = await repo.update_order_candidate_status(
            traced_candidate.model_copy(update={"status": OrderCandidateStatus.UNDER_REVIEW})
        )

        assert legacy is not None and legacy.runtime_instance_id is None
        assert evaluations[0].signal_evaluation_id == "eval-traced"
        assert candidates[0].order_candidate_id == "candidate-traced"
        assert updated_candidate.status == OrderCandidateStatus.UNDER_REVIEW
    finally:
        await engine.dispose()


async def test_service_creates_shadow_records_and_propagates_audit_ids():
    engine, session_maker = await _repo_engine(
        PGSignalEvaluationORM.__table__,
        PGOrderCandidateORM.__table__,
    )
    service = SignalEvaluationShadowService(
        repository=PgSignalEvaluationRepository(session_maker=session_maker)
    )
    try:
        evaluation = await service.create_signal_evaluation_from_strategy_family_output(
            _strategy_family_signal_output(),
            runtime=_runtime(),
        )
        candidate = await service.create_order_candidate_from_signal_evaluation(
            evaluation.signal_evaluation_id,
            proposed_quantity=Decimal("0.01"),
            intended_notional=Decimal("25"),
            entry_price_reference=Decimal("2500"),
        )

        assert evaluation.runtime_instance_id == "runtime-1"
        assert evaluation.strategy_family_version_id == "version-1"
        assert evaluation.metadata["adapter"] == "StrategyFamilySignalOutput"
        assert candidate.signal_evaluation_id == evaluation.signal_evaluation_id
        assert candidate.runtime_instance_id == "runtime-1"
        assert candidate.candidate_executable is False
        assert candidate.not_order is True
    finally:
        await engine.dispose()


async def test_trading_console_inspection_endpoints_are_get_only_shadow_views(monkeypatch):
    evaluation = _evaluation()
    candidate = _candidate()

    class _FakeService:
        async def list_signal_evaluations(self, **kwargs):
            assert kwargs["runtime_instance_id"] == "runtime-1"
            return [evaluation]

        async def get_signal_evaluation(self, signal_evaluation_id):
            assert signal_evaluation_id == evaluation.signal_evaluation_id
            return evaluation

        async def list_order_candidates(self, **kwargs):
            assert kwargs["signal_evaluation_id"] == evaluation.signal_evaluation_id
            return [candidate]

        async def get_order_candidate(self, order_candidate_id):
            assert order_candidate_id == candidate.order_candidate_id
            return candidate

    monkeypatch.setattr(api_module, "_signal_evaluation_shadow_service", _FakeService(), raising=False)

    listed_evaluations = await list_signal_evaluations(runtime_instance_id="runtime-1")
    detail_evaluation = await get_signal_evaluation(evaluation.signal_evaluation_id)
    listed_candidates = await list_order_candidates(
        signal_evaluation_id=evaluation.signal_evaluation_id
    )
    detail_candidate = await get_order_candidate(candidate.order_candidate_id)

    assert listed_evaluations[0].shadow_mode is True
    assert detail_evaluation.execution_enabled is False
    assert listed_candidates[0].candidate_executable is False
    assert listed_candidates[0].not_order is True
    assert listed_candidates[0].not_execution_intent is True
    assert detail_candidate.execution_enabled is False


def test_td3_new_code_has_no_forbidden_runtime_dependencies():
    forbidden = [
        "PgOrderRepository",
        "OrderLifecycleService",
        "OwnerBoundedExecutionService",
        "PgExecutionIntentRepository",
        "ExchangeGateway",
    ]
    files = [
        Path("src/domain/signal_evaluation.py"),
        Path("src/application/signal_evaluation_shadow_service.py"),
        Path("src/infrastructure/pg_signal_evaluation_repository.py"),
    ]
    for path in files:
        text = path.read_text()
        for token in forbidden:
            assert token not in text

    import src.interfaces.api_trading_console as api_trading_console

    for fn in [
        api_trading_console.list_signal_evaluations,
        api_trading_console.get_signal_evaluation,
        api_trading_console.list_order_candidates,
        api_trading_console.get_order_candidate,
        api_trading_console._signal_evaluation_shadow_service,
    ]:
        source = py_inspect.getsource(fn)
        for token in forbidden:
            assert token not in source


def test_existing_bounded_live_trial_authorization_stays_single_use_metadata_only():
    authorization = BoundedLiveTrialAuthorization(
        authorization_id="auth-1",
        draft_id="draft-1",
        carrier_id="carrier-1",
        strategy_family_id="family-1",
        symbol="ETH/USDT:USDT",
        side="long",
        max_notional=Decimal("25"),
        quantity=Decimal("0.01"),
        leverage=Decimal("2"),
        protection_plan_type="single_tp_plus_sl",
        owner_live_authorized_by="owner",
        owner_live_authorized_at_ms=NOW_MS,
        linked_acknowledgement_id="ack-1",
        source_draft_id="draft-1",
        hard_blockers=[],
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )

    assert authorization.single_use is True
    assert authorization.execution_intent_created is False
    assert authorization.order_created is False
    assert authorization.next_executable is False
    assert authorization.metadata_only is True
