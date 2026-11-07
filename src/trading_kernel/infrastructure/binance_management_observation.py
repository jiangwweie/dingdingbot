"""Readonly raw Binance order evidence; no order submission or credential access."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.trading_kernel.domain.trade_management import (
    OrderAction,
    OrderEvidence,
    OrderTerms,
)


class AmendmentReader(Protocol):
    async def fapiPrivateGetOrderAmendment(
        self, params: dict[str, object]
    ) -> object: ...


class OrderAmendment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    amendment_id: str
    order_id: str
    symbol: str
    at_ms: int = Field(gt=0)
    before_price: Decimal = Field(gt=0, allow_inf_nan=False)
    after_price: Decimal = Field(gt=0, allow_inf_nan=False)
    before_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    after_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    modification_count: int = Field(gt=0)


class AmendmentPage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rows: tuple[OrderAmendment, ...]
    possibly_truncated: bool


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise ValueError("order protocol requires an object")
    return value


def _string(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if (
        not isinstance(value, (str, int))
        or isinstance(value, bool)
        or not str(value).strip()
    ):
        raise ValueError("order protocol string/identifier missing")
    return str(value)


def _boolean(row: Mapping[str, object], key: str) -> bool:
    value = row[key]
    if type(value) is not bool:
        raise ValueError("order protocol boolean missing")
    return value


def _integer(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if type(value) is not int or value < 0:
        raise ValueError("order protocol integer missing")
    return value


def _price(
    row: Mapping[str, object], key: str, *, optional: bool = False
) -> str | None:
    if optional and key not in row:
        return None
    value = row[key]
    if not isinstance(value, str):
        raise TypeError("order decimals must be strings")
    decimal = Decimal(value)
    if not decimal.is_finite() or decimal < 0:
        raise ValueError("invalid order decimal")
    return None if decimal == 0 else value


def parse_order_update(
    message: Mapping[str, object],
    *,
    account_id: str,
    received_at_ms: int,
    coverage_complete: bool,
    before_terms: OrderTerms | None = None,
    known_command_outcome_pending: bool = False,
) -> OrderEvidence:
    event_type = _string(message, "e")
    if event_type not in {"ORDER_TRADE_UPDATE", "ALGO_UPDATE"}:
        raise ValueError("not an order event")
    row = _mapping(message["o"])
    algo = event_type == "ALGO_UPDATE"
    symbol = _string(row, "s")
    if not symbol.isalnum() or symbol != symbol.upper():
        raise ValueError("invalid instrument symbol")
    side = _string(row, "ps").lower()
    if side not in {"long", "short"}:
        raise ValueError("independent position side required")
    event_time = _integer(message, "E")
    transaction_time = _integer(message, "T")
    conditional_terms=algo or _string(row,"o") not in {"LIMIT","MARKET"}
    close = _boolean(row, "cp") if conditional_terms or "cp" in row else False
    quantity = _price(row, "q")
    if close and quantity is not None:
        raise ValueError("close-all unexpectedly declares fixed quantity")
    terms = OrderTerms.model_validate(
        {
            "venue_id": "binance-usdm",
            "account_id": account_id,
            "exchange_instrument_id": f"binance-usdm:{symbol}:perpetual",
            "position_side": side,
            "order_namespace": "conditional" if algo else "regular",
            "exchange_order_id": _string(row, "aid" if algo else "i"),
            "client_order_id": _string(row, "caid" if algo else "c"),
            "side": _string(row, "S").lower(),
            "order_type": _string(row, "o"),
            "quantity": quantity,
            "price": _price(row, "p"),
            "trigger_price": _price(row, "tp" if algo else "sp"),
            "close_position": close,
            "reduce_only": _boolean(row, "R"),
            "time_in_force": _string(row, "f"),
            "working_type": _string(row, "wt"),
            "price_protect": _boolean(row, "pP") if conditional_terms or "pP" in row else False,
            "activation_price": _price(row, "AP", optional=True),
            "callback_rate": _price(row, "cr", optional=True),
            "price_match": _string(row, "pm"),
            "self_trade_prevention_mode": _string(row, "V"),
            "good_till_date_ms": _integer(row, "gtd"),
        }
    )
    status = _string(row, "X")
    if algo:
        if status == "NEW":
            # Documented trailing activation pushes NEW again with ia=true.
            if "ia" not in row:
                raise ValueError("algo activation discriminator missing")
            action = OrderAction.STATUS if _boolean(row, "ia") else OrderAction.NEW
        else:
            actions = {
                "CANCELED": OrderAction.CANCEL,
                "TRIGGERING": OrderAction.TRIGGERED,
                "TRIGGERED": OrderAction.TRIGGERED,
                "FINISHED": OrderAction.STATUS,
                "REJECTED": OrderAction.REJECTED,
                "EXPIRED": OrderAction.EXPIRED,
            }
            if status not in actions:
                raise ValueError("unrecognized algo status")
            action = actions[status]
        # Algo execution truth is resolved through actualOrderId/trades, never
        # invented from its status. Missing aq is valid for untriggered orders.
        executed = row.get("aq", "0")
    else:
        execution = _string(row, "x")
        actions = {
            "NEW": OrderAction.NEW,
            "AMENDMENT": OrderAction.AMENDMENT,
            "CANCELED": OrderAction.CANCEL,
            "TRADE": OrderAction.TRADE,
            "EXPIRED": OrderAction.EXPIRED,
            "CALCULATED": OrderAction.STATUS,
        }
        if execution not in actions:
            raise ValueError("unrecognized execution type")
        action = actions[execution]
        executed = row["z"]
    if not isinstance(executed, str):
        raise TypeError("execution quantity must be exact")
    # E/T are time, not unique sequence numbers. Include canonical payload in
    # the evidence identity so distinct same-ms events are never collapsed.
    import hashlib
    import json

    digest = hashlib.sha256(
        json.dumps(dict(message), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return OrderEvidence(
        evidence_id=f"binance-order:{account_id}:{digest}",
        terms=terms,
        action=action,
        exchange_event_at_ms=transaction_time,
        received_at_ms=received_at_ms,
        created_at_ms=_integer(row, "O") if "O" in row else None,
        executed_quantity=Decimal(executed),
        coverage_complete=coverage_complete,
        known_command_outcome_pending=known_command_outcome_pending,
        before_terms=before_terms,
        source_event_at_ms=event_time,
    )


async def read_order_amendments(
    exchange: AmendmentReader,
    *,
    symbol: str,
    order_id: str,
    start_ms: int,
    end_ms: int,
    limit: int = 100,
) -> AmendmentPage:
    if (
        not symbol.isalnum()
        or symbol != symbol.upper()
        or not order_id.isdecimal()
        or int(order_id) <= 0
    ):
        raise ValueError("exact symbol/order identity required")
    if (
        not 0 < start_ms <= end_ms
        or end_ms - start_ms > 86400000
        or not 1 <= limit <= 100
    ):
        raise ValueError("bounded amendment window/limit required")
    raw = await asyncio.wait_for(
        exchange.fapiPrivateGetOrderAmendment(
            {
                "symbol": symbol,
                "orderId": int(order_id),
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": limit,
            }
        ),
        timeout=10,
    )
    if not isinstance(raw, list) or len(raw) > limit:
        raise ValueError("invalid amendment page")
    rows = []
    seen = set()
    for value in raw:
        r = _mapping(value)
        a = _mapping(r["amendment"])
        price = _mapping(a["price"])
        qty = _mapping(a["origQty"])
        item = OrderAmendment(
            amendment_id=_string(r, "amendmentId"),
            order_id=_string(r, "orderId"),
            symbol=_string(r, "symbol"),
            at_ms=_integer(r, "time"),
            before_price=Decimal(_string(price, "before")),
            after_price=Decimal(_string(price, "after")),
            before_quantity=Decimal(_string(qty, "before")),
            after_quantity=Decimal(_string(qty, "after")),
            modification_count=_integer(a, "count"),
        )
        if (
            item.order_id != order_id
            or item.symbol != symbol
            or not start_ms <= item.at_ms <= end_ms
        ):
            raise ValueError("amendment identity/window mismatch")
        if item.amendment_id in seen:
            raise ValueError("duplicate amendment in page")
        seen.add(item.amendment_id)
        rows.append(item)
    return AmendmentPage(rows=tuple(rows), possibly_truncated=len(rows) == limit)


def parse_rest_order(row: Mapping[str,object],*,account_id: str,conditional: bool,received_at_ms: int,
                     coverage_complete: bool) -> OrderEvidence:
    """Normalize current/history REST rows without guessing absent trade facts."""
    state=_string(row,'algoStatus' if conditional else 'status')
    created=_integer(row,'createTime' if conditional else 'time');updated=_integer(row,'updateTime')
    q=_string(row,'quantity' if conditional else 'origQty')
    body={'s':row['symbol'],'S':row['side'],'ps':row['positionSide'],
          'o':row['orderType'] if conditional else row['type'],'f':row['timeInForce'],
          'q':q,'p':row['price'],'R':row['reduceOnly'],'cp':row['closePosition'],
          'wt':row['workingType'],'pP':row['priceProtect'],'pm':row['priceMatch'],
          'V':row['selfTradePreventionMode'],'gtd':row['goodTillDate'],'O':created,'X':state}
    if conditional:
        body.update({'aid':row['algoId'],'caid':row['clientAlgoId'],'tp':row['triggerPrice'],'ia':row.get('isActivated',False)})
        if row.get('actualQty') is not None:body['aq']=row['actualQty']
    else:
        body.update({'i':row['orderId'],'c':row['clientOrderId'],'sp':row['stopPrice'],
                     'x':'TRADE' if state in ('FILLED','PARTIALLY_FILLED') else 'EXPIRED' if state=='EXPIRED_IN_MATCH' else state,'z':row['executedQty']})
    for raw,key in [('activatePrice','AP'),('callbackRate','cr')]:
        if raw in row:body[key]=row[raw]
    e=parse_order_update({'e':'ALGO_UPDATE' if conditional else 'ORDER_TRADE_UPDATE','E':updated,'T':updated,'o':body},
        account_id=account_id,received_at_ms=received_at_ms,coverage_complete=coverage_complete)
    # A REST NEW row is creation only when its update time equals creation.
    # Same-ID changes are compared to stored terms and ordinary amend history.
    if state=='NEW':e=e.model_copy(update={'action':OrderAction.NEW})
    return e
