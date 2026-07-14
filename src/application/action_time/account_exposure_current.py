"""Project one account-wide exchange snapshot into per-instrument exposure truth."""

from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa

from src.application.action_time.account_exchange_ownership import (
    AccountExchangeTruthClassification,
    AccountOrderClassification,
    AccountPositionClassification,
)
from src.domain.account_risk import compute_directional_risk
from src.infrastructure.binance_usdm_account_risk_snapshot import (
    ExchangeOpenOrderRow,
    ExchangePositionRow,
    FullAccountRiskSnapshot,
)


_ZERO = Decimal("0")
_STOP_PURPOSES = {"initial_stop", "runner_stop"}


class AccountExposureCurrentRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_exposure_current_id: str
    account_id: str
    exchange_id: str
    exchange_instrument_id: str
    exchange_symbol: str
    position_mode: str
    position_bucket: str
    owner_ticket_id: str | None
    ownership_state: str
    position_slot_claimed: bool
    exposure_state: str
    position_qty: Decimal
    entry_price: Decimal | None
    confirmed_stop_price: Decimal | None
    working_entry_qty: Decimal
    planned_reserved_risk: Decimal
    actual_directional_risk: Decimal
    held_risk: Decimal
    protection_state: str
    stop_covered_qty: Decimal
    reconciliation_state: str
    first_blocker: str | None
    source_snapshot_id: str
    projection_version: int


class AccountExposureProjectionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rows: tuple[AccountExposureCurrentRow, ...]
    global_blockers: tuple[str, ...]
    semantic_event_count: int


def project_account_exposure_current(
    conn: sa.Connection,
    *,
    snapshot: FullAccountRiskSnapshot,
    classification: AccountExchangeTruthClassification,
    now_ms: int,
) -> AccountExposureProjectionResult:
    """Persist fresh per-instrument truth; network I/O belongs to the caller."""

    if now_ms <= 0:
        raise ValueError("now_ms must be positive")
    if not snapshot.snapshot_ready:
        blocker = snapshot.failure_code or "account_risk_snapshot_not_ready"
        return AccountExposureProjectionResult(
            rows=(), global_blockers=(blocker,), semantic_event_count=0
        )
    reservations = _active_reservations(conn, snapshot.account_id)
    rows = _position_rows(snapshot, classification, reservations)
    owned_ticket_ids = {row.owner_ticket_id for row in rows if row.owner_ticket_id}
    rows.extend(_reservation_only_rows(snapshot, reservations, owned_ticket_ids))
    rows.extend(_flat_rows_absent_from_snapshot(conn, snapshot, rows))
    event_count = _persist_rows(conn, rows, snapshot=snapshot, now_ms=now_ms)
    blockers = sorted(
        set(classification.blockers).union(
            row.first_blocker for row in rows if row.first_blocker
        )
    )
    return AccountExposureProjectionResult(
        rows=tuple(rows),
        global_blockers=tuple(blockers),
        semantic_event_count=event_count,
    )


def _position_rows(
    snapshot: FullAccountRiskSnapshot,
    classification: AccountExchangeTruthClassification,
    reservations: dict[str, dict[str, object]],
) -> list[AccountExposureCurrentRow]:
    classified_positions = {
        (item.exchange_symbol, item.exchange_instrument_id): item
        for item in classification.positions
    }
    rows: list[AccountExposureCurrentRow] = []
    for position in snapshot.positions:
        classified = _find_position_classification(position, classified_positions)
        if classified is None:
            classified = AccountPositionClassification(
                exchange_symbol=position.exchange_symbol,
                exchange_instrument_id=f"{snapshot.exchange_id}:{position.exchange_symbol}",
                ownership_state="external_unowned",
                blocker="account_exchange_position_unknown_global_fail_closed",
            )
        rows.append(
            _row_for_position(
                snapshot,
                position,
                classified,
                classification.orders,
                planned_reserved_risk=_reservation_risk(
                    reservations, classified.owner_ticket_id
                ),
            )
        )
    return rows


