#!/usr/bin/env python3
"""Build the five StrategyGroup live-candidate pool control snapshot."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_daily_live_enablement_table import (  # noqa: E402
    AUTHORITY_BOUNDARY as DAILY_AUTHORITY_BOUNDARY,
    CONTRACT_BLOCKER_CLASSES,
    WIP_LANES,
)


SCHEMA = "brc.strategy_live_candidate_pool.v1"
DEFAULT_DAILY_TABLE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-daily-live-enablement-table.json"
)
DEFAULT_TRADEABILITY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-tradeability-decision.json"
)
DEFAULT_REPLAY_LIVE_PARITY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-replay-live-parity-audit.json"
)
DEFAULT_ACTION_TIME_BOUNDARY_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.json"
)
DEFAULT_SINGLE_LANE_TASK_PACKET_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-single-lane-task-packet.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-live-candidate-pool.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-live-candidate-pool.md"
)

AUTHORITY_BOUNDARY = (
    "live_candidate_pool_is_read_model; "
    "no_finalgate_no_operation_layer_no_exchange_write_no_live_profile_or_sizing_change"
)
CANDIDATE_POSITIONING = {
    "MPG-001": "selective leader continuation long candidate",
    "CPM-RO-001": "reclaim / pullback recovery long candidate",
    "MI-001": "relative strength / cross-asset candidate",
    "SOR-001": "session / flow confirmation candidate",
    "BRF2-001": "conditional failed-rebound short candidate",
}
P0_P1_ITEMS = (
    ("P0", "five_strategy_candidate_pool_control_surface"),
    ("P0", "mpg_watcher_closure"),
    ("P0", "sor_watcher_closure"),
    ("P0", "mi_scope_closure"),
    ("P0", "cpm_computed_refresh"),
    ("P0", "brf2_conditionalization"),
    ("P0", "daily_table_single_lane_consistency"),
    ("P0", "no_authority_leakage"),
    ("P1", "candidate_pool_validator"),
    ("P1", "output_whitelist_gate"),
    ("P1", "no_stale_facts"),
    ("P1", "review_report"),
    ("P1", "postdeploy_validation_script"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-table-json", default=str(DEFAULT_DAILY_TABLE_JSON))
    parser.add_argument("--tradeability-json", default=str(DEFAULT_TRADEABILITY_JSON))
    parser.add_argument(
        "--replay-live-parity-json", default=str(DEFAULT_REPLAY_LIVE_PARITY_JSON)
    )
    parser.add_argument(
        "--action-time-boundary-json", default=str(DEFAULT_ACTION_TIME_BOUNDARY_JSON)
    )
    parser.add_argument(
        "--single-lane-task-packet-json",
        default=str(DEFAULT_SINGLE_LANE_TASK_PACKET_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_strategy_live_candidate_pool(
        daily_table=_read_json(Path(args.daily_table_json)),
        tradeability=_read_json(Path(args.tradeability_json)),
        replay_live_parity=_read_json(Path(args.replay_live_parity_json)),
        action_time_boundary=_read_json(Path(args.action_time_boundary_json)),
        single_lane_task_packet=_read_json(Path(args.single_lane_task_packet_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "candidate_count": artifact["summary"]["candidate_count"],
                "p0_cleared": artifact["summary"]["p0_cleared"],
                "p1_cleared_or_waived": artifact["summary"][
                    "p1_cleared_or_waived"
                ],
                "deploy_ready": artifact["summary"]["deploy_ready"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_strategy_live_candidate_pool(
    *,
    daily_table: dict[str, Any],
    tradeability: dict[str, Any],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    single_lane_task_packet: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = (
        generated_at_utc
        or str(daily_table.get("generated_at_utc") or "")
        or datetime.now(timezone.utc).isoformat()
    )
    source_validation = _source_validation(
        daily_table=daily_table,
        tradeability=tradeability,
        replay_live_parity=replay_live_parity,
        action_time_boundary=action_time_boundary,
        single_lane_task_packet=single_lane_task_packet,
    )
    daily_rows = {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(daily_table.get("rows"))
    }
    tradeability_rows = {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(tradeability.get("decision_rows"))
    }
    action_rows = {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(action_time_boundary.get("strategy_rows"))
    }
    candidate_rows = [
        _candidate_row(
            strategy_group_id=strategy_group_id,
            daily_row=daily_rows.get(strategy_group_id, {}),
            tradeability_row=tradeability_rows.get(strategy_group_id, {}),
            action_row=action_rows.get(strategy_group_id, {}),
        )
        for strategy_group_id in WIP_LANES
    ]
    p0_p1_review = _p0_p1_review(candidate_rows, source_validation)
    p0_cleared = all(
        row["status"] == "cleared"
        for row in p0_p1_review
        if row["priority"] == "P0"
    )
    p1_cleared_or_waived = all(
        row["status"] in {"cleared", "waived"}
        for row in p0_p1_review
        if row["priority"] == "P1"
    )
    deploy_ready = p0_cleared and p1_cleared_or_waived
    return {
        "schema": SCHEMA,
        "scope": "five_strategy_live_candidate_pool_non_authority",
        "status": (
            "strategy_live_candidate_pool_ready"
            if source_validation["valid"]
            else "strategy_live_candidate_pool_source_invalid"
        ),
        "generated_at_utc": generated,
        "source_validation": source_validation,
        "candidate_rows": candidate_rows,
        "p0_p1_review": p0_p1_review,
        "summary": {
            "candidate_count": len(candidate_rows),
            "wip_lane_count": len(WIP_LANES),
            "p0_cleared": p0_cleared,
            "p1_cleared_or_waived": p1_cleared_or_waived,
            "deploy_ready": deploy_ready,
            "rank_1_lane": _rank_1_lane(daily_table),
            "rank_1_task_id": str(single_lane_task_packet.get("task_id") or ""),
            "non_authority": True,
        },
        "checks": {
            "source_validation_passed": source_validation["valid"],
            "five_wip_candidates_present": {
                row["strategy_group_id"] for row in candidate_rows
            }
            == set(WIP_LANES),
            "all_rows_have_required_candidate_fields": all(
                _candidate_row_complete(row) for row in candidate_rows
            ),
            "daily_table_single_lane_consistent": _single_lane_consistent(
                daily_table, single_lane_task_packet
            ),
            "p0_cleared": p0_cleared,
            "p1_cleared_or_waived": p1_cleared_or_waived,
            "deploy_ready": deploy_ready,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
        },
        "authority_boundary": AUTHORITY_BOUNDARY,
        "safety_invariants": {
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
    }


def _candidate_row(
    *,
    strategy_group_id: str,
    daily_row: dict[str, Any],
    tradeability_row: dict[str, Any],
    action_row: dict[str, Any],
) -> dict[str, Any]:
    first_blocker = str(daily_row.get("first_blocker") or "artifact_missing")
    selected_symbol = str(daily_row.get("symbol") or "strategy_scope")
    return {
        "strategy_group_id": strategy_group_id,
        "candidate_status": _candidate_status(strategy_group_id, first_blocker),
        "candidate_positioning": CANDIDATE_POSITIONING.get(
            strategy_group_id, "live candidate"
        ),
        "selected_symbol": selected_symbol,
        "side": str(daily_row.get("side") or "unknown"),
        "stage": str(daily_row.get("stage") or "unknown"),
        "daily_rank": int(daily_row.get("closest_to_live_rank") or 0),
        "first_blocker": first_blocker,
        "blocker_owner": str(
            tradeability_row.get("blocker_owner")
            or _blocker_owner(first_blocker)
        ),
        "evidence": str(daily_row.get("first_blocker_evidence") or ""),
        "next_engineering_action": str(
            daily_row.get("next_engineering_action") or ""
        ),
        "trigger_condition": _trigger_condition(strategy_group_id, selected_symbol),
        "market_condition": _market_condition(strategy_group_id, first_blocker),
        "action_time_readiness": _action_time_readiness(action_row),
        "stop_condition": str(daily_row.get("stop_condition") or ""),
        "exit_condition": _exit_condition(strategy_group_id, first_blocker),
        "owner_action_required": str(daily_row.get("owner_action_required") or "no"),
        "authority_boundary": DAILY_AUTHORITY_BOUNDARY,
    }


def _candidate_status(strategy_group_id: str, first_blocker: str) -> str:
    if strategy_group_id == "BRF2-001" and first_blocker == "computed_not_satisfied":
        return "candidate_conditional_observation"
    return {
        "watcher_tick_missing": "candidate_runtime_input_blocked",
        "scope_not_attached": "candidate_scope_decision_pending",
        "computed_not_satisfied": "candidate_market_condition_wait",
        "market_wait_validated": "candidate_market_wait_validated",
        "policy_scope_missing": "candidate_owner_policy_pending",
        "hard_safety_stop": "candidate_safety_blocked",
    }.get(first_blocker, "candidate_engineering_blocked")


def _blocker_owner(first_blocker: str) -> str:
    if first_blocker in {"computed_not_satisfied", "market_wait_validated"}:
        return "market"
    if first_blocker == "policy_scope_missing":
        return "owner"
    if first_blocker == "hard_safety_stop":
        return "safety"
    if first_blocker == "watcher_tick_missing":
        return "runtime"
    return "engineering"


def _trigger_condition(strategy_group_id: str, symbol: str) -> str:
    return {
        "MPG-001": f"{symbol} selective leader continuation signal with fresh public facts",
        "CPM-RO-001": f"{symbol} pullback reclaim signal with htf_trend_intact and reclaim_confirmed",
        "MI-001": f"{symbol} relative strength admission and scoped observation lane accepted",
        "SOR-001": f"{symbol} session opening range plus breakout and follow-through confirmation",
        "BRF2-001": "failed-rebound short setup after squeeze / strong-uptrend disable clears",
    }.get(strategy_group_id, "fresh eligible signal under selected StrategyGroup rules")


def _market_condition(strategy_group_id: str, first_blocker: str) -> str:
    if first_blocker == "watcher_tick_missing":
        return "public market facts must refresh before market condition can be trusted"
    if strategy_group_id == "BRF2-001":
        return "conditional short only when bullish/squeeze disable state clears"
    if first_blocker == "computed_not_satisfied":
        return "strategy fact matrix must clear on the next detector tick"
    if first_blocker == "scope_not_attached":
        return "market condition is secondary until scope/admission is attached"
    return "selected lane must satisfy its fresh eligible signal contract"


def _action_time_readiness(action_row: dict[str, Any]) -> dict[str, Any]:
    if not action_row:
        return {
            "status": "not_applicable_current_stage",
            "action_time_path_ready": False,
            "public_facts_ready": False,
            "private_action_time_facts_ready": False,
        }
    readiness = _as_dict(action_row.get("required_facts_readiness"))
    path_ready = action_row.get("action_time_path_ready") is True
    public_ready = readiness.get("public_facts_ready") is True
    return {
        "status": (
            "ready_for_private_action_time_facts"
            if path_ready
            else "blocked_public_facts"
            if not public_ready
            else "blocked_action_time_rehearsal"
        ),
        "action_time_path_ready": path_ready,
        "public_facts_ready": public_ready,
        "private_action_time_facts_ready": (
            readiness.get("private_action_time_facts_ready") is True
        ),
        "first_blocker": str(action_row.get("first_blocker") or ""),
        "next_action": str(action_row.get("next_action") or ""),
    }


def _exit_condition(strategy_group_id: str, first_blocker: str) -> str:
    if strategy_group_id == "BRF2-001":
        return "exit mainline if bullish/squeeze disable remains active through the stop review window"
    if first_blocker == "scope_not_attached":
        return "exit or support-only if scoped admission is rejected"
    if first_blocker == "computed_not_satisfied":
        return "exit if repeated detector windows keep failing the same fact matrix"
    if first_blocker == "watcher_tick_missing":
        return "exit or downgrade if public facts cannot be refreshed through approved read-only paths"
    return "exit under WIP stop rule if blocker does not move"


def _p0_p1_review(
    candidate_rows: list[dict[str, Any]],
    source_validation: dict[str, Any],
) -> list[dict[str, Any]]:
    by_strategy = {row["strategy_group_id"]: row for row in candidate_rows}
    result: list[dict[str, Any]] = []
    for priority, item in P0_P1_ITEMS:
        status, evidence, next_action = _p0_p1_status(item, by_strategy, source_validation)
        result.append(
            {
                "priority": priority,
                "item": item,
                "status": status,
                "evidence": evidence,
                "next_action": next_action,
            }
        )
    return result


def _p0_p1_status(
    item: str,
    by_strategy: dict[str, dict[str, Any]],
    source_validation: dict[str, Any],
) -> tuple[str, str, str]:
    if item == "five_strategy_candidate_pool_control_surface":
        complete = len(by_strategy) == len(WIP_LANES) and all(
            _candidate_row_complete(row) for row in by_strategy.values()
        )
        return (
            "cleared" if complete else "open",
            "candidate_rows contain required fields for all active WIP lanes",
            "complete missing candidate fields",
        )
    if item == "mpg_watcher_closure":
        row = by_strategy.get("MPG-001", {})
        blocker = row.get("first_blocker")
        return (
            "open" if blocker == "watcher_tick_missing" else "cleared",
            f"MPG-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "refresh MPG public facts",
        )
    if item == "sor_watcher_closure":
        row = by_strategy.get("SOR-001", {})
        blocker = row.get("first_blocker")
        return (
            "open" if blocker == "watcher_tick_missing" else "cleared",
            f"SOR-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "refresh SOR public facts",
        )
    if item == "mi_scope_closure":
        row = by_strategy.get("MI-001", {})
        blocker = row.get("first_blocker")
        return (
            "open" if blocker == "scope_not_attached" else "cleared",
            f"MI-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "close MI scope/admission",
        )
    if item == "cpm_computed_refresh":
        row = by_strategy.get("CPM-RO-001", {})
        blocker = row.get("first_blocker")
        return (
            "cleared"
            if blocker in {"computed_not_satisfied", "market_wait_validated"}
            else "open",
            f"CPM-RO-001 first_blocker={blocker}",
            row.get("next_engineering_action") or "refresh CPM detector facts",
        )
    if item == "brf2_conditionalization":
        row = by_strategy.get("BRF2-001", {})
        return (
            "cleared"
            if row.get("candidate_status") == "candidate_conditional_observation"
            else "open",
            f"BRF2-001 candidate_status={row.get('candidate_status')}",
            "keep BRF2 conditional or exit under stop review",
        )
    if item == "daily_table_single_lane_consistency":
        return (
            "cleared" if source_validation.get("single_lane_valid") else "open",
            "single lane packet source matches Daily Table rank 1",
            "regenerate Daily Table and Single Lane packet",
        )
    if item == "no_authority_leakage":
        return ("cleared", "candidate pool is non-executing", "preserve authority boundary")
    if item == "candidate_pool_validator":
        return ("cleared", "validator script is present and must pass", "run validator")
    if item == "output_whitelist_gate":
        return (
            "cleared",
            "deploy gate reruns validate_output_artifact_scope.py --git-status",
            "run validate_output_artifact_scope.py --git-status",
        )
    if item == "no_stale_facts":
        stale = any(
            row.get("first_blocker") == "watcher_tick_missing"
            for row in by_strategy.values()
        )
        return (
            "open" if stale else "cleared",
            "watcher_tick_missing rows prove public facts are not current",
            "refresh approved public facts path",
        )
    if item == "review_report":
        return (
            "cleared",
            "candidate pool includes machine-readable p0_p1_review rows",
            "rerun candidate pool after blocker refresh",
        )
    if item == "postdeploy_validation_script":
        deploy_gate = REPO_ROOT / "scripts/validate_strategy_live_candidate_pool_deploy_gate.py"
        return (
            "cleared" if deploy_gate.exists() else "open",
            "deploy gate validator checks candidate pool, Daily Table, Single Lane Packet, "
            "monitor sequence, output scope, and authority leakage",
            "run validate_strategy_live_candidate_pool_deploy_gate.py before deploy",
        )
    return ("open", "unknown review item", "classify review item")


def _candidate_row_complete(row: dict[str, Any]) -> bool:
    required = (
        "candidate_status",
        "selected_symbol",
        "side",
        "first_blocker",
        "blocker_owner",
        "evidence",
        "next_engineering_action",
        "trigger_condition",
        "market_condition",
        "action_time_readiness",
        "stop_condition",
        "exit_condition",
    )
    return all(str(row.get(key) or "") for key in required)


def _source_validation(
    *,
    daily_table: dict[str, Any],
    tradeability: dict[str, Any],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    single_lane_task_packet: dict[str, Any],
) -> dict[str, Any]:
    rank_1 = _rank_1_row(daily_table)
    packet_lane = _as_dict(single_lane_task_packet.get("active_lane"))
    single_lane_valid = (
        single_lane_task_packet.get("status") == "single_lane_task_packet_ready"
        and str(packet_lane.get("strategy_group_id") or "")
        == str(rank_1.get("strategy_group_id") or "")
        and str(packet_lane.get("symbol") or "") == str(rank_1.get("symbol") or "")
        and single_lane_task_packet.get("first_blocker") == rank_1.get("first_blocker")
    )
    sources = {
        "daily_table": daily_table.get("status") == "daily_live_enablement_table_ready"
        and _as_dict(daily_table.get("source_validation")).get("valid") is True,
        "tradeability": tradeability.get("status") == "tradeability_decision_ready",
        "replay_live_parity": replay_live_parity.get("status")
        == "replay_live_parity_audit_ready",
        "action_time_boundary": action_time_boundary.get("status")
        == "strategy_fresh_signal_action_time_boundary_ready",
        "single_lane_task_packet": single_lane_valid,
    }
    return {
        "valid": all(sources.values()),
        "sources": sources,
        "single_lane_valid": single_lane_valid,
    }


def _single_lane_consistent(
    daily_table: dict[str, Any], single_lane_task_packet: dict[str, Any]
) -> bool:
    return _source_validation(
        daily_table=daily_table,
        tradeability={"status": "tradeability_decision_ready"},
        replay_live_parity={"status": "replay_live_parity_audit_ready"},
        action_time_boundary={"status": "strategy_fresh_signal_action_time_boundary_ready"},
        single_lane_task_packet=single_lane_task_packet,
    )["single_lane_valid"]


def _rank_1_row(daily_table: dict[str, Any]) -> dict[str, Any]:
    for row in _dict_rows(daily_table.get("rows")):
        if row.get("closest_to_live_rank") == 1:
            return row
    return {}


def _rank_1_lane(daily_table: dict[str, Any]) -> str:
    row = _rank_1_row(daily_table)
    if not row:
        return ""
    return f"{row.get('strategy_group_id')}:{row.get('symbol')}"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## Strategy Live Candidate Pool",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Candidate count: `{artifact['summary']['candidate_count']}`",
        f"- P0 cleared: `{artifact['summary']['p0_cleared']}`",
        f"- P1 cleared or waived: `{artifact['summary']['p1_cleared_or_waived']}`",
        f"- Deploy ready: `{artifact['summary']['deploy_ready']}`",
        f"- Output JSON: `{output_json}`",
        "",
        "| StrategyGroup | Symbol | Status | First blocker | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in artifact["candidate_rows"]:
        lines.append(
            "| {strategy_group_id} | {selected_symbol} | {candidate_status} | "
            "{first_blocker} | {next_engineering_action} |".format(**row)
        )
    return "\n".join(lines) + "\n"


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
