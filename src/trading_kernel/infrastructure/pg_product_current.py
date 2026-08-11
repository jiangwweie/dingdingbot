"""Short-transaction PostgreSQL projection for current product/session facts."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.product import ProductSessionSnapshot
from src.trading_kernel.infrastructure.pg_models import (
    instrument_product_current,
    instrument_product_profiles,
)


class PostgresProductCurrentRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def list_refresh_targets(self, *, limit: int = 10) -> tuple[str, ...]:
        if not 1 <= limit <= 10:
            raise ValueError("product refresh target limit must be between one and ten")
        rows = (
            await self._connection.execute(
                sa.select(
                    instrument_product_profiles.c.exchange_instrument_id
                )
                .where(
                    instrument_product_profiles.c.product_family
                    == "tradfi_equity_perpetual",
                    instrument_product_profiles.c.status.in_(
                        ("candidate", "reference", "active")
                    ),
                )
                .order_by(
                    instrument_product_profiles.c.status,
                    instrument_product_profiles.c.exchange_instrument_id,
                )
                .limit(limit)
            )
        ).scalars().all()
        return tuple(str(item) for item in rows)

    async def upsert_snapshots(
        self,
        snapshots: tuple[ProductSessionSnapshot, ...],
    ) -> int:
        if not snapshots:
            return 0
        identities = tuple(item.exchange_instrument_id for item in snapshots)
        if len(identities) != len(set(identities)) or len(identities) > 10:
            raise ValueError("product refresh snapshots must be unique and bounded")
        if any(
            item.product_family != "tradfi_equity_perpetual"
            for item in snapshots
        ):
            raise ValueError("product refresh accepts only TradFi Equity products")
        values = [
            {
                "exchange_instrument_id": item.exchange_instrument_id,
                "product_status": item.product_status,
                "session_state": item.session_state,
                "regular_session_open_ms": item.regular_session_open_ms,
                "regular_session_close_ms": item.regular_session_close_ms,
                "mark_price": item.mark_price,
                "index_price": item.index_price,
                "funding_rate": item.funding_rate,
                "best_bid": item.best_bid,
                "best_ask": item.best_ask,
                "best_bid_quantity": item.best_bid_quantity,
                "best_ask_quantity": item.best_ask_quantity,
                "corporate_event_status": item.corporate_event_status,
                "observed_at_ms": item.observed_at_ms,
                "valid_until_ms": item.valid_until_ms,
                "source_ref": item.source_ref,
                "projection_version": 1,
            }
            for item in snapshots
        ]
        statement = pg_insert(instrument_product_current).values(values)
        await self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    instrument_product_current.c.exchange_instrument_id
                ],
                set_={
                    "product_status": statement.excluded.product_status,
                    "session_state": statement.excluded.session_state,
                    "regular_session_open_ms": (
                        statement.excluded.regular_session_open_ms
                    ),
                    "regular_session_close_ms": (
                        statement.excluded.regular_session_close_ms
                    ),
                    "mark_price": statement.excluded.mark_price,
                    "index_price": statement.excluded.index_price,
                    "funding_rate": statement.excluded.funding_rate,
                    "best_bid": statement.excluded.best_bid,
                    "best_ask": statement.excluded.best_ask,
                    "best_bid_quantity": statement.excluded.best_bid_quantity,
                    "best_ask_quantity": statement.excluded.best_ask_quantity,
                    "corporate_event_status": (
                        statement.excluded.corporate_event_status
                    ),
                    "observed_at_ms": statement.excluded.observed_at_ms,
                    "valid_until_ms": statement.excluded.valid_until_ms,
                    "source_ref": statement.excluded.source_ref,
                    "projection_version": (
                        instrument_product_current.c.projection_version + 1
                    ),
                },
            )
        )
        return len(snapshots)