def _find_position_classification(
    position: ExchangePositionRow,
    rows: dict[tuple[str, str], AccountPositionClassification],
) -> AccountPositionClassification | None:
    matches = [
        row for (symbol, _instrument), row in rows.items() if symbol == position.exchange_symbol
    ]
    return matches[0] if len(matches) == 1 else None


def _row_for_position(
    snapshot: FullAccountRiskSnapshot,
    position: ExchangePositionRow,
    classified: AccountPositionClassification,
    classifications: tuple[AccountOrderClassification, ...],
    planned_reserved_risk: Decimal,
) -> AccountExposureCurrentRow:
    qty = abs(position.position_qty)
    side = "long" if position.position_qty > 0 else "short"
    stop_segments = _confirmed_stop_segments(
        snapshot,
        classifications=classifications,
        exchange_symbol=position.exchange_symbol,
        owner_ticket_id=classified.owner_ticket_id,
        position_side=position.position_side,
        trade_side=side,
        position_qty=qty,
    )
    stop_price = stop_segments[0][0] if stop_segments else None
    stop_covered_qty = sum((segment_qty for _, segment_qty in stop_segments), _ZERO)
    working_entry_qty, working_entry_price = _working_entry(
        snapshot,
        classifications=classifications,
        exchange_symbol=position.exchange_symbol,
        owner_ticket_id=classified.owner_ticket_id,
    )
    blocker = classified.blocker
    if classified.ownership_state not in {"owned_by_ticket", "owned_by_other_known_ticket"}:
        exposure_state = "unknown"
        protection_state = "unknown"
        reconciliation_state = "unknown"
        blocker = blocker or "account_exchange_position_unknown_global_fail_closed"
        directional_risk = _ZERO
        held_risk = planned_reserved_risk
    elif stop_price is None or stop_covered_qty < qty:
        exposure_state = "open_unprotected"
        protection_state = "missing"
        reconciliation_state = "mismatch"
        blocker = "account_exposure_protection_missing"
        directional_risk = _ZERO
        held_risk = planned_reserved_risk
    else:
        directional_risk = sum(
            (
                compute_directional_risk(
                    side=side,
                    actual_average_entry_price=position.entry_price,
                    confirmed_stop_price=segment_stop_price,
                    position_qty=segment_qty,
                )
                for segment_stop_price, segment_qty in stop_segments
            ),
            _ZERO,
        )
        remaining_entry_risk = _ZERO
        if working_entry_qty > 0:
            reference = working_entry_price or position.entry_price
            remaining_entry_risk = abs(reference - stop_price) * working_entry_qty
        exposure_state = "working_entry" if working_entry_qty > 0 else "open_protected"
        protection_state = "confirmed"
        reconciliation_state = "matched"
        held_risk = max(
            planned_reserved_risk,
            directional_risk + remaining_entry_risk,
        )
    return AccountExposureCurrentRow(
        account_exposure_current_id=_stable_id(
            "account_exposure", snapshot.account_id, classified.exchange_instrument_id, "BOTH"
        ),
        account_id=snapshot.account_id,
        exchange_id=snapshot.exchange_id,
        exchange_instrument_id=classified.exchange_instrument_id,
        exchange_symbol=position.exchange_symbol,
        position_mode=str(snapshot.position_mode or "one_way"),
        position_bucket="BOTH",
        owner_ticket_id=classified.owner_ticket_id,
        ownership_state=classified.ownership_state,
        position_slot_claimed=True,
        exposure_state=exposure_state,
        position_qty=qty,
        entry_price=position.entry_price,
        confirmed_stop_price=stop_price,
        working_entry_qty=working_entry_qty,
        planned_reserved_risk=planned_reserved_risk,
        actual_directional_risk=directional_risk,
        held_risk=held_risk,
        protection_state=protection_state,
        stop_covered_qty=stop_covered_qty,
        reconciliation_state=reconciliation_state,
        first_blocker=blocker,
        source_snapshot_id=snapshot.source_snapshot_id,
        projection_version=0,
    )


