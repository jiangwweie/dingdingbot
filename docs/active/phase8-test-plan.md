# Phase 8: 自动化调参 - 测试计划

**文档版本**: 1.0  
**创建日期**: 2026-04-02  
**状态**: 待执行  

---

## 一、测试概述

### 1.1 测试范围

| 测试层级 | 测试内容 | 测试文件 |
|----------|----------|----------|
| 单元测试 | Optuna 目标函数、参数空间验证 | `tests/unit/test_objective_calculator.py` |
| 单元测试 | 策略优化器核心逻辑 | `tests/unit/test_strategy_optimizer.py` |
| 单元测试 | Optuna 持久化 Repository | `tests/unit/test_optuna_repository.py` |
| 集成测试 | API 端点集成 | `tests/integration/test_optimize_api.py` |
| E2E 测试 | 完整优化流程 | `tests/e2e/test_e2e_optimization.py` |

### 1.2 测试环境

- **Python**: 3.11+
- **测试框架**: pytest + pytest-asyncio
- **Mock 库**: pytest-mock / unittest.mock
- **Optuna**: 4.x
- **数据库**: SQLite (临时测试库)

### 1.3 测试前置条件

1. Optuna 已安装：`pip install optuna`
2. 回测系统测试通过
3. HistoricalDataRepository 有测试数据

---

## 二、T1: Optuna 目标函数单元测试 (P0)

### 2.1 测试文件：`tests/unit/test_objective_calculator.py`

### 2.2 测试用例清单

| 用例 ID | 测试名称 | 优先级 | 说明 |
|---------|----------|--------|------|
| UT-001 | test_calculate_sharpe_normal | P0 | 正常夏普比率计算 |
| UT-002 | test_calculate_sharpe_with_existing_ratio | P0 | 使用已有 sharpe_ratio 字段 |
| UT-003 | test_calculate_sharpe_insufficient_trades | P0 | 交易数<2 时惩罚 |
| UT-004 | test_calculate_sharpe_zero_volatility | P0 | 零波动率处理 |
| UT-005 | test_calculate_pnl_max_dd_normal | P0 | 正常收益/回撤比计算 |
| UT-006 | test_calculate_pnl_max_dd_zero_drawdown | P0 | 零回撤处理 |
| UT-007 | test_calculate_pnl_max_dd_negative_pnl | P0 | 负收益处理 |
| UT-008 | test_calculate_sortino_normal | P0 | 正常索提诺比率计算 |
| UT-009 | test_calculate_sortino_with_existing_ratio | P0 | 使用已有 sortino_ratio 字段 |
| UT-010 | test_calculate_sortino_no_loss | P0 | 无亏损交易处理 |
| UT-011 | test_calculate_total_return | P0 | 总收益率计算 |
| UT-012 | test_calculate_win_rate | P0 | 胜率计算 |
| UT-013 | test_calculate_sharpe_empty_data | P1 | 空数据边界情况 |
| UT-014 | test_calculate_sharpe_negative_returns | P1 | 负收益场景 |

### 2.3 测试代码示例

