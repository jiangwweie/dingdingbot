"""
Optimization Models 单元测试

测试数据模型的验证和序列化功能

覆盖的测试用例:
- UT-101: ParameterDefinition 创建和验证
- UT-102: ParameterSpace 创建和验证
- UT-103: OptimizationRequest 创建和验证
- UT-104: OptimizationJobStatus 枚举
- UT-105: OptimizationObjective 枚举
- UT-106: 参数范围验证
- UT-107: 无效参数配置处理
- UT-108: 模型序列化
"""

import pytest
from decimal import Decimal
from pydantic import ValidationError
import sys
import os

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
    OptimizationTrialResult,
)


# ============================================================
# Tests: ParameterType 枚举
# ============================================================

class TestParameterType:
    """参数类型枚举测试"""
    
    def test_int_type(self):
        """测试整数类型"""
        assert ParameterType.INT == "int"
    
    def test_float_type(self):
        """测试浮点类型"""
        assert ParameterType.FLOAT == "float"
    
    def test_categorical_type(self):
        """测试分类类型"""
        assert ParameterType.CATEGORICAL == "categorical"


# ============================================================
# Tests: OptimizationObjective 枚举
# ============================================================

class TestOptimizationObjective:
    """优化目标枚举测试"""
    
    def test_sharpe_objective(self):
        """测试夏普比率目标"""
        assert OptimizationObjective.SHARPE == "sharpe"
    
    def test_sortino_objective(self):
        """测试索提诺比率目标"""
        assert OptimizationObjective.SORTINO == "sortino"
    
    def test_pnl_dd_objective(self):
        """测试收益回撤比目标"""
        assert OptimizationObjective.PNL_DD == "pnl_dd"
    
    def test_total_return_objective(self):
        """测试总收益目标"""
        assert OptimizationObjective.TOTAL_RETURN == "total_return"
    
    def test_win_rate_objective(self):
        """测试胜率目标"""
        assert OptimizationObjective.WIN_RATE == "win_rate"
    
    def test_max_profit_objective(self):
        """测试最大利润目标"""
        assert OptimizationObjective.MAX_PROFIT == "max_profit"


# ============================================================
# Tests: OptunaDirection 枚举
# ============================================================

class TestOptunaDirection:
    """优化方向枚举测试"""
    
    def test_maximize(self):
        """测试最大化"""
        assert OptunaDirection.MAXIMIZE == "maximize"
    
    def test_minimize(self):
        """测试最小化"""
        assert OptunaDirection.MINIMIZE == "minimize"


# ============================================================
# Tests: OptimizationJobStatus 枚举
# ============================================================

class TestOptimizationJobStatus:
    """任务状态枚举测试"""
    
    def test_pending(self):
        """测试待处理状态"""
        assert OptimizationJobStatus.PENDING == "pending"
    
    def test_running(self):
        """测试运行中状态"""
        assert OptimizationJobStatus.RUNNING == "running"
    
    def test_completed(self):
        """测试完成状态"""
        assert OptimizationJobStatus.COMPLETED == "completed"
    
    def test_stopped(self):
        """测试停止状态"""
        assert OptimizationJobStatus.STOPPED == "stopped"
    
    def test_failed(self):
        """测试失败状态"""
        assert OptimizationJobStatus.FAILED == "failed"


# ============================================================
# Tests: ParameterDefinition 模型
# ============================================================

