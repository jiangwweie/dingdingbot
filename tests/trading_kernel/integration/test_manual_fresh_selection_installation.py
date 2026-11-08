"""Fresh Spec installation binds the real existing Static comparison source."""

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationRequest,
    advance_strategy_universe,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseConfigurationRequest,
    configure_strategy_universe,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
    build_comparative_universe_projection,
)
from src.trading_kernel.domain.generic_selection_spec import (
    SpecNumericInstallationEvidence,
    generic_selection_spec,
)
from src.trading_kernel.domain.strategy_registry import strategy_contract_for
from src.trading_kernel.infrastructure.manual_runtime_initialization import (
    initialize_manual_runtime,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.integration.universe_activation_support import (
    make_warming_ready,
    save_complete_comparative_projection,
)
from tests.trading_kernel.unit.detectors.fixtures import mi_long_snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "group,event", [("MPG-001", "MPG-LONG"), ("MI-001", "MI-LONG")]
)
async def test_fresh_spec_installer_preserves_static_comparison_members_and_revision(
    head_template_engine, group, event
):
    engine = head_template_engine
    members = ("binance-usdm:BTCUSDT:perpetual", "binance-usdm:ETHUSDT:perpetual")
    now = 1800000000000 // 3600000 * 3600000 - 2000
    async with PostgresKernelUnitOfWork(engine) as u:
        await initialize_manual_runtime(
            u,
            RuntimeAuthoritySeedRequest(
                account_id="manual-fresh-selection",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=now,
            ),
        )
        result = await configure_strategy_universe(
            u,
            UniverseConfigurationRequest(
                runtime_profile_id="tiny-live-v1",
                event_id=event,
                exchange_instrument_ids=members,
                installed_at_ms=now + 1000,
            ),
        )
        uid = result.universe.universe_version_id
    await make_warming_ready(
        engine,
        universe_version_id=uid,
        warm_closed_bar_time_ms=now + 2000,
        valid_until_ms=now + 60000,
    )
    if group == "MPG-001":
        await save_complete_comparative_projection(
            engine,
            contract=strategy_contract_for(generic_selection_spec(group).event_spec_id),
            universe_version_id=uid,
            members=members,
            closed_bar_time_ms=now + 2000,
        )
    else:
        candles = mi_long_snapshot().candles_1h
        delta = now + 2000 - candles[-1].close_time_ms
        candles = tuple(
            c.model_copy(
                update={
                    "open_time_ms": c.open_time_ms + delta,
                    "close_time_ms": c.close_time_ms + delta,
                }
            )
            for c in candles
        )
        projection = build_comparative_universe_projection(
            event_spec_id=generic_selection_spec(group).event_spec_id,
            universe_version_id=uid,
            strategy_group_id=group,
            exchange_instrument_ids=members,
            closed_bar_time_ms=now + 2000,
            lookback_bars=12,
            freshness_window_ms=3600000,
            member_windows=tuple(
                ComparativeMemberWindow(exchange_instrument_id=m, candles_1h=candles)
                for m in members
            ),
        )
        async with PostgresKernelUnitOfWork(engine) as u:
            await u.strategy_universes.save_comparative_projection(projection)
    async with PostgresKernelUnitOfWork(engine) as u:
        assert (
            await advance_strategy_universe(
                u,
                UniverseActivationRequest(
                    universe_version_id=uid, attempted_at_ms=now + 2001
                ),
            )
        ).status.value == "activated"
    spec = generic_selection_spec(group)
    evidence = SpecNumericInstallationEvidence(
        selection_spec_id=spec.selection_spec_id,
        algorithm_semantic_digest=spec.algorithm_semantic_digest,
        checked_cutoffs=1852,
        mismatch_count=0,
        source_archive_count=96,
        reference_commit="f65d72fa92580de4b8c0323f4106d5975b97f4eb",
        common_numeric_authority="PASS",
        sor_golden="PASS",
        spec_cert="PASS",
    )
    for _ in range(2):
        async with PostgresKernelUnitOfWork(engine) as u:
            await u.instrument_selection.install_generic_spec(
                spec, installed_at_ms=now + 3000, certification=evidence
            )
            binding = await u.instrument_selection.get_comparison_universe_binding(
                spec.event_spec_id
            )
            assert binding is not None
            assert binding.source_static_universe_version_id == uid
            assert binding.exchange_instrument_ids == members
            assert binding.comparison_transition_revision == 0
    async with engine.connect() as c:
        assert (
            await c.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
        )
        assert (
            await c.scalar(
                sa.text("SELECT new_entry_submit_enabled FROM brc_owner_policy_current")
            )
            is False
        )
