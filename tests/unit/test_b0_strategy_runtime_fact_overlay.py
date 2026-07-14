from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.runtime_execution_planning_service import (
    RuntimeExecutionPlanningService,
)
from src.application.runtime_final_gate_preview_service import (
    RuntimeFinalGatePreviewService,
)
from src.application.runtime_strategy_signal_planning_service import (
    RuntimeStrategySignalPlanningService,
)
from src.application.strategy_evaluation_context_builder import (
    build_strategy_evaluation_context,
)
from src.application.strategy_runtime_fact_overlay_service import (
    StrategyRuntimeMarketFacts,
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
from src.domain.models import AccountSnapshot, Direction, Position
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
from src.domain.strategy_semantics import (
    FactAvailabilityStatus,
    StrategyFactCheckStatus,
    initial_strategy_semantics_catalog,
)


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


def _signal_input(
    *,
    family_id: str = "CPM-RO-001",
    version_id: str = "CPM-RO-001-v0",
    account_status: str = "normal",
    position_open_order_summary: dict | None = None,
) -> StrategyFamilySignalInput:
    return StrategyFamilySignalInput(
        evaluation_id="eval-cpm-runtime-fact-overlay",
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
            source="unit_market_read_only",
            freshness="fresh",
            last_price=Decimal("2525"),
            mark_price=Decimal("2525"),
            funding_rate=Decimal("0.0001"),
            volatility=Decimal("0.15"),
            atr=Decimal("25"),
            timeframe="1h",
            candle_context={
                "windows": {"1h": _candles(25), "4h": _candles(12)},
                "closed_bar": True,
            },
        ),
        account_facts_snapshot=AccountFactsSnapshot(
            source="unit_account_read_only",
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
            read_only_provider="unit_test",
            limitations=[],
        ),
        position_open_order_summary=position_open_order_summary
        if position_open_order_summary is not None
        else {"position_count": 0, "open_order_count": 0},
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


def _output() -> StrategyFamilySignalOutput:
    return StrategyFamilySignalOutput(
        signal_id="signal-cpm-runtime-fact-overlay",
        evaluation_id="eval-cpm-runtime-fact-overlay",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        trigger_candle_close_time_ms=NOW_MS,
        timeframe="1h",
        signal_type=SignalType.WOULD_ENTER,
        side=SignalSide.LONG,
        confidence=Decimal("0.7"),
        reason_codes=["price_action_closed_bar"],
        human_summary="CPM runtime fact overlay unit signal.",
        required_execution_mode="observe_only",
        evidence_payload={"price_action_structure": {"pullback_reclaim": True}},
    )


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-cpm-fact-overlay",
        trial_binding_id="trial-cpm-fact-overlay",
        admission_decision_id="admission-cpm-fact-overlay",
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


class _PositionSource:
    def __init__(self, positions: list[Position] | None = None) -> None:
        self.positions = positions or []
        self.calls: list[dict] = []

    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        self.calls.append({"symbol": symbol, "limit": limit})
        return list(self.positions)


class _MarketFactSource:
    def __init__(self, facts: StrategyRuntimeMarketFacts) -> None:
        self.facts = facts
        self.calls: list[dict] = []

    async def read_strategy_market_facts(
        self,
        *,
        symbol: str,
        generated_at_ms: int,
    ) -> StrategyRuntimeMarketFacts:
        self.calls.append({"symbol": symbol, "generated_at_ms": generated_at_ms})
        return self.facts


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
        self.evaluation = SignalEvaluation(
            signal_evaluation_id="signal-eval-runtime-fact-overlay",
            runtime_instance_id=getattr(runtime, "runtime_instance_id", None),
            trial_binding_id=getattr(runtime, "trial_binding_id", None),
            strategy_family_id=output.strategy_family_id,
            strategy_family_version_id=output.strategy_family_version_id,
            source_signal_id=output.signal_id,
            symbol=output.symbol,
            side=output.side.value,
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
            order_candidate_id="order-candidate-runtime-fact-overlay",
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


def _planning_service(
    *,
    overlay: StrategyRuntimeFactOverlayService,
    final_gate_positions: list[Position] | None = None,
    store: _ShadowAndCandidateStore | None = None,
    runtime: StrategyRuntimeInstance | None = None,
) -> RuntimeStrategySignalPlanningService:
    runtime = runtime or _runtime()
    store = store or _ShadowAndCandidateStore()

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == runtime.runtime_instance_id
            return runtime

    class _FinalGatePositionSource:
        async def list_active(self, *, symbol: str | None = None, limit: int = 100):
            assert symbol == runtime.symbol
            assert limit == 100
            return list(final_gate_positions or [])

    final_gate = RuntimeFinalGatePreviewService(
        runtime_service=_RuntimeService(),
        signal_evaluation_service=store,
        active_position_source=_FinalGatePositionSource(),
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
        runtime_fact_overlay_service=overlay,
    )


async def test_overlay_replaces_caller_supplied_position_count_with_trusted_projection():
    position_source = _PositionSource(positions=[])
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=position_source,
        account_facts_source=_ready_account_source(),
    )

    result = await overlay.apply(
        _signal_input(
            account_status="not_checked",
            position_open_order_summary={"active_positions_count": 99, "position_count": 99},
        ),
        output=_output(),
        runtime=_runtime(),
    )
    context = build_strategy_evaluation_context(
        result.signal_input,
        output=_output(),
        runtime=_runtime(),
    )
    cpm = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
    )

    assert result.blockers == []
    assert position_source.calls == [{"symbol": "ETH/USDT:USDT", "limit": 100}]
    assert result.signal_input.position_open_order_summary["active_positions_count"] == 0
    assert result.signal_input.position_open_order_summary[
        "caller_supplied_active_position_count_used"
    ] is False
    assert context.facts["account_facts"].status == FactAvailabilityStatus.AVAILABLE
    assert context.facts["position_projection"].status == FactAvailabilityStatus.AVAILABLE
    assert cpm.fact_check(context).status == StrategyFactCheckStatus.PASS


