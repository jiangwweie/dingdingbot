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
from pathlib import Path
import time
from typing import Any


DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
DEFAULT_OUTPUT_JSON = DEFAULT_REPORT_DIR / "strategygroup-runtime-goal-status.json"

PACKET_FILES = {
    "latest_summary": "latest-summary.json",
    "post_signal_resume": "post-signal-resume-pack.json",
    "resume_dispatch": "resume-dispatch-packet.json",
    "runtime_dry_run_audit": "runtime-dry-run-audit-chain.json",
    "source_readiness": "owner-console-source-readiness.json",
    "pilot_status": "strategygroup-runtime-pilot-status.json",
    "live_facts_readiness": "strategy-group-live-facts-readiness.json",
}

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

FRESH_SIGNAL_STATUSES = {
    "ready_for_non_executing_prepare",
    "ready_for_fresh_submit_authorization",
    "waiting_for_fresh_authorization",
    "ready_for_action_time_final_gate",
    "finalgate_ready",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


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


def _blocker_class(packet: dict[str, Any] | None) -> str:
    data = _data(packet)
    owner_state = _dict(data.get("owner_state"))
    return str(data.get("blocker_class") or owner_state.get("blocker_class") or "").strip()


def _ready_runtime_signal_count(packet: dict[str, Any] | None) -> int:
    data = _data(packet)
    value = data.get("ready_runtime_signals")
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


def _release_head(release_manifest: dict[str, Any] | None) -> str | None:
    data = _dict(release_manifest)
    local_git = _dict(data.get("local_git"))
    return str(local_git.get("head") or data.get("head") or "").strip() or None


def _source_owner_summary(packet: dict[str, Any] | None) -> dict[str, Any]:
    data = _data(packet)
    return _dict(data.get("owner_summary"))


def _has_fresh_signal(packets: dict[str, dict[str, Any] | None]) -> bool:
    if any(
        _ready_runtime_signal_count(packets.get(name)) > 0
        for name in ("latest_summary", "post_signal_resume", "resume_dispatch")
    ):
        return True
    statuses = {
        _status(packets.get("latest_summary")),
        _status(packets.get("post_signal_resume")),
        _status(packets.get("resume_dispatch")),
        _dispatch_status(packets.get("resume_dispatch")),
    }
    return bool(statuses & FRESH_SIGNAL_STATUSES)


def _current_status(
    *,
    checks: dict[str, bool],
    packets: dict[str, dict[str, Any] | None],
    dangerous_effects: list[str],
    deployment_blockers: list[str],
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
            "align_tokyo_deployment_before_runtime_action",
            "Tokyo 部署与目标 commit 不一致",
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

    dispatch_status = _dispatch_status(packets.get("resume_dispatch"))
    resume_status = _status(packets.get("resume_dispatch")) or _status(
        packets.get("post_signal_resume")
    )

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
    } or resume_status == "ready_for_action_time_final_gate":
        return (
            "action_time_finalgate_ready",
            "run_official_action_time_finalgate",
            "fresh signal 已进入 action-time FinalGate 检查点",
            False,
        )
    if resume_status in {
        "ready_for_non_executing_prepare",
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
        key: _read_json(report_dir / filename)
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
    source = _data(packets["source_readiness"])
    live_facts = _data(packets["live_facts_readiness"])
    dangerous = _dangerous_effects(*packets.values())
    missing_packets = [
        key for key, value in packets.items() if value is None
    ]

    checks = {
        "required_packets_present": all(value is not None for value in packets.values()),
        "deployment_aligned": not deployment_blockers,
        "runtime_dry_run_audit_passed": (
            dry_run.get("status") == "passed"
            and dry_run_checks.get("dangerous_effects_absent") is True
        ),
        "source_readiness_ready": source.get("status") == "ready",
        "live_facts_ready": str(live_facts.get("status") or "").startswith(
            "strategy_group_live_facts_ready"
        ),
        "dangerous_effects_absent": not dangerous,
        "fresh_signal_present": _has_fresh_signal(packets),
    }
    status, next_checkpoint, owner_detail, real_order_ready = _current_status(
        checks=checks,
        packets=packets,
        dangerous_effects=dangerous,
        deployment_blockers=deployment_blockers,
    )

    source_summary = _source_owner_summary(packets["source_readiness"])
    blockers = [
        *deployment_blockers,
        *[f"missing_packet:{key}" for key in missing_packets],
        *([] if checks["runtime_dry_run_audit_passed"] else ["runtime_dry_run_audit_not_passed"]),
        *([] if checks["source_readiness_ready"] else ["source_readiness_not_ready"]),
        *([] if checks["live_facts_ready"] else ["live_facts_not_ready"]),
        *([] if checks["dangerous_effects_absent"] else ["dangerous_effects_present"]),
    ]
    return {
        "scope": "strategygroup_runtime_goal_status",
        "generated_at_ms": int(time.time() * 1000),
        "status": status,
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
            "latest_summary_status": _status(packets["latest_summary"]),
            "post_signal_resume_status": _status(packets["post_signal_resume"]),
            "resume_dispatch_status": _status(packets["resume_dispatch"]),
            "resume_dispatch_action": _data(packets["resume_dispatch"]).get(
                "dispatch_action"
            ),
            "source_owner_summary": source_summary,
            "dry_run_scenario_count": dry_run_checks.get("scenario_count"),
        },
        "real_order_boundary": {
            "ready_for_real_order_action": real_order_ready,
            "requires_selected_strategygroup": True,
            "requires_tiny_risk": True,
            "requires_fresh_signal": True,
            "requires_required_facts": True,
            "requires_candidate_grant_authorization": True,
            "requires_action_time_finalgate": True,
            "requires_official_operation_layer": True,
        },
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
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--release-manifest", type=Path)
    parser.add_argument("--expected-head")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    packet = build_goal_status_packet(
        report_dir=args.report_dir,
        release_manifest=args.release_manifest,
        expected_head=args.expected_head,
    )
    _write_json(args.output_json, packet)
    if args.json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] not in {"hard_safety_stop", "deployment_issue"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
