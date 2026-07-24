"""Typed CCXT translation at the sole trading-kernel venue boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from decimal import Decimal
import inspect
from typing import Literal, Protocol

from pydantic import JsonValue

from src.trading_kernel.application.ports import (
    LeverageTruthRequest,
    LeverageTruthSnapshot,
    VenueCommandRequest,
    VenueMutationRejected,
    VenueSetLeverageRequest,
    VenueTruthRequest,
)
from src.trading_kernel.application.runtime_facts import (
    EntryAdmissionSnapshotRequest,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
    LifecycleFactsRequest,
    PositionSnapshotRequest,
    ReviewEconomicsRequest,
)
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.domain.capacity_sizing import MaintenanceMarginBracket
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionInstrumentFacts,
    AdmissionOrder,
    AdmissionPosition,
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
    SetLeverageCommandResult,
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

    def set_leverage(
        self,
        leverage: int,
        symbol: str,
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

    def fapiPrivateV2GetPositionRisk(self, params: Mapping[str, object]) -> object: ...

    def fetch_my_trades(
        self,
        symbol: str,
        since: object,
        limit: int,
        params: Mapping[str, object],
    ) -> object: ...

    def fetch_open_orders(
        self,
        symbol: str | None,
        since: object,
        limit: int,
        params: Mapping[str, object],
    ) -> object: ...

    def fetch_order_book(self, symbol: str, limit: int) -> object: ...

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

    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot:
        """Read one bounded Cross-account truth window for a new ENTRY."""

        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
        )
        await _call_raw_exchange(exchange.load_markets, False)
        (
            order_book,
            balance,
            position_mode,
            positions,
            target_positions,
            regular_orders,
            conditional_orders,
        ) = await asyncio.gather(
            _call_raw_exchange(exchange.fetch_order_book, symbol, 5),
            _call_raw_exchange(exchange.fetch_balance, {"type": "future"}),
            _call_raw_exchange(exchange.fetch_position_mode, symbol, {}),
            _call_raw_exchange(exchange.fetch_positions, [], {}),
            _read_binance_usdm_admission_target_positions(
                exchange=exchange,
                symbol=symbol,
            ),
            _call_raw_exchange(
                exchange.fetch_open_orders,
                None,
                None,
                1_000,
                {"conditional": False},
            ),
            _call_raw_exchange(
                exchange.fetch_open_orders,
                None,
                None,
                1_000,
                {"conditional": True},
            ),
        )
        order_book_mapping = _require_mapping(order_book, name="admission order book")
        balance_mapping = _require_mapping(balance, name="admission balance")
        position_mode_mapping = _require_mapping(
            position_mode,
            name="admission position mode",
        )
        position_rows = _require_list(positions, name="admission positions")
        target_position_rows = _require_list(
            target_positions,
            name="admission requested-instrument positions",
        )
        regular_order_rows = _require_list(
            regular_orders,
            name="admission regular open orders",
        )
        conditional_order_rows = _require_list(
            conditional_orders,
            name="admission conditional open orders",
        )
        target_rows = tuple(target_position_rows)
        non_target_position_rows = tuple(
            row
            for row in position_rows
            if _venue_row_symbol(row, row_kind="position") != symbol
        )
        snapshot_position_rows = (*non_target_position_rows, *target_rows)
        return EntryAdmissionSnapshot(
            venue_id=request.venue_id,
            account_id=request.account_id,
            position_mode=_account_position_mode(position_mode_mapping),
            margin_mode=_admission_margin_mode(list(snapshot_position_rows)),
            total_wallet_balance=_admission_balance_decimal(
                balance_mapping,
                key="totalWalletBalance",
            ),
            total_margin_balance=_admission_balance_decimal(
                balance_mapping,
                key="totalMarginBalance",
            ),
            total_initial_margin=_admission_balance_decimal(
                balance_mapping,
                key="totalInitialMargin",
            ),
            total_maintenance_margin=_admission_balance_decimal(
                balance_mapping,
                key="totalMaintMargin",
            ),
            available_margin=_admission_balance_decimal(
                balance_mapping,
                key="availableBalance",
            ),
            best_bid_price=_top_of_book_price(order_book_mapping, "bids"),
            best_ask_price=_top_of_book_price(order_book_mapping, "asks"),
            instrument_facts=(
                _admission_instrument_facts(
                    target_rows,
                    exchange_instrument_id=request.exchange_instrument_id,
                ),
            ),
            positions=tuple(
                _admission_position(
                    row,
                    exchange_instrument_id=self._instrument_id_for_symbol(
                        venue_id=request.venue_id,
                        symbol=_venue_row_symbol(row, row_kind="position"),
                    ),
                )
                for row in snapshot_position_rows
            ),
            open_orders=tuple(
                _admission_order(
                    row,
                    exchange_instrument_id=self._instrument_id_for_symbol(
                        venue_id=request.venue_id,
                        symbol=_venue_row_symbol(row, row_kind="open-order"),
                    ),
                )
                for row in (*regular_order_rows, *conditional_order_rows)
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
        if request.venue_id != "binance-usdm":
            raise RuntimeError("maintenance-margin rules are unsupported for venue")
        raw_leverage_brackets = getattr(exchange, "fapiPrivateGetLeverageBracket", None)
        if not callable(raw_leverage_brackets):
            raise RuntimeError("venue does not expose maintenance-margin brackets")
        await _call_raw_exchange(exchange.load_markets, False)
        market = exchange.market(symbol)
        quantity_step, price_tick, min_quantity, min_notional = (
            _instrument_rules(market)
        )
        market_id = _binance_market_id(symbol)
        bracket_rows = _require_list(
            await _call_raw_exchange(
                raw_leverage_brackets,
                {"symbol": market_id},
            ),
            name="maintenance-margin brackets",
        )
        maintenance_margin_brackets, bracket_max_leverage = (
            _binance_maintenance_margin_brackets(
                bracket_rows,
                venue_id=request.venue_id,
                market_id=market_id,
            )
        )
        market_max_leverage = _market_max_leverage(market)
        exchange_max_leverage = (
            bracket_max_leverage
            if market_max_leverage is None
            else min(bracket_max_leverage, market_max_leverage)
        )
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=quantity_step,
            price_tick=price_tick,
            min_quantity=min_quantity,
            min_notional=min_notional,
            exchange_max_leverage=exchange_max_leverage,
            maintenance_margin_brackets=maintenance_margin_brackets,
            maintenance_margin_brackets_digest=canonical_digest(
                maintenance_margin_brackets
            ),
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
        quantity, average_entry_price, liquidation_price = _position_details(
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
            liquidation_price=liquidation_price,
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
        position_quantity, _, _ = _position_details(
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

    async def set_leverage(
        self,
        request: VenueSetLeverageRequest,
    ) -> SetLeverageCommandResult:
        """Perform one signed leverage mutation then prove its exact read-back."""

        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
        )
        response = await _call_exchange(
            exchange.set_leverage,
            request.payload.desired_leverage,
            symbol,
            {},
            clock_ms=self._clock_ms,
        )
        if isinstance(response, ExchangeCommandResult):
            if response.status is ExchangeCommandStatus.REJECTED:
                raise VenueMutationRejected(str(response.reason))
            raise RuntimeError("leverage mutation has no authoritative result")
        configured_leverage, _, _ = await _read_exact_instrument_leverage(
            exchange=exchange,
            symbol=symbol,
        )
        observed_at_ms = self._clock_ms()
        return SetLeverageCommandResult(
            exchange_configured_leverage=configured_leverage,
            leverage_verified_at_ms=observed_at_ms,
            leverage_verification_digest=canonical_digest(
                {
                    "command_id": request.command_id,
                    "venue_id": request.venue_id,
                    "account_id": request.account_id,
                    "exchange_instrument_id": request.exchange_instrument_id,
                    "desired_leverage": request.payload.desired_leverage,
                    "exchange_configured_leverage": configured_leverage,
                    "verified_at_ms": observed_at_ms,
                }
            ),
        )

    async def read_configured_leverage(
        self,
        request: LeverageTruthRequest,
    ) -> LeverageTruthSnapshot:
        """Read bounded exact-instrument truth without guessing mutation outcome."""

        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
        )
        positions, regular_orders, conditional_orders = await asyncio.gather(
            _call_raw_exchange(exchange.fetch_positions, [symbol], {}),
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
        configured_leverage, long_quantity, short_quantity = (
            _configured_leverage_and_position_quantities(
                _require_list(positions, name="leverage positions"),
                expected_symbol=symbol,
            )
        )
        return LeverageTruthSnapshot(
            exchange_configured_leverage=configured_leverage,
            long_position_quantity=long_quantity,
            short_position_quantity=short_quantity,
            regular_open_order_ids=_open_exchange_order_ids(
                _require_list(regular_orders, name="regular leverage orders")
            ),
            conditional_open_order_ids=_open_exchange_order_ids(
                _require_list(
                    conditional_orders,
                    name="conditional leverage orders",
                )
            ),
            observed_at_ms=self._clock_ms(),
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

    def _instrument_id_for_symbol(
        self,
        *,
        venue_id: str,
        symbol: str,
    ) -> str:
        for (configured_venue_id, exchange_instrument_id), venue_symbol in (
            self._venue_symbols.items()
        ):
            if configured_venue_id == venue_id and venue_symbol == symbol:
                return exchange_instrument_id
        return f"unmapped:{symbol}"


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


def _admission_balance_decimal(
    balance: Mapping[object, object],
    *,
    key: str,
) -> Decimal:
    info = balance.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    value = raw_info.get(key)
    if value is None:
        raise RuntimeError(f"venue admission balance lacks {key}")
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise RuntimeError(f"venue admission balance {key} is invalid")
    return result


def _admission_margin_mode(rows: list[object]) -> Literal["cross", "isolated"]:
    modes: set[str] = set()
    for row in rows:
        mapping = _require_mapping(row, name="admission position row")
        raw = _mapping_value(mapping.get("info"), "marginType")
        if raw is None:
            raw = mapping.get("marginMode")
        normalized = str(raw or "").strip().lower()
        if normalized not in {"cross", "isolated"}:
            raise RuntimeError("venue admission position lacks valid margin mode")
        modes.add(normalized)
    if len(modes) != 1:
        raise RuntimeError("venue admission margin mode is absent or contradictory")
    return next(iter(modes))  # type: ignore[return-value]


def _admission_instrument_facts(
    rows: tuple[object, ...],
    *,
    exchange_instrument_id: str,
) -> AdmissionInstrumentFacts:
    values: set[tuple[Decimal, int]] = set()
    for row in rows:
        mapping = _require_mapping(row, name="requested admission position row")
        info = mapping.get("info")
        raw_info = info if isinstance(info, Mapping) else {}
        mark_price = Decimal(str(mapping.get("markPrice") or raw_info.get("markPrice") or "0"))
        leverage_raw = mapping.get("leverage") or raw_info.get("leverage")
        try:
            leverage = int(str(leverage_raw))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("venue admission leverage is invalid") from exc
        if str(leverage_raw).strip() != str(leverage) or leverage <= 0:
            raise RuntimeError("venue admission leverage must be a positive integer")
        if not mark_price.is_finite() or mark_price <= 0:
            raise RuntimeError("venue admission mark price is invalid")
        values.add((mark_price, leverage))
    if len(values) != 1:
        raise RuntimeError("venue admission instrument facts are absent or contradictory")
    mark_price, configured_leverage = next(iter(values))
    return AdmissionInstrumentFacts(
        exchange_instrument_id=exchange_instrument_id,
        mark_price=mark_price,
        configured_leverage=configured_leverage,
    )


async def _read_binance_usdm_admission_target_positions(
    *,
    exchange: _CcxtExchange,
    symbol: str,
) -> list[object]:
    """Read the requested Binance symbol, including its zero long/short sides."""

    market_id = _binance_market_id(symbol)
    rows = _require_list(
        await _call_raw_exchange(
            exchange.fapiPrivateV2GetPositionRisk,
            {"symbol": market_id},
        ),
        name="admission requested-instrument position risk",
    )
    normalized_rows: list[object] = []
    position_sides: set[str] = set()
    for row in rows:
        raw = _require_mapping(
            row,
            name="admission requested-instrument position risk row",
        )
        if str(raw.get("symbol") or "").strip() != market_id:
            continue
        position_side = str(raw.get("positionSide") or "").strip().upper()
        if position_side not in {"LONG", "SHORT"}:
            raise RuntimeError(
                "venue admission requested-instrument position side is invalid"
            )
        position_sides.add(position_side)
        normalized_rows.append(
            {
                "symbol": symbol,
                "contracts": raw.get("positionAmt"),
                "entryPrice": raw.get("entryPrice"),
                "info": dict(raw),
            }
        )
    if len(normalized_rows) != 2 or position_sides != {"LONG", "SHORT"}:
        raise RuntimeError(
            "venue admission snapshot lacks requested instrument position sides"
        )
    return normalized_rows


def _venue_row_symbol(value: object, *, row_kind: str) -> str:
    mapping = _require_mapping(value, name=f"admission {row_kind} row")
    symbol = str(mapping.get("symbol") or "").strip()
    if not symbol:
        raise RuntimeError(f"venue admission {row_kind} lacks symbol")
    return symbol


def _admission_position(
    value: object,
    *,
    exchange_instrument_id: str,
) -> AdmissionPosition:
    mapping = _require_mapping(value, name="admission position row")
    quantity = abs(Decimal(str(mapping.get("contracts") or "0")))
    if not quantity.is_finite():
        raise RuntimeError("venue admission position quantity is invalid")
    if quantity == 0:
        average_entry_price = None
    else:
        average_entry_price = Decimal(
            str(
                mapping.get("entryPrice")
                or _mapping_value(mapping.get("info"), "entryPrice")
                or "0"
            )
        )
        if not average_entry_price.is_finite() or average_entry_price <= 0:
            raise RuntimeError("open venue admission position lacks entry price")
    return AdmissionPosition(
        exchange_instrument_id=exchange_instrument_id,
        position_side=_row_position_side(mapping),
        quantity=quantity,
        average_entry_price=average_entry_price,
    )


def _admission_order(
    value: object,
    *,
    exchange_instrument_id: str,
) -> AdmissionOrder:
    mapping = _require_mapping(value, name="admission open-order row")
    return AdmissionOrder(
        exchange_order_id=str(mapping.get("id") or "").strip(),
        venue_client_order_id=(
            str(mapping.get("clientOrderId")).strip()
            if mapping.get("clientOrderId") is not None
            else None
        ),
        exchange_instrument_id=exchange_instrument_id,
        position_side=_row_position_side(mapping),
        reduce_only=_boolean_field(mapping, "reduceOnly"),
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


async def _read_exact_instrument_leverage(
    *,
    exchange: _CcxtExchange,
    symbol: str,
) -> tuple[int, Decimal, Decimal]:
    rows = _require_list(
        await _call_raw_exchange(exchange.fetch_positions, [symbol], {}),
        name="leverage positions",
    )
    return _configured_leverage_and_position_quantities(rows, expected_symbol=symbol)


def _configured_leverage_and_position_quantities(
    rows: list[object],
    *,
    expected_symbol: str,
) -> tuple[int, Decimal, Decimal]:
    leverage_values: set[int] = set()
    long_quantity = Decimal("0")
    short_quantity = Decimal("0")
    matched_rows = 0
    for value in rows:
        mapping = _require_mapping(value, name="leverage position row")
        if str(mapping.get("symbol") or "").strip() != expected_symbol:
            continue
        matched_rows += 1
        raw_leverage = mapping.get("leverage") or _mapping_value(
            mapping.get("info"), "leverage"
        )
        try:
            leverage = int(str(raw_leverage))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("venue leverage read-back is invalid") from exc
        if str(raw_leverage).strip() != str(leverage) or leverage <= 0:
            raise RuntimeError("venue leverage read-back must be a positive integer")
        leverage_values.add(leverage)
        quantity = abs(Decimal(str(mapping.get("contracts") or "0")))
        if not quantity.is_finite():
            raise RuntimeError("venue leverage position quantity is invalid")
        side = _row_position_side(mapping)
        if side == "long":
            long_quantity += quantity
        else:
            short_quantity += quantity
    if matched_rows == 0 or len(leverage_values) != 1:
        raise RuntimeError("venue leverage read-back is absent or contradictory")
    return next(iter(leverage_values)), long_quantity, short_quantity


def _position_details(
    rows: list[object],
    *,
    expected_symbol: str,
    position_side: Literal["long", "short"],
) -> tuple[Decimal, Decimal | None, Decimal | None]:
    total_quantity = Decimal("0")
    weighted_entry = Decimal("0")
    liquidation_prices: set[Decimal] = set()
    liquidation_evidence_missing = False
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
        raw_liquidation = (
            value.get("liquidationPrice")
            or _mapping_value(value.get("info"), "liquidationPrice")
        )
        if raw_liquidation in (None, "", "0", 0):
            liquidation_evidence_missing = True
            continue
        liquidation = Decimal(str(raw_liquidation))
        if not liquidation.is_finite() or liquidation <= 0:
            raise RuntimeError("venue liquidation evidence is invalid")
        liquidation_prices.add(liquidation)
    if total_quantity == 0:
        return Decimal("0"), None, None
    liquidation_price = (
        next(iter(liquidation_prices))
        if not liquidation_evidence_missing and len(liquidation_prices) == 1
        else None
    )
    return total_quantity, weighted_entry / total_quantity, liquidation_price


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


def _top_of_book_price(
    value: Mapping[object, object],
    side: Literal["bids", "asks"],
) -> Decimal:
    rows = value.get(side)
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"venue order book {side} is missing")
    top = rows[0]
    if not isinstance(top, (list, tuple)) or not top:
        raise RuntimeError(f"venue order book {side} top level is invalid")
    result = Decimal(str(top[0] or "0"))
    if result <= 0:
        raise RuntimeError(f"venue order book {side} price is non-positive")
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


def _binance_market_id(symbol: str) -> str:
    base_quote = symbol.split(":", 1)[0]
    parts = base_quote.split("/")
    if len(parts) != 2 or not all(parts):
        raise RuntimeError("venue symbol cannot produce a Binance market identity")
    return "".join(parts)


def _market_max_leverage(market: Mapping[str, object]) -> int | None:
    raw = _nested_market_value(market, "limits", "leverage", "max")
    if raw is None:
        return None
    try:
        parsed = int(str(raw))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("venue market lacks a valid maximum leverage") from exc
    if str(raw).strip() != str(parsed) or parsed <= 0:
        raise RuntimeError("venue market maximum leverage must be a positive integer")
    return parsed


def _binance_maintenance_margin_brackets(
    rows: list[object],
    *,
    venue_id: str,
    market_id: str,
) -> tuple[tuple[MaintenanceMarginBracket, ...], int]:
    matching = tuple(
        row
        for row in rows
        if isinstance(row, Mapping) and str(row.get("symbol") or "") == market_id
    )
    if len(matching) != 1:
        raise RuntimeError("venue maintenance-margin brackets lack exact instrument truth")
    raw_brackets = matching[0].get("brackets")
    if not isinstance(raw_brackets, list) or not raw_brackets:
        raise RuntimeError("venue maintenance-margin bracket rows are invalid")
    parsed: list[MaintenanceMarginBracket] = []
    max_leverages: list[int] = []
    for row in raw_brackets:
        if not isinstance(row, Mapping):
            raise RuntimeError("venue maintenance-margin bracket is not a mapping")
        raw_number = row.get("bracket")
        try:
            number = int(str(raw_number))
            initial_leverage = int(str(row.get("initialLeverage")))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("venue maintenance-margin leverage is invalid") from exc
        if (
            str(raw_number).strip() != str(number)
            or str(row.get("initialLeverage")).strip() != str(initial_leverage)
            or number <= 0
            or initial_leverage <= 0
        ):
            raise RuntimeError("venue maintenance-margin bracket identities are invalid")
        cap_value = Decimal(str(row.get("notionalCap") or "0"))
        parsed.append(
            MaintenanceMarginBracket(
                bracket_id=f"{venue_id}:{market_id}:{number}",
                notional_floor=Decimal(str(row.get("notionalFloor") or "0")),
                notional_cap=None if cap_value == 0 else cap_value,
                maintenance_margin_rate=Decimal(
                    str(row.get("maintMarginRatio") or "0")
                ),
                maintenance_amount=Decimal(str(row.get("cum") or "0")),
            )
        )
        max_leverages.append(initial_leverage)
    ordered = tuple(sorted(parsed, key=lambda item: item.notional_floor))
    if tuple(item.bracket_id for item in ordered) != tuple(
        item.bracket_id for item in parsed
    ):
        raise RuntimeError("venue maintenance-margin brackets are not sorted")
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous.notional_cap != current.notional_floor:
            raise RuntimeError("venue maintenance-margin brackets are discontinuous")
    return ordered, max(max_leverages)


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


def _open_exchange_order_ids(rows: list[object]) -> tuple[str, ...]:
    identities: set[str] = set()
    for value in rows:
        mapping = _require_mapping(value, name="venue open-order row")
        identity = str(mapping.get("id") or "").strip()
        if not identity:
            raise RuntimeError("venue open order lacks exchange identity")
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
