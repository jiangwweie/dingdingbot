#!/usr/bin/env python3
"""Read-only diagnostics for BNB final-gate blockers."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


TABLES = [
    "global_kill_switch_state",
    "orders",
    "execution_intents",
    "positions",
]


async def _columns(conn: Any, table: str) -> list[str]:
    rows = (
        await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :table
                ORDER BY ordinal_position
                """
            ),
            {"schema": "public", "table": table},
        )
    ).all()
    return [str(row[0]) for row in rows]


def _selects(columns: set[str], wanted: list[str]) -> list[str]:
    selected: list[str] = []
    for name in wanted:
        if name in columns:
            if name in {"quantity", "amount", "price", "filled_qty", "avg_price", "leverage"}:
                selected.append(f"{name}::text AS {name}")
            else:
                selected.append(name)
    return selected


async def inspect_blockers() -> dict[str, Any]:
    database_url = os.environ.get("PG_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("PG_DATABASE_URL is required")
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            table_columns = {table: await _columns(conn, table) for table in TABLES}

            gks_rows = []
            if table_columns["global_kill_switch_state"]:
                gks_rows = [
                    dict(row)
                    for row in (
                        await conn.execute(
                            text(
                                """
                                SELECT state_key, active, reason, updated_by, updated_at_ms
                                FROM global_kill_switch_state
                                ORDER BY updated_at_ms DESC
                                LIMIT 5
                                """
                            )
                        )
                    ).mappings().all()
                ]

            order_columns = set(table_columns["orders"])
            order_selects = _selects(
                order_columns,
                [
                    "id",
                    "signal_id",
                    "authorization_id",
                    "symbol",
                    "side",
                    "role",
                    "status",
                    "order_type",
                    "quantity",
                    "amount",
                    "price",
                    "exchange_order_id",
                    "client_order_id",
                    "parent_order_id",
                    "created_at",
                    "updated_at",
                ],
            )
            bnb_orders = []
            if order_selects and "symbol" in order_columns:
                status_filter = ""
                if "status" in order_columns:
                    status_filter = (
                        "AND lower(status) IN ('open', 'new', 'submitted', 'partially_filled')"
                    )
                rows = (
                    await conn.execute(
                        text(
                            "SELECT "
                            + ", ".join(order_selects)
                            + " FROM orders WHERE symbol = :symbol "
                            + status_filter
                            + " ORDER BY "
                            + ("updated_at" if "updated_at" in order_columns else order_selects[0].split()[0])
                            + " DESC LIMIT 20"
                        ),
                        {"symbol": "BNB/USDT:USDT"},
                    )
                ).mappings().all()
                bnb_orders = [dict(row) for row in rows]

            intent_columns = set(table_columns["execution_intents"])
            intent_selects = _selects(
                intent_columns,
                [
                    "id",
                    "signal_id",
                    "authorization_id",
                    "symbol",
                    "direction",
                    "status",
                    "order_id",
                    "exchange_order_id",
                    "failed_reason",
                    "created_at",
                    "updated_at",
                ],
            )
            bnb_intents = []
            if intent_selects:
                rows = (
                    await conn.execute(
                        text(
                            "SELECT "
                            + ", ".join(intent_selects)
                            + " FROM execution_intents "
                            + "WHERE (signal_id LIKE :pattern OR authorization_id IS NOT NULL) "
                            + "ORDER BY "
                            + ("created_at" if "created_at" in intent_columns else intent_selects[0].split()[0])
                            + " DESC LIMIT 20"
                        ),
                        {"pattern": "%BNB%"},
                    )
                ).mappings().all()
                bnb_intents = [dict(row) for row in rows]

            return {
                "note": "read-only final-gate blocker diagnostics; raw payloads omitted",
                "table_columns": table_columns,
                "global_kill_switch_state": gks_rows,
                "bnb_open_orders_pg": bnb_orders,
                "bnb_execution_intents": bnb_intents,
                "positions_schema_has_quantity": "quantity" in set(table_columns["positions"]),
            }
    finally:
        await engine.dispose()


async def main() -> None:
    print(json.dumps(await inspect_blockers(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
