from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_strategygroup_runtime_local_monitor_sequence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_strategygroup_runtime_local_monitor_sequence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_monitor_default_owner_policy_package_path_uses_policy_identity():
    module = _load_module()

    default_path = module.DEFAULT_STRATEGYGROUP_OWNER_POLICY_PACKAGE_JSON
    assert default_path.name == "latest-strategygroup-owner-policy-package.json"
    assert "owner-decision-package" not in default_path.name
    assert not hasattr(module, "DEFAULT_STRATEGYGROUP_OWNER_DECISION_PACKAGE_JSON")


def _write_output(command: list[str], payload: dict) -> None:
    output_path = Path(command[command.index("--output-json") + 1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload), encoding="utf-8")


def _monitor_issues(report: dict) -> dict:
    assert "checks" not in report
    return report["owner_runtime_issues"]


def _legacy_monitor_checks(report: dict) -> dict:
    assert "checks" not in report
    return report.get("checks", {})


def test_local_monitor_sequence_run_step_reads_output_json_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    output_json = tmp_path / "step-output.json"
    read_paths: list[Path] = []

    def fake_reader(path: Path) -> dict:
        read_paths.append(path)
        return {"status": "waiting_for_market"}

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        output_json.write_text(
            json.dumps({"status": "waiting_for_market"}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(module, "_read_json_if_exists", fake_reader)

    step = module._run_step(
        "daily_check",
        ["python", "script.py", "--output-json", str(output_json)],
        output_json,
        fake_runner,
    )

    assert read_paths == [output_json]
    assert step["artifact"] == {"status": "waiting_for_market"}
    assert step["artifact"] == {"status": "waiting_for_market"}
    assert "packet" not in step
    assert step["stdout"] == "ok"


def test_capital_trial_summary_is_trial_envelope_compatibility_projection() -> None:
    module = _load_module()

    summary = module._sequence_capital_trial_summary(
        {
            "status": "trial_envelope_projection_ready",
            "projection_schema": (
                "brc.strategygroup_capital_trial_envelope_projection.v1"
            ),
            "projection_status": "trial_envelope_projection_ready",
            "projection_metadata": {
                "artifact_role": "trial_envelope_projection",
                "strategygroup_lifecycle_owner": False,
                "tradeability_decision_source": False,
                "runtime_truth_source": False,
            },
            "capital_trial_summary": {
                "selected_non_mpg_strategy_group_id": "BRF2-001",
                "selected_short_strategy_group_id": "BRF2-001",
                "selected_candidate_status": (
                    "short_experiment_evidence_pending_owner_policy"
                ),
                "short_experiment_candidate_count": 1,
                "trial_envelope_generated": True,
            },
            "selected_non_mpg_trial_candidate": {
                "strategy_asset_current_decision": "promote",
                "policy_outcome": "promote",
                "reason": "promote_to_tiny_live_intake_candidate_not_live_ready",
                "promotion_scope": "intake_only",
                "promotion_target": "paper_observation_or_experiment_evidence",
                "tiny_live_ready": False,
                "next_checkpoint": "BRF2-001_tiny_live_intake_evidence",
                "side_scope": ["short"],
            },
        }
    )

    assert summary["projection_role"] == "trial_envelope_compatibility_projection"
    assert summary["projection_schema"] == (
        "brc.strategygroup_capital_trial_envelope_projection.v1"
    )
    assert summary["projection_status"] == "trial_envelope_projection_ready"
    assert summary["state_source"] == "capital_trial_envelope_projection"
    assert summary["primary_judgment_source"] is False
    assert summary["strategygroup_lifecycle_owner"] is False
    assert summary["tradeability_decision_source"] is False
    assert summary["runtime_truth_source"] is False
    assert "legacy_bridge_provenance" not in summary
    assert summary["short_experiment_candidate_count"] == 1
    assert "short_candidate_trade_count" not in summary
    assert summary["selected_short_strategy_group_id"] == "BRF2-001"
    assert summary["promotion_scope"] == "intake_only"
    assert "tiny_live_ready" not in summary
    assert "actionable_now" not in summary
    assert "real_order_authority" not in summary


def _write_passed_post_revision_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "passed",
            "interaction": {
                "level": "L0_local_post_revision_replay_review",
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
        },
    )


def _write_waiting_brf2_shadow_candidate_evidence(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "brf2_shadow_candidate_evidence_waiting_for_fresh_signal",
            "strategy_group_id": "BRF2-001",
            "shadow_candidate_evidence_ready": False,
            "shadow_candidate_evidence": {
                "shadow_candidate_evidence_type": (
                    "brf2_non_executing_short_signal_candidate_evidence"
                ),
                "signal_state": "fact_input_missing",
            },
            "first_blocker": {
                "class": "brf2_watcher_fact_input_missing",
                "owner": "engineering",
                "repair_checkpoint": "attach_brf2_watcher_fact_input_producer",
            },
            "next_runtime_step": "attach_brf2_watcher_fact_input_producer",
            "checks": {
                "required_facts_satisfied": False,
                "disable_facts_clear": False,
            },
            "interaction": {
                "level": "L0_local_brf2_shadow_candidate_evidence",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
            },
        },
    )


