# ADR-002: BT-2 资金费率模拟架构设计

> **状态**: 进行中 (In Progress)
> **创建日期**: 2026-04-07
> **优先级**: P0
> **关联任务**: BT-2 资金费率模拟

---

## 1. 需求分析

### 1.1 业务背景

**资金费率 (Funding Rate)** 是永续合约市场的核心机制，用于锚定合约价格与现货价格。

**业务规则**:
- 资金费率每 8 小时结算一次（每日 3 次：00:00 / 08:00 / 16:00 UTC）
- 多头支付/收取：`持仓价值 × 资金费率`
- 空头收取/支付：`持仓价值 × 资金费率`
- 费率符号决定方向：正费率 → 多头支付给空头；负费率 → 空头支付给多头

**当前回测系统的缺陷**:
- 缺少资金费用计算 → 回测收益虚高
- 无法评估长期持仓策略的真实成本
- 用户无法准确对比不同策略的净收益

### 1.2 简化模型设计理由

**真实世界的复杂性**:
- 资金费率浮动（市场供需决定，-0.04% ~ +0.04% 常见）
- 精确的 8 小时结算时点
- 持仓时长不足 8 小时按比例计算

**简化模型选择**:
| 方案 | 计算方式 | 精度 | 复杂度 | 选择 |
|------|----------|------|--------|------|
| 固定费率 | 0.01% × 持仓次数 | 中 | 低 | ✅ |
| 历史费率回测 | 逐 8 小时查询历史费率 | 高 | 高 | ❌ |
| 动态费率模型 | 基于市场情绪预测 | 低 | 极高 | ❌ |

**选择固定费率 0.01% 的理由**:
1. **长期平均值**: Binance/Bybit 历史数据显示，BTC/USDT 永续合约资金费率长期均值约 0.01%
2. **简化实现**: 无需外部数据依赖，回测完全离线运行
3. **保守估计**: 0.01% 属于中性偏保守估计，避免过度乐观
4. **符号区分**: 多头支付（负收益），空头收取（正收益）

### 1.3 计算模型

```
资金费用 = 持仓价值 × 资金费率 × 持仓时长系数

其中:
- 持仓价值 = 入场价格 × 持仓数量
- 资金费率 = 0.0001 (0.01%)
- 持仓时长系数 = 持仓 K 线数量 / (24 小时 / 8 小时) = 持仓 K 线数量 / 3 (对于 1h K 线)
```

**简化公式 (按 K 线数量估算)**:
```
# 对于 1h K 线 (每根 K 线代表 1 小时)
funding_events = holding_hours / 8
total_funding_cost = entry_price × position_size × funding_rate × funding_events

# 对于任意时间周期
timeframe_hours = {
    "15m": 0.25,
    "1h": 1,
    "4h": 4,
    "1d": 24,
    "1w": 168
}
funding_events = (klines_held × timeframe_hours[timeframe]) / 8
```

---

## 2. 架构方案

### 2.1 KV 配置设计（参考滑点配置）

**配置键命名规范**:
```
backtest.funding_rate_enabled    # 资金费率开关 (boolean)
backtest.funding_rate            # 资金费率值 (Decimal)
```

**配置存储结构** (config_entries_v2 表):
```sql
INSERT INTO config_entries_v2
(config_key, config_value, value_type, version, profile_name, updated_at)
VALUES
('backtest.funding_rate_enabled', 'true', 'boolean', 'v1.0.0', 'default', 1712476800000),
('backtest.funding_rate', '0.0001', 'decimal', 'v1.0.0', 'default', 1712476800000)
```

### 2.2 配置优先级设计

**优先级顺序**（从高到低）:
```
1. API Request 参数 (用户显式覆盖)
2. KV 配置 (config_entries_v2 数据库存储)
3. Code Defaults (代码硬编码默认值)
```

**优先级合并逻辑** (backtester.py):
```python
# 资金费率开关配置
funding_rate_enabled = (
    request.funding_rate_enabled
    if request.funding_rate_enabled is not None
    else (kv_configs.get('funding_rate_enabled') if kv_configs else None)
)
if funding_rate_enabled is None:
    funding_rate_enabled = True  # 默认开启

# 资金费率值配置
funding_rate = (
    kv_configs.get('funding_rate')
    if kv_configs and kv_configs.get('funding_rate') is not None
    else Decimal('0.0001')  # 默认 0.01% 每 8 小时
)
```

