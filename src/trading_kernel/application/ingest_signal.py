"""Persist one typed live signal after current-authority validation."""

from __future__ import annotations

from enum import StrEnum
from itertools import pairwise

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.application.ports import KernelUnitOfWork, RuntimeScopeSnapshot
from src.trading_kernel.domain.instrument_selection import (
    SOR_LONG_EVENT_SPEC_ID,
    SOR_SHORT_EVENT_SPEC_ID,
)
from src.trading_kernel.domain.selection_authority import (
    AuthorityOutcome,
    SelectionControl,
    SelectionMode,
    SelectionSessionAuthority,
    UniverseAuthorityPair,
    authority_successor_is_compatible,
    selection_authority_allows_new_entry,
)
from src.trading_kernel.domain.signal import StrategySignal, build_signal_fact_digest


class IngestSignalStatus(StrEnum):
    CANDIDATE_READY = "candidate_ready"
    DUPLICATE_SIGNAL = "duplicate_signal"
    SIGNAL_INVALID_OR_STALE = "signal_invalid_or_stale"
    SCOPE_OR_POLICY_MISMATCH = "scope_or_policy_mismatch"
    SCHEMA_IDENTITY_MISMATCH = "schema_identity_mismatch"
    SELECTION_ENTRY_VACUUM = "selection_entry_vacuum"
    SELECTION_AUTHORITY_INVALID = "selection_authority_invalid"
    SELECTION_TRIGGER_SUPPRESSED = "selection_trigger_suppressed"


class SignalAuthorityStatus(StrEnum):
    VALID = "valid"
    SIGNAL_INVALID_OR_STALE = "signal_invalid_or_stale"
    SCOPE_OR_POLICY_MISMATCH = "scope_or_policy_mismatch"
    SCHEMA_IDENTITY_MISMATCH = "schema_identity_mismatch"
    SELECTION_ENTRY_VACUUM = "selection_entry_vacuum"
    SELECTION_AUTHORITY_INVALID = "selection_authority_invalid"
    SELECTION_TRIGGER_SUPPRESSED = "selection_trigger_suppressed"


class SelectionEntryAuthorityStatus(StrEnum):
    VALID = "valid"
    VACUUM_OPEN = "vacuum_open"
    AUTHORITY_INVALID = "authority_invalid"
    TRIGGER_SUPPRESSED = "trigger_suppressed"
    OWNER_OR_POLICY_BLOCKED = "owner_or_policy_blocked"


