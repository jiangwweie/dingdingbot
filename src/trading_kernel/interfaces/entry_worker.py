"""Own candidate arbitration, action-time facts, Ticket issuance, and ENTRY."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.issue_ready_signal import (
    IssueReadySignalRequest,
    issue_ready_signal,
)
from src.trading_kernel.application.issue_ticket import IssueTicketStatus
from src.trading_kernel.application.ports import UnitOfWorkFactory, VenuePort
from src.trading_kernel.application.runtime_facts import (
    ActionTimeFactsRequest,
    EntryFactsSource,
    InstrumentRulesRequest,
)
from src.trading_kernel.application.select_entry_candidate import (
    SelectEntryCandidateRequest,
    SelectEntryCandidateStatus,
    select_entry_candidate,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind


class EntryWorkerStatus(StrEnum):
    NO_CANDIDATE = "no_candidate"
    ENTRY_LANE_BUSY = "entry_lane_busy"
    FACTS_UNAVAILABLE = "facts_unavailable"
    ISSUE_REFUSED = "issue_refused"
    DISPATCHED = "dispatched"
    SUPERSEDED = "superseded"


class EntryWorkerRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_id: str
    runtime_commit: str
    schema_revision: str
    now_ms: int
    lease_until_ms: int
    timeout_seconds: float
    action_fact_validity_ms: int

    @field_validator(
        "worker_id",
        "runtime_commit",
        "schema_revision",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("ENTRY worker identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> "EntryWorkerRequest":
        if self.now_ms <= 0 or self.lease_until_ms <= self.now_ms:
            raise ValueError("ENTRY worker lease must end after its tick")
        if self.timeout_seconds <= 0 or self.action_fact_validity_ms <= 0:
            raise ValueError("ENTRY worker timeouts must be positive")
        return self


class EntryWorkerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: EntryWorkerStatus
    ticket_id: str | None = None
    command_id: str | None = None
    issue_status: IssueTicketStatus | None = None
    dispatch_status: DispatchCommandStatus | None = None


async def run_entry_worker_once(
    uow_factory: UnitOfWorkFactory,
    venue: VenuePort,
    facts_source: EntryFactsSource,
    request: EntryWorkerRequest,
) -> EntryWorkerResult:
    existing = await _dispatch_entry(uow_factory, venue, request, ticket_id=None)
    if existing.status is not DispatchCommandStatus.NO_COMMAND:
        return EntryWorkerResult(
            status=(
                EntryWorkerStatus.SUPERSEDED
                if existing.status is DispatchCommandStatus.SUPERSEDED
                else EntryWorkerStatus.DISPATCHED
            ),
            command_id=existing.command_id,
            dispatch_status=existing.status,
        )

    async with uow_factory() as uow:
        lane = await uow.entry_admission.get_global_lane()
        if lane is not None and lane.status != "idle":
            return EntryWorkerResult(status=EntryWorkerStatus.ENTRY_LANE_BUSY)
        selected = await select_entry_candidate(
            uow,
            SelectEntryCandidateRequest(now_ms=request.now_ms),
        )
        if (
            selected.status is SelectEntryCandidateStatus.NO_CANDIDATE
            or selected.candidate is None
        ):
            return EntryWorkerResult(status=EntryWorkerStatus.NO_CANDIDATE)
        signal = selected.candidate.signal
        scope = await uow.signals.get_runtime_scope(signal.runtime_scope_id)
        profile = (
            None
            if scope is None
            else await uow.signals.get_runtime_profile(scope.runtime_profile_id)
        )
        if scope is None or profile is None:
            await uow.signals.save_readiness(
                runtime_scope_id=signal.runtime_scope_id,
                readiness_state="blocked",
                first_blocker="scope_or_policy_mismatch",
                signal_event_id=signal.signal_event_id,
                fact_summary={"reason": "runtime_scope_or_profile_missing"},
                updated_at_ms=request.now_ms,
            )
            return EntryWorkerResult(status=EntryWorkerStatus.ISSUE_REFUSED)

    facts_request = ActionTimeFactsRequest(
        signal_event_id=signal.signal_event_id,
        runtime_scope_id=signal.runtime_scope_id,
        venue_id=profile.venue_id,
        account_id=profile.account_id,
        exchange_instrument_id=signal.exchange_instrument_id,
        position_side=signal.position_side,
        observed_at_ms=request.now_ms,
        valid_for_ms=request.action_fact_validity_ms,
    )
    rules_request = InstrumentRulesRequest(
        venue_id=profile.venue_id,
        account_id=profile.account_id,
        exchange_instrument_id=signal.exchange_instrument_id,
        observed_at_ms=request.now_ms,
        valid_for_ms=request.action_fact_validity_ms,
    )
    try:
        action_facts, instrument_rules = await asyncio.wait_for(
            asyncio.gather(
                facts_source.read_action_time_facts(facts_request),
                facts_source.read_instrument_rules(rules_request),
            ),
            timeout=request.timeout_seconds,
        )
    except Exception as exc:
        async with uow_factory() as uow:
            await uow.signals.save_readiness(
                runtime_scope_id=signal.runtime_scope_id,
                readiness_state="blocked",
                first_blocker="observation_unavailable",
                signal_event_id=signal.signal_event_id,
                fact_summary={"reason": f"action_facts:{type(exc).__name__}"},
                updated_at_ms=request.now_ms,
            )
        return EntryWorkerResult(status=EntryWorkerStatus.FACTS_UNAVAILABLE)

    async with uow_factory() as uow:
        await uow.signals.upsert_instrument_rules(
            exchange_instrument_id=instrument_rules.exchange_instrument_id,
            quantity_step=instrument_rules.quantity_step,
            price_tick=instrument_rules.price_tick,
            min_quantity=instrument_rules.min_quantity,
            min_notional=instrument_rules.min_notional,
            observed_at_ms=instrument_rules.observed_at_ms,
            valid_until_ms=instrument_rules.valid_until_ms,
        )
        issued = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                action_time_facts=action_facts,
                claim_owner=request.worker_id,
                runtime_commit=request.runtime_commit,
                schema_revision=request.schema_revision,
                now_ms=request.now_ms,
            ),
        )
    if issued.status is not IssueTicketStatus.ISSUED or issued.ticket_id is None:
        return EntryWorkerResult(
            status=EntryWorkerStatus.ISSUE_REFUSED,
            issue_status=issued.status,
        )

    dispatched = await _dispatch_entry(
        uow_factory,
        venue,
        request,
        ticket_id=issued.ticket_id,
    )
    return EntryWorkerResult(
        status=(
            EntryWorkerStatus.SUPERSEDED
            if dispatched.status is DispatchCommandStatus.SUPERSEDED
            else EntryWorkerStatus.DISPATCHED
        ),
        ticket_id=issued.ticket_id,
        command_id=dispatched.command_id,
        issue_status=issued.status,
        dispatch_status=dispatched.status,
    )


async def _dispatch_entry(
    uow_factory: UnitOfWorkFactory,
    venue: VenuePort,
    request: EntryWorkerRequest,
    *,
    ticket_id: str | None,
):
    return await dispatch_one_command(
        uow_factory,
        venue,
        DispatchCommandRequest(
            worker_id=request.worker_id,
            ticket_id=ticket_id,
            command_kinds=(ExchangeCommandKind.ENTRY,),
            now_ms=request.now_ms,
            lease_until_ms=request.lease_until_ms,
            timeout_seconds=request.timeout_seconds,
        ),
    )