def _confirmed_stop_segments(
    snapshot: FullAccountRiskSnapshot,
    *,
    classifications: tuple[AccountOrderClassification, ...],
    exchange_symbol: str,
    owner_ticket_id: str | None,
    position_side: str,
    trade_side: str,
    position_qty: Decimal,
) -> tuple[tuple[Decimal, Decimal], ...]:
    if not owner_ticket_id:
        return ()
    matching_orders = {
        _order_identity(order): order
        for order in (*snapshot.regular_open_orders, *snapshot.algo_open_orders)
    }
    stops: list[ExchangeOpenOrderRow] = []
    for classified in classifications:
        if (
            classified.exchange_symbol == exchange_symbol
            and classified.owner_ticket_id == owner_ticket_id
            and classified.purpose in _STOP_PURPOSES
        ):
            order = matching_orders.get(_classification_identity(classified))
            if order and _is_eligible_protective_stop(
                order,
                position_side=position_side,
                trade_side=trade_side,
            ):
                stops.append(order)
    if not stops:
        return ()
    ordered = sorted(
        stops,
        key=lambda item: item.trigger_price or _ZERO,
        reverse=trade_side == "short",
    )
    remaining = position_qty
    segments: list[tuple[Decimal, Decimal]] = []
    for order in ordered:
        if remaining <= 0:
            break
        assert order.trigger_price is not None
        assert order.quantity is not None
        covered_qty = min(order.quantity, remaining)
        if covered_qty <= 0:
            continue
        segments.append((order.trigger_price, covered_qty))
        remaining -= covered_qty
    return tuple(segments)


def _is_eligible_protective_stop(
    order: ExchangeOpenOrderRow,
    *,
    position_side: str,
    trade_side: str,
) -> bool:
    if not order.trigger_price or order.trigger_price <= 0:
        return False
    if not order.quantity or order.quantity <= 0:
        return False
    if order.reduce_only is not True and order.close_position is not True:
        return False
    expected_order_side = "SELL" if trade_side == "long" else "BUY"
    if order.side != expected_order_side:
        return False
    return order.position_side == position_side


def _working_entry(
    snapshot: FullAccountRiskSnapshot,
    *,
    classifications: tuple[AccountOrderClassification, ...],
    exchange_symbol: str,
    owner_ticket_id: str | None,
) -> tuple[Decimal, Decimal | None]:
    if not owner_ticket_id:
        return _ZERO, None
    matching_orders = {
        _order_identity(order): order
        for order in (*snapshot.regular_open_orders, *snapshot.algo_open_orders)
    }
    entries = [
        matching_orders.get(_classification_identity(classified))
        for classified in classifications
        if (
            classified.exchange_symbol == exchange_symbol
            and classified.owner_ticket_id == owner_ticket_id
            and classified.purpose == "working_entry"
        )
    ]
    valid = [item for item in entries if item and item.quantity and item.quantity > 0]
    if not valid:
        return _ZERO, None
    return sum((item.quantity or _ZERO for item in valid), _ZERO), valid[0].price


