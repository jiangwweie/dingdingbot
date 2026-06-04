#!/usr/bin/env python3
"""Inspect PG runtime_profiles without mutating state.

The output intentionally omits full profile_payload. It reports only schema,
counts, active names, and a safe business summary for human review before or
after a controlled runtime profile metadata task.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Mapping

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.domain.validators import stable_config_hash
from src.infrastructure.database import close_db, get_pg_session_maker


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "t"}


def safe_payload_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a non-secret profile payload summary."""
    if not isinstance(payload, Mapping):
        return {"payload_type": type(payload).__name__}

    market = payload.get("market") if isinstance(payload.get("market"), Mapping) else {}
    strategy = payload.get("strategy") if isinstance(payload.get("strategy"), Mapping) else {}
    risk = payload.get("risk") if isinstance(payload.get("risk"), Mapping) else {}
    brc = payload.get("brc") if isinstance(payload.get("brc"), Mapping) else {}
    non_permissions = (
        brc.get("non_permissions")
        if isinstance(brc.get("non_permissions"), Mapping)
        else {}
    )
    fixed_caps = brc.get("fixed_caps") if isinstance(brc.get("fixed_caps"), Mapping) else {}

    return {
        "payload_hash": stable_config_hash(payload),
        "payload_keys": sorted(str(key) for key in payload.keys()),
        "market": {
            "primary_symbol": market.get("primary_symbol"),
            "symbols": market.get("symbols"),
            "primary_timeframe": market.get("primary_timeframe"),
            "mtf_timeframe": market.get("mtf_timeframe"),
        },
        "strategy": {
            "allowed_directions": strategy.get("allowed_directions"),
            "trigger_type": (
                strategy.get("trigger", {}).get("type")
                if isinstance(strategy.get("trigger"), Mapping)
                else None
            ),
        },
        "risk": {
            "max_leverage": risk.get("max_leverage"),
            "max_total_exposure": risk.get("max_total_exposure"),
            "daily_max_trades": risk.get("daily_max_trades"),
        },
        "brc": {
            "carrier_id": brc.get("carrier_id"),
            "controlled_playbook_id": brc.get("controlled_playbook_id"),
            "symbol_sequence": brc.get("symbol_sequence"),
            "fixed_caps": fixed_caps,
            "non_permissions": non_permissions,
        },
    }


def safe_profile_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("name"),
        "description": row.get("description"),
        "is_active": _as_bool(row.get("is_active")),
        "is_readonly": _as_bool(row.get("is_readonly")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "version": row.get("version"),
        "payload_summary": safe_payload_summary(row.get("profile_payload")),
    }


async def inspect_runtime_profiles() -> dict[str, Any]:
    maker = get_pg_session_maker()
    async with maker() as session:
        exists = await session.scalar(
            text("SELECT to_regclass(:name) IS NOT NULL"),
            {"name": "public.runtime_profiles"},
        )
        report: dict[str, Any] = {
            "runtime_profiles_exists": bool(exists),
            "note": "read-only inspection; full profile_payload omitted",
        }
        if not exists:
            return report

        result = await session.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema=:schema_name AND table_name=:table_name
                ORDER BY ordinal_position
                """
            ),
            {"schema_name": "public", "table_name": "runtime_profiles"},
        )
        report["columns"] = [dict(row) for row in result.mappings().all()]

        result = await session.execute(
            text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname=:schema_name AND tablename=:table_name
                ORDER BY indexname
                """
            ),
            {"schema_name": "public", "table_name": "runtime_profiles"},
        )
        report["indexes"] = [dict(row) for row in result.mappings().all()]

        result = await session.execute(
            text(
                """
                SELECT conname, pg_get_constraintdef(c.oid) AS definition
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid=t.oid
                JOIN pg_namespace n ON n.oid=t.relnamespace
                WHERE n.nspname=:schema_name AND t.relname=:table_name
                ORDER BY conname
                """
            ),
            {"schema_name": "public", "table_name": "runtime_profiles"},
        )
        report["constraints"] = [dict(row) for row in result.mappings().all()]

        count = await session.scalar(text("SELECT count(*) FROM runtime_profiles"))
        active_count = await session.scalar(
            text("SELECT count(*) FROM runtime_profiles WHERE is_active IS TRUE")
        )
        report["count"] = int(count or 0)
        report["active_count"] = int(active_count or 0)

        result = await session.execute(
            text(
                """
                SELECT name, description, profile_payload, is_active, is_readonly,
                       created_at, updated_at, version
                FROM runtime_profiles
                ORDER BY is_active DESC, updated_at DESC, name ASC
                """
            )
        )
        report["profiles"] = [
            safe_profile_row(dict(row))
            for row in result.mappings().all()
        ]

        return report


async def main() -> None:
    try:
        report = await inspect_runtime_profiles()
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
