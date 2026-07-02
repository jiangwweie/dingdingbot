#!/usr/bin/env python3
"""Call the official first-real-submit endpoint in disabled-smoke mode.

This flow consumes a ready official submit handoff artifact and calls the
existing Trading Console first-real-submit action endpoint with
owner_confirmed_for_first_real_submit_action=false. It deliberately refuses
real_gateway_action handoffs, so it can prove the official path is reachable
without placing an exchange order.
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
from src.domain.runtime_official_submit_handoff import (  # noqa: E402
    RuntimeOfficialSubmitHandoffMode,
    RuntimeOfficialSubmitHandoffArtifact,
    RuntimeOfficialSubmitHandoffStatus,
)


API_BASE_ENV = "RUNTIME_OFFICIAL_SUBMIT_DISABLED_SMOKE_API_BASE"


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


def _build_report(
    args: argparse.Namespace,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    raw_handoff = _read_handoff_artifact_file(args.handoff_artifact_json)
    handoff = RuntimeOfficialSubmitHandoffArtifact.model_validate(raw_handoff)
    blockers = _handoff_blockers(handoff)
    if blockers:
        return _report(
            args=args,
            handoff=handoff,
            status="blocked",
            blocked_stage="handoff_precondition",
        blockers=blockers,
        warnings=[],
        response=None,
        official_endpoint_called=False,
    )

    query = dict(handoff.official_query)
    query["owner_confirmed_for_first_real_submit_action"] = False
    api_client = client or UrlLibApiClient(api_base=_api_base(args))
    response = api_client.request_json(
        handoff.official_endpoint_method,
        handoff.official_endpoint_path,
        query=query,
    )
    http_status = int(response.get("http_status") or 0)
    body = response.get("body")
    if not isinstance(body, dict):
        body = {}
    response_blockers: list[str] = []
    response_warnings: list[str] = []
    status = str(body.get("status") or "")
    if http_status >= 300:
        response_blockers.append(f"official_first_real_submit_action_http_{http_status}")
    elif status != "exchange_submit_execution_disabled":
        response_blockers.append(
            f"disabled_official_submit_unexpected_status:{status or 'missing'}"
        )
    if body.get("exchange_submit_execution_enabled") is True:
        response_blockers.append("disabled_smoke_response_enabled_exchange_submit")
    if body.get("exchange_submit_execution_mode") not in {None, "disabled"}:
        response_warnings.append(
            "disabled_smoke_response_mode:"
            f"{body.get('exchange_submit_execution_mode')}"
        )
    return _report(
        args=args,
        handoff=handoff,
        status="blocked" if response_blockers else "disabled_smoke_passed",
        blocked_stage=(
            "official_first_real_submit_action"
            if response_blockers
            else None
        ),
        blockers=response_blockers,
        warnings=response_warnings,
        response=response,
        official_endpoint_called=True,
    )


def _handoff_blockers(handoff: RuntimeOfficialSubmitHandoffArtifact) -> list[str]:
    blockers: list[str] = []
    if handoff.status != RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL:
        blockers.append("handoff_not_ready_for_official_submit_call")
        blockers.extend(f"handoff:{item}" for item in handoff.blockers)
    if not handoff.ready_for_official_submit_call:
        blockers.append("handoff_ready_flag_false")
    if handoff.mode != RuntimeOfficialSubmitHandoffMode.DISABLED_SMOKE:
        blockers.append("disabled_smoke_refuses_real_gateway_handoff")
    if handoff.official_endpoint_method != "POST":
        blockers.append("official_endpoint_method_not_post")
    if "runtime-execution-first-real-submit-actions/authorizations/" not in (
        handoff.official_endpoint_path
    ):
        blockers.append("official_endpoint_path_unrecognized")
    if not handoff.fresh_submit_authorization_id:
        blockers.append("fresh_submit_authorization_id_missing")
    if (
        handoff.fresh_submit_authorization_id
        == handoff.source_consumed_authorization_id
    ):
        blockers.append("fresh_submit_authorization_reuses_consumed_authorization")
    if handoff.official_query.get("owner_confirmed_for_first_real_submit_action") is True:
        blockers.append("handoff_query_requests_real_submit_action")
    return _dedupe(blockers)


def _report(
    *,
    args: argparse.Namespace,
    handoff: RuntimeOfficialSubmitHandoffArtifact,
    status: str,
    blocked_stage: str | None,
    blockers: list[str],
    warnings: list[str],
    response: dict[str, Any] | None,
    official_endpoint_called: bool,
) -> dict[str, Any]:
    body = response.get("body") if response else None
    if not isinstance(body, dict):
        body = {}
    report: dict[str, Any] = {
        "scope": "runtime_official_submit_disabled_smoke_from_handoff",
        "status": status,
        "runtime_instance_id": handoff.runtime_instance_id,
        "handoff_id": handoff.handoff_id,
        "fresh_submit_authorization_id": handoff.fresh_submit_authorization_id,
        "official_call": {
            "method": handoff.official_endpoint_method,
            "path": handoff.official_endpoint_path,
            "query": {
                **dict(handoff.official_query),
                "owner_confirmed_for_first_real_submit_action": False,
            },
            "mode": "disabled_smoke",
        },
        "http_status": int((response or {}).get("http_status") or 0),
        "api_payload": body,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(list(handoff.warnings) + warnings),
        "safety_invariants": _safety(
            response_body=body,
            official_endpoint_called=official_endpoint_called,
        ),
    }
    if blocked_stage:
        report["blocked_stage"] = blocked_stage
    if args.output:
        Path(args.output).expanduser().write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return report


def _safety(
    *,
    response_body: dict[str, Any],
    official_endpoint_called: bool,
) -> dict[str, bool]:
    return {
        "uses_existing_official_submit_endpoint": True,
        "calls_official_submit_endpoint": official_endpoint_called,
        "requests_real_gateway_action": False,
        "owner_confirmed_for_first_real_submit_action": False,
        "exchange_submit_execution_enabled": (
            response_body.get("exchange_submit_execution_enabled") is True
        ),
        "exchange_write_called": False,
        "order_lifecycle_called": False,
        "execution_intent_created": False,
        "order_created": False,
        "runtime_budget_mutated": False,
        "attempt_counter_mutated": False,
        "withdrawal_or_transfer_created": False,
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Call official first-real-submit endpoint from a ready handoff "
            "artifact in disabled-smoke mode."
        ),
    )
    parser.add_argument("--handoff-artifact-json", required=True)
    parser.add_argument("--output")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        report = _build_report(args)
    if not args.output:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] in {"disabled_smoke_passed", "blocked"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
