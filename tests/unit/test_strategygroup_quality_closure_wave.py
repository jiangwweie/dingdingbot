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


def _decision_ledger() -> dict:
    return {
        "status": "decision_ledger_ready",
        "ledger_rows": [
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
    }


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
                "actionable_now": False,
                "actionable_now_reason": "runtime_state_only",
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
                "actionable_now": False,
                "actionable_now_reason": "observe_only",
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
                "actionable_now": False,
                "actionable_now_reason": "shadow_only",
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
                "actionable_now": False,
                "actionable_now_reason": "observe_only",
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
                "actionable_now": False,
                "actionable_now_reason": "observe_only",
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
                "actionable_now": False,
                "actionable_now_reason": "parked",
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
                "actionable_now": False,
                "actionable_now_reason": "observe_only",
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
                "actionable_now": False,
                "actionable_now_reason": "observe_only",
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
                "actionable_now": False,
                "actionable_now_reason": "observe_only",
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


def test_quality_closure_wave_builds_priority_packets_and_owner_cards():
    module = _load_module()

    packet = module.build_quality_closure_wave(
        capture_gap_audit=_capture_gap_audit(),
        decision_ledger=_decision_ledger(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        mpg_replay_corpus=_mpg_replay_corpus(),
    )

    assert packet["status"] == "quality_closure_wave_ready"
    assert packet["priority_1_capture_closure"]["status"] == "ready_for_owner_review"
    priority_rows = {
        row["strategy_group_id"]: row
        for row in packet["priority_1_capture_closure"]["rows"]
    }
    assert priority_rows["BTPC-001"]["ledger_decision"] == "revise"
    assert priority_rows["BTPC-001"]["missed_no_action_forward_positive_count"] == 152
    assert priority_rows["LSR-001"]["would_enter_forward_positive_count"] == 2
    assert priority_rows["BRF-001"]["owner_policy_decision_after_packet"] is True

    wave_1 = packet["wave_1_strategy_explainer"]
    assert wave_1["status"] == "ready"
    assert wave_1["missing_required_cards"] == []
    wave_1_cards = {row["strategy_group_id"]: row for row in wave_1["cards"]}
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
        assert group in wave_1_cards
        assert wave_1_cards[group]["actionable_now"] is False
        assert wave_1_cards[group]["live_permission_change_recommended_now"] is False
        assert wave_1_cards[group]["owner_can_decide"]
        assert wave_1_cards[group]["system_auto_action"]

    cards = {
        row["strategy_group_id"]: row
        for row in packet["priority_2_owner_cards_v1"]["cards"]
    }
    assert cards["MPG-001"]["owner_label"] == "动量延续"
    assert cards["MPG-001"]["actionable_now"] is False
    assert cards["BRF-001"]["live_permission_change_recommended_now"] is False


def test_quality_closure_wave_keeps_identity_and_mpg_member_review_policy_only():
    module = _load_module()

    packet = module.build_quality_closure_wave(
        capture_gap_audit=_capture_gap_audit(),
        decision_ledger=_decision_ledger(),
        registry=_registry(),
        tier_policy=_tier_policy(),
        mpg_replay_corpus=_mpg_replay_corpus(),
    )

    identity = {
        row["strategy_group_id"]: row
        for row in packet["priority_3_identity_review"]["rows"]
    }
    assert identity["MI-001"]["would_enter_count"] == 23
    assert identity["MI-001"]["owner_policy_decision_required"] is True
    assert "promote_to_formal_candidate_review" in identity["MI-001"]["owner_decision_options"]
    assert identity["CPM-RO-001"]["would_enter_forward_positive_count"] == 13

    wave_2 = packet["wave_2_capture_quality_closure"]
    assert wave_2["status"] == "ready_for_owner_review"
    assert wave_2["done_when"]["btpc_lsr_brf_have_closure_rows"] is True
    assert wave_2["done_when"]["vcb_rbr_are_not_hidden_in_forward_rollup"] is True
    assert wave_2["done_when"]["all_rows_are_review_only"] is True
    wave_2_rows = {row["strategy_group_id"]: row for row in wave_2["rows"]}
    assert set(wave_2_rows) == {"BTPC-001", "LSR-001", "BRF-001", "VCB-001", "RBR-001"}
    assert wave_2_rows["VCB-001"]["review_decision"] == "keep_observing_or_revise"
    assert wave_2_rows["VCB-001"]["would_enter_forward_positive_count"] == 2
    assert wave_2_rows["RBR-001"]["review_decision"] == "park_unless_new_edge"
    assert wave_2_rows["RBR-001"]["would_enter_count"] == 6

    mpg_review = packet["priority_4_mpg_member_tiering_exit_decay_review"]
    assert mpg_review["status"] == "ready_for_owner_review"
    assert mpg_review["replay_sample_count"] == 2
    assert len(mpg_review["member_rows"]) == 6
    assert mpg_review["owner_policy_decision_required"] is True
    assert mpg_review["live_permission_change_recommended_now"] is False

    wave_3 = packet["wave_3_mpg_member_deepening"]
    assert wave_3["status"] == "ready_for_owner_review"
    assert wave_3["done_when"]["six_member_roles_present"] is True
    assert wave_3["done_when"]["exit_horizons_present"] is True
    assert wave_3["done_when"]["decay_controls_present"] is True
    assert wave_3["done_when"]["no_live_scope_expansion"] is True
    assert wave_3["owner_policy_decision_required"] is True
    assert wave_3["live_permission_change_recommended_now"] is False


def test_quality_closure_wave_safety_invariants_and_cli(tmp_path, capsys):
    module = _load_module()
    capture_path = tmp_path / "capture.json"
    ledger_path = tmp_path / "ledger.json"
    registry_path = tmp_path / "registry.json"
    tier_path = tmp_path / "tier.json"
    replay_path = tmp_path / "replay.json"
    output_json = tmp_path / "wave.json"
    output_md = tmp_path / "wave.md"
    for path, payload in (
        (capture_path, _capture_gap_audit()),
        (ledger_path, _decision_ledger()),
        (registry_path, _registry()),
        (tier_path, _tier_policy()),
        (replay_path, _mpg_replay_corpus()),
    ):
        path.write_text(json.dumps(payload), encoding="utf-8")

    exit_code = module.main(
        [
            "--capture-gap-audit-json",
            str(capture_path),
            "--decision-ledger-json",
            str(ledger_path),
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
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_payload["status"] == "quality_closure_wave_ready"
    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["safety_invariants"]["real_order_authority"] is False
    assert packet["safety_invariants"]["tier_policy_changed"] is False
    assert packet["safety_invariants"]["live_profile_changed"] is False
    assert packet["owner_confirmation_checkpoint"]["owner_confirmation_required"] is True
    md = output_md.read_text(encoding="utf-8")
    assert "StrategyGroup Quality Closure Wave" in md
    assert "Wave 1 Strategy Explainer" in md
    assert "Wave 2 Capture Quality Closure" in md
    assert "Wave 3 MPG Member Deepening" in md
