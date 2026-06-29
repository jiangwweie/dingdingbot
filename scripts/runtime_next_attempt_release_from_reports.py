#!/usr/bin/env python3
"""Build a runtime next-attempt release projection from report JSON files.

Inputs are existing non-executing reports:

- runtime_active_position_resolution_from_reports.py output
- optional verify_runtime_next_attempt_gate_evidence.py output

The script is projection-only and never talks to PG, exchange, OrderLifecycle,
or runtime mutation services.
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
    RuntimeActivePositionResolutionArtifact,
)
from src.domain.runtime_next_attempt_release import (  # noqa: E402
    build_runtime_next_attempt_release_evidence,
)


def _load_report(path: str) -> dict[str, Any]:
    text = Path(path).expanduser().read_text(encoding="utf-8")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{path} does not contain a JSON object")
    value = json.loads(text[start:])
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _payload(report: dict[str, Any], key: str) -> dict[str, Any]:
    value = report.get(key)
    if isinstance(value, dict):
        return value
    return report


def _build_projection(args: argparse.Namespace) -> dict[str, Any]:
    resolution_report = _load_report(args.active_position_resolution_json)
    gate_report = (
        _load_report(args.next_attempt_gate_json)
        if args.next_attempt_gate_json
        else None
    )
    release_evidence = build_runtime_next_attempt_release_evidence(
        active_position_resolution=RuntimeActivePositionResolutionArtifact.model_validate(
            _payload(resolution_report, "artifact"),
        ),
        next_attempt_gate_evidence=gate_report,
        now_ms=args.now_ms if args.now_ms is not None else int(time.time() * 1000),
    )
    return {
        "scope": "runtime_next_attempt_release_from_reports",
        "status": release_evidence.status.value,
        "release_evidence": release_evidence.model_dump(mode="json"),
        "source_reports": {
            "active_position_resolution_json": args.active_position_resolution_json,
            "next_attempt_gate_json": args.next_attempt_gate_json,
        },
        "next_attempt_release_plan": {
            "scope": "runtime_next_attempt_release_plan",
            "not_executed": True,
            "strategy_signal_observation_allowed": (
                release_evidence.strategy_signal_observation_allowed
            ),
            "shadow_candidate_planning_allowed": (
                release_evidence.shadow_candidate_planning_allowed
            ),
            "executable_submit_allowed": False,
            "requires_fresh_strategy_signal": True,
            "requires_fresh_authorization": True,
            "requires_official_final_gate": True,
            "recommended_review_checkpoint": release_evidence.recommended_review_checkpoint,
        },
        "safety_invariants": {
            "next_attempt_release_projection_only": True,
            "pg_read_called": False,
            "exchange_called": False,
            "exchange_write_called": False,
            "execution_intent_created": False,
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
        description="Build a projection-only next-attempt release from reports.",
    )
    parser.add_argument("--active-position-resolution-json", required=True)
    parser.add_argument("--next-attempt-gate-json")
    parser.add_argument("--now-ms", type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    projection = _build_projection(args)
    print(json.dumps(projection, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if projection["status"] == "ready_for_strategy_signal" else 2


if __name__ == "__main__":
    raise SystemExit(main())
