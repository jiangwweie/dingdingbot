from __future__ import annotations

import json
import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_regime_role_coverage_map.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_regime_role_coverage_map",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _safe() -> dict:
    return {
        "real_order_authority": False,
        "actionable_now": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "order_created": False,
        "live_profile_changed": False,
        "tier_policy_changed": False,
        "strategy_parameters_changed": False,
        "registry_authority_changed": False,
        "server_files_mutated": False,
        "places_order": False,
    }


def _portfolio_row(
    group_id: str,
    *,
    owner_label: str,
    tier: str,
    stage: str,
    recent: int = 0,
    positive: int = 0,
    no_action: int = 0,
    blocker: str | None = None,
    trial_eligible: bool = False,
) -> dict:
    blockers = [{"key": blocker, "count": no_action or 1}] if blocker else []
    return {
        "strategy_group_id": group_id,
        "owner_label": owner_label,
        "execution_tier": tier,
        "evidence_stage": stage,
        "recent_opportunity_count": recent,
        "would_enter_forward_positive_count": positive,
        "no_action_count": no_action,
        "high_priority_no_action_count": no_action,
        "dominant_blocker_classes": blockers,
        "strategy_review_checkpoint": f"{group_id}_next",
        "trial_eligible": trial_eligible,
        "actionable_now": False,
        "live_permission_change": False,
        "cost_after_result_summary": {
            "4h": {"tradable_mfe_after_cost_count": positive},
            "12h": {"tradable_mfe_after_cost_count": positive},
        },
    }


def _portfolio_board() -> dict:
    return {
        "status": "portfolio_board_ready",
        "portfolio_summary": {
            "active_review_strategy_groups": [
                "MPG-001",
                "BRF-001",
                "BTPC-001",
                "LSR-001",
                "MI-001",
                "CPM-RO-001",
                "FBS-001",
                "SOR-001",
                "VCB-001",
                "RBR-001",
            ],
        },
        "trial_candidate_pool": {
            "candidate_count": 5,
            "trial_eligible_count": 1,
            "actionable_now_count": 0,
            "candidates": [
                {"strategy_group_id": "MPG-001", "pool_stage": "selected_live_lane_waiting_for_market"},
                {"strategy_group_id": "BRF-001", "pool_stage": "promote_review_candidate"},
                {"strategy_group_id": "LSR-001", "pool_stage": "rewrite_candidate_after_revision"},
                {"strategy_group_id": "MI-001", "pool_stage": "identity_candidate_review"},
                {"strategy_group_id": "CPM-RO-001", "pool_stage": "identity_candidate_review"},
            ],
        },
        "portfolio_rows": [
            _portfolio_row("MPG-001", owner_label="动量延续", tier="L4", stage="trial_waiting", trial_eligible=True),
            _portfolio_row("MI-001", owner_label="动量冲击", tier="unknown", stage="identity_review", recent=23, positive=22, no_action=315),
            _portfolio_row("BRF-001", owner_label="熊市反弹失败", tier="L1", stage="promote_review", recent=1, no_action=168, blocker="market_structure_not_confirmed"),
            _portfolio_row("BTPC-001", owner_label="熊市回抽延续", tier="L2", stage="revise", no_action=169, blocker="stale_data_or_signal"),
            _portfolio_row("LSR-001", owner_label="流动性扫盘", tier="L1", stage="revise", recent=2, positive=2, no_action=167),
            _portfolio_row("RBR-001", owner_label="区间边界回归", tier="L1", stage="park", recent=6, positive=6, no_action=163),
            _portfolio_row("VCB-001", owner_label="波动压缩突破", tier="L1", stage="observe", recent=2, positive=2, no_action=167, blocker="classifier_threshold_not_met"),
            _portfolio_row("FBS-001", owner_label="资金费率/基差压力", tier="L3", stage="coverage_visibility_review"),
            _portfolio_row("SOR-001", owner_label="开盘区间结构", tier="L3", stage="coverage_visibility_review"),
            _portfolio_row("CPM-RO-001", owner_label="CPM 回补观察", tier="unknown", stage="identity_review", recent=18, positive=13, no_action=151),
        ],
        "safety_invariants": _safe(),
    }


