"""
Config Profile Repository - SQLite persistence for configuration profiles.

配置 Profile 管理：支持多套配置档案的创建、切换、删除等操作。
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import aiosqlite

from src.domain.exceptions import FatalStartupError


class ProfileInfo:
    """Profile 信息数据类"""

    def __init__(
        self,
        name: str,
        description: Optional[str] = None,
        is_active: bool = False,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        created_from: Optional[str] = None,
        config_count: int = 0,
    ):
        self.name = name
        self.description = description
        self.is_active = is_active
        self.created_at = created_at
        self.updated_at = updated_at
        self.created_from = created_from
        self.config_count = config_count

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_from": self.created_from,
            "config_count": self.config_count,
        }

    @classmethod
    def from_row(cls, row: aiosqlite.Row, config_count: int = 0) -> "ProfileInfo":
        """从数据库行创建"""
        return cls(
            name=row["name"],
            description=row["description"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_from=row["created_from"],
            config_count=config_count,
        )


class ConfigProfileRepository:
    """
    SQLite repository for managing configuration profiles.

    核心功能:
    - Profile 列表查询
    - 创建 Profile (支持从现有配置复制)
    - 切换 Profile (原子操作)
    - 删除 Profile
    - 复制 Profile 配置
    """

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        """
        Initialize ConfigProfileRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables.

        注意：迁移脚本应该已经创建了表，这里只做验证。
        """
        # Create connection if not injected
        if self._owns_connection and self._db is None:
            from src.infrastructure.connection_pool import get_connection as pool_get_connection
            self._db = await pool_get_connection(self.db_path)
            # PRAGMAs are set centrally in connection_pool, no need to repeat here

        # 验证 config_profiles 表是否存在
        async with self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='config_profiles'"
        ) as cursor:
            result = await cursor.fetchone()
            if not result:
                raise FatalStartupError(
                    "config_profiles 表不存在，请先运行迁移脚本：python scripts/migrate_to_profiles.py"
                )

        # 验证 config_entries_v2 表有 profile_name 字段
        async with self._db.execute("PRAGMA table_info(config_entries_v2)") as cursor:
            rows = await cursor.fetchall()
            columns = [row[1] for row in rows]
            if "profile_name" not in columns:
                raise FatalStartupError(
                    "config_entries_v2 表缺少 profile_name 字段，请先运行迁移脚本"
                )

        await self._db.commit()

    async def close(self) -> None:
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._db:
            self._db = None

    async def list_profiles(self) -> List[ProfileInfo]:
        """
        获取所有 Profile 列表

        Returns:
            ProfileInfo 列表，包含配置项数量
        """
        async with self._db.execute("""
            SELECT p.*, COUNT(e.config_key) as config_count
            FROM config_profiles p
            LEFT JOIN config_entries_v2 e ON p.name = e.profile_name
            GROUP BY p.name
            ORDER BY p.created_at DESC
        """) as cursor:
            rows = await cursor.fetchall()
            return [ProfileInfo.from_row(row, row["config_count"]) for row in rows]

    async def get_profile(self, name: str) -> Optional[ProfileInfo]:
        """
        获取单个 Profile 详情

        Args:
            name: Profile 名称

        Returns:
            ProfileInfo 或 None
        """
        async with self._db.execute("""
            SELECT p.*, COUNT(e.config_key) as config_count
            FROM config_profiles p
            LEFT JOIN config_entries_v2 e ON p.name = e.profile_name
            WHERE p.name = ?
            GROUP BY p.name
        """, (name,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return ProfileInfo.from_row(row, row["config_count"])
            return None

    async def create_profile(
        self,
        name: str,
        description: Optional[str] = None,
        copy_from: Optional[str] = None,
    ) -> ProfileInfo:
        """
        创建新的 Profile

        Args:
            name: Profile 名称
            description: 描述
            copy_from: 从中复制配置的源 Profile 名称（可选）

        Returns:
            创建的 ProfileInfo

        Raises:
            ValueError: 名称已存在或源 Profile 不存在
        """
        async with self._lock:
            # 检查名称是否已存在
            async with self._db.execute(
                "SELECT name FROM config_profiles WHERE name = ?", (name,)
            ) as cursor:
                if await cursor.fetchone():
                    raise ValueError(f"Profile '{name}' 已存在")

            now = datetime.now(timezone.utc).isoformat()

            # 创建 Profile
            await self._db.execute("""
                INSERT INTO config_profiles (name, description, is_active, created_at, updated_at, created_from)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, description, False, now, now, copy_from))

            # 如果指定了源 Profile，复制配置项
            if copy_from:
                # 验证源 Profile 存在
                async with self._db.execute(
                    "SELECT name FROM config_profiles WHERE name = ?", (copy_from,)
                ) as cursor:
                    if not await cursor.fetchone():
                        await self._db.rollback()
                        raise ValueError(f"源 Profile '{copy_from}' 不存在")

                # 复制配置项
                await self._db.execute("""
                    INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                    SELECT config_key, config_value, value_type, version, updated_at, ?
                    FROM config_entries_v2
                    WHERE profile_name = ?
                """, (name, copy_from))

            await self._db.commit()

            return await self.get_profile(name)

    async def activate_profile(self, name: str) -> None:
        """
        激活指定的 Profile（原子操作）

        Args:
            name: Profile 名称

        Raises:
            ValueError: Profile 不存在
        """
        async with self._lock:
            # 验证 Profile 存在
            async with self._db.execute(
                "SELECT name FROM config_profiles WHERE name = ?", (name,)
            ) as cursor:
                if not await cursor.fetchone():
                    raise ValueError(f"Profile '{name}' 不存在")

            # 事务：先禁用所有，再激活目标
            await self._db.execute("UPDATE config_profiles SET is_active = FALSE")
            await self._db.execute(
                "UPDATE config_profiles SET is_active = TRUE WHERE name = ?",
                (name,)
            )
            await self._db.commit()

    async def get_active_profile(self) -> Optional[ProfileInfo]:
        """
        获取当前激活的 Profile

        Returns:
            激活的 ProfileInfo 或 None
        """
        async with self._db.execute("""
            SELECT p.*, COUNT(e.config_key) as config_count
            FROM config_profiles p
            LEFT JOIN config_entries_v2 e ON p.name = e.profile_name
            WHERE p.is_active = TRUE
            GROUP BY p.name
        """) as cursor:
            row = await cursor.fetchone()
            if row:
                return ProfileInfo.from_row(row, row["config_count"])
            return None

    async def delete_profile(self, name: str) -> bool:
        """
        删除 Profile 及其配置项

        Args:
            name: Profile 名称

        Returns:
            True 如果删除成功

        Raises:
            ValueError: 不能删除 default 或当前激活的 Profile
        """
        # 边界检查
        if name == "default":
            raise ValueError("不能删除 default Profile")

        async with self._lock:
            # 验证 Profile 存在且不是当前激活的
            async with self._db.execute(
                "SELECT name, is_active FROM config_profiles WHERE name = ?", (name,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    raise ValueError(f"Profile '{name}' 不存在")
                if row["is_active"]:
                    raise ValueError(f"不能删除当前激活的 Profile '{name}'")

            # 删除配置项
            await self._db.execute(
                "DELETE FROM config_entries_v2 WHERE profile_name = ?",
                (name,)
            )

            # 删除 Profile
            cursor = await self._db.execute(
                "DELETE FROM config_profiles WHERE name = ?",
                (name,)
            )

            await self._db.commit()
            return cursor.rowcount > 0

    async def rename_profile(
        self,
        old_name: str,
        new_name: str,
        description: Optional[str] = None,
    ) -> ProfileInfo:
        """
        重命名 Profile

        Args:
            old_name: 原 Profile 名称
            new_name: 新 Profile 名称
            description: 新描述（可选）

        Returns:
            重命名后的 ProfileInfo

        Raises:
            ValueError: 不能重命名为 default
        """
        # 边界检查：不能重命名为 default
        if new_name == "default":
            raise ValueError("不能重命名为 'default'")

        async with self._lock:
            # 验证原 Profile 存在
            async with self._db.execute(
                "SELECT name, is_active FROM config_profiles WHERE name = ?", (old_name,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    raise ValueError(f"Profile '{old_name}' 不存在")

            # 更新 Profile 名称和描述
            now = datetime.now(timezone.utc).isoformat()
            await self._db.execute("""
                UPDATE config_profiles
                SET name = ?, description = ?, updated_at = ?
                WHERE name = ?
            """, (new_name, description, now, old_name))

            # 更新配置项中的 profile_name
            await self._db.execute("""
                UPDATE config_entries_v2
                SET profile_name = ?
                WHERE profile_name = ?
            """, (new_name, old_name))

            await self._db.commit()

            return await self.get_profile(new_name)

    async def copy_profile_configs(self, from_name: str, to_name: str) -> int:
        """
        复制一个 Profile 的配置项到另一个 Profile

        Args:
            from_name: 源 Profile 名称
            to_name: 目标 Profile 名称

        Returns:
            复制的配置项数量

        Raises:
            ValueError: 源或目标 Profile 不存在
        """
        async with self._lock:
            # 验证源 Profile 存在
            async with self._db.execute(
                "SELECT name FROM config_profiles WHERE name = ?", (from_name,)
            ) as cursor:
                if not await cursor.fetchone():
                    raise ValueError(f"源 Profile '{from_name}' 不存在")

            # 验证目标 Profile 存在
            async with self._db.execute(
                "SELECT name FROM config_profiles WHERE name = ?", (to_name,)
            ) as cursor:
                if not await cursor.fetchone():
                    raise ValueError(f"目标 Profile '{to_name}' 不存在")

            # 复制配置项
            now = int(datetime.now(timezone.utc).timestamp() * 1000)
            cursor = await self._db.execute("""
                INSERT INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name)
                SELECT config_key, config_value, value_type, version, ?, ?
                FROM config_entries_v2
                WHERE profile_name = ?
            """, (now, to_name, from_name))

            await self._db.commit()
            return cursor.rowcount

    async def get_profile_configs(self, profile_name: str) -> Dict[str, Any]:
        """
        获取指定 Profile 的所有配置项

        Args:
            profile_name: Profile 名称

        Returns:
            配置项字典 {config_key: config_value}
        """
        async with self._db.execute("""
            SELECT config_key, config_value, value_type
            FROM config_entries_v2
            WHERE profile_name = ?
            ORDER BY config_key
        """, (profile_name,)) as cursor:
            rows = await cursor.fetchall()
            result = {}
            for row in rows:
                result[row["config_key"]] = self._deserialize_value(
                    row["config_value"], row["value_type"]
                )
            return result

    def _deserialize_value(self, value_str: str, value_type: str) -> Any:
        """Deserialize value from storage."""
        import json
        from decimal import Decimal

        if value_type == "decimal":
            return Decimal(value_str)
        elif value_type == "boolean":
            return value_str == "true"
        elif value_type == "number":
            try:
                return int(value_str)
            except ValueError:
                return float(value_str)
        elif value_type == "json":
            return json.loads(value_str)
        else:
            return value_str
