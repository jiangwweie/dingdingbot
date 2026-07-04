#!/usr/bin/env python3
"""Build a read-only StrategyGroup runtime goal status artifact.

This artifact is for the main control goal loop. It summarizes current watcher,
source-readiness, dry-run audit, and deployment evidence into one decision
surface. It never calls exchange write APIs, FinalGate, Operation Layer, or
Tokyo APIs; callers provide already-written report files.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    FileBackedRuntimeControlStateRepository,
    PgBackedRuntimeControlStateRepository,
)

DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
DEFAULT_OUTPUT_JSON = DEFAULT_REPORT_DIR / "strategygroup-runtime-goal-status.json"

SOURCE_ARTIFACT_FILES = {
    "watcher_tick": "watcher-tick.json",
    "latest_summary": "latest-summary.json",
    "wakeup": "wakeup-evidence.json",
    "post_signal_resume": "post-signal-resume-pack.json",
    "resume_dispatch": "resume-dispatch-artifact.json",
    "runtime_dry_run_audit": "runtime-dry-run-audit-chain.json",
    "source_readiness": "owner-console-source-readiness.json",
    "pilot_status": "strategygroup-runtime-pilot-status.json",
    "live_facts_readiness": "strategy-group-live-facts-readiness.json",
}
OPTIONAL_SOURCE_ARTIFACT_KEYS = {"wakeup", "candidate_pool"}

DANGEROUS_TRUE_KEYS = {
    "exchange_write_called",
    "exchange_called",
    "order_created",
    "real_order_created",
    "order_lifecycle_called",
    "execution_intent_created",
    "withdrawal_or_transfer_created",
    "modifies_secret_or_credentials",
    "modifies_live_profile",
    "modifies_order_sizing_defaults",
    "finalgate_bypassed",
    "operation_layer_bypassed",
}

WAITING_STATUSES = {
    "waiting_for_signal",
    "watching_no_signal",
    "waiting_for_market",
}

WAITING_BLOCKER_FRAGMENTS = {
    "strategy_signal_not_ready_for_shadow_candidate_prepare",
    "no_fresh_strategy_signal",
    "waiting_for_market",
}

FRESH_SIGNAL_STATUSES = {
    "ready_for_non_executing_prepare",
    "runtime_signal_ready_for_non_executing_prepare",
    "ready_for_fresh_submit_authorization",
    "waiting_for_fresh_authorization",
    "ready_for_action_time_final_gate",
    "ready_for_final_gate_preflight",
    "finalgate_ready",
}

REQUIRED_DRY_RUN_CHECKS = {
    "required_scenarios_present",
    "all_scenarios_passed",
    "dangerous_effects_absent",
    "disabled_smoke_not_real_execution_proof",
    "operation_layer_evidence_relay_checked",
    "scoped_pipeline_operation_layer_submit_projection_checked",
    "fresh_signal_fast_auto_chain_checked",
    "required_facts_readiness_checked",
    "legacy_local_registration_probe_tolerance_checked",
    "mock_operation_layer_closed_loop_checked",
    "operation_layer_blocker_review_policy_checked",
    "operation_layer_hard_safety_blocker_matrix_checked",
    "expanded_watcher_scope_execution_guard_checked",
    "operation_layer_authorization_chain_guard_checked",
    "post_submit_closed_loop_evidence_guard_checked",
    "post_submit_exit_outcome_matrix_checked",
    "reduce_only_recovery_standing_authorization_checked",
    "operation_layer_submit_result_identity_guard_checked",
    "post_submit_finalize_result_identity_guard_checked",
    "shared_runtime_pipeline_checked",
    "common_execution_chain_reuse_checked",
    "strategygroup_adapter_boundary_checked",
    "strategy_intake_no_execution_pipeline_fields_checked",
    "runtime_tier_policy_checked",
    "only_mpg_tiny_real_order_eligible_checked",
    "new_strategygroups_default_observe_only_checked",
    "selected_strategygroup_dispatch_guard_checked",
    "all_selected_strategygroups_reach_finalgate_dispatch_checked",
    "execution_attempt_rehearsal_prepare_checked",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _read_source_artifact(
    report_dir: Path,
    key: str,
    filename: str,
) -> dict[str, Any] | None:
    return _read_json(report_dir / filename)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _artifact_data(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return {}
    nested = artifact.get("data")
    return nested if isinstance(nested, dict) else artifact


def _artifact_status(artifact: dict[str, Any] | None) -> str:
    return str(_artifact_data(artifact).get("status") or "").strip()


def _dispatch_artifact_status(artifact: dict[str, Any] | None) -> str:
    return str(_artifact_data(artifact).get("dispatch_status") or "").strip()


def _artifact_blockers(artifact: dict[str, Any] | None) -> list[str]:
    return [
        str(item)
        for item in _list(_artifact_data(artifact).get("blockers"))
        if str(item)
    ]


def _non_waiting_artifact_blockers(
    artifact: dict[str, Any] | None,
) -> list[str]:
    blockers: list[str] = []
    for blocker in _artifact_blockers(artifact):
        text = blocker.lower()
        if any(fragment in text for fragment in WAITING_BLOCKER_FRAGMENTS):
            continue
        blockers.append(blocker)
    return blockers


def _artifact_blocker_class(artifact: dict[str, Any] | None) -> str:
    data = _artifact_data(artifact)
    owner_state = _dict(data.get("owner_state"))
    return str(
        data.get("blocker_class") or owner_state.get("blocker_class") or ""
    ).strip()


def _ready_runtime_signal_count(artifact: dict[str, Any] | None) -> int:
    data = _artifact_data(artifact)
    value = data.get("ready_runtime_signals")
    if value is None:
        value = _dict(data.get("summary")).get("runtime_ready_signal_count")
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        rows = value.get("rows") or value.get("items") or value.get("signals")
        if isinstance(rows, list):
            return len(rows)
    return 0


def _walk_dangerous(value: Any, path: str, out: list[str]) -> None:
    if isinstance(value, dict):
        if value.get("simulated_exchange_effects") is True:
            return
        for key, nested in value.items():
            nested_path = f"{path}.{key}" if path else str(key)
            if key in DANGEROUS_TRUE_KEYS and nested is True:
                out.append(nested_path)
            _walk_dangerous(nested, nested_path, out)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _walk_dangerous(nested, f"{path}[{index}]", out)


def _dangerous_effects(*source_artifacts: dict[str, Any] | None) -> list[str]:
    findings: list[str] = []
    for index, artifact in enumerate(source_artifacts):
        _walk_dangerous(artifact, f"artifact[{index}]", findings)
    return sorted(set(findings))


def _dangerous_scan_artifacts(
    source_artifacts: dict[str, dict[str, Any] | None],
) -> list[dict[str, Any] | None]:
    scan_artifacts: list[dict[str, Any] | None] = []
    for key, artifact in source_artifacts.items():
        if key == "runtime_dry_run_audit":
            dry_run = _artifact_data(artifact)
            checks = _dict(dry_run.get("checks"))
            if (
                dry_run.get("status") == "passed"
                and checks.get("dangerous_effects_absent") is True
            ):
                continue
        scan_artifacts.append(artifact)
    return scan_artifacts


def _release_head(release_manifest: dict[str, Any] | None) -> str | None:
    data = _dict(release_manifest)
    local_git = _dict(data.get("local_git"))
    return str(local_git.get("head") or data.get("head") or "").strip() or None


def _source_owner_summary(artifact: dict[str, Any] | None) -> dict[str, Any]:
    data = _artifact_data(artifact)
    return _dict(data.get("owner_summary"))


def _source_health_item(
    artifact: dict[str, Any] | None,
    key: str,
) -> dict[str, Any]:
    data = _artifact_data(artifact)
    return _dict(_dict(data.get("source_health")).get(key))


def _source_deploy_channel_artifact_blockers(
    artifact: dict[str, Any] | None,
) -> list[str]:
    item = _source_health_item(artifact, "deploy_channel")
    status = str(item.get("status") or "").strip()
    if status in {"", "ready", "ready_empty"}:
        return []
    summary = _dict(item.get("summary"))
    blockers = [
        str(value)
        for value in _list(summary.get("blockers"))
        if str(value)
    ]
    reason = str(item.get("reason") or item.get("detail") or "").strip()
    if reason:
        blockers.extend(
            part.strip()
            for part in reason.split(",")
            if part.strip()
        )
    if not blockers:
        blockers.append(status)
    return sorted({f"deploy_channel:{item}" for item in blockers})


def _combined_blocker_text(
    source_artifacts: dict[str, dict[str, Any] | None],
    blockers: list[str],
) -> str:
    parts = list(blockers)
    for artifact in source_artifacts.values():
        parts.extend(_artifact_blockers(artifact))
    return " ".join(parts).lower()


def _combined_artifact_blockers(
    source_artifacts: dict[str, dict[str, Any] | None],
    blockers: list[str],
) -> list[str]:
    combined = list(blockers)
    for artifact in source_artifacts.values():
        combined.extend(_artifact_blockers(artifact))
    return [str(item) for item in combined if str(item)]


def _contains_any(text: str, fragments: tuple[str, ...]) -> bool:
    return any(fragment in text for fragment in fragments)


def _contains_blocker_family(text: str, families: tuple[str, ...]) -> bool:
    if not text:
        return False
    pattern = re.compile(
        r"(?<![a-z0-9_])(" + "|".join(re.escape(family) for family in families) + r")(?![a-z0-9_])",
        re.IGNORECASE,
    )
    return bool(pattern.search(text))


def _has_active_position_or_open_order_conflict(
    source_artifacts: dict[str, dict[str, Any] | None],
    blockers: list[str],
) -> bool:
    conflict_families = (
        "active_position",
        "active_position_conflict",
        "active_position_exists",
        "active_position_present",
        "active_position_resolution",
        "conflicting_active_position",
        "conflicting_open_order",
        "open_order",
        "open_order_conflict",
        "open_order_exists",
        "open_order_present",
        "open_order_resolution",
        "open_orders_present",
    )
    non_conflict_fragments = (
        ":missing",
        "_missing",
        "missing_",
        ":not_ready",
        "_not_ready",
        "not_ready_",
    )
    for blocker in _combined_artifact_blockers(source_artifacts, blockers):
        text = blocker.lower()
        if any(fragment in text for fragment in non_conflict_fragments):
            continue
        if _contains_blocker_family(text, conflict_families):
            return True
    return False


def _readiness_item(
    key: str,
    status: str,
    blocker_class: str,
    blocks_real_submit: bool,
    detail: str,
    evidence: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "status": status,
        "blocker_class": blocker_class,
        "blocks_real_submit": blocks_real_submit,
        "detail": detail,
        "evidence": evidence,
    }


def _real_order_readiness_matrix(
    *,
    status: str,
    checks: dict[str, bool],
    source_artifacts: dict[str, dict[str, Any] | None],
    blockers: list[str],
    dangerous_effects: list[str],
    real_order_ready: bool,
) -> list[dict[str, Any]]:
    blocker_text = _combined_blocker_text(source_artifacts, blockers)
    source_summary = _source_owner_summary(source_artifacts.get("source_readiness"))
    dispatch_status = _dispatch_artifact_status(source_artifacts.get("resume_dispatch"))
    resume_status = _artifact_status(source_artifacts.get("resume_dispatch")) or _artifact_status(
        source_artifacts.get("post_signal_resume")
    )

    has_active_position_blocker = _has_active_position_or_open_order_conflict(
        source_artifacts,
        blockers,
    )
    has_protection_blocker = _contains_any(
        blocker_text,
        (
            "missing_protection",
            "protection_missing",
            "protection_not_ready",
            "protection:missing",
        ),
    )
    has_budget_blocker = _contains_any(
        blocker_text,
        (
            "missing_budget",
            "budget_missing",
            "budget_not_ready",
            "budget_exhausted",
            "budget:missing",
        ),
    )
    has_duplicate_blocker = _contains_any(
        blocker_text,
        ("duplicate_submit", "idempotency", "duplicate_order"),
    )
    has_scope_param_blocker = _contains_blocker_family(
        blocker_text,
        (
            "fresh_signal_outside_selected_strategygroup_scope",
            "outside_selected_strategygroup_scope",
            "outside_side_scope",
            "outside_symbol_scope",
            "selected_strategygroup_scope_mismatch",
            "scope_mismatch",
            "symbol",
            "symbol_mismatch",
            "symbol_scope_mismatch",
            "side",
            "side_mismatch",
            "side_scope_mismatch",
            "notional",
            "notional_mismatch",
            "notional_scope_mismatch",
            "leverage",
            "leverage_mismatch",
            "leverage_scope_mismatch",
            "max_exposure",
            "max_exposure_mismatch",
            "max_exposure_scope_mismatch",
        ),
    )
    has_runtime_order_capable_profile_blocker = _contains_any(
        blocker_text,
        (
            "brc_execution_permission_max_not_order_allowed",
            "runtime_exchange_submit_gateway_binding_not_enabled",
            "exchange_submit_execution_disabled",
            "exchange_submit_execution_not_enabled",
            "exchange_submit_gateway_binding_not_ready",
            "gateway_binding_not_enabled",
            "permission_max_not_order_allowed",
            "execution_permission_max_not_order_allowed",
            "runtime_order_capable_profile_not_ready",
            "runtime_order_capable_env_not_ready",
        ),
    )
    deployment_channel_blocked = status == "deployment_issue" or any(
        str(item).startswith("deploy_channel:") for item in blockers
    )

    return [
        _readiness_item(
            "deployment_channel",
            "blocked" if deployment_channel_blocked else "pass",
            "deployment_issue" if deployment_channel_blocked else "none",
            deployment_channel_blocked,
            (
                "部署通道暂不可用"
                if deployment_channel_blocked
                else "部署通道未阻断当前链路"
            ),
            "owner-console-source-readiness.source_health.deploy_channel",
        ),
        _readiness_item(
            "selected_strategygroup_scope",
            "pass" if checks["selected_strategygroup_scope_ready"] else "blocked",
            "none" if checks["selected_strategygroup_scope_ready"] else "hard_safety_stop",
            not checks["selected_strategygroup_scope_ready"],
            (
                "当前 signal 属于 selected StrategyGroup 范围"
                if checks["selected_strategygroup_scope_ready"]
                else "signal 或 runtime scope 不属于当前 selected StrategyGroup"
            ),
            "pilot_status.watcher_scope_alignment",
        ),
        _readiness_item(
            "fresh_signal",
            "pass" if checks["fresh_signal_present"] else "waiting_for_market",
            "none" if checks["fresh_signal_present"] else "waiting_for_market",
            not checks["fresh_signal_present"],
            "已检测到 fresh signal" if checks["fresh_signal_present"] else "当前没有 fresh signal",
            "latest_summary/post_signal_resume/resume_dispatch",
        ),
        _readiness_item(
            "required_facts",
            "pass" if checks["live_facts_ready"] else "blocked",
            "none" if checks["live_facts_ready"] else "missing_fact",
            not checks["live_facts_ready"],
            "RequiredFacts / live facts ready" if checks["live_facts_ready"] else "RequiredFacts / live facts 不完整",
            "strategy-group-live-facts-readiness.json",
        ),
        _readiness_item(
            "candidate_authorization",
            (
                "pass"
                if status in {"action_time_finalgate_ready", "operation_layer_ready"}
                else "waiting_for_chain"
                if checks["fresh_signal_present"]
                else "waiting_for_market"
            ),
            (
                "none"
                if status in {"action_time_finalgate_ready", "operation_layer_ready"}
                else "missing_fact"
                if checks["fresh_signal_present"]
                else "waiting_for_market"
            ),
            status not in {"action_time_finalgate_ready", "operation_layer_ready"},
            "candidate / authorization evidence 状态",
            "post_signal_resume/resume_dispatch",
        ),
        _readiness_item(
            "action_time_finalgate",
            (
                "pass"
                if status == "operation_layer_ready"
                else "waiting_for_chain"
                if status
                in {
                    "fresh_signal_detected",
                    "fresh_signal_processing",
                    "action_time_finalgate_ready",
                }
                else "waiting_for_market"
                if not checks["fresh_signal_present"]
                else "blocked"
            ),
            (
                "none"
                if status == "operation_layer_ready"
                else "waiting_for_market"
                if not checks["fresh_signal_present"]
                else "missing_fact"
            ),
            status != "operation_layer_ready",
            "需要 action-time FinalGate pass 后才能真实 submit",
            f"resume_dispatch.dispatch_status={dispatch_status or resume_status}",
        ),
        _readiness_item(
            "official_operation_layer",
            "pass" if real_order_ready else "waiting_for_chain",
            (
                "none"
                if real_order_ready
                else "missing_fact"
                if checks["fresh_signal_present"]
                else "waiting_for_market"
            ),
            not real_order_ready,
            "官方 Operation Layer evidence 状态",
            "resume_dispatch",
        ),
        _readiness_item(
            "runtime_order_capable_profile",
            "blocked" if has_runtime_order_capable_profile_blocker else "pass",
            "deployment_issue"
            if has_runtime_order_capable_profile_blocker
            else "none",
            has_runtime_order_capable_profile_blocker,
            (
                "runtime order-capable profile 未就绪"
                if has_runtime_order_capable_profile_blocker
                else "runtime order-capable profile 未发现阻断"
            ),
            "resume_dispatch.blockers/gateway_readiness",
        ),
        _readiness_item(
            "active_position_open_order",
            "blocked" if has_active_position_blocker else "pass",
            "active_position_resolution" if has_active_position_blocker else "none",
            has_active_position_blocker,
            (
                "存在持仓或挂单冲突"
                if has_active_position_blocker
                else f"{source_summary.get('orders') or '订单正常'} / {source_summary.get('positions') or '持仓正常'}"
            ),
            "live_facts_readiness/resume_dispatch.blockers",
        ),
        _readiness_item(
            "protection",
            "blocked" if has_protection_blocker else "pass",
            "missing_fact" if has_protection_blocker else "none",
            has_protection_blocker,
            "保护未就绪" if has_protection_blocker else str(source_summary.get("protection") or "保护正常"),
            "live_facts_readiness/source_readiness",
        ),
        _readiness_item(
            "budget",
            "blocked" if has_budget_blocker else "pass",
            "missing_fact" if has_budget_blocker else "none",
            has_budget_blocker,
            "预算未就绪" if has_budget_blocker else str(source_summary.get("funds") or "资金正常"),
            "live_facts_readiness/source_readiness",
        ),
        _readiness_item(
            "duplicate_submit",
            "blocked" if has_duplicate_blocker else "pass",
            "hard_safety_stop" if has_duplicate_blocker else "none",
            has_duplicate_blocker,
            "存在重复提交风险" if has_duplicate_blocker else "未发现 duplicate-submit blocker",
            "resume_dispatch.blockers/operation_layer_readiness",
        ),
        _readiness_item(
            "symbol_side_notional_leverage_scope",
            "blocked" if has_scope_param_blocker else "pass",
            "hard_safety_stop" if has_scope_param_blocker else "none",
            has_scope_param_blocker,
            (
                "symbol / side / notional / leverage 不在 Owner-allocated subaccount/profile boundary 内"
                if has_scope_param_blocker
                else "未发现 symbol / side / notional / leverage scope blocker"
            ),
            "resume_dispatch.blockers/selected_scope",
        ),
        _readiness_item(
            "hard_safety",
            "blocked" if dangerous_effects else "pass",
            "hard_safety_stop" if dangerous_effects else "none",
            bool(dangerous_effects),
            "发现 forbidden-effect 标记" if dangerous_effects else "未发现 forbidden-effect 标记",
            "dangerous_effects scan",
        ),
    ]


def _matrix_submit_blocking_items(
    readiness_matrix: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        item
        for item in readiness_matrix
        if item.get("blocks_real_submit") is True
    ]


def _status_from_submit_artifact_blockers(
    blocking_items: list[dict[str, Any]],
) -> tuple[str, str, str]:
    keys = {str(item.get("key") or "") for item in blocking_items}
    if "active_position_open_order" in keys:
        return (
            "active_position_resolution",
            "record_submit_blocker_review_and_resolve_active_position",
            "Operation Layer evidence 已到边界，但存在持仓或挂单冲突，真实提交保持关闭",
        )
    if keys & {
        "runtime_order_capable_profile",
        "deployment_channel",
    }:
        return (
            "deployment_issue",
            "repair_runtime_order_capable_profile_or_deploy_channel",
            "Operation Layer evidence 已到边界，但 runtime order-capable profile 或部署通道未就绪，真实提交保持关闭",
        )
    if keys & {
        "selected_strategygroup_scope",
        "symbol_side_notional_leverage_scope",
        "duplicate_submit",
        "hard_safety",
    }:
        return (
            "hard_safety_stop",
            "record_submit_blocker_review_artifact",
            "Operation Layer evidence 已到边界，但存在真实提交硬阻断，真实提交保持关闭",
        )
    return (
        "missing_fact",
        "record_submit_blocker_review_and_refresh_required_facts",
        "Operation Layer evidence 已到边界，但仍有事实、保护或预算缺口，真实提交保持关闭",
    )


def _resolve_output_json(
    *,
    report_dir: Path,
    output_json: Path | None,
    report_dir_explicit: bool,
) -> Path:
    if output_json is not None:
        return output_json
    if report_dir_explicit:
        return report_dir / DEFAULT_OUTPUT_JSON.name
    return DEFAULT_OUTPUT_JSON


def _runtime_dry_run_required_checks_passed(checks: dict[str, Any]) -> bool:
    return all(checks.get(name) is True for name in REQUIRED_DRY_RUN_CHECKS)


def _runtime_dry_run_missing_required_checks(checks: dict[str, Any]) -> list[str]:
    return sorted(name for name in REQUIRED_DRY_RUN_CHECKS if checks.get(name) is not True)


def _has_fresh_signal(source_artifacts: dict[str, dict[str, Any] | None]) -> bool:
    if _candidate_pool_fresh_row(source_artifacts):
        return True
    if _candidate_pool_authoritative_no_fresh_signal(source_artifacts):
        return False
    authoritative_names = (
        "latest_summary",
        "post_signal_resume",
        "resume_dispatch",
        "pilot_status",
    )
    authoritative_statuses = {
        _artifact_status(source_artifacts.get(name))
        for name in authoritative_names
        if source_artifacts.get(name) is not None
    }
    authoritative_ready_signal_count = sum(
        _ready_runtime_signal_count(source_artifacts.get(name))
        for name in authoritative_names
    )
    if (
        authoritative_statuses
        and not (authoritative_statuses & FRESH_SIGNAL_STATUSES)
        and authoritative_ready_signal_count == 0
        and all(
            status in WAITING_STATUSES
            or status in {"blocked_operator_review", "owner_attention_pending"}
            for status in authoritative_statuses
        )
    ):
        return False
    if any(
        _ready_runtime_signal_count(source_artifacts.get(name)) > 0
        for name in (
            "latest_summary",
            "wakeup",
            "post_signal_resume",
            "resume_dispatch",
            "pilot_status",
        )
    ):
        return True
    statuses = {
        _artifact_status(source_artifacts.get("wakeup")),
        _artifact_status(source_artifacts.get("latest_summary")),
        _artifact_status(source_artifacts.get("post_signal_resume")),
        _artifact_status(source_artifacts.get("resume_dispatch")),
        _artifact_status(source_artifacts.get("pilot_status")),
        _dispatch_artifact_status(source_artifacts.get("resume_dispatch")),
    }
    return bool(statuses & FRESH_SIGNAL_STATUSES)


def _candidate_pool_fresh_row(
    source_artifacts: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    candidate_pool = _artifact_data(source_artifacts.get("candidate_pool"))
    if candidate_pool.get("status") != "strategy_live_candidate_pool_ready":
        return {}
    for key in ("action_time_lane_inputs", "promotion_candidates"):
        for row in _list(candidate_pool.get(key)):
            row_dict = _dict(row)
            if row_dict:
                return row_dict
    for row in _list(candidate_pool.get("symbol_readiness_rows")):
        row_dict = _dict(row)
        if str(row_dict.get("signal_state") or "") == "fresh":
            return row_dict
    return {}


def _candidate_pool_fresh_row_scope_ready(
    source_artifacts: dict[str, dict[str, Any] | None],
) -> bool:
    row = _candidate_pool_fresh_row(source_artifacts)
    coverage = _dict(row.get("server_runtime_coverage"))
    return (
        str(coverage.get("state") or "") == "active_watcher_scope"
        and bool(_list(coverage.get("active_runtime_instance_ids")))
        and bool(_list(coverage.get("selected_runtime_instance_ids")))
    )


def _candidate_pool_runtime_coverage_ready(
    source_artifacts: dict[str, dict[str, Any] | None],
) -> bool:
    candidate_pool = _artifact_data(source_artifacts.get("candidate_pool"))
    if candidate_pool.get("status") != "strategy_live_candidate_pool_ready":
        return False
    coverage = _dict(candidate_pool.get("server_runtime_coverage"))
    if coverage.get("status") != "complete":
        return False
    expected = coverage.get("expected_row_count")
    active_matched = coverage.get("active_matched_row_count")
    missing = coverage.get("missing_row_count")
    if not isinstance(expected, int) or expected <= 0:
        return False
    if active_matched != expected or missing != 0:
        return False
    rows = _list(coverage.get("rows"))
    if len(rows) != expected:
        return False
    for value in rows:
        row = _dict(value)
        if row.get("state") != "active_watcher_scope":
            return False
        if row.get("blocker_class") not in {"", None, "none"}:
            return False
        if not _list(row.get("active_runtime_instance_ids")):
            return False
        if not _list(row.get("selected_runtime_instance_ids")):
            return False
    return True


def _candidate_pool_authoritative_no_fresh_signal(
    source_artifacts: dict[str, dict[str, Any] | None],
) -> bool:
    candidate_pool = _artifact_data(source_artifacts.get("candidate_pool"))
    if candidate_pool.get("status") != "strategy_live_candidate_pool_ready":
        return False
    if not _candidate_pool_runtime_coverage_ready(source_artifacts):
        return False
    if _list(candidate_pool.get("action_time_lane_inputs")):
        return False
    if _list(candidate_pool.get("promotion_candidates")):
        return False
    return not any(
        str(_dict(row).get("signal_state") or "") == "fresh"
        for row in _list(candidate_pool.get("symbol_readiness_rows"))
    )


def _selected_runtime_instance_ids(artifact: dict[str, Any] | None) -> list[str]:
    return [
        str(item)
        for item in _list(_artifact_data(artifact).get("selected_runtime_instance_ids"))
        if str(item)
    ]


def _pilot_matched_runtime_instance_ids(artifact: dict[str, Any] | None) -> list[str]:
    alignment = _dict(_artifact_data(artifact).get("watcher_scope_alignment"))
    rows = _list(alignment.get("matched_runtime_signal_summaries"))
    return [
        str(_dict(item).get("runtime_instance_id"))
        for item in rows
        if str(_dict(item).get("runtime_instance_id") or "")
    ]


def _candidate_universe_active_runtime_instance_ids(
    source_artifacts: dict[str, dict[str, Any] | None],
) -> set[str]:
    ids: set[str] = set()
    for key in ("latest_summary", "watcher_tick", "pilot_status"):
        coverage = _dict(_artifact_data(source_artifacts.get(key)).get("candidate_universe_coverage"))
        rows = _list(coverage.get("rows"))
        for row_value in rows:
            row = _dict(row_value)
            if row.get("state") != "active_watcher_scope":
                continue
            if row.get("blocker_class") not in {"", None, "none"}:
                continue
            ids.update(str(item) for item in _list(row.get("active_runtime_instance_ids")) if str(item))
            ids.update(str(item) for item in _list(row.get("selected_runtime_instance_ids")) if str(item))
    return ids


def _selected_scope_artifact_blockers(
    *,
    source_artifacts: dict[str, dict[str, Any] | None],
    fresh_signal_present: bool,
) -> list[str]:
    if not fresh_signal_present:
        return []
    if _candidate_pool_fresh_row_scope_ready(source_artifacts):
        return []
    if _candidate_pool_runtime_coverage_ready(source_artifacts):
        return []

    pilot = _artifact_data(source_artifacts.get("pilot_status"))
    alignment = _dict(pilot.get("watcher_scope_alignment"))
    if not alignment:
        return []

    alignment_status = str(alignment.get("status") or "")
    if alignment_status == "mismatch":
        return ["selected_strategygroup_scope_mismatch"]

    matched_ids = set(_pilot_matched_runtime_instance_ids(source_artifacts.get("pilot_status")))
    if not matched_ids:
        return ["selected_strategygroup_matched_runtime_ids_missing"]
    covered_ids = _candidate_universe_active_runtime_instance_ids(source_artifacts)
    if alignment_status == "expanded_scope":
        out_of_scope_rows = _list(alignment.get("out_of_scope_runtime_signal_summaries"))
        actionable_out_of_scope = [
            str(_dict(item).get("runtime_instance_id"))
            for item in out_of_scope_rows
            if str(_dict(item).get("status") or "") in FRESH_SIGNAL_STATUSES
            and str(_dict(item).get("runtime_instance_id") or "")
        ]
        unauthorized_out_of_scope = [
            runtime_id
            for runtime_id in actionable_out_of_scope
            if runtime_id not in covered_ids
        ]
        if unauthorized_out_of_scope:
            return [
                f"fresh_signal_outside_selected_strategygroup_scope:{runtime_id}"
                for runtime_id in sorted(set(unauthorized_out_of_scope))
            ]
        return []

    candidate_ids = (
        _selected_runtime_instance_ids(source_artifacts.get("resume_dispatch"))
        or _selected_runtime_instance_ids(source_artifacts.get("post_signal_resume"))
        or _selected_runtime_instance_ids(source_artifacts.get("latest_summary"))
    )
    if not candidate_ids:
        return ["fresh_signal_runtime_instance_id_missing"]

    selected_scope_ids = matched_ids | covered_ids
    out_of_scope_ids = sorted(set(candidate_ids) - selected_scope_ids)
    if out_of_scope_ids:
        return [
            f"fresh_signal_outside_selected_strategygroup_scope:{runtime_id}"
            for runtime_id in out_of_scope_ids
        ]
    return []


def _watcher_operational_liveness_blockers(
    artifact: dict[str, Any] | None,
) -> list[str]:
    operational_fragments = (
        "loop_command_failed",
        "supervisor_command_failed",
        "status_command_failed",
        "status_artifact_missing",
        "status_artifact_unreadable",
        "status_artifact_stale",
        "blocked_forbidden_effect",
        "forbidden_effect",
        "runtime_attempts_exhausted",
    )
    ignored_chain_fragments = (
        "followup_command_failed",
        "prepared_authorization_id_missing",
        "order_candidate_id_or_authorization_id_required",
        "next-attempt-position-order-conflict",
        "active_position",
        "open_order",
        "conflicting_open_order",
    )
    blockers: list[str] = []
    watcher_status_evidence_status = str(
        _artifact_data(artifact).get("watcher_status_evidence_status") or ""
    )
    for blocker in _non_waiting_artifact_blockers(artifact):
        text = blocker.lower()
        if "loop_command_failed" in text and watcher_status_evidence_status == "ok":
            continue
        if any(fragment in text for fragment in ignored_chain_fragments):
            continue
        if any(fragment in text for fragment in operational_fragments):
            blockers.append(blocker)
    return blockers


def _watcher_liveness_artifact_blockers(
    source_artifacts: dict[str, dict[str, Any] | None],
    *,
    fresh_signal_present: bool,
) -> list[str]:
    blockers: list[str] = []
    for name in ("watcher_tick", "latest_summary"):
        artifact = source_artifacts.get(name)
        status = _artifact_status(artifact)
        operational_blockers = _watcher_operational_liveness_blockers(artifact)
        blockers.extend(
            f"{name}:{item}"
            for item in operational_blockers
        )
        if status and status not in WAITING_STATUSES and status not in FRESH_SIGNAL_STATUSES:
            if status == "watcher_attention" and not operational_blockers:
                continue
            if status == "owner_notified" and not operational_blockers:
                continue
            if status not in {"blocked", "owner_attention_pending"}:
                blockers.append(f"{name}:unexpected_status:{status}")
            elif not operational_blockers:
                continue
    return sorted(set(blockers))


def _current_artifact_status(
    *,
    checks: dict[str, bool],
    source_artifacts: dict[str, dict[str, Any] | None],
    dangerous_effects: list[str],
    deployment_blockers: list[str],
    watcher_liveness_blockers: list[str],
    selected_scope_blockers: list[str],
) -> tuple[str, str, str, bool]:
    if dangerous_effects:
        return (
            "hard_safety_stop",
            "stop_and_investigate_forbidden_effects",
            "发现危险效果标记，禁止继续靠近实盘动作",
            False,
        )
    dispatch_blocker_class = _artifact_blocker_class(source_artifacts.get("resume_dispatch"))
    if dispatch_blocker_class == "hard_safety_stop":
        return (
            "hard_safety_stop",
            "stop_and_investigate_hard_safety_stop",
            "官方接力状态报告 hard safety stop，禁止继续靠近实盘动作",
            False,
        )
    if deployment_blockers:
        return (
            "deployment_issue",
            "repair_deploy_channel_while_continuing_watcher_observation",
            "部署通道或目标部署状态不可用，watcher 可继续观察，真实提交保持关闭",
            False,
        )
    if not checks["required_artifacts_present"]:
        return (
            "missing_fact",
            "refresh_required_runtime_artifacts",
            "主链路状态所需产物不完整，先刷新本地/东京只读证据",
            False,
        )
    if not checks["runtime_dry_run_audit_passed"]:
        return (
            "dry_run_audit_degraded",
            "repair_runtime_dry_run_audit_chain",
            "审计演练未通过，先修主链路断点",
            False,
        )
    if not checks["source_readiness_ready"]:
        return (
            "source_readiness_degraded",
            "refresh_or_repair_owner_console_source_readiness",
            "Owner Console source readiness 不健康",
            False,
        )
    if not checks["live_facts_ready"]:
        return (
            "missing_fact",
            "refresh_strategy_group_live_facts_readiness",
            "live facts 尚未 ready，不能进入实盘动作边界",
            False,
        )
    if selected_scope_blockers:
        return (
            "runtime_scope_mismatch",
            "ignore_out_of_scope_signal_and_continue_selected_scope_observation",
            "fresh signal 不属于当前 selected StrategyGroup 范围，不能靠近实盘动作",
            False,
        )
    if dispatch_blocker_class == "active_position_resolution":
        return (
            "active_position_resolution",
            "resolve_active_position_or_open_order_conflict",
            "存在持仓或挂单冲突，必须先完成 active position resolution",
            False,
        )
    if dispatch_blocker_class == "missing_fact":
        return (
            "missing_fact",
            "repair_missing_operation_layer_evidence",
            "Operation Layer 接力证据不完整，先补齐缺失 evidence",
            False,
        )
    if watcher_liveness_blockers:
        return (
            "runtime_liveness_degraded",
            "repair_runtime_attempt_renewal_or_scope",
            "watcher 已报告 runtime attempt 或 scope 接力异常，先修复自动观察链路",
            False,
        )

    dispatch_status = _dispatch_artifact_status(source_artifacts.get("resume_dispatch"))
    latest_status = _artifact_status(source_artifacts.get("latest_summary"))
    post_status = _artifact_status(source_artifacts.get("post_signal_resume"))
    if not checks["fresh_signal_present"] and (
        latest_status in WAITING_STATUSES or post_status in WAITING_STATUSES
    ):
        return (
            "waiting_for_signal",
            "continue_watcher_observation",
            "系统健康，当前等待市场机会",
            False,
        )

    chain_statuses = {
        _artifact_status(source_artifacts.get("resume_dispatch")),
        _artifact_status(source_artifacts.get("post_signal_resume")),
        _artifact_status(source_artifacts.get("pilot_status")),
    }
    if checks["fresh_signal_present"]:
        chain_statuses.add(_artifact_status(source_artifacts.get("wakeup")))
    chain_statuses.discard("")

    if dispatch_status == "official_operation_layer_evidence_ready":
        return (
            "operation_layer_ready",
            "call_official_operation_layer_submit_after_action_time_recheck",
            "Operation Layer evidence 已准备好，只能走官方路径",
            True,
        )
    if dispatch_status in {
        "official_finalgate_preflight_dispatch_ready",
        "official_finalgate_preflight_passed",
    } or "ready_for_action_time_final_gate" in chain_statuses:
        return (
            "action_time_finalgate_ready",
            "run_official_action_time_finalgate",
            "fresh signal 已进入 action-time FinalGate 检查点",
            False,
        )
    candidate_pool_fresh = _candidate_pool_fresh_row(source_artifacts)
    if candidate_pool_fresh:
        next_action = str(
            candidate_pool_fresh.get("next_action")
            or "refresh_private_action_time_facts_before_finalgate"
        )
        return (
            "fresh_signal_processing",
            next_action,
            "Candidate Pool 已选出 fresh action-time lane，继续非执行 action-time 前置链路",
            False,
        )
    if chain_statuses & {
        "ready_for_non_executing_prepare",
        "runtime_signal_ready_for_non_executing_prepare",
        "ready_for_fresh_submit_authorization",
        "waiting_for_fresh_authorization",
    }:
        return (
            "fresh_signal_processing",
            "prepare_candidate_grant_authorization_evidence",
            "fresh signal 已出现，先补 candidate / authorization evidence",
            False,
        )
    if _has_fresh_signal(source_artifacts):
        return (
            "fresh_signal_detected",
            "rebuild_resume_dispatch_and_prepare_evidence",
            "watcher 已发现 fresh signal，进入非执行准备链路",
            False,
        )

    if latest_status in WAITING_STATUSES or post_status in WAITING_STATUSES:
        return (
            "waiting_for_signal",
            "continue_watcher_observation",
            "系统健康，当前等待市场机会",
            False,
        )
    return (
        "needs_review",
        "review_runtime_artifacts",
        "当前状态产物无法自动归类",
        False,
    )


def _pg_rows(value: Any) -> list[dict[str, Any]]:
    return [_dict(item) for item in _list(value) if isinstance(item, dict)]


def _pg_lane_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("strategy_group_id") or ""),
        str(row.get("symbol") or ""),
        str(row.get("side") or ""),
    )


def _pg_open_action_time_lanes(
    control_state: dict[str, Any],
) -> list[dict[str, Any]]:
    open_statuses = {"opened", "facts_refreshing", "ticket_pending", "ticket_created"}
    return [
        row
        for row in _pg_rows(control_state.get("action_time_lane_inputs"))
        if row.get("lane_scope") == "real_submit_candidate"
        and row.get("status") in open_statuses
    ]


def _pg_active_tickets_by_lane(
    control_state: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    active_statuses = {"created", "preflight_pending", "finalgate_ready", "submitted"}
    tickets: dict[str, dict[str, Any]] = {}
    for row in _pg_rows(control_state.get("action_time_tickets")):
        if row.get("status") not in active_statuses:
            continue
        lane_id = str(row.get("action_time_lane_input_id") or "")
        if not lane_id:
            continue
        current = tickets.get(lane_id)
        if current is None or int(row.get("created_at_ms") or 0) >= int(
            current.get("created_at_ms") or 0
        ):
            tickets[lane_id] = row
    return tickets


def _pg_latest_safety_by_lane(
    control_state: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for row in _pg_rows(control_state.get("runtime_safety_state")):
        lane_id = str(row.get("action_time_lane_input_id") or "")
        if not lane_id:
            continue
        current = snapshots.get(lane_id)
        if current is None or int(row.get("observed_at_ms") or 0) >= int(
            current.get("observed_at_ms") or 0
        ):
            snapshots[lane_id] = row
    return snapshots


def _pg_blocker_counts(candidate_pool: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in _pg_rows(candidate_pool.get("symbol_readiness_rows")):
        blocker = str(row.get("first_blocker") or "unknown")
        counts[blocker] = counts.get(blocker, 0) + 1
    return counts


def _pg_non_market_blockers(candidate_pool: dict[str, Any]) -> list[str]:
    market_wait_blockers = {
        "computed_not_satisfied",
        "market_wait_validated",
    }
    blockers: list[str] = []
    for blocker, count in sorted(_pg_blocker_counts(candidate_pool).items()):
        if blocker in market_wait_blockers:
            continue
        if blocker.startswith("fresh_") and blocker.endswith("_absent"):
            continue
        blockers.append(f"candidate_pool_blocker:{blocker}:{count}")
    return blockers


def _pg_runtime_coverage_complete(candidate_pool: dict[str, Any]) -> bool:
    coverage = _dict(candidate_pool.get("server_runtime_coverage"))
    if coverage.get("status") != "complete":
        return False
    expected = coverage.get("expected_row_count")
    active = coverage.get("active_matched_row_count")
    missing = coverage.get("missing_row_count")
    return isinstance(expected, int) and expected > 0 and active == expected and missing == 0


def _pg_selected_scope_ready(candidate_pool: dict[str, Any]) -> bool:
    rows = (
        _pg_rows(candidate_pool.get("action_time_lane_inputs"))
        or _pg_rows(candidate_pool.get("promotion_candidates"))
    )
    if not rows:
        return True
    for row in rows:
        scope_state = str(row.get("scope_state") or "")
        if scope_state not in {
            "live_submit_allowed",
            "conditional_action_time_rehearsal_allowed",
        }:
            return False
        coverage = _dict(row.get("server_runtime_coverage"))
        if str(coverage.get("state") or "") != "active_watcher_scope":
            return False
        if not _list(coverage.get("active_runtime_instance_ids")):
            return False
        if not _list(coverage.get("selected_runtime_instance_ids")):
            return False
    return True


def _pg_open_lanes_scope_ready(
    control_state: dict[str, Any],
    open_lanes: list[dict[str, Any]],
) -> bool:
    runtime_scope_by_id = {
        str(row.get("runtime_scope_binding_id") or ""): row
        for row in _pg_rows(control_state.get("runtime_scope_bindings"))
        if row.get("status") == "active"
    }
    for lane in open_lanes:
        binding = runtime_scope_by_id.get(
            str(lane.get("runtime_scope_binding_id") or "")
        )
        if not binding:
            return False
        for key in ("strategy_group_id", "symbol", "side", "runtime_profile_id"):
            if str(lane.get(key) or "") != str(binding.get(key) or ""):
                return False
        if binding.get("selected_strategygroup_scope") is not True:
            return False
        if binding.get("symbol_side_scope_closed") is not True:
            return False
        if binding.get("notional_leverage_scope_closed") is not True:
            return False
        if binding.get("live_submit_allowed") is not True:
            return False
    return True


def _pg_active_position_conflict(
    safety_by_lane: dict[str, dict[str, Any]],
) -> bool:
    return any(row.get("active_position_conflict") is True for row in safety_by_lane.values())


def _pg_real_order_ready(
    *,
    open_lanes: list[dict[str, Any]],
    tickets_by_lane: dict[str, dict[str, Any]],
    safety_by_lane: dict[str, dict[str, Any]],
) -> bool:
    if len(open_lanes) != 1:
        return False
    lane = open_lanes[0]
    lane_id = str(lane.get("action_time_lane_input_id") or "")
    ticket = tickets_by_lane.get(lane_id, {})
    safety = safety_by_lane.get(lane_id, {})
    return (
        ticket.get("status") == "finalgate_ready"
        and safety.get("submit_allowed") is True
        and safety.get("finalgate_ready") is True
        and safety.get("operation_layer_ready") is True
        and safety.get("protection_ready") is True
        and safety.get("active_position_conflict") is False
        and safety.get("facts_fresh") is True
        and safety.get("trusted_fact_refs_complete") is True
    )


def _pg_status_tuple(
    *,
    candidate_pool: dict[str, Any],
    open_lanes: list[dict[str, Any]],
    tickets_by_lane: dict[str, dict[str, Any]],
    safety_by_lane: dict[str, dict[str, Any]],
    non_market_blockers: list[str],
    coverage_complete: bool,
    selected_scope_ready: bool,
    real_order_ready: bool,
) -> tuple[str, str, str]:
    if not selected_scope_ready:
        return (
            "runtime_scope_mismatch",
            "repair_pg_selected_scope_projection",
            "PG 当前候选交易不在 selected StrategyGroup / symbol / side scope 内",
        )
    if _pg_active_position_conflict(safety_by_lane):
        return (
            "active_position_resolution",
            "resolve_active_position_or_open_order_conflict",
            "PG runtime safety state 显示存在持仓或挂单冲突",
        )
    if real_order_ready:
        return (
            "operation_layer_ready",
            "call_official_operation_layer_submit_after_action_time_recheck",
            "PG ticket 与 runtime safety state 已到官方 Operation Layer 边界",
        )
    if open_lanes:
        lane = sorted(
            open_lanes,
            key=lambda row: (
                str(row.get("strategy_group_id") or ""),
                str(row.get("symbol") or ""),
                str(row.get("side") or ""),
            ),
        )[0]
        lane_id = str(lane.get("action_time_lane_input_id") or "")
        if lane_id not in tickets_by_lane:
            return (
                "fresh_signal_processing",
                "materialize_action_time_ticket",
                "PG action-time lane 已打开，但还没有正式 Action-Time Ticket",
            )
        ticket_status = str(tickets_by_lane[lane_id].get("status") or "")
        if ticket_status in {"created", "preflight_pending"}:
            return (
                "action_time_finalgate_ready",
                "run_official_action_time_finalgate",
                "PG Action-Time Ticket 已生成，等待 action-time FinalGate",
            )
        return (
            "fresh_signal_processing",
            "refresh_action_time_ticket_or_runtime_safety_state",
            f"PG Action-Time Ticket 当前状态为 {ticket_status or 'unknown'}",
        )
    if _pg_rows(candidate_pool.get("promotion_candidates")):
        return (
            "fresh_signal_processing",
            "select_single_action_time_lane_input",
            "PG promotion candidate 已出现，等待仲裁成单一 action-time lane",
        )
    if _candidate_pool_fresh_row({"candidate_pool": candidate_pool}):
        return (
            "fresh_signal_detected",
            "promote_fresh_signal_candidate",
            "PG Candidate Pool 已检测到 fresh signal，等待 promotion",
        )
    if non_market_blockers:
        if not coverage_complete:
            return (
                "runtime_liveness_degraded",
                "repair_pg_runtime_coverage_projection",
                "PG Candidate Pool 尚未证明完整 server-backed runtime coverage",
            )
        return (
            "missing_fact",
            "repair_pg_pretrade_readiness_projection",
            "PG Candidate Pool 仍存在非市场类前置阻断",
        )
    return (
        "waiting_for_signal",
        "continue_watcher_observation",
        "PG 当前状态已接入主控面，当前等待市场机会",
    )


def _pg_readiness_matrix(
    *,
    status: str,
    checks: dict[str, bool],
    open_lanes: list[dict[str, Any]],
    tickets_by_lane: dict[str, dict[str, Any]],
    safety_by_lane: dict[str, dict[str, Any]],
    real_order_ready: bool,
) -> list[dict[str, Any]]:
    has_open_lane = bool(open_lanes)
    active_ticket_present = any(
        str(lane.get("action_time_lane_input_id") or "") in tickets_by_lane
        for lane in open_lanes
    )
    submit_allowed = any(row.get("submit_allowed") is True for row in safety_by_lane.values())
    active_position_conflict = _pg_active_position_conflict(safety_by_lane)
    return [
        _readiness_item(
            "deployment_channel",
            "pass",
            "none",
            False,
            "部署状态不由 Goal Status PG projection 读取；交给 server monitor PG projection",
            "pg_runtime_control_state",
        ),
        _readiness_item(
            "selected_strategygroup_scope",
            "pass" if checks["selected_strategygroup_scope_ready"] else "blocked",
            "none" if checks["selected_strategygroup_scope_ready"] else "hard_safety_stop",
            not checks["selected_strategygroup_scope_ready"],
            "PG selected StrategyGroup / symbol / side scope 已闭合"
            if checks["selected_strategygroup_scope_ready"]
            else "PG selected StrategyGroup / symbol / side scope 未闭合",
            "pg_runtime_scope_bindings/owner_policy_current",
        ),
        _readiness_item(
            "fresh_signal",
            "pass" if checks["fresh_signal_present"] else "waiting_for_market",
            "none" if checks["fresh_signal_present"] else "waiting_for_market",
            not checks["fresh_signal_present"],
            "PG 当前存在 fresh signal / action-time lane"
            if checks["fresh_signal_present"]
            else "PG 当前没有 fresh signal",
            "pg_live_signal_events/pg_action_time_lane_inputs",
        ),
        _readiness_item(
            "required_facts",
            "pass" if checks["live_facts_ready"] else "blocked",
            "none" if checks["live_facts_ready"] else "missing_fact",
            checks["fresh_signal_present"] and not checks["live_facts_ready"],
            "PG action-time facts 已满足或当前无 fresh lane"
            if checks["live_facts_ready"]
            else "PG action-time facts 尚未闭合",
            "pg_runtime_fact_snapshots/pg_action_time_lane_inputs",
        ),
        _readiness_item(
            "candidate_authorization",
            "pass" if has_open_lane else "waiting_for_market",
            "none" if has_open_lane else "waiting_for_market",
            not has_open_lane,
            "PG action-time lane 已形成" if has_open_lane else "当前没有 promotion 后的 action-time lane",
            "pg_action_time_lane_inputs",
        ),
        _readiness_item(
            "action_time_ticket",
            "pass" if active_ticket_present else "waiting_for_chain",
            "none" if active_ticket_present else "missing_fact",
            has_open_lane and not active_ticket_present,
            "Action-Time Ticket 已存在" if active_ticket_present else "缺少正式 Action-Time Ticket",
            "pg_action_time_tickets",
        ),
        _readiness_item(
            "action_time_finalgate",
            "pass" if status == "operation_layer_ready" else "waiting_for_chain",
            "none" if status == "operation_layer_ready" else "missing_fact",
            status != "operation_layer_ready",
            "FinalGate / runtime safety 已通过" if status == "operation_layer_ready" else "等待 FinalGate / runtime safety 闭合",
            "pg_action_time_tickets/pg_runtime_safety_state_snapshots",
        ),
        _readiness_item(
            "official_operation_layer",
            "pass" if real_order_ready else "waiting_for_chain",
            "none" if real_order_ready else "missing_fact",
            not real_order_ready,
            "PG real submit boundary 已闭合" if real_order_ready else "官方 Operation Layer 仍未开放",
            "pg_runtime_safety_state_snapshots",
        ),
        _readiness_item(
            "runtime_order_capable_profile",
            "pass" if checks["watcher_liveness_healthy"] else "blocked",
            "none" if checks["watcher_liveness_healthy"] else "deployment_issue",
            not checks["watcher_liveness_healthy"],
            "PG server runtime coverage 完整"
            if checks["watcher_liveness_healthy"]
            else "PG server runtime coverage 不完整",
            "pg_watcher_runtime_coverage",
        ),
        _readiness_item(
            "active_position_open_order",
            "blocked" if active_position_conflict else "pass",
            "active_position_resolution" if active_position_conflict else "none",
            active_position_conflict,
            "PG runtime safety state 显示持仓/挂单冲突"
            if active_position_conflict
            else "PG runtime safety state 未显示持仓/挂单冲突",
            "pg_runtime_safety_state_snapshots",
        ),
        _readiness_item(
            "protection",
            "pass" if (not checks["fresh_signal_present"] or submit_allowed) else "waiting_for_chain",
            "none" if (not checks["fresh_signal_present"] or submit_allowed) else "missing_fact",
            checks["fresh_signal_present"] and not submit_allowed,
            "当前无 fresh lane 或 runtime safety 已证明 protection"
            if (not checks["fresh_signal_present"] or submit_allowed)
            else "等待 runtime safety protection 闭合",
            "pg_runtime_safety_state_snapshots",
        ),
        _readiness_item(
            "budget",
            "pass" if (not checks["fresh_signal_present"] or submit_allowed) else "waiting_for_chain",
            "none" if (not checks["fresh_signal_present"] or submit_allowed) else "missing_fact",
            checks["fresh_signal_present"] and not submit_allowed,
            "当前无 fresh lane 或 runtime safety 已证明预算边界"
            if (not checks["fresh_signal_present"] or submit_allowed)
            else "等待 runtime safety 预算边界闭合",
            "pg_runtime_safety_state_snapshots",
        ),
        _readiness_item(
            "duplicate_submit",
            "pass",
            "none",
            False,
            "PG 单一 real-submit lane / active ticket 约束负责防重",
            "pg_action_time_lane_inputs/pg_action_time_tickets",
        ),
        _readiness_item(
            "symbol_side_notional_leverage_scope",
            "pass" if checks["selected_strategygroup_scope_ready"] else "blocked",
            "none" if checks["selected_strategygroup_scope_ready"] else "hard_safety_stop",
            not checks["selected_strategygroup_scope_ready"],
            "PG owner policy / runtime scope 已绑定 symbol、side、notional、leverage"
            if checks["selected_strategygroup_scope_ready"]
            else "PG scope 绑定未闭合",
            "pg_owner_policy_current/pg_runtime_scope_bindings",
        ),
        _readiness_item(
            "hard_safety",
            "pass",
            "none",
            False,
            "PG Goal Status projector 不调用 FinalGate、Operation Layer 或 exchange write",
            "pg_goal_status_projector",
        ),
    ]


def _build_pg_goal_status_artifact(
    *,
    control_state: dict[str, Any],
    candidate_pool: dict[str, Any],
    report_dir: Path,
    release_manifest: Path | None,
    expected_head: str | None,
) -> dict[str, Any]:
    open_lanes = _pg_open_action_time_lanes(control_state)
    tickets_by_lane = _pg_active_tickets_by_lane(control_state)
    safety_by_lane = _pg_latest_safety_by_lane(control_state)
    non_market_blockers = _pg_non_market_blockers(candidate_pool)
    coverage_complete = _pg_runtime_coverage_complete(candidate_pool)
    selected_scope_ready = _pg_selected_scope_ready(
        candidate_pool
    ) and _pg_open_lanes_scope_ready(control_state, open_lanes)
    fresh_signal_present = bool(
        open_lanes
        or _pg_rows(candidate_pool.get("promotion_candidates"))
        or _candidate_pool_fresh_row({"candidate_pool": candidate_pool})
    )
    real_order_ready = _pg_real_order_ready(
        open_lanes=open_lanes,
        tickets_by_lane=tickets_by_lane,
        safety_by_lane=safety_by_lane,
    )
    status, next_checkpoint, owner_detail = _pg_status_tuple(
        candidate_pool=candidate_pool,
        open_lanes=open_lanes,
        tickets_by_lane=tickets_by_lane,
        safety_by_lane=safety_by_lane,
        non_market_blockers=non_market_blockers,
        coverage_complete=coverage_complete,
        selected_scope_ready=selected_scope_ready,
        real_order_ready=real_order_ready,
    )
    active_lane_ids = [
        str(row.get("action_time_lane_input_id") or "")
        for row in open_lanes
        if str(row.get("action_time_lane_input_id") or "")
    ]
    action_time_facts_ready = (
        not open_lanes
        or all(str(row.get("action_time_fact_snapshot_id") or "") for row in open_lanes)
    )
    checks = {
        "required_artifacts_present": True,
        "deployment_aligned": True,
        "runtime_dry_run_audit_passed": True,
        "source_readiness_ready": True,
        "live_facts_ready": action_time_facts_ready,
        "dangerous_effects_absent": True,
        "fresh_signal_present": fresh_signal_present,
        "selected_strategygroup_scope_ready": selected_scope_ready,
        "watcher_liveness_healthy": coverage_complete,
        "ready_for_real_order_action": real_order_ready,
        "pg_current_projection": True,
        "legacy_report_dir_read": False,
        "legacy_candidate_pool_json_read": False,
    }
    blockers = list(non_market_blockers)
    if open_lanes:
        missing_ticket_lane_ids = [
            lane_id for lane_id in active_lane_ids if lane_id not in tickets_by_lane
        ]
        blockers.extend(
            f"action_time_ticket_missing:{lane_id}" for lane_id in missing_ticket_lane_ids
        )
    if not selected_scope_ready:
        blockers.append("selected_strategygroup_scope_mismatch")
    if _pg_active_position_conflict(safety_by_lane):
        blockers.append("active_position_resolution")

    readiness_matrix = _pg_readiness_matrix(
        status=status,
        checks=checks,
        open_lanes=open_lanes,
        tickets_by_lane=tickets_by_lane,
        safety_by_lane=safety_by_lane,
        real_order_ready=real_order_ready,
    )
    matrix_submit_blockers = _matrix_submit_blocking_items(readiness_matrix)
    submit_blocker_keys = [
        str(item.get("key") or "") for item in matrix_submit_blockers
    ]
    submit_blocker_review_items = [
        item for item in matrix_submit_blockers if item.get("status") == "blocked"
    ]
    submit_blocker_review_keys = [
        str(item.get("key") or "") for item in submit_blocker_review_items
    ]
    submit_blocker_review_required = bool(submit_blocker_review_items)
    return {
        "scope": "strategygroup_runtime_goal_status",
        "generated_at_ms": int(time.time() * 1000),
        "status": status,
        "ready_for_real_order_action": real_order_ready,
        "non_authority_checkpoint": next_checkpoint,
        "owner_state": {
            "label": (
                "等待机会"
                if status == "waiting_for_signal"
                else "处理中"
                if status
                in {
                    "fresh_signal_detected",
                    "fresh_signal_processing",
                    "action_time_finalgate_ready",
                    "operation_layer_ready",
                }
                else "需要介入"
            ),
            "detail": owner_detail,
            "non_authority_checkpoint": next_checkpoint,
        },
        "checks": checks,
        "blockers": blockers,
        "evidence": {
            "report_dir": str(report_dir),
            "report_dir_ignored_for_pg_current": True,
            "release_manifest": str(release_manifest) if release_manifest else None,
            "release_manifest_ignored_for_pg_current": release_manifest is not None,
            "expected_head": expected_head,
            "deployed_head": None,
            "deploy_channel_enforced": False,
            "candidate_pool_status": _artifact_status(candidate_pool),
            "candidate_pool_source_mode": "db_backed",
            "legacy_candidate_pool_json_read": False,
            "legacy_report_dir_read": False,
            "candidate_pool_action_time_lane_input_count": len(
                _pg_rows(candidate_pool.get("action_time_lane_inputs"))
            ),
            "pg_action_time_lane_input_count": len(open_lanes),
            "pg_active_ticket_count": len(tickets_by_lane),
            "pg_runtime_safety_snapshot_count": len(safety_by_lane),
            "pg_runtime_coverage_complete": coverage_complete,
            "pg_blocker_counts": _pg_blocker_counts(candidate_pool),
            "watcher_liveness_blockers": []
            if coverage_complete
            else ["pg_runtime_coverage_incomplete"],
            "selected_scope_blockers": []
            if selected_scope_ready
            else ["selected_strategygroup_scope_mismatch"],
            "matrix_submit_blockers": submit_blocker_keys,
            "submit_blocker_review": {
                "required": submit_blocker_review_required,
                "allowed": False,
                "project_progress_allowed": False,
                "continue_observation_allowed": not submit_blocker_review_required,
                "real_submit_allowed": real_order_ready,
                "non_authority_checkpoint": next_checkpoint,
                "blocker_keys": submit_blocker_review_keys,
            },
            "active_action_time_lane_input_ids": active_lane_ids,
            "active_ticket_ids": [
                str(row.get("ticket_id") or "") for row in tickets_by_lane.values()
            ],
        },
        "real_order_boundary": {
            "ready_for_real_order_action": real_order_ready,
            "requires_selected_strategygroup": True,
            "selected_strategygroup_scope_ready": selected_scope_ready,
            "requires_allocated_subaccount_profile_boundary": True,
            "requires_fresh_signal": True,
            "requires_required_facts": True,
            "requires_candidate_grant_authorization": True,
            "requires_action_time_ticket": True,
            "requires_action_time_finalgate": True,
            "requires_official_operation_layer": True,
            "submit_blocker_review_required": submit_blocker_review_required,
            "submit_blocker_review_allowed": False,
            "project_progress_allowed": False,
            "continue_observation_allowed": not submit_blocker_review_required,
            "real_submit_allowed": real_order_ready,
            "submit_blocker_keys": submit_blocker_keys,
        },
        "real_order_readiness_matrix": readiness_matrix,
        "safety_invariants": {
            "read_only_artifact_builder": True,
            "calls_tokyo_api": False,
            "calls_exchange_write": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "creates_order": False,
            "creates_execution_intent": False,
            "modifies_secret_or_credentials": False,
            "modifies_live_profile": False,
            "modifies_order_sizing_defaults": False,
            "withdrawal_or_transfer_created": False,
            "dangerous_effects": [],
        },
    }


def build_goal_status_artifact(
    *,
    report_dir: Path,
    release_manifest: Path | None = None,
    expected_head: str | None = None,
    candidate_pool_json: Path | None = None,
    candidate_pool: dict[str, Any] | None = None,
    repository: FileBackedRuntimeControlStateRepository | None = None,
) -> dict[str, Any]:
    control_state_repository = repository or FileBackedRuntimeControlStateRepository()
    source_artifacts = control_state_repository.goal_status_source_artifacts(
        report_dir=report_dir,
        source_artifact_files=SOURCE_ARTIFACT_FILES,
        candidate_pool_json=candidate_pool_json,
    )
    if candidate_pool is not None:
        source_artifacts["candidate_pool"] = candidate_pool
    manifest_artifact = control_state_repository.release_manifest(release_manifest)
    deployed_head = _release_head(manifest_artifact)
    expected_head = expected_head or deployed_head
    deployment_blockers: list[str] = []
    if expected_head and deployed_head and expected_head != deployed_head:
        deployment_blockers.append("deployed_head_mismatch")
    if expected_head and release_manifest and not deployed_head:
        deployment_blockers.append("deployed_head_unknown")

    dry_run = _artifact_data(source_artifacts["runtime_dry_run_audit"])
    dry_run_checks = _dict(dry_run.get("checks"))
    dry_run_missing_required_checks = _runtime_dry_run_missing_required_checks(
        dry_run_checks
    )
    source = _artifact_data(source_artifacts["source_readiness"])
    source_deploy_channel_blockers = _source_deploy_channel_artifact_blockers(
        source_artifacts["source_readiness"]
    )
    deploy_channel_enforced = release_manifest is not None or expected_head is not None
    if deploy_channel_enforced:
        deployment_blockers.extend(source_deploy_channel_blockers)
    live_facts = _artifact_data(source_artifacts["live_facts_readiness"])
    dangerous = _dangerous_effects(*_dangerous_scan_artifacts(source_artifacts))
    fresh_signal_present = _has_fresh_signal(source_artifacts)
    watcher_liveness = _watcher_liveness_artifact_blockers(
        source_artifacts,
        fresh_signal_present=fresh_signal_present,
    )
    selected_scope_blockers = _selected_scope_artifact_blockers(
        source_artifacts=source_artifacts,
        fresh_signal_present=fresh_signal_present,
    )
    missing_artifacts = [
        key
        for key, value in source_artifacts.items()
        if value is None and key not in OPTIONAL_SOURCE_ARTIFACT_KEYS
    ]

    dry_run_required_check_status = {
        name: dry_run_checks.get(name) is True
        for name in sorted(REQUIRED_DRY_RUN_CHECKS)
    }

    checks = {
        "required_artifacts_present": all(
            value is not None
            for key, value in source_artifacts.items()
            if key not in OPTIONAL_SOURCE_ARTIFACT_KEYS
        ),
        "deployment_aligned": not deployment_blockers,
        "runtime_dry_run_audit_passed": (
            dry_run.get("status") == "passed"
            and dry_run_checks.get("dangerous_effects_absent") is True
            and _runtime_dry_run_required_checks_passed(dry_run_checks)
        ),
        "source_readiness_ready": source.get("status") == "ready",
        "live_facts_ready": str(live_facts.get("status") or "").startswith(
            "strategy_group_live_facts_ready"
        ),
        "dangerous_effects_absent": not dangerous,
        "fresh_signal_present": fresh_signal_present,
        "selected_strategygroup_scope_ready": not selected_scope_blockers,
        "watcher_liveness_healthy": not watcher_liveness,
        **dry_run_required_check_status,
    }
    status, next_checkpoint, owner_detail, real_order_ready = _current_artifact_status(
        checks=checks,
        source_artifacts=source_artifacts,
        dangerous_effects=dangerous,
        deployment_blockers=deployment_blockers,
        watcher_liveness_blockers=watcher_liveness,
        selected_scope_blockers=selected_scope_blockers,
    )

    source_summary = _source_owner_summary(source_artifacts["source_readiness"])
    blockers = [
        *deployment_blockers,
        *[f"missing_artifact:{key}" for key in missing_artifacts],
        *([] if checks["runtime_dry_run_audit_passed"] else ["runtime_dry_run_audit_not_passed"]),
        *[
            f"runtime_dry_run_missing_required_check:{name}"
            for name in dry_run_missing_required_checks
        ],
        *([] if checks["source_readiness_ready"] else ["source_readiness_not_ready"]),
        *([] if checks["live_facts_ready"] else ["live_facts_not_ready"]),
        *selected_scope_blockers,
        *watcher_liveness,
        *([] if checks["dangerous_effects_absent"] else ["dangerous_effects_present"]),
    ]
    readiness_matrix = _real_order_readiness_matrix(
        status=status,
        checks=checks,
        source_artifacts=source_artifacts,
        blockers=blockers,
        dangerous_effects=dangerous,
        real_order_ready=real_order_ready,
    )
    matrix_submit_blockers = _matrix_submit_blocking_items(readiness_matrix)
    submit_blocker_keys = [
        str(item.get("key") or "") for item in matrix_submit_blockers
    ]
    submit_blocker_review_items = [
        item
        for item in matrix_submit_blockers
        if item.get("status") == "blocked"
    ]
    submit_blocker_review_keys = [
        str(item.get("key") or "") for item in submit_blocker_review_items
    ]
    if real_order_ready and matrix_submit_blockers:
        status, next_checkpoint, owner_detail = _status_from_submit_artifact_blockers(
            matrix_submit_blockers
        )
        real_order_ready = False
        blockers = [
            *blockers,
            *[
                f"matrix_submit_blocker:{item.get('key')}"
                for item in matrix_submit_blockers
            ],
        ]
        readiness_matrix = _real_order_readiness_matrix(
            status=status,
            checks=checks,
            source_artifacts=source_artifacts,
            blockers=blockers,
            dangerous_effects=dangerous,
            real_order_ready=real_order_ready,
        )
        submit_blocker_keys = [
            str(item.get("key") or "") for item in matrix_submit_blockers
        ]
        submit_blocker_review_items = [
            item
            for item in matrix_submit_blockers
            if item.get("status") == "blocked"
        ]
        submit_blocker_review_keys = [
            str(item.get("key") or "") for item in submit_blocker_review_items
        ]
    checks["ready_for_real_order_action"] = real_order_ready
    submit_blocker_review_required = bool(submit_blocker_review_items)
    submit_blocker_review_allowed = (
        submit_blocker_review_required
        and not dangerous
        and status
        in {
            "active_position_resolution",
            "missing_fact",
            "hard_safety_stop",
        }
    )
    return {
        "scope": "strategygroup_runtime_goal_status",
        "generated_at_ms": int(time.time() * 1000),
        "status": status,
        "ready_for_real_order_action": real_order_ready,
        "non_authority_checkpoint": next_checkpoint,
        "owner_state": {
            "label": (
                "等待机会"
                if status == "waiting_for_signal"
                else "处理中"
                if status in {
                    "fresh_signal_detected",
                    "fresh_signal_processing",
                    "action_time_finalgate_ready",
                    "operation_layer_ready",
                }
                else "需要介入"
            ),
            "detail": owner_detail,
            "non_authority_checkpoint": next_checkpoint,
        },
        "checks": checks,
        "blockers": blockers,
        "evidence": {
            "report_dir": str(report_dir),
            "release_manifest": str(release_manifest) if release_manifest else None,
            "expected_head": expected_head,
            "deployed_head": deployed_head,
            "deploy_channel_enforced": deploy_channel_enforced,
            "deploy_channel_blockers": source_deploy_channel_blockers,
            "deploy_channel_source_health": _source_health_item(
                source_artifacts["source_readiness"],
                "deploy_channel",
            ),
            "latest_summary_status": _artifact_status(source_artifacts["latest_summary"]),
            "watcher_tick_status": _artifact_status(source_artifacts["watcher_tick"]),
            "post_signal_resume_status": _artifact_status(source_artifacts["post_signal_resume"]),
            "candidate_pool_status": _artifact_status(source_artifacts["candidate_pool"]),
            "candidate_pool_source_mode": (
                "explicit_local_diagnostic_json"
                if candidate_pool_json is not None and candidate_pool is None
                else "in_memory_diagnostic"
                if candidate_pool is not None
                else "not_provided"
            ),
            "legacy_candidate_pool_json_read": (
                candidate_pool_json is not None
                and candidate_pool is None
                and source_artifacts["candidate_pool"] is not None
            ),
            "candidate_pool_action_time_lane_input_count": len(
                _list(
                    _artifact_data(source_artifacts["candidate_pool"]).get(
                        "action_time_lane_inputs"
                    )
                )
            ),
            "resume_dispatch_status": _artifact_status(source_artifacts["resume_dispatch"]),
            "resume_dispatch_action": _artifact_data(source_artifacts["resume_dispatch"]).get(
                "dispatch_action"
            ),
            "source_owner_summary": source_summary,
            "dry_run_scenario_count": dry_run_checks.get("scenario_count"),
            "dry_run_required_checks": dry_run_required_check_status,
            "dry_run_missing_required_checks": dry_run_missing_required_checks,
            "watcher_liveness_blockers": watcher_liveness,
            "selected_scope_blockers": selected_scope_blockers,
            "matrix_submit_blockers": submit_blocker_keys,
            "submit_blocker_review": {
                "required": submit_blocker_review_required,
                "allowed": submit_blocker_review_allowed,
                "project_progress_allowed": submit_blocker_review_allowed,
                "continue_observation_allowed": submit_blocker_review_allowed,
                "real_submit_allowed": real_order_ready,
                "non_authority_checkpoint": next_checkpoint,
                "blocker_keys": submit_blocker_review_keys,
            },
            "pilot_matched_runtime_instance_ids": _pilot_matched_runtime_instance_ids(
                source_artifacts["pilot_status"]
            ),
            "resume_dispatch_selected_runtime_instance_ids": (
                _selected_runtime_instance_ids(source_artifacts["resume_dispatch"])
            ),
            "active_runtime_count": _artifact_data(source_artifacts["latest_summary"]).get(
                "active_runtime_count"
            ),
            "selected_runtime_instance_count": len(
                _list(
                    _artifact_data(source_artifacts["latest_summary"]).get(
                        "selected_runtime_instance_ids"
                    )
                )
            ),
        },
        "real_order_boundary": {
            "ready_for_real_order_action": real_order_ready,
            "requires_selected_strategygroup": True,
            "selected_strategygroup_scope_ready": not selected_scope_blockers,
            "requires_allocated_subaccount_profile_boundary": True,
            "requires_fresh_signal": True,
            "requires_required_facts": True,
            "requires_candidate_grant_authorization": True,
            "requires_action_time_finalgate": True,
            "requires_official_operation_layer": True,
            "submit_blocker_review_required": submit_blocker_review_required,
            "submit_blocker_review_allowed": submit_blocker_review_allowed,
            "project_progress_allowed": submit_blocker_review_allowed,
            "continue_observation_allowed": submit_blocker_review_allowed,
            "real_submit_allowed": real_order_ready,
            "submit_blocker_keys": submit_blocker_keys,
        },
        "real_order_readiness_matrix": readiness_matrix,
        "safety_invariants": {
            "read_only_artifact_builder": True,
            "calls_tokyo_api": False,
            "calls_exchange_write": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "creates_order": False,
            "creates_execution_intent": False,
            "modifies_secret_or_credentials": False,
            "modifies_live_profile": False,
            "modifies_order_sizing_defaults": False,
            "withdrawal_or_transfer_created": False,
            "dangerous_effects": dangerous,
        },
    }


def build_goal_status_artifact_from_control_state(
    *,
    control_state: dict[str, Any],
    report_dir: Path,
    release_manifest: Path | None = None,
    expected_head: str | None = None,
    repository: Any | None = None,
) -> dict[str, Any]:
    if control_state.get("source_mode") != "db_backed":
        raise ValueError("Goal Status PG path requires DB-backed state")
    from scripts.build_strategy_live_candidate_pool import (  # noqa: PLC0415
        build_strategy_live_candidate_pool_from_control_state,
    )

    candidate_pool = build_strategy_live_candidate_pool_from_control_state(control_state)
    artifact = _build_pg_goal_status_artifact(
        control_state=control_state,
        candidate_pool=candidate_pool,
        report_dir=report_dir,
        release_manifest=release_manifest,
        expected_head=expected_head,
    )
    artifact["source_mode"] = "db_backed"
    artifact["projection_target"] = "production_current"
    artifact["control_state_watermark"] = {
        "schema": str(control_state.get("schema") or ""),
        "table_counts": _dict(control_state.get("table_counts")),
    }
    artifact["evidence"]["candidate_pool_source_mode"] = "db_backed"
    artifact["evidence"]["legacy_candidate_pool_json_read"] = False
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a read-only StrategyGroup runtime goal status artifact."
    )
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--release-manifest", type=Path)
    parser.add_argument("--expected-head")
    parser.add_argument(
        "--candidate-pool-json",
        type=Path,
        default=None,
        help=(
            "Optional local diagnostic input only. Production current Goal Status "
            "must use --database-url/PG_DATABASE_URL with --require-database-url."
        ),
    )
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument(
        "--require-database-url",
        action="store_true",
        help="Fail instead of falling back to legacy report-dir JSON inputs when PG_DATABASE_URL is absent.",
    )
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG DSNs only in tests.",
    )
    parser.add_argument(
        "--allow-local-file-diagnostic",
        action="store_true",
        help=(
            "Allow explicit local report-dir / Candidate Pool JSON diagnostics only. "
            "Production current Goal Status must use PG."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report_dir = args.report_dir or DEFAULT_REPORT_DIR
    output_json = _resolve_output_json(
        report_dir=report_dir,
        output_json=args.output_json,
        report_dir_explicit=args.report_dir is not None,
    )
    if args.require_database_url and not args.database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for DB-backed Goal Status",
            file=sys.stderr,
        )
        return 2

    if args.database_url:
        if not args.database_url.startswith(
            ("postgresql://", "postgresql+psycopg://")
        ) and not args.allow_non_postgres_for_test:
            print(
                "ERROR: DB-backed Goal Status requires PostgreSQL DSN",
                file=sys.stderr,
            )
            return 2
        engine = sa.create_engine(args.database_url)
        try:
            with engine.connect() as conn:
                repository = PgBackedRuntimeControlStateRepository(conn)
                artifact = build_goal_status_artifact_from_control_state(
                    control_state=repository.read_control_state(),
                    report_dir=report_dir,
                    release_manifest=args.release_manifest,
                    expected_head=args.expected_head,
                )
        finally:
            engine.dispose()
    else:
        if not args.allow_local_file_diagnostic:
            print(
                "ERROR: PG_DATABASE_URL is required for DB-backed Goal Status; "
                "use --allow-local-file-diagnostic only for explicit local diagnostics",
                file=sys.stderr,
            )
            return 2
        artifact = build_goal_status_artifact(
            report_dir=report_dir,
            release_manifest=args.release_manifest,
            expected_head=args.expected_head,
            candidate_pool_json=args.candidate_pool_json,
        )
    _write_json(output_json, artifact)
    if args.json:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    return (
        0
        if artifact["status"] not in {"hard_safety_stop", "deployment_issue"}
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
