"""One short PostgreSQL transaction per trading-kernel state reduction."""

from __future__ import annotations

from types import TracebackType
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction

from src.trading_kernel.application.ports import (
    AggregateVersionConflict,
    AggregateRepository,
    BudgetRepository,
    CapacityClaimRepository,
    EntryAdmissionRepository,
    EventRepository,
    ExchangeCommandRepository,
    IncidentRepository,
    MonitorRepository,
    PositionRepository,
    ReviewRepository,
    RuntimeIncidentRecord,
    SignalRepository,
    StrategyRegistryRepository,
    TicketRepository,
    UnsupportedKernelEffect,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
    build_command_id,
    build_venue_client_order_id,
    require_next_generation_allowed,
)
from src.trading_kernel.domain.effects import (
    CancelEntryRemainder,
    CancelProtectionOrders,
    MarkCancelCommandReconciledAbsent,
    OpenIncident,
    PrepareEntryCommand,
    PrepareControlledFlattenCommand,
    PrepareExitCommand,
    PrepareInitialStopCommand,
    PrepareProtectionReplacementCommand,
    PrepareTakeProfitCommand,
    ReleaseBudget,
    ReleaseEntryLane,
    ResolveIncident,
    RequestControlledFlatten,
    SettleBudget,
)
from src.trading_kernel.domain.events import TicketIssued, TradeEvent
from src.trading_kernel.domain.incident_blocking import (
    EntryBlockScope,
    canonical_entry_block_key,
)
from src.trading_kernel.domain.reducer import Reduction
from src.trading_kernel.domain.ticket import EntryOrderType
from src.trading_kernel.infrastructure.pg_repositories import (
    PostgresAggregateRepository,
    PostgresBudgetRepository,
    PostgresCapacityClaimRepository,
    PostgresEventRepository,
    PostgresEntryAdmissionRepository,
    PostgresExchangeCommandRepository,
    PostgresIncidentRepository,
    PostgresMonitorRepository,
    PostgresPositionRepository,
    PostgresReviewRepository,
    PostgresTicketRepository,
)
from src.trading_kernel.infrastructure.pg_signal_repository import (
    PostgresSignalRepository,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    PostgresStrategyRegistryRepository,
)


__all__ = ["AggregateVersionConflict", "PostgresKernelUnitOfWork"]


