from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.strategy_evaluation_context_builder import (
    build_strategy_evaluation_context,
)
from src.application.strategy_semantics_shadow_binding_service import (
    StrategySemanticsBindingError,
    StrategySemanticsShadowBindingService,
)
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
from src.domain.strategy_semantics import (
    FactAvailabilityStatus,
    MarketState,
    StrategyFactCheckStatus,
    initial_strategy_semantics_catalog,
)


NOW_MS = 1781000000000


def _candles(count: int) -> list[dict]:
    candles: list[dict] = []
    for index in range(count):
        close = Decimal("2500") + Decimal(index)
        candles.append(
            {
                "open_time_ms": NOW_MS - (count - index) * 3_600_000,
                "open": str(close - Decimal("1")),
                "high": str(close + Decimal("2")),
                "low": str(close - Decimal("3")),
                "close": str(close),
                "volume": "100",
            }
        )
    return candles


def _trend_down_candles(count: int) -> list[dict]:
    candles: list[dict] = []
    for index in range(count):
        close = Decimal("2600") - Decimal(index * 8)
        candles.append(
            {
                "open_time_ms": NOW_MS - (count - index) * 3_600_000,
                "open": str(close + Decimal("1")),
                "high": str(close + Decimal("3")),
                "low": str(close - Decimal("3")),
                "close": str(close),
                "volume": "100",
            }
        )
    return candles


def _signal_input(
    *,
    family_id: str = "CPM-RO-001",
    version_id: str = "CPM-RO-001-v0",
    include_4h: bool = True,
    account_status: str = "normal",
    account_limitations: list[str] | None = None,
    include_funding: bool = True,
) -> StrategyFamilySignalInput:
    windows = {"1h": _candles(25)}
    if include_4h:
        windows["4h"] = _candles(12)
    return StrategyFamilySignalInput(
        evaluation_id=f"eval-{family_id}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        trigger_candle_close_time_ms=NOW_MS,
        primary_timeframe="1h",
        context_timeframes=["4h"],
        market_snapshot=MarketSnapshot(
            symbol="ETH/USDT:USDT",
            timestamp_ms=NOW_MS,
            source="exchange_live_market_read_only",
            freshness="fresh",
            last_price=Decimal("2525"),
            mark_price=Decimal("2525"),
            funding_rate=Decimal("0.0001") if include_funding else None,
            volatility=Decimal("0.15"),
            atr=Decimal("25"),
            timeframe="1h",
            candle_context={"windows": windows, "closed_bar": True},
        ),
        account_facts_snapshot=AccountFactsSnapshot(
            source="exchange_live_account_read_only",
            truth_level="exchange_read",
            timestamp_ms=NOW_MS,
            freshness="fresh",
            account_status=account_status,
            available_balance=Decimal("30"),
            positions=[],
            open_orders=[],
            position_count=0,
            open_order_count=0,
            unknown_unmanaged_counts={"orders": 0, "positions": 0},
            reconciliation_status={"status": "clean"},
            read_only_provider="unit_test_read_only",
            limitations=account_limitations or [],
        ),
        position_open_order_summary={"position_count": 0, "open_order_count": 0},
        reconciliation_status={"status": "clean"},
        runtime_safety_snapshot={"runtime_state": "shadow", "live_ready": False},
        trial_constraints_snapshot={
            "max_attempts": 3,
            "max_loss_budget": "10",
            "max_notional_per_attempt": "10",
            "max_active_positions": 1,
            "max_leverage": "1",
            "allowed_symbols": ["ETH/USDT:USDT"],
        },
        source="unit_test",
        freshness="fresh",
    )


def _runtime(
    *,
    family_id: str = "CPM-RO-001",
    version_id: str = "CPM-RO-001-v0",
    side: str = "long",
) -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-b0-builder",
        trial_binding_id="trial-b0-builder",
        admission_decision_id="admission-b0-builder",
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
            total_budget=Decimal("30"),
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=[side],
            max_leverage=Decimal("1"),
            requires_protection=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _output(
    *,
    family_id: str = "CPM-RO-001",
    version_id: str = "CPM-RO-001-v0",
    side: SignalSide = SignalSide.LONG,
    signal_type: SignalType = SignalType.WOULD_ENTER,
    evidence_payload: dict | None = None,
) -> StrategyFamilySignalOutput:
    return StrategyFamilySignalOutput(
        signal_id=f"signal-{family_id}",
        evaluation_id=f"eval-{family_id}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        trigger_candle_close_time_ms=NOW_MS,
        timeframe="1h",
        signal_type=signal_type,
        side=side,
        confidence=Decimal("0.7"),
        reason_codes=["price_action_closed_bar"],
        human_summary="B0 builder strategy signal.",
        required_execution_mode="observe_only",
        evidence_payload=evidence_payload
        if evidence_payload is not None
        else {"price_action_structure": {"pullback_reclaim": True}},
    )


