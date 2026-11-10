from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.exit_parameter_controls import (
    ExitParameterChange,
    ExitParameterPublishRequest,
    publish_exit_parameters,
)
from src.trading_kernel.domain.entry_regime import (
    FOUR_HOURS_MS,
    REGIME_EVENTS,
    BtcMa50Snapshot,
)
from src.trading_kernel.domain.exit_policy import registered_event_exit_bindings
from src.trading_kernel.domain.identities import RuntimeIdentity, TicketIdentity
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_models import exchange_commands
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.command_dispatch import issue, seed_policy
from tests.trading_kernel.support.dispatch_venues import (
    KindAwareAcceptingVenue,
    PreflightFacts,
)
from tests.trading_kernel.support.tickets import make_ticket


def snapshot(last=101):
    h = FOUR_HOURS_MS
    bars = []
    for i in range(50):
        price = Decimal(last if i == 49 else 100)
        bars.append(
            ClosedCandle(
                open_time_ms=(i + 1) * h,
                close_time_ms=(i + 2) * h,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=Decimal(1),
            )
        )
    return BtcMa50Snapshot(candles=tuple(bars), observed_at_ms=51 * h + 1000)


@pytest.mark.asyncio
async def test_regime_defaults_disabled_then_enforces_closed_period_and_keeps_evidence(
    issue_engine,
):
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="test",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1000,
            ),
        )
        default = await uow.entry_regimes.evaluate(REGIME_EVENTS[0], now_ms=2000)
        assert default.allowed and default.result == "disabled"
        await uow.entry_regimes.lock_controls((REGIME_EVENTS[0],))
        await uow.entry_regimes.switch(
            event_spec_id=REGIME_EVENTS[0],
            expected_revision=1,
            enabled=True,
            authorization_id="test-authorized",
            now_ms=2000,
        )
        await uow.entry_regimes.save_snapshot(snapshot())
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        allowed = await uow.entry_regimes.evaluate(
            REGIME_EVENTS[0], now_ms=51 * FOUR_HOURS_MS + 2000
        )
        assert allowed.allowed
        await uow.entry_regimes.record(
            phase="admission",
            identity_key="signal:1",
            ticket_id="ticket:1",
            evidence=allowed,
        )
        await uow.entry_regimes.record(
            phase="admission",
            identity_key="signal:1",
            ticket_id="ticket:1",
            evidence=allowed,
        )
        stale = await uow.entry_regimes.evaluate(
            REGIME_EVENTS[0], now_ms=52 * FOUR_HOURS_MS
        )
        assert not stale.allowed
        assert stale.result == "btc4h_facts_unavailable"


@pytest.mark.asyncio
async def test_final_send_blocks_scoped_entry_when_ma50_enabled_but_facts_unavailable(
    issue_engine,
):
    base = make_ticket()
    runtime = RuntimeIdentity(
        runtime_profile_id="tiny-live-v1",
        strategy_group_id="CPM-RO-001",
        strategy_version_id="sgv:CPM-RO-001:v3",
        event_spec_id=REGIME_EVENTS[0],
    )
    identity = TicketIdentity(
        ticket_id=build_ticket_id(
            signal_event_id="signal:regime",
            runtime=runtime,
            netting_domain=base.identity.netting_domain,
        ),
        exposure_episode_id="episode:regime",
        signal_event_id="signal:regime",
        runtime=runtime,
        netting_domain=base.identity.netting_domain,
    )
    ticket = make_ticket(
        identity=identity, exposure_family="long_continuation", family_ticket_limit=1
    )
    await seed_policy(issue_engine, event_spec_id=runtime.event_spec_id)
    await issue(issue_engine, ticket)
    source = next(
        b
        for b in registered_event_exit_bindings()
        if b.event_spec_id == runtime.event_spec_id
    )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await uow.directional_risk.initialize(
            venue_id="binance-usdm", account_id="experiment-1", now_ms=1000
        )
        await publish_exit_parameters(
            uow,
            ExitParameterPublishRequest(
                expected_version=1,
                reason="regime_test",
                idempotency_key="regime-publish",
                owner_identity="owner",
                now_ms=1050,
                venue_id="binance-usdm",
                account_id="experiment-1",
                changes=(
                    ExitParameterChange(
                        event_spec_id=runtime.event_spec_id,
                        expected_binding_id=source.exit_binding_id,
                        expected_version=1,
                        reward_multiple=Decimal(1),
                        quantity_fraction=Decimal("0.5"),
                        ma50_enabled=True,
                        expected_regime_revision=1,
                    ),
                ),
            ),
            authentication_strength="totp_step_up",
        )
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(issue_engine),
        KindAwareAcceptingVenue(),
        DispatchCommandRequest(
            worker_id="entry-regime",
            ticket_id=ticket.identity.ticket_id,
            now_ms=1100,
            lease_until_ms=6100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=1000,
        ),
        entry_facts_source=PreflightFacts(),
        clock_ms=lambda: 1100,
    )
    assert result.status is DispatchCommandStatus.SUPERSEDED
    async with issue_engine.connect() as connection:
        command = (
            (
                await connection.execute(
                    sa.select(exchange_commands).where(
                        exchange_commands.c.command_id == result.command_id
                    )
                )
            )
            .mappings()
            .one()
        )
        assert (
            command["result_payload"]["reason"]
            == "dispatch_preflight:entry_regime_blocked"
        )


@pytest.mark.asyncio
async def test_btc_refresh_claim_survives_restart_and_does_not_mint_valid_facts(
    issue_engine,
):
    now = 51 * FOUR_HOURS_MS + 1000
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert await uow.entry_regimes.try_begin_refresh(
            now_ms=now, retry_interval_ms=30000
        )
        assert await uow.entry_regimes.snapshot() is None
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert not await uow.entry_regimes.try_begin_refresh(
            now_ms=now + 1000, retry_interval_ms=30000
        )
        assert await uow.entry_regimes.snapshot() is None
        assert await uow.entry_regimes.try_begin_refresh(
            now_ms=now + 30000, retry_interval_ms=30000
        )
        await uow.entry_regimes.save_snapshot(snapshot())
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert not await uow.entry_regimes.try_begin_refresh(
            now_ms=now + 40000, retry_interval_ms=30000
        )
