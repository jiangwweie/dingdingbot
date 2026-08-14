from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.ports import (
    VenueCommandRequest,
    VenueSetLeverageRequest,
)
from src.trading_kernel.application.runtime_facts import (
    AccountRiskSnapshotRequest,
    EntryAdmissionSnapshotRequest,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
)
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskSnapshot,
    MaintenanceMarginBracket,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork


class AcceptingVenue:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self.saw_committed_claim = False

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        async with PostgresKernelUnitOfWork(self._engine) as uow:
            command = await uow.exchange_commands.get(request.command_id)
        self.saw_committed_claim = (
            command is not None and command.status is ExchangeCommandStatus.CLAIMED
        )
        exchange_order_id = (
            request.payload.exchange_order_id
            if isinstance(request.payload, CancelCommandPayload)
            else f"venue-{request.kind.value}-1"
        )
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id=exchange_order_id,
        )

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        return _accepted_leverage(request)


class SlowVenue:
    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        del request
        await asyncio.sleep(0.1)
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id="late-order",
        )

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        await asyncio.sleep(0.1)
        return _accepted_leverage(request)


class CountingVenue:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        del request
        self.calls += 1
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id="unexpected-order",
        )

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        raise AssertionError(
            f"unexpected set leverage for {request.exchange_instrument_id}"
        )


class KindAwareAcceptingVenue:
    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        exchange_order_id = (
            request.payload.exchange_order_id
            if isinstance(request.payload, CancelCommandPayload)
            else f"venue-{request.kind.value}-1"
        )
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id=exchange_order_id,
        )

    async def set_leverage(
        self, request: VenueSetLeverageRequest
    ) -> SetLeverageCommandResult:
        return _accepted_leverage(request)


class PreflightFacts:
    def __init__(self, *, configured_leverage: int = 5) -> None:
        self._configured_leverage = configured_leverage

    async def read_entry_admission_snapshot(
        self, request: EntryAdmissionSnapshotRequest
    ) -> EntryAdmissionSnapshot:
        return EntryAdmissionSnapshot(
            account_risk_snapshot=self._account_risk_snapshot(
                venue_id=request.venue_id,
                account_id=request.account_id,
                exchange_instrument_id=request.exchange_instrument_id,
                observed_at_ms=request.observed_at_ms,
                valid_for_ms=request.valid_for_ms,
            ),
            best_bid_price=Decimal(59999),
            best_ask_price=Decimal(60000),
            open_orders=(),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_account_risk_snapshot(
        self, request: AccountRiskSnapshotRequest
    ) -> AccountRiskSnapshot:
        return self._account_risk_snapshot(
            venue_id=request.venue_id,
            account_id=request.account_id,
            exchange_instrument_id=request.exchange_instrument_id,
            observed_at_ms=request.observed_at_ms,
            valid_for_ms=request.valid_for_ms,
        )

    def _account_risk_snapshot(
        self,
        *,
        venue_id: str,
        account_id: str,
        exchange_instrument_id: str,
        observed_at_ms: int,
        valid_for_ms: int,
    ) -> AccountRiskSnapshot:
        return AccountRiskSnapshot.create(
            venue_id=venue_id,
            account_id=account_id,
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id=exchange_instrument_id,
            mark_price=Decimal(60000),
            configured_leverage=self._configured_leverage,
            total_wallet_balance=Decimal(300),
            total_margin_balance=Decimal(300),
            total_initial_margin=Decimal(10),
            total_maintenance_margin=Decimal(1),
            available_margin=Decimal(290),
            account_positions=(),
            observed_at_ms=observed_at_ms,
            valid_until_ms=observed_at_ms + valid_for_ms,
        )

    async def read_instrument_rules(
        self, request: InstrumentRulesRequest
    ) -> InstrumentRulesFacts:
        brackets = (
            MaintenanceMarginBracket(
                bracket_id="test:1",
                notional_floor=Decimal(0),
                notional_cap=None,
                maintenance_margin_rate=Decimal("0.005"),
                maintenance_amount=Decimal(0),
            ),
        )
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal(5),
            exchange_max_leverage=10,
            maintenance_margin_brackets=brackets,
            maintenance_margin_brackets_digest=canonical_digest(brackets),
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )


def _accepted_leverage(request: VenueSetLeverageRequest) -> SetLeverageCommandResult:
    return SetLeverageCommandResult(
        exchange_configured_leverage=request.payload.desired_leverage,
        leverage_verified_at_ms=2_000,
        leverage_verification_digest="sha256:" + "4" * 64,
    )