def _reservation_only_rows(
    snapshot: FullAccountRiskSnapshot,
    reservations: dict[str, dict[str, object]],
    position_ticket_ids: set[str],
) -> list[AccountExposureCurrentRow]:
    rows: list[AccountExposureCurrentRow] = []
    for reservation in reservations.values():
        ticket_id = str(reservation["ticket_id"] or "")
        if ticket_id and ticket_id in position_ticket_ids:
            continue
        symbol = str(reservation["symbol"])
        instrument_id = f"{snapshot.exchange_id}:{symbol}"
        risk = _decimal(reservation["risk_at_stop"])
        rows.append(
            AccountExposureCurrentRow(
                account_exposure_current_id=_stable_id(
                    "account_exposure", snapshot.account_id, instrument_id, "BOTH"
                ),
                account_id=snapshot.account_id,
                exchange_id=snapshot.exchange_id,
                exchange_instrument_id=instrument_id,
                exchange_symbol=symbol,
                position_mode=str(snapshot.position_mode or "one_way"),
                position_bucket="BOTH",
                owner_ticket_id=ticket_id or None,
                ownership_state="owned_by_ticket" if ticket_id else "identity_conflict",
                position_slot_claimed=True,
                exposure_state="reserved",
                position_qty=_ZERO,
                entry_price=None,
                confirmed_stop_price=None,
                working_entry_qty=_ZERO,
                planned_reserved_risk=risk,
                actual_directional_risk=_ZERO,
                held_risk=risk,
                protection_state="not_applicable",
                stop_covered_qty=_ZERO,
                reconciliation_state="matched",
                first_blocker=None if ticket_id else "budget_reservation_ticket_missing",
                source_snapshot_id=snapshot.source_snapshot_id,
                projection_version=0,
            )
        )
    return rows


def _active_reservations(
    conn: sa.Connection,
    account_id: str,
) -> dict[str, dict[str, object]]:
    if not sa.inspect(conn).has_table("brc_budget_reservations"):
        return {}
    table = sa.Table("brc_budget_reservations", sa.MetaData(), autoload_with=conn)
    required = {"ticket_id", "account_id", "symbol", "status", "risk_at_stop", "reserved_margin"}
    if not required <= set(table.c.keys()):
        return {}
    return {
        str(row["ticket_id"]): dict(row)
        for row in conn.execute(
            sa.select(table)
            .where(table.c.account_id == account_id)
            .where(table.c.status.in_(("active", "consumed")))
        ).mappings()
        if str(row["ticket_id"] or "")
    }


def _reservation_risk(
    reservations: dict[str, dict[str, object]],
    ticket_id: str | None,
) -> Decimal:
    if not ticket_id or ticket_id not in reservations:
        return _ZERO
    return _decimal(reservations[ticket_id]["risk_at_stop"])


def _flat_rows_absent_from_snapshot(
    conn: sa.Connection,
    snapshot: FullAccountRiskSnapshot,
    projected_rows: list[AccountExposureCurrentRow],
) -> list[AccountExposureCurrentRow]:
    if not sa.inspect(conn).has_table("brc_account_exposure_current"):
        return []
    table = sa.Table("brc_account_exposure_current", sa.MetaData(), autoload_with=conn)
    projected_keys = {
        (row.exchange_instrument_id, row.position_mode, row.position_bucket)
        for row in projected_rows
    }
    result: list[AccountExposureCurrentRow] = []
    for existing in conn.execute(
        sa.select(table).where(table.c.account_id == snapshot.account_id)
    ).mappings():
        key = (
            str(existing["exchange_instrument_id"]),
            str(existing["position_mode"]),
            str(existing["position_bucket"]),
        )
        if key in projected_keys:
            continue
        result.append(
            AccountExposureCurrentRow(
                account_exposure_current_id=str(existing["account_exposure_current_id"]),
                account_id=snapshot.account_id,
                exchange_id=snapshot.exchange_id,
                exchange_instrument_id=key[0],
                exchange_symbol=str(existing["exchange_symbol"]),
                position_mode=key[1],
                position_bucket=key[2],
                owner_ticket_id=(
                    str(existing["owner_ticket_id"])
                    if existing["owner_ticket_id"] is not None
                    else None
                ),
                ownership_state=str(existing["ownership_state"]),
                position_slot_claimed=False,
                exposure_state="flat",
                position_qty=_ZERO,
                entry_price=None,
                confirmed_stop_price=None,
                working_entry_qty=_ZERO,
                planned_reserved_risk=_ZERO,
                actual_directional_risk=_ZERO,
                held_risk=_ZERO,
                protection_state="not_applicable",
                stop_covered_qty=_ZERO,
                reconciliation_state="matched",
                first_blocker=None,
                source_snapshot_id=snapshot.source_snapshot_id,
                projection_version=0,
            )
        )
    return result


