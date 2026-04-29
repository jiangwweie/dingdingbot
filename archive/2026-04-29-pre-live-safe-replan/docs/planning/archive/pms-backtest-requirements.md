# PMS 回测需求规格说明

**文档版本**: v1.0  
**创建日期**: 2026-04-01  
**最后更新**: 2026-04-01  
**文档类型**: 需求规格说明书 (SRS)

---

## 一、引言

### 1.1 目的

本文档定义 PMS 回测系统修复与增强的完整需求规格，包括问题分析、功能需求、非功能需求和验收标准。

### 1.2 范围

本需求覆盖以下模块：
- 回测引擎核心逻辑修复
- 订单持久化系统
- 回测报告持久化系统
- 前端展示界面

### 1.3 术语定义

| 术语 | 定义 |
|------|------|
| PMS | Portfolio Management System (投资组合管理系统) |
| MTF | Multi-Timeframe Analysis (多时间周期分析) |
| 未来函数 | 使用未来数据进行决策的逻辑错误 |
| 滑点 | 预期成交价与实际成交价的差异 |
| 止盈 | Take Profit (TP)，预设的获利平仓价位 |

---

## 二、问题分析与需求概述

### 2.1 已确认的 7 个问题分析

| 编号 | 问题名称 | 分析结论 | 需求类型 | 优先级 |
|------|----------|----------|----------|--------|
| P01 | 止盈撮合过于理想 | ✅ 无限价单成交假设 | 功能修复 | P0 |
| P02 | MTF 使用未收盘 K 线 | ✅ 存在未来函数 | 功能修复 | P0 |
| P03 | 同时同向持仓 | ⚠️ 不限制但概率低 | 功能增强 | P2 |
| P04 | 权益金检查 Bug | ⚠️ positions 为空 | 功能修复 | P2 |
| P05 | 订单生命周期追溯 | ❌ 未入库 | 新功能 | P0 |
| P06 | 回测记录列表 | ❌ 未实现 | 新功能 | P0 |
| P07 | 日期选择/时间段 | ⚠️ CCXT 限制 | 功能增强 | P1 |

### 2.2 需求分类

**功能需求**:
- FR-001: 止盈撮合滑点模拟
- FR-002: MTF 数据正确引用
- FR-003: 订单持久化存储
- FR-004: 回测报告持久化
- FR-005: 回测记录列表展示
- FR-006: 订单详情可视化
- FR-007: 时间段分页获取
- FR-008: 回测记录删除

**非功能需求**:
- NFR-001: 性能要求
- NFR-002: 数据一致性
- NFR-003: 用户体验
- NFR-004: 可维护性

---

## 三、功能需求详述

### 3.1 FR-001: 止盈撮合滑点模拟

**需求描述**: 回测中模拟真实交易的滑点影响，止盈订单成交价需考虑滑点

**业务规则**:
1. 默认滑点率：0.05% (5 个基点)
2. LONG 仓位止盈：`effective_price = tp_price * (1 - slippage_rate)`
3. SHORT 仓位止盈：`effective_price = tp_price * (1 + slippage_rate)`
4. 滑点率可配置

**输入**:
- 止盈价格 (take_profit_price): Decimal
- 仓位方向 (direction): Direction (LONG/SHORT)
- 滑点率 (slippage_rate): Decimal, 默认 0.0005

**处理逻辑**:
```python
def check_take_profit_fill(
    kline: KlineData,
    take_profit_price: Decimal,
    direction: Direction,
    slippage_rate: Decimal = Decimal("0.0005"),
) -> bool:
    """检查止盈订单是否应该成交"""
    if direction == Direction.LONG:
        # 多头止盈：价格向下突破
        effective_price = take_profit_price * (1 - slippage_rate)
        return kline.low <= effective_price <= kline.high
    else:
        # 空头止盈：价格向上突破
        effective_price = take_profit_price * (1 + slippage_rate)
        return kline.low <= effective_price <= kline.high
```

**输出**: 
- 成交判断：bool

**验收标准**:
- [ ] 滑点率可通过配置修改
- [ ] LONG/SHORT 方向滑点计算正确
- [ ] 回测收益率因滑点下降 5-15%

---

