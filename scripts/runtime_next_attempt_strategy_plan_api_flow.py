#!/usr/bin/env python3
"""Call the runtime next-attempt strategy planning API.

This script is the RTF-002 dry-run/probe entry:

post-submit finalize payload JSON + fresh signal input JSON
-> Trading Console next-attempt strategy planning endpoint
-> audit artifact

It never creates executable intents, local orders, OrderLifecycle handoffs,
exchange requests, closes, transfers, or withdrawals.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    API_BASE_ENV as FIRST_REAL_SUBMIT_API_BASE_ENV,
    DEFAULT_API_BASE,
    UrlLibApiClient,
)


API_BASE_ENV = "RUNTIME_NEXT_ATTEMPT_STRATEGY_PLAN_API_BASE"


def _load_env_file(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path).expanduser()
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and not os.environ.get(key):
            os.environ[key] = value


def _api_base(args: argparse.Namespace) -> str:
    return (
        args.api_base
        or os.environ.get(API_BASE_ENV)
        or os.environ.get(FIRST_REAL_SUBMIT_API_BASE_ENV)
        or DEFAULT_API_BASE
    )


def _read_json_file(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _metadata(args: argparse.Namespace) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if args.metadata_json:
        value = json.loads(args.metadata_json)
        if not isinstance(value, dict):
            raise ValueError("--metadata-json must be a JSON object")
        metadata.update(value)
    metadata.update(
        {
            "runtime_next_attempt_strategy_plan_api_flow": True,
            "non_executing_probe": True,
        }
    )
    return metadata


def _request_body(args: argparse.Namespace) -> dict[str, Any]:
    if not args.post_submit_finalize_payload_json:
        raise ValueError("post_submit_finalize_payload_json_required")
    body: dict[str, Any] = {
        "post_submit_finalize_payload": _read_json_file(
            args.post_submit_finalize_payload_json
        ),
        "signal_input": _read_json_file(args.signal_input_json),
        "metadata": _metadata(args),
        "non_executing": True,
    }
    if args.context_id:
        body["context_id"] = args.context_id
    if args.expires_at_ms is not None:
        body["expires_at_ms"] = args.expires_at_ms
    return body


def _call_api(
    *,
    args: argparse.Namespace,
    client: Any | None = None,
) -> dict[str, Any]:
    api_client = client or UrlLibApiClient(api_base=_api_base(args))
    return api_client.request_json(
        "POST",
        (
            "/api/trading-console/strategy-runtimes/"
            f"{args.runtime_instance_id}/next-attempt-strategy-plans"
        ),
        body=_request_body(args),
    )


def _build_artifact(
    args: argparse.Namespace,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    response = _call_api(args=args, client=client)
    http_status = int(response.get("http_status") or 0)
    body = response.get("body")
    if not isinstance(body, dict):
        body = {}
    if http_status >= 300:
        return {
            "scope": "runtime_next_attempt_strategy_plan_api_flow",
            "status": "blocked",
            "blocked_stage": "next_attempt_strategy_plan_api",
            "runtime_instance_id": args.runtime_instance_id,
            "http_status": http_status,
            "api_payload": body,
            "blockers": [f"next_attempt_strategy_plan_api_http_{http_status}"],
            "warnings": [],
            "safety_invariants": _safety(),
        }
    return {
        "scope": "runtime_next_attempt_strategy_plan_api_flow",
        "status": body.get("status") or "unknown",
        "runtime_instance_id": args.runtime_instance_id,
        "http_status": http_status,
        "api_payload": body,
        "blockers": list(body.get("blockers") or []),
        "warnings": list(body.get("warnings") or []),
        "safety_invariants": _safety(),
    }


def _safety() -> dict[str, bool]:
    return {
        "uses_official_trading_console_api": True,
        "non_executing": True,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Call the non-executing runtime next-attempt strategy planning API."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--post-submit-finalize-payload-json")
    parser.add_argument("--signal-input-json", required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--context-id")
    parser.add_argument("--expires-at-ms", type=int)
    parser.add_argument("--metadata-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        artifact = _build_artifact(args)
    print(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    )
    return 0 if artifact["status"] in {
        "ready_for_final_gate_preflight",
        "waiting_for_signal",
        "blocked_by_post_submit_gate",
        "blocked_by_strategy_planning",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
