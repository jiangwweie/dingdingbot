from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.runtime_execution_planning_service import (
    RuntimeExecutionPlanningService,
)
from src.application.runtime_final_gate_preview_service import (
    RuntimeFinalGatePreviewService,
)
from src.application.runtime_strategy_signal_planning_service import (
    RuntimeStrategySignalCandidatePlanningStatus,
    RuntimeStrategySignalPlanningError,
    RuntimeStrategySignalPlanningService,
)
from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationService,
)
from src.application.signal_evaluation_shadow_service import SignalEvaluationShadowService
from src.application.strategy_runtime_fact_overlay_service import (
    StrategyRuntimeFactOverlayService,
)
from src.application.strategy_semantics_shadow_binding_service import (
    StrategySemanticsBindingError,
    StrategySemanticsShadowBindingService,
)
from src.application.trial_readiness_account_facts import (
    AccountFactsFreshnessStatus,
    AccountFactsReconciliationStatus,
    AccountFactsSourceType,
    StaticTrialReadinessAccountFactsSource,
    TrialReadinessAccountFacts,
)
from src.domain.runtime_execution_plan import RuntimeExecutionIntentDraftStatus
from src.domain.signal_evaluation import (
    OrderCandidate,
    SignalEvaluation,
    SignalEvaluationDecision,
    SignalEvaluationStatus,
)
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    MarketSnapshot,
    SignalSide,
    SignalType,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.infrastructure.pg_models import (
    PGOrderCandidateORM,
    PGSignalEvaluationORM,
    PGRuntimeExecutionIntentDraftORM,
)
from src.infrastructure.pg_runtime_execution_intent_draft_repository import (
    PgRuntimeExecutionIntentDraftRepository,
)
from src.infrastructure.pg_signal_evaluation_repository import PgSignalEvaluationRepository


NOW_MS = 1781000000000


def _candles(count: int) -> list[dict]:
    return [
        {
            "open_time_ms": NOW_MS - (count - index) * 3_600_000,
            "open": str(Decimal("2500") + Decimal(index)),
            "high": str(Decimal("2502") + Decimal(index)),
            "low": str(Decimal("2497") + Decimal(index)),
            "close": str(Decimal("2501") + Decimal(index)),
            "volume": "100",
        }
        for index in range(count)
    ]


def _signal_input(*, include_4h: bool = True) -> StrategyFamilySignalInput:
    windows = {"1h": _candles(25)}
    if include_4h:
        windows["4h"] = _candles(12)
    return StrategyFamilySignalInput(
        evaluation_id="eval-cpm-runtime-orchestration",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        primary_timeframe="1h",
        context_timeframes=["4h"],
        market_snapshot=MarketSnapshot(
            symbol="ETH/USDT:USDT",
            timestamp_ms=NOW_MS,
            source="unit_market_read_only",
            freshness="fresh",
            last_price=Decimal("2525"),
            mark_price=Decimal("2525"),
            funding_rate=Decimal("0.0001"),
            volatility=Decimal("0.15"),
            atr=Decimal("25"),
            timeframe="1h",
            candle_context={"windows": windows, "closed_bar": True},
        ),
        account_facts_snapshot=AccountFactsSnapshot(
            source="unit_account_read_only",
            truth_level="exchange_read",
            timestamp_ms=NOW_MS,
            freshness="fresh",
            account_status="normal",
            available_balance=Decimal("30"),
            positions=[],
            open_orders=[],
            position_count=0,
            open_order_count=0,
            unknown_unmanaged_counts={"orders": 0, "positions": 0},
            reconciliation_status={"status": "clean"},
            read_only_provider="unit_test",
            limitations=[],
        ),
        position_open_order_summary={"position_count": 0, "open_order_count": 0},
        reconciliation_status={"status": "clean"},
        runtime_safety_snapshot={"runtime_state": "shadow", "live_ready": False},
        trial_constraints_snapshot={
            "max_attempts": 3,
            "max_loss_budget": "9",
            "max_notional_per_attempt": "10",
            "max_active_positions": 1,
            "max_leverage": "1",
            "allowed_symbols": ["ETH/USDT:USDT"],
        },
        source="unit_test",
        freshness="fresh",
    )


