from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.domain.risk_budget import RiskBudgetChangeRequest
from src.trading_kernel.infrastructure.pg_directional_risk_repository import (
    PostgresDirectionalRiskRepository,
)
from src.trading_kernel.infrastructure.pg_models import owner_policy_current
from tests.trading_kernel.support.command_dispatch import seed_policy


def change(**kwargs):
    return RiskBudgetChangeRequest(
        **(
            {
                "venue_id": "binance-usdm",
                "account_id": "experiment-1",
                "owner_policy_id": "policy-main",
                "expected_policy_version": 1,
                "expected_directional_version": 1,
                "baseline": "0.03",
                "owner_identity": "owner",
                "reason": "increase",
                "idempotency_key": "budget-1",
                "requested_at_ms": 2000,
            }
            | kwargs
        )
    )


@pytest.mark.asyncio
async def test_budget_change_atomic_idempotent_and_preserves_entry(
    head_template_engine,
):
    engine = head_template_engine
    await seed_policy(engine)
    async with engine.begin() as c:
        repo = PostgresDirectionalRiskRepository(c)
        await repo.initialize(
            venue_id="binance-usdm", account_id="experiment-1", now_ms=1000
        )
        policy = (await c.execute(sa.select(owner_policy_current))).mappings().one()
        req = change(expected_policy_version=policy["policy_version"])
        result = await repo.request_budget_change(req)
        assert result.status == "effective"
        updated = (await c.execute(sa.select(owner_policy_current))).mappings().one()
        assert updated["max_ticket_stop_risk_fraction"] == Decimal(".03")
        assert updated["max_gross_stop_risk_fraction"] == Decimal(".09")
        assert updated["directional_stop_risk_limit_fraction"] == Decimal(".06")
        assert updated["new_entry_submit_enabled"] == policy["new_entry_submit_enabled"]
        assert updated["policy_version"] == policy["policy_version"] + 1
        assert await repo.request_budget_change(req) == result
        assert (await repo.get("binance-usdm", "experiment-1")).view == "unset"


@pytest.mark.asyncio
async def test_budget_same_value_does_not_rotate_policy(head_template_engine):
    engine = head_template_engine
    await seed_policy(engine)
    async with engine.begin() as c:
        await PostgresDirectionalRiskRepository(c).initialize(
            venue_id="binance-usdm", account_id="experiment-1", now_ms=1000
        )
        version = await c.scalar(sa.select(owner_policy_current.c.policy_version))
        result = await PostgresDirectionalRiskRepository(c).request_budget_change(
            change(baseline=".02", expected_policy_version=version)
        )
        assert result.status == "unchanged"
        assert (
            await c.scalar(sa.select(owner_policy_current.c.policy_version)) == version
        )


@pytest.mark.asyncio
async def test_budget_waits_for_exact_inflight_send_and_preserves_concurrent_pause(
    head_template_engine,
):
    from src.trading_kernel.infrastructure.pg_models import entry_send_authorizations
    from tests.trading_kernel.support.command_dispatch import issue, ticket

    engine = head_template_engine
    await seed_policy(engine)
    t = ticket()
    await issue(engine, t)
    async with engine.begin() as c:
        command_id = await c.scalar(
            sa.text(
                "SELECT command_id FROM brc_exchange_commands WHERE command_kind='entry'"
            )
        )
        # All-account authorization, including a non-Crypto control=NULL sender.
        await c.execute(
            sa.insert(entry_send_authorizations).values(
                command_id=command_id,
                venue_id="binance-usdm",
                account_id="experiment-1",
                worker_id="sender",
                authorized_at_ms=1500,
                expires_at_ms=2500,
            )
        )
        repo = PostgresDirectionalRiskRepository(c)
        req = change(expected_policy_version=7)
        assert (await repo.request_budget_change(req)).status == "pending"
        assert await c.scalar(
            sa.select(owner_policy_current.c.max_ticket_stop_risk_fraction)
        ) == Decimal(".02")
        assert (
            await repo.progress("binance-usdm", "experiment-1", 3000)
        ).pending_baseline == Decimal(".03")
        await c.execute(
            sa.update(owner_policy_current).values(
                new_entry_submit_enabled=False, policy_version=8, updated_at_ms=3001
            )
        )
        await repo.finish_send(command_id, 3002)
        current = await repo.progress("binance-usdm", "experiment-1", 3003)
        assert current.pending_baseline is None
        assert (
            await c.scalar(sa.select(owner_policy_current.c.new_entry_submit_enabled))
            is False
        )
        assert await c.scalar(sa.select(owner_policy_current.c.policy_version)) == 9
        assert (
            await repo.budget_receipt("binance-usdm", "experiment-1", "budget-1")
        ).status == "effective"


