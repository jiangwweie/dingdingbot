"""Issue the next persisted ready signal through the global ENTRY lane."""

from __future__ import annotations

from hashlib import sha256

from pydantic import BaseModel, ConfigDict

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
from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)
from src.trading_kernel.domain.ticket import TradeTicket, build_ticket_id


class IssueReadySignalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_owner: str
    runtime_commit: str
    schema_revision: str
    now_ms: int


async def issue_ready_signal(
    uow: KernelUnitOfWork,
    request: IssueReadySignalRequest,
) -> IssueTicketResult:
    signal = await uow.signals.get_next_ready(now_ms=request.now_ms)
    if signal is None:
        signal = await uow.signals.get_next_stale_ready(now_ms=request.now_ms)
        if signal is None:
            return IssueTicketResult(
                status=IssueTicketStatus.NO_READY_SIGNAL,
                ticket_id=None,
            )
    authority = await validate_signal_authority(
        uow,
        signal,
        runtime_commit=request.runtime_commit,
        schema_revision=request.schema_revision,
        now_ms=request.now_ms,
    )
    if authority is not SignalAuthorityStatus.VALID:
        await uow.signals.save_readiness(
            runtime_scope_id=signal.runtime_scope_id,
            readiness_state="blocked",
            first_blocker=authority.value,
            signal_event_id=signal.signal_event_id,
            fact_summary={"fact_digest": signal.fact_digest},
            updated_at_ms=request.now_ms,
        )
        return IssueTicketResult(
            status=IssueTicketStatus(authority.value),
            ticket_id=None,
        )

    scope = await uow.signals.get_runtime_scope(signal.runtime_scope_id)
    if scope is None:
        raise RuntimeError("validated signal lost its runtime scope")
    profile = await uow.signals.get_runtime_profile(scope.runtime_profile_id)
    if profile is None:
        raise RuntimeError("validated signal lost its runtime profile")
    policy = await uow.entry_admission.get_owner_policy(scope.owner_policy_id)
    if policy is None:
        raise RuntimeError("validated signal lost its Owner policy")

    runtime = RuntimeIdentity(
        runtime_profile_id=scope.runtime_profile_id,
        strategy_group_id=signal.strategy_group_id,
        strategy_version_id=signal.strategy_version_id,
        event_spec_id=signal.event_spec_id,
    )
    domain = NettingDomain(
        venue_id=profile.venue_id,
        account_id=profile.account_id,
        exchange_instrument_id=signal.exchange_instrument_id,
        position_side=signal.position_side,
    )
    ticket_id = build_ticket_id(
        signal_event_id=signal.signal_event_id,
        runtime=runtime,
        netting_domain=domain,
    )
    ticket = TradeTicket(
        identity=TicketIdentity(
            ticket_id=ticket_id,
            exposure_episode_id=_build_exposure_episode_id(signal.signal_event_id),
            signal_event_id=signal.signal_event_id,
            runtime=runtime,
            netting_domain=domain,
        ),
        owner_policy_id=scope.owner_policy_id,
        owner_policy_version=policy.policy_version,
        runtime_scope_id=scope.runtime_scope_id,
        runtime_scope_version=scope.scope_version,
        fact_digest=signal.fact_digest,
        created_at_ms=request.now_ms,
        expires_at_ms=signal.expires_at_ms,
        quantity=signal.terms.quantity,
        notional=signal.terms.notional,
        leverage=signal.terms.leverage,
        risk_at_stop=signal.terms.risk_at_stop,
        entry_order_type=signal.terms.entry_order_type,
        entry_limit_price=signal.terms.entry_limit_price,
        initial_stop_price=signal.terms.initial_stop_price,
        take_profit_prices=signal.terms.take_profit_prices,
    )
    result = await issue_ticket(
        uow,
        IssueTicketRequest(
            ticket=ticket,
            now_ms=request.now_ms,
            claim_owner=request.claim_owner,
        ),
    )
    if result.status is IssueTicketStatus.ISSUED:
        await uow.signals.save_readiness(
            runtime_scope_id=signal.runtime_scope_id,
            readiness_state="ticket_issued",
            first_blocker=None,
            signal_event_id=signal.signal_event_id,
            fact_summary={"fact_digest": signal.fact_digest},
            updated_at_ms=request.now_ms,
        )
    elif result.status is not IssueTicketStatus.ENTRY_LANE_OCCUPIED:
        await uow.signals.save_readiness(
            runtime_scope_id=signal.runtime_scope_id,
            readiness_state="blocked",
            first_blocker=result.status.value,
            signal_event_id=signal.signal_event_id,
            fact_summary={"fact_digest": signal.fact_digest},
            updated_at_ms=request.now_ms,
        )
    return result


def _build_exposure_episode_id(signal_event_id: str) -> str:
    digest = sha256(signal_event_id.encode("utf-8")).hexdigest()[:32]
    return f"episode:{digest}"
