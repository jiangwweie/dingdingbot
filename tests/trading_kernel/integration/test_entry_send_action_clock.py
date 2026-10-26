"""Real PostgreSQL -> actual venue adapter with an advancing preflight clock."""

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.infrastructure.pg_models import (
    entry_send_authorizations,
    exchange_commands,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter
from tests.trading_kernel.support.command_dispatch import issue, seed_policy, ticket
from tests.trading_kernel.support.dispatch_venues import PreflightFacts


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_clock", [False, True])
async def test_slow_fresh_preflight_starts_window_at_committed_send_right(
    head_template_engine, monkeypatch, explicit_clock
):
    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    now = 1_100
    monkeypatch.setattr(
        "src.trading_kernel.application.dispatch_exchange_command.action_clock_ms",
        lambda: now,
    )
    reads = []

    class Facts(PreflightFacts):
        async def read_entry_admission_snapshot(self, request):
            nonlocal now
            reads.append(request.observed_at_ms)
            result = await super().read_entry_admission_snapshot(request)
            now = (
                13_100  # same 12-second elapsed path as the three production rejections
            )
            return result

    class Exchange:
        def __init__(self):
            self.calls = []

        async def create_order(self, *args):
            async with engine.connect() as c:
                persisted = (
                    (await c.execute(sa.select(entry_send_authorizations)))
                    .mappings()
                    .one()
                )
                assert persisted["authorized_at_ms"] == now
                assert persisted["expires_at_ms"] == now + 5_000
                assert args[-1]["timestamp"] == persisted["authorized_at_ms"]
            self.calls.append(args)
            return {"id": "real-adapter-recording-order"}

    exchange = Exchange()
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange}, clock_ms=lambda: now
    )
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        adapter,
        DispatchCommandRequest(
            worker_id="action-clock",
            ticket_id=t.identity.ticket_id,
            now_ms=1_100,
            lease_until_ms=31_100,
            timeout_seconds=2,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=30_000,
        ),
        entry_facts_source=Facts(),
        **({"clock_ms": lambda: now} if explicit_clock else {}),
    )
    assert result.status is DispatchCommandStatus.ACCEPTED
    assert len(exchange.calls) == 1
    async with engine.connect() as c:
        assert await c.scalar(sa.select(exchange_commands.c.status)) == "accepted"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boundary",
    [
        "facts_expire",
        "deadline",
        "lease",
        "clock_backwards",
        "pause",
        "runtime_fence",
        "after_send_commit",
        "facts_expire_after_commit",
    ],
)
async def test_elapsed_time_and_control_changes_never_refresh_stale_send_authority(
    head_template_engine, boundary
):
    from contextlib import asynccontextmanager

    from src.trading_kernel.infrastructure.pg_models import (
        owner_policy_current,
        runtime_capabilities_current,
    )

    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    now = 1_100
    calls = []
    delay_to = {
        "facts_expire": 13_100,
        "deadline": 31_001,
        "lease": 6_101,
        "clock_backwards": 1_099,
    }.get(boundary, 13_100)

    class Facts(PreflightFacts):
        async def read_entry_admission_snapshot(self, request):
            nonlocal now
            result = await super().read_entry_admission_snapshot(request)
            now = delay_to
            if boundary in {"pause", "runtime_fence"}:
                async with engine.begin() as c:
                    table = (
                        owner_policy_current
                        if boundary == "pause"
                        else runtime_capabilities_current
                    )
                    values = (
                        {"new_entry_submit_enabled": False}
                        if boundary == "pause"
                        else {"enabled": False}
                    )
                    await c.execute(sa.update(table).values(**values))
            return result

    class Exchange:
        async def create_order(self, *args):
            calls.append(args)
            return {"id": "must-not-send"}

    @asynccontextmanager
    async def uow_factory():
        nonlocal now
        async with PostgresKernelUnitOfWork(engine) as uow:
            yield uow
        if boundary in {"after_send_commit", "facts_expire_after_commit"}:
            async with engine.connect() as c:
                expiry = await c.scalar(
                    sa.select(entry_send_authorizations.c.expires_at_ms)
                )
            if expiry is not None:
                now = (
                    13_600 if boundary == "facts_expire_after_commit" else expiry
                ) + 1

    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): Exchange()}, clock_ms=lambda: now
    )
    result = await dispatch_one_command(
        uow_factory,
        adapter,
        DispatchCommandRequest(
            worker_id="action-clock",
            ticket_id=t.identity.ticket_id,
            now_ms=1_100,
            lease_until_ms=6_100 if boundary == "lease" else 61_100,
            timeout_seconds=2,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms={
                "deadline": 60_000,
                "facts_expire": 10_000,
                "facts_expire_after_commit": 12_500,
            }.get(boundary, 30_000),
        ),
        entry_facts_source=Facts(),
        clock_ms=lambda: now,
    )
    assert result.status in {
        DispatchCommandStatus.SUPERSEDED,
        DispatchCommandStatus.REJECTED,
    }
    assert calls == []
    async with engine.connect() as c:
        payload = await c.scalar(sa.select(exchange_commands.c.result_payload))
        assert (
            payload["reason"]
            == {
                "facts_expire": "dispatch_preflight:stale_snapshot",
                "deadline": "dispatch_preflight:deadline_expired",
                "lease": "dispatch_preflight:command_mismatch",
                "clock_backwards": "dispatch_preflight:stale_snapshot",
                "pause": "dispatch_preflight:new_entry_disabled",
                "runtime_fence": "dispatch_preflight:runtime_fenced",
                "after_send_commit": "entry_send_window_expired",
                "facts_expire_after_commit": "entry_send_window_expired",
            }[boundary]
        )
        count = await c.scalar(
            sa.select(sa.func.count()).select_from(entry_send_authorizations)
        )
        assert count == int(
            boundary in {"after_send_commit", "facts_expire_after_commit"}
        )
    repeated = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        adapter,
        DispatchCommandRequest(
            worker_id="action-clock",
            ticket_id=t.identity.ticket_id,
            now_ms=now,
            lease_until_ms=now + 30_000,
            timeout_seconds=2,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=30_000,
        ),
        entry_facts_source=PreflightFacts(),
        clock_ms=lambda: now,
    )
    assert repeated.status is DispatchCommandStatus.NO_COMMAND
    assert calls == []


@pytest.mark.asyncio
async def test_unknown_result_uses_actual_time_and_preserves_unfinished_send(head_template_engine):
    engine = head_template_engine
    t = ticket()
    await seed_policy(engine)
    await issue(engine, t)
    now = 1_100

    class Facts(PreflightFacts):
        async def read_entry_admission_snapshot(self, request):
            nonlocal now
            result = await super().read_entry_admission_snapshot(request)
            now = 13_100
            return result

    class Venue:
        async def execute(self, request):
            assert request.entry_authorized_at_ms == now
            raise TimeoutError('response unavailable')

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine), Venue(),
        DispatchCommandRequest(worker_id='unknown-clock', ticket_id=t.identity.ticket_id,
            now_ms=1_100, lease_until_ms=31_100, timeout_seconds=2,
            runtime_commit='kernel-test-head', schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=30_000),
        entry_facts_source=Facts(), clock_ms=lambda: now)
    assert result.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    async with engine.connect() as c:
        payload = await c.scalar(sa.select(exchange_commands.c.result_payload))
        assert payload['observed_at_ms'] == now
        send = (await c.execute(sa.select(entry_send_authorizations))).mappings().one()
        assert send['completed_at_ms'] is None
        assert send['authorized_at_ms'] == now
