from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_strategygroup_btpc_classifier_rule_review.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_btpc_classifier_rule_review",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _btpc_l2_decision() -> dict:
    return {
        "status": "btpc_l2_keep_revise_fact_source_review_ready",
        "review_outcome_state": {
            "state_family": "Review Outcome State",
            "source_role": "btpc_l2_keep_revise_fact_source_provenance",
            "tradeability_decision_source": False,
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
        },
        "action_rows": [
            {
                "action": "review_btpc_strong_uptrend_conflict_disable_rule",
                "review_area": "classifier_rule",
                "reason": "strong_uptrend_conflict_case_remains_revise_before_promotion",
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
            },
            {
                "action": "review_btpc_freshness_or_classifier_stale_signal_rule",
                "review_area": "classifier_rule",
                "reason": "stale_signal_case_remains_revise_before_promotion",
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
            },
        ],
        "interaction": {
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
        },
        "safety_invariants": {
            "server_files_mutated": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
    }


def _proxy_replay_quality() -> dict:
    return {
        "status": "btpc_proxy_replay_quality_review_ready",
        "review_outcome_state": {
            "state_family": "Review Outcome State",
            "source_role": "btpc_proxy_replay_quality_review_provenance",
            "tradeability_decision_source": False,
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
        },
        "case_rows": [
            {
                "fixture_case": "strong_uptrend_conflict",
                "proxy_replay_quality_review_outcome": "revise_conflict_disable_before_l2_promotion",
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
            },
            {
                "fixture_case": "stale_signal",
                "proxy_replay_quality_review_outcome": "revise_freshness_or_classifier_before_l2_promotion",
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
            },
        ],
        "interaction": {
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
        },
        "safety_invariants": {
            "server_files_mutated": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
    }


def _live_source_mapping() -> dict:
    return {
        "status": "btpc_live_derivatives_fact_source_mapping_ready_without_live_authority",
        "review_outcome_state": {
            "state_family": "Review Outcome State",
            "source_role": "btpc_live_derivatives_fact_source_mapping_provenance",
            "tradeability_decision_source": False,
            "mapping_satisfies_live_required_facts": False,
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
        },
        "interaction": {
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
        },
        "safety_invariants": {
            "mapping_is_not_live_required_fact": True,
            "server_files_mutated": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
    }


def test_btpc_classifier_rule_review_records_v1_rules_without_authority() -> None:
    module = _load_module()

    artifact = module.build_btpc_classifier_rule_review(
        btpc_l2_review_artifact=_btpc_l2_decision(),
        btpc_proxy_replay_quality_artifact=_proxy_replay_quality(),
        btpc_live_source_mapping_artifact=_live_source_mapping(),
    )

    assert artifact["status"] == "btpc_classifier_rule_review_recorded_without_live_authority"
    assert artifact["counts"]["expected_rule_count"] == 2
    assert artifact["counts"]["rule_review_count"] == 2
    assert artifact["counts"]["implementation_ready_count"] == 2
    assert artifact["counts"]["proxy_replay_case_link_count"] == 2
    assert artifact["counts"]["live_required_fact_satisfied_count"] == 0
    assert "real_order_authorized_count" not in artifact["counts"]
    assert artifact["counts"]["l4_scope_change_recommended_count"] == 0
    assert "real_order_authority" not in artifact["btpc_state"]
    assert artifact["btpc_state"]["classifier_logic_version"] == (
        "btpc-001-price-action-v1"
    )
    review_outcome = artifact["review_outcome_state"]
    assert review_outcome["state_family"] == "Review Outcome State"
    assert review_outcome["source_role"] == "btpc_classifier_rule_review_provenance"
    assert review_outcome["tradeability_decision_source"] is False
    assert review_outcome["classifier_rule_review_recorded"] is True
    assert review_outcome["strong_uptrend_rule_recorded"] is True
    assert review_outcome["freshness_rule_recorded"] is True
    assert (
        review_outcome["classifier_review_satisfies_live_required_facts"]
        is False
    )
    assert review_outcome["l2_promotion_recommended_now"] is False
    assert review_outcome["l4_scope_change_recommended"] is False
    assert "decision" not in artifact
    assert (
        review_outcome["real_order_scope_change_recommended"]
        is False
    )

    rows = {row["rule_id"]: row for row in artifact["rule_rows"]}
    assert rows["btpc_strong_uptrend_conflict_disable_rule"][
        "expected_reason_code"
    ] == "btpc_disable_strong_uptrend_conflict"
    assert rows["btpc_strong_uptrend_conflict_disable_rule"][
        "required_disable_state"
    ] == "strong_uptrend_disable_state"
    assert rows["btpc_freshness_or_classifier_stale_signal_rule"][
        "expected_reason_code"
    ] == "btpc_disable_stale_signal_before_l2_review"
    assert rows["btpc_freshness_or_classifier_stale_signal_rule"][
        "required_disable_state"
    ] == "stale_signal"
    assert all(row["implementation_ready"] is True for row in rows.values())
    assert all("real_order_authority" not in row for row in rows.values())
    assert all(row["operation_layer_authority"] is False for row in rows.values())
    assert all(row["exchange_write_authority"] is False for row in rows.values())
    assert artifact["interaction"]["remote_interaction_count"] == 0
    assert artifact["interaction"]["approaches_real_order"] is False
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert artifact["interaction"]["calls_exchange_write"] is False
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["classifier_review_is_not_live_required_fact"] is True
    assert artifact["safety_invariants"]["does_not_lower_owner_selected_leverage"] is True
    assert artifact["safety_invariants"]["does_not_change_live_profile_or_sizing_defaults"] is True
    assert "operator_command_plan" not in artifact
    assert "execution_intent_created" not in artifact["safety_invariants"]


def test_btpc_classifier_rule_review_blocks_forbidden_source_authority() -> None:
    module = _load_module()
    proxy = _proxy_replay_quality()
    proxy["review_outcome_state"]["real_order_scope_change_recommended"] = True

    artifact = module.build_btpc_classifier_rule_review(
        btpc_l2_review_artifact=_btpc_l2_decision(),
        btpc_proxy_replay_quality_artifact=proxy,
        btpc_live_source_mapping_artifact=_live_source_mapping(),
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    assert (
        "artifact_1.review_outcome_state.real_order_scope_change_recommended"
        in artifact["safety_invariants"]["source_forbidden_effects"]
    )
    assert artifact["review_outcome_state"]["default_next_step"] == (
        "stop_and_repair_btpc_classifier_rule_review_source_forbidden_effects"
    )
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_btpc_classifier_rule_review_rejects_source_authority_mirror_fields() -> None:
    module = _load_module()
    l2_review = _btpc_l2_decision()
    l2_review["safety_invariants"]["real_order_authority"] = False
    l2_review["action_rows"][0]["actionable_now"] = False
    proxy = _proxy_replay_quality()
    proxy["review_outcome_state"]["real_order_authority"] = False
    proxy["case_rows"][0]["actionable_now"] = False

    artifact = module.build_btpc_classifier_rule_review(
        btpc_l2_review_artifact=l2_review,
        btpc_proxy_replay_quality_artifact=proxy,
        btpc_live_source_mapping_artifact=_live_source_mapping(),
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    effects = artifact["safety_invariants"]["source_forbidden_effects"]
    assert (
        "artifact_0.safety_invariants."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects
    assert (
        "artifact_0.action_rows.review_btpc_strong_uptrend_conflict_disable_rule."
        "legacy_authority_mirror_present:actionable_now"
    ) in effects
    assert (
        "artifact_1.review_outcome_state."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects
    assert (
        "artifact_1.case_rows.strong_uptrend_conflict."
        "legacy_authority_mirror_present:actionable_now"
    ) in effects
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_btpc_classifier_rule_review_rejects_legacy_packet_kwargs() -> None:
    module = _load_module()

    with pytest.raises(TypeError):
        module.build_btpc_classifier_rule_review(
            btpc_l2_review_artifact=_btpc_l2_decision(),
            btpc_proxy_replay_quality_packet=_proxy_replay_quality(),
            btpc_live_source_mapping_packet=_live_source_mapping(),
        )


def test_btpc_classifier_rule_review_cli_writes_outputs(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_module()
    decision_path = tmp_path / "decision.json"
    proxy_path = tmp_path / "proxy.json"
    mapping_path = tmp_path / "mapping.json"
    output_path = tmp_path / "rule-review.json"
    owner_path = tmp_path / "rule-review.md"
    decision_path.write_text(json.dumps(_btpc_l2_decision()), encoding="utf-8")
    proxy_path.write_text(json.dumps(_proxy_replay_quality()), encoding="utf-8")
    mapping_path.write_text(json.dumps(_live_source_mapping()), encoding="utf-8")

    exit_code = module.main(
        [
            "--btpc-l2-review-json",
            str(decision_path),
            "--btpc-proxy-replay-quality-json",
            str(proxy_path),
            "--btpc-live-source-mapping-json",
            str(mapping_path),
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(owner_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "btpc_classifier_rule_review"
    assert (
        file_payload["status"]
        == "btpc_classifier_rule_review_recorded_without_live_authority"
    )
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "BTPC Classifier Rule Review" in owner_text
    assert "Live RequiredFacts satisfied by classifier review: `false`" in owner_text
    assert "Real order authority" not in owner_text
    assert "| Rule | Case | Implemented | Live fact | Exchange write |" in owner_text
    assert "| Rule | Case | Implemented | Live fact | Real order |" not in owner_text


def test_btpc_classifier_rule_review_cli_omitted_inputs_do_not_read_defaults(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_module()
    output_path = tmp_path / "rule-review.json"
    owner_path = tmp_path / "rule-review.md"

    exit_code = module.main(
        [
            "--output-json",
            str(output_path),
            "--output-owner-progress",
            str(owner_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["status"] == (
        "btpc_classifier_rule_review_waiting_for_action_rows"
    )
    assert file_payload["source_status"] == {
        "btpc_l2_keep_revise_fact_source_review": None,
        "btpc_proxy_replay_quality_review": None,
        "btpc_live_derivatives_fact_source_mapping": None,
    }
    assert file_payload["counts"]["rule_review_count"] == 0
