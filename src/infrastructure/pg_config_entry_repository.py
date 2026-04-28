"""PostgreSQL config entry repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.logger import logger
from src.infrastructure.pg_models import PGConfigEntryORM


class PgConfigEntryRepository:
    """PG implementation matching ConfigEntryRepository's active API."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    def _get_value_type(self, value: Any) -> str:
        if isinstance(value, Decimal):
            return "decimal"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, (dict, list)):
            return "json"
        return "string"

    def _serialize_value(self, value: Any, value_type: str) -> str:
        if value_type == "decimal":
            return str(value)
        if value_type == "json":
            return json.dumps(value, ensure_ascii=False, default=str)
        if value_type == "boolean":
            return "true" if value else "false"
        return str(value)

    def _deserialize_value(self, value_str: str, value_type: str, config_key: str = "") -> Any:
        try:
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
        except Exception as exc:
            logger.error(f"配置项解析失败 [key={config_key or 'unknown'}]: {exc}, value={value_str[:100]}")
            return None

    async def get_entry(self, config_key: str) -> Optional[dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = (
                select(PGConfigEntryORM)
                .where(PGConfigEntryORM.config_key == config_key)
                .order_by(PGConfigEntryORM.profile_name.asc())
                .limit(1)
            )
            orm = (await session.execute(stmt)).scalar_one_or_none()
            return self._to_entry(orm) if orm else None

    async def upsert_entry(
        self,
        config_key: str,
        config_value: Any,
        version: str = "v1.0.0",
    ) -> int:
        return await self.upsert_entry_with_profile(
            config_key=config_key,
            config_value=config_value,
            version=version,
            profile_name="default",
        )

    async def get_all_entries(self) -> dict[str, Any]:
        async with self._session_maker() as session:
            stmt = select(PGConfigEntryORM).order_by(PGConfigEntryORM.config_key.asc())
            rows = (await session.execute(stmt)).scalars().all()
            return {
                row.config_key: self._deserialize_value(row.config_value, row.value_type, row.config_key)
                for row in rows
                if row.profile_name == "default"
            }

    async def get_entries_by_prefix(self, prefix: str) -> dict[str, Any]:
        return await self.get_entries_by_prefix_with_profile(prefix=prefix, profile_name="default")

    async def delete_entry(self, config_key: str) -> bool:
        async with self._session_maker() as session:
            result = await session.execute(
                delete(PGConfigEntryORM).where(PGConfigEntryORM.config_key == config_key)
            )
            await session.commit()
            return (result.rowcount or 0) > 0

    async def delete_entries_by_prefix(self, prefix: str) -> int:
        if not prefix.endswith("."):
            prefix = prefix + "."
        async with self._session_maker() as session:
            result = await session.execute(
                delete(PGConfigEntryORM).where(PGConfigEntryORM.config_key.like(f"{prefix}%"))
            )
            await session.commit()
            return result.rowcount or 0

    async def save_strategy_params(
        self,
        params: dict[str, Any],
        version: str = "v1.0.0",
        prefix: str = "strategy",
    ) -> int:
        entries: list[tuple[str, Any]] = []

        def flatten(data: dict[str, Any], parent_key: str = "") -> None:
            for key, value in data.items():
                new_key = f"{parent_key}.{key}" if parent_key else key
                if isinstance(value, dict):
                    flatten(value, new_key)
                else:
                    entries.append((f"{prefix}.{new_key}", value))

        flatten(params)
        for key, value in entries:
            await self.upsert_entry(key, value, version)
        return len(entries)

    async def import_from_dict(self, config_dict: dict[str, Any], version: str = "v1.0.0") -> int:
        count = 0
        for key, value in config_dict.items():
            await self.upsert_entry(key, value, version)
            count += 1
        return count

    async def export_to_dict(self) -> dict[str, Any]:
        return await self.get_all_entries()

    async def get_backtest_configs(self, profile_name: str = "default") -> dict[str, Any]:
        defaults = {
            "backtest.slippage_rate": Decimal("0.001"),
            "backtest.fee_rate": Decimal("0.0004"),
            "backtest.initial_balance": Decimal("10000"),
            "backtest.tp_slippage_rate": Decimal("0.0005"),
            "backtest.funding_rate_enabled": True,
            "backtest.funding_rate": Decimal("0.0001"),
            "backtest.tp_trailing_enabled": False,
            "backtest.tp_trailing_percent": Decimal("0.01"),
            "backtest.tp_step_threshold": Decimal("0.003"),
            "backtest.tp_trailing_enabled_levels": ["TP1"],
            "backtest.tp_trailing_activation_rr": Decimal("0.5"),
            "backtest.trailing_exit_enabled": False,
            "backtest.trailing_exit_percent": Decimal("0.015"),
            "backtest.trailing_exit_activation_rr": Decimal("0.3"),
            "backtest.trailing_exit_slippage_rate": Decimal("0.001"),
            "backtest.breakeven_enabled": True,
        }
        stored = await self.get_entries_by_prefix_with_profile("backtest", profile_name)
        return {
            key.replace("backtest.", ""): stored.get(key, value)
            for key, value in defaults.items()
        }

    async def save_backtest_configs(
        self,
        configs: dict[str, Any],
        profile_name: str = "default",
        version: str = "v1.0.0",
    ) -> int:
        count = 0
        for key, value in configs.items():
            full_key = key if key.startswith("backtest.") else f"backtest.{key}"
            await self.upsert_entry_with_profile(full_key, value, version, profile_name)
            count += 1
        return count

    async def get_entries_by_prefix_with_profile(
        self,
        prefix: str,
        profile_name: str,
    ) -> dict[str, Any]:
        if not prefix.endswith("."):
            prefix = prefix + "."
        async with self._session_maker() as session:
            stmt = (
                select(PGConfigEntryORM)
                .where(
                    PGConfigEntryORM.config_key.like(f"{prefix}%"),
                    PGConfigEntryORM.profile_name == profile_name,
                )
                .order_by(PGConfigEntryORM.config_key.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return {
                row.config_key: self._deserialize_value(row.config_value, row.value_type, row.config_key)
                for row in rows
            }

    async def upsert_entry_with_profile(
        self,
        config_key: str,
        config_value: Any,
        version: str = "v1.0.0",
        profile_name: str = "default",
    ) -> int:
        value_type = self._get_value_type(config_value)
        value_str = self._serialize_value(config_value, value_type)
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        async with self._session_maker() as session:
            stmt = (
                pg_insert(PGConfigEntryORM)
                .values(
                    config_key=config_key,
                    config_value=value_str,
                    value_type=value_type,
                    version=version,
                    updated_at=now,
                    profile_name=profile_name,
                )
                .on_conflict_do_update(
                    index_elements=[
                        PGConfigEntryORM.profile_name,
                        PGConfigEntryORM.config_key,
                    ],
                    set_={
                        "config_value": value_str,
                        "value_type": value_type,
                        "version": version,
                        "updated_at": now,
                    },
                )
                .returning(PGConfigEntryORM.id)
            )
            entry_id = (await session.execute(stmt)).scalar_one()
            await session.commit()
            return int(entry_id)

    def _to_entry(self, orm: PGConfigEntryORM) -> dict[str, Any]:
        return {
            "id": orm.id,
            "config_key": orm.config_key,
            "config_value": self._deserialize_value(orm.config_value, orm.value_type, orm.config_key),
            "value_type": orm.value_type,
            "version": orm.version,
            "updated_at": orm.updated_at,
        }
