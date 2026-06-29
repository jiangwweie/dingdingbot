from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_quality_closure_wave.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_quality_closure_wave",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _capture_gap_audit() -> dict:
    return {
        "status": "strategy_capture_gap_audit_ready",
        "system_observation_summary": {
            "would_enter_count": 52,
            "high_priority_no_action_count": 671,
        },
        "strategy_expectation_rows": [
            {
                "strategy_group_id": "BTPC-001",
                "would_enter_count": 0,
                "no_action_count": 169,
                "high_priority_no_action_count": 169,
                "would_enter_forward_positive_count": 0,
                "missed_no_action_forward_positive_count": 152,
                "dominant_blocker_classes": [
                    {"key": "stale_data_or_signal", "count": 169}
                ],
            },
            {
                "strategy_group_id": "LSR-001",
                "would_enter_count": 2,
                "no_action_count": 167,
                "high_priority_no_action_count": 167,
                "would_enter_forward_positive_count": 2,
                "missed_no_action_forward_positive_count": 0,
                "dominant_blocker_classes": [
                    {"key": "classifier_or_strategy_rewrite", "count": 167}
                ],
            },
            {
                "strategy_group_id": "BRF-001",
                "would_enter_count": 1,
                "no_action_count": 168,
                "high_priority_no_action_count": 168,
                "would_enter_forward_positive_count": 0,
                "missed_no_action_forward_positive_count": 136,
                "dominant_blocker_classes": [
                    {"key": "market_structure_not_confirmed", "count": 85}
                ],
            },
            {
                "strategy_group_id": "MI-001",
                "would_enter_count": 23,
                "no_action_count": 315,
                "high_priority_no_action_count": 0,
                "would_enter_forward_positive_count": 22,
                "missed_no_action_forward_positive_count": 0,
            },
            {
                "strategy_group_id": "CPM-RO-001",
                "would_enter_count": 18,
                "no_action_count": 151,
                "high_priority_no_action_count": 0,
                "would_enter_forward_positive_count": 13,
                "missed_no_action_forward_positive_count": 0,
            },
            {
                "strategy_group_id": "MPG-001",
                "would_enter_count": 0,
                "no_action_count": 0,
                "high_priority_no_action_count": 0,
                "would_enter_forward_positive_count": 0,
                "missed_no_action_forward_positive_count": 0,
            },
            {
                "strategy_group_id": "VCB-001",
                "would_enter_count": 2,
                "no_action_count": 167,
                "high_priority_no_action_count": 167,
                "would_enter_forward_positive_count": 2,
                "missed_no_action_forward_positive_count": 135,
                "dominant_blocker_classes": [
                    {"key": "classifier_threshold_not_met", "count": 162}
                ],
            },
            {
                "strategy_group_id": "RBR-001",
                "would_enter_count": 6,
                "no_action_count": 163,
                "high_priority_no_action_count": 0,
                "would_enter_forward_positive_count": 6,
                "missed_no_action_forward_positive_count": 0,
                "dominant_blocker_classes": [
                    {"key": "observe_only_would_enter", "count": 6}
                ],
            },
        ],
        "priority_line_closure": {
            "phase2_priority_strategy_lines": [
                {
                    "strategy_group_id": "BTPC-001",
                    "would_enter_count": 0,
                    "high_priority_no_action_count": 169,
                    "would_enter_forward_positive_count": 0,
                    "missed_no_action_forward_positive_count": 152,
                },
                {
                    "strategy_group_id": "LSR-001",
                    "would_enter_count": 2,
                    "high_priority_no_action_count": 167,
                    "would_enter_forward_positive_count": 2,
                    "missed_no_action_forward_positive_count": 0,
                },
                {
                    "strategy_group_id": "BRF-001",
                    "would_enter_count": 1,
                    "high_priority_no_action_count": 168,
                    "would_enter_forward_positive_count": 0,
                    "missed_no_action_forward_positive_count": 136,
                },
            ],
            "phase3_registry_identity_review": [
                {
                    "strategy_group_id": "MI-001",
                    "would_enter_count": 23,
                    "would_enter_forward_positive_count": 22,
                },
                {
                    "strategy_group_id": "CPM-RO-001",
                    "would_enter_count": 18,
                    "would_enter_forward_positive_count": 13,
                },
            ],
            "phase4_visibility_review": [
                {"strategy_group_id": "MPG-001", "would_enter_count": 0},
                {
                    "strategy_group_id": "VCB-001",
                    "would_enter_count": 2,
                    "would_enter_forward_positive_count": 2,
                },
                {
                    "strategy_group_id": "RBR-001",
                    "would_enter_count": 6,
                    "would_enter_forward_positive_count": 6,
                },
            ],
        },
    }


