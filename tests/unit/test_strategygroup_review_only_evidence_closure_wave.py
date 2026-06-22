from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategygroup_review_only_evidence_closure_wave.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_strategygroup_review_only_evidence_closure_wave",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _policy_confirmation() -> dict:
    decisions = [
        ("BRF-001", "P05-BRF-001", "promote_review_lane_approved_without_live_scope_change"),
        (
            "BTPC-001",
            "P05-BTPC-001",
            "keep_l2_shadow_and_continue_fact_classifier_revision",
        ),
        ("LSR-001", "P05-LSR-001", "short_revival_rewrite_review_lane_approved"),
        (
            "MI-001",
            "P05-MI-001",
            "formal_candidate_review_opened_without_registry_admission",
        ),
        (
            "CPM-RO-001",
            "P05-CPM-RO-001",
            "observation_asset_merge_review_opened_without_registry_admission",
        ),
        (
            "MPG-001",
            "P05-MPG-001",
            "member_role_split_approved_without_member_live_scope_expansion",
        ),
    ]
    return {
        "status": "review_only_policy_confirmation_ready",
        "confirmed_decisions": [
            {
                "card_id": f"{group}:owner_policy_decision",
                "strategy_group_id": group,
                "queue_id": queue_id,
                "review_only_policy_effect": effect,
            }
            for group, queue_id, effect in decisions
        ],
        "owner_perception_snapshot": {
            "p0_state": "waiting_for_market",
            "queue_count": 7,
            "rows": [
                {
                    "strategy_group_id": group,
                    "owner_state": "待复核",
                    "confirmed_effect": effect,
                    "next_queue_id": queue_id,
                }
                for group, queue_id, effect in decisions
            ],
        },
        "safety_invariants": _safe(),
    }


def _capture_gap_audit() -> dict:
    rows = [
        ("BRF-001", 1, 168, 168, 0, 136, "market_structure_not_confirmed"),
        ("BTPC-001", 0, 169, 169, 0, 152, "stale_data_or_signal"),
        ("LSR-001", 2, 167, 167, 2, 0, "no_action_other"),
        ("MI-001", 23, 315, 0, 22, 0, "observe_only_would_enter"),
        ("CPM-RO-001", 18, 151, 0, 13, 0, "observe_only_would_enter"),
        ("MPG-001", 0, 0, 0, 0, 0, "waiting_for_market"),
    ]
    return {
        "status": "strategy_capture_gap_audit_ready",
        "strategy_expectation_rows": [
            {
                "strategy_group_id": group,
                "would_enter_count": would_enter,
                "no_action_count": no_action,
                "high_priority_no_action_count": high_priority,
                "would_enter_forward_positive_count": would_enter_positive,
                "missed_no_action_forward_positive_count": missed_positive,
                "positive_forward_outcome_count": would_enter_positive + missed_positive,
                "dominant_blocker_classes": [{"key": blocker, "count": no_action}],
            }
            for (
                group,
                would_enter,
                no_action,
                high_priority,
                would_enter_positive,
                missed_positive,
                blocker,
            ) in rows
        ],
        "safety_invariants": _safe(),
    }


def _quality_closure_wave() -> dict:
    groups = ["BRF-001", "BTPC-001", "LSR-001", "MI-001", "CPM-RO-001", "MPG-001"]
    return {
        "status": "quality_closure_wave_ready",
        "wave_1_strategy_explainer": {
            "cards": [
                {
                    "strategy_group_id": group,
                    "owner_label": group,
                    "current_tier": "L2" if group == "BTPC-001" else "L1",
                    "system_auto_action": f"{group}_next_review",
                }
                for group in groups
            ]
        },
        "wave_2_capture_quality_closure": {
            "rows": [
                {
                    "strategy_group_id": group,
                    "current_tier": "L2" if group == "BTPC-001" else "L1",
                }
                for group in groups
            ]
        },
        "wave_3_mpg_member_deepening": {
            "status": "ready_for_owner_review",
            "member_count": 6,
            "member_rows": [{"member_id": "TSI-001"}],
            "exit_decay_review": {"status": "needed_before_any_live_scope_expansion"},
        },
        "safety_invariants": _safe(),
    }


def _owner_decision_package() -> dict:
    evidence = {
        "BRF-001": (["would_enter observed: 1"], ["forward outcome pending"]),
        "BTPC-001": (
            ["high-priority stale-blocked no_action count: 169"],
            ["live RequiredFacts gaps remain: 8"],
        ),
        "LSR-001": (["would_enter observed: 2"], ["sample size is small"]),
        "MI-001": (["would_enter observed: 23"], ["identity unresolved"]),
        "CPM-RO-001": (["would_enter observed: 18"], ["quality mixed"]),
        "MPG-001": (["six member roles present"], ["no member live scope"]),
    }
    return {
        "status": "owner_decision_package_ready",
        "owner_decision_cards": [
            {
                "strategy_group_id": group,
                "why_not_live": "review-only evidence cannot authorize live execution",
                "evidence_for": evidence[group][0],
                "evidence_against": evidence[group][1],
            }
            for group in evidence
        ],
        "safety_invariants": _safe(),
    }


def _btpc_packet(**counts) -> dict:
    return {
        "status": "ready",
        "counts": counts,
        "decision": {
            "keep_l2_shadow_observation": True,
            "l2_promotion_recommended_now": False,
        },
        "safety_invariants": _safe(),
    }


def _safe() -> dict:
    return {
        "registry_authority_changed": False,
        "tier_policy_changed": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "mpg_member_live_scope_expanded": False,
        "l4_real_order_scope_expanded": False,
        "shadow_candidate_created": False,
        "execution_intent_created": False,
        "final_gate_called": False,
        "operation_layer_called": False,
        "order_created": False,
        "exchange_write_called": False,
        "real_order_authority": False,
    }


