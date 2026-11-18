"""Action-time prices for new Owner exit instructions, distinct from the old Stop."""

from decimal import Decimal

from src.trading_kernel.domain.commands import ExchangeCommandKind, OrderCommandPayload


def owner_command_price_blocker(
    *,
    kind: ExchangeCommandKind,
    payload: OrderCommandPayload,
    position_side: str,
    current_price: Decimal,
) -> str | None:
    if not current_price.is_finite() or current_price <= 0:
        return "owner_command_price_unavailable"
    long = position_side == "long"
    if (
        kind is ExchangeCommandKind.TAKE_PROFIT
        and payload.limit_price is not None
        and (
            payload.limit_price <= current_price
            if long
            else payload.limit_price >= current_price
        )
    ):
        return "owner_tp_target_crossed"
    if (
        kind is ExchangeCommandKind.REPLACE_PROTECTION
        and payload.stop_price is not None
        and (
            payload.stop_price >= current_price
            if long
            else payload.stop_price <= current_price
        )
    ):
        return "owner_new_stop_crossed"
    return None
