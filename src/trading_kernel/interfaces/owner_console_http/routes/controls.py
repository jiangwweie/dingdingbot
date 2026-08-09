"""Authenticated Owner control-plane HTTP routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    FlattenPreview,
    FlattenSubmitRequest,
    begin_flatten_all,
    freeze_flatten_targets,
    preview_flatten_all,
    set_global_entry_state,
    set_strategy_entry_state,
)
from src.trading_kernel.domain.owner_control import (
    OwnerControlOperation,
    StrategyEntryControl,
    StrategyEntryState,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.owner_console_http.auth import InvalidCredentials
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    get_auth_service,
    get_clock_ms,
    get_control_engine,
    get_settings,
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


class EmptyControlBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GlobalEntryView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    configured_state: Literal["enabled", "paused"]
    effective_state: Literal["enabled", "paused"]
    policy_version: int
    active_ticket_count: int
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
    strategies: tuple[StrategyControlView, ...]
    current_operation: OwnerControlOperation | None
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
        strategies = await uow.owner_controls.list_strategy_controls()
        ticket_ids = await uow.aggregates.list_active_ticket_ids(
            runtime_profile_id=settings.runtime_profile_id,
            venue_id=settings.venue_id,
            account_id=settings.account_id,
            limit=policy.max_concurrent_tickets,
        )
        operation = await uow.owner_controls.get_latest_operation()
        events = await uow.owner_controls.list_recent_events(limit=20)
    global_state = "enabled" if policy.new_entry_submit_enabled else "paused"
    return ControlsResponse.model_validate(
        {
            "generated_at_ms": get_clock_ms(request),
            "global_entry": {
                "configured_state": global_state,
                "effective_state": global_state,
                "policy_version": policy.policy_version,
                "active_ticket_count": len(ticket_ids),
                "first_blocker": None,
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
            runtime_profile_id=settings.runtime_profile_id,
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
        runtime_profile_id=settings.runtime_profile_id,
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
            runtime_profile_id=settings.runtime_profile_id,
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