def _build_packet() -> dict:
    module = _load_module()
    return module.build_review_only_evidence_closure_wave(
        review_only_policy_confirmation=_policy_confirmation(),
        capture_gap_audit=_capture_gap_audit(),
        quality_closure_wave=_quality_closure_wave(),
        owner_decision_package=_owner_decision_package(),
        btpc_fact_quality=_btpc_packet(fact_gap_count=5, fact_source_pending_count=4),
        btpc_source_mapping=_btpc_packet(
            expected_live_fact_source_count=8,
            source_attachment_pending_count=8,
            live_required_fact_gap_count=8,
        ),
        btpc_classifier_review=_btpc_packet(
            rule_review_count=2,
            implementation_ready_count=2,
        ),
        btpc_keep_revise=_btpc_packet(
            proxy_reviewable_would_enter_count=2,
            revise_case_count=3,
        ),
        btpc_proxy_replay=_btpc_packet(replay_case_count=5),
    )


def test_review_only_evidence_closure_wave_builds_three_phases():
    packet = _build_packet()

    assert packet["status"] == "review_only_evidence_closure_wave_ready"
    assert packet["phase_status"]["phase_1_owner_perception_projection"] == "ready"
    assert packet["phase_status"]["phase_2_evidence_closure_queue"] == "ready"
    assert packet["phase_status"]["phase_3_next_owner_decision_package"] == (
        "ready_for_owner_policy_decision"
    )
    assert packet["owner_progress_projection"]["p0_state"] == "waiting_for_market"
    assert packet["owner_progress_projection"]["p0_5_state"] == (
        "review_only_evidence_closure_active"
    )
    assert len(packet["evidence_closure_packets"]) == 6
    assert packet["next_owner_decision_package"]["decision_count"] == 6


def test_review_only_evidence_closure_wave_keeps_live_authority_closed():
    packet = _build_packet()

    assert packet["interaction"]["remote_interaction_count"] == 0
    assert packet["interaction"]["calls_finalgate"] is False
    assert packet["interaction"]["calls_operation_layer"] is False
    assert packet["safety_invariants"]["real_order_authority"] is False
    assert packet["safety_invariants"]["registry_authority_changed"] is False
    assert packet["completion_boundary"]["owner_policy_confirmation_required_now"] is True
    assert packet["completion_boundary"]["runtime_owner_intervention_required"] is False

    cards = {
        card["strategy_group_id"]: card
        for card in packet["next_owner_decision_package"]["cards"]
    }
    assert cards["MI-001"]["default_recommendation"] == (
        "open_formal_candidate_review_with_overlap_and_concentration_checks"
    )
    assert cards["MPG-001"]["does_not_authorize_live_execution"] is True


def test_review_only_evidence_closure_wave_rejects_forbidden_policy_effects():
    module = _load_module()
    policy_confirmation = _policy_confirmation()
    policy_confirmation["safety_invariants"]["registry_authority_changed"] = True

    try:
        module.build_review_only_evidence_closure_wave(
            review_only_policy_confirmation=policy_confirmation,
            capture_gap_audit=_capture_gap_audit(),
            quality_closure_wave=_quality_closure_wave(),
            owner_decision_package=_owner_decision_package(),
        )
    except ValueError as exc:
        assert "forbidden effects" in str(exc)
    else:
        raise AssertionError("expected forbidden policy effect to fail")


def test_review_only_evidence_closure_wave_cli_writes_outputs(tmp_path, capsys):
    module = _load_module()
    inputs = {
        "policy.json": _policy_confirmation(),
        "capture.json": _capture_gap_audit(),
        "quality.json": _quality_closure_wave(),
        "owner.json": _owner_decision_package(),
        "btpc-fact.json": _btpc_packet(fact_gap_count=5),
        "btpc-source.json": _btpc_packet(source_attachment_pending_count=8),
        "btpc-classifier.json": _btpc_packet(rule_review_count=2),
        "btpc-keep.json": _btpc_packet(proxy_reviewable_would_enter_count=2),
        "btpc-proxy.json": _btpc_packet(replay_case_count=5),
    }
    for name, payload in inputs.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    output_json = tmp_path / "wave.json"
    output_md = tmp_path / "wave.md"
    owner_progress = tmp_path / "owner-progress.md"

    exit_code = module.main(
        [
            "--review-only-policy-confirmation-json",
            str(tmp_path / "policy.json"),
            "--capture-gap-audit-json",
            str(tmp_path / "capture.json"),
            "--quality-closure-wave-json",
            str(tmp_path / "quality.json"),
            "--owner-decision-package-json",
            str(tmp_path / "owner.json"),
            "--btpc-fact-quality-json",
            str(tmp_path / "btpc-fact.json"),
            "--btpc-source-mapping-json",
            str(tmp_path / "btpc-source.json"),
            "--btpc-classifier-review-json",
            str(tmp_path / "btpc-classifier.json"),
            "--btpc-keep-revise-json",
            str(tmp_path / "btpc-keep.json"),
            "--btpc-proxy-replay-json",
            str(tmp_path / "btpc-proxy.json"),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--output-owner-progress",
            str(owner_progress),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    packet = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    owner_progress_text = owner_progress.read_text(encoding="utf-8")
    assert stdout_payload["status"] == "review_only_evidence_closure_wave_ready"
    assert packet["next_owner_decision_package"]["status"] == (
        "next_owner_decision_package_ready"
    )
    assert "Evidence Closure Packets" in markdown
    assert "StrategyGroup Owner Progress" in owner_progress_text
