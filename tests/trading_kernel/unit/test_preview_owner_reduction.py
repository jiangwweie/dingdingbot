from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.application.preview_owner_reduction import (
    PreviewOwnerReductionRequest,
    build_owner_reduction_preview,
)
from tests.trading_kernel.support.owner_reduction import aggregate, facts


@pytest.mark.asyncio
async def test_preview_reads_one_ticket_and_never_commits():
    a = aggregate()
    uow = SimpleNamespace(
        aggregates=SimpleNamespace(get=AsyncMock(return_value=a)),
        commit_reduction=AsyncMock(),
    )
    request = PreviewOwnerReductionRequest(
        ticket_id=a.identity.ticket_id,
        expected_version=a.version,
        requested_quantity=a.position_qty / 2,
        quantity_step=D(".0001"),
        minimum_quantity=D(".0001"),
        minimum_notional=D(1),
        facts=facts(a),
        now_ms=3000,
    )
    p = await build_owner_reduction_preview(uow, request)
    assert p.ticket_id == a.identity.ticket_id
    uow.aggregates.get.assert_awaited_once_with(a.identity.ticket_id)
    uow.commit_reduction.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_missing_or_stale_ticket_has_no_preview(missing):
    a = aggregate()
    uow = SimpleNamespace(
        aggregates=SimpleNamespace(get=AsyncMock(return_value=None if missing else a))
    )
    req = PreviewOwnerReductionRequest(
        ticket_id=a.identity.ticket_id,
        expected_version=a.version + 1,
        requested_quantity=a.position_qty / 2,
        quantity_step=D(".0001"),
        minimum_quantity=D(".0001"),
        minimum_notional=D(1),
        facts=facts(a),
        now_ms=3000,
    )
    with pytest.raises(ValueError, match="ticket_missing|version_changed"):
        await build_owner_reduction_preview(uow, req)
