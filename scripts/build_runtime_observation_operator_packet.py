#!/usr/bin/env python3
"""Build a read-only operator packet for active runtime observation.

The packet joins:

1. An active runtime observation status packet.
2. A runtime + strategy signal watch packet.
3. A no-signal diagnostic packet when applicable.

It does not write PG rows, resolve runtimes, create shadow candidates, create
ExecutionIntents, place orders, call OrderLifecycle, or mutate runtime state.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_runtime_no_signal_diagnostic_packet import (  # noqa: E402
    build_no_signal_diagnostic_packet,
)
from scripts.build_runtime_strategy_signal_watch_packet import (  # noqa: E402
    SourceName,
    build_watch_packet,
)
from scripts.preview_strategy_group_readonly_observation import (  # noqa: E402
    build_preview_packet,
)


def build_operator_packet(
    *,
    active_status_packet: dict[str, Any],
    strategy_preview_packet: dict[str, Any],
) -> dict[str, Any]:
    watch_packet = build_watch_packet(
        active_status_packet=active_status_packet,
        strategy_preview_packet=strategy_preview_packet,
    )
    diagnostic_packet = build_no_signal_diagnostic_packet(watch_packet)
    forbidden_effects = _forbidden_effects(watch_packet, diagnostic_packet)
    watch_status = str(watch_packet.get("status") or "unknown")
    diagnostic_status = str(diagnostic_packet.get("status") or "unknown")

    status = "blocked_forbidden_effect"
    next_step = "resolve_operator_packet_forbidden_effects"
    if not forbidden_effects:
        if watch_status in {
            "runtime_signal_ready",
            "runtime_prepare_records_ready_for_preview",
        }:
            status = "runtime_signal_attention"
            next_step = "review_runtime_ready_signal_prepare_or_preview_path"
        elif watch_status == "strategy_group_signal_review_available":
            status = "strategy_group_signal_review_available"
            next_step = "review_strategy_group_would_enter_without_execution"
        elif diagnostic_status == "no_signal_window_complete":
            status = "no_signal_window_complete"
            next_step = "review_no_signal_diagnostic_before_new_window"
        elif diagnostic_status == "no_signal_observation_running":
            status = "observation_running_no_signal"
            next_step = "continue_active_runtime_observation"
        else:
            status = "operator_review"
            next_step = "review_observation_operator_packet"

    return {
        "scope": "runtime_observation_operator_packet",
        "status": status,
        "watch_status": watch_status,
        "diagnostic_status": diagnostic_status,
        "active_runtime_observation": watch_packet.get("active_runtime_observation"),
        "signal_counts": (diagnostic_packet.get("signal_counts") or {}),
        "coverage": (diagnostic_packet.get("coverage") or {}),
        "no_action_diagnostics": (
            diagnostic_packet.get("no_action_diagnostics") or {}
        ),
        "runtime_prepare_context": watch_packet.get("runtime_prepare_context") or {},
        "operator_command_plan": {
            "not_executed": True,
            "next_step": next_step,
            "allowed_next_actions": _allowed_next_actions(
                status=status,
                watch_packet=watch_packet,
                diagnostic_packet=diagnostic_packet,
            ),
            "records_observation": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "withdrawal_or_transfer_requested": False,
        },
        "owner_gate": {
            "operator_review_only": True,
            "does_not_authorize": [
                "real runtime submit",
                "exchange order placement",
                "OrderLifecycle submit",
                "executable ExecutionIntent",
                "withdrawal or transfer",
            ],
        },
        "right_tail_objective_context": {
            "no_signal_is_not_failure": True,
            "small_bounded_losses_allowed_when_runtime_ready": True,
            "forcing_entry_without_signal_forbidden": True,
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
        },
        "watch_packet": watch_packet,
        "no_signal_diagnostic_packet": diagnostic_packet,
        "safety_invariants": {
            "operator_packet_only": True,
            "status_packet_read_only": True,
            "strategy_preview_only": True,
            "pg_observation_written": False,
            "runtime_resolver_called": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effects": forbidden_effects,
        },
    }


def build_operator_packet_from_path(
    *,
    status_packet_json: str | Path,
    strategy_source: SourceName,
) -> dict[str, Any]:
    active_status = _load_json_object(Path(status_packet_json).expanduser())
    preview = build_preview_packet(source_name=strategy_source)
    return build_operator_packet(
        active_status_packet=active_status,
        strategy_preview_packet=preview,
    )


def _allowed_next_actions(
    *,
    status: str,
    watch_packet: dict[str, Any],
    diagnostic_packet: dict[str, Any],
) -> list[str]:
    if status == "runtime_signal_attention":
        return list(
            (watch_packet.get("operator_command_plan") or {}).get(
                "allowed_next_actions"
            )
            or ["review_runtime_ready_signal_prepare_or_preview_path"]
        )
    if status == "strategy_group_signal_review_available":
        return ["review_strategy_group_would_enter_without_execution"]
    if status in {"observation_running_no_signal", "no_signal_window_complete"}:
        return list(
            (diagnostic_packet.get("operator_command_plan") or {}).get(
                "allowed_next_actions"
            )
            or ["continue_active_runtime_observation"]
        )
    return ["review_observation_operator_packet"]


def _forbidden_effects(*packets: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    for index, packet in enumerate(packets):
        checks = packet.get("checks") if isinstance(packet.get("checks"), dict) else {}
        effects.extend(f"packet_{index}.{item}" for item in checks.get("forbidden_effects") or [])
        safety = (
            packet.get("safety_invariants")
            if isinstance(packet.get("safety_invariants"), dict)
            else {}
        )
        for item in safety.get("forbidden_effects") or []:
            effects.append(f"packet_{index}.{item}")
        for item in safety.get("source_forbidden_effects") or []:
            effects.append(f"packet_{index}.source.{item}")
        for key in (
            "shadow_candidate_created",
            "execution_intent_created",
            "order_created",
            "order_lifecycle_called",
            "exchange_write_called",
            "attempt_counter_mutated",
            "runtime_budget_mutated",
            "withdrawal_or_transfer_created",
        ):
            if safety.get(key) is True:
                effects.append(f"packet_{index}.{key}")
    return sorted(set(str(item) for item in effects if item))


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-packet-json", required=True)
    parser.add_argument(
        "--strategy-source",
        choices=["sample", "local_sqlite_fallback", "live_market"],
        default="local_sqlite_fallback",
    )
    parser.add_argument("--output-json")
    args = parser.parse_args(argv)

    packet = build_operator_packet_from_path(
        status_packet_json=args.status_packet_json,
        strategy_source=args.strategy_source,
    )
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if packet["status"] != "blocked_forbidden_effect" else 2


if __name__ == "__main__":
    raise SystemExit(main())
