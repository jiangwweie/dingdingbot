"""Formal current incident projection for non-lane runtime failures."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import sqlalchemy as sa

from src.application.action_time.netting_domain_hold import (
    resolve_netting_domain_hold_source,
    upsert_netting_domain_hold,
)
from src.application.action_time.lifecycle_safety_core import reduce_lifecycle_decision


INITIAL_STOP_INCIDENT_TYPE = "initial_stop_not_established"
INITIAL_STOP_HOLD_SOURCE_KIND = "protection_barrier"
INITIAL_STOP_AUTHORITY_BOUNDARY = (
    "initial_stop_incident_projection; typed Attempt plus exact ENTRY command "
    "identity; current incident and source-specific NettingDomain hold only; "
    "no exchange-write, ENTRY retry, sizing, profile, transfer, or policy authority"
)


def upsert_system_runtime_incident(
    conn: sa.engine.Connection,
    *,
    incident_type: str,
    blocker: str,
    details: dict[str, Any],
    now_ms: int,
) -> dict[str, str]:
    if not sa.inspect(conn).has_table("brc_runtime_incidents"):
        return {"status": "incident_table_missing", "incident_id": ""}
    table = sa.Table("brc_runtime_incidents", sa.MetaData(), autoload_with=conn)
    fingerprint = sha256(f"system:{incident_type}:{blocker}".encode()).hexdigest()[:48]
    incident_id = f"incident:system:{fingerprint}"
    values = {
        "incident_id": incident_id, "incident_type": incident_type,
        "severity": "blocking", "status": "open", "strategy_group_id": None,
        "symbol": None, "side": None, "blocker_class": blocker,
        "trigger_ref": str(details.get("source_watermark") or ""),
        "details": details, "opened_at_ms": now_ms, "closed_at_ms": None,
    }
    existing = conn.execute(sa.select(table.c.incident_id).where(table.c.incident_id == incident_id)).scalar_one_or_none()
    if existing is None:
        conn.execute(table.insert().values(**values))
    else:
        conn.execute(table.update().where(table.c.incident_id == incident_id).values(
            status="open", blocker_class=blocker, trigger_ref=values["trigger_ref"],
            details=details, closed_at_ms=None,
        ))
    return {"status": "open", "incident_id": incident_id}


def project_protection_barrier_failure(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    order_role: str,
    blocker: str,
    outcome_ambiguous: bool,
    protection_barrier_generation: int,
    trigger_ref: str,
    now_ms: int,
) -> dict[str, Any]:
    """Project one typed protection failure without creating exchange effects."""

    attempt, entry = _protection_identity(
        conn,
        protected_submit_attempt_id=protected_submit_attempt_id,
    )
    role = str(order_role or "").upper()
    normalized_blocker = str(blocker or "").strip()
    current_generation = int(attempt.get("protection_barrier_generation") or 1)
    observed_generation = int(protection_barrier_generation or 0)
    if observed_generation != current_generation:
        return {
            "status": "stale_generation_ignored",
            "incident_id": "",
            "hold_id": "",
            "first_blocker": None,
            "next_action": "retain_current_protection_generation_truth",
        }
    if not normalized_blocker:
        raise ValueError("protection_barrier_incident_blocker_required")
    if role == "TP1":
        return _project_tp1_degraded(
            conn,
            attempt=attempt,
            blocker=normalized_blocker,
            now_ms=now_ms,
        )
    if role != "SL":
        raise ValueError("protection_barrier_incident_role_invalid")
    if str(attempt.get("entry_effect_state") or "") != "accepted_filled":
        raise ValueError("initial_stop_incident_requires_filled_entry_effect")
    if str(attempt.get("protection_barrier_state") or "") in {
        "initial_stop_confirmed",
        "degraded",
        "closed",
    }:
        return {
            "status": "terminal_barrier_retained",
            "incident_id": "",
            "hold_id": "",
            "first_blocker": None,
            "next_action": "retain_current_protection_barrier_truth",
        }

    generation = current_generation
    incident_id = _initial_stop_incident_id(
        attempt=attempt,
        entry=entry,
        protection_barrier_generation=generation,
    )
    details = {
        "schema": "brc.initial_stop_not_established_incident.v1",
        "ticket_id": str(attempt["ticket_id"]),
        "protected_submit_attempt_id": str(
            attempt["protected_submit_attempt_id"]
        ),
        "exposure_episode_id": str(entry["exposure_episode_id"]),
        "netting_domain_key": str(entry["netting_domain_key"]),
        "protection_barrier_generation": generation,
        "protection_quantity": str(attempt.get("protection_quantity") or ""),
        "outcome_ambiguous": bool(outcome_ambiguous),
        "first_blocker": normalized_blocker,
        "next_action": (
            "reconcile_exact_initial_stop_exchange_identity"
            if outcome_ambiguous
            else "prepare_exact_initial_stop_recovery_generation"
        ),
    }
    table = _table(conn, "brc_runtime_incidents")
    existing = conn.execute(
        sa.select(table).where(table.c.incident_id == incident_id)
    ).mappings().first()
    values = {
        "incident_id": incident_id,
        "incident_type": INITIAL_STOP_INCIDENT_TYPE,
        "severity": "critical",
        "status": "open",
        "strategy_group_id": str(attempt["strategy_group_id"]),
        "symbol": str(attempt["symbol"]),
        "side": str(attempt["side"]),
        "blocker_class": normalized_blocker,
        "trigger_ref": str(trigger_ref or incident_id),
        "details": details,
        "opened_at_ms": (
            int(existing.get("opened_at_ms") or now_ms) if existing else now_ms
        ),
        "closed_at_ms": None,
    }
    if existing:
        conn.execute(
            table.update().where(table.c.incident_id == incident_id).values(**values)
        )
    else:
        conn.execute(table.insert().values(**values))

    _project_protection_state(
        conn,
        attempt=attempt,
        barrier_state="hard_stopped",
        lifecycle_status="protection_missing",
        blocker=normalized_blocker,
        now_ms=now_ms,
    )
    hold = ensure_protection_barrier_hold(
        conn,
        protected_submit_attempt_id=protected_submit_attempt_id,
        protection_barrier_generation=generation,
        blocker=normalized_blocker,
        next_action=str(details["next_action"]),
        now_ms=now_ms,
    )
    return {
        "status": "open",
        "incident_id": incident_id,
        "hold_id": str(hold["scope_freeze_id"]),
        "first_blocker": normalized_blocker,
        "next_action": details["next_action"],
    }


def resolve_initial_stop_incident(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    protection_barrier_generation: int,
    resolution_source: str,
    now_ms: int,
) -> dict[str, Any]:
    """Close one exact barrier-generation incident and only its own hold."""

    attempt, entry = _protection_identity(
        conn,
        protected_submit_attempt_id=protected_submit_attempt_id,
    )
    current_generation = int(attempt.get("protection_barrier_generation") or 1)
    if int(protection_barrier_generation or 0) != current_generation:
        return {
            "status": "stale_generation_ignored",
            "incident_id": "",
            "resolved_hold_count": 0,
        }
    if str(attempt.get("protection_barrier_state") or "") not in {
        "initial_stop_confirmed",
        "degraded",
        "closed",
    }:
        raise ValueError("initial_stop_incident_resolution_proof_missing")
    incident_id = _initial_stop_incident_id(
        attempt=attempt,
        entry=entry,
        protection_barrier_generation=current_generation,
    )
    table = _table(conn, "brc_runtime_incidents")
    existing = conn.execute(
        sa.select(table).where(table.c.incident_id == incident_id)
    ).mappings().first()
    barrier_source_id = _protection_barrier_source_id(
        attempt=attempt,
        entry=entry,
        protection_barrier_generation=current_generation,
    )
    resolved_hold_count = resolve_netting_domain_hold_source(
        conn,
        netting_domain_key=str(entry["netting_domain_key"]),
        source_kind=INITIAL_STOP_HOLD_SOURCE_KIND,
        source_id=barrier_source_id,
        resolution_source=str(resolution_source or "initial_stop_reconciled"),
        now_ms=now_ms,
    )
    if existing is None:
        return {
            "status": "not_open",
            "incident_id": incident_id,
            "resolved_hold_count": resolved_hold_count,
        }
    closed_at_ms = int(existing.get("closed_at_ms") or now_ms)
    details = _mapping(existing.get("details"))
    details.update(
        {
            "resolution_source": str(resolution_source or ""),
            "resolved_at_ms": closed_at_ms,
        }
    )
    conn.execute(
        table.update()
        .where(table.c.incident_id == incident_id)
        .values(status="closed", details=details, closed_at_ms=closed_at_ms)
    )
    return {
        "status": "closed",
        "incident_id": incident_id,
        "resolved_hold_count": resolved_hold_count,
    }


def ensure_protection_barrier_hold(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    protection_barrier_generation: int,
    blocker: str,
    next_action: str,
    now_ms: int,
) -> dict[str, Any]:
    """Fence new exposure immediately for one exact active barrier generation."""

    attempt, entry = _protection_identity(
        conn,
        protected_submit_attempt_id=protected_submit_attempt_id,
    )
    current_generation = int(attempt.get("protection_barrier_generation") or 1)
    if int(protection_barrier_generation or 0) != current_generation:
        raise ValueError("protection_barrier_hold_generation_stale")
    source_id = _protection_barrier_source_id(
        attempt=attempt,
        entry=entry,
        protection_barrier_generation=current_generation,
    )
    return upsert_netting_domain_hold(
        conn,
        account_id=entry.get("account_id"),
        runtime_profile_id=entry.get("runtime_profile_id"),
        exchange_id=entry.get("exchange_id"),
        exchange_instrument_id=entry.get("exchange_instrument_id"),
        position_mode=entry.get("position_mode"),
        position_bucket=entry.get("position_bucket"),
        netting_domain_key=entry.get("netting_domain_key"),
        source_ticket_id=entry.get("ticket_id"),
        strategy_group_id=entry.get("strategy_group_id"),
        symbol=entry.get("symbol"),
        side=entry.get("side"),
        source_kind=INITIAL_STOP_HOLD_SOURCE_KIND,
        source_id=source_id,
        blockers=[str(blocker or "initial_stop_pending")],
        next_action=next_action,
        authority_boundary=INITIAL_STOP_AUTHORITY_BOUNDARY,
        now_ms=now_ms,
    )


def supersede_protection_barrier_generation(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    protection_barrier_generation: int,
    now_ms: int,
) -> dict[str, Any]:
    """Close the prior barrier source before atomically advancing generation."""

    attempt, entry = _protection_identity(
        conn,
        protected_submit_attempt_id=protected_submit_attempt_id,
    )
    prior_generation = int(protection_barrier_generation or 0)
    if prior_generation != int(attempt.get("protection_barrier_generation") or 1):
        raise ValueError("protection_barrier_supersede_generation_stale")
    source_id = _protection_barrier_source_id(
        attempt=attempt,
        entry=entry,
        protection_barrier_generation=prior_generation,
    )
    resolved = resolve_netting_domain_hold_source(
        conn,
        netting_domain_key=str(entry["netting_domain_key"]),
        source_kind=INITIAL_STOP_HOLD_SOURCE_KIND,
        source_id=source_id,
        resolution_source="protection_barrier_generation_superseded",
        now_ms=now_ms,
    )
    incident_id = _initial_stop_incident_id(
        attempt=attempt,
        entry=entry,
        protection_barrier_generation=prior_generation,
    )
    incidents = _table(conn, "brc_runtime_incidents")
    incident = conn.execute(
        sa.select(incidents).where(incidents.c.incident_id == incident_id)
    ).mappings().one_or_none()
    if incident and str(incident.get("status") or "") != "closed":
        details = _mapping(incident.get("details"))
        details.update(
            {
                "resolution_source": "protection_barrier_generation_superseded",
                "resolved_at_ms": now_ms,
            }
        )
        conn.execute(
            incidents.update()
            .where(incidents.c.incident_id == incident_id)
            .values(status="closed", details=details, closed_at_ms=now_ms)
        )
    return {
        "status": "superseded",
        "barrier_source_id": source_id,
        "incident_id": incident_id if incident else "",
        "resolved_hold_count": resolved,
    }


def resolve_protection_barrier_from_flat_proof(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    ticket_id: str,
    exposure_episode_id: str,
    netting_domain_key: str,
    source_entry_exchange_command_id: str,
    protection_barrier_generation: int,
    authoritative_position_flat: bool,
    exact_live_residual_absent: bool,
    resolution_source: str,
    now_ms: int,
) -> dict[str, Any]:
    """Close one current barrier from exact flat and no-residual evidence."""

    if not authoritative_position_flat or not exact_live_residual_absent:
        return {"status": "flat_proof_incomplete", "resolved_hold_count": 0}
    attempt, entry = _protection_identity(
        conn,
        protected_submit_attempt_id=protected_submit_attempt_id,
    )
    generation = int(protection_barrier_generation or 0)
    if generation != int(attempt.get("protection_barrier_generation") or 1):
        return {"status": "stale_generation_ignored", "resolved_hold_count": 0}
    expected_identity = {
        "ticket_id": str(attempt.get("ticket_id") or ""),
        "exposure_episode_id": str(entry.get("exposure_episode_id") or ""),
        "netting_domain_key": str(entry.get("netting_domain_key") or ""),
        "source_entry_exchange_command_id": str(
            entry.get("exchange_command_id") or ""
        ),
    }
    observed_identity = {
        "ticket_id": str(ticket_id or ""),
        "exposure_episode_id": str(exposure_episode_id or ""),
        "netting_domain_key": str(netting_domain_key or ""),
        "source_entry_exchange_command_id": str(
            source_entry_exchange_command_id or ""
        ),
    }
    if observed_identity != expected_identity:
        return {"status": "identity_mismatch", "resolved_hold_count": 0}
    if str(entry.get("protected_submit_attempt_id") or "") != str(
        attempt.get("protected_submit_attempt_id") or ""
    ) or str(entry.get("source_command_id") or "") != str(
        attempt.get("protected_submit_attempt_id") or ""
    ):
        return {"status": "identity_mismatch", "resolved_hold_count": 0}

    attempts = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    barrier = str(attempt.get("protection_barrier_state") or "")
    if str(attempt.get("entry_effect_state") or "") == "accepted_filled" and barrier in {
        "initial_stop_pending",
        "initial_stop_confirmed",
        "degraded",
        "hard_stopped",
    }:
        updated = conn.execute(
            attempts.update()
            .where(
                attempts.c.protected_submit_attempt_id
                == protected_submit_attempt_id,
                attempts.c.protection_barrier_generation == generation,
                attempts.c.protection_barrier_state == barrier,
            )
            .values(protection_barrier_state="closed", updated_at_ms=now_ms)
            .returning(attempts.c.protected_submit_attempt_id)
        ).scalar_one_or_none()
        if updated is None:
            return {"status": "flat_proof_cas_failed", "resolved_hold_count": 0}
    elif barrier != "closed":
        return {"status": "flat_proof_barrier_not_closable", "resolved_hold_count": 0}

    resolved = resolve_initial_stop_incident(
        conn,
        protected_submit_attempt_id=protected_submit_attempt_id,
        protection_barrier_generation=generation,
        resolution_source=resolution_source,
        now_ms=now_ms,
    )
    return {
        "status": "closed_from_flat_proof",
        "incident_id": resolved.get("incident_id", ""),
        "resolved_hold_count": int(resolved.get("resolved_hold_count") or 0),
    }


def _project_tp1_degraded(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    blocker: str,
    now_ms: int,
) -> dict[str, Any]:
    if str(attempt.get("protection_barrier_state") or "") not in {
        "initial_stop_confirmed",
        "degraded",
    }:
        raise ValueError("tp1_degraded_requires_confirmed_initial_stop")
    _project_protection_state(
        conn,
        attempt=attempt,
        barrier_state="degraded",
        lifecycle_status="protection_degraded",
        blocker=blocker,
        now_ms=now_ms,
    )
    return {
        "status": "protection_degraded",
        "incident_id": "",
        "hold_id": "",
        "first_blocker": blocker,
        "next_action": "reconcile_or_recover_tp1_without_replacing_initial_stop",
    }


def _project_protection_state(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    barrier_state: str,
    lifecycle_status: str,
    blocker: str,
    now_ms: int,
) -> None:
    attempts = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    terminal_barriers = {"initial_stop_confirmed", "degraded", "closed"}
    current_barrier = str(attempt.get("protection_barrier_state") or "")
    if barrier_state == "hard_stopped" and current_barrier in terminal_barriers:
        return
    conn.execute(
        attempts.update()
        .where(
            attempts.c.protected_submit_attempt_id
            == attempt["protected_submit_attempt_id"],
            attempts.c.protection_barrier_generation
            == int(attempt.get("protection_barrier_generation") or 1),
        )
        .values(protection_barrier_state=barrier_state, updated_at_ms=now_ms)
    )
    lifecycles = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    lifecycle = conn.execute(
        sa.select(lifecycles).where(
            lifecycles.c.protected_submit_attempt_id
            == attempt["protected_submit_attempt_id"]
        )
    ).mappings().one_or_none()
    if lifecycle is None:
        return
    current_status = str(lifecycle.get("status") or "")
    if current_status in {
        "reconciliation_matched",
        "budget_settled",
        "review_recorded",
        "lifecycle_closed",
    }:
        return
    decision = reduce_lifecycle_decision(
        current_status=current_status,
        target_status=lifecycle_status,
        blockers=[blocker],
    )
    conn.execute(
        lifecycles.update()
        .where(lifecycles.c.lifecycle_run_id == lifecycle["lifecycle_run_id"])
        .values(
            status=decision.status,
            first_blocker=decision.first_blocker,
            blockers=list(decision.blockers),
            updated_at_ms=now_ms,
        )
    )


def _protection_identity(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    attempt_id = str(protected_submit_attempt_id or "").strip()
    if not attempt_id:
        raise ValueError("protected_submit_attempt_id_required")
    attempts = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    attempt = conn.execute(
        sa.select(attempts).where(
            attempts.c.protected_submit_attempt_id == attempt_id
        )
    ).mappings().one_or_none()
    if attempt is None:
        raise ValueError("protected_submit_attempt_missing")
    commands = _table(conn, "brc_ticket_bound_exchange_commands")
    entries = list(
        conn.execute(
            sa.select(commands).where(
                commands.c.protected_submit_attempt_id == attempt_id,
                commands.c.order_role == "ENTRY",
            )
        ).mappings()
    )
    if len(entries) != 1:
        raise ValueError("initial_stop_incident_entry_command_cardinality_invalid")
    entry = dict(entries[0])
    for field in ("ticket_id", "exposure_episode_id", "netting_domain_key"):
        if not str(entry.get(field) or "").strip():
            raise ValueError(f"initial_stop_incident_identity_missing:{field}")
    return dict(attempt), entry


def _initial_stop_incident_id(
    *,
    attempt: dict[str, Any],
    entry: dict[str, Any],
    protection_barrier_generation: int,
) -> str:
    return protection_barrier_incident_id(
        ticket_id=str(attempt["ticket_id"]),
        exposure_episode_id=str(entry["exposure_episode_id"]),
        protection_barrier_generation=protection_barrier_generation,
    )


def protection_barrier_incident_id(
    *,
    ticket_id: str,
    exposure_episode_id: str,
    protection_barrier_generation: int,
) -> str:
    """Return the stable exact identity shared by projector and safety gates."""

    fingerprint = sha256(
        "\x1f".join(
            (
                str(ticket_id),
                str(exposure_episode_id),
                str(protection_barrier_generation),
            )
        ).encode()
    ).hexdigest()[:48]
    return f"incident:initial_stop:{fingerprint}"


def _protection_barrier_source_id(
    *,
    attempt: dict[str, Any],
    entry: dict[str, Any],
    protection_barrier_generation: int,
) -> str:
    fingerprint = sha256(
        "\x1f".join(
            (
                str(attempt["ticket_id"]),
                str(entry["exposure_episode_id"]),
                str(protection_barrier_generation),
            )
        ).encode()
    ).hexdigest()[:48]
    return f"protection_barrier:{fingerprint}"


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    if not sa.inspect(conn).has_table(table_name):
        raise ValueError(f"runtime_incident_projection_table_missing:{table_name}")
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        import json

        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}
