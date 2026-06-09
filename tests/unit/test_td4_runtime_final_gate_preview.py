from __future__ import annotations

import inspect as py_inspect
from decimal import Decimal
from pathlib import Path

from src.application.runtime_final_gate_preview_service import (
    RuntimeFinalGatePreviewService,
)
from src.domain.runtime_final_gate_preview import RuntimeFinalGatePreviewVerdict
from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateProtectionPreview,
    OrderCandidateRiskPreview,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.interfaces import api as api_module
from src.interfaces.api_trading_console import (
    runtime_final_gate_preview_for_order_candidate,
)


NOW_MS = 1780496665000


def _runtime(**overrides) -> StrategyRuntimeInstance:
    values = {
        "runtime_instance_id": "runtime-1",
        "trial_binding_id": "binding-1",
        "admission_decision_id": "admission-1",
        "strategy_family_id": "family-1",
        "strategy_family_version_id": "version-1",
        "symbol": "ETH/USDT:USDT",
        "side": "long",
        "status": StrategyRuntimeInstanceStatus.ACTIVE,
        "boundary": StrategyRuntimeBoundary(
            max_attempts=2,
            attempts_used=0,
            max_active_positions=1,
            max_notional_per_attempt=Decimal("50"),
            total_budget=Decimal("100"),
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=["long"],
            max_leverage=Decimal("3"),
            requires_protection=True,
            requires_review=True,
        ),
        "created_at_ms": NOW_MS,
        "updated_at_ms": NOW_MS,
    }
    values.update(overrides)
    return StrategyRuntimeInstance(**values)


def _candidate(**overrides) -> OrderCandidate:
    values = {
        "order_candidate_id": "order-candidate-1",
        "signal_evaluation_id": "signal-eval-1",
        "runtime_instance_id": "runtime-1",
        "trial_binding_id": "binding-1",
        "strategy_family_id": "family-1",
        "strategy_family_version_id": "version-1",
        "symbol": "ETH/USDT:USDT",
        "side": "long",
        "candidate_order_type": "market",
        "proposed_quantity": Decimal("0.01"),
        "intended_notional": Decimal("25"),
        "entry_price_reference": Decimal("2500"),
        "risk_preview": OrderCandidateRiskPreview(
            intended_notional=Decimal("25"),
            proposed_quantity=Decimal("0.01"),
            leverage=Decimal("2"),
        ),
        "protection_preview": OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="shadow_stop_reference",
        ),
        "rationale": "candidate for preview",
        "created_at_ms": NOW_MS,
        "updated_at_ms": NOW_MS,
    }
    values.update(overrides)
    return OrderCandidate(**values)


def _preview_service() -> RuntimeFinalGatePreviewService:
    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == "runtime-1"
            return _runtime()

    class _SignalService:
        async def get_order_candidate(self, order_candidate_id: str) -> OrderCandidate:
            assert order_candidate_id == "order-candidate-1"
            return _candidate()

    return RuntimeFinalGatePreviewService(
        runtime_service=_RuntimeService(),
        signal_evaluation_service=_SignalService(),
    )


def _preview_service_with_positions(active_positions) -> RuntimeFinalGatePreviewService:
    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == "runtime-1"
            return _runtime()

    class _SignalService:
        async def get_order_candidate(self, order_candidate_id: str) -> OrderCandidate:
            assert order_candidate_id == "order-candidate-1"
            return _candidate()

    class _PositionSource:
        async def list_active(self, *, symbol: str | None = None, limit: int = 100):
            assert symbol == "ETH/USDT:USDT"
            assert limit == 100
            return list(active_positions)

    return RuntimeFinalGatePreviewService(
        runtime_service=_RuntimeService(),
        signal_evaluation_service=_SignalService(),
        active_position_source=_PositionSource(),
    )


def test_runtime_final_gate_preview_passes_with_complete_safe_shadow_facts():
    preview = _preview_service().preview(
        runtime=_runtime(),
        candidate=_candidate(),
        active_positions_count=0,
        owner_reviewed=True,
    )

    assert preview.verdict == RuntimeFinalGatePreviewVerdict.PASS
    assert preview.blockers == []
    assert preview.runtime_boundary_snapshot.execution_enabled is False
    assert preview.candidate_snapshot.candidate_executable is False
    assert preview.audit_id_snapshot.complete is True
    assert preview.dry_run is True
    assert preview.execution_enabled is False
    assert preview.execution_intent_created is False
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.runtime_state_mutated is False


def test_runtime_final_gate_budget_check_prefers_max_loss_over_notional():
    preview = _preview_service().preview(
        runtime=_runtime(
            boundary=StrategyRuntimeBoundary(
                max_attempts=2,
                attempts_used=0,
                budget_reserved=Decimal("0"),
                max_active_positions=1,
                max_notional_per_attempt=Decimal("10"),
                total_budget=Decimal("9"),
                allowed_symbols=["ETH/USDT:USDT"],
                allowed_sides=["long"],
                max_leverage=Decimal("1"),
                requires_protection=True,
                requires_review=True,
            )
        ),
        candidate=_candidate(
            intended_notional=Decimal("10"),
            risk_preview=OrderCandidateRiskPreview(
                intended_notional=Decimal("10"),
                proposed_quantity=Decimal("0.004"),
                max_loss_reference=Decimal("3"),
                leverage=Decimal("1"),
            ),
        ),
        active_positions_count=0,
        owner_reviewed=True,
    )

    budget_check = next(
        check for check in preview.checks if check.name == "budget_remaining"
    )
    assert preview.verdict == RuntimeFinalGatePreviewVerdict.PASS
    assert "candidate_exceeds_budget_remaining" not in preview.blockers
    assert budget_check.facts["budget_reservation_basis"] == "max_loss_reference"
    assert budget_check.facts["budget_reservation_amount"] == Decimal("3")
    assert budget_check.facts["intended_notional"] == Decimal("10")


