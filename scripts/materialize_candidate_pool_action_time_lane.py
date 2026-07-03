#!/usr/bin/env python3
"""Materialize one Candidate Pool action-time lane into prepare evidence.

This bridges the current pre-trade control surface into the existing runtime
prepare path:

Candidate Pool action_time_lane_inputs[0]
-> runtime next-attempt observation prepare API
-> signal_input_json / shadow_candidate_id / prepared_authorization_id
-> watcher status/operator/wakeup artifacts

It does not call FinalGate, Operation Layer, exchange write APIs, OrderLifecycle,
withdrawals, transfers, live profile mutation, or order sizing mutation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import runtime_next_attempt_observation_api_prepare_flow as prepare_flow  # noqa: E402
from scripts.build_runtime_observation_operator_evidence import (  # noqa: E402
    build_operator_evidence_from_path,
)
from scripts.build_runtime_observation_wakeup_evidence import (  # noqa: E402
    build_wakeup_evidence,
)


DEFAULT_CANDIDATE_POOL_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-live-candidate-pool.json"
)
DEFAULT_REPORT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
DEFAULT_OUTPUT_JSON = DEFAULT_REPORT_DIR / "action-time-lane-materialization.json"
LIVE_SUBMIT_SCOPE_STATES = {"live_submit_allowed"}
CONDITIONAL_REHEARSAL_SCOPE_STATES = {"conditional_action_time_rehearsal_allowed"}
READY_BLOCKER = "action_time_preflight_ready"
READY_PREPARE_STATUS = "ready_for_final_gate_preflight"


PrepareBuilder = Callable[[argparse.Namespace], dict[str, Any]]


@dataclass(frozen=True)
class LaneSelection:
    lane: dict[str, Any]
    runtime_instance_id: str
    strategy_group_id: str
    strategy_family_version_id: str
    symbol: str
    side: str


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _safe_file_id(value: str) -> str:
    return (
        value.replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("\\", "_")
    )


def _selected_runtime_ids(lane: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("selected_runtime_instance_ids", "active_runtime_instance_ids"):
        for item in _as_list(lane.get(key)):
            text = str(item or "").strip()
            if text and text not in ids:
                ids.append(text)
    for key in ("runtime_instance_id", "selected_runtime_instance_id"):
        text = str(lane.get(key) or "").strip()
        if text and text not in ids:
            ids.append(text)
    return ids


def _select_lane(candidate_pool: dict[str, Any]) -> tuple[LaneSelection | None, list[str]]:
    blockers: list[str] = []
    if candidate_pool.get("status") != "strategy_live_candidate_pool_ready":
        return None, ["candidate_pool_not_ready"]
    lane_inputs = [_as_dict(item) for item in _as_list(candidate_pool.get("action_time_lane_inputs"))]
    lane_inputs = [item for item in lane_inputs if item]
    if not lane_inputs:
        return None, []
    if len(lane_inputs) > 1:
        return None, ["multiple_action_time_lane_inputs"]
    lane = lane_inputs[0]
    scope_state = str(lane.get("scope_state") or "")
    if scope_state not in LIVE_SUBMIT_SCOPE_STATES:
        blockers.append(f"action_time_lane_scope_not_live_submit:{scope_state or 'missing'}")
    first_blocker = str(lane.get("first_blocker") or "")
    if first_blocker and first_blocker != READY_BLOCKER:
        blockers.append(f"action_time_lane_not_preflight_ready:{first_blocker}")
    signal_state = str(lane.get("signal_state") or "")
    if signal_state and signal_state != "fresh":
        blockers.append(f"action_time_lane_signal_not_fresh:{signal_state}")
    runtime_ids = _selected_runtime_ids(lane)
    if not runtime_ids:
        blockers.append("action_time_lane_runtime_instance_id_missing")
    strategy_group_id = _first_text(
        lane.get("strategy_group_id"),
        lane.get("strategy_family_id"),
        lane.get("strategy"),
    )
    symbol = _first_text(lane.get("symbol"), lane.get("selected_symbol"))
    side = _first_text(lane.get("side"), lane.get("signal_side"))
    if not strategy_group_id:
        blockers.append("action_time_lane_strategy_group_id_missing")
    if not symbol:
        blockers.append("action_time_lane_symbol_missing")
    if not side:
        blockers.append("action_time_lane_side_missing")
    if blockers:
        return None, blockers
    strategy_family_version_id = _first_text(
        lane.get("strategy_family_version_id"),
        lane.get("strategy_group_version_id"),
        f"{strategy_group_id}-v0",
    )
    return (
        LaneSelection(
            lane=lane,
            runtime_instance_id=runtime_ids[0],
            strategy_group_id=str(strategy_group_id),
            strategy_family_version_id=str(strategy_family_version_id),
            symbol=str(symbol),
            side=str(side),
        ),
        [],
    )


def _prepare_args(
    args: argparse.Namespace,
    *,
    selection: LaneSelection,
    signal_input_json: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=selection.runtime_instance_id,
        env_file=args.env_file,
        api_base=args.api_base,
        source=args.source,
        include_exchange=False,
        symbol=selection.symbol,
        side=selection.side,
        family=selection.strategy_group_id,
        strategy_family_id=selection.strategy_group_id,
        carrier_id=None,
        quantity=None,
        target_notional_usdt=None,
        max_notional=None,
        leverage=None,
        max_attempts=None,
        protection_mode=None,
        review_requirement=None,
        evaluation_id=None,
        playbook_id=None,
        one_hour_limit=args.one_hour_limit,
        four_hour_limit=args.four_hour_limit,
        timeout_seconds=args.timeout_seconds,
        signal_output_json=str(signal_input_json),
        output_dir=str(args.materialization_dir),
        allow_prepare_records=bool(args.allow_prepare_records),
        candidate_id=None,
        context_id=(
            "candidate-pool-action-time-lane:"
            f"{selection.strategy_group_id}:{selection.symbol}:{selection.side}"
        ),
        owner_operator_id=args.owner_operator_id,
        owner_confirmation_reference=args.owner_confirmation_reference,
        reason=(
            "materialize candidate pool action-time lane into non-executing "
            "prepare evidence"
        ),
        next_attempt_symbol=selection.symbol,
        next_attempt_side=selection.side,
        next_attempt_family=selection.strategy_group_id,
        next_attempt_strategy_family_id=selection.strategy_group_id,
        next_attempt_carrier_id=None,
    )


def _ids_from_prepare(prepare_artifact: dict[str, Any]) -> dict[str, Any]:
    ids = _as_dict(prepare_artifact.get("ids"))
    plan = _as_dict(prepare_artifact.get("api_prepare_plan"))
    nested_plan = _as_dict(_as_dict(prepare_artifact.get("prepare_artifact")).get("prepare_artifact_plan"))
    return {
        "prepared_authorization_id": _first_text(
            plan.get("prepared_authorization_id"),
            nested_plan.get("prepared_authorization_id"),
            ids.get("authorization_id"),
        ),
        "shadow_candidate_id": _first_text(
            ids.get("shadow_candidate_id"),
            ids.get("order_candidate_id"),
            ids.get("candidate_id"),
        ),
    }


def _upsert_runtime_summary(
    status_artifact: dict[str, Any],
    *,
    selection: LaneSelection,
    signal_input_json: str,
    prepared_authorization_id: str,
    shadow_candidate_id: str | None,
) -> None:
    rows = [
        _as_dict(item)
        for item in _as_list(status_artifact.get("runtime_signal_summaries"))
    ]
    updated_row = {
        "runtime_instance_id": selection.runtime_instance_id,
        "strategy_group_id": selection.strategy_group_id,
        "strategy_family_id": selection.strategy_group_id,
        "strategy_family_version_id": selection.strategy_family_version_id,
        "symbol": selection.symbol,
        "side": selection.side,
        "status": READY_PREPARE_STATUS,
        "signal_state": "fresh",
        "promotion_state": "action_time_lane",
        "first_blocker": READY_BLOCKER,
        "signal_input_json": signal_input_json,
        "prepared_authorization_id": prepared_authorization_id,
        "shadow_candidate_id": shadow_candidate_id,
    }
    replaced = False
    for index, row in enumerate(rows):
        if str(row.get("runtime_instance_id") or "") == selection.runtime_instance_id:
            rows[index] = {**row, **updated_row}
            replaced = True
            break
    if not replaced:
        rows.append(updated_row)
    status_artifact["runtime_signal_summaries"] = rows


def _patch_status_artifacts(
    *,
    report_dir: Path,
    selection: LaneSelection,
    prepare_artifact: dict[str, Any],
    signal_input_json: str,
    prepared_authorization_id: str,
    shadow_candidate_id: str | None,
) -> dict[str, Any]:
    status_path = report_dir / "status-artifact.json"
    latest_path = report_dir / "latest-status.json"
    status_artifact = _read_json(status_path)
    status_artifact["status"] = "ok"
    status_artifact["latest_status"] = READY_PREPARE_STATUS
    selected_ids = [
        str(item)
        for item in _as_list(status_artifact.get("selected_runtime_instance_ids"))
        if str(item).strip()
    ]
    if selection.runtime_instance_id not in selected_ids:
        selected_ids.append(selection.runtime_instance_id)
    status_artifact["selected_runtime_instance_ids"] = selected_ids
    status_artifact["signal_input_json"] = signal_input_json
    status_artifact["prepared_authorization_id"] = prepared_authorization_id
    status_artifact["shadow_candidate_id"] = shadow_candidate_id
    _upsert_runtime_summary(
        status_artifact,
        selection=selection,
        signal_input_json=signal_input_json,
        prepared_authorization_id=prepared_authorization_id,
        shadow_candidate_id=shadow_candidate_id,
    )
    safety = _as_dict(status_artifact.get("safety_invariants"))
    prepare_safety = _as_dict(prepare_artifact.get("safety_invariants"))
    status_artifact["safety_invariants"] = {
        **safety,
        "candidate_pool_action_time_lane_materialized": True,
        "observed_prepare_records_created": bool(
            prepare_safety.get("prepare_records_created")
        ),
        "observed_shadow_candidate_created": bool(
            prepare_safety.get("shadow_candidate_created")
        ),
        "observed_runtime_execution_intent_draft_created": bool(
            prepare_safety.get("runtime_execution_intent_draft_created")
        ),
        "observed_recorded_execution_intent_created": bool(
            prepare_safety.get("recorded_execution_intent_created")
        ),
        "observed_submit_authorization_created": bool(
            prepare_safety.get("submit_authorization_created")
        ),
        "observed_protection_plan_created": bool(
            prepare_safety.get("protection_plan_created")
        ),
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "execution_intent_created": False,
        "runtime_budget_mutated": False,
        "withdrawal_or_transfer_created": False,
    }
    allowed = set(status_artifact.get("allowed_prepare_record_effects") or [])
    allowed.update(
        {
            "shadow_candidate_created",
            "runtime_execution_intent_draft_created",
            "recorded_execution_intent_created",
            "submit_authorization_created",
            "protection_plan_created",
        }
    )
    status_artifact["allowed_prepare_record_effects"] = sorted(allowed)
    status_artifact["candidate_pool_action_time_lane_materialization"] = {
        "status": "ready_for_action_time_final_gate",
        "runtime_instance_id": selection.runtime_instance_id,
        "strategy_group_id": selection.strategy_group_id,
        "symbol": selection.symbol,
        "side": selection.side,
        "signal_input_json": signal_input_json,
        "shadow_candidate_id": shadow_candidate_id,
        "prepared_authorization_id": prepared_authorization_id,
        "authority_boundary": (
            "non_executing_prepare_only; no_finalgate_no_operation_layer_no_exchange_write"
        ),
    }
    _write_json(status_path, status_artifact)
    _write_json(latest_path, status_artifact)
    return status_artifact


def _refresh_operator_and_wakeup(
    *,
    report_dir: Path,
    strategy_source: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    operator = build_operator_evidence_from_path(
        status_artifact_json=report_dir / "status-artifact.json",
        strategy_source=strategy_source,
    )
    wakeup = build_wakeup_evidence(operator)
    _write_json(report_dir / "operator-evidence.json", operator)
    _write_json(report_dir / "wakeup-evidence.json", wakeup)
    return operator, wakeup


def materialize_action_time_lane(
    *,
    candidate_pool_json: Path = DEFAULT_CANDIDATE_POOL_JSON,
    report_dir: Path = DEFAULT_REPORT_DIR,
    output_json: Path = DEFAULT_OUTPUT_JSON,
    args: argparse.Namespace,
    prepare_builder: PrepareBuilder | None = None,
) -> dict[str, Any]:
    candidate_pool = _read_json(candidate_pool_json)
    selection, blockers = _select_lane(candidate_pool)
    base = {
        "schema": "brc.candidate_pool_action_time_lane_materialization.v1",
        "scope": "candidate_pool_action_time_lane_non_executing_prepare",
        "candidate_pool_json": str(candidate_pool_json),
        "report_dir": str(report_dir),
        "authority_boundary": (
            "non_executing_prepare_only; no_finalgate_no_operation_layer_no_exchange_write"
        ),
        "safety_invariants": {
            "uses_official_trading_console_api": True,
            "allow_prepare_records": bool(args.allow_prepare_records),
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "withdrawal_or_transfer_created": False,
        },
    }
    if selection is None:
        conditional_rehearsal_only = (
            len(blockers) == 1
            and blockers[0].startswith(
                "action_time_lane_scope_not_live_submit:"
            )
            and blockers[0].rsplit(":", 1)[-1] in CONDITIONAL_REHEARSAL_SCOPE_STATES
        )
        if not blockers:
            status = "no_action_time_lane_input"
        elif conditional_rehearsal_only:
            status = "no_live_submit_action_time_lane_input"
        else:
            status = "blocked"
        payload = {
            **base,
            "status": status,
            "blockers": blockers,
            "lane": None,
            "signal_input_json": None,
            "shadow_candidate_id": None,
            "prepared_authorization_id": None,
        }
        _write_json(output_json, payload)
        return payload

    materialization_dir = Path(args.materialization_dir).expanduser()
    signal_path = (
        materialization_dir
        / f"{_safe_file_id(selection.runtime_instance_id)}-signal-input.json"
    )
    prepare_args = _prepare_args(
        args,
        selection=selection,
        signal_input_json=signal_path,
    )
    prepare_builder = prepare_builder or prepare_flow._build_artifact
    prepare_artifact = prepare_builder(prepare_args)
    ids = _ids_from_prepare(prepare_artifact)
    signal_input_json = _first_text(prepare_artifact.get("signal_input_json"), signal_path)
    prepared_authorization_id = ids["prepared_authorization_id"]
    shadow_candidate_id = ids["shadow_candidate_id"]
    if (
        prepare_artifact.get("status") != READY_PREPARE_STATUS
        or not signal_input_json
        or not prepared_authorization_id
    ):
        payload = {
            **base,
            "status": "blocked",
            "blockers": list(prepare_artifact.get("blockers") or [])
            or ["prepare_artifact_not_ready_for_finalgate_preflight"],
            "lane": selection.lane,
            "runtime_instance_id": selection.runtime_instance_id,
            "prepare_artifact": prepare_artifact,
            "signal_input_json": signal_input_json,
            "shadow_candidate_id": shadow_candidate_id,
            "prepared_authorization_id": prepared_authorization_id,
        }
        _write_json(output_json, payload)
        return payload

    status_artifact = _patch_status_artifacts(
        report_dir=report_dir,
        selection=selection,
        prepare_artifact=prepare_artifact,
        signal_input_json=str(signal_input_json),
        prepared_authorization_id=str(prepared_authorization_id),
        shadow_candidate_id=shadow_candidate_id,
    )
    operator, wakeup = _refresh_operator_and_wakeup(
        report_dir=report_dir,
        strategy_source=args.source,
    )
    payload = {
        **base,
        "status": "ready_for_action_time_final_gate",
        "blockers": [],
        "lane": selection.lane,
        "runtime_instance_id": selection.runtime_instance_id,
        "strategy_group_id": selection.strategy_group_id,
        "symbol": selection.symbol,
        "side": selection.side,
        "prepare_artifact": prepare_artifact,
        "status_artifact_status": status_artifact.get("status"),
        "operator_status": operator.get("status"),
        "wakeup_status": wakeup.get("status"),
        "signal_input_json": signal_input_json,
        "shadow_candidate_id": shadow_candidate_id,
        "prepared_authorization_id": prepared_authorization_id,
    }
    _write_json(output_json, payload)
    return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-pool-json", default=str(DEFAULT_CANDIDATE_POOL_JSON))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--materialization-dir")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--source", choices=["live_market", "sample"], default="live_market")
    parser.add_argument("--one-hour-limit", type=int, default=25)
    parser.add_argument("--four-hour-limit", type=int, default=25)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--allow-prepare-records", action="store_true")
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--owner-confirmation-reference",
        default="owner-authorized-candidate-pool-action-time-lane-materialization",
    )
    args = parser.parse_args(argv)
    if not args.materialization_dir:
        args.materialization_dir = str(Path(args.report_dir) / "action-time-lane-materialization")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = materialize_action_time_lane(
        candidate_pool_json=Path(args.candidate_pool_json).expanduser(),
        report_dir=Path(args.report_dir).expanduser(),
        output_json=Path(args.output_json).expanduser(),
        args=args,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    if payload["status"] in {
        "no_action_time_lane_input",
        "no_live_submit_action_time_lane_input",
        "ready_for_action_time_final_gate",
    }:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
