"""Authenticated Owner control-plane HTTP routes."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer

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
from src.trading_kernel.domain.risk_budget import RiskBudgetReceipt
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
    long_limit = (policy.directional_stop_risk_limit_fraction * Decimal(limits[0])).normalize()
    short_limit = (policy.directional_stop_risk_limit_fraction * Decimal(limits[1])).normalize()
    return DirectionalRiskView(
        control=control,
        long_limit=(policy.directional_stop_risk_limit_fraction * Decimal(limits[0])).normalize(),
        short_limit=(policy.directional_stop_risk_limit_fraction * Decimal(limits[1])).normalize(),
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
    if strategy_group_id in (ORB_STRATEGY_GROUP_ID, *ORB_DIRECTIONAL_GROUPS):
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
            return await stage_orb_dynamic_selection_mode(uow,strategy_group_id=strategy_group_id,effective_session_start_ms=body.effective_session_start_ms,
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
    if strategy_group_id in (ORB_STRATEGY_GROUP_ID, *ORB_DIRECTIONAL_GROUPS):
        selection_spec_id = (
            ORB_SELECTION_SPEC_ID if strategy_group_id == ORB_STRATEGY_GROUP_ID
            else directional_orb_spec(strategy_group_id).selection_spec_id
        )
        now=get_clock_ms(request)
        session=now//86_400_000*86_400_000
        next_session=session if now<session+3_600_000 else session+86_400_000
        async with PostgresKernelUnitOfWork(get_read_engine(request)) as uow:
            assert uow._connection is not None
            await uow._connection.execute(sa.text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            try:
                await uow.instrument_selection.get_orb_spec(selection_spec_id)
            except LookupError:
                orb_runtime=None
            else:
                orb_runtime=await get_selection_runtime_view(uow,SelectionRuntimeReadonlyRequest(strategy_group_id=strategy_group_id,
                    selection_spec_id=selection_spec_id,session_start_ms=session))
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
            if strategy_group_id in (ORB_STRATEGY_GROUP_ID, *ORB_DIRECTIONAL_GROUPS):
                return await stage_orb_static_selection_mode(uow,strategy_group_id=strategy_group_id,rollback_baseline_id=body.rollback_baseline_id,
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
        if strategy_group_id in (ORB_STRATEGY_GROUP_ID, *ORB_DIRECTIONAL_GROUPS):
            return await stage_orb_static_selection_mode(uow,strategy_group_id=strategy_group_id,rollback_baseline_id=body.rollback_baseline_id,
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
        if (
            event_spec_id in (*EXIT_EVENTS, *ORB_DIRECTIONAL_EVENTS)
            and await uow.exit_profiles.get_current_configuration(
                venue_id=settings.venue_id, account_id=settings.account_id
            )
            is not None
        ):
            raise OwnerControlBlocked("exit_configuration_bundle_required")
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


class RiskBudgetBody(ControlWriteBody):
    baseline: str = Field(pattern=r"^0\.(?:02[0-9]?|030?)$")
    expected_directional_version: int = Field(ge=1)


class RiskBudgetPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline: str = Field(pattern=r"^0\.(?:02[0-9]?|030?)$")


class RiskBudgetView(BaseModel):
    venue_id: str
    account_id: str
    policy_version: int
    directional_version: int
    baseline: Decimal
    gross_limit: Decimal
    directional_limit: Decimal
    minimum_risk: Decimal
    long_limit: Decimal
    short_limit: Decimal
    view: str
    pending_baseline: Decimal | None
    pending_directional_view: str | None
    min_baseline: Decimal
    max_baseline: Decimal
    step: Decimal
    entry_enabled: bool
    updated_at_ms: int
    wallet_balance_at_last_admission: Decimal | None
    balance_captured_at_ms: int | None
    long_risk_at_stop: Decimal
    short_risk_at_stop: Decimal


@router.get("/controls/risk-budget")
async def get_risk_budget(request: Request) -> RiskBudgetView:
    from src.trading_kernel.domain.risk_budget import (
        BASELINE_STEP,
        MAX_BASELINE,
        MIN_BASELINE,
        RiskBudget,
    )

    settings = get_settings(request)
    async with owner_read_transaction(get_read_engine(request)) as c:
        policy = await PostgresEntryAdmissionRepository(c).get_owner_policy(
            settings.owner_policy_id
        )
        control = await PostgresDirectionalRiskRepository(c).get(
            settings.venue_id, settings.account_id
        )
        if policy is None or control is None:
            raise OwnerControlBlocked("risk_budget_authority_missing")
        admission = PostgresEntryAdmissionRepository(c)
        long_usage = await admission.sum_active_directional_stop_risk(venue_id=settings.venue_id, account_id=settings.account_id, position_side="long")
        short_usage = await admission.sum_active_directional_stop_risk(venue_id=settings.venue_id, account_id=settings.account_id, position_side="short")
        balance = (await c.execute(sa.select(capacity_claims.c.total_wallet_balance_at_claim, capacity_claims.c.created_at_ms).where(capacity_claims.c.venue_id == settings.venue_id, capacity_claims.c.account_id == settings.account_id).order_by(capacity_claims.c.created_at_ms.desc()).limit(1))).first()
        budget = RiskBudget(baseline=policy.max_ticket_stop_risk_fraction)
        if (
            policy.max_gross_stop_risk_fraction != budget.gross
            or policy.directional_stop_risk_limit_fraction != budget.directional
        ):
            raise OwnerControlBlocked("risk_budget_policy_inconsistent")
        limits = RULE_LIMITS[control.view]
        return RiskBudgetView(
            venue_id=settings.venue_id,
            account_id=settings.account_id,
            policy_version=policy.policy_version,
            directional_version=control.version,
            baseline=budget.baseline,
            gross_limit=budget.gross,
            directional_limit=budget.directional,
            minimum_risk=budget.minimum,
            long_limit=budget.directional * Decimal(limits[0]),
            short_limit=budget.directional * Decimal(limits[1]),
            view=control.view,
            pending_baseline=control.pending_baseline,
            pending_directional_view=control.pending_view,
            min_baseline=MIN_BASELINE,
            max_baseline=MAX_BASELINE,
            step=BASELINE_STEP,
            entry_enabled=policy.new_entry_submit_enabled,
            updated_at_ms=control.effective_at_ms,
            wallet_balance_at_last_admission=None if balance is None else balance[0],
            balance_captured_at_ms=None if balance is None else balance[1],
            long_risk_at_stop=long_usage,
            short_risk_at_stop=short_usage,
        )


@router.post("/controls/risk-budget/preview")
async def preview_risk_budget(
    body: RiskBudgetPreviewBody, request: Request
) -> RiskBudgetView:
    from src.trading_kernel.domain.risk_budget import RiskBudget

    _validate_write_request(request)
    budget = RiskBudget(baseline=Decimal(body.baseline))
    current = await get_risk_budget(request)
    limits = RULE_LIMITS[current.view]
    return current.model_copy(
        update={
            "baseline": budget.baseline,
            "gross_limit": budget.gross,
            "directional_limit": budget.directional,
            "minimum_risk": budget.minimum,
            "long_limit": budget.directional * Decimal(limits[0]),
            "short_limit": budget.directional * Decimal(limits[1]),
        }
    )


@router.post("/controls/risk-budget")
async def change_risk_budget(
    body: RiskBudgetBody, request: Request
) -> RiskBudgetReceipt:
    from src.trading_kernel.domain.risk_budget import RiskBudgetChangeRequest

    _validate_write_request(request)
    await _require_step_up(body, request)
    settings = get_settings(request)
    try:
        mutation = RiskBudgetChangeRequest(
            venue_id=settings.venue_id,
            account_id=settings.account_id,
            owner_policy_id=settings.owner_policy_id,
            baseline=Decimal(body.baseline),
            expected_policy_version=body.expected_version,
            expected_directional_version=body.expected_directional_version,
            owner_identity=settings.auth.username,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
            requested_at_ms=get_clock_ms(request),
        )
        async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
            result = await uow.directional_risk.request_budget_change(mutation)
        return RiskBudgetReceipt.model_validate(result)
    except ValueError as exc:
        raise OwnerControlConflict(str(exc)) from exc


@router.get("/controls/risk-budget/requests/{idempotency_key}")
async def get_risk_budget_receipt(
    idempotency_key: str, request: Request
) -> RiskBudgetReceipt | None:
    settings = get_settings(request)
    async with owner_read_transaction(get_read_engine(request)) as c:
        result = await PostgresDirectionalRiskRepository(c).budget_receipt(
            settings.venue_id, settings.account_id, idempotency_key
        )
    return None if result is None else RiskBudgetReceipt.model_validate(result)


# Supported TP fields only; the server inherits Runner/BE/guards from exact authority.
from src.trading_kernel.application.exit_configuration import (
    ActivateExitConfigurationRequest,
    ExitConfigurationPreview,
    activate_exit_configuration,
    preview_exit_configuration,
)
from src.trading_kernel.domain.exit_configuration import (
    DIRECTIONAL_EXIT_EVENTS,
    EXIT_EVENTS,
    MA50_EVENTS,
    EventExitParameters,
    ExitConfigurationIntent,
    ExitConfigurationRecord,
)
from src.trading_kernel.domain.exit_policy import ExitProfile
from src.trading_kernel.domain.exit_regime import BtcMa50Snapshot
from src.trading_kernel.domain.orb_session_selection import (
    ORB_DIRECTIONAL_EVENTS,
    ORB_DIRECTIONAL_GROUPS,
    ORB_DIRECTIONAL_LONG_EVENT,
    ORB_EVENT_SPEC_IDS,
    ORB_SELECTION_SPEC_ID,
    ORB_STRATEGY_GROUP_ID,
    directional_orb_spec,
)


class ExitConfigurationPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: ExitConfigurationIntent


class ExitConfigurationBody(ControlWriteBody):
    intent: ExitConfigurationIntent
    preview_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    preview_valid_until_ms: int = Field(gt=0)


def _require_exit_configuration_scope(
    intent: ExitConfigurationIntent, request: Request
) -> None:
    settings = get_settings(request)
    if intent.venue_id != settings.venue_id or intent.account_id != settings.account_id:
        raise OwnerControlBlocked("exit_configuration_account_scope_mismatch")


class ExitProfileSourceView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_spec_id: str
    profile: ExitProfile
    semantic_hash: str


class ExitConfigurationView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    current: ExitConfigurationRecord | None
    intent: ExitConfigurationIntent
    sources: tuple[ExitProfileSourceView, ...]
    ma50_snapshot: BtcMa50Snapshot | None


@router.get("/controls/exit-configuration")
async def read_exit_configuration(request: Request) -> ExitConfigurationView:
    settings = get_settings(request)
    async with owner_read_transaction(get_read_engine(request)) as connection:
        profiles = PostgresExitProfileAuthorityRepository(connection)
        record = await profiles.get_current_configuration(
            venue_id=settings.venue_id, account_id=settings.account_id
        )
        parameters = []
        sources = []
        split_bindings = tuple(
            [await profiles.get_current_binding(event) for event in ORB_DIRECTIONAL_EVENTS]
        )
        if any(split_bindings) and not all(split_bindings):
            raise OwnerControlBlocked("exit_binding_missing")
        events = DIRECTIONAL_EXIT_EVENTS if all(split_bindings) else EXIT_EVENTS
        for event in events:
            current = await profiles.get_current_binding(event)
            if current is None:
                raise OwnerControlBlocked("exit_binding_missing")
            binding = await profiles.get_binding(current.exit_binding_id)
            if binding is None:
                raise OwnerControlBlocked("exit_binding_missing")
            profile = await profiles.get_profile(
                exit_profile_id=binding.exit_profile_id,
                semantic_hash=binding.exit_profile_semantic_hash,
            )
            if profile is None:
                raise OwnerControlBlocked("exit_profile_missing")
            previous = None if record is None else next(
                (e for e in record.intent.events if e.event_spec_id == event), None
            )
            if record is not None and previous is None and event in ORB_DIRECTIONAL_EVENTS:
                old_event = ORB_EVENT_SPEC_IDS[ORB_DIRECTIONAL_EVENTS.index(event)]
                previous = next(e for e in record.intent.events if e.event_spec_id == old_event)
                source = next(p.profile for p in record.profiles if p.event_spec_id == old_event)
            else:
                source = profile.profile
            sor = event in (*ORB_EVENT_SPEC_IDS, *ORB_DIRECTIONAL_EVENTS)
            parameters.append(
                EventExitParameters(
                    event_spec_id=event,
                    expected_binding_id=current.exit_binding_id,
                    expected_binding_revision=current.projection_version,
                    reward_multiple=source.tp1.reward_multiple
                    if record
                    else Decimal("1.2")
                    if sor
                    else Decimal(1),
                    target_fraction=source.tp1.quantity_fraction
                    if record or sor
                    else Decimal(".05"),
                    minimum_lift=previous.minimum_lift if previous else not sor,
                    max_actual_fraction=previous.max_actual_fraction
                    if previous
                    else Decimal(1)
                    if sor
                    else Decimal(".5"),
                    ma50_enabled=event == ORB_DIRECTIONAL_LONG_EVENT or (
                        previous.ma50_enabled if previous else event in MA50_EVENTS
                    ),
                ).model_dump(mode="json")
            )
            sources.append(
                {
                    "event_spec_id": event,
                    "profile": source.model_dump(mode="json"),
                    "semantic_hash": source.semantic_hash(),
                }
            )
        snapshot = await profiles.get_ma50_snapshot()
    return ExitConfigurationView.model_validate(
        {
            "current": None if record is None else record.model_dump(mode="json"),
            "intent": {
                "product_id": "brc-app-manual-v1",
                "venue_id": settings.venue_id,
                "account_id": settings.account_id,
                "expected_revision": 0 if record is None else record.revision,
                "events": parameters,
            },
            "sources": sources,
            "ma50_snapshot": None
            if snapshot is None
            else snapshot.model_dump(mode="json"),
        }
    )


@router.post("/controls/exit-configuration/preview")
async def preview_exit_configuration_route(
    body: ExitConfigurationPreviewBody, request: Request
) -> ExitConfigurationPreview:
    _validate_write_request(request)
    _require_exit_configuration_scope(body.intent, request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        return await preview_exit_configuration(
            uow, intent=body.intent, now_ms=get_clock_ms(request)
        )


@router.post("/controls/exit-configuration")
async def activate_exit_configuration_route(
    body: ExitConfigurationBody, request: Request
) -> ExitConfigurationRecord:
    _validate_write_request(request)
    _require_exit_configuration_scope(body.intent, request)
    await _require_step_up(body, request)
    settings = get_settings(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        await uow.exit_profiles.acquire_authority_write_lock()
        return await activate_exit_configuration(
            uow,
            request=ActivateExitConfigurationRequest(
                expected_version=body.expected_version,
                intent=body.intent,
                preview_digest=body.preview_digest,
                preview_valid_until_ms=body.preview_valid_until_ms,
                reason=body.reason,
                idempotency_key=body.idempotency_key,
                owner_identity=settings.auth.username,
                now_ms=get_clock_ms(request),
            ),
            authentication_strength="totp_step_up",
        )


@router.get("/controls/exit-configuration/requests/{idempotency_key}")
async def read_exit_configuration_receipt(
    idempotency_key: str, request: Request
) -> ExitConfigurationRecord | None:
    settings = get_settings(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        await uow.exit_profiles.acquire_authority_write_lock()
        auth = await uow.owner_controls.get_authorization_by_idempotency_key(
            idempotency_key
        )
        if auth is None:
            return None
        if (
            auth.purpose != "exit_profile_bind"
            or auth.target_scope.get("account_id") != settings.account_id
            or auth.target_scope.get("venue_id") != settings.venue_id
        ):
            raise OwnerControlBlocked("exit_configuration_receipt_scope_mismatch")
        configuration_id = auth.target_scope.get("configuration_id")
        if not isinstance(configuration_id, str):
            raise OwnerControlBlocked("exit_configuration_receipt_missing")
        return await uow.exit_profiles.get_configuration(configuration_id)


from src.trading_kernel.domain.exit_execution import PostFillExitPlan


class TicketExitPlanView(BaseModel):
    protection_status: str = "unknown"
    stop_present: bool = False
    protection_reason: str | None = None
    model_config = ConfigDict(frozen=True, extra="forbid")
    ticket_id: str
    management_mode: Literal["AUTO", "MANUAL", "REVIEW_REQUIRED"]
    aggregate_status: str
    plan: PostFillExitPlan | None
    tp1_target_quantity: Decimal
    tp1_filled_quantity: Decimal
    current_quantity: Decimal
    active_stop_price: Decimal | None
    protected_quantity: Decimal
    observed_at_ms: int | None


@router.get("/tickets/{ticket_id}/exit-plan")
async def read_ticket_exit_plan(ticket_id: str, request: Request) -> TicketExitPlanView:
    settings = get_settings(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        aggregate = await uow.aggregates.get(ticket_id)
        if aggregate is None:
            raise HTTPException(status_code=404, detail="ticket_not_found")
        domain = aggregate.identity.netting_domain
        if (
            domain.venue_id != settings.venue_id
            or domain.account_id != settings.account_id
        ):
            raise HTTPException(status_code=404, detail="ticket_not_found")
        from src.trading_kernel.domain.manual_position import manual_protection_view
        view = manual_protection_view(reason=aggregate.manual_risk_reason,orders=aggregate.management_orders)
        return TicketExitPlanView(
            protection_status=view.status if aggregate.management_mode.value == "MANUAL" else "unknown",
            stop_present=view.stop_present,protection_reason=view.reason,
            ticket_id=ticket_id,
            management_mode=aggregate.management_mode.value,
            aggregate_status=aggregate.status.value,
            plan=aggregate.post_fill_exit_plan,
            tp1_target_quantity=aggregate.tp1_target_qty,
            tp1_filled_quantity=aggregate.tp1_filled_qty,
            current_quantity=aggregate.position_qty,
            active_stop_price=aggregate.active_stop_price,
            protected_quantity=aggregate.protected_qty,
            observed_at_ms=aggregate.management_observed_at_ms,
        )


from src.trading_kernel.domain.exit_execution import (
    ExitPlanUnexecutable,
    ExitQuantities,
    calculate_exit_quantities,
    calculate_tp_price,
)


class ExitSizingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_spec_id: str
    exchange_instrument_id: str
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    entry_price: Decimal = Field(gt=0, allow_inf_nan=False)
    initial_stop: Decimal = Field(gt=0, allow_inf_nan=False)
    parameters: EventExitParameters


class ExitSizingView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    quantity: Decimal
    tp_price: Decimal | None
    quantities: ExitQuantities | None
    blocker: str | None
    rules_observed_at_ms: int | None
    rules_valid_until_ms: int | None


@router.post("/controls/exit-configuration/sizing-preview")
async def preview_exit_sizing(body: ExitSizingBody, request: Request) -> ExitSizingView:
    _validate_write_request(request)
    settings = get_settings(request)
    from src.trading_kernel.domain.instrument_identity import (
        parse_binance_usdm_instrument_id,
    )

    parse_binance_usdm_instrument_id(body.exchange_instrument_id)
    if (
        body.event_spec_id != body.parameters.event_spec_id
        or body.event_spec_id not in (*EXIT_EVENTS, *ORB_DIRECTIONAL_EVENTS)
    ):
        raise OwnerControlBlocked("exit_sizing_event_scope_mismatch")
    now=get_clock_ms(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        current = await uow.exit_profiles.get_current_binding(body.event_spec_id)
        if (
            current is None
            or current.exit_binding_id != body.parameters.expected_binding_id
            or current.projection_version != body.parameters.expected_binding_revision
        ):
            raise OwnerControlConflict("exit_sizing_binding_changed")
        binding = await uow.exit_profiles.get_binding(current.exit_binding_id)
        source = (
            None
            if binding is None
            else await uow.exit_profiles.get_profile(
                exit_profile_id=binding.exit_profile_id,
                semantic_hash=binding.exit_profile_semantic_hash,
            )
        )
        rules = await uow.signals.get_instrument_rules(
            settings.venue_id, body.exchange_instrument_id
        )
    if source is None:
        raise OwnerControlBlocked("exit_profile_missing")
    if rules is None or rules.exit_order_rules is None:
        return ExitSizingView(
            quantity=body.quantity,
            tp_price=None,
            quantities=None,
            blocker="rule_unavailable",
            rules_observed_at_ms=None,
            rules_valid_until_ms=None,
        )
    from src.trading_kernel.domain.exit_configuration import derive_exit_profile

    profile = derive_exit_profile(
        source=source.profile, parameters=body.parameters, revision_id="sizing-preview"
    )
    assert profile.execution is not None
    price = None
    try:
        price = calculate_tp_price(
            side=profile.position_side,
            entry_price=body.entry_price,
            initial_stop=body.initial_stop,
            multiple=profile.tp1.reward_multiple,
            price_tick=rules.exit_order_rules.price_tick,
        )
        quantities = calculate_exit_quantities(
            quantity=body.quantity,
            tp_price=price,
            stop_price=body.initial_stop,
            target_fraction=profile.tp1.quantity_fraction,
            policy=profile.execution.quantity_policy,
            max_fraction=profile.execution.max_actual_fraction,
            rules=rules.exit_order_rules,
            now_ms=now,
        )
        blocker = None
    except ExitPlanUnexecutable as exc:
        quantities = None
        blocker = str(exc)
    return ExitSizingView(
        quantity=body.quantity,
        tp_price=price,
        quantities=quantities,
        blocker=blocker,
        rules_observed_at_ms=rules.exit_order_rules.observed_at_ms,
        rules_valid_until_ms=rules.exit_order_rules.valid_until_ms,
    )


class ReviewEnrichmentApplyBody(ControlWriteBody):
    request_id: str = Field(min_length=1,max_length=160)
    approved_preview_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


@router.post('/controls/review-enrichment/{ticket_id}/request')
async def request_review_enrichment_route(ticket_id: str, request: Request) -> dict[str, str]:
    from src.trading_kernel.application.review_enrichment import (
        request_review_enrichment,
    )

    _validate_write_request(request)
    settings=get_settings(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        aggregate=await uow.aggregates.get(ticket_id)
        if aggregate is None or aggregate.identity.netting_domain.account_id!=settings.account_id:
            raise HTTPException(status_code=404,detail='ticket_not_found')
        return {'request_id':await request_review_enrichment(uow,ticket_id=ticket_id,now_ms=get_clock_ms(request))}


@router.get('/controls/review-enrichment/requests/{request_id}')
async def review_enrichment_preview_route(request_id: str, request: Request) -> dict:
    settings=get_settings(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        row=await uow.reviews.get_enrichment(request_id)
        if row is None:
            raise HTTPException(status_code=404,detail='request_not_found')
        aggregate=await uow.aggregates.get(row.ticket_id)
        if aggregate is None or aggregate.identity.netting_domain.account_id!=settings.account_id:
            raise HTTPException(status_code=404,detail='request_not_found')
        return row.model_dump(mode="json")


@router.post('/controls/review-enrichment/apply')
async def apply_review_enrichment_route(body: ReviewEnrichmentApplyBody, request: Request) -> dict[str,str]:
    from src.trading_kernel.application.owner_control import (
        _authorization,
        _require_matching_authorization,
    )
    _validate_write_request(request)
    await _require_step_up(body,request)
    settings=get_settings(request)
    now=get_clock_ms(request)
    mutation=ControlMutationRequest(expected_version=body.expected_version,reason=body.reason,
        idempotency_key=body.idempotency_key,owner_identity=settings.auth.username,now_ms=now)
    scope: dict[str, JsonValue]={'product_id':'brc-app-manual-v1','account_id':settings.account_id,
        'request_id':body.request_id,'preview_digest':body.approved_preview_digest}
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        row=await uow.reviews.get_enrichment(body.request_id,for_update=True)
        if row is None:
            raise OwnerControlBlocked('review_enrichment_request_missing')
        aggregate=await uow.aggregates.get(row.ticket_id)
        if aggregate is None or aggregate.identity.netting_domain.account_id!=settings.account_id:
            raise OwnerControlBlocked('review_enrichment_account_mismatch')
        prior=await uow.owner_controls.get_authorization_by_idempotency_key(body.idempotency_key)
        if prior is None:
            current=await uow.reviews.get_for_ticket(row.ticket_id)
            if current is None or current.revision!=body.expected_version:
                raise OwnerControlConflict('review_revision_changed')
            authorization=_authorization(purpose='review_revise',request=mutation,
                authentication_strength='totp_step_up',target_scope=scope)
            await uow.owner_controls.add_authorization(authorization)
        else:
            _require_matching_authorization(prior,purpose='review_revise',request=mutation,target_scope=scope)
            authorization=prior
        await uow.reviews.approve_enrichment(body.request_id,digest=body.approved_preview_digest,
            authorization_id=authorization.authorization_id,now_ms=now)
        return {'request_id':body.request_id,'status':'approved'}