@pytest.mark.asyncio
async def test_budget_request_during_preflight_rejects_old_ticket_without_sending(
    head_template_engine,
):
    import asyncio

    from src.trading_kernel.application.dispatch_exchange_command import (
        DispatchCommandRequest,
        dispatch_one_command,
    )
    from src.trading_kernel.infrastructure.pg_unit_of_work import (
        PostgresKernelUnitOfWork,
    )
    from src.trading_kernel.infrastructure.runtime_identity import (
        CURRENT_SCHEMA_REVISION,
    )
    from tests.trading_kernel.support.command_dispatch import issue, ticket
    from tests.trading_kernel.support.dispatch_venues import (
        CountingVenue,
        PreflightFacts,
    )

    engine = head_template_engine
    await seed_policy(engine)
    t = ticket()
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
            DispatchCommandRequest(
                worker_id="sender",
                ticket_id=t.identity.ticket_id,
                now_ms=1100,
                lease_until_ms=6100,
                timeout_seconds=5,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                admission_snapshot_validity_ms=1000,
            ),
            entry_facts_source=Facts(),
            clock_ms=lambda: 2100,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 5)
        async with engine.begin() as c:
            assert (
                await PostgresDirectionalRiskRepository(c).request_budget_change(
                    change(expected_policy_version=7)
                )
            ).status == "effective"
        release.set()
        await task
        assert venue.calls == 0
        async with engine.connect() as c:
            assert (
                await c.scalar(sa.text("SELECT status FROM brc_budget_reservations"))
                == "released"
            )
            assert (
                await c.scalar(sa.text("SELECT status FROM brc_entry_lane_current"))
                == "idle"
            )
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_authentic_owner_resume_survives_budget_change_but_not_pause(
    head_template_engine,
):
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        set_global_entry_state,
    )
    from src.trading_kernel.infrastructure.entry_restoration_certification import (
        read_entry_restoration_state,
    )
    from src.trading_kernel.infrastructure.pg_unit_of_work import (
        PostgresKernelUnitOfWork,
    )
    from tests.trading_kernel.support.command_dispatch import issue, ticket

    engine = head_template_engine
    await seed_policy(engine)
    await issue(engine, ticket())
    # Pause then authenticated resume via the official path; readiness is not
    # the assertion here, so freeze the existing scope before policy mutation.
    async with engine.begin() as c:
        await c.execute(
            sa.update(owner_policy_current).values(new_entry_submit_enabled=False)
        )
    async with PostgresKernelUnitOfWork(engine) as uow:
        from unittest.mock import AsyncMock

        uow.owner_controls.get_global_entry_resume_blocker = AsyncMock(
            return_value=None
        )
        await set_global_entry_state(
            uow,
            owner_policy_id="policy-main",
            enabled=True,
            request=ControlMutationRequest(
                expected_version=7,
                owner_identity="owner",
                reason="resume",
                idempotency_key="resume",
                now_ms=1800,
            ),
            authentication_strength="totp_step_up",
        )
    async with engine.begin() as c:
        assert (
            await read_entry_restoration_state(c, now_ms=1900)
        ).owner_resume_authorized
        await PostgresDirectionalRiskRepository(c).request_budget_change(
            change(expected_policy_version=8)
        )
        assert (
            await read_entry_restoration_state(c, now_ms=2100)
        ).owner_resume_authorized
        await c.execute(
            sa.update(owner_policy_current).values(new_entry_submit_enabled=False)
        )
        assert not (
            await read_entry_restoration_state(c, now_ms=2200)
        ).owner_resume_authorized


