"""Reusable certified readonly and venue boundaries for full-chain tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.application.ports import (
    LeverageTruthRequest,
    LeverageTruthSnapshot,
    VenueCommandRequest,
    VenueSetLeverageRequest,
)
from src.trading_kernel.application.runtime_facts import (
    AccountRiskSnapshotRequest,
    EntryAdmissionSnapshotRequest,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
    LifecycleFactsRequest,
    PositionSnapshotRequest,
)
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskPosition,
    AccountRiskSnapshot,
    MaintenanceMarginBracket,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.position import PositionSnapshot
from tests.trading_kernel.unit.detectors.fixtures import NOW_MS


def _maintenance_brackets() -> tuple[MaintenanceMarginBracket, ...]:
    return (
        MaintenanceMarginBracket(
            bracket_id="test:1",
            notional_floor=Decimal(0),
            notional_cap=None,
            maintenance_margin_rate=Decimal("0.005"),
            maintenance_amount=Decimal(0),
        ),
    )


class CertifiedEntryAdmissionFactsSource:
    def __init__(
        self,
        *,
        reference_price: Decimal,
        position_side: Literal["long", "short"],
    ) -> None:
        offset = max(reference_price * Decimal("0.0001"), Decimal("0.01"))
        spread = offset / Decimal(2)
        if position_side == "long":
            self.best_ask = reference_price + offset
            self.best_bid = self.best_ask - spread
        else:
            self.best_bid = reference_price - offset
            self.best_ask = self.best_bid + spread

    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot:
        return EntryAdmissionSnapshot(
            account_risk_snapshot=AccountRiskSnapshot.create(
                venue_id=request.venue_id,
                account_id=request.account_id,
                account_risk_mode="standard_usdm_single_asset",
                settlement_asset="USDT",
                position_mode="independent_sides",
                margin_mode="cross",
                exchange_instrument_id=request.exchange_instrument_id,
                mark_price=(self.best_bid + self.best_ask) / Decimal(2),
                configured_leverage=5,
                total_wallet_balance=Decimal(1000000),
                total_margin_balance=Decimal(1000000),
                total_initial_margin=Decimal(0),
                total_maintenance_margin=Decimal(0),
                available_margin=Decimal(1000000),
                account_positions=(),
                observed_at_ms=request.observed_at_ms,
                valid_until_ms=request.observed_at_ms + request.valid_for_ms,
            ),
            best_bid_price=self.best_bid,
            best_ask_price=self.best_ask,
            open_orders=(),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts:
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal(5),
            exchange_max_leverage=10,
            maintenance_margin_brackets=_maintenance_brackets(),
            maintenance_margin_brackets_digest=canonical_digest(
                _maintenance_brackets()
            ),
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_account_risk_snapshot(
        self,
        request: AccountRiskSnapshotRequest,
    ) -> AccountRiskSnapshot:
        return AccountRiskSnapshot.create(
            venue_id=request.venue_id,
            account_id=request.account_id,
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id=request.exchange_instrument_id,
            mark_price=(self.best_bid + self.best_ask) / Decimal(2),
            configured_leverage=5,
            total_wallet_balance=Decimal(1000000),
            total_margin_balance=Decimal(1000000),
            total_initial_margin=Decimal(0),
            total_maintenance_margin=Decimal(0),
            available_margin=Decimal(1000000),
            account_positions=(),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


class CertifiedVenue:
    def __init__(self) -> None:
        self.calls: list[VenueCommandRequest] = []
        self.last_observed_at_ms = NOW_MS

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.calls.append(request)
        self.last_observed_at_ms = max(
            self.last_observed_at_ms + 1,
            request.deadline_at_ms - 29_999,
        )
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=self.last_observed_at_ms,
            exchange_order_id=(
                request.payload.exchange_order_id
                if isinstance(request.payload, CancelCommandPayload)
                else f"venue-{request.kind.value}-{len(self.calls)}"
            ),
        )

    async def lookup_command_truth(self, request):
        raise AssertionError(f"unexpected unknown command lookup: {request.command_id}")

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        self.last_observed_at_ms += 1
        return SetLeverageCommandResult(
            exchange_configured_leverage=request.payload.desired_leverage,
            leverage_verified_at_ms=self.last_observed_at_ms,
            leverage_verification_digest="sha256:" + "4" * 64,
        )

    async def read_configured_leverage(
        self, request: LeverageTruthRequest
    ) -> LeverageTruthSnapshot:
        self.last_observed_at_ms += 1
        return LeverageTruthSnapshot(
            exchange_configured_leverage=request.desired_leverage,
            long_position_quantity=Decimal(0),
            short_position_quantity=Decimal(0),
            regular_open_order_ids=(),
            conditional_open_order_ids=(),
            observed_at_ms=self.last_observed_at_ms,
        )


class CertifiedPositionSource:
    def __init__(self) -> None:
        self.quantity = Decimal(0)
        self.average_entry_price: Decimal | None = None
        self.liquidation_price: Decimal | None = None

    def set_open(
        self,
        *,
        quantity: Decimal,
        average_entry_price: Decimal,
        position_side: str,
    ) -> None:
        self.quantity = quantity
        self.average_entry_price = average_entry_price
        self.liquidation_price = average_entry_price * (
            Decimal("0.75") if position_side == "long" else Decimal("1.25")
        )

    def set_flat(self) -> None:
        self.quantity = Decimal(0)
        self.average_entry_price = None
        self.liquidation_price = None

    async def read_position_snapshot(
        self,
        request: PositionSnapshotRequest,
    ) -> PositionSnapshot:
        return PositionSnapshot(
            netting_domain=request.netting_domain,
            quantity=self.quantity,
            average_entry_price=self.average_entry_price,
            venue_reported_liquidation_price=self.liquidation_price,
            open_orders=(),
            observed_at_ms=request.observed_at_ms,
        )


class CertifiedPostFillFactsSource:
    def __init__(self, ticket) -> None:
        self.ticket = ticket

    async def read_account_risk_snapshot(
        self,
        request: AccountRiskSnapshotRequest,
    ) -> AccountRiskSnapshot:
        ticket = self.ticket
        stress_balance = max(Decimal(1000000), ticket.notional * Decimal(10))
        return AccountRiskSnapshot.create(
            venue_id=request.venue_id,
            account_id=request.account_id,
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id=request.exchange_instrument_id,
            mark_price=ticket.entry_reference_price,
            configured_leverage=ticket.selected_leverage,
            total_wallet_balance=stress_balance,
            total_margin_balance=stress_balance,
            total_initial_margin=ticket.reserved_margin,
            total_maintenance_margin=Decimal(0),
            available_margin=stress_balance - ticket.reserved_margin,
            account_positions=(
                AccountRiskPosition(
                    exchange_instrument_id=request.exchange_instrument_id,
                    position_side=ticket.identity.netting_domain.position_side,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    current_unrealized_pnl=Decimal(0),
                    current_maintenance_margin=Decimal(0),
                ),
            ),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts:
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal(5),
            exchange_max_leverage=10,
            maintenance_margin_brackets=_maintenance_brackets(),
            maintenance_margin_brackets_digest=canonical_digest(
                _maintenance_brackets()
            ),
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


class CertifiedLifecycleFactsSource:
    def __init__(self) -> None:
        self.facts: TicketLifecycleFacts | None = None

    async def read_lifecycle_facts(
        self,
        request: LifecycleFactsRequest,
    ) -> TicketLifecycleFacts:
        if self.facts is None:
            raise AssertionError("lifecycle facts requested before TP1 fill")
        return self.facts.model_copy(update={"observed_at_ms": request.observed_at_ms})