def _output(signal_type: SignalType = SignalType.WOULD_ENTER) -> StrategyFamilySignalOutput:
    return StrategyFamilySignalOutput(
        signal_id="signal-cpm-runtime-orchestration",
        evaluation_id="eval-cpm-runtime-orchestration",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        timeframe="1h",
        signal_type=signal_type,
        side=SignalSide.LONG if signal_type == SignalType.WOULD_ENTER else SignalSide.NONE,
        confidence=Decimal("0.7"),
        reason_codes=["price_action_closed_bar"],
        human_summary="CPM runtime orchestration unit signal.",
        required_execution_mode="observe_only",
        evidence_payload={"price_action_structure": {"pullback_reclaim": True}},
    )


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-cpm-orchestration",
        trial_binding_id="trial-cpm-orchestration",
        admission_decision_id="admission-cpm-orchestration",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        side="long",
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("9"),
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=["long"],
            max_leverage=Decimal("1"),
            max_margin_per_attempt=Decimal("10"),
            min_liquidation_stop_buffer=Decimal("25"),
            requires_protection=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _runtime_for_strategy(
    *,
    family_id: str,
    version_id: str,
    side: str,
) -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id=f"runtime-{family_id.lower()}-{side}",
        trial_binding_id=f"trial-{family_id.lower()}-{side}",
        admission_decision_id=f"admission-{family_id.lower()}-{side}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        side=side,
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("9"),
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=[side],
            max_leverage=Decimal("1"),
            max_margin_per_attempt=Decimal("10"),
            min_liquidation_stop_buffer=Decimal("25"),
            requires_protection=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _candle(index: int, open_: str, high: str, low: str, close: str) -> dict[str, Any]:
    return {
        "open_time_ms": NOW_MS - (40 - index) * 3_600_000,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": "100",
    }


def _cpm_reclaim_1h() -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for index in range(18):
        close = Decimal("100") + Decimal(index) * Decimal("0.15")
        candles.append(
            _candle(
                index,
                str(close - Decimal("0.1")),
                str(close + Decimal("0.4")),
                str(close - Decimal("0.4")),
                str(close),
            )
        )
    candles.append(_candle(18, "101.6", "102.4", "100.9", "101.8"))
    candles.append(_candle(19, "101.9", "103.0", "101.0", "102.2"))
    candles.append(_candle(20, "102.4", "105.0", "102.0", "104.2"))
    return candles


def _cpm_uptrend_4h() -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for index in range(21):
        close = Decimal("100") + Decimal(index) * Decimal("0.5")
        candles.append(
            _candle(
                index,
                str(close - Decimal("0.2")),
                str(close + Decimal("0.5")),
                str(close - Decimal("0.5")),
                str(close),
            )
        )
    return candles


def _brf_1h() -> list[dict[str, Any]]:
    return [
        _candle(0, "101", "102", "99", "100"),
        _candle(1, "100", "103", "99", "102"),
        _candle(2, "102", "105", "101", "104"),
        _candle(3, "104", "106", "103", "105"),
        _candle(4, "105", "108", "104", "107"),
        _candle(5, "107", "109", "106", "108"),
        _candle(6, "108", "110", "107", "109"),
        _candle(7, "109", "111", "108", "110"),
        _candle(8, "110", "112", "109", "111"),
        _candle(9, "111", "113", "110", "112"),
        _candle(10, "112", "113", "109", "111"),
        _candle(11, "111", "114", "105", "106"),
    ]


def _brf_down_context_4h() -> list[dict[str, Any]]:
    return [
        _candle(0, "122", "123", "119", "120"),
        _candle(1, "120", "121", "117", "118"),
        _candle(2, "118", "119", "115", "116"),
        _candle(3, "116", "117", "113", "114"),
    ]


