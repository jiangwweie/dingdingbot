from __future__ import annotations

import json

from scripts import runtime_live_closure_evidence_packet as packet_builder
from scripts import runtime_live_closure_evidence_verifier as verifier


def _official_complete_sources() -> list[dict]:
    return [
        {
            "scope": "runtime_signal_watcher_live_signal",
            "status": "fresh_signal_ready",
            "signal_packet_id": "live-signal-packet-1",
        },
        {
            "scope": "strategy_group_live_facts_readiness",
            "status": "ready",
            "required_facts_readiness_packet_id": "facts-ready-1",
        },
        {
            "scope": "official_entry_chain",
            "status": "official_operation_layer_submit_ready",
            "ids": {
                "order_candidate_id": "candidate-1",
                "runtime_grant_id": "runtime-grant-1",
                "fresh_submit_authorization_id": "fresh-auth-1",
                "action_time_finalgate_packet_id": "finalgate-1",
                "operation_layer_submit_authorization_id": "op-auth-1",
                "exchange_submit_execution_result_id": "exchange-result-1",
                "exchange_native_hard_stop_order_id": "hard-stop-1",
            },
            "safety_invariants": {
                "live_exchange_called": True,
                "real_order_placed": True,
            },
        },
        {
            "scope": "official_post_submit_close_loop",
            "status": "settled",
            "ids": {
                "exchange_submit_execution_result_id": "exchange-result-1",
                "post_submit_finalize_packet_id": "finalize-1",
                "post_submit_reconciliation_evidence_id": "reconcile-1",
                "post_submit_budget_settlement_id": "settlement-1",
                "submit_outcome_review_id": "review-1",
            },
        },
    ]


