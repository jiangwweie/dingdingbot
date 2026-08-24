from __future__ import annotations

import pytest

from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
)


@pytest.mark.asyncio
async def test_repository_namespaces_selection_materialization_and_observation_leases(
    head_template_engine,
) -> None:
    async with head_template_engine.connect() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        columns = await connection.run_sync(
            lambda sync: {
                table: {column["name"] for column in __import__("sqlalchemy").inspect(sync).get_columns(table)}
                for table in (
                    "brc_instrument_selection_jobs_current",
                    "brc_strategy_universe_materialization_generations",
                    "brc_runtime_scopes_current",
                )
            }
        )

    assert {"lease_owner", "lease_expires_at_ms"} <= columns[
        "brc_instrument_selection_jobs_current"
    ]
    assert {"lease_owner", "lease_expires_at_ms"} <= columns[
        "brc_strategy_universe_materialization_generations"
    ]
    assert {"lease_owner", "lease_expires_at_ms"} <= columns[
        "brc_runtime_scopes_current"
    ]
    assert {
        repository.lease_namespace("selection"),
        repository.lease_namespace("materialization"),
        repository.lease_namespace("observation"),
    } == {
        "selection_job",
        "materialization_generation",
        "runtime_scope_observation",
    }
