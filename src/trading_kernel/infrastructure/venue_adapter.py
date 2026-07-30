"""Typed CCXT translation at the sole trading-kernel venue boundary."""

from __future__ import annotations

import asyncio
import inspect
import itertools
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, cast

from ccxt.base import errors as ccxt_errors  # type: ignore[import-untyped]
from pydantic import JsonValue

from src.trading_kernel.application.certify_universe_instrument import (
    InstrumentCertificationReadRequest,
    InstrumentCertificationSnapshot,
    InstrumentCertificationTransientFailure,
)
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.application.ports import (
    LeverageTruthRequest,
    LeverageTruthSnapshot,
    VenueCommandRequest,
    VenueMutationFailure,
    VenueMutationRejected,
    VenueSetLeverageRequest,
    VenueTruthRequest,
)
from src.trading_kernel.application.runtime_facts import (
    AccountRiskSnapshotRequest,
    EntryAdmissionSnapshotRequest,
    FeeDiscountCapabilityFacts,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
    LifecycleFactsRequest,
    PositionSnapshotRequest,
    ReviewEconomicsRequest,
)
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskPosition,
    AccountRiskSnapshot,
    MaintenanceMarginBracket,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionOrder,
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.exit_policy import LifecycleMarketFacts
from src.trading_kernel.domain.fee_valuation import (
    FeeValuationEvidence,
    NativeFee,
    value_native_fee,
)
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.instrument_certification import (
    InstrumentCertificationFacts,
)
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_ccxt_symbol,
    parse_binance_usdm_instrument_id,
    to_ccxt_symbol,
    to_exchange_instrument_id,
)
from src.trading_kernel.domain.order_attribution import (
    OrderRole,
    ResolvedOrderIdentity,
)
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.review import ReviewEconomicsFacts, ReviewFill
from src.trading_kernel.domain.venue_truth import (
    VenueLookupStatus,
    VenueOrderTruth,
    VenueTruthSnapshot,
)
from src.trading_kernel.infrastructure.binance_fee_valuation import (
    read_bnbusdt_fee_valuation_evidence,
)
from src.trading_kernel.infrastructure.binance_order_attribution import (
    resolve_binance_order_identity,
)

CcxtNetworkError = ccxt_errors.NetworkError


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

    def fapiPublicGetPremiumIndex(self, params: Mapping[str, object]) -> object: ...

    def fapiPrivateV2GetAccount(self, params: Mapping[str, object]) -> object: ...

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


@dataclass
class _ReviewFeeValuationContext:
    """One Review-scoped readonly BNB index snapshot, fetched only on demand."""

    exchange: object
    review_observed_at_ms: int
    bnb_snapshot: FeeValuationEvidence | None = None

    async def valuation_for(self, native_fee: NativeFee) -> FeeValuationEvidence:
        if native_fee.asset == "USDT":
            return FeeValuationEvidence(
                method="native_usdt",
                rate_usdt_per_asset=Decimal(1),
                price_pair=None,
                observed_at_ms=None,
                valued_at_ms=self.review_observed_at_ms,
            )
        if self.bnb_snapshot is None:
            self.bnb_snapshot = await read_bnbusdt_fee_valuation_evidence(
                exchange=self.exchange,
                review_observed_at_ms=self.review_observed_at_ms,
            )
        return self.bnb_snapshot


_AUTHORITATIVE_REJECTION_TYPES = {
    "BadRequest",
    "InsufficientFunds",
    "InvalidOrder",
    "OperationRejected",
}
_ORDER_NOT_FOUND_TYPES = {"OrderNotFound"}
_EXCHANGE_CODE = re.compile(r'["\']code["\']\s*:\s*(-?[0-9]{1,6})')


class InstrumentCertificationSnapshotContradiction(RuntimeError):
    """Kernel ownership projection contradicts authenticated Venue quantity."""