def _strategy_asset_state_source() -> dict:
    return _with_strategy_asset_state({
        "status": "strategy_asset_state_ready",
        "source_rows": [
            {
                "strategy_group_id": "BRF-001",
                "tier": "L1",
                "decision": "promote",
                "required_next_evidence": "promotion_evidence_review_only",
                "next_checkpoint": "BRF-001_forward_outcome_and_requiredfacts_review",
            },
            {
                "strategy_group_id": "BTPC-001",
                "tier": "L2",
                "decision": "revise",
                "required_next_evidence": "classifier_fact_source_revision_review",
                "next_checkpoint": "BTPC-001_classifier_fact_source_revision_review",
            },
            {
                "strategy_group_id": "LSR-001",
                "tier": "L1",
                "decision": "revise",
                "required_next_evidence": "classifier_fact_source_revision_review",
                "next_checkpoint": "LSR-001_classifier_fact_source_revision_review",
            },
            {
                "strategy_group_id": "MI-001",
                "tier": "unknown",
                "decision": "revise",
                "required_next_evidence": "registry_identity_classification",
                "next_checkpoint": "MI-001_registry_identity_review",
            },
            {
                "strategy_group_id": "CPM-RO-001",
                "tier": "unknown",
                "decision": "revise",
                "required_next_evidence": "registry_identity_classification",
                "next_checkpoint": "CPM-RO-001_registry_identity_review",
            },
            {
                "strategy_group_id": "MPG-001",
                "tier": "L4",
                "decision": "keep_observing",
                "required_next_evidence": "no_action_visibility_and_routing_summary",
                "next_checkpoint": "MPG-001_no_action_visibility_and_routing_audit",
            },
            {
                "strategy_group_id": "VCB-001",
                "tier": "L1",
                "decision": "keep_observing",
                "required_next_evidence": "true_false_breakout_classifier_review",
                "next_checkpoint": "VCB-001_true_false_breakout_classifier_review",
            },
            {
                "strategy_group_id": "RBR-001",
                "tier": "L1",
                "decision": "park",
                "required_next_evidence": "material_new_edge_evidence_before_reactivation",
                "next_checkpoint": "park_until_material_new_edge_evidence",
            },
        ],
    })


def _with_strategy_asset_state(source: dict) -> dict:
    source["strategy_asset_state"] = {
        "status": "strategy_asset_state_ready",
        "asset_rows": [
            {
                "strategy_group_id": row["strategy_group_id"],
                "current_tier": row.get("tier", "unknown"),
                "current_decision": row["decision"],
                "promotion_target": row.get("required_next_evidence", "not_applicable"),
                "required_next_evidence": row.get("required_next_evidence", ""),
                "next_checkpoint": row.get("next_checkpoint", ""),
            }
            for row in source["source_rows"]
        ],
    }
    return source


def _strategy_asset_state_source_with_conflict() -> dict:
    source = _strategy_asset_state_source()
    for row in source["strategy_asset_state"]["asset_rows"]:
        if row["strategy_group_id"] == "BTPC-001":
            row["current_decision"] = "park"
            row["next_checkpoint"] = "strategy_asset_state_checkpoint"
    return source


def _strategy_asset_state_source_with_missing_decision() -> dict:
    source = _strategy_asset_state_source()
    for row in source["strategy_asset_state"]["asset_rows"]:
        if row["strategy_group_id"] == "BTPC-001":
            row.pop("current_decision", None)
            row["next_checkpoint"] = "missing_decision_checkpoint"
    return source


