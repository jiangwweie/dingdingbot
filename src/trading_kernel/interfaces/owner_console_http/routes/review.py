"""Bounded deterministic Owner Console Review Center route."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from src.trading_kernel.application.owner_console.models import (
    ApiEnvelope,
    ReviewCenterSummary,
    ReviewListQuery,
)
from src.trading_kernel.application.owner_console.programmatic_review import (
    build_review_center,
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

router = APIRouter(prefix="/api/owner/v1/review", tags=["owner-read"])

_DAY_MS = 86_400_000


@router.get("", response_model=ApiEnvelope[ReviewCenterSummary])
async def review_center(
    request: Request,
    from_ms: int | None = None,
    to_ms: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2_048)] = None,
    review_status: Literal[
        "in_progress",
        "waiting_for_settlement",
        "waiting_for_review",
        "complete",
        "incomplete_evidence",
    ]
    | None = None,
    strategy_group_id: str | None = None,
) -> ApiEnvelope[ReviewCenterSummary]:
    """Return one deterministic bounded terminal Review Center snapshot."""

    now_ms = get_clock_ms(request)
    query = validate_query(
        ReviewListQuery,
        from_ms=now_ms - 30 * _DAY_MS if from_ms is None else from_ms,
        to_ms=now_ms if to_ms is None else to_ms,
        limit=limit,
        cursor=cursor,
        review_status=review_status,
        strategy_group_id=strategy_group_id,
    )
    facts = await read_page_facts(
        request,
        lambda repository: repository.read_review_center_facts(query),
    )
    data = build_review_center(facts)
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=evidence_watermark(data.evidence),
    )
