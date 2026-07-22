"""Persist one typed live signal after current-authority validation."""

from __future__ import annotations

from enum import StrEnum
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.application.ports import (
    InstrumentRulesSnapshot,
    KernelUnitOfWork,
)
from src.trading_kernel.domain.signal import ActionableSignal, build_signal_fact_digest


class IngestSignalStatus(StrEnum):
    TICKET_READY = "ticket_ready"
    DUPLICATE_SIGNAL = "duplicate_signal"
    SIGNAL_INVALID_OR_STALE = "signal_invalid_or_stale"
    SCOPE_OR_POLICY_MISMATCH = "scope_or_policy_mismatch"
    ACCOUNT_MODE_INVALID = "account_mode_invalid"
    INSTRUMENT_RULES_INVALID = "instrument_rules_invalid"
    SCHEMA_IDENTITY_MISMATCH = "schema_identity_mismatch"


class SignalAuthorityStatus(StrEnum):
    VALID = "valid"
    SIGNAL_INVALID_OR_STALE = "signal_invalid_or_stale"
    SCOPE_OR_POLICY_MISMATCH = "scope_or_policy_mismatch"
    ACCOUNT_MODE_INVALID = "account_mode_invalid"
    INSTRUMENT_RULES_INVALID = "instrument_rules_invalid"
    SCHEMA_IDENTITY_MISMATCH = "schema_identity_mismatch"


class IngestSignalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal: ActionableSignal
    runtime_commit: str
    schema_revision: str
    now_ms: int


class IngestSignalResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: IngestSignalStatus
    signal_event_id: str | None


async def ingest_signal(
    uow: KernelUnitOfWork,
    request: IngestSignalRequest,
) -> IngestSignalResult:
    authority = await validate_signal_authority(
        uow,
        request.signal,
        runtime_commit=request.runtime_commit,
        schema_revision=request.schema_revision,
        now_ms=request.now_ms,
    )
    if authority is not SignalAuthorityStatus.VALID:
        return IngestSignalResult(
            status=IngestSignalStatus(authority.value),
            signal_event_id=request.signal.signal_event_id,
        )
    if not await uow.signals.add(request.signal):
        return IngestSignalResult(
            status=IngestSignalStatus.DUPLICATE_SIGNAL,
            signal_event_id=request.signal.signal_event_id,
        )
    await uow.signals.save_readiness(
        runtime_scope_id=request.signal.runtime_scope_id,
        readiness_state="ticket_ready",
        first_blocker=None,
        signal_event_id=request.signal.signal_event_id,
        fact_summary={"fact_digest": request.signal.fact_digest},
        updated_at_ms=request.now_ms,
    )
    return IngestSignalResult(
        status=IngestSignalStatus.TICKET_READY,
        signal_event_id=request.signal.signal_event_id,
    )


async def validate_signal_authority(
    uow: KernelUnitOfWork,
    signal: ActionableSignal,
    *,
    runtime_commit: str,
    schema_revision: str,
    now_ms: int,
) -> SignalAuthorityStatus:
    if now_ms < signal.occurred_at_ms or now_ms >= signal.expires_at_ms:
        return SignalAuthorityStatus.SIGNAL_INVALID_OR_STALE

    scope = await uow.signals.get_runtime_scope(signal.runtime_scope_id)
    if scope is None or not scope.enabled:
        return SignalAuthorityStatus.SCOPE_OR_POLICY_MISMATCH
    if (
        scope.scope_version != signal.runtime_scope_version
        or scope.strategy_group_id != signal.strategy_group_id
        or scope.strategy_version_id != signal.strategy_version_id
        or scope.event_spec_id != signal.event_spec_id
        or scope.exchange_instrument_id != signal.exchange_instrument_id
        or scope.position_side != signal.position_side
    ):
        return SignalAuthorityStatus.SCOPE_OR_POLICY_MISMATCH

    strategy_group = await uow.signals.get_strategy_group(signal.strategy_group_id)
    strategy_version = await uow.signals.get_strategy_version(
        signal.strategy_version_id
    )
    event_spec = await uow.signals.get_event_spec(signal.event_spec_id)
    if (
        strategy_group is None
        or strategy_group.status != "active"
        or strategy_group.active_version_id != signal.strategy_version_id
        or strategy_version is None
        or strategy_version.status != "active"
        or strategy_version.strategy_group_id != signal.strategy_group_id
        or event_spec is None
        or event_spec.status != "active"
        or event_spec.strategy_version_id != signal.strategy_version_id
        or event_spec.position_side != signal.position_side
        or event_spec.entry_order_type != signal.terms.entry_order_type.value
    ):
        return SignalAuthorityStatus.SCOPE_OR_POLICY_MISMATCH

    facts = await uow.signals.get_required_facts(
        runtime_scope_id=signal.runtime_scope_id,
        event_spec_id=signal.event_spec_id,
    )
    if (
        facts is None
        or any(
            not fact.satisfied
            or fact.observed_at_ms > signal.occurred_at_ms
            or fact.valid_until_ms <= now_ms
            for fact in facts
        )
        or build_signal_fact_digest(facts) != signal.fact_digest
    ):
        return SignalAuthorityStatus.SIGNAL_INVALID_OR_STALE

    profile = await uow.signals.get_runtime_profile(scope.runtime_profile_id)
    instrument = await uow.signals.get_instrument(signal.exchange_instrument_id)
    rules = await uow.signals.get_instrument_rules(signal.exchange_instrument_id)
    policy = await uow.entry_admission.get_owner_policy(scope.owner_policy_id)
    if profile is None or profile.status != "active" or profile.environment != "live":
        return SignalAuthorityStatus.SCOPE_OR_POLICY_MISMATCH
    if profile.position_mode != "independent_sides":
        return SignalAuthorityStatus.ACCOUNT_MODE_INVALID
    if (
        instrument is None
        or instrument.status != "active"
        or instrument.venue_id != profile.venue_id
        or rules is None
        or rules.valid_until_ms <= now_ms
    ):
        return SignalAuthorityStatus.INSTRUMENT_RULES_INVALID
    if policy is None or not policy.enabled or not policy.real_submit_enabled:
        return SignalAuthorityStatus.SCOPE_OR_POLICY_MISMATCH
    if not _terms_fit_instrument_rules(signal, rules):
        return SignalAuthorityStatus.INSTRUMENT_RULES_INVALID

    capability = await uow.signals.get_runtime_capability("signal_to_ticket")
    if not (
        capability
        and capability.enabled
        and capability.certified_commit == runtime_commit
        and capability.schema_revision == schema_revision
    ):
        return SignalAuthorityStatus.SCHEMA_IDENTITY_MISMATCH
    return SignalAuthorityStatus.VALID


def _terms_fit_instrument_rules(
    signal: ActionableSignal,
    rules: InstrumentRulesSnapshot,
) -> bool:
    quantity_step = rules.quantity_step
    price_tick = rules.price_tick
    terms = signal.terms
    if (
        terms.quantity < rules.min_quantity
        or terms.notional < rules.min_notional
        or not _is_multiple(terms.quantity, quantity_step)
        or not _is_multiple(terms.initial_stop_price, price_tick)
    ):
        return False
    if terms.entry_limit_price is not None and not _is_multiple(
        terms.entry_limit_price,
        price_tick,
    ):
        return False
    return all(_is_multiple(price, price_tick) for price in terms.take_profit_prices)


def _is_multiple(value: Decimal, increment: Decimal) -> bool:
    return increment > 0 and value % increment == 0
