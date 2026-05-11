"""PG repository for Global Kill Switch v0 state."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGGlobalKillSwitchStateORM
from src.infrastructure.repository_ports import GlobalKillSwitchStateSnapshot


GLOBAL_KILL_SWITCH_STATE_KEY = "global"


class PgGlobalKillSwitchRepository:
    """Single-row PG persistence for the stop-all-new-entries switch."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        await init_pg_core_db()

    async def get_state(self) -> Optional[GlobalKillSwitchStateSnapshot]:
        async with self._session_maker() as session:
            row = await session.get(
                PGGlobalKillSwitchStateORM,
                GLOBAL_KILL_SWITCH_STATE_KEY,
            )
            return self._to_snapshot(row) if row is not None else None

    async def set_state(
        self,
        *,
        active: bool,
        reason: Optional[str],
        updated_by: str,
        updated_at_ms: int,
    ) -> GlobalKillSwitchStateSnapshot:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGGlobalKillSwitchStateORM,
                    GLOBAL_KILL_SWITCH_STATE_KEY,
                    with_for_update=True,
                )
                if row is None:
                    row = PGGlobalKillSwitchStateORM(
                        state_key=GLOBAL_KILL_SWITCH_STATE_KEY,
                        active=active,
                        reason=reason,
                        updated_by=updated_by,
                        updated_at_ms=updated_at_ms,
                    )
                    session.add(row)
                else:
                    row.active = active
                    row.reason = reason
                    row.updated_by = updated_by
                    row.updated_at_ms = updated_at_ms
                await session.flush()
                return self._to_snapshot(row)

    @staticmethod
    def _to_snapshot(row: PGGlobalKillSwitchStateORM) -> GlobalKillSwitchStateSnapshot:
        return GlobalKillSwitchStateSnapshot(
            active=bool(row.active),
            reason=row.reason,
            updated_by=row.updated_by,
            updated_at_ms=int(row.updated_at_ms),
            source="pg",
        )
