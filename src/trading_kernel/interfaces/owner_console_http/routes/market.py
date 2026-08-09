"""Credential-free bounded public candle route."""

from __future__ import annotations

from decimal import InvalidOperation
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from src.trading_kernel.application.owner_console.models import (
    ApiEnvelope,
    CandleQuery,
    CandleSeries,
)
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    get_clock_ms,
    get_market_data,
)
from src.trading_kernel.interfaces.owner_console_http.errors import (
    PublicMarketFailure,
)
from src.trading_kernel.interfaces.owner_console_http.routes._shared import (
    envelope,
    validate_query,
)

router = APIRouter(prefix="/api/owner/v1/market", tags=["owner-read"])


@router.get("/candles", response_model=ApiEnvelope[CandleSeries])
async def candles(
    request: Request,
    exchange_instrument_id: str,
    timeframe: Literal["15m", "1h"],
    closed_at_ms: Annotated[int, Query(gt=0)],
    limit: Annotated[int, Query(ge=1, le=500)] = 300,
) -> ApiEnvelope[CandleSeries]:
    """Read public closed candles without opening a PostgreSQL transaction."""

    now_ms = get_clock_ms(request)
    query = validate_query(
        CandleQuery,
        exchange_instrument_id=exchange_instrument_id,
        timeframe=timeframe,
        limit=limit,
        closed_at_ms=closed_at_ms,
    )
    try:
        data = await get_market_data(request).read_candles(query)
    except (
        TimeoutError,
        TypeError,
        ValueError,
        InvalidOperation,
        OverflowError,
    ) as exc:
        raise PublicMarketFailure from exc
    return envelope(
        data,
        now_ms=now_ms,
        source_watermark_ms=(
            None if not data.candles else data.candles[-1].close_time_ms
        ),
    )
