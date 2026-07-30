from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import NotRequired, TypedDict

import pytest
from pydantic import JsonValue

from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    reconcile_ticket,
)
from src.trading_kernel.application.runtime_facts import ReviewEconomicsRequest
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.order_attribution import TicketOrderReference
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.full_chain.lifecycle_support import (
    dispatch_lifecycle_command,
    reach_runner_protected,
)
from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
from tests.trading_kernel.integration.test_command_dispatch import (
    KindAwareAcceptingVenue,
)
from tests.trading_kernel.integration.test_ticket_lifecycle_maintenance import (
    _registered_sor_long_ticket,
)
from tests.trading_kernel.integration.universe_certification_support import (
    NoTicketVenueTruth,
)
from tests.trading_kernel.unit.test_venue_adapter import FakeAsyncExchange

dispatch_engine = dispatch_fixture.dispatch_engine


class _FlatPositionSource:
    async def read_position_snapshot(self, request):
        raise AssertionError(f"closure work must not read position: {request.ticket_id}")


class _TradeInfo(TypedDict):
    positionSide: str
    commission: str
    commissionAsset: NotRequired[str]


class _TradeRow(TypedDict):
    id: str
    orderId: str
    amount: str
    price: str
    fee: dict[str, str]
    timestamp: int
    realizedPnl: str
    info: _TradeInfo


class _RunnerTradesExchange(FakeAsyncExchange):
    """Official Binance-shaped review rows: only trade/order identity is usable."""

    def __init__(self, *, fee_mode: str, review_fault: str | None = None) -> None:
        super().__init__()
        self.fee_mode = fee_mode
        self.review_fault = review_fault
        self.references: tuple[TicketOrderReference, ...] = ()
        self.trade_calls: list[dict[str, object]] = []
        self.index_calls: list[dict[str, object]] = []
        self.returned_trade_rows: list[_TradeRow] = []

    def bind(self, request: ReviewEconomicsRequest) -> None:
        self.references = (
            request.entry_order_reference,
            *request.exit_order_references,
        )

    async def fetch_my_trades(
        self,
        symbol: str,
        since: object,
        limit: int,
        params: Mapping[str, object],
    ) -> object:
        del since
        assert symbol == "BTC/USDT:USDT"
        assert limit == 100
        self.trade_calls.append(dict(params))
        order_id = str(params["orderId"])
        references = {item.submitted_exchange_order_id: item for item in self.references}
        if order_id == "venue-entry-1":
            rows = [self._fill("entry-trade", order_id, "0.001", "60000", 2_200)]
            return self._review_rows(rows)
        if order_id == "venue-take_profit-1":
            rows = [self._fill("tp1-trade", order_id, "0.0005", "62000", 2_500)]
            return self._review_rows(rows)
        if order_id == "1085699838084":
            rows = [self._fill("runner-trade", order_id, "0.0005", "63000", 3_000)]
            return self._review_rows(rows)
        assert order_id not in references
        raise AssertionError(f"unexpected Binance orderId lookup: {order_id}")

    async def fapiPrivateGetAlgoOrder(self, params: Mapping[str, object]) -> object:
        assert set(params) == {"algoId"}
        submitted_id = str(params["algoId"])
        reference = next(
            item for item in self.references if item.submitted_exchange_order_id == submitted_id
        )
        expectation = reference.conditional_expectation
        assert expectation is not None
        result = {
            "algoId": submitted_id,
            "clientAlgoId": reference.venue_client_order_id,
            "symbol": expectation.exchange_instrument_id.split(":", 2)[1],
            "side": expectation.side.upper(),
            "positionSide": expectation.position_side.upper(),
            "type": expectation.order_type.upper(),
        }
        if reference.command_kind is ExchangeCommandKind.REPLACE_PROTECTION:
            return {
                **result,
                "actualOrderId": "1085699838084",
                "actualQty": str(expectation.quantity),
                "status": "FINISHED",
            }
        return {
            **result,
            "actualOrderId": "",
            "actualQty": "0",
            "status": "CANCELED",
        }

    async def fapiPrivateGetIncome(self, params: Mapping[str, object]) -> object:
        assert params["symbol"] == "BTCUSDT"
        return []

    async def fapiPublicGetPremiumIndex(self, params: Mapping[str, object]) -> object:
        self.index_calls.append(dict(params))
        return {"symbol": "BNBUSDT", "indexPrice": "600", "time": 4_000}

    def _fill(
        self,
        trade_id: str,
        order_id: str,
        quantity: str,
        price: str,
        timestamp: int,
    ) -> _TradeRow:
        fee_asset = "USDT"
        fee_amount = "0.010"
        if self.fee_mode == "bnb" or self.fee_mode == "mixed" and trade_id != "entry-trade":
            fee_asset, fee_amount = "BNB", "0.000010"
        return {
            "id": trade_id,
            "orderId": order_id,
            "amount": quantity,
            "price": price,
            "fee": {"cost": fee_amount, "currency": fee_asset},
            "timestamp": timestamp,
            "realizedPnl": "0",
            "info": {
                "positionSide": "LONG",
                "commission": fee_amount,
                "commissionAsset": fee_asset,
            },
        }

    def _review_rows(self, rows: list[_TradeRow]) -> list[_TradeRow]:
        if self.review_fault == "missing_commission_asset":
            for row in rows:
                row["info"].pop("commissionAsset")
        elif self.review_fault == "negative_commission":
            for row in rows:
                row["info"]["commission"] = "-0.010"
        elif self.review_fault == "wrong_order_id":
            rows.append(
                self._fill(
                    "wrong-order-trade",
                    "manual-order",
                    "0.0005",
                    "63000",
                    3_000,
                )
            )
        self.returned_trade_rows.extend(rows)
        return rows


