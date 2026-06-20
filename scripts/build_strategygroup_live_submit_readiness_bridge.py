#!/usr/bin/env python3
"""Build the P0 live-submit readiness bridge packet.

The bridge turns local pre-live rehearsal readiness into a runtime/monitor
consumable standby state. It does not call FinalGate, Operation Layer, exchange
APIs, submit endpoints, or create real-order authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRE_LIVE_READINESS_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-pre-live-rehearsal-readiness-current.json"
)
DEFAULT_DAILY_CHECK_JSON = REPO_ROOT / "output/runtime-monitor/latest-daily-check.json"
DEFAULT_LIVE_CUTOVER_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-live-cutover-readiness.json"
)
DEFAULT_GOAL_PROGRESS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-goal-progress.json"
)
DEFAULT_COMPLETION_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-p0-live-order-closure-completion-audit.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-live-submit-readiness-bridge.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-live-submit-readiness-bridge.md"
)

ACTION_TIME_FACTS = [
    {
        "key": "account_facts",
        "question": "account facts freshness",
        "ready_status": "ready",
        "stale_status": "stale",
        "missing_status": "missing",
    },
    {
        "key": "position_open_order_conflict",
        "question": "position and open-order conflict",
        "ready_status": "clear",
        "stale_status": "stale",
        "missing_status": "missing",
    },
    {
        "key": "budget_coverage",
        "question": "budget coverage",
        "ready_status": "sufficient",
        "stale_status": "stale",
        "missing_status": "insufficient",
    },
    {
        "key": "protection_template",
        "question": "protection template",
        "ready_status": "ready",
        "stale_status": "stale",
        "missing_status": "missing",
    },
    {
        "key": "exchange_rules",
        "question": "exchange rule check",
        "ready_status": "pass",
        "stale_status": "stale",
        "missing_status": "fail",
    },
    {
        "key": "signal_freshness",
        "question": "signal freshness",
        "ready_status": "fresh",
        "stale_status": "expired",
        "missing_status": "waiting",
    },
]

FORBIDDEN_TRUE_PATHS = [
    ("interaction", "mutates_remote_files"),
    ("interaction", "approaches_real_order"),
    ("interaction", "calls_finalgate"),
    ("interaction", "calls_operation_layer"),
    ("interaction", "calls_exchange_write"),
    ("interaction", "places_order"),
    ("decision", "actionable_now"),
    ("decision", "real_order_authority"),
    ("safety_invariants", "actionable_now"),
    ("safety_invariants", "real_order_authority"),
    ("safety_invariants", "final_gate_called"),
    ("safety_invariants", "operation_layer_called"),
    ("safety_invariants", "exchange_write_called"),
    ("safety_invariants", "order_created"),
    ("safety_invariants", "live_profile_changed"),
    ("safety_invariants", "order_sizing_defaults_changed"),
    ("safety_invariants", "withdrawal_or_transfer_created"),
]


def build_live_submit_readiness_bridge(
    *,
    pre_live_readiness: dict[str, Any],
    daily_check: dict[str, Any],
    live_cutover: dict[str, Any],
    goal_progress: dict[str, Any],
    completion_audit: dict[str, Any],
    fact_sources: dict[str, Any] | None = None,
    signal_status_override: str | None = None,
) -> dict[str, Any]:
    fact_sources = fact_sources or {}
    fresh_signal_state = _fresh_signal_state(
        daily_check=daily_check,
        live_cutover=live_cutover,
        goal_progress=goal_progress,
        signal_status_override=signal_status_override,
    )
    action_time_check_active = fresh_signal_state in {"fresh", "processing"}
    matrix = _action_time_required_facts_matrix(
        fact_sources=fact_sources,
        fresh_signal_state=fresh_signal_state,
        action_time_check_active=action_time_check_active,
    )
    hard_fact_blockers = [
        row["blocker"]
        for row in matrix
        if row["blocks_live_submit_now"] is True and row.get("blocker")
    ]
    pre_live_ready = (
        pre_live_readiness.get("status") == "pre_live_rehearsal_ready"
        and _as_dict(pre_live_readiness.get("decision")).get(
            "pre_live_rehearsal_ready"
        )
        is True
    )
    status = _bridge_status(
        pre_live_ready=pre_live_ready,
        fresh_signal_state=fresh_signal_state,
        hard_fact_blockers=hard_fact_blockers,
        completion_status=str(completion_audit.get("status") or ""),
    )
    owner_state = _owner_state_for_status(status, hard_fact_blockers)
    ready_for_finalgate_checkpoint = (
        status == "processing_ready_for_finalgate_checkpoint"
        and not hard_fact_blockers
    )
    live_submit_ready = False
    packet = {
        "schema": "brc.strategygroup_live_submit_readiness_bridge.v1",
        "scope": "p0_live_submit_readiness_bridge",
        "status": status,
        "source_status": {
            "pre_live_rehearsal_readiness": pre_live_readiness.get("status"),
            "daily_check": daily_check.get("status"),
            "live_cutover": live_cutover.get("status"),
            "goal_progress": goal_progress.get("status"),
            "completion_audit": completion_audit.get("status"),
        },
        "runtime_consumption": {
            "standard_local_monitor_sequence_step": True,
            "tokyo_runtime_can_consume_after_deploy": True,
            "artifact_path": "output/runtime-monitor/latest-live-submit-readiness-bridge.json",
            "pre_live_rehearsal_ready_visible": pre_live_ready,
            "live_submit_ready_false_reason": (
                "no_fresh_signal"
                if fresh_signal_state == "none"
                else "action_time_required_facts_not_ready"
                if hard_fact_blockers
                else "awaiting_finalgate_and_operation_layer"
            ),
            "blockers_empty_when_waiting_for_market": (
                fresh_signal_state != "none" or not hard_fact_blockers
            ),
        },
        "fresh_signal_transition": {
            "current_checkpoint": _current_checkpoint(fresh_signal_state),
            "current_state": "waiting_for_market"
            if fresh_signal_state == "none"
            else "processing",
            "next_chain": [
                "RequiredFacts",
                "candidate/auth",
                "FinalGate",
                "Operation Layer",
            ],
            "p05_work_preempted_on_fresh_signal": fresh_signal_state
            in {"fresh", "processing"},
            "owner_manual_packet_read_required": False,
        },
        "action_time_required_facts_matrix": matrix,
        "operation_layer_input_boundary": _operation_layer_input_boundary(),
        "owner_state": owner_state,
        "checks": {
            "blockers": [] if status == "live_submit_standby_waiting_for_market" else hard_fact_blockers,
            "hard_fact_blockers": hard_fact_blockers,
            "pre_live_rehearsal_ready": pre_live_ready,
            "ready_for_finalgate_checkpoint": ready_for_finalgate_checkpoint,
            "live_submit_ready": live_submit_ready,
            "owner_intervention_required": owner_state["owner_intervention_required"],
            "fresh_signal_state": fresh_signal_state,
        },
        "decision": {
            "pre_live_rehearsal_ready": pre_live_ready,
            "live_submit_standby_ready": status
            in {
                "live_submit_standby_waiting_for_market",
                "processing_collecting_action_time_required_facts",
                "processing_ready_for_finalgate_checkpoint",
            },
            "ready_for_finalgate_checkpoint": ready_for_finalgate_checkpoint,
            "live_submit_ready": live_submit_ready,
            "live_submit_ready_false_reason": (
                "no_fresh_signal"
                if fresh_signal_state == "none"
                else "action_time_required_facts_not_ready"
                if hard_fact_blockers
                else "awaiting_finalgate_and_operation_layer"
            ),
            "actionable_now": False,
            "real_order_authority": False,
            "default_next_step": _default_next_step(status),
        },
        "interaction": {
            "level": "L0_local_live_submit_readiness_bridge",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "safety_invariants": {
            "local_bridge_only": True,
            "actionable_now": False,
            "real_order_authority": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_defaults_changed": False,
            "withdrawal_or_transfer_created": False,
        },
    }
    packet["validation_errors"] = validate_packet(packet)
    if packet["validation_errors"]:
        packet["status"] = "live_submit_readiness_bridge_failed"
    return packet


def validate_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if packet.get("schema") != "brc.strategygroup_live_submit_readiness_bridge.v1":
        errors.append("schema_mismatch")
    for section, key in FORBIDDEN_TRUE_PATHS:
        if _as_dict(packet.get(section)).get(key) is True:
            errors.append(f"forbidden_true:{section}.{key}")
    decision = _as_dict(packet.get("decision"))
    if decision.get("pre_live_rehearsal_ready") is not True:
        errors.append("pre_live_rehearsal_not_ready")
    checks = _as_dict(packet.get("checks"))
    if decision.get("live_submit_ready") is True:
        errors.append("live_submit_ready_requires_official_chain")
    if checks.get("live_submit_ready") is True:
        errors.append("checks_live_submit_ready_requires_official_chain")
    matrix = _dict_rows(packet.get("action_time_required_facts_matrix"))
    matrix_keys = [str(row.get("key") or "") for row in matrix]
    expected_keys = [row["key"] for row in ACTION_TIME_FACTS]
    if matrix_keys != expected_keys:
        errors.append(f"required_facts_matrix_mismatch:{matrix_keys}")
    operation_boundary = _as_dict(packet.get("operation_layer_input_boundary"))
    for key in (
        "input_shape_ready",
        "protection_params_shape_ready",
        "budget_context_shape_ready",
        "idempotency_key_shape_ready",
        "recovery_path_shape_ready",
    ):
        if operation_boundary.get(key) is not True:
            errors.append(f"operation_layer_boundary_not_ready:{key}")
    for key in (
        "finalgate_pass_required_before_submit",
        "live_submit_still_gated",
        "real_order_authority",
        "places_order",
        "calls_operation_layer",
    ):
        expected = False if key in {"real_order_authority", "places_order", "calls_operation_layer"} else True
        if operation_boundary.get(key) is not expected:
            errors.append(f"operation_layer_boundary_bad:{key}")
    owner_state = _as_dict(packet.get("owner_state"))
    if owner_state.get("owner_manual_packet_read_required") is not False:
        errors.append("owner_manual_packet_read_required")
    if packet.get("status") == "live_submit_standby_waiting_for_market":
        runtime = _as_dict(packet.get("runtime_consumption"))
        if checks.get("blockers") != []:
            errors.append("waiting_for_market_blockers_not_empty")
        if checks.get("owner_intervention_required") is not False:
            errors.append("waiting_for_market_owner_intervention")
        if runtime.get("live_submit_ready_false_reason") != "no_fresh_signal":
            errors.append("waiting_for_market_false_reason_not_no_fresh_signal")
    return errors


def _fresh_signal_state(
    *,
    daily_check: dict[str, Any],
    live_cutover: dict[str, Any],
    goal_progress: dict[str, Any],
    signal_status_override: str | None,
) -> str:
    if signal_status_override:
        return signal_status_override
    statuses = {
        str(daily_check.get("status") or ""),
        str(live_cutover.get("status") or ""),
        str(goal_progress.get("status") or ""),
    }
    if any("fresh_signal" in status and "waiting" not in status for status in statuses):
        return "fresh"
    if "processing" in statuses:
        return "processing"
    return "none"


def _action_time_required_facts_matrix(
    *,
    fact_sources: dict[str, Any],
    fresh_signal_state: str,
    action_time_check_active: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in ACTION_TIME_FACTS:
        key = spec["key"]
        source = _as_dict(fact_sources.get(key))
        if key == "signal_freshness":
            raw_status = (
                "fresh"
                if fresh_signal_state in {"fresh", "processing"}
                else "expired"
                if fresh_signal_state == "expired"
                else "missing"
            )
        else:
            raw_status = str(source.get("status") or "pending_action_time")
        status = _fact_status(spec, raw_status, action_time_check_active)
        blocks = action_time_check_active and status not in {
            spec["ready_status"],
            "fresh",
            "clear",
            "sufficient",
            "pass",
        }
        rows.append(
            {
                "key": key,
                "question": spec["question"],
                "status": status,
                "source_status": raw_status,
                "check_surface": "live_submit",
                "action_time_check_active": action_time_check_active,
                "blocks_live_submit_now": blocks,
                "blocker": f"{key}:{status}" if blocks else None,
                "owner_wording": _owner_wording_for_fact(key, status),
            }
        )
    return rows


def _fact_status(
    spec: dict[str, str],
    raw_status: str,
    action_time_check_active: bool,
) -> str:
    if not action_time_check_active and raw_status == "pending_action_time":
        return "pending_action_time"
    if raw_status in {"ready", "fresh", "available", "present", "pass", "clear", "sufficient"}:
        return spec["ready_status"]
    if raw_status in {"stale", "expired"}:
        return spec["stale_status"]
    if raw_status in {"conflict", "insufficient", "fail", "missing"}:
        return spec["missing_status"]
    return raw_status


def _operation_layer_input_boundary() -> dict[str, Any]:
    return {
        "input_shape_ready": True,
        "required_fields": [
            "strategy_group_id",
            "runtime_profile_id",
            "subaccount_boundary",
            "symbol",
            "side",
            "notional_or_quantity",
            "leverage",
            "protection_params",
            "budget_context",
            "submit_idempotency_key",
            "recovery_path",
            "authorization_evidence_ids",
        ],
        "protection_params_shape_ready": True,
        "budget_context_shape_ready": True,
        "idempotency_key_shape_ready": True,
        "recovery_path_shape_ready": True,
        "finalgate_pass_required_before_submit": True,
        "live_submit_still_gated": True,
        "real_order_authority": False,
        "places_order": False,
        "calls_operation_layer": False,
    }


def _bridge_status(
    *,
    pre_live_ready: bool,
    fresh_signal_state: str,
    hard_fact_blockers: list[str],
    completion_status: str,
) -> str:
    if completion_status in {"complete", "completed"}:
        return "post_submit_settled"
    if not pre_live_ready:
        return "pre_live_rehearsal_not_ready"
    if fresh_signal_state == "none":
        return "live_submit_standby_waiting_for_market"
    if hard_fact_blockers:
        return "processing_action_time_facts_blocked"
    return "processing_ready_for_finalgate_checkpoint"


def _owner_state_for_status(
    status: str, hard_fact_blockers: list[str]
) -> dict[str, Any]:
    if status == "live_submit_standby_waiting_for_market":
        return {
            "owner_status": "waiting_for_opportunity",
            "owner_label": "等待机会",
            "automation_summary": "系统待命中",
            "intervention": "无需操作",
            "reason": "没有新的可用市场信号",
            "owner_intervention_required": False,
            "owner_manual_packet_read_required": False,
        }
    if status == "processing_ready_for_finalgate_checkpoint":
        return {
            "owner_status": "processing",
            "owner_label": "处理中",
            "automation_summary": "系统自动处理中",
            "intervention": "无需操作",
            "reason": "信号与事实检查已进入实盘链路前置阶段",
            "owner_intervention_required": False,
            "owner_manual_packet_read_required": False,
        }
    if status == "processing_action_time_facts_blocked":
        return {
            "owner_status": "temporarily_unavailable",
            "owner_label": "暂不可用",
            "automation_summary": "事实不可用",
            "intervention": "无需操作",
            "reason": ",".join(hard_fact_blockers),
            "owner_intervention_required": False,
            "owner_manual_packet_read_required": False,
        }
    if status == "post_submit_settled":
        return {
            "owner_status": "completed",
            "owner_label": "已完成",
            "automation_summary": "等待复盘",
            "intervention": "无需操作",
            "reason": "订单闭环已完成",
            "owner_intervention_required": False,
            "owner_manual_packet_read_required": False,
        }
    return {
        "owner_status": "needs_intervention",
        "owner_label": "需要介入",
        "automation_summary": "阶段状态需要处理",
        "intervention": "需要介入",
        "reason": status,
        "owner_intervention_required": True,
        "owner_manual_packet_read_required": False,
    }


def _current_checkpoint(fresh_signal_state: str) -> str:
    if fresh_signal_state == "none":
        return "waiting_for_market"
    return "action_time_required_facts"


def _default_next_step(status: str) -> str:
    if status == "live_submit_standby_waiting_for_market":
        return "continue_watcher_observation_until_fresh_signal"
    if status == "processing_ready_for_finalgate_checkpoint":
        return "run_action_time_finalgate_after_required_facts"
    if status == "processing_action_time_facts_blocked":
        return "refresh_or_repair_missing_action_time_facts"
    if status == "post_submit_settled":
        return "record_review_ledger_outcome"
    return "repair_live_submit_readiness_bridge_inputs"


def _owner_wording_for_fact(key: str, status: str) -> str:
    if status in {"pending_action_time", "waiting"}:
        return "等待机会"
    if status in {"ready", "fresh", "clear", "sufficient", "pass"}:
        return "正常"
    if key in {"account_facts", "signal_freshness"}:
        return "事实不可用"
    if key == "position_open_order_conflict":
        return "订单或持仓冲突"
    if key == "budget_coverage":
        return "预算不足"
    if key == "protection_template":
        return "保护未就绪"
    return "暂不可用"


def build_markdown(packet: dict[str, Any]) -> str:
    owner = _as_dict(packet.get("owner_state"))
    checks = _as_dict(packet.get("checks"))
    return "\n".join(
        [
            "## P0 Live Submit Readiness Bridge",
            "",
            f"- Status: `{packet.get('status')}`",
            f"- Owner status: `{owner.get('owner_status')}` / {owner.get('owner_label')}",
            f"- Pre-live rehearsal ready: `{checks.get('pre_live_rehearsal_ready')}`",
            f"- Live submit ready: `{checks.get('live_submit_ready')}`",
            f"- Owner intervention: `{checks.get('owner_intervention_required')}`",
            "- Real order authority: `false`",
            "",
            "## Action-Time RequiredFacts",
            "",
            _facts_table(_dict_rows(packet.get("action_time_required_facts_matrix"))),
            "",
            "## Operation Layer Boundary",
            "",
            "- Input shape ready: `true`",
            "- FinalGate pass required before submit: `true`",
            "- Live submit still gated: `true`",
            "- Operation Layer called: `false`",
        ]
    ).rstrip() + "\n"


def _facts_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Fact | Status | Blocks live submit now | Owner wording |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| `{}` | `{}` | `{}` | {} |".format(
                row.get("key"),
                row.get("status"),
                row.get("blocks_live_submit_now"),
                row.get("owner_wording"),
            )
        )
    return "\n".join(lines)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pre-live-readiness-json", default=str(DEFAULT_PRE_LIVE_READINESS_JSON)
    )
    parser.add_argument("--daily-check-json", default=str(DEFAULT_DAILY_CHECK_JSON))
    parser.add_argument("--live-cutover-json", default=str(DEFAULT_LIVE_CUTOVER_JSON))
    parser.add_argument("--goal-progress-json", default=str(DEFAULT_GOAL_PROGRESS_JSON))
    parser.add_argument(
        "--completion-audit-json", default=str(DEFAULT_COMPLETION_AUDIT_JSON)
    )
    parser.add_argument("--fact-sources-json")
    parser.add_argument(
        "--signal-status",
        choices=["none", "fresh", "processing", "expired"],
        help="Test/fixture override. Defaults to source packet inference.",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        packet = _load_json(Path(args.output_json).expanduser())
        errors = validate_packet(packet)
        result = {
            "status": "passed" if not errors else "failed",
            "error_count": len(errors),
            "errors": errors,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not errors else 2

    packet = build_live_submit_readiness_bridge(
        pre_live_readiness=_load_json(Path(args.pre_live_readiness_json).expanduser()),
        daily_check=_load_json(Path(args.daily_check_json).expanduser()),
        live_cutover=_load_json(Path(args.live_cutover_json).expanduser()),
        goal_progress=_load_json(Path(args.goal_progress_json).expanduser()),
        completion_audit=_load_json(Path(args.completion_audit_json).expanduser()),
        fact_sources=_load_json(Path(args.fact_sources_json).expanduser())
        if args.fact_sources_json
        else None,
        signal_status_override=args.signal_status,
    )
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    _write_text(Path(args.output_json).expanduser(), payload + "\n")
    _write_text(Path(args.output_owner_progress).expanduser(), build_markdown(packet))
    print(payload)
    return 0 if packet["status"] != "live_submit_readiness_bridge_failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
