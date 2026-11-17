"""Real pause/resume ledger must release only a drained static Owner fence."""

from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    set_strategy_entry_state,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.owner_control import StrategyEntryState
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.selection_runtime_worker import (
    SelectionRuntimeRequest,
    run_materialization_runtime_once,
)
from tests.trading_kernel.support.generic_seed_template import (
    GROUPS,
    seed_generic_database,
)
from tests.trading_kernel.support.generic_selection import CUTOFF


async def change(engine, group, target, version, at):
    async with PostgresKernelUnitOfWork(engine) as u:
        return await set_strategy_entry_state(
            u,
            strategy_group_id=group,
            target_state=target,
            request=ControlMutationRequest(
                expected_version=version,
                reason="owner decision",
                idempotency_key=f"{group}:{version}",
                owner_identity="owner",
                now_ms=at,
            ),
            authentication_strength="totp_step_up",
        )


async def tick(engine, group, at):
    return await run_materialization_runtime_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(engine),
        audit_source=AsyncMock(),
        request=SelectionRuntimeRequest(
            strategy_group_id=group,
            selection_spec_id=generic_selection_spec(group).selection_spec_id,
            worker_id="materializer",
            now_ms=at,
        ),
        clock_ms=lambda: at,
    )


@pytest.mark.parametrize("group", GROUPS)
@pytest.mark.parametrize("early_resume", [True, False])
async def test_static_owner_pause_drains_and_resolves_after_real_resume(
    head_template_engine, group, early_resume
):
    e = head_template_engine
    await seed_generic_database(e)
    await change(e, group, StrategyEntryState.PAUSED, 1, CUTOFF + 100)
    if early_resume:
        await change(e, group, StrategyEntryState.ENABLED, 2, CUTOFF + 101)
    await tick(e, group, CUTOFF + 102)
    await tick(e, group, CUTOFF + 103)
    if not early_resume:
        async with PostgresKernelUnitOfWork(e) as u:
            v = await u.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group,
                selection_spec_id=generic_selection_spec(group).selection_spec_id,
            )
            assert v.state.value == "OWNER_PAUSED" and v.drained_at_ms is not None
        await change(e, group, StrategyEntryState.ENABLED, 2, CUTOFF + 104)
    await tick(e, group, CUTOFF + 105)
    await tick(e, group, CUTOFF + 106)
    async with PostgresKernelUnitOfWork(e) as u:
        assert (
            await u.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group,
                selection_spec_id=generic_selection_spec(group).selection_spec_id,
            )
            is None
        )
    async with e.connect() as c:
        rows = (
            (
                await c.execute(
                    sa.text(
                        "SELECT event_type,payload FROM brc_strategy_entry_vacuum_events ORDER BY event_sequence"
                    )
                )
            )
            .mappings()
            .all()
        )
        assert [r["event_type"] for r in rows] == [
            "OPEN",
            "DRAINING_ENTRY",
            "OWNER_PAUSED",
            "RESOLVED_OWNER_RESUME",
        ]
        assert rows[-1]["payload"]["owner_resume_authorization_id"]
        assert rows[-1]["payload"]["owner_pause_authorization_id"]


