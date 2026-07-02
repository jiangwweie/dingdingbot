#!/usr/bin/env python3
"""Probe full runtime binding on an isolated local port with read-only guards.

Default behavior is DRY-RUN. The script only starts `python -m src.main` when
RUN_RUNTIME_PROBE=true and all live/read-only environment guards pass.
"""

from __future__ import annotations

import asyncio
import json
import os
import select
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Mapping

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


RUN_ENV = "RUN_RUNTIME_PROBE"
DEFAULT_PORT = 18082
DEFAULT_TIMEOUT_SECONDS = 45


def _bool_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_value(env: Mapping[str, str], name: str, default: str = "") -> str:
    return str(env.get(name, default)).strip()


def guard_probe_environment(env: Mapping[str, str]) -> None:
    """Fail closed unless the probe environment is live/read-only and non-action."""
    expected = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
    }
    failures: list[str] = []
    for name, expected_value in expected.items():
        actual = _env_value(env, name).lower()
        if actual != expected_value:
            failures.append(f"{name}={env.get(name)!r}, expected {expected_value!r}")

    if not _env_value(env, "PG_DATABASE_URL"):
        failures.append("PG_DATABASE_URL is required")
    if _env_value(env, "RUNTIME_PROFILE"):
        failures.append("RUNTIME_PROFILE must be unset for production/live runtime startup")
    if failures:
        raise ValueError("unsafe runtime-bound probe environment: " + "; ".join(failures))


async def require_single_active_profile() -> dict:
    """Read PG runtime_profiles and require exactly one active row."""
    from scripts.inspect_runtime_profiles_readonly import inspect_runtime_profiles

    report = await inspect_runtime_profiles()
    active_count = int(report.get("active_count") or 0)
    if not report.get("runtime_profiles_exists"):
        raise ValueError("runtime_profiles table does not exist")
    if active_count != 1:
        raise ValueError(f"expected exactly one active runtime profile, got {active_count}")
    return report


def _int_env(env: Mapping[str, str], name: str, default: int) -> int:
    raw = _env_value(env, name)
    if not raw:
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build_probe_plan(env: Mapping[str, str]) -> dict:
    port = _int_env(env, "RUNTIME_PROBE_PORT", DEFAULT_PORT)
    timeout_seconds = _int_env(env, "RUNTIME_PROBE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    return {
        "mode": "dry_run" if not _bool_env(env.get(RUN_ENV)) else "run",
        "entrypoint": "python -m src.main",
        "health_url": f"http://127.0.0.1:{port}/api/health",
        "port": port,
        "timeout_seconds": timeout_seconds,
        "required_env": {
            "TRADING_ENV": "live",
            "EXCHANGE_TESTNET": "false",
            "BRC_EXECUTION_PERMISSION_MAX": "read_only",
            "RUNTIME_CONTROL_API_ENABLED": "false",
            "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
            "RUNTIME_PROFILE": "unset",
        },
        "safety": {
            "order_permission": "not granted by this script",
            "runtime_control_api": "disabled",
            "test_signal_injection": "disabled",
            "requires_single_active_pg_profile": True,
        },
    }


def _read_health(url: str) -> tuple[int, dict | str]:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = response.read().decode("utf-8")
            try:
                return response.status, json.loads(payload)
            except json.JSONDecodeError:
                return response.status, payload
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        return exc.code, payload
    except Exception as exc:  # pragma: no cover - exercised only in manual probe
        return 0, str(exc)


def _terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=8)


def _drain_available_stdout(proc: subprocess.Popen, lines: list[str]) -> None:
    if proc.stdout is None:
        return
    while True:
        readable, _, _ = select.select([proc.stdout], [], [], 0)
        if not readable:
            return
        line = proc.stdout.readline()
        if not line:
            return
        lines.append(line.rstrip())


async def run_probe(env: Mapping[str, str]) -> dict:
    guard_probe_environment(env)
    profile_report = await require_single_active_profile()
    plan = build_probe_plan(env)
    probe_env = dict(os.environ)
    probe_env.update(env)
    probe_env["BACKEND_PORT"] = str(plan["port"])
    probe_env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "-m", "src.main"],
        cwd=os.getcwd(),
        env=probe_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    lines: list[str] = []
    try:
        deadline = time.time() + int(plan["timeout_seconds"])
        last_status = 0
        last_payload: dict | str = ""
        while time.time() < deadline:
            _drain_available_stdout(proc, lines)
            if proc.poll() is not None:
                _drain_available_stdout(proc, lines)
                break
            last_status, last_payload = _read_health(plan["health_url"])
            if last_status == 200 and isinstance(last_payload, dict):
                return {
                    "result": "health_ready",
                    "plan": plan,
                    "profile_count": profile_report.get("count"),
                    "active_count": profile_report.get("active_count"),
                    "health_status": last_status,
                    "health": last_payload,
                    "process_returncode": proc.poll(),
                    "log_tail": lines[-80:],
                }
            time.sleep(1)
        return {
            "result": "not_ready",
            "plan": plan,
            "profile_count": profile_report.get("count"),
            "active_count": profile_report.get("active_count"),
            "health_status": last_status,
            "health": last_payload,
            "process_returncode": proc.poll(),
            "log_tail": lines[-80:],
        }
    finally:
        _terminate_process(proc)


async def main() -> None:
    plan = build_probe_plan(os.environ)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not _bool_env(os.getenv(RUN_ENV)):
        print()
        print("DRY RUN - no runtime process started.")
        print(f"Set {RUN_ENV}=true only after active PG runtime profile approval.")
        return

    result = await run_probe(os.environ)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
