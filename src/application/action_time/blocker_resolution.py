"""Explicitly certify resolution of one persisted Action-Time blocker."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from src.application.runtime_process_outcome import (
    materialize_runtime_process_outcome,
)
from src.domain.runtime_lane_identity import RuntimeLaneIdentity


PROCESS_NAMES = {
    "action_time_ticket_sequence",
    "action_time_ticket_sequence_batch",
}
BLOCKING_STATES = {"business_blocked", "retryable_failure", "hard_failure"}


def certify_action_time_blocker_resolution(
    conn: sa.engine.Connection,
    *,
    process_outcome_id: str,
    expected_first_blocker: str,
    certification_ref: str,
    runtime_head: str,
    now_ms: int,
) -> dict[str, Any]:
    """Replace an exact unresolved lane blocker with a certified success.

    This is a non-executing engineering certification surface.  It cannot
    create a signal, Ticket, runtime grant, exchange command, or submit
    authority.  Exact outcome id and blocker matching prevent broad clearing.
    """

    table = sa.Table(
        "brc_runtime_process_outcomes",
        sa.MetaData(),
        autoload_with=conn,
    )
    outcome = conn.execute(
        sa.select(table).where(
            table.c.process_outcome_id == str(process_outcome_id or "").strip()
        )
    ).mappings().first()
    blockers: list[str] = []
    if outcome is None:
        blockers.append("process_outcome_missing")
    else:
        if str(outcome.get("process_name") or "") not in PROCESS_NAMES:
            blockers.append("process_outcome_name_mismatch")
        scope_key = str(outcome.get("scope_key") or "")
        if not scope_key.startswith("lane:") or len(scope_key.split(":")) != 4:
            blockers.append("process_outcome_lane_scope_invalid")
        if str(outcome.get("process_state") or "") not in BLOCKING_STATES:
            blockers.append("process_outcome_not_blocking")
        if str(outcome.get("first_blocker") or "") != str(
            expected_first_blocker or ""
        ):
            blockers.append("process_outcome_first_blocker_mismatch")
    certification_ref = str(certification_ref or "").strip()
    runtime_head = str(runtime_head or "").strip()
    lane_identity: RuntimeLaneIdentity | None = None
    if outcome is not None and str(outcome.get("process_name") or "") == (
        "action_time_ticket_sequence"
    ):
        try:
            lane_identity = RuntimeLaneIdentity.model_validate(
                {
                    field: outcome.get(field)
                    for field in RuntimeLaneIdentity.model_fields
                }
            )
        except (TypeError, ValueError):
            blockers.append("runtime_lane_identity_invalid")
    if not certification_ref:
        blockers.append("certification_ref_required")
    if not runtime_head:
        blockers.append("runtime_head_required")
    if blockers:
        return {
            "status": "blocked",
            "first_blocker": blockers[0],
            "blockers": blockers,
            "exchange_write_called": False,
        }

    scope_key = str(outcome["scope_key"])
    resolved = materialize_runtime_process_outcome(
        conn,
        process_name=str(outcome["process_name"]),
        scope_key=scope_key,
        run_id=f"certification:{certification_ref}:{now_ms}",
        result_status="action_time_blocker_resolution_certified",
        blockers=[],
        started_at_ms=now_ms,
        completed_at_ms=now_ms,
        runtime_head=runtime_head,
        source_watermark=f"certification:{certification_ref}",
        projector_owner="action_time_blocker_resolution_certifier",
        lane_identity=lane_identity,
        action_time_invocation_id=(
            str(outcome.get("action_time_invocation_id") or "").strip() or None
        ),
    )
    return {
        "status": "blocker_resolution_certified",
        "process_outcome": resolved,
        "first_blocker": None,
        "blockers": [],
        "exchange_write_called": False,
    }
