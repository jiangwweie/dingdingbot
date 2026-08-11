"""Instrument Center and TOTP-controlled StrategyUniverse routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from src.trading_kernel.application.install_strategy_universe import (
    OwnerUniverseConfigurationRequest,
    UniverseConfigurationRequest,
    UniverseInstallResult,
    configure_strategy_universe_by_owner,
)
from src.trading_kernel.application.owner_console.models import (
    ApiEnvelope,
    Freshness,
    InstrumentCenterPage,
    InstrumentCenterQuery,
)
from src.trading_kernel.infrastructure.pg_product_current import (
    PostgresProductCurrentRepository,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.owner_console_http.auth import InvalidCredentials
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    get_auth_service,
    get_clock_ms,
    get_control_engine,
    get_market_data,
    get_settings,
)
from src.trading_kernel.interfaces.owner_console_http.errors import PublicMarketFailure
from src.trading_kernel.interfaces.owner_console_http.routes._shared import (
    envelope,
    read_page_facts,
    validate_query,
)

router = APIRouter(prefix="/api/owner/v1/instruments", tags=["instruments"])


class UniversePreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_profile_id: str = Field(min_length=1, max_length=160)
    event_id: str = Field(min_length=1, max_length=96)
    exchange_instrument_ids: tuple[str, ...] = Field(min_length=1, max_length=10)


class UniverseApplyBody(UniversePreviewBody):
    expected_base_universe_version_id: str | None = Field(
        default=None,
        max_length=160,
    )
    reason: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=160)
    totp_code: str = Field(min_length=6, max_length=8)


class UniverseChangePreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_profile_id: str
    owner_policy_id: str
    event_spec_id: str
    event_id: str
    base_universe_version_id: str | None
    current_exchange_instrument_ids: tuple[str, ...]
    proposed_exchange_instrument_ids: tuple[str, ...]
    added_exchange_instrument_ids: tuple[str, ...]
    removed_exchange_instrument_ids: tuple[str, ...]
    unchanged_exchange_instrument_ids: tuple[str, ...]
    can_apply: bool
    first_blocker: Literal["no_membership_change"] | None = None


class InstrumentRefreshResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempted_count: int = Field(ge=0, le=10)
    updated_count: int = Field(ge=0, le=10)
    unavailable_count: int = Field(ge=0, le=10)
    observed_at_ms: int = Field(gt=0)


@router.get("", response_model=ApiEnvelope[InstrumentCenterPage])
async def instrument_center(
    request: Request,
    product_family: Literal[
        "crypto_perpetual",
        "tradfi_equity_perpetual",
    ]
    | None = None,
    session_state: Literal[
        "pre_market",
        "regular",
        "after_market",
        "overnight",
        "no_trading",
        "unavailable",
    ]
    | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ApiEnvelope[InstrumentCenterPage]:
    now_ms = get_clock_ms(request)
    query = validate_query(
        InstrumentCenterQuery,
        product_family=product_family,
        session_state=session_state,
        limit=limit,
    )
    data = await read_page_facts(
        request,
        lambda repository: repository.read_instrument_center(query),
    )
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=data.source_watermark_ms,
        freshness=_instrument_freshness(data, now_ms=now_ms),
    )


@router.post("/universes/preview", response_model=UniverseChangePreview)
async def preview_universe_change(
    body: UniversePreviewBody,
    request: Request,
) -> UniverseChangePreview:
    _validate_write_request(request)
    now_ms = get_clock_ms(request)
    configured = UniverseConfigurationRequest(
        runtime_profile_id=body.runtime_profile_id,
        event_id=body.event_id,
        exchange_instrument_ids=body.exchange_instrument_ids,
        installed_at_ms=now_ms,
    )


    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        context = await uow.strategy_universes.resolve_install_context(
            runtime_profile_id=configured.runtime_profile_id,
            event_id=configured.event_id,
        )
        current = await uow.strategy_universes.get_current(context.event_spec_id)
        current_members = (
            ()
            if current is None
            else await uow.strategy_universes.get_members(
                current.universe_version_id
            )
        )
    proposed = configured.exchange_instrument_ids
    current_set = set(current_members)
    proposed_set = set(proposed)
    added = tuple(sorted(proposed_set - current_set))
    removed = tuple(sorted(current_set - proposed_set))
    unchanged = tuple(sorted(current_set & proposed_set))
    can_apply = bool(added or removed)
    return UniverseChangePreview(
        runtime_profile_id=configured.runtime_profile_id,
        owner_policy_id=context.owner_policy_id,
        event_spec_id=context.event_spec_id,
        event_id=configured.event_id,
        base_universe_version_id=(
            None if current is None else current.universe_version_id
        ),
        current_exchange_instrument_ids=current_members,
        proposed_exchange_instrument_ids=proposed,
        added_exchange_instrument_ids=added,
        removed_exchange_instrument_ids=removed,
        unchanged_exchange_instrument_ids=unchanged,
        can_apply=can_apply,
        first_blocker=None if can_apply else "no_membership_change",
    )


@router.post("/refresh", response_model=InstrumentRefreshResponse)
async def refresh_instrument_current(
    request: Request,
) -> InstrumentRefreshResponse:
    _validate_write_request(request)
    now_ms = get_clock_ms(request)
    engine = get_control_engine(request)
    async with engine.begin() as connection:
        targets = await PostgresProductCurrentRepository(
            connection
        ).list_refresh_targets()
    if not targets:
        return InstrumentRefreshResponse(
            attempted_count=0,
            updated_count=0,
            unavailable_count=0,
            observed_at_ms=now_ms,
        )
    try:
        snapshots = await get_market_data(request).read_product_sessions(
            targets,
            observed_at_ms=now_ms,
        )
    except (
        TimeoutError,
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise PublicMarketFailure from exc
    async with engine.begin() as connection:
        updated = await PostgresProductCurrentRepository(
            connection
        ).upsert_snapshots(snapshots)
    return InstrumentRefreshResponse(
        attempted_count=len(targets),
        updated_count=updated,
        unavailable_count=sum(
            item.product_status == "temporarily_unavailable"
            or item.session_state == "unavailable"
            for item in snapshots
        ),
        observed_at_ms=now_ms,
    )


@router.post("/universes/apply", response_model=UniverseInstallResult)
async def apply_universe_change(
    body: UniverseApplyBody,
    request: Request,
) -> UniverseInstallResult:
    _validate_write_request(request)
    now_ms = get_clock_ms(request)
    await get_auth_service(request).verify_step_up(
        body.totp_code,
        now_ms=now_ms,
    )
    settings = get_settings(request)
    async with PostgresKernelUnitOfWork(get_control_engine(request)) as uow:
        return await configure_strategy_universe_by_owner(
            uow,
            OwnerUniverseConfigurationRequest(
                runtime_profile_id=body.runtime_profile_id,
                event_id=body.event_id,
                exchange_instrument_ids=body.exchange_instrument_ids,
                expected_base_universe_version_id=(
                    body.expected_base_universe_version_id
                ),
                reason=body.reason,
                idempotency_key=body.idempotency_key,
                owner_identity=settings.auth.username,
                installed_at_ms=now_ms,
            ),
        )


def _instrument_freshness(
    page: InstrumentCenterPage,
    *,
    now_ms: int,
) -> Freshness:
    observed = tuple(
        item for item in page.items if item.observed_at_ms is not None
    )
    if not observed:
        return Freshness.UNAVAILABLE
    if any(
        item.valid_until_ms is None or item.valid_until_ms < now_ms
        for item in observed
    ):
        return Freshness.STALE
    return Freshness.FRESH


def _validate_write_request(request: Request) -> None:
    settings = get_settings(request)
    if request.headers.get("origin") != settings.public_origin:
        raise InvalidCredentials
    host = request.headers.get("host", "").split(":", 1)[0]
    if host != settings.public_host:
        raise InvalidCredentials
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type != "application/json":
        raise InvalidCredentials