```python
"""Optuna 目标函数单元测试"""

import pytest
from decimal import Decimal
from unittest.mock import Mock
from src.application.strategy_optimizer import ObjectiveCalculator


class TestObjectiveCalculator:
    """目标值计算器单元测试"""
    
    @pytest.fixture
    def calculator(self):
        return ObjectiveCalculator()
    
    @pytest.fixture
    def create_mock_report(self):
        """创建模拟回测报告的工厂函数"""
        def _factory(**kwargs):
            report = Mock()
            report.total_return = kwargs.get('total_return', Decimal('0.15'))
            report.max_drawdown = kwargs.get('max_drawdown', Decimal('0.05'))
            report.total_pnl = kwargs.get('total_pnl', Decimal('1500'))
            report.total_trades = kwargs.get('total_trades', 50)
            report.win_rate = kwargs.get('win_rate', Decimal('0.6'))
            report.avg_win = kwargs.get('avg_win', Decimal('100'))
            report.avg_loss = kwargs.get('avg_loss', Decimal('-50'))
            report.sharpe_ratio = kwargs.get('sharpe_ratio', None)
            report.sortino_ratio = kwargs.get('sortino_ratio', None)
            return report
        return _factory
    
    # ========== 夏普比率测试 ==========
    
    def test_calculate_sharpe_normal(self, calculator, create_mock_report):
        """测试正常夏普比率计算"""
        report = create_mock_report(
            avg_win=Decimal('100'),
            avg_loss=Decimal('-50'),
        )
        
        result = calculator.calculate_sharpe(report)
        
        assert isinstance(result, float)
        assert result > 0  # 正收益应该得到正的夏普比率
    
    def test_calculate_sharpe_with_existing_ratio(self, calculator, create_mock_report):
        """测试使用已有 sharpe_ratio 字段"""
        expected_sharpe = 2.5
        report = create_mock_report(sharpe_ratio=Decimal(str(expected_sharpe)))
        
        result = calculator.calculate_sharpe(report)
        
        assert result == pytest.approx(expected_sharpe, rel=1e-6)
    
    def test_calculate_sharpe_insufficient_trades(self, calculator, create_mock_report):
        """测试交易数不足时的惩罚"""
        report = create_mock_report(total_trades=1)
        
        result = calculator.calculate_sharpe(report)
        
        assert result == -999.0  # 惩罚值
    
    def test_calculate_sharpe_zero_volatility(self, calculator, create_mock_report):
        """测试零波动率场景"""
        report = create_mock_report(
            avg_win=Decimal('50'),
            avg_loss=Decimal('50'),  # 无波动
        )
        
        result = calculator.calculate_sharpe(report)
        
        assert result == 0.0
    
    def test_calculate_sharpe_empty_data(self, calculator, create_mock_report):
        """测试空数据"""
        report = create_mock_report(
            total_trades=0,
            avg_win=Decimal('0'),
            avg_loss=Decimal('0'),
        )
        
        result = calculator.calculate_sharpe(report)
        
        assert result == -999.0
    
    def test_calculate_sharpe_negative_returns(self, calculator, create_mock_report):
        """测试负收益场景"""
        report = create_mock_report(
            avg_win=Decimal('30'),
            avg_loss=Decimal('-100'),  # 亏损大于盈利
        )
        
        result = calculator.calculate_sharpe(report)
        
        assert result < 0  # 负收益应得到负的夏普比率
    
    # ========== 收益/回撤比测试 ==========
    
    def test_calculate_pnl_max_dd_normal(self, calculator, create_mock_report):
        """测试正常收益/回撤比计算"""
        report = create_mock_report(
            total_pnl=Decimal('1500'),
            max_drawdown=Decimal('500'),
        )
        
        result = calculator.calculate_pnl_max_dd(report)
        
        assert result == pytest.approx(3.0, rel=1e-6)
    
    def test_calculate_pnl_max_dd_zero_drawdown(self, calculator, create_mock_report):
        """测试零回撤场景"""
        report = create_mock_report(
            total_pnl=Decimal('1000'),
            max_drawdown=Decimal('0'),
        )
        
        result = calculator.calculate_pnl_max_dd(report)
        
        assert result == float('inf')  # 无穷大
    
    def test_calculate_pnl_max_dd_negative_pnl(self, calculator, create_mock_report):
        """测试负收益场景"""
        report = create_mock_report(
            total_pnl=Decimal('-500'),
            max_drawdown=Decimal('500'),
        )
        
        result = calculator.calculate_pnl_max_dd(report)
        
        assert result < 0
    
    # ========== 索提诺比率测试 ==========
    
    def test_calculate_sortino_normal(self, calculator, create_mock_report):
        """测试正常索提诺比率计算"""
        report = create_mock_report(
            avg_win=Decimal('100'),
            avg_loss=Decimal('-50'),
            total_trades=50,
        )
        
        result = calculator.calculate_sortino(report)
        
        assert isinstance(result, float)
        assert result > 0
    
    def test_calculate_sortino_with_existing_ratio(self, calculator, create_mock_report):
        """测试使用已有 sortino_ratio 字段"""
        expected_sortino = 3.2
        report = create_mock_report(
            sortino_ratio=Decimal(str(expected_sortino)),
        )
        
        result = calculator.calculate_sortino(report)
        
        assert result == pytest.approx(expected_sortino, rel=1e-6)
    
    def test_calculate_sortino_no_loss(self, calculator, create_mock_report):
        """测试无亏损场景"""
        report = create_mock_report(
            avg_loss=Decimal('0'),  # 无亏损
        )
        
        result = calculator.calculate_sortino(report)
        
        assert result == -999.0  # 无法计算下行偏差
    
    # ========== 其他目标测试 ==========
    
    def test_calculate_total_return(self, calculator, create_mock_report):
        """测试总收益率计算"""
        expected_return = 0.15
        report = create_mock_report(total_return=Decimal(str(expected_return)))
        
        result = calculator.calculate_total_return(report)
        
        assert result == pytest.approx(expected_return, rel=1e-6)
    
    def test_calculate_win_rate(self, calculator, create_mock_report):
        """测试胜率计算"""
        expected_win_rate = 0.65
        report = create_mock_report(win_rate=Decimal(str(expected_win_rate)))
        
        result = calculator.calculate_win_rate(report)
        
        assert result == pytest.approx(expected_win_rate, rel=1e-6)
```

