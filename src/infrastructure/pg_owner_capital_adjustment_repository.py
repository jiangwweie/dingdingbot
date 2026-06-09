"""PG repository for Owner capital adjustment review facts."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.owner_capital_adjustment import (
    OwnerCapitalAdjustmentRecord,
    OwnerCapitalAdjustmentType,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGOwnerCapitalAdjustmentORM


class PgOwnerCapitalAdjustmentRepository:
    """Append/read Owner external capital facts without execution authority."""

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

    async def append(
        self,
        record: OwnerCapitalAdjustmentRecord,
    ) -> OwnerCapitalAdjustmentRecord:
        async with self._session_maker() as session:
            async with session.begin():
                row = self._to_orm(record)
                session.add(row)
                await session.flush()
                return self._to_domain(row)

    async def get(self, adjustment_id: str) -> OwnerCapitalAdjustmentRecord | None:
        async with self._session_maker() as session:
            row = await session.get(PGOwnerCapitalAdjustmentORM, adjustment_id)
            return self._to_domain(row) if row is not None else None

    async def list(
        self,
        *,
        currency: str | None = None,
        limit: int = 50,
    ) -> list[OwnerCapitalAdjustmentRecord]:
        async with self._session_maker() as session:
            stmt = select(PGOwnerCapitalAdjustmentORM)
            if currency is not None:
                stmt = stmt.where(PGOwnerCapitalAdjustmentORM.currency == currency)
            stmt = (
                stmt.order_by(
                    PGOwnerCapitalAdjustmentORM.occurred_at_ms.desc(),
                    PGOwnerCapitalAdjustmentORM.adjustment_id.desc(),
                )
                .limit(max(limit, 0))
            )
            result = await session.execute(stmt)
            return [self._to_domain(row) for row in result.scalars().all()]

    @staticmethod
    def _to_orm(
        record: OwnerCapitalAdjustmentRecord,
    ) -> PGOwnerCapitalAdjustmentORM:
        return PGOwnerCapitalAdjustmentORM(
            adjustment_id=record.adjustment_id,
            adjustment_type=record.adjustment_type.value,
            currency=record.currency,
            amount=record.amount,
            capital_base_delta=record.capital_base_delta,
            target_capital_base=record.target_capital_base,
            reason=record.reason,
            occurred_at_ms=record.occurred_at_ms,
            recorded_by=record.recorded_by,
            evidence_refs=list(record.evidence_refs),
            metadata_json=dict(record.metadata),
            records_external_owner_action=record.records_external_owner_action,
            withdrawal_instruction_created=record.withdrawal_instruction_created,
            transfer_instruction_created=record.transfer_instruction_created,
            order_instruction_created=record.order_instruction_created,
            exchange_called=record.exchange_called,
            mutates_runtime_budget=record.mutates_runtime_budget,
            mutates_strategy_pnl=record.mutates_strategy_pnl,
            creates_risk_event=record.creates_risk_event,
            created_at_ms=record.occurred_at_ms,
            updated_at_ms=record.occurred_at_ms,
        )

    @staticmethod
    def _to_domain(
        row: PGOwnerCapitalAdjustmentORM,
    ) -> OwnerCapitalAdjustmentRecord:
        return OwnerCapitalAdjustmentRecord(
            adjustment_id=row.adjustment_id,
            adjustment_type=OwnerCapitalAdjustmentType(row.adjustment_type),
            currency=row.currency,
            amount=row.amount,
            capital_base_delta=row.capital_base_delta,
            target_capital_base=row.target_capital_base,
            reason=row.reason,
            occurred_at_ms=row.occurred_at_ms,
            recorded_by=row.recorded_by,
            evidence_refs=list(row.evidence_refs or []),
            metadata=dict(row.metadata_json or {}),
            records_external_owner_action=row.records_external_owner_action,
            withdrawal_instruction_created=row.withdrawal_instruction_created,
            transfer_instruction_created=row.transfer_instruction_created,
            order_instruction_created=row.order_instruction_created,
            exchange_called=row.exchange_called,
            mutates_runtime_budget=row.mutates_runtime_budget,
            mutates_strategy_pnl=row.mutates_strategy_pnl,
            creates_risk_event=row.creates_risk_event,
        )
