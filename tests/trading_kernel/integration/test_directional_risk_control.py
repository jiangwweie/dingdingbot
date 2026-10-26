import asyncio
from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandResult,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.directional_risk import DirectionalChangeRequest
from src.trading_kernel.infrastructure.pg_directional_risk_repository import (
    PostgresDirectionalRiskRepository,
)
from src.trading_kernel.infrastructure.pg_models import exchange_commands
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.command_dispatch import issue, seed_policy, ticket
from tests.trading_kernel.support.dispatch_venues import (
    CountingVenue,
    PreflightFacts,
    SlowVenue,
)


def dispatch_request(t):
    return DispatchCommandRequest(
        worker_id="sender",
        ticket_id=t.identity.ticket_id,
        now_ms=1100,
        lease_until_ms=6100,
        timeout_seconds=5,
        runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
        admission_snapshot_validity_ms=1000,
    )


@pytest.mark.asyncio
async def test_owner_change_during_real_preflight_uses_new_control(
    head_template_engine,
):
    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    started = asyncio.Event()
    release = asyncio.Event()

    class Facts(PreflightFacts):
        async def read_entry_admission_snapshot(self, request):
            started.set()
            await release.wait()
            return await super().read_entry_admission_snapshot(request)

    venue = CountingVenue()
    task = asyncio.create_task(
        dispatch_one_command(
            lambda: PostgresKernelUnitOfWork(engine),
            venue,
            dispatch_request(t),
            entry_facts_source=Facts(),
            clock_ms=lambda: 1100,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 5)
        async with engine.begin() as c:
            repo = PostgresDirectionalRiskRepository(c)
            await repo.request_change(
                change().model_copy(
                    update={"account_id": t.identity.netting_domain.account_id}
                )
            )
        release.set()
        result = await task
        assert result.status == DispatchCommandStatus.ACCEPTED and venue.calls == 1
        from src.trading_kernel.infrastructure.pg_models import (
            entry_send_authorizations,
        )

        async with engine.connect() as c:
            control = await c.scalar(sa.select(entry_send_authorizations.c.control))
            assert control["view"] == "bearish" and control["version"] == 2
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_tightening_rejects_unsent_ticket_and_releases_its_authorities(
    head_template_engine,
):
    from src.trading_kernel.infrastructure.pg_models import (
        budget_reservations,
        entry_lane_current,
        trade_tickets,
    )

    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    async with engine.begin() as c:
        # Another nonterminal domain owns four risk units. Only its Ticket risk
        # is needed by this bounded repository query; no extra exchange order.
        row = dict((await c.execute(sa.select(trade_tickets))).mappings().one())
        row.update(
            ticket_id="ticket:other-domain",
            signal_event_id="signal:other-domain",
            exposure_episode_id="episode:other-domain",
            exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
            active_netting_domain_key="other-domain",
            risk_at_stop=Decimal(4),
            planned_stop_risk_budget=Decimal(4),
            post_fill_stop_risk_limit=Decimal("4.4"),
        )
        await c.execute(sa.insert(trade_tickets).values(**row))
        await PostgresDirectionalRiskRepository(c).request_change(
            change().model_copy(
                update={"account_id": t.identity.netting_domain.account_id}
            )
        )
    venue = CountingVenue()
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        dispatch_request(t),
        entry_facts_source=PreflightFacts(),
        clock_ms=lambda: 1100,
    )
    assert result.status is DispatchCommandStatus.SUPERSEDED and venue.calls == 0
    async with engine.connect() as c:
        command = (
            await c.execute(sa.select(exchange_commands.c.result_payload))
        ).scalar_one()
        assert command["reason"] == "dispatch_preflight:directional_risk_exhausted"
        assert await c.scalar(sa.select(entry_lane_current.c.status)) == "idle"
        assert await c.scalar(sa.select(budget_reservations.c.status)) == "released"
        assert (
            await c.scalar(
                sa.select(trade_tickets.c.terminal_at_ms).where(
                    trade_tickets.c.ticket_id == t.identity.ticket_id
                )
            )
            is not None
        )