class _FakeShadowService:
    def __init__(self) -> None:
        self.evaluation: SignalEvaluation | None = None

    async def create_signal_evaluation_from_strategy_family_output(
        self,
        output: StrategyFamilySignalOutput,
        *,
        runtime=None,
        metadata=None,
    ) -> SignalEvaluation:
        side = "none" if output.side == SignalSide.NONE else output.side.value
        self.evaluation = SignalEvaluation(
            signal_evaluation_id="signal-eval-b0-builder",
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
        )
        return self.evaluation

    async def get_signal_evaluation(self, signal_evaluation_id: str) -> SignalEvaluation:
        assert self.evaluation is not None
        assert signal_evaluation_id == self.evaluation.signal_evaluation_id
        return self.evaluation

    async def create_order_candidate_from_signal_evaluation(self, signal_evaluation_id: str, **kwargs):
        assert self.evaluation is not None
        return OrderCandidate(
            order_candidate_id="order-candidate-b0-builder",
            signal_evaluation_id=signal_evaluation_id,
            runtime_instance_id=self.evaluation.runtime_instance_id,
            trial_binding_id=self.evaluation.trial_binding_id,
            strategy_family_id=self.evaluation.strategy_family_id,
            strategy_family_version_id=self.evaluation.strategy_family_version_id,
            symbol=self.evaluation.symbol,
            side=self.evaluation.side,
            candidate_order_type=kwargs["candidate_order_type"],
            risk_preview=kwargs["risk_preview"],
            protection_preview=kwargs["protection_preview"],
            rationale=kwargs.get("rationale") or "",
            evidence_refs=kwargs["evidence_refs"],
            metadata=kwargs["metadata"],
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
        )


async def test_builder_context_can_feed_cpm_semantic_shadow_candidate():
    signal_input = _signal_input()
    output = _output()
    runtime = _runtime()
    context = build_strategy_evaluation_context(
        signal_input,
        output=output,
        runtime=runtime,
    )

    cpm = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
    )
    assert cpm.fact_check(context).status == StrategyFactCheckStatus.PASS
    assert context.facts["ohlcv_1h"].status == FactAvailabilityStatus.AVAILABLE
    assert context.facts["ohlcv_4h"].status == FactAvailabilityStatus.AVAILABLE
    assert context.facts["account_facts"].status == FactAvailabilityStatus.AVAILABLE
    assert context.facts["runtime_boundary"].value_snapshot["runtime_instance_id"] == (
        "runtime-b0-builder"
    )

    candidate = await StrategySemanticsShadowBindingService(
        shadow_service=_FakeShadowService()
    ).create_semantic_order_candidate_from_strategy_output(
        output,
        context=context,
        runtime=runtime,
        intended_notional=Decimal("10"),
        entry_price_reference=Decimal("2525"),
        stop_price_reference=Decimal("2475"),
        max_loss_reference=Decimal("3"),
        leverage=Decimal("1"),
    )

    assert candidate.not_order is True
    assert candidate.not_execution_intent is True
    assert candidate.candidate_executable is False
    assert candidate.metadata["adapter_scope"] == "b0_shadow_only"
    assert candidate.metadata["fact_check"]["status"] == "PASS"


async def test_binding_service_builds_context_from_signal_pair_before_shadow_candidate():
    signal_input = _signal_input()
    output = _output()
    runtime = _runtime()

    candidate = await StrategySemanticsShadowBindingService(
        shadow_service=_FakeShadowService()
    ).create_semantic_order_candidate_from_strategy_signal_pair(
        signal_input,
        output,
        runtime=runtime,
        context_id="context-built-by-service",
        intended_notional=Decimal("10"),
        entry_price_reference=Decimal("2525"),
        stop_price_reference=Decimal("2475"),
        max_loss_reference=Decimal("3"),
        leverage=Decimal("1"),
    )

    assert candidate.not_order is True
    assert candidate.not_execution_intent is True
    assert candidate.metadata["adapter_scope"] == "b0_shadow_only"
    assert candidate.metadata["strategy_evaluation_context_id"] == (
        "context-built-by-service"
    )
    assert candidate.metadata["strategy_evaluation_missing_facts"] == [
        "crowding_proxy",
        "open_interest",
        "range_structure",
        "short_squeeze_risk",
    ]
    assert candidate.metadata["fact_check"]["status"] == "PASS"


