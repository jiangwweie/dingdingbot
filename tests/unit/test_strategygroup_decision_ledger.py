from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_decision_ledger.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_decision_ledger",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _opportunity_decision_loop(*, forbidden: bool = False) -> dict:
    return {
        "status": "decision_loop_ready",
        "strategy_quality_decisions": {
            "rows": [
                {
                    "strategy_group_id": "BTPC-001",
                    "current_tier": "L2",
                    "strategy_quality_decision": (
                        "keep_l2_shadow_and_revise_fact_classifier_inputs"
                    ),
                    "reason": (
                        "btpc_proxy_replay_quality_ready_with_review_only_revisions"
                    ),
                    "next_stage": (
                        "feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_decision"
                    ),
                    "evidence": {
                        "replay_sample_count": 5,
                        "would_enter_sample_count": 2,
                        "revise_sample_count": 3,
                        "fact_source_pending_item_count": 1,
                    },
                    "revision_completion": {
                        "status": "no_revision_required",
                        "completion_blockers": [],
                    },
                    "revision_execution": {
                        "status": "no_revision_execution_required",
                        "execution_blockers": [],
                    },
                    "not_l4_scope_change": True,
                    "real_order_authority": False,
                    "candidate_or_finalgate_authority": False,
                },
                {
                    "strategy_group_id": "VCB-001",
                    "current_tier": "L1",
                    "strategy_quality_decision": "revise_before_l2",
                    "reason": "coverage_ready_but_revise_or_negative_evidence_present",
                    "next_stage": (
                        "record_revise_decision_and_keep_l1_until_review_passes"
                    ),
                    "evidence": {
                        "replay_sample_count": 5,
                        "would_enter_sample_count": 2,
                        "revise_sample_count": 1,
                    },
                    "revision_completion": {
                        "status": "local_revision_completion_ready",
                        "completion_blockers": [],
                    },
                    "revision_execution": {
                        "status": "local_revision_execution_complete",
                        "execution_blockers": [],
                    },
                    "not_l4_scope_change": True,
                    "real_order_authority": False,
                    "candidate_or_finalgate_authority": False,
                },
                {
                    "strategy_group_id": "RBR-001",
                    "current_tier": "L1",
                    "strategy_quality_decision": "park_until_new_edge",
                    "reason": "parked_negative_or_low_quality_evidence",
                    "next_stage": "park_until_new_evidence",
                    "evidence": {
                        "replay_sample_count": 1,
                        "would_enter_sample_count": 0,
                        "revise_sample_count": 0,
                    },
                    "not_l4_scope_change": True,
                    "real_order_authority": False,
                    "candidate_or_finalgate_authority": False,
                },
            ]
        },
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
            "order_created": forbidden,
        },
    }


def _signal_coverage() -> dict:
    return {
        "status": "mainline_no_signal_broader_would_enter",
        "broader_observation": {
            "high_priority_no_action_signals": [
                {
                    "strategy_group_id": "BTPC-001",
                    "signal_type": "no_action",
                    "coverage_review_priority": "P0_5",
                    "human_summary": (
                        "BTPC v1 rejects stale shadow signals before any L2 promotion review."
                    ),
                    "reason_codes": ["btpc_disable_stale_signal_before_l2_review"],
                    "policy_l2_readiness": "l2_shadow_candidate_observation_enabled",
                    "policy_recommended_action": (
                        "continue_l2_shadow_candidate_observation_without_l4_scope_change"
                    ),
                },
                {
                    "strategy_group_id": "LSR-001",
                    "signal_type": "no_action",
                    "coverage_review_priority": "P1",
                    "human_summary": (
                        "LSR v1 disables the old long sweep preview until the short-revival rewrite passes review."
                    ),
                    "reason_codes": [
                        "lsr_disable_long_preview_conflicts_with_short_revival_lead"
                    ],
                    "policy_l2_readiness": "blocked_rewrite_required",
                    "policy_recommended_action": (
                        "keep_l1_observe_only_until_side_specific_rewrite_handoff_exists"
                    ),
                },
            ]
        },
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


def _tier_policy() -> dict:
    return {
        "current_strategy_groups": {
            "BTPC-001": {"tier": "L2"},
            "VCB-001": {"tier": "L1"},
            "RBR-001": {"tier": "L1"},
        },
        "new_strategy_group_defaults": {"known_new_groups": {"LSR": "L1"}},
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_decision_ledger_outputs_one_minimal_row_per_strategygroup():
    module = _load_module()

    packet = module.build_strategygroup_decision_ledger(
        opportunity_decision_loop_packet=_opportunity_decision_loop(),
        signal_coverage_packet=_signal_coverage(),
        tier_policy=_tier_policy(),
    )

    assert packet["status"] == "decision_ledger_ready"
    assert packet["counts"]["current_row_count"] == 4
    assert packet["decision"]["one_current_row_per_strategy_group"] is True
    assert packet["decision"]["raw_replay_samples_duplicated"] is False
    assert packet["decision"]["no_action_attribution_is_field_input_only"] is True
    rows = {row["strategy_group_id"]: row for row in packet["ledger_rows"]}
    assert list(rows["BTPC-001"].keys()) == packet["required_row_fields"]
    assert rows["BTPC-001"]["decision"] == "revise"
    assert rows["BTPC-001"]["opportunity_type"] == "would_enter"
    assert "no_action:" in rows["BTPC-001"]["reason"]
    assert rows["VCB-001"]["decision"] == "revise"
    assert rows["RBR-001"]["decision"] == "park"
    assert rows["LSR-001"]["decision"] == "revise"
    assert rows["LSR-001"]["opportunity_type"] == "no_action"
    assert packet["tier_review"]["counts"] == {
        "park": 1,
        "revise_before_tier_change": 3,
    }
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["places_order"] is False
    assert packet["safety_invariants"]["order_created"] is False


def test_decision_ledger_blocks_forbidden_source_effect():
    module = _load_module()

    packet = module.build_strategygroup_decision_ledger(
        opportunity_decision_loop_packet=_opportunity_decision_loop(forbidden=True),
        signal_coverage_packet=_signal_coverage(),
        tier_policy=_tier_policy(),
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert "packet_0.safety_invariants.order_created" in packet["safety_invariants"][
        "source_forbidden_effects"
    ]
    assert packet["interaction"]["places_order"] is False


def test_decision_ledger_cli_writes_outputs(tmp_path, capsys):
    module = _load_module()
    opportunity_path = tmp_path / "opportunity.json"
    signal_path = tmp_path / "signal.json"
    policy_path = tmp_path / "policy.json"
    out_path = tmp_path / "ledger.json"
    md_path = tmp_path / "ledger.md"
    _write_json(opportunity_path, _opportunity_decision_loop())
    _write_json(signal_path, _signal_coverage())
    _write_json(policy_path, _tier_policy())

    exit_code = module.main(
        [
            "--opportunity-decision-loop-json",
            str(opportunity_path),
            "--signal-coverage-json",
            str(signal_path),
            "--tier-policy-json",
            str(policy_path),
            "--output-json",
            str(out_path),
            "--output-owner-progress",
            str(md_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["status"] == "decision_ledger_ready"
    assert "StrategyGroup Decision Ledger" in md_path.read_text(encoding="utf-8")