@pytest.mark.asyncio
async def test_change_after_committed_send_right_waits_for_actual_result(
    head_template_engine,
):
    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    started = asyncio.Event()
    release = asyncio.Event()

    class Venue:
        async def execute(self, request):
            async with engine.connect() as c:
                repo = PostgresDirectionalRiskRepository(c)
                assert await repo.send_expiry(request.command_id) == 2100
            assert request.entry_authorized_at_ms == 1100
            started.set()
            await release.wait()
            return ExchangeCommandResult(
                status=ExchangeCommandStatus.ACCEPTED,
                observed_at_ms=2100,
                exchange_order_id="accepted-1",
            )

    task = asyncio.create_task(
        dispatch_one_command(
            lambda: PostgresKernelUnitOfWork(engine),
            Venue(),
            dispatch_request(t),
            entry_facts_source=PreflightFacts(),
            clock_ms=lambda: 1100,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 5)
        async with engine.begin() as c:
            result = await PostgresDirectionalRiskRepository(c).request_change(
                change().model_copy(
                    update={"account_id": t.identity.netting_domain.account_id}
                )
            )
            assert result.pending_view == "bearish"
        release.set()
        assert (await task).status == DispatchCommandStatus.ACCEPTED
        async with engine.connect() as c:
            result = await PostgresDirectionalRiskRepository(c).get(
                "binance-usdm", t.identity.netting_domain.account_id
            )
            assert result.pending_view is None and result.view == "bearish"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_corrupt_directional_control_after_send_does_not_rollback_acceptance(
    head_template_engine,
):
    from src.trading_kernel.infrastructure.pg_models import directional_risk_controls

    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)

    class Venue:
        async def execute(self, request):
            async with engine.begin() as c:
                await c.execute(
                    sa.update(directional_risk_controls).values(
                        rule_digest="sha256:" + "f" * 64
                    )
                )
            return ExchangeCommandResult(
                status="accepted",
                exchange_order_id="accepted-with-control-drift",
                observed_at_ms=2000,
            )

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        Venue(),
        dispatch_request(t),
        entry_facts_source=PreflightFacts(),
        clock_ms=lambda: 1100,
    )
    assert result.status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(engine) as uow:
        aggregate = await uow.aggregates.get(t.identity.ticket_id)
        assert aggregate.status.value == "entry_accepted"
        with pytest.raises(ValueError):
            await uow.directional_risk.get(
                "binance-usdm", t.identity.netting_domain.account_id
            )


@pytest.mark.asyncio
async def test_corrupt_control_during_unknown_recovery_preserves_accepted_outcome(
    head_template_engine,
):
    from src.trading_kernel.application.recover_unknown_command import (
        RecoverUnknownCommandRequest,
        recover_unknown_command,
    )
    from src.trading_kernel.domain.venue_truth import (
        VenueOrderTruth,
        VenueTruthSnapshot,
    )
    from src.trading_kernel.infrastructure.pg_models import directional_risk_controls

    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        SlowVenue(),
        dispatch_request(t).model_copy(update={"timeout_seconds": 0.01}),
        entry_facts_source=PreflightFacts(),
        clock_ms=lambda: 1100,
    )
    assert result.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    async with engine.begin() as c:
        await c.execute(
            sa.update(directional_risk_controls).values(
                rule_digest="sha256:" + "f" * 64
            )
        )
    async with PostgresKernelUnitOfWork(engine) as uow:
        command = await uow.exchange_commands.get(result.command_id)

    class Truth:
        async def lookup_command_truth(self, request):
            return VenueTruthSnapshot(
                lookup_status="visible",
                order=VenueOrderTruth(
                    exchange_order_id="recovered-entry",
                    venue_client_order_id=command.venue_client_order_id,
                    exchange_instrument_id=t.identity.netting_domain.exchange_instrument_id,
                    position_side="long",
                    order_side="buy",
                    quantity=command.payload.quantity,
                    reduce_only=False,
                ),
                position_quantity=0,
                matching_fill_quantity=0,
                regular_open_client_order_ids=(),
                conditional_open_client_order_ids=(),
                observed_at_ms=8000,
                exchange_observed_at_ms=7000,
            )

    recovered = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(engine),
        Truth(),
        RecoverUnknownCommandRequest(
            command_id=result.command_id,
            now_ms=8000,
            visibility_deadline_ms=5000,
            timeout_seconds=1,
        ),
    )
    assert recovered.status.value == "reconciled_submitted"
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert (
            await uow.aggregates.get(t.identity.ticket_id)
        ).status.value == "entry_accepted"
        assert (
            await uow.exchange_commands.get(result.command_id)
        ).status is ExchangeCommandStatus.RECONCILED_ACCEPTED


