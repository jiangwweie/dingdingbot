from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_portfolio_board.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_portfolio_board",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _safe() -> dict:
    return {
        "calls_exchange_write": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "places_order": False,
        "registry_authority_changed": False,
        "tier_policy_changed": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "mpg_member_live_scope_expanded": False,
        "l4_real_order_scope_expanded": False,
        "preview_or_replay_treated_as_live_signal": False,
    }


def _forward(event_count: int, completed: int = 0, tradable: int = 0, pending: int = 0):
    return {
        "event_count": event_count,
        "by_window": {
            "4h": {
                "completed": completed,
                "tradable_mfe_after_cost_count": tradable,
                "pending": pending,
                "unavailable": 0,
                "unknown": 0,
            }
        },
    }


def _row(
    group: str,
    *,
    would_enter: int = 0,
    positive: int = 0,
    no_action: int = 0,
    high_no_action: int = 0,
    missed_positive: int = 0,
    blockers: list[dict] | None = None,
) -> dict:
    return {
        "strategy_group_id": group,
        "would_enter_count": would_enter,
        "would_enter_forward_positive_count": positive,
        "no_action_count": no_action,
        "high_priority_no_action_count": high_no_action,
        "missed_no_action_forward_positive_count": missed_positive,
        "dominant_blocker_classes": blockers or [],
        "forward_outcome_summary": _forward(would_enter + no_action),
        "would_enter_forward_outcome_summary": _forward(
            would_enter,
            completed=would_enter,
            tradable=positive,
            pending=0,
        ),
    }


def _capture_audit(**overrides) -> dict:
    decisions = [
        ("BRF-001", "promote_review", "BRF-001_forward_outcome_and_requiredfacts_review"),
        ("BTPC-001", "revise", "BTPC-001_classifier_fact_source_revision_review"),
        ("LSR-001", "revise", "LSR-001_classifier_fact_source_revision_review"),
        ("MI-001", "identity_review", "MI-001_registry_identity_review"),
        ("CPM-RO-001", "identity_review", "CPM-RO-001_registry_identity_review"),
        ("MPG-001", "coverage_visibility_review", "MPG-001_no_action_visibility_and_routing_audit"),
        ("FBS-001", "coverage_visibility_review", "FBS-001_no_action_visibility_and_routing_audit"),
        ("SOR-001", "coverage_visibility_review", "SOR-001_no_action_visibility_and_routing_audit"),
        ("VCB-001", "keep_observing", "VCB-001_continue_observe_only"),
        ("RBR-001", "park", "park_until_material_new_edge_evidence"),
    ]
    base = {
        "status": "strategy_capture_gap_audit_ready",
        "owner_visibility_state": {
            "p0_state": "waiting_for_market",
            "signal_observation_state": "review_needed",
            "observation_active": True,
        },
        "runtime_baseline": {"status": "waiting_for_market", "blockers": []},
        "observation_recommendations": [
            {
                "strategy_group_id": group,
                "observation_recommendation": decision,
                "next_checkpoint": next_checkpoint,
            }
            for group, decision, next_checkpoint in decisions
        ],
        "strategy_expectation_rows": [
            _row("MPG-001"),
            _row("BRF-001", would_enter=1, no_action=168, high_no_action=168),
            _row(
                "BTPC-001",
                no_action=169,
                high_no_action=169,
                missed_positive=152,
                blockers=[{"key": "stale_data_or_signal", "count": 169}],
            ),
            _row("LSR-001", would_enter=2, positive=2, no_action=167),
            _row("MI-001", would_enter=23, positive=22, no_action=315),
            _row("CPM-RO-001", would_enter=18, positive=13, no_action=151),
            _row("FBS-001"),
            _row("SOR-001"),
            _row("VCB-001", would_enter=2, positive=2, no_action=167),
            _row("RBR-001", would_enter=6, positive=6, no_action=163),
        ],
        "safety_invariants": _safe(),
    }
    base.update(overrides)
    return base


def _tier_policy() -> dict:
    return {
        "status": "current_pilot_supplement",
        "current_strategy_groups": {
            "MPG-001": {"tier": "L4"},
            "BTPC-001": {"tier": "L2"},
            "FBS-001": {"tier": "L3"},
            "SOR-001": {"tier": "L3"},
        },
        "new_strategy_group_defaults": {
            "default_tier": "L1",
            "known_new_groups": {
                "BRF": "L1",
                "LSR": "L1",
                "RBR": "L1",
                "VCB": "L1",
            },
        },
        "safety_invariants": _safe(),
    }


