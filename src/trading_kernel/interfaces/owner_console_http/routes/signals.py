"""Bounded Owner Console Signal routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request

from src.trading_kernel.application.owner_console.models import (
    ApiEnvelope,
    SignalAdmissionDetail,
    SignalListPage,
    SignalListQuery,
)
from src.trading_kernel.application.owner_console.signals import (
    build_signal_detail,
    build_signal_page,
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

router = APIRouter(prefix="/api/owner/v1/signals", tags=["owner-read"])

_DAY_MS = 86_400_000


@router.get("", response_model=ApiEnvelope[SignalListPage])
async def signals(
    request: Request,
    from_ms: int | None = None,
    to_ms: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2_048)] = None,
    decision_status: Literal["admitted", "rejected", "not_evaluated"] | None = None,
    strategy_group_id: str | None = None,
    exchange_instrument_id: str | None = None,
    position_side: Literal["long", "short"] | None = None,
) -> ApiEnvelope[SignalListPage]:
    """Return one bounded keyset-paginated Signal page."""

    now_ms = get_clock_ms(request)
    query = validate_query(
        SignalListQuery,
        from_ms=now_ms - 7 * _DAY_MS if from_ms is None else from_ms,
        to_ms=now_ms if to_ms is None else to_ms,
        limit=limit,
        cursor=cursor,
        decision_status=decision_status,
        strategy_group_id=strategy_group_id,
        exchange_instrument_id=exchange_instrument_id,
        position_side=position_side,
    )
    facts = await read_page_facts(
        request,
        lambda repository: repository.read_signal_page_facts(query),
    )
    data = build_signal_page(facts)
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=evidence_watermark(
            evidence for item in data.items for evidence in item.evidence
        ),
    )


@router.get(
    "/{signal_event_id}",
    response_model=ApiEnvelope[SignalAdmissionDetail],
)
async def signal_detail(
    request: Request,
    signal_event_id: Annotated[str, Path(min_length=1, max_length=160)],
) -> ApiEnvelope[SignalAdmissionDetail]:
    """Return exact persisted admission causality for one Signal."""

    now_ms = get_clock_ms(request)
    facts = await read_page_facts(
        request,
        lambda repository: repository.read_signal_detail_facts(signal_event_id),
    )
    data = build_signal_detail(facts)
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=evidence_watermark(data.evidence),
    )