---

## 三、T2: 参数空间验证测试 (P0)

### 3.1 测试文件：`tests/unit/test_parameter_space.py`

### 3.2 测试用例清单

| 用例 ID | 测试名称 | 优先级 | 说明 |
|---------|----------|--------|------|
| UT-101 | test_parameter_space_validation | P0 | 参数空间验证 |
| UT-102 | test_int_parameter_sampling | P0 | 整数参数采样 |
| UT-103 | test_float_parameter_sampling | P0 | 浮点参数采样 |
| UT-104 | test_categorical_parameter_sampling | P0 | 分类参数采样 |
| UT-105 | test_parameter_range_validation | P0 | 参数范围验证 |
| UT-106 | test_invalid_parameter_config | P0 | 无效参数配置 |
| UT-107 | test_empty_parameter_space | P1 | 空参数空间 |
| UT-108 | test_duplicate_parameter_names | P1 | 重复参数名检测 |

### 3.3 测试代码示例

```python
"""参数空间验证单元测试"""

import pytest
from pydantic import ValidationError
from src.domain.optimizer import (
    ParameterType,
    ParameterDefinition,
    ParameterSpace,
)


class TestParameterDefinition:
    """参数定义测试"""
    
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
        
        assert param.type == ParameterType.FLOAT
        assert param.low == 0.4
        assert param.high == 0.8
    
    def test_categorical_parameter_creation(self):
        """测试创建分类参数"""
        param = ParameterDefinition(
            name="stop_loss_type",
            type=ParameterType.CATEGORICAL,
            choices=["fixed", "trailing", "dynamic"],
            default="fixed",
        )
        
        assert param.type == ParameterType.CATEGORICAL
        assert len(param.choices) == 3
        assert "fixed" in param.choices
    
    def test_int_parameter_invalid_range(self):
        """测试整数参数范围验证"""
        with pytest.raises(ValueError):
            ParameterDefinition(
                name="invalid",
                type=ParameterType.INT,
                low=100,  # low > high
                high=10,
            )
    
    def test_float_parameter_missing_range(self):
        """测试浮点参数缺少范围"""
        with pytest.raises(ValidationError):
            ParameterDefinition(
                name="invalid",
                type=ParameterType.FLOAT,
                # missing low/high
            )
    
    def test_categorical_parameter_missing_choices(self):
        """测试分类参数缺少可选项"""
        with pytest.raises(ValidationError):
            ParameterDefinition(
                name="invalid",
                type=ParameterType.CATEGORICAL,
                # missing choices
            )


class TestParameterSpace:
    """参数空间测试"""
    
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
                    low=0.4,
                    high=0.8,
                    default=0.6,
                ),
            ]
        )
        
        assert len(space.parameters) == 2
        assert space.parameters[0].name == "ema_period"
        assert space.parameters[1].name == "min_wick_ratio"
    
    def test_empty_parameter_space(self):
        """测试空参数空间"""
        space = ParameterSpace(parameters=[])
        
        assert len(space.parameters) == 0
    
    def test_duplicate_parameter_names(self):
        """测试重复参数名检测"""
        # 注意：当前实现可能不检测重复，这里记录期望行为
        pass


class TestParameterSampling:
    """参数采样测试（需要 Mock Optuna Trial）"""
    
    @pytest.fixture
    def mock_trial(self):
        """模拟 Optuna Trial"""
        from unittest.mock import Mock
        trial = Mock()
        trial.suggest_int.return_value = 55
        trial.suggest_float.return_value = 0.65
        trial.suggest_categorical.return_value = "trailing"
        return trial
    
    def test_sample_int_parameter(self, mock_trial):
        """测试整数参数采样"""
        param = ParameterDefinition(
            name="ema_period",
            type=ParameterType.INT,
            low=10,
            high=200,
        )
        
        # 这里需要 StrategyOptimizer._sample_params 方法
        # 待实现后补充测试
        pass
```

