from __future__ import annotations

import json

from scripts import runtime_live_closure_evidence_verifier as verifier
from scripts import runtime_live_cutover_readiness as live_cutover


def _complete_evidence() -> dict[str, str]:
    contract = live_cutover.build_live_closure_cutover_contract()
    return {
        key: f"{key}-1"
        for key in contract["required_evidence_keys"]
    }


def _official_artifact(
    evidence: dict[str, object],
    *,
    live_submit_proof: dict[str, object] | None = None,
) -> dict[str, object]:
    artifact = {
        "source_kind": "official_live_closure_evidence",
        "evidence": evidence,
        "runtime_boundary_proof": _runtime_boundary_proof(),
    }
    if "exchange_submit_execution_result_id" in evidence:
        exchange_submit_execution_result_id = _evidence_id(
            evidence["exchange_submit_execution_result_id"]
        )
        if "live_watcher_signal_packet_id" in evidence:
            artifact["live_signal_chain_proof"] = _live_signal_chain_proof(evidence)
        if "fresh_submit_authorization_id" in evidence:
            artifact["pre_submit_authorization_chain_proof"] = (
                _pre_submit_authorization_chain_proof(evidence)
            )
        artifact["live_submit_proof"] = live_submit_proof or {
            "exchange_result_present": True,
            "result_source_matched": True,
            "result_source_count": 1,
            "live_exchange_called": True,
            "real_order_placed": True,
            "exchange_accepted": True,
            "exchange_order_id_present": True,
            "exchange_submit_execution_result_id": exchange_submit_execution_result_id,
        }
        if "exchange_native_hard_stop_order_id" in evidence:
            artifact["exchange_native_protection_proof"] = {
                "hard_stop_present": True,
                "result_source_matched": True,
                "result_source_count": 1,
                "exchange_native": True,
                "hard_stop_accepted": True,
                "reduce_only": True,
                "exchange_submit_execution_result_id": exchange_submit_execution_result_id,
                "exchange_native_hard_stop_order_id": _evidence_id(
                    evidence["exchange_native_hard_stop_order_id"]
                ),
            }
        close_loop_keys = [
            key
            for key in (
                "runtime_post_submit_finalize_payload_id",
                "post_submit_reconciliation_evidence_id",
                "post_submit_budget_settlement_id",
                "submit_outcome_review_id",
            )
            if key in evidence
        ]
        if close_loop_keys:
            artifact["post_submit_close_loop_proof"] = {
                "exchange_submit_execution_result_id": exchange_submit_execution_result_id,
                "present_evidence_keys": close_loop_keys,
                "matched_evidence_keys": close_loop_keys,
                "missing_source_match_keys": [],
                "finalize_complete": True,
                "reconciliation_matched": True,
                "budget_settled": True,
                "review_recorded": True,
            }
    return artifact


def _runtime_boundary_proof(
    *,
    missing_fields: list[str] | None = None,
    conflict_fields: list[str] | None = None,
) -> dict[str, object]:
    values = {
        "strategy_group_id": ["MPG-001"],
        "runtime_profile_id": ["owner-runtime-console-v1"],
        "subaccount_id": ["tokyo-runtime-subaccount"],
        "symbol": ["MSTR/USDT:USDT"],
        "side": ["long"],
        "notional": ["100"],
        "leverage": ["1"],
    }
    for field in missing_fields or []:
        values[field] = []
    if conflict_fields:
        for field in conflict_fields:
            values[field].append(f"other-{field}")
    return {
        "source_artifact_count": 4,
        "observed_fields": [field for field, items in values.items() if items],
        "missing_fields": missing_fields or [],
        "conflict_fields": conflict_fields or [],
        "values": values,
    }


def _live_signal_chain_proof(evidence: dict[str, object]) -> dict[str, object]:
    live_signal_keys = [
        key
        for key in (
            "required_facts_readiness_artifact_id",
            "candidate_id",
        )
        if key in evidence
    ]
    return {
        "live_watcher_signal_packet_id": _evidence_id(
            evidence["live_watcher_signal_packet_id"]
        ),
        "present_evidence_keys": live_signal_keys,
        "matched_evidence_keys": live_signal_keys,
        "missing_source_match_keys": [],
    }


