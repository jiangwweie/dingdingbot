from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from scripts.trading_kernel.verify_schema import (
    _verify_compatible_source,
    _verify_preservation,
)
from tests.trading_kernel.integration.test_portfolio_admission_observability_migration import (
    SOURCE_REVISION,
    _database_url,
    _prepare_production_shaped_0002,
)
from tests.trading_kernel.integration.test_sor_v3_compatible_migration import (
    HEAD_REVISION,
    _run_migration,
    compatible_migration_engine,
)

__all__ = ["compatible_migration_engine"]


async def test_mig_007_nonflat_0002_is_blocked_before_migration(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_trade_tickets SET terminal_at_ms = NULL, "
                "status = 'protected' WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )

    source = await _verify_compatible_source(_database_url(engine), SOURCE_REVISION)

    assert source["status"] == "fail"
    assert source["migration_gate"]["active_tickets"] == 1
    async with engine.connect() as connection:
        assert await connection.scalar(
            sa.text("SELECT version_num FROM alembic_version")
        ) == SOURCE_REVISION


async def test_mig_008_manifest_covers_every_0002_table_column_and_value(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    database_url = _database_url(engine)
    async with engine.connect() as connection:
        source_shape = await connection.run_sync(
            lambda sync: {
                table_name: tuple(
                    column["name"]
                    for column in sa.inspect(sync).get_columns(table_name)
                )
                for table_name in sa.inspect(sync).get_table_names()
                if table_name != "alembic_version"
            }
        )

    source = await _verify_compatible_source(database_url, SOURCE_REVISION)
    manifest = source["preservation_manifest"]
    table_entries = {entry["table"]: entry for entry in manifest["tables"]}

    assert source["status"] == "pass", source
    assert set(table_entries) == set(source_shape)
    for table_name, columns in source_shape.items():
        entry = table_entries[table_name]
        assert tuple(entry["columns"]) == columns
        assert all(
            len(row["value_digests"]) == len(columns)
            for row in entry["rows"]
        )

    result = _run_migration(database_url, "upgrade", HEAD_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]
    target = await _verify_preservation(
        database_url,
        source_revision=SOURCE_REVISION,
        expected_digest=str(manifest["digest"]),
    )

    source_digests = {
        entry["table"]: entry["digest"] for entry in manifest["tables"]
    }
    target_digests = {
        entry["table"]: entry["digest"]
        for entry in target["preservation_manifest"]["tables"]
    }
    assert target["status"] == "pass", {
        table_name: (source_digests[table_name], target_digests[table_name])
        for table_name in source_digests
        if source_digests[table_name] != target_digests[table_name]
    }
    assert target["preservation_manifest"] == manifest


async def test_mig_008_one_changed_0002_value_breaks_equivalence(
    compatible_migration_engine: AsyncEngine,
) -> None:
    engine = compatible_migration_engine
    await _prepare_production_shaped_0002(engine)
    await _install_source_runtime_identity(engine)
    database_url = _database_url(engine)
    source = await _verify_compatible_source(database_url, SOURCE_REVISION)
    digest = str(source["preservation_manifest"]["digest"])
    result = _run_migration(database_url, "upgrade", HEAD_REVISION)
    assert result.returncode == 0, result.stderr[-4000:]
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_trade_tickets SET decision_digest = "
                "'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' "
                "WHERE ticket_id = 'ticket-v3-terminal'"
            )
        )

    target = await _verify_preservation(
        database_url,
        source_revision=SOURCE_REVISION,
        expected_digest=digest,
    )

    assert target["status"] == "fail"
    assert target["preservation_manifest"]["digest"] != digest


async def _install_source_runtime_identity(engine: AsyncEngine) -> None:
    values = {
        "runtime_commit": "b" * 40,
        "schema_revision": SOURCE_REVISION,
        "seed_identity": "sha256:" + "c" * 64,
    }
    async with engine.begin() as connection:
        for key, value in values.items():
            await connection.execute(
                sa.text(
                    "INSERT INTO brc_schema_metadata "
                    "(metadata_key, metadata_value, updated_at_ms) "
                    "VALUES (:key, :value, 1000) "
                    "ON CONFLICT (metadata_key) DO UPDATE "
                    "SET metadata_value = EXCLUDED.metadata_value, "
                    "updated_at_ms = EXCLUDED.updated_at_ms"
                ),
                {"key": key, "value": value},
            )