def _registry() -> dict:
    return {
        "status": "current_pilot_baseline",
        "rows": [
            {"strategy_group_id": "MPG-001", "owner_label": "动量延续", "default_tier": "L4", "trial_eligible": True},
            {"strategy_group_id": "BRF-001", "owner_label": "熊市反弹失败", "default_tier": "L1", "trial_eligible": False},
            {"strategy_group_id": "BTPC-001", "owner_label": "熊市回抽延续", "default_tier": "L2", "trial_eligible": False},
            {"strategy_group_id": "LSR-001", "owner_label": "流动性扫盘", "default_tier": "L1", "trial_eligible": False},
            {"strategy_group_id": "VCB-001", "owner_label": "波动压缩突破", "default_tier": "L1", "trial_eligible": False},
            {"strategy_group_id": "RBR-001", "owner_label": "区间边界回归", "default_tier": "L1", "trial_eligible": False, "current_decision_ref": "park"},
            {"strategy_group_id": "TEQ-001", "owner_label": "类股权永续动量", "default_tier": "L2", "trial_eligible": False},
            {"strategy_group_id": "PMR-001", "owner_label": "贵金属制度覆盖", "default_tier": "L1", "trial_eligible": False},
        ],
        "safety_invariants": _safe(),
    }


def _deep_dive() -> dict:
    return {
        "status": "review_only_deep_dive_ready_for_owner_policy",
        "deep_dive_artifacts": [
            {"strategy_group_id": "MPG-001", "recommended_owner_policy": "accept_member_role_split", "owner_policy_type": "member_role_exit_decay_boundary"},
            {"strategy_group_id": "MI-001", "recommended_owner_policy": "open_formal_candidate_review_without_registry_admission", "owner_policy_type": "registry_identity_candidate_review"},
            {"strategy_group_id": "CPM-RO-001", "recommended_owner_policy": "keep_observation_asset_run_merge_review_before_independent_admission", "owner_policy_type": "registry_identity_merge_review"},
        ],
        "deep_dive_packets": [
            {"strategy_group_id": "MI-001", "recommended_owner_policy": "legacy_packet_should_not_drive_stage", "owner_policy_type": "legacy_packet"},
        ],
        "interaction": {"remote_interaction_count": 0},
        "safety_invariants": _safe(),
    }


def _quality_closure() -> dict:
    return {
        "status": "quality_closure_wave_ready",
        "priority_1_capture_closure": {
            "rows": [
                {
                    "strategy_group_id": "BRF-001",
                    "strategy_asset_current_decision": "promote_review_only",
                    "next_checkpoint": "BRF-001_forward_outcome_and_requiredfacts_review",
                },
                {
                    "strategy_group_id": "BTPC-001",
                    "strategy_asset_current_decision": "revise",
                    "next_checkpoint": "BTPC-001_classifier_fact_source_revision_review",
                },
                {
                    "strategy_group_id": "LSR-001",
                    "strategy_asset_current_decision": "revise",
                    "next_checkpoint": "LSR-001_classifier_fact_source_revision_review",
                },
            ]
        },
        "priority_3_identity_review": {
            "rows": [
                {
                    "strategy_group_id": "MI-001",
                    "strategy_asset_current_decision": "identity_review",
                    "next_checkpoint": "MI-001_registry_identity_review",
                },
                {
                    "strategy_group_id": "CPM-RO-001",
                    "strategy_asset_current_decision": "identity_review",
                    "next_checkpoint": "CPM-RO-001_registry_identity_review",
                },
            ]
        },
        "safety_invariants": _safe(),
    }


