"""Shared current-kernel command-dispatch setup for tests.

This module owns reusable input builders and progression helpers.  It contains
no tests and imports no ``test_*`` module.
"""

from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.issue_ticket import IssueTicketStatus, issue_ticket
from src.trading_kernel.application.reconcile_ticket import (
    ExitTicketRequest,
    ReconcileTicketRequest,
    reconcile_ticket,
    request_exit,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.events import PostFillStressAssessed
from src.trading_kernel.domain.identities import TicketIdentity
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_models import (
    owner_policy_current,
    runtime_capabilities_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.capacity_claims import (
    make_issue_request,
    make_stress_evidence,
)
from tests.trading_kernel.support.dispatch_venues import AcceptingVenue, PreflightFacts
from tests.trading_kernel.support.runtime_scope import seed_ticket_runtime_scope
from tests.trading_kernel.support.tickets import make_ticket


def registered_sor_ticket():
    base = make_ticket()
    runtime = base.identity.runtime.model_copy(
        update={
            "strategy_group_id": "SOR-001",
            "strategy_version_id": "sgv:SOR-001:v4",
            "event_spec_id": "event_spec:SOR-001:SOR-LONG:v4",
        }
    )
    identity = TicketIdentity(
        ticket_id=build_ticket_id(
            signal_event_id=base.identity.signal_event_id,
            runtime=runtime,
            netting_domain=base.identity.netting_domain,
        ),
        exposure_episode_id=base.identity.exposure_episode_id,
        signal_event_id=base.identity.signal_event_id,
        runtime=runtime,
        netting_domain=base.identity.netting_domain,
    )
    return base.model_copy(update={"identity": identity})


def ticket():
    return registered_sor_ticket()


async def seed_policy(
    engine: AsyncEngine,
    *,
    event_spec_id: str = "event_spec:SOR-001:SOR-LONG:v4",
    event_spec_ids: tuple[str, ...] | None = None,
) -> None:
    authorized_event_spec_ids = event_spec_ids or (event_spec_id,)
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_policy_current).values(
                owner_policy_id="policy-main",
                policy_version=7,
                enabled=True,
                new_entry_submit_enabled=True,
                priority_rank=1,
                max_concurrent_tickets=3,
                max_strategy_group_concurrent_tickets=2,
                family_ticket_limits={
                    "long_continuation": 1,
                    "opening_range": 2,
                    "rally_failure_short": 1,
                },
                max_ticket_stop_risk_fraction="0.02",
                max_gross_stop_risk_fraction="0.06",
                max_ticket_initial_margin_fraction="0.30",
                max_gross_initial_margin_utilization="0.90",
                directional_stop_risk_limit_fraction="0.04",
                min_materialization_ratio="0.50",
                max_leverage=10,
                supported_margin_mode="cross",
                post_stop_stress_multiple="2.0",
                max_post_fill_stop_risk_overrun_fraction="0.10",
                scope={
                    "event_runtime_profiles": [
                        {
                            "event_spec_id": authorized_event_spec_id,
                            "runtime_profile_id": "tiny-live-v1",
                        }
                        for authorized_event_spec_id in authorized_event_spec_ids
                    ]
                },
                updated_at_ms=1_000,
            )
        )


async def issue(
    engine: AsyncEngine,
    ticket,
    *,
    ticket_margin_budget: Decimal = Decimal(30),
) -> None:
    await seed_ticket_runtime_scope(engine, ticket)
    async with engine.begin() as connection:
        await connection.execute(
            pg_insert(runtime_capabilities_current)
            .values(
                capability_key="exchange_commands",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                certification={},
                updated_at_ms=1_000,
            )
            .on_conflict_do_update(
                index_elements=[runtime_capabilities_current.c.capability_key],
                set_={
                    "enabled": True,
                    "certified_commit": "kernel-test-head",
                    "schema_revision": CURRENT_SCHEMA_REVISION,
                    "certification": {},
                    "updated_at_ms": 1_000,
                },
            )
        )
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await issue_ticket(
            uow,
            make_issue_request(
                ticket=ticket,
                now_ms=1_001,
                claim_owner="issuer-1",
                ticket_margin_budget=ticket_margin_budget,
            ),
        )
    assert result.status is IssueTicketStatus.ISSUED


async def commit_passed_post_fill_stress_if_pending(
    engine: AsyncEngine,
    ticket_id: str,
) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        aggregate = await uow.aggregates.get(ticket_id)
        if (
            aggregate is not None
            and aggregate.status is AggregateStatus.POST_FILL_RISK_PENDING
        ):
            assert aggregate.average_fill_price is not None
            assert aggregate.initial_stop_exchange_order_id is not None
            event = PostFillStressAssessed(
                event_id=f"event:{ticket_id}:{aggregate.last_event_sequence + 1}",
                ticket_id=ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=2_200,
                status="passed",
                evidence=make_stress_evidence(aggregate.ticket),
                owner_policy_id=aggregate.ticket.owner_policy_id,
                owner_policy_version=aggregate.ticket.owner_policy_version,
                filled_qty=aggregate.position_qty,
                average_fill_price=aggregate.average_fill_price,
                initial_stop_price=aggregate.ticket.initial_stop_price,
                initial_stop_exchange_order_id=aggregate.initial_stop_exchange_order_id,
            )
            await uow.commit_reduction(
                event=event,
                reduction=reduce_event(aggregate, event),
                expected_version=aggregate.version,
            )


async def dispatch_for_ticket(
    engine: AsyncEngine,
    venue,
    ticket_id: str,
    *,
    now_ms: int = 2_200,
) -> None:
    await commit_passed_post_fill_stress_if_pending(engine, ticket_id)
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id="lifecycle-dispatcher",
            ticket_id=ticket_id,
            now_ms=now_ms,
            lease_until_ms=now_ms + 5_000,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )
    assert result.status is DispatchCommandStatus.ACCEPTED
    await commit_passed_post_fill_stress_if_pending(engine, ticket_id)


async def reach_cancel_pending(
    engine: AsyncEngine,
    ticket,
    accepting: AcceptingVenue,
) -> None:
    await issue(engine, ticket)
    await dispatch_for_ticket(
        engine, accepting, ticket.identity.ticket_id, now_ms=1_100
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=Decimal(60000),
                    venue_reported_liquidation_price=Decimal(0),
                    observed_at_ms=2_100,
                ),
            ),
        )
    await dispatch_for_ticket(
        engine, accepting, ticket.identity.ticket_id, now_ms=2_200
    )
    await dispatch_for_ticket(
        engine, accepting, ticket.identity.ticket_id, now_ms=2_300
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="strategy_exit",
                requested_at_ms=3_000,
            ),
        )
    await dispatch_for_ticket(
        engine, accepting, ticket.identity.ticket_id, now_ms=3_100
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    observed_at_ms=3_200,
                ),
            ),
        )
