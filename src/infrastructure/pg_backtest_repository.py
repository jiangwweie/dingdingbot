"""PostgreSQL backtest report repository."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.models import Direction, PMSBacktestReport, PositionCloseEvent, PositionSummary
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.logger import setup_logger
from src.infrastructure.pg_models import (
    PGBacktestAttributionORM,
    PGBacktestReportORM,
    PGPositionCloseEventORM,
)

logger = setup_logger(__name__)


class PgBacktestReportRepository:
    """PG implementation matching BacktestReportRepository's active API."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    def _calculate_parameters_hash(self, strategy_snapshot: str, symbol: str, timeframe: str) -> str:
        content = f"{strategy_snapshot}:{symbol}:{timeframe}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        if value is None:
            return default
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return default

    def _serialize_positions_summary(self, positions: list[PositionSummary]) -> str:
        data = []
        for pos in positions:
            data.append(
                {
                    "position_id": pos.position_id,
                    "signal_id": pos.signal_id,
                    "symbol": pos.symbol,
                    "direction": pos.direction.value,
                    "entry_price": str(pos.entry_price),
                    "exit_price": str(pos.exit_price) if pos.exit_price else None,
                    "entry_time": pos.entry_time,
                    "exit_time": pos.exit_time,
                    "realized_pnl": str(pos.realized_pnl),
                    "exit_reason": pos.exit_reason,
                }
            )
        return json.dumps(data, ensure_ascii=False)

    def _deserialize_positions_summary(self, json_str: Optional[str]) -> list[PositionSummary]:
        if not json_str:
            return []
        try:
            data = json.loads(json_str)
        except Exception:
            return []

        positions: list[PositionSummary] = []
        for item in data:
            try:
                positions.append(
                    PositionSummary(
                        position_id=item["position_id"],
                        signal_id=item["signal_id"],
                        symbol=item["symbol"],
                        direction=Direction(item["direction"]),
                        entry_price=self._decimal(item.get("entry_price")),
                        exit_price=self._decimal(item.get("exit_price")) if item.get("exit_price") else None,
                        entry_time=item["entry_time"],
                        exit_time=item.get("exit_time"),
                        realized_pnl=self._decimal(item.get("realized_pnl")),
                        exit_reason=item.get("exit_reason"),
                    )
                )
            except Exception as exc:
                logger.warning(f"PG 回测仓位摘要解析失败，已忽略一条: {exc}")
        return positions

    async def save_report(
        self,
        report: PMSBacktestReport,
        strategy_snapshot: str,
        symbol: str,
        timeframe: str,
    ) -> None:
        if not report.strategy_id:
            raise ValueError("strategy_id 不能为空")

        parameters_hash = self._calculate_parameters_hash(strategy_snapshot, symbol, timeframe)
        report_id = (
            f"rpt_{report.strategy_id}_{report.backtest_start}_"
            f"{parameters_hash[:8]}_{uuid.uuid4().hex[:8]}"
        )
        created_at = int(datetime.now(timezone.utc).timestamp() * 1000)

        async with self._session_maker() as session:
            session.add(
                PGBacktestReportORM(
                    id=report_id,
                    strategy_id=report.strategy_id,
                    strategy_name=report.strategy_name,
                    strategy_version="1.0.0",
                    strategy_snapshot=strategy_snapshot,
                    parameters_hash=parameters_hash,
                    symbol=symbol,
                    timeframe=timeframe,
                    backtest_start=report.backtest_start,
                    backtest_end=report.backtest_end,
                    created_at=created_at,
                    initial_balance=report.initial_balance,
                    final_balance=report.final_balance,
                    total_return=report.total_return,
                    total_trades=report.total_trades,
                    winning_trades=report.winning_trades,
                    losing_trades=report.losing_trades,
                    win_rate=report.win_rate,
                    total_pnl=report.total_pnl,
                    total_fees_paid=report.total_fees_paid,
                    total_slippage_cost=report.total_slippage_cost,
                    total_funding_cost=report.total_funding_cost,
                    max_drawdown=report.max_drawdown,
                    sharpe_ratio=report.sharpe_ratio,
                    positions_summary=self._serialize_positions_summary(report.positions) if report.positions else None,
                    monthly_returns=None,
                )
            )

            for event in report.close_events or []:
                session.add(
                    PGPositionCloseEventORM(
                        report_id=report_id,
                        position_id=event.position_id,
                        order_id=event.order_id,
                        event_type=event.event_type,
                        event_category=event.event_category,
                        close_price=event.close_price,
                        close_qty=event.close_qty,
                        close_pnl=event.close_pnl,
                        close_fee=event.close_fee,
                        close_time=event.close_time,
                        exit_reason=event.exit_reason,
                    )
                )

            if report.signal_attributions or report.aggregate_attribution or report.analysis_dimensions:
                session.add(
                    PGBacktestAttributionORM(
                        report_id=report_id,
                        signal_attributions=report.signal_attributions,
                        aggregate_attribution=report.aggregate_attribution,
                        analysis_dimensions=report.analysis_dimensions,
                        created_at=created_at,
                    )
                )

            await session.commit()
        logger.info(f"已保存 PG 回测报告：{report_id}")

    async def get_report(self, report_id: str) -> Optional[PMSBacktestReport]:
        async with self._session_maker() as session:
            report = await session.get(PGBacktestReportORM, report_id)
            if not report:
                return None

            close_stmt = (
                select(PGPositionCloseEventORM)
                .where(PGPositionCloseEventORM.report_id == report_id)
                .order_by(PGPositionCloseEventORM.close_time.asc())
            )
            close_rows = (await session.execute(close_stmt)).scalars().all()
            close_events = [
                PositionCloseEvent(
                    position_id=row.position_id,
                    order_id=row.order_id,
                    event_type=row.event_type,
                    event_category=row.event_category,
                    close_price=row.close_price,
                    close_qty=row.close_qty,
                    close_pnl=row.close_pnl,
                    close_fee=row.close_fee,
                    close_time=row.close_time,
                    exit_reason=row.exit_reason,
                )
                for row in close_rows
            ]

            attr = await session.get(PGBacktestAttributionORM, report_id)
            return self._to_report(report, close_events, attr)

    async def get_reports_by_strategy(self, strategy_id: str, limit: int = 50) -> list[dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = (
                select(PGBacktestReportORM)
                .where(PGBacktestReportORM.strategy_id == strategy_id)
                .order_by(PGBacktestReportORM.backtest_start.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._summary(row) for row in rows]

    async def get_reports_by_parameters_hash(
        self,
        parameters_hash: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = (
                select(PGBacktestReportORM)
                .where(PGBacktestReportORM.parameters_hash == parameters_hash)
                .order_by(PGBacktestReportORM.backtest_start.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._summary(row) for row in rows]

    async def delete_report(self, report_id: str) -> None:
        async with self._session_maker() as session:
            await session.execute(delete(PGBacktestReportORM).where(PGBacktestReportORM.id == report_id))
            await session.commit()
        logger.info(f"已删除 PG 回测报告：{report_id}")

    async def get_report_snapshot(self, report_id: str) -> Optional[str]:
        async with self._session_maker() as session:
            stmt = select(PGBacktestReportORM.strategy_snapshot).where(PGBacktestReportORM.id == report_id)
            return (await session.execute(stmt)).scalar_one_or_none()

    async def list_reports(
        self,
        strategy_id: Optional[str] = None,
        symbol: Optional[str] = None,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict[str, Any]:
        filters = []
        if strategy_id:
            filters.append(PGBacktestReportORM.strategy_id == strategy_id)
        if symbol:
            filters.append(PGBacktestReportORM.symbol == symbol)
        if start_date:
            filters.append(PGBacktestReportORM.backtest_start >= start_date)
        if end_date:
            filters.append(PGBacktestReportORM.backtest_start <= end_date)

        sort_map = {
            "total_return": PGBacktestReportORM.total_return,
            "win_rate": PGBacktestReportORM.win_rate,
            "created_at": PGBacktestReportORM.created_at,
        }
        sort_col = sort_map.get(sort_by, PGBacktestReportORM.created_at)
        if sort_order.lower() != "asc":
            sort_col = sort_col.desc()

        offset = max(page - 1, 0) * page_size
        async with self._session_maker() as session:
            count_stmt = select(func.count()).select_from(PGBacktestReportORM)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = (await session.execute(count_stmt)).scalar_one()

            stmt = select(PGBacktestReportORM)
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.order_by(sort_col).limit(page_size).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()

        return {
            "reports": [self._list_item(row) for row in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def _summary(self, row: PGBacktestReportORM) -> dict[str, Any]:
        return {
            "id": row.id,
            "strategy_name": row.strategy_name,
            "backtest_start": row.backtest_start,
            "backtest_end": row.backtest_end,
            "total_return": row.total_return,
            "win_rate": row.win_rate,
            "total_pnl": row.total_pnl,
            "max_drawdown": row.max_drawdown,
            "total_trades": row.total_trades,
            "winning_trades": row.winning_trades,
            "losing_trades": row.losing_trades,
        }

    def _list_item(self, row: PGBacktestReportORM) -> dict[str, Any]:
        return {
            "id": row.id,
            "strategy_id": row.strategy_id,
            "strategy_name": row.strategy_name,
            "strategy_version": row.strategy_version,
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "backtest_start": row.backtest_start,
            "backtest_end": row.backtest_end,
            "created_at": row.created_at,
            "total_return": str(row.total_return),
            "total_trades": row.total_trades,
            "win_rate": str(row.win_rate),
            "total_pnl": str(row.total_pnl),
            "max_drawdown": str(row.max_drawdown),
            "sharpe_ratio": str(row.sharpe_ratio) if row.sharpe_ratio is not None else "None",
        }

    def _to_report(
        self,
        row: PGBacktestReportORM,
        close_events: list[PositionCloseEvent],
        attr: Optional[PGBacktestAttributionORM],
    ) -> PMSBacktestReport:
        return PMSBacktestReport(
            strategy_id=row.strategy_id,
            strategy_name=row.strategy_name,
            backtest_start=row.backtest_start,
            backtest_end=row.backtest_end,
            initial_balance=self._decimal(row.initial_balance),
            final_balance=self._decimal(row.final_balance),
            total_return=self._decimal(row.total_return),
            total_trades=row.total_trades,
            winning_trades=row.winning_trades,
            losing_trades=row.losing_trades,
            win_rate=self._decimal(row.win_rate),
            total_pnl=self._decimal(row.total_pnl),
            total_fees_paid=self._decimal(row.total_fees_paid),
            total_slippage_cost=self._decimal(row.total_slippage_cost),
            total_funding_cost=self._decimal(row.total_funding_cost),
            max_drawdown=self._decimal(row.max_drawdown),
            sharpe_ratio=row.sharpe_ratio,
            positions=self._deserialize_positions_summary(row.positions_summary),
            close_events=close_events,
            signal_attributions=attr.signal_attributions if attr else None,
            aggregate_attribution=attr.aggregate_attribution if attr else None,
            analysis_dimensions=attr.analysis_dimensions if attr else None,
        )
