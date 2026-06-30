import pytest
from pydantic import ValidationError

from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessEvidence,
    build_runtime_executable_submit_readiness_artifact,
)
from src.domain.runtime_official_submit_handoff import (
    RuntimeOfficialSubmitHandoffMode,
    RuntimeOfficialSubmitHandoffArtifact,
    RuntimeOfficialSubmitHandoffStatus,
    build_runtime_official_submit_handoff_artifact,
)


def _readiness(**overrides):
    evidence = RuntimeExecutableSubmitReadinessEvidence(
        final_gate_preview_id="final-gate-preview-1",
        final_gate_passed=True,
        runtime_grant_authorization_id="runtime-grant-1",
        trusted_submit_fact_snapshot_id="trusted-facts-1",
        submit_idempotency_policy_id="idem-1",
        attempt_outcome_policy_id="attempt-policy-1",
        protection_creation_failure_policy_id="protection-failure-1",
        local_registration_enablement_decision_id="local-enable-1",
        exchange_submit_enablement_decision_id="exchange-enable-1",
        exchange_submit_action_authorization_id="exchange-action-auth-1",
        order_lifecycle_submit_enablement_id="ol-submit-enable-1",
        exchange_submit_adapter_enablement_id="exchange-adapter-enable-1",
        deployment_readiness_evidence_id="deploy-ready-1",
        protection_required_and_ready=True,
        active_position_source_trusted=True,
        account_facts_fresh=True,
        duplicate_submit_guard_ready=True,
    )
    values = {
        "runtime_instance_id": "runtime-1",
        "source_strategy_planning_artifact_id": "strategy-plan-1",
        "source_authorization_id": "consumed-auth-1",
        "strategy_planning_status": "ready_for_final_gate_preflight",
        "signal_evaluation_id": "signal-eval-1",
        "order_candidate_id": "order-candidate-1",
        "source_release_evidence_id": "release-1",
        "evidence": evidence,
        "now_ms": 1_765_000_000_000,
    }
    values.update(overrides)
    return build_runtime_executable_submit_readiness_artifact(**values)


def test_ready_disabled_smoke_handoff_uses_fresh_authorization_and_official_endpoint():
    handoff = build_runtime_official_submit_handoff_artifact(
        readiness_artifact=_readiness(),
        fresh_submit_authorization_id="fresh-auth-1",
        now_ms=1_765_000_000_001,
    )

    assert handoff.status == (
        RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL
    )
    assert handoff.ready_for_official_submit_call is True
    assert handoff.official_endpoint_method == "POST"
    assert handoff.official_endpoint_path.endswith(
        "/runtime-execution-first-real-submit-actions/authorizations/fresh-auth-1"
    )
    assert handoff.official_query[
        "owner_confirmed_for_first_real_submit_action"
    ] is False
    assert handoff.official_query["trusted_submit_fact_snapshot_id"] == (
        "trusted-facts-1"
    )
    assert handoff.source_consumed_authorization_id == "consumed-auth-1"
    assert handoff.metadata["read_only_submit_projection"] is True
    assert handoff.metadata["execution_attempt_source"] is False
    assert handoff.metadata["lifecycle_authority"] is False
    assert "read_only_handoff" not in handoff.metadata
    assert handoff.order_lifecycle_called is False
    assert handoff.exchange_order_submitted is False


def test_blocks_reusing_consumed_authorization_as_fresh_submit_authorization():
    handoff = build_runtime_official_submit_handoff_artifact(
        readiness_artifact=_readiness(),
        fresh_submit_authorization_id="consumed-auth-1",
        now_ms=1,
    )

    assert handoff.status == RuntimeOfficialSubmitHandoffStatus.BLOCKED
    assert "fresh_submit_authorization_reuses_consumed_authorization" in (
        handoff.blockers
    )


def test_blocks_when_readiness_is_not_ready():
    readiness = _readiness(
        strategy_planning_status="blocked_by_release_gate",
        order_candidate_id=None,
    )

    handoff = build_runtime_official_submit_handoff_artifact(
        readiness_artifact=readiness,
        fresh_submit_authorization_id="fresh-auth-1",
        now_ms=1,
    )

    assert handoff.status == RuntimeOfficialSubmitHandoffStatus.BLOCKED
    assert "readiness_not_ready_for_executable_submit" in handoff.blockers
    assert any(item.startswith("readiness:") for item in handoff.blockers)


def test_real_gateway_handoff_uses_standing_authorization_without_chat_confirmation():
    handoff = build_runtime_official_submit_handoff_artifact(
        readiness_artifact=_readiness(),
        fresh_submit_authorization_id="fresh-auth-1",
        mode=RuntimeOfficialSubmitHandoffMode.REAL_GATEWAY_ACTION,
        owner_confirmed_for_real_submit_action=False,
        now_ms=1,
    )

    assert handoff.status == (
        RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL
    )
    assert handoff.official_query[
        "owner_confirmed_for_first_real_submit_action"
    ] is True
    assert "owner_real_submit_action_confirmation_missing" not in handoff.blockers
    assert handoff.metadata["standing_authorization_reference"].startswith(
        "owner-standing-authorization:"
    )


def test_real_gateway_handoff_can_be_ready_with_confirmation():
    handoff = build_runtime_official_submit_handoff_artifact(
        readiness_artifact=_readiness(),
        fresh_submit_authorization_id="fresh-auth-1",
        mode=RuntimeOfficialSubmitHandoffMode.REAL_GATEWAY_ACTION,
        owner_confirmed_for_real_submit_action=True,
        now_ms=1,
    )

    assert handoff.status == (
        RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL
    )
    assert handoff.official_query[
        "owner_confirmed_for_first_real_submit_action"
    ] is True


def test_rejects_execution_metadata():
    handoff = build_runtime_official_submit_handoff_artifact(
        readiness_artifact=_readiness(),
        fresh_submit_authorization_id="fresh-auth-1",
        now_ms=1,
    )
    payload = handoff.model_dump(mode="python")
    payload["metadata"] = {"submit_order": True}

    with pytest.raises(ValidationError, match="forbidden execution field"):
        RuntimeOfficialSubmitHandoffArtifact.model_validate(payload)