def _capture_gap_audit(field: str = "strategy_capture_gap_supported") -> dict:
    return {
        "status": "strategy_capture_gap_audit_ready",
        "official_server_time_utc": "2026-06-22T00:00:00Z",
        "audit_conclusion": {field: True},
        "owner_visibility_state": {
            "p0_state": "waiting_for_market",
            "signal_observation_state": "review_needed",
        },
        "runtime_baseline": {"status": "waiting_for_market"},
        "safety_invariants": _safe(),
    }


def _registry() -> dict:
    return {
        "status": "current_pilot_baseline",
        "rows": [
            {"strategy_group_id": "MPG-001", "owner_label": "动量延续", "default_tier": "L4"},
            {"strategy_group_id": "TEQ-001", "owner_label": "类股权永续动量", "default_tier": "L2"},
            {"strategy_group_id": "PMR-001", "owner_label": "贵金属制度覆盖", "default_tier": "L1"},
            {"strategy_group_id": "BRF-001", "owner_label": "熊市反弹失败", "default_tier": "L1"},
            {"strategy_group_id": "BTPC-001", "owner_label": "熊市回抽延续", "default_tier": "L2"},
        ],
        "safety_invariants": _safe(),
    }


def _tier_policy() -> dict:
    return {
        "status": "current_pilot_supplement",
        "current_strategy_groups": {
            "MPG-001": {"tier": "L4"},
            "BTPC-001": {"tier": "L2"},
            "FBS-001": {"tier": "L3"},
            "SOR-001": {"tier": "L3"},
            "TEQ-001": {"tier": "L2"},
            "PMR-001": {"tier": "L1"},
        },
        "safety_invariants": _safe(),
    }


def test_regime_role_coverage_map_has_required_shape_and_safety():
    module = _load_module()

    artifact = module.build_regime_role_coverage_map(
        portfolio_board=_portfolio_board(),
        trial_candidate_pool_md="| `MPG-001` | selected |\n",
        capture_gap_audit=_capture_gap_audit(),
        registry_baseline=_registry(),
        tier_policy=_tier_policy(),
        required_facts_map_md="BTPC-001 derivatives funding OI RequiredFacts",
        strategy_asset_state_source={
            "status": "strategy_asset_state_ready",
            "safety_invariants": _safe(),
        },
        git_log_oneline_8=["abc123 commit"],
        git_status_short=[
            "?? scripts/build_strategygroup_regime_role_coverage_map.py",
            "?? live-config.env",
        ],
        generated_at_utc="2026-06-22T00:00:00Z",
    )

    assert artifact["schema"] == "brc.strategygroup_regime_role_coverage_map.v1"
    assert artifact["status"] == "regime_role_coverage_map_ready"
    assert artifact["scope"] == "local_review_only"
    assert len(artifact["strategy_group_rows"]) == 10
    assert len(artifact["role_buckets"]) == 10
    assert all(value is False for value in artifact["safety_invariants"].values())
    assert "actionable_now" not in artifact["safety_invariants"]
    assert "real_order_authority" not in artifact["safety_invariants"]

    by_group = {row["strategy_group_id"]: row for row in artifact["strategy_group_rows"]}
    assert by_group["BTPC-001"]["gap_classes"] == ["classifier_gap", "fact_source_gap"]
    assert by_group["RBR-001"]["research_escalation"] == "bounded_research_recommended"
    assert by_group["MI-001"]["trial_pool_status"] == "identity_candidate_review"
    assert by_group["CPM-RO-001"]["side_semantics"].startswith("trend pullback")
    assert all("actionable_now" not in row for row in artifact["strategy_group_rows"])
    assert "actionable_now_count" not in artifact["trial_pool_implications"]

    by_bucket = {row["bucket"]: row for row in artifact["role_buckets"]}
    assert "BRF-001" in by_bucket["bear_rally_failure_short"]["strategy_groups"]
    assert "BTPC-001" in by_bucket["bear_pullback_continuation_short"]["strategy_groups"]
    assert by_bucket["derivatives_stress"]["strategy_research_need"] == "research_required_before_trial"
    assert by_bucket["range_reversion"]["strategy_research_need"] == "bounded_research_recommended"

    gap_summary = artifact["gap_summary"]
    assert "RBR-001" in gap_summary["by_gap_class"]["true_research_gap"]
    assert gap_summary["fact_source_gap_count"] >= 2
    assert artifact["registry_only_notes"][0]["strategy_group_id"] == "PMR-001"
    assert artifact["source_status"]["required_inputs"]["required_facts_map_md"]["mentions_derivatives"] is True
    assert artifact["market_regime_assessment"]["strategy_capture_gap"] is True
    assert (
        artifact["market_regime_assessment"]["strategy_capture_gap_evidence_field"]
        == "audit_conclusion.strategy_capture_gap_supported"
    )

    active_contract = artifact["active_review_group_contract"]
    assert active_contract["source"] == "portfolio_board.portfolio_summary.active_review_strategy_groups"
    assert active_contract["missing_in_specs"] == []
    assert active_contract["extra_in_specs"] == []

    git_status = artifact["source_status"]["required_inputs"]["git_status_short"]
    assert git_status["dirty_count"] == 2
    assert git_status["task_related_count"] == 1
    assert git_status["full_status_omitted"] is True
    assert "lines" not in git_status
    assert "live-config.env" not in json.dumps(git_status, ensure_ascii=False)


