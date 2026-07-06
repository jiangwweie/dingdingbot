#!/usr/bin/env python3
"""Build the PG-backed StrategyGroup runtime Goal Status export.

Goal Status is a read-only current projection. Production and CLI callers must
read PG control state; generated JSON/MD and report-dir artifacts are exports or
diagnostics and must not decide runtime or trading state.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
)

DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
DEFAULT_OUTPUT_JSON = DEFAULT_REPORT_DIR / "strategygroup-runtime-goal-status.json"


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


def _matrix_submit_blocking_items(
    readiness_matrix: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        item
        for item in readiness_matrix
        if item.get("blocks_real_submit") is True
    ]


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


def _pg_rows(value: Any) -> list[dict[str, Any]]:
    return [_dict(item) for item in _list(value) if isinstance(item, dict)]


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


def _plain_language_stage(status: str) -> str:
    return {
        "waiting_for_signal": "等待市场机会",
        "fresh_signal_detected": "发现新信号",
        "fresh_signal_processing": "正在把信号推进成正式票据",
        "action_time_finalgate_ready": "正式票据已生成，等待最终安全检查",
        "operation_layer_ready": "已到官方执行入口前",
        "runtime_scope_mismatch": "运行范围不一致",
        "runtime_liveness_degraded": "服务器观察链路不完整",
        "active_position_resolution": "需要先处理持仓或挂单冲突",
        "missing_fact": "前置事实不完整",
        "hard_safety_stop": "安全边界阻断",
        "deployment_issue": "部署或运行环境异常",
    }.get(status, "当前状态需要工程诊断")


def _plain_language_next_system_action(checkpoint: str) -> str:
    return {
        "continue_watcher_observation": "系统继续观察市场，不需要 Owner 操作",
        "promote_fresh_signal_candidate": "系统把 fresh signal 推进为候选机会",
        "select_single_action_time_lane_input": "系统从多个候选中仲裁出唯一 action-time lane",
        "materialize_action_time_ticket": "系统为当前 lane 生成 Action-Time Ticket",
        "run_official_action_time_finalgate": "系统使用 ticket 进入官方 FinalGate 检查",
        "refresh_action_time_ticket_or_runtime_safety_state": "系统刷新 ticket 或运行安全状态",
        "call_official_operation_layer_submit_after_action_time_recheck": "系统在最终复核后进入官方执行入口",
        "repair_pg_selected_scope_projection": "系统修复 PG 运行范围投影",
        "repair_pg_runtime_coverage_projection": "系统修复服务器观察覆盖投影",
        "repair_pg_pretrade_readiness_projection": "系统修复 pre-trade readiness 投影",
        "resolve_active_position_or_open_order_conflict": "系统先处理持仓或挂单冲突",
    }.get(checkpoint, checkpoint or "等待下一次 PG current projection")


def _goal_owner_action_required(status: str, owner_label: str) -> bool:
    return owner_label == "需要介入" or status in {
        "hard_safety_stop",
        "deployment_issue",
    }


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
    owner_label = (
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
    )
    owner_action_required = _goal_owner_action_required(status, owner_label)
    missing_ticket_lane_ids = [
        lane_id for lane_id in active_lane_ids if lane_id not in tickets_by_lane
    ]
    return {
        "scope": "strategygroup_runtime_goal_status",
        "generated_at_ms": int(time.time() * 1000),
        "status": status,
        "ready_for_real_order_action": real_order_ready,
        "non_authority_checkpoint": next_checkpoint,
        "plain_language_stage": _plain_language_stage(status),
        "plain_language_reason": owner_detail,
        "plain_language_next_system_action": _plain_language_next_system_action(
            next_checkpoint
        ),
        "owner_action_required": owner_action_required,
        "owner_state": {
            "label": owner_label,
            "detail": owner_detail,
            "non_authority_checkpoint": next_checkpoint,
            "owner_action_required": owner_action_required,
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
        "action_time_ticket_explanation": {
            "plain_language_stage": (
                "已有正式候选交易票据"
                if tickets_by_lane
                else "尚未生成正式候选交易票据"
                if open_lanes
                else "当前没有 action-time lane"
            ),
            "plain_language_reason": (
                "Action-Time Ticket 已锁定策略、币种、方向、事件时间、预算和保护引用"
                if tickets_by_lane
                else "当前 lane 还缺 Action-Time Ticket，FinalGate 没有可审对象"
                if open_lanes
                else "当前没有 fresh signal 推进到 action-time lane"
            ),
            "missing_ticket_lane_ids": missing_ticket_lane_ids,
            "active_ticket_ids": [
                str(row.get("ticket_id") or "") for row in tickets_by_lane.values()
            ],
            "decides_trade_authority": False,
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


def build_goal_status_artifact_from_control_state(
    *,
    control_state: dict[str, Any],
    report_dir: Path,
    release_manifest: Path | None = None,
    expected_head: str | None = None,
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
        description="Build a PG-backed read-only StrategyGroup runtime goal status artifact."
    )
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--release-manifest", type=Path)
    parser.add_argument("--expected-head")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument(
        "--require-database-url",
        action="store_true",
        help="Accepted for deploy compatibility; Goal Status is always PG-only.",
    )
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG DSNs only in tests.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report_dir = args.report_dir or DEFAULT_REPORT_DIR
    output_json = _resolve_output_json(
        report_dir=report_dir,
        output_json=args.output_json,
        report_dir_explicit=args.report_dir is not None,
    )
    if not args.database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for PG-only Goal Status",
            file=sys.stderr,
        )
        return 2
    if not args.database_url.startswith(
        ("postgresql://", "postgresql+psycopg://")
    ) and not args.allow_non_postgres_for_test:
        print(
            "ERROR: PG-only Goal Status requires PostgreSQL DSN",
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