class PostgresKernelUnitOfWork:
    tickets: TicketRepository
    aggregates: AggregateRepository
    events: EventRepository
    exchange_commands: ExchangeCommandRepository
    budgets: BudgetRepository
    capacity_claims: CapacityClaimRepository
    incidents: IncidentRepository
    monitors: MonitorRepository
    positions: PositionRepository
    reviews: ReviewRepository
    entry_admission: EntryAdmissionRepository
    signals: SignalRepository
    strategy_registry: StrategyRegistryRepository

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._connection: AsyncConnection | None = None
        self._transaction: AsyncTransaction | None = None

    async def __aenter__(self) -> "PostgresKernelUnitOfWork":
        if self._connection is not None:
            raise RuntimeError("unit of work is already active")
        self._connection = await self._engine.connect()
        self._transaction = await self._connection.begin()
        self.tickets = PostgresTicketRepository(self._connection)
        self.aggregates = PostgresAggregateRepository(self._connection)
        self.events = PostgresEventRepository(self._connection)
        self.exchange_commands = PostgresExchangeCommandRepository(self._connection)
        self.budgets = PostgresBudgetRepository(self._connection)
        self.capacity_claims = PostgresCapacityClaimRepository(self._connection)
        self.incidents = PostgresIncidentRepository(self._connection)
        self.monitors = PostgresMonitorRepository(self._connection)
        self.positions = PostgresPositionRepository(self._connection)
        self.reviews = PostgresReviewRepository(self._connection)
        self.entry_admission = PostgresEntryAdmissionRepository(self._connection)
        self.signals = PostgresSignalRepository(self._connection)
        self.strategy_registry = PostgresStrategyRegistryRepository(self._connection)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        transaction = self._require_transaction()
        connection = self._require_connection()
        try:
            if exc_type is None:
                await transaction.commit()
            else:
                await transaction.rollback()
        finally:
            await connection.close()
            self._transaction = None
            self._connection = None

    async def commit_reduction(
        self,
        *,
        event: TradeEvent,
        reduction: Reduction,
        expected_version: int,
    ) -> None:
        self._require_connection()
        aggregate = reduction.aggregate
        ticket_id = aggregate.identity.ticket_id
        current = await self.aggregates.get_for_update(ticket_id)

        if expected_version == 0:
            if current is not None:
                raise AggregateVersionConflict("Ticket aggregate already exists")
            if not isinstance(event, TicketIssued):
                raise AggregateVersionConflict("new aggregate requires TicketIssued")
            if aggregate.version != 1 or aggregate.last_event_sequence != 1:
                raise AggregateVersionConflict("new aggregate must start at one")
            await self.tickets.add(aggregate.ticket)
            await self.aggregates.add(
                aggregate,
                updated_at_ms=event.occurred_at_ms,
            )
        else:
            if current is None:
                raise AggregateVersionConflict("aggregate does not exist")
            await self.aggregates.save(
                aggregate,
                expected_version=expected_version,
                updated_at_ms=event.occurred_at_ms,
            )

        if event.sequence != aggregate.last_event_sequence:
            raise AggregateVersionConflict("event sequence differs from reduction")
        if _event_ticket_id(event) != ticket_id:
            raise AggregateVersionConflict("event Ticket differs from reduction")

        await self.events.append(event)
        for effect in reduction.effects:
            if isinstance(effect, PrepareEntryCommand):
                await self.exchange_commands.add(
                    _entry_command(effect, occurred_at_ms=event.occurred_at_ms)
                )
                continue
            if isinstance(effect, PrepareInitialStopCommand):
                await self.exchange_commands.add(
                    _initial_stop_command(
                        aggregate,
                        effect,
                        occurred_at_ms=event.occurred_at_ms,
                    )
                )
                continue
            if isinstance(effect, PrepareTakeProfitCommand):
                generation = await self._next_retryable_generation(
                    aggregate=aggregate,
                    kind=ExchangeCommandKind.TAKE_PROFIT,
                )
                await self.exchange_commands.add(
                    _take_profit_command(
                        aggregate,
                        effect,
                        generation=generation,
                        occurred_at_ms=event.occurred_at_ms,
                    )
                )
                continue
            if isinstance(effect, PrepareProtectionReplacementCommand):
                generation = await self._next_retryable_generation(
                    aggregate=aggregate,
                    kind=ExchangeCommandKind.REPLACE_PROTECTION,
                )
                await self.exchange_commands.add(
                    _protection_replacement_command(
                        aggregate,
                        effect,
                        generation=generation,
                        occurred_at_ms=event.occurred_at_ms,
                    )
                )
                continue
            if isinstance(effect, CancelEntryRemainder):
                if aggregate.entry_exchange_order_id is None:
                    raise UnsupportedKernelEffect(
                        "partial fill has no authoritative ENTRY order identity"
                    )
                generation = await self.exchange_commands.next_generation(
                    ticket_id=aggregate.identity.ticket_id,
                    kind=ExchangeCommandKind.CANCEL_ORDER,
                )
                await self.exchange_commands.add(
                    _cancel_protection_command(
                        aggregate,
                        CancelProtectionOrders(
                            ticket_id=effect.ticket_id,
                            exchange_order_id=aggregate.entry_exchange_order_id,
                        ),
                        generation=generation,
                        occurred_at_ms=event.occurred_at_ms,
                    )
                )
                continue
            if isinstance(effect, RequestControlledFlatten):
                if (
                    aggregate.status is not AggregateStatus.PARTIAL_FILL_INCIDENT
                    or aggregate.position_qty != effect.quantity
                ):
                    raise UnsupportedKernelEffect(
                        "controlled flatten intent differs from partial exposure"
                    )
                continue
            if isinstance(effect, PrepareControlledFlattenCommand):
                await self.exchange_commands.add(
                    _controlled_flatten_command(
                        aggregate,
                        effect,
                        occurred_at_ms=event.occurred_at_ms,
                    )
                )
                continue
            if isinstance(effect, PrepareExitCommand):
                generation = await self.exchange_commands.next_generation(
                    ticket_id=aggregate.identity.ticket_id,
                    kind=ExchangeCommandKind.EXIT,
                )
                if generation > 1:
                    prior_commands = await self.exchange_commands.list_for_ticket(
                        aggregate.identity.ticket_id
                    )
                    prior = max(
                        (
                            command
                            for command in prior_commands
                            if command.kind is ExchangeCommandKind.EXIT
                        ),
                        key=lambda command: command.generation,
                    )
                    require_next_generation_allowed(
                        kind=ExchangeCommandKind.EXIT,
                        prior_status=prior.status,
                        next_generation=generation,
                    )
                await self.exchange_commands.add(
                    _exit_command(
                        aggregate,
                        effect,
                        generation=generation,
                        occurred_at_ms=event.occurred_at_ms,
                    )
                )
                continue
            if isinstance(effect, CancelProtectionOrders):
                generation = await self.exchange_commands.next_generation(
                    ticket_id=aggregate.identity.ticket_id,
                    kind=ExchangeCommandKind.CANCEL_ORDER,
                )
                if generation > 1:
                    prior_commands = await self.exchange_commands.list_for_ticket(
                        aggregate.identity.ticket_id
                    )
                    prior = max(
                        (
                            command
                            for command in prior_commands
                            if command.kind is ExchangeCommandKind.CANCEL_ORDER
                        ),
                        key=lambda command: command.generation,
                    )
                    if (
                        isinstance(prior.payload, CancelCommandPayload)
                        and prior.payload.exchange_order_id
                        == effect.exchange_order_id
                    ):
                        require_next_generation_allowed(
                            kind=ExchangeCommandKind.CANCEL_ORDER,
                            prior_status=prior.status,
                            next_generation=generation,
                        )
                await self.exchange_commands.add(
                    _cancel_protection_command(
                        aggregate,
                        effect,
                        generation=generation,
                        occurred_at_ms=event.occurred_at_ms,
                    )
                )
                continue
            if isinstance(effect, MarkCancelCommandReconciledAbsent):
                await self.exchange_commands.mark_cancel_reconciled_absent(
                    ticket_id=effect.ticket_id,
                    exchange_order_id=effect.exchange_order_id,
                    observed_at_ms=event.occurred_at_ms,
                )
                continue
            if isinstance(effect, ReleaseBudget):
                await self.budgets.release(
                    effect.ticket_id,
                    released_at_ms=event.occurred_at_ms,
                )
                await self.entry_admission.release_account_exposure(
                    venue_id=aggregate.ticket.identity.netting_domain.venue_id,
                    account_id=aggregate.ticket.identity.netting_domain.account_id,
                    notional=aggregate.ticket.notional,
                    risk_at_stop=aggregate.ticket.risk_at_stop,
                    updated_at_ms=event.occurred_at_ms,
                )
                continue
            if isinstance(effect, ReleaseEntryLane):
                await self.entry_admission.release_global_lane(
                    ticket_id=effect.ticket_id
                )
                continue
            if isinstance(effect, OpenIncident):
                entry_block_scope = _incident_entry_block_scope(
                    effect.incident_kind
                )
                await self.incidents.add(
                    RuntimeIncidentRecord(
                        incident_id=(
                            f"incident:{effect.ticket_id}:"
                            f"{aggregate.last_event_sequence}"
                        ),
                        ticket_id=effect.ticket_id,
                        incident_kind=effect.incident_kind,
                        status="open",
                        first_blocker=effect.incident_kind,
                        entry_block_scope=entry_block_scope,
                        entry_block_key=canonical_entry_block_key(
                            entry_block_scope,
                            venue_id=aggregate.ticket.identity.netting_domain.venue_id,
                            account_id=aggregate.ticket.identity.netting_domain.account_id,
                            exchange_instrument_id=(
                                aggregate.ticket.identity.netting_domain.exchange_instrument_id
                            ),
                        ),
                        details={"event_id": event.event_id},
                        opened_at_ms=event.occurred_at_ms,
                    )
                )
                continue
            if isinstance(effect, ResolveIncident):
                incident = await self.incidents.get_open_for_ticket_kind(
                    effect.ticket_id,
                    effect.incident_kind,
                )
                if incident is None:
                    raise UnsupportedKernelEffect(
                        "expected runtime incident is missing during resolution"
                    )
                await self.incidents.resolve(
                    incident.incident_id,
                    resolved_at_ms=event.occurred_at_ms,
                )
                continue
            if isinstance(effect, SettleBudget):
                await self.budgets.release(
                    effect.ticket_id,
                    released_at_ms=event.occurred_at_ms,
                )
                await self.entry_admission.release_account_exposure(
                    venue_id=aggregate.ticket.identity.netting_domain.venue_id,
                    account_id=aggregate.ticket.identity.netting_domain.account_id,
                    notional=aggregate.ticket.notional,
                    risk_at_stop=aggregate.ticket.risk_at_stop,
                    updated_at_ms=event.occurred_at_ms,
                )
                continue
            raise UnsupportedKernelEffect(
                f"no durable materializer for {type(effect).__name__}"
            )

        if aggregate.status is AggregateStatus.ENTRY_REJECTED:
            await self.tickets.mark_terminal(
                ticket_id,
                status="entry_rejected",
                terminal_at_ms=event.occurred_at_ms,
            )
        elif aggregate.status is AggregateStatus.ENTRY_RECONCILED_ABSENT:
            await self.tickets.mark_terminal(
                ticket_id,
                status="entry_reconciled_absent",
                terminal_at_ms=event.occurred_at_ms,
            )
        elif aggregate.status is AggregateStatus.TERMINAL:
            await self.tickets.mark_terminal(
                ticket_id,
                status="terminal",
                terminal_at_ms=event.occurred_at_ms,
            )

    async def _next_retryable_generation(
        self,
        *,
        aggregate,
        kind: ExchangeCommandKind,
    ) -> int:
        generation = await self.exchange_commands.next_generation(
            ticket_id=aggregate.identity.ticket_id,
            kind=kind,
        )
        if generation == 1:
            return generation
        prior_commands = await self.exchange_commands.list_for_ticket(
            aggregate.identity.ticket_id
        )
        prior = max(
            (command for command in prior_commands if command.kind is kind),
            key=lambda command: command.generation,
        )
        require_next_generation_allowed(
            kind=kind,
            prior_status=prior.status,
            next_generation=generation,
        )
        return generation

    def _require_connection(self) -> AsyncConnection:
        if self._connection is None:
            raise RuntimeError("unit of work must be entered before use")
        return self._connection

    def _require_transaction(self) -> AsyncTransaction:
        if self._transaction is None:
            raise RuntimeError("unit of work transaction is not active")
        return self._transaction


