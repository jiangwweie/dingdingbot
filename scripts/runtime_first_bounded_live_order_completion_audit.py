#!/usr/bin/env python3
"""Audit P0 first bounded live order closure completion from local evidence.

This script is deliberately local-only. It does not call Tokyo, FinalGate,
Operation Layer, OrderLifecycle, exchange write paths, or any server mutation.
It turns the live-cutover goal into a small machine-readable matrix:

- what is already proven by non-executing rehearsals;
- what is still market/live-execution dependent;
- whether any non-market evidence gap needs repair before the next signal.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


DEFAULT_DAILY_CHECK_JSON = (
    ROOT_DIR / "output/runtime-monitor/latest-daily-check-cache-only.json"
)
DEFAULT_GOAL_PROGRESS_JSON = ROOT_DIR / "output/runtime-monitor/latest-goal-progress.json"
DEFAULT_DRY_RUN_AUDIT_JSON = (
    ROOT_DIR / "output/runtime-monitor/latest-runtime-dry-run-audit-chain.json"
)
DEFAULT_LIVE_CUTOVER_JSON = (
    ROOT_DIR / "output/runtime-monitor/latest-live-cutover-readiness.json"
)
DEFAULT_OUTPUT_JSON = (
    ROOT_DIR / "output/runtime-monitor/latest-p0-live-order-closure-completion-audit.json"
)
DEFAULT_OWNER_PROGRESS = (
    ROOT_DIR / "output/runtime-monitor/latest-p0-live-order-closure-completion-audit.md"
)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _flag(packet: dict[str, Any], key: str) -> Any:
    checks = _dict(packet.get("checks"))
    if key in checks:
        return checks[key]
    summary = _dict(packet.get("summary"))
    if key in summary:
        return summary[key]
    return None


def _section_status(packet: dict[str, Any], section_name: str) -> Any:
    for section in _list(packet.get("sections")):
        if isinstance(section, dict) and section.get("name") == section_name:
            return section.get("status")
    return None


def _contract_checks(packet: dict[str, Any]) -> dict[str, Any]:
    contract = _dict(packet.get("live_closure_cutover_contract"))
    return _dict(contract.get("checks"))


def _contract_evidence_keys(packet: dict[str, Any]) -> list[str]:
    contract = _dict(packet.get("live_closure_cutover_contract"))
    return [str(item) for item in _list(contract.get("required_evidence_keys"))]


def _completion_boundary(goal_progress: dict[str, Any]) -> dict[str, Any]:
    return _dict(goal_progress.get("completion_boundary"))


def _live_closure_boundary(goal_progress: dict[str, Any]) -> dict[str, Any]:
    return _dict(goal_progress.get("live_closure_evidence_boundary"))


def _proof_missing_or_false(
    proof: dict[str, Any],
    *,
    allowed_false_keys: set[str] | None = None,
) -> list[str]:
    allowed_false_keys = allowed_false_keys or set()
    missing: list[str] = []
    for key, value in proof.items():
        if value is None:
            missing.append(key)
        elif value is False and key not in allowed_false_keys:
            missing.append(key)
    return missing


def _audit_items(
    *,
    daily_check: dict[str, Any],
    goal_progress: dict[str, Any],
    dry_run_audit: dict[str, Any],
    live_cutover: dict[str, Any],
) -> list[dict[str, Any]]:
    evidence_keys = _contract_evidence_keys(live_cutover)
    contract_checks = _contract_checks(live_cutover)
    completion = _completion_boundary(goal_progress)
    live_closure = _live_closure_boundary(goal_progress)
    current_read = _dict(daily_check.get("current_read_interaction"))
    if not current_read:
        current_read = _dict(daily_check.get("interaction"))

    items = [
        {
            "requirement": "selected StrategyGroup and allocated subaccount boundary",
            "evidence_source": "runtime_live_cutover_readiness + runtime_dry_run_audit_chain",
            "status": "ready_non_market",
            "proof": {
                "selected_strategy_group_id": live_cutover.get(
                    "selected_strategy_group_id"
                ),
                "first_live_lane": live_cutover.get("first_live_lane"),
                "strategy_scope_section": _section_status(
                    live_cutover,
                    "strategy_scope",
                ),
                "only_mpg_tiny_real_order_eligible_checked": _flag(
                    dry_run_audit,
                    "only_mpg_tiny_real_order_eligible_checked",
                ),
                "strategygroup_adapter_boundary_checked": _flag(
                    dry_run_audit,
                    "strategygroup_adapter_boundary_checked",
                ),
            },
        },
        {
            "requirement": "fresh signal -> RequiredFacts -> candidate/auth fast chain",
            "evidence_source": "runtime_dry_run_audit_chain + runtime_live_cutover_readiness",
            "status": "ready_non_market_waiting_live_signal",
            "proof": {
                "entry_fast_chain_section": _section_status(
                    live_cutover,
                    "entry_fast_chain",
                ),
                "fresh_signal_fast_auto_chain_checked": _flag(
                    dry_run_audit,
                    "fresh_signal_fast_auto_chain_checked",
                ),
                "required_facts_readiness_checked": _flag(
                    dry_run_audit,
                    "required_facts_readiness_checked",
                ),
                "non_executing_prepare_auto_bridge_checked": _flag(
                    dry_run_audit,
                    "non_executing_prepare_auto_bridge_checked",
                ),
                "selected_strategygroup_dispatch_guard_checked": _flag(
                    dry_run_audit,
                    "selected_strategygroup_dispatch_guard_checked",
                ),
            },
        },
        {
            "requirement": (
                "candidate/auth -> action-time FinalGate -> official Operation "
                "Layer evidence relay"
            ),
            "evidence_source": "runtime_dry_run_audit_chain + runtime_live_cutover_readiness",
            "status": "ready_non_market_waiting_live_finalgate_and_operation_layer",
            "proof": {
                "operation_layer_relay_section": _section_status(
                    live_cutover,
                    "operation_layer_relay",
                ),
                "operation_layer_evidence_relay_checked": _flag(
                    dry_run_audit,
                    "operation_layer_evidence_relay_checked",
                ),
                "scoped_pipeline_operation_layer_handoff_checked": _flag(
                    dry_run_audit,
                    "scoped_pipeline_operation_layer_handoff_checked",
                ),
                "operation_layer_authorization_chain_guard_checked": _flag(
                    dry_run_audit,
                    "operation_layer_authorization_chain_guard_checked",
                ),
            },
        },
        {
            "requirement": "hard blockers classify execution conflicts before real submit",
            "evidence_source": "runtime_dry_run_audit_chain + runtime_live_cutover_readiness",
            "status": "ready_non_market",
            "proof": {
                "hard_blocker_policy_section": _section_status(
                    live_cutover,
                    "hard_blocker_policy",
                ),
                "operation_layer_hard_safety_blocker_matrix_checked": _flag(
                    dry_run_audit,
                    "operation_layer_hard_safety_blocker_matrix_checked",
                ),
                "operation_layer_blocker_review_policy_checked": _flag(
                    dry_run_audit,
                    "operation_layer_blocker_review_policy_checked",
                ),
                "expanded_watcher_scope_execution_guard_checked": _flag(
                    dry_run_audit,
                    "expanded_watcher_scope_execution_guard_checked",
                ),
            },
        },
        {
            "requirement": "real submit must happen only through official Operation Layer",
            "evidence_source": "runtime_live_cutover_readiness",
            "status": "not_complete_market_dependent",
            "proof": {
                "current_real_submit_allowed": live_cutover.get(
                    "current_real_submit_allowed"
                ),
                "current_real_submit_blocker": live_cutover.get(
                    "current_real_submit_blocker"
                ),
                "official_operation_layer_ready_stage_required": (
                    "operation_layer_submit_authorization_id" in evidence_keys
                ),
                "next_fresh_signal_cutover_ready": live_cutover.get(
                    "next_fresh_signal_cutover_ready"
                ),
            },
            "allowed_false_keys": {"current_real_submit_allowed"},
        },
        {
            "requirement": "entry accepted -> exchange-native hard stop/protection/recovery",
            "evidence_source": "runtime_dry_run_audit_chain + runtime_live_cutover_readiness",
            "status": "ready_non_market_waiting_real_exchange_acceptance",
            "proof": {
                "exit_protection_recovery_section": _section_status(
                    live_cutover,
                    "exit_protection_recovery",
                ),
                "post_submit_exit_outcome_matrix_checked": _flag(
                    dry_run_audit,
                    "post_submit_exit_outcome_matrix_checked",
                ),
                "reduce_only_recovery_standing_authorization_checked": _flag(
                    dry_run_audit,
                    "reduce_only_recovery_standing_authorization_checked",
                ),
                "exchange_native_protection_stage_required": (
                    "exchange_native_hard_stop_order_id" in evidence_keys
                ),
            },
        },
        {
            "requirement": (
                "post-submit finalize / reconciliation / budget settlement / "
                "review closure"
            ),
            "evidence_source": (
                "runtime_dry_run_audit_chain + runtime_live_cutover_readiness + "
                "goal_progress"
            ),
            "status": "ready_non_market_waiting_real_submit_outcome",
            "proof": {
                "post_submit_close_loop_section": _section_status(
                    live_cutover,
                    "post_submit_close_loop",
                ),
                "post_submit_closed_loop_evidence_guard_checked": _flag(
                    dry_run_audit,
                    "post_submit_closed_loop_evidence_guard_checked",
                ),
                "post_submit_finalize_result_identity_guard_checked": _flag(
                    dry_run_audit,
                    "post_submit_finalize_result_identity_guard_checked",
                ),
                "live_closure_evidence_boundary_status": live_closure.get("status"),
                "first_bounded_real_order_complete": completion.get(
                    "first_bounded_real_order_complete"
                ),
            },
            "allowed_false_keys": {"first_bounded_real_order_complete"},
        },
        {
            "requirement": (
                "do not use synthetic/replay/disabled smoke as real execution proof"
            ),
            "evidence_source": "runtime_dry_run_audit_chain + runtime_live_cutover_readiness",
            "status": "ready_non_market",
            "proof": {
                "dry_run_safety_section": _section_status(
                    live_cutover,
                    "dry_run_safety",
                ),
                "disabled_smoke_not_real_execution_proof": _flag(
                    dry_run_audit,
                    "disabled_smoke_not_real_execution_proof",
                ),
                "live_closure_contract_rejects_synthetic_signal": contract_checks.get(
                    "live_closure_contract_rejects_synthetic_signal"
                ),
                "live_closure_contract_rejects_disabled_smoke": contract_checks.get(
                    "live_closure_contract_rejects_disabled_smoke"
                ),
            },
        },
        {
            "requirement": (
                "low-noise monitor stays quiet when healthy waiting and wakes on "
                "fresh signal"
            ),
            "evidence_source": "daily_check + goal_progress",
            "status": "ready_non_market",
            "proof": {
                "daily_status": daily_check.get("status"),
                "notification_decision": _dict(daily_check.get("notification")).get(
                    "decision"
                ),
                "fresh_signal_notification_policy_checked": _dict(
                    daily_check.get("checks")
                ).get("fresh_signal_notification_policy_checked"),
                "current_read_interaction_level": current_read.get("level"),
                "current_read_remote_interaction_count": current_read.get(
                    "remote_interaction_count"
                ),
                "goal_interaction_remote_interaction_count": _dict(
                    goal_progress.get("interaction")
                ).get("remote_interaction_count"),
            },
        },
    ]

    for item in items:
        item["missing_or_false_non_market_evidence"] = _proof_missing_or_false(
            _dict(item.get("proof")),
            allowed_false_keys=set(item.get("allowed_false_keys") or []),
        )
        item.pop("allowed_false_keys", None)
    return items


def build_completion_audit_report(
    *,
    daily_check: dict[str, Any],
    goal_progress: dict[str, Any],
    dry_run_audit: dict[str, Any],
    live_cutover: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    items = _audit_items(
        daily_check=daily_check,
        goal_progress=goal_progress,
        dry_run_audit=dry_run_audit,
        live_cutover=live_cutover,
    )
    non_market_gaps = [
        {
            "requirement": item["requirement"],
            "missing_or_false": item["missing_or_false_non_market_evidence"],
        }
        for item in items
        if item["status"].startswith("ready")
        and item["missing_or_false_non_market_evidence"]
    ]
    market_dependent_remaining = [
        item["requirement"]
        for item in items
        if (
            "market_dependent" in item["status"]
            or "waiting_live" in item["status"]
            or item["status"] == "ready_non_market_waiting_real_exchange_acceptance"
            or item["status"] == "ready_non_market_waiting_real_submit_outcome"
        )
    ]
    completion = _completion_boundary(goal_progress)
    goal_complete = (
        completion.get("goal_complete") is True
        and completion.get("first_bounded_real_order_complete") is True
        and completion.get("real_order_closure_proven") is True
    )
    if goal_complete and not non_market_gaps:
        status = "complete"
        market_dependent_remaining = []
    elif non_market_gaps:
        status = "needs_non_market_repair"
    else:
        status = "not_complete_waiting_for_market"
    return {
        "schema": "brc.p0_first_bounded_live_order_completion_audit.v1",
        "scope": "P0 First Bounded Live Order Closure Cutover completion audit",
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "status": status,
        "goal_complete": goal_complete,
        "non_market_gaps": non_market_gaps,
        "market_dependent_remaining": market_dependent_remaining,
        "safety_invariants": {
            "server_files_mutated": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "approaches_real_order": False,
            "withdrawal_or_transfer_created": False,
        },
        "items": items,
    }


def _owner_progress_text(report: dict[str, Any]) -> str:
    non_market = report.get("non_market_gaps") or []
    market_remaining = [str(item) for item in report.get("market_dependent_remaining") or []]
    non_market_text = "无" if not non_market else str(len(non_market))
    lines = [
        "## P0 First Bounded Live Order Closure Completion Audit",
        "",
        f"- 当前状态: {report.get('status')}",
        f"- Goal complete: {'是' if report.get('goal_complete') else '否'}",
        f"- 非市场缺口: {non_market_text}",
        f"- 市场依赖剩余项: {len(market_remaining)}",
        "- 服务器修改: 否",
        "- Live FinalGate: 否",
        "- Live Operation Layer: 否",
        "- Exchange write: 否",
        "- 接近真实订单: 否",
        "",
        "## Market Dependent Remaining",
        "",
    ]
    if market_remaining:
        lines.extend(f"- {item}" for item in market_remaining)
    else:
        lines.append("- none")
    lines.extend(["", "## Non-Market Gaps", ""])
    if non_market:
        for gap in non_market:
            lines.append(
                f"- {gap.get('requirement')}: "
                f"{', '.join(str(item) for item in gap.get('missing_or_false') or [])}"
            )
    else:
        lines.append("- none")
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit first bounded live order closure completion from local evidence."
    )
    parser.add_argument("--daily-check-json", default=str(DEFAULT_DAILY_CHECK_JSON))
    parser.add_argument("--goal-progress-json", default=str(DEFAULT_GOAL_PROGRESS_JSON))
    parser.add_argument("--dry-run-audit-json", default=str(DEFAULT_DRY_RUN_AUDIT_JSON))
    parser.add_argument("--live-cutover-json", default=str(DEFAULT_LIVE_CUTOVER_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--owner-progress", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_completion_audit_report(
        daily_check=_read_json(Path(args.daily_check_json)),
        goal_progress=_read_json(Path(args.goal_progress_json)),
        dry_run_audit=_read_json(Path(args.dry_run_audit_json)),
        live_cutover=_read_json(Path(args.live_cutover_json)),
    )
    _write_json(Path(args.output_json), report)
    owner_progress = _owner_progress_text(report)
    _write_text(Path(args.output_owner_progress), owner_progress + "\n")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(owner_progress)
    return 0 if report["status"] in {"complete", "not_complete_waiting_for_market"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