async def test_overlay_injects_trusted_market_facts_for_fco_required_facts():
    market_source = _MarketFactSource(
        StrategyRuntimeMarketFacts(
            source_id="unit_derivative_market_facts",
            timestamp_ms=NOW_MS,
            freshness="fresh",
            funding_rate=Decimal("0.0002"),
            next_funding_time_ms=NOW_MS + 28_800_000,
            open_interest=Decimal("12345.67"),
            open_interest_notional=Decimal("1300000"),
            open_interest_change_pct=Decimal("1.25"),
            crowding_proxy={
                "status": "defined",
                "long_short_ratio": "1.8",
                "crowded_side": "long",
                "definition": "unit_test_derivative_market_context",
            },
            read_only_guarantee=True,
            external_call_type="read_only_derivatives_snapshot",
        )
    )
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=_PositionSource(positions=[]),
        account_facts_source=_ready_account_source(),
        market_fact_source=market_source,
        require_trusted_market_fact_source=True,
    )

    result = await overlay.apply(
        _signal_input(family_id="FCO-001", version_id="FCO-001-v0"),
    )
    context = build_strategy_evaluation_context(result.signal_input)
    fco = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id="FCO-001",
        strategy_family_version_id="FCO-001-v0",
    )
    fact_check = fco.fact_check(context)

    assert result.blockers == []
    assert market_source.calls == [
        {"symbol": "ETH/USDT:USDT", "generated_at_ms": NOW_MS}
    ]
    assert result.signal_input.market_snapshot.funding_rate == Decimal("0.0002")
    assert context.facts["funding_rate"].status == FactAvailabilityStatus.AVAILABLE
    assert context.facts["open_interest"].status == FactAvailabilityStatus.AVAILABLE
    assert context.facts["crowding_proxy"].status == FactAvailabilityStatus.AVAILABLE
    assert fact_check.status == StrategyFactCheckStatus.PASS
    assert (
        context.facts["open_interest"].value_snapshot["value"]["open_interest"]
        == "12345.67"
    )
    assert (
        context.facts["crowding_proxy"].value_snapshot["value"]["status"]
        == "defined"
    )


