# Phase 8: 自动化调参 (Optuna 集成) - API 契约与设计文档

**文档版本**: 1.0  
**创建日期**: 2026-04-02  
**状态**: 设计中  

---

## 一、功能概述

集成 Optuna 参数优化框架，实现自动化策略参数寻优，支持夏普比率、收益回撤比等多目标优化。

### 1.1 核心功能

| 功能 | 说明 | 优先级 |
|------|------|--------|
| Optuna 目标函数 | 支持夏普比率、PnL/MaxDD、索提诺比率等优化目标 | P0 |
| 参数空间定义 | EMA 周期、Pinbar 阈值、止损比例等参数范围配置 | P0 |
| 持久化研究历史 | SQLite 存储试验历史，支持断点续研 | P0 |
| 可视化分析 | 参数重要性、优化路径、平行坐标图 | P1 |

### 1.2 用户故事

```
作为交易员，我希望：
- 能够定义参数优化范围（如 EMA 周期 10-200）
- 能够选择优化目标（夏普比率/收益回撤比/索提诺比率）
- 能够查看优化进度和最佳参数
- 能够将最佳参数应用到策略
```

---

## 二、架构设计

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Phase 8 架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐      ┌──────────────────────────────┐ │
│  │   Frontend UI   │ ◄──► │       REST API (FastAPI)     │ │
│  │  (参数配置/进度) │      │  /api/optimize/* 端点        │ │
│  └─────────────────┘      └──────────────┬───────────────┘ │
│                                          │                   │
│                                          ▼                   │
│                                 ┌─────────────────┐         │
│                                 │ StrategyOptimizer│         │
│                                 │ (应用服务层)     │         │
│                                 └────────┬────────┘         │
│                                          │                   │
│                    ┌─────────────────────┼───────────────┐  │
│                    ▼                     ▼               ▼  │
│           ┌─────────────┐      ┌─────────────┐  ┌─────────┐│
│           │ OptunaStudy │      │  Backtester │  │ Optuna  ││
│           │ Repository  │      │  (回测引擎) │  │ Storage ││
│           │ (SQLite)    │      │             │  │ (SQLite)││
│           └─────────────┘      └─────────────┘  └─────────┘│
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心类设计

```python
# src/domain/optimizer.py

from pydantic import BaseModel, Field
from typing import Literal, Optional
from decimal import Decimal
from enum import Enum


class OptimizationObjective(str, Enum):
    """优化目标"""
    SHARPE = "sharpe"           # 夏普比率
    PNL_MAX_DD = "pnl_max_dd"   # 收益/最大回撤比
    SORTINO = "sortino"         # 索提诺比率
    TOTAL_RETURN = "total_return"  # 总收益
    WIN_RATE = "win_rate"       # 胜率


class ParameterType(str, Enum):
    """参数类型"""
    INT = "int"
    FLOAT = "float"
    CATEGORICAL = "categorical"


class ParameterDefinition(BaseModel):
    """参数定义"""
    name: str
    type: ParameterType
    
    # 范围参数
    low: Optional[float] = None      # 下限
    high: Optional[float] = None     # 上限
    step: Optional[float] = None     # 步长 (int/float)
    
    # 分类参数
    choices: Optional[list[str]] = None  # 可选项 (categorical)
    
    # 默认值
    default: Optional[float] = None


class ParameterSpace(BaseModel):
    """参数空间定义"""
    parameters: list[ParameterDefinition]


class OptimizeRequest(BaseModel):
    """优化请求"""
    strategy_id: str
    symbol: str
    timeframe: str
    start_time: int  # 毫秒时间戳
    end_time: int    # 毫秒时间戳
    
    # 优化配置
    objective: OptimizationObjective = OptimizationObjective.SHARPE
    n_trials: int = 100
    timeout_seconds: Optional[int] = 3600
    
    # 参数空间
    parameter_space: ParameterSpace
    
    # 可选：研究名称（用于断点续研）
    study_name: Optional[str] = None


class OptimizeTrialResult(BaseModel):
    """单次试验结果"""
    trial_number: int
    params: dict[str, float | str]
    value: float
    datetime_start: Optional[int] = None  # 毫秒时间戳
    datetime_complete: Optional[int] = None
    state: Literal["COMPLETE", "PRUNED", "FAIL"] = "COMPLETE"


class OptimizeResult(BaseModel):
    """优化结果"""
    study_name: str
    study_id: int
    objective: OptimizationObjective
    direction: Literal["minimize", "maximize"]
    
    # 最佳结果
    best_trial: Optional[OptimizeTrialResult] = None
    best_value: Optional[float] = None
    best_params: Optional[dict[str, float | str]] = None
    
    # 统计信息
    n_trials: int
    n_complete: int
    n_pruned: int
    n_fail: int
    
    # 所有试验结果
    trials: list[OptimizeTrialResult] = Field(default_factory=list)
    
    # 执行时间
    optimization_duration_seconds: float
```

---

## 三、API 端点契约

### 3.1 优化任务管理

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/api/optimize` | POST | 启动优化任务 | Required |
| `/api/optimize/{study_id}/status` | GET | 查询优化进度 | Required |
| `/api/optimize/{study_id}/result` | GET | 获取优化结果 | Required |
| `/api/optimize/{study_id}/stop` | POST | 停止优化任务 | Required |
| `/api/optimize/studies` | GET | 获取研究列表 | Required |
| `/api/optimize/{study_id}` | DELETE | 删除研究 | Required |

### 3.2 详细契约

#### POST /api/optimize - 启动优化任务

**请求体**: `OptimizeRequest`

**响应**: `201 Created`
```json
{
    "study_id": 1,
    "study_name": "BTC/USDT:USDT:15m:20260402120000",
    "message": "Optimization started",
    "estimated_duration_seconds": 3600
}
```

**错误响应**:
- `400 Bad Request` - 参数空间无效
- `409 Conflict` - 同名研究已存在
- `500 Internal Server Error` - Optuna 初始化失败

---

#### GET /api/optimize/{study_id}/status - 查询进度

**路径参数**:
- `study_id` (int) - 研究 ID

**响应**: `200 OK`
```json
{
    "study_id": 1,
    "study_name": "BTC/USDT:USDT:15m:20260402120000",
    "status": "running",
    "progress": {
        "n_trials": 45,
        "n_complete": 42,
        "n_pruned": 2,
        "n_fail": 1,
        "total_trials": 100,
        "progress_percent": 45.0,
        "elapsed_seconds": 1620,
        "estimated_remaining_seconds": 1980
    },
    "current_best": {
        "value": 2.35,
        "trial_number": 28,
        "params": {
            "ema_period": 55,
            "min_wick_ratio": 0.65
        }
    }
}
```

**状态枚举**:
- `pending` - 等待启动
- `running` - 进行中
- `completed` - 已完成
- `stopped` - 已手动停止
- `failed` - 失败

---

#### GET /api/optimize/{study_id}/result - 获取结果

**路径参数**:
- `study_id` (int) - 研究 ID

**响应**: `200 OK`
```json
{
    "study_name": "BTC/USDT:USDT:15m:20260402120000",
    "objective": "sharpe",
    "direction": "maximize",
    "best_trial": {
        "trial_number": 28,
        "value": 2.35,
        "params": {
            "ema_period": 55,
            "min_wick_ratio": 0.65,
            "max_loss_percent": 1.0
        },
        "datetime_complete": 1712059200000
    },
    "best_value": 2.35,
    "best_params": {
        "ema_period": 55,
        "min_wick_ratio": 0.65,
        "max_loss_percent": 1.0
    },
    "n_trials": 100,
    "n_complete": 95,
    "n_pruned": 3,
    "n_fail": 2,
    "optimization_duration_seconds": 3420,
    "trials": [
        {
            "trial_number": 1,
            "params": {"ema_period": 20, "min_wick_ratio": 0.5},
            "value": 1.85,
            "state": "COMPLETE"
        }
    ]
}
```

**错误响应**:
- `404 Not Found` - 研究不存在

---

#### POST /api/optimize/{study_id}/stop - 停止优化

**路径参数**:
- `study_id` (int) - 研究 ID

**响应**: `200 OK`
```json
{
    "study_id": 1,
    "status": "stopped",
    "message": "Optimization stopped successfully",
    "best_trial_so_far": {
        "trial_number": 45,
        "value": 2.18,
        "params": {"ema_period": 60, "min_wick_ratio": 0.6}
    }
}
```

---

#### GET /api/optimize/studies - 获取研究列表

**查询参数**:
- `page` (int, default=1) - 页码
- `page_size` (int, default=20) - 每页数量
- `status` (str, optional) - 状态筛选

**响应**: `200 OK`
```json
{
    "total": 15,
    "page": 1,
    "page_size": 20,
    "studies": [
        {
            "study_id": 1,
            "study_name": "BTC/USDT:USDT:15m:20260402120000",
            "strategy_id": "pinbar_ema",
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "objective": "sharpe",
            "status": "completed",
            "best_value": 2.35,
            "n_trials": 100,
            "created_at": 1712055600000,
            "completed_at": 1712059200000
        }
    ]
}
```

---

#### DELETE /api/optimize/{study_id} - 删除研究

**路径参数**:
- `study_id` (int) - 研究 ID

**响应**: `200 OK`
```json
{
    "study_id": 1,
    "message": "Study deleted successfully"
}
```

---

## 四、Optuna 目标函数设计

### 4.1 目标函数接口

```python
# src/application/strategy_optimizer.py

class ObjectiveCalculator:
    """目标值计算器"""
    
    @staticmethod
    def calculate_sharpe(report) -> float:
        """
        计算夏普比率
        Sharpe = (Rp - Rf) / σp
        简化：假设无风险利率 Rf = 0
        """
        if report.total_trades < 2:
            return -999.0  # 惩罚交易过少
        if report.sharpe_ratio is not None:
            return float(report.sharpe_ratio)
        # 简化计算：使用收益/波动率
        returns = [float(report.avg_win), float(report.avg_loss)]
        if len(returns) < 2:
            return -999.0
        import numpy as np
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        if std_return == 0:
            return 0.0
        return float(mean_return / std_return)
    
    @staticmethod
    def calculate_pnl_max_dd(report) -> float:
        """计算收益/最大回撤比"""
        if report.max_drawdown == 0:
            return float('inf') if report.total_pnl > 0 else -999.0
        return float(report.total_pnl / report.max_drawdown)
    
    @staticmethod
    def calculate_sortino(report) -> float:
        """计算索提诺比率"""
        if report.total_trades < 2:
            return -999.0
        if report.sortino_ratio is not None:
            return float(report.sortino_ratio)
        if report.avg_loss >= 0:
            return -999.0
        downside_deviation = abs(float(report.avg_loss))
        if downside_deviation == 0:
            return 0.0
        return float(report.avg_win) / downside_deviation
    
    @staticmethod
    def calculate_total_return(report) -> float:
        """计算总收益率"""
        return float(report.total_return)
    
    @staticmethod
    def calculate_win_rate(report) -> float:
        """计算胜率"""
        return float(report.win_rate)
```

---

## 五、数据库设计

### 5.1 Optuna 研究表

```sql
-- Optuna 自动创建的表（使用 optuna.storages.RDBStorage）
-- optuna_studies: 研究信息
-- optuna_trials: 试验信息
-- optuna_trial_params: 试验参数
-- optuna_trial_values: 试验值

-- 我们的业务表
CREATE TABLE optuna_studies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    study_name VARCHAR(255) NOT NULL UNIQUE,
    strategy_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(20) NOT NULL,
    objective VARCHAR(50) NOT NULL,
    direction VARCHAR(20) NOT NULL,
    n_trials INTEGER NOT NULL DEFAULT 100,
    timeout_seconds INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    
    -- 最佳结果缓存
    best_trial_number INTEGER,
    best_value DECIMAL(20, 10),
    best_params_json TEXT,
    
    -- 时间戳
    created_at BIGINT NOT NULL,
    started_at BIGINT,
    completed_at BIGINT,
    
    -- 外键（关联 Optuna 内部表）
    optuna_study_id INTEGER
);

CREATE INDEX idx_optuna_studies_status ON optuna_studies(status);
CREATE INDEX idx_optuna_studies_strategy ON optuna_studies(strategy_id);
```

---

## 六、测试策略

### 6.1 单元测试

| 测试文件 | 测试内容 | 覆盖率目标 |
|----------|----------|-----------|
| `test_objective_calculator.py` | 目标值计算逻辑 | ≥90% |
| `test_strategy_optimizer.py` | 参数采样和回测流程 | ≥85% |
| `test_optuna_repository.py` | SQLite 持久化 | ≥90% |

### 6.2 集成测试

| 测试文件 | 测试内容 |
|----------|----------|
| `test_optimize_api.py` | API 端点集成 |
| `test_optimization_workflow.py` | 完整优化工作流 |

### 6.3 E2E 测试

| 测试文件 | 测试内容 |
|----------|----------|
| `test_e2e_optimization.py` | 端到端优化流程 |
| `test_concurrent_optimization.py` | 并发优化任务 |

---

## 七、实现检查清单

### 后端任务

- [ ] B1: 创建 `OptimizationObjective` 和 `ParameterType` 枚举
- [ ] B2: 创建 `ParameterDefinition` 和 `ParameterSpace` 模型
- [ ] B3: 创建 `OptimizeRequest` 和 `OptimizeResult` 模型
- [ ] B4: 实现 `ObjectiveCalculator` 类（目标值计算）
- [ ] B5: 实现 `StrategyOptimizer` 类（核心优化逻辑）
- [ ] B6: 实现 `OptunaRepository` 类（SQLite 持久化）
- [ ] B7: 实现 API 端点（/api/optimize/*）
- [ ] B8: 集成 Backtester 和 HistoricalDataRepository

### 前端任务

- [ ] F1: 创建 API 客户端函数
- [ ] F2: 参数配置 UI 组件
- [ ] F3: 优化进度监控页面
- [ ] F4: 可视化图表组件（参数重要性、优化路径）

### 测试任务

- [ ] T1: Optuna 目标函数单元测试
- [ ] T2: 参数空间验证测试
- [ ] T3: API 集成测试
- [ ] T4: E2E 测试

---

## 八、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Optuna 过拟合 | 中 | 高 | Walk-Forward 验证 + 样本外测试 |
| 回测耗时过长 | 高 | 中 | 早剪枝 + 超时机制 |
| 参数空间过大 | 中 | 中 | 默认限制 n_trials=100 |
| SQLite 并发写入 | 低 | 中 | WAL 模式 + busy_timeout |

---

*文档结束*
