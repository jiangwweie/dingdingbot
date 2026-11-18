"""One short PostgreSQL transaction per trading-kernel state reduction."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction
from typing_extensions import Self

from src.trading_kernel.application.notice_policy import build_notices
from src.trading_kernel.application.ports import (
    AdmissionDecisionRepository,
    AggregateRepository,
    AggregateVersionConflict,
    BudgetRepository,
    CapacityClaimRepository,
    DirectionalRiskRepository,
    EntryAdmissionRepository,
    EventRepository,
    ExchangeCommandRepository,
    ExitProfileAuthorityRepository,
    IncidentRepository,
    InstrumentSelectionRepository,
    ManagementRepository,
    MonitorRepository,
    OwnerControlRepository,
    OwnerPositionOperationRepository,
    PositionRepository,
    ReviewRepository,
    RuntimeIncidentRecord,
    ShadowOutcomeRepository,
    SignalRepository,
    StrategyRegistryRepository,
    StrategyUniverseRepository,
    TicketRepository,
    UnsupportedKernelEffect,
)
from src.trading_kernel.application.project_owner_state import (
    derive_terminal_owner_projection,
)
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.capacity import CapacityClaim
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
    SetLeverageCommandPayload,
    build_command_id,
    build_venue_client_order_id,
    require_next_generation_allowed,
)
from src.trading_kernel.domain.effects import (
    CancelEntryRemainder,
    CancelProtectionOrders,
    CancelVacuumEntryOrder,
    MarkCancelCommandReconciledAbsent,
    OpenIncident,
    PrepareControlledFlattenCommand,
    PrepareEntryCommand,
    PrepareExitCommand,
    PrepareInitialStopCommand,
    PrepareProtectionReplacementCommand,
    PrepareSetLeverageCommand,
    PrepareTakeProfitCommand,
    ProjectTerminalOwnerState,
    ReleaseBudget,
    ReleaseCapitalAuthorities,
    ReleaseEntryLane,
    RequestControlledFlatten,
    ResolveExactClosureIncidents,
    ResolveIncident,
    ResolveTicketIncidentsAtClosure,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.events import (
    NaturalTakeProfitRecorded,
    OwnerAutomaticTpRestoreRequested,
    OwnerProfitPlanCancelled,
    OwnerProfitPlanInstalled,
    OwnerProfitPlanRetired,
    OwnerProtectionRequested,
    OwnerReductionRecorded,
    PostFillStressAssessed,
    TakeProfitCompletedForExit,
    TakeProfitFilled,
    TakeProfitProgressed,
    TicketIssued,
    TradeEvent,
)
from src.trading_kernel.domain.incident_blocking import (
    EntryBlockScope,
    canonical_entry_block_key,
)
from src.trading_kernel.domain.reducer import Reduction
from src.trading_kernel.domain.ticket import EntryOrderType, TradeTicket
from src.trading_kernel.domain.trade_management import ManagementMode
from src.trading_kernel.infrastructure.pg_directional_risk_repository import (
    PostgresDirectionalRiskRepository,
)
from src.trading_kernel.infrastructure.pg_exit_profile_repository import (
    PostgresExitProfileAuthorityRepository,
)
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
)
from src.trading_kernel.infrastructure.pg_management_repository import (
    PostgresManagementRepository,
)
from src.trading_kernel.infrastructure.pg_models import post_fill_exit_plans
from src.trading_kernel.infrastructure.pg_notice_outbox import enqueue_notice
from src.trading_kernel.infrastructure.pg_repositories import (
    PostgresAdmissionDecisionRepository,
    PostgresAggregateRepository,
    PostgresBudgetRepository,
    PostgresCapacityClaimRepository,
    PostgresEntryAdmissionRepository,
    PostgresEventRepository,
    PostgresExchangeCommandRepository,
    PostgresIncidentRepository,
    PostgresMonitorRepository,
    PostgresOwnerControlRepository,
    PostgresPositionRepository,
    PostgresReviewRepository,
    PostgresShadowOutcomeRepository,
    PostgresTicketRepository,
)
from src.trading_kernel.infrastructure.pg_signal_repository import (
    PostgresSignalRepository,
)
from src.trading_kernel.infrastructure.pg_universe_repository import (
    PostgresStrategyUniverseRepository,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    PostgresStrategyRegistryRepository,
)

__all__ = ["AggregateVersionConflict", "PostgresKernelUnitOfWork"]


class PostgresKernelUnitOfWork:
    management: ManagementRepository
    directional_risk: DirectionalRiskRepository
    tickets: TicketRepository
    aggregates: AggregateRepository
    events: EventRepository
    exchange_commands: ExchangeCommandRepository
    budgets: BudgetRepository
    capacity_claims: CapacityClaimRepository
    incidents: IncidentRepository
    monitors: MonitorRepository
    owner_controls: OwnerControlRepository
    positions: PositionRepository
    reviews: ReviewRepository
    entry_admission: EntryAdmissionRepository
    admission_decisions: AdmissionDecisionRepository
    shadow_outcomes: ShadowOutcomeRepository
    signals: SignalRepository
    strategy_registry: StrategyRegistryRepository
    strategy_universes: StrategyUniverseRepository
    instrument_selection: InstrumentSelectionRepository
    exit_profiles: ExitProfileAuthorityRepository

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._connection: AsyncConnection | None = None
        self._transaction: AsyncTransaction | None = None
        self._notice_changes: dict[
            str, tuple[TradeAggregate | None, list[TradeEvent]]
        ] = {}

    async def __aenter__(self) -> Self:
        if self._connection is not None:
            raise RuntimeError("unit of work is already active")
        self._connection = await self._engine.connect()
        self._transaction = await self._connection.begin()
        self._management_repository = PostgresManagementRepository(self._connection)
        self._management_repository.application_checkpoint = (
            self._management_application_checkpoint
        )
        self.management = self._management_repository
        self.directional_risk = PostgresDirectionalRiskRepository(self._connection)
        self.tickets = PostgresTicketRepository(self._connection)
        self.aggregates = PostgresAggregateRepository(self._connection)
        self.events = PostgresEventRepository(self._connection)
        self.exchange_commands = PostgresExchangeCommandRepository(self._connection)
        self.budgets = PostgresBudgetRepository(self._connection)
        self.capacity_claims = PostgresCapacityClaimRepository(self._connection)
        self.incidents = PostgresIncidentRepository(self._connection)
        self.monitors = PostgresMonitorRepository(self._connection)
        self.owner_controls = PostgresOwnerControlRepository(self._connection)
        from src.trading_kernel.infrastructure.pg_owner_position_operations import (
            PostgresOwnerPositionOperations,
        )

        self.owner_position_operations: OwnerPositionOperationRepository = (
            PostgresOwnerPositionOperations(self._connection)
        )
        self.positions = PostgresPositionRepository(self._connection)
        self.reviews = PostgresReviewRepository(self._connection)
        self.entry_admission = PostgresEntryAdmissionRepository(self._connection)
        self.admission_decisions = PostgresAdmissionDecisionRepository(self._connection)
        self.shadow_outcomes = PostgresShadowOutcomeRepository(self._connection)
        self.signals = PostgresSignalRepository(self._connection)
        self.strategy_registry = PostgresStrategyRegistryRepository(self._connection)
        self.strategy_universes = PostgresStrategyUniverseRepository(self._connection)
        self.instrument_selection = PostgresInstrumentSelectionRepository(
            self._connection
        )
        self.exit_profiles = PostgresExitProfileAuthorityRepository(self._connection)
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
                for ticket_id in self._management_repository.new_evidence:
                    if ticket_id not in self._notice_changes:
                        self._notice_changes[ticket_id] = (
                            await self.aggregates.get(ticket_id),
                            [],
                        )
                for ticket_id, (before, events) in self._notice_changes.items():
                    final = await self.aggregates.get(ticket_id)
                    if final is not None:
                        position = await self.positions.get(
                            final.identity.netting_domain.key()
                        )
                        for notice in build_notices(
                            before,
                            final,
                            tuple(events),
                            position,
                            tuple(
                                self._management_repository.new_evidence.get(
                                    ticket_id, []
                                )
                            ),
                        ):
                            await enqueue_notice(connection, notice)
                await transaction.commit()
            else:
                await transaction.rollback()
        finally:
            await connection.close()
            self._transaction = None
            self._connection = None
            self._notice_changes.clear()

    @asynccontextmanager
    async def _management_application_checkpoint(self) -> AsyncIterator[None]:
        """Rollback an observer's SQL and deferred notice state together."""
        notices = {
            key: (before, list(events))
            for key, (before, events) in self._notice_changes.items()
        }
        evidence = {
            key: list(items)
            for key, items in self._management_repository.new_evidence.items()
        }
        try:
            async with self._require_connection().begin_nested():
                yield
        except BaseException:
            self._notice_changes.clear()
            self._notice_changes.update(notices)
            self._management_repository.new_evidence.clear()
            self._management_repository.new_evidence.update(evidence)
            raise

    async def commit_reduction(
        self,
        *,
        event: TradeEvent,
        reduction: Reduction,
        expected_version: int,
    ) -> None:
        self._require_connection()
        aggregate = reduction.aggregate
        if aggregate.management_mode is not ManagementMode.AUTO:
            allowed = (
                ReleaseBudget,
                ReleaseCapitalAuthorities,
                ReleaseEntryLane,
                ProjectTerminalOwnerState,
                ResolveIncident,
                ResolveTicketIncidentsAtClosure,
                ResolveExactClosureIncidents,
            )
            if any(not isinstance(effect, allowed) for effect in reduction.effects):
                raise UnsupportedKernelEffect(
                    "manual/review management forbids exchange effects"
                )
        ticket_id = aggregate.identity.ticket_id
        current = await self.aggregates.get_for_update(ticket_id)

        if isinstance(event, OwnerReductionRecorded):
            reduction_proof = event.proof
            if (
                reduction_proof is None
                or current is None
                or reduction_proof.ticket_id != ticket_id
                or reduction_proof.domain != current.identity.netting_domain
            ):
                raise UnsupportedKernelEffect(
                    "Owner reduction requires exact readonly fill proof"
                )
            reduction_proof.require_source(current)
            if reduction_proof.retired_protections:
                from src.trading_kernel.domain.trade_management import (
                    OrderAction,
                    OrderEvidence,
                )
                from src.trading_kernel.infrastructure.pg_models import (
                    management_order_evidence,
                )

                references = await self.exchange_commands.list_order_references(
                    ticket_id
                )
                for retired in reduction_proof.retired_protections:
                    raw = (
                        await self._require_connection().execute(
                            sa.select(management_order_evidence.c.payload).where(
                                management_order_evidence.c.ticket_id == ticket_id,
                                management_order_evidence.c.evidence_id
                                == retired.evidence_id,
                            )
                        )
                    ).scalar_one_or_none()
                    evidence = (
                        None if raw is None else OrderEvidence.model_validate(raw)
                    )
                    if (
                        evidence is None
                        or evidence.terms.exchange_order_id != retired.exchange_order_id
                        or evidence.terms.client_order_id != retired.client_order_id
                        or evidence.terms.order_namespace != "conditional"
                        or evidence.terms.identity[:4]
                        != (
                            current.identity.netting_domain.venue_id,
                            current.identity.netting_domain.account_id,
                            current.identity.netting_domain.exchange_instrument_id,
                            current.identity.netting_domain.position_side,
                        )
                        or evidence.action
                        not in {OrderAction.CANCEL, OrderAction.EXPIRED}
                        or evidence.action
                        is not (
                            OrderAction.CANCEL
                            if retired.status == "CANCELED"
                            else OrderAction.EXPIRED
                        )
                        or evidence.executed_quantity != 0
                        or evidence.received_at_ms != retired.observed_at_ms
                        or not evidence.coverage_complete
                        or evidence.known_command_outcome_pending
                        or not any(
                            r.submitted_exchange_order_id == retired.exchange_order_id
                            and r.venue_client_order_id == retired.client_order_id
                            and r.command_created_at_ms <= evidence.exchange_event_at_ms
                            for r in references
                        )
                    ):
                        raise UnsupportedKernelEffect(
                            "Owner reduction retired protection lacks durable terminal evidence"
                        )
            from src.trading_kernel.infrastructure.owner_device_authorization_evidence import (
                trusted_owner_authorization_matches,
            )

            if not await trusted_owner_authorization_matches(
                self._require_connection(), reduction_proof.authorization_id
            ):
                raise UnsupportedKernelEffect(
                    "Owner reduction signed authority not verified"
                )
            auth = await self.owner_controls.get_authorization(
                reduction_proof.authorization_id
            )
            command = await self.exchange_commands.get(reduction_proof.command_id)
            from src.trading_kernel.infrastructure.pg_models import (
                owner_position_operations,
            )

            operation = (
                (
                    await self._require_connection().execute(
                        sa.select(owner_position_operations)
                        .where(
                            owner_position_operations.c.operation_id
                            == reduction_proof.operation_id
                        )
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                operation is None
                or operation["authorization_id"] != reduction_proof.authorization_id
                or operation["ticket_id"] != ticket_id
                or operation["state"] == "previewed"
                or auth is None
                or auth.purpose != "position_reduce"
                or auth.authentication_strength != "trusted_device_session"
                or auth.target_scope.get("operation_id") != reduction_proof.operation_id
                or auth.target_scope.get("ticket_id") != ticket_id
                or command is None
                or command.kind is not ExchangeCommandKind.OWNER_REDUCE
                or command.status
                not in {
                    ExchangeCommandStatus.ACCEPTED,
                    ExchangeCommandStatus.RECONCILED_ACCEPTED,
                }
                or command.ticket_identity != current.identity
                or not isinstance(command.payload, OrderCommandPayload)
                or command.payload.owner_operation_id != reduction_proof.operation_id
                or command.payload.quantity != reduction_proof.requested_quantity
                or command.venue_client_order_id
                != reduction_proof.venue_client_order_id
                or (
                    reduction_proof.executed_quantity,
                    reduction_proof.remaining_quantity,
                    reduction_proof.average_price,
                    reduction_proof.protection_order_id,
                    reduction_proof.protection_price,
                    reduction_proof.digest(),
                )
                != (
                    event.filled_quantity,
                    event.remaining_quantity,
                    event.average_fill_price,
                    event.protection_order_id,
                    event.protection_price,
                    event.proof_digest,
                )
            ):
                raise UnsupportedKernelEffect(
                    "Owner reduction proof differs from authorized command"
                )

        if isinstance(event, OwnerProfitPlanRetired):
            retirement = await self.owner_position_operations.get(
                event.operation_id, for_update=True
            )
            original = await self.exchange_commands.get(event.command_id)
            source_rows = await self.management.command_rows_for_order(
                ticket_id, "regular", event.exchange_order_id
            )
            if (
                current is None
                or retirement is None
                or retirement["ticket_id"] != ticket_id
                or retirement["kind"]
                not in {"manual_tp_set", "manual_tp_cancel", "position_close"}
                or retirement["completed_at_ms"] is not None
                or not any(
                    r["command_kind"] == "cancel_order"
                    and r["status"]
                    in {"accepted", "reconciled_accepted", "reconciled_absent"}
                    and r["request_payload"].get("owner_operation_id")
                    == event.operation_id
                    and r["request_payload"].get("exchange_order_id")
                    == event.exchange_order_id
                    and r["request_payload"].get("order_namespace") == "regular"
                    for r in source_rows
                )
                or original is None
                or original.kind is not ExchangeCommandKind.TAKE_PROFIT
                or original.status
                not in {
                    ExchangeCommandStatus.ACCEPTED,
                    ExchangeCommandStatus.RECONCILED_ACCEPTED,
                }
                or original.ticket_identity != current.identity
                or not isinstance(original.payload, OrderCommandPayload)
                or original.venue_client_order_id
                != event.evidence.terms.client_order_id
                or original.payload.limit_price != event.evidence.terms.price
                or original.payload.quantity != event.evidence.terms.quantity
                or event.source_kind
                != (
                    "manual"
                    if original.payload.owner_operation_id is not None
                    else "retired_automatic"
                )
                or not any(
                    r["command_id"] == event.command_id
                    and r["result_payload"].get("exchange_order_id")
                    == event.exchange_order_id
                    for r in source_rows
                )
                or event.evidence.terms.identity[:4]
                != (
                    current.identity.netting_domain.venue_id,
                    current.identity.netting_domain.account_id,
                    current.identity.netting_domain.exchange_instrument_id,
                    current.identity.netting_domain.position_side,
                )
            ):
                raise UnsupportedKernelEffect(
                    "retired TP differs from durable operation/order source"
                )
            await self.management.save_evidence(ticket_id, event.evidence)
        if isinstance(event, (OwnerProfitPlanInstalled, OwnerProfitPlanCancelled)):
            plan_operation = await self.owner_position_operations.get(
                event.operation_id, for_update=True
            )
            expected_kind = (
                "manual_tp_set"
                if isinstance(event, OwnerProfitPlanInstalled)
                else "manual_tp_cancel"
            )
            evidence = event.evidence
            if (
                current is None
                or plan_operation is None
                or plan_operation["kind"] != expected_kind
                or plan_operation["ticket_id"] != ticket_id
                or evidence is None
                or evidence.terms.exchange_order_id != event.exchange_order_id
                or not evidence.coverage_complete
                or evidence.known_command_outcome_pending
                or evidence.terms.identity[:4]
                != (
                    current.identity.netting_domain.venue_id,
                    current.identity.netting_domain.account_id,
                    current.identity.netting_domain.exchange_instrument_id,
                    current.identity.netting_domain.position_side,
                )
                or not await self.owner_position_operations.authority_current(
                    plan_operation, management_revision=current.management_revision
                )
            ):
                raise UnsupportedKernelEffect("manual TP operation source differs")
            if isinstance(event, OwnerProfitPlanInstalled):
                plan_command = await self.exchange_commands.get(event.command_id)
                if (
                    plan_command is None
                    or plan_command.status
                    not in {
                        ExchangeCommandStatus.ACCEPTED,
                        ExchangeCommandStatus.RECONCILED_ACCEPTED,
                    }
                    or not isinstance(plan_command.payload, OrderCommandPayload)
                    or plan_command.payload.owner_operation_id != event.operation_id
                    or plan_command.payload.limit_price != event.price
                    or plan_command.payload.quantity != event.quantity
                    or plan_command.venue_client_order_id
                    != evidence.terms.client_order_id
                ):
                    raise UnsupportedKernelEffect("manual TP command differs")
            elif evidence.action.value not in {"cancel", "expired"}:
                raise UnsupportedKernelEffect("manual TP cancellation unproven")
            await self.management.save_evidence(ticket_id, evidence)
        if isinstance(event, OwnerProtectionRequested):
            protection_op = await self.owner_position_operations.get(
                event.operation_id, for_update=True
            )
            if (
                current is None
                or protection_op is None
                or protection_op["ticket_id"] != ticket_id
                or protection_op["completed_at_ms"] is not None
                or protection_op["kind"]
                not in {"position_reduce", "protection_tighten", "manual_tp_set"}
                or not await self.owner_position_operations.authority_current(
                    protection_op, management_revision=current.management_revision
                )
            ):
                raise UnsupportedKernelEffect(
                    "Owner protection lacks current operation authority"
                )
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

        if isinstance(event, PostFillStressAssessed):
            profile_record = await self.exit_profiles.get_profile(
                exit_profile_id=aggregate.ticket.exit_policy_id,
                semantic_hash=aggregate.ticket.exit_policy_semantic_hash,
            )
            if profile_record is None:
                raise UnsupportedKernelEffect("post-fill exact profile missing")
            if (
                profile_record.profile.execution is not None
                and event.status == "passed"
                and event.exit_plan is None
                and event.exit_plan_failure is None
            ):
                raise UnsupportedKernelEffect(
                    "v2 post-fill requires explicit plan or safe failure"
                )
            if event.exit_plan is not None and (
                profile_record.profile.execution != event.exit_plan.execution
                or profile_record.profile.tp1.reward_multiple
                != event.exit_plan.target_multiple
                or profile_record.profile.tp1.quantity_fraction
                != event.exit_plan.target_fraction
            ):
                raise UnsupportedKernelEffect(
                    "post-fill plan differs from frozen execution profile"
                )
        if isinstance(
            event,
            (
                TakeProfitFilled,
                TakeProfitProgressed,
                TakeProfitCompletedForExit,
                NaturalTakeProfitRecorded,
            ),
        ) and (
            aggregate.post_fill_exit_plan is not None
            or isinstance(event, NaturalTakeProfitRecorded)
        ):
            proof = event.tp_fill_evidence
            filled = (
                event.cumulative_filled_qty
                if isinstance(event, (TakeProfitProgressed, NaturalTakeProfitRecorded))
                else event.filled_qty
            )
            if (
                proof is None
                or proof.quantity != filled
                or current is None
                or proof.exchange_order_id != current.tp1_exchange_order_id
            ):
                raise UnsupportedKernelEffect(
                    "TP1 cumulative fill lacks exact durable trade proof"
                )
            reference = next(
                (
                    r
                    for r in await self.exchange_commands.list_order_references(
                        ticket_id
                    )
                    if r.command_id == proof.command_id
                    and r.command_kind is ExchangeCommandKind.TAKE_PROFIT
                ),
                None,
            )
            if (
                reference is None
                or reference.submitted_exchange_order_id != proof.exchange_order_id
                or proof.vwap != event.average_fill_price
            ):
                raise UnsupportedKernelEffect(
                    "TP1 trade proof differs from frozen command"
                )
        await self.events.append(event)
        if isinstance(event, PostFillStressAssessed) and event.exit_plan is not None:
            await self._require_connection().execute(
                sa.insert(post_fill_exit_plans).values(
                    ticket_id=ticket_id,
                    source_event_id=event.event_id,
                    plan=event.exit_plan.model_dump(mode="json"),
                    created_at_ms=event.occurred_at_ms,
                )
            )
        if ticket_id not in self._notice_changes:
            self._notice_changes[ticket_id] = (current, [])
        self._notice_changes[ticket_id][1].append(event)
        for effect in reduction.effects:
            if isinstance(effect, PrepareEntryCommand):
                claim = await self._initial_command_claim(effect.ticket)
                await self.exchange_commands.add(
                    _entry_command(
                        effect,
                        leverage_verification_digest=(
                            effect.leverage_verification_digest
                            or _initial_leverage_fact_digest(claim)
                        ),
                        occurred_at_ms=event.occurred_at_ms,
                    )
                )
                continue
            if isinstance(effect, PrepareSetLeverageCommand):
                claim = await self._initial_command_claim(effect.ticket)
                await self.exchange_commands.add(
                    _set_leverage_command(
                        effect,
                        entry_admission_snapshot_digest=(
                            claim.entry_admission_snapshot_digest
                        ),
                        leverage_fact_digest=_initial_leverage_fact_digest(claim),
                        occurred_at_ms=event.occurred_at_ms,
                    )
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
                if isinstance(event, OwnerAutomaticTpRestoreRequested):
                    op = await self.owner_position_operations.get(
                        event.operation_id, for_update=True
                    )
                    if (
                        op is None
                        or op["ticket_id"] != ticket_id
                        or op["payload"].get("facts", {}).get("tp_state") != "cancelled"
                    ):
                        raise UnsupportedKernelEffect(
                            "original TP restore lacks terminal source fact"
                        )
                    generation = await self.exchange_commands.next_generation(
                        ticket_id=ticket_id, kind=ExchangeCommandKind.TAKE_PROFIT
                    )
                else:
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
                            order_namespace="regular",
                            purpose="entry_remainder",
                        ),
                        generation=generation,
                        occurred_at_ms=event.occurred_at_ms,
                    )
                )
                continue
            if isinstance(effect, CancelVacuumEntryOrder):
                if aggregate.entry_exchange_order_id != effect.exchange_order_id:
                    raise UnsupportedKernelEffect(
                        "Vacuum cancel differs from authoritative ENTRY order"
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
                            exchange_order_id=effect.exchange_order_id,
                            order_namespace="regular",
                            purpose="selection_vacuum_entry",
                        ),
                        generation=generation,
                        occurred_at_ms=event.occurred_at_ms,
                        entry_vacuum_id=effect.entry_vacuum_id,
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
                        and prior.payload.exchange_order_id == effect.exchange_order_id
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
                    reserved_margin=aggregate.ticket.reserved_margin,
                    updated_at_ms=event.occurred_at_ms,
                )
                continue
            if isinstance(effect, ReleaseEntryLane):
                await self.entry_admission.release_global_lane(
                    ticket_id=effect.ticket_id
                )
                continue
            if isinstance(effect, OpenIncident):
                entry_block_scope = _incident_entry_block_scope(effect.incident_kind)
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
            if isinstance(effect, ResolveExactClosureIncidents):
                actual = await self.incidents.list_open_for_ticket(effect.ticket_id)
                if {i.incident_id for i in actual} != set(effect.incident_ids):
                    raise UnsupportedKernelEffect("closure incident set changed")
                for incident in actual:
                    await self.incidents.resolve(
                        incident.incident_id, resolved_at_ms=event.occurred_at_ms
                    )
                continue
            if isinstance(effect, ResolveTicketIncidentsAtClosure):
                await self.incidents.resolve_all_open_for_ticket(
                    effect.ticket_id,
                    resolved_at_ms=event.occurred_at_ms,
                    resolved_by_event_id=event.event_id,
                )
                continue
            if isinstance(effect, ReleaseCapitalAuthorities):
                await self.budgets.release(
                    effect.ticket_id,
                    released_at_ms=effect.released_at_ms,
                )
                await self.entry_admission.release_account_exposure(
                    venue_id=aggregate.ticket.identity.netting_domain.venue_id,
                    account_id=aggregate.ticket.identity.netting_domain.account_id,
                    notional=effect.notional,
                    risk_at_stop=effect.risk_at_stop,
                    reserved_margin=aggregate.ticket.reserved_margin,
                    updated_at_ms=effect.released_at_ms,
                )
                await self.tickets.release_active_netting_domain(
                    effect.ticket_id,
                    netting_domain_key=effect.netting_domain_key,
                )
                continue
            if isinstance(effect, ProjectTerminalOwnerState):
                await self.monitors.save_if_changed(
                    derive_terminal_owner_projection(
                        ticket_id=effect.ticket_id,
                        updated_at_ms=event.occurred_at_ms,
                    )
                )
                from src.trading_kernel.application.reconciliation_health import (
                    resolve_reconciliation_wait,
                )

                await resolve_reconciliation_wait(
                    self,
                    key=f"reconciliation-mismatch:{effect.ticket_id}",
                    now_ms=event.occurred_at_ms,
                )
                await resolve_reconciliation_wait(
                    self,
                    key=f"reconciliation-closure:{effect.ticket_id}",
                    now_ms=event.occurred_at_ms,
                )
                await resolve_reconciliation_wait(
                    self,
                    key=f"reconciliation-overdue:{effect.ticket_id}",
                    now_ms=event.occurred_at_ms,
                )
                continue
            raise UnsupportedKernelEffect(
                f"no durable materializer for {type(effect).__name__}"
            )

        if aggregate.status is AggregateStatus.LEVERAGE_REJECTED:
            await self.tickets.mark_terminal(
                ticket_id,
                status="leverage_rejected",
                terminal_at_ms=event.occurred_at_ms,
            )
        elif aggregate.status is AggregateStatus.ENTRY_REJECTED:
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

    async def _initial_command_claim(
        self,
        ticket: TradeTicket,
    ) -> CapacityClaim:
        claim = await self.capacity_claims.get(ticket.capacity_claim_id)
        if claim is None:
            raise UnsupportedKernelEffect(
                "initial command requires its immutable CapacityClaim"
            )
        if (
            claim.capacity_claim_id != ticket.capacity_claim_id
            or claim.ticket_identity != ticket.identity
            or claim.owner_policy_id != ticket.owner_policy_id
            or claim.owner_policy_version != ticket.owner_policy_version
            or claim.runtime_scope_id != ticket.runtime_scope_id
            or claim.runtime_scope_version != ticket.runtime_scope_version
            or claim.selected_leverage != ticket.selected_leverage
            or claim.leverage_change_required != ticket.leverage_change_required
        ):
            raise UnsupportedKernelEffect(
                "initial command Claim differs from immutable Ticket authority"
            )
        if ticket.leverage_change_required == (
            claim.configured_leverage_at_claim == ticket.selected_leverage
        ):
            raise UnsupportedKernelEffect(
                "initial command Claim has contradictory leverage-change evidence"
            )
        return claim