async def test_overlay_fails_closed_when_required_market_fact_source_is_missing():
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=_PositionSource(positions=[]),
        account_facts_source=_ready_account_source(),
        market_fact_source=None,
        require_trusted_market_fact_source=True,
    )
    signal_input = _signal_input(family_id="FCO-001", version_id="FCO-001-v0")
    signal_input.market_snapshot.candle_context["market_facts"] = {
        "open_interest": {"open_interest": "999"},
        "crowding_proxy": {"status": "caller_supplied"},
    }

    result = await overlay.apply(signal_input)
    context = build_strategy_evaluation_context(result.signal_input)
    fco = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id="FCO-001",
        strategy_family_version_id="FCO-001-v0",
    )
    fact_check = fco.fact_check(context)

    assert "trusted_market_fact_source_unavailable" in result.blockers
    assert result.signal_input.market_snapshot.funding_rate is None
    assert "market_facts" not in result.signal_input.market_snapshot.candle_context
    assert context.facts["funding_rate"].status == FactAvailabilityStatus.MISSING
    assert context.facts["open_interest"].status == FactAvailabilityStatus.MISSING
    assert context.facts["crowding_proxy"].status == FactAvailabilityStatus.MISSING
    assert fact_check.status == StrategyFactCheckStatus.BLOCK_MISSING_FACTS
    assert set(fact_check.missing_facts) == {
        "funding_rate",
        "open_interest",
        "crowding_proxy",
    }


async def test_overlay_marks_stale_market_facts_as_stale_required_facts():
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=_PositionSource(positions=[]),
        account_facts_source=_ready_account_source(),
        market_fact_source=_MarketFactSource(
            StrategyRuntimeMarketFacts(
                source_id="unit_derivative_market_facts",
                timestamp_ms=NOW_MS - 86_400_000,
                freshness="stale",
                funding_rate=Decimal("0.0002"),
                open_interest=Decimal("12345.67"),
                crowding_proxy={"status": "defined"},
                read_only_guarantee=True,
            )
        ),
        require_trusted_market_fact_source=True,
    )

    result = await overlay.apply(
        _signal_input(family_id="FCO-001", version_id="FCO-001-v0"),
    )
    context = build_strategy_evaluation_context(result.signal_input)
    fco = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id="FCO-001",
        strategy_family_version_id="FCO-001-v0",
    )
    fact_check = fco.fact_check(context)

    assert result.blockers == []
    assert context.facts["funding_rate"].status == FactAvailabilityStatus.STALE
    assert context.facts["open_interest"].status == FactAvailabilityStatus.STALE
    assert context.facts["crowding_proxy"].status == FactAvailabilityStatus.STALE
    assert fact_check.status == StrategyFactCheckStatus.BLOCK_STALE_DATA
    assert set(fact_check.stale_facts) == {
        "funding_rate",
        "open_interest",
        "crowding_proxy",
    }


async def test_overlay_fails_closed_when_trusted_position_source_is_missing():
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=None,
        account_facts_source=_ready_account_source(),
    )

    result = await overlay.apply(_signal_input(), output=_output(), runtime=_runtime())
    context = build_strategy_evaluation_context(
        result.signal_input,
        output=_output(),
        runtime=_runtime(),
    )
    cpm = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
    )
    fact_check = cpm.fact_check(context)

    assert "trusted_position_projection_source_unavailable" in result.blockers
    assert context.facts["position_projection"].status == FactAvailabilityStatus.MISSING
    assert fact_check.status == StrategyFactCheckStatus.BLOCK_MISSING_FACTS
    assert "position_projection" in fact_check.missing_facts