def _runtime_signal_input(
    *,
    family_id: str,
    version_id: str,
    one_hour: list[dict[str, Any]],
    four_hour: list[dict[str, Any]],
    last_price: Decimal,
    atr: Decimal,
    side: str,
) -> StrategyFamilySignalInput:
    return StrategyFamilySignalInput(
        evaluation_id=f"eval-runtime-signal-{family_id}-{side}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        primary_timeframe="1h",
        context_timeframes=["4h"],
        market_snapshot=MarketSnapshot(
            symbol="ETH/USDT:USDT",
            timestamp_ms=NOW_MS,
            source="unit_market_read_only",
            freshness="fresh",
            last_price=last_price,
            mark_price=last_price,
            funding_rate=Decimal("0.0001"),
            volatility=Decimal("0.15"),
            atr=atr,
            timeframe="1h",
            candle_context={
                "windows": {"1h": one_hour, "4h": four_hour},
                "closed_bar": True,
            },
        ),
        account_facts_snapshot=AccountFactsSnapshot(
            source="unit_account_placeholder",
            truth_level="placeholder",
            timestamp_ms=NOW_MS,
            freshness="fresh",
            account_status="not_checked",
            available_balance=Decimal("30"),
            positions=[],
            open_orders=[],
            position_count=99,
            open_order_count=0,
            unknown_unmanaged_counts={"orders": 0, "positions": 99},
            reconciliation_status={"status": "not_checked"},
            read_only_provider="unit_placeholder",
            limitations=["caller supplied facts must be replaced by trusted overlay"],
        ),
        position_open_order_summary={"active_positions_count": 99, "position_count": 99},
        reconciliation_status={"status": "not_checked"},
        runtime_safety_snapshot={"runtime_state": "shadow", "live_ready": False},
        trial_constraints_snapshot={
            "max_attempts": 3,
            "max_loss_budget": "9",
            "max_notional_per_attempt": "10",
            "max_active_positions": 1,
            "max_leverage": "1",
            "allowed_symbols": ["ETH/USDT:USDT"],
            "side": side,
        },
        source="unit_test",
        freshness="fresh",
    )


def _ready_account_source() -> StaticTrialReadinessAccountFactsSource:
    return StaticTrialReadinessAccountFactsSource(
        TrialReadinessAccountFacts(
            account_id="unit-account",
            account_type="unit",
            source_id="unit_cached_account_facts",
            source_type=AccountFactsSourceType.PG_ACCOUNT_FACTS,
            account_equity=Decimal("30"),
            available_margin=Decimal("29"),
            timestamp_ms=NOW_MS,
            freshness_status=AccountFactsFreshnessStatus.FRESH,
            reconciliation_status=AccountFactsReconciliationStatus.CLEAN,
            read_only_guarantee=True,
            external_call_performed=False,
            external_call_type="none",
        )
    )


class _TrustedPositionSource:
    def __init__(self, positions: list | None = None) -> None:
        self.positions = positions or []

    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        assert symbol == "ETH/USDT:USDT"
        assert limit == 100
        return list(self.positions)


class _FakeCPMShortEvaluator:
    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> StrategyFamilySignalOutput:
        return StrategyFamilySignalOutput(
            signal_id=f"fake-short-{signal_input.evaluation_id}",
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            symbol=signal_input.symbol,
            timestamp_ms=signal_input.timestamp_ms,
            timeframe=signal_input.primary_timeframe,
            signal_type=SignalType.WOULD_ENTER,
            side=SignalSide.SHORT,
            confidence=Decimal("0.6"),
            reason_codes=["unit_fake_cpm_short"],
            human_summary="Fake CPM short output for semantic gate coverage.",
            required_execution_mode="observe_only",
            evidence_payload={
                "latest_1h_close": "104.2",
                "lookback_low": "100.9",
                "price_action_structure": {"pullback_reclaim": True},
            },
        )


