"""PostgreSQL config snapshot repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGConfigSnapshotEntryORM, PGConfigSnapshotORM


class PgConfigSnapshotRepository:
    """PG implementation matching ConfigSnapshotRepository's active API."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def create(self, snapshot: dict[str, Any]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        async with self._session_maker() as session:
            await session.execute(update(PGConfigSnapshotORM).values(is_active=False))
            orm = PGConfigSnapshotORM(
                version=snapshot["version"],
                config_json=snapshot["config_json"],
                description=snapshot.get("description", ""),
                created_at=now,
                created_by=snapshot.get("created_by", "user"),
                is_active=True,
            )
            session.add(orm)
            await session.flush()
            new_id = orm.id
            await session.commit()
            return new_id

    async def get_by_id(self, id: int) -> Optional[dict[str, Any]]:
        async with self._session_maker() as session:
            orm = await session.get(PGConfigSnapshotORM, id)
            return self._snapshot_dict(orm) if orm else None

    async def get_list(
        self,
        limit: int = 20,
        offset: int = 0,
        created_by: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        filters = []
        if created_by:
            filters.append(PGConfigSnapshotORM.created_by == created_by)
        if is_active is not None:
            filters.append(PGConfigSnapshotORM.is_active.is_(is_active))

        async with self._session_maker() as session:
            count_stmt = select(func.count()).select_from(PGConfigSnapshotORM)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = (await session.execute(count_stmt)).scalar_one()

            stmt = select(PGConfigSnapshotORM)
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.order_by(PGConfigSnapshotORM.created_at.desc()).limit(limit).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._snapshot_dict(row) for row in rows], total

    async def get_active(self) -> Optional[dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = (
                select(PGConfigSnapshotORM)
                .where(PGConfigSnapshotORM.is_active.is_(True))
                .order_by(PGConfigSnapshotORM.created_at.desc())
                .limit(1)
            )
            orm = (await session.execute(stmt)).scalar_one_or_none()
            return self._snapshot_dict(orm) if orm else None

    async def set_active(self, id: int) -> bool:
        async with self._session_maker() as session:
            if not await session.get(PGConfigSnapshotORM, id):
                return False
            await session.execute(update(PGConfigSnapshotORM).values(is_active=False))
            await session.execute(
                update(PGConfigSnapshotORM).where(PGConfigSnapshotORM.id == id).values(is_active=True)
            )
            await session.commit()
            return True

    async def delete(self, id: int) -> bool:
        async with self._session_maker() as session:
            result = await session.execute(delete(PGConfigSnapshotORM).where(PGConfigSnapshotORM.id == id))
            await session.commit()
            return (result.rowcount or 0) > 0

    async def count(self) -> int:
        async with self._session_maker() as session:
            return (await session.execute(select(func.count()).select_from(PGConfigSnapshotORM))).scalar_one()

    async def get_recent_snapshots(self, count: int = 5) -> list[int]:
        async with self._session_maker() as session:
            stmt = select(PGConfigSnapshotORM.id).order_by(PGConfigSnapshotORM.created_at.desc()).limit(count)
            return list((await session.execute(stmt)).scalars().all())

    async def get_active_version(self) -> Optional[str]:
        async with self._session_maker() as session:
            stmt = select(PGConfigSnapshotORM.version).where(PGConfigSnapshotORM.is_active.is_(True)).limit(1)
            return (await session.execute(stmt)).scalar_one_or_none()

    async def get_versions_for_protection(self, protect_count: int) -> list[str]:
        async with self._session_maker() as session:
            stmt = select(PGConfigSnapshotORM.version).order_by(PGConfigSnapshotORM.created_at.desc()).limit(protect_count)
            return list((await session.execute(stmt)).scalars().all())

    async def get_config_entry(self, category: str, key: str) -> Optional[dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGConfigSnapshotEntryORM).where(
                PGConfigSnapshotEntryORM.category == category,
                PGConfigSnapshotEntryORM.key == key,
            )
            orm = (await session.execute(stmt)).scalar_one_or_none()
            return self._entry_dict(orm) if orm else None

    async def get_config_entries(self, category: Optional[str] = None) -> list[dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGConfigSnapshotEntryORM)
            if category:
                stmt = stmt.where(PGConfigSnapshotEntryORM.category == category)
            stmt = stmt.order_by(PGConfigSnapshotEntryORM.category.asc(), PGConfigSnapshotEntryORM.key.asc())
            rows = (await session.execute(stmt)).scalars().all()
            return [self._entry_dict(row) for row in rows]

    async def upsert_config_entry(
        self,
        category: str,
        key: str,
        value_json: str,
        description: str = "",
        updated_by: str = "user",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        async with self._session_maker() as session:
            stmt = pg_insert(PGConfigSnapshotEntryORM).values(
                category=category,
                key=key,
                value_json=value_json,
                description=description,
                updated_at=now,
                updated_by=updated_by,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[PGConfigSnapshotEntryORM.category, PGConfigSnapshotEntryORM.key],
                set_={
                    "value_json": stmt.excluded.value_json,
                    "description": stmt.excluded.description,
                    "updated_at": stmt.excluded.updated_at,
                    "updated_by": stmt.excluded.updated_by,
                },
            ).returning(PGConfigSnapshotEntryORM.id)
            new_id = (await session.execute(stmt)).scalar_one()
            await session.commit()
            return new_id

    async def delete_config_entry(self, category: str, key: str) -> bool:
        async with self._session_maker() as session:
            result = await session.execute(
                delete(PGConfigSnapshotEntryORM).where(
                    PGConfigSnapshotEntryORM.category == category,
                    PGConfigSnapshotEntryORM.key == key,
                )
            )
            await session.commit()
            return (result.rowcount or 0) > 0

    async def get_strategy_params(self) -> Optional[dict[str, Any]]:
        import json

        entry = await self.get_config_entry("strategy_params", "default")
        return json.loads(entry["value_json"]) if entry else None

    async def save_strategy_params(
        self,
        params: dict[str, Any],
        description: str = "Strategy parameters",
        updated_by: str = "user",
    ) -> int:
        import json

        return await self.upsert_config_entry(
            category="strategy_params",
            key="default",
            value_json=json.dumps(params),
            description=description,
            updated_by=updated_by,
        )

    def _snapshot_dict(self, orm: PGConfigSnapshotORM) -> dict[str, Any]:
        return {
            "id": orm.id,
            "version": orm.version,
            "config_json": orm.config_json,
            "description": orm.description,
            "created_at": orm.created_at,
            "created_by": orm.created_by,
            "is_active": 1 if orm.is_active else 0,
        }

    def _entry_dict(self, orm: PGConfigSnapshotEntryORM) -> dict[str, Any]:
        return {
            "id": orm.id,
            "category": orm.category,
            "key": orm.key,
            "value_json": orm.value_json,
            "description": orm.description,
            "updated_at": orm.updated_at,
            "updated_by": orm.updated_by,
        }
