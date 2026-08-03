#!/usr/bin/env python3
"""Read-only trading-kernel certification with one JSON stdout result."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.strategy_universe_batch_manifest import (
    APPROVED_FIRST_BATCH_INSTRUMENT_IDS,
    APPROVED_UNIVERSE_EVENT_SPECS,
)
from src.trading_kernel.domain.instrument_certification import (
    build_certification_manifest_digest,
)
from src.trading_kernel.domain.strategy_registry import (
    build_registry_semantic_hash,
    registered_strategy_contracts,
)
from src.trading_kernel.domain.strategy_universe import build_strategy_universe
from src.trading_kernel.infrastructure.pg_models import metadata
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    DYNAMIC_POLICY,
    OWNER_POLICY_ID,
    RuntimeAuthoritySeedRequest,
    build_runtime_seed_identity,
)
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)

SCHEMA = "brc.trading_kernel.readonly_certification.v1"
EXPECTED_ALEMBIC_REVISION = CURRENT_SCHEMA_REVISION
LEGACY_EXECUTION_TABLES = (
    "brc_runtime_execution_tickets",
    "brc_runtime_execution_orders",
    "brc_action_time_tickets",
    "brc_order_lifecycle_records",
    "brc_execution_intents",
)
_DECIMAL_POLICY_FIELDS = frozenset(
    {
        "max_ticket_stop_risk_fraction",
        "max_gross_stop_risk_fraction",
        "max_ticket_initial_margin_fraction",
        "max_gross_initial_margin_utilization",
        "directional_stop_risk_limit_fraction",
        "min_materialization_ratio",
        "post_stop_stress_multiple",
        "max_post_fill_stop_risk_overrun_fraction",
    }
)
_COMPATIBLE_SOURCE_EVENT_SPECS = (
    ("BRF2-001", "event_spec:BRF2-001:BRF2-SHORT:v2"),
    ("CPM-RO-001", "event_spec:CPM-RO-001:CPM-LONG:v2"),
    ("MI-001", "event_spec:MI-001:MI-LONG:v2"),
    ("MPG-001", "event_spec:MPG-001:MPG-LONG:v2"),
    ("SOR-001", "event_spec:SOR-001:SOR-LONG:v3"),
    ("SOR-001", "event_spec:SOR-001:SOR-SHORT:v3"),
)


def _canonical_decimal(value: object) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def _certification_batch_policy_stage_matches(
    *,
    batch_policy_version: int,
    current_policy_version: int,
    new_entry_submit_enabled: bool,
) -> bool:
    """Accept an exact batch policy or its one authorized ENTRY-arm successor."""

    if (
        isinstance(batch_policy_version, bool)
        or isinstance(current_policy_version, bool)
        or batch_policy_version <= 0
        or current_policy_version <= 0
    ):
        return False
    if batch_policy_version == current_policy_version:
        return True
    return bool(
        current_policy_version == batch_policy_version + 1
        and new_entry_submit_enabled
    )


def _universe_manifest_matches(
    manifest: Sequence[Mapping[str, object]],
    *,
    expected_event_specs: Sequence[tuple[str, str]],
    expected_member_ids: tuple[str, ...],
) -> bool:
    expected_group_by_event = {
        event_spec_id: strategy_group_id
        for strategy_group_id, event_spec_id in expected_event_specs
    }
    if tuple(str(row.get("event_spec_id", "")) for row in manifest) != tuple(
        sorted(expected_group_by_event)
    ):
        return False
    for row in manifest:
        event_spec_id = str(row.get("event_spec_id", ""))
        raw_member_ids = row.get("member_ids")
        if not isinstance(raw_member_ids, (list, tuple)):
            return False
        member_ids = tuple(str(member_id) for member_id in raw_member_ids)
        if member_ids != expected_member_ids:
            return False
        try:
            expected_digest = build_strategy_universe(
                universe_version_id="certification:expected",
                strategy_group_id=expected_group_by_event[event_spec_id],
                event_spec_id=event_spec_id,
                universe_version=1,
                exchange_instrument_ids=member_ids,
                installed_at_ms=1,
            ).semantic_digest
        except (KeyError, TypeError, ValueError):
            return False
        if str(row.get("semantic_digest", "")) != expected_digest:
            return False
    return True


def _closure_ticket_manifest(
    row: dict[str, object] | None,
) -> dict[str, object] | None:
    if row is None:
        return None
    order_residue_count = sum(
        row[key] is not None
        for key in (
            "initial_stop_exchange_order_id",
            "active_stop_exchange_order_id",
            "tp1_exchange_order_id",
            "pending_replaced_stop_exchange_order_id",
            "pending_cancel_exchange_order_id",
        )
    )
    return {
        "ticket_id": str(row["ticket_id"]),
        "aggregate_status": str(row["aggregate_status"]),
        "aggregate_version": int(str(row["aggregate_version"])),
        "last_event_sequence": int(str(row["last_event_sequence"])),
        "netting_domain_key": str(row["netting_domain_key"]),
        "position_quantity": _canonical_decimal(row["position_qty"]),
        "protected_quantity": _canonical_decimal(row["protected_qty"]),
        "owned_order_residue_count": order_residue_count,
        "unresolved_command_count": int(str(row["unresolved_command_count"])),
        "open_incident_count": int(str(row["open_incident_count"])),
        "budget_reservation_status": (
            None
            if row["budget_reservation_status"] is None
            else str(row["budget_reservation_status"])
        ),
        "account_capacity_released": bool(row["account_capacity_released"]),
        "netting_domain_released": row["active_netting_domain_key"] is None,
        "review_presence": bool(row["review_presence"]),
    }


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
    parser.add_argument(
        "--closure-ticket-id",
        help="Exact zero-exposure Settlement/Review pending Ticket for closure-only certification.",
    )
    return parser


async def _certify(
    database_url: str,
    *,
    require_flat: bool,
    closure_ticket_id: str | None = None,
    now_ms: int | None = None,
) -> dict[str, object]:
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    normalized_closure_ticket_id = (
        None if closure_ticket_id is None else closure_ticket_id.strip()
    )
    if closure_ticket_id is not None and not normalized_closure_ticket_id:
        raise ValueError("closure Ticket identity must be non-blank")
    if require_flat and normalized_closure_ticket_id is not None:
        raise ValueError("flat and closure-only certification are mutually exclusive")
    effective_now_ms = int(time.time() * 1_000) if now_ms is None else now_ms
    if effective_now_ms <= 0:
        raise ValueError("certification time must be positive")
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
            registry_metadata_hash = str(
                (
                    await connection.execute(
                        text(
                            "SELECT metadata_value FROM brc_schema_metadata "
                            "WHERE metadata_key = 'registry_semantic_hash'"
                        )
                    )
                ).scalar_one_or_none()
                or ""
            )
            runtime_profile_row = (
                await connection.execute(
                    text(
                        "SELECT runtime_profile_id, account_id "
                        "FROM brc_runtime_profiles "
                        "WHERE runtime_profile_id = 'tiny-live-v1'"
                    )
                )
            ).mappings().one_or_none()
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
            universe_counts = (
                await connection.execute(
                    text(
                        """
                        WITH certification_targets AS (
                            SELECT DISTINCT
                                   scope.runtime_profile_id,
                                   scope.exchange_instrument_id
                              FROM brc_runtime_scopes_current scope
                              JOIN brc_strategy_universe_versions version
                                ON version.universe_version_id =
                                   scope.universe_version_id
                              JOIN brc_strategy_universe_members member
                                ON member.universe_version_id =
                                   scope.universe_version_id
                               AND member.exchange_instrument_id =
                                   scope.exchange_instrument_id
                             WHERE scope.lifecycle_state IN ('active', 'warming')
                               AND version.lifecycle_state IN ('active', 'warming')
                             ORDER BY scope.runtime_profile_id,
                                      scope.exchange_instrument_id
                             LIMIT 70
                        ),
                        violations AS (
                            SELECT member.universe_version_id,
                                   member.exchange_instrument_id
                              FROM brc_strategy_universe_members member
                              LEFT JOIN brc_runtime_scopes_current scope
                                ON scope.universe_version_id =
                                   member.universe_version_id
                               AND scope.exchange_instrument_id =
                                   member.exchange_instrument_id
                             WHERE scope.runtime_scope_id IS NULL
                            UNION ALL
                            SELECT scope.universe_version_id,
                                   scope.exchange_instrument_id
                              FROM brc_runtime_scopes_current scope
                              LEFT JOIN brc_strategy_universe_versions version
                                ON version.universe_version_id =
                                   scope.universe_version_id
                              LEFT JOIN brc_strategy_universe_members member
                                ON member.universe_version_id =
                                   scope.universe_version_id
                               AND member.exchange_instrument_id =
                                   scope.exchange_instrument_id
                             WHERE version.universe_version_id IS NULL
                                OR member.universe_version_id IS NULL
                                OR scope.event_spec_id <> version.event_spec_id
                                OR scope.universe_semantic_digest <>
                                   version.semantic_digest
                                OR scope.lifecycle_state <>
                                   version.lifecycle_state
                            UNION ALL
                            SELECT current.universe_version_id,
                                   current.event_spec_id
                              FROM brc_strategy_universe_current current
                              LEFT JOIN brc_strategy_universe_versions version
                                ON version.universe_version_id =
                                   current.universe_version_id
                             WHERE version.universe_version_id IS NULL
                                OR version.event_spec_id <>
                                   current.event_spec_id
                                OR version.semantic_digest <>
                                   current.semantic_digest
                                OR version.lifecycle_state <> 'active'
                                OR current.lifecycle_state <> 'active'
                            UNION ALL
                            SELECT version.universe_version_id,
                                   version.event_spec_id
                              FROM brc_strategy_universe_versions version
                              LEFT JOIN brc_strategy_universe_current current
                                ON current.universe_version_id =
                                   version.universe_version_id
                             WHERE version.lifecycle_state = 'active'
                               AND current.universe_version_id IS NULL
                        )
                        SELECT
                            (SELECT count(*)
                               FROM brc_strategy_universe_versions),
                            (SELECT count(*)
                               FROM brc_strategy_universe_current),
                            (SELECT count(*)
                               FROM brc_strategy_universe_members),
                            (SELECT count(*)
                               FROM brc_runtime_scopes_current),
                            (SELECT count(*) FROM violations),
                            (SELECT count(*) FROM brc_runtime_scopes_current
                              WHERE lifecycle_state = 'active'),
                            (SELECT count(*) FROM brc_runtime_scopes_current
                              WHERE lifecycle_state = 'warming'),
                            (SELECT count(*) FROM brc_runtime_scopes_current
                              WHERE lifecycle_state = 'retired'),
                            (SELECT count(*)
                               FROM certification_targets target
                               JOIN brc_instrument_certification_current certification
                                 ON certification.runtime_profile_id =
                                    target.runtime_profile_id
                                AND certification.exchange_instrument_id =
                                    target.exchange_instrument_id
                              WHERE certification.status =
                                    'temporarily_unavailable')
                        """
                    )
                )
            ).one()
            active_universe_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT current.event_spec_id,
                               current.universe_version_id,
                               current.semantic_digest,
                               array_agg(
                                   member.exchange_instrument_id
                                   ORDER BY member.exchange_instrument_id
                               ) AS member_ids
                          FROM brc_strategy_universe_current current
                          JOIN brc_strategy_universe_versions version
                            ON version.universe_version_id =
                               current.universe_version_id
                          JOIN brc_strategy_universe_members member
                            ON member.universe_version_id =
                               current.universe_version_id
                         WHERE current.lifecycle_state = 'active'
                           AND version.lifecycle_state = 'active'
                         GROUP BY current.event_spec_id,
                                  current.universe_version_id,
                                  current.semantic_digest
                         ORDER BY current.event_spec_id
                        """
                    )
                )
            ).mappings().all()
            warming_universe_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT version.event_spec_id,
                               version.universe_version_id,
                               version.semantic_digest,
                               array_agg(
                                   member.exchange_instrument_id
                                   ORDER BY member.exchange_instrument_id
                               ) AS member_ids
                          FROM brc_strategy_universe_versions version
                          JOIN brc_strategy_universe_members member
                            ON member.universe_version_id =
                               version.universe_version_id
                         WHERE version.lifecycle_state = 'warming'
                         GROUP BY version.event_spec_id,
                                  version.universe_version_id,
                                  version.semantic_digest
                         ORDER BY version.event_spec_id
                        """
                    )
                )
            ).mappings().all()
            shadow_pending_count = int(
                (
                    await connection.execute(
                        text(
                            "SELECT count(*) FROM brc_shadow_outcomes_current "
                            "WHERE status IN ('pending', 'claimed')"
                        )
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
                               family_ticket_limits,
                               max_ticket_stop_risk_fraction,
                               max_gross_stop_risk_fraction,
                               max_ticket_initial_margin_fraction,
                               max_gross_initial_margin_utilization,
                               directional_stop_risk_limit_fraction,
                               min_materialization_ratio,
                               max_leverage,
                               supported_margin_mode,
                               post_stop_stress_multiple,
                               max_post_fill_stop_risk_overrun_fraction,
                               scope
                          FROM brc_owner_policy_current
                        """
                    )
                )
            ).mappings().one_or_none()
            owner_policy_event_versions = tuple(
                int(value)
                for value in (
                    await connection.execute(
                        text(
                            "SELECT policy_version FROM brc_owner_policy_events "
                            "WHERE owner_policy_id = :owner_policy_id "
                            "ORDER BY policy_version"
                        ),
                        {"owner_policy_id": OWNER_POLICY_ID},
                    )
                ).scalars()
            )
            entry_gate_counts = (
                await connection.execute(
                    text(
                        """
                        WITH active_members AS (
                            SELECT DISTINCT scope.runtime_profile_id,
                                   scope.exchange_instrument_id
                              FROM brc_runtime_scopes_current scope
                              JOIN brc_strategy_universe_current current
                                ON current.universe_version_id = scope.universe_version_id
                             WHERE scope.lifecycle_state = 'active'
                        )
                        SELECT
                            (SELECT count(*) FROM brc_strategy_universe_current),
                            (SELECT count(*) FROM brc_runtime_scopes_current
                              WHERE lifecycle_state = 'active'),
                            (SELECT count(*) FROM brc_runtime_scopes_current
                              WHERE lifecycle_state = 'warming'),
                            (SELECT count(*) FROM active_members),
                            (SELECT count(*)
                               FROM active_members member
                               JOIN brc_instrument_certification_current certification
                                 ON certification.runtime_profile_id = member.runtime_profile_id
                                AND certification.exchange_instrument_id = member.exchange_instrument_id
                              WHERE certification.status = 'eligible'
                                AND certification.blocker_code IS NULL
                                AND certification.valid_until_ms > :now_ms)
                        """
                    ),
                    {"now_ms": effective_now_ms},
                )
            ).one()
            certification_batch_row = (
                await connection.execute(
                    text(
                        """
                        SELECT batch.certification_batch_id,
                               batch.runtime_profile_id,
                               batch.target_commit,
                               batch.target_schema_revision,
                               batch.target_seed_identity,
                               batch.owner_policy_id,
                               batch.owner_policy_version,
                               batch.manifest_digest,
                               batch.status,
                               batch.completed_at_ms,
                               batch.valid_until_ms,
                               count(member.exchange_instrument_id) AS member_count,
                               count(*) FILTER (
                                   WHERE member.status = 'eligible'
                               ) AS eligible_member_count
                          FROM brc_instrument_certification_batches batch
                          JOIN brc_instrument_certification_batch_members member
                            ON member.certification_batch_id =
                               batch.certification_batch_id
                         WHERE batch.status = 'completed'
                           AND batch.valid_until_ms > :now_ms
                         GROUP BY batch.certification_batch_id
                         ORDER BY batch.completed_at_ms DESC,
                                  batch.certification_batch_id
                         LIMIT 1
                        """
                    ),
                    {"now_ms": effective_now_ms},
                )
            ).mappings().one_or_none()
            compatible_batch_row = (
                await connection.execute(
                    text(
                        """
                        SELECT batch.certification_batch_id,
                               batch.runtime_profile_id,
                               batch.target_commit,
                               batch.target_schema_revision,
                               batch.target_seed_identity,
                               batch.owner_policy_id,
                               batch.owner_policy_version,
                               batch.manifest_digest,
                               batch.status,
                               count(member.exchange_instrument_id) AS member_count
                          FROM brc_instrument_certification_batches batch
                          JOIN brc_instrument_certification_batch_members member
                            ON member.certification_batch_id =
                               batch.certification_batch_id
                         WHERE batch.status IN ('pending', 'completed')
                         GROUP BY batch.certification_batch_id
                         ORDER BY batch.started_at_ms DESC,
                                  batch.certification_batch_id
                         LIMIT 1
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
                            "('prepared', 'claimed', 'dispatch_started', "
                            "'outcome_unknown')"
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
            closure_ticket_row = None
            closure_active_ticket_count = 0
            if normalized_closure_ticket_id is not None:
                closure_active_ticket_count = int(
                    (
                        await connection.execute(
                            text(
                                "SELECT count(*) FROM brc_trade_tickets "
                                "WHERE terminal_at_ms IS NULL"
                            )
                        )
                    ).scalar_one()
                )
                closure_ticket_row = (
                    await connection.execute(
                        text(
                            """
                            SELECT ticket.ticket_id,
                                   ticket.netting_domain_key,
                                   ticket.active_netting_domain_key,
                                   aggregate_current.status AS aggregate_status,
                                   aggregate_current.version AS aggregate_version,
                                   aggregate_current.last_event_sequence,
                                   aggregate_current.position_qty,
                                   aggregate_current.protected_qty,
                                   aggregate_current.initial_stop_exchange_order_id,
                                   aggregate_current.active_stop_exchange_order_id,
                                   aggregate_current.tp1_exchange_order_id,
                                   aggregate_current.pending_replaced_stop_exchange_order_id,
                                   aggregate_current.pending_cancel_exchange_order_id,
                                   aggregate_current.review_id,
                                   reservation.status AS budget_reservation_status,
                                   reservation.released_at_ms AS budget_released_at_ms,
                                   EXISTS(
                                       SELECT 1
                                         FROM brc_account_exposure_current exposure
                                        WHERE exposure.venue_id = ticket.venue_id
                                          AND exposure.account_id = ticket.account_id
                                          AND exposure.gross_notional = 0
                                          AND exposure.gross_risk_at_stop = 0
                                          AND exposure.active_ticket_count = 0
                                   ) AS account_capacity_released,
                                   (SELECT count(*)
                                      FROM brc_exchange_commands command
                                     WHERE command.ticket_id = ticket.ticket_id
                                       AND command.status IN (
                                           'prepared', 'claimed',
                                           'dispatch_started', 'outcome_unknown'
                                       )) AS unresolved_command_count,
                                   (SELECT count(*)
                                      FROM brc_runtime_incidents incident
                                     WHERE incident.ticket_id = ticket.ticket_id
                                       AND incident.status <> 'resolved'
                                   ) AS open_incident_count,
                                   EXISTS(
                                       SELECT 1 FROM brc_trade_reviews review
                                        WHERE review.ticket_id = ticket.ticket_id
                                   ) AS review_presence
                              FROM brc_trade_tickets ticket
                              JOIN brc_trade_aggregates aggregate_current
                                ON aggregate_current.ticket_id = ticket.ticket_id
                              LEFT JOIN brc_budget_reservations reservation
                                ON reservation.ticket_id = ticket.ticket_id
                             WHERE ticket.ticket_id = :ticket_id
                               AND ticket.terminal_at_ms IS NULL
                            """
                        ),
                        {"ticket_id": normalized_closure_ticket_id},
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
    strategy_universe = {
        "version_count": int(universe_counts[0]),
        "current_count": int(universe_counts[1]),
        "member_count": int(universe_counts[2]),
        "scope_count": int(universe_counts[3]),
        "integrity_violation_count": int(universe_counts[4]),
        "scope_lifecycle_counts": {
            "active": int(universe_counts[5]),
            "warming": int(universe_counts[6]),
            "retired": int(universe_counts[7]),
        },
        "temporarily_unavailable_certification_count": int(universe_counts[8]),
        "shadow_pending_count": shadow_pending_count,
    }
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
            if key != "scope"
        }
    )
    closure_ticket = _closure_ticket_manifest(
        None if closure_ticket_row is None else dict(closure_ticket_row),
    )
    policy_is_dynamic = owner_policy_row is not None and all(
        (
            owner_policy_row["owner_policy_id"] == OWNER_POLICY_ID,
            int(owner_policy_row["policy_version"]) > 0,
            owner_policy_row["enabled"] is True,
            isinstance(owner_policy_row["new_entry_submit_enabled"], bool),
            int(owner_policy_row["max_concurrent_tickets"])
            == DYNAMIC_POLICY.max_concurrent_tickets,
            owner_policy_row["family_ticket_limits"]
            == DYNAMIC_POLICY.family_ticket_limits.model_dump(),
            Decimal(str(owner_policy_row["max_ticket_stop_risk_fraction"]))
            == DYNAMIC_POLICY.max_ticket_stop_risk_fraction,
            Decimal(str(owner_policy_row["max_gross_stop_risk_fraction"]))
            == DYNAMIC_POLICY.max_gross_stop_risk_fraction,
            Decimal(
                str(owner_policy_row["max_ticket_initial_margin_fraction"])
            )
            == DYNAMIC_POLICY.max_ticket_initial_margin_fraction,
            Decimal(
                str(owner_policy_row["max_gross_initial_margin_utilization"])
            )
            == DYNAMIC_POLICY.max_gross_initial_margin_utilization,
            Decimal(
                str(owner_policy_row["directional_stop_risk_limit_fraction"])
            )
            == DYNAMIC_POLICY.directional_stop_risk_limit_fraction,
            Decimal(str(owner_policy_row["min_materialization_ratio"]))
            == DYNAMIC_POLICY.min_materialization_ratio,
            int(owner_policy_row["max_leverage"]) == DYNAMIC_POLICY.max_leverage,
            owner_policy_row["supported_margin_mode"]
            == DYNAMIC_POLICY.supported_margin_mode,
            Decimal(
                str(owner_policy_row["post_stop_stress_multiple"])
            )
            == DYNAMIC_POLICY.post_stop_stress_multiple,
            Decimal(
                str(owner_policy_row["max_post_fill_stop_risk_overrun_fraction"])
            )
            == DYNAMIC_POLICY.max_post_fill_stop_risk_overrun_fraction,
        )
    )
    policy_lineage_pass = bool(
        owner_policy_row is not None
        and owner_policy_event_versions
        and owner_policy_event_versions[0] == 1
        and owner_policy_event_versions
        == tuple(
            range(
                owner_policy_event_versions[0],
                int(owner_policy_row["policy_version"]) + 1,
            )
        )
        and owner_policy_event_versions[-1]
        == int(owner_policy_row["policy_version"])
    )
    capabilities_are_current = (
        set(capabilities) == {"exchange_commands", "strategy_signal_ingest"}
        and capabilities["strategy_signal_ingest"] is True
        and isinstance(capabilities["exchange_commands"], bool)
    )
    database_integrity_pass = (
        revision == EXPECTED_ALEMBIC_REVISION
        and runtime_identity.get("schema_revision") == EXPECTED_ALEMBIC_REVISION
        and set(runtime_identity)
        == {"runtime_commit", "schema_revision", "seed_identity"}
        and actual_tables == expected_tables
        and strategy_universe["integrity_violation_count"] == 0
        and capabilities_are_current
        and policy_is_dynamic
        and policy_lineage_pass
        and integrity_orphans == 0
        and legacy_execution_tables == 0
        and unresolved_commands == 0
        and open_incidents == 0
    )
    registered_contracts = registered_strategy_contracts()
    expected_event_specs = tuple(
        sorted(
            (
                (contract.strategy_group_id, contract.event_spec_id)
                for contract in registered_contracts
            ),
            key=lambda identity: identity[1],
        )
    )
    expected_event_spec_ids = tuple(
        event_spec_id for _strategy_group_id, event_spec_id in expected_event_specs
    )
    expected_strategy_group_by_event = {
        event_spec_id: strategy_group_id
        for strategy_group_id, event_spec_id in expected_event_specs
    }
    expected_registry_hash = build_registry_semantic_hash(
        registered_contracts
    )
    registry_identity = {
        "status": (
            "pass"
            if registry_metadata_hash == expected_registry_hash
            else "fail"
        ),
        "expected_semantic_hash": expected_registry_hash,
        "metadata_semantic_hash": registry_metadata_hash,
    }
    policy_scope = None if owner_policy_row is None else owner_policy_row["scope"]
    policy_events = (
        ()
        if not isinstance(policy_scope, dict)
        or not isinstance(policy_scope.get("allowed_event_spec_ids"), list)
        else tuple(sorted(str(value) for value in policy_scope["allowed_event_spec_ids"]))
    )
    active_current_count = int(entry_gate_counts[0])
    active_scope_count = int(entry_gate_counts[1])
    warming_scope_count = int(entry_gate_counts[2])
    active_member_count = int(entry_gate_counts[3])
    eligible_fresh_certification_count = int(entry_gate_counts[4])
    expected_manifest_digest = build_certification_manifest_digest(
        APPROVED_FIRST_BATCH_INSTRUMENT_IDS
    )
    expected_member_ids = tuple(sorted(APPROVED_FIRST_BATCH_INSTRUMENT_IDS))
    runtime_profile_id = (
        None
        if not isinstance(policy_scope, dict)
        else policy_scope.get("runtime_profile_id")
    )
    active_universe_manifest = [
        {
            "event_spec_id": str(row["event_spec_id"]),
            "universe_version_id": str(row["universe_version_id"]),
            "semantic_digest": str(row["semantic_digest"]),
            "member_ids": list(row["member_ids"]),
        }
        for row in active_universe_rows
    ]
    universe_identity_pass = _universe_manifest_matches(
        active_universe_manifest,
        expected_event_specs=expected_event_specs,
        expected_member_ids=expected_member_ids,
    )
    warming_universe_manifest = [
        {
            "event_spec_id": str(row["event_spec_id"]),
            "universe_version_id": str(row["universe_version_id"]),
            "semantic_digest": str(row["semantic_digest"]),
            "member_ids": list(row["member_ids"]),
        }
        for row in warming_universe_rows
    ]
    compatible_batch_pass = bool(
        compatible_batch_row is not None
        and compatible_batch_row["runtime_profile_id"] == runtime_profile_id
        and compatible_batch_row["target_commit"]
        == runtime_identity.get("runtime_commit")
        and compatible_batch_row["target_schema_revision"]
        == runtime_identity.get("schema_revision")
        and compatible_batch_row["target_seed_identity"]
        == runtime_identity.get("seed_identity")
        and compatible_batch_row["owner_policy_id"] == OWNER_POLICY_ID
        and owner_policy_row is not None
        and int(compatible_batch_row["owner_policy_version"]) == 4
        and int(owner_policy_row["policy_version"]) == 4
        and owner_policy_row["new_entry_submit_enabled"] is False
        and compatible_batch_row["manifest_digest"] == expected_manifest_digest
        and int(compatible_batch_row["member_count"])
        == len(APPROVED_FIRST_BATCH_INSTRUMENT_IDS)
    )
    compatible_active_universe_pass = _universe_manifest_matches(
        active_universe_manifest,
        expected_event_specs=_COMPATIBLE_SOURCE_EVENT_SPECS,
        expected_member_ids=expected_member_ids,
    )
    first_vnext_event_spec_id = APPROVED_UNIVERSE_EVENT_SPECS[0][1]
    compatible_warming_universe_pass = _universe_manifest_matches(
        warming_universe_manifest,
        expected_event_specs=(
            (
                expected_strategy_group_by_event[first_vnext_event_spec_id],
                first_vnext_event_spec_id,
            ),
        ),
        expected_member_ids=expected_member_ids,
    )
    compatible_universe_identity_pass = bool(
        compatible_active_universe_pass
        and compatible_warming_universe_pass
        and compatible_batch_pass
    )
    deployment_stage = (
        "warming"
        if compatible_universe_identity_pass
        else "active"
        if universe_identity_pass
        else "invalid"
    )
    strategy_universe["identity_status"] = (
        "pass"
        if compatible_universe_identity_pass or universe_identity_pass
        else "fail"
    )
    strategy_universe["semantic_digest_status"] = (
        "pass"
        if compatible_universe_identity_pass or universe_identity_pass
        else "fail"
    )
    strategy_universe["deployment_stage"] = deployment_stage
    strategy_universe["active_manifest"] = active_universe_manifest
    strategy_universe["warming_manifest"] = warming_universe_manifest
    strategy_universe["approved_vnext_event_spec_ids"] = list(
        expected_event_spec_ids
    )
    certification_batch_pass = bool(
        certification_batch_row is not None
        and certification_batch_row["runtime_profile_id"] == runtime_profile_id
        and certification_batch_row["target_commit"]
        == runtime_identity.get("runtime_commit")
        and certification_batch_row["target_schema_revision"]
        == runtime_identity.get("schema_revision")
        and certification_batch_row["target_seed_identity"]
        == runtime_identity.get("seed_identity")
        and certification_batch_row["owner_policy_id"] == OWNER_POLICY_ID
        and owner_policy_row is not None
        and _certification_batch_policy_stage_matches(
            batch_policy_version=int(
                certification_batch_row["owner_policy_version"]
            ),
            current_policy_version=int(owner_policy_row["policy_version"]),
            new_entry_submit_enabled=bool(
                owner_policy_row["new_entry_submit_enabled"]
            ),
        )
        and certification_batch_row["manifest_digest"]
        == expected_manifest_digest
        and certification_batch_row["status"] == "completed"
        and int(certification_batch_row["member_count"])
        == len(APPROVED_FIRST_BATCH_INSTRUMENT_IDS)
        and int(certification_batch_row["eligible_member_count"])
        == len(APPROVED_FIRST_BATCH_INSTRUMENT_IDS)
    )
    universe_bootstrap_pass = (
        database_integrity_pass
        and active_current_count == 6
        and active_scope_count == 42
        and warming_scope_count == 0
        and active_member_count == 7
        and certification_batch_pass
        and policy_events == expected_event_spec_ids
    )
    flatness_pass = (
        non_flat_positions == 0
        and active_ticket_domains == 0
        and unresolved_commands == 0
        and open_incidents == 0
        and active_budget_reservations == 0
    )
    entry_promotion_pass = (
        universe_bootstrap_pass
        and flatness_pass
        and owner_policy_row is not None
        and owner_policy_row["new_entry_submit_enabled"] is False
        and capabilities.get("exchange_commands") is False
    )
    expected_seed_identity = ""
    if runtime_profile_row is not None:
        expected_seed_identity = build_runtime_seed_identity(
            RuntimeAuthoritySeedRequest(
                account_id=str(runtime_profile_row["account_id"]),
                runtime_commit=str(runtime_identity.get("runtime_commit", "missing")),
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1,
            )
        )
    actual_seed_identity = str(runtime_identity.get("seed_identity", ""))
    seed_identity = {
        "status": (
            "pass"
            if expected_seed_identity == actual_seed_identity
            else "fail"
        ),
        "expected": expected_seed_identity,
        "actual": actual_seed_identity,
    }
    portfolio_admission_postflight_pass = bool(
        compatible_universe_identity_pass
        and flatness_pass
        and owner_policy_row is not None
        and int(owner_policy_row["policy_version"]) == 4
        and owner_policy_row["new_entry_submit_enabled"] is False
        and registry_identity["status"] == "pass"
        and seed_identity["status"] == "pass"
        and runtime_identity.get("schema_revision") == EXPECTED_ALEMBIC_REVISION
    )
    closure_is_valid = (
        normalized_closure_ticket_id is None
        or (
            closure_active_ticket_count == 1
            and closure_ticket is not None
            and closure_ticket["ticket_id"] == normalized_closure_ticket_id
            and closure_ticket["aggregate_status"]
            in {"settlement_pending", "review_pending"}
            and closure_ticket["position_quantity"] == "0"
            and closure_ticket["protected_quantity"] == "0"
            and closure_ticket["owned_order_residue_count"] == 0
            and closure_ticket["unresolved_command_count"] == 0
            and closure_ticket["open_incident_count"] == 0
            and closure_ticket["budget_reservation_status"] == "released"
            and closure_ticket["account_capacity_released"] is True
            and closure_ticket["netting_domain_released"] is True
        )
    )
    passed = (
        database_integrity_pass
        and closure_is_valid
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
        "strategy_universe": strategy_universe,
        "registry_identity": registry_identity,
        "seed_identity": seed_identity,
        "portfolio_admission_postflight_pass": (
            portfolio_admission_postflight_pass
        ),
        "database_integrity_pass": database_integrity_pass,
        "flatness_pass": flatness_pass,
        "universe_bootstrap_pass": universe_bootstrap_pass,
        "entry_promotion_pass": entry_promotion_pass,
        "entry_promotion_counts": {
            "active_current_universes": active_current_count,
            "active_scopes": active_scope_count,
            "warming_scopes": warming_scope_count,
            "active_instruments": active_member_count,
            "eligible_fresh_certifications": eligible_fresh_certification_count,
        },
        "certification_batch": (
            None
            if certification_batch_row is None
            else dict(certification_batch_row)
        ),
        "compatible_certification_batch": (
            None if compatible_batch_row is None else dict(compatible_batch_row)
        ),
        "compatible_certification_batch_pass": compatible_batch_pass,
        "certification_batch_pass": certification_batch_pass,
        "capabilities": capabilities,
        "owner_policy": owner_policy,
        "owner_policy_lineage_pass": policy_lineage_pass,
        "release_counts": release_counts,
        "active_counts": active_counts,
        "owner_projection": owner_projection,
        "closure_ticket": closure_ticket,
        "require_flat": require_flat,
        "closure_ticket_id": normalized_closure_ticket_id,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = asyncio.run(
        _certify(
            str(args.database_url or "").strip(),
            require_flat=args.require_flat,
            closure_ticket_id=args.closure_ticket_id,
        )
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
