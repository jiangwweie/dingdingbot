#!/usr/bin/env python3
"""Resolve persisted fresh submit authorization through Trading Console API."""

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


API_BASE_ENV = "RUNTIME_FRESH_SUBMIT_AUTHORIZATION_RESOLUTION_API_BASE"


def _load_env_file(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path).expanduser()
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
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
    return _unwrap_payload(value)


def _unwrap_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("packet", "api_payload"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return nested
    return payload


def _request_body(args: argparse.Namespace) -> dict[str, Any]:
    body: dict[str, Any] = {
        "handoff_packet": _read_json_file(args.handoff_json),
        "requested_fresh_submit_authorization_id": (
            args.requested_fresh_submit_authorization_id
        ),
        "allow_order_candidate_fallback": args.allow_order_candidate_fallback,
        "metadata": {
            "runtime_fresh_submit_authorization_resolution_api_flow": True,
            "non_executing_probe": True,
        },
        "non_executing": True,
    }
    if args.additional_warning:
        body["additional_warnings"] = list(args.additional_warning)
    if args.additional_blocker:
        body["additional_blockers"] = list(args.additional_blocker)
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
            f"{args.runtime_instance_id}/official-submit-handoff-"
            "fresh-authorizations/resolve"
        ),
        body=_request_body(args),
    )


def _build_report(
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
            "scope": "runtime_fresh_submit_authorization_resolution_api_flow",
            "status": "blocked",
            "blocked_stage": "fresh_submit_authorization_resolution_api",
            "runtime_instance_id": args.runtime_instance_id,
            "http_status": http_status,
            "api_payload": body,
            "blockers": [
                f"fresh_submit_authorization_resolution_api_http_{http_status}"
            ],
            "warnings": [],
            "safety_invariants": _safety(),
        }
    return {
        "scope": "runtime_fresh_submit_authorization_resolution_api_flow",
        "status": body.get("status") or "unknown",
        "runtime_instance_id": args.runtime_instance_id,
        "http_status": http_status,
        "api_payload": body,
        "blockers": list(body.get("blockers") or []),
        "warnings": list(body.get("warnings") or []),
        "operator_action_preview": {
            "method": body.get("official_endpoint_method"),
            "path": body.get("official_endpoint_path"),
            "query": body.get("official_query") or {},
            "ready_for_disabled_smoke_call": body.get(
                "ready_for_disabled_smoke_call"
            ),
            "resolved_fresh_submit_authorization_id": body.get(
                "resolved_fresh_submit_authorization_id"
            ),
            "resolution_source": body.get("resolution_source"),
        },
        "safety_invariants": _safety(),
    }


def _safety() -> dict[str, bool]:
    return {
        "uses_trading_console_api": True,
        "non_executing": True,
        "creates_authorization": False,
        "calls_official_submit_endpoint": False,
        "requests_real_gateway_action": False,
        "execution_intent_created": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "withdrawal_or_transfer_created": False,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve persisted fresh submit authorization for handoff.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--handoff-json", required=True)
    parser.add_argument("--requested-fresh-submit-authorization-id")
    parser.add_argument(
        "--allow-order-candidate-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--additional-warning", action="append")
    parser.add_argument("--additional-blocker", action="append")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        report = _build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] in {"resolved", "blocked"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
