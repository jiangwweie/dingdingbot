"""
Pending Recovery Repository - 待恢复记录持久化

职责：
1. 持久化 pending_recovery 记录到 SQLite
2. 提供跨进程访问能力（脚本/CLI）
3. 最小实现，不切 PG

表结构：
- order_id TEXT PRIMARY KEY
- exchange_order_id TEXT
- symbol TEXT NOT NULL
- error TEXT
- created_at INTEGER NOT NULL
- updated_at INTEGER NOT NULL
"""
import aiosqlite
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from src.infrastructure.logger import logger


class PendingRecoveryRepository:
    """
    Pending Recovery Repository (SQLite)

    最小实现，用于跨进程访问 pending_recovery 记录。
    """

    def __init__(self, db_path: str = "data/pending_recovery.db"):
        """
        初始化 repository

        Args:
            db_path: SQLite 数据库文件路径
        """
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """初始化数据库连接和表结构"""
        self._db = await aiosqlite.connect(self._db_path)

        # 创建表
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS pending_recovery (
                order_id TEXT PRIMARY KEY,
                exchange_order_id TEXT,
                symbol TEXT NOT NULL,
                error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        # 创建索引（symbol 用于按交易对查询）
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending_recovery_symbol
            ON pending_recovery(symbol)
        """)

        await self._db.commit()

        logger.info(f"PendingRecoveryRepository initialized: {self._db_path}")

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("PendingRecoveryRepository closed")

    async def save(self, record: Dict[str, Any]) -> None:
        """
        保存 pending_recovery 记录（upsert by order_id）

        Args:
            record: 包含 order_id, exchange_order_id, symbol, error, timestamp 的字典
        """
        if not self._db:
            raise RuntimeError("Repository not initialized")

        order_id = record["order_id"]
        exchange_order_id = record.get("exchange_order_id")
        symbol = record["symbol"]
        error = record.get("error")
        timestamp = record.get("timestamp", int(datetime.now(timezone.utc).timestamp() * 1000))

        # Upsert
        await self._db.execute("""
            INSERT INTO pending_recovery
                (order_id, exchange_order_id, symbol, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                exchange_order_id = excluded.exchange_order_id,
                symbol = excluded.symbol,
                error = excluded.error,
                updated_at = excluded.updated_at
        """, (order_id, exchange_order_id, symbol, error, timestamp, timestamp))

        await self._db.commit()

        logger.debug(f"PendingRecovery saved: order_id={order_id}")

    async def get(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定 order_id 的 pending_recovery 记录

        Args:
            order_id: 订单 ID

        Returns:
            记录字典，不存在返回 None
        """
        if not self._db:
            raise RuntimeError("Repository not initialized")

        cursor = await self._db.execute("""
            SELECT order_id, exchange_order_id, symbol, error, created_at, updated_at
            FROM pending_recovery
            WHERE order_id = ?
        """, (order_id,))

        row = await cursor.fetchone()
        if not row:
            return None

        return {
            "order_id": row[0],
            "exchange_order_id": row[1],
            "symbol": row[2],
            "error": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }

    async def list_all(self) -> List[Dict[str, Any]]:
        """
        列出所有 pending_recovery 记录

        Returns:
            记录列表
        """
        if not self._db:
            raise RuntimeError("Repository not initialized")

        cursor = await self._db.execute("""
            SELECT order_id, exchange_order_id, symbol, error, created_at, updated_at
            FROM pending_recovery
            ORDER BY created_at DESC
        """)

        rows = await cursor.fetchall()

        return [
            {
                "order_id": row[0],
                "exchange_order_id": row[1],
                "symbol": row[2],
                "error": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
            for row in rows
        ]

    async def delete(self, order_id: str) -> None:
        """
        删除指定 order_id 的 pending_recovery 记录

        Args:
            order_id: 订单 ID
        """
        if not self._db:
            raise RuntimeError("Repository not initialized")

        await self._db.execute("""
            DELETE FROM pending_recovery
            WHERE order_id = ?
        """, (order_id,))

        await self._db.commit()

        logger.debug(f"PendingRecovery deleted: order_id={order_id}")
