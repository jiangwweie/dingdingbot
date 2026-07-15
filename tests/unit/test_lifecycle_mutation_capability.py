from __future__ import annotations

from sqlalchemy import text

from src.application.action_time.lifecycle_mutation_capability import (
    lifecycle_mutation_capability_decision,
    set_lifecycle_mutation_capability,
)
from src.application.readmodels.lifecycle_mutation_enablement_proof import (
    ActionTimeCertificationReferenceV2,
    LaneSourceWatermarkV1,
    LifecycleMutationEnablementProof,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_pg_capability_is_shared_fail_closed_current_truth(pg_control_connection):
    pg_control_connection.execute(
        text(
            "UPDATE brc_runtime_capabilities_current "
            "SET status = 'disabled', certification_ref = 'unit:phase-one' "
            "WHERE capability_id = 'ticket_lifecycle_durable_mutation'"
        )
    )

    disabled = lifecycle_mutation_capability_decision(pg_control_connection)
    action_time = ActionTimeCertificationReferenceV2(
        stage="post_canary",
        target_runtime_head="a" * 40,
        certification_input_digest="sha256:" + "b" * 64,
        release_activation_outcome_id="activation-1",
        release_activation_source_watermark="release:1",
        lane_source_watermarks=(LaneSourceWatermarkV1(lane_scope_key="scope-1", lane_identity_key="lane-1", source_watermark="watermark-1", process_outcome_id="process-1"),),
        fact_snapshot_ids=("fact-1",),
        fact_set_digest="sha256:" + "c" * 64,
        fact_min_valid_until_ms=NOW_MS + 60_000,
        deploy_nonce="nonce-1",
    )
    proof = LifecycleMutationEnablementProof(
        target_runtime_head="a" * 40,
        lane_identity_digest="sha256:" + "d" * 64,
        action_time_certification_ref=action_time.certification_ref(),
        action_time_certification_payload=action_time,
        certification_projection_digest="sha256:" + "e" * 64,
    )
    enabled = set_lifecycle_mutation_capability(
        pg_control_connection,
        enabled=True,
        certification_ref=proof.lifecycle_certification_ref(),
        now_ms=NOW_MS,
        proof=proof,
    )

    assert disabled["enabled"] is False
    assert disabled["first_blocker"] == "lifecycle_mutation_capability_not_ready"
    assert enabled["enabled"] is True
    assert enabled["blockers"] == []
    assert enabled["capability"]["certification_ref"] == proof.lifecycle_certification_ref()
    assert enabled["capability"]["proof_schema"] == proof.proof_schema