async def test_runtime_final_gate_preview_uses_local_active_position_source_when_query_missing():
    preview = await _preview_service_with_positions([]).preview_order_candidate(
        order_candidate_id="order-candidate-1",
        owner_reviewed=True,
    )

    assert preview.verdict == RuntimeFinalGatePreviewVerdict.PASS
    assert preview.active_positions_count == 0
    assert preview.metadata["active_positions_count_source"] == "local_position_projection"
    assert preview.execution_intent_created is False
    assert preview.order_created is False


async def test_runtime_final_gate_preview_blocks_when_local_active_positions_exhaust_capacity():
    preview = await _preview_service_with_positions([object()]).preview_order_candidate(
        order_candidate_id="order-candidate-1",
        owner_reviewed=True,
    )

    assert preview.verdict == RuntimeFinalGatePreviewVerdict.BLOCK
    assert preview.active_positions_count == 1
    assert "active_position_capacity_exhausted" in preview.blockers
    assert preview.metadata["active_positions_count_source"] == "local_position_projection"


def test_runtime_final_gate_preview_blocks_runtime_boundary_violations():
    runtime = _runtime(
        status=StrategyRuntimeInstanceStatus.PAUSED,
        boundary=StrategyRuntimeBoundary(
            max_attempts=2,
            attempts_used=2,
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("20"),
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=["long"],
            max_leverage=Decimal("1"),
            requires_protection=True,
            requires_review=True,
        ),
    )
    candidate = _candidate(
        symbol="BTC/USDT:USDT",
        side="short",
        intended_notional=Decimal("25"),
        risk_preview=OrderCandidateRiskPreview(leverage=Decimal("2")),
        protection_preview=OrderCandidateProtectionPreview(requires_protection=True),
    )

    preview = _preview_service().preview(
        runtime=runtime,
        candidate=candidate,
        active_positions_count=1,
        owner_reviewed=False,
    )

    assert preview.verdict == RuntimeFinalGatePreviewVerdict.BLOCK
    assert "runtime_not_active" in preview.blockers
    assert "attempts_exhausted" in preview.blockers
    assert "candidate_exceeds_max_notional_per_attempt" in preview.blockers
    assert "symbol_outside_runtime_boundary" in preview.blockers
    assert "side_outside_runtime_boundary" in preview.blockers
    assert "candidate_exceeds_max_leverage" in preview.blockers
    assert "active_position_capacity_exhausted" in preview.blockers
    assert "protection_reference_missing" in preview.blockers
    assert "owner_review_required" in preview.blockers


def test_runtime_final_gate_preview_blocks_when_active_position_fact_is_missing():
    runtime = _runtime(
        boundary=StrategyRuntimeBoundary(
            max_attempts=2,
            max_active_positions=1,
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=["long"],
            requires_protection=False,
            requires_review=False,
        )
    )
    candidate = _candidate(
        intended_notional=None,
        risk_preview=OrderCandidateRiskPreview(),
        protection_preview=OrderCandidateProtectionPreview(requires_protection=False),
    )

    preview = _preview_service().preview(
        runtime=runtime,
        candidate=candidate,
        active_positions_count=None,
        owner_reviewed=False,
    )

    assert preview.verdict == RuntimeFinalGatePreviewVerdict.BLOCK
    assert "active_positions_count_not_available" in preview.blockers
    assert "candidate_notional_missing" in preview.warnings
    assert "runtime_max_leverage_missing" in preview.warnings


def test_runtime_final_gate_preview_blocks_incomplete_audit_id_spine():
    candidate = _candidate(trial_binding_id=None)

    preview = _preview_service().preview(
        runtime=_runtime(),
        candidate=candidate,
        active_positions_count=0,
        owner_reviewed=True,
    )

    assert preview.verdict == RuntimeFinalGatePreviewVerdict.BLOCK
    assert "audit_ids_incomplete_or_mismatched" in preview.blockers
    assert "trial_binding_id" in preview.audit_id_snapshot.missing
    assert "trial_binding_id" in preview.audit_id_snapshot.mismatches


async def test_trading_console_runtime_final_gate_preview_is_get_only_shadow_view(monkeypatch):
    service = _preview_service()
    monkeypatch.setattr(api_module, "_runtime_final_gate_preview_service", service, raising=False)

    preview = await runtime_final_gate_preview_for_order_candidate(
        "order-candidate-1",
        active_positions_count=0,
        owner_reviewed=True,
    )

    assert preview.verdict == RuntimeFinalGatePreviewVerdict.PASS
    assert preview.preview_only is True
    assert preview.execution_enabled is False
    assert preview.candidate_executable is False
    assert preview.not_order is True
    assert preview.not_execution_intent is True
    assert preview.execution_intent_created is False
    assert preview.order_created is False


def test_td4_new_code_has_no_execution_or_exchange_dependencies():
    forbidden = [
        "PgOrderRepository",
        "OrderLifecycleService",
        "OwnerBoundedExecutionService",
        "PgExecutionIntentRepository",
        "ExchangeGateway",
        "place_order",
        "delete_orders_batch",
        "exchange_order_id",
        "client_order_id",
    ]
    files = [
        Path("src/domain/runtime_final_gate_preview.py"),
        Path("src/application/runtime_final_gate_preview_service.py"),
    ]
    for path in files:
        text = path.read_text()
        for token in forbidden:
            assert token not in text

    source = py_inspect.getsource(runtime_final_gate_preview_for_order_candidate)
    for token in forbidden:
        assert token not in source