class _ShadowAndCandidateStore:
    def __init__(self) -> None:
        self.evaluation: SignalEvaluation | None = None
        self.candidate: OrderCandidate | None = None

    async def create_signal_evaluation_from_strategy_family_output(
        self,
        output: StrategyFamilySignalOutput,
        *,
        runtime=None,
        metadata=None,
    ) -> SignalEvaluation:
        side = "none" if output.side == SignalSide.NONE else output.side.value
        self.evaluation = SignalEvaluation(
            signal_evaluation_id="signal-eval-runtime-orchestration",
            runtime_instance_id=getattr(runtime, "runtime_instance_id", None),
            trial_binding_id=getattr(runtime, "trial_binding_id", None),
            strategy_family_id=output.strategy_family_id,
            strategy_family_version_id=output.strategy_family_version_id,
            source_signal_id=output.signal_id,
            symbol=output.symbol,
            side=side,
            status=SignalEvaluationStatus.EVALUATED,
            decision=SignalEvaluationDecision.CANDIDATE,
            reason_codes=list(output.reason_codes),
            rationale=output.human_summary,
            evaluated_at_ms=NOW_MS,
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
            metadata=metadata or {},
        )
        return self.evaluation

    async def get_signal_evaluation(self, signal_evaluation_id: str) -> SignalEvaluation:
        assert self.evaluation is not None
        assert signal_evaluation_id == self.evaluation.signal_evaluation_id
        return self.evaluation

    async def create_order_candidate_from_signal_evaluation(
        self,
        signal_evaluation_id: str,
        **kwargs,
    ) -> OrderCandidate:
        assert self.evaluation is not None
        self.candidate = OrderCandidate(
            order_candidate_id="order-candidate-runtime-orchestration",
            signal_evaluation_id=signal_evaluation_id,
            runtime_instance_id=self.evaluation.runtime_instance_id,
            trial_binding_id=self.evaluation.trial_binding_id,
            strategy_family_id=self.evaluation.strategy_family_id,
            strategy_family_version_id=self.evaluation.strategy_family_version_id,
            symbol=self.evaluation.symbol,
            side=self.evaluation.side,
            candidate_order_type=kwargs["candidate_order_type"],
            proposed_quantity=kwargs.get("proposed_quantity"),
            intended_notional=kwargs.get("intended_notional"),
            entry_price_reference=kwargs.get("entry_price_reference"),
            risk_preview=kwargs["risk_preview"],
            protection_preview=kwargs["protection_preview"],
            rationale=kwargs.get("rationale") or "",
            evidence_refs=kwargs["evidence_refs"],
            metadata=kwargs["metadata"],
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
        )
        return self.candidate

    async def get_order_candidate(self, order_candidate_id: str) -> OrderCandidate:
        assert self.candidate is not None
        assert order_candidate_id == self.candidate.order_candidate_id
        return self.candidate


def _service(
    *,
    active_positions=None,
    include_position_source: bool = True,
    store: _ShadowAndCandidateStore | None = None,
) -> RuntimeStrategySignalPlanningService:
    runtime = _runtime()
    store = store or _ShadowAndCandidateStore()

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == runtime.runtime_instance_id
            return runtime

    class _PositionSource:
        async def list_active(self, *, symbol: str | None = None, limit: int = 100):
            assert symbol == runtime.symbol
            assert limit == 100
            return list(active_positions or [])

    final_gate = RuntimeFinalGatePreviewService(
        runtime_service=_RuntimeService(),
        signal_evaluation_service=store,
        active_position_source=_PositionSource() if include_position_source else None,
    )
    planning = RuntimeExecutionPlanningService(
        runtime_service=_RuntimeService(),
        signal_evaluation_service=store,
        final_gate_preview_service=final_gate,
    )
    return RuntimeStrategySignalPlanningService(
        semantics_binding_service=StrategySemanticsShadowBindingService(
            shadow_service=store,
        ),
        runtime_execution_planning_service=planning,
    )


