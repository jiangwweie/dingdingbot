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
            low_float=0.4,
            high_float=0.8,
            default=0.6,
        )

        assert param.name == "min_wick_ratio"
        assert param.type == ParameterType.FLOAT
        assert param.low_float == 0.4
        assert param.high_float == 0.8

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

    def test_int_parameter_requires_int_values(self):
        """测试整数参数需要整数值"""
        with pytest.raises(ValidationError) as exc_info:
            ParameterDefinition(
                name="test",
                type=ParameterType.INT,
                low=0.5,  # 应该是整数
                high=10,
            )
        assert "int_from_float" in str(exc_info.value)

    def test_float_parameter_requires_float_values(self):
        """测试浮点参数可以接受小数"""
        param = ParameterDefinition(
            name="test",
            type=ParameterType.FLOAT,
            low_float=0.1,
            high_float=1.0,
        )
        assert param.low_float == 0.1
        assert param.high_float == 1.0


# ============================================================
# Tests: ParameterSpace 模型
# ============================================================

class TestParameterSpace:
    """参数空间模型测试"""

    def test_parameter_space_creation(self):
        """测试创建参数空间"""
        space = ParameterSpace(
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
            ]
        )

        assert len(space.parameters) == 2
        assert space.parameters[0].name == "ema_period"
        assert space.parameters[1].name == "min_wick_ratio"

    def test_add_parameter(self):
        """测试添加参数"""
        space = ParameterSpace()
        space.add_parameter(ParameterDefinition(
            name="ema_period",
            type=ParameterType.INT,
            low=10,
            high=200,
        ))

        assert len(space.parameters) == 1
        assert space.parameters[0].name == "ema_period"

    def test_empty_parameter_space(self):
        """测试空参数空间"""
        space = ParameterSpace()

        assert len(space.parameters) == 0

    def test_get_parameter_by_name(self):
        """测试按名称获取参数"""
        space = ParameterSpace(
            parameters=[
                ParameterDefinition(name="ema_period", type=ParameterType.INT, low=10, high=200),
                ParameterDefinition(name="min_wick_ratio", type=ParameterType.FLOAT, low_float=0.1, high_float=1.0),
            ]
        )

        # 查找参数
        ema_param = next((p for p in space.parameters if p.name == "ema_period"), None)
        assert ema_param is not None
        assert ema_param.type == ParameterType.INT


# ============================================================
# Tests: OptimizationRequest 模型
# ============================================================

class TestOptimizationRequest:
    """优化请求模型测试"""

    def test_minimal_request(self):
        """测试最小化请求"""
        request = OptimizationRequest(
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
        )

        assert request.symbol == "BTC/USDT:USDT"
        assert request.timeframe == "15m"
        assert request.objective == OptimizationObjective.SHARPE
        assert request.n_trials == 100
        assert request.initial_balance == Decimal("10000")

    def test_full_request(self):
        """测试完整配置请求"""
        request = OptimizationRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            start_time=1672531200000,
            end_time=1709251200000,
            limit=200,
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
            objective=OptimizationObjective.SORTINO,
            n_trials=50,
            timeout=1800,
            initial_balance=Decimal("50000"),
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
        )

        assert request.objective == OptimizationObjective.SORTINO
        assert request.n_trials == 50
        assert request.timeout == 1800
        assert request.initial_balance == Decimal("50000")
        assert request.limit == 200

    def test_invalid_n_trials_too_low(self):
        """测试 n_trials 过小验证失败"""
        with pytest.raises(ValidationError) as exc_info:
            OptimizationRequest(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                parameter_space=ParameterSpace(parameters=[]),
                n_trials=5,  # 小于最小值 10
            )

        assert "n_trials" in str(exc_info.value)

    def test_invalid_n_trials_too_high(self):
        """测试 n_trials 过大验证失败"""
        with pytest.raises(ValidationError) as exc_info:
            OptimizationRequest(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                parameter_space=ParameterSpace(parameters=[]),
                n_trials=2000,  # 大于最大值 1000
            )

        assert "n_trials" in str(exc_info.value)

    def test_resume_from_last(self):
        """测试从上次进度继续"""
        request = OptimizationRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            parameter_space=ParameterSpace(parameters=[]),
            continue_from_last=True,
        )

        assert request.continue_from_last is True


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
            total_return=Decimal("0.15"),
            sharpe_ratio=2.35,
            sortino_ratio=3.2,
            max_drawdown=Decimal("0.08"),
            win_rate=0.65,
            total_trades=50,
            winning_trades=32,
        )

        assert result.trial_number == 1
        assert result.params["ema_period"] == 50
        assert result.objective_value == 2.35
        assert result.total_return == Decimal("0.15")
        assert result.win_rate == 0.65

    def test_trial_result_default_values(self):
        """测试默认值"""
        result = OptimizationTrialResult(
            trial_number=1,
            params={"ema_period": 50},
            objective_value=1.5,
            total_trades=0,
            winning_trades=0,
        )

        assert result.total_return is None
        assert result.sharpe_ratio is None
        assert result.sortino_ratio is None
        assert result.max_drawdown is None
        assert result.win_rate is None
        assert result.total_trades == 0
        assert result.winning_trades == 0


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

        data = param.model_dump()
        assert data["name"] == "ema_period"
        assert data["type"] == "int"
        assert data["low"] == 10
        assert data["high"] == 200

    def test_parameter_space_json(self):
        """测试参数空间 JSON 序列化"""
        space = ParameterSpace(
            parameters=[
                ParameterDefinition(name="ema_period", type=ParameterType.INT, low=10, high=200),
                ParameterDefinition(name="min_wick_ratio", type=ParameterType.FLOAT, low_float=0.4, high_float=0.8),
            ]
        )

        data = space.model_dump()
        assert len(data["parameters"]) == 2
        assert data["parameters"][0]["name"] == "ema_period"
        assert data["parameters"][1]["name"] == "min_wick_ratio"

    def test_optimization_request_json(self):
        """测试优化请求 JSON 序列化"""
        request = OptimizationRequest(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            parameter_space=ParameterSpace(
                parameters=[
                    ParameterDefinition(name="ema_period", type=ParameterType.INT, low=10, high=200),
                ]
            ),
            objective=OptimizationObjective.SHARPE,
            n_trials=100,
        )

        data = request.model_dump()
        assert data["symbol"] == "BTC/USDT:USDT"
        assert data["timeframe"] == "15m"
        assert data["objective"] == "sharpe"
        assert data["n_trials"] == 100
