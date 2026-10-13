from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel import verify_schema
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
)
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)


@pytest.mark.asyncio
async def test_hourly_upgrade_preserves_exact_source_0010_rows(monkeypatch):
    name,url=await create_empty_database()
    engine=create_async_engine(url)
    try:
        run_alembic(url,'upgrade','0010_dynamic_intent_v1')
        # Build certified terminal lineage using the real source schema and an active Generic Event.
        from src.trading_kernel.domain.strategy_registry import strategy_contract_for
        from tests.trading_kernel.support import event_chain as chain
        monkeypatch.setattr(chain,'CURRENT_SCHEMA_REVISION','0010_dynamic_intent_v1')
        await chain.run_event_chain(engine,
            strategy_contract_for('event_spec:CPM-RO-001:CPM-LONG:v3'),False)
        async with engine.begin() as connection:
            await connection.execute(sa.text('UPDATE brc_owner_policy_current SET policy_version=4,new_entry_submit_enabled=false'))
            assert await connection.scalar(sa.text('SELECT count(*) FROM brc_trade_reviews'))==1
        from src.trading_kernel.application.owner_control import (
            ExitProfileBindingMutationRequest,
            switch_event_exit_profile,
        )
        from src.trading_kernel.domain.exit_policy import registered_exit_profiles
        target_profile=next(p for p in registered_exit_profiles() if p.exit_profile_id=='exit-profile:momentum-tail:1h:long:v1')
        async with PostgresKernelUnitOfWork(engine) as uow:
            pointer=await uow.exit_profiles.get_current_binding('event_spec:CPM-RO-001:CPM-LONG:v3')
            await switch_event_exit_profile(uow,strategy_group_id='CPM-RO-001',event_spec_id='event_spec:CPM-RO-001:CPM-LONG:v3',
                request=ExitProfileBindingMutationRequest(expected_version=pointer.projection_version,reason='retain Owner exit choice',idempotency_key='source:exit:choice',owner_identity='owner',now_ms=1800000011100,
                    expected_binding_id=pointer.exit_binding_id,target_exit_profile_id=target_profile.exit_profile_id,target_exit_profile_semantic_hash=target_profile.semantic_hash()),authentication_strength='totp_step_up')
        async with engine.connect() as connection:
            source_bindings=tuple((await connection.execute(sa.text('SELECT * FROM brc_event_exit_profile_binding_current ORDER BY event_spec_id'))).mappings())
        source=await verify_schema._verify_compatible_source(url,'0010_dynamic_intent_v1')
        assert source['status']=='pass',{k:v for k,v in source.items() if isinstance(v,dict) and (v.get('status')=='fail' or k=='migration_gate')}
        run_alembic(url,'upgrade','head')
        target=await verify_schema._verify_preservation(url,source_revision='0010_dynamic_intent_v1',expected_digest=source['preservation_manifest']['digest'])
        assert target['status']=='pass',target
        assert target['preservation_manifest']['row_count']==source['preservation_manifest']['row_count']
        from src.trading_kernel.infrastructure.runtime_authority_seed import (
            deploy_compatible_upgrade_identity,
        )
        from src.trading_kernel.infrastructure.runtime_identity import (
            CURRENT_SCHEMA_REVISION,
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            upgraded=await deploy_compatible_upgrade_identity(uow,RuntimeAuthoritySeedRequest(account_id='account-certification',runtime_commit='target0011',schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=1800000012000))
        assert upgraded.schema_revision==CURRENT_SCHEMA_REVISION
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text("SELECT entry_state FROM brc_strategy_entry_controls_current WHERE strategy_group_id='SOR-1H-001'"))=='paused'
            assert await connection.scalar(sa.text("SELECT new_entry_submit_enabled FROM brc_owner_policy_current")) is False
            assert await connection.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_specs WHERE selection_kind='orb_session_dynamic_v1'"))==1
            target_bindings=tuple((await connection.execute(sa.text("SELECT * FROM brc_event_exit_profile_binding_current WHERE event_spec_id NOT LIKE 'event_spec:SOR-1H-001:%' ORDER BY event_spec_id"))).mappings())
            assert target_bindings==source_bindings

    finally:
        await engine.dispose()
        await drop_disposable_database(name)