@pytest.mark.parametrize(
    "fault",
    [
        "still_paused",
        "no_drain",
        "pending_selection",
        "missing_resolution_event",
        "forged_event",
    ],
)
async def test_static_fence_rejects_incomplete_or_forged_resume(
    head_template_engine, fault
):
    from src.trading_kernel.application.owner_control import (
        stage_generic_dynamic_selection_mode,
    )

    e = head_template_engine
    group = "CPM-RO-001"
    await seed_generic_database(e)
    await change(e, group, StrategyEntryState.PAUSED, 1, CUTOFF + 100)
    if fault != "no_drain":
        await tick(e, group, CUTOFF + 101)
        await tick(e, group, CUTOFF + 102)
    if fault != "still_paused":
        await change(e, group, StrategyEntryState.ENABLED, 2, CUTOFF + 103)
    if fault == "pending_selection":
        from tests.trading_kernel.support.static_selection_source import (
            install_static_selection_source,
        )

        await install_static_selection_source(e, group)
        async with PostgresKernelUnitOfWork(e) as u:
            await stage_generic_dynamic_selection_mode(
                u,
                strategy_group_id=group,
                effective_period_anchor_ms=(
                    CUTOFF // (generic_selection_spec(group).cadence_hours * 3600000)
                    + 1
                )
                * generic_selection_spec(group).cadence_hours
                * 3600000,
                request=ControlMutationRequest(
                    expected_version=1,
                    reason="new selection intent",
                    idempotency_key="selection-intent",
                    owner_identity="owner",
                    now_ms=CUTOFF + 104,
                ),
                authentication_strength="totp_step_up",
            )
    async with PostgresKernelUnitOfWork(e) as u:
        v = await u.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,
            selection_spec_id=generic_selection_spec(group).selection_spec_id,
            for_update=True,
        )
        if fault in {"still_paused", "no_drain", "pending_selection"}:
            assert not await u.instrument_selection.resolve_static_owner_pause_vacuum(
                v, resolved_at_ms=CUTOFF + 105
            )
    # Direct state edits cannot replace the state machine or its exact proof.
    with pytest.raises(sa.exc.DBAPIError, match="static Owner resume requires"):
        async with e.begin() as c:
            if fault == "forged_event":
                await c.execute(
                    sa.text(
                        "INSERT INTO brc_strategy_entry_vacuum_events VALUES ('forged',:id,:seq,'RESOLVED_OWNER_RESUME','{}',:at)"
                    ),
                    {
                        "id": v.entry_vacuum_id,
                        "seq": v.projection_version + 1,
                        "at": CUTOFF + 105,
                    },
                )
            await c.execute(
                sa.text(
                    "UPDATE brc_strategy_entry_vacuums_current SET state='RESOLVED_OWNER_RESUME',resolved_at_ms=:at,projection_version=projection_version+1 WHERE entry_vacuum_id=:id"
                ),
                {"id": v.entry_vacuum_id, "at": CUTOFF + 105},
            )


async def test_resolution_ledger_cannot_commit_without_resolving_the_fence(
    head_template_engine,
):
    e = head_template_engine
    group = "CPM-RO-001"
    await seed_generic_database(e)
    await change(e, group, StrategyEntryState.PAUSED, 1, CUTOFF + 100)
    await tick(e, group, CUTOFF + 101)
    await tick(e, group, CUTOFF + 102)
    await change(e, group, StrategyEntryState.ENABLED, 2, CUTOFF + 103)
    with pytest.raises(sa.exc.DBAPIError, match="ledger must resolve"):
        async with e.begin() as c:
            await c.execute(
                sa.text(
                    "INSERT INTO brc_strategy_entry_vacuum_events SELECT 'uncommitted',entry_vacuum_id,projection_version+1,'RESOLVED_OWNER_RESUME',brc_static_owner_resume_proof(entry_vacuum_id,:at),:at FROM brc_strategy_entry_vacuums_current"
                ),
                {"at": CUTOFF + 104},
            )


@pytest.mark.parametrize("drain_first", [False, True])
async def test_repeated_real_pause_resume_before_worker_catches_up(
    head_template_engine, drain_first
):
    e = head_template_engine
    group = "CPM-RO-001"
    await seed_generic_database(e)
    await change(e, group, StrategyEntryState.PAUSED, 1, CUTOFF + 100)
    if drain_first:
        await tick(e, group, CUTOFF + 101)
        await tick(e, group, CUTOFF + 102)
    await change(e, group, StrategyEntryState.ENABLED, 2, CUTOFF + 103)
    await change(e, group, StrategyEntryState.PAUSED, 3, CUTOFF + 104)
    await change(e, group, StrategyEntryState.ENABLED, 4, CUTOFF + 105)
    for offset in (106, 107, 108):
        await tick(e, group, CUTOFF + offset)
    async with PostgresKernelUnitOfWork(e) as u:
        assert (
            await u.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group,
                selection_spec_id=generic_selection_spec(group).selection_spec_id,
            )
            is None
        )


