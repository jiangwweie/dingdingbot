import pytest

from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


@pytest.mark.asyncio
async def test_opposite_side_is_occupied_in_app_product(head_template_engine):
    t = registered_sor_long_ticket()
    await reach_position_protected(head_template_engine, t)
    other = t.identity.netting_domain.model_copy(update={"position_side": "short"})
    async with PostgresKernelUnitOfWork(head_template_engine) as u:
        assert await u.entry_admission.has_active_ticket_in_domain(other.key())