class TestParameterDefinition:
    """参数定义模型测试"""
    
    def test_int_parameter_creation(self):
        """测试创建整数参数"""
        param = ParameterDefinition(
            name="ema_period",
            type=ParameterType.INT,
            low=10,
            high=200,
            step=1,
            default=50,
        )
        
        assert param.name == "ema_period"
        assert param.type == ParameterType.INT
        assert param.low == 10
        assert param.high == 200
        assert param.step == 1
        assert param.default == 50
    
    def test_float_parameter_creation(self):
        """测试创建浮点参数"""
        param = ParameterDefinition(
            name="min_wick_ratio",
            type=ParameterType.FLOAT,
            low=0.4,
            high=0.8,
            step=0.05,
            default=0.6,
        )
        
        assert param.name == "min_wick_ratio"
        assert param.type == ParameterType.FLOAT
        assert param.low == 0.4
        assert param.high == 0.8
        assert param.step == 0.05
    
    def test_categorical_parameter_creation(self):
        """测试创建分类参数"""
        param = ParameterDefinition(
            name="stop_loss_type",
            type=ParameterType.CATEGORICAL,
            choices=["fixed", "trailing", "dynamic"],
            default="fixed",
        )
        
        assert param.name == "stop_loss_type"
        assert param.type == ParameterType.CATEGORICAL
        assert param.choices == ["fixed", "trailing", "dynamic"]
        assert param.default == "fixed"
    
    def test_parameter_without_default(self):
        """测试无默认值的参数"""
        param = ParameterDefinition(
            name="ema_period",
            type=ParameterType.INT,
            low=10,
            high=200,
        )
        
        assert param.default is None
    
    def test_parameter_without_step(self):
        """测试无步长的参数"""
        param = ParameterDefinition(
            name="min_wick_ratio",
            type=ParameterType.FLOAT,
            low=0.4,
            high=0.8,
        )
        
        assert param.step is None


# ============================================================
# Tests: ParameterSpace 模型
# ============================================================

class TestParameterSpace:
    """参数空间模型测试"""
    
    def test_parameter_space_creation(self):
        """测试创建参数空间"""
        space = ParameterSpace(
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
                    default=0.6,
                ),
            ]
        )
        
        assert space.strategy_id == "pinbar_ema"
        assert len(space.parameters) == 2
        assert space.parameters[0].name == "ema_period"
        assert space.parameters[1].name == "min_wick_ratio"
    
    def test_get_parameter_names(self):
        """测试获取参数名称列表"""
        space = ParameterSpace(
            strategy_id="test",
            parameters=[
                ParameterDefinition(
                    name="param1",
                    type=ParameterType.INT,
                    low=1,
                    high=10,
                ),
                ParameterDefinition(
                    name="param2",
                    type=ParameterType.FLOAT,
                    low=0.1,
                    high=1.0,
                ),
            ]
        )
        
        names = space.get_parameter_names()
        
        assert names == ["param1", "param2"]
    
    def test_empty_parameter_space(self):
        """测试空参数空间"""
        space = ParameterSpace(
            strategy_id="test",
            parameters=[]
        )
        
        assert len(space.parameters) == 0
        assert space.get_parameter_names() == []


# ============================================================
# Tests: OptimizationRequest 模型
# ============================================================

class TestOptimizationRequest:
    """优化请求模型测试"""
    
    def test_minimal_request(self):
        """测试最小化请求"""
        request = OptimizationRequest(
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
        )
        
        assert request.strategy_id == "pinbar_ema"
        assert request.symbol == "BTC/USDT:USDT"
        assert request.timeframe == "15m"
        assert request.objective == OptimizationObjective.SHARPE
        assert request.direction == OptunaDirection.MAXIMIZE
        assert request.n_trials == 100
    
    def test_full_request(self):
        """测试完整配置请求"""
        request = OptimizationRequest(
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
            objective=OptimizationObjective.SORTINO,
            direction=OptunaDirection.MAXIMIZE,
            n_trials=50,
            timeout_seconds=1800,
            backtest_start=1672531200000,
            backtest_end=1709251200000,
            initial_balance=Decimal('50000'),
            slippage_rate=Decimal('0.001'),
            fee_rate=Decimal('0.0004'),
        )
        
        assert request.objective == OptimizationObjective.SORTINO
        assert request.n_trials == 50
        assert request.timeout_seconds == 1800
        assert request.initial_balance == Decimal('50000')
    
    def test_invalid_n_trials_too_low(self):
        """测试 n_trials 过小验证失败"""
        with pytest.raises(ValidationError) as exc_info:
            OptimizationRequest(
                strategy_id="test",
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                parameter_space=ParameterSpace(
                    strategy_id="test",
                    parameters=[],
                ),
                n_trials=5,  # 小于最小值 10
            )
        
        assert "n_trials" in str(exc_info.value)
    
    def test_invalid_n_trials_too_high(self):
        """测试 n_trials 过大验证失败"""
        with pytest.raises(ValidationError) as exc_info:
            OptimizationRequest(
                strategy_id="test",
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                parameter_space=ParameterSpace(
                    strategy_id="test",
                    parameters=[],
                ),
                n_trials=2000,  # 大于最大值 1000
            )
        
        assert "n_trials" in str(exc_info.value)
    
    def test_resume_from_trial(self):
        """测试断点续研配置"""
        request = OptimizationRequest(
            strategy_id="test",
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            parameter_space=ParameterSpace(
                strategy_id="test",
                parameters=[],
            ),
            resume_from_trial=50,  # 从第 50 次试验继续
        )
        
        assert request.resume_from_trial == 50