class _BoundAdapterReviewSource:
    def __init__(self, adapter: CcxtVenueAdapter, exchange: _RunnerTradesExchange) -> None:
        self.adapter = adapter
        self.exchange = exchange

    async def read_review_economics(self, request: ReviewEconomicsRequest):
        self.exchange.bind(request)
        return await self.adapter.read_review_economics(request)


async def _move_runner_to_review_pending(engine, ticket) -> None:
    await reach_runner_protected(engine, ticket)
    async with PostgresKernelUnitOfWork(engine) as uow:
        flat = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_500,
                ),
            ),
        )
    assert flat.status.value == "external_flat_incident"
    assert (
        await dispatch_lifecycle_command(
            engine,
            KindAwareAcceptingVenue(),
            ticket.identity.ticket_id,
            now_ms=3_550,
        )
    ).status.value == "accepted"
    async with PostgresKernelUnitOfWork(engine) as uow:
        matched = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_600,
                ),
            ),
        )
    assert matched.status.value == "matched"


def _review_adapter(ticket, exchange: _RunnerTradesExchange) -> _BoundAdapterReviewSource:
    adapter = CcxtVenueAdapter(
        exchanges={
            (
                ticket.identity.netting_domain.venue_id,
                ticket.identity.netting_domain.account_id,
            ): exchange
        },
        settlement_assets={
            (
                ticket.identity.netting_domain.venue_id,
                ticket.identity.netting_domain.exchange_instrument_id,
            ): "USDT"
        },
        clock_ms=lambda: 4_000,
    )
    return _BoundAdapterReviewSource(adapter, exchange)


def _review_worker_request(*, now_ms: int) -> ReconciliationWorkerRequest:
    return ReconciliationWorkerRequest(
        worker_id="reconciliation-full-chain",
        runtime_commit="kernel-test-head",
        schema_revision="0001_trading_kernel_baseline_v3",
        now_ms=now_ms,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=2_000,
    )




