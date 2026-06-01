"""PG repository for read-only strategy group forward reviews."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.strategy_group_forward_review import StrategyGroupForwardReviewRecord
from src.infrastructure.database import get_pg_engine, get_pg_session_maker
from src.infrastructure.pg_models import PGBrcStrategyGroupForwardReviewORM


class PgStrategyGroupForwardReviewRepository:
    """Persist observe-only forward review records.

    This repository writes review/evidence metadata only. It has no dependency
    on execution intents, orders, runtime start, or exchange writes.
    """

    sink_id = "pg_brc_strategy_group_forward_reviews"

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        engine = get_pg_engine()
        async with engine.begin() as conn:
            await conn.run_sync(PGBrcStrategyGroupForwardReviewORM.__table__.create, checkfirst=True)

    async def record(self, review: StrategyGroupForwardReviewRecord) -> StrategyGroupForwardReviewRecord:
        payload = review.model_dump(mode="json")
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcStrategyGroupForwardReviewORM,
                    review.review_id,
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcStrategyGroupForwardReviewORM(review_id=review.review_id)
                    session.add(row)
                self._apply_payload(row, payload)
                await session.flush()
                return self._to_record(row)

    async def record_many(
        self,
        reviews: list[StrategyGroupForwardReviewRecord],
    ) -> list[StrategyGroupForwardReviewRecord]:
        recorded: list[StrategyGroupForwardReviewRecord] = []
        for review in reviews:
            recorded.append(await self.record(review))
        return recorded

    async def list_by_observation_id(
        self,
        observation_id: str,
    ) -> list[StrategyGroupForwardReviewRecord]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcStrategyGroupForwardReviewORM)
                .where(PGBrcStrategyGroupForwardReviewORM.observation_id == observation_id)
                .order_by(PGBrcStrategyGroupForwardReviewORM.review_due_at_ms.asc())
            )
            return [self._to_record(row) for row in result.scalars().all()]

    async def list_by_observation_ids(
        self,
        observation_ids: list[str],
    ) -> list[StrategyGroupForwardReviewRecord]:
        if not observation_ids:
            return []
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcStrategyGroupForwardReviewORM)
                .where(PGBrcStrategyGroupForwardReviewORM.observation_id.in_(observation_ids))
                .order_by(
                    PGBrcStrategyGroupForwardReviewORM.observation_id.asc(),
                    PGBrcStrategyGroupForwardReviewORM.review_due_at_ms.asc(),
                )
            )
            return [self._to_record(row) for row in result.scalars().all()]

    @staticmethod
    def _apply_payload(row: PGBrcStrategyGroupForwardReviewORM, payload: dict) -> None:
        row.observation_id = payload["observation_id"]
        row.candidate_id = payload["candidate_id"]
        row.symbol = payload["symbol"]
        row.side = payload["side"]
        row.signal_type = payload["signal_type"]
        row.market_bar_timestamp_ms = payload["market_bar_timestamp_ms"]
        row.review_window = payload["review_window"]
        row.review_due_at_ms = payload["review_due_at_ms"]
        row.review_status = payload["review_status"]
        row.forward_return_pct = _optional_decimal(payload.get("forward_return_pct"))
        row.mfe_pct = _optional_decimal(payload.get("mfe_pct"))
        row.mae_pct = _optional_decimal(payload.get("mae_pct"))
        row.source = payload["source"]
        row.calculated_at_ms = payload.get("calculated_at_ms")
        row.notes = payload.get("notes")
        row.not_order = payload["not_order"]
        row.not_execution_intent = payload["not_execution_intent"]
        row.no_execution_permission = payload["no_execution_permission"]
        row.no_order_permission = payload["no_order_permission"]
        row.no_runtime_start = payload["no_runtime_start"]
        row.updated_at_ms = payload.get("calculated_at_ms") or payload["review_due_at_ms"]
        if not row.created_at_ms:
            row.created_at_ms = row.updated_at_ms

    @staticmethod
    def _to_record(row: PGBrcStrategyGroupForwardReviewORM) -> StrategyGroupForwardReviewRecord:
        return StrategyGroupForwardReviewRecord(
            review_id=row.review_id,
            observation_id=row.observation_id,
            candidate_id=row.candidate_id,
            symbol=row.symbol,
            side=row.side,
            signal_type=row.signal_type,
            market_bar_timestamp_ms=row.market_bar_timestamp_ms,
            review_window=row.review_window,
            review_due_at_ms=row.review_due_at_ms,
            review_status=row.review_status,
            forward_return_pct=str(row.forward_return_pct) if row.forward_return_pct is not None else None,
            mfe_pct=str(row.mfe_pct) if row.mfe_pct is not None else None,
            mae_pct=str(row.mae_pct) if row.mae_pct is not None else None,
            source=row.source,
            calculated_at_ms=row.calculated_at_ms,
            notes=row.notes,
            not_order=True,
            not_execution_intent=True,
            no_execution_permission=True,
            no_order_permission=True,
            no_runtime_start=True,
        )


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