### 3.2 FR-002: MTF 数据正确引用

**需求描述**: MTF 验证必须使用已确认的更高周期 K 线，避免未来函数

**业务规则**:
1. 当前周期 K 线收盘时，只能使用已收盘的更高周期 K 线
2. 往前偏移量 = 更高周期 K 线的完整周期时长
3. 示例：15m K 线收盘时，应使用 1h 的"上一根"已收盘 K 线

**时间偏移计算**:
```python
TIMEFRAME_OFFSET = {
    ("15m", "1h"): 60 * 60 * 1000,      # 1 小时
    ("1h", "4h"): 4 * 60 * 60 * 1000,   # 4 小时
    ("4h", "1d"): 24 * 60 * 60 * 1000,  # 24 小时
    ("1d", "1w"): 7 * 24 * 60 * 60 * 1000,  # 7 天
}

def get_confirmed_timestamp(kline_timestamp: int, higher_tf: str) -> int:
    """获取已确认的更高周期时间戳"""
    offset_ms = TIMEFRAME_OFFSET.get((kline.timeframe, higher_tf))
    if offset_ms is None:
        offset_ms = self._parse_timeframe(higher_tf) * 60 * 1000
    return kline_timestamp - offset_ms
```

**输入**:
- 当前 K 线时间戳：int (毫秒)
- 更高周期：str (如 "1h", "4h")

**输出**:
- 已确认的时间戳：int (毫秒)

**验收标准**:
- [ ] 信号数量减少 (更严格的 MTF 过滤)
- [ ] 回测结果更保守可靠
- [ ] 无未来函数污染

---

### 3.3 FR-003: 订单持久化存储

**需求描述**: 回测过程中的所有订单必须保存到数据库，支持生命周期追溯

**数据结构** (Order 模型):
```python
@dataclass
class Order:
    id: str                    # 订单 ID (UUID)
    signal_id: str             # 关联信号 ID
    symbol: str                # 交易对
    direction: Direction       # 方向 (LONG/SHORT)
    order_type: OrderType      # 订单类型
    order_role: OrderRole      # 订单角色 (ENTRY/TP1/SL 等)
    price: Optional[Decimal]   # 订单价格
    trigger_price: Optional[Decimal]  # 触发价格
    requested_qty: Decimal     # 请求数量
    filled_qty: Decimal        # 已成交数量
    average_exec_price: Optional[Decimal]  # 平均成交价
    status: OrderStatus        # 订单状态
    created_at: int            # 创建时间戳
    updated_at: int            # 更新时间戳
    filled_at: Optional[int]   # 成交时间戳 (新增)
    parent_order_id: Optional[str]  # 父订单 ID (新增，用于止盈关联)
```

**业务规则**:
1. 订单创建时立即保存
2. 订单状态变更时更新
3. 成交时记录 filled_at
4. 止盈单需关联 parent_order_id

**操作接口**:
```python
class OrderRepository:
    async def save_order(self, order: Order) -> None:
        """保存订单"""
        pass
    
    async def update_order(self, order: Order) -> None:
        """更新订单"""
        pass
    
    async def get_orders_by_signal(self, signal_id: str) -> List[Order]:
        """获取信号关联的所有订单"""
        pass
    
    async def get_order_detail(self, order_id: str) -> Optional[Order]:
        """获取订单详情"""
        pass
```

**验收标准**:
- [ ] 每笔订单可追溯
- [ ] 订单状态变更正确记录
- [ ] 止盈单正确关联父订单

---

### 3.4 FR-004: 回测报告持久化

**需求描述**: 回测完成后生成报告并保存到数据库，支持历史查看和自动调参

