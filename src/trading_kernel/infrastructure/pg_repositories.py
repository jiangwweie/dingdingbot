"""SQLAlchemy Core repositories for the clean trading-kernel schema."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.ports import (
    AggregateVersionConflict,
    AccountExposureSnapshot,
    BudgetReservationRecord,
    EntryLaneSnapshot,
    OwnerPolicySnapshot,
    RuntimeIncidentRecord,
)
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.events import (
    BudgetSettled,
    EntryAccepted,
    EntryFilled,
    EntryOutcomeUnknown,
    EntryPartiallyFilled,
    EntryRejected,
    ExitRequested,
    InitialStopConfirmed,
    PositionFlatConfirmed,
    ReconciliationMatched,
    ReviewRecorded,
    TicketIssued,
    TradeEvent,
)
from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)
from src.trading_kernel.domain.ticket import EntryOrderType, TicketStatus, TradeTicket
from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    budget_reservations,
    entry_lane_current,
    exchange_commands,
    owner_policy_current,
    runtime_incidents,
    trade_aggregates,
    trade_events,
    trade_tickets,
)


_EVENT_MODELS = {
    event_type.__name__: event_type
    for event_type in (
        TicketIssued,
        EntryAccepted,
        EntryRejected,
        EntryOutcomeUnknown,
        EntryFilled,
        EntryPartiallyFilled,
        InitialStopConfirmed,
        ExitRequested,
        PositionFlatConfirmed,
        ReconciliationMatched,
        BudgetSettled,
        ReviewRecorded,
    )
}


class PostgresTicketRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, ticket: TradeTicket) -> None:
        await self._connection.execute(sa.insert(trade_tickets).values(_ticket_values(ticket)))

    async def get(self, ticket_id: str) -> TradeTicket | None:
        result = await self._connection.execute(
            sa.select(trade_tickets).where(trade_tickets.c.ticket_id == ticket_id)
        )
        row = result.mappings().one_or_none()
        return None if row is None else _ticket_from_row(row)

    async def mark_terminal(
        self,
        ticket_id: str,
        *,
        status: str,
        terminal_at_ms: int,
    ) -> None:
        updated = await self._connection.execute(
            sa.update(trade_tickets)
            .where(trade_tickets.c.ticket_id == ticket_id)
            .values(
                status=status,
                terminal_at_ms=terminal_at_ms,
                active_netting_domain_key=None,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict("Ticket missing during terminalization")


class PostgresAggregateRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection
        self._tickets = PostgresTicketRepository(connection)

    async def add(
        self,
        aggregate: TradeAggregate,
        *,
        updated_at_ms: int | None = None,
    ) -> None:
        if aggregate.version != 1 or aggregate.last_event_sequence != 1:
            raise AggregateVersionConflict("new aggregate must start at version one")
        await self._connection.execute(
            sa.insert(trade_aggregates).values(
                _aggregate_values(aggregate, updated_at_ms=updated_at_ms)
            )
        )

    async def get(self, ticket_id: str) -> TradeAggregate | None:
        return await self._get(ticket_id, for_update=False)

    async def get_for_update(self, ticket_id: str) -> TradeAggregate | None:
        return await self._get(ticket_id, for_update=True)

    async def _get(
        self,
        ticket_id: str,
        *,
        for_update: bool,
    ) -> TradeAggregate | None:
        statement = sa.select(trade_aggregates).where(
            trade_aggregates.c.ticket_id == ticket_id
        )
        if for_update:
            statement = statement.with_for_update(of=trade_aggregates)
        result = await self._connection.execute(statement)
        row = result.mappings().one_or_none()
        if row is None:
            return None
        ticket = await self._tickets.get(ticket_id)
        if ticket is None:
            raise RuntimeError("aggregate exists without immutable Ticket")
        return _aggregate_from_row(row, ticket)

    async def save(
        self,
        aggregate: TradeAggregate,
        *,
        expected_version: int,
        updated_at_ms: int | None = None,
    ) -> None:
        current = await self.get_for_update(aggregate.identity.ticket_id)
        if current is None:
            raise AggregateVersionConflict("aggregate does not exist")
        if current.version != expected_version:
            raise AggregateVersionConflict(
                f"expected aggregate version {expected_version}, found {current.version}"
            )
        if aggregate.version != expected_version + 1:
            raise AggregateVersionConflict("next aggregate version must increment once")
        if aggregate.last_event_sequence <= current.last_event_sequence:
            raise AggregateVersionConflict("event sequence must advance monotonically")

        result = await self._connection.execute(
            sa.update(trade_aggregates)
            .where(
                trade_aggregates.c.ticket_id == aggregate.identity.ticket_id,
                trade_aggregates.c.version == expected_version,
            )
            .values(_aggregate_values(aggregate, updated_at_ms=updated_at_ms))
        )
        if result.rowcount != 1:
            raise AggregateVersionConflict("aggregate changed during save")


class PostgresEventRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def append(self, event: TradeEvent) -> None:
        await self._connection.execute(
            sa.insert(trade_events).values(
                event_id=event.event_id,
                ticket_id=_event_ticket_id(event),
                sequence=event.sequence,
                event_type=type(event).__name__,
                payload=event.model_dump(mode="json"),
                occurred_at_ms=event.occurred_at_ms,
            )
        )

    async def list_for_ticket(self, ticket_id: str) -> list[TradeEvent]:
        result = await self._connection.execute(
            sa.select(trade_events)
            .where(trade_events.c.ticket_id == ticket_id)
            .order_by(trade_events.c.sequence)
        )
        events: list[TradeEvent] = []
        for row in result.mappings():
            event_model = _EVENT_MODELS.get(row["event_type"])
            if event_model is None:
                raise RuntimeError(f"unsupported persisted event type: {row['event_type']}")
            events.append(event_model.model_validate(row["payload"]))
        return events


class PostgresExchangeCommandRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection
        self._tickets = PostgresTicketRepository(connection)

    async def add(self, command: ExchangeCommand) -> None:
        await self._connection.execute(
            sa.insert(exchange_commands).values(
                command_id=command.command_id,
                ticket_id=command.ticket_identity.ticket_id,
                command_kind=command.kind.value,
                generation=command.generation,
                idempotency_key=command.idempotency_key,
                venue_client_order_id=command.venue_client_order_id,
                status=command.status.value,
                quantity=command.payload.quantity,
                request_payload=command.payload.model_dump(mode="json"),
                result_payload=None,
                claim_owner=None,
                lease_until_ms=None,
                created_at_ms=command.created_at_ms,
                deadline_at_ms=command.deadline_at_ms,
                completed_at_ms=None,
            )
        )

    async def get(self, command_id: str) -> ExchangeCommand | None:
        result = await self._connection.execute(
            sa.select(exchange_commands).where(
                exchange_commands.c.command_id == command_id
            )
        )
        row = result.mappings().one_or_none()
        return None if row is None else await self._command_from_row(row)

    async def list_for_ticket(self, ticket_id: str) -> list[ExchangeCommand]:
        result = await self._connection.execute(
            sa.select(exchange_commands)
            .where(exchange_commands.c.ticket_id == ticket_id)
            .order_by(exchange_commands.c.created_at_ms, exchange_commands.c.command_id)
        )
        return [await self._command_from_row(row) for row in result.mappings()]

    async def claim_one_prepared(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
    ) -> ExchangeCommand | None:
        result = await self._connection.execute(
            sa.select(exchange_commands.c.command_id)
            .where(
                exchange_commands.c.status == ExchangeCommandStatus.PREPARED.value,
                exchange_commands.c.deadline_at_ms > now_ms,
            )
            .order_by(exchange_commands.c.created_at_ms, exchange_commands.c.command_id)
            .with_for_update(skip_locked=True, of=exchange_commands)
            .limit(1)
        )
        command_id = result.scalar_one_or_none()
        if command_id is None:
            return None
        updated = await self._connection.execute(
            sa.update(exchange_commands)
            .where(
                exchange_commands.c.command_id == command_id,
                exchange_commands.c.status == ExchangeCommandStatus.PREPARED.value,
            )
            .values(
                status=ExchangeCommandStatus.CLAIMED.value,
                claim_owner=worker_id,
                lease_until_ms=lease_until_ms,
            )
        )
        if updated.rowcount != 1:
            return None
        return await self.get(str(command_id))

    async def record_result(
        self,
        *,
        command_id: str,
        worker_id: str,
        result: ExchangeCommandResult,
    ) -> None:
        updated = await self._connection.execute(
            sa.update(exchange_commands)
            .where(
                exchange_commands.c.command_id == command_id,
                exchange_commands.c.status == ExchangeCommandStatus.CLAIMED.value,
                exchange_commands.c.claim_owner == worker_id,
            )
            .values(
                status=result.status.value,
                result_payload=result.model_dump(mode="json"),
                completed_at_ms=result.observed_at_ms,
                lease_until_ms=None,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict("command claim changed before result")

    async def get_one_expired_claim(self, *, now_ms: int) -> ExchangeCommand | None:
        result = await self._connection.execute(
            sa.select(exchange_commands.c.command_id)
            .where(
                exchange_commands.c.status == ExchangeCommandStatus.CLAIMED.value,
                exchange_commands.c.lease_until_ms <= now_ms,
            )
            .order_by(exchange_commands.c.lease_until_ms, exchange_commands.c.command_id)
            .with_for_update(skip_locked=True, of=exchange_commands)
            .limit(1)
        )
        command_id = result.scalar_one_or_none()
        return None if command_id is None else await self.get(str(command_id))

    async def record_expired_claim_unknown(
        self,
        *,
        command_id: str,
        result: ExchangeCommandResult,
    ) -> None:
        if result.status is not ExchangeCommandStatus.OUTCOME_UNKNOWN:
            raise ValueError("expired claim recovery requires unknown outcome")
        updated = await self._connection.execute(
            sa.update(exchange_commands)
            .where(
                exchange_commands.c.command_id == command_id,
                exchange_commands.c.status == ExchangeCommandStatus.CLAIMED.value,
                exchange_commands.c.lease_until_ms <= result.observed_at_ms,
            )
            .values(
                status=result.status.value,
                result_payload=result.model_dump(mode="json"),
                completed_at_ms=result.observed_at_ms,
                lease_until_ms=None,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict("expired command claim changed")

    async def _command_from_row(self, row: Mapping[str, object]) -> ExchangeCommand:
        ticket = await self._tickets.get(str(row["ticket_id"]))
        if ticket is None:
            raise RuntimeError("exchange command exists without immutable Ticket")
        return ExchangeCommand(
            command_id=str(row["command_id"]),
            ticket_identity=ticket.identity,
            kind=ExchangeCommandKind(str(row["command_kind"])),
            generation=int(row["generation"]),
            idempotency_key=str(row["idempotency_key"]),
            venue_client_order_id=str(row["venue_client_order_id"]),
            payload=OrderCommandPayload.model_validate(row["request_payload"]),
            status=ExchangeCommandStatus(str(row["status"])),
            created_at_ms=int(row["created_at_ms"]),
            deadline_at_ms=int(row["deadline_at_ms"]),
        )


class PostgresBudgetRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, reservation: BudgetReservationRecord) -> None:
        await self._connection.execute(
            sa.insert(budget_reservations).values(**reservation.model_dump())
        )

    async def get_for_ticket(
        self,
        ticket_id: str,
    ) -> BudgetReservationRecord | None:
        result = await self._connection.execute(
            sa.select(budget_reservations).where(
                budget_reservations.c.ticket_id == ticket_id
            )
        )
        row = result.mappings().one_or_none()
        return None if row is None else BudgetReservationRecord.model_validate(row)

    async def release(self, ticket_id: str, *, released_at_ms: int) -> None:
        updated = await self._connection.execute(
            sa.update(budget_reservations)
            .where(
                budget_reservations.c.ticket_id == ticket_id,
                budget_reservations.c.status == "active",
            )
            .values(status="released", released_at_ms=released_at_ms)
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict("active budget reservation is missing")


class PostgresIncidentRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, incident: RuntimeIncidentRecord) -> None:
        await self._connection.execute(
            sa.insert(runtime_incidents).values(**incident.model_dump(mode="json"))
        )

    async def get_open_for_ticket(
        self,
        ticket_id: str,
    ) -> RuntimeIncidentRecord | None:
        result = await self._connection.execute(
            sa.select(runtime_incidents).where(
                runtime_incidents.c.ticket_id == ticket_id,
                runtime_incidents.c.status == "open",
            )
        )
        row = result.mappings().one_or_none()
        return None if row is None else RuntimeIncidentRecord.model_validate(row)

    async def resolve(self, incident_id: str, *, resolved_at_ms: int) -> None:
        await self._connection.execute(
            sa.update(runtime_incidents)
            .where(runtime_incidents.c.incident_id == incident_id)
            .values(status="resolved", resolved_at_ms=resolved_at_ms)
        )


class PostgresEntryAdmissionRepository:
    GLOBAL_LANE_ID = "global-entry"

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def lock_global_lane(self) -> EntryLaneSnapshot:
        await self._connection.execute(
            pg_insert(entry_lane_current)
            .values(
                lane_id=self.GLOBAL_LANE_ID,
                ticket_id=None,
                signal_event_id=None,
                status="idle",
                claimed_at_ms=None,
                lease_until_ms=None,
                claim_owner=None,
                version=0,
            )
            .on_conflict_do_nothing(index_elements=[entry_lane_current.c.lane_id])
        )
        result = await self._connection.execute(
            sa.select(entry_lane_current)
            .where(entry_lane_current.c.lane_id == self.GLOBAL_LANE_ID)
            .with_for_update(of=entry_lane_current)
        )
        row = result.mappings().one()
        return EntryLaneSnapshot.model_validate(row)

    async def get_global_lane(self) -> EntryLaneSnapshot | None:
        result = await self._connection.execute(
            sa.select(entry_lane_current).where(
                entry_lane_current.c.lane_id == self.GLOBAL_LANE_ID
            )
        )
        row = result.mappings().one_or_none()
        return None if row is None else EntryLaneSnapshot.model_validate(row)

    async def get_owner_policy(
        self,
        owner_policy_id: str,
    ) -> OwnerPolicySnapshot | None:
        result = await self._connection.execute(
            sa.select(owner_policy_current).where(
                owner_policy_current.c.owner_policy_id == owner_policy_id
            )
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return OwnerPolicySnapshot(
            owner_policy_id=str(row["owner_policy_id"]),
            policy_version=int(row["policy_version"]),
            enabled=bool(row["enabled"]),
            real_submit_enabled=bool(row["real_submit_enabled"]),
            max_concurrent_tickets=int(row["max_concurrent_tickets"]),
            max_gross_notional=Decimal(row["max_gross_notional"]),
        )

    async def has_active_ticket_in_domain(self, netting_domain_key: str) -> bool:
        result = await self._connection.execute(
            sa.select(trade_tickets.c.ticket_id)
            .where(
                trade_tickets.c.active_netting_domain_key == netting_domain_key
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def has_ticket_for_signal(self, signal_event_id: str) -> bool:
        result = await self._connection.execute(
            sa.select(trade_tickets.c.ticket_id)
            .where(trade_tickets.c.signal_event_id == signal_event_id)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_account_exposure(
        self,
        account_id: str,
        *,
        for_update: bool = False,
    ) -> AccountExposureSnapshot | None:
        statement = sa.select(account_exposure_current).where(
            account_exposure_current.c.account_id == account_id
        )
        if for_update:
            statement = statement.with_for_update(of=account_exposure_current)
        result = await self._connection.execute(statement)
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else AccountExposureSnapshot.model_validate(row)
        )

    async def reserve_account_exposure(
        self,
        *,
        account_id: str,
        notional: Decimal,
        risk_at_stop: Decimal,
        expected_version: int | None,
        updated_at_ms: int,
    ) -> None:
        if expected_version is None:
            await self._connection.execute(
                sa.insert(account_exposure_current).values(
                    account_id=account_id,
                    gross_notional=notional,
                    gross_risk_at_stop=risk_at_stop,
                    active_ticket_count=1,
                    projection_version=1,
                    updated_at_ms=updated_at_ms,
                )
            )
            return
        result = await self._connection.execute(
            sa.update(account_exposure_current)
            .where(
                account_exposure_current.c.account_id == account_id,
                account_exposure_current.c.projection_version == expected_version,
            )
            .values(
                gross_notional=account_exposure_current.c.gross_notional + notional,
                gross_risk_at_stop=(
                    account_exposure_current.c.gross_risk_at_stop + risk_at_stop
                ),
                active_ticket_count=account_exposure_current.c.active_ticket_count + 1,
                projection_version=expected_version + 1,
                updated_at_ms=updated_at_ms,
            )
        )
        if result.rowcount != 1:
            raise AggregateVersionConflict("account exposure changed during reserve")

    async def release_account_exposure(
        self,
        *,
        account_id: str,
        notional: Decimal,
        risk_at_stop: Decimal,
        updated_at_ms: int,
    ) -> None:
        current = await self.get_account_exposure(account_id, for_update=True)
        if current is None or current.active_ticket_count <= 0:
            raise AggregateVersionConflict("account exposure is missing during release")
        if current.gross_notional < notional or current.gross_risk_at_stop < risk_at_stop:
            raise AggregateVersionConflict("account exposure release would become negative")
        updated = await self._connection.execute(
            sa.update(account_exposure_current)
            .where(
                account_exposure_current.c.account_id == account_id,
                account_exposure_current.c.projection_version
                == current.projection_version,
            )
            .values(
                gross_notional=current.gross_notional - notional,
                gross_risk_at_stop=current.gross_risk_at_stop - risk_at_stop,
                active_ticket_count=current.active_ticket_count - 1,
                projection_version=current.projection_version + 1,
                updated_at_ms=updated_at_ms,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict("account exposure changed during release")

    async def claim_global_lane(
        self,
        *,
        ticket_id: str,
        signal_event_id: str,
        claim_owner: str,
        claimed_at_ms: int,
        lease_until_ms: int,
        expected_version: int,
    ) -> None:
        result = await self._connection.execute(
            sa.update(entry_lane_current)
            .where(
                entry_lane_current.c.lane_id == self.GLOBAL_LANE_ID,
                entry_lane_current.c.status == "idle",
                entry_lane_current.c.version == expected_version,
            )
            .values(
                ticket_id=ticket_id,
                signal_event_id=signal_event_id,
                status="claimed",
                claimed_at_ms=claimed_at_ms,
                lease_until_ms=lease_until_ms,
                claim_owner=claim_owner,
                version=expected_version + 1,
            )
        )
        if result.rowcount != 1:
            raise AggregateVersionConflict("global entry lane changed during claim")

    async def release_global_lane(self, *, ticket_id: str) -> None:
        updated = await self._connection.execute(
            sa.update(entry_lane_current)
            .where(
                entry_lane_current.c.lane_id == self.GLOBAL_LANE_ID,
                entry_lane_current.c.ticket_id == ticket_id,
                entry_lane_current.c.status == "claimed",
            )
            .values(
                ticket_id=None,
                signal_event_id=None,
                status="idle",
                claimed_at_ms=None,
                lease_until_ms=None,
                claim_owner=None,
                version=entry_lane_current.c.version + 1,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict("global entry lane ownership mismatch")


def _ticket_values(ticket: TradeTicket) -> dict[str, object]:
    identity = ticket.identity
    return {
        "ticket_id": identity.ticket_id,
        "exposure_episode_id": identity.exposure_episode_id,
        "signal_event_id": identity.signal_event_id,
        "strategy_group_id": identity.runtime.strategy_group_id,
        "strategy_version_id": identity.runtime.strategy_version_id,
        "event_spec_id": identity.runtime.event_spec_id,
        "runtime_profile_id": identity.runtime.runtime_profile_id,
        "owner_policy_id": ticket.owner_policy_id,
        "owner_policy_version": ticket.owner_policy_version,
        "runtime_scope_id": ticket.runtime_scope_id,
        "runtime_scope_version": ticket.runtime_scope_version,
        "account_id": identity.netting_domain.account_id,
        "venue_id": identity.netting_domain.venue_id,
        "exchange_instrument_id": identity.netting_domain.exchange_instrument_id,
        "position_side": identity.netting_domain.position_side,
        "netting_domain_key": identity.netting_domain.key(),
        "active_netting_domain_key": identity.netting_domain.key(),
        "quantity": ticket.quantity,
        "notional": ticket.notional,
        "leverage": ticket.leverage,
        "risk_at_stop": ticket.risk_at_stop,
        "entry_order_type": ticket.entry_order_type.value,
        "entry_limit_price": ticket.entry_limit_price,
        "initial_stop_price": ticket.initial_stop_price,
        "take_profit_prices": [str(price) for price in ticket.take_profit_prices],
        "fact_digest": ticket.fact_digest,
        "decision_digest": ticket.decision_digest(),
        "status": ticket.status.value,
        "created_at_ms": ticket.created_at_ms,
        "expires_at_ms": ticket.expires_at_ms,
        "terminal_at_ms": None,
    }


def _ticket_from_row(row: Mapping[str, object]) -> TradeTicket:
    runtime = RuntimeIdentity(
        runtime_profile_id=str(row["runtime_profile_id"]),
        strategy_group_id=str(row["strategy_group_id"]),
        strategy_version_id=str(row["strategy_version_id"]),
        event_spec_id=str(row["event_spec_id"]),
    )
    domain = NettingDomain(
        venue_id=str(row["venue_id"]),
        account_id=str(row["account_id"]),
        exchange_instrument_id=str(row["exchange_instrument_id"]),
        position_side=str(row["position_side"]),
    )
    identity = TicketIdentity(
        ticket_id=str(row["ticket_id"]),
        exposure_episode_id=str(row["exposure_episode_id"]),
        signal_event_id=str(row["signal_event_id"]),
        runtime=runtime,
        netting_domain=domain,
    )
    return TradeTicket(
        identity=identity,
        owner_policy_id=str(row["owner_policy_id"]),
        owner_policy_version=int(row["owner_policy_version"]),
        runtime_scope_id=str(row["runtime_scope_id"]),
        runtime_scope_version=int(row["runtime_scope_version"]),
        fact_digest=str(row["fact_digest"]),
        created_at_ms=int(row["created_at_ms"]),
        expires_at_ms=int(row["expires_at_ms"]),
        quantity=Decimal(row["quantity"]),
        notional=Decimal(row["notional"]),
        leverage=Decimal(row["leverage"]),
        risk_at_stop=Decimal(row["risk_at_stop"]),
        entry_order_type=EntryOrderType(str(row["entry_order_type"])),
        entry_limit_price=(
            None
            if row["entry_limit_price"] is None
            else Decimal(row["entry_limit_price"])
        ),
        initial_stop_price=Decimal(row["initial_stop_price"]),
        take_profit_prices=tuple(Decimal(value) for value in row["take_profit_prices"]),
        status=TicketStatus(str(row["status"])),
    )


def _aggregate_values(
    aggregate: TradeAggregate,
    *,
    updated_at_ms: int | None,
) -> dict[str, object]:
    return {
        "ticket_id": aggregate.identity.ticket_id,
        "status": aggregate.status.value,
        "version": aggregate.version,
        "last_event_sequence": aggregate.last_event_sequence,
        "position_qty": aggregate.position_qty,
        "average_fill_price": aggregate.average_fill_price,
        "protected_qty": aggregate.protected_qty,
        "entry_exchange_order_id": aggregate.entry_exchange_order_id,
        "initial_stop_exchange_order_id": aggregate.initial_stop_exchange_order_id,
        "review_id": aggregate.review_id,
        "updated_at_ms": updated_at_ms or aggregate.ticket.created_at_ms,
    }


def _aggregate_from_row(
    row: Mapping[str, object],
    ticket: TradeTicket,
) -> TradeAggregate:
    return TradeAggregate(
        identity=ticket.identity,
        ticket=ticket,
        status=AggregateStatus(str(row["status"])),
        version=int(row["version"]),
        last_event_sequence=int(row["last_event_sequence"]),
        position_qty=Decimal(row["position_qty"]),
        average_fill_price=(
            None
            if row["average_fill_price"] is None
            else Decimal(row["average_fill_price"])
        ),
        protected_qty=Decimal(row["protected_qty"]),
        entry_exchange_order_id=(
            None
            if row["entry_exchange_order_id"] is None
            else str(row["entry_exchange_order_id"])
        ),
        initial_stop_exchange_order_id=(
            None
            if row["initial_stop_exchange_order_id"] is None
            else str(row["initial_stop_exchange_order_id"])
        ),
        review_id=None if row["review_id"] is None else str(row["review_id"]),
    )


def _event_ticket_id(event: TradeEvent) -> str:
    if isinstance(event, TicketIssued):
        return event.ticket.identity.ticket_id
    return event.ticket_id