def _candidate_planning_service(
    *,
    runtime: StrategyRuntimeInstance,
    store: _ShadowAndCandidateStore | None = None,
    overlay: StrategyRuntimeFactOverlayService | None = None,
    signal_evaluation_service: RuntimeStrategySignalEvaluationService | None = None,
) -> tuple[RuntimeStrategySignalPlanningService, _ShadowAndCandidateStore]:
    store = store or _ShadowAndCandidateStore()

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == runtime.runtime_instance_id
            return runtime

    class _PositionSource:
        async def list_active(self, *, symbol: str | None = None, limit: int = 100):
            assert symbol == runtime.symbol
            assert limit == 100
            return []

    final_gate = RuntimeFinalGatePreviewService(
        runtime_service=_RuntimeService(),
        signal_evaluation_service=store,
        active_position_source=_PositionSource(),
    )
    planning = RuntimeExecutionPlanningService(
        runtime_service=_RuntimeService(),
        signal_evaluation_service=store,
        final_gate_preview_service=final_gate,
    )
    return (
        RuntimeStrategySignalPlanningService(
            semantics_binding_service=StrategySemanticsShadowBindingService(
                shadow_service=store,
            ),
            runtime_execution_planning_service=planning,
            runtime_fact_overlay_service=overlay,
            signal_evaluation_service=signal_evaluation_service,
        ),
        store,
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


async def test_strategy_signal_pair_can_reach_runtime_intent_draft_without_execution():
    draft = await _service(active_positions=[]).intent_draft_for_strategy_signal_pair(
        _signal_input(),
        _output(),
        runtime=_runtime(),
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
        proposed_quantity=Decimal("0.004"),
        intended_notional=Decimal("10"),
        entry_price_reference=Decimal("2525"),
        stop_price_reference=Decimal("2475"),
        max_loss_reference=Decimal("3"),
        leverage=Decimal("1"),
        margin_required=Decimal("10"),
        liquidation_price_reference=Decimal("2400"),
        liquidation_stop_buffer=Decimal("75"),
        take_profit_references=[{"kind": "runner", "policy": "trailing_atr"}],
    )

    assert draft.status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
    assert draft.runtime_instance_id == "runtime-cpm-orchestration"
    assert draft.order_candidate_id == "order-candidate-runtime-orchestration"
    assert draft.risk_preview.max_loss_reference == Decimal("3")
    assert draft.protection_preview.stop_price_reference == Decimal("2475")
    assert draft.not_order is True
    assert draft.not_execution_intent is True
    assert draft.execution_intent_created is False
    assert draft.order_created is False
    assert draft.exchange_called is False


async def test_runtime_signal_input_cpm_long_creates_shadow_candidate_with_proposal():
    runtime = _runtime_for_strategy(
        family_id="CPM-RO-001",
        version_id="CPM-RO-001-v0",
        side="long",
    )
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=_TrustedPositionSource(positions=[]),
        account_facts_source=_ready_account_source(),
    )
    service, store = _candidate_planning_service(runtime=runtime, overlay=overlay)

    result = await service.plan_shadow_candidate_from_signal_input(
        _runtime_signal_input(
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            one_hour=_cpm_reclaim_1h(),
            four_hour=_cpm_uptrend_4h(),
            last_price=Decimal("104.2"),
            atr=Decimal("3"),
            side="long",
        ),
        runtime=runtime,
        context_id="context-cpm-shadow-planning-v1",
    )

    assert result.status == RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
    assert result.evaluation_result.can_call_semantic_binding is True
    assert result.signal_evaluation_created is True
    assert result.order_candidate_created is True
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False
    assert store.evaluation is not None
    assert store.candidate is not None
    assert result.candidate is store.candidate
    assert result.candidate.side == "long"
    assert result.proposal is not None
    assert result.proposal.entry_price_reference == Decimal("104.2")
    assert result.proposal.stop_source == "cpm_pullback_low"
    assert result.proposal.stop_price_reference == Decimal("99.6")
    assert result.proposal.intended_notional == Decimal("10")
    assert result.proposal.leverage == Decimal("1")
    assert result.proposal.margin_required == Decimal("10.00000000")
    assert result.proposal.max_loss_reference > Decimal("0")
    assert result.candidate.entry_price_reference == Decimal("104.2")
    assert result.candidate.risk_preview.intended_notional == Decimal("10")
    assert result.candidate.protection_preview.stop_price_reference == Decimal("99.6")
    assert result.candidate.protection_preview.take_profit_references[0]["rr"] == "1"
    assert (
        result.candidate.protection_preview.take_profit_references[1][
            "right_tail_capture"
        ]
        is True
    )
    assert result.candidate.metadata["runtime_strategy_signal_candidate_planning"] is True
    assert result.candidate.metadata["planning_proposal"]["metadata"]["not_proven_alpha"] is True
    assert result.candidate.not_order is True
    assert result.candidate.not_execution_intent is True


async def test_runtime_signal_input_brf_short_creates_shadow_candidate_with_rally_stop():
    runtime = _runtime_for_strategy(
        family_id="BRF-001",
        version_id="BRF-001-v0",
        side="short",
    )
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=_TrustedPositionSource(positions=[]),
        account_facts_source=_ready_account_source(),
    )
    service, store = _candidate_planning_service(runtime=runtime, overlay=overlay)

    result = await service.plan_shadow_candidate_from_signal_input(
        _runtime_signal_input(
            family_id="BRF-001",
            version_id="BRF-001-v0",
            one_hour=_brf_1h(),
            four_hour=_brf_down_context_4h(),
            last_price=Decimal("106"),
            atr=Decimal("4"),
            side="short",
        ),
        runtime=runtime,
        context_id="context-brf-shadow-planning-v1",
    )

    assert result.status == RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
    assert result.evaluation_result.output is not None
    assert result.evaluation_result.output.side == SignalSide.SHORT
    assert store.evaluation is not None
    assert store.candidate is not None
    assert result.candidate is store.candidate
    assert result.candidate.side == "short"
    assert result.proposal is not None
    assert result.proposal.entry_price_reference == Decimal("106")
    assert result.proposal.stop_source == "brf_rally_high"
    assert result.proposal.stop_price_reference == Decimal("114")
    assert result.proposal.take_profit_references[0]["price_reference"] == "98.00000000"
    assert (
        result.proposal.take_profit_references[1]["policy"]
        == "trailing_atr_or_structure_invalidation"
    )
    assert result.candidate.protection_preview.stop_price_reference == Decimal("114")
    assert result.candidate.risk_preview.leverage == Decimal("1")
    assert result.candidate.execution_enabled is False
    assert result.candidate.candidate_executable is False
    assert result.execution_intent_created is False
    assert result.order_lifecycle_called is False
    assert result.exchange_called is False


