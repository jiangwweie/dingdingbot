"""Shared bounded read mechanics for Owner Console HTTP routes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import TypeVar
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, ValidationError

from src.trading_kernel.application.owner_console.models import (
    ApiEnvelope,
    EvidenceRef,
    Freshness,
)
from src.trading_kernel.infrastructure import pg_owner_read_repository
from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    PostgresOwnerReadRepository,
)
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    get_read_engine,
)

DataT = TypeVar("DataT")
FactsT = TypeVar("FactsT")
QueryT = TypeVar("QueryT", bound=BaseModel)


async def read_page_facts(
    request: Request,
    operation: Callable[[PostgresOwnerReadRepository], Awaitable[FactsT]],
) -> FactsT:
    """Read all facts for one page in one short repeatable-read transaction."""

    async with pg_owner_read_repository.owner_read_transaction(
        get_read_engine(request)
    ) as connection:
        repository = pg_owner_read_repository.PostgresOwnerReadRepository(connection)
        return await operation(repository)


def validate_query(model: type[QueryT], **values: object) -> QueryT:
    """Validate dynamic defaults through the immutable application query model."""

    try:
        return model.model_validate(values)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid bounded query") from exc


def envelope(
    data: DataT,
    *,
    now_ms: int,
    source_watermark_ms: int | None,
    freshness: Freshness = Freshness.FRESH,
) -> ApiEnvelope[DataT]:
    """Wrap one assembled snapshot without changing its business semantics."""

    return ApiEnvelope[DataT](
        snapshot_id=f"snap:{uuid4().hex}",
        generated_at=utc_iso8601(now_ms),
        source_watermark=(
            None
            if source_watermark_ms is None
            else utc_iso8601(source_watermark_ms)
        ),
        freshness=freshness,
        data=data,
    )


def evidence_watermark(evidence: Iterable[EvidenceRef]) -> int | None:
    """Return the latest exact persisted evidence timestamp, if any."""

    timestamps = tuple(item.occurred_at_ms for item in evidence)
    return None if not timestamps else max(timestamps)


def latest_ms(*values: int | None) -> int | None:
    """Return the maximum available persisted timestamp."""

    present = tuple(value for value in values if value is not None)
    return None if not present else max(present)


def utc_iso8601(timestamp_ms: int) -> str:
    """Serialize epoch milliseconds as an exact UTC ISO-8601 timestamp."""

    return (
        datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def utc_day_start_ms(timestamp_ms: int) -> int:
    """Return the UTC day boundary used by overview daily aggregates."""

    instant = datetime.fromtimestamp(timestamp_ms / 1_000, tz=UTC)
    return int(
        instant.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        * 1_000
    )
