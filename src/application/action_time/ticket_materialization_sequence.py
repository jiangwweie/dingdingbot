"""Atomic PG Action-Time fact-to-Ticket materialization sequence."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
import os
import time
from typing import Any

import sqlalchemy as sa

from src.application.action_time.action_time_ticket import (
    materialize_action_time_ticket as _materialize_ticket,
)
from src.application.action_time.action_time_invocation import (
    ActionTimeInvocationBlocked,
    bind_action_time_invocation_ticket,
    load_action_time_invocation,
    load_action_time_invocation_evidence,
)
from src.application.action_time.fact_snapshots import (
    materialize_action_time_fact_snapshots as _materialize_facts,
    materialize_action_time_invocation_fact_snapshots as _materialize_invocation_facts,
)
from src.application.action_time.promotion_action_time_lane import (
    materialize_pg_promotion_action_time_lane as _materialize_promotion,
    materialize_action_time_invocation_promotion_action_time_lane as _materialize_invocation_promotion,
)
from src.application.runtime_process_outcome import (
    materialize_runtime_process_outcome,
)


ProjectionPublisher = Callable[[sa.engine.Connection], dict[str, Any]]
FactMaterializer = Callable[..., dict[str, Any]]
PromotionMaterializer = Callable[..., dict[str, Any]]
TicketMaterializer = Callable[..., dict[str, Any]]
ClockMs = Callable[[], int]


SCHEMA = "brc.action_time_ticket_materialization_sequence.v1"
PROCESS_NAME = "action_time_ticket_sequence"
AUTHORITY_BOUNDARY = (
    "pg_atomic_action_time_fact_reservation_lane_ticket_only; "
    "no_finalgate_no_operation_layer_no_exchange_write"
)
FORBIDDEN_EFFECTS = {
    "finalgate_called": False,
    "operation_layer_called": False,
    "exchange_write_called": False,
    "order_created": False,
    "order_lifecycle_called": False,
    "withdrawal_or_transfer_created": False,
    "live_profile_changed": False,
    "order_sizing_changed": False,
}


def materialize_action_time_ticket_sequence(
    conn: sa.engine.Connection,
    *,
    now_ms: int | None = None,
    projection_publisher: ProjectionPublisher | None = None,
    fact_materializer: FactMaterializer = _materialize_facts,
    promotion_materializer: PromotionMaterializer = _materialize_promotion,
    ticket_materializer: TicketMaterializer = _materialize_ticket,
    completion_clock_ms: ClockMs | None = None,
    action_time_invocation_id: str | None = None,
    stage_at_ms: int | None = None,
    invocation_fact_materializer: FactMaterializer = _materialize_invocation_facts,
    invocation_promotion_materializer: PromotionMaterializer = (
        _materialize_invocation_promotion
    ),
) -> dict[str, Any]:
    """Commit a complete fact-to-Ticket unit or no partial action rows.

    The caller owns the outer transaction. This function owns a nested
    savepoint so it can roll back action rows and still persist one exact
    sequence-level process outcome in the outer transaction.
    """

    invocation_mode = bool(str(action_time_invocation_id or "").strip())
    if not invocation_mode and projection_publisher is None:
        raise ValueError("projection_publisher is required outside invocation mode")
    started_at_ms = int(
        stage_at_ms
        if invocation_mode and stage_at_ms is not None
        else now_ms
        if now_ms is not None
        else time.time() * 1000
    )
    clock = completion_clock_ms or (lambda: int(time.time() * 1000))
    fact_payload: dict[str, Any] = {}
    projection_payload: dict[str, Any] = {}
    promotion_payload: dict[str, Any] = {}
    ticket_payload: dict[str, Any] = {}
    scope_key = "global"
    blockers: list[str] = []
    status = "action_time_ticket_sequence_rolled_back"
    invocation = None

    savepoint = conn.begin_nested()
    try:
        if invocation_mode:
            invocation = load_action_time_invocation(
                conn,
                action_time_invocation_id=str(action_time_invocation_id),
            )
            scope_key = (
                "lane:"
                f"{invocation.lane_identity.strategy_group_id}:"
                f"{invocation.lane_identity.symbol}:"
                f"{invocation.lane_identity.side}"
            )
            fact_payload = invocation_fact_materializer(
                conn,
                action_time_invocation_id=invocation.action_time_invocation_id,
                stage_at_ms=started_at_ms,
            )
        else:
            fact_payload = fact_materializer(conn, now_ms=started_at_ms)
        fact_status = str(fact_payload.get("status") or "")
        if not invocation_mode and fact_status == "no_current_fresh_live_signal":
            savepoint.commit()
            status = fact_status
        elif fact_status not in {
            "action_time_fact_snapshots_materialized",
            "action_time_invocation_fact_snapshot_materialized",
        }:
            blockers = _blockers_or_status(fact_payload)
            scope_key = _scope_key(fact=fact_payload)
            savepoint.rollback()
        else:
            if invocation_mode:
                assert invocation is not None
                evidence = load_action_time_invocation_evidence(
                    conn,
                    action_time_invocation_id=invocation.action_time_invocation_id,
                    stage_at_ms=started_at_ms,
                )
                promotion_payload = invocation_promotion_materializer(
                    conn,
                    evidence=evidence,
                )
            else:
                projection_payload = projection_publisher(conn)
                if projection_payload.get("status") not in {
                    "current_projections_published",
                    "action_time_pretrade_readiness_published",
                }:
                    blockers = _blockers_or_status(
                        projection_payload,
                        fallback="action_time_current_projection_publish_failed",
                    )
                    scope_key = _scope_key(fact=fact_payload)
                    savepoint.rollback()
                else:
                    promotion_payload = promotion_materializer(
                        conn,
                        now_ms=started_at_ms,
                    )
            promotion_status = str(promotion_payload.get("status") or "")
            scope_key = _scope_key(
                promotion=promotion_payload,
                fact=fact_payload,
            )
            if not savepoint.is_active:
                pass
            elif _promotion_is_already_processed_signal(
                promotion_status,
                promotion_payload,
            ):
                blockers = []
                status = "action_time_ticket_sequence_signal_already_processed"
                savepoint.rollback()
            elif promotion_status not in {
                "promotion_action_time_lane_created",
                "action_time_lane_already_open",
            }:
                blockers = _blockers_or_status(
                    promotion_payload,
                    fallback=(
                        "action_time_sequence_promotion_not_created:"
                        f"{promotion_status or 'missing'}"
                    ),
                )
                savepoint.rollback()
            else:
                ticket_payload = ticket_materializer(
                    conn,
                    now_ms=started_at_ms,
                )
                ticket_status = str(ticket_payload.get("status") or "")
                scope_key = _scope_key(
                    ticket=ticket_payload,
                    promotion=promotion_payload,
                    fact=fact_payload,
                )
                if ticket_status not in {
                    "action_time_ticket_created",
                    "action_time_ticket_already_exists",
                }:
                    blockers = _blockers_or_status(
                        ticket_payload,
                        fallback=(
                            "action_time_sequence_ticket_not_created:"
                            f"{ticket_status or 'missing'}"
                        ),
                    )
                    savepoint.rollback()
                else:
                    if invocation_mode:
                        assert invocation is not None
                        bind_action_time_invocation_ticket(
                            conn,
                            action_time_invocation_id=invocation.action_time_invocation_id,
                            ticket_id=str(ticket_payload.get("ticket_id") or ""),
                            stage_at_ms=started_at_ms,
                        )
                    completion_ms = int(clock())
                    expires_at_ms = _ticket_expires_at_ms(
                        conn,
                        ticket_id=str(ticket_payload.get("ticket_id") or ""),
                    )
                    if expires_at_ms <= completion_ms:
                        blockers = [
                            "action_time_sequence_ttl_expired_before_ticket_commit"
                        ]
                        savepoint.rollback()
                    else:
                        savepoint.commit()
                        status = "action_time_ticket_sequence_committed"
    except ActionTimeInvocationBlocked as exc:
        if savepoint.is_active:
            savepoint.rollback()
        blockers = [exc.blocker]
    except Exception as exc:
        if savepoint.is_active:
            savepoint.rollback()
        blockers = [f"action_time_sequence_exception:{type(exc).__name__}"]

    completed_at_ms = int(clock())
    result_status = (
        status
        if status in {
            "no_current_fresh_live_signal",
            "action_time_ticket_sequence_committed",
            "action_time_ticket_sequence_signal_already_processed",
        }
        else "action_time_ticket_sequence_blocked"
    )
    outcome_specs = _process_outcome_specs(
        status=status,
        result_status=result_status,
        scope_key=scope_key,
        blockers=blockers,
        fact=fact_payload,
        promotion=promotion_payload,
        ticket=ticket_payload,
    )
    process_outcomes = [
        materialize_runtime_process_outcome(
            conn,
            process_name=PROCESS_NAME,
            scope_key=spec["scope_key"],
            run_id=_run_id(
                spec["scope_key"],
                started_at_ms,
                spec["result_status"],
            ),
            result_status=spec["result_status"],
            blockers=spec["blockers"],
            started_at_ms=started_at_ms,
            completed_at_ms=completed_at_ms,
            runtime_head=os.getenv("BRC_RUNTIME_HEAD", "runtime-head-unknown"),
            source_watermark=(
                invocation.source_watermark
                if invocation is not None
                else spec["source_watermark"]
            ),
            lane_identity=(
                invocation.lane_identity if invocation is not None else None
            ),
            action_time_invocation_id=(
                invocation.action_time_invocation_id
                if invocation is not None
                else None
            ),
        )
        for spec in outcome_specs
    ]
    process_outcome = _primary_process_outcome(
        process_outcomes,
        primary_scope_key=scope_key,
    )
    return {
        "schema": SCHEMA,
        "status": status,
        "scope_key": scope_key,
        "blockers": blockers,
        "fact": fact_payload,
        "projection": projection_payload,
        "promotion": promotion_payload,
        "ticket": ticket_payload,
        "process_outcome": process_outcome,
        "process_outcomes": process_outcomes,
        "started_at_ms": started_at_ms,
        "completed_at_ms": completed_at_ms,
        "authority_boundary": AUTHORITY_BOUNDARY,
        "forbidden_effects": FORBIDDEN_EFFECTS,
    }


def _promotion_is_already_processed_signal(
    promotion_status: str,
    promotion_payload: dict[str, Any],
) -> bool:
    """Treat exact-signal progression reuse as idempotent terminal truth.

    A terminal lane/promotion identity blocker on its own remains a safety
    conflict.  It is a harmless repeat only when PG proves that this exact
    signal already owns a lane, Ticket, or protected-submit attempt.
    """

    if promotion_status != "terminal_action_time_identity_not_reopened":
        return False
    return any(
        str(blocker).startswith(
            (
                "signal_event_already_has_action_time_lane:",
                "signal_event_already_has_action_time_ticket:",
                "signal_event_already_has_protected_submit_attempt:",
            )
        )
        for blocker in promotion_payload.get("blockers") or []
    )


def _ticket_expires_at_ms(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
) -> int:
    if not ticket_id:
        return 0
    value = conn.execute(
        sa.text(
            """
            SELECT expires_at_ms
            FROM brc_action_time_tickets
            WHERE ticket_id = :ticket_id
            LIMIT 1
            """
        ),
        {"ticket_id": ticket_id},
    ).scalar_one_or_none()
    return int(value or 0)


def _scope_key(
    *,
    ticket: dict[str, Any] | None = None,
    promotion: dict[str, Any] | None = None,
    fact: dict[str, Any] | None = None,
) -> str:
    rows = [ticket or {}, promotion or {}]
    fact_payload = fact or {}
    rows.extend(
        row
        for key in ("materialized", "blocked")
        for row in fact_payload.get(key) or []
        if isinstance(row, dict)
    )
    for row in rows:
        strategy_group_id = str(row.get("strategy_group_id") or "")
        symbol = str(row.get("symbol") or "")
        side = str(row.get("side") or "")
        if strategy_group_id and symbol and side:
            return f"lane:{strategy_group_id}:{symbol}:{side}"
    return "global"


def _source_watermark(
    *,
    fact: dict[str, Any],
    promotion: dict[str, Any],
    ticket: dict[str, Any],
) -> str:
    for value in (
        ticket.get("ticket_id"),
        promotion.get("signal_event_id"),
        *(
            row.get("signal_event_id")
            for row in fact.get("materialized") or []
            if isinstance(row, dict)
        ),
        *(
            row.get("signal_event_id")
            for row in fact.get("blocked") or []
            if isinstance(row, dict)
        ),
    ):
        if value:
            return str(value)
    return "no_current_fresh_live_signal"


def _process_outcome_specs(
    *,
    status: str,
    result_status: str,
    scope_key: str,
    blockers: list[str],
    fact: dict[str, Any],
    promotion: dict[str, Any],
    ticket: dict[str, Any],
) -> list[dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}

    def add(
        row_scope_key: str,
        *,
        row_status: str,
        row_blockers: list[str],
        source_watermark: str,
        overwrite: bool = True,
    ) -> None:
        if not row_scope_key:
            return
        if not overwrite and row_scope_key in specs:
            return
        specs[row_scope_key] = {
            "scope_key": row_scope_key,
            "result_status": row_status,
            "blockers": _dedupe(row_blockers),
            "source_watermark": source_watermark,
        }

    for row in fact.get("blocked") or []:
        if not isinstance(row, dict):
            continue
        add(
            _lane_scope_key(row),
            row_status="action_time_ticket_sequence_blocked",
            row_blockers=list(row.get("blockers") or []),
            source_watermark=str(row.get("signal_event_id") or ""),
            overwrite=False,
        )

    promotion_status = str(promotion.get("status") or "")
    promotion_succeeded = promotion_status in {
        "promotion_action_time_lane_created",
        "action_time_lane_already_open",
    }
    for row in promotion.get("per_candidate_results") or []:
        if not isinstance(row, dict):
            continue
        candidate_blockers = [str(item) for item in row.get("blockers") or []]
        candidate_status = str(row.get("status") or "")
        if candidate_blockers:
            row_status = "action_time_ticket_sequence_blocked"
            row_blockers = candidate_blockers
        elif candidate_status == "arbitration_lost" and promotion_succeeded:
            row_status = "action_time_ticket_sequence_candidate_ready"
            row_blockers = []
        elif candidate_status == "arbitration_lost":
            row_status = "action_time_ticket_sequence_blocked"
            row_blockers = blockers
        else:
            continue
        add(
            _lane_scope_key(row),
            row_status=row_status,
            row_blockers=row_blockers,
            source_watermark=str(row.get("signal_event_id") or ""),
        )

    if status == "action_time_ticket_sequence_committed":
        add(
            scope_key,
            row_status=result_status,
            row_blockers=[],
            source_watermark=_source_watermark(
                fact=fact,
                promotion=promotion,
                ticket=ticket,
            ),
        )
    elif status == "no_current_fresh_live_signal":
        add(
            "global",
            row_status=result_status,
            row_blockers=[],
            source_watermark="no_current_fresh_live_signal",
        )
    elif ticket and _lane_scope_key(ticket):
        add(
            _lane_scope_key(ticket),
            row_status=result_status,
            row_blockers=blockers,
            source_watermark=_source_watermark(
                fact=fact,
                promotion=promotion,
                ticket=ticket,
            ),
        )
    elif not specs and fact.get("materialized"):
        for row in fact.get("materialized") or []:
            if not isinstance(row, dict):
                continue
            add(
                _lane_scope_key(row),
                row_status=result_status,
                row_blockers=blockers,
                source_watermark=str(row.get("signal_event_id") or ""),
            )
    if not specs:
        add(
            scope_key or "global",
            row_status=result_status,
            row_blockers=blockers,
            source_watermark=_source_watermark(
                fact=fact,
                promotion=promotion,
                ticket=ticket,
            ),
        )
    return [specs[key] for key in sorted(specs)]


def _lane_scope_key(row: dict[str, Any]) -> str:
    strategy_group_id = str(row.get("strategy_group_id") or "")
    symbol = str(row.get("symbol") or "")
    side = str(row.get("side") or "")
    if strategy_group_id and symbol and side:
        return f"lane:{strategy_group_id}:{symbol}:{side}"
    return ""


def _primary_process_outcome(
    process_outcomes: list[dict[str, Any]],
    *,
    primary_scope_key: str,
) -> dict[str, Any]:
    failures = [
        row
        for row in process_outcomes
        if row.get("process_state") in {"retryable_failure", "hard_failure"}
    ]
    if failures:
        return failures[0]
    for row in process_outcomes:
        if row.get("scope_key") == primary_scope_key:
            return row
    return process_outcomes[0]


def _blockers_or_status(
    payload: dict[str, Any],
    *,
    fallback: str = "action_time_ticket_sequence_blocked",
) -> list[str]:
    blockers = [
        str(item)
        for item in payload.get("blockers") or []
        if str(item)
    ]
    return list(dict.fromkeys(blockers or [fallback]))


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _run_id(scope_key: str, now_ms: int, status: str) -> str:
    digest = sha256(
        f"{scope_key}|{now_ms}|{status}".encode("utf-8")
    ).hexdigest()[:32]
    return f"action_time_ticket_sequence:{digest}"
