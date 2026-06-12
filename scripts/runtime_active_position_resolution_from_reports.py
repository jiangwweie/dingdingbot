#!/usr/bin/env python3
"""Build a runtime active-position resolution packet from report JSON files.

Inputs are the existing read-only reports:

- runtime_live_position_monitor.py output
- runtime_position_exit_plan.py output
- build_runtime_post_close_followup_packet.py output

The script is packet-only and never talks to PG, exchange, OrderLifecycle, or
runtime mutation services.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.runtime_active_position_resolution import (  # noqa: E402
    build_runtime_active_position_resolution_packet,
)
from src.domain.runtime_live_position_monitor import RuntimeLivePositionMonitorPacket  # noqa: E402
from src.domain.runtime_position_exit_plan import RuntimePositionExitPlan  # noqa: E402
from src.domain.runtime_post_close_followup import RuntimePostCloseFollowupPacket  # noqa: E402


def _load_report(path: str) -> dict[str, Any]:
    text = Path(path).expanduser().read_text(encoding="utf-8")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{path} does not contain a JSON object")
    value = json.loads(text[start:])
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _payload(report: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = report.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"report field {key} must be a JSON object")
    return value


def _build_packet(args: argparse.Namespace) -> dict[str, Any]:
    monitor_report = _load_report(args.live_position_monitor_json)
    exit_report = _load_report(args.position_exit_plan_json) if args.position_exit_plan_json else None
    followup_report = _load_report(args.post_close_followup_json) if args.post_close_followup_json else None

    monitor_payload = _payload(monitor_report, "packet") or monitor_report
    exit_payload = _payload(exit_report, "plan") if exit_report is not None else None
    followup_payload = _payload(followup_report, "packet") if followup_report is not None else None

    packet = build_runtime_active_position_resolution_packet(
        monitor=RuntimeLivePositionMonitorPacket.model_validate(monitor_payload),
        exit_plan=(
            RuntimePositionExitPlan.model_validate(exit_payload)
            if exit_payload is not None
            else None
        ),
        post_close_followup=(
            RuntimePostCloseFollowupPacket.model_validate(followup_payload)
            if followup_payload is not None
            else None
        ),
        now_ms=args.now_ms if args.now_ms is not None else int(time.time() * 1000),
    )
    return {
        "scope": "runtime_active_position_resolution_from_reports",
        "status": packet.status.value,
        "packet": packet.model_dump(mode="json"),
        "source_reports": {
            "live_position_monitor_json": args.live_position_monitor_json,
            "position_exit_plan_json": args.position_exit_plan_json,
            "post_close_followup_json": args.post_close_followup_json,
        },
        "safety_invariants": {
            "packet_only": True,
            "pg_read_called": False,
            "exchange_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_cancelled": False,
            "order_lifecycle_called": False,
            "position_closed": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a packet-only active-position resolution from reports.",
    )
    parser.add_argument("--live-position-monitor-json", required=True)
    parser.add_argument("--position-exit-plan-json")
    parser.add_argument("--post-close-followup-json")
    parser.add_argument("--now-ms", type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = _build_packet(args)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
