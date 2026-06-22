from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_review_only_deep_dive_wave.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_review_only_deep_dive_wave",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _safe() -> dict:
    return {
        "registry_authority_changed": False,
        "tier_policy_changed": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "mpg_member_live_scope_expanded": False,
        "l4_real_order_scope_expanded": False,
        "shadow_candidate_created": False,
        "execution_intent_created": False,
        "final_gate_called": False,
        "operation_layer_called": False,
        "order_created": False,
        "exchange_write_called": False,
        "real_order_authority": False,
    }


def _source_packet(group: str, **counts) -> dict:
    base_counts = {
        "would_enter_count": 0,
        "would_enter_forward_positive_count": 0,
        "no_action_count": 0,
        "missed_no_action_forward_positive_count": 0,
        "positive_forward_outcome_count": 0,
    }
    base_counts.update(counts)
    packet = {
        "strategy_group_id": group,
        "closure_result": f"{group}_closure",
        "source_counts": base_counts,
        "evidence_for": [f"{group} evidence for"],
        "evidence_against": [f"{group} evidence against"],
        "safety_invariants": _safe(),
    }
    if group == "BTPC-001":
        packet["btpc_attribution"] = {
            "live_required_fact_gap_count": 8,
            "source_attachment_pending_count": 8,
        }
    if group == "MPG-001":
        packet["member_review"] = {
            "status": "ready_for_owner_review",
            "member_count": 6,
            "member_rows": [{"member_id": "TSI-001"}],
        }
    return packet


def _evidence_closure_wave(**overrides) -> dict:
    base = {
        "status": "review_only_evidence_closure_wave_ready",
        "evidence_closure_packets": [
            _source_packet(
                "BRF-001",
                would_enter_count=1,
                no_action_count=168,
                missed_no_action_forward_positive_count=136,
                positive_forward_outcome_count=136,
            ),
            _source_packet(
                "BTPC-001",
                no_action_count=169,
                missed_no_action_forward_positive_count=152,
                positive_forward_outcome_count=152,
            ),
            _source_packet(
                "LSR-001",
                would_enter_count=2,
                would_enter_forward_positive_count=2,
                no_action_count=167,
                positive_forward_outcome_count=2,
            ),
            _source_packet(
                "MI-001",
                would_enter_count=23,
                would_enter_forward_positive_count=22,
                no_action_count=315,
                positive_forward_outcome_count=22,
            ),
            _source_packet(
                "CPM-RO-001",
                would_enter_count=18,
                would_enter_forward_positive_count=13,
                no_action_count=151,
                positive_forward_outcome_count=13,
            ),
            _source_packet("MPG-001"),
        ],
        "interaction": {
            "level": "L0_local_review_only_evidence_closure_wave",
            "remote_interaction_count": 0,
        },
        "safety_invariants": _safe(),
    }
    base.update(overrides)
    return base


def _build_packet() -> dict:
    module = _load_module()
    return module.build_review_only_deep_dive_wave(
        evidence_closure_wave=_evidence_closure_wave()
    )


def test_review_only_deep_dive_wave_reaches_owner_decision_point():
    packet = _build_packet()

    assert packet["status"] == "review_only_deep_dive_ready_for_owner_decision"
    assert packet["phase_status"]["phase_1_owner_perception_projection"] == "ready"
    assert packet["phase_status"]["phase_2_six_line_deep_dive"] == "ready"
    assert packet["phase_status"]["phase_3_owner_policy_decision_package"] == (
        "ready_for_owner_policy_decision"
    )
    assert len(packet["deep_dive_packets"]) == 6
    assert packet["owner_decision_package"]["decision_count"] == 6
    assert packet["owner_decision_package"]["owner_policy_confirmation_required_now"]
    assert not packet["owner_decision_package"]["runtime_owner_intervention_required"]

    by_group = {item["strategy_group_id"]: item for item in packet["deep_dive_packets"]}
    assert by_group["MI-001"]["recommended_owner_decision"] == (
        "open_formal_candidate_review_without_registry_admission"
    )
    assert by_group["CPM-RO-001"]["recommended_owner_decision"] == (
        "keep_observation_asset_run_merge_review_before_independent_admission"
    )
    assert by_group["MPG-001"]["member_review"]["member_count"] == 6


def test_review_only_deep_dive_wave_keeps_live_authority_closed():
    packet = _build_packet()

    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["calls_finalgate"] is False
    assert packet["interaction"]["calls_operation_layer"] is False
    assert packet["interaction"]["calls_exchange_write"] is False
    assert packet["safety_invariants"]["real_order_authority"] is False
    assert packet["safety_invariants"]["registry_authority_changed"] is False
    assert packet["safety_invariants"]["tier_policy_changed"] is False
    assert packet["completion_boundary"]["runtime_owner_intervention_required"] is False

    for card in packet["owner_decision_package"]["cards"]:
        assert card["does_not_authorize_live_execution"] is True


def test_review_only_deep_dive_wave_rejects_forbidden_source_effects():
    module = _load_module()
    source = _evidence_closure_wave()
    source["safety_invariants"]["tier_policy_changed"] = True

    try:
        module.build_review_only_deep_dive_wave(evidence_closure_wave=source)
    except ValueError as exc:
        assert "forbidden effects" in str(exc)
    else:
        raise AssertionError("expected forbidden source effect to fail")


def test_review_only_deep_dive_wave_cli_writes_outputs(tmp_path, capsys):
    module = _load_module()
    source = tmp_path / "closure.json"
    output_json = tmp_path / "deep-dive.json"
    output_md = tmp_path / "deep-dive.md"
    output_owner = tmp_path / "owner.md"
    source.write_text(json.dumps(_evidence_closure_wave()), encoding="utf-8")

    exit_code = module.main(
        [
            "--evidence-closure-wave-json",
            str(source),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--output-owner-decision",
            str(output_owner),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    owner_text = output_owner.read_text(encoding="utf-8")
    assert stdout_payload["status"] == "review_only_deep_dive_ready_for_owner_decision"
    assert packet["owner_decision_package"]["decision_count"] == 6
    assert "StrategyGroup Review-Only Deep-Dive Wave" in markdown
    assert "StrategyGroup Deep-Dive Owner Decision Package" in owner_text
