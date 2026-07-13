"""PG-backed causal context for one exact Action-Time signal attempt."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import sqlalchemy as sa

from src.application.action_time.identity_conservation import (
    RuntimeLaneIdentityConservationError,
    runtime_lane_identity_from_live_signal,
    runtime_lane_lineage_from_record,
)
from src.domain.action_time_invocation import (
    ActionTimeInvocation,
    ActionTimeInvocationBlocked,
    ActionTimeInvocationEvidence,
)
from src.domain.runtime_lane_identity import RuntimeLaneIdentity


INVOCATION_TABLE = "brc_action_time_invocations"
FACT_TABLE = "brc_runtime_fact_snapshots"
SIGNAL_TABLE = "brc_live_signal_events"


def start_action_time_invocation(
    conn: sa.engine.Connection,
    *,
    signal_event_id: str,
    opened_at_ms: int,
) -> ActionTimeInvocation:
    """Idempotently bind one current typed signal to one Action-Time attempt."""

    normalized_signal_id = str(signal_event_id or "").strip()
    if not normalized_signal_id:
        raise ActionTimeInvocationBlocked("action_time_invocation_signal_id_missing")
    normalized_opened_at_ms = int(opened_at_ms)
    invocation_table = _table(conn, INVOCATION_TABLE)
    signal_table = _table(conn, SIGNAL_TABLE)
    signal = conn.execute(
        sa.select(signal_table).where(
            signal_table.c.signal_event_id == normalized_signal_id
        )
    ).mappings().first()
    if signal is None:
        raise ActionTimeInvocationBlocked("action_time_invocation_signal_missing")
    signal_row = dict(signal)
    _require_current_live_signal(signal_row, stage_at_ms=normalized_opened_at_ms)
    identity, source_watermark = _identity_and_source_watermark(signal_row)
    invocation_id = _invocation_id(
        signal_event_id=normalized_signal_id,
        lane_identity=identity,
        source_watermark=source_watermark,
    )
    existing = _load_row(
        conn,
        invocation_table=invocation_table,
        action_time_invocation_id=invocation_id,
    )
    if existing is not None:
        return _invocation_from_row(existing)

    row = {
        "action_time_invocation_id": invocation_id,
        "signal_event_id": normalized_signal_id,
        **identity.model_dump(mode="json"),
        "lane_identity_key": identity.identity_key,
        "source_watermark": source_watermark,
        "opened_at_ms": normalized_opened_at_ms,
        "expires_at_ms": int(signal_row["expires_at_ms"]),
        "account_safe_fact_snapshot_id": None,
        "account_mode_fact_snapshot_id": None,
        "action_time_fact_snapshot_id": None,
        "ticket_id": None,
        "closed_at_ms": None,
        "created_at_ms": normalized_opened_at_ms,
        "updated_at_ms": normalized_opened_at_ms,
    }
    try:
        with conn.begin_nested():
            conn.execute(invocation_table.insert().values(**row))
    except sa.exc.IntegrityError as exc:
        existing = _load_row(
            conn,
            invocation_table=invocation_table,
            action_time_invocation_id=invocation_id,
        )
        if existing is None:
            raise ActionTimeInvocationBlocked(
                "action_time_invocation_persist_failed"
            ) from exc
        return _invocation_from_row(existing)
    return _invocation_from_row(row)


def load_action_time_invocation(
    conn: sa.engine.Connection,
    *,
    action_time_invocation_id: str,
) -> ActionTimeInvocation:
    """Load the sole causal context used by later Action-Time stages."""

    invocation_table = _table(conn, INVOCATION_TABLE)
    row = _load_row(
        conn,
        invocation_table=invocation_table,
        action_time_invocation_id=action_time_invocation_id,
    )
    if row is None:
        raise ActionTimeInvocationBlocked("action_time_invocation_missing")
    return _invocation_from_row(row)


def bind_action_time_invocation_fact_refs(
    conn: sa.engine.Connection,
    *,
    action_time_invocation_id: str,
    stage_at_ms: int,
    account_safe_fact_snapshot_id: str | None = None,
    account_mode_fact_snapshot_id: str | None = None,
    action_time_fact_snapshot_id: str | None = None,
) -> ActionTimeInvocation:
    """Attach exact fresh fact rows without rewriting their observation time."""

    invocation = load_action_time_invocation(
        conn,
        action_time_invocation_id=action_time_invocation_id,
    )
    normalized_stage_at_ms = int(stage_at_ms)
    _require_stage_within_invocation(
        invocation,
        stage_at_ms=normalized_stage_at_ms,
    )
    fact_table = _table(conn, FACT_TABLE)
    requested = {
        "account_safe_fact_snapshot_id": (
            account_safe_fact_snapshot_id,
            "account_safe",
        ),
        "account_mode_fact_snapshot_id": (
            account_mode_fact_snapshot_id,
            "account_mode",
        ),
        "action_time_fact_snapshot_id": (
            action_time_fact_snapshot_id,
            "action_time",
        ),
    }
    updates: dict[str, str] = {}
    for field, (fact_snapshot_id, expected_surface) in requested.items():
        if fact_snapshot_id is None:
            continue
        normalized_fact_id = str(fact_snapshot_id).strip()
        if not normalized_fact_id:
            raise ActionTimeInvocationBlocked(
                f"action_time_invocation_{expected_surface}_fact_id_missing"
            )
        _require_bindable_fact(
            conn,
            fact_table=fact_table,
            invocation=invocation,
            fact_snapshot_id=normalized_fact_id,
            expected_surface=expected_surface,
            stage_at_ms=normalized_stage_at_ms,
        )
        updates[field] = normalized_fact_id

    if not updates:
        return invocation
    invocation_table = _table(conn, INVOCATION_TABLE)
    conn.execute(
        invocation_table.update()
        .where(
            invocation_table.c.action_time_invocation_id
            == invocation.action_time_invocation_id
        )
        .values(**updates, updated_at_ms=normalized_stage_at_ms)
    )
    return load_action_time_invocation(
        conn,
        action_time_invocation_id=invocation.action_time_invocation_id,
    )


def load_action_time_invocation_signal(
    conn: sa.engine.Connection,
    *,
    action_time_invocation_id: str,
    stage_at_ms: int,
) -> tuple[ActionTimeInvocation, dict[str, Any]]:
    """Resolve only the signal originally selected for this invocation."""

    invocation = load_action_time_invocation(
        conn,
        action_time_invocation_id=action_time_invocation_id,
    )
    normalized_stage_at_ms = int(stage_at_ms)
    _require_stage_within_invocation(
        invocation,
        stage_at_ms=normalized_stage_at_ms,
    )
    signal_table = _table(conn, SIGNAL_TABLE)
    row = conn.execute(
        sa.select(signal_table).where(
            signal_table.c.signal_event_id == invocation.signal_event_id
        )
    ).mappings().first()
    if row is None:
        raise ActionTimeInvocationBlocked("action_time_invocation_signal_missing")
    signal = dict(row)
    _require_current_live_signal(signal, stage_at_ms=normalized_stage_at_ms)
    identity, source_watermark = _identity_and_source_watermark(signal)
    if identity.identity_key != invocation.lane_identity.identity_key:
        raise ActionTimeInvocationBlocked(
            "runtime_lane_identity_mismatch:invocation_signal_identity"
        )
    if source_watermark != invocation.source_watermark:
        raise ActionTimeInvocationBlocked(
            "runtime_lane_identity_mismatch:invocation_signal_source_watermark"
        )
    return invocation, signal


def load_action_time_invocation_evidence(
    conn: sa.engine.Connection,
    *,
    action_time_invocation_id: str,
    stage_at_ms: int,
) -> ActionTimeInvocationEvidence:
    """Load exact fresh references without consulting generic readiness rows."""

    invocation, signal = load_action_time_invocation_signal(
        conn,
        action_time_invocation_id=action_time_invocation_id,
        stage_at_ms=stage_at_ms,
    )
    normalized_stage_at_ms = int(stage_at_ms)
    public_fact_snapshot_id = _required_text(
        signal.get("fact_snapshot_id"),
        blocker="action_time_invocation_public_fact_id_missing",
    )
    account_safe_fact_snapshot_id = _required_text(
        invocation.account_safe_fact_snapshot_id,
        blocker="action_time_invocation_account_safe_fact_missing",
    )
    account_mode_fact_snapshot_id = _required_text(
        invocation.account_mode_fact_snapshot_id,
        blocker="action_time_invocation_account_mode_fact_missing",
    )
    action_time_fact_snapshot_id = _required_text(
        invocation.action_time_fact_snapshot_id,
        blocker="action_time_invocation_action_time_fact_missing",
    )
    fact_table = _table(conn, FACT_TABLE)
    _require_evidence_fact(
        conn,
        fact_table=fact_table,
        invocation=invocation,
        fact_snapshot_id=public_fact_snapshot_id,
        expected_surface="pretrade_public",
        stage_at_ms=normalized_stage_at_ms,
        require_after_opening=False,
        require_invocation_binding=False,
    )
    for fact_snapshot_id, expected_surface in (
        (account_safe_fact_snapshot_id, "account_safe"),
        (account_mode_fact_snapshot_id, "account_mode"),
        (action_time_fact_snapshot_id, "action_time"),
    ):
        _require_evidence_fact(
            conn,
            fact_table=fact_table,
            invocation=invocation,
            fact_snapshot_id=fact_snapshot_id,
            expected_surface=expected_surface,
            stage_at_ms=normalized_stage_at_ms,
            require_after_opening=True,
            require_invocation_binding=True,
        )
    try:
        return ActionTimeInvocationEvidence(
            invocation=invocation,
            stage_at_ms=normalized_stage_at_ms,
            public_fact_snapshot_id=public_fact_snapshot_id,
            account_safe_fact_snapshot_id=account_safe_fact_snapshot_id,
            account_mode_fact_snapshot_id=account_mode_fact_snapshot_id,
            action_time_fact_snapshot_id=action_time_fact_snapshot_id,
        )
    except ValueError as exc:
        raise ActionTimeInvocationBlocked(str(exc)) from exc


def bind_action_time_invocation_ticket(
    conn: sa.engine.Connection,
    *,
    action_time_invocation_id: str,
    ticket_id: str,
    stage_at_ms: int,
) -> ActionTimeInvocation:
    """Close causal context at the one Ticket it was allowed to create."""

    invocation = load_action_time_invocation(
        conn,
        action_time_invocation_id=action_time_invocation_id,
    )
    normalized_stage_at_ms = int(stage_at_ms)
    _require_stage_within_invocation(
        invocation,
        stage_at_ms=normalized_stage_at_ms,
    )
    normalized_ticket_id = _required_text(
        ticket_id,
        blocker="action_time_invocation_ticket_id_missing",
    )
    if (
        invocation.ticket_id is not None
        and invocation.ticket_id != normalized_ticket_id
    ):
        raise ActionTimeInvocationBlocked(
            "action_time_invocation_ticket_already_bound"
        )
    ticket_table = _table(conn, "brc_action_time_tickets")
    ticket = conn.execute(
        sa.select(ticket_table).where(ticket_table.c.ticket_id == normalized_ticket_id)
    ).mappings().first()
    if ticket is None:
        raise ActionTimeInvocationBlocked("action_time_invocation_ticket_missing")
    ticket_row = dict(ticket)
    if str(ticket_row.get("signal_event_id") or "") != invocation.signal_event_id:
        raise ActionTimeInvocationBlocked(
            "action_time_invocation_ticket_signal_mismatch"
        )
    ticket_invocation_id = _optional_text(
        ticket_row.get("action_time_invocation_id")
    )
    if (
        ticket_invocation_id is not None
        and ticket_invocation_id != invocation.action_time_invocation_id
    ):
        raise ActionTimeInvocationBlocked(
            "action_time_invocation_ticket_context_mismatch"
        )
    if "action_time_invocation_id" in ticket_table.c:
        conn.execute(
            ticket_table.update()
            .where(ticket_table.c.ticket_id == normalized_ticket_id)
            .values(action_time_invocation_id=invocation.action_time_invocation_id)
        )
    invocation_table = _table(conn, INVOCATION_TABLE)
    conn.execute(
        invocation_table.update()
        .where(
            invocation_table.c.action_time_invocation_id
            == invocation.action_time_invocation_id
        )
        .values(
            ticket_id=normalized_ticket_id,
            closed_at_ms=normalized_stage_at_ms,
            updated_at_ms=normalized_stage_at_ms,
        )
    )
    return load_action_time_invocation(
        conn,
        action_time_invocation_id=invocation.action_time_invocation_id,
    )


def _require_current_live_signal(
    signal: dict[str, Any],
    *,
    stage_at_ms: int,
) -> None:
    if (
        str(signal.get("source_kind") or "") != "live_market"
        or str(signal.get("status") or "") != "facts_validated"
        or str(signal.get("freshness_state") or "") != "fresh"
        or signal.get("invalidated_at_ms") is not None
        or int(signal.get("expires_at_ms") or 0) <= stage_at_ms
    ):
        raise ActionTimeInvocationBlocked("action_time_invocation_signal_not_current")
    if any(
        int(signal.get(field) or 0) > stage_at_ms
        for field in ("event_time_ms", "observed_at_ms", "created_at_ms")
    ):
        raise ActionTimeInvocationBlocked("action_time_invocation_signal_after_stage")


def _identity_and_source_watermark(
    signal: dict[str, Any],
) -> tuple[RuntimeLaneIdentity, str]:
    try:
        identity = runtime_lane_identity_from_live_signal(signal)
        lineage = runtime_lane_lineage_from_record(signal)
    except RuntimeLaneIdentityConservationError as exc:
        raise ActionTimeInvocationBlocked(exc.blocker) from exc
    if lineage.signal_event_id != str(signal.get("signal_event_id") or ""):
        raise ActionTimeInvocationBlocked(
            "runtime_lane_identity_mismatch:invocation_signal_lineage"
        )
    return identity, lineage.source_watermark


def _invocation_id(
    *,
    signal_event_id: str,
    lane_identity: RuntimeLaneIdentity,
    source_watermark: str,
) -> str:
    material = f"{signal_event_id}|{lane_identity.identity_key}|{source_watermark}"
    return "action_time_invocation:" + sha256(material.encode("utf-8")).hexdigest()[:32]


def _load_row(
    conn: sa.engine.Connection,
    *,
    invocation_table: sa.Table,
    action_time_invocation_id: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        sa.select(invocation_table).where(
            invocation_table.c.action_time_invocation_id
            == str(action_time_invocation_id)
        )
    ).mappings().first()
    return dict(row) if row is not None else None


def _invocation_from_row(row: dict[str, Any]) -> ActionTimeInvocation:
    try:
        identity = RuntimeLaneIdentity.model_validate(
            {field: row.get(field) for field in RuntimeLaneIdentity.model_fields}
        )
        if str(row.get("lane_identity_key") or "") != identity.identity_key:
            raise ActionTimeInvocationBlocked(
                "runtime_lane_identity_mismatch:action_time_invocation_identity_key"
            )
        return ActionTimeInvocation(
            action_time_invocation_id=str(row.get("action_time_invocation_id") or ""),
            signal_event_id=str(row.get("signal_event_id") or ""),
            lane_identity=identity,
            source_watermark=str(row.get("source_watermark") or ""),
            opened_at_ms=int(row.get("opened_at_ms") or 0),
            expires_at_ms=int(row.get("expires_at_ms") or 0),
            account_safe_fact_snapshot_id=_optional_text(
                row.get("account_safe_fact_snapshot_id")
            ),
            account_mode_fact_snapshot_id=_optional_text(
                row.get("account_mode_fact_snapshot_id")
            ),
            action_time_fact_snapshot_id=_optional_text(
                row.get("action_time_fact_snapshot_id")
            ),
            ticket_id=_optional_text(row.get("ticket_id")),
            closed_at_ms=(
                int(row["closed_at_ms"])
                if row.get("closed_at_ms") is not None
                else None
            ),
        )
    except ActionTimeInvocationBlocked:
        raise
    except (TypeError, ValueError) as exc:
        raise ActionTimeInvocationBlocked(
            "runtime_lane_identity_mismatch:action_time_invocation_row"
        ) from exc


def _require_stage_within_invocation(
    invocation: ActionTimeInvocation,
    *,
    stage_at_ms: int,
) -> None:
    if stage_at_ms < invocation.opened_at_ms:
        raise ActionTimeInvocationBlocked("action_time_invocation_stage_before_opening")
    if stage_at_ms >= invocation.expires_at_ms:
        raise ActionTimeInvocationBlocked("action_time_invocation_stage_expired")


def _require_evidence_fact(
    conn: sa.engine.Connection,
    *,
    fact_table: sa.Table,
    invocation: ActionTimeInvocation,
    fact_snapshot_id: str,
    expected_surface: str,
    stage_at_ms: int,
    require_after_opening: bool,
    require_invocation_binding: bool,
) -> dict[str, Any]:
    row = conn.execute(
        sa.select(fact_table).where(fact_table.c.fact_snapshot_id == fact_snapshot_id)
    ).mappings().first()
    if row is None:
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_missing"
        )
    fact = dict(row)
    if str(fact.get("fact_surface") or "") != expected_surface:
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_surface_mismatch"
        )
    if (
        not _truthy(fact.get("satisfied"))
        or str(fact.get("freshness_state") or "") != "fresh"
    ):
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_not_fresh"
        )
    observed_at_ms = int(fact.get("observed_at_ms") or 0)
    valid_until_ms = int(fact.get("valid_until_ms") or 0)
    if observed_at_ms > stage_at_ms:
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_after_stage"
        )
    if valid_until_ms <= stage_at_ms:
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_expired"
        )
    if require_after_opening and observed_at_ms < invocation.opened_at_ms:
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_before_opening"
        )
    if require_invocation_binding:
        if "action_time_invocation_id" not in fact_table.c:
            raise ActionTimeInvocationBlocked(
                "action_time_invocation_fact_binding_storage_missing"
            )
        if (
            _optional_text(fact.get("action_time_invocation_id"))
            != invocation.action_time_invocation_id
        ):
            raise ActionTimeInvocationBlocked(
                f"action_time_invocation_{expected_surface}_fact_not_bound"
            )
    return fact


def _require_bindable_fact(
    conn: sa.engine.Connection,
    *,
    fact_table: sa.Table,
    invocation: ActionTimeInvocation,
    fact_snapshot_id: str,
    expected_surface: str,
    stage_at_ms: int,
) -> None:
    row = conn.execute(
        sa.select(fact_table).where(fact_table.c.fact_snapshot_id == fact_snapshot_id)
    ).mappings().first()
    if row is None:
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_missing"
        )
    fact = dict(row)
    if str(fact.get("fact_surface") or "") != expected_surface:
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_surface_mismatch"
        )
    if (
        not _truthy(fact.get("satisfied"))
        or str(fact.get("freshness_state") or "") != "fresh"
    ):
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_not_fresh"
        )
    observed_at_ms = int(fact.get("observed_at_ms") or 0)
    valid_until_ms = int(fact.get("valid_until_ms") or 0)
    if observed_at_ms < invocation.opened_at_ms:
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_before_opening"
        )
    if observed_at_ms > stage_at_ms:
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_after_stage"
        )
    if valid_until_ms <= stage_at_ms:
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_expired"
        )
    current_invocation_id = _optional_text(fact.get("action_time_invocation_id"))
    if (
        current_invocation_id is not None
        and current_invocation_id != invocation.action_time_invocation_id
    ):
        raise ActionTimeInvocationBlocked(
            f"action_time_invocation_{expected_surface}_fact_already_bound"
        )
    conn.execute(
        fact_table.update()
        .where(fact_table.c.fact_snapshot_id == fact_snapshot_id)
        .values(action_time_invocation_id=invocation.action_time_invocation_id)
    )


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _required_text(value: object, *, blocker: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ActionTimeInvocationBlocked(blocker)
    return normalized


def _truthy(value: object) -> bool:
    return value is True or value == 1


def _table(conn: sa.engine.Connection, name: str) -> sa.Table:
    if not sa.inspect(conn).has_table(name):
        raise ActionTimeInvocationBlocked(f"action_time_invocation_table_missing:{name}")
    return sa.Table(name, sa.MetaData(), autoload_with=conn)
