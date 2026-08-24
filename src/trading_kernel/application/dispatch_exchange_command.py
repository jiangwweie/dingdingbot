"""Claim and dispatch one durable exchange command without a long DB transaction."""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ingest_signal import (
    resolve_selection_entry_authority,
)
from src.trading_kernel.application.owner_control import strategy_entry_is_enabled
from src.trading_kernel.application.ports import (
    UnitOfWorkFactory,
    VenueCommandRequest,
    VenueMutationFailure,
    VenueMutationRejected,
    VenuePort,
    VenueSetLeverageRequest,
)
from src.trading_kernel.application.revalidate_entry_dispatch import (
    EntryDispatchPreflightRequest,
    EntryDispatchPreflightStatus,
    revalidate_entry_dispatch,
)
from src.trading_kernel.application.runtime_facts import (
    EntryAdmissionSnapshotRequest,
    EntryFactsSource,
    InstrumentRulesRequest,
    ProductSessionRequest,
)
from src.trading_kernel.domain.account_entry_health import classify_account_entry_health
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
    SetLeverageCommandPayload,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.events import (
    CancelOrderOutcomeUnknown,
    CancelOrderRejected,
    ControlledFlattenAccepted,
    ControlledFlattenOutcomeUnknown,
    ControlledFlattenRejected,
    EntryAccepted,
    EntryOutcomeUnknown,
    EntryRejected,
    EntryRemainderCancelConfirmed,
    EntryRemainderCancelOutcomeUnknown,
    EntryRemainderCancelRejected,
    EntryVacuumCancelConfirmed,
    EntryVacuumCancelOutcomeUnknown,
    EntryVacuumCancelRejected,
    EntryVacuumSuperseded,
    ExitAccepted,
    ExitOutcomeUnknown,
    ExitRejected,
    InitialStopConfirmed,
    InitialStopOutcomeUnknown,
    InitialStopRejected,
    LeverageConfirmed,
    LeverageOutcomeUnknown,
    LeverageRejected,
    OwnedOrphanCancelConfirmed,
    ProtectionCancelConfirmed,
    ProtectionCancelOutcomeUnknown,
    ProtectionCancelRejected,
    ProtectionReplacementConfirmed,
    ProtectionReplacementOutcomeUnknown,
    ProtectionReplacementRejected,
    TakeProfitConfirmed,
    TakeProfitOutcomeUnknown,
    TakeProfitRejected,
)
from src.trading_kernel.domain.instrument_entry_health import (
    classify_instrument_entry_health,
)
from src.trading_kernel.domain.product import (
    ProductEntryStatus,
    evaluate_event_product_entry,
    product_compatibility_for,
)
from src.trading_kernel.domain.reducer import reduce_event


class _EventCommon(TypedDict):
    event_id: str
    ticket_id: str
    sequence: int
    occurred_at_ms: int


class DispatchCommandStatus(StrEnum):
    NO_COMMAND = "no_command"
    SUPERSEDED = "superseded"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    OUTCOME_UNKNOWN = "outcome_unknown"


class DispatchCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_id: str
    ticket_id: str | None = None
    command_kinds: tuple[ExchangeCommandKind, ...] = ()
    now_ms: int
    lease_until_ms: int
    timeout_seconds: float
    runtime_commit: str | None = None
    schema_revision: str | None = None
    admission_snapshot_validity_ms: int | None = None

    @field_validator("worker_id", mode="before")
    @classmethod
    def _require_worker_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("dispatcher worker identity must be non-blank")
        return normalized

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _normalize_optional_ticket(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("dispatcher ticket identity must be non-blank")
        return normalized

    @field_validator("now_ms", "lease_until_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("dispatcher times must be positive")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _require_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("dispatcher timeout must be positive")
        return value

    @model_validator(mode="after")
    def _validate_lease(self) -> DispatchCommandRequest:
        if self.lease_until_ms <= self.now_ms:
            raise ValueError("command lease must end after claim time")
        return self


class DispatchCommandResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: DispatchCommandStatus
    command_id: str | None = None


async def dispatch_one_command(
    uow_factory: UnitOfWorkFactory,
    venue: VenuePort,
    request: DispatchCommandRequest,
    *,
    entry_facts_source: EntryFactsSource | None = None,
) -> DispatchCommandResult:
    async with uow_factory() as uow:
        expired = await uow.exchange_commands.get_one_expired_claim(
            now_ms=request.now_ms,
            ticket_id=request.ticket_id,
            command_kinds=request.command_kinds,
        )
        if expired is not None:
            expired_result = ExchangeCommandResult(
                status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
                observed_at_ms=request.now_ms,
                reason="stale_claim_after_restart",
            )
            aggregate = await uow.aggregates.get(expired.ticket_identity.ticket_id)
            if aggregate is None:
                raise RuntimeError("expired command has no Ticket aggregate")
            event = _command_result_event(
                command=expired,
                aggregate=aggregate,
                result=expired_result,
            )
            await uow.exchange_commands.record_expired_claim_unknown(
                command_id=expired.command_id,
                result=expired_result,
            )
            await uow.commit_reduction(
                event=event,
                reduction=reduce_event(aggregate, event),
                expected_version=aggregate.version,
            )
            return DispatchCommandResult(
                status=DispatchCommandStatus.OUTCOME_UNKNOWN,
                command_id=expired.command_id,
            )

    async with uow_factory() as uow:
        command = await uow.exchange_commands.claim_one_prepared(
            worker_id=request.worker_id,
            now_ms=request.now_ms,
            lease_until_ms=request.lease_until_ms,
            ticket_id=request.ticket_id,
            command_kinds=request.command_kinds,
        )
        if command is not None:
            aggregate = await uow.aggregates.get(
                command.ticket_identity.ticket_id
            )
            if aggregate is None:
                raise RuntimeError("claimed command has no Ticket aggregate")
            if not _command_is_applicable(command, aggregate.status):
                await uow.exchange_commands.mark_claimed_superseded(
                    command_id=command.command_id,
                    worker_id=request.worker_id,
                    observed_at_ms=request.now_ms,
                    reason=(
                        "aggregate_state_moved_on:"
                        f"{aggregate.status.value}"
                    ),
                )
                return DispatchCommandResult(
                    status=DispatchCommandStatus.SUPERSEDED,
                    command_id=command.command_id,
                )
            if command.kind in {
                ExchangeCommandKind.SET_LEVERAGE,
                ExchangeCommandKind.ENTRY,
            }:
                selection_control = (
                    await uow.instrument_selection.get_selection_control(
                        aggregate.ticket.identity.runtime.strategy_group_id
                    )
                )
                vacuum = (
                    None
                    if selection_control is None
                    else await uow.instrument_selection.get_current_entry_vacuum(
                        strategy_group_id=(
                            aggregate.ticket.identity.runtime.strategy_group_id
                        ),
                        selection_spec_id=selection_control.selection_spec_id,
                    )
                )
                if vacuum is not None and vacuum.blocks_new_entry:
                    await uow.exchange_commands.mark_claimed_superseded(
                        command_id=command.command_id,
                        worker_id=request.worker_id,
                        observed_at_ms=request.now_ms,
                        reason=(
                            "selection_entry_vacuum:"
                            f"{vacuum.entry_vacuum_id}"
                        ),
                    )
                    event = EntryVacuumSuperseded(
                        event_id=(
                            f"event:{aggregate.identity.ticket_id}:"
                            f"{aggregate.last_event_sequence + 1}"
                        ),
                        ticket_id=aggregate.identity.ticket_id,
                        sequence=aggregate.last_event_sequence + 1,
                        occurred_at_ms=request.now_ms,
                        entry_vacuum_id=vacuum.entry_vacuum_id,
                        command_id=command.command_id,
                    )
                    await uow.commit_reduction(
                        event=event,
                        reduction=reduce_event(aggregate, event),
                        expected_version=aggregate.version,
                    )
                    return DispatchCommandResult(
                        status=DispatchCommandStatus.SUPERSEDED,
                        command_id=command.command_id,
                    )
    if command is None:
        return DispatchCommandResult(status=DispatchCommandStatus.NO_COMMAND)

    if command.kind in {
        ExchangeCommandKind.SET_LEVERAGE,
        ExchangeCommandKind.ENTRY,
    }:
        preflight = await _preflight_new_entry_mutation(
            uow_factory,
            command=command,
            request=request,
            entry_facts_source=entry_facts_source,
        )
        if preflight is not EntryDispatchPreflightStatus.ALLOWED:
            await _record_preflight_refusal(
                uow_factory,
                command=command,
                worker_id=request.worker_id,
                now_ms=request.now_ms,
                status=preflight,
            )
            return DispatchCommandResult(
                status=DispatchCommandStatus.SUPERSEDED,
                command_id=command.command_id,
            )

    try:
        if command.kind is ExchangeCommandKind.SET_LEVERAGE:
            if not isinstance(command.payload, SetLeverageCommandPayload):
                raise RuntimeError("SET_LEVERAGE command payload is invalid")
            dispatch_result: ExchangeCommandResult | SetLeverageCommandResult = (
                await asyncio.wait_for(
                    venue.set_leverage(
                        VenueSetLeverageRequest(
                            command_id=command.command_id,
                            venue_id=command.ticket_identity.netting_domain.venue_id,
                            account_id=command.ticket_identity.netting_domain.account_id,
                            exchange_instrument_id=(
                                command.ticket_identity.netting_domain.exchange_instrument_id
                            ),
                            payload=command.payload,
                            deadline_at_ms=command.deadline_at_ms,
                        )
                    ),
                    timeout=request.timeout_seconds,
                )
            )
        else:
            venue_request = VenueCommandRequest(
                command_id=command.command_id,
                kind=command.kind,
                venue_id=command.ticket_identity.netting_domain.venue_id,
                account_id=command.ticket_identity.netting_domain.account_id,
                exchange_instrument_id=(
                    command.ticket_identity.netting_domain.exchange_instrument_id
                ),
                position_side=command.ticket_identity.netting_domain.position_side,
                venue_client_order_id=command.venue_client_order_id,
                payload=command.payload,
                deadline_at_ms=command.deadline_at_ms,
            )
            dispatch_result = await asyncio.wait_for(
                venue.execute(venue_request),
                timeout=request.timeout_seconds,
            )
    except VenueMutationRejected as exc:
        dispatch_result = ExchangeCommandResult(
            status=ExchangeCommandStatus.REJECTED,
            observed_at_ms=request.now_ms,
            reason=f"venue_rejected:{type(exc).__name__}",
        )
    except VenueMutationFailure as exc:
        dispatch_result = ExchangeCommandResult(
            status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
            observed_at_ms=request.now_ms,
            reason=f"venue_error:{exc.reason}",
        )
    except TimeoutError:
        dispatch_result = ExchangeCommandResult(
            status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
            observed_at_ms=request.now_ms,
            reason="venue_timeout",
        )
    except Exception as exc:  # noqa: BLE001 - unknown venue outcome must fail closed.
        dispatch_result = ExchangeCommandResult(
            status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
            observed_at_ms=request.now_ms,
            reason=f"venue_error:{type(exc).__name__}",
        )

    if (
        command.kind is ExchangeCommandKind.SET_LEVERAGE
        and isinstance(dispatch_result, SetLeverageCommandResult)
        and isinstance(command.payload, SetLeverageCommandPayload)
        and dispatch_result.exchange_configured_leverage != command.payload.desired_leverage
    ):
        dispatch_result = ExchangeCommandResult(
            status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
            observed_at_ms=dispatch_result.leverage_verified_at_ms,
            reason="leverage_readback_mismatch",
        )

    async with uow_factory() as uow:
        aggregate = await uow.aggregates.get(command.ticket_identity.ticket_id)
        if aggregate is None:
            raise RuntimeError("claimed command has no Ticket aggregate")
        event = _command_result_event(
            command=command,
            aggregate=aggregate,
            result=dispatch_result,
        )
        if isinstance(dispatch_result, SetLeverageCommandResult):
            await uow.exchange_commands.record_leverage_result(
                command_id=command.command_id,
                worker_id=request.worker_id,
                result=dispatch_result,
            )
        else:
            await uow.exchange_commands.record_result(
                command_id=command.command_id,
                worker_id=request.worker_id,
                result=dispatch_result,
            )
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )

    return DispatchCommandResult(
        status=(
            DispatchCommandStatus.ACCEPTED
            if isinstance(dispatch_result, SetLeverageCommandResult)
            else DispatchCommandStatus(dispatch_result.status.value)
        ),
        command_id=command.command_id,
    )


async def _preflight_new_entry_mutation(
    uow_factory: UnitOfWorkFactory,
    *,
    command: ExchangeCommand,
    request: DispatchCommandRequest,
    entry_facts_source: EntryFactsSource | None,
) -> EntryDispatchPreflightStatus:
    if (
        entry_facts_source is None
        or not request.runtime_commit
        or not request.schema_revision
        or request.admission_snapshot_validity_ms is None
        or request.admission_snapshot_validity_ms <= 0
    ):
        return EntryDispatchPreflightStatus.RUNTIME_FENCED
    domain = command.ticket_identity.netting_domain
    snapshot_request = EntryAdmissionSnapshotRequest(
        venue_id=domain.venue_id,
        account_id=domain.account_id,
        exchange_instrument_id=domain.exchange_instrument_id,
        observed_at_ms=request.now_ms,
        valid_for_ms=request.admission_snapshot_validity_ms,
    )
    rules_request = InstrumentRulesRequest(
        venue_id=domain.venue_id,
        account_id=domain.account_id,
        exchange_instrument_id=domain.exchange_instrument_id,
        observed_at_ms=request.now_ms,
        valid_for_ms=request.admission_snapshot_validity_ms,
    )
    try:
        product_compatibility = product_compatibility_for(
            command.ticket_identity.runtime.event_spec_id
        )
    except ValueError:
        return EntryDispatchPreflightStatus.PRODUCT_ENTRY_BLOCKED
    product_request = ProductSessionRequest(
        venue_id=domain.venue_id,
        account_id=domain.account_id,
        exchange_instrument_id=domain.exchange_instrument_id,
        observed_at_ms=request.now_ms,
    )
    async with uow_factory() as uow:
        product_profile = await uow.signals.get_product_profile(
            domain.exchange_instrument_id
        )
    try:
        snapshot, rules, product_session = await asyncio.wait_for(
            asyncio.gather(
                entry_facts_source.read_entry_admission_snapshot(snapshot_request),
                entry_facts_source.read_instrument_rules(rules_request),
                (
                    _read_product_session(
                        entry_facts_source,
                        product_request,
                    )
                    if product_compatibility.product_family
                    == "tradfi_equity_perpetual"
                    else _no_product_session()
                ),
            ),
            timeout=request.timeout_seconds,
        )
    except Exception:  # noqa: BLE001 - unreadable admission facts must fence Entry.
        return EntryDispatchPreflightStatus.STALE_SNAPSHOT
    source_product_decision = evaluate_event_product_entry(
        compatibility=product_compatibility,
        profile=product_profile,
        snapshot=product_session,
        now_ms=request.now_ms,
    )
    if source_product_decision.status is ProductEntryStatus.IDENTITY_MISMATCH:
        return EntryDispatchPreflightStatus.PRODUCT_ENTRY_BLOCKED
    async with uow_factory() as uow:
        if product_session is not None:
            await uow.signals.upsert_product_sessions((product_session,))
        current_command = await uow.exchange_commands.get(command.command_id)
        aggregate = await uow.aggregates.get(command.ticket_identity.ticket_id)
        claim = await uow.capacity_claims.get_for_ticket(
            command.ticket_identity.ticket_id
        )
        if current_command is None or aggregate is None or claim is None:
            return EntryDispatchPreflightStatus.COMMAND_MISMATCH
        policy = await uow.entry_admission.get_owner_policy(
            aggregate.ticket.owner_policy_id
        )
        scope = await uow.signals.get_runtime_scope(aggregate.ticket.runtime_scope_id)
        active_universe = await uow.signals.get_active_universe_member(
            event_spec_id=aggregate.ticket.identity.runtime.event_spec_id,
            exchange_instrument_id=domain.exchange_instrument_id,
        )
        strategy_group = await uow.signals.get_strategy_group(
            aggregate.ticket.identity.runtime.strategy_group_id
        )
        owner_controls = getattr(uow, "owner_controls", None)
        strategy_control = (
            None
            if owner_controls is None
            else await owner_controls.get_strategy_control(
                aggregate.ticket.identity.runtime.strategy_group_id
            )
        )
        selection_control = await uow.instrument_selection.get_selection_control(
            aggregate.ticket.identity.runtime.strategy_group_id
        )
        selection_vacuum = (
            None
            if selection_control is None
            else await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=(
                    aggregate.ticket.identity.runtime.strategy_group_id
                ),
                selection_spec_id=selection_control.selection_spec_id,
            )
        )
        selection_authority_valid = True
        if selection_control is not None:
            source_signal = await uow.signals.get(
                aggregate.ticket.identity.signal_event_id
            )
            if (
                source_signal is None
                or source_signal.selection_authority_id
                != aggregate.ticket.selection_authority_id
                or source_signal.selection_authority_id
                != claim.selection_authority_id
            ) or scope is None:
                selection_authority_valid = False
            else:
                selection = await resolve_selection_entry_authority(
                    uow,
                    runtime_scope=scope,
                    birth_selection_authority_id=(
                        source_signal.selection_authority_id
                    ),
                    observed_close_time_ms=source_signal.occurred_at_ms,
                    now_ms=request.now_ms,
                    allow_current_as_birth=False,
                )
                selection_authority_valid = selection.allowed
        strategy_version = await uow.signals.get_strategy_version(
            aggregate.ticket.identity.runtime.strategy_version_id
        )
        event_spec = await uow.signals.get_event_spec(
            aggregate.ticket.identity.runtime.event_spec_id
        )
        capability = await uow.signals.get_runtime_capability("exchange_commands")
        current_product_profile = await uow.signals.get_product_profile(
            domain.exchange_instrument_id
        )
        current_product_session = await uow.signals.get_product_session(
            domain.exchange_instrument_id
        )
        ownership = await uow.entry_admission.read_admission_ownership(
            venue_id=domain.venue_id,
            account_id=domain.account_id,
            exchange_instrument_id=domain.exchange_instrument_id,
        )
        active_family_ticket_count = (
            await uow.entry_admission.count_active_family_tickets(
                venue_id=domain.venue_id,
                account_id=domain.account_id,
                exposure_family=aggregate.ticket.exposure_family,
            )
        )
        active_directional_risk_at_stop = (
            await uow.entry_admission.sum_active_directional_stop_risk(
                venue_id=domain.venue_id,
                account_id=domain.account_id,
                position_side=domain.position_side,
            )
        )
    product_entry_decision = evaluate_event_product_entry(
        compatibility=product_compatibility,
        profile=current_product_profile,
        snapshot=current_product_session,
        now_ms=request.now_ms,
    )
    decision = revalidate_entry_dispatch(
        EntryDispatchPreflightRequest(
            command=current_command,
            ticket=aggregate.ticket,
            capacity_claim=claim,
            owner_policy=policy,
            runtime_scope=scope,
            active_universe=active_universe,
            strategy_group=strategy_group,
            strategy_version=strategy_version,
            event_spec=event_spec,
            runtime_capability=capability,
            runtime_commit=request.runtime_commit,
            schema_revision=request.schema_revision,
            admission_snapshot=snapshot,
            instrument_rules=rules,
            account_entry_health=classify_account_entry_health(snapshot, ownership),
            instrument_entry_health=classify_instrument_entry_health(
                snapshot,
                ownership,
                exchange_instrument_id=domain.exchange_instrument_id,
                requested_position_side=domain.position_side,
            ),
            active_family_ticket_count=active_family_ticket_count,
            active_directional_risk_at_stop=active_directional_risk_at_stop,
            now_ms=request.now_ms,
            product_entry_decision=product_entry_decision,
            strategy_entry_enabled=strategy_entry_is_enabled(strategy_control),
            selection_entry_vacuum_open=bool(
                selection_vacuum and selection_vacuum.blocks_new_entry
            ),
            selection_authority_valid=selection_authority_valid,
        )
    )
    return decision.status


