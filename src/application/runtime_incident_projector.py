"""Formal current incident projection for non-lane runtime failures."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import sqlalchemy as sa


def upsert_system_runtime_incident(
    conn: sa.engine.Connection,
    *,
    incident_type: str,
    blocker: str,
    details: dict[str, Any],
    now_ms: int,
) -> dict[str, str]:
    if not sa.inspect(conn).has_table("brc_runtime_incidents"):
        return {"status": "incident_table_missing", "incident_id": ""}
    table = sa.Table("brc_runtime_incidents", sa.MetaData(), autoload_with=conn)
    fingerprint = sha256(f"system:{incident_type}:{blocker}".encode()).hexdigest()[:48]
    incident_id = f"incident:system:{fingerprint}"
    values = {
        "incident_id": incident_id, "incident_type": incident_type,
        "severity": "blocking", "status": "open", "strategy_group_id": None,
        "symbol": None, "side": None, "blocker_class": blocker,
        "trigger_ref": str(details.get("source_watermark") or ""),
        "details": details, "opened_at_ms": now_ms, "closed_at_ms": None,
    }
    existing = conn.execute(sa.select(table.c.incident_id).where(table.c.incident_id == incident_id)).scalar_one_or_none()
    if existing is None:
        conn.execute(table.insert().values(**values))
    else:
        conn.execute(table.update().where(table.c.incident_id == incident_id).values(
            status="open", blocker_class=blocker, trigger_ref=values["trigger_ref"],
            details=details, closed_at_ms=None,
        ))
    return {"status": "open", "incident_id": incident_id}
