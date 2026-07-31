#!/usr/bin/env python3
"""Verify the exact clean trading-kernel PostgreSQL table allowlist."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from migrations.trading_kernel import v4_schema
from src.trading_kernel.infrastructure.pg_models import metadata
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)

SCHEMA = "brc.trading_kernel.schema_verification.v1"
PRESERVATION_SCHEMA = "brc.trading_kernel.v4_preservation.v1"
EXPECTED_ALEMBIC_REVISION = CURRENT_SCHEMA_REVISION
COMPATIBLE_SOURCE_REVISION = "0001_trading_kernel_baseline_v4"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    parser.add_argument(
        "--compatible-source-revision",
        help="Verify an exact flat source revision and emit its v4 preservation manifest.",
    )
    parser.add_argument(
        "--preserve-source-revision",
        help="Recompute one source-revision manifest after migration.",
    )
    parser.add_argument(
        "--expected-preservation-digest",
        help="Expected sha256 digest for post-migration preservation verification.",
    )
    return parser


async def _verify(database_url: str) -> dict[str, object]:
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
                               AND relname LIKE 'brc\\_%' ESCAPE '\\'
                             ORDER BY relname
                            """
                        )
                    )
                ).scalars()
            }
            await connection.rollback()
    finally:
        await engine.dispose()

    expected_tables = set(metadata.tables)
    missing_tables = sorted(expected_tables - actual_tables)
    unexpected_tables = sorted(actual_tables - expected_tables)
    passed = (
        revision == EXPECTED_ALEMBIC_REVISION
        and not missing_tables
        and not unexpected_tables
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "expected_table_count": len(expected_tables),
        "actual_table_count": len(actual_tables),
        "missing_tables": missing_tables,
        "unexpected_tables": unexpected_tables,
    }


async def _verify_compatible_source(
    database_url: str,
    source_revision: str,
) -> dict[str, object]:
    if source_revision != COMPATIBLE_SOURCE_REVISION:
        raise ValueError("compatible source must be the exact v4 revision")
    engine = _create_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = await _alembic_revision(connection)
            shape = await _verify_exact_metadata_shape(
                connection,
                expected_metadata=v4_schema.metadata,
            )
            migration_gate = await _migration_gate(connection)
            manifest = await _v4_preservation_manifest(connection)
            runtime_identity = await _runtime_identity(connection)
            await connection.rollback()
    finally:
        await engine.dispose()
    passed = bool(
        revision == source_revision
        and shape["status"] == "pass"
        and all(int(value) == 0 for value in migration_gate.values())
        and all(runtime_identity.values())
        and runtime_identity["schema_revision"] == source_revision
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "source_shape": shape,
        "runtime_identity": runtime_identity,
        "migration_gate": migration_gate,
        "preservation_manifest": manifest,
    }


async def _verify_preservation(
    database_url: str,
    *,
    source_revision: str,
    expected_digest: str,
) -> dict[str, object]:
    if source_revision != COMPATIBLE_SOURCE_REVISION:
        raise ValueError("preservation source must be the exact v4 revision")
    if not _is_sha256_identity(expected_digest):
        raise ValueError("expected preservation digest must be an exact sha256 identity")
    engine = _create_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = await _alembic_revision(connection)
            manifest = await _v4_preservation_manifest(connection)
            await connection.rollback()
    finally:
        await engine.dispose()
    passed = bool(
        revision == EXPECTED_ALEMBIC_REVISION
        and manifest["digest"] == expected_digest
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "source_revision": source_revision,
        "expected_preservation_digest": expected_digest,
        "preservation_manifest": manifest,
    }


def _create_engine(database_url: str):
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    return create_async_engine(database_url)


async def _alembic_revision(connection: AsyncConnection) -> str:
    return str(
        (
            await connection.execute(
                text("SELECT version_num FROM alembic_version")
            )
        ).scalar_one()
    )


