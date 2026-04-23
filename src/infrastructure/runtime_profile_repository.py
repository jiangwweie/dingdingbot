"""
SQLite Runtime Profile Repository.

Runtime profiles are frozen, non-secret business configuration bundles used by
Sim/Live startup. Secrets and environment switches remain in .env.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

from src.infrastructure.connection_pool import get_connection


@dataclass(frozen=True)
class RuntimeProfile:
    """Runtime profile row."""

    name: str
    profile_payload: dict[str, Any]
    description: Optional[str] = None
    is_active: bool = False
    is_readonly: bool = False
    created_at: int = 0
    updated_at: int = 0
    version: int = 1


class RuntimeProfileRepository:
    """SQLite repository for frozen runtime profiles."""

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ) -> None:
        self.db_path = db_path
        self._db = connection
        self._owns_connection = connection is None
        self._lock: Optional[asyncio.Lock] = None

    def _ensure_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def initialize(self) -> None:
        """Initialize connection and runtime_profiles table."""
        async with self._ensure_lock():
            if self._db is None and self._owns_connection:
                db_dir = os.path.dirname(self.db_path)
                if db_dir:
                    os.makedirs(db_dir, exist_ok=True)
                self._db = await get_connection(self.db_path)

            await self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_profiles (
                    name TEXT PRIMARY KEY,
                    description TEXT,
                    profile_json TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT FALSE,
                    is_readonly BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            await self._db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runtime_profiles_active
                ON runtime_profiles(is_active)
                """
            )
            await self._db.commit()

    async def close(self) -> None:
        """Clear local connection reference; pool-managed connections stay open."""
        self._db = None

    async def upsert_profile(
        self,
        name: str,
        profile_payload: dict[str, Any],
        *,
        description: Optional[str] = None,
        is_active: bool = False,
        is_readonly: bool = False,
        version: Optional[int] = None,
    ) -> RuntimeProfile:
        """Create or update a runtime profile."""
        self._ensure_initialized()
        now_ms = self._now_ms()
        existing = await self.get_profile(name)
        next_version = version or ((existing.version + 1) if existing else 1)

        if is_active:
            await self._db.execute("UPDATE runtime_profiles SET is_active = FALSE")

        await self._db.execute(
            """
            INSERT INTO runtime_profiles (
                name, description, profile_json, is_active, is_readonly,
                created_at, updated_at, version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                profile_json = excluded.profile_json,
                is_active = excluded.is_active,
                is_readonly = excluded.is_readonly,
                updated_at = excluded.updated_at,
                version = excluded.version
            """,
            (
                name,
                description,
                json.dumps(profile_payload, ensure_ascii=False, sort_keys=True, default=str),
                bool(is_active),
                bool(is_readonly),
                existing.created_at if existing else now_ms,
                now_ms,
                next_version,
            ),
        )
        await self._db.commit()
        profile = await self.get_profile(name)
        if profile is None:
            raise RuntimeError(f"failed to upsert runtime profile: {name}")
        return profile

    async def get_profile(self, name: str) -> Optional[RuntimeProfile]:
        """Get a runtime profile by name."""
        self._ensure_initialized()
        async with self._db.execute(
            """
            SELECT name, description, profile_json, is_active, is_readonly,
                   created_at, updated_at, version
            FROM runtime_profiles
            WHERE name = ?
            """,
            (name,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._from_row(row)

    async def get_active_profile(self) -> Optional[RuntimeProfile]:
        """Get the currently active runtime profile."""
        self._ensure_initialized()
        async with self._db.execute(
            """
            SELECT name, description, profile_json, is_active, is_readonly,
                   created_at, updated_at, version
            FROM runtime_profiles
            WHERE is_active = TRUE
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._from_row(row)

    async def list_profiles(self) -> list[RuntimeProfile]:
        """List all runtime profiles."""
        self._ensure_initialized()
        async with self._db.execute(
            """
            SELECT name, description, profile_json, is_active, is_readonly,
                   created_at, updated_at, version
            FROM runtime_profiles
            ORDER BY updated_at DESC
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._from_row(row) for row in rows]

    def _ensure_initialized(self) -> None:
        if self._db is None:
            raise RuntimeError("RuntimeProfileRepository not initialized")

    @staticmethod
    def _from_row(row: aiosqlite.Row) -> RuntimeProfile:
        return RuntimeProfile(
            name=row["name"],
            description=row["description"],
            profile_payload=json.loads(row["profile_json"]),
            is_active=bool(row["is_active"]),
            is_readonly=bool(row["is_readonly"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=row["version"],
        )

    @staticmethod
    def _now_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)

