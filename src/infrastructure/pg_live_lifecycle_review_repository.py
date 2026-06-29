"""PG repository for live bounded-action lifecycle review records."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.live_lifecycle_review import BrcLiveLifecycleReviewRecord
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGBrcLiveLifecycleReviewORM


class PgLiveLifecycleReviewRepository:
    """Append/read live lifecycle review records without trade-side effects."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        await init_pg_core_db()

    async def append(self, record: BrcLiveLifecycleReviewRecord) -> BrcLiveLifecycleReviewRecord:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcLiveLifecycleReviewORM(**self._to_row_payload(record))
                session.add(row)
                await session.flush()
                return self._to_record(row)

    async def get_latest(
        self,
        *,
        authorization_id: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> Optional[BrcLiveLifecycleReviewRecord]:
        async with self._session_maker() as session:
            stmt = select(PGBrcLiveLifecycleReviewORM)
            if authorization_id is not None:
                stmt = stmt.where(PGBrcLiveLifecycleReviewORM.authorization_id == authorization_id)
            if symbol is not None:
                stmt = stmt.where(PGBrcLiveLifecycleReviewORM.symbol == symbol)
            stmt = stmt.order_by(PGBrcLiveLifecycleReviewORM.created_at_ms.desc()).limit(1)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return self._to_record(row) if row is not None else None

    async def list(
        self,
        *,
        authorization_id: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> list[BrcLiveLifecycleReviewRecord]:
        async with self._session_maker() as session:
            stmt = select(PGBrcLiveLifecycleReviewORM)
            if authorization_id is not None:
                stmt = stmt.where(PGBrcLiveLifecycleReviewORM.authorization_id == authorization_id)
            if symbol is not None:
                stmt = stmt.where(PGBrcLiveLifecycleReviewORM.symbol == symbol)
            stmt = stmt.order_by(PGBrcLiveLifecycleReviewORM.created_at_ms.desc()).limit(limit)
            result = await session.execute(stmt)
            return [self._to_record(row) for row in result.scalars().all()]

    @staticmethod
    def _to_row_payload(record: BrcLiveLifecycleReviewRecord) -> dict[str, object]:
        payload = record.model_dump(mode="json")
        payload["metadata_json"] = payload.pop("metadata")
        return payload

    @staticmethod
    def _to_record(row: PGBrcLiveLifecycleReviewORM) -> BrcLiveLifecycleReviewRecord:
        return BrcLiveLifecycleReviewRecord.model_validate(
            {
                "review_id": row.review_id,
                "authorization_id": row.authorization_id,
                "carrier_id": row.carrier_id,
                "strategy_family_id": row.strategy_family_id,
                "runtime_instance_id": row.runtime_instance_id,
                "trial_binding_id": row.trial_binding_id,
                "strategy_family_version_id": row.strategy_family_version_id,
                "signal_evaluation_id": row.signal_evaluation_id,
                "order_candidate_id": row.order_candidate_id,
                "symbol": row.symbol,
                "side": row.side,
                "quantity": row.quantity,
                "max_notional": row.max_notional,
                "leverage": row.leverage,
                "max_attempts": row.max_attempts,
                "protection_mode": row.protection_mode,
                "review_requirement": row.review_requirement,
                "lifecycle_status": row.lifecycle_status,
                "review_status": row.review_status,
                "final_gate_result": row.final_gate_result,
                "protection_status": row.protection_status,
                "execution_intent_id": row.execution_intent_id,
                "entry_order_id": row.entry_order_id,
                "entry_exchange_order_id": row.entry_exchange_order_id,
                "tp_order_ids": list(row.tp_order_ids or []),
                "tp_exchange_order_ids": list(row.tp_exchange_order_ids or []),
                "sl_order_id": row.sl_order_id,
                "sl_exchange_order_id": row.sl_exchange_order_id,
                "tp_price": row.tp_price,
                "sl_trigger": row.sl_trigger,
                "owner_risk_acceptance": row.owner_risk_acceptance,
                "hard_gates_passed": row.hard_gates_passed,
                "evidence_refs": list(row.evidence_refs or []),
                "metadata": dict(row.metadata_json or {}),
                "action_allowed": row.action_allowed,
                "creates_authorization": row.creates_authorization,
                "creates_execution_intent": row.creates_execution_intent,
                "places_order": row.places_order,
                "mutates_exchange": row.mutates_exchange,
                "grants_trading_permission": row.grants_trading_permission,
                "owner_action_enabled": row.owner_action_enabled,
                "created_by": row.created_by,
                "created_at_ms": row.created_at_ms,
                "updated_at_ms": row.updated_at_ms,
            }
        )