async def _no_product_session():
    return None


async def _read_product_session(entry_facts_source, request):
    reader = getattr(entry_facts_source, "read_product_session", None)
    if not callable(reader):
        raise TypeError("TradFi dispatch Product source is unavailable")
    return await reader(request)


async def _record_preflight_refusal(
    uow_factory: UnitOfWorkFactory,
    *,
    command: ExchangeCommand,
    worker_id: str,
    now_ms: int,
    status: EntryDispatchPreflightStatus,
) -> None:
    result = ExchangeCommandResult(
        status=ExchangeCommandStatus.REJECTED,
        observed_at_ms=now_ms,
        reason=f"dispatch_preflight:{status.value}",
    )
    async with uow_factory() as uow:
        current_command = await uow.exchange_commands.get(command.command_id)
        aggregate = await uow.aggregates.get(command.ticket_identity.ticket_id)
        if current_command is None or aggregate is None:
            raise RuntimeError("claimed command changed before preflight refusal")
        if status is EntryDispatchPreflightStatus.SELECTION_ENTRY_VACUUM:
            selection_control = (
                await uow.instrument_selection.get_selection_control(
                    aggregate.ticket.identity.runtime.strategy_group_id
                )
            )
            vacuum = (
                None
                if selection_control is None
                else await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=(
                        aggregate.ticket.identity.runtime.strategy_group_id
                    ),
                    selection_spec_id=selection_control.selection_spec_id,
                )
            )
            if vacuum is None or not vacuum.blocks_new_entry:
                raise RuntimeError(
                    "Selection Entry Vacuum changed before dispatch supersession"
                )
            await uow.exchange_commands.mark_claimed_superseded(
                command_id=current_command.command_id,
                worker_id=worker_id,
                observed_at_ms=now_ms,
                reason=f"selection_entry_vacuum:{vacuum.entry_vacuum_id}",
            )
            event = EntryVacuumSuperseded(
                event_id=(
                    f"event:{aggregate.identity.ticket_id}:"
                    f"{aggregate.last_event_sequence + 1}"
                ),
                ticket_id=aggregate.identity.ticket_id,
                sequence=aggregate.last_event_sequence + 1,
                occurred_at_ms=now_ms,
                entry_vacuum_id=vacuum.entry_vacuum_id,
                command_id=current_command.command_id,
            )
            await uow.commit_reduction(
                event=event,
                reduction=reduce_event(aggregate, event),
                expected_version=aggregate.version,
            )
            return
        event = _command_result_event(
            command=current_command,
            aggregate=aggregate,
            result=result,
        )
        await uow.exchange_commands.record_result(
            command_id=current_command.command_id,
            worker_id=worker_id,
            result=result,
        )
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )


