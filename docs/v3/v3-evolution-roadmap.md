# 盯盘狗系统 v3.0 演进路线图

**文档版本**: 1.0
**创建日期**: 2026-03-30
**状态**: 已批准（技术定调确认）
**最终目标**: 实盘自动化执行能力

---

## 一、演进步骤总览

根据用户 D1 决策：**先完成 P0 止盈追踪逻辑，再启动 v3 迁移**

```
【当前阶段】                    【v3 迁移阶段】
P0: 止盈追踪逻辑 ─────────► Phase 0: v3 准备
     (2026-04)                   (2026-05)
                                  │
                                  ▼
                          Phase 1: 模型筑基 (2 周)
                                  │
                                  ▼
                          Phase 2: 撮合引擎 (3 周)
                                  │
                                  ▼
                          Phase 3: 风控状态机 (2 周)
                                  │
                                  ▼
                          Phase 4: 订单编排 (2 周)
                                  │
                                  ▼
                          Phase 5: 实盘集成 (3 周)
                                  │
                                  ▼
                          Phase 6: 前端适配 (2 周)
```

**总工期**: 约 18 周 (4.5 个月)
- P0 止盈追踪：4 周
- v3 迁移：14 周

---

## 二、架构评审技术定调（已确认）

### 2.1 SignalToOrderAdapter 设计模式

**技术定调**: 极其惊艳，完美遵循开闭原则（OCP）

```
┌─────────────────────────────────────────────────────────────┐
│                    适配器模式架构                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────┐      ┌──────────────────────────────┐ │
│  │  StrategyEngine │ ──►  │      SignalResult (v2.0)     │ │
│  │  (策略引擎)      │      │  (通知/前端展示，无需修改)    │ │
│  └─────────────────┘      └──────────────┬───────────────┘ │
│                                          │                   │
│                                          ▼                   │
│                                 ┌─────────────────┐         │
│                                 │ SignalToOrder   │         │
│                                 │ Adapter         │         │
│                                 │ (适配器层)       │         │
│                                 └────────┬────────┘         │
│                                          │                   │
│                    ┌─────────────────────┼───────────────┐  │
│                    ▼                     ▼               ▼  │
│           ┌─────────────┐      ┌─────────────┐  ┌─────────┐│
│           │   Signal    │      │    Order    │  │Position ││
│           │  (v3.0 意图) │      │  (v3.0 执行) │  │(v3.0 状态)│
│           └─────────────┘      └─────────────┘  └─────────┘│
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**核心优势**:
- 上层策略引擎**零修改**
- 底层撮合逻辑可**独立重构**
- v2.0 通知/前端**向后兼容**

---

### 2.2 Direction 枚举迁移策略

**技术定调**: 方案 A（数据库迁移）+ Alembic 版本控制

**迁移脚本设计**:
```python
# migrations/versions/001_unify_direction_enum.py
"""统一 Direction 枚举为大写

Revision ID: 001
Create Date: 2026-05-01

"""
from alembic import op

def upgrade():
    # .signals 表
    op.execute("UPDATE signals SET direction = UPPER(direction) WHERE direction IN ('long', 'short')")

    # .signal_attempts 表
    op.execute("UPDATE signal_attempts SET direction = UPPER(direction) WHERE direction IN ('long', 'short')")

    # 添加检查约束 (防止未来出现小写)
    op.execute("ALTER TABLE signals ADD CONSTRAINT check_direction CHECK (direction IN ('LONG', 'SHORT'))")

def downgrade():
    op.execute("UPDATE signals SET direction = LOWER(direction)")
    op.execute("UPDATE signal_attempts SET direction = LOWER(direction)")
```

**验证清单**:
- [ ] 本地开发环境迁移测试
- [ ] 测试服迁移验证
- [ ] 生产服迁移演练（可回滚）
- [ ] 回滚脚本测试

---

### 2.3 并发安全设计（实盘生死线）

**技术定调**: 内存锁 + 数据库排他锁双层保护

```python
# PositionManager.reduce_position() 伪代码

