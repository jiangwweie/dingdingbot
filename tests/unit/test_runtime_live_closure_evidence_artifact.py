from __future__ import annotations

import json

from scripts import runtime_live_closure_evidence_artifact as artifact_builder
from scripts import runtime_live_closure_evidence_verifier as verifier


BOUNDARY_FIELDS = {
    "strategy_group_id": "MPG-001",
    "runtime_profile_id": "owner-runtime-console-v1",
    "subaccount_id": "tokyo-runtime-subaccount",
    "symbol": "MSTR/USDT:USDT",
    "side": "long",
    "notional": "100",
    "leverage": "1",
}


def _official_complete_sources() -> list[dict]:
    return [
        {
            "scope": "runtime_signal_watcher_live_signal",
            "status": "fresh_signal_ready",
            "signal_packet_id": "live-signal-packet-1",
            **BOUNDARY_FIELDS,
        },
        {
            "scope": "strategy_group_live_facts_readiness",
            "status": "ready",
            "signal_packet_id": "live-signal-packet-1",
            "required_facts_readiness_artifact_id": "facts-ready-1",
            **BOUNDARY_FIELDS,
        },
        {
            "scope": "official_entry_chain",
            "status": "official_operation_layer_submit_ready",
            "ids": {
                "signal_packet_id": "live-signal-packet-1",
                "order_candidate_id": "candidate-1",
                "runtime_grant_id": "runtime-grant-1",
                "fresh_submit_authorization_id": "fresh-auth-1",
                "action_time_finalgate_packet_id": "finalgate-1",
                "operation_layer_submit_authorization_id": "op-auth-1",
                "exchange_submit_execution_result_id": "exchange-result-1",
                "exchange_native_hard_stop_order_id": "hard-stop-1",
            },
            **BOUNDARY_FIELDS,
            "safety_invariants": {
                "live_exchange_called": True,
                "real_order_placed": True,
                "exchange_submit_accepted": True,
                "exchange_native_protection": True,
                "hard_stop_accepted": True,
                "reduce_only": True,
            },
            "exchange_order_id": "entry-order-1",
        },
        {
            "scope": "official_post_submit_close_loop",
            "status": "settled",
            "ids": {
                "exchange_submit_execution_result_id": "exchange-result-1",
                "post_submit_finalize_payload_id": "finalize-1",
                "post_submit_reconciliation_evidence_id": "reconcile-1",
                "post_submit_budget_settlement_id": "settlement-1",
                "submit_outcome_review_id": "review-1",
            },
            **BOUNDARY_FIELDS,
            "post_submit_finalize_complete": True,
            "post_submit_reconciliation_matched": True,
            "post_submit_budget_settled": True,
            "submit_outcome_review_recorded": True,
        },
    ]


