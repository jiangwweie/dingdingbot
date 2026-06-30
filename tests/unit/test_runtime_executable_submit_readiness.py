import pytest
from pydantic import ValidationError

from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessArtifact,
    RuntimeExecutableSubmitReadinessEvidence,
    RuntimeExecutableSubmitReadinessStatus,
    build_runtime_executable_submit_readiness_artifact,
)


def _evidence(**overrides):
    values = {
        "final_gate_preview_id": "final-gate-preview-1",
        "final_gate_passed": True,
        "runtime_grant_authorization_id": "runtime-grant-1",
        "trusted_submit_fact_snapshot_id": "trusted-facts-1",
        "submit_idempotency_policy_id": "idem-1",
        "attempt_outcome_policy_id": "attempt-policy-1",
        "protection_creation_failure_policy_id": "protection-failure-1",
        "local_registration_enablement_decision_id": "local-enable-1",
        "exchange_submit_enablement_decision_id": "exchange-enable-1",
        "exchange_submit_action_authorization_id": "exchange-action-auth-1",
        "order_lifecycle_submit_enablement_id": "ol-submit-enable-1",
        "exchange_submit_adapter_enablement_id": "exchange-adapter-enable-1",
        "deployment_readiness_evidence_id": "deploy-ready-1",
        "protection_required_and_ready": True,
        "active_position_source_trusted": True,
        "account_facts_fresh": True,
        "duplicate_submit_guard_ready": True,
    }
    values.update(overrides)
    return RuntimeExecutableSubmitReadinessEvidence(**values)


def _packet(**overrides):
    values = {
        "runtime_instance_id": "runtime-1",
        "source_strategy_planning_artifact_id": "strategy-plan-1",
        "source_authorization_id": "consumed-auth-1",
        "strategy_planning_status": "ready_for_final_gate_preflight",
        "signal_evaluation_id": "signal-eval-1",
        "order_candidate_id": "order-candidate-1",
        "source_release_evidence_id": "release-1",
        "evidence": _evidence(),
        "now_ms": 1_765_000_000_000,
    }
    values.update(overrides)
    return build_runtime_executable_submit_readiness_artifact(**values)


def test_runtime_grant_path_ready_without_legacy_rehearsal_id():
    packet = _packet()

    assert packet.status == (
        RuntimeExecutableSubmitReadinessStatus.READY_FOR_EXECUTABLE_SUBMIT
    )
    assert packet.executable_submit_ready is True
    assert packet.legacy_pre_attempt_rehearsal_required is False
    assert "legacy_runtime_submit_rehearsal_id_not_required" in packet.warnings
    assert packet.order_lifecycle_called is False
    assert packet.exchange_order_submitted is False
    assert packet.withdrawal_or_transfer_created is False


def test_blocks_when_strategy_planning_has_no_candidate():
    packet = _packet(
        strategy_planning_status="blocked_by_release_gate",
        order_candidate_id=None,
    )

    assert packet.status == RuntimeExecutableSubmitReadinessStatus.BLOCKED
    assert packet.executable_submit_ready is False
    assert "strategy_planning_not_ready_for_final_gate_preflight" in packet.blockers
    assert "order_candidate_id_missing" in packet.blockers


def test_blocks_when_final_gate_is_not_passed():
    packet = _packet(
        evidence=_evidence(
            final_gate_preview_id="final-gate-preview-1",
            final_gate_passed=False,
        )
    )

    assert packet.status == RuntimeExecutableSubmitReadinessStatus.BLOCKED
    assert "final_gate_not_passed" in packet.blockers


def test_blocks_without_runtime_grant_or_owner_submit_authorization():
    packet = _packet(
        evidence=_evidence(
            runtime_grant_authorization_id=None,
            owner_real_submit_authorization_id=None,
        )
    )

    assert packet.status == RuntimeExecutableSubmitReadinessStatus.BLOCKED
    assert "runtime_grant_or_owner_submit_authorization_missing" in packet.blockers


def test_blocks_missing_trusted_facts_and_duplicate_guard():
    packet = _packet(
        evidence=_evidence(
            trusted_submit_fact_snapshot_id=None,
            active_position_source_trusted=False,
            account_facts_fresh=False,
            duplicate_submit_guard_ready=False,
        )
    )

    assert packet.status == RuntimeExecutableSubmitReadinessStatus.BLOCKED
    assert "trusted_submit_fact_snapshot_id_missing" in packet.blockers
    assert "active_position_source_not_trusted" in packet.blockers
    assert "account_facts_not_fresh" in packet.blockers
    assert "duplicate_submit_guard_not_ready" in packet.blockers


def test_legacy_first_real_submit_source_blockers_are_warnings_on_runtime_grant_path():
    packet = _packet(
        first_real_submit_source_status="blocked",
        first_real_submit_source_blockers=[
            "submit_rehearsal_not_ready",
            "first_real_submit_runtime_submit_rehearsal_id_missing",
        ],
    )

    assert packet.status == (
        RuntimeExecutableSubmitReadinessStatus.READY_FOR_EXECUTABLE_SUBMIT
    )
    assert (
        "first_real_submit_source_not_ready_but_runtime_grant_path_used"
        in packet.warnings
    )
    assert (
        "first_real_submit_source:submit_rehearsal_not_ready"
        in packet.warnings
    )
    assert packet.blockers == []


def test_first_real_submit_source_blocks_when_runtime_evidence_is_incomplete():
    packet = _packet(
        evidence=_evidence(runtime_grant_authorization_id=None),
        first_real_submit_source_status="blocked",
        first_real_submit_source_blockers=["submit_rehearsal_not_ready"],
    )

    assert packet.status == RuntimeExecutableSubmitReadinessStatus.BLOCKED
    assert "first_real_submit_source_not_ready" in packet.blockers
    assert "first_real_submit_source:submit_rehearsal_not_ready" in packet.blockers


def test_rejects_execution_metadata():
    packet = _packet()
    payload = packet.model_dump(mode="python")
    payload["metadata"] = {"submit_order": True}

    with pytest.raises(ValidationError, match="forbidden execution field"):
        RuntimeExecutableSubmitReadinessArtifact.model_validate(payload)


def test_builder_rejects_execution_metadata():
    packet = build_runtime_executable_submit_readiness_artifact(
        runtime_instance_id="runtime-1",
        source_strategy_planning_artifact_id="strategy-plan-1",
        source_authorization_id="auth-1",
        strategy_planning_status="ready_for_final_gate_preflight",
        signal_evaluation_id="signal-eval-1",
        order_candidate_id="order-candidate-1",
        evidence=_evidence(),
        additional_warnings=[],
        additional_blockers=[],
        now_ms=1,
    )
    payload = packet.model_dump(mode="python")
    payload["metadata"] = {"exchange_payload": {"x": 1}}

    with pytest.raises(ValidationError, match="forbidden execution field"):
        RuntimeExecutableSubmitReadinessArtifact.model_validate(payload)