def _write_ready_cpm_artifact(command: list[str], script: str) -> bool:
    base_interaction = {
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }
    if script == "build_cpm_identity_routing_decision.py":
        _write_output(
            command,
            {
                "status": "cpm_identity_routing_decision_ready",
                "strategy_group_id": "CPM-RO-001",
                "path_id": "CPM-LONG",
                "identity_decision": "standalone_trial_asset",
                "cpm_long_vs_mpg_long_distinct": True,
                "interaction": {
                    **base_interaction,
                    "level": "L0_local_cpm_identity_routing",
                },
            },
        )
        return True
    if script == "build_cpm_owner_trial_policy_scope.py":
        _write_output(
            command,
            {
                "status": "cpm_owner_trial_policy_scope_recorded",
                "owner_policy_recorded": True,
                "cpm_policy_scope_recorded": True,
                "owner_policy_scope_missing": False,
                "cpm_stage_after_policy": "admitted_trial_asset",
                "cpm_new_first_blocker": "cpm_required_facts_mapping_gap",
                "policy": {
                    "strategy_group_id": "CPM-RO-001",
                    "capital_scope": {
                        "type": "isolated_subaccount_full_allocation",
                        "amount_source": "action_time_exchange_available_balance",
                    },
                    "side_scope": ["long"],
                    "symbol_scope": "cpm_research_supported_symbols_with_replay_v2_expansion",
                    "watcher_symbol_scope": [
                        "ETHUSDT",
                        "SOLUSDT",
                        "AVAXUSDT",
                        "SUIUSDT",
                    ],
                    "primary_live_submit_symbol_scope": ["ETHUSDT"],
                    "leverage_scenario": "5x_scenario_not_authority",
                    "attempt_cap": 3,
                },
                "interaction": {**base_interaction, "level": "L0_local_cpm_owner_policy"},
            },
        )
        return True
    if script == "build_cpm_required_facts_mapping.py":
        _write_output(
            command,
            {
                "status": "cpm_required_facts_mapping_ready",
                "strategy_group_id": "CPM-RO-001",
                "path_id": "CPM-LONG",
                "required_facts_mapping_ready": True,
                "live_required_facts_authority": False,
                "action_time_refresh_required": True,
                "fresh_signal_rule": {
                    "signal_id": "cpm_long_pullback_reclaim_signal_v1"
                },
                "required_fact_observation_specs": [{"fact_key": "htf_trend_intact"}],
                "disable_fact_observation_specs": [{"fact_key": "htf_trend_broken"}],
                "after_next_state": "armed_observation",
                "first_blocker_after_mapping": "fresh_cpm_long_signal_absent",
                "watcher_scope": {
                    "symbols": ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"],
                    "primary_live_submit_symbols": ["ETHUSDT"],
                    "expanded_readonly_symbols": ["SOLUSDT", "AVAXUSDT", "SUIUSDT"],
                },
                "checks": {
                    "required_fact_count": 8,
                    "disable_fact_count": 6,
                    "expanded_watcher_scope_symbols_mapped": True,
                    "expanded_scope_does_not_change_live_profile": True,
                },
                "interaction": {
                    **base_interaction,
                    "level": "L0_local_cpm_required_facts_mapping",
                },
            },
        )
        return True
    if script == "build_cpm_runtime_signal_facts.py":
        _write_output(
            command,
            {
                "status": "cpm_runtime_signal_facts_ready",
                "strategy_group_id": "CPM-RO-001",
                "path_id": "CPM-LONG",
                "fact_input_present": True,
                "watcher_tick_present": True,
                "fact_authority": "readonly_proxy_not_action_time_required_fact",
                "fact_authority_boundary": {
                    "live_required_facts_authority": False,
                    "action_time_refresh_required": True,
                },
                "first_blocker": {"class": "none", "owner": "runtime"},
                "interaction": {
                    **base_interaction,
                    "level": "L0_local_cpm_runtime_signal_facts",
                },
            },
        )
        return True
    if script == "build_cpm_runtime_signal_capture.py":
        _write_output(
            command,
            {
                "status": "cpm_runtime_signal_capture_ready",
                "strategy_group_id": "CPM-RO-001",
                "path_id": "CPM-LONG",
                "fact_input_status": "cpm_runtime_signal_facts_ready",
                "fact_input_present": True,
                "watcher_tick_present": True,
                "watcher_scope": {
                    "signal_id": "cpm_long_pullback_reclaim_signal_v1",
                    "symbol_scope": ["ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"],
                    "primary_live_submit_symbol_scope": ["ETHUSDT"],
                    "expanded_readonly_symbol_scope": ["SOLUSDT", "AVAXUSDT", "SUIUSDT"],
                },
                "signal_detector_preview": {
                    "fact_input_present": True,
                    "watcher_tick_present": True,
                    "current_signal_state": "fresh_signal_absent",
                    "fresh_signal_present": False,
                    "first_blocker_class": "fresh_cpm_long_signal_absent",
                    "first_blocker_owner": "market",
                    "signal_capture_checkpoint": (
                        "continue_cpm_long_armed_observation_until_reclaim_signal"
                    ),
                    "missing_required_fact_keys": ["reclaim_confirmed"],
                    "active_disable_fact_keys": [],
                    "action_time_pending_fact_keys": [
                        "active_position_or_open_order_clear",
                        "action_time_available_balance",
                    ],
                },
                "shadow_candidate_shape": {"shadow_candidate_ready": False},
                "interaction": {
                    **base_interaction,
                    "level": "L0_local_cpm_runtime_signal_capture",
                },
            },
        )
        return True
    if script == "build_cpm_shadow_candidate_evidence.py":
        _write_output(
            command,
            {
                "status": "cpm_shadow_candidate_evidence_waiting_for_fresh_signal",
                "strategy_group_id": "CPM-RO-001",
                "shadow_candidate_evidence_ready": False,
                "shadow_candidate_evidence": {
                    "shadow_candidate_evidence_id": "",
                    "signal_state": "fresh_signal_absent",
                },
                "first_blocker": {
                    "class": "fresh_cpm_long_signal_absent",
                    "owner": "market",
                    "repair_checkpoint": (
                        "continue_cpm_long_armed_observation_until_reclaim_signal"
                    ),
                },
                "next_runtime_step": (
                    "continue_cpm_long_armed_observation_until_reclaim_signal"
                ),
                "interaction": {
                    **base_interaction,
                    "level": "L0_local_cpm_shadow_candidate_evidence",
                },
            },
        )
        return True
    if script == "build_cpm_dry_run_submit_rehearsal.py":
        _write_output(
            command,
            {
                "status": "cpm_dry_run_submit_rehearsal_shape_ready",
                "strategy_group_id": "CPM-RO-001",
                "path_id": "CPM-LONG",
                "dry_run_submit_rehearsal": "shape_ready",
                "checks": {
                    "armed_observation_ready": True,
                    "submit_rehearsal_shape_ready": True,
                    "fresh_signal_submit_rehearsal_passed": False,
                    "candidate_authorization_evidence_ready": False,
                    "finalgate_dry_run_passed": False,
                    "operation_layer_paper_passed": False,
                    "execution_attempt_rehearsal_ready": False,
                    "synthetic_fresh_signal_fixture_ready": True,
                    "synthetic_fresh_signal_present": True,
                    "synthetic_dangerous_authority_fields_fail_closed": True,
                    "synthetic_shadow_candidate_evidence_ready": True,
                    "synthetic_candidate_authorization_evidence_shape_ready": True,
                    "synthetic_action_time_required_facts_declared": True,
                    "synthetic_finalgate_dry_run_passed": True,
                    "synthetic_operation_layer_paper_passed": True,
                    "synthetic_execution_attempt_rehearsal_ready": True,
                    "exchange_write": False,
                    "order_created": False,
                },
                "synthetic_fresh_signal_rehearsal": {
                    "fixture_ready": True,
                    "fresh_signal_present": True,
                    "shadow_candidate_evidence_ready": True,
                    "candidate_authorization_evidence_shape_ready": True,
                    "action_time_required_facts_declared": True,
                    "finalgate_dry_run_passed": True,
                    "operation_layer_paper_passed": True,
                    "execution_attempt_rehearsal_ready": True,
                    "fresh_signal_submit_rehearsal_passed": True,
                    "dangerous_authority_fields_fail_closed": True,
                    "not_live_market_signal": True,
                    "not_execution_authority": True,
                },
                "interaction": {
                    **base_interaction,
                    "level": "L0_local_cpm_dry_run_submit_rehearsal",
                },
            },
        )
        return True
    if script == "fetch_binance_usdm_public_facts.py":
        _write_output(
            command,
            {
                "status": "binance_usdm_public_facts_ready",
                "generated_at_utc": "2026-06-30T00:00:00+00:00",
                "summary": {
                    "symbol_count": 5,
                    "ready_symbol_count": 5,
                    "public_fact_max_age_seconds": 300,
                },
                "checks": {
                    "public_facts_ready": True,
                    "exchange_write": False,
                    "order_created": False,
                },
                "interaction": {
                    **base_interaction,
                    "level": "L0_local_binance_usdm_public_facts",
                },
            },
        )
        return True
    if script == "build_four_candidate_runtime_activation_evidence.py":
        output_dir = Path(command[command.index("--output-dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, strategy_group_id, symbols in [
            (
                "latest-mpg-runtime-activation-evidence.json",
                "MPG-001",
                ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"],
            ),
            (
                "latest-sor-runtime-activation-evidence.json",
                "SOR-001",
                ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT"],
            ),
        ]:
            (output_dir / name).write_text(
                json.dumps(
                    {
                        "schema": "brc.four_candidate_runtime_activation_evidence.v1",
                        "status": "runtime_activation_evidence_ready",
                        "strategy_group_id": strategy_group_id,
                        "runtime_artifact_ready": True,
                        "watcher_scope_contract_ready": True,
                        "required_facts_contract_ready": True,
                        "candidate_evidence_shape_ready": True,
                        "fresh_signal_rehearsal_ready": True,
                        "watcher_scope": {"symbol_scope": symbols},
                        "interaction": {
                            **base_interaction,
                            "level": "L0_local_runtime_activation_evidence",
                        },
                    }
                ),
                encoding="utf-8",
            )
        (output_dir / "latest-four-candidate-scope-review-decision.json").write_text(
            json.dumps(
                {
                    "status": "four_candidate_scope_review_decision_ready",
                    "interaction": {
                        **base_interaction,
                        "level": "L0_local_four_candidate_scope_review_decision",
                    },
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "latest-cpm-fresh-signal-live-path-readiness.json").write_text(
            json.dumps(
                {
                    "status": "cpm_fresh_signal_live_path_readiness_ready",
                    "public_fact_path_ready": True,
                    "fresh_signal_present": False,
                    "live_submit_allowed": False,
                    "interaction": {
                        **base_interaction,
                        "level": "L0_local_cpm_fresh_signal_live_path_readiness",
                    },
                }
            ),
            encoding="utf-8",
        )
        return True
    if script == "build_sor_session_scope_detector.py":
        output_dir = Path(command[command.index("--output-dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "latest-sor-session-detector-facts.json").write_text(
            json.dumps(
                {
                    "status": "sor_session_detector_facts_ready",
                    "fresh_session_signal_count": 0,
                    "first_blocker": "computed_not_satisfied",
                    "interaction": {
                        **base_interaction,
                        "level": "L0_local_sor_session_detector",
                    },
                }
            ),
            encoding="utf-8",
        )
        return True
    if script == "build_mpg_high_beta_scope_readiness.py":
        output_dir = Path(command[command.index("--output-dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "latest-mpg-action-time-facts-readiness.json").write_text(
            json.dumps(
                {
                    "status": "mpg_action_time_facts_readiness_ready",
                    "interaction": {
                        **base_interaction,
                        "level": "L0_local_mpg_high_beta_scope_readiness",
                    },
                }
            ),
            encoding="utf-8",
        )
        return True
    if script == "build_strategy_fresh_signal_action_time_boundary.py":
        _write_output(
            command,
            {
                "schema": "brc.strategy_fresh_signal_action_time_boundary.v1",
                "scope": "fresh_signal_action_time_boundary_non_authority",
                "status": "strategy_fresh_signal_action_time_boundary_ready",
                "generated_at_utc": "2026-07-01T00:00:00+00:00",
                "summary": {
                    "strategy_count": 3,
                    "fresh_signal_present_count": 0,
                    "would_enter_finalgate_if_private_facts_ready_count": 0,
                    "live_submit_allowed_count": 0,
                },
                "strategy_rows": [
                    {
                        "strategy_group_id": "CPM-RO-001",
                        "symbol": "ETHUSDT",
                        "first_blocker": "fresh_cpm_long_signal_absent",
                        "blocker_class": "fresh_cpm_long_signal_absent",
                        "next_action": (
                            "continue_cpm_long_armed_observation_until_reclaim_signal"
                        ),
                    },
                    {
                        "strategy_group_id": "MPG-001",
                        "symbol": "SOLUSDT",
                        "first_blocker": "fresh_mpg_long_signal_absent",
                        "blocker_class": "fresh_mpg_long_signal_absent",
                        "next_action": (
                            "continue_mpg_armed_observation_until_fresh_signal"
                        ),
                    },
                    {
                        "strategy_group_id": "SOR-001",
                        "symbol": "SOLUSDT",
                        "first_blocker": "fresh_sor_session_range_signal_absent",
                        "blocker_class": "fresh_sor_session_range_signal_absent",
                        "next_action": (
                            "continue_sor_session_observation_until_range_signal"
                        ),
                    },
                ],
                "checks": {
                    "calls_finalgate": False,
                    "calls_operation_layer": False,
                    "calls_exchange_write": False,
                    "order_created": False,
                },
                "interaction": {
                    **base_interaction,
                    "level": "L0_local_strategy_fresh_signal_action_time_boundary",
                },
            },
        )
        return True
    if script == "build_replay_live_parity_audit.py":
        _write_output(
            command,
            {
                "schema": "brc.replay_live_parity_audit.v1",
                "scope": "replay_live_parity_audit_non_authority",
                "status": "replay_live_parity_audit_ready",
                "generated_at_utc": "2026-07-01T00:00:00+00:00",
                "summary": {
                    "strategy_count": 3,
                    "replay_signal_count": 131,
                    "live_detector_reproduced_count": 14,
                    "mismatch_count": 117,
                    "mismatch_reason_policy": (
                        "replay_signal_without_live_reproduction_is_signal_capture_defect_not_market_wait"
                    ),
                },
                "per_symbol_mismatch_table": [
                    {
                        "strategy_group_id": "CPM-RO-001",
                        "symbol": "ETHUSDT",
                        "detector_attached": True,
                        "watcher_tick_present": True,
                        "computed": True,
                        "failed_facts": [
                            "htf_trend_intact",
                            "reclaim_confirmed",
                        ],
                        "blocker_class": "computed_not_satisfied",
                        "next_action": (
                            "continue_observation_with_failed_fact_matrix"
                        ),
                        "mismatch_count": 4,
                    },
                    {
                        "strategy_group_id": "MPG-001",
                        "symbol": "SOLUSDT",
                        "detector_attached": True,
                        "watcher_tick_present": True,
                        "computed": False,
                        "failed_facts": ["action_time_boundary"],
                        "blocker_class": "action_time_boundary_not_reproduced",
                        "next_action": "repair_non_executing_action_time_rehearsal",
                        "mismatch_count": 25,
                    },
                    {
                        "strategy_group_id": "SOR-001",
                        "symbol": "SOLUSDT",
                        "detector_attached": True,
                        "watcher_tick_present": True,
                        "computed": False,
                        "failed_facts": ["session_range_boundary"],
                        "blocker_class": "action_time_boundary_not_reproduced",
                        "next_action": "repair_non_executing_action_time_rehearsal",
                        "mismatch_count": 25,
                    }
                ],
                "checks": {
                    "replay_treated_as_live_signal": False,
                    "live_submit_allowed": False,
                    "finalgate_called": False,
                    "operation_layer_called": False,
                    "exchange_write_called": False,
                    "order_created": False,
                },
                "interaction": {
                    **base_interaction,
                    "level": "L0_local_replay_live_parity_audit",
                },
            },
        )
        return True
    if script == "build_mi_trial_admission_decision.py":
        _write_output(
            command,
            {
                "schema": "brc.mi_trial_admission_decision.v1",
                "scope": "mi_trial_admission_decision_non_authority",
                "status": "mi_trial_admission_decision_ready",
                "generated_at_utc": "2026-07-01T00:00:00+00:00",
                "strategy_group_id": "MI-001",
                "trial_admission_decision": "trial_asset_admission_candidate",
                "promotion_scope": "trial_admission",
                "tradeability": {
                    "can_trade_now": False,
                    "first_blocker": "trial_admission_fact_not_integrated",
                    "blocker_owner": "engineering",
                },
                "checks": {
                    "live_submit_allowed": False,
                    "finalgate_called": False,
                    "operation_layer_called": False,
                    "exchange_write_called": False,
                    "order_created": False,
                },
                "interaction": {
                    **base_interaction,
                    "level": "L0_local_mi_trial_admission_decision",
                },
            },
        )
        return True
    if script == "build_four_candidate_runtime_activation_closure.py":
        _write_output(
            command,
            {
                "status": "four_candidate_runtime_activation_contract_ready",
                "source_replay": {
                    "venue_basis": "coinbase_spot_proxy",
                    "execution_venue_match": False,
                },
                "summary": {
                    "p0_contract_declared": True,
                    "p1_contract_declared": True,
                    "p0_runtime_artifacts_ready": True,
                    "p1_runtime_artifacts_ready": False,
                    "p0_tasks_closed": True,
                    "p1_tasks_closed": False,
                    "contract_declared_count": 4,
                    "runtime_artifact_ready_count": 3,
                    "scope_review_closed_count": 4,
                    "watcher_scope_contract_ready_count": 3,
                    "required_facts_contract_ready_count": 3,
                    "candidate_evidence_shape_ready_count": 3,
                    "fresh_signal_rehearsal_ready_count": 3,
                    "action_time_boundary_ready_count": 3,
                    "live_submit_allowed_count": 0,
                    "formal_replay_review_opened_count": 1,
                    "next_checkpoint": "attach_binance_usdm_readonly_watcher_facts_for_expanded_symbols",
                },
                "interaction": {
                    **base_interaction,
                    "level": "L0_local_four_candidate_runtime_activation_contract",
                },
            },
        )
        return True
    return False


def _write_ready_opportunity_review_work_loop(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "review_work_loop_ready",
            "review_outcome_state": {
                "state_family": "Review Outcome State",
                "source_role": "signal_observation_work_queue_provenance",
                "tradeability_decision_source": False,
                "default_next_step": "continue_btpc_l2_shadow_fact_quality_review",
            },
            "interaction": {
                "level": "L0_local_opportunity_review_work_loop",
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
        },
    )


def _write_ready_btpc_fact_quality_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_l2_shadow_fact_quality_review_ready",
            "review_outcome_state": {
                "state_family": "Review Outcome State",
                "source_role": "btpc_l2_shadow_fact_quality_review_provenance",
                "tradeability_decision_source": False,
                "default_next_step": "attach_btpc_derivatives_fact_sources_and_margin_model_for_l2_quality_review",
                "l2_shadow_observation_can_continue": True,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_l2_shadow_fact_quality_review",
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
        },
    )


def _write_ready_btpc_local_fact_proxy_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_local_fact_proxy_review_ready",
            "review_outcome_state": {
                "l2_shadow_quality_review_can_continue": True,
                "local_proxy_satisfies_live_required_facts": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_fact_proxy_review",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "proxy_is_not_live_required_fact": True,
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_btpc_proxy_replay_quality_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_proxy_replay_quality_review_ready",
            "review_outcome_state": {
                "proxy_replay_quality_review_ready": True,
                "proxy_replay_satisfies_live_required_facts": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_proxy_replay_quality_review",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "proxy_replay_is_not_live_required_fact": True,
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_btpc_l2_keep_revise_fact_source_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_l2_keep_revise_fact_source_review_ready",
            "review_outcome_state": {
                "state_family": "Review Outcome State",
                "source_role": "btpc_l2_keep_revise_fact_source_provenance",
                "tradeability_decision_source": False,
                "keep_l2_shadow_observation": True,
                "revise_fact_classifier_inputs_before_promotion": True,
                "l2_promotion_recommended_now": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_l2_keep_revise_fact_source_review",
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
        },
    )


def _write_ready_btpc_live_derivatives_fact_source_mapping(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_live_derivatives_fact_source_mapping_ready_without_live_authority",
            "review_outcome_state": {
                "state_family": "Review Outcome State",
                "source_role": "btpc_live_derivatives_fact_source_mapping_provenance",
                "tradeability_decision_source": False,
                "live_derivatives_fact_source_mapping_ready": True,
                "mapping_satisfies_live_required_facts": False,
                "l2_promotion_recommended_now": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_live_derivatives_fact_source_mapping",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "mapping_is_not_live_required_fact": True,
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_btpc_classifier_rule_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_classifier_rule_review_recorded_without_live_authority",
            "review_outcome_state": {
                "classifier_rule_review_recorded": True,
                "classifier_review_satisfies_live_required_facts": False,
                "l2_promotion_recommended_now": False,
                "l4_scope_change_recommended": False,
                "real_order_scope_change_recommended": False,
            },
            "interaction": {
                "level": "L0_local_btpc_classifier_rule_review",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "classifier_review_is_not_live_required_fact": True,
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_strategy_asset_state(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.strategygroup_strategy_asset_state.v1",
            "scope": "strategygroup_strategy_asset_state",
            "status": "strategy_asset_state_ready",
            "decision": {
                "single_main_product": True,
                "one_current_row_per_strategy_group": True,
                "raw_replay_samples_duplicated": False,
                "role_review_is_decision_support_only": True,
                "no_action_attribution_queue_recorded": True,
                "real_order_scope_change_recommended": False,
                "l4_promotion_recommended": False,
            },
            "observation_layer": {
                "p0_state": "waiting_for_executable_fresh_signal",
                "signal_observation_state": "observation_active",
                "mainline_ready_signal_count": 0,
                "broader_would_enter_count": 1,
                "broader_actionable_would_enter_count": 0,
                "high_priority_no_action_count": 4,
                "latest_observe_only_would_enter": {
                    "strategy_group_id": "RBR-001",
                    "symbol": "ADA/USDT:USDT",
                    "side": "short",
                    "confidence": "0.57",
                    "not_live_signal": True,
                },
                "actionable_now": False,
                "real_order_authority": False,
            },
            "role_review_rows": [
                {
                    "source_observation_strategy_group_id": "RBR-001",
                    "source_observation_symbol": "ADA/USDT:USDT",
                    "source_observation_side": "short",
                    "linked_intake_strategy_group_id": "RBR2-001",
                    "next_checkpoint": (
                        "RBR_RBR2_role_review_range_detector_classifier_merge_note"
                    ),
                }
            ],
            "no_action_attribution_queue": [
                {
                    "strategy_group_id": "BRF-001",
                    "attribution_class": "market_structure_or_path_risk",
                },
                {
                    "strategy_group_id": "BTPC-001",
                    "attribution_class": "fact_source_or_freshness",
                },
                {
                    "strategy_group_id": "LSR-001",
                    "attribution_class": "side_specific_rewrite",
                },
                {
                    "strategy_group_id": "VCB-001",
                    "attribution_class": "classifier_or_threshold",
                },
            ],
            "interaction": {
                "level": "L0_local_strategy_asset_state",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "local_strategy_asset_state_only": True,
                "server_files_mutated": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_strategygroup_quality_wave(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "quality_wave_ready",
            "rows": [
                {
                    "strategy_group_id": "BTPC-001",
                    "current_tier": "L2",
                    "current_decision": "revise",
                },
                {
                    "strategy_group_id": "VCB-001",
                    "current_tier": "L1",
                    "current_decision": "keep_observing",
                },
                {
                    "strategy_group_id": "LSR-001",
                    "current_tier": "L1",
                    "current_decision": "keep_observing",
                },
                {
                    "strategy_group_id": "BRF-001",
                    "current_tier": "L1",
                    "current_decision": "keep_observing",
                },
                {
                    "strategy_group_id": "RBR-001",
                    "current_tier": "L1",
                    "current_decision": "park",
                },
            ],
            "interaction": {
                "level": "L0_local_quality_wave",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _write_ready_handoff_boundary_closure(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "handoff_boundary_closure_ready",
            "interaction": {
                "level": "L0_local_handoff_boundary_closure",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _write_ready_btpc_fact_classifier_guard(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "btpc_fact_classifier_guard_ready",
            "interaction": {
                "level": "L0_local_btpc_fact_classifier_guard",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_lifecycle_rehearsal(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "lifecycle_rehearsal_ready",
            "interaction": {
                "level": "L0_local_lifecycle_rehearsal",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_pre_live_rehearsal_readiness(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "pre_live_rehearsal_ready",
            "decision": {
                "pre_live_rehearsal_ready": True,
                "live_submit_ready": False,
                "live_outcome_calibrated": False,
                "actionable_now": False,
                "real_order_authority": False,
            },
            "interaction": {
                "level": "L0_local_pre_live_rehearsal_readiness",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_runtime_safety_state(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "live_submit_standby_waiting_for_market",
            "runtime_safety_state": {
                "state_family": "Runtime Safety State",
                "primary_judgment_source": True,
                "pre_live_rehearsal_ready": True,
                "live_submit_ready": False,
                "live_submit_ready_false_reason": "no_fresh_signal",
                "actionable_now": False,
                "real_order_authority": False,
            },
            "owner_state": {
                "owner_status": "waiting_for_opportunity",
                "owner_label": "等待机会",
                "owner_intervention_required": False,
                "owner_manual_internal_evidence_review_required": False,
            },
            "interaction": {
                "level": "L0_runtime_safety_state",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
        },
    )


def _write_ready_tradeability_decision(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.strategygroup_tradeability_decision.v1",
            "scope": "strategygroup_tradeability_decision_read_model",
            "status": "tradeability_decision_ready",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "summary": {
                "row_count": 3,
                "tradable_now_count": 0,
                "actionable_now_count": 0,
                "real_order_authority_count": 0,
                "owner_first_blocker_count": 0,
                "engineering_first_blocker_count": 1,
                "market_first_blocker_count": 2,
                "runtime_first_blocker_count": 0,
                "strategy_review_first_blocker_count": 1,
                "top_strategy_group_id": "BRF2-001",
                "top_decision": "not_tradable_facts",
                "top_first_blocker_class": "brf2_watcher_fact_input_missing",
                "top_next_action": "attach_brf2_watcher_fact_input_producer",
            },
            "decision_rows": [
                {
                    "strategy_group_id": "BRF2-001",
                    "stage": "armed_observation",
                    "decision": "not_tradable_facts",
                    "first_blocker_class": "brf2_watcher_fact_input_missing",
                    "blocker_owner": "engineering",
                    "next_action": "attach_brf2_watcher_fact_input_producer",
                    "after_next_state": "armed_observation",
                    "actionable_now": False,
                    "real_order_authority": False,
                },
                {
                    "strategy_group_id": "MPG-001",
                    "stage": "armed_observation",
                    "decision": "not_tradable_market_wait",
                    "first_blocker_class": "fresh_executable_signal_absent",
                    "blocker_owner": "market",
                    "next_action": "continue_armed_observation_until_fresh_signal",
                    "after_next_state": "live_submit_ready",
                    "actionable_now": False,
                    "real_order_authority": False,
                },
                {
                    "strategy_group_id": "SOR-001",
                    "stage": "armed_observation",
                    "decision": "not_tradable_market_wait",
                    "first_blocker_class": "fresh_session_range_signal_absent",
                    "blocker_owner": "market",
                    "next_action": "continue_session_range_armed_observation_until_fresh_signal",
                    "after_next_state": "live_submit_ready",
                    "actionable_now": False,
                    "real_order_authority": False,
                },
            ],
            "owner_summary": {
                "state": "交易资格已判定",
                "top_strategy_group_id": "BRF2-001",
                "top_decision": "not_tradable_facts",
                "top_first_blocker": "brf2_watcher_fact_input_missing",
                "owner_policy_blocker_present": False,
                "owner_intervention_required": False,
                "real_order_authority": False,
                "actionable_now": False,
            },
            "checks": {
                "row_count": 3,
                "one_current_decision_per_strategy_group": True,
                "owner_policy_blocker_present": False,
                "owner_intervention_required": False,
                "row_count_matches_decision_rows": True,
                "tradable_now_rows_have_authority": True,
                "authority_rows_are_tradable_now": True,
                "tradable_now_scoped_to_live_submit": True,
                "market_wait_only_after_admission": True,
                "actionable_now_count": 0,
                "real_order_authority_count": 0,
            },
            "interaction": {
                "level": "L0_local_tradeability_decision",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _write_ready_three_strategy_live_trial_portfolio(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.three_strategy_live_trial_portfolio.v1",
            "scope": "three_strategy_live_trial_portfolio_read_model",
            "status": "three_strategy_live_trial_portfolio_ready",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "portfolio_goal": "at_least_3_live_trial_strategygroups",
            "selected_strategy_groups": ["MPG-001", "BRF2-001", "SOR-001"],
            "seat_count": 3,
            "objective_met": True,
            "seat_readiness": {
                "MPG-001": {
                    "stage": "armed_observation",
                    "runtime_readiness": {
                        "armed_observation_ready": True,
                        "controlled_live_standby_ready": True,
                        "stage_5_waiting_live_opportunity_ready": True,
                        "action_time_preflight_pending_fresh_signal": True,
                        "tiny_live_ready": False,
                        "live_submit_ready": False,
                    },
                    "first_blocker": {
                        "decision": "not_tradable_market_wait",
                        "first_blocker_class": "fresh_executable_signal_absent",
                        "blocker_owner": "market",
                        "next_action": "continue_armed_observation_until_fresh_signal",
                    },
                },
                "BRF2-001": {
                    "stage": "armed_observation",
                    "required_facts_mapping_ready": True,
                    "runtime_readiness": {
                        "armed_observation_ready": True,
                        "blocked_by": "fresh_brf2_short_signal_absent",
                        "controlled_live_standby_ready": True,
                        "stage_5_waiting_live_opportunity_ready": True,
                        "action_time_preflight_pending_fresh_signal": True,
                        "tiny_live_ready": False,
                        "live_submit_ready": False,
                    },
                    "first_blocker": {
                        "decision": "not_tradable_market_wait",
                        "first_blocker_class": "fresh_brf2_short_signal_absent",
                        "blocker_owner": "market",
                        "next_action": (
                            "continue_brf2_armed_observation_until_fresh_signal"
                        ),
                    },
                },
                "SOR-001": {
                    "stage": "armed_observation",
                    "runtime_readiness": {
                        "armed_observation_ready": True,
                        "controlled_live_standby_ready": True,
                        "stage_5_waiting_live_opportunity_ready": True,
                        "action_time_preflight_pending_fresh_signal": True,
                        "tiny_live_ready": False,
                        "live_submit_ready": False,
                    },
                    "first_blocker": {
                        "decision": "not_tradable_market_wait",
                        "first_blocker_class": "fresh_session_range_signal_absent",
                        "blocker_owner": "market",
                        "next_action": "continue_session_range_armed_observation_until_fresh_signal",
                    },
                },
            },
            "next_engineering_bottleneck": {
                "MPG-001": "fresh_signal_wait",
                "BRF2-001": "fresh_signal_wait",
                "SOR-001": "fresh_signal_wait",
            },
            "stage_5_live_opportunity_standby": {
                "status": "waiting_for_trial_grade_live_opportunity",
                "ready": True,
                "standby_count": 3,
                "waiting_for": "fresh_trial_grade_signal",
                "strategy_group_ids": ["MPG-001", "BRF2-001", "SOR-001"],
                "action_time_preflight_pending_fresh_signal": True,
                "hard_safety_gates_relaxed": False,
            },
            "checks": {
                "seat_count": 3,
                "at_least_three_seats": True,
                "objective_met": True,
                "controlled_live_standby_count": 3,
                "stage_5_waiting_live_opportunity_ready_count": 3,
                "hard_safety_gates_relaxed": False,
            },
            "interaction": {
                "level": "L0_local_three_strategy_live_trial_portfolio",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _write_ready_trial_grade_signal_gate_audit(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.strategygroup_trial_grade_signal_gate_audit.v1",
            "scope": "strategygroup_trial_grade_signal_gate_audit_non_executing",
            "status": "trial_grade_signal_gate_audit_ready",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "summary": {
                "strategy_group_count": 3,
                "trial_grade_observation_count_30d": 1,
                "action_time_trial_submit_count_30d": 0,
                "hard_safety_gates_relaxed": False,
            },
            "strategy_group_rows": {
                strategy_group_id: {
                    "strategy_group_id": strategy_group_id,
                    "tomorrow_same_structure_assessment": {
                        "would_enter_controlled_live_trial": True,
                    },
                }
                for strategy_group_id in ("MPG-001", "BRF2-001", "SOR-001")
            },
            "checks": {
                "signal_grade_catalog_present": True,
                "all_selected_strategy_groups_covered": True,
                "hard_safety_gates_not_relaxed": True,
                "risk_expressed_as_envelope": True,
                "recent_counts_are_source_qualified": True,
                "replay_or_proxy_not_action_time_authority": True,
            },
            "interaction": {
                "level": "L0_local_trial_grade_signal_gate_audit",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
            },
            "safety_invariants": {
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _write_ready_brf2_required_facts_mapping(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.brf2_required_facts_mapping.v1",
            "scope": "brf2_required_facts_mapping_for_armed_observation",
            "status": "brf2_required_facts_mapping_ready",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "strategy_group_id": "BRF2-001",
            "current_stage": "admitted_trial_asset",
            "after_next_state": "armed_observation",
            "required_facts_mapping_ready": True,
            "fresh_signal_rule": {
                "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
                "side": "short",
            },
            "required_fact_observation_specs": [
                {"fact_key": "closed_1h_ohlcv", "accepted_statuses": ["ready"]},
                {"fact_key": "closed_5m_ohlcv", "accepted_statuses": ["ready"]},
                {"fact_key": "rally_context", "accepted_statuses": ["ready"]},
                {
                    "fact_key": "rally_failure_trigger_state",
                    "accepted_statuses": ["confirmed", "ready"],
                },
                {
                    "fact_key": "short_squeeze_risk_state",
                    "accepted_statuses": ["bounded", "clear"],
                },
                {
                    "fact_key": "strong_reclaim_disable_state",
                    "accepted_statuses": ["clear", "false"],
                },
                {
                    "fact_key": "liquidity_downshift_state",
                    "accepted_statuses": ["clear", "false"],
                },
                {
                    "fact_key": "spread_liquidity_state",
                    "accepted_statuses": ["acceptable", "ready"],
                },
            ],
            "disable_fact_observation_specs": [
                {
                    "fact_key": "short_squeeze_risk_state",
                    "active_statuses": ["bounded", "red", "unbounded", "unknown"],
                    "blocker": "squeeze_risk_not_clear",
                },
                {
                    "fact_key": "strong_reclaim_disable_state",
                    "active_statuses": ["active", "true"],
                    "blocker": "strong_reclaim_disable_active",
                },
                {
                    "fact_key": "rally_extension_invalidates_failure_state",
                    "active_statuses": ["active", "true"],
                    "blocker": "rally_extension_invalidates_failure",
                },
                {
                    "fact_key": "liquidity_downshift_state",
                    "active_statuses": ["active", "true"],
                    "blocker": "liquidity_downshift_active",
                },
                {
                    "fact_key": "spread_liquidity_state",
                    "active_statuses": [
                        "missing",
                        "thin_volume",
                        "unknown",
                        "wide_spread",
                    ],
                    "blocker": "spread_liquidity_not_acceptable",
                },
            ],
            "first_blocker_after_mapping": "fresh_brf2_short_signal_absent",
            "mapping_checkpoint": (
                "continue_brf2_armed_observation_until_fresh_signal"
            ),
            "checks": {
                "required_facts_mapping_ready": True,
                "required_fact_count": 8,
                "disable_fact_count": 5,
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "interaction": {
                "level": "L0_local_brf2_required_facts_mapping",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _write_missing_brf2_runtime_signal_facts(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.brf2_runtime_signal_facts.v1",
            "scope": "brf2_runtime_signal_facts_read_model",
            "status": "brf2_runtime_signal_facts_missing_watcher_input",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "strategy_group_id": "BRF2-001",
            "fact_input_present": False,
            "watcher_tick_present": False,
            "source_status": "missing",
            "source_path": "output/runtime-monitor/latest-live-market-strategy-preview.json",
            "facts": {},
            "first_blocker": {
                "class": "brf2_watcher_fact_input_missing",
                "owner": "engineering",
                "repair_checkpoint": "attach_brf2_watcher_fact_input_producer",
            },
            "fact_input_checkpoint": "attach_brf2_watcher_fact_input_producer",
            "checks": {
                "fact_input_present": False,
                "watcher_tick_present": False,
                "missing_watcher_input": True,
                "actionable_now": False,
                "real_order_authority": False,
            },
            "interaction": {
                "level": "L0_local_brf2_runtime_signal_facts",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _expected_brf2_fact_input_gap() -> dict:
    return {
        "class": "missing_fact",
        "source": "brf2_runtime_signal_facts",
        "strategy_group_id": "BRF2-001",
        "gap": "brf2_watcher_fact_input_missing",
        "owner": "engineering",
        "next_engineering_checkpoint": "attach_brf2_watcher_fact_input_producer",
        "requirement": "BRF2 armed observation must have watcher fact input before it can be classified as market wait",
        "missing_or_false": [
            "brf2_runtime_signal_fact_input_present",
            "brf2_runtime_signal_watcher_tick_present",
        ],
    }


def test_brf2_fact_input_gap_clears_when_watcher_facts_are_present():
    module = _load_module()

    gap = module._brf2_fact_input_non_market_gap(
        {
            "status": "brf2_runtime_signal_facts_ready",
            "fact_input_present": True,
            "watcher_tick_present": True,
        },
        {
            "status": "brf2_runtime_signal_capture_ready",
            "signal_detector_preview": {
                "current_signal_state": "fresh_signal_absent",
                "first_blocker_class": "fresh_brf2_short_signal_absent",
                "first_blocker_owner": "market",
            },
        },
    )

    assert gap is None


def _write_ready_brf2_runtime_signal_capture(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.brf2_runtime_signal_capture.v1",
            "scope": "brf2_runtime_signal_capture_read_model",
            "status": "brf2_runtime_signal_capture_ready",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "strategy_group_id": "BRF2-001",
            "fact_input_status": "brf2_runtime_signal_facts_missing_watcher_input",
            "fact_input_present": False,
            "watcher_tick_present": False,
            "watcher_scope": {
                "strategy_group_id": "BRF2-001",
                "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
                "side_scope": ["short"],
                "timeframes": ["1h_closed", "5m_closed"],
            },
            "signal_detector_preview": {
                "detector_ready": True,
                "fact_input_present": False,
                "watcher_tick_present": False,
                "fact_input_status": "brf2_runtime_signal_facts_missing_watcher_input",
                "fresh_signal_present": False,
                "current_signal_state": "fact_input_missing",
                "first_blocker_class": "brf2_watcher_fact_input_missing",
                "first_blocker_owner": "engineering",
                "signal_capture_checkpoint": "attach_brf2_watcher_fact_input_producer",
                "missing_required_fact_keys": ["closed_1h_ohlcv"],
                "active_disable_fact_keys": [],
            },
            "no_action_attribution": {
                "attribution_ready": True,
                "strategy_group_id": "BRF2-001",
                "reason": "brf2_watcher_fact_input_missing",
                "blocked_fact_count": 1,
                "blocker_owner": "engineering",
            },
            "shadow_candidate_shape": {
                "shadow_candidate_ready": False,
                "shadow_candidate_type": (
                    "brf2_non_executing_short_signal_candidate_evidence"
                ),
            },
            "checks": {
                "mapping_ready": True,
                "fact_input_present": False,
                "watcher_tick_present": False,
                "fresh_signal_present": False,
                "missing_required_fact_count": 1,
                "active_disable_fact_count": 0,
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "interaction": {
                "level": "L0_local_brf2_runtime_signal_capture",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _write_ready_trial_asset_admission_proposal(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.strategygroup_trial_asset_admission_proposal.v1",
            "scope": "strategygroup_trial_asset_admission_proposal",
            "status": "trial_asset_admission_proposal_ready",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "proposal": {
                "strategy_group_id": "BRF2-001",
                "current_stage": "tiny_live_intake_candidate",
                "proposed_stage": "admitted_trial_asset",
                "owner_policy_required": False,
            "owner_policy_recorded": True,
            "owner_policy_scope_missing": False,
            "non_authority_checkpoint": (
                "close_brf2_required_facts_mapping_for_armed_observation"
            ),
                "after_next_state": "armed_observation",
                "actionable_now": False,
                "real_order_authority": False,
            },
            "owner_policy_checkpoint": {
                "owner_policy_required": False,
                "owner_policy_recorded": True,
                "owner_policy_scope_missing": False,
                "owner_policy_fields": [
                    "capital_scope",
                    "max_notional",
                    "valid_until",
                    "slippage_limit",
                    "trial_identity",
                ],
                "owner_intervention_required_now": False,
                "owner_intervention_required": False,
            },
            "checks": {
                "proposal_generated": True,
                "owner_policy_required": False,
                "owner_policy_recorded": True,
                "owner_policy_scope_missing": False,
                "owner_intervention_required": False,
                "actionable_now": False,
                "real_order_authority": False,
            },
            "interaction": {
                "level": "L0_local_trial_asset_admission_proposal",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _write_ready_brf2_owner_trial_policy_scope(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.brf2_owner_trial_policy_scope.v0",
            "scope": "final_owned_brf2_owner_trial_policy_scope_non_executing",
            "status": "brf2_owner_trial_policy_scope_recorded",
            "generated_at_utc": "2026-06-23T00:00:00+00:00",
            "brf2_policy_scope_recorded": True,
            "owner_policy_recorded": True,
            "owner_policy_scope_missing": False,
            "brf2_stage_after_policy": "admitted_trial_asset",
            "brf2_new_first_blocker": "required_facts_mapping_gap",
            "brf2_policy_checkpoint": (
                "close_brf2_required_facts_mapping_for_armed_observation"
            ),
            "policy": {
                "strategy_group_id": "BRF2-001",
                "trial_identity": "BRF2_CONTROLLED_SHORT_TRIAL_V0",
                "capital_scope": {
                    "type": "isolated_subaccount_full_allocation",
                    "allocation_mode": "full_available_isolated_subaccount",
                    "amount_source": "action_time_exchange_available_balance",
                    "currency": "USDT",
                    "loss_capable": True,
                },
                "side_scope": ["short"],
                "symbol_scope": "brf2_research_supported_symbols_only",
                "leverage_scenario": "5x_scenario_not_authority",
                "max_notional": {
                    "currency": "USDT",
                    "balance_source": "action_time_exchange_available_balance",
                },
                "attempt_cap": 3,
                "loss_unit": {
                    "currency": "USDT",
                    "balance_source": "action_time_exchange_available_balance",
                },
            },
            "interaction": {
                "level": "L0_local_brf2_owner_trial_policy_scope",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
        },
    )


def _write_ready_strategygroup_portfolio_board(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "portfolio_board_ready",
            "portfolio_summary": {
                "portfolio_row_count": 10,
                "trial_candidate_count": 5,
                "engineering_continuation_count": 9,
                "owner_policy_queue_count": 4,
            },
            "trial_candidate_pool": {
                "candidate_count": 5,
                "eligible_now_count": 1,
                "actionable_now_count": 0,
                "live_permission_change_count": 0,
            },
            "owner_progress_projection": {
                "owner_intervention_required": False,
            },
            "interaction": {
                "level": "L0_local_strategygroup_portfolio_board",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
                "registry_authority_changed": False,
                "tier_policy_changed": False,
                "live_profile_changed": False,
                "order_sizing_changed": False,
            },
        },
    )


def _write_ready_capital_trial_envelope_projection(command: list[str]) -> None:
    assert "--research-intake-review-json" in command
    _write_output(
        command,
        {
            "status": "trial_envelope_projection_ready",
            "projection_schema": (
                "brc.strategygroup_capital_trial_envelope_projection.v1"
            ),
            "projection_status": "trial_envelope_projection_ready",
            "projection_metadata": {
                "artifact_role": "trial_envelope_projection",
                "strategygroup_lifecycle_owner": False,
                "tradeability_decision_source": False,
                "runtime_truth_source": False,
            },
            "capital_trial_summary": {
                "eligibility_row_count": 7,
                "non_mpg_trial_candidate_count": 7,
                "selected_non_mpg_strategy_group_id": "BRF2-001",
                "selected_short_strategy_group_id": "BRF2-001",
                "short_experiment_candidate_count": 1,
                "selected_candidate_status": (
                    "short_experiment_evidence_pending_owner_policy"
                ),
                "trial_envelope_generated": True,
                "actionable_now_count": 0,
                "live_permission_change_count": 0,
                "real_order_authority_count": 0,
                "owner_policy_checkpoint_count": 1,
            },
            "trial_envelope_v0": {
                "schema": "brc.strategygroup_capital_trial_envelope.v0",
                "strategy_group_id": "BRF2-001",
                "policy_outcome": "promote",
                "reason": "promote_to_tiny_live_intake_candidate_not_live_ready",
                "promotion_scope": "intake_only",
                "promotion_target": "paper_observation_or_experiment_evidence",
                "tiny_live_ready": False,
                "next_checkpoint": "BRF2-001_tiny_live_intake_evidence",
                "side_scope": ["short"],
                "actionable_now": False,
                "live_permission_change": False,
                "real_order_authority": False,
            },
            "selected_non_mpg_trial_candidate": {
                "strategy_group_id": "BRF2-001",
                "strategy_asset_current_decision": "promote",
                "reason": "promote_to_tiny_live_intake_candidate_not_live_ready",
                "promotion_scope": "intake_only",
                "promotion_target": "paper_observation_or_experiment_evidence",
                "tiny_live_ready": False,
                "next_checkpoint": "BRF2-001_tiny_live_intake_evidence",
                "side_scope": ["short"],
            },
            "owner_policy_checkpoint": {
                "runtime_owner_intervention_required": False,
            },
            "interaction": {
                "level": "L0_local_capital_trial_envelope_projection",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
                "registry_authority_changed": False,
                "tier_policy_changed": False,
                "live_profile_changed": False,
                "order_sizing_changed": False,
            },
        },
    )


def _write_ready_strategygroup_research_intake_review(command: list[str]) -> None:
    _write_output(
        command,
        {
            "status": "research_intake_review_ready",
            "summary": {
                "candidate_count": 2,
                "paper_observation_admission_candidate_count": 1,
                "role_only_intake_candidate_count": 1,
                "actionable_now_count": 0,
                "real_order_authority_count": 0,
            },
            "candidate_rows": [
                {
                    "strategy_group_id": "BRF2-001",
                    "main_control_intake_position": (
                        "paper_observation_admission_candidate"
                    ),
                    "actionable_now": False,
                    "real_order_authority": False,
                },
                {
                    "strategy_group_id": "RBR2-001",
                    "main_control_intake_position": "role_only_intake_candidate",
                    "actionable_now": False,
                    "real_order_authority": False,
                },
            ],
            "strategy_decision_provenance_rows": [
                {
                    "strategy_group_id": "BRF2-001",
                    "tier": "unknown",
                    "opportunity_type": "research_intake",
                    "decision": "promote",
                    "required_next_evidence": "paper_observation_evidence_shape",
                    "authority_boundary": (
                        "research_intake_review_only; real_order_authority=false"
                    ),
                    "next_checkpoint": (
                        "BRF2-001_paper_observation_admission_evidence"
                    ),
                },
                {
                    "strategy_group_id": "RBR2-001",
                    "tier": "unknown",
                    "opportunity_type": "research_intake",
                    "decision": "keep_observing",
                    "required_next_evidence": "range_detector_facts",
                    "authority_boundary": (
                        "research_intake_review_only; real_order_authority=false"
                    ),
                    "next_checkpoint": (
                        "RBR2-001_role_only_range_detector_classifier_merge_note"
                    ),
                },
            ],
            "interaction": {
                "level": "L0_local_research_intake_review",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "actionable_now": False,
                "real_order_authority": False,
                "final_gate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
                "tier_policy_changed": False,
                "live_profile_changed": False,
            },
        },
    )


def _write_passed_runtime_dry_run_audit_chain(command: list[str]) -> None:
    _write_output(
        command,
        {
            "schema": "brc.runtime_dry_run_audit_chain.v1",
            "scope": "runtime_dry_run_audit_chain",
            "status": "passed",
            "scenario_count": 14,
            "checks": {
                "dangerous_effects_absent": True,
                "required_scenarios_present": True,
                "all_scenarios_passed": True,
            },
            "interaction": {
                "level": "L0_local_runtime_dry_run_audit_chain",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_finalgate": False,
                "calls_operation_layer": False,
                "calls_exchange_write": False,
                "places_order": False,
            },
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )


def _write_ready_daily_live_enablement_table(command: list[str]) -> None:
    rows = []
    for rank, strategy_group_id in enumerate(
        ["CPM-RO-001", "MPG-001", "MI-001", "SOR-001", "BRF2-001"],
        start=1,
    ):
        blocker = (
            "computed_not_satisfied"
            if strategy_group_id in {"CPM-RO-001", "BRF2-001"}
            else "scope_not_attached"
            if strategy_group_id in {"MPG-001", "MI-001"}
            else "detector_not_attached"
        )
        rows.append(
            {
                "strategy_group_id": strategy_group_id,
                "symbol": "SOLUSDT",
                "side": "long",
                "stage": "armed",
                "chain_position": "tradeability_first_blocker",
                "first_blocker": blocker,
                "first_blocker_evidence": (
                    "output/runtime-monitor/latest-strategygroup-tradeability-decision.json"
                ),
                "owner_action_required": "no",
                "next_engineering_action": "continue_observation_with_failed_fact_matrix",
                "stop_condition": "first_blocker changes or lane exits WIP",
                "closest_to_live_rank": rank,
                "rank_reason": f"fixture rank {rank}",
                "authority_boundary": (
                    "daily_table_is_read_model; "
                    "no_finalgate_no_operation_layer_no_exchange_write"
                ),
                "market_wait_validation": {
                    "valid": False,
                    "not_applicable": True,
                    "checks": {},
                },
            }
        )
    source_validation = {
        "valid": True,
        "sources": {
            "tradeability": {
                "present": True,
                "valid": True,
                "schema_valid": True,
                "status_valid": True,
                "expected_schema": "brc.strategygroup_tradeability_decision.v1",
                "actual_schema": "brc.strategygroup_tradeability_decision.v1",
                "expected_statuses": ["tradeability_decision_ready"],
                "actual_status": "tradeability_decision_ready",
            },
            "replay_live_parity": {
                "present": True,
                "valid": True,
                "schema_valid": True,
                "status_valid": True,
                "expected_schema": "brc.replay_live_parity_audit.v1",
                "actual_schema": "brc.replay_live_parity_audit.v1",
                "expected_statuses": ["replay_live_parity_audit_ready"],
                "actual_status": "replay_live_parity_audit_ready",
            },
            "action_time_boundary": {
                "present": True,
                "valid": True,
                "schema_valid": True,
                "status_valid": True,
                "expected_schema": (
                    "brc.strategy_fresh_signal_action_time_boundary.v1"
                ),
                "actual_schema": (
                    "brc.strategy_fresh_signal_action_time_boundary.v1"
                ),
                "expected_statuses": [
                    "strategy_fresh_signal_action_time_boundary_ready"
                ],
                "actual_status": (
                    "strategy_fresh_signal_action_time_boundary_ready"
                ),
            },
            "mi_trial_admission": {
                "present": True,
                "valid": True,
                "schema_valid": True,
                "status_valid": True,
                "expected_schema": "brc.mi_trial_admission_decision.v1",
                "actual_schema": "brc.mi_trial_admission_decision.v1",
                "expected_statuses": ["mi_trial_admission_decision_ready"],
                "actual_status": "mi_trial_admission_decision_ready",
            },
            "runtime_safety": {
                "present": True,
                "valid": True,
                "schema_valid": True,
                "status_valid": True,
                "expected_schema": "brc.strategygroup_runtime_safety_state.v1",
                "actual_schema": "brc.strategygroup_runtime_safety_state.v1",
                "expected_statuses": [
                    "live_submit_ready",
                    "live_submit_standby_waiting_for_market",
                    "runtime_safety_state_ready",
                ],
                "actual_status": "runtime_safety_state_ready",
            },
        },
    }
    _write_output(
        command,
        {
            "schema": "brc.daily_live_enablement_table.v1",
            "scope": "daily_live_enablement_table_non_authority",
            "status": "daily_live_enablement_table_ready",
            "generated_at_utc": "2026-07-01T00:00:00+00:00",
            "source_validation": source_validation,
            "rows": rows,
            "summary": {
                "row_count": 5,
                "wip_lane_count": 5,
                "rank_1_lane": "CPM-RO-001:SOLUSDT",
                "rank_1_first_blocker": "computed_not_satisfied",
                "rank_1_next_engineering_action": (
                    "continue_observation_with_failed_fact_matrix"
                ),
                "owner_action_required_count": 0,
                "source_validation_valid": True,
                "non_authority": True,
            },
            "checks": {
                "source_validation_passed": True,
                "active_wip_lanes_only": True,
                "single_rank_1": True,
                "all_rows_have_blocker_evidence_action_stop": True,
                "authority_boundary_preserved": True,
                "finalgate_called": False,
                "operation_layer_called": False,
                "exchange_write_called": False,
                "order_created": False,
            },
            "interaction": {
                "level": "L0_local_daily_live_enablement_table",
                "remote_interaction_count": 0,
                "mutates_remote_files": False,
                "approaches_real_order": False,
            },
        },
    )


def _maybe_write_strategygroup_closure_step(
    script: str, command: list[str]
) -> subprocess.CompletedProcess[str] | None:
    if script == "runtime_dry_run_audit_chain.py":
        _write_passed_runtime_dry_run_audit_chain(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_quality_wave.py":
        _write_ready_strategygroup_quality_wave(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_handoff_boundary_closure.py":
        _write_ready_handoff_boundary_closure(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_btpc_fact_classifier_guard.py":
        _write_ready_btpc_fact_classifier_guard(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_lifecycle_rehearsal.py":
        _write_ready_lifecycle_rehearsal(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_pre_live_rehearsal_readiness.py":
        _write_ready_pre_live_rehearsal_readiness(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_runtime_safety_state.py":
        _write_ready_runtime_safety_state(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_trial_grade_signal_gate_audit.py":
        _write_ready_trial_grade_signal_gate_audit(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_three_strategy_live_trial_portfolio.py":
        _write_ready_three_strategy_live_trial_portfolio(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_tradeability_decision.py":
        _write_ready_tradeability_decision(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_daily_live_enablement_table.py":
        _write_ready_daily_live_enablement_table(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "validate_daily_live_enablement_table.py":
        from scripts.validate_daily_live_enablement_table import (  # noqa: PLC0415
            validate_daily_live_enablement_table,
        )

        table_path = Path(command[-1])
        table = json.loads(table_path.read_text(encoding="utf-8"))
        errors = validate_daily_live_enablement_table(table)
        return subprocess.CompletedProcess(
            command,
            1 if errors else 0,
            "",
            "\n".join(errors),
        )
    if script == "build_single_lane_task_packet.py":
        from scripts.build_single_lane_task_packet import (  # noqa: PLC0415
            build_single_lane_task_packet,
        )

        daily_table_path = Path(command[command.index("--daily-table-json") + 1])
        output_json = Path(command[command.index("--output-json") + 1])
        output_md = Path(command[command.index("--output-owner-progress") + 1])
        packet = build_single_lane_task_packet(
            daily_table=json.loads(daily_table_path.read_text(encoding="utf-8")),
            source="output/runtime-monitor/latest-daily-live-enablement-table.json",
            generated_at_utc="2026-07-01T00:00:00+00:00",
        )
        output_json.write_text(json.dumps(packet), encoding="utf-8")
        output_md.write_text("## Single Lane Task Packet\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "validate_single_lane_task_packet.py":
        from scripts.validate_single_lane_task_packet import (  # noqa: PLC0415
            validate_single_lane_task_packet,
        )

        packet_path = Path(command[-1])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        errors = validate_single_lane_task_packet(packet)
        return subprocess.CompletedProcess(
            command,
            1 if errors else 0,
            "",
            "\n".join(errors),
        )
    if script == "build_strategy_live_candidate_pool.py":
        from scripts.build_strategy_live_candidate_pool import (  # noqa: PLC0415
            build_strategy_live_candidate_pool,
        )

        daily_table_path = Path(command[command.index("--daily-table-json") + 1])
        tradeability_path = Path(command[command.index("--tradeability-json") + 1])
        parity_path = Path(command[command.index("--replay-live-parity-json") + 1])
        action_time_path = Path(command[command.index("--action-time-boundary-json") + 1])
        packet_path = Path(command[command.index("--single-lane-task-packet-json") + 1])
        runtime_active_monitor_path = Path(
            command[command.index("--runtime-active-monitor-json") + 1]
        )
        output_json = Path(command[command.index("--output-json") + 1])
        output_md = Path(command[command.index("--output-owner-progress") + 1])
        artifact = build_strategy_live_candidate_pool(
            daily_table=json.loads(daily_table_path.read_text(encoding="utf-8")),
            tradeability=json.loads(tradeability_path.read_text(encoding="utf-8")),
            replay_live_parity=json.loads(parity_path.read_text(encoding="utf-8")),
            action_time_boundary=json.loads(action_time_path.read_text(encoding="utf-8")),
            single_lane_task_packet=json.loads(packet_path.read_text(encoding="utf-8")),
            runtime_active_monitor=(
                json.loads(runtime_active_monitor_path.read_text(encoding="utf-8"))
                if runtime_active_monitor_path.exists()
                else {}
            ),
            generated_at_utc="2026-07-01T00:00:00+00:00",
        )
        output_json.write_text(json.dumps(artifact), encoding="utf-8")
        output_md.write_text("## Strategy Live Candidate Pool\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "validate_strategy_live_candidate_pool.py":
        from scripts.validate_strategy_live_candidate_pool import (  # noqa: PLC0415
            validate_strategy_live_candidate_pool,
        )

        artifact_path = Path(command[-1])
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        errors = validate_strategy_live_candidate_pool(artifact)
        return subprocess.CompletedProcess(
            command,
            1 if errors else 0,
            "",
            "\n".join(errors),
        )
    if script == "build_brf2_owner_trial_policy_scope.py":
        _write_ready_brf2_owner_trial_policy_scope(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_brf2_required_facts_mapping.py":
        _write_ready_brf2_required_facts_mapping(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_brf2_runtime_signal_facts.py":
        _write_missing_brf2_runtime_signal_facts(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_brf2_runtime_signal_capture.py":
        _write_ready_brf2_runtime_signal_capture(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_portfolio_board.py":
        _write_ready_strategygroup_portfolio_board(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_capital_trial_envelope_projection.py":
        _write_ready_capital_trial_envelope_projection(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_trial_asset_admission_proposal.py":
        _write_ready_trial_asset_admission_proposal(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    if script == "build_strategygroup_research_intake_review.py":
        _write_ready_strategygroup_research_intake_review(command)
        return subprocess.CompletedProcess(command, 0, "", "")
    return None


def test_local_monitor_sequence_runs_cache_checks_in_order(tmp_path: Path) -> None:
    module = _load_module()
    calls: list[str] = []
    btpc_fact_quality_commands: list[list[str]] = []
    btpc_local_proxy_commands: list[list[str]] = []
    btpc_proxy_replay_commands: list[list[str]] = []
    decision_loop_commands: list[list[str]] = []
    btpc_keep_revise_commands: list[list[str]] = []
    btpc_live_source_mapping_commands: list[list[str]] = []
    btpc_classifier_rule_commands: list[list[str]] = []
    btpc_fact_classifier_guard_commands: list[list[str]] = []
    strategy_asset_state_commands: list[list[str]] = []
    quality_wave_commands: list[list[str]] = []
    l2_readiness_commands: list[list[str]] = []
    runtime_safety_state_commands: list[list[str]] = []
    trial_admission_commands: list[list[str]] = []
    portfolio_board_commands: list[list[str]] = []
    three_strategy_commands: list[list[str]] = []
    tradeability_commands: list[list[str]] = []
    daily_table_commands: list[list[str]] = []
    daily_table_validator_commands: list[list[str]] = []
    single_lane_task_packet_commands: list[list[str]] = []
    single_lane_task_packet_validator_commands: list[list[str]] = []
    strategy_live_candidate_pool_commands: list[list[str]] = []
    strategy_live_candidate_pool_validator_commands: list[list[str]] = []
    binance_public_facts_commands: list[list[str]] = []
    sor_session_scope_detector_commands: list[list[str]] = []
    action_time_boundary_commands: list[list[str]] = []
    replay_live_parity_commands: list[list[str]] = []
    mi_trial_admission_commands: list[list[str]] = []
    dry_run_audit_commands: list[list[str]] = []

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        script = Path(command[1]).name
        calls.append(script)
        if script == "build_strategygroup_btpc_l2_shadow_fact_quality_review.py":
            btpc_fact_quality_commands.append(command)
        if script == "build_strategygroup_btpc_local_fact_proxy_review.py":
            btpc_local_proxy_commands.append(command)
        if script == "build_strategygroup_btpc_proxy_replay_quality_review.py":
            btpc_proxy_replay_commands.append(command)
        if script == "build_strategygroup_trial_asset_admission_proposal.py":
            trial_admission_commands.append(command)
        if script == "build_strategygroup_portfolio_board.py":
            portfolio_board_commands.append(command)
        if script == "build_strategygroup_l2_readiness_review.py":
            l2_readiness_commands.append(command)
        if script == "build_strategygroup_btpc_l2_keep_revise_fact_source_review.py":
            btpc_keep_revise_commands.append(command)
        if script == "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py":
            btpc_live_source_mapping_commands.append(command)
        if script == "build_strategygroup_btpc_classifier_rule_review.py":
            btpc_classifier_rule_commands.append(command)
        if script == "build_strategygroup_btpc_fact_classifier_guard.py":
            btpc_fact_classifier_guard_commands.append(command)
        if script == "build_strategygroup_strategy_asset_state.py":
            strategy_asset_state_commands.append(command)
        if script == "build_strategygroup_quality_wave.py":
            quality_wave_commands.append(command)
        if script == "build_strategygroup_runtime_safety_state.py":
            runtime_safety_state_commands.append(command)
        if script == "build_strategygroup_three_strategy_live_trial_portfolio.py":
            three_strategy_commands.append(command)
        if script == "build_strategygroup_tradeability_decision.py":
            tradeability_commands.append(command)
        if script == "build_daily_live_enablement_table.py":
            daily_table_commands.append(command)
        if script == "validate_daily_live_enablement_table.py":
            daily_table_validator_commands.append(command)
        if script == "build_single_lane_task_packet.py":
            single_lane_task_packet_commands.append(command)
        if script == "validate_single_lane_task_packet.py":
            single_lane_task_packet_validator_commands.append(command)
        if script == "build_strategy_live_candidate_pool.py":
            strategy_live_candidate_pool_commands.append(command)
        if script == "validate_strategy_live_candidate_pool.py":
            strategy_live_candidate_pool_validator_commands.append(command)
        if script == "fetch_binance_usdm_public_facts.py":
            binance_public_facts_commands.append(command)
        if script == "build_sor_session_scope_detector.py":
            sor_session_scope_detector_commands.append(command)
        if script == "build_strategy_fresh_signal_action_time_boundary.py":
            action_time_boundary_commands.append(command)
        if script == "build_replay_live_parity_audit.py":
            replay_live_parity_commands.append(command)
        if script == "build_mi_trial_admission_decision.py":
            mi_trial_admission_commands.append(command)
        if script == "runtime_dry_run_audit_chain.py":
            dry_run_audit_commands.append(command)
        closure_result = _maybe_write_strategygroup_closure_step(script, command)
        if closure_result is not None:
            return closure_result
        if script == "build_strategygroup_post_revision_replay_review.py":
            _write_passed_post_revision_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_opportunity_review_work_loop.py":
            decision_loop_commands.append(command)
            _write_ready_opportunity_review_work_loop(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_l2_shadow_fact_quality_review.py":
            _write_ready_btpc_fact_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_local_fact_proxy_review.py":
            _write_ready_btpc_local_fact_proxy_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_proxy_replay_quality_review.py":
            _write_ready_btpc_proxy_replay_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_l2_keep_revise_fact_source_review.py"
        ):
            _write_ready_btpc_l2_keep_revise_fact_source_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ):
            _write_ready_btpc_live_derivatives_fact_source_mapping(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_classifier_rule_review.py":
            _write_ready_btpc_classifier_rule_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_strategy_asset_state.py":
            _write_ready_strategy_asset_state(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_daily_check.py":
            _write_output(
                command,
                {
                    "status": "waiting_for_market",
                    "interaction": {
                        "level": "L0_local_cache_read",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "runtime_live_cutover_readiness.py":
            _write_output(
                command,
                {
                    "status": "live_cutover_waiting_for_fresh_signal",
                    "interaction": {
                        "level": "L0_local_cutover_readiness",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "run_strategygroup_runtime_goal_progress_audit.py":
            _write_output(
                command,
                {
                    "status": "waiting_for_market",
                    "interaction": {
                        "level": "L0_local_goal_progress_audit",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "runtime_first_bounded_live_order_completion_audit.py":
            _write_output(
                command,
                {
                    "status": "not_complete_waiting_for_market",
                    "non_market_gaps": [],
                    "interaction": {
                        "level": "L0_local_completion_audit",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "checks": {"btpc001_l2_shadow_replay_cases_present": True},
                    "interaction": {
                        "level": "L0_local_replay_lab",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "run_strategygroup_signal_coverage_diagnostic.py":
            _write_output(
                command,
                {
                    "status": "mainline_and_broader_no_signal",
                    "interaction": {
                        "level": "L0_local_signal_coverage",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "build_strategygroup_signal_coverage_expansion_review.py":
            _write_output(
                command,
                {
                    "status": "no_expansion_review_needed",
                    "interaction": {
                        "level": "L0_local_signal_coverage_expansion_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "build_strategygroup_l2_readiness_review.py":
            _write_output(
                command,
                {
                    "status": "l2_readiness_review_no_rows",
                    "interaction": {
                        "level": "L0_local_l2_readiness_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "run_strategygroup_l2_intake_dry_run.py":
            _write_output(
                command,
                {
                    "status": "l2_intake_dry_run_no_candidates",
                    "interaction": {
                        "level": "L0_local_l2_intake_dry_run",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif script == "build_brf2_shadow_candidate_evidence.py":
            _write_output(
                command,
                {
                    "status": (
                        "brf2_shadow_candidate_evidence_waiting_for_fresh_signal"
                    ),
                    "strategy_group_id": "BRF2-001",
                    "shadow_candidate_evidence_ready": False,
                    "shadow_candidate_evidence": {
                        "shadow_candidate_evidence_type": (
                            "brf2_non_executing_short_signal_candidate_evidence"
                        ),
                        "signal_state": "fresh_signal_absent",
                    },
                    "first_blocker": {
                        "class": "fresh_brf2_short_signal_absent",
                        "owner": "market",
                        "next_action": (
                            "continue_brf2_armed_observation_until_fresh_signal"
                        ),
                    },
                    "next_runtime_step": (
                        "continue_brf2_armed_observation_until_fresh_signal"
                    ),
                    "checks": {
                        "required_facts_satisfied": False,
                        "disable_facts_clear": False,
                    },
                    "interaction": {
                        "level": "L0_local_brf2_shadow_candidate_evidence",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        elif _write_ready_cpm_artifact(command, script):
            pass
        elif script == "build_strategygroup_trial_grade_signal_gate_audit.py":
            _write_ready_trial_grade_signal_gate_audit(command)
        else:
            assert script == "run_strategygroup_l2_tier_policy_review.py"
            _write_output(
                command,
                {
                    "status": "l2_tier_policy_review_no_candidates",
                    "interaction": {
                        "level": "L0_local_l2_tier_policy_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    report = module.build_local_monitor_sequence_report(
        daily_check_json=tmp_path / "daily.json",
        daily_owner_progress=tmp_path / "daily.md",
        live_cutover_json=tmp_path / "cutover.json",
        live_cutover_md=tmp_path / "cutover.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        dry_run_audit_json=tmp_path / "dry-run-audit-chain.json",
        dry_run_audit_dir=tmp_path / "dry-run-audit-chain",
        replay_lab_json=tmp_path / "replay.json",
        replay_lab_md=tmp_path / "replay.md",
        signal_coverage_json=tmp_path / "signal-coverage.json",
        signal_coverage_md=tmp_path / "signal-coverage.md",
        signal_coverage_expansion_review_json=tmp_path / "signal-expansion.json",
        signal_coverage_expansion_review_md=tmp_path / "signal-expansion.md",
        l2_readiness_review_json=tmp_path / "l2-review.json",
        l2_readiness_review_md=tmp_path / "l2-review.md",
        l2_intake_dry_run_json=tmp_path / "l2-dry-run.json",
        l2_intake_dry_run_md=tmp_path / "l2-dry-run.md",
        l2_tier_policy_review_json=tmp_path / "l2-tier-review.json",
        l2_tier_policy_review_md=tmp_path / "l2-tier-review.md",
        post_revision_replay_review_json=tmp_path / "post-revision-review.json",
        post_revision_replay_review_md=tmp_path / "post-revision-review.md",
        opportunity_review_work_loop_json=tmp_path / "opportunity-review-work-loop.json",
        opportunity_review_work_loop_md=tmp_path / "opportunity-review-work-loop.md",
        btpc_l2_shadow_fact_quality_review_json=tmp_path / "btpc-fact-review.json",
        btpc_l2_shadow_fact_quality_review_md=tmp_path / "btpc-fact-review.md",
        btpc_local_fact_proxy_review_json=tmp_path / "btpc-proxy-review.json",
        btpc_local_fact_proxy_review_md=tmp_path / "btpc-proxy-review.md",
        btpc_proxy_replay_quality_review_json=tmp_path / "btpc-proxy-replay.json",
        btpc_proxy_replay_quality_review_md=tmp_path / "btpc-proxy-replay.md",
        btpc_l2_keep_revise_fact_source_review_json=tmp_path
        / "btpc-l2-decision.json",
        btpc_l2_keep_revise_fact_source_review_md=tmp_path
        / "btpc-l2-decision.md",
        btpc_live_derivatives_fact_source_mapping_json=tmp_path
        / "btpc-live-source-mapping.json",
        btpc_live_derivatives_fact_source_mapping_md=tmp_path
        / "btpc-live-source-mapping.md",
        btpc_classifier_rule_review_json=tmp_path / "btpc-classifier-rule.json",
        btpc_classifier_rule_review_md=tmp_path / "btpc-classifier-rule.md",
        strategy_asset_state_json=tmp_path / "strategy-asset-state.json",
        strategy_asset_state_md=tmp_path / "strategy-asset-state.md",
        strategygroup_quality_wave_json=tmp_path / "quality-wave.json",
        strategygroup_quality_wave_md=tmp_path / "quality-wave.md",
        strategygroup_handoff_boundary_closure_json=tmp_path
        / "handoff-boundary.json",
        strategygroup_handoff_boundary_closure_md=tmp_path
        / "handoff-boundary.md",
        strategygroup_btpc_fact_classifier_guard_json=tmp_path
        / "btpc-guard.json",
        strategygroup_btpc_fact_classifier_guard_md=tmp_path
        / "btpc-guard.md",
        strategygroup_lifecycle_rehearsal_json=tmp_path / "lifecycle.json",
        strategygroup_lifecycle_rehearsal_md=tmp_path / "lifecycle.md",
        strategygroup_pre_live_rehearsal_readiness_json=tmp_path
        / "pre-live-readiness.json",
        strategygroup_pre_live_rehearsal_readiness_md=tmp_path
        / "pre-live-readiness.md",
        strategygroup_runtime_safety_state_json=tmp_path
        / "runtime-safety-state.json",
        strategygroup_runtime_safety_state_md=tmp_path
        / "runtime-safety-state.md",
        strategy_capture_gap_audit_json=tmp_path / "capture-gap-audit.json",
        strategygroup_portfolio_board_json=tmp_path / "portfolio-board.json",
        strategygroup_portfolio_board_md=tmp_path / "portfolio-board.md",
        strategygroup_review_only_deep_dive_wave_json=tmp_path
        / "review-deep-dive.json",
        strategygroup_owner_policy_package_json=tmp_path
        / "owner-policy-package.json",
        strategygroup_quality_closure_wave_json=tmp_path / "quality-closure.json",
        strategygroup_trial_candidate_pool_md=tmp_path / "trial-pool.md",
        strategygroup_capital_trial_envelope_projection_json=tmp_path
        / "capital-trial-envelope-projection.json",
        strategygroup_capital_trial_envelope_projection_md=tmp_path
        / "capital-trial-envelope-projection.md",
        strategygroup_capital_trial_envelope_json=tmp_path / "trial-envelope.json",
        strategygroup_capital_trial_envelope_md=tmp_path / "trial-envelope.md",
        strategygroup_research_intake_review_json=tmp_path
        / "research-intake-review.json",
        strategygroup_research_intake_review_md=tmp_path
        / "research-intake-review.md",
        strategygroup_trial_asset_admission_proposal_json=tmp_path
        / "trial-admission-proposal.json",
        strategygroup_trial_asset_admission_proposal_md=tmp_path
        / "trial-admission-proposal.md",
        brf2_owner_trial_policy_scope_json=tmp_path / "brf2-policy.json",
        brf2_owner_trial_policy_scope_md=tmp_path / "brf2-policy.md",
        brf2_required_facts_mapping_json=tmp_path / "brf2-required-facts.json",
        brf2_required_facts_mapping_md=tmp_path / "brf2-required-facts.md",
        brf2_runtime_signal_facts_json=tmp_path / "brf2-signal-facts.json",
        brf2_runtime_signal_facts_md=tmp_path / "brf2-signal-facts.md",
        brf2_runtime_signal_capture_json=tmp_path / "brf2-signal-capture.json",
        brf2_runtime_signal_capture_md=tmp_path / "brf2-signal-capture.md",
        brf2_shadow_candidate_evidence_json=(
            tmp_path / "brf2-shadow-evidence.json"
        ),
        brf2_shadow_candidate_evidence_md=tmp_path / "brf2-shadow-evidence.md",
        strategy_fresh_signal_action_time_boundary_json=(
            tmp_path / "fresh-signal-action-time-boundary.json"
        ),
        strategy_fresh_signal_action_time_boundary_md=(
            tmp_path / "fresh-signal-action-time-boundary.md"
        ),
        replay_live_parity_audit_json=tmp_path / "replay-live-parity.json",
        replay_live_parity_audit_md=tmp_path / "replay-live-parity.md",
        mi_trial_admission_decision_json=tmp_path / "mi-trial-admission.json",
        mi_trial_admission_decision_md=tmp_path / "mi-trial-admission.md",
        strategygroup_trial_grade_signal_gate_audit_json=tmp_path
        / "trial-grade-audit.json",
        strategygroup_trial_grade_signal_gate_audit_md=tmp_path
        / "trial-grade-audit.md",
        three_strategy_live_trial_portfolio_json=tmp_path
        / "three-strategy-portfolio.json",
        three_strategy_live_trial_portfolio_md=tmp_path
        / "three-strategy-portfolio.md",
        strategygroup_tradeability_decision_json=tmp_path / "tradeability.json",
        strategygroup_tradeability_decision_md=tmp_path / "tradeability.md",
        daily_live_enablement_table_json=tmp_path / "daily-live-table.json",
        daily_live_enablement_table_md=tmp_path / "daily-live-table.md",
        single_lane_task_packet_json=tmp_path / "single-lane-task-packet.json",
        single_lane_task_packet_md=tmp_path / "single-lane-task-packet.md",
        binance_public_facts_ssh_host="tokyo",
        command_runner=fake_runner,
    )

    assert calls == [
        "run_strategygroup_runtime_daily_check.py",
        "runtime_dry_run_audit_chain.py",
        "runtime_live_cutover_readiness.py",
        "build_strategygroup_portfolio_board.py",
        "build_strategygroup_research_intake_review.py",
        "build_strategygroup_capital_trial_envelope_projection.py",
        "build_brf2_owner_trial_policy_scope.py",
        "build_strategygroup_trial_asset_admission_proposal.py",
        "build_brf2_required_facts_mapping.py",
        "build_brf2_runtime_signal_facts.py",
        "build_brf2_runtime_signal_capture.py",
        "build_brf2_shadow_candidate_evidence.py",
        "build_cpm_identity_routing_decision.py",
        "build_cpm_owner_trial_policy_scope.py",
        "build_cpm_required_facts_mapping.py",
        "fetch_binance_usdm_public_facts.py",
        "build_cpm_runtime_signal_facts.py",
        "build_cpm_runtime_signal_capture.py",
        "build_cpm_shadow_candidate_evidence.py",
        "build_cpm_dry_run_submit_rehearsal.py",
        "build_four_candidate_runtime_activation_evidence.py",
        "build_sor_session_scope_detector.py",
        "build_mpg_high_beta_scope_readiness.py",
        "build_strategy_fresh_signal_action_time_boundary.py",
        "build_replay_live_parity_audit.py",
        "build_mi_trial_admission_decision.py",
        "build_four_candidate_runtime_activation_closure.py",
        "run_strategygroup_runtime_goal_progress_audit.py",
        "runtime_first_bounded_live_order_completion_audit.py",
        "run_strategygroup_runtime_replay_lab.py",
        "run_strategygroup_signal_coverage_diagnostic.py",
        "build_strategygroup_signal_coverage_expansion_review.py",
        "build_strategygroup_l2_readiness_review.py",
        "run_strategygroup_l2_intake_dry_run.py",
        "run_strategygroup_l2_tier_policy_review.py",
        "build_strategygroup_post_revision_replay_review.py",
        "build_strategygroup_opportunity_review_work_loop.py",
        "build_strategygroup_btpc_l2_shadow_fact_quality_review.py",
        "build_strategygroup_btpc_local_fact_proxy_review.py",
        "build_strategygroup_btpc_proxy_replay_quality_review.py",
        "build_strategygroup_opportunity_review_work_loop.py",
        "build_strategygroup_btpc_l2_keep_revise_fact_source_review.py",
        "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py",
        "build_strategygroup_btpc_classifier_rule_review.py",
        "build_strategygroup_strategy_asset_state.py",
        "build_strategygroup_quality_wave.py",
        "build_strategygroup_handoff_boundary_closure.py",
        "build_strategygroup_btpc_fact_classifier_guard.py",
        "build_strategygroup_lifecycle_rehearsal.py",
        "build_strategygroup_pre_live_rehearsal_readiness.py",
        "build_strategygroup_runtime_safety_state.py",
        "build_strategygroup_trial_grade_signal_gate_audit.py",
        "build_strategygroup_three_strategy_live_trial_portfolio.py",
        "build_strategygroup_tradeability_decision.py",
        "build_daily_live_enablement_table.py",
        "validate_daily_live_enablement_table.py",
        "build_single_lane_task_packet.py",
        "validate_single_lane_task_packet.py",
        "build_strategy_live_candidate_pool.py",
        "validate_strategy_live_candidate_pool.py",
        "build_daily_live_enablement_table.py",
        "validate_daily_live_enablement_table.py",
        "build_single_lane_task_packet.py",
        "validate_single_lane_task_packet.py",
    ]
    assert len(decision_loop_commands) == 2
    assert len(trial_admission_commands) == 1
    assert len(portfolio_board_commands) == 1
    assert len(daily_table_commands) == 2
    assert len(daily_table_validator_commands) == 2
    assert len(single_lane_task_packet_commands) == 2
    assert len(single_lane_task_packet_validator_commands) == 2
    assert len(strategy_live_candidate_pool_commands) == 1
    assert len(strategy_live_candidate_pool_validator_commands) == 1
    assert len(binance_public_facts_commands) == 1
    binance_command = binance_public_facts_commands[0]
    assert binance_command[binance_command.index("--ssh-host") + 1] == "tokyo"
    assert len(sor_session_scope_detector_commands) == 1
    sor_session_command = sor_session_scope_detector_commands[0]
    assert sor_session_command[sor_session_command.index("--ssh-host") + 1] == "tokyo"
    bootstrap_daily_command = daily_table_commands[0]
    server_backed_daily_command = daily_table_commands[1]
    assert "--candidate-pool-json" not in bootstrap_daily_command
    assert "--candidate-pool-json" in server_backed_daily_command
    assert server_backed_daily_command[
        server_backed_daily_command.index("--candidate-pool-json") + 1
    ] == str(tmp_path / "latest-strategy-live-candidate-pool.json")
    single_lane_command = single_lane_task_packet_commands[-1]
    assert "--daily-table-json" in single_lane_command
    assert single_lane_command[
        single_lane_command.index("--daily-table-json") + 1
    ] == str(tmp_path / "daily-live-table.json")
    assert single_lane_command[
        single_lane_command.index("--output-json") + 1
    ] == str(tmp_path / "single-lane-task-packet.json")
    candidate_pool_command = strategy_live_candidate_pool_commands[0]
    assert candidate_pool_command[
        candidate_pool_command.index("--daily-table-json") + 1
    ] == str(tmp_path / "daily-live-table.json")
    assert candidate_pool_command[
        candidate_pool_command.index("--single-lane-task-packet-json") + 1
    ] == str(tmp_path / "single-lane-task-packet.json")
    assert "--runtime-active-monitor-json" in candidate_pool_command
    portfolio_board_command = portfolio_board_commands[0]
    assert "--capture-gap-audit-json" in portfolio_board_command
    assert portfolio_board_command[
        portfolio_board_command.index("--capture-gap-audit-json") + 1
    ] == str(tmp_path / "capture-gap-audit.json")
    assert portfolio_board_command[
        portfolio_board_command.index("--review-deep-dive-json") + 1
    ] == str(tmp_path / "review-deep-dive.json")
    assert portfolio_board_command[
        portfolio_board_command.index("--owner-policy-package-json") + 1
    ] == str(tmp_path / "owner-policy-package.json")
    assert portfolio_board_command[
        portfolio_board_command.index("--quality-closure-wave-json") + 1
    ] == str(tmp_path / "quality-closure.json")
    trial_admission_command = trial_admission_commands[0]
    assert "--capital-trial-envelope-projection-json" in trial_admission_command
    assert trial_admission_command[
        trial_admission_command.index("--capital-trial-envelope-projection-json") + 1
    ] == str(tmp_path / "capital-trial-envelope-projection.json")
    assert "--trial-envelope-json" in trial_admission_command
    assert trial_admission_command[
        trial_admission_command.index("--trial-envelope-json") + 1
    ] == str(tmp_path / "trial-envelope.json")
    assert "--brf2-owner-trial-policy-scope-json" in trial_admission_command
    assert trial_admission_command[
        trial_admission_command.index("--brf2-owner-trial-policy-scope-json") + 1
    ] == str(tmp_path / "brf2-policy.json")
    assert "--btpc-proxy-replay-quality-json" not in decision_loop_commands[0]
    assert "--btpc-proxy-replay-quality-json" in decision_loop_commands[1]
    assert decision_loop_commands[1][
        decision_loop_commands[1].index("--btpc-proxy-replay-quality-json") + 1
    ] == str(tmp_path / "btpc-proxy-replay.json")
    assert len(l2_readiness_commands) == 1
    l2_readiness_command = l2_readiness_commands[0]
    assert "--expansion-review-json" in l2_readiness_command
    assert l2_readiness_command[
        l2_readiness_command.index("--expansion-review-json") + 1
    ] == str(tmp_path / "signal-expansion.json")
    assert len(btpc_fact_quality_commands) == 1
    btpc_fact_quality_command = btpc_fact_quality_commands[0]
    assert "--opportunity-review-work-loop-json" in btpc_fact_quality_command
    assert btpc_fact_quality_command[
        btpc_fact_quality_command.index("--opportunity-review-work-loop-json") + 1
    ] == str(tmp_path / "opportunity-review-work-loop.json")
    assert "--l2-readiness-json" in btpc_fact_quality_command
    assert btpc_fact_quality_command[
        btpc_fact_quality_command.index("--l2-readiness-json") + 1
    ] == str(tmp_path / "l2-review.json")
    assert "--replay-lab-json" in btpc_fact_quality_command
    assert btpc_fact_quality_command[
        btpc_fact_quality_command.index("--replay-lab-json") + 1
    ] == str(tmp_path / "replay.json")
    assert len(btpc_local_proxy_commands) == 1
    btpc_local_proxy_command = btpc_local_proxy_commands[0]
    assert "--btpc-fact-quality-json" in btpc_local_proxy_command
    assert btpc_local_proxy_command[
        btpc_local_proxy_command.index("--btpc-fact-quality-json") + 1
    ] == str(tmp_path / "btpc-fact-review.json")
    assert len(btpc_proxy_replay_commands) == 1
    btpc_proxy_replay_command = btpc_proxy_replay_commands[0]
    assert "--btpc-local-fact-proxy-json" in btpc_proxy_replay_command
    assert btpc_proxy_replay_command[
        btpc_proxy_replay_command.index("--btpc-local-fact-proxy-json") + 1
    ] == str(tmp_path / "btpc-proxy-review.json")
    assert len(btpc_keep_revise_commands) == 1
    btpc_keep_revise_command = btpc_keep_revise_commands[0]
    assert "--opportunity-review-work-loop-json" in btpc_keep_revise_command
    assert btpc_keep_revise_command[
        btpc_keep_revise_command.index("--opportunity-review-work-loop-json") + 1
    ] == str(tmp_path / "opportunity-review-work-loop.json")
    assert "--btpc-proxy-replay-quality-json" in btpc_keep_revise_command
    assert btpc_keep_revise_command[
        btpc_keep_revise_command.index("--btpc-proxy-replay-quality-json") + 1
    ] == str(tmp_path / "btpc-proxy-replay.json")
    assert len(btpc_live_source_mapping_commands) == 1
    btpc_live_source_mapping_command = btpc_live_source_mapping_commands[0]
    assert "--btpc-l2-review-json" in btpc_live_source_mapping_command
    assert btpc_live_source_mapping_command[
        btpc_live_source_mapping_command.index("--btpc-l2-review-json") + 1
    ] == str(tmp_path / "btpc-l2-decision.json")
    assert len(btpc_classifier_rule_commands) == 1
    btpc_classifier_rule_command = btpc_classifier_rule_commands[0]
    assert "--btpc-l2-review-json" in btpc_classifier_rule_command
    assert btpc_classifier_rule_command[
        btpc_classifier_rule_command.index("--btpc-l2-review-json") + 1
    ] == str(tmp_path / "btpc-l2-decision.json")
    assert "--btpc-proxy-replay-quality-json" in btpc_classifier_rule_command
    assert btpc_classifier_rule_command[
        btpc_classifier_rule_command.index("--btpc-proxy-replay-quality-json") + 1
    ] == str(tmp_path / "btpc-proxy-replay.json")
    assert "--btpc-live-source-mapping-json" in btpc_classifier_rule_command
    assert btpc_classifier_rule_command[
        btpc_classifier_rule_command.index("--btpc-live-source-mapping-json") + 1
    ] == str(tmp_path / "btpc-live-source-mapping.json")
    assert len(btpc_fact_classifier_guard_commands) == 1
    btpc_fact_classifier_guard_command = btpc_fact_classifier_guard_commands[0]
    assert "--btpc-l2-review-json" in btpc_fact_classifier_guard_command
    assert btpc_fact_classifier_guard_command[
        btpc_fact_classifier_guard_command.index("--btpc-l2-review-json") + 1
    ] == str(tmp_path / "btpc-l2-decision.json")
    assert "--btpc-live-source-mapping-json" in btpc_fact_classifier_guard_command
    assert btpc_fact_classifier_guard_command[
        btpc_fact_classifier_guard_command.index("--btpc-live-source-mapping-json") + 1
    ] == str(tmp_path / "btpc-live-source-mapping.json")
    assert "--btpc-classifier-rule-review-json" in btpc_fact_classifier_guard_command
    assert btpc_fact_classifier_guard_command[
        btpc_fact_classifier_guard_command.index("--btpc-classifier-rule-review-json")
        + 1
    ] == str(tmp_path / "btpc-classifier-rule.json")
    assert len(strategy_asset_state_commands) == 1
    strategy_asset_state_command = strategy_asset_state_commands[0]
    assert "--opportunity-review-work-loop-json" in strategy_asset_state_command
    assert strategy_asset_state_command[
        strategy_asset_state_command.index("--opportunity-review-work-loop-json") + 1
    ] == str(tmp_path / "opportunity-review-work-loop.json")
    assert "--signal-coverage-json" in strategy_asset_state_command
    assert strategy_asset_state_command[
        strategy_asset_state_command.index("--signal-coverage-json") + 1
    ] == str(tmp_path / "signal-coverage.json")
    assert "--post-revision-replay-review-json" in strategy_asset_state_command
    assert strategy_asset_state_command[
        strategy_asset_state_command.index("--post-revision-replay-review-json") + 1
    ] == str(tmp_path / "post-revision-review.json")
    assert "--capture-gap-audit-json" in strategy_asset_state_command
    assert strategy_asset_state_command[
        strategy_asset_state_command.index("--capture-gap-audit-json") + 1
    ] == str(tmp_path / "capture-gap-audit.json")
    assert "--research-intake-review-json" in strategy_asset_state_command
    assert strategy_asset_state_command[
        strategy_asset_state_command.index("--research-intake-review-json") + 1
    ] == str(tmp_path / "research-intake-review.json")
    assert len(quality_wave_commands) == 1
    quality_wave_command = quality_wave_commands[0]
    assert "--strategy-asset-state-json" in quality_wave_command
    assert quality_wave_command[
        quality_wave_command.index("--strategy-asset-state-json") + 1
    ] == str(tmp_path / "strategy-asset-state.json")
    assert "--local-monitor-json" not in quality_wave_command
    assert len(runtime_safety_state_commands) == 1
    assert calls.index("build_brf2_shadow_candidate_evidence.py") < calls.index(
        "build_strategygroup_runtime_safety_state.py"
    )
    assert len(tradeability_commands) == 1
    assert len(dry_run_audit_commands) == 1
    dry_run_audit_command = dry_run_audit_commands[0]
    assert dry_run_audit_command[
        dry_run_audit_command.index("--output-json") + 1
    ] == str(tmp_path / "dry-run-audit-chain.json")
    assert dry_run_audit_command[
        dry_run_audit_command.index("--output-dir") + 1
    ] == str(tmp_path / "dry-run-audit-chain")
    assert len(three_strategy_commands) == 1
    three_strategy_command = three_strategy_commands[0]
    assert "--capital-trial-envelope-projection-json" in three_strategy_command
    assert three_strategy_command[
        three_strategy_command.index("--capital-trial-envelope-projection-json") + 1
    ] == str(tmp_path / "capital-trial-envelope-projection.json")
    assert "--trial-asset-admission-proposal-json" in three_strategy_command
    assert three_strategy_command[
        three_strategy_command.index("--trial-asset-admission-proposal-json") + 1
    ] == str(tmp_path / "trial-admission-proposal.json")
    assert "--brf2-owner-trial-policy-scope-json" in three_strategy_command
    assert three_strategy_command[
        three_strategy_command.index("--brf2-owner-trial-policy-scope-json") + 1
    ] == str(tmp_path / "brf2-policy.json")
    assert "--brf2-required-facts-mapping-json" in three_strategy_command
    assert three_strategy_command[
        three_strategy_command.index("--brf2-required-facts-mapping-json") + 1
    ] == str(tmp_path / "brf2-required-facts.json")
    assert "--brf2-runtime-signal-capture-json" in three_strategy_command
    assert three_strategy_command[
        three_strategy_command.index("--brf2-runtime-signal-capture-json") + 1
    ] == str(tmp_path / "brf2-signal-capture.json")
    assert "--trial-grade-signal-gate-audit-json" in three_strategy_command
    assert three_strategy_command[
        three_strategy_command.index("--trial-grade-signal-gate-audit-json") + 1
    ] == str(tmp_path / "trial-grade-audit.json")
    assert "--signal-coverage-json" in three_strategy_command
    assert three_strategy_command[
        three_strategy_command.index("--signal-coverage-json") + 1
    ] == str(tmp_path / "signal-coverage.json")
    tradeability_command = tradeability_commands[0]
    assert "--capital-trial-envelope-projection-json" in tradeability_command
    assert tradeability_command[
        tradeability_command.index("--capital-trial-envelope-projection-json") + 1
    ] == str(tmp_path / "capital-trial-envelope-projection.json")
    assert "--signal-coverage-json" in tradeability_command
    assert tradeability_command[
        tradeability_command.index("--signal-coverage-json") + 1
    ] == str(tmp_path / "signal-coverage.json")
    assert "--trial-asset-admission-proposal-json" in tradeability_command
    assert tradeability_command[
        tradeability_command.index("--trial-asset-admission-proposal-json") + 1
    ] == str(tmp_path / "trial-admission-proposal.json")
    assert "--brf2-owner-trial-policy-scope-json" in tradeability_command
    assert tradeability_command[
        tradeability_command.index("--brf2-owner-trial-policy-scope-json") + 1
    ] == str(tmp_path / "brf2-policy.json")
    assert "--three-strategy-live-trial-portfolio-json" in tradeability_command
    assert tradeability_command[
        tradeability_command.index("--three-strategy-live-trial-portfolio-json") + 1
    ] == str(tmp_path / "three-strategy-portfolio.json")
    assert "--trial-grade-signal-gate-audit-json" in tradeability_command
    assert tradeability_command[
        tradeability_command.index("--trial-grade-signal-gate-audit-json") + 1
    ] == str(tmp_path / "trial-grade-audit.json")
    assert "--runtime-safety-state-json" in tradeability_command
    assert tradeability_command[
        tradeability_command.index("--runtime-safety-state-json") + 1
    ] == str(tmp_path / "runtime-safety-state.json")
    assert "--brf2-runtime-signal-capture-json" in tradeability_command
    assert tradeability_command[
        tradeability_command.index("--brf2-runtime-signal-capture-json") + 1
    ] == str(tmp_path / "brf2-signal-capture.json")
    assert "--brf2-shadow-candidate-evidence-json" in tradeability_command
    assert tradeability_command[
        tradeability_command.index("--brf2-shadow-candidate-evidence-json") + 1
    ] == str(tmp_path / "brf2-shadow-evidence.json")
    assert len(action_time_boundary_commands) == 1
    action_time_boundary_command = action_time_boundary_commands[0]
    assert action_time_boundary_command[
        action_time_boundary_command.index("--output-json") + 1
    ] == str(tmp_path / "fresh-signal-action-time-boundary.json")
    assert action_time_boundary_command[
        action_time_boundary_command.index("--output-owner-progress") + 1
    ] == str(tmp_path / "fresh-signal-action-time-boundary.md")
    assert len(replay_live_parity_commands) == 1
    replay_live_parity_command = replay_live_parity_commands[0]
    assert replay_live_parity_command[
        replay_live_parity_command.index("--output-json") + 1
    ] == str(tmp_path / "replay-live-parity.json")
    assert replay_live_parity_command[
        replay_live_parity_command.index("--output-owner-progress") + 1
    ] == str(tmp_path / "replay-live-parity.md")
    assert "--sor-detector-json" in replay_live_parity_command
    assert replay_live_parity_command[
        replay_live_parity_command.index("--sor-detector-json") + 1
    ] == str(tmp_path / "latest-sor-session-detector-facts.json")
    assert len(mi_trial_admission_commands) == 1
    mi_trial_admission_command = mi_trial_admission_commands[0]
    assert mi_trial_admission_command[
        mi_trial_admission_command.index("--output-json") + 1
    ] == str(tmp_path / "mi-trial-admission.json")
    assert mi_trial_admission_command[
        mi_trial_admission_command.index("--output-owner-progress") + 1
    ] == str(tmp_path / "mi-trial-admission.md")
    assert "--replay-live-parity-audit-json" in tradeability_command
    assert tradeability_command[
        tradeability_command.index("--replay-live-parity-audit-json") + 1
    ] == str(tmp_path / "replay-live-parity.json")
    assert "--mi-trial-admission-decision-json" in tradeability_command
    assert tradeability_command[
        tradeability_command.index("--mi-trial-admission-decision-json") + 1
    ] == str(tmp_path / "mi-trial-admission.json")
    assert "--strategy-fresh-signal-action-time-boundary-json" in (
        tradeability_command
    )
    assert tradeability_command[
        tradeability_command.index(
            "--strategy-fresh-signal-action-time-boundary-json"
        )
        + 1
    ] == str(tmp_path / "fresh-signal-action-time-boundary.json")
    assert len(daily_table_commands) == 2
    bootstrap_daily_table_command = daily_table_commands[0]
    server_backed_daily_table_command = daily_table_commands[1]
    assert "--candidate-pool-json" not in bootstrap_daily_table_command
    assert server_backed_daily_table_command[
        server_backed_daily_table_command.index("--candidate-pool-json") + 1
    ] == str(tmp_path / "latest-strategy-live-candidate-pool.json")
    assert bootstrap_daily_table_command[
        bootstrap_daily_table_command.index("--tradeability-json") + 1
    ] == str(tmp_path / "tradeability.json")
    assert bootstrap_daily_table_command[
        bootstrap_daily_table_command.index("--replay-live-parity-json") + 1
    ] == str(tmp_path / "replay-live-parity.json")
    assert bootstrap_daily_table_command[
        bootstrap_daily_table_command.index("--action-time-boundary-json") + 1
    ] == str(tmp_path / "fresh-signal-action-time-boundary.json")
    assert bootstrap_daily_table_command[
        bootstrap_daily_table_command.index("--mi-trial-admission-json") + 1
    ] == str(tmp_path / "mi-trial-admission.json")
    assert bootstrap_daily_table_command[
        bootstrap_daily_table_command.index("--runtime-safety-json") + 1
    ] == str(tmp_path / "runtime-safety-state.json")
    assert bootstrap_daily_table_command[
        bootstrap_daily_table_command.index("--output-json") + 1
    ] == str(tmp_path / "daily-live-table.json")
    assert server_backed_daily_table_command[
        server_backed_daily_table_command.index("--output-json") + 1
    ] == str(tmp_path / "daily-live-table.json")
    assert bootstrap_daily_table_command[
        bootstrap_daily_table_command.index("--output-owner-progress") + 1
    ] == str(tmp_path / "daily-live-table.md")
    assert len(daily_table_validator_commands) == 2
    assert daily_table_validator_commands[-1][-1] == str(tmp_path / "daily-live-table.json")
    runtime_safety_state_command = runtime_safety_state_commands[0]
    assert "--brf2-shadow-candidate-evidence-json" in runtime_safety_state_command
    assert runtime_safety_state_command[
        runtime_safety_state_command.index(
            "--brf2-shadow-candidate-evidence-json"
        )
        + 1
    ] == str(tmp_path / "brf2-shadow-evidence.json")
    assert report["status"] == "needs_non_market_repair"
    assert _monitor_issues(report)["blockers"] == []
    assert "current_action" not in report["owner_summary"]
    assert report["owner_summary"]["non_authority_checkpoint"] == (
        "修复本地监控或非市场证据缺口"
    )
    assert report["owner_summary"]["checkpoint_source"] == (
        "local_monitor_status_projection"
    )
    assert report["interaction"]["level"] == "L0_local_monitor_sequence"
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False
    replay_parity = report["replay_live_parity_audit"]
    assert replay_parity["status"] == "replay_live_parity_audit_ready"
    assert replay_parity["cpm_first_blocker_class"] == "computed_not_satisfied"
    assert replay_parity["cpm_first_failed_facts"] == [
        "htf_trend_intact",
        "reclaim_confirmed",
    ]
    assert replay_parity["cpm_first_next_action"] == (
        "continue_observation_with_failed_fact_matrix"
    )
    assert replay_parity["cpm_per_symbol_blocker_matrix"] == [
        {
            "strategy_group_id": "CPM-RO-001",
            "symbol": "ETHUSDT",
            "detector_attached": True,
            "watcher_tick_present": True,
            "computed": True,
            "failed_facts": ["htf_trend_intact", "reclaim_confirmed"],
            "blocker_class": "computed_not_satisfied",
            "next_action": "continue_observation_with_failed_fact_matrix",
            "mismatch_count": 4,
        }
    ]
    assert report["owner_summary"]["replay_live_parity_audit"][
        "cpm_first_blocker_class"
    ] == "computed_not_satisfied"
    assert report["strategy_research_intake"]["active"] is True
    assert report["strategy_research_intake"]["strategy_group_ids"] == [
        "BRF2-001",
        "RBR2-001",
    ]
    assert "actionable_now" not in report["strategy_research_intake"]
    assert "actionable_now" not in report["owner_summary"]["strategy_research_intake"]
    for removed_check in (
        "research_intake_review_active",
        "research_intake_candidates",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert "strategy_candidate_trade" not in report
    assert "strategy_candidate_trade" not in report["owner_summary"]
    assert report["strategy_experiment_candidate"]["selected_strategy_group_id"] == (
        "BRF2-001"
    )
    assert report["strategy_experiment_candidate"]["selected_short_strategy_group_id"] == (
        "BRF2-001"
    )
    assert report["strategy_experiment_candidate"]["strategy_asset_current_decision"] == "promote"
    assert "decision" not in report["strategy_experiment_candidate"]
    assert report["strategy_experiment_candidate"]["promotion_scope"] == "intake_only"
    assert "tiny_live_ready" not in report["strategy_experiment_candidate"]
    assert report["strategy_experiment_candidate"]["projection_role"] == (
        "trial_envelope_compatibility_projection"
    )
    assert report["strategy_experiment_candidate"]["primary_judgment_source"] is False
    assert "legacy_bridge_provenance" not in report["strategy_experiment_candidate"]
    assert report["strategy_experiment_candidate"][
        "short_experiment_candidate_count"
    ] == 1
    assert "short_candidate_trade_count" not in report["strategy_experiment_candidate"]
    assert "strategy_observation_layer" not in report
    assert report["signal_observation_grade"]["grade_code"] == (
        "signal-observation-grade-review"
    )
    assert "grade" not in report["signal_observation_grade"]
    assert report["signal_observation_grade"]["state"] == "observation_active"
    assert report["signal_observation_grade"]["main_chain_state"] == (
        "waiting_for_executable_fresh_signal"
    )
    assert report["signal_observation_grade"]["broader_would_enter_count"] == 1
    assert report["signal_observation_grade"]["high_priority_no_action_count"] == 4
    assert report["signal_observation_grade"]["latest_observe_only_would_enter"][
        "strategy_group_id"
    ] == "RBR-001"
    assert report["signal_observation_grade"]["latest_observe_only_would_enter"][
        "symbol"
    ] == "ADA/USDT:USDT"
    assert report["signal_observation_grade"]["selected_short_intake_candidate"] == (
        "BRF2-001"
    )
    assert "selected_short_intake_candidate_tiny_live_ready" not in (
        report["signal_observation_grade"]
    )
    for removed_projection_field in ("actionable_now", "real_order_authority"):
        assert removed_projection_field not in report["signal_observation_grade"]
        assert (
            removed_projection_field
            not in report["owner_summary"]["signal_observation_grade"]
        )
    assert report["signal_observation_grade"]["no_action_attribution_count"] == 4
    assert report["signal_observation_grade"]["role_review_count"] == 1
    assert "candidate_trade_selected_strategy_group_id" not in _legacy_monitor_checks(report)
    assert "candidate_trade_selected_short_strategy_group_id" not in _legacy_monitor_checks(report)
    assert "candidate_trade_actionable_now" not in _legacy_monitor_checks(report)
    assert "candidate_trade_real_order_authority" not in _legacy_monitor_checks(report)
    assert report["strategy_experiment_candidate"]["selected_strategy_group_id"] == (
        "BRF2-001"
    )
    assert (
        report["strategy_experiment_candidate"]["selected_short_strategy_group_id"]
        == "BRF2-001"
    )
    assert "actionable_now" not in report["strategy_experiment_candidate"]
    for removed_check in (
        "signal_observation_grade_state",
        "signal_observation_grade_would_enter_count",
        "signal_observation_grade_high_priority_no_action_count",
        "signal_observation_grade_latest_strategy_group_id",
        "signal_observation_grade_no_action_attribution_count",
        "signal_observation_grade_role_review_count",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert report["strategy_experiment_candidate"]["promotion_scope"] == (
        "intake_only"
    )
    assert "tiny_live_ready" not in report["strategy_experiment_candidate"]
    assert "real_order_authority" not in report["strategy_experiment_candidate"]
    for removed_check in (
        "short_experiment_candidate_selected_strategy_group_id",
        "short_experiment_candidate_selected_short_strategy_group_id",
        "short_experiment_candidate_actionable_now",
        "short_experiment_candidate_real_order_authority",
        "short_experiment_candidate_promotion_scope",
        "short_experiment_candidate_tiny_live_ready",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert "strategy_tradeability_decision" not in report
    assert report["tradeability_decision"]["top_strategy_group_id"] == (
        "BRF2-001"
    )
    assert report["strategy_trial_asset_admission"]["status"] == (
        "trial_asset_admission_proposal_ready"
    )
    assert report["strategy_trial_asset_admission"]["strategy_group_id"] == (
        "BRF2-001"
    )
    assert report["strategy_trial_asset_admission"]["owner_policy_required"] is False
    for removed_projection_field in ("actionable_now", "real_order_authority"):
        assert removed_projection_field not in report["strategy_trial_asset_admission"]
        assert (
            removed_projection_field
            not in report["owner_summary"]["trial_asset_admission"]
        )
    for removed_check in (
        "trial_asset_admission_proposal_status",
        "trial_asset_admission_strategy_group_id",
        "trial_asset_admission_owner_policy_required",
        "trial_asset_admission_next_action",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert report["brf2_owner_trial_policy"]["owner_policy_recorded"] is True
    assert report["brf2_owner_trial_policy"]["owner_policy_scope_missing"] is False
    assert report["brf2_owner_trial_policy"]["brf2_stage_after_policy"] == (
        "admitted_trial_asset"
    )
    assert report["brf2_owner_trial_policy"]["brf2_new_first_blocker"] == (
        "required_facts_mapping_gap"
    )
    for removed_projection_field in ("actionable_now", "real_order_authority"):
        assert removed_projection_field not in report["brf2_owner_trial_policy"]
        assert (
            removed_projection_field
            not in report["owner_summary"]["brf2_owner_trial_policy"]
        )
    assert report["brf2_required_facts_mapping"]["ready"] is True
    assert report["brf2_required_facts_mapping"]["fresh_signal_rule_id"] == (
        "brf2_short_rally_failure_fresh_signal_v1"
    )
    assert report["brf2_required_facts_mapping"]["after_next_state"] == (
        "armed_observation"
    )
    for removed_projection_field in ("actionable_now", "real_order_authority"):
        assert removed_projection_field not in report["brf2_required_facts_mapping"]
    for removed_check in (
        "brf2_owner_policy_recorded",
        "brf2_owner_policy_scope_missing",
        "brf2_stage_after_policy",
        "brf2_new_first_blocker",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    for removed_check in (
        "brf2_required_facts_mapping_ready",
        "brf2_after_required_facts_mapping_state",
        "brf2_fresh_signal_rule_id",
        "brf2_required_fact_count",
        "brf2_disable_fact_count",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert report["brf2_runtime_signal_facts"]["status"] == (
        "brf2_runtime_signal_facts_missing_watcher_input"
    )
    assert report["brf2_runtime_signal_facts"]["fact_input_present"] is False
    assert report["brf2_runtime_signal_facts"]["watcher_tick_present"] is False
    assert report["brf2_runtime_signal_facts"]["primary_judgment_source"] is False
    assert report["brf2_runtime_signal_facts"]["tradeability_decision_source"] is False
    assert report["brf2_runtime_signal_facts"]["runtime_truth_source"] is False
    assert report["brf2_runtime_signal_capture"]["ready"] is True
    assert report["brf2_runtime_signal_capture"]["current_signal_state"] == (
        "fact_input_missing"
    )
    assert report["brf2_runtime_signal_capture"]["first_blocker_class"] == (
        "brf2_watcher_fact_input_missing"
    )
    assert (
        report["brf2_runtime_signal_capture"]["shadow_candidate_shape_ready"]
        is False
    )
    assert report["brf2_runtime_signal_capture"]["primary_judgment_source"] is False
    assert (
        report["brf2_runtime_signal_capture"]["tradeability_decision_source"]
        is False
    )
    assert report["brf2_runtime_signal_capture"]["runtime_truth_source"] is False
    assert report["owner_summary"]["brf2_runtime_signal_capture"] == (
        report["brf2_runtime_signal_capture"]
    )
    for removed_check in (
        "brf2_runtime_signal_capture_ready",
        "brf2_runtime_signal_fact_input_present",
        "brf2_runtime_signal_watcher_tick_present",
        "brf2_runtime_signal_fact_input_status",
        "brf2_runtime_signal_state",
        "brf2_runtime_signal_first_blocker_class",
        "brf2_runtime_signal_missing_fact_count",
        "brf2_runtime_signal_active_disable_fact_count",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert report["brf2_shadow_candidate_evidence"]["status"] == (
        "brf2_shadow_candidate_evidence_waiting_for_fresh_signal"
    )
    assert "candidate_packet_ready" not in report["brf2_shadow_candidate_evidence"]
    assert report["brf2_shadow_candidate_evidence"][
        "shadow_candidate_evidence_ready"
    ] is False
    assert "candidate_packet_id" not in report["brf2_shadow_candidate_evidence"]
    assert report["brf2_shadow_candidate_evidence"]["projection_role"] == (
        "shadow_candidate_evidence_provenance"
    )
    assert report["brf2_shadow_candidate_evidence"][
        "primary_judgment_source"
    ] is False
    assert report["brf2_shadow_candidate_evidence"][
        "non_executing_evidence"
    ] is True
    assert report["owner_summary"]["brf2_shadow_candidate_evidence"] == (
        report["brf2_shadow_candidate_evidence"]
    )
    for removed_projection_field in (
        "live_submit_authority",
        "operation_layer_authority",
        "actionable_now",
        "real_order_authority",
    ):
        assert removed_projection_field not in report["brf2_shadow_candidate_evidence"]
    for removed_check in (
        "brf2_shadow_candidate_evidence_status",
        "brf2_shadow_candidate_evidence_ready",
        "brf2_shadow_candidate_evidence_first_blocker_class",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert (
        report["three_strategy_live_trial_portfolio"]["next_bottlenecks"][
            "BRF2-001"
        ]
        == "fresh_signal_wait"
    )
    for removed_check in (
        "brf2_next_bottleneck",
        "brf2_actionable_now",
        "brf2_real_order_authority",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert report["three_strategy_live_trial_portfolio"]["ready"] is True
    assert report["three_strategy_live_trial_portfolio"]["seat_count"] == 3
    assert report["three_strategy_live_trial_portfolio"]["projection_role"] == (
        "trial_envelope_projection"
    )
    assert report["three_strategy_live_trial_portfolio"]["state_source"] == (
        "three_strategy_live_trial_portfolio"
    )
    assert report["three_strategy_live_trial_portfolio"][
        "primary_judgment_source"
    ] is False
    assert report["three_strategy_live_trial_portfolio"][
        "tradeability_decision_source"
    ] is False
    assert report["three_strategy_live_trial_portfolio"][
        "runtime_truth_source"
    ] is False
    assert "actionable_now" not in report["three_strategy_live_trial_portfolio"]
    assert "real_order_authority" not in report["three_strategy_live_trial_portfolio"]
    assert report["three_strategy_live_trial_portfolio"][
        "selected_strategy_groups"
    ] == ["MPG-001", "BRF2-001", "SOR-001"]
    assert report["three_strategy_live_trial_portfolio"]["market_wait_count"] == 3
    assert report["three_strategy_live_trial_portfolio"]["owner_policy_gap_count"] == 0
    assert report["three_strategy_live_trial_portfolio"]["engineering_gap_count"] == 0
    assert report["three_strategy_live_trial_portfolio"]["stage_5_status"] == (
        "waiting_for_trial_grade_live_opportunity"
    )
    assert report["three_strategy_live_trial_portfolio"][
        "controlled_live_standby_count"
    ] == 3
    assert (
        "stage_5_waiting_live_opportunity_ready"
        not in report["three_strategy_live_trial_portfolio"]
    )
    assert (
        "action_time_preflight_pending_fresh_signal"
        not in report["three_strategy_live_trial_portfolio"]
    )
    assert report["three_strategy_live_trial_portfolio"]["readiness_stage_evidence"][
        "fresh_signal_state"
    ] == "none"
    assert report["three_strategy_live_trial_portfolio"]["readiness_stage_evidence"][
        "can_create_execution_attempt"
    ] is False
    assert (
        "actionable_now"
        not in report["three_strategy_live_trial_portfolio"]["readiness_stage_evidence"]
    )
    assert (
        "real_order_authority"
        not in report["three_strategy_live_trial_portfolio"]["readiness_stage_evidence"]
    )
    assert report["three_strategy_live_trial_portfolio"][
        "hard_safety_gates_relaxed"
    ] is False
    for removed_check in (
        "three_strategy_live_trial_portfolio_ready",
        "live_trial_seat_count",
        "live_trial_strategy_groups",
        "live_trial_market_wait_count",
        "live_trial_owner_policy_gap_count",
        "live_trial_engineering_gap_count",
        "live_trial_next_bottlenecks",
        "stage_5_status",
        "stage_5_waiting_live_opportunity_ready",
        "controlled_live_standby_count",
        "action_time_preflight_pending_fresh_signal",
        "stage_5_hard_safety_gates_relaxed",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert report["strategy_trial_grade_signal_gate_audit"]["ready"] is True
    assert report["strategy_trial_grade_signal_gate_audit"][
        "strategy_group_count"
    ] == 3
    assert report["strategy_trial_grade_signal_gate_audit"][
        "trial_grade_observation_count_30d"
    ] == 1
    assert report["strategy_trial_grade_signal_gate_audit"][
        "action_time_submit_count_30d"
    ] == 0
    assert report["strategy_trial_grade_signal_gate_audit"][
        "hard_safety_gates_relaxed"
    ] is False
    for removed_projection_field in ("actionable_now", "real_order_authority"):
        assert (
            removed_projection_field
            not in report["strategy_trial_grade_signal_gate_audit"]
        )
        assert (
            removed_projection_field
            not in report["owner_summary"]["trial_grade_signal_gate_audit"]
        )
    for removed_check in (
        "trial_grade_signal_gate_audit_ready",
        "trial_grade_strategy_group_count",
        "trial_grade_observation_count_30d",
        "trial_grade_action_time_submit_count_30d",
        "trial_grade_hard_safety_gates_relaxed",
        "trial_grade_brf2_would_enter_controlled_live_trial_if_same_structure",
        "trial_grade_mpg_would_enter_controlled_live_trial_if_same_structure",
        "trial_grade_sor_would_enter_controlled_live_trial_if_same_structure",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert report["tradeability_decision"]["top_decision"] == (
        "not_tradable_facts"
    )
    assert report["tradeability_decision"]["top_first_blocker_class"] == (
        "brf2_watcher_fact_input_missing"
    )
    assert report["tradeability_decision"]["top_tradeability_checkpoint"] == (
        "attach_brf2_watcher_fact_input_producer"
    )
    for removed_check in (
        "tradeability_top_strategy_group_id",
        "tradeability_top_verdict",
        "tradeability_top_decision",
        "tradeability_top_first_blocker_class",
        "tradeability_top_tradeability_checkpoint",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert report["tradeability_decision"]["row_count"] == 3
    assert report["tradeability_decision"]["decision_rows_count"] == 3
    assert report["tradeability_decision"][
        "row_count_matches_decision_rows"
    ] is True
    assert report["tradeability_decision"]["projection_role"] == (
        "tradeability_decision_projection"
    )
    assert report["tradeability_decision"]["decision_result_counts"][
        "runtime_trade_allowed_rows"
    ] == 0
    assert "decision_value_counts" not in report["tradeability_decision"]
    assert "authority_true_row_counts" not in report["tradeability_decision"]
    assert "runtime_authority_row_counts" not in report["tradeability_decision"]
    assert "tradable_now_count" not in report["tradeability_decision"]
    assert "actionable_now_count" not in report["tradeability_decision"]
    assert "real_order_authority_count" not in report["tradeability_decision"]
    for removed_check in (
        "tradeability_row_count",
        "tradeability_decision_rows_count",
        "tradeability_decision_rows_count",
        "tradeability_row_count_matches_decision_rows",
        "tradeability_tradable_now_count",
        "tradeability_real_order_authority_count",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert _monitor_issues(report)["non_market_gaps"] == [_expected_brf2_fact_input_gap()]


def test_local_monitor_sequence_artifact_daily_check_uses_report_json_path(
    tmp_path: Path,
) -> None:
    module = _load_module()

    command = module._daily_check_command(
        mode="artifact",
        output_json=tmp_path / "daily.json",
        output_owner_progress=tmp_path / "daily.md",
    )

    assert "--report-json-path" in command
    assert command[command.index("--report-json-path") + 1] == str(
        tmp_path / "daily.json"
    )
    assert "--from-cache" not in command
    assert "--auto-cache" not in command


def test_local_monitor_sequence_auto_cache_uses_local_snapshot_inside_tokyo_release(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    monkeypatch.setattr(
        module,
        "REPO_ROOT",
        Path("/home/ubuntu/brc-deploy/releases/brc-runtime-governance-test"),
    )

    command = module._daily_check_command(
        mode="auto-cache",
        output_json=tmp_path / "daily.json",
        output_owner_progress=tmp_path / "daily.md",
    )

    assert "--auto-cache" in command
    assert command[command.index("--snapshot-host") + 1] == "local"


def test_local_monitor_sequence_surfaces_completion_non_market_gap(
    tmp_path: Path,
) -> None:
    module = _load_module()

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        script = Path(command[1]).name
        closure_result = _maybe_write_strategygroup_closure_step(script, command)
        if closure_result is not None:
            return closure_result
        if script == "build_strategygroup_post_revision_replay_review.py":
            _write_passed_post_revision_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_opportunity_review_work_loop.py":
            _write_ready_opportunity_review_work_loop(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_l2_shadow_fact_quality_review.py":
            _write_ready_btpc_fact_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_local_fact_proxy_review.py":
            _write_ready_btpc_local_fact_proxy_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_proxy_replay_quality_review.py":
            _write_ready_btpc_proxy_replay_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_l2_keep_revise_fact_source_review.py"
        ):
            _write_ready_btpc_l2_keep_revise_fact_source_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ):
            _write_ready_btpc_live_derivatives_fact_source_mapping(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_classifier_rule_review.py":
            _write_ready_btpc_classifier_rule_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_strategy_asset_state.py":
            _write_ready_strategy_asset_state(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_daily_check.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "runtime_live_cutover_readiness.py":
            _write_output(
                command,
                {"status": "live_cutover_waiting_for_fresh_signal", "interaction": {}},
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_goal_progress_audit.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "runtime_first_bounded_live_order_completion_audit.py":
            _write_output(
                command,
                {
                    "status": "needs_non_market_repair",
                    "non_market_gaps": [
                        {
                            "requirement": "P0 completion audit input sources are traceable",
                            "missing_or_false": ["goal_progress:generated_before_daily_check"],
                        }
                    ],
                    "interaction": {
                        "level": "L0_local_completion_audit",
                        "remote_interaction_count": 0,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 2, "", "")

        if script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "interaction": {
                        "level": "L0_local_replay_lab",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_signal_coverage_diagnostic.py":
            _write_output(
                command,
                {
                    "status": "mainline_and_broader_no_signal",
                    "interaction": {"level": "L0_local_signal_coverage"},
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_signal_coverage_expansion_review.py":
            _write_output(
                command,
                {
                    "status": "no_expansion_review_needed",
                    "interaction": {
                        "level": "L0_local_signal_coverage_expansion_review"
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_l2_readiness_review.py":
            _write_output(
                command,
                {
                    "status": "l2_readiness_review_no_rows",
                    "interaction": {
                        "level": "L0_local_l2_readiness_review"
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_l2_intake_dry_run.py":
            _write_output(
                command,
                {
                    "status": "l2_intake_dry_run_no_candidates",
                    "interaction": {
                        "level": "L0_local_l2_intake_dry_run"
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_brf2_shadow_candidate_evidence.py":
            _write_waiting_brf2_shadow_candidate_evidence(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        if _write_ready_cpm_artifact(command, script):
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_trial_grade_signal_gate_audit.py":
            _write_ready_trial_grade_signal_gate_audit(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        assert script == "run_strategygroup_l2_tier_policy_review.py"
        _write_output(
            command,
            {
                "status": "l2_tier_policy_review_no_candidates",
                "interaction": {
                    "level": "L0_local_l2_tier_policy_review"
                },
            },
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    report = module.build_local_monitor_sequence_report(
        daily_check_json=tmp_path / "daily.json",
        daily_owner_progress=tmp_path / "daily.md",
        live_cutover_json=tmp_path / "cutover.json",
        live_cutover_md=tmp_path / "cutover.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        dry_run_audit_json=tmp_path / "dry-run-audit-chain.json",
        dry_run_audit_dir=tmp_path / "dry-run-audit-chain",
        replay_lab_json=tmp_path / "replay.json",
        replay_lab_md=tmp_path / "replay.md",
        signal_coverage_json=tmp_path / "signal-coverage.json",
        signal_coverage_md=tmp_path / "signal-coverage.md",
        signal_coverage_expansion_review_json=tmp_path / "signal-expansion.json",
        signal_coverage_expansion_review_md=tmp_path / "signal-expansion.md",
        l2_readiness_review_json=tmp_path / "l2-review.json",
        l2_readiness_review_md=tmp_path / "l2-review.md",
        l2_intake_dry_run_json=tmp_path / "l2-dry-run.json",
        l2_intake_dry_run_md=tmp_path / "l2-dry-run.md",
        l2_tier_policy_review_json=tmp_path / "l2-tier-review.json",
        l2_tier_policy_review_md=tmp_path / "l2-tier-review.md",
        post_revision_replay_review_json=tmp_path / "post-revision-review.json",
        post_revision_replay_review_md=tmp_path / "post-revision-review.md",
        opportunity_review_work_loop_json=tmp_path / "opportunity-review-work-loop.json",
        opportunity_review_work_loop_md=tmp_path / "opportunity-review-work-loop.md",
        btpc_l2_shadow_fact_quality_review_json=tmp_path / "btpc-fact-review.json",
        btpc_l2_shadow_fact_quality_review_md=tmp_path / "btpc-fact-review.md",
        btpc_local_fact_proxy_review_json=tmp_path / "btpc-proxy-review.json",
        btpc_local_fact_proxy_review_md=tmp_path / "btpc-proxy-review.md",
        btpc_proxy_replay_quality_review_json=tmp_path / "btpc-proxy-replay.json",
        btpc_proxy_replay_quality_review_md=tmp_path / "btpc-proxy-replay.md",
        btpc_l2_keep_revise_fact_source_review_json=tmp_path
        / "btpc-l2-decision.json",
        btpc_l2_keep_revise_fact_source_review_md=tmp_path
        / "btpc-l2-decision.md",
        btpc_live_derivatives_fact_source_mapping_json=tmp_path
        / "btpc-live-source-mapping.json",
        btpc_live_derivatives_fact_source_mapping_md=tmp_path
        / "btpc-live-source-mapping.md",
        btpc_classifier_rule_review_json=tmp_path / "btpc-classifier-rule.json",
        btpc_classifier_rule_review_md=tmp_path / "btpc-classifier-rule.md",
        strategy_asset_state_json=tmp_path / "strategy-asset-state.json",
        strategy_asset_state_md=tmp_path / "strategy-asset-state.md",
        strategygroup_quality_wave_json=tmp_path / "quality-wave.json",
        strategygroup_quality_wave_md=tmp_path / "quality-wave.md",
        strategygroup_handoff_boundary_closure_json=tmp_path
        / "handoff-boundary.json",
        strategygroup_handoff_boundary_closure_md=tmp_path
        / "handoff-boundary.md",
        strategygroup_btpc_fact_classifier_guard_json=tmp_path
        / "btpc-guard.json",
        strategygroup_btpc_fact_classifier_guard_md=tmp_path
        / "btpc-guard.md",
        strategygroup_lifecycle_rehearsal_json=tmp_path / "lifecycle.json",
        strategygroup_lifecycle_rehearsal_md=tmp_path / "lifecycle.md",
        strategygroup_pre_live_rehearsal_readiness_json=tmp_path
        / "pre-live-readiness.json",
        strategygroup_pre_live_rehearsal_readiness_md=tmp_path
        / "pre-live-readiness.md",
        strategygroup_runtime_safety_state_json=tmp_path
        / "runtime-safety-state.json",
        strategygroup_runtime_safety_state_md=tmp_path
        / "runtime-safety-state.md",
        strategygroup_portfolio_board_json=tmp_path / "portfolio-board.json",
        strategygroup_portfolio_board_md=tmp_path / "portfolio-board.md",
        strategygroup_trial_candidate_pool_md=tmp_path / "trial-pool.md",
        strategygroup_capital_trial_envelope_projection_json=tmp_path
        / "capital-trial-envelope-projection.json",
        strategygroup_capital_trial_envelope_projection_md=tmp_path
        / "capital-trial-envelope-projection.md",
        strategygroup_capital_trial_envelope_json=tmp_path / "trial-envelope.json",
        strategygroup_capital_trial_envelope_md=tmp_path / "trial-envelope.md",
        strategygroup_research_intake_review_json=tmp_path
        / "research-intake-review.json",
        strategygroup_research_intake_review_md=tmp_path
        / "research-intake-review.md",
        strategygroup_trial_asset_admission_proposal_json=tmp_path
        / "trial-admission-proposal.json",
        strategygroup_trial_asset_admission_proposal_md=tmp_path
        / "trial-admission-proposal.md",
        brf2_owner_trial_policy_scope_json=tmp_path / "brf2-policy.json",
        brf2_owner_trial_policy_scope_md=tmp_path / "brf2-policy.md",
        brf2_required_facts_mapping_json=tmp_path / "brf2-required-facts.json",
        brf2_required_facts_mapping_md=tmp_path / "brf2-required-facts.md",
        brf2_runtime_signal_facts_json=tmp_path / "brf2-signal-facts.json",
        brf2_runtime_signal_facts_md=tmp_path / "brf2-signal-facts.md",
        brf2_runtime_signal_capture_json=tmp_path / "brf2-signal-capture.json",
        brf2_runtime_signal_capture_md=tmp_path / "brf2-signal-capture.md",
        brf2_shadow_candidate_evidence_json=(
            tmp_path / "brf2-shadow-evidence.json"
        ),
        brf2_shadow_candidate_evidence_md=tmp_path / "brf2-shadow-evidence.md",
        three_strategy_live_trial_portfolio_json=tmp_path
        / "three-strategy-portfolio.json",
        three_strategy_live_trial_portfolio_md=tmp_path
        / "three-strategy-portfolio.md",
        strategygroup_tradeability_decision_json=tmp_path / "tradeability.json",
        strategygroup_tradeability_decision_md=tmp_path / "tradeability.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert _monitor_issues(report)["blockers"] == []
    assert "execution_blockers" not in _legacy_monitor_checks(report)
    assert _monitor_issues(report)["non_market_gaps"][0]["missing_or_false"] == [
        "goal_progress:generated_before_daily_check"
    ]
    assert "engineering_gaps" not in _legacy_monitor_checks(report)
    assert report["owner_runtime_state"]["owner_intervention_required"] is False


def test_local_monitor_sequence_treats_stale_cache_as_refresh_not_blocker(
    tmp_path: Path,
) -> None:
    module = _load_module()

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        script = Path(command[1]).name
        closure_result = _maybe_write_strategygroup_closure_step(script, command)
        if closure_result is not None:
            return closure_result
        if script == "build_strategygroup_post_revision_replay_review.py":
            _write_passed_post_revision_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_opportunity_review_work_loop.py":
            _write_ready_opportunity_review_work_loop(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_l2_shadow_fact_quality_review.py":
            _write_ready_btpc_fact_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_local_fact_proxy_review.py":
            _write_ready_btpc_local_fact_proxy_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_proxy_replay_quality_review.py":
            _write_ready_btpc_proxy_replay_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_l2_keep_revise_fact_source_review.py"
        ):
            _write_ready_btpc_l2_keep_revise_fact_source_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ):
            _write_ready_btpc_live_derivatives_fact_source_mapping(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_classifier_rule_review.py":
            _write_ready_btpc_classifier_rule_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_strategy_asset_state.py":
            _write_ready_strategy_asset_state(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_daily_check.py":
            _write_output(
                command,
                {
                    "status": "waiting_for_market_monitor_refresh_needed",
                    "runtime_status": "waiting_for_market",
                    "monitor_status": "needs_refresh",
                    "owner_status": "waiting_for_opportunity",
                    "owner_runtime_state": {
                        "runtime_status": "waiting_for_market",
                        "monitor_status": "needs_refresh",
                        "owner_status": "waiting_for_opportunity",
                        "owner_intervention_required": False,
                        "monitor_refresh_needed": True,
                        "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
                        "waiting_for_market": True,
                    },
                    "checks": {
                        "blockers": [],
                        "waiting_for_market": True,
                    },
                    "interaction": {
                        "level": "L0_local_cache_gate",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 2, "", "")
        if script == "runtime_live_cutover_readiness.py":
            _write_output(
                command,
                {"status": "live_cutover_waiting_for_fresh_signal", "interaction": {}},
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_goal_progress_audit.py":
            _write_output(
                command,
                {
                    "status": "waiting_for_market_monitor_refresh_needed",
                    "runtime_status": "waiting_for_market",
                    "monitor_status": "needs_refresh",
                    "owner_status": "waiting_for_opportunity",
                    "owner_runtime_state": {
                        "runtime_status": "waiting_for_market",
                        "monitor_status": "needs_refresh",
                        "owner_status": "waiting_for_opportunity",
                        "owner_intervention_required": False,
                        "monitor_refresh_needed": True,
                        "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
                        "waiting_for_market": True,
                    },
                    "checks": {
                        "blockers": [],
                        "product_gaps": [],
                        "waiting_for_market": True,
                    },
                    "interaction": {
                        "level": "L0_local_goal_progress_audit",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 2, "", "")

        if script == "runtime_first_bounded_live_order_completion_audit.py":
            _write_output(
                command,
                {
                    "status": "not_complete_waiting_for_market",
                    "non_market_gaps": [],
                    "interaction": {
                        "level": "L0_local_completion_audit",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "interaction": {
                        "level": "L0_local_replay_lab",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "interaction": {
                        "level": "L0_local_replay_lab",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_signal_coverage_diagnostic.py":
            _write_output(
                command,
                {
                    "status": "mainline_and_broader_no_signal",
                    "interaction": {
                        "level": "L0_local_signal_coverage",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_signal_coverage_expansion_review.py":
            _write_output(
                command,
                {
                    "status": "no_expansion_review_needed",
                    "interaction": {
                        "level": "L0_local_signal_coverage_expansion_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_l2_readiness_review.py":
            _write_output(
                command,
                {
                    "status": "l2_readiness_review_no_rows",
                    "interaction": {
                        "level": "L0_local_l2_readiness_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_l2_intake_dry_run.py":
            _write_output(
                command,
                {
                    "status": "l2_intake_dry_run_no_candidates",
                    "interaction": {
                        "level": "L0_local_l2_intake_dry_run",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_brf2_shadow_candidate_evidence.py":
            _write_waiting_brf2_shadow_candidate_evidence(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        if _write_ready_cpm_artifact(command, script):
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_trial_grade_signal_gate_audit.py":
            _write_ready_trial_grade_signal_gate_audit(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        assert script == "run_strategygroup_l2_tier_policy_review.py"
        _write_output(
            command,
            {
                "status": "l2_tier_policy_review_no_candidates",
                "interaction": {
                    "level": "L0_local_l2_tier_policy_review",
                    "remote_interaction_count": 0,
                    "mutates_remote_files": False,
                    "approaches_real_order": False,
                },
            },
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    report = module.build_local_monitor_sequence_report(
        daily_check_json=tmp_path / "daily.json",
        daily_owner_progress=tmp_path / "daily.md",
        live_cutover_json=tmp_path / "cutover.json",
        live_cutover_md=tmp_path / "cutover.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        dry_run_audit_json=tmp_path / "dry-run-audit-chain.json",
        dry_run_audit_dir=tmp_path / "dry-run-audit-chain",
        replay_lab_json=tmp_path / "replay.json",
        replay_lab_md=tmp_path / "replay.md",
        signal_coverage_json=tmp_path / "signal-coverage.json",
        signal_coverage_md=tmp_path / "signal-coverage.md",
        signal_coverage_expansion_review_json=tmp_path / "signal-expansion.json",
        signal_coverage_expansion_review_md=tmp_path / "signal-expansion.md",
        l2_readiness_review_json=tmp_path / "l2-review.json",
        l2_readiness_review_md=tmp_path / "l2-review.md",
        l2_intake_dry_run_json=tmp_path / "l2-dry-run.json",
        l2_intake_dry_run_md=tmp_path / "l2-dry-run.md",
        l2_tier_policy_review_json=tmp_path / "l2-tier-review.json",
        l2_tier_policy_review_md=tmp_path / "l2-tier-review.md",
        post_revision_replay_review_json=tmp_path / "post-revision-review.json",
        post_revision_replay_review_md=tmp_path / "post-revision-review.md",
        opportunity_review_work_loop_json=tmp_path / "opportunity-review-work-loop.json",
        opportunity_review_work_loop_md=tmp_path / "opportunity-review-work-loop.md",
        btpc_l2_shadow_fact_quality_review_json=tmp_path / "btpc-fact-review.json",
        btpc_l2_shadow_fact_quality_review_md=tmp_path / "btpc-fact-review.md",
        btpc_local_fact_proxy_review_json=tmp_path / "btpc-proxy-review.json",
        btpc_local_fact_proxy_review_md=tmp_path / "btpc-proxy-review.md",
        btpc_proxy_replay_quality_review_json=tmp_path / "btpc-proxy-replay.json",
        btpc_proxy_replay_quality_review_md=tmp_path / "btpc-proxy-replay.md",
        btpc_l2_keep_revise_fact_source_review_json=tmp_path
        / "btpc-l2-decision.json",
        btpc_l2_keep_revise_fact_source_review_md=tmp_path
        / "btpc-l2-decision.md",
        btpc_live_derivatives_fact_source_mapping_json=tmp_path
        / "btpc-live-source-mapping.json",
        btpc_live_derivatives_fact_source_mapping_md=tmp_path
        / "btpc-live-source-mapping.md",
        btpc_classifier_rule_review_json=tmp_path / "btpc-classifier-rule.json",
        btpc_classifier_rule_review_md=tmp_path / "btpc-classifier-rule.md",
        strategy_asset_state_json=tmp_path / "strategy-asset-state.json",
        strategy_asset_state_md=tmp_path / "strategy-asset-state.md",
        strategygroup_quality_wave_json=tmp_path / "quality-wave.json",
        strategygroup_quality_wave_md=tmp_path / "quality-wave.md",
        strategygroup_handoff_boundary_closure_json=tmp_path
        / "handoff-boundary.json",
        strategygroup_handoff_boundary_closure_md=tmp_path
        / "handoff-boundary.md",
        strategygroup_btpc_fact_classifier_guard_json=tmp_path
        / "btpc-guard.json",
        strategygroup_btpc_fact_classifier_guard_md=tmp_path
        / "btpc-guard.md",
        strategygroup_lifecycle_rehearsal_json=tmp_path / "lifecycle.json",
        strategygroup_lifecycle_rehearsal_md=tmp_path / "lifecycle.md",
        strategygroup_pre_live_rehearsal_readiness_json=tmp_path
        / "pre-live-readiness.json",
        strategygroup_pre_live_rehearsal_readiness_md=tmp_path
        / "pre-live-readiness.md",
        strategygroup_runtime_safety_state_json=tmp_path
        / "runtime-safety-state.json",
        strategygroup_runtime_safety_state_md=tmp_path
        / "runtime-safety-state.md",
        strategygroup_portfolio_board_json=tmp_path / "portfolio-board.json",
        strategygroup_portfolio_board_md=tmp_path / "portfolio-board.md",
        strategygroup_trial_candidate_pool_md=tmp_path / "trial-pool.md",
        strategygroup_capital_trial_envelope_projection_json=tmp_path
        / "capital-trial-envelope-projection.json",
        strategygroup_capital_trial_envelope_projection_md=tmp_path
        / "capital-trial-envelope-projection.md",
        strategygroup_capital_trial_envelope_json=tmp_path / "trial-envelope.json",
        strategygroup_capital_trial_envelope_md=tmp_path / "trial-envelope.md",
        strategygroup_research_intake_review_json=tmp_path
        / "research-intake-review.json",
        strategygroup_research_intake_review_md=tmp_path
        / "research-intake-review.md",
        strategygroup_trial_asset_admission_proposal_json=tmp_path
        / "trial-admission-proposal.json",
        strategygroup_trial_asset_admission_proposal_md=tmp_path
        / "trial-admission-proposal.md",
        brf2_owner_trial_policy_scope_json=tmp_path / "brf2-policy.json",
        brf2_owner_trial_policy_scope_md=tmp_path / "brf2-policy.md",
        brf2_required_facts_mapping_json=tmp_path / "brf2-required-facts.json",
        brf2_required_facts_mapping_md=tmp_path / "brf2-required-facts.md",
        brf2_runtime_signal_facts_json=tmp_path / "brf2-signal-facts.json",
        brf2_runtime_signal_facts_md=tmp_path / "brf2-signal-facts.md",
        brf2_runtime_signal_capture_json=tmp_path / "brf2-signal-capture.json",
        brf2_runtime_signal_capture_md=tmp_path / "brf2-signal-capture.md",
        brf2_shadow_candidate_evidence_json=(
            tmp_path / "brf2-shadow-evidence.json"
        ),
        brf2_shadow_candidate_evidence_md=tmp_path / "brf2-shadow-evidence.md",
        three_strategy_live_trial_portfolio_json=tmp_path
        / "three-strategy-portfolio.json",
        three_strategy_live_trial_portfolio_md=tmp_path
        / "three-strategy-portfolio.md",
        strategygroup_tradeability_decision_json=tmp_path / "tradeability.json",
        strategygroup_tradeability_decision_md=tmp_path / "tradeability.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["runtime_status"] == "waiting_for_market"
    assert report["monitor_status"] == "needs_refresh"
    assert report["owner_status"] == "waiting_for_opportunity"
    assert report["owner_runtime_state"] == {
        "runtime_status": "waiting_for_market",
        "monitor_status": "needs_refresh",
        "owner_status": "waiting_for_opportunity",
        "owner_intervention_required": False,
        "monitor_refresh_needed": True,
        "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
        "waiting_for_market": True,
    }
    assert report["owner_summary"]["state"] == "需要修复"
    assert "current_action" not in report["owner_summary"]
    assert report["owner_summary"]["non_authority_checkpoint"] == (
        "修复本地监控或非市场证据缺口"
    )
    assert report["owner_summary"]["checkpoint_source"] == (
        "local_monitor_status_projection"
    )
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert _monitor_issues(report)["blockers"] == []
    assert report["owner_runtime_state"]["monitor_refresh_needed"] is True
    assert report["owner_runtime_state"]["monitor_refresh_reasons"] == [
        "runtime_progress_cache_stale"
    ]
    assert "monitor_refresh_gaps" not in _legacy_monitor_checks(report)
    assert report["notification"]["refresh_required"] is True
    assert report["notification"]["automation_notify"] is True
    assert report["notification"]["owner_notify"] is False
    assert report["notification"] == module.monitor_notification_projection(
        monitor_refresh_needed=True,
        owner_notify=False,
        owner_intervention_required=False,
        monitor_refresh_reasons=["runtime_progress_cache_stale"],
        include_monitor_refresh_fields=True,
    )
    for removed_check in (
        "refresh_required",
        "automation_notify",
        "owner_notify",
        "goal_complete",
        "runtime_status",
        "monitor_status",
        "owner_status",
        "monitor_refresh_needed",
        "monitor_refresh_reasons",
        "owner_intervention_required",
        "waiting_for_market",
    ):
        assert removed_check not in _legacy_monitor_checks(report)
    assert _monitor_issues(report)["non_market_gaps"] == [_expected_brf2_fact_input_gap()]
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False


def test_local_monitor_sequence_surfaces_signal_coverage_gap(
    tmp_path: Path,
) -> None:
    module = _load_module()

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        script = Path(command[1]).name
        closure_result = _maybe_write_strategygroup_closure_step(script, command)
        if closure_result is not None:
            return closure_result
        if script == "build_strategygroup_post_revision_replay_review.py":
            _write_passed_post_revision_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_opportunity_review_work_loop.py":
            _write_ready_opportunity_review_work_loop(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_l2_shadow_fact_quality_review.py":
            _write_ready_btpc_fact_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_local_fact_proxy_review.py":
            _write_ready_btpc_local_fact_proxy_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_proxy_replay_quality_review.py":
            _write_ready_btpc_proxy_replay_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_l2_keep_revise_fact_source_review.py"
        ):
            _write_ready_btpc_l2_keep_revise_fact_source_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ):
            _write_ready_btpc_live_derivatives_fact_source_mapping(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_classifier_rule_review.py":
            _write_ready_btpc_classifier_rule_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_strategy_asset_state.py":
            _write_ready_strategy_asset_state(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_daily_check.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "runtime_live_cutover_readiness.py":
            _write_output(
                command,
                {"status": "live_cutover_waiting_for_fresh_signal", "interaction": {}},
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_goal_progress_audit.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "runtime_first_bounded_live_order_completion_audit.py":
            _write_output(
                command,
                {
                    "status": "not_complete_waiting_for_market",
                    "non_market_gaps": [],
                    "interaction": {},
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "interaction": {
                        "level": "L0_local_replay_lab",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_signal_coverage_diagnostic.py":
            _write_output(
                command,
                {
                    "status": "mainline_no_signal_broader_would_enter",
                    "interaction": {
                        "level": "L0_local_signal_coverage",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_signal_coverage_expansion_review.py":
            _write_output(
                command,
                {
                    "status": "review_needed_broader_observe_only_would_enter",
                    "counts": {"review_row_count": 4},
                    "interaction": {
                        "level": "L0_local_signal_coverage_expansion_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_l2_readiness_review.py":
            _write_output(
                command,
                {
                    "status": "l2_readiness_review_has_conditional_candidate",
                    "review_outcome_state": {
                        "default_next_step": "run_conditional_l2_dry_run_without_tier_change",
                        "handoff_intake_recommended_groups": ["BTPC-001"],
                        "tradeability_decision_source": False,
                    },
                    "interaction": {
                        "level": "L0_local_l2_readiness_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_l2_intake_dry_run.py":
            _write_output(
                command,
                {
                    "status": "l2_intake_dry_run_passed",
                    "review_outcome_state": {
                        "groups_ready_for_l2_policy_review": ["BTPC-001"],
                        "tradeability_decision_source": False,
                    },
                    "interaction": {
                        "level": "L0_local_l2_intake_dry_run",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_brf2_shadow_candidate_evidence.py":
            _write_waiting_brf2_shadow_candidate_evidence(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        if _write_ready_cpm_artifact(command, script):
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_trial_grade_signal_gate_audit.py":
            _write_ready_trial_grade_signal_gate_audit(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        assert script == "run_strategygroup_l2_tier_policy_review.py"
        _write_output(
            command,
                {
                    "status": "l2_tier_policy_review_recommended",
                    "review_outcome_state": {
                        "groups_ready_to_apply_l2": ["BTPC-001"],
                        "tradeability_decision_source": False,
                    },
                    "interaction": {
                    "level": "L0_local_l2_tier_policy_review",
                    "remote_interaction_count": 0,
                    "mutates_remote_files": False,
                    "approaches_real_order": False,
                },
            },
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    report = module.build_local_monitor_sequence_report(
        daily_check_json=tmp_path / "daily.json",
        daily_owner_progress=tmp_path / "daily.md",
        live_cutover_json=tmp_path / "cutover.json",
        live_cutover_md=tmp_path / "cutover.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        dry_run_audit_json=tmp_path / "dry-run-audit-chain.json",
        dry_run_audit_dir=tmp_path / "dry-run-audit-chain",
        replay_lab_json=tmp_path / "replay.json",
        replay_lab_md=tmp_path / "replay.md",
        signal_coverage_json=tmp_path / "signal-coverage.json",
        signal_coverage_md=tmp_path / "signal-coverage.md",
        signal_coverage_expansion_review_json=tmp_path / "signal-expansion.json",
        signal_coverage_expansion_review_md=tmp_path / "signal-expansion.md",
        l2_readiness_review_json=tmp_path / "l2-review.json",
        l2_readiness_review_md=tmp_path / "l2-review.md",
        l2_intake_dry_run_json=tmp_path / "l2-dry-run.json",
        l2_intake_dry_run_md=tmp_path / "l2-dry-run.md",
        l2_tier_policy_review_json=tmp_path / "l2-tier-review.json",
        l2_tier_policy_review_md=tmp_path / "l2-tier-review.md",
        post_revision_replay_review_json=tmp_path / "post-revision-review.json",
        post_revision_replay_review_md=tmp_path / "post-revision-review.md",
        opportunity_review_work_loop_json=tmp_path / "opportunity-review-work-loop.json",
        opportunity_review_work_loop_md=tmp_path / "opportunity-review-work-loop.md",
        btpc_l2_shadow_fact_quality_review_json=tmp_path / "btpc-fact-review.json",
        btpc_l2_shadow_fact_quality_review_md=tmp_path / "btpc-fact-review.md",
        btpc_local_fact_proxy_review_json=tmp_path / "btpc-proxy-review.json",
        btpc_local_fact_proxy_review_md=tmp_path / "btpc-proxy-review.md",
        btpc_proxy_replay_quality_review_json=tmp_path / "btpc-proxy-replay.json",
        btpc_proxy_replay_quality_review_md=tmp_path / "btpc-proxy-replay.md",
        btpc_l2_keep_revise_fact_source_review_json=tmp_path
        / "btpc-l2-decision.json",
        btpc_l2_keep_revise_fact_source_review_md=tmp_path
        / "btpc-l2-decision.md",
        btpc_live_derivatives_fact_source_mapping_json=tmp_path
        / "btpc-live-source-mapping.json",
        btpc_live_derivatives_fact_source_mapping_md=tmp_path
        / "btpc-live-source-mapping.md",
        btpc_classifier_rule_review_json=tmp_path / "btpc-classifier-rule.json",
        btpc_classifier_rule_review_md=tmp_path / "btpc-classifier-rule.md",
        strategy_asset_state_json=tmp_path / "strategy-asset-state.json",
        strategy_asset_state_md=tmp_path / "strategy-asset-state.md",
        strategygroup_quality_wave_json=tmp_path / "quality-wave.json",
        strategygroup_quality_wave_md=tmp_path / "quality-wave.md",
        strategygroup_handoff_boundary_closure_json=tmp_path
        / "handoff-boundary.json",
        strategygroup_handoff_boundary_closure_md=tmp_path
        / "handoff-boundary.md",
        strategygroup_btpc_fact_classifier_guard_json=tmp_path
        / "btpc-guard.json",
        strategygroup_btpc_fact_classifier_guard_md=tmp_path
        / "btpc-guard.md",
        strategygroup_lifecycle_rehearsal_json=tmp_path / "lifecycle.json",
        strategygroup_lifecycle_rehearsal_md=tmp_path / "lifecycle.md",
        strategygroup_pre_live_rehearsal_readiness_json=tmp_path
        / "pre-live-readiness.json",
        strategygroup_pre_live_rehearsal_readiness_md=tmp_path
        / "pre-live-readiness.md",
        strategygroup_runtime_safety_state_json=tmp_path
        / "runtime-safety-state.json",
        strategygroup_runtime_safety_state_md=tmp_path
        / "runtime-safety-state.md",
        strategygroup_portfolio_board_json=tmp_path / "portfolio-board.json",
        strategygroup_portfolio_board_md=tmp_path / "portfolio-board.md",
        strategygroup_trial_candidate_pool_md=tmp_path / "trial-pool.md",
        strategygroup_capital_trial_envelope_projection_json=tmp_path
        / "capital-trial-envelope-projection.json",
        strategygroup_capital_trial_envelope_projection_md=tmp_path
        / "capital-trial-envelope-projection.md",
        strategygroup_capital_trial_envelope_json=tmp_path / "trial-envelope.json",
        strategygroup_capital_trial_envelope_md=tmp_path / "trial-envelope.md",
        strategygroup_research_intake_review_json=tmp_path
        / "research-intake-review.json",
        strategygroup_research_intake_review_md=tmp_path
        / "research-intake-review.md",
        strategygroup_trial_asset_admission_proposal_json=tmp_path
        / "trial-admission-proposal.json",
        strategygroup_trial_asset_admission_proposal_md=tmp_path
        / "trial-admission-proposal.md",
        brf2_owner_trial_policy_scope_json=tmp_path / "brf2-policy.json",
        brf2_owner_trial_policy_scope_md=tmp_path / "brf2-policy.md",
        brf2_required_facts_mapping_json=tmp_path / "brf2-required-facts.json",
        brf2_required_facts_mapping_md=tmp_path / "brf2-required-facts.md",
        brf2_runtime_signal_facts_json=tmp_path / "brf2-signal-facts.json",
        brf2_runtime_signal_facts_md=tmp_path / "brf2-signal-facts.md",
        brf2_runtime_signal_capture_json=tmp_path / "brf2-signal-capture.json",
        brf2_runtime_signal_capture_md=tmp_path / "brf2-signal-capture.md",
        brf2_shadow_candidate_evidence_json=(
            tmp_path / "brf2-shadow-evidence.json"
        ),
        brf2_shadow_candidate_evidence_md=tmp_path / "brf2-shadow-evidence.md",
        three_strategy_live_trial_portfolio_json=tmp_path
        / "three-strategy-portfolio.json",
        three_strategy_live_trial_portfolio_md=tmp_path
        / "three-strategy-portfolio.md",
        strategygroup_tradeability_decision_json=tmp_path / "tradeability.json",
        strategygroup_tradeability_decision_md=tmp_path / "tradeability.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_non_market_repair"
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert _monitor_issues(report)["blockers"] == []
    assert _monitor_issues(report)["non_market_gaps"] == [
        {
            "source": "l2_tier_policy_review",
            "requirement": "conditional L2 tier policy review recommends a local policy update before the broader opportunity is considered covered",
            "missing_or_false": [
                "conditional_l2_tier_policy_update_needed",
                "groups:BTPC-001",
            ],
        },
        _expected_brf2_fact_input_gap(),
    ]
    assert "engineering_gaps" not in _legacy_monitor_checks(report)
    assert report["owner_runtime_state"]["owner_intervention_required"] is False
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False


def test_local_monitor_sequence_clears_signal_gap_when_l2_already_enabled(
    tmp_path: Path,
) -> None:
    module = _load_module()

    def fake_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        script = Path(command[1]).name
        closure_result = _maybe_write_strategygroup_closure_step(script, command)
        if closure_result is not None:
            return closure_result
        if script == "build_strategygroup_post_revision_replay_review.py":
            _write_passed_post_revision_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_opportunity_review_work_loop.py":
            _write_ready_opportunity_review_work_loop(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_l2_shadow_fact_quality_review.py":
            _write_ready_btpc_fact_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_local_fact_proxy_review.py":
            _write_ready_btpc_local_fact_proxy_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_proxy_replay_quality_review.py":
            _write_ready_btpc_proxy_replay_quality_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_l2_keep_revise_fact_source_review.py"
        ):
            _write_ready_btpc_l2_keep_revise_fact_source_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if (
            script
            == "build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ):
            _write_ready_btpc_live_derivatives_fact_source_mapping(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_btpc_classifier_rule_review.py":
            _write_ready_btpc_classifier_rule_review(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_strategy_asset_state.py":
            _write_ready_strategy_asset_state(command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_daily_check.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "runtime_live_cutover_readiness.py":
            _write_output(
                command,
                {"status": "live_cutover_waiting_for_fresh_signal", "interaction": {}},
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_runtime_goal_progress_audit.py":
            _write_output(command, {"status": "waiting_for_market", "interaction": {}})
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "runtime_first_bounded_live_order_completion_audit.py":
            _write_output(
                command,
                {
                    "status": "not_complete_waiting_for_market",
                    "non_market_gaps": [],
                    "interaction": {},
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_runtime_replay_lab.py":
            _write_output(
                command,
                {
                    "status": "passed",
                    "interaction": {
                        "level": "L0_local_replay_lab",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "run_strategygroup_signal_coverage_diagnostic.py":
            _write_output(
                command,
                {
                    "status": "mainline_no_signal_broader_would_enter",
                    "interaction": {
                        "level": "L0_local_signal_coverage",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_signal_coverage_expansion_review.py":
            _write_output(
                command,
                {
                    "status": "review_needed_broader_observe_only_would_enter",
                    "interaction": {
                        "level": "L0_local_signal_coverage_expansion_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "build_strategygroup_l2_readiness_review.py":
            _write_output(
                command,
                {
                    "status": "l2_readiness_review_already_enabled",
                    "review_outcome_state": {
                        "enabled_l2_groups": ["BTPC-001"],
                        "tradeability_decision_source": False,
                    },
                    "interaction": {
                        "level": "L0_local_l2_readiness_review",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if script == "run_strategygroup_l2_intake_dry_run.py":
            _write_output(
                command,
                {
                    "status": "l2_intake_dry_run_no_candidates",
                    "interaction": {
                        "level": "L0_local_l2_intake_dry_run",
                        "remote_interaction_count": 0,
                        "mutates_remote_files": False,
                        "approaches_real_order": False,
                    },
                },
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_brf2_shadow_candidate_evidence.py":
            _write_waiting_brf2_shadow_candidate_evidence(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        if _write_ready_cpm_artifact(command, script):
            return subprocess.CompletedProcess(command, 0, "", "")

        if script == "build_strategygroup_trial_grade_signal_gate_audit.py":
            _write_ready_trial_grade_signal_gate_audit(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        assert script == "run_strategygroup_l2_tier_policy_review.py"
        _write_output(
            command,
            {
                "status": "l2_tier_policy_review_no_candidates",
                "interaction": {
                    "level": "L0_local_l2_tier_policy_review",
                    "remote_interaction_count": 0,
                    "mutates_remote_files": False,
                    "approaches_real_order": False,
                },
            },
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    report = module.build_local_monitor_sequence_report(
        daily_check_json=tmp_path / "daily.json",
        daily_owner_progress=tmp_path / "daily.md",
        live_cutover_json=tmp_path / "cutover.json",
        live_cutover_md=tmp_path / "cutover.md",
        goal_progress_json=tmp_path / "goal.json",
        goal_progress_md=tmp_path / "goal.md",
        completion_audit_json=tmp_path / "completion.json",
        completion_audit_md=tmp_path / "completion.md",
        dry_run_audit_json=tmp_path / "dry-run-audit-chain.json",
        dry_run_audit_dir=tmp_path / "dry-run-audit-chain",
        replay_lab_json=tmp_path / "replay.json",
        replay_lab_md=tmp_path / "replay.md",
        signal_coverage_json=tmp_path / "signal-coverage.json",
        signal_coverage_md=tmp_path / "signal-coverage.md",
        signal_coverage_expansion_review_json=tmp_path / "signal-expansion.json",
        signal_coverage_expansion_review_md=tmp_path / "signal-expansion.md",
        l2_readiness_review_json=tmp_path / "l2-review.json",
        l2_readiness_review_md=tmp_path / "l2-review.md",
        l2_intake_dry_run_json=tmp_path / "l2-dry-run.json",
        l2_intake_dry_run_md=tmp_path / "l2-dry-run.md",
        l2_tier_policy_review_json=tmp_path / "l2-tier-review.json",
        l2_tier_policy_review_md=tmp_path / "l2-tier-review.md",
        post_revision_replay_review_json=tmp_path / "post-revision-review.json",
        post_revision_replay_review_md=tmp_path / "post-revision-review.md",
        opportunity_review_work_loop_json=tmp_path / "opportunity-review-work-loop.json",
        opportunity_review_work_loop_md=tmp_path / "opportunity-review-work-loop.md",
        btpc_l2_shadow_fact_quality_review_json=tmp_path / "btpc-fact-review.json",
        btpc_l2_shadow_fact_quality_review_md=tmp_path / "btpc-fact-review.md",
        btpc_local_fact_proxy_review_json=tmp_path / "btpc-proxy-review.json",
        btpc_local_fact_proxy_review_md=tmp_path / "btpc-proxy-review.md",
        btpc_proxy_replay_quality_review_json=tmp_path / "btpc-proxy-replay.json",
        btpc_proxy_replay_quality_review_md=tmp_path / "btpc-proxy-replay.md",
        btpc_l2_keep_revise_fact_source_review_json=tmp_path
        / "btpc-l2-decision.json",
        btpc_l2_keep_revise_fact_source_review_md=tmp_path
        / "btpc-l2-decision.md",
        btpc_live_derivatives_fact_source_mapping_json=tmp_path
        / "btpc-live-source-mapping.json",
        btpc_live_derivatives_fact_source_mapping_md=tmp_path
        / "btpc-live-source-mapping.md",
        btpc_classifier_rule_review_json=tmp_path / "btpc-classifier-rule.json",
        btpc_classifier_rule_review_md=tmp_path / "btpc-classifier-rule.md",
        strategy_asset_state_json=tmp_path / "strategy-asset-state.json",
        strategy_asset_state_md=tmp_path / "strategy-asset-state.md",
        strategygroup_quality_wave_json=tmp_path / "quality-wave.json",
        strategygroup_quality_wave_md=tmp_path / "quality-wave.md",
        strategygroup_handoff_boundary_closure_json=tmp_path
        / "handoff-boundary.json",
        strategygroup_handoff_boundary_closure_md=tmp_path
        / "handoff-boundary.md",
        strategygroup_btpc_fact_classifier_guard_json=tmp_path
        / "btpc-guard.json",
        strategygroup_btpc_fact_classifier_guard_md=tmp_path
        / "btpc-guard.md",
        strategygroup_lifecycle_rehearsal_json=tmp_path / "lifecycle.json",
        strategygroup_lifecycle_rehearsal_md=tmp_path / "lifecycle.md",
        strategygroup_pre_live_rehearsal_readiness_json=tmp_path
        / "pre-live-readiness.json",
        strategygroup_pre_live_rehearsal_readiness_md=tmp_path
        / "pre-live-readiness.md",
        strategygroup_runtime_safety_state_json=tmp_path
        / "runtime-safety-state.json",
        strategygroup_runtime_safety_state_md=tmp_path
        / "runtime-safety-state.md",
        strategygroup_portfolio_board_json=tmp_path / "portfolio-board.json",
        strategygroup_portfolio_board_md=tmp_path / "portfolio-board.md",
        strategygroup_trial_candidate_pool_md=tmp_path / "trial-pool.md",
        strategygroup_capital_trial_envelope_projection_json=tmp_path
        / "capital-trial-envelope-projection.json",
        strategygroup_capital_trial_envelope_projection_md=tmp_path
        / "capital-trial-envelope-projection.md",
        strategygroup_capital_trial_envelope_json=tmp_path / "trial-envelope.json",
        strategygroup_capital_trial_envelope_md=tmp_path / "trial-envelope.md",
        strategygroup_research_intake_review_json=tmp_path
        / "research-intake-review.json",
        strategygroup_research_intake_review_md=tmp_path
        / "research-intake-review.md",
        strategygroup_trial_asset_admission_proposal_json=tmp_path
        / "trial-admission-proposal.json",
        strategygroup_trial_asset_admission_proposal_md=tmp_path
        / "trial-admission-proposal.md",
        brf2_owner_trial_policy_scope_json=tmp_path / "brf2-policy.json",
        brf2_owner_trial_policy_scope_md=tmp_path / "brf2-policy.md",
        brf2_required_facts_mapping_json=tmp_path / "brf2-required-facts.json",
        brf2_required_facts_mapping_md=tmp_path / "brf2-required-facts.md",
        brf2_runtime_signal_facts_json=tmp_path / "brf2-signal-facts.json",
        brf2_runtime_signal_facts_md=tmp_path / "brf2-signal-facts.md",
        brf2_runtime_signal_capture_json=tmp_path / "brf2-signal-capture.json",
        brf2_runtime_signal_capture_md=tmp_path / "brf2-signal-capture.md",
        brf2_shadow_candidate_evidence_json=(
            tmp_path / "brf2-shadow-evidence.json"
        ),
        brf2_shadow_candidate_evidence_md=tmp_path / "brf2-shadow-evidence.md",
        three_strategy_live_trial_portfolio_json=tmp_path
        / "three-strategy-portfolio.json",
        three_strategy_live_trial_portfolio_md=tmp_path
        / "three-strategy-portfolio.md",
        strategygroup_tradeability_decision_json=tmp_path / "tradeability.json",
        strategygroup_tradeability_decision_md=tmp_path / "tradeability.md",
        command_runner=fake_runner,
    )

    assert report["status"] == "needs_non_market_repair"
    assert _monitor_issues(report)["blockers"] == []
    assert _monitor_issues(report)["non_market_gaps"] == [_expected_brf2_fact_input_gap()]
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False


def test_local_monitor_sequence_clears_expansion_gap_when_review_work_loop_ready() -> None:
    module = _load_module()

    gap = module._expansion_review_non_market_gap(
        {"status": "review_needed_broader_observe_only_would_enter"},
        {"status": "l2_readiness_review_all_blocked"},
        {"status": "l2_intake_dry_run_no_candidates"},
        {"status": "l2_tier_policy_review_no_candidates"},
        {"status": "review_work_loop_ready"},
    )

    assert gap is None

    status = module._sequence_status(
        steps=[],
        artifacts={
            "daily_check": {
                "status": "waiting_for_market",
                "runtime_status": "waiting_for_market",
            },
            "goal_progress": {
                "status": "waiting_for_market",
                "runtime_status": "waiting_for_market",
            },
            "completion_audit": {"status": "not_complete_waiting_for_market"},
            "signal_coverage": {"status": "mainline_no_signal_broader_would_enter"},
            "signal_coverage_expansion_review": {
                "status": "review_needed_broader_observe_only_would_enter"
            },
            "l2_readiness_review": {"status": "l2_readiness_review_all_blocked"},
            "l2_intake_dry_run": {"status": "l2_intake_dry_run_no_candidates"},
            "l2_tier_policy_review": {"status": "l2_tier_policy_review_no_candidates"},
            "opportunity_review_work_loop": {"status": "review_work_loop_ready"},
        },
    )

    assert status == "waiting_for_market"


def test_local_monitor_sequence_treats_low_priority_would_enter_as_waiting() -> None:
    module = _load_module()

    status = module._sequence_status(
        steps=[],
        artifacts={
            "daily_check": {
                "status": "waiting_for_market",
                "runtime_status": "waiting_for_market",
            },
            "goal_progress": {
                "status": "waiting_for_market",
                "runtime_status": "waiting_for_market",
            },
            "completion_audit": {"status": "not_complete_waiting_for_market"},
            "signal_coverage": {
                "status": "mainline_no_signal_low_priority_broader_would_enter"
            },
            "signal_coverage_expansion_review": {
                "status": "low_priority_observe_only_would_enter_parked"
            },
            "l2_readiness_review": {"status": "l2_readiness_review_all_blocked"},
            "l2_intake_dry_run": {"status": "l2_intake_dry_run_no_candidates"},
            "l2_tier_policy_review": {"status": "l2_tier_policy_review_no_candidates"},
            "opportunity_review_work_loop": {"status": "review_work_loop_ready"},
        },
    )

    assert status == "waiting_for_market"


def test_local_monitor_sequence_success_allows_waiting_monitor_refresh() -> None:
    module = _load_module()

    report = {
        "status": "waiting_for_market_monitor_refresh_needed",
        "runtime_status": "waiting_for_market",
        "monitor_status": "needs_refresh",
        "owner_runtime_state": {
            "runtime_status": "waiting_for_market",
            "monitor_status": "needs_refresh",
            "owner_status": "waiting_for_opportunity",
            "owner_intervention_required": False,
            "monitor_refresh_needed": True,
            "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
            "waiting_for_market": True,
        },
        "owner_runtime_issues": {
            "blockers": [],
            "non_market_gaps": [],
            "blocker_count": 0,
            "non_market_gap_count": 0,
        },
        "checks": {
            "blockers": [],
            "execution_blockers": [],
            "non_market_gaps": [],
            "engineering_gaps": [],
            "monitor_refresh_gaps": ["runtime_progress_cache_stale"],
        },
    }

    assert module.artifact_monitor_refresh_needed(report) is True
    assert module._sequence_report_is_success(report)
    assert "hard_safety_stop" not in report["owner_runtime_issues"]["blockers"]
    assert report["owner_runtime_state"]["owner_intervention_required"] is False


def test_monitor_refresh_helper_typed_state_overrides_legacy_checks() -> None:
    module = _load_module()

    artifact = {
        "status": "waiting_for_market",
        "runtime_status": "waiting_for_market",
        "monitor_status": "fresh",
        "owner_runtime_state": {
            "runtime_status": "waiting_for_market",
            "monitor_status": "fresh",
            "owner_status": "waiting_for_opportunity",
            "owner_intervention_required": False,
            "monitor_refresh_needed": False,
            "monitor_refresh_reasons": [],
            "waiting_for_market": True,
        },
        "checks": {
            "monitor_refresh_needed": True,
            "monitor_refresh_reasons": ["legacy_stale_refresh_mirror"],
        },
    }

    assert module.artifact_monitor_refresh_needed(artifact) is False
    assert module.artifact_monitor_refresh_reasons(artifact) == []


def test_monitor_refresh_returncode_uses_shared_owner_runtime_issues_projection() -> None:
    module = _load_module()
    artifact = {
        "status": module.MONITOR_REFRESH_STATUS,
        "runtime_status": "waiting_for_market",
        "monitor_status": "needs_refresh",
        "owner_runtime_state": {
            "runtime_status": "waiting_for_market",
            "monitor_status": "needs_refresh",
            "owner_status": "waiting_for_opportunity",
            "owner_intervention_required": False,
            "monitor_refresh_needed": True,
            "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
            "waiting_for_market": True,
        },
        "owner_runtime_issues": {
            "blockers": [],
            "non_market_gaps": [],
        },
        "checks": {
            "blockers": ["legacy_checks_blocker_mirror"],
            "non_market_gaps": ["legacy_checks_gap_mirror"],
        },
    }
    step = {"name": "daily_check", "returncode": 2}

    assert module.artifact_owner_runtime_issues(artifact) == {
        "blockers": [],
        "non_market_gaps": [],
    }
    assert module.monitor_step_returncode_is_refresh(
        step_name=step["name"],
        returncode=step["returncode"],
        artifact=artifact,
    ) is True
    assert module._sequence_report_is_success(artifact) is True


def test_owner_runtime_issues_projection_keeps_legacy_checks_as_compatibility_only() -> None:
    module = _load_module()

    legacy_artifact = {
        "checks": {
            "blockers": ["legacy_blocker"],
            "non_market_gaps": [{"source": "legacy_checks"}],
        }
    }
    typed_artifact = {
        "owner_runtime_issues": {"blockers": [], "non_market_gaps": []},
        "checks": {
            "blockers": ["legacy_blocker"],
            "non_market_gaps": [{"source": "legacy_checks"}],
        },
    }

    assert module.artifact_owner_runtime_issues(legacy_artifact) == {
        "blockers": ["legacy_blocker"],
        "non_market_gaps": [{"source": "legacy_checks"}],
    }
    assert module.artifact_owner_runtime_issues(typed_artifact) == {
        "blockers": [],
        "non_market_gaps": [],
    }


def test_local_monitor_sequence_owner_labels_use_shared_monitor_mapping() -> None:
    module = _load_module()

    def owner_state(status: str) -> str:
        return module.monitor_owner_state_label_for(
            status,
            local_labels=module.OWNER_PROGRESS_STATE_LABELS,
            default_label="需要修复",
        )

    def owner_action(status: str) -> str:
        return module.monitor_owner_action_label_for(
            status,
            local_labels=module.OWNER_PROGRESS_ACTION_LABELS,
            default_label="修复本地监控或非市场证据缺口",
        )

    expected = {
        module.MONITOR_REFRESH_STATUS: (
            "等待机会",
            "刷新本地 runtime monitor 缓存",
        ),
        module.DEPLOYMENT_ISSUE_STATUS: (
            "暂不可用",
            "刷新或修复 runtime monitor 权威状态",
        ),
        "needs_refresh": (
            "监控状态需刷新",
            "刷新本地 runtime monitor 缓存",
        ),
        "complete": ("已完成", "归档第一笔边界内真实订单闭环"),
        "processing": ("处理中", "等待系统完成当前链路"),
        "degraded": ("需要修复", "修复本地监控或非市场证据缺口"),
        "blocked": ("需要修复", "修复本地监控或非市场证据缺口"),
        "unknown": ("需要修复", "修复本地监控或非市场证据缺口"),
    }
    for status, (state, action) in expected.items():
        assert owner_state(status) == state
        assert owner_action(status) == action


def test_local_monitor_sequence_tradeability_decision_projection_preserves_shape() -> None:
    module = _load_module()
    artifact = {
        "status": "tradeability_decision_ready",
        "summary": {
            "row_count": 3,
            "tradable_now_count": 0,
            "actionable_now_count": 0,
            "real_order_authority_count": 0,
            "controlled_live_standby_count": 3,
            "stage_5_waiting_live_opportunity_ready_count": 3,
            "top_strategy_group_id": "BRF2-001",
            "top_decision": "not_tradable_market_wait",
            "top_first_blocker_class": "fresh_signal_absent",
            "top_next_action": "continue_armed_observation",
        },
        "decision_rows": [
            {
                "strategy_group_id": "MPG-001",
                "blocker_owner": "market",
                "after_next_state": "armed_observation",
            },
            {
                "strategy_group_id": "BRF2-001",
                "blocker_owner": "market",
                "after_next_state": "armed_observation",
            },
            {
                "strategy_group_id": "CPM-RO-001",
                "stage": "armed_observation",
                "decision": "not_tradable_market_wait",
                "first_blocker_class": "fresh_cpm_long_signal_absent",
                "blocker_owner": "market",
                "required_facts_status": "ready",
                "after_next_state": "live_submit_ready",
            },
        ],
        "july_bullish_rebound_trade_path_closure": {
            "status": "july_bullish_rebound_trade_path_closure_ready",
            "hypothesis_id": "JULY-BULLISH-REBOUND-TRADE-PATH-CLOSURE-001",
            "machine_consumption_surface": "tradeability_decision",
            "summary": {
                "machine_consumed_path_count": 5,
                "long_side_path_count": 3,
                "short_side_guard_path_count": 2,
                "rbr_exit_decision_count": 2,
            },
            "checks": {
                "required_path_ids_present": True,
                "cpm_mapping_gap_removed_from_first_blockers": True,
                "rbr_observe_only_has_exit_decision": True,
                "capital_scope_uses_action_time_exchange_available_balance": True,
            },
            "paths": [
                {
                    "path_id": "CPM-LONG",
                    "required_facts_mapping_status": "ready",
                    "first_blocker": "fresh_cpm_long_signal_absent",
                    "blocker_owner": "market",
                    "can_trade_now": False,
                    "capital_scope_source": (
                        "action_time_exchange_available_balance"
                    ),
                }
            ],
        },
        "checks": {"owner_intervention_required": False},
    }

    projection = module._TradeabilityDecisionProjection.from_artifact(artifact)

    assert projection.active is True
    assert projection.row_count_matches_decision_rows is True
    assert projection.top_decision == "not_tradable_market_wait"
    assert projection.top_blocker_owner == "market"
    july = projection.as_dict()["july_bullish_rebound_trade_path_closure"]
    assert july["status"] == "july_bullish_rebound_trade_path_closure_ready"
    assert july["machine_consumed_path_count"] == 5
    assert july["long_side_path_count"] == 3
    assert july["short_side_guard_path_count"] == 2
    assert july["rbr_exit_decision_count"] == 2
    assert july["required_path_ids_present"] is True
    assert july["cpm_mapping_gap_removed_from_first_blockers"] is True
    assert july["rbr_observe_only_has_exit_decision"] is True
    assert (
        july["capital_scope_uses_action_time_exchange_available_balance"] is True
    )
    cpm = projection.as_dict()["cpm_armed_observation"]
    assert cpm["stage"] == "armed_observation"
    assert cpm["decision"] == "not_tradable_market_wait"
    assert cpm["first_blocker_class"] == "fresh_cpm_long_signal_absent"
    assert cpm["required_facts_status"] == "ready"
    assert cpm["path_id"] == "CPM-LONG"
    assert cpm["path_required_facts_mapping_status"] == "ready"
    assert cpm["path_can_trade_now"] is False
    assert cpm["capital_scope_source"] == "action_time_exchange_available_balance"
    assert "actionable_now" not in projection.as_dict()
    assert "real_order_authority" not in projection.as_dict()
    assert "runtime_authority_row_counts" not in projection.as_dict()
    assert projection.as_dict() == module._sequence_tradeability_decision_summary(
        artifact
    )


def test_tradeability_projection_ignores_legacy_checks_owner_intervention() -> None:
    module = _load_module()
    artifact = {
        "status": "tradeability_decision_ready",
        "summary": {
            "row_count": 1,
            "top_strategy_group_id": "BRF2-001",
            "top_decision": "not_tradable_market_wait",
            "top_first_blocker_class": "fresh_signal_absent",
            "top_next_action": "continue_armed_observation",
        },
        "decision_rows": [
            {
                "strategy_group_id": "BRF2-001",
                "blocker_owner": "market",
                "after_next_state": "armed_observation",
            },
        ],
        "owner_runtime_state": {"owner_intervention_required": False},
        "checks": {"owner_intervention_required": True},
    }

    projection = module._TradeabilityDecisionProjection.from_artifact(artifact)

    assert projection.owner_intervention_required is False
    assert projection.as_dict()["owner_intervention_required"] is False


def test_sequence_success_ignores_legacy_checks_owner_intervention_mirror() -> None:
    module = _load_module()
    report = {
        "status": "waiting_for_market",
        "runtime_status": "waiting_for_market",
        "owner_runtime_issues": {"blockers": [], "non_market_gaps": []},
        "owner_runtime_state": {"owner_intervention_required": False},
        "notification": {"owner_intervention_required": False},
        "checks": {"owner_intervention_required": True},
    }

    assert module._sequence_report_is_success(report) is True


def test_owner_intervention_helper_ignores_legacy_checks_mirror() -> None:
    module = _load_module()

    assert (
        module.owner_intervention_required_from_sources(
            artifacts=[
                {
                    "owner_runtime_state": {"owner_intervention_required": False},
                    "checks": {"owner_intervention_required": True},
                }
            ],
            execution_blockers=[],
            engineering_gaps=[],
        )
        is False
    )
    assert (
        module.owner_intervention_required_from_sources(
            artifacts=[{"owner_runtime_state": {"owner_intervention_required": True}}],
            execution_blockers=[],
            engineering_gaps=[],
        )
        is True
    )


def test_local_monitor_sequence_three_strategy_portfolio_projection_preserves_shape() -> None:
    module = _load_module()
    artifact = {
        "status": "three_strategy_live_trial_portfolio_ready",
        "objective_met": True,
        "seat_count": 3,
        "selected_strategy_groups": ["MPG-001", "BRF2-001", "SOR-001"],
        "seat_readiness": {
            "MPG-001": {"first_blocker": {"blocker_owner": "market"}},
            "BRF2-001": {"first_blocker": {"blocker_owner": "owner"}},
            "SOR-001": {"first_blocker": {"blocker_owner": "engineering"}},
        },
        "next_engineering_bottleneck": {
            "MPG-001": "fresh_signal_wait",
            "BRF2-001": "owner_policy_scope_missing",
        },
        "stage_5_live_opportunity_standby": {
            "status": "waiting_for_trial_grade_live_opportunity",
            "ready": True,
            "standby_count": 3,
            "action_time_preflight_pending_fresh_signal": True,
            "hard_safety_gates_relaxed": False,
        },
    }

    projection = module._ThreeStrategyPortfolioSummaryProjection.from_artifact(artifact)

    assert projection.ready is True
    assert projection.objective_met is True
    assert projection.market_wait_count == 1
    assert projection.owner_policy_gap_count == 1
    assert projection.engineering_gap_count == 1
    assert projection.controlled_live_standby_count == 3
    assert projection.hard_safety_gates_relaxed is False
    assert projection.readiness_stage_evidence["source"] == (
        "three_strategy_live_trial_portfolio.summary_projection"
    )
    assert projection.readiness_stage_evidence["live_submit_ready"] is False
    assert "actionable_now" not in projection.readiness_stage_evidence
    assert "real_order_authority" not in projection.readiness_stage_evidence
    assert projection.readiness_stage_evidence["can_create_execution_attempt"] is False
    assert projection.primary_judgment_source is False
    assert projection.tradeability_decision_source is False
    assert projection.runtime_truth_source is False
    assert "actionable_now" not in projection.as_dict()
    assert "real_order_authority" not in projection.as_dict()
    assert projection.as_dict() == module._sequence_three_strategy_portfolio_summary(
        artifact
    )


def test_local_monitor_sequence_brf2_runtime_signal_facts_projection_preserves_shape() -> None:
    module = _load_module()
    artifact = {
        "status": "brf2_runtime_signal_facts_missing_watcher_input",
        "strategy_group_id": "BRF2-001",
        "fact_input_present": False,
        "watcher_tick_present": False,
        "source_status": "missing",
        "source_path": "",
        "first_blocker": {
            "class": "brf2_watcher_fact_input_missing",
            "owner": "engineering",
            "repair_checkpoint": "attach_brf2_watcher_fact_input_producer",
        },
        "fact_input_checkpoint": "attach_brf2_watcher_fact_input_producer",
    }

    projection = module._BRF2RuntimeSignalFactsProjection.from_artifact(artifact)

    assert projection.active is True
    assert projection.strategy_group_id == "BRF2-001"
    assert projection.fact_input_present is False
    assert projection.watcher_tick_present is False
    assert projection.first_blocker_class == "brf2_watcher_fact_input_missing"
    assert projection.projection_role == "requiredfacts_input_health_projection"
    assert projection.state_source == "brf2_runtime_signal_facts"
    assert projection.primary_judgment_source is False
    assert projection.tradeability_decision_source is False
    assert projection.runtime_truth_source is False
    assert projection.live_requiredfacts_authority is False
    assert "actionable_now" not in projection.as_dict()
    assert "real_order_authority" not in projection.as_dict()
    assert projection.as_dict() == module._sequence_brf2_runtime_signal_facts_summary(
        artifact
    )


def test_local_monitor_sequence_brf2_runtime_signal_capture_projection_preserves_shape() -> None:
    module = _load_module()
    artifact = {
        "status": "brf2_runtime_signal_capture_ready",
        "strategy_group_id": "BRF2-001",
        "fact_input_status": "brf2_runtime_signal_facts_missing_watcher_input",
        "watcher_scope": {
            "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
        },
        "signal_detector_preview": {
            "fact_input_present": False,
            "watcher_tick_present": False,
            "current_signal_state": "fact_input_missing",
            "fresh_signal_present": False,
            "first_blocker_class": "brf2_watcher_fact_input_missing",
            "first_blocker_owner": "engineering",
            "signal_capture_checkpoint": "attach_brf2_watcher_fact_input_producer",
            "missing_required_fact_keys": ["brf2_runtime_signal_row"],
            "active_disable_fact_keys": [],
        },
        "no_action_attribution": {"blocked_fact_count": 1},
        "shadow_candidate_shape": {"shadow_candidate_ready": False},
    }

    projection = module._BRF2RuntimeSignalCaptureProjection.from_artifact(artifact)

    assert projection.ready is True
    assert projection.signal_id == "brf2_short_rally_failure_fresh_signal_v1"
    assert projection.current_signal_state == "fact_input_missing"
    assert projection.first_blocker_class == "brf2_watcher_fact_input_missing"
    assert projection.missing_required_fact_count == 1
    assert projection.shadow_candidate_shape_ready is False
    assert projection.projection_role == "runtime_readiness_signal_capture_projection"
    assert projection.state_source == "brf2_runtime_signal_capture"
    assert projection.primary_judgment_source is False
    assert projection.tradeability_decision_source is False
    assert projection.runtime_truth_source is False
    assert projection.live_submit_readiness_source == "runtime_safety_state"
    assert projection.execution_attempt_required_for_lifecycle_entry is True
    assert "actionable_now" not in projection.as_dict()
    assert "real_order_authority" not in projection.as_dict()
    assert "live_submit_authority" not in projection.as_dict()
    assert "operation_layer_authority" not in projection.as_dict()
    assert projection.as_dict() == module._sequence_brf2_runtime_signal_capture_summary(
        artifact
    )


def test_local_monitor_sequence_brf2_runtime_signal_capture_projection_preserves_disable_blocker() -> None:
    module = _load_module()
    artifact = {
        "status": "brf2_runtime_signal_capture_ready",
        "strategy_group_id": "BRF2-001",
        "fact_input_status": "brf2_runtime_signal_facts_ready",
        "watcher_scope": {
            "signal_id": "brf2_short_rally_failure_fresh_signal_v1",
        },
        "signal_detector_preview": {
            "fact_input_present": True,
            "watcher_tick_present": True,
            "current_signal_state": "blocked_by_disable_fact",
            "fresh_signal_present": False,
            "first_blocker_class": "short_squeeze_risk_state_disable_active",
            "first_blocker_owner": "market",
            "signal_capture_checkpoint": (
                "continue_brf2_armed_observation_until_disable_clears"
            ),
            "missing_required_fact_keys": ["short_squeeze_risk_state"],
            "active_disable_fact_keys": ["short_squeeze_risk_state"],
        },
        "no_action_attribution": {"blocked_fact_count": 2},
        "shadow_candidate_shape": {"shadow_candidate_ready": False},
    }

    projection = module._sequence_brf2_runtime_signal_capture_summary(artifact)

    assert projection["current_signal_state"] == "blocked_by_disable_fact"
    assert projection["first_blocker_class"] == (
        "short_squeeze_risk_state_disable_active"
    )
    assert projection["first_blocker_owner"] == "market"
    assert projection["signal_capture_checkpoint"] == (
        "continue_brf2_armed_observation_until_disable_clears"
    )
    assert projection["active_disable_fact_count"] == 1
    assert projection["blocked_fact_count"] == 2


def test_local_monitor_sequence_brf2_shadow_evidence_projection_is_provenance() -> None:
    module = _load_module()
    artifact = {
        "status": "brf2_shadow_candidate_evidence_ready",
        "strategy_group_id": "BRF2-001",
        "shadow_candidate_evidence_ready": True,
        "shadow_candidate_evidence": {
            "shadow_candidate_evidence_id": (
                "brf2-shadow-evidence:brf2-signal-001"
            ),
            "signal_state": "fresh_signal_present",
        },
        "first_blocker": {
            "class": "brf2_candidate_authorization_evidence_not_created",
            "owner": "system",
        },
        "next_runtime_step": "prepare_fresh_candidate_authorization_evidence",
    }

    projection = module._BRF2ShadowCandidateEvidenceProjection.from_artifact(artifact)

    assert projection.active is True
    assert projection.strategy_group_id == "BRF2-001"
    assert projection.shadow_candidate_evidence_ready is True
    assert projection.shadow_candidate_evidence_id == (
        "brf2-shadow-evidence:brf2-signal-001"
    )
    assert projection.signal_state == "fresh_signal_present"
    assert projection.projection_role == "shadow_candidate_evidence_provenance"
    assert projection.state_source == "brf2_shadow_candidate_evidence"
    assert projection.primary_judgment_source is False
    assert projection.non_executing_evidence is True
    for removed_projection_field in (
        "live_submit_authority",
        "operation_layer_authority",
        "actionable_now",
        "real_order_authority",
    ):
        assert removed_projection_field not in projection.as_dict()
    assert projection.as_dict() == (
        module._sequence_brf2_shadow_candidate_evidence_summary(artifact)
    )


def test_local_monitor_sequence_brf2_shadow_evidence_projection_preserves_disable_blocker() -> None:
    module = _load_module()
    artifact = {
        "status": "brf2_shadow_candidate_evidence_waiting_for_fresh_signal",
        "strategy_group_id": "BRF2-001",
        "shadow_candidate_evidence_ready": False,
        "shadow_candidate_evidence": {
            "shadow_candidate_evidence_id": "",
            "signal_state": "blocked_by_disable_fact",
        },
        "first_blocker": {
            "class": "short_squeeze_risk_state_disable_active",
            "owner": "market",
        },
        "next_runtime_step": (
            "continue_brf2_armed_observation_until_disable_clears"
        ),
    }

    projection = module._sequence_brf2_shadow_candidate_evidence_summary(artifact)

    assert projection["active"] is True
    assert projection["signal_state"] == "blocked_by_disable_fact"
    assert projection["first_blocker_class"] == (
        "short_squeeze_risk_state_disable_active"
    )
    assert projection["first_blocker_owner"] == "market"
    assert projection["next_runtime_step"] == (
        "continue_brf2_armed_observation_until_disable_clears"
    )


def test_local_monitor_sequence_cpm_projection_preserves_armed_observation_chain() -> None:
    module = _load_module()

    identity = module._sequence_cpm_identity_routing_decision_summary(
        {
            "status": "cpm_identity_routing_decision_ready",
            "strategy_group_id": "CPM-RO-001",
            "path_id": "CPM-LONG",
            "identity_decision": "standalone_trial_asset",
            "cpm_long_vs_mpg_long_distinct": True,
        }
    )
    policy = module._sequence_cpm_owner_trial_policy_summary(
        {
            "status": "cpm_owner_trial_policy_scope_recorded",
            "owner_policy_recorded": True,
            "cpm_policy_scope_recorded": True,
            "owner_policy_scope_missing": False,
            "policy": {
                "strategy_group_id": "CPM-RO-001",
                "capital_scope": {
                    "amount_source": "action_time_exchange_available_balance"
                },
                "side_scope": ["long"],
            },
        }
    )
    mapping = module._sequence_cpm_required_facts_mapping_summary(
        {
            "status": "cpm_required_facts_mapping_ready",
            "strategy_group_id": "CPM-RO-001",
            "path_id": "CPM-LONG",
            "required_facts_mapping_ready": True,
            "live_required_facts_authority": False,
            "action_time_refresh_required": True,
            "fresh_signal_rule": {
                "signal_id": "cpm_long_pullback_reclaim_signal_v1"
            },
            "required_fact_observation_specs": [{"fact_key": "htf_trend_intact"}],
            "disable_fact_observation_specs": [{"fact_key": "htf_trend_broken"}],
        }
    )
    capture = module._sequence_cpm_runtime_signal_capture_summary(
        {
            "status": "cpm_runtime_signal_capture_ready",
            "strategy_group_id": "CPM-RO-001",
            "path_id": "CPM-LONG",
            "fact_input_status": "cpm_runtime_signal_facts_ready",
            "fact_input_present": True,
            "watcher_tick_present": True,
            "watcher_scope": {
                "signal_id": "cpm_long_pullback_reclaim_signal_v1"
            },
            "signal_detector_preview": {
                "current_signal_state": "fresh_signal_absent",
                "fresh_signal_present": False,
                "first_blocker_class": "fresh_cpm_long_signal_absent",
                "first_blocker_owner": "market",
                "signal_capture_checkpoint": (
                    "continue_cpm_long_armed_observation_until_reclaim_signal"
                ),
                "missing_required_fact_keys": ["reclaim_confirmed"],
                "active_disable_fact_keys": [],
                "action_time_pending_fact_keys": [
                    "active_position_or_open_order_clear",
                    "action_time_available_balance",
                ],
            },
            "shadow_candidate_shape": {"shadow_candidate_ready": False},
        }
    )
    shadow = module._sequence_cpm_shadow_candidate_evidence_summary(
        {
            "status": "cpm_shadow_candidate_evidence_waiting_for_fresh_signal",
            "strategy_group_id": "CPM-RO-001",
            "shadow_candidate_evidence_ready": False,
            "shadow_candidate_evidence": {"signal_state": "fresh_signal_absent"},
            "first_blocker": {
                "class": "fresh_cpm_long_signal_absent",
                "owner": "market",
            },
            "next_runtime_step": (
                "continue_cpm_long_armed_observation_until_reclaim_signal"
            ),
        }
    )
    rehearsal = module._sequence_cpm_dry_run_submit_rehearsal_summary(
        {
            "status": "cpm_dry_run_submit_rehearsal_shape_ready",
            "strategy_group_id": "CPM-RO-001",
            "path_id": "CPM-LONG",
            "dry_run_submit_rehearsal": "shape_ready",
            "checks": {
                "armed_observation_ready": True,
                "submit_rehearsal_shape_ready": True,
                "fresh_signal_submit_rehearsal_passed": False,
                "candidate_authorization_evidence_ready": False,
                "finalgate_dry_run_passed": False,
                "operation_layer_paper_passed": False,
                "execution_attempt_rehearsal_ready": False,
                "synthetic_fresh_signal_fixture_ready": True,
                "synthetic_fresh_signal_present": True,
                "synthetic_dangerous_authority_fields_fail_closed": True,
                "synthetic_shadow_candidate_evidence_ready": True,
                "synthetic_candidate_authorization_evidence_shape_ready": True,
                "synthetic_action_time_required_facts_declared": True,
                "synthetic_finalgate_dry_run_passed": True,
                "synthetic_operation_layer_paper_passed": True,
                "synthetic_execution_attempt_rehearsal_ready": True,
                "exchange_write": False,
                "order_created": False,
            },
            "synthetic_fresh_signal_rehearsal": {
                "fixture_ready": True,
                "fresh_signal_present": True,
                "shadow_candidate_evidence_ready": True,
                "candidate_authorization_evidence_shape_ready": True,
                "action_time_required_facts_declared": True,
                "finalgate_dry_run_passed": True,
                "operation_layer_paper_passed": True,
                "execution_attempt_rehearsal_ready": True,
                "fresh_signal_submit_rehearsal_passed": True,
                "dangerous_authority_fields_fail_closed": True,
                "not_live_market_signal": True,
                "not_execution_authority": True,
            },
        }
    )

    assert identity["standalone_trial_asset"] is True
    assert policy["owner_policy_recorded"] is True
    assert policy["capital_scope_source"] == "action_time_exchange_available_balance"
    assert mapping["ready"] is True
    assert mapping["live_required_facts_authority"] is False
    assert mapping["action_time_refresh_required"] is True
    assert capture["ready"] is True
    assert capture["current_signal_state"] == "fresh_signal_absent"
    assert capture["first_blocker_class"] == "fresh_cpm_long_signal_absent"
    assert capture["shadow_candidate_shape_ready"] is False
    assert shadow["signal_state"] == "fresh_signal_absent"
    assert shadow["first_blocker_class"] == "fresh_cpm_long_signal_absent"
    assert rehearsal["dry_run_submit_rehearsal"] == "shape_ready"
    assert rehearsal["armed_observation_ready"] is True
    assert rehearsal["submit_rehearsal_shape_ready"] is True
    assert rehearsal["fresh_signal_submit_rehearsal_passed"] is False
    assert rehearsal["finalgate_dry_run_passed"] is False
    assert rehearsal["operation_layer_paper_passed"] is False
    assert rehearsal["synthetic_fresh_signal_fixture_ready"] is True
    assert rehearsal["synthetic_fresh_signal_present"] is True
    assert rehearsal["synthetic_dangerous_authority_fields_fail_closed"] is True
    assert rehearsal["synthetic_candidate_authorization_evidence_shape_ready"] is True
    assert rehearsal["synthetic_action_time_required_facts_declared"] is True
    assert rehearsal["synthetic_finalgate_dry_run_passed"] is True
    assert rehearsal["synthetic_operation_layer_paper_passed"] is True
    assert rehearsal["synthetic_execution_attempt_rehearsal_ready"] is True
    assert rehearsal["synthetic_fresh_signal_submit_rehearsal_passed"] is True
    assert rehearsal["exchange_write"] is False
    assert rehearsal["order_created"] is False
    for projection in (identity, policy, mapping, capture, shadow, rehearsal):
        assert projection["primary_judgment_source"] is False
        assert "actionable_now" not in projection
        assert "real_order_authority" not in projection


def test_monitor_status_helpers_fail_closed_for_unknown_status() -> None:
    module = _load_module()

    assert module.monitor_runtime_status_for(status="unknown") == (
        "temporarily_unavailable"
    )
    assert module.monitor_runtime_status_for(status="ready") == "running"
    assert module.monitor_owner_status_for(
        runtime_status="unknown",
        monitor_status="unknown",
    ) == "temporarily_unavailable"
    assert module.monitor_owner_status_for(
        runtime_status="running",
        monitor_status="fresh",
    ) == "running"


def test_local_monitor_sequence_monitor_status_requires_source() -> None:
    module = _load_module()

    assert module.artifact_monitor_status({"status": "waiting_for_market"}) == ""
    assert module.artifact_monitor_status({"status": "unknown"}) == ""
    assert (
        module.artifact_monitor_status(
            {"owner_runtime_state": {"monitor_status": "fresh"}}
        )
        == "fresh"
    )
    assert module.artifact_monitor_status({"status": module.MONITOR_REFRESH_STATUS}) == (
        "needs_refresh"
    )
    assert (
        module.artifact_monitor_status(
            {"status": "temporarily_unavailable_monitor_refresh_needed"}
        )
        == "needs_refresh"
    )


def test_combined_artifact_monitor_status_preserves_source_order() -> None:
    module = _load_module()

    assert (
        module.combined_artifact_monitor_status(
            status="waiting_for_market",
            artifacts=[
                {"owner_runtime_state": {"monitor_status": "fresh"}},
                {"status": "waiting_for_market_monitor_refresh_needed"},
            ],
        )
        == "needs_refresh"
    )
    assert (
        module.combined_artifact_monitor_status(
            status="waiting_for_market",
            artifacts=[
                {"checks": {"deployment_issue": True}},
                {"status": "waiting_for_market_monitor_refresh_needed"},
            ],
        )
        == "deployment_issue"
    )


def test_monitor_status_projection_centralizes_owner_runtime_state() -> None:
    module = _load_module()

    projection = module.monitor_status_projection(
        status="waiting_for_market",
        artifacts=[
            {
                "runtime_status": "waiting_for_market",
                "owner_runtime_state": {"monitor_status": "fresh"},
            },
            {
                "status": module.MONITOR_REFRESH_STATUS,
                "owner_runtime_state": {
                    "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
                },
            },
        ],
        owner_intervention_required=False,
    )

    assert projection.runtime_status == "waiting_for_market"
    assert projection.monitor_status == "needs_refresh"
    assert projection.owner_status == "waiting_for_opportunity"
    assert projection.monitor_refresh_needed is True
    assert projection.monitor_refresh_reasons == ["runtime_progress_cache_stale"]
    assert projection.owner_runtime_state == {
        "runtime_status": "waiting_for_market",
        "monitor_status": "needs_refresh",
        "owner_status": "waiting_for_opportunity",
        "owner_intervention_required": False,
        "monitor_refresh_needed": True,
        "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
        "waiting_for_market": True,
    }


def test_monitor_status_projection_ignores_legacy_refresh_checks_mirror() -> None:
    module = _load_module()

    projection = module.monitor_status_projection(
        status="waiting_for_market",
        artifacts=[
            {
                "runtime_status": "waiting_for_market",
                "checks": {
                    "monitor_refresh_needed": True,
                    "monitor_refresh_reasons": ["legacy_cache_stale"],
                },
            }
        ],
        owner_intervention_required=False,
    )

    assert projection.monitor_status == "unknown"
    assert projection.monitor_refresh_needed is False
    assert projection.monitor_refresh_reasons == []
    assert projection.owner_runtime_state["waiting_for_market"] is True


def test_monitor_refresh_sequence_status_uses_typed_runtime_source() -> None:
    module = _load_module()

    assert (
        module.monitor_refresh_sequence_status(
            [
                {
                    "status": module.MONITOR_REFRESH_STATUS,
                    "runtime_status": "waiting_for_market",
                }
            ]
        )
        == module.MONITOR_REFRESH_STATUS
    )
    assert (
        module.monitor_refresh_sequence_status(
            [{"status": module.MONITOR_REFRESH_STATUS}]
        )
        == "temporarily_unavailable_monitor_refresh_needed"
    )
    assert module.monitor_refresh_sequence_status([{"status": "waiting_for_market"}]) == ""


def test_local_monitor_sequence_monitor_status_fresh_requires_artifact_source() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {
            "status": "waiting_for_market",
            "runtime_status": "waiting_for_market",
            "owner_runtime_state": {"monitor_status": "fresh"},
        },
        "goal_progress": {
            "status": "waiting_for_market",
            "runtime_status": "waiting_for_market",
        },
        "completion_audit": {"status": "not_complete_waiting_for_market"},
        "signal_coverage": {
            "status": "mainline_no_signal_low_priority_broader_would_enter"
        },
    }

    status = module._sequence_status(steps=[], artifacts=artifacts)
    monitor_status = module._sequence_monitor_status(status=status, artifacts=artifacts)

    assert status == "waiting_for_market"
    assert monitor_status == "fresh"


def test_local_monitor_sequence_status_accepts_artifact_carrier() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {
            "status": "waiting_for_market",
            "runtime_status": "waiting_for_market",
            "owner_runtime_state": {"monitor_status": "fresh"},
        },
        "goal_progress": {
            "status": "waiting_for_market",
            "runtime_status": "waiting_for_market",
        },
        "completion_audit": {"status": "not_complete_waiting_for_market"},
        "signal_coverage": {
            "status": "mainline_no_signal_low_priority_broader_would_enter"
        },
    }

    status = module._sequence_status(steps=[], artifacts=artifacts)
    monitor_status = module._sequence_monitor_status(status=status, artifacts=artifacts)

    assert status == "waiting_for_market"
    assert monitor_status == "fresh"


def test_local_monitor_sequence_monitor_status_without_source_stays_unknown() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {
            "status": "waiting_for_market",
            "runtime_status": "waiting_for_market",
        },
        "goal_progress": {
            "status": "waiting_for_market",
            "runtime_status": "waiting_for_market",
        },
        "completion_audit": {"status": "not_complete_waiting_for_market"},
        "signal_coverage": {"status": "mainline_no_signal_low_priority_broader_would_enter"},
    }

    status = module._sequence_status(steps=[], artifacts=artifacts)
    monitor_status = module._sequence_monitor_status(status=status, artifacts=artifacts)
    runtime_status = module._sequence_runtime_status(status=status, artifacts=artifacts)

    assert status == "waiting_for_market"
    assert runtime_status == "waiting_for_market"
    assert monitor_status == "unknown"


def test_local_monitor_sequence_status_does_not_use_top_level_artifact_waiting() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {"status": "waiting_for_market"},
        "goal_progress": {"status": "waiting_for_market"},
        "completion_audit": {"status": "not_complete_waiting_for_market"},
        "signal_coverage": {"status": "mainline_no_signal_low_priority_broader_would_enter"},
    }

    status = module._sequence_status(steps=[], artifacts=artifacts)
    runtime_status = module._sequence_runtime_status(status=status, artifacts=artifacts)

    assert status == "needs_non_market_repair"
    assert runtime_status == "temporarily_unavailable"


def test_local_monitor_sequence_status_retains_owner_runtime_waiting() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {
            "status": "unknown",
            "owner_runtime_state": {"runtime_status": "waiting_for_market"},
        },
        "goal_progress": {
            "status": "unknown",
            "owner_runtime_state": {"runtime_status": "waiting_for_market"},
        },
        "completion_audit": {"status": "not_complete_waiting_for_market"},
        "signal_coverage": {"status": "mainline_no_signal_low_priority_broader_would_enter"},
    }

    status = module._sequence_status(steps=[], artifacts=artifacts)
    runtime_status = module._sequence_runtime_status(status=status, artifacts=artifacts)

    assert status == "waiting_for_market"
    assert runtime_status == "waiting_for_market"


def test_local_monitor_sequence_processing_does_not_use_top_level_artifact_status() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {"status": "processing"},
        "goal_progress": {"status": "processing"},
        "completion_audit": {"status": "not_complete_waiting_for_market"},
        "signal_coverage": {"status": "mainline_no_signal_low_priority_broader_would_enter"},
    }

    status = module._sequence_status(steps=[], artifacts=artifacts)
    runtime_status = module._sequence_runtime_status(status=status, artifacts=artifacts)

    assert status == "needs_non_market_repair"
    assert runtime_status == "temporarily_unavailable"


def test_local_monitor_sequence_processing_retains_declared_runtime_status() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {
            "status": "unknown",
            "owner_runtime_state": {"runtime_status": "processing"},
        },
        "goal_progress": {"status": "unknown"},
        "completion_audit": {"status": "not_complete_waiting_for_market"},
        "signal_coverage": {"status": "mainline_no_signal_low_priority_broader_would_enter"},
    }

    status = module._sequence_status(steps=[], artifacts=artifacts)
    runtime_status = module._sequence_runtime_status(status=status, artifacts=artifacts)

    assert status == "processing"
    assert runtime_status == "processing"


def test_local_monitor_sequence_does_not_default_monitor_refresh_to_market_wait() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {
            "status": module.MONITOR_REFRESH_STATUS,
            "monitor_status": "needs_refresh",
        },
        "goal_progress": {
            "status": module.MONITOR_REFRESH_STATUS,
            "monitor_status": "needs_refresh",
        },
        "completion_audit": {"status": "not_complete_waiting_for_market"},
        "signal_coverage": {"status": "mainline_no_signal_low_priority_broader_would_enter"},
    }

    status = module._sequence_status(steps=[], artifacts=artifacts)
    runtime_status = module._sequence_runtime_status(status=status, artifacts=artifacts)

    assert status == "temporarily_unavailable_monitor_refresh_needed"
    assert runtime_status == "temporarily_unavailable"


def test_local_monitor_sequence_classifies_binance_public_facts_gap_as_refresh() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {
            "status": "waiting_for_market",
            "runtime_status": "waiting_for_market",
            "owner_runtime_state": {"monitor_status": "fresh"},
        },
        "goal_progress": {
            "status": "waiting_for_market",
            "runtime_status": "waiting_for_market",
        },
        "binance_usdm_public_facts": {
            "status": "binance_usdm_public_facts_unavailable",
            "checks": {"public_facts_ready": False},
        },
        "completion_audit": {"status": "not_complete_waiting_for_market"},
        "signal_coverage": {
            "status": "mainline_no_signal_low_priority_broader_would_enter"
        },
    }
    steps = [
        {
            "name": "binance_usdm_public_facts",
            "returncode": 2,
            "artifact": artifacts["binance_usdm_public_facts"],
        }
    ]

    status = module._sequence_status(steps=steps, artifacts=artifacts)

    assert module._step_returncode_is_allowed_monitor_refresh(
        steps[0], artifacts
    ) is True
    assert status == "temporarily_unavailable_monitor_refresh_needed"


def test_local_monitor_sequence_fresh_signal_processing_beats_cache_refresh() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {
            "status": "processing",
            "runtime_status": "processing",
            "monitor_status": "needs_refresh",
            "checks": {
                "monitor_refresh_needed": True,
                "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
            },
        },
        "goal_progress": {
            "status": "processing",
            "runtime_status": "processing",
            "monitor_status": "needs_refresh",
            "checks": {
                "monitor_refresh_needed": True,
                "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
            },
        },
        "completion_audit": {"status": "not_complete_runtime_processing"},
        "signal_coverage": {"status": "mainline_runtime_signal_ready"},
    }

    status = module._sequence_status(steps=[], artifacts=artifacts)
    monitor_status = module._sequence_monitor_status(status=status, artifacts=artifacts)
    runtime_status = module._sequence_runtime_status(status=status, artifacts=artifacts)
    owner_status = module.monitor_owner_status_for(
        runtime_status=runtime_status,
        monitor_status=monitor_status,
        owner_intervention_required=False,
        default_status="temporarily_unavailable",
    )

    assert status == "processing"
    assert runtime_status == "processing"
    assert monitor_status == "needs_refresh"
    assert owner_status == "processing"
    assert module._sequence_report_is_success(
        {
            "status": status,
            "runtime_status": runtime_status,
            "monitor_status": monitor_status,
            "checks": {
                "blockers": [],
                "execution_blockers": [],
                "non_market_gaps": [],
                "engineering_gaps": [],
                "owner_intervention_required": False,
            },
        }
    )


def test_local_monitor_sequence_success_rejects_deployment_issue() -> None:
    module = _load_module()

    assert not module._sequence_report_is_success(
        {
            "status": "temporarily_unavailable_deployment_issue",
            "runtime_status": "temporarily_unavailable",
            "monitor_status": "deployment_issue",
            "checks": {
                "blockers": [],
                "execution_blockers": [],
                "non_market_gaps": [],
                "engineering_gaps": [],
                "owner_intervention_required": False,
            },
        }
    )


def test_local_monitor_sequence_classifies_deployment_returncodes_without_owner_decision() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {
            "status": "temporarily_unavailable_deployment_issue",
            "runtime_status": "temporarily_unavailable",
            "monitor_status": "deployment_issue",
            "owner_summary": {"owner_intervention_required": False},
            "checks": {
                "blockers": ["runtime_head_mismatch", "l1_snapshot_blocked"],
                "deployment_issue": True,
                "owner_intervention_required": False,
            },
        },
        "goal_progress": {
            "status": "temporarily_unavailable_deployment_issue",
            "runtime_status": "temporarily_unavailable",
            "monitor_status": "deployment_issue",
            "owner_summary": {"owner_intervention_required": False},
            "checks": {"blockers": [], "owner_intervention_required": False},
        },
        "completion_audit": {"status": "not_complete_waiting_for_market"},
    }
    steps = [
        {"name": "daily_check", "returncode": 2},
        {"name": "goal_progress", "returncode": 2},
        {"name": "completion_audit", "returncode": 0},
    ]

    execution_blockers = [
        f"{step['name']}:returncode:{step['returncode']}"
        for step in steps
        if int(step.get("returncode") or 0) not in (0,)
        and not module.monitor_step_returncode_is_refresh(
            step_name=step["name"],
            returncode=step["returncode"],
            artifact=artifacts[step["name"]],
        )
        and not module.monitor_step_returncode_is_deployment_issue(
            step_name=step["name"],
            returncode=step["returncode"],
            artifact=artifacts[step["name"]],
        )
    ]

    assert module._sequence_status(steps=steps, artifacts=artifacts) == (
        "temporarily_unavailable_deployment_issue"
    )
    assert execution_blockers == []
    assert module._sequence_owner_intervention_required(
        artifacts=artifacts,
        execution_blockers=execution_blockers,
        engineering_gaps=[],
    ) is False


def test_local_monitor_sequence_allows_runtime_activation_public_fact_refresh_returncode() -> None:
    module = _load_module()
    artifacts = {
        "daily_check": {
            "status": module.MONITOR_REFRESH_STATUS,
            "runtime_status": "waiting_for_market",
            "monitor_status": "needs_refresh",
            "owner_runtime_state": {
                "runtime_status": "waiting_for_market",
                "monitor_status": "needs_refresh",
                "owner_intervention_required": False,
                "monitor_refresh_needed": True,
            },
            "owner_runtime_issues": {"blockers": [], "non_market_gaps": []},
        },
        "goal_progress": {"status": "not_complete_waiting_for_market"},
        "completion_audit": {"status": "not_complete_waiting_for_market"},
        "four_candidate_runtime_activation_evidence": {
            "status": "runtime_activation_evidence_public_facts_unavailable",
            "runtime_artifact_ready": False,
            "checks": {"public_facts_artifact_fresh": False},
        },
        "binance_usdm_public_facts": {
            "status": "binance_usdm_public_facts_unavailable",
            "checks": {"public_facts_ready": False},
        },
    }
    steps = [
        {"name": "daily_check", "returncode": 2},
        {"name": "binance_usdm_public_facts", "returncode": 2},
        {"name": "four_candidate_runtime_activation_evidence", "returncode": 2},
        {"name": "completion_audit", "returncode": 0},
    ]

    execution_blockers = [
        f"{step['name']}:returncode:{step['returncode']}"
        for step in steps
        if int(step.get("returncode") or 0) not in (0,)
        and not module._step_returncode_is_allowed_monitor_refresh(step, artifacts)
        and not module._step_returncode_is_allowed_deployment_issue(step, artifacts)
    ]

    assert execution_blockers == []
    assert module._sequence_status(steps=steps, artifacts=artifacts) == (
        module.TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS
    )
    assert module._sequence_report_is_success(
        {
            "status": module.TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS,
            "runtime_status": "temporarily_unavailable",
            "monitor_status": "needs_refresh",
            "owner_runtime_issues": {"blockers": [], "non_market_gaps": []},
            "owner_runtime_state": {"owner_intervention_required": False},
        }
    ) is True


def test_local_monitor_sequence_owner_decision_reads_owner_state() -> None:
    module = _load_module()

    assert module._sequence_owner_intervention_required(
        artifacts={
            "runtime_safety_state": {
                "owner_state": {"owner_intervention_required": True},
                "checks": {},
            }
        },
        execution_blockers=[],
        engineering_gaps=[],
    ) is True


def test_local_monitor_sequence_monitor_owner_runtime_state_preserves_shape() -> None:
    module = _load_module()

    projection = module.monitor_owner_runtime_state(
        runtime_status="waiting_for_market",
        monitor_status="needs_refresh",
        owner_status="waiting_for_opportunity",
        owner_intervention_required=False,
        monitor_refresh_reasons=[
            "runtime_progress_cache_stale",
            "runtime_progress_cache_stale",
        ],
        waiting_for_market=True,
    )

    assert projection == {
        "runtime_status": "waiting_for_market",
        "monitor_status": "needs_refresh",
        "owner_status": "waiting_for_opportunity",
        "owner_intervention_required": False,
        "monitor_refresh_needed": True,
        "monitor_refresh_reasons": ["runtime_progress_cache_stale"],
        "waiting_for_market": True,
    }


def test_local_monitor_sequence_owner_runtime_issue_projection_uses_shared_helper() -> None:
    module = _load_module()

    projection = module.owner_runtime_issues_projection(
        blockers=["runtime_head_mismatch"],
        non_market_gaps=[
            {
                "source": "goal_progress",
                "requirement": "generated_before_daily_check",
                "missing_or_false": ["goal_progress:generated_before_daily_check"],
            }
        ],
        include_counts=True,
    )

    assert projection == {
        "blockers": ["runtime_head_mismatch"],
        "non_market_gaps": [
            {
                "source": "goal_progress",
                "requirement": "generated_before_daily_check",
                "missing_or_false": ["goal_progress:generated_before_daily_check"],
            }
        ],
        "blocker_count": 1,
        "non_market_gap_count": 1,
    }
    assert not hasattr(module, "_OwnerRuntimeIssueProjection")


def test_local_monitor_sequence_success_rejects_owner_decision() -> None:
    module = _load_module()

    assert not module._sequence_report_is_success(
        {
            "status": "waiting_for_market",
            "runtime_status": "waiting_for_market",
            "monitor_status": "fresh",
            "owner_runtime_state": {"owner_intervention_required": True},
            "checks": {
                "blockers": [],
                "execution_blockers": [],
                "non_market_gaps": [],
                "engineering_gaps": [],
                "owner_intervention_required": False,
            },
        }
    )
