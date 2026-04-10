"""
全局 SQLite 连接池

按 db_path 分组管理连接，同一路径的 Repository 共享同一连接实例。

设计目标:
- 消除 17 处独立的 aiosqlite.connect() 调用
- 同路径 Repository 共享连接，减少锁竞争
- 向后兼容：不传 connection 时 Repository 仍能独立工作
- 线程安全：延迟创建 Lock，避免事件循环绑定问题

使用方式:
    # 方式 1: Repository 自行管理（向后兼容）
    repo = StrategyConfigRepository(db_path="data/v3_dev.db")
    await repo.initialize()  # 自行创建连接

    # 方式 2: 通过连接池注入（推荐）
    from src.infrastructure.connection_pool import get_connection
    conn = await get_connection("data/v3_dev.db")
    repo = StrategyConfigRepository(db_path="data/v3_dev.db", connection=conn)
    await repo.initialize()  # 跳过连接创建，仅建表
"""
import asyncio
import logging
from typing import Dict, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class ConnectionPool:
    """全局 SQLite 连接池（单例模式）

    按 db_path 分组管理连接，同一 db_path 的调用者共享同一连接。

    线程安全:
    - _lock 延迟创建，避免在 import 时绑定到错误的事件循环
    - 使用双重检查锁定模式保证并发安全

    PRAGMA 优化:
    - WAL 模式：支持读写并发
    - synchronous=NORMAL：性能与安全的平衡
    - wal_autocheckpoint=1000：每 1000 页检查点
    - cache_size=-64000：64MB 缓存
    """

    _instance: Optional['ConnectionPool'] = None
    _initialized: bool = False

    def __init__(self) -> None:
        self._connections: Dict[str, aiosqlite.Connection] = {}
        self._lock: Optional[asyncio.Lock] = None  # 延迟创建，避免事件循环问题

    def _get_lock(self) -> asyncio.Lock:
        """延迟创建锁，确保在正确的事件循环中"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def get_connection(self, db_path: str) -> aiosqlite.Connection:
        """获取指定数据库的连接（如不存在则创建）

        Args:
            db_path: SQLite 数据库文件路径

        Returns:
            aiosqlite.Connection 实例
        """
        if db_path in self._connections:
            return self._connections[db_path]

        async with self._get_lock():
            # Double-check after acquiring lock
            if db_path in self._connections:
                return self._connections[db_path]

            logger.info(f"创建新的 SQLite 连接: {db_path}")
            conn = await aiosqlite.connect(db_path)
            conn.row_factory = aiosqlite.Row

            # 优化设置
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA wal_autocheckpoint=1000")
            await conn.execute("PRAGMA cache_size=-64000")  # 64MB cache

            self._connections[db_path] = conn
            return conn

    async def close_all(self) -> None:
        """关闭所有连接"""
        async with self._get_lock():
            for db_path, conn in list(self._connections.items()):
                try:
                    await conn.close()
                    logger.info(f"关闭 SQLite 连接: {db_path}")
                except Exception as e:
                    logger.warning(f"关闭连接失败 {db_path}: {e}")
            self._connections.clear()

    @classmethod
    def get_instance(cls) -> 'ConnectionPool':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# 模块级单例便捷函数
_pool = ConnectionPool.get_instance()


async def get_connection(db_path: str) -> aiosqlite.Connection:
    """便捷函数：获取指定数据库的连接

    Args:
        db_path: SQLite 数据库文件路径

    Returns:
        aiosqlite.Connection 实例
    """
    return await _pool.get_connection(db_path)


async def close_all_connections() -> None:
    """便捷函数：关闭所有连接池中的连接"""
    await _pool.close_all()
