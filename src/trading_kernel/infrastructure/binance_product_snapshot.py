"""Parse bounded Binance public product facts into exact current snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Literal

from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.product import ProductSessionSnapshot, SessionState

_VALID_FOR_MS = 900_000
_SESSION_STATES: Mapping[str, SessionState] = {
    "PRE_MARKET": "pre_market",
    "REGULAR": "regular",
    "AFTER_MARKET": "after_market",
    "OVERNIGHT": "overnight",
    "NO_TRADING": "no_trading",
}


def parse_binance_product_snapshots(
    *,
    exchange_instrument_ids: tuple[str, ...],
    exchange_info: object,
    trading_schedule: object,
    premium_index: object,
    depth_by_symbol: Mapping[str, object],
    observed_at_ms: int,
) -> tuple[ProductSessionSnapshot, ...]:
    """Fail closed per instrument while preserving one successful shared batch."""

    exchange_by_symbol = _by_symbol(_rows(exchange_info, keys=("symbols", "data")))
    schedule_by_symbol = _schedule_by_symbol(trading_schedule)
    premium_by_symbol = _by_symbol(_rows(premium_index, keys=("data", "symbols")))
    snapshots: list[ProductSessionSnapshot] = []
    for exchange_instrument_id in exchange_instrument_ids:
        identity = parse_binance_usdm_instrument_id(exchange_instrument_id)
        product = exchange_by_symbol.get(identity.symbol)
        sessions = schedule_by_symbol.get(identity.symbol, ())
        current_session = _current_session(sessions, observed_at_ms=observed_at_ms)
        regular_session = _nearest_regular_session(
            sessions,
            observed_at_ms=observed_at_ms,
        )
        premium = premium_by_symbol.get(identity.symbol)
        best_bid, best_ask, best_bid_quantity, best_ask_quantity = _best_bid_ask(
            depth_by_symbol.get(identity.symbol)
        )
        snapshots.append(
            ProductSessionSnapshot(
                exchange_instrument_id=exchange_instrument_id,
                product_family="tradfi_equity_perpetual",
                product_status=_product_status(product),
                session_state=(
                    "unavailable" if current_session is None else current_session[0]
                ),
                regular_session_open_ms=(
                    None if regular_session is None else regular_session[1]
                ),
                regular_session_close_ms=(
                    None if regular_session is None else regular_session[2]
                ),
                mark_price=_decimal_field(premium, "markPrice"),
                index_price=_decimal_field(premium, "indexPrice"),
                funding_rate=_decimal_field(premium, "lastFundingRate"),
                best_bid=best_bid,
                best_ask=best_ask,
                best_bid_quantity=best_bid_quantity,
                best_ask_quantity=best_ask_quantity,
                corporate_event_status="unavailable",
                observed_at_ms=observed_at_ms,
                valid_until_ms=observed_at_ms + _VALID_FOR_MS,
                source_ref=(
                    "binance:fapi:exchangeInfo+tradingSchedule+premiumIndex+depth"
                ),
            )
        )
    return tuple(snapshots)


def _rows(payload: object, *, keys: tuple[str, ...]) -> tuple[Mapping[str, object], ...]:
    if isinstance(payload, Mapping):
        for key in keys:
            nested = payload.get(key)
            if isinstance(nested, Sequence) and not isinstance(
                nested,
                (str, bytes),
            ):
                return tuple(item for item in nested if isinstance(item, Mapping))
        return (payload,)
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        return tuple(item for item in payload if isinstance(item, Mapping))
    return ()


def _by_symbol(
    rows: tuple[Mapping[str, object], ...],
) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for row in rows:
        symbol = row.get("symbol")
        if isinstance(symbol, str) and symbol:
            result[symbol] = row
    return result


def _schedule_by_symbol(
    payload: object,
) -> dict[str, tuple[tuple[SessionState, int, int], ...]]:
    grouped: dict[str, list[tuple[SessionState, int, int]]] = {}
    for row in _rows(payload, keys=("data", "symbols")):
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            continue
        nested: object = None
        for key in (
            "tradingSessions",
            "tradingSchedule",
            "schedule",
            "sessions",
        ):
            if key in row:
                nested = row[key]
                break
        session_rows = (
            _rows(nested, keys=("data",))
            if nested is not None
            else (row,)
        )
        for session_row in session_rows:
            parsed = _session_interval(session_row)
            if parsed is not None:
                grouped.setdefault(symbol, []).append(parsed)
    return {
        symbol: tuple(sorted(intervals, key=lambda item: (item[1], item[2])))
        for symbol, intervals in grouped.items()
    }


def _session_interval(
    row: Mapping[str, object],
) -> tuple[SessionState, int, int] | None:
    raw_state = row.get("session") or row.get("sessionType") or row.get("type")
    state = _SESSION_STATES.get(str(raw_state or "").upper())
    if state is None:
        return None
    start = _integer_field(row, ("startTime", "startTimeMs", "start"))
    end = _integer_field(row, ("endTime", "endTimeMs", "end"))
    if start is None or end is None or end <= start:
        return None
    return state, start, end


def _integer_field(
    row: Mapping[str, object],
    keys: tuple[str, ...],
) -> int | None:
    for key in keys:
        value = row.get(key)
        if value is None or isinstance(value, bool):
            continue
        if not isinstance(value, (int, float, str)):
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if parsed > 0:
            return parsed
    return None


def _current_session(
    sessions: tuple[tuple[SessionState, int, int], ...],
    *,
    observed_at_ms: int,
) -> tuple[SessionState, int, int] | None:
    matches = tuple(
        item for item in sessions if item[1] <= observed_at_ms < item[2]
    )
    return None if not matches else max(matches, key=lambda item: item[1])


def _nearest_regular_session(
    sessions: tuple[tuple[SessionState, int, int], ...],
    *,
    observed_at_ms: int,
) -> tuple[SessionState, int, int] | None:
    regular = tuple(item for item in sessions if item[0] == "regular")
    return (
        None
        if not regular
        else min(regular, key=lambda item: abs(item[1] - observed_at_ms))
    )


def _product_status(
    product: Mapping[str, object] | None,
) -> Literal["active", "inactive", "temporarily_unavailable"]:
    if product is None:
        return "temporarily_unavailable"
    compatible = (
        product.get("contractType") == "TRADIFI_PERPETUAL"
        and product.get("underlyingType") == "EQUITY"
        and product.get("marginAsset") == "USDT"
    )
    if not compatible:
        return "temporarily_unavailable"
    status = str(product.get("status") or "").upper()
    if status == "TRADING":
        return "active"
    if status in {"SETTLING", "CLOSE", "CLOSED", "DELIVERING"}:
        return "inactive"
    return "temporarily_unavailable"


def _decimal_field(
    row: Mapping[str, object] | None,
    key: str,
) -> Decimal | None:
    if row is None or row.get(key) is None:
        return None
    try:
        value = Decimal(str(row[key]))
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def _best_bid_ask(
    payload: object,
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    if not isinstance(payload, Mapping):
        return None, None, None, None
    best_bid, best_bid_quantity = _book_level(payload.get("bids"))
    best_ask, best_ask_quantity = _book_level(payload.get("asks"))
    return best_bid, best_ask, best_bid_quantity, best_ask_quantity


def _book_level(rows: object) -> tuple[Decimal | None, Decimal | None]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or not rows:
        return None, None
    first = rows[0]
    if not isinstance(first, Sequence) or isinstance(first, (str, bytes)) or not first:
        return None, None
    try:
        price = Decimal(str(first[0]))
        quantity = Decimal(str(first[1])) if len(first) > 1 else None
    except (InvalidOperation, ValueError):
        return None, None
    valid_price = price if price.is_finite() and price > 0 else None
    valid_quantity = (
        quantity
        if quantity is not None and quantity.is_finite() and quantity >= 0
        else None
    )
    return valid_price, valid_quantity
