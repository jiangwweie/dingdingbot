"""Shared current management receiver lease used by Entry and ordinary AUTO writes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.domain.product_identity import PRODUCT_ID

if TYPE_CHECKING:
    from src.trading_kernel.application.ports import ManagementRepository


async def management_feed_is_current(
    uow, *, venue_id, account_id, runtime_commit, now_ms
):
    return await uow.management.feed_ready(
        f"{PRODUCT_ID}:{venue_id}:{account_id}",
        now_ms=now_ms,
        runtime_commit=runtime_commit,
    )


class ManagementFeedReadiness(BaseModel):
    """Trading readiness is distinct from service liveness and integrity certification."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    required: bool
    ready: bool
    connection_state: str
    blocker_code: str | None
    blocked_since_ms: int | None
    last_successful_at_ms: int | None
    lease_until_ms: int | None
    epoch_id: str | None
    persisted_watermark: int | None
    applied_watermark: int | None


async def read_management_feed_readiness(
    management: ManagementRepository,
    *,
    required: bool,
    venue_id: str,
    account_id: str,
    runtime_commit: str | None,
    now_ms: int,
) -> ManagementFeedReadiness:
    scope = f"{PRODUCT_ID}:{venue_id}:{account_id}"
    return await management.read_readiness(
        scope, required=required, runtime_commit=runtime_commit, now_ms=now_ms
    )