def _registry() -> dict:
    return {
        "status": "ready",
        "rows": [
            {
                "strategy_group_id": "MPG-001",
                "owner_label": "动量延续",
                "default_tier": "L4",
                "edge_thesis": "Capture clean momentum continuation.",
                "regime_fit": "Directional momentum.",
                "trade_logic": "Long-only continuation.",
                "required_next_evidence": "first live outcome",
                "risk_gaps": {
                    "strategy_quality_risk": {
                        "items": ["false breakout"],
                        "owner_can_accept": True,
                    }
                },
            },
            {
                "strategy_group_id": "BRF-001",
                "owner_label": "熊市反弹失败",
                "default_tier": "L1",
                "edge_thesis": "Capture bear rally failure.",
                "regime_fit": "Bear rally rejection.",
                "trade_logic": "Short-only review.",
                "required_next_evidence": "rally context review",
                "risk_gaps": {},
            },
            {
                "strategy_group_id": "BTPC-001",
                "owner_label": "熊市回抽延续",
                "default_tier": "L2",
                "edge_thesis": "Capture bear pullback continuation.",
                "regime_fit": "Weak rally in downtrend.",
                "trade_logic": "Short-only shadow.",
                "required_next_evidence": "fact-source review",
                "risk_gaps": {},
            },
            {
                "strategy_group_id": "LSR-001",
                "owner_label": "流动性扫盘",
                "default_tier": "L1",
                "edge_thesis": "Capture side-specific revival.",
                "regime_fit": "Range sweep.",
                "trade_logic": "Observe-only.",
                "required_next_evidence": "rewrite review",
                "risk_gaps": {},
            },
            {
                "strategy_group_id": "VCB-001",
                "owner_label": "波动压缩突破",
                "default_tier": "L1",
                "edge_thesis": "Capture compression breakout.",
                "regime_fit": "Volatility compression breakout.",
                "trade_logic": "Observe-only breakout review.",
                "required_next_evidence": "breakout classifier review",
                "risk_gaps": {},
            },
            {
                "strategy_group_id": "RBR-001",
                "owner_label": "区间边界回归",
                "default_tier": "L1",
                "edge_thesis": "Range-boundary vocabulary.",
                "regime_fit": "Range rejection.",
                "trade_logic": "Parked vocabulary.",
                "required_next_evidence": "material new edge evidence",
                "risk_gaps": {},
            },
            {
                "strategy_group_id": "FBS-001",
                "owner_label": "资金费率压力",
                "default_tier": "L3",
                "edge_thesis": "Derivative stress.",
                "regime_fit": "Funding pressure.",
                "trade_logic": "Observe-only.",
                "required_next_evidence": "derivatives review",
                "risk_gaps": {},
            },
            {
                "strategy_group_id": "SOR-001",
                "owner_label": "开盘区间结构",
                "default_tier": "L3",
                "edge_thesis": "Session structure.",
                "regime_fit": "Opening range.",
                "trade_logic": "Observe-only.",
                "required_next_evidence": "session review",
                "risk_gaps": {},
            },
            {
                "strategy_group_id": "TEQ-001",
                "owner_label": "类股权永续动量",
                "default_tier": "L2",
                "edge_thesis": "Theme momentum.",
                "regime_fit": "Equity-like perpetual momentum.",
                "trade_logic": "Shadow review.",
                "required_next_evidence": "theme review",
                "risk_gaps": {},
            },
        ],
    }


def _tier_policy() -> dict:
    return {
        "current_strategy_groups": {
            "MPG-001": {"tier": "L4"},
            "BTPC-001": {"tier": "L2"},
        },
        "new_strategy_group_defaults": {
            "known_new_groups": {"BRF": "L1", "LSR": "L1"}
        },
    }


def _mpg_replay_corpus() -> dict:
    return {
        "replay_samples": [
            {
                "fixture_case": "trend_continuation",
                "blocker_class": "none",
                "expected_owner_state": "processing",
            },
            {
                "fixture_case": "fast_reversal",
                "blocker_class": "review_only_warning",
                "expected_owner_state": "processing",
            },
        ]
    }


