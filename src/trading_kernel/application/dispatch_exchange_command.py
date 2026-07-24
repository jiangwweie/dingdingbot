"""Claim and dispatch one durable exchange command without a long DB transaction."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.ports import (
    UnitOfWorkFactory,
    VenueCommandRequest,
    VenueMutationRejected,
    VenuePort,
    VenueSetLeverageRequest,
)
from src.trading_kernel.application.runtime_facts import (
    EntryAdmissionSnapshotRequest,
    EntryFactsSource,
    InstrumentRulesRequest,
)
from src.trading_kernel.application.revalidate_entry_dispatch import (
    EntryDispatchPreflightRequest,
    EntryDispatchPreflightStatus,
    revalidate_entry_dispatch,
)
from src.trading_kernel.domain.account_entry_health import classify_account_entry_health
from src.trading_kernel.domain.instrument_entry_health import classify_instrument_entry_health
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
    SetLeverageCommandResult,
    SetLeverageCommandPayload,
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
    LeverageConfirmed,
    LeverageOutcomeUnknown,
    LeverageRejected,
    EntryRemainderCancelConfirmed,
    EntryRemainderCancelOutcomeUnknown,
    EntryRemainderCancelRejected,
    ExitAccepted,
    ExitOutcomeUnknown,
    ExitRejected,
    InitialStopConfirmed,
    InitialStopOutcomeUnknown,
    InitialStopRejected,
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
from src.trading_kernel.domain.reducer import reduce_event


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
    def _validate_lease(self) -> "DispatchCommandRequest":
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
            result = ExchangeCommandResult(
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
                result=result,
            )
            await uow.exchange_commands.record_expired_claim_unknown(
                command_id=expired.command_id,
                result=result,
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
    if command is None:
        return DispatchCommandResult(status=DispatchCommandStatus.NO_COMMAND)

    if (
        command.kind in {ExchangeCommandKind.SET_LEVERAGE, ExchangeCommandKind.ENTRY}
        and entry_facts_source is not None
    ):
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
            result: ExchangeCommandResult | SetLeverageCommandResult = (
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
            result = await asyncio.wait_for(
                venue.execute(venue_request),
                timeout=request.timeout_seconds,
            )
    except VenueMutationRejected as exc:
        result = ExchangeCommandResult(
            status=ExchangeCommandStatus.REJECTED,
            observed_at_ms=request.now_ms,
            reason=f"venue_rejected:{type(exc).__name__}",
        )
    except TimeoutError:
        result = ExchangeCommandResult(
            status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
            observed_at_ms=request.now_ms,
            reason="venue_timeout",
        )
    except Exception as exc:
        result = ExchangeCommandResult(
            status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
            observed_at_ms=request.now_ms,
            reason=f"venue_error:{type(exc).__name__}",
        )

    if (
        command.kind is ExchangeCommandKind.SET_LEVERAGE
        and isinstance(result, SetLeverageCommandResult)
        and isinstance(command.payload, SetLeverageCommandPayload)
        and result.exchange_configured_leverage != command.payload.desired_leverage
    ):
        result = ExchangeCommandResult(
            status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
            observed_at_ms=result.leverage_verified_at_ms,
            reason="leverage_readback_mismatch",
        )

    async with uow_factory() as uow:
        aggregate = await uow.aggregates.get(command.ticket_identity.ticket_id)
        if aggregate is None:
            raise RuntimeError("claimed command has no Ticket aggregate")
        event = _command_result_event(
            command=command,
            aggregate=aggregate,
            result=result,
        )
        if isinstance(result, SetLeverageCommandResult):
            await uow.exchange_commands.record_leverage_result(
                command_id=command.command_id,
                worker_id=request.worker_id,
                result=result,
            )
        else:
            await uow.exchange_commands.record_result(
                command_id=command.command_id,
                worker_id=request.worker_id,
                result=result,
            )
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )

    return DispatchCommandResult(
        status=(
            DispatchCommandStatus.ACCEPTED
            if isinstance(result, SetLeverageCommandResult)
            else DispatchCommandStatus(result.status.value)
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
        snapshot, rules = await asyncio.wait_for(
            asyncio.gather(
                entry_facts_source.read_entry_admission_snapshot(snapshot_request),
                entry_facts_source.read_instrument_rules(rules_request),
            ),
            timeout=request.timeout_seconds,
        )
    except Exception:
        return EntryDispatchPreflightStatus.STALE_SNAPSHOT
    async with uow_factory() as uow:
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
        strategy_group = await uow.signals.get_strategy_group(
            aggregate.ticket.identity.runtime.strategy_group_id
        )
        strategy_version = await uow.signals.get_strategy_version(
            aggregate.ticket.identity.runtime.strategy_version_id
        )
        event_spec = await uow.signals.get_event_spec(
            aggregate.ticket.identity.runtime.event_spec_id
        )
        capability = await uow.signals.get_runtime_capability("exchange_commands")
        ownership = await uow.entry_admission.read_admission_ownership(
            venue_id=domain.venue_id,
            account_id=domain.account_id,
            exchange_instrument_id=domain.exchange_instrument_id,
        )
    decision = revalidate_entry_dispatch(
        EntryDispatchPreflightRequest(
            command=current_command,
            ticket=aggregate.ticket,
            capacity_claim=claim,
            owner_policy=policy,
            runtime_scope=scope,
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
            now_ms=request.now_ms,
        )
    )
    return decision.status


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
            AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING,
            AggregateStatus.RECONCILIATION_PENDING,
        },
    }
    return aggregate_status in applicable_statuses[command.kind]


def _command_result_event(
    *,
    command: ExchangeCommand,
    aggregate,
    result: ExchangeCommandResult | SetLeverageCommandResult,
):
    kind = command.kind
    ticket_id = aggregate.identity.ticket_id
    next_sequence = aggregate.last_event_sequence + 1
    common = {
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
        if aggregate.status is AggregateStatus.PARTIAL_FILL_INCIDENT:
            if result.status is ExchangeCommandStatus.ACCEPTED:
                return EntryRemainderCancelConfirmed(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                )
            if result.status is ExchangeCommandStatus.REJECTED:
                return EntryRemainderCancelRejected(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                    reason=str(result.reason),
                )
            if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
                return EntryRemainderCancelOutcomeUnknown(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                    reason=str(result.reason),
                )
        if (
            aggregate.status is AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING
        ):
            if result.status is ExchangeCommandStatus.ACCEPTED:
                return ProtectionCancelConfirmed(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                )
            if result.status is ExchangeCommandStatus.REJECTED:
                return ProtectionCancelRejected(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                    reason=str(result.reason),
                )
            if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
                return ProtectionCancelOutcomeUnknown(
                    **common,
                    exchange_order_id=command.payload.exchange_order_id,
                    reason=str(result.reason),
                )
        if result.status is ExchangeCommandStatus.REJECTED:
            return CancelOrderRejected(
                **common,
                exchange_order_id=command.payload.exchange_order_id,
                reason=str(result.reason),
            )
        if result.status is ExchangeCommandStatus.OUTCOME_UNKNOWN:
            return CancelOrderOutcomeUnknown(
                **common,
                exchange_order_id=command.payload.exchange_order_id,
                reason=str(result.reason),
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
    if kind is ExchangeCommandKind.CANCEL_ORDER:
        if not isinstance(command.payload, CancelCommandPayload):
            raise RuntimeError("cancel command payload is invalid")
        cancel_payload = command.payload
        known_order_ids = {
            aggregate.initial_stop_exchange_order_id,
            aggregate.active_stop_exchange_order_id,
            aggregate.tp1_exchange_order_id,
            aggregate.pending_replaced_stop_exchange_order_id,
        }
        if cancel_payload.exchange_order_id not in known_order_ids:
            return OwnedOrphanCancelConfirmed(
                **common,
                exchange_order_id=cancel_payload.exchange_order_id,
            )
        return ProtectionCancelConfirmed(
            **common,
            exchange_order_id=str(result.exchange_order_id),
        )
    raise RuntimeError(f"unsupported command kind: {kind.value}")