@pytest.mark.asyncio
async def test_authorized_old_send_keeps_switch_pending_even_after_lease_expiry(
    head_template_engine,
):
    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    domain = t.identity.netting_domain
    async with engine.begin() as c:
        command_id = await c.scalar(sa.select(exchange_commands.c.command_id))
        await c.execute(
            sa.update(exchange_commands).values(
                status="claimed", claim_owner="sender", lease_until_ms=6_000
            )
        )
        repo = PostgresDirectionalRiskRepository(c)
        control = await repo.get(domain.venue_id, domain.account_id)
        await repo.authorize_send(
            command_id=command_id,
            venue_id=domain.venue_id,
            account_id=domain.account_id,
            worker_id="sender",
            now_ms=1_500,
            deadline_at_ms=t.expires_at_ms,
            valid_until_ms=t.expires_at_ms,
            control=control,
        )
    async with engine.begin() as c:
        repo = PostgresDirectionalRiskRepository(c)
        result = await repo.request_change(
            change().model_copy(update={"account_id": domain.account_id})
        )
        assert result.pending_view == "bearish" and result.view == "unset"
        assert (
            await repo.progress(domain.venue_id, domain.account_id, 100_000)
        ).pending_view == "bearish"
        await c.execute(sa.update(exchange_commands).values(status="reconciled_absent"))
        # Local time or a reconciled-absent row alone cannot revoke a suspended sender.
        await repo.recover_resolved_sends(
            domain.venue_id,
            domain.account_id,
            command_id=command_id,
            exchange_time_ms=6_500,
            observed_at_ms=100_000,
        )
        assert (
            await repo.progress(domain.venue_id, domain.account_id, 100_000)
        ).pending_view == "bearish"
        await repo.recover_resolved_sends(
            domain.venue_id,
            domain.account_id,
            command_id=command_id,
            exchange_time_ms=6_501,
            observed_at_ms=100_001,
        )
        result = await repo.progress(domain.venue_id, domain.account_id, 100_001)
        assert result.view == "bearish" and result.pending_view is None


