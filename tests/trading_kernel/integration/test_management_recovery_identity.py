import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from src.trading_kernel.domain.events import ManagementReviewRequired
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.strategy_registry import (
    build_registry_semantic_hash,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    owner_policy_current,
    runtime_capabilities_current,
    runtime_profiles,
    schema_metadata,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    build_runtime_seed_identity,
    deploy_management_recovery_identity,
    deploy_verified_exit_recovery_identity,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


async def seed_recovery_fixture(e, t):
    seed=RuntimeAuthoritySeedRequest(account_id=t.identity.netting_domain.account_id,runtime_commit='a'*40,schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=1000)
    async with e.begin() as c:
        await c.execute(insert(runtime_profiles).values(runtime_profile_id=t.identity.runtime.runtime_profile_id,venue_id="binance-usdm",account_id=t.identity.netting_domain.account_id,environment="live",status="active",position_mode="independent_sides",updated_at_ms=1000).on_conflict_do_nothing())
        for key,value in {'runtime_commit':'a'*40,'schema_revision':CURRENT_SCHEMA_REVISION,'seed_identity':build_runtime_seed_identity(seed),
            'registry_semantic_hash':build_registry_semantic_hash(registered_strategy_contracts(include_sor_split=True))}.items():
            await c.execute(insert(schema_metadata).values(metadata_key=key,metadata_value=value,updated_at_ms=1000).on_conflict_do_update(index_elements=['metadata_key'],set_={'metadata_value':value}))
        await c.execute(insert(runtime_capabilities_current).values(capability_key='strategy_signal_ingest',enabled=True,certified_commit='a'*40,
            schema_revision=CURRENT_SCHEMA_REVISION,certification={'product_id':'brc-app-manual-v1'},updated_at_ms=1000).on_conflict_do_nothing())
        await c.execute(sa.update(owner_policy_current).values(new_entry_submit_enabled=False))

@pytest.mark.asyncio
async def test_recovery_identity_is_exact_single_ticket_and_disables_both_capabilities(head_template_engine):
    e=head_template_engine;t=registered_sor_long_ticket()
    await reach_position_protected(e,t)
    await seed_recovery_fixture(e, t)
    async with PostgresKernelUnitOfWork(e) as u:
        a=await u.aggregates.get_for_update(t.identity.ticket_id)
        ev=ManagementReviewRequired(event_id='gap',ticket_id=t.identity.ticket_id,sequence=a.last_event_sequence+1,occurred_at_ms=6000,evidence_id='gap',reason='collector_gap')
        await u.commit_reduction(event=ev,reduction=reduce_event(a,ev),expected_version=a.version)
    request=RuntimeAuthoritySeedRequest(account_id=t.identity.netting_domain.account_id,runtime_commit='b'*40,schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=8000)
    with pytest.raises(ValueError):
        async with PostgresKernelUnitOfWork(e) as u:
            await deploy_management_recovery_identity(u,request,recovery_ticket_ids=('wrong',))
    async with PostgresKernelUnitOfWork(e) as u:
        await deploy_management_recovery_identity(u,request,recovery_ticket_ids=(t.identity.ticket_id,))
    async with e.connect() as c:
        rows=(await c.execute(sa.select(runtime_capabilities_current))).mappings().all()
    assert not any(r['enabled'] for r in rows)
    assert all(r['certification']['runtime_mode']=='management_recovery_only' for r in rows)
    assert all(r['certification']['management_recovery_ticket_ids']==[t.identity.ticket_id] for r in rows)


@pytest.mark.asyncio
async def test_verified_recovery_binds_accepted_strategy_exit(head_template_engine):
    from src.trading_kernel.application.reconcile_ticket import (
        ExitTicketRequest,
        request_exit,
    )
    from tests.trading_kernel.support.command_dispatch import dispatch_for_ticket
    from tests.trading_kernel.support.dispatch_venues import KindAwareAcceptingVenue

    engine = head_template_engine
    ticket = registered_sor_long_ticket()
    ticket_id = ticket.identity.ticket_id
    await reach_position_protected(engine, ticket)
    await seed_recovery_fixture(engine, ticket)
    async with PostgresKernelUnitOfWork(engine) as uow:
        await request_exit(
            uow, ExitTicketRequest(ticket_id=ticket_id, reason="pre_tp1_time_stop_hit", requested_at_ms=5000)
        )
    await dispatch_for_ticket(
        engine, KindAwareAcceptingVenue(observed_at_ms=5101), ticket_id, now_ms=5100
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        aggregate = await uow.aggregates.get(ticket_id)
    assert aggregate.exit_exchange_order_id

    request = RuntimeAuthoritySeedRequest(
        account_id=ticket.identity.netting_domain.account_id,
        runtime_commit="b" * 40,
        schema_revision=CURRENT_SCHEMA_REVISION,
        seeded_at_ms=8000,
    )
    scope = {
        "ticket_id": ticket_id,
        "expected_version": aggregate.version,
        "management_revision": aggregate.management_revision,
        "source_commit": "a" * 40,
        "schema_revision": CURRENT_SCHEMA_REVISION,
        "incident_ids": [],
        "exit_order_id": aggregate.exit_exchange_order_id,
    }
    with pytest.raises(ValueError, match="previously protected managed"):
        async with PostgresKernelUnitOfWork(engine) as uow:
            await deploy_management_recovery_identity(uow, request, recovery_ticket_ids=(ticket_id,))
    with pytest.raises(ValueError, match="EXIT recovery aggregate differs"):
        async with PostgresKernelUnitOfWork(engine) as uow:
            await deploy_verified_exit_recovery_identity(uow, request, scope={**scope, "exit_order_id": "wrong"})
    with pytest.raises(ValueError, match="EXIT recovery command differs"):
        async with PostgresKernelUnitOfWork(engine) as uow:
            await uow._require_connection().execute(
                sa.update(exchange_commands)
                .where(exchange_commands.c.ticket_id == ticket_id, exchange_commands.c.command_kind == "exit")
                .values(result_payload={"exchange_order_id": "wrong"})
            )
            await deploy_verified_exit_recovery_identity(uow, request, scope=scope)

    async with PostgresKernelUnitOfWork(engine) as uow:
        await deploy_verified_exit_recovery_identity(uow, request, scope=scope)
    async with engine.connect() as conn:
        rows = (await conn.execute(sa.select(runtime_capabilities_current))).mappings().all()
        assert await conn.scalar(sa.select(owner_policy_current.c.new_entry_submit_enabled)) is False
    assert len(rows) == 2
    for row in rows:
        assert not row["enabled"]
        assert row["certification"]["runtime_mode"] == "verified_exit_recovery_only"
        assert row["certification"]["verified_exit_recovery_scope"]["exit_order_id"] == scope["exit_order_id"]
