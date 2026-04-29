"""PostgreSQL runtime profile repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGRuntimeProfileORM
from src.infrastructure.runtime_profile_repository import RuntimeProfile


class PgRuntimeProfileRepository:
    """PG repository for frozen runtime profiles."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def upsert_profile(
        self,
        name: str,
        profile_payload: dict[str, Any],
        *,
        description: Optional[str] = None,
        is_active: bool = False,
        is_readonly: bool = False,
        version: Optional[int] = None,
        allow_readonly_update: bool = False,
    ) -> RuntimeProfile:
        now_ms = self._now_ms()
        async with self._session_maker() as session:
            existing = await self._get_profile(session, name)
            if existing and existing.is_readonly and not allow_readonly_update:
                raise ValueError(f"Cannot modify readonly runtime profile: {name}")

            next_version = version or ((existing.version + 1) if existing else 1)
            created_at = existing.created_at if existing else now_ms

            if is_active:
                await session.execute(update(PGRuntimeProfileORM).values(is_active=False))

            stmt = (
                pg_insert(PGRuntimeProfileORM)
                .values(
                    name=name,
                    description=description,
                    profile_payload=profile_payload,
                    is_active=is_active,
                    is_readonly=is_readonly,
                    created_at=created_at,
                    updated_at=now_ms,
                    version=next_version,
                )
                .on_conflict_do_update(
                    index_elements=[PGRuntimeProfileORM.name],
                    set_={
                        "description": description,
                        "profile_payload": profile_payload,
                        "is_active": is_active,
                        "is_readonly": is_readonly,
                        "updated_at": now_ms,
                        "version": next_version,
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

        profile = await self.get_profile(name)
        if profile is None:
            raise RuntimeError(f"failed to upsert runtime profile: {name}")
        return profile

    async def get_profile(self, name: str) -> Optional[RuntimeProfile]:
        async with self._session_maker() as session:
            return await self._get_profile(session, name)

    async def get_active_profile(self) -> Optional[RuntimeProfile]:
        async with self._session_maker() as session:
            stmt = (
                select(PGRuntimeProfileORM)
                .where(PGRuntimeProfileORM.is_active.is_(True))
                .order_by(PGRuntimeProfileORM.updated_at.desc())
                .limit(1)
            )
            orm = (await session.execute(stmt)).scalar_one_or_none()
            return self._from_orm(orm) if orm else None

    async def list_profiles(self) -> list[RuntimeProfile]:
        async with self._session_maker() as session:
            stmt = select(PGRuntimeProfileORM).order_by(PGRuntimeProfileORM.updated_at.desc())
            rows = (await session.execute(stmt)).scalars().all()
            return [self._from_orm(row) for row in rows]

    async def _get_profile(
        self,
        session: AsyncSession,
        name: str,
    ) -> Optional[RuntimeProfile]:
        orm = await session.get(PGRuntimeProfileORM, name)
        return self._from_orm(orm) if orm else None

    @staticmethod
    def _from_orm(orm: PGRuntimeProfileORM) -> RuntimeProfile:
        return RuntimeProfile(
            name=orm.name,
            description=orm.description,
            profile_payload=orm.profile_payload,
            is_active=bool(orm.is_active),
            is_readonly=bool(orm.is_readonly),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            version=orm.version,
        )

    @staticmethod
    def _now_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
