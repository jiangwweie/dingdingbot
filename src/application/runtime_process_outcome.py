"""Typed PG process outcome semantics independent from trading opportunity."""

from __future__ import annotations

from typing import Literal
from hashlib import sha256

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa


class RuntimeProcessOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_name: str
    process_state: Literal[
        "succeeded",
        "noop",
        "business_blocked",
        "retryable_failure",
        "hard_failure",
    ]
    business_state: Literal[
        "running",
        "waiting_for_opportunity",
        "processing",
        "temporarily_unavailable",
        "needs_intervention",
        "paused",
        "completed",
    ]
    first_blocker: str = ""


NOOP_STATUSES = {
    "no_fresh_signal",
    "no_operation_layer_handoff_ready",
    "no_unknown_commands",
    "healthy_waiting_quiet",
    "action_time_lane_already_open",
}
PROCESS_FAILURE_PREFIXES = (
    "runtime_control_state_invalid",
    "database_",
    "pg_",
    "watcher_or_service_failure",
    "exchange_command_lookup_failed",
)
HARD_FAILURE_PREFIXES = (
    "identity_mismatch",
    "cross_scope",
    "forbidden_effect",
    "exchange_command_hard_stopped",
)


def classify_process_outcome(
    *,
    process_name: str,
    result_status: str,
    blockers: list[str],
) -> RuntimeProcessOutcome:
    normalized = [str(item) for item in blockers if str(item)]
    first = normalized[0] if normalized else ""
    if result_status in NOOP_STATUSES and not normalized:
        return RuntimeProcessOutcome(
            process_name=process_name,
            process_state="noop",
            business_state="waiting_for_opportunity",
        )
    if any(first.startswith(prefix) for prefix in HARD_FAILURE_PREFIXES):
        return RuntimeProcessOutcome(
            process_name=process_name,
            process_state="hard_failure",
            business_state="needs_intervention",
            first_blocker=first,
        )
    if any(first.startswith(prefix) for prefix in PROCESS_FAILURE_PREFIXES):
        return RuntimeProcessOutcome(
            process_name=process_name,
            process_state="retryable_failure",
            business_state="temporarily_unavailable",
            first_blocker=first,
        )
    if normalized or result_status in {"blocked", "promotion_candidates_blocked"}:
        return RuntimeProcessOutcome(
            process_name=process_name,
            process_state="business_blocked",
            business_state="needs_intervention",
            first_blocker=first or result_status,
        )
    business_state = (
        "completed"
        if result_status.endswith(("completed", "submitted", "created"))
        else "processing"
    )
    return RuntimeProcessOutcome(
        process_name=process_name,
        process_state="succeeded",
        business_state=business_state,
    )


def materialize_runtime_process_outcome(
    conn: sa.engine.Connection,
    *,
    process_name: str,
    scope_key: str,
    run_id: str,
    result_status: str,
    blockers: list[str],
    started_at_ms: int,
    completed_at_ms: int,
    runtime_head: str,
    source_watermark: str,
    projector_owner: str = "runtime_process_outcome_projector",
) -> dict[str, object]:
    outcome = classify_process_outcome(
        process_name=process_name,
        result_status=result_status,
        blockers=blockers,
    )
    identity = f"{process_name}|{scope_key}"
    row: dict[str, object] = {
        "process_outcome_id": (
            "process_outcome:"
            + sha256(identity.encode("utf-8")).hexdigest()[:32]
        ),
        "process_name": process_name,
        "scope_key": scope_key,
        "run_id": run_id,
        "process_state": outcome.process_state,
        "business_state": outcome.business_state,
        "first_blocker": outcome.first_blocker or None,
        "started_at_ms": started_at_ms,
        "completed_at_ms": completed_at_ms,
        "runtime_head": runtime_head,
        "source_watermark": source_watermark,
        "projector_owner": projector_owner,
        "updated_at_ms": completed_at_ms,
    }
    table = sa.Table(
        "brc_runtime_process_outcomes",
        sa.MetaData(),
        autoload_with=conn,
    )
    existing = conn.execute(
        sa.select(table.c.process_outcome_id).where(
            table.c.process_outcome_id == row["process_outcome_id"]
        )
    ).first()
    if existing:
        conn.execute(
            table.update()
            .where(table.c.process_outcome_id == row["process_outcome_id"])
            .values(**row)
        )
    else:
        conn.execute(table.insert().values(**row))
    return row
