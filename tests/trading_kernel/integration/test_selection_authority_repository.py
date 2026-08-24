from __future__ import annotations

import pytest
import sqlalchemy as sa

from src.trading_kernel.domain.selection_authority import (
    AuthorityOutcome,
    ContinuitySourceKind,
    SelectionMode,
    SelectionSessionAuthority,
)
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
)
from src.trading_kernel.infrastructure.pg_models import instrument_selection_specs
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


@pytest.mark.asyncio
async def test_authority_and_current_pointer_round_trip_atomically(
    head_template_engine,
) -> None:
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="selection-authority-test",
                runtime_commit="selection-authority-test",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1_704_067_200_000,
            ),
        )
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.insert(instrument_selection_specs).values(
                selection_spec_id="sor-dynamic-selection-v0",
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v4",
                selection_version=1,
                selection_kind="sor_dynamic_v0",
                algorithm_semantic_digest="sha256:" + "a" * 64,
                status="active",
                installed_at_ms=1_704_067_200_000,
            )
        )
    authority = SelectionSessionAuthority(
        selection_authority_id="authority:test:1",
        selection_spec_id="sor-dynamic-selection-v0",
        session_start_ms=1_704_067_200_000,
        decision_boundary_ms=1_704_070_800_000,
        authority_sequence=1,
        selection_mode=SelectionMode.DISABLED,
        selection_snapshot_id=None,
        continued_from_selection_authority_id=None,
        continuity_source_kind=ContinuitySourceKind.NONE,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=1,
        authority_outcome=AuthorityOutcome.OWNER_PAUSED_NOT_MATERIALIZED,
        authorized_pair=None,
        grant_proof=None,
        effective_from_ms=1_704_070_800_000,
        first_eligible_close_time_ms=None,
        expires_at_ms=1_704_157_200_000,
        reason_code="AWAITING_SELECTION",
        created_at_ms=1_704_070_800_000,
    )

    async with head_template_engine.begin() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        await repository.add_authority_and_set_current(
            authority,
            expected_current_version=None,
        )

    async with head_template_engine.connect() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        persisted = await repository.get_current_authority(
            "sor-dynamic-selection-v0"
        )

    assert persisted == authority
