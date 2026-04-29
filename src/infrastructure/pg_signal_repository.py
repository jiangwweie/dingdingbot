"""
PostgreSQL Signal Repository - live signals / signal_take_profits 真源

本仓储只负责:
- signals
- signal_take_profits

不负责:
- signal_attempts
- config_snapshots
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.models import (
    AttemptDeleteRequest,
    AttemptQuery,
    Direction,
    SignalDeleteRequest,
    SignalQuery,
    SignalResult,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.logger import logger
from src.infrastructure.pg_models import PGSignalAttemptORM, PGSignalORM, PGSignalTakeProfitORM


class PgSignalRepository:
    """PG live signal 仓储。"""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    def _json_safe(self, value: Any) -> Any:
        return json.loads(json.dumps(value, ensure_ascii=False, default=self._json_default))

    async def save_signal(
        self,
        signal: SignalResult,
        signal_id: str = None,
        status: str = "PENDING",
        source: str = "live",
    ) -> str:
        created_at = datetime.now(timezone.utc).isoformat()
        signal_id_value = signal_id or created_at
        values = self._build_signal_values(
            signal=signal,
            signal_id_value=signal_id_value,
            created_at=created_at,
            status=status,
            source=source,
        )

        async with self._session_maker() as session:
            try:
                stmt = select(PGSignalORM).where(PGSignalORM.signal_id == signal_id_value)
                orm = (await session.execute(stmt)).scalar_one_or_none()
                if orm is None:
                    session.add(PGSignalORM(**values))
                else:
                    self._apply_signal_refresh(orm, values)

                if signal.take_profit_levels is not None:
                    await self._replace_take_profit_levels(
                        session,
                        signal_id_value,
                        signal.take_profit_levels,
                    )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                stmt = select(PGSignalORM).where(PGSignalORM.signal_id == signal_id_value)
                orm = (await session.execute(stmt)).scalar_one_or_none()
                if orm is None:
                    raise
                self._apply_signal_refresh(orm, values)
                if signal.take_profit_levels is not None:
                    await self._replace_take_profit_levels(
                        session,
                        signal_id_value,
                        signal.take_profit_levels,
                    )
                await session.commit()

        logger.info(f"PG live signal saved: signal_id={signal_id_value}, {signal.symbol}:{signal.timeframe}")
        return signal_id_value

    def _build_signal_values(
        self,
        *,
        signal: SignalResult,
        signal_id_value: str,
        created_at: str,
        status: str,
        source: str,
    ) -> Dict[str, Any]:
        take_profit_1 = None
        if signal.take_profit_levels:
            take_profit_1 = Decimal(str(signal.take_profit_levels[0].get("price")))
        return {
            "signal_id": signal_id_value,
            "created_at": created_at,
            "symbol": signal.symbol,
            "timeframe": signal.timeframe,
            "direction": Direction.normalize(signal.direction),
            "entry_price": signal.entry_price,
            "stop_loss": signal.suggested_stop_loss,
            "position_size": signal.suggested_position_size,
            "leverage": signal.current_leverage,
            "tags_json": signal.tags,
            "risk_info": signal.risk_reward_info,
            "status": self._normalize_status(status) or "PENDING",
            "take_profit_1": take_profit_1,
            "pnl_ratio": signal.pnl_ratio,
            "kline_timestamp": signal.kline_timestamp or None,
            "strategy_name": signal.strategy_name,
            "score": Decimal(str(signal.score)),
            "source": source,
            "pattern_score": Decimal(str(signal.score)),
            "ema_trend": "",
            "mtf_status": "",
        }

    def _apply_signal_refresh(self, orm: PGSignalORM, values: Dict[str, Any]) -> None:
        orm.symbol = values["symbol"]
        orm.timeframe = values["timeframe"]
        orm.direction = values["direction"]
        orm.entry_price = values["entry_price"]
        orm.stop_loss = values["stop_loss"]
        orm.position_size = values["position_size"]
        orm.leverage = values["leverage"]
        orm.tags_json = values["tags_json"]
        orm.risk_info = values["risk_info"]
        orm.take_profit_1 = values["take_profit_1"]
        orm.kline_timestamp = values["kline_timestamp"]
        orm.strategy_name = values["strategy_name"]
        orm.score = values["score"]
        orm.source = values["source"]
        orm.pattern_score = values["pattern_score"]
        orm.ema_trend = values["ema_trend"]
        orm.mtf_status = values["mtf_status"]
        orm.status = self._preserve_status_on_refresh(orm.status, values["status"])

    def _normalize_status(self, status: Optional[str]) -> Optional[str]:
        if status is None:
            return None
        return status.strip().upper()

    def _preserve_status_on_refresh(
        self,
        existing_status: Optional[str],
        incoming_status: Optional[str],
    ) -> Optional[str]:
        existing = self._normalize_status(existing_status)
        incoming = self._normalize_status(incoming_status)
        if incoming == "PENDING" and existing and existing != "PENDING":
            return existing
        return incoming or existing

    async def _replace_take_profit_levels(
        self,
        session: AsyncSession,
        signal_id: str,
        take_profit_levels: List[Dict[str, str]],
    ) -> None:
        await session.execute(
            delete(PGSignalTakeProfitORM).where(
                PGSignalTakeProfitORM.signal_id == signal_id
            )
        )
        for tp in take_profit_levels:
            session.add(
                PGSignalTakeProfitORM(
                    signal_id=signal_id,
                    tp_id=tp["id"],
                    position_ratio=Decimal(str(tp["position_ratio"])),
                    risk_reward=Decimal(str(tp["risk_reward"])),
                    price_level=Decimal(str(tp["price"])),
                    status="PENDING",
                )
            )

    async def update_signal_status_by_tracker_id(self, signal_id: str, status: str) -> None:
        async with self._session_maker() as session:
            stmt = select(PGSignalORM).where(PGSignalORM.signal_id == signal_id)
            orm = (await session.execute(stmt)).scalar_one_or_none()
            if orm is None:
                return
            orm.status = self._normalize_status(status) or orm.status
            await session.commit()

    async def update_superseded_by(self, signal_id: str, superseded_by: str) -> None:
        async with self._session_maker() as session:
            stmt = select(PGSignalORM).where(PGSignalORM.signal_id == signal_id)
            orm = (await session.execute(stmt)).scalar_one_or_none()
            if orm is None:
                return
            orm.superseded_by = superseded_by
            orm.status = "SUPERSEDED"
            await session.commit()

    async def get_active_signal(self, dedup_key: str) -> Optional[dict]:
        parts = dedup_key.split(":")
        if len(parts) < 4:
            return None
        strategy_name = parts[-1]
        direction = Direction.normalize(parts[-2])
        timeframe = parts[-3]
        symbol = ":".join(parts[:-3])

        async with self._session_maker() as session:
            stmt = (
                select(PGSignalORM)
                .where(
                    PGSignalORM.symbol == symbol,
                    PGSignalORM.timeframe == timeframe,
                    PGSignalORM.direction == direction,
                    PGSignalORM.status.in_(["ACTIVE", "active"]),
                )
                .order_by(PGSignalORM.created_at.desc())
                .limit(1)
            )
            if strategy_name:
                stmt = stmt.where(PGSignalORM.strategy_name == strategy_name)
            orm = (await session.execute(stmt)).scalar_one_or_none()
            return await self._to_dict_with_tp(session, orm) if orm else None

    async def get_opposing_signal(self, symbol: str, timeframe: str, direction: str) -> Optional[dict]:
        normalized_direction = Direction.normalize(direction)
        opposing_direction = "SHORT" if normalized_direction == "LONG" else "LONG"
        async with self._session_maker() as session:
            stmt = (
                select(PGSignalORM)
                .where(
                    PGSignalORM.symbol == symbol,
                    PGSignalORM.timeframe == timeframe,
                    PGSignalORM.direction == opposing_direction,
                    PGSignalORM.status.in_(["ACTIVE", "active"]),
                )
                .order_by(PGSignalORM.created_at.desc())
                .limit(1)
            )
            orm = (await session.execute(stmt)).scalar_one_or_none()
            return await self._to_dict_with_tp(session, orm) if orm else None

    async def get_signal_by_tracker_id(self, signal_id: str) -> Optional[dict]:
        async with self._session_maker() as session:
            stmt = select(PGSignalORM).where(PGSignalORM.signal_id == signal_id)
            orm = (await session.execute(stmt)).scalar_one_or_none()
            return await self._to_dict_with_tp(session, orm) if orm else None

    async def list_active_signals_for_cache_rebuild(self) -> List[dict]:
        async with self._session_maker() as session:
            stmt = (
                select(PGSignalORM)
                .where(PGSignalORM.status.in_(["ACTIVE", "active", "PENDING", "pending"]))
                .order_by(PGSignalORM.created_at.desc())
            )
            result = await session.execute(stmt)
            return [self._to_plain_dict(orm) for orm in result.scalars().all()]

    async def get_signals(
        self,
        query: SignalQuery = None,
        limit: int = 50,
        offset: int = 0,
        symbol: str = None,
        timeframe: str = None,
        direction: str = None,
        strategy_name: str = None,
        status: str = None,
        start_time: str = None,
        end_time: str = None,
        sort_by: str = "created_at",
        order: str = "desc",
        source: str = None,
    ) -> dict:
        if query:
            limit = query.limit
            offset = query.offset
            symbol = query.symbol
            direction = query.direction
            strategy_name = query.strategy_name
            status = query.status
            start_time = query.start_time
            end_time = query.end_time
            source = query.source

        direction = Direction.normalize(direction) if direction else None
        status = self._normalize_status(status) if status else None

        filters = []
        if symbol:
            filters.append(PGSignalORM.symbol == symbol)
        if timeframe:
            filters.append(PGSignalORM.timeframe == timeframe)
        if direction:
            filters.append(PGSignalORM.direction == direction)
        if strategy_name:
            filters.append(PGSignalORM.strategy_name == strategy_name)
        if status:
            filters.append(PGSignalORM.status == status)
        if start_time:
            filters.append(PGSignalORM.created_at >= start_time)
        if end_time:
            filters.append(PGSignalORM.created_at <= end_time)
        if source:
            filters.append(PGSignalORM.source == source)

        sort_column = PGSignalORM.created_at if sort_by != "pattern_score" else PGSignalORM.pattern_score
        sort_column = sort_column.desc() if order.lower() == "desc" else sort_column.asc()

        async with self._session_maker() as session:
            count_stmt = select(func.count()).select_from(PGSignalORM)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = (await session.execute(count_stmt)).scalar_one()

            stmt = select(PGSignalORM)
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.order_by(sort_column).limit(limit).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()

            data = []
            for orm in rows:
                data.append(await self._to_dict_with_tp(session, orm, normalize_status=True))
            return {"total": total, "data": data}

    async def delete_signals(
        self,
        request: SignalDeleteRequest = None,
        ids: list = None,
        delete_all: bool = False,
        symbol: str = None,
        direction: str = None,
        strategy_name: str = None,
        status: str = None,
        start_time: str = None,
        end_time: str = None,
        source: str = None,
    ) -> int:
        if request:
            ids = request.ids
            delete_all = request.delete_all
            symbol = request.symbol
            direction = request.direction
            strategy_name = request.strategy_name
            status = request.status
            start_time = request.start_time
            end_time = request.end_time
            source = request.source

        if source == "backtest":
            return 0

        direction = Direction.normalize(direction) if direction else None
        status = self._normalize_status(status) if status else None

        async with self._session_maker() as session:
            if ids:
                result = await session.execute(delete(PGSignalORM).where(PGSignalORM.id.in_(ids)))
                await session.commit()
                return result.rowcount or 0
            if not delete_all:
                return 0

            stmt = delete(PGSignalORM)
            filters = []
            if symbol:
                filters.append(PGSignalORM.symbol == symbol)
            if direction:
                filters.append(PGSignalORM.direction == direction)
            if strategy_name:
                filters.append(PGSignalORM.strategy_name == strategy_name)
            if status:
                filters.append(PGSignalORM.status == status)
            if start_time:
                filters.append(PGSignalORM.created_at >= start_time)
            if end_time:
                filters.append(PGSignalORM.created_at <= end_time)
            if filters:
                stmt = stmt.where(*filters)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0

    async def clear_all_signals(self) -> int:
        async with self._session_maker() as session:
            result = await session.execute(delete(PGSignalORM))
            await session.commit()
            return result.rowcount or 0

    async def save_attempt(self, attempt, symbol: str, timeframe: str, config_version: str = None) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        direction = attempt.pattern.direction.value if attempt.pattern else None
        pattern_score = float(attempt.pattern.score) if attempt.pattern else None
        final_result = attempt.final_result
        kline_timestamp = attempt.kline_timestamp

        filter_stage = None
        filter_reason = None
        for filter_name, filter_result in attempt.filter_results:
            if not filter_result.passed:
                filter_stage = filter_name
                filter_reason = filter_result.reason
                break

        details = {
            "pattern": attempt.pattern.details if attempt.pattern else None,
            "filters": [
                {"name": name, "passed": result.passed, "reason": result.reason}
                for name, result in attempt.filter_results
            ],
        }
        trace_tree = self._build_trace_tree(attempt)
        evaluation_summary = self._generate_evaluation_summary(attempt, symbol, timeframe)

        async with self._session_maker() as session:
            session.add(
                PGSignalAttemptORM(
                    created_at=created_at,
                    symbol=symbol,
                    timeframe=timeframe,
                    strategy_name=attempt.strategy_name,
                    direction=direction,
                    pattern_score=Decimal(str(pattern_score)) if pattern_score is not None else None,
                    final_result=final_result,
                    filter_stage=filter_stage,
                    filter_reason=filter_reason,
                    details=self._json_safe(details),
                    kline_timestamp=kline_timestamp,
                    evaluation_summary=evaluation_summary,
                    trace_tree=self._json_safe(trace_tree),
                    config_version=config_version,
                )
            )
            await session.commit()

    async def get_diagnostics(self, symbol: str = None, hours: int = 24) -> dict:
        from datetime import timedelta

        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        filters = [PGSignalAttemptORM.created_at >= since]
        if symbol:
            filters.append(PGSignalAttemptORM.symbol == symbol)

        async with self._session_maker() as session:
            total_klines = int((await session.execute(
                select(func.count()).select_from(PGSignalAttemptORM).where(*filters)
            )).scalar_one())
            no_pattern = int((await session.execute(
                select(func.count()).select_from(PGSignalAttemptORM).where(
                    *filters,
                    PGSignalAttemptORM.final_result == "NO_PATTERN",
                )
            )).scalar_one())
            signal_fired = int((await session.execute(
                select(func.count()).select_from(PGSignalAttemptORM).where(
                    *filters,
                    PGSignalAttemptORM.final_result == "SIGNAL_FIRED",
                )
            )).scalar_one())
            filtered = int((await session.execute(
                select(func.count()).select_from(PGSignalAttemptORM).where(
                    *filters,
                    PGSignalAttemptORM.final_result == "FILTERED",
                )
            )).scalar_one())
            breakdown_rows = (await session.execute(
                select(PGSignalAttemptORM.filter_stage, func.count())
                .where(*filters, PGSignalAttemptORM.final_result == "FILTERED")
                .group_by(PGSignalAttemptORM.filter_stage)
            )).all()
            recent_rows = (await session.execute(
                select(PGSignalAttemptORM)
                .where(*filters)
                .order_by(PGSignalAttemptORM.created_at.desc())
                .limit(20)
            )).scalars().all()

        return {
            "summary": {
                "total_klines": total_klines,
                "no_pattern": no_pattern,
                "signal_fired": signal_fired,
                "filtered": filtered,
                "filter_breakdown": {stage: count for stage, count in breakdown_rows if stage},
            },
            "recent_attempts": [self._attempt_to_dict(row) for row in recent_rows],
        }

    async def get_attempts(
        self,
        query: AttemptQuery = None,
        limit: int = 50,
        offset: int = 0,
        symbol: str = None,
        timeframe: str = None,
        strategy_name: str = None,
        final_result: str = None,
        filter_stage: str = None,
        start_time: str = None,
        end_time: str = None,
    ) -> dict:
        if query:
            limit = query.limit
            offset = query.offset
            symbol = query.symbol
            timeframe = query.timeframe
            strategy_name = query.strategy_name
            final_result = query.final_result
            filter_stage = query.filter_stage
            start_time = query.start_time
            end_time = query.end_time

        filters = []
        if symbol:
            filters.append(PGSignalAttemptORM.symbol == symbol)
        if timeframe:
            filters.append(PGSignalAttemptORM.timeframe == timeframe)
        if strategy_name:
            filters.append(PGSignalAttemptORM.strategy_name == strategy_name)
        if final_result:
            filters.append(PGSignalAttemptORM.final_result == final_result)
        if filter_stage:
            filters.append(PGSignalAttemptORM.filter_stage == filter_stage)
        if start_time:
            filters.append(PGSignalAttemptORM.created_at >= start_time)
        if end_time:
            filters.append(PGSignalAttemptORM.created_at <= end_time)

        async with self._session_maker() as session:
            count_stmt = select(func.count()).select_from(PGSignalAttemptORM)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = int((await session.execute(count_stmt)).scalar_one())

            stmt = select(PGSignalAttemptORM)
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.order_by(PGSignalAttemptORM.created_at.desc()).limit(limit).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()
            return {"total": total, "data": [self._attempt_to_dict(row) for row in rows]}

    async def delete_attempts(
        self,
        request: AttemptDeleteRequest = None,
        ids: list = None,
        delete_all: bool = False,
        symbol: str = None,
        timeframe: str = None,
        strategy_name: str = None,
        final_result: str = None,
        filter_stage: str = None,
        start_time: str = None,
        end_time: str = None,
    ) -> int:
        if request:
            ids = request.ids
            delete_all = request.delete_all
            symbol = request.symbol
            timeframe = request.timeframe
            strategy_name = request.strategy_name
            final_result = request.final_result
            filter_stage = request.filter_stage
            start_time = request.start_time
            end_time = request.end_time

        async with self._session_maker() as session:
            if ids:
                result = await session.execute(delete(PGSignalAttemptORM).where(PGSignalAttemptORM.id.in_(ids)))
                await session.commit()
                return result.rowcount or 0
            if not delete_all:
                return 0

            stmt = delete(PGSignalAttemptORM)
            filters = []
            if symbol:
                filters.append(PGSignalAttemptORM.symbol == symbol)
            if timeframe:
                filters.append(PGSignalAttemptORM.timeframe == timeframe)
            if strategy_name:
                filters.append(PGSignalAttemptORM.strategy_name == strategy_name)
            if final_result:
                filters.append(PGSignalAttemptORM.final_result == final_result)
            if filter_stage:
                filters.append(PGSignalAttemptORM.filter_stage == filter_stage)
            if start_time:
                filters.append(PGSignalAttemptORM.created_at >= start_time)
            if end_time:
                filters.append(PGSignalAttemptORM.created_at <= end_time)
            if filters:
                stmt = stmt.where(*filters)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0

    async def clear_all_attempts(self) -> int:
        async with self._session_maker() as session:
            result = await session.execute(delete(PGSignalAttemptORM))
            await session.commit()
            return result.rowcount or 0

    async def get_signal_by_id(self, signal_id: int) -> Optional[dict]:
        async with self._session_maker() as session:
            orm = await session.get(PGSignalORM, signal_id)
            return await self._to_dict_with_tp(session, orm) if orm else None

    async def get_stats(self) -> dict:
        async with self._session_maker() as session:
            total = (await session.execute(select(func.count()).select_from(PGSignalORM))).scalar_one()
            today = datetime.now(timezone.utc).date().isoformat()
            today_count = (
                await session.execute(
                    select(func.count()).select_from(PGSignalORM).where(PGSignalORM.created_at.like(f"{today}%"))
                )
            ).scalar_one()
            long_count = (
                await session.execute(
                    select(func.count()).select_from(PGSignalORM).where(PGSignalORM.direction == "LONG")
                )
            ).scalar_one()
            short_count = (
                await session.execute(
                    select(func.count()).select_from(PGSignalORM).where(PGSignalORM.direction == "SHORT")
                )
            ).scalar_one()
            won_count = (
                await session.execute(
                    select(func.count()).select_from(PGSignalORM).where(PGSignalORM.status == "WON")
                )
            ).scalar_one()
            lost_count = (
                await session.execute(
                    select(func.count()).select_from(PGSignalORM).where(PGSignalORM.status == "LOST")
                )
            ).scalar_one()
            closed_count = won_count + lost_count
            return {
                "total": total,
                "today": today_count,
                "long_count": long_count,
                "short_count": short_count,
                "win_rate": (won_count / closed_count) if closed_count > 0 else 0.0,
                "won_count": won_count,
                "lost_count": lost_count,
            }

    async def get_signal_ids_by_backtest_report(
        self,
        strategy_id: str,
        start_time: int,
        end_time: int,
    ) -> list[str]:
        """Return backtest signal IDs for a strategy and time range."""
        start_iso = datetime.fromtimestamp(start_time / 1000, tz=timezone.utc).isoformat()
        end_iso = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc).isoformat()
        async with self._session_maker() as session:
            stmt = (
                select(PGSignalORM.signal_id)
                .where(
                    PGSignalORM.source == "backtest",
                    PGSignalORM.strategy_name == strategy_id,
                    PGSignalORM.created_at >= start_iso,
                    PGSignalORM.created_at <= end_iso,
                )
                .order_by(PGSignalORM.created_at.asc())
            )
            return [signal_id for signal_id in (await session.execute(stmt)).scalars().all() if signal_id]

    async def get_pending_signals(self, symbol: str) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = (
                select(PGSignalORM)
                .where(PGSignalORM.symbol == symbol, PGSignalORM.status == "PENDING")
                .order_by(PGSignalORM.created_at.desc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "id": orm.id,
                    "symbol": orm.symbol,
                    "timeframe": orm.timeframe,
                    "direction": orm.direction,
                    "entry_price": orm.entry_price,
                    "stop_loss": orm.stop_loss,
                    "take_profit_1": orm.take_profit_1,
                }
                for orm in rows
            ]

    async def update_signal_status(
        self,
        signal_id: int,
        status: str,
        pnl_ratio: Optional[Decimal] = None,
    ) -> None:
        async with self._session_maker() as session:
            orm = await session.get(PGSignalORM, signal_id)
            if orm is None:
                return
            orm.status = status
            orm.closed_at = datetime.now(timezone.utc).isoformat()
            orm.pnl_ratio = pnl_ratio
            await session.commit()

    async def store_take_profit_levels(
        self,
        signal_id: str,
        take_profit_levels: List[Dict[str, str]],
    ) -> None:
        async with self._session_maker() as session:
            await session.execute(
                delete(PGSignalTakeProfitORM).where(PGSignalTakeProfitORM.signal_id == signal_id)
            )
            for tp in take_profit_levels:
                session.add(
                    PGSignalTakeProfitORM(
                        signal_id=signal_id,
                        tp_id=tp["id"],
                        position_ratio=Decimal(str(tp["position_ratio"])),
                        risk_reward=Decimal(str(tp["risk_reward"])),
                        price_level=Decimal(str(tp["price"])),
                        status="PENDING",
                    )
                )
            await session.commit()

    async def get_take_profit_levels(self, signal_id: str) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = (
                select(PGSignalTakeProfitORM)
                .where(PGSignalTakeProfitORM.signal_id == signal_id)
                .order_by(PGSignalTakeProfitORM.tp_id.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "id": row.id,
                    "tp_id": row.tp_id,
                    "position_ratio": str(row.position_ratio),
                    "risk_reward": str(row.risk_reward),
                    "price_level": str(row.price_level),
                    "status": row.status,
                    "filled_at": row.filled_at,
                    "pnl_ratio": str(row.pnl_ratio) if row.pnl_ratio is not None else None,
                }
                for row in rows
            ]

    def _generate_evaluation_summary(self, attempt, symbol: str, timeframe: str) -> str:
        lines = [
            "=== 信号评估报告 ===",
            f"币种：{symbol}",
            f"周期：{timeframe}",
            f"策略：{attempt.strategy_name}",
            "",
            "【评估结果】",
        ]
        if attempt.final_result == "SIGNAL_FIRED":
            direction = attempt.pattern.direction if attempt.pattern else None
            direction_str = "看涨" if direction == "LONG" else "看跌" if direction == "SHORT" else "未知"
            lines.append(f"最终结果：信号触发 ({direction_str})")
        elif attempt.final_result == "NO_PATTERN":
            lines.append("最终结果：未检测到有效形态")
        elif attempt.final_result == "FILTERED":
            lines.append("最终结果：信号被过滤器拦截")
        else:
            lines.append(f"最终结果：{attempt.final_result}")
        return "\n".join(lines)

    def _build_trace_tree(self, attempt) -> dict:
        import uuid

        root = {
            "node_id": str(uuid.uuid4()),
            "node_type": "and_gate",
            "passed": attempt.final_result == "SIGNAL_FIRED",
            "reason": "all_conditions_met" if attempt.final_result == "SIGNAL_FIRED" else "condition_failed",
            "metadata": {
                "strategy_name": attempt.strategy_name,
                "final_result": attempt.final_result,
            },
            "children": [],
        }

        if attempt.pattern:
            root["children"].append({
                "node_id": str(uuid.uuid4()),
                "node_type": "trigger",
                "passed": True,
                "reason": "pattern_detected",
                "metadata": {
                    "trigger_type": attempt.pattern.strategy_name,
                    "direction": attempt.pattern.direction.value if hasattr(attempt.pattern.direction, "value") else attempt.pattern.direction,
                    "score": attempt.pattern.score,
                    "details": attempt.pattern.details,
                },
                "children": [],
            })
        else:
            root["children"].append({
                "node_id": str(uuid.uuid4()),
                "node_type": "trigger",
                "passed": False,
                "reason": "no_pattern_detected",
                "metadata": {"trigger_type": attempt.strategy_name},
                "children": [],
            })

        for filter_name, filter_result in attempt.filter_results:
            root["children"].append({
                "node_id": str(uuid.uuid4()),
                "node_type": "filter",
                "passed": filter_result.passed,
                "reason": filter_result.reason,
                "metadata": {
                    "filter_name": filter_name,
                    "filter_type": filter_name,
                },
                "children": [],
            })
        return root

    def _attempt_to_dict(self, orm: PGSignalAttemptORM) -> dict:
        return {
            "id": orm.id,
            "created_at": orm.created_at,
            "symbol": orm.symbol,
            "timeframe": orm.timeframe,
            "strategy_name": orm.strategy_name,
            "direction": orm.direction,
            "pattern_score": float(orm.pattern_score) if orm.pattern_score is not None else None,
            "final_result": orm.final_result,
            "filter_stage": orm.filter_stage,
            "filter_reason": orm.filter_reason,
            "details": orm.details,
            "kline_timestamp": orm.kline_timestamp,
            "evaluation_summary": orm.evaluation_summary,
            "trace_tree": orm.trace_tree,
            "config_version": orm.config_version,
        }

    def _to_plain_dict(self, orm: PGSignalORM, *, normalize_status: bool = False) -> dict:
        data = {
            "id": orm.id,
            "created_at": orm.created_at,
            "symbol": orm.symbol,
            "timeframe": orm.timeframe,
            "direction": orm.direction,
            "entry_price": str(orm.entry_price),
            "stop_loss": str(orm.stop_loss),
            "position_size": str(orm.position_size),
            "leverage": orm.leverage,
            "tags_json": orm.tags_json,
            "risk_info": orm.risk_info,
            "status": orm.status.lower() if normalize_status and orm.status else orm.status,
            "take_profit_1": str(orm.take_profit_1) if orm.take_profit_1 is not None else None,
            "closed_at": orm.closed_at,
            "pnl_ratio": str(orm.pnl_ratio) if orm.pnl_ratio is not None else None,
            "kline_timestamp": orm.kline_timestamp,
            "strategy_name": orm.strategy_name,
            "score": float(orm.score) if orm.score is not None else 0.0,
            "signal_id": orm.signal_id,
            "source": orm.source,
            "pattern_score": float(orm.pattern_score) if orm.pattern_score is not None else None,
            "ema_trend": orm.ema_trend,
            "mtf_status": orm.mtf_status,
            "superseded_by": orm.superseded_by,
            "opposing_signal_id": orm.opposing_signal_id,
            "opposing_signal_score": float(orm.opposing_signal_score) if orm.opposing_signal_score is not None else None,
        }
        return data

    async def _to_dict_with_tp(
        self,
        session: AsyncSession,
        orm: Optional[PGSignalORM],
        *,
        normalize_status: bool = False,
    ) -> Optional[dict]:
        if orm is None:
            return None
        data = self._to_plain_dict(orm, normalize_status=normalize_status)
        stmt = (
            select(PGSignalTakeProfitORM)
            .where(PGSignalTakeProfitORM.signal_id == orm.signal_id)
            .order_by(PGSignalTakeProfitORM.tp_id.asc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        data["take_profit_levels"] = [
            {
                "id": row.id,
                "tp_id": row.tp_id,
                "position_ratio": str(row.position_ratio),
                "risk_reward": str(row.risk_reward),
                "price_level": str(row.price_level),
                "status": row.status,
                "filled_at": row.filled_at,
                "pnl_ratio": str(row.pnl_ratio) if row.pnl_ratio is not None else None,
            }
            for row in rows
        ]
        return data