async def reduce_position(
    self,
    position_id: str,
    exit_order: Order,
) -> Decimal:
    """
    减仓处理 (TP1 成交或 SL 成交)

    并发保护:
    1. Asyncio Lock - 单进程内协程同步
    2. SELECT FOR UPDATE - 数据库行级排他锁
    """
    # ===== 第一层：Asyncio Lock (进程内) =====
    async with self._position_locks[position_id]:

        # ===== 第二层：数据库排他锁 (跨进程) =====
        async with self._db.begin():
            # SQLite: BEGIN EXCLUSIVE
            # PostgreSQL: SELECT ... FOR UPDATE
            position = await self._fetch_position_locked(position_id)

            if position is None:
                raise ValueError(f"Position {position_id} not found")

            # 临界区：仓位状态修改
            if exit_order.direction == Direction.LONG:
                gross_pnl = (exit_order.average_exec_price - position.entry_price) * exit_order.filled_qty
            else:
                gross_pnl = (position.entry_price - exit_order.average_exec_price) * exit_order.filled_qty

            net_pnl = gross_pnl - exit_order.fee_paid

            # 原子更新
            position.current_qty -= exit_order.filled_qty
            position.realized_pnl += net_pnl
            position.total_fees_paid += exit_order.fee_paid

            if position.current_qty <= Decimal("0"):
                position.is_closed = True
                position.closed_at = int(time.time() * 1000)

            await self._session.merge(position)

            # 账户同步
            account = await self._fetch_account_locked(position.signal_id)
            account.total_balance += net_pnl
            await self._session.merge(account)

            return net_pnl
```

**并发场景测试**:
```python
async def test_concurrent_tp1_sl():
    """
    测试场景：TP1 和 SL 同时触发（极端行情）
    预期结果：只有一个订单能成功减仓
    """
    # 模拟两个协程同时调用 reduce_position
    task1 = asyncio.create_task(manager.reduce_position(pos_id, tp1_order))
    task2 = asyncio.create_task(manager.reduce_position(pos_id, sl_order))

    results = await asyncio.gather(task1, task2, return_exceptions=True)

    # 验证：只有一个成功，另一个抛出锁定异常
    assert sum(1 for r in results if not isinstance(r, Exception)) == 1
```

---

## 三、P0 阶段：止盈追踪逻辑（2026-04）

### 3.1 任务分解

| 编号 | 任务 | 预计工时 | 依赖 | 状态 |
|------|------|----------|------|------|
| P0-1 | 设计实时价格监控架构 | 4h | 无 | ⏳ 待启动 |
| P0-2 | 实现止盈状态追踪器 | 8h | P0-1 | ⏳ |
| P0-3 | 集成 WebSocket 价格推送 | 8h | P0-2 | ⏳ |
| P0-4 | 实现多级别止盈状态机 | 12h | P0-3 | ⏳ |
| P0-5 | 编写端到端测试 | 8h | P0-4 | ⏳ |
| P0-6 | 实盘模拟验证 | 8h | P0-5 | ⏳ |

**总计**: 48 小时（约 6 个工作日）

### 3.2 技术设计

```python
# src/application/take_profit_tracker.py

class TakeProfitTracker:
    """
    多级别止盈追踪器

    职责:
    1. 监听 WebSocket 实时价格推送
    2. 检查每个止盈级别是否触发
    3. 更新信号状态 (WON/LOST)
    4. 通知推送
    """

    def __init__(
        self,
        exchange_gateway: ExchangeGateway,
        signal_repository: SignalRepository,
        notifier: NotificationService,
    ):
        self._gateway = exchange_gateway
        self._repository = signal_repository
        self._notifier = notifier

        # 活跃止盈追踪列表
        self._tracking_positions: Dict[str, PositionTakeProfit] = {}

    async def start_tracking(self, signal_id: str, take_profit_levels: List[TpLevel]):
        """开始追踪信号的止盈级别"""
        pass

    async def check_price_update(self, symbol: str, price: Decimal):
        """价格更新时检查是否触发止盈"""
        pass
