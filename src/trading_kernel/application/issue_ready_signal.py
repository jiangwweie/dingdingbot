"""Issue the selected Signal from one immutable admission snapshot."""

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
from src.trading_kernel.application.owner_control import strategy_entry_is_enabled
from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.application.project_shadow_outcome import (
    pending_shadow_spec_for_rejection,
)
from src.trading_kernel.domain.account_entry_health import (
    classify_account_entry_health,
)
from src.trading_kernel.domain.admission_decision import (
    AdmissionDecisionStatus,
    AdmissionPortfolioUsage,
    CandidateSetSnapshot,
    freeze_admission_decision,
)
from src.trading_kernel.domain.arbitration import (
    freeze_candidate_set,
    rank_candidates,
)
from src.trading_kernel.domain.capacity import (
    CapacityClaimStatus,
    CapacityInstrumentRules,
    CapacityPolicy,
    CapacityUsage,
)
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.exposure_family import ExposureFamily
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.instrument_entry_health import (
    classify_instrument_entry_health,
)
from src.trading_kernel.domain.product import (
    ProductEntryDecision,
    evaluate_event_product_entry,
    product_compatibility_for,
)
from src.trading_kernel.domain.strategy_registry import strategy_contract_for
from src.trading_kernel.domain.ticket import EntryOrderType


class IssueReadySignalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_event_id: str
    admission_snapshot: EntryAdmissionSnapshot
    claim_owner: str
    runtime_commit: str
    schema_revision: str
    now_ms: int
    action_time_product_decision: ProductEntryDecision | None = None

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


