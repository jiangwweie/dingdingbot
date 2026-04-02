"""
StrategyOptimizer 单元测试

测试策略优化器核心逻辑

覆盖的测试用例:
- UT-201: PerformanceCalculator 夏普比率计算
- UT-202: PerformanceCalculator 索提诺比率计算
- UT-203: PerformanceCalculator 最大回撤计算
- UT-204: PerformanceCalculator 收益回撤比计算
- UT-205: _sample_params 整数参数采样
- UT-206: _sample_params 浮点参数采样
- UT-207: _sample_params 分类参数采样
- UT-208: _calculate_objective 夏普比率
- UT-209: _calculate_objective 索提诺比率
- UT-210: _calculate_objective 收益回撤比
- UT-211: _calculate_objective 总收益
- UT-212: _calculate_objective 胜率
- UT-213: 边界情况处理
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.application.strategy_optimizer import (
    StrategyOptimizer,
    PerformanceCalculator,
)
from src.domain.models import (
    ParameterType,
    ParameterDefinition,
    ParameterSpace,
    OptimizationObjective,
    OptunaDirection,
    OptimizationRequest,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_exchange_gateway():
    """模拟交易所网关"""
    gateway = Mock()
    gateway.initialize = AsyncMock()
    gateway.close = AsyncMock()
    return gateway


@pytest.fixture
def mock_backtester():
    """模拟回测器"""
    backtester = Mock()
    backtester.run_backtest = AsyncMock()
    return backtester


@pytest.fixture
def optimizer(mock_exchange_gateway, mock_backtester):
    """创建 StrategyOptimizer 实例"""
    return StrategyOptimizer(
        exchange_gateway=mock_exchange_gateway,
        backtester=mock_backtester,
        db_path=":memory:",
    )


@pytest.fixture
def sample_parameter_space():
    """创建示例参数空间"""
    return ParameterSpace(
        strategy_id="pinbar_ema",
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
                low=0.4,
                high=0.8,
                step=0.05,
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
        strategy_id="pinbar_ema",
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        parameter_space=ParameterSpace(
            strategy_id="pinbar_ema",
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
    
    def test_sample_params_int_type(self, optimizer, sample_parameter_space):
        """测试整数参数采样"""
        mock_trial = Mock()
        mock_trial.suggest_int.return_value = 55
        
        params = optimizer._sample_params(mock_trial, sample_parameter_space)
        
        assert "ema_period" in params
        mock_trial.suggest_int.assert_called_once()
    
    def test_sample_params_float_type(self, optimizer, sample_parameter_space):
        """测试浮点参数采样"""
        mock_trial = Mock()
        mock_trial.suggest_float.return_value = 0.65
        
        params = optimizer._sample_params(mock_trial, sample_parameter_space)
        
        assert "min_wick_ratio" in params
        mock_trial.suggest_float.assert_called()
    
    def test_sample_params_categorical_type(self, optimizer, sample_parameter_space):
        """测试分类参数采样"""
        mock_trial = Mock()
        mock_trial.suggest_int.return_value = 50
        mock_trial.suggest_float.return_value = 0.6
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
        mock_report.sharpe_ratio = Decimal('3.2')  # 简化：使用 sharpe 代替
        
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
        mock_report.total_pnl = Decimal('3500')
        
        result = optimizer._calculate_objective(
            OptimizationObjective.MAX_PROFIT,
            mock_report
        )
        
        assert result == 3500.0


# ============================================================
# Tests: Build Backtest Request
# ============================================================

class TestBuildBacktestRequest:
    """构建回测请求测试"""
    
    def test_build_backtest_request(self, optimizer, sample_optimization_request):
        """测试构建回测请求"""
        params = {"ema_period": 50}
        
        request = optimizer._build_backtest_request(
            sample_optimization_request,
            params
        )
        
        assert request.symbol == "BTC/USDT:USDT"
        assert request.timeframe == "15m"
        assert request.mode == "v3_pms"
        assert request.initial_balance == Decimal('10000')
    
    def test_build_backtest_request_custom_params(self, optimizer):
        """测试自定义配置的回测请求"""
        request = OptimizationRequest(
            strategy_id="test",
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            parameter_space=ParameterSpace(
                strategy_id="test",
                parameters=[]
            ),
            initial_balance=Decimal('50000'),
            slippage_rate=Decimal('0.002'),
            fee_rate=Decimal('0.0005'),
        )
        
        backtest_request = optimizer._build_backtest_request(
            request,
            {"ema_period": 50}
        )
        
        assert backtest_request.symbol == "ETH/USDT:USDT"
        assert backtest_request.timeframe == "1h"
        assert backtest_request.initial_balance == Decimal('50000')
        assert backtest_request.slippage_rate == Decimal('0.002')


# ============================================================
# Tests: Edge Cases
# ============================================================

class TestEdgeCases:
    """边界情况测试"""
    
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
            strategy_id="test",
            parameters=[]
        )
        
        mock_trial = Mock()
        params = optimizer._sample_params(mock_trial, empty_space)
        
        assert params == {}
        mock_trial.assert_not_called()


# ============================================================
# Tests: Job Management (Integration)
# ============================================================

@pytest.mark.asyncio
class TestJobManagement:
    """任务管理集成测试"""
    
    async def test_job_initialization(self, optimizer, sample_optimization_request):
        """测试任务初始化"""
        # 注意：这里只测试任务创建，不测试完整的异步优化流程
        job_id = "test_job_001"
        
        from src.domain.models import OptimizationJob, OptimizationJobStatus
        from datetime import datetime, timezone
        
        job = OptimizationJob(
            job_id=job_id,
            strategy_id=sample_optimization_request.strategy_id,
            symbol=sample_optimization_request.symbol,
            timeframe=sample_optimization_request.timeframe,
            objective=sample_optimization_request.objective,
            direction=sample_optimization_request.direction,
            n_trials=sample_optimization_request.n_trials,
            status=OptimizationJobStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        
        assert job.job_id == job_id
        assert job.status == OptimizationJobStatus.PENDING
        assert job.current_trial == 0
    
    async def test_job_status_transitions(self, optimizer):
        """测试任务状态转换"""
        from src.domain.models import OptimizationJob, OptimizationJobStatus
        from datetime import datetime, timezone
        
        job = OptimizationJob(
            job_id="test_job_002",
            strategy_id="test",
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            objective=OptimizationObjective.SHARPE,
            direction=OptunaDirection.MAXIMIZE,
            n_trials=10,
            status=OptimizationJobStatus.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        
        # PENDING -> RUNNING
        job.status = OptimizationJobStatus.RUNNING
        assert job.status == OptimizationJobStatus.RUNNING
        
        # RUNNING -> COMPLETED
        job.status = OptimizationJobStatus.COMPLETED
        assert job.status == OptimizationJobStatus.COMPLETED