class SelectionEntryAuthorityFacts(BaseModel):
    """Bounded current facts used identically at every new-ENTRY boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_control: SelectionControl | None
    current_authority: SelectionSessionAuthority | None
    authority_chain: tuple[SelectionSessionAuthority, ...]
    current_pair: UniverseAuthorityPair | None
    active_generation_pair: UniverseAuthorityPair | None
    scoped_vacuum_open: bool
    authority_interrupted: bool
    owner_entry_enabled: bool
    owner_control_version: int | None
    global_policy_enabled: bool
    trigger_suppressed: bool


class SelectionEntryAuthorityDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SelectionEntryAuthorityStatus
    selection_authority_id: str | None
    current_selection_authority_id: str | None
    reason_code: str

    @property
    def allowed(self) -> bool:
        return self.status is SelectionEntryAuthorityStatus.VALID


def evaluate_selection_entry_authority(
    facts: SelectionEntryAuthorityFacts,
    *,
    birth_selection_authority_id: str | None,
    observed_close_time_ms: int,
    now_ms: int,
    allow_current_as_birth: bool,
) -> SelectionEntryAuthorityDecision:
    """Validate one exact or uninterrupted compatible birth Authority lineage."""

    control = facts.selection_control
    current = facts.current_authority
    if control is None:
        if birth_selection_authority_id is not None:
            return _selection_refused(
                SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
                "selection_authority_without_control",
                current,
            )
        return _selection_allowed(None, current)
    if control.selection_mode is SelectionMode.DISABLED:
        return _selection_refused(
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            "selection_control_disabled",
            current,
        )
    if facts.scoped_vacuum_open:
        return _selection_refused(
            SelectionEntryAuthorityStatus.VACUUM_OPEN,
            "selection_entry_vacuum_open",
            current,
        )
    if (
        not facts.owner_entry_enabled
        or not facts.global_policy_enabled
        or facts.owner_control_version is None
    ):
        return _selection_refused(
            SelectionEntryAuthorityStatus.OWNER_OR_POLICY_BLOCKED,
            "selection_owner_or_policy_blocked",
            current,
        )

    current_is_live = bool(
        current
        and current.effective_from_ms <= now_ms < current.expires_at_ms
    )
    if control.selection_mode is SelectionMode.STATIC_BASELINE:
        if not current_is_live:
            if birth_selection_authority_id is not None:
                return _selection_refused(
                    SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
                    "static_signal_has_unexpected_selection_authority",
                    current,
                )
            return _selection_allowed(None, current)
        assert current is not None
        if (
            current.selection_mode is not SelectionMode.STATIC_BASELINE
            or current.authority_outcome is not AuthorityOutcome.FALLBACK_PREVIOUS
        ):
            return _selection_refused(
                SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
                "static_selection_transition_authority_invalid",
                current,
            )
    elif current is None:
        return _selection_refused(
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            "selection_current_authority_missing",
            current,
        )

    assert current is not None
    if current.selection_mode is not control.selection_mode:
        return _selection_refused(
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            "selection_control_authority_mode_mismatch",
            current,
        )
    if current.authority_outcome not in {
        AuthorityOutcome.PRE_FENCE_CONTINUITY,
        AuthorityOutcome.ACTIVE_NEW,
        AuthorityOutcome.NO_CHANGE,
        AuthorityOutcome.FALLBACK_PREVIOUS,
    }:
        return _selection_refused(
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            "selection_authority_non_trading_outcome",
            current,
        )
    if facts.current_pair is None or current.authorized_pair != facts.current_pair:
        return _selection_refused(
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            "selection_authority_pair_mismatch",
            current,
        )
    if (
        current.authority_outcome is AuthorityOutcome.ACTIVE_NEW
        and facts.active_generation_pair != current.authorized_pair
    ):
        return _selection_refused(
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            "selection_authority_generation_mismatch",
            current,
        )
    if current.owner_control_version != facts.owner_control_version:
        return _selection_refused(
            SelectionEntryAuthorityStatus.OWNER_OR_POLICY_BLOCKED,
            "selection_owner_control_version_drift",
            current,
        )
    observed_session_start_ms = (observed_close_time_ms // 86_400_000) * 86_400_000
    if current.session_start_ms != observed_session_start_ms:
        return _selection_refused(
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            "selection_authority_period_mismatch",
            current,
        )
    if not selection_authority_allows_new_entry(
        current,
        now_ms=now_ms,
        observed_close_time_ms=observed_close_time_ms,
        scoped_vacuum_open=facts.scoped_vacuum_open,
    ):
        reason = (
            "selection_close_before_first_eligible"
            if current.first_eligible_close_time_ms is not None
            and observed_close_time_ms < current.first_eligible_close_time_ms
            else "selection_authority_time_window_invalid"
        )
        return _selection_refused(
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            reason,
            current,
        )
    if facts.trigger_suppressed:
        return _selection_refused(
            SelectionEntryAuthorityStatus.TRIGGER_SUPPRESSED,
            "selection_first_trigger_already_consumed",
            current,
        )

    birth_id = birth_selection_authority_id
    if birth_id is None and allow_current_as_birth:
        birth_id = current.selection_authority_id
    if birth_id is None:
        return _selection_refused(
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            "selection_birth_authority_missing",
            current,
        )
    chain = facts.authority_chain
    if (
        not chain
        or chain[0].selection_authority_id != birth_id
        or chain[-1].selection_authority_id != current.selection_authority_id
    ):
        return _selection_refused(
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            "selection_authority_lineage_missing",
            current,
        )
    if facts.authority_interrupted:
        return _selection_refused(
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            "selection_authority_lineage_interrupted",
            current,
        )
    for birth, successor in pairwise(chain):
        if not authority_successor_is_compatible(
            birth=birth,
            successor=successor,
            vacuum_opened=False,
            owner_control_continuous=True,
            global_policy_continuous=True,
            eligible_close_coverage_continuous=True,
        ):
            return _selection_refused(
                SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
                "selection_authority_successor_incompatible",
                current,
            )
    return _selection_allowed(birth_id, current)


def _selection_allowed(
    selection_authority_id: str | None,
    current: SelectionSessionAuthority | None,
) -> SelectionEntryAuthorityDecision:
    return SelectionEntryAuthorityDecision(
        status=SelectionEntryAuthorityStatus.VALID,
        selection_authority_id=selection_authority_id,
        current_selection_authority_id=(
            None if current is None else current.selection_authority_id
        ),
        reason_code="selection_authority_valid",
    )


def _selection_refused(
    status: SelectionEntryAuthorityStatus,
    reason_code: str,
    current: SelectionSessionAuthority | None,
) -> SelectionEntryAuthorityDecision:
    return SelectionEntryAuthorityDecision(
        status=status,
        selection_authority_id=None,
        current_selection_authority_id=(
            None if current is None else current.selection_authority_id
        ),
        reason_code=reason_code,
    )


async def resolve_selection_entry_authority(
    uow: KernelUnitOfWork,
    *,
    runtime_scope: RuntimeScopeSnapshot,
    birth_selection_authority_id: str | None,
    observed_close_time_ms: int,
    now_ms: int,
    allow_current_as_birth: bool,
    lock_current: bool = False,
) -> SelectionEntryAuthorityDecision:
    """Read exact bounded PostgreSQL facts and apply the shared pure evaluator."""

    control = await uow.instrument_selection.get_selection_control(
        runtime_scope.strategy_group_id,
        for_update=lock_current,
    )
    if control is None:
        return evaluate_selection_entry_authority(
            SelectionEntryAuthorityFacts(
                selection_control=None,
                current_authority=None,
                authority_chain=(),
                current_pair=None,
                active_generation_pair=None,
                scoped_vacuum_open=False,
                authority_interrupted=False,
                owner_entry_enabled=True,
                owner_control_version=None,
                global_policy_enabled=True,
                trigger_suppressed=False,
            ),
            birth_selection_authority_id=birth_selection_authority_id,
            observed_close_time_ms=observed_close_time_ms,
            now_ms=now_ms,
            allow_current_as_birth=allow_current_as_birth,
        )

    current = await uow.instrument_selection.get_current_authority(
        control.selection_spec_id,
        for_update=lock_current,
    )
    vacuum = await uow.instrument_selection.get_current_entry_vacuum(
        strategy_group_id=runtime_scope.strategy_group_id,
        selection_spec_id=control.selection_spec_id,
    )
    owner_control = await uow.owner_controls.get_strategy_control(
        runtime_scope.strategy_group_id
    )
    policy = await uow.entry_admission.get_owner_policy(
        runtime_scope.owner_policy_id
    )
    long_current = await uow.strategy_universes.get_current(
        SOR_LONG_EVENT_SPEC_ID
    )
    short_current = await uow.strategy_universes.get_current(
        SOR_SHORT_EVENT_SPEC_ID
    )
    current_pair = (
        None
        if long_current is None or short_current is None
        else UniverseAuthorityPair(
            long_universe_version_id=long_current.universe_version_id,
            short_universe_version_id=short_current.universe_version_id,
        )
    )
    resolved_birth_id = birth_selection_authority_id
    if resolved_birth_id is None and allow_current_as_birth and current is not None:
        resolved_birth_id = current.selection_authority_id
    chain = (
        ()
        if current is None or resolved_birth_id is None
        else await uow.signals.get_selection_authority_chain(
            selection_spec_id=control.selection_spec_id,
            birth_selection_authority_id=resolved_birth_id,
            current_selection_authority_id=current.selection_authority_id,
            max_depth=64,
        )
    )
    interrupted = bool(
        chain
        and await uow.signals.selection_authority_was_interrupted(
            strategy_group_id=runtime_scope.strategy_group_id,
            selection_spec_id=control.selection_spec_id,
            owner_policy_id=runtime_scope.owner_policy_id,
            after_ms=chain[0].created_at_ms,
            through_ms=now_ms,
        )
    )
    active_generation_pair = None
    if (
        current is not None
        and current.authority_outcome is AuthorityOutcome.ACTIVE_NEW
        and current.authorized_pair is not None
        and current.materialization_generation_id is not None
        and await uow.signals.selection_generation_matches_pair(
            materialization_generation_id=current.materialization_generation_id,
            long_universe_version_id=(
                current.authorized_pair.long_universe_version_id
            ),
            short_universe_version_id=(
                current.authorized_pair.short_universe_version_id
            ),
        )
    ):
        active_generation_pair = current.authorized_pair
    session_reference = str(
        (observed_close_time_ms // 86_400_000) * 86_400_000
    )
    suppressed = await uow.signals.is_strategy_trigger_suppressed(
        event_spec_id=runtime_scope.event_spec_id,
        exchange_instrument_id=runtime_scope.exchange_instrument_id,
        session_reference=session_reference,
    )
    return evaluate_selection_entry_authority(
        SelectionEntryAuthorityFacts(
            selection_control=control,
            current_authority=current,
            authority_chain=chain,
            current_pair=current_pair,
            active_generation_pair=active_generation_pair,
            scoped_vacuum_open=bool(vacuum and vacuum.blocks_new_entry),
            authority_interrupted=interrupted,
            owner_entry_enabled=bool(
                owner_control and owner_control.entry_state.value == "enabled"
            ),
            owner_control_version=(
                None if owner_control is None else owner_control.control_version
            ),
            global_policy_enabled=bool(
                policy
                and policy.enabled
                and policy.new_entry_submit_enabled
                and policy.scope is not None
                and policy.scope.authorizes(
                    event_spec_id=runtime_scope.event_spec_id,
                    runtime_profile_id=runtime_scope.runtime_profile_id,
                )
            ),
            trigger_suppressed=suppressed,
        ),
        birth_selection_authority_id=birth_selection_authority_id,
        observed_close_time_ms=observed_close_time_ms,
        now_ms=now_ms,
        allow_current_as_birth=allow_current_as_birth,
    )


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
    if (
        scope is None
        or scope.lifecycle_state != "active"
        or not scope.observation_enabled
        or not scope.entry_enabled
    ):
        return SignalAuthorityStatus.SCOPE_OR_POLICY_MISMATCH
    if (
        scope.scope_version != signal.runtime_scope_version
        or scope.strategy_group_id != signal.strategy_group_id
        or scope.strategy_version_id != signal.strategy_version_id
        or scope.event_spec_id != signal.event_spec_id
        or scope.universe_version_id != signal.universe_version_id
        or scope.universe_semantic_digest != signal.universe_semantic_digest
        or scope.exchange_instrument_id != signal.exchange_instrument_id
        or scope.position_side != signal.position_side
    ):
        return SignalAuthorityStatus.SCOPE_OR_POLICY_MISMATCH

    universe = await uow.signals.get_active_universe_member(
        event_spec_id=signal.event_spec_id,
        exchange_instrument_id=signal.exchange_instrument_id,
    )
    if (
        universe is None
        or universe.universe_version_id != signal.universe_version_id
        or universe.semantic_digest != signal.universe_semantic_digest
    ):
        return SignalAuthorityStatus.SCOPE_OR_POLICY_MISMATCH

    selection = await resolve_selection_entry_authority(
        uow,
        runtime_scope=scope,
        birth_selection_authority_id=signal.selection_authority_id,
        observed_close_time_ms=signal.occurred_at_ms,
        now_ms=now_ms,
        allow_current_as_birth=False,
    )
    if not selection.allowed:
        return _signal_selection_status(selection.status)

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


def _signal_selection_status(
    status: SelectionEntryAuthorityStatus,
) -> SignalAuthorityStatus:
    if status is SelectionEntryAuthorityStatus.VACUUM_OPEN:
        return SignalAuthorityStatus.SELECTION_ENTRY_VACUUM
    if status is SelectionEntryAuthorityStatus.TRIGGER_SUPPRESSED:
        return SignalAuthorityStatus.SELECTION_TRIGGER_SUPPRESSED
    if status is SelectionEntryAuthorityStatus.OWNER_OR_POLICY_BLOCKED:
        return SignalAuthorityStatus.SCOPE_OR_POLICY_MISMATCH
    return SignalAuthorityStatus.SELECTION_AUTHORITY_INVALID


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
