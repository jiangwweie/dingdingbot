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
    }


def _source_artifact(group: str, **counts) -> dict:
    base_counts = {
        "would_enter_count": 0,
        "would_enter_forward_positive_count": 0,
        "no_action_count": 0,
        "missed_no_action_forward_positive_count": 0,
        "positive_forward_outcome_count": 0,
    }
    base_counts.update(counts)
    artifact = {
        "strategy_group_id": group,
        "closure_result": f"{group}_closure",
        "source_counts": base_counts,
        "evidence_for": [f"{group} evidence for"],
        "evidence_against": [f"{group} evidence against"],
        "safety_invariants": _safe(),
    }
    if group == "BTPC-001":
        artifact["btpc_attribution"] = {
            "review_outcome_state": {
                "default_next_step": "execute_btpc_l2_fact_source_and_classifier_review_tasks_locally",
                "keep_l2_shadow_observation": True,
                "state_family": "Review Outcome State",
                "tradeability_decision_source": False,
            },
            "live_required_fact_gap_count": 8,
            "source_attachment_pending_count": 8,
        }
    if group == "MPG-001":
        artifact["member_review"] = {
            "status": "ready_for_owner_review",
            "member_count": 6,
            "member_rows": [{"member_id": "TSI-001"}],
        }
    return artifact


def _evidence_closure_wave(**overrides) -> dict:
    source_artifacts = [
        _source_artifact(
            "BRF-001",
            would_enter_count=1,
            no_action_count=168,
            missed_no_action_forward_positive_count=136,
            positive_forward_outcome_count=136,
        ),
        _source_artifact(
            "BTPC-001",
            no_action_count=169,
            missed_no_action_forward_positive_count=152,
            positive_forward_outcome_count=152,
        ),
        _source_artifact(
            "LSR-001",
            would_enter_count=2,
            would_enter_forward_positive_count=2,
            no_action_count=167,
            positive_forward_outcome_count=2,
        ),
        _source_artifact(
            "MI-001",
            would_enter_count=23,
            would_enter_forward_positive_count=22,
            no_action_count=315,
            positive_forward_outcome_count=22,
        ),
        _source_artifact(
            "CPM-RO-001",
            would_enter_count=18,
            would_enter_forward_positive_count=13,
            no_action_count=151,
            positive_forward_outcome_count=13,
        ),
        _source_artifact("MPG-001"),
    ]
    base = {
        "status": "review_only_evidence_closure_wave_ready",
        "evidence_closure_artifacts": source_artifacts,
        "interaction": {
            "level": "L0_local_review_only_evidence_closure_wave",
            "remote_interaction_count": 0,
        },
        "safety_invariants": _safe(),
    }
    base.update(overrides)
    return base


def _build_artifact() -> dict:
    module = _load_module()
    return module.build_review_only_deep_dive_wave(
        evidence_closure_wave=_evidence_closure_wave()
    )


def test_review_only_deep_dive_wave_reaches_owner_policy_point():
    artifact = _build_artifact()

    assert artifact["status"] == "review_only_deep_dive_ready_for_owner_policy"
    assert artifact["phase_status"]["phase_1_owner_perception_projection"] == "ready"
    assert artifact["phase_status"]["phase_2_six_line_deep_dive"] == "ready"
    assert artifact["phase_status"]["phase_3_owner_policy_package"] == (
        "ready_for_owner_policy_review"
    )
    assert len(artifact["deep_dive_artifacts"]) == 6
    assert "deep_dive_packets" not in artifact
    assert artifact["owner_progress_projection"]["deep_dive_artifact_count"] == 6
    assert artifact["owner_progress_projection"]["signal_observation_review_state"] == (
        "six_line_review_ready_for_owner_policy_review"
    )
    assert "owner_decision_package" not in artifact
    assert artifact["owner_policy_package"]["owner_policy_item_count"] == 6
    assert artifact["owner_policy_package"]["owner_policy_confirmation_required_now"]
    assert not artifact["owner_policy_package"]["runtime_owner_intervention_required"]

    by_group = {item["strategy_group_id"]: item for item in artifact["deep_dive_artifacts"]}
    assert by_group["MI-001"]["recommended_owner_policy"] == (
        "open_formal_candidate_review_without_registry_admission"
    )
    assert by_group["MI-001"]["strategy_review_checkpoint_if_approved"] == (
        "open_mi_identity_overlap_symbol_concentration_review"
    )
    assert by_group["CPM-RO-001"]["recommended_owner_policy"] == (
        "keep_observation_asset_run_merge_review_before_independent_admission"
    )
    assert by_group["CPM-RO-001"]["strategy_review_checkpoint_if_approved"] == (
        "open_cpm_ro_semantic_source_merge_quality_review"
    )
    assert by_group["MPG-001"]["member_review"]["member_count"] == 6
    assert "decision" not in by_group["BTPC-001"]["btpc_attribution"]
    assert "attribution_result" not in by_group["BTPC-001"]["btpc_attribution"]
    assert by_group["BTPC-001"]["btpc_attribution"]["review_outcome_state"][
        "default_next_step"
    ] == "execute_btpc_l2_fact_source_and_classifier_review_tasks_locally"
    assert by_group["BTPC-001"]["btpc_attribution"]["review_outcome_state"][
        "tradeability_decision_source"
    ] is False


