#!/usr/bin/env python3
"""Build a non-executing runtime executable-submit readiness report.

Inputs are JSON artifacts produced by prior local/Tokyo probes. The script does
not read PG, call exchange, call OrderLifecycle, create orders, or mutate
runtime state.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.domain.runtime_executable_submit_readiness import (
    RuntimeExecutableSubmitReadinessEvidence,
    build_runtime_executable_submit_readiness_packet,
)


def build_report(
    *,
    strategy_planning_packet: dict[str, Any],
    evidence_payload: dict[str, Any],
    first_real_submit_packet: dict[str, Any] | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    evidence_source = evidence_payload.get("evidence", evidence_payload)
    evidence = RuntimeExecutableSubmitReadinessEvidence.model_validate(
        evidence_source
    )
    first_packet = first_real_submit_packet or {}
    packet = build_runtime_executable_submit_readiness_packet(
        runtime_instance_id=_required(
            strategy_planning_packet,
            "runtime_instance_id",
        ),
        source_strategy_planning_packet_id=_required(
            strategy_planning_packet,
            "packet_id",
        ),
        source_authorization_id=_required(
            strategy_planning_packet,
            "source_authorization_id",
        ),
        strategy_planning_status=_required(strategy_planning_packet, "status"),
        signal_evaluation_id=_optional(
            strategy_planning_packet,
            "signal_evaluation_id",
        ),
        order_candidate_id=_optional(strategy_planning_packet, "order_candidate_id"),
        source_release_packet_id=_optional(
            strategy_planning_packet,
            "source_release_packet_id",
        ),
        evidence=evidence,
        first_real_submit_packet_status=_optional(first_packet, "status"),
        first_real_submit_packet_blockers=list(first_packet.get("blockers") or []),
        now_ms=now_ms or _now_ms(),
    )
    return {
        "scope": "runtime_executable_submit_readiness_report",
        "packet": packet.model_dump(mode="json"),
        "safety_invariants": {
            "pg_read": False,
            "pg_write": False,
            "execution_intent_created": False,
            "executable_execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "exchange_order_submitted": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy-planning-packet", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--first-real-submit-packet")
    parser.add_argument("--output")
    parser.add_argument("--now-ms", type=int)
    args = parser.parse_args()

    strategy_planning_packet = _read_json(Path(args.strategy_planning_packet))
    evidence_payload = _read_json(Path(args.evidence))
    first_real_submit_packet = (
        _read_json(Path(args.first_real_submit_packet))
        if args.first_real_submit_packet
        else None
    )
    report = build_report(
        strategy_planning_packet=strategy_planning_packet,
        evidence_payload=evidence_payload,
        first_real_submit_packet=first_real_submit_packet,
        now_ms=args.now_ms,
    )
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict) and isinstance(data.get("packet"), dict):
        return data["packet"]
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _required(payload: dict[str, Any], key: str) -> str:
    value = _optional(payload, key)
    if not value:
        raise ValueError(f"missing required field: {key}")
    return value


def _optional(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    text = str(value or "").strip()
    return text or None


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
