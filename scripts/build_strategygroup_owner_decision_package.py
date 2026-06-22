#!/usr/bin/env python3
"""Build Owner-ready StrategyGroup decision cards and policy packet.

This command consumes current local StrategyGroup audit, ledger, replay, and
quality-closure evidence, then projects them into Owner-readable decision cards.
It is local review support only. It never changes StrategyGroup policy, tier,
live profile, runtime scope, FinalGate, Operation Layer, or exchange state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CAPTURE_GAP_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/strategy-capture-gap-audit-20260622.json"
)
DEFAULT_QUALITY_CLOSURE_WAVE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-quality-closure-wave.json"
)
DEFAULT_DECISION_LEDGER_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-decision-ledger.json"
)
DEFAULT_REGISTRY_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
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
DEFAULT_OPPORTUNITY_DECISION_LOOP_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-opportunity-decision-loop.json"
)
DEFAULT_MPG_REPLAY_CORPUS_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/MPG-001/replay/mpg-001-replay-corpus.json"
)
DEFAULT_BRF_REPLAY_CORPUS_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/BRF-001/replay/brf-001-l1-observe-replay-corpus.json"
)
DEFAULT_LSR_REPLAY_CORPUS_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/LSR-001/replay/lsr-001-l1-observe-replay-corpus.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-owner-decision-package.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-owner-decision-package.md"
)

PRIMARY_DECISION_GROUPS = (
    "BRF-001",
    "BTPC-001",
    "LSR-001",
    "MI-001",
    "CPM-RO-001",
)
SNAPSHOT_GROUPS = (
    "MPG-001",
    "BRF-001",
    "BTPC-001",
    "LSR-001",
    "MI-001",
    "CPM-RO-001",
    "RBR-001",
    "VCB-001",
)

OWNER_LABEL_FALLBACKS = {
    "MI-001": "动量冲击",
    "CPM-RO-001": "CPM 回补观察",
}

STRATEGY_DECISION_SPECS = {
    "BRF-001": {
        "decision_type": "promote_review_direction",
        "owner_decision_question": "是否允许 BRF-001 进入下一层 promote review，而不是直接进入实盘。",
        "default_recommendation": "approve_promote_review_without_live_scope_change",
        "owner_summary": "BRF 已看到熊市反弹失败 short 结构，但 squeeze 与 RequiredFacts 仍要先复核。",
        "next_if_approved": "build_brf_squeeze_requiredfacts_forward_outcome_review",
        "next_if_rejected": "keep_brf_l1_observe_until_new_structure",
        "decision_options": [
            {
                "option_id": "approve_promote_review",
                "label": "进入晋级复核",
                "meaning": "允许系统继续做 squeeze、RequiredFacts、forward outcome 复核。",
                "tradeoff": "不会增加实盘权限，但会把 BRF 放入更高优先级策略治理。",
            },
            {
                "option_id": "keep_l1_observe",
                "label": "继续 L1 观察",
                "meaning": "保留 BRF 观察，不进入下一层晋级复核。",
                "tradeoff": "降低误升风险，但可能继续错过 bear-rally failure 结构学习。",
            },
            {
                "option_id": "park_until_squeeze_review",
                "label": "暂缓",
                "meaning": "先不推进 BRF，除非 squeeze 风险材料更清楚。",
                "tradeoff": "最保守，但会延后 BRF 捕获质量闭合。",
            },
        ],
    },
    "BTPC-001": {
        "decision_type": "keep_l2_shadow_or_revise_gate",
        "owner_decision_question": "是否保持 BTPC-001 为 L2 shadow，并继续修 fact-source 与 classifier，而不是放松 stale gate 或停车。",
        "default_recommendation": "keep_l2_shadow_and_revise_fact_classifier_inputs",
        "owner_summary": "BTPC 不是简单没机会，而是 stale/fact-source/classifier 阻断过强，当前适合保持 L2 shadow 并修输入。",
        "next_if_approved": "continue_btpc_fact_source_attachment_and_classifier_review",
        "next_if_rejected": "park_btpc_or_wait_for_live_fact_source_before_any_more_review",
        "decision_options": [
            {
                "option_id": "keep_l2_shadow_revise",
                "label": "保持 L2 并修输入",
                "meaning": "继续 L2 shadow，不改实盘权限，补事实源与分类器归因。",
                "tradeoff": "保留右尾学习机会，但需要继续投入事实源修复。",
            },
            {
                "option_id": "wait_fact_source",
                "label": "等事实源",
                "meaning": "不做策略方向判断，先等 live derivatives / margin 事实源接完。",
                "tradeoff": "证据更稳，但当前 169 次 stale 误杀无法快速收敛。",
            },
            {
                "option_id": "relax_gate_after_false_positive_review",
                "label": "有条件放松",
                "meaning": "只在 false-positive 风险复核完成后讨论 stale gate 放松。",
                "tradeoff": "可能提高捕获率，但不能在当前包内直接落地。",
            },
            {
                "option_id": "park_btpc",
                "label": "停车",
                "meaning": "停止 BTPC 近期推进。",
                "tradeoff": "减少治理复杂度，但放弃当前最多的 missed no-action 正向窗口。",
            },
        ],
    },
    "LSR-001": {
        "decision_type": "formalize_short_revival_rewrite",
        "owner_decision_question": "是否把 LSR-001 的 short-revival 语义正式化为复核方向，并保持 observe-only。",
        "default_recommendation": "formalize_short_revival_rewrite_without_live_scope_change",
        "owner_summary": "LSR 有 2 个 would_enter 且 forward outcome 为正，适合继续做 side-specific rewrite。",
        "next_if_approved": "build_lsr_short_revival_range_context_requiredfacts_review",
        "next_if_rejected": "keep_lsr_generic_observe_or_park",
        "decision_options": [
            {
                "option_id": "formalize_short_revival",
                "label": "正式化 short-revival",
                "meaning": "把 short-revival 作为 LSR 下一轮主复核语义。",
                "tradeoff": "可捕获已出现的正向窗口，但要解决 long/short 语义冲突。",
            },
            {
                "option_id": "keep_observe",
                "label": "继续观察",
                "meaning": "不正式化 rewrite，只保留 L1 观察。",
                "tradeoff": "安全但会延迟 LSR 捕获质量闭合。",
            },
            {
                "option_id": "park_lsr",
                "label": "停车",
                "meaning": "暂停 LSR 复核。",
                "tradeoff": "减少维护，但放弃已有正向样本。",
            },
        ],
    },
    "MI-001": {
        "decision_type": "registry_identity",
        "owner_decision_question": "MI-001 应作为正式候选、MPG 子能力、观察资产，还是停车。",
        "default_recommendation": "open_formal_candidate_review_and_overlap_check",
        "owner_summary": "MI-001 的 would_enter 和 forward positive 很强，不能继续只当 smoke lane。",
        "next_if_approved": "build_mi_identity_overlap_symbol_concentration_packet",
        "next_if_rejected": "keep_mi_observe_asset_without_registry_admission",
        "decision_options": [
            {
                "option_id": "formal_candidate_review",
                "label": "正式候选复核",
                "meaning": "进入策略柜候选复核，但不进入实盘。",
                "tradeoff": "最大化学习价值，但需要补语义、重叠和集中度证据。",
            },
            {
                "option_id": "mpg_support_capability",
                "label": "MPG 子能力",
                "meaning": "作为 MPG 的动量冲击 member/scorer 复核。",
                "tradeoff": "减少独立策略复杂度，但可能掩盖 MI 自身 edge。",
            },
            {
                "option_id": "observe_asset",
                "label": "观察资产",
                "meaning": "保留信号观察，不进入正式候选。",
                "tradeoff": "治理轻，但强样本无法进入主学习闭环。",
            },
            {
                "option_id": "park",
                "label": "停车",
                "meaning": "认为语义不足或过拟合风险高，暂不推进。",
                "tradeoff": "最保守，但与当前 23/22 正向证据冲突。",
            },
        ],
    },
    "CPM-RO-001": {
        "decision_type": "registry_identity",
        "owner_decision_question": "CPM-RO-001 应独立、合并、作为观察资产，还是停车。",
        "default_recommendation": "keep_as_observation_asset_and_run_merge_review",
        "owner_summary": "CPM-RO 有 would_enter 与正向 outcome，但质量混杂且注册身份不清。",
        "next_if_approved": "build_cpm_ro_semantic_source_merge_quality_packet",
        "next_if_rejected": "park_cpm_ro_until_identity_evidence_improves",
        "decision_options": [
            {
                "option_id": "independent_strategy_review",
                "label": "独立策略复核",
                "meaning": "作为独立策略组候选继续做 handoff / RequiredFacts。",
                "tradeoff": "可能保留新 edge，但会增加策略柜复杂度。",
            },
            {
                "option_id": "merge_into_existing_family",
                "label": "合并",
                "meaning": "合并进 CPM/RBR/momentum 相关家族。",
                "tradeoff": "治理更简洁，但需要确认不会损失独立语义。",
            },
            {
                "option_id": "observe_asset",
                "label": "观察资产",
                "meaning": "保留观察，不进入正式候选。",
                "tradeoff": "适合当前 13/18 的混杂质量。",
            },
            {
                "option_id": "park",
                "label": "停车",
                "meaning": "暂不推进，除非后续 forward quality 改善。",
                "tradeoff": "减少噪声，但可能错过中等质量机会。",
            },
        ],
    },
}

MPG_MEMBER_POLICY = [
    {
        "member_id": "TSI-001",
        "decision_recommendation": "keep_core_candidate_with_decay_control",
        "owner_label": "保留核心候选",
    },
    {
        "member_id": "MHI-001",
        "decision_recommendation": "downshift_or_park_before_live_expansion",
        "owner_label": "降权或停车复核",
    },
    {
        "member_id": "PPO-001",
        "decision_recommendation": "keep_support_member",
        "owner_label": "保留支持 member",
    },
    {
        "member_id": "DMI-001",
        "decision_recommendation": "resolve_member_vs_independent_identity",
        "owner_label": "身份边界复核",
    },
    {
        "member_id": "WPR-001",
        "decision_recommendation": "keep_confirmation_member",
        "owner_label": "保留确认器",
    },
    {
        "member_id": "MFI-001",
        "decision_recommendation": "keep_scorer_not_primary",
        "owner_label": "保留为 scorer / risk damper",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-gap-audit-json", default=str(DEFAULT_CAPTURE_GAP_AUDIT_JSON))
    parser.add_argument("--quality-closure-wave-json", default=str(DEFAULT_QUALITY_CLOSURE_WAVE_JSON))
    parser.add_argument("--decision-ledger-json", default=str(DEFAULT_DECISION_LEDGER_JSON))
    parser.add_argument("--registry-json", default=str(DEFAULT_REGISTRY_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument("--btpc-fact-quality-json", default=str(DEFAULT_BTPC_FACT_QUALITY_JSON))
    parser.add_argument("--btpc-source-mapping-json", default=str(DEFAULT_BTPC_SOURCE_MAPPING_JSON))
    parser.add_argument("--btpc-classifier-review-json", default=str(DEFAULT_BTPC_CLASSIFIER_REVIEW_JSON))
    parser.add_argument("--btpc-keep-revise-json", default=str(DEFAULT_BTPC_KEEP_REVISE_JSON))
    parser.add_argument("--btpc-proxy-replay-json", default=str(DEFAULT_BTPC_PROXY_REPLAY_JSON))
    parser.add_argument("--opportunity-decision-loop-json", default=str(DEFAULT_OPPORTUNITY_DECISION_LOOP_JSON))
    parser.add_argument("--mpg-replay-corpus-json", default=str(DEFAULT_MPG_REPLAY_CORPUS_JSON))
    parser.add_argument("--brf-replay-corpus-json", default=str(DEFAULT_BRF_REPLAY_CORPUS_JSON))
    parser.add_argument("--lsr-replay-corpus-json", default=str(DEFAULT_LSR_REPLAY_CORPUS_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    packet = build_owner_decision_package(
        capture_gap_audit=_load_json_object(Path(args.capture_gap_audit_json)),
        quality_closure_wave=_load_json_object(Path(args.quality_closure_wave_json)),
        decision_ledger=_load_json_object(Path(args.decision_ledger_json)),
        registry=_load_json_object(Path(args.registry_json)),
        tier_policy=_load_json_object(Path(args.tier_policy_json)),
        btpc_fact_quality=_load_json_object(Path(args.btpc_fact_quality_json)),
        btpc_source_mapping=_load_json_object(Path(args.btpc_source_mapping_json)),
        btpc_classifier_review=_load_json_object(Path(args.btpc_classifier_review_json)),
        btpc_keep_revise=_load_json_object(Path(args.btpc_keep_revise_json)),
        btpc_proxy_replay=_load_json_object(Path(args.btpc_proxy_replay_json)),
        opportunity_decision_loop=_load_json_object(Path(args.opportunity_decision_loop_json)),
        mpg_replay_corpus=_load_json_object(Path(args.mpg_replay_corpus_json)),
        brf_replay_corpus=_load_json_object(Path(args.brf_replay_corpus_json)),
        lsr_replay_corpus=_load_json_object(Path(args.lsr_replay_corpus_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_md.write_text(_markdown(packet, output_json, output_md), encoding="utf-8")
    print(json.dumps({"status": packet["status"], "output_json": str(output_json)}, ensure_ascii=False))
    return 0


def build_owner_decision_package(
    *,
    capture_gap_audit: dict[str, Any],
    quality_closure_wave: dict[str, Any],
    decision_ledger: dict[str, Any],
    registry: dict[str, Any],
    tier_policy: dict[str, Any],
    btpc_fact_quality: dict[str, Any],
    btpc_source_mapping: dict[str, Any],
    btpc_classifier_review: dict[str, Any],
    btpc_keep_revise: dict[str, Any],
    btpc_proxy_replay: dict[str, Any],
    opportunity_decision_loop: dict[str, Any],
    mpg_replay_corpus: dict[str, Any],
    brf_replay_corpus: dict[str, Any],
    lsr_replay_corpus: dict[str, Any],
) -> dict[str, Any]:
    registry_by_group = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(registry.get("rows"))
    }
    ledger_by_group = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(decision_ledger.get("ledger_rows"))
    }
    audit_by_group = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(capture_gap_audit.get("strategy_expectation_rows"))
    }
    current_tiers = _current_tiers(tier_policy, registry_by_group)
    wave_cards_by_group = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(
            _as_dict(quality_closure_wave.get("wave_1_strategy_explainer")).get("cards")
        )
    }
    wave_2_by_group = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(
            _as_dict(quality_closure_wave.get("wave_2_capture_quality_closure")).get("rows")
        )
    }

    strategy_quality_snapshot = _strategy_quality_snapshot(
        capture_gap_audit,
        audit_by_group,
        registry_by_group,
        ledger_by_group,
        current_tiers,
    )
    decision_cards = [
        _strategy_decision_card(
            group,
            audit_row=audit_by_group.get(group, {}),
            registry_row=registry_by_group.get(group, {}),
            ledger_row=ledger_by_group.get(group, {}),
            wave_card=wave_cards_by_group.get(group, {}),
            wave_2_row=wave_2_by_group.get(group, {}),
            current_tier=current_tiers.get(group, "unknown"),
            btpc_fact_quality=btpc_fact_quality,
            btpc_source_mapping=btpc_source_mapping,
            btpc_classifier_review=btpc_classifier_review,
            btpc_keep_revise=btpc_keep_revise,
            btpc_proxy_replay=btpc_proxy_replay,
            brf_replay_corpus=brf_replay_corpus,
            lsr_replay_corpus=lsr_replay_corpus,
        )
        for group in PRIMARY_DECISION_GROUPS
    ]
    mpg_member_decision_card = _mpg_member_decision_card(
        quality_closure_wave,
        mpg_replay_corpus,
        registry_by_group.get("MPG-001", {}),
        current_tiers.get("MPG-001", "unknown"),
    )
    closure_tracks = _closure_tracks(decision_cards, mpg_member_decision_card)
    decision_cards.append(mpg_member_decision_card)

    decision_count = len(decision_cards)
    return {
        "schema": "brc.strategygroup_owner_decision_package.v1",
        "scope": "strategy_perception_evidence_closure_wave",
        "status": "owner_decision_package_ready",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "closed_engineering_problem": (
            "Strategy observations are now converted into Owner-ready decision "
            "cards with default recommendations, counterevidence, risks, and "
            "next system actions."
        ),
        "capability_unlocked": (
            "Owner can decide strategy policy direction without reading raw "
            "would_enter/no_action rows or replay packets."
        ),
        "next_engineering_bottleneck": (
            "Owner policy confirmation is required before promote, park, kill, "
            "registry admission, tier policy, member live scope, or live-profile changes."
        ),
        "source_status": {
            "capture_gap_audit": capture_gap_audit.get("status"),
            "quality_closure_wave": quality_closure_wave.get("status"),
            "decision_ledger": decision_ledger.get("status"),
            "registry": registry.get("status"),
            "btpc_fact_quality": btpc_fact_quality.get("status"),
            "btpc_source_mapping": btpc_source_mapping.get("status"),
            "btpc_classifier_review": btpc_classifier_review.get("status"),
            "btpc_keep_revise": btpc_keep_revise.get("status"),
            "btpc_proxy_replay": btpc_proxy_replay.get("status"),
            "opportunity_decision_loop": opportunity_decision_loop.get("status"),
        },
        "strategy_quality_snapshot": strategy_quality_snapshot,
        "closure_tracks": closure_tracks,
        "owner_decision_cards": decision_cards,
        "owner_decision_summary": {
            "owner_policy_decision_required": True,
            "runtime_owner_intervention_required": False,
            "decision_count": decision_count,
            "ready_decision_count": sum(1 for card in decision_cards if card["decision_ready"]),
            "default_recommendations": [
                {
                    "card_id": card["card_id"],
                    "strategy_group_id": card["strategy_group_id"],
                    "default_recommendation": card["default_recommendation"],
                }
                for card in decision_cards
            ],
            "hard_stop": (
                "Do not promote, park, kill, change registry authority, change tier policy, "
                "change live profile, expand MPG member live scope, or expand real-order scope "
                "without Owner confirmation."
            ),
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
    }


def _strategy_quality_snapshot(
    capture_gap_audit: dict[str, Any],
    audit_by_group: dict[str, dict[str, Any]],
    registry_by_group: dict[str, dict[str, Any]],
    ledger_by_group: dict[str, dict[str, Any]],
    current_tiers: dict[str, str],
) -> dict[str, Any]:
    visibility = _as_dict(capture_gap_audit.get("owner_visibility_state"))
    rows = []
    for group in SNAPSHOT_GROUPS:
        audit = audit_by_group.get(group, {})
        ledger = ledger_by_group.get(group, {})
        rows.append(
            {
                "strategy_group_id": group,
                "owner_label": _owner_label(group, registry_by_group.get(group, {})),
                "current_tier": current_tiers.get(group, "unknown"),
                "owner_state": _owner_state(group, ledger, audit),
                "system_found": _system_found(group, audit, ledger),
                "next_step": ledger.get("next_checkpoint") or "continue_strategy_review",
                "owner_decision_ready": group in set(PRIMARY_DECISION_GROUPS) | {"MPG-001"},
                "no_live_permission": True,
            }
        )
    return {
        "status": "ready",
        "p0_state": visibility.get("p0_state", "waiting_for_market"),
        "p0_5_observation_state": visibility.get("p0_5_observation_state", "review_needed"),
        "observation_active": bool(visibility.get("observation_active", True)),
        "owner_intervention_required": False,
        "owner_summary": (
            "P0 waits for executable fresh signal; P0.5 has Owner-ready "
            "StrategyGroup decision cards; no live permission change."
        ),
        "rows": rows,
    }


def _strategy_decision_card(
    group: str,
    *,
    audit_row: dict[str, Any],
    registry_row: dict[str, Any],
    ledger_row: dict[str, Any],
    wave_card: dict[str, Any],
    wave_2_row: dict[str, Any],
    current_tier: str,
    btpc_fact_quality: dict[str, Any],
    btpc_source_mapping: dict[str, Any],
    btpc_classifier_review: dict[str, Any],
    btpc_keep_revise: dict[str, Any],
    btpc_proxy_replay: dict[str, Any],
    brf_replay_corpus: dict[str, Any],
    lsr_replay_corpus: dict[str, Any],
) -> dict[str, Any]:
    spec = STRATEGY_DECISION_SPECS[group]
    evidence = _audit_evidence(audit_row)
    extra = _extra_evidence(
        group,
        audit_row=audit_row,
        btpc_fact_quality=btpc_fact_quality,
        btpc_source_mapping=btpc_source_mapping,
        btpc_classifier_review=btpc_classifier_review,
        btpc_keep_revise=btpc_keep_revise,
        btpc_proxy_replay=btpc_proxy_replay,
        brf_replay_corpus=brf_replay_corpus,
        lsr_replay_corpus=lsr_replay_corpus,
    )
    return {
        "card_id": f"{group}:owner_policy_decision",
        "card_type": "strategy_policy_decision",
        "strategy_group_id": group,
        "owner_label": _owner_label(group, registry_row),
        "current_tier": current_tier,
        "ledger_decision": ledger_row.get("decision", "unknown"),
        "decision_type": spec["decision_type"],
        "decision_ready": True,
        "owner_policy_decision_required": True,
        "runtime_owner_intervention_required": False,
        "owner_decision_question": spec["owner_decision_question"],
        "owner_summary": spec["owner_summary"],
        "default_recommendation": spec["default_recommendation"],
        "decision_options": spec["decision_options"],
        "evidence_for": _evidence_for(group, evidence, extra),
        "evidence_against": _evidence_against(group, evidence, extra),
        "open_risks": _open_risks(group, evidence, extra),
        "evidence_summary": evidence,
        "specialized_evidence": extra,
        "why_not_live": wave_card.get("why_not_live")
        or registry_row.get("actionable_now_reason")
        or "decision packet is review-only and cannot authorize execution",
        "next_system_action_if_approved": spec["next_if_approved"],
        "next_system_action_if_rejected": spec["next_if_rejected"],
        "next_checkpoint": ledger_row.get("next_checkpoint")
        or wave_2_row.get("next_checkpoint")
        or "continue_strategy_review",
        "not_authorized": _not_authorized(),
        "authority_boundary": _authority_boundary(),
    }


def _mpg_member_decision_card(
    quality_closure_wave: dict[str, Any],
    mpg_replay_corpus: dict[str, Any],
    registry_row: dict[str, Any],
    current_tier: str,
) -> dict[str, Any]:
    wave_3 = _as_dict(quality_closure_wave.get("wave_3_mpg_member_deepening"))
    member_rows = _dict_rows(wave_3.get("member_rows"))
    by_member = {str(row.get("member_id")): row for row in member_rows}
    replay_samples = _dict_rows(mpg_replay_corpus.get("replay_samples"))
    member_decisions = []
    for spec in MPG_MEMBER_POLICY:
        member_id = spec["member_id"]
        row = by_member.get(member_id, {})
        member_decisions.append(
            {
                "member_id": member_id,
                "owner_label": spec["owner_label"],
                "provisional_role": row.get("provisional_role", "unknown"),
                "review_focus": row.get("review_focus", "member_policy_review"),
                "default_recommendation": spec["decision_recommendation"],
                "source_recommendation": row.get("recommended_action"),
                "live_scope_allowed_now": False,
            }
        )
    return {
        "card_id": "MPG-001:member_policy_decision",
        "card_type": "mpg_member_policy_decision",
        "strategy_group_id": "MPG-001",
        "owner_label": _owner_label("MPG-001", registry_row),
        "current_tier": current_tier,
        "ledger_decision": "keep_observing",
        "decision_type": "member_tiering_exit_decay_policy",
        "decision_ready": True,
        "owner_policy_decision_required": True,
        "runtime_owner_intervention_required": False,
        "owner_decision_question": (
            "是否接受 MPG member 角色拆分与 exit/decay 复核方向，且不扩实盘范围。"
        ),
        "owner_summary": "MPG 主线仍等 fresh signal，但 member 风险差异已经足够进入政策复核。",
        "default_recommendation": "approve_member_role_split_without_live_scope_expansion",
        "decision_options": [
            {
                "option_id": "approve_member_role_split",
                "label": "接受 member 角色拆分",
                "meaning": "按 TSI/MHI/PPO/DMI/WPR/MFI 的默认角色继续复核。",
                "tradeoff": "能降低 MPG 黑盒风险，但仍不授权任何 member 实盘扩围。",
            },
            {
                "option_id": "keep_mpg_as_single_l4_box",
                "label": "保持 MPG 单一黑盒",
                "meaning": "暂不拆 member 角色。",
                "tradeoff": "治理简单，但无法解释收益强与回撤重的来源。",
            },
            {
                "option_id": "freeze_member_review",
                "label": "冻结 member 复核",
                "meaning": "暂不推进 MPG member 层。",
                "tradeoff": "避免过度治理，但会保留当前 member 风险不透明问题。",
            },
        ],
        "member_decisions": member_decisions,
        "evidence_for": [
            f"MPG replay sample count: {len(replay_samples)}",
            "six member roles are present in the quality closure wave",
            "exit horizons and decay controls are present before any live expansion",
        ],
        "evidence_against": [
            "current package does not prove which member should receive live scope",
            "member-level evidence remains review-only and not action-time live facts",
        ],
        "open_risks": [
            "MHI high-return/high-drawdown survivability",
            "TSI right-tail decay and post-spike giveback",
            "DMI identity boundary between MPG member and independent observer",
        ],
        "evidence_summary": {
            "replay_sample_count": len(replay_samples),
            "member_count": len(member_decisions),
            "exit_decay_review": wave_3.get("exit_decay_review"),
        },
        "specialized_evidence": {
            "wave_3_status": wave_3.get("status"),
            "done_when": wave_3.get("done_when"),
        },
        "why_not_live": "MPG member review is policy evidence only and cannot expand L4 live scope",
        "next_system_action_if_approved": "build_mpg_member_exit_decay_policy_packet",
        "next_system_action_if_rejected": "keep_mpg_member_layer_observe_only",
        "next_checkpoint": "MPG-001_member_tiering_exit_decay_review",
        "not_authorized": _not_authorized(),
        "authority_boundary": _authority_boundary(),
    }


def _closure_tracks(
    cards: list[dict[str, Any]],
    mpg_card: dict[str, Any],
) -> list[dict[str, Any]]:
    by_group = {card["strategy_group_id"]: card for card in cards}
    return [
        {
            "track_id": "P0.5-A",
            "name": "Strategy Quality Snapshot",
            "status": "ready",
            "done_when": "Owner can see P0 waiting plus P0.5 strategy-review activity.",
        },
        _track("P0.5-B", "BRF squeeze / RequiredFacts / forward outcome review", by_group["BRF-001"]),
        _track("P0.5-C", "BTPC stale / fact-source / classifier attribution closure", by_group["BTPC-001"]),
        _track("P0.5-D", "LSR side-specific rewrite evidence closure", by_group["LSR-001"]),
        _track("P0.5-E", "MI-001 identity packet", by_group["MI-001"]),
        _track("P0.5-F", "CPM-RO-001 identity packet", by_group["CPM-RO-001"]),
        _track("P0.5-G", "MPG member role / exit-decay / risk boundary review", mpg_card),
    ]


def _track(track_id: str, name: str, card: dict[str, Any]) -> dict[str, Any]:
    return {
        "track_id": track_id,
        "name": name,
        "status": "ready_for_owner_decision",
        "card_id": card["card_id"],
        "default_recommendation": card["default_recommendation"],
        "decision_ready": card["decision_ready"],
    }


def _audit_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "would_enter_count": _int(row.get("would_enter_count")),
        "no_action_count": _int(row.get("no_action_count")),
        "high_priority_no_action_count": _int(row.get("high_priority_no_action_count")),
        "would_enter_forward_positive_count": _int(row.get("would_enter_forward_positive_count")),
        "missed_no_action_forward_positive_count": _int(row.get("missed_no_action_forward_positive_count")),
        "positive_forward_outcome_count": _int(row.get("positive_forward_outcome_count")),
        "latest_event_time_utc": row.get("latest_event_time_utc"),
        "sample_reasons": row.get("sample_reasons", []),
        "dominant_blocker_classes": row.get("dominant_blocker_classes", []),
        "would_enter_forward_outcome_summary": row.get("would_enter_forward_outcome_summary", {}),
        "missed_no_action_forward_outcome_summary": row.get("missed_no_action_forward_outcome_summary", {}),
    }


def _extra_evidence(
    group: str,
    *,
    audit_row: dict[str, Any],
    btpc_fact_quality: dict[str, Any],
    btpc_source_mapping: dict[str, Any],
    btpc_classifier_review: dict[str, Any],
    btpc_keep_revise: dict[str, Any],
    btpc_proxy_replay: dict[str, Any],
    brf_replay_corpus: dict[str, Any],
    lsr_replay_corpus: dict[str, Any],
) -> dict[str, Any]:
    if group == "BTPC-001":
        return {
            "fact_gap_count": _int(_as_dict(btpc_fact_quality.get("counts")).get("fact_gap_count")),
            "fact_source_pending_count": _int(
                _as_dict(btpc_fact_quality.get("counts")).get("fact_source_pending_count")
            ),
            "live_required_fact_gap_count": _int(
                _as_dict(btpc_source_mapping.get("counts")).get("live_required_fact_gap_count")
            ),
            "source_attachment_pending_count": _int(
                _as_dict(btpc_source_mapping.get("counts")).get("source_attachment_pending_count")
            ),
            "classifier_rule_review_count": _int(
                _as_dict(btpc_classifier_review.get("counts")).get("rule_review_count")
            ),
            "proxy_reviewable_would_enter_count": _int(
                _as_dict(btpc_proxy_replay.get("counts")).get("proxy_reviewable_would_enter_count")
            ),
            "revise_case_count": _int(_as_dict(btpc_proxy_replay.get("counts")).get("freshness_or_conflict_revision_count")),
            "default_keep_revise_decision": _as_dict(btpc_keep_revise.get("decision")),
        }
    if group == "BRF-001":
        return _replay_summary(brf_replay_corpus)
    if group == "LSR-001":
        return _replay_summary(lsr_replay_corpus)
    if group in {"MI-001", "CPM-RO-001"}:
        return {
            "identity_not_in_registry": True,
            "forward_positive_ratio": _ratio(
                _int(audit_row.get("would_enter_forward_positive_count")),
                _int(audit_row.get("would_enter_count")),
            ),
        }
    return {}


def _replay_summary(corpus: dict[str, Any]) -> dict[str, Any]:
    samples = _dict_rows(corpus.get("replay_samples"))
    return {
        "replay_sample_count": len(samples),
        "review_recommendation_counts": _count_by(samples, "review_recommendation"),
        "signal_status_counts": _count_by(samples, "signal_status"),
        "required_facts_ready_count": sum(1 for row in samples if row.get("required_facts_ready") is True),
        "real_order_allowed_count": sum(1 for row in samples if row.get("real_order_allowed") is True),
    }


def _evidence_for(group: str, evidence: dict[str, Any], extra: dict[str, Any]) -> list[str]:
    if group == "BRF-001":
        return [
            f"would_enter observed: {evidence['would_enter_count']}",
            f"missed no_action forward positives: {evidence['missed_no_action_forward_positive_count']}",
            f"BRF replay sample count: {extra.get('replay_sample_count', 0)}",
        ]
    if group == "BTPC-001":
        return [
            f"high-priority stale-blocked no_action count: {evidence['high_priority_no_action_count']}",
            f"missed no_action forward positives: {evidence['missed_no_action_forward_positive_count']}",
            f"proxy reviewable would_enter count: {extra.get('proxy_reviewable_would_enter_count', 0)}",
            f"classifier rule review count: {extra.get('classifier_rule_review_count', 0)}",
        ]
    if group == "LSR-001":
        return [
            f"would_enter observed: {evidence['would_enter_count']}",
            f"would_enter forward positives: {evidence['would_enter_forward_positive_count']}",
            f"LSR replay sample count: {extra.get('replay_sample_count', 0)}",
        ]
    if group == "MI-001":
        return [
            f"would_enter observed: {evidence['would_enter_count']}",
            f"would_enter forward positives: {evidence['would_enter_forward_positive_count']}",
            f"forward positive ratio: {extra.get('forward_positive_ratio')}",
        ]
    if group == "CPM-RO-001":
        return [
            f"would_enter observed: {evidence['would_enter_count']}",
            f"would_enter forward positives: {evidence['would_enter_forward_positive_count']}",
            f"forward positive ratio: {extra.get('forward_positive_ratio')}",
        ]
    return []


def _evidence_against(group: str, evidence: dict[str, Any], extra: dict[str, Any]) -> list[str]:
    if group == "BRF-001":
        return [
            "latest would_enter forward outcome is still pending",
            "squeeze-risk replay sample recommends revise before promotion",
            "RequiredFacts review is not a live-authority packet",
        ]
    if group == "BTPC-001":
        return [
            f"live RequiredFacts gaps remain: {extra.get('live_required_fact_gap_count', 0)}",
            f"source attachments pending: {extra.get('source_attachment_pending_count', 0)}",
            "relaxing stale gate now would be a policy and safety risk",
        ]
    if group == "LSR-001":
        return [
            "sample size is small",
            "long preview and short-revival semantics still conflict",
            "range-context RequiredFacts are not yet formal live authority",
        ]
    if group == "MI-001":
        return [
            "strategy identity is not in current registry",
            "overlap with MPG / TEQ is not yet resolved",
            "symbol concentration and semantic explanation still need review",
        ]
    if group == "CPM-RO-001":
        return [
            "strategy identity is not in current registry",
            "forward quality is mixed relative to MI",
            "merge target across CPM/RBR/momentum family is unresolved",
        ]
    return []


def _open_risks(group: str, evidence: dict[str, Any], extra: dict[str, Any]) -> list[str]:
    if group == "BRF-001":
        return ["short squeeze risk", "bear rally context quality", "RequiredFacts source maturity"]
    if group == "BTPC-001":
        return ["false positives after stale-gate relaxation", "derivatives source attachment", "margin/liquidation model gap"]
    if group == "LSR-001":
        return ["side-specific rewrite ambiguity", "range context facts", "small sample count"]
    if group == "MI-001":
        return ["identity ambiguity", "overlap with MPG / TEQ", "possible overfitting despite strong forward positives"]
    if group == "CPM-RO-001":
        return ["identity ambiguity", "mixed outcome quality", "merge-vs-independent governance cost"]
    return []


def _system_found(group: str, audit: dict[str, Any], ledger: dict[str, Any]) -> str:
    if group == "MPG-001":
        return "P0 selected lane has no executable fresh signal; member review is active."
    if not audit:
        return ledger.get("reason", "strategy review pending")
    would_enter = _int(audit.get("would_enter_count"))
    missed = _int(audit.get("missed_no_action_forward_positive_count"))
    if would_enter:
        return f"observed {would_enter} would_enter events"
    if missed:
        return f"observed {missed} missed no_action forward positives"
    return ledger.get("reason", "no recent qualifying structure")


def _owner_state(group: str, ledger: dict[str, Any], audit: dict[str, Any]) -> str:
    decision = str(ledger.get("decision") or "")
    if group in {"MI-001", "CPM-RO-001"}:
        return "身份待定"
    if group == "BTPC-001" or decision == "revise":
        return "待调整"
    if decision == "promote":
        return "待复核"
    if decision == "park":
        return "已暂停"
    return "等待机会"


def _owner_label(group: str, registry_row: dict[str, Any]) -> str:
    return str(registry_row.get("owner_label") or OWNER_LABEL_FALLBACKS.get(group) or group)


def _current_tiers(
    tier_policy: dict[str, Any],
    registry_by_group: dict[str, dict[str, Any]],
) -> dict[str, str]:
    output = {
        group: str(_as_dict(data).get("tier") or "unknown")
        for group, data in _as_dict(tier_policy.get("current_strategy_groups")).items()
    }
    known_new = _as_dict(_as_dict(tier_policy.get("new_strategy_group_defaults")).get("known_new_groups"))
    for base, tier in known_new.items():
        output.setdefault(f"{base}-001", str(tier or "unknown"))
    for group, row in registry_by_group.items():
        output.setdefault(group, str(row.get("default_tier") or "unknown"))
    return output


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    output: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        output[value] = output.get(value, 0) + 1
    return dict(sorted(output.items()))


def _ratio(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0/0"
    return f"{numerator}/{denominator}"


def _interaction() -> dict[str, Any]:
    return {
        "level": "L0_local_owner_decision_package",
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


def _not_authorized() -> list[str]:
    return [
        "promote",
        "park",
        "kill",
        "registry_admission",
        "tier_policy_change",
        "live_profile_change",
        "order_sizing_change",
        "FinalGate",
        "Operation Layer",
        "exchange_write",
        "real_order",
    ]


def _authority_boundary() -> str:
    return (
        "local_review_only; Owner policy decision package; no FinalGate; no Operation Layer; "
        "no exchange write; no tier policy change; no live profile change; no real order authority"
    )


def _markdown(packet: dict[str, Any], output_json: Path, output_md: Path) -> str:
    lines = [
        "# StrategyGroup Owner Decision Package",
        "",
        "## Summary",
        "",
        f"- Status: `{packet['status']}`",
        f"- Closed problem: {packet['closed_engineering_problem']}",
        f"- Capability unlocked: {packet['capability_unlocked']}",
        f"- Next bottleneck: {packet['next_engineering_bottleneck']}",
        "- Real order authority: `false`",
        "- Live permission change: `false`",
        "",
        "## Strategy Quality Snapshot",
        "",
        "| StrategyGroup | Owner state | System found | Next step | Decision ready |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in packet["strategy_quality_snapshot"]["rows"]:
        lines.append(
            "| `{}` | {} | {} | `{}` | `{}` |".format(
                row["strategy_group_id"],
                row["owner_state"],
                row["system_found"],
                row["next_step"],
                str(row["owner_decision_ready"]).lower(),
            )
        )
    lines.extend(
        [
            "",
            "## Closure Tracks",
            "",
            "| Track | Status | Card | Default recommendation |",
            "| --- | --- | --- | --- |",
        ]
    )
    for track in packet["closure_tracks"]:
        lines.append(
            "| `{}` {} | `{}` | `{}` | `{}` |".format(
                track["track_id"],
                track["name"],
                track["status"],
                track.get("card_id", "-"),
                track.get("default_recommendation", "-"),
            )
        )
    lines.extend(
        [
            "",
            "## Owner Decision Cards",
            "",
            "| Card | Question | Default | Evidence for | Evidence against |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for card in packet["owner_decision_cards"]:
        lines.append(
            "| `{}` | {} | `{}` | {} | {} |".format(
                card["card_id"],
                card["owner_decision_question"],
                card["default_recommendation"],
                "<br>".join(card.get("evidence_for", [])) or "-",
                "<br>".join(card.get("evidence_against", [])) or "-",
            )
        )
    lines.extend(
        [
            "",
            "## Decision Options",
            "",
        ]
    )
    for card in packet["owner_decision_cards"]:
        lines.extend(
            [
                f"### {card['card_id']}",
                "",
                f"- Owner summary: {card['owner_summary']}",
                f"- Why not live: {card['why_not_live']}",
                "",
                "| Option | Meaning | Tradeoff |",
                "| --- | --- | --- |",
            ]
        )
        for option in card.get("decision_options", []):
            lines.append(
                "| `{}` {} | {} | {} |".format(
                    option["option_id"],
                    option["label"],
                    option["meaning"],
                    option["tradeoff"],
                )
            )
        if card.get("member_decisions"):
            lines.extend(
                [
                    "",
                    "| Member | Default recommendation | Live scope now |",
                    "| --- | --- | --- |",
                ]
            )
            for member in card["member_decisions"]:
                lines.append(
                    "| `{}` {} | `{}` | `{}` |".format(
                        member["member_id"],
                        member["owner_label"],
                        member["default_recommendation"],
                        str(member["live_scope_allowed_now"]).lower(),
                    )
                )
        lines.append("")
    summary = packet["owner_decision_summary"]
    lines.extend(
        [
            "## Owner Confirmation Boundary",
            "",
            f"- Owner policy decision required: `{str(summary['owner_policy_decision_required']).lower()}`",
            f"- Runtime Owner intervention required: `{str(summary['runtime_owner_intervention_required']).lower()}`",
            f"- Decision count: `{summary['decision_count']}`",
            f"- Hard stop: {summary['hard_stop']}",
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
        ]
    )
    return "\n".join(lines) + "\n"


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