def _entry_command(
    effect: PrepareEntryCommand,
    *,
    occurred_at_ms: int,
) -> ExchangeCommand:
    ticket = effect.ticket
    command_id = build_command_id(
        ticket_id=ticket.identity.ticket_id,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
    )
    side: Literal["buy", "sell"] = (
        "buy" if ticket.identity.netting_domain.position_side == "long" else "sell"
    )
    order_type: Literal["market", "limit"] = (
        "market" if ticket.entry_order_type is EntryOrderType.MARKET else "limit"
    )
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=ticket.identity,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
        idempotency_key=command_id,
        venue_client_order_id=build_venue_client_order_id(command_id),
        payload=OrderCommandPayload(
            side=side,
            quantity=ticket.quantity,
            order_type=order_type,
            reduce_only=False,
            limit_price=ticket.entry_limit_price,
        ),
        status=ExchangeCommandStatus.PREPARED,
        created_at_ms=occurred_at_ms,
        deadline_at_ms=ticket.expires_at_ms,
    )


def _initial_stop_command(
    aggregate,
    effect: PrepareInitialStopCommand,
    *,
    occurred_at_ms: int,
) -> ExchangeCommand:
    return _order_command(
        aggregate=aggregate,
        kind=ExchangeCommandKind.INITIAL_STOP,
        payload=OrderCommandPayload(
            side=_closing_side(aggregate),
            quantity=effect.quantity,
            order_type="stop_market",
            reduce_only=True,
            stop_price=effect.stop_price,
        ),
        occurred_at_ms=occurred_at_ms,
    )


