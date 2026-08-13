"""Own candidate arbitration, action-time facts, Ticket issuance, and ENTRY."""

from __future__ import annotations

import asyncio
from decimal import Decimal
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
from src.trading_kernel.application.owner_control import strategy_entry_is_enabled
from src.trading_kernel.application.ports import (
    KernelUnitOfWork,
    UnitOfWorkFactory,
    VenuePort,
)
from src.trading_kernel.application.runtime_facts import (
    EntryAdmissionSnapshotRequest,
    EntryFactsSource,
    InstrumentRulesRequest,
    ProductSessionRequest,
)
from src.trading_kernel.application.select_entry_candidate import (
    SelectEntryCandidateRequest,
    SelectEntryCandidateStatus,
    select_entry_candidate,
)
from src.trading_kernel.domain.admission_decision import (
    AdmissionDecisionStatus,
    AdmissionPortfolioUsage,
    freeze_admission_decision,
)
from src.trading_kernel.domain.arbitration import (
    freeze_candidate_set,
    rank_candidates,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.product import (
    ProductEntryStatus,
    evaluate_event_product_entry,
    product_compatibility_for,
)
from src.trading_kernel.domain.strategy_registry import strategy_contract_for


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
    admission_snapshot_validity_ms: int

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
    def _validate_window(self) -> EntryWorkerRequest:
        if self.now_ms <= 0 or self.lease_until_ms <= self.now_ms:
            raise ValueError("ENTRY worker lease must end after its tick")
        if self.timeout_seconds <= 0 or self.admission_snapshot_validity_ms <= 0:
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
    existing = await _dispatch_entry(
        uow_factory,
        venue,
        request,
        ticket_id=None,
        entry_facts_source=facts_source,
    )
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
        owner_controls = getattr(uow, "owner_controls", None)
        strategy_control = (
            None
            if owner_controls is None
            else await owner_controls.get_strategy_control(signal.strategy_group_id)
        )
        if not strategy_entry_is_enabled(strategy_control):
            await uow.signals.save_readiness(
                runtime_scope_id=signal.runtime_scope_id,
                readiness_state="blocked",
                first_blocker=f"strategy_paused:{signal.strategy_group_id}",
                signal_event_id=signal.signal_event_id,
                fact_summary={"reason": "owner_strategy_entry_control"},
                updated_at_ms=request.now_ms,
            )
            return EntryWorkerResult(
                status=EntryWorkerStatus.ISSUE_REFUSED,
                issue_status=IssueTicketStatus.STRATEGY_PAUSED,
            )
        scope = await uow.signals.get_runtime_scope(signal.runtime_scope_id)
        profile = (
            None
            if scope is None
            else await uow.signals.get_runtime_profile(scope.runtime_profile_id)
        )
        product_profile = await uow.signals.get_product_profile(
            signal.exchange_instrument_id
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

    snapshot_request = EntryAdmissionSnapshotRequest(
        venue_id=profile.venue_id,
        account_id=profile.account_id,
        exchange_instrument_id=signal.exchange_instrument_id,
        observed_at_ms=request.now_ms,
        valid_for_ms=request.admission_snapshot_validity_ms,
    )
    rules_request = InstrumentRulesRequest(
        venue_id=profile.venue_id,
        account_id=profile.account_id,
        exchange_instrument_id=signal.exchange_instrument_id,
        observed_at_ms=request.now_ms,
        valid_for_ms=request.admission_snapshot_validity_ms,
    )
    product_session_request = ProductSessionRequest(
        venue_id=profile.venue_id,
        account_id=profile.account_id,
        exchange_instrument_id=signal.exchange_instrument_id,
        observed_at_ms=request.now_ms,
    )
    try:
        product_compatibility = product_compatibility_for(signal.event_spec_id)
        admission_snapshot, instrument_rules, product_session = await asyncio.wait_for(
            asyncio.gather(
                facts_source.read_entry_admission_snapshot(snapshot_request),
                facts_source.read_instrument_rules(rules_request),
                (
                    _read_product_session(
                        facts_source,
                        product_session_request,
                    )
                    if product_compatibility.product_family
                    == "tradfi_equity_perpetual"
                    else _no_product_session()
                ),
            ),
            timeout=request.timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - action facts failure blocks new Entry.
        async with uow_factory() as uow:
            await _record_action_facts_unavailable(
                uow,
                signal_event_id=signal.signal_event_id,
                failure_type=type(exc).__name__,
                now_ms=request.now_ms,
            )
        return EntryWorkerResult(status=EntryWorkerStatus.FACTS_UNAVAILABLE)

    action_time_product_decision = (
        evaluate_event_product_entry(
            compatibility=product_compatibility,
            profile=product_profile,
            snapshot=product_session,
            now_ms=request.now_ms,
        )
        if product_compatibility.product_family == "tradfi_equity_perpetual"
        else None
    )
    async with uow_factory() as uow:
        if (
            product_session is not None
            and action_time_product_decision is not None
            and action_time_product_decision.status
            is not ProductEntryStatus.IDENTITY_MISMATCH
        ):
            await uow.signals.upsert_product_sessions((product_session,))
        await uow.signals.upsert_instrument_rules(
            venue_id=profile.venue_id,
            exchange_instrument_id=instrument_rules.exchange_instrument_id,
            quantity_step=instrument_rules.quantity_step,
            price_tick=instrument_rules.price_tick,
            min_quantity=instrument_rules.min_quantity,
            min_notional=instrument_rules.min_notional,
            exchange_max_leverage=instrument_rules.exchange_max_leverage,
            maintenance_margin_brackets=instrument_rules.maintenance_margin_brackets,
            maintenance_margin_brackets_digest=(
                instrument_rules.maintenance_margin_brackets_digest
            ),
            notional_coefficient=instrument_rules.notional_coefficient,
            notional_coefficient_certified=(
                instrument_rules.notional_coefficient_certified
            ),
            observed_at_ms=instrument_rules.observed_at_ms,
            valid_until_ms=instrument_rules.valid_until_ms,
        )
        issued = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=admission_snapshot,
                claim_owner=request.worker_id,
                runtime_commit=request.runtime_commit,
                schema_revision=request.schema_revision,
                now_ms=request.now_ms,
                action_time_product_decision=action_time_product_decision,
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
        entry_facts_source=facts_source,
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


async def _no_product_session():
    return None


async def _read_product_session(facts_source, request):
    reader = getattr(facts_source, "read_product_session", None)
    if not callable(reader):
        raise TypeError("TradFi action-time Product source is unavailable")
    return await reader(request)


async def _record_action_facts_unavailable(
    uow: KernelUnitOfWork,
    *,
    signal_event_id: str,
    failure_type: str,
    now_ms: int,
) -> None:
    candidates = rank_candidates(
        await uow.signals.list_ready_candidates(now_ms=now_ms, limit=64)
    )
    if not candidates or candidates[0].signal.signal_event_id != signal_event_id:
        return
    signal = candidates[0].signal
    scope = await uow.signals.get_runtime_scope(signal.runtime_scope_id)
    profile = (
        None
        if scope is None
        else await uow.signals.get_runtime_profile(scope.runtime_profile_id)
    )
    policy = (
        None
        if scope is None
        else await uow.entry_admission.get_owner_policy(scope.owner_policy_id)
    )
    if scope is None or profile is None or policy is None:
        await uow.signals.save_readiness(
            runtime_scope_id=signal.runtime_scope_id,
            readiness_state="blocked",
            first_blocker="observation_unavailable",
            signal_event_id=signal.signal_event_id,
            fact_summary={"reason": f"action_facts:{failure_type}"},
            updated_at_ms=now_ms,
        )
        return
    exposure = await uow.entry_admission.get_account_exposure(
        profile.venue_id,
        profile.account_id,
    )
    contract = strategy_contract_for(signal.event_spec_id)
    active_family_ticket_count = (
        await uow.entry_admission.count_active_family_tickets(
            venue_id=profile.venue_id,
            account_id=profile.account_id,
            exposure_family=contract.exposure_family,
        )
    )
    directional_risk_at_stop = (
        await uow.entry_admission.sum_active_directional_stop_risk(
            venue_id=profile.venue_id,
            account_id=profile.account_id,
            position_side=signal.position_side,
        )
    )
    active_ticket_count = 0 if exposure is None else exposure.active_ticket_count
    gross_risk = Decimal(0) if exposure is None else exposure.gross_risk_at_stop
    reserved_margin = (
        Decimal(0) if exposure is None else exposure.current_reserved_margin
    )
    await uow.admission_decisions.add(
        freeze_admission_decision(
            signal=signal,
            candidate_set=freeze_candidate_set(candidates),
            exposure_family=contract.exposure_family,
            runtime_profile_id=profile.runtime_profile_id,
            owner_policy_id=policy.owner_policy_id,
            owner_policy_version=policy.policy_version,
            venue_id=profile.venue_id,
            account_id=profile.account_id,
            portfolio_usage=AdmissionPortfolioUsage(
                active_ticket_count=active_ticket_count,
                active_family_ticket_count=active_family_ticket_count,
                gross_risk_at_stop=gross_risk,
                directional_risk_at_stop=directional_risk_at_stop,
                current_reserved_margin=reserved_margin,
                remaining_ticket_slots=max(
                    0,
                    policy.max_concurrent_tickets - active_ticket_count,
                ),
                remaining_family_slots=max(
                    0,
                    policy.family_ticket_limits.for_family(contract.exposure_family)
                    - active_family_ticket_count,
                ),
                remaining_gross_stop_risk=None,
                remaining_directional_stop_risk=None,
                remaining_initial_margin=None,
            ),
            decision_status=AdmissionDecisionStatus.REJECTED,
            first_blocker="observation_unavailable",
            binding_constraint="action_facts_unavailable",
            capacity_claim_id=None,
            ticket_id=None,
            entry_admission_snapshot_digest=None,
            decided_at_ms=now_ms,
        )
    )
    await uow.signals.save_readiness(
        runtime_scope_id=signal.runtime_scope_id,
        readiness_state="blocked",
        first_blocker="observation_unavailable",
        signal_event_id=signal.signal_event_id,
        fact_summary={"reason": f"action_facts:{failure_type}"},
        updated_at_ms=now_ms,
    )


async def _dispatch_entry(
    uow_factory: UnitOfWorkFactory,
    venue: VenuePort,
    request: EntryWorkerRequest,
    *,
    ticket_id: str | None,
    entry_facts_source: EntryFactsSource | None = None,
):
    return await dispatch_one_command(
        uow_factory,
        venue,
        DispatchCommandRequest(
            worker_id=request.worker_id,
            ticket_id=ticket_id,
            command_kinds=(
                ExchangeCommandKind.SET_LEVERAGE,
                ExchangeCommandKind.ENTRY,
            ),
            now_ms=request.now_ms,
            lease_until_ms=request.lease_until_ms,
            timeout_seconds=request.timeout_seconds,
            runtime_commit=request.runtime_commit,
            schema_revision=request.schema_revision,
            admission_snapshot_validity_ms=request.admission_snapshot_validity_ms,
        ),
        entry_facts_source=entry_facts_source,
    )
