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
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable
import urllib.request
import urllib.parse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_API_BASE = "http://127.0.0.1:18080"
DEFAULT_OUTPUT_DIR = Path("/home/ubuntu/brc-deploy/reports/runtime-signal-watcher")
DEFAULT_LIVE_FACTS_FILENAME = "strategy-group-live-facts-input.json"
ENDPOINTS = (
    (
        "/api/trading-console/strategy-group-live-facts-readiness",
        "strategy-group-live-facts-readiness.json",
    ),
    (
        "/api/trading-console/owner-console-source-readiness",
        "owner-console-source-readiness.json",
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


def _runtime_pilot_status_query(
    *,
    selected_strategy_group_id: str | None,
    max_symbols: int | None,
    stale_after_seconds: int | None,
) -> str:
    query: dict[str, str] = {}
    if selected_strategy_group_id:
        query["selected_strategy_group_id"] = selected_strategy_group_id
    if max_symbols is not None:
        query["max_symbols"] = str(max_symbols)
    if stale_after_seconds is not None:
        query["stale_after_seconds"] = str(stale_after_seconds)
    return urllib.parse.urlencode(query)


def refresh_packets(
    *,
    api_base: str,
    output_dir: Path,
    label: str,
    timeout_seconds: int = 30,
    cookie: str | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
    generated_at_ms: int | None = None,
    collect_live_facts_before_refresh: bool = False,
    handoff_dir: Path | None = None,
    env_file: Path | None = None,
    live_facts_output: Path | None = None,
    live_facts_base_url: str | None = None,
    live_facts_collector: Callable[..., dict[str, Any]] | None = None,
    selected_strategy_group_id: str | None = None,
    max_symbols: int | None = None,
    stale_after_seconds: int | None = None,
    refresh_dry_run_audit_chain: bool = False,
    dry_run_output_dir: Path | None = None,
    dry_run_output_json: Path | None = None,
    dry_run_builder: Callable[..., dict[str, Any]] | None = None,
    refresh_goal_status: bool = False,
    goal_status_output_json: Path | None = None,
    release_manifest: Path | None = None,
    expected_head: str | None = None,
    goal_status_builder: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generated_at_ms = generated_at_ms or int(time.time() * 1000)
    output_dir.mkdir(parents=True, exist_ok=True)

    packets: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    live_facts_precollect: dict[str, Any] = {
        "enabled": collect_live_facts_before_refresh,
        "status": "skipped",
    }
    if collect_live_facts_before_refresh:
        from scripts.collect_strategy_group_live_facts_readonly import (
            DEFAULT_BASE_URL,
            DEFAULT_HANDOFF_DIR,
            collect_live_facts,
        )

        collector = live_facts_collector or collect_live_facts
        resolved_handoff_dir = handoff_dir or DEFAULT_HANDOFF_DIR
        resolved_env_file = env_file
        resolved_live_facts_output = (
            live_facts_output or output_dir / DEFAULT_LIVE_FACTS_FILENAME
        )
        try:
            live_facts_packet = collector(
                handoff_dir=resolved_handoff_dir,
                env_file=resolved_env_file,
                base_url=live_facts_base_url or DEFAULT_BASE_URL,
            )
            _write_json(resolved_live_facts_output, live_facts_packet)
            live_facts_precollect = {
                "enabled": True,
                "status": live_facts_packet.get("status"),
                "output_json": str(resolved_live_facts_output),
                "collector_error_count": len(
                    live_facts_packet.get("collector_errors") or {}
                ),
                "signed_get_only": bool(
                    (live_facts_packet.get("safety_invariants") or {}).get(
                        "signed_get_only"
                    )
                ),
            }
            if live_facts_packet.get("collector_errors"):
                warnings.append("live_facts_precollect_partial")
        except Exception as exc:
            blockers.append(f"live_facts_precollect_failed:{type(exc).__name__}")
            warnings.append(str(exc))
            live_facts_precollect = {
                "enabled": True,
                "status": "failed",
                "output_json": str(resolved_live_facts_output),
            }

    dry_run_audit_refresh: dict[str, Any] = {
        "enabled": refresh_dry_run_audit_chain,
        "status": "skipped",
    }
    if refresh_dry_run_audit_chain:
        from scripts.runtime_dry_run_audit_chain import (
            DEFAULT_OUTPUT_JSON as DEFAULT_DRY_RUN_OUTPUT_JSON,
            build_audit_chain,
        )

        builder = dry_run_builder or build_audit_chain
        resolved_dry_run_output_dir = dry_run_output_dir or output_dir / "dry-run-audit-chain"
        resolved_dry_run_output_json = (
            dry_run_output_json or output_dir / DEFAULT_DRY_RUN_OUTPUT_JSON.name
        )
        try:
            dry_run_packet = builder(resolved_dry_run_output_dir)
            _write_json(resolved_dry_run_output_json, dry_run_packet)
            dry_run_audit_refresh = {
                "enabled": True,
                "status": dry_run_packet.get("status"),
                "output_json": str(resolved_dry_run_output_json),
                "output_dir": str(resolved_dry_run_output_dir),
                "scenario_count": dry_run_packet.get("scenario_count"),
                "dangerous_effects_absent": (
                    (dry_run_packet.get("checks") or {}).get(
                        "dangerous_effects_absent"
                    )
                    is True
                ),
            }
            if dry_run_packet.get("status") != "passed":
                blockers.append("runtime_dry_run_audit_chain_not_passed")
        except Exception as exc:
            blockers.append(f"runtime_dry_run_audit_chain_failed:{type(exc).__name__}")
            warnings.append(str(exc))
            dry_run_audit_refresh = {
                "enabled": True,
                "status": "failed",
                "output_json": str(resolved_dry_run_output_json),
                "output_dir": str(resolved_dry_run_output_dir),
            }

    if cookie is None:
        try:
            cookie = _operator_cookie()
        except Exception as exc:
            blockers.append(f"operator_cookie_unavailable:{type(exc).__name__}")
            warnings.append(str(exc))

    api_root = api_base.rstrip("/")
    if cookie is None:
        for endpoint, filename in ENDPOINTS:
            output_path = output_dir / filename
            blockers.append(f"{filename}:refresh_skipped:operator_cookie_unavailable")
            packets.append(
                {
                    "endpoint": endpoint,
                    "output_json": str(output_path),
                    "status": "skipped_operator_cookie_unavailable",
                    "api_freshness_status": None,
                    "api_blocker_count": 1,
                    "api_warning_count": 1,
                }
            )
    else:
        for endpoint, filename in ENDPOINTS:
            query = ""
            if endpoint in {
                "/api/trading-console/strategygroup-runtime-pilot-status",
                "/api/trading-console/owner-console-source-readiness",
            }:
                query = _runtime_pilot_status_query(
                    selected_strategy_group_id=selected_strategy_group_id,
                    max_symbols=max_symbols,
                    stale_after_seconds=stale_after_seconds,
                )
            url = f"{api_root}{endpoint}" + (f"?{query}" if query else "")
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

    goal_status_refresh: dict[str, Any] = {
        "enabled": refresh_goal_status,
        "status": "skipped",
    }
    if refresh_goal_status:
        from scripts.build_strategygroup_runtime_goal_status import (
            DEFAULT_OUTPUT_JSON as DEFAULT_GOAL_STATUS_OUTPUT_JSON,
            build_goal_status_packet,
        )

        builder = goal_status_builder or build_goal_status_packet
        resolved_goal_status_output_json = (
            goal_status_output_json or output_dir / DEFAULT_GOAL_STATUS_OUTPUT_JSON.name
        )
        try:
            goal_status_packet = builder(
                report_dir=output_dir,
                release_manifest=release_manifest,
                expected_head=expected_head,
            )
            _write_json(resolved_goal_status_output_json, goal_status_packet)
            goal_status_refresh = {
                "enabled": True,
                "status": goal_status_packet.get("status"),
                "output_json": str(resolved_goal_status_output_json),
                "next_safe_checkpoint": (
                    (goal_status_packet.get("owner_state") or {}).get(
                        "next_safe_checkpoint"
                    )
                ),
                "runtime_dry_run_audit_passed": (
                    (goal_status_packet.get("checks") or {}).get(
                        "runtime_dry_run_audit_passed"
                    )
                    is True
                ),
                "ready_for_real_order_action": (
                    (goal_status_packet.get("real_order_boundary") or {}).get(
                        "ready_for_real_order_action"
                    )
                    is True
                ),
            }
        except Exception as exc:
            blockers.append(f"strategygroup_runtime_goal_status_failed:{type(exc).__name__}")
            warnings.append(str(exc))
            goal_status_refresh = {
                "enabled": True,
                "status": "failed",
                "output_json": str(resolved_goal_status_output_json),
            }

    status = "refreshed" if not blockers else "refresh_blocked"
    return {
        "scope": "strategygroup_runtime_product_state_refresh",
        "label": label,
        "status": status,
        "generated_at_ms": generated_at_ms,
        "packets": packets,
        "live_facts_precollect": live_facts_precollect,
        "dry_run_audit_refresh": dry_run_audit_refresh,
        "goal_status_refresh": goal_status_refresh,
        "blockers": blockers,
        "warnings": warnings,
        "selected_scope_config": {
            "selected_strategy_group_id": selected_strategy_group_id,
            "max_symbols": max_symbols,
            "stale_after_seconds": stale_after_seconds,
            "source": "cli_or_env" if selected_strategy_group_id else "default",
        },
        "safety_invariants": {
            "readmodel_refresh_only": True,
            "optional_signed_get_live_facts_precollect": collect_live_facts_before_refresh,
            "optional_dry_run_audit_chain_refresh": refresh_dry_run_audit_chain,
            "optional_goal_status_refresh": refresh_goal_status,
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
    parser.add_argument("--collect-live-facts-before-refresh", action="store_true")
    parser.add_argument("--handoff-dir")
    parser.add_argument("--env-file")
    parser.add_argument("--live-facts-output")
    parser.add_argument("--live-facts-base-url")
    parser.add_argument("--refresh-dry-run-audit-chain", action="store_true")
    parser.add_argument("--dry-run-output-dir")
    parser.add_argument("--dry-run-output-json")
    parser.add_argument("--refresh-goal-status", action="store_true")
    parser.add_argument("--goal-status-output-json")
    parser.add_argument("--release-manifest")
    parser.add_argument("--expected-head")
    parser.add_argument(
        "--selected-strategy-group-id",
        default=os.environ.get("BRC_SELECTED_STRATEGY_GROUP_ID")
        or os.environ.get("BRC_STRATEGYGROUP_SELECTED_ID"),
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=(
            int(os.environ["BRC_STRATEGYGROUP_MAX_SYMBOLS"])
            if os.environ.get("BRC_STRATEGYGROUP_MAX_SYMBOLS")
            else None
        ),
    )
    parser.add_argument(
        "--stale-after-seconds",
        type=int,
        default=(
            int(os.environ["BRC_STRATEGYGROUP_STALE_AFTER_SECONDS"])
            if os.environ.get("BRC_STRATEGYGROUP_STALE_AFTER_SECONDS")
            else None
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = refresh_packets(
        api_base=args.api_base,
        output_dir=Path(args.output_dir).expanduser(),
        label=args.label,
        timeout_seconds=args.timeout_seconds,
        collect_live_facts_before_refresh=args.collect_live_facts_before_refresh,
        handoff_dir=Path(args.handoff_dir).expanduser() if args.handoff_dir else None,
        env_file=Path(args.env_file).expanduser() if args.env_file else None,
        live_facts_output=(
            Path(args.live_facts_output).expanduser()
            if args.live_facts_output
            else None
        ),
        live_facts_base_url=args.live_facts_base_url,
        selected_strategy_group_id=args.selected_strategy_group_id,
        max_symbols=args.max_symbols,
        stale_after_seconds=args.stale_after_seconds,
        refresh_dry_run_audit_chain=args.refresh_dry_run_audit_chain,
        dry_run_output_dir=(
            Path(args.dry_run_output_dir).expanduser()
            if args.dry_run_output_dir
            else None
        ),
        dry_run_output_json=(
            Path(args.dry_run_output_json).expanduser()
            if args.dry_run_output_json
            else None
        ),
        refresh_goal_status=args.refresh_goal_status,
        goal_status_output_json=(
            Path(args.goal_status_output_json).expanduser()
            if args.goal_status_output_json
            else None
        ),
        release_manifest=(
            Path(args.release_manifest).expanduser()
            if args.release_manifest
            else None
        ),
        expected_head=args.expected_head,
    )
    if args.output_json:
        _write_json(Path(args.output_json).expanduser(), packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["status"] == "refreshed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
