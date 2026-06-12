#!/usr/bin/env python3
"""Build a non-executing official submit handoff from readiness JSON."""

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

from src.domain.runtime_executable_submit_readiness import (  # noqa: E402
    RuntimeExecutableSubmitReadinessPacket,
)
from src.domain.runtime_official_submit_handoff import (  # noqa: E402
    RuntimeOfficialSubmitHandoffMode,
    build_runtime_official_submit_handoff_packet,
)


def build_report(
    *,
    readiness_payload: dict[str, Any],
    fresh_submit_authorization_id: str | None,
    mode: RuntimeOfficialSubmitHandoffMode,
    owner_confirmed_for_real_submit_action: bool,
    now_ms: int | None = None,
) -> dict[str, Any]:
    readiness = RuntimeExecutableSubmitReadinessPacket.model_validate(
        _unwrap_readiness(readiness_payload)
    )
    packet = build_runtime_official_submit_handoff_packet(
        readiness_packet=readiness,
        fresh_submit_authorization_id=fresh_submit_authorization_id,
        mode=mode,
        owner_confirmed_for_real_submit_action=(
            owner_confirmed_for_real_submit_action
        ),
        now_ms=now_ms or _now_ms(),
    )
    return {
        "scope": "runtime_official_submit_handoff_report",
        "packet": packet.model_dump(mode="json"),
        "operator_action_preview": {
            "method": packet.official_endpoint_method,
            "path": packet.official_endpoint_path,
            "query": packet.official_query,
            "ready_for_call": packet.ready_for_official_submit_call,
            "mode": packet.mode.value,
        },
        "safety_invariants": {
            "calls_official_endpoint": False,
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


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    payload = _read_json(Path(args.readiness_json))
    report = build_report(
        readiness_payload=payload,
        fresh_submit_authorization_id=args.fresh_submit_authorization_id,
        mode=RuntimeOfficialSubmitHandoffMode(args.mode),
        owner_confirmed_for_real_submit_action=(
            args.owner_confirmed_for_real_submit_action
        ),
        now_ms=args.now_ms,
    )
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0 if report["packet"]["status"] in {
        "ready_for_official_submit_call",
        "blocked",
    } else 2


def _unwrap_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("packet", "api_payload"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return nested
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a non-executing official submit handoff packet.",
    )
    parser.add_argument("--readiness-json", required=True)
    parser.add_argument("--fresh-submit-authorization-id")
    parser.add_argument(
        "--mode",
        choices=[item.value for item in RuntimeOfficialSubmitHandoffMode],
        default=RuntimeOfficialSubmitHandoffMode.DISABLED_SMOKE.value,
    )
    parser.add_argument(
        "--owner-confirmed-for-real-submit-action",
        action="store_true",
    )
    parser.add_argument("--now-ms", type=int)
    parser.add_argument("--output")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
