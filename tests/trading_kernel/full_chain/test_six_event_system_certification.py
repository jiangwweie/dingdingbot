from __future__ import annotations

import pytest

from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from tests.trading_kernel.support.event_chain import run_event_chain

CASES=tuple((contract,dynamic) for contract in registered_strategy_contracts()
    if contract.strategy_group_id not in {'SOR-US-EQ-PERP-001','SOR-001'}
    for dynamic in ((False,True) if contract.strategy_group_id=='SOR-1H-001' else (False,)))

@pytest.mark.parametrize('contract,hourly_dynamic',CASES,ids=[f"{c.event_id}:{'Dynamic' if dynamic else 'Static'}" for c,dynamic in CASES])
@pytest.mark.asyncio
async def test_registered_event_reaches_terminal_review_from_closed_market_input(head_template_engine,contract,hourly_dynamic):
    await run_event_chain(head_template_engine,contract,hourly_dynamic)
