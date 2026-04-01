# PMS 回测问题修复计划

**文档版本**: v1.0  
**创建日期**: 2026-04-01  
**最后更新**: 2026-04-01  
**优先级**: P0 (紧急)

---

## 一、执行摘要

### 1.1 背景

PMS 回测系统在深度分析中发现了 7 个核心问题，涉及止盈撮合、MTF 数据使用、订单入库等关键环节。本计划汇总分析结果并提供详细的修复方案。

### 1.2 修复范围

| 问题类别 | 问题数 | 修复状态 |
|----------|--------|----------|
| P0 级 (严重) | 4 | 待修复 |
| P1 级 (中等) | 1 | 待修复 |
| P2 级 (优化) | 2 | 待修复 |
| **总计** | **7** | - |

### 1.3 预计工时

| 阶段 | 工时 (小时) | 交付物 |
|------|-------------|--------|
| P0 级修复 | 8 小时 | 核心问题修复 + 测试 |
| P1 级修复 | 2 小时 | CCXT 分页获取 |
| P2 级修复 | 3 小时 | 代码优化 |
| **总计** | **13 小时** | - |

---

## 二、问题分析汇总表

### 2.1 问题 1: 止盈撮合过于理想 (P0)

**问题描述**: 回测中假设限价单可以无限价成交，未考虑滑点影响

**分析结论**: ✅ 确认问题 - 无限价单成交假设导致回测结果虚高

**修复方案**:
```python
# 修复前 - 理想化撮合
if kline.low <= take_profit_price <= kline.high:
    order.filled = True

# 修复后 - 添加 0.05% 滑点
SLIPPAGE_RATE = Decimal("0.0005")  # 0.05%
effective_tp_price = take_profit_price * (1 - SLIPPAGE_RATE)  # LONG 仓位
if kline.low <= effective_tp_price <= kline.high:
    order.filled = True
```

**影响范围**: 
- `src/application/backtester.py` - 止盈撮合逻辑
- 回测结果准确性

**验收标准**:
- [ ] 添加滑点配置参数
- [ ] 回测收益率下降 5-15% (更接近实盘)
- [ ] 测试用例验证滑点计算正确

---

### 2.2 问题 2: MTF 使用未收盘 K 线 (P0)

**问题描述**: MTF 验证使用当前正在形成的 K 线，存在未来函数

**分析结论**: ✅ 确认问题 - 存在未来函数，回测结果不可靠

**修复方案**:
```python
# 修复前 - 使用当前 K 线
higher_tf_trends = self._get_closest_higher_tf_trends(kline.timestamp, higher_tf_data)

# 修复后 - 往前偏移 1 根 K 线
# MTF 验证应使用已确认的更高周期 K 线
# 当前 15m K 线收盘时，应使用 1h 的"上一根"已收盘 K 线
confirmed_timestamp = kline.timestamp - self._get_timeframe_duration(higher_tf)
higher_tf_trends = self._get_closest_higher_tf_trends(confirmed_timestamp, higher_tf_data)
```

**影响范围**:
- `src/application/backtester.py` - MTF 验证逻辑
- 所有使用 MTF 过滤的策略

**验收标准**:
- [ ] 信号数量减少 (过滤更严格)
- [ ] 回测结果更保守
- [ ] 无未来函数污染

---

### 2.3 问题 3: 同时同向持仓 (P2)

**问题描述**: 回测未限制同一币种同时存在多个同向仓位

**分析结论**: ⚠️ 不限制但概率低 - 策略逻辑自然避免

**修复方案**:
```python
# 新增检查 - 开仓前验证
def _check_position_conflict(self, symbol: str, direction: Direction) -> bool:
    """检查是否存在同向持仓冲突"""
    for position in self.active_positions:
        if position.symbol == symbol and position.direction == direction:
            return False  # 存在同向持仓，拒绝开仓
    return True
```

**优先级**: P2 (低) - 策略逻辑已自然避免，修复为防御性编程

---

### 2.4 问题 4: 权益金检查 Bug (P2)

**问题描述**: 开仓前权益金检查在 positions 为空时报错

**分析结论**: ⚠️ positions 为空时边界条件处理不当

**修复方案**:
```python
# 修复前 - 可能报空指针
current_equity = account.balance + sum(p.unrealized_pnl for p in positions)

# 修复后 - 安全处理
current_equity = account.balance
if positions:
    current_equity += sum(p.unrealized_pnl for p in positions)
```

