"""Persist one typed live signal after current-authority validation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.signal import StrategySignal, build_signal_fact_digest


class IngestSignalStatus(StrEnum):
    CANDIDATE_READY = "candidate_ready"
    DUPLICATE_SIGNAL = "duplicate_signal"
    SIGNAL_INVALID_OR_STALE = "signal_invalid_or_stale"
    SCOPE_OR_POLICY_MISMATCH = "scope_or_policy_mismatch"
    SCHEMA_IDENTITY_MISMATCH = "schema_identity_mismatch"


class SignalAuthorityStatus(StrEnum):
    VALID = "valid"
    SIGNAL_INVALID_OR_STALE = "signal_invalid_or_stale"
    SCOPE_OR_POLICY_MISMATCH = "scope_or_policy_mismatch"
    SCHEMA_IDENTITY_MISMATCH = "schema_identity_mismatch"


class IngestSignalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal: StrategySignal
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
        readiness_state="candidate_ready",
        first_blocker=None,
        signal_event_id=request.signal.signal_event_id,
        fact_summary={
            "fact_count": len(request.signal.facts),
            "fact_digest": request.signal.fact_digest,
        },
        updated_at_ms=request.now_ms,
    )
    return IngestSignalResult(
        status=IngestSignalStatus.CANDIDATE_READY,
        signal_event_id=request.signal.signal_event_id,
    )


async def validate_signal_authority(
    uow: KernelUnitOfWork,
    signal: StrategySignal,
    *,
    runtime_commit: str,
    schema_revision: str,
    now_ms: int,
) -> SignalAuthorityStatus:
    if (
        now_ms < signal.occurred_at_ms
        or now_ms >= signal.expires_at_ms
        or not _signal_fact_bundle_is_consistent(signal)
    ):
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
    ):
        return SignalAuthorityStatus.SCOPE_OR_POLICY_MISMATCH

    facts = await uow.signals.get_required_facts(
        runtime_scope_id=signal.runtime_scope_id,
        event_spec_id=signal.event_spec_id,
    )
    if (
        facts is None
        or facts != signal.facts
        or any(
            fact.observed_at_ms > signal.occurred_at_ms
            or fact.valid_until_ms <= now_ms
            or fact.valid_until_ms < signal.expires_at_ms
            for fact in facts
        )
        or build_signal_fact_digest(facts) != signal.fact_digest
    ):
        return SignalAuthorityStatus.SIGNAL_INVALID_OR_STALE

    instrument = await uow.signals.get_instrument(signal.exchange_instrument_id)
    if instrument is None or instrument.status != "active":
        return SignalAuthorityStatus.SCOPE_OR_POLICY_MISMATCH

    capability = await uow.signals.get_runtime_capability("strategy_signal_ingest")
    if not (
        capability
        and capability.enabled
        and capability.certified_commit == runtime_commit
        and capability.schema_revision == schema_revision
    ):
        return SignalAuthorityStatus.SCHEMA_IDENTITY_MISMATCH
    return SignalAuthorityStatus.VALID


def _signal_fact_bundle_is_consistent(signal: StrategySignal) -> bool:
    try:
        digest = build_signal_fact_digest(signal.facts)
    except ValueError:
        return False
    if digest != signal.fact_digest:
        return False
    references = [fact for fact in signal.facts if fact.role == "protection_reference"]
    if len(references) != 1:
        return False
    if any(fact.role == "disable" and fact.satisfied for fact in signal.facts):
        return False
    return not any(
        fact.role != "disable" and not fact.satisfied for fact in signal.facts
    )