def test_portfolio_board_is_evidence_driven_and_review_only():
    module = _load_module()

    board_artifact = module.build_strategygroup_portfolio_board(
        capture_gap_audit=_capture_audit(),
        review_deep_dive=_deep_dive(),
        owner_policy_package={"status": "owner_policy_package_ready", "safety_invariants": _safe()},
        quality_closure_wave=_quality_closure(),
        tier_policy=_tier_policy(),
        registry_baseline=_registry(),
    )

    assert board_artifact["status"] == "portfolio_board_ready"
    assert board_artifact["runtime_posture"]["p0_state"] == "waiting_for_market"
    assert board_artifact["runtime_posture"]["p0_state_source"] == (
        "strategy_capture_gap_audit.owner_visibility_state.p0_state"
    )
    assert board_artifact["owner_progress_projection"]["p0_state_source"] == (
        "strategy_capture_gap_audit.owner_visibility_state.p0_state"
    )
    assert board_artifact["portfolio_summary"]["portfolio_row_count"] == 10
    assert board_artifact["portfolio_summary"]["registry_only_strategy_groups"] == [
        "PMR-001",
        "TEQ-001",
    ]
    by_group = {row["strategy_group_id"]: row for row in board_artifact["portfolio_rows"]}
    assert by_group["MPG-001"]["evidence_stage"] == "trial_waiting"
    assert by_group["MPG-001"]["capture_gap_recommendation_provenance"] == {
        "recommendation": "coverage_visibility_review",
        "next_checkpoint": "MPG-001_no_action_visibility_and_routing_audit",
        "source_role": "capture_gap_observation_provenance",
    }
    assert by_group["MI-001"]["execution_tier"] == "unknown"
    assert by_group["MI-001"]["evidence_stage"] == "identity_review"
    assert by_group["MI-001"]["strategy_review_checkpoint"] == "MI-001_registry_identity_review"
    assert "registry_identity_or_registry_row_missing" in by_group["MI-001"]["evidence_gaps"]
    assert by_group["CPM-RO-001"]["strategy_review_checkpoint"] == "CPM-RO-001_registry_identity_review"
    assert by_group["BTPC-001"]["evidence_stage"] == "revise"
    assert by_group["BRF-001"]["evidence_stage"] == "promote_review"
    assert by_group["RBR-001"]["evidence_stage"] == "park"
    assert by_group["RBR-001"]["owner_policy_required"] is False

    assert board_artifact["trial_candidate_pool"]["candidate_count"] == 5
    assert "actionable_now_count" not in board_artifact["trial_candidate_pool"]
    assert board_artifact["trial_candidate_pool"]["live_permission_change_count"] == 0
    for row in board_artifact["portfolio_rows"]:
        assert "actionable_now" not in row
        assert "actionable_now_reason" not in row
        assert row["live_permission_change"] is False
        assert row["does_not_authorize_live_execution"] is True
    for row in board_artifact["trial_candidate_pool"]["rows"]:
        assert "actionable_now" not in row
    assert "execution_intent_created" not in board_artifact["safety_invariants"]


def test_portfolio_board_identity_review_fallback_actions_are_review_artifacts():
    module = _load_module()

    board_artifact = module.build_strategygroup_portfolio_board(
        capture_gap_audit=_capture_audit(),
        review_deep_dive=_deep_dive(),
        owner_policy_package={
            "status": "owner_policy_package_ready",
            "safety_invariants": _safe(),
        },
        quality_closure_wave={
            "status": "quality_closure_wave_ready",
            "safety_invariants": _safe(),
        },
        tier_policy=_tier_policy(),
        registry_baseline=_registry(),
    )

    by_group = {row["strategy_group_id"]: row for row in board_artifact["portfolio_rows"]}
    assert by_group["MI-001"]["strategy_review_checkpoint"] == (
        "open_mi_identity_overlap_symbol_concentration_review"
    )
    assert by_group["CPM-RO-001"]["strategy_review_checkpoint"] == (
        "open_cpm_ro_semantic_source_merge_quality_review"
    )
    assert "packet" not in by_group["MI-001"]["strategy_review_checkpoint"]
    assert "packet" not in by_group["CPM-RO-001"]["strategy_review_checkpoint"]


def test_portfolio_board_does_not_use_capture_gap_decision_as_stage_authority():
    module = _load_module()

    board_artifact = module.build_strategygroup_portfolio_board(
        capture_gap_audit=_capture_audit(),
        review_deep_dive={"status": "missing", "safety_invariants": _safe()},
        owner_policy_package={"status": "owner_policy_package_ready", "safety_invariants": _safe()},
        quality_closure_wave={"status": "quality_closure_wave_ready", "safety_invariants": _safe()},
        tier_policy=_tier_policy(),
        registry_baseline=_registry(),
    )

    by_group = {row["strategy_group_id"]: row for row in board_artifact["portfolio_rows"]}
    assert by_group["BRF-001"]["capture_gap_recommendation_provenance"] == {
        "recommendation": "promote_review",
        "next_checkpoint": "BRF-001_forward_outcome_and_requiredfacts_review",
        "source_role": "capture_gap_observation_provenance",
    }
    assert by_group["BRF-001"]["evidence_stage"] != "promote_review"
    assert by_group["BRF-001"]["evidence_stage_reasons"] == [
        "no_decision_or_capture_evidence"
    ]