def _pre_submit_authorization_chain_proof(
    evidence: dict[str, object],
) -> dict[str, object]:
    pre_submit_keys = [
        key
        for key in (
            "candidate_id",
            "runtime_grant_id",
            "action_time_finalgate_packet_id",
            "operation_layer_submit_authorization_id",
        )
        if key in evidence
    ]
    return {
        "fresh_submit_authorization_id": _evidence_id(
            evidence["fresh_submit_authorization_id"]
        ),
        "present_evidence_keys": pre_submit_keys,
        "matched_evidence_keys": pre_submit_keys,
        "missing_source_match_keys": [],
    }


def _evidence_id(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        nested = value.get("id")
        if isinstance(nested, str):
            return nested
    raise AssertionError(f"Cannot derive test evidence id from {value!r}")


def test_live_closure_evidence_verifier_marks_complete_when_all_contract_keys_present():
    artifact = verifier.build_live_closure_evidence_verification(
        _official_artifact(_complete_evidence()),
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "live_closure_complete"
    assert artifact["owner_state"] == "完成"
    assert artifact["official_live_source_ready"] is True
    assert artifact["stage_count"] == 9
    assert artifact["completed_stage_count"] == 9
    assert artifact["first_incomplete_stage"] is None
    assert artifact["missing_evidence_keys"] == []
    assert artifact["completion"] == {
        "first_bounded_real_order_complete": True,
        "real_order_closure_proven": True,
        "mock_signal_treated_as_real_signal": False,
        "disabled_smoke_treated_as_real_execution_proof": False,
    }
    assert artifact["safety_invariants"]["exchange_write_called"] is False


def test_live_closure_evidence_verifier_marks_in_progress_at_first_missing_stage():
    evidence = _complete_evidence()
    evidence.pop("exchange_native_hard_stop_order_id")
    evidence.pop("runtime_post_submit_finalize_payload_id")

    artifact = verifier.build_live_closure_evidence_verification(
        _official_artifact(evidence),
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "live_closure_in_progress"
    assert artifact["owner_state"] == "处理中"
    assert artifact["completed_stage_count"] == 6
    assert artifact["first_incomplete_stage"] == "exchange_native_protection"
    assert artifact["missing_evidence_keys"] == [
        "exchange_native_hard_stop_order_id",
        "runtime_post_submit_finalize_payload_id",
    ]
    exchange_native_stage = next(
        stage for stage in artifact["stages"] if stage["name"] == "exchange_native_protection"
    )
    assert exchange_native_stage["status"] == "missing_evidence"
    assert exchange_native_stage["missing_evidence_keys"] == [
        "exchange_native_hard_stop_order_id"
    ]
    finalize_stage = next(
        stage for stage in artifact["stages"] if stage["name"] == "post_submit_finalize"
    )
    assert finalize_stage["status"] == "blocked_by_previous_stage"


def test_live_closure_evidence_verifier_rejects_synthetic_or_disabled_live_proof():
    evidence = _complete_evidence()

    artifact = verifier.build_live_closure_evidence_verification(
        {
            "source_kind": "official_live_closure_evidence",
            "evidence": evidence,
            "live_signal_chain_proof": {
                "live_watcher_signal_packet_id": "live_watcher_signal_packet_id-1",
                "present_evidence_keys": [
                    "required_facts_readiness_artifact_id",
                    "candidate_id",
                ],
                "matched_evidence_keys": [
                    "required_facts_readiness_artifact_id",
                    "candidate_id",
                ],
                "missing_source_match_keys": [],
            },
            "live_submit_proof": {
                "exchange_result_present": True,
                "result_source_matched": True,
                "result_source_count": 1,
                "live_exchange_called": True,
                "real_order_placed": True,
                "exchange_accepted": True,
                "exchange_order_id_present": True,
                "exchange_submit_execution_result_id": "exchange_submit_execution_result_id-1",
            },
            "exchange_native_protection_proof": {
                "hard_stop_present": True,
                "result_source_matched": True,
                "result_source_count": 1,
                "exchange_native": True,
                "hard_stop_accepted": True,
                "reduce_only": True,
                "exchange_submit_execution_result_id": "exchange_submit_execution_result_id-1",
                "exchange_native_hard_stop_order_id": (
                    "exchange_native_hard_stop_order_id-1"
                ),
            },
            "pre_submit_authorization_chain_proof": {
                "fresh_submit_authorization_id": "fresh_submit_authorization_id-1",
                "present_evidence_keys": [
                    "candidate_id",
                    "runtime_grant_id",
                    "action_time_finalgate_packet_id",
                    "operation_layer_submit_authorization_id",
                ],
                "matched_evidence_keys": [
                    "candidate_id",
                    "runtime_grant_id",
                    "action_time_finalgate_packet_id",
                    "operation_layer_submit_authorization_id",
                ],
                "missing_source_match_keys": [],
            },
            "post_submit_close_loop_proof": {
                "exchange_submit_execution_result_id": "exchange_submit_execution_result_id-1",
                "present_evidence_keys": [
                    "runtime_post_submit_finalize_payload_id",
                    "post_submit_reconciliation_evidence_id",
                    "post_submit_budget_settlement_id",
                    "submit_outcome_review_id",
                ],
                "matched_evidence_keys": [
                    "runtime_post_submit_finalize_payload_id",
                    "post_submit_reconciliation_evidence_id",
                    "post_submit_budget_settlement_id",
                    "submit_outcome_review_id",
                ],
                "missing_source_match_keys": [],
                "finalize_complete": True,
                "reconciliation_matched": True,
                "budget_settled": True,
                "review_recorded": True,
            },
            "runtime_boundary_proof": _runtime_boundary_proof(),
            "reject_reasons": ["replay_signal", "disabled_smoke_only"],
        },
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "blocked_live_closure_rejected"
    assert artifact["owner_state"] == "需要介入"
    assert artifact["completion"] == {
        "first_bounded_real_order_complete": False,
        "real_order_closure_proven": False,
        "mock_signal_treated_as_real_signal": True,
        "disabled_smoke_treated_as_real_execution_proof": True,
    }
    rejected = [
        stage
        for stage in artifact["stages"]
        if stage["status"] == "rejected"
    ]
    assert [stage["name"] for stage in rejected] == [
        "live_fresh_signal",
        "official_operation_layer_ready",
    ]


def test_live_closure_evidence_verifier_rejects_missing_live_submit_proof():
    evidence = _complete_evidence()
    artifact = verifier.build_live_closure_evidence_verification(
        {
            "source_kind": "official_live_closure_evidence",
            "evidence": evidence,
            "live_signal_chain_proof": _live_signal_chain_proof(evidence),
            "pre_submit_authorization_chain_proof": (
                _pre_submit_authorization_chain_proof(evidence)
            ),
            "runtime_boundary_proof": _runtime_boundary_proof(),
        },
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "blocked_live_closure_rejected"
    assert artifact["owner_state"] == "需要介入"
    assert artifact["completion"]["first_bounded_real_order_complete"] is False
    assert artifact["reject_reasons"] == ["live_submit_proof_missing"]
    real_exchange_stage = next(
        stage for stage in artifact["stages"] if stage["name"] == "real_exchange_acceptance"
    )
    assert real_exchange_stage["status"] == "rejected"
    assert real_exchange_stage["reject_reasons"] == ["live_submit_proof_missing"]


def test_live_closure_evidence_verifier_rejects_false_live_submit_proof():
    artifact = verifier.build_live_closure_evidence_verification(
        _official_artifact(
            _complete_evidence(),
            live_submit_proof={
                "exchange_result_present": True,
                "result_source_matched": True,
                "result_source_count": 1,
                "live_exchange_called": False,
                "real_order_placed": False,
                "exchange_accepted": True,
                "exchange_order_id_present": True,
                "exchange_submit_execution_result_id": "exchange_submit_execution_result_id-1",
            },
        ),
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "blocked_live_closure_rejected"
    assert artifact["completion"]["real_order_closure_proven"] is False
    assert artifact["reject_reasons"] == [
        "live_exchange_not_called",
        "real_order_not_placed",
    ]


def test_live_closure_evidence_verifier_rejects_unaccepted_live_submit_proof():
    artifact = verifier.build_live_closure_evidence_verification(
        _official_artifact(
            _complete_evidence(),
            live_submit_proof={
                "exchange_result_present": True,
                "result_source_matched": True,
                "result_source_count": 1,
                "live_exchange_called": True,
                "real_order_placed": True,
                "exchange_accepted": False,
                "exchange_order_id_present": False,
                "exchange_submit_execution_result_id": "exchange_submit_execution_result_id-1",
            },
        ),
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "blocked_live_closure_rejected"
    assert artifact["completion"]["real_order_closure_proven"] is False
    assert artifact["reject_reasons"] == [
        "exchange_order_id_missing",
        "exchange_submit_not_accepted",
    ]
    real_exchange_stage = next(
        stage
        for stage in artifact["stages"]
        if stage["name"] == "real_exchange_acceptance"
    )
    assert real_exchange_stage["status"] == "rejected"
    assert real_exchange_stage["reject_reasons"] == [
        "exchange_submit_not_accepted",
        "exchange_order_id_missing",
    ]


def test_live_closure_evidence_verifier_rejects_live_submit_proof_result_id_mismatch():
    artifact = verifier.build_live_closure_evidence_verification(
        _official_artifact(
            _complete_evidence(),
            live_submit_proof={
                "exchange_result_present": True,
                "result_source_matched": True,
                "result_source_count": 1,
                "live_exchange_called": True,
                "real_order_placed": True,
                "exchange_accepted": True,
                "exchange_order_id_present": True,
                "exchange_submit_execution_result_id": "other-exchange-result",
            },
        ),
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "blocked_live_closure_rejected"
    assert artifact["owner_state"] == "需要介入"
    assert artifact["completion"]["first_bounded_real_order_complete"] is False
    assert artifact["completion"]["real_order_closure_proven"] is False
    assert artifact["reject_reasons"] == ["live_submit_proof_result_id_mismatch"]
    real_exchange_stage = next(
        stage
        for stage in artifact["stages"]
        if stage["name"] == "real_exchange_acceptance"
    )
    assert real_exchange_stage["status"] == "rejected"
    assert real_exchange_stage["reject_reasons"] == [
        "live_submit_proof_result_id_mismatch"
    ]


def test_live_closure_evidence_verifier_rejects_live_submit_proof_without_source_match():
    artifact = verifier.build_live_closure_evidence_verification(
        _official_artifact(
            _complete_evidence(),
            live_submit_proof={
                "exchange_result_present": True,
                "result_source_matched": False,
                "result_source_count": 0,
                "live_exchange_called": True,
                "real_order_placed": True,
                "exchange_accepted": True,
                "exchange_order_id_present": True,
                "exchange_submit_execution_result_id": "exchange_submit_execution_result_id-1",
            },
        ),
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "blocked_live_closure_rejected"
    assert artifact["owner_state"] == "需要介入"
    assert artifact["completion"]["first_bounded_real_order_complete"] is False
    assert artifact["completion"]["real_order_closure_proven"] is False
    assert artifact["reject_reasons"] == ["live_submit_proof_result_source_missing"]
    real_exchange_stage = next(
        stage
        for stage in artifact["stages"]
        if stage["name"] == "real_exchange_acceptance"
    )
    assert real_exchange_stage["status"] == "rejected"
    assert real_exchange_stage["reject_reasons"] == [
        "live_submit_proof_result_source_missing"
    ]


def test_live_closure_evidence_verifier_rejects_missing_live_signal_chain_proof():
    artifact = _official_artifact(_complete_evidence())
    artifact.pop("live_signal_chain_proof")

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["owner_state"] == "需要介入"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["reject_reasons"] == ["live_signal_chain_proof_missing"]
    rejected = [
        stage
        for stage in verification["stages"]
        if stage["status"] == "rejected"
    ]
    assert [stage["name"] for stage in rejected] == [
        "required_facts_ready",
        "candidate_authorization_bound",
    ]


def test_live_closure_evidence_verifier_rejects_missing_runtime_boundary_proof():
    artifact = _official_artifact(_complete_evidence())
    artifact.pop("runtime_boundary_proof")

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["owner_state"] == "需要介入"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["reject_reasons"] == ["runtime_boundary_proof_missing"]
    rejected = [
        stage
        for stage in verification["stages"]
        if stage["status"] == "rejected"
    ]
    assert [stage["name"] for stage in rejected] == [
        "candidate_authorization_bound",
        "action_time_finalgate_passed",
        "official_operation_layer_ready",
        "real_exchange_acceptance",
        "exchange_native_protection",
        "post_submit_finalize",
        "reconciliation_settlement_review",
    ]


def test_live_closure_evidence_verifier_rejects_runtime_boundary_mismatch():
    artifact = _official_artifact(_complete_evidence())
    artifact["runtime_boundary_proof"] = _runtime_boundary_proof(
        conflict_fields=["symbol", "leverage"]
    )

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["reject_reasons"] == [
        "leverage_boundary_mismatch",
        "symbol_boundary_mismatch",
    ]
    rejected = [
        stage
        for stage in verification["stages"]
        if stage["status"] == "rejected"
    ]
    assert [stage["name"] for stage in rejected] == [
        "candidate_authorization_bound",
        "action_time_finalgate_passed",
        "official_operation_layer_ready",
        "real_exchange_acceptance",
        "exchange_native_protection",
        "post_submit_finalize",
        "reconciliation_settlement_review",
    ]


def test_live_closure_evidence_verifier_rejects_runtime_boundary_missing_fields():
    artifact = _official_artifact(_complete_evidence())
    artifact["runtime_boundary_proof"] = _runtime_boundary_proof(
        missing_fields=["subaccount_id", "notional"]
    )

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["reject_reasons"] == [
        "notional_boundary_missing",
        "subaccount_boundary_missing",
    ]
    rejected = [
        stage
        for stage in verification["stages"]
        if stage["status"] == "rejected"
    ]
    assert [stage["name"] for stage in rejected] == [
        "candidate_authorization_bound",
        "action_time_finalgate_passed",
        "official_operation_layer_ready",
        "real_exchange_acceptance",
        "exchange_native_protection",
        "post_submit_finalize",
        "reconciliation_settlement_review",
    ]


def test_live_closure_evidence_verifier_rejects_unbound_live_signal_chain():
    artifact = _official_artifact(_complete_evidence())
    artifact["live_signal_chain_proof"] = {
        "live_watcher_signal_packet_id": "live_watcher_signal_packet_id-1",
        "present_evidence_keys": [
            "required_facts_readiness_artifact_id",
            "candidate_id",
        ],
        "matched_evidence_keys": [],
        "missing_source_match_keys": [
            "required_facts_readiness_artifact_id",
            "candidate_id",
        ],
    }

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["reject_reasons"] == [
        "candidate_signal_source_missing",
        "required_facts_signal_source_missing",
    ]


def test_live_closure_evidence_verifier_rejects_missing_pre_submit_authorization_chain_proof():
    artifact = _official_artifact(_complete_evidence())
    artifact.pop("pre_submit_authorization_chain_proof")

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["owner_state"] == "需要介入"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["reject_reasons"] == [
        "pre_submit_authorization_chain_proof_missing"
    ]
    rejected = [
        stage
        for stage in verification["stages"]
        if stage["status"] == "rejected"
    ]
    assert [stage["name"] for stage in rejected] == [
        "candidate_authorization_bound",
        "action_time_finalgate_passed",
        "official_operation_layer_ready",
    ]


def test_live_closure_evidence_verifier_rejects_unbound_pre_submit_authorization_chain():
    artifact = _official_artifact(_complete_evidence())
    artifact["pre_submit_authorization_chain_proof"] = {
        "fresh_submit_authorization_id": "fresh_submit_authorization_id-1",
        "present_evidence_keys": [
            "candidate_id",
            "runtime_grant_id",
            "action_time_finalgate_packet_id",
            "operation_layer_submit_authorization_id",
        ],
        "matched_evidence_keys": [
            "candidate_id",
            "runtime_grant_id",
        ],
        "missing_source_match_keys": [
            "action_time_finalgate_packet_id",
            "operation_layer_submit_authorization_id",
        ],
    }

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["reject_reasons"] == [
        "finalgate_authorization_chain_source_missing",
        "operation_layer_authorization_chain_source_missing",
    ]
    rejected = [
        stage
        for stage in verification["stages"]
        if stage["status"] == "rejected"
    ]
    assert [stage["name"] for stage in rejected] == [
        "action_time_finalgate_passed",
        "official_operation_layer_ready",
    ]


def test_live_closure_evidence_verifier_rejects_missing_post_submit_close_loop_proof():
    artifact = _official_artifact(_complete_evidence())
    artifact.pop("post_submit_close_loop_proof")

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["owner_state"] == "需要介入"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["completion"]["real_order_closure_proven"] is False
    assert verification["reject_reasons"] == ["post_submit_close_loop_proof_missing"]
    rejected = [
        stage
        for stage in verification["stages"]
        if stage["status"] == "rejected"
    ]
    assert [stage["name"] for stage in rejected] == [
        "post_submit_finalize",
        "reconciliation_settlement_review",
    ]


def test_live_closure_evidence_verifier_rejects_missing_exchange_native_protection_proof():
    artifact = _official_artifact(_complete_evidence())
    artifact.pop("exchange_native_protection_proof")

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["owner_state"] == "需要介入"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["completion"]["real_order_closure_proven"] is False
    assert verification["reject_reasons"] == [
        "exchange_native_protection_proof_missing"
    ]
    rejected = [
        stage
        for stage in verification["stages"]
        if stage["status"] == "rejected"
    ]
    assert [stage["name"] for stage in rejected] == [
        "exchange_native_protection"
    ]


def test_live_closure_evidence_verifier_rejects_unbound_exchange_native_protection():
    artifact = _official_artifact(_complete_evidence())
    artifact["exchange_native_protection_proof"] = {
        "hard_stop_present": True,
        "result_source_matched": False,
        "result_source_count": 1,
        "exchange_native": True,
        "hard_stop_accepted": True,
        "reduce_only": True,
        "exchange_submit_execution_result_id": "exchange_submit_execution_result_id-1",
        "exchange_native_hard_stop_order_id": "exchange_native_hard_stop_order_id-1",
    }

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["reject_reasons"] == [
        "exchange_native_protection_result_source_missing"
    ]


def test_live_closure_evidence_verifier_rejects_local_unaccepted_non_reduce_only_stop():
    artifact = _official_artifact(_complete_evidence())
    artifact["exchange_native_protection_proof"] = {
        "hard_stop_present": True,
        "result_source_matched": True,
        "result_source_count": 1,
        "exchange_native": False,
        "hard_stop_accepted": False,
        "reduce_only": False,
        "exchange_submit_execution_result_id": "exchange_submit_execution_result_id-1",
        "exchange_native_hard_stop_order_id": "exchange_native_hard_stop_order_id-1",
    }

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["reject_reasons"] == [
        "hard_stop_not_accepted",
        "hard_stop_not_reduce_only",
        "local_only_stop",
    ]


def test_live_closure_evidence_verifier_rejects_unbound_post_submit_close_loop_proof():
    artifact = _official_artifact(_complete_evidence())
    artifact["post_submit_close_loop_proof"] = {
        "exchange_submit_execution_result_id": "exchange_submit_execution_result_id-1",
        "present_evidence_keys": [
            "runtime_post_submit_finalize_payload_id",
            "post_submit_reconciliation_evidence_id",
            "post_submit_budget_settlement_id",
            "submit_outcome_review_id",
        ],
        "matched_evidence_keys": [],
        "missing_source_match_keys": [
            "runtime_post_submit_finalize_payload_id",
            "post_submit_reconciliation_evidence_id",
            "post_submit_budget_settlement_id",
            "submit_outcome_review_id",
        ],
        "finalize_complete": False,
        "reconciliation_matched": False,
        "budget_settled": False,
        "review_recorded": False,
    }

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["reject_reasons"] == [
        "post_submit_close_loop_result_source_missing",
        "post_submit_finalize_result_source_missing",
    ]


def test_live_closure_evidence_verifier_rejects_incomplete_post_submit_truth():
    artifact = _official_artifact(_complete_evidence())
    artifact["post_submit_close_loop_proof"] = {
        "exchange_submit_execution_result_id": "exchange_submit_execution_result_id-1",
        "present_evidence_keys": [
            "runtime_post_submit_finalize_payload_id",
            "post_submit_reconciliation_evidence_id",
            "post_submit_budget_settlement_id",
            "submit_outcome_review_id",
        ],
        "matched_evidence_keys": [
            "runtime_post_submit_finalize_payload_id",
            "post_submit_reconciliation_evidence_id",
            "post_submit_budget_settlement_id",
            "submit_outcome_review_id",
        ],
        "missing_source_match_keys": [],
        "finalize_complete": False,
        "reconciliation_matched": False,
        "budget_settled": False,
        "review_recorded": False,
    }

    verification = verifier.build_live_closure_evidence_verification(
        artifact,
        generated_at_ms=1781755000000,
    )

    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False
    assert verification["reject_reasons"] == [
        "post_submit_budget_not_settled",
        "post_submit_finalize_not_complete",
        "post_submit_reconciliation_not_matched",
        "submit_outcome_review_not_recorded",
    ]


def test_live_closure_evidence_verifier_rejects_duplicate_required_evidence_id():
    evidence = _complete_evidence()
    evidence["required_facts_readiness_artifact_id"] = evidence[
        "live_watcher_signal_packet_id"
    ]

    artifact = verifier.build_live_closure_evidence_verification(
        _official_artifact(evidence),
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "blocked_live_closure_rejected"
    assert artifact["owner_state"] == "需要介入"
    assert artifact["completion"]["first_bounded_real_order_complete"] is False
    assert artifact["completion"]["real_order_closure_proven"] is False
    assert artifact["reject_reasons"] == ["duplicate_evidence_id"]


def test_live_closure_evidence_verifier_rejects_malformed_required_evidence_id():
    evidence: dict[str, object] = _complete_evidence()
    evidence["candidate_id"] = {"candidate": "candidate-1"}
    evidence["runtime_grant_id"] = True

    artifact = verifier.build_live_closure_evidence_verification(
        _official_artifact(evidence),  # type: ignore[arg-type]
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "blocked_live_closure_rejected"
    assert artifact["owner_state"] == "需要介入"
    assert artifact["completion"]["first_bounded_real_order_complete"] is False
    assert artifact["completion"]["real_order_closure_proven"] is False
    assert artifact["reject_reasons"] == ["malformed_evidence_id"]
    assert artifact["malformed_evidence_keys"] == [
        "candidate_id",
        "runtime_grant_id",
    ]
    assert artifact["missing_evidence_keys"] == [
        "candidate_id",
        "runtime_grant_id",
    ]


def test_live_closure_evidence_verifier_accepts_structured_evidence_id_values():
    evidence = {
        key: {"id": f"{key}-1"}
        for key in live_cutover.build_live_closure_cutover_contract()[
            "required_evidence_keys"
        ]
    }

    artifact = verifier.build_live_closure_evidence_verification(
        _official_artifact(evidence),  # type: ignore[arg-type]
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "live_closure_complete"
    assert artifact["missing_evidence_keys"] == []
    assert artifact["malformed_evidence_keys"] == []
    assert artifact["reject_reasons"] == []


def test_live_closure_evidence_verifier_rejects_unmarked_complete_shape():
    artifact = verifier.build_live_closure_evidence_verification(
        {"evidence": _complete_evidence()},
        generated_at_ms=1781755000000,
    )

    assert artifact["status"] == "blocked_live_closure_rejected"
    assert artifact["official_live_source_ready"] is False
    assert artifact["reject_reasons"] == ["official_live_closure_source_missing"]
    assert artifact["completion"]["first_bounded_real_order_complete"] is False
    assert artifact["completion"]["real_order_closure_proven"] is False


def test_live_closure_evidence_verifier_cli_writes_packet(tmp_path, capsys):
    evidence_json = tmp_path / "live-evidence.json"
    output_json = tmp_path / "live-verification.json"
    evidence_json.write_text(
        json.dumps(_official_artifact(_complete_evidence())),
        encoding="utf-8",
    )

    assert verifier.main(
        [
            "--evidence-json",
            str(evidence_json),
            "--output-json",
            str(output_json),
        ]
    ) == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert artifact["status"] == "live_closure_complete"
