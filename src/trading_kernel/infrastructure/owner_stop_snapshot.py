"""Require a newer complete open-order page to confirm an exact live Stop."""

from collections.abc import Mapping, Sequence
from decimal import Decimal

from src.trading_kernel.application.owner_operation_facts import OwnerStopSnapshotError
from src.trading_kernel.domain.commands import OrderCommandPayload
from src.trading_kernel.domain.identities import NettingDomain


def require_current_stop_snapshot(
    rows: Sequence[object],
    *,
    payload: OrderCommandPayload,
    domain: NettingDomain,
    order_id: str,
    client_id: str,
    previous_updated_at_ms: int,
    observed_at_ms: int,
) -> None:
    matches = [
        r for r in rows if isinstance(r, Mapping) and str(r.get("algoId")) == order_id
    ]
    if len(matches) != 1:
        raise OwnerStopSnapshotError("owner_stop_snapshot_missing_or_duplicated")
    r = matches[0]
    # Binance can echo reduceOnly=true on close-all STOP_MARKET reads even
    # though placement omits that flag. The close-all and zero-quantity
    # checks below still apply to the current order.
    allows_binance_reduce_only_echo = (
        domain.venue_id == "binance-usdm" and payload.order_type == "stop_market"
    )
    try:
        q = Decimal(str(r["quantity"]))
        executed = Decimal(str(r.get("actualQty") or "0"))
        price = Decimal(str(r["triggerPrice"]))
        updated = int(r["updateTime"])
        if (
            r.get("symbol") != domain.exchange_instrument_id.split(":")[1]
            or r.get("positionSide") != domain.position_side.upper()
            or r.get("side") != payload.side.upper()
            or r.get("clientAlgoId") != client_id
            or r.get("orderType") != payload.order_type.upper()
            or r.get("algoStatus") != "NEW"
            or r.get("workingType") != "CONTRACT_PRICE"
            or r.get("priceProtect") is not False
            or type(r.get("reduceOnly")) is not bool
            or payload.close_position
            and r["reduceOnly"]
            and not allows_binance_reduce_only_echo
            or str(r.get("actualOrderId") or "") not in {"", "0"}
            or type(r.get("closePosition")) is not bool
            or r["closePosition"] != payload.close_position
            or not q.is_finite()
            or q != (Decimal(0) if payload.close_position else payload.quantity)
            or not executed.is_finite()
            or executed != 0
            or not price.is_finite()
            or price != payload.stop_price
            or not previous_updated_at_ms <= updated <= observed_at_ms
        ):
            raise OwnerStopSnapshotError("owner_stop_snapshot_terms_or_state_changed")
    except (KeyError, TypeError, ArithmeticError) as exc:
        raise OwnerStopSnapshotError("owner_stop_snapshot_protocol_invalid") from exc
