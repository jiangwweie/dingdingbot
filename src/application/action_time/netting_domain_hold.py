"""Source-specific capital safety holds keyed by mechanical netting domain."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import sqlalchemy as sa


TABLE = "brc_ticket_bound_scope_freezes"


def upsert_exchange_command_domain_hold(
    conn: sa.engine.Connection,
    *,
    command: dict[str, Any],
    blockers: list[str],
    now_ms: int,
) -> dict[str, Any]:
    return upsert_netting_domain_hold(
        conn,
        account_id=command.get("account_id"),
        runtime_profile_id=command.get("runtime_profile_id"),
        exchange_id=command.get("exchange_id"),
        exchange_instrument_id=command.get("exchange_instrument_id"),
        position_mode=command.get("position_mode"),
        position_bucket=command.get("position_bucket"),
        netting_domain_key=command.get("netting_domain_key"),
        source_ticket_id=command.get("ticket_id"),
        strategy_group_id=command.get("strategy_group_id"),
        symbol=command.get("symbol"),
        side=command.get("side"),
        source_kind="exchange_command",
        source_id=command.get("exchange_command_id"),
        blockers=blockers,
        next_action="reconcile_exchange_command_identity_before_new_exposure",
        authority_boundary=(
            "source_specific_netting_domain_hold; blocks new exposure in one "
            "mechanical position domain; no exchange-write or policy authority"
        ),
        now_ms=now_ms,
    )


def upsert_netting_domain_hold(
    conn: sa.engine.Connection,
    *,
    account_id: Any,
    runtime_profile_id: Any,
    exchange_id: Any,
    exchange_instrument_id: Any,
    position_mode: Any,
    position_bucket: Any,
    netting_domain_key: Any,
    source_ticket_id: Any,
    strategy_group_id: Any,
    symbol: Any,
    side: Any,
    source_kind: Any,
    source_id: Any,
    blockers: list[str],
    next_action: str,
    authority_boundary: str,
    now_ms: int,
) -> dict[str, Any]:
    if not sa.inspect(conn).has_table(TABLE):
        raise ValueError("netting_domain_hold_table_missing")
    values = {
        "account_id": str(account_id or "").strip(),
        "runtime_profile_id": str(runtime_profile_id or "").strip(),
        "exchange_id": str(exchange_id or "").strip(),
        "exchange_instrument_id": str(exchange_instrument_id or "").strip(),
        "position_mode": str(position_mode or "").strip(),
        "position_bucket": str(position_bucket or "").strip(),
        "netting_domain_key": str(netting_domain_key or "").strip(),
        "source_ticket_id": str(source_ticket_id or "").strip(),
        "strategy_group_id": str(strategy_group_id or "").strip(),
        "symbol": str(symbol or "").strip(),
        "side": str(side or "").strip(),
        "source_kind": str(source_kind or "").strip(),
        "source_id": str(source_id or "").strip(),
    }
    missing = [key for key, value in values.items() if not value]
    if missing or not blockers:
        raise ValueError(
            "netting_domain_hold_identity_incomplete:"
            + ",".join(missing or ["blockers"])
        )
    hold_id = _stable_id(
        "netting_domain_hold",
        values["netting_domain_key"],
        values["source_kind"],
        values["source_id"],
    )
    row = {
        "scope_freeze_id": hold_id,
        **values,
        "status": "active",
        "first_blocker": blockers[0],
        "blockers": list(dict.fromkeys(blockers)),
        "freeze_scope": {
            "netting_domain_key": values["netting_domain_key"],
            "source_kind": values["source_kind"],
            "source_id": values["source_id"],
        },
        "next_action": next_action,
        "authority_boundary": authority_boundary,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }
    table = sa.Table(TABLE, sa.MetaData(), autoload_with=conn)
    existing = conn.execute(
        sa.select(table).where(table.c.scope_freeze_id == hold_id)
    ).mappings().first()
    table_values = {
        column.name: row[column.name]
        for column in table.columns
        if column.name in row
    }
    if existing:
        table_values["created_at_ms"] = existing.get("created_at_ms") or now_ms
        conn.execute(
            table.update()
            .where(table.c.scope_freeze_id == hold_id)
            .values(**table_values)
        )
    else:
        conn.execute(table.insert().values(**table_values))
    stored = conn.execute(
        sa.select(table).where(table.c.scope_freeze_id == hold_id)
    ).mappings().one()
    return dict(stored)


def resolve_netting_domain_hold_source(
    conn: sa.engine.Connection,
    *,
    netting_domain_key: str,
    source_kind: str,
    source_id: str,
    resolution_source: str,
    now_ms: int,
) -> int:
    table = sa.Table(TABLE, sa.MetaData(), autoload_with=conn)
    result = conn.execute(
        table.update()
        .where(
            table.c.netting_domain_key == netting_domain_key,
            table.c.source_kind == source_kind,
            table.c.source_id == source_id,
            table.c.status == "active",
        )
        .values(
            status="resolved",
            first_blocker="source_specific_risk_reconciled",
            blockers=[],
            next_action="continue_only_if_all_other_domain_holds_clear",
            updated_at_ms=now_ms,
            freeze_scope={
                "netting_domain_key": netting_domain_key,
                "resolution_source": resolution_source,
            },
        )
    )
    return int(result.rowcount or 0)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()[:40]
    return f"{prefix}:{digest}"