```

### 3.3 与 v3.0 的关系

**P0 阶段设计原则**: 为 v3.0 迁移做铺垫

| P0 模块 | v3.0 对应 | 迁移策略 |
|---------|----------|---------|
| `TakeProfitTracker` | `DynamicRiskManager` | P0 逻辑保留，v3.0 重构为状态机 |
| `PositionTakeProfit` | `Position` + `Order_TP1` | P0 为过渡设计，v3.0 完全替换 |
| WebSocket 价格监听 | `ExchangeGateway.watch_orders` | P0 代码可复用 |

---

## 四、Phase 0: v3 迁移准备（2026-05 第 1 周）

### 4.1 任务清单

| 任务 | 说明 | 交付物 |
|------|------|--------|
| 技术栈调研 | Alembic + SQLAlchemy async | 技术选型报告 |
| 数据库 Schema 设计 | orders/positions/accounts 表 | DDL 脚本 |
| 迁移脚本编写 | Direction 枚举统一 | `001_unify_direction_enum.py` |
| 开发环境搭建 | 本地 SQLite + 测试 PostgreSQL | Docker Compose |

### 4.2 技术选型

| 技术 | 选型 | 理由 |
|------|------|------|
| ORM | SQLAlchemy 2.0 async | 异步支持 + Alembic 集成 |
| 迁移工具 | Alembic | 行业标准，可回滚 |
| 数据库 | SQLite (开发) / PostgreSQL (生产) | 轻量 vs 高并发 |

---

## 五、Phase 1-6: v3 核心迁移（2026-05 至 2026-08）

### 5.1 阶段总览

| 阶段 | 名称 | 工期 | 开始日期 | 结束日期 | 里程碑 |
|------|------|------|----------|----------|--------|
| Phase 1 | 模型筑基 | 2 周 | 2026-05-06 | 2026-05-17 | 新模型 + 数据库迁移 ✅ |
| Phase 2 | 撮合引擎 | 3 周 | 2026-05-19 | 2026-06-06 | 悲观撮合 + 回测对比 |
| Phase 3 | 风控状态机 | 2 周 | 2026-06-09 | 2026-06-20 | Trailing Stop 实盘模拟 |
| Phase 4 | 订单编排 | 2 周 | 2026-06-23 | 2026-07-04 | Signal→Orders 裂变 |
| Phase 5 | 实盘集成 | 3 周 | 2026-07-07 | 2026-07-25 | WebSocket 订单推送 |
| Phase 6 | 前端适配 | 2 周 | 2026-07-28 | 2026-08-08 | 仓位管理页面 |

---

### 5.2 Phase 1: 模型筑基（2 周） ✅ 已完成

**状态**: ✅ 已完成 (2026-03-30)

**目标**: 实现 v3.0 核心模型，不改动现有业务逻辑

**任务分解**:
```
Week 1:
├─ 新增 Order/Position/Account 实体类 ✅
├─ 新增 OrderStatus/OrderType/OrderRole 枚举 ✅
├─ 统一 Direction 为大写 ✅
└─ 数据库迁移脚本编写 ✅

Week 2:
├─ 数据库表创建 (orders/positions/accounts) ✅
├─ 单元测试编写 (覆盖率 ≥ 90%) ✅
├─ Code Review (领域层纯净性检查) ✅
└─ 提交到 dev 分支 ✅
```

**验收标准**:
- [x] 新模型通过 Pydantic v2 验证
- [x] 数据库迁移脚本可回滚
- [x] 单元测试覆盖率 ≥ 90% (143 测试，100% 通过)
- [x] 无 I/O 依赖污染领域层

**交付物**:
- `src/domain/models.py` (新增 Order/Position/Account)
- `src/infrastructure/v3_orm.py` (SQLAlchemy ORM 模型)
- `migrations/versions/001_unify_direction_enum.py`
- `migrations/versions/002_create_orders_positions_tables.py`
- `migrations/versions/003_create_signals_accounts_tables.py`
- `tests/unit/test_v3_models.py` (22 测试)
- `tests/unit/test_v3_orm.py` (27 测试)
- `tests/integration/test_v3_phase1_integration.py` (70 测试)
- `web-front/src/types/v3-models.ts` (前端类型定义)
- `docs/v3/v3-phase1-complete-report.md` (完成报告)

---

### 5.3 Phase 2: 撮合引擎（3 周）

**目标**: 实现悲观撮合引擎，支持 v3.0 回测模式

**任务分解**:
```
Week 1:
├─ 实现 MockMatchingEngine 类
├─ 实现订单优先级排序逻辑
└─ 实现滑点和手续费计算

