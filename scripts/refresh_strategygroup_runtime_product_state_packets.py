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


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _detail_source(
    *,
    status: str,
    owner_label: str,
    reason: str,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "owner_label": owner_label,
        "reason": reason,
    }
    if summary is not None:
        payload["summary"] = summary
    return payload


def _real_order_readiness_fallback(
    runtime_goal_status: dict[str, Any],
) -> dict[str, Any]:
    matrix = runtime_goal_status.get("real_order_readiness_matrix")
    rows = [item for item in matrix if isinstance(item, dict)] if isinstance(matrix, list) else []
    owner_state = (
        runtime_goal_status.get("owner_state")
        if isinstance(runtime_goal_status.get("owner_state"), dict)
        else {}
    )
    submit_blocking_keys = [
        str(item.get("key"))
        for item in rows
        if item.get("blocks_real_submit") is True and item.get("key")
    ]
    waiting_count = sum(
        1
        for item in rows
        if str(item.get("status") or "").startswith("waiting")
    )
    blocked_count = sum(
        1 for item in rows if str(item.get("status") or "") == "blocked"
    )
    pass_count = sum(1 for item in rows if str(item.get("status") or "") == "pass")
    ready = _goal_status_ready_for_real_order_action(runtime_goal_status)
    status = (
        "ready_for_real_order"
        if ready
        else "waiting_for_market"
        if submit_blocking_keys == ["fresh_signal"] or waiting_count
        else "blocked"
        if blocked_count
        else "unavailable"
    )
    owner_label = (
        "可进入实盘动作"
        if ready
        else "等待机会"
        if status == "waiting_for_market"
        else "实盘边界暂不可用"
    )
    return {
        "status": status,
        "owner_label": owner_label,
        "owner_detail": str(owner_state.get("detail") or owner_label),
        "ready_for_real_order_action": ready,
        "pass_count": pass_count,
        "waiting_count": waiting_count,
        "blocked_count": blocked_count,
        "submit_blocking_keys": submit_blocking_keys,
        "next_safe_checkpoint": str(
            runtime_goal_status.get("next_safe_checkpoint")
            or owner_state.get("next_safe_checkpoint")
            or "refresh_runtime_goal_status"
        ),
        "matrix": rows,
        "source_health": _detail_source(
            status="ready_empty" if status == "waiting_for_market" else "degraded",
            owner_label=owner_label,
            reason=str(runtime_goal_status.get("status") or "runtime_goal_status"),
        ),
    }


def _goal_status_ready_for_real_order_action(
    goal_status_packet: dict[str, Any],
) -> bool:
    ready_value = goal_status_packet.get("ready_for_real_order_action")
    if isinstance(ready_value, bool):
        return ready_value
    checks = (
        goal_status_packet.get("checks")
        if isinstance(goal_status_packet.get("checks"), dict)
        else {}
    )
    ready_value = checks.get("ready_for_real_order_action")
    if isinstance(ready_value, bool):
        return ready_value
    boundary = (
        goal_status_packet.get("real_order_boundary")
        if isinstance(goal_status_packet.get("real_order_boundary"), dict)
        else {}
    )
    return boundary.get("ready_for_real_order_action") is True


