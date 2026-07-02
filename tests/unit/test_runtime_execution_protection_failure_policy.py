from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_protection_failure_policy import (
    RuntimeExecutionProtectionFailurePolicy,
    RuntimeExecutionProtectionFailurePolicyStatus,
    build_runtime_execution_protection_failure_policy,
)
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlan,
    RuntimeExecutionProtectionPlanStatus,
)


NOW_MS = 1781090000000


def _ready_protection_plan() -> RuntimeExecutionProtectionPlan:
    return RuntimeExecutionProtectionPlan(
        protection_plan_id="runtime-protection-plan-intent-1",
        protection_plan_preview_id="runtime-protection-preview-intent-1",
        execution_intent_id="intent-1",
        runtime_execution_intent_draft_id="draft-1",
        source_type="brc_runtime_order_candidate",
        source_id="candidate-1",
        semantic_ids=BrcSemanticIds(
            runtime_instance_id="runtime-1",
            trial_binding_id="binding-1",
            strategy_family_id="CPM-001",
            strategy_family_version_id="CPM-001-v0",
            signal_evaluation_id="signal-eval-1",
            order_candidate_id="candidate-1",
        ),
        status=RuntimeExecutionProtectionPlanStatus.READY_FOR_SUBMIT_ADAPTER,
        symbol="BNB/USDT:USDT",
        side="long",
        proposed_quantity=Decimal("0.016"),
        intended_notional=Decimal("9.60"),
        entry_price_reference=Decimal("600"),
        requires_protection=True,
        stop_reference="pullback_low",
        stop_price_reference=Decimal("587.50"),
        take_profit_references=[
            {"kind": "tp1", "price": "612.50", "size_fraction": "0.5"},
            {"kind": "runner", "trail": "atr"},
        ],
        risk_preview={"max_loss_reference": "0.20"},
        protection_preview={"requires_protection": True},
        blockers=[],
        warnings=[],
        created_at_ms=NOW_MS,
    )


def test_protection_failure_policy_ready_without_execution_authority():
    policy = build_runtime_execution_protection_failure_policy(
        protection_plan=_ready_protection_plan(),
        now_ms=NOW_MS,
    )

    assert (
        policy.status
        == RuntimeExecutionProtectionFailurePolicyStatus
        .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )
    assert policy.policy_id == "runtime-protection-failure-policy-intent-1"
    assert policy.incident_kind == "entry_filled_protection_creation_failed"
    assert policy.response_mode == "fail_closed_unprotected_position_recovery"
    assert policy.block_new_entries_until_resolved is True
    assert policy.mark_position_unprotected_until_verified is True
    assert policy.require_owner_recovery_review is True
    assert policy.require_reduce_only_recovery_mode is True
    assert policy.require_reconciliation_before_retry is True
    assert policy.consume_attempt_on_any_fill is True
    assert policy.hold_or_reconcile_budget_until_position_resolved is True
    assert policy.must_not_mark_unprotected_position_as_protected is True
    assert policy.order_created is False
    assert policy.order_lifecycle_called is False
    assert policy.exchange_called is False
    assert policy.exchange_order_submitted is False
    assert policy.execution_intent_status_changed is False


def test_protection_failure_policy_blocks_missing_fail_closed_actions():
    policy = build_runtime_execution_protection_failure_policy(
        protection_plan=_ready_protection_plan(),
        block_new_entries_until_resolved=False,
        require_reduce_only_recovery_mode=False,
        hold_or_reconcile_budget_until_position_resolved=False,
        now_ms=NOW_MS,
    )

    assert policy.status == RuntimeExecutionProtectionFailurePolicyStatus.BLOCKED
    assert "block_new_entries_until_resolved_missing" in policy.blockers
    assert "require_reduce_only_recovery_mode_missing" in policy.blockers
    assert "hold_or_reconcile_budget_until_position_resolved_missing" in (
        policy.blockers
    )
    assert policy.exchange_called is False


def test_protection_failure_policy_rejects_execution_metadata():
    payload = build_runtime_execution_protection_failure_policy(
        protection_plan=_ready_protection_plan(),
        now_ms=NOW_MS,
    ).model_dump(mode="python")
    payload["metadata"] = {"exchange_order_id": "abc"}

    with pytest.raises(ValueError, match="forbidden execution field"):
        RuntimeExecutionProtectionFailurePolicy(**payload)
