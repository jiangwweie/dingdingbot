"""Real local ledger setup for delayed Owner execution and recovery tests."""

from decimal import Decimal as D

import sqlalchemy as sa

from src.trading_kernel.application.owner_operation_facts import (
    OwnerReductionObservation,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind as K,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandStatus as S,
)
from src.trading_kernel.domain.owner_position_operation import (
    preview_position_operation,
)
from src.trading_kernel.infrastructure.pg_models import runtime_capabilities_current
from src.trading_kernel.infrastructure.pg_owner_position_operations import (
    PostgresOwnerPositionOperations,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.owner_operation_source import OwnerOperationSource
from tests.trading_kernel.support.owner_reduction import (
    accept_signed_operation,
    facts,
    setup_operation,
)


async def accepted_operation(engine, kind, return_owner=False, **params):
    t, device, p, key = await setup_operation(engine)
    async with PostgresKernelUnitOfWork(engine) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        if kind != "position_reduce":
            p = preview_position_operation(
                aggregate=a,
                facts=facts(a, observed_at_ms=6000, valid_until_ms=9000),
                kind=kind,
                quantity_step=D(".0001"),
                price_tick=D(".1"),
                minimum_quantity=D(".0001"),
                minimum_notional=D(1),
                now_ms=6000,
                **params,
            )
    async with engine.begin() as c:
        await c.execute(
            sa.update(runtime_capabilities_current)
            .where(runtime_capabilities_current.c.capability_key == "exchange_commands")
            .values(
                certification={
                    "product_id": "brc-app-manual-v1",
                    "owner_cooperation": "owner-cooperation-v1",
                }
            )
        )
        repo = PostgresOwnerPositionOperations(c)
        op = await repo.create_preview(
            preview=p,
            owner_identity="Owner",
            device_id=device["device_id"],
            device_epoch=1,
            idempotency_key="delayed-preview",
            now_ms=6000,
        )
        op, _ = await accept_signed_operation(c, device, key, op, now_ms=6001)
    return (t, op, device, key) if return_owner else (t, op)


class DelayedSource(OwnerOperationSource):
    calls = 0

    async def read_owner_position(self, **kwargs):
        self.calls += 1
        return await super().read_owner_position(**kwargs)

    async def read_owner_reduction(self, *, aggregate, state, commands, **kwargs):
        self.calls += 1
        o = await self.read_owner_position(
            aggregate=aggregate,
            commands=commands,
            accepted_order_ids=kwargs["accepted_order_ids"],
            operation_id=state.operation_id,
        )
        reductions = [c for c in commands if c.kind is K.OWNER_REDUCE]
        status = "not_sent"
        if reductions:
            c = reductions[-1]
            status = (
                "rejected"
                if c.status in {S.REJECTED, S.RECONCILED_ABSENT, S.SUPERSEDED}
                else "unknown"
                if c.status is S.OUTCOME_UNKNOWN
                else "not_sent"
            )
        return OwnerReductionObservation(
            facts=o.facts.model_copy(
                update={
                    "reduction_state": status,
                    "reduction_operation_id": state.operation_id,
                }
            ),
            protection_close_position=o.protection_close_position,
        )
