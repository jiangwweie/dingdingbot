#!/usr/bin/env python3
"""Build a review-only StrategyGroup regime-role coverage map.

The map answers whether the current StrategyGroup portfolio covers weak-market,
range, short, derivatives-stress, and momentum-impulse roles. It is an
evidence synthesis artifact only; it does not create registry authority, tier
authority, live permission, candidates, orders, or exchange writes.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategygroup_non_executing_projection import (  # noqa: E402
    LEGACY_AUTHORITY_MIRROR_KEYS,
)

DEFAULT_REGISTRY_BASELINE_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_REQUIRED_FACTS_MAP_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-required-facts-map.md"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-regime-role-coverage-map.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-regime-role-coverage-map.md"
)

SCHEMA = "brc.strategygroup_regime_role_coverage_map.v1"

ACTIVE_REVIEW_ORDER = (
    "MPG-001",
    "MI-001",
    "BRF-001",
    "BTPC-001",
    "LSR-001",
    "RBR-001",
    "VCB-001",
    "FBS-001",
    "SOR-001",
    "CPM-RO-001",
)

ACTIVE_REVIEW_GROUP_SOURCE = (
    "portfolio_board.portfolio_summary.active_review_strategy_groups"
)

TASK_RELATED_GIT_STATUS_PREFIXES = (
    "scripts/build_strategygroup_regime_role_coverage_map.py",
    "tests/unit/test_strategygroup_regime_role_coverage_map.py",
    "output/runtime-monitor/latest-strategygroup-regime-role-coverage-map",
)

ROLE_BUCKET_ORDER = (
    "trend_long",
    "momentum_impulse",
    "bear_rally_failure_short",
    "bear_pullback_continuation_short",
    "range_reversion",
    "liquidity_sweep_reversal",
    "false_breakout_or_compression_failure",
    "derivatives_stress",
    "session_structure",
    "unclear_or_identity_review",
)

ROLE_BUCKET_MEANINGS = {
    "trend_long": "多头趋势 / 动量延续",
    "momentum_impulse": "短期动量冲击 / 反弹动量",
    "bear_rally_failure_short": "熊市反弹失败做空",
    "bear_pullback_continuation_short": "熊市回抽延续做空",
    "range_reversion": "区间边界回归",
    "liquidity_sweep_reversal": "扫盘 / reclaim / rejection",
    "false_breakout_or_compression_failure": "假突破 / 压缩失败",
    "derivatives_stress": "funding / OI / basis / squeeze risk",
    "session_structure": "session range / 开盘结构",
    "unclear_or_identity_review": "身份未定",
}

STRATEGY_ROLE_SPECS: dict[str, dict[str, Any]] = {
    "MPG-001": {
        "portfolio_role": "selected long momentum trial lane",
        "side_semantics": "long momentum continuation",
        "regime_fit": "clean 1h directional persistence; not a bear/range hedge",
        "role_buckets": ["trend_long"],
        "gap_classes": ["visibility_gap", "maturity_gap"],
        "gap_reason": "L4 lane exists, but current board shows no fresh executable signal and still needs no-action visibility plus member exit-decay review.",
        "research_decision": "no_research_needed",
        "research_reason": "The role is covered in final; next work is runtime visibility and member-risk evidence, not a new research lane.",
    },
    "MI-001": {
        "portfolio_role": "high-signal momentum-impulse identity candidate",
        "side_semantics": "long or rebound impulse; registry identity unresolved",
        "regime_fit": "short-window impulse and rebound acceleration after ignition",
        "role_buckets": ["momentum_impulse", "unclear_or_identity_review"],
        "gap_classes": ["identity_gap"],
        "gap_reason": "Recent outcomes are strong, but MI is not yet a registry/tier asset and overlap with MPG or theme momentum is unresolved.",
        "research_decision": "no_research_needed",
        "research_reason": "The immediate blocker is final-side identity, overlap, concentration, and registry hygiene; bounded research is only needed if identity review splits MI into a new family.",
    },
    "BRF-001": {
        "portfolio_role": "bear rally failure promote-review lane",
        "side_semantics": "short after weak rally rejection",
        "regime_fit": "bear rally failure, rejection, structure extreme",
        "role_buckets": ["bear_rally_failure_short"],
        "gap_classes": ["maturity_gap", "fact_source_gap"],
        "gap_reason": "The role exists, but forward outcome and squeeze/RequiredFacts review remain incomplete before any promotion.",
        "research_decision": "no_research_needed",
        "research_reason": "Final already has a BRF lane; close promote-review evidence first before asking strategy research for more variants.",
    },
    "BTPC-001": {
        "portfolio_role": "bear pullback continuation L2 shadow lane",
        "side_semantics": "short continuation after weak rally or pullback",
        "regime_fit": "downtrend continuation excluding strong upside reclaim",
        "role_buckets": ["bear_pullback_continuation_short", "derivatives_stress"],
        "gap_classes": ["classifier_gap", "fact_source_gap"],
        "gap_reason": "Capture audit shows stale/fact-source blocking dominates; gate relaxation is not justified until live fact sources are attached.",
        "research_decision": "no_research_needed",
        "research_reason": "This is a final engineering closure problem first: fact-source mapping, classifier attribution, and stale-gate diagnosis.",
    },
    "LSR-001": {
        "portfolio_role": "liquidity sweep and short-revival rewrite lane",
        "side_semantics": "long observe plus short-revival review",
        "regime_fit": "sweep, reclaim, rejection, and short revival with range context",
        "role_buckets": ["liquidity_sweep_reversal", "bear_pullback_continuation_short"],
        "gap_classes": ["classifier_gap", "maturity_gap"],
        "gap_reason": "Observed samples are positive, but the side-specific rewrite and range-context RequiredFacts are not complete.",
        "research_decision": "no_research_needed",
        "research_reason": "The existing rewrite lane should be closed in final before opening a new research lane.",
    },
    "RBR-001": {
        "portfolio_role": "parked range-boundary vocabulary",
        "side_semantics": "range reversion; currently short-review vocabulary",
        "regime_fit": "calm range boundary rejection, currently weak or parked",
        "role_buckets": ["range_reversion"],
        "gap_classes": ["maturity_gap", "true_research_gap"],
        "gap_reason": "A range bucket exists, but current decision is park; active trial-quality range evidence is missing.",
        "research_decision": "bounded_research_recommended",
        "research_reason": "Final can keep RBR parked, while strategy research should explore a bounded range/reversion lane if weak-range coverage is strategically required.",
    },
    "VCB-001": {
        "portfolio_role": "volatility compression breakout observe lane",
        "side_semantics": "long breakout; false-breakout classifier required",
        "regime_fit": "compression breakout and failure/rejection regimes",
        "role_buckets": ["false_breakout_or_compression_failure"],
        "gap_classes": ["classifier_gap", "maturity_gap"],
        "gap_reason": "The role is present but still classifier-heavy; current board keeps it observe-only.",
        "research_decision": "bounded_research_recommended",
        "research_reason": "Final should keep classifier review; research can separately test false-breakout/compression-failure variants if the classifier remains weak.",
    },
    "FBS-001": {
        "portfolio_role": "derivatives-stress armed observation lane",
        "side_semantics": "funding/basis stress; long and short-disable/redesign semantics",
        "regime_fit": "funding, basis, premium, OI, crowding, squeeze-risk regimes",
        "role_buckets": ["derivatives_stress"],
        "gap_classes": ["fact_source_gap", "visibility_gap"],
        "gap_reason": "The role exists at L3, but derivatives RequiredFacts and no-action visibility must be attached before promotion.",
        "research_decision": "research_required_before_trial",
        "research_reason": "Derivative-stress coverage needs better fact source design and possibly bounded research for funding/OI/squeeze variants before trial use.",
    },
    "SOR-001": {
        "portfolio_role": "session-structure armed observation lane",
        "side_semantics": "session short plus long-revival-only conditions",
        "regime_fit": "session open, range, trigger-bar, post-open decay",
        "role_buckets": ["session_structure"],
        "gap_classes": ["visibility_gap", "maturity_gap"],
        "gap_reason": "The role exists but recent board does not show useful opportunity evidence; no-action visibility and session attribution need closure.",
        "research_decision": "bounded_research_recommended",
        "research_reason": "Final should expose no-action/session attribution; research can extend session structures if current SOR remains too narrow.",
    },
    "CPM-RO-001": {
        "portfolio_role": "mild-trend pullback observation asset",
        "side_semantics": "trend pullback entry; capture a resumed segment, identity unresolved",
        "regime_fit": "controlled pullback inside mild trend, then reclaim or bounce-loss confirmation",
        "role_buckets": ["trend_long", "unclear_or_identity_review"],
        "gap_classes": ["identity_gap", "classifier_gap"],
        "gap_reason": "CPM produced repeated would-enter evidence but remains outside registry/tier identity; overlap with MPG/BTPC/RBR/MI is unresolved.",
        "research_decision": "no_research_needed",
        "research_reason": "Immediate work is final-side merge/identity review. Research is useful only after final decides whether CPM is a standalone family.",
    },
}

REGISTRY_ONLY_NOTES = {
    "PMR-001": (
        "Registry-only in this wave: precious-metal overlay remains L1 observe-only "
        "and is not part of the active Portfolio Board / Trial Candidate Pool."
    ),
    "TEQ-001": (
        "Registry-only in this wave: equity-like momentum is L2 shadow-capable, "
        "but this task focuses on active review board gaps, not broad long-theme expansion."
    ),
}

SAFETY_INVARIANTS = {
    "calls_finalgate": False,
    "calls_operation_layer": False,
    "calls_exchange_write": False,
    "order_created": False,
    "live_profile_changed": False,
    "tier_policy_changed": False,
    "strategy_parameters_changed": False,
    "registry_authority_changed": False,
    "server_files_mutated": False,
}

FORBIDDEN_TRUE_KEYS = tuple(SAFETY_INVARIANTS)

LEGACY_AUTHORITY_MIRROR_TRUE_KEYS = LEGACY_AUTHORITY_MIRROR_KEYS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio-board-json", required=True)
    parser.add_argument("--trial-candidate-pool-md", required=True)
    parser.add_argument("--capture-gap-audit-json", required=True)
    parser.add_argument("--registry-baseline-json", default=str(DEFAULT_REGISTRY_BASELINE_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument("--required-facts-map-md", default=str(DEFAULT_REQUIRED_FACTS_MAP_MD))
    parser.add_argument("--goal-progress-json")
    parser.add_argument("--local-monitor-sequence-json")
    parser.add_argument(
        "--strategy-asset-state-json",
        dest="strategy_asset_state_source_json",
        metavar="STRATEGY_ASSET_STATE_JSON",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_regime_role_coverage_map(
        portfolio_board=_load_json_object(Path(args.portfolio_board_json)),
        trial_candidate_pool_md=_load_text(Path(args.trial_candidate_pool_md)),
        capture_gap_audit=_load_json_object(Path(args.capture_gap_audit_json)),
        registry_baseline=_load_json_object(Path(args.registry_baseline_json)),
        tier_policy=_load_json_object(Path(args.tier_policy_json)),
        required_facts_map_md=_load_text(Path(args.required_facts_map_md)),
        goal_progress=_read_optional_json(Path(args.goal_progress_json))
        if args.goal_progress_json
        else None,
        local_monitor_sequence=_read_optional_json(Path(args.local_monitor_sequence_json))
        if args.local_monitor_sequence_json
        else None,
        strategy_asset_state_source=_read_optional_json(
            Path(args.strategy_asset_state_source_json)
        )
        if args.strategy_asset_state_source_json
        else None,
        git_log_oneline_8=_git_lines(["log", "--oneline", "-8"]),
        git_status_short=_git_lines(["status", "--short"]),
    )

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_md.write_text(_markdown(artifact, output_json), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "strategy_group_count": len(artifact["strategy_group_rows"]),
                "role_bucket_count": len(artifact["role_buckets"]),
                "output_json": str(output_json),
                "output_md": str(output_md),
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_regime_role_coverage_map(
    *,
    portfolio_board: dict[str, Any],
    trial_candidate_pool_md: str,
    capture_gap_audit: dict[str, Any],
    registry_baseline: dict[str, Any],
    tier_policy: dict[str, Any],
    required_facts_map_md: str,
    goal_progress: dict[str, Any] | None = None,
    local_monitor_sequence: dict[str, Any] | None = None,
    strategy_asset_state_source: dict[str, Any] | None = None,
    git_log_oneline_8: list[str] | None = None,
    git_status_short: list[str] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    for name, source_artifact in (
        ("portfolio_board", portfolio_board),
        ("capture_gap_audit", capture_gap_audit),
        ("registry_baseline", registry_baseline),
        ("tier_policy", tier_policy),
        ("goal_progress", goal_progress),
        ("local_monitor_sequence", local_monitor_sequence),
        ("strategy_asset_state", strategy_asset_state_source),
    ):
        if source_artifact:
            _validate_review_only_safety(name, source_artifact)

    portfolio_rows = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(portfolio_board.get("portfolio_rows"))
        if row.get("strategy_group_id")
    }
    registry_rows = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(registry_baseline.get("rows"))
        if row.get("strategy_group_id")
    }
    tier_rows = {
        str(group): value
        for group, value in (tier_policy.get("current_strategy_groups") or {}).items()
        if isinstance(value, dict)
    }
    trial_pool_status = _trial_pool_status_by_group(portfolio_board)
    active_review_group_contract = _active_review_group_contract(portfolio_board)

    strategy_group_rows = []
    for group_id in active_review_group_contract["known_active_groups"]:
        row = _strategy_group_row(
            group_id=group_id,
            portfolio_row=portfolio_rows.get(group_id, {}),
            registry_row=registry_rows.get(group_id, {}),
            tier_row=tier_rows.get(group_id, {}),
            trial_pool_status=trial_pool_status.get(group_id, "not_in_trial_pool"),
        )
        strategy_group_rows.append(row)

    role_buckets = _role_buckets(strategy_group_rows)
    gap_summary = _gap_summary(strategy_group_rows, role_buckets)
    research_escalation = _research_escalation(role_buckets)
    registry_only = _registry_only_rows(registry_rows, portfolio_rows)
    source_status = _source_status(
        portfolio_board=portfolio_board,
        trial_candidate_pool_md=trial_candidate_pool_md,
        capture_gap_audit=capture_gap_audit,
        registry_baseline=registry_baseline,
        tier_policy=tier_policy,
        required_facts_map_md=required_facts_map_md,
        goal_progress=goal_progress,
        local_monitor_sequence=local_monitor_sequence,
        strategy_asset_state_source=strategy_asset_state_source,
        active_review_group_contract=active_review_group_contract,
        git_log_oneline_8=git_log_oneline_8 or [],
        git_status_short=git_status_short or [],
    )

    artifact = {
        "schema": SCHEMA,
        "status": "regime_role_coverage_map_ready",
        "scope": "local_review_only",
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_status": source_status,
        "active_review_group_contract": active_review_group_contract,
        "market_regime_assessment": _market_regime_assessment(
            capture_gap_audit, active_review_group_contract
        ),
        "role_buckets": role_buckets,
        "strategy_group_rows": strategy_group_rows,
        "gap_summary": gap_summary,
        "research_escalation_recommendations": research_escalation,
        "trial_pool_implications": _trial_pool_implications(
            portfolio_board, strategy_group_rows, role_buckets
        ),
        "registry_only_notes": registry_only,
        "safety_invariants": dict(SAFETY_INVARIANTS),
    }
    return artifact


def _strategy_group_row(
    *,
    group_id: str,
    portfolio_row: dict[str, Any],
    registry_row: dict[str, Any],
    tier_row: dict[str, Any],
    trial_pool_status: str,
) -> dict[str, Any]:
    spec = STRATEGY_ROLE_SPECS[group_id]
    blockers = _dict_rows(portfolio_row.get("dominant_blocker_classes"))
    dominant_blocker = blockers[0]["key"] if blockers else "none_recorded"
    forward = portfolio_row.get("cost_after_result_summary") or {}
    tradable_forward_count = _best_tradable_forward_count(forward)
    execution_tier = (
        portfolio_row.get("execution_tier")
        or tier_row.get("tier")
        or registry_row.get("default_tier")
        or "unknown"
    )
    current_review_checkpoint = (
        portfolio_row.get("strategy_review_checkpoint")
        or spec.get("current_review_checkpoint")
        or "no_review_checkpoint_recorded"
    )
    return {
        "strategy_group_id": group_id,
        "owner_label": portfolio_row.get("owner_label")
        or registry_row.get("owner_label")
        or group_id,
        "execution_tier": execution_tier,
        "evidence_stage": portfolio_row.get("evidence_stage")
        or registry_row.get("evidence_status")
        or "unknown",
        "portfolio_role": spec["portfolio_role"],
        "side_semantics": spec["side_semantics"],
        "regime_fit": spec["regime_fit"],
        "role_buckets": list(spec["role_buckets"]),
        "recent_opportunity_count": int(portfolio_row.get("recent_opportunity_count") or 0),
        "tradable_forward_count": int(
            portfolio_row.get("would_enter_forward_positive_count")
            if portfolio_row.get("would_enter_forward_positive_count") is not None
            else tradable_forward_count
        ),
        "no_action_count": int(portfolio_row.get("no_action_count") or 0),
        "high_priority_no_action_count": int(
            portfolio_row.get("high_priority_no_action_count") or 0
        ),
        "dominant_blocker": dominant_blocker,
        "dominant_blocker_classes": blockers,
        "gap_classes": list(spec["gap_classes"]),
        "gap_reason": spec["gap_reason"],
        "current_review_checkpoint": current_review_checkpoint,
        "trial_pool_status": trial_pool_status,
        "trial_eligible": bool(portfolio_row.get("trial_eligible", False)),
        "live_permission_change": bool(
            portfolio_row.get("live_permission_change", False)
        ),
        "research_escalation": spec["research_decision"],
        "research_reason": spec["research_reason"],
    }


def _role_buckets(strategy_group_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_bucket: dict[str, list[dict[str, Any]]] = {
        bucket: [] for bucket in ROLE_BUCKET_ORDER
    }
    for row in strategy_group_rows:
        for bucket in row["role_buckets"]:
            rows_by_bucket.setdefault(bucket, []).append(row)

    role_rows = []
    for bucket in ROLE_BUCKET_ORDER:
        rows = rows_by_bucket.get(bucket, [])
        gap_classes = sorted({gap for row in rows for gap in row["gap_classes"]})
        active_groups = [row["strategy_group_id"] for row in rows]
        if not rows:
            coverage_status = "missing"
        elif any(row["trial_pool_status"] != "not_in_trial_pool" for row in rows):
            coverage_status = "covered_in_trial_review"
        elif any(row["execution_tier"] in {"L2", "L3", "L4"} for row in rows):
            coverage_status = "covered_but_not_trial_ready"
        elif bucket == "range_reversion":
            coverage_status = "covered_parked_or_weak"
        else:
            coverage_status = "covered_low_maturity"

        role_rows.append(
            {
                "bucket": bucket,
                "meaning": ROLE_BUCKET_MEANINGS[bucket],
                "coverage_status": coverage_status,
                "strategy_groups": active_groups,
                "primary_gap_classes": gap_classes,
                "final_engineering_need": _final_need_for_bucket(bucket, rows),
                "strategy_research_need": _research_need_for_bucket(bucket, rows),
            }
        )
    return role_rows


def _gap_summary(
    strategy_group_rows: list[dict[str, Any]], role_buckets: list[dict[str, Any]]
) -> dict[str, Any]:
    by_class: dict[str, list[str]] = {}
    for row in strategy_group_rows:
        for gap in row["gap_classes"]:
            by_class.setdefault(gap, []).append(row["strategy_group_id"])

    true_missing = [
        bucket["bucket"]
        for bucket in role_buckets
        if bucket["coverage_status"] == "missing"
    ]
    return {
        "by_gap_class": {
            gap: sorted(set(groups)) for gap, groups in sorted(by_class.items())
        },
        "true_missing_role_buckets": true_missing,
        "maturity_gap_count": len(set(by_class.get("maturity_gap", []))),
        "fact_source_gap_count": len(set(by_class.get("fact_source_gap", []))),
        "classifier_gap_count": len(set(by_class.get("classifier_gap", []))),
        "visibility_gap_count": len(set(by_class.get("visibility_gap", []))),
        "identity_gap_count": len(set(by_class.get("identity_gap", []))),
        "true_research_gap_count": len(set(by_class.get("true_research_gap", []))),
        "summary": (
            "Short, range, derivatives, and weak-market roles are not absent, "
            "but most are not trial-ready. The most material true research gap "
            "is active range-reversion quality after RBR is parked; the most "
            "material final engineering gaps are BTPC facts/stale gate, FBS "
            "derivatives facts, and MI/CPM identity."
        ),
    }


def _research_escalation(role_buckets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recommendations = []
    for bucket in role_buckets:
        recommendations.append(
            {
                "role_bucket": bucket["bucket"],
                "meaning": bucket["meaning"],
                "research_escalation_result": bucket["strategy_research_need"],
                "reason": _research_reason_for_bucket(bucket),
                "final_before_research": bucket["final_engineering_need"],
            }
        )
    return recommendations


def _active_review_group_contract(portfolio_board: dict[str, Any]) -> dict[str, Any]:
    summary = portfolio_board.get("portfolio_summary") or {}
    raw_groups = summary.get("active_review_strategy_groups")
    if not isinstance(raw_groups, list):
        raise ValueError(
            "portfolio_board.portfolio_summary.active_review_strategy_groups must be supplied"
        )
    active_groups = _dedupe_non_empty_strings(raw_groups)
    if not active_groups:
        raise ValueError(
            "portfolio_board.portfolio_summary.active_review_strategy_groups must not be empty"
        )

    spec_groups = list(STRATEGY_ROLE_SPECS)
    known_active_groups = [group for group in active_groups if group in STRATEGY_ROLE_SPECS]
    missing_in_specs = [group for group in active_groups if group not in STRATEGY_ROLE_SPECS]
    extra_in_specs = [group for group in spec_groups if group not in active_groups]
    return {
        "source": ACTIVE_REVIEW_GROUP_SOURCE,
        "active_review_strategy_groups": active_groups,
        "known_active_groups": known_active_groups,
        "strategy_role_spec_groups": spec_groups,
        "missing_in_specs": missing_in_specs,
        "extra_in_specs": extra_in_specs,
        "contract_status": "aligned"
        if not missing_in_specs and not extra_in_specs
        else "spec_mismatch_reported",
    }


def _market_regime_assessment(
    capture_gap_audit: dict[str, Any],
    active_review_group_contract: dict[str, Any],
) -> dict[str, Any]:
    owner_visibility = capture_gap_audit.get("owner_visibility_state") or {}
    strategy_capture_gap, evidence_field = _strategy_capture_gap_support(
        capture_gap_audit
    )
    return {
        "assessment_source": "local_current_artifacts_only",
        "external_market_data_refreshed": False,
        "official_audit_time_utc": capture_gap_audit.get("official_server_time_utc"),
        "p0_state": owner_visibility.get("p0_state")
        or (capture_gap_audit.get("runtime_baseline") or {}).get("status")
        or "unknown",
        "signal_observation_state": owner_visibility.get(
            "signal_observation_state", "unknown"
        ),
        "strategy_capture_gap": strategy_capture_gap,
        "strategy_capture_gap_evidence_field": evidence_field,
        "active_review_strategy_groups": active_review_group_contract[
            "active_review_strategy_groups"
        ],
        "active_review_group_contract_status": active_review_group_contract[
            "contract_status"
        ],
        "interpretation": (
            "The latest local artifacts show no P0 executable fresh signal, "
            "but Signal Observation review evidence is active. Recent opportunity evidence "
            "is concentrated in MI and CPM long/rebound structures, while short, "
            "range, and derivatives-stress roles are covered mainly by immature "
            "or fact/classifier-blocked StrategyGroups."
        ),
        "limitation": (
            "This task did not refresh public Binance klines/funding/OI; it uses "
            "the current committed/generated artifacts as the review authority."
        ),
    }


def _strategy_capture_gap_support(
    capture_gap_audit: dict[str, Any],
) -> tuple[bool, str]:
    audit_conclusion = capture_gap_audit.get("audit_conclusion")
    sources = []
    if isinstance(audit_conclusion, dict):
        sources.append(("audit_conclusion", audit_conclusion))
    sources.append(("top_level", capture_gap_audit))

    for source_name, source in sources:
        for field in ("strategy_capture_gap_supported", "strategy_capture_gap_detected"):
            value = source.get(field)
            if value is not None:
                return bool(value), f"{source_name}.{field}"
    return False, "missing"


def _trial_pool_implications(
    portfolio_board: dict[str, Any],
    strategy_group_rows: list[dict[str, Any]],
    role_buckets: list[dict[str, Any]],
) -> dict[str, Any]:
    pool = portfolio_board.get("trial_candidate_pool") or {}
    short_range_groups = [
        row["strategy_group_id"]
        for row in strategy_group_rows
        if any(
            bucket
            in {
                "bear_rally_failure_short",
                "bear_pullback_continuation_short",
                "range_reversion",
                "liquidity_sweep_reversal",
                "false_breakout_or_compression_failure",
                "derivatives_stress",
            }
            for bucket in row["role_buckets"]
        )
    ]
    return {
        "trial_candidate_count": pool.get("candidate_count", 5),
        "trial_eligible_count": pool.get("trial_eligible_count", 1),
        "current_bias_risk": (
            "The current trial pool is useful, but opportunity evidence is skewed "
            "toward MI/CPM and MPG-style long or rebound momentum. Weak-market "
            "and range roles should remain visible as review lanes so the system "
            "does not overfit the next trial pool to recent long-side brightness."
        ),
        "short_range_derivatives_groups_to_keep_visible": sorted(set(short_range_groups)),
        "no_new_trial_candidate_now": True,
        "new_candidate_trigger_conditions": [
            "RBR replacement or revision shows repeatable positive range-reversion outcomes after costs",
            "FBS derivatives RequiredFacts are attached and produce reviewable stress/squeeze evidence",
            "BTPC stale/fact-source blockers are resolved and false-negative review remains positive",
            "BRF forward outcome plus squeeze classifier supports L2 review without live scope expansion",
        ],
    }


def _source_status(
    *,
    portfolio_board: dict[str, Any],
    trial_candidate_pool_md: str,
    capture_gap_audit: dict[str, Any],
    registry_baseline: dict[str, Any],
    tier_policy: dict[str, Any],
    required_facts_map_md: str,
    goal_progress: dict[str, Any] | None,
    local_monitor_sequence: dict[str, Any] | None,
    strategy_asset_state_source: dict[str, Any] | None,
    active_review_group_contract: dict[str, Any],
    git_log_oneline_8: list[str],
    git_status_short: list[str],
) -> dict[str, Any]:
    return {
        "required_inputs": {
            "portfolio_board_json": {
                "path": "caller_supplied",
                "status": portfolio_board.get("status"),
                "active_review_group_contract": active_review_group_contract,
            },
            "trial_candidate_pool_md": {
                "path": "caller_supplied",
                "read": bool(trial_candidate_pool_md.strip()),
                "candidate_lines": [
                    line
                    for line in trial_candidate_pool_md.splitlines()
                    if line.startswith("| `")
                ],
            },
            "capture_gap_audit_json": {
                "path": "caller_supplied",
                "status": capture_gap_audit.get("status"),
            },
            "registry_baseline_json": {
                "path": str(DEFAULT_REGISTRY_BASELINE_JSON),
                "status": registry_baseline.get("status"),
            },
            "tier_policy_json": {
                "path": str(DEFAULT_TIER_POLICY_JSON),
                "status": tier_policy.get("status"),
            },
            "required_facts_map_md": {
                "path": str(DEFAULT_REQUIRED_FACTS_MAP_MD),
                "read": bool(required_facts_map_md.strip()),
                "mentions_derivatives": "derivatives" in required_facts_map_md,
                "mentions_btpc": "BTPC-001" in required_facts_map_md,
            },
            "git_log_oneline_8": git_log_oneline_8,
            "git_status_short": _git_status_summary(git_status_short),
        },
        "optional_inputs": {
            "goal_progress_json_status": (goal_progress or {}).get("status"),
            "local_monitor_sequence_json_status": (
                local_monitor_sequence or {}
            ).get("status"),
            "strategy_asset_state_json_status": (
                strategy_asset_state_source or {}
            ).get("status"),
        },
    }


def _git_status_summary(git_status_short: list[str]) -> dict[str, Any]:
    task_related = []
    for line in git_status_short:
        item = _parse_git_status_short_line(line)
        if any(
            item["path"].startswith(prefix)
            for prefix in TASK_RELATED_GIT_STATUS_PREFIXES
        ):
            task_related.append(item)

    return {
        "dirty_count": len(git_status_short),
        "task_related_count": len(task_related),
        "task_related_paths": task_related,
        "omitted_count": len(git_status_short) - len(task_related),
        "full_status_omitted": True,
    }


def _parse_git_status_short_line(line: str) -> dict[str, str]:
    status = line[:2].strip() or "unknown"
    path = line[3:].strip() if len(line) > 3 else line.strip()
    return {"status": status, "path": path}


def _registry_only_rows(
    registry_rows: dict[str, dict[str, Any]],
    portfolio_rows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for group_id, note in REGISTRY_ONLY_NOTES.items():
        row = registry_rows.get(group_id, {})
        if group_id not in portfolio_rows:
            rows.append(
                {
                    "strategy_group_id": group_id,
                    "owner_label": row.get("owner_label", group_id),
                    "default_tier": row.get("default_tier", "unknown"),
                    "note": note,
                }
            )
    return rows


def _final_need_for_bucket(bucket: str, rows: list[dict[str, Any]]) -> str:
    if bucket == "trend_long":
        return "Keep MPG P0 standby; close CPM identity and no-action visibility before adding long-trend trial scope."
    if bucket == "momentum_impulse":
        return "Resolve MI identity, overlap, concentration, and tier unknown status inside final."
    if bucket == "bear_rally_failure_short":
        return "Complete BRF forward outcome, squeeze classifier, and RequiredFacts review."
    if bucket == "bear_pullback_continuation_short":
        return "Attach BTPC fact sources and close LSR side-specific range-context rewrite."
    if bucket == "range_reversion":
        return "Keep RBR parked unless new edge evidence appears; define active range-quality evidence standard."
    if bucket == "liquidity_sweep_reversal":
        return "Complete LSR range-context facts and side-specific rewrite quality review."
    if bucket == "false_breakout_or_compression_failure":
        return "Review VCB compression/false-breakout classifier and cost sensitivity."
    if bucket == "derivatives_stress":
        return "Attach funding, basis, OI, and squeeze-risk fact sources before promotion."
    if bucket == "session_structure":
        return "Expose SOR no-action/session attribution and session-window readiness."
    return "Resolve registry identity before runtime or trial interpretation."


def _research_need_for_bucket(bucket: str, rows: list[dict[str, Any]]) -> str:
    if bucket in {"range_reversion", "false_breakout_or_compression_failure", "session_structure"}:
        return "bounded_research_recommended"
    if bucket == "derivatives_stress":
        return "research_required_before_trial"
    return "no_research_needed"


def _research_reason_for_bucket(bucket: dict[str, Any]) -> str:
    role = bucket["bucket"]
    if role == "range_reversion":
        return "RBR exists but is parked; a trial-quality weak-range lane needs bounded research evidence."
    if role == "false_breakout_or_compression_failure":
        return "VCB exists but classifier quality is not enough; bounded research can test failure/rejection variants."
    if role == "derivatives_stress":
        return "FBS requires derivatives facts and stress semantics before trial; research should stay bounded and fact-first."
    if role == "session_structure":
        return "SOR exists but is narrow and visibility-poor; bounded research can expand session structures after final visibility is fixed."
    return "Current final assets cover the role enough for engineering closure before new research."


def _trial_pool_status_by_group(portfolio_board: dict[str, Any]) -> dict[str, str]:
    pool = portfolio_board.get("trial_candidate_pool") or {}
    candidates = pool.get("candidates")
    if not isinstance(candidates, list):
        candidates = [
            row
            for row in _dict_rows(portfolio_board.get("portfolio_rows"))
            if row.get("evidence_stage")
            in {
                "trial_waiting",
                "promote_review",
                "revise",
                "identity_review",
            }
        ]
    status = {}
    for row in candidates:
        group_id = str(row.get("strategy_group_id"))
        if group_id and group_id != "None":
            status[group_id] = str(
                row.get("pool_stage")
                or row.get("evidence_stage")
                or "trial_pool_review"
            )
    return status


def _best_tradable_forward_count(summary: dict[str, Any]) -> int:
    best = 0
    for value in summary.values():
        if isinstance(value, dict):
            best = max(best, int(value.get("tradable_mfe_after_cost_count") or 0))
    return best


def _validate_review_only_safety(name: str, source_artifact: dict[str, Any]) -> None:
    invariants = source_artifact.get("safety_invariants")
    if not isinstance(invariants, dict):
        return
    for key in FORBIDDEN_TRUE_KEYS:
        if invariants.get(key) is True:
            raise ValueError(f"{name} has unsafe invariant {key}=true")
    for key in LEGACY_AUTHORITY_MIRROR_TRUE_KEYS:
        if invariants.get(key) is True:
            raise ValueError(
                f"{name} has legacy_authority_mirror_present:{key}"
            )
    aliases = {
        "places_order": "order_created",
        "calls_finalgate": "calls_finalgate",
        "calls_operation_layer": "calls_operation_layer",
        "calls_exchange_write": "calls_exchange_write",
    }
    for alias in aliases:
        if invariants.get(alias) is True:
            raise ValueError(f"{name} has unsafe invariant {alias}=true")


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _dedupe_non_empty_strings(value: list[Any]) -> list[str]:
    seen = set()
    result = []
    for item in value:
        text = str(item).strip()
        if not text or text == "None" or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _load_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _load_json_object(path)


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_lines(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "# StrategyGroup Regime Role Coverage Map",
        "",
        "## 结论",
        "",
        "- **当前 StrategyGroup 体系不是缺少熊市 / 震荡 / 做空语义，而是这些语义多数还不成熟。**",
        "- **MI-001 / CPM-RO-001** 的近期机会更亮，容易让 Trial Pool 偏向多头或反弹动量；本盘点要求继续保留 **BRF / BTPC / LSR / RBR / FBS / SOR / VCB** 的弱市角色可见性。",
        "- **真正需要 strategy-research bounded lane 的重点不是再造全部 short 策略，而是 range-reversion、false-breakout/compression-failure、derivatives-stress 的补证或替代语义。**",
        "",
        "## 已知客观事实",
        "",
        f"- **输出 JSON**: `{output_json}`",
        f"- **Schema**: `{artifact['schema']}`",
        f"- **Scope**: `{artifact['scope']}`",
        f"- **Active review groups**: `{len(artifact['strategy_group_rows'])}`",
        f"- **Active review group source**: `{artifact['active_review_group_contract']['source']}`",
        f"- **Missing in specs**: `{', '.join(artifact['active_review_group_contract']['missing_in_specs']) or '[]'}`",
        f"- **Extra in specs**: `{', '.join(artifact['active_review_group_contract']['extra_in_specs']) or '[]'}`",
        f"- **Role buckets**: `{len(artifact['role_buckets'])}`",
        f"- **External market refresh**: `{artifact['market_regime_assessment']['external_market_data_refreshed']}`",
        "",
        "## 当前市场 regime 判断",
        "",
        f"- **P0 状态**: `{artifact['market_regime_assessment']['p0_state']}`",
        "- **Signal Observation 状态**: "
        f"`{artifact['market_regime_assessment']['signal_observation_state']}`",
        f"- **Strategy Capture Gap**: `{artifact['market_regime_assessment']['strategy_capture_gap']}`",
        f"- **Gap 证据字段**: `{artifact['market_regime_assessment']['strategy_capture_gap_evidence_field']}`",
        f"- **判断来源**: `{artifact['market_regime_assessment']['assessment_source']}`",
        f"- **解释**: {artifact['market_regime_assessment']['interpretation']}",
        f"- **限制**: {artifact['market_regime_assessment']['limitation']}",
        "",
        "## StrategyGroup 角色覆盖表",
        "",
        "| StrategyGroup | Owner Label | Tier | Evidence | Role | Buckets | Recent | Tradable | Blocker | Trial Pool | Checkpoint |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for row in artifact["strategy_group_rows"]:
        lines.append(
            "| `{strategy_group_id}` | **{owner_label}** | `{execution_tier}` | `{evidence_stage}` | {portfolio_role} | `{buckets}` | {recent} | {tradable} | `{blocker}` | `{trial}` | `{next}` |".format(
                strategy_group_id=row["strategy_group_id"],
                owner_label=row["owner_label"],
                execution_tier=row["execution_tier"],
                evidence_stage=row["evidence_stage"],
                portfolio_role=row["portfolio_role"],
                buckets=", ".join(row["role_buckets"]),
                recent=row["recent_opportunity_count"],
                tradable=row["tradable_forward_count"],
                blocker=row["dominant_blocker"],
                trial=row["trial_pool_status"],
                next=row["current_review_checkpoint"],
            )
        )

    lines.extend(
        [
            "",
            "## 熊市 / 震荡 / 做空语义缺口",
            "",
            "| Bucket | Meaning | Coverage | Groups | Gap Classes | Final Need | Research Need |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for bucket in artifact["role_buckets"]:
        lines.append(
            "| `{bucket}` | **{meaning}** | `{coverage}` | `{groups}` | `{gaps}` | {final_need} | `{research_need}` |".format(
                bucket=bucket["bucket"],
                meaning=bucket["meaning"],
                coverage=bucket["coverage_status"],
                groups=", ".join(bucket["strategy_groups"]) or "-",
                gaps=", ".join(bucket["primary_gap_classes"]) or "-",
                final_need=bucket["final_engineering_need"],
                research_need=bucket["strategy_research_need"],
            )
        )

    lines.extend(
        [
            "",
            "## 哪些在 final 内补",
            "",
        ]
    )
    for row in artifact["strategy_group_rows"]:
        lines.append(
            f"- **{row['strategy_group_id']}**: {row['current_review_checkpoint']}。缺口：`{', '.join(row['gap_classes'])}`。"
        )

    lines.extend(
        [
            "",
            "## 哪些需要 strategy-research bounded lane",
            "",
            "| Role Bucket | Research Escalation Result | Reason |",
            "| --- | --- | --- |",
        ]
    )
    for item in artifact["research_escalation_recommendations"]:
        lines.append(
            f"| `{item['role_bucket']}` | `{item['research_escalation_result']}` | {item['reason']} |"
        )

    lines.extend(
        [
            "",
            "## 对 Trial Candidate Pool 的影响",
            "",
            f"- **Trial candidate count**: `{artifact['trial_pool_implications']['trial_candidate_count']}`",
            f"- **Trial eligible count**: `{artifact['trial_pool_implications']['trial_eligible_count']}`",
            f"- **结论**: {artifact['trial_pool_implications']['current_bias_risk']}",
            "- **新增候选触发条件**:",
        ]
    )
    for condition in artifact["trial_pool_implications"]["new_candidate_trigger_conditions"]:
        lines.append(f"  - {condition}")

    lines.extend(
        [
            "",
            "## 安全边界",
            "",
            "| Invariant | Value |",
            "| --- | --- |",
        ]
    )
    for key, value in artifact["safety_invariants"].items():
        lines.append(f"| `{key}` | `{str(value).lower()}` |")

    lines.extend(
        [
            "",
            "## Registry-only 说明",
            "",
        ]
    )
    for note in artifact["registry_only_notes"]:
        lines.append(
            f"- **{note['strategy_group_id']}** / **{note['owner_label']}**: {note['note']}"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
