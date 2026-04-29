import pytest

from src.domain.models import SignalDeleteRequest, SignalQuery
from src.infrastructure.hybrid_signal_repository import HybridSignalRepository


class _FakeSignalRepo:
    def __init__(self):
        self.calls = []

    async def save_signal(self, *args, **kwargs):
        self.calls.append(("save_signal", args, kwargs))
        return "saved"

    async def get_signals(self, *args, **kwargs):
        self.calls.append(("get_signals", args, kwargs))
        return {"total": 0, "data": []}

    async def delete_signals(self, *args, **kwargs):
        self.calls.append(("delete_signals", args, kwargs))
        return 7

    async def clear_all_signals(self):
        self.calls.append(("clear_all_signals", (), {}))
        return 11


@pytest.mark.asyncio
async def test_backtest_write_requires_legacy_repo():
    repo = HybridSignalRepository(live_repo=_FakeSignalRepo(), legacy_repo=None)

    with pytest.raises(RuntimeError, match="Backtest signal write requires"):
        await repo.save_signal(object(), source="backtest")


@pytest.mark.asyncio
async def test_backtest_delete_requires_legacy_repo():
    repo = HybridSignalRepository(live_repo=_FakeSignalRepo(), legacy_repo=None)

    with pytest.raises(RuntimeError, match="Backtest signal delete requires"):
        await repo.delete_signals(request=SignalDeleteRequest(source="backtest"))


@pytest.mark.asyncio
async def test_backtest_read_requires_legacy_repo():
    repo = HybridSignalRepository(live_repo=_FakeSignalRepo(), legacy_repo=None)

    with pytest.raises(RuntimeError, match="Backtest signal read requires"):
        await repo.get_signals(query=SignalQuery(source="backtest"))


@pytest.mark.asyncio
async def test_backtest_routes_to_injected_legacy_repo():
    live = _FakeSignalRepo()
    legacy = _FakeSignalRepo()
    repo = HybridSignalRepository(live_repo=live, legacy_repo=legacy)

    assert await repo.save_signal(object(), source="backtest") == "saved"
    assert await repo.delete_signals(request=SignalDeleteRequest(source="backtest")) == 7
    assert await repo.clear_all_signals() == 11

    assert [call[0] for call in legacy.calls] == [
        "save_signal",
        "delete_signals",
        "clear_all_signals",
    ]
    assert live.calls == []


@pytest.mark.asyncio
async def test_live_routes_to_pg_repo():
    live = _FakeSignalRepo()
    legacy = _FakeSignalRepo()
    repo = HybridSignalRepository(live_repo=live, legacy_repo=legacy)

    assert await repo.save_signal(object(), source="live") == "saved"
    assert await repo.delete_signals(source="live") == 7
    assert await repo.get_signals(source="live") == {"total": 0, "data": []}

    assert [call[0] for call in live.calls] == [
        "save_signal",
        "delete_signals",
        "get_signals",
    ]
    assert legacy.calls == []
