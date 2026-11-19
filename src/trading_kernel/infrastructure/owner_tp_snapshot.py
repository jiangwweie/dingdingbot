"""An active TP observation must agree with the later current-order snapshot."""

from decimal import Decimal

from src.trading_kernel.domain.commands import OrderCommandPayload
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)


def require_current_tp_snapshot(
    rows: list,
    *,
    payload: OrderCommandPayload,
    domain: NettingDomain,
    order_id: str,
    client_id: str,
    previous_executed_quantity: Decimal,
    previous_updated_at_ms: int,
    observed_at_ms: int,
) -> None:
    matches = [row for row in rows if isinstance(row, dict) and str(row.get('orderId')) == order_id]
    if len(matches) != 1:
        raise ValueError('owner_tp_snapshot_missing_or_duplicate')
    row = matches[0]
    if (
        row.get('symbol') != parse_binance_usdm_instrument_id(domain.exchange_instrument_id).symbol
        or row.get('positionSide') != domain.position_side.upper()
        or row.get('side') != payload.side.upper()
        or row.get('clientOrderId') != client_id
        or row.get('type') != 'LIMIT'
        or row.get('timeInForce') != payload.time_in_force
        or row.get('status') not in {'NEW', 'PARTIALLY_FILLED'}
        or Decimal(str(row.get('origQty'))) != payload.quantity
        or Decimal(str(row.get('price'))) != payload.limit_price
        or Decimal(str(row.get('executedQty'))) != previous_executed_quantity
        or not previous_updated_at_ms <= int(row.get('updateTime', 0)) <= observed_at_ms
    ):
        raise ValueError('owner_tp_snapshot_changed')