@pytest.mark.asyncio
async def test_database_refuses_direct_risk_change_without_owner_request(
    head_template_engine,
):
    from sqlalchemy.exc import DBAPIError

    await seed_policy(head_template_engine)
    with pytest.raises(DBAPIError, match="authenticated policy transition"):
        async with head_template_engine.begin() as c:
            await c.execute(
                sa.update(owner_policy_current).values(
                    max_ticket_stop_risk_fraction=Decimal(".03"),
                    max_gross_stop_risk_fraction=Decimal(".09"),
                    directional_stop_risk_limit_fraction=Decimal(".06"),
                )
            )


@pytest.mark.asyncio
async def test_risk_budget_must_not_overwrite_pending_direction_and_rejects_key_reuse(
    head_template_engine,
):
    from src.trading_kernel.domain.directional_risk import DirectionalChangeRequest
    from src.trading_kernel.infrastructure.pg_models import entry_send_authorizations
    from tests.trading_kernel.support.command_dispatch import issue, ticket

    engine = head_template_engine
    await seed_policy(engine)
    await issue(engine, ticket())
    async with engine.begin() as c:
        repo = PostgresDirectionalRiskRepository(c)
        command_id = await c.scalar(
            sa.text(
                "SELECT command_id FROM brc_exchange_commands WHERE command_kind='entry'"
            )
        )
        await c.execute(
            sa.insert(entry_send_authorizations).values(
                command_id=command_id,
                venue_id="binance-usdm",
                account_id="experiment-1",
                worker_id="sender",
                authorized_at_ms=1500,
                expires_at_ms=2500,
            )
        )
        await repo.request_change(
            DirectionalChangeRequest(
                venue_id="binance-usdm",
                account_id="experiment-1",
                expected_version=1,
                view="bearish",
                owner_identity="owner",
                reason="direction",
                idempotency_key="direction",
                requested_at_ms=1800,
            )
        )
        with pytest.raises(ValueError, match="transition_pending"):
            await repo.request_budget_change(
                change(expected_policy_version=7, expected_directional_version=2)
            )
        await repo.finish_send(command_id, 1900)
        await repo.progress("binance-usdm", "experiment-1", 1901)
        control = await repo.get("binance-usdm", "experiment-1")
        req = change(
            expected_policy_version=7, expected_directional_version=control.version
        )
        await repo.request_budget_change(req)
        with pytest.raises(ValueError, match="idempotency_conflict"):
            await repo.request_budget_change(
                req.model_copy(update={"baseline": Decimal(".025")})
            )