class _AdmissionDecisionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_set: CandidateSetSnapshot
    exposure_family: ExposureFamily
    runtime_profile_id: str
    owner_policy_id: str
    owner_policy_version: int
    venue_id: str
    account_id: str
    portfolio_usage: AdmissionPortfolioUsage


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
    candidate_set = None if not candidates else freeze_candidate_set(candidates)
    if (
        not candidates
        or candidates[0].signal.signal_event_id != request.signal_event_id
    ):
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
    delayed_selection_refusal = (
        authority
        if authority
        in {
            SignalAuthorityStatus.SELECTION_ENTRY_VACUUM,
            SignalAuthorityStatus.SELECTION_AUTHORITY_INVALID,
            SignalAuthorityStatus.SELECTION_TRIGGER_SUPPRESSED,
        }
        else None
    )
    if (
        authority is not SignalAuthorityStatus.VALID
        and delayed_selection_refusal is None
    ):
        await _block_signal(uow, signal, authority.value, request.now_ms)
        return IssueTicketResult(
            status=IssueTicketStatus(authority.value),
            ticket_id=None,
        )

    selection_control = await uow.instrument_selection.get_selection_control(
        signal.strategy_group_id
    )
    vacuum = (
        None
        if selection_control is None
        else await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=signal.strategy_group_id,
            selection_spec_id=selection_control.selection_spec_id,
        )
    )

    scope = await uow.signals.get_runtime_scope(signal.runtime_scope_id)
    if scope is None or scope.lifecycle_state != "active" or not scope.entry_enabled:
        return await _refuse(
            uow,
            signal,
            IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH,
            request.now_ms,
        )
    profile = await uow.signals.get_runtime_profile(scope.runtime_profile_id)
    policy = await uow.entry_admission.get_owner_policy(scope.owner_policy_id)
    product_profile = await uow.signals.get_product_profile(
        signal.exchange_instrument_id
    )
    product_session = await uow.signals.get_product_session(
        signal.exchange_instrument_id
    )
    owner_controls = getattr(uow, "owner_controls", None)
    strategy_control = (
        None
        if owner_controls is None
        else await owner_controls.get_strategy_control(signal.strategy_group_id)
    )
    rules = (
        None
        if profile is None
        else await uow.signals.get_instrument_rules(
            profile.venue_id,
            signal.exchange_instrument_id,
        )
    )
    event_spec = await uow.signals.get_event_spec(signal.event_spec_id)
    if (
        profile is None
        or profile.status != "active"
        or profile.venue_id != request.admission_snapshot.account_risk_snapshot.venue_id
        or profile.account_id
        != request.admission_snapshot.account_risk_snapshot.account_id
        or policy is None
        or not policy.enabled
        or not policy.new_entry_submit_enabled
        or policy.scope is None
        or not policy.scope.authorizes(
            event_spec_id=signal.event_spec_id,
            runtime_profile_id=scope.runtime_profile_id,
        )
        or not strategy_entry_is_enabled(strategy_control)
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
    current_exit_binding = await uow.exit_profiles.get_current_binding(
        signal.event_spec_id,
        for_update=True,
    )
    exit_binding = (
        None
        if current_exit_binding is None
        else await uow.exit_profiles.get_binding(current_exit_binding.exit_binding_id)
    )
    exit_profile = (
        None
        if exit_binding is None
        else await uow.exit_profiles.get_profile(
            exit_profile_id=exit_binding.exit_profile_id,
            semantic_hash=exit_binding.exit_profile_semantic_hash,
        )
    )
    ownership = await uow.entry_admission.read_admission_ownership(
        venue_id=profile.venue_id,
        account_id=profile.account_id,
        exchange_instrument_id=signal.exchange_instrument_id,
    )
    account_entry_health = classify_account_entry_health(
        request.admission_snapshot,
        ownership,
    )
    instrument_entry_health = classify_instrument_entry_health(
        request.admission_snapshot,
        ownership,
        exchange_instrument_id=signal.exchange_instrument_id,
        requested_position_side=signal.position_side,
    )
    exposure = await uow.entry_admission.get_account_exposure(
        profile.venue_id,
        profile.account_id,
    )
    contract = strategy_contract_for(signal.event_spec_id)
    active_family_ticket_count = await uow.entry_admission.count_active_family_tickets(
        venue_id=profile.venue_id,
        account_id=profile.account_id,
        exposure_family=contract.exposure_family,
    )
    directional_risk_at_stop = (
        await uow.entry_admission.sum_active_directional_stop_risk(
            venue_id=profile.venue_id,
            account_id=profile.account_id,
            position_side=signal.position_side,
        )
    )
    usage = CapacityUsage(
        gross_notional=(exposure.gross_notional if exposure else Decimal(0)),
        gross_risk_at_stop=(exposure.gross_risk_at_stop if exposure else Decimal(0)),
        current_reserved_margin=(
            exposure.current_reserved_margin if exposure else Decimal(0)
        ),
        active_ticket_count=(exposure.active_ticket_count if exposure else 0),
        active_family_ticket_count=active_family_ticket_count,
        directional_risk_at_stop=directional_risk_at_stop,
    )
    admission_context = _AdmissionDecisionContext(
        candidate_set=(
            candidate_set
            if candidate_set is not None
            else freeze_candidate_set(candidates)
        ),
        exposure_family=contract.exposure_family,
        runtime_profile_id=profile.runtime_profile_id,
        owner_policy_id=policy.owner_policy_id,
        owner_policy_version=policy.policy_version,
        venue_id=profile.venue_id,
        account_id=profile.account_id,
        portfolio_usage=_portfolio_usage(
            policy=policy,
            usage=usage,
            admission_snapshot=request.admission_snapshot,
            exposure_family=contract.exposure_family,
        ),
    )
    if current_exit_binding is None or exit_binding is None or exit_profile is None:
        return await _refuse(
            uow,
            signal,
            IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH,
            request.now_ms,
            admission_context=admission_context,
            entry_admission_snapshot_digest=request.admission_snapshot.digest(),
            binding_constraint="exit_profile_authority_missing",
            admission_snapshot=request.admission_snapshot,
        )
    if delayed_selection_refusal is not None:
        status = IssueTicketStatus(delayed_selection_refusal.value)
        return await _refuse(
            uow,
            signal,
            status,
            request.now_ms,
            admission_context=admission_context,
            entry_admission_snapshot_digest=request.admission_snapshot.digest(),
            binding_constraint=(
                vacuum.entry_vacuum_id
                if delayed_selection_refusal
                is SignalAuthorityStatus.SELECTION_ENTRY_VACUUM
                and vacuum is not None
                and vacuum.blocks_new_entry
                else delayed_selection_refusal.value
            ),
            admission_snapshot=request.admission_snapshot,
        )
    if vacuum is not None and vacuum.blocks_new_entry:
        return await _refuse(
            uow,
            signal,
            IssueTicketStatus.SELECTION_ENTRY_VACUUM,
            request.now_ms,
            admission_context=admission_context,
            entry_admission_snapshot_digest=request.admission_snapshot.digest(),
            binding_constraint=vacuum.entry_vacuum_id,
            admission_snapshot=request.admission_snapshot,
        )
    current_product_decision = evaluate_event_product_entry(
        compatibility=product_compatibility_for(signal.event_spec_id),
        profile=product_profile,
        snapshot=product_session,
        now_ms=request.now_ms,
    )
    product_decision = (
        request.action_time_product_decision
        if request.action_time_product_decision is not None
        and not request.action_time_product_decision.allowed
        else current_product_decision
    )
    if not product_decision.allowed:
        return await _refuse(
            uow,
            signal,
            IssueTicketStatus.PRODUCT_ENTRY_BLOCKED,
            request.now_ms,
            admission_context=admission_context,
            entry_admission_snapshot_digest=(request.admission_snapshot.digest()),
            binding_constraint=product_decision.status.value,
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
            family_ticket_limits=policy.family_ticket_limits,
            max_ticket_stop_risk_fraction=(policy.max_ticket_stop_risk_fraction),
            max_gross_stop_risk_fraction=(policy.max_gross_stop_risk_fraction),
            max_ticket_initial_margin_fraction=(
                policy.max_ticket_initial_margin_fraction
            ),
            max_gross_initial_margin_utilization=(
                policy.max_gross_initial_margin_utilization
            ),
            directional_stop_risk_limit_fraction=(
                policy.directional_stop_risk_limit_fraction
            ),
            min_materialization_ratio=policy.min_materialization_ratio,
            max_leverage=policy.max_leverage,
            supported_margin_mode=policy.supported_margin_mode,
            post_stop_stress_multiple=policy.post_stop_stress_multiple,
            max_post_fill_stop_risk_overrun_fraction=(
                policy.max_post_fill_stop_risk_overrun_fraction
            ),
        ),
        usage=usage,
        instrument_rules=CapacityInstrumentRules(
            venue_id=rules.venue_id,
            exchange_instrument_id=rules.exchange_instrument_id,
            quantity_step=rules.quantity_step,
            price_tick=rules.price_tick,
            min_quantity=rules.min_quantity,
            min_notional=rules.min_notional,
            exchange_max_leverage=rules.exchange_max_leverage,
            maintenance_margin_brackets=rules.maintenance_margin_brackets,
            maintenance_margin_brackets_digest=(
                rules.maintenance_margin_brackets_digest
            ),
            notional_coefficient=rules.notional_coefficient,
            notional_coefficient_certified=(rules.notional_coefficient_certified),
            projection_version=rules.projection_version,
            observed_at_ms=rules.observed_at_ms,
            valid_until_ms=rules.valid_until_ms,
        ),
        admission_snapshot=request.admission_snapshot,
        account_entry_health=account_entry_health,
        instrument_entry_health=instrument_entry_health,
        entry_order_type=EntryOrderType(event_spec.entry_order_type),
        current_exit_binding=current_exit_binding,
        exit_binding=exit_binding,
        exit_profile=exit_profile,
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
            admission_context=admission_context,
            entry_admission_snapshot_digest=(request.admission_snapshot.digest()),
            binding_constraint=decision.status.value,
            admission_snapshot=request.admission_snapshot,
        )

    result = await issue_ticket(
        uow,
        IssueTicketRequest(
            capacity_claim=decision.claim,
            now_ms=request.now_ms,
            claim_owner=request.claim_owner,
        ),
    )
    if result.status is not IssueTicketStatus.ISSUED:
        return await _refuse(
            uow,
            signal,
            result.status,
            request.now_ms,
            admission_context=admission_context,
            entry_admission_snapshot_digest=request.admission_snapshot.digest(),
            binding_constraint=result.status.value,
            admission_snapshot=request.admission_snapshot,
        )
    if result.status is IssueTicketStatus.ISSUED:
        if result.ticket_id is None:
            raise RuntimeError("issued Ticket is missing its identity")
        await uow.admission_decisions.add(
            freeze_admission_decision(
                signal=signal,
                candidate_set=admission_context.candidate_set,
                exposure_family=admission_context.exposure_family,
                runtime_profile_id=admission_context.runtime_profile_id,
                owner_policy_id=admission_context.owner_policy_id,
                owner_policy_version=admission_context.owner_policy_version,
                venue_id=admission_context.venue_id,
                account_id=admission_context.account_id,
                portfolio_usage=admission_context.portfolio_usage,
                decision_status=AdmissionDecisionStatus.ADMITTED,
                first_blocker=None,
                binding_constraint=None,
                capacity_claim_id=decision.claim.capacity_claim_id,
                ticket_id=result.ticket_id,
                entry_admission_snapshot_digest=(request.admission_snapshot.digest()),
                decided_at_ms=request.now_ms,
            )
        )
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
    *,
    admission_context: _AdmissionDecisionContext | None = None,
    entry_admission_snapshot_digest: str | None = None,
    binding_constraint: str | None = None,
    admission_snapshot: EntryAdmissionSnapshot | None = None,
) -> IssueTicketResult:
    blocker = (
        "signal_invalid_or_stale"
        if status
        in {
            IssueTicketStatus.SIGNAL_INVALID_OR_STALE,
            IssueTicketStatus.FACTS_EXPIRED,
        }
        else status.value
    )
    if admission_context is not None:
        decision = freeze_admission_decision(
            signal=signal,
            candidate_set=admission_context.candidate_set,
            exposure_family=admission_context.exposure_family,
            runtime_profile_id=admission_context.runtime_profile_id,
            owner_policy_id=admission_context.owner_policy_id,
            owner_policy_version=admission_context.owner_policy_version,
            venue_id=admission_context.venue_id,
            account_id=admission_context.account_id,
            portfolio_usage=admission_context.portfolio_usage,
            decision_status=AdmissionDecisionStatus.REJECTED,
            first_blocker=blocker,
            binding_constraint=binding_constraint,
            capacity_claim_id=None,
            ticket_id=None,
            entry_admission_snapshot_digest=entry_admission_snapshot_digest,
            decided_at_ms=now_ms,
        )
        await uow.admission_decisions.add(decision)
        if admission_snapshot is not None:
            shadow = pending_shadow_spec_for_rejection(
                decision=decision,
                signal=signal,
                admission_snapshot=admission_snapshot,
            )
            if shadow is not None:
                await uow.shadow_outcomes.add_pending(shadow)
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
        CapacityClaimStatus.EXPOSURE_FAMILY_CAPACITY_EXHAUSTED: (
            IssueTicketStatus.EXPOSURE_FAMILY_CAPACITY_EXHAUSTED
        ),
        CapacityClaimStatus.DIRECTIONAL_RISK_EXHAUSTED: (
            IssueTicketStatus.BUDGET_EXHAUSTED
        ),
        CapacityClaimStatus.PROTECTION_UNAVAILABLE: (
            IssueTicketStatus.PROTECTION_UNAVAILABLE
        ),
        CapacityClaimStatus.EXIT_LEG_MATERIALIZATION_UNMET: (
            IssueTicketStatus.EXIT_LEG_MATERIALIZATION_UNMET
        ),
    }
    return mapping[status]


