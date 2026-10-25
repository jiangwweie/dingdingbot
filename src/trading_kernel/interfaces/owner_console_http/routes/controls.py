"""Authenticated Owner control-plane HTTP routes."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

import sqlalchemy as sa
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
    stage_generic_dynamic_selection_mode,
    stage_generic_static_selection_mode,
    stage_orb_dynamic_selection_mode,
    stage_orb_static_selection_mode,
    switch_event_exit_profile,
)
from src.trading_kernel.application.ports import RuntimeProfileSnapshot
from src.trading_kernel.domain.directional_risk import (
    RULE_LIMITS,
    DirectionalChangeRequest,
    DirectionalControl,
)
from src.trading_kernel.domain.exit_policy import (
    CurrentEventExitBinding,
    ExitProfileRecord,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.owner_control import (
    OwnerControlOperation,
    StrategyEntryControl,
    StrategyEntryState,
)
from src.trading_kernel.domain.selection_authority import (
    SelectionControl,
    SelectionMode,
)
from src.trading_kernel.infrastructure.pg_directional_risk_repository import (
    PostgresDirectionalRiskRepository,
)
from src.trading_kernel.infrastructure.pg_exit_profile_repository import (
    PostgresExitProfileAuthorityRepository,
)
from src.trading_kernel.infrastructure.pg_models import capacity_claims
from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    owner_read_transaction,
)
from src.trading_kernel.infrastructure.pg_repositories import (
    PostgresEntryAdmissionRepository,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.owner_console_http.auth import (
    ForbiddenOwnerRequest,
    InvalidCredentials,
    StepUpInvalid,
)
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
    GenericSelectionRuntimeReadonlyRequest,
    GenericSelectionRuntimeReadonlyView,
    SelectionRuntimeReadonlyRequest,
    SelectionRuntimeReadonlyView,
    get_exit_profile_authority_view,
    get_generic_selection_runtime_view,
    get_selection_runtime_view,
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


class DirectionalRiskBody(ControlWriteBody):
    view: Literal["bullish", "neutral", "bearish"]


class DirectionalRiskView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    control: DirectionalControl
    long_limit: Decimal
    short_limit: Decimal
    long_risk_at_stop: Decimal
    short_risk_at_stop: Decimal
    observed_at_ms: int
    review_due: bool
    wallet_balance_at_last_admission: Decimal | None
    balance_captured_at_ms: int | None
    long_over_limit_at_last_balance: bool | None
    short_over_limit_at_last_balance: bool | None


class DirectionalRiskReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    result: DirectionalControl | None
    current: DirectionalControl


@router.get("/controls/directional-risk/requests/{idempotency_key}")
async def get_directional_receipt(
    idempotency_key: str, request: Request
) -> DirectionalRiskReceipt:
    if not idempotency_key.strip() or len(idempotency_key) > 160:
        raise OwnerControlBlocked("directional_idempotency_key_invalid")
    settings = get_settings(request)
    async with owner_read_transaction(get_read_engine(request)) as c:
        repo = PostgresDirectionalRiskRepository(c)
        current = await repo.get(settings.venue_id, settings.account_id)
        if current is None:
            raise OwnerControlBlocked("directional_control_missing")
        result = await repo.request_receipt(
            settings.venue_id, settings.account_id, idempotency_key
        )
    return DirectionalRiskReceipt(result=result, current=current)


@router.get("/controls/directional-risk")
async def get_directional_risk(request: Request) -> DirectionalRiskView:
    settings = get_settings(request)
    now_ms = get_clock_ms(request)
    async with owner_read_transaction(get_read_engine(request)) as connection:
        control = await PostgresDirectionalRiskRepository(connection).get(
            settings.venue_id, settings.account_id
        )
        if control is None:
            raise OwnerControlBlocked("directional_control_missing")
        admission = PostgresEntryAdmissionRepository(connection)
        policy = await admission.get_owner_policy(settings.owner_policy_id)
        if policy is None:
            raise OwnerControlBlocked("owner_policy_missing")
        long_usage = await admission.sum_active_directional_stop_risk(
            venue_id=settings.venue_id,
            account_id=settings.account_id,
            position_side="long",
        )
        short_usage = await admission.sum_active_directional_stop_risk(
            venue_id=settings.venue_id,
            account_id=settings.account_id,
            position_side="short",
        )
        balance = (
            await connection.execute(
                sa.select(
                    capacity_claims.c.total_wallet_balance_at_claim,
                    capacity_claims.c.created_at_ms,
                )
                .where(
                    capacity_claims.c.venue_id == settings.venue_id,
                    capacity_claims.c.account_id == settings.account_id,
                )
                .order_by(capacity_claims.c.created_at_ms.desc())
                .limit(1)
            )
        ).first()
    limits = RULE_LIMITS[control.view]
    long_limit = min(policy.directional_stop_risk_limit_fraction, Decimal(limits[0]))
    short_limit = min(policy.directional_stop_risk_limit_fraction, Decimal(limits[1]))
    return DirectionalRiskView(
        control=control,
        long_limit=min(policy.directional_stop_risk_limit_fraction, Decimal(limits[0])),
        short_limit=min(
            policy.directional_stop_risk_limit_fraction, Decimal(limits[1])
        ),
        long_risk_at_stop=long_usage,
        short_risk_at_stop=short_usage,
        wallet_balance_at_last_admission=None if balance is None else balance[0],
        balance_captured_at_ms=None if balance is None else balance[1],
        long_over_limit_at_last_balance=None
        if balance is None
        else long_usage > balance[0] * long_limit,
        short_over_limit_at_last_balance=None
        if balance is None
        else short_usage > balance[0] * short_limit,
        observed_at_ms=now_ms,
        review_due=control.view != "unset"
        and now_ms - control.effective_at_ms >= 86_400_000,
    )


@router.post("/controls/directional-risk")
async def change_directional_risk(
    body: DirectionalRiskBody, request: Request
) -> DirectionalControl:
    _validate_write_request(request)
    await _require_step_up(body, request)
    settings = get_settings(request)
    try:
        mutation = DirectionalChangeRequest(
            venue_id=settings.venue_id,
            account_id=settings.account_id,
            expected_version=body.expected_version,
            view=body.view,
            owner_identity=settings.auth.username,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
            requested_at_ms=get_clock_ms(request),
        )
        async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
            return await uow.directional_risk.request_change(mutation)
    except ValueError as exc:
        raise OwnerControlConflict(str(exc)) from exc


class DynamicSelectionActivationBody(ControlWriteBody):
    effective_session_start_ms: int = Field(gt=0)


class GenericSelectionActivationBody(ControlWriteBody):
    effective_period_anchor_ms: int = Field(gt=0)


class GenericStaticSelectionActivationBody(GenericSelectionActivationBody):
    rollback_baseline_id: str = Field(min_length=1, max_length=160)
    selection_epoch_id: str = Field(min_length=1, max_length=160)


class GenericSelectionPreviewView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    control: SelectionControl | None
    runtime: GenericSelectionRuntimeReadonlyView
    cadence_hours: int
    next_effective_period_anchor_ms: int
    next_eligibility_not_before_ms: int


class OrbSelectionPreviewView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    strategy_label: Literal["SOR-1H（1h 入场 / 15m 退出）"] = (
        "SOR-1H（1h 入场 / 15m 退出）"
    )
    installed: bool
    control: SelectionControl | None
    runtime: SelectionRuntimeReadonlyView | None
    next_effective_period_anchor_ms: int
    next_prepare_not_before_ms: int
    next_eligibility_not_before_ms: int


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
    max_same_strategy_side: int | None
    strategy_side_active_counts: dict[str,int]
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
    selection_mode: SelectionMode
    pending_selection_mode: SelectionMode | None
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
    dynamic_selection: DynamicSelectionControlView | None
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
    async with PostgresKernelUnitOfWork(get_read_engine(request)) as uow:
        assert uow._connection is not None
        await uow._connection.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        policy = await uow.entry_admission.get_owner_policy(settings.owner_policy_id)
        if policy is None:
            raise RuntimeError("Owner Policy is unavailable")
        dynamic_selection = await uow.instrument_selection.get_selection_control(
            "SOR-001"
        )
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
        capacity_sides: tuple[Literal["long","short"], ...] = ("long","short")
        strategy_side_counts = {
            f"{control.strategy_group_id}:{side}": await uow.entry_admission.count_active_strategy_side_tickets(
                venue_id=settings.venue_id,account_id=settings.account_id,
                strategy_group_id=control.strategy_group_id,position_side=side,
            )
            for control in strategies for side in capacity_sides
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
                "max_same_strategy_side":policy.max_same_strategy_side,
                "strategy_side_active_counts":strategy_side_counts,
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
            "dynamic_selection": None if dynamic_selection is None else {
                "strategy_group_id": dynamic_selection.strategy_group_id,
                "selection_spec_id": dynamic_selection.selection_spec_id,
                "selection_mode": dynamic_selection.selection_mode.value,
                "pending_selection_mode": (
                    None
                    if dynamic_selection.pending_selection_mode is None
                    else dynamic_selection.pending_selection_mode.value
                ),
                "pending_effective_session_start_ms": (
                    dynamic_selection.pending_effective_period_anchor_ms
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
    if strategy_group_id=="SOR-001":
        raise OwnerControlBlocked("strategy_retired")
    await _require_step_up(body, request)
    return await _set_strategy(strategy_group_id, StrategyEntryState.ENABLED, body, request)


@router.post(
    "/controls/strategies/{strategy_group_id}/selection/dynamic/activate"
)
async def activate_dynamic_selection(
    strategy_group_id: str,
    body: DynamicSelectionActivationBody | GenericSelectionActivationBody,
    request: Request,
) -> SelectionControl:
    _validate_write_request(request)
    if strategy_group_id=="SOR-001":
        raise OwnerControlBlocked("strategy_retired")
    settings = get_settings(request)
    now_ms = get_clock_ms(request)
    if strategy_group_id in {"CPM-RO-001","MPG-001","MI-001","BRF2-001"}:
        if not isinstance(body,GenericSelectionActivationBody):
            raise OwnerControlBlocked("generic_selection_requires_period_anchor")
        async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
            await uow.owner_controls.get_strategy_control(strategy_group_id,for_update=True)
            existing=await uow.owner_controls.get_authorization_by_idempotency_key(body.idempotency_key)
            if existing is not None:
                # Only the original application boundary can validate and
                # replay an already step-up-authorized immutable intent.
                return await stage_generic_dynamic_selection_mode(uow,strategy_group_id=strategy_group_id,
                    effective_period_anchor_ms=body.effective_period_anchor_ms,
                    request=_mutation(body,settings.auth.username,now_ms),authentication_strength="totp_step_up")
            current=await uow.instrument_selection.get_selection_control(strategy_group_id,for_update=True)
            if current is None:
                raise OwnerControlBlocked("generic_selection_control_missing")
            if current.control_version!=body.expected_version:
                raise OwnerControlConflict("selection_control_version_conflict")
            # Local cryptographic verification has no network I/O. Keep this
            # rare Owner mutation under its existing transaction lock, so a
            # duplicate cannot consume proof before the first intent commits.
            await _require_step_up(body,request)
            return await stage_generic_dynamic_selection_mode(uow,strategy_group_id=strategy_group_id,
                effective_period_anchor_ms=body.effective_period_anchor_ms,
                request=_mutation(body,settings.auth.username,now_ms),authentication_strength="totp_step_up")
    if not isinstance(body,DynamicSelectionActivationBody):
        raise OwnerControlBlocked("sor_selection_requires_session_start")
    if strategy_group_id == 'SOR-1H-001':
        async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
            await uow.owner_controls.get_strategy_control(strategy_group_id,for_update=True)
            existing=await uow.owner_controls.get_authorization_by_idempotency_key(body.idempotency_key)
            if existing is None:
                control=await uow.instrument_selection.get_selection_control(strategy_group_id,for_update=True)
                if control is None:
                    raise OwnerControlBlocked('selection_control_missing')
                if control.control_version!=body.expected_version:
                    raise OwnerControlConflict('selection_control_version_conflict')
                await _require_step_up(body,request)
            return await stage_orb_dynamic_selection_mode(uow,effective_session_start_ms=body.effective_session_start_ms,
                request=_mutation(body,settings.auth.username,now_ms),authentication_strength='totp_step_up')
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


@router.get("/controls/strategies/{strategy_group_id}/selection")
async def preview_generic_selection(strategy_group_id: str,request: Request) -> GenericSelectionPreviewView | OrbSelectionPreviewView:
    if strategy_group_id=='SOR-1H-001':
        now=get_clock_ms(request)
        session=now//86_400_000*86_400_000
        next_session=session if now<session+3_600_000 else session+86_400_000
        async with PostgresKernelUnitOfWork(get_read_engine(request)) as uow:
            assert uow._connection is not None
            await uow._connection.execute(sa.text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            try:
                await uow.instrument_selection.get_orb_spec('SOR_1H_OR_ATR_DYNAMIC_V1')
            except LookupError:
                orb_runtime=None
            else:
                orb_runtime=await get_selection_runtime_view(uow,SelectionRuntimeReadonlyRequest(strategy_group_id=strategy_group_id,
                    selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1',session_start_ms=session))
        return OrbSelectionPreviewView(installed=orb_runtime is not None,control=None if orb_runtime is None else orb_runtime.selection_control,
            runtime=orb_runtime,next_effective_period_anchor_ms=next_session,next_prepare_not_before_ms=next_session+3_600_000,
            next_eligibility_not_before_ms=next_session+7_200_000)
    try:
        spec=generic_selection_spec(strategy_group_id)
    except ValueError as exc:
        raise OwnerControlBlocked("generic_strategy_not_supported") from exc
    now=get_clock_ms(request)
    cadence=spec.cadence_hours*3_600_000
    anchor=(now//cadence+1)*cadence
    async with PostgresKernelUnitOfWork(get_read_engine(request)) as uow:
        assert uow._connection is not None
        await uow._connection.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        control=await uow.instrument_selection.get_selection_control(strategy_group_id)
        runtime=await get_generic_selection_runtime_view(uow,GenericSelectionRuntimeReadonlyRequest(strategy_group_id=strategy_group_id,now_ms=now))
    return GenericSelectionPreviewView(control=control,runtime=runtime,cadence_hours=spec.cadence_hours,
        next_effective_period_anchor_ms=anchor,next_eligibility_not_before_ms=anchor+3_600_000)


@router.post("/controls/strategies/{strategy_group_id}/selection/static/activate")
async def activate_generic_static_selection(strategy_group_id: str,body: GenericStaticSelectionActivationBody,request: Request) -> SelectionControl:
    _validate_write_request(request)
    settings=get_settings(request)
    now_ms=get_clock_ms(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        await uow.owner_controls.get_strategy_control(strategy_group_id,for_update=True)
        existing=await uow.owner_controls.get_authorization_by_idempotency_key(body.idempotency_key)
        if existing is not None:
            if strategy_group_id=='SOR-1H-001':
                return await stage_orb_static_selection_mode(uow,rollback_baseline_id=body.rollback_baseline_id,
                    selection_epoch_id=body.selection_epoch_id,effective_session_start_ms=body.effective_period_anchor_ms,
                    request=_mutation(body,settings.auth.username,now_ms),authentication_strength='totp_step_up')
            return await stage_generic_static_selection_mode(uow,strategy_group_id=strategy_group_id,
                rollback_baseline_id=body.rollback_baseline_id,selection_epoch_id=body.selection_epoch_id,
                effective_period_anchor_ms=body.effective_period_anchor_ms,
                request=_mutation(body,settings.auth.username,now_ms),authentication_strength="totp_step_up")
        current=await uow.instrument_selection.get_selection_control(strategy_group_id,for_update=True)
        if current is None:
            raise OwnerControlBlocked("generic_selection_control_missing")
        if current.control_version!=body.expected_version:
            raise OwnerControlConflict("selection_control_version_conflict")
        await _require_step_up(body,request)
        if strategy_group_id=='SOR-1H-001':
            return await stage_orb_static_selection_mode(uow,rollback_baseline_id=body.rollback_baseline_id,
                selection_epoch_id=body.selection_epoch_id,effective_session_start_ms=body.effective_period_anchor_ms,
                request=_mutation(body,settings.auth.username,now_ms),authentication_strength='totp_step_up')
        return await stage_generic_static_selection_mode(uow,strategy_group_id=strategy_group_id,
            rollback_baseline_id=body.rollback_baseline_id,selection_epoch_id=body.selection_epoch_id,
            effective_period_anchor_ms=body.effective_period_anchor_ms,
            request=_mutation(body,settings.auth.username,now_ms),authentication_strength="totp_step_up")


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
        raise StepUpInvalid
    try:
        await get_auth_service(request).verify_step_up(body.totp_code,now_ms=get_clock_ms(request))
    except InvalidCredentials as exc:
        raise StepUpInvalid from exc


def _validate_write_request(request: Request) -> None:
    settings = get_settings(request)
    if request.headers.get("origin") != settings.public_origin:
        raise ForbiddenOwnerRequest
    host = request.headers.get("host", "").split(":", 1)[0]
    if host != settings.public_host:
        raise ForbiddenOwnerRequest
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if request.method == "POST" and content_type != "application/json":
        raise ForbiddenOwnerRequest
