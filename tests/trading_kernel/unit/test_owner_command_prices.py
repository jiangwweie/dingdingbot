from decimal import Decimal as D

import pytest

from src.trading_kernel.domain.commands import (
    ExchangeCommandKind as K,
)
from src.trading_kernel.domain.commands import (
    OrderCommandPayload,
)
from src.trading_kernel.domain.owner_command_prices import owner_command_price_blocker


@pytest.mark.parametrize(
    "side,kind,typ,target,current,reason",
    [
        ("long", K.TAKE_PROFIT, "limit", "63000", "64000", "owner_tp_target_crossed"),
        ("short", K.TAKE_PROFIT, "limit", "63000", "62000", "owner_tp_target_crossed"),
        ("long", K.TAKE_PROFIT, "limit", "63000", "63000", "owner_tp_target_crossed"),
        ("short", K.TAKE_PROFIT, "limit", "63000", "63000", "owner_tp_target_crossed"),
        (
            "long",
            K.REPLACE_PROTECTION,
            "stop_market",
            "61000",
            "60000",
            "owner_new_stop_crossed",
        ),
        (
            "short",
            K.REPLACE_PROTECTION,
            "stop_market",
            "59000",
            "60000",
            "owner_new_stop_crossed",
        ),
        ("long", K.TAKE_PROFIT, "limit", "63000", "62000", None),
        ("short", K.TAKE_PROFIT, "limit", "63000", "64000", None),
        ("long", K.REPLACE_PROTECTION, "stop_market", "59000", "60000", None),
    ],
)
def test_pending_command_checks_its_own_price(side, kind, typ, target, current, reason):
    p = OrderCommandPayload(
        side="sell" if side == "long" else "buy",
        quantity=D(".001"),
        order_type=typ,
        reduce_only=True,
        limit_price=D(target) if typ == "limit" else None,
        time_in_force="GTC" if typ == "limit" else None,
        stop_price=D(target) if typ == "stop_market" else None,
        owner_operation_id="op",
    )
    assert (
        owner_command_price_blocker(
            kind=kind, payload=p, position_side=side, current_price=D(current)
        )
        == reason
    )
