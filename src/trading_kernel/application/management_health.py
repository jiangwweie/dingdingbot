"""Shared current management receiver lease used by Entry and ordinary AUTO writes."""

from src.trading_kernel.domain.product_identity import PRODUCT_ID


async def management_feed_is_current(
    uow, *, venue_id, account_id, runtime_commit, now_ms
):
    return await uow.management.feed_ready(
        f"{PRODUCT_ID}:{venue_id}:{account_id}",
        now_ms=now_ms,
        runtime_commit=runtime_commit,
    )