# ============================================================
# Tests: OptimizationTrialResult 模型
# ============================================================

class TestOptimizationTrialResult:
    """试验结果模型测试"""
    
    def test_trial_result_creation(self):
        """测试创建试验结果"""
        result = OptimizationTrialResult(
            trial_number=1,
            params={"ema_period": 50, "min_wick_ratio": 0.6},
            objective_value=2.35,
            total_return=0.15,
            sharpe_ratio=2.35,
            sortino_ratio=3.2,
            max_drawdown=0.08,
            win_rate=0.65,
            total_trades=50,
        )
        
        assert result.trial_number == 1
        assert result.params["ema_period"] == 50
        assert result.objective_value == 2.35
        assert result.total_return == 0.15
    
    def test_trial_result_default_values(self):
        """测试默认值"""
        result = OptimizationTrialResult(
            trial_number=1,
            params={"ema_period": 50},
            objective_value=1.5,
        )
        
        assert result.total_return == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.sortino_ratio == 0.0
        assert result.max_drawdown == 0.0
        assert result.win_rate == 0.0
        assert result.total_trades == 0
        assert result.datetime is None


# ============================================================
# Tests: 模型序列化
# ============================================================

class TestModelSerialization:
    """模型序列化测试"""
    
    def test_parameter_definition_json(self):
        """测试参数定义 JSON 序列化"""
        param = ParameterDefinition(
            name="ema_period",
            type=ParameterType.INT,
            low=10,
            high=200,
            default=50,
        )
        
        json_data = param.model_dump(mode='json')
        
        assert json_data["name"] == "ema_period"
        assert json_data["type"] == "int"
        assert json_data["low"] == 10
    
    def test_parameter_space_json(self):
        """测试参数空间 JSON 序列化"""
        space = ParameterSpace(
            strategy_id="test",
            parameters=[
                ParameterDefinition(
                    name="ema_period",
                    type=ParameterType.INT,
                    low=10,
                    high=200,
                ),
            ]
        )
        
        json_data = space.model_dump(mode='json')
        
        assert json_data["strategy_id"] == "test"
        assert len(json_data["parameters"]) == 1
    
    def test_optimization_request_json(self):
        """测试优化请求 JSON 序列化"""
        request = OptimizationRequest(
            strategy_id="test",
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            parameter_space=ParameterSpace(
                strategy_id="test",
                parameters=[
                    ParameterDefinition(
                        name="ema_period",
                        type=ParameterType.INT,
                        low=10,
                        high=200,
                    ),
                ]
            ),
        )
        
        json_data = request.model_dump(mode='json')
        
        assert json_data["strategy_id"] == "test"
        assert json_data["symbol"] == "BTC/USDT:USDT"
        assert json_data["objective"] == "sharpe"