---

### 2.5 问题 5: 订单生命周期追溯 (P0)

**问题描述**: 回测订单未入库，无法追溯订单生命周期

**分析结论**: ❌ 未入库 - 新建 `orders` 表存储

**需求澄清**:
- **不改动现有表** - 保持现有表结构稳定
- **不复用现有表** - 不强行复用 `signals/signal_take_profits` 表
- **新建独立 `orders` 表** - 完整记录订单生命周期

**表结构** (已存在 `src/infrastructure/v3_orm.py` L396-514):
```python
class OrderORM(Base):
    __tablename__ = "orders"
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(64), ForeignKey("signals.id"))
    exchange_order_id: Mapped[Optional[str]] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(16))
    order_type: Mapped[str] = mapped_column(String(32))
    order_role: Mapped[str] = mapped_column(String(16))  # ENTRY/TP1/TP2/SL
    price: Mapped[Optional[Decimal]] = mapped_column(DecimalField(32))
    trigger_price: Mapped[Optional[Decimal]] = mapped_column(DecimalField(32))
    requested_qty: Mapped[Decimal] = mapped_column(DecimalField(32))
    filled_qty: Mapped[Decimal] = mapped_column(DecimalField(32), default=Decimal('0'))
    average_exec_price: Mapped[Optional[Decimal]] = mapped_column(DecimalField(32))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    exit_reason: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[int] = mapped_column(Integer)
    
    # 需补充字段
    filled_at: Mapped[Optional[int]] = mapped_column(Integer)  # 成交时间戳
    parent_order_id: Mapped[Optional[str]] = mapped_column(String(64))  # 父订单 ID (止盈关联入场单)
```

**迁移文件**: `migrations/versions/2026-05-02-002_create_orders_positions_tables.py` (已存在)

---

### 2.6 问题 6: 回测记录列表 (P0)

**问题描述**: 回测报告未持久化，无法查看历史记录

**分析结论**: ❌ 未实现 - 新建 `backtest_reports` 表

**表结构设计**:
```python
class BacktestReportORM(Base):
    __tablename__ = "backtest_reports"
    
    # === 主键 ===
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # === 策略关联 ===
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0.0")
    
    # === 策略快照 (符合 3NF 设计：记录回测时的完整参数组合) ===
    # 用途 1: 自动调参 - 通过 parameters_hash 聚类分析最优参数组合
    # 用途 2: 历史追溯 - 回测报告与当时使用的参数绑定，不受策略后续修改影响
    # 用途 3: 参数空间搜索 - 快速筛选相同/相似参数组合的回测结果
    strategy_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON 格式：{"triggers": [...], "filters": [...], "risk_config": {...}, "mtf_config": {...}}
    
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # SHA256 哈希值，用于快速去重和聚类分析
    
    # === 基础信息 ===
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    
    # === 时间范围 ===
    backtest_start: Mapped[int] = mapped_column(Integer)  # 回测开始时间戳
    backtest_end: Mapped[int] = mapped_column(Integer)    # 回测结束时间戳
    created_at: Mapped[int] = mapped_column(Integer)      # 报告创建时间戳
    
    # === 核心指标 ===
    initial_balance: Mapped[Decimal] = mapped_column(DecimalField(32))
    final_balance: Mapped[Decimal] = mapped_column(DecimalField(32))
    total_return: Mapped[Decimal] = mapped_column(DecimalField(32))  # 总收益率 %
    total_trades: Mapped[int] = mapped_column(Integer)
    winning_trades: Mapped[int] = mapped_column(Integer)
    losing_trades: Mapped[int] = mapped_column(Integer)
    win_rate: Mapped[Decimal] = mapped_column(DecimalField(32))  # 胜率 %
    total_pnl: Mapped[Decimal] = mapped_column(DecimalField(32))
    total_fees_paid: Mapped[Decimal] = mapped_column(DecimalField(32), default=Decimal('0'))
    total_slippage_cost: Mapped[Decimal] = mapped_column(DecimalField(32), default=Decimal('0'))
    max_drawdown: Mapped[Decimal] = mapped_column(DecimalField(32))  # 最大回撤 %
    
    # === 详细数据 (JSON 存储，性能优化) ===
    positions_summary: Mapped[Optional[str]] = mapped_column(Text)  # 仓位摘要 JSON
    monthly_returns: Mapped[Optional[str]] = mapped_column(Text)   # 月度收益 JSON
    
    # === 索引 ===
    __table_args__ = (
        Index("idx_backtest_reports_strategy_id", "strategy_id"),
        Index("idx_backtest_reports_symbol", "symbol"),
        Index("idx_backtest_reports_parameters_hash", "parameters_hash"),
        Index("idx_backtest_reports_created_at", "created_at"),
    )
```

