"""
HistoricalDataRepository - 历史数据仓库

实现本地 SQLite 优先 + CCXT 自动补充的数据获取机制。

核心功能:
1. get_klines() - 获取 K 线数据（本地优先）
2. get_klines_aligned() - 获取对齐的多周期数据 (MTF)
3. _save_klines() - 保存 K 线到本地 (幂等性：INSERT OR IGNORE)

技术栈:
- SQLAlchemy 2.0 async
- SQLite + aiosqlite
- 降级策略：本地数据不足时自动从 CCXT 补充
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.domain.models import KlineData
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.v3_orm import KlineORM, Base
from src.infrastructure.logger import logger


class HistoricalDataRepository:
    """
    历史数据仓库 - 统一数据源访问

    数据获取策略:
    1. 优先从本地 SQLite 读取
    2. 本地数据不足时，自动从 CCXT 补充
    3. 补充的数据自动保存到 SQLite (幂等性写入)

    使用示例:
        >>> repo = HistoricalDataRepository(
        ...     db_path="data/v3_dev.db",
        ...     exchange_gateway=gateway
        ... )
        >>> klines = await repo.get_klines(
        ...     symbol="BTC/USDT:USDT",
        ...     timeframe="15m",
        ...     start_time=1704067200000,
        ...     end_time=1706745600000,
        ... )
    """

    # 时间框架映射 (用于 MTF 对齐)
    TIMEFRAME_MINUTES = {
        "1m": 1,
        "3m": 3,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "6h": 360,
        "12h": 720,
        "1d": 1440,
        "1w": 10080,
    }

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        exchange_gateway: Optional[ExchangeGateway] = None,
    ):
        """
        初始化数据仓库

        Args:
            db_path: SQLite 数据库路径
            exchange_gateway: 交易所网关（用于数据补充）
        """
        self.db_path = db_path
        self._gateway = exchange_gateway

        # 确保数据库目录存在
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        # 初始化异步数据库引擎
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
            future=True,
        )

        # 异步 Session 工厂
        self._async_session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # 信号量：限制并发数据库操作
        self._semaphore = asyncio.Semaphore(5)

    async def initialize(self):
        """初始化数据库表（创建索引等）"""
        async with self._engine.begin() as conn:
            # 创建表
            await conn.run_sync(Base.metadata.create_all)

            # 创建索引
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_klines_symbol_tf_ts "
                "ON klines(symbol, timeframe, timestamp)"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_klines_symbol_timeframe_timestamp "
                "ON klines(symbol, timeframe, timestamp)"
            ))

        logger.info(f"HistoricalDataRepository initialized: {self.db_path}")

    async def close(self):
        """关闭数据库连接"""
        await self._engine.dispose()
        logger.info("HistoricalDataRepository connection closed")

    async def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> List[KlineData]:
        """
        获取 K 线数据（本地优先）

        数据获取策略:
        1. 首先从 SQLite 查询指定时间范围的数据
        2. 如果数据不足且提供了 exchange_gateway，自动从交易所补充
        3. 补充的数据自动保存到 SQLite

        Args:
            symbol: 交易对 (e.g., "BTC/USDT:USDT")
            timeframe: 时间周期 (e.g., "15m", "1h")
            start_time: 开始时间戳 (毫秒)
            end_time: 结束时间戳 (毫秒)
            limit: 最多返回的 K 线数量

        Returns:
            List[KlineData]: K 线数据列表，按时间升序排列
        """
        async with self._semaphore:
            async with self._async_session_factory() as session:
                # Step 1: 从 SQLite 查询
                klines = await self._query_klines_from_db(
                    session, symbol, timeframe, start_time, end_time, limit
                )

                logger.debug(
                    f"Queried {len(klines)} klines from DB for {symbol} {timeframe} "
                    f"(range: {start_time} - {end_time})"
                )

                # Step 2: 检查是否需要补充数据
                need_fallback = (
                    self._gateway is not None and
                    (
                        # 没有数据
                        len(klines) == 0 or
                        # 数据不足且指定了时间范围
                        (start_time and end_time and len(klines) < limit) or
                        # 数据不足且没有指定时间范围（默认请求）
                        (not start_time and not end_time and len(klines) < limit)
                    )
                )

                if need_fallback:
                    logger.debug(
                        f"Local data insufficient ({len(klines)} < {limit}), "
                        f"fetching from exchange for {symbol} {timeframe}..."
                    )

                    # 计算需要从交易所获取的时间范围
                    fallback_start = start_time
                    fallback_end = end_time

                    # 如果已有部分数据，只需要补充缺失的部分
                    if klines and start_time and end_time:
                        # 找出已有数据的时间范围
                        existing_min_ts = min(k.timestamp for k in klines)
                        existing_max_ts = max(k.timestamp for k in klines)

                        # 需要补充的范围：start_time 到 existing_min_ts 之前的部分
                        # 以及 existing_max_ts 到 end_time 之后的部分
                        if existing_min_ts > start_time:
                            # 补充前半部分
                            partial_klines = await self._fetch_from_exchange(
                                symbol, timeframe, start_time, existing_min_ts - 1, limit
                            )
                            klines = partial_klines + klines
                            klines = klines[:limit]  # 保持 limit 限制
                            logger.debug(f"Supplemented {len(partial_klines)} klines from exchange (before) for {symbol} {timeframe}")

                        if existing_max_ts < end_time and len(klines) < limit:
                            # 补充后半部分
                            remaining_limit = limit - len(klines)
                            partial_klines = await self._fetch_from_exchange(
                                symbol, timeframe, existing_max_ts + 1, end_time, remaining_limit
                            )
                            klines = klines + partial_klines
                            klines = klines[:limit]  # 保持 limit 限制
                            logger.debug(f"Supplemented {len(partial_klines)} klines from exchange (after) for {symbol} {timeframe}")
                    else:
                        # 没有本地数据，直接获取
                        klines = await self._fetch_from_exchange(
                            symbol, timeframe, start_time, end_time, limit
                        )

                # 按时间戳升序排序
                klines.sort(key=lambda k: k.timestamp)

                return klines

    async def _query_klines_from_db(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str,
        start_time: Optional[int],
        end_time: Optional[int],
        limit: int,
    ) -> List[KlineData]:
        """从 SQLite 查询 K 线数据"""
        # 构建查询条件
        conditions = [
            KlineORM.symbol == symbol,
            KlineORM.timeframe == timeframe,
        ]

        if start_time:
            conditions.append(KlineORM.timestamp >= start_time)
        if end_time:
            conditions.append(KlineORM.timestamp <= end_time)

        # 执行查询
        query = select(KlineORM).where(*conditions).order_by(KlineORM.timestamp.asc()).limit(limit)

        result = await session.execute(query)
        orm_records = result.scalars().all()

        # 转换为领域模型
        return [self._orm_to_domain(orm) for orm in orm_records]

    async def _fetch_from_exchange(
        self,
        symbol: str,
        timeframe: str,
        start_time: Optional[int],
        end_time: Optional[int],
        limit: int,
    ) -> List[KlineData]:
        """
        从交易所获取 K 线数据并保存到本地

        Args:
            symbol: 交易对
            timeframe: 时间周期
            start_time: 开始时间戳
            end_time: 结束时间戳
            limit: 最多获取的数量

        Returns:
            List[KlineData]: 获取到的 K 线数据
        """
        if self._gateway is None:
            logger.warning("No exchange gateway configured, cannot fetch from exchange")
            return []

        # 从交易所获取
        klines = await self._gateway.fetch_historical_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )

        # 按时间范围过滤
        if start_time and end_time:
            klines = [k for k in klines if start_time <= k.timestamp <= end_time]
        elif start_time:
            klines = [k for k in klines if k.timestamp >= start_time]
        elif end_time:
            klines = [k for k in klines if k.timestamp <= end_time]

        # 保存到本地
        if klines:
            await self._save_klines(klines)
            logger.debug(f"Saved {len(klines)} klines to local DB for {symbol} {timeframe}")

        return klines

    async def _save_klines(self, klines: List[KlineData]) -> None:
        """
        保存 K 线数据到 SQLite（幂等性：INSERT OR IGNORE）

        Args:
            klines: K 线数据列表
        """
        if not klines:
            return

        from sqlalchemy.dialects.sqlite import insert

        async with self._async_session_factory() as session:
            # 批量插入数据
            for kline in klines:
                stmt = insert(KlineORM).values(
                    symbol=kline.symbol,
                    timeframe=kline.timeframe,
                    timestamp=kline.timestamp,
                    open=kline.open,
                    high=kline.high,
                    low=kline.low,
                    close=kline.close,
                    volume=kline.volume,
                    is_closed=kline.is_closed,
                ).on_conflict_do_nothing(
                    index_elements=['symbol', 'timeframe', 'timestamp']
                )
                await session.execute(stmt)

            await session.commit()

        logger.debug(f"Saved {len(klines)} klines to DB")

    async def get_klines_aligned(
        self,
        symbol: str,
        main_tf: str,
        higher_tf: str,
        start_time: int,
        end_time: int,
    ) -> Tuple[List[KlineData], Dict[int, KlineData]]:
        """
        获取对齐的多周期数据 (MTF 专用)

        返回主周期 K 线和高层周期 K 线的映射关系，用于策略回测。

        Args:
            symbol: 交易对
            main_tf: 主周期 (e.g., "15m")
            higher_tf: 高层周期 (e.g., "1h")
            start_time: 开始时间戳
            end_time: 结束时间戳

        Returns:
            Tuple:
                - List[KlineData]: 主周期 K 线列表
                - Dict[int, KlineData]: {主周期 K 线时间戳：对应的高层周期 K 线}
        """
        # 并行获取两个周期的数据
        main_klines, higher_klines = await asyncio.gather(
            self.get_klines(symbol, main_tf, start_time, end_time, limit=5000),
            self.get_klines(symbol, higher_tf, start_time, end_time, limit=5000),
        )

        # 构建高层周期 K 线的映射
        higher_tf_map = {k.timestamp: k for k in higher_klines}

        # 为主周期每个 K 线找到对应的高层周期 K 线
        aligned_higher = {}

        for main_k in main_klines:
            # 找到 main_k.timestamp 所属的高层周期 K 线
            # 高层周期 K 线的开盘时间 <= main_k.timestamp
            matching_higher = None

            for higher_ts in sorted(higher_tf_map.keys(), reverse=True):
                if higher_ts <= main_k.timestamp:
                    matching_higher = higher_tf_map[higher_ts]
                    break

            if matching_higher:
                aligned_higher[main_k.timestamp] = matching_higher

        logger.info(
            f"Aligned {len(main_klines)} {main_tf} klines with "
            f"{len(aligned_higher)} {higher_tf} klines"
        )

        return main_klines, aligned_higher

    def _orm_to_domain(self, orm: KlineORM) -> KlineData:
        """ORM 模型转换为领域模型"""
        return KlineData(
            symbol=orm.symbol,
            timeframe=orm.timeframe,
            timestamp=orm.timestamp,
            open=orm.open,
            high=orm.high,
            low=orm.low,
            close=orm.close,
            volume=orm.volume,
            is_closed=orm.is_closed,
        )

    def _domain_to_orm(self, domain: KlineData) -> KlineORM:
        """领域模型转换为 ORM 模型"""
        return KlineORM(
            symbol=domain.symbol,
            timeframe=domain.timeframe,
            timestamp=domain.timestamp,
            open=domain.open,
            high=domain.high,
            low=domain.low,
            close=domain.close,
            volume=domain.volume,
            is_closed=domain.is_closed,
        )

    async def get_kline_range(
        self,
        symbol: str,
        timeframe: str,
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        获取某交易对某周期在数据库中的时间范围

        Args:
            symbol: 交易对
            timeframe: 时间周期

        Returns:
            Tuple: (min_timestamp, max_timestamp)
        """
        async with self._async_session_factory() as session:
            result = await session.execute(
                select(
                    func.min(KlineORM.timestamp),
                    func.max(KlineORM.timestamp),
                ).where(
                    KlineORM.symbol == symbol,
                    KlineORM.timeframe == timeframe,
                )
            )

            row = result.first()
            if row:
                return row[0], row[1]
            return None, None

    async def count_klines(
        self,
        symbol: str,
        timeframe: str,
    ) -> int:
        """
        统计某交易对某周期的 K 线数量

        Args:
            symbol: 交易对
            timeframe: 时间周期

        Returns:
            int: K 线数量
        """
        async with self._async_session_factory() as session:
            result = await session.execute(
                select(func.count(KlineORM.id)).where(
                    KlineORM.symbol == symbol,
                    KlineORM.timeframe == timeframe,
                )
            )

            return result.scalar() or 0
