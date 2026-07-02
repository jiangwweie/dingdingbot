"""
Hybrid Signal Repository

目的：
- runtime/research 默认 signals / signal_take_profits / signal_attempts 走 PG
- 仅当测试或旧脚本显式注入 legacy_repo 时保留 SQLite fallback
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
        self._legacy_repo = legacy_repo

    @staticmethod
    def _extract_source(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Optional[str]:
        source = kwargs.get("source")
        request = kwargs.get("request")
        query = kwargs.get("query")
        if request is None and args:
            first = args[0]
            if hasattr(first, "source"):
                request = first
        if query is None and request is None and args:
            first = args[0]
            if hasattr(first, "source"):
                query = first
        request_source = getattr(request, "source", None) if request is not None else None
        query_source = getattr(query, "source", None) if query is not None else None
        return source or request_source or query_source

    def _require_legacy_for_backtest(self, operation: str) -> SignalRepository:
        if self._legacy_repo is None:
            raise RuntimeError(
                f"Backtest signal {operation} requires an explicit legacy_repo. "
                "Inject SignalRepository(...) to keep research/backtest cleanup "
                "isolated from live PG signals."
            )
        return self._legacy_repo

    async def initialize(self) -> None:
        await self._live_repo.initialize()
        if self._legacy_repo is not None:
            await self._legacy_repo.initialize()

    async def close(self) -> None:
        await self._live_repo.close()
        if self._legacy_repo is not None:
            await self._legacy_repo.close()

    def __getattr__(self, name: str) -> Any:
        if self._legacy_repo is None:
            raise AttributeError(
                f"HybridSignalRepository has no route for '{name}'. "
                "Add an explicit PG route or inject legacy_repo for tests."
            )
        return getattr(self._legacy_repo, name)

    async def save_signal(self, *args, **kwargs):
        if self._extract_source(args, kwargs) == "backtest":
            legacy = self._require_legacy_for_backtest("write")
            return await legacy.save_signal(*args, **kwargs)
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
        if self._legacy_repo is None:
            return None
        return await self._legacy_repo.get_signal_by_id(signal_id)

    async def get_stats(self):
        return await self._live_repo.get_stats()

    async def clear_all_signals(self):
        legacy = self._require_legacy_for_backtest("clear_all")
        return await legacy.clear_all_signals()

    async def delete_signals(self, *args, **kwargs):
        if self._extract_source(args, kwargs) == "backtest":
            legacy = self._require_legacy_for_backtest("delete")
            return await legacy.delete_signals(*args, **kwargs)
        return await self._live_repo.delete_signals(*args, **kwargs)

    async def save_attempt(self, *args, **kwargs):
        return await self._live_repo.save_attempt(*args, **kwargs)

    async def get_diagnostics(self, *args, **kwargs):
        return await self._live_repo.get_diagnostics(*args, **kwargs)

    async def get_attempts(self, *args, **kwargs):
        return await self._live_repo.get_attempts(*args, **kwargs)

    async def delete_attempts(self, *args, **kwargs):
        if self._legacy_repo is not None and kwargs.get("use_legacy"):
            kwargs.pop("use_legacy", None)
            return await self._legacy_repo.delete_attempts(*args, **kwargs)
        return await self._live_repo.delete_attempts(*args, **kwargs)

    async def clear_all_attempts(self):
        return await self._live_repo.clear_all_attempts()

    async def get_signals(self, *args, **kwargs):
        if self._extract_source(args, kwargs) == "backtest":
            legacy = self._require_legacy_for_backtest("read")
            return await legacy.get_signals(*args, **kwargs)
        return await self._live_repo.get_signals(*args, **kwargs)