def _command_is_applicable(
    command: ExchangeCommand,
    aggregate_status: AggregateStatus,
) -> bool:
    applicable_statuses = {
        ExchangeCommandKind.SET_LEVERAGE: {AggregateStatus.LEVERAGE_PENDING},
        ExchangeCommandKind.ENTRY: {
            AggregateStatus.ENTRY_PENDING,
            AggregateStatus.LEVERAGE_CONFIRMED,
        },
        ExchangeCommandKind.INITIAL_STOP: {AggregateStatus.PROTECTION_PENDING},
        ExchangeCommandKind.TAKE_PROFIT: {AggregateStatus.TP1_PENDING},
        ExchangeCommandKind.REPLACE_PROTECTION: {
            AggregateStatus.RUNNER_REPLACEMENT_PENDING
        },
        ExchangeCommandKind.EXIT: {AggregateStatus.EXIT_PENDING},
        ExchangeCommandKind.CONTROLLED_FLATTEN: {
            AggregateStatus.CONTROLLED_FLATTEN_PENDING
        },
        ExchangeCommandKind.CANCEL_ORDER: {
            AggregateStatus.PARTIAL_FILL_INCIDENT,
            AggregateStatus.ENTRY_VACUUM_CANCEL_PENDING,
            AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING,
            AggregateStatus.RECONCILIATION_PENDING,
        },
    }
    if command.kind is not ExchangeCommandKind.CANCEL_ORDER:
        return aggregate_status in applicable_statuses[command.kind]
    if not isinstance(command.payload, CancelCommandPayload):
        return False
    applicable_cancel_status = {
        "entry_remainder": AggregateStatus.PARTIAL_FILL_INCIDENT,
        "selection_vacuum_entry": AggregateStatus.ENTRY_VACUUM_CANCEL_PENDING,
        "runner_old_stop": AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING,
        "reconciliation_cleanup": AggregateStatus.RECONCILIATION_PENDING,
    }
    return aggregate_status is applicable_cancel_status[command.payload.purpose]


