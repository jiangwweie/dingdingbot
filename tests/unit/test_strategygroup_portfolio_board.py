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
        "real_order_authority": False,
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
            "p0_5_observation_state": "review_needed",
            "observation_active": True,
        },
        "runtime_baseline": {"status": "waiting_for_market", "blockers": []},
        "decision_recommendations": [
            {
                "strategy_group_id": group,
                "decision": decision,
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
        "status": "review_only_deep_dive_ready_for_owner_decision",
        "deep_dive_packets": [
            {"strategy_group_id": "MPG-001", "recommended_owner_decision": "accept_member_role_split", "decision_type": "member_role_exit_decay_boundary"},
            {"strategy_group_id": "MI-001", "recommended_owner_decision": "open_formal_candidate_review_without_registry_admission", "decision_type": "registry_identity_candidate_review"},
            {"strategy_group_id": "CPM-RO-001", "recommended_owner_decision": "keep_observation_asset_run_merge_review_before_independent_admission", "decision_type": "registry_identity_merge_review"},
        ],
        "interaction": {"remote_interaction_count": 0},
        "safety_invariants": _safe(),
    }


def test_portfolio_board_is_evidence_driven_and_review_only():
    module = _load_module()

    packet = module.build_strategygroup_portfolio_board(
        capture_gap_audit=_capture_audit(),
        review_deep_dive=_deep_dive(),
        owner_decision_package={"status": "owner_decision_package_ready", "safety_invariants": _safe()},
        quality_closure_wave={"status": "quality_closure_wave_ready", "safety_invariants": _safe()},
        tier_policy=_tier_policy(),
        registry_baseline=_registry(),
    )

    assert packet["status"] == "portfolio_board_ready"
    assert packet["portfolio_summary"]["portfolio_row_count"] == 10
    assert packet["portfolio_summary"]["registry_only_strategy_groups"] == [
        "PMR-001",
        "TEQ-001",
    ]
    by_group = {row["strategy_group_id"]: row for row in packet["portfolio_rows"]}
    assert by_group["MPG-001"]["evidence_stage"] == "trial_waiting"
    assert by_group["MPG-001"]["audit_decision"] == "coverage_visibility_review"
    assert by_group["MI-001"]["execution_tier"] == "unknown"
    assert by_group["MI-001"]["evidence_stage"] == "identity_review"
    assert "registry_identity_or_registry_row_missing" in by_group["MI-001"]["evidence_gaps"]
    assert by_group["BTPC-001"]["evidence_stage"] == "revise"
    assert by_group["RBR-001"]["evidence_stage"] == "park"
    assert by_group["RBR-001"]["owner_policy_required"] is False

    assert packet["trial_candidate_pool"]["candidate_count"] == 5
    assert packet["trial_candidate_pool"]["actionable_now_count"] == 0
    assert packet["trial_candidate_pool"]["live_permission_change_count"] == 0
    for row in packet["portfolio_rows"]:
        assert row["actionable_now"] is False
        assert row["live_permission_change"] is False
        assert row["does_not_authorize_live_execution"] is True


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
    owner.write_text(json.dumps({"status": "owner_decision_package_ready", "safety_invariants": _safe()}), encoding="utf-8")
    quality.write_text(json.dumps({"status": "quality_closure_wave_ready", "safety_invariants": _safe()}), encoding="utf-8")

    exit_code = module.main(
        [
            "--capture-gap-audit-json",
            str(capture),
            "--review-deep-dive-json",
            str(deep),
            "--owner-decision-package-json",
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
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_payload["portfolio_row_count"] == 10
    assert stdout_payload["trial_candidate_count"] == 5
    assert packet["portfolio_summary"]["portfolio_row_count"] == 10
    assert "StrategyGroup Portfolio Board v0" in output_md.read_text(encoding="utf-8")
    assert "StrategyGroup Trial Candidate Pool v0" in pool_md.read_text(encoding="utf-8")
