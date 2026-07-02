#!/usr/bin/env python3
"""Call the runtime post-submit finalize API.

This script resolves post-submit evidence through the Trading Console API and
returns a non-executing post-submit finalize artifact. It never calls exchange, creates
orders, submits through OrderLifecycle, closes positions, transfers, or
withdraws funds.
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


API_BASE_ENV = "RUNTIME_POST_SUBMIT_FINALIZE_API_BASE"


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


def _metadata(args: argparse.Namespace) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if args.metadata_json:
        value = json.loads(args.metadata_json)
        if not isinstance(value, dict):
            raise ValueError("--metadata-json must be a JSON object")
        metadata.update(value)
    metadata.update(
        {
            "runtime_post_submit_finalize_api_flow": True,
            "non_executing_probe": True,
        }
    )
    return metadata


def _request_body(args: argparse.Namespace) -> dict[str, Any]:
    body: dict[str, Any] = {
        "closed_review_required": bool(args.closed_review_required),
        "protection_blockers": list(args.protection_blocker or []),
        "metadata": _metadata(args),
        "non_executing": True,
    }
    if args.authorization_id:
        body["authorization_id"] = args.authorization_id
    if args.reservation_id:
        body["reservation_id"] = args.reservation_id
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
            f"{args.runtime_instance_id}/post-submit-finalize-payloads"
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
            "scope": "runtime_post_submit_finalize_api_flow",
            "status": "blocked",
            "blocked_stage": "post_submit_finalize_api",
            "runtime_instance_id": args.runtime_instance_id,
            "authorization_id": args.authorization_id,
            "http_status": http_status,
            "api_payload": body,
            "blockers": [f"post_submit_finalize_api_http_{http_status}"],
            "warnings": [],
            "safety_invariants": _safety(),
        }
    return {
        "scope": "runtime_post_submit_finalize_api_flow",
        "status": body.get("status") or "unknown",
        "runtime_instance_id": args.runtime_instance_id,
        "authorization_id": body.get("authorization_id") or args.authorization_id,
        "http_status": http_status,
        "api_payload": body,
        "post_submit_finalize_payload": body,
        "blockers": list(body.get("blockers") or []),
        "next_attempt_blockers": list(
            (body.get("next_attempt_gate") or {}).get("blockers") or []
        ),
        "warnings": list(body.get("warnings") or []),
        "safety_invariants": _safety(),
    }


def _safety() -> dict[str, bool]:
    return {
        "uses_official_trading_console_api": True,
        "non_executing": True,
        "pre_submit_rehearsal_called": False,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated_by_script": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Call the runtime post-submit finalize payload API.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--reservation-id")
    parser.add_argument("--authorization-id")
    parser.add_argument("--closed-review-required", action="store_true")
    parser.add_argument("--protection-blocker", action="append")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
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
        "finalized_ready_for_next_attempt",
        "finalized_next_attempt_blocked",
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