class CcxtVenueAdapter:
    def __init__(
        self,
        *,
        exchanges: Mapping[tuple[str, str], _CcxtExchange],
        settlement_assets: Mapping[tuple[str, str], str] | None = None,
        taker_fee_rates: Mapping[tuple[str, str], Decimal] | None = None,
        default_settlement_asset: str | None = None,
        default_taker_fee_rate: Decimal | None = None,
        clock_ms: Callable[[], int],
    ) -> None:
        self._exchanges = dict(exchanges)
        self._settlement_assets = dict(settlement_assets or {})
        self._taker_fee_rates = dict(taker_fee_rates or {})
        self._default_settlement_asset = default_settlement_asset
        self._default_taker_fee_rate = default_taker_fee_rate
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
            account_risk_snapshot,
            regular_orders,
            conditional_orders,
        ) = await asyncio.gather(
            _call_raw_exchange(exchange.fetch_order_book, symbol, 5),
            self._read_account_risk_snapshot(
                exchange=exchange,
                symbol=symbol,
                venue_id=request.venue_id,
                account_id=request.account_id,
                exchange_instrument_id=request.exchange_instrument_id,
                observed_at_ms=request.observed_at_ms,
                valid_for_ms=request.valid_for_ms,
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
        if not isinstance(account_risk_snapshot, AccountRiskSnapshot):
            raise TypeError("admission account risk snapshot is invalid")
        regular_order_rows = _require_list(
            regular_orders,
            name="admission regular open orders",
        )
        conditional_order_rows = _require_list(
            conditional_orders,
            name="admission conditional open orders",
        )
        return EntryAdmissionSnapshot(
            account_risk_snapshot=account_risk_snapshot,
            best_bid_price=_top_of_book_price(order_book_mapping, "bids"),
            best_ask_price=_top_of_book_price(order_book_mapping, "asks"),
            open_orders=tuple(
                _admission_order(
                    row,
                    exchange_instrument_id=self._instrument_id_for_symbol(
                        venue_id=request.venue_id,
                        symbol=_venue_row_symbol(row, row_kind="open-order"),
                    ),
                    order_namespace="regular",
                )
                for row in regular_order_rows
            )
            + tuple(
                _admission_order(
                    row,
                    exchange_instrument_id=self._instrument_id_for_symbol(
                        venue_id=request.venue_id,
                        symbol=_venue_row_symbol(row, row_kind="open-order"),
                    ),
                    order_namespace="conditional",
                )
                for row in conditional_order_rows
            ),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_account_risk_snapshot(
        self,
        request: AccountRiskSnapshotRequest,
    ) -> AccountRiskSnapshot:
        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
        )
        await _call_raw_exchange(exchange.load_markets, False)
        return await self._read_account_risk_snapshot(
            exchange=exchange,
            symbol=symbol,
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
            observed_at_ms=request.observed_at_ms,
            valid_for_ms=request.valid_for_ms,
        )

    async def _read_account_risk_snapshot(
        self,
        *,
        exchange: _CcxtExchange,
        symbol: str,
        venue_id: str,
        account_id: str,
        exchange_instrument_id: str,
        observed_at_ms: int,
        valid_for_ms: int,
    ) -> AccountRiskSnapshot:
        raw_account = getattr(exchange, "fapiPrivateV2GetAccount", None)
        if not callable(raw_account):
            raise TypeError("Binance venue lacks USD-M account readonly lookup")
        account_result, position_mode_result, target_position_result = (
            await asyncio.gather(
                _call_raw_exchange(raw_account, {}),
                _call_raw_exchange(exchange.fetch_position_mode, symbol, {}),
                _read_binance_usdm_admission_target_positions(
                    exchange=exchange,
                    symbol=symbol,
                    require_mark_price=True,
                ),
            )
        )
        account = _require_mapping(account_result, name="USD-M account risk")
        position_mode = _account_position_mode(
            _require_mapping(
                position_mode_result,
                name="account risk position mode",
            )
        )
        target_rows = tuple(
            _require_list(
                target_position_result,
                name="account risk target positions",
            )
        )
        settlement_asset = self._settlement_assets.get(
            (venue_id, exchange_instrument_id),
            self._default_settlement_asset,
        )
        if settlement_asset is None:
            settlement_asset = parse_binance_usdm_instrument_id(
                exchange_instrument_id
            ).quote_asset
        return _build_account_risk_snapshot(
            account=account,
            target_rows=target_rows,
            venue_id=venue_id,
            account_id=account_id,
            exchange_instrument_id=exchange_instrument_id,
            symbol=symbol,
            settlement_asset=settlement_asset,
            position_mode=position_mode,
            observed_at_ms=observed_at_ms,
            valid_for_ms=valid_for_ms,
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
            raise TypeError("venue does not expose maintenance-margin brackets")
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
        notional_coefficient, coefficient_certified = (
            _binance_notional_coefficient(
                bracket_rows,
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
                {
                    "maintenance_margin_brackets": maintenance_margin_brackets,
                    "notional_coefficient": notional_coefficient,
                    "notional_coefficient_certified": coefficient_certified,
                }
            ),
            notional_coefficient=notional_coefficient,
            notional_coefficient_certified=coefficient_certified,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_instrument_certification(
        self,
        request: InstrumentCertificationReadRequest,
    ) -> InstrumentCertificationSnapshot:
        """Read one exact product/account snapshot without mutation authority."""

        try:
            return await self._read_instrument_certification_snapshot(request)
        except CcxtNetworkError as exc:
            raise InstrumentCertificationTransientFailure(
                "authenticated readonly Venue/network failure"
            ) from exc

    async def _read_instrument_certification_snapshot(
        self,
        request: InstrumentCertificationReadRequest,
    ) -> InstrumentCertificationSnapshot:
        target = request.target
        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=target.venue_id,
            account_id=target.account_id,
            exchange_instrument_id=target.exchange_instrument_id,
        )
        await _call_raw_exchange(exchange.load_markets, False)
        market = exchange.market(symbol)
        quantity_step, price_tick, min_quantity, min_notional = (
            _raw_instrument_rules(market)
        )
        rules_read = (
            self.read_instrument_rules(
                InstrumentRulesRequest(
                    venue_id=target.venue_id,
                    account_id=target.account_id,
                    exchange_instrument_id=target.exchange_instrument_id,
                    observed_at_ms=request.observed_at_ms,
                    valid_for_ms=request.valid_for_ms,
                )
            )
            if all(
                value is not None
                for value in (
                    quantity_step,
                    price_tick,
                    min_quantity,
                    min_notional,
                )
            )
            else _empty_value()
        )
        (
            rules,
            position_mode,
            target_positions,
            regular_orders,
            conditional_orders,
        ) = await asyncio.gather(
            rules_read,
            _call_raw_exchange(exchange.fetch_position_mode, symbol, {}),
            _read_binance_usdm_admission_target_positions(
                exchange=exchange,
                symbol=symbol,
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
        position_rows = _require_list(
            target_positions,
            name="certification target positions",
        )
        configured_leverage, long_quantity, short_quantity = (
            _configured_leverage_and_position_quantities(
                position_rows,
                expected_symbol=symbol,
            )
        )
        unowned_position_qty = Decimal(0)
        for position_side, quantity in (
            ("long", long_quantity),
            ("short", short_quantity),
        ):
            domain_key = NettingDomain(
                venue_id=target.venue_id,
                account_id=target.account_id,
                exchange_instrument_id=target.exchange_instrument_id,
                position_side=cast(Literal["long", "short"], position_side),
            ).key()
            projected_quantity = request.ownership.projected_position_quantity(
                domain_key
            )
            if domain_key in request.ownership.owned_position_domain_keys:
                if projected_quantity is None:
                    raise InstrumentCertificationSnapshotContradiction(
                        "owned_position_projection_missing"
                    )
                if projected_quantity > quantity:
                    raise InstrumentCertificationSnapshotContradiction(
                        "projected_position_exceeds_venue"
                    )
                unowned_position_qty += quantity - projected_quantity
            elif projected_quantity is not None:
                raise InstrumentCertificationSnapshotContradiction(
                    "projected_position_domain_unowned"
                )
            else:
                unowned_position_qty += quantity

        open_order_sources: tuple[
            tuple[Literal["regular", "conditional"], list[object]],
            tuple[Literal["regular", "conditional"], list[object]],
        ] = (
            (
                "regular",
                _require_list(
                    regular_orders,
                    name="certification regular open orders",
                ),
            ),
            (
                "conditional",
                _require_list(
                    conditional_orders,
                    name="certification conditional open orders",
                ),
            ),
        )
        open_orders = tuple(
            _admission_order(
                row,
                exchange_instrument_id=target.exchange_instrument_id,
                order_namespace=namespace,
            )
            for namespace, rows in open_order_sources
            for row in rows
        )
        owned_order_ids = set(request.ownership.owned_exchange_order_ids)
        return InstrumentCertificationSnapshot(
            facts=InstrumentCertificationFacts(
                runtime_profile_id=target.runtime_profile_id,
                exchange_instrument_id=target.exchange_instrument_id,
                product_status=_certification_product_status(market),
                tick_size=price_tick,
                step_size=quantity_step,
                min_qty=min_quantity,
                min_notional=min_notional,
                position_mode=_account_position_mode(
                    _require_mapping(
                        position_mode,
                        name="certification position mode",
                    )
                ),
                margin_mode=_admission_margin_mode(position_rows),
                configured_leverage=configured_leverage,
                notional_coefficient_certified=(
                    rules is not None and rules.notional_coefficient_certified
                ),
                unowned_position_qty=unowned_position_qty,
                unowned_open_order_count=sum(
                    order.exchange_order_id not in owned_order_ids
                    for order in open_orders
                ),
                observed_at_ms=request.observed_at_ms,
            ),
            instrument_rules=rules,
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
        (
            quantity,
            average_entry_price,
            liquidation_price,
            liquidation_observation_status,
        ) = _position_details(
            position_rows,
            expected_symbol=symbol,
            position_side=domain.position_side,
        )
        open_orders = _position_open_orders(
            _require_list(regular_orders, name="regular open orders"),
            expected_symbol=symbol,
            position_side=domain.position_side,
            order_namespace="regular",
        ) + _position_open_orders(
            _require_list(conditional_orders, name="conditional open orders"),
            expected_symbol=symbol,
            position_side=domain.position_side,
            order_namespace="conditional",
        )
        return PositionSnapshot(
            netting_domain=domain,
            quantity=quantity,
            average_entry_price=average_entry_price,
            venue_reported_liquidation_price=liquidation_price,
            venue_reported_liquidation_observation_status=(
                liquidation_observation_status
            ),
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
        settlement_asset = self._settlement_assets.get(
            key,
            self._default_settlement_asset,
        )
        taker_fee_rate = self._taker_fee_rates.get(
            key,
            self._default_taker_fee_rate,
        )
        if not settlement_asset:
            raise RuntimeError("canonical instrument has no settlement asset mapping")
        if taker_fee_rate is None:
            raise RuntimeError("canonical instrument has no taker fee rate")

        tp1_exchange_order_id = request.tp1_exchange_order_id
        # The latest venue candle can still be open and is excluded below.
        candle_limit = max(request.atr_period + 2, request.structure_window_bars + 1)
        positions_call = _call_raw_exchange(
            exchange.fetch_positions,
            [symbol],
            {"positionSide": domain.position_side.upper()},
        )
        resolved_entry = await resolve_binance_order_identity(
            exchange=exchange,
            reference=request.entry_order_reference,
            observed_at_ms=request.observed_at_ms,
        )
        if resolved_entry.actual_order_id is None:
            raise RuntimeError("filled entry command has no executable order identity")
        entry_fills_call = _call_raw_exchange(
            exchange.fetch_my_trades,
            symbol,
            None,
            100,
            {"orderId": resolved_entry.actual_order_id},
        )
        tp1_order_call = (
            _call_raw_exchange(
                exchange.fetch_order,
                tp1_exchange_order_id,
                symbol,
                {},
            )
            if tp1_exchange_order_id is not None
            else _empty_value()
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
        positions, entry_fills, tp1_order, candle_rows = await asyncio.gather(
            positions_call,
            entry_fills_call,
            tp1_order_call,
            candles_call,
        )
        position_quantity, _, _, _ = _position_details(
            _require_list(positions, name="positions"),
            expected_symbol=symbol,
            position_side=domain.position_side,
        )
        lifecycle_fee_context = _ReviewFeeValuationContext(
            exchange=exchange,
            review_observed_at_ms=request.observed_at_ms,
        )
        attributed_entry_fills: list[ReviewFill] = []
        bnb_entry_fee_upper_quote = Decimal(0)
        for row in _require_list(entry_fills, name="entry fills"):
            if _review_fee_asset(row, settlement_asset=settlement_asset) == "BNB":
                notional = _exact_order_fill_notional(
                    row,
                    resolved=resolved_entry,
                    position_side=domain.position_side,
                    entry_time_ms=request.exposure_started_at_ms,
                    exit_time_ms=request.observed_at_ms,
                )
                if notional is not None:
                    bnb_entry_fee_upper_quote += notional * taker_fee_rate
                continue
            fill = await _review_fill(
                row,
                resolved=resolved_entry,
                fee_valuation_context=lifecycle_fee_context,
                settlement_asset=settlement_asset,
                position_side=domain.position_side,
                entry_time_ms=request.exposure_started_at_ms,
                exit_time_ms=request.observed_at_ms,
            )
            if fill is not None:
                attributed_entry_fills.append(fill)
        if not attributed_entry_fills and bnb_entry_fee_upper_quote == 0:
            raise RuntimeError("entry fills are unavailable for the exact order identity")
        entry_fee_quote = sum(
            (fill.fee_quote for fill in attributed_entry_fills),
            Decimal(0),
        ) + bnb_entry_fee_upper_quote
        tp1_quantity, tp1_average_price = _order_fill_metrics(tp1_order)
        allocated_entry_fee = (
            entry_fee_quote * position_quantity / request.entry_quantity
        )
        market_facts = (
            _lifecycle_market_facts(
                _require_list(candle_rows, name="lifecycle candles"),
                timeframe=request.timeframe,
                observed_at_ms=request.observed_at_ms,
                entered_at_ms=request.exposure_started_at_ms,
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

    async def read_fee_discount_capability(
        self,
        *,
        observed_at_ms: int,
    ) -> FeeDiscountCapabilityFacts:
        if observed_at_ms <= 0:
            raise ValueError("BNB fee capability observation time must be positive")
        candidates = tuple(
            (account_id, exchange)
            for (venue_id, account_id), exchange in self._exchanges.items()
            if venue_id == "binance-usdm"
        )
        if len(candidates) != 1:
            raise RuntimeError("BNB fee capability requires one Binance USD-M account")
        _, exchange = candidates[0]
        fee_burn = getattr(exchange, "fapiPrivateGetFeeBurn", None)
        if not callable(fee_burn):
            raise TypeError("Binance venue lacks fee burn readonly lookup")
        fee_burn_result, balance_result = await asyncio.gather(
            _call_raw_exchange(fee_burn, {}),
            _call_raw_exchange(exchange.fetch_balance, {"type": "future"}),
        )
        fee_burn_mapping = _require_mapping(fee_burn_result, name="fee burn")
        enabled = fee_burn_mapping.get("feeBurn")
        if not isinstance(enabled, bool):
            raise TypeError("Binance fee burn readonly fact is invalid")
        return FeeDiscountCapabilityFacts(
            fee_burn_enabled=enabled,
            bnb_futures_wallet_balance=_bnb_futures_wallet_balance(balance_result),
            observed_at_ms=observed_at_ms,
            source="binance_usdm_readonly",
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
            (domain.venue_id, domain.exchange_instrument_id),
            self._default_settlement_asset,
        )
        if not settlement_asset:
            raise RuntimeError("canonical instrument has no settlement asset mapping")

        references = (
            request.entry_order_reference,
            *request.exit_order_references,
        )
        resolved_references = tuple(
            await asyncio.gather(
                *(
                    resolve_binance_order_identity(
                        exchange=exchange,
                        reference=reference,
                        observed_at_ms=request.observed_at_ms,
                    )
                    for reference in references
                )
            )
        )
        fee_valuation_context = _ReviewFeeValuationContext(
            exchange=exchange,
            review_observed_at_ms=request.observed_at_ms,
        )
        fills_by_trade_id: dict[str, ReviewFill] = {}
        for resolved in resolved_references:
            if resolved.actual_order_id is None:
                continue
            rows = _require_list(
                await _call_raw_exchange(
                    exchange.fetch_my_trades,
                    symbol,
                    request.entry_time_ms,
                    100,
                    {"orderId": resolved.actual_order_id},
                ),
                name="review fills",
            )
            for row in rows:
                row_order_id = _review_row_order_id(row)
                if row_order_id != resolved.actual_order_id:
                    raise RuntimeError(
                        "review fill order id differs from requested actual order"
                    )
                fill = await _review_fill(
                    row,
                    resolved=resolved,
                    fee_valuation_context=fee_valuation_context,
                    settlement_asset=settlement_asset,
                    position_side=domain.position_side,
                    entry_time_ms=request.entry_time_ms,
                    exit_time_ms=request.exit_time_ms,
                )
                existing = fills_by_trade_id.get(fill.exchange_trade_id)
                if existing is not None and existing != fill:
                    raise RuntimeError(
                        "venue returned contradictory duplicate review fill"
                    )
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
            if fill.role is OrderRole.ENTRY
        )
        exit_fills = tuple(
            fill
            for fill in ordered_fills
            if fill.role is OrderRole.EXIT
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
        exchange, symbol = self._resolve_exchange_and_symbol(
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
        )

        params: dict[str, object] = {"positionSide": request.position_side.upper()}

        if isinstance(request.payload, CancelCommandPayload):
            response = await _call_exchange(
                exchange.cancel_order,
                request.payload.exchange_order_id,
                symbol,
                {
                    **params,
                    "conditional": request.payload.order_namespace == "conditional",
                },
                clock_ms=self._clock_ms,
            )
            if isinstance(response, ExchangeCommandResult):
                return response
            if not isinstance(response, Mapping):
                raise TypeError("venue cancel response is not a mapping")
            return ExchangeCommandResult(
                status=ExchangeCommandStatus.ACCEPTED,
                observed_at_ms=self._clock_ms(),
                exchange_order_id=request.payload.exchange_order_id,
                venue_payload=_safe_response_payload(response),
            )

        if not isinstance(request.payload, OrderCommandPayload):
            raise TypeError("unsupported venue command payload")

        params["newClientOrderId"] = request.venue_client_order_id
        if request.payload.reduce_only and request.venue_id != "binance-usdm":
            params["reduceOnly"] = True
        if request.payload.time_in_force is not None:
            params["timeInForce"] = request.payload.time_in_force
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
            raise TypeError("venue response is not a mapping")
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
        try:
            response = await _call_exchange(
                exchange.set_leverage,
                request.payload.desired_leverage,
                symbol,
                {},
                clock_ms=self._clock_ms,
            )
        except Exception as exc:
            exchange_code = _exchange_error_code(exc)
            if exchange_code is None:
                raise
            raise VenueMutationFailure(
                f"exchange_code_{exchange_code}"
            ) from exc
        if isinstance(response, ExchangeCommandResult):
            if response.status is ExchangeCommandStatus.REJECTED:
                raise VenueMutationRejected(str(response.reason))
            raise TypeError("leverage mutation has no authoritative result")
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
        (
            leverage_and_positions,
            regular_orders,
            conditional_orders,
        ) = await asyncio.gather(
            _read_exact_instrument_leverage(exchange=exchange, symbol=symbol),
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
        configured_leverage, long_quantity, short_quantity = leverage_and_positions
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
                "positionSide": request.position_side.upper(),
                "conditional": request.payload.order_namespace == "conditional",
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
            namespace_orders = (
                conditional_orders
                if request.payload.order_namespace == "conditional"
                else regular_orders
            )
            order_response = _find_order_by_exchange_id(
                namespace_orders,
                exchange_order_id=request.payload.exchange_order_id,
            )
            order_known_open = order_response is not None
        else:
            order_known_open = False
        order = (
            None
            if order_response is None
            else _parse_order_truth(
                order_response,
                request=request,
                expected_symbol=symbol,
                known_open=order_known_open,
                order_namespace=(
                    request.payload.order_namespace
                    if isinstance(request.payload, CancelCommandPayload)
                    else "regular"
                ),
            )
        )
        fills = (
            _require_list(
                await _call_raw_exchange(
                    exchange.fetch_my_trades,
                    symbol,
                    None,
                    100,
                    {"orderId": order.exchange_order_id},
                ),
                name="fills",
            )
            if order is not None
            else []
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
                exchange_order_id=(
                    order.exchange_order_id if order is not None else None
                ),
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
        symbol = self._symbol_for(
            venue_id=venue_id,
            exchange_instrument_id=exchange_instrument_id,
        )
        exchange = self._exchanges.get((venue_id, account_id))
        if exchange is None:
            raise RuntimeError("venue/account adapter is not configured")
        return exchange, symbol

    def _symbol_for(
        self,
        *,
        venue_id: str,
        exchange_instrument_id: str,
    ) -> str:
        if venue_id != "binance-usdm":
            raise RuntimeError("canonical Binance USD-M instrument is unavailable")
        try:
            return to_ccxt_symbol(
                parse_binance_usdm_instrument_id(exchange_instrument_id)
            )
        except ValueError as exc:
            raise RuntimeError(
                "canonical Binance USD-M instrument is unavailable"
            ) from exc

    def _instrument_id_for_symbol(
        self,
        *,
        venue_id: str,
        symbol: str,
    ) -> str:
        if venue_id != "binance-usdm":
            raise RuntimeError("canonical Binance USD-M instrument is unavailable")
        try:
            return to_exchange_instrument_id(
                parse_binance_usdm_ccxt_symbol(symbol)
            )
        except ValueError as exc:
            raise RuntimeError(
                "canonical Binance USD-M instrument is unavailable"
            ) from exc


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


def _exchange_error_code(exc: Exception) -> str | None:
    if type(exc).__name__ != "ExchangeError":
        return None
    match = _EXCHANGE_CODE.search(str(exc))
    if match is None:
        return None
    return str(int(match.group(1)))


def _require_list(value: object, *, name: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"venue {name} response is not a list")
    return value


def _require_mapping(value: object, *, name: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"venue {name} response is not a mapping")
    return value


def _parse_order_truth(
    value: object,
    *,
    request: VenueTruthRequest,
    expected_symbol: str,
    known_open: bool,
    order_namespace: Literal["regular", "conditional"],
) -> VenueOrderTruth:
    if not isinstance(value, Mapping):
        raise TypeError("venue order truth response is not a mapping")
    info = value.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    raw_symbol = str(value.get("symbol") or "").strip()
    position_side = _position_side_literal(
        str(raw_info.get("positionSide") or "").strip().lower()
    )
    order_side = _order_side_literal(
        str(value.get("side") or "").strip().lower()
    )
    if raw_symbol == expected_symbol:
        exchange_instrument_id = request.exchange_instrument_id
    else:
        try:
            exchange_instrument_id = to_exchange_instrument_id(
                parse_binance_usdm_ccxt_symbol(raw_symbol)
            )
        except ValueError as exc:
            raise RuntimeError(
                "canonical Binance USD-M instrument is unavailable"
            ) from exc
    return VenueOrderTruth(
        exchange_order_id=str(value.get("id") or ""),
        venue_client_order_id=str(value.get("clientOrderId") or ""),
        exchange_instrument_id=exchange_instrument_id,
        position_side=position_side,
        order_side=order_side,
        quantity=Decimal(str(value.get("amount") or "0")),
        reduce_only=bool(value.get("reduceOnly", False)),
        order_namespace=order_namespace,
        is_open=known_open or _unified_order_is_open(value),
    )


def _unified_order_is_open(value: Mapping[object, object]) -> bool:
    status = str(value.get("status") or "").strip().lower()
    if status == "open":
        return True
    if status in {"closed", "canceled", "cancelled", "rejected", "expired"}:
        return False
    raise RuntimeError("venue order truth lacks a recognized unified status")


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


def _build_account_risk_snapshot(
    *,
    account: Mapping[object, object],
    target_rows: tuple[object, ...],
    venue_id: str,
    account_id: str,
    exchange_instrument_id: str,
    symbol: str,
    settlement_asset: str | None,
    position_mode: Literal["independent_sides", "one_way"],
    observed_at_ms: int,
    valid_for_ms: int,
) -> AccountRiskSnapshot:
    if venue_id != "binance-usdm":
        raise RuntimeError("account risk is supported only for Binance USD-M")
    if account.get("multiAssetsMargin") is not False:
        raise RuntimeError("account risk requires standard USD-M single-asset mode")
    if settlement_asset != "USDT":
        raise RuntimeError("account risk requires USDT settlement")
    if position_mode != "independent_sides":
        raise RuntimeError("account risk requires independent position sides")

    raw_positions = _require_list(
        account.get("positions"),
        name="USD-M account positions",
    )
    account_positions = tuple(
        position
        for position in (
            _account_risk_position(
                row,
                venue_id=venue_id,
            )
            for row in raw_positions
        )
        if position is not None
    )
    target_account_positions = {
        position.position_side: position
        for position in account_positions
        if position.exchange_instrument_id == exchange_instrument_id
    }
    if len(target_account_positions) != sum(
        position.exchange_instrument_id == exchange_instrument_id
        for position in account_positions
    ):
        raise RuntimeError("account risk target position sides are contradictory")

    target_position_facts = tuple(
        _target_position_fact(row)
        for row in target_rows
    )
    if {position_side for position_side, _, _ in target_position_facts} != {
        "long",
        "short",
    }:
        raise RuntimeError("account risk target position sides are incomplete")
    for position_side, quantity, average_entry_price in target_position_facts:
        account_position = target_account_positions.get(
            position_side
        )
        if quantity == 0:
            if account_position is not None:
                raise RuntimeError(
                    "account and position risk target quantities contradict"
                )
            continue
        if (
            account_position is None
            or account_position.quantity != quantity
            or account_position.average_entry_price
            != average_entry_price
        ):
            raise RuntimeError(
                "account and position risk target facts contradict"
            )

    mark_price, configured_leverage = _admission_mark_and_leverage(target_rows)
    margin_mode = _admission_margin_mode(list(target_rows))
    if margin_mode != "cross":
        raise RuntimeError("account risk requires Cross margin")
    if _binance_market_id(symbol) != exchange_instrument_id.split(":")[1]:
        raise RuntimeError("account risk target identity is contradictory")
    return AccountRiskSnapshot.create(
        venue_id=venue_id,
        account_id=account_id,
        account_risk_mode="standard_usdm_single_asset",
        settlement_asset="USDT",
        position_mode="independent_sides",
        margin_mode="cross",
        exchange_instrument_id=exchange_instrument_id,
        mark_price=mark_price,
        configured_leverage=configured_leverage,
        total_wallet_balance=_account_risk_decimal(
            account,
            key="totalWalletBalance",
        ),
        total_margin_balance=_account_risk_decimal(
            account,
            key="totalMarginBalance",
            signed=True,
        ),
        total_initial_margin=_account_risk_decimal(
            account,
            key="totalInitialMargin",
        ),
        total_maintenance_margin=_account_risk_decimal(
            account,
            key="totalMaintMargin",
        ),
        available_margin=_account_risk_decimal(
            account,
            key="availableBalance",
        ),
        account_positions=account_positions,
        observed_at_ms=observed_at_ms,
        valid_until_ms=observed_at_ms + valid_for_ms,
    )


def _account_risk_position(
    value: object,
    *,
    venue_id: str,
) -> AccountRiskPosition | None:
    row = _require_mapping(value, name="USD-M account position row")
    market_id = str(row.get("symbol") or "").strip()
    if not market_id:
        raise RuntimeError("USD-M account position lacks symbol")
    position_side = str(row.get("positionSide") or "").strip().upper()
    if position_side not in {"LONG", "SHORT"}:
        raise RuntimeError("USD-M account position side is invalid")
    quantity = _finite_decimal(
        row.get("positionAmt"),
        label="USD-M account position quantity",
    ).copy_abs()
    if quantity == 0:
        return None
    entry_price = _finite_decimal(
        row.get("entryPrice"),
        label="USD-M account position entry",
    )
    if entry_price <= 0:
        raise RuntimeError("open USD-M account position lacks entry price")
    exchange_instrument_id = _instrument_id_from_binance_market_id(
        venue_id=venue_id,
        market_id=market_id,
    )
    return AccountRiskPosition(
        exchange_instrument_id=exchange_instrument_id,
        position_side=cast(
            Literal["long", "short"],
            position_side.lower(),
        ),
        quantity=quantity,
        average_entry_price=entry_price,
        current_unrealized_pnl=_finite_decimal(
            row.get("unrealizedProfit"),
            label="USD-M account position unrealized PnL",
        ),
        current_maintenance_margin=_finite_nonnegative_decimal(
            row.get("maintMargin"),
            label="USD-M account position maintenance margin",
        ),
    )


def _account_risk_decimal(
    account: Mapping[object, object],
    *,
    key: str,
    signed: bool = False,
) -> Decimal:
    value = _finite_decimal(
        account.get(key),
        label=f"USD-M account {key}",
    )
    if not signed and value < 0:
        raise RuntimeError(f"USD-M account {key} must be nonnegative")
    return value


def _finite_nonnegative_decimal(value: object, *, label: str) -> Decimal:
    parsed = _finite_decimal(value, label=label)
    if parsed < 0:
        raise RuntimeError(f"{label} must be nonnegative")
    return parsed


def _finite_decimal(value: object, *, label: str) -> Decimal:
    if value is None or str(value).strip() == "":
        raise RuntimeError(f"{label} is unavailable")
    try:
        parsed = Decimal(str(value))
    except ArithmeticError as exc:
        raise RuntimeError(f"{label} is invalid") from exc
    if not parsed.is_finite():
        raise RuntimeError(f"{label} is invalid")
    return parsed


def _instrument_id_from_binance_market_id(
    *,
    venue_id: str,
    market_id: str,
) -> str:
    candidate = f"{venue_id}:{market_id}:perpetual"
    try:
        parse_binance_usdm_instrument_id(candidate)
    except ValueError as exc:
        raise RuntimeError(
            "canonical Binance USD-M instrument is unavailable for account position"
        ) from exc
    return candidate


def _admission_margin_mode(rows: list[object]) -> Literal["cross", "isolated"]:
    modes: set[Literal["cross", "isolated"]] = set()
    for row in rows:
        mapping = _require_mapping(row, name="admission position row")
        raw = _mapping_value(mapping.get("info"), "marginType")
        if raw is None:
            raw = mapping.get("marginMode")
        normalized = str(raw or "").strip().lower()
        if normalized not in {"cross", "isolated"}:
            raise RuntimeError("venue admission position lacks valid margin mode")
        modes.add(cast(Literal["cross", "isolated"], normalized))
    if len(modes) != 1:
        raise RuntimeError("venue admission margin mode is absent or contradictory")
    return next(iter(modes))


def _admission_mark_and_leverage(
    rows: tuple[object, ...],
) -> tuple[Decimal, int]:
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
    return mark_price, configured_leverage


async def _read_binance_usdm_admission_target_positions(
    *,
    exchange: _CcxtExchange,
    symbol: str,
    require_mark_price: bool = False,
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
    exact_rows: list[Mapping[str, object]] = []
    position_sides: set[str] = set()
    for row in rows:
        raw = cast(
            Mapping[str, object],
            _require_mapping(
                row,
                name="admission requested-instrument position risk row",
            ),
        )
        if str(raw.get("symbol") or "").strip() != market_id:
            continue
        position_side = str(raw.get("positionSide") or "").strip().upper()
        if position_side not in {"LONG", "SHORT"}:
            raise RuntimeError(
                "venue admission requested-instrument position side is invalid"
            )
        position_sides.add(position_side)
        exact_rows.append(raw)
    if len(exact_rows) != 2 or position_sides != {"LONG", "SHORT"}:
        raise RuntimeError(
            "venue admission snapshot lacks requested instrument position sides"
        )
    flat_mark_price = (
        await _read_flat_position_risk_mark_price(
            exchange=exchange,
            market_id=market_id,
            rows=tuple(exact_rows),
        )
        if require_mark_price
        else None
    )
    normalized_rows: list[object] = []
    for exact_row in exact_rows:
        info = dict(exact_row)
        if flat_mark_price is not None:
            info["markPrice"] = str(flat_mark_price)
        normalized_rows.append(
            {
                "symbol": symbol,
                "contracts": exact_row.get("positionAmt"),
                "entryPrice": exact_row.get("entryPrice"),
                "info": info,
            }
        )
    return normalized_rows


async def _read_flat_position_risk_mark_price(
    *,
    exchange: _CcxtExchange,
    market_id: str,
    rows: tuple[Mapping[str, object], ...],
) -> Decimal | None:
    position_amounts = tuple(
        Decimal(str(row.get("positionAmt") or "0")) for row in rows
    )
    mark_prices = tuple(Decimal(str(row.get("markPrice") or "0")) for row in rows)
    if any(amount != 0 for amount in position_amounts) or any(
        mark_price != 0 for mark_price in mark_prices
    ):
        return None
    premium_index = getattr(exchange, "fapiPublicGetPremiumIndex", None)
    if not callable(premium_index):
        raise TypeError("Binance venue lacks USD-M premium-index readonly lookup")
    result = _require_mapping(
        await _call_raw_exchange(premium_index, {"symbol": market_id}),
        name="admission premium-index mark",
    )
    if str(result.get("symbol") or "").strip() != market_id:
        raise RuntimeError("venue admission premium-index symbol differs from request")
    return Decimal(str(result.get("markPrice") or "0"))


def _venue_row_symbol(value: object, *, row_kind: str) -> str:
    mapping = _require_mapping(value, name=f"admission {row_kind} row")
    symbol = str(mapping.get("symbol") or "").strip()
    if not symbol:
        raise RuntimeError(f"venue admission {row_kind} lacks symbol")
    return symbol


def _target_position_fact(
    value: object,
) -> tuple[Literal["long", "short"], Decimal, Decimal | None]:
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
    return _row_position_side(mapping), quantity, average_entry_price


def _admission_order(
    value: object,
    *,
    exchange_instrument_id: str,
    order_namespace: Literal["regular", "conditional"],
) -> AdmissionOrder:
    mapping = _require_mapping(value, name="admission open-order row")
    order_side = str(mapping.get("side") or "").strip().lower()
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
        order_namespace=order_namespace,
        order_side=cast(
            Literal["buy", "sell"] | None,
            order_side if order_side in {"buy", "sell"} else None,
        ),
        quantity=_admission_order_decimal(
            mapping,
            "amount",
            "contracts",
            "origQty",
        ),
        trigger_price=_admission_order_decimal(
            mapping,
            "triggerPrice",
            "stopPrice",
        ),
        limit_price=_admission_order_decimal(mapping, "price"),
    )


def _admission_order_decimal(
    mapping: Mapping[object, object],
    *keys: str,
) -> Decimal | None:
    sources = (mapping, _require_mapping(mapping.get("info") or {}, name="info"))
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value is None or str(value).strip() == "":
                continue
            parsed = Decimal(str(value))
            if parsed == 0:
                continue
            if not parsed.is_finite() or parsed <= 0:
                raise RuntimeError("venue admission order numeric fact is invalid")
            return parsed
    return None


def _position_quantity(
    rows: list[object],
    *,
    expected_symbol: str,
    position_side: Literal["long", "short"],
) -> Decimal:
    total = Decimal(0)
    for value in rows:
        if not isinstance(value, Mapping):
            raise TypeError("venue position row is not a mapping")
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
    rows = await _read_binance_usdm_admission_target_positions(
        exchange=exchange,
        symbol=symbol,
    )
    return _configured_leverage_and_position_quantities(rows, expected_symbol=symbol)


def _configured_leverage_and_position_quantities(
    rows: list[object],
    *,
    expected_symbol: str,
) -> tuple[int, Decimal, Decimal]:
    leverage_values: set[int] = set()
    long_quantity = Decimal(0)
    short_quantity = Decimal(0)
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
) -> tuple[
    Decimal,
    Decimal | None,
    Decimal | None,
    Literal["valid", "missing", "invalid"],
]:
    total_quantity = Decimal(0)
    weighted_entry = Decimal(0)
    liquidation_prices: set[Decimal] = set()
    liquidation_evidence_missing = False
    liquidation_evidence_invalid = False
    for value in rows:
        if not isinstance(value, Mapping):
            raise TypeError("venue position row is not a mapping")
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
        if raw_liquidation in (None, ""):
            liquidation_evidence_missing = True
            continue
        try:
            liquidation = Decimal(str(raw_liquidation))
        except ArithmeticError:
            liquidation_evidence_invalid = True
            continue
        if not liquidation.is_finite() or liquidation < 0:
            liquidation_evidence_invalid = True
            continue
        liquidation_prices.add(liquidation)
    if total_quantity == 0:
        return Decimal(0), None, None, "missing"
    if liquidation_evidence_invalid or len(liquidation_prices) > 1:
        return total_quantity, weighted_entry / total_quantity, None, "invalid"
    liquidation_price = (
        next(iter(liquidation_prices))
        if not liquidation_evidence_missing and len(liquidation_prices) == 1
        else None
    )
    return (
        total_quantity,
        weighted_entry / total_quantity,
        liquidation_price,
        "valid" if liquidation_price is not None else "missing",
    )


def _position_open_orders(
    rows: Sequence[object],
    *,
    expected_symbol: str,
    position_side: Literal["long", "short"],
    order_namespace: Literal["regular", "conditional"],
) -> tuple[VenueOrderSnapshot, ...]:
    orders: list[VenueOrderSnapshot] = []
    for value in rows:
        if not isinstance(value, Mapping):
            raise TypeError("venue open-order row is not a mapping")
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
                order_namespace=order_namespace,
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
            raise TypeError("venue open-order row is not a mapping")
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


def _bnb_futures_wallet_balance(value: object) -> Decimal:
    balance = _require_mapping(value, name="BNB futures balance")
    total = balance.get("total")
    total_mapping = total if isinstance(total, Mapping) else {}
    raw_balance = total_mapping.get("BNB")
    if raw_balance is None:
        info = balance.get("info")
        info_mapping = info if isinstance(info, Mapping) else {}
        assets = info_mapping.get("assets")
        if isinstance(assets, Sequence) and not isinstance(
            assets, (str, bytes, bytearray)
        ):
            for asset in assets:
                asset_mapping = asset if isinstance(asset, Mapping) else {}
                if str(asset_mapping.get("asset") or "").strip().upper() == "BNB":
                    raw_balance = asset_mapping.get("walletBalance")
                    break
    result = Decimal(str(raw_balance if raw_balance is not None else "0"))
    if not result.is_finite() or result < 0:
        raise RuntimeError("BNB futures wallet balance is invalid")
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


def _raw_instrument_rules(
    market: Mapping[str, object],
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    """Preserve deterministic missing/invalid rules as readonly raw facts."""

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
    return (
        _optional_positive_rule_value(lot.get("stepSize")),
        _optional_positive_rule_value(price_filter.get("tickSize")),
        _optional_positive_rule_value(lot.get("minQty")),
        _optional_positive_rule_value(
            notional_filter.get("notional")
            or notional_filter.get("minNotional"),
        ),
    )


def _certification_product_status(market: Mapping[str, object]) -> str:
    active = market.get("active")
    info = market.get("info")
    venue_status = (
        str(info.get("status") or "").strip().upper()
        if isinstance(info, Mapping)
        else ""
    )
    if active is True and venue_status == "TRADING":
        return "trading"
    return "not_trading"


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
            raise TypeError("venue maintenance-margin bracket is not a mapping")
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
    for previous, current in itertools.pairwise(ordered):
        if previous.notional_cap != current.notional_floor:
            raise RuntimeError("venue maintenance-margin brackets are discontinuous")
    return ordered, max(max_leverages)


def _binance_notional_coefficient(
    rows: list[object],
    *,
    market_id: str,
) -> tuple[Decimal, bool]:
    matching = tuple(
        row
        for row in rows
        if isinstance(row, Mapping) and str(row.get("symbol") or "") == market_id
    )
    if len(matching) != 1:
        raise RuntimeError("venue notional coefficient lacks exact instrument truth")
    raw = matching[0].get("notionalCoef")
    coefficient = (
        Decimal(1)
        if raw is None or str(raw).strip() == ""
        else _finite_decimal(raw, label="venue notional coefficient")
    )
    if coefficient <= 0:
        raise RuntimeError("venue notional coefficient must be positive")
    return coefficient, coefficient == 1


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


def _optional_positive_rule_value(
    value: object,
) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        parsed = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return parsed


async def _empty_rows() -> list[object]:
    return []


async def _empty_value() -> None:
    return None


def _order_fill_metrics(value: object | None) -> tuple[Decimal, Decimal | None]:
    if value is None:
        return Decimal(0), None
    mapping = _require_mapping(value, name="TP1 order")
    info = mapping.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    quantity = abs(
        Decimal(
            str(mapping.get("filled") or raw_info.get("executedQty") or "0")
        )
    )
    if quantity == 0:
        return Decimal(0), None
    average_price = Decimal(
        str(mapping.get("average") or raw_info.get("avgPrice") or "0")
    )
    if average_price <= 0:
        raise RuntimeError("TP1 filled order lacks positive average price")
    return quantity, average_price


def _review_fee_asset(
    value: object,
    *,
    settlement_asset: str,
) -> Literal["USDT", "BNB"]:
    if not isinstance(value, Mapping):
        raise TypeError("venue review fill row is not a mapping")
    info = value.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    del settlement_asset
    return _raw_review_native_fee(raw_info).asset


def _exact_order_fill_notional(
    value: object,
    *,
    resolved: ResolvedOrderIdentity,
    position_side: Literal["long", "short"],
    entry_time_ms: int,
    exit_time_ms: int,
) -> Decimal | None:
    if not isinstance(value, Mapping):
        raise TypeError("venue review fill row is not a mapping")
    info = value.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    exchange_order_id = str(
        value.get("order")
        or value.get("orderId")
        or raw_info.get("orderId")
        or ""
    ).strip()
    if exchange_order_id != resolved.actual_order_id:
        return None
    raw_position_side = str(
        value.get("positionSide")
        or raw_info.get("positionSide")
        or ""
    ).strip().lower()
    if _position_side_literal(raw_position_side) != position_side:
        raise RuntimeError("review fill position side differs from Ticket")
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
    return quantity * price


async def _review_fill(
    value: object,
    *,
    resolved: ResolvedOrderIdentity,
    fee_valuation_context: _ReviewFeeValuationContext,
    settlement_asset: str,
    position_side: Literal["long", "short"],
    entry_time_ms: int,
    exit_time_ms: int,
) -> ReviewFill:
    if not isinstance(value, Mapping):
        raise TypeError("venue review fill row is not a mapping")
    info = value.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    exchange_order_id = _review_row_order_id(value)
    if exchange_order_id != resolved.actual_order_id:
        raise RuntimeError("review fill order id differs from requested actual order")
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
    native_fee = _raw_review_native_fee(raw_info)
    if native_fee.asset == "USDT" and settlement_asset.upper() != "USDT":
        raise RuntimeError("non-USDT settlement asset has no review fee valuation")
    valuation = await fee_valuation_context.valuation_for(native_fee)
    valued_fee = value_native_fee(
        native_fee=native_fee,
        valuation_evidence=valuation,
    )
    realized_pnl_quote = Decimal(
        str(value.get("realizedPnl") or raw_info.get("realizedPnl") or "0")
    )
    return ReviewFill(
        exchange_trade_id=trade_id,
        exchange_order_id=exchange_order_id,
        command_id=resolved.reference.command_id,
        role=resolved.reference.role,
        quantity=quantity,
        price=price,
        fee=valued_fee,
        realized_pnl_quote=realized_pnl_quote,
        occurred_at_ms=occurred_at_ms,
    )


def _review_row_order_id(value: object) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("venue review fill row is not a mapping")
    info = value.get("info")
    raw_info = info if isinstance(info, Mapping) else {}
    return str(
        value.get("order")
        or value.get("orderId")
        or raw_info.get("orderId")
        or ""
    ).strip()


def _raw_review_native_fee(raw_info: Mapping[object, object]) -> NativeFee:
    raw_asset = str(raw_info.get("commissionAsset") or "").strip().upper()
    if raw_asset not in {"USDT", "BNB"}:
        raise RuntimeError("review fill commissionAsset is unavailable or unsupported")
    raw_amount = raw_info.get("commission")
    if raw_amount is None:
        raise RuntimeError("review fill commission is unavailable")
    try:
        amount = Decimal(str(raw_amount))
    except Exception as exc:
        raise RuntimeError("review fill commission is invalid") from exc
    if not amount.is_finite() or amount < 0:
        raise RuntimeError("review fill commission must be finite and non-negative")
    return NativeFee(
        asset=cast(Literal["USDT", "BNB"], raw_asset),
        amount=amount,
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
            raise TypeError("venue funding income row is not a mapping")
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
        sum((amount for amount, _ in funding_by_id.values()), Decimal(0)),
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
    atr = sum(true_ranges, Decimal(0)) / Decimal(atr_period)
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
) -> Literal["independent_sides", "one_way"]:
    hedged = value.get("hedged")
    if not isinstance(hedged, bool):
        raise TypeError("venue position mode response lacks hedged boolean")
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
    exchange_order_id: str | None,
) -> Decimal:
    if exchange_order_id is None:
        return Decimal(0)
    total = Decimal(0)
    for value in rows:
        if not isinstance(value, Mapping):
            raise TypeError("venue fill row is not a mapping")
        info = value.get("info")
        raw_info = info if isinstance(info, Mapping) else {}
        row_order_id = str(
            value.get("order")
            or value.get("orderId")
            or raw_info.get("orderId")
            or ""
        )
        if row_order_id == exchange_order_id:
            total += abs(Decimal(str(value.get("amount") or "0")))
    return total


def _open_client_order_ids(rows: list[object]) -> tuple[str, ...]:
    identities: set[str] = set()
    for value in rows:
        if not isinstance(value, Mapping):
            raise TypeError("venue open-order row is not a mapping")
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
    rows: Sequence[object],
    *,
    exchange_order_id: str,
) -> object | None:
    for value in rows:
        if not isinstance(value, Mapping):
            raise TypeError("venue open-order row is not a mapping")
        if str(value.get("id") or "").strip() == exchange_order_id:
            return value
    return None


def _safe_response_payload(response: Mapping[object, object]) -> dict[str, JsonValue]:
    return {
        key: value
        for key in ("status", "clientOrderId")
        if isinstance((value := response.get(key)), (str, int, float, bool))
    }
