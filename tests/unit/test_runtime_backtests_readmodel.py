"""Unit tests for Runtime Backtests readmodel (GET /api/research/backtests)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.application.readmodels.runtime_backtests import RuntimeBacktestsReadModel


@pytest.fixture
def readmodel():
    return RuntimeBacktestsReadModel()


class TestEmptyRepo:
    async def test_no_repo_returns_empty(self, readmodel):
        """No repo → empty backtests list."""
        result = await readmodel.build(backtest_repo=None)
        assert result.backtests == []

    async def test_repo_returns_empty_reports(self, readmodel):
        """Repo with empty reports → empty list."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value={"reports": []})
        result = await readmodel.build(backtest_repo=repo)
        assert result.backtests == []

    async def test_repo_exception_propagates(self, readmodel):
        """Repo raises exception → exception propagates (not swallowed as empty list)."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(side_effect=Exception("db error"))
        with pytest.raises(Exception, match="db error"):
            await readmodel.build(backtest_repo=repo)

    async def test_repo_returns_non_dict(self, readmodel):
        """Repo returns non-dict → empty list (graceful degradation)."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value="not a dict")
        result = await readmodel.build(backtest_repo=repo)
        assert result.backtests == []


class TestSingleMapping:
    async def test_single_report_maps_correctly(self, readmodel):
        """A single report maps to a ConsoleBacktestItem with correct fields."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value={
            "reports": [
                {
                    "id": "bt_001",
                    "strategy_id": "alpha_v2",
                    "strategy_name": "Alpha V2",
                    "symbol": "ETH/USDT:USDT",
                    "timeframe": "1h",
                    "backtest_start": 1745270400000,
                    "backtest_end": 1747862400000,
                    "total_return": 0.45,
                    "sharpe_ratio": 2.1,
                    "max_drawdown": 0.15,
                    "win_rate": 0.54,
                    "total_trades": 1250,
                }
            ]
        })
        result = await readmodel.build(backtest_repo=repo)
        assert len(result.backtests) == 1
        bt = result.backtests[0]
        assert bt.id == "bt_001"
        assert bt.candidate_ref == "alpha_v2"
        assert bt.symbol == "ETH/USDT:USDT"
        assert bt.timeframe == "1h"
        assert bt.start_date == "2025-04-21"
        assert bt.end_date == "2025-05-21"
        assert bt.status == "COMPLETED"
        assert bt.metrics.total_return == 0.45
        assert bt.metrics.sharpe == 2.1
        assert bt.metrics.max_drawdown == 0.15
        assert bt.metrics.win_rate == 0.54
        assert bt.metrics.trades == 1250

    async def test_fallback_to_strategy_name(self, readmodel):
        """When strategy_id is missing, candidate_ref falls back to strategy_name."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value={
            "reports": [
                {
                    "id": "bt_002",
                    "strategy_name": "Pinbar Classic",
                    "symbol": "BTC/USDT:USDT",
                    "timeframe": "15m",
                }
            ]
        })
        result = await readmodel.build(backtest_repo=repo)
        assert result.backtests[0].candidate_ref == "Pinbar Classic"


class TestMissingMetrics:
    async def test_missing_metrics_fields_are_null(self, readmodel):
        """Report with no metrics fields → all metrics are None (not 0)."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value={
            "reports": [
                {
                    "id": "bt_003",
                    "symbol": "SOL/USDT:USDT",
                    "timeframe": "4h",
                }
            ]
        })
        result = await readmodel.build(backtest_repo=repo)
        bt = result.backtests[0]
        assert bt.metrics.total_return is None
        assert bt.metrics.sharpe is None
        assert bt.metrics.max_drawdown is None
        assert bt.metrics.win_rate is None
        assert bt.metrics.trades is None

    async def test_partial_metrics(self, readmodel):
        """Report with some metrics fields → others are None."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value={
            "reports": [
                {
                    "id": "bt_004",
                    "symbol": "BTC/USDT:USDT",
                    "timeframe": "1h",
                    "total_return": 0.32,
                    "total_trades": 500,
                }
            ]
        })
        result = await readmodel.build(backtest_repo=repo)
        bt = result.backtests[0]
        assert bt.metrics.total_return == 0.32
        assert bt.metrics.trades == 500
        assert bt.metrics.sharpe is None
        assert bt.metrics.win_rate is None

    async def test_none_metrics_fields(self, readmodel):
        """Report with explicit None metrics fields → preserved as None."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value={
            "reports": [
                {
                    "id": "bt_005",
                    "symbol": "ETH/USDT:USDT",
                    "timeframe": "15m",
                    "total_return": None,
                    "sharpe_ratio": None,
                    "total_trades": None,
                }
            ]
        })
        result = await readmodel.build(backtest_repo=repo)
        bt = result.backtests[0]
        assert bt.metrics.total_return is None
        assert bt.metrics.sharpe is None
        assert bt.metrics.trades is None


class TestRealZero:
    async def test_real_zero_preserved(self, readmodel):
        """Backend returns actual 0 → preserved as 0, not None."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value={
            "reports": [
                {
                    "id": "bt_006",
                    "symbol": "BTC/USDT:USDT",
                    "timeframe": "1h",
                    "total_return": 0,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0,
                    "win_rate": 0.0,
                    "total_trades": 0,
                }
            ]
        })
        result = await readmodel.build(backtest_repo=repo)
        bt = result.backtests[0]
        assert bt.metrics.total_return == 0.0
        assert bt.metrics.sharpe == 0.0
        assert bt.metrics.max_drawdown == 0.0
        assert bt.metrics.win_rate == 0.0
        assert bt.metrics.trades == 0