def _exit_command(
    aggregate,
    effect: PrepareExitCommand,
    *,
    generation: int,
    occurred_at_ms: int,
) -> ExchangeCommand:
    return _order_command(
        aggregate=aggregate,
        kind=ExchangeCommandKind.EXIT,
        generation=generation,
        payload=OrderCommandPayload(
            side=_closing_side(aggregate),
            quantity=effect.quantity,
            order_type="market",
            reduce_only=True,
        ),
        occurred_at_ms=occurred_at_ms,
    )


def _take_profit_command(
    aggregate,
    effect: PrepareTakeProfitCommand,
    *,
    generation: int,
    occurred_at_ms: int,
) -> ExchangeCommand:
    return _order_command(
        aggregate=aggregate,
        kind=ExchangeCommandKind.TAKE_PROFIT,
        generation=generation,
        payload=OrderCommandPayload(
            side=_closing_side(aggregate),
            quantity=effect.quantity,
            order_type="limit",
            reduce_only=True,
            limit_price=effect.limit_price,
        ),
        occurred_at_ms=occurred_at_ms,
    )


def _protection_replacement_command(
    aggregate,
    effect: PrepareProtectionReplacementCommand,
    *,
    generation: int,
    occurred_at_ms: int,
) -> ExchangeCommand:
    return _order_command(
        aggregate=aggregate,
        kind=ExchangeCommandKind.REPLACE_PROTECTION,
        generation=generation,
        payload=OrderCommandPayload(
            side=_closing_side(aggregate),
            quantity=effect.quantity,
            order_type="stop_market",
            reduce_only=True,
            stop_price=effect.stop_price,
            replaces_exchange_order_id=effect.replaces_exchange_order_id,
            source_watermark_ms=effect.source_watermark_ms,
        ),
        occurred_at_ms=occurred_at_ms,
    )


