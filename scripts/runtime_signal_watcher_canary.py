#!/usr/bin/env python3
"""Run one API-only, non-executing watcher canary tick."""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib import request


def _post(api_base: str, path: str, body: dict, timeout: float) -> dict:
    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = request.Request(
        api_base.rstrip("/") + path,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        raw = response.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise RuntimeError("canary_response_too_large")
        return json.loads(raw.decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment-canary", action="store_true", required=True)
    parser.add_argument("--api-only", action="store_true", required=True)
    parser.add_argument("--no-pg-materialization", action="store_true", required=True)
    parser.add_argument("--no-fact-refresh", action="store_true", required=True)
    parser.add_argument("--api-base", default="http://127.0.0.1:18081")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    args = parser.parse_args(argv)
    runtime_ids = [
        value.strip()
        for value in os.getenv("BRC_CANARY_RUNTIME_INSTANCE_IDS", "").split(",")
        if value.strip()
    ]
    if not runtime_ids:
        print(json.dumps({"status": "blocked", "error": "canary_runtime_ids_missing"}))
        return 2
    results = []
    for runtime_id in runtime_ids:
        results.append(
            _post(
                args.api_base,
                "/api/trading-console/strategy-runtimes/"
                f"{runtime_id}/next-attempt-observation-cycle",
                {
                    "source": "live_market",
                    "include_exchange": False,
                    "allow_action_time_ticket_materialization": False,
                    "response_projection": "watcher_compact",
                    "non_executing": True,
                    "timeout_seconds": min(args.timeout_seconds, 60.0),
                },
                min(args.timeout_seconds, 120.0),
            )
        )
    print(
        json.dumps(
            {
                "status": "passed",
                "route_set_status": "passed",
                "runtime_count": len(results),
                "results": results,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

