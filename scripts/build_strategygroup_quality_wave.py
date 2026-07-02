#!/usr/bin/env python3
"""Build or validate the StrategyGroup quality-governance wave.

The quality wave joins registry, tier review, Strategy Asset State, handoff/replay
coverage, RequiredFacts mapping, and local monitor evidence for the current
Signal Observation learning set. It is governance evidence only and does not
create live authority.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategygroup_non_executing_projection import (  # noqa: E402
    legacy_authority_mirror_present_errors,
)
from src.domain.runtime_readiness_state import false_flag_errors  # noqa: E402

DEFAULT_REGISTRY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
DEFAULT_TIER_REVIEW_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-tier-review-current.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_REQUIRED_FACTS_MAP = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/main-control-required-facts-map.md"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.md"
)

INCLUDED_GROUPS = ["BTPC-001", "VCB-001", "LSR-001", "BRF-001", "RBR-001"]
GAP_CLASSES = {
    "fact_source_gap",
    "classifier_gap",
    "replay_quality_gap",
    "cost_or_slippage_gap",
    "tier_policy_gap",
    "stale_or_missing_artifact_gap",
    "authority_boundary_gap",
    "parked_low_priority_gap",
}
REQUIRED_ROW_FIELDS = [
    "strategy_group_id",
    "eats",
    "current_tier",
    "current_decision",
    "promotion_scope",
    "promotion_target",
    "system_can_continue",
    "owner_policy_action_required",
    "primary_gap_class",
    "secondary_gap_class",
    "required_next_evidence",
    "do_not_promote_reason",
    "authority_boundary",
]
SAFETY_INVARIANTS = {
    "calls_finalgate": False,
    "calls_operation_layer": False,
    "calls_exchange_write": False,
    "places_order": False,
    "changes_live_profile": False,
    "changes_order_sizing_defaults": False,
    "withdrawal_or_transfer": False,
}
AUTHORITY_BOUNDARY = (
    "quality_governance_only; owner_risk_acceptance_may_affect_trial_or_"
    "tier_policy_only; no_runtime_gate_bypass; no_real_order_scope_change"
)


def build_quality_wave_artifact(
    registry: dict[str, Any],
    tier_review: dict[str, Any],
    strategy_asset_state_source: dict[str, Any],
    tier_policy: dict[str, Any],
    required_facts_text: str,
    local_monitor: dict[str, Any],
) -> dict[str, Any]:
    coverage = build_source_coverage(required_facts_text, local_monitor)
    registry_by_group = _by_group(_dict_rows(registry.get("rows")))
    tier_review_by_group = _by_group(_dict_rows(tier_review.get("rows")))
    strategy_asset_rows = _strategy_asset_decision_rows(strategy_asset_state_source)
    strategy_asset_by_group = _by_group(strategy_asset_rows)
    policy_by_group = _as_dict(tier_policy.get("current_strategy_groups"))

    rows: list[dict[str, Any]] = []
    contradictions: list[dict[str, str]] = []
    for group in INCLUDED_GROUPS:
        registry_row = registry_by_group.get(group, {})
        tier_row = tier_review_by_group.get(group, {})
        strategy_asset_row = strategy_asset_by_group.get(group, {})
        policy_row = _as_dict(policy_by_group.get(group))
        group_coverage = coverage[group]
        group_coverage["strategy_asset_state_row"] = bool(strategy_asset_row)
        rows.append(
            _build_quality_row(
                group,
                registry_row,
                tier_row,
                strategy_asset_row,
                policy_row,
                group_coverage,
            )
        )
        contradictions.extend(
            _find_contradictions(
                group,
                registry_row,
                tier_row,
                strategy_asset_row,
                policy_row,
            )
        )

    gap_findings = _build_gap_findings(rows, coverage)
    closures = _build_closures(rows, gap_findings)
    strategy_asset_state_provenance = _strategy_asset_state_provenance(rows)
    return {
        "schema": "brc.strategygroup_quality_wave.v1",
        "status": "quality_wave_ready",
        "scope": "signal_observation_strategygroup_quality_wave",
        "readmodel_boundary": {
            "runtime_truth": False,
            "owner_supervision": True,
            "audit_evidence": True,
            "presentation_only": False,
        },
        "included_strategy_groups": INCLUDED_GROUPS,
        "source_authority": {
            "registry_baseline": (
                "docs/current/strategy-group-handoffs/"
                "strategygroup-registry-baseline.json"
            ),
            "tier_review": (
                "docs/current/strategy-group-handoffs/"
                "strategygroup-tier-review-current.json"
            ),
            "strategy_asset_state": (
                "caller_supplied_strategy_asset_state"
            ),
            "tier_policy": (
                "docs/current/strategy-group-handoffs/"
                "main-control-runtime-tier-policy.json"
            ),
            "required_facts_map": (
                "docs/current/strategy-group-handoffs/"
                "main-control-required-facts-map.md"
            ),
            "local_monitor_sequence": (
                "caller_supplied"
            ),
        },
        "global_authority_model": {
            "owner_controls": [
                "policy",
                "tier",
                "risk_scope",
                "capital_scope",
                "pause_resume",
                "promote_downshift_park_kill",
                "production_stage_transition",
            ],
            "system_controls": ["normal_process_execution"],
            "runtime_authority_sources": [
                "Tradeability Decision",
                "Runtime Safety State",
            ],
            "review_updates": ["strategy_governance"],
            "owner_risk_acceptance_cannot_grant_runtime_authority": True,
        },
        "safety_invariants": deepcopy(SAFETY_INVARIANTS),
        "strategy_asset_state_source": {
            "source": "strategy_asset_state.asset_rows",
            "row_count": len(strategy_asset_rows),
        },
        "strategy_asset_state_provenance": strategy_asset_state_provenance,
        "source_coverage": coverage,
        "rows": rows,
        "gap_findings": gap_findings,
        "closures": closures,
        "contradictions": contradictions,
        "quality_wave_decision_counts": _counts(rows, "current_decision"),
        "gap_counts": _counts(rows, "primary_gap_class"),
    }


def build_source_coverage(
    required_facts_text: str,
    local_monitor: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    steps = {
        str(step.get("name") or step.get("step") or ""): str(step.get("status") or "")
        for step in _dict_rows(local_monitor.get("steps"))
    }
    coverage: dict[str, dict[str, Any]] = {}
    for group in INCLUDED_GROUPS:
        handoff = _handoff_path(group)
        replay = _replay_path(group)
        coverage[group] = {
            "registry_baseline_row": True,
            "tier_review_row": True,
            "strategy_asset_state_row": True,
            "handoff_pack": handoff.exists(),
            "handoff_path": _rel(handoff) if handoff.exists() else None,
            "replay_corpus": replay.exists(),
            "replay_path": _rel(replay) if replay.exists() else None,
            "required_facts_mapping": group in required_facts_text,
            "runtime_tier_policy": group == "BTPC-001",
            "local_monitor_entrypoint": _local_monitor_entrypoint(group, steps),
        }
    return coverage


def build_owner_markdown(artifact: dict[str, Any]) -> str:
    rows = _dict_rows(artifact.get("rows"))
    lines = [
        "---",
        "title: STRATEGYGROUP_QUALITY_WAVE_CURRENT",
        "status: CURRENT",
        "authority: docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json",
        "last_verified: 2026-06-20",
        "---",
        "",
        "# StrategyGroup Quality Wave Current",
        "",
        "## 目的",
        "",
        "这份质量治理波次不是单策略报告，也不是主判断源。它把 BTPC / VCB / LSR / BRF / RBR 的 registry、tier review、Strategy Asset State、handoff、replay、RequiredFacts 和本地 monitor 覆盖整理为质量证据 provenance。",
        "",
        "当前策略资产判断以 `strategy_asset_state.asset_rows` 为主；本波次只保留质量证据、gap 分类和审计覆盖。静态质量治理不授权实盘。Owner 风险接受可以影响 trial 或 tier policy 路径，但不能绕过运行时安全门。",
        "",
        "## 总览",
        "",
        _summary_table(rows),
        "",
        "## 关闭或测试守护的 gap findings",
        "",
        _closure_table(_dict_rows(artifact.get("closures"))),
        "",
        "## 分组质量判断",
        "",
    ]
    for row in rows:
        lines.extend(_row_section(row))
    lines.extend(
        [
            "## 权限边界",
            "",
            "本波次只服务 StrategyGroup 质量治理，不部署、不下单、不修改实盘配置、不修改杠杆/仓位/订单大小默认值、不创建提现或划转动作。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def validate_artifact(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if artifact.get("schema") != "brc.strategygroup_quality_wave.v1":
        errors.append("schema_mismatch")
    rows = _dict_rows(artifact.get("rows"))
    groups = [str(row.get("strategy_group_id") or "") for row in rows]
    if groups != INCLUDED_GROUPS:
        errors.append(f"group_order_mismatch:{groups}")
    safety = _as_dict(artifact.get("safety_invariants"))
    errors.extend(
        false_flag_errors(
            safety,
            error_prefix="safety_invariant",
            false_keys=tuple(SAFETY_INVARIANTS),
        )
    )
    for row in rows:
        group = str(row.get("strategy_group_id") or "unknown")
        for field in REQUIRED_ROW_FIELDS:
            if field not in row:
                errors.append(f"{group}.missing_field:{field}")
        for field in (
            "current_decision",
            "promotion_scope",
            "promotion_target",
            "required_next_evidence",
            "do_not_promote_reason",
        ):
            if not str(row.get(field) or ""):
                errors.append(f"{group}.missing_strategy_asset_state_field:{field}")
        errors.extend(
            legacy_authority_mirror_present_errors(
                row,
                label_prefix=f"{group}.quality_row_",
            )
        )
        if row.get("owner_policy_action_required") is True:
            errors.append(f"{group}.unexpected_owner_operator_requirement")
        if row.get("current_decision") in {"promote", "promote_review_only"}:
            scope = str(row.get("promotion_scope") or "not_applicable")
            if scope == "not_applicable":
                errors.append(f"{group}.missing_promotion_scope")
        for field in ("primary_gap_class", "secondary_gap_class"):
            if row.get(field) not in GAP_CLASSES:
                errors.append(f"{group}.{field}_unknown:{row.get(field)}")
        if row.get("authority_boundary") != AUTHORITY_BOUNDARY:
            errors.append(f"{group}.authority_boundary_mismatch")
    boundary = _as_dict(artifact.get("readmodel_boundary"))
    if boundary.get("presentation_only") is not False:
        errors.append("readmodel_boundary_presentation_only_not_false")
    if boundary.get("owner_supervision") is not True:
        errors.append("readmodel_boundary_owner_supervision_not_true")
    provenance = _as_dict(artifact.get("strategy_asset_state_provenance"))
    if provenance.get("source_role") != "quality_evidence_provenance":
        errors.append("strategy_asset_state_provenance_source_role_mismatch")
    if provenance.get("primary_judgment_source") is not False:
        errors.append("strategy_asset_state_provenance_must_not_be_primary")
    if provenance.get("primary_judgment_source_name") != "strategy_asset_state":
        errors.append("strategy_asset_state_provenance_primary_source_mismatch")
    provenance_rows = _dict_rows(provenance.get("rows"))
    if len(provenance_rows) != len(rows):
        errors.append("strategy_asset_state_provenance_row_count_mismatch")
    closures = _dict_rows(artifact.get("closures"))
    if len(closures) < 3:
        errors.append("insufficient_gap_closures")
    closure_groups = {str(item.get("strategy_group_id") or "") for item in closures}
    if len(closure_groups - {""}) < 2:
        errors.append("gap_closures_do_not_span_two_groups")
    if not any(item.get("shared_infrastructure") is True for item in closures):
        errors.append("missing_shared_infrastructure_closure")
    if not any(
        item.get("proves_owner_risk_acceptance_not_actionability") is True
        for item in closures
    ):
        errors.append("missing_owner_risk_acceptance_actionability_closure")
    coverage = _as_dict(artifact.get("source_coverage"))
    for group in INCLUDED_GROUPS:
        group_coverage = _as_dict(coverage.get(group))
        for key in (
            "registry_baseline_row",
            "tier_review_row",
            "strategy_asset_state_row",
            "handoff_pack",
            "replay_corpus",
            "required_facts_mapping",
            "runtime_tier_policy",
            "local_monitor_entrypoint",
        ):
            if key not in group_coverage:
                errors.append(f"{group}.coverage_missing:{key}")
        if group_coverage.get("strategy_asset_state_row") is not True:
            errors.append(f"{group}.strategy_asset_state_row_missing")
    return errors


def load_inputs(
    registry_path: Path,
    tier_review_path: Path,
    strategy_asset_state_source_path: Path,
    tier_policy_path: Path,
    required_facts_path: Path,
    local_monitor_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str, dict[str, Any]]:
    return (
        _load_json(registry_path),
        _load_json(tier_review_path),
        _load_json(strategy_asset_state_source_path),
        _load_json(tier_policy_path),
        required_facts_path.read_text(encoding="utf-8") if required_facts_path.exists() else "",
        _load_json(local_monitor_path)
        if local_monitor_path and local_monitor_path.exists()
        else {},
    )


def _build_quality_row(
    group: str,
    registry_row: dict[str, Any],
    tier_row: dict[str, Any],
    strategy_asset_row: dict[str, Any],
    policy_row: dict[str, Any],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    primary_gap, secondary_gap = _gap_classes(
        group,
        coverage,
        strategy_asset_row,
    )
    decision = str(strategy_asset_row.get("current_decision") or "")
    promotion_scope = str(strategy_asset_row.get("promotion_scope") or "")
    promotion_target = str(strategy_asset_row.get("promotion_target") or "")
    system_can_continue = primary_gap != "parked_low_priority_gap" or group != "RBR-001"
    required_next_evidence = str(strategy_asset_row.get("required_next_evidence") or "")
    return {
        "strategy_group_id": group,
        "owner_label": str(registry_row.get("owner_label") or group),
        "eats": str(registry_row.get("edge_thesis") or ""),
        "current_tier": str(strategy_asset_row.get("tier") or ""),
        "current_decision": decision,
        "promotion_scope": promotion_scope,
        "promotion_target": promotion_target,
        "system_can_continue": system_can_continue,
        "owner_policy_action_required": False,
        "primary_gap_class": primary_gap,
        "secondary_gap_class": secondary_gap,
        "required_next_evidence": required_next_evidence,
        "do_not_promote_reason": str(
            strategy_asset_row.get("reason") or ""
        ),
        "next_engineering_checkpoint": _next_checkpoint(group, primary_gap, required_next_evidence),
        "source_coverage": deepcopy(coverage),
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _strategy_asset_state_provenance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "state_family": "Strategy Asset State",
        "source_role": "quality_evidence_provenance",
        "primary_judgment_source": False,
        "primary_judgment_source_name": "strategy_asset_state",
        "consumed_by": [
            "strategygroup_pre_live_rehearsal_readiness",
            "audit_detail_views",
        ],
        "row_count": len(rows),
        "rows": [_strategy_asset_provenance_row(row) for row in rows],
    }


def _strategy_asset_provenance_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_group_id": str(row.get("strategy_group_id") or "unknown"),
        "state_family": "Strategy Asset State",
        "source_role": "quality_evidence_provenance",
        "current_tier": str(row.get("current_tier") or "unknown"),
        "current_decision": str(row.get("current_decision") or ""),
        "promotion_scope": str(row.get("promotion_scope") or "not_applicable"),
        "promotion_target": str(row.get("promotion_target") or "not_applicable"),
        "primary_gap_class": str(row.get("primary_gap_class") or ""),
        "secondary_gap_class": str(row.get("secondary_gap_class") or ""),
        "system_can_continue": row.get("system_can_continue") is True,
        "required_next_evidence": str(row.get("required_next_evidence") or ""),
        "next_engineering_checkpoint": str(
            row.get("next_engineering_checkpoint") or ""
        ),
        "authority_boundary": str(row.get("authority_boundary") or ""),
    }


def _gap_classes(
    group: str,
    coverage: dict[str, Any],
    strategy_asset_row: dict[str, Any],
) -> tuple[str, str]:
    if group == "RBR-001":
        return "parked_low_priority_gap", "replay_quality_gap"
    if group == "BTPC-001":
        return "fact_source_gap", "classifier_gap"
    if not coverage.get("handoff_pack"):
        return "stale_or_missing_artifact_gap", "replay_quality_gap"
    decision = str(strategy_asset_row.get("current_decision") or "")
    if decision == "revise":
        return "classifier_gap", "fact_source_gap"
    return "replay_quality_gap", "fact_source_gap"


def _next_checkpoint(group: str, gap_class: str, evidence: str) -> str:
    if group == "RBR-001":
        return "keep_parked_until_material_new_edge_evidence"
    if group == "BTPC-001":
        return "complete_fact_source_and_classifier_revision_guard"
    if gap_class == "stale_or_missing_artifact_gap":
        return f"create_or_accept_explicit_missing_handoff_boundary_for_{group}"
    return evidence


def _build_gap_findings(
    rows: list[dict[str, Any]],
    coverage: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in rows:
        group = row["strategy_group_id"]
        group_coverage = coverage[group]
        if not group_coverage["handoff_pack"]:
            findings.append(
                _finding(
                    group,
                    "stale_or_missing_artifact_gap",
                    "handoff pack is absent and must stay explicit before promotion",
                )
            )
        if not group_coverage["replay_corpus"]:
            findings.append(
                _finding(
                    group,
                    "replay_quality_gap",
                    "replay corpus is absent and promotion must remain parked or blocked",
                )
            )
        if not group_coverage["required_facts_mapping"]:
            findings.append(
                _finding(
                    group,
                    "fact_source_gap",
                    "RequiredFacts mapping is absent for this StrategyGroup",
                )
            )
    findings.append(
        _finding(
            "ALL_INCLUDED",
            "authority_boundary_gap",
            "Owner risk acceptance cannot set runtime actionability or bypass gates",
            shared=True,
        )
    )
    return findings


def _build_closures(
    rows: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    closures = [
        {
            "closure_id": "quality-wave-shared-source-drift-guard",
            "strategy_group_id": "ALL_INCLUDED",
            "gap_class": "authority_boundary_gap",
            "closure_type": "machine_checkable_test",
            "closed_or_guarded": True,
            "shared_infrastructure": True,
            "proves_owner_risk_acceptance_not_actionability": True,
            "evidence": "tests validate safety invariants, actionability false, and source-derived rows",
        }
    ]
    for finding in findings:
        group = str(finding.get("strategy_group_id") or "")
        if group in {"VCB-001", "RBR-001", "BTPC-001"}:
            closures.append(
                {
                    "closure_id": f"quality-wave-{group.lower()}-{finding['gap_class']}",
                    "strategy_group_id": group,
                    "gap_class": finding["gap_class"],
                    "closure_type": "explicit_classification",
                    "closed_or_guarded": True,
                    "shared_infrastructure": False,
                    "proves_owner_risk_acceptance_not_actionability": False,
                    "evidence": finding["description"],
                }
            )
        if len(closures) >= 4:
            break
    return closures


def _finding(
    group: str,
    gap_class: str,
    description: str,
    *,
    shared: bool = False,
) -> dict[str, Any]:
    return {
        "strategy_group_id": group,
        "gap_class": gap_class,
        "description": description,
        "shared_infrastructure": shared,
    }


def _find_contradictions(
    group: str,
    registry_row: dict[str, Any],
    tier_row: dict[str, Any],
    strategy_asset_row: dict[str, Any],
    policy_row: dict[str, Any],
) -> list[dict[str, str]]:
    contradictions: list[dict[str, str]] = []
    registry_tier = str(registry_row.get("default_tier") or "")
    review_tier = str(tier_row.get("current_tier") or "")
    ledger_tier = str(strategy_asset_row.get("tier") or "")
    policy_tier = str(policy_row.get("tier") or registry_tier)
    for source, tier in (
        ("tier_review", review_tier),
        ("strategy_asset_state", ledger_tier),
        ("tier_policy", policy_tier),
    ):
        if tier and registry_tier and tier != registry_tier:
            contradictions.append(
                {
                    "strategy_group_id": group,
                    "source": source,
                    "registry_tier": registry_tier,
                    "source_tier": tier,
                }
            )
    return contradictions


def _strategy_asset_decision_rows(strategy_asset_state_source: dict[str, Any]) -> list[dict[str, Any]]:
    strategy_asset_state = _as_dict(strategy_asset_state_source.get("strategy_asset_state"))
    return [
        _strategy_asset_row_from_strategy_asset_state(row)
        for row in _dict_rows(strategy_asset_state.get("asset_rows"))
    ]


def _strategy_asset_row_from_strategy_asset_state(row: dict[str, Any]) -> dict[str, Any]:
    promotion_target = str(row.get("promotion_target") or "not_applicable")
    decision = str(row.get("current_decision") or "")
    return {
        "strategy_group_id": str(row.get("strategy_group_id") or "unknown"),
        "tier": str(row.get("current_tier") or "unknown"),
        "current_decision": _display_decision(decision, promotion_target),
        "promotion_scope": _display_promotion_scope(row),
        "promotion_target": promotion_target,
        "reason": str(row.get("reason") or ""),
        "required_next_evidence": str(row.get("required_next_evidence") or ""),
        "next_checkpoint": str(row.get("next_checkpoint") or ""),
        "source": "strategy_asset_state",
    }


def _display_decision(decision: str, promotion_target: str) -> str:
    if decision == "promote" and promotion_target == "promotion_evidence_review_only":
        return "promote_review_only"
    return decision


def _display_promotion_scope(row: dict[str, Any]) -> str:
    if str(row.get("promotion_target") or "") == "promotion_evidence_review_only":
        return "review_only"
    return str(row.get("promotion_scope") or "not_applicable")


def _handoff_path(group: str) -> Path:
    return REPO_ROOT / "docs/current/strategy-group-handoffs" / group / "handoff.json"


def _replay_path(group: str) -> Path:
    names = {
        "BTPC-001": "btpc-001-l2-replay-corpus.json",
        "VCB-001": "vcb-001-l1-observe-replay-corpus.json",
        "LSR-001": "lsr-001-l1-observe-replay-corpus.json",
        "BRF-001": "brf-001-l1-observe-replay-corpus.json",
        "RBR-001": "rbr-001-l1-observe-replay-corpus.json",
    }
    return (
        REPO_ROOT
        / "docs/current/strategy-group-handoffs"
        / group
        / "replay"
        / names[group]
    )


def _local_monitor_entrypoint(group: str, steps: dict[str, str]) -> str | None:
    if group == "BTPC-001":
        wanted = [
            "btpc_l2_shadow_fact_quality_review",
            "btpc_l2_keep_revise_fact_source_review",
            "btpc_live_derivatives_fact_source_mapping",
            "btpc_classifier_rule_review",
            "strategy_asset_state",
        ]
    else:
        wanted = ["post_revision_replay_review", "strategy_asset_state"]
    present = [step for step in wanted if step in steps]
    return ",".join(present) if present else None


def _summary_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| StrategyGroup | Tier | Decision | System can continue | Primary gap | Next checkpoint |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row["strategy_group_id"],
                row["current_tier"],
                row["current_decision"],
                str(row["system_can_continue"]).lower(),
                row["primary_gap_class"],
                row["next_engineering_checkpoint"],
            )
        )
    return "\n".join(lines)


def _closure_table(closures: list[dict[str, Any]]) -> str:
    lines = [
        "| Closure | StrategyGroup | Gap | Type | Shared |",
        "| --- | --- | --- | --- | --- |",
    ]
    for closure in closures:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                closure.get("closure_id"),
                closure.get("strategy_group_id"),
                closure.get("gap_class"),
                closure.get("closure_type"),
                str(closure.get("shared_infrastructure")).lower(),
            )
        )
    return "\n".join(lines)


def _row_section(row: dict[str, Any]) -> list[str]:
    return [
        f"### `{row['strategy_group_id']}` {row['owner_label']}",
        "",
        f"- 吃的机会: {row['eats']}",
        f"- 当前层级 / 决策: `{row['current_tier']}` / `{row['current_decision']}`",
        f"- 晋级范围 / 目标: `{row['promotion_scope']}` / `{row['promotion_target']}`",
        f"- 系统可继续工程化: `{str(row['system_can_continue']).lower()}`",
        f"- Owner policy action required: `{str(row['owner_policy_action_required']).lower()}`",
        f"- 主要 gap / 次要 gap: `{row['primary_gap_class']}` / `{row['secondary_gap_class']}`",
        f"- 下一证据: {row['required_next_evidence']}",
        f"- 不晋级原因: {row['do_not_promote_reason']}",
        f"- 下一工程 checkpoint: `{row['next_engineering_checkpoint']}`",
        "",
    ]


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _by_group(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("strategy_group_id") or ""): row for row in rows}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _write_files(artifact: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(build_owner_markdown(artifact), encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-json", default=str(DEFAULT_REGISTRY_JSON))
    parser.add_argument("--tier-review-json", default=str(DEFAULT_TIER_REVIEW_JSON))
    parser.add_argument(
        "--strategy-asset-state-json",
        dest="strategy_asset_state_source_json",
        metavar="STRATEGY_ASSET_STATE_JSON",
    )
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument("--required-facts-map", default=str(DEFAULT_REQUIRED_FACTS_MAP))
    parser.add_argument("--local-monitor-json")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if not args.strategy_asset_state_source_json:
        parser.error("--strategy-asset-state-json is required")

    inputs = load_inputs(
        Path(args.registry_json).expanduser(),
        Path(args.tier_review_json).expanduser(),
        Path(args.strategy_asset_state_source_json).expanduser(),
        Path(args.tier_policy_json).expanduser(),
        Path(args.required_facts_map).expanduser(),
        Path(args.local_monitor_json).expanduser()
        if args.local_monitor_json
        else None,
    )
    expected = build_quality_wave_artifact(*inputs)
    errors = validate_artifact(expected)
    output_json = Path(args.output_json).expanduser()
    output_md = Path(args.output_md).expanduser()
    if args.check:
        if not output_json.exists():
            errors.append(f"missing_json:{output_json}")
        if not output_md.exists():
            errors.append(f"missing_markdown:{output_md}")
        if output_json.exists():
            existing = _load_json(output_json)
            if existing != expected:
                errors.append("json_output_drift")
            errors.extend(validate_artifact(existing))
        if output_md.exists():
            markdown = output_md.read_text(encoding="utf-8")
            for group in INCLUDED_GROUPS:
                if group not in markdown:
                    errors.append(f"markdown_missing_group:{group}")
            if "运行时安全门" not in markdown:
                errors.append("markdown_missing_runtime_safety_boundary")
    else:
        _write_files(expected, output_json, output_md)

    report = {
        "status": "passed" if not errors else "failed",
        "scope": "signal_observation_strategygroup_quality_wave",
        "json_path": str(output_json),
        "markdown_path": str(output_md),
        "row_count": len(expected["rows"]),
        "closure_count": len(expected["closures"]),
        "contradiction_count": len(expected["contradictions"]),
        "gap_counts": expected["gap_counts"],
        "errors": errors,
        "safety_invariants": expected["safety_invariants"],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