### 2.3 资金费用计算逻辑

**核心计算流程**:
```python
# Step 1: 在回测主循环中，每根 K 线检查资金费用
for kline in klines:
    # ... 订单撮合逻辑 ...

    # Step 2: 对每个持仓计算资金费用
    for position in positions_map.values():
        if not position.is_closed and position.current_qty > 0:
            funding_cost = self._calculate_funding_cost(
                position=position,
                kline=kline,
                funding_rate=funding_rate,
                enabled=funding_rate_enabled,
            )
            # Step 3: 更新仓位累计资金费用
            position.total_funding_paid += funding_cost
            total_funding_cost += funding_cost
```

**计算方法**:
```python
def _calculate_funding_cost(
    self,
    position: Position,
    kline: Kline,
    funding_rate: Decimal,
    enabled: bool,
) -> Decimal:
    """计算单根 K 线的资金费用"""
    if not enabled:
        return Decimal('0')

    # 持仓价值 = 入场价 × 持仓量
    position_value = position.entry_price * abs(position.current_qty)

    # 时间周期系数 (1h K 线 = 1/8 个资金费率周期)
    timeframe_hours = {
        "15m": Decimal('0.25'),
        "1h": Decimal('1'),
        "4h": Decimal('4'),
        "1d": Decimal('24'),
        "1w": Decimal('168'),
    }
    hours = timeframe_hours.get(kline.timeframe, Decimal('1'))
    funding_events = hours / Decimal('8')

    # 资金费用 = 持仓价值 × 费率 × 周期数
    # 多头支付（负），空头收取（正）
    if position.direction == Direction.LONG:
        return position_value * funding_rate * funding_events
    else:
        return -position_value * funding_rate * funding_events  # 空头收取，为负成本（正收益）
```

**注意**: 空头收取资金费用，在会计处理上为"负成本"（即收益），因此总资金费用对于空头为负值。

---

## 3. 数据模型变更

### 3.1 Position 模型新增字段

**文件**: `src/domain/models.py`

**新增字段**:
```python
class Position(FinancialModel):
    """
    资产层：PMS 系统的绝对核心，代表当前持有敞口
    """
    # ... 现有字段 ...
    total_funding_paid: Decimal = Field(
        default=Decimal('0'),
        description="累计支付的资金费用 (BT-2)"
    )
```

**字段说明**:
- `total_funding_paid`: 累计支付的资金费用
  - 多头持仓：通常为正值（支付费用）
  - 空头持仓：通常为负值（收取费用）
  - 平仓时不再计算，仅持仓期间累计

### 3.2 PMSBacktestReport 新增字段

**文件**: `src/domain/models.py`

**新增字段**:
```python
class PMSBacktestReport(FinancialModel):
    """
    v3.0 PMS 模式回测报告
    """
    # ... 现有字段 ...
    total_funding_cost: Decimal = Field(
        default=Decimal('0'),
        description="总资金费用 (BT-2)"
    )
```

**字段说明**:
- `total_funding_cost`: 回测期间所有仓位的总资金费用
  - 计算方式：所有 `position.total_funding_paid` 求和
  - 用于评估策略的整体资金成本

### 3.3 BacktestRequest 新增字段

**文件**: `src/domain/models.py`

**新增字段**:
```python
class BacktestRequest(BaseModel):
    """Request model for backtest endpoint"""
    # ... 现有字段 ...

    # BT-2: 资金费率配置
    funding_rate_enabled: Optional[bool] = Field(
        default=None,
        description="是否启用资金费用计算 (default: True, or from KV config)"
    )
    # 注意：funding_rate 通过 KV 配置管理，不在 request 中直接暴露
```

**设计理由**:
- `funding_rate_enabled` 允许用户临时关闭资金费用计算进行对比
- `funding_rate` 通过 KV 配置管理，支持 Profile 级别的默认值设置

---

## 4. 关联影响分析

### 4.1 配置管理模块

**影响文件**:
- `src/infrastructure/config_entry_repository.py` ✅ 已完成
- `src/application/config_manager.py` ✅ 已完成

**已变更内容**:

