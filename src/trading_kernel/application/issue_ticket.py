"""Issue one immutable Ticket through the globally serialized ENTRY lane."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import (
    BudgetReservationRecord,
    KernelUnitOfWork,
    RuntimeScopeSnapshot,
)
from src.trading_kernel.domain.events import TicketIssued
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.capacity import CapacityClaim
from src.trading_kernel.domain.ticket import TradeTicket


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
    ADMISSION_INCIDENT_OPEN = "admission_incident_open"


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

    exposure = await uow.entry_admission.get_account_exposure(
        ticket.identity.netting_domain.venue_id,
        ticket.identity.netting_domain.account_id,
        for_update=True,
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
    if not policy.enabled or not policy.new_entry_submit_enabled:
        return IssueTicketResult(
            status=IssueTicketStatus.POLICY_DISABLED,
            ticket_id=None,
        )

    scope = await uow.signals.get_runtime_scope(
        ticket.runtime_scope_id,
        for_update=True,
    )
    if not _scope_matches_ticket(scope, ticket):
        return IssueTicketResult(
            status=IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH,
            ticket_id=None,
        )

    ownership = await uow.entry_admission.read_admission_ownership(
        venue_id=ticket.identity.netting_domain.venue_id,
        account_id=ticket.identity.netting_domain.account_id,
        exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
        # The global ENTRY lane and exact account exposure row already own
        # admission serialization.  Ownership is a bounded current-state
        # verification; locking its active Ticket/Aggregate/Command rows here
        # would invert Lifecycle's Aggregate -> Account Capacity lock order.
        for_update=False,
    )
    if ownership.open_incident_scopes:
        return IssueTicketResult(
            status=IssueTicketStatus.ADMISSION_INCIDENT_OPEN,
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

    current_tickets = exposure.active_ticket_count if exposure is not None else 0
    if (
        current_tickets >= policy.max_concurrent_tickets
        or ticket.selected_leverage > policy.max_leverage
        or ticket.margin_mode != policy.supported_margin_mode
        or ticket.risk_at_stop > ticket.planned_stop_risk_budget
        or ticket.post_fill_stop_risk_limit < ticket.planned_stop_risk_budget
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
            venue_id=ticket.identity.netting_domain.venue_id,
            account_id=ticket.identity.netting_domain.account_id,
            reserved_notional=ticket.notional,
            reserved_risk=ticket.risk_at_stop,
            reserved_margin=ticket.reserved_margin,
            planned_stop_risk_budget=ticket.planned_stop_risk_budget,
            risk_reservation_basis=ticket.risk_reservation_basis,
            status="active",
            created_at_ms=request.now_ms,
        )
    )
    await uow.entry_admission.reserve_account_exposure(
        venue_id=ticket.identity.netting_domain.venue_id,
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


def _scope_matches_ticket(
    scope: RuntimeScopeSnapshot | None,
    ticket: TradeTicket,
) -> bool:
    """Require the locked current Scope to match the frozen Claim/Ticket authority."""

    if scope is None or not scope.enabled:
        return False
    identity = ticket.identity
    return (
        scope.runtime_scope_id == ticket.runtime_scope_id
        and scope.scope_version == ticket.runtime_scope_version
        and scope.strategy_group_id == identity.runtime.strategy_group_id
        and scope.strategy_version_id == identity.runtime.strategy_version_id
        and scope.event_spec_id == identity.runtime.event_spec_id
        and scope.runtime_profile_id == identity.runtime.runtime_profile_id
        and scope.owner_policy_id == ticket.owner_policy_id
        and scope.exchange_instrument_id
        == identity.netting_domain.exchange_instrument_id
        and scope.position_side == identity.netting_domain.position_side
    )