def test_live_closure_evidence_artifact_builds_official_complete_artifact():
    artifact = artifact_builder.build_live_closure_evidence_artifact(
        _official_complete_sources(),
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["official_live_closure_evidence"] is True
    assert artifact["live_signal_chain_proof"] == {
        "live_watcher_signal_packet_id": "live-signal-packet-1",
        "present_evidence_keys": [
            "required_facts_readiness_artifact_id",
            "candidate_id",
        ],
        "matched_evidence_keys": [
            "required_facts_readiness_artifact_id",
            "candidate_id",
        ],
        "missing_source_match_keys": [],
    }
    assert artifact["pre_submit_authorization_chain_proof"] == {
        "fresh_submit_authorization_id": "fresh-auth-1",
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
    }
    assert artifact["live_submit_proof"] == {
        "exchange_result_present": True,
        "result_source_matched": True,
        "result_source_count": 2,
        "live_exchange_called": True,
        "real_order_placed": True,
        "exchange_accepted": True,
        "exchange_order_id_present": True,
        "exchange_submit_execution_result_id": "exchange-result-1",
    }
    assert artifact["exchange_native_protection_proof"] == {
        "hard_stop_present": True,
        "result_source_matched": True,
        "result_source_count": 1,
        "exchange_native": True,
        "hard_stop_accepted": True,
        "reduce_only": True,
        "exchange_submit_execution_result_id": "exchange-result-1",
        "exchange_native_hard_stop_order_id": "hard-stop-1",
    }
    assert artifact["post_submit_close_loop_proof"] == {
        "exchange_submit_execution_result_id": "exchange-result-1",
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
    }
    assert artifact["runtime_boundary_proof"] == {
        "source_artifact_count": 4,
        "observed_fields": [
            "strategy_group_id",
            "runtime_profile_id",
            "subaccount_id",
            "symbol",
            "side",
            "notional",
            "leverage",
        ],
        "missing_fields": [],
        "conflict_fields": [],
        "values": {
            "strategy_group_id": ["MPG-001"],
            "runtime_profile_id": ["owner-runtime-console-v1"],
            "subaccount_id": ["tokyo-runtime-subaccount"],
            "symbol": ["MSTR/USDT:USDT"],
            "side": ["long"],
            "notional": ["100"],
            "leverage": ["1"],
        },
    }
    assert artifact["reject_reasons"] == []
    assert artifact["missing_evidence_keys"] == []
    assert artifact["evidence"] == {
        "live_watcher_signal_packet_id": "live-signal-packet-1",
        "required_facts_readiness_artifact_id": "facts-ready-1",
        "candidate_id": "candidate-1",
        "runtime_grant_id": "runtime-grant-1",
        "fresh_submit_authorization_id": "fresh-auth-1",
        "action_time_finalgate_packet_id": "finalgate-1",
        "operation_layer_submit_authorization_id": "op-auth-1",
        "exchange_submit_execution_result_id": "exchange-result-1",
        "exchange_native_hard_stop_order_id": "hard-stop-1",
        "runtime_post_submit_finalize_payload_id": "finalize-1",
        "post_submit_reconciliation_evidence_id": "reconcile-1",
        "post_submit_budget_settlement_id": "settlement-1",
        "submit_outcome_review_id": "review-1",
    }
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "live_closure_complete"


def test_live_closure_evidence_artifact_keeps_partial_official_artifact_in_progress():
    artifact = artifact_builder.build_live_closure_evidence_artifact(
        _official_complete_sources()[:2],
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["reject_reasons"] == []
    assert artifact["live_submit_proof"] == {
        "exchange_result_present": False,
        "result_source_matched": False,
        "result_source_count": 0,
        "live_exchange_called": False,
        "real_order_placed": False,
        "exchange_accepted": False,
        "exchange_order_id_present": False,
    }
    assert artifact["present_evidence_keys"] == [
        "live_watcher_signal_packet_id",
        "required_facts_readiness_artifact_id",
    ]
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "live_closure_in_progress"
    assert verification["first_incomplete_stage"] == "candidate_authorization_bound"


def test_live_closure_evidence_artifact_rejects_controlled_local_cycle_shape():
    sources = _official_complete_sources()
    sources[2]["scope"] = "runtime_controlled_tiny_live_readiness_to_local_cycle_proof"
    sources[2]["status"] = "controlled_tiny_live_readiness_to_local_cycle_passed"
    sources[2]["safety_invariants"] = {
        "live_exchange_called": False,
        "real_order_placed": False,
        "controlled_fake_gateway_called": True,
        "controlled_order_lifecycle_submit_called": True,
    }

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert "controlled_in_memory_execution" in artifact["reject_reasons"]
    assert "live_exchange_not_called" in artifact["reject_reasons"]
    assert "real_order_not_placed" in artifact["reject_reasons"]
    assert artifact["live_submit_proof"] == {
        "exchange_result_present": True,
        "result_source_matched": True,
        "result_source_count": 2,
        "live_exchange_called": False,
        "real_order_placed": False,
        "exchange_accepted": False,
        "exchange_order_id_present": True,
        "exchange_submit_execution_result_id": "exchange-result-1",
    }
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_rejects_exchange_result_without_live_markers():
    sources = _official_complete_sources()
    sources[2]["safety_invariants"] = {}

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert "live_exchange_not_called" in artifact["reject_reasons"]
    assert "real_order_not_placed" in artifact["reject_reasons"]
    assert artifact["live_submit_proof"] == {
        "exchange_result_present": True,
        "result_source_matched": True,
        "result_source_count": 2,
        "live_exchange_called": False,
        "real_order_placed": False,
        "exchange_accepted": False,
        "exchange_order_id_present": True,
        "exchange_submit_execution_result_id": "exchange-result-1",
    }
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_rejects_cross_source_live_submit_markers():
    sources = _official_complete_sources()
    sources[2]["safety_invariants"] = {}
    sources.append(
        {
            "scope": "unrelated_submit_marker",
            "status": "submitted",
            "safety_invariants": {
                "live_exchange_called": True,
                "real_order_placed": True,
                "exchange_submit_accepted": True,
            },
            "exchange_order_id": "unrelated-entry-order",
        }
    )

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["live_submit_proof"] == {
        "exchange_result_present": True,
        "result_source_matched": True,
        "result_source_count": 2,
        "live_exchange_called": False,
        "real_order_placed": False,
        "exchange_accepted": False,
        "exchange_order_id_present": True,
        "exchange_submit_execution_result_id": "exchange-result-1",
    }
    assert "live_exchange_not_called" in artifact["reject_reasons"]
    assert "real_order_not_placed" in artifact["reject_reasons"]
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_rejects_exchange_result_without_acceptance():
    sources = _official_complete_sources()
    sources[2]["safety_invariants"]["exchange_submit_accepted"] = False
    sources[2].pop("exchange_order_id")

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["live_submit_proof"] == {
        "exchange_result_present": True,
        "result_source_matched": True,
        "result_source_count": 2,
        "live_exchange_called": True,
        "real_order_placed": True,
        "exchange_accepted": False,
        "exchange_order_id_present": False,
        "exchange_submit_execution_result_id": "exchange-result-1",
    }
    assert "exchange_submit_not_accepted" in artifact["reject_reasons"]
    assert "exchange_order_id_missing" in artifact["reject_reasons"]
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_rejects_runtime_boundary_mismatch():
    sources = _official_complete_sources()
    sources[1]["symbol"] = "TSLA/USDT:USDT"

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["runtime_boundary_proof"]["conflict_fields"] == ["symbol"]
    assert artifact["runtime_boundary_proof"]["values"]["symbol"] == [
        "MSTR/USDT:USDT",
        "TSLA/USDT:USDT",
    ]
    assert "symbol_boundary_mismatch" in artifact["reject_reasons"]
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_rejects_runtime_boundary_missing_after_candidate():
    sources = _official_complete_sources()
    for source in sources:
        source.pop("subaccount_id", None)
        source.pop("notional", None)

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["runtime_boundary_proof"]["missing_fields"] == [
        "subaccount_id",
        "notional",
    ]
    assert "subaccount_boundary_missing" in artifact["reject_reasons"]
    assert "notional_boundary_missing" in artifact["reject_reasons"]
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_rejects_legacy_required_facts_packet_id():
    sources = _official_complete_sources()
    facts_source = sources[1]
    facts_source["required_facts_readiness_packet_id"] = facts_source.pop(
        "required_facts_readiness_artifact_id"
    )

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert "required_facts_readiness_artifact_id" not in artifact["evidence"]
    assert "required_facts_readiness_packet_id" not in artifact["evidence"]
    assert "required_facts_signal_source_missing" in artifact["reject_reasons"]
    assert artifact["live_signal_chain_proof"]["present_evidence_keys"] == [
        "candidate_id"
    ]
    assert artifact["live_signal_chain_proof"]["matched_evidence_keys"] == [
        "candidate_id"
    ]


def test_live_closure_evidence_artifact_rejects_unbound_live_signal_chain():
    sources = _official_complete_sources()
    sources[1].pop("signal_packet_id")
    sources[2]["ids"].pop("signal_packet_id")

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["live_signal_chain_proof"] == {
        "live_watcher_signal_packet_id": "live-signal-packet-1",
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
    assert "required_facts_signal_source_missing" in artifact["reject_reasons"]
    assert "candidate_signal_source_missing" in artifact["reject_reasons"]
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_rejects_unbound_pre_submit_authorization_chain():
    sources = _official_complete_sources()
    sources[2]["ids"].pop("action_time_finalgate_packet_id")
    sources[2]["ids"].pop("operation_layer_submit_authorization_id")
    sources.append(
        {
            "scope": "stale_operation_layer_arm_evidence",
            "status": "official_operation_layer_submit_ready",
            "ids": {
                "fresh_submit_authorization_id": "stale-auth",
                "action_time_finalgate_packet_id": "finalgate-1",
                "operation_layer_submit_authorization_id": "op-auth-1",
            },
        }
    )

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["pre_submit_authorization_chain_proof"] == {
        "fresh_submit_authorization_id": "fresh-auth-1",
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
    assert "finalgate_authorization_chain_source_missing" in artifact["reject_reasons"]
    assert (
        "operation_layer_authorization_chain_source_missing"
        in artifact["reject_reasons"]
    )
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_rejects_unbound_exchange_native_protection():
    sources = _official_complete_sources()
    sources[2]["ids"].pop("exchange_native_hard_stop_order_id")
    sources.append(
        {
            "scope": "unrelated_hard_stop_source",
            "status": "protected",
            "ids": {"exchange_native_hard_stop_order_id": "hard-stop-1"},
        }
    )

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["exchange_native_protection_proof"] == {
        "hard_stop_present": True,
        "result_source_matched": False,
        "result_source_count": 1,
        "exchange_native": False,
        "hard_stop_accepted": False,
        "reduce_only": False,
        "exchange_submit_execution_result_id": "exchange-result-1",
        "exchange_native_hard_stop_order_id": "hard-stop-1",
    }
    assert "exchange_native_protection_result_source_missing" in artifact["reject_reasons"]
    assert "local_only_stop" in artifact["reject_reasons"]
    assert "hard_stop_not_accepted" in artifact["reject_reasons"]
    assert "hard_stop_not_reduce_only" in artifact["reject_reasons"]
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_rejects_local_unaccepted_non_reduce_only_stop():
    sources = _official_complete_sources()
    sources[2]["safety_invariants"]["exchange_native_protection"] = False
    sources[2]["safety_invariants"]["hard_stop_accepted"] = False
    sources[2]["safety_invariants"]["reduce_only"] = False

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["exchange_native_protection_proof"] == {
        "hard_stop_present": True,
        "result_source_matched": True,
        "result_source_count": 1,
        "exchange_native": False,
        "hard_stop_accepted": False,
        "reduce_only": False,
        "exchange_submit_execution_result_id": "exchange-result-1",
        "exchange_native_hard_stop_order_id": "hard-stop-1",
    }
    assert "local_only_stop" in artifact["reject_reasons"]
    assert "hard_stop_not_accepted" in artifact["reject_reasons"]
    assert "hard_stop_not_reduce_only" in artifact["reject_reasons"]
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_rejects_unbound_post_submit_close_loop():
    sources = _official_complete_sources()
    sources[3]["ids"].pop("exchange_submit_execution_result_id")

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["post_submit_close_loop_proof"] == {
        "exchange_submit_execution_result_id": "exchange-result-1",
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
    assert "post_submit_finalize_result_source_missing" in artifact["reject_reasons"]
    assert "post_submit_close_loop_result_source_missing" in artifact["reject_reasons"]
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_rejects_incomplete_post_submit_truth():
    sources = _official_complete_sources()
    sources[3]["post_submit_finalize_complete"] = False
    sources[3]["post_submit_reconciliation_matched"] = False
    sources[3]["post_submit_budget_settled"] = False
    sources[3]["submit_outcome_review_recorded"] = False

    artifact = artifact_builder.build_live_closure_evidence_artifact(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert artifact["post_submit_close_loop_proof"] == {
        "exchange_submit_execution_result_id": "exchange-result-1",
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
    assert "post_submit_finalize_not_complete" in artifact["reject_reasons"]
    assert "post_submit_reconciliation_not_matched" in artifact["reject_reasons"]
    assert "post_submit_budget_not_settled" in artifact["reject_reasons"]
    assert "submit_outcome_review_not_recorded" in artifact["reject_reasons"]
    verification = verifier.build_live_closure_evidence_verification(artifact)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_artifact_cli_writes_artifact_and_verification(tmp_path, capsys):
    input_json = tmp_path / "source.json"
    output_json = tmp_path / "artifact.json"
    verification_json = tmp_path / "verification.json"
    input_json.write_text(
        json.dumps({"sources": _official_complete_sources()}),
        encoding="utf-8",
    )

    assert artifact_builder.main(
        [
            "--input-json",
            str(input_json),
            "--official-live-source",
            "--output-json",
            str(output_json),
            "--verify-output-json",
            str(verification_json),
        ]
    ) == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    verification = json.loads(verification_json.read_text(encoding="utf-8"))
    assert artifact["status"] == "live_closure_evidence_artifact_built"
    assert verification["status"] == "live_closure_complete"