def _source_readiness_fallback_packet(
    *,
    output_dir: Path,
    generated_at_ms: int,
    selected_strategy_group_id: str | None,
    max_symbols: int | None,
    stale_after_seconds: int | None,
    reason: str,
) -> dict[str, Any]:
    dry_run = _read_json_if_exists(output_dir / "runtime-dry-run-audit-chain.json")
    if not dry_run:
        dry_run = _read_json_if_exists(
            output_dir / "dry-run-audit-chain" / "runtime-dry-run-audit-chain.json"
        )
    goal_status = _read_json_if_exists(output_dir / "strategygroup-runtime-goal-status.json")
    live_facts = _read_json_if_exists(output_dir / "strategy-group-live-facts-readiness.json")
    deploy_channel = _deploy_channel_fallback_source(output_dir)

    dry_run_ready = dry_run.get("status") == "passed" and (
        (dry_run.get("checks") or {}).get("dangerous_effects_absent") is True
    )
    live_facts_status = str(live_facts.get("status") or "")
    live_facts_source = _detail_source(
        status="degraded" if live_facts else "unavailable",
        owner_label="事实状态暂不可用",
        reason=live_facts_status or "live_facts_readiness_source_missing",
        summary={
            "blocker_count": len(live_facts.get("blockers") or []),
        }
        if live_facts
        else None,
    )
    real_order_readiness = _real_order_readiness_fallback(goal_status)
    source_health = {
        "strategy_catalog": _detail_source(
            status="degraded",
            owner_label="策略组暂不可用",
            reason="source_readiness_api_unavailable",
        ),
        "runtime_source": _detail_source(
            status="unavailable",
            owner_label="运行状态源未连接",
            reason=reason,
        ),
        "watcher": _detail_source(
            status="unavailable",
            owner_label="观察状态暂不可用",
            reason=reason,
        ),
        "live_facts": live_facts_source,
        "funds": _detail_source(
            status="unavailable",
            owner_label="资金状态暂不可用",
            reason="account_readmodel_not_refreshed",
        ),
        "orders": _detail_source(
            status="unavailable",
            owner_label="订单状态暂不可用",
            reason="orders_readmodel_not_refreshed",
        ),
        "positions": _detail_source(
            status="unavailable",
            owner_label="持仓状态暂不可用",
            reason="positions_readmodel_not_refreshed",
        ),
        "protection": _detail_source(
            status="unavailable",
            owner_label="保护状态暂不可用",
            reason="protection_readmodel_not_refreshed",
        ),
        "reconciliation": _detail_source(
            status="degraded",
            owner_label="对账详情暂不可用",
            reason="source_readiness_api_unavailable",
        ),
        "operation_audit": _detail_source(
            status="unavailable",
            owner_label="审计详情暂不可用",
            reason="source_readiness_api_unavailable",
        ),
        "runtime_dry_run_audit": _detail_source(
            status="ready" if dry_run_ready else "degraded",
            owner_label="审计演练正常" if dry_run_ready else "审计演练需检查",
            reason=str(dry_run.get("status") or "runtime_dry_run_audit_missing"),
            summary={
                "scenario_count": dry_run.get("scenario_count"),
                "dangerous_effects_absent": (
                    (dry_run.get("checks") or {}).get("dangerous_effects_absent")
                    is True
                ),
            },
        ),
        "strategygroup_runtime_goal_status": _detail_source(
            status="degraded" if goal_status else "unavailable",
            owner_label=str(
                (goal_status.get("owner_state") or {}).get("label")
                or "目标状态暂不可用"
            ),
            reason=str(goal_status.get("status") or "strategygroup_runtime_goal_status_missing"),
        ),
        "real_order_readiness": real_order_readiness["source_health"],
        "deploy_channel": deploy_channel,
    }
    critical_unavailable = [
        name
        for name in ("runtime_source", "watcher")
        if source_health[name]["status"] == "unavailable"
    ]
    owner_label = str(
        (goal_status.get("owner_state") or {}).get("label")
        or "暂不可用"
    )
    return {
        "scope": "owner_console_source_readiness",
        "status": "source_unavailable",
        "generated_at_ms": generated_at_ms,
        "selected_scope_config": {
            "selected_strategy_group_id": selected_strategy_group_id,
            "max_symbols": max_symbols,
            "stale_after_seconds": stale_after_seconds,
        },
        "source_paths": {
            "runtime_dry_run_audit_chain_path": str(
                output_dir / "runtime-dry-run-audit-chain.json"
            ),
            "strategygroup_runtime_goal_status_path": str(
                output_dir / "strategygroup-runtime-goal-status.json"
            ),
            "tokyo_deploy_channel_status_path": str(
                output_dir / "tokyo-deploy-channel-status.json"
            ),
            "tokyo_readonly_probe_status_path": str(
                output_dir / "tokyo-readonly-probe-current.json"
            ),
            "watcher_report_dir": str(output_dir),
        },
        "owner_state": {
            "status": "temporarily_unavailable",
            "label": owner_label,
            "blocked_reason": reason,
            "next_safe_checkpoint": str(
                (goal_status.get("owner_state") or {}).get("next_safe_checkpoint")
                or "restore_owner_console_readmodel_api"
            ),
        },
        "owner_summary": {
            "strategy_groups": "暂不可用",
            "watcher": source_health["watcher"]["owner_label"],
            "market_opportunity": owner_label,
            "funds": source_health["funds"]["owner_label"],
            "orders": source_health["orders"]["owner_label"],
            "positions": source_health["positions"]["owner_label"],
            "protection": source_health["protection"]["owner_label"],
            "reconciliation": source_health["reconciliation"]["owner_label"],
            "operation_audit": source_health["operation_audit"]["owner_label"],
            "runtime_dry_run_audit": source_health["runtime_dry_run_audit"][
                "owner_label"
            ],
            "runtime_goal_status": source_health["strategygroup_runtime_goal_status"][
                "owner_label"
            ],
            "real_order_readiness": real_order_readiness["owner_label"],
            "deploy_channel": source_health["deploy_channel"]["owner_label"],
        },
        "strategy_groups": [],
        "source_health": source_health,
        "real_order_readiness": real_order_readiness,
        "critical_unavailable_sources": critical_unavailable,
        "frontend_contract": {
            "single_api_source": True,
            "hide_strategy_groups_when_runtime_degraded": False,
            "ready_empty_is_not_unavailable": True,
            "owner_homepage_internal_gate_terms_allowed": False,
        },
        "raw_status_refs": {
            "runtime_dry_run_audit_status": dry_run.get("status"),
            "strategygroup_runtime_goal_status": goal_status.get("status"),
            "live_facts_readiness_status": live_facts_status,
            "tokyo_deploy_channel_status": deploy_channel.get("summary", {}).get(
                "source_status"
            ),
            "tokyo_deploy_channel_blockers": list(
                deploy_channel.get("summary", {}).get("blockers") or []
            )[:20],
            "fallback_reason": reason,
        },
        "safety_invariants": {
            "read_model_only": True,
            "fallback_packet_only": True,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "runtime_budget_mutated": False,
            "creates_candidate": False,
            "creates_authorization": False,
            "withdrawal_or_transfer_created": False,
            "mutates_pg": False,
            "secrets_printed": False,
        },
    }