**数据结构** (BacktestReport 模型):
```python
@dataclass
class BacktestReport:
    id: str                    # 报告 ID (UUID)
    
    # === 策略关联 (符合 3NF 设计) ===
    strategy_id: str           # 策略模板 ID
    strategy_name: str         # 策略名称 (冗余存储，性能优化)
    strategy_version: str      # 策略版本 (如 "1.0.0")
    
    # === 策略快照 (核心：记录回测时的参数组合，用于自动调参) ===
    strategy_snapshot: dict    # 完整参数快照 JSON
                                 # {"triggers": [...], "filters": [...], "risk_config": {...}}
    parameters_hash: str       # SHA256 参数组合哈希，用于聚类分析
    
    symbol: str                # 交易对
    timeframe: str             # 时间周期
    
    # 回测时间范围
    backtest_start: int        # 回测开始时间戳
    backtest_end: int          # 回测结束时间戳
    created_at: int            # 报告创建时间戳
    
    # 核心指标
    initial_balance: Decimal   # 初始余额
    final_balance: Decimal     # 最终余额
    total_return: Decimal      # 总收益率 (%)
    total_trades: int          # 总交易数
    winning_trades: int        # 盈利交易数
    losing_trades: int         # 亏损交易数
    win_rate: Decimal          # 胜率 (%)
    total_pnl: Decimal         # 总盈亏 (USDT)
    total_fees_paid: Decimal   # 总手续费
    total_slippage_cost: Decimal  # 总滑点成本
    max_drawdown: Decimal      # 最大回撤 (%)
    
    # 详细数据 (JSON)
    positions_summary: str     # 仓位摘要
    monthly_returns: str       # 月度收益
```

**设计说明**:
| 字段 | 用途 | 3NF 合规性 |
|------|------|-----------|
| `strategy_snapshot` | JSON 存储完整参数，自动调参的基础 | ✅ 对扩展开放 |
| `parameters_hash` | 快速查询相同参数组合的回测记录 | ✅ 支持聚类分析 |
| `strategy_name` | 冗余存储，避免 JOIN 查询 | ⚠️ 有意反范式化 (性能优化) |

**验收标准**:
- [ ] 报告完整保存所有指标
- [ ] 支持按策略查询历史报告
- [ ] 支持按参数哈希聚类分析 (自动调参基础)
- [ ] 策略快照正确序列化与反序列化

---

### 3.5 FR-005: 回测记录列表展示

**需求描述**: 前端展示回测历史记录列表，支持筛选和排序

**功能需求**:
1. 表格展示回测记录
2. 支持按策略/币种/时间范围筛选
3. 支持按收益率/胜率/创建时间排序
4. 支持分页

**API 接口**:
```typescript
// GET /api/v3/backtest/reports
interface ListBacktestReportsRequest {
  strategyId?: string;
  symbol?: string;
  startDate?: number;
  endDate?: number;
  page?: number;
  pageSize?: number;
  sortBy?: 'total_return' | 'win_rate' | 'created_at';
  sortOrder?: 'asc' | 'desc';
}

interface ListBacktestReportsResponse {
  reports: BacktestReportSummary[];
  total: number;
  page: number;
  pageSize: number;
}
```

**UI 组件**:
- 回测列表表格
- 筛选条件表单
- 分页器

**验收标准**:
- [ ] 列表正确展示回测记录
- [ ] 筛选功能正常工作
- [ ] 排序功能正常工作
- [ ] 分页功能正常工作

---

### 3.6 FR-006: 订单详情与 K 线图渲染

**需求描述**: 前端展示订单详情，并在 K 线图上标注订单位置

**功能需求**:
1. 订单详情展示
2. K 线图标注 (入场点/出场点/止盈点)
3. 订单位置可视化

**API 接口**:
```typescript
// GET /api/v3/backtest/reports/{reportId}/orders/{orderId}
interface OrderDetailResponse {
  order: Order;
  signal?: Signal;
  position?: Position;
  klines: KlineData[];  // 订单相关 K 线
}
```

**UI 组件**:
- 订单详情抽屉
- K 线图 (带标注)
- 订单位置标记

**验收标准**:
- [ ] 订单详情完整展示
- [ ] K 线图正确标注订单位置
- [ ] 订单位置可视化清晰

---

### 3.7 FR-007: 时间段分页获取

**需求描述**: 突破 CCXT 单次获取 K 线数量限制，支持分页获取

**业务规则**:
1. CCXT 单次最大获取 1000 根 K 线
2. 自动分页获取完整时间范围数据
3. 合并所有分页数据