def _portfolio_usage(
    *,
    policy,
    usage: CapacityUsage,
    admission_snapshot: EntryAdmissionSnapshot,
    exposure_family: ExposureFamily,
) -> AdmissionPortfolioUsage:
    account = admission_snapshot.account_risk_snapshot
    remaining_gross_risk = max(
        Decimal(0),
        account.total_wallet_balance * policy.max_gross_stop_risk_fraction
        - usage.gross_risk_at_stop,
    )
    remaining_initial_margin = max(
        Decimal(0),
        account.total_margin_balance * policy.max_gross_initial_margin_utilization
        - max(
            account.total_initial_margin,
            usage.current_reserved_margin,
        ),
    )
    return AdmissionPortfolioUsage(
        active_ticket_count=usage.active_ticket_count,
        active_family_ticket_count=(usage.active_family_ticket_count),
        gross_risk_at_stop=usage.gross_risk_at_stop,
        directional_risk_at_stop=usage.directional_risk_at_stop,
        current_reserved_margin=usage.current_reserved_margin,
        remaining_ticket_slots=max(
            0,
            policy.max_concurrent_tickets - usage.active_ticket_count,
        ),
        remaining_family_slots=max(
            0,
            policy.family_ticket_limits.for_family(exposure_family)
            - usage.active_family_ticket_count,
        ),
        remaining_gross_stop_risk=remaining_gross_risk,
        remaining_directional_stop_risk=max(
            Decimal(0),
            account.total_wallet_balance * policy.directional_stop_risk_limit_fraction
            - usage.directional_risk_at_stop,
        ),
        remaining_initial_margin=remaining_initial_margin,
    )
