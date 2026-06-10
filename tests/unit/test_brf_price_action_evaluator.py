from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.application.strategy_evaluation_context_builder import (
    build_strategy_evaluation_context,
)
from src.application.strategy_semantics_shadow_binding_service import (
    StrategySemanticsShadowBindingService,
)
from src.domain.brf_price_action_evaluator import BRF001PriceActionEvaluator
from src.domain.signal_evaluation import (
    OrderCandidate,
    SignalEvaluation,
    SignalEvaluationDecision,
    SignalEvaluationStatus,
)
from src.domain.strategy_candidate_semantics import (
    EntrySetupKind,
    ExitPlanKind,
    StrategyArchetype,
    StrategyCandidateSemantics,
    StrategyPayoffProfile,
)
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    FORBIDDEN_EXECUTION_FIELDS,
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
    StrategyFactCheckStatus,
    initial_strategy_semantics_catalog,
)


NOW_MS = 1781000000000


def _candle(index: int, open_: str, high: str, low: str, close: str) -> dict[str, Any]:
    return {
        "open_time_ms": NOW_MS - (20 - index) * 3_600_000,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": "100",
    }


def _bear_rally_failure_1h() -> list[dict[str, Any]]:
    candles = [
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
    return candles


def _no_rejection_1h() -> list[dict[str, Any]]:
    candles = _bear_rally_failure_1h()
    candles[-1] = _candle(11, "111", "113", "110", "112")
    return candles


def _down_context_4h() -> list[dict[str, Any]]:
    return [
        _candle(0, "122", "123", "119", "120"),
        _candle(1, "120", "121", "117", "118"),
        _candle(2, "118", "119", "115", "116"),
        _candle(3, "116", "117", "113", "114"),
    ]


def _signal_input(
    *,
    family_id: str = "BRF-001",
    version_id: str = "BRF-001-v0",
    one_hour: list[dict[str, Any]] | None = None,
    four_hour: list[dict[str, Any]] | None = None,
    closed_bar: bool = True,
) -> StrategyFamilySignalInput:
    windows: dict[str, list[dict[str, Any]]] = {}
    if one_hour is not None:
        windows["1h"] = one_hour
    if four_hour is not None:
        windows["4h"] = four_hour
    return StrategyFamilySignalInput(
        evaluation_id=f"eval-{family_id}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        primary_timeframe="1h",
        context_timeframes=["4h"],
        market_snapshot=MarketSnapshot(
            symbol="ETH/USDT:USDT",
            timestamp_ms=NOW_MS,
            source="exchange_live_market_read_only",
            freshness="fresh",
            last_price=Decimal("106"),
            mark_price=Decimal("106"),
            funding_rate=Decimal("0.0001"),
            volatility=Decimal("0.18"),
            atr=Decimal("4"),
            timeframe="1h",
            candle_context={"windows": windows, "closed_bar": closed_bar},
        ),
        account_facts_snapshot=AccountFactsSnapshot(
            source="exchange_live_account_read_only",
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
            read_only_provider="unit_test_read_only",
            limitations=[],
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
            "side": "short",
        },
        source="unit_test",
        freshness="fresh",
    )


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-brf-evaluator",
        trial_binding_id="trial-brf-evaluator",
        admission_decision_id="admission-brf-evaluator",
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
        symbol="ETH/USDT:USDT",
        side="short",
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("30"),
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=["short"],
            max_leverage=Decimal("1"),
            requires_protection=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
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
            signal_evaluation_id="signal-eval-brf",
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

    async def create_order_candidate_from_signal_evaluation(self, signal_evaluation_id: str, **kwargs):
        assert self.evaluation is not None
        return OrderCandidate(
            order_candidate_id="order-candidate-brf",
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


async def test_brf_evaluator_supplies_short_squeeze_fact_for_shadow_candidate():
    signal_input = _signal_input(
        one_hour=_bear_rally_failure_1h(),
        four_hour=_down_context_4h(),
    )
    output = BRF001PriceActionEvaluator().evaluate(signal_input)

    assert output.signal_type == SignalType.WOULD_ENTER
    assert output.side == SignalSide.SHORT
    assert output.required_execution_mode == "observe_only"
    assert output.evidence_payload["price_action_structure"]["bear_rally_failure"] is True
    assert output.evidence_payload["short_squeeze_risk"]["status"] == "reviewed"
    assert (
        output.evidence_payload["short_squeeze_risk"]["runtime_confirmation_mode"]
        == "runtime_bounded_auto_attempts"
    )
    assert (
        output.evidence_payload["short_squeeze_risk"][
            "owner_confirm_each_entry_required"
        ]
        is False
    )
    candidate_semantics = StrategyCandidateSemantics.model_validate(
        output.evidence_payload["candidate_semantics"]
    )
    assert candidate_semantics.archetype == StrategyArchetype.BEAR_RALLY_FAILURE
    assert candidate_semantics.payoff_profile == StrategyPayoffProfile.RIGHT_TAIL
    assert candidate_semantics.entry.kind == EntrySetupKind.RALLY_FAILURE
    assert candidate_semantics.entry.side == "short"
    assert candidate_semantics.entry.entry_price_reference == Decimal("106")
    assert candidate_semantics.protection.stop_price_reference == Decimal("114")
    assert candidate_semantics.exit.plan_kind == ExitPlanKind.PARTIAL_TP_PLUS_RUNNER
    assert candidate_semantics.exit.runner is not None
    assert candidate_semantics.exit.runner.preserve_right_tail is True
    assert "short_side_conservative_profile_required" in candidate_semantics.quality.warnings
    assert output.not_order is True
    assert output.not_execution_intent is True
    assert not _contains_forbidden_key(output.model_dump(mode="json"))

    runtime = _runtime()
    context = build_strategy_evaluation_context(signal_input, output=output, runtime=runtime)
    brf = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
    )
    fact_check = brf.fact_check(context)

    assert context.facts["short_squeeze_risk"].status == FactAvailabilityStatus.AVAILABLE
    assert fact_check.status == StrategyFactCheckStatus.PASS

    candidate = await StrategySemanticsShadowBindingService(
        shadow_service=_FakeShadowService()
    ).create_semantic_order_candidate_from_strategy_signal_pair(
        signal_input,
        output,
        runtime=runtime,
        intended_notional=Decimal("10"),
        entry_price_reference=Decimal("106"),
        stop_price_reference=Decimal("114"),
        max_loss_reference=Decimal("3"),
        leverage=Decimal("1"),
    )

    assert candidate.not_order is True
    assert candidate.not_execution_intent is True
    assert candidate.candidate_executable is False
    assert candidate.side == "short"
    assert candidate.metadata["adapter_scope"] == "b0_shadow_only"
    assert candidate.metadata["fact_check"]["status"] == "PASS"


def test_brf_evaluator_invalid_without_closed_candle_context():
    signal_input = _signal_input(one_hour=[], four_hour=_down_context_4h())
    output = BRF001PriceActionEvaluator().evaluate(signal_input)

    assert output.signal_type == SignalType.INVALID
    assert output.side == SignalSide.NONE
    assert "brf_invalid_insufficient_1h_candles" in output.reason_codes
    assert output.not_order is True
    assert output.not_execution_intent is True


def test_brf_evaluator_no_action_when_rejection_not_confirmed():
    signal_input = _signal_input(
        one_hour=_no_rejection_1h(),
        four_hour=_down_context_4h(),
    )
    output = BRF001PriceActionEvaluator().evaluate(signal_input)

    assert output.signal_type == SignalType.NO_ACTION
    assert output.side == SignalSide.NONE
    assert "brf_no_action_no_rejection_close" in output.reason_codes
    assert output.evidence_payload["short_squeeze_risk"]["status"] == "reviewed"
    assert output.not_order is True
    assert output.not_execution_intent is True


def test_brf_evaluator_rejects_wrong_family():
    signal_input = _signal_input(
        family_id="CPM-RO-001",
        version_id="CPM-RO-001-v0",
        one_hour=_bear_rally_failure_1h(),
        four_hour=_down_context_4h(),
    )
    output = BRF001PriceActionEvaluator().evaluate(signal_input)

    assert output.signal_type == SignalType.INVALID
    assert output.strategy_family_id == "BRF-001"
    assert "brf_invalid_wrong_family" in output.reason_codes


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).strip().lower() in FORBIDDEN_EXECUTION_FIELDS
            or _contains_forbidden_key(nested)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False
