#!/usr/bin/env python3
"""Build dry-run LLM advisory events from runtime artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.runtime_advisory_event_adapter import (  # noqa: E402
    build_completion_audit_advisory_event,
    build_daily_check_advisory_event,
    build_review_due_advisory_event,
    build_trade_closed_advisory_event,
    build_watcher_packet_advisory_event,
    now_ms,
)


Builder = Callable[[dict[str, Any]], Any]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    timestamp = args.now_ms if args.now_ms is not None else now_ms()
    events = []
    for path_value, builder in (
        (args.daily_check_json, build_daily_check_advisory_event),
        (args.completion_audit_json, build_completion_audit_advisory_event),
        (args.watcher_json, build_watcher_packet_advisory_event),
        (args.trade_closed_json, build_trade_closed_advisory_event),
        (args.review_due_json, build_review_due_advisory_event),
    ):
        if path_value is None:
            continue
        path = Path(path_value)
        packet = _read_json(path)
        events.append(
            builder(
                packet,
                now=timestamp,
                source_ref=str(path),
            ).model_dump(mode="json")
        )

    payload = {
        "schema_version": 1,
        "mode": "dry_run",
        "not_execution_authority": True,
        "event_count": len(events),
        "events": events,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build dry-run LLM advisory events from runtime artifacts.",
    )
    parser.add_argument("--daily-check-json")
    parser.add_argument("--completion-audit-json")
    parser.add_argument("--watcher-json")
    parser.add_argument("--trade-closed-json")
    parser.add_argument("--review-due-json")
    parser.add_argument("--output-json")
    parser.add_argument("--now-ms", type=int)
    return parser.parse_args(argv)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
