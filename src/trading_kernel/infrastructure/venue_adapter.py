"""Typed CCXT translation at the sole trading-kernel venue boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from decimal import Decimal
import inspect
from typing import Literal, Protocol

from pydantic import JsonValue

from src.trading_kernel.application.ports import VenueCommandRequest, VenueTruthRequest
from src.trading_kernel.application.runtime_facts import (
    ActionTimeFactsRequest,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
    LifecycleFactsRequest,
    PositionSnapshotRequest,
    ReviewEconomicsRequest,
)
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.domain.capacity import ActionTimeFacts
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.venue_truth import (
    VenueLookupStatus,
    VenueOrderTruth,
    VenueTruthSnapshot,
)
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.review import ReviewEconomicsFacts, ReviewFill
from src.trading_kernel.domain.exit_policy import LifecycleMarketFacts


class _CcxtExchange(Protocol):
    def load_markets(self, reload: bool = False) -> object: ...

    def market(self, symbol: str) -> Mapping[str, object]: ...

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: object,
        price: object,
        params: Mapping[str, object],
    ) -> object: ...

    def cancel_order(
        self,
        order_id: str,
        symbol: str,
        params: Mapping[str, object],
    ) -> object: ...

    def fetch_order(
        self,
        order_id: object,
        symbol: str,
        params: Mapping[str, object],
    ) -> object: ...

    def fetch_positions(
        self,
        symbols: list[str],
        params: Mapping[str, object],
    ) -> object: ...

    def fetch_my_trades(
        self,
        symbol: str,
        since: object,
        limit: int,
        params: Mapping[str, object],
    ) -> object: ...

    def fetch_open_orders(
        self,
        symbol: str,
        since: object,
        limit: int,
        params: Mapping[str, object],
    ) -> object: ...

    def fetch_ticker(self, symbol: str) -> object: ...

    def fetch_balance(self, params: Mapping[str, object]) -> object: ...

    def fetch_position_mode(
        self,
        symbol: str,
        params: Mapping[str, object],
    ) -> object: ...

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: object,
        limit: int,
    ) -> object: ...

    def close(self) -> object: ...


_AUTHORITATIVE_REJECTION_TYPES = {
    "BadRequest",
    "InsufficientFunds",
    "InvalidOrder",
    "OperationRejected",
}
_ORDER_NOT_FOUND_TYPES = {"OrderNotFound"}


class CcxtVenueAdapter:
    def __init__(
        self,
        *,
        exchanges: Mapping[tuple[str, str], _CcxtExchange],
        venue_symbols: Mapping[tuple[str, str], str],
        settlement_assets: Mapping[tuple[str, str], str] | None = None,
        taker_fee_rates: Mapping[tuple[str, str], Decimal] | None = None,
        clock_ms: Callable[[], int],
    ) -> None:
        self._exchanges = dict(exchanges)
        self._venue_symbols = dict(venue_symbols)
        self._settlement_assets = dict(settlement_assets or {})
        self._taker_fee_rates = dict(taker_fee_rates or {})
        self._clock_ms = clock_ms

    async def close(self) -> None:
        closed_exchange_ids: set[int] = set()
        for exchange in self._exchanges.values():
            exchange_identity = id(exchange)
            if exchange_identity in closed_exchange_ids:
                continue
            closed_exchange_ids.add(exchange_identity)
            close = getattr(exchange, "close", None)
            if callable(close):
                await _call_raw_exchange(close)

    async def read_action_time_facts(
        self,
        request: ActionTimeFactsRequest,
    ) -> ActionTimeFacts:
        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
        )
        settlement_asset = self._settlement_assets.get(
            (request.venue_id, request.exchange_instrument_id)
        )
        if not settlement_asset:
            raise RuntimeError("canonical instrument has no settlement asset mapping")

        ticker, balance, mode, positions, regular_orders, conditional_orders = (
            await asyncio.gather(
                _call_raw_exchange(exchange.fetch_ticker, symbol),
                _call_raw_exchange(exchange.fetch_balance, {"type": "future"}),
                _call_raw_exchange(exchange.fetch_position_mode, symbol, {}),
                _call_raw_exchange(
                    exchange.fetch_positions,
                    [symbol],
                    {"positionSide": request.position_side.upper()},
                ),
                _call_raw_exchange(
                    exchange.fetch_open_orders,
                    symbol,
                    None,
                    100,
                    {"conditional": False},
                ),
                _call_raw_exchange(
                    exchange.fetch_open_orders,
                    symbol,
                    None,
                    100,
                    {"conditional": True},
                ),
            )
        )
        ticker_mapping = _require_mapping(ticker, name="ticker")
        balance_mapping = _require_mapping(balance, name="balance")
        mode_mapping = _require_mapping(mode, name="position mode")
        position_rows = _require_list(positions, name="positions")
        regular_rows = _require_list(regular_orders, name="regular open orders")
        conditional_rows = _require_list(
            conditional_orders,
            name="conditional open orders",
        )
        return ActionTimeFacts(
            signal_event_id=request.signal_event_id,
            runtime_scope_id=request.runtime_scope_id,
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
            position_side=request.position_side,
            account_position_mode=_account_position_mode(mode_mapping),
            best_bid_price=_positive_decimal_field(
                ticker_mapping,
                "bid",
                fallback_info_key="bidPrice",
            ),
            best_ask_price=_positive_decimal_field(
                ticker_mapping,
                "ask",
                fallback_info_key="askPrice",
            ),
            account_equity=_balance_decimal(
                balance_mapping,
                bucket="total",
                asset=settlement_asset,
                fallback_info_key="totalWalletBalance",
            ),
            available_margin=_balance_decimal(
                balance_mapping,
                bucket="free",
                asset=settlement_asset,
                fallback_info_key="availableBalance",
            ),
            netting_domain_position_qty=_position_quantity(
                position_rows,
                expected_symbol=symbol,
                position_side=request.position_side,
            ),
            netting_domain_open_order_count=_open_order_count(
                (*regular_rows, *conditional_rows),
                expected_symbol=symbol,
                position_side=request.position_side,
            ),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts:
        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
        )
        await _call_raw_exchange(exchange.load_markets, False)
        market = exchange.market(symbol)
        quantity_step, price_tick, min_quantity, min_notional = (
            _instrument_rules(market)
        )
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=quantity_step,
            price_tick=price_tick,
            min_quantity=min_quantity,
            min_notional=min_notional,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_position_snapshot(
        self,
        request: PositionSnapshotRequest,
    ) -> PositionSnapshot:
        domain = request.netting_domain
        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=domain.venue_id,
            account_id=domain.account_id,
            exchange_instrument_id=domain.exchange_instrument_id,
        )
        positions, regular_orders, conditional_orders = await asyncio.gather(
            _call_raw_exchange(
                exchange.fetch_positions,
                [symbol],
                {"positionSide": domain.position_side.upper()},
            ),
            _call_raw_exchange(
                exchange.fetch_open_orders,
                symbol,
                None,
                100,
                {"conditional": False},
            ),
            _call_raw_exchange(
                exchange.fetch_open_orders,
                symbol,
                None,
                100,
                {"conditional": True},
            ),
        )
        position_rows = _require_list(positions, name="positions")
        quantity, average_entry_price = _position_details(
            position_rows,
            expected_symbol=symbol,
            position_side=domain.position_side,
        )
        open_orders = _position_open_orders(
            (
                *_require_list(regular_orders, name="regular open orders"),
                *_require_list(
                    conditional_orders,
                    name="conditional open orders",
                ),
            ),
            expected_symbol=symbol,
            position_side=domain.position_side,
        )
        return PositionSnapshot(
            netting_domain=domain,
            quantity=quantity,
            average_entry_price=average_entry_price,
            open_orders=open_orders,
            observed_at_ms=request.observed_at_ms,
        )

    async def read_lifecycle_facts(
        self,
        request: LifecycleFactsRequest,
    ) -> TicketLifecycleFacts:
        domain = request.netting_domain
        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=domain.venue_id,
            account_id=domain.account_id,
            exchange_instrument_id=domain.exchange_instrument_id,
        )
        key = (domain.venue_id, domain.exchange_instrument_id)
        settlement_asset = self._settlement_assets.get(key)
        taker_fee_rate = self._taker_fee_rates.get(key)
        if not settlement_asset:
            raise RuntimeError("canonical instrument has no settlement asset mapping")
        if taker_fee_rate is None:
            raise RuntimeError("canonical instrument has no taker fee rate")

        tp1_client_id = request.tp1_venue_client_order_id
        candle_limit = max(request.atr_period + 1, request.structure_window_bars)
        positions_call = _call_raw_exchange(
            exchange.fetch_positions,
            [symbol],
            {"positionSide": domain.position_side.upper()},
        )
        entry_fills_call = _call_raw_exchange(
            exchange.fetch_my_trades,
            symbol,
            None,
            100,
            {"clientOrderId": request.entry_venue_client_order_id},
        )
        tp1_fills_call = (
            _call_raw_exchange(
                exchange.fetch_my_trades,
                symbol,
                None,
                100,
                {"clientOrderId": tp1_client_id},
            )
            if tp1_client_id is not None
            else _empty_rows()
        )
        candles_call = (
            _call_raw_exchange(
                exchange.fetch_ohlcv,
                symbol,
                request.timeframe,
                None,
                candle_limit,
            )
            if request.runner_market_required
            else _empty_rows()
        )
        positions, entry_fills, tp1_fills, candle_rows = await asyncio.gather(
            positions_call,
            entry_fills_call,
            tp1_fills_call,
            candles_call,
        )
        position_quantity, _ = _position_details(
            _require_list(positions, name="positions"),
            expected_symbol=symbol,
            position_side=domain.position_side,
        )
        _, _, entry_fee_quote = _fill_metrics(
            _require_list(entry_fills, name="entry fills"),
            venue_client_order_id=request.entry_venue_client_order_id,
            settlement_asset=settlement_asset,
        )
        tp1_quantity, tp1_average_price, _ = _fill_metrics(
            _require_list(tp1_fills, name="TP1 fills"),
            venue_client_order_id=tp1_client_id,
            settlement_asset=settlement_asset,
        )
        allocated_entry_fee = (
            entry_fee_quote * position_quantity / request.entry_quantity
        )
        market_facts = (
            _lifecycle_market_facts(
                _require_list(candle_rows, name="lifecycle candles"),
                timeframe=request.timeframe,
                observed_at_ms=request.observed_at_ms,
                entered_at_ms=request.entered_at_ms,
                position_side=domain.position_side,
                structure_window_bars=request.structure_window_bars,
                atr_period=request.atr_period,
            )
            if request.runner_market_required
            else None
        )
        return TicketLifecycleFacts(
            position_quantity=position_quantity,
            tp1_filled_quantity=tp1_quantity,
            tp1_average_fill_price=tp1_average_price,
            allocated_entry_fee_quote=allocated_entry_fee,
            exit_taker_fee_rate=taker_fee_rate,
            price_tick=request.price_tick,
            market_facts=market_facts,
            observed_at_ms=request.observed_at_ms,
        )

    async def read_review_economics(
        self,
        request: ReviewEconomicsRequest,
    ) -> ReviewEconomicsFacts:
        domain = request.netting_domain
        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=domain.venue_id,
            account_id=domain.account_id,
            exchange_instrument_id=domain.exchange_instrument_id,
        )
        settlement_asset = self._settlement_assets.get(
            (domain.venue_id, domain.exchange_instrument_id)
        )
        if not settlement_asset:
            raise RuntimeError("canonical instrument has no settlement asset mapping")

        client_ids = (
            request.entry_venue_client_order_id,
            *request.exit_venue_client_order_ids,
        )
        rows: list[object] = []
        for client_id in client_ids:
            rows.extend(
                _require_list(
                    await _call_raw_exchange(
                        exchange.fetch_my_trades,
                        symbol,
                        request.entry_time_ms,
                        100,
                        {"clientOrderId": client_id},
                    ),
                    name="review fills",
                )
            )
        fills_by_trade_id: dict[str, ReviewFill] = {}
        known_client_ids = set(client_ids)
        for row in rows:
            fill = _review_fill(
                row,
                known_client_ids=known_client_ids,
                settlement_asset=settlement_asset,
                position_side=domain.position_side,
                entry_time_ms=request.entry_time_ms,
                exit_time_ms=request.exit_time_ms,
            )
            if fill is None:
                continue
            existing = fills_by_trade_id.get(fill.exchange_trade_id)
            if existing is not None and existing != fill:
                raise RuntimeError("venue returned contradictory duplicate review fill")
            fills_by_trade_id[fill.exchange_trade_id] = fill

        ordered_fills = tuple(
            sorted(
                fills_by_trade_id.values(),
                key=lambda item: (item.occurred_at_ms, item.exchange_trade_id),
            )
        )
        entry_fills = tuple(
            fill
            for fill in ordered_fills
            if fill.venue_client_order_id == request.entry_venue_client_order_id
        )
        exit_client_ids = set(request.exit_venue_client_order_ids)
        exit_fills = tuple(
            fill
            for fill in ordered_fills
            if fill.venue_client_order_id in exit_client_ids
        )

        if request.funding_attribution_exact:
            funding_quote, funding_unavailable_reason = await _funding_quote(
                exchange,
                venue_id=domain.venue_id,
                symbol=symbol,
                settlement_asset=settlement_asset,
                entry_time_ms=request.entry_time_ms,
                exit_time_ms=request.exit_time_ms,
            )
        else:
            funding_quote = None
            funding_unavailable_reason = "overlapping_instrument_exposure"

        return ReviewEconomicsFacts(
            ticket_id=request.ticket_id,
            entry_fills=entry_fills,
            exit_fills=exit_fills,
            funding_quote=funding_quote,
            funding_unavailable_reason=funding_unavailable_reason,
            observed_at_ms=request.observed_at_ms,
        )

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        exchange_key = (request.venue_id, request.account_id)
        exchange = self._exchanges.get(exchange_key)
        if exchange is None:
            raise RuntimeError("venue/account adapter is not configured")
        symbol_key = (request.venue_id, request.exchange_instrument_id)
        symbol = self._venue_symbols.get(symbol_key)
        if not symbol:
            raise RuntimeError("canonical instrument has no venue symbol mapping")

        params: dict[str, object] = {"positionSide": request.position_side.upper()}

        if isinstance(request.payload, CancelCommandPayload):
            response = await _call_exchange(
                exchange.cancel_order,
                request.payload.exchange_order_id,
                symbol,
                params,
                clock_ms=self._clock_ms,
            )
            if isinstance(response, ExchangeCommandResult):
                return response
            if not isinstance(response, Mapping):
                raise RuntimeError("venue cancel response is not a mapping")
            return ExchangeCommandResult(
                status=ExchangeCommandStatus.ACCEPTED,
                observed_at_ms=self._clock_ms(),
                exchange_order_id=request.payload.exchange_order_id,
                venue_payload=_safe_response_payload(response),
            )

        if not isinstance(request.payload, OrderCommandPayload):
            raise RuntimeError("unsupported venue command payload")

        params["newClientOrderId"] = request.venue_client_order_id
        if request.payload.reduce_only and request.venue_id != "binance-usdm":
            params["reduceOnly"] = True
        if request.payload.stop_price is not None:
            params["stopPrice"] = request.payload.stop_price

        response = await _call_exchange(
            exchange.create_order,
            symbol,
            request.payload.order_type,
            request.payload.side,
            request.payload.quantity,
            request.payload.limit_price,
            params,
            clock_ms=self._clock_ms,
        )
        if isinstance(response, ExchangeCommandResult):
            return response

        if not isinstance(response, Mapping):
            raise RuntimeError("venue response is not a mapping")
        exchange_order_id = str(response.get("id") or "").strip()
        if not exchange_order_id:
            raise RuntimeError("venue acceptance lacks exchange order identity")

        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=self._clock_ms(),
            exchange_order_id=exchange_order_id,
            venue_payload=_safe_response_payload(response),
        )

    async def lookup_command_truth(
        self,
        request: VenueTruthRequest,
    ) -> VenueTruthSnapshot:
        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
        )
        order_response: object | None
        if isinstance(request.payload, CancelCommandPayload):
            lookup_order_id: object = request.payload.exchange_order_id
            lookup_params: Mapping[str, object] = {
                "positionSide": request.position_side.upper()
            }
        else:
            lookup_order_id = None
            lookup_params = {"origClientOrderId": request.venue_client_order_id}
        try:
            order_response = await _call_raw_exchange(
                exchange.fetch_order,
                lookup_order_id,
                symbol,
                lookup_params,
            )
        except Exception as exc:
            if type(exc).__name__ not in _ORDER_NOT_FOUND_TYPES:
                raise
            order_response = None

        positions = _require_list(
            await _call_raw_exchange(
                exchange.fetch_positions,
                [symbol],
                {"positionSide": request.position_side.upper()},
            ),
            name="positions",
        )
        fills = _require_list(
            await _call_raw_exchange(
                exchange.fetch_my_trades,
                symbol,
                None,
                100,
                {"clientOrderId": request.venue_client_order_id},
            ),
            name="fills",
        )
        regular_orders = _require_list(
            await _call_raw_exchange(
                exchange.fetch_open_orders,
                symbol,
                None,
                100,
                {"conditional": False},
            ),
            name="regular open orders",
        )
        conditional_orders = _require_list(
            await _call_raw_exchange(
                exchange.fetch_open_orders,
                symbol,
                None,
                100,
                {"conditional": True},
            ),
            name="conditional open orders",
        )
        if order_response is None and isinstance(
            request.payload,
            CancelCommandPayload,
        ):
            order_response = _find_order_by_exchange_id(
                (*regular_orders, *conditional_orders),
                exchange_order_id=request.payload.exchange_order_id,
            )
        order = (
            None
            if order_response is None
            else _parse_order_truth(
                order_response,
                request=request,
                expected_symbol=symbol,
            )
        )
        return VenueTruthSnapshot(
            lookup_status=(
                VenueLookupStatus.ABSENT
                if order is None
                else VenueLookupStatus.VISIBLE
            ),
            order=order,
            position_quantity=_position_quantity(
                positions,
                expected_symbol=symbol,
                position_side=request.position_side,
            ),
            matching_fill_quantity=_matching_fill_quantity(
                fills,
                venue_client_order_id=request.venue_client_order_id,
            ),
            regular_open_client_order_ids=_open_client_order_ids(regular_orders),
            conditional_open_client_order_ids=_open_client_order_ids(
                conditional_orders
            ),
            observed_at_ms=self._clock_ms(),
        )

    def _resolve_exchange_and_symbol(
        self,
        *,
        venue_id: str,
        account_id: str,
        exchange_instrument_id: str,
    ) -> tuple[_CcxtExchange, str]:
        exchange = self._exchanges.get((venue_id, account_id))
        if exchange is None:
            raise RuntimeError("venue/account adapter is not configured")
        symbol = self._venue_symbols.get((venue_id, exchange_instrument_id))
        if not symbol:
            raise RuntimeError("canonical instrument has no venue symbol mapping")
        return exchange, symbol


async def _call_exchange(
    operation: Callable[..., object],
    *args: object,
    clock_ms: Callable[[], int],
) -> object | ExchangeCommandResult:
    try:
        if inspect.iscoroutinefunction(operation):
            response = await operation(*args)
        else:
            response = await asyncio.to_thread(operation, *args)
        if inspect.isawaitable(response):
            response = await response
        return response
    except Exception as exc:
        error_type = type(exc).__name__
        if error_type in _AUTHORITATIVE_REJECTION_TYPES:
            return ExchangeCommandResult(
                status=ExchangeCommandStatus.REJECTED,
                observed_at_ms=clock_ms(),
                reason=f"venue_rejected:{error_type}",
            )
        raise


async def _call_raw_exchange(
    operation: Callable[..., object],
    *args: object,
) -> object:
    if inspect.iscoroutinefunction(operation):
        return await operation(*args)
    response = await asyncio.to_thread(operation, *args)
    if inspect.isawaitable(response):
        return await response
    return response


def _require_list(value: object, *, name: str) -> list[object]:
    if not isinstance(value, list):
        raise RuntimeError(f"venue {name} response is not a list")
    return value


def _require_mapping(value: object, *, name: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"venue {name} response is not a mapping")
    return value


def _parse_order_truth(
    value: object,
    *,
    request: VenueTruthRequest,
    expected_symbol: str,
) -> VenueOrderTruth:
    if not isinstance(value, Mapping):
        raise RuntimeError("venue order truth response is not a mapping")
    info = value.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    raw_symbol = str(value.get("symbol") or "").strip()
    position_side = _position_side_literal(
        str(raw_info.get("positionSide") or "").strip().lower()
    )
    order_side = _order_side_literal(
        str(value.get("side") or "").strip().lower()
    )
    return VenueOrderTruth(
        exchange_order_id=str(value.get("id") or ""),
        venue_client_order_id=str(value.get("clientOrderId") or ""),
        exchange_instrument_id=(
            request.exchange_instrument_id
            if raw_symbol == expected_symbol
            else f"unmapped:{raw_symbol}"
        ),
        position_side=position_side,
        order_side=order_side,
        quantity=Decimal(str(value.get("amount") or "0")),
        reduce_only=bool(value.get("reduceOnly", False)),
    )


def _position_quantity(
    rows: list[object],
    *,
    expected_symbol: str,
    position_side: Literal["long", "short"],
) -> Decimal:
    total = Decimal("0")
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue position row is not a mapping")
        if str(value.get("symbol") or "") != expected_symbol:
            continue
        if _row_position_side(value) != position_side:
            continue
        total += abs(Decimal(str(value.get("contracts") or "0")))
    return total


def _position_details(
    rows: list[object],
    *,
    expected_symbol: str,
    position_side: Literal["long", "short"],
) -> tuple[Decimal, Decimal | None]:
    total_quantity = Decimal("0")
    weighted_entry = Decimal("0")
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue position row is not a mapping")
        if str(value.get("symbol") or "") != expected_symbol:
            continue
        if _row_position_side(value) != position_side:
            continue
        quantity = abs(Decimal(str(value.get("contracts") or "0")))
        if quantity == 0:
            continue
        price = Decimal(
            str(
                value.get("entryPrice")
                or _mapping_value(value.get("info"), "entryPrice")
                or "0"
            )
        )
        if price <= 0:
            raise RuntimeError("open venue position lacks entry price")
        total_quantity += quantity
        weighted_entry += quantity * price
    if total_quantity == 0:
        return Decimal("0"), None
    return total_quantity, weighted_entry / total_quantity


def _position_open_orders(
    rows: tuple[object, ...],
    *,
    expected_symbol: str,
    position_side: Literal["long", "short"],
) -> tuple[VenueOrderSnapshot, ...]:
    orders: list[VenueOrderSnapshot] = []
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue open-order row is not a mapping")
        if str(value.get("symbol") or "") != expected_symbol:
            continue
        if _row_position_side(value) != position_side:
            continue
        orders.append(
            VenueOrderSnapshot(
                exchange_order_id=str(value.get("id") or ""),
                venue_client_order_id=(
                    str(value.get("clientOrderId"))
                    if value.get("clientOrderId") is not None
                    else None
                ),
                position_side=position_side,
                reduce_only=_boolean_field(value, "reduceOnly"),
            )
        )
    return tuple(sorted(orders, key=lambda item: item.exchange_order_id))


def _row_position_side(value: Mapping[object, object]) -> Literal["long", "short"]:
    info = value.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    raw = str(raw_info.get("positionSide") or value.get("side") or "").lower()
    return _position_side_literal(raw)


def _open_order_count(
    rows: tuple[object, ...],
    *,
    expected_symbol: str,
    position_side: Literal["long", "short"],
) -> int:
    count = 0
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue open-order row is not a mapping")
        if str(value.get("symbol") or "") != expected_symbol:
            continue
        if _row_position_side(value) == position_side:
            count += 1
    return count


def _positive_decimal_field(
    value: Mapping[object, object],
    key: str,
    *,
    fallback_info_key: str,
) -> Decimal:
    info = value.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    result = Decimal(str(value.get(key) or raw_info.get(fallback_info_key) or "0"))
    if result <= 0:
        raise RuntimeError(f"venue {key} is missing or non-positive")
    return result


def _balance_decimal(
    balance: Mapping[object, object],
    *,
    bucket: str,
    asset: str,
    fallback_info_key: str,
) -> Decimal:
    raw_bucket = balance.get(bucket)
    bucket_mapping = raw_bucket if isinstance(raw_bucket, Mapping) else {}
    info = balance.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    result = Decimal(
        str(bucket_mapping.get(asset) or raw_info.get(fallback_info_key) or "0")
    )
    if result < 0 or (bucket == "total" and result <= 0):
        raise RuntimeError(f"venue account {bucket} is invalid")
    return result


def _instrument_rules(
    market: Mapping[str, object],
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    info = market.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    filters = raw_info.get("filters")
    filter_rows = filters if isinstance(filters, list) else []
    by_type = {
        str(row.get("filterType") or ""): row
        for row in filter_rows
        if isinstance(row, Mapping)
    }
    lot = by_type.get("LOT_SIZE", {})
    price_filter = by_type.get("PRICE_FILTER", {})
    notional_filter = by_type.get("MIN_NOTIONAL") or by_type.get("NOTIONAL") or {}

    quantity_step = _positive_rule_value(
        lot.get("stepSize"),
        fallback=_nested_market_value(market, "precision", "amount"),
        name="quantity step",
    )
    price_tick = _positive_rule_value(
        price_filter.get("tickSize"),
        fallback=_nested_market_value(market, "precision", "price"),
        name="price tick",
    )
    min_quantity = _positive_rule_value(
        lot.get("minQty"),
        fallback=_nested_market_value(market, "limits", "amount", "min"),
        name="minimum quantity",
    )
    min_notional = _positive_rule_value(
        notional_filter.get("notional")
        or notional_filter.get("minNotional"),
        fallback=_nested_market_value(market, "limits", "cost", "min"),
        name="minimum notional",
    )
    return quantity_step, price_tick, min_quantity, min_notional


def _nested_market_value(
    value: Mapping[str, object],
    *keys: str,
) -> object | None:
    current: object = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _positive_rule_value(
    value: object,
    *,
    fallback: object,
    name: str,
) -> Decimal:
    parsed = Decimal(str(value or fallback or "0"))
    if parsed <= 0:
        raise RuntimeError(f"venue {name} is missing or non-positive")
    return parsed


async def _empty_rows() -> list[object]:
    return []


def _fill_metrics(
    rows: list[object],
    *,
    venue_client_order_id: str | None,
    settlement_asset: str,
) -> tuple[Decimal, Decimal | None, Decimal]:
    if venue_client_order_id is None:
        return Decimal("0"), None, Decimal("0")
    quantity = Decimal("0")
    weighted_price = Decimal("0")
    fee_quote = Decimal("0")
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue fill row is not a mapping")
        info = value.get("info")
        raw_info = info if isinstance(info, Mapping) else {}
        client_id = str(
            value.get("clientOrderId")
            or raw_info.get("clientOrderId")
            or ""
        )
        if client_id != venue_client_order_id:
            continue
        fill_quantity = abs(Decimal(str(value.get("amount") or "0")))
        fill_price = Decimal(str(value.get("price") or "0"))
        if fill_quantity <= 0 or fill_price <= 0:
            raise RuntimeError("venue fill quantity and price must be positive")
        quantity += fill_quantity
        weighted_price += fill_quantity * fill_price
        fee = value.get("fee")
        if isinstance(fee, Mapping) and fee.get("cost") is not None:
            currency = str(fee.get("currency") or "").upper()
            if currency != settlement_asset.upper():
                raise RuntimeError("venue fill fee is not in settlement asset")
            fee_quote += abs(Decimal(str(fee.get("cost"))))
    average_price = None if quantity == 0 else weighted_price / quantity
    return quantity, average_price, fee_quote


def _review_fill(
    value: object,
    *,
    known_client_ids: set[str],
    settlement_asset: str,
    position_side: Literal["long", "short"],
    entry_time_ms: int,
    exit_time_ms: int,
) -> ReviewFill | None:
    if not isinstance(value, Mapping):
        raise RuntimeError("venue review fill row is not a mapping")
    info = value.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    client_id = str(
        value.get("clientOrderId")
        or raw_info.get("clientOrderId")
        or ""
    ).strip()
    if client_id not in known_client_ids:
        return None
    raw_position_side = str(
        value.get("positionSide")
        or raw_info.get("positionSide")
        or ""
    ).strip().lower()
    if _position_side_literal(raw_position_side) != position_side:
        raise RuntimeError("review fill position side differs from Ticket")
    trade_id = str(
        value.get("id")
        or raw_info.get("tradeId")
        or raw_info.get("id")
        or ""
    ).strip()
    if not trade_id:
        raise RuntimeError("review fill lacks exchange trade identity")
    occurred_at_ms = int(
        value.get("timestamp")
        or raw_info.get("time")
        or raw_info.get("timestamp")
        or 0
    )
    if not entry_time_ms <= occurred_at_ms <= exit_time_ms:
        raise RuntimeError("review fill falls outside Ticket exposure window")
    quantity = abs(Decimal(str(value.get("amount") or raw_info.get("qty") or "0")))
    price = Decimal(str(value.get("price") or raw_info.get("price") or "0"))
    if quantity <= 0 or price <= 0:
        raise RuntimeError("review fill quantity and price must be positive")
    fee = value.get("fee")
    if not isinstance(fee, Mapping) or fee.get("cost") is None:
        raise RuntimeError("review fill fee is unavailable")
    fee_asset = str(fee.get("currency") or "").strip().upper()
    if fee_asset != settlement_asset.upper():
        raise RuntimeError("review fill fee is not in the settlement asset")
    fee_quote = abs(Decimal(str(fee.get("cost"))))
    return ReviewFill(
        exchange_trade_id=trade_id,
        venue_client_order_id=client_id,
        quantity=quantity,
        price=price,
        fee_quote=fee_quote,
        occurred_at_ms=occurred_at_ms,
    )


async def _funding_quote(
    exchange: _CcxtExchange,
    *,
    venue_id: str,
    symbol: str,
    settlement_asset: str,
    entry_time_ms: int,
    exit_time_ms: int,
) -> tuple[Decimal | None, str | None]:
    raw_fetch = getattr(exchange, "fapiPrivateGetIncome", None)
    if venue_id != "binance-usdm" or not callable(raw_fetch):
        return None, "funding_read_unsupported"
    market_id = symbol.split(":", 1)[0].replace("/", "")
    rows = _require_list(
        await _call_raw_exchange(
            raw_fetch,
            {
                "symbol": market_id,
                "incomeType": "FUNDING_FEE",
                "startTime": entry_time_ms,
                "endTime": exit_time_ms,
                "limit": 1000,
            },
        ),
        name="funding income",
    )
    funding_by_id: dict[str, tuple[Decimal, int]] = {}
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue funding income row is not a mapping")
        if str(value.get("incomeType") or "").upper() != "FUNDING_FEE":
            continue
        if str(value.get("symbol") or "") != market_id:
            continue
        occurred_at_ms = int(value.get("time") or value.get("timestamp") or 0)
        if not entry_time_ms <= occurred_at_ms <= exit_time_ms:
            continue
        funding_id = str(value.get("tranId") or value.get("id") or "").strip()
        if not funding_id:
            raise RuntimeError("funding income lacks exchange identity")
        asset = str(value.get("asset") or value.get("currency") or "").upper()
        if asset != settlement_asset.upper():
            raise RuntimeError("funding income is not in the settlement asset")
        amount = Decimal(str(value.get("income") or value.get("amount") or ""))
        normalized = (amount, occurred_at_ms)
        existing = funding_by_id.get(funding_id)
        if existing is not None and existing != normalized:
            raise RuntimeError("venue returned contradictory duplicate funding income")
        funding_by_id[funding_id] = normalized
    return (
        sum((amount for amount, _ in funding_by_id.values()), Decimal("0")),
        None,
    )


def _lifecycle_market_facts(
    rows: list[object],
    *,
    timeframe: str,
    observed_at_ms: int,
    entered_at_ms: int,
    position_side: Literal["long", "short"],
    structure_window_bars: int,
    atr_period: int,
) -> LifecycleMarketFacts:
    duration_ms = {"15m": 900_000, "1h": 3_600_000}[timeframe]
    candles: list[tuple[int, int, Decimal, Decimal, Decimal]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            raise RuntimeError("venue lifecycle candle row is malformed")
        open_time_ms = int(row[0])
        close_time_ms = open_time_ms + duration_ms - 1
        if close_time_ms > observed_at_ms:
            continue
        candles.append(
            (
                open_time_ms,
                close_time_ms,
                Decimal(str(row[2])),
                Decimal(str(row[3])),
                Decimal(str(row[4])),
            )
        )
    candles.sort(key=lambda item: item[0])
    if len(candles) < atr_period + 1 or len(candles) < structure_window_bars:
        raise RuntimeError("lifecycle candles are insufficient")
    true_ranges: list[Decimal] = []
    for index in range(len(candles) - atr_period, len(candles)):
        _, _, high, low, _ = candles[index]
        previous_close = candles[index - 1][4]
        true_ranges.append(
            max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        )
    atr = sum(true_ranges, Decimal("0")) / Decimal(atr_period)
    structure_rows = candles[-structure_window_bars:]
    structure_reference = (
        min(item[3] for item in structure_rows)
        if position_side == "long"
        else max(item[2] for item in structure_rows)
    )
    return LifecycleMarketFacts(
        watermark_ms=candles[-1][1],
        is_final_closed_candle=True,
        structure_reference=structure_reference,
        atr=atr,
        holding_bars=sum(1 for item in candles if item[1] >= entered_at_ms),
    )


def _account_position_mode(
    value: Mapping[object, object],
) -> str:
    hedged = value.get("hedged")
    if not isinstance(hedged, bool):
        raise RuntimeError("venue position mode response lacks hedged boolean")
    return "independent_sides" if hedged else "one_way"


def _mapping_value(value: object, key: str) -> object | None:
    return value.get(key) if isinstance(value, Mapping) else None


def _boolean_field(value: Mapping[object, object], key: str) -> bool:
    raw = value.get(key)
    if raw is None:
        raw = _mapping_value(value.get("info"), key)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0", ""}:
            return False
    if isinstance(raw, (int, float)):
        return bool(raw)
    raise RuntimeError(f"venue boolean field {key} is invalid")


def _position_side_literal(value: str) -> Literal["long", "short"]:
    if value == "long":
        return "long"
    if value == "short":
        return "short"
    raise RuntimeError("venue order truth has invalid position side")


def _order_side_literal(value: str) -> Literal["buy", "sell"]:
    if value == "buy":
        return "buy"
    if value == "sell":
        return "sell"
    raise RuntimeError("venue order truth has invalid order side")


def _matching_fill_quantity(
    rows: list[object],
    *,
    venue_client_order_id: str,
) -> Decimal:
    total = Decimal("0")
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue fill row is not a mapping")
        info = value.get("info")
        raw_info = info if isinstance(info, Mapping) else {}
        client_id = str(
            value.get("clientOrderId")
            or raw_info.get("clientOrderId")
            or ""
        )
        if client_id == venue_client_order_id:
            total += abs(Decimal(str(value.get("amount") or "0")))
    return total


def _open_client_order_ids(rows: list[object]) -> tuple[str, ...]:
    identities: set[str] = set()
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue open-order row is not a mapping")
        identity = str(value.get("clientOrderId") or "").strip()
        if identity:
            identities.add(identity)
    return tuple(sorted(identities))


def _find_order_by_exchange_id(
    rows: tuple[object, ...],
    *,
    exchange_order_id: str,
) -> object | None:
    for value in rows:
        if not isinstance(value, Mapping):
            raise RuntimeError("venue open-order row is not a mapping")
        if str(value.get("id") or "").strip() == exchange_order_id:
            return value
    return None


def _safe_response_payload(response: Mapping[object, object]) -> dict[str, JsonValue]:
    return {
        key: value
        for key in ("status", "clientOrderId")
        if isinstance((value := response.get(key)), (str, int, float, bool))
    }
