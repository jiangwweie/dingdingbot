from __future__ import annotations

import json
from decimal import Decimal

import pytest
from fastapi import HTTPException

from scripts import runtime_strategy_signal_intent_draft_source_api_flow as api_flow
from src.application.runtime_strategy_signal_intent_draft_source_service import (
    RuntimeStrategySignalIntentDraftSourceService,
    RuntimeStrategySignalIntentDraftSourceStatus,
)
from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationResult,
    RuntimeStrategySignalEvaluationStatus,
)
from src.application.runtime_strategy_signal_planning_service import (
    RuntimeStrategySignalCandidatePlanningResult,
    RuntimeStrategySignalCandidatePlanningStatus,
)
from src.application.runtime_strategy_signal_scheduler_assembly import (
    RuntimeStrategySignalSchedulerFactSources,
    RuntimeStrategySignalSchedulerReadiness,
    RuntimeStrategySignalSchedulerReadinessStatus,
)
from src.application.runtime_strategy_signal_scheduler_planning_service import (
    RuntimeStrategySignalSchedulerPlanningResult,
    RuntimeStrategySignalSchedulerPlanningStatus,
)
from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_plan import (
    RuntimeExecutionIntentDraft,
    RuntimeExecutionIntentDraftStatus,
    RuntimeExecutionPlanStatus,
)
from src.domain.runtime_final_gate_preview import RuntimeFinalGatePreviewVerdict
from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateProtectionPreview,
    OrderCandidateRiskPreview,
)
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    MarketSnapshot,
    SignalSide,
    StrategyFamilySignalInput,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.interfaces import api_trading_console
from src.interfaces.api_trading_console import (
    RuntimeStrategySignalIntentDraftSourceRequest,
)


NOW_MS = 1_781_000_000_000


def _signal_input() -> StrategyFamilySignalInput:
    return StrategyFamilySignalInput(
        evaluation_id="eval-rtf014",
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
            atr=Decimal("25"),
            timeframe="1h",
            candle_context={"closed_bar": True, "windows": {"1h": [], "4h": []}},
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
            unknown_unmanaged_counts={"positions": 0, "orders": 0},
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


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-rtf014",
        trial_binding_id="trial-rtf014",
        admission_decision_id="admission-rtf014",
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


def _candidate() -> OrderCandidate:
    return OrderCandidate(
        order_candidate_id="order-candidate-rtf014",
        signal_evaluation_id="eval-rtf014",
        runtime_instance_id="runtime-rtf014",
        trial_binding_id="trial-rtf014",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        side="long",
        proposed_quantity=Decimal("0.004"),
        intended_notional=Decimal("10"),
        entry_price_reference=Decimal("2525"),
        risk_preview=OrderCandidateRiskPreview(
            intended_notional=Decimal("10"),
            proposed_quantity=Decimal("0.004"),
            max_loss_reference=Decimal("0.2"),
            leverage=Decimal("1"),
            margin_required=Decimal("10"),
        ),
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="cpm_pullback_low",
            stop_price_reference=Decimal("2475"),
        ),
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _draft(
    *,
    status: RuntimeExecutionIntentDraftStatus = (
        RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
    ),
) -> RuntimeExecutionIntentDraft:
    ids = BrcSemanticIds(
        runtime_instance_id="runtime-rtf014",
        trial_binding_id="trial-rtf014",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        signal_evaluation_id="eval-rtf014",
        order_candidate_id="order-candidate-rtf014",
    )
    return RuntimeExecutionIntentDraft(
        draft_id="runtime-intent-draft-order-candidate-rtf014",
        plan_id="runtime-plan-order-candidate-rtf014",
        runtime_instance_id="runtime-rtf014",
        order_candidate_id="order-candidate-rtf014",
        signal_evaluation_id="eval-rtf014",
        semantic_ids=ids,
        status=status,
        symbol="ETH/USDT:USDT",
        side="long",
        candidate_order_type="market",
        proposed_quantity=Decimal("0.004"),
        intended_notional=Decimal("10"),
        entry_price_reference=Decimal("2525"),
        risk_preview=OrderCandidateRiskPreview(max_loss_reference=Decimal("0.2")),
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_price_reference=Decimal("2475"),
        ),
        owner_reviewed=True,
        owner_confirmed_for_intent=(
            status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
        ),
        source_plan_status=RuntimeExecutionPlanStatus.READY_FOR_INTENT_DRAFT,
        final_gate_verdict=RuntimeFinalGatePreviewVerdict.PASS,
        created_at_ms=NOW_MS,
    )


