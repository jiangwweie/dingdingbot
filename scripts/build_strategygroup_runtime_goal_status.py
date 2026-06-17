#!/usr/bin/env python3
"""Build a read-only StrategyGroup runtime goal status packet.

This packet is for the main control goal loop. It summarizes current watcher,
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
import time
from typing import Any


DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
DEFAULT_OUTPUT_JSON = DEFAULT_REPORT_DIR / "strategygroup-runtime-goal-status.json"

PACKET_FILES = {
    "watcher_tick": "watcher-tick.json",
    "latest_summary": "latest-summary.json",
    "wakeup": "wakeup-packet.json",
    "post_signal_resume": "post-signal-resume-pack.json",
    "resume_dispatch": "resume-dispatch-packet.json",
    "runtime_dry_run_audit": "runtime-dry-run-audit-chain.json",
    "source_readiness": "owner-console-source-readiness.json",
    "pilot_status": "strategygroup-runtime-pilot-status.json",
    "live_facts_readiness": "strategy-group-live-facts-readiness.json",
}
PACKET_FILE_FALLBACKS = {
    "runtime_dry_run_audit": (
        "dry-run-audit-chain/runtime-dry-run-audit-chain.json",
    ),
}
OPTIONAL_PACKET_KEYS = {"wakeup"}

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
    "scoped_pipeline_operation_layer_handoff_checked",
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
    "operation_layer_submit_result_identity_guard_checked",
    "post_submit_finalize_result_identity_guard_checked",
    "shared_runtime_pipeline_checked",
    "common_execution_chain_reuse_checked",
    "strategygroup_adapter_boundary_checked",
    "strategy_handoff_no_execution_pipeline_fields_checked",
    "runtime_tier_policy_checked",
    "only_mpg_tiny_real_order_eligible_checked",
    "new_strategygroups_default_observe_only_checked",
    "selected_strategygroup_dispatch_guard_checked",
    "all_selected_strategygroups_reach_finalgate_dispatch_checked",
    "non_executing_prepare_auto_bridge_checked",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _read_packet(report_dir: Path, key: str, filename: str) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    primary = _read_json(report_dir / filename)
    if primary is not None:
        candidates.append(primary)
    for fallback in PACKET_FILE_FALLBACKS.get(key, ()):
        packet = _read_json(report_dir / fallback)
        if packet is not None:
            candidates.append(packet)
    if not candidates:
        return None
    if key == "runtime_dry_run_audit":
        return max(candidates, key=_runtime_dry_run_packet_score)
    return candidates[0]


def _runtime_dry_run_packet_score(packet: dict[str, Any]) -> tuple[int, int, int, int]:
    data = packet.get("data") if isinstance(packet.get("data"), dict) else packet
    checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
    passed_required = sum(
        1 for name in REQUIRED_DRY_RUN_CHECKS if checks.get(name) is True
    )
    scenario_count = checks.get("scenario_count")
    if not isinstance(scenario_count, int):
        scenario_count = data.get("scenario_count")
    if not isinstance(scenario_count, int):
        scenario_count = 0
    generated_at_ms = data.get("generated_at_ms")
    if not isinstance(generated_at_ms, int):
        generated_at_ms = 0
    return (
        1 if data.get("status") == "passed" else 0,
        passed_required,
        scenario_count,
        generated_at_ms,
    )


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


def _data(packet: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return {}
    nested = packet.get("data")
    return nested if isinstance(nested, dict) else packet


def _status(packet: dict[str, Any] | None) -> str:
    return str(_data(packet).get("status") or "").strip()


def _dispatch_status(packet: dict[str, Any] | None) -> str:
    return str(_data(packet).get("dispatch_status") or "").strip()


def _blockers(packet: dict[str, Any] | None) -> list[str]:
    return [str(item) for item in _list(_data(packet).get("blockers")) if str(item)]


def _non_waiting_blockers(packet: dict[str, Any] | None) -> list[str]:
    blockers: list[str] = []
    for blocker in _blockers(packet):
        text = blocker.lower()
        if any(fragment in text for fragment in WAITING_BLOCKER_FRAGMENTS):
            continue
        blockers.append(blocker)
    return blockers


def _blocker_class(packet: dict[str, Any] | None) -> str:
    data = _data(packet)
    owner_state = _dict(data.get("owner_state"))
    return str(data.get("blocker_class") or owner_state.get("blocker_class") or "").strip()


def _ready_runtime_signal_count(packet: dict[str, Any] | None) -> int:
    data = _data(packet)
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


def _dangerous_effects(*packets: dict[str, Any] | None) -> list[str]:
    findings: list[str] = []
    for index, packet in enumerate(packets):
        _walk_dangerous(packet, f"packet[{index}]", findings)
    return sorted(set(findings))


def _dangerous_scan_packets(
    packets: dict[str, dict[str, Any] | None],
) -> list[dict[str, Any] | None]:
    scan_packets: list[dict[str, Any] | None] = []
    for key, packet in packets.items():
        if key == "runtime_dry_run_audit":
            dry_run = _data(packet)
            checks = _dict(dry_run.get("checks"))
            if (
                dry_run.get("status") == "passed"
                and checks.get("dangerous_effects_absent") is True
            ):
                continue
        scan_packets.append(packet)
    return scan_packets


def _release_head(release_manifest: dict[str, Any] | None) -> str | None:
    data = _dict(release_manifest)
    local_git = _dict(data.get("local_git"))
    return str(local_git.get("head") or data.get("head") or "").strip() or None


def _source_owner_summary(packet: dict[str, Any] | None) -> dict[str, Any]:
    data = _data(packet)
    return _dict(data.get("owner_summary"))


def _source_health_item(
    packet: dict[str, Any] | None,
    key: str,
) -> dict[str, Any]:
    data = _data(packet)
    return _dict(_dict(data.get("source_health")).get(key))


def _source_deploy_channel_blockers(
    packet: dict[str, Any] | None,
) -> list[str]:
    item = _source_health_item(packet, "deploy_channel")
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
    packets: dict[str, dict[str, Any] | None],
    blockers: list[str],
) -> str:
    parts = list(blockers)
    for packet in packets.values():
        parts.extend(_blockers(packet))
    return " ".join(parts).lower()


def _combined_blockers(
    packets: dict[str, dict[str, Any] | None],
    blockers: list[str],
) -> list[str]:
    combined = list(blockers)
    for packet in packets.values():
        combined.extend(_blockers(packet))
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
    packets: dict[str, dict[str, Any] | None],
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
    for blocker in _combined_blockers(packets, blockers):
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
    packets: dict[str, dict[str, Any] | None],
    blockers: list[str],
    dangerous_effects: list[str],
    real_order_ready: bool,
) -> list[dict[str, Any]]:
    blocker_text = _combined_blocker_text(packets, blockers)
    source_summary = _source_owner_summary(packets.get("source_readiness"))
    dispatch_status = _dispatch_status(packets.get("resume_dispatch"))
    resume_status = _status(packets.get("resume_dispatch")) or _status(
        packets.get("post_signal_resume")
    )

    has_active_position_blocker = _has_active_position_or_open_order_conflict(
        packets,
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
            "post-signal-resume-pack.json/resume-dispatch-packet.json",
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
            "resume-dispatch-packet.json",
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
                "symbol / side / notional / leverage 不在 selected tiny boundary 内"
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


def _status_from_submit_blockers(
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
        "selected_strategygroup_scope",
        "symbol_side_notional_leverage_scope",
        "duplicate_submit",
        "hard_safety",
    }:
        return (
            "hard_safety_stop",
            "record_submit_blocker_review_packet",
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


def _has_fresh_signal(packets: dict[str, dict[str, Any] | None]) -> bool:
    if any(
        _ready_runtime_signal_count(packets.get(name)) > 0
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
        _status(packets.get("wakeup")),
        _status(packets.get("latest_summary")),
        _status(packets.get("post_signal_resume")),
        _status(packets.get("resume_dispatch")),
        _status(packets.get("pilot_status")),
        _dispatch_status(packets.get("resume_dispatch")),
    }
    return bool(statuses & FRESH_SIGNAL_STATUSES)


def _selected_runtime_instance_ids(packet: dict[str, Any] | None) -> list[str]:
    return [
        str(item)
        for item in _list(_data(packet).get("selected_runtime_instance_ids"))
        if str(item)
    ]


def _pilot_matched_runtime_instance_ids(packet: dict[str, Any] | None) -> list[str]:
    alignment = _dict(_data(packet).get("watcher_scope_alignment"))
    rows = _list(alignment.get("matched_runtime_signal_summaries"))
    return [
        str(_dict(item).get("runtime_instance_id"))
        for item in rows
        if str(_dict(item).get("runtime_instance_id") or "")
    ]


def _selected_scope_blockers(
    *,
    packets: dict[str, dict[str, Any] | None],
    fresh_signal_present: bool,
) -> list[str]:
    if not fresh_signal_present:
        return []

    pilot = _data(packets.get("pilot_status"))
    alignment = _dict(pilot.get("watcher_scope_alignment"))
    if not alignment:
        return []

    alignment_status = str(alignment.get("status") or "")
    if alignment_status == "mismatch":
        return ["selected_strategygroup_scope_mismatch"]

    matched_ids = set(_pilot_matched_runtime_instance_ids(packets.get("pilot_status")))
    if not matched_ids:
        return ["selected_strategygroup_matched_runtime_ids_missing"]
    if alignment_status == "expanded_scope":
        out_of_scope_rows = _list(alignment.get("out_of_scope_runtime_signal_summaries"))
        actionable_out_of_scope = [
            str(_dict(item).get("runtime_instance_id"))
            for item in out_of_scope_rows
            if str(_dict(item).get("status") or "") in FRESH_SIGNAL_STATUSES
            and str(_dict(item).get("runtime_instance_id") or "")
        ]
        if actionable_out_of_scope:
            return [
                f"fresh_signal_outside_selected_strategygroup_scope:{runtime_id}"
                for runtime_id in sorted(set(actionable_out_of_scope))
            ]
        return []

    candidate_ids = (
        _selected_runtime_instance_ids(packets.get("resume_dispatch"))
        or _selected_runtime_instance_ids(packets.get("post_signal_resume"))
        or _selected_runtime_instance_ids(packets.get("latest_summary"))
    )
    if not candidate_ids:
        return ["fresh_signal_runtime_instance_id_missing"]

    out_of_scope_ids = sorted(set(candidate_ids) - matched_ids)
    if out_of_scope_ids:
        return [
            f"fresh_signal_outside_selected_strategygroup_scope:{runtime_id}"
            for runtime_id in out_of_scope_ids
        ]
    return []


def _watcher_liveness_blockers(
    packets: dict[str, dict[str, Any] | None],
    *,
    fresh_signal_present: bool,
) -> list[str]:
    blockers: list[str] = []
    for name in ("watcher_tick", "latest_summary"):
        packet = packets.get(name)
        status = _status(packet)
        blockers.extend(f"{name}:{item}" for item in _non_waiting_blockers(packet))
        if status and status not in WAITING_STATUSES and status not in FRESH_SIGNAL_STATUSES:
            if status not in {"blocked", "owner_attention_pending"}:
                blockers.append(f"{name}:unexpected_status:{status}")
            elif not _non_waiting_blockers(packet) and not (
                status == "owner_attention_pending" and fresh_signal_present
            ):
                blockers.append(f"{name}:status:{status}")
    return sorted(set(blockers))


def _current_status(
    *,
    checks: dict[str, bool],
    packets: dict[str, dict[str, Any] | None],
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
    dispatch_blocker_class = _blocker_class(packets.get("resume_dispatch"))
    if dispatch_blocker_class == "hard_safety_stop":
        return (
            "hard_safety_stop",
            "stop_and_investigate_hard_safety_stop",
            "官方接力 packet 报告 hard safety stop，禁止继续靠近实盘动作",
            False,
        )
    if deployment_blockers:
        return (
            "deployment_issue",
            "repair_deploy_channel_while_continuing_watcher_observation",
            "部署通道或目标部署状态不可用，watcher 可继续观察，真实提交保持关闭",
            False,
        )
    if not checks["required_packets_present"]:
        return (
            "missing_fact",
            "refresh_required_runtime_packets",
            "主链路状态所需 packet 不完整，先刷新本地/东京只读证据",
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

    dispatch_status = _dispatch_status(packets.get("resume_dispatch"))
    chain_statuses = {
        _status(packets.get("resume_dispatch")),
        _status(packets.get("post_signal_resume")),
        _status(packets.get("pilot_status")),
        _status(packets.get("wakeup")),
    }
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
    if _has_fresh_signal(packets):
        return (
            "fresh_signal_detected",
            "rebuild_resume_dispatch_and_prepare_evidence",
            "watcher 已发现 fresh signal，进入非执行准备链路",
            False,
        )

    latest_status = _status(packets.get("latest_summary"))
    post_status = _status(packets.get("post_signal_resume"))
    if latest_status in WAITING_STATUSES or post_status in WAITING_STATUSES:
        return (
            "waiting_for_signal",
            "continue_watcher_observation",
            "系统健康，当前等待市场机会",
            False,
        )
    return (
        "needs_review",
        "review_runtime_packets",
        "当前 packet 状态无法自动归类",
        False,
    )


def build_goal_status_packet(
    *,
    report_dir: Path,
    release_manifest: Path | None = None,
    expected_head: str | None = None,
) -> dict[str, Any]:
    packets = {
        key: _read_packet(report_dir, key, filename)
        for key, filename in PACKET_FILES.items()
    }
    manifest_packet = _read_json(release_manifest) if release_manifest else None
    deployed_head = _release_head(manifest_packet)
    expected_head = expected_head or deployed_head
    deployment_blockers: list[str] = []
    if expected_head and deployed_head and expected_head != deployed_head:
        deployment_blockers.append("deployed_head_mismatch")
    if expected_head and release_manifest and not deployed_head:
        deployment_blockers.append("deployed_head_unknown")

    dry_run = _data(packets["runtime_dry_run_audit"])
    dry_run_checks = _dict(dry_run.get("checks"))
    dry_run_missing_required_checks = _runtime_dry_run_missing_required_checks(
        dry_run_checks
    )
    source = _data(packets["source_readiness"])
    source_deploy_channel_blockers = _source_deploy_channel_blockers(
        packets["source_readiness"]
    )
    deploy_channel_enforced = release_manifest is not None or expected_head is not None
    if deploy_channel_enforced:
        deployment_blockers.extend(source_deploy_channel_blockers)
    live_facts = _data(packets["live_facts_readiness"])
    dangerous = _dangerous_effects(*_dangerous_scan_packets(packets))
    fresh_signal_present = _has_fresh_signal(packets)
    watcher_liveness = _watcher_liveness_blockers(
        packets,
        fresh_signal_present=fresh_signal_present,
    )
    selected_scope_blockers = _selected_scope_blockers(
        packets=packets,
        fresh_signal_present=fresh_signal_present,
    )
    missing_packets = [
        key
        for key, value in packets.items()
        if value is None and key not in OPTIONAL_PACKET_KEYS
    ]

    dry_run_required_check_status = {
        name: dry_run_checks.get(name) is True
        for name in sorted(REQUIRED_DRY_RUN_CHECKS)
    }

    checks = {
        "required_packets_present": all(
            value is not None
            for key, value in packets.items()
            if key not in OPTIONAL_PACKET_KEYS
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
    status, next_checkpoint, owner_detail, real_order_ready = _current_status(
        checks=checks,
        packets=packets,
        dangerous_effects=dangerous,
        deployment_blockers=deployment_blockers,
        watcher_liveness_blockers=watcher_liveness,
        selected_scope_blockers=selected_scope_blockers,
    )

    source_summary = _source_owner_summary(packets["source_readiness"])
    blockers = [
        *deployment_blockers,
        *[f"missing_packet:{key}" for key in missing_packets],
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
        packets=packets,
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
        status, next_checkpoint, owner_detail = _status_from_submit_blockers(
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
            packets=packets,
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
        "next_safe_checkpoint": next_checkpoint,
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
            "next_safe_checkpoint": next_checkpoint,
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
                packets["source_readiness"],
                "deploy_channel",
            ),
            "latest_summary_status": _status(packets["latest_summary"]),
            "watcher_tick_status": _status(packets["watcher_tick"]),
            "post_signal_resume_status": _status(packets["post_signal_resume"]),
            "resume_dispatch_status": _status(packets["resume_dispatch"]),
            "resume_dispatch_action": _data(packets["resume_dispatch"]).get(
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
                "next_safe_checkpoint": next_checkpoint,
                "blocker_keys": submit_blocker_review_keys,
            },
            "pilot_matched_runtime_instance_ids": _pilot_matched_runtime_instance_ids(
                packets["pilot_status"]
            ),
            "resume_dispatch_selected_runtime_instance_ids": (
                _selected_runtime_instance_ids(packets["resume_dispatch"])
            ),
            "active_runtime_count": _data(packets["latest_summary"]).get(
                "active_runtime_count"
            ),
            "selected_runtime_instance_count": len(
                _list(
                    _data(packets["latest_summary"]).get(
                        "selected_runtime_instance_ids"
                    )
                )
            ),
        },
        "real_order_boundary": {
            "ready_for_real_order_action": real_order_ready,
            "requires_selected_strategygroup": True,
            "selected_strategygroup_scope_ready": not selected_scope_blockers,
            "requires_tiny_risk": True,
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
            "read_only_packet_builder": True,
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a read-only StrategyGroup runtime goal status packet."
    )
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--release-manifest", type=Path)
    parser.add_argument("--expected-head")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report_dir = args.report_dir or DEFAULT_REPORT_DIR
    output_json = _resolve_output_json(
        report_dir=report_dir,
        output_json=args.output_json,
        report_dir_explicit=args.report_dir is not None,
    )
    packet = build_goal_status_packet(
        report_dir=report_dir,
        release_manifest=args.release_manifest,
        expected_head=args.expected_head,
    )
    _write_json(output_json, packet)
    if args.json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] not in {"hard_safety_stop", "deployment_issue"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