**接口设计**:
```python
async def fetch_historical_ohlcv_paginated(
    self,
    symbol: str,
    timeframe: str,
    start_time: int,
    end_time: int,
    limit: int = 1000,
) -> List[KlineData]:
    """
    分页获取历史 K 线
    
    Args:
        symbol: 交易对
        timeframe: 时间周期
        start_time: 开始时间戳 (毫秒)
        end_time: 结束时间戳 (毫秒)
        limit: 单次最大获取数量
    
    Returns:
        完整的 K 线列表
    """
    all_klines = []
    current_start = start_time
    
    while current_start < end_time:
        klines = await self._gateway.fetch_historical_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            since=current_start,
            limit=limit,
        )
        if not klines:
            break
        all_klines.extend(klines)
        current_start = klines[-1].timestamp + 1
    
    return all_klines
```

**验收标准**:
- [ ] 可获取任意时间范围数据
- [ ] 数据完整无遗漏
- [ ] 分页逻辑正确

---

### 3.8 FR-008: 回测记录删除

**需求描述**: 支持删除单条或批量删除回测记录

**功能需求**:
1. 单条删除
2. 批量删除 (支持多选)
3. 删除确认

**API 接口**:
```typescript
// DELETE /api/v3/backtest/reports/{reportId}
interface DeleteReportResponse {
  success: boolean;
}

// POST /api/v3/backtest/reports/delete-batch
interface BatchDeleteRequest {
  reportIds: string[];
}

interface BatchDeleteResponse {
  success: boolean;
  deletedCount: number;
}
```

**验收标准**:
- [ ] 单条删除正常工作
- [ ] 批量删除正常工作
- [ ] 删除前有确认提示

---

## 四、非功能需求

### 4.1 NFR-001: 性能要求

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 回测执行时间 | <30s (1 年 15m 数据) | 端到端计时 |
| 订单保存延迟 | <10ms/单 | 数据库写入计时 |
| 列表加载时间 | <1s (100 条记录) | 前端加载计时 |
| 详情加载时间 | <500ms | 前端加载计时 |

### 4.2 NFR-002: 数据一致性

| 要求 | 说明 |
|------|------|
| 事务一致性 | 订单保存使用数据库事务 |
| 外键约束 | orders.signal_id 外键关联 signals.id |
| 数据完整性 | 删除报告时级联删除关联订单 |

### 4.3 NFR-003: 用户体验

| 要求 | 说明 |
|------|------|
| 响应式加载 | 加载状态明确提示 |
| 错误处理 | 错误信息清晰友好 |
| 操作确认 | 删除等危险操作需确认 |

### 4.4 NFR-004: 可维护性

| 要求 | 说明 |
|------|------|
| 代码注释 | 关键逻辑有详细注释 |
| 单元测试 | 核心逻辑单元测试覆盖率>90% |
| 日志记录 | 关键操作有日志记录 |

---

## 五、数据库设计

### 5.1 orders 表

```sql
CREATE TABLE orders (
    id VARCHAR(64) PRIMARY KEY,
    signal_id VARCHAR(64) NOT NULL,
    exchange_order_id VARCHAR(64),
    symbol VARCHAR(32) NOT NULL,
    direction VARCHAR(16) NOT NULL,
    order_type VARCHAR(32) NOT NULL,
    order_role VARCHAR(16) NOT NULL,
    price DECIMAL(32, 18),
    trigger_price DECIMAL(32, 18),
    requested_qty DECIMAL(32, 18) NOT NULL,
    filled_qty DECIMAL(32, 18) NOT NULL DEFAULT '0',
    average_exec_price DECIMAL(32, 18),
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    exit_reason VARCHAR(64),
    filled_at BIGINT,
    parent_order_id VARCHAR(64),
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    
    CONSTRAINT fk_orders_signal FOREIGN KEY (signal_id) REFERENCES signals(id) ON DELETE CASCADE,
    CONSTRAINT check_orders_direction CHECK (direction IN ('LONG', 'SHORT')),
    CONSTRAINT check_orders_status CHECK (status IN ('PENDING', 'OPEN', 'PARTIALLY_FILLED', 'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED')),
    CONSTRAINT check_orders_order_type CHECK (order_type IN ('MARKET', 'LIMIT', 'STOP_MARKET', 'STOP_LIMIT', 'TRAILING_STOP')),
    CONSTRAINT check_orders_order_role CHECK (order_role IN ('ENTRY', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5', 'SL'))
);

CREATE INDEX idx_orders_signal_id ON orders(signal_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_symbol ON orders(symbol);
```

