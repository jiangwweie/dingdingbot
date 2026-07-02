"""PostgreSQL repository for auditable protection price plans."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.protection_price_planner import (
    ProtectionPlanPhase,
    ProtectionPricePlanRecord,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGBrcProtectionPricePlanORM


class PgProtectionPricePlanRepository:
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

    async def save_plan(self, plan: ProtectionPricePlanRecord) -> ProtectionPricePlanRecord:
        row = _to_orm(plan)
        try:
            async with self._session_maker() as session:
                async with session.begin():
                    session.add(row)
                return _to_domain(row)
        except SQLAlchemyError as exc:
            raise RuntimeError(f"pg_protection_price_plan_write_failed:{exc}") from exc

    async def latest_valid_plan(
        self,
        authorization_id: str,
        *,
        phase: ProtectionPlanPhase | None = None,
    ) -> ProtectionPricePlanRecord | None:
        try:
            async with self._session_maker() as session:
                stmt = (
                    select(PGBrcProtectionPricePlanORM)
                    .where(PGBrcProtectionPricePlanORM.authorization_id == authorization_id)
                    .where(PGBrcProtectionPricePlanORM.status == "valid")
                    .order_by(
                        PGBrcProtectionPricePlanORM.computed_at_ms.desc(),
                        PGBrcProtectionPricePlanORM.plan_id.desc(),
                    )
                    .limit(1)
                )
                if phase is not None:
                    stmt = stmt.where(PGBrcProtectionPricePlanORM.phase == phase)
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                return _to_domain(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise RuntimeError(f"pg_protection_price_plan_read_failed:{exc}") from exc


def _to_orm(plan: ProtectionPricePlanRecord) -> PGBrcProtectionPricePlanORM:
    return PGBrcProtectionPricePlanORM(
        plan_id=plan.plan_id,
        authorization_id=plan.authorization_id,
        carrier_id=plan.carrier_id,
        symbol=plan.symbol,
        side=plan.side,
        phase=plan.phase,
        status=plan.status,
        planner_version=plan.planner_version,
        price_source_type=plan.price_source_type,
        reference_price=plan.reference_price,
        fill_price=plan.fill_price,
        quantity=plan.quantity,
        tp_price=plan.tp_price,
        sl_price=plan.sl_price,
        tp_quantity=plan.tp_quantity,
        sl_quantity=plan.sl_quantity,
        tick_size=plan.tick_size,
        amount_step=plan.amount_step,
        min_amount=plan.min_amount,
        min_notional=plan.min_notional,
        rounding_json=dict(plan.rounding),
        filters_json=dict(plan.filters),
        blockers_json=list(plan.blockers),
        computed_at_ms=plan.computed_at_ms,
        source_ref=plan.source_ref,
        created_at_ms=plan.computed_at_ms,
    )


def _to_domain(row: PGBrcProtectionPricePlanORM) -> ProtectionPricePlanRecord:
    return ProtectionPricePlanRecord(
        plan_id=row.plan_id,
        authorization_id=row.authorization_id,
        carrier_id=row.carrier_id,
        symbol=row.symbol,
        side=row.side,
        phase=row.phase,
        status=row.status,
        planner_version=row.planner_version,
        price_source_type=row.price_source_type,
        reference_price=row.reference_price,
        fill_price=row.fill_price,
        quantity=row.quantity,
        tp_price=row.tp_price,
        sl_price=row.sl_price,
        tp_quantity=row.tp_quantity,
        sl_quantity=row.sl_quantity,
        tick_size=row.tick_size,
        amount_step=row.amount_step,
        min_amount=row.min_amount,
        min_notional=row.min_notional,
        rounding=dict(row.rounding_json or {}),
        filters=dict(row.filters_json or {}),
        blockers=list(row.blockers_json or []),
        computed_at_ms=row.computed_at_ms,
        source_ref=row.source_ref,
    )
