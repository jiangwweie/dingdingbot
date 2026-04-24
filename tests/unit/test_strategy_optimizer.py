"""
Strategy Optimizer 单元测试

测试策略优化器的核心功能

覆盖的测试用例:
- UT-201: PerformanceCalculator 性能指标计算
- UT-202: ParameterSampling 参数采样
- UT-203: ObjectiveCalculation 目标函数计算
- UT-204: BuildBacktestRequest 回测请求构建
- UT-205: EdgeCases 边界情况处理
- UT-206: JobManagement 任务管理
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch
from concurrent.futures import TimeoutError as FutureTimeoutError
import json
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.domain.models import (
    ParameterType,
    ParameterDefinition,
    ParameterSpace,
    OptimizationObjective,
    OptunaDirection,
    OptimizationRequest,
    OptimizationJobStatus,
    OptimizationJob,
    PMSBacktestReport,
    RiskConfig,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_parameter_space():
    """创建示例参数空间"""
    return ParameterSpace(
        parameters=[
            ParameterDefinition(
                name="ema_period",
                type=ParameterType.INT,
                low=10,
                high=200,
                default=50,
            ),
            ParameterDefinition(
                name="min_wick_ratio",
                type=ParameterType.FLOAT,
                low_float=0.4,
                high_float=0.8,
                default=0.6,
            ),
            ParameterDefinition(
                name="stop_loss_type",
                type=ParameterType.CATEGORICAL,
                choices=["fixed", "trailing", "dynamic"],
                default="fixed",
            ),
        ]
    )


@pytest.fixture
def sample_optimization_request():
    """创建示例优化请求"""
    return OptimizationRequest(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        parameter_space=ParameterSpace(
            parameters=[
                ParameterDefinition(
                    name="ema_period",
                    type=ParameterType.INT,
                    low=10,
                    high=200,
                ),
            ]
        ),
        objective=OptimizationObjective.SHARPE,
        n_trials=10,
    )


# ============================================================
# Tests: PerformanceCalculator
# ============================================================

class TestPerformanceCalculator:
    """PerformanceCalculator 测试"""

    @pytest.fixture
    def calculator(self):
        from src.application.strategy_optimizer import PerformanceCalculator
        return PerformanceCalculator()

    def test_calculate_sharpe_positive_returns(self, calculator):
        """测试正收益的夏普比率计算"""
        returns = [0.02, 0.03, 0.025, 0.015]
        result = calculator.calculate_sharpe_ratio(returns)
        assert isinstance(result, float)

    def test_calculate_sharpe_negative_returns(self, calculator):
        """测试负收益的夏普比率计算"""
        returns = [-0.02, -0.03, -0.025]
        result = calculator.calculate_sharpe_ratio(returns)
        assert isinstance(result, float)

    def test_calculate_sortino_with_downside(self, calculator):
        """测试有下行波动的索提诺比率"""
        returns = [0.02, -0.01, 0.03, -0.005]
        result = calculator.calculate_sortino_ratio(returns)
        assert isinstance(result, float)

    def test_calculate_max_drawdown_simple(self, calculator):
        """测试简单最大回撤计算"""
        equity = [100, 110, 105, 120, 115]
        result = calculator.calculate_max_drawdown(equity)
        assert 0 <= result <= 1

    def test_calculate_pnl_dd_ratio(self, calculator):
        """测试收益回撤比计算"""
        result = calculator.calculate_pnl_dd_ratio(1000.0, 0.1)
        assert result == pytest.approx(10000.0, rel=1e-6)


# ============================================================
# Tests: Parameter Sampling
# ============================================================

class TestParameterSampling:
    """参数采样测试"""

    @pytest.fixture
    def optimizer(self, sample_optimization_request):
        from src.application.strategy_optimizer import StrategyOptimizer
        mock_gateway = Mock()
        mock_backtester = Mock()
        optimizer = StrategyOptimizer(mock_gateway, mock_backtester)
        optimizer._jobs = {}
        return optimizer

    def test_sample_params_int_type(self, optimizer, sample_parameter_space):
        """测试整数参数采样"""
        mock_trial = Mock()
        mock_trial.suggest_int.return_value = 100

        params = optimizer._sample_params(mock_trial, sample_parameter_space)

        assert "ema_period" in params
        assert params["ema_period"] == 100
        mock_trial.suggest_int.assert_called_once()

    def test_sample_params_float_type(self, optimizer, sample_parameter_space):
        """测试浮点参数采样"""
        mock_trial = Mock()
        mock_trial.suggest_float.return_value = 0.7

        params = optimizer._sample_params(mock_trial, sample_parameter_space)

        assert "min_wick_ratio" in params
        assert params["min_wick_ratio"] == 0.7
        mock_trial.suggest_float.assert_called_once()

    def test_sample_params_categorical_type(self, optimizer, sample_parameter_space):
        """测试分类参数采样"""
        mock_trial = Mock()
        mock_trial.suggest_categorical.return_value = "trailing"

        params = optimizer._sample_params(mock_trial, sample_parameter_space)

        assert "stop_loss_type" in params
        assert params["stop_loss_type"] == "trailing"
        mock_trial.suggest_categorical.assert_called_once()

    def test_sample_params_all_types(self, optimizer, sample_parameter_space):
        """测试所有参数类型的采样"""
        mock_trial = Mock()
        mock_trial.suggest_int.return_value = 100
        mock_trial.suggest_float.return_value = 0.7
        mock_trial.suggest_categorical.return_value = "dynamic"

        params = optimizer._sample_params(mock_trial, sample_parameter_space)

        assert len(params) == 3
        assert params["ema_period"] == 100
        assert params["min_wick_ratio"] == 0.7
        assert params["stop_loss_type"] == "dynamic"


# ============================================================
# Tests: Objective Calculation
# ============================================================

class TestObjectiveCalculation:
    """目标函数计算测试"""

    @pytest.fixture
    def optimizer(self):
        from src.application.strategy_optimizer import StrategyOptimizer
        mock_gateway = Mock()
        mock_backtester = Mock()
        optimizer = StrategyOptimizer(mock_gateway, mock_backtester)
        optimizer._jobs = {}
        return optimizer

    def test_calculate_objective_sharpe(self, optimizer):
        """测试夏普比率目标计算"""
        mock_report = Mock()
        mock_report.sharpe_ratio = Decimal('2.35')
        mock_report.total_return = Decimal('0.15')
        mock_report.max_drawdown = Decimal('0.08')
        mock_report.total_pnl = Decimal('1500')
        mock_report.win_rate = Decimal('0.6')

        result = optimizer._calculate_objective(
            OptimizationObjective.SHARPE,
            mock_report
        )

        assert result == 2.35

    def test_calculate_objective_sharpe_none(self, optimizer):
        """测试 sharpe_ratio 为 None 时的处理"""
        mock_report = Mock()
        mock_report.sharpe_ratio = None

        result = optimizer._calculate_objective(
            OptimizationObjective.SHARPE,
            mock_report
        )

        assert result == 0.0

    def test_calculate_objective_sortino(self, optimizer):
        """测试索提诺比率目标计算"""
        mock_report = Mock()
        mock_report.sortino_ratio = Decimal('3.2')

        result = optimizer._calculate_objective(
            OptimizationObjective.SORTINO,
            mock_report
        )

        assert result == 3.2

    def test_calculate_objective_pnl_dd(self, optimizer):
        """测试收益回撤比目标计算"""
        mock_report = Mock()
        mock_report.total_pnl = Decimal('2000')
        mock_report.max_drawdown = Decimal('0.1')

        result = optimizer._calculate_objective(
            OptimizationObjective.PNL_DD,
            mock_report
        )

        assert result > 0

    def test_calculate_objective_total_return(self, optimizer):
        """测试总收益目标计算"""
        mock_report = Mock()
        mock_report.total_return = Decimal('0.25')

        result = optimizer._calculate_objective(
            OptimizationObjective.TOTAL_RETURN,
            mock_report
        )

        assert result == 0.25

    def test_build_optimization_history_records_sortino_ratio(self, optimizer):
        """测试优化历史记录不再把 sortino 写死为 0.0"""
        mock_report = Mock(
            total_return=Decimal("0.25"),
            sharpe_ratio=Decimal("1.8"),
            sortino_ratio=Decimal("2.4"),
            max_drawdown=Decimal("0.12"),
            win_rate=Decimal("47.5"),
            total_trades=120,
            total_pnl=Decimal("2500"),
            total_fees_paid=Decimal("45"),
        )

        history = optimizer._build_optimization_history(
            job_id="job_1",
            trial_number=3,
            params={"ema_period": 43},
            objective_value=1.8,
            report=mock_report,
        )
        metrics = json.loads(history.metrics_json)

        assert metrics["sortino_ratio"] == 2.4

    def test_calculate_objective_win_rate(self, optimizer):
        """测试胜率目标计算"""
        mock_report = Mock()
        mock_report.win_rate = Decimal('0.65')

        result = optimizer._calculate_objective(
            OptimizationObjective.WIN_RATE,
            mock_report
        )

        assert result == 0.65

    def test_calculate_objective_max_profit(self, optimizer):
        """测试最大利润目标计算"""
        mock_report = Mock()
        mock_report.total_pnl = Decimal('500')

        result = optimizer._calculate_objective(
            OptimizationObjective.MAX_PROFIT,
            mock_report
        )

        assert result == 500.0


# ============================================================
# Tests: Build Trial Backtest Inputs
# ============================================================

class TestBuildTrialBacktestInputs:
    """Optuna trial 回测输入构建测试"""

    @pytest.fixture
    def optimizer(self):
        from src.application.strategy_optimizer import StrategyOptimizer
        mock_gateway = Mock()
        mock_backtester = Mock()
        optimizer = StrategyOptimizer(mock_gateway, mock_backtester)
        optimizer._jobs = {}
        return optimizer

    @pytest.mark.asyncio
    async def test_build_trial_backtest_inputs(self, optimizer, sample_optimization_request):
        """测试通过 profile resolver 构建回测请求"""
        params = {"ema_period": 50, "min_wick_ratio": 0.6}
        runtime_overrides = optimizer._build_runtime_overrides(params)

        request, returned_overrides = await optimizer._build_trial_backtest_inputs(
            sample_optimization_request,
            params,
            fixed_params=None,
            runtime_overrides=runtime_overrides,
        )

        assert returned_overrides == runtime_overrides
        assert request.symbol == "BTC/USDT:USDT"
        assert request.timeframe == "15m"
        assert request.mode == "v3_pms"
        assert request.initial_balance == Decimal('10000')
        assert request.strategies is not None
        assert request.order_strategy is not None

    @pytest.mark.asyncio
    async def test_build_trial_backtest_inputs_custom_engine_params(self, optimizer):
        """测试自定义配置的回测请求"""
        request = OptimizationRequest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            parameter_space=ParameterSpace(
                parameters=[]
            ),
            initial_balance=Decimal('50000'),
            slippage_rate=Decimal('0.002'),
            fee_rate=Decimal('0.0005'),
        )
        runtime_overrides = optimizer._build_runtime_overrides({"ema_period": 50})

        backtest_request, _ = await optimizer._build_trial_backtest_inputs(
            request,
            {"ema_period": 50},
            fixed_params={"tp_slippage_rate": Decimal("0.0007")},
            runtime_overrides=runtime_overrides,
        )

        assert backtest_request.symbol == "ETH/USDT:USDT"
        assert backtest_request.timeframe == "1h"
        assert backtest_request.initial_balance == Decimal('50000')
        assert backtest_request.slippage_rate == Decimal('0.002')
        assert backtest_request.fee_rate == Decimal('0.0005')
        assert backtest_request.tp_slippage_rate == Decimal("0.0007")

    @pytest.mark.asyncio
    async def test_build_trial_inputs_injects_sampled_risk_overrides(self, optimizer, sample_optimization_request):
        """采样得到的风控参数应注入到 request.risk_overrides"""
        params = {
            "max_loss_percent": 0.02,
            "max_total_exposure": 2.5,
        }
        runtime_overrides = optimizer._build_runtime_overrides(params)

        backtest_request, _ = await optimizer._build_trial_backtest_inputs(
            sample_optimization_request,
            params,
            fixed_params=None,
            runtime_overrides=runtime_overrides,
        )

        assert isinstance(backtest_request.risk_overrides, RiskConfig)
        assert backtest_request.risk_overrides.max_loss_percent == Decimal("0.02")
        assert backtest_request.risk_overrides.max_total_exposure == Decimal("2.5")
        assert backtest_request.risk_overrides.max_leverage == 20

    @pytest.mark.asyncio
    async def test_build_trial_inputs_fixed_risk_overrides_override_sampled(self, optimizer, sample_optimization_request):
        """fixed_params 中的风控参数应覆盖采样值"""
        params = {
            "max_loss_percent": 0.02,
            "max_total_exposure": 2.5,
        }
        fixed_params = {
            "max_loss_percent": 0.015,
            "max_total_exposure": 2.0,
            "max_leverage": 10,
        }
        runtime_overrides = optimizer._build_runtime_overrides(params, fixed_params)

        backtest_request, _ = await optimizer._build_trial_backtest_inputs(
            sample_optimization_request,
            params,
            fixed_params=fixed_params,
            runtime_overrides=runtime_overrides,
        )

        assert isinstance(backtest_request.risk_overrides, RiskConfig)
        assert backtest_request.risk_overrides.max_loss_percent == Decimal("0.015")
        assert backtest_request.risk_overrides.max_total_exposure == Decimal("2.0")
        assert backtest_request.risk_overrides.max_leverage == 10

    @pytest.mark.asyncio
    async def test_build_candidate_report_is_candidate_only(self, optimizer, sample_optimization_request):
        """candidate report 只输出审查产物，不直接改 runtime profile。"""
        from src.domain.models import OptimizationJob, OptimizationTrialResult, OptimizationJobStatus

        job_id = "opt_candidate"
        best_trial = OptimizationTrialResult(
            trial_number=3,
            params={"ema_period": 55, "max_loss_percent": 0.02},
            objective_value=1.23,
            total_return=Decimal("0.12"),
            max_drawdown=Decimal("0.05"),
            total_trades=8,
        )
        optimizer._jobs[job_id] = OptimizationJob(
            job_id=job_id,
            request=sample_optimization_request.model_copy(update={"fixed_params": {"tp_slippage_rate": Decimal("0.0007")}}, deep=True),
            status=OptimizationJobStatus.COMPLETED,
            total_trials=10,
            best_trial=best_trial,
            best_value=1.23,
        )

        async def _fake_results(*args, **kwargs):
            return [best_trial]

        optimizer.get_trial_results = _fake_results  # type: ignore[method-assign]

        report = await optimizer.build_candidate_report(job_id)

        assert report["status"] == "candidate_only"
        assert report["promotion_policy"] == "manual_review_required"
        assert report["source_profile"]["name"] == "backtest_eth_baseline"
        assert report["best_trial"]["trial_number"] == 3
        assert report["resolved_request"]["tp_slippage_rate"] == Decimal("0.0007")

    @pytest.mark.asyncio
    async def test_write_candidate_report_writes_json_file(self, optimizer, sample_optimization_request, tmp_path):
        """candidate report 产物应可落盘给人工审查。"""
        from src.domain.models import OptimizationJob, OptimizationTrialResult, OptimizationJobStatus

        job_id = "opt_candidate_file"
        best_trial = OptimizationTrialResult(
            trial_number=1,
            params={"max_atr_ratio": 0.01},
            objective_value=0.88,
            total_return=Decimal("0.08"),
            max_drawdown=Decimal("0.03"),
            total_trades=5,
        )
        optimizer._jobs[job_id] = OptimizationJob(
            job_id=job_id,
            request=sample_optimization_request,
            status=OptimizationJobStatus.COMPLETED,
            total_trials=10,
            best_trial=best_trial,
            best_value=0.88,
        )

        async def _fake_results(*args, **kwargs):
            return [best_trial]

        optimizer.get_trial_results = _fake_results  # type: ignore[method-assign]

        file_path = await optimizer.write_candidate_report(job_id, output_dir=tmp_path)

        assert file_path.exists()
        content = file_path.read_text(encoding="utf-8")
        assert "candidate_only" in content
        assert "optuna_candidate_opt_candidate_file" in content


# ============================================================
# Tests: Edge Cases
# ============================================================

class TestEdgeCases:
    """边界情况测试"""

    @pytest.fixture
    def optimizer(self):
        from src.application.strategy_optimizer import StrategyOptimizer
        mock_gateway = Mock()
        mock_backtester = Mock()
        optimizer = StrategyOptimizer(mock_gateway, mock_backtester)
        optimizer._jobs = {}
        return optimizer

    def test_calculate_objective_unknown_type(self, optimizer):
        """测试未知目标类型的处理"""
        mock_report = Mock()

        # 创建一个无效的枚举值（通过字符串绕过类型检查）
        from enum import Enum

        class FakeObjective(str, Enum):
            FAKE = "fake"

        result = optimizer._calculate_objective(
            FakeObjective.FAKE,
            mock_report
        )

        # 应该返回默认值
        assert result == 0.0

    def test_sample_params_empty_space(self, optimizer):
        """测试空参数空间的采样"""
        empty_space = ParameterSpace(
            parameters=[]
        )

        mock_trial = Mock()
        params = optimizer._sample_params(mock_trial, empty_space)

        assert params == {}
        mock_trial.assert_not_called()

    def test_build_profile_seed_request_preserves_tp_slippage_rate(self, optimizer, sample_optimization_request):
        """测试 profile seed request 不丢失 TP slippage 配置"""
        sample_optimization_request.tp_slippage_rate = Decimal("0.0009")

        request = optimizer._build_profile_seed_request(sample_optimization_request)

        assert request.tp_slippage_rate == Decimal("0.0009")

    def test_objective_prunes_trial_when_main_loop_future_times_out(self, optimizer, sample_optimization_request):
        """测试主循环 future 超时时会 prune 当前 trial"""
        from src.application.strategy_optimizer import DEFAULT_TRIAL_TIMEOUT_SECONDS
        import optuna

        optimizer._jobs = {
            "job_timeout": Mock(current_trial=0)
        }
        optimizer._stop_flags = {"job_timeout": False}

        trial = Mock(number=0)
        future = Mock()
        future.result.side_effect = FutureTimeoutError()

        def _fake_schedule(coro, _loop):
            coro.close()
            return future

        with patch("src.application.strategy_optimizer.asyncio.run_coroutine_threadsafe", side_effect=_fake_schedule):
            objective = optimizer._create_objective_function(  # type: ignore[attr-defined]
                sample_optimization_request,
                "job_timeout",
                fixed_params=None,
                main_loop=Mock(),
            )
            with pytest.raises(optuna.TrialPruned) as exc_info:
                objective(trial)

        future.cancel.assert_called_once()
        assert str(DEFAULT_TRIAL_TIMEOUT_SECONDS) in str(exc_info.value)


# ============================================================
# Tests: Job Management (Integration)
# ============================================================

@pytest.mark.asyncio
class TestJobManagement:
    """任务管理集成测试"""

    @pytest.fixture
    def optimizer(self):
        from src.application.strategy_optimizer import StrategyOptimizer
        mock_gateway = Mock()
        mock_backtester = Mock()
        optimizer = StrategyOptimizer(mock_gateway, mock_backtester)
        optimizer._jobs = {}
        return optimizer

    async def test_job_initialization(self, optimizer, sample_optimization_request):
        """测试任务初始化"""
        from datetime import datetime, timezone

        job = OptimizationJob(
            job_id="test_job_001",
            request=sample_optimization_request,
            status=OptimizationJobStatus.RUNNING,
            total_trials=sample_optimization_request.n_trials,
            started_at=datetime.now(timezone.utc),
        )

        assert job.job_id == "test_job_001"
        assert job.status == OptimizationJobStatus.RUNNING
        assert job.current_trial == 0
        assert job.total_trials == sample_optimization_request.n_trials

    async def test_job_status_transitions(self, optimizer, sample_optimization_request):
        """测试任务状态转换"""
        from datetime import datetime, timezone

        job = OptimizationJob(
            job_id="test_job_002",
            request=sample_optimization_request,
            status=OptimizationJobStatus.RUNNING,
            total_trials=10,
            started_at=datetime.now(timezone.utc),
        )

        # RUNNING -> COMPLETED
        job.status = OptimizationJobStatus.COMPLETED
        assert job.status == OptimizationJobStatus.COMPLETED

        # COMPLETED -> STOPPED (不允许)
        # 实际业务中应该有状态转换验证逻辑
        # 这里简化测试，仅验证状态可以被设置