#### ConfigEntryRepository
```python
# 默认配置 (get_backtest_configs 方法)
DEFAULT_BACKTEST_CONFIG = {
    'backtest.slippage_rate': Decimal('0.001'),
    'backtest.fee_rate': Decimal('0.0004'),
    'backtest.initial_balance': Decimal('10000'),
    'backtest.tp_slippage_rate': Decimal('0.0005'),
    'backtest.funding_rate_enabled': True,  # BT-2 新增
    'backtest.funding_rate': Decimal('0.0001'),  # BT-2 新增
}
```

#### ConfigManager
```python
# 文档注释已更新 (1363-1364 行)
# - funding_rate_enabled: bool (默认 True)
# - funding_rate: Decimal (默认 0.0001, 每 8 小时)

# save_backtest_configs 文档注释已更新 (1395-1396 行)
# - funding_rate_enabled (bool)
# - funding_rate (Decimal)
```

**影响评估**: 配置读取/保存逻辑已就绪，无需额外修改。

### 4.2 回测引擎模块

**影响文件**:
- `src/application/backtester.py` ⚠️ 部分完成

**已完成内容**:
1. KV 配置读取逻辑 (1140-1151 行) ✅
2. 配置优先级合并逻辑 ✅
3. 日志输出配置信息 ✅
4. 总资金费用累计变量初始化 (1211 行) ✅

**待完成内容**:
1. `._calculate_funding_cost()` 方法实现 ❌
2. 回测主循环中调用资金费用计算 ❌
3. Position 累计资金费用更新 ❌
4. PMSBacktestReport 字段填充 ❌

**修改位置** (`_run_v3_pms_backtest` 方法):

```python
# Step 8: 动态风险管理主循环 (约 1395 行后插入)
for kline in klines:
    # ... 现有订单撮合逻辑 ...

    # ===== BT-2: 资金费用计算 =====
    if funding_rate_enabled:
        for position in positions_map.values():
            if not position.is_closed and position.current_qty > 0:
                funding_cost = self._calculate_funding_cost(
                    position=position,
                    kline=kline,
                    funding_rate=funding_rate,
                )
                position.total_funding_paid += funding_cost
                total_funding_cost += funding_cost
```

```python
# Step 9: Build PMSBacktestReport (约 1425 行)
report = PMSBacktestReport(
    # ... 现有字段 ...
    total_fees_paid=total_fees_paid,
    total_slippage_cost=total_slippage_cost,
    total_funding_cost=total_funding_cost,  # BT-2 新增
    # ...
)
```

```python
# 新增辅助方法 (在 backtester.py 类中)
def _calculate_funding_cost(
    self,
    position: Position,
    kline: KlineData,
    funding_rate: Decimal,
) -> Decimal:
    """
    计算单根 K 线的资金费用

    Args:
        position: 持仓对象
        kline: 当前 K 线数据
        funding_rate: 资金费率 (Decimal)

    Returns:
        资金费用金额（正数=支付，负数=收取）
    """
    # 持仓价值
    position_value = position.entry_price * abs(position.current_qty)

    # 时间周期系数
    timeframe_hours = {
        "15m": Decimal('0.25'),
        "1h": Decimal('1'),
        "4h": Decimal('4'),
        "1d": Decimal('24'),
        "1w": Decimal('168'),
    }
    hours = timeframe_hours.get(kline.timeframe, Decimal('1'))
    funding_events = hours / Decimal('8')

    # 资金费用计算 (多头支付，空头收取)
    funding_cost = position_value * funding_rate * funding_events

    # 多头支付为正成本，空头收取为负成本（正收益）
    if position.direction == Direction.LONG:
        return funding_cost
    else:
        return -funding_cost
```

### 4.3 撮合引擎模块

**影响文件**:
- `src/domain/matching_engine.py`

**影响评估**: **无直接影响**

**理由**:
- 资金费用计算在回测主循环中执行，独立于订单撮合
- MockMatchingEngine 仅负责订单执行、手续费计算
- 资金费用是持仓期间的累计成本，非交易时点费用

**可选扩展** (未来):
- 如需在 `_execute_fill` 中初始化 `watermark_price` 时考虑资金费用基准
- 当前设计无需修改

### 4.4 数据模型模块

**影响文件**:
- `src/domain/models.py` ✅ 已完成

