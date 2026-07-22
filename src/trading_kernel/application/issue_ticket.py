"""Issue one immutable Ticket through the globally serialized ENTRY lane."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import (
    BudgetReservationRecord,
    KernelUnitOfWork,
)
from src.trading_kernel.domain.events import TicketIssued
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.capacity import CapacityClaim


class IssueTicketStatus(StrEnum):
    ISSUED = "issued"
    NO_READY_SIGNAL = "no_ready_signal"
    SIGNAL_INVALID_OR_STALE = "signal_invalid_or_stale"
    SCOPE_OR_POLICY_MISMATCH = "scope_or_policy_mismatch"
    ACCOUNT_MODE_INVALID = "account_mode_invalid"
    INSTRUMENT_RULES_INVALID = "instrument_rules_invalid"
    SCHEMA_IDENTITY_MISMATCH = "schema_identity_mismatch"
    ENTRY_LANE_OCCUPIED = "entry_lane_occupied"
    FACTS_EXPIRED = "facts_expired"
    ACTIVE_NETTING_DOMAIN = "active_netting_domain"
    DUPLICATE_SIGNAL = "duplicate_signal"
    POLICY_MISSING_OR_STALE = "policy_missing_or_stale"
    POLICY_DISABLED = "policy_disabled"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PROTECTION_UNAVAILABLE = "protection_unavailable"
    CAPACITY_CLAIM_MISSING = "capacity_claim_missing"


class IssueTicketRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capacity_claim: CapacityClaim
    now_ms: int
    claim_owner: str

    @field_validator("now_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("issue time must be positive")
        return value

    @field_validator("claim_owner", mode="before")
    @classmethod
    def _require_claim_owner(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("claim owner must be non-blank")
        return normalized


class IssueTicketResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: IssueTicketStatus
    ticket_id: str | None


async def issue_ticket(
    uow: KernelUnitOfWork,
    request: IssueTicketRequest,
) -> IssueTicketResult:
    claim = request.capacity_claim
    ticket = claim.to_ticket()
    lane = await uow.entry_admission.lock_global_lane()
    if lane.status != "idle":
        return IssueTicketResult(
            status=IssueTicketStatus.ENTRY_LANE_OCCUPIED,
            ticket_id=None,
        )

    if request.now_ms >= claim.expires_at_ms:
        return IssueTicketResult(
            status=IssueTicketStatus.FACTS_EXPIRED,
            ticket_id=None,
        )

    policy = await uow.entry_admission.get_owner_policy(ticket.owner_policy_id)
    if policy is None or policy.policy_version != ticket.owner_policy_version:
        return IssueTicketResult(
            status=IssueTicketStatus.POLICY_MISSING_OR_STALE,
            ticket_id=None,
        )
    if not policy.enabled or not policy.real_submit_enabled:
        return IssueTicketResult(
            status=IssueTicketStatus.POLICY_DISABLED,
            ticket_id=None,
        )

    if await uow.entry_admission.has_active_ticket_in_domain(
        ticket.identity.netting_domain.key()
    ):
        return IssueTicketResult(
            status=IssueTicketStatus.ACTIVE_NETTING_DOMAIN,
            ticket_id=None,
        )
    if await uow.entry_admission.has_ticket_for_signal(
        ticket.identity.signal_event_id
    ):
        return IssueTicketResult(
            status=IssueTicketStatus.DUPLICATE_SIGNAL,
            ticket_id=None,
        )

    exposure = await uow.entry_admission.get_account_exposure(
        ticket.identity.netting_domain.account_id,
        for_update=True,
    )
    current_notional = exposure.gross_notional if exposure is not None else 0
    current_risk = exposure.gross_risk_at_stop if exposure is not None else 0
    current_tickets = exposure.active_ticket_count if exposure is not None else 0
    if (
        current_tickets >= policy.max_concurrent_tickets
        or current_notional + ticket.notional > policy.max_gross_notional
        or current_risk + ticket.risk_at_stop > policy.max_gross_risk_at_stop
        or ticket.risk_at_stop > policy.max_ticket_risk_at_stop
        or ticket.leverage != policy.target_leverage
    ):
        return IssueTicketResult(
            status=IssueTicketStatus.BUDGET_EXHAUSTED,
            ticket_id=None,
        )

    await uow.capacity_claims.add(claim)
    await uow.budgets.add(
        BudgetReservationRecord(
            budget_reservation_id=f"budget:{ticket.identity.ticket_id}",
            ticket_id=ticket.identity.ticket_id,
            owner_policy_id=ticket.owner_policy_id,
            account_id=ticket.identity.netting_domain.account_id,
            reserved_notional=ticket.notional,
            reserved_risk=ticket.risk_at_stop,
            status="active",
            created_at_ms=request.now_ms,
        )
    )
    await uow.entry_admission.reserve_account_exposure(
        account_id=ticket.identity.netting_domain.account_id,
        notional=ticket.notional,
        risk_at_stop=ticket.risk_at_stop,
        expected_version=(
            None if exposure is None else exposure.projection_version
        ),
        updated_at_ms=request.now_ms,
    )
    await uow.entry_admission.claim_global_lane(
        ticket_id=ticket.identity.ticket_id,
        signal_event_id=ticket.identity.signal_event_id,
        claim_owner=request.claim_owner,
        claimed_at_ms=request.now_ms,
        lease_until_ms=ticket.expires_at_ms,
        expected_version=lane.version,
    )

    event = TicketIssued(
        event_id=f"event:{ticket.identity.ticket_id}:1",
        ticket=ticket,
        sequence=1,
        occurred_at_ms=request.now_ms,
    )
    await uow.commit_reduction(
        event=event,
        reduction=reduce_event(None, event),
        expected_version=0,
    )
    return IssueTicketResult(
        status=IssueTicketStatus.ISSUED,
        ticket_id=ticket.identity.ticket_id,
    )
