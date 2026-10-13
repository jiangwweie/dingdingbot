from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.domain.orb_session_selection import OrbSessionSelectionSpec
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION

D=1_800_000_000_000//86_400_000*86_400_000


@pytest.mark.asyncio
async def test_hourly_spec_installs_as_independent_paused_pair_with_frozen_candidate_panel(head_template_engine:AsyncEngine) -> None:
    async with head_template_engine.connect() as c:
        assert await c.scalar(sa.text("SELECT to_regclass('public.brc_orb_session_selection_specs_v1')")) is not None
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(uow,RuntimeAuthoritySeedRequest(account_id='orb-test',runtime_commit='orb-local-test',
            schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=D))
        await uow.instrument_selection.install_orb_spec(OrbSessionSelectionSpec(),installed_at_ms=D+1)
    async with head_template_engine.connect() as c:
        assert await c.scalar(sa.text("SELECT entry_state FROM brc_strategy_entry_controls_current WHERE strategy_group_id='SOR-1H-001'"))=='paused'
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_spec_members WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"))==24
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_spec_events WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"))==2
        assert await c.scalar(sa.text("SELECT selection_kind FROM brc_instrument_selection_specs WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"))=='orb_session_dynamic_v1'
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))==0
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"))==0
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        assert await uow.instrument_selection.get_orb_spec('SOR_1H_OR_ATR_DYNAMIC_V1')==OrbSessionSelectionSpec()


@pytest.mark.asyncio
async def test_hourly_snapshot_member_results_are_immutable_independent_and_epoch_bound(head_template_engine:AsyncEngine) -> None:
    from decimal import Decimal

    from src.trading_kernel.domain.instrument_selection import (
        SelectionKline,
        SelectionSourceWindow,
    )
    from src.trading_kernel.domain.orb_session_selection import (
        build_orb_session_period,
        compute_orb_selection,
    )
    spec=OrbSessionSelectionSpec();h=3_600_000
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(uow,RuntimeAuthoritySeedRequest(account_id='orb-test',runtime_commit='orb-local-test',
            schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=D))
        await uow.instrument_selection.install_orb_spec(spec,installed_at_ms=D+1)
    windows=tuple(SelectionSourceWindow(exchange_instrument_id=m,input_window_start_ms=D-23*h,feature_cutoff_at_ms=D+h,
        klines=tuple(SelectionKline(open_time_ms=D-23*h+i*900000,close_time_ms=D-23*h+(i+1)*900000,
            open=Decimal(100),close=Decimal(100),high=Decimal(101),low=Decimal(99),quote_volume=Decimal(1000000))
            for i in range(96))) for m in spec.candidate_ids)
    result=compute_orb_selection(spec=spec,period=build_orb_session_period(D),selection_epoch_id='epoch:orb:pg',
        source_windows=windows,decision_at_ms=D+h,source_observed_at_ms=D+h+1,created_at_ms=D+h+2)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await uow.instrument_selection.save_orb_snapshot(result)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        assert await uow.instrument_selection.get_orb_snapshot(result.snapshot.selection_snapshot_id)==result
    async with head_template_engine.connect() as c:
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_member_decisions WHERE selection_family='orb_session_dynamic_v1'"))==24
    with pytest.raises(Exception,match='immutable'):
        async with head_template_engine.begin() as c:
            await c.execute(sa.text("UPDATE brc_instrument_selection_snapshots SET selected_count=6 WHERE selection_snapshot_id=:sid"),{'sid':result.snapshot.selection_snapshot_id})
