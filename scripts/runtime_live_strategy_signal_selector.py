#!/usr/bin/env python3
"""Select a runtime-compatible live strategy signal input.

RTF-034 bridges the broad read-only strategy shelf back into the runtime
next-attempt loop. It scans current strategy-group observations, selects only a
``would_enter`` signal that exactly matches the target runtime profile, and can
write the matching ``StrategyFamilySignalInput`` JSON for the existing
full-cycle script.

It never mutates PG, changes runtime profile, creates candidates, creates
ExecutionIntents, creates orders, calls OrderLifecycle, writes to exchange,
opens/closes positions, transfers funds, or creates withdrawals.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.build_runtime_strategy_signal_input_packet import (  # noqa: E402
    _load_env_file,
    _load_runtime,
)
from scripts.preview_strategy_group_readonly_observation import (  # noqa: E402
    SourceName,
    build_preview_packet,
)


PreviewBuilder = Callable[..., dict[str, Any]]


def _runtime_value(runtime: Any, name: str) -> Any:
    value = getattr(runtime, name, None)
    if hasattr(value, "value"):
        return value.value
    return value


def _runtime_profile(runtime: Any) -> dict[str, Any]:
    return {
        "runtime_instance_id": _runtime_value(runtime, "runtime_instance_id"),
        "strategy_family_id": _runtime_value(runtime, "strategy_family_id"),
        "strategy_family_version_id": _runtime_value(
            runtime,
            "strategy_family_version_id",
        ),
        "symbol": _runtime_value(runtime, "symbol"),
        "side": _runtime_value(runtime, "side"),
        "status": _runtime_value(runtime, "status"),
        "execution_enabled": bool(_runtime_value(runtime, "execution_enabled")),
        "shadow_mode": bool(_runtime_value(runtime, "shadow_mode")),
    }


def _current_signal_rows(preview_packet: dict[str, Any]) -> list[dict[str, Any]]:
    preview = preview_packet.get("preview") or {}
    rows = preview.get("current_signals") or []
    return [row for row in rows if isinstance(row, dict)]


def _signal_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row.get("candidate_id"),
        "strategy_family_id": row.get("strategy_group_id"),
        "strategy_family_version_id": row.get("strategy_family_version_id"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "signal_type": row.get("signal_type"),
        "confidence": row.get("confidence"),
        "reason_codes": list(row.get("reason_codes") or []),
        "human_summary": row.get("human_summary"),
        "market_bar_timestamp_ms": row.get("market_bar_timestamp_ms"),
        "not_order": row.get("not_order"),
        "not_execution_intent": row.get("not_execution_intent"),
        "no_execution_permission": row.get("no_execution_permission"),
        "no_order_permission": row.get("no_order_permission"),
        "no_runtime_start": row.get("no_runtime_start"),
    }


def _compatibility_blockers(row: dict[str, Any], runtime_profile: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if row.get("signal_type") != "would_enter":
        blockers.append("strategy_signal_not_would_enter")
    if row.get("strategy_group_id") != runtime_profile["strategy_family_id"]:
        blockers.append("runtime_strategy_family_mismatch")
    if row.get("strategy_family_version_id") != runtime_profile["strategy_family_version_id"]:
        blockers.append("runtime_strategy_family_version_mismatch")
    if row.get("symbol") != runtime_profile["symbol"]:
        blockers.append("runtime_symbol_mismatch")
    if row.get("side") != runtime_profile["side"]:
        blockers.append("runtime_side_mismatch")
    if row.get("not_order") is not True:
        blockers.append("signal_record_not_order_flag_missing")
    if row.get("not_execution_intent") is not True:
        blockers.append("signal_record_not_execution_intent_flag_missing")
    if not isinstance(row.get("signal_input_snapshot"), dict):
        blockers.append("signal_input_snapshot_missing")
    return sorted(dict.fromkeys(blockers))


def _select_row(
    *,
    rows: list[dict[str, Any]],
    runtime_profile: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any] | None]:
    inspected: list[dict[str, Any]] = []
    runtime_current: dict[str, Any] | None = None
    selected: dict[str, Any] | None = None

    for row in rows:
        blockers = _compatibility_blockers(row, runtime_profile)
        summary = {
            **_signal_summary(row),
            "runtime_compatibility_blockers": blockers,
            "runtime_compatible": not blockers,
        }
        inspected.append(summary)
        same_runtime_shape = (
            row.get("strategy_group_id") == runtime_profile["strategy_family_id"]
            and row.get("strategy_family_version_id")
            == runtime_profile["strategy_family_version_id"]
            and row.get("symbol") == runtime_profile["symbol"]
            and row.get("side") == runtime_profile["side"]
        )
        if same_runtime_shape:
            runtime_current = summary
        if not blockers and selected is None:
            selected = row

    return selected, inspected, runtime_current


def _write_signal_input(path: str | None, selected_row: dict[str, Any] | None) -> str | None:
    if not path or selected_row is None:
        return None
    signal_input = selected_row.get("signal_input_snapshot")
    if not isinstance(signal_input, dict):
        return None
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(signal_input, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(output_path)


def _safety_invariants() -> dict[str, bool]:
    return {
        "read_only_market_scan": True,
        "database_write": False,
        "runtime_profile_mutated": False,
        "signal_evaluation_created": False,
        "order_candidate_created": False,
        "execution_intent_created": False,
        "executable_execution_intent_created": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "exchange_write_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _status(
    *,
    selected: dict[str, Any] | None,
    non_runtime_would_enter_count: int,
    runtime_current_signal: dict[str, Any] | None,
) -> str:
    if selected is not None:
        return "runtime_compatible_would_enter_selected"
    if non_runtime_would_enter_count:
        return "would_enter_available_but_not_runtime_compatible"
    if runtime_current_signal is not None:
        return "runtime_signal_observe_only"
    return "no_would_enter_signal_available"


def _operator_next_step(status: str) -> str:
    if status == "runtime_compatible_would_enter_selected":
        return "run_runtime_full_next_attempt_submit_cycle_with_selected_signal_input"
    if status == "would_enter_available_but_not_runtime_compatible":
        return "owner_confirm_new_runtime_or_profile_change_before_using_non_runtime_signal"
    if status == "runtime_signal_observe_only":
        return "continue_runtime_observation_or_wait_for_next_closed_bar"
    return "continue_strategy_shelf_scan_or_wait_for_next_closed_bar"


def _build_packet_from_preview(
    *,
    runtime: Any,
    preview_packet: dict[str, Any],
    output_signal_input_json: str | None = None,
) -> dict[str, Any]:
    runtime_profile = _runtime_profile(runtime)
    rows = _current_signal_rows(preview_packet)
    selected, inspected, runtime_current_signal = _select_row(
        rows=rows,
        runtime_profile=runtime_profile,
    )
    non_runtime_would_enter = [
        row
        for row in inspected
        if row["signal_type"] == "would_enter" and not row["runtime_compatible"]
    ]
    output_path = _write_signal_input(output_signal_input_json, selected)
    status = _status(
        selected=selected,
        non_runtime_would_enter_count=len(non_runtime_would_enter),
        runtime_current_signal=runtime_current_signal,
    )
    blockers: list[str] = []
    if selected is None:
        if non_runtime_would_enter:
            blockers.append("would_enter_signals_not_runtime_compatible")
        elif runtime_current_signal is not None:
            blockers.append("runtime_strategy_signal_not_would_enter")
        else:
            blockers.append("runtime_strategy_signal_not_found_in_strategy_shelf")

    return {
        "scope": "runtime_live_strategy_signal_selector",
        "status": status,
        "runtime_instance_id": runtime_profile["runtime_instance_id"],
        "runtime_profile": runtime_profile,
        "source_requested": preview_packet.get("source_requested"),
        "market_source": preview_packet.get("market_source"),
        "preview_checks": preview_packet.get("checks") or {},
        "selected_signal": _signal_summary(selected) if selected is not None else None,
        "runtime_current_signal": runtime_current_signal,
        "non_runtime_would_enter_signals": non_runtime_would_enter,
        "inspected_signal_count": len(inspected),
        "output_signal_input_json": output_path,
        "blockers": blockers,
        "warnings": [
            "selector_does_not_change_runtime_profile",
            "strategy_alpha_not_proven_warning_not_execution_blocker",
        ],
        "operator_command_plan": {
            "next_step": _operator_next_step(status),
            "signal_input_json": output_path,
            "records_observation": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_owner_runtime_profile_confirmation": (
                status == "would_enter_available_but_not_runtime_compatible"
            ),
        },
        "safety_invariants": _safety_invariants(),
    }


async def _build_packet(
    args: argparse.Namespace,
    *,
    preview_builder: PreviewBuilder = build_preview_packet,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    runtime = await _load_runtime(args.runtime_instance_id)
    preview_packet = preview_builder(source_name=args.source)
    return _build_packet_from_preview(
        runtime=runtime,
        preview_packet=preview_packet,
        output_signal_input_json=args.output_signal_input_json,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select a runtime-compatible live strategy signal input.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--env-file")
    parser.add_argument(
        "--source",
        choices=["sample", "local_sqlite_fallback", "live_market"],
        default="live_market",
    )
    parser.add_argument("--output-signal-input-json")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = asyncio.run(_build_packet(args))
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if packet["status"] == "runtime_compatible_would_enter_selected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
