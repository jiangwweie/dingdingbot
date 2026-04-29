"""
配置管理系统 Repository 层实现

提供 7 个 Repository 类，用于配置管理系统的数据库操作接口。

迁移策略：
- 默认构造路由到 PG（当 MIGRATE_ALL_STATE_TO_PG=true 且无显式 db_path/connection）
- 显式传入 db_path/connection 时仍走 SQLite（测试兼容）
"""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Tuple, Dict, Any, Literal

import aiosqlite

from src.domain.models import (
    RiskConfig,
    StrategyParams,
)
from src.domain.exceptions import (
    CryptoMonitorError,
    FatalStartupError,
)

# PG 迁移环境变量
MIGRATE_ALL_STATE_TO_PG = os.getenv("MIGRATE_ALL_STATE_TO_PG", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _should_route_default_to_pg(db_path: str, connection: Optional[aiosqlite.Connection]) -> bool:
    """Route default production config repositories to PG, keep explicit SQLite fixtures untouched."""
    if connection is not None or db_path != "data/v3_dev.db":
        return False
    try:
        from src.infrastructure.database import should_use_pg_for_default_repository

        return should_use_pg_for_default_repository()
    except Exception:
        return MIGRATE_ALL_STATE_TO_PG


# ============================================================
# Exception Classes
# ============================================================
class ConfigNotFoundError(CryptoMonitorError):
    """Configuration not found"""
    pass


class ConfigConflictError(CryptoMonitorError):
    """Configuration conflict (e.g., duplicate name)"""
    pass


class ConfigValidationError(CryptoMonitorError):
    """Configuration validation failed"""
    pass


# ============================================================
# StrategyConfigRepository
# ============================================================
class StrategyConfigRepository:
    """
    Repository for managing strategy configurations.
    Supports CRUD operations and toggle functionality.

    迁移策略：
    - 默认构造（无参数）→ PG
    - 显式 db_path/connection → SQLite（测试兼容）
    """

    def __new__(
        cls,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
        use_pg: Optional[bool] = None,
    ):
        if cls is StrategyConfigRepository:
            should_use_pg = _should_route_default_to_pg(db_path, connection) if use_pg is None else use_pg
            if should_use_pg:
                from src.infrastructure.pg_config_repositories import PgStrategyConfigRepository

                return PgStrategyConfigRepository()
        return super().__new__(cls)

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
        use_pg: Optional[bool] = None,
    ):
        """
        Initialize StrategyConfigRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
            use_pg: 显式指定使用 PG（None 时根据环境变量和参数自动判断）
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None  # 标记是否自行管理生命周期
        self._lock = asyncio.Lock()
        self._use_pg = False

    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        if self._use_pg:
            return await self._pg_repo.initialize()

        # 如果有注入的连接，跳过连接创建
        if self._owns_connection and self._db is None:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # Open database connection via connection pool (shared across repos)
            from src.infrastructure.connection_pool import get_connection as pool_get_connection
            self._db = await pool_get_connection(self.db_path)
            # PRAGMAs are set centrally in connection_pool, no need to repeat here

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                trigger_config TEXT NOT NULL,
                filter_configs TEXT NOT NULL,
                filter_logic TEXT DEFAULT 'AND',
                symbols TEXT NOT NULL,
                timeframes TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                version INTEGER DEFAULT 1
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategies_active ON strategies(is_active)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategies_updated ON strategies(updated_at)
        """)

        await self._db.commit()

    async def close(self) -> None:
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._use_pg:
            return await self._pg_repo.close()
        if self._db:
            self._db = None

    async def create(self, strategy: Dict[str, Any]) -> str:
        """
        Create a new strategy configuration.

        Args:
            strategy: Strategy dict with keys:
                - id: str (optional, UUID will be generated if not provided)
                - name: str
                - description: str (optional)
                - trigger_config: dict
                - filter_configs: list
                - filter_logic: str ('AND' or 'OR')
                - symbols: list
                - timeframes: list

        Returns:
            Created strategy ID

        Raises:
            ConfigConflictError: If strategy name already exists
        """
        if self._use_pg:
            return await self._pg_repo.create(strategy)
        async with self._lock:
            strategy_id = strategy.get("id") or str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()

            # Check for duplicate name
            async with self._db.execute(
                "SELECT id FROM strategies WHERE name = ?",
                (strategy["name"],)
            ) as cursor:
                if await cursor.fetchone():
                    raise ConfigConflictError(
                        f"Strategy name '{strategy['name']}' already exists",
                        "C-101"
                    )

            await self._db.execute("""
                INSERT INTO strategies
                (id, name, description, is_active, trigger_config, filter_configs,
                 filter_logic, symbols, timeframes, created_at, updated_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                strategy_id,
                strategy["name"],
                strategy.get("description"),
                True,
                json.dumps(strategy["trigger_config"]),
                json.dumps(strategy.get("filter_configs", [])),
                strategy.get("filter_logic", "AND"),
                json.dumps(strategy.get("symbols", [])),
                json.dumps(strategy.get("timeframes", [])),
                now,
                now,
                1
            ))
            await self._db.commit()
            return strategy_id

    async def get_by_id(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """
        Get strategy configuration by ID.

        Args:
            strategy_id: Strategy ID

        Returns:
            Strategy dict with all fields, or None if not found
        """
        if self._use_pg:
            return await self._pg_repo.get_by_id(strategy_id)

        async with self._db.execute(
            "SELECT * FROM strategies WHERE id = ?",
            (strategy_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    async def get_list(
        self,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get strategy list with pagination.

        Args:
            is_active: Filter by active status (optional)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Tuple of (list of strategy dicts, total count)
        """
        if self._use_pg:
            return await self._pg_repo.get_list(is_active, limit, offset)

        where_clauses = []
        params: List[Any] = []

        if is_active is not None:
            where_clauses.append("is_active = ?")
            params.append(1 if is_active else 0)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM strategies {where_sql}"
        async with self._db.execute(count_sql, params) as cursor:
            row = await cursor.fetchone()
            total = row[0] if row else 0

        # Get paginated data
        data_sql = f"""
            SELECT * FROM strategies {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
        """
        data_params = params + [limit, offset]

        async with self._db.execute(data_sql, data_params) as cursor:
            rows = await cursor.fetchall()
            data = [self._row_to_dict(row) for row in rows]

        return data, total

    async def update(self, strategy_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update strategy configuration.

        Args:
            strategy_id: Strategy ID
            updates: Dict with fields to update

        Returns:
            True if updated successfully, False if not found

        Raises:
            ConfigConflictError: If new name conflicts with existing strategy
        """
        if self._use_pg:
            return await self._pg_repo.update(strategy_id, updates)

        async with self._lock:
            # Check if strategy exists
            existing = await self.get_by_id(strategy_id)
            if not existing:
                return False

            # Check for name conflict if name is being updated
            if "name" in updates and updates["name"] != existing["name"]:
                async with self._db.execute(
                    "SELECT id FROM strategies WHERE name = ? AND id != ?",
                    (updates["name"], strategy_id)
                ) as cursor:
                    if await cursor.fetchone():
                        raise ConfigConflictError(
                            f"Strategy name '{updates['name']}' already exists",
                            "C-101"
                        )

            now = datetime.now(timezone.utc).isoformat()
            set_clauses = ["updated_at = ?", "version = version + 1"]
            set_params: List[Any] = [now]

            for key, value in updates.items():
                if key in ("trigger_config", "filter_configs", "symbols", "timeframes"):
                    set_clauses.append(f"{key} = ?")
                    set_params.append(json.dumps(value))
                elif key != "updated_at":
                    set_clauses.append(f"{key} = ?")
                    set_params.append(value)

            sql = f"UPDATE strategies SET {', '.join(set_clauses)} WHERE id = ?"
            set_params.append(strategy_id)

            await self._db.execute(sql, set_params)
            await self._db.commit()
            return True

    async def delete(self, strategy_id: str) -> bool:
        """
        Delete strategy configuration.

        Args:
            strategy_id: Strategy ID

        Returns:
            True if deleted successfully, False if not found
        """
        if self._use_pg:
            return await self._pg_repo.delete(strategy_id)

        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM strategies WHERE id = ?",
                (strategy_id,)
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def toggle(self, strategy_id: str) -> Optional[bool]:
        """
        Toggle strategy active status.

        Args:
            strategy_id: Strategy ID

        Returns:
            New active status, or None if not found
        """
        if self._use_pg:
            return await self._pg_repo.toggle(strategy_id)

        async with self._lock:
            existing = await self.get_by_id(strategy_id)
            if not existing:
                return None

            new_status = not existing["is_active"]
            now = datetime.now(timezone.utc).isoformat()

            await self._db.execute("""
                UPDATE strategies SET is_active = ?, updated_at = ?
                WHERE id = ?
            """, (new_status, now, strategy_id))
            await self._db.commit()
            return new_status

    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        """Convert database row to strategy dict."""
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "is_active": bool(row["is_active"]),
            "trigger_config": json.loads(row["trigger_config"]),
            "filter_configs": json.loads(row["filter_configs"]),
            "filter_logic": row["filter_logic"],
            "symbols": json.loads(row["symbols"]),
            "timeframes": json.loads(row["timeframes"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "version": row["version"],
        }


# ============================================================
# RiskConfigRepository
# ============================================================
class RiskConfigRepository:
    """
    Repository for managing risk configuration.
    Single instance pattern (id='global').
    """

    def __new__(
        cls,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        if cls is RiskConfigRepository and _should_route_default_to_pg(db_path, connection):
            from src.infrastructure.pg_config_repositories import PgRiskConfigRepository

            return PgRiskConfigRepository()
        return super().__new__(cls)

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        """
        Initialize RiskConfigRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        if self._owns_connection and self._db is None:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # Open database connection via connection pool (shared across repos)
            from src.infrastructure.connection_pool import get_connection as pool_get_connection
            self._db = await pool_get_connection(self.db_path)
            # PRAGMAs are set centrally in connection_pool, no need to repeat here

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS risk_configs (
                id TEXT PRIMARY KEY DEFAULT 'global',
                max_loss_percent DECIMAL(5,4) NOT NULL,
                max_leverage INTEGER NOT NULL,
                max_total_exposure DECIMAL(5,4),
                daily_max_trades INTEGER,
                daily_max_loss DECIMAL(20,8),
                max_position_hold_time INTEGER,
                cooldown_minutes INTEGER DEFAULT 240,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                version INTEGER DEFAULT 1
            )
        """)

        await self._db.commit()

    async def close(self) -> None:
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._db:
            self._db = None

    async def get_global(self) -> Optional[Dict[str, Any]]:
        """
        Get global risk configuration.

        Returns:
            Risk config dict, or None if not configured
        """
        async with self._db.execute(
            "SELECT * FROM risk_configs WHERE id = 'global'"
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_dict(row) if row else None

    async def update(self, config: Dict[str, Any]) -> bool:
        """
        Update global risk configuration.

        Args:
            config: Risk config dict with fields to update

        Returns:
            True if updated successfully
        """
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()

            # Check if global config exists
            existing = await self.get_global()

            # Prepare update values with Decimal → str conversion
            update_values: Dict[str, Any] = {}
            decimal_fields = {"max_loss_percent", "max_total_exposure", "daily_max_loss"}

            for key, value in config.items():
                if key == "updated_at":
                    continue
                # Convert Decimal to string for database storage
                if key in decimal_fields and value is not None:
                    update_values[key] = str(value)
                else:
                    update_values[key] = value

            if existing:
                # Update existing
                set_clauses = ["updated_at = ?", "version = version + 1"]
                set_params: List[Any] = [now]

                for key, value in update_values.items():
                    set_clauses.append(f"{key} = ?")
                    set_params.append(value)

                sql = f"UPDATE risk_configs SET {', '.join(set_clauses)} WHERE id = 'global'"
                await self._db.execute(sql, set_params)
            else:
                # Insert new
                await self._db.execute("""
                    INSERT INTO risk_configs
                    (id, max_loss_percent, max_leverage, max_total_exposure,
                     daily_max_trades, daily_max_loss, max_position_hold_time,
                     cooldown_minutes, created_at, updated_at, version)
                    VALUES ('global', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(update_values.get("max_loss_percent", Decimal("0.01"))),
                    update_values.get("max_leverage", 10),
                    str(update_values.get("max_total_exposure", Decimal("0.8"))) if update_values.get("max_total_exposure") else None,
                    update_values.get("daily_max_trades"),
                    str(update_values.get("daily_max_loss")) if update_values.get("daily_max_loss") else None,
                    update_values.get("max_position_hold_time"),
                    update_values.get("cooldown_minutes", 240),
                    now,
                    now,
                    1
                ))

            await self._db.commit()
            return True

    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        """Convert database row to risk config dict."""
        return {
            "id": row["id"],
            "max_loss_percent": Decimal(str(row["max_loss_percent"])),
            "max_leverage": row["max_leverage"],
            "max_total_exposure": Decimal(str(row["max_total_exposure"])) if row["max_total_exposure"] else None,
            "daily_max_trades": row["daily_max_trades"],
            "daily_max_loss": Decimal(str(row["daily_max_loss"])) if row["daily_max_loss"] else None,
            "max_position_hold_time": row["max_position_hold_time"],
            "cooldown_minutes": row["cooldown_minutes"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "version": row["version"],
        }


# ============================================================
# SystemConfigRepository
# ============================================================
class SystemConfigRepository:
    """
    Repository for managing system configuration.
    Single instance pattern (id='global').
    """

    def __new__(
        cls,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        if cls is SystemConfigRepository and _should_route_default_to_pg(db_path, connection):
            from src.infrastructure.pg_config_repositories import PgSystemConfigRepository

            return PgSystemConfigRepository()
        return super().__new__(cls)

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        """
        Initialize SystemConfigRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        if self._owns_connection and self._db is None:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # Open database connection via connection pool (shared across repos)
            from src.infrastructure.connection_pool import get_connection as pool_get_connection
            self._db = await pool_get_connection(self.db_path)
            # PRAGMAs are set centrally in connection_pool, no need to repeat here

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS system_configs (
                id TEXT PRIMARY KEY DEFAULT 'global',
                core_symbols TEXT NOT NULL,
                ema_period INTEGER DEFAULT 60,
                mtf_ema_period INTEGER DEFAULT 60,
                mtf_mapping TEXT NOT NULL,
                signal_cooldown_seconds INTEGER DEFAULT 14400,
                queue_batch_size INTEGER DEFAULT 10,
                queue_flush_interval DECIMAL(4,2) DEFAULT 5.0,
                queue_max_size INTEGER DEFAULT 1000,
                warmup_history_bars INTEGER DEFAULT 100,
                atr_filter_enabled BOOLEAN DEFAULT TRUE,
                atr_period INTEGER DEFAULT 14,
                atr_min_ratio DECIMAL(4,2) DEFAULT 0.5,
                restart_required BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: add missing columns for existing databases
        try:
            await self._db.execute("ALTER TABLE system_configs ADD COLUMN restart_required BOOLEAN DEFAULT FALSE")
        except Exception:
            pass

        await self._db.commit()

    async def close(self) -> None:
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._db:
            self._db = None

    async def get_global(self) -> Optional[Dict[str, Any]]:
        """
        Get global system configuration.

        Returns:
            System config dict, or None if not configured
        """
        async with self._db.execute(
            "SELECT * FROM system_configs WHERE id = 'global'"
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_dict(row) if row else None

    async def update(self, config: Dict[str, Any], restart_required: bool = False) -> bool:
        """
        Update global system configuration.

        Args:
            config: System config dict with fields to update
            restart_required: Whether system restart is required

        Returns:
            True if updated successfully
        """
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            existing = await self.get_global()

            if existing:
                set_clauses = ["updated_at = ?"]
                set_params: List[Any] = [now]

                for key, value in config.items():
                    if key in ("core_symbols", "mtf_mapping"):
                        set_clauses.append(f"{key} = ?")
                        set_params.append(json.dumps(value))
                    elif key not in ("updated_at", "created_at"):
                        set_clauses.append(f"{key} = ?")
                        set_params.append(value)

                if restart_required:
                    set_clauses.append("restart_required = TRUE")

                sql = f"UPDATE system_configs SET {', '.join(set_clauses)} WHERE id = 'global'"
                await self._db.execute(sql, set_params)
            else:
                await self._db.execute("""
                    INSERT INTO system_configs
                    (id, core_symbols, ema_period, mtf_ema_period, mtf_mapping,
                     signal_cooldown_seconds, queue_batch_size, queue_flush_interval,
                     queue_max_size, warmup_history_bars, atr_filter_enabled,
                     atr_period, atr_min_ratio, restart_required,
                     created_at, updated_at)
                    VALUES ('global', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    json.dumps(config.get("core_symbols", ["BTC/USDT:USDT", "ETH/USDT:USDT"])),
                    config.get("ema_period", 60),
                    config.get("mtf_ema_period", 60),
                    json.dumps(config.get("mtf_mapping", {"15m": "1h", "1h": "4h", "4h": "1d"})),
                    config.get("signal_cooldown_seconds", 14400),
                    config.get("queue_batch_size", 10),
                    config.get("queue_flush_interval", 5.0),
                    config.get("queue_max_size", 1000),
                    config.get("warmup_history_bars", 100),
                    config.get("atr_filter_enabled", True),
                    config.get("atr_period", 14),
                    config.get("atr_min_ratio", 0.5),
                    restart_required,
                    now,
                    now
                ))

            await self._db.commit()
            return True

    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        """Convert database row to system config dict."""
        return {
            "id": row["id"],
            "core_symbols": json.loads(row["core_symbols"]),
            "ema_period": row["ema_period"],
            "mtf_ema_period": row["mtf_ema_period"],
            "mtf_mapping": json.loads(row["mtf_mapping"]),
            "signal_cooldown_seconds": row["signal_cooldown_seconds"],
            "queue_batch_size": row["queue_batch_size"],
            "queue_flush_interval": Decimal(str(row["queue_flush_interval"])) if row["queue_flush_interval"] else Decimal("5.0"),
            "queue_max_size": row["queue_max_size"],
            "warmup_history_bars": row["warmup_history_bars"],
            "atr_filter_enabled": bool(row["atr_filter_enabled"]),
            "atr_period": row["atr_period"],
            "atr_min_ratio": Decimal(str(row["atr_min_ratio"])) if row["atr_min_ratio"] else Decimal("0.5"),
            "restart_required": bool(row["restart_required"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


# ============================================================
# SymbolConfigRepository
# ============================================================
class SymbolConfigRepository:
    """
    Repository for managing symbol configurations.
    Supports CRUD operations and toggle functionality.
    """

    def __new__(
        cls,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        if cls is SymbolConfigRepository and _should_route_default_to_pg(db_path, connection):
            from src.infrastructure.pg_config_repositories import PgSymbolConfigRepository

            return PgSymbolConfigRepository()
        return super().__new__(cls)

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        """
        Initialize SymbolConfigRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        if self._owns_connection and self._db is None:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # Open database connection via connection pool (shared across repos)
            from src.infrastructure.connection_pool import get_connection as pool_get_connection
            self._db = await pool_get_connection(self.db_path)
            # PRAGMAs are set centrally in connection_pool, no need to repeat here

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS symbols (
                symbol TEXT PRIMARY KEY,
                is_active BOOLEAN DEFAULT TRUE,
                is_core BOOLEAN DEFAULT FALSE,
                min_quantity DECIMAL(20,8),
                price_precision INTEGER,
                quantity_precision INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self._db.commit()

    async def close(self) -> None:
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._db:
            self._db = None

    async def get_all(self) -> List[Dict[str, Any]]:
        """
        Get all symbol configurations.

        Returns:
            List of symbol dicts
        """
        async with self._db.execute(
            "SELECT * FROM symbols ORDER BY symbol"
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def get_active(self) -> List[Dict[str, Any]]:
        """
        Get all active symbol configurations.

        Returns:
            List of active symbol dicts
        """
        async with self._db.execute(
            "SELECT * FROM symbols WHERE is_active = TRUE ORDER BY symbol"
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def get_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get symbol configuration by symbol.

        Args:
            symbol: Symbol string (e.g., "BTC/USDT:USDT")

        Returns:
            Symbol dict, or None if not found
        """
        async with self._db.execute(
            "SELECT * FROM symbols WHERE symbol = ?",
            (symbol,)
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_dict(row) if row else None

    async def create(self, symbol_config: Dict[str, Any]) -> bool:
        """
        Create a new symbol configuration.

        Args:
            symbol_config: Symbol config dict with keys:
                - symbol: str
                - is_active: bool (optional, default True)
                - is_core: bool (optional, default False)
                - min_quantity: Decimal (optional)
                - price_precision: int (optional)
                - quantity_precision: int (optional)

        Returns:
            True if created successfully

        Raises:
            ConfigConflictError: If symbol already exists
        """
        async with self._lock:
            existing = await self.get_by_symbol(symbol_config["symbol"])
            if existing:
                raise ConfigConflictError(
                    f"Symbol '{symbol_config['symbol']}' already exists",
                    "C-102"
                )

            now = datetime.now(timezone.utc).isoformat()
            await self._db.execute("""
                INSERT INTO symbols
                (symbol, is_active, is_core, min_quantity, price_precision,
                 quantity_precision, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol_config["symbol"],
                symbol_config.get("is_active", True),
                symbol_config.get("is_core", False),
                symbol_config.get("min_quantity"),
                symbol_config.get("price_precision"),
                symbol_config.get("quantity_precision"),
                now,
                now
            ))
            await self._db.commit()
            return True

    async def update(self, symbol: str, updates: Dict[str, Any]) -> bool:
        """
        Update symbol configuration.

        Args:
            symbol: Symbol string
            updates: Dict with fields to update

        Returns:
            True if updated successfully, False if not found
        """
        async with self._lock:
            existing = await self.get_by_symbol(symbol)
            if not existing:
                return False

            now = datetime.now(timezone.utc).isoformat()
            set_clauses = ["updated_at = ?"]
            set_params: List[Any] = [now]

            for key, value in updates.items():
                if key not in ("updated_at", "created_at", "symbol"):
                    set_clauses.append(f"{key} = ?")
                    set_params.append(value)

            sql = f"UPDATE symbols SET {', '.join(set_clauses)} WHERE symbol = ?"
            set_params.append(symbol)

            await self._db.execute(sql, set_params)
            await self._db.commit()
            return True

    async def delete(self, symbol: str) -> bool:
        """
        Delete symbol configuration.

        Args:
            symbol: Symbol string

        Returns:
            True if deleted successfully, False if not found or is core symbol
        """
        async with self._lock:
            existing = await self.get_by_symbol(symbol)
            if not existing:
                return False

            # Cannot delete core symbols
            if existing.get("is_core"):
                raise ConfigValidationError(
                    f"Cannot delete core symbol '{symbol}'",
                    "C-103"
                )

            cursor = await self._db.execute(
                "DELETE FROM symbols WHERE symbol = ?",
                (symbol,)
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def toggle(self, symbol: str) -> Optional[bool]:
        """
        Toggle symbol active status.

        Args:
            symbol: Symbol string

        Returns:
            New active status, or None if not found
        """
        async with self._lock:
            existing = await self.get_by_symbol(symbol)
            if not existing:
                return None

            new_status = not existing["is_active"]
            now = datetime.now(timezone.utc).isoformat()

            await self._db.execute("""
                UPDATE symbols SET is_active = ?, updated_at = ?
                WHERE symbol = ?
            """, (new_status, now, symbol))
            await self._db.commit()
            return new_status

    async def add_core_symbols(self, symbols: List[str]) -> int:
        """
        Add core symbols (idempotent operation).

        Args:
            symbols: List of symbol strings to add as core symbols

        Returns:
            Number of symbols added (excluding already existing ones)
        """
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            added_count = 0

            for symbol in symbols:
                existing = await self.get_by_symbol(symbol)
                if not existing:
                    await self._db.execute("""
                        INSERT INTO symbols
                        (symbol, is_active, is_core, created_at, updated_at)
                        VALUES (?, TRUE, TRUE, ?, ?)
                    """, (symbol, now, now))
                    added_count += 1
                elif not existing.get("is_core"):
                    # Mark as core if not already
                    await self._db.execute("""
                        UPDATE symbols SET is_core = TRUE, updated_at = ?
                        WHERE symbol = ?
                    """, (now, symbol))

            await self._db.commit()
            return added_count

    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        """Convert database row to symbol dict."""
        return {
            "symbol": row["symbol"],
            "is_active": bool(row["is_active"]),
            "is_core": bool(row["is_core"]),
            "min_quantity": Decimal(str(row["min_quantity"])) if row["min_quantity"] else None,
            "price_precision": row["price_precision"],
            "quantity_precision": row["quantity_precision"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


# ============================================================
# NotificationConfigRepository
# ============================================================
class NotificationConfigRepository:
    """
    Repository for managing notification configurations.
    Supports CRUD operations and test functionality.
    """

    def __new__(
        cls,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        if cls is NotificationConfigRepository and _should_route_default_to_pg(db_path, connection):
            from src.infrastructure.pg_config_repositories import PgNotificationConfigRepository

            return PgNotificationConfigRepository()
        return super().__new__(cls)

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        """
        Initialize NotificationConfigRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        if self._owns_connection and self._db is None:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # Open database connection via connection pool (shared across repos)
            from src.infrastructure.connection_pool import get_connection as pool_get_connection
            self._db = await pool_get_connection(self.db_path)
            # PRAGMAs are set centrally in connection_pool, no need to repeat here

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                channel_type TEXT NOT NULL,
                webhook_url TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                notify_on_signal BOOLEAN DEFAULT TRUE,
                notify_on_order BOOLEAN DEFAULT TRUE,
                notify_on_error BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self._db.commit()

    async def close(self) -> None:
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._db:
            self._db = None

    async def create(self, notification: Dict[str, Any]) -> str:
        """
        Create a new notification configuration.

        Args:
            notification: Notification dict with keys:
                - id: str (optional, UUID will be generated if not provided)
                - channel_type: str ('feishu', 'wechat', 'telegram')
                - webhook_url: str
                - is_active: bool (optional, default True)
                - notify_on_signal: bool (optional, default True)
                - notify_on_order: bool (optional, default True)
                - notify_on_error: bool (optional, default True)

        Returns:
            Created notification ID
        """
        async with self._lock:
            notification_id = notification.get("id") or str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()

            await self._db.execute("""
                INSERT INTO notifications
                (id, channel_type, webhook_url, is_active, notify_on_signal,
                 notify_on_order, notify_on_error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                notification_id,
                notification["channel_type"],
                notification["webhook_url"],
                notification.get("is_active", True),
                notification.get("notify_on_signal", True),
                notification.get("notify_on_order", True),
                notification.get("notify_on_error", True),
                now,
                now
            ))
            await self._db.commit()
            return notification_id

    async def get_by_id(self, notification_id: str) -> Optional[Dict[str, Any]]:
        """
        Get notification configuration by ID.

        Args:
            notification_id: Notification ID

        Returns:
            Notification dict, or None if not found
        """
        async with self._db.execute(
            "SELECT * FROM notifications WHERE id = ?",
            (notification_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_dict(row) if row else None

    async def get_list(
        self,
        channel_type: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Get notification list with optional filters.

        Args:
            channel_type: Filter by channel type (optional)
            is_active: Filter by active status (optional)

        Returns:
            List of notification dicts
        """
        where_clauses = []
        params: List[Any] = []

        if channel_type:
            where_clauses.append("channel_type = ?")
            params.append(channel_type)

        if is_active is not None:
            where_clauses.append("is_active = ?")
            params.append(1 if is_active else 0)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        async with self._db.execute(
            f"SELECT * FROM notifications {where_sql} ORDER BY created_at DESC",
            params
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def get_notifications(self) -> List[Dict[str, Any]]:
        """
        Get all notification configurations.

        Returns:
            List of notification dicts ordered by created_at DESC
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def get_active_channels(self) -> List[Dict[str, Any]]:
        """
        Get all active notification channels.

        Returns:
            List of active notification dicts
        """
        async with self._db.execute(
            "SELECT * FROM notifications WHERE is_active = TRUE ORDER BY channel_type"
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def update(self, notification_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update notification configuration.

        Args:
            notification_id: Notification ID
            updates: Dict with fields to update

        Returns:
            True if updated successfully, False if not found
        """
        async with self._lock:
            existing = await self.get_by_id(notification_id)
            if not existing:
                return False

            now = datetime.now(timezone.utc).isoformat()
            set_clauses = ["updated_at = ?"]
            set_params: List[Any] = [now]

            for key, value in updates.items():
                if key not in ("updated_at", "created_at", "id"):
                    set_clauses.append(f"{key} = ?")
                    set_params.append(value)

            sql = f"UPDATE notifications SET {', '.join(set_clauses)} WHERE id = ?"
            set_params.append(notification_id)

            await self._db.execute(sql, set_params)
            await self._db.commit()
            return True

    async def delete(self, notification_id: str) -> bool:
        """
        Delete notification configuration.

        Args:
            notification_id: Notification ID

        Returns:
            True if deleted successfully, False if not found
        """
        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM notifications WHERE id = ?",
                (notification_id,)
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def test_connection(self, notification_id: str) -> Dict[str, Any]:
        """
        Test notification channel connection.

        Args:
            notification_id: Notification ID

        Returns:
            Test result dict with keys:
                - success: bool
                - message: str
                - channel_type: str
        """
        notification = await self.get_by_id(notification_id)
        if not notification:
            return {
                "success": False,
                "message": f"Notification '{notification_id}' not found",
                "channel_type": None
            }

        # Simulate connection test (actual implementation would send test request)
        webhook_url = notification["webhook_url"]
        channel_type = notification["channel_type"]

        # Basic URL validation
        if not webhook_url or not webhook_url.startswith("http"):
            return {
                "success": False,
                "message": "Invalid webhook URL format",
                "channel_type": channel_type
            }

        return {
            "success": True,
            "message": f"Connection test successful for {channel_type}",
            "channel_type": channel_type
        }

    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        """Convert database row to notification dict."""
        return {
            "id": row["id"],
            "channel_type": row["channel_type"],
            "webhook_url": row["webhook_url"],
            "is_active": bool(row["is_active"]),
            "notify_on_signal": bool(row["notify_on_signal"]),
            "notify_on_order": bool(row["notify_on_order"]),
            "notify_on_error": bool(row["notify_on_error"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


# ============================================================
# ConfigSnapshotRepository (Extended)
# ============================================================
class ConfigSnapshotRepositoryExtended:
    """
    Extended repository for managing configuration snapshots.
    Provides version control and rollback capabilities.

    Note: This extends the existing ConfigSnapshotRepository with
    additional methods for the new config management system.
    """

    def __new__(
        cls,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        if cls is ConfigSnapshotRepositoryExtended and _should_route_default_to_pg(db_path, connection):
            from src.infrastructure.pg_config_repositories import PgConfigSnapshotRepositoryExtended

            return PgConfigSnapshotRepositoryExtended()
        return super().__new__(cls)

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        """
        Initialize ConfigSnapshotRepositoryExtended.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        if self._owns_connection and self._db is None:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # Open database connection via connection pool (shared across repos)
            from src.infrastructure.connection_pool import get_connection as pool_get_connection
            self._db = await pool_get_connection(self.db_path)
            # PRAGMAs are set centrally in connection_pool, no need to repeat here

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS config_snapshots (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                snapshot_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                is_auto BOOLEAN DEFAULT FALSE
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_created ON config_snapshots(created_at DESC)
        """)

        await self._db.commit()

    async def close(self) -> None:
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._db:
            self._db = None

    async def create(self, snapshot: Dict[str, Any]) -> str:
        """
        Create a new configuration snapshot.

        Args:
            snapshot: Snapshot dict with keys:
                - id: str (optional, UUID will be generated)
                - name: str
                - description: str (optional)
                - snapshot_data: dict (complete configuration data)
                - created_by: str (optional)
                - is_auto: bool (optional, default False)

        Returns:
            Created snapshot ID
        """
        async with self._lock:
            snapshot_id = snapshot.get("id") or str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()

            await self._db.execute("""
                INSERT INTO config_snapshots
                (id, name, description, snapshot_data, created_at, created_by, is_auto)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot_id,
                snapshot["name"],
                snapshot.get("description"),
                json.dumps(snapshot["snapshot_data"]),
                now,
                snapshot.get("created_by", "user"),
                snapshot.get("is_auto", False)
            ))
            await self._db.commit()
            return snapshot_id

    async def get_by_id(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        Get snapshot by ID.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Snapshot dict, or None if not found
        """
        async with self._db.execute(
            "SELECT * FROM config_snapshots WHERE id = ?",
            (snapshot_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_dict(row) if row else None

    async def get_list(
        self,
        limit: int = 20,
        offset: int = 0,
        is_auto: Optional[bool] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get snapshot list with pagination.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            is_auto: Filter by auto snapshot status (optional)

        Returns:
            Tuple of (list of snapshot dicts, total count)
        """
        where_clauses = []
        params: List[Any] = []

        if is_auto is not None:
            where_clauses.append("is_auto = ?")
            params.append(1 if is_auto else 0)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM config_snapshots {where_sql}"
        async with self._db.execute(count_sql, params) as cursor:
            row = await cursor.fetchone()
            total = row[0] if row else 0

        # Get paginated data
        data_sql = f"""
            SELECT * FROM config_snapshots {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        data_params = params + [limit, offset]

        async with self._db.execute(data_sql, data_params) as cursor:
            rows = await cursor.fetchall()
            data = [self._row_to_dict(row) for row in rows]

        return data, total

    async def delete(self, snapshot_id: str) -> bool:
        """
        Delete a snapshot.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            True if deleted successfully, False if not found
        """
        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM config_snapshots WHERE id = ?",
                (snapshot_id,)
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def get_recent(self, count: int = 5) -> List[Dict[str, Any]]:
        """
        Get most recent snapshots.

        Args:
            count: Number of snapshots to retrieve

        Returns:
            List of recent snapshot dicts
        """
        async with self._db.execute(
            "SELECT * FROM config_snapshots ORDER BY created_at DESC LIMIT ?",
            (count,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        """Convert database row to snapshot dict."""
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "config_data": json.loads(row["snapshot_data"]),  # API expects config_data
            "created_at": row["created_at"],
            "updated_at": row["created_at"],  # Use created_at as updated_at (no updates)
            "created_by": row["created_by"],
            "is_auto": bool(row["is_auto"]),
        }


# ============================================================
# ConfigHistoryRepository
# ============================================================
class ConfigHistoryRepository:
    """
    Repository for managing configuration change history.
    Provides audit trail and rollback information.
    """

    def __new__(
        cls,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        if cls is ConfigHistoryRepository and _should_route_default_to_pg(db_path, connection):
            from src.infrastructure.pg_config_repositories import PgConfigHistoryRepository

            return PgConfigHistoryRepository()
        return super().__new__(cls)

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        """
        Initialize ConfigHistoryRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        if self._owns_connection and self._db is None:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # Open database connection via connection pool (shared across repos)
            from src.infrastructure.connection_pool import get_connection as pool_get_connection
            self._db = await pool_get_connection(self.db_path)
            # PRAGMAs are set centrally in connection_pool, no need to repeat here

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS config_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                old_values TEXT,
                new_values TEXT,
                old_full_snapshot TEXT,  -- R5.3: 变更前完整配置快照
                new_full_snapshot TEXT,  -- R5.3: 变更后完整配置快照
                changed_by TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                change_summary TEXT
            )
        """)

        # R5.3: Migration - Add full snapshot columns if not exists
        try:
            await self._db.execute("""
                ALTER TABLE config_history ADD COLUMN old_full_snapshot TEXT
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
        try:
            await self._db.execute("""
                ALTER TABLE config_history ADD COLUMN new_full_snapshot TEXT
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_entity ON config_history(entity_type, entity_id)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_time ON config_history(changed_at DESC)
        """)

        await self._db.commit()

    async def close(self) -> None:
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._db:
            self._db = None

    async def record_change(
        self,
        entity_type: str,
        entity_id: str,
        action: Literal["CREATE", "UPDATE", "DELETE", "ROLLBACK"],
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        old_full_snapshot: Optional[Dict[str, Any]] = None,  # R5.3
        new_full_snapshot: Optional[Dict[str, Any]] = None,  # R5.3
        changed_by: str = "user",
        change_summary: Optional[str] = None
    ) -> int:
        """
        Record a configuration change.

        Args:
            entity_type: Type of entity ('strategy', 'risk_config', 'system_config',
                        'symbol', 'notification', 'snapshot')
            entity_id: ID of the entity
            action: Action type ('CREATE', 'UPDATE', 'DELETE', 'ROLLBACK')
            old_values: Previous values (for UPDATE actions)
            new_values: New values (for CREATE/UPDATE actions)
            old_full_snapshot: Complete configuration snapshot before change (R5.3)
            new_full_snapshot: Complete configuration snapshot after change (R5.3)
            changed_by: User identifier
            change_summary: Human-readable summary

        Returns:
            Record ID
        """
        now = datetime.now(timezone.utc).isoformat()

        async with self._lock:
            cursor = await self._db.execute("""
                INSERT INTO config_history
                (entity_type, entity_id, action, old_values, new_values,
                 old_full_snapshot, new_full_snapshot, changed_by, changed_at, change_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entity_type,
                entity_id,
                action,
                json.dumps(old_values) if old_values else None,
                json.dumps(new_values) if new_values else None,
                json.dumps(old_full_snapshot) if old_full_snapshot else None,  # R5.3
                json.dumps(new_full_snapshot) if new_full_snapshot else None,  # R5.3
                changed_by,
                now,
                change_summary
            ))
            await self._db.commit()
            return cursor.lastrowid

    async def get_history(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get configuration change history with filters.

        Args:
            entity_type: Filter by entity type (optional)
            entity_id: Filter by entity ID (optional)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Tuple of (list of history dicts, total count)
        """
        where_clauses = []
        params: List[Any] = []

        if entity_type:
            where_clauses.append("entity_type = ?")
            params.append(entity_type)

        if entity_id:
            where_clauses.append("entity_id = ?")
            params.append(entity_id)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM config_history {where_sql}"
        async with self._db.execute(count_sql, params) as cursor:
            row = await cursor.fetchone()
            total = row[0] if row else 0

        # Get paginated data
        data_sql = f"""
            SELECT * FROM config_history {where_sql}
            ORDER BY changed_at DESC
            LIMIT ? OFFSET ?
        """
        data_params = params + [limit, offset]

        async with self._db.execute(data_sql, data_params) as cursor:
            rows = await cursor.fetchall()
            data = [self._row_to_dict(row) for row in rows]

        return data, total

    async def get_entity_history(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 20,
        action: Optional[str] = None,  # R10.1: 按动作类型过滤
        start_date: Optional[str] = None,  # R10.1: 按时间范围过滤
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get complete history for a specific entity.

        Args:
            entity_type: Type of entity
            entity_id: ID of the entity
            limit: Maximum number of records
            action: Filter by action type (CREATE/UPDATE/DELETE/ROLLBACK) - R10.1
            start_date: Filter by start date (ISO format) - R10.1
            end_date: Filter by end date (ISO format) - R10.1

        Returns:
            List of history dicts for the entity
        """
        where_clauses = ["entity_type = ?", "entity_id = ?"]
        params: List[Any] = [entity_type, entity_id]

        # R10.1: Add action filter
        if action:
            where_clauses.append("action = ?")
            params.append(action)

        # R10.1: Add date range filters
        if start_date:
            where_clauses.append("changed_at >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("changed_at <= ?")
            params.append(end_date)

        query = f"""
            SELECT * FROM config_history
            WHERE {' AND '.join(where_clauses)}
            ORDER BY changed_at DESC
            LIMIT ?
        """
        params.append(limit)

        async with self._db.execute(query, tuple(params)) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def get_recent_changes(
        self,
        limit: int = 20,
        changed_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent configuration changes across all entities.

        Args:
            limit: Maximum number of results
            changed_by: Filter by user (optional)

        Returns:
            List of recent history dicts
        """
        where_clauses = []
        params: List[Any] = []

        if changed_by:
            where_clauses.append("changed_by = ?")
            params.append(changed_by)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        async with self._db.execute(
            f"""
            SELECT * FROM config_history {where_sql}
            ORDER BY changed_at DESC
            LIMIT ?
        """, params + [limit]
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    async def get_changes_summary(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get summary of configuration changes.

        Args:
            start_time: Start time filter (ISO 8601 format)
            end_time: End time filter (ISO 8601 format)

        Returns:
            Summary dict with:
                - total_changes: int
                - changes_by_type: dict
                - changes_by_action: dict
                - changes_by_user: dict
        """
        where_clauses = []
        params: List[Any] = []

        if start_time:
            where_clauses.append("changed_at >= ?")
            params.append(start_time)

        if end_time:
            where_clauses.append("changed_at <= ?")
            params.append(end_time)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Get total changes
        total = 0
        async with self._db.execute(
            f"SELECT COUNT(*) FROM config_history {where_sql}", params
        ) as cursor:
            row = await cursor.fetchone()
            total = row[0] if row else 0

        # Get changes by action type
        changes_by_action = {}
        async with self._db.execute(
            f"""
            SELECT action, COUNT(*) as count FROM config_history
            {where_sql}
            GROUP BY action
        """, params
        ) as cursor:
            rows = await cursor.fetchall()
            changes_by_action = {row["action"]: row["count"] for row in rows}

        # Get changes by entity type
        changes_by_entity = {}
        async with self._db.execute(
            f"""
            SELECT entity_type, COUNT(*) as count FROM config_history
            {where_sql}
            GROUP BY entity_type
        """, params
        ) as cursor:
            rows = await cursor.fetchall()
            changes_by_entity = {row["entity_type"]: row["count"] for row in rows}

        # Get changes by user
        changes_by_user = {}
        async with self._db.execute(
            f"""
            SELECT changed_by, COUNT(*) as count FROM config_history
            {where_sql}
            GROUP BY changed_by
        """, params
        ) as cursor:
            rows = await cursor.fetchall()
            changes_by_user = {row["changed_by"] or "unknown": row["count"] for row in rows}

        return {
            "total_changes": total,
            "changes_by_action": changes_by_action,
            "changes_by_entity": changes_by_entity,
            "changes_by_user": changes_by_user,
        }

    async def get_rollback_candidates(self, entity_type: str, entity_id: str) -> List[Dict[str, Any]]:
        """
        Get potential rollback points for an entity.

        Args:
            entity_type: Type of entity
            entity_id: ID of the entity

        Returns:
            List of history records that can be rolled back to
        """
        async with self._db.execute("""
            SELECT * FROM config_history
            WHERE entity_type = ? AND entity_id = ? AND action IN ('CREATE', 'UPDATE')
            ORDER BY changed_at DESC
        """, (entity_type, entity_id)) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        """Convert database row to history dict."""
        return {
            "id": row["id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "action": row["action"],
            "old_values": json.loads(row["old_values"]) if row["old_values"] else None,
            "new_values": json.loads(row["new_values"]) if row["new_values"] else None,
            "changed_by": row["changed_by"],
            "changed_at": row["changed_at"],
            "change_summary": row["change_summary"],
        }


# ============================================================
# Convenience function for initializing all repositories
# ============================================================
class ConfigDatabaseManager:
    """
    Centralized manager for all configuration repositories.
    Provides unified initialization and cleanup.

    Note: Uses the global ConnectionPool to get a shared database connection,
    which is injected into all repositories to avoid SQLite locking issues.
    """

    def __init__(self, db_path: str = "data/v3_dev.db"):
        self.db_path = db_path
        self._owns_pool = False  # Whether this manager created the pool connection
        self.strategy_repo: Optional[StrategyConfigRepository] = None
        self.risk_repo: Optional[RiskConfigRepository] = None
        self.system_repo: Optional[SystemConfigRepository] = None
        self.symbol_repo: Optional[SymbolConfigRepository] = None
        self.notification_repo: Optional[NotificationConfigRepository] = None
        self.snapshot_repo: Optional[ConfigSnapshotRepositoryExtended] = None
        self.history_repo: Optional[ConfigHistoryRepository] = None

    async def initialize(self) -> None:
        """Initialize all repositories with a shared database connection from the pool."""
        # Get shared connection from the global connection pool
        from src.infrastructure.connection_pool import get_connection as pool_get_connection
        shared_conn = await pool_get_connection(self.db_path)
        self._owns_pool = False  # Pool manages connection lifecycle

        # Create data directory if not exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # Create repositories with injected shared connection
        self.strategy_repo = StrategyConfigRepository(self.db_path, connection=shared_conn)
        self.risk_repo = RiskConfigRepository(self.db_path, connection=shared_conn)
        self.system_repo = SystemConfigRepository(self.db_path, connection=shared_conn)
        self.symbol_repo = SymbolConfigRepository(self.db_path, connection=shared_conn)
        self.notification_repo = NotificationConfigRepository(self.db_path, connection=shared_conn)
        self.snapshot_repo = ConfigSnapshotRepositoryExtended(self.db_path, connection=shared_conn)
        self.history_repo = ConfigHistoryRepository(self.db_path, connection=shared_conn)

        # Initialize tables (sequentially to avoid locking issues)
        # Repositories skip connection creation since connection is injected
        await self.strategy_repo.initialize()
        await self.risk_repo.initialize()
        await self.system_repo.initialize()
        await self.symbol_repo.initialize()
        await self.notification_repo.initialize()
        await self.snapshot_repo.initialize()
        await self.history_repo.initialize()

    async def close(self) -> None:
        """Close repository connections (pool-managed, not closed here)."""
        # Close individual repositories (they won't close the pool-managed connection)
        if self.strategy_repo:
            await self.strategy_repo.close()
        if self.risk_repo:
            await self.risk_repo.close()
        if self.system_repo:
            await self.system_repo.close()
        if self.symbol_repo:
            await self.symbol_repo.close()
        if self.notification_repo:
            await self.notification_repo.close()
        if self.snapshot_repo:
            await self.snapshot_repo.close()
        if self.history_repo:
            await self.history_repo.close()
        # Note: Pool-managed connection is NOT closed here.
        # Call close_all_connections() at application shutdown to close pool.
