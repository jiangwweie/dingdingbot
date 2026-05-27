#!/usr/bin/env python3
"""BRC Owner Console smoke helper.

HTTP mode expects a running backend. It signs a short-lived local operator
session from .env/.env.local by default and exercises read-only + Operation
preflight/cancel/wrong-confirm/get/list paths.

Runtime-bound-test mode uses the in-memory test service to prove that
switch_playbook can preflight and confirm successfully when BRC campaign,
account facts, audit, and operation repository services are bound.

Runtime-bound-evidence mode uses the same bounded service context and emits a
local evidence packet for Owner Console verification. It does not start live,
generic trading, actual flatten, order cancel/close, withdrawal/transfer, or
LLM direct execution.

TF-001 carrier decision review mode checks whether the current Operation Layer
can carry TF-001 without expanding authority.

TF-001 carrier full-chain mode validates the bounded third-stage trial flow:
select playbook, confirm, enter monitor carrier, pause, stop runtime, and write
the review decision. It does not start live/mainnet, generic trading, actual
flatten, order cancel/close, withdrawal/transfer, or LLM direct execution.
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


def _clean_reconciled_market_state(evidence_ref: str) -> dict[str, Any]:
    return {
        "active_position_count": 0,
        "open_order_count": 0,
        "all_local_flat": True,
        "source": "mixed",
        "truth_level": "reconciled",
        "data_source": "mixed",
        "reconciliation_status": {"status": "clean", "checked_sources": ["local_pg", "exchange_testnet"]},
        "reconciliation_status_value": "clean",
        "checked_sources": ["local_pg", "exchange_testnet"],
        "source_snapshots": {
            "local_pg": {"available": True, "position_count": 0, "open_order_count": 0},
            "exchange_testnet": {"available": True, "position_count": 0, "open_order_count": 0},
            "exchange_live": {"available": False, "reason": "forbidden in Owner Console account facts slice"},
        },
        "evidence_refs": [evidence_ref],
        "mismatch_count": 0,
        "unknown_or_unmanaged_orders": [],
        "unknown_or_unmanaged_positions": [],
        "unknown_or_unmanaged_order_count": 0,
        "unknown_or_unmanaged_position_count": 0,
        "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
    }


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


async def run_runtime_bound_evidence_smoke() -> dict[str, Any]:
    from tests.unit.test_brc_operation_layer import _operation_service, _switch_preflight

    service, _, brc_repo, market = await _operation_service(
        market_state=_clean_reconciled_market_state("runtime-bound-evidence:account-facts-clean")
    )
    capabilities = {item.operation_type: item.model_dump(mode="json") for item in service.capabilities()}

    switch_preflight = await _switch_preflight(service)
    switch_confirm = await service.confirm(
        operation_id=switch_preflight.operation_id,
        preflight_id=switch_preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=switch_preflight.idempotency_key,
    )
    switch_detail = await service.get(switch_preflight.operation_id)

    stop_preflight = await service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={"reason_text": "runtime-bound evidence envelope only"},
        source={"kind": "runtime_bound_evidence", "ref": "brc_owner_console_smoke.py"},
    )
    stop_detail = await service.get(stop_preflight.operation_id)

    flatten_preflight = await service.preflight(
        operation_type="emergency_flatten",
        requested_by="owner",
        input_params={"reason_text": "runtime-bound dry-run evidence only"},
        source={"kind": "runtime_bound_evidence", "ref": "brc_owner_console_smoke.py"},
    )
    flatten_confirm = None
    if flatten_preflight.confirmation_requirement.required:
        flatten_confirm = await service.confirm(
            operation_id=flatten_preflight.operation_id,
            preflight_id=flatten_preflight.preflight_id,
            confirmation_phrase="CONFIRM_FLATTEN_DRY_RUN",
            idempotency_key=flatten_preflight.idempotency_key,
        )
    flatten_detail = await service.get(flatten_preflight.operation_id)

    listed = await service.list(limit=10)
    return {
        "mode": "runtime-bound-evidence",
        "generated_at_ms": int(time.time() * 1000),
        "safety_boundary": {
            "live_ready": False,
            "actual_flatten_executed": False,
            "order_cancel_executed": False,
            "close_position_executed": False,
            "withdrawal_or_transfer_executed": False,
            "llm_authorized_execution": False,
        },
        "capabilities": {
            key: {
                "status": value.get("status"),
                "executable_through_operation": value.get("executable_through_operation"),
                "dry_run_only": value.get("dry_run_only"),
                "current_reason": value.get("current_reason"),
            }
            for key, value in capabilities.items()
            if key in {"switch_playbook", "emergency_stop_runtime", "emergency_flatten", "live_execution", "withdrawal", "transfer"}
        },
        "account_facts_summary": {
            "source": market.get("source"),
            "truth_level": market.get("truth_level"),
            "reconciliation_status": market.get("reconciliation_status_value"),
            "checked_sources": market.get("checked_sources"),
            "mismatch_count": market.get("mismatch_count"),
            "unknown_unmanaged_counts": market.get("unknown_unmanaged_counts"),
            "evidence_refs": market.get("evidence_refs"),
        },
        "switch_playbook": {
            "preflight": {
                "operation_id": switch_preflight.operation_id,
                "preflight_id": switch_preflight.preflight_id,
                "decision": switch_preflight.decision,
                "status": switch_preflight.status,
                "idempotency_key_present": bool(switch_preflight.idempotency_key),
                "account_source": switch_preflight.account_order_summary.get("source"),
                "truth_level": switch_preflight.account_order_summary.get("truth_level"),
                "reconciliation_status": switch_preflight.account_order_summary.get("reconciliation_status_value"),
            },
            "confirm": {
                "status": switch_confirm.status,
                "operation_id": switch_confirm.operation_id,
                "preflight_id": switch_confirm.preflight_id,
                "campaign_refs": switch_confirm.campaign_refs,
                "audit_refs": switch_confirm.audit_refs,
            },
            "detail_status": switch_detail.operation.status,
            "campaign_playbook": brc_repo.campaign.current_playbook_id,
        },
        "emergency_stop_runtime": {
            "preflight": {
                "operation_id": stop_preflight.operation_id,
                "preflight_id": stop_preflight.preflight_id,
                "decision": stop_preflight.decision,
                "status": stop_preflight.status,
                "summary": stop_preflight.summary,
            },
            "result_status": stop_detail.result.status if stop_detail.result is not None else None,
            "does_not_flatten": True,
            "does_not_cancel_orders": True,
        },
        "emergency_flatten": {
            "preflight": {
                "operation_id": flatten_preflight.operation_id,
                "preflight_id": flatten_preflight.preflight_id,
                "decision": flatten_preflight.decision,
                "status": flatten_preflight.status,
                "dry_run_only": bool(flatten_preflight.after.get("dry_run_only")),
                "actual_execution_available": bool(flatten_preflight.after.get("actual_execution_available")),
            },
            "confirm_status": flatten_confirm.status if flatten_confirm is not None else None,
            "result_status": flatten_detail.result.status if flatten_detail.result is not None else None,
            "dry_run_id": (flatten_preflight.after.get("dry_run_plan") or {}).get("dry_run_id"),
            "actual_flatten_executed": False,
        },
        "operation_list": {
            "count": len(listed.operations),
            "operation_ids": [item.operation_id for item in listed.operations],
        },
    }


async def run_tf001_carrier_decision_review() -> dict[str, Any]:
    from tests.unit.test_brc_operation_layer import _operation_service

    service, _, brc_repo, market = await _operation_service(
        market_state=_clean_reconciled_market_state("tf001-carrier-decision-review:account-facts-clean")
    )
    capabilities = {item.operation_type: item.model_dump(mode="json") for item in service.capabilities()}

    switch_preflight = await service.preflight(
        operation_type="switch_playbook",
        requested_by="owner",
        input_params={
            "target_playbook_id": "TF-001",
            "reason_text": "TF-001 carrier validation decision review",
            "evidence_refs": ["docs/ops/brc-r5-001-tf001-carrier-full-chain-validation-plan.md"],
        },
        source={"kind": "tf001_carrier_decision_review", "ref": "brc_owner_console_smoke.py"},
    )
    switch_detail = await service.get(switch_preflight.operation_id)

    monitor_preflight = await service.preflight(
        operation_type="enter_strategy_or_monitor",
        requested_by="owner",
        input_params={
            "carrier_playbook_id": "TF-001",
            "carrier_role": "carrier_validation_only",
            "reason_text": "Validate monitor carrier path without strategy execution",
        },
        source={"kind": "tf001_carrier_decision_review", "ref": "brc_owner_console_smoke.py"},
    )
    monitor_confirm = await service.confirm(
        operation_id=monitor_preflight.operation_id,
        preflight_id=monitor_preflight.preflight_id,
        confirmation_phrase="CONFIRM_ENTER_MONITOR",
        idempotency_key=monitor_preflight.idempotency_key,
    )
    monitor_detail = await service.get(monitor_preflight.operation_id)

    listed = await service.list(limit=10)
    switch_result = switch_detail.result
    switch_ready = switch_preflight.decision == "allow" and switch_preflight.status == "awaiting_confirmation"
    return {
        "mode": "tf001-carrier-decision-review",
        "generated_at_ms": int(time.time() * 1000),
        "decision": {
            "tf001_switch_playbook_ready": switch_ready,
            "tf001_monitor_carrier_ready": monitor_confirm.status == "noop",
            "recommended_next_task": "BRC-R5-001 TF-001 carrier full-chain validation smoke",
            "reason": (
                "TF-001 is available as a carrier-validation playbook."
                if switch_ready
                else "TF-001 is not ready for switch_playbook execution."
            ),
        },
        "safety_boundary": {
            "live_ready": False,
            "strategy_execution_enabled": False,
            "actual_flatten_executed": False,
            "order_cancel_executed": False,
            "close_position_executed": False,
            "withdrawal_or_transfer_executed": False,
            "llm_authorized_execution": False,
        },
        "account_facts_summary": {
            "source": market.get("source"),
            "truth_level": market.get("truth_level"),
            "reconciliation_status": market.get("reconciliation_status_value"),
            "checked_sources": market.get("checked_sources"),
            "mismatch_count": market.get("mismatch_count"),
            "unknown_unmanaged_counts": market.get("unknown_unmanaged_counts"),
        },
        "capabilities": {
            "switch_playbook": {
                "status": capabilities["switch_playbook"].get("status"),
                "executable_through_operation": capabilities["switch_playbook"].get("executable_through_operation"),
            },
            "enter_strategy_or_monitor": {
                "status": capabilities["enter_strategy_or_monitor"].get("status"),
                "executable_through_operation": capabilities["enter_strategy_or_monitor"].get("executable_through_operation"),
                "reason": capabilities["enter_strategy_or_monitor"].get("current_reason"),
            },
            "live_execution": {
                "status": capabilities["live_execution"].get("status"),
                "executable_through_operation": capabilities["live_execution"].get("executable_through_operation"),
            },
        },
        "tf001_switch_playbook": {
            "preflight": {
                "operation_id": switch_preflight.operation_id,
                "preflight_id": switch_preflight.preflight_id,
                "decision": switch_preflight.decision,
                "status": switch_preflight.status,
                "target_playbook_id": switch_preflight.playbook_summary.get("target_playbook_id"),
                "known": switch_preflight.playbook_summary.get("known"),
                "allowlisted_ids": switch_preflight.playbook_summary.get("allowlisted_ids"),
                "blockers": switch_preflight.risk_summary.get("blockers", []),
            },
            "result_status": switch_result.status if switch_result is not None else None,
            "blocked_reason": switch_result.blocked_reason if switch_result is not None else None,
        },
        "tf001_monitor_carrier": {
            "preflight": {
                "operation_id": monitor_preflight.operation_id,
                "preflight_id": monitor_preflight.preflight_id,
                "decision": monitor_preflight.decision,
                "status": monitor_preflight.status,
                "idempotency_key_present": bool(monitor_preflight.idempotency_key),
                "target_state": monitor_preflight.after,
            },
            "confirm": {
                "status": monitor_confirm.status,
                "operation_id": monitor_confirm.operation_id,
                "preflight_id": monitor_confirm.preflight_id,
                "result_summary": monitor_confirm.result_summary,
                "final_state": monitor_confirm.next_state,
            },
            "detail_status": monitor_detail.operation.status,
        },
        "campaign_playbook_after_review": brc_repo.campaign.current_playbook_id,
        "operation_list": {
            "count": len(listed.operations),
            "operation_ids": [item.operation_id for item in listed.operations],
        },
    }


async def run_tf001_carrier_full_chain() -> dict[str, Any]:
    from tests.unit.test_brc_operation_layer import _operation_service

    service, _, brc_repo, market = await _operation_service(
        market_state=_clean_reconciled_market_state("tf001-carrier-full-chain:account-facts-clean"),
        runtime_stop_adapter=True,
    )
    capabilities = {item.operation_type: item.model_dump(mode="json") for item in service.capabilities()}

    switch_preflight = await service.preflight(
        operation_type="switch_playbook",
        requested_by="owner",
        input_params={
            "target_playbook_id": "TF-001",
            "reason_text": "TF-001 carrier full-chain validation selection",
            "evidence_refs": ["docs/ops/brc-r5-001-tf001-carrier-full-chain-validation-plan.md"],
        },
        source={"kind": "tf001_carrier_full_chain", "ref": "brc_owner_console_smoke.py"},
    )
    switch_confirm = await service.confirm(
        operation_id=switch_preflight.operation_id,
        preflight_id=switch_preflight.preflight_id,
        confirmation_phrase="CONFIRM_SWITCH_PLAYBOOK",
        idempotency_key=switch_preflight.idempotency_key,
    )

    monitor_preflight = await service.preflight(
        operation_type="enter_strategy_or_monitor",
        requested_by="owner",
        input_params={
            "carrier_playbook_id": "TF-001",
            "carrier_role": "carrier_validation_only",
            "reason_text": "Enter monitor carrier only; no strategy execution authority",
        },
        source={"kind": "tf001_carrier_full_chain", "ref": "brc_owner_console_smoke.py"},
    )
    monitor_confirm = await service.confirm(
        operation_id=monitor_preflight.operation_id,
        preflight_id=monitor_preflight.preflight_id,
        confirmation_phrase="CONFIRM_ENTER_MONITOR",
        idempotency_key=monitor_preflight.idempotency_key,
    )

    pause_preflight = await service.preflight(
        operation_type="enter_pause",
        requested_by="owner",
        input_params={"reason_text": "Pause new strategy actions during TF-001 carrier validation"},
        source={"kind": "tf001_carrier_full_chain", "ref": "brc_owner_console_smoke.py"},
    )
    pause_confirm = await service.confirm(
        operation_id=pause_preflight.operation_id,
        preflight_id=pause_preflight.preflight_id,
        confirmation_phrase="CONFIRM_ENTER_PAUSE",
        idempotency_key=pause_preflight.idempotency_key,
    )

    stop_preflight = await service.preflight(
        operation_type="emergency_stop_runtime",
        requested_by="owner",
        input_params={"reason_text": "Stop runtime carrier after TF-001 validation"},
        source={"kind": "tf001_carrier_full_chain", "ref": "brc_owner_console_smoke.py"},
    )
    stop_confirm = await service.confirm(
        operation_id=stop_preflight.operation_id,
        preflight_id=stop_preflight.preflight_id,
        confirmation_phrase="CONFIRM_STOP_RUNTIME",
        idempotency_key=stop_preflight.idempotency_key,
    )

    review_preflight = await service.preflight(
        operation_type="write_review_decision",
        requested_by="owner",
        input_params={
            "decision": "accepted",
            "reason_text": "TF-001 carrier full-chain validation completed as governance smoke only",
            "next_recommended_task": "Review TF-001 evidence packet before any strategy-family trial expansion",
            "metadata": {
                "carrier_playbook_id": "TF-001",
                "carrier_only": True,
                "alpha_or_profit_claim": False,
            },
        },
        source={"kind": "tf001_carrier_full_chain", "ref": "brc_owner_console_smoke.py"},
    )
    review_confirm = await service.confirm(
        operation_id=review_preflight.operation_id,
        preflight_id=review_preflight.preflight_id,
        confirmation_phrase="CONFIRM_WRITE_REVIEW",
        idempotency_key=review_preflight.idempotency_key,
    )

    listed = await service.list(limit=20)
    operation_ids = [item.operation_id for item in listed.operations]
    stages = {
        "select_playbook": switch_confirm.status,
        "confirm_selection": switch_confirm.status,
        "monitor": monitor_confirm.status,
        "pause": pause_confirm.status,
        "stop": stop_confirm.status,
        "review": review_confirm.status,
    }
    completed = (
        stages["select_playbook"] == "executed"
        and stages["confirm_selection"] == "executed"
        and stages["monitor"] == "noop"
        and stages["pause"] in {"executed", "noop"}
        and stages["stop"] == "executed"
        and stages["review"] == "executed"
        and brc_repo.campaign.current_playbook_id == "TF-001"
    )
    return {
        "mode": "tf001-carrier-full-chain",
        "generated_at_ms": int(time.time() * 1000),
        "objective": "select -> confirm -> monitor -> pause -> stop -> review",
        "completed": completed,
        "stage_statuses": stages,
        "safety_boundary": {
            "live_ready": False,
            "strategy_execution_enabled": False,
            "actual_flatten_executed": False,
            "order_cancel_executed": False,
            "close_position_executed": False,
            "withdrawal_or_transfer_executed": False,
            "llm_authorized_execution": False,
        },
        "account_facts_summary": {
            "source": market.get("source"),
            "truth_level": market.get("truth_level"),
            "reconciliation_status": market.get("reconciliation_status_value"),
            "checked_sources": market.get("checked_sources"),
            "mismatch_count": market.get("mismatch_count"),
            "unknown_unmanaged_counts": market.get("unknown_unmanaged_counts"),
            "evidence_refs": market.get("evidence_refs"),
        },
        "capabilities": {
            key: {
                "status": capabilities[key].get("status"),
                "executable_through_operation": capabilities[key].get("executable_through_operation"),
                "dry_run_only": capabilities[key].get("dry_run_only"),
                "reason": capabilities[key].get("current_reason"),
            }
            for key in [
                "switch_playbook",
                "enter_strategy_or_monitor",
                "enter_pause",
                "emergency_stop_runtime",
                "emergency_flatten",
                "live_execution",
            ]
        },
        "operations": {
            "switch_playbook": {
                "operation_id": switch_preflight.operation_id,
                "preflight_id": switch_preflight.preflight_id,
                "preflight_decision": switch_preflight.decision,
                "confirm_status": switch_confirm.status,
                "campaign_refs": switch_confirm.campaign_refs,
                "audit_refs": switch_confirm.audit_refs,
            },
            "enter_strategy_or_monitor": {
                "operation_id": monitor_preflight.operation_id,
                "preflight_id": monitor_preflight.preflight_id,
                "preflight_decision": monitor_preflight.decision,
                "confirm_status": monitor_confirm.status,
                "result_summary": monitor_confirm.result_summary,
                "final_state": monitor_confirm.next_state,
            },
            "enter_pause": {
                "operation_id": pause_preflight.operation_id,
                "preflight_id": pause_preflight.preflight_id,
                "preflight_decision": pause_preflight.decision,
                "confirm_status": pause_confirm.status,
                "runtime_refs": pause_confirm.result_summary.get("runtime_refs", pause_confirm.audit_refs),
                "final_state": pause_confirm.next_state,
            },
            "emergency_stop_runtime": {
                "operation_id": stop_preflight.operation_id,
                "preflight_id": stop_preflight.preflight_id,
                "preflight_decision": stop_preflight.decision,
                "confirm_status": stop_confirm.status,
                "runtime_refs": stop_confirm.result_summary.get("runtime_refs", stop_confirm.audit_refs),
                "audit_refs": stop_confirm.audit_refs,
                "does_not_flatten": True,
                "does_not_cancel_orders": True,
                "runtime_stop_call_count": len(market.get("runtime_stop_calls", [])),
            },
            "write_review_decision": {
                "operation_id": review_preflight.operation_id,
                "preflight_id": review_preflight.preflight_id,
                "preflight_decision": review_preflight.decision,
                "confirm_status": review_confirm.status,
                "review_refs": review_confirm.review_refs,
                "audit_refs": review_confirm.audit_refs,
            },
        },
        "campaign_playbook_after_full_chain": brc_repo.campaign.current_playbook_id,
        "review_decision_count": len(brc_repo.review_decisions),
        "operation_list": {
            "count": len(listed.operations),
            "operation_ids": operation_ids,
            "all_chain_operations_listed": all(
                operation_id in operation_ids
                for operation_id in [
                    switch_preflight.operation_id,
                    monitor_preflight.operation_id,
                    pause_preflight.operation_id,
                    stop_preflight.operation_id,
                    review_preflight.operation_id,
                ]
            ),
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=[
            "http",
            "runtime-bound-test",
            "runtime-bound-evidence",
            "tf001-carrier-decision-review",
            "tf001-carrier-full-chain",
        ],
        default="http",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--cookie", default=None)
    parser.add_argument("--output", default=None, help="optional local JSON evidence output path")
    args = parser.parse_args(argv)

    if args.mode == "runtime-bound-test":
        payload = asyncio.run(run_runtime_bound_test_smoke())
        if args.output:
            _write_json(Path(args.output), payload)
        _print_json(payload)
        return 0
    if args.mode == "runtime-bound-evidence":
        payload = asyncio.run(run_runtime_bound_evidence_smoke())
        if args.output:
            _write_json(Path(args.output), payload)
        _print_json(payload)
        return 0
    if args.mode == "tf001-carrier-decision-review":
        payload = asyncio.run(run_tf001_carrier_decision_review())
        if args.output:
            _write_json(Path(args.output), payload)
        _print_json(payload)
        return 0
    if args.mode == "tf001-carrier-full-chain":
        payload = asyncio.run(run_tf001_carrier_full_chain())
        if args.output:
            _write_json(Path(args.output), payload)
        _print_json(payload)
        return 0

    cookie = args.cookie or _signed_cookie_from_env()
    payload = run_http_smoke(args.base_url, cookie)
    if args.output:
        _write_json(Path(args.output), payload)
    _print_json(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