class TestStatusStability:
    async def test_status_always_completed(self, readmodel):
        """Existing reports always map to COMPLETED status."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value={
            "reports": [
                {"id": "bt_a", "symbol": "A", "timeframe": "1h"},
                {"id": "bt_b", "symbol": "B", "timeframe": "4h"},
            ]
        })
        result = await readmodel.build(backtest_repo=repo)
        for bt in result.backtests:
            assert bt.status == "COMPLETED"


class TestLimit:
    async def test_limit_applied(self, readmodel):
        """Limit truncates the result."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value={
            "reports": [
                {"id": f"bt_{i}", "symbol": "ETH", "timeframe": "1h"}
                for i in range(10)
            ]
        })
        result = await readmodel.build(backtest_repo=repo, limit=3)
        assert len(result.backtests) == 3


class TestRouteLevel:
    def test_backtests_endpoint_exists_on_router(self):
        """GET /api/research/backtests is registered on the research router."""
        from src.interfaces.api_console_research import router

        route_paths = [r.path for r in router.routes]
        assert "/api/research/backtests" in route_paths

    def test_backtests_endpoint_returns_empty_when_no_data(self):
        """Endpoint returns { "backtests": [] } when repo has no data."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from src.interfaces.api_console_research import router

        fake_repo = AsyncMock()
        fake_repo.list_reports = AsyncMock(return_value={"reports": []})
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()

        with patch(
            "src.infrastructure.backtest_repository.BacktestReportRepository",
            return_value=fake_repo,
        ):
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.get("/api/research/backtests")
            assert response.status_code == 200
            data = response.json()
            assert "backtests" in data
            assert isinstance(data["backtests"], list)
            assert len(data["backtests"]) == 0

    def test_backtests_endpoint_returns_data(self):
        """Endpoint returns backtest records from repo."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from src.interfaces.api_console_research import router

        fake_repo = AsyncMock()
        fake_repo.list_reports = AsyncMock(return_value={
            "reports": [
                {
                    "id": "bt_test",
                    "strategy_id": "alpha",
                    "symbol": "ETH/USDT:USDT",
                    "timeframe": "1h",
                    "backtest_start": 1745270400000,
                    "backtest_end": 1747862400000,
                    "total_return": 0.45,
                    "sharpe_ratio": 2.1,
                    "max_drawdown": 0.15,
                    "win_rate": 0.54,
                    "total_trades": 1250,
                }
            ]
        })
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()

        with patch(
            "src.infrastructure.backtest_repository.BacktestReportRepository",
            return_value=fake_repo,
        ):
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.get("/api/research/backtests")
            assert response.status_code == 200
            data = response.json()
            assert len(data["backtests"]) == 1
            bt = data["backtests"][0]
            assert bt["id"] == "bt_test"
            assert bt["candidate_ref"] == "alpha"
            assert bt["status"] == "COMPLETED"
            assert bt["metrics"]["total_return"] == 0.45

    def test_backtests_endpoint_returns_500_on_repo_error(self):
        """Endpoint returns 500 when repo raises exception (not empty list)."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from src.interfaces.api_console_research import router

        fake_repo = AsyncMock()
        fake_repo.list_reports = AsyncMock(side_effect=Exception("db connection lost"))
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()

        with patch(
            "src.infrastructure.backtest_repository.BacktestReportRepository",
            return_value=fake_repo,
        ):
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app, raise_server_exceptions=False)

            response = client.get("/api/research/backtests")
            assert response.status_code == 500

    def test_backtests_endpoint_null_metrics_in_json(self):
        """Endpoint returns null for missing metrics (not 0)."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from src.interfaces.api_console_research import router

        fake_repo = AsyncMock()
        fake_repo.list_reports = AsyncMock(return_value={
            "reports": [
                {
                    "id": "bt_null",
                    "strategy_id": "test",
                    "symbol": "ETH/USDT:USDT",
                    "timeframe": "1h",
                }
            ]
        })
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()

        with patch(
            "src.infrastructure.backtest_repository.BacktestReportRepository",
            return_value=fake_repo,
        ):
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.get("/api/research/backtests")
            assert response.status_code == 200
            bt = response.json()["backtests"][0]
            assert bt["metrics"]["total_return"] is None
            assert bt["metrics"]["sharpe"] is None
            assert bt["metrics"]["max_drawdown"] is None
            assert bt["metrics"]["win_rate"] is None
            assert bt["metrics"]["trades"] is None

    def test_backtests_endpoint_real_zero_preserved_in_json(self):
        """Endpoint preserves actual 0 values (not converting to null)."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from src.interfaces.api_console_research import router

        fake_repo = AsyncMock()
        fake_repo.list_reports = AsyncMock(return_value={
            "reports": [
                {
                    "id": "bt_zero",
                    "strategy_id": "test",
                    "symbol": "ETH/USDT:USDT",
                    "timeframe": "1h",
                    "total_return": 0,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0,
                    "win_rate": 0.0,
                    "total_trades": 0,
                }
            ]
        })
        fake_repo.initialize = AsyncMock()
        fake_repo.close = AsyncMock()

        with patch(
            "src.infrastructure.backtest_repository.BacktestReportRepository",
            return_value=fake_repo,
        ):
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.get("/api/research/backtests")
            assert response.status_code == 200
            bt = response.json()["backtests"][0]
            assert bt["metrics"]["total_return"] == 0
            assert bt["metrics"]["sharpe"] == 0.0
            assert bt["metrics"]["max_drawdown"] == 0
            assert bt["metrics"]["win_rate"] == 0.0
            assert bt["metrics"]["trades"] == 0


class TestDirtySharpeRatio:
    """Tests for _str_to_decimal defensive handling of dirty sharpe_ratio data."""

    def test_str_to_decimal_valid_number(self):
        """Valid numeric string parses correctly."""
        from src.infrastructure.backtest_repository import BacktestReportRepository
        repo = BacktestReportRepository.__new__(BacktestReportRepository)
        result = repo._str_to_decimal("2.1")
        assert result is not None
        assert float(result) == 2.1

    def test_str_to_decimal_none_returns_none(self):
        """None input returns None."""
        from src.infrastructure.backtest_repository import BacktestReportRepository
        repo = BacktestReportRepository.__new__(BacktestReportRepository)
        assert repo._str_to_decimal(None) is None

    def test_str_to_decimal_json_array_returns_none(self):
        """JSON array string (dirty sharpe_ratio) returns None, no exception."""
        from src.infrastructure.backtest_repository import BacktestReportRepository
        repo = BacktestReportRepository.__new__(BacktestReportRepository)
        assert repo._str_to_decimal("[1.2, 3.4]") is None

    def test_str_to_decimal_json_object_returns_none(self):
        """JSON object string returns None, no exception."""
        from src.infrastructure.backtest_repository import BacktestReportRepository
        repo = BacktestReportRepository.__new__(BacktestReportRepository)
        assert repo._str_to_decimal('{"value": 1.5}') is None

    def test_str_to_decimal_garbage_returns_none(self):
        """Arbitrary garbage string returns None, no exception."""
        from src.infrastructure.backtest_repository import BacktestReportRepository
        repo = BacktestReportRepository.__new__(BacktestReportRepository)
        assert repo._str_to_decimal("not_a_number") is None

    def test_str_to_decimal_empty_string_returns_none(self):
        """Empty string returns None, no exception."""
        from src.infrastructure.backtest_repository import BacktestReportRepository
        repo = BacktestReportRepository.__new__(BacktestReportRepository)
        assert repo._str_to_decimal("") is None

    async def test_dirty_sharpe_ratio_in_list_reports_maps_to_none(self, readmodel):
        """When repo returns dirty sharpe_ratio string, readmodel maps it to None."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value={
            "reports": [
                {
                    "id": "bt_dirty",
                    "strategy_id": "test",
                    "symbol": "ETH/USDT:USDT",
                    "timeframe": "1h",
                    "sharpe_ratio": "None",  # _str_to_decimal returns None → str(None) = "None"
                }
            ]
        })
        result = await readmodel.build(backtest_repo=repo)
        bt = result.backtests[0]
        assert bt.metrics.sharpe is None

    async def test_dirty_sharpe_ratio_does_not_crash_list(self, readmodel):
        """Multiple reports with dirty sharpe_ratio don't crash the entire list."""
        repo = AsyncMock()
        repo.list_reports = AsyncMock(return_value={
            "reports": [
                {
                    "id": "bt_ok",
                    "strategy_id": "a",
                    "symbol": "BTC/USDT:USDT",
                    "timeframe": "1h",
                    "sharpe_ratio": "1.5",
                },
                {
                    "id": "bt_dirty",
                    "strategy_id": "b",
                    "symbol": "ETH/USDT:USDT",
                    "timeframe": "4h",
                    "sharpe_ratio": "None",
                },
                {
                    "id": "bt_null",
                    "strategy_id": "c",
                    "symbol": "SOL/USDT:USDT",
                    "timeframe": "15m",
                    "sharpe_ratio": None,
                },
            ]
        })
        result = await readmodel.build(backtest_repo=repo)
        assert len(result.backtests) == 3
        assert result.backtests[0].metrics.sharpe == 1.5
        assert result.backtests[1].metrics.sharpe is None
        assert result.backtests[2].metrics.sharpe is None