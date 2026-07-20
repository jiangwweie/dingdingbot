"""PG-backed conservation and deterministic arbitration of fresh signals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import sqlalchemy as sa

from src.application.action_time.action_time_invocation import (
    close_action_time_invocation_without_ticket,
    start_action_time_invocation,
)
from src.application.action_time.signal_arbitration import (
    ArbitrationDisposition,
    FreshSignalArbitrationCandidate,
    SignalArbitrationDecision,
    arbitrate_fresh_signals,
)
from src.application.runtime_process_outcome import (
    materialize_runtime_process_outcome,
)


@dataclass(frozen=True)
class PersistedSignalArbitrationDecision:
    decision: SignalArbitrationDecision
    action_time_invocation_id: str


def conserve_and_arbitrate_fresh_signals(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
    global_blocker: str | None = None,
    candidate_blockers: Mapping[str, str] | None = None,
    runtime_head: str = "unknown",
) -> tuple[PersistedSignalArbitrationDecision, ...]:
    """Create one Invocation per fresh Signal and persist every decision.

    This function is the only fresh-signal selection boundary. It deliberately
    does not form a Claim or Ticket; the selected Invocation is passed to the
    typed Action-Time coordinator, while all other invocations are terminal
    with their exact rank/reason/winner preserved in PostgreSQL.
    """

    rows = _fresh_signal_rows(conn, now_ms=int(now_ms))
    if not rows:
        return ()
    candidates = tuple(_candidate_from_row(row) for row in rows)
    normalized_blockers = {
        str(key): str(value)
        for key, value in dict(candidate_blockers or {}).items()
        if str(key) and str(value)
    }
    decisions = arbitrate_fresh_signals(
        candidates,
        now_ms=int(now_ms),
        global_blocker=global_blocker,
        candidate_blocker=lambda candidate: normalized_blockers.get(
            candidate.signal_event_id
        ),
    )
    rows_by_signal = {str(row["signal_event_id"]): row for row in rows}
    invocations = {
        signal_event_id: start_action_time_invocation(
            conn,
            signal_event_id=signal_event_id,
            opened_at_ms=int(now_ms),
        )
        for signal_event_id in rows_by_signal
    }
    persisted: list[PersistedSignalArbitrationDecision] = []
    for decision in decisions:
        invocation = invocations[decision.signal_event_id]
        if decision.disposition is not ArbitrationDisposition.SELECTED:
            terminal_kind = _terminal_kind(decision.disposition)
            close_action_time_invocation_without_ticket(
                conn,
                action_time_invocation_id=invocation.action_time_invocation_id,
                terminal_kind=terminal_kind,
                terminal_reason_code=decision.reason_code,
                stage_at_ms=int(now_ms),
                arbitration_rank=decision.rank,
                winner_signal_event_id=decision.winner_signal_event_id,
            )
        _persist_process_outcome(
            conn,
            invocation=invocation,
            decision=decision,
            now_ms=int(now_ms),
            runtime_head=str(rows_by_signal[decision.signal_event_id].get("producer_runtime_head") or runtime_head),
        )
        persisted.append(
            PersistedSignalArbitrationDecision(
                decision=decision,
                action_time_invocation_id=invocation.action_time_invocation_id,
            )
        )
    return tuple(persisted)


def _fresh_signal_rows(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> tuple[dict[str, Any], ...]:
    signals = sa.Table("brc_live_signal_events", sa.MetaData(), autoload_with=conn)
    scopes = sa.Table(
        "brc_strategy_group_candidate_scope", sa.MetaData(), autoload_with=conn
    )
    statement = (
        sa.select(
            signals,
            sa.func.coalesce(scopes.c.priority_rank, 2_147_483_647).label(
                "candidate_scope_priority"
            ),
        )
        .select_from(
            signals.outerjoin(
                scopes,
                scopes.c.candidate_scope_id == signals.c.candidate_scope_id,
            )
        )
        .where(
            signals.c.source_kind == "live_market",
            signals.c.status == "facts_validated",
            signals.c.freshness_state == "fresh",
            signals.c.expires_at_ms > now_ms,
            signals.c.invalidated_at_ms.is_(None),
        )
        .order_by(
            sa.func.coalesce(scopes.c.priority_rank, 2_147_483_647).asc(),
            signals.c.event_time_ms.asc(),
            signals.c.observed_at_ms.asc(),
            signals.c.signal_event_id.asc(),
        )
        .limit(64)
    )
    return tuple(dict(row) for row in conn.execute(statement).mappings())


def _candidate_from_row(row: Mapping[str, Any]) -> FreshSignalArbitrationCandidate:
    return FreshSignalArbitrationCandidate(
        signal_event_id=str(row["signal_event_id"]),
        # Candidate-scope priority is the current owner-authorized ordering
        # field. Owner policy has no independent priority column, so inventing
        # one here would create a second policy authority.
        owner_policy_priority=0,
        candidate_scope_priority=int(row["candidate_scope_priority"]),
        event_time_ms=int(row["event_time_ms"]),
        observed_at_ms=int(row["observed_at_ms"]),
        expires_at_ms=int(row["expires_at_ms"]),
    )


def _terminal_kind(disposition: ArbitrationDisposition) -> str:
    mapping = {
        ArbitrationDisposition.NOT_SELECTED_THIS_ROUND: "not_selected",
        ArbitrationDisposition.EXPIRED: "expired",
        ArbitrationDisposition.CANDIDATE_BLOCKED: "rejected",
        ArbitrationDisposition.GLOBAL_BLOCKED: "cancelled",
    }
    return mapping[disposition]


def _persist_process_outcome(
    conn: sa.engine.Connection,
    *,
    invocation: Any,
    decision: SignalArbitrationDecision,
    now_ms: int,
    runtime_head: str,
) -> None:
    blockers = [decision.reason_code] if decision.reason_code else []
    result_status = "action_time_signal_selected"
    if decision.disposition is ArbitrationDisposition.NOT_SELECTED_THIS_ROUND:
        result_status = "action_time_signal_not_selected"
    elif decision.disposition is ArbitrationDisposition.EXPIRED:
        result_status = "action_time_signal_expired"
    elif decision.disposition is ArbitrationDisposition.CANDIDATE_BLOCKED:
        result_status = "action_time_signal_candidate_blocked"
    elif decision.disposition is ArbitrationDisposition.GLOBAL_BLOCKED:
        result_status = "action_time_signal_global_blocked"
    materialize_runtime_process_outcome(
        conn,
        process_name="action_time_signal_arbitration",
        scope_key=None,
        run_id=(
            "action_time_signal_arbitration:"
            + sha256(
                f"{invocation.source_watermark}|{now_ms}".encode("utf-8")
            ).hexdigest()[:24]
        ),
        result_status=result_status,
        blockers=blockers,
        started_at_ms=now_ms,
        completed_at_ms=now_ms,
        runtime_head=runtime_head,
        source_watermark=invocation.source_watermark,
        lane_identity=invocation.lane_identity,
        action_time_invocation_id=invocation.action_time_invocation_id,
    )