---

## 四、T3: API 集成测试 (P0)

### 4.1 测试文件：`tests/integration/test_optimize_api.py`

### 4.2 测试用例清单

| 用例 ID | 测试名称 | 优先级 | 说明 |
|---------|----------|--------|------|
| IT-001 | test_start_optimization | P0 | 启动优化任务 |
| IT-002 | test_query_progress | P0 | 查询优化进度 |
| IT-003 | test_get_optimization_result | P0 | 获取优化结果 |
| IT-004 | test_stop_optimization | P0 | 停止优化任务 |
| IT-005 | test_get_studies_list | P0 | 获取研究列表 |
| IT-006 | test_delete_study | P0 | 删除研究 |
| IT-007 | test_invalid_parameter_space | P0 | 无效参数空间处理 |
| IT-008 | test_duplicate_study_name | P1 | 同名研究冲突 |
| IT-009 | test_study_not_found | P1 | 研究不存在处理 |
| IT-010 | test_optimization_error_handling | P1 | 优化错误处理 |

### 4.3 测试代码示例

```python
"""Optimization API 集成测试"""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.infrastructure.optuna_repository import OptunaRepository


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def test_repository():
    """创建测试 Repository"""
    repo = OptunaRepository(db_path=":memory:")
    yield repo
    # 清理


@pytest.mark.integration
class TestOptimizeAPI:
    """优化 API 集成测试"""
    
    def test_start_optimization(self, client, test_repository):
        """测试启动优化任务"""
        payload = {
            "strategy_id": "pinbar_ema",
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "start_time": 1672531200000,
            "end_time": 1709251200000,
            "objective": "sharpe",
            "n_trials": 10,  # 测试用少量试验
            "timeout_seconds": 60,
            "parameter_space": {
                "parameters": [
                    {
                        "name": "ema_period",
                        "type": "int",
                        "low": 10,
                        "high": 50,
                        "default": 20,
                    }
                ]
            }
        }
        
        response = client.post("/api/optimize", json=payload)
        
        assert response.status_code == 201
        data = response.json()
        assert "study_id" in data
        assert "study_name" in data
    
    def test_query_progress(self, client, test_repository):
        """测试查询优化进度"""
        # 先启动优化
        # ...
        
        # 查询进度
        response = client.get(f"/api/optimize/{study_id}/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "progress" in data
    
    def test_get_optimization_result(self, client, test_repository):
        """测试获取优化结果"""
        # 等待优化完成
        # ...
        
        response = client.get(f"/api/optimize/{study_id}/result")
        
        assert response.status_code == 200
        data = response.json()
        assert "best_trial" in data
        assert "best_params" in data
    
    def test_stop_optimization(self, client, test_repository):
        """测试停止优化任务"""
        # 启动优化
        # ...
        
        response = client.post(f"/api/optimize/{study_id}/stop")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
    
    def test_get_studies_list(self, client, test_repository):
        """测试获取研究列表"""
        response = client.get("/api/optimize/studies")
        
        assert response.status_code == 200
        data = response.json()
        assert "studies" in data
        assert "total" in data
    
    def test_delete_study(self, client, test_repository):
        """测试删除研究"""
        response = client.delete(f"/api/optimize/{study_id}")
        
        assert response.status_code == 200
        
        # 验证已删除
        response = client.get(f"/api/optimize/{study_id}/result")
        assert response.status_code == 404
    
    def test_invalid_parameter_space(self, client):
        """测试无效参数空间处理"""
        payload = {
            "strategy_id": "test",
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "start_time": 1672531200000,
            "end_time": 1709251200000,
            "parameter_space": {
                "parameters": [
                    {
                        "name": "invalid",
                        "type": "int",
                        "low": 100,
                        "high": 10,  # 无效范围
                    }
                ]
            }
        }
        
        response = client.post("/api/optimize", json=payload)
        
        assert response.status_code == 400
    
    def test_study_not_found(self, client):
        """测试研究不存在处理"""
        response = client.get("/api/optimize/99999/status")
        
        assert response.status_code == 404
```

---

## 五、T4: E2E 测试 (P1)

### 5.1 测试文件：`tests/e2e/test_e2e_optimization.py`

### 5.2 测试用例清单

