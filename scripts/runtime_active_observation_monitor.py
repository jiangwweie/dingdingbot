#!/usr/bin/env python3
"""Monitor all active strategy runtimes without submitting orders.

This is an operator wrapper around ``runtime_next_attempt_observation_monitor``.
It discovers ACTIVE runtimes from the Trading Console API, runs the existing
per-runtime monitor for each one, and writes an auditable aggregate packet.

By default it is observe-only. With ``--allow-prepare-records`` it may create
shadow SignalEvaluation / shadow OrderCandidate / prepare authorization records
only when a real strategy signal is ready for prepare. It never arms local
registration, arms exchange submit, calls OrderLifecycle, submits orders, or
moves funds.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    API_BASE_ENV as FIRST_REAL_SUBMIT_API_BASE_ENV,
    DEFAULT_API_BASE,
    UrlLibApiClient,
)
from scripts import runtime_next_attempt_observation_api_prepare_flow as observation_flow  # noqa: E402
from scripts import runtime_next_attempt_observation_monitor as monitor  # noqa: E402


MAX_OBSERVATION_API_TIMEOUT_SECONDS = 60.0
NON_ACTIONABLE_OBSERVATION_BLOCKERS = {
    "runtime_attempts_exhausted",
    "order_candidate_id_or_authorization_id_required",
}
OBSERVE_ONLY_REVIEW_BLOCKERS = {
    "strategy_stop_reference_unavailable",
}
WAITING_FOR_SIGNAL_BLOCKERS = {
    "strategy_signal_not_ready_for_shadow_candidate_prepare",
}


def _api_base(args: argparse.Namespace) -> str:
    import os

    return (
        args.api_base
        or os.environ.get(observation_flow.API_BASE_ENV)
        or os.environ.get(FIRST_REAL_SUBMIT_API_BASE_ENV)
        or DEFAULT_API_BASE
    )


def _effective_observation_timeout_seconds(args: argparse.Namespace) -> float:
    timeout = float(args.timeout_seconds or 10.0)
    return min(timeout, MAX_OBSERVATION_API_TIMEOUT_SECONDS)


def _active_runtimes(*, client: Any) -> list[dict[str, Any]]:
    response = client.request_json("GET", "/api/trading-console/strategy-runtimes")
    body = response.get("body")
    if response.get("http_status", 0) >= 300 or response.get("error"):
        raise RuntimeError(f"strategy_runtimes_http_{response.get('http_status')}")
    items = body if isinstance(body, list) else (body or {}).get("items", [])
    if not isinstance(items, list):
        raise RuntimeError("strategy_runtimes_response_not_list")
    return [
        item
        for item in items
        if isinstance(item, dict) and str(item.get("status") or "").lower() == "active"
    ]


def _selected_active_runtimes(
    active: list[dict[str, Any]],
    *,
    runtime_instance_ids: list[str] | None,
    strategy_family_ids: list[str] | None,
    max_runtimes: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    requested = [
        str(item).strip()
        for item in (runtime_instance_ids or [])
        if str(item or "").strip()
    ]
    requested_families = {
        str(item).strip()
        for item in (strategy_family_ids or [])
        if str(item or "").strip()
    }
    if requested_families:
        active = [
            runtime
            for runtime in active
            if str(_runtime_value(runtime, "strategy_family_id", "family") or "")
            in requested_families
        ]
    if not requested:
        return active[: max(max_runtimes, 0)], []

    requested_set = set(requested)
    selected = [
        runtime
        for runtime in active
        if str(_runtime_value(runtime, "runtime_instance_id", "runtime_id") or "")
        in requested_set
    ]
    found = {
        str(_runtime_value(runtime, "runtime_instance_id", "runtime_id") or "")
        for runtime in selected
    }
    missing = [runtime_id for runtime_id in requested if runtime_id not in found]
    return selected[: max(max_runtimes, 0)], missing


def _runtime_value(runtime: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = runtime.get(key)
        if value is not None and value != "":
            return value
    return None


def _monitor_args(args: argparse.Namespace, runtime: dict[str, Any]) -> argparse.Namespace:
    runtime_instance_id = str(_runtime_value(runtime, "runtime_instance_id", "runtime_id") or "")
    symbol = _runtime_value(runtime, "symbol")
    side = _runtime_value(runtime, "side")
    strategy_family_id = _runtime_value(runtime, "strategy_family_id", "family")
    carrier_id = _runtime_value(
        runtime,
        "carrier_id",
        "strategy_family_version_id",
        "strategy_family_id",
    )
    return argparse.Namespace(
        runtime_instance_id=runtime_instance_id,
        env_file=args.env_file,
        api_base=_api_base(args),
        source=args.source,
        include_exchange=args.include_exchange,
        symbol=symbol,
        side=side,
        family=strategy_family_id,
        strategy_family_id=strategy_family_id,
        carrier_id=carrier_id,
        quantity=None,
        target_notional_usdt=None,
        max_notional=None,
        leverage=None,
        max_attempts=None,
        protection_mode=None,
        review_requirement=None,
        evaluation_id=None,
        playbook_id=args.playbook_id,
        one_hour_limit=args.one_hour_limit,
        four_hour_limit=args.four_hour_limit,
        timeout_seconds=_effective_observation_timeout_seconds(args),
        signal_output_json=None,
        output_dir=str(Path(args.output_dir).expanduser() / runtime_instance_id),
        allow_prepare_records=args.allow_prepare_records,
        candidate_id=None,
        context_id=None,
        owner_operator_id=args.owner_operator_id,
        owner_confirmation_reference=args.owner_confirmation_reference,
        reason=args.reason,
        next_attempt_symbol=symbol,
        next_attempt_side=side,
        next_attempt_family=strategy_family_id,
        next_attempt_strategy_family_id=strategy_family_id,
        next_attempt_carrier_id=carrier_id,
        max_cycles=args.max_cycles_per_runtime,
        interval_seconds=args.interval_seconds,
        continue_on_blocked=args.continue_on_blocked,
        output_json=str(
            Path(args.output_dir).expanduser()
            / runtime_instance_id
            / "monitor-packet.json"
        ),
    )


def _signal_summary(packet: dict[str, Any]) -> dict[str, Any]:
    latest_packet = packet.get("latest_packet")
    if not isinstance(latest_packet, dict):
        latest_packet = packet
    observation_payload = latest_packet.get("observation_payload")
    if not isinstance(observation_payload, dict):
        observation_payload = {}
    signal_packet = observation_payload.get("signal_packet")
    if not isinstance(signal_packet, dict):
        signal_packet = latest_packet.get("signal_packet")
    if not isinstance(signal_packet, dict):
        signal_packet = {}
    evaluation = signal_packet.get("evaluation_result")
    if not isinstance(evaluation, dict):
        evaluation = {}
    output = evaluation.get("output")
    if not isinstance(output, dict):
        output = {}
    signal_snapshot = output.get("signal_snapshot")
    if not isinstance(signal_snapshot, dict):
        signal_snapshot = {}
    context_tags = signal_snapshot.get("context_tags")
    if not isinstance(context_tags, dict):
        context_tags = {}
    data_quality = output.get("data_quality")
    if not isinstance(data_quality, dict):
        data_quality = {}
    return {
        "evaluation_status": evaluation.get("status"),
        "evaluator_id": evaluation.get("evaluator_id"),
        "signal_type": output.get("signal_type"),
        "required_execution_mode": output.get("required_execution_mode"),
        "side": output.get("side"),
        "reason_codes": list(output.get("reason_codes") or []),
        "human_summary": output.get("human_summary"),
        "confidence": output.get("confidence"),
        "data_quality_status": data_quality.get("status"),
        "context_tags": context_tags,
        "can_call_semantic_binding": evaluation.get("can_call_semantic_binding"),
        "semantics_binding_found": evaluation.get("semantics_binding_found"),
        "strategy_candidate_mode": evaluation.get("strategy_candidate_mode"),
        "timestamp_ms": output.get("timestamp_ms"),
    }


def _summary(runtime: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    return {
        "runtime_instance_id": _runtime_value(runtime, "runtime_instance_id", "runtime_id"),
        "status": packet.get("status"),
        "symbol": _runtime_value(runtime, "symbol"),
        "side": _runtime_value(runtime, "side"),
        "strategy_family_id": _runtime_value(runtime, "strategy_family_id", "family"),
        "strategy_family_version_id": _runtime_value(
            runtime,
            "strategy_family_version_id",
            "carrier_id",
        ),
        "ready_for_prepare": packet.get("ready_for_prepare"),
        "ready_for_final_gate_preflight": packet.get(
            "ready_for_final_gate_preflight"
        ),
        "blockers": list(packet.get("blockers") or []),
        "warnings": list(packet.get("warnings") or []),
        "report_path": (
            (packet.get("operator_command_plan") or {}).get("report_path")
            or packet.get("output_json")
        ),
        "signal_input_json": (packet.get("operator_command_plan") or {}).get(
            "signal_input_json"
        ),
        "prepared_authorization_id": (
            packet.get("operator_command_plan") or {}
        ).get("prepared_authorization_id"),
        "signal_summary": _signal_summary(packet),
        "prepare_records_created": bool(safety.get("prepare_records_created")),
        "created_records": {
            "shadow_candidate_created": bool(safety.get("shadow_candidate_created")),
            "runtime_execution_intent_draft_created": bool(
                safety.get("runtime_execution_intent_draft_created")
            ),
            "recorded_execution_intent_created": bool(
                safety.get("recorded_execution_intent_created")
            ),
            "submit_authorization_created": bool(
                safety.get("submit_authorization_created")
            ),
            "protection_plan_created": bool(safety.get("protection_plan_created")),
            "executable_execution_intent_created": bool(
                safety.get("executable_execution_intent_created")
            ),
        },
        "forbidden_effects": {
            "exchange_write_called": bool(safety.get("exchange_write_called")),
            "order_created": bool(safety.get("order_created")),
            "order_lifecycle_called": bool(safety.get("order_lifecycle_called")),
            "attempt_counter_mutated": bool(safety.get("attempt_counter_mutated")),
            "runtime_budget_mutated": bool(safety.get("runtime_budget_mutated")),
            "withdrawal_or_transfer_created": bool(
                safety.get("withdrawal_or_transfer_created")
            ),
        },
    }


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _safety(
    *,
    allow_prepare_records: bool,
    packets: list[dict[str, Any]],
) -> dict[str, Any]:
    def any_flag(name: str) -> bool:
        return any(bool((packet.get("safety_invariants") or {}).get(name)) for packet in packets)

    return {
        "uses_official_trading_console_api": True,
        "monitors_active_runtimes": True,
        "allow_prepare_records": allow_prepare_records,
        "prepare_records_created": any_flag("prepare_records_created"),
        "shadow_candidate_created": any_flag("shadow_candidate_created"),
        "runtime_execution_intent_draft_created": any_flag(
            "runtime_execution_intent_draft_created"
        ),
        "recorded_execution_intent_created": any_flag(
            "recorded_execution_intent_created"
        ),
        "submit_authorization_created": any_flag("submit_authorization_created"),
        "protection_plan_created": any_flag("protection_plan_created"),
        "executable_execution_intent_created": any_flag(
            "executable_execution_intent_created"
        ),
        "local_registration_armed": any_flag("local_registration_armed"),
        "exchange_submit_armed": any_flag("exchange_submit_armed"),
        "execute_real_submit": any_flag("execute_real_submit"),
        "exchange_write_called": any_flag("exchange_write_called"),
        "order_created": any_flag("order_created"),
        "order_lifecycle_called": any_flag("order_lifecycle_called"),
        "attempt_counter_mutated": any_flag("attempt_counter_mutated"),
        "runtime_budget_mutated": any_flag("runtime_budget_mutated"),
        "position_opened": any_flag("position_opened"),
        "position_closed": any_flag("position_closed"),
        "withdrawal_or_transfer_created": any_flag("withdrawal_or_transfer_created"),
    }


def _overall_status(packets: list[dict[str, Any]]) -> str:
    statuses = {str(packet.get("status") or "unknown") for packet in packets}
    if not packets:
        return "no_active_runtimes"
    if "ready_for_final_gate_preflight" in statuses:
        return "ready_for_final_gate_preflight"
    if "ready_for_prepare" in statuses:
        return "ready_for_prepare"
    if statuses == {"waiting_for_signal"}:
        return "waiting_for_signal"
    if "blocked" in statuses:
        return "blocked"
    return "mixed"


def _build_packet(
    args: argparse.Namespace,
    *,
    client: Any | None = None,
    monitor_builder: Callable[[argparse.Namespace], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    observation_flow._load_env_file(args.env_file)
    api_client = client or UrlLibApiClient(api_base=_api_base(args))
    builder = monitor_builder or monitor._build_monitor_packet
    active = _active_runtimes(client=api_client)
    requested_runtime_instance_ids = list(
        getattr(args, "runtime_instance_id", None) or []
    )
    requested_strategy_family_ids = list(
        getattr(args, "strategy_family_id", None) or []
    )
    selected, missing_runtime_instance_ids = _selected_active_runtimes(
        active,
        runtime_instance_ids=requested_runtime_instance_ids,
        strategy_family_ids=requested_strategy_family_ids,
        max_runtimes=int(args.max_runtimes or 100),
    )

    packets: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for runtime in selected:
        runtime_args = _monitor_args(args, runtime)
        packet = builder(runtime_args)
        packet = _downgrade_non_actionable_observation_blockers(packet)
        packet["runtime_instance_id"] = runtime_args.runtime_instance_id
        packet["output_json"] = runtime_args.output_json
        _write_json(runtime_args.output_json, packet)
        packets.append(packet)
        summaries.append(_summary(runtime, packet))

    status = _overall_status(packets)
    blockers: list[str] = []
    for item in summaries:
        for blocker in item["blockers"]:
            if _is_waiting_for_signal_blocker(
                status=str(item.get("status") or ""),
                blocker=str(blocker),
            ):
                continue
            scoped = f"{item['runtime_instance_id']}:{blocker}"
            if scoped not in blockers:
                blockers.append(scoped)
    warnings: list[str] = []
    for runtime_id in missing_runtime_instance_ids:
        warnings.append(f"requested_runtime_not_active_or_not_found:{runtime_id}")
    effective_timeout = _effective_observation_timeout_seconds(args)
    if float(args.timeout_seconds or 10.0) != effective_timeout:
        warnings.append(
            "observation_timeout_seconds_clamped_to_api_max_60"
        )

    return {
        "scope": "runtime_active_observation_monitor",
        "status": status,
        "active_runtime_count": len(active),
        "monitored_runtime_count": len(selected),
        "requested_runtime_instance_ids": requested_runtime_instance_ids,
        "requested_strategy_family_ids": requested_strategy_family_ids,
        "selected_runtime_instance_ids": [
            str(_runtime_value(runtime, "runtime_instance_id", "runtime_id") or "")
            for runtime in selected
        ],
        "allow_prepare_records": args.allow_prepare_records,
        "max_cycles_per_runtime": args.max_cycles_per_runtime,
        "requested_timeout_seconds": args.timeout_seconds,
        "effective_observation_timeout_seconds": effective_timeout,
        "runtime_summaries": summaries,
        "runtime_packets": packets if args.include_runtime_packets else [],
        "blockers": blockers,
        "warnings": warnings,
        "operator_command_plan": {
            "next_step": _next_step(status),
            "not_executed": True,
            "creates_shadow_candidate": any(
                bool((packet.get("safety_invariants") or {}).get("prepare_records_created"))
                for packet in packets
            ),
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_official_final_gate": True,
            "uses_standing_runtime_authorization": True,
            "requires_official_operation_layer": True,
        },
        "safety_invariants": _safety(
            allow_prepare_records=args.allow_prepare_records,
            packets=packets,
        ),
    }


def _next_step(status: str) -> str:
    if status == "ready_for_final_gate_preflight":
        return "run_official_final_gate_preflight_for_prepared_authorization"
    if status == "ready_for_prepare":
        return "rerun_active_monitor_with_allow_prepare_records_under_standing_authorization"
    if status == "blocked":
        return "resolve_runtime_observation_blockers"
    if status == "no_active_runtimes":
        return "start_or_authorize_a_runtime_before_monitoring"
    return "wait_for_next_observation_cycle"


def _downgrade_non_actionable_observation_blockers(
    packet: dict[str, Any],
) -> dict[str, Any]:
    if str(packet.get("status") or "") != "blocked":
        return packet
    blockers = [str(blocker) for blocker in packet.get("blockers") or []]
    if not blockers:
        return packet
    observation_only = _is_observe_only_review_packet(packet)
    allowed_blockers = set(NON_ACTIONABLE_OBSERVATION_BLOCKERS)
    if observation_only:
        allowed_blockers.update(OBSERVE_ONLY_REVIEW_BLOCKERS)
    if any(blocker not in allowed_blockers for blocker in blockers):
        return packet
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    if any(
        bool(safety.get(flag))
        for flag in (
            "submit_authorization_created",
            "protection_plan_created",
            "executable_execution_intent_created",
            "local_registration_armed",
            "exchange_submit_armed",
            "execute_real_submit",
            "exchange_write_called",
            "order_created",
            "order_lifecycle_called",
            "attempt_counter_mutated",
            "runtime_budget_mutated",
            "position_opened",
            "position_closed",
            "withdrawal_or_transfer_created",
        )
    ):
        return packet

    downgraded = dict(packet)
    downgraded["status"] = "waiting_for_signal"
    downgraded["blockers"] = []
    downgraded["warnings"] = sorted(
        {
            *[str(warning) for warning in packet.get("warnings") or []],
            *[
                f"non_actionable_observation_blocker:{blocker}"
                for blocker in blockers
            ],
        }
    )
    plan = dict(packet.get("operator_command_plan") or {})
    plan["next_step"] = "continue_waiting_for_strategy_signal"
    plan["not_executed"] = True
    plan["places_order"] = False
    plan["calls_order_lifecycle"] = False
    downgraded["operator_command_plan"] = plan
    downgraded["non_actionable_observation_blockers"] = blockers
    return downgraded


def _is_observe_only_review_packet(packet: dict[str, Any]) -> bool:
    summary = _signal_summary(packet)
    return str(summary.get("required_execution_mode") or "") == "observe_only"


def _is_waiting_for_signal_blocker(*, status: str, blocker: str) -> bool:
    return (
        status == "waiting_for_signal"
        and blocker in WAITING_FOR_SIGNAL_BLOCKERS
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor all ACTIVE strategy runtimes without live submit.",
    )
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--source", choices=["live_market", "sample"], default="live_market")
    parser.add_argument("--include-exchange", action="store_true", default=False)
    parser.add_argument("--allow-prepare-records", action="store_true", default=False)
    parser.add_argument(
        "--runtime-instance-id",
        action="append",
        default=[],
        help=(
            "Limit monitoring to the given ACTIVE runtime instance. "
            "May be repeated."
        ),
    )
    parser.add_argument(
        "--strategy-family-id",
        action="append",
        default=[],
        help=(
            "Limit monitoring to ACTIVE runtimes belonging to this strategy "
            "family. May be repeated."
        ),
    )
    parser.add_argument("--max-runtimes", type=int, default=100)
    parser.add_argument("--max-cycles-per-runtime", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--continue-on-blocked", action="store_true", default=False)
    parser.add_argument("--one-hour-limit", type=int, default=25)
    parser.add_argument("--four-hour-limit", type=int, default=25)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--playbook-id")
    parser.add_argument(
        "--output-dir",
        default="output/runtime-active-observation-monitor",
    )
    parser.add_argument("--output-json")
    parser.add_argument("--include-runtime-packets", action="store_true", default=False)
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--owner-confirmation-reference",
        default="owner-authorized-active-runtime-observation-monitor",
    )
    parser.add_argument(
        "--reason",
        default="owner authorized active runtime observation monitor",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        packet = _build_packet(args)
    output = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        _write_json(args.output_json, packet)
    print(output)
    return 0 if packet["status"] in {
        "waiting_for_signal",
        "ready_for_prepare",
        "ready_for_final_gate_preflight",
        "no_active_runtimes",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