async def test_runtime_signal_input_cpm_short_mismatch_blocks_before_candidate():
    runtime = _runtime_for_strategy(
        family_id="CPM-RO-001",
        version_id="CPM-RO-001-v0",
        side="long",
    )
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=_TrustedPositionSource(positions=[]),
        account_facts_source=_ready_account_source(),
    )
    evaluator_gate = RuntimeStrategySignalEvaluationService(
        evaluators={
            ("CPM-RO-001", "CPM-RO-001-v0"): _FakeCPMShortEvaluator(),
        }
    )
    service, store = _candidate_planning_service(
        runtime=runtime,
        overlay=overlay,
        signal_evaluation_service=evaluator_gate,
    )

    result = await service.plan_shadow_candidate_from_signal_input(
        _runtime_signal_input(
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            one_hour=_cpm_reclaim_1h(),
            four_hour=_cpm_uptrend_4h(),
            last_price=Decimal("104.2"),
            atr=Decimal("3"),
            side="long",
        ),
        runtime=runtime,
    )

    assert result.status == RuntimeStrategySignalCandidatePlanningStatus.BLOCKED
    assert "strategy_output_side_not_supported_by_semantics" in result.blockers
    assert result.candidate is None
    assert result.proposal is None
    assert store.evaluation is None
    assert store.candidate is None
    assert result.order_candidate_created is False
    assert result.execution_intent_created is False


async def test_runtime_signal_input_rmr_and_fco_do_not_trade():
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=_TrustedPositionSource(positions=[]),
        account_facts_source=_ready_account_source(),
    )

    for family_id, version_id, expected_status in [
        (
            "RMR-001",
            "RMR-001-v0",
            RuntimeStrategySignalCandidatePlanningStatus.OBSERVE_ONLY,
        ),
        (
            "FCO-001",
            "FCO-001-v0",
            RuntimeStrategySignalCandidatePlanningStatus.BLOCKED,
        ),
    ]:
        runtime = _runtime_for_strategy(
            family_id=family_id,
            version_id=version_id,
            side="long",
        )
        service, store = _candidate_planning_service(runtime=runtime, overlay=overlay)

        result = await service.plan_shadow_candidate_from_signal_input(
            _runtime_signal_input(
                family_id=family_id,
                version_id=version_id,
                one_hour=_cpm_reclaim_1h(),
                four_hour=_cpm_uptrend_4h(),
                last_price=Decimal("104.2"),
                atr=Decimal("3"),
                side="long",
            ),
            runtime=runtime,
        )

        assert result.status == expected_status
        assert result.candidate is None
        assert result.proposal is None
        assert store.evaluation is None
        assert store.candidate is None
        assert result.order_candidate_created is False
        assert result.execution_intent_created is False
        assert result.exchange_called is False


async def test_runtime_signal_input_blocks_missing_trusted_account_facts_before_candidate():
    runtime = _runtime_for_strategy(
        family_id="CPM-RO-001",
        version_id="CPM-RO-001-v0",
        side="long",
    )
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=_TrustedPositionSource(positions=[]),
        account_facts_source=None,
    )
    service, store = _candidate_planning_service(runtime=runtime, overlay=overlay)

    result = await service.plan_shadow_candidate_from_signal_input(
        _runtime_signal_input(
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            one_hour=_cpm_reclaim_1h(),
            four_hour=_cpm_uptrend_4h(),
            last_price=Decimal("104.2"),
            atr=Decimal("3"),
            side="long",
        ),
        runtime=runtime,
    )

    assert result.status == RuntimeStrategySignalCandidatePlanningStatus.BLOCKED
    assert "trusted_account_facts_source_unavailable" in result.blockers
    assert result.candidate is None
    assert result.proposal is None
    assert store.evaluation is None
    assert store.candidate is None
    assert result.order_candidate_created is False
    assert result.exchange_called is False