Week 2:
├─ 实现 _execute_fill 仓位同步逻辑
├─ 新增 PMSBacktestReport 模型
└─ Backtester 支持 mode="v3_pms" 参数

Week 3:
├─ v2/v3 回测对比验证
├─ 边界 case 单元测试
└─ 性能基准测试
```

**验收标准**:
- [ ] v3.0 回测报告包含真实盈亏统计
- [ ] 同一策略 v2/v3 回测结果差异可解释
- [ ] 单元测试覆盖撮合边界 case
- [ ] 滑点/手续费计算精度验证

**交付物**:
- `src/domain/matching_engine.py`
- `src/application/pms_backtester.py`
- `tests/unit/test_mock_matching_engine.py`
- `tests/integration/test_v2_vs_v3_backtest.py`

---

### 5.4 Phase 3: 风控状态机（2 周）

**目标**: 实现动态风控状态机

**任务分解**:
```
Week 1:
├─ 实现 DynamicRiskManager 类
├─ 实现 TP1 成交后推保护损逻辑
└─ 实现移动止损 (Trailing) 计算

Week 2:
├─ 实现阶梯阈值频控
├─ 状态转移单元测试
└─ 实盘模拟测试
```

**验收标准**:
- [ ] TP1 成交后 SL 自动上移至开仓价
- [ ] Trailing 止损随高水位线动态调整
- [ ] 阶梯阈值有效限制更新频率
- [ ] 并发安全测试通过

**交付物**:
- `src/domain/risk_state_machine.py`
- `tests/unit/test_dynamic_risk_manager.py`

---

### 5.5 Phase 4: 订单编排（2 周）

**目标**: 实现 OrderManager 订单编排层

**任务分解**:
```
Week 1:
├─ 实现 OrderManager 类
├─ 实现 Signal→Orders 裂变逻辑
└─ 实现订单撤销和状态更新

Week 2:
├─ SignalToOrderAdapter 实现
├─ SignalPipeline 集成 OrderManager
└─ 端到端流程测试
```

**验收标准**:
- [ ] 信号生成后自动裂变 3 个订单 (Entry/TP1/SL)
- [ ] 订单状态与交易所同步
- [ ] 支持订单撤销
- [ ] 适配器模式验证通过

**交付物**:
- `src/application/order_manager.py`
- `src/application/adapters/signal_adapter.py`
- `tests/integration/test_order_orchestration.py`

---

### 5.6 Phase 5: 实盘集成（3 周）

**目标**: 实盘模式支持 v3.0 PMS

**任务分解**:
```
Week 1:
├─ ExchangeGateway 扩展订单管理接口
├─ 实现 watch_orders WebSocket 推送处理
└─ 实现并发保护 (Asyncio Lock)

Week 2:
├─ 实现启动时对账 (Reconciliation)
├─ 实现数据库行级锁
└─ 断网重启测试

Week 3:
├─ 端到端测试 (回测→模拟盘→实盘)
├─ 性能压测
└─ 安全审计
```

**验收标准**:
- [ ] 实盘订单状态实时同步
- [ ] 断网重启后仓位状态一致
- [ ] 无并发脏写问题
- [ ] 性能满足 100 订单/秒

**交付物**:
- `src/infrastructure/exchange_gateway.py` (增强版)
- `src/application/reconciliation.py`
- `tests/e2e/test_live_trading.py`

---

### 5.7 Phase 6: 前端适配（2 周）

**目标**: 前端支持 v3.0 仓位展示

**任务分解**:
```
Week 1:
├─ 仓位管理页面 (持仓/历史仓位)
├─ 订单管理页面 (挂单/成交)
└─ 回测报告新增 PMS 模式展示