def _command_result_event(
    *,
    command: ExchangeCommand,
    aggregate,
    result: ExchangeCommandResult | SetLeverageCommandResult,
):
    kind = command.kind
    ticket_id = aggregate.identity.ticket_id
    next_sequence = aggregate.last_event_sequence + 1
    common: _EventCommon = {
        "event_id": f"event:{ticket_id}:{next_sequence}",
        "ticket_id": ticket_id,
        "sequence": next_sequence,
        "occurred_at_ms": (
            result.leverage_verified_at_ms
            if isinstance(result, SetLeverageCommandResult)
            else result.observed_at_ms
        ),
    }
    if kind is ExchangeCommandKind.SET_LEVERAGE:
        if isinstance(result, SetLeverageCommandResult):
            return LeverageConfirmed(
                **common,
                exchange_configured_leverage=result.exchange_configured_leverage,
                leverage_verified_at_ms=result.leverage_verified_at_ms,
                leverage_verification_digest=result.leverage_verification_digest,
            )
        if result.status is ExchangeCommandStatus.REJECTED:
            return LeverageRejected(**common, reason=str(result.reason))
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return LeverageOutcomeUnknown(**common, reason=str(result.reason))
        raise RuntimeError("SET_LEVERAGE result is invalid")
    if not isinstance(result, ExchangeCommandResult):
        raise TypeError("order command result is invalid")
    if kind is ExchangeCommandKind.ENTRY and result.status is ExchangeCommandStatus.ACCEPTED:
        return EntryAccepted(
            **common,
            exchange_order_id=str(result.exchange_order_id),
        )
    if kind is ExchangeCommandKind.ENTRY and result.status is ExchangeCommandStatus.REJECTED:
        return EntryRejected(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.ENTRY and result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
        return EntryOutcomeUnknown(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.EXIT and result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
        return ExitOutcomeUnknown(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.TAKE_PROFIT:
        if not isinstance(command.payload, OrderCommandPayload):
            raise RuntimeError("TP1 command payload is invalid")
        if result.status is ExchangeCommandStatus.ACCEPTED:
            return TakeProfitConfirmed(
                **common,
                exchange_order_id=str(result.exchange_order_id),
                target_qty=command.payload.quantity,
            )
        if result.status is ExchangeCommandStatus.REJECTED:
            return TakeProfitRejected(**common, reason=str(result.reason))
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return TakeProfitOutcomeUnknown(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.REPLACE_PROTECTION:
        payload = command.payload
        if not isinstance(payload, OrderCommandPayload):
            raise RuntimeError("protection replacement payload is invalid")
        if payload.stop_price is None:
            raise RuntimeError("protection replacement stop price is missing")
        if payload.replaces_exchange_order_id is None:
            raise RuntimeError("protection replacement prior order is missing")
        if payload.source_watermark_ms is None:
            raise RuntimeError("protection replacement watermark is missing")
        if result.status is ExchangeCommandStatus.ACCEPTED:
            return ProtectionReplacementConfirmed(
                **common,
                exchange_order_id=str(result.exchange_order_id),
                protected_qty=payload.quantity,
                stop_price=payload.stop_price,
                replaces_exchange_order_id=payload.replaces_exchange_order_id,
                source_watermark_ms=payload.source_watermark_ms,
            )
        if result.status is ExchangeCommandStatus.REJECTED:
            return ProtectionReplacementRejected(
                **common,
                reason=str(result.reason),
            )
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return ProtectionReplacementOutcomeUnknown(
                **common,
                reason=str(result.reason),
            )
    if kind is ExchangeCommandKind.INITIAL_STOP and result.status is ExchangeCommandStatus.REJECTED:
        return InitialStopRejected(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.INITIAL_STOP and result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
        return InitialStopOutcomeUnknown(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.EXIT and result.status is ExchangeCommandStatus.REJECTED:
        return ExitRejected(**common, reason=str(result.reason))
    if kind is ExchangeCommandKind.CANCEL_ORDER:
        if not isinstance(command.payload, CancelCommandPayload):
            raise RuntimeError("cancel command payload is invalid")
        return _cancel_result_event(
            payload=command.payload,
            aggregate_status=aggregate.status,
            result=result,
            common=common,
        )
    if kind is ExchangeCommandKind.CONTROLLED_FLATTEN:
        if result.status is ExchangeCommandStatus.ACCEPTED:
            return ControlledFlattenAccepted(
                **common,
                exchange_order_id=str(result.exchange_order_id),
            )
        if result.status is ExchangeCommandStatus.REJECTED:
            return ControlledFlattenRejected(**common, reason=str(result.reason))
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return ControlledFlattenOutcomeUnknown(
                **common,
                reason=str(result.reason),
            )
    if result.status is not ExchangeCommandStatus.ACCEPTED:
        raise RuntimeError(
            f"unsupported {kind.value} result status: {result.status.value}"
        )
    if kind is ExchangeCommandKind.INITIAL_STOP:
        return InitialStopConfirmed(
            **common,
            exchange_order_id=str(result.exchange_order_id),
            protected_qty=aggregate.position_qty,
        )
    if kind is ExchangeCommandKind.EXIT:
        return ExitAccepted(
            **common,
            exchange_order_id=str(result.exchange_order_id),
        )
    raise RuntimeError(f"unsupported command kind: {kind.value}")


def _cancel_result_event(
    *,
    payload: CancelCommandPayload,
    aggregate_status: AggregateStatus,
    result: ExchangeCommandResult,
    common: _EventCommon,
):
    expected_status = {
        "entry_remainder": AggregateStatus.PARTIAL_FILL_INCIDENT,
        "selection_vacuum_entry": AggregateStatus.ENTRY_VACUUM_CANCEL_PENDING,
        "runner_old_stop": AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING,
        "reconciliation_cleanup": AggregateStatus.RECONCILIATION_PENDING,
    }[payload.purpose]
    if aggregate_status is not expected_status:
        raise RuntimeError("cancel purpose is incompatible with aggregate state")
    if not isinstance(result, ExchangeCommandResult):
        raise TypeError("cancel command result is invalid")
    exchange_order_id = payload.exchange_order_id
    if payload.purpose == "selection_vacuum_entry":
        if result.status is ExchangeCommandStatus.ACCEPTED:
            return EntryVacuumCancelConfirmed(
                **common,
                exchange_order_id=exchange_order_id,
            )
        if result.status is ExchangeCommandStatus.REJECTED:
            return EntryVacuumCancelRejected(
                **common,
                exchange_order_id=exchange_order_id,
                reason=str(result.reason),
            )
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return EntryVacuumCancelOutcomeUnknown(
                **common,
                exchange_order_id=exchange_order_id,
                reason=str(result.reason),
            )
    if payload.purpose == "entry_remainder":
        if result.status is ExchangeCommandStatus.ACCEPTED:
            return EntryRemainderCancelConfirmed(
                **common, exchange_order_id=exchange_order_id
            )
        if result.status is ExchangeCommandStatus.REJECTED:
            return EntryRemainderCancelRejected(
                **common, exchange_order_id=exchange_order_id, reason=str(result.reason)
            )
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return EntryRemainderCancelOutcomeUnknown(
                **common, exchange_order_id=exchange_order_id, reason=str(result.reason)
            )
    if payload.purpose == "runner_old_stop":
        if result.status is ExchangeCommandStatus.ACCEPTED:
            return ProtectionCancelConfirmed(
                **common, exchange_order_id=exchange_order_id
            )
        if result.status is ExchangeCommandStatus.REJECTED:
            return ProtectionCancelRejected(
                **common, exchange_order_id=exchange_order_id, reason=str(result.reason)
            )
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return ProtectionCancelOutcomeUnknown(
                **common, exchange_order_id=exchange_order_id, reason=str(result.reason)
            )
    if payload.purpose == "reconciliation_cleanup":
        if result.status is ExchangeCommandStatus.ACCEPTED:
            return OwnedOrphanCancelConfirmed(
                **common, exchange_order_id=exchange_order_id
            )
        if result.status is ExchangeCommandStatus.REJECTED:
            return CancelOrderRejected(
                **common, exchange_order_id=exchange_order_id, reason=str(result.reason)
            )
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return CancelOrderOutcomeUnknown(
                **common, exchange_order_id=exchange_order_id, reason=str(result.reason)
            )
    raise RuntimeError("cancel command has an unsupported result status")
