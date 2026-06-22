#!/usr/bin/env python3
"""Build the review-only StrategyGroup evidence closure wave.

This command consumes the confirmed review-only policy packet plus current local
StrategyGroup evidence and projects three phases:

1. Owner perception projection.
2. Review-only evidence closure packets.
3. Next Owner decision package.

It is local review support only. It never mutates registry authority, tier
policy, live profile, FinalGate, Operation Layer, exchange state, or orders.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_REVIEW_ONLY_POLICY_CONFIRMATION_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-policy-confirmation.json"
)
DEFAULT_CAPTURE_GAP_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/strategy-capture-gap-audit-20260622.json"
)
DEFAULT_QUALITY_CLOSURE_WAVE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-quality-closure-wave.json"
)
DEFAULT_OWNER_DECISION_PACKAGE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-owner-decision-package.json"
)
DEFAULT_BTPC_FACT_QUALITY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-l2-shadow-fact-quality-review.json"
)
DEFAULT_BTPC_SOURCE_MAPPING_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-live-derivatives-fact-source-mapping.json"
)
DEFAULT_BTPC_CLASSIFIER_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-classifier-rule-review.json"
)
DEFAULT_BTPC_KEEP_REVISE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-decision.json"
)
DEFAULT_BTPC_PROXY_REPLAY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-proxy-replay-quality-review.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-evidence-closure-wave.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-evidence-closure-wave.md"
)
DEFAULT_OUTPUT_OWNER_PROGRESS = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-owner-progress.md"
)

FORBIDDEN_EFFECTS = (
    "registry_authority_changed",
    "tier_policy_changed",
    "live_profile_changed",
    "order_sizing_changed",
    "mpg_member_live_scope_expanded",
    "l4_real_order_scope_expanded",
    "shadow_candidate_created",
    "execution_intent_created",
    "final_gate_called",
    "operation_layer_called",
    "order_created",
    "exchange_write_called",
    "real_order_authority",
)

DECISION_ORDER = (
    "BRF-001",
    "BTPC-001",
    "LSR-001",
    "MI-001",
    "CPM-RO-001",
    "MPG-001",
)

NEXT_OWNER_DECISION_SPECS = {
    "BRF-001": {
        "card_id": "BRF-001:next_policy_decision",
        "decision_type": "promote_review_continuation",
        "question": "BRF-001 是否继续进入上层 promote review 证据线，而不改变实盘范围。",
        "default_recommendation": "continue_promote_review_evidence_lane_without_live_scope_change",
        "next_system_action_if_approved": "build_brf_requiredfacts_squeeze_classifier_replay_pack",
        "blocked_policy_effects": ["tier_policy_change", "live_scope_change"],
        "options": [
            "continue_promote_review_evidence_lane",
            "keep_l1_observe_until_forward_outcome_completes",
            "pause_until_squeeze_classifier_is_stronger",
        ],
    },
    "BTPC-001": {
        "card_id": "BTPC-001:next_policy_decision",
        "decision_type": "l2_shadow_revise_or_park",
        "question": "BTPC-001 是否保持 L2 shadow 并继续修 fact-source/classifier，而不是放松 gate 或停车。",
        "default_recommendation": "keep_l2_shadow_revise_fact_source_classifier_without_gate_relaxation",
        "next_system_action_if_approved": "run_btpc_false_positive_and_fact_attachment_review",
        "blocked_policy_effects": ["stale_gate_relaxation", "tier_policy_change"],
        "options": [
            "keep_l2_shadow_revise_sources",
            "wait_for_live_fact_source_attachment",
            "prepare_conditional_gate_relax_review",
            "park_btpc_until_edge_reappears",
        ],
    },
    "LSR-001": {
        "card_id": "LSR-001:next_policy_decision",
        "decision_type": "short_revival_rewrite",
        "question": "LSR-001 是否正式化 short-revival rewrite 作为下一轮复核方向。",
        "default_recommendation": "formalize_short_revival_rewrite_without_live_scope_change",
        "next_system_action_if_approved": "build_lsr_range_context_requiredfacts_replay_pack",
        "blocked_policy_effects": ["live_scope_change", "l1_to_l2_promotion"],
        "options": [
            "formalize_short_revival_rewrite",
            "keep_l1_generic_observe",
            "park_lsr_until_sample_size_improves",
        ],
    },
    "MI-001": {
        "card_id": "MI-001:next_policy_decision",
        "decision_type": "registry_identity",
        "question": "MI-001 应作为正式候选、MPG 子能力、观察资产，还是停车。",
        "default_recommendation": "open_formal_candidate_review_with_overlap_and_concentration_checks",
        "next_system_action_if_approved": "build_mi_registry_handoff_draft_without_admission",
        "blocked_policy_effects": ["registry_admission", "live_scope_change"],
        "options": [
            "formal_candidate_review",
            "mpg_support_capability_review",
            "observe_asset_only",
            "park_mi",
        ],
    },
    "CPM-RO-001": {
        "card_id": "CPM-RO-001:next_policy_decision",
        "decision_type": "registry_identity",
        "question": "CPM-RO-001 应独立、合并、作为观察资产，还是停车。",
        "default_recommendation": "keep_observation_asset_and_run_merge_review",
        "next_system_action_if_approved": "build_cpm_ro_merge_target_review_without_registry_admission",
        "blocked_policy_effects": ["registry_admission", "live_scope_change"],
        "options": [
            "independent_strategy_review",
            "merge_into_existing_family",
            "observe_asset_only",
            "park_cpm_ro",
        ],
    },
    "MPG-001": {
        "card_id": "MPG-001:next_policy_decision",
        "decision_type": "member_role_exit_decay_boundary",
        "question": "MPG-001 是否接受 member role / exit-decay / risk boundary 分层，且不扩 member 实盘范围。",
        "default_recommendation": "accept_member_role_split_and_decay_review_without_member_live_scope_expansion",
        "next_system_action_if_approved": "build_mpg_member_scoring_and_decay_controls",
        "blocked_policy_effects": ["mpg_member_live_scope_expansion", "live_profile_change"],
        "options": [
            "accept_member_role_split",
            "keep_mpg_single_l4_box",
            "freeze_member_review",
        ],
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review-only-policy-confirmation-json",
        default=str(DEFAULT_REVIEW_ONLY_POLICY_CONFIRMATION_JSON),
    )
    parser.add_argument(
        "--capture-gap-audit-json",
        default=str(DEFAULT_CAPTURE_GAP_AUDIT_JSON),
    )
    parser.add_argument(
        "--quality-closure-wave-json",
        default=str(DEFAULT_QUALITY_CLOSURE_WAVE_JSON),
    )
    parser.add_argument(
        "--owner-decision-package-json",
        default=str(DEFAULT_OWNER_DECISION_PACKAGE_JSON),
    )
    parser.add_argument("--btpc-fact-quality-json", default=str(DEFAULT_BTPC_FACT_QUALITY_JSON))
    parser.add_argument(
        "--btpc-source-mapping-json",
        default=str(DEFAULT_BTPC_SOURCE_MAPPING_JSON),
    )
    parser.add_argument(
        "--btpc-classifier-review-json",
        default=str(DEFAULT_BTPC_CLASSIFIER_REVIEW_JSON),
    )
    parser.add_argument("--btpc-keep-revise-json", default=str(DEFAULT_BTPC_KEEP_REVISE_JSON))
    parser.add_argument("--btpc-proxy-replay-json", default=str(DEFAULT_BTPC_PROXY_REPLAY_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument(
        "--output-owner-progress",
        default=str(DEFAULT_OUTPUT_OWNER_PROGRESS),
    )
    args = parser.parse_args(argv)

    packet = build_review_only_evidence_closure_wave(
        review_only_policy_confirmation=_load_json_object(
            Path(args.review_only_policy_confirmation_json)
        ),
        capture_gap_audit=_load_json_object(Path(args.capture_gap_audit_json)),
        quality_closure_wave=_load_json_object(Path(args.quality_closure_wave_json)),
        owner_decision_package=_load_json_object(Path(args.owner_decision_package_json)),
        btpc_fact_quality=_load_json_object(Path(args.btpc_fact_quality_json), required=False),
        btpc_source_mapping=_load_json_object(Path(args.btpc_source_mapping_json), required=False),
        btpc_classifier_review=_load_json_object(
            Path(args.btpc_classifier_review_json),
            required=False,
        ),
        btpc_keep_revise=_load_json_object(Path(args.btpc_keep_revise_json), required=False),
        btpc_proxy_replay=_load_json_object(Path(args.btpc_proxy_replay_json), required=False),
    )

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_owner_progress = Path(args.output_owner_progress)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_owner_progress.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_md.write_text(_markdown(packet, output_json, output_md), encoding="utf-8")
    output_owner_progress.write_text(
        _owner_progress_markdown(packet, output_owner_progress),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"status": packet["status"], "output_json": str(output_json)},
            ensure_ascii=False,
        )
    )
    return 0


def build_review_only_evidence_closure_wave(
    *,
    review_only_policy_confirmation: dict[str, Any],
    capture_gap_audit: dict[str, Any],
    quality_closure_wave: dict[str, Any],
    owner_decision_package: dict[str, Any],
    btpc_fact_quality: dict[str, Any] | None = None,
    btpc_source_mapping: dict[str, Any] | None = None,
    btpc_classifier_review: dict[str, Any] | None = None,
    btpc_keep_revise: dict[str, Any] | None = None,
    btpc_proxy_replay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_inputs(
        review_only_policy_confirmation=review_only_policy_confirmation,
        capture_gap_audit=capture_gap_audit,
        quality_closure_wave=quality_closure_wave,
        owner_decision_package=owner_decision_package,
    )

    evidence_context = _evidence_context(
        capture_gap_audit=capture_gap_audit,
        quality_closure_wave=quality_closure_wave,
        owner_decision_package=owner_decision_package,
        btpc_fact_quality=btpc_fact_quality or {},
        btpc_source_mapping=btpc_source_mapping or {},
        btpc_classifier_review=btpc_classifier_review or {},
        btpc_keep_revise=btpc_keep_revise or {},
        btpc_proxy_replay=btpc_proxy_replay or {},
    )
    evidence_packets = [
        _evidence_packet_for(group, review_only_policy_confirmation, evidence_context)
        for group in DECISION_ORDER
    ]
    owner_progress_projection = _owner_progress_projection(
        review_only_policy_confirmation,
        evidence_packets,
    )
    next_owner_decision_package = _next_owner_decision_package(evidence_packets)

    return {
        "schema": "brc.strategygroup_review_only_evidence_closure_wave.v1",
        "scope": "strategy_perception_evidence_closure_phases_1_to_3",
        "status": "review_only_evidence_closure_wave_ready",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase_status": {
            "phase_1_owner_perception_projection": "ready",
            "phase_2_evidence_closure_queue": "ready",
            "phase_3_next_owner_decision_package": "ready_for_owner_policy_decision",
        },
        "closed_problem": (
            "P0 waiting_for_market is now separated from active P0.5 "
            "strategy-review evidence closure and next Owner policy decisions."
        ),
        "owner_progress_projection": owner_progress_projection,
        "evidence_closure_packets": evidence_packets,
        "next_owner_decision_package": next_owner_decision_package,
        "completion_boundary": {
            "current_stage": "review_only_evidence_closure_wave_ready",
            "owner_policy_confirmation_required_now": True,
            "runtime_owner_intervention_required": False,
            "owner_decision_required_for": [
                item["card_id"]
                for item in next_owner_decision_package["cards"]
            ],
            "allowed_without_owner_input": [
                "refresh read-only evidence",
                "rerun local review-only packet generation",
                "keep P0 live-submit standby waiting for fresh signal",
            ],
            "blocked_until_separate_owner_confirmation": [
                "promote",
                "park",
                "kill",
                "registry_admission",
                "tier_policy_change",
                "live_profile_change",
                "mpg_member_live_scope_expansion",
                "real_order_scope_expansion",
            ],
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
        "source_status": {
            "review_only_policy_confirmation": review_only_policy_confirmation.get("status"),
            "capture_gap_audit": capture_gap_audit.get("status"),
            "quality_closure_wave": quality_closure_wave.get("status"),
            "owner_decision_package": owner_decision_package.get("status"),
        },
    }


def _validate_inputs(
    *,
    review_only_policy_confirmation: dict[str, Any],
    capture_gap_audit: dict[str, Any],
    quality_closure_wave: dict[str, Any],
    owner_decision_package: dict[str, Any],
) -> None:
    expected = {
        "review_only_policy_confirmation": (
            review_only_policy_confirmation,
            "review_only_policy_confirmation_ready",
        ),
        "capture_gap_audit": (capture_gap_audit, "strategy_capture_gap_audit_ready"),
        "quality_closure_wave": (quality_closure_wave, "quality_closure_wave_ready"),
        "owner_decision_package": (owner_decision_package, "owner_decision_package_ready"),
    }
    bad_statuses = [
        f"{name}={packet.get('status')}"
        for name, (packet, expected_status) in expected.items()
        if packet.get("status") != expected_status
    ]
    if bad_statuses:
        raise ValueError("inputs are not ready: " + ", ".join(bad_statuses))
    for name, (packet, _) in expected.items():
        safety = _as_dict(packet.get("safety_invariants"))
        forbidden = [key for key in FORBIDDEN_EFFECTS if safety.get(key) is True]
        if forbidden:
            raise ValueError(f"{name} has forbidden effects: {forbidden}")


def _evidence_context(
    *,
    capture_gap_audit: dict[str, Any],
    quality_closure_wave: dict[str, Any],
    owner_decision_package: dict[str, Any],
    btpc_fact_quality: dict[str, Any],
    btpc_source_mapping: dict[str, Any],
    btpc_classifier_review: dict[str, Any],
    btpc_keep_revise: dict[str, Any],
    btpc_proxy_replay: dict[str, Any],
) -> dict[str, Any]:
    return {
        "capture_rows": {
            str(row.get("strategy_group_id")): row
            for row in _dict_rows(capture_gap_audit.get("strategy_expectation_rows"))
        },
        "quality_rows": {
            str(row.get("strategy_group_id")): row
            for row in _dict_rows(
                _as_dict(quality_closure_wave.get("wave_2_capture_quality_closure")).get("rows")
            )
        },
        "strategy_cards": {
            str(row.get("strategy_group_id")): row
            for row in _dict_rows(
                _as_dict(quality_closure_wave.get("wave_1_strategy_explainer")).get("cards")
            )
        },
        "owner_cards": {
            str(row.get("strategy_group_id")): row
            for row in _dict_rows(owner_decision_package.get("owner_decision_cards"))
        },
        "mpg_member_review": _as_dict(
            quality_closure_wave.get("wave_3_mpg_member_deepening")
        ),
        "btpc": {
            "fact_quality": btpc_fact_quality,
            "source_mapping": btpc_source_mapping,
            "classifier_review": btpc_classifier_review,
            "keep_revise": btpc_keep_revise,
            "proxy_replay": btpc_proxy_replay,
        },
    }


def _evidence_packet_for(
    group: str,
    policy_confirmation: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    confirmed = _confirmed_decision_for_group(policy_confirmation, group)
    capture = _as_dict(context["capture_rows"].get(group))
    quality = _as_dict(context["quality_rows"].get(group))
    strategy_card = _as_dict(context["strategy_cards"].get(group))
    owner_card = _as_dict(context["owner_cards"].get(group))
    spec = NEXT_OWNER_DECISION_SPECS[group]

    base = {
        "queue_id": confirmed.get("queue_id") or f"P05-{group}",
        "strategy_group_id": group,
        "status": "review_only_evidence_packet_ready",
        "review_only": True,
        "real_order_authority": False,
        "confirmed_review_only_policy_effect": confirmed.get("review_only_policy_effect"),
        "source_counts": _source_counts(capture),
        "dominant_blocker_classes": capture.get("dominant_blocker_classes", []),
        "owner_label": strategy_card.get("owner_label") or group,
        "current_tier": strategy_card.get("current_tier") or quality.get("current_tier"),
        "system_auto_action": strategy_card.get("system_auto_action"),
        "why_not_live": owner_card.get("why_not_live") or _generic_why_not_live(),
        "evidence_for": list(_list(owner_card.get("evidence_for"))),
        "evidence_against": list(_list(owner_card.get("evidence_against"))),
        "closure_findings": [],
        "closure_result": "",
        "next_owner_policy_card": {
            "card_id": spec["card_id"],
            "decision_type": spec["decision_type"],
            "question": spec["question"],
            "default_recommendation": spec["default_recommendation"],
            "options": spec["options"],
            "next_system_action_if_approved": spec["next_system_action_if_approved"],
            "blocked_policy_effects": spec["blocked_policy_effects"],
        },
        "safety_invariants": _safety_invariants(),
    }

    if group == "BRF-001":
        base["closure_findings"] = [
            "bear-rally failure short structure exists in observe-only audit",
            "forward outcome for the latest would_enter is still pending",
            "squeeze classifier and RequiredFacts review remain review-only prerequisites",
        ]
        base["closure_result"] = (
            "promote_review_evidence_lane_can_continue_without_live_scope_change"
        )
    elif group == "BTPC-001":
        btpc = context["btpc"]
        base["btpc_attribution"] = _btpc_attribution(btpc)
        base["closure_findings"] = [
            "stale gate attribution is real and should not be hidden as no opportunity",
            "live derivatives mappings are identified but not attached as live RequiredFacts",
            "classifier rule review is recorded but does not authorize promotion or live submit",
        ]
        base["closure_result"] = (
            "keep_l2_shadow_and_revise_fact_source_classifier_before_any_gate_relaxation"
        )
    elif group == "LSR-001":
        base["closure_findings"] = [
            "short-revival would_enter evidence exists but sample size remains small",
            "long preview and side-specific short semantics still need policy separation",
            "range-context RequiredFacts should be formalized before any tier change",
        ]
        base["closure_result"] = (
            "formalize_short_revival_rewrite_review_without_live_scope_change"
        )
    elif group == "MI-001":
        base["closure_findings"] = [
            "MI has strong would_enter and forward-positive concentration",
            "registry identity is unresolved and must not be treated as admission",
            "overlap with MPG or adjacent momentum capability requires review",
        ]
        base["closure_result"] = (
            "open_formal_candidate_review_without_registry_admission"
        )
    elif group == "CPM-RO-001":
        base["closure_findings"] = [
            "CPM-RO has meaningful would_enter evidence but mixed forward quality",
            "merge target across CPM, RBR, or momentum families is unresolved",
            "observation asset status is safer than independent admission now",
        ]
        base["closure_result"] = (
            "keep_observation_asset_and_run_merge_review_without_registry_admission"
        )
    elif group == "MPG-001":
        mpg_member_review = context["mpg_member_review"]
        base["member_review"] = {
            "status": mpg_member_review.get("status"),
            "member_count": mpg_member_review.get("member_count"),
            "exit_decay_review": mpg_member_review.get("exit_decay_review"),
            "member_rows": mpg_member_review.get("member_rows", []),
        }
        base["closure_findings"] = [
            "MPG remains the selected L4 live lane but has no executable fresh signal now",
            "member roles and exit-decay controls are ready for policy review",
            "no member receives live scope from this packet",
        ]
        base["closure_result"] = (
            "member_role_exit_decay_review_ready_without_member_live_scope_expansion"
        )
    return base


def _source_counts(capture_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "would_enter_count": _int(capture_row.get("would_enter_count")),
        "no_action_count": _int(capture_row.get("no_action_count")),
        "high_priority_no_action_count": _int(
            capture_row.get("high_priority_no_action_count")
        ),
        "would_enter_forward_positive_count": _int(
            capture_row.get("would_enter_forward_positive_count")
        ),
        "missed_no_action_forward_positive_count": _int(
            capture_row.get("missed_no_action_forward_positive_count")
        ),
        "positive_forward_outcome_count": _int(
            capture_row.get("positive_forward_outcome_count")
        ),
    }


def _btpc_attribution(btpc: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fact_quality_counts = _as_dict(btpc["fact_quality"].get("counts"))
    source_mapping_counts = _as_dict(btpc["source_mapping"].get("counts"))
    classifier_counts = _as_dict(btpc["classifier_review"].get("counts"))
    keep_revise_counts = _as_dict(btpc["keep_revise"].get("counts"))
    proxy_counts = _as_dict(btpc["proxy_replay"].get("counts"))
    return {
        "fact_gap_count": _int(fact_quality_counts.get("fact_gap_count")),
        "fact_source_pending_count": _int(
            fact_quality_counts.get("fact_source_pending_count")
        ),
        "expected_live_fact_source_count": _int(
            source_mapping_counts.get("expected_live_fact_source_count")
        ),
        "source_attachment_pending_count": _int(
            source_mapping_counts.get("source_attachment_pending_count")
        ),
        "live_required_fact_gap_count": _int(
            source_mapping_counts.get("live_required_fact_gap_count")
        ),
        "classifier_rule_review_count": _int(
            classifier_counts.get("rule_review_count")
        ),
        "implementation_ready_count": _int(
            classifier_counts.get("implementation_ready_count")
        ),
        "proxy_reviewable_would_enter_count": _int(
            keep_revise_counts.get("proxy_reviewable_would_enter_count")
        ),
        "revise_case_count": _int(keep_revise_counts.get("revise_case_count")),
        "proxy_replay_case_count": _int(proxy_counts.get("replay_case_count")),
        "decision": _as_dict(btpc["keep_revise"].get("decision")),
    }


def _owner_progress_projection(
    policy_confirmation: dict[str, Any],
    evidence_packets: list[dict[str, Any]],
) -> dict[str, Any]:
    source_snapshot = _as_dict(policy_confirmation.get("owner_perception_snapshot"))
    packet_by_group = {
        str(packet["strategy_group_id"]): packet for packet in evidence_packets
    }
    rows = []
    for row in _dict_rows(source_snapshot.get("rows")):
        group = str(row.get("strategy_group_id"))
        packet = packet_by_group.get(group)
        rows.append(
            {
                "strategy_group_id": group,
                "owner_state": row.get("owner_state"),
                "confirmed_effect": row.get("confirmed_effect"),
                "next_queue_id": row.get("next_queue_id"),
                "evidence_closure_status": packet.get("status") if packet else "not_selected",
                "closure_result": packet.get("closure_result") if packet else None,
                "no_live_permission": True,
            }
        )
    return {
        "status": "owner_progress_projection_ready",
        "owner_summary": (
            "主链路等待可执行机会；P0.5 策略观察层已进入证据闭合；"
            "实盘权限没有变化。"
        ),
        "p0_state": source_snapshot.get("p0_state", "waiting_for_market"),
        "p0_owner_label": "主链路等待机会",
        "p0_5_state": "review_only_evidence_closure_active",
        "p0_5_owner_label": "策略复核队列运行中",
        "queue_count": source_snapshot.get("queue_count", len(evidence_packets) + 1),
        "evidence_packet_count": len(evidence_packets),
        "next_owner_decision_count": len(evidence_packets),
        "no_live_permission": True,
        "owner_intervention_required": False,
        "owner_policy_confirmation_required_after_wave": True,
        "rows": rows,
    }


def _next_owner_decision_package(
    evidence_packets: list[dict[str, Any]]
) -> dict[str, Any]:
    cards = []
    for packet in evidence_packets:
        next_card = dict(packet["next_owner_policy_card"])
        next_card.update(
            {
                "strategy_group_id": packet["strategy_group_id"],
                "source_queue_id": packet["queue_id"],
                "decision_ready": True,
                "review_only": True,
                "default_recommendation": next_card["default_recommendation"],
                "evidence_for": packet["evidence_for"],
                "evidence_against": packet["evidence_against"],
                "closure_findings": packet["closure_findings"],
                "closure_result": packet["closure_result"],
                "why_not_live": packet["why_not_live"],
                "does_not_authorize_live_execution": True,
            }
        )
        cards.append(next_card)
    return {
        "schema": "brc.strategygroup_next_owner_decision_package.v1",
        "status": "next_owner_decision_package_ready",
        "owner_policy_confirmation_required_now": True,
        "runtime_owner_intervention_required": False,
        "decision_count": len(cards),
        "cards": cards,
        "default_recommendations": [
            {
                "card_id": card["card_id"],
                "strategy_group_id": card["strategy_group_id"],
                "default_recommendation": card["default_recommendation"],
            }
            for card in cards
        ],
        "blocked_policy_effects": [
            "promote",
            "park",
            "kill",
            "registry_admission",
            "tier_policy_change",
            "live_profile_change",
            "mpg_member_live_scope_expansion",
            "real_order_scope_expansion",
        ],
        "safety_invariants": _safety_invariants(),
    }


def _confirmed_decision_for_group(
    policy_confirmation: dict[str, Any],
    group: str,
) -> dict[str, Any]:
    for row in _dict_rows(policy_confirmation.get("confirmed_decisions")):
        if row.get("strategy_group_id") == group:
            return row
    return {}


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_review_only_evidence_closure_wave",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }


def _safety_invariants() -> dict[str, Any]:
    return {
        "local_review_only": True,
        "server_interaction": False,
        "server_files_mutated": False,
        "runtime_started": False,
        "strategy_parameters_changed": False,
        "tier_policy_changed": False,
        "live_profile_changed": False,
        "registry_authority_changed": False,
        "mpg_member_live_scope_expanded": False,
        "l4_real_order_scope_expanded": False,
        "shadow_candidate_created": False,
        "execution_intent_created": False,
        "final_gate_called": False,
        "operation_layer_called": False,
        "order_created": False,
        "exchange_write_called": False,
        "real_order_authority": False,
        "preview_or_replay_treated_as_live_signal": False,
    }


def _markdown(packet: dict[str, Any], output_json: Path, output_md: Path) -> str:
    lines = [
        "# StrategyGroup Review-Only Evidence Closure Wave",
        "",
        "## Summary",
        "",
        f"- Status: `{packet['status']}`",
        f"- Closed problem: {packet['closed_problem']}",
        "- Real order authority: `false`",
        "- Live permission change: `false`",
        "- Owner policy confirmation required now: `true`",
        "",
        "## Phase Status",
        "",
        "| Phase | Status |",
        "| --- | --- |",
    ]
    for key, value in packet["phase_status"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(_owner_projection_lines(packet["owner_progress_projection"]))
    lines.extend(
        [
            "",
            "## Evidence Closure Packets",
            "",
            "| Queue | StrategyGroup | Closure result | Next card | Real order authority |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in packet["evidence_closure_packets"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `false` |".format(
                row["queue_id"],
                row["strategy_group_id"],
                row["closure_result"],
                row["next_owner_policy_card"]["card_id"],
            )
        )
    lines.extend(
        [
            "",
            "## Next Owner Decision Package",
            "",
            "| Card | StrategyGroup | Default recommendation |",
            "| --- | --- | --- |",
        ]
    )
    for card in packet["next_owner_decision_package"]["cards"]:
        lines.append(
            "| `{}` | `{}` | `{}` |".format(
                card["card_id"],
                card["strategy_group_id"],
                card["default_recommendation"],
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            f"- Current stage: `{packet['completion_boundary']['current_stage']}`",
            "- Owner policy confirmation required now: `true`",
            "- Runtime Owner intervention required: `false`",
            "- Blocked until separate Owner confirmation: "
            + ", ".join(
                f"`{item}`"
                for item in packet["completion_boundary"][
                    "blocked_until_separate_owner_confirmation"
                ]
            ),
            "",
            "## Safety",
            "",
            "| Field | Value |",
            "| --- | --- |",
        ]
    )
    for key, value in packet["safety_invariants"].items():
        lines.append(f"| `{key}` | `{str(value).lower()}` |")
    lines.extend(
        [
            "",
            "## Output",
            "",
            f"- JSON: `{output_json}`",
            f"- Markdown: `{output_md}`",
            "",
        ]
    )
    return "\n".join(lines)


def _owner_progress_markdown(packet: dict[str, Any], output_path: Path) -> str:
    lines = [
        "## StrategyGroup Owner Progress",
        "",
        f"- 报告时间: {packet['generated_at_utc']}",
        "- 主链路: 等待可执行机会",
        "- 策略观察层: review-only 证据闭合已完成",
        "- 实盘权限变化: 否",
        "- Owner 当前要决策: 是，限于策略政策方向",
        "- Runtime Owner 介入: 否",
        "",
    ]
    lines.extend(_owner_projection_lines(packet["owner_progress_projection"]))
    lines.extend(
        [
            "",
            "## Next Policy Decisions",
            "",
            "| Card | Default recommendation |",
            "| --- | --- |",
        ]
    )
    for card in packet["next_owner_decision_package"]["cards"]:
        lines.append(
            f"| `{card['card_id']}` | `{card['default_recommendation']}` |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- 不授权真实下单、FinalGate、Operation Layer、tier policy、live profile、registry admission 或 member live scope expansion。",
            f"- Output: `{output_path}`",
            "",
        ]
    )
    return "\n".join(lines)


def _owner_projection_lines(projection: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## Owner Progress Projection",
        "",
        f"- Owner summary: {projection['owner_summary']}",
        f"- P0 state: `{projection['p0_state']}`",
        f"- P0.5 state: `{projection['p0_5_state']}`",
        f"- Evidence packets: `{projection['evidence_packet_count']}`",
        f"- No live permission: `{str(projection['no_live_permission']).lower()}`",
        "",
        "| StrategyGroup | Owner state | Closure status | Closure result | Live permission |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in projection["rows"]:
        lines.append(
            "| `{}` | {} | `{}` | `{}` | `false` |".format(
                row["strategy_group_id"],
                row.get("owner_state") or "-",
                row.get("evidence_closure_status") or "-",
                row.get("closure_result") or "-",
            )
        )
    return lines


def _load_json_object(path: Path, *, required: bool = True) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if not required:
            return {}
        raise SystemExit(f"missing JSON input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON input: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"JSON input must be an object: {path}")
    return data


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _generic_why_not_live() -> str:
    return (
        "review-only evidence requires fresh signal, live RequiredFacts, "
        "candidate/auth evidence, action-time FinalGate, official Operation "
        "Layer, protection, account, and exchange facts before any live submit."
    )


if __name__ == "__main__":
    raise SystemExit(main())