async def test_runtime_signal_input_blocks_missing_trusted_active_position_source_before_candidate():
    runtime = _runtime_for_strategy(
        family_id="CPM-RO-001",
        version_id="CPM-RO-001-v0",
        side="long",
    )
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=None,
        account_facts_source=_ready_account_source(),
    )
    service, store = _candidate_planning_service(runtime=runtime, overlay=overlay)

    result = await service.plan_shadow_candidate_from_signal_input(
        _runtime_signal_input(
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            one_hour=_cpm_reclaim_1h(),
            four_hour=_cpm_uptrend_4h(),
            last_price=Decimal("104.2"),
            atr=Decimal("3"),
            side="long",
        ),
        runtime=runtime,
    )

    assert result.status == RuntimeStrategySignalCandidatePlanningStatus.BLOCKED
    assert "trusted_position_projection_source_unavailable" in result.blockers
    assert result.candidate is None
    assert result.proposal is None
    assert store.evaluation is None
    assert store.candidate is None
    assert result.signal_evaluation_created is False
    assert result.order_candidate_created is False
    assert result.execution_intent_created is False
    assert result.exchange_called is False


async def test_strategy_signal_pair_blocks_when_local_active_position_source_is_missing():
    draft = await _service(include_position_source=False).intent_draft_for_strategy_signal_pair(
        _signal_input(),
        _output(),
        runtime=_runtime(),
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
        proposed_quantity=Decimal("0.004"),
        intended_notional=Decimal("10"),
        entry_price_reference=Decimal("2525"),
        stop_price_reference=Decimal("2475"),
        max_loss_reference=Decimal("3"),
        leverage=Decimal("1"),
        margin_required=Decimal("10"),
        liquidation_price_reference=Decimal("2400"),
        liquidation_stop_buffer=Decimal("75"),
    )

    assert draft.status == RuntimeExecutionIntentDraftStatus.BLOCKED
    assert "active_positions_count_not_available" in draft.blockers
    assert draft.execution_intent_created is False
    assert draft.order_created is False
    assert draft.exchange_called is False


async def test_strategy_signal_pair_stops_before_candidate_when_required_facts_missing():
    store = _ShadowAndCandidateStore()

    with pytest.raises(StrategySemanticsBindingError, match="BLOCK_MISSING_FACTS"):
        await _service(active_positions=[], store=store).intent_draft_for_strategy_signal_pair(
            _signal_input(include_4h=False),
            _output(),
            runtime=_runtime(),
            owner_reviewed=True,
            owner_confirmed_for_intent=True,
            proposed_quantity=Decimal("0.004"),
            intended_notional=Decimal("10"),
            entry_price_reference=Decimal("2525"),
            stop_price_reference=Decimal("2475"),
            max_loss_reference=Decimal("3"),
            leverage=Decimal("1"),
            margin_required=Decimal("10"),
            liquidation_price_reference=Decimal("2400"),
            liquidation_stop_buffer=Decimal("75"),
        )

    assert store.candidate is None


