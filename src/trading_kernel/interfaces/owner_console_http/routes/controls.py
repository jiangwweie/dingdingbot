"""Authenticated Owner control-plane HTTP routes."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    ExitProfileBindingMutationRequest,
    ExitProfileRetirementRequest,
    FlattenPreview,
    FlattenSubmitRequest,
    OwnerControlBlocked,
    OwnerControlConflict,
    begin_flatten_all,
    freeze_flatten_targets,
    preview_flatten_all,
    retire_exit_profile,
    set_global_entry_state,
    set_strategy_entry_state,
    stage_dynamic_selection_mode,
    switch_event_exit_profile,
)
from src.trading_kernel.application.ports import RuntimeProfileSnapshot
from src.trading_kernel.domain.exit_policy import (
    CurrentEventExitBinding,
    ExitProfileRecord,
)
from src.trading_kernel.domain.owner_control import (
    OwnerControlOperation,
    StrategyEntryControl,
    StrategyEntryState,
)
from src.trading_kernel.domain.selection_authority import SelectionControl
from src.trading_kernel.infrastructure.pg_exit_profile_repository import (
    PostgresExitProfileAuthorityRepository,
)
from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    owner_read_transaction,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.owner_console_http.auth import InvalidCredentials
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    get_auth_service,
    get_clock_ms,
    get_control_engine,
    get_read_engine,
    get_settings,
)
from src.trading_kernel.interfaces.readonly_api import (
    ExitProfileAuthorityReadonlyRequest,
    ExitProfileAuthorityReadonlyView,
    get_exit_profile_authority_view,
)

router = APIRouter(prefix="/api/owner/v1", tags=["owner-controls"])


class ControlWriteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=160)
    totp_code: str | None = Field(default=None, min_length=6, max_length=8)


class FlattenBody(ControlWriteBody):
    snapshot_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    confirmation_text: Literal["确认平仓全部持仓"]


class DynamicSelectionActivationBody(ControlWriteBody):
    effective_session_start_ms: int = Field(gt=0)


class ExitProfileBindingBody(ControlWriteBody):
    expected_binding_id: str = Field(min_length=1, max_length=240)
    target_exit_profile_id: str = Field(min_length=1, max_length=240)
    target_exit_profile_semantic_hash: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$"
    )


class ExitProfileRetirementBody(ControlWriteBody):
    exit_profile_semantic_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class EmptyControlBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GlobalEntryView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    configured_state: Literal["enabled", "paused"]
    effective_state: Literal["enabled", "paused"]
    policy_version: int
    active_ticket_count: int
    first_blocker: str | None = None


class AccountCapacityView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_concurrent_tickets: int
    active_ticket_count: int
    remaining_ticket_slots: int
    gross_stop_risk: Decimal
    gross_stop_risk_limit: Decimal | None
    max_gross_stop_risk_fraction: Decimal
    long_stop_risk: Decimal
    short_stop_risk: Decimal
    directional_stop_risk_limit: Decimal | None
    directional_stop_risk_limit_fraction: Decimal
    reserved_margin: Decimal
    gross_initial_margin_limit: Decimal | None
    max_gross_initial_margin_utilization: Decimal
    wallet_balance_basis: Decimal | None
    margin_balance_basis: Decimal | None
    family_active_counts: dict[str, int]
    family_limits: dict[str, int]
    source: Literal["current_projection", "no_active_exposure"]

    @field_serializer(
        "gross_stop_risk",
        "gross_stop_risk_limit",
        "max_gross_stop_risk_fraction",
        "long_stop_risk",
        "short_stop_risk",
        "directional_stop_risk_limit",
        "directional_stop_risk_limit_fraction",
        "reserved_margin",
        "gross_initial_margin_limit",
        "max_gross_initial_margin_utilization",
        "wallet_balance_basis",
        "margin_balance_basis",
    )
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class RuntimeEntryAuthorityView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_commands_enabled: bool
    effective_status: Literal["ready", "fenced"]
    runtime_profile_ids: tuple[str, ...]
    first_blocker: str | None = None


class StrategyControlView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    entry_state: StrategyEntryState
    control_version: int
    last_event_id: str
    reason: str
    updated_at_ms: int
    configured_state: StrategyEntryState
    effective_state: Literal["enabled", "paused", "paused_by_global"]


class DynamicSelectionControlView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    selection_spec_id: str
    selection_mode: Literal["static_baseline", "dynamic_selection"]
    pending_selection_mode: Literal["dynamic_selection"] | None
    pending_effective_session_start_ms: int | None
    control_version: int


class ControlEventView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    authorization_id: str
    version: int
    state: str
    first_blocker: str | None = None
    created_at_ms: int


class ControlsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_at_ms: int
    global_entry: GlobalEntryView
    account_capacity: AccountCapacityView
    runtime_entry_authority: RuntimeEntryAuthorityView
    dynamic_selection: DynamicSelectionControlView
    strategies: tuple[StrategyControlView, ...]
    current_operation: OwnerControlOperation | None
    recent_operations: tuple[OwnerControlOperation, ...]
    events: tuple[ControlEventView, ...]


class GlobalMutationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    configured_state: Literal["enabled", "paused"]
    effective_state: Literal["enabled", "paused"]
    version: int
    updated_at_ms: int


class ControlEventsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: tuple[ControlEventView, ...]


class NotFoundResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["not_found"] = "not_found"


@router.get("/controls")
async def read_controls(request: Request) -> ControlsResponse:
    settings = get_settings(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        policy = await uow.entry_admission.get_owner_policy(settings.owner_policy_id)
        if policy is None:
            raise RuntimeError("Owner Policy is unavailable")
        dynamic_selection = await uow.instrument_selection.get_selection_control(
            "SOR-001"
        )
        if dynamic_selection is None:
            raise RuntimeError("SOR Dynamic Selection Control is unavailable")
        strategies = await uow.owner_controls.list_strategy_controls()
        ticket_ids = await uow.aggregates.list_active_ticket_ids(
            venue_id=settings.venue_id,
            account_id=settings.account_id,
            limit=policy.max_concurrent_tickets,
        )
        operation = await uow.owner_controls.get_latest_nonterminal_operation()
        recent_operations = await uow.owner_controls.list_recent_operations(limit=20)
        events = await uow.owner_controls.list_recent_events(limit=20)
        exposure = await uow.entry_admission.get_account_exposure(
            settings.venue_id,
            settings.account_id,
        )
        long_risk = await uow.entry_admission.sum_active_directional_stop_risk(
            venue_id=settings.venue_id,
            account_id=settings.account_id,
            position_side="long",
        )
        short_risk = await uow.entry_admission.sum_active_directional_stop_risk(
            venue_id=settings.venue_id,
            account_id=settings.account_id,
            position_side="short",
        )
        family_names = (
            "long_continuation",
            "opening_range",
            "rally_failure_short",
        )
        family_counts = {
            family: await uow.entry_admission.count_active_family_tickets(
                venue_id=settings.venue_id,
                account_id=settings.account_id,
                exposure_family=family,
            )
            for family in family_names
        }
        capability = await uow.signals.get_runtime_capability("exchange_commands")
        runtime_profile_ids = tuple(
            sorted(
                {
                    item.runtime_profile_id
                    for item in (policy.scope.event_runtime_profiles if policy.scope else ())
                }
            )
        )
        runtime_profiles: tuple[RuntimeProfileSnapshot | None, ...] = tuple(
            [
                await uow.signals.get_runtime_profile(runtime_profile_id)
                for runtime_profile_id in runtime_profile_ids
            ]
        )
        latest_claim = await uow.capacity_claims.get_latest_for_account(
            venue_id=settings.venue_id,
            account_id=settings.account_id,
        )
        wallet_basis = (
            None if latest_claim is None else latest_claim.total_wallet_balance_at_claim
        )
        margin_basis = (
            None if latest_claim is None else latest_claim.total_margin_balance_at_claim
        )
        raw_entry_blocker = await uow.owner_controls.get_global_entry_resume_blocker(
            owner_policy_id=settings.owner_policy_id,
        )
    global_state = "enabled" if policy.new_entry_submit_enabled else "paused"
    exposure_ticket_count = 0 if exposure is None else exposure.active_ticket_count
    gross_stop_risk = Decimal(0) if exposure is None else exposure.gross_risk_at_stop
    reserved_margin = (
        Decimal(0) if exposure is None else exposure.current_reserved_margin
    )
    runtime_profiles_ready = bool(runtime_profile_ids) and all(
        profile is not None
        and profile.status == "active"
        and profile.position_mode == "independent_sides"
        for profile in runtime_profiles
    )
    capability_ready = capability is not None and capability.enabled
    entry_blocker = (
        None
        if policy.new_entry_submit_enabled
        and raw_entry_blocker == "exchange_command_unresolved"
        else raw_entry_blocker
    )
    return ControlsResponse.model_validate(
        {
            "generated_at_ms": get_clock_ms(request),
            "global_entry": {
                "configured_state": global_state,
                "effective_state": global_state,
                "policy_version": policy.policy_version,
                "active_ticket_count": len(ticket_ids),
                "first_blocker": entry_blocker,
            },
            "account_capacity": {
                "max_concurrent_tickets": policy.max_concurrent_tickets,
                "active_ticket_count": exposure_ticket_count,
                "remaining_ticket_slots": max(
                    policy.max_concurrent_tickets - exposure_ticket_count,
                    0,
                ),
                "gross_stop_risk": gross_stop_risk,
                "gross_stop_risk_limit": (
                    None
                    if wallet_basis is None
                    else wallet_basis * policy.max_gross_stop_risk_fraction
                ),
                "max_gross_stop_risk_fraction": (
                    policy.max_gross_stop_risk_fraction
                ),
                "long_stop_risk": long_risk,
                "short_stop_risk": short_risk,
                "directional_stop_risk_limit": (
                    None
                    if wallet_basis is None
                    else wallet_basis * policy.directional_stop_risk_limit_fraction
                ),
                "directional_stop_risk_limit_fraction": (
                    policy.directional_stop_risk_limit_fraction
                ),
                "reserved_margin": reserved_margin,
                "gross_initial_margin_limit": (
                    None
                    if margin_basis is None
                    else margin_basis * policy.max_gross_initial_margin_utilization
                ),
                "max_gross_initial_margin_utilization": (
                    policy.max_gross_initial_margin_utilization
                ),
                "wallet_balance_basis": wallet_basis,
                "margin_balance_basis": margin_basis,
                "family_active_counts": family_counts,
                "family_limits": policy.family_ticket_limits.model_dump(),
                "source": (
                    "current_projection"
                    if exposure is not None
                    else "no_active_exposure"
                ),
            },
            "runtime_entry_authority": {
                "exchange_commands_enabled": capability_ready,
                "effective_status": (
                    "ready"
                    if entry_blocker is None
                    and runtime_profiles_ready
                    and capability_ready
                    else "fenced"
                ),
                "runtime_profile_ids": runtime_profile_ids,
                "first_blocker": entry_blocker,
            },
            "dynamic_selection": {
                "strategy_group_id": dynamic_selection.strategy_group_id,
                "selection_spec_id": dynamic_selection.selection_spec_id,
                "selection_mode": dynamic_selection.selection_mode.value,
                "pending_selection_mode": (
                    None
                    if dynamic_selection.pending_selection_mode is None
                    else dynamic_selection.pending_selection_mode.value
                ),
                "pending_effective_session_start_ms": (
                    dynamic_selection.pending_effective_session_start_ms
                ),
                "control_version": dynamic_selection.control_version,
            },
            "strategies": [
                {
                    **control.model_dump(mode="json"),
                    "configured_state": control.entry_state.value,
                    "effective_state": (
                        "paused_by_global"
                        if not policy.new_entry_submit_enabled
                        else control.entry_state.value
                    ),
                }
                for control in strategies
            ],
            "current_operation": (
                None if operation is None else operation.model_dump(mode="json")
            ),
            "recent_operations": [
                item.model_dump(mode="json") for item in recent_operations
            ],
            "events": list(events),
        }
    )


@router.post("/controls/strategies/{strategy_group_id}/pause")
async def pause_strategy(
    strategy_group_id: str,
    body: ControlWriteBody,
    request: Request,
) -> StrategyEntryControl:
    _validate_write_request(request)
    return await _set_strategy(strategy_group_id, StrategyEntryState.PAUSED, body, request)


@router.post("/controls/strategies/{strategy_group_id}/resume")
async def resume_strategy(
    strategy_group_id: str,
    body: ControlWriteBody,
    request: Request,
) -> StrategyEntryControl:
    _validate_write_request(request)
    await _require_step_up(body, request)
    return await _set_strategy(strategy_group_id, StrategyEntryState.ENABLED, body, request)


@router.post(
    "/controls/strategies/{strategy_group_id}/selection/dynamic/activate"
)
async def activate_dynamic_selection(
    strategy_group_id: str,
    body: DynamicSelectionActivationBody,
    request: Request,
) -> SelectionControl:
    _validate_write_request(request)
    settings = get_settings(request)
    now_ms = get_clock_ms(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        current = await uow.instrument_selection.get_selection_control(
            strategy_group_id
        )
        if current is None:
            raise OwnerControlBlocked("selection_control_missing")
        if current.control_version != body.expected_version:
            raise OwnerControlConflict("selection_control_version_conflict")
    await _require_step_up(body, request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        return await stage_dynamic_selection_mode(
            uow,
            strategy_group_id=strategy_group_id,
            effective_session_start_ms=body.effective_session_start_ms,
            request=_mutation(body, settings.auth.username, now_ms),
            authentication_strength="totp_step_up",
        )


@router.get("/controls/exit-profiles")
async def read_exit_profile_authority(
    request: Request,
    event_spec_id: str | None = None,
    event_limit: int = Query(default=20, ge=1, le=50),
) -> ExitProfileAuthorityReadonlyView:
    async with owner_read_transaction(get_read_engine(request)) as connection:
        return await get_exit_profile_authority_view(
            PostgresExitProfileAuthorityRepository(connection),
            ExitProfileAuthorityReadonlyRequest(
                event_spec_id=event_spec_id,
                event_limit=event_limit,
            ),
        )


@router.post(
    "/controls/strategies/{strategy_group_id}/events/{event_spec_id}/exit-profile"
)
async def bind_event_exit_profile(
    strategy_group_id: str,
    event_spec_id: str,
    body: ExitProfileBindingBody,
    request: Request,
) -> CurrentEventExitBinding:
    _validate_write_request(request)
    await _require_step_up(body, request)
    settings = get_settings(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        return await switch_event_exit_profile(
            uow,
            strategy_group_id=strategy_group_id,
            event_spec_id=event_spec_id,
            request=ExitProfileBindingMutationRequest(
                expected_version=body.expected_version,
                expected_binding_id=body.expected_binding_id,
                target_exit_profile_id=body.target_exit_profile_id,
                target_exit_profile_semantic_hash=(
                    body.target_exit_profile_semantic_hash
                ),
                reason=body.reason,
                idempotency_key=body.idempotency_key,
                owner_identity=settings.auth.username,
                now_ms=get_clock_ms(request),
            ),
            authentication_strength="totp_step_up",
        )


@router.post("/controls/exit-profiles/{exit_profile_id}/retire")
async def retire_profile(
    exit_profile_id: str,
    body: ExitProfileRetirementBody,
    request: Request,
) -> ExitProfileRecord:
    _validate_write_request(request)
    await _require_step_up(body, request)
    settings = get_settings(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        return await retire_exit_profile(
            uow,
            request=ExitProfileRetirementRequest(
                expected_version=body.expected_version,
                exit_profile_id=exit_profile_id,
                exit_profile_semantic_hash=body.exit_profile_semantic_hash,
                reason=body.reason,
                idempotency_key=body.idempotency_key,
                owner_identity=settings.auth.username,
                now_ms=get_clock_ms(request),
            ),
            authentication_strength="totp_step_up",
        )


@router.post("/controls/entry/pause")
async def pause_global_entry(
    body: ControlWriteBody,
    request: Request,
) -> GlobalMutationResponse:
    _validate_write_request(request)
    return await _set_global(False, body, request)


@router.post("/controls/entry/resume")
async def resume_global_entry(
    body: ControlWriteBody,
    request: Request,
) -> GlobalMutationResponse:
    _validate_write_request(request)
    await _require_step_up(body, request)
    return await _set_global(True, body, request)


@router.post("/controls/exposure/flatten-all/preview")
async def flatten_preview(body: EmptyControlBody, request: Request) -> FlattenPreview:
    _validate_write_request(request)
    settings = get_settings(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        preview = await preview_flatten_all(
            uow,
            owner_policy_id=settings.owner_policy_id,
            venue_id=settings.venue_id,
            account_id=settings.account_id,
        )
    return preview


@router.post("/controls/exposure/flatten-all", status_code=201)
async def flatten_submit(
    body: FlattenBody,
    request: Request,
) -> OwnerControlOperation:
    _validate_write_request(request)
    await _require_step_up(body, request)
    settings = get_settings(request)
    now_ms = get_clock_ms(request)
    control_request = FlattenSubmitRequest(
        expected_version=body.expected_version,
        reason=body.reason,
        idempotency_key=body.idempotency_key,
        owner_identity=settings.auth.username,
        now_ms=now_ms,
        runtime_profile_id="account-wide",
        venue_id=settings.venue_id,
        account_id=settings.account_id,
        snapshot_digest=body.snapshot_digest,
    )
    engine = get_control_engine(request)
    async with PostgresKernelUnitOfWork(engine) as uow:
        operation = await begin_flatten_all(
            uow,
            owner_policy_id=settings.owner_policy_id,
            request=control_request,
        )
    async with PostgresKernelUnitOfWork(engine) as uow:
        operation = await freeze_flatten_targets(
            uow,
            owner_policy_id=settings.owner_policy_id,
            authorization_id=operation.authorization_id,
            now_ms=now_ms,
        )
    return operation


@router.get("/control-operations/{authorization_id}")
async def read_control_operation(
    authorization_id: str,
    request: Request,
) -> OwnerControlOperation | NotFoundResponse:
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        operation = await uow.owner_controls.get_operation(authorization_id)
    if operation is None:
        return NotFoundResponse()
    return operation


@router.get("/control-events")
async def read_control_events(
    request: Request,
    limit: int = 20,
) -> ControlEventsResponse:
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        events = await uow.owner_controls.list_recent_events(limit=limit)
    return ControlEventsResponse.model_validate({"items": list(events)})


async def _set_strategy(
    strategy_group_id: str,
    target: StrategyEntryState,
    body: ControlWriteBody,
    request: Request,
) -> StrategyEntryControl:
    settings = get_settings(request)
    now_ms = get_clock_ms(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        control = await set_strategy_entry_state(
            uow,
            strategy_group_id=strategy_group_id,
            target_state=target,
            request=_mutation(body, settings.auth.username, now_ms),
            authentication_strength=(
                "session" if target is StrategyEntryState.PAUSED else "totp_step_up"
            ),
        )
    return control


async def _set_global(
    enabled: bool,
    body: ControlWriteBody,
    request: Request,
) -> GlobalMutationResponse:
    settings = get_settings(request)
    now_ms = get_clock_ms(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        policy = await set_global_entry_state(
            uow,
            owner_policy_id=settings.owner_policy_id,
            enabled=enabled,
            request=_mutation(body, settings.auth.username, now_ms),
            authentication_strength="totp_step_up" if enabled else "session",
        )
    return GlobalMutationResponse(
        configured_state="enabled" if enabled else "paused",
        effective_state="enabled" if enabled else "paused",
        version=policy.policy_version,
        updated_at_ms=now_ms,
    )


def _mutation(body: ControlWriteBody, owner_identity: str, now_ms: int) -> ControlMutationRequest:
    return ControlMutationRequest(
        expected_version=body.expected_version,
        reason=body.reason,
        idempotency_key=body.idempotency_key,
        owner_identity=owner_identity,
        now_ms=now_ms,
    )


async def _require_step_up(body: ControlWriteBody, request: Request) -> None:
    if body.totp_code is None:
        raise InvalidCredentials
    await get_auth_service(request).verify_step_up(
        body.totp_code,
        now_ms=get_clock_ms(request),
    )


def _validate_write_request(request: Request) -> None:
    settings = get_settings(request)
    if request.headers.get("origin") != settings.public_origin:
        raise InvalidCredentials
    host = request.headers.get("host", "").split(":", 1)[0]
    if host != settings.public_host:
        raise InvalidCredentials
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if request.method == "POST" and content_type != "application/json":
        raise InvalidCredentials