### 5.2 backtest_reports 表

```sql
CREATE TABLE backtest_reports (
    id VARCHAR(64) PRIMARY KEY,
    strategy_id VARCHAR(64) NOT NULL,
    strategy_name VARCHAR(128) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    timeframe VARCHAR(16) NOT NULL,
    backtest_start BIGINT NOT NULL,
    backtest_end BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    
    -- 核心指标
    initial_balance DECIMAL(32, 18) NOT NULL,
    final_balance DECIMAL(32, 18) NOT NULL,
    total_return DECIMAL(10, 4) NOT NULL,
    total_trades INTEGER NOT NULL,
    winning_trades INTEGER NOT NULL,
    losing_trades INTEGER NOT NULL,
    win_rate DECIMAL(10, 4) NOT NULL,
    total_pnl DECIMAL(32, 18) NOT NULL,
    total_fees_paid DECIMAL(32, 18) NOT NULL,
    total_slippage_cost DECIMAL(32, 18) NOT NULL,
    max_drawdown DECIMAL(10, 4) NOT NULL,
    
    -- 详细数据 (JSON 存储)
    positions_summary TEXT,
    monthly_returns TEXT,
    
    CONSTRAINT fk_backtest_reports_strategy FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE
);

CREATE INDEX idx_backtest_reports_strategy_id ON backtest_reports(strategy_id);
CREATE INDEX idx_backtest_reports_symbol ON backtest_reports(symbol);
CREATE INDEX idx_backtest_reports_created_at ON backtest_reports(created_at);
```

---

## 六、API 设计

### 6.1 回测报告 API

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/api/v3/backtest/reports` | GET | 获取回测报告列表 | 是 |
| `/api/v3/backtest/reports/{id}` | GET | 获取回测报告详情 | 是 |
| `/api/v3/backtest/reports/{id}` | DELETE | 删除回测报告 | 是 |
| `/api/v3/backtest/reports/delete-batch` | POST | 批量删除回测报告 | 是 |
| `/api/v3/backtest/run` | POST | 运行回测 | 是 |

### 6.2 订单详情 API

| 端点 | 方法 | 描述 | 认证 |
|------|------|------|------|
| `/api/v3/backtest/reports/{reportId}/orders` | GET | 获取报告关联订单列表 | 是 |
| `/api/v3/backtest/reports/{reportId}/orders/{orderId}` | GET | 获取订单详情 (含 K 线) | 是 |

---

## 七、验收标准总览

### 7.1 功能验收

| 功能 | 验收标准 | 状态 |
|------|----------|------|
| 止盈滑点 | 回测收益率下降 5-15% | ☐ |
| MTF 修复 | 信号数量减少，无未来函数 | ☐ |
| 订单入库 | 每笔订单可追溯 | ☐ |
| 回测报告 | 报告可持久化查看 | ☐ |
| 列表页面 | 展示历史回测记录 | ☐ |
| 详情页面 | 展示订单详情与 K 线 | ☐ |
| 分页获取 | 可获取任意时间范围数据 | ☐ |
| 删除功能 | 单条/批量删除正常 | ☐ |

### 7.2 测试验收

| 测试类型 | 目标 | 状态 |
|----------|------|------|
| 单元测试 | 覆盖率>90% | ☐ |
| 集成测试 | 核心流程 100% 通过 | ☐ |
| E2E 测试 | 端到端流程通过 | ☐ |

### 7.3 性能验收

| 指标 | 目标值 | 状态 |
|------|--------|------|
| 回测执行时间 | <30s | ☐ |
| 订单保存延迟 | <10ms/单 | ☐ |
| 列表加载时间 | <1s | ☐ |

---

## 八、附录

### 8.1 参考文档

- [PMS 回测修复计划](pms-backtest-fix-plan.md)
- [OrderORM 定义](../../src/infrastructure/v3_orm.py)
- [PMSBacktestReport 定义](../../src/domain/models.py)

### 8.2 修订历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| v1.0 | 2026-04-01 | AI Builder | 初始版本 |

---

*文档创建时间：2026-04-01*