---

### 2.7 问题 7: 日期选择/时间段 (P1)

**问题描述**: CCXT 获取历史 K 线有限制，无法一次性获取大量数据

**分析结论**: ⚠️ CCXT 限制 - 需分页获取

**修复方案**:
```python
async def fetch_historical_ohlcv_paginated(
    self,
    symbol: str,
    timeframe: str,
    start_time: int,
    end_time: int,
    limit: int = 1000,  # CCXT 单次最大
) -> List[KlineData]:
    """分页获取历史 K 线"""
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
        # 下一页的起始时间 = 最后一根 K 线时间 + 1ms
        current_start = klines[-1].timestamp + 1
    
    return all_klines
```

---

## 三、技术方案设计

### 3.1 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ 回测列表页面 │  │ 回测详情页面 │  │ 订单详情与 K 线图    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                         API Layer                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │GET /backtest│  │GET /backtest│  │  POST /backtest/run │  │
│  │             │  │/{id}        │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Application Layer                       │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                   Backtester                            ││
│  │  - 修复 MTF 未来函数                                      ││
│  │  - 添加止盈滑点                                          ││
│  │  - 保存订单到 orders 表                                   ││
│  │  - 保存回测报告到 backtest_reports 表                     ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Infrastructure Layer                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ OrderORM    │  │ BacktestRe- │  │ SignalORM           │  │
│  │ (orders 表)  │  │ portORM     │  │ (signals 表)         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 订单保存流程

```
信号触发 → 创建订单 → 保存到 DB → 模拟撮合 → 更新订单状态
   │                                            │
   │                                            ▼
   │                                    成交 → filled_at = now
   │                                            │
   │                                            ▼
   │                                    创建止盈单 (TP1/TP2)
   │                                            │
   │                                            ▼
   │                                    parent_order_id = 入场单 ID
   │
   ▼
回测结束 → 汇总统计 → 保存 backtest_reports
```

### 3.3 回测报告保存流程

```
回测执行中:
1. 每个订单创建/更新时 → 保存到 orders 表
2. 每个仓位开仓/平仓时 → 保存到 positions 表

回测结束后:
1. 统计所有已平仓仓位 → 计算总收益/胜率/最大回撤
2. 生成 PMSBacktestReport 对象
3. 序列化并保存到 backtest_reports 表
4. 返回报告 ID 给前端
```

---

## 四、任务分解与优先级

### 4.1 任务清单

| ID | 任务名称 | 优先级 | 预计工时 | 依赖 | 状态 |
|----|----------|--------|----------|------|------|
| T1 | 修复 MTF 未来函数 | P0 | 1h | 无 | 待开始 |
| T2 | 修复止盈撮合 (添加滑点) | P0 | 1h | 无 | 待开始 |
| T3 | 创建 orders 表 Alembic 迁移 | P0 | 0.5h | 无 | 待开始 |
| T4 | 实现订单保存逻辑 | P0 | 2h | T3 | 待开始 |
| T5 | 创建 backtest_reports 表 | P0 | 1h | 无 | 待开始 |
| T6 | 实现回测报告保存 | P0 | 2h | T5 | 待开始 |
| T7 | 回测记录列表页面 | P0 | 3h | T6 | 待开始 |
| T8 | 订单详情与 K 线图渲染 | P0 | 3h | T4 | 待开始 |
| T9 | 时间段分页获取 (CCXT) | P1 | 2h | 无 | 待开始 |
| T10 | 删除功能 (单条/批量) | P1 | 1h | T7 | 待开始 |
| T11 | 同时同向持仓限制 | P2 | 1h | 无 | 待开始 |
| T12 | 权益金检查修复 | P2 | 1h | 无 | 待开始 |

### 4.2 任务依赖图

```
          ┌──────┐
          │  T3  │
          │  T5  │
          └──┬─┬─┘
             │ │
          ┌──▼─▼──┐
          │  T4   │
          │  T6   │
          └───┬───┘
              │
          ┌───▼───┐
          │  T7   │
          └───┬───┘
              │
          ┌───▼───┐     ┌──────┐
          │  T8   │     │  T9  │
          └───────┘     └──┬───┘
                           │
                      ┌────▼────┐
                      │   T10   │
                      └─────────┘
```

