"""
Config Snapshot Repository - SQLite persistence for configuration version control.
"""
import asyncio
import os
from datetime import datetime, timezone
from typing import Optional, List, Tuple, Dict, Any

import aiosqlite


class ConfigSnapshotRepository:
    """
    SQLite repository for persisting configuration snapshots.
    Provides version control and rollback capabilities for user configuration.
    """

    def __init__(self, db_path: str = "data/v3_dev.db"):
        """
        Initialize ConfigSnapshotRepository.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables.
        Also creates the data/ directory if it doesn't exist.
        """
        # Create data directory if not exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # Open database connection
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        # Enable WAL mode for high concurrency write support
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.execute("PRAGMA wal_autocheckpoint=1000")
        await self._db.execute("PRAGMA cache_size=-64000")  # 64MB cache

        # Create config_snapshots table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS config_snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                version       TEXT NOT NULL UNIQUE,
                config_json   TEXT NOT NULL,
                description   TEXT DEFAULT '',
                created_at    TEXT NOT NULL,
                created_by    TEXT DEFAULT 'user',
                is_active     INTEGER DEFAULT 0
            )
        """)

        # Create indexes
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_version ON config_snapshots(version)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_active ON config_snapshots(is_active)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON config_snapshots(created_at DESC)
        """)

        # Create config_entries table for strategy parameters (Phase K - Strategy Parameter Configuration)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS config_entries (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                category      TEXT NOT NULL,           -- Config category: 'strategy_params', 'risk_params', etc.
                key           TEXT NOT NULL,           -- Config key within category
                value_json    TEXT NOT NULL,           -- JSON-serialized config value
                description   TEXT DEFAULT '',
                updated_at    TEXT NOT NULL,
                updated_by    TEXT DEFAULT 'user',
                UNIQUE(category, key)
            )
        """)

        # Create indexes for config_entries
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_config_entries_category ON config_entries(category)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_config_entries_key ON config_entries(key)
        """)

        await self._db.commit()

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def create(self, snapshot: Dict[str, Any]) -> int:
        """
        Create a new config snapshot.

        Args:
            snapshot: Snapshot data dict with keys:
                - version: str (semantic version like 'v1.0.0')
                - config_json: str (serialized config)
                - description: str (optional)
                - created_by: str (optional, default 'user')

        Returns:
            Created snapshot ID

        Raises:
            IntegrityError: If version already exists
        """
        async with self._lock:
            now = datetime.now(timezone.utc).isoformat()

            # Deactivate all existing snapshots first
            await self._db.execute("UPDATE config_snapshots SET is_active = 0")

            cursor = await self._db.execute("""
                INSERT INTO config_snapshots
                (version, config_json, description, created_at, created_by, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (
                snapshot["version"],
                snapshot["config_json"],
                snapshot.get("description", ""),
                now,
                snapshot.get("created_by", "user"),
            ))
            await self._db.commit()
            return cursor.lastrowid

    async def get_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        """
        Get snapshot by ID.

        Args:
            id: Snapshot record ID

        Returns:
            Snapshot dict with all fields, or None if not found
        """
        async with self._db.execute(
            "SELECT * FROM config_snapshots WHERE id = ?", (id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_list(
        self,
        limit: int = 20,
        offset: int = 0,
        created_by: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get snapshot list with pagination and optional filters.

        Args:
            limit: Maximum number of results to return
            offset: Number of results to skip
            created_by: Filter by creator (optional)
            is_active: Filter by active status (optional)

        Returns:
            Tuple of (list of snapshot dicts, total count)
        """
        # Build WHERE clause
        where_clauses = []
        params: List[Any] = []

        if created_by:
            where_clauses.append("created_by = ?")
            params.append(created_by)

        if is_active is not None:
            where_clauses.append("is_active = ?")
            params.append(1 if is_active else 0)

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
            data = [dict(row) for row in rows]

        return data, total

    async def get_active(self) -> Optional[Dict[str, Any]]:
        """
        Get the currently active snapshot.

        Returns:
            Active snapshot dict with all fields, or None if not found
        """
        async with self._db.execute(
            "SELECT * FROM config_snapshots WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def set_active(self, id: int) -> bool:
        """
        Set snapshot as active (deactivate all others first).

        Args:
            id: Snapshot record ID

        Returns:
            True if activated successfully, False if not found
        """
        async with self._lock:
            # Check if snapshot exists
            snapshot = await self.get_by_id(id)
            if not snapshot:
                return False

            # Deactivate all
            await self._db.execute("UPDATE config_snapshots SET is_active = 0")

            # Activate target
            await self._db.execute(
                "UPDATE config_snapshots SET is_active = 1 WHERE id = ?",
                (id,)
            )
            await self._db.commit()
            return True

    async def delete(self, id: int) -> bool:
        """
        Delete a snapshot by ID.

        Args:
            id: Snapshot record ID

        Returns:
            True if deleted successfully, False if not found
        """
        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM config_snapshots WHERE id = ?",
                (id,)
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def count(self) -> int:
        """
        Get total number of snapshots.

        Returns:
            Total count of snapshots
        """
        async with self._db.execute("SELECT COUNT(*) FROM config_snapshots") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_recent_snapshots(self, count: int = 5) -> List[int]:
        """
        Get IDs of the most recent N snapshots.

        Args:
            count: Number of recent snapshots to get

        Returns:
            List of snapshot IDs (newest first)
        """
        async with self._db.execute(
            "SELECT id FROM config_snapshots ORDER BY created_at DESC LIMIT ?",
            (count,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def get_active_version(self) -> Optional[str]:
        """
        Get the version of the currently active snapshot.

        Returns:
            Version string or None if no active snapshot
        """
        async with self._db.execute(
            "SELECT version FROM config_snapshots WHERE is_active = 1 LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_versions_for_protection(self, protect_count: int) -> List[str]:
        """
        Get versions of the most recent N snapshots (for protection).

        Args:
            protect_count: Number of recent snapshots to protect

        Returns:
            List of version strings (newest first)
        """
        async with self._db.execute(
            "SELECT version FROM config_snapshots ORDER BY created_at DESC LIMIT ?",
            (protect_count,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    # ============================================================
    # Config Entries Management (Strategy Parameters)
    # ============================================================

    async def get_config_entry(self, category: str, key: str) -> Optional[Dict[str, Any]]:
        """
        Get a single config entry by category and key.

        Args:
            category: Config category (e.g., 'strategy_params')
            key: Config key within category

        Returns:
            Config entry dict with keys: id, category, key, value_json, description, updated_at, updated_by
            or None if not found
        """
        async with self._db.execute(
            "SELECT * FROM config_entries WHERE category = ? AND key = ?",
            (category, key)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_config_entries(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all config entries, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns:
            List of config entry dicts
        """
        if category:
            async with self._db.execute(
                "SELECT * FROM config_entries WHERE category = ? ORDER BY key",
                (category,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        else:
            async with self._db.execute(
                "SELECT * FROM config_entries ORDER BY category, key"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def upsert_config_entry(
        self,
        category: str,
        key: str,
        value_json: str,
        description: str = "",
        updated_by: str = "user"
    ) -> int:
        """
        Insert or update a config entry.

        Args:
            category: Config category
            key: Config key within category
            value_json: JSON-serialized config value
            description: Optional description
            updated_by: User identifier

        Returns:
            Config entry ID
        """
        now = datetime.now(timezone.utc).isoformat()

        async with self._lock:
            # Try update first
            cursor = await self._db.execute("""
                UPDATE config_entries
                SET value_json = ?, description = ?, updated_at = ?, updated_by = ?
                WHERE category = ? AND key = ?
            """, (value_json, description, now, updated_by, category, key))

            if cursor.rowcount == 0:
                # Insert new entry
                cursor = await self._db.execute("""
                    INSERT INTO config_entries (category, key, value_json, description, updated_at, updated_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (category, key, value_json, description, now, updated_by))
                await self._db.commit()
                return cursor.lastrowid

            await self._db.commit()
            return cursor.lastrowid

    async def delete_config_entry(self, category: str, key: str) -> bool:
        """
        Delete a config entry.

        Args:
            category: Config category
            key: Config key within category

        Returns:
            True if deleted successfully, False if not found
        """
        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM config_entries WHERE category = ? AND key = ?",
                (category, key)
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def get_strategy_params(self) -> Optional[Dict[str, Any]]:
        """
        Get strategy parameters config entry.

        Returns:
            Strategy params dict or None if not configured
        """
        entry = await self.get_config_entry('strategy_params', 'default')
        if entry:
            import json
            return json.loads(entry['value_json'])
        return None

    async def save_strategy_params(
        self,
        params: Dict[str, Any],
        description: str = "Strategy parameters",
        updated_by: str = "user"
    ) -> int:
        """
        Save strategy parameters.

        Args:
            params: Strategy params dict
            description: Optional description
            updated_by: User identifier

        Returns:
            Config entry ID
        """
        import json
        return await self.upsert_config_entry(
            category='strategy_params',
            key='default',
            value_json=json.dumps(params),
            description=description,
            updated_by=updated_by
        )
