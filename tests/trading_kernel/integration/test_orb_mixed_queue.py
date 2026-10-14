"""Run the exact shared queue selector on isolated minimal PG relations only."""

from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
)
from src.trading_kernel.infrastructure.pg_universe_repository import (
    PostgresStrategyUniverseRepository,
)
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", [None, "paused", "expired", "last_hour", "stale_control"]
)
async def test_hourly_queue_preserves_oldest_auditable_orb_without_weakening_other_gates(
    fault,
):
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        async with engine.begin() as c:
            ddl = [
                "CREATE TABLE brc_strategy_universe_materialization_generations(materialization_generation_id text, strategy_group_id text, selection_spec_id text, selection_epoch_id text,selection_mode text,period_anchor_ms bigint,selection_control_version bigint,selection_snapshot_id text,lifecycle_state text,desired_at_ms bigint,created_at_ms bigint)",
                "CREATE TABLE brc_strategy_entry_controls_current(strategy_group_id text,entry_state text)",
                "CREATE TABLE brc_strategy_selection_control_current(strategy_group_id text,control_version bigint)",
                "CREATE TABLE brc_instrument_selection_snapshots(selection_snapshot_id text,expires_at_ms bigint)",
                "CREATE TABLE brc_instrument_selection_member_decisions(selection_snapshot_id text,exchange_instrument_id text,selected boolean)",
                "CREATE TABLE brc_instrument_selection_spec_events(selection_spec_id text,event_spec_id text)",
                "CREATE TABLE brc_exposure_episode_current(event_spec_id text,exchange_instrument_id text,last_observed_at_ms bigint,comparison_last_observed_at_ms bigint,authority_recovery_last_observed_at_ms bigint,authority_recovery_id text,authority_recovery_armed_at_ms bigint)",
                "CREATE TABLE brc_selection_authority_current(selection_authority_id text,selection_spec_id text)",
                "CREATE TABLE brc_selection_session_authorities(selection_authority_id text,recovery_grant_proof jsonb,continued_from_selection_authority_id text,current_close_proof jsonb)",
                "CREATE TABLE brc_selection_authority_event_bindings(selection_authority_id text,event_spec_id text,universe_version_id text)",
                "CREATE TABLE brc_strategy_universe_members(universe_version_id text,exchange_instrument_id text)",
                "CREATE TABLE brc_strategy_universe_versions(lifecycle_state text,materialization_generation_id text)",
            ]
            for sql in ddl:
                await c.execute(sa.text(sql))
            await c.execute(
                sa.text(
                    "CREATE TABLE brc_instrument_selection_specs(selection_spec_id text,selection_kind text,strategy_group_id text)"
                )
            )
            now = await c.scalar(
                sa.text(
                    "SELECT floor(extract(epoch FROM clock_timestamp())*1000)::bigint"
                )
            )
            for gid, group, spec, event, member, age in [
                (
                    "orb",
                    "SOR-1H-001",
                    "SOR_1H_OR_ATR_DYNAMIC_V1",
                    "event_spec:SOR-1H-001:SOR-1H-LONG:v1",
                    "BTC",
                    10000,
                ),
                (
                    "generic",
                    "MI-001",
                    "MI_POSITIVE_IMPULSE_RECENCY_V0",
                    "event_spec:MI-001:MI-LONG:v3",
                    "ETH",
                    1000,
                ),
            ]:
                await c.execute(
                    sa.text(
                        "INSERT INTO brc_strategy_universe_materialization_generations VALUES(:gid,:group,:spec,'epoch:live','dynamic_selection',:day,2,:gid,'DESIRED',:time,:time)"
                    ),
                    {
                        "gid": gid,
                        "group": group,
                        "spec": spec,
                        "time": now - age,
                        "day": now // 86400000 * 86400000,
                    },
                )
                await c.execute(
                    sa.text(
                        "INSERT INTO brc_strategy_entry_controls_current VALUES(:group,'enabled')"
                    ),
                    {"group": group},
                )
                await c.execute(
                    sa.text(
                        "INSERT INTO brc_strategy_selection_control_current VALUES(:group,2)"
                    ),
                    {"group": group},
                )
                await c.execute(
                    sa.text(
                        "INSERT INTO brc_instrument_selection_snapshots VALUES(:gid,:expire)"
                    ),
                    {"gid": gid, "expire": now + 86400000},
                )
                await c.execute(
                    sa.text(
                        "INSERT INTO brc_instrument_selection_member_decisions VALUES(:gid,:member,true)"
                    ),
                    {"gid": gid, "member": member},
                )
                await c.execute(
                    sa.text(
                        "INSERT INTO brc_instrument_selection_spec_events VALUES(:spec,:event)"
                    ),
                    {"spec": spec, "event": event},
                )
            await c.execute(
                sa.text(
                    "INSERT INTO brc_instrument_selection_specs VALUES('SOR_1H_OR_ATR_DYNAMIC_V1','orb_session_dynamic_v1','SOR-1H-001'),('MI_POSITIVE_IMPULSE_RECENCY_V0','generic_dynamic_v1','MI-001')"
                )
            )
            if fault == "paused":
                await c.execute(
                    sa.text(
                        "UPDATE brc_strategy_entry_controls_current SET entry_state='paused' WHERE strategy_group_id='SOR-1H-001'"
                    )
                )
            if fault == "stale_control":
                await c.execute(
                    sa.text(
                        "UPDATE brc_strategy_selection_control_current SET control_version=3 WHERE strategy_group_id='SOR-1H-001'"
                    )
                )
            if fault == "last_hour":
                # Evaluate a real queue clock after its last daily eligible close.
                clock = now // 86400000 * 86400000 + 23 * 3600000 + 1
            else:
                clock = now // 86400000 * 86400000 + 3600000 + 1
            if fault == "expired":
                await c.execute(
                    sa.text(
                        "UPDATE brc_instrument_selection_snapshots SET expires_at_ms=:now WHERE selection_snapshot_id='orb'"
                    ),
                    {"now": clock - 1},
                )
            await c.execute(
                sa.text(
                    "INSERT INTO brc_exposure_episode_current VALUES('event_spec:SOR-1H-001:SOR-1H-LONG:v1','BTC',:close,NULL,NULL,NULL,NULL)"
                ),
                {"close": clock // 3600000 * 3600000},
            )
            repo = PostgresStrategyUniverseRepository(c)
            with patch.object(
                PostgresInstrumentSelectionRepository,
                "read_authority_clock_ms",
                AsyncMock(return_value=clock),
            ):
                orb = await repo.materialization_slot_available("orb")
                generic = await repo.materialization_slot_available("generic")
            assert orb is (fault is None)
            assert generic is (fault is not None)

    finally:
        await engine.dispose()
        await drop_disposable_database(name)
