from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


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
        "status": "btpc_l2_keep_revise_fact_source_decision_ready",
        "decision": {
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
        },
        "action_rows": [
            {
                "action": "review_btpc_strong_uptrend_conflict_disable_rule",
                "decision_area": "classifier_rule",
                "reason": "strong_uptrend_conflict_case_remains_revise_before_promotion",
                "real_order_authority": False,
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
            },
            {
                "action": "review_btpc_freshness_or_classifier_stale_signal_rule",
                "decision_area": "classifier_rule",
                "reason": "stale_signal_case_remains_revise_before_promotion",
                "real_order_authority": False,
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
        "decision": {
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
        },
        "case_rows": [
            {
                "fixture_case": "strong_uptrend_conflict",
                "proxy_replay_quality_decision": "revise_conflict_disable_before_l2_promotion",
                "real_order_authority": False,
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
            },
            {
                "fixture_case": "stale_signal",
                "proxy_replay_quality_decision": "revise_freshness_or_classifier_before_l2_promotion",
                "real_order_authority": False,
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
        "decision": {
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

    packet = module.build_btpc_classifier_rule_review(
        btpc_l2_decision_packet=_btpc_l2_decision(),
        btpc_proxy_replay_quality_packet=_proxy_replay_quality(),
        btpc_live_source_mapping_packet=_live_source_mapping(),
    )

    assert packet["status"] == "btpc_classifier_rule_review_recorded_without_live_authority"
    assert packet["counts"]["expected_rule_count"] == 2
    assert packet["counts"]["rule_review_count"] == 2
    assert packet["counts"]["implementation_ready_count"] == 2
    assert packet["counts"]["proxy_replay_case_link_count"] == 2
    assert packet["counts"]["live_required_fact_satisfied_count"] == 0
    assert packet["counts"]["real_order_authorized_count"] == 0
    assert packet["counts"]["l4_scope_change_recommended_count"] == 0
    assert packet["btpc_state"]["classifier_logic_version"] == (
        "btpc-001-price-action-v1"
    )
    assert packet["decision"]["classifier_rule_review_recorded"] is True
    assert packet["decision"]["strong_uptrend_rule_recorded"] is True
    assert packet["decision"]["freshness_rule_recorded"] is True
    assert packet["decision"]["classifier_review_satisfies_live_required_facts"] is False
    assert packet["decision"]["l2_promotion_recommended_now"] is False
    assert packet["decision"]["l4_scope_change_recommended"] is False
    assert packet["decision"]["real_order_scope_change_recommended"] is False

    rows = {row["rule_id"]: row for row in packet["rule_rows"]}
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
    assert all(row["real_order_authority"] is False for row in rows.values())
    assert all(row["operation_layer_authority"] is False for row in rows.values())
    assert all(row["exchange_write_authority"] is False for row in rows.values())
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["approaches_real_order"] is False
    assert packet["interaction"]["calls_finalgate"] is False
    assert packet["interaction"]["calls_operation_layer"] is False
    assert packet["interaction"]["calls_exchange_write"] is False
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["classifier_review_is_not_live_required_fact"] is True
    assert packet["safety_invariants"]["does_not_lower_owner_selected_leverage"] is True
    assert packet["safety_invariants"]["does_not_change_live_profile_or_sizing_defaults"] is True


def test_btpc_classifier_rule_review_blocks_forbidden_source_authority() -> None:
    module = _load_module()
    proxy = _proxy_replay_quality()
    proxy["decision"]["real_order_scope_change_recommended"] = True

    packet = module.build_btpc_classifier_rule_review(
        btpc_l2_decision_packet=_btpc_l2_decision(),
        btpc_proxy_replay_quality_packet=proxy,
        btpc_live_source_mapping_packet=_live_source_mapping(),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert (
        "packet_1.decision.real_order_scope_change_recommended"
        in packet["safety_invariants"]["source_forbidden_effects"]
    )
    assert packet["decision"]["default_next_step"] == (
        "stop_and_repair_btpc_classifier_rule_review_source_forbidden_effects"
    )
    assert packet["operator_command_plan"]["places_order"] is False


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
            "--btpc-l2-decision-json",
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
