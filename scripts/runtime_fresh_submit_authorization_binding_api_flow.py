#!/usr/bin/env python3
"""Create or bind a persisted fresh submit authorization through API."""

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


API_BASE_ENV = "RUNTIME_FRESH_SUBMIT_AUTHORIZATION_BINDING_API_BASE"


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


def _read_handoff_artifact_file(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return _unwrap_payload(value)


def _unwrap_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("handoff_artifact", "artifact", "api_payload"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return nested
    return payload


def _request_body(args: argparse.Namespace) -> dict[str, Any]:
    handoff_artifact = _read_handoff_artifact_file(_handoff_artifact_json(args))
    body: dict[str, Any] = {
        "handoff_artifact": handoff_artifact,
        "requested_fresh_submit_authorization_id": (
            args.requested_fresh_submit_authorization_id
        ),
        "allow_create_from_existing_intent": args.allow_create_from_existing_intent,
        "allow_create_intent_from_latest_draft": (
            args.allow_create_intent_from_latest_draft
        ),
        "metadata": {
            "runtime_fresh_submit_authorization_binding_api_flow": True,
            "no_exchange_side_effects": True,
        },
        "no_exchange_side_effects": True,
    }
    if args.additional_warning:
        body["additional_warnings"] = list(args.additional_warning)
    if args.additional_blocker:
        body["additional_blockers"] = list(args.additional_blocker)
    return body


def _handoff_artifact_json(args: argparse.Namespace) -> str:
    path = getattr(args, "handoff_artifact_json", None)
    if not path:
        raise ValueError("handoff_artifact_json_required")
    return str(path)


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
            "fresh-authorizations/bind"
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
            "scope": "runtime_fresh_submit_authorization_binding_api_flow",
            "status": "blocked",
            "blocked_stage": "fresh_submit_authorization_binding_api",
            "runtime_instance_id": args.runtime_instance_id,
            "http_status": http_status,
            "api_payload": body,
            "blockers": [
                f"fresh_submit_authorization_binding_api_http_{http_status}"
            ],
            "warnings": [],
            "safety_invariants": _safety(body),
        }
    return {
        "scope": "runtime_fresh_submit_authorization_binding_api_flow",
        "status": body.get("status") or "unknown",
        "runtime_instance_id": args.runtime_instance_id,
        "http_status": http_status,
        "api_payload": body,
        "blockers": list(body.get("blockers") or []),
        "warnings": list(body.get("warnings") or []),
        "operator_action_preview": {
            "fresh_submit_authorization_id": body.get("fresh_submit_authorization_id"),
            "execution_intent_id": body.get("execution_intent_id"),
            "runtime_execution_intent_draft_id": (
                body.get("runtime_execution_intent_draft_id")
            ),
            "ready_for_fresh_authorization_resolution": body.get(
                "ready_for_fresh_authorization_resolution"
            ),
            "ready_for_disabled_smoke_call": body.get(
                "ready_for_disabled_smoke_call"
            ),
            "binding_source": body.get("binding_source"),
        },
        "safety_invariants": _safety(body),
    }


def _safety(body: dict[str, Any]) -> dict[str, bool]:
    return {
        "uses_trading_console_api": True,
        "creates_execution_intent": body.get("creates_execution_intent") is True,
        "creates_submit_authorization": (
            body.get("creates_submit_authorization") is True
        ),
        "calls_official_submit_endpoint": False,
        "requests_real_gateway_action": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "runtime_state_mutated": False,
        "withdrawal_or_transfer_created": False,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or bind persisted fresh submit authorization.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--handoff-artifact-json", required=True)
    parser.add_argument("--requested-fresh-submit-authorization-id")
    parser.add_argument(
        "--allow-create-from-existing-intent",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--allow-create-intent-from-latest-draft",
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
    return 0 if report["status"] in {
        "bound_existing_authorization",
        "created_authorization",
        "created_intent_and_authorization",
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