def _readiness() -> RuntimeStrategySignalSchedulerReadiness:
    return RuntimeStrategySignalSchedulerReadiness(
        candidate_id="CPM-RO-001",
        evaluation_id="eval-rtf014",
        signal_id="signal-rtf014",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        side="long",
        signal_type="would_enter",
        status=RuntimeStrategySignalSchedulerReadinessStatus.READY_FOR_NON_EXECUTING_PLANNER,
        semantics_binding_found=True,
        runtime_instance_id="runtime-rtf014",
        runtime_bound=True,
        fact_sources=RuntimeStrategySignalSchedulerFactSources(
            trusted_runtime_fact_overlay_configured=True,
            trusted_active_position_source_available=True,
            trusted_account_facts_source_available=True,
        ),
        scheduler_can_call_runtime_planner=True,
    )


def _scheduler_result(
    *,
    status: RuntimeStrategySignalSchedulerPlanningStatus = (
        RuntimeStrategySignalSchedulerPlanningStatus.SHADOW_CANDIDATE_CREATED
    ),
    candidate: OrderCandidate | None = None,
    blockers: list[str] | None = None,
) -> RuntimeStrategySignalSchedulerPlanningResult:
    candidate_planning = None
    if candidate is not None:
        candidate_planning = RuntimeStrategySignalCandidatePlanningResult(
            planning_id="runtime-signal-candidate-plan-eval-rtf014",
            runtime_instance_id="runtime-rtf014",
            strategy_family_id="CPM-RO-001",
            strategy_family_version_id="CPM-RO-001-v0",
            symbol="ETH/USDT:USDT",
            status=RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED,
            evaluation_result=RuntimeStrategySignalEvaluationResult(
                evaluation_id="eval-rtf014",
                strategy_family_id="CPM-RO-001",
                strategy_family_version_id="CPM-RO-001-v0",
                symbol="ETH/USDT:USDT",
                status=RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING,
                can_call_semantic_binding=True,
            ),
            candidate=candidate,
            signal_evaluation_created=True,
            order_candidate_created=True,
        )
    return RuntimeStrategySignalSchedulerPlanningResult(
        planning_id="scheduler-runtime-signal-plan-eval-rtf014",
        runtime_instance_id="runtime-rtf014",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        status=status,
        readiness=_readiness(),
        candidate_planning_result=candidate_planning,
        blockers=blockers or [],
        planner_call_performed=status
        == RuntimeStrategySignalSchedulerPlanningStatus.SHADOW_CANDIDATE_CREATED,
        signal_evaluation_created=candidate is not None,
        order_candidate_created=candidate is not None,
    )


class _Scheduler:
    def __init__(self, result: RuntimeStrategySignalSchedulerPlanningResult) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def plan_signal_input_if_ready(self, signal_input, **kwargs):
        self.calls.append({"signal_input": signal_input, **kwargs})
        return self.result


class _ExecutionPlanning:
    def __init__(self, draft: RuntimeExecutionIntentDraft | Exception) -> None:
        self.draft = draft
        self.calls: list[dict] = []

    async def record_intent_draft_for_order_candidate(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.draft, Exception):
            raise self.draft
        return self.draft


@pytest.mark.asyncio
async def test_records_ready_intent_draft_source_from_shadow_candidate():
    scheduler = _Scheduler(_scheduler_result(candidate=_candidate()))
    planning = _ExecutionPlanning(_draft())
    service = RuntimeStrategySignalIntentDraftSourceService(
        scheduler_planning_service=scheduler,
        runtime_execution_planning_service=planning,
    )

    packet = await service.record_ready_intent_draft_source(
        _signal_input(),
        runtime=_runtime(),
        allow_shadow_candidate_creation=True,
        allow_intent_draft_creation=True,
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
        active_positions_count=0,
    )

    assert packet.status == (
        RuntimeStrategySignalIntentDraftSourceStatus.PERSISTED_READY_INTENT_DRAFT
    )
    assert packet.ready_for_official_handoff_source is True
    assert packet.signal_evaluation_id == "eval-rtf014"
    assert packet.order_candidate_id == "order-candidate-rtf014"
    assert (
        packet.runtime_execution_intent_draft_id
        == "runtime-intent-draft-order-candidate-rtf014"
    )
    assert packet.draft_status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
    assert packet.signal_evaluation_created is True
    assert packet.order_candidate_created is True
    assert packet.runtime_execution_intent_draft_created is True
    assert packet.execution_intent_created is False
    assert packet.order_created is False
    assert packet.order_lifecycle_called is False
    assert packet.exchange_called is False
    assert scheduler.calls[0]["allow_shadow_candidate_creation"] is True
    assert planning.calls == [
        {
            "order_candidate_id": "order-candidate-rtf014",
            "owner_reviewed": True,
            "owner_confirmed_for_intent": True,
            "active_positions_count": 0,
        }
    ]


