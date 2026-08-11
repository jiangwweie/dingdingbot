"""Version-isolated strategy evaluation routes for the Owner Console."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request

from src.trading_kernel.application.owner_console.models import (
    ApiEnvelope,
    StrategyObservationListPage,
    StrategyObservationQuery,
    StrategySummaryPage,
    StrategySummaryQuery,
    StrategyTicketListPage,
    StrategyTicketQuery,
)
from src.trading_kernel.application.owner_console.strategies import (
    build_strategy_observation_page,
    build_strategy_page,
    build_strategy_ticket_page,
)
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    get_clock_ms,
)
from src.trading_kernel.interfaces.owner_console_http.routes._shared import (
    envelope,
    evidence_watermark,
    read_page_facts,
    validate_query,
)

router = APIRouter(prefix="/api/owner/v1/strategies", tags=["owner-read"])

_DAY_MS = 86_400_000


@router.get("", response_model=ApiEnvelope[StrategySummaryPage])
async def strategy_versions(
    request: Request,
    from_ms: int | None = None,
    to_ms: int | None = None,
    view: Literal["current", "all"] = "current",
) -> ApiEnvelope[StrategySummaryPage]:
    """Return bounded evaluation summaries keyed by immutable StrategyVersion."""

    now_ms = get_clock_ms(request)
    query = validate_query(
        StrategySummaryQuery,
        from_ms=now_ms - 30 * _DAY_MS if from_ms is None else from_ms,
        to_ms=now_ms if to_ms is None else to_ms,
        view=view,
    )
    data = build_strategy_page(
        await read_page_facts(
            request,
            lambda repository: repository.read_strategy_page_facts(query),
        )
    )
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=evidence_watermark(data.evidence),
    )


@router.get(
    "/{strategy_version_id}/tickets",
    response_model=ApiEnvelope[StrategyTicketListPage],
)
async def strategy_version_tickets(
    request: Request,
    strategy_version_id: Annotated[str, Path(min_length=1, max_length=160)],
    from_ms: int | None = None,
    to_ms: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2_048)] = None,
    scope: Literal["natural", "all"] = "natural",
    exit_path: Literal[
        "tp1_reached",
        "tp1_not_reached",
        "controlled_exit",
    ]
    | None = None,
) -> ApiEnvelope[StrategyTicketListPage]:
    """Return the path-bounded Ticket modal opened from one StrategyVersion."""

    now_ms = get_clock_ms(request)
    query = validate_query(
        StrategyTicketQuery,
        from_ms=now_ms - 30 * _DAY_MS if from_ms is None else from_ms,
        to_ms=now_ms if to_ms is None else to_ms,
        limit=limit,
        cursor=cursor,
        strategy_version_id=strategy_version_id,
        scope=scope,
        exit_path=exit_path,
    )
    data = build_strategy_ticket_page(
        await read_page_facts(
            request,
            lambda repository: repository.read_strategy_ticket_page_facts(query),
        )
    )
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=evidence_watermark(
            evidence for item in data.items for evidence in item.evidence
        ),
    )


@router.get(
    "/{strategy_version_id}/observations",
    response_model=ApiEnvelope[StrategyObservationListPage],
)
async def strategy_version_observations(
    request: Request,
    strategy_version_id: Annotated[str, Path(min_length=1, max_length=160)],
    from_ms: int | None = None,
    to_ms: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2_048)] = None,
    first_path: Literal[
        "tp1_first",
        "initial_stop_first",
        "ambiguous_same_bar",
        "opening_range_failure",
        "time_stop",
        "session_exit",
        "horizon_complete",
    ]
    | None = None,
) -> ApiEnvelope[StrategyObservationListPage]:
    """Return bounded Signal-owned Observation evidence for one version."""

    now_ms = get_clock_ms(request)
    query = validate_query(
        StrategyObservationQuery,
        from_ms=now_ms - 30 * _DAY_MS if from_ms is None else from_ms,
        to_ms=now_ms if to_ms is None else to_ms,
        limit=limit,
        cursor=cursor,
        strategy_version_id=strategy_version_id,
        first_path=first_path,
    )
    data = build_strategy_observation_page(
        await read_page_facts(
            request,
            lambda repository: repository.read_strategy_observation_page_facts(
                query
            ),
        )
    )
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=evidence_watermark(
            evidence for item in data.items for evidence in item.evidence
        ),
    )