async def _verify_exact_metadata_shape(
    connection: AsyncConnection,
    *,
    expected_metadata: sa.MetaData,
) -> dict[str, object]:
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
                       AND relname LIKE 'brc\\_%' ESCAPE '\\'
                     ORDER BY relname
                    """
                )
            )
        ).scalars()
    }
    expected_tables = set(expected_metadata.tables)
    missing_tables = sorted(expected_tables - actual_tables)
    unexpected_tables = sorted(actual_tables - expected_tables)
    column_mismatches: dict[str, dict[str, list[str]]] = {}
    for table in expected_metadata.sorted_tables:
        actual_columns = {
            str(name)
            for name in (
                await connection.execute(
                    text(
                        """
                        SELECT attname
                          FROM pg_catalog.pg_attribute
                         WHERE attrelid = to_regclass(:table_name)
                           AND attnum > 0
                           AND NOT attisdropped
                         ORDER BY attnum
                        """
                    ),
                    {"table_name": table.name},
                )
            ).scalars()
        }
        expected_columns = set(table.c.keys())
        if actual_columns != expected_columns:
            column_mismatches[table.name] = {
                "missing": sorted(expected_columns - actual_columns),
                "unexpected": sorted(actual_columns - expected_columns),
            }
    return {
        "status": (
            "pass"
            if not missing_tables and not unexpected_tables and not column_mismatches
            else "fail"
        ),
        "missing_tables": missing_tables,
        "unexpected_tables": unexpected_tables,
        "column_mismatches": column_mismatches,
    }


async def _migration_gate(connection: AsyncConnection) -> dict[str, int]:
    statements = {
        "active_tickets": (
            "SELECT count(*) FROM brc_trade_tickets WHERE terminal_at_ms IS NULL"
        ),
        "non_flat_positions": (
            "SELECT count(*) FROM brc_positions_current WHERE quantity <> 0"
        ),
        "active_reservations": (
            "SELECT count(*) FROM brc_budget_reservations WHERE status = 'active'"
        ),
        "active_domains": (
            "SELECT count(*) FROM brc_trade_tickets "
            "WHERE active_netting_domain_key IS NOT NULL"
        ),
        "unreviewed_terminal_tickets": (
            "SELECT count(*) FROM brc_trade_tickets ticket "
            "WHERE ticket.terminal_at_ms IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM brc_trade_reviews review "
            "WHERE review.ticket_id = ticket.ticket_id)"
        ),
        "unresolved_commands": (
            "SELECT count(*) FROM brc_exchange_commands "
            "WHERE status IN ('prepared', 'claimed', 'dispatch_started', "
            "'outcome_unknown')"
        ),
        "open_incidents": (
            "SELECT count(*) FROM brc_runtime_incidents WHERE status <> 'resolved'"
        ),
    }
    return {
        key: int((await connection.scalar(text(statement))) or 0)
        for key, statement in statements.items()
    }


async def _runtime_identity(connection: AsyncConnection) -> dict[str, str]:
    rows = (
        await connection.execute(
            text(
                "SELECT metadata_key, metadata_value FROM brc_schema_metadata "
                "WHERE metadata_key IN "
                "('runtime_commit', 'schema_revision', 'seed_identity')"
            )
        )
    ).mappings()
    values = {
        str(row["metadata_key"]): str(row["metadata_value"])
        for row in rows
    }
    return {
        "runtime_commit": values.get("runtime_commit", ""),
        "schema_revision": values.get("schema_revision", ""),
        "seed_identity": values.get("seed_identity", ""),
    }


async def _v4_preservation_manifest(
    connection: AsyncConnection,
) -> dict[str, object]:
    table_entries: list[dict[str, object]] = []
    total_rows = 0
    for table in v4_schema.metadata.sorted_tables:
        column_names = tuple(table.c.keys())
        rows = (
            await connection.execute(sa.select(*(table.c[name] for name in column_names)))
        ).mappings().all()
        canonical_rows = sorted(
            json.dumps(
                [_canonical_value(row[name]) for name in column_names],
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            for row in rows
        )
        table_payload = {
            "table": table.name,
            "columns": list(column_names),
            "rows": canonical_rows,
        }
        table_digest = _sha256_json(table_payload)
        table_entries.append(
            {
                "table": table.name,
                "row_count": len(canonical_rows),
                "digest": table_digest,
            }
        )
        total_rows += len(canonical_rows)
    manifest_payload = {
        "schema": PRESERVATION_SCHEMA,
        "source_revision": COMPATIBLE_SOURCE_REVISION,
        "tables": table_entries,
    }
    return {
        "schema": PRESERVATION_SCHEMA,
        "source_revision": COMPATIBLE_SOURCE_REVISION,
        "table_count": len(table_entries),
        "row_count": total_rows,
        "table_digests": table_entries,
        "digest": _sha256_json(manifest_payload),
    }


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"unsupported preservation value type: {type(value).__name__}")


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _is_sha256_identity(value: str) -> bool:
    return bool(
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = str(args.database_url or "").strip()
    if args.compatible_source_revision:
        if args.preserve_source_revision or args.expected_preservation_digest:
            raise ValueError("schema verification mode is ambiguous")
        payload = asyncio.run(
            _verify_compatible_source(
                database_url,
                str(args.compatible_source_revision),
            )
        )
    elif args.preserve_source_revision:
        if not args.expected_preservation_digest:
            raise ValueError("post-migration preservation requires an expected digest")
        payload = asyncio.run(
            _verify_preservation(
                database_url,
                source_revision=str(args.preserve_source_revision),
                expected_digest=str(args.expected_preservation_digest),
            )
        )
    elif args.expected_preservation_digest:
        raise ValueError("expected preservation digest requires a source revision")
    else:
        payload = asyncio.run(_verify(database_url))
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
