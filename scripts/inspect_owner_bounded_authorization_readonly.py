#!/usr/bin/env python3
"""Read-only inspection for Owner bounded live authorization state."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


AUTH_TABLE = "brc_bounded_live_trial_authorizations"
INTENT_TABLE = "execution_intents"
WANTED_AUTH_COLUMNS = [
    "authorization_id",
    "draft_id",
    "carrier_id",
    "symbol",
    "side",
    "quantity",
    "max_notional",
    "leverage",
    "protection_plan_type",
    "single_use",
    "consumed",
    "cancelled",
    "expires_at_ms",
    "created_at_ms",
    "updated_at_ms",
    "activated_at_ms",
    "operator_id",
]


async def _table_columns(conn: Any, table: str) -> list[dict[str, Any]]:
    rows = (
        await conn.execute(
            text(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = :table
                ORDER BY ordinal_position
                """
            ),
            {"schema": "public", "table": table},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _select_expr(name: str) -> str:
    if name in {"quantity", "max_notional", "leverage"}:
        return f"{name}::text AS {name}"
    return name


async def inspect_owner_bounded_authorizations() -> dict[str, Any]:
    database_url = os.environ.get("PG_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("PG_DATABASE_URL is required")
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            auth_columns = await _table_columns(conn, AUTH_TABLE)
            auth_column_names = {column["column_name"] for column in auth_columns}
            auth_rows: list[dict[str, Any]] = []
            selected_auth_columns = [
                name for name in WANTED_AUTH_COLUMNS if name in auth_column_names
            ]
            if selected_auth_columns:
                order_col = (
                    "created_at_ms"
                    if "created_at_ms" in auth_column_names
                    else selected_auth_columns[0]
                )
                rows = (
                    await conn.execute(
                        text(
                            "SELECT "
                            + ", ".join(_select_expr(name) for name in selected_auth_columns)
                            + f" FROM {AUTH_TABLE} ORDER BY {order_col} DESC LIMIT 10"
                        )
                    )
                ).mappings().all()
                auth_rows = [dict(row) for row in rows]

            intent_columns = await _table_columns(conn, INTENT_TABLE)
            intent_column_names = {column["column_name"] for column in intent_columns}
            intents_by_authorization: list[dict[str, Any]] = []
            if "authorization_id" in intent_column_names:
                status_expr = (
                    "status" if "status" in intent_column_names else "NULL::text"
                )
                order_col = "created_at" if "created_at" in intent_column_names else "id"
                rows = (
                    await conn.execute(
                        text(
                            f"""
                            SELECT authorization_id, count(*) AS count,
                                   array_agg({status_expr} ORDER BY {order_col} DESC) AS statuses
                            FROM {INTENT_TABLE}
                            WHERE authorization_id IS NOT NULL
                            GROUP BY authorization_id
                            """
                        )
                    )
                ).mappings().all()
                intents_by_authorization = [dict(row) for row in rows]

            return {
                "note": "read-only inspection; credentials and raw payloads omitted",
                "authorization_columns": auth_columns,
                "recent_authorizations": auth_rows,
                "execution_intents_by_authorization": intents_by_authorization,
            }
    finally:
        await engine.dispose()


async def main() -> None:
    print(
        json.dumps(
            await inspect_owner_bounded_authorizations(),
            ensure_ascii=False,
            default=str,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