**已变更内容**:
1. `Position.total_funding_paid` 字段 ✅
2. `PMSBacktestReport.total_funding_cost` 字段 ✅
3. `BacktestRequest.funding_rate_enabled` 字段 ✅

**影响评估**: 模型变更已完成，Pydantic 会自动处理序列化和验证。

### 4.5 API 接口模块

**影响文件**:
- `src/interfaces/api.py` (待确认)

**影响评估**: **需审查**

**待确认内容**:
1. `/backtest` 端点是否需要接受 `funding_rate_enabled` 参数？
2. 回测结果响应是否需要新增 `total_funding_cost` 字段？
3. 前端是否需要资金费用开关的 UI 控制？

**建议修改**:
```python
# BacktestRequest 已经支持 funding_rate_enabled 字段
# API 端点无需修改，Pydantic 会自动处理
```

### 4.6 前端展示模块

**影响文件**:
- `web-front/` (待确认)

**影响评估**: **待前端开发确认**

**建议新增展示**:
1. 回测结果页面新增"总资金费用"字段
2. 回测配置表单新增"资金费用开关"复选框
3. 仓位详情弹窗新增"累计资金费用"字段

### 4.7 数据库存储模块

**影响文件**:
- `src/infrastructure/repositories/backtest_report_repository.py` (待确认)

**影响评估**: **需审查**

**待确认内容**:
1. `backtest_reports` 表是否需要新增 `total_funding_cost` 列？
2. 现有查询语句是否需要调整？

**建议迁移 SQL**:
```sql
-- 添加总资金费用列
ALTER TABLE backtest_reports
ADD COLUMN total_funding_cost DECIMAL(20, 10) DEFAULT 0;

-- 添加索引（可选）
CREATE INDEX idx_backtest_reports_funding_cost
ON backtest_reports(total_funding_cost);
```

**注意**: 对于已存在的历史数据，`total_funding_cost` 默认为 0，不影响现有功能。

---

## 5. 接口契约

### 5.1 BacktestRequest 新增字段

**请求体示例**:
```json
{
  "symbol": "BTC/USDT:USDT",
  "timeframe": "1h",
  "limit": 1000,
  "mode": "v3_pms",
  "funding_rate_enabled": true,
  "initial_balance": "10000",
  "slippage_rate": "0.001",
  "fee_rate": "0.0004",
  "tp_slippage_rate": "0.0005"
}
```

**字段说明**:
| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `funding_rate_enabled` | `boolean` | 否 | `true` | 是否启用资金费用计算 |

### 5.2 API 响应字段变更

**PMSBacktestReport 响应示例**:
```json
{
  "strategy_id": "pinbar",
  "strategy_name": "Pinbar Strategy",
  "initial_balance": "10000",
  "final_balance": "10523.45",
  "total_return": "5.2345",
  "total_trades": 15,
  "winning_trades": 9,
  "losing_trades": 6,
  "win_rate": "60.0",
  "total_pnl": "523.45",
  "total_fees_paid": "12.34",
  "total_slippage_cost": "5.67",
  "total_funding_cost": "-2.50",
  "max_drawdown": "3.2",
  "positions": [...]
}
```

**新增字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| `total_funding_cost` | `Decimal` | 总资金费用（正=支付，负=收取） |

### 5.3 配置 API 变更

**新增配置接口** (如需要):
```http
GET /api/v1/backtest/configs
```

**响应示例**:
```json
{
  "slippage_rate": "0.001",
  "fee_rate": "0.0004",
  "initial_balance": "10000",
  "tp_slippage_rate": "0.0005",
  "funding_rate_enabled": true,
  "funding_rate": "0.0001"
}
```

**保存配置接口** (如需要):
```http
POST /api/v1/backtest/configs
Content-Type: application/json

{
  "funding_rate_enabled": true,
  "funding_rate": "0.0001"
}
```

---

## 6. 实施计划

### 6.1 任务分解