def test_portfolio_board_does_not_default_missing_p0_state_to_waiting_for_market():
    module = _load_module()
    capture = _capture_audit()
    capture.pop("owner_visibility_state", None)

    board_artifact = module.build_strategygroup_portfolio_board(
        capture_gap_audit=capture,
        review_deep_dive=_deep_dive(),
        owner_policy_package={
            "status": "owner_policy_package_ready",
            "safety_invariants": _safe(),
        },
        quality_closure_wave=_quality_closure(),
        tier_policy=_tier_policy(),
        registry_baseline=_registry(),
    )

    assert board_artifact["runtime_posture"]["p0_state"] == "unknown_runtime_state"
    assert board_artifact["runtime_posture"]["p0_state"] != "waiting_for_market"
    assert board_artifact["runtime_posture"]["p0_state_source"] == (
        "missing_capture_gap_owner_visibility_state_p0_state"
    )
    assert board_artifact["owner_progress_projection"]["p0_state"] == (
        "unknown_runtime_state"
    )


def test_portfolio_board_rejects_forbidden_source_effects():
    module = _load_module()
    audit = _capture_audit()
    audit["safety_invariants"]["calls_exchange_write"] = True

    try:
        module.build_strategygroup_portfolio_board(capture_gap_audit=audit)
    except ValueError as exc:
        assert "forbidden effects" in str(exc)
    else:
        raise AssertionError("expected forbidden source effect to fail")


def test_portfolio_board_cli_writes_outputs(tmp_path, capsys):
    module = _load_module()
    capture = tmp_path / "capture.json"
    tier = tmp_path / "tier.json"
    registry = tmp_path / "registry.json"
    deep = tmp_path / "deep.json"
    owner = tmp_path / "owner.json"
    quality = tmp_path / "quality.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    pool_md = tmp_path / "pool.md"
    capture.write_text(json.dumps(_capture_audit()), encoding="utf-8")
    tier.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    registry.write_text(json.dumps(_registry()), encoding="utf-8")
    deep.write_text(json.dumps(_deep_dive()), encoding="utf-8")
    owner.write_text(json.dumps({"status": "owner_policy_package_ready", "safety_invariants": _safe()}), encoding="utf-8")
    quality.write_text(json.dumps(_quality_closure()), encoding="utf-8")

    exit_code = module.main(
        [
            "--capture-gap-audit-json",
            str(capture),
            "--review-deep-dive-json",
            str(deep),
            "--owner-policy-package-json",
            str(owner),
            "--quality-closure-wave-json",
            str(quality),
            "--tier-policy-json",
            str(tier),
            "--registry-baseline-json",
            str(registry),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--output-trial-pool-md",
            str(pool_md),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    board_artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_payload["portfolio_row_count"] == 10
    assert stdout_payload["trial_candidate_count"] == 5
    assert board_artifact["portfolio_summary"]["portfolio_row_count"] == 10
    assert "StrategyGroup Portfolio Board v0" in output_md.read_text(encoding="utf-8")
    assert "StrategyGroup Trial Candidate Pool v0" in pool_md.read_text(encoding="utf-8")


def test_portfolio_board_cli_omitted_review_provenance_stays_missing(
    tmp_path, capsys
):
    module = _load_module()
    capture = tmp_path / "capture.json"
    tier = tmp_path / "tier.json"
    registry = tmp_path / "registry.json"
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    pool_md = tmp_path / "pool.md"
    capture.write_text(json.dumps(_capture_audit()), encoding="utf-8")
    tier.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    registry.write_text(json.dumps(_registry()), encoding="utf-8")

    exit_code = module.main(
        [
            "--capture-gap-audit-json",
            str(capture),
            "--tier-policy-json",
            str(tier),
            "--registry-baseline-json",
            str(registry),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--output-trial-pool-md",
            str(pool_md),
        ]
    )

    assert exit_code == 0
    capsys.readouterr()
    board_artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert board_artifact["source_status"]["review_deep_dive"] == "missing"
    assert board_artifact["source_status"]["owner_policy_package"] == "missing"
    assert board_artifact["source_status"]["quality_closure_wave"] == "missing"
    assert "review_deep_dive_missing" in board_artifact["source_status"]["source_gaps"]
    assert "owner_policy_package_missing" in board_artifact["source_status"]["source_gaps"]
    assert "quality_closure_wave_missing" in board_artifact["source_status"]["source_gaps"]


def test_portfolio_board_cli_requires_capture_gap_audit(tmp_path):
    module = _load_module()
    output_json = tmp_path / "portfolio.json"
    output_md = tmp_path / "portfolio.md"
    pool_md = tmp_path / "pool.md"

    try:
        module.main(
            [
                "--output-json",
                str(output_json),
                "--output-md",
                str(output_md),
                "--output-trial-pool-md",
                str(pool_md),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected missing capture gap audit to fail argparse")