@pytest.mark.asyncio
async def test_same_schema_release_preserves_owner_selected_risk(head_template_engine):
    from src.trading_kernel.infrastructure.pg_unit_of_work import (
        PostgresKernelUnitOfWork,
    )
    from src.trading_kernel.infrastructure.runtime_authority_seed import (
        RuntimeAuthoritySeedRequest,
        deploy_runtime_identity,
    )
    from src.trading_kernel.infrastructure.runtime_identity import (
        CURRENT_SCHEMA_REVISION,
    )

    engine = head_template_engine
    initial = RuntimeAuthoritySeedRequest(
        account_id="experiment-1",
        runtime_commit="a" * 40,
        schema_revision=CURRENT_SCHEMA_REVISION,
        seeded_at_ms=1000,
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await deploy_runtime_identity(uow, initial)
    async with engine.begin() as c:
        await PostgresDirectionalRiskRepository(c).request_budget_change(change())
        old = (await c.execute(sa.select(owner_policy_current))).mappings().one()
    async with PostgresKernelUnitOfWork(engine) as uow:
        await deploy_runtime_identity(
            uow,
            initial.model_copy(
                update={"runtime_commit": "b" * 40, "seeded_at_ms": 3000}
            ),
        )
    async with engine.connect() as c:
        new = (await c.execute(sa.select(owner_policy_current))).mappings().one()
        assert dict(new) == dict(old)
        assert new["max_ticket_stop_risk_fraction"] == Decimal(".03")


@pytest.mark.asyncio
async def test_certification_checks_owner_budget_journal_and_formula(
    head_template_engine,
):
    from src.trading_kernel.infrastructure.pg_unit_of_work import (
        PostgresKernelUnitOfWork,
    )
    from src.trading_kernel.infrastructure.risk_budget_certification import (
        risk_budget_authority_valid,
    )
    from src.trading_kernel.infrastructure.runtime_authority_seed import (
        RuntimeAuthoritySeedRequest,
        deploy_runtime_identity,
    )
    from src.trading_kernel.infrastructure.runtime_identity import (
        CURRENT_SCHEMA_REVISION,
    )

    engine = head_template_engine
    async with PostgresKernelUnitOfWork(engine) as uow:
        await deploy_runtime_identity(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="experiment-1",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1000,
            ),
        )
    async with engine.begin() as c:
        policy = (await c.execute(sa.select(owner_policy_current))).mappings().one()
        assert await risk_budget_authority_valid(c, policy)
        await PostgresDirectionalRiskRepository(c).request_budget_change(change())
        policy = (await c.execute(sa.select(owner_policy_current))).mappings().one()
        assert await risk_budget_authority_valid(c, policy)
        forged = dict(policy)
        forged["max_gross_stop_risk_fraction"] = Decimal(".12")
        assert not await risk_budget_authority_valid(c, forged)


@pytest.mark.asyncio
async def test_budget_waits_during_actual_network_send_then_applies(
    head_template_engine,
):
    import asyncio

    from src.trading_kernel.application.dispatch_exchange_command import (
        DispatchCommandRequest,
        dispatch_one_command,
    )
    from src.trading_kernel.domain.commands import ExchangeCommandResult
    from src.trading_kernel.infrastructure.pg_unit_of_work import (
        PostgresKernelUnitOfWork,
    )
    from src.trading_kernel.infrastructure.runtime_identity import (
        CURRENT_SCHEMA_REVISION,
    )
    from tests.trading_kernel.support.command_dispatch import issue, ticket
    from tests.trading_kernel.support.dispatch_venues import PreflightFacts

    engine = head_template_engine
    await seed_policy(engine)
    t = ticket()
    await issue(engine, t)
    started = asyncio.Event()
    release = asyncio.Event()

    class Venue:
        async def execute(self, request):
            assert request.entry_authorized_at_ms == 1100
            started.set()
            await release.wait()
            return ExchangeCommandResult(
                status="accepted",
                observed_at_ms=2100,
                exchange_order_id="budget-inflight-accepted",
            )

    task = asyncio.create_task(
        dispatch_one_command(
            lambda: PostgresKernelUnitOfWork(engine),
            Venue(),
            DispatchCommandRequest(
                worker_id="sender",
                ticket_id=t.identity.ticket_id,
                now_ms=1100,
                lease_until_ms=6100,
                timeout_seconds=5,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                admission_snapshot_validity_ms=1000,
            ),
            entry_facts_source=PreflightFacts(),
            clock_ms=lambda: 1100,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 5)
        async with engine.begin() as c:
            assert (
                await PostgresDirectionalRiskRepository(c).request_budget_change(
                    change(expected_policy_version=7, requested_at_ms=1500)
                )
            ).status == "pending"
            assert await c.scalar(
                sa.select(owner_policy_current.c.max_ticket_stop_risk_fraction)
            ) == Decimal(".02")
        release.set()
        assert (await task).status.value == "accepted"
        async with engine.connect() as c:
            assert await c.scalar(
                sa.select(owner_policy_current.c.max_ticket_stop_risk_fraction)
            ) == Decimal(".03")
            assert (
                await PostgresDirectionalRiskRepository(c).get(
                    "binance-usdm", "experiment-1"
                )
            ).pending_baseline is None
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