def change(key="one", expected=1, view="bearish"):
    return DirectionalChangeRequest(
        venue_id="binance-usdm",
        account_id="test",
        expected_version=expected,
        view=view,
        owner_identity="owner",
        reason="outlook",
        idempotency_key=key,
        requested_at_ms=2_000,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("visible", [True, False])
async def test_unknown_visibility_and_control_completion_are_independent(
    head_template_engine, visible
):
    from src.trading_kernel.application.recover_unknown_command import (
        RecoverUnknownCommandRequest,
        recover_unknown_command,
    )
    from src.trading_kernel.domain.venue_truth import (
        VenueOrderTruth,
        VenueTruthSnapshot,
    )
    from src.trading_kernel.infrastructure.pg_models import entry_send_authorizations

    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        SlowVenue(),
        dispatch_request(t).model_copy(update={"timeout_seconds": 0.01}),
        entry_facts_source=PreflightFacts(),
        clock_ms=lambda: 1100,
    )
    assert result.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    async with engine.begin() as c:
        await PostgresDirectionalRiskRepository(c).request_change(
            change().model_copy(
                update={"account_id": t.identity.netting_domain.account_id}
            )
        )
    async with PostgresKernelUnitOfWork(engine) as uow:
        command = await uow.exchange_commands.get(result.command_id)

    class Truth:
        async def lookup_command_truth(self, request):
            assert request.entry_window_expires_at_ms == 2100
            order = (
                None
                if not visible
                else VenueOrderTruth(
                    exchange_order_id="known-entry",
                    venue_client_order_id=command.venue_client_order_id,
                    exchange_instrument_id=t.identity.netting_domain.exchange_instrument_id,
                    position_side="long",
                    order_side="buy",
                    quantity=command.payload.quantity,
                    reduce_only=False,
                )
            )
            return VenueTruthSnapshot(
                lookup_status="visible" if visible else "absent",
                order=order,
                position_quantity=0,
                matching_fill_quantity=0,
                regular_open_client_order_ids=(),
                conditional_open_client_order_ids=(),
                observed_at_ms=2200,
            )

    recovered = await recover_unknown_command(
        lambda: PostgresKernelUnitOfWork(engine),
        Truth(),
        RecoverUnknownCommandRequest(
            command_id=result.command_id,
            now_ms=2200,
            visibility_deadline_ms=2100,
            timeout_seconds=1,
        ),
    )
    assert recovered.status.value == (
        "reconciled_submitted" if visible else "lookup_failed"
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        aggregate = await uow.aggregates.get(t.identity.ticket_id)
        assert aggregate.status.value == (
            "entry_accepted" if visible else "entry_outcome_unknown"
        )
        control = await uow.directional_risk.get(
            "binance-usdm", t.identity.netting_domain.account_id
        )
        assert control.pending_view == "bearish"
        assert (
            len(await uow.exchange_commands.list_for_ticket(t.identity.ticket_id)) == 1
        )
    async with engine.connect() as c:
        assert (
            await c.scalar(sa.select(entry_send_authorizations.c.completed_at_ms))
            is None
        )


@pytest.mark.asyncio
async def test_change_is_durable_cas_idempotent_and_not_replayed(head_template_engine):
    async with head_template_engine.begin() as c:
        repo = PostgresDirectionalRiskRepository(c)
        await repo.initialize(venue_id="binance-usdm", account_id="test", now_ms=1_000)
        result = await repo.request_change(change())
        assert result.view == "bearish" and result.version == 2
    async with head_template_engine.begin() as c:
        repo = PostgresDirectionalRiskRepository(c)
        assert (await repo.request_change(change())).version == 2
        assert (
            await repo.request_receipt("binance-usdm", "test", "one")
        ).view == "bearish"
        assert await repo.request_receipt("binance-usdm", "other", "one") is None
        with pytest.raises(ValueError, match="directional_version_conflict"):
            await repo.request_change(change("two"))
        with pytest.raises(ValueError, match="directional_idempotency_conflict"):
            await repo.request_change(change(view="bullish"))


@pytest.mark.asyncio
async def test_pending_control_recovers_when_another_safety_path_resolved_command(
    head_template_engine,
):
    from src.trading_kernel.application.recover_directional_transition import (
        recover_directional_transition_once,
    )
    from src.trading_kernel.domain.venue_truth import VenueTruthSnapshot

    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    domain = t.identity.netting_domain
    async with engine.begin() as c:
        command_id = await c.scalar(sa.select(exchange_commands.c.command_id))
        await c.execute(
            sa.update(exchange_commands).values(
                status="claimed", claim_owner="sender", lease_until_ms=6000
            )
        )
        repo = PostgresDirectionalRiskRepository(c)
        await repo.authorize_send(
            command_id=command_id,
            venue_id=domain.venue_id,
            account_id=domain.account_id,
            worker_id="sender",
            now_ms=1500,
            deadline_at_ms=t.expires_at_ms,
            valid_until_ms=t.expires_at_ms,
            control=await repo.get(domain.venue_id, domain.account_id),
        )
        await repo.request_change(
            change().model_copy(update={"account_id": domain.account_id})
        )
        await c.execute(sa.update(exchange_commands).values(status="reconciled_absent"))

    class Truth:
        async def lookup_command_truth(self, request):
            assert request.command_id == command_id
            assert request.entry_window_expires_at_ms == 6500
            return VenueTruthSnapshot(
                lookup_status="absent",
                position_quantity=0,
                matching_fill_quantity=0,
                regular_open_client_order_ids=(),
                conditional_open_client_order_ids=(),
                observed_at_ms=10000,
                exchange_observed_at_ms=9000,
            )

    assert await recover_directional_transition_once(
        lambda: PostgresKernelUnitOfWork(engine),
        Truth(),
        now_ms=10000,
        timeout_seconds=1,
        worker_id="reconciler",
        runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
    )
    async with engine.connect() as c:
        control = await PostgresDirectionalRiskRepository(c).get(
            domain.venue_id, domain.account_id
        )
        assert control.view == "bearish" and control.pending_view is None


@pytest.mark.asyncio
async def test_control_lock_serializes_competing_mutations(head_template_engine):
    async with head_template_engine.begin() as c:
        await PostgresDirectionalRiskRepository(c).initialize(
            venue_id="binance-usdm", account_id="test", now_ms=1_000
        )
    first = asyncio.Event()
    release = asyncio.Event()
    second_backend = asyncio.get_running_loop().create_future()

    async def writer_one():
        async with head_template_engine.begin() as c:
            result = await PostgresDirectionalRiskRepository(c).request_change(change())
            first.set()
            await release.wait()
            return result

    async def writer_two():
        await first.wait()
        async with head_template_engine.begin() as c:
            second_backend.set_result(
                await c.scalar(sa.text("SELECT pg_backend_pid()"))
            )
            return await PostgresDirectionalRiskRepository(c).request_change(
                change("two", view="bullish")
            )

    one = asyncio.create_task(writer_one())
    two = asyncio.create_task(writer_two())
    try:
        await asyncio.wait_for(first.wait(), 5)
        pid = await asyncio.wait_for(second_backend, 5)
        async with head_template_engine.connect() as observer, asyncio.timeout(5):
            # Observe a real blocked advisory acquisition before releasing the
            # first writer, so a merely sequential fixture cannot satisfy this.
            while not await observer.scalar(
                sa.text(
                    "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=:pid AND locktype='advisory' AND NOT granted)"
                ),
                {"pid": pid},
            ):
                await asyncio.sleep(0.01)
        release.set()
        assert (await one).view == "bearish"
        with pytest.raises(ValueError, match="directional_version_conflict"):
            await two
    finally:
        release.set()
        await asyncio.gather(one, two, return_exceptions=True)
