from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.signal_evaluation_shadow_service import SignalEvaluationShadowService
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
from src.domain.strategy_semantics import (
    FactAvailabilityStatus,
    MarketState,
    StrategyCandidateMode,
    StrategyEvaluationContext,
    StrategyFactCheckStatus,
    StrategyFactSnapshot,
    StrategyRuntimeConfirmationMode,
    initial_strategy_semantics_catalog,
)
from src.domain.strategy_family_signal import (
    SignalSide,
    SignalType,
    StrategyFamilySignalOutput,
)
from src.infrastructure.pg_models import PGOrderCandidateORM, PGSignalEvaluationORM
from src.infrastructure.pg_signal_evaluation_repository import PgSignalEvaluationRepository


NOW_MS = 1781000000000


def _evaluation(
    *,
    family_id: str = "BRF-001",
    version_id: str = "BRF-001-v0",
    side: str = "short",
) -> SignalEvaluation:
    return SignalEvaluation(
        signal_evaluation_id="signal-eval-b0",
        runtime_instance_id="runtime-b0",
        trial_binding_id="trial-binding-b0",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        source_signal_id="source-signal-b0",
        symbol="ETH/USDT:USDT",
        side=side,
        status=SignalEvaluationStatus.EVALUATED,
        decision=(
            SignalEvaluationDecision.CANDIDATE
            if side in {"long", "short"}
            else SignalEvaluationDecision.NO_ACTION
        ),
        reason_codes=["b0_unit_test"],
        rationale="B0 strategy semantics unit test",
        evaluated_at_ms=NOW_MS,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _fact(fact_key: str, *, stale: bool = False) -> StrategyFactSnapshot:
    return StrategyFactSnapshot(
        fact_key=fact_key,
        source="unit_test",
        observed_at_ms=NOW_MS,
        status=FactAvailabilityStatus.STALE if stale else FactAvailabilityStatus.AVAILABLE,
        freshness_ms=999999 if stale else 100,
        evidence_ref=f"unit:{fact_key}",
    )


def _context(
    *,
    family_id: str = "BRF-001",
    version_id: str = "BRF-001-v0",
    side: str = "short",
    omit: set[str] | None = None,
    stale: set[str] | None = None,
) -> StrategyEvaluationContext:
    omit = omit or set()
    stale = stale or set()
    keys = {
        "ohlcv_1h",
        "ohlcv_4h",
        "price_action_structure",
        "account_facts",
        "runtime_boundary",
        "position_projection",
        "short_squeeze_risk",
    }
    facts = {
        key: _fact(key, stale=key in stale)
        for key in keys
        if key not in omit
    }
    return StrategyEvaluationContext(
        context_id="strategy-context-b0",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        side=side,
        evaluated_at_ms=NOW_MS,
        facts=facts,
        market_state=MarketState.TREND_DOWN,
    )


class _FakeShadowService:
    def __init__(self, evaluation: SignalEvaluation) -> None:
        self.evaluation = evaluation
        self.created_kwargs: dict | None = None
        self.created_evaluation_output: StrategyFamilySignalOutput | None = None

    async def create_signal_evaluation_from_strategy_family_output(
        self,
        output: StrategyFamilySignalOutput,
        *,
        runtime=None,
        metadata=None,
    ) -> SignalEvaluation:
        self.created_evaluation_output = output
        side = "none" if output.side == SignalSide.NONE else output.side.value
        self.evaluation = SignalEvaluation(
            signal_evaluation_id="signal-eval-from-output",
            runtime_instance_id=getattr(runtime, "runtime_instance_id", self.evaluation.runtime_instance_id),
            trial_binding_id=getattr(runtime, "trial_binding_id", self.evaluation.trial_binding_id),
            strategy_family_id=output.strategy_family_id,
            strategy_family_version_id=output.strategy_family_version_id,
            source_signal_id=output.signal_id,
            symbol=output.symbol,
            side=side,
            status=SignalEvaluationStatus.EVALUATED,
            decision=(
                SignalEvaluationDecision.CANDIDATE
                if side in {"long", "short"}
                else SignalEvaluationDecision.NO_ACTION
            ),
            reason_codes=list(output.reason_codes),
            rationale=output.human_summary,
            evidence_snapshot=output.model_dump(mode="json"),
            policy_snapshot={
                "required_execution_mode": output.required_execution_mode,
            },
            evaluated_at_ms=NOW_MS,
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
            metadata=metadata or {},
        )
        return self.evaluation

    async def get_signal_evaluation(self, signal_evaluation_id: str) -> SignalEvaluation:
        assert signal_evaluation_id == self.evaluation.signal_evaluation_id
        return self.evaluation

    async def create_order_candidate_from_signal_evaluation(self, signal_evaluation_id: str, **kwargs):
        self.created_kwargs = kwargs
        return OrderCandidate(
            order_candidate_id="order-candidate-b0",
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
            rationale=kwargs.get("rationale") or self.evaluation.rationale,
            evidence_refs=kwargs["evidence_refs"],
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
            expires_at_ms=kwargs.get("expires_at_ms"),
            metadata=kwargs["metadata"],
        )


def _strategy_output(
    *,
    family_id: str = "CPM-RO-001",
    version_id: str = "CPM-RO-001-v0",
    signal_type: SignalType = SignalType.WOULD_ENTER,
    side: SignalSide = SignalSide.LONG,
) -> StrategyFamilySignalOutput:
    return StrategyFamilySignalOutput(
        signal_id="strategy-signal-b0",
        evaluation_id="strategy-output-eval-b0",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        timeframe="1h",
        signal_type=signal_type,
        side=side,
        confidence=Decimal("0.7"),
        reason_codes=["b0_strategy_output"],
        human_summary="B0 strategy output unit test",
        required_execution_mode="observe_only",
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


def test_initial_catalog_separates_semantic_reference_and_execution_approval():
    catalog = initial_strategy_semantics_catalog()
    cpm = catalog.get_binding(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
    )
    brf = catalog.get_binding(
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
    )
    rmr = catalog.get_binding(
        strategy_family_id="RMR-001",
        strategy_family_version_id="RMR-001-v0",
    )
    fco = catalog.get_binding(
        strategy_family_id="FCO-001",
        strategy_family_version_id="FCO-001-v0",
    )

    assert cpm.canonical_family_id == "CPM-001"
    assert cpm.proven_alpha is False
    assert cpm.reference_implementation is True
    assert cpm.allows_shadow_order_candidate is True
    assert cpm.supported_sides == ["long"]

    assert brf.allows_shadow_order_candidate is True
    assert brf.supported_sides == ["short"]
    assert brf.protection_policy.mandatory is True
    assert (
        brf.runtime_confirmation_mode
        == StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
    )
    assert brf.owner_confirm_each_entry_required is False
    assert brf.metadata["short_side_conservative_profile_required"] is True
    assert "per-entry Owner confirmation" in brf.metadata["runtime_confirmation_note"]

    assert rmr.candidate_mode == StrategyCandidateMode.REGIME_CLASSIFIER_ONLY
    assert rmr.allows_shadow_order_candidate is False
    assert rmr.runtime_confirmation_mode == StrategyRuntimeConfirmationMode.OBSERVE_ONLY
    assert rmr.metadata["must_not_hard_filter_before_review"] is True

    assert fco.candidate_mode == StrategyCandidateMode.DATA_BACKLOG_ONLY
    assert fco.allows_shadow_order_candidate is False
    assert (
        fco.runtime_confirmation_mode
        == StrategyRuntimeConfirmationMode.DATA_BACKLOG_ONLY
    )
    assert fco.metadata["data_dependency_backlog"] is True


def test_required_facts_block_missing_and_stale_core_price_action_facts():
    catalog = initial_strategy_semantics_catalog()
    brf = catalog.get_binding(
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
    )

    missing_result = brf.fact_check(_context(omit={"ohlcv_4h"}))
    stale_result = brf.fact_check(_context(stale={"account_facts"}))

    assert missing_result.status == StrategyFactCheckStatus.BLOCK_MISSING_FACTS
    assert missing_result.missing_facts == ["ohlcv_4h"]
    assert "ohlcv_4h_missing" in missing_result.reason_codes

    assert stale_result.status == StrategyFactCheckStatus.BLOCK_STALE_DATA
    assert stale_result.stale_facts == ["account_facts"]
    assert "account_facts_stale" in stale_result.reason_codes


def test_brf_semantics_can_create_non_executing_shadow_order_candidate():
    evaluation = _evaluation()
    fake_shadow = _FakeShadowService(evaluation)
    service = StrategySemanticsShadowBindingService(shadow_service=fake_shadow)

    async def _run() -> OrderCandidate:
        return await service.create_semantic_order_candidate(
            signal_evaluation_id=evaluation.signal_evaluation_id,
            context=_context(),
            proposed_quantity=Decimal("0.01"),
            intended_notional=Decimal("10"),
            entry_price_reference=Decimal("1680"),
            stop_price_reference=Decimal("1725"),
            max_loss_reference=Decimal("3"),
            leverage=Decimal("1"),
            take_profit_references=[
                {"kind": "partial_tp", "rr": "1", "position_ratio": "0.5"},
                {"kind": "runner", "policy": "trailing_atr"},
            ],
        )

    candidate = asyncio.run(_run())

    assert candidate.not_order is True
    assert candidate.not_execution_intent is True
    assert candidate.candidate_executable is False
    assert candidate.side == "short"
    assert candidate.candidate_order_type == "market"
    assert candidate.risk_preview.intended_notional == Decimal("10")
    assert candidate.risk_preview.max_loss_reference == Decimal("3")
    assert candidate.protection_preview.requires_protection is True
    assert candidate.protection_preview.stop_price_reference == Decimal("1725")
    assert candidate.metadata["adapter_scope"] == "b0_shadow_only"
    assert candidate.metadata["strategy_semantics"]["canonical_family_id"] == "BRF-001"
    assert (
        candidate.metadata["strategy_semantics"]["runtime_confirmation_mode"]
        == "runtime_bounded_auto_attempts"
    )
    assert candidate.metadata["strategy_semantics"]["proven_alpha"] is False
    assert "MFE" in candidate.metadata["right_tail_review_metrics"]
    assert "runner_capped_too_early" in candidate.metadata["right_tail_review_metrics"]


async def test_binding_rejects_rmr_classifier_as_order_candidate():
    evaluation = _evaluation(
        family_id="RMR-001",
        version_id="RMR-001-v0",
        side="none",
    )
    service = StrategySemanticsShadowBindingService(
        shadow_service=_FakeShadowService(evaluation)
    )

    with pytest.raises(StrategySemanticsBindingError, match="not order-candidate eligible"):
        await service.create_semantic_order_candidate(
            signal_evaluation_id=evaluation.signal_evaluation_id,
            context=StrategyEvaluationContext(
                context_id="rmr-context",
                strategy_family_id="RMR-001",
                strategy_family_version_id="RMR-001-v0",
                symbol="ETH/USDT:USDT",
                side="none",
                evaluated_at_ms=NOW_MS,
                facts={
                    "ohlcv_1h": _fact("ohlcv_1h"),
                    "ohlcv_4h": _fact("ohlcv_4h"),
                    "range_structure": _fact("range_structure"),
                    "volatility_state": _fact("volatility_state"),
                },
                market_state=MarketState.CHOP,
            ),
            stop_price_reference=Decimal("0"),
        )


async def test_binding_requires_concrete_stop_before_shadow_candidate():
    evaluation = _evaluation()
    service = StrategySemanticsShadowBindingService(
        shadow_service=_FakeShadowService(evaluation)
    )

    with pytest.raises(StrategySemanticsBindingError, match="concrete stop price"):
        await service.create_semantic_order_candidate(
            signal_evaluation_id=evaluation.signal_evaluation_id,
            context=_context(),
            intended_notional=Decimal("10"),
        )


async def test_cpm_strategy_output_can_flow_to_semantic_shadow_candidate():
    fake_shadow = _FakeShadowService(
        _evaluation(
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            side="long",
        )
    )
    service = StrategySemanticsShadowBindingService(shadow_service=fake_shadow)

    candidate = await service.create_semantic_order_candidate_from_strategy_output(
        _strategy_output(),
        context=_context(
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            side="long",
        ),
        proposed_quantity=Decimal("0.004"),
        intended_notional=Decimal("10"),
        entry_price_reference=Decimal("2500"),
        stop_price_reference=Decimal("2425"),
        max_loss_reference=Decimal("3"),
        leverage=Decimal("1"),
        take_profit_references=[
            {"kind": "partial_tp", "rr": "1", "position_ratio": "0.5"},
            {"kind": "runner", "policy": "trailing_atr"},
        ],
    )

    assert fake_shadow.created_evaluation_output is not None
    assert candidate.not_order is True
    assert candidate.not_execution_intent is True
    assert candidate.strategy_family_id == "CPM-RO-001"
    assert candidate.strategy_family_version_id == "CPM-RO-001-v0"
    assert candidate.side == "long"
    assert candidate.metadata["source_strategy_signal_id"] == "strategy-signal-b0"
    assert candidate.metadata["strategy_semantics"]["canonical_family_id"] == "CPM-001"
    assert candidate.metadata["source_strategy_required_execution_mode"] == "observe_only"
    assert candidate.protection_preview.stop_price_reference == Decimal("2425")


async def test_cpm_short_strategy_output_is_rejected_by_long_only_semantics():
    fake_shadow = _FakeShadowService(
        _evaluation(
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            side="short",
        )
    )
    service = StrategySemanticsShadowBindingService(shadow_service=fake_shadow)

    with pytest.raises(StrategySemanticsBindingError, match="not supported"):
        await service.create_semantic_order_candidate_from_strategy_output(
            _strategy_output(side=SignalSide.SHORT),
            context=_context(
                family_id="CPM-RO-001",
                version_id="CPM-RO-001-v0",
                side="short",
            ),
            stop_price_reference=Decimal("2600"),
        )


async def test_non_entry_strategy_output_cannot_create_shadow_candidate():
    fake_shadow = _FakeShadowService(
        _evaluation(
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            side="long",
        )
    )
    service = StrategySemanticsShadowBindingService(shadow_service=fake_shadow)

    with pytest.raises(StrategySemanticsBindingError, match="only WOULD_ENTER"):
        await service.create_semantic_order_candidate_from_strategy_output(
            _strategy_output(signal_type=SignalType.NO_ACTION, side=SignalSide.NONE),
            context=_context(
                family_id="CPM-RO-001",
                version_id="CPM-RO-001-v0",
                side="none",
            ),
            stop_price_reference=Decimal("2425"),
        )


async def test_strategy_output_binding_works_with_real_shadow_repository():
    engine, session_maker = await _repo_engine(
        PGSignalEvaluationORM.__table__,
        PGOrderCandidateORM.__table__,
    )
    shadow_service = SignalEvaluationShadowService(
        repository=PgSignalEvaluationRepository(session_maker=session_maker)
    )
    service = StrategySemanticsShadowBindingService(shadow_service=shadow_service)
    try:
        candidate = await service.create_semantic_order_candidate_from_strategy_output(
            _strategy_output(),
            context=_context(
                family_id="CPM-RO-001",
                version_id="CPM-RO-001-v0",
                side="long",
            ),
            proposed_quantity=Decimal("0.004"),
            intended_notional=Decimal("10"),
            entry_price_reference=Decimal("2500"),
            stop_price_reference=Decimal("2425"),
            max_loss_reference=Decimal("3"),
            leverage=Decimal("1"),
        )
        stored_evaluations = await shadow_service.list_signal_evaluations(
            strategy_family_id="CPM-RO-001"
        )
        stored_candidates = await shadow_service.list_order_candidates(
            signal_evaluation_id=candidate.signal_evaluation_id
        )

        assert len(stored_evaluations) == 1
        assert stored_evaluations[0].source_signal_id == "strategy-signal-b0"
        assert len(stored_candidates) == 1
        assert stored_candidates[0].order_candidate_id == candidate.order_candidate_id
        assert stored_candidates[0].metadata["adapter_scope"] == "b0_shadow_only"
    finally:
        await engine.dispose()