def _persist_rows(
    conn: sa.Connection,
    rows: list[AccountExposureCurrentRow],
    *,
    snapshot: FullAccountRiskSnapshot,
    now_ms: int,
) -> int:
    current = sa.Table("brc_account_exposure_current", sa.MetaData(), autoload_with=conn)
    events = sa.Table("brc_account_risk_projection_events", sa.MetaData(), autoload_with=conn)
    event_count = 0
    for row in rows:
        existing = conn.execute(
            sa.select(current).where(
                current.c.account_id == row.account_id,
                current.c.exchange_instrument_id == row.exchange_instrument_id,
                current.c.position_mode == row.position_mode,
                current.c.position_bucket == row.position_bucket,
            )
        ).mappings().one_or_none()
        fingerprint = _semantic_fingerprint(row)
        projection_version = int(existing["projection_version"] or 0) + 1 if existing else 1
        values = _row_values(
            row, snapshot=snapshot, fingerprint=fingerprint,
            projection_version=projection_version, now_ms=now_ms,
        )
        if existing:
            conn.execute(
                current.update()
                .where(current.c.account_exposure_current_id == existing["account_exposure_current_id"])
                .values(**values)
            )
        else:
            conn.execute(current.insert().values(**values))
        if existing and str(existing["semantic_fingerprint"]) == fingerprint:
            continue
        event_count += 1
        event_values = {
            "account_risk_projection_event_id": _stable_id(
                "account_risk_projection_event", row.account_exposure_current_id, fingerprint
            ),
            "account_exposure_current_id": row.account_exposure_current_id,
            "semantic_fingerprint": fingerprint,
            "event_payload": _event_payload(events, row),
            "created_at_ms": now_ms,
        }
        conn.execute(events.insert().values(**event_values))
    return event_count


def _row_values(
    row: AccountExposureCurrentRow,
    *,
    snapshot: FullAccountRiskSnapshot,
    fingerprint: str,
    projection_version: int,
    now_ms: int,
) -> dict[str, object]:
    return {
        **row.model_dump(),
        "netting_domain_key": f"{row.account_id}:{row.exchange_instrument_id}:{row.position_bucket}",
        "exchange_initial_margin": _ZERO,
        "unreflected_pending_margin": _ZERO,
        "tp1_open_qty": _ZERO,
        "runner_stop_open_qty": _ZERO,
        "observed_at_ms": snapshot.observed_at_ms,
        "valid_until_ms": snapshot.valid_until_ms,
        "projection_version": projection_version,
        "semantic_fingerprint": fingerprint,
        "updated_at_ms": now_ms,
    }


def _semantic_fingerprint(row: AccountExposureCurrentRow) -> str:
    payload = {
        "ownership_state": row.ownership_state,
        "exposure_state": row.exposure_state,
        "held_risk": str(row.held_risk),
        "protection_state": row.protection_state,
        "reconciliation_state": row.reconciliation_state,
        "first_blocker": row.first_blocker,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _event_payload(events: sa.Table, row: AccountExposureCurrentRow) -> object:
    payload = {
        "ownership_state": row.ownership_state,
        "exposure_state": row.exposure_state,
        "held_risk": str(row.held_risk),
        "protection_state": row.protection_state,
        "reconciliation_state": row.reconciliation_state,
        "first_blocker": row.first_blocker,
    }
    return payload if isinstance(events.c.event_payload.type, sa.JSON) else json.dumps(payload, sort_keys=True)


def _order_identity(order: ExchangeOpenOrderRow) -> str:
    return order.exchange_order_id or order.algo_id or order.client_order_id


def _classification_identity(order: AccountOrderClassification) -> str:
    return order.exchange_order_id or order.algo_id or order.client_order_id


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}:{sha256('|'.join(parts).encode()).hexdigest()[:32]}"