@pytest.mark.asyncio
async def test_blocks_before_scheduler_when_owner_confirmation_missing():
    scheduler = _Scheduler(_scheduler_result(candidate=_candidate()))
    planning = _ExecutionPlanning(_draft())
    service = RuntimeStrategySignalIntentDraftSourceService(
        scheduler_planning_service=scheduler,
        runtime_execution_planning_service=planning,
    )

    packet = await service.record_ready_intent_draft_source(
        _signal_input(),
        runtime=_runtime(),
        allow_shadow_candidate_creation=True,
        allow_intent_draft_creation=True,
        owner_reviewed=True,
        owner_confirmed_for_intent=False,
    )

    assert packet.status == RuntimeStrategySignalIntentDraftSourceStatus.BLOCKED
    assert "owner_confirmed_for_intent_required_for_ready_draft_source" in (
        packet.blockers
    )
    assert packet.signal_evaluation_created is False
    assert packet.order_candidate_created is False
    assert packet.runtime_execution_intent_draft_created is False
    assert scheduler.calls == []
    assert planning.calls == []


@pytest.mark.asyncio
async def test_blocks_without_intent_draft_creation_flag():
    scheduler = _Scheduler(_scheduler_result(candidate=_candidate()))
    planning = _ExecutionPlanning(_draft())
    service = RuntimeStrategySignalIntentDraftSourceService(
        scheduler_planning_service=scheduler,
        runtime_execution_planning_service=planning,
    )

    packet = await service.record_ready_intent_draft_source(
        _signal_input(),
        runtime=_runtime(),
        allow_shadow_candidate_creation=True,
        allow_intent_draft_creation=False,
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )

    assert packet.status == RuntimeStrategySignalIntentDraftSourceStatus.BLOCKED
    assert "intent_draft_creation_not_enabled" in packet.blockers
    assert scheduler.calls == []
    assert planning.calls == []


@pytest.mark.asyncio
async def test_blocks_when_scheduler_does_not_create_shadow_candidate():
    scheduler = _Scheduler(
        _scheduler_result(
            status=RuntimeStrategySignalSchedulerPlanningStatus.PLANNER_BLOCKED,
            blockers=["trusted_account_facts_source_unavailable"],
        )
    )
    planning = _ExecutionPlanning(_draft())
    service = RuntimeStrategySignalIntentDraftSourceService(
        scheduler_planning_service=scheduler,
        runtime_execution_planning_service=planning,
    )

    packet = await service.record_ready_intent_draft_source(
        _signal_input(),
        runtime=_runtime(),
        allow_shadow_candidate_creation=True,
        allow_intent_draft_creation=True,
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )

    assert packet.status == RuntimeStrategySignalIntentDraftSourceStatus.BLOCKED
    assert "trusted_account_facts_source_unavailable" in packet.blockers
    assert "scheduler_shadow_candidate_not_created" in packet.blockers
    assert packet.runtime_execution_intent_draft_created is False
    assert planning.calls == []


