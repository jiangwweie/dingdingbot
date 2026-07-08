#!/usr/bin/env python3
"""Dispatch the Runtime Signal Watcher PG ticket identity to the next safe step.

The CLI consumes PG Action-Time Ticket identity only. With
``--execute-preflight`` it may call the official action-time FinalGate preflight
GET endpoint. With ``--execute-operation-layer-submit`` it may call only the
ticket-bound protected submit endpoint after the same-run ticket FinalGate and
handoff checks pass. Legacy resume-pack JSON and loose evidence-file identity
are not accepted as production or diagnostic CLI sources.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

import sqlalchemy as sa


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402
from src.application.readmodels.owner_projection import (
    owner_non_authority_checkpoint,
    owner_state_without_legacy_input_recovery_action,
)
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    is_current_action_time_lane,
    is_current_action_time_ticket,
)


DEFAULT_API_BASE = "http://127.0.0.1:18080"
OPEN_PG_TICKET_STATUSES = {"created", "preflight_pending", "finalgate_ready"}
OPEN_PG_LANE_STATUSES = {"opened", "facts_refreshing", "ticket_pending", "ticket_created"}
READY_STATUS = "ready_for_action_time_final_gate"
FINALGATE_READY_STATUS = "finalgate_ready"
WAITING_STATUS = "waiting_for_market"
NON_EXECUTING_PREPARE_STATUS = "ready_for_non_executing_prepare"
FRESH_AUTHORIZATION_STATUSES = {
    "ready_for_fresh_submit_authorization",
    "waiting_for_fresh_authorization",
}
FINALGATE_ACTION = "run_official_action_time_final_gate_preflight"
CONTINUE_ACTION = "continue_watcher_observation"
TICKET_BOUND_OPERATION_LAYER_HANDOFF_ACTION = (
    "prepare_ticket_bound_operation_layer_handoff"
)
OPERATION_LAYER_SUBMIT_ACTION = "call_official_operation_layer_submit"
OPERATION_LAYER_SUBMIT_MODE_REAL = "real_gateway_action"
OPERATION_LAYER_SUBMIT_MODE_DISABLED_SMOKE = "disabled_smoke"
OPERATION_LAYER_SUBMIT_MODE_TEMP_TINY_LIVE = "temp_tiny_live_protected_submit"
OPERATION_LAYER_SUBMIT_MODES = {
    OPERATION_LAYER_SUBMIT_MODE_REAL,
    OPERATION_LAYER_SUBMIT_MODE_DISABLED_SMOKE,
    OPERATION_LAYER_SUBMIT_MODE_TEMP_TINY_LIVE,
}
POST_SUBMIT_FINALIZE_ACTION = "post_submit_finalize_reconciliation_budget_settlement"
RETIRED_FILE_AUTHORITY_SCOPES = {
    "runtime_fresh_attempt_readiness_projection",
}
SESSION_COOKIE_ENV = "BRC_OPERATOR_SESSION_COOKIE"
SESSION_COOKIE_FALLBACK_ENV = "OWNER_BOUNDED_SESSION_COOKIE"
UNSAFE_TRUE_FLAGS = {
    "places_order",
    "calls_order_lifecycle",
    "exchange_write_called",
    "withdrawal_or_transfer_requested",
    "withdrawal_or_transfer_created",
    "runtime_budget_mutated",
    "mutates_pg",
    "order_created",
}
READY_REQUIRED_FIELDS = (
    "ticket_id",
)


def _pg_ticket_resume_pack(
    *,
    database_url: str,
    api_base: str,
) -> tuple[dict[str, Any], Path]:
    normalized = normalize_sync_postgres_dsn(database_url)
    if not normalized:
        return _blocked_pg_ticket_resume_pack(
            "blocked_by_missing_pg_database_url",
            ["missing_fact:PG_DATABASE_URL"],
        ), Path("pg://runtime-control-state/action-time-ticket")
    engine = sa.create_engine(normalized)
    try:
        with engine.connect() as conn:
            now_ms = int(time.time() * 1000)
            rows = _open_pg_ticket_identity_rows(conn, now_ms=now_ms)
            lane_rows = _open_pg_lane_identity_rows(conn, now_ms=now_ms)
    finally:
        engine.dispose()
    source_path = Path("pg://runtime-control-state/action-time-ticket")
    if not rows:
        if not lane_rows:
            return _waiting_pg_ticket_resume_pack(), source_path
        return _blocked_pg_ticket_resume_pack(
            "blocked_by_missing_pg_ticket_identity",
            ["missing_fact:open_pg_action_time_ticket"],
        ), source_path
    mismatched = [
        row for row in rows if row.get("identity_mismatch_fields")
    ]
    if mismatched:
        ticket_ids = ",".join(
            sorted(str(row["ticket_id"]) for row in mismatched)
        )
        mismatch_fields = ",".join(
            sorted(
                {
                    str(field)
                    for row in mismatched
                    for field in row.get("identity_mismatch_fields", [])
                }
            )
        )
        return _blocked_pg_ticket_resume_pack(
            "blocked_by_inconsistent_pg_ticket_identity",
            [f"inconsistent_pg_action_time_ticket_identity:{ticket_ids}:{mismatch_fields}"],
        ), source_path
    if len(rows) > 1:
        ticket_ids = ",".join(sorted(str(row["ticket_id"]) for row in rows))
        return _blocked_pg_ticket_resume_pack(
            "blocked_by_ambiguous_pg_ticket_identity",
            [f"ambiguous_open_pg_action_time_ticket:{ticket_ids}"],
        ), source_path

    row = rows[0]
    ticket_id = str(row["ticket_id"])
    strategy_group_id = str(row["strategy_group_id"])
    symbol = str(row["symbol"])
    side = str(row["side"])
    runtime_profile_id = str(row["runtime_profile_id"])
    action_time_lane_input_id = str(row["action_time_lane_input_id"])
    promotion_candidate_id = str(row["promotion_candidate_id"])
    signal_event_id = str(row["signal_event_id"])
    allowed_actions = [FINALGATE_ACTION]
    return {
        "scope": "pg_ticket_bound_resume_identity",
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "status": READY_STATUS,
        "ticket_id": ticket_id,
        "action_time_ticket_id": ticket_id,
        "action_time_lane_input_id": action_time_lane_input_id,
        "promotion_candidate_id": promotion_candidate_id,
        "signal_event_id": signal_event_id,
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "runtime_profile_id": runtime_profile_id,
        "selected_runtime_instance_ids": [],
        "action_time_resume": {
            "status": READY_STATUS,
            "next_step": FINALGATE_ACTION,
            "ticket_id": ticket_id,
            "action_time_ticket_id": ticket_id,
            "action_time_lane_input_id": action_time_lane_input_id,
            "promotion_candidate_id": promotion_candidate_id,
            "signal_event_id": signal_event_id,
            "strategy_group_id": strategy_group_id,
            "symbol": symbol,
            "side": side,
            "runtime_profile_id": runtime_profile_id,
            "allowed_auto_actions": allowed_actions,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_requested": False,
        },
        "owner_state": {
            "status": READY_STATUS,
            "blocker_class": "none",
            "non_authority_checkpoint": FINALGATE_ACTION,
        },
        "command_plan": _preflight_command_plan(api_base=api_base, ticket_id=ticket_id),
        "safety_invariants": {
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "mutates_pg": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effect_flags": [],
        },
        "allowed_auto_actions": allowed_actions,
        "blockers": [],
        "warnings": [],
    }, source_path


def _open_pg_ticket_identity_rows(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> list[dict[str, Any]]:
    metadata = sa.MetaData()
    tickets = sa.Table("brc_action_time_tickets", metadata, autoload_with=conn)
    lanes = sa.Table("brc_action_time_lane_inputs", metadata, autoload_with=conn)
    statement = (
        sa.select(
            tickets.c.ticket_id,
            tickets.c.action_time_lane_input_id,
            tickets.c.promotion_candidate_id,
            tickets.c.signal_event_id,
            tickets.c.strategy_group_id,
            tickets.c.symbol,
            tickets.c.side,
            tickets.c.runtime_profile_id,
            tickets.c.status.label("ticket_status"),
            tickets.c.expires_at_ms.label("ticket_expires_at_ms"),
            tickets.c.created_at_ms.label("ticket_created_at_ms"),
            lanes.c.promotion_candidate_id.label("lane_promotion_candidate_id"),
            lanes.c.signal_event_id.label("lane_signal_event_id"),
            lanes.c.strategy_group_id.label("lane_strategy_group_id"),
            lanes.c.symbol.label("lane_symbol"),
            lanes.c.side.label("lane_side"),
            lanes.c.runtime_profile_id.label("lane_runtime_profile_id"),
            lanes.c.lane_scope.label("lane_scope"),
            lanes.c.status.label("lane_status"),
            lanes.c.expires_at_ms.label("lane_expires_at_ms"),
            lanes.c.closed_at_ms.label("lane_closed_at_ms"),
        )
        .select_from(
            tickets.join(
                lanes,
                tickets.c.action_time_lane_input_id
                == lanes.c.action_time_lane_input_id,
            )
        )
        .where(tickets.c.status.in_(sorted(OPEN_PG_TICKET_STATUSES)))
        .where(tickets.c.expires_at_ms.is_not(None))
        .where(tickets.c.expires_at_ms > now_ms)
        .where(lanes.c.lane_scope == "real_submit_candidate")
        .where(lanes.c.status.in_(sorted(OPEN_PG_LANE_STATUSES)))
        .where(lanes.c.closed_at_ms.is_(None))
        .where(lanes.c.expires_at_ms.is_not(None))
        .where(lanes.c.expires_at_ms > now_ms)
        .order_by(tickets.c.created_at_ms.asc(), tickets.c.ticket_id.asc())
    )
    rows: list[dict[str, Any]] = []
    for row in conn.execute(statement).mappings():
        item = dict(row)
        if not _joined_ticket_and_lane_are_current(item, now_ms=now_ms):
            continue
        item["identity_mismatch_fields"] = _pg_ticket_identity_mismatch_fields(item)
        rows.append(item)
    return rows


def _open_pg_lane_identity_rows(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> list[dict[str, Any]]:
    metadata = sa.MetaData()
    lanes = sa.Table("brc_action_time_lane_inputs", metadata, autoload_with=conn)
    statement = (
        sa.select(
            lanes.c.action_time_lane_input_id,
            lanes.c.promotion_candidate_id,
            lanes.c.signal_event_id,
            lanes.c.strategy_group_id,
            lanes.c.symbol,
            lanes.c.side,
            lanes.c.runtime_profile_id,
            lanes.c.lane_scope,
            lanes.c.status.label("lane_status"),
            lanes.c.expires_at_ms.label("lane_expires_at_ms"),
            lanes.c.closed_at_ms.label("lane_closed_at_ms"),
        )
        .where(lanes.c.lane_scope == "real_submit_candidate")
        .where(lanes.c.status.in_(sorted(OPEN_PG_LANE_STATUSES)))
        .where(lanes.c.closed_at_ms.is_(None))
        .where(lanes.c.expires_at_ms.is_not(None))
        .where(lanes.c.expires_at_ms > now_ms)
        .order_by(lanes.c.created_at_ms.asc(), lanes.c.action_time_lane_input_id.asc())
    )
    return [
        item
        for item in (dict(row) for row in conn.execute(statement).mappings())
        if _joined_lane_is_current(item, now_ms=now_ms)
    ]


def _joined_ticket_and_lane_are_current(
    row: dict[str, Any],
    *,
    now_ms: int,
) -> bool:
    ticket = {
        "status": row.get("ticket_status"),
        "expires_at_ms": row.get("ticket_expires_at_ms"),
    }
    return is_current_action_time_ticket(
        ticket,
        now_ms,
    ) and _joined_lane_is_current(row, now_ms=now_ms)


def _joined_lane_is_current(row: dict[str, Any], *, now_ms: int) -> bool:
    lane = {
        "lane_scope": row.get("lane_scope"),
        "status": row.get("lane_status"),
        "expires_at_ms": row.get("lane_expires_at_ms"),
        "closed_at_ms": row.get("lane_closed_at_ms"),
    }
    return is_current_action_time_lane(lane, now_ms)


def _pg_ticket_identity_mismatch_fields(row: dict[str, Any]) -> list[str]:
    pairs = (
        ("promotion_candidate_id", "lane_promotion_candidate_id"),
        ("signal_event_id", "lane_signal_event_id"),
        ("strategy_group_id", "lane_strategy_group_id"),
        ("symbol", "lane_symbol"),
        ("side", "lane_side"),
        ("runtime_profile_id", "lane_runtime_profile_id"),
    )
    return [
        left
        for left, right in pairs
        if str(row.get(left) or "") != str(row.get(right) or "")
    ]


def _waiting_pg_ticket_resume_pack() -> dict[str, Any]:
    return {
        "scope": "pg_ticket_bound_resume_identity",
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "status": WAITING_STATUS,
        "action_time_resume": {
            "status": WAITING_STATUS,
            "allowed_auto_actions": [],
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_requested": False,
        },
        "owner_state": {
            "status": "waiting_for_opportunity",
            "blocker_class": "waiting_for_market",
            "blocked_at": "pg_action_time_ticket_identity",
            "blocked_reason": "no_open_pg_action_time_lane_or_ticket",
            "non_authority_checkpoint": CONTINUE_ACTION,
            "owner_action_required": False,
        },
        "safety_invariants": {
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "mutates_pg": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effect_flags": [],
        },
        "blockers": [],
        "warnings": [],
        "pg_ticket_identity_dispatch_status": "waiting_for_pg_action_time_ticket",
    }


def _blocked_pg_ticket_resume_pack(
    dispatch_status: str,
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "scope": "pg_ticket_bound_resume_identity",
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "status": "blocked",
        "action_time_resume": {
            "status": "blocked",
            "allowed_auto_actions": [],
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_requested": False,
        },
        "owner_state": {
            "status": "temporarily_unavailable",
            "blocker_class": "runtime_data_gap",
            "blocked_at": "pg_action_time_ticket_identity",
            "blocked_reason": blockers[0] if blockers else dispatch_status,
            "non_authority_checkpoint": "materialize_action_time_ticket",
            "authority_mode": "continue_watcher_observation_no_submit",
            "owner_action_required": False,
        },
        "safety_invariants": {
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "mutates_pg": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effect_flags": [],
        },
        "blockers": blockers,
        "warnings": [],
        "pg_ticket_identity_dispatch_status": dispatch_status,
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe_text(values: Any) -> list[str]:
    items: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def _nonempty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _unsafe_flags(resume_pack: dict[str, Any]) -> list[str]:
    action_time_resume = _dict(resume_pack.get("action_time_resume"))
    safety = _dict(resume_pack.get("safety_invariants"))
    flags: list[str] = []
    for source in (action_time_resume, safety):
        for name in sorted(UNSAFE_TRUE_FLAGS):
            if source.get(name) not in {False, None, "", 0}:
                flags.append(name)
    for name in _list(safety.get("forbidden_effect_flags")):
        if str(name).strip():
            flags.append(str(name))
    return sorted(set(flags))


def _missing_ready_fields(
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> list[str]:
    return [
        name
        for name in READY_REQUIRED_FIELDS
        if not _nonempty(action_time_resume.get(name) or resume_pack.get(name))
    ]


def _action_runtime_instance_ids(
    *,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> list[str]:
    ids: list[str] = []
    for value in (
        action_time_resume.get("runtime_instance_id"),
        resume_pack.get("runtime_instance_id"),
        _dict(resume_pack.get("command_plan")).get("runtime_instance_id"),
        _dict(resume_pack.get("operation_layer_command_plan")).get(
            "runtime_instance_id"
        ),
    ):
        text = str(value or "").strip()
        if text and text not in ids:
            ids.append(text)

    selected_ids = [
        str(item or "").strip()
        for item in _list(resume_pack.get("selected_runtime_instance_ids"))
        if str(item or "").strip()
    ]
    if not ids and len(selected_ids) == 1:
        ids.append(selected_ids[0])
    return ids


def _action_strategy_group_ids(
    *,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> list[str]:
    runtime_ids = set(
        _action_runtime_instance_ids(
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
        )
    )
    signal_input_json = _first_text(
        action_time_resume.get("signal_input_json"),
        resume_pack.get("signal_input_json"),
    )
    prepared_authorization_id = _first_text(
        action_time_resume.get("prepared_authorization_id"),
        resume_pack.get("prepared_authorization_id"),
        _dict(resume_pack.get("command_plan")).get("prepared_authorization_id"),
        _dict(resume_pack.get("command_plan")).get("authorization_id"),
    )
    shadow_candidate_id = _first_text(
        action_time_resume.get("shadow_candidate_id"),
        resume_pack.get("shadow_candidate_id"),
    )
    ids: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in ids:
            ids.append(text)

    for source in (action_time_resume, resume_pack):
        add(source.get("strategy_group_id"))
        add(source.get("strategy_family_id"))
    for source in (
        _dict(resume_pack.get("command_plan")),
        _dict(resume_pack.get("operation_layer_command_plan")),
    ):
        add(source.get("strategy_group_id"))
        add(source.get("strategy_family_id"))

    for item in _list(resume_pack.get("runtime_signal_summaries")):
        if not isinstance(item, dict):
            continue
        matches_runtime = (
            bool(runtime_ids)
            and str(item.get("runtime_instance_id") or "").strip() in runtime_ids
        )
        matches_signal = (
            bool(signal_input_json)
            and str(item.get("signal_input_json") or "").strip() == signal_input_json
        )
        matches_authorization = (
            bool(prepared_authorization_id)
            and str(item.get("prepared_authorization_id") or "").strip()
            == prepared_authorization_id
        )
        matches_candidate = (
            bool(shadow_candidate_id)
            and str(item.get("shadow_candidate_id") or "").strip()
            == shadow_candidate_id
        )
        if matches_runtime or matches_signal or matches_authorization or matches_candidate:
            add(item.get("strategy_group_id"))
            add(item.get("strategy_family_id"))
    return ids


def _selected_scope_action_blockers(
    *,
    selected_strategy_group_id: str | None,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
    require_unique_when_unselected: bool = False,
) -> list[str]:
    action_groups = _action_strategy_group_ids(
        resume_pack=resume_pack,
        action_time_resume=action_time_resume,
    )
    return _selected_scope_group_blockers(
        selected_strategy_group_id=selected_strategy_group_id,
        action_groups=action_groups,
        require_unique_when_unselected=require_unique_when_unselected,
    )


def _selected_scope_group_blockers(
    *,
    selected_strategy_group_id: str | None,
    action_groups: list[str],
    require_unique_when_unselected: bool = False,
) -> list[str]:
    selected = str(selected_strategy_group_id or "").strip()
    if not selected:
        if not require_unique_when_unselected:
            return []
        if len(action_groups) == 1:
            return []
        if not action_groups:
            return ["missing_fact:unique_strategy_group_for_action"]
        return [
            "ambiguous_strategy_group_for_action:"
            f"{','.join(sorted(action_groups))}"
        ]
    if len(action_groups) > 1:
        return [
            "ambiguous_strategy_group_for_action:"
            f"{','.join(sorted(action_groups))}"
        ]
    if selected not in action_groups:
        if action_groups:
            return [
                "selected_strategy_group_mismatch:"
                f"expected={selected}:actual={','.join(action_groups)}"
            ]
        return ["missing_fact:selected_strategy_group_id_for_action"]
    return []


def _preflight_command_plan(
    *,
    api_base: str,
    ticket_id: str,
) -> dict[str, Any]:
    encoded_ticket_id = urllib.parse.quote(str(ticket_id), safe="")
    endpoint = (
        "/api/trading-console/"
        f"runtime-action-time-finalgate-preflights/tickets/{encoded_ticket_id}"
    )
    return {
        "kind": "official_action_time_finalgate_preflight",
        "method": "GET",
        "api_base": api_base.rstrip("/"),
        "path": endpoint,
        "curl": (
            "curl -fsS "
            f"{api_base.rstrip('/')}{endpoint}"
        ),
        "ticket_id": ticket_id,
        "requires_operator_session": True,
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
    }


def _session_cookie() -> tuple[str | None, str | None]:
    explicit = (
        os.environ.get(SESSION_COOKIE_ENV)
        or os.environ.get(SESSION_COOKIE_FALLBACK_ENV)
        or ""
    ).strip()
    if explicit:
        if "=" in explicit:
            return explicit, None
        try:
            from src.interfaces.operator_auth import SESSION_COOKIE
        except Exception as exc:
            return None, f"operator_session_cookie_name_unavailable:{type(exc).__name__}"
        return f"{SESSION_COOKIE}={explicit}", None

    try:
        from src.interfaces.operator_auth import SESSION_COOKIE, _load_auth_config, _sign_payload

        config = _load_auth_config()
        now = int(time.time())
        token = _sign_payload(
            {
                "sub": config.username,
                "iat": now,
                "exp": now + min(config.ttl_seconds, 3600),
                "scope": "brc_operator_console",
            },
            config.session_secret,
        )
        return f"{SESSION_COOKIE}={token}", None
    except Exception as exc:
        return None, f"operator_session_unavailable:{type(exc).__name__}"


def _request_json(
    *,
    method: str,
    url: str,
    cookie: str,
    timeout_seconds: int,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json", "Cookie": cookie}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            return {
                "http_status": response.status,
                "body": json.loads(raw) if raw else None,
                "error": False,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body: Any = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        return {"http_status": exc.code, "body": body, "error": True}
    except Exception as exc:
        return {
            "http_status": None,
            "body": None,
            "error": True,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def _preflight_forbidden_effects(body: Any) -> list[str]:
    payload = _dict(body)
    effects: list[str] = []
    checks = {
        "submit_executed": False,
        "order_created": False,
        "exchange_called": False,
        "owner_bounded_execution_called": False,
        "order_lifecycle_called": False,
    }
    for name, expected in checks.items():
        if payload.get(name) is not expected:
            effects.append(f"preflight_effect:{name}")
    return effects


def _preflight_passed(body: Any) -> bool:
    payload = _dict(body)
    status = str(
        payload.get("status") or payload.get("controlled_submit_plan_status") or ""
    ).lower()
    final_gate_status = str(payload.get("final_gate_verdict") or "").lower()
    return (
        status == "ready_for_controlled_submit_adapter"
        and final_gate_status == "pass"
        and not payload.get("blockers")
    )


def _preflight_blockers(body: Any) -> list[str]:
    payload = _dict(body)
    blockers = [str(item) for item in _list(payload.get("blockers")) if str(item).strip()]
    raw_status = payload.get("status") or payload.get("controlled_submit_plan_status")
    normalized_status = str(raw_status or "").lower()
    if raw_status is not None and normalized_status != "ready_for_controlled_submit_adapter":
        blockers.append(f"preflight_status:{raw_status}")
    final_gate_status = payload.get("final_gate_verdict")
    if final_gate_status is not None and str(final_gate_status).lower() != "pass":
        blockers.append(f"final_gate_verdict:{final_gate_status}")
    return sorted(set(blockers))


def _allowed_auto_actions(
    *,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
) -> list[str]:
    actions = [
        str(item)
        for item in _list(action_time_resume.get("allowed_auto_actions"))
        if str(item).strip()
    ]
    if actions:
        return actions
    return [
        str(item)
        for item in _list(resume_pack.get("allowed_auto_actions"))
        if str(item).strip()
    ]


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _action_time_ticket_id(
    *,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
    command_plan: dict[str, Any] | None = None,
) -> str | None:
    command_plan = command_plan or {}
    return _first_text(
        action_time_resume.get("ticket_id"),
        action_time_resume.get("action_time_ticket_id"),
        resume_pack.get("ticket_id"),
        resume_pack.get("action_time_ticket_id"),
        command_plan.get("ticket_id"),
        _dict(resume_pack.get("command_plan")).get("ticket_id"),
    )


def _ticket_bound_operation_layer_handoff_plan(
    *,
    api_base: str,
    ticket_id: str,
    finalgate_pass_id: str,
) -> dict[str, Any]:
    encoded_ticket_id = urllib.parse.quote(str(ticket_id), safe="")
    encoded_finalgate_pass_id = urllib.parse.quote(str(finalgate_pass_id), safe="")
    endpoint = (
        "/api/trading-console/runtime-operation-layer-handoffs/"
        f"tickets/{encoded_ticket_id}/finalgate-passes/{encoded_finalgate_pass_id}"
    )
    return {
        "kind": "ticket_bound_operation_layer_handoff",
        "method": "POST",
        "api_base": api_base.rstrip("/"),
        "path": endpoint,
        "curl": "curl -fsS -X POST " f"{api_base.rstrip('/')}{endpoint}",
        "ticket_id": ticket_id,
        "finalgate_pass_id": finalgate_pass_id,
        "requires_operator_session": True,
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
        "non_authority_checkpoint": "prepare_ticket_bound_protected_submit",
    }


def _operation_layer_handoff_forbidden_effects(body: Any) -> list[str]:
    payload = _dict(body)
    command_plan = _dict(payload.get("command_plan"))
    effects: list[str] = []
    checks = {
        "submit_executed": False,
        "operation_layer_submit_called": False,
        "order_created": False,
        "exchange_called": False,
        "exchange_write_called": False,
        "owner_bounded_execution_called": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
    }
    for name, expected in checks.items():
        if payload.get(name) is not expected:
            effects.append(f"operation_layer_handoff_effect:{name}")
    command_checks = {
        "places_order": False,
        "exchange_write_called": False,
        "order_lifecycle_called": False,
    }
    for name, expected in command_checks.items():
        if name in command_plan and command_plan.get(name) is not expected:
            effects.append(f"operation_layer_handoff_command_effect:{name}")
    for legacy_key in (
        "authorization_id",
        "prepared_authorization_id",
        "shadow_candidate_id",
        "signal_input_json",
    ):
        if command_plan.get(legacy_key):
            effects.append(f"operation_layer_handoff_legacy_input:{legacy_key}")
    return effects


def _operation_layer_handoff_passed(body: Any) -> bool:
    payload = _dict(body)
    command_plan = _dict(payload.get("command_plan"))
    return (
        payload.get("status") == "operation_layer_handoff_ready"
        and payload.get("operation_layer_verdict") == "ready"
        and bool(payload.get("ticket_id"))
        and bool(payload.get("finalgate_pass_id"))
        and bool(payload.get("operation_submit_command_id"))
        and command_plan.get("kind") == "ticket_bound_operation_layer_handoff"
        and bool(command_plan.get("ticket_id"))
        and bool(command_plan.get("finalgate_pass_id"))
        and bool(command_plan.get("operation_submit_command_id"))
        and command_plan.get("requires_ticket_bound_protected_submit") is True
        and command_plan.get("places_order") is False
        and command_plan.get("exchange_write_called") is False
        and command_plan.get("order_lifecycle_called") is False
        and not payload.get("blockers")
    )


def _operation_layer_handoff_blockers(body: Any) -> list[str]:
    payload = _dict(body)
    blockers = [str(item) for item in _list(payload.get("blockers")) if str(item).strip()]
    if payload.get("status") != "operation_layer_handoff_ready":
        blockers.append(f"operation_layer_handoff_status:{payload.get('status')}")
    if payload.get("operation_layer_verdict") not in {"ready", None}:
        blockers.append(f"operation_layer_verdict:{payload.get('operation_layer_verdict')}")
    for key in ("ticket_id", "finalgate_pass_id"):
        if not payload.get(key):
            blockers.append(f"operation_layer_handoff_body_missing:{key}")
    if not payload.get("operation_submit_command_id"):
        blockers.append("operation_submit_command_id_missing")
    command_plan = _dict(payload.get("command_plan"))
    if payload.get("status") == "operation_layer_handoff_ready":
        if command_plan.get("kind") != "ticket_bound_operation_layer_handoff":
            blockers.append("operation_layer_handoff_command_kind_invalid")
        for key in ("ticket_id", "finalgate_pass_id", "operation_submit_command_id"):
            if not command_plan.get(key):
                blockers.append(f"operation_layer_handoff_command_missing:{key}")
        if command_plan.get("requires_ticket_bound_protected_submit") is not True:
            blockers.append("ticket_bound_protected_submit_requirement_missing")
        for key in ("places_order", "exchange_write_called", "order_lifecycle_called"):
            if command_plan.get(key) is not False:
                blockers.append(f"operation_layer_handoff_command_effect:{key}")
    return _dedupe_text(blockers)


def _operation_layer_handoff_identity_blockers(
    *,
    expected_ticket_id: str,
    expected_finalgate_pass_id: str,
    body: Any,
) -> list[str]:
    payload = _dict(body)
    command_plan = _dict(payload.get("command_plan"))
    blockers: list[str] = []
    for key, expected_value in (
        ("ticket_id", expected_ticket_id),
        ("finalgate_pass_id", expected_finalgate_pass_id),
    ):
        for source_name, source in (
            ("body", payload),
            ("command", command_plan),
        ):
            actual = str(source.get(key) or "").strip()
            if not actual:
                blockers.append(f"operation_layer_handoff_{source_name}_missing:{key}")
            elif actual != expected_value:
                blockers.append(
                    f"operation_layer_handoff_{source_name}_mismatch:{key}:"
                    f"expected={expected_value}:actual={actual}"
                )
    body_submit_id = str(payload.get("operation_submit_command_id") or "").strip()
    command_submit_id = str(
        command_plan.get("operation_submit_command_id") or ""
    ).strip()
    if not body_submit_id:
        blockers.append("operation_submit_command_id_missing")
    if not command_submit_id:
        blockers.append("operation_layer_handoff_command_missing:operation_submit_command_id")
    if body_submit_id and command_submit_id and body_submit_id != command_submit_id:
        blockers.append(
            "operation_layer_handoff_command_mismatch:operation_submit_command_id:"
            f"expected={body_submit_id}:actual={command_submit_id}"
        )
    return _dedupe_text(blockers)


def _operation_layer_blocker_class(
    blockers: list[str],
    missing_ids: list[str],
) -> str:
    combined = " ".join([*blockers, *missing_ids]).lower()
    if any(token in combined for token in ("withdraw", "transfer", "bypass")):
        return "hard_safety_stop"
    if "authorization_id_mismatch" in combined:
        return "hard_safety_stop"
    if "ticket_bound_submit_result_mismatch" in combined:
        return "hard_safety_stop"
    if "operation_layer_handoff_body_mismatch" in combined:
        return "hard_safety_stop"
    if "operation_layer_handoff_command_mismatch" in combined:
        return "hard_safety_stop"
    if "submit_result_order_id_not_in_ticket_request" in combined:
        return "hard_safety_stop"
    if "runtime_instance_id_mismatch" in combined:
        return "hard_safety_stop"
    if "reservation_id_mismatch" in combined:
        return "hard_safety_stop"
    if any(token in combined for token in ("duplicate", "idempotency")):
        return "hard_safety_stop"
    if any(token in combined for token in ("active_position", "open_order_conflict")):
        return "active_position_resolution"
    if any(token in combined for token in ("symbol_scope", "side_scope")):
        return "hard_safety_stop"
    if any(token in combined for token in ("notional_scope", "leverage_scope")):
        return "hard_safety_stop"
    if "deployment" in combined or "gateway_readiness" in combined:
        return "deployment_issue"
    if "owner_runtime_" in combined and "env_confirmation" in combined:
        return "deployment_issue"
    return "missing_fact"


def _owner_state_for_operation_layer_handoff(
    *,
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    body: dict[str, Any],
) -> dict[str, Any]:
    if status == "operation_layer_ready":
        return {
            "status": "operation_layer_ready",
            "blocker_class": "none",
            "blocked_at": "none",
            "blocked_reason": "none",
            "next_recover_condition": "ticket_bound_protected_submit_adapter_ready",
            "non_authority_checkpoint": "prepare_ticket_bound_protected_submit",
            "authority_mode": "none",
            "operation_layer_handoff_status": body.get("status"),
        }
    return {
        "status": "blocked",
        "blocker_class": blocker_class,
        "blocked_at": "OperationLayerHandoff",
        "blocked_reason": blockers[0] if blockers else dispatch_status,
        "next_recover_condition": "ticket_bound_operation_layer_handoff_ready",
        "non_authority_checkpoint": "retry_ticket_bound_operation_layer_handoff",
        "authority_mode": "continue_watcher_observation_no_submit",
        "operation_layer_handoff_status": body.get("status"),
    }


def build_dispatch_artifact(
    *,
    resume_pack: dict[str, Any],
    source_path: Path,
    api_base: str = DEFAULT_API_BASE,
    label: str = "tokyo-runtime-signal-watcher",
    execute_preflight: bool = False,
    preflight_timeout_seconds: int = 120,
    execute_operation_layer_submit: bool = False,
    operation_layer_submit_mode: str = OPERATION_LAYER_SUBMIT_MODE_REAL,
    execute_post_submit_finalize: bool = False,
    selected_strategy_group_id: str | None = None,
) -> dict[str, Any]:
    action_time_resume = _dict(resume_pack.get("action_time_resume"))
    owner_state = _dict(resume_pack.get("owner_state"))
    top_level_status = str(resume_pack.get("status") or "")
    action_time_status = str(action_time_resume.get("status") or "")
    status = (
        top_level_status
        if top_level_status == FINALGATE_READY_STATUS
        else action_time_status or top_level_status
    )
    allowed_auto_actions = _allowed_auto_actions(
        resume_pack=resume_pack,
        action_time_resume=action_time_resume,
    )
    unsafe_flags = _unsafe_flags(resume_pack)
    base_blockers = [
        str(item)
        for item in _list(resume_pack.get("blockers"))
        if str(item).strip()
    ]
    retired_scope = str(resume_pack.get("scope") or "").strip()

    if retired_scope in RETIRED_FILE_AUTHORITY_SCOPES:
        return _dispatch_artifact(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state={
                "status": "needs_intervention",
                "blocker_class": "hard_safety_stop",
                "blocked_at": "file_authority_retired",
                "blocked_reason": f"retired_file_authority_scope:{retired_scope}",
                "non_authority_checkpoint": "materialize_pg_action_time_ticket",
                "authority_mode": "continue_watcher_observation_no_submit",
            },
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_action=None,
            dispatch_status="blocked_by_retired_file_authority_projection",
            blockers=base_blockers + [
                f"retired_file_authority_scope:{retired_scope}",
            ],
            command_plan=None,
            selected_strategy_group_id=selected_strategy_group_id,
        )

    if unsafe_flags:
        return _dispatch_artifact(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state=owner_state,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_action=None,
            dispatch_status="blocked_by_unsafe_resume_flags",
            blockers=base_blockers + [f"unsafe_flag:{name}" for name in unsafe_flags],
            command_plan=None,
        )

    if (
        status == "blocked"
        and str(resume_pack.get("scope") or "") == "pg_ticket_bound_resume_identity"
    ):
        return _dispatch_artifact(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state=owner_state,
            status="blocked",
            blocker_class=str(owner_state.get("blocker_class") or "runtime_data_gap"),
            dispatch_action=None,
            dispatch_status=str(
                resume_pack.get("pg_ticket_identity_dispatch_status")
                or "blocked_by_missing_pg_ticket_identity"
            ),
            blockers=base_blockers,
            command_plan=None,
            selected_strategy_group_id=selected_strategy_group_id,
        )

    if status == WAITING_STATUS:
        return _dispatch_artifact(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state=owner_state,
            status=WAITING_STATUS,
            blocker_class="waiting_for_market",
            dispatch_action=CONTINUE_ACTION,
            dispatch_status="no_action_continue_observation",
            blockers=[],
            command_plan=None,
            selected_strategy_group_id=selected_strategy_group_id,
        )

    if status == NON_EXECUTING_PREPARE_STATUS:
        return _dispatch_artifact(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state={
                "status": "needs_intervention",
                "blocker_class": "hard_safety_stop",
                "blocked_at": "file_authority_retired",
                "blocked_reason": "non_executing_prepare_signal_file_path_retired",
                "next_recover_condition": (
                    "pg_promotion_candidate_and_action_time_ticket_materialized"
                ),
                "non_authority_checkpoint": "materialize_pg_action_time_ticket",
                "authority_mode": "continue_watcher_observation_no_submit",
            },
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_action=None,
            dispatch_status="blocked_by_retired_non_executing_prepare_file_authority",
            blockers=base_blockers
            + [
                "retired_file_authority_scope:non_executing_prepare_signal_input_json",
                "pg_promotion_candidate_required",
                "pg_action_time_ticket_required",
                "ticket_bound_finalgate_required",
            ],
            command_plan=None,
            selected_strategy_group_id=selected_strategy_group_id,
        )

    if status in FRESH_AUTHORIZATION_STATUSES:
        return _dispatch_artifact(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state={
                "status": "needs_intervention",
                "blocker_class": "hard_safety_stop",
                "blocked_at": "file_authority_retired",
                "blocked_reason": "fresh_authorization_handoff_file_path_retired",
                "non_authority_checkpoint": "materialize_pg_action_time_ticket",
                "authority_mode": "continue_watcher_observation_no_submit",
            },
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_action=None,
            dispatch_status="blocked_by_retired_fresh_authorization_file_authority",
            blockers=base_blockers
            + [
                "retired_file_authority_scope:fresh_authorization_handoff_json",
                "pg_action_time_ticket_required",
                "ticket_bound_operation_layer_handoff_required",
            ],
            command_plan=None,
            selected_strategy_group_id=selected_strategy_group_id,
        )

    selected_scope_blockers = _selected_scope_action_blockers(
        selected_strategy_group_id=selected_strategy_group_id,
        resume_pack=resume_pack,
        action_time_resume=action_time_resume,
        require_unique_when_unselected=execute_operation_layer_submit,
    )
    if selected_scope_blockers:
        return _dispatch_artifact(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state={
                "status": "needs_intervention",
                "blocker_class": "hard_safety_stop",
                "blocked_at": "selected_strategygroup_scope",
                "blocked_reason": ",".join(selected_scope_blockers),
                "non_authority_checkpoint": "review_selected_strategygroup_scope",
                "authority_mode": "continue_watcher_observation_no_submit",
            },
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_action=None,
            dispatch_status="blocked_by_selected_strategygroup_scope",
            blockers=base_blockers + selected_scope_blockers,
            command_plan=None,
            selected_strategy_group_id=selected_strategy_group_id,
        )

    if status == FINALGATE_READY_STATUS:
        command_plan = _dict(resume_pack.get("command_plan"))
        preflight_result = _dict(resume_pack.get("finalgate_preflight_result"))
        artifact = _dispatch_artifact(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state=_owner_state_for_preflight(
                status=FINALGATE_READY_STATUS,
                blocker_class="none",
                dispatch_status="official_finalgate_preflight_passed",
                blockers=[],
            ),
            status=FINALGATE_READY_STATUS,
            blocker_class="none",
            dispatch_action=TICKET_BOUND_OPERATION_LAYER_HANDOFF_ACTION,
            dispatch_status="official_finalgate_preflight_passed",
            blockers=[],
            command_plan=command_plan or None,
            finalgate_preflight_result=preflight_result or None,
            operation_layer_command_plan=None,
            selected_strategy_group_id=selected_strategy_group_id,
        )
        if (
            command_plan
            and _ticket_bound_finalgate_command_plan(command_plan)
            and preflight_result
            and _preflight_passed(preflight_result.get("body"))
        ):
            if not execute_preflight:
                return _dispatch_artifact_from_preflight(
                    artifact=artifact,
                    status=FINALGATE_READY_STATUS,
                    blocker_class="none",
                    dispatch_status="official_finalgate_preflight_passed",
                    blockers=[],
                    preflight_result=preflight_result,
                    operation_layer_command_plan=None,
                )
            return _execute_ticket_bound_operation_layer_handoff(
                artifact=artifact,
                preflight_result=preflight_result,
                timeout_seconds=preflight_timeout_seconds,
                execute_operation_layer_submit=execute_operation_layer_submit,
                operation_layer_submit_mode=operation_layer_submit_mode,
                execute_post_submit_finalize=execute_post_submit_finalize,
            )

        blockers = [
            "legacy_authorization_finalgate_ready_retired",
            "ticket_bound_action_time_ticket_required",
        ]
        if not _action_time_ticket_id(
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            command_plan=command_plan,
        ):
            blockers.append("missing_fact:ticket_id")
        if command_plan and not _ticket_bound_finalgate_command_plan(command_plan):
            blockers.append("ticket_bound_finalgate_command_plan_required")
        if _dict(resume_pack.get("operation_layer_command_plan")):
            blockers.append("legacy_operation_layer_command_plan_ignored")
        return _dispatch_artifact_from_preflight(
            artifact=artifact,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_legacy_finalgate_authorization_without_ticket",
            blockers=base_blockers + blockers,
            preflight_result=preflight_result or None,
            operation_layer_command_plan=None,
        )

    if status == READY_STATUS:
        if FINALGATE_ACTION not in allowed_auto_actions:
            return _dispatch_artifact(
                label=label,
                source_path=source_path,
                resume_pack=resume_pack,
                action_time_resume=action_time_resume,
                owner_state=owner_state,
                status="blocked",
                blocker_class="hard_safety_stop",
                dispatch_action=None,
                dispatch_status="blocked_by_resume_allowed_actions",
                blockers=base_blockers + [
                    "allowed_auto_actions_missing_finalgate_preflight"
                ],
                command_plan=None,
                selected_strategy_group_id=selected_strategy_group_id,
            )
        missing = _missing_ready_fields(resume_pack, action_time_resume)
        if missing:
            return _dispatch_artifact(
                label=label,
                source_path=source_path,
                resume_pack=resume_pack,
                action_time_resume=action_time_resume,
                owner_state=owner_state,
                status="blocked",
                blocker_class="missing_fact",
                dispatch_action=None,
                dispatch_status="blocked_by_missing_preflight_evidence",
                blockers=base_blockers + [f"missing_fact:{name}" for name in missing],
                command_plan=None,
                selected_strategy_group_id=selected_strategy_group_id,
            )

        ticket_id = _action_time_ticket_id(
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
        )
        artifact = _dispatch_artifact(
            label=label,
            source_path=source_path,
            resume_pack=resume_pack,
            action_time_resume=action_time_resume,
            owner_state=owner_state,
            status=READY_STATUS,
            blocker_class="none",
            dispatch_action=FINALGATE_ACTION,
            dispatch_status="official_finalgate_preflight_dispatch_ready",
            blockers=[],
            command_plan=_preflight_command_plan(
                api_base=api_base,
                ticket_id=str(ticket_id),
            ),
            selected_strategy_group_id=selected_strategy_group_id,
        )
        if not execute_preflight:
            return artifact
        return _execute_finalgate_preflight(
            artifact=artifact,
            timeout_seconds=preflight_timeout_seconds,
            execute_operation_layer_submit=execute_operation_layer_submit,
            operation_layer_submit_mode=operation_layer_submit_mode,
            execute_post_submit_finalize=execute_post_submit_finalize,
        )

    return _dispatch_artifact(
        label=label,
        source_path=source_path,
        resume_pack=resume_pack,
        action_time_resume=action_time_resume,
        owner_state=owner_state,
        status="blocked",
        blocker_class="hard_safety_stop",
        dispatch_action=None,
        dispatch_status="blocked_by_unknown_resume_status",
        blockers=base_blockers + [f"unknown_resume_status:{status or 'missing'}"],
        command_plan=None,
        selected_strategy_group_id=selected_strategy_group_id,
    )


def _dispatch_artifact(
    *,
    label: str,
    source_path: Path,
    resume_pack: dict[str, Any],
    action_time_resume: dict[str, Any],
    owner_state: dict[str, Any],
    status: str,
    blocker_class: str,
    dispatch_action: str | None,
    dispatch_status: str,
    blockers: list[str],
    command_plan: dict[str, Any] | None,
    finalgate_preflight_result: dict[str, Any] | None = None,
    operation_layer_command_plan: dict[str, Any] | None = None,
    selected_strategy_group_id: str | None = None,
) -> dict[str, Any]:
    owner_state_projection = _owner_state_projection(owner_state)
    return {
        "scope": "runtime_signal_watcher_resume_dispatcher",
        "label": label,
        "generated_at_ms": int(time.time() * 1000),
        "source_resume_pack": str(source_path),
        "status": status,
        "blocker_class": blocker_class,
        "dispatch_status": dispatch_status,
        "dispatch_action": dispatch_action,
        "selected_strategy_group_id": (
            str(selected_strategy_group_id).strip()
            if str(selected_strategy_group_id or "").strip()
            else None
        ),
        "owner_state": owner_state_projection,
        "selected_runtime_instance_ids": list(
            resume_pack.get("selected_runtime_instance_ids") or []
        ),
        "action_time_resume": action_time_resume,
        "command_plan": command_plan,
        "finalgate_preflight_result": finalgate_preflight_result,
        "operation_layer_command_plan": operation_layer_command_plan,
        "blockers": blockers,
        "warnings": list(resume_pack.get("warnings") or []),
        "safety_invariants": {
            "dispatcher_only": finalgate_preflight_result is None,
            "official_finalgate_preflight_called": finalgate_preflight_result is not None,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "mutates_pg": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "official_operation_layer_submit_called": False,
            "official_post_submit_finalize_called": False,
        },
    }


def _owner_state_projection(owner_state: dict[str, Any]) -> dict[str, Any]:
    checkpoint = owner_non_authority_checkpoint(
        owner_state,
        default="review_current_state",
    )
    projection = {
        **owner_state_without_legacy_input_recovery_action(owner_state),
        "non_authority_checkpoint": checkpoint,
        "checkpoint_source": "owner_state",
    }
    return projection


def _execute_finalgate_preflight(
    *,
    artifact: dict[str, Any],
    timeout_seconds: int,
    execute_operation_layer_submit: bool = False,
    operation_layer_submit_mode: str = OPERATION_LAYER_SUBMIT_MODE_REAL,
    execute_post_submit_finalize: bool = False,
) -> dict[str, Any]:
    command_plan = _dict(artifact.get("command_plan"))
    if command_plan.get("method") != "GET" or not command_plan.get("curl"):
        return _dispatch_artifact_from_preflight(
            artifact=artifact,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_invalid_preflight_command_plan",
            blockers=["invalid_preflight_command_plan"],
            preflight_result=None,
            operation_layer_command_plan=None,
        )

    cookie, cookie_error = _session_cookie()
    if not cookie:
        return _dispatch_artifact_from_preflight(
            artifact=artifact,
            status="blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_unavailable",
            blockers=[cookie_error or "operator_session_unavailable"],
            preflight_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": cookie_error or "operator_session_unavailable",
            },
            operation_layer_command_plan=None,
        )

    url = str(command_plan["api_base"]).rstrip("/") + str(command_plan["path"])
    response = _request_json(
        method="GET",
        url=url,
        cookie=cookie,
        timeout_seconds=timeout_seconds,
    )
    preflight_result = {
        "called": True,
        "method": "GET",
        "path": command_plan["path"],
        "http_status": response.get("http_status"),
        "body": response.get("body"),
        "error": bool(response.get("error")),
        "error_type": response.get("error_type"),
        "error_message": response.get("error_message"),
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
    }

    http_status = response.get("http_status")
    if http_status in {401, 403}:
        return _dispatch_artifact_from_preflight(
            artifact=artifact,
            status="blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_http_error",
            blockers=[f"operator_session_http_status:{http_status}"],
            preflight_result=preflight_result,
            operation_layer_command_plan=None,
        )
    if response.get("error"):
        blocker_class = "missing_fact" if http_status == 404 else "deployment_issue"
        return _dispatch_artifact_from_preflight(
            artifact=artifact,
            status="blocked",
            blocker_class=blocker_class,
            dispatch_status="blocked_by_finalgate_preflight_http_error",
            blockers=[f"finalgate_preflight_http_status:{http_status or 'unavailable'}"],
            preflight_result=preflight_result,
            operation_layer_command_plan=None,
        )

    forbidden_effects = _preflight_forbidden_effects(response.get("body"))
    if forbidden_effects:
        return _dispatch_artifact_from_preflight(
            artifact=artifact,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_finalgate_preflight_forbidden_effect",
            blockers=forbidden_effects,
            preflight_result=preflight_result,
            operation_layer_command_plan=None,
        )

    if not _preflight_passed(response.get("body")):
        blockers = _preflight_blockers(response.get("body"))
        return _dispatch_artifact_from_preflight(
            artifact=artifact,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_action_time_finalgate",
            blockers=blockers or ["runtime_final_gate_execution_check_not_passed"],
            preflight_result=preflight_result,
            operation_layer_command_plan=None,
        )

    if _ticket_bound_finalgate_command_plan(command_plan):
        return _execute_ticket_bound_operation_layer_handoff(
            artifact=artifact,
            preflight_result=preflight_result,
            timeout_seconds=timeout_seconds,
            execute_operation_layer_submit=execute_operation_layer_submit,
            operation_layer_submit_mode=operation_layer_submit_mode,
            execute_post_submit_finalize=execute_post_submit_finalize,
        )

    return _dispatch_artifact_from_preflight(
        artifact=artifact,
        status="blocked",
        blocker_class="hard_safety_stop",
        dispatch_status="blocked_by_legacy_finalgate_authorization_without_ticket",
        blockers=[
            "legacy_authorization_finalgate_ready_retired",
            "ticket_bound_action_time_ticket_required",
        ],
        preflight_result=preflight_result,
        operation_layer_command_plan=None,
    )


def _ticket_bound_finalgate_command_plan(command_plan: dict[str, Any]) -> bool:
    path = str(command_plan.get("path") or command_plan.get("official_endpoint_path") or "")
    return "/runtime-action-time-finalgate-preflights/tickets/" in path


def _execute_ticket_bound_operation_layer_handoff(
    *,
    artifact: dict[str, Any],
    preflight_result: dict[str, Any],
    timeout_seconds: int,
    execute_operation_layer_submit: bool,
    operation_layer_submit_mode: str,
    execute_post_submit_finalize: bool,
) -> dict[str, Any]:
    preflight_body = _dict(preflight_result.get("body"))
    command_plan = _dict(artifact.get("command_plan"))
    ticket_id = _first_text(
        preflight_body.get("ticket_id"),
        command_plan.get("ticket_id"),
    )
    finalgate_pass_id = _first_text(preflight_body.get("finalgate_pass_id"))
    if not ticket_id or not finalgate_pass_id:
        blockers = []
        if not ticket_id:
            blockers.append("ticket_id_missing_after_finalgate")
        if not finalgate_pass_id:
            blockers.append("finalgate_pass_id_missing_after_finalgate")
        return _dispatch_artifact_from_operation_layer_handoff(
            artifact=artifact,
            status="blocked",
            blocker_class="missing_fact",
            dispatch_status="blocked_by_missing_ticket_bound_operation_layer_handoff",
            blockers=blockers,
            preflight_result=preflight_result,
            handoff_plan=None,
            handoff_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": "missing_ticket_or_finalgate_pass",
            },
        )

    handoff_plan = _ticket_bound_operation_layer_handoff_plan(
        api_base=str(command_plan.get("api_base") or DEFAULT_API_BASE),
        ticket_id=ticket_id,
        finalgate_pass_id=finalgate_pass_id,
    )
    cookie, cookie_error = _session_cookie()
    if not cookie:
        return _dispatch_artifact_from_operation_layer_handoff(
            artifact=artifact,
            status="blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_unavailable",
            blockers=[cookie_error or "operator_session_unavailable"],
            preflight_result=preflight_result,
            handoff_plan=handoff_plan,
            handoff_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": cookie_error or "operator_session_unavailable",
            },
        )
    response = _request_json(
        method="POST",
        url=str(handoff_plan["api_base"]).rstrip("/") + str(handoff_plan["path"]),
        cookie=cookie,
        timeout_seconds=timeout_seconds,
    )
    handoff_result = {
        "called": True,
        "method": "POST",
        "path": handoff_plan["path"],
        "http_status": response.get("http_status"),
        "body": response.get("body"),
        "error": bool(response.get("error")),
        "error_type": response.get("error_type"),
        "error_message": response.get("error_message"),
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
    }
    http_status = response.get("http_status")
    if http_status in {401, 403}:
        return _dispatch_artifact_from_operation_layer_handoff(
            artifact=artifact,
            status="blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_http_error",
            blockers=[f"operator_session_http_status:{http_status}"],
            preflight_result=preflight_result,
            handoff_plan=handoff_plan,
            handoff_result=handoff_result,
        )
    if response.get("error"):
        blocker_class = "missing_fact" if http_status == 404 else "deployment_issue"
        return _dispatch_artifact_from_operation_layer_handoff(
            artifact=artifact,
            status="blocked",
            blocker_class=blocker_class,
            dispatch_status="blocked_by_ticket_bound_operation_layer_handoff_http_error",
            blockers=[f"operation_layer_handoff_http_status:{http_status or 'unavailable'}"],
            preflight_result=preflight_result,
            handoff_plan=handoff_plan,
            handoff_result=handoff_result,
        )
    forbidden_effects = _operation_layer_handoff_forbidden_effects(response.get("body"))
    if forbidden_effects:
        return _dispatch_artifact_from_operation_layer_handoff(
            artifact=artifact,
            status="blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_operation_layer_handoff_forbidden_effect",
            blockers=forbidden_effects,
            preflight_result=preflight_result,
            handoff_plan=handoff_plan,
            handoff_result=handoff_result,
        )
    if not _operation_layer_handoff_passed(response.get("body")):
        blockers = _operation_layer_handoff_blockers(response.get("body"))
        return _dispatch_artifact_from_operation_layer_handoff(
            artifact=artifact,
            status="blocked",
            blocker_class=_operation_layer_blocker_class(blockers, []),
            dispatch_status="blocked_by_ticket_bound_operation_layer_handoff",
            blockers=blockers or ["operation_layer_handoff_not_ready"],
            preflight_result=preflight_result,
            handoff_plan=handoff_plan,
            handoff_result=handoff_result,
        )
    identity_blockers = _operation_layer_handoff_identity_blockers(
        expected_ticket_id=ticket_id,
        expected_finalgate_pass_id=finalgate_pass_id,
        body=response.get("body"),
    )
    if identity_blockers:
        return _dispatch_artifact_from_operation_layer_handoff(
            artifact=artifact,
            status="blocked",
            blocker_class=_operation_layer_blocker_class(identity_blockers, []),
            dispatch_status="blocked_by_ticket_bound_operation_layer_handoff_identity",
            blockers=identity_blockers,
            preflight_result=preflight_result,
            handoff_plan=handoff_plan,
            handoff_result=handoff_result,
        )
    result = _dispatch_artifact_from_operation_layer_handoff(
        artifact=artifact,
        status="operation_layer_ready",
        blocker_class="none",
        dispatch_status="ticket_bound_operation_layer_handoff_ready",
        blockers=[],
        preflight_result=preflight_result,
        handoff_plan=handoff_plan,
        handoff_result=handoff_result,
    )
    if execute_operation_layer_submit:
        return _execute_ticket_bound_protected_submit(
            artifact=result,
            timeout_seconds=timeout_seconds,
            operation_layer_submit_mode=operation_layer_submit_mode,
            execute_post_submit_finalize=execute_post_submit_finalize,
        )
    return result


def _dispatch_artifact_from_preflight(
    *,
    artifact: dict[str, Any],
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    preflight_result: dict[str, Any] | None,
    operation_layer_command_plan: dict[str, Any] | None,
) -> dict[str, Any]:
    owner_state = _owner_state_for_preflight(
        status=status,
        blocker_class=blocker_class,
        dispatch_status=dispatch_status,
        blockers=blockers,
    )
    return {
        **artifact,
        "status": status,
        "blocker_class": blocker_class,
        "dispatch_status": dispatch_status,
        "dispatch_action": (
            TICKET_BOUND_OPERATION_LAYER_HANDOFF_ACTION
            if status == "finalgate_ready"
            else None
        ),
        "owner_state": _owner_state_projection(owner_state),
        "finalgate_preflight_result": preflight_result,
        "operation_layer_command_plan": operation_layer_command_plan,
        "blockers": blockers,
        "safety_invariants": {
            **_dict(artifact.get("safety_invariants")),
            "dispatcher_only": False,
            "official_finalgate_preflight_called": preflight_result is not None
            and bool(preflight_result.get("called")),
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "mutates_pg": bool(
                _dict(artifact.get("safety_invariants")).get("mutates_pg")
            ),
            "pg_prepare_evidence_mutated": bool(
                _dict(artifact.get("safety_invariants")).get(
                    "pg_prepare_evidence_mutated"
                )
            ),
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "official_operation_layer_submit_called": False,
            "official_post_submit_finalize_called": False,
        },
    }


def _dispatch_artifact_from_operation_layer_handoff(
    *,
    artifact: dict[str, Any],
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    preflight_result: dict[str, Any],
    handoff_plan: dict[str, Any] | None,
    handoff_result: dict[str, Any],
) -> dict[str, Any]:
    body = _dict(handoff_result.get("body"))
    command_plan = _dict(body.get("command_plan"))
    owner_state = _owner_state_for_operation_layer_handoff(
        status=status,
        blocker_class=blocker_class,
        dispatch_status=dispatch_status,
        blockers=blockers,
        body=body,
    )
    return {
        **artifact,
        "status": status,
        "blocker_class": blocker_class,
        "dispatch_status": dispatch_status,
        "dispatch_action": (
            "prepare_ticket_bound_protected_submit"
            if status == "operation_layer_ready"
            else None
        ),
        "owner_state": _owner_state_projection(owner_state),
        "ticket_id": body.get("ticket_id"),
        "finalgate_pass_id": body.get("finalgate_pass_id"),
        "operation_layer_handoff_id": body.get("operation_layer_handoff_id"),
        "operation_submit_command_id": body.get("operation_submit_command_id"),
        "strategy_group_id": body.get("strategy_group_id"),
        "symbol": body.get("symbol"),
        "side": body.get("side"),
        "finalgate_preflight_result": preflight_result,
        "operation_layer_handoff_plan": handoff_plan,
        "operation_layer_handoff_result": handoff_result,
        "operation_layer_command_plan": (
            command_plan if status == "operation_layer_ready" and command_plan else None
        ),
        "operation_layer_readiness": (
            {
                "status": "ready",
                "blocker_class": "none",
                "ticket_id": body.get("ticket_id"),
                "finalgate_pass_id": body.get("finalgate_pass_id"),
                "operation_layer_handoff_id": body.get("operation_layer_handoff_id"),
                "operation_submit_command_id": body.get("operation_submit_command_id"),
                "strategy_group_id": body.get("strategy_group_id"),
                "symbol": body.get("symbol"),
                "side": body.get("side"),
                "ready_for_ticket_bound_protected_submit": True,
                "places_order": False,
                "exchange_write_called": False,
                "order_lifecycle_called": False,
                "owner_state": owner_state,
            }
            if status == "operation_layer_ready"
            else None
        ),
        "blockers": blockers,
        "safety_invariants": {
            **_dict(artifact.get("safety_invariants")),
            "dispatcher_only": False,
            "official_finalgate_preflight_called": bool(preflight_result.get("called")),
            "ticket_bound_operation_layer_handoff_called": bool(
                handoff_result.get("called")
            ),
            "official_operation_layer_submit_called": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "exchange_write_called": False,
            "mutates_pg": status == "operation_layer_ready"
            or bool(_dict(artifact.get("safety_invariants")).get("mutates_pg")),
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _ticket_bound_protected_submit_url(
    *,
    artifact: dict[str, Any],
    submit_mode: str,
) -> tuple[str, str, list[str]]:
    ticket_id = _first_text(artifact.get("ticket_id"))
    operation_submit_command_id = _first_text(
        artifact.get("operation_submit_command_id")
    )
    blockers: list[str] = []
    if not ticket_id:
        blockers.append("ticket_id_missing_for_ticket_bound_submit")
    if not operation_submit_command_id:
        blockers.append("operation_submit_command_id_missing_for_ticket_bound_submit")
    api_base = str(
        _dict(artifact.get("operation_layer_handoff_plan")).get("api_base")
        or _dict(artifact.get("operation_layer_command_plan")).get("api_base")
        or DEFAULT_API_BASE
    ).rstrip("/")
    path = (
        "/api/trading-console/runtime-protected-submits/tickets/"
        f"{urllib.parse.quote(ticket_id or '', safe='')}"
        "/operation-submit-commands/"
        f"{urllib.parse.quote(operation_submit_command_id or '', safe='')}"
    )
    query = urllib.parse.urlencode({"submit_mode": submit_mode})
    return api_base + path + "?" + query, path, blockers


def _execute_ticket_bound_protected_submit(
    *,
    artifact: dict[str, Any],
    timeout_seconds: int,
    operation_layer_submit_mode: str,
    execute_post_submit_finalize: bool,
) -> dict[str, Any]:
    if operation_layer_submit_mode not in OPERATION_LAYER_SUBMIT_MODES:
        return _dispatch_artifact_from_operation_layer_submit(
            artifact=artifact,
            status="operation_layer_submit_blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_invalid_operation_layer_submit_mode",
            blockers=[
                f"invalid_operation_layer_submit_mode:{operation_layer_submit_mode}"
            ],
            submit_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": "invalid_operation_layer_submit_mode",
            },
        )
    url, path, url_blockers = _ticket_bound_protected_submit_url(
        artifact=artifact,
        submit_mode=operation_layer_submit_mode,
    )
    if url_blockers:
        return _dispatch_artifact_from_operation_layer_submit(
            artifact=artifact,
            status="operation_layer_submit_blocked",
            blocker_class="missing_fact",
            dispatch_status="blocked_before_ticket_bound_protected_submit",
            blockers=url_blockers,
            submit_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": "ticket_bound_submit_identity_missing",
            },
        )
    cookie, cookie_error = _session_cookie()
    if not cookie:
        return _dispatch_artifact_from_operation_layer_submit(
            artifact=artifact,
            status="operation_layer_submit_blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_unavailable",
            blockers=[cookie_error or "operator_session_unavailable"],
            submit_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": cookie_error or "operator_session_unavailable",
            },
        )
    response = _request_json(
        method="POST",
        url=url,
        cookie=cookie,
        timeout_seconds=timeout_seconds,
    )
    body = _ticket_bound_submit_body_for_dispatch(_dict(response.get("body")))
    submit_result = {
        "called": True,
        "method": "POST",
        "path": path,
        "http_status": response.get("http_status"),
        "body": body,
        "error": bool(response.get("error")),
        "error_type": response.get("error_type"),
        "error_message": response.get("error_message"),
        "owner_confirmed_for_first_real_submit_action": (
            operation_layer_submit_mode
            in {
                OPERATION_LAYER_SUBMIT_MODE_REAL,
                OPERATION_LAYER_SUBMIT_MODE_TEMP_TINY_LIVE,
            }
        ),
        "standing_authorized_first_real_submit": (
            operation_layer_submit_mode
            in {
                OPERATION_LAYER_SUBMIT_MODE_REAL,
                OPERATION_LAYER_SUBMIT_MODE_TEMP_TINY_LIVE,
            }
        ),
        "standing_authorization_scope": "ticket_bound_runtime_safety_state",
        "owner_chat_confirmation_required_for_real_submit": False,
        "legacy_owner_confirmation_env_required": False,
        "standing_authorization_consumed_for_real_submit": (
            operation_layer_submit_mode
            in {
                OPERATION_LAYER_SUBMIT_MODE_REAL,
                OPERATION_LAYER_SUBMIT_MODE_TEMP_TINY_LIVE,
            }
        ),
        "operation_layer_submit_mode": operation_layer_submit_mode,
        "temporary_live_aperture": (
            "remove_after_l2_l9_closure"
            if operation_layer_submit_mode
            == OPERATION_LAYER_SUBMIT_MODE_TEMP_TINY_LIVE
            else None
        ),
        "official_operation_layer_submit_called": True,
        "official_operation_layer_endpoint": True,
    }
    http_status = response.get("http_status")
    if http_status in {401, 403}:
        return _dispatch_artifact_from_operation_layer_submit(
            artifact=artifact,
            status="operation_layer_submit_blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_http_error",
            blockers=[f"operator_session_http_status:{http_status}"],
            submit_result=submit_result,
        )
    if response.get("error"):
        return _dispatch_artifact_from_operation_layer_submit(
            artifact=artifact,
            status="operation_layer_submit_blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_ticket_bound_protected_submit_http_error",
            blockers=[
                f"ticket_bound_protected_submit_http_status:{http_status or 'unavailable'}"
            ],
            submit_result=submit_result,
        )
    forbidden_effects = _ticket_bound_submit_forbidden_effects(
        body,
        submit_mode=operation_layer_submit_mode,
    )
    if forbidden_effects:
        return _dispatch_artifact_from_operation_layer_submit(
            artifact=artifact,
            status="operation_layer_submit_blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_ticket_bound_submit_forbidden_effect",
            blockers=forbidden_effects,
            submit_result=submit_result,
        )
    if operation_layer_submit_mode == OPERATION_LAYER_SUBMIT_MODE_DISABLED_SMOKE:
        if body.get("status") != "disabled_smoke_passed":
            return _dispatch_artifact_from_operation_layer_submit(
                artifact=artifact,
                status="operation_layer_submit_blocked",
                blocker_class="hard_safety_stop",
                dispatch_status="blocked_by_disabled_smoke_submit_result",
                blockers=[
                    "disabled_smoke_expected_disabled_smoke_passed:"
                    f"{body.get('status') or 'missing'}"
                ],
                submit_result=submit_result,
            )
        return _dispatch_artifact_from_operation_layer_submit(
            artifact=artifact,
            status="operation_layer_disabled_smoke_passed",
            blocker_class="none",
            dispatch_status="ticket_bound_protected_submit_disabled_smoke_passed",
            blockers=[],
            submit_result=submit_result,
        )

    if operation_layer_submit_mode not in {
        OPERATION_LAYER_SUBMIT_MODE_REAL,
        OPERATION_LAYER_SUBMIT_MODE_TEMP_TINY_LIVE,
    }:
        return _dispatch_artifact_from_operation_layer_submit(
            artifact=artifact,
            status="operation_layer_submit_blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_invalid_operation_layer_submit_mode",
            blockers=[
                f"invalid_operation_layer_submit_mode:{operation_layer_submit_mode}"
            ],
            submit_result=submit_result,
        )
    if body.get("status") == "submitted":
        identity_blockers = _ticket_bound_submit_result_identity_blockers(
            artifact=artifact,
            body=body,
        )
        if identity_blockers:
            return _dispatch_artifact_from_operation_layer_submit(
                artifact=artifact,
                status="operation_layer_submit_failed",
                blocker_class=_operation_layer_blocker_class(identity_blockers, []),
                dispatch_status="ticket_bound_submit_result_identity_mismatch",
                blockers=identity_blockers,
                submit_result=submit_result,
            )
        submitted_artifact = _dispatch_artifact_from_operation_layer_submit(
            artifact=artifact,
            status="submitted",
            blocker_class="none",
            dispatch_status="ticket_bound_protected_submit_completed",
            blockers=[],
            submit_result=submit_result,
        )
        if not execute_post_submit_finalize:
            return submitted_artifact
        return _execute_ticket_bound_post_submit_closure(
            artifact=submitted_artifact,
            timeout_seconds=timeout_seconds,
        )

    blockers = _dedupe_text(body.get("blockers") or [])
    return _dispatch_artifact_from_operation_layer_submit(
        artifact=artifact,
        status=(
            "operation_layer_submit_failed"
            if body.get("status") == "submit_failed"
            else "operation_layer_submit_blocked"
        ),
        blocker_class=_operation_layer_blocker_class(blockers, []),
        dispatch_status="blocked_by_ticket_bound_protected_submit_result",
        blockers=blockers or [f"ticket_bound_submit_status:{body.get('status') or 'missing'}"],
        submit_result=submit_result,
    )


def _ticket_bound_submit_body_for_dispatch(body: dict[str, Any]) -> dict[str, Any]:
    status = str(body.get("status") or "")
    exchange_write_called = body.get("exchange_write_called") is True
    order_lifecycle_called = body.get("order_lifecycle_called") is True
    return {
        **body,
        "exchange_called": exchange_write_called,
        "exchange_order_submitted": status == "submitted" and exchange_write_called,
        "order_lifecycle_submit_called": order_lifecycle_called,
    }


def _ticket_bound_submit_forbidden_effects(
    body: dict[str, Any],
    *,
    submit_mode: str,
) -> list[str]:
    effects: list[str] = []
    for key in (
        "withdrawal_or_transfer_created",
        "live_profile_changed",
        "order_sizing_changed",
    ):
        if body.get(key) not in {False, None, "", 0}:
            effects.append(f"ticket_bound_submit_forbidden_effect:{key}")
    if submit_mode == OPERATION_LAYER_SUBMIT_MODE_DISABLED_SMOKE:
        for key in (
            "exchange_write_called",
            "order_created",
            "order_lifecycle_called",
            "exchange_called",
            "exchange_order_submitted",
            "order_lifecycle_submit_called",
        ):
            if body.get(key) not in {False, None, "", 0}:
                effects.append(f"disabled_smoke_forbidden_effect:{key}")
    return effects


def _ticket_bound_submit_result_identity_blockers(
    *,
    artifact: dict[str, Any],
    body: dict[str, Any],
) -> list[str]:
    expected = {
        "ticket_id": artifact.get("ticket_id"),
        "operation_submit_command_id": artifact.get("operation_submit_command_id"),
        "strategy_group_id": artifact.get("strategy_group_id"),
        "symbol": artifact.get("symbol"),
        "side": artifact.get("side"),
    }
    blockers: list[str] = []
    for key, expected_value in expected.items():
        actual = str(body.get(key) or "")
        expected_text = str(expected_value or "")
        if not actual:
            blockers.append(f"ticket_bound_submit_result_missing:{key}")
        elif expected_text and actual != expected_text:
            blockers.append(
                f"ticket_bound_submit_result_mismatch:{key}:"
                f"expected={expected_text}:actual={actual}"
            )
    if not body.get("protected_submit_attempt_id"):
        blockers.append("protected_submit_attempt_id_missing")
    if not body.get("runtime_safety_snapshot_id"):
        blockers.append("runtime_safety_snapshot_id_missing")
    if body.get("submit_allowed") is not True:
        blockers.append("ticket_bound_submit_allowed_false")
    return _dedupe_text(blockers)


def _ticket_bound_post_submit_closure_url(
    *,
    artifact: dict[str, Any],
) -> tuple[str, str, list[str]]:
    body = _dict(_dict(artifact.get("operation_layer_submit_result")).get("body"))
    protected_submit_attempt_id = _first_text(body.get("protected_submit_attempt_id"))
    blockers: list[str] = []
    if not protected_submit_attempt_id:
        blockers.append("protected_submit_attempt_id_missing_for_post_submit_closure")
    api_base = str(
        _dict(artifact.get("operation_layer_handoff_plan")).get("api_base")
        or _dict(artifact.get("operation_layer_command_plan")).get("api_base")
        or DEFAULT_API_BASE
    ).rstrip("/")
    path = (
        "/api/trading-console/runtime-post-submit-closures/"
        "protected-submit-attempts/"
        f"{urllib.parse.quote(protected_submit_attempt_id or '', safe='')}"
    )
    return api_base + path, path, blockers


def _execute_ticket_bound_post_submit_closure(
    *,
    artifact: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    url, path, url_blockers = _ticket_bound_post_submit_closure_url(artifact=artifact)
    if url_blockers:
        return _dispatch_artifact_from_ticket_bound_post_submit_closure(
            artifact=artifact,
            status="post_submit_closure_blocked",
            blocker_class="missing_fact",
            dispatch_status="blocked_before_ticket_bound_post_submit_closure",
            blockers=url_blockers,
            closure_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": "ticket_bound_post_submit_closure_identity_missing",
            },
        )
    cookie, cookie_error = _session_cookie()
    if not cookie:
        return _dispatch_artifact_from_ticket_bound_post_submit_closure(
            artifact=artifact,
            status="post_submit_closure_blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_unavailable",
            blockers=[cookie_error or "operator_session_unavailable"],
            closure_result={
                "called": False,
                "http_status": None,
                "body": None,
                "error": cookie_error or "operator_session_unavailable",
            },
        )
    response = _request_json(
        method="POST",
        url=url,
        cookie=cookie,
        timeout_seconds=timeout_seconds,
    )
    body = _dict(response.get("body"))
    closure_result = {
        "called": True,
        "method": "POST",
        "path": path,
        "http_status": response.get("http_status"),
        "body": body,
        "error": bool(response.get("error")),
        "error_type": response.get("error_type"),
        "error_message": response.get("error_message"),
        "official_post_submit_finalize_endpoint": False,
        "ticket_bound_post_submit_closure_endpoint": True,
        "exchange_write_called": False,
        "places_order": False,
        "calls_order_lifecycle": False,
        "withdrawal_or_transfer_created": False,
    }
    http_status = response.get("http_status")
    if http_status in {401, 403}:
        return _dispatch_artifact_from_ticket_bound_post_submit_closure(
            artifact=artifact,
            status="post_submit_closure_blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_operator_session_http_error",
            blockers=[f"operator_session_http_status:{http_status}"],
            closure_result=closure_result,
        )
    if response.get("error"):
        return _dispatch_artifact_from_ticket_bound_post_submit_closure(
            artifact=artifact,
            status="post_submit_closure_blocked",
            blocker_class="deployment_issue",
            dispatch_status="blocked_by_ticket_bound_post_submit_closure_http_error",
            blockers=[
                f"ticket_bound_post_submit_closure_http_status:{http_status or 'unavailable'}"
            ],
            closure_result=closure_result,
        )
    forbidden_effects = _ticket_bound_post_submit_closure_forbidden_effects(body)
    if forbidden_effects:
        return _dispatch_artifact_from_ticket_bound_post_submit_closure(
            artifact=artifact,
            status="post_submit_closure_blocked",
            blocker_class="hard_safety_stop",
            dispatch_status="blocked_by_ticket_bound_post_submit_closure_forbidden_effect",
            blockers=forbidden_effects,
            closure_result=closure_result,
        )
    identity_blockers = _ticket_bound_post_submit_closure_identity_blockers(
        artifact=artifact,
        body=body,
    )
    if identity_blockers:
        return _dispatch_artifact_from_ticket_bound_post_submit_closure(
            artifact=artifact,
            status="post_submit_closure_blocked",
            blocker_class=_operation_layer_blocker_class(identity_blockers, []),
            dispatch_status="ticket_bound_post_submit_closure_identity_mismatch",
            blockers=identity_blockers,
            closure_result=closure_result,
        )

    body_status = str(body.get("status") or "")
    blockers = _dedupe_text(body.get("blockers") or [])
    if body_status == "reconciliation_pending":
        return _dispatch_artifact_from_ticket_bound_post_submit_closure(
            artifact=artifact,
            status="post_submit_reconciliation_pending",
            blocker_class="missing_fact",
            dispatch_status="ticket_bound_post_submit_closure_reconciliation_pending",
            blockers=blockers or ["post_submit_reconciliation_fact_missing"],
            closure_result=closure_result,
        )
    if body_status == "closed":
        closed_blockers = _ticket_bound_post_submit_closure_closed_blockers(body)
        if closed_blockers:
            return _dispatch_artifact_from_ticket_bound_post_submit_closure(
                artifact=artifact,
                status="post_submit_closure_blocked",
                blocker_class=_operation_layer_blocker_class(closed_blockers, []),
                dispatch_status="ticket_bound_post_submit_closure_closed_truth_mismatch",
                blockers=closed_blockers,
                closure_result=closure_result,
            )
        return _dispatch_artifact_from_ticket_bound_post_submit_closure(
            artifact=artifact,
            status="settled",
            blocker_class="none",
            dispatch_status="ticket_bound_post_submit_closure_closed",
            blockers=[],
            closure_result=closure_result,
        )
    return _dispatch_artifact_from_ticket_bound_post_submit_closure(
        artifact=artifact,
        status="post_submit_closure_blocked",
        blocker_class=_operation_layer_blocker_class(blockers, []),
        dispatch_status="blocked_by_ticket_bound_post_submit_closure_result",
        blockers=blockers or [f"post_submit_closure_status:{body_status or 'missing'}"],
        closure_result=closure_result,
    )


def _ticket_bound_post_submit_closure_forbidden_effects(
    body: dict[str, Any],
) -> list[str]:
    effects: list[str] = []
    checks = {
        "finalgate_called": False,
        "operation_layer_called": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "runtime_budget_mutated": False,
    }
    for name, expected in checks.items():
        if body.get(name) not in {expected, None, "", 0}:
            effects.append(f"ticket_bound_post_submit_closure_effect:{name}")
    return effects


def _ticket_bound_post_submit_closure_identity_blockers(
    *,
    artifact: dict[str, Any],
    body: dict[str, Any],
) -> list[str]:
    submit_body = _dict(_dict(artifact.get("operation_layer_submit_result")).get("body"))
    expected = {
        "protected_submit_attempt_id": submit_body.get("protected_submit_attempt_id"),
        "ticket_id": artifact.get("ticket_id"),
        "operation_submit_command_id": artifact.get("operation_submit_command_id"),
        "strategy_group_id": artifact.get("strategy_group_id"),
        "symbol": artifact.get("symbol"),
        "side": artifact.get("side"),
    }
    blockers: list[str] = []
    for key, expected_value in expected.items():
        actual = str(body.get(key) or "")
        expected_text = str(expected_value or "")
        if not actual:
            blockers.append(f"ticket_bound_post_submit_closure_missing:{key}")
        elif expected_text and actual != expected_text:
            blockers.append(
                f"ticket_bound_post_submit_closure_mismatch:{key}:"
                f"expected={expected_text}:actual={actual}"
            )
    return _dedupe_text(blockers)


def _ticket_bound_post_submit_closure_closed_blockers(
    body: dict[str, Any],
) -> list[str]:
    expected = {
        "protection_state": "submitted",
        "reconciliation_state": "matched",
        "settlement_state": "released",
        "review_state": "recorded",
    }
    blockers: list[str] = []
    for key, expected_value in expected.items():
        actual = str(body.get(key) or "")
        if actual != expected_value:
            blockers.append(
                f"ticket_bound_post_submit_closure_closed_truth:{key}:"
                f"expected={expected_value}:actual={actual or 'missing'}"
            )
    if body.get("first_blocker"):
        blockers.append("ticket_bound_post_submit_closure_closed_with_first_blocker")
    if body.get("blockers"):
        blockers.append("ticket_bound_post_submit_closure_closed_with_blockers")
    return _dedupe_text(blockers)


def _dispatch_artifact_from_ticket_bound_post_submit_closure(
    *,
    artifact: dict[str, Any],
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    closure_result: dict[str, Any],
) -> dict[str, Any]:
    body = _dict(closure_result.get("body"))
    closure_called = bool(closure_result.get("called"))
    owner_state = {
        "status": status,
        "blocker_class": blocker_class,
        "blocked_at": "post_submit_reconciliation",
        "blocked_reason": ",".join(blockers),
        "non_authority_checkpoint": body.get("next_action")
        or "run_ticket_bound_post_submit_reconciliation",
        "authority_mode": "halt_new_entries_until_post_submit_settled",
        "checkpoint_source": "ticket_bound_post_submit_closure",
    }
    if status == "settled":
        owner_state = {
            "status": "settled",
            "blocker_class": "none",
            "blocked_at": None,
            "blocked_reason": None,
            "non_authority_checkpoint": CONTINUE_ACTION,
            "checkpoint_source": "ticket_bound_post_submit_closure",
        }
    return {
        **artifact,
        "status": status,
        "blocker_class": blocker_class,
        "dispatch_status": dispatch_status,
        "dispatch_action": CONTINUE_ACTION if status == "settled" else None,
        "owner_state": _owner_state_projection(owner_state),
        "ticket_bound_post_submit_closure_result": closure_result,
        "blockers": blockers,
        "safety_invariants": {
            **_dict(artifact.get("safety_invariants")),
            "dispatcher_only": False,
            "ticket_bound_post_submit_closure_called": closure_called,
            "ticket_bound_post_submit_closure_endpoint": closure_called,
            "official_post_submit_finalize_called": False,
            "post_submit_budget_settlement_called": False,
            "runtime_budget_mutated": False,
            "mutates_pg": bool(
                closure_called
                or _dict(artifact.get("safety_invariants")).get("mutates_pg")
            ),
            "withdrawal_or_transfer_created": bool(
                body.get("withdrawal_or_transfer_created")
            ),
        },
    }


def _dispatch_artifact_from_operation_layer_submit(
    *,
    artifact: dict[str, Any],
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    submit_result: dict[str, Any],
) -> dict[str, Any]:
    body = _dict(submit_result.get("body"))
    owner_state = _owner_state_for_operation_layer_submit(
        status=status,
        blocker_class=blocker_class,
        dispatch_status=dispatch_status,
        blockers=blockers,
        body=body,
    )
    called = bool(submit_result.get("called"))
    exchange_called = bool(body.get("exchange_called"))
    exchange_order_submitted = bool(body.get("exchange_order_submitted"))
    order_lifecycle_submit_called = bool(body.get("order_lifecycle_submit_called"))
    return {
        **artifact,
        "status": status,
        "blocker_class": blocker_class,
        "dispatch_status": dispatch_status,
        "dispatch_action": (
            POST_SUBMIT_FINALIZE_ACTION
            if status == "submitted"
            else (
                CONTINUE_ACTION
                if status == "operation_layer_disabled_smoke_passed"
                else None
            )
        ),
        "owner_state": _owner_state_projection(owner_state),
        "operation_layer_submit_result": submit_result,
        "blockers": blockers,
        "safety_invariants": {
            **_dict(artifact.get("safety_invariants")),
            "dispatcher_only": False,
            "official_operation_layer_submit_called": called,
            "official_operation_layer_submit_endpoint": called,
            "official_operation_layer_submit_http_status": submit_result.get(
                "http_status"
            ),
            "standing_authorized_first_real_submit": bool(
                submit_result.get("standing_authorized_first_real_submit")
            ),
            "owner_chat_confirmation_required_for_real_submit": bool(
                submit_result.get("owner_chat_confirmation_required_for_real_submit")
            ),
            "legacy_owner_confirmation_env_required": bool(
                submit_result.get("legacy_owner_confirmation_env_required")
            ),
            "standing_authorization_consumed_for_real_submit": bool(
                submit_result.get("standing_authorization_consumed_for_real_submit")
            ),
            "mutates_pg": bool(
                called or _dict(artifact.get("safety_invariants")).get("mutates_pg")
            ),
            "pg_submit_evidence_mutated": called,
            "places_order": exchange_order_submitted,
            "calls_order_lifecycle": order_lifecycle_submit_called,
            "exchange_write_called": exchange_called,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": bool(
                body.get("withdrawal_or_transfer_created")
            ),
            "official_post_submit_finalize_called": False,
            "post_submit_budget_settlement_called": False,
        },
    }


def _owner_state_for_operation_layer_submit(
    *,
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
    body: dict[str, Any],
) -> dict[str, Any]:
    if status == "submitted":
        return {
            "status": "submitted",
            "blocker_class": "none",
            "blocked_at": "none",
            "blocked_reason": "none",
            "next_recover_condition": "post_submit_finalize_reconciliation_budget_settlement",
            "non_authority_checkpoint": POST_SUBMIT_FINALIZE_ACTION,
            "authority_mode": "none",
            "exchange_submit_execution_status": body.get("status"),
        }
    if status == "operation_layer_disabled_smoke_passed":
        return {
            "status": status,
            "blocker_class": "none",
            "blocked_at": "none",
            "blocked_reason": "none",
            "next_recover_condition": "fresh_strategy_signal_or_real_gateway_action",
            "non_authority_checkpoint": CONTINUE_ACTION,
            "authority_mode": "none",
            "exchange_submit_execution_status": body.get("status"),
        }
    if status == "operation_layer_submit_failed":
        return {
            "status": status,
            "blocker_class": blocker_class,
            "blocked_at": "OperationLayerSubmit",
            "blocked_reason": blockers[0] if blockers else dispatch_status,
            "next_recover_condition": (
                "reconcile_exchange_and_local_order_state_then_apply_recovery_policy"
            ),
            "non_authority_checkpoint": (
                "run_post_submit_reconciliation_and_protection_failure_policy"
            ),
            "authority_mode": "halt_new_entries_until_reconciled",
            "exchange_submit_execution_status": body.get("status"),
        }
    if dispatch_status == "blocked_by_legacy_authorization_operation_layer_submit":
        return {
            "status": status,
            "blocker_class": blocker_class,
            "blocked_at": "OperationLayerSubmit",
            "blocked_reason": blockers[0] if blockers else dispatch_status,
            "next_recover_condition": (
                "ticket_bound_action_time_ticket_and_protected_submit_available"
            ),
            "non_authority_checkpoint": (
                "materialize_action_time_ticket_and_ticket_bound_operation_layer_handoff"
            ),
            "authority_mode": "continue_watcher_observation_no_submit",
            "exchange_submit_execution_status": body.get("status"),
        }
    return {
        "status": status,
        "blocker_class": blocker_class,
        "blocked_at": "OperationLayerSubmit",
        "blocked_reason": blockers[0] if blockers else dispatch_status,
        "next_recover_condition": "operation_layer_submit_blocker_resolved",
        "non_authority_checkpoint": (
            "refresh_operation_layer_evidence_and_rerun_action_time_finalgate"
        ),
        "authority_mode": "continue_watcher_observation_no_submit",
        "exchange_submit_execution_status": body.get("status"),
    }


def _owner_state_for_preflight(
    *,
    status: str,
    blocker_class: str,
    dispatch_status: str,
    blockers: list[str],
) -> dict[str, Any]:
    if status == "finalgate_ready":
        return {
            "status": "finalgate_ready",
            "blocker_class": "none",
            "blocked_at": "none",
            "blocked_reason": "none",
            "next_recover_condition": "ticket_bound_operation_layer_handoff_ready",
            "non_authority_checkpoint": (
                TICKET_BOUND_OPERATION_LAYER_HANDOFF_ACTION
            ),
            "authority_mode": "none",
        }
    if dispatch_status in {
        "blocked_by_operator_session_unavailable",
        "blocked_by_operator_session_http_error",
    }:
        return {
            "status": "blocked",
            "blocker_class": blocker_class,
            "blocked_at": "operator_session",
            "blocked_reason": dispatch_status,
            "next_recover_condition": "operator_session_available_for_local_official_preflight",
            "non_authority_checkpoint": "restore_operator_session_or_local_session_signing",
            "authority_mode": "continue_watcher_observation_no_submit",
        }
    if dispatch_status == "blocked_by_action_time_finalgate":
        return {
            "status": "blocked",
            "blocker_class": blocker_class,
            "blocked_at": "FinalGate",
            "blocked_reason": blockers[0] if blockers else "action_time_finalgate_blocked",
            "next_recover_condition": "fresh_action_time_facts_pass_finalgate",
            "non_authority_checkpoint": "refresh_action_time_facts_or_return_to_observation",
            "authority_mode": "observe_only_no_submit",
        }
    if dispatch_status == "blocked_by_missing_ticket_bound_operation_layer_handoff":
        return {
            "status": "blocked",
            "blocker_class": blocker_class,
            "blocked_at": "OperationLayerHandoff",
            "blocked_reason": "operation_layer_ticket_handoff_missing",
            "next_recover_condition": (
                "ticket_id_and_finalgate_pass_id_bound_to_operation_layer"
            ),
            "non_authority_checkpoint": (
                "implement_ticket_bound_operation_layer_handoff"
            ),
            "authority_mode": "continue_watcher_observation_no_submit",
        }
    if dispatch_status == "blocked_by_legacy_finalgate_authorization_without_ticket":
        return {
            "status": "blocked",
            "blocker_class": blocker_class,
            "blocked_at": "FinalGate",
            "blocked_reason": blockers[0] if blockers else dispatch_status,
            "next_recover_condition": (
                "pg_action_time_ticket_and_ticket_bound_finalgate_materialized"
            ),
            "non_authority_checkpoint": "materialize_pg_action_time_ticket",
            "authority_mode": "continue_watcher_observation_no_submit",
        }
    return {
        "status": "blocked",
        "blocker_class": blocker_class,
        "blocked_at": "FinalGate",
        "blocked_reason": blockers[0] if blockers else dispatch_status,
        "next_recover_condition": "preflight_blocker_resolved",
        "non_authority_checkpoint": "retry_official_action_time_finalgate_preflight_after_repair",
        "authority_mode": "continue_watcher_observation_no_submit",
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a Runtime Signal Watcher resume dispatch artifact, optionally "
            "calling the official action-time FinalGate preflight GET."
        ),
    )
    parser.add_argument(
        "--identity-source",
        choices=("pg_ticket",),
        default="pg_ticket",
        help="Trade identity source. Production dispatch uses PG ticket identity only.",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("PG_DATABASE_URL") or os.environ.get("DATABASE_URL") or "",
        help="PG DSN used when --identity-source=pg_ticket.",
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--label", default="tokyo-runtime-signal-watcher")
    parser.add_argument(
        "--selected-strategy-group-id",
        default=os.environ.get("BRC_SELECTED_STRATEGY_GROUP_ID")
        or os.environ.get("BRC_STRATEGYGROUP_SELECTED_ID"),
        help=(
            "Optional selected StrategyGroup scope. When set, actionable "
            "fresh-authorization, FinalGate, or Operation Layer dispatch is "
            "blocked unless the resume artifact proves the action belongs to "
            "that StrategyGroup."
        ),
    )
    parser.add_argument(
        "--execute-preflight",
        action="store_true",
        help=(
            "Call the official action-time FinalGate preflight when ready, or "
            "the official fresh-authorization binding API when parked at that "
            "non-executing checkpoint."
        ),
    )
    parser.add_argument(
        "--execute-operation-layer-submit",
        action="store_true",
        help=(
            "After ticket-bound FinalGate preflight and Operation Layer "
            "handoff pass, call the ticket-bound protected submit endpoint. "
            "Legacy authorization Operation Layer submit is retired and "
            "blocks fail-closed."
        ),
    )
    parser.add_argument(
        "--operation-layer-submit-mode",
        choices=sorted(OPERATION_LAYER_SUBMIT_MODES),
        default=OPERATION_LAYER_SUBMIT_MODE_REAL,
        help=(
            "Operation Layer submit mode used with "
            "--execute-operation-layer-submit. real_gateway_action keeps the "
            "existing real-order boundary for ticket-bound protected submit; "
            "disabled_smoke calls the protected submit endpoint in no-exchange "
            "mode and requires disabled_smoke_passed. "
            "temp_tiny_live_protected_submit is a temporary ENTRY+SL+TP1 live "
            "aperture and must be removed after L2-L9 closure."
        ),
    )
    parser.add_argument(
        "--execute-post-submit-finalize",
        action="store_true",
        help=(
            "After ticket-bound protected submit succeeds, call the official "
            "post-submit finalize endpoint to record reconciliation and "
            "budget settlement evidence."
        ),
    )
    parser.add_argument(
        "--preflight-timeout-seconds",
        type=int,
        default=120,
        help="HTTP timeout for --execute-preflight.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    resume_pack, source_path = _pg_ticket_resume_pack(
        database_url=args.database_url,
        api_base=args.api_base,
    )
    artifact = build_dispatch_artifact(
        resume_pack=resume_pack,
        source_path=source_path,
        api_base=args.api_base,
        label=args.label,
        execute_preflight=args.execute_preflight,
        preflight_timeout_seconds=args.preflight_timeout_seconds,
        execute_operation_layer_submit=args.execute_operation_layer_submit,
        operation_layer_submit_mode=args.operation_layer_submit_mode,
        execute_post_submit_finalize=args.execute_post_submit_finalize,
        selected_strategy_group_id=args.selected_strategy_group_id,
    )
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    if artifact.get("dispatch_status") == (
        "blocked_by_missing_ticket_bound_operation_layer_handoff"
    ):
        return 1
    return 0 if artifact["status"] in {
        WAITING_STATUS,
        READY_STATUS,
        *FRESH_AUTHORIZATION_STATUSES,
        NON_EXECUTING_PREPARE_STATUS,
        "fresh_authorization_bound",
        "finalgate_ready",
        "operation_layer_ready",
        "operation_layer_blocked",
        "operation_layer_submit_blocked",
        "operation_layer_submit_failed",
        "submitted",
        "settled",
        "post_submit_finalize_blocked",
        "post_submit_finalized_next_attempt_blocked",
        "blocked",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