def _entry_command(
    effect: PrepareEntryCommand,
    *,
    leverage_verification_digest: str,
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
            required_configured_leverage=ticket.selected_leverage,
            leverage_verification_digest=leverage_verification_digest,
        ),
        status=ExchangeCommandStatus.PREPARED,
        created_at_ms=occurred_at_ms,
        deadline_at_ms=ticket.expires_at_ms,
    )


def _initial_leverage_fact_digest(claim: CapacityClaim) -> str:
    """Freeze the pre-mutation exact instrument leverage fact from admission."""

    return canonical_digest(
        {
            "entry_admission_snapshot_digest": (claim.entry_admission_snapshot_digest),
            "instrument_facts": {
                "exchange_instrument_id": (
                    claim.ticket_identity.netting_domain.exchange_instrument_id
                ),
                "mark_price": claim.mark_price_at_claim,
                "configured_leverage": claim.configured_leverage_at_claim,
            },
        }
    )


def _set_leverage_command(
    effect: PrepareSetLeverageCommand,
    *,
    entry_admission_snapshot_digest: str,
    leverage_fact_digest: str,
    occurred_at_ms: int,
) -> ExchangeCommand:
    ticket = effect.ticket
    command_id = build_command_id(
        ticket_id=ticket.identity.ticket_id,
        kind=ExchangeCommandKind.SET_LEVERAGE,
        generation=1,
    )
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=ticket.identity,
        kind=ExchangeCommandKind.SET_LEVERAGE,
        generation=1,
        idempotency_key=command_id,
        venue_client_order_id=None,
        payload=SetLeverageCommandPayload(
            desired_leverage=ticket.selected_leverage,
            owner_policy_version=ticket.owner_policy_version,
            entry_admission_snapshot_digest=entry_admission_snapshot_digest,
            leverage_fact_digest=leverage_fact_digest,
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
            owner_operation_id=effect.owner_operation_id,
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
            time_in_force="GTC" if aggregate.post_fill_exit_plan is not None else "GTX",
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
            reduce_only=not effect.close_position,
            close_position=effect.close_position,
            owner_operation_id=effect.owner_operation_id,
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
    entry_vacuum_id: str | None = None,
) -> ExchangeCommand:
    command_id = build_command_id(
        ticket_id=aggregate.identity.ticket_id,
        kind=ExchangeCommandKind.CANCEL_ORDER,
        generation=generation,
    )
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=aggregate.identity,
        management_revision=aggregate.management_revision,
        kind=ExchangeCommandKind.CANCEL_ORDER,
        generation=generation,
        idempotency_key=command_id,
        venue_client_order_id=build_venue_client_order_id(command_id),
        payload=CancelCommandPayload(
            exchange_order_id=effect.exchange_order_id,
            order_namespace=effect.order_namespace,
            purpose=effect.purpose,
            entry_vacuum_id=entry_vacuum_id,
        ),
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
        management_revision=aggregate.management_revision,
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
    return (
        "sell" if aggregate.identity.netting_domain.position_side == "long" else "buy"
    )


def _incident_entry_block_scope(incident_kind: str) -> EntryBlockScope:
    """Classify reducer safety failures without relying on free-form storage."""

    if incident_kind == "external_flat":
        return EntryBlockScope.NONE
    if incident_kind == "leverage_outcome_unknown":
        return EntryBlockScope.LEVERAGE_DOMAIN
    return EntryBlockScope.ACCOUNT_CAPACITY


def _event_ticket_id(event: TradeEvent) -> str:
    if isinstance(event, TicketIssued):
        return event.ticket.identity.ticket_id
    return event.ticket_id