@pytest.mark.asyncio
async def test_trading_console_endpoint_rejects_runtime_mismatch(monkeypatch):
    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str):
            assert runtime_instance_id == "other-runtime"
            return _runtime()

    monkeypatch.setattr(
        api_trading_console,
        "_strategy_runtime_service",
        lambda: _async_value(_RuntimeService()),
    )

    with pytest.raises(HTTPException) as exc:
        await (
            api_trading_console
            .runtime_strategy_signal_intent_draft_source_for_signal_input(
                "other-runtime",
                RuntimeStrategySignalIntentDraftSourceRequest(
                    signal_input=_signal_input(),
                ),
            )
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_trading_console_endpoint_creates_ready_source(monkeypatch):
    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str):
            assert runtime_instance_id == "runtime-rtf014"
            return _runtime()

    scheduler = _Scheduler(_scheduler_result(candidate=_candidate()))
    planning = _ExecutionPlanning(_draft())
    service = RuntimeStrategySignalIntentDraftSourceService(
        scheduler_planning_service=scheduler,
        runtime_execution_planning_service=planning,
    )
    monkeypatch.setattr(
        api_trading_console,
        "_strategy_runtime_service",
        lambda: _async_value(_RuntimeService()),
    )
    monkeypatch.setattr(
        api_trading_console,
        "_runtime_strategy_signal_intent_draft_source_service",
        lambda: _async_value(service),
    )

    packet = await (
        api_trading_console
        .runtime_strategy_signal_intent_draft_source_for_signal_input(
            "runtime-rtf014",
            RuntimeStrategySignalIntentDraftSourceRequest(
                signal_input=_signal_input(),
                active_positions_count=0,
            ),
        )
    )

    assert packet.status == (
        RuntimeStrategySignalIntentDraftSourceStatus.PERSISTED_READY_INTENT_DRAFT
    )
    assert packet.ready_for_official_handoff_source is True
    assert planning.calls[0]["order_candidate_id"] == "order-candidate-rtf014"


async def _async_value(value):
    return value


class _Client:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "body": body,
            }
        )
        return {
            "http_status": 200,
            "body": {
                "status": "persisted_ready_intent_draft",
                "blockers": [],
                "warnings": ["unit"],
                "signal_evaluation_id": "eval-rtf014",
                "order_candidate_id": "order-candidate-rtf014",
                "runtime_execution_intent_draft_id": (
                    "runtime-intent-draft-order-candidate-rtf014"
                ),
                "draft_status": "ready_for_intent_creation",
                "ready_for_official_handoff_source": True,
                "signal_evaluation_created": True,
                "order_candidate_created": True,
                "runtime_execution_intent_draft_created": True,
            },
        }


def _args(tmp_path, **overrides):
    signal_path = tmp_path / "signal.json"
    signal_path.write_text(
        json.dumps({"signal_input": _signal_input().model_dump(mode="json")}),
        encoding="utf-8",
    )
    values = {
        "runtime_instance_id": "runtime-rtf014",
        "signal_input_json": str(signal_path),
        "env_file": None,
        "api_base": "http://unit",
        "candidate_id": "CPM-RO-001",
        "context_id": "context-rtf014",
        "expires_at_ms": None,
        "active_positions_count": 0,
        "allow_live_runtime_handoff_prepare": False,
        "metadata_json": None,
    }
    values.update(overrides)
    return type("Args", (), values)()


def test_intent_draft_source_api_flow_posts_ready_source_request(tmp_path):
    client = _Client()

    report = api_flow._build_report(_args(tmp_path), client=client)

    assert report["status"] == "persisted_ready_intent_draft"
    assert report["operator_action_preview"]["ready_for_official_handoff_source"] is True
    assert report["safety_invariants"]["signal_evaluation_created"] is True
    assert report["safety_invariants"]["order_candidate_created"] is True
    assert report["safety_invariants"]["runtime_execution_intent_draft_created"] is True
    assert report["safety_invariants"]["execution_intent_created"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False
    assert report["safety_invariants"]["order_lifecycle_called"] is False
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == (
        "/api/trading-console/strategy-runtimes/runtime-rtf014/"
        "strategy-signal-intent-draft-sources"
    )
    assert call["body"]["signal_input"]["evaluation_id"] == "eval-rtf014"
    assert call["body"]["allow_shadow_candidate_creation"] is True
    assert call["body"]["allow_intent_draft_creation"] is True
    assert call["body"]["allow_live_runtime_handoff_prepare"] is False
    assert call["body"]["owner_reviewed"] is True
    assert call["body"]["owner_confirmed_for_intent"] is True
    assert call["body"]["active_positions_count"] == 0
    assert call["body"]["metadata"]["signal_input_source_wrapper"] == {
        "wrapper": "signal_input",
    }


def test_intent_draft_source_api_flow_rejects_legacy_signal_wrapper(tmp_path):
    client = _Client()
    signal_path = tmp_path / "legacy-signal.json"
    signal_path.write_text(
        json.dumps(
            {
                "signal_packet": {
                    "signal_input": _signal_input().model_dump(mode="json"),
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="legacy signal wrapper"):
        api_flow._build_report(
            _args(tmp_path, signal_input_json=str(signal_path)),
            client=client,
        )

    assert client.calls == []