async def test_strategy_signal_pair_requires_overlay_for_strategy_required_market_facts():
    signal_input = _signal_input().model_copy(
        update={
            "strategy_family_id": "FCO-001",
            "strategy_family_version_id": "FCO-001-v0",
        },
        deep=True,
    )
    output = StrategyFamilySignalOutput(
        signal_id="signal-fco-no-overlay",
        evaluation_id=signal_input.evaluation_id,
        strategy_family_id="FCO-001",
        strategy_family_version_id="FCO-001-v0",
        symbol=signal_input.symbol,
        timestamp_ms=NOW_MS,
        timeframe="1h",
        signal_type=SignalType.WOULD_ENTER,
        side=SignalSide.LONG,
        confidence=Decimal("0.6"),
        reason_codes=["funding_oi_crowding_review"],
        human_summary="FCO required market facts must have trusted overlay.",
        required_execution_mode="observe_only",
        evidence_payload={"market_facts": {"status": "caller_supplied"}},
    )
    runtime = _runtime().model_copy(
        update={
            "runtime_instance_id": "runtime-fco-no-overlay",
            "trial_binding_id": "trial-fco-no-overlay",
            "admission_decision_id": "admission-fco-no-overlay",
            "strategy_family_id": "FCO-001",
            "strategy_family_version_id": "FCO-001-v0",
        },
        deep=True,
    )

    with pytest.raises(
        RuntimeStrategySignalPlanningError,
        match="trusted market fact overlay is required",
    ):
        await _service(active_positions=[]).intent_draft_for_strategy_signal_pair(
            signal_input,
            output,
            runtime=runtime,
            owner_reviewed=True,
            owner_confirmed_for_intent=True,
            proposed_quantity=Decimal("0.004"),
            intended_notional=Decimal("10"),
            entry_price_reference=Decimal("2525"),
            stop_price_reference=Decimal("2475"),
            max_loss_reference=Decimal("3"),
            leverage=Decimal("1"),
            margin_required=Decimal("10"),
            liquidation_price_reference=Decimal("2400"),
            liquidation_stop_buffer=Decimal("75"),
        )


async def test_strategy_signal_pair_records_pg_shadow_candidate_and_intent_draft():
    engine, session_maker = await _repo_engine(
        PGSignalEvaluationORM.__table__,
        PGOrderCandidateORM.__table__,
        PGRuntimeExecutionIntentDraftORM.__table__,
    )
    shadow_service = SignalEvaluationShadowService(
        repository=PgSignalEvaluationRepository(session_maker=session_maker)
    )
    draft_repo = PgRuntimeExecutionIntentDraftRepository(session_maker=session_maker)
    runtime = _runtime()

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == runtime.runtime_instance_id
            return runtime

    class _PositionSource:
        async def list_active(self, *, symbol: str | None = None, limit: int = 100):
            assert symbol == runtime.symbol
            assert limit == 100
            return []

    final_gate = RuntimeFinalGatePreviewService(
        runtime_service=_RuntimeService(),
        signal_evaluation_service=shadow_service,
        active_position_source=_PositionSource(),
    )
    planning = RuntimeExecutionPlanningService(
        runtime_service=_RuntimeService(),
        signal_evaluation_service=shadow_service,
        final_gate_preview_service=final_gate,
        intent_draft_repository=draft_repo,
    )
    service = RuntimeStrategySignalPlanningService(
        semantics_binding_service=StrategySemanticsShadowBindingService(
            shadow_service=shadow_service,
        ),
        runtime_execution_planning_service=planning,
    )

    try:
        draft = await service.record_intent_draft_for_strategy_signal_pair(
            _signal_input(),
            _output(),
            runtime=runtime,
            owner_reviewed=True,
            owner_confirmed_for_intent=True,
            proposed_quantity=Decimal("0.004"),
            intended_notional=Decimal("10"),
            entry_price_reference=Decimal("2525"),
            stop_price_reference=Decimal("2475"),
            max_loss_reference=Decimal("3"),
            leverage=Decimal("1"),
            margin_required=Decimal("10"),
            liquidation_price_reference=Decimal("2400"),
            liquidation_stop_buffer=Decimal("75"),
            take_profit_references=[{"kind": "runner", "policy": "trailing_atr"}],
        )
        stored_evaluations = await shadow_service.list_signal_evaluations(
            strategy_family_id="CPM-RO-001"
        )
        stored_candidates = await shadow_service.list_order_candidates(
            signal_evaluation_id=draft.signal_evaluation_id
        )
        stored_draft = await draft_repo.get(draft.draft_id)

        assert len(stored_evaluations) == 1
        assert stored_evaluations[0].not_order is True
        assert stored_evaluations[0].not_execution_intent is True
        assert len(stored_candidates) == 1
        assert stored_candidates[0].metadata["adapter_scope"] == "b0_shadow_only"
        assert stored_candidates[0].risk_preview.max_loss_reference == Decimal("3")
        assert stored_draft is not None
        assert stored_draft.status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
        assert stored_draft.order_candidate_id == stored_candidates[0].order_candidate_id
        assert stored_draft.execution_intent_created is False
        assert stored_draft.order_created is False
        assert stored_draft.exchange_called is False
    finally:
        await engine.dispose()
