"""SQLAlchemy Core repositories for the clean trading-kernel schema."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter, ValidationError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.elements import ColumnElement

from src.trading_kernel.application.ports import (
    AccountExposureSnapshot,
    AggregateVersionConflict,
    BudgetReservationRecord,
    EntryLaneSnapshot,
    MonitorStateRecord,
    OwnerControlRepository,
    OwnerPolicySnapshot,
    RuntimeIncidentRecord,
    TradeReviewRecord,
)
from src.trading_kernel.application.reconciliation_scheduler import (
    ReconciliationActionCandidate,
    ReconciliationActionKind,
)
from src.trading_kernel.domain.admission_decision import AdmissionDecision
from src.trading_kernel.domain.aggregate import (
    RECONCILIATION_POSITION_STATUSES,
    AggregateStatus,
    TradeAggregate,
)
from src.trading_kernel.domain.capacity import CapacityClaim, FamilyTicketLimits
from src.trading_kernel.domain.commands import (
    CommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.cross_margin_stress import CrossMarginStressEvidence
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionOwnership,
    OwnedPositionProjection,
)
from src.trading_kernel.domain.events import (
    PERSISTED_TRADE_EVENT_MODELS,
    TicketIssued,
    TradeEvent,
)
from src.trading_kernel.domain.exposure_family import ExposureFamily
from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)
from src.trading_kernel.domain.incident_blocking import (
    EntryBlockScope,
    canonical_entry_block_key,
)
from src.trading_kernel.domain.order_attribution import (
    ConditionalOrderExpectation,
    OrderNamespace,
    OrderRole,
    TicketOrderReference,
)
from src.trading_kernel.domain.owner_control import (
    ControlOperationState,
    OwnerAuthorization,
    OwnerControlOperation,
    StrategyEntryControl,
    StrategyEntryState,
)
from src.trading_kernel.domain.owner_policy import OwnerPolicyScope
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.post_fill_risk import (
    PostFillDisposition,
    PostFillRiskStatus,
)
from src.trading_kernel.domain.shadow_outcome import (
    ShadowOutcomeClaim,
    ShadowOutcomeProjection,
    ShadowOutcomeSpec,
)
from src.trading_kernel.domain.ticket import EntryOrderType, TicketStatus, TradeTicket
from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    admission_decisions,
    budget_reservations,
    capacity_claims,
    entry_lane_current,
    exchange_commands,
    monitor_current,
    monitor_events,
    owner_authorizations,
    owner_control_operation_events,
    owner_control_operations_current,
    owner_policy_current,
    owner_policy_events,
    positions_current,
    runtime_capabilities_current,
    runtime_incidents,
    runtime_profiles,
    schema_metadata,
    shadow_outcomes_current,
    strategy_entry_control_events,
    strategy_entry_controls_current,
    trade_aggregates,
    trade_events,
    trade_reviews,
    trade_tickets,
)

_EVENT_MODELS = {
    event_type.__name__: event_type
    for event_type in PERSISTED_TRADE_EVENT_MODELS
}
_COMMAND_PAYLOAD_ADAPTER: TypeAdapter[CommandPayload] = TypeAdapter(CommandPayload)


def _strategy_control_from_row(row: RowMapping) -> StrategyEntryControl:
    return StrategyEntryControl(
        strategy_group_id=str(row["strategy_group_id"]),
        entry_state=StrategyEntryState(str(row["entry_state"])),
        control_version=int(row["control_version"]),
        last_event_id=str(row["last_event_id"]),
        reason=str(row["reason"]),
        updated_at_ms=int(row["updated_at_ms"]),
    )


def _operation_from_row(row: RowMapping) -> OwnerControlOperation:
    return OwnerControlOperation(
        authorization_id=str(row["authorization_id"]),
        operation_kind="flatten_all",
        state=ControlOperationState(str(row["state"])),
        version=int(row["version"]),
        runtime_profile_id=str(row["runtime_profile_id"]),
        venue_id=str(row["venue_id"]),
        account_id=str(row["account_id"]),
        target_ticket_ids=tuple(str(item) for item in row["target_ticket_ids"]),
        snapshot_digest=str(row["snapshot_digest"]),
        first_blocker=(
            None if row["first_blocker"] is None else str(row["first_blocker"])
        ),
        claimed_by=None if row["claimed_by"] is None else str(row["claimed_by"]),
        lease_until_ms=(
            None if row["lease_until_ms"] is None else int(row["lease_until_ms"])
        ),
        created_at_ms=int(row["created_at_ms"]),
        updated_at_ms=int(row["updated_at_ms"]),
    )


def _operation_values(operation: OwnerControlOperation) -> dict[str, object]:
    values = operation.model_dump(mode="json")
    values["state"] = operation.state.value
    values["target_ticket_ids"] = list(operation.target_ticket_ids)
    return values


def _owner_policy_from_row(row: RowMapping | dict[str, object]) -> OwnerPolicySnapshot:
    supported_margin_mode = str(row["supported_margin_mode"])
    if supported_margin_mode != "cross":
        raise RuntimeError("Owner policy has unsupported margin mode")
    return OwnerPolicySnapshot(
        owner_policy_id=str(row["owner_policy_id"]),
        policy_version=int(str(row["policy_version"])),
        enabled=bool(row["enabled"]),
        new_entry_submit_enabled=bool(row["new_entry_submit_enabled"]),
        priority_rank=int(str(row["priority_rank"])),
        max_concurrent_tickets=int(str(row["max_concurrent_tickets"])),
        family_ticket_limits=FamilyTicketLimits.model_validate(
            row["family_ticket_limits"]
        ),
        max_ticket_stop_risk_fraction=Decimal(str(row["max_ticket_stop_risk_fraction"])),
        max_gross_stop_risk_fraction=Decimal(str(row["max_gross_stop_risk_fraction"])),
        max_ticket_initial_margin_fraction=Decimal(
            str(row["max_ticket_initial_margin_fraction"])
        ),
        max_gross_initial_margin_utilization=Decimal(
            str(row["max_gross_initial_margin_utilization"])
        ),
        directional_stop_risk_limit_fraction=Decimal(
            str(row["directional_stop_risk_limit_fraction"])
        ),
        min_materialization_ratio=Decimal(str(row["min_materialization_ratio"])),
        max_leverage=int(str(row["max_leverage"])),
        supported_margin_mode=cast(Literal["cross"], supported_margin_mode),
        post_stop_stress_multiple=Decimal(str(row["post_stop_stress_multiple"])),
        max_post_fill_stop_risk_overrun_fraction=Decimal(
            str(row["max_post_fill_stop_risk_overrun_fraction"])
        ),
        scope=_owner_policy_scope(row["scope"]),
    )


def _owner_policy_scope(value: object) -> OwnerPolicyScope | None:
    try:
        return OwnerPolicyScope.model_validate(value)
    except ValidationError:
        return None


class HistoricalTerminalTicket(BaseModel):
    """Read-only terminal Ticket projection that has no v4 action authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    capacity_claim_id: str
    exposure_family: ExposureFamily
    terminal_at_ms: int


