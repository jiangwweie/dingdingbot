"""
Config Entry Repository - SQLite persistence for strategy parameters.

Phase K: 策略参数配置化 - 数据库存储方案
"""
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union

import aiosqlite

from src.domain.exceptions import FatalStartupError


class ConfigEntryRepository:
    """
    SQLite repository for persisting strategy parameters.

    Config key naming convention:
    - strategy.pinbar.min_wick_ratio
    - strategy.ema.period
    - strategy.mtf.enabled
    - risk.max_loss_percent
    """

    def __init__(self, db_path: str = "data/v3_dev.db"):
        """
        Initialize ConfigEntryRepository.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables.

        Note: For Profile support, the unique constraint is on (profile_name, config_key),
        not just config_key alone.
        """
        # Open database connection
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        # Enable WAL mode for high concurrency write support
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")

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

        # Create composite unique index for Profile support
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
        """Close database connection."""
        if self._db:
            await self._db.close()
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

    def _deserialize_value(self, value_str: str, value_type: str) -> Any:
        """
        Deserialize value from storage.

        Args:
            value_str: JSON string representation
            value_type: Type hint

        Returns:
            Deserialized Python value
        """
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
                    "config_value": self._deserialize_value(row["config_value"], row["value_type"]),
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

        async with self._lock:
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
                    row["config_value"], row["value_type"]
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
                    row["config_value"], row["value_type"]
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
        async with self._lock:
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

        async with self._lock:
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
        count = 0

        def flatten(d: Dict[str, Any], parent_key: str = ""):
            nonlocal count
            for k, v in d.items():
                new_key = f"{parent_key}.{k}" if parent_key else k
                if isinstance(v, dict):
                    flatten(v, new_key)
                else:
                    asyncio.create_task(self.upsert_entry(f"{prefix}.{new_key}", v, version))
                    count += 1

        flatten(params)
        return count

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