Week 2:
├─ 账户净值曲线可视化
├─ 多级别止盈可视化
└─ 用户体验测试
```

**验收标准**:
- [ ] 前端展示仓位盈亏与后端一致
- [ ] 回测报告支持 v2/v3 切换
- [ ] 用户体验无降级
- [ ] 移动端适配

**交付物**:
- `web-front/src/pages/Positions.tsx`
- `web-front/src/pages/Orders.tsx`
- `web-front/src/components/PMSBacktestReport.tsx`

---

## 六、风险管理

### 6.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 | 负责人 |
|------|------|------|----------|--------|
| 并发脏写 | 高 | 高 | Asyncio Lock + 数据库行级锁 | 后端 |
| 实盘订单状态不同步 | 中 | 高 | 启动时对账 + WebSocket 心跳 | 后端 |
| 回测结果差异过大 | 中 | 中 | 双模式对比 + 差异分析报告 | QA |
| 前端用户体验降级 | 低 | 中 | 灰度发布 + 用户反馈收集 | 前端 |
| 迁移工期超期 | 中 | 中 | 每周进度 Review + 灵活调整 | PM |

### 6.2 回滚策略

| 阶段 | 回滚方式 | 回滚时间 |
|------|---------|---------|
| Phase 1 | 删除新表，恢复 Direction 小写 | < 1 小时 |
| Phase 2 | 配置开关 `enable_pms_mode=false` | 即时 |
| Phase 3 | 配置开关 `enable_pms_mode=false` | 即时 |
| Phase 4 | 配置开关 `enable_pms_mode=false` | 即时 |
| Phase 5 | 前端版本回滚 + 配置开关 | < 4 小时 |
| Phase 6 | 前端版本回滚 | < 1 小时 |

---

## 七、质量保障

### 7.1 代码审查红线

| 检查项 | 标准 | 工具 |
|--------|------|------|
| 领域层纯净性 | domain/ 无 I/O 依赖 | grep/ccxt/aiohttp |
| 金融精度 | 所有金额用 Decimal | 类型检查 |
| 并发安全 | 仓位修改加锁 | Code Review |
| 日志脱敏 | API 密钥 mask_secret() | 日志审计 |

### 7.2 测试覆盖要求

| 模块 | 覆盖率要求 | 测试类型 |
|------|-----------|---------|
| 撮合引擎 | 100% | 单元测试 + 边界 case |
| 风控状态机 | 100% | 单元测试 + 状态转移 |
| 订单编排 | 95% | 单元测试 + 集成测试 |
| 实盘集成 | 90% | E2E 测试 + 模拟盘 |

### 7.3 文档更新清单

| 文档 | 更新时机 | 负责人 |
|------|---------|--------|
| CLAUDE.md | Phase 1 完成 | 后端 |
| docs/v3/ | 各阶段完成 | 各模块负责人 |
| API 文档 | Phase 4 完成 | 后端 |
| 用户手册 | Phase 6 完成 | 前端 |

---

## 八、团队分工

| 角色 | Phase 1-3 | Phase 4-5 | Phase 6 |
|------|----------|----------|--------|
| 后端开发 | 2 人 | 2 人 | 0.5 人 |
| 前端开发 | 0 | 0.5 人 | 1 人 |
| QA 测试 | 0.5 人 | 1 人 | 1 人 |
| 架构师 | 0.5 人 | 0.5 人 | 0.5 人 |

---

## 九、里程碑检查点

| 检查点 | 日期 | 检查内容 | 通过标准 |
|--------|------|---------|---------|
| M1 | 2026-05-17 | Phase 1 完成 | 新模型 + 数据库迁移通过 ✅ |
| M2 | 2026-06-06 | Phase 2 完成 | v2/v3 回测对比报告 |
| M3 | 2026-06-20 | Phase 3 完成 | Trailing Stop 模拟测试 |
| M4 | 2026-07-04 | Phase 4 完成 | 订单编排端到端测试 |
| M5 | 2026-07-25 | Phase 5 完成 | 实盘 E2E 测试 |
| M6 | 2026-08-08 | Phase 6 完成 | 前端上线 |

---

## 十、下一步行动

### 立即行动（本周）

1. **创建 TaskCreate 任务清单**
   - P0-1: 设计实时价格监控架构
   - P0-2: 实现止盈状态追踪器
   - ...

2. **搭建开发环境**
   - 安装 Alembic + SQLAlchemy async
   - 配置本地 SQLite 测试数据库

3. **召开启动会议**
   - 确认团队成员角色
   - 分配 Phase 1 任务

### 本周预期交付

- [ ] P0 止盈追踪技术方案
- [ ] v3 Phase 1 详细任务分解
- [ ] 开发环境就绪

---

*盯盘狗 🐶 项目组*
*2026-03-30*