| 任务 ID | 任务名称 | 工时估算 | 依赖 | 状态 |
|---------|----------|----------|------|------|
| BT-2.1 | Position 模型新增 `total_funding_paid` 字段 | 0.5h | - | ✅ 已完成 |
| BT-2.2 | PMSBacktestReport 新增 `total_funding_cost` 字段 | 0.5h | BT-2.1 | ✅ 已完成 |
| BT-2.3 | BacktestRequest 新增 `funding_rate_enabled` 字段 | 0.5h | - | ✅ 已完成 |
| BT-2.4 | ConfigEntryRepository 添加默认配置 | 0.5h | - | ✅ 已完成 |
| BT-2.5 | ConfigManager 文档注释更新 | 0.5h | BT-2.4 | ✅ 已完成 |
| BT-2.6 | Backtester 配置读取逻辑 | 1h | BT-2.4 | ✅ 已完成 |
| BT-2.7 | Backtester 资金费用计算方法实现 | 2h | BT-2.1 | ⏳ 进行中 |
| BT-2.8 | Backtester 主循环集成资金费用计算 | 2h | BT-2.7 | ⏳ 进行中 |
| BT-2.9 | PMSBacktestReport 字段填充 | 1h | BT-2.8 | ⏳ 进行中 |
| BT-2.10 | 单元测试（资金费用计算逻辑） | 3h | BT-2.9 | ⏳ 进行中 |
| BT-2.11 | API 接口审查（如需要） | 1h | BT-2.3 | ⏳ 进行中 |
| BT-2.12 | 前端展示审查（如需要） | 1h | BT-2.2 | ⏳ 进行中 |

**总工时估算**: 12 小时

### 6.2 依赖关系

```
BT-2.1 → BT-2.2 → BT-2.7 → BT-2.8 → BT-2.9 → BT-2.10
   ↓        ↓                                    ↓
BT-2.3 → BT-2.6                                  BT-2.11
   ↓                                              ↓
BT-2.4 → BT-2.5                                 BT-2.12
```

### 6.3 里程碑

| 里程碑 | 达成条件 | 预计日期 |
|--------|----------|----------|
| M1: 模型完成 | BT-2.1 ~ BT-2.3 ✅ | 2026-04-07 |
| M2: 配置完成 | BT-2.4 ~ BT-2.6 ✅ | 2026-04-07 |
| M3: 核心逻辑完成 | BT-2.7 ~ BT-2.9 | 2026-04-08 |
| M4: 测试完成 | BT-2.10 ~ BT-2.12 | 2026-04-09 |

---

## 7. 已修改代码审查

### 7.1 ConfigEntryRepository

**文件**: `src/infrastructure/config_entry_repository.py`

**审查结果**: ✅ 通过

**关键变更** (440-452 行):
```python
DEFAULT_BACKTEST_CONFIG = {
    'backtest.slippage_rate': Decimal('0.001'),
    'backtest.fee_rate': Decimal('0.0004'),
    'backtest.initial_balance': Decimal('10000'),
    'backtest.tp_slippage_rate': Decimal('0.0005'),
    'backtest.funding_rate_enabled': True,  # ✅ BT-2 新增
    'backtest.funding_rate': Decimal('0.0001'),  # ✅ BT-2 新增
}
```

**审查意见**:
- ✅ 默认值符合设计规范
- ✅ 配置键命名遵循 `backtest.*` 前缀规范
- ✅ 类型正确（boolean 和 decimal）

### 7.2 ConfigManager

**文件**: `src/application/config_manager.py`

**审查结果**: ✅ 通过

**关键变更** (1363-1364, 1395-1396 行):
```python
# get_backtest_configs 返回文档注释
- funding_rate_enabled: bool (默认 True)
- funding_rate: Decimal (默认 0.0001, 每 8 小时)

# save_backtest_configs 参数文档注释
- funding_rate_enabled (bool)
- funding_rate (Decimal)
```

**审查意见**:
- ✅ 文档注释清晰
- ✅ 与 ConfigEntryRepository 保持一致

### 7.3 Position 模型

**文件**: `src/domain/models.py`

**审查结果**: ✅ 通过

**关键变更** (1078 行):
```python
class Position(FinancialModel):
    total_funding_paid: Decimal = Field(
        default=Decimal('0'),
        description="累计支付的资金费用 (BT-2)"
    )
```

**审查意见**:
- ✅ 字段命名清晰
- ✅ 默认值正确
- ✅ 描述包含 BT-2 任务标识

### 7.4 PMSBacktestReport 模型

**文件**: `src/domain/models.py`

**审查结果**: ✅ 通过