| 用例 ID | 测试名称 | 优先级 | 说明 |
|---------|----------|--------|------|
| E2E-001 | test_full_optimization_workflow | P0 | 完整优化流程 |
| E2E-002 | test_large_dataset_stress | P1 | 大数据量压力测试 |
| E2E-003 | test_checkpoint_resume | P1 | 断点续研测试 |
| E2E-004 | test_concurrent_optimization | P1 | 并发优化任务测试 |

### 5.3 测试代码示例

```python
"""Optimization E2E 测试"""

import pytest
import asyncio
from decimal import Decimal


@pytest.mark.e2e
class TestE2EOptimization:
    """E2E 优化流程测试"""
    
    @pytest.mark.asyncio
    async def test_full_optimization_workflow(self):
        """测试完整优化流程"""
        # 1. 准备测试数据
        # 2. 启动优化任务
        # 3. 轮询进度直到完成
        # 4. 验证最佳参数
        
        assert best_params is not None
        assert best_value > 0
    
    @pytest.mark.asyncio
    async def test_large_dataset_stress(self):
        """大数据量压力测试"""
        # 使用 5 年历史数据
        # 运行 100 次试验
        # 验证性能和内存
        
        assert elapsed_time < 600  # 10 分钟内完成
        assert memory_usage < 500  # 内存<500MB
    
    @pytest.mark.asyncio
    async def test_checkpoint_resume(self):
        """测试断点续研"""
        # 1. 启动优化，运行 10 次试验后停止
        # 2. 使用同名研究重新启动
        # 3. 验证试验历史延续
        
        assert total_trials == 20  # 10 + 10
        assert study_history_preserved
    
    @pytest.mark.asyncio
    async def test_concurrent_optimization(self):
        """测试并发优化任务"""
        # 同时启动 3 个优化任务
        # 验证互不干扰
        
        tasks = [
            optimize_task(symbol="BTC/USDT:USDT"),
            optimize_task(symbol="ETH/USDT:USDT"),
            optimize_task(symbol="SOL/USDT:USDT"),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 所有任务都应该成功
        assert all(not isinstance(r, Exception) for r in results)
```

---

## 六、测试执行

### 6.1 运行所有测试

```bash
# 运行单元测试
pytest tests/unit/test_objective_calculator.py -v
pytest tests/unit/test_strategy_optimizer.py -v
pytest tests/unit/test_optuna_repository.py -v

# 运行集成测试
pytest tests/integration/test_optimize_api.py -v

# 运行 E2E 测试
pytest tests/e2e/test_e2e_optimization.py -v

# 运行所有 Phase 8 测试
pytest tests/unit/test_objective_calculator.py tests/unit/test_strategy_optimizer.py tests/unit/test_optuna_repository.py tests/integration/test_optimize_api.py tests/e2e/test_e2e_optimization.py -v
```

### 6.2 生成覆盖率报告

```bash
# 生成覆盖率报告
pytest tests/unit/ tests/integration/ --cov=src/application/strategy_optimizer --cov=src/domain/optimizer --cov=src/infrastructure/optuna_repository --cov-report=html

# 查看覆盖率
coverage report --fail-under=80
```

---

## 七、测试数据准备

### 7.1 模拟回测报告

```python
def create_mock_backtest_report(**kwargs):
    """创建模拟回测报告"""
    from unittest.mock import Mock
    report = Mock()
    report.total_return = kwargs.get('total_return', Decimal('0.15'))
    report.max_drawdown = kwargs.get('max_drawdown', Decimal('0.05'))
    report.total_pnl = kwargs.get('total_pnl', Decimal('1500'))
    report.total_trades = kwargs.get('total_trades', 50)
    report.win_rate = kwargs.get('win_rate', Decimal('0.6'))
    report.avg_win = kwargs.get('avg_win', Decimal('100'))
    report.avg_loss = kwargs.get('avg_loss', Decimal('-50'))
    report.sharpe_ratio = kwargs.get('sharpe_ratio', None)
    report.sortino_ratio = kwargs.get('sortino_ratio', None)
    return report
```

### 7.2 测试数据库

```python
@pytest.fixture
def temp_db():
    """创建临时测试数据库"""
    import tempfile
    import os
    
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    yield path
    
    # 清理
    if os.path.exists(path):
        os.remove(path)
```

---

## 八、通过标准

| 测试层级 | 通过率要求 | 覆盖率要求 |
|----------|-----------|-----------|
| 单元测试 | 100% | ≥90% |
| 集成测试 | 100% | ≥80% |
| E2E 测试 | 100% | N/A |

---

*文档结束*