def test_regime_role_coverage_map_keeps_legacy_capture_gap_detected_compatibility():
    module = _load_module()

    artifact = module.build_regime_role_coverage_map(
        portfolio_board=_portfolio_board(),
        trial_candidate_pool_md="| `MPG-001` | selected |\n",
        capture_gap_audit=_capture_gap_audit("strategy_capture_gap_detected"),
        registry_baseline=_registry(),
        tier_policy=_tier_policy(),
        required_facts_map_md="BTPC-001 derivatives",
        git_log_oneline_8=[],
        git_status_short=[],
    )

    assert artifact["market_regime_assessment"]["strategy_capture_gap"] is True
    assert (
        artifact["market_regime_assessment"]["strategy_capture_gap_evidence_field"]
        == "audit_conclusion.strategy_capture_gap_detected"
    )


def test_regime_role_coverage_map_reports_portfolio_board_spec_mismatch():
    module = _load_module()
    portfolio = _portfolio_board()
    portfolio["portfolio_summary"]["active_review_strategy_groups"] = [
        "MPG-001",
        "NEW-001",
    ]

    artifact = module.build_regime_role_coverage_map(
        portfolio_board=portfolio,
        trial_candidate_pool_md="| `MPG-001` | selected |\n",
        capture_gap_audit=_capture_gap_audit(),
        registry_baseline=_registry(),
        tier_policy=_tier_policy(),
        required_facts_map_md="BTPC-001 derivatives",
        git_log_oneline_8=[],
        git_status_short=[],
    )

    active_contract = artifact["active_review_group_contract"]
    assert active_contract["known_active_groups"] == ["MPG-001"]
    assert active_contract["missing_in_specs"] == ["NEW-001"]
    assert "MI-001" in active_contract["extra_in_specs"]
    assert active_contract["contract_status"] == "spec_mismatch_reported"
    assert [row["strategy_group_id"] for row in artifact["strategy_group_rows"]] == [
        "MPG-001"
    ]


def test_regime_role_coverage_map_rejects_missing_portfolio_active_groups():
    module = _load_module()
    portfolio = _portfolio_board()
    del portfolio["portfolio_summary"]["active_review_strategy_groups"]

    try:
        module.build_regime_role_coverage_map(
            portfolio_board=portfolio,
            trial_candidate_pool_md="| `MPG-001` | selected |\n",
            capture_gap_audit=_capture_gap_audit(),
            registry_baseline=_registry(),
            tier_policy=_tier_policy(),
            required_facts_map_md="BTPC-001 derivatives",
            git_log_oneline_8=[],
            git_status_short=[],
        )
    except ValueError as exc:
        assert "active_review_strategy_groups must be supplied" in str(exc)
    else:
        raise AssertionError("missing active review groups should fail closed")