def test_quality_closure_wave_builds_priority_artifacts_and_owner_policy_items():
    module = _load_module()

    artifact = module.build_quality_closure_wave(
        capture_gap_audit=_capture_gap_audit(),
        strategy_asset_state_source=_strategy_asset_state_source(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        mpg_replay_corpus=_mpg_replay_corpus(),
    )

    assert artifact["status"] == "quality_closure_wave_ready"
    assert artifact["priority_1_capture_closure"]["status"] == "ready_for_owner_review"
    priority_rows = {
        row["strategy_group_id"]: row
        for row in artifact["priority_1_capture_closure"]["rows"]
    }
    assert priority_rows["BTPC-001"]["strategy_asset_current_decision"] == "revise"
    assert "decision_source" not in priority_rows["BTPC-001"]
    assert "ledger_decision" not in priority_rows["BTPC-001"]
    assert priority_rows["BTPC-001"]["missed_no_action_forward_positive_count"] == 152
    assert priority_rows["LSR-001"]["would_enter_forward_positive_count"] == 2
    assert priority_rows["BRF-001"]["owner_policy_confirmation_after_review"] is True
    assert "owner_policy_confirmation_after_packet" not in priority_rows["BRF-001"]
    assert "packet" not in artifact["closed_engineering_problem"]

    wave_1 = artifact["wave_1_strategy_explainer"]
    assert wave_1["status"] == "ready"
    assert wave_1["missing_required_policy_items"] == []
    wave_1_policy_items = {row["strategy_group_id"]: row for row in wave_1["policy_items"]}
    for group in (
        "MPG-001",
        "BTPC-001",
        "LSR-001",
        "BRF-001",
        "MI-001",
        "CPM-RO-001",
        "FBS-001",
        "SOR-001",
        "VCB-001",
        "TEQ-001",
    ):
        assert group in wave_1_policy_items
        assert "actionable_now" not in wave_1_policy_items[group]
        assert wave_1_policy_items[group]["live_permission_change_recommended_now"] is False
        assert wave_1_policy_items[group]["owner_policy_review_scope"]
        assert wave_1_policy_items[group]["strategy_review_checkpoint"]

    policy_items = {
        row["strategy_group_id"]: row
        for row in artifact["priority_2_owner_policy_items_v1"]["policy_items"]
    }
    assert policy_items["MPG-001"]["owner_label"] == "动量延续"
    assert "actionable_now" not in policy_items["MPG-001"]
    assert policy_items["BRF-001"]["live_permission_change_recommended_now"] is False


def test_quality_closure_wave_uses_strategy_asset_state_before_injected_legacy_rows():
    module = _load_module()

    artifact = module.build_quality_closure_wave(
        capture_gap_audit=_capture_gap_audit(),
        strategy_asset_state_source=_strategy_asset_state_source_with_conflict(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        mpg_replay_corpus=_mpg_replay_corpus(),
    )

    assert artifact["strategy_asset_state_source"] == {
        "source": "strategy_asset_state.asset_rows",
        "row_count": 8,
        "missing_current_decision_count": 0,
    }
    priority_rows = {
        row["strategy_group_id"]: row
        for row in artifact["priority_1_capture_closure"]["rows"]
    }
    assert priority_rows["BTPC-001"]["strategy_asset_current_decision"] == "park"
    assert "ledger_decision" not in priority_rows["BTPC-001"]
    assert "decision" not in priority_rows["BTPC-001"]
    assert priority_rows["BTPC-001"]["next_checkpoint"] == "strategy_asset_state_checkpoint"


def test_quality_closure_wave_does_not_default_missing_strategy_asset_decision():
    module = _load_module()

    artifact = module.build_quality_closure_wave(
        capture_gap_audit=_capture_gap_audit(),
        strategy_asset_state_source=_strategy_asset_state_source_with_missing_decision(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        mpg_replay_corpus=_mpg_replay_corpus(),
    )

    assert artifact["strategy_asset_state_source"] == {
        "source": "strategy_asset_state.asset_rows",
        "row_count": 8,
        "missing_current_decision_count": 1,
    }
    priority_rows = {
        row["strategy_group_id"]: row
        for row in artifact["priority_1_capture_closure"]["rows"]
    }
    assert priority_rows["BTPC-001"]["strategy_asset_current_decision"] == "unknown"
    assert priority_rows["BTPC-001"]["strategy_asset_current_decision"] != "keep_observing"
    assert "ledger_decision" not in priority_rows["BTPC-001"]
    owner_policy_items = {
        row["strategy_group_id"]: row
        for row in artifact["priority_2_owner_policy_items_v1"]["policy_items"]
    }
    assert owner_policy_items["BTPC-001"]["review_recommendation"] == "unknown"
    wave_2_rows = {
        row["strategy_group_id"]: row
        for row in artifact["wave_2_capture_quality_closure"]["rows"]
    }
    assert wave_2_rows["BTPC-001"]["review_outcome"] == "revise"
    assert wave_2_rows["BTPC-001"]["strategy_asset_current_decision"] == "unknown"
    assert wave_2_rows["BTPC-001"]["strategy_asset_current_decision"] != "revise"
    forward_rows = {
        row["strategy_group_id"]: row
        for row in artifact["priority_5_forward_outcome_no_action_ledger_extension"]["rows"]
    }
    assert forward_rows["BTPC-001"]["strategy_asset_current_decision"] == "unknown"
    assert forward_rows["BTPC-001"]["strategy_asset_current_decision"] != "keep_observing"
    assert "ledger_decision" not in forward_rows["BTPC-001"]


def test_quality_closure_wave_fails_closed_without_strategy_asset_state():
    module = _load_module()
    strategy_asset_state_source = _strategy_asset_state_source()
    strategy_asset_state_source.pop("strategy_asset_state")

    artifact = module.build_quality_closure_wave(
        capture_gap_audit=_capture_gap_audit(),
        strategy_asset_state_source=strategy_asset_state_source,
        registry=_registry(),
        tier_policy=_tier_policy(),
        mpg_replay_corpus=_mpg_replay_corpus(),
    )

    assert artifact["strategy_asset_state_source"] == {
        "source": "missing_strategy_asset_state",
        "row_count": 0,
        "missing_current_decision_count": 0,
    }
    priority_rows = {
        row["strategy_group_id"]: row
        for row in artifact["priority_1_capture_closure"]["rows"]
    }
    assert priority_rows["BTPC-001"]["strategy_asset_current_decision"] == "unknown"
    assert "ledger_decision" not in priority_rows["BTPC-001"]
    owner_policy_items = {
        row["strategy_group_id"]: row
        for row in artifact["priority_2_owner_policy_items_v1"]["policy_items"]
    }
    assert owner_policy_items["BTPC-001"]["review_recommendation"] == "unknown"
    identity_rows = {
        row["strategy_group_id"]: row
        for row in artifact["priority_3_identity_review"]["rows"]
    }
    assert identity_rows["MI-001"]["strategy_asset_current_decision"] == "unknown"
    assert identity_rows["MI-001"]["strategy_asset_current_decision"] != "revise"
    assert "ledger_decision" not in identity_rows["MI-001"]
    forward_rows = {
        row["strategy_group_id"]: row
        for row in artifact["priority_5_forward_outcome_no_action_ledger_extension"]["rows"]
    }
    assert forward_rows["BTPC-001"]["strategy_asset_current_decision"] == "unknown"
    assert forward_rows["BTPC-001"]["strategy_asset_current_decision"] != "keep_observing"
    assert "ledger_decision" not in forward_rows["BTPC-001"]


def test_quality_closure_wave_keeps_identity_and_mpg_member_review_policy_only():
    module = _load_module()

    artifact = module.build_quality_closure_wave(
        capture_gap_audit=_capture_gap_audit(),
        strategy_asset_state_source=_strategy_asset_state_source(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        mpg_replay_corpus=_mpg_replay_corpus(),
    )

    identity = {
        row["strategy_group_id"]: row
        for row in artifact["priority_3_identity_review"]["rows"]
    }
    assert identity["MI-001"]["would_enter_count"] == 23
    assert identity["MI-001"]["owner_policy_confirmation_required"] is True
    assert identity["MI-001"]["system_recommendation"] == (
        "prepare_registry_identity_review_no_tier_change"
    )
    assert "packet_only" not in identity["MI-001"]["system_recommendation"]
    assert "promote_to_formal_candidate_review" in identity["MI-001"]["owner_policy_options"]
    assert identity["CPM-RO-001"]["would_enter_forward_positive_count"] == 13
    assert identity["CPM-RO-001"]["system_recommendation"] == (
        "prepare_registry_identity_review_no_tier_change"
    )

    wave_2 = artifact["wave_2_capture_quality_closure"]
    assert wave_2["status"] == "ready_for_owner_review"
    assert wave_2["done_when"]["btpc_lsr_brf_have_closure_rows"] is True
    assert wave_2["done_when"]["vcb_rbr_are_not_hidden_in_forward_rollup"] is True
    assert wave_2["done_when"]["all_rows_are_review_only"] is True
    wave_2_rows = {row["strategy_group_id"]: row for row in wave_2["rows"]}
    assert set(wave_2_rows) == {"BTPC-001", "LSR-001", "BRF-001", "VCB-001", "RBR-001"}
    assert "review_decision" not in wave_2_rows["VCB-001"]
    assert wave_2_rows["VCB-001"]["review_outcome"] == "keep_observing_or_revise"
    assert wave_2_rows["VCB-001"]["would_enter_forward_positive_count"] == 2
    assert "review_decision" not in wave_2_rows["RBR-001"]
    assert wave_2_rows["RBR-001"]["review_outcome"] == "park_unless_new_edge"
    assert wave_2_rows["RBR-001"]["would_enter_count"] == 6

    mpg_review = artifact["priority_4_mpg_member_tiering_exit_decay_review"]
    assert mpg_review["status"] == "ready_for_owner_review"
    assert mpg_review["replay_sample_count"] == 2
    assert len(mpg_review["member_rows"]) == 6
    assert mpg_review["owner_policy_confirmation_required"] is True
    assert mpg_review["live_permission_change_recommended_now"] is False

    wave_3 = artifact["wave_3_mpg_member_deepening"]
    assert wave_3["status"] == "ready_for_owner_review"
    assert wave_3["done_when"]["six_member_roles_present"] is True
    assert wave_3["done_when"]["exit_horizons_present"] is True
    assert wave_3["done_when"]["decay_controls_present"] is True
    assert wave_3["done_when"]["no_live_scope_expansion"] is True
    assert wave_3["owner_policy_confirmation_required"] is True
    assert wave_3["live_permission_change_recommended_now"] is False

    checkpoint = {
        row["strategy_group_id"]: row
        for row in artifact["owner_confirmation_checkpoint"]["decisions"]
    }
    assert checkpoint["MI-001"]["current_recommendation"] == (
        "prepare_registry_identity_review_no_tier_change"
    )
    assert "packet_only" not in checkpoint["MI-001"]["current_recommendation"]


def test_quality_closure_wave_safety_invariants_and_cli(tmp_path, capsys):
    module = _load_module()
    capture_path = tmp_path / "capture.json"
    strategy_asset_state_path = tmp_path / "strategy-asset-state.json"
    registry_path = tmp_path / "registry.json"
    tier_path = tmp_path / "tier.json"
    replay_path = tmp_path / "replay.json"
    output_json = tmp_path / "wave.json"
    output_md = tmp_path / "wave.md"
    for path, payload in (
        (capture_path, _capture_gap_audit()),
        (strategy_asset_state_path, _strategy_asset_state_source()),
        (registry_path, _registry()),
        (tier_path, _tier_policy()),
        (replay_path, _mpg_replay_corpus()),
    ):
        path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = module.main(
        [
            "--capture-gap-audit-json",
            str(capture_path),
            "--strategy-asset-state-json",
            str(strategy_asset_state_path),
            "--registry-json",
            str(registry_path),
            "--tier-policy-json",
            str(tier_path),
            "--mpg-replay-corpus-json",
            str(replay_path),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    artifact = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_payload["status"] == "quality_closure_wave_ready"
    assert artifact["interaction"]["remote_interaction_count"] == 0
    assert "real_order_authority" not in artifact["safety_invariants"]
    assert artifact["safety_invariants"]["tier_policy_changed"] is False
    assert artifact["safety_invariants"]["live_profile_changed"] is False
    assert "execution_intent_created" not in artifact["safety_invariants"]
    assert artifact["owner_confirmation_checkpoint"]["owner_confirmation_required"] is True
    md = output_md.read_text(encoding="utf-8")
    assert "StrategyGroup Quality Closure Wave" in md
    assert "Wave 1 Strategy Explainer" in md
    assert "Wave 2 Capture Quality Closure" in md
    assert "Wave 3 MPG Member Deepening" in md
    assert "owner_policy_confirmation_after_packet" not in artifact["priority_1_capture_closure"]["rows"][0]
    assert "review packet" not in md
    assert "evidence packet" not in md
