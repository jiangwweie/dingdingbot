#!/usr/bin/env python3
"""Refresh StrategyGroup runtime product-state packets from local readmodels.

This script is intended as a read-only watcher post-step. It calls local
Trading Console readmodel endpoints with an operator session and writes the
Owner-readable packets used by heartbeat automation. It never creates
candidates, authorizations, orders, transfers, or exchange writes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_API_BASE = "http://127.0.0.1:18080"
DEFAULT_OUTPUT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
ENDPOINTS = (
    (
        "/api/trading-console/strategy-group-live-facts-readiness",
        "strategy-group-live-facts-readiness.json",
    ),
    (
        "/api/trading-console/strategygroup-runtime-pilot-status",
        "strategygroup-runtime-pilot-status.json",
    ),
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _operator_cookie(now: int | None = None) -> str:
    from src.interfaces.operator_auth import SESSION_COOKIE, _load_auth_config, _sign_payload

    config = _load_auth_config()
    issued_at = now or int(time.time())
    token = _sign_payload(
        {
            "sub": config.username,
            "iat": issued_at,
            "exp": issued_at + min(config.ttl_seconds, 3600),
            "scope": "brc_operator_console",
        },
        config.session_secret,
    )
    return f"{SESSION_COOKIE}={token}"


def _request_json(
    *,
    url: str,
    cookie: str,
    timeout_seconds: int,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Cookie": cookie,
        },
    )
    with opener(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"readmodel response must be a JSON object: {url}")
    return payload


def refresh_packets(
    *,
    api_base: str,
    output_dir: Path,
    label: str,
    timeout_seconds: int = 30,
    cookie: str | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    cookie = cookie or _operator_cookie()
    generated_at_ms = generated_at_ms or int(time.time() * 1000)
    output_dir.mkdir(parents=True, exist_ok=True)

    packets: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    api_root = api_base.rstrip("/")
    for endpoint, filename in ENDPOINTS:
        url = f"{api_root}{endpoint}"
        output_path = output_dir / filename
        try:
            response = _request_json(
                url=url,
                cookie=cookie,
                timeout_seconds=timeout_seconds,
                opener=opener,
            )
            packet = (
                response.get("data")
                if isinstance(response.get("data"), dict)
                else response
            )
            _write_json(output_path, packet)
            packets.append(
                {
                    "endpoint": endpoint,
                    "output_json": str(output_path),
                    "status": packet.get("status"),
                    "api_freshness_status": response.get("freshness_status"),
                    "api_blocker_count": len(response.get("blockers") or []),
                    "api_warning_count": len(response.get("warnings") or []),
                }
            )
        except Exception as exc:
            blockers.append(f"{filename}:refresh_failed:{type(exc).__name__}")
            warnings.append(str(exc))

    status = "refreshed" if not blockers else "refresh_blocked"
    return {
        "scope": "strategygroup_runtime_product_state_refresh",
        "label": label,
        "status": status,
        "generated_at_ms": generated_at_ms,
        "packets": packets,
        "blockers": blockers,
        "warnings": warnings,
        "safety_invariants": {
            "readmodel_refresh_only": True,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "execution_intent_created": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "places_order": False,
            "mutates_pg": False,
        },
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh StrategyGroup runtime product-state readmodel packets.",
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output-json")
    parser.add_argument("--label", default="strategygroup-runtime-product-state-refresh")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = refresh_packets(
        api_base=args.api_base,
        output_dir=Path(args.output_dir).expanduser(),
        label=args.label,
        timeout_seconds=args.timeout_seconds,
    )
    if args.output_json:
        _write_json(Path(args.output_json).expanduser(), packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] == "refreshed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
