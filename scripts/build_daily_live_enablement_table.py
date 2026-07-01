#!/usr/bin/env python3
"""Build the Daily Live Enablement Table read model.

The table is the single daily control surface for active StrategyGroup live
enablement lanes. It is non-executing and must not create live authority.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TRADEABILITY_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-tradeability-decision.json"
)
DEFAULT_REPLAY_LIVE_PARITY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-replay-live-parity-audit.json"
)
DEFAULT_ACTION_TIME_BOUNDARY_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.json"
)
DEFAULT_MI_TRIAL_ADMISSION_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-mi-trial-admission-decision.json"
)
DEFAULT_RUNTIME_SAFETY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-runtime-safety-state.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-daily-live-enablement-table.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-daily-live-enablement-table.md"
)

SCHEMA = "brc.daily_live_enablement_table.v1"
WIP_LANES = ("CPM-RO-001", "MPG-001", "MI-001", "SOR-001", "BRF2-001")
WIP_PRIORITY_BONUS = {
    "CPM-RO-001": 20,
    "MPG-001": 20,
    "MI-001": 10,
    "SOR-001": 10,
    "BRF2-001": 0,
}
CONTRACT_BLOCKER_CLASSES = {
    "artifact_missing",
    "schema_invalid",
    "detector_not_attached",
    "watcher_tick_missing",
    "scope_not_attached",
    "computed_not_satisfied",
    "replay_live_rule_mismatch",
    "action_time_boundary_not_reproduced",
    "policy_scope_missing",
    "runtime_profile_scope_missing",
    "market_wait_validated",
    "active_position_resolution",
    "hard_safety_stop",
    "review_only_warning",
}
OWNER_BLOCKERS = {"policy_scope_missing"}
AUTHORITY_BOUNDARY = (
    "daily_table_is_read_model; no_finalgate_no_operation_layer_no_exchange_write"
)
BLOCKER_RANK_SCORE = {
    "scope_not_attached": 95,
    "action_time_boundary_not_reproduced": 90,
    "detector_not_attached": 80,
    "watcher_tick_missing": 75,
    "replay_live_rule_mismatch": 70,
    "runtime_profile_scope_missing": 65,
    "active_position_resolution": 60,
    "artifact_missing": 55,
    "schema_invalid": 50,
    "market_wait_validated": 45,
    "computed_not_satisfied": 40,
    "policy_scope_missing": 30,
    "hard_safety_stop": 0,
    "review_only_warning": 0,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tradeability-json", default=str(DEFAULT_TRADEABILITY_JSON))
    parser.add_argument(
        "--replay-live-parity-json", default=str(DEFAULT_REPLAY_LIVE_PARITY_JSON)
    )
    parser.add_argument(
        "--action-time-boundary-json", default=str(DEFAULT_ACTION_TIME_BOUNDARY_JSON)
    )
    parser.add_argument(
        "--mi-trial-admission-json", default=str(DEFAULT_MI_TRIAL_ADMISSION_JSON)
    )
    parser.add_argument("--runtime-safety-json", default=str(DEFAULT_RUNTIME_SAFETY_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_daily_live_enablement_table(
        tradeability=_read_optional_json(Path(args.tradeability_json)),
        replay_live_parity=_read_optional_json(Path(args.replay_live_parity_json)),
        action_time_boundary=_read_optional_json(Path(args.action_time_boundary_json)),
        mi_trial_admission=_read_optional_json(Path(args.mi_trial_admission_json)),
        runtime_safety=_read_optional_json(Path(args.runtime_safety_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "row_count": artifact["summary"]["row_count"],
                "rank_1_lane": artifact["summary"]["rank_1_lane"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def build_daily_live_enablement_table(
    *,
    tradeability: dict[str, Any],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    mi_trial_admission: dict[str, Any],
    runtime_safety: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    tradeability_rows = {
        str(row.get("strategy_group_id") or ""): row
        for row in _dict_rows(tradeability.get("decision_rows"))
    }
    ranked_rows = [
        _daily_row(
            strategy_group_id=strategy_group_id,
            tradeability_row=tradeability_rows.get(strategy_group_id, {}),
            replay_live_parity=replay_live_parity,
            action_time_boundary=action_time_boundary,
            mi_trial_admission=mi_trial_admission,
            runtime_safety=runtime_safety,
        )
        for strategy_group_id in WIP_LANES
    ]
    ranked_rows = _rank_rows(ranked_rows)
    rank_1 = next(row for row in ranked_rows if row["closest_to_live_rank"] == 1)
    return {
        "schema": SCHEMA,
        "scope": "daily_live_enablement_table_non_authority",
        "status": "daily_live_enablement_table_ready",
        "generated_at_utc": generated,
        "rows": ranked_rows,
        "summary": {
            "row_count": len(ranked_rows),
            "wip_lane_count": len(WIP_LANES),
            "rank_1_lane": (
                f"{rank_1['strategy_group_id']}:{rank_1['symbol']}"
            ),
            "rank_1_first_blocker": rank_1["first_blocker"],
            "rank_1_next_engineering_action": rank_1["next_engineering_action"],
            "owner_action_required_count": sum(
                row["owner_action_required"] == "yes" for row in ranked_rows
            ),
            "non_authority": True,
        },
        "checks": {
            "active_wip_lanes_only": {
                row["strategy_group_id"] for row in ranked_rows
            }
            == set(WIP_LANES),
            "single_rank_1": sum(
                row["closest_to_live_rank"] == 1 for row in ranked_rows
            )
            == 1,
            "all_rows_have_blocker_evidence_action_stop": all(
                row["first_blocker"]
                and row["first_blocker_evidence"]
                and row["next_engineering_action"]
                and row["stop_condition"]
                for row in ranked_rows
            ),
            "authority_boundary_preserved": all(
                row["authority_boundary"] == AUTHORITY_BOUNDARY
                for row in ranked_rows
            ),
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
        },
        "interaction": {
            "level": "L0_local_daily_live_enablement_table",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
        },
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


def _daily_row(
    *,
    strategy_group_id: str,
    tradeability_row: dict[str, Any],
    replay_live_parity: dict[str, Any],
    action_time_boundary: dict[str, Any],
    mi_trial_admission: dict[str, Any],
    runtime_safety: dict[str, Any],
) -> dict[str, Any]:
    first_blocker = str(
        tradeability_row.get("first_blocker_class") or "artifact_missing"
    )
    parity_row = _best_parity_row(
        strategy_group_id=strategy_group_id,
        first_blocker=first_blocker,
        replay_live_parity=replay_live_parity,
    )
    action_row = _action_time_row(strategy_group_id, action_time_boundary)
    symbol = _lane_symbol(
        strategy_group_id=strategy_group_id,
        tradeability_row=tradeability_row,
        parity_row=parity_row,
        action_row=action_row,
        mi_trial_admission=mi_trial_admission,
    )
    side = _lane_side(
        strategy_group_id=strategy_group_id,
        tradeability_row=tradeability_row,
        mi_trial_admission=mi_trial_admission,
    )
    stage = _daily_stage(str(tradeability_row.get("stage") or "research_candidate"))
    chain_position = _chain_position(first_blocker)
    evidence = _evidence(
        strategy_group_id=strategy_group_id,
        first_blocker=first_blocker,
        tradeability_row=tradeability_row,
        parity_row=parity_row,
        action_row=action_row,
        mi_trial_admission=mi_trial_admission,
    )
    next_action = str(
        tradeability_row.get("next_action")
        or _next_action_for_blocker(first_blocker)
    )
    stop_condition = _stop_condition(
        strategy_group_id=strategy_group_id,
        first_blocker=first_blocker,
        next_action=next_action,
    )
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "stage": stage,
        "chain_position": chain_position,
        "first_blocker": first_blocker,
        "first_blocker_evidence": evidence,
        "owner_action_required": (
            "yes" if first_blocker in OWNER_BLOCKERS else "no"
        ),
        "next_engineering_action": next_action,
        "stop_condition": stop_condition,
        "closest_to_live_rank": 0,
        "rank_reason": "",
        "authority_boundary": AUTHORITY_BOUNDARY,
        "replay_signal": _replay_signal(strategy_group_id, parity_row),
        "live_detector": _live_detector_state(first_blocker, parity_row),
        "market_wait_validation": _market_wait_validation(tradeability_row),
        "runtime_safety_reference": _runtime_safety_reference(
            strategy_group_id, runtime_safety
        ),
    }


def _best_parity_row(
    *,
    strategy_group_id: str,
    first_blocker: str,
    replay_live_parity: dict[str, Any],
) -> dict[str, Any]:
    rows = [
        row
        for row in _dict_rows(replay_live_parity.get("per_symbol_mismatch_table"))
        if str(row.get("strategy_group_id") or "") == strategy_group_id
    ]
    if not rows:
        return {}
    matching = [
        row for row in rows if str(row.get("blocker_class") or "") == first_blocker
    ]
    candidates = matching or rows
    return sorted(
        candidates,
        key=lambda row: (
            -int(row.get("mismatch_count") or 0),
            str(row.get("symbol") or ""),
        ),
    )[0]


def _action_time_row(
    strategy_group_id: str,
    action_time_boundary: dict[str, Any],
) -> dict[str, Any]:
    for row in _dict_rows(action_time_boundary.get("strategy_rows")):
        if str(row.get("strategy_group_id") or "") == strategy_group_id:
            return row
    return {}


def _lane_symbol(
    *,
    strategy_group_id: str,
    tradeability_row: dict[str, Any],
    parity_row: dict[str, Any],
    action_row: dict[str, Any],
    mi_trial_admission: dict[str, Any],
) -> str:
    if parity_row.get("symbol"):
        return str(parity_row["symbol"])
    if action_row.get("symbol"):
        return str(action_row["symbol"])
    if strategy_group_id == "MI-001":
        reviewed = _as_dict(mi_trial_admission.get("symbol_scope")).get(
            "reviewed_symbols"
        )
        if isinstance(reviewed, list) and reviewed:
            return str(reviewed[0])
    for path in _dict_rows(tradeability_row.get("trade_paths")):
        watcher = _as_dict(path.get("watcher_scope"))
        symbols = watcher.get("symbols")
        if isinstance(symbols, list) and symbols:
            return str(symbols[0])
        if isinstance(symbols, str) and symbols:
            return symbols
    policy = _as_dict(tradeability_row.get("policy_scope"))
    symbol_scope = policy.get("symbol_scope")
    if isinstance(symbol_scope, list) and symbol_scope:
        return str(symbol_scope[0])
    return "strategy_scope"


def _lane_side(
    *,
    strategy_group_id: str,
    tradeability_row: dict[str, Any],
    mi_trial_admission: dict[str, Any],
) -> str:
    if strategy_group_id == "MI-001" and mi_trial_admission.get("side"):
        return str(mi_trial_admission["side"])
    for path in _dict_rows(tradeability_row.get("trade_paths")):
        if path.get("side"):
            return str(path["side"])
    policy = _as_dict(tradeability_row.get("policy_scope"))
    side_scope = policy.get("side_scope")
    if isinstance(side_scope, list) and side_scope:
        return str(side_scope[0])
    return "unknown"


def _daily_stage(stage: str) -> str:
    return {
        "research_candidate": "research",
        "tiny_live_intake_candidate": "intake",
        "trial_asset_admission_candidate": "admission",
        "observe_only_would_enter": "readonly",
        "armed_observation": "armed",
        "tiny_live_ready": "action_time",
        "live_submit_ready": "live_submit_ready",
    }.get(stage, stage or "research")


def _chain_position(first_blocker: str) -> str:
    if first_blocker in {"scope_not_attached", "policy_scope_missing"}:
        return "symbol_scope_decision"
    if first_blocker in {
        "action_time_boundary_not_reproduced",
        "runtime_profile_scope_missing",
        "active_position_resolution",
    }:
        return "action_time_boundary"
    if first_blocker in {
        "detector_not_attached",
        "watcher_tick_missing",
        "computed_not_satisfied",
        "replay_live_rule_mismatch",
        "market_wait_validated",
    }:
        return "replay_live_parity"
    return "tradeability_first_blocker"


def _evidence(
    *,
    strategy_group_id: str,
    first_blocker: str,
    tradeability_row: dict[str, Any],
    parity_row: dict[str, Any],
    action_row: dict[str, Any],
    mi_trial_admission: dict[str, Any],
) -> str:
    if parity_row:
        return (
            "output/runtime-monitor/latest-replay-live-parity-audit.json:"
            f"{strategy_group_id}/{parity_row.get('symbol') or 'strategy_scope'} "
            f"blocker_class={parity_row.get('blocker_class')}"
        )
    if action_row:
        return (
            "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.json:"
            f"{strategy_group_id} first_blocker={action_row.get('first_blocker')}"
        )
    if strategy_group_id == "MI-001" and mi_trial_admission:
        return (
            "output/runtime-monitor/latest-mi-trial-admission-decision.json:"
            f"trial_admission_decision={mi_trial_admission.get('trial_admission_decision')}"
        )
    detail = str(tradeability_row.get("first_blocker_detail") or first_blocker)
    return (
        "output/runtime-monitor/latest-strategygroup-tradeability-decision.json:"
        f"{strategy_group_id} {detail}"
    )


def _stop_condition(
    *,
    strategy_group_id: str,
    first_blocker: str,
    next_action: str,
) -> str:
    if first_blocker == "market_wait_validated":
        return "fresh eligible signal appears or lane exits WIP under stop rule"
    if first_blocker == "computed_not_satisfied":
        return (
            "failed fact matrix clears or blocker reclassifies after next detector tick"
        )
    if first_blocker == "scope_not_attached":
        return (
            "scoped live observation proposal is attached or Owner scope decision is required"
        )
    if first_blocker == "policy_scope_missing":
        return "Owner scoped policy is recorded or lane exits mainline"
    if first_blocker == "detector_not_attached":
        return "live detector is attached to the selected lane"
    if first_blocker == "watcher_tick_missing":
        return "watcher/public facts tick is present for the selected lane"
    if first_blocker == "action_time_boundary_not_reproduced":
        return "non-executing action-time rehearsal reaches candidate/auth boundary"
    if first_blocker == "artifact_missing":
        return "required current artifact is generated through monitor sequence"
    if first_blocker == "schema_invalid":
        return "artifact schema validates and generator regression test passes"
    return f"{next_action} changes first_blocker or lane exits WIP"


def _next_action_for_blocker(first_blocker: str) -> str:
    return {
        "artifact_missing": "generate_or_wire_current_artifact",
        "schema_invalid": "repair_artifact_schema_and_add_regression",
        "detector_not_attached": "attach_live_detector_to_selected_lane",
        "watcher_tick_missing": "refresh_or_repair_watcher_fact_source",
        "scope_not_attached": "produce_scoped_live_observation_or_scope_proposal",
        "computed_not_satisfied": "continue_observation_with_failed_fact_matrix",
        "replay_live_rule_mismatch": "normalize_replay_live_rules_or_record_revision",
        "action_time_boundary_not_reproduced": "repair_non_executing_action_time_rehearsal_path",
        "policy_scope_missing": "record_scoped_owner_policy",
        "runtime_profile_scope_missing": "bind_runtime_profile_scope",
        "market_wait_validated": "continue_armed_observation_until_fresh_signal",
        "active_position_resolution": "resolve_active_position_or_open_order",
        "hard_safety_stop": "remove_hard_safety_violation",
        "review_only_warning": "record_strategy_review_decision",
    }.get(first_blocker, "repair_daily_live_enablement_blocker_classification")


def _replay_signal(strategy_group_id: str, parity_row: dict[str, Any]) -> str:
    if parity_row:
        return "yes"
    if strategy_group_id == "MI-001":
        return "not_applicable"
    return "unknown_with_reason:no_replay_live_parity_row"


def _live_detector_state(first_blocker: str, parity_row: dict[str, Any]) -> str:
    if not parity_row:
        return "not_tested"
    if first_blocker == "market_wait_validated":
        return "matched"
    if first_blocker in {
        "computed_not_satisfied",
        "scope_not_attached",
        "detector_not_attached",
        "watcher_tick_missing",
        "replay_live_rule_mismatch",
    }:
        return first_blocker
    return "not_matched"


def _market_wait_validation(tradeability_row: dict[str, Any]) -> dict[str, Any]:
    validation = _as_dict(tradeability_row.get("market_wait_validation"))
    if not validation:
        return {"valid": False, "not_applicable": True, "checks": {}}
    return validation


def _runtime_safety_reference(
    strategy_group_id: str,
    runtime_safety: dict[str, Any],
) -> dict[str, Any]:
    state = _as_dict(runtime_safety.get("runtime_safety_state"))
    return {
        "strategy_group_id": strategy_group_id,
        "live_submit_ready": state.get("live_submit_ready") is True,
        "live_submit_ready_false_reason": str(
            state.get("live_submit_ready_false_reason") or ""
        ),
        "state_source": "runtime_safety_state",
    }


def _rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            -_rank_score(row),
            WIP_LANES.index(row["strategy_group_id"]),
        ),
    )
    ranked_by_id: dict[str, dict[str, Any]] = {}
    for rank, row in enumerate(ordered, start=1):
        ranked = dict(row)
        ranked["closest_to_live_rank"] = rank
        ranked["rank_reason"] = (
            f"{row['first_blocker']} score {_rank_score(row)} "
            f"(blocker {BLOCKER_RANK_SCORE.get(row['first_blocker'], 0)} + "
            f"WIP priority {WIP_PRIORITY_BONUS.get(row['strategy_group_id'], 0)})"
        )
        ranked_by_id[row["strategy_group_id"]] = ranked
    return [ranked_by_id[strategy_group_id] for strategy_group_id in WIP_LANES]


def _rank_score(row: dict[str, Any]) -> int:
    return BLOCKER_RANK_SCORE.get(
        str(row.get("first_blocker") or ""), 0
    ) + WIP_PRIORITY_BONUS.get(str(row.get("strategy_group_id") or ""), 0)


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
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
    rows = artifact["rows"]
    lines = [
        "# Daily Live Enablement Table",
        "",
        f"- Source JSON: `{output_json}`",
        f"- Generated: `{artifact['generated_at_utc']}`",
        f"- Rank 1 lane: `{artifact['summary']['rank_1_lane']}`",
        "",
        "| Rank | StrategyGroup | Symbol | Stage | First blocker | Owner action | Next action | Stop condition |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in sorted(rows, key=lambda item: item["closest_to_live_rank"]):
        lines.append(
            "| {rank} | `{strategy}` | `{symbol}` | `{stage}` | `{blocker}` | `{owner}` | `{action}` | {stop} |".format(
                rank=row["closest_to_live_rank"],
                strategy=row["strategy_group_id"],
                symbol=row["symbol"],
                stage=row["stage"],
                blocker=row["first_blocker"],
                owner=row["owner_action_required"],
                action=row["next_engineering_action"],
                stop=row["stop_condition"],
            )
        )
    lines.extend(
        [
            "",
            "This table is a non-authority read model. It does not call FinalGate, Operation Layer, or exchange write.",
            "",
        ]
    )
    return "\n".join(lines)


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