async def test_resume_without_totp_cannot_release_static_fence(head_template_engine):
    e = head_template_engine
    group = "CPM-RO-001"
    await seed_generic_database(e)
    await change(e, group, StrategyEntryState.PAUSED, 1, CUTOFF + 100)
    await tick(e, group, CUTOFF + 101)
    await tick(e, group, CUTOFF + 102)
    async with PostgresKernelUnitOfWork(e) as u:
        await set_strategy_entry_state(
            u,
            strategy_group_id=group,
            target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(
                expected_version=2,
                reason="insufficient authentication",
                idempotency_key="weak-resume",
                owner_identity="owner",
                now_ms=CUTOFF + 103,
            ),
            authentication_strength="session",
        )
    result = await tick(e, group, CUTOFF + 104)
    assert result.reason_code == "STATIC_OWNER_RESUME_PROOF_MISSING"
    async with PostgresKernelUnitOfWork(e) as u:
        v = await u.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,
            selection_spec_id=generic_selection_spec(group).selection_spec_id,
        )
        assert v.state.value == "OWNER_PAUSED"


@pytest.mark.parametrize('group',GROUPS)
async def test_mobile_pause_resume_before_static_drain_is_honored_by_event_guards(head_template_engine,group):
    from tests.trading_kernel.support.mobile_owner import (
        mobile_client,
        strategy_control,
    )
    engine=head_template_engine
    await seed_generic_database(engine)
    async with mobile_client(engine,at_ms=CUTOFF+90) as browser:
        paused=await strategy_control(browser,group=group,enabled=False,version=1,at_ms=CUTOFF+100)
        resumed=await strategy_control(browser,group=group,enabled=True,version=paused['control_version'],at_ms=CUTOFF+101)
        assert resumed['entry_state']=='enabled'
        for at in (CUTOFF+102,CUTOFF+103,CUTOFF+104,CUTOFF+105):
            await tick(engine,group,at)
    async with PostgresKernelUnitOfWork(engine) as u:
        assert await u.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=generic_selection_spec(group).selection_spec_id) is None
    async with engine.connect() as c:
        events=(await c.execute(sa.text('SELECT e.event_type,e.payload FROM brc_strategy_entry_vacuum_events e JOIN brc_strategy_entry_vacuums_current v USING(entry_vacuum_id) WHERE v.strategy_group_id=:group ORDER BY e.event_sequence'),{'group':group})).mappings().all()
        assert [e['event_type'] for e in events]==['OPEN','DRAINING_ENTRY','OWNER_PAUSED','RESOLVED_OWNER_RESUME']
        assert events[2]['payload']['resumed_before_drain'] is True


async def test_trusted_strength_without_signed_evidence_cannot_finish_early_resume(head_template_engine):
    from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
        SelectionJobConflict,
    )
    engine=head_template_engine;group='CPM-RO-001'
    await seed_generic_database(engine)
    await change(engine,group,StrategyEntryState.PAUSED,1,CUTOFF+100)
    async with PostgresKernelUnitOfWork(engine) as u:
        await set_strategy_entry_state(u,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(expected_version=2,owner_identity='Owner',reason='unproven strength must not grant authority',idempotency_key='unproven-resume',now_ms=CUTOFF+101),authentication_strength='trusted_device_session')
    await tick(engine,group,CUTOFF+102)
    with pytest.raises(SelectionJobConflict,match='early Resume drain proof missing'):
        await tick(engine,group,CUTOFF+103)
    async with PostgresKernelUnitOfWork(engine) as u:
        vacuum=await u.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=generic_selection_spec(group).selection_spec_id)
        assert vacuum.state.value=='DRAINING_ENTRY' and vacuum.drained_at_ms is None


async def test_all_installed_strategy_resume_predicates_include_device_evidence(head_template_engine):
    import re
    async with head_template_engine.connect() as c:
        definitions=(await c.execute(sa.text("SELECT proname,prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND prosrc LIKE '%strategy_resume%' AND prosrc LIKE '%totp_step_up%'"))).all()
    assert len(definitions)>=8
    bare_resume=re.compile(r"purpose\s*=\s*'strategy_resume'\s+AND\s+\w+\.authentication_strength\s*=\s*'totp_step_up'")
    remaining=[name for name,source in definitions if bare_resume.search(source)]
    assert remaining==[],remaining
