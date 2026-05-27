#!/usr/bin/env python3
"""BRC Owner Console smoke helper.

HTTP mode expects a running backend. It signs a short-lived local operator
session from .env/.env.local by default and exercises read-only + Operation
preflight/cancel/wrong-confirm/get/list paths.

Runtime-bound-test mode uses the in-memory test service to prove that
switch_playbook can preflight and confirm successfully when BRC campaign,
account facts, audit, and operation repository services are bound.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - local env dependent
    load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_env_files() -> None:
    if load_dotenv is None:
        return
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(REPO_ROOT / ".env.local", override=True)


def _signed_cookie_from_env(ttl_seconds: int = 1800) -> str:
    _load_env_files()
    from src.interfaces.operator_auth import _sign_payload

    missing = [
        name
        for name in ("BRC_OPERATOR_USERNAME", "BRC_OPERATOR_SESSION_SECRET")
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError(
            "missing local operator session env values: "
            + ", ".join(missing)
            + "; set them in .env/.env.local or pass --cookie"
        )
    username = os.environ["BRC_OPERATOR_USERNAME"]
    secret = os.environ["BRC_OPERATOR_SESSION_SECRET"]
    now = int(time.time())
    token = _sign_payload(
        {
            "sub": username,
            "iat": now,
            "exp": now + ttl_seconds,
            "scope": "brc_operator_console",
        },
        secret,
    )
    return f"brc_operator_session={token}"


def _request(
    *,
    base_url: str,
    method: str,
    path: str,
    cookie: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={
            "Cookie": cookie,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if payload is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        parsed = json.loads(body) if body else {}
        return exc.code, parsed


def run_http_smoke(base_url: str, cookie: str) -> dict[str, Any]:
    result: dict[str, Any] = {"base_url": base_url, "checks": []}

    def check(name: str, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        status, body = _request(base_url=base_url, method=method, path=path, cookie=cookie, payload=payload)
        item = {"name": name, "status_code": status, "body": body}
        result["checks"].append(item)
        return item

    readiness = check("readiness", "GET", "/api/brc/readiness")
    capabilities = check("capabilities", "GET", "/api/brc/operations/capabilities")
    facts = check("account_facts", "GET", "/api/brc/account/facts")
    preflight = check(
        "switch_playbook_preflight",
        "POST",
        "/api/brc/operations/preflight",
        {
            "operation_type": "switch_playbook",
            "requested_by": "owner",
            "input_params": {
                "target_playbook_id": "PB-004-BRC-CONTROLLED-TESTNET",
                "reason_text": "owner dev smoke",
                "evidence_refs": ["docs/product/brc-owner-console-current-state.md"],
            },
            "source": {"kind": "dev_smoke", "ref": "brc_owner_console_smoke.py"},
        },
    )
    preflight_body = preflight["body"]
    operation_id = preflight_body.get("operation_id")
    if operation_id:
        check("cancel_operation", "POST", f"/api/brc/operations/{operation_id}/cancel", {"requested_by": "owner"})
        check(
            "wrong_confirm_phrase",
            "POST",
            f"/api/brc/operations/{operation_id}/confirm",
            {
                "preflight_id": preflight_body.get("preflight_id"),
                "confirmation_phrase": "WRONG_PHRASE",
                "idempotency_key": preflight_body.get("idempotency_key"),
                "confirmed_by": "owner",
            },
        )
        check("get_operation", "GET", f"/api/brc/operations/{operation_id}")
    check("list_operations", "GET", "/api/brc/operations?limit=5")

    result["summary"] = {
        "readiness_status": readiness["status_code"],
        "capabilities_status": capabilities["status_code"],
        "account_facts_status": facts["status_code"],
        "preflight_status": preflight["status_code"],
        "preflight_decision": preflight_body.get("decision"),
        "preflight_operation_status": preflight_body.get("status"),
        "live_ready": readiness["body"].get("live_ready"),
        "account_source": facts["body"].get("source"),
        "account_truth_level": facts["body"].get("truth_level"),
    }
    return result


async def run_runtime_bound_test_smoke() -> dict[str, Any]:
    from tests.unit.test_brc_operation_layer import _switch_preflight, _operation_service

    service, _, brc_repo, _ = await _operation_service()
    preflight = await _switch_preflight(service)
    confirmed = await service.confirm(
        operation_id=preflight.operation_id,
        preflight_id=preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=preflight.idempotency_key,
    )
    listed = await service.list(limit=5)
    detail = await service.get(preflight.operation_id)
    return {
        "mode": "runtime-bound-test",
        "preflight": {
            "decision": preflight.decision,
            "status": preflight.status,
            "operation_id": preflight.operation_id,
            "preflight_id": preflight.preflight_id,
        },
        "confirm": {
            "status": confirmed.status,
            "campaign_refs": confirmed.campaign_refs,
            "audit_refs": confirmed.audit_refs,
        },
        "campaign_playbook": brc_repo.campaign.current_playbook_id,
        "operation_list_count": len(listed.operations),
        "detail_status": detail.operation.status,
    }


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["http", "runtime-bound-test"], default="http")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--cookie", default=None)
    args = parser.parse_args(argv)

    if args.mode == "runtime-bound-test":
        _print_json(asyncio.run(run_runtime_bound_test_smoke()))
        return 0

    cookie = args.cookie or _signed_cookie_from_env()
    _print_json(run_http_smoke(args.base_url, cookie))
    return 0


if __name__ == "__main__":
    sys.exit(main())