def test_regime_role_coverage_map_rejects_authority_mutation():
    module = _load_module()
    portfolio = _portfolio_board()
    portfolio["safety_invariants"]["real_order_authority"] = True
    portfolio["safety_invariants"]["actionable_now"] = True

    try:
        module.build_regime_role_coverage_map(
            portfolio_board=portfolio,
            trial_candidate_pool_md="| `MPG-001` | selected |\n",
            capture_gap_audit=_capture_gap_audit(),
            registry_baseline=_registry(),
            tier_policy=_tier_policy(),
            required_facts_map_md="BTPC-001 derivatives",
            git_log_oneline_8=[],
            git_status_short=[],
        )
    except ValueError as exc:
        assert "legacy_authority_mirror_present:actionable_now" in str(exc)
    else:
        raise AssertionError("unsafe artifact should be rejected")

    portfolio["safety_invariants"]["actionable_now"] = False
    try:
        module.build_regime_role_coverage_map(
            portfolio_board=portfolio,
            trial_candidate_pool_md="| `MPG-001` | selected |\n",
            capture_gap_audit=_capture_gap_audit(),
            registry_baseline=_registry(),
            tier_policy=_tier_policy(),
            required_facts_map_md="BTPC-001 derivatives",
            git_log_oneline_8=[],
            git_status_short=[],
        )
    except ValueError as exc:
        assert "legacy_authority_mirror_present:real_order_authority" in str(exc)
    else:
        raise AssertionError("unsafe artifact should be rejected")


def test_regime_role_coverage_map_cli_uses_explicit_generated_inputs(
    tmp_path: Path, capsys
):
    module = _load_module()
    portfolio = tmp_path / "portfolio.json"
    trial_pool = tmp_path / "trial-pool.md"
    capture = tmp_path / "capture.json"
    registry = tmp_path / "registry.json"
    tier = tmp_path / "tier.json"
    facts = tmp_path / "facts.md"
    output_json = tmp_path / "regime-role.json"
    output_md = tmp_path / "regime-role.md"
    portfolio.write_text(json.dumps(_portfolio_board()), encoding="utf-8")
    trial_pool.write_text("| `MPG-001` | selected |\n", encoding="utf-8")
    capture.write_text(json.dumps(_capture_gap_audit()), encoding="utf-8")
    registry.write_text(json.dumps(_registry()), encoding="utf-8")
    tier.write_text(json.dumps(_tier_policy()), encoding="utf-8")
    facts.write_text("BTPC-001 derivatives", encoding="utf-8")

    exit_code = module.main(
        [
            "--portfolio-board-json",
            str(portfolio),
            "--trial-candidate-pool-md",
            str(trial_pool),
            "--capture-gap-audit-json",
            str(capture),
            "--registry-baseline-json",
            str(registry),
            "--tier-policy-json",
            str(tier),
            "--required-facts-map-md",
            str(facts),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ]
    )

    assert exit_code == 0
    capsys.readouterr()
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    required = artifact["source_status"]["required_inputs"]
    optional = artifact["source_status"]["optional_inputs"]
    assert required["portfolio_board_json"]["path"] == "caller_supplied"
    assert required["trial_candidate_pool_md"]["path"] == "caller_supplied"
    assert required["capture_gap_audit_json"]["path"] == "caller_supplied"
    assert optional["goal_progress_json_status"] is None
    assert optional["local_monitor_sequence_json_status"] is None
    assert optional["strategy_asset_state_json_status"] is None
    assert "stress/squeeze packets" not in markdown
    assert "stress/squeeze evidence" in markdown


def test_regime_role_coverage_map_cli_requires_generated_inputs(tmp_path: Path):
    module = _load_module()
    output_json = tmp_path / "regime-role.json"
    output_md = tmp_path / "regime-role.md"

    try:
        module.main(
            [
                "--output-json",
                str(output_json),
                "--output-md",
                str(output_md),
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected missing generated inputs to fail argparse")