def _controlled_flatten_command(
    aggregate,
    effect: PrepareControlledFlattenCommand,
    *,
    occurred_at_ms: int,
) -> ExchangeCommand:
    return _order_command(
        aggregate=aggregate,
        kind=ExchangeCommandKind.CONTROLLED_FLATTEN,
        payload=OrderCommandPayload(
            side=_closing_side(aggregate),
            quantity=effect.quantity,
            order_type="market",
            reduce_only=True,
        ),
        occurred_at_ms=occurred_at_ms,
    )


def _cancel_protection_command(
    aggregate,
    effect: CancelProtectionOrders,
    *,
    generation: int,
    occurred_at_ms: int,
) -> ExchangeCommand:
    command_id = build_command_id(
        ticket_id=aggregate.identity.ticket_id,
        kind=ExchangeCommandKind.CANCEL_ORDER,
        generation=generation,
    )
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=aggregate.identity,
        kind=ExchangeCommandKind.CANCEL_ORDER,
        generation=generation,
        idempotency_key=command_id,
        venue_client_order_id=build_venue_client_order_id(command_id),
        payload=CancelCommandPayload(exchange_order_id=effect.exchange_order_id),
        status=ExchangeCommandStatus.PREPARED,
        created_at_ms=occurred_at_ms,
        deadline_at_ms=occurred_at_ms + 30_000,
    )


def _order_command(
    *,
    aggregate,
    kind: ExchangeCommandKind,
    generation: int = 1,
    payload: OrderCommandPayload,
    occurred_at_ms: int,
) -> ExchangeCommand:
    command_id = build_command_id(
        ticket_id=aggregate.identity.ticket_id,
        kind=kind,
        generation=generation,
    )
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=aggregate.identity,
        kind=kind,
        generation=generation,
        idempotency_key=command_id,
        venue_client_order_id=build_venue_client_order_id(command_id),
        payload=payload,
        status=ExchangeCommandStatus.PREPARED,
        created_at_ms=occurred_at_ms,
        deadline_at_ms=occurred_at_ms + 30_000,
    )


def _closing_side(aggregate) -> Literal["buy", "sell"]:
    return "sell" if aggregate.identity.netting_domain.position_side == "long" else "buy"


def _incident_entry_block_scope(incident_kind: str) -> EntryBlockScope:
    """Classify reducer safety failures without relying on free-form storage."""

    if incident_kind == "external_flat":
        return EntryBlockScope.NONE
    return EntryBlockScope.ACCOUNT_CAPACITY


def _event_ticket_id(event: TradeEvent) -> str:
    if isinstance(event, TicketIssued):
        return event.ticket.identity.ticket_id
    return event.ticket_id