async def test_strategy_signal_planning_uses_overlay_before_runtime_draft_without_execution():
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=_PositionSource(positions=[]),
        account_facts_source=_ready_account_source(),
    )
    draft = await _planning_service(overlay=overlay).intent_draft_for_strategy_signal_pair(
        _signal_input(
            account_status="not_checked",
            position_open_order_summary={"active_positions_count": 99, "position_count": 99},
        ),
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

    assert draft.status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
    assert draft.execution_intent_created is False
    assert draft.order_created is False
    assert draft.exchange_called is False


async def test_strategy_signal_planning_blocks_before_candidate_when_overlay_account_missing():
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=_PositionSource(positions=[]),
        account_facts_source=None,
    )
    service = _planning_service(overlay=overlay)

    with pytest.raises(StrategySemanticsBindingError, match="BLOCK_MISSING_FACTS"):
        await service.intent_draft_for_strategy_signal_pair(
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
        )


async def test_strategy_signal_planning_requires_trusted_market_facts_from_required_facts():
    store = _ShadowAndCandidateStore()
    overlay = StrategyRuntimeFactOverlayService(
        active_position_source=_PositionSource(positions=[]),
        account_facts_source=_ready_account_source(),
        market_fact_source=None,
    )
    signal_input = _signal_input(family_id="FCO-001", version_id="FCO-001-v0")
    signal_input.market_snapshot.candle_context["market_facts"] = {
        "open_interest": {"open_interest": "999"},
        "crowding_proxy": {"status": "caller_supplied"},
    }
    output = StrategyFamilySignalOutput(
        signal_id="signal-fco-runtime-required-market-facts",
        evaluation_id=signal_input.evaluation_id,
        strategy_family_id="FCO-001",
        strategy_family_version_id="FCO-001-v0",
        symbol=signal_input.symbol,
        timestamp_ms=NOW_MS,
        trigger_candle_close_time_ms=NOW_MS,
        timeframe="1h",
        signal_type=SignalType.WOULD_ENTER,
        side=SignalSide.LONG,
        confidence=Decimal("0.6"),
        reason_codes=["funding_oi_crowding_review"],
        human_summary="FCO required market facts must come from trusted overlay.",
        required_execution_mode="observe_only",
        evidence_payload={"market_facts": {"status": "caller_supplied"}},
    )
    runtime = _runtime().model_copy(
        update={
            "runtime_instance_id": "runtime-fco-required-market-facts",
            "trial_binding_id": "trial-fco-required-market-facts",
            "admission_decision_id": "admission-fco-required-market-facts",
            "strategy_family_id": "FCO-001",
            "strategy_family_version_id": "FCO-001-v0",
            "side": "long",
        },
        deep=True,
    )
    service = _planning_service(overlay=overlay, store=store, runtime=runtime)

    with pytest.raises(StrategySemanticsBindingError, match="data_backlog_only"):
        await service.intent_draft_for_strategy_signal_pair(
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

    assert store.candidate is None
    assert store.evaluation is not None
    overlay_metadata = store.evaluation.metadata["trusted_runtime_fact_overlay"]
    market_overlay = overlay_metadata["metadata"]["market_fact_overlay"]
    assert overlay_metadata["blockers"] == ["trusted_market_fact_source_unavailable"]
    assert market_overlay["required_by_strategy_semantics"] is True
    assert market_overlay["required_keys"] == [
        "funding_rate",
        "open_interest",
        "crowding_proxy",
    ]
    assert store.evaluation.metadata["strategy_required_trusted_market_facts"] == [
        "funding_rate",
        "open_interest",
        "crowding_proxy",
    ]


async def test_trading_console_factory_wires_trusted_runtime_fact_overlay(monkeypatch):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    class _PlanningService:
        pass

    class _ShadowService:
        pass

    position_source = _PositionSource(positions=[])
    monkeypatch.setattr(api_module, "_runtime_strategy_signal_planning_service", None, raising=False)
    monkeypatch.setattr(api_module, "_runtime_execution_planning_service", _PlanningService(), raising=False)
    monkeypatch.setattr(api_module, "_signal_evaluation_shadow_service", _ShadowService(), raising=False)
    monkeypatch.setattr(api_module, "_position_repo", position_source, raising=False)
    monkeypatch.setattr(
        api_module,
        "_account_getter",
        lambda: AccountSnapshot(
            total_balance=Decimal("30"),
            available_balance=Decimal("29"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=NOW_MS,
        ),
        raising=False,
    )

    service = await api_trading_console._runtime_strategy_signal_planning_service()
    overlay = service._runtime_fact_overlay_service
    result = await overlay.apply(_signal_input(), output=_output(), runtime=_runtime())

    assert overlay is not None
    assert result.blockers == []
    assert result.signal_input.position_open_order_summary["active_positions_count"] == 0
    assert result.signal_input.account_facts_snapshot.source == "cached_snapshot"
    assert result.signal_input.account_facts_snapshot.available_balance == Decimal("29")
    assert overlay._market_fact_source is None


async def test_trading_console_factory_can_enable_public_market_fact_source(monkeypatch):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    class _PlanningService:
        pass

    class _ShadowService:
        pass

    monkeypatch.setenv("TRADING_CONSOLE_PUBLIC_MARKET_FACTS_ENABLED", "true")
    monkeypatch.setattr(api_module, "_runtime_strategy_signal_planning_service", None, raising=False)
    monkeypatch.setattr(api_module, "_runtime_execution_planning_service", _PlanningService(), raising=False)
    monkeypatch.setattr(api_module, "_signal_evaluation_shadow_service", _ShadowService(), raising=False)
    monkeypatch.setattr(api_module, "_position_repo", _PositionSource(positions=[]), raising=False)
    monkeypatch.setattr(
        api_module,
        "_account_getter",
        lambda: AccountSnapshot(
            total_balance=Decimal("30"),
            available_balance=Decimal("29"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=NOW_MS,
        ),
        raising=False,
    )

    service = await api_trading_console._runtime_strategy_signal_planning_service()
    overlay = service._runtime_fact_overlay_service

    assert overlay._market_fact_source is not None
    assert (
        overlay._market_fact_source.source_id
        == "binance_usdm_derivative_market_facts_read_only"
    )
    assert overlay._market_fact_source.is_live_read_only is True


async def test_trading_console_factory_can_use_live_read_only_account_facts(monkeypatch):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    class _PlanningService:
        pass

    class _ShadowService:
        pass

    class _ReadOnlyGateway:
        def __init__(self) -> None:
            self.fetch_balance_calls = 0

        async def fetch_account_balance(self):
            self.fetch_balance_calls += 1
            return AccountSnapshot(
                total_balance=Decimal("30"),
                available_balance=Decimal("28.5"),
                unrealized_pnl=Decimal("0"),
                positions=[],
                timestamp=NOW_MS,
            )

    gateway = _ReadOnlyGateway()
    monkeypatch.setenv("TRADING_CONSOLE_RUNTIME_ACCOUNT_FACTS_SOURCE", "live_read_only")
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "read_only")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("EXCHANGE_API_KEY", "unit-key")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "unit-secret")
    monkeypatch.setattr(api_module, "_runtime_strategy_signal_planning_service", None, raising=False)
    monkeypatch.setattr(api_module, "_runtime_execution_planning_service", _PlanningService(), raising=False)
    monkeypatch.setattr(api_module, "_signal_evaluation_shadow_service", _ShadowService(), raising=False)
    monkeypatch.setattr(api_module, "_position_repo", _PositionSource(positions=[]), raising=False)
    monkeypatch.setattr(
        api_module,
        "_trading_console_read_only_exchange_gateway",
        gateway,
        raising=False,
    )

    service = await api_trading_console._runtime_strategy_signal_planning_service()
    overlay = service._runtime_fact_overlay_service
    result = await overlay.apply(_signal_input(), output=_output(), runtime=_runtime())

    assert result.blockers == []
    assert gateway.fetch_balance_calls == 1
    assert (
        result.signal_input.account_facts_snapshot.source
        == "binance_usdt_futures_read_only"
    )
    assert result.signal_input.account_facts_snapshot.freshness == "fresh"
    assert result.signal_input.account_facts_snapshot.available_balance == Decimal("28.5")
    assert overlay._market_fact_source is None
