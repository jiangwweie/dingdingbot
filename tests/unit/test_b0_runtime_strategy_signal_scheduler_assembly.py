from __future__ import annotations

from decimal import Decimal

from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationResult,
    RuntimeStrategySignalEvaluationStatus,
)
from src.application.runtime_strategy_signal_planning_service import (
    RuntimeStrategySignalCandidatePlanningResult,
    RuntimeStrategySignalCandidatePlanningStatus,
)
from src.application.runtime_strategy_signal_scheduler_assembly import (
    RuntimeStrategySignalSchedulerAssemblyService,
    RuntimeStrategySignalSchedulerFactSources,
    RuntimeStrategySignalSchedulerReadinessStatus,
)
from src.application.runtime_strategy_signal_scheduler_planning_service import (
    RuntimeStrategySignalSchedulerPlanningResult,
    RuntimeStrategySignalSchedulerPlanningService,
    RuntimeStrategySignalSchedulerPlanningStatus,
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


NOW_MS = 1781000000000


def _signal_input(
    *,
    family_id: str = "CPM-RO-001",
    version_id: str = "CPM-RO-001-v0",
) -> StrategyFamilySignalInput:
    return StrategyFamilySignalInput(
        evaluation_id=f"eval-scheduler-{family_id}",
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
            last_price=Decimal("2525"),
            mark_price=Decimal("2525"),
            timeframe="1h",
            candle_context={"windows": {"1h": [], "4h": []}, "closed_bar": True},
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
        source="unit_test",
        freshness="fresh",
    )


def _output(
    *,
    family_id: str = "CPM-RO-001",
    version_id: str = "CPM-RO-001-v0",
    signal_type: SignalType = SignalType.WOULD_ENTER,
) -> StrategyFamilySignalOutput:
    return StrategyFamilySignalOutput(
        signal_id=f"signal-scheduler-{family_id}",
        evaluation_id=f"eval-scheduler-{family_id}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        timeframe="1h",
        signal_type=signal_type,
        side=SignalSide.LONG if signal_type == SignalType.WOULD_ENTER else SignalSide.NONE,
        confidence=Decimal("0.7"),
        reason_codes=["scheduler_readiness_unit"],
        human_summary="Scheduler readiness unit signal.",
        required_execution_mode="observe_only",
        evidence_payload={"price_action_structure": {"pullback_reclaim": True}},
    )


def _runtime(
    *,
    family_id: str = "CPM-RO-001",
    version_id: str = "CPM-RO-001-v0",
) -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id=f"runtime-scheduler-{family_id}",
        trial_binding_id=f"trial-scheduler-{family_id}",
        admission_decision_id=f"admission-scheduler-{family_id}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
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


def _ready_sources(*, market: bool = False) -> RuntimeStrategySignalSchedulerFactSources:
    return RuntimeStrategySignalSchedulerFactSources(
        trusted_runtime_fact_overlay_configured=True,
        trusted_active_position_source_available=True,
        trusted_account_facts_source_available=True,
        trusted_market_fact_source_available=market,
        source_scope="unit_trusted_sources",
    )


class _FakeShadowPlanner:
    def __init__(
        self,
        *,
        status: RuntimeStrategySignalCandidatePlanningStatus = (
            RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
        ),
        blockers: list[str] | None = None,
    ) -> None:
        self.status = status
        self.blockers = blockers or []
        self.calls: list[dict] = []

    async def plan_shadow_candidate_from_signal_input(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        runtime: StrategyRuntimeInstance,
        context_builder=None,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeStrategySignalCandidatePlanningResult:
        self.calls.append(
            {
                "evaluation_id": signal_input.evaluation_id,
                "runtime_instance_id": runtime.runtime_instance_id,
                "context_id": context_id,
                "expires_at_ms": expires_at_ms,
                "metadata": metadata or {},
            }
        )
        created = (
            self.status
            == RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
        )
        return RuntimeStrategySignalCandidatePlanningResult(
            planning_id=f"fake-plan-{signal_input.evaluation_id}",
            runtime_instance_id=runtime.runtime_instance_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            symbol=signal_input.symbol,
            status=self.status,
            evaluation_result=RuntimeStrategySignalEvaluationResult(
                evaluation_id=signal_input.evaluation_id,
                strategy_family_id=signal_input.strategy_family_id,
                strategy_family_version_id=signal_input.strategy_family_version_id,
                symbol=signal_input.symbol,
                status=(
                    RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
                ),
                can_call_semantic_binding=True,
            ),
            blockers=list(self.blockers),
            warnings=[],
            signal_evaluation_created=created,
            order_candidate_created=created,
        )


class _FakeSignalEvaluationService:
    def __init__(self, result: RuntimeStrategySignalEvaluationResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> RuntimeStrategySignalEvaluationResult:
        self.calls.append(signal_input.evaluation_id)
        return self.result


def test_scheduler_assembly_blocks_without_runtime_or_trusted_sources():
    readiness = RuntimeStrategySignalSchedulerAssemblyService().preview(
        _signal_input(),
        _output(),
        candidate_id="CPM-RO-001",
    )

    assert readiness.status == RuntimeStrategySignalSchedulerReadinessStatus.BLOCKED
    assert "runtime_instance_required_for_scheduler_planning" in readiness.blockers
    assert "trusted_runtime_fact_overlay_not_configured" in readiness.blockers
    assert "trusted_active_position_source_unavailable" in readiness.blockers
    assert "trusted_account_facts_source_unavailable" in readiness.blockers
    assert readiness.scheduler_can_call_runtime_planner is False
    assert readiness.planner_call_performed is False
    assert readiness.signal_evaluation_created is False
    assert readiness.order_candidate_created is False
    assert readiness.execution_intent_created is False
    assert readiness.order_created is False
    assert readiness.exchange_called is False


def test_scheduler_assembly_can_reach_non_executing_planner_ready_state():
    readiness = RuntimeStrategySignalSchedulerAssemblyService(
        runtime=_runtime(),
        fact_sources=_ready_sources(),
    ).preview(_signal_input(), _output(), candidate_id="CPM-RO-001")

    assert (
        readiness.status
        == RuntimeStrategySignalSchedulerReadinessStatus.READY_FOR_NON_EXECUTING_PLANNER
    )
    assert readiness.blockers == []
    assert readiness.scheduler_can_call_runtime_planner is True
    assert readiness.planner_call_performed is False
    assert readiness.order_candidate_created is False
    assert readiness.execution_intent_created is False
    assert readiness.order_created is False
    assert readiness.order_lifecycle_called is False
    assert readiness.exchange_called is False
    assert readiness.not_execution_authority is True


async def test_scheduler_planning_requires_explicit_enablement_before_planner_call():
    planner = _FakeShadowPlanner()
    result = await RuntimeStrategySignalSchedulerPlanningService(
        planner=planner,
        fact_sources=_ready_sources(),
    ).plan_if_ready(
        _signal_input(),
        _output(),
        runtime=_runtime(),
        candidate_id="CPM-RO-001",
    )

    assert (
        result.status
        == RuntimeStrategySignalSchedulerPlanningStatus.EXPLICIT_ENABLE_REQUIRED
    )
    assert result.readiness.scheduler_can_call_runtime_planner is True
    assert result.blockers == ["shadow_candidate_creation_not_explicitly_enabled"]
    assert result.planner_call_performed is False
    assert result.signal_evaluation_created is False
    assert result.order_candidate_created is False
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False
    assert planner.calls == []


async def test_scheduler_planning_calls_shadow_planner_only_when_ready_and_enabled():
    planner = _FakeShadowPlanner()
    result = await RuntimeStrategySignalSchedulerPlanningService(
        planner=planner,
        fact_sources=_ready_sources(),
    ).plan_if_ready(
        _signal_input(),
        _output(),
        runtime=_runtime(),
        candidate_id="CPM-RO-001",
        allow_shadow_candidate_creation=True,
        context_id="context-scheduler-handoff",
        metadata={"unit_test": True},
    )

    assert (
        result.status
        == RuntimeStrategySignalSchedulerPlanningStatus.SHADOW_CANDIDATE_CREATED
    )
    assert result.readiness.scheduler_can_call_runtime_planner is True
    assert result.planner_call_performed is True
    assert result.signal_evaluation_created is True
    assert result.order_candidate_created is True
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.order_lifecycle_called is False
    assert result.exchange_called is False
    assert planner.calls == [
        {
            "evaluation_id": "eval-scheduler-CPM-RO-001",
            "runtime_instance_id": "runtime-scheduler-CPM-RO-001",
            "context_id": "context-scheduler-handoff",
            "expires_at_ms": None,
            "metadata": {
                "scheduler_candidate_id": "CPM-RO-001",
                "scheduler_planning_handoff": True,
                "unit_test": True,
            },
        }
    ]


async def test_scheduler_planning_does_not_call_planner_when_readiness_blocked():
    planner = _FakeShadowPlanner()
    result = await RuntimeStrategySignalSchedulerPlanningService(
        planner=planner,
    ).plan_if_ready(
        _signal_input(),
        _output(),
        runtime=_runtime(),
        candidate_id="CPM-RO-001",
        allow_shadow_candidate_creation=True,
    )

    assert result.status == RuntimeStrategySignalSchedulerPlanningStatus.BLOCKED
    assert "trusted_runtime_fact_overlay_not_configured" in result.blockers
    assert result.planner_call_performed is False
    assert result.order_candidate_created is False
    assert result.execution_intent_created is False
    assert result.exchange_called is False
    assert planner.calls == []


async def test_scheduler_planning_blocks_before_planner_when_server_evaluation_not_ready():
    planner = _FakeShadowPlanner()
    evaluator = _FakeSignalEvaluationService(
        RuntimeStrategySignalEvaluationResult(
            evaluation_id="eval-scheduler-CPM-RO-001",
            strategy_family_id="CPM-RO-001",
            strategy_family_version_id="CPM-RO-001-v0",
            symbol="ETH/USDT:USDT",
            status=RuntimeStrategySignalEvaluationStatus.BLOCKED,
            blockers=["strategy_semantics_binding_missing"],
            can_call_semantic_binding=False,
        )
    )

    result = await RuntimeStrategySignalSchedulerPlanningService(
        planner=planner,
        fact_sources=_ready_sources(),
        signal_evaluation_service=evaluator,
    ).plan_signal_input_if_ready(
        _signal_input(),
        runtime=_runtime(),
        candidate_id="CPM-RO-001",
        allow_shadow_candidate_creation=True,
    )

    assert evaluator.calls == ["eval-scheduler-CPM-RO-001"]
    assert result.status == RuntimeStrategySignalSchedulerPlanningStatus.BLOCKED
    assert result.evaluation_result is not None
    assert result.evaluation_result.status == RuntimeStrategySignalEvaluationStatus.BLOCKED
    assert result.readiness.scheduler_can_call_runtime_planner is False
    assert "strategy_semantics_binding_missing" in result.blockers
    assert result.planner_call_performed is False
    assert result.signal_evaluation_created is False
    assert result.order_candidate_created is False
    assert result.execution_intent_created is False
    assert result.order_lifecycle_called is False
    assert result.exchange_called is False
    assert planner.calls == []


async def test_scheduler_planning_propagates_shadow_planner_block_without_execution():
    planner = _FakeShadowPlanner(
        status=RuntimeStrategySignalCandidatePlanningStatus.BLOCKED,
        blockers=["trusted_account_facts_source_unavailable"],
    )
    result = await RuntimeStrategySignalSchedulerPlanningService(
        planner=planner,
        fact_sources=_ready_sources(),
    ).plan_if_ready(
        _signal_input(),
        _output(),
        runtime=_runtime(),
        candidate_id="CPM-RO-001",
        allow_shadow_candidate_creation=True,
    )

    assert result.status == RuntimeStrategySignalSchedulerPlanningStatus.PLANNER_BLOCKED
    assert result.blockers == ["trusted_account_facts_source_unavailable"]
    assert result.planner_call_performed is True
    assert result.signal_evaluation_created is False
    assert result.order_candidate_created is False
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False


def test_scheduler_assembly_requires_market_source_for_fco_required_facts():
    readiness = RuntimeStrategySignalSchedulerAssemblyService(
        runtime=_runtime(family_id="FCO-001", version_id="FCO-001-v0"),
        fact_sources=_ready_sources(market=False),
    ).preview(
        _signal_input(family_id="FCO-001", version_id="FCO-001-v0"),
        _output(family_id="FCO-001", version_id="FCO-001-v0"),
        candidate_id="FCO-001",
    )

    assert readiness.status == RuntimeStrategySignalSchedulerReadinessStatus.BLOCKED
    assert readiness.required_trusted_market_fact_keys == [
        "funding_rate",
        "open_interest",
        "crowding_proxy",
    ]
    assert "trusted_market_fact_source_required_by_strategy_unavailable" in readiness.blockers
    assert readiness.order_candidate_created is False
    assert readiness.exchange_called is False


def test_scheduler_assembly_keeps_no_action_as_observe_only():
    readiness = RuntimeStrategySignalSchedulerAssemblyService(
        runtime=_runtime(),
        fact_sources=_ready_sources(),
    ).preview(
        _signal_input(),
        _output(signal_type=SignalType.NO_ACTION),
        candidate_id="CPM-RO-001",
    )

    assert readiness.status == RuntimeStrategySignalSchedulerReadinessStatus.OBSERVE_ONLY
    assert "strategy_signal_not_would_enter" in readiness.blockers
    assert readiness.scheduler_can_call_runtime_planner is False
    assert readiness.order_candidate_created is False
    assert readiness.execution_intent_created is False


async def test_trading_console_shadow_plan_endpoint_delegates_non_executing_service(
    monkeypatch,
):
    from src.interfaces import api as api_module
    from src.interfaces import api_trading_console

    runtime = _runtime()

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == runtime.runtime_instance_id
            return runtime

    class _PlanningService:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def plan_signal_input_if_ready(
            self,
            signal_input: StrategyFamilySignalInput,
            **kwargs,
        ) -> RuntimeStrategySignalSchedulerPlanningResult:
            self.calls.append(
                {
                    "evaluation_id": signal_input.evaluation_id,
                    "runtime_instance_id": kwargs["runtime"].runtime_instance_id,
                    "candidate_id": kwargs["candidate_id"],
                    "allow_shadow_candidate_creation": (
                        kwargs["allow_shadow_candidate_creation"]
                    ),
                    "context_id": kwargs["context_id"],
                    "expires_at_ms": kwargs["expires_at_ms"],
                    "metadata": kwargs["metadata"],
                }
            )
            return await RuntimeStrategySignalSchedulerPlanningService(
                planner=_FakeShadowPlanner(),
                fact_sources=_ready_sources(),
            ).plan_if_ready(
                signal_input,
                _output(),
                **kwargs,
            )

    planning_service = _PlanningService()
    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_service",
        _RuntimeService(),
        raising=False,
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_strategy_signal_scheduler_planning_service",
        planning_service,
        raising=False,
    )

    result = await api_trading_console.runtime_strategy_signal_shadow_plan_for_signal_input(
        runtime.runtime_instance_id,
        api_trading_console.RuntimeStrategySignalShadowPlanningRequest(
            signal_input=_signal_input(),
            allow_shadow_candidate_creation=True,
            candidate_id="CPM-RO-001",
            context_id="context-api-shadow-plan",
            expires_at_ms=NOW_MS + 60_000,
            metadata={"unit_test": True},
        ),
    )

    assert (
        result.status
        == RuntimeStrategySignalSchedulerPlanningStatus.SHADOW_CANDIDATE_CREATED
    )
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.order_lifecycle_called is False
    assert result.exchange_called is False
    assert planning_service.calls == [
        {
            "evaluation_id": "eval-scheduler-CPM-RO-001",
            "runtime_instance_id": runtime.runtime_instance_id,
            "candidate_id": "CPM-RO-001",
            "allow_shadow_candidate_creation": True,
            "context_id": "context-api-shadow-plan",
            "expires_at_ms": NOW_MS + 60_000,
            "metadata": {
                "trading_console_api": True,
                "runtime_instance_id": runtime.runtime_instance_id,
                "unit_test": True,
            },
        }
    ]
