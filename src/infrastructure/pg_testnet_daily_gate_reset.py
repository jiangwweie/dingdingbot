"""PG implementation for guarded testnet daily-gate reset plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.testnet_daily_gate_reset import DailyGateResetPlan
from src.infrastructure.database import get_pg_session_maker
from src.infrastructure.pg_models import PGDailyRiskStatsAggregateORM


@dataclass(frozen=True)
class DailyGateResetResult:
    scope_key: str
    stats_date: str
    profile_name: str
    symbol: str
    carrier_id: str
    row_found: bool
    trade_count_before: int | None
    trade_count_after: int | None
    realized_pnl_before: Decimal | None
    realized_pnl_after: Decimal | None
    live_ready: bool = False
    execution_permission_granted: bool = False
    order_permission_granted: bool = False


class PgTestnetDailyGateResetRepository:
    """Apply narrow testnet daily-gate reset plans to PG aggregates."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def reset_trade_count(self, plan: DailyGateResetPlan) -> DailyGateResetResult:
        async with self._session_maker() as session:
            async with session.begin():
                stmt = (
                    select(PGDailyRiskStatsAggregateORM)
                    .where(
                        PGDailyRiskStatsAggregateORM.scope_key == plan.scope_key,
                        PGDailyRiskStatsAggregateORM.stats_date == plan.stats_date,
                    )
                    .with_for_update()
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is None:
                    return DailyGateResetResult(
                        scope_key=plan.scope_key,
                        stats_date=plan.stats_date.isoformat(),
                        profile_name=plan.profile_name,
                        symbol=plan.symbol,
                        carrier_id=plan.carrier_id,
                        row_found=False,
                        trade_count_before=None,
                        trade_count_after=None,
                        realized_pnl_before=None,
                        realized_pnl_after=None,
                    )

                trade_count_before = int(row.trade_count or 0)
                realized_pnl_before = Decimal(str(row.realized_pnl or "0"))
                row.trade_count = plan.reset_trade_count_to
                row.updated_at = datetime.now(timezone.utc)
                await session.flush()
                return DailyGateResetResult(
                    scope_key=plan.scope_key,
                    stats_date=plan.stats_date.isoformat(),
                    profile_name=plan.profile_name,
                    symbol=plan.symbol,
                    carrier_id=plan.carrier_id,
                    row_found=True,
                    trade_count_before=trade_count_before,
                    trade_count_after=int(row.trade_count or 0),
                    realized_pnl_before=realized_pnl_before,
                    realized_pnl_after=Decimal(str(row.realized_pnl or "0")),
                )