async def test_builder_missing_4h_context_blocks_cpm_binding():
    signal_input = _signal_input(include_4h=False)
    output = _output()
    context = build_strategy_evaluation_context(
        signal_input,
        output=output,
        runtime=_runtime(),
    )

    assert context.facts["ohlcv_4h"].status == FactAvailabilityStatus.MISSING
    with pytest.raises(StrategySemanticsBindingError, match="BLOCK_MISSING_FACTS"):
        await StrategySemanticsShadowBindingService(
            shadow_service=_FakeShadowService()
        ).create_semantic_order_candidate_from_strategy_output(
            output,
            context=context,
            runtime=_runtime(),
            stop_price_reference=Decimal("2475"),
        )


async def test_binding_service_signal_pair_still_blocks_missing_required_facts():
    signal_input = _signal_input(include_4h=False)
    output = _output()

    with pytest.raises(StrategySemanticsBindingError, match="BLOCK_MISSING_FACTS"):
        await StrategySemanticsShadowBindingService(
            shadow_service=_FakeShadowService()
        ).create_semantic_order_candidate_from_strategy_signal_pair(
            signal_input,
            output,
            runtime=_runtime(),
            stop_price_reference=Decimal("2475"),
        )


async def test_builder_does_not_invent_brf_short_squeeze_risk():
    signal_input = _signal_input(
        family_id="BRF-001",
        version_id="BRF-001-v0",
    )
    output = _output(
        family_id="BRF-001",
        version_id="BRF-001-v0",
        side=SignalSide.SHORT,
        evidence_payload={"price_action_structure": {"bear_rally_failure": True}},
    )
    context = build_strategy_evaluation_context(
        signal_input,
        output=output,
        runtime=_runtime(family_id="BRF-001", version_id="BRF-001-v0", side="short"),
    )

    brf = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
    )
    fact_check = brf.fact_check(context)

    assert context.facts["short_squeeze_risk"].status == FactAvailabilityStatus.MISSING
    assert fact_check.status == StrategyFactCheckStatus.OBSERVE_ONLY
    assert "short_squeeze_risk" in fact_check.missing_facts
    with pytest.raises(StrategySemanticsBindingError, match="OBSERVE_ONLY"):
        await StrategySemanticsShadowBindingService(
            shadow_service=_FakeShadowService()
        ).create_semantic_order_candidate_from_strategy_output(
            output,
            context=context,
            runtime=_runtime(family_id="BRF-001", version_id="BRF-001-v0", side="short"),
            stop_price_reference=Decimal("2575"),
        )


def test_builder_keeps_fco_data_dependencies_missing_until_explicit_sources_exist():
    signal_input = _signal_input(
        family_id="FCO-001",
        version_id="FCO-001-v0",
        include_funding=True,
    )
    context = build_strategy_evaluation_context(signal_input)
    fco = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id="FCO-001",
        strategy_family_version_id="FCO-001-v0",
    )
    fact_check = fco.fact_check(context)

    assert context.facts["funding_rate"].status == FactAvailabilityStatus.AVAILABLE
    assert context.facts["open_interest"].status == FactAvailabilityStatus.MISSING
    assert context.facts["crowding_proxy"].status == FactAvailabilityStatus.MISSING
    assert fact_check.status == StrategyFactCheckStatus.BLOCK_MISSING_FACTS


def test_builder_generates_rmr_regime_facts_without_execution_authority():
    signal_input = _signal_input(
        family_id="RMR-001",
        version_id="RMR-001-v0",
    )
    signal_input.market_snapshot.candle_context["windows"]["1h"] = _trend_down_candles(16)
    context = build_strategy_evaluation_context(signal_input)
    rmr = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id="RMR-001",
        strategy_family_version_id="RMR-001-v0",
    )
    fact_check = rmr.fact_check(context)

    assert context.market_state == MarketState.TREND_DOWN
    assert fact_check.status == StrategyFactCheckStatus.PASS
    assert context.facts["range_structure"].source == "rmr_regime_classifier"
    range_value = context.facts["range_structure"].value_snapshot["value"]
    assert range_value["market_state"] == "TREND_DOWN"
    assert range_value["strategy_effect"]["brf"] == (
        "context_support_only_not_execution_authority"
    )
    assert range_value["hard_filter"] is False
    assert range_value["execution_authority"] is False
    assert context.facts["volatility_state"].status == FactAvailabilityStatus.AVAILABLE


def test_builder_marks_observation_only_account_facts_as_missing():
    signal_input = _signal_input(
        account_status="not_checked",
        account_limitations=["observation signal input does not require account facts"],
    )
    context = build_strategy_evaluation_context(signal_input, output=_output())

    assert context.facts["account_facts"].status == FactAvailabilityStatus.MISSING
    assert "account_facts" in context.metadata["missing_facts"]
