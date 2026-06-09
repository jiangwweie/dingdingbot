"""PG repository for Owner capital baseline snapshot facts."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.owner_capital_baseline_snapshot import (
    OwnerCapitalBaselineSnapshot,
    OwnerCapitalBaselineSnapshotSource,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGOwnerCapitalBaselineSnapshotORM


class PgOwnerCapitalBaselineSnapshotRepository:
    """Append/read account-equity baseline facts without execution authority."""

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
        snapshot: OwnerCapitalBaselineSnapshot,
    ) -> OwnerCapitalBaselineSnapshot:
        async with self._session_maker() as session:
            async with session.begin():
                row = self._to_orm(snapshot)
                session.add(row)
                await session.flush()
                return self._to_domain(row)

    async def get(self, snapshot_id: str) -> OwnerCapitalBaselineSnapshot | None:
        async with self._session_maker() as session:
            row = await session.get(PGOwnerCapitalBaselineSnapshotORM, snapshot_id)
            return self._to_domain(row) if row is not None else None

    async def list(
        self,
        *,
        currency: str | None = None,
        limit: int = 50,
    ) -> list[OwnerCapitalBaselineSnapshot]:
        async with self._session_maker() as session:
            stmt = select(PGOwnerCapitalBaselineSnapshotORM)
            if currency is not None:
                stmt = stmt.where(PGOwnerCapitalBaselineSnapshotORM.currency == currency)
            stmt = (
                stmt.order_by(
                    PGOwnerCapitalBaselineSnapshotORM.occurred_at_ms.desc(),
                    PGOwnerCapitalBaselineSnapshotORM.snapshot_id.desc(),
                )
                .limit(max(limit, 0))
            )
            result = await session.execute(stmt)
            return [self._to_domain(row) for row in result.scalars().all()]

    @staticmethod
    def _to_orm(
        snapshot: OwnerCapitalBaselineSnapshot,
    ) -> PGOwnerCapitalBaselineSnapshotORM:
        return PGOwnerCapitalBaselineSnapshotORM(
            snapshot_id=snapshot.snapshot_id,
            currency=snapshot.currency,
            account_equity=snapshot.account_equity,
            capital_base=snapshot.capital_base,
            available_balance=snapshot.available_balance,
            unrealized_pnl=snapshot.unrealized_pnl,
            source=snapshot.source.value,
            reason=snapshot.reason,
            occurred_at_ms=snapshot.occurred_at_ms,
            recorded_by=snapshot.recorded_by,
            evidence_refs=list(snapshot.evidence_refs),
            metadata_json=dict(snapshot.metadata),
            records_account_equity_fact=snapshot.records_account_equity_fact,
            creates_withdrawal_instruction=snapshot.creates_withdrawal_instruction,
            creates_transfer_instruction=snapshot.creates_transfer_instruction,
            creates_order_instruction=snapshot.creates_order_instruction,
            calls_exchange=snapshot.calls_exchange,
            mutates_runtime_budget=snapshot.mutates_runtime_budget,
            mutates_strategy_pnl=snapshot.mutates_strategy_pnl,
            creates_risk_event=snapshot.creates_risk_event,
            created_at_ms=snapshot.occurred_at_ms,
            updated_at_ms=snapshot.occurred_at_ms,
        )

    @staticmethod
    def _to_domain(
        row: PGOwnerCapitalBaselineSnapshotORM,
    ) -> OwnerCapitalBaselineSnapshot:
        return OwnerCapitalBaselineSnapshot(
            snapshot_id=row.snapshot_id,
            currency=row.currency,
            account_equity=row.account_equity,
            capital_base=row.capital_base,
            available_balance=row.available_balance,
            unrealized_pnl=row.unrealized_pnl,
            source=OwnerCapitalBaselineSnapshotSource(row.source),
            reason=row.reason,
            occurred_at_ms=row.occurred_at_ms,
            recorded_by=row.recorded_by,
            evidence_refs=list(row.evidence_refs or []),
            metadata=dict(row.metadata_json or {}),
            records_account_equity_fact=row.records_account_equity_fact,
            creates_withdrawal_instruction=row.creates_withdrawal_instruction,
            creates_transfer_instruction=row.creates_transfer_instruction,
            creates_order_instruction=row.creates_order_instruction,
            calls_exchange=row.calls_exchange,
            mutates_runtime_budget=row.mutates_runtime_budget,
            mutates_strategy_pnl=row.mutates_strategy_pnl,
            creates_risk_event=row.creates_risk_event,
        )
