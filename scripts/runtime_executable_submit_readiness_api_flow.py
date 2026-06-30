#!/usr/bin/env python3
"""Call the current non-executing runtime executable-submit readiness API."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from importlib import import_module
import json
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

_ARCHIVED_MODULE = import_module(
    "scripts.replay_recovery_history.first_real_submit."
    "runtime_executable_submit_readiness_api_flow"
)

API_BASE_ENV = _ARCHIVED_MODULE.API_BASE_ENV
FIRST_REAL_SUBMIT_API_BASE_ENV = _ARCHIVED_MODULE.FIRST_REAL_SUBMIT_API_BASE_ENV
DEFAULT_API_BASE = _ARCHIVED_MODULE.DEFAULT_API_BASE
UrlLibApiClient = _ARCHIVED_MODULE.UrlLibApiClient
_api_base = _ARCHIVED_MODULE._api_base
_load_env_file = _ARCHIVED_MODULE._load_env_file
_read_json_file = _ARCHIVED_MODULE._read_json_file
_safety = _ARCHIVED_MODULE._safety
_strategy_planning_artifact_json_arg = (
    _ARCHIVED_MODULE._strategy_planning_artifact_json_arg
)


def _request_body(args: argparse.Namespace) -> dict[str, Any]:
    body: dict[str, Any] = {
        "strategy_planning_artifact": _read_json_file(
            _strategy_planning_artifact_json_arg(args)
        ),
        "evidence": _read_json_file(args.evidence_json),
        "metadata": {
            "runtime_executable_submit_readiness_api_flow": True,
            "non_executing_probe": True,
        },
        "non_executing": True,
    }
    if args.first_real_submit_evidence_json:
        body["first_real_submit_evidence"] = _read_json_file(
            args.first_real_submit_evidence_json
        )
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
            f"{args.runtime_instance_id}/executable-submit-readiness-previews"
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
            "scope": "runtime_executable_submit_readiness_api_flow",
            "status": "blocked",
            "blocked_stage": "executable_submit_readiness_api",
            "runtime_instance_id": args.runtime_instance_id,
            "http_status": http_status,
            "api_payload": body,
            "blockers": [
                f"executable_submit_readiness_api_http_{http_status}"
            ],
            "warnings": [],
            "safety_invariants": _safety(),
        }
    return {
        "scope": "runtime_executable_submit_readiness_api_flow",
        "status": body.get("status") or "unknown",
        "runtime_instance_id": args.runtime_instance_id,
        "http_status": http_status,
        "api_payload": body,
        "blockers": list(body.get("blockers") or []),
        "warnings": list(body.get("warnings") or []),
        "safety_invariants": _safety(),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Call the non-executing runtime executable-submit readiness API."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--strategy-planning-artifact-json")
    parser.add_argument("--evidence-json", required=True)
    parser.add_argument("--first-real-submit-evidence-json")
    parser.add_argument("--additional-warning", action="append")
    parser.add_argument("--additional-blocker", action="append")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    args = parser.parse_args(argv)
    if not args.strategy_planning_artifact_json:
        parser.error("--strategy-planning-artifact-json is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        artifact = _build_artifact(args)
    print(
        json.dumps(
            artifact,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0 if artifact["status"] in {
        "ready_for_executable_submit",
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