class HistoricalTerminalCapacityClaim(BaseModel):
    """Read-only terminal Claim projection that has no v4 action authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capacity_claim_id: str
    ticket_id: str
    exposure_family: ExposureFamily


def _accepted_exchange_order_id(row: RowMapping) -> str:
    payload = row["result_payload"]
    if not isinstance(payload, dict):
        raise TypeError("accepted command lacks a typed result payload")
    exchange_order_id = str(payload.get("exchange_order_id") or "").strip()
    if not exchange_order_id:
        raise RuntimeError("accepted command lacks exchange order identity")
    return exchange_order_id


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
        if row is None or _is_historical_terminal_ticket(row):
            return None
        return _ticket_from_row(row)

    async def get_historical_terminal(
        self,
        ticket_id: str,
    ) -> HistoricalTerminalTicket | None:
        result = await self._connection.execute(
            sa.select(
                trade_tickets.c.ticket_id,
                trade_tickets.c.capacity_claim_id,
                trade_tickets.c.exposure_family,
                trade_tickets.c.terminal_at_ms,
            ).where(
                trade_tickets.c.ticket_id == ticket_id,
                trade_tickets.c.terminal_at_ms.is_not(None),
                trade_tickets.c.exposure_family.is_not(None),
                trade_tickets.c.minimum_stop_risk_budget.is_(None),
            )
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return HistoricalTerminalTicket(
            ticket_id=str(row["ticket_id"]),
            capacity_claim_id=str(row["capacity_claim_id"]),
            exposure_family=_exposure_family(row["exposure_family"]),
            terminal_at_ms=int(row["terminal_at_ms"]),
        )

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

    async def release_active_netting_domain(
        self,
        ticket_id: str,
        *,
        netting_domain_key: str,
    ) -> None:
        updated = await self._connection.execute(
            sa.update(trade_tickets)
            .where(
                trade_tickets.c.ticket_id == ticket_id,
                trade_tickets.c.active_netting_domain_key == netting_domain_key,
            )
            .values(active_netting_domain_key=None)
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict("active Netting Domain is missing during release")

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

    async def list_active_ticket_ids(
        self,
        *,
        venue_id: str,
        account_id: str,
        limit: int,
    ) -> tuple[str, ...]:
        if not venue_id.strip() or not account_id.strip():
            raise ValueError("active Ticket scope identities must be non-blank")
        if limit <= 0 or limit > 3:
            raise ValueError("active Ticket selection limit must be 1 through 3")
        rows = (
            await self._connection.execute(
                sa.select(trade_aggregates.c.ticket_id)
                .join(
                    trade_tickets,
                    trade_tickets.c.ticket_id == trade_aggregates.c.ticket_id,
                )
                .where(
                    trade_tickets.c.venue_id == venue_id,
                    trade_tickets.c.account_id == account_id,
                    trade_tickets.c.terminal_at_ms.is_(None),
                )
                .order_by(trade_aggregates.c.ticket_id)
                .limit(limit + 1)
            )
        ).scalars().all()
        if len(rows) > limit:
            raise RuntimeError("active Ticket set exceeds Controlled Exit bound")
        return tuple(str(ticket_id) for ticket_id in rows)

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

    async def claim_next_critical_reconciliation_work(
        self,
        *,
        now_ms: int,
    ) -> TradeAggregate | None:
        """Select one due safety action; the caller performs venue I/O after commit."""

        if now_ms <= 0:
            raise ValueError("reconciliation selector requires positive now_ms")
        due_at = sa.func.coalesce(
            trade_aggregates.c.reconciliation_due_at_ms,
            trade_aggregates.c.updated_at_ms,
        )
        critical_statuses = (
            AggregateStatus.POST_FILL_RISK_PENDING.value,
            *(status.value for status in RECONCILIATION_POSITION_STATUSES),
        )
        result = await self._connection.execute(
            sa.select(trade_aggregates.c.ticket_id)
            .where(
                trade_aggregates.c.status.in_(critical_statuses),
                due_at <= now_ms,
            )
            .order_by(
                due_at,
                trade_aggregates.c.ticket_id,
            )
            .with_for_update(skip_locked=True, of=trade_aggregates)
            .limit(1)
        )
        ticket_id = result.scalar_one_or_none()
        return None if ticket_id is None else await self.get(str(ticket_id))

    async def claim_next_routine_reconciliation_work(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
    ) -> TradeAggregate | None:
        """Select one due closure action after safety and overdue certification."""

        if not worker_id.strip():
            raise ValueError("reconciliation claim worker must be non-blank")
        if now_ms <= 0 or lease_until_ms <= now_ms:
            raise ValueError("reconciliation claim lease must be future-dated")
        due_at = sa.func.coalesce(
            trade_aggregates.c.reconciliation_due_at_ms,
            trade_aggregates.c.updated_at_ms,
        )
        routine_statuses = (
            AggregateStatus.SETTLEMENT_PENDING.value,
            AggregateStatus.REVIEW_PENDING.value,
        )
        result = await self._connection.execute(
            sa.select(trade_aggregates.c.ticket_id)
            .where(
                trade_aggregates.c.status.in_(routine_statuses),
                due_at <= now_ms,
            )
            .order_by(due_at, trade_aggregates.c.ticket_id)
            .with_for_update(skip_locked=True, of=trade_aggregates)
            .limit(1)
        )
        ticket_id = result.scalar_one_or_none()
        if ticket_id is None:
            return None
        leased = await self._connection.execute(
            sa.update(trade_aggregates)
            .where(
                trade_aggregates.c.ticket_id == ticket_id,
                due_at <= now_ms,
            )
            .values(reconciliation_due_at_ms=lease_until_ms)
        )
        if leased.rowcount != 1:
            return None
        return await self.get(str(ticket_id))

    async def peek_next_routine_reconciliation_action(
        self,
        *,
        now_ms: int,
    ) -> ReconciliationActionCandidate | None:
        if now_ms <= 0:
            raise ValueError("reconciliation selector requires positive now_ms")
        due_at = sa.func.coalesce(
            trade_aggregates.c.reconciliation_due_at_ms,
            trade_aggregates.c.updated_at_ms,
        )
        row = (
            await self._connection.execute(
                sa.select(
                    trade_aggregates.c.ticket_id,
                    trade_aggregates.c.status,
                    due_at.label("due_at_ms"),
                )
                .where(
                    trade_aggregates.c.status.in_(
                        (
                            AggregateStatus.SETTLEMENT_PENDING.value,
                            AggregateStatus.REVIEW_PENDING.value,
                        )
                    ),
                    due_at <= now_ms,
                )
                .order_by(due_at, trade_aggregates.c.ticket_id)
                .limit(1)
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        status = AggregateStatus(str(row["status"]))
        return ReconciliationActionCandidate(
            kind=(
                ReconciliationActionKind.SETTLEMENT
                if status is AggregateStatus.SETTLEMENT_PENDING
                else ReconciliationActionKind.REVIEW
            ),
            stable_identity=str(row["ticket_id"]),
            due_at_ms=int(row["due_at_ms"]),
            max_wait_ms=60_000,
        )

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
            if await self._tickets.get_historical_terminal(ticket_id) is not None:
                return None
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

    async def list_order_references(
        self,
        ticket_id: str,
    ) -> tuple[TicketOrderReference, ...]:
        ticket_result = await self._connection.execute(
            sa.select(
                trade_tickets.c.exchange_instrument_id,
                trade_tickets.c.position_side,
            ).where(trade_tickets.c.ticket_id == ticket_id)
        )
        ticket_row = ticket_result.mappings().one_or_none()
        if ticket_row is None:
            raise RuntimeError("order attribution Ticket does not exist")
        result = await self._connection.execute(
            sa.select(exchange_commands).where(
                exchange_commands.c.ticket_id == ticket_id,
                exchange_commands.c.status.in_(
                    (
                        ExchangeCommandStatus.ACCEPTED.value,
                        ExchangeCommandStatus.RECONCILED_ACCEPTED.value,
                    )
                ),
            ).order_by(
                exchange_commands.c.created_at_ms,
                exchange_commands.c.command_id,
            )
        )
        references: list[TicketOrderReference] = []
        for row in result.mappings():
            kind = ExchangeCommandKind(str(row["command_kind"]))
            if kind in {
                ExchangeCommandKind.CANCEL_ORDER,
                ExchangeCommandKind.SET_LEVERAGE,
            }:
                continue
            payload = _COMMAND_PAYLOAD_ADAPTER.validate_python(row["request_payload"])
            if not isinstance(payload, OrderCommandPayload):
                raise TypeError("accepted order command has a non-order payload")
            if payload.order_type in {"stop_market", "take_profit_market"}:
                namespace = OrderNamespace.CONDITIONAL
                conditional_expectation: ConditionalOrderExpectation | None = (
                    ConditionalOrderExpectation(
                        exchange_instrument_id=str(ticket_row["exchange_instrument_id"]),
                        position_side=_position_side(ticket_row["position_side"]),
                        side=payload.side,
                        order_type=cast(
                            Literal["stop_market", "take_profit_market"],
                            payload.order_type,
                        ),
                        quantity=payload.quantity,
                    )
                )
            else:
                namespace = OrderNamespace.REGULAR
                conditional_expectation = None
            references.append(
                TicketOrderReference(
                    command_id=str(row["command_id"]),
                    command_kind=kind,
                    role=(
                        OrderRole.ENTRY
                        if kind is ExchangeCommandKind.ENTRY
                        else OrderRole.EXIT
                    ),
                    namespace=namespace,
                    venue_client_order_id=str(row["venue_client_order_id"] or ""),
                    submitted_exchange_order_id=_accepted_exchange_order_id(row),
                    conditional_expectation=conditional_expectation,
                )
            )
        return tuple(references)

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

    async def record_leverage_result(
        self,
        *,
        command_id: str,
        worker_id: str,
        result: SetLeverageCommandResult,
    ) -> None:
        updated = await self._connection.execute(
            sa.update(exchange_commands)
            .where(
                exchange_commands.c.command_id == command_id,
                exchange_commands.c.command_kind == ExchangeCommandKind.SET_LEVERAGE.value,
                exchange_commands.c.status == ExchangeCommandStatus.CLAIMED.value,
                exchange_commands.c.claim_owner == worker_id,
            )
            .values(
                status=ExchangeCommandStatus.ACCEPTED.value,
                result_payload=result.model_dump(mode="json"),
                completed_at_ms=result.leverage_verified_at_ms,
                lease_until_ms=None,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict("leverage command claim changed before result")

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

    async def mark_prepared_superseded(
        self,
        *,
        command_id: str,
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
                exchange_commands.c.status == ExchangeCommandStatus.PREPARED.value,
            )
            .values(
                status=ExchangeCommandStatus.SUPERSEDED.value,
                result_payload={
                    "status": ExchangeCommandStatus.SUPERSEDED.value,
                    "reason": normalized_reason,
                    "observed_at_ms": observed_at_ms,
                },
                completed_at_ms=observed_at_ms,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict(
                "prepared command changed before supersession"
            )

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

    async def reconcile_unknown_leverage_confirmed(
        self,
        *,
        command_id: str,
        result: SetLeverageCommandResult,
    ) -> None:
        updated = await self._connection.execute(
            sa.update(exchange_commands)
            .where(
                exchange_commands.c.command_id == command_id,
                exchange_commands.c.command_kind == ExchangeCommandKind.SET_LEVERAGE.value,
                exchange_commands.c.status == ExchangeCommandStatus.OUTCOME_UNKNOWN.value,
            )
            .values(
                status=ExchangeCommandStatus.RECONCILED_ACCEPTED.value,
                result_payload=result.model_dump(mode="json"),
                completed_at_ms=result.leverage_verified_at_ms,
            )
        )
        if updated.rowcount != 1:
            raise AggregateVersionConflict(
                "unknown leverage command changed before confirmation reconciliation"
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
            venue_client_order_id=(
                None
                if row["venue_client_order_id"] is None
                else str(row["venue_client_order_id"])
            ),
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

    async def get_latest_for_account(
        self,
        *,
        venue_id: str,
        account_id: str,
    ) -> CapacityClaim | None:
        result = await self._connection.execute(
            sa.select(capacity_claims)
            .where(
                capacity_claims.c.venue_id == venue_id,
                capacity_claims.c.account_id == account_id,
            )
            .order_by(
                capacity_claims.c.created_at_ms.desc(),
                capacity_claims.c.capacity_claim_id,
            )
            .limit(1)
        )
        row = result.mappings().one_or_none()
        if row is None or row["minimum_stop_risk_budget"] is None:
            return None
        return _capacity_claim_from_row(row)

    async def get_historical_terminal(
        self,
        capacity_claim_id: str,
    ) -> HistoricalTerminalCapacityClaim | None:
        result = await self._connection.execute(
            sa.select(
                capacity_claims.c.capacity_claim_id,
                capacity_claims.c.ticket_id,
                capacity_claims.c.exposure_family,
            )
            .join(
                trade_tickets,
                trade_tickets.c.ticket_id == capacity_claims.c.ticket_id,
            )
            .where(
                capacity_claims.c.capacity_claim_id == capacity_claim_id,
                trade_tickets.c.terminal_at_ms.is_not(None),
                capacity_claims.c.exposure_family.is_not(None),
                capacity_claims.c.minimum_stop_risk_budget.is_(None),
            )
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return HistoricalTerminalCapacityClaim(
            capacity_claim_id=str(row["capacity_claim_id"]),
            ticket_id=str(row["ticket_id"]),
            exposure_family=_exposure_family(row["exposure_family"]),
        )

    async def _get(
        self,
        predicate: sa.ColumnElement[bool],
    ) -> CapacityClaim | None:
        result = await self._connection.execute(
            sa.select(capacity_claims).where(predicate)
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        if row["minimum_stop_risk_budget"] is None:
            historical = await self.get_historical_terminal(
                str(row["capacity_claim_id"])
            )
            if historical is not None:
                return None
        return _capacity_claim_from_row(row)


class PostgresAdmissionDecisionRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, decision: AdmissionDecision) -> None:
        await self._connection.execute(
            sa.insert(admission_decisions).values(
                _admission_decision_values(decision)
            )
        )

    async def get_for_signal(
        self,
        signal_event_id: str,
    ) -> AdmissionDecision | None:
        row = (
            await self._connection.execute(
                sa.select(admission_decisions).where(
                    admission_decisions.c.signal_event_id == signal_event_id
                )
            )
        ).mappings().one_or_none()
        return None if row is None else _admission_decision_from_row(row)

    async def list_recent(
        self,
        *,
        limit: int,
    ) -> tuple[AdmissionDecision, ...]:
        if limit <= 0 or limit > 256:
            raise ValueError("AdmissionDecision limit must be between 1 and 256")
        rows = (
            await self._connection.execute(
                sa.select(admission_decisions)
                .order_by(
                    admission_decisions.c.decided_at_ms.desc(),
                    admission_decisions.c.admission_decision_id,
                )
                .limit(limit)
            )
        ).mappings()
        return tuple(_admission_decision_from_row(row) for row in rows)


class PostgresShadowOutcomeRepository:
    """Bounded current projection for immutable rejected-admission evidence."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add_pending(self, spec: ShadowOutcomeSpec) -> None:
        statement = pg_insert(shadow_outcomes_current).values(
            _shadow_outcome_pending_values(spec)
        )
        await self._connection.execute(
            statement.on_conflict_do_nothing(
                index_elements=[shadow_outcomes_current.c.signal_event_id]
            )
        )

    async def claim_one_due(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
    ) -> ShadowOutcomeClaim | None:
        row = (
            await self._connection.execute(
                sa.select(shadow_outcomes_current)
                .where(
                    sa.or_(
                        sa.and_(
                            shadow_outcomes_current.c.status == "pending",
                            shadow_outcomes_current.c.horizon_end_ms <= now_ms,
                        ),
                        sa.and_(
                            shadow_outcomes_current.c.status == "claimed",
                            shadow_outcomes_current.c.lease_until_ms <= now_ms,
                        ),
                    )
                )
                .order_by(
                    shadow_outcomes_current.c.horizon_end_ms,
                    shadow_outcomes_current.c.shadow_outcome_id,
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        shadow_id = str(row["shadow_outcome_id"])
        claim_token = f"shadow-claim:{uuid4().hex}"
        projection_version = int(row["projection_version"]) + 1
        await self._connection.execute(
            sa.update(shadow_outcomes_current)
            .where(shadow_outcomes_current.c.shadow_outcome_id == shadow_id)
            .values(
                status="claimed",
                claim_owner=worker_id,
                claim_token=claim_token,
                lease_until_ms=lease_until_ms,
                projection_version=projection_version,
            )
        )
        return ShadowOutcomeClaim(
            spec=_shadow_outcome_spec_from_row(row),
            claim_owner=worker_id,
            claim_token=claim_token,
            projection_version=projection_version,
            lease_until_ms=lease_until_ms,
        )

    async def complete(
        self,
        *,
        claim: ShadowOutcomeClaim,
        projection: ShadowOutcomeProjection,
        completed_at_ms: int,
    ) -> None:
        if projection.evaluation_kind != claim.spec.evaluation_kind:
            raise ValueError("unsupported Shadow evaluation kind")
        if any(
            value is None
            for value in (
                projection.max_favorable_price,
                projection.max_adverse_price,
                projection.mfe_r,
                projection.mae_r,
                projection.observed_through_ms,
            )
        ):
            raise ValueError("completed Shadow projection must be complete")
        result = await self._connection.execute(
            sa.update(shadow_outcomes_current)
            .where(
                shadow_outcomes_current.c.shadow_outcome_id
                == claim.spec.shadow_outcome_id,
                shadow_outcomes_current.c.status == "claimed",
                shadow_outcomes_current.c.claim_owner == claim.claim_owner,
                shadow_outcomes_current.c.claim_token == claim.claim_token,
                shadow_outcomes_current.c.projection_version
                == claim.projection_version,
                shadow_outcomes_current.c.lease_until_ms == claim.lease_until_ms,
            )
            .values(
                status="completed",
                claim_owner=None,
                claim_token=None,
                lease_until_ms=None,
                max_favorable_price=projection.max_favorable_price,
                max_adverse_price=projection.max_adverse_price,
                mfe_r=projection.mfe_r,
                mae_r=projection.mae_r,
                observed_through_ms=projection.observed_through_ms,
                completion_reason=(
                    "sor_path_observed"
                    if claim.spec.evaluation_kind == "sor_path_observation_v1"
                    else "fixed_horizon_observed"
                ),
                first_path=projection.first_path,
                first_path_at_ms=projection.first_path_at_ms,
                observed_bar_count=projection.observed_bar_count,
                completed_at_ms=completed_at_ms,
                projection_version=shadow_outcomes_current.c.projection_version + 1,
            )
        )
        await self._require_claim_affected_or_terminal(claim, result.rowcount)

    async def mark_unavailable(
        self,
        *,
        claim: ShadowOutcomeClaim,
        reason: str,
        completed_at_ms: int,
    ) -> None:
        normalized_reason = str(reason or "").strip()
        if not normalized_reason:
            raise ValueError("unavailable Shadow reason must be non-blank")
        result = await self._connection.execute(
            sa.update(shadow_outcomes_current)
            .where(
                shadow_outcomes_current.c.shadow_outcome_id
                == claim.spec.shadow_outcome_id,
                shadow_outcomes_current.c.status == "claimed",
                shadow_outcomes_current.c.claim_owner == claim.claim_owner,
                shadow_outcomes_current.c.claim_token == claim.claim_token,
                shadow_outcomes_current.c.projection_version
                == claim.projection_version,
                shadow_outcomes_current.c.lease_until_ms == claim.lease_until_ms,
            )
            .values(
                status="unavailable",
                claim_owner=None,
                claim_token=None,
                lease_until_ms=None,
                completion_reason=normalized_reason,
                completed_at_ms=completed_at_ms,
                projection_version=shadow_outcomes_current.c.projection_version + 1,
            )
        )
        await self._require_claim_affected_or_terminal(claim, result.rowcount)

    async def release_expired_claim(
        self,
        *,
        claim: ShadowOutcomeClaim,
    ) -> None:
        result = await self._connection.execute(
            sa.update(shadow_outcomes_current)
            .where(
                shadow_outcomes_current.c.shadow_outcome_id
                == claim.spec.shadow_outcome_id,
                shadow_outcomes_current.c.status == "claimed",
                shadow_outcomes_current.c.claim_owner == claim.claim_owner,
                shadow_outcomes_current.c.claim_token == claim.claim_token,
                shadow_outcomes_current.c.projection_version
                == claim.projection_version,
                shadow_outcomes_current.c.lease_until_ms == claim.lease_until_ms,
            )
            .values(
                status="pending",
                claim_owner=None,
                claim_token=None,
                lease_until_ms=None,
                projection_version=shadow_outcomes_current.c.projection_version + 1,
            )
        )
        await self._require_claim_affected_or_terminal(claim, result.rowcount)

    async def _require_claim_affected_or_terminal(
        self,
        claim: ShadowOutcomeClaim,
        rowcount: int,
    ) -> None:
        if rowcount == 1:
            return
        row = (
            await self._connection.execute(
                sa.select(shadow_outcomes_current.c.status).where(
                    shadow_outcomes_current.c.shadow_outcome_id
                    == claim.spec.shadow_outcome_id
                )
            )
        ).mappings().one_or_none()
        if row is not None and str(row["status"]) in {"completed", "unavailable"}:
            return
        raise RuntimeError("lost Shadow claim")


class PostgresIncidentRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, incident: RuntimeIncidentRecord) -> None:
        await self._connection.execute(
            pg_insert(runtime_incidents)
            .values(**incident.model_dump(mode="json"))
            .on_conflict_do_nothing(index_elements=[runtime_incidents.c.incident_id])
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

    async def resolve_all_open_for_ticket(
        self,
        ticket_id: str,
        *,
        resolved_at_ms: int,
        resolved_by_event_id: str,
    ) -> None:
        del resolved_by_event_id
        await self._connection.execute(
            sa.update(runtime_incidents)
            .where(
                runtime_incidents.c.ticket_id == ticket_id,
                runtime_incidents.c.status == "open",
            )
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
            "venue_reported_liquidation_price": (
                snapshot.venue_reported_liquidation_price
            ),
            "venue_reported_liquidation_observation_status": (
                snapshot.venue_reported_liquidation_observation_status
            ),
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
            venue_reported_liquidation_price=(
                None
                if row["venue_reported_liquidation_price"] is None
                else Decimal(row["venue_reported_liquidation_price"])
            ),
            venue_reported_liquidation_observation_status=cast(
                Literal["valid", "missing", "invalid"],
                str(row["venue_reported_liquidation_observation_status"]),
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

    async def get(self, review_id: str) -> TradeReviewRecord | None:
        result = await self._connection.execute(
            sa.select(trade_reviews).where(
                trade_reviews.c.review_id == review_id
            )
        )
        row = result.mappings().one_or_none()
        return None if row is None else TradeReviewRecord.model_validate(row)

    async def get_for_ticket(self, ticket_id: str) -> TradeReviewRecord | None:
        result = await self._connection.execute(
            sa.select(trade_reviews)
            .join(
                trade_aggregates,
                sa.and_(
                    trade_aggregates.c.ticket_id == trade_reviews.c.ticket_id,
                    trade_aggregates.c.review_id == trade_reviews.c.review_id,
                ),
            )
            .where(trade_reviews.c.ticket_id == ticket_id)
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
            current = MonitorStateRecord.model_validate(current_row)
            if state.updated_at_ms <= current.updated_at_ms:
                return current
            await self._connection.execute(
                sa.update(monitor_current)
                .where(monitor_current.c.monitor_key == state.monitor_key)
                .values(updated_at_ms=state.updated_at_ms)
            )
            return current.model_copy(
                update={"updated_at_ms": state.updated_at_ms}
            )

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


class PostgresOwnerControlRepository(OwnerControlRepository):
    """Exact bounded PostgreSQL authority for Owner control transitions."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def get_strategy_control(
        self,
        strategy_group_id: str,
        *,
        for_update: bool = False,
    ) -> StrategyEntryControl | None:
        statement = sa.select(strategy_entry_controls_current).where(
            strategy_entry_controls_current.c.strategy_group_id == strategy_group_id
        )
        if for_update:
            statement = statement.with_for_update(of=strategy_entry_controls_current)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        return None if row is None else _strategy_control_from_row(row)

    async def list_strategy_controls(self) -> tuple[StrategyEntryControl, ...]:
        rows = (
            await self._connection.execute(
                sa.select(strategy_entry_controls_current).order_by(
                    strategy_entry_controls_current.c.strategy_group_id
                )
            )
        ).mappings()
        return tuple(_strategy_control_from_row(row) for row in rows)

    async def add_authorization(self, authorization: OwnerAuthorization) -> None:
        await self._connection.execute(
            sa.insert(owner_authorizations).values(
                **authorization.model_dump(mode="json")
            )
        )

    async def get_authorization_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> OwnerAuthorization | None:
        row = (
            await self._connection.execute(
                sa.select(owner_authorizations).where(
                    owner_authorizations.c.idempotency_key == idempotency_key
                )
            )
        ).mappings().one_or_none()
        return None if row is None else OwnerAuthorization.model_validate(row)

    async def save_strategy_control(
        self,
        *,
        current: StrategyEntryControl,
        authorization_id: str,
        operation: Literal["pause", "resume"],
        payload: dict[str, JsonValue],
    ) -> None:
        await self._connection.execute(
            sa.insert(strategy_entry_control_events).values(
                strategy_entry_control_event_id=current.last_event_id,
                strategy_group_id=current.strategy_group_id,
                control_version=current.control_version,
                operation=operation,
                target_state=current.entry_state.value,
                authorization_id=authorization_id,
                reason=current.reason,
                payload=payload,
                created_at_ms=current.updated_at_ms,
            )
        )
        result = await self._connection.execute(
            sa.update(strategy_entry_controls_current)
            .where(
                strategy_entry_controls_current.c.strategy_group_id
                == current.strategy_group_id,
                strategy_entry_controls_current.c.control_version
                == current.control_version - 1,
            )
            .values(
                entry_state=current.entry_state.value,
                control_version=current.control_version,
                last_event_id=current.last_event_id,
                reason=current.reason,
                updated_at_ms=current.updated_at_ms,
            )
        )
        if result.rowcount != 1:
            raise AggregateVersionConflict("Strategy control version changed")

    async def set_global_entry_enabled(
        self,
        *,
        owner_policy_id: str,
        expected_version: int,
        enabled: bool,
        authorization_id: str,
        reason: str,
        updated_at_ms: int,
    ) -> OwnerPolicySnapshot:
        row = (
            await self._connection.execute(
                sa.select(owner_policy_current)
                .where(owner_policy_current.c.owner_policy_id == owner_policy_id)
                .with_for_update(of=owner_policy_current)
            )
        ).mappings().one_or_none()
        if row is None:
            raise RuntimeError("Owner policy is missing")
        if int(row["policy_version"]) != expected_version:
            raise AggregateVersionConflict("Owner policy version changed")
        if bool(row["new_entry_submit_enabled"]) == enabled:
            return _owner_policy_from_row(row)
        next_version = expected_version + 1
        await self._connection.execute(
            sa.insert(owner_policy_events).values(
                owner_policy_event_id=f"owner-policy-event:{uuid4().hex}",
                owner_policy_id=owner_policy_id,
                policy_version=next_version,
                operation=(
                    "owner_control_entry_resume"
                    if enabled
                    else "owner_control_entry_pause"
                ),
                payload={
                    "authorization_id": authorization_id,
                    "reason": reason,
                    "new_entry_submit_enabled": enabled,
                },
                created_at_ms=updated_at_ms,
            )
        )
        await self._connection.execute(
            sa.update(owner_policy_current)
            .where(owner_policy_current.c.owner_policy_id == owner_policy_id)
            .values(
                policy_version=next_version,
                new_entry_submit_enabled=enabled,
                updated_at_ms=updated_at_ms,
            )
        )
        updated = dict(row)
        updated.update(
            policy_version=next_version,
            new_entry_submit_enabled=enabled,
            updated_at_ms=updated_at_ms,
        )
        return _owner_policy_from_row(updated)

    async def get_global_entry_resume_blocker(
        self,
        *,
        owner_policy_id: str,
    ) -> str | None:
        policy_scope = (
            await self._connection.execute(
                sa.select(owner_policy_current.c.scope).where(
                    owner_policy_current.c.owner_policy_id == owner_policy_id
                )
            )
        ).scalar_one_or_none()
        try:
            scope = OwnerPolicyScope.model_validate(policy_scope)
        except ValueError:
            return "owner_policy_scope_not_ready"
        runtime_profile_ids = tuple(
            sorted(
                {
                    item.runtime_profile_id
                    for item in scope.event_runtime_profiles
                }
            )
        )
        profiles = (
            await self._connection.execute(
                sa.select(runtime_profiles).where(
                    runtime_profiles.c.runtime_profile_id.in_(runtime_profile_ids)
                )
            )
        ).mappings().all()
        if (
            len(profiles) != len(runtime_profile_ids)
            or any(
                profile["status"] != "active"
                or profile["position_mode"] != "independent_sides"
                for profile in profiles
            )
        ):
            return "runtime_profile_not_ready"
        metadata_rows = {
            str(row["metadata_key"]): str(row["metadata_value"])
            for row in (
                await self._connection.execute(
                    sa.select(schema_metadata).where(
                        schema_metadata.c.metadata_key.in_(
                            ("runtime_commit", "schema_revision")
                        )
                    )
                )
            ).mappings()
        }
        capability = (
            await self._connection.execute(
                sa.select(runtime_capabilities_current).where(
                    runtime_capabilities_current.c.capability_key
                    == "exchange_commands"
                )
            )
        ).mappings().one_or_none()
        if (
            capability is None
            or not bool(capability["enabled"])
            or capability["certified_commit"] != metadata_rows.get("runtime_commit")
            or capability["schema_revision"] != metadata_rows.get("schema_revision")
        ):
            return "runtime_identity_not_ready"
        open_incident_count = await self._connection.scalar(
            sa.select(sa.func.count()).select_from(runtime_incidents).where(
                runtime_incidents.c.status == "open"
            )
        )
        if int(open_incident_count or 0) != 0:
            return "runtime_incident_open"
        unresolved_command_count = await self._connection.scalar(
            sa.select(sa.func.count()).select_from(exchange_commands).where(
                exchange_commands.c.status.in_(
                    ("prepared", "claimed", "dispatch_started", "outcome_unknown")
                )
            )
        )
        if int(unresolved_command_count or 0) != 0:
            return "exchange_command_unresolved"
        return None

    async def add_operation(self, operation: OwnerControlOperation) -> None:
        await self._connection.execute(
            sa.insert(owner_control_operations_current).values(
                **_operation_values(operation)
            )
        )
        await self._append_operation_event(operation, event_payload={})

    async def get_operation(
        self,
        authorization_id: str,
        *,
        for_update: bool = False,
    ) -> OwnerControlOperation | None:
        statement = sa.select(owner_control_operations_current).where(
            owner_control_operations_current.c.authorization_id == authorization_id
        )
        if for_update:
            statement = statement.with_for_update(of=owner_control_operations_current)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        return None if row is None else _operation_from_row(row)

    async def get_actionable_operation(
        self,
        *,
        now_ms: int,
        for_update: bool = False,
    ) -> OwnerControlOperation | None:
        statement = (
            sa.select(owner_control_operations_current)
            .where(
                owner_control_operations_current.c.state
                == ControlOperationState.PENDING.value,
                sa.or_(
                    owner_control_operations_current.c.lease_until_ms.is_(None),
                    owner_control_operations_current.c.lease_until_ms <= now_ms,
                ),
            )
            .order_by(owner_control_operations_current.c.created_at_ms)
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update(
                of=owner_control_operations_current,
                skip_locked=True,
            )
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        return None if row is None else _operation_from_row(row)

    async def get_progressable_operation(
        self,
        *,
        for_update: bool = False,
    ) -> OwnerControlOperation | None:
        statement = (
            sa.select(owner_control_operations_current)
            .where(
                owner_control_operations_current.c.state.in_(
                    (
                        ControlOperationState.EXITS_REQUESTED.value,
                        ControlOperationState.EXIT_IN_PROGRESS.value,
                        ControlOperationState.RECONCILIATION_PENDING.value,
                        ControlOperationState.SETTLEMENT_PENDING.value,
                        ControlOperationState.REVIEW_PENDING.value,
                        ControlOperationState.NEEDS_INTERVENTION.value,
                    )
                )
            )
            .order_by(owner_control_operations_current.c.created_at_ms)
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update(
                of=owner_control_operations_current,
                skip_locked=True,
            )
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        return None if row is None else _operation_from_row(row)

    async def get_latest_operation(self) -> OwnerControlOperation | None:
        row = (
            await self._connection.execute(
                sa.select(owner_control_operations_current)
                .order_by(owner_control_operations_current.c.created_at_ms.desc())
                .limit(1)
            )
        ).mappings().one_or_none()
        return None if row is None else _operation_from_row(row)

    async def get_latest_nonterminal_operation(self) -> OwnerControlOperation | None:
        row = (
            await self._connection.execute(
                sa.select(owner_control_operations_current)
                .where(
                    owner_control_operations_current.c.state.not_in(
                        (
                            ControlOperationState.COMPLETED.value,
                            ControlOperationState.BLOCKED.value,
                        )
                    )
                )
                .order_by(
                    owner_control_operations_current.c.updated_at_ms.desc(),
                    owner_control_operations_current.c.authorization_id,
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        return None if row is None else _operation_from_row(row)

    async def list_recent_operations(
        self,
        *,
        limit: int,
    ) -> tuple[OwnerControlOperation, ...]:
        rows = (
            await self._connection.execute(
                sa.select(owner_control_operations_current)
                .order_by(
                    owner_control_operations_current.c.updated_at_ms.desc(),
                    owner_control_operations_current.c.authorization_id,
                )
                .limit(max(1, min(limit, 20)))
            )
        ).mappings()
        return tuple(_operation_from_row(row) for row in rows)

    async def save_operation(
        self,
        operation: OwnerControlOperation,
        *,
        event_payload: dict[str, JsonValue],
    ) -> None:
        result = await self._connection.execute(
            sa.update(owner_control_operations_current)
            .where(
                owner_control_operations_current.c.authorization_id
                == operation.authorization_id,
                owner_control_operations_current.c.version == operation.version - 1,
            )
            .values(**_operation_values(operation))
        )
        if result.rowcount != 1:
            raise AggregateVersionConflict("Control operation version changed")
        await self._append_operation_event(operation, event_payload=event_payload)

    async def list_recent_events(
        self,
        *,
        limit: int,
    ) -> tuple[dict[str, JsonValue], ...]:
        rows = (
            await self._connection.execute(
                sa.select(owner_control_operation_events)
                .order_by(owner_control_operation_events.c.created_at_ms.desc())
                .limit(max(1, min(limit, 100)))
            )
        ).mappings()
        return tuple(
            {
                "event_id": str(row["control_operation_event_id"]),
                "authorization_id": str(row["authorization_id"]),
                "version": int(row["operation_version"]),
                "state": str(row["state"]),
                "first_blocker": row["first_blocker"],
                "created_at_ms": int(row["created_at_ms"]),
            }
            for row in rows
        )

    async def _append_operation_event(
        self,
        operation: OwnerControlOperation,
        *,
        event_payload: dict[str, JsonValue],
    ) -> None:
        await self._connection.execute(
            sa.insert(owner_control_operation_events).values(
                control_operation_event_id=f"control-operation-event:{uuid4().hex}",
                authorization_id=operation.authorization_id,
                operation_version=operation.version,
                state=operation.state.value,
                first_blocker=operation.first_blocker,
                payload=event_payload,
                created_at_ms=operation.updated_at_ms,
            )
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
        supported_margin_mode = str(row["supported_margin_mode"])
        if supported_margin_mode != "cross":
            raise RuntimeError("Owner policy has unsupported margin mode")
        return OwnerPolicySnapshot(
            owner_policy_id=str(row["owner_policy_id"]),
            policy_version=int(row["policy_version"]),
            enabled=bool(row["enabled"]),
            new_entry_submit_enabled=bool(row["new_entry_submit_enabled"]),
            priority_rank=int(row["priority_rank"]),
            max_concurrent_tickets=int(row["max_concurrent_tickets"]),
            family_ticket_limits=FamilyTicketLimits.model_validate(
                row["family_ticket_limits"]
            ),
            max_ticket_stop_risk_fraction=Decimal(
                row["max_ticket_stop_risk_fraction"]
            ),
            max_gross_stop_risk_fraction=Decimal(
                row["max_gross_stop_risk_fraction"]
            ),
            max_ticket_initial_margin_fraction=Decimal(
                row["max_ticket_initial_margin_fraction"]
            ),
            max_gross_initial_margin_utilization=Decimal(
                row["max_gross_initial_margin_utilization"]
            ),
            directional_stop_risk_limit_fraction=Decimal(
                row["directional_stop_risk_limit_fraction"]
            ),
            min_materialization_ratio=Decimal(row["min_materialization_ratio"]),
            max_leverage=int(row["max_leverage"]),
            supported_margin_mode=cast(Literal["cross"], supported_margin_mode),
            post_stop_stress_multiple=Decimal(row["post_stop_stress_multiple"]),
            max_post_fill_stop_risk_overrun_fraction=Decimal(
                row["max_post_fill_stop_risk_overrun_fraction"]
            ),
            scope=_owner_policy_scope(row["scope"]),
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

    async def count_active_family_tickets(
        self,
        *,
        venue_id: str,
        account_id: str,
        exposure_family: str,
    ) -> int:
        result = await self._connection.execute(
            sa.select(sa.func.count())
            .select_from(trade_tickets)
            .where(
                trade_tickets.c.venue_id == venue_id,
                trade_tickets.c.account_id == account_id,
                trade_tickets.c.exposure_family == exposure_family,
                trade_tickets.c.terminal_at_ms.is_(None),
            )
        )
        return int(result.scalar_one())

    async def sum_active_directional_stop_risk(
        self,
        *,
        venue_id: str,
        account_id: str,
        position_side: Literal["long", "short"],
    ) -> Decimal:
        result = await self._connection.execute(
            sa.select(
                sa.func.coalesce(sa.func.sum(trade_tickets.c.risk_at_stop), 0)
            ).where(
                trade_tickets.c.venue_id == venue_id,
                trade_tickets.c.account_id == account_id,
                trade_tickets.c.position_side == position_side,
                trade_tickets.c.terminal_at_ms.is_(None),
            )
        )
        return Decimal(result.scalar_one())

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
        domains_statement = (
            sa.select(
                trade_tickets.c.active_netting_domain_key,
                trade_aggregates.c.position_qty,
            )
            .select_from(
                trade_tickets.join(
                    trade_aggregates,
                    trade_aggregates.c.ticket_id == trade_tickets.c.ticket_id,
                )
            )
            .where(active_ticket)
            .order_by(trade_tickets.c.active_netting_domain_key)
        )
        domain_rows = (await self._connection.execute(domains_statement)).all()
        owned_position_domain_keys = tuple(
            str(row.active_netting_domain_key)
            for row in domain_rows
            if row.active_netting_domain_key is not None
        )
        owned_position_projections = tuple(
            OwnedPositionProjection(
                netting_domain_key=str(row.active_netting_domain_key),
                quantity=Decimal(row.position_qty),
            )
            for row in domain_rows
            if row.active_netting_domain_key is not None
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
        orders_statement = sa.select(*order_id_columns)
        orders_statement = orders_statement.select_from(
            trade_aggregates.join(
                trade_tickets,
                trade_tickets.c.ticket_id == trade_aggregates.c.ticket_id,
            )
        ).where(active_ticket)
        order_rows = await self._connection.execute(
            orders_statement
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

        unknown_statement = sa.select(exchange_commands.c.ticket_id)
        unknown_statement = unknown_statement.select_from(
            exchange_commands.join(
                trade_tickets,
                trade_tickets.c.ticket_id == exchange_commands.c.ticket_id,
            )
        ).where(
            active_ticket,
            exchange_commands.c.status
            == ExchangeCommandStatus.OUTCOME_UNKNOWN.value,
        ).order_by(exchange_commands.c.ticket_id)
        unknown_result = await self._connection.execute(
            unknown_statement
        )
        unknown_command_outcome_ticket_ids = tuple(
            sorted({str(value) for value in unknown_result.scalars().all()})
        )

        account_key = canonical_entry_block_key(
            EntryBlockScope.ACCOUNT_CAPACITY,
            venue_id=venue_id,
            account_id=account_id,
        )
        leverage_key = canonical_entry_block_key(
            EntryBlockScope.LEVERAGE_DOMAIN,
            venue_id=venue_id,
            account_id=account_id,
            exchange_instrument_id=exchange_instrument_id,
        )
        incident_statement = sa.select(runtime_incidents.c.entry_block_scope)
        incident_statement = incident_statement.where(
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
        ).order_by(runtime_incidents.c.entry_block_scope)
        incident_result = await self._connection.execute(
            incident_statement
        )
        open_incident_scopes = tuple(
            sorted(
                {
                    EntryBlockScope(str(value))
                    for value in incident_result.scalars().all()
                },
                key=lambda scope: scope.value,
            )
        )
        return AdmissionOwnership(
            owned_position_domain_keys=owned_position_domain_keys,
            owned_position_projections=owned_position_projections,
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
        reserved_margin: Decimal,
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
                    current_reserved_margin=reserved_margin,
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
                current_reserved_margin=(
                    account_exposure_current.c.current_reserved_margin
                    + reserved_margin
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
        reserved_margin: Decimal,
        updated_at_ms: int,
    ) -> None:
        current = await self.get_account_exposure(
            venue_id,
            account_id,
            for_update=True,
        )
        if current is None or current.active_ticket_count <= 0:
            raise AggregateVersionConflict("account exposure is missing during release")
        if (
            current.gross_notional < notional
            or current.gross_risk_at_stop < risk_at_stop
            or current.current_reserved_margin < reserved_margin
        ):
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
                current_reserved_margin=(
                    current.current_reserved_margin - reserved_margin
                ),
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
        "universe_version_id": ticket.universe_version_id,
        "selection_authority_id": ticket.selection_authority_id,
        "universe_semantic_digest": ticket.universe_semantic_digest,
        "account_id": identity.netting_domain.account_id,
        "venue_id": identity.netting_domain.venue_id,
        "exchange_instrument_id": identity.netting_domain.exchange_instrument_id,
        "position_side": identity.netting_domain.position_side,
        "netting_domain_key": identity.netting_domain.key(),
        "active_netting_domain_key": identity.netting_domain.key(),
        "exposure_family": ticket.exposure_family,
        "active_family_ticket_count_at_claim": (
            ticket.active_family_ticket_count_at_claim
        ),
        "family_ticket_limit": ticket.family_ticket_limit,
        "directional_risk_at_stop_at_claim": (
            ticket.directional_risk_at_stop_at_claim
        ),
        "directional_stop_risk_limit_fraction": (
            ticket.directional_stop_risk_limit_fraction
        ),
        "min_materialization_ratio": ticket.min_materialization_ratio,
        "minimum_stop_risk_budget": ticket.minimum_stop_risk_budget,
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
        "cross_margin_stress_model_id": ticket.cross_margin_stress_model_id,
        "post_stop_stress_multiple": ticket.post_stop_stress_multiple,
        "claim_stress_proof_digest": ticket.claim_stress_proof_digest,
        "risk_at_stop": ticket.risk_at_stop,
        "entry_order_type": ticket.entry_order_type.value,
        "entry_limit_price": ticket.entry_limit_price,
        "initial_stop_price": ticket.initial_stop_price,
        "pre_tp1_reclaim_price": ticket.pre_tp1_reclaim_price,
        "exposure_session_end_ms": ticket.exposure_session_end_ms,
        "take_profit_prices": [str(price) for price in ticket.take_profit_prices],
        "take_profit_quantities": [
            str(quantity) for quantity in ticket.take_profit_quantities
        ],
        "fact_digest": ticket.fact_digest,
        "exit_policy_id": ticket.exit_policy_id,
        "exit_policy_semantic_hash": ticket.exit_policy_semantic_hash,
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
    margin_mode = str(row["margin_mode"])
    if margin_mode != "cross":
        raise RuntimeError("Ticket has unsupported margin mode")
    return TradeTicket(
        identity=identity,
        owner_policy_id=str(row["owner_policy_id"]),
        owner_policy_version=int(row["owner_policy_version"]),
        runtime_scope_id=str(row["runtime_scope_id"]),
        runtime_scope_version=int(row["runtime_scope_version"]),
        universe_version_id=str(row["universe_version_id"]),
        selection_authority_id=row["selection_authority_id"],
        universe_semantic_digest=str(row["universe_semantic_digest"]),
        fact_digest=str(row["fact_digest"]),
        exposure_family=_exposure_family(row["exposure_family"]),
        active_family_ticket_count_at_claim=int(
            row["active_family_ticket_count_at_claim"]
        ),
        family_ticket_limit=int(row["family_ticket_limit"]),
        directional_risk_at_stop_at_claim=Decimal(
            row["directional_risk_at_stop_at_claim"]
        ),
        directional_stop_risk_limit_fraction=Decimal(
            row["directional_stop_risk_limit_fraction"]
        ),
        min_materialization_ratio=Decimal(row["min_materialization_ratio"]),
        minimum_stop_risk_budget=Decimal(row["minimum_stop_risk_budget"]),
        exit_policy_id=str(row["exit_policy_id"]),
        exit_policy_semantic_hash=str(row["exit_policy_semantic_hash"]),
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
        margin_mode=cast(Literal["cross"], margin_mode),
        cross_margin_stress_model_id=cast(
            Literal["cross-margin-stop-stress-v1"],
            str(row["cross_margin_stress_model_id"]),
        ),
        post_stop_stress_multiple=Decimal(row["post_stop_stress_multiple"]),
        claim_stress_proof_digest=str(row["claim_stress_proof_digest"]),
        risk_at_stop=Decimal(row["risk_at_stop"]),
        entry_order_type=EntryOrderType(str(row["entry_order_type"])),
        entry_limit_price=(
            None
            if row["entry_limit_price"] is None
            else Decimal(row["entry_limit_price"])
        ),
        initial_stop_price=Decimal(row["initial_stop_price"]),
        pre_tp1_reclaim_price=(
            None
            if row["pre_tp1_reclaim_price"] is None
            else Decimal(row["pre_tp1_reclaim_price"])
        ),
        exposure_session_end_ms=(
            None
            if row["exposure_session_end_ms"] is None
            else int(row["exposure_session_end_ms"])
        ),
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
        "universe_version_id": claim.universe_version_id,
        "selection_authority_id": claim.selection_authority_id,
        "universe_semantic_digest": claim.universe_semantic_digest,
        "account_id": identity.netting_domain.account_id,
        "venue_id": identity.netting_domain.venue_id,
        "exchange_instrument_id": (
            identity.netting_domain.exchange_instrument_id
        ),
        "position_side": identity.netting_domain.position_side,
        "netting_domain_key": identity.netting_domain.key(),
        "fact_digest": claim.fact_digest,
        "exit_policy_id": claim.exit_policy_id,
        "exit_policy_semantic_hash": claim.exit_policy_semantic_hash,
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
        "exposure_family": claim.exposure_family,
        "active_family_ticket_count_at_claim": (
            claim.active_family_ticket_count_at_claim
        ),
        "family_ticket_limit": claim.family_ticket_limit,
        "gross_risk_at_stop_at_claim": claim.gross_risk_at_stop_at_claim,
        "directional_risk_at_stop_at_claim": (
            claim.directional_risk_at_stop_at_claim
        ),
        "current_reserved_margin_at_claim": (
            claim.current_reserved_margin_at_claim
        ),
        "max_ticket_stop_risk_fraction": (
            claim.max_ticket_stop_risk_fraction
        ),
        "max_gross_stop_risk_fraction": (
            claim.max_gross_stop_risk_fraction
        ),
        "directional_stop_risk_limit_fraction": (
            claim.directional_stop_risk_limit_fraction
        ),
        "max_ticket_initial_margin_fraction": (
            claim.max_ticket_initial_margin_fraction
        ),
        "max_gross_initial_margin_utilization": (
            claim.max_gross_initial_margin_utilization
        ),
        "min_materialization_ratio": claim.min_materialization_ratio,
        "minimum_stop_risk_budget": claim.minimum_stop_risk_budget,
        "planned_stop_risk_budget": claim.planned_stop_risk_budget,
        "max_post_fill_stop_risk_overrun_fraction": (
            claim.max_post_fill_stop_risk_overrun_fraction
        ),
        "post_fill_stop_risk_limit": claim.post_fill_stop_risk_limit,
        "post_stop_stress_multiple": claim.post_stop_stress_multiple,
        "ticket_margin_budget": claim.ticket_margin_budget,
        "required_leverage": claim.required_leverage,
        "selected_leverage": claim.selected_leverage,
        "configured_leverage_at_claim": claim.configured_leverage_at_claim,
        "leverage_change_required": claim.leverage_change_required,
        "exchange_max_leverage": claim.exchange_max_leverage,
        "reserved_margin": claim.reserved_margin,
        "cross_margin_stress_evidence": (
            claim.cross_margin_stress_evidence.model_dump(mode="json")
        ),
        "entry_reference_price": claim.entry_reference_price,
        "quantity": claim.quantity,
        "notional": claim.notional,
        "risk_at_stop": claim.risk_at_stop,
        "entry_order_type": claim.entry_order_type.value,
        "entry_limit_price": claim.entry_limit_price,
        "initial_stop_price": claim.initial_stop_price,
        "pre_tp1_reclaim_price": claim.pre_tp1_reclaim_price,
        "exposure_session_end_ms": claim.exposure_session_end_ms,
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
    position_mode_at_claim = str(row["position_mode_at_claim"])
    if position_mode_at_claim not in {"independent_sides", "one_way"}:
        raise RuntimeError("Capacity Claim has unsupported position mode")
    margin_mode_at_claim = str(row["margin_mode_at_claim"])
    if margin_mode_at_claim not in {"cross", "isolated"}:
        raise RuntimeError("Capacity Claim has unsupported margin mode")
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
        universe_version_id=str(row["universe_version_id"]),
        selection_authority_id=row["selection_authority_id"],
        universe_semantic_digest=str(row["universe_semantic_digest"]),
        fact_digest=str(row["fact_digest"]),
        exit_policy_id=str(row["exit_policy_id"]),
        exit_policy_semantic_hash=str(row["exit_policy_semantic_hash"]),
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
        position_mode_at_claim=cast(
            Literal["independent_sides", "one_way"],
            position_mode_at_claim,
        ),
        margin_mode_at_claim=cast(
            Literal["cross", "isolated"],
            margin_mode_at_claim,
        ),
        active_ticket_count_at_claim=int(row["active_ticket_count_at_claim"]),
        remaining_slots_at_claim=int(row["remaining_slots_at_claim"]),
        exposure_family=_exposure_family(row["exposure_family"]),
        active_family_ticket_count_at_claim=int(
            row["active_family_ticket_count_at_claim"]
        ),
        family_ticket_limit=int(row["family_ticket_limit"]),
        remaining_family_slots_at_claim=(
            int(row["family_ticket_limit"])
            - int(row["active_family_ticket_count_at_claim"])
        ),
        gross_risk_at_stop_at_claim=Decimal(
            row["gross_risk_at_stop_at_claim"]
        ),
        directional_risk_at_stop_at_claim=Decimal(
            row["directional_risk_at_stop_at_claim"]
        ),
        current_reserved_margin_at_claim=Decimal(
            row["current_reserved_margin_at_claim"]
        ),
        max_ticket_stop_risk_fraction=Decimal(
            row["max_ticket_stop_risk_fraction"]
        ),
        max_gross_stop_risk_fraction=Decimal(
            row["max_gross_stop_risk_fraction"]
        ),
        directional_stop_risk_limit_fraction=Decimal(
            row["directional_stop_risk_limit_fraction"]
        ),
        max_ticket_initial_margin_fraction=Decimal(
            row["max_ticket_initial_margin_fraction"]
        ),
        max_gross_initial_margin_utilization=Decimal(
            row["max_gross_initial_margin_utilization"]
        ),
        min_materialization_ratio=Decimal(row["min_materialization_ratio"]),
        minimum_stop_risk_budget=Decimal(row["minimum_stop_risk_budget"]),
        planned_stop_risk_budget=Decimal(row["planned_stop_risk_budget"]),
        max_post_fill_stop_risk_overrun_fraction=Decimal(
            row["max_post_fill_stop_risk_overrun_fraction"]
        ),
        post_fill_stop_risk_limit=Decimal(row["post_fill_stop_risk_limit"]),
        post_stop_stress_multiple=Decimal(row["post_stop_stress_multiple"]),
        ticket_margin_budget=Decimal(row["ticket_margin_budget"]),
        required_leverage=int(row["required_leverage"]),
        selected_leverage=int(row["selected_leverage"]),
        configured_leverage_at_claim=int(row["configured_leverage_at_claim"]),
        leverage_change_required=bool(row["leverage_change_required"]),
        exchange_max_leverage=int(row["exchange_max_leverage"]),
        reserved_margin=Decimal(row["reserved_margin"]),
        cross_margin_stress_evidence=CrossMarginStressEvidence.model_validate(
            row["cross_margin_stress_evidence"]
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
        pre_tp1_reclaim_price=(
            None
            if row["pre_tp1_reclaim_price"] is None
            else Decimal(row["pre_tp1_reclaim_price"])
        ),
        exposure_session_end_ms=(
            None
            if row["exposure_session_end_ms"] is None
            else int(row["exposure_session_end_ms"])
        ),
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
        "actual_stop_risk": aggregate.actual_stop_risk,
        "venue_reported_liquidation_price": (
            aggregate.venue_reported_liquidation_price
        ),
        "post_fill_risk_status": (
            None
            if aggregate.post_fill_risk_status is None
            else aggregate.post_fill_risk_status.value
        ),
        "post_fill_disposition": (
            None
            if aggregate.post_fill_disposition is None
            else aggregate.post_fill_disposition.value
        ),
        "post_fill_stress_status": aggregate.post_fill_stress_status,
        "post_fill_stress_proof_digest": (
            aggregate.post_fill_stress_proof_digest
        ),
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
        "entry_vacuum_id": aggregate.entry_vacuum_id,
        "entry_materialization_kind": aggregate.entry_materialization_kind,
        "exit_exchange_order_id": aggregate.exit_exchange_order_id,
        "review_id": aggregate.review_id,
        "updated_at_ms": updated_at_ms or aggregate.ticket.created_at_ms,
    }


def _admission_decision_values(
    decision: AdmissionDecision,
) -> dict[str, object]:
    candidate_set = decision.candidate_set.model_dump(mode="json")
    return {
        "admission_decision_id": decision.admission_decision_id,
        "signal_event_id": decision.signal_event_id,
        "exposure_episode_id": decision.exposure_episode_id,
        "strategy_group_id": decision.strategy_group_id,
        "strategy_version_id": decision.strategy_version_id,
        "event_spec_id": decision.event_spec_id,
        "universe_version_id": decision.universe_version_id,
        "selection_authority_id": decision.selection_authority_id,
        "universe_semantic_digest": decision.universe_semantic_digest,
        "runtime_profile_id": decision.runtime_profile_id,
        "runtime_scope_id": decision.runtime_scope_id,
        "runtime_scope_version": decision.runtime_scope_version,
        "owner_policy_id": decision.owner_policy_id,
        "owner_policy_version": decision.owner_policy_version,
        "venue_id": decision.venue_id,
        "account_id": decision.account_id,
        "exchange_instrument_id": decision.exchange_instrument_id,
        "position_side": decision.position_side,
        "exposure_family": decision.exposure_family,
        "candidate_rank": decision.candidate_rank,
        "candidate_count": candidate_set["candidate_count"],
        "candidate_set_digest": candidate_set["candidate_set_digest"],
        "candidate_set_summary": candidate_set["candidate_set_summary"],
        "portfolio_usage": decision.portfolio_usage.model_dump(mode="json"),
        "decision_status": decision.decision_status.value,
        "first_blocker": decision.first_blocker,
        "binding_constraint": decision.binding_constraint,
        "capacity_claim_id": decision.capacity_claim_id,
        "ticket_id": decision.ticket_id,
        "entry_admission_snapshot_digest": (
            decision.entry_admission_snapshot_digest
        ),
        "decision_digest": decision.decision_digest,
        "decided_at_ms": decision.decided_at_ms,
    }


def _admission_decision_from_row(row: RowMapping) -> AdmissionDecision:
    return AdmissionDecision.model_validate(
        {
            **dict(row),
            "candidate_set": {
                "ranked_signal_event_ids": tuple(
                    item["signal_event_id"]
                    for item in row["candidate_set_summary"]
                ),
                "candidate_count": int(row["candidate_count"]),
                "candidate_set_digest": str(row["candidate_set_digest"]),
                "candidate_set_summary": row["candidate_set_summary"],
            },
            "portfolio_usage": row["portfolio_usage"],
        },
        extra="ignore",
    )


def _shadow_outcome_pending_values(spec: ShadowOutcomeSpec) -> dict[str, object]:
    unavailable = spec.unavailable_reason is not None
    return {
        "shadow_outcome_id": spec.shadow_outcome_id,
        "signal_event_id": spec.signal_event_id,
        "admission_decision_id": spec.admission_decision_id,
        "source_kind": spec.source_kind,
        "status": "unavailable" if unavailable else "pending",
        "evaluation_kind": spec.evaluation_kind,
        "exchange_instrument_id": spec.exchange_instrument_id,
        "position_side": spec.position_side,
        "timeframe": spec.timeframe,
        "entry_reference_price": spec.entry_reference_price,
        "initial_stop_price": spec.initial_stop_price,
        "initial_risk_per_unit": spec.initial_risk_per_unit,
        "take_profit_price": spec.take_profit_price,
        "opening_range_boundary_price": spec.opening_range_boundary_price,
        "session_exit_deadline_ms": spec.session_exit_deadline_ms,
        "mark_price": spec.mark_price,
        "index_price": spec.index_price,
        "funding_rate": spec.funding_rate,
        "best_bid_price": spec.best_bid_price,
        "best_ask_price": spec.best_ask_price,
        "best_bid_quantity": spec.best_bid_quantity,
        "best_ask_quantity": spec.best_ask_quantity,
        "spread_bps": spec.spread_bps,
        "mark_index_deviation_bps": spec.mark_index_deviation_bps,
        "horizon_start_ms": spec.horizon_start_ms,
        "horizon_end_ms": spec.horizon_end_ms,
        "claim_owner": None,
        "claim_token": None,
        "lease_until_ms": None,
        "max_favorable_price": None,
        "max_adverse_price": None,
        "mfe_r": None,
        "mae_r": None,
        "observed_through_ms": None,
        "completion_reason": spec.unavailable_reason,
        "first_path": None,
        "first_path_at_ms": None,
        "observed_bar_count": None,
        "projection_version": 1,
        "created_at_ms": spec.created_at_ms,
        "completed_at_ms": spec.created_at_ms if unavailable else None,
    }


def _shadow_outcome_spec_from_row(row: RowMapping) -> ShadowOutcomeSpec:
    return ShadowOutcomeSpec(
        shadow_outcome_id=str(row["shadow_outcome_id"]),
        signal_event_id=str(row["signal_event_id"]),
        admission_decision_id=(
            None
            if row["admission_decision_id"] is None
            else str(row["admission_decision_id"])
        ),
        source_kind=cast(
            Literal["portfolio_rejection", "strategy_observation"],
            str(row["source_kind"]),
        ),
        evaluation_kind=cast(
            Literal["fixed_horizon_excursion_v1", "sor_path_observation_v1"],
            str(row["evaluation_kind"]),
        ),
        exchange_instrument_id=str(row["exchange_instrument_id"]),
        position_side=cast(Literal["long", "short"], str(row["position_side"])),
        timeframe=cast(Literal["1h", "15m"], str(row["timeframe"])),
        entry_reference_price=_decimal_or_none(row["entry_reference_price"]),
        initial_stop_price=_decimal_or_none(row["initial_stop_price"]),
        take_profit_price=_decimal_or_none(row["take_profit_price"]),
        opening_range_boundary_price=_decimal_or_none(
            row["opening_range_boundary_price"]
        ),
        session_exit_deadline_ms=(
            None
            if row["session_exit_deadline_ms"] is None
            else int(row["session_exit_deadline_ms"])
        ),
        mark_price=_decimal_or_none(row["mark_price"]),
        index_price=_decimal_or_none(row["index_price"]),
        funding_rate=_decimal_or_none(row["funding_rate"]),
        best_bid_price=_decimal_or_none(row["best_bid_price"]),
        best_ask_price=_decimal_or_none(row["best_ask_price"]),
        best_bid_quantity=_decimal_or_none(row["best_bid_quantity"]),
        best_ask_quantity=_decimal_or_none(row["best_ask_quantity"]),
        unavailable_reason=(
            str(row["completion_reason"])
            if row["status"] == "unavailable"
            else None
        ),
        horizon_start_ms=int(row["horizon_start_ms"]),
        horizon_end_ms=int(row["horizon_end_ms"]),
        created_at_ms=int(row["created_at_ms"]),
    )


def _decimal_or_none(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


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
        actual_stop_risk=(
            None
            if row["actual_stop_risk"] is None
            else Decimal(row["actual_stop_risk"])
        ),
        venue_reported_liquidation_price=(
            None
            if row["venue_reported_liquidation_price"] is None
            else Decimal(row["venue_reported_liquidation_price"])
        ),
        post_fill_risk_status=(
            None
            if row["post_fill_risk_status"] is None
            else PostFillRiskStatus(str(row["post_fill_risk_status"]))
        ),
        post_fill_disposition=(
            None
            if row["post_fill_disposition"] is None
            else PostFillDisposition(str(row["post_fill_disposition"]))
        ),
        post_fill_stress_status=(
            None
            if row["post_fill_stress_status"] is None
            else cast(Literal["passed", "failed"], str(row["post_fill_stress_status"]))
        ),
        post_fill_stress_proof_digest=(
            None
            if row["post_fill_stress_proof_digest"] is None
            else str(row["post_fill_stress_proof_digest"])
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
        entry_vacuum_id=(
            None
            if row["entry_vacuum_id"] is None
            else str(row["entry_vacuum_id"])
        ),
        entry_materialization_kind=row["entry_materialization_kind"],
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


def _exposure_family(value: object) -> ExposureFamily:
    normalized = str(value)
    if normalized in {
        "long_continuation",
        "opening_range",
        "rally_failure_short",
    }:
        return cast(ExposureFamily, normalized)
    raise RuntimeError(f"invalid persisted exposure family: {normalized!r}")


def _is_historical_terminal_ticket(row: RowMapping) -> bool:
    return (
        row["terminal_at_ms"] is not None
        and row["minimum_stop_risk_budget"] is None
    )
