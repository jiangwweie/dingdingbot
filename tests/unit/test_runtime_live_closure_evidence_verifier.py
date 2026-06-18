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


def _official_packet(
    evidence: dict[str, str],
    *,
    live_submit_proof: dict[str, bool] | None = None,
) -> dict[str, object]:
    packet = {
        "source_kind": "official_live_closure_evidence",
        "evidence": evidence,
    }
    if "exchange_submit_execution_result_id" in evidence:
        packet["live_submit_proof"] = live_submit_proof or {
            "exchange_result_present": True,
            "live_exchange_called": True,
            "real_order_placed": True,
        }
    return packet


def test_live_closure_evidence_verifier_marks_complete_when_all_contract_keys_present():
    packet = verifier.build_live_closure_evidence_verification(
        _official_packet(_complete_evidence()),
        generated_at_ms=1781755000000,
    )

    assert packet["status"] == "live_closure_complete"
    assert packet["owner_state"] == "完成"
    assert packet["official_live_source_ready"] is True
    assert packet["stage_count"] == 9
    assert packet["completed_stage_count"] == 9
    assert packet["first_incomplete_stage"] is None
    assert packet["missing_evidence_keys"] == []
    assert packet["completion"] == {
        "first_bounded_real_order_complete": True,
        "real_order_closure_proven": True,
        "mock_signal_treated_as_real_signal": False,
        "disabled_smoke_treated_as_real_execution_proof": False,
    }
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_live_closure_evidence_verifier_marks_in_progress_at_first_missing_stage():
    evidence = _complete_evidence()
    evidence.pop("exchange_native_hard_stop_order_id")
    evidence.pop("runtime_post_submit_finalize_packet_id")

    packet = verifier.build_live_closure_evidence_verification(
        _official_packet(evidence),
        generated_at_ms=1781755000000,
    )

    assert packet["status"] == "live_closure_in_progress"
    assert packet["owner_state"] == "处理中"
    assert packet["completed_stage_count"] == 6
    assert packet["first_incomplete_stage"] == "exchange_native_protection"
    assert packet["missing_evidence_keys"] == [
        "exchange_native_hard_stop_order_id",
        "runtime_post_submit_finalize_packet_id",
    ]
    exchange_native_stage = next(
        stage for stage in packet["stages"] if stage["name"] == "exchange_native_protection"
    )
    assert exchange_native_stage["status"] == "missing_evidence"
    assert exchange_native_stage["missing_evidence_keys"] == [
        "exchange_native_hard_stop_order_id"
    ]
    finalize_stage = next(
        stage for stage in packet["stages"] if stage["name"] == "post_submit_finalize"
    )
    assert finalize_stage["status"] == "blocked_by_previous_stage"


def test_live_closure_evidence_verifier_rejects_synthetic_or_disabled_live_proof():
    evidence = _complete_evidence()

    packet = verifier.build_live_closure_evidence_verification(
        {
            "source_kind": "official_live_closure_evidence",
            "evidence": evidence,
            "live_submit_proof": {
                "exchange_result_present": True,
                "live_exchange_called": True,
                "real_order_placed": True,
            },
            "reject_reasons": ["replay_signal", "disabled_smoke_only"],
        },
        generated_at_ms=1781755000000,
    )

    assert packet["status"] == "blocked_live_closure_rejected"
    assert packet["owner_state"] == "需要介入"
    assert packet["completion"] == {
        "first_bounded_real_order_complete": False,
        "real_order_closure_proven": False,
        "mock_signal_treated_as_real_signal": True,
        "disabled_smoke_treated_as_real_execution_proof": True,
    }
    rejected = [
        stage
        for stage in packet["stages"]
        if stage["status"] == "rejected"
    ]
    assert [stage["name"] for stage in rejected] == [
        "live_fresh_signal",
        "official_operation_layer_ready",
    ]


def test_live_closure_evidence_verifier_rejects_missing_live_submit_proof():
    packet = verifier.build_live_closure_evidence_verification(
        {
            "source_kind": "official_live_closure_evidence",
            "evidence": _complete_evidence(),
        },
        generated_at_ms=1781755000000,
    )

    assert packet["status"] == "blocked_live_closure_rejected"
    assert packet["owner_state"] == "需要介入"
    assert packet["completion"]["first_bounded_real_order_complete"] is False
    assert packet["reject_reasons"] == ["live_submit_proof_missing"]
    real_exchange_stage = next(
        stage for stage in packet["stages"] if stage["name"] == "real_exchange_acceptance"
    )
    assert real_exchange_stage["status"] == "rejected"
    assert real_exchange_stage["reject_reasons"] == ["live_submit_proof_missing"]


def test_live_closure_evidence_verifier_rejects_false_live_submit_proof():
    packet = verifier.build_live_closure_evidence_verification(
        _official_packet(
            _complete_evidence(),
            live_submit_proof={
                "exchange_result_present": True,
                "live_exchange_called": False,
                "real_order_placed": False,
            },
        ),
        generated_at_ms=1781755000000,
    )

    assert packet["status"] == "blocked_live_closure_rejected"
    assert packet["completion"]["real_order_closure_proven"] is False
    assert packet["reject_reasons"] == [
        "live_exchange_not_called",
        "real_order_not_placed",
    ]


def test_live_closure_evidence_verifier_rejects_duplicate_required_evidence_id():
    evidence = _complete_evidence()
    evidence["required_facts_readiness_packet_id"] = evidence[
        "live_watcher_signal_packet_id"
    ]

    packet = verifier.build_live_closure_evidence_verification(
        _official_packet(evidence),
        generated_at_ms=1781755000000,
    )

    assert packet["status"] == "blocked_live_closure_rejected"
    assert packet["owner_state"] == "需要介入"
    assert packet["completion"]["first_bounded_real_order_complete"] is False
    assert packet["completion"]["real_order_closure_proven"] is False
    assert packet["reject_reasons"] == ["duplicate_evidence_id"]


def test_live_closure_evidence_verifier_rejects_unmarked_complete_shape():
    packet = verifier.build_live_closure_evidence_verification(
        {"evidence": _complete_evidence()},
        generated_at_ms=1781755000000,
    )

    assert packet["status"] == "blocked_live_closure_rejected"
    assert packet["official_live_source_ready"] is False
    assert packet["reject_reasons"] == ["official_live_closure_source_missing"]
    assert packet["completion"]["first_bounded_real_order_complete"] is False
    assert packet["completion"]["real_order_closure_proven"] is False


def test_live_closure_evidence_verifier_cli_writes_packet(tmp_path, capsys):
    evidence_json = tmp_path / "live-evidence.json"
    output_json = tmp_path / "live-verification.json"
    evidence_json.write_text(
        json.dumps(_official_packet(_complete_evidence())),
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
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert packet["status"] == "live_closure_complete"
