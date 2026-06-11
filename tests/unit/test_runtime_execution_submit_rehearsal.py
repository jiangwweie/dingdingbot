from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_exchange_gateway_readiness import (
    RuntimeExecutionExchangeGatewayReadinessStatus,
)
from src.domain.runtime_execution_exchange_submit_enablement import (
    RuntimeExecutionExchangeSubmitGateStatus,
)
from src.domain.runtime_execution_submit_rehearsal import (
    RuntimeExecutionSubmitRehearsal,
    RuntimeExecutionSubmitRehearsalStatus,
    build_runtime_execution_submit_rehearsal,
)


NOW_MS = 1781000000000


def _semantic_ids() -> BrcSemanticIds:
    return BrcSemanticIds(
        runtime_instance_id="runtime-1",
        trial_binding_id="trial-1",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        signal_evaluation_id="evaluation-1",
        order_candidate_id="candidate-1",
    )


def _decision(**overrides):
    fields = {
        "decision_id": "runtime-exchange-submit-enable-auth-1",
        "authorization_id": "auth-1",
        "execution_intent_id": "intent-1",
        "runtime_instance_id": "runtime-1",
        "source_type": "brc_runtime_order_candidate",
        "source_id": "candidate-1",
        "semantic_ids": _semantic_ids(),
        "status": (
            RuntimeExecutionExchangeSubmitGateStatus
            .READY_FOR_EXCHANGE_SUBMIT_ACTION
        ),
        "trusted_submit_fact_snapshot_id": "trusted-submit-facts-intent-1",
        "submit_idempotency_policy_id": "runtime-submit-idempotency-auth-1",
        "attempt_outcome_policy_id": "runtime-attempt-outcome-policy-auth-1",
        "protection_creation_failure_policy_id": (
            "protection-failure-policy-intent-1"
        ),
        "local_registration_enablement_decision_id": (
            "runtime-local-registration-enable-auth-1"
        ),
        "owner_real_submit_authorization_id": "owner-real-submit-auth-1",
        "order_lifecycle_submit_enablement_id": (
            "order-lifecycle-submit-enable-1"
        ),
        "exchange_submit_adapter_enablement_id": (
            "exchange-submit-adapter-enable-1"
        ),
        "deployment_readiness_evidence_id": (
            "runtime-exchange-gateway-readiness-1"
        ),
        "exchange_submit_action_authorization_id": "exchange-submit-action-1",
        "blockers": [],
        "warnings": [],
        "execution_intent_status_changed": False,
        "order_lifecycle_submit_called": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "owner_bounded_execution_called": False,
        "withdrawal_or_transfer_created": False,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _gateway_readiness(**overrides):
    fields = {
        "readiness_id": "runtime-exchange-gateway-readiness-1",
        "status": (
            RuntimeExecutionExchangeGatewayReadinessStatus
            .READY_FOR_MANUAL_GATEWAY_BINDING
        ),
        "blockers": [],
        "warnings": ["not_live_action_authorization"],
        "created_at_ms": NOW_MS - 1_000,
        "gateway_injected": False,
        "exchange_called": False,
        "exchange_order_submitted": False,
        "order_lifecycle_submit_called": False,
        "execution_intent_status_changed": False,
        "owner_bounded_execution_called": False,
        "withdrawal_or_transfer_created": False,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_submit_rehearsal_can_be_ready_for_owner_review_without_authority():
    rehearsal = build_runtime_execution_submit_rehearsal(
        exchange_submit_enablement_decision=_decision(),
        runtime_exchange_gateway_readiness=_gateway_readiness(),
        now_ms=NOW_MS,
    )

    assert (
        rehearsal.status
        == RuntimeExecutionSubmitRehearsalStatus.READY_FOR_OWNER_LIVE_ACTION_REVIEW
    )
    assert rehearsal.blockers == []
    assert rehearsal.exchange_submit_enablement_ready is True
    assert rehearsal.runtime_gateway_readiness_ready is True
    assert rehearsal.runtime_gateway_readiness_fresh is True
    assert rehearsal.runtime_gateway_readiness_age_ms == 1_000
    assert rehearsal.no_blocking_recovery_tasks is True
    checklist = {item.key: item for item in rehearsal.evidence_checklist}
    assert checklist["trusted_submit_facts"].ready is True
    assert checklist["submit_idempotency"].evidence_id == (
        "runtime-submit-idempotency-auth-1"
    )
    assert checklist["owner_real_submit_authorization"].ready is True
    assert checklist["runtime_exchange_gateway_readiness"].ready is True
    assert checklist["no_blocking_recovery_tasks"].ready is True
    assert rehearsal.metadata["first_real_submit_checklist"] is True
    assert rehearsal.not_live_action_authorization is True
    assert rehearsal.not_exchange_submit_authority is True
    assert rehearsal.not_order_lifecycle_authority is True
    assert rehearsal.execution_intent_status_changed is False
    assert rehearsal.order_created is False
    assert rehearsal.order_lifecycle_called is False
    assert rehearsal.exchange_called is False
    assert rehearsal.exchange_order_submitted is False
    assert rehearsal.owner_bounded_execution_called is False
    assert rehearsal.withdrawal_or_transfer_created is False
    assert "not_live_action_authorization" in rehearsal.warnings[0]


def test_submit_rehearsal_blocks_missing_gateway_readiness_and_recovery_tasks():
    rehearsal = build_runtime_execution_submit_rehearsal(
        exchange_submit_enablement_decision=_decision(),
        runtime_exchange_gateway_readiness=None,
        blocking_recovery_task_ids=["rt-ex-submit-recovery-auth-1"],
        now_ms=NOW_MS,
    )

    assert rehearsal.status == RuntimeExecutionSubmitRehearsalStatus.BLOCKED
    assert "runtime_exchange_gateway_readiness_missing" in rehearsal.blockers
    assert "execution_recovery_blocking_tasks_open" in rehearsal.blockers
    checklist = {item.key: item for item in rehearsal.evidence_checklist}
    assert checklist["runtime_exchange_gateway_readiness"].ready is False
    assert "runtime_exchange_gateway_readiness_missing" in (
        checklist["runtime_exchange_gateway_readiness"].blockers
    )
    assert checklist["no_blocking_recovery_tasks"].ready is False
    assert "execution_recovery_blocking_tasks_open" in (
        checklist["no_blocking_recovery_tasks"].blockers
    )
    assert (
        "execution_recovery_blocking_task:rt-ex-submit-recovery-auth-1"
        in rehearsal.warnings
    )
    assert rehearsal.runtime_gateway_readiness_ready is False
    assert rehearsal.no_blocking_recovery_tasks is False
    assert rehearsal.exchange_called is False


def test_submit_rehearsal_blocks_stale_gateway_readiness():
    rehearsal = build_runtime_execution_submit_rehearsal(
        exchange_submit_enablement_decision=_decision(),
        runtime_exchange_gateway_readiness=_gateway_readiness(
            created_at_ms=NOW_MS - 900_001,
        ),
        now_ms=NOW_MS,
    )

    assert rehearsal.status == RuntimeExecutionSubmitRehearsalStatus.BLOCKED
    assert "runtime_exchange_gateway_readiness_stale" in rehearsal.blockers
    assert rehearsal.runtime_gateway_readiness_ready is False
    assert rehearsal.runtime_gateway_readiness_fresh is False
    assert rehearsal.runtime_gateway_readiness_age_ms == 900_001
    checklist = {item.key: item for item in rehearsal.evidence_checklist}
    assert checklist["runtime_exchange_gateway_readiness"].ready is False
    assert "runtime_exchange_gateway_readiness_stale" in (
        checklist["runtime_exchange_gateway_readiness"].blockers
    )


def test_submit_rehearsal_blocks_gateway_readiness_missing_timestamp():
    readiness = _gateway_readiness()
    delattr(readiness, "created_at_ms")

    rehearsal = build_runtime_execution_submit_rehearsal(
        exchange_submit_enablement_decision=_decision(),
        runtime_exchange_gateway_readiness=readiness,
        now_ms=NOW_MS,
    )

    assert rehearsal.status == RuntimeExecutionSubmitRehearsalStatus.BLOCKED
    assert (
        "runtime_exchange_gateway_readiness_created_at_missing"
        in rehearsal.blockers
    )
    assert rehearsal.runtime_gateway_readiness_ready is False


def test_submit_rehearsal_blocks_mismatched_or_mutating_artifacts():
    rehearsal = build_runtime_execution_submit_rehearsal(
        exchange_submit_enablement_decision=_decision(exchange_called=True),
        runtime_exchange_gateway_readiness=_gateway_readiness(
            readiness_id="runtime-exchange-gateway-readiness-other",
            exchange_order_submitted=True,
        ),
        now_ms=NOW_MS,
    )

    assert rehearsal.status == RuntimeExecutionSubmitRehearsalStatus.BLOCKED
    assert "exchange_submit_enablement_called_exchange" in rehearsal.blockers
    assert "runtime_exchange_gateway_readiness_id_mismatch" in rehearsal.blockers
    assert (
        "runtime_exchange_gateway_readiness_submitted_exchange_order"
        in rehearsal.blockers
    )
    assert rehearsal.exchange_called is False
    assert rehearsal.exchange_order_submitted is False


def test_submit_rehearsal_rejects_execution_metadata():
    rehearsal = build_runtime_execution_submit_rehearsal(
        exchange_submit_enablement_decision=_decision(),
        runtime_exchange_gateway_readiness=_gateway_readiness(),
        now_ms=NOW_MS,
    )
    payload = rehearsal.model_dump(mode="python")
    payload["metadata"] = {"exchange_payload": {"symbol": "BNB/USDT:USDT"}}

    with pytest.raises(ValueError, match="forbidden execution field"):
        RuntimeExecutionSubmitRehearsal.model_validate(payload)
