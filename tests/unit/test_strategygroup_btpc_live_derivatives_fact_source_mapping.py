from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_btpc_live_derivatives_fact_source_mapping",
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
            "keep_l2_shadow_observation": True,
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
        },
        "action_rows": [
            {
                "action": "attach_live_derivatives_fact_sources_before_btpc_live_eligibility",
                "review_area": "live_fact_source",
                "live_required_fact_authority": False,
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
            },
            {
                "action": "review_btpc_strong_uptrend_conflict_disable_rule",
                "review_area": "classifier_rule",
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
            },
        ],
        "interaction": {
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "safety_invariants": {
            "server_files_mutated": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
    }


def _btpc_handoff() -> dict:
    return {
        "status": "l2_intake_contract_observe_only",
        "required_facts": {
            "derivatives": [
                "funding_72h",
                "perp_spot_premium",
                "open_interest_or_crowding_proxy",
                "short_squeeze_risk",
                "historical_open_interest_window",
                "historical_global_long_short_ratio_window",
                "top_trader_position_ratio_window",
            ],
            "risk": [
                "real_exchange_margin_liquidation_model",
                "spread_liquidity_downshift_state",
                "slippage_cost_state",
                "protection_plan_state",
                "exit_plan_state",
            ],
        },
        "execution_boundary": {
            "final_gate_input": False,
            "operation_layer_input": False,
            "real_submit_authorized": False,
        },
        "risk_defaults": {
            "risk_tier": "not_live_order_eligible",
            "max_notional_per_action_usdt": "0",
            "max_active_positions": 0,
        },
    }


def test_btpc_live_fact_source_mapping_records_live_sources_without_authority() -> None:
    module = _load_module()

    artifact = module.build_btpc_live_derivatives_fact_source_mapping(
        btpc_l2_review_artifact=_btpc_l2_decision(),
        btpc_handoff=_btpc_handoff(),
    )

    assert (
        artifact["status"]
        == "btpc_live_derivatives_fact_source_mapping_ready_without_live_authority"
    )
    assert artifact["counts"]["expected_live_fact_source_count"] == 8
    assert artifact["counts"]["mapping_ready_count"] == 8
    assert artifact["counts"]["source_attachment_pending_count"] == 8
    assert artifact["counts"]["live_required_fact_satisfied_count"] == 0
    assert artifact["counts"]["live_required_fact_gap_count"] == 8
    assert artifact["counts"]["derivatives_fact_source_count"] == 7
    assert artifact["counts"]["risk_fact_source_count"] == 1
    assert "real_order_authorized_count" not in artifact["counts"]
    assert "real_order_authority" not in artifact["btpc_state"]
    assert "decision" not in artifact
    review_outcome = artifact["review_outcome_state"]
    assert review_outcome["state_family"] == "Review Outcome State"
    assert (
        review_outcome["source_role"]
        == "btpc_live_derivatives_fact_source_mapping_provenance"
    )
    assert review_outcome["tradeability_decision_source"] is False
    assert review_outcome["live_derivatives_fact_source_mapping_ready"] is True
    assert review_outcome["mapping_satisfies_live_required_facts"] is False
    assert review_outcome["source_attachment_required_before_live_eligibility"] is True
    assert review_outcome["l2_promotion_recommended_now"] is False
    assert review_outcome["l4_scope_change_recommended"] is False
    assert review_outcome["real_order_scope_change_recommended"] is False

    rows = {row["required_fact"]: row for row in artifact["source_rows"]}
    assert rows["historical_open_interest_window"]["source_route"] == (
        "open_interest_history_window"
    )
    assert rows["historical_global_long_short_ratio_window"]["source_route"] == (
        "global_long_short_account_ratio_history_window"
    )
    assert rows["top_trader_position_ratio_window"]["source_route"] == (
        "top_trader_position_ratio_history_window"
    )
    assert rows["real_exchange_margin_liquidation_model"]["source_route"] == (
        "exchange_leverage_bracket_margin_and_symbol_filter_model"
    )
    assert all(row["live_required_fact_satisfied"] is False for row in rows.values())
    assert all(row["can_feed_finalgate"] is False for row in rows.values())
    assert all(row["can_feed_operation_layer"] is False for row in rows.values())
    assert all("real_order_authority" not in row for row in rows.values())
    assert all(row["exchange_write_authority"] is False for row in rows.values())
    assert artifact["interaction"]["remote_interaction_count"] == 0
    assert artifact["interaction"]["approaches_real_order"] is False
    assert artifact["interaction"]["calls_finalgate"] is False
    assert artifact["interaction"]["calls_operation_layer"] is False
    assert artifact["interaction"]["calls_exchange_write"] is False
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["mapping_is_not_live_required_fact"] is True
    assert artifact["safety_invariants"]["does_not_lower_owner_selected_leverage"] is True
    assert artifact["safety_invariants"]["does_not_change_live_profile_or_sizing_defaults"] is True
    assert "operator_command_plan" not in artifact
    assert "execution_intent_created" not in artifact["safety_invariants"]


def test_btpc_live_fact_source_mapping_blocks_forbidden_live_authority() -> None:
    module = _load_module()
    decision = _btpc_l2_decision()
    decision["review_outcome_state"]["real_order_scope_change_recommended"] = True

    artifact = module.build_btpc_live_derivatives_fact_source_mapping(
        btpc_l2_review_artifact=decision,
        btpc_handoff=_btpc_handoff(),
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    assert (
        "btpc_l2_decision.real_order_scope_change_recommended"
        in artifact["safety_invariants"]["source_forbidden_effects"]
    )
    assert artifact["review_outcome_state"]["default_next_step"] == (
        "stop_and_repair_btpc_live_fact_source_mapping_source_forbidden_effects"
    )
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_btpc_live_fact_source_mapping_rejects_source_authority_mirror_fields() -> None:
    module = _load_module()
    decision = _btpc_l2_decision()
    decision["safety_invariants"]["real_order_authority"] = False
    decision["review_outcome_state"]["actionable_now"] = False
    decision["action_rows"][0]["real_order_authority"] = False
    handoff = _btpc_handoff()
    handoff["execution_boundary"]["actionable_now"] = False

    artifact = module.build_btpc_live_derivatives_fact_source_mapping(
        btpc_l2_review_artifact=decision,
        btpc_handoff=handoff,
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    effects = artifact["safety_invariants"]["source_forbidden_effects"]
    assert (
        "btpc_l2_review.safety_invariants."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects
    assert (
        "btpc_l2_review.review_outcome_state."
        "legacy_authority_mirror_present:actionable_now"
    ) in effects
    assert (
        "btpc_l2_review.action_rows."
        "attach_live_derivatives_fact_sources_before_btpc_live_eligibility."
        "legacy_authority_mirror_present:real_order_authority"
    ) in effects
    assert (
        "btpc_handoff.execution_boundary."
        "legacy_authority_mirror_present:actionable_now"
    ) in effects
    assert artifact["interaction"]["places_order"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_btpc_live_fact_source_mapping_cli_writes_outputs(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_module()
    decision_path = tmp_path / "decision.json"
    handoff_path = tmp_path / "handoff.json"
    output_path = tmp_path / "mapping.json"
    owner_path = tmp_path / "mapping.md"
    decision_path.write_text(json.dumps(_btpc_l2_decision()), encoding="utf-8")
    handoff_path.write_text(json.dumps(_btpc_handoff()), encoding="utf-8")

    exit_code = module.main(
        [
            "--btpc-l2-review-json",
            str(decision_path),
            "--btpc-handoff-json",
            str(handoff_path),
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
    assert file_payload["scope"] == "btpc_live_derivatives_fact_source_mapping"
    assert (
        file_payload["status"]
        == "btpc_live_derivatives_fact_source_mapping_ready_without_live_authority"
    )
    owner_text = owner_path.read_text(encoding="utf-8")
    assert "BTPC Live Derivatives Fact Source Mapping" in owner_text
    assert "Live RequiredFacts satisfied by mapping: `false`" in owner_text
    assert "Real order authority" not in owner_text
