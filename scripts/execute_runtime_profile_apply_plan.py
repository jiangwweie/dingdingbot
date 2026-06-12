#!/usr/bin/env python3
"""Execute or dry-run an RTF-038 runtime profile apply plan.

The default mode is dry-run and performs no API calls. Apply mode requires an
explicit ``--execute`` flag and a ready RTF-038 packet. The apply plan can only
record a promotion confirmation and create an execution-disabled shadow
runtime draft; it never submits orders, calls OrderLifecycle, calls exchange,
withdraws, or transfers funds.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Protocol


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    DEFAULT_API_BASE,
    UrlLibApiClient,
)


READY_PACKET_STATUS = "ready_for_runtime_profile_apply_with_trial_binding"
DRY_RUN_STATUS = "dry_run_runtime_profile_apply_plan_ready"
APPLIED_STATUS = "runtime_profile_apply_plan_applied"
BLOCKED_STATUS = "blocked_runtime_profile_apply_plan"


class ApiClient(Protocol):
    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


def _load_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _api_requests(packet: dict[str, Any]) -> list[dict[str, Any]]:
    apply_packet = packet.get("apply_packet") or {}
    plan = apply_packet.get("api_apply_plan") or {}
    requests = plan.get("requests") or []
    if not isinstance(requests, list):
        raise ValueError("api_apply_plan.requests must be a list")
    result: list[dict[str, Any]] = []
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError("api apply request must be an object")
        result.append(request)
    return result


def _request_is_safe(request: dict[str, Any]) -> bool:
    method = str(request.get("method") or "").upper()
    path = str(request.get("path") or "")
    if method != "POST":
        return False
    if path == "/api/brc/strategy-runtime-promotion-confirmations":
        return True
    if (
        path.startswith("/api/brc/strategy-runtime-promotion-confirmations/")
        and path.endswith("/runtime-drafts")
    ):
        return bool(request.get("execution_enabled") is False) and bool(
            request.get("shadow_mode") is True
        )
    return False


def _safety_invariants() -> dict[str, bool]:
    return {
        "order_lifecycle_called": False,
        "exchange_write_called": False,
        "withdrawal_or_transfer_created": False,
        "order_created": False,
        "execution_intent_created": False,
        "executable_execution_intent_created": False,
    }


def _blocked(
    *,
    packet: dict[str, Any],
    blockers: list[str],
    mode: str,
) -> dict[str, Any]:
    return {
        "scope": "runtime_profile_apply_plan_executor",
        "status": BLOCKED_STATUS,
        "mode": mode,
        "source_status": packet.get("status"),
        "requests_planned": [],
        "responses": [],
        "ids": {},
        "checks": {
            "ready_to_apply": False,
            "execute_requested": False,
            "blockers": sorted(set(blockers)),
        },
        "blockers": sorted(set(blockers)),
        "warnings": [],
        "safety_invariants": {
            **_safety_invariants(),
            "api_called": False,
            "promotion_confirmation_record_created": False,
            "runtime_created": False,
            "runtime_enabled": False,
            "runtime_activated": False,
        },
    }


def build_execution_report(
    *,
    packet: dict[str, Any],
    mode: str,
    execute: bool = False,
    client: ApiClient | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if packet.get("status") != READY_PACKET_STATUS:
        blockers.append("rtf038_apply_readiness_packet_not_ready")
    apply_packet = packet.get("apply_packet") or {}
    plan = apply_packet.get("api_apply_plan") or {}
    if plan.get("ready_to_apply") is not True:
        blockers.append("api_apply_plan_not_ready")
    if plan.get("places_order_when_applied") is not False:
        blockers.append("api_apply_plan_order_effect_not_false")
    if plan.get("calls_exchange_when_applied") is not False:
        blockers.append("api_apply_plan_exchange_effect_not_false")
    requests = _api_requests(packet)
    if len(requests) != 2:
        blockers.append("api_apply_plan_requires_exactly_two_requests")
    unsafe = [
        str(request.get("step") or request.get("path") or index)
        for index, request in enumerate(requests)
        if not _request_is_safe(request)
    ]
    if unsafe:
        blockers.append("api_apply_plan_contains_unsafe_request")
    if mode not in {"dry-run", "apply"}:
        blockers.append("mode_must_be_dry_run_or_apply")
    if mode == "apply" and not execute:
        blockers.append("execute_flag_required_for_apply_mode")
    if blockers:
        return _blocked(packet=packet, blockers=blockers, mode=mode)

    planned = [
        {
            "step": request.get("step"),
            "method": request.get("method"),
            "path": request.get("path"),
            "expected_effect": request.get("expected_effect"),
            "does_not_create_order": request.get("does_not_create_order"),
            "does_not_call_exchange": request.get("does_not_call_exchange"),
        }
        for request in requests
    ]
    if mode == "dry-run":
        return {
            "scope": "runtime_profile_apply_plan_executor",
            "status": DRY_RUN_STATUS,
            "mode": mode,
            "source_status": packet.get("status"),
            "requests_planned": planned,
            "responses": [],
            "ids": {},
            "checks": {
                "ready_to_apply": True,
                "execute_requested": False,
                "api_called": False,
                "blockers": [],
            },
            "blockers": [],
            "warnings": [
                "dry_run_did_not_call_api",
                "apply_requires_mode_apply_and_execute_flag",
            ],
            "safety_invariants": {
                **_safety_invariants(),
                "api_called": False,
                "promotion_confirmation_record_created": False,
                "runtime_created": False,
                "runtime_enabled": False,
                "runtime_activated": False,
            },
        }

    if client is None:
        raise ValueError("client is required for apply mode")
    responses: list[dict[str, Any]] = []
    ids: dict[str, str] = {}
    for request in requests:
        response = client.request_json(
            str(request["method"]),
            str(request["path"]),
            body=dict(request.get("body") or {}),
        )
        responses.append(
            {
                "step": request.get("step"),
                "method": request.get("method"),
                "path": request.get("path"),
                "http_status": response.get("http_status"),
                "body": response.get("body"),
                "error": bool(response.get("error", False)),
            }
        )
        if response.get("error") or int(response.get("http_status") or 0) >= 400:
            return {
                "scope": "runtime_profile_apply_plan_executor",
                "status": BLOCKED_STATUS,
                "mode": mode,
                "source_status": packet.get("status"),
                "requests_planned": planned,
                "responses": responses,
                "ids": ids,
                "checks": {
                    "ready_to_apply": False,
                    "execute_requested": True,
                    "api_called": True,
                    "blockers": [f"{request.get('step')}_http_error"],
                },
                "blockers": [f"{request.get('step')}_http_error"],
                "warnings": [],
                "safety_invariants": {
                    **_safety_invariants(),
                    "api_called": True,
                    "promotion_confirmation_record_created": bool(
                        ids.get("promotion_confirmation_id")
                    ),
                    "runtime_created": False,
                    "runtime_enabled": False,
                    "runtime_activated": False,
                },
            }
        body = response.get("body") or {}
        if request.get("step") == "record_promotion_confirmation":
            confirmation_id = (body.get("confirmation") or {}).get("confirmation_id")
            if confirmation_id:
                ids["promotion_confirmation_id"] = str(confirmation_id)
        if request.get("step") == "create_shadow_runtime_draft":
            runtime = body.get("runtime") or {}
            runtime_id = runtime.get("runtime_instance_id")
            if runtime_id:
                ids["runtime_instance_id"] = str(runtime_id)
            if runtime.get("execution_enabled") not in {False, None}:
                return _blocked(
                    packet=packet,
                    blockers=["created_runtime_execution_enabled_not_false"],
                    mode=mode,
                )
    return {
        "scope": "runtime_profile_apply_plan_executor",
        "status": APPLIED_STATUS,
        "mode": mode,
        "source_status": packet.get("status"),
        "requests_planned": planned,
        "responses": responses,
        "ids": ids,
        "checks": {
            "ready_to_apply": True,
            "execute_requested": True,
            "api_called": True,
            "promotion_confirmation_record_created": bool(
                ids.get("promotion_confirmation_id")
            ),
            "shadow_runtime_draft_created": bool(ids.get("runtime_instance_id")),
            "blockers": [],
        },
        "blockers": [],
        "warnings": [
            "runtime_draft_is_execution_disabled_shadow_record",
            "post_creation_full_cycle_probe_required",
        ],
        "safety_invariants": {
            **_safety_invariants(),
            "api_called": True,
            "promotion_confirmation_record_created": bool(
                ids.get("promotion_confirmation_id")
            ),
            "runtime_created": bool(ids.get("runtime_instance_id")),
            "runtime_enabled": False,
            "runtime_activated": False,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or execute an RTF-038 runtime profile apply plan.",
    )
    parser.add_argument("--apply-readiness-json", required=True)
    parser.add_argument("--mode", choices=["dry-run", "apply"], default="dry-run")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    client = UrlLibApiClient(api_base=args.api_base) if args.mode == "apply" else None
    report = build_execution_report(
        packet=_load_json(args.apply_readiness_json),
        mode=args.mode,
        execute=args.execute,
        client=client,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] in {DRY_RUN_STATUS, APPLIED_STATUS} else 2


if __name__ == "__main__":
    raise SystemExit(main())
