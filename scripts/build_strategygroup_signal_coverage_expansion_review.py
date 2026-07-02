#!/usr/bin/env python3
"""Build a read-only review artifact for StrategyGroup coverage expansion.

The input is a signal coverage diagnostic artifact. The output explains whether
broader observe-only would-enter signals should trigger an observation-scope
review. It never promotes a StrategyGroup into real-order eligibility and never
creates runtime, candidate, FinalGate, Operation Layer, or order actions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, NamedTuple


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategygroup_non_executing_projection import (  # noqa: E402
    legacy_authority_mirror_effects_for_artifacts,
    non_executing_interaction,
    non_executing_safety_boundary,
    review_outcome_default_next_step,
    review_outcome_state_boundary,
    source_forbidden_effects,
)


DEFAULT_SIGNAL_COVERAGE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-diagnostic.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_EXPANSION_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-signal-coverage-expansion-policy.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-expansion-review.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-expansion-review.md"
)


class SignalCoverageArtifactView(NamedTuple):
    artifact: dict[str, Any]
    broader_observation: dict[str, Any]
    checks: dict[str, Any]
    would_enter_signals: list[dict[str, Any]]
    high_priority_no_action_signals: list[dict[str, Any]]


def build_signal_coverage_expansion_review(
    *,
    signal_coverage_artifact: dict[str, Any],
    tier_policy: dict[str, Any],
    expansion_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    coverage = _signal_coverage_artifact_view(signal_coverage_artifact)
    would_enter = coverage.would_enter_signals
    current_tiers = _current_tiers(tier_policy)
    new_default_tiers = _new_default_tiers(tier_policy)
    policy_groups = _as_dict(_as_dict(expansion_policy).get("strategy_groups"))
    review_rows = [
        _review_row(
            signal=row,
            current_tiers=current_tiers,
            new_default_tiers=new_default_tiers,
            expansion_policy=_as_dict(
                policy_groups.get(str(row.get("strategy_group_id") or ""))
            ),
        )
        for row in would_enter
    ]
    actionable_review_rows = [
        row for row in review_rows if _row_needs_priority_review(row)
    ]
    observation_layer = _observation_layer_summary(
        signal_coverage=coverage,
        review_rows=review_rows,
    )
    no_action_attribution_queue = _no_action_attribution_queue(
        coverage
    )
    role_review_rows = _role_review_rows(
        signal_coverage=coverage,
        review_rows=review_rows,
    )
    forbidden_effects = _forbidden_effects(coverage)

    if forbidden_effects:
        status = "blocked_forbidden_effect"
        owner_state = "needs_intervention"
        next_step = "review_signal_coverage_source_forbidden_effects"
    elif actionable_review_rows:
        status = "review_needed_broader_observe_only_would_enter"
        owner_state = "coverage_review_needed"
        next_step = "review_observe_only_expansion_candidates"
    elif review_rows:
        status = "low_priority_observe_only_would_enter_parked"
        owner_state = "waiting_for_opportunity"
        next_step = "continue_mainline_and_keep_low_priority_observation_parked"
    else:
        status = "no_expansion_review_needed"
        owner_state = "waiting_for_opportunity"
        next_step = "continue_mainline_and_replay_monitoring"

    return {
        "scope": "strategygroup_signal_coverage_expansion_review",
        "status": status,
        "owner_state": owner_state,
        "source_signal_coverage_status": signal_coverage_artifact.get("status"),
        "interaction": non_executing_interaction(
            "L0_local_signal_coverage_expansion_review"
        ),
        "counts": {
            "broader_would_enter_signal_count": len(would_enter),
            "review_row_count": len(review_rows),
            "actionable_review_row_count": len(actionable_review_rows),
            "low_priority_or_parked_review_row_count": (
                len(review_rows) - len(actionable_review_rows)
            ),
            "new_strategy_group_review_count": sum(
                1 for row in review_rows if row["source_category"] == "new_default"
            ),
            "current_strategy_group_review_count": sum(
                1 for row in review_rows if row["source_category"] == "current"
            ),
            "high_priority_no_action_attribution_count": len(
                no_action_attribution_queue
            ),
            "role_review_row_count": len(role_review_rows),
            "forbidden_effect_count": len(forbidden_effects),
        },
        "observation_layer": observation_layer,
        "review_rows": review_rows,
        "role_review_rows": role_review_rows,
        "no_action_attribution_queue": no_action_attribution_queue,
        "review_outcome_state": review_outcome_state_boundary(
            source_role="signal_coverage_expansion_review_provenance",
            review_scope="signal_coverage_expansion_review",
            extra={
                "observation_scope_review_recommended": bool(actionable_review_rows),
                "low_priority_observation_recorded": bool(review_rows)
                and not actionable_review_rows,
                "role_review_recorded": bool(role_review_rows),
                "no_action_attribution_queue_recorded": bool(
                    no_action_attribution_queue
                ),
                "real_order_scope_change_recommended": False,
                "l4_promotion_recommended": False,
                "default_next_step": next_step,
                "reason": (
                    "broader_observe_only_would_enter_signals_exist"
                    if review_rows
                    else "no_broader_would_enter_signal"
                ),
            },
        ),
        "safety_invariants": non_executing_safety_boundary(
            true_keys=(
                "review_only",
                "input_is_not_execution_authority",
                "does_not_expand_l4_real_order_scope",
                "does_not_modify_runtime_scope",
            ),
            false_keys=(
                "server_interaction",
                "server_files_mutated",
                "runtime_started",
                "strategy_parameters_changed",
                "tier_policy_changed",
                "shadow_candidate_created",
                "final_gate_called",
                "operation_layer_called",
                "order_created",
                "order_lifecycle_called",
                "exchange_write_called",
                "withdrawal_or_transfer_created",
            ),
            source_forbidden_effects=forbidden_effects,
        ),
    }


def render_owner_progress_markdown(artifact: dict[str, Any]) -> str:
    lines = [
        "# 策略观察面扩展评审",
        "",
        "## Owner 摘要",
        "",
        f"- Status: `{artifact.get('status')}`",
        f"- Owner state: `{artifact.get('owner_state')}`",
        f"- Broader would-enter: `{_as_dict(artifact.get('counts')).get('broader_would_enter_signal_count', 0)}`",
        f"- High-priority no-action attribution: `{_as_dict(artifact.get('counts')).get('high_priority_no_action_attribution_count', 0)}`",
        f"- Role review rows: `{_as_dict(artifact.get('counts')).get('role_review_row_count', 0)}`",
        "- 实盘范围变更建议: `false`",
        "- L4 晋级建议: `false`",
        "",
        "## 观察级机会",
        "",
        _review_table(_dict_rows(artifact.get("review_rows"))),
        "",
        "## Role Review",
        "",
        _role_review_table(_dict_rows(artifact.get("role_review_rows"))),
        "",
        "## No-Action 归因队列",
        "",
        _no_action_table(_dict_rows(artifact.get("no_action_attribution_queue"))),
        "",
        "## 安全边界",
        "",
        "- 不修改策略参数",
        "- 不修改 tier policy",
        "- 不扩大 L4 实盘范围",
        "- 不调用 FinalGate / Operation Layer",
        "- 不创建订单或 exchange write",
        "",
        "## 下一步",
        "",
        f"- `{review_outcome_default_next_step(artifact)}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _observation_layer_summary(
    *,
    signal_coverage: SignalCoverageArtifactView,
    review_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    checks = signal_coverage.checks
    would_enter = signal_coverage.would_enter_signals
    high_priority_no_action = signal_coverage.high_priority_no_action_signals
    actionable_count = _int(
        checks.get("broader_actionable_would_enter_signal_count")
    )
    latest = would_enter[0] if would_enter else {}
    return {
        "p0_state": "waiting_for_executable_fresh_signal",
        "signal_observation_state": (
            "observation_active"
            if would_enter or high_priority_no_action
            else "quiet"
        ),
        "mainline_ready_signal_count": _int(
            checks.get("mainline_ready_signal_count")
        ),
        "broader_would_enter_count": len(would_enter),
        "broader_actionable_would_enter_count": actionable_count,
        "high_priority_no_action_count": len(high_priority_no_action),
        "latest_observe_only_would_enter": {
            "strategy_group_id": str(latest.get("strategy_group_id") or ""),
            "symbol": str(latest.get("symbol") or ""),
            "side": str(latest.get("side") or ""),
            "confidence": str(latest.get("confidence") or ""),
            "source": "signal_coverage_broader_observation",
            "not_live_signal": True,
        }
        if latest
        else {},
        "review_row_strategy_group_ids": [
            str(row.get("strategy_group_id") or "") for row in review_rows
        ],
    }


def _review_row(
    *,
    signal: dict[str, Any],
    current_tiers: dict[str, str],
    new_default_tiers: dict[str, str],
    expansion_policy: dict[str, Any],
) -> dict[str, Any]:
    strategy_group_id = str(signal.get("strategy_group_id") or "unknown")
    normalized_key = _normalize_strategy_group_key(strategy_group_id)
    if strategy_group_id in current_tiers:
        source_category = "current"
        current_tier = current_tiers[strategy_group_id]
    elif normalized_key in new_default_tiers:
        source_category = "new_default"
        current_tier = new_default_tiers[normalized_key]
    else:
        source_category = "unknown"
        current_tier = "unclassified"

    return {
        "strategy_group_id": strategy_group_id,
        "normalized_key": normalized_key,
        "source_category": source_category,
        "current_tier": current_tier,
        "symbol": signal.get("symbol"),
        "side": signal.get("side"),
        "confidence": signal.get("confidence"),
        "reason_codes": [str(item) for item in signal.get("reason_codes") or []],
        "coverage_review_priority": str(
            expansion_policy.get("coverage_review_priority") or "unknown"
        ),
        "policy_l2_readiness": str(
            expansion_policy.get("l2_readiness") or "unknown"
        ),
        "policy_recommended_action": str(
            expansion_policy.get("recommended_action") or "require_policy_review"
        ),
        "suggested_scope_action": _suggested_scope_action(
            source_category=source_category,
            current_tier=current_tier,
        ),
        "suggested_next_tier": _suggested_next_tier(
            source_category=source_category,
            current_tier=current_tier,
        ),
        "may_place_real_order_after_this_review": False,
        "requires_owner_live_lane_change_for_l4": True,
        "execution_boundary": _execution_boundary(current_tier=current_tier),
    }


def _role_review_rows(
    *,
    signal_coverage: SignalCoverageArtifactView,
    review_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    review_by_group = {
        str(row.get("strategy_group_id") or ""): row for row in review_rows
    }
    for signal in signal_coverage.would_enter_signals:
        group = str(signal.get("strategy_group_id") or "")
        if group != "RBR-001":
            continue
        review_row = review_by_group.get(group, {})
        rows.append(
            {
                "source_observation_strategy_group_id": group,
                "source_observation_symbol": str(signal.get("symbol") or ""),
                "source_observation_side": str(signal.get("side") or ""),
                "source_observation_type": "observe_only_would_enter",
                "linked_intake_strategy_group_id": "RBR2-001",
                "role_review_outcome": "review_range_detector_role_not_live_candidate",
                "required_next_evidence": (
                    "compare_rbr001_observe_only_signal_with_rbr2_range_detector_role"
                ),
                "next_checkpoint": (
                    "RBR_RBR2_role_review_range_detector_classifier_merge_note"
                ),
                "authority_boundary": (
                    "role_review_only; no_finalgate_no_operation_layer; "
                    "no_exchange_write"
                ),
                "policy_recommended_action": str(
                    review_row.get("policy_recommended_action") or ""
                ),
                "reason_codes": [
                    str(item) for item in signal.get("reason_codes") or []
                ],
            }
        )
    return rows


def _no_action_attribution_queue(
    signal_coverage: SignalCoverageArtifactView,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in signal_coverage.high_priority_no_action_signals:
        group = str(row.get("strategy_group_id") or "unknown")
        reason_codes = [str(item) for item in row.get("reason_codes") or []]
        rows.append(
            {
                "strategy_group_id": group,
                "symbol": str(row.get("symbol") or ""),
                "side": str(row.get("side") or ""),
                "confidence": str(row.get("confidence") or ""),
                "attribution_class": _no_action_attribution_class(row),
                "reason_codes": reason_codes,
                "required_next_evidence": _no_action_required_next_evidence(row),
                "next_checkpoint": _no_action_next_checkpoint(row),
                "authority_boundary": (
                    "no_action_attribution_only; no_finalgate_no_operation_layer; "
                    "no_exchange_write"
                ),
            }
        )
    return rows


def _no_action_attribution_class(row: dict[str, Any]) -> str:
    text = " ".join(
        [
            str(row.get("policy_l2_readiness") or ""),
            str(row.get("policy_recommended_action") or ""),
            " ".join(str(item) for item in row.get("reason_codes") or []),
        ]
    )
    if "squeeze" in text or "rally" in text:
        return "market_structure_or_path_risk"
    if "rewrite" in text:
        return "side_specific_rewrite"
    if "classifier" in text or "volume" in text:
        return "classifier_or_threshold"
    if "fact" in text or "stale" in text:
        return "fact_source_or_freshness"
    return "review_required"


def _no_action_required_next_evidence(row: dict[str, Any]) -> str:
    klass = _no_action_attribution_class(row)
    if klass == "fact_source_or_freshness":
        return "freshness_and_fact_source_mapping"
    if klass == "side_specific_rewrite":
        return "side_specific_rewrite_review"
    if klass == "classifier_or_threshold":
        return "classifier_threshold_review"
    if klass == "market_structure_or_path_risk":
        return "market_structure_and_path_risk_review"
    return "next_high_priority_replay_or_market_observation"


def _no_action_next_checkpoint(row: dict[str, Any]) -> str:
    group = str(row.get("strategy_group_id") or "unknown")
    return f"{group}_{_no_action_required_next_evidence(row)}"


def _row_needs_priority_review(row: dict[str, Any]) -> bool:
    priority = str(row.get("coverage_review_priority") or "unknown")
    readiness = str(row.get("policy_l2_readiness") or "unknown")
    if priority in {"P2", "P2_low", "low"}:
        return False
    if readiness == "blocked_parked_negative_evidence":
        return False
    return True


def _suggested_scope_action(*, source_category: str, current_tier: str) -> str:
    if current_tier == "L0":
        return "consider_l1_observe_only_intake"
    if current_tier == "L1":
        return "keep_l1_observe_only_and_review_for_l2_shadow_candidate"
    if current_tier == "L2":
        return "review_shadow_candidate_quality"
    if current_tier == "L3":
        return "review_armed_observation_quality"
    if current_tier == "L4":
        return "keep_official_runtime_chain_boundary"
    if source_category == "unknown":
        return "require_handoff_classification_before_observation"
    return "review_strategygroup_scope"


def _suggested_next_tier(*, source_category: str, current_tier: str) -> str:
    if source_category == "unknown":
        return "L0_or_L1_after_handoff"
    if current_tier == "L1":
        return "L2_after_handoff_review_and_dry_run"
    return current_tier


def _execution_boundary(*, current_tier: str) -> str:
    if current_tier == "L1":
        return "observe-only; no candidate/order"
    if current_tier == "L2":
        return "shadow review only; no FinalGate/Operation Layer"
    if current_tier == "L3":
        return "armed observation review; no Operation Layer"
    if current_tier == "L4":
        return "official chain only; preview is not submit authority"
    return "handoff classification required before observation"


def _normalize_strategy_group_key(strategy_group_id: str) -> str:
    if strategy_group_id.endswith("-001"):
        return strategy_group_id[:-4]
    return strategy_group_id


def _current_tiers(tier_policy: dict[str, Any]) -> dict[str, str]:
    current = _as_dict(tier_policy.get("current_strategy_groups"))
    return {
        str(key): str(_as_dict(value).get("tier"))
        for key, value in current.items()
        if _as_dict(value).get("tier")
    }


def _new_default_tiers(tier_policy: dict[str, Any]) -> dict[str, str]:
    defaults = _as_dict(tier_policy.get("new_strategy_group_defaults"))
    known = _as_dict(defaults.get("known_new_groups"))
    return {str(key): str(value) for key, value in known.items() if str(value)}


def _forbidden_effects(signal_coverage: SignalCoverageArtifactView) -> list[str]:
    checks = signal_coverage.checks
    effects = source_forbidden_effects(
        (("", signal_coverage.artifact),),
        true_keys=(
            "shadow_candidate_created",
            "execution_intent_created",
            "final_gate_called",
            "operation_layer_called",
            "order_created",
            "order_lifecycle_called",
            "exchange_write_called",
            "withdrawal_or_transfer_created",
        ),
    )
    effects.extend(str(item) for item in checks.get("forbidden_effects") or [])
    effects.extend(_legacy_authority_mirror_effects(signal_coverage))
    return sorted(set(effect for effect in effects if effect))


def _legacy_authority_mirror_effects(
    signal_coverage: SignalCoverageArtifactView,
) -> list[str]:
    artifact = signal_coverage.artifact
    broader = signal_coverage.broader_observation
    source_view = {
        **artifact,
        "checks": signal_coverage.checks,
        "broader_observation": broader,
        "would_enter_signals": signal_coverage.would_enter_signals,
        "high_priority_no_action_signals": signal_coverage.high_priority_no_action_signals,
    }
    return legacy_authority_mirror_effects_for_artifacts(
        (("signal_coverage", source_view),),
        root_section_name="root",
        section_names=(
            "checks",
            "broader_observation",
            "safety_invariants",
            "review_outcome_state",
        ),
        row_names=("would_enter_signals", "high_priority_no_action_signals"),
        row_id_keys=("strategy_group_id", "symbol", "signal_type"),
    )


def _signal_coverage_artifact_view(
    artifact: dict[str, Any],
) -> SignalCoverageArtifactView:
    broader = _as_dict(artifact.get("broader_observation"))
    return SignalCoverageArtifactView(
        artifact=artifact,
        broader_observation=broader,
        checks=_as_dict(artifact.get("checks")),
        would_enter_signals=_dict_rows(broader.get("would_enter_signals")),
        high_priority_no_action_signals=_dict_rows(
            broader.get("high_priority_no_action_signals")
        ),
    )


def _review_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "| StrategyGroup | Symbol | Side | Confidence | Tier | Next tier | Action | Boundary |\n"
            "| --- | --- | --- | ---: | --- | --- | --- | --- |\n"
            "| none | - | - | - | - | - | - | - |"
        )
    output = [
        "| StrategyGroup | Symbol | Side | Confidence | Tier | Next tier | Action | Boundary |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("symbol"),
                row.get("side"),
                row.get("confidence"),
                row.get("current_tier"),
                row.get("suggested_next_tier"),
                row.get("suggested_scope_action"),
                row.get("execution_boundary"),
            )
        )
    return "\n".join(output)


def _role_review_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "| Source | Linked Intake | Role Review | Next |\n"
            "| --- | --- | --- | --- |\n"
            "| none | - | - | - |"
        )
    output = [
        "| Source | Linked Intake | Role Review | Next |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row.get("source_observation_strategy_group_id"),
                row.get("linked_intake_strategy_group_id"),
                row.get("role_review_outcome"),
                row.get("next_checkpoint"),
            )
        )
    return "\n".join(output)


def _no_action_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "| StrategyGroup | Symbol | Class | Next |\n"
            "| --- | --- | --- | --- |\n"
            "| none | - | - | - |"
        )
    output = [
        "| StrategyGroup | Symbol | Class | Next |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("symbol"),
                row.get("attribution_class"),
                row.get("next_checkpoint"),
            )
        )
    return "\n".join(output)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-coverage-json", default=str(DEFAULT_SIGNAL_COVERAGE_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument(
        "--expansion-policy-json",
        default=str(DEFAULT_EXPANSION_POLICY_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    artifact = build_signal_coverage_expansion_review(
        signal_coverage_artifact=_load_json_object(
            Path(args.signal_coverage_json).expanduser()
        ),
        tier_policy=_load_json_object(Path(args.tier_policy_json).expanduser()),
        expansion_policy=_load_json_object(Path(args.expansion_policy_json).expanduser()),
    )
    payload = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    if args.output_owner_progress:
        owner_path = Path(args.output_owner_progress).expanduser()
        owner_path.parent.mkdir(parents=True, exist_ok=True)
        owner_path.write_text(render_owner_progress_markdown(artifact), encoding="utf-8")
    print(payload)
    return 0 if artifact["status"] != "blocked_forbidden_effect" else 2


if __name__ == "__main__":
    raise SystemExit(main())
