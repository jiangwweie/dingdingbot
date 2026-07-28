#!/usr/bin/env python3
"""Probe the production venue identity, rules, positions, and orders read-only."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Literal, Mapping, Protocol

from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.ports import (  # noqa: E402
    LeverageTruthRequest,
    VenueTruthPort,
)
from src.trading_kernel.application.runtime_facts import (  # noqa: E402
    EntryAdmissionSnapshotRequest,
    EntryFactsSource,
    InstrumentRulesRequest,
)
from src.trading_kernel.infrastructure.production_runtime import (  # noqa: E402
    ProductionRuntimeSettings,
    build_binance_usdm_venue_adapter,
    canonical_binance_usdm_instruments,
)


class ProductionProbeFactsSource(EntryFactsSource, VenueTruthPort, Protocol):
    pass


class InstrumentRuleProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    quantity_step: Decimal
    price_tick: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    exchange_max_leverage: int
    configured_leverage: int
    valid_until_ms: int


class ProtectedHandoverTicketProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    netting_domain_key: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    aggregate_status: Literal["position_protected", "runner_protected"]
    position_quantity: Decimal
    protected_quantity: Decimal
    active_stop_order: dict[str, object]
    active_tp1_order: dict[str, object] | None = None
    recorded_tp1_fill_quantity: Decimal | None = None


class ProductionRuntimeProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: Literal["live"]
    venue_id: Literal["binance-usdm"]
    account_id: str
    account_position_mode: Literal["independent_sides"]
    account_margin_mode: Literal["cross"]
    instrument_rule_count: int
    netting_domain_count: int
    non_flat_domain_count: int
    open_order_domain_count: int
    total_wallet_balance: Decimal
    available_margin: Decimal
    rules: tuple[InstrumentRuleProbe, ...]
    protected_tickets: tuple[ProtectedHandoverTicketProbe, ...] = ()
    observed_at_ms: int


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now-ms", type=int)
    parser.add_argument("--validity-ms", type=int, default=5_000)
    parser.add_argument(
        "--protected-ticket-json",
        action="append",
        default=[],
        help="Exact readonly protected Ticket manifest row from certification.",
    )
    return parser


async def probe_production_runtime(
    adapter: ProductionProbeFactsSource,
    settings: ProductionRuntimeSettings,
    *,
    now_ms: int,
    validity_ms: int,
    expected_protected_tickets: tuple[ProtectedHandoverTicketProbe, ...] = (),
) -> ProductionRuntimeProbe:
    if now_ms <= 0 or validity_ms <= 0:
        raise ValueError("probe time and validity must be positive")

    instruments = canonical_binance_usdm_instruments()
    account_probe_instrument = next(
        instrument for instrument in instruments if ":BTCUSDT:" in instrument
    )
    admission_snapshot = await adapter.read_entry_admission_snapshot(
        EntryAdmissionSnapshotRequest(
            venue_id=settings.venue_id,
            account_id=settings.account_id,
            exchange_instrument_id=account_probe_instrument,
            observed_at_ms=now_ms,
            valid_for_ms=validity_ms,
        )
    )
    if admission_snapshot.position_mode != settings.account_position_mode:
        raise RuntimeError("production account position mode differs from config")
    if admission_snapshot.margin_mode != "cross":
        raise RuntimeError("production account margin mode differs from config")

    rule_rows: list[InstrumentRuleProbe] = []
    for exchange_instrument_id in instruments:
        rules = await adapter.read_instrument_rules(
            InstrumentRulesRequest(
                venue_id=settings.venue_id,
                account_id=settings.account_id,
                exchange_instrument_id=exchange_instrument_id,
                observed_at_ms=now_ms,
                valid_for_ms=validity_ms,
            )
        )
        leverage_truth = await adapter.read_configured_leverage(
            LeverageTruthRequest(
                command_id=f"production-probe:{exchange_instrument_id}",
                venue_id=settings.venue_id,
                account_id=settings.account_id,
                exchange_instrument_id=exchange_instrument_id,
                desired_leverage=5,
                observed_at_ms=now_ms,
            )
        )
        rule_rows.append(
            InstrumentRuleProbe(
                exchange_instrument_id=rules.exchange_instrument_id,
                quantity_step=rules.quantity_step,
                price_tick=rules.price_tick,
                min_quantity=rules.min_quantity,
                min_notional=rules.min_notional,
                exchange_max_leverage=rules.exchange_max_leverage,
                configured_leverage=(
                    leverage_truth.exchange_configured_leverage
                ),
                valid_until_ms=rules.valid_until_ms,
            )
        )

    netting_domain_count = len(instruments) * 2
    non_flat_domain_count = sum(
        position.quantity > 0 for position in admission_snapshot.positions
    )
    open_order_domain_count = len(
        {
            (order.exchange_instrument_id, order.position_side)
            for order in admission_snapshot.open_orders
        }
    )
    protected_tickets = _verify_protected_exchange_tickets(
        expected_protected_tickets,
        positions=admission_snapshot.positions,
        open_orders=admission_snapshot.open_orders,
    )
    return ProductionRuntimeProbe(
        environment=settings.environment,
        venue_id=settings.venue_id,
        account_id=settings.account_id,
        account_position_mode=admission_snapshot.position_mode,
        account_margin_mode=admission_snapshot.margin_mode,
        instrument_rule_count=len(rule_rows),
        netting_domain_count=netting_domain_count,
        non_flat_domain_count=non_flat_domain_count,
        open_order_domain_count=open_order_domain_count,
        total_wallet_balance=admission_snapshot.total_wallet_balance,
        available_margin=admission_snapshot.available_margin,
        rules=tuple(rule_rows),
        protected_tickets=protected_tickets,
        observed_at_ms=now_ms,
    )


def _verify_protected_exchange_tickets(
    expected_tickets: tuple[ProtectedHandoverTicketProbe, ...],
    *,
    positions: tuple[object, ...],
    open_orders: tuple[object, ...],
) -> tuple[ProtectedHandoverTicketProbe, ...]:
    if not expected_tickets:
        return ()
    position_by_domain = {
        (position.exchange_instrument_id, position.position_side): position
        for position in positions
    }
    orders_by_id = {
        order.exchange_order_id: order
        for order in open_orders
    }
    if len({ticket.ticket_id for ticket in expected_tickets}) != len(
        expected_tickets
    ):
        raise RuntimeError("protected Ticket manifest contains duplicate identities")
    for ticket in expected_tickets:
        position = position_by_domain.get(
            (ticket.exchange_instrument_id, ticket.position_side)
        )
        if position is None or position.quantity != ticket.position_quantity:
            raise RuntimeError("exchange protected position differs from manifest")
        if ticket.protected_quantity != ticket.position_quantity:
            raise RuntimeError("protected manifest quantity is inconsistent")
        _require_exact_protected_order(
            ticket.active_stop_order,
            order=orders_by_id.get(str(ticket.active_stop_order.get("exchange_order_id"))),
            expected_instrument_id=ticket.exchange_instrument_id,
            expected_position_side=ticket.position_side,
            expected_quantity=ticket.protected_quantity,
            require_stop_price=True,
        )
        if ticket.aggregate_status == "position_protected":
            if ticket.active_tp1_order is None or ticket.recorded_tp1_fill_quantity is not None:
                raise RuntimeError("protected manifest TP1 state is inconsistent")
            _require_exact_protected_order(
                ticket.active_tp1_order,
                order=orders_by_id.get(
                    str(ticket.active_tp1_order.get("exchange_order_id"))
                ),
                expected_instrument_id=ticket.exchange_instrument_id,
                expected_position_side=ticket.position_side,
                expected_quantity=Decimal(str(ticket.active_tp1_order.get("quantity"))),
                require_stop_price=False,
            )
        elif (
            ticket.active_tp1_order is not None
            or ticket.recorded_tp1_fill_quantity is None
            or ticket.recorded_tp1_fill_quantity <= 0
        ):
            raise RuntimeError("runner manifest TP1 state is inconsistent")
    return expected_tickets


def _require_exact_protected_order(
    expected: Mapping[str, object],
    *,
    order: object | None,
    expected_instrument_id: str,
    expected_position_side: Literal["long", "short"],
    expected_quantity: Decimal,
    require_stop_price: bool,
) -> None:
    if order is None:
        raise RuntimeError("exchange protected order is absent")
    expected_order_side = "sell" if expected_position_side == "long" else "buy"
    if (
        expected.get("order_namespace") != "conditional"
        or expected.get("position_side") != expected_position_side
        or expected.get("order_side") != expected_order_side
        or expected.get("reduce_only") is not True
        or order.exchange_instrument_id != expected_instrument_id
        or order.position_side != expected_position_side
        or order.order_namespace != "conditional"
        or order.order_side != expected_order_side
        or order.reduce_only is not True
        or order.quantity != expected_quantity
    ):
        raise RuntimeError("exchange protected order differs from manifest")
    if require_stop_price:
        expected_stop_price = Decimal(str(expected.get("stop_price")))
        if order.trigger_price != expected_stop_price:
            raise RuntimeError("exchange protected Stop price differs from manifest")


async def _run(args: argparse.Namespace) -> int:
    settings = ProductionRuntimeSettings.from_environment()
    adapter = build_binance_usdm_venue_adapter()
    try:
        expected_protected_tickets = tuple(
            ProtectedHandoverTicketProbe.model_validate_json(row)
            for row in args.protected_ticket_json
        )
        result = await probe_production_runtime(
            adapter,
            settings,
            now_ms=args.now_ms or int(time.time() * 1_000),
            validity_ms=args.validity_ms,
            expected_protected_tickets=expected_protected_tickets,
        )
        print(result.model_dump_json())
        return 0
    finally:
        await adapter.close()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
