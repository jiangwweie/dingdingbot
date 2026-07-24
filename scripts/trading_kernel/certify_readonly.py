#!/usr/bin/env python3
"""Read-only trading-kernel certification with one JSON stdout result."""

from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
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
from src.trading_kernel.infrastructure.runtime_authority_seed import (  # noqa: E402
    DYNAMIC_POLICY,
    OWNER_POLICY_ID,
)


SCHEMA = "brc.trading_kernel.readonly_certification.v1"
EXPECTED_ALEMBIC_REVISION = "0001_initial"
LEGACY_EXECUTION_TABLES = (
    "brc_runtime_execution_tickets",
    "brc_runtime_execution_orders",
    "brc_action_time_tickets",
    "brc_order_lifecycle_records",
    "brc_execution_intents",
)
_DECIMAL_POLICY_FIELDS = frozenset(
    {
        "planned_stop_risk_fraction",
        "max_initial_margin_utilization",
        "min_liquidation_distance_to_stop_distance_ratio",
        "max_post_fill_stop_risk_overrun_fraction",
    }
)


def _canonical_decimal(value: object) -> str:
    return format(Decimal(str(value)).normalize(), "f")


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
            owner_policy_row = (
                await connection.execute(
                    text(
                        """
                        SELECT owner_policy_id,
                               policy_version,
                               enabled,
                               new_entry_submit_enabled,
                               max_concurrent_tickets,
                               planned_stop_risk_fraction,
                               max_initial_margin_utilization,
                               max_leverage,
                               supported_margin_mode,
                               min_liquidation_distance_to_stop_distance_ratio,
                               max_post_fill_stop_risk_overrun_fraction
                          FROM brc_owner_policy_current
                        """
                    )
                )
            ).mappings().one_or_none()
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
            budget_reservations = int(
                (
                    await connection.execute(
                        text("SELECT count(*) FROM brc_budget_reservations")
                    )
                ).scalar_one()
            )
            released_budget_reservations = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT count(*)
                              FROM brc_budget_reservations
                             WHERE status = 'released'
                               AND released_at_ms IS NOT NULL
                            """
                        )
                    )
                ).scalar_one()
            )
            active_budget_reservations = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM brc_budget_reservations "
                            "WHERE status = 'active'"
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
    release_counts = {
        "budget_reservations": budget_reservations,
        "released_budget_reservations": released_budget_reservations,
        "active_budget_reservations": active_budget_reservations,
    }
    owner_projection = (
        None
        if owner_projection_row is None
        else {key: owner_projection_row[key] for key in owner_projection_row}
    )
    owner_policy = (
        None
        if owner_policy_row is None
        else {
            key: (
                _canonical_decimal(value)
                if key in _DECIMAL_POLICY_FIELDS
                else value
            )
            for key, value in owner_policy_row.items()
        }
    )
    policy_is_dynamic = owner_policy_row is not None and all(
        (
            owner_policy_row["owner_policy_id"] == OWNER_POLICY_ID,
            int(owner_policy_row["policy_version"]) in {1, 2, 3},
            owner_policy_row["enabled"] is True,
            isinstance(owner_policy_row["new_entry_submit_enabled"], bool),
            int(owner_policy_row["max_concurrent_tickets"])
            == DYNAMIC_POLICY.max_concurrent_tickets,
            Decimal(str(owner_policy_row["planned_stop_risk_fraction"]))
            == DYNAMIC_POLICY.planned_stop_risk_fraction,
            Decimal(str(owner_policy_row["max_initial_margin_utilization"]))
            == DYNAMIC_POLICY.max_initial_margin_utilization,
            int(owner_policy_row["max_leverage"]) == DYNAMIC_POLICY.max_leverage,
            owner_policy_row["supported_margin_mode"]
            == DYNAMIC_POLICY.supported_margin_mode,
            Decimal(
                str(owner_policy_row["min_liquidation_distance_to_stop_distance_ratio"])
            )
            == DYNAMIC_POLICY.min_liquidation_distance_to_stop_distance_ratio,
            Decimal(
                str(owner_policy_row["max_post_fill_stop_risk_overrun_fraction"])
            )
            == DYNAMIC_POLICY.max_post_fill_stop_risk_overrun_fraction,
        )
    )
    capabilities_are_current = (
        set(capabilities) == {"exchange_commands", "strategy_signal_ingest"}
        and capabilities["strategy_signal_ingest"] is True
        and isinstance(capabilities["exchange_commands"], bool)
    )
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
        and capabilities_are_current
        and policy_is_dynamic
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
        "owner_policy": owner_policy,
        "release_counts": release_counts,
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
