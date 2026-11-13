"""Shared disposable installed static Universe fixture for Selection tests."""

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    install_strategy_universe,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.generic_selection import CUTOFF, HOUR


async def install_static_selection_source(database: AsyncEngine, group: str, *, member_count: int = 1, cutoff_ms: int = CUTOFF):
    spec = generic_selection_spec(group)
    members = spec.candidate_ids[:member_count]
    async with PostgresKernelUnitOfWork(database) as uow:
        installed = await install_strategy_universe(uow,UniverseInstallRequest(
            event_spec_id=spec.event_spec_id,runtime_profile_id="tiny-live-v1",
            owner_policy_id="policy-main",exchange_instrument_ids=members,
            installed_at_ms=cutoff_ms-1,
        ))
    assert installed.universe is not None
    uid = installed.universe.universe_version_id
    comparison_id = None
    async with database.begin() as conn:
        await conn.execute(sa.text(
            "UPDATE brc_strategy_universe_versions SET lifecycle_state='active',activated_at_ms=:at "
            "WHERE universe_version_id=:uid"
        ),{"uid":uid,"at":cutoff_ms-1})
        await conn.execute(sa.text(
            "UPDATE brc_runtime_scopes_current SET lifecycle_state='active',entry_enabled=true,"
            "observation_enabled=true,warm_closed_bar_time_ms=:closed,warm_completed_at_ms=:at,"
            "warm_readiness_digest=:digest,warm_valid_until_ms=:valid WHERE universe_version_id=:uid"
        ),{"uid":uid,"closed":cutoff_ms-HOUR,"at":cutoff_ms-1,
            "digest":"sha256:"+"1"*64,"valid":cutoff_ms+2*HOUR})
        await conn.execute(sa.text(
            "INSERT INTO brc_strategy_universe_current VALUES(:event,:uid,:digest,'active',1,:at)"
        ),{"event":spec.event_spec_id,"uid":uid,
            "digest":installed.universe.semantic_digest,"at":cutoff_ms-1})
        if group in {"MPG-001","MI-001"}:
            digest = canonical_digest({"exchange_instrument_ids":members})
            comparison_id = "comparison:"+digest[7:]
            await conn.execute(sa.text(
                "INSERT INTO brc_comparison_universe_definitions VALUES(:id,:digest,:count) ON CONFLICT DO NOTHING"
            ),{"id":comparison_id,"digest":digest,"count":len(members)})
            for member in members:
                await conn.execute(sa.text(
                    "INSERT INTO brc_comparison_universe_members VALUES(:id,:member) ON CONFLICT DO NOTHING"
                ),{"id":comparison_id,"member":member})
            await conn.execute(sa.text(
                "INSERT INTO brc_comparison_binding_current VALUES(:event,:id,0,:uid)"
            ),{"event":spec.event_spec_id,"id":comparison_id,"uid":uid})
    return uid,comparison_id

