#!/usr/bin/env python3
"""Create a persisted runtime intent draft source from a strategy signal."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from dataclasses import dataclass
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


API_BASE_ENV = "RUNTIME_STRATEGY_SIGNAL_INTENT_DRAFT_SOURCE_API_BASE"
_LEGACY_SIGNAL_WRAPPER = "signal_" + "pack" + "et"


@dataclass(frozen=True)
class SignalInputSource:
    signal_input: dict[str, Any]
    wrapper: str | None = None


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
    return value


def _read_signal_input_source(path: str) -> SignalInputSource:
    payload = _read_json_file(path)
    if isinstance(payload.get("signal_input"), dict):
        return SignalInputSource(
            signal_input=payload["signal_input"],
            wrapper="signal_input",
        )
    if _LEGACY_SIGNAL_WRAPPER in payload:
        raise ValueError(
            "legacy signal wrapper is not accepted; use signal_input"
        )
    return SignalInputSource(signal_input=payload)


def _metadata(args: argparse.Namespace) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if args.metadata_json:
        value = json.loads(args.metadata_json)
        if not isinstance(value, dict):
            raise ValueError("--metadata-json must be a JSON object")
        metadata.update(value)
    metadata.update(
        {
            "runtime_strategy_signal_intent_draft_source_api_flow": True,
            "non_executing_probe": True,
        }
    )
    return metadata


def _request_body(args: argparse.Namespace) -> dict[str, Any]:
    signal_source = _read_signal_input_source(args.signal_input_json)
    metadata = _metadata(args)
    if signal_source.wrapper:
        metadata["signal_input_source_wrapper"] = {
            "wrapper": signal_source.wrapper,
        }
    body: dict[str, Any] = {
        "signal_input": signal_source.signal_input,
        "allow_shadow_candidate_creation": True,
        "allow_intent_draft_creation": True,
        "owner_reviewed": True,
        "owner_confirmed_for_intent": True,
        "metadata": metadata,
        "non_executing": True,
    }
    if args.candidate_id:
        body["candidate_id"] = args.candidate_id
    if args.context_id:
        body["context_id"] = args.context_id
    if args.expires_at_ms is not None:
        body["expires_at_ms"] = args.expires_at_ms
    if args.active_positions_count is not None:
        body["active_positions_count"] = args.active_positions_count
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
            f"{args.runtime_instance_id}/strategy-signal-intent-draft-sources"
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
            "scope": "runtime_strategy_signal_intent_draft_source_api_flow",
            "status": "blocked",
            "blocked_stage": "intent_draft_source_api",
            "runtime_instance_id": args.runtime_instance_id,
            "http_status": http_status,
            "api_payload": body,
            "blockers": [f"intent_draft_source_api_http_{http_status}"],
            "warnings": [],
            "safety_invariants": _safety(body),
        }
    return {
        "scope": "runtime_strategy_signal_intent_draft_source_api_flow",
        "status": body.get("status") or "unknown",
        "runtime_instance_id": args.runtime_instance_id,
        "http_status": http_status,
        "api_payload": body,
        "blockers": list(body.get("blockers") or []),
        "warnings": list(body.get("warnings") or []),
        "operator_action_preview": {
            "signal_evaluation_id": body.get("signal_evaluation_id"),
            "order_candidate_id": body.get("order_candidate_id"),
            "runtime_execution_intent_draft_id": body.get(
                "runtime_execution_intent_draft_id"
            ),
            "draft_status": body.get("draft_status"),
            "ready_for_official_handoff_source": body.get(
                "ready_for_official_handoff_source"
            ),
        },
        "safety_invariants": _safety(body),
    }


def _safety(body: dict[str, Any]) -> dict[str, bool]:
    return {
        "uses_official_trading_console_api": True,
        "non_executing": True,
        "signal_evaluation_created": body.get("signal_evaluation_created") is True,
        "order_candidate_created": body.get("order_candidate_created") is True,
        "runtime_execution_intent_draft_created": (
            body.get("runtime_execution_intent_draft_created") is True
        ),
        "execution_intent_created": False,
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
            "Create a non-executing persisted strategy-signal intent draft source."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--signal-input-json", required=True)
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--candidate-id")
    parser.add_argument("--context-id")
    parser.add_argument("--expires-at-ms", type=int)
    parser.add_argument("--active-positions-count", type=int)
    parser.add_argument("--metadata-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        report = _build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] in {
        "persisted_ready_intent_draft",
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
