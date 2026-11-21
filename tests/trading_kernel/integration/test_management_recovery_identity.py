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
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


@pytest.mark.asyncio
async def test_recovery_identity_is_exact_single_ticket_and_disables_both_capabilities(head_template_engine):
    e=head_template_engine;t=registered_sor_long_ticket()
    await reach_position_protected(e,t)
    seed=RuntimeAuthoritySeedRequest(account_id=t.identity.netting_domain.account_id,runtime_commit='a'*40,schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=1000)
    async with e.begin() as c:
        await c.execute(insert(runtime_profiles).values(runtime_profile_id=t.identity.runtime.runtime_profile_id,venue_id="binance-usdm",account_id=t.identity.netting_domain.account_id,environment="live",status="active",position_mode="independent_sides",updated_at_ms=1000).on_conflict_do_nothing())
        for key,value in {'runtime_commit':'a'*40,'schema_revision':CURRENT_SCHEMA_REVISION,'seed_identity':build_runtime_seed_identity(seed),
            'registry_semantic_hash':build_registry_semantic_hash(registered_strategy_contracts(include_sor_split=True))}.items():
            await c.execute(insert(schema_metadata).values(metadata_key=key,metadata_value=value,updated_at_ms=1000).on_conflict_do_update(index_elements=['metadata_key'],set_={'metadata_value':value}))
        await c.execute(insert(runtime_capabilities_current).values(capability_key='strategy_signal_ingest',enabled=True,certified_commit='a'*40,
            schema_revision=CURRENT_SCHEMA_REVISION,certification={'product_id':'brc-app-manual-v1'},updated_at_ms=1000).on_conflict_do_nothing())
        await c.execute(sa.update(owner_policy_current).values(new_entry_submit_enabled=False))
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
