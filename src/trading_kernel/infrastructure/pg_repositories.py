"""SQLAlchemy Core repositories for the clean trading-kernel schema."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

import sqlalchemy as sa
from pydantic import TypeAdapter
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.elements import ColumnElement

from src.trading_kernel.application.ports import (
    AggregateVersionConflict,
    AccountExposureSnapshot,
    BudgetReservationRecord,
    EntryLaneSnapshot,
    MonitorStateRecord,
    OwnerPolicySnapshot,
    RuntimeIncidentRecord,
    TradeReviewRecord,
)
from src.trading_kernel.domain.capacity import CapacityClaim
from src.trading_kernel.domain.entry_admission_snapshot import AdmissionOwnership
from src.trading_kernel.domain.incident_blocking import EntryBlockScope
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.commands import (
    CommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.events import (
    BudgetSettled,
    CancelOrderAbsenceConfirmed,
    CancelOrderOutcomeUnknown,
    CancelOrderRejected,
    ControlledFlattenAbsenceConfirmed,
    ControlledFlattenAccepted,
    ControlledFlattenOutcomeUnknown,
    ControlledFlattenRejected,
    EntryAccepted,
    EntryAbsenceConfirmed,
    EntryFilled,
    EntryOutcomeUnknown,
    EntryPartiallyFilled,
    EntryRejected,
    EntryRemainderCancelConfirmed,
    EntryRemainderCancelOutcomeUnknown,
    EntryRemainderCancelRejected,
    ExternalFlatDetected,
    ExitAccepted,
    ExitAbsenceConfirmed,
    ExitOutcomeUnknown,
    ExitRejected,
    ExitRequested,
    InitialStopConfirmed,
    InitialStopAbsenceConfirmed,
    InitialStopOutcomeUnknown,
    InitialStopRejected,
    OwnedOrphanOrderDetected,
    OwnedOrderAbsenceConfirmed,
    OwnedOrphanCancelConfirmed,
    PositionFlatConfirmed,
    ProtectionCancelConfirmed,
    ProtectionCancelAbsenceConfirmed,
    ProtectionCancelOutcomeUnknown,
    ProtectionCancelRejected,
    ProtectionReplacementAbsenceConfirmed,
    ProtectionReplacementConfirmed,
    ProtectionReplacementOutcomeUnknown,
    ProtectionReplacementRejected,
    ReconciliationMatched,
    ReviewRecorded,
    TicketIssued,
    TakeProfitAbsenceConfirmed,
    TakeProfitConfirmed,
    TakeProfitFilled,
    TakeProfitOutcomeUnknown,
    TakeProfitRejected,
    TradeEvent,
    UnownedOrderDetected,
)
from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.ticket import EntryOrderType, TicketStatus, TradeTicket
from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    budget_reservations,
    capacity_claims,
    entry_lane_current,
    exchange_commands,
    monitor_current,
    monitor_events,
    owner_policy_current,
    positions_current,
    runtime_incidents,
    trade_aggregates,
    trade_events,
    trade_reviews,
    trade_tickets,
)


_EVENT_MODELS = {
    event_type.__name__: event_type
    for event_type in (
        TicketIssued,
        EntryAccepted,
        EntryAbsenceConfirmed,
        EntryRejected,
        EntryOutcomeUnknown,
        EntryFilled,
        EntryPartiallyFilled,
        EntryRemainderCancelConfirmed,
        EntryRemainderCancelRejected,
        EntryRemainderCancelOutcomeUnknown,
        InitialStopConfirmed,
        InitialStopRejected,
        InitialStopOutcomeUnknown,
        InitialStopAbsenceConfirmed,
        TakeProfitConfirmed,
        TakeProfitRejected,
        TakeProfitOutcomeUnknown,
        TakeProfitAbsenceConfirmed,
        TakeProfitFilled,
        ProtectionReplacementConfirmed,
        ProtectionReplacementRejected,
        ProtectionReplacementOutcomeUnknown,
        ProtectionReplacementAbsenceConfirmed,
        ExitRequested,
        ExitAccepted,
        ExitRejected,
        ExitOutcomeUnknown,
        ExitAbsenceConfirmed,
        ControlledFlattenAccepted,
        ControlledFlattenRejected,
        ControlledFlattenOutcomeUnknown,
        ControlledFlattenAbsenceConfirmed,
        PositionFlatConfirmed,
        ExternalFlatDetected,
        OwnedOrphanOrderDetected,
        OwnedOrderAbsenceConfirmed,
        OwnedOrphanCancelConfirmed,
        UnownedOrderDetected,
        ProtectionCancelConfirmed,
        ProtectionCancelRejected,
        ProtectionCancelOutcomeUnknown,
        ProtectionCancelAbsenceConfirmed,
        ReconciliationMatched,
        BudgetSettled,
        CancelOrderAbsenceConfirmed,
        CancelOrderRejected,
        CancelOrderOutcomeUnknown,
        ReviewRecorded,
    )
}
_COMMAND_PAYLOAD_ADAPTER: TypeAdapter[CommandPayload] = TypeAdapter(CommandPayload)


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

    async def has_other_instrument_ticket_in_window(
        self,
        *,
        ticket_id: str,
        venue_id: str,
        account_id: str,
        exchange_instrument_id: str,
        entry_time_ms: int,
        exit_time_ms: int,
    ) -> bool:
        if entry_time_ms <= 0 or exit_time_ms < entry_time_ms:
            raise ValueError("Ticket overlap window is invalid")
        result = await self._connection.execute(
            sa.select(
                sa.exists().where(
                    trade_tickets.c.ticket_id != ticket_id,
                    trade_tickets.c.venue_id == venue_id,
                    trade_tickets.c.account_id == account_id,
                    trade_tickets.c.exchange_instrument_id
                    == exchange_instrument_id,
                    trade_tickets.c.status.not_in(
                        (
                            "expired_before_submit",
                            "entry_rejected",
                            "entry_reconciled_absent",
                        )
                    ),
                    trade_tickets.c.created_at_ms <= exit_time_ms,
                    sa.or_(
                        trade_tickets.c.terminal_at_ms.is_(None),
                        trade_tickets.c.terminal_at_ms >= entry_time_ms,
                    ),
                )
            )
        )
        return bool(result.scalar_one())


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

    async def get_next_for_statuses(
        self,
        statuses: tuple[AggregateStatus, ...],
        *,
        work_kind: Literal["lifecycle", "reconciliation"] | None = None,
        now_ms: int | None = None,
    ) -> TradeAggregate | None:
        if not statuses:
            return None
        due_column = None
        if work_kind == "lifecycle":
            due_column = trade_aggregates.c.lifecycle_due_at_ms
        elif work_kind == "reconciliation":
            due_column = trade_aggregates.c.reconciliation_due_at_ms
        if due_column is not None and (now_ms is None or now_ms <= 0):
            raise ValueError("scheduled aggregate selection requires positive now_ms")
        conditions: list[ColumnElement[bool]] = [
            trade_aggregates.c.status.in_(
                tuple(status.value for status in statuses)
            )
        ]
        if due_column is not None:
            conditions.append(
                sa.func.coalesce(due_column, trade_aggregates.c.updated_at_ms)
                <= now_ms
            )
        order_column = (
            trade_aggregates.c.updated_at_ms
            if due_column is None
            else sa.func.coalesce(due_column, trade_aggregates.c.updated_at_ms)
        )
        result = await self._connection.execute(
            sa.select(trade_aggregates.c.ticket_id)
            .where(*conditions)
            .order_by(
                order_column,
                trade_aggregates.c.ticket_id,
            )
            .with_for_update(skip_locked=True, of=trade_aggregates)
            .limit(1)
        )
        ticket_id = result.scalar_one_or_none()
        return None if ticket_id is None else await self.get(str(ticket_id))

    async def schedule_next_check(
        self,
        ticket_id: str,
        *,
        work_kind: Literal["lifecycle", "reconciliation"],
        due_at_ms: int,
    ) -> None:
        if due_at_ms <= 0:
            raise ValueError("aggregate next-check time must be positive")
        column = (
            trade_aggregates.c.lifecycle_due_at_ms
            if work_kind == "lifecycle"
            else trade_aggregates.c.reconciliation_due_at_ms
        )
        updated = await self._connection.execute(
            sa.update(trade_aggregates)
            .where(trade_aggregates.c.ticket_id == ticket_id)
            .values({column.name: due_at_ms})
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict("aggregate missing during reschedule")

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
                quantity=(
                    command.payload.quantity
                    if isinstance(command.payload, OrderCommandPayload)
                    else None
                ),
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

    async def next_generation(
        self,
        *,
        ticket_id: str,
        kind: ExchangeCommandKind,
    ) -> int:
        result = await self._connection.execute(
            sa.select(sa.func.coalesce(sa.func.max(exchange_commands.c.generation), 0))
            .where(
                exchange_commands.c.ticket_id == ticket_id,
                exchange_commands.c.command_kind == kind.value,
            )
        )
        return int(result.scalar_one()) + 1

    async def claim_one_prepared(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
        ticket_id: str | None = None,
        command_kinds: tuple[ExchangeCommandKind, ...] = (),
    ) -> ExchangeCommand | None:
        conditions = [
            exchange_commands.c.status == ExchangeCommandStatus.PREPARED.value,
            exchange_commands.c.deadline_at_ms > now_ms,
        ]
        if ticket_id is not None:
            conditions.append(exchange_commands.c.ticket_id == ticket_id)
        if command_kinds:
            conditions.append(
                exchange_commands.c.command_kind.in_(
                    tuple(kind.value for kind in command_kinds)
                )
            )
        result = await self._connection.execute(
            sa.select(exchange_commands.c.command_id)
            .where(*conditions)
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

    async def mark_claimed_superseded(
        self,
        *,
        command_id: str,
        worker_id: str,
        observed_at_ms: int,
        reason: str,
    ) -> None:
        normalized_reason = str(reason or "").strip()
        if not normalized_reason:
            raise ValueError("superseded command requires a reason")
        updated = await self._connection.execute(
            sa.update(exchange_commands)
            .where(
                exchange_commands.c.command_id == command_id,
                exchange_commands.c.status == ExchangeCommandStatus.CLAIMED.value,
                exchange_commands.c.claim_owner == worker_id,
            )
            .values(
                status=ExchangeCommandStatus.SUPERSEDED.value,
                result_payload={
                    "status": ExchangeCommandStatus.SUPERSEDED.value,
                    "reason": normalized_reason,
                    "observed_at_ms": observed_at_ms,
                },
                completed_at_ms=observed_at_ms,
                lease_until_ms=None,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict("command claim changed before supersession")

    async def get_one_expired_claim(
        self,
        *,
        now_ms: int,
        ticket_id: str | None = None,
        command_kinds: tuple[ExchangeCommandKind, ...] = (),
    ) -> ExchangeCommand | None:
        conditions = [
            exchange_commands.c.status == ExchangeCommandStatus.CLAIMED.value,
            exchange_commands.c.lease_until_ms <= now_ms,
        ]
        if ticket_id is not None:
            conditions.append(exchange_commands.c.ticket_id == ticket_id)
        if command_kinds:
            conditions.append(
                exchange_commands.c.command_kind.in_(
                    tuple(kind.value for kind in command_kinds)
                )
            )
        result = await self._connection.execute(
            sa.select(exchange_commands.c.command_id)
            .where(*conditions)
            .order_by(exchange_commands.c.lease_until_ms, exchange_commands.c.command_id)
            .with_for_update(skip_locked=True, of=exchange_commands)
            .limit(1)
        )
        command_id = result.scalar_one_or_none()
        return None if command_id is None else await self.get(str(command_id))

    async def get_one_unknown(self) -> ExchangeCommand | None:
        result = await self._connection.execute(
            sa.select(exchange_commands.c.command_id)
            .where(
                exchange_commands.c.status
                == ExchangeCommandStatus.OUTCOME_UNKNOWN.value
            )
            .order_by(
                exchange_commands.c.completed_at_ms,
                exchange_commands.c.command_id,
            )
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

    async def mark_cancel_reconciled_absent(
        self,
        *,
        ticket_id: str,
        exchange_order_id: str,
        observed_at_ms: int,
    ) -> None:
        updated = await self._connection.execute(
            sa.update(exchange_commands)
            .where(
                exchange_commands.c.ticket_id == ticket_id,
                exchange_commands.c.command_kind
                == ExchangeCommandKind.CANCEL_ORDER.value,
                exchange_commands.c.status
                == ExchangeCommandStatus.OUTCOME_UNKNOWN.value,
                exchange_commands.c.request_payload["exchange_order_id"].astext
                == exchange_order_id,
            )
            .values(
                status=ExchangeCommandStatus.RECONCILED_ABSENT.value,
                completed_at_ms=observed_at_ms,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict(
                "unknown cancel command was not available for absence reconciliation"
            )

    async def reconcile_unknown_submitted(
        self,
        *,
        command_id: str,
        exchange_order_id: str,
        observed_at_ms: int,
    ) -> None:
        updated = await self._connection.execute(
            sa.update(exchange_commands)
            .where(
                exchange_commands.c.command_id == command_id,
                exchange_commands.c.status
                == ExchangeCommandStatus.OUTCOME_UNKNOWN.value,
            )
            .values(
                status=ExchangeCommandStatus.RECONCILED_ACCEPTED.value,
                result_payload={
                    "status": "reconciled_accepted",
                    "exchange_order_id": exchange_order_id,
                    "observed_at_ms": observed_at_ms,
                },
                completed_at_ms=observed_at_ms,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict(
                "unknown command changed before submitted reconciliation"
            )

    async def reconcile_unknown_absent(
        self,
        *,
        command_id: str,
        observed_at_ms: int,
        reason: str,
    ) -> None:
        updated = await self._connection.execute(
            sa.update(exchange_commands)
            .where(
                exchange_commands.c.command_id == command_id,
                exchange_commands.c.status
                == ExchangeCommandStatus.OUTCOME_UNKNOWN.value,
            )
            .values(
                status=ExchangeCommandStatus.RECONCILED_ABSENT.value,
                result_payload={
                    "status": "reconciled_absent",
                    "reason": reason,
                    "observed_at_ms": observed_at_ms,
                },
                completed_at_ms=observed_at_ms,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict(
                "unknown command changed before absence reconciliation"
            )

    async def _command_from_row(self, row: RowMapping) -> ExchangeCommand:
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
            payload=_COMMAND_PAYLOAD_ADAPTER.validate_python(row["request_payload"]),
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


class PostgresCapacityClaimRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, claim: CapacityClaim) -> None:
        await self._connection.execute(
            sa.insert(capacity_claims).values(_capacity_claim_values(claim))
        )

    async def get(self, capacity_claim_id: str) -> CapacityClaim | None:
        return await self._get(
            capacity_claims.c.capacity_claim_id == capacity_claim_id
        )

    async def get_for_signal(self, signal_event_id: str) -> CapacityClaim | None:
        return await self._get(
            capacity_claims.c.signal_event_id == signal_event_id
        )

    async def get_for_ticket(self, ticket_id: str) -> CapacityClaim | None:
        return await self._get(capacity_claims.c.ticket_id == ticket_id)

    async def _get(
        self,
        predicate: sa.ColumnElement[bool],
    ) -> CapacityClaim | None:
        result = await self._connection.execute(
            sa.select(capacity_claims).where(predicate)
        )
        row = result.mappings().one_or_none()
        return None if row is None else _capacity_claim_from_row(row)


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
            sa.select(runtime_incidents)
            .where(
                runtime_incidents.c.ticket_id == ticket_id,
                runtime_incidents.c.status == "open",
            )
            .order_by(
                runtime_incidents.c.opened_at_ms.desc(),
                runtime_incidents.c.incident_id.desc(),
            )
            .limit(1)
        )
        row = result.mappings().one_or_none()
        return None if row is None else RuntimeIncidentRecord.model_validate(row)

    async def get_open_for_ticket_kind(
        self,
        ticket_id: str,
        incident_kind: str,
    ) -> RuntimeIncidentRecord | None:
        result = await self._connection.execute(
            sa.select(runtime_incidents)
            .where(
                runtime_incidents.c.ticket_id == ticket_id,
                runtime_incidents.c.incident_kind == incident_kind,
                runtime_incidents.c.status == "open",
            )
            .order_by(
                runtime_incidents.c.opened_at_ms.desc(),
                runtime_incidents.c.incident_id.desc(),
            )
            .limit(1)
        )
        row = result.mappings().one_or_none()
        return None if row is None else RuntimeIncidentRecord.model_validate(row)

    async def resolve(self, incident_id: str, *, resolved_at_ms: int) -> None:
        await self._connection.execute(
            sa.update(runtime_incidents)
            .where(runtime_incidents.c.incident_id == incident_id)
            .values(status="resolved", resolved_at_ms=resolved_at_ms)
        )


class PostgresPositionRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def upsert(
        self,
        *,
        ticket_id: str,
        snapshot: PositionSnapshot,
    ) -> None:
        key = snapshot.netting_domain.key()
        current = await self._connection.execute(
            sa.select(positions_current.c.projection_version)
            .where(positions_current.c.netting_domain_key == key)
            .with_for_update(of=positions_current)
        )
        version = current.scalar_one_or_none()
        values = {
            "ticket_id": ticket_id if snapshot.quantity > 0 else None,
            "venue_id": snapshot.netting_domain.venue_id,
            "account_id": snapshot.netting_domain.account_id,
            "exchange_instrument_id": (
                snapshot.netting_domain.exchange_instrument_id
            ),
            "position_side": snapshot.netting_domain.position_side,
            "quantity": snapshot.quantity,
            "average_entry_price": snapshot.average_entry_price,
            "observed_at_ms": snapshot.observed_at_ms,
            "projection_version": 1 if version is None else int(version) + 1,
        }
        if version is None:
            await self._connection.execute(
                sa.insert(positions_current).values(
                    netting_domain_key=key,
                    **values,
                )
            )
        else:
            await self._connection.execute(
                sa.update(positions_current)
                .where(positions_current.c.netting_domain_key == key)
                .values(**values)
            )

    async def get(self, netting_domain_key: str) -> PositionSnapshot | None:
        result = await self._connection.execute(
            sa.select(positions_current).where(
                positions_current.c.netting_domain_key == netting_domain_key
            )
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return PositionSnapshot(
            netting_domain=NettingDomain(
                venue_id=str(row["venue_id"]),
                account_id=str(row["account_id"]),
                exchange_instrument_id=str(row["exchange_instrument_id"]),
                position_side=_position_side(row["position_side"]),
            ),
            quantity=Decimal(row["quantity"]),
            average_entry_price=(
                None
                if row["average_entry_price"] is None
                else Decimal(row["average_entry_price"])
            ),
            open_orders=(),
            observed_at_ms=int(row["observed_at_ms"]),
        )


class PostgresReviewRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, review: TradeReviewRecord) -> None:
        await self._connection.execute(
            sa.insert(trade_reviews).values(**review.model_dump(mode="json"))
        )

    async def get_for_ticket(self, ticket_id: str) -> TradeReviewRecord | None:
        result = await self._connection.execute(
            sa.select(trade_reviews).where(trade_reviews.c.ticket_id == ticket_id)
        )
        row = result.mappings().one_or_none()
        return None if row is None else TradeReviewRecord.model_validate(row)


class PostgresMonitorRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def get(self, monitor_key: str) -> MonitorStateRecord | None:
        result = await self._connection.execute(
            sa.select(monitor_current).where(
                monitor_current.c.monitor_key == monitor_key
            )
        )
        row = result.mappings().one_or_none()
        return None if row is None else MonitorStateRecord.model_validate(row)

    async def save_if_changed(
        self,
        state: MonitorStateRecord,
    ) -> MonitorStateRecord:
        result = await self._connection.execute(
            sa.select(monitor_current)
            .where(monitor_current.c.monitor_key == state.monitor_key)
            .with_for_update(of=monitor_current)
        )
        current_row = result.mappings().one_or_none()
        if current_row is not None and _same_monitor_state(current_row, state):
            return MonitorStateRecord.model_validate(current_row)

        version = 1 if current_row is None else int(current_row["projection_version"]) + 1
        persisted = state.model_copy(update={"projection_version": version})
        values = persisted.model_dump(mode="json")
        if current_row is None:
            await self._connection.execute(sa.insert(monitor_current).values(**values))
        else:
            await self._connection.execute(
                sa.update(monitor_current)
                .where(monitor_current.c.monitor_key == state.monitor_key)
                .values(**values)
            )
        await self._connection.execute(
            sa.insert(monitor_events).values(
                monitor_event_id=f"monitor-event:{state.monitor_key}:{version}",
                monitor_key=state.monitor_key,
                event_type="state_changed",
                payload={
                    "owner_status": state.owner_status,
                    "summary": state.summary,
                    "intervention": state.intervention,
                    "ticket_id": state.ticket_id,
                    "incident_id": state.incident_id,
                    "projection_version": version,
                },
                created_at_ms=state.updated_at_ms,
            )
        )
        return persisted


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
            new_entry_submit_enabled=bool(row["new_entry_submit_enabled"]),
            priority_rank=int(row["priority_rank"]),
            max_concurrent_tickets=int(row["max_concurrent_tickets"]),
            planned_stop_risk_fraction=Decimal(row["planned_stop_risk_fraction"]),
            max_initial_margin_utilization=Decimal(
                row["max_initial_margin_utilization"]
            ),
            max_leverage=int(row["max_leverage"]),
            supported_margin_mode=str(row["supported_margin_mode"]),
            min_liquidation_distance_to_stop_distance_ratio=Decimal(
                row["min_liquidation_distance_to_stop_distance_ratio"]
            ),
            max_post_fill_stop_risk_overrun_fraction=Decimal(
                row["max_post_fill_stop_risk_overrun_fraction"]
            ),
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

    async def read_admission_ownership(
        self,
        *,
        venue_id: str,
        account_id: str,
        exchange_instrument_id: str,
    ) -> AdmissionOwnership:
        """Load only current BRC ownership relevant to one admission snapshot."""

        active_ticket = sa.and_(
            trade_tickets.c.venue_id == venue_id,
            trade_tickets.c.account_id == account_id,
            trade_tickets.c.active_netting_domain_key.is_not(None),
        )
        domains_result = await self._connection.execute(
            sa.select(trade_tickets.c.active_netting_domain_key)
            .where(active_ticket)
            .order_by(trade_tickets.c.active_netting_domain_key)
        )
        owned_position_domain_keys = tuple(
            str(value)
            for value in domains_result.scalars().all()
            if value is not None
        )

        order_id_columns = (
            trade_aggregates.c.entry_exchange_order_id,
            trade_aggregates.c.initial_stop_exchange_order_id,
            trade_aggregates.c.active_stop_exchange_order_id,
            trade_aggregates.c.tp1_exchange_order_id,
            trade_aggregates.c.pending_replaced_stop_exchange_order_id,
            trade_aggregates.c.pending_cancel_exchange_order_id,
            trade_aggregates.c.exit_exchange_order_id,
        )
        order_rows = await self._connection.execute(
            sa.select(*order_id_columns)
            .select_from(
                trade_aggregates.join(
                    trade_tickets,
                    trade_tickets.c.ticket_id == trade_aggregates.c.ticket_id,
                )
            )
            .where(active_ticket)
        )
        owned_exchange_order_ids = tuple(
            sorted(
                {
                    str(value)
                    for row in order_rows.mappings()
                    for value in row.values()
                    if value is not None and str(value).strip()
                }
            )
        )

        unknown_result = await self._connection.execute(
            sa.select(exchange_commands.c.ticket_id)
            .select_from(
                exchange_commands.join(
                    trade_tickets,
                    trade_tickets.c.ticket_id == exchange_commands.c.ticket_id,
                )
            )
            .where(
                active_ticket,
                exchange_commands.c.status
                == ExchangeCommandStatus.OUTCOME_UNKNOWN.value,
            )
            .distinct()
            .order_by(exchange_commands.c.ticket_id)
        )
        unknown_command_outcome_ticket_ids = tuple(
            str(value) for value in unknown_result.scalars().all()
        )

        account_key = f"{venue_id}:{account_id}"
        leverage_key = f"{account_key}:{exchange_instrument_id}"
        incident_result = await self._connection.execute(
            sa.select(runtime_incidents.c.entry_block_scope)
            .where(
                runtime_incidents.c.status == "open",
                sa.or_(
                    runtime_incidents.c.entry_block_scope
                    == EntryBlockScope.RUNTIME.value,
                    sa.and_(
                        runtime_incidents.c.entry_block_scope
                        == EntryBlockScope.ACCOUNT_CAPACITY.value,
                        runtime_incidents.c.entry_block_key == account_key,
                    ),
                    sa.and_(
                        runtime_incidents.c.entry_block_scope
                        == EntryBlockScope.LEVERAGE_DOMAIN.value,
                        runtime_incidents.c.entry_block_key == leverage_key,
                    ),
                ),
            )
            .distinct()
            .order_by(runtime_incidents.c.entry_block_scope)
        )
        open_incident_scopes = tuple(
            EntryBlockScope(str(value))
            for value in incident_result.scalars().all()
        )
        return AdmissionOwnership(
            owned_position_domain_keys=owned_position_domain_keys,
            owned_exchange_order_ids=owned_exchange_order_ids,
            open_incident_scopes=open_incident_scopes,
            unknown_command_outcome_ticket_ids=unknown_command_outcome_ticket_ids,
        )

    async def get_account_exposure(
        self,
        venue_id: str,
        account_id: str,
        *,
        for_update: bool = False,
    ) -> AccountExposureSnapshot | None:
        statement = sa.select(account_exposure_current).where(
            account_exposure_current.c.venue_id == venue_id,
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
        venue_id: str,
        account_id: str,
        notional: Decimal,
        risk_at_stop: Decimal,
        expected_version: int | None,
        updated_at_ms: int,
    ) -> None:
        if expected_version is None:
            await self._connection.execute(
                sa.insert(account_exposure_current).values(
                    venue_id=venue_id,
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
                account_exposure_current.c.venue_id == venue_id,
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
        venue_id: str,
        account_id: str,
        notional: Decimal,
        risk_at_stop: Decimal,
        updated_at_ms: int,
    ) -> None:
        current = await self.get_account_exposure(
            venue_id,
            account_id,
            for_update=True,
        )
        if current is None or current.active_ticket_count <= 0:
            raise AggregateVersionConflict("account exposure is missing during release")
        if current.gross_notional < notional or current.gross_risk_at_stop < risk_at_stop:
            raise AggregateVersionConflict("account exposure release would become negative")
        updated = await self._connection.execute(
            sa.update(account_exposure_current)
            .where(
                account_exposure_current.c.venue_id == venue_id,
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
        "entry_reference_price": ticket.entry_reference_price,
        "quantity": ticket.quantity,
        "notional": ticket.notional,
        "capacity_claim_id": ticket.capacity_claim_id,
        "planned_stop_risk_budget": ticket.planned_stop_risk_budget,
        "post_fill_stop_risk_limit": ticket.post_fill_stop_risk_limit,
        "selected_leverage": ticket.selected_leverage,
        "leverage_change_required": ticket.leverage_change_required,
        "reserved_margin": ticket.reserved_margin,
        "risk_reservation_basis": ticket.risk_reservation_basis,
        "margin_mode": ticket.margin_mode,
        "min_liquidation_distance_to_stop_distance_ratio": (
            ticket.min_liquidation_distance_to_stop_distance_ratio
        ),
        "projected_liquidation_price": ticket.projected_liquidation_price,
        "projected_liquidation_distance_to_stop_distance_ratio": (
            ticket.projected_liquidation_distance_to_stop_distance_ratio
        ),
        "risk_at_stop": ticket.risk_at_stop,
        "entry_order_type": ticket.entry_order_type.value,
        "entry_limit_price": ticket.entry_limit_price,
        "initial_stop_price": ticket.initial_stop_price,
        "take_profit_prices": [str(price) for price in ticket.take_profit_prices],
        "take_profit_quantities": [
            str(quantity) for quantity in ticket.take_profit_quantities
        ],
        "fact_digest": ticket.fact_digest,
        "decision_digest": ticket.decision_digest(),
        "status": ticket.status.value,
        "created_at_ms": ticket.created_at_ms,
        "expires_at_ms": ticket.expires_at_ms,
        "terminal_at_ms": None,
    }


def _ticket_from_row(row: RowMapping) -> TradeTicket:
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
        position_side=_position_side(row["position_side"]),
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
        capacity_claim_id=str(row["capacity_claim_id"]),
        created_at_ms=int(row["created_at_ms"]),
        expires_at_ms=int(row["expires_at_ms"]),
        entry_reference_price=Decimal(row["entry_reference_price"]),
        quantity=Decimal(row["quantity"]),
        notional=Decimal(row["notional"]),
        planned_stop_risk_budget=Decimal(row["planned_stop_risk_budget"]),
        post_fill_stop_risk_limit=Decimal(row["post_fill_stop_risk_limit"]),
        selected_leverage=int(row["selected_leverage"]),
        leverage_change_required=bool(row["leverage_change_required"]),
        reserved_margin=Decimal(row["reserved_margin"]),
        risk_reservation_basis=str(row["risk_reservation_basis"]),
        margin_mode=str(row["margin_mode"]),
        min_liquidation_distance_to_stop_distance_ratio=Decimal(
            row["min_liquidation_distance_to_stop_distance_ratio"]
        ),
        projected_liquidation_price=Decimal(row["projected_liquidation_price"]),
        projected_liquidation_distance_to_stop_distance_ratio=Decimal(
            row["projected_liquidation_distance_to_stop_distance_ratio"]
        ),
        risk_at_stop=Decimal(row["risk_at_stop"]),
        entry_order_type=EntryOrderType(str(row["entry_order_type"])),
        entry_limit_price=(
            None
            if row["entry_limit_price"] is None
            else Decimal(row["entry_limit_price"])
        ),
        initial_stop_price=Decimal(row["initial_stop_price"]),
        take_profit_prices=tuple(Decimal(value) for value in row["take_profit_prices"]),
        take_profit_quantities=tuple(
            Decimal(value) for value in row["take_profit_quantities"]
        ),
        status=TicketStatus(str(row["status"])),
    )


def _capacity_claim_values(claim: CapacityClaim) -> dict[str, object]:
    identity = claim.ticket_identity
    return {
        "capacity_claim_id": claim.capacity_claim_id,
        "ticket_id": identity.ticket_id,
        "signal_event_id": identity.signal_event_id,
        "exposure_episode_id": identity.exposure_episode_id,
        "strategy_group_id": identity.runtime.strategy_group_id,
        "strategy_version_id": identity.runtime.strategy_version_id,
        "event_spec_id": identity.runtime.event_spec_id,
        "runtime_profile_id": identity.runtime.runtime_profile_id,
        "owner_policy_id": claim.owner_policy_id,
        "owner_policy_version": claim.owner_policy_version,
        "runtime_scope_id": claim.runtime_scope_id,
        "runtime_scope_version": claim.runtime_scope_version,
        "account_id": identity.netting_domain.account_id,
        "venue_id": identity.netting_domain.venue_id,
        "exchange_instrument_id": (
            identity.netting_domain.exchange_instrument_id
        ),
        "position_side": identity.netting_domain.position_side,
        "netting_domain_key": identity.netting_domain.key(),
        "fact_digest": claim.fact_digest,
        "entry_admission_snapshot_digest": claim.entry_admission_snapshot_digest,
        "account_entry_health_digest": claim.account_entry_health_digest,
        "instrument_entry_health_digest": claim.instrument_entry_health_digest,
        "instrument_rules_projection_version": (
            claim.instrument_rules_projection_version
        ),
        "account_capacity_domain_key": claim.account_capacity_domain_key,
        "leverage_domain_key": claim.leverage_domain_key,
        "total_wallet_balance_at_claim": claim.total_wallet_balance_at_claim,
        "total_margin_balance_at_claim": claim.total_margin_balance_at_claim,
        "total_initial_margin_at_claim": claim.total_initial_margin_at_claim,
        "total_maintenance_margin_at_claim": claim.total_maintenance_margin_at_claim,
        "available_margin_at_claim": claim.available_margin_at_claim,
        "mark_price_at_claim": claim.mark_price_at_claim,
        "position_mode_at_claim": claim.position_mode_at_claim,
        "margin_mode_at_claim": claim.margin_mode_at_claim,
        "active_ticket_count_at_claim": claim.active_ticket_count_at_claim,
        "remaining_slots_at_claim": claim.remaining_slots_at_claim,
        "planned_stop_risk_fraction": claim.planned_stop_risk_fraction,
        "planned_stop_risk_budget": claim.planned_stop_risk_budget,
        "max_post_fill_stop_risk_overrun_fraction": (
            claim.max_post_fill_stop_risk_overrun_fraction
        ),
        "post_fill_stop_risk_limit": claim.post_fill_stop_risk_limit,
        "max_initial_margin_utilization": claim.max_initial_margin_utilization,
        "min_liquidation_distance_to_stop_distance_ratio": (
            claim.min_liquidation_distance_to_stop_distance_ratio
        ),
        "ticket_margin_budget": claim.ticket_margin_budget,
        "required_leverage": claim.required_leverage,
        "selected_leverage": claim.selected_leverage,
        "configured_leverage_at_claim": claim.configured_leverage_at_claim,
        "leverage_change_required": claim.leverage_change_required,
        "exchange_max_leverage": claim.exchange_max_leverage,
        "reserved_margin": claim.reserved_margin,
        "maintenance_margin_bracket_id": claim.maintenance_margin_bracket_id,
        "projected_liquidation_price": claim.projected_liquidation_price,
        "projected_liquidation_distance": claim.projected_liquidation_distance,
        "projected_liquidation_distance_to_stop_distance_ratio": (
            claim.projected_liquidation_distance_to_stop_distance_ratio
        ),
        "entry_reference_price": claim.entry_reference_price,
        "quantity": claim.quantity,
        "notional": claim.notional,
        "risk_at_stop": claim.risk_at_stop,
        "entry_order_type": claim.entry_order_type.value,
        "entry_limit_price": claim.entry_limit_price,
        "initial_stop_price": claim.initial_stop_price,
        "take_profit_prices": [str(value) for value in claim.take_profit_prices],
        "take_profit_quantities": [
            str(value) for value in claim.take_profit_quantities
        ],
        "decision_digest": claim.decision_digest,
        "created_at_ms": claim.created_at_ms,
        "expires_at_ms": claim.expires_at_ms,
    }


def _capacity_claim_from_row(row: RowMapping) -> CapacityClaim:
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
        position_side=_position_side(row["position_side"]),
    )
    return CapacityClaim(
        capacity_claim_id=str(row["capacity_claim_id"]),
        ticket_identity=TicketIdentity(
            ticket_id=str(row["ticket_id"]),
            exposure_episode_id=str(row["exposure_episode_id"]),
            signal_event_id=str(row["signal_event_id"]),
            runtime=runtime,
            netting_domain=domain,
        ),
        owner_policy_id=str(row["owner_policy_id"]),
        owner_policy_version=int(row["owner_policy_version"]),
        runtime_scope_id=str(row["runtime_scope_id"]),
        runtime_scope_version=int(row["runtime_scope_version"]),
        fact_digest=str(row["fact_digest"]),
        entry_admission_snapshot_digest=str(row["entry_admission_snapshot_digest"]),
        account_entry_health_digest=str(row["account_entry_health_digest"]),
        instrument_entry_health_digest=str(row["instrument_entry_health_digest"]),
        instrument_rules_projection_version=int(
            row["instrument_rules_projection_version"]
        ),
        account_capacity_domain_key=str(row["account_capacity_domain_key"]),
        leverage_domain_key=str(row["leverage_domain_key"]),
        total_wallet_balance_at_claim=Decimal(row["total_wallet_balance_at_claim"]),
        total_margin_balance_at_claim=Decimal(row["total_margin_balance_at_claim"]),
        total_initial_margin_at_claim=Decimal(row["total_initial_margin_at_claim"]),
        total_maintenance_margin_at_claim=Decimal(
            row["total_maintenance_margin_at_claim"]
        ),
        available_margin_at_claim=Decimal(row["available_margin_at_claim"]),
        mark_price_at_claim=Decimal(row["mark_price_at_claim"]),
        position_mode_at_claim=str(row["position_mode_at_claim"]),
        margin_mode_at_claim=str(row["margin_mode_at_claim"]),
        active_ticket_count_at_claim=int(row["active_ticket_count_at_claim"]),
        remaining_slots_at_claim=int(row["remaining_slots_at_claim"]),
        planned_stop_risk_fraction=Decimal(row["planned_stop_risk_fraction"]),
        planned_stop_risk_budget=Decimal(row["planned_stop_risk_budget"]),
        max_post_fill_stop_risk_overrun_fraction=Decimal(
            row["max_post_fill_stop_risk_overrun_fraction"]
        ),
        post_fill_stop_risk_limit=Decimal(row["post_fill_stop_risk_limit"]),
        max_initial_margin_utilization=Decimal(
            row["max_initial_margin_utilization"]
        ),
        min_liquidation_distance_to_stop_distance_ratio=Decimal(
            row["min_liquidation_distance_to_stop_distance_ratio"]
        ),
        ticket_margin_budget=Decimal(row["ticket_margin_budget"]),
        required_leverage=int(row["required_leverage"]),
        selected_leverage=int(row["selected_leverage"]),
        configured_leverage_at_claim=int(row["configured_leverage_at_claim"]),
        leverage_change_required=bool(row["leverage_change_required"]),
        exchange_max_leverage=int(row["exchange_max_leverage"]),
        reserved_margin=Decimal(row["reserved_margin"]),
        maintenance_margin_bracket_id=str(row["maintenance_margin_bracket_id"]),
        projected_liquidation_price=Decimal(row["projected_liquidation_price"]),
        projected_liquidation_distance=Decimal(row["projected_liquidation_distance"]),
        projected_liquidation_distance_to_stop_distance_ratio=Decimal(
            row["projected_liquidation_distance_to_stop_distance_ratio"]
        ),
        created_at_ms=int(row["created_at_ms"]),
        expires_at_ms=int(row["expires_at_ms"]),
        entry_reference_price=Decimal(row["entry_reference_price"]),
        quantity=Decimal(row["quantity"]),
        notional=Decimal(row["notional"]),
        risk_at_stop=Decimal(row["risk_at_stop"]),
        entry_order_type=EntryOrderType(str(row["entry_order_type"])),
        entry_limit_price=(
            None
            if row["entry_limit_price"] is None
            else Decimal(row["entry_limit_price"])
        ),
        initial_stop_price=Decimal(row["initial_stop_price"]),
        take_profit_prices=tuple(
            Decimal(value) for value in row["take_profit_prices"]
        ),
        take_profit_quantities=tuple(
            Decimal(value) for value in row["take_profit_quantities"]
        ),
        decision_digest=str(row["decision_digest"]),
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
        "entry_lane_held": aggregate.entry_lane_held,
        "position_qty": aggregate.position_qty,
        "average_fill_price": aggregate.average_fill_price,
        "protected_qty": aggregate.protected_qty,
        "entry_exchange_order_id": aggregate.entry_exchange_order_id,
        "initial_stop_exchange_order_id": aggregate.initial_stop_exchange_order_id,
        "active_stop_exchange_order_id": aggregate.active_stop_exchange_order_id,
        "active_stop_price": aggregate.active_stop_price,
        "tp1_exchange_order_id": aggregate.tp1_exchange_order_id,
        "tp1_target_qty": aggregate.tp1_target_qty,
        "tp1_filled_qty": aggregate.tp1_filled_qty,
        "break_even_floor_price": aggregate.break_even_floor_price,
        "pending_replaced_stop_exchange_order_id": (
            aggregate.pending_replaced_stop_exchange_order_id
        ),
        "pending_stop_price": aggregate.pending_stop_price,
        "pending_stop_watermark_ms": aggregate.pending_stop_watermark_ms,
        "runner_stop_watermark_ms": aggregate.runner_stop_watermark_ms,
        "pending_cancel_exchange_order_id": (
            aggregate.pending_cancel_exchange_order_id
        ),
        "exit_exchange_order_id": aggregate.exit_exchange_order_id,
        "review_id": aggregate.review_id,
        "updated_at_ms": updated_at_ms or aggregate.ticket.created_at_ms,
    }


def _aggregate_from_row(
    row: RowMapping,
    ticket: TradeTicket,
) -> TradeAggregate:
    return TradeAggregate(
        identity=ticket.identity,
        ticket=ticket,
        status=AggregateStatus(str(row["status"])),
        version=int(row["version"]),
        last_event_sequence=int(row["last_event_sequence"]),
        entry_lane_held=bool(row["entry_lane_held"]),
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
        active_stop_exchange_order_id=(
            None
            if row["active_stop_exchange_order_id"] is None
            else str(row["active_stop_exchange_order_id"])
        ),
        active_stop_price=(
            None
            if row["active_stop_price"] is None
            else Decimal(row["active_stop_price"])
        ),
        tp1_exchange_order_id=(
            None
            if row["tp1_exchange_order_id"] is None
            else str(row["tp1_exchange_order_id"])
        ),
        tp1_target_qty=Decimal(row["tp1_target_qty"]),
        tp1_filled_qty=Decimal(row["tp1_filled_qty"]),
        break_even_floor_price=(
            None
            if row["break_even_floor_price"] is None
            else Decimal(row["break_even_floor_price"])
        ),
        pending_replaced_stop_exchange_order_id=(
            None
            if row["pending_replaced_stop_exchange_order_id"] is None
            else str(row["pending_replaced_stop_exchange_order_id"])
        ),
        pending_stop_price=(
            None
            if row["pending_stop_price"] is None
            else Decimal(row["pending_stop_price"])
        ),
        pending_stop_watermark_ms=(
            None
            if row["pending_stop_watermark_ms"] is None
            else int(row["pending_stop_watermark_ms"])
        ),
        runner_stop_watermark_ms=(
            None
            if row["runner_stop_watermark_ms"] is None
            else int(row["runner_stop_watermark_ms"])
        ),
        pending_cancel_exchange_order_id=(
            None
            if row["pending_cancel_exchange_order_id"] is None
            else str(row["pending_cancel_exchange_order_id"])
        ),
        exit_exchange_order_id=(
            None
            if row["exit_exchange_order_id"] is None
            else str(row["exit_exchange_order_id"])
        ),
        review_id=None if row["review_id"] is None else str(row["review_id"]),
    )


def _event_ticket_id(event: TradeEvent) -> str:
    if isinstance(event, TicketIssued):
        return event.ticket.identity.ticket_id
    return event.ticket_id


def _same_monitor_state(
    current: RowMapping,
    requested: MonitorStateRecord,
) -> bool:
    return all(
        current[field] == getattr(requested, field)
        for field in (
            "owner_status",
            "summary",
            "intervention",
            "ticket_id",
            "incident_id",
        )
    )


def _position_side(value: object) -> Literal["long", "short"]:
    normalized = str(value)
    if normalized == "long":
        return "long"
    if normalized == "short":
        return "short"
    raise RuntimeError(f"invalid persisted position side: {normalized!r}")
