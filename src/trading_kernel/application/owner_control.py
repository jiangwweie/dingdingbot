"""Owner control-plane application transitions."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator

from src.trading_kernel.application.controlled_exit import (
    ControlledExitClassification,
    classify_controlled_exit_status,
)
from src.trading_kernel.application.ports import (
    AggregateVersionConflict,
    ExitProfileAuthorityConflict,
    KernelUnitOfWork,
    OwnerPolicySnapshot,
    UnitOfWorkFactory,
)
from src.trading_kernel.application.reconcile_ticket import (
    ExitTicketRequest,
    request_exit,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.exit_policy import (
    CurrentEventExitBinding,
    ExitProfileRecord,
    build_event_exit_binding,
)
from src.trading_kernel.domain.instrument_selection import DAY_MS, INTERVAL_MS
from src.trading_kernel.domain.owner_control import (
    ControlOperationState,
    OwnerAuthorization,
    OwnerControlOperation,
    StrategyEntryControl,
    StrategyEntryState,
    advance_control_operation,
    transition_strategy_entry_control,
)
from src.trading_kernel.domain.selection_authority import (
    SelectionControl,
    SelectionMode,
)
from src.trading_kernel.domain.strategy_entry_vacuum import (
    StrategyEntryVacuum,
    StrategyEntryVacuumState,
)


class OwnerControlConflict(RuntimeError):
    """The supplied optimistic version or snapshot is no longer current."""


class OwnerControlBlocked(RuntimeError):
    """Current authoritative facts block the requested expansion or exit."""


class ControlMutationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_version: int
    reason: str
    idempotency_key: str
    owner_identity: str
    now_ms: int

    @field_validator("reason", "idempotency_key", "owner_identity", mode="before")
    @classmethod
    def _require_text(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("control request text must be non-blank")
        return normalized


class FlattenPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_profile_id: Literal["account-wide"] = "account-wide"
    venue_id: str
    account_id: str
    owner_policy_version: int
    global_entry_enabled: bool
    ticket_ids: tuple[str, ...]
    ticket_states: dict[str, str]
    snapshot_digest: str
    first_blocker: str | None = None


class FlattenSubmitRequest(ControlMutationRequest):
    runtime_profile_id: Literal["account-wide"] = "account-wide"
    venue_id: str
    account_id: str
    snapshot_digest: str


class ExitProfileBindingMutationRequest(ControlMutationRequest):
    expected_binding_id: str
    target_exit_profile_id: str
    target_exit_profile_semantic_hash: str

    @field_validator(
        "expected_binding_id",
        "target_exit_profile_id",
        mode="before",
    )
    @classmethod
    def _require_exit_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("ExitProfile mutation identities must be non-blank")
        return normalized

    @field_validator("target_exit_profile_semantic_hash")
    @classmethod
    def _require_profile_hash(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) != 71:
            raise ValueError("ExitProfile mutation hash must be canonical")
        return value


class ExitProfileRetirementRequest(ControlMutationRequest):
    exit_profile_id: str
    exit_profile_semantic_hash: str

    @field_validator("exit_profile_id", mode="before")
    @classmethod
    def _require_retirement_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("ExitProfile retirement identity must be non-blank")
        return normalized

    @field_validator("exit_profile_semantic_hash")
    @classmethod
    def _require_retirement_hash(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) != 71:
            raise ValueError("ExitProfile retirement hash must be canonical")
        return value


async def set_strategy_entry_state(
    uow: KernelUnitOfWork,
    *,
    strategy_group_id: str,
    target_state: StrategyEntryState,
    request: ControlMutationRequest,
    authentication_strength: Literal["session", "totp_step_up"],
) -> StrategyEntryControl:
    existing_authorization = (
        await uow.owner_controls.get_authorization_by_idempotency_key(
            request.idempotency_key
        )
    )
    current = await uow.owner_controls.get_strategy_control(
        strategy_group_id,
        for_update=True,
    )
    if current is None:
        raise OwnerControlBlocked("strategy_control_missing")
    if existing_authorization is not None:
        _require_matching_authorization(
            existing_authorization,
            purpose=(
                "strategy_pause"
                if target_state is StrategyEntryState.PAUSED
                else "strategy_resume"
            ),
            request=request,
            target_scope={"strategy_group_id": strategy_group_id},
        )
        return current
    if current.control_version != request.expected_version:
        raise OwnerControlConflict("strategy_control_version_conflict")
    strategy_group = await uow.signals.get_strategy_group(strategy_group_id)
    if strategy_group is None or strategy_group.status != "active":
        raise OwnerControlBlocked("strategy_group_not_active")
    if current.entry_state is target_state:
        return current

    operation: Literal["pause", "resume"] = (
        "pause" if target_state is StrategyEntryState.PAUSED else "resume"
    )
    authorization_purpose: Literal["strategy_pause", "strategy_resume"] = (
        "strategy_pause" if operation == "pause" else "strategy_resume"
    )
    authorization = _authorization(
        purpose=authorization_purpose,
        request=request,
        authentication_strength=authentication_strength,
        target_scope={"strategy_group_id": strategy_group_id},
    )
    event_id = f"strategy-control-event:{uuid4().hex}"
    next_control = transition_strategy_entry_control(
        current,
        target_state=target_state,
        event_id=event_id,
        reason=request.reason,
        now_ms=request.now_ms,
    )
    await uow.owner_controls.add_authorization(authorization)
    await uow.owner_controls.save_strategy_control(
        current=next_control,
        authorization_id=authorization.authorization_id,
        operation=operation,
        payload={"owner_identity": request.owner_identity},
    )
    if target_state is StrategyEntryState.PAUSED:
        selection_control = await uow.instrument_selection.get_selection_control(
            strategy_group_id,
            for_update=True,
        )
        if selection_control is not None:
            session_start_ms = (request.now_ms // DAY_MS) * DAY_MS
            await uow.instrument_selection.open_owner_paused_entry_vacuum(
                StrategyEntryVacuum(
                    entry_vacuum_id=(
                        f"vacuum:{strategy_group_id}:{session_start_ms}:"
                        f"owner-pause:{next_control.control_version}"
                    ),
                    strategy_group_id=strategy_group_id,
                    selection_spec_id=selection_control.selection_spec_id,
                    session_start_ms=session_start_ms,
                    source_generation_id=None,
                    state=StrategyEntryVacuumState.OPEN,
                    fenced_at_ms=request.now_ms,
                    drained_at_ms=None,
                    resolved_at_ms=None,
                    first_blocker="OWNER_PAUSED",
                    projection_version=1,
                )
            )
    return next_control


async def set_global_entry_state(
    uow: KernelUnitOfWork,
    *,
    owner_policy_id: str,
    enabled: bool,
    request: ControlMutationRequest,
    authentication_strength: Literal["session", "totp_step_up"],
) -> OwnerPolicySnapshot:
    current = await uow.entry_admission.get_owner_policy(owner_policy_id)
    if current is None:
        raise OwnerControlBlocked("owner_policy_missing")
    existing = await uow.owner_controls.get_authorization_by_idempotency_key(
        request.idempotency_key
    )
    if existing is not None:
        _require_matching_authorization(
            existing,
            purpose="entry_resume" if enabled else "entry_pause",
            request=request,
            target_scope={"owner_policy_id": owner_policy_id},
        )
        return current
    if current.policy_version != request.expected_version:
        raise OwnerControlConflict("owner_policy_version_conflict")
    if current.new_entry_submit_enabled == enabled:
        return current
    if enabled:
        blocker = await uow.owner_controls.get_global_entry_resume_blocker(
            owner_policy_id=owner_policy_id,
        )
        if blocker is not None:
            raise OwnerControlBlocked(blocker)
    authorization = _authorization(
        purpose="entry_resume" if enabled else "entry_pause",
        request=request,
        authentication_strength=authentication_strength,
        target_scope={"owner_policy_id": owner_policy_id},
    )
    await uow.owner_controls.add_authorization(authorization)
    try:
        return await uow.owner_controls.set_global_entry_enabled(
            owner_policy_id=owner_policy_id,
            expected_version=request.expected_version,
            enabled=enabled,
            authorization_id=authorization.authorization_id,
            reason=request.reason,
            updated_at_ms=request.now_ms,
        )
    except AggregateVersionConflict as error:
        raise OwnerControlConflict("owner_policy_version_conflict") from error


async def stage_dynamic_selection_mode(
    uow: KernelUnitOfWork,
    *,
    strategy_group_id: str,
    effective_session_start_ms: int,
    request: ControlMutationRequest,
    authentication_strength: Literal["totp_step_up"],
) -> SelectionControl:
    """Authorize the first Static-to-Dynamic attempt for the next UTC Session."""

    if authentication_strength != "totp_step_up":
        raise OwnerControlBlocked("selection_mode_change_requires_step_up")
    target_scope: dict[str, JsonValue] = {
        "strategy_group_id": strategy_group_id,
        "target_selection_mode": SelectionMode.DYNAMIC_SELECTION.value,
        "effective_session_start_ms": effective_session_start_ms,
    }
    existing = await uow.owner_controls.get_authorization_by_idempotency_key(
        request.idempotency_key
    )
    current = await uow.instrument_selection.get_selection_control(
        strategy_group_id,
        for_update=True,
    )
    if current is None:
        raise OwnerControlBlocked("selection_control_missing")
    if existing is not None:
        _require_matching_authorization(
            existing,
            purpose="selection_mode_change",
            request=request,
            target_scope=target_scope,
        )
        if existing.authentication_strength != "totp_step_up":
            raise OwnerControlConflict("selection_authorization_strength_conflict")
        return current
    if current.control_version != request.expected_version:
        raise OwnerControlConflict("selection_control_version_conflict")
    if current.selection_mode is not SelectionMode.STATIC_BASELINE:
        raise OwnerControlBlocked("selection_mode_not_static_baseline")
    if current.pending_selection_mode is not None:
        raise OwnerControlBlocked("selection_mode_transition_already_pending")
    next_session_start_ms = _next_dynamic_selection_session_start_ms(request.now_ms)
    if effective_session_start_ms != next_session_start_ms:
        raise OwnerControlBlocked("selection_effective_session_not_next")

    authorization = _authorization(
        purpose="selection_mode_change",
        request=request,
        authentication_strength=authentication_strength,
        target_scope=target_scope,
    )
    await uow.owner_controls.add_authorization(authorization)
    staged = await uow.instrument_selection.stage_pending_selection_mode(
        strategy_group_id=strategy_group_id,
        expected_control_version=current.control_version,
        expected_current_mode=SelectionMode.STATIC_BASELINE,
        pending_mode=SelectionMode.DYNAMIC_SELECTION,
        effective_session_start_ms=effective_session_start_ms,
        authorization_id=authorization.authorization_id,
        updated_at_ms=request.now_ms,
    )
    if staged is None:
        raise OwnerControlConflict("selection_control_version_conflict")
    return staged


def _next_dynamic_selection_session_start_ms(now_ms: int) -> int:
    session_start_ms = (now_ms // DAY_MS) * DAY_MS
    decision_boundary_ms = session_start_ms + 4 * INTERVAL_MS
    return (
        session_start_ms if now_ms < decision_boundary_ms else session_start_ms + DAY_MS
    )


async def switch_event_exit_profile(
    uow: KernelUnitOfWork,
    *,
    strategy_group_id: str,
    event_spec_id: str,
    request: ExitProfileBindingMutationRequest,
    authentication_strength: Literal["totp_step_up"],
) -> CurrentEventExitBinding:
    if authentication_strength != "totp_step_up":
        raise OwnerControlBlocked("exit_profile_bind_requires_step_up")
    await uow.exit_profiles.acquire_authority_write_lock()
    previous = await uow.exit_profiles.get_binding(request.expected_binding_id)
    if previous is None or previous.event_spec_id != event_spec_id:
        raise OwnerControlBlocked("exit_binding_missing")
    binding = build_event_exit_binding(
        exit_binding_id=(
            f"exit-binding:{event_spec_id}:v{previous.binding_version + 1}"
        ),
        binding_version=previous.binding_version + 1,
        event_spec_id=event_spec_id,
        exit_profile_id=request.target_exit_profile_id,
        exit_profile_semantic_hash=request.target_exit_profile_semantic_hash,
        activation_reason=request.reason,
        created_at_ms=request.now_ms,
    )
    target_scope: dict[str, JsonValue] = {
        "strategy_group_id": strategy_group_id,
        "event_spec_id": event_spec_id,
        "expected_binding_id": request.expected_binding_id,
        "target_exit_profile_id": request.target_exit_profile_id,
        "target_exit_profile_semantic_hash": (
            request.target_exit_profile_semantic_hash
        ),
        "target_exit_binding_id": binding.exit_binding_id,
        "target_binding_semantic_hash": binding.binding_semantic_hash,
    }
    existing = await uow.owner_controls.get_authorization_by_idempotency_key(
        request.idempotency_key
    )
    if existing is not None:
        _require_matching_authorization(
            existing,
            purpose="exit_profile_bind",
            request=request,
            target_scope=target_scope,
        )
        if existing.authentication_strength != "totp_step_up":
            raise OwnerControlBlocked("exit_profile_bind_requires_step_up")
        committed_binding = build_event_exit_binding(
            exit_binding_id=binding.exit_binding_id,
            binding_version=binding.binding_version,
            event_spec_id=event_spec_id,
            exit_profile_id=request.target_exit_profile_id,
            exit_profile_semantic_hash=request.target_exit_profile_semantic_hash,
            activation_reason=request.reason,
            created_at_ms=existing.authorized_at_ms,
        )
        committed = await uow.exit_profiles.get_binding(
            committed_binding.exit_binding_id
        )
        if committed != committed_binding:
            raise OwnerControlBlocked("exit_binding_idempotency_result_missing")
        return CurrentEventExitBinding(
            event_spec_id=event_spec_id,
            exit_binding_id=committed_binding.exit_binding_id,
            binding_semantic_hash=committed_binding.binding_semantic_hash,
            projection_version=request.expected_version + 1,
            activated_at_ms=existing.authorized_at_ms,
        )
    current = await uow.exit_profiles.get_current_binding(
        event_spec_id,
        for_update=True,
    )
    if current is None:
        raise OwnerControlBlocked("exit_binding_current_missing")
    if (
        current.projection_version != request.expected_version
        or current.exit_binding_id != request.expected_binding_id
    ):
        raise OwnerControlConflict("exit_binding_version_conflict")
    event_spec = await uow.signals.get_event_spec(event_spec_id)
    if event_spec is None or event_spec.status != "active":
        raise OwnerControlBlocked("event_spec_not_active")
    strategy_version = await uow.signals.get_strategy_version(
        event_spec.strategy_version_id
    )
    if (
        strategy_version is None
        or strategy_version.status != "active"
        or strategy_version.strategy_group_id != strategy_group_id
    ):
        raise OwnerControlBlocked("event_strategy_scope_mismatch")
    target = await uow.exit_profiles.get_profile(
        exit_profile_id=request.target_exit_profile_id,
        semantic_hash=request.target_exit_profile_semantic_hash,
    )
    if target is None or target.status != "active":
        raise OwnerControlBlocked("exit_profile_not_active")
    authorization = _authorization(
        purpose="exit_profile_bind",
        request=request,
        authentication_strength=authentication_strength,
        target_scope=target_scope,
    )
    await uow.owner_controls.add_authorization(authorization)
    if (
        binding.exit_profile_id != target.profile.exit_profile_id
        or binding.exit_profile_semantic_hash != target.profile.semantic_hash()
    ):
        raise OwnerControlBlocked("exit_profile_hash_drift")
    try:
        return await uow.exit_profiles.switch_current_binding(
            expected_current=current,
            new_binding=binding,
            owner_authorization_id=authorization.authorization_id,
            reason=request.reason,
            switched_at_ms=request.now_ms,
        )
    except ExitProfileAuthorityConflict as error:
        if str(error) == "EXIT_BINDING_VERSION_CONFLICT":
            raise OwnerControlConflict("exit_binding_version_conflict") from error
        raise OwnerControlBlocked(str(error).lower()) from error


async def retire_exit_profile(
    uow: KernelUnitOfWork,
    *,
    request: ExitProfileRetirementRequest,
    authentication_strength: Literal["totp_step_up"],
) -> ExitProfileRecord:
    if authentication_strength != "totp_step_up":
        raise OwnerControlBlocked("exit_profile_retire_requires_step_up")
    target_scope: dict[str, JsonValue] = {
        "exit_profile_id": request.exit_profile_id,
        "exit_profile_semantic_hash": request.exit_profile_semantic_hash,
    }
    await uow.exit_profiles.acquire_authority_write_lock()
    record = await uow.exit_profiles.get_profile(
        exit_profile_id=request.exit_profile_id,
        semantic_hash=request.exit_profile_semantic_hash,
    )
    if record is None:
        raise OwnerControlBlocked("exit_profile_missing")
    existing = await uow.owner_controls.get_authorization_by_idempotency_key(
        request.idempotency_key
    )
    if existing is not None:
        _require_matching_authorization(
            existing,
            purpose="exit_profile_retire",
            request=request,
            target_scope=target_scope,
        )
        if existing.authentication_strength != "totp_step_up":
            raise OwnerControlBlocked("exit_profile_retire_requires_step_up")
        return record
    if record.profile.exit_profile_version != request.expected_version:
        raise OwnerControlConflict("exit_profile_version_conflict")
    authorization = _authorization(
        purpose="exit_profile_retire",
        request=request,
        authentication_strength=authentication_strength,
        target_scope=target_scope,
    )
    await uow.owner_controls.add_authorization(authorization)
    try:
        return await uow.exit_profiles.retire_profile(
            profile=record.profile,
            retired_at_ms=request.now_ms,
        )
    except ExitProfileAuthorityConflict as error:
        raise OwnerControlBlocked(str(error).lower()) from error


async def preview_flatten_all(
    uow: KernelUnitOfWork,
    *,
    owner_policy_id: str,
    venue_id: str,
    account_id: str,
) -> FlattenPreview:
    policy = await uow.entry_admission.get_owner_policy(owner_policy_id)
    if policy is None:
        raise OwnerControlBlocked("owner_policy_missing")
    ticket_ids = await uow.aggregates.list_active_ticket_ids(
        venue_id=venue_id,
        account_id=account_id,
        limit=policy.max_concurrent_tickets,
    )
    states: dict[str, str] = {}
    first_blocker: str | None = None
    for ticket_id in ticket_ids:
        aggregate = await uow.aggregates.get(ticket_id)
        if aggregate is None:
            states[ticket_id] = "terminal"
            continue
        classification = classify_controlled_exit_status(aggregate.status)
        states[ticket_id] = classification.value
        if (
            classification is ControlledExitClassification.BLOCKED
            and first_blocker is None
        ):
            first_blocker = (
                f"ticket_not_flattenable:{ticket_id}:{aggregate.status.value}"
            )
    digest = _snapshot_digest(
        venue_id=venue_id,
        account_id=account_id,
        policy_version=policy.policy_version,
        global_entry_enabled=policy.new_entry_submit_enabled,
        states=states,
    )
    return FlattenPreview(
        venue_id=venue_id,
        account_id=account_id,
        owner_policy_version=policy.policy_version,
        global_entry_enabled=policy.new_entry_submit_enabled,
        ticket_ids=ticket_ids,
        ticket_states=states,
        snapshot_digest=digest,
        first_blocker=first_blocker,
    )


async def begin_flatten_all(
    uow: KernelUnitOfWork,
    *,
    owner_policy_id: str,
    request: FlattenSubmitRequest,
) -> OwnerControlOperation:
    preview = await preview_flatten_all(
        uow,
        owner_policy_id=owner_policy_id,
        venue_id=request.venue_id,
        account_id=request.account_id,
    )
    if preview.snapshot_digest != request.snapshot_digest:
        raise OwnerControlConflict("flatten_snapshot_conflict")
    existing_auth = await uow.owner_controls.get_authorization_by_idempotency_key(
        request.idempotency_key
    )
    if existing_auth is not None:
        _require_matching_authorization(
            existing_auth,
            purpose="owner_flatten_all",
            request=request,
            target_scope={
                "runtime_profile_id": request.runtime_profile_id,
                "venue_id": request.venue_id,
                "account_id": request.account_id,
                "preview_digest": request.snapshot_digest,
            },
        )
        existing = await uow.owner_controls.get_operation(
            existing_auth.authorization_id
        )
        if existing is None:
            raise OwnerControlConflict("idempotency_operation_missing")
        return existing

    authorization = _authorization(
        purpose="owner_flatten_all",
        request=request,
        authentication_strength="totp_step_up",
        target_scope={
            "runtime_profile_id": request.runtime_profile_id,
            "venue_id": request.venue_id,
            "account_id": request.account_id,
            "preview_digest": request.snapshot_digest,
        },
    )
    await uow.owner_controls.add_authorization(authorization)
    if preview.global_entry_enabled:
        await uow.owner_controls.set_global_entry_enabled(
            owner_policy_id=owner_policy_id,
            expected_version=preview.owner_policy_version,
            enabled=False,
            authorization_id=authorization.authorization_id,
            reason="owner_flatten_all",
            updated_at_ms=request.now_ms,
        )
    operation = OwnerControlOperation(
        authorization_id=authorization.authorization_id,
        state=ControlOperationState.VALIDATING,
        version=1,
        runtime_profile_id="account-wide",
        venue_id=request.venue_id,
        account_id=request.account_id,
        target_ticket_ids=(),
        snapshot_digest=request.snapshot_digest,
        created_at_ms=request.now_ms,
        updated_at_ms=request.now_ms,
    )
    await uow.owner_controls.add_operation(operation)
    return operation


async def freeze_flatten_targets(
    uow: KernelUnitOfWork,
    *,
    owner_policy_id: str,
    authorization_id: str,
    now_ms: int,
) -> OwnerControlOperation:
    operation = await uow.owner_controls.get_operation(
        authorization_id,
        for_update=True,
    )
    if operation is None:
        raise OwnerControlConflict("flatten_operation_missing")
    if operation.state is not ControlOperationState.VALIDATING:
        return operation
    preview = await preview_flatten_all(
        uow,
        owner_policy_id=owner_policy_id,
        venue_id=operation.venue_id,
        account_id=operation.account_id,
    )
    if preview.first_blocker is not None:
        target_state = ControlOperationState.BLOCKED
        blocker = preview.first_blocker
    elif not preview.ticket_ids:
        target_state = ControlOperationState.COMPLETED
        blocker = None
    else:
        target_state = ControlOperationState.PENDING
        blocker = None
    updated = operation.model_copy(
        update={
            "state": advance_control_operation(operation.state, target_state),
            "version": operation.version + 1,
            "target_ticket_ids": preview.ticket_ids,
            "snapshot_digest": preview.snapshot_digest,
            "first_blocker": blocker,
            "updated_at_ms": now_ms,
        }
    )
    await uow.owner_controls.save_operation(
        updated,
        event_payload={"target_ticket_ids": list(preview.ticket_ids)},
    )
    return updated


async def consume_pending_flatten(
    uow: KernelUnitOfWork,
    *,
    worker_id: str,
    now_ms: int,
    lease_until_ms: int,
) -> OwnerControlOperation | None:
    operation = await uow.owner_controls.get_actionable_operation(
        now_ms=now_ms,
        for_update=True,
    )
    if operation is None:
        return None
    classifications: dict[str, ControlledExitClassification] = {}
    for ticket_id in operation.target_ticket_ids:
        aggregate = await uow.aggregates.get_for_update(ticket_id)
        classifications[ticket_id] = (
            ControlledExitClassification.TERMINAL
            if aggregate is None
            else classify_controlled_exit_status(aggregate.status)
        )
    blocked = tuple(
        ticket_id
        for ticket_id, classification in classifications.items()
        if classification is ControlledExitClassification.BLOCKED
    )
    if blocked:
        target_state = ControlOperationState.BLOCKED
        blocker = f"ticket_not_flattenable:{blocked[0]}"
    else:
        for ticket_id, classification in classifications.items():
            if classification is ControlledExitClassification.ELIGIBLE:
                await request_exit(
                    uow,
                    ExitTicketRequest(
                        ticket_id=ticket_id,
                        reason=f"owner_flatten_all:{operation.authorization_id}",
                        requested_at_ms=now_ms,
                    ),
                )
        target_state = ControlOperationState.EXITS_REQUESTED
        blocker = None
    claimed = operation.model_copy(
        update={
            "state": ControlOperationState.CLAIMED,
            "version": operation.version + 1,
            "claimed_by": worker_id,
            "lease_until_ms": lease_until_ms,
            "updated_at_ms": now_ms,
        }
    )
    await uow.owner_controls.save_operation(
        claimed,
        event_payload={"worker_id": worker_id},
    )
    completed = claimed.model_copy(
        update={
            "state": advance_control_operation(claimed.state, target_state),
            "version": claimed.version + 1,
            "first_blocker": blocker,
            "lease_until_ms": None,
            "updated_at_ms": now_ms,
        }
    )
    await uow.owner_controls.save_operation(
        completed,
        event_payload={"target_ticket_ids": list(operation.target_ticket_ids)},
    )
    return completed


async def consume_pending_flatten_once(
    uow_factory: UnitOfWorkFactory,
    *,
    worker_id: str,
    now_ms: int,
    lease_until_ms: int,
) -> OwnerControlOperation | None:
    async with uow_factory() as uow:
        if getattr(uow, "owner_controls", None) is None:
            return None
        return await consume_pending_flatten(
            uow,
            worker_id=worker_id,
            now_ms=now_ms,
            lease_until_ms=lease_until_ms,
        )


async def advance_flatten_operation_once(
    uow_factory: UnitOfWorkFactory,
    *,
    now_ms: int,
) -> OwnerControlOperation | None:
    """Advance one durable flatten projection step from bounded Ticket facts."""

    async with uow_factory() as uow:
        if getattr(uow, "owner_controls", None) is None:
            return None
        operation = await uow.owner_controls.get_progressable_operation(for_update=True)
        if operation is None:
            return None
        aggregates = []
        for ticket_id in operation.target_ticket_ids:
            aggregate = await uow.aggregates.get(ticket_id)
            if aggregate is None:
                if operation.state is ControlOperationState.NEEDS_INTERVENTION:
                    return operation
                return await _save_operation_progress(
                    uow,
                    operation,
                    ControlOperationState.NEEDS_INTERVENTION,
                    now_ms=now_ms,
                    blocker=f"ticket_missing:{ticket_id}",
                )
            incident = await uow.incidents.get_open_for_ticket(ticket_id)
            if incident is not None:
                if operation.state is ControlOperationState.NEEDS_INTERVENTION:
                    return operation
                return await _save_operation_progress(
                    uow,
                    operation,
                    ControlOperationState.NEEDS_INTERVENTION,
                    now_ms=now_ms,
                    blocker=f"ticket_incident:{ticket_id}:{incident.incident_kind}",
                )
            aggregates.append(aggregate)

        statuses = {aggregate.status for aggregate in aggregates}
        target: ControlOperationState | None = None
        if operation.state is ControlOperationState.EXITS_REQUESTED:
            target = (
                ControlOperationState.RECONCILIATION_PENDING
                if statuses
                <= {
                    AggregateStatus.SETTLEMENT_PENDING,
                    AggregateStatus.REVIEW_PENDING,
                    AggregateStatus.TERMINAL,
                }
                else ControlOperationState.EXIT_IN_PROGRESS
            )
        elif operation.state is ControlOperationState.EXIT_IN_PROGRESS:
            if statuses <= {
                AggregateStatus.SETTLEMENT_PENDING,
                AggregateStatus.REVIEW_PENDING,
                AggregateStatus.TERMINAL,
            }:
                target = ControlOperationState.RECONCILIATION_PENDING
        elif operation.state is ControlOperationState.RECONCILIATION_PENDING:
            if statuses <= {
                AggregateStatus.SETTLEMENT_PENDING,
                AggregateStatus.REVIEW_PENDING,
                AggregateStatus.TERMINAL,
            }:
                target = ControlOperationState.SETTLEMENT_PENDING
        elif operation.state is ControlOperationState.SETTLEMENT_PENDING:
            if statuses <= {
                AggregateStatus.REVIEW_PENDING,
                AggregateStatus.TERMINAL,
            }:
                target = ControlOperationState.REVIEW_PENDING
        elif operation.state in {
            ControlOperationState.REVIEW_PENDING,
            ControlOperationState.NEEDS_INTERVENTION,
        }:
            ready = statuses == {AggregateStatus.TERMINAL} or not statuses
            for ticket_id in operation.target_ticket_ids:
                budget = await uow.budgets.get_for_ticket(ticket_id)
                review = await uow.reviews.get_for_ticket(ticket_id)
                ready = bool(
                    ready
                    and budget is not None
                    and budget.status == "released"
                    and review is not None
                )
            if ready:
                target = ControlOperationState.COMPLETED
        if target is None:
            return operation
        return await _save_operation_progress(
            uow,
            operation,
            target,
            now_ms=now_ms,
            blocker=None,
        )


async def _save_operation_progress(
    uow: KernelUnitOfWork,
    operation: OwnerControlOperation,
    target: ControlOperationState,
    *,
    now_ms: int,
    blocker: str | None,
) -> OwnerControlOperation:
    updated = operation.model_copy(
        update={
            "state": advance_control_operation(operation.state, target),
            "version": operation.version + 1,
            "first_blocker": blocker,
            "updated_at_ms": now_ms,
        }
    )
    await uow.owner_controls.save_operation(
        updated,
        event_payload={"target_ticket_ids": list(operation.target_ticket_ids)},
    )
    return updated


def strategy_entry_is_enabled(control: StrategyEntryControl | None) -> bool:
    """Fail closed unless one explicit enabled StrategyGroup authority exists."""

    return control is not None and control.entry_state is StrategyEntryState.ENABLED


def _authorization(
    *,
    purpose: Literal[
        "strategy_pause",
        "strategy_resume",
        "entry_pause",
        "entry_resume",
        "owner_flatten_all",
        "selection_mode_change",
        "exit_profile_bind",
        "exit_profile_retire",
    ],
    request: ControlMutationRequest,
    authentication_strength: Literal["session", "totp_step_up"],
    target_scope: dict[str, JsonValue],
) -> OwnerAuthorization:
    digest = _authorization_digest(
        purpose=purpose,
        request=request,
        target_scope=target_scope,
    )
    return OwnerAuthorization(
        authorization_id=f"owner-authorization:{uuid4().hex}",
        purpose=purpose,
        owner_identity=request.owner_identity,
        authentication_strength=authentication_strength,
        request_digest=digest,
        target_scope=target_scope,
        idempotency_key=request.idempotency_key,
        authorized_at_ms=request.now_ms,
    )


def _authorization_digest(
    *,
    purpose: Literal[
        "strategy_pause",
        "strategy_resume",
        "entry_pause",
        "entry_resume",
        "owner_flatten_all",
        "selection_mode_change",
        "exit_profile_bind",
        "exit_profile_retire",
    ],
    request: ControlMutationRequest,
    target_scope: dict[str, JsonValue],
) -> str:
    canonical_request = {
        "purpose": purpose,
        "expected_version": request.expected_version,
        "reason": request.reason,
        "idempotency_key": request.idempotency_key,
        "target_scope": target_scope,
    }
    return (
        "sha256:"
        + sha256(
            json.dumps(
                canonical_request, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
    )


def _require_matching_authorization(
    existing: OwnerAuthorization,
    *,
    purpose: Literal[
        "strategy_pause",
        "strategy_resume",
        "entry_pause",
        "entry_resume",
        "owner_flatten_all",
        "selection_mode_change",
        "exit_profile_bind",
        "exit_profile_retire",
    ],
    request: ControlMutationRequest,
    target_scope: dict[str, JsonValue],
) -> None:
    if (
        existing.purpose != purpose
        or existing.owner_identity != request.owner_identity
        or existing.target_scope != target_scope
        or existing.request_digest
        != _authorization_digest(
            purpose=purpose,
            request=request,
            target_scope=target_scope,
        )
    ):
        raise OwnerControlConflict("idempotency_key_conflict")


def _snapshot_digest(
    *,
    venue_id: str,
    account_id: str,
    policy_version: int,
    global_entry_enabled: bool,
    states: dict[str, str],
) -> str:
    payload = {
        "scope": "account-wide",
        "venue_id": venue_id,
        "account_id": account_id,
        "policy_version": policy_version,
        "global_entry_enabled": global_entry_enabled,
        "tickets": sorted(states.items()),
    }
    return (
        "sha256:"
        + sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
