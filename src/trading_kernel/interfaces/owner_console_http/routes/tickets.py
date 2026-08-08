"""Bounded Owner Console Ticket and causality routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request

from src.trading_kernel.application.owner_console.causality import (
    build_trade_causality,
)
from src.trading_kernel.application.owner_console.models import (
    ApiEnvelope,
    TradeCausalityDetail,
    TradeListPage,
    TradeListQuery,
)
from src.trading_kernel.application.owner_console.trades import build_trade_page
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    get_clock_ms,
)
from src.trading_kernel.interfaces.owner_console_http.errors import (
    OwnerResourceNotFound,
)
from src.trading_kernel.interfaces.owner_console_http.routes._shared import (
    envelope,
    evidence_watermark,
    read_page_facts,
    validate_query,
)

router = APIRouter(prefix="/api/owner/v1/tickets", tags=["owner-read"])

_DAY_MS = 86_400_000


@router.get("", response_model=ApiEnvelope[TradeListPage])
async def tickets(
    request: Request,
    from_ms: int | None = None,
    to_ms: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2_048)] = None,
    aggregate_status: str | None = None,
    strategy_group_id: str | None = None,
    exchange_instrument_id: str | None = None,
    position_side: Literal["long", "short"] | None = None,
) -> ApiEnvelope[TradeListPage]:
    """Return one bounded keyset-paginated active/terminal Ticket page."""

    now_ms = get_clock_ms(request)
    query = validate_query(
        TradeListQuery,
        from_ms=now_ms - 30 * _DAY_MS if from_ms is None else from_ms,
        to_ms=now_ms if to_ms is None else to_ms,
        limit=limit,
        cursor=cursor,
        aggregate_status=aggregate_status,
        strategy_group_id=strategy_group_id,
        exchange_instrument_id=exchange_instrument_id,
        position_side=position_side,
    )
    facts = await read_page_facts(
        request,
        lambda repository: repository.read_trade_page_facts(query),
    )
    data = build_trade_page(facts)
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=evidence_watermark(
            evidence for item in data.items for evidence in item.evidence
        ),
    )


@router.get(
    "/{ticket_id}/causality",
    response_model=ApiEnvelope[TradeCausalityDetail],
)
async def ticket_causality(
    request: Request,
    ticket_id: Annotated[str, Path(min_length=1, max_length=160)],
) -> ApiEnvelope[TradeCausalityDetail]:
    """Return one exact immutable Ticket causality workbench."""

    now_ms = get_clock_ms(request)
    facts = await read_page_facts(
        request,
        lambda repository: repository.read_trade_causality_facts(ticket_id),
    )
    if facts is None:
        raise OwnerResourceNotFound
    data = build_trade_causality(facts)
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=evidence_watermark(data.evidence),
    )
