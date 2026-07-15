from __future__ import annotations

from src.application.readmodels.lifecycle_mutation_enablement_proof import (
    ActionTimeCertificationReferenceV2,
    LaneSourceWatermarkV1,
    LifecycleMutationEnablementProof,
)


def _proof() -> LifecycleMutationEnablementProof:
    action_time = ActionTimeCertificationReferenceV2(
        stage="post_canary",
        target_runtime_head="a" * 40,
        certification_input_digest="sha256:" + "b" * 64,
        release_activation_outcome_id="activation-1",
        release_activation_source_watermark="release:1",
        lane_source_watermarks=(
            LaneSourceWatermarkV1(
                lane_scope_key="SG-1:ETHUSDT:long",
                lane_identity_key="lane-1",
                source_watermark="watermark-1",
                process_outcome_id="process-1",
            ),
        ),
        fact_snapshot_ids=("fact-1",),
        fact_set_digest="sha256:" + "c" * 64,
        fact_min_valid_until_ms=100_000,
        deploy_nonce="deploy-nonce-1",
    )
    return LifecycleMutationEnablementProof(
        target_runtime_head="a" * 40,
        lane_identity_digest="sha256:" + "d" * 64,
        action_time_certification_ref=action_time.certification_ref(),
        action_time_certification_payload=action_time,
        certification_projection_digest="sha256:" + "e" * 64,
    )


def test_lifecycle_proof_binds_nested_action_time_payload():
    proof = _proof()
    assert proof.schema == "brc.lifecycle_mutation_enablement_proof.v2"
    assert proof.action_time_certification_ref.startswith("action-time-cert:v2:")
    assert proof.lifecycle_certification_ref().startswith("lifecycle-cert:v2:")


def test_lifecycle_ref_changes_when_deploy_nonce_changes():
    original = _proof()
    changed_action_time = original.action_time_certification_payload.model_copy(
        update={"deploy_nonce": "deploy-nonce-2"}
    )
    changed = original.model_copy(
        update={
            "action_time_certification_payload": changed_action_time,
            "action_time_certification_ref": changed_action_time.certification_ref(),
        }
    )
    assert changed.lifecycle_certification_ref() != original.lifecycle_certification_ref()
