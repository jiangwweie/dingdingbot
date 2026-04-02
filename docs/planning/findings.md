# 研究发现

> **说明**: 本文件记录有长期参考价值的技术发现、架构决策和踩坑记录。临时性发现已归档。

---

## 📑 目录

1. [P1 任务产品分析](#p1-任务产品分析)
2. [Phase 8 后端实现技术细节](#phase-8-后端实现技术细节)
3. [Phase 8 前端实现技术细节](#phase-8-前端实现技术细节)
4. [Phase 7 回测数据本地化架构](#phase-7-回测数据本地化架构)
5. [BTC 历史数据导入记录](#btc-历史数据导入记录)
6. [P1 问题系统性修复技术细节](#p1-问题系统性修复技术细节)
7. [P1/P2 问题修复技术细节](#p1p2-问题修复技术细节)
8. [P0-003/004 资金安全加固](#p0-003004-资金安全加固)
9. [Phase 6 前端架构](#phase-6-前端架构)
10. [API 契约与端点](#api-契约与端点)

---

## P1 任务产品分析

**日期**: 2026-04-02  
**分析人**: Product Manager  
**文档**: `docs/products/p1-tasks-analysis-brief.md`

### 核心发现

**三个 P1 任务的优先级排序**:

| 优先级 | 任务 | RICE 评分 | 核心理由 |
|--------|------|-----------|----------|
| **P0** | 策略参数可配置化 | 8.5 | 当前最大痛点，用户必须改代码配置参数 |
| **P1** | 订单管理级联展示 | 6.2 | 高频使用场景，已有后端数据基础 |
| **P2** | 订单详情页 K 线渲染 | 4.8 | 锦上添花功能，有第三方替代方案 |

### 用户故事摘要

#### 策略参数可配置化
- **核心用户**: 高级交易员（80% 活跃用户）
- **核心价值**: 配置修改时间从小时级降至分钟级
- **MVP 范围**: 参数编辑 UI + 热重载集成（2-3 人日）

#### 订单管理级联展示
- **核心用户**: 所有订单用户（100% 活跃用户）
- **核心价值**: 订单复盘效率提升 50%
- **MVP 范围**: 树形数据结构 + 展开/折叠 UI（4 人日）

#### 订单详情页 K 线渲染
- **核心用户**: 专业交易员（40% 活跃用户）
- **核心价值**: 提升专业体验，减少第三方切换
- **MVP 范围**: TradingView Lightweight Charts 集成（5 人日）

### 技术依赖分析

| 任务 | 前端依赖 | 后端依赖 | 技术风险 |
|------|----------|----------|----------|
| 策略参数可配置化 | 策略工作台组件（80% 完成） | ConfigManager 热重载 API（已完成） | 低 |
| 订单管理级联展示 | 订单列表组件重构 | OrderManager 订单链查询 | 中 |
| K 线渲染 (TradingView) | Lightweight Charts 库 | 订单 K 线上下文 API（已完成） | 中（性能） |

### 产品决策

**建议立即启动 P0 任务（策略参数可配置化）**，理由：
1. 用户痛点最强烈，直接影响用户使用门槛
2. 技术风险最低，已有热重载基础设施
3. 不依赖其他功能，可独立快速交付

---

---

## Phase 8 后端实现技术细节

**日期**: 2026-04-02  
**实现人**: Backend Developer

### 架构设计

#### 1. Optuna 集成架构

**核心组件**:
```
src/application/strategy_optimizer.py
├── PerformanceCalculator         # 性能指标计算器
│   ├── calculate_sharpe_ratio()  # 夏普比率
│   ├── calculate_sortino_ratio() # 索提诺比率
│   ├── calculate_max_drawdown()  # 最大回撤
│   └── calculate_pnl_dd_ratio()  # 收益回撤比
├── StrategyOptimizer             # 策略优化器核心
│   ├── start_optimization()      # 启动优化任务
│   ├── _run_optimization()       # 异步运行优化
│   ├── _create_objective_function() # 创建目标函数
│   └── _sample_params()          # 参数空间采样
└── OptimizationHistoryRepository # 历史持久化
    ├── save_trial()              # 保存试验记录
    ├── get_trials_by_job()       # 查询试验历史
    └── get_best_trial()          # 获取最佳试验
```

**设计决策**:
- **异步优化**: 使用 asyncio.Task 后台运行，不阻塞 API 请求
- **断点续研**: 通过 OptimizationHistoryRepository 持久化试验历史，支持从上次进度继续
- **可选依赖**: Optuna 作为可选依赖，未安装时优雅降级（返回错误提示）

#### 2. 参数空间定义

**Pydantic 模型设计**:
```python
class ParameterDefinition(BaseModel):
    """单个参数的定义"""
    name: str                              # 参数名称
    type: ParameterType                    # 参数类型 (INT/FLOAT/CATEGORICAL)
    low: Optional[Union[int, float]]       # 范围下限 (int/float 类型)
    high: Optional[Union[int, float]]      # 范围上限 (int/float 类型)
    step: Optional[Union[int, float]]      # 步长 (可选)
    choices: Optional[List[...]]           # 可选值列表 (categorical 类型)
    default: Optional[Union[int, float, str]]  # 默认值
```

**验证规则**:
- INT/FLOAT 类型必须提供 low 和 high，且 low < high
- CATEGORICAL 类型必须提供 choices 列表

#### 3. 多目标优化支持

**支持的目标类型**:
| 目标 | 说明 | 计算方法 |
|------|------|----------|
| SHARPE | 夏普比率 | 年化收益/年化标准差 |
| SORTINO | 索提诺比率 | 年化收益/下行标准差 |
| PNL_DD | 收益回撤比 | 总收益/最大回撤 |
| TOTAL_RETURN | 总收益率 | (最终余额 - 初始余额) / 初始余额 |
| WIN_RATE | 胜率 | 盈利交易数/总交易数 |
| MAX_PROFIT | 最大利润 | 总盈亏 (USDT) |

#### 4. 优化历史持久化

**数据库表结构**:
```sql
CREATE TABLE optimization_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    trial_number INTEGER NOT NULL,
    params TEXT NOT NULL,              -- JSON 格式存储参数
    objective_value REAL NOT NULL,     -- 目标函数值
    total_return REAL DEFAULT 0.0,     -- 总收益率
    sharpe_ratio REAL DEFAULT 0.0,     -- 夏普比率
    max_drawdown REAL DEFAULT 0.0,     -- 最大回撤
    win_rate REAL DEFAULT 0.0,         -- 胜率
    total_trades INTEGER DEFAULT 0,    -- 总交易数
    total_pnl REAL DEFAULT 0.0,        -- 总盈亏
    total_fees REAL DEFAULT 0.0,       -- 总手续费
    created_at TEXT NOT NULL,          -- ISO 8601 时间戳
    UNIQUE(job_id, trial_number)
)
```

### 技术难点与解决方案

#### 1. Optuna 异步支持

**问题**: Optuna 3.x 支持异步目标函数，但需要事件循环

**解决方案**:
```python
def objective(trial: Trial) -> float:
    # 检查停止标志
    if self._stop_flags.get(job_id, False):
        raise optuna.TrialPruned("任务被停止")
    
    # 运行异步目标函数
    return asyncio.get_event_loop().run_until_complete(
        objective_async(trial)
    )
```

#### 2. 断点续研实现

**问题**: 如何从中断处继续优化

**解决方案**:
1. 每次试验完成后自动保存到 SQLite
2. 重启时使用 `study.tell()` 告知 Optuna 已完成的试验
3. 通过 `resume_from_trial` 参数指定从第几个试验继续

### 测试结果

**单元测试覆盖率**: 100% (22/22 测试通过)

| 测试类别 | 测试数 | 通过率 |
|----------|--------|--------|
| PerformanceCalculator | 5 | 100% |
| Parameter Sampling | 4 | 100% |
| Objective Calculation | 7 | 100% |
| Build Backtest Request | 2 | 100% |
| Edge Cases | 2 | 100% |
| Job Management | 2 | 100% |

### 遗留问题

1. **索提诺比率计算**: 当前实现返回 0.0，需要接入真实的回测收益率序列
2. **参数重要性分析**: 待 Optuna 集成后实现
3. **并行优化**: 目前单任务串行，未来可支持多任务并行

---

## Phase 8 前端实现技术细节

**日期**: 2026-04-02  
**实现人**: Frontend Developer

### 架构决策

#### 1. 图表库选择：Recharts vs Plotly.js

**决策**: 使用 Recharts（已安装）而非 Plotly.js

**原因**:
- 项目已安装 Recharts，无需新增依赖
- Recharts 与 React 集成更紧密
- 包体积更小（Plotly.js ~3MB，Recharts ~200KB）
- 功能满足需求（折线图、柱状图、散点图）

**妥协**:
- 平行坐标图使用简化的散点图矩阵替代
- 待后续有需要时可引入 Plotly.js

#### 2. 参数空间设计

**预定义参数模板**: 15+ 个参数模板，分为 4 类：
- **Trigger - Pinbar**: 最小影线占比、最大实体占比、实体位置容差
- **Trigger - Engulfing**: 最小实体占比、要求完全吞没
- **Filter - EMA**: EMA 周期
- **Filter - MTF**: MTF 要求确认
- **Filter - Volume**: 成交量激增倍数、回看周期
- **Filter - Volatility**: 波动率最小/最大 ATR 比率
- **Filter - ATR**: ATR 周期、最小比率
- **Risk**: 最大亏损比例、默认杠杆倍数

**参数类型**:
- `int`: 整数范围（如 EMA 周期 9-50）
- `float`: 浮点范围（如 Pinbar 最小影线占比 0.5-0.8）
- `categorical`: 离散选择（如 MTF 要求确认 [true, false]）

#### 3. 优化目标设计

支持 5 种优化目标：
1. **sharpe** - 夏普比率（收益风险比，越高越好）
2. **sortino** - 索提诺比率（仅考虑下行风险）
3. **pnl_maxdd** - 收益/最大回撤比
4. **total_return** - 总收益率
5. **win_rate** - 胜率

### 组件设计

#### ParameterSpaceConfig

**职责**: 参数空间配置表单

**子组件**:
- `IntRangeInput` - 整数范围输入
- `FloatRangeInput` - 浮点范围输入（支持对数刻度）
- `CategoricalInput` - 离散选择输入（支持 JSON 解析）
- `ObjectiveSelector` - 优化目标选择器

**交互**:
- 分类筛选（全部、Trigger、Filter、Risk）
- 一键添加预定义参数
- 实时删除已配置参数

#### OptimizationProgress

**职责**: 优化进度监控

**特性**:
- 3 秒自动轮询状态
- 实时进度条显示
- 当前最优参数展示
- 已用时间/预计剩余时间
- 停止优化按钮

#### OptimizationResults

**职责**: 优化结果可视化

**子组件**:
- `BestParamsCard` - 最佳参数卡片（含指标网格）
- `OptimizationPathChart` - 优化路径图（Recharts LineChart）
- `ParameterImportanceChart` - 参数重要性图（Recharts BarChart）
- `ParallelCoordinatesChart` - 参数 - 性能散点图（Recharts ScatterChart）
- `TopTrialsTable` - Top N 试验表格

**交互**:
- 复制/下载最佳参数
- 应用参数到策略（预留接口）
- 参数选择器（选择展示的平行坐标参数）

### API 设计

**端点**:
- `POST /api/optimization/run` - 启动优化
- `GET /api/optimization/:id/status` - 获取状态
- `GET /api/optimization/:id/results` - 获取结果
- `POST /api/optimization/:id/stop` - 停止优化
- `GET /api/optimization` - 获取历史列表

**类型定义**:
```typescript
interface OptimizationRequest {
  symbol: string;
  timeframe: string;
  start_time: number;
  end_time: number;
  objective: OptimizationObjective;
  parameter_space: ParameterSpace;
  n_trials: number;
  timeout_seconds?: number;
  seed?: number;
}
```

### 技术债

1. **平行坐标图简化**: 当前使用散点图矩阵替代，功能受限
2. **历史记录未实现**: 需要后端 API 支持
3. **参数应用接口**: 预留 `onApplyParams` 回调，需后端支持

---

## Phase 7 回测数据本地化架构

### 修复概览 (2026-04-02)

**修复原则**:
- 有长远考虑 - 设计可扩展、可维护的解决方案
- 系统性修复 - 不是补丁式修复，而是架构级改进
- 保持一致性 - 与现有代码风格和规范保持一致

### P1-001: 类型注解不完整

**问题**: `BacktestOrderSummary.direction` 使用 `str`，无法享受类型检查好处。

**修复方案**:
```python
# 修复前
direction: str

# 修复后
from src.domain.models import Direction
direction: Direction  # Pydantic 自动序列化/反序列化
```

**影响**:
- 前后端类型定义统一
- IDE 自动补全和类型检查
- 运行时验证增强

### P1-002: 日志级别不当

**问题**: 降级逻辑使用 INFO 日志，高频操作可能导致日志刷屏。

**修复方案**:
```python
# 修复前
logger.info(f"Local data insufficient...")

# 修复后
logger.debug(f"Local data insufficient ({len(klines)} < {limit}), "
             f"fetching from exchange for {symbol} {timeframe}...")
```

**影响**:
- 生产环境日志更清晰
- 调试时仍可查看详细流程
- 添加了 symbol/timeframe 上下文

### P1-003: 魔法数字

**问题**: K 线前后取 10 根、默认 25 根等硬编码。

**修复方案**:
```python
class BacktestConfig:
    """回测相关配置常量"""
    KLINE_WINDOW_BEFORE = 10  # 前取 10 根
    KLINE_WINDOW_AFTER = 10   # 后取 10 根
    DEFAULT_KLINE_WINDOW = 25  # 默认获取 25 根 K 线用于预览
```

**影响**:
- 配置集中管理
- 支持未来通过配置文件调整
- 代码可读性提升

### P1-004: 时间框架映射不完整

**问题**: 仅支持 6 种时间框架，多处定义导致不一致。

**修复方案**:
1. 扩展 `domain/timeframe_utils.py` 的 `TIMEFRAME_TO_MS`:
```python
TIMEFRAME_TO_MS = {
    "1m": 60 * 1000,
    "3m": 3 * 60 * 1000,
    ...
    "1M": 30 * 24 * 60 * 60 * 1000,  # 月度 K 线
}
```

2. api.py 统一使用工具函数:
```python
from src.domain.timeframe_utils import parse_timeframe_to_ms
kline_interval_ms = parse_timeframe_to_ms(timeframe)
```

**支持的时间框架** (16 种):
1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 2d, 3d, 1w, 2w, 1M

### P1-005: 删除订单后未级联清理

**问题**: 删除 ENTRY 订单可能留下孤立的 TP/SL 订单。

**修复方案**:
```python
async def delete_order(self, order_id: str, cascade: bool = True) -> None:
    # 获取订单判断角色
    order = await self.get_order(order_id)
    
    if cascade and order.order_role == OrderRole.ENTRY:
        # 删除子订单（通过 parent_order_id）
        await self._db.execute(
            "DELETE FROM orders WHERE parent_order_id = ?", (order_id,)
        )
        # 删除 OCO 组订单
        if order.oco_group_id:
            await self._db.execute(
                "DELETE FROM orders WHERE oco_group_id = ? AND id != ?",
                (order.oco_group_id, order_id)
            )
    
    # 删除主订单
    await self._db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
```

**影响**:
- 数据完整性保证
- 默认 cascade=True 确保安全
- 支持关闭级联删除（特殊场景）

### P1-006: ORM 风格不一致 (技术债)

**问题**: OrderRepository 使用 aiosqlite 而非 SQLAlchemy 2.0。

**处理方案**:
- 记录到技术债清单
- 待后续渐进式迁移
- 当前先统一接口风格

---

## Phase 7 回测数据本地化架构

### 核心设计定调 (2026-04-02)

**技术选型**:
| 层次 | 选型 | 理由 |
|------|------|------|
| **回测引擎** | 自研 MockMatchingEngine | 与 v3.0 实盘逻辑 100% 一致性 |
| **K 线存储** | SQLite | 统一技术栈、事务支持、数据量小 (85MB) |
| **读取策略** | 本地优先 + 自动补充 | 用户透明，首次缓存，后续 50x 加速 |

**为什么不使用 Parquet**:
- 数据量小 (85MB) → 无需列式存储优势
- 技术栈统一 → 与现有 SQLAlchemy ORM 一致
- 事务支持 → ACID 完整性，幂等写入

**数据流架构**:
```
Backtester → HistoricalDataRepository → SQLite (本地优先)
                                      ↓
                              ExchangeGateway (自动补充)
```

**预期性能提升**:
- 单次回测 (15m, 1 个月): 5s → 0.1s (50x)
- Optuna 调参 (100 trial): 2 小时 → 2 分钟 (60x)

### Phase 7 验证结果 (2026-04-02 更新)

**测试通过率**: 100%
- MTF 数据对齐测试：34/34 通过
- 回测数据源测试：12/12 通过
- 数据仓库测试：23/23 通过

**性能实测**:
| 测试项 | 耗时 | 对比交易所源 |
|--------|------|--------------|
| 读取 100 根 15m K 线 | 20.30ms | 100-250x |
| 读取 1000 根 15m K 线 | 8.89ms | 200-500x |
| MTF 对齐 (2977 条) | 128.16ms | - |
| 连续读取 10 次 (缓存) | 1.36ms/次 | - |

**发现的问题**:
- 942 条 `high < low` 异常记录 (ETL 列错位导致)
- 影响时间范围：2024-12-05 ~ 2024-12-07
- 修复建议：重新导入异常时间段数据

详细验证报告：`docs/planning/phase7-validation-report.md`

---

## BTC 历史数据导入记录

### 导入汇总 (2026-04-02)

| 指标 | 结果 |
|------|------|
| **处理文件数** | 296 个 ZIP ✅ |
| **失败** | 0 ❌ |
| **总导入行数** | 285,877 行 |
| **数据库大小** | 56 MB |
| **时间跨度** | 2020-01 → 2026-02 (75 个月) |

**分周期统计**:
| 周期 | 记录数 | 说明 |
|------|--------|------|
| 15m | 216,096 | 主力回测周期 |
| 1h | 54,024 | MTF 过滤用 |
| 4h | 13,506 | MTF 过滤用 |
| 1d | 2,251 | 大周期趋势 |

**ETL 工具**:
- `scripts/etl/validate_csv.py` - CSV 验证工具
- `scripts/etl/etl_converter.py` - ETL 转换工具
- 支持：单个转换、ZIP 解压转换、批量转换

**数据库路径**: `data/backtests/market_data.db`

---

## P1/P2 问题修复技术细节

### P1-1: trigger_price 零值风险

**根本原因**: Python 的 falsy 判断陷阱

```python
# 问题代码
current_trigger = sl_order.trigger_price or position.entry_price

# 问题场景
sl_order.trigger_price = Decimal("0")  # 假设为 0
# current_trigger 会错误地使用 position.entry_price
```

**修复要点**:
- 显式 `is not None` 判断，避免 falsy 陷阱
- Decimal("0") 是合法的 trigger_price 值（虽然业务上不应该）

---

### P1-2: STOP_LIMIT 订单缺少价格偏差检查

**根本原因**: 订单类型判断不完整

```python
# 问题代码 (仅检查 LIMIT)
if order_type == OrderType.LIMIT and price is not None:
    price_check, ticker_price, deviation = await self._check_price_reasonability(...)
```

**修复要点**:
- STOP_LIMIT 订单的限价单部分同样需要价格合理性检查
- 使用 `in (OrderType.LIMIT, OrderType.STOP_LIMIT)` 判断

---

### P1-3: trigger_price 字段应从 CCXT 响应提取

**根本原因**: CCXT 字段映射不完整

**修复要点**:
- 多字段回退解析，适配不同交易所
- 使用 Decimal 精度转换

---

### P2-1: 魔法数字配置化

**优化方案**:
```python
class RiskManagerConfig(BaseModel):
    trailing_percent: Decimal = Decimal("0.02")
    step_threshold: Decimal = Decimal("0.005")
    breakeven_threshold: Decimal = Decimal("0.01")
```

**收益**: 支持配置管理、回测调优

---

### P2-2: 类常量移到配置文件

**优化方案**:
```yaml
# config/core.yaml
capital_protection:
  min_notional:
    binance: 5      # Binance 5 USDT
    bybit: 2        # Bybit 2 USDT
    okx: 5          # OKX 5 USDT
  price_deviation_threshold: "0.10"
  extreme_price_deviation_threshold: "0.20"
```

**收益**: 多交易所适配性提升

---

## P0-003/004 资金安全加固

### P0-004: 订单参数合理性检查

#### 1. 最小名义价值检查

**实现位置**: `src/application/capital_protection.py::_check_min_notional()`

**Binance 规则**:
- NOTIONAL: 名义价值 ≥ 5 USDT (部分币种 100 USDT)
- 公式：`notional_value = quantity * price`

**检查逻辑**:
```python
def _check_min_notional(
    self,
    quantity: Decimal,
    price: Decimal,
) -> tuple[bool, Decimal]:
    notional_value = quantity * price
    passed = notional_value >= self.MIN_NOTIONAL  # 5 USDT
    return passed, notional_value
```

**失败处理**: 拒绝订单，记录 W 级日志

---

#### 2. 价格合理性检查

**实现位置**: `src/application/capital_protection.py::_check_price_reasonability()`

**检查逻辑**:
```python
async def _check_price_reasonability(
    self,
    symbol: str,
    order_price: Decimal,
) -> tuple[bool, Decimal, Decimal]:
    ticker_price = await self._gateway.fetch_ticker_price(symbol)
    deviation = abs(order_price - ticker_price) / ticker_price
    
    # 正常行情：≤10%，极端行情：≤20%
    threshold = self.EXTREME_PRICE_DEVIATION_THRESHOLD if is_extreme else self.PRICE_DEVIATION_THRESHOLD
    passed = deviation <= threshold
    return passed, ticker_price, deviation
```

---

## Phase 6 前端架构

### 前端 API 调用层 (`web-front/src/lib/api.ts`)

**订单管理**:
```typescript
// POST /api/v3/orders (开仓)
async function createOrder(payload: OrderRequest): Promise<OrderResponse>

// GET /api/v3/orders (查询订单列表)
async function fetchOrders(params?: QueryParams): Promise<Order[]>

// POST /api/v3/orders/{id}/cancel (取消订单)
async function cancelOrder(orderId: string): Promise<OrderResponse>
```

**仓位管理**:
```typescript
// GET /api/v3/positions
async function fetchPositions(symbol?: string): Promise<PositionResponse>

// POST /api/v3/positions/{position_id}/close
async function closePosition(positionId: string): Promise<OrderResponse>
```

**账户管理**:
```typescript
// GET /api/v3/account/balance
async function fetchAccountBalance(): Promise<AccountResponse>

// GET /api/v3/account/snapshot
async function fetchAccountSnapshot(): Promise<AccountSnapshot>
```

---

## P0-005 Binance Testnet 验证 (2026-04-01)

### 验证结果：通过 ✅

**测试环境**: Binance Testnet  
**测试范围**: 订单执行、DCA、持仓管理、对账服务、WebSocket 推送

### 修复的问题

| 问题 | 修复文件 | 说明 |
|------|----------|------|
| 订单 ID 混淆 | `exchange_gateway.py` | `cancel_order` 和 `fetch_order` 使用 `exchange_order_id` 而非内部 UUID |
| leverage None 处理 | `exchange_gateway.py` | `int(leverage_val) if leverage_val is not None else 1` |
| cancel_order 参数 | `exchange_gateway.py` | 修复参数命名问题 |

### 对账服务发现

- **孤儿订单处理**: 发现 7 个孤儿订单 (交易所有 DB 无)
- **处理逻辑**: 导入 orphan entry order → 创建 missing signal
- **幽灵订单**: 无发现 (DB 有交易所无)

### WebSocket 验证

- ✅ 连接建立成功
- ✅ 订单状态实时更新
- ✅ 重连机制正常 (指数退避：1s → 2s → 4s → 8s → 16s → 32s)

---

## Phase 6 前端组件检查 (2026-04-01)

### 组件完成度：100%

| 组件 | 文件 | 状态 |
|------|------|------|
| 仓位管理页面 | `web-front/src/pages/Positions.tsx` | ✅ |
| 订单管理页面 | `web-front/src/pages/Orders.tsx` | ✅ |
| 回测报告组件 | `web-front/src/pages/PMSBacktest.tsx` | ✅ |
| 账户页面 | `web-front/src/pages/Account.tsx` | ✅ |
| 止盈可视化 | `TPChainDisplay.tsx` + `SLOrderDisplay.tsx` | ✅ |

### 发现的小问题

| 问题 | 优先级 | 修复建议 |
|------|--------|----------|
| Orders.tsx 日期筛选未传递给 API | P1 | 在 `fetchOrders` URL 参数中添加 `startDate`/`endDate` |
| Positions.tsx 类型一致性 | P3 | 验证 `totalUnrealizedPnl` 类型匹配 |

---

## Phase 6 E2E 测试验证 (2026-04-01)

### 测试结果：80/103 通过 (77.7%)

- **通过**: 80 (77.7%)
- **跳过**: 23 (22.3%) - 因 window 标记过滤
- **失败**: 0

### 核心功能验证状态

| 模块 | 测试数 | 状态 |
|------|--------|------|
| 回测服务 | 11 | ✅ |
| 配置验证 | 15 | ✅ |
| 真实交易所 API | 19 | ✅ |
| 完整业务链 | 9 | ✅ |
| 动态规则 | 10 | ✅ |

### 建议修复

在 `pytest.ini` 中注册自定义标记 (`window1`/`window2`/`window3`/`window4`/`e2e`)

---

## 配置管理决策 (2026-04-02)

### 配置统一管理方案决策

**背景**: 当前系统参数分散在 YAML 配置文件和数据库中，需要集中管理。

**决策内容**:
- ❌ **不迁移 YAML 配置**: 产品尚未成熟，YAML 配置保持现状，不进行迁移
- ✅ **新增配置管理功能**: 支持配置导出/导入 YAML 功能，便于备份和迁移
- ✅ **数据库作为运行态**: 运行参数存储在数据库中，支持热更新

**配置架构**:
```
┌─────────────────────────────────────────────────────┐
│                   配置管理架构                       │
├─────────────────────────────────────────────────────┤
│                                                      │
│  config/core.yaml ──────► 系统核心配置 (只读)        │
│  config/user.yaml ──────► 用户配置 (API 密钥等)       │
│                                                      │
│  SQLite (v3_dev.db) ────► 运行参数 (热更新)          │
│    - 策略参数                                        │
│    - 风控配置                                        │
│    - 交易对配置                                      │
│                                                      │
│  导出/导入接口 ────────► YAML 备份/恢复              │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**后续任务**:
- 配置导出 API: `GET /api/v3/config/export` → YAML 文件
- 配置导入 API: `POST /api/v3/config/import` ← YAML 文件
- 配置对比功能：数据库 vs YAML 差异对比

---

## 历史发现归档

以下主题的技术发现已归档至 `archive/` 目录：
- P6-005: 账户净值曲线可视化
- P6-006: PMS 回测报告组件
- P6-007: 多级别止盈可视化
- Phase 6 详细架构分析

---

*最后更新：2026-04-02*
