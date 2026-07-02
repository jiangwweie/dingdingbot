from __future__ import annotations

from decimal import Decimal

import pytest

from scripts import build_runtime_reduce_only_close_owner_evidence as script
from src.domain.runtime_position_exit_plan import (
    RuntimePositionExitPlan,
    RuntimePositionExitPlanStatus,
)
from src.domain.runtime_reduce_only_close_authorization import (
    OWNER_REDUCE_ONLY_CLOSE_APPROVAL_ENV,
    RuntimeReduceOnlyCloseOwnerEvidence,
    RuntimeReduceOnlyCloseOwnerEvidenceStatus,
    STANDING_REDUCE_ONLY_RECOVERY_SCOPE,
    build_runtime_reduce_only_close_owner_evidence,
)


def _exit_plan(**overrides) -> RuntimePositionExitPlan:
    data = {
        "plan_id": "exit-plan-1",
        "runtime_instance_id": "runtime-1",
        "symbol": "AVAX/USDT:USDT",
        "side": "short",
        "status": RuntimePositionExitPlanStatus.READY_FOR_OWNER_REVIEW,
        "source_monitor_id": "monitor-1",
        "active_position_present": True,
        "hard_stop_boundary_present": True,
        "existing_tp_protection_present": False,
        "current_qty": Decimal("1.0"),
        "entry_price": Decimal("6.566"),
        "stop_price_reference": Decimal("6.639"),
        "risk_per_unit": Decimal("0.073"),
        "tp1_price_reference": Decimal("6.493"),
        "tp1_quantity_requested": Decimal("0.50"),
        "tp1_quantity_step_aligned": Decimal("0.0"),
        "runner_quantity_reference": Decimal("1.0"),
        "tp1_reduce_only_side": "buy",
        "full_reduce_only_close_quantity": Decimal("1.0"),
        "full_reduce_only_close_notional_reference": Decimal("6.57"),
        "full_reduce_only_close_feasible": True,
        "full_reduce_only_close_requires_owner_authorization": False,
        "market_min_qty": Decimal("1.0"),
        "market_qty_step": Decimal("1.0"),
        "tp1_quantity_feasible": False,
        "recommended_recovery_action": (
            "keep_hard_stop_only_or_prepare_official_reduce_only_recovery"
        ),
        "warnings": ["tp1_partial_quantity_below_min_qty_or_step"],
        "created_at_ms": 1,
    }
    data.update(overrides)
    return RuntimePositionExitPlan(**data)


def test_reduce_only_close_owner_evidence_ready_when_full_close_feasible():
    evidence = build_runtime_reduce_only_close_owner_evidence(
        exit_plan=_exit_plan(),
        now_ms=123,
    )

    assert (
        evidence.status
        == RuntimeReduceOnlyCloseOwnerEvidenceStatus.READY_FOR_STANDING_RECOVERY_AUTHORIZATION
    )
    assert evidence.owner_approval_env is None
    assert evidence.owner_approval_value is None
    assert evidence.owner_approval_required is False
    assert evidence.standing_authorization_scope == STANDING_REDUCE_ONLY_RECOVERY_SCOPE
    assert evidence.operation_layer_required is True
    assert evidence.finalgate_required is True
    assert evidence.close_quantity == Decimal("1.0")
    assert evidence.reduce_only_side == "buy"
    assert evidence.not_order is True
    assert evidence.not_execution_authority is True
    assert evidence.exchange_order_submitted is False
    assert evidence.position_closed is False
    assert "tp1_partial_quantity_below_min_qty_or_step" in evidence.warnings
    payload = evidence.model_dump(mode="json")
    assert payload["reduce_only_close_owner_evidence_only"] is True
    assert "packet_only" not in payload


def test_reduce_only_close_owner_evidence_blocks_when_full_close_not_feasible():
    evidence = build_runtime_reduce_only_close_owner_evidence(
        exit_plan=_exit_plan(
            full_reduce_only_close_feasible=False,
            full_reduce_only_close_quantity=Decimal("0"),
        ),
        now_ms=123,
    )

    assert evidence.status == RuntimeReduceOnlyCloseOwnerEvidenceStatus.BLOCKED
    assert evidence.owner_approval_value is None
    assert "full_reduce_only_close_not_feasible" in evidence.blockers


def test_reduce_only_close_owner_rejects_legacy_packet_only_input():
    evidence = build_runtime_reduce_only_close_owner_evidence(
        exit_plan=_exit_plan(),
        now_ms=123,
    )
    legacy_payload = evidence.model_dump(mode="json")
    legacy_payload["packet_only"] = legacy_payload.pop(
        "reduce_only_close_owner_evidence_only",
    )

    with pytest.raises(ValueError):
        RuntimeReduceOnlyCloseOwnerEvidence.model_validate(legacy_payload)


def test_reduce_only_close_owner_script_safety_is_projection_only():
    safety = script._reduce_only_close_owner_safety_invariants(
        exchange_read_only=True,
    )

    assert safety["reduce_only_close_owner_projection_only"] is True
    assert "packet_only" not in safety
    assert safety["exchange_read_only"] is True
    assert safety["exchange_write_called"] is False
    assert safety["order_created"] is False
    assert safety["position_closed"] is False
