"""
Config Entry Repository - SQLite persistence for strategy parameters.

Phase K: 策略参数配置化 - 数据库存储方案
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union

import aiosqlite

from src.domain.exceptions import FatalStartupError
from src.infrastructure.logger import logger


class ConfigEntryRepository:
    """
    SQLite repository for persisting strategy parameters.

    Config key naming convention:
    - strategy.pinbar.min_wick_ratio
    - strategy.ema.period
    - strategy.mtf.enabled
    - risk.max_loss_percent
    """

    def __new__(
        cls,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        if cls is ConfigEntryRepository and connection is None and db_path == "data/v3_dev.db":
            from src.infrastructure.database import should_use_pg_for_default_repository
            if should_use_pg_for_default_repository():
                from src.infrastructure.pg_config_entry_repository import PgConfigEntryRepository
                return PgConfigEntryRepository()
        return super().__new__(cls)

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        """
        Initialize ConfigEntryRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        self._lock: Optional[asyncio.Lock] = None  # 延迟创建，避免事件循环冲突

    def _ensure_lock(self) -> asyncio.Lock:
        """Ensure lock is created for current event loop.

        This method is safe to call from any event loop context.
        Each call will return the lock associated with the current running event loop.
        """
        try:
            # 尝试获取当前运行的事件循环
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行的事件循环，返回一个新创建的 lock
            # 这种情况通常发生在同步代码中
            return asyncio.Lock()

        # 为当前事件循环创建或获取 lock
        if self._lock is None:
            self._lock = asyncio.Lock()

        return self._lock

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables.

        Note: For Profile support, the unique constraint is on (profile_name, config_key),
        not just config_key alone.

        This method is idempotent - calling it multiple times has no effect after first initialization.
        """
        # 幂等性检查：如果已经初始化，直接返回
        if self._db is not None:
            return

        async with self._ensure_lock():
            # Create connection if not injected
            if self._owns_connection and self._db is None:
                # Create data directory if not exists
                db_dir = os.path.dirname(self.db_path)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir, exist_ok=True)

                # Open database connection via connection pool (shared across repos)
                from src.infrastructure.connection_pool import get_connection as pool_get_connection
                self._db = await pool_get_connection(self.db_path)
                # PRAGMAs are set centrally in connection_pool, no need to repeat here

            # Create config_entries_v2 table (Phase K design with Profile support)
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS config_entries_v2 (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_key    VARCHAR(128) NOT NULL,
                    config_value  TEXT NOT NULL,
                    value_type    VARCHAR(16) NOT NULL,
                    version       VARCHAR(32) NOT NULL DEFAULT 'v1.0.0',
                    updated_at    BIGINT NOT NULL,
                    profile_name  TEXT NOT NULL DEFAULT 'default'
                )
            """)

            # Migration: Add profile_name column if not exists (for legacy tables)
            try:
                await self._db.execute("""
                    ALTER TABLE config_entries_v2 ADD COLUMN profile_name TEXT NOT NULL DEFAULT 'default'
                """)
            except aiosqlite.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise

            # Migration: Drop old unique index and create new composite index
            try:
                await self._db.execute("""
                    DROP INDEX IF EXISTS idx_config_entries_v2_key
                """)
            except aiosqlite.OperationalError:
                pass

            # Create indexes (after migration)
            await self._db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_config_entries_v2_key
                ON config_entries_v2(profile_name, config_key)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_config_entries_v2_updated_at
                ON config_entries_v2(updated_at DESC)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_config_entries_v2_profile
                ON config_entries_v2(profile_name)
            """)

        await self._db.commit()

    async def close(self) -> None:
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._db:
            self._db = None

    def _get_value_type(self, value: Any) -> str:
        """
        Determine the value type for storage.

        Args:
            value: Any Python value

        Returns:
            Type string: 'string', 'number', 'boolean', 'json', 'decimal'
        """
        if isinstance(value, Decimal):
            return "decimal"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, (int, float)):
            return "number"
        elif isinstance(value, (dict, list)):
            return "json"
        else:
            return "string"

    def _serialize_value(self, value: Any, value_type: str) -> str:
        """
        Serialize value for storage.

        Args:
            value: Value to serialize
            value_type: Type hint

        Returns:
            JSON string representation
        """
        if value_type == "decimal":
            return str(value)
        elif value_type == "json":
            return json.dumps(value)
        elif value_type == "boolean":
            return "true" if value else "false"
        else:
            return str(value)

    def _deserialize_value(self, value_str: str, value_type: str, config_key: str = "") -> Any:
        """
        Deserialize value from storage.

        Args:
            value_str: JSON string representation
            value_type: Type hint
            config_key: Configuration key for error logging

        Returns:
            Deserialized Python value, or None if deserialization fails
        """
        try:
            if value_type == "decimal":
                return Decimal(value_str)
            elif value_type == "boolean":
                return value_str == "true"
            elif value_type == "number":
                # Try int first, then float
                try:
                    return int(value_str)
                except ValueError:
                    return float(value_str)
            elif value_type == "json":
                return json.loads(value_str)
            else:
                return value_str
        except (json.JSONDecodeError, ValueError, Exception) as e:
            key_info = f"key={config_key}" if config_key else "key=unknown"
            logger.error(f"配置项解析失败 [{key_info}]: {e}, value={value_str[:100]}")
            return None  # 返回 None 让上层使用默认值

    async def get_entry(self, config_key: str) -> Optional[Dict[str, Any]]:
        """
        Get a single config entry by key.

        Args:
            config_key: Configuration key (e.g., 'strategy.pinbar.min_wick_ratio')

        Returns:
            Config entry dict with keys: id, config_key, config_value, value_type, version, updated_at
            or None if not found
        """
        async with self._db.execute(
            "SELECT * FROM config_entries_v2 WHERE config_key = ?",
            (config_key,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "config_key": row["config_key"],
                    "config_value": self._deserialize_value(row["config_value"], row["value_type"], row["config_key"]),
                    "value_type": row["value_type"],
                    "version": row["version"],
                    "updated_at": row["updated_at"],
                }
            return None

    async def upsert_entry(
        self,
        config_key: str,
        config_value: Any,
        version: str = "v1.0.0",
    ) -> int:
        """
        Insert or update a config entry.

        Args:
            config_key: Configuration key
            config_value: Configuration value (any JSON-serializable type)
            version: Version string

        Returns:
            Config entry ID
        """
        value_type = self._get_value_type(config_value)
        value_str = self._serialize_value(config_value, value_type)
        now = int(datetime.now(timezone.utc).timestamp() * 1000)

        async with self._ensure_lock():
            # Try update first
            cursor = await self._db.execute("""
                UPDATE config_entries_v2
                SET config_value = ?, value_type = ?, version = ?, updated_at = ?
                WHERE config_key = ?
            """, (value_str, value_type, version, now, config_key))

            if cursor.rowcount == 0:
                # Insert new entry
                cursor = await self._db.execute("""
                    INSERT INTO config_entries_v2
                    (config_key, config_value, value_type, version, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (config_key, value_str, value_type, version, now))
                await self._db.commit()
                return cursor.lastrowid

            await self._db.commit()
            return cursor.lastrowid

    async def get_all_entries(self) -> Dict[str, Any]:
        """
        Get all config entries as a dictionary.

        Returns:
            Dictionary mapping config_key -> config_value
        """
        async with self._db.execute(
            "SELECT config_key, config_value, value_type FROM config_entries_v2 ORDER BY config_key"
        ) as cursor:
            rows = await cursor.fetchall()
            result = {}
            for row in rows:
                result[row["config_key"]] = self._deserialize_value(
                    row["config_value"], row["value_type"], row["config_key"]
                )
            return result

    async def get_entries_by_prefix(self, prefix: str) -> Dict[str, Any]:
        """
        Get all config entries with keys starting with a prefix.

        Args:
            prefix: Key prefix (e.g., 'strategy.pinbar')

        Returns:
            Dictionary mapping config_key -> config_value
        """
        if not prefix.endswith("."):
            prefix = prefix + "."

        async with self._db.execute(
            "SELECT config_key, config_value, value_type FROM config_entries_v2 "
            "WHERE config_key LIKE ? ORDER BY config_key",
            (f"{prefix}%",)
        ) as cursor:
            rows = await cursor.fetchall()
            result = {}
            for row in rows:
                result[row["config_key"]] = self._deserialize_value(
                    row["config_value"], row["value_type"], row["config_key"]
                )
            return result

    async def delete_entry(self, config_key: str) -> bool:
        """
        Delete a config entry.

        Args:
            config_key: Configuration key

        Returns:
            True if deleted successfully, False if not found
        """
        async with self._ensure_lock():
            cursor = await self._db.execute(
                "DELETE FROM config_entries_v2 WHERE config_key = ?",
                (config_key,)
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def delete_entries_by_prefix(self, prefix: str) -> int:
        """
        Delete all config entries with keys starting with a prefix.

        Args:
            prefix: Key prefix

        Returns:
            Number of entries deleted
        """
        if not prefix.endswith("."):
            prefix = prefix + "."

        async with self._ensure_lock():
            cursor = await self._db.execute(
                "DELETE FROM config_entries_v2 WHERE config_key LIKE ?",
                (f"{prefix}%",)
            )
            await self._db.commit()
            return cursor.rowcount

    async def save_strategy_params(
        self,
        params: Dict[str, Any],
        version: str = "v1.0.0",
        prefix: str = "strategy"
    ) -> int:
        """
        Save strategy parameters from a nested dictionary.

        Args:
            params: Nested dictionary of parameters
                   e.g., {"pinbar": {"min_wick_ratio": "0.6", ...}, ...}
            version: Version string
            prefix: Key prefix (default 'strategy')

        Returns:
            Number of entries saved
        """
        # Collect all key-value pairs to save
        entries_to_save: list = []

        def flatten(d: Dict[str, Any], parent_key: str = ""):
            for k, v in d.items():
                new_key = f"{parent_key}.{k}" if parent_key else k
                if isinstance(v, dict):
                    flatten(v, new_key)
                else:
                    entries_to_save.append((f"{prefix}.{new_key}", v))

        flatten(params)

        # Save all entries and wait for completion
        for key, value in entries_to_save:
            await self.upsert_entry(key, value, version)

        return len(entries_to_save)

    async def import_from_dict(self, config_dict: Dict[str, Any], version: str = "v1.0.0") -> int:
        """
        Import configuration from a flat dictionary.

        Args:
            config_dict: Dictionary with config_key -> config_value mappings
            version: Version string

        Returns:
            Number of entries imported
        """
        count = 0
        for key, value in config_dict.items():
            await self.upsert_entry(key, value, version)
            count += 1
        return count

    async def export_to_dict(self) -> Dict[str, Any]:
        """
        Export all configuration to a flat dictionary.

        Returns:
            Dictionary with config_key -> config_value mappings
        """
        return await self.get_all_entries()

    # ============================================================
    # Backtest Configuration Methods (KV Mode with Profile Support)
    # ============================================================

    async def get_backtest_configs(self, profile_name: str = 'default') -> Dict[str, Any]:
        """
        Get backtest configuration (KV mode) with profile support.

        Args:
            profile_name: Profile name (default: 'default')

        Returns:
            Dictionary with backtest configuration values

        Default values (applied if KV not exists):
            - slippage_rate: Decimal('0.001')
            - fee_rate: Decimal('0.0004')
            - initial_balance: Decimal('10000')
            - tp_slippage_rate: Decimal('0.0005')
            - funding_rate_enabled: True
            - funding_rate: Decimal('0.0001')  # 0.01% per 8 hours
        """
        # Default configuration values
        DEFAULT_BACKTEST_CONFIG = {
            'backtest.slippage_rate': Decimal('0.001'),
            'backtest.fee_rate': Decimal('0.0004'),
            'backtest.initial_balance': Decimal('10000'),
            'backtest.tp_slippage_rate': Decimal('0.0005'),
            'backtest.funding_rate_enabled': True,
            'backtest.funding_rate': Decimal('0.0001'),  # BT-2: 资金费率 0.01%
            # TTP: Trailing Take Profit 配置（默认关闭）
            'backtest.tp_trailing_enabled': False,
            'backtest.tp_trailing_percent': Decimal('0.01'),
            'backtest.tp_step_threshold': Decimal('0.003'),
            'backtest.tp_trailing_enabled_levels': ['TP1'],
            'backtest.tp_trailing_activation_rr': Decimal('0.5'),
            # Trailing Exit: 追踪退出配置 (ADR-2026-04-20, 默认关闭)
            'backtest.trailing_exit_enabled': False,
            'backtest.trailing_exit_percent': Decimal('0.015'),
            'backtest.trailing_exit_activation_rr': Decimal('0.3'),
            'backtest.trailing_exit_slippage_rate': Decimal('0.001'),
            # Breakeven: TP1 成交后将 SL 移至入场价（默认开启）
            'backtest.breakeven_enabled': True,
        }

        # Get stored configs with prefix and profile
        stored_configs = await self.get_entries_by_prefix_with_profile(
            prefix='backtest',
            profile_name=profile_name
        )

        # Merge with defaults (stored values override defaults)
        result = {}
        for key, default_value in DEFAULT_BACKTEST_CONFIG.items():
            config_key = key.replace('backtest.', '')  # Remove prefix for cleaner key names
            result[config_key] = stored_configs.get(key, default_value)

        return result

    async def save_backtest_configs(
        self,
        configs: Dict[str, Any],
        profile_name: str = 'default',
        version: str = 'v1.0.0'
    ) -> int:
        """
        Save backtest configuration (KV mode) with profile support.

        Args:
            configs: Dictionary of backtest configuration values
                    Keys can be with or without 'backtest.' prefix
            profile_name: Profile name (default: 'default')
            version: Version string (default: 'v1.0.0')

        Returns:
            Number of config entries saved

        Configuration keys:
            - slippage_rate (stored as backtest.slippage_rate)
            - fee_rate (stored as backtest.fee_rate)
            - initial_balance (stored as backtest.initial_balance)
            - tp_slippage_rate (stored as backtest.tp_slippage_rate)
        """
        saved_count = 0

        for key, value in configs.items():
            # Add 'backtest.' prefix if not present
            if not key.startswith('backtest.'):
                full_key = f'backtest.{key}'
            else:
                full_key = key

            await self.upsert_entry_with_profile(
                config_key=full_key,
                config_value=value,
                version=version,
                profile_name=profile_name
            )
            saved_count += 1

        return saved_count

    async def get_entries_by_prefix_with_profile(
        self,
        prefix: str,
        profile_name: str
    ) -> Dict[str, Any]:
        """
        Get all config entries with keys starting with a prefix for a specific profile.

        Args:
            prefix: Key prefix (e.g., 'backtest', 'strategy.pinbar')
            profile_name: Profile name to filter by

        Returns:
            Dictionary mapping config_key -> config_value
        """
        if not prefix.endswith("."):
            prefix = prefix + "."

        async with self._db.execute(
            "SELECT config_key, config_value, value_type FROM config_entries_v2 "
            "WHERE config_key LIKE ? AND profile_name = ? ORDER BY config_key",
            (f"{prefix}%", profile_name)
        ) as cursor:
            rows = await cursor.fetchall()
            result = {}
            for row in rows:
                result[row["config_key"]] = self._deserialize_value(
                    row["config_value"], row["value_type"], row["config_key"]
                )
            return result

    async def upsert_entry_with_profile(
        self,
        config_key: str,
        config_value: Any,
        version: str = "v1.0.0",
        profile_name: str = 'default'
    ) -> int:
        """
        Insert or update a config entry with profile support.

        Args:
            config_key: Configuration key (e.g., 'backtest.slippage_rate')
            config_value: Configuration value (any JSON-serializable type)
            version: Version string
            profile_name: Profile name (default: 'default')

        Returns:
            Config entry ID
        """
        value_type = self._get_value_type(config_value)
        value_str = self._serialize_value(config_value, value_type)
        now = int(datetime.now(timezone.utc).timestamp() * 1000)

        async with self._ensure_lock():
            # Try update first
            cursor = await self._db.execute("""
                UPDATE config_entries_v2
                SET config_value = ?, value_type = ?, version = ?, updated_at = ?
                WHERE config_key = ? AND profile_name = ?
            """, (value_str, value_type, version, now, config_key, profile_name))

            if cursor.rowcount == 0:
                # Insert new entry
                cursor = await self._db.execute("""
                    INSERT INTO config_entries_v2
                    (config_key, config_value, value_type, version, updated_at, profile_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (config_key, value_str, value_type, version, now, profile_name))
                await self._db.commit()
                return cursor.lastrowid

            await self._db.commit()
            return cursor.lastrowid