@pytest.mark.asyncio
@pytest.mark.parametrize("fee_mode", ["usdt", "bnb", "mixed"])
async def test_btc_like_runner_closure_uses_actual_order_id_and_records_complete_review(
    dispatch_engine,
    fee_mode: str,
) -> None:
    ticket = _registered_sor_long_ticket()
    await _move_runner_to_review_pending(dispatch_engine, ticket)
    exchange = _RunnerTradesExchange(fee_mode=fee_mode)
    source = _review_adapter(ticket, exchange)
    request = _review_worker_request(now_ms=40_000)

    settled = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        NoTicketVenueTruth(),
        _FlatPositionSource(),
        request,
        review_economics_source=source,
    )
    assert settled.status is ReconciliationWorkerStatus.SETTLED
    reviewed = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        NoTicketVenueTruth(),
        _FlatPositionSource(),
        request.model_copy(update={"now_ms": 70_000}),
        review_economics_source=source,
    )
    assert reviewed.status is ReconciliationWorkerStatus.REVIEWED

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        review = await uow.reviews.get_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.status is AggregateStatus.TERMINAL
    assert [type(event).__name__ for event in events].count("BudgetSettled") == 1
    assert [type(event).__name__ for event in events].count("ReviewRecorded") == 1
    assert review is not None
    assert review.metrics["economics_completeness"] == "complete"
    assert review.metrics["entry_quantity"] == "0.001"
    assert review.metrics["exit_quantity"] == "0.0010"
    fees = Decimal(str(review.metrics["trading_fees_quote"]))
    assert fees == (
        Decimal("0.030") if fee_mode == "usdt" else Decimal("0.018000")
        if fee_mode == "bnb" else Decimal("0.022000")
    )
    gross = Decimal(str(review.metrics["gross_realized_pnl_quote"]))
    funding = Decimal(str(review.metrics["funding_quote"]))
    net = Decimal(str(review.metrics["net_pnl_quote"]))
    assert gross == Decimal("2.5000")
    assert net == gross - fees + funding
    assert Decimal(str(review.metrics["planned_r_multiple"])) == (
        net / ticket.risk_at_stop
    )
    attribution_rows = _attribution_rows(review.metrics)
    assert {row["exchange_order_id"] for row in attribution_rows} == {
        "venue-entry-1",
        "venue-take_profit-1",
        "1085699838084",
    }
    assert exchange.trade_calls == [
        {"orderId": "venue-entry-1"},
        {"orderId": "venue-take_profit-1"},
        {"orderId": "1085699838084"},
    ]
    assert all("clientOrderId" not in row for row in exchange.returned_trade_rows)
    assert str(review.metrics["order_attribution_digest"]).startswith("sha256:")
    native_assets = {_native_fee_asset(row) for row in attribution_rows}
    assert native_assets == (
        {"USDT"} if fee_mode == "usdt" else {"BNB"}
        if fee_mode == "bnb" else {"USDT", "BNB"}
    )
    assert all(
        _fee_evidence_method(row) == "native_usdt"
        if _native_fee_asset(row) == "USDT"
        else _fee_evidence_method(row)
        == "binance_usdm_bnbusdt_review_index_snapshot"
        for row in attribution_rows
    )
    assert exchange.index_calls == ([] if fee_mode == "usdt" else [{"symbol": "BNBUSDT"}])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "review_fault",
    [
        "wrong_order_id",
        "missing_commission_asset",
        "negative_commission",
    ],
)
async def test_review_attribution_contradiction_keeps_ticket_pending(
    dispatch_engine,
    review_fault: str,
) -> None:
    ticket = _registered_sor_long_ticket()
    await _move_runner_to_review_pending(dispatch_engine, ticket)
    source = _review_adapter(
        ticket,
        _RunnerTradesExchange(fee_mode="usdt", review_fault=review_fault),
    )

    settled = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        NoTicketVenueTruth(),
        _FlatPositionSource(),
        _review_worker_request(now_ms=40_000),
        review_economics_source=source,
    )
    assert settled.status is ReconciliationWorkerStatus.SETTLED
    unavailable = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        NoTicketVenueTruth(),
        _FlatPositionSource(),
        _review_worker_request(now_ms=70_000),
        review_economics_source=source,
    )
    assert unavailable.status is ReconciliationWorkerStatus.FACTS_UNAVAILABLE
    assert unavailable.ticket_id == ticket.identity.ticket_id

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        review = await uow.reviews.get_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.status is AggregateStatus.REVIEW_PENDING
    assert [type(event).__name__ for event in events].count("ReviewRecorded") == 0
    assert review is None


def _attribution_rows(
    metrics: Mapping[str, JsonValue],
) -> tuple[Mapping[str, JsonValue], ...]:
    raw_rows = metrics["order_attribution"]
    assert isinstance(raw_rows, list)
    rows: list[Mapping[str, JsonValue]] = []
    for raw_row in raw_rows:
        assert isinstance(raw_row, dict)
        rows.append(raw_row)
    return tuple(rows)


def _native_fee_asset(row: Mapping[str, JsonValue]) -> str:
    fee = _fee_mapping(row)
    native = fee["native"]
    assert isinstance(native, dict)
    asset = native["asset"]
    assert isinstance(asset, str)
    return asset


def _fee_evidence_method(row: Mapping[str, JsonValue]) -> str:
    fee = _fee_mapping(row)
    evidence = fee["evidence"]
    assert isinstance(evidence, dict)
    method = evidence["method"]
    assert isinstance(method, str)
    return method


def _fee_mapping(row: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    fee = row["fee"]
    assert isinstance(fee, dict)
    return fee
