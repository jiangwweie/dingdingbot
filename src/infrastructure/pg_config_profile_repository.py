"""PostgreSQL config profile repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.config_profile_repository import ProfileInfo
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGConfigEntryORM, PGConfigProfileORM


class PgConfigProfileRepository:
    """PG implementation matching ConfigProfileRepository's active API."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def list_profiles(self) -> list[ProfileInfo]:
        async with self._session_maker() as session:
            stmt = (
                select(PGConfigProfileORM, func.count(PGConfigEntryORM.config_key).label("config_count"))
                .outerjoin(PGConfigEntryORM, PGConfigProfileORM.name == PGConfigEntryORM.profile_name)
                .group_by(PGConfigProfileORM.name)
                .order_by(PGConfigProfileORM.created_at.desc())
            )
            rows = (await session.execute(stmt)).all()
            return [self._to_profile(profile, count) for profile, count in rows]

    async def get_profile(self, name: str) -> Optional[ProfileInfo]:
        async with self._session_maker() as session:
            stmt = (
                select(PGConfigProfileORM, func.count(PGConfigEntryORM.config_key).label("config_count"))
                .outerjoin(PGConfigEntryORM, PGConfigProfileORM.name == PGConfigEntryORM.profile_name)
                .where(PGConfigProfileORM.name == name)
                .group_by(PGConfigProfileORM.name)
            )
            row = (await session.execute(stmt)).first()
            return self._to_profile(row[0], row[1]) if row else None

    async def create_profile(
        self,
        name: str,
        description: Optional[str] = None,
        copy_from: Optional[str] = None,
    ) -> ProfileInfo:
        now = datetime.now(timezone.utc).isoformat()
        async with self._session_maker() as session:
            if await session.get(PGConfigProfileORM, name):
                raise ValueError(f"Profile '{name}' 已存在")
            if copy_from and not await session.get(PGConfigProfileORM, copy_from):
                raise ValueError(f"源 Profile '{copy_from}' 不存在")

            session.add(
                PGConfigProfileORM(
                    name=name,
                    description=description,
                    is_active=False,
                    created_at=now,
                    updated_at=now,
                    created_from=copy_from,
                )
            )
            if copy_from:
                source_rows = (
                    await session.execute(
                        select(PGConfigEntryORM).where(PGConfigEntryORM.profile_name == copy_from)
                    )
                ).scalars().all()
                for row in source_rows:
                    session.add(
                        PGConfigEntryORM(
                            config_key=row.config_key,
                            config_value=row.config_value,
                            value_type=row.value_type,
                            version=row.version,
                            updated_at=int(datetime.now(timezone.utc).timestamp() * 1000),
                            profile_name=name,
                        )
                    )
            await session.commit()
        profile = await self.get_profile(name)
        if not profile:
            raise ValueError(f"Profile '{name}' 创建后读取失败")
        return profile

    async def activate_profile(self, name: str) -> None:
        async with self._session_maker() as session:
            if not await session.get(PGConfigProfileORM, name):
                raise ValueError(f"Profile '{name}' 不存在")
            await session.execute(update(PGConfigProfileORM).values(is_active=False))
            await session.execute(
                update(PGConfigProfileORM).where(PGConfigProfileORM.name == name).values(is_active=True)
            )
            await session.commit()

    async def get_active_profile(self) -> Optional[ProfileInfo]:
        async with self._session_maker() as session:
            stmt = (
                select(PGConfigProfileORM, func.count(PGConfigEntryORM.config_key).label("config_count"))
                .outerjoin(PGConfigEntryORM, PGConfigProfileORM.name == PGConfigEntryORM.profile_name)
                .where(PGConfigProfileORM.is_active.is_(True))
                .group_by(PGConfigProfileORM.name)
            )
            row = (await session.execute(stmt)).first()
            return self._to_profile(row[0], row[1]) if row else None

    async def delete_profile(self, name: str) -> bool:
        if name == "default":
            raise ValueError("不能删除 default Profile")
        async with self._session_maker() as session:
            profile = await session.get(PGConfigProfileORM, name)
            if not profile:
                raise ValueError(f"Profile '{name}' 不存在")
            if profile.is_active:
                raise ValueError(f"不能删除当前激活的 Profile '{name}'")
            await session.execute(delete(PGConfigEntryORM).where(PGConfigEntryORM.profile_name == name))
            result = await session.execute(delete(PGConfigProfileORM).where(PGConfigProfileORM.name == name))
            await session.commit()
            return (result.rowcount or 0) > 0

    async def rename_profile(
        self,
        old_name: str,
        new_name: str,
        description: Optional[str] = None,
    ) -> ProfileInfo:
        if new_name == "default":
            raise ValueError("不能重命名为 'default'")
        now = datetime.now(timezone.utc).isoformat()
        async with self._session_maker() as session:
            profile = await session.get(PGConfigProfileORM, old_name)
            if not profile:
                raise ValueError(f"Profile '{old_name}' 不存在")
            if await session.get(PGConfigProfileORM, new_name):
                raise ValueError(f"Profile '{new_name}' 已存在")
            profile.name = new_name
            profile.description = description
            profile.updated_at = now
            await session.execute(
                update(PGConfigEntryORM)
                .where(PGConfigEntryORM.profile_name == old_name)
                .values(profile_name=new_name)
            )
            await session.commit()
        renamed = await self.get_profile(new_name)
        if not renamed:
            raise ValueError(f"Profile '{new_name}' 重命名后读取失败")
        return renamed

    async def copy_profile_configs(self, from_name: str, to_name: str) -> int:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        async with self._session_maker() as session:
            if not await session.get(PGConfigProfileORM, from_name):
                raise ValueError(f"源 Profile '{from_name}' 不存在")
            if not await session.get(PGConfigProfileORM, to_name):
                raise ValueError(f"目标 Profile '{to_name}' 不存在")

            rows = (
                await session.execute(select(PGConfigEntryORM).where(PGConfigEntryORM.profile_name == from_name))
            ).scalars().all()
            for row in rows:
                stmt = pg_insert(PGConfigEntryORM).values(
                    config_key=row.config_key,
                    config_value=row.config_value,
                    value_type=row.value_type,
                    version=row.version,
                    updated_at=now_ms,
                    profile_name=to_name,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[PGConfigEntryORM.profile_name, PGConfigEntryORM.config_key],
                    set_={
                        "config_value": stmt.excluded.config_value,
                        "value_type": stmt.excluded.value_type,
                        "version": stmt.excluded.version,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)
            await session.commit()
            return len(rows)

    async def get_profile_configs(self, profile_name: str) -> dict[str, Any]:
        async with self._session_maker() as session:
            rows = (
                await session.execute(
                    select(PGConfigEntryORM)
                    .where(PGConfigEntryORM.profile_name == profile_name)
                    .order_by(PGConfigEntryORM.config_key.asc())
                )
            ).scalars().all()
            return {
                row.config_key: self._deserialize_value(row.config_value, row.value_type)
                for row in rows
            }

    def _deserialize_value(self, value_str: str, value_type: str) -> Any:
        if value_type == "decimal":
            return Decimal(value_str)
        if value_type == "boolean":
            return value_str == "true"
        if value_type == "number":
            try:
                return int(value_str)
            except ValueError:
                return float(value_str)
        if value_type == "json":
            return json.loads(value_str)
        return value_str

    def _to_profile(self, orm: PGConfigProfileORM, config_count: int = 0) -> ProfileInfo:
        return ProfileInfo(
            name=orm.name,
            description=orm.description,
            is_active=bool(orm.is_active),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            created_from=orm.created_from,
            config_count=config_count or 0,
        )
