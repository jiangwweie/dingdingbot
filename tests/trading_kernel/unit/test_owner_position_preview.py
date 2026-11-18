from decimal import Decimal as D

import pytest

from src.trading_kernel.domain.owner_position_operation import (
    preview_position_operation,
)
from tests.trading_kernel.support.owner_reduction import aggregate, facts


@pytest.mark.parametrize('kind,values',[
    ('protection_tighten', {'price': D(59500)}),
    ('manual_tp_set', {'price': D(63000), 'quantity': D('.0002')}),
    ('position_close', {}),
])
def test_preview_freezes_owner_intent_without_modifying_original_strategy(kind, values):
    a = aggregate()
    p = preview_position_operation(aggregate=a, facts=facts(a), kind=kind,
        quantity_step=D('.0001'), price_tick=D('.1'), minimum_quantity=D('.0001'), minimum_notional=D(1),
        now_ms=3000, **values)
    assert p.kind == kind and p.management_revision == a.management_revision
    assert p.source_quantity == a.position_qty
    assert p.expires_at_ms == 33000


@pytest.mark.parametrize('price', [D(58500), D(61000)])
def test_stop_preview_refuses_widening_or_crossed_stop(price):
    with pytest.raises(ValueError):
        preview_position_operation(aggregate=aggregate(), facts=facts(), kind='protection_tighten', price=price,
            quantity_step=D('.0001'), price_tick=D('.1'), minimum_quantity=D('.0001'), minimum_notional=D(1), now_ms=3000)
