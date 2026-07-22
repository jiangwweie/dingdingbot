"""Issue the currently selected Signal through one action-time CapacityClaim."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.build_capacity_claim import build_capacity_claim
from src.trading_kernel.application.ingest_signal import (
    SignalAuthorityStatus,
    validate_signal_authority,
)
from src.trading_kernel.application.issue_ticket import (
    IssueTicketRequest,
    IssueTicketResult,
    IssueTicketStatus,
    issue_ticket,
)
from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.arbitration import rank_candidates
from src.trading_kernel.domain.capacity import (
    ActionTimeFacts,
    CapacityClaimStatus,
    CapacityInstrumentRules,
    CapacityPolicy,
    CapacityUsage,
)
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.ticket import EntryOrderType


class IssueReadySignalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_event_id: str
    action_time_facts: ActionTimeFacts
    claim_owner: str
    runtime_commit: str
    schema_revision: str
    now_ms: int

    @field_validator(
        "signal_event_id",
        "claim_owner",
        "runtime_commit",
        "schema_revision",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("issue-ready identities must be non-blank")
        return normalized

    @field_validator("now_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("issue-ready time must be positive")
        return value


async def issue_ready_signal(
    uow: KernelUnitOfWork,
    request: IssueReadySignalRequest,
) -> IssueTicketResult:
    candidates = rank_candidates(
        await uow.signals.list_ready_candidates(
            now_ms=request.now_ms,
            limit=64,
        )
    )
    if not candidates or candidates[0].signal.signal_event_id != request.signal_event_id:
        requested_signal = await uow.signals.get(request.signal_event_id)
        if requested_signal is None:
            return IssueTicketResult(
                status=IssueTicketStatus.NO_READY_SIGNAL,
                ticket_id=None,
            )
        requested_authority = await validate_signal_authority(
            uow,
            requested_signal,
            runtime_commit=request.runtime_commit,
            schema_revision=request.schema_revision,
            now_ms=request.now_ms,
        )
        if requested_authority is not SignalAuthorityStatus.VALID:
            await _block_signal(
                uow,
                requested_signal,
                requested_authority.value,
                request.now_ms,
            )
            return IssueTicketResult(
                status=IssueTicketStatus(requested_authority.value),
                ticket_id=None,
            )
        return IssueTicketResult(
            status=IssueTicketStatus.NO_READY_SIGNAL,
            ticket_id=None,
        )
    signal = candidates[0].signal
    authority = await validate_signal_authority(
        uow,
        signal,
        runtime_commit=request.runtime_commit,
        schema_revision=request.schema_revision,
        now_ms=request.now_ms,
    )
    if authority is not SignalAuthorityStatus.VALID:
        await _block_signal(uow, signal, authority.value, request.now_ms)
        return IssueTicketResult(
            status=IssueTicketStatus(authority.value),
            ticket_id=None,
        )

    scope = await uow.signals.get_runtime_scope(signal.runtime_scope_id)
    if scope is None or not scope.enabled:
        return await _refuse(
            uow,
            signal,
            IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH,
            request.now_ms,
        )
    profile = await uow.signals.get_runtime_profile(scope.runtime_profile_id)
    policy = await uow.entry_admission.get_owner_policy(scope.owner_policy_id)
    rules = await uow.signals.get_instrument_rules(signal.exchange_instrument_id)
    event_spec = await uow.signals.get_event_spec(signal.event_spec_id)
    if (
        profile is None
        or profile.status != "active"
        or profile.venue_id != request.action_time_facts.venue_id
        or profile.account_id != request.action_time_facts.account_id
        or policy is None
        or not policy.enabled
        or not policy.real_submit_enabled
        or event_spec is None
        or event_spec.status != "active"
    ):
        return await _refuse(
            uow,
            signal,
            IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH,
            request.now_ms,
        )
    if rules is None:
        return await _refuse(
            uow,
            signal,
            IssueTicketStatus.INSTRUMENT_RULES_INVALID,
            request.now_ms,
        )

    exposure = await uow.entry_admission.get_account_exposure(profile.account_id)
    usage = CapacityUsage(
        gross_notional=(
            exposure.gross_notional if exposure else Decimal("0")
        ),
        gross_risk_at_stop=(
            exposure.gross_risk_at_stop if exposure else Decimal("0")
        ),
        active_ticket_count=(exposure.active_ticket_count if exposure else 0),
    )
    domain = NettingDomain(
        venue_id=profile.venue_id,
        account_id=profile.account_id,
        exchange_instrument_id=signal.exchange_instrument_id,
        position_side=signal.position_side,
    )
    decision = build_capacity_claim(
        signal=signal,
        runtime_profile_id=profile.runtime_profile_id,
        venue_id=profile.venue_id,
        account_id=profile.account_id,
        position_mode=profile.position_mode,
        policy=CapacityPolicy(
            owner_policy_id=policy.owner_policy_id,
            policy_version=policy.policy_version,
            max_concurrent_tickets=policy.max_concurrent_tickets,
            max_gross_notional=policy.max_gross_notional,
            max_gross_risk_at_stop=policy.max_gross_risk_at_stop,
            max_ticket_risk_at_stop=policy.max_ticket_risk_at_stop,
            target_leverage=policy.target_leverage,
        ),
        usage=usage,
        instrument_rules=CapacityInstrumentRules(
            quantity_step=rules.quantity_step,
            price_tick=rules.price_tick,
            min_quantity=rules.min_quantity,
            min_notional=rules.min_notional,
            projection_version=rules.projection_version,
            observed_at_ms=rules.observed_at_ms,
            valid_until_ms=rules.valid_until_ms,
        ),
        action_facts=request.action_time_facts,
        entry_order_type=EntryOrderType(event_spec.entry_order_type),
        netting_domain_occupied=(
            await uow.entry_admission.has_active_ticket_in_domain(domain.key())
        ),
        now_ms=request.now_ms,
    )
    if decision.status is not CapacityClaimStatus.CLAIMED or decision.claim is None:
        issue_status = _issue_status(decision.status)
        return await _refuse(
            uow,
            signal,
            issue_status,
            request.now_ms,
        )

    result = await issue_ticket(
        uow,
        IssueTicketRequest(
            capacity_claim=decision.claim,
            now_ms=request.now_ms,
            claim_owner=request.claim_owner,
        ),
    )
    if result.status is IssueTicketStatus.ISSUED:
        await uow.signals.save_readiness(
            runtime_scope_id=signal.runtime_scope_id,
            readiness_state="processing",
            first_blocker=None,
            signal_event_id=signal.signal_event_id,
            fact_summary={
                "capacity_claim_id": decision.claim.capacity_claim_id,
                "fact_digest": signal.fact_digest,
            },
            updated_at_ms=request.now_ms,
        )
    return result


async def _refuse(
    uow: KernelUnitOfWork,
    signal,
    status: IssueTicketStatus,
    now_ms: int,
) -> IssueTicketResult:
    blocker = (
        "signal_invalid_or_stale"
        if status in {
            IssueTicketStatus.SIGNAL_INVALID_OR_STALE,
            IssueTicketStatus.FACTS_EXPIRED,
        }
        else status.value
    )
    await _block_signal(uow, signal, blocker, now_ms)
    return IssueTicketResult(status=status, ticket_id=None)


async def _block_signal(uow, signal, blocker: str, now_ms: int) -> None:
    await uow.signals.save_readiness(
        runtime_scope_id=signal.runtime_scope_id,
        readiness_state="blocked",
        first_blocker=blocker,
        signal_event_id=signal.signal_event_id,
        fact_summary={
            "fact_count": len(signal.facts),
            "fact_digest": signal.fact_digest,
        },
        updated_at_ms=now_ms,
    )


def _issue_status(status: CapacityClaimStatus) -> IssueTicketStatus:
    mapping = {
        CapacityClaimStatus.SIGNAL_INVALID_OR_STALE: (
            IssueTicketStatus.SIGNAL_INVALID_OR_STALE
        ),
        CapacityClaimStatus.SCOPE_OR_POLICY_MISMATCH: (
            IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH
        ),
        CapacityClaimStatus.ACTION_FACTS_INVALID_OR_STALE: (
            IssueTicketStatus.SIGNAL_INVALID_OR_STALE
        ),
        CapacityClaimStatus.ACCOUNT_MODE_INVALID: (
            IssueTicketStatus.ACCOUNT_MODE_INVALID
        ),
        CapacityClaimStatus.INSTRUMENT_RULES_INVALID: (
            IssueTicketStatus.INSTRUMENT_RULES_INVALID
        ),
        CapacityClaimStatus.NETTING_DOMAIN_OCCUPIED: (
            IssueTicketStatus.ACTIVE_NETTING_DOMAIN
        ),
        CapacityClaimStatus.BUDGET_EXHAUSTED: IssueTicketStatus.BUDGET_EXHAUSTED,
        CapacityClaimStatus.PROTECTION_UNAVAILABLE: (
            IssueTicketStatus.PROTECTION_UNAVAILABLE
        ),
    }
    return mapping[status]
