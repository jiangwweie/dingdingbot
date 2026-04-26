"""
Hybrid Signal Repository

目的：
- live signals / signal_take_profits 走 PG
- signal_attempts / config_snapshots / backtest signal helpers 继续走 SQLite
"""

from __future__ import annotations

from typing import Any, Optional

from src.infrastructure.pg_signal_repository import PgSignalRepository
from src.infrastructure.signal_repository import SignalRepository


class HybridSignalRepository:
    """将 live signals 与 legacy attempts/config 分流。"""

    def __init__(
        self,
        *,
        live_repo: Optional[PgSignalRepository] = None,
        legacy_repo: Optional[SignalRepository] = None,
    ) -> None:
        self._live_repo = live_repo or PgSignalRepository()
        self._legacy_repo = legacy_repo or SignalRepository()

    async def initialize(self) -> None:
        await self._legacy_repo.initialize()
        await self._live_repo.initialize()

    async def close(self) -> None:
        await self._live_repo.close()
        await self._legacy_repo.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._legacy_repo, name)

    async def save_signal(self, *args, **kwargs):
        return await self._live_repo.save_signal(*args, **kwargs)

    async def update_signal_status_by_tracker_id(self, *args, **kwargs):
        return await self._live_repo.update_signal_status_by_tracker_id(*args, **kwargs)

    async def update_superseded_by(self, *args, **kwargs):
        return await self._live_repo.update_superseded_by(*args, **kwargs)

    async def get_active_signal(self, *args, **kwargs):
        return await self._live_repo.get_active_signal(*args, **kwargs)

    async def get_opposing_signal(self, *args, **kwargs):
        return await self._live_repo.get_opposing_signal(*args, **kwargs)

    async def get_signal_by_tracker_id(self, *args, **kwargs):
        return await self._live_repo.get_signal_by_tracker_id(*args, **kwargs)

    async def list_active_signals_for_cache_rebuild(self, *args, **kwargs):
        return await self._live_repo.list_active_signals_for_cache_rebuild(*args, **kwargs)

    async def get_pending_signals(self, *args, **kwargs):
        return await self._live_repo.get_pending_signals(*args, **kwargs)

    async def update_signal_status(self, *args, **kwargs):
        return await self._live_repo.update_signal_status(*args, **kwargs)

    async def store_take_profit_levels(self, *args, **kwargs):
        return await self._live_repo.store_take_profit_levels(*args, **kwargs)

    async def get_take_profit_levels(self, *args, **kwargs):
        return await self._live_repo.get_take_profit_levels(*args, **kwargs)

    async def get_signal_by_id(self, signal_id: int):
        signal = await self._live_repo.get_signal_by_id(signal_id)
        if signal is not None:
            return signal
        return await self._legacy_repo.get_signal_by_id(signal_id)

    async def get_stats(self):
        return await self._live_repo.get_stats()

    async def clear_all_signals(self):
        return await self._live_repo.clear_all_signals()

    async def delete_signals(self, *args, **kwargs):
        source = kwargs.get("source")
        request = kwargs.get("request")
        request_source = getattr(request, "source", None) if request is not None else None
        if source == "backtest" or request_source == "backtest":
            return await self._legacy_repo.delete_signals(*args, **kwargs)
        return await self._live_repo.delete_signals(*args, **kwargs)

    async def get_signals(self, *args, **kwargs):
        source = kwargs.get("source")
        query = kwargs.get("query")
        if query is not None and getattr(query, "source", None) is not None:
            source = query.source
        if source == "backtest":
            return await self._legacy_repo.get_signals(*args, **kwargs)
        return await self._live_repo.get_signals(*args, **kwargs)
