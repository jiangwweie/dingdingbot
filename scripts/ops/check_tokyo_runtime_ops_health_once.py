#!/usr/bin/env python3
"""One-shot Tokyo runtime ops health command plan/check helper.

By default this prints the readonly commands an operator should run on Tokyo.
It can execute locally with --execute-local, which is intended for tests and for
running directly on the server. It never mutates runtime state.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from typing import Any


SCHEMA = "brc.ops.tokyo_runtime_ops_health_once.v1"
COMMANDS = (
    ("disk_df", ("df", "-h")),
    ("reports_du", ("du", "-sh", "/home/ubuntu/brc-deploy/reports")),
    ("releases_du", ("du", "-sh", "/home/ubuntu/brc-deploy/releases")),
    ("backups_du", ("du", "-sh", "/home/ubuntu/brc-deploy/backups")),
    ("journald_usage", ("journalctl", "--disk-usage")),
    ("backend_status", ("systemctl", "is-active", "brc-owner-console-backend.service")),
    ("watcher_timer_status", ("systemctl", "is-active", "brc-runtime-signal-watcher.timer")),
    ("monitor_timer_status", ("systemctl", "is-active", "brc-runtime-monitor.timer")),
    ("pg_listener", ("ss", "-ltnp")),
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = build_payload(execute_local=args.execute_local)
    if args.manifest_json:
        with open(args.manifest_json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] != "critical" else 2


def build_payload(*, execute_local: bool) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for name, command in COMMANDS:
        if not execute_local:
            results.append({"name": name, "command": list(command), "status": "planned"})
            continue
        executable = shutil.which(command[0])
        if not executable:
            results.append({"name": name, "command": list(command), "status": "missing_binary"})
            continue
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        results.append(
            {
                "name": name,
                "command": list(command),
                "status": "ok" if completed.returncode == 0 else "warn",
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            }
        )
    statuses = {row["status"] for row in results}
    status = "ok"
    if "warn" in statuses or "missing_binary" in statuses:
        status = "warn"
    return {
        "schema": SCHEMA,
        "status": status,
        "mode": "execute_local" if execute_local else "plan_only",
        "results": results,
        "checks": {
            "no_pg_runtime_truth_write": True,
            "no_trade_runtime_mutation": True,
            "readonly_commands_only": True,
        },
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-local", action="store_true")
    parser.add_argument("--manifest-json")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