def test_live_closure_evidence_packet_builds_official_complete_packet():
    packet = packet_builder.build_live_closure_evidence_packet(
        _official_complete_sources(),
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert packet["official_live_closure_evidence"] is True
    assert packet["live_submit_proof"] == {
        "exchange_result_present": True,
        "result_source_matched": True,
        "result_source_count": 2,
        "live_exchange_called": True,
        "real_order_placed": True,
        "exchange_submit_execution_result_id": "exchange-result-1",
    }
    assert packet["post_submit_close_loop_proof"] == {
        "exchange_submit_execution_result_id": "exchange-result-1",
        "present_evidence_keys": [
            "runtime_post_submit_finalize_packet_id",
            "post_submit_reconciliation_evidence_id",
            "post_submit_budget_settlement_id",
            "submit_outcome_review_id",
        ],
        "matched_evidence_keys": [
            "runtime_post_submit_finalize_packet_id",
            "post_submit_reconciliation_evidence_id",
            "post_submit_budget_settlement_id",
            "submit_outcome_review_id",
        ],
        "missing_source_match_keys": [],
    }
    assert packet["reject_reasons"] == []
    assert packet["missing_evidence_keys"] == []
    assert packet["evidence"] == {
        "live_watcher_signal_packet_id": "live-signal-packet-1",
        "required_facts_readiness_packet_id": "facts-ready-1",
        "candidate_id": "candidate-1",
        "runtime_grant_id": "runtime-grant-1",
        "fresh_submit_authorization_id": "fresh-auth-1",
        "action_time_finalgate_packet_id": "finalgate-1",
        "operation_layer_submit_authorization_id": "op-auth-1",
        "exchange_submit_execution_result_id": "exchange-result-1",
        "exchange_native_hard_stop_order_id": "hard-stop-1",
        "runtime_post_submit_finalize_packet_id": "finalize-1",
        "post_submit_reconciliation_evidence_id": "reconcile-1",
        "post_submit_budget_settlement_id": "settlement-1",
        "submit_outcome_review_id": "review-1",
    }
    verification = verifier.build_live_closure_evidence_verification(packet)
    assert verification["status"] == "live_closure_complete"


def test_live_closure_evidence_packet_keeps_partial_official_packet_in_progress():
    packet = packet_builder.build_live_closure_evidence_packet(
        _official_complete_sources()[:2],
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert packet["reject_reasons"] == []
    assert packet["live_submit_proof"] == {
        "exchange_result_present": False,
        "result_source_matched": False,
        "result_source_count": 0,
        "live_exchange_called": False,
        "real_order_placed": False,
    }
    assert packet["present_evidence_keys"] == [
        "live_watcher_signal_packet_id",
        "required_facts_readiness_packet_id",
    ]
    verification = verifier.build_live_closure_evidence_verification(packet)
    assert verification["status"] == "live_closure_in_progress"
    assert verification["first_incomplete_stage"] == "candidate_authorization_bound"


def test_live_closure_evidence_packet_rejects_controlled_local_cycle_shape():
    sources = _official_complete_sources()
    sources[2]["scope"] = "runtime_controlled_tiny_live_bridge_to_local_cycle_proof"
    sources[2]["status"] = "controlled_tiny_live_bridge_to_local_cycle_passed"
    sources[2]["safety_invariants"] = {
        "live_exchange_called": False,
        "real_order_placed": False,
        "controlled_fake_gateway_called": True,
        "controlled_order_lifecycle_submit_called": True,
    }

    packet = packet_builder.build_live_closure_evidence_packet(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert "controlled_in_memory_execution" in packet["reject_reasons"]
    assert "live_exchange_not_called" in packet["reject_reasons"]
    assert "real_order_not_placed" in packet["reject_reasons"]
    assert packet["live_submit_proof"] == {
        "exchange_result_present": True,
        "result_source_matched": True,
        "result_source_count": 2,
        "live_exchange_called": False,
        "real_order_placed": False,
        "exchange_submit_execution_result_id": "exchange-result-1",
    }
    verification = verifier.build_live_closure_evidence_verification(packet)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_packet_rejects_exchange_result_without_live_markers():
    sources = _official_complete_sources()
    sources[2]["safety_invariants"] = {}

    packet = packet_builder.build_live_closure_evidence_packet(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert "live_exchange_not_called" in packet["reject_reasons"]
    assert "real_order_not_placed" in packet["reject_reasons"]
    assert packet["live_submit_proof"] == {
        "exchange_result_present": True,
        "result_source_matched": True,
        "result_source_count": 2,
        "live_exchange_called": False,
        "real_order_placed": False,
        "exchange_submit_execution_result_id": "exchange-result-1",
    }
    verification = verifier.build_live_closure_evidence_verification(packet)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_packet_rejects_cross_source_live_submit_markers():
    sources = _official_complete_sources()
    sources[2]["safety_invariants"] = {}
    sources.append(
        {
            "scope": "unrelated_submit_marker",
            "status": "submitted",
            "safety_invariants": {
                "live_exchange_called": True,
                "real_order_placed": True,
            },
        }
    )

    packet = packet_builder.build_live_closure_evidence_packet(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert packet["live_submit_proof"] == {
        "exchange_result_present": True,
        "result_source_matched": True,
        "result_source_count": 2,
        "live_exchange_called": False,
        "real_order_placed": False,
        "exchange_submit_execution_result_id": "exchange-result-1",
    }
    assert "live_exchange_not_called" in packet["reject_reasons"]
    assert "real_order_not_placed" in packet["reject_reasons"]
    verification = verifier.build_live_closure_evidence_verification(packet)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_packet_rejects_unbound_post_submit_close_loop():
    sources = _official_complete_sources()
    sources[3]["ids"].pop("exchange_submit_execution_result_id")

    packet = packet_builder.build_live_closure_evidence_packet(
        sources,
        source_kind="official_live_closure_evidence",
        official_live_source=True,
        generated_at_ms=1781755000000,
    )

    assert packet["post_submit_close_loop_proof"] == {
        "exchange_submit_execution_result_id": "exchange-result-1",
        "present_evidence_keys": [
            "runtime_post_submit_finalize_packet_id",
            "post_submit_reconciliation_evidence_id",
            "post_submit_budget_settlement_id",
            "submit_outcome_review_id",
        ],
        "matched_evidence_keys": [],
        "missing_source_match_keys": [
            "runtime_post_submit_finalize_packet_id",
            "post_submit_reconciliation_evidence_id",
            "post_submit_budget_settlement_id",
            "submit_outcome_review_id",
        ],
    }
    assert "post_submit_finalize_result_source_missing" in packet["reject_reasons"]
    assert "post_submit_close_loop_result_source_missing" in packet["reject_reasons"]
    verification = verifier.build_live_closure_evidence_verification(packet)
    assert verification["status"] == "blocked_live_closure_rejected"
    assert verification["completion"]["first_bounded_real_order_complete"] is False


def test_live_closure_evidence_packet_cli_writes_packet_and_verification(tmp_path, capsys):
    input_json = tmp_path / "source.json"
    output_json = tmp_path / "packet.json"
    verification_json = tmp_path / "verification.json"
    input_json.write_text(
        json.dumps({"sources": _official_complete_sources()}),
        encoding="utf-8",
    )

    assert packet_builder.main(
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
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    verification = json.loads(verification_json.read_text(encoding="utf-8"))
    assert packet["status"] == "live_closure_evidence_packet_built"
    assert verification["status"] == "live_closure_complete"
