"""PostgreSQL implementation of legacy config repositories.

This module provides PG implementations for the 7 repositories in config_repositories.py:
- StrategyConfigRepository
- RiskConfigRepository
- SystemConfigRepository
- SymbolConfigRepository
- NotificationConfigRepository
- ConfigSnapshotRepositoryExtended
- ConfigHistoryRepository

Migration strategy:
- Default constructor routes to PG (when MIGRATE_ALL_STATE_TO_PG=true)
- Explicit db_path/connection parameters still use SQLite (for tests)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Tuple

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.exceptions import CryptoMonitorError
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGConfigHistoryORM,
    PGConfigSnapshotExtendedORM,
    PGNotificationConfigORM,
    PGRiskConfigORM,
    PGStrategyConfigORM,
    PGSymbolConfigORM,
    PGSystemConfigORM,
)


# ============================================================
# Exception Classes (same as SQLite version)
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
# PGStrategyConfigRepository
# ============================================================
class PgStrategyConfigRepository:
    """PG implementation of StrategyConfigRepository."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def create(self, strategy: Dict[str, Any]) -> str:
        strategy_id = strategy.get("id") or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        async with self._session_maker() as session:
            # Check for duplicate name
            stmt = select(PGStrategyConfigORM).where(PGStrategyConfigORM.name == strategy["name"])
            if (await session.execute(stmt)).scalar():
                raise ConfigConflictError(
                    f"Strategy name '{strategy['name']}' already exists",
                    "C-101"
                )

            session.add(
                PGStrategyConfigORM(
                    id=strategy_id,
                    name=strategy["name"],
                    description=strategy.get("description"),
                    is_active=True,
                    trigger_config=strategy["trigger_config"],
                    filter_configs=strategy.get("filter_configs", []),
                    filter_logic=strategy.get("filter_logic", "AND"),
                    symbols=strategy.get("symbols", []),
                    timeframes=strategy.get("timeframes", []),
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
            )
            await session.commit()
        return strategy_id

    async def get_by_id(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        async with self._session_maker() as session:
            row = await session.get(PGStrategyConfigORM, strategy_id)
            return self._row_to_dict(row) if row else None

    async def get_list(
        self,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        async with self._session_maker() as session:
            stmt = select(PGStrategyConfigORM)
            if is_active is not None:
                stmt = stmt.where(PGStrategyConfigORM.is_active == is_active)

            # Get total count
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await session.execute(count_stmt)).scalar() or 0

            # Get paginated data
            stmt = stmt.order_by(PGStrategyConfigORM.updated_at.desc()).limit(limit).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()
            data = [self._row_to_dict(row) for row in rows]

        return data, total

    async def update(self, strategy_id: str, updates: Dict[str, Any]) -> bool:
        async with self._session_maker() as session:
            existing = await session.get(PGStrategyConfigORM, strategy_id)
            if not existing:
                return False

            # Check for name conflict if name is being updated
            if "name" in updates and updates["name"] != existing.name:
                stmt = select(PGStrategyConfigORM).where(
                    PGStrategyConfigORM.name == updates["name"],
                    PGStrategyConfigORM.id != strategy_id
                )
                if (await session.execute(stmt)).scalar():
                    raise ConfigConflictError(
                        f"Strategy name '{updates['name']}' already exists",
                        "C-101"
                    )

            now = datetime.now(timezone.utc).isoformat()
            update_dict = {
                "updated_at": now,
                "version": existing.version + 1,
            }

            for key, value in updates.items():
                if key in ("trigger_config", "filter_configs", "symbols", "timeframes"):
                    update_dict[key] = value
                elif key not in ("updated_at", "created_at", "id"):
                    update_dict[key] = value

            stmt = (
                update(PGStrategyConfigORM)
                .where(PGStrategyConfigORM.id == strategy_id)
                .values(**update_dict)
            )
            await session.execute(stmt)
            await session.commit()
        return True

    async def delete(self, strategy_id: str) -> bool:
        async with self._session_maker() as session:
            stmt = delete(PGStrategyConfigORM).where(PGStrategyConfigORM.id == strategy_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def toggle(self, strategy_id: str) -> Optional[bool]:
        async with self._session_maker() as session:
            existing = await session.get(PGStrategyConfigORM, strategy_id)
            if not existing:
                return None

            new_status = not existing.is_active
            now = datetime.now(timezone.utc).isoformat()

            stmt = (
                update(PGStrategyConfigORM)
                .where(PGStrategyConfigORM.id == strategy_id)
                .values(is_active=new_status, updated_at=now)
            )
            await session.execute(stmt)
            await session.commit()
        return new_status

    def _row_to_dict(self, row: PGStrategyConfigORM) -> Dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "is_active": row.is_active,
            "trigger_config": row.trigger_config,
            "filter_configs": row.filter_configs,
            "filter_logic": row.filter_logic,
            "symbols": row.symbols,
            "timeframes": row.timeframes,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "version": row.version,
        }


# ============================================================
# PGRiskConfigRepository
# ============================================================
class PgRiskConfigRepository:
    """PG implementation of RiskConfigRepository."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def get_global(self) -> Optional[Dict[str, Any]]:
        async with self._session_maker() as session:
            row = await session.get(PGRiskConfigORM, "global")
            return self._row_to_dict(row) if row else None

    async def update(self, config: Dict[str, Any]) -> bool:
        async with self._session_maker() as session:
            now = datetime.now(timezone.utc).isoformat()
            existing = await session.get(PGRiskConfigORM, "global")

            if existing:
                update_dict = {
                    "updated_at": now,
                    "version": existing.version + 1,
                }

                for key, value in config.items():
                    if key == "updated_at":
                        continue
                    if key in ("max_loss_percent", "max_total_exposure", "daily_max_loss"):
                        if value is not None:
                            update_dict[key] = str(value)
                    elif key not in ("created_at", "id"):
                        update_dict[key] = value

                stmt = (
                    update(PGRiskConfigORM)
                    .where(PGRiskConfigORM.id == "global")
                    .values(**update_dict)
                )
                await session.execute(stmt)
            else:
                session.add(
                    PGRiskConfigORM(
                        id="global",
                        max_loss_percent=str(config.get("max_loss_percent", Decimal("0.01"))),
                        max_leverage=config.get("max_leverage", 10),
                        max_total_exposure=str(config.get("max_total_exposure", Decimal("0.8"))) if config.get("max_total_exposure") else None,
                        daily_max_trades=config.get("daily_max_trades"),
                        daily_max_loss=str(config.get("daily_max_loss")) if config.get("daily_max_loss") else None,
                        max_position_hold_time=config.get("max_position_hold_time"),
                        cooldown_minutes=config.get("cooldown_minutes", 240),
                        created_at=now,
                        updated_at=now,
                        version=1,
                    )
                )

            await session.commit()
        return True

    def _row_to_dict(self, row: PGRiskConfigORM) -> Dict[str, Any]:
        return {
            "id": row.id,
            "max_loss_percent": Decimal(str(row.max_loss_percent)),
            "max_leverage": row.max_leverage,
            "max_total_exposure": Decimal(str(row.max_total_exposure)) if row.max_total_exposure else None,
            "daily_max_trades": row.daily_max_trades,
            "daily_max_loss": Decimal(str(row.daily_max_loss)) if row.daily_max_loss else None,
            "max_position_hold_time": row.max_position_hold_time,
            "cooldown_minutes": row.cooldown_minutes,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "version": row.version,
        }


# ============================================================
# PGSystemConfigRepository
# ============================================================
class PgSystemConfigRepository:
    """PG implementation of SystemConfigRepository."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def get_global(self) -> Optional[Dict[str, Any]]:
        async with self._session_maker() as session:
            row = await session.get(PGSystemConfigORM, "global")
            return self._row_to_dict(row) if row else None

    async def update(self, config: Dict[str, Any], restart_required: bool = False) -> bool:
        async with self._session_maker() as session:
            now = datetime.now(timezone.utc).isoformat()
            existing = await session.get(PGSystemConfigORM, "global")

            if existing:
                update_dict = {
                    "updated_at": now,
                }

                for key, value in config.items():
                    if key in ("core_symbols", "mtf_mapping"):
                        update_dict[key] = value
                    elif key not in ("updated_at", "created_at", "id"):
                        update_dict[key] = value

                if restart_required:
                    update_dict["restart_required"] = True

                stmt = (
                    update(PGSystemConfigORM)
                    .where(PGSystemConfigORM.id == "global")
                    .values(**update_dict)
                )
                await session.execute(stmt)
            else:
                session.add(
                    PGSystemConfigORM(
                        id="global",
                        core_symbols=config.get("core_symbols", ["BTC/USDT:USDT", "ETH/USDT:USDT"]),
                        ema_period=config.get("ema_period", 60),
                        mtf_ema_period=config.get("mtf_ema_period", 60),
                        mtf_mapping=config.get("mtf_mapping", {"15m": "1h", "1h": "4h", "4h": "1d"}),
                        signal_cooldown_seconds=config.get("signal_cooldown_seconds", 14400),
                        queue_batch_size=config.get("queue_batch_size", 10),
                        queue_flush_interval=config.get("queue_flush_interval", Decimal("5.0")),
                        queue_max_size=config.get("queue_max_size", 1000),
                        warmup_history_bars=config.get("warmup_history_bars", 100),
                        atr_filter_enabled=config.get("atr_filter_enabled", True),
                        atr_period=config.get("atr_period", 14),
                        atr_min_ratio=config.get("atr_min_ratio", Decimal("0.5")),
                        restart_required=restart_required,
                        created_at=now,
                        updated_at=now,
                    )
                )

            await session.commit()
        return True

    def _row_to_dict(self, row: PGSystemConfigORM) -> Dict[str, Any]:
        return {
            "id": row.id,
            "core_symbols": row.core_symbols,
            "ema_period": row.ema_period,
            "mtf_ema_period": row.mtf_ema_period,
            "mtf_mapping": row.mtf_mapping,
            "signal_cooldown_seconds": row.signal_cooldown_seconds,
            "queue_batch_size": row.queue_batch_size,
            "queue_flush_interval": Decimal(str(row.queue_flush_interval)) if row.queue_flush_interval else Decimal("5.0"),
            "queue_max_size": row.queue_max_size,
            "warmup_history_bars": row.warmup_history_bars,
            "atr_filter_enabled": row.atr_filter_enabled,
            "atr_period": row.atr_period,
            "atr_min_ratio": Decimal(str(row.atr_min_ratio)) if row.atr_min_ratio else Decimal("0.5"),
            "restart_required": row.restart_required,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


# ============================================================
# PGSymbolConfigRepository
# ============================================================
class PgSymbolConfigRepository:
    """PG implementation of SymbolConfigRepository."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def get_all(self) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGSymbolConfigORM).order_by(PGSymbolConfigORM.symbol)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(row) for row in rows]

    async def get_active(self) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGSymbolConfigORM).where(PGSymbolConfigORM.is_active == True).order_by(PGSymbolConfigORM.symbol)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(row) for row in rows]

    async def get_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        async with self._session_maker() as session:
            row = await session.get(PGSymbolConfigORM, symbol)
            return self._row_to_dict(row) if row else None

    async def create(self, symbol_config: Dict[str, Any]) -> bool:
        async with self._session_maker() as session:
            existing = await session.get(PGSymbolConfigORM, symbol_config["symbol"])
            if existing:
                raise ConfigConflictError(
                    f"Symbol '{symbol_config['symbol']}' already exists",
                    "C-102"
                )

            now = datetime.now(timezone.utc).isoformat()
            session.add(
                PGSymbolConfigORM(
                    symbol=symbol_config["symbol"],
                    is_active=symbol_config.get("is_active", True),
                    is_core=symbol_config.get("is_core", False),
                    min_quantity=symbol_config.get("min_quantity"),
                    price_precision=symbol_config.get("price_precision"),
                    quantity_precision=symbol_config.get("quantity_precision"),
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
        return True

    async def update(self, symbol: str, updates: Dict[str, Any]) -> bool:
        async with self._session_maker() as session:
            existing = await session.get(PGSymbolConfigORM, symbol)
            if not existing:
                return False

            now = datetime.now(timezone.utc).isoformat()
            update_dict = {"updated_at": now}

            for key, value in updates.items():
                if key not in ("updated_at", "created_at", "symbol"):
                    update_dict[key] = value

            stmt = (
                update(PGSymbolConfigORM)
                .where(PGSymbolConfigORM.symbol == symbol)
                .values(**update_dict)
            )
            await session.execute(stmt)
            await session.commit()
        return True

    async def delete(self, symbol: str) -> bool:
        async with self._session_maker() as session:
            existing = await session.get(PGSymbolConfigORM, symbol)
            if not existing:
                return False

            # Cannot delete core symbols
            if existing.is_core:
                raise ConfigValidationError(
                    f"Cannot delete core symbol '{symbol}'",
                    "C-103"
                )

            stmt = delete(PGSymbolConfigORM).where(PGSymbolConfigORM.symbol == symbol)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def toggle(self, symbol: str) -> Optional[bool]:
        async with self._session_maker() as session:
            existing = await session.get(PGSymbolConfigORM, symbol)
            if not existing:
                return None

            new_status = not existing.is_active
            now = datetime.now(timezone.utc).isoformat()

            stmt = (
                update(PGSymbolConfigORM)
                .where(PGSymbolConfigORM.symbol == symbol)
                .values(is_active=new_status, updated_at=now)
            )
            await session.execute(stmt)
            await session.commit()
        return new_status

    async def add_core_symbols(self, symbols: List[str]) -> int:
        async with self._session_maker() as session:
            now = datetime.now(timezone.utc).isoformat()
            added_count = 0

            for symbol in symbols:
                existing = await session.get(PGSymbolConfigORM, symbol)
                if not existing:
                    session.add(
                        PGSymbolConfigORM(
                            symbol=symbol,
                            is_active=True,
                            is_core=True,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    added_count += 1
                elif not existing.is_core:
                    stmt = (
                        update(PGSymbolConfigORM)
                        .where(PGSymbolConfigORM.symbol == symbol)
                        .values(is_core=True, updated_at=now)
                    )
                    await session.execute(stmt)

            await session.commit()
        return added_count

    def _row_to_dict(self, row: PGSymbolConfigORM) -> Dict[str, Any]:
        return {
            "symbol": row.symbol,
            "is_active": row.is_active,
            "is_core": row.is_core,
            "min_quantity": Decimal(str(row.min_quantity)) if row.min_quantity else None,
            "price_precision": row.price_precision,
            "quantity_precision": row.quantity_precision,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


# ============================================================
# PGNotificationConfigRepository
# ============================================================
class PgNotificationConfigRepository:
    """PG implementation of NotificationConfigRepository."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def create(self, notification: Dict[str, Any]) -> str:
        notification_id = notification.get("id") or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        async with self._session_maker() as session:
            session.add(
                PGNotificationConfigORM(
                    id=notification_id,
                    channel_type=notification["channel_type"],
                    webhook_url=notification["webhook_url"],
                    is_active=notification.get("is_active", True),
                    notify_on_signal=notification.get("notify_on_signal", True),
                    notify_on_order=notification.get("notify_on_order", True),
                    notify_on_error=notification.get("notify_on_error", True),
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
        return notification_id

    async def get_by_id(self, notification_id: str) -> Optional[Dict[str, Any]]:
        async with self._session_maker() as session:
            row = await session.get(PGNotificationConfigORM, notification_id)
            return self._row_to_dict(row) if row else None

    async def get_list(
        self,
        channel_type: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGNotificationConfigORM)
            if channel_type:
                stmt = stmt.where(PGNotificationConfigORM.channel_type == channel_type)
            if is_active is not None:
                stmt = stmt.where(PGNotificationConfigORM.is_active == is_active)
            stmt = stmt.order_by(PGNotificationConfigORM.created_at.desc())
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(row) for row in rows]

    async def get_notifications(self) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGNotificationConfigORM).order_by(PGNotificationConfigORM.created_at.desc())
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(row) for row in rows]

    async def get_active_channels(self) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGNotificationConfigORM).where(PGNotificationConfigORM.is_active == True).order_by(PGNotificationConfigORM.channel_type)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(row) for row in rows]

    async def update(self, notification_id: str, updates: Dict[str, Any]) -> bool:
        async with self._session_maker() as session:
            existing = await session.get(PGNotificationConfigORM, notification_id)
            if not existing:
                return False

            now = datetime.now(timezone.utc).isoformat()
            update_dict = {"updated_at": now}

            for key, value in updates.items():
                if key not in ("updated_at", "created_at", "id"):
                    update_dict[key] = value

            stmt = (
                update(PGNotificationConfigORM)
                .where(PGNotificationConfigORM.id == notification_id)
                .values(**update_dict)
            )
            await session.execute(stmt)
            await session.commit()
        return True

    async def delete(self, notification_id: str) -> bool:
        async with self._session_maker() as session:
            stmt = delete(PGNotificationConfigORM).where(PGNotificationConfigORM.id == notification_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def test_connection(self, notification_id: str) -> Dict[str, Any]:
        notification = await self.get_by_id(notification_id)
        if not notification:
            return {
                "success": False,
                "message": f"Notification '{notification_id}' not found",
                "channel_type": None
            }

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

    def _row_to_dict(self, row: PGNotificationConfigORM) -> Dict[str, Any]:
        return {
            "id": row.id,
            "channel_type": row.channel_type,
            "webhook_url": row.webhook_url,
            "is_active": row.is_active,
            "notify_on_signal": row.notify_on_signal,
            "notify_on_order": row.notify_on_order,
            "notify_on_error": row.notify_on_error,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


# ============================================================
# PGConfigHistoryRepository
# ============================================================
class PgConfigHistoryRepository:
    """PG implementation of ConfigHistoryRepository."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def record_change(
        self,
        entity_type: str,
        entity_id: str,
        action: Literal["CREATE", "UPDATE", "DELETE", "ROLLBACK"],
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        old_full_snapshot: Optional[Dict[str, Any]] = None,
        new_full_snapshot: Optional[Dict[str, Any]] = None,
        changed_by: str = "user",
        change_summary: Optional[str] = None
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()

        async with self._session_maker() as session:
            row = PGConfigHistoryORM(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                old_values=old_values,
                new_values=new_values,
                old_full_snapshot=old_full_snapshot,
                new_full_snapshot=new_full_snapshot,
                changed_by=changed_by,
                changed_at=now,
                change_summary=change_summary,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def get_history(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        async with self._session_maker() as session:
            stmt = select(PGConfigHistoryORM)
            if entity_type:
                stmt = stmt.where(PGConfigHistoryORM.entity_type == entity_type)
            if entity_id:
                stmt = stmt.where(PGConfigHistoryORM.entity_id == entity_id)

            # Get total count
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await session.execute(count_stmt)).scalar() or 0

            # Get paginated data
            stmt = stmt.order_by(PGConfigHistoryORM.changed_at.desc()).limit(limit).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()
            data = [self._row_to_dict(row) for row in rows]

        return data, total

    async def get_entity_history(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 20,
        action: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGConfigHistoryORM).where(
                PGConfigHistoryORM.entity_type == entity_type,
                PGConfigHistoryORM.entity_id == entity_id,
            )
            if action:
                stmt = stmt.where(PGConfigHistoryORM.action == action)
            if start_date:
                stmt = stmt.where(PGConfigHistoryORM.changed_at >= start_date)
            if end_date:
                stmt = stmt.where(PGConfigHistoryORM.changed_at <= end_date)

            stmt = stmt.order_by(PGConfigHistoryORM.changed_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(row) for row in rows]

    async def get_recent_changes(
        self,
        limit: int = 20,
        changed_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGConfigHistoryORM)
            if changed_by:
                stmt = stmt.where(PGConfigHistoryORM.changed_by == changed_by)
            stmt = stmt.order_by(PGConfigHistoryORM.changed_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(row) for row in rows]

    async def get_changes_summary(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict[str, Any]:
        async with self._session_maker() as session:
            stmt = select(PGConfigHistoryORM)
            if start_time:
                stmt = stmt.where(PGConfigHistoryORM.changed_at >= start_time)
            if end_time:
                stmt = stmt.where(PGConfigHistoryORM.changed_at <= end_time)

            # Get total changes
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await session.execute(count_stmt)).scalar() or 0

            # Get changes by action type
            action_stmt = select(
                PGConfigHistoryORM.action,
                func.count().label("count")
            ).select_from(stmt.subquery()).group_by(PGConfigHistoryORM.action)
            action_rows = (await session.execute(action_stmt)).all()
            changes_by_action = {row.action: row.count for row in action_rows}

            # Get changes by entity type
            entity_stmt = select(
                PGConfigHistoryORM.entity_type,
                func.count().label("count")
            ).select_from(stmt.subquery()).group_by(PGConfigHistoryORM.entity_type)
            entity_rows = (await session.execute(entity_stmt)).all()
            changes_by_entity = {row.entity_type: row.count for row in entity_rows}

            # Get changes by user
            user_stmt = select(
                PGConfigHistoryORM.changed_by,
                func.count().label("count")
            ).select_from(stmt.subquery()).group_by(PGConfigHistoryORM.changed_by)
            user_rows = (await session.execute(user_stmt)).all()
            changes_by_user = {row.changed_by or "unknown": row.count for row in user_rows}

        return {
            "total_changes": total,
            "changes_by_action": changes_by_action,
            "changes_by_entity": changes_by_entity,
            "changes_by_user": changes_by_user,
        }

    async def get_rollback_candidates(self, entity_type: str, entity_id: str) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGConfigHistoryORM).where(
                PGConfigHistoryORM.entity_type == entity_type,
                PGConfigHistoryORM.entity_id == entity_id,
                PGConfigHistoryORM.action.in_(["CREATE", "UPDATE"]),
            ).order_by(PGConfigHistoryORM.changed_at.desc())
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: PGConfigHistoryORM) -> Dict[str, Any]:
        return {
            "id": row.id,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "action": row.action,
            "old_values": row.old_values,
            "new_values": row.new_values,
            "changed_by": row.changed_by,
            "changed_at": row.changed_at,
            "change_summary": row.change_summary,
        }


# ============================================================
# PGConfigSnapshotRepositoryExtended
# ============================================================
class PgConfigSnapshotRepositoryExtended:
    """PG implementation of ConfigSnapshotRepositoryExtended."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def create(self, snapshot: Dict[str, Any]) -> str:
        snapshot_id = snapshot.get("id") or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        async with self._session_maker() as session:
            session.add(
                PGConfigSnapshotExtendedORM(
                    id=snapshot_id,
                    name=snapshot["name"],
                    description=snapshot.get("description"),
                    snapshot_data=snapshot["snapshot_data"],
                    created_at=now,
                    created_by=snapshot.get("created_by", "user"),
                    is_auto=snapshot.get("is_auto", False),
                )
            )
            await session.commit()
        return snapshot_id

    async def get_by_id(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        async with self._session_maker() as session:
            row = await session.get(PGConfigSnapshotExtendedORM, snapshot_id)
            return self._row_to_dict(row) if row else None

    async def get_list(
        self,
        limit: int = 20,
        offset: int = 0,
        is_auto: Optional[bool] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        async with self._session_maker() as session:
            stmt = select(PGConfigSnapshotExtendedORM)
            if is_auto is not None:
                stmt = stmt.where(PGConfigSnapshotExtendedORM.is_auto == is_auto)

            # Get total count
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = (await session.execute(count_stmt)).scalar() or 0

            # Get paginated data
            stmt = stmt.order_by(PGConfigSnapshotExtendedORM.created_at.desc()).limit(limit).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()
            data = [self._row_to_dict(row) for row in rows]

        return data, total

    async def delete(self, snapshot_id: str) -> bool:
        async with self._session_maker() as session:
            stmt = delete(PGConfigSnapshotExtendedORM).where(PGConfigSnapshotExtendedORM.id == snapshot_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def get_recent(self, count: int = 5) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            stmt = select(PGConfigSnapshotExtendedORM).order_by(PGConfigSnapshotExtendedORM.created_at.desc()).limit(count)
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: PGConfigSnapshotExtendedORM) -> Dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "config_data": row.snapshot_data,  # API expects config_data
            "created_at": row.created_at,
            "updated_at": row.created_at,  # Use created_at as updated_at (no updates)
            "created_by": row.created_by,
            "is_auto": row.is_auto,
        }