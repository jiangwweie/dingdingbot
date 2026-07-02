#!/usr/bin/env python3
"""Build the review-only StrategyGroup deep-dive wave.

This command continues the six approved review-only lanes until each lane has a
next Owner policy point. It is local evidence synthesis only: it does not
mutate registry authority, tier policy, live profile, FinalGate, Operation
Layer, exchange state, or orders.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    review_only_forbidden_effects,
    review_only_interaction,
    review_only_legacy_authority_mirror_true_keys,
    review_only_safety_invariants,
)

DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-deep-dive-wave.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-deep-dive-wave.md"
)
DEFAULT_OUTPUT_OWNER_POLICY = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-deep-dive-owner-policy.md"
)

SCHEMA = "brc.strategygroup_review_only_deep_dive_wave.v1"

REVIEW_ORDER = (
    "BRF-001",
    "BTPC-001",
    "LSR-001",
    "MI-001",
    "CPM-RO-001",
    "MPG-001",
)

FORBIDDEN_EFFECTS = review_only_forbidden_effects()
LEGACY_AUTHORITY_MIRROR_TRUE_KEYS = review_only_legacy_authority_mirror_true_keys()

DEEP_DIVE_SPECS: dict[str, dict[str, Any]] = {
    "BRF-001": {
        "owner_label": "熊市反弹失败",
        "executed_system_action": "build_brf_requiredfacts_squeeze_classifier_replay_pack",
        "diagnostic_conclusion": (
            "BRF showed a real bear-rally-failure capture gap, but promotion "
            "quality is still constrained by squeeze risk, pending forward "
            "outcome, and RequiredFacts readiness."
        ),
        "recommendation": (
            "continue_promote_review_but_hold_l1_until_squeeze_and_forward_outcome_complete"
        ),
        "owner_policy_question": (
            "BRF-001 是否继续 promote-review 证据线，但暂不升 tier、不扩大实盘范围。"
        ),
        "next_if_approved": (
            "build_brf_squeeze_classifier_requiredfacts_forward_outcome_v2"
        ),
        "owner_policy_type": "promote_review_outcome",
        "options": [
            "continue_promote_review_without_tier_change",
            "keep_l1_observe_until_forward_outcome_completes",
            "pause_brf_until_squeeze_classifier_improves",
        ],
        "policy_effects_blocked": ["tier_policy_change", "live_scope_change"],
        "findings": [
            "would_enter evidence exists, but the latest would_enter forward outcome is not enough to justify promotion",
            "missed no_action forward positives indicate capture quality work is still useful",
            "squeeze classifier and RequiredFacts should be completed before any L2 review",
        ],
    },
    "BTPC-001": {
        "owner_label": "熊市回抽延续",
        "executed_system_action": "run_btpc_false_positive_and_fact_attachment_review",
        "diagnostic_conclusion": (
            "BTPC is not simply idle; the dominant issue is systemic stale/fact "
            "source/classifier blocking. Gate relaxation remains unsafe before "
            "live fact-source attachment is closed."
        ),
        "recommendation": (
            "keep_l2_shadow_attach_fact_sources_before_any_gate_relaxation"
        ),
        "owner_policy_question": (
            "BTPC-001 是否继续 L2 shadow，并先完成事实源挂接，而不是放松 stale gate。"
        ),
        "next_if_approved": "attach_btpc_live_fact_sources_then_rerun_false_negative_review",
        "owner_policy_type": "l2_shadow_revise_boundary",
        "options": [
            "keep_l2_shadow_attach_sources_first",
            "prepare_conditional_gate_relax_review_after_sources",
            "park_btpc_until_edge_reappears",
        ],
        "policy_effects_blocked": ["stale_gate_relaxation", "tier_policy_change"],
        "findings": [
            "all audited BTPC windows were blocked by stale/fact-source attribution",
            "missed forward positives make the false-negative review material",
            "live RequiredFacts gaps remain and prevent promotion or live authority",
        ],
    },
    "LSR-001": {
        "owner_label": "流动性扫盘/短线复活",
        "executed_system_action": "build_lsr_range_context_requiredfacts_replay_pack",
        "diagnostic_conclusion": (
            "LSR short-revival has positive observe-only evidence, but the "
            "sample is small and range-context facts must be formalized before "
            "tier or live-scope changes."
        ),
        "recommendation": (
            "formalize_short_revival_rewrite_keep_l1_until_range_facts_complete"
        ),
        "owner_policy_question": (
            "LSR-001 是否正式采用 short-revival rewrite 方向，并保持 observe-only。"
        ),
        "next_if_approved": "build_lsr_short_revival_v2_range_context_fixture",
        "owner_policy_type": "short_revival_rewrite_outcome",
        "options": [
            "formalize_short_revival_rewrite",
            "keep_l1_generic_observe",
            "park_lsr_until_sample_size_improves",
        ],
        "policy_effects_blocked": ["live_scope_change", "l1_to_l2_promotion"],
        "findings": [
            "both would_enter samples are forward-positive in the source artifact",
            "side-specific short semantics still need separation from long preview logic",
            "range-context RequiredFacts remain review-only and not live authority",
        ],
    },
    "MI-001": {
        "owner_label": "MI 身份复核",
        "executed_system_action": "build_mi_registry_handoff_draft_without_admission",
        "diagnostic_conclusion": (
            "MI is the strongest identity-review candidate in this wave. It has "
            "high would_enter volume and forward-positive concentration, but "
            "registry identity, overlap, and concentration are unresolved."
        ),
        "recommendation": (
            "open_formal_candidate_review_without_registry_admission"
        ),
        "owner_policy_question": (
            "MI-001 是否进入正式候选复核，同时暂不进入 registry、不扩大实盘。"
        ),
        "next_if_approved": "open_mi_identity_overlap_symbol_concentration_review",
        "owner_policy_type": "registry_identity_candidate_review",
        "options": [
            "formal_candidate_review_without_admission",
            "mpg_support_capability_review",
            "observe_asset_only",
            "park_mi",
        ],
        "policy_effects_blocked": ["registry_admission", "live_scope_change"],
        "findings": [
            "would_enter count and forward-positive ratio are materially stronger than most observe-only lanes",
            "identity is still outside the current registry authority",
            "overlap with MPG or adjacent momentum capability must be resolved before admission",
        ],
    },
    "CPM-RO-001": {
        "owner_label": "CPM-RO 合并复核",
        "executed_system_action": "build_cpm_ro_merge_target_review_without_registry_admission",
        "diagnostic_conclusion": (
            "CPM-RO has meaningful signal evidence, but the quality is mixed "
            "relative to MI and its family boundary is unresolved. Observation "
            "asset plus merge review is the safer next policy direction."
        ),
        "recommendation": (
            "keep_observation_asset_run_merge_review_before_independent_admission"
        ),
        "owner_policy_question": (
            "CPM-RO-001 是否保留观察资产并进入 merge review，而不是独立 admission。"
        ),
        "next_if_approved": "open_cpm_ro_semantic_source_merge_quality_review",
        "owner_policy_type": "registry_identity_merge_review",
        "options": [
            "observe_asset_and_merge_review",
            "independent_strategy_review",
            "merge_into_existing_family",
            "park_cpm_ro",
        ],
        "policy_effects_blocked": ["registry_admission", "live_scope_change"],
        "findings": [
            "would_enter evidence is meaningful but lower quality than MI",
            "merge target across CPM, RBR, or momentum families is unresolved",
            "independent admission would be premature without semantic source review",
        ],
    },
    "MPG-001": {
        "owner_label": "动量延续成员治理",
        "executed_system_action": "build_mpg_member_scoring_and_decay_controls",
        "diagnostic_conclusion": (
            "MPG remains the selected L4 live lane, but there is no executable "
            "fresh signal now. Member roles and exit-decay policy can be "
            "decided without expanding member live scope."
        ),
        "recommendation": (
            "accept_member_role_split_hold_member_live_scope_until_exit_decay_review"
        ),
        "owner_policy_question": (
            "MPG-001 是否接受 member role split 和 exit-decay 复核，但不扩大 member live scope。"
        ),
        "next_if_approved": "build_mpg_member_role_controls_v2_without_live_scope_expansion",
        "owner_policy_type": "member_role_exit_decay_boundary",
        "options": [
            "accept_member_role_split_without_live_expansion",
            "keep_mpg_single_l4_box",
            "freeze_member_review",
        ],
        "policy_effects_blocked": ["mpg_member_live_scope_expansion", "live_profile_change"],
        "findings": [
            "six member roles are present and can be separated for policy review",
            "exit horizons and decay controls exist as review inputs",
            "no member receives live scope from this deep-dive artifact",
        ],
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-closure-wave-json")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument(
        "--output-owner-policy",
        dest="output_owner_policy",
        default=str(DEFAULT_OUTPUT_OWNER_POLICY),
    )
    parser.add_argument(
        "--output-owner-decision",
        dest="output_owner_policy",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    review_artifact = build_review_only_deep_dive_wave(
        evidence_closure_wave=_load_json_object(Path(args.evidence_closure_wave_json))
        if args.evidence_closure_wave_json
        else {}
    )

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_owner_policy = Path(args.output_owner_policy)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_owner_policy.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(review_artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_md.write_text(_markdown(review_artifact, output_json), encoding="utf-8")
    output_owner_policy.write_text(
        _owner_policy_markdown(review_artifact, output_owner_policy),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"status": review_artifact["status"], "output_json": str(output_json)},
            ensure_ascii=False,
        )
    )
    return 0


def build_review_only_deep_dive_wave(
    *,
    evidence_closure_wave: dict[str, Any],
) -> dict[str, Any]:
    _validate_evidence_closure_wave(evidence_closure_wave)
    source_artifact_rows = _dict_rows(
        evidence_closure_wave.get("evidence_closure_artifacts")
    )
    source_artifacts = {
        str(artifact.get("strategy_group_id")): artifact
        for artifact in source_artifact_rows
    }
    missing = [group for group in REVIEW_ORDER if group not in source_artifacts]
    if missing:
        raise ValueError("missing evidence closure artifacts: " + ", ".join(missing))

    deep_dive_artifacts = [
        _deep_dive_artifact_for_group(group, source_artifacts[group])
        for group in REVIEW_ORDER
    ]
    owner_policy_items = [_owner_policy_item(artifact) for artifact in deep_dive_artifacts]

    return {
        "schema": SCHEMA,
        "scope": "strategygroup_review_only_six_line_deep_dive",
        "status": "review_only_deep_dive_ready_for_owner_policy",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase_status": {
            "phase_1_owner_perception_projection": "ready",
            "phase_2_six_line_deep_dive": "ready",
            "phase_3_owner_policy_package": "ready_for_owner_policy_review",
        },
        "closed_problem": (
            "The six review-only lanes now have concrete diagnostic conclusions "
            "and next Owner policy choices without changing live authority."
        ),
        "deep_dive_artifacts": deep_dive_artifacts,
        "owner_policy_package": {
            "status": "owner_policy_package_ready",
            "owner_policy_item_count": len(owner_policy_items),
            "owner_policy_confirmation_required_now": True,
            "runtime_owner_intervention_required": False,
            "items": owner_policy_items,
        },
        "owner_progress_projection": _owner_progress_projection(deep_dive_artifacts),
        "completion_boundary": {
            "current_stage": "six_line_deep_dive_ready_for_owner_policy_review",
            "owner_policy_confirmation_required_now": True,
            "runtime_owner_intervention_required": False,
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
            "allowed_without_owner_input": [
                "rerun local review-only deep-dive synthesis",
                "refresh read-only evidence",
                "keep P0 live-submit standby waiting for fresh signal",
            ],
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
        "source_status": {
            "evidence_closure_wave": evidence_closure_wave.get("status"),
        },
    }


def _validate_evidence_closure_wave(artifact: dict[str, Any]) -> None:
    if artifact.get("status") != "review_only_evidence_closure_wave_ready":
        raise ValueError(
            "evidence closure wave is not ready: " + str(artifact.get("status"))
        )
    safety = _as_dict(artifact.get("safety_invariants"))
    forbidden = [key for key in FORBIDDEN_EFFECTS if safety.get(key) is True]
    if forbidden:
        raise ValueError("evidence closure wave has forbidden effects: " + str(forbidden))
    legacy_mirrors = [
        key
        for key in LEGACY_AUTHORITY_MIRROR_TRUE_KEYS
        if safety.get(key) is True
    ]
    if legacy_mirrors:
        raise ValueError(
            "evidence closure wave has legacy authority mirrors: "
            + str(legacy_mirrors)
        )
    interaction = _as_dict(artifact.get("interaction"))
    if _int(interaction.get("remote_interaction_count")) != 0:
        raise ValueError("evidence closure wave is not local-only")


def _deep_dive_artifact_for_group(
    group: str, source_artifact: dict[str, Any]
) -> dict[str, Any]:
    spec = DEEP_DIVE_SPECS[group]
    counts = _as_dict(source_artifact.get("source_counts"))
    would_enter = _int(counts.get("would_enter_count"))
    would_enter_positive = _int(counts.get("would_enter_forward_positive_count"))
    no_action = _int(counts.get("no_action_count"))
    missed_positive = _int(counts.get("missed_no_action_forward_positive_count"))
    positive_total = _int(counts.get("positive_forward_outcome_count"))

    artifact: dict[str, Any] = {
        "strategy_group_id": group,
        "owner_label": spec["owner_label"],
        "status": "review_only_deep_dive_ready_for_owner_policy",
        "review_only": True,
        "executed_system_action": spec["executed_system_action"],
        "source_closure_result": source_artifact.get("closure_result"),
        "source_counts": {
            "would_enter_count": would_enter,
            "would_enter_forward_positive_count": would_enter_positive,
            "no_action_count": no_action,
            "missed_no_action_forward_positive_count": missed_positive,
            "positive_forward_outcome_count": positive_total,
            "would_enter_forward_positive_ratio": _ratio(
                would_enter_positive, would_enter
            ),
            "missed_positive_no_action_ratio": _ratio(missed_positive, no_action),
        },
        "diagnostic_conclusion": spec["diagnostic_conclusion"],
        "deep_dive_findings": list(spec["findings"]),
        "evidence_for": list(_list(source_artifact.get("evidence_for"))),
        "evidence_against": list(_list(source_artifact.get("evidence_against"))),
        "residual_uncertainties": _residual_uncertainties(group, source_artifact),
        "recommended_owner_policy": spec["recommendation"],
        "owner_policy_type": spec["owner_policy_type"],
        "owner_policy_question": spec["owner_policy_question"],
        "owner_policy_options": list(spec["options"]),
        "strategy_review_checkpoint_if_approved": spec["next_if_approved"],
        "policy_effects_blocked": list(spec["policy_effects_blocked"]),
        "does_not_authorize_live_execution": True,
        "safety_invariants": _safety_invariants(),
    }
    if group == "BTPC-001":
        artifact["btpc_attribution"] = _btpc_attribution(
            _as_dict(source_artifact.get("btpc_attribution"))
        )
    if group == "MPG-001":
        artifact["member_review"] = _as_dict(source_artifact.get("member_review"))
    return artifact


def _btpc_attribution(source: dict[str, Any]) -> dict[str, Any]:
    return dict(source)


def _owner_policy_item(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy_item_id": f"{artifact['strategy_group_id']}:deep_dive_owner_policy",
        "strategy_group_id": artifact["strategy_group_id"],
        "owner_label": artifact["owner_label"],
        "owner_policy_type": artifact["owner_policy_type"],
        "question": artifact["owner_policy_question"],
        "default_recommendation": artifact["recommended_owner_policy"],
        "options": artifact["owner_policy_options"],
        "evidence_for": artifact["evidence_for"],
        "evidence_against": artifact["evidence_against"],
        "diagnostic_conclusion": artifact["diagnostic_conclusion"],
        "strategy_review_checkpoint_if_approved": artifact["strategy_review_checkpoint_if_approved"],
        "policy_effects_blocked": artifact["policy_effects_blocked"],
        "does_not_authorize_live_execution": True,
    }


def _owner_progress_projection(deep_dive_artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "six_line_deep_dive_owner_progress_ready",
        "owner_summary": (
            "P0 主链路等待可执行机会；Signal Observation 六条策略复核线已深挖到下一轮 "
            "Owner 政策决策点；实盘权限没有变化。"
        ),
        "p0_state": "waiting_for_market",
        "p0_owner_label": "主链路等待机会",
        "signal_observation_review_state": (
            "six_line_review_ready_for_owner_policy_review"
        ),
        "signal_observation_owner_label": "六条策略复核线等待政策决策",
        "deep_dive_artifact_count": len(deep_dive_artifacts),
        "next_owner_policy_item_count": len(deep_dive_artifacts),
        "no_live_permission": True,
        "owner_intervention_required": False,
        "owner_policy_confirmation_required_now": True,
        "rows": [
            {
                "strategy_group_id": artifact["strategy_group_id"],
                "owner_label": artifact["owner_label"],
                "status": artifact["status"],
                "recommended_owner_policy": artifact["recommended_owner_policy"],
                "does_not_authorize_live_execution": True,
            }
            for artifact in deep_dive_artifacts
        ],
    }


def _residual_uncertainties(group: str, source_artifact: dict[str, Any]) -> list[str]:
    if group == "BRF-001":
        return [
            "latest would_enter forward outcome remains insufficient for promotion",
            "squeeze-risk classifier is not yet a promotion-quality control",
            "RequiredFacts are not live-authority facts",
        ]
    if group == "BTPC-001":
        attribution = _as_dict(source_artifact.get("btpc_attribution"))
        return [
            f"live_required_fact_gap_count={_int(attribution.get('live_required_fact_gap_count'))}",
            f"source_attachment_pending_count={_int(attribution.get('source_attachment_pending_count'))}",
            "stale-gate relaxation remains blocked until fact sources are attached",
        ]
    if group == "LSR-001":
        return [
            "sample size remains small",
            "short-revival and long-preview semantics still need separation",
            "range-context RequiredFacts are not live authority",
        ]
    if group == "MI-001":
        return [
            "registry identity is unresolved",
            "overlap with MPG or adjacent momentum capability remains unresolved",
            "symbol concentration still needs review before admission",
        ]
    if group == "CPM-RO-001":
        return [
            "merge target is unresolved",
            "forward quality is mixed relative to MI",
            "independent admission is not justified by this review artifact",
        ]
    if group == "MPG-001":
        return [
            "no fresh executable signal exists for the P0 live lane",
            "member roles are review inputs, not live-scope grants",
            "exit-decay controls must be accepted before any member expansion review",
        ]
    return []


def _interaction() -> dict[str, Any]:
    return review_only_interaction("L0_local_review_only_deep_dive")


def _safety_invariants() -> dict[str, bool]:
    return review_only_safety_invariants(
        include_order_sizing_changed=True,
        include_authority_mirrors=False,
    )


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## StrategyGroup Review-Only Deep-Dive Wave",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Deep-dive artifacts: `{len(artifact['deep_dive_artifacts'])}`",
        "- Owner policy confirmation required: "
        + _yes_no(artifact["owner_policy_package"]["owner_policy_confirmation_required_now"]),
        "- Runtime Owner intervention required: "
        + _yes_no(artifact["owner_policy_package"]["runtime_owner_intervention_required"]),
        f"- Output: `{output_json}`",
        "",
        "## Deep-Dive Results",
        "",
        "| StrategyGroup | Diagnostic conclusion | Recommended Owner policy | Live permission |",
        "| --- | --- | --- | --- |",
    ]
    for item in artifact["deep_dive_artifacts"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{item['strategy_group_id']}`",
                    str(item["diagnostic_conclusion"]),
                    f"`{item['recommended_owner_policy']}`",
                    "`false`",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- 不授权真实下单、FinalGate、Operation Layer、registry admission、tier policy、live profile 或 member live scope expansion。",
            "- 当前停止点是 Owner 策略政策决策，不是 Runtime 故障处理。",
        ]
    )
    return "\n".join(lines) + "\n"


def _owner_policy_markdown(artifact: dict[str, Any], output_path: Path) -> str:
    lines = [
        "## StrategyGroup Deep-Dive Owner Policy Package",
        "",
        "- 主链路: 等待可执行机会",
        "- 策略复核层: 六条线已深挖完成",
        "- 实盘权限变化: 否",
        "- Owner 当前要决策: 是，限于策略政策方向",
        "- Runtime Owner 介入: 否",
        f"- Output: `{output_path}`",
        "",
        "## Policy Policy items",
        "",
        "| StrategyGroup | 推荐决策 | 备选项 | 不授权 |",
        "| --- | --- | --- | --- |",
    ]
    for policy_item in artifact["owner_policy_package"]["items"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{policy_item['strategy_group_id']}`",
                    f"`{policy_item['default_recommendation']}`",
                    ", ".join(f"`{item}`" for item in policy_item["options"]),
                    "真实下单 / 提权 / registry admission",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Questions", ""])
    for policy_item in artifact["owner_policy_package"]["items"]:
        lines.append(f"- `{policy_item['strategy_group_id']}`: {policy_item['question']}")
    return "\n".join(lines) + "\n"


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {path}")
    return payload


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _ratio(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0/0"
    return f"{numerator}/{denominator}"


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


if __name__ == "__main__":
    raise SystemExit(main())