def test_review_only_deep_dive_wave_keeps_live_authority_closed():
    artifact = _build_artifact()

    assert artifact["interaction"]["remote_interaction_count"] == 0
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert artifact["interaction"]["calls_exchange_write"] is False
    assert "real_order_authority" not in artifact
    assert "real_order_authority" not in artifact["safety_invariants"]
    assert all(
        "real_order_authority" not in row for row in artifact["deep_dive_artifacts"]
    )
    assert "execution_intent_created" not in artifact["safety_invariants"]
    assert artifact["safety_invariants"]["registry_authority_changed"] is False
    assert artifact["safety_invariants"]["tier_policy_changed"] is False
    assert artifact["completion_boundary"]["runtime_owner_intervention_required"] is False

    for policy_item in artifact["owner_policy_package"]["items"]:
        assert policy_item["does_not_authorize_live_execution"] is True


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


def test_review_only_deep_dive_wave_rejects_legacy_authority_mirror():
    module = _load_module()
    source = _evidence_closure_wave()
    source["safety_invariants"]["real_order_authority"] = True

    try:
        module.build_review_only_deep_dive_wave(evidence_closure_wave=source)
    except ValueError as exc:
        assert "legacy authority mirrors" in str(exc)
        assert "real_order_authority" in str(exc)
    else:
        raise AssertionError("expected legacy authority mirror to fail")


def test_review_only_deep_dive_wave_rejects_actionable_now_authority_mirror():
    module = _load_module()
    source = _evidence_closure_wave()
    source["safety_invariants"]["actionable_now"] = True

    try:
        module.build_review_only_deep_dive_wave(evidence_closure_wave=source)
    except ValueError as exc:
        assert "legacy authority mirrors" in str(exc)
        assert "actionable_now" in str(exc)
    else:
        raise AssertionError("expected legacy authority mirror to fail")


def test_review_only_deep_dive_wave_does_not_fallback_to_legacy_packet_rows():
    module = _load_module()
    source = _evidence_closure_wave()
    source.pop("evidence_closure_artifacts")
    source["evidence_closure_packets"] = [
        _source_artifact(group) for group in module.REVIEW_ORDER
    ]

    try:
        module.build_review_only_deep_dive_wave(evidence_closure_wave=source)
    except ValueError as exc:
        assert "missing evidence closure artifacts" in str(exc)
    else:
        raise AssertionError("expected legacy packet-only source rows to fail")


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
            "--output-owner-policy",
            str(output_owner),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    owner_text = output_owner.read_text(encoding="utf-8")
    assert stdout_payload["status"] == "review_only_deep_dive_ready_for_owner_policy"
    assert artifact["owner_policy_package"]["owner_policy_item_count"] == 6
    assert "real_order_authority" not in artifact["safety_invariants"]
    assert "StrategyGroup Review-Only Deep-Dive Wave" in markdown
    assert "Real order authority" not in markdown
    assert "StrategyGroup Deep-Dive Owner Policy Package" in owner_text


def test_review_only_deep_dive_wave_cli_omitted_input_does_not_read_default(
    tmp_path,
):
    module = _load_module()

    try:
        module.main(
            [
                "--output-json",
                str(tmp_path / "deep-dive.json"),
                "--output-md",
                str(tmp_path / "deep-dive.md"),
                "--output-owner-decision",
                str(tmp_path / "owner.md"),
            ]
        )
    except ValueError as exc:
        assert "evidence closure wave is not ready" in str(exc)
    else:
        raise AssertionError("expected omitted evidence closure wave to fail")