def _deploy_channel_fallback_source(output_dir: Path) -> dict[str, Any]:
    deploy_channel = _read_json_if_exists(output_dir / "tokyo-deploy-channel-status.json")
    if not deploy_channel:
        readonly_probe = _read_json_if_exists(output_dir / "tokyo-readonly-probe-current.json")
        if readonly_probe.get("scope") == "tokyo_runtime_governance_readonly_probe":
            deploy_channel = readonly_probe

    checks = (
        deploy_channel.get("checks")
        if isinstance(deploy_channel.get("checks"), dict)
        else {}
    )
    blockers = sorted(
        {
            str(item)
            for key in ("blockers", "tokyo_probe_blockers", "tokyo_connectivity_blockers")
            for item in (checks.get(key) or [])
            if str(item)
        }
    )
    source_status = str(deploy_channel.get("status") or "")
    connectivity_ready = checks.get("tokyo_connectivity_probe_ready")
    if blockers or source_status == "blocked" or connectivity_ready is False:
        return _detail_source(
            status="degraded",
            owner_label="部署通道暂不可用",
            reason=(
                ",".join(blockers)
                if blockers
                else source_status or "tokyo_deploy_channel_blocked"
            ),
            summary={
                "checked": True,
                "connectivity_ready": connectivity_ready,
                "blockers": blockers[:20],
                "source_status": source_status,
            },
        )
    if source_status in {
        "ready",
        "ready_for_owner_git_deploy_decision",
        "ready_for_deploy_apply",
        "postdeploy_accepted",
    } or connectivity_ready is True:
        return _detail_source(
            status="ready",
            owner_label="部署通道正常",
            reason=source_status or "tokyo_deploy_channel_ready",
            summary={
                "checked": True,
                "connectivity_ready": connectivity_ready,
                "blockers": [],
                "source_status": source_status,
            },
        )
    return _detail_source(
        status="ready_empty",
        owner_label="部署通道未检查",
        reason="tokyo_deploy_channel_status_missing",
        summary={
            "checked": False,
            "connectivity_ready": None,
            "blockers": [],
            "source_status": source_status,
        },
    )


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
    refresh_chain_closure_status: bool = False,
    chain_closure_output_json: Path | None = None,
    chain_closure_status_builder: Callable[..., dict[str, Any]] | None = None,
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
    refreshed_dry_run_packet: dict[str, Any] | None = None
    resolved_dry_run_output_json: Path | None = None
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
            refreshed_dry_run_packet = dry_run_packet
            _write_json(resolved_dry_run_output_json, dry_run_packet)
            goal_status_dry_run_json = output_dir / DEFAULT_DRY_RUN_OUTPUT_JSON.name
            if (
                resolved_dry_run_output_json.resolve()
                != goal_status_dry_run_json.resolve()
            ):
                _write_json(goal_status_dry_run_json, dry_run_packet)
            dry_run_audit_refresh = {
                "enabled": True,
                "status": dry_run_packet.get("status"),
                "output_json": str(resolved_dry_run_output_json),
                "output_dir": str(resolved_dry_run_output_dir),
                "goal_status_input_json": str(goal_status_dry_run_json),
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

    chain_closure_status_refresh: dict[str, Any] = {
        "enabled": refresh_chain_closure_status,
        "status": "skipped",
    }
    if refresh_chain_closure_status:
        from scripts.runtime_execution_chain_closure_status import (
            DEFAULT_OUTPUT_JSON as DEFAULT_CHAIN_CLOSURE_OUTPUT_JSON,
            build_status_packet,
        )

        builder = chain_closure_status_builder or build_status_packet
        resolved_chain_closure_output_json = (
            chain_closure_output_json
            or output_dir / DEFAULT_CHAIN_CLOSURE_OUTPUT_JSON.name
        )
        try:
            audit_packet = refreshed_dry_run_packet
            audit_source_json = resolved_dry_run_output_json
            if audit_packet is None:
                audit_source_json = output_dir / "runtime-dry-run-audit-chain.json"
                audit_packet = _read_json_if_exists(audit_source_json)
            if not audit_packet:
                blockers.append("runtime_chain_closure_status_audit_missing")
                chain_closure_status_refresh = {
                    "enabled": True,
                    "status": "failed",
                    "output_json": str(resolved_chain_closure_output_json),
                    "audit_json": str(audit_source_json) if audit_source_json else None,
                }
            else:
                closure_packet = builder(audit_packet=audit_packet)
                _write_json(resolved_chain_closure_output_json, closure_packet)
                chain_closure_status_refresh = {
                    "enabled": True,
                    "status": closure_packet.get("status"),
                    "output_json": str(resolved_chain_closure_output_json),
                    "audit_json": str(audit_source_json) if audit_source_json else None,
                    "real_order_allowed": (
                        (closure_packet.get("real_execution") or {}).get(
                            "real_order_allowed"
                        )
                        is True
                    ),
                    "missing_live_proof_count": len(
                        (closure_packet.get("real_execution") or {}).get(
                            "missing_live_proofs"
                        )
                        or []
                    ),
                }
                if (
                    closure_packet.get("status")
                    != "non_market_execution_chain_ready"
                ):
                    blockers.append("runtime_chain_closure_status_not_ready")
        except Exception as exc:
            blockers.append(f"runtime_chain_closure_status_failed:{type(exc).__name__}")
            warnings.append(str(exc))
            chain_closure_status_refresh = {
                "enabled": True,
                "status": "failed",
                "output_json": str(resolved_chain_closure_output_json),
            }

    if cookie is None:
        try:
            cookie = _operator_cookie()
        except Exception as exc:
            blockers.append(f"operator_cookie_unavailable:{type(exc).__name__}")
            warnings.append(str(exc))

    api_root = api_base.rstrip("/")
    source_readiness_fallback: dict[str, Any] = {
        "enabled": False,
        "status": "skipped",
    }
    if cookie is None:
        for endpoint, filename in ENDPOINTS:
            output_path = output_dir / filename
            blockers.append(f"{filename}:refresh_skipped:operator_cookie_unavailable")
            if filename == "owner-console-source-readiness.json":
                fallback_packet = _source_readiness_fallback_packet(
                    output_dir=output_dir,
                    generated_at_ms=generated_at_ms,
                    selected_strategy_group_id=selected_strategy_group_id,
                    max_symbols=max_symbols,
                    stale_after_seconds=stale_after_seconds,
                    reason="operator_cookie_unavailable",
                )
                _write_json(output_path, fallback_packet)
                source_readiness_fallback = {
                    "enabled": True,
                    "status": fallback_packet.get("status"),
                    "output_json": str(output_path),
                    "reason": "operator_cookie_unavailable",
                }
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
            fallback_goal_status_json = output_dir / DEFAULT_GOAL_STATUS_OUTPUT_JSON.name
            if (
                resolved_goal_status_output_json.resolve()
                != fallback_goal_status_json.resolve()
            ):
                _write_json(fallback_goal_status_json, goal_status_packet)
            goal_status_refresh = {
                "enabled": True,
                "status": goal_status_packet.get("status"),
                "output_json": str(resolved_goal_status_output_json),
                "fallback_input_json": str(fallback_goal_status_json),
                "next_safe_checkpoint": (
                    goal_status_packet.get("next_safe_checkpoint")
                    or (goal_status_packet.get("owner_state") or {}).get(
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
                    _goal_status_ready_for_real_order_action(goal_status_packet)
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

    if cookie is None:
        fallback_path = output_dir / "owner-console-source-readiness.json"
        fallback_packet = _source_readiness_fallback_packet(
            output_dir=output_dir,
            generated_at_ms=generated_at_ms,
            selected_strategy_group_id=selected_strategy_group_id,
            max_symbols=max_symbols,
            stale_after_seconds=stale_after_seconds,
            reason="operator_cookie_unavailable",
        )
        _write_json(fallback_path, fallback_packet)
        source_readiness_fallback = {
            "enabled": True,
            "status": fallback_packet.get("status"),
            "output_json": str(fallback_path),
            "reason": "operator_cookie_unavailable",
            "goal_status_included": bool(
                fallback_packet.get("raw_status_refs", {}).get(
                    "strategygroup_runtime_goal_status"
                )
            ),
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
        "chain_closure_status_refresh": chain_closure_status_refresh,
        "goal_status_refresh": goal_status_refresh,
        "source_readiness_fallback": source_readiness_fallback,
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
            "optional_chain_closure_status_refresh": refresh_chain_closure_status,
            "optional_goal_status_refresh": refresh_goal_status,
            "optional_source_readiness_fallback": source_readiness_fallback.get(
                "enabled"
            )
            is True,
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
    parser.add_argument("--refresh-chain-closure-status", action="store_true")
    parser.add_argument("--chain-closure-output-json")
    parser.add_argument("--refresh-goal-status", action="store_true")
    parser.add_argument("--goal-status-output-json")
    parser.add_argument("--release-manifest")
    parser.add_argument("--expected-head")
    parser.add_argument(
        "--allow-degraded-local-refresh-success",
        action="store_true",
        help=(
            "Return exit code 0 when local operator auth is unavailable but "
            "non-executing dry-run audit and goal-status refresh completed "
            "with only operator-cookie skip blockers. This is for local "
            "long-running goal loops; server/systemd runs should keep the "
            "default fail-visible exit behavior."
        ),
    )
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


def _degraded_local_refresh_is_continuable(packet: dict[str, Any]) -> bool:
    if packet.get("status") != "refresh_blocked":
        return False
    blockers = [str(item) for item in packet.get("blockers") or []]
    if not blockers:
        return False
    if not all(
        blocker.startswith("operator_cookie_unavailable:")
        or blocker.endswith(":refresh_skipped:operator_cookie_unavailable")
        for blocker in blockers
    ):
        return False
    dry_run = packet.get("dry_run_audit_refresh")
    if isinstance(dry_run, dict) and dry_run.get("enabled") is True:
        if dry_run.get("status") != "passed":
            return False
    goal_status = packet.get("goal_status_refresh")
    if isinstance(goal_status, dict) and goal_status.get("enabled") is True:
        if goal_status.get("status") in {None, "failed"}:
            return False
        if goal_status.get("runtime_dry_run_audit_passed") is not True:
            return False
    fallback = packet.get("source_readiness_fallback")
    if not isinstance(fallback, dict):
        return False
    if fallback.get("enabled") is not True:
        return False
    if fallback.get("reason") != "operator_cookie_unavailable":
        return False
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        return False
    forbidden_flags = (
        "exchange_write_called",
        "order_created",
        "order_lifecycle_called",
        "execution_intent_created",
        "runtime_budget_mutated",
        "withdrawal_or_transfer_created",
        "places_order",
        "mutates_pg",
    )
    return not any(safety.get(name) is True for name in forbidden_flags)


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
        refresh_chain_closure_status=args.refresh_chain_closure_status,
        chain_closure_output_json=(
            Path(args.chain_closure_output_json).expanduser()
            if args.chain_closure_output_json
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
    exit_code = 0 if packet["status"] == "refreshed" else 2
    if (
        args.allow_degraded_local_refresh_success
        and _degraded_local_refresh_is_continuable(packet)
    ):
        exit_code = 0
        packet["cli_exit_policy"] = {
            "status": "degraded_local_refresh_continuable",
            "exit_code": 0,
            "reason": "operator_cookie_unavailable_with_local_audit_refresh_complete",
        }
    if args.output_json:
        _write_json(Path(args.output_json).expanduser(), packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
