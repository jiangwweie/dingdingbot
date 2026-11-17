"""Real PG preview is read-only and conserves the existing lifecycle."""

from decimal import Decimal as D

import pytest

from src.trading_kernel.application.preview_owner_reduction import (
    PreviewOwnerReductionRequest,
    build_owner_reduction_preview,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)
from tests.trading_kernel.support.owner_reduction import facts


@pytest.mark.asyncio
async def test_pg_preview_does_not_mutate_ticket_or_create_commands(
    head_template_engine,
):
    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    async with PostgresKernelUnitOfWork(e) as u:
        before = await u.aggregates.get(t.identity.ticket_id)
        assert before is not None
        old_commands = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
        req = PreviewOwnerReductionRequest(
            ticket_id=t.identity.ticket_id,
            expected_version=before.version,
            requested_quantity=before.position_qty / 2,
            quantity_step=D(".0001"),
            minimum_quantity=D(".0001"),
            minimum_notional=D(1),
            facts=facts(before, observed_at_ms=7000, valid_until_ms=10000),
            now_ms=7000,
        )
        preview = await build_owner_reduction_preview(u, req)
        assert preview.source_quantity == before.position_qty
    async with PostgresKernelUnitOfWork(e) as u:
        after = await u.aggregates.get(t.identity.ticket_id)
        commands = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
    assert before == after
    assert [c.command_id for c in commands] == [c.command_id for c in old_commands]