**关键变更** (1257 行):
```python
class PMSBacktestReport(FinancialModel):
    total_funding_cost: Decimal = Field(
        default=Decimal('0'),
        description="总资金费用 (BT-2)"
    )
```

**审查意见**:
- ✅ 字段命名与 Position 保持一致
- ✅ 默认值正确

### 7.5 BacktestRequest 模型

**文件**: `src/domain/models.py`

**审查结果**: ✅ 通过

**关键变更** (待确认位置，应在 630 行后):
```python
class BacktestRequest(BaseModel):
    funding_rate_enabled: Optional[bool] = Field(
        default=None,
        description="是否启用资金费用计算 (default: True, or from KV config)"
    )
```

**审查意见**:
- ✅ 使用 Optional 支持优先级合并逻辑
- ✅ 描述清晰说明默认值来源

### 7.6 Backtester 配置读取

**文件**: `src/application/backtester.py`

**审查结果**: ✅ 通过

**关键变更** (1140-1158 行):
```python
# BT-2: 资金费率配置
funding_rate_enabled = (
    request.funding_rate_enabled
    if request.funding_rate_enabled is not None
    else (kv_configs.get('funding_rate_enabled') if kv_configs else None)
)
if funding_rate_enabled is None:
    funding_rate_enabled = True  # 默认开启
funding_rate = (
    kv_configs.get('funding_rate')
    if kv_configs and kv_configs.get('funding_rate') is not None
    else Decimal('0.0001')
)  # 默认 0.01% 每 8 小时

logger.info(
    f"Running v3 PMS backtest with config: "
    f"slippage={slippage_rate}, fee={fee_rate}, "
    f"initial_balance={initial_balance}, tp_slippage={tp_slippage_rate}, "
    f"funding_enabled={funding_rate_enabled}, funding_rate={funding_rate}"
)
```

**审查意见**:
- ✅ 优先级逻辑正确（request > KV > code defaults）
- ✅ 日志输出包含新配置
- ⚠️ 待完成：资金费用计算逻辑集成

---

## 8. 测试计划

### 8.1 单元测试用例

| 用例 ID | 测试场景 | 预期结果 |
|---------|----------|----------|
| UT-FR-01 | 多头持仓 1h K 线，资金费用计算 | 正费用（支付） |
| UT-FR-02 | 空头持仓 1h K 线，资金费用计算 | 负费用（收取） |
| UT-FR-03 | 资金费率开关关闭 | 费用为 0 |
| UT-FR-04 | 不同时间周期计算 | 15m/1h/4h/1d 计算正确 |
| UT-FR-05 | 配置优先级测试 | request > KV > defaults |

### 8.2 集成测试用例

| 用例 ID | 测试场景 | 预期结果 |
|---------|----------|----------|
| IT-FR-01 | 完整回测流程，包含资金费用 | 报告包含 total_funding_cost |
| IT-FR-02 | 历史数据回测对比（开/关） | 开启时收益略低 |

---

## 9. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 资金费率固定值过于简化 | 中 | 中 | 文档说明为简化模型，未来支持动态费率 |
| 长时间回测累积误差 | 低 | 低 | 简化模型本身不追求精确 |
| 前端展示遗漏 | 低 | 低 | 与前端团队沟通确认 |

---

## 10. 决策记录

### 决策 1: 固定费率 vs 动态费率

**决策**: 采用固定费率 0.01%

**理由**:
- 简化实现，无外部数据依赖
- 长期平均值，保守估计
- 符合回测系统的"保守悲观"原则

### 决策 2: 计算精度

**决策**: 按 K 线数量估算持仓时长

**理由**:
- 无需精确追踪 8 小时结算时点
- 计算开销低
- 长期回测结果趋于准确

### 决策 3: 会计处理

**决策**: 多头支付为正，空头收取为负

**理由**:
- 符合会计惯例（成本为正，收益为负）
- 与手续费处理保持一致

---

## 11. 参考文档

- [滑点配置 KV 化设计](./adr-001-slippage-kv-design.md)（参考）
- [PMS 回测引擎设计](../designs/phase2-matching-engine-contract.md)
- [Binance 资金费率说明](https://www.binance.com/en/support/faq/funding-fees)

---

*本 ADR 由架构设计流程自动生成，后续变更需经架构师审查。*
