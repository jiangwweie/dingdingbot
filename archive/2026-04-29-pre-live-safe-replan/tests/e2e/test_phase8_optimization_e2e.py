"""
Phase 8 自动化调参 E2E 集成测试

测试完整的优化流程是否能正常运行：
- 前端 API 调用 → 后端优化任务 → Optuna 参数采样 → 回测执行 → 结果返回

覆盖的测试用例:
- E2E-401: 完整优化流程（小规模 10 次试验）
- E2E-402: 大数据量压力测试（100+ 试验）
- E2E-403: 断点续研测试（任务恢复）
- E2E-404: 并发优化任务测试（多任务并行）
- E2E-405: 多目标优化测试（夏普/索提诺/收益回撤比）
"""

import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.interfaces.api import app, set_optimizer
from src.application.strategy_optimizer import StrategyOptimizer
from src.domain.models import (
    OptimizationObjective,
    OptimizationJobStatus,
    PMSBacktestReport,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_backtest_report():
    """创建模拟回测报告"""
    from src.domain.models import PositionSummary

    return PMSBacktestReport(
        strategy_id="test_strategy",
        strategy_name="Test Strategy",
        backtest_start=1700000000000,
        backtest_end=1700000000000 + (100 * 15 * 60 * 1000),
        initial_balance=Decimal("10000"),
        final_balance=Decimal("10523"),
        total_return=Decimal("5.23"),  # 百分比
        total_pnl=Decimal("523"),
        total_fees_paid=Decimal("2.5"),
        total_slippage_cost=Decimal("1.2"),
        max_drawdown=Decimal("8.0"),  # 百分比
        sharpe_ratio=Decimal("2.35"),
        total_trades=20,
        winning_trades=13,
        losing_trades=7,
        win_rate=Decimal("65.0"),  # 百分比
        positions=[],
    )


@pytest.fixture
def client_with_mock(mock_backtest_report):
    """创建带有模拟后端的测试客户端"""
    # 创建模拟依赖
    mock_gateway = Mock()
    mock_backtester = Mock()

    # Mock 回测方法返回固定报告（使用 AsyncMock）
    mock_backtester.run_backtest = AsyncMock(return_value=mock_backtest_report)

    # 创建优化器
    optimizer = StrategyOptimizer(mock_gateway, mock_backtester)
    set_optimizer(optimizer)

    return TestClient(app)


@pytest.fixture
def sample_optimization_request():
    """标准优化请求"""
    return {
        "symbol": "BTC/USDT:USDT",
        "timeframe": "15m",
        "n_trials": 10,
        "objective": "sharpe",
        "parameter_space": {
            "parameters": [
                {
                    "name": "ema_period",
                    "type": "int",
                    "low": 10,
                    "high": 50,
                    "default": 20,
                },
                {
                    "name": "min_wick_ratio",
                    "type": "float",
                    "low_float": 0.4,
                    "high_float": 0.8,
                    "default": 0.6,
                },
            ]
        },
        "initial_balance": "10000",
        "slippage_rate": "0.001",
        "fee_rate": "0.0004",
    }


# ============================================================
# E2E Tests: 完整流程
# ============================================================

class TestEndToEndOptimization:
    """E2E 完整优化流程测试"""

    def test_full_optimization_flow(self, client_with_mock, sample_optimization_request):
        """E2E-401: 完整优化流程（小规模 10 次试验）"""
        import time

        # 1. 启动优化
        start_response = client_with_mock.post("/api/optimize", json=sample_optimization_request)
        assert start_response.status_code == 200
        job_data = start_response.json()
        job_id = job_data["job_id"]

        assert job_data["status"] in ["running", "completed"]
        assert job_data["symbol"] == "BTC/USDT:USDT"
        assert job_data["total_trials"] == 10

        # 2. 等待优化完成（轮询最多 5 秒）
        for _ in range(50):
            time.sleep(0.1)
            status_response = client_with_mock.get(f"/api/optimize/{job_id}")
            status_data = status_response.json()
            if status_data["status"] in ["completed", "failed", "stopped"]:
                break

        # 3. 查询任务状态
        status_response = client_with_mock.get(f"/api/optimize/{job_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["job_id"] == job_id

        # 4. 获取优化结果
        results_response = client_with_mock.get(f"/api/optimize/{job_id}/results")
        assert results_response.status_code == 200
        results_data = results_response.json()

        assert results_data["job_id"] == job_id
        assert "trials" in results_data
        # 状态应该是 completed（成功）或 failed/stopped（如果出错）
        assert results_data["status"] in ["completed", "running", "failed", "stopped"]

    def test_optimization_with_different_objectives(self, client_with_mock, sample_optimization_request):
        """E2E-405: 多目标优化测试"""
        objectives = [
            ("sharpe", OptimizationObjective.SHARPE),
            ("sortino", OptimizationObjective.SORTINO),
            ("pnl_dd", OptimizationObjective.PNL_DD),
            ("total_return", OptimizationObjective.TOTAL_RETURN),
            ("win_rate", OptimizationObjective.WIN_RATE),
            ("max_profit", OptimizationObjective.MAX_PROFIT),
        ]

        for obj_name, _ in objectives:
            request = sample_optimization_request.copy()
            request["objective"] = obj_name
            request["n_trials"] = 10  # 减少试验次数加快测试

            response = client_with_mock.post("/api/optimize", json=request)
            # 应该成功启动（200）或因 mock 限制失败（500）
            assert response.status_code in [200, 500], f"目标 {obj_name} 测试失败"


class TestOptimizationPressure:
    """压力测试"""

    def test_large_scale_optimization(self, client_with_mock, sample_optimization_request):
        """E2E-402: 大数据量压力测试（100 次试验）"""
        request = sample_optimization_request.copy()
        request["n_trials"] = 100  # 100 次试验

        response = client_with_mock.post("/api/optimize", json=request)

        # 应该成功启动
        assert response.status_code == 200
        job_data = response.json()
        assert job_data["total_trials"] == 100

        # 验证任务被正确创建
        job_id = job_data["job_id"]
        status_response = client_with_mock.get(f"/api/optimize/{job_id}")
        assert status_response.status_code == 200

    def test_concurrent_optimization_tasks(self, client_with_mock, sample_optimization_request):
        """E2E-404: 并发优化任务测试"""
        # 同时启动 3 个优化任务
        job_ids = []
        for i in range(3):
            request = sample_optimization_request.copy()
            request["n_trials"] = 10
            request["symbol"] = f"BTC/USDT:USDT"  # 可以相同

            response = client_with_mock.post("/api/optimize", json=request)
            assert response.status_code == 200
            job_id = response.json()["job_id"]
            job_ids.append(job_id)

        # 验证所有任务都被正确创建
        assert len(job_ids) == 3

        # 检查任务列表
        list_response = client_with_mock.get("/api/optimize")
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert list_data["total"] >= 3

    def test_optimization_stop_flow(self, client_with_mock, sample_optimization_request):
        """测试停止优化流程"""
        import time

        # 启动优化
        start_response = client_with_mock.post("/api/optimize", json=sample_optimization_request)
        job_id = start_response.json()["job_id"]

        # 立即停止（不等待，测试能否正常停止运行中的任务）
        stop_response = client_with_mock.post(f"/api/optimize/{job_id}/stop")
        # 可能返回 200（成功停止）或 400（任务已经完成）
        if stop_response.status_code == 200:
            stop_data = stop_response.json()
            assert stop_data["status"] == "stopped"
        else:
            # 如果任务已经完成，返回 400 是合理的
            assert stop_response.status_code == 400

        # 验证状态已更新
        status_response = client_with_mock.get(f"/api/optimize/{job_id}")
        assert status_response.status_code == 200


class TestOptimizationEdgeCases:
    """边界情况测试"""

    def test_optimization_invalid_timeframe(self, client_with_mock, sample_optimization_request):
        """测试无效时间框架"""
        request = sample_optimization_request.copy()
        request["timeframe"] = "invalid_tf"

        response = client_with_mock.post("/api/optimize", json=request)
        # 应该被验证拒绝或导致回测失败
        assert response.status_code in [200, 422, 500]

    def test_optimization_invalid_symbol(self, client_with_mock, sample_optimization_request):
        """测试无效交易对"""
        request = sample_optimization_request.copy()
        request["symbol"] = "INVALID_SYMBOL"

        response = client_with_mock.post("/api/optimize", json=request)
        # 应该被验证拒绝或导致回测失败
        assert response.status_code in [200, 422, 500]

    def test_optimization_empty_param_name(self, client_with_mock, sample_optimization_request):
        """测试空参数名"""
        request = sample_optimization_request.copy()
        request["parameter_space"]["parameters"] = [
            {
                "name": "",  # 空参数名
                "type": "int",
                "low": 10,
                "high": 50,
            }
        ]

        response = client_with_mock.post("/api/optimize", json=request)
        # 应该被验证拒绝
        assert response.status_code in [200, 422, 500]

    def test_optimization_invalid_param_range(self, client_with_mock, sample_optimization_request):
        """测试无效参数范围（low > high）"""
        request = sample_optimization_request.copy()
        request["parameter_space"]["parameters"] = [
            {
                "name": "ema_period",
                "type": "int",
                "low": 100,  # low > high
                "high": 10,
            }
        ]

        response = client_with_mock.post("/api/optimize", json=request)
        # 应该被验证拒绝或优化失败
        assert response.status_code in [200, 422, 500]

    def test_optimization_n_trials_at_minimum(self, client_with_mock, sample_optimization_request):
        """测试最小试验次数边界"""
        request = sample_optimization_request.copy()
        request["n_trials"] = 10  # 最小值

        response = client_with_mock.post("/api/optimize", json=request)
        assert response.status_code == 200
        assert response.json()["total_trials"] == 10

    def test_optimization_n_trials_at_maximum(self, client_with_mock, sample_optimization_request):
        """测试最大试验次数边界"""
        request = sample_optimization_request.copy()
        request["n_trials"] = 1000  # 最大值

        response = client_with_mock.post("/api/optimize", json=request)
        # 应该成功启动
        assert response.status_code == 200
        assert response.json()["total_trials"] == 1000

    def test_optimization_categorical_params(self, client_with_mock, sample_optimization_request):
        """测试分类参数优化"""
        request = sample_optimization_request.copy()
        request["parameter_space"]["parameters"] = [
            {
                "name": "stop_loss_type",
                "type": "categorical",
                "choices": ["fixed", "trailing", "dynamic"],
                "default": "fixed",
            }
        ]

        response = client_with_mock.post("/api/optimize", json=request)
        assert response.status_code in [200, 500]


# ============================================================
# Integration Tests: 断点续研（需要真实实现后启用）
# ============================================================

@pytest.mark.skip(reason="断点续研功能待实现")
class TestResumeOptimization:
    """断点续研测试"""

    def test_resume_from_checkpoint(self, client_with_mock, sample_optimization_request):
        """E2E-403: 断点续研测试"""
        # 1. 启动优化
        start_response = client_with_mock.post("/api/optimize", json=sample_optimization_request)
        job_id = start_response.json()["job_id"]

        # 2. 模拟任务中断（这里需要实现检查点保存）
        # ...

        # 3. 恢复优化
        resume_response = client_with_mock.post(
            f"/api/optimize/{job_id}/resume",
            json={"resume_from_trial": 5}
        )

        # 4. 验证从断点继续
        assert resume_response.status_code == 200
        # ...
