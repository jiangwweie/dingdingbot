#!/usr/bin/env python3
"""Read-only trading-kernel certification with one JSON stdout result."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.infrastructure.pg_models import metadata  # noqa: E402


SCHEMA = "brc.trading_kernel.readonly_certification.v1"
EXPECTED_ALEMBIC_REVISION = "0001_initial"
LEGACY_EXECUTION_TABLES = (
    "brc_runtime_execution_tickets",
    "brc_runtime_execution_orders",
    "brc_action_time_tickets",
    "brc_order_lifecycle_records",
    "brc_execution_intents",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    parser.add_argument(
        "--require-flat",
        action="store_true",
        help="Also require zero position quantity and zero active Ticket domains.",
    )
    return parser


async def _certify(database_url: str, *, require_flat: bool) -> dict[str, object]:
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = str(
                (
                    await connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    )
                ).scalar_one()
            )
            runtime_identity = {
                str(row["metadata_key"]): str(row["metadata_value"])
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT metadata_key, metadata_value
                              FROM brc_schema_metadata
                             WHERE metadata_key IN (
                                'runtime_commit',
                                'schema_revision',
                                'seed_identity'
                             )
                            """
                        )
                    )
                ).mappings()
            }
            actual_tables = {
                str(name)
                for name in (
                    await connection.execute(
                        text(
                            """
                            SELECT relname
                              FROM pg_catalog.pg_class
                             WHERE relkind IN ('r', 'p')
                               AND relnamespace = current_schema()::regnamespace
                               AND relname <> 'alembic_version'
                            """
                        )
                    )
                ).scalars()
            }
            expected_tables = set(metadata.tables)
            runtime_scope_count = int(
                (
                    await connection.execute(
                        text("SELECT count(*) FROM brc_runtime_scopes_current")
                    )
                ).scalar_one()
            )
            capabilities = {
                str(row["capability_key"]): bool(row["enabled"])
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT capability_key, enabled
                              FROM brc_runtime_capabilities_current
                             ORDER BY capability_key
                            """
                        )
                    )
                ).mappings()
            }
            integrity_orphans = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT
                                (SELECT count(*)
                                   FROM brc_trade_aggregates aggregate_current
                                   LEFT JOIN brc_trade_tickets ticket
                                     ON ticket.ticket_id = aggregate_current.ticket_id
                                  WHERE ticket.ticket_id IS NULL)
                              + (SELECT count(*)
                                   FROM brc_trade_events event
                                   LEFT JOIN brc_trade_tickets ticket
                                     ON ticket.ticket_id = event.ticket_id
                                  WHERE ticket.ticket_id IS NULL)
                              + (SELECT count(*)
                                   FROM brc_exchange_commands command
                                   LEFT JOIN brc_trade_tickets ticket
                                     ON ticket.ticket_id = command.ticket_id
                                  WHERE ticket.ticket_id IS NULL)
                            """
                        )
                    )
                ).scalar_one()
            )
            legacy_execution_tables = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT count(*)
                              FROM pg_catalog.pg_class
                             WHERE relkind IN ('r', 'p')
                               AND relnamespace = current_schema()::regnamespace
                               AND relname = ANY(:legacy_names)
                            """
                        ),
                        {"legacy_names": list(LEGACY_EXECUTION_TABLES)},
                    )
                ).scalar_one()
            )
            non_flat_positions = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM brc_positions_current "
                            "WHERE quantity <> 0"
                        )
                    )
                ).scalar_one()
            )
            active_ticket_domains = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM brc_trade_tickets "
                            "WHERE active_netting_domain_key IS NOT NULL"
                        )
                    )
                ).scalar_one()
            )
            unresolved_commands = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM brc_exchange_commands "
                            "WHERE status IN "
                            "('prepared', 'claimed', 'outcome_unknown')"
                        )
                    )
                ).scalar_one()
            )
            open_incidents = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM brc_runtime_incidents "
                            "WHERE status = 'open'"
                        )
                    )
                ).scalar_one()
            )
            owner_projection_row = (
                await connection.execute(
                    text(
                        """
                        SELECT monitor_key,
                               owner_status,
                               summary,
                               intervention,
                               ticket_id,
                               incident_id,
                               updated_at_ms,
                               projection_version
                          FROM brc_monitor_current
                         ORDER BY updated_at_ms DESC, monitor_key
                         LIMIT 1
                        """
                    )
                )
            ).mappings().one_or_none()
            await connection.rollback()
    finally:
        await engine.dispose()

    checks = {
        "integrity_orphans": integrity_orphans,
        "legacy_execution_tables": legacy_execution_tables,
        "non_flat_positions": non_flat_positions,
        "active_ticket_domains": active_ticket_domains,
        "unresolved_commands": unresolved_commands,
        "open_incidents": open_incidents,
    }
    table_allowlist = {
        "status": "pass" if actual_tables == expected_tables else "fail",
        "count": len(actual_tables),
        "tables": sorted(actual_tables),
    }
    active_counts = {
        "tickets": active_ticket_domains,
        "commands": unresolved_commands,
        "positions": non_flat_positions,
        "incidents": open_incidents,
    }
    owner_projection = (
        None
        if owner_projection_row is None
        else {key: owner_projection_row[key] for key in owner_projection_row}
    )
    expected_capabilities = {
        "exchange_commands": False,
        "strategy_signal_ingest": True,
    }
    passed = (
        revision == EXPECTED_ALEMBIC_REVISION
        and runtime_identity.get("schema_revision") == EXPECTED_ALEMBIC_REVISION
        and set(runtime_identity) == {
            "runtime_commit",
            "schema_revision",
            "seed_identity",
        }
        and actual_tables == expected_tables
        and runtime_scope_count == 22
        and capabilities == expected_capabilities
        and integrity_orphans == 0
        and legacy_execution_tables == 0
        and unresolved_commands == 0
        and open_incidents == 0
        and (
            not require_flat
            or (non_flat_positions == 0 and active_ticket_domains == 0)
        )
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "runtime_identity": runtime_identity,
        "table_allowlist": table_allowlist,
        "runtime_scope_count": runtime_scope_count,
        "capabilities": capabilities,
        "active_counts": active_counts,
        "owner_projection": owner_projection,
        "require_flat": require_flat,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = asyncio.run(
        _certify(str(args.database_url or "").strip(), require_flat=args.require_flat)
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
