"""Complete bounded income summary; list pagination never changes these totals."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from src.trading_kernel.application.owner_console.models import (
    ApiEnvelope,
    PerformanceQuery,
    PerformanceSummary,
)
from src.trading_kernel.interfaces.owner_console_http.dependencies import get_clock_ms
from src.trading_kernel.interfaces.owner_console_http.routes._shared import (
    envelope,
    read_page_facts,
    validate_query,
)

router = APIRouter(prefix="/api/owner/v1", tags=["owner-read"])


@router.get("/performance", response_model=ApiEnvelope[PerformanceSummary])
async def performance(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    from_ms: int | None = None,
    to_ms: int | None = None,
    strategy_group_id: str | None = None,
    strategy_version_id: str | None = None,
    exchange_instrument_id: str | None = None,
    position_side: Literal["long", "short"] | None = None,
    view: Literal["current", "all"] = "all",
    exit_scope: Literal["all", "strategy", "owner", "safety", "unknown"] = "all",
    review_status: Literal[
        "in_progress",
        "waiting_for_settlement",
        "waiting_for_review",
        "complete",
        "incomplete_evidence",
    ]
    | None = None,
    aggregate_status: str | None = None,
) -> ApiEnvelope[PerformanceSummary]:
    now = get_clock_ms(request)
    query = validate_query(
        PerformanceQuery,
        limit=limit,
        from_ms=now - 30 * 86400000 if from_ms is None else from_ms,
        to_ms=now if to_ms is None else to_ms,
        strategy_group_id=strategy_group_id,
        strategy_version_id=strategy_version_id,
        exchange_instrument_id=exchange_instrument_id,
        position_side=position_side,
        view=view,
        exit_scope=exit_scope,
        review_status=review_status,
        aggregate_status=aggregate_status,
    )
    data = await read_page_facts(
        request, lambda repo: repo.read_performance_summary(query)
    )
    return envelope(data, now_ms=now, source_watermark_ms=None)