### 4.3 执行顺序

**阶段 1: P0 级核心修复 (8 小时)**
1. T1 - 修复 MTF 未来函数 (1h)
2. T2 - 修复止盈撮合 (1h)
3. T3 - 创建 orders 表迁移 (0.5h)
4. T4 - 实现订单保存逻辑 (2h)
5. T5 - 创建 backtest_reports 表 (1h)
6. T6 - 实现回测报告保存 (2h)

**阶段 2: 前端展示 (6 小时)**
7. T7 - 回测记录列表页面 (3h)
8. T8 - 订单详情与 K 线图 (3h)

**阶段 3: P1 级改进 (3 小时)**
9. T9 - 时间段分页获取 (2h)
10. T10 - 删除功能 (1h)

**阶段 4: P2 级优化 (2 小时)**
11. T11 - 同时同向持仓限制 (1h)
12. T12 - 权益金检查修复 (1h)

---

## 五、验收标准

### 5.1 功能验收

| 功能 | 验收标准 | 验证方法 |
|------|----------|----------|
| MTF 修复 | 回测信号数量减少，无未来函数 | 对比修复前后信号数 |
| 止盈滑点 | 回测收益率下降 5-15% | 对比修复前后收益率 |
| 订单入库 | 每笔订单可追溯 | 查询 orders 表 |
| 回测报告 | 报告可持久化查看 | 查询 backtest_reports 表 |
| 列表页面 | 展示历史回测记录 | 前端访问列表页 |
| 详情页面 | 展示订单详情与 K 线 | 前端点击查看详情 |

### 5.2 测试验收

| 测试类型 | 目标覆盖率 | 关键测试用例 |
|----------|------------|--------------|
| 单元测试 | 90%+ | 滑点计算、MTF 偏移、订单保存 |
| 集成测试 | 100% | 完整回测流程 |
| E2E 测试 | 核心流程 | 回测执行 → 保存 → 查看 |

### 5.3 性能验收

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 回测执行时间 | <30s (1 年数据) | 计时器 |
| 订单保存延迟 | <10ms/单 | 数据库写入计时 |
| 列表加载时间 | <1s (100 条) | 前端性能测试 |

---

## 六、风险评估

### 6.1 技术风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 回测结果大幅变化 | 高 | 中 | 提前告知用户，提供对比工具 |
| 数据库性能瓶颈 | 中 | 中 | 添加索引，批量写入 |
| 前端兼容性问题 | 低 | 低 | 充分测试主流浏览器 |

### 6.2 进度风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 任务复杂度超出预期 | 中 | 中 | 分解更细，每日检查 |
| 依赖问题阻塞 | 低 | 中 | 提前验证依赖 |

---

## 七、Git 提交计划

### 7.1 提交历史

```
# 阶段 1: P0 修复
feat(backtest): 修复 MTF 未来函数 - 往前偏移 1 根 K 线
feat(backtest): 添加止盈撮合滑点 - 0.05% 滑点率
migrations: 创建 orders 表 Alembic 迁移
feat(backtest): 实现订单保存逻辑 - 回测中调用
migrations: 创建 backtest_reports 表
feat(backtest): 实现回测报告保存 - 持久化统计

# 阶段 2: 前端展示
feat(ui): 回测记录列表页面 - 表格 + 筛选
feat(ui): 订单详情与 K 线图渲染 - 可视化展示

# 阶段 3: P1 改进
feat(backtest): CCXT 时间段分页获取 - 突破限制
feat(ui): 回测记录删除功能 - 单条/批量

# 阶段 4: P2 优化
fix(backtest): 同时同向持仓限制 - 防御性检查
fix(backtest): 权益金检查修复 - 空 positions 处理
```

---

## 八、参考文档

- [P0 级审查问题修复报告](../code-review/p0-fix-report-2026-04-01.md)
- [P1/P2 问题修复总结](../code-review/p1-p2-fix-summary-2026-04-01.md)
- [OrderORM 定义](../../src/infrastructure/v3_orm.py)
- [BacktestRequest 模型](../../src/domain/models.py)
- [PMSBacktestReport 模型](../../src/domain/models.py)

---

*文档创建时间：2026-04-01*
