# 研究发现

## Phase 6: 前端适配 - 技术发现 (2026-03-31)

### 前端架构分析

**技术栈**:
- React 19 + TypeScript + Vite 6.x
- TailwindCSS 4.x (Apple 风格设计系统)
- SWR (数据获取) + React Hooks (本地状态)
- Lightweight Charts / Recharts (图表)

**现有页面** (`web-front/src/pages/`):
- `Dashboard.tsx` - 系统仪表盘
- `Signals.tsx` - 信号历史列表（可配置表格列）
- `StrategyWorkbench.tsx` - 策略工作台（递归逻辑树编辑）
- `Backtest.tsx` - 回测沙箱
- `Snapshots.tsx` - 配置快照管理

**类型定义现状**:
- `web-front/src/types/order.ts` - Phase 5 订单/持仓类型（完整）
- `web-front/src/types/v3-models.ts` - v3.0 核心模型（Account/Signal/Order/Position）
- `web-front/src/types/strategy.ts` - 递归逻辑树类型

**API 调用层现状** (`web-front/src/lib/api.ts`):
- 信号/策略/回测 API 已完整实现
- **缺失**: v3 订单/仓位/账户 API 调用函数

### 后端 API 状态

**已实现** (Phase 5):
- ExchangeGateway 订单接口（`place_order`, `cancel_order`, `fetch_order`）
- WebSocket 订单推送监听（`watch_orders`）
- PositionManager 并发保护
- Reconciliation 对账服务
- CapitalProtection 资金保护

**缺失** (需 Phase 6 实现):
- REST API 端点（`/api/v3/orders`, `/api/v3/positions`, `/api/v3/account/balance`）
- PMS 回测报告端点

### 技术债务

| 问题 | 影响 | 解决方案 |
|------|------|----------|
| OrderRole 枚举前后端不一致 | 类型对齐问题 | 后端已实现精细定义 (ENTRY/TP1-5/SL)，前端 order.ts 已对齐 |
| v3 API 端点缺失 | 前端无法获取数据 | 需实现后端 REST API 端点 + 前端 API 调用函数 |

---

## Phase 1-5 完成技术总结 (2026-03-31)

### 审查结果

**系统性审查**: 57/57 项通过 (100%)
**单元测试**: 241/241 通过 (100%)
**审查报告**: `docs/reviews/phase1-5-comprehensive-review-report.md`

### 核心发现

1. **枚举定义一致性** ✅
   - Direction: LONG/SHORT 在所有阶段使用一致
   - OrderStatus: 7 状态 (PENDING/OPEN/FILLED/CANCELED/REJECTED/EXPIRED/PARTIALLY_FILLED)
   - OrderType: 5 类型 (MARKET/LIMIT/STOP_MARKET/STOP_LIMIT/TRAILING_STOP)
   - OrderRole: 7 角色 (ENTRY/TP1/TP2/TP3/TP4/TP5/SL)

2. **Decimal 精度保护** ✅
   - 所有金融计算使用 Decimal，无 float 污染
   - FinancialModel 基类确保精度继承

3. **领域层纯净性** ✅
   - domain/目录无 I/O 依赖
   - 符合 Clean Architecture 原则

4. **Gemini 评审问题修复** ✅
   - G-001: asyncio.Lock 释放后使用 → WeakValueDictionary
   - G-002: 市价单价格缺失 → fetch_ticker_price
   - G-003: DCA 限价单吃单陷阱 → place_all_orders_upfront
   - G-004: 对账幽灵偏差 → 10 秒 Grace Period

5. **并发安全设计** ✅
   - Asyncio Lock (进程内) + SELECT FOR UPDATE (数据库行级锁)
   - WeakValueDictionary 自动清理锁对象

### 交付物清单

| Phase | 核心文件 | 测试数 | 状态 |
|-------|---------|--------|------|
| Phase 1 | src/domain/models.py, src/infrastructure/v3_orm.py | 49 | ✅ |
| Phase 2 | src/domain/matching_engine.py | 14 | ✅ |
| Phase 3 | src/domain/risk_manager.py | 35 | ✅ |
| Phase 4 | src/domain/order_manager.py | 33 | ✅ |
| Phase 5 | exchange_gateway.py, position_manager.py, capital_protection.py, reconciliation.py, dca_strategy.py | 110 | ✅ |

---

## 子任务 F - 递归逻辑树引擎

### 技术要点

1. **Pydantic 递归模型**
   - 使用 `from __future__ import annotations` 启用字符串自引用
   - 使用 `Annotated[Union[...], Field(discriminator='type')]` 实现多态
   - 使用 `model_validator` 限制递归深度

2. **Discriminator Union**
   - 自动类型识别基于 `type` 字段
   - 支持运行时类型缩窄

3. **递归评估算法**
   - 深度优先遍历
   - AND 节点：`all()` 短路
   - OR 节点：`any()` 短路
   - NOT 节点：结果反转

### 现有代码分析

**当前策略引擎** (`src/domain/strategy_engine.py`):
- `DynamicStrategyRunner` - 平铺式 runner
- `StrategyWithFilters` - 平铺过滤器链
- `create_dynamic_runner()` - 工厂函数

**当前数据模型** (`src/domain/models.py`):
- `StrategyDefinition` - 平铺的 `triggers` 和 `filters` 列表
- `TriggerConfig` - 触发器配置
- `FilterConfig` - 过滤器配置

### 需要创建的新文件

```
src/domain/
├── logic_tree.py          # 递归类型定义
├── recursive_engine.py    # 递归评估引擎
└── ...

tests/unit/
└── test_recursive_engine.py  # 递归引擎测试
```

---

## 子任务 E - 前端递归渲染

### 技术要点

1. **React 递归组件**
   - 组件调用自身处理子节点
   - 使用 `depth` prop 控制缩进和样式

2. **Schema 驱动表单**
   - 从后端 API 获取 JSON Schema
   - 动态生成输入控件

3. **Trace 树可视化**
   - 与逻辑树同构的结果树
   - 成功/失败状态标记

### 现有前端分析

**当前组件** (`web-front/src/components/`):
- `StrategyBuilder.tsx` - 硬编码平铺组件
- 各种 `*Editor.tsx` - 死板的参数编辑器

**需要删除**:
- `StrategyBuilder.tsx`
- `PinbarParamsEditor.tsx`
- `EmaFilterEditor.tsx`
- 等 10+ 个硬编码组件

### 需要创建的新文件

```
web-front/src/components/
├── NodeRenderer.tsx       # 递归渲染器
├── LogicGateControl.tsx   # 逻辑门控制
└── LeafNodeForm.tsx       # 叶子节点表单
```

---

## 参考资料

### Pydantic 递归模型
- https://docs.pydantic.dev/latest/usage/postponed_annotations/#self-referencing-models
- https://docs.pydantic.dev/latest/usage/types/unions/#discriminated-unions

### React 递归组件
- https://react.dev/learn/passing-data-deeply-context
- https://advanced-react.com/advanced-patterns/recursion

---

## 第二阶段研究发现（2026-03-26）

### 系统状态验证结果

**已完成功能**:
1. 递归逻辑树引擎 - `src/domain/logic_tree.py` + `src/domain/recursive_engine.py` ✅
2. 热预览接口 - `POST /api/strategies/preview` ✅
3. 前端递归组件 - `NodeRenderer.tsx`, `LogicGateControl.tsx`, `LeafNodeForm.tsx` ✅
4. Trace 树可视化 - `TraceTreeViewer.tsx` ✅
5. 策略模板 CRUD - `GET/POST/PUT/DELETE /api/strategies` ✅
6. 策略元数据接口 - `GET /api/strategies/meta` ✅

**待完成功能**:
1. 一键下发实盘 - 策略模板应用到实盘监控
2. 信号标签动态化 - 移除 `ema_trend`/`mtf_status` 硬编码
3. 前端硬编码组件清理 - 确认是否还有遗留

### 技术债清单

| 编号 | 问题 | 影响范围 | 优先级 |
|------|------|----------|--------|
| #1 | TraceEvent 字段命名不一致 | 前后端数据对齐 | 高 |
| #2 | SignalResult 硬编码标签 | 通知卡片动态化 | 高 |
| #3 | FilterConfig.params 为 Dict[str, Any] | API 类型安全 | 中 |
| #4 | 前端可能还有硬编码组件 | Schema 驱动纯度 | 中 |

### 下一阶段技术方案

### 下一阶段技术方案

**一键下发实盘方案**:
```
用户操作：选择模板 → 点击"应用"
    ↓
前端：POST /api/strategies/{id}/apply
    ↓
后端：
  1. 从数据库加载策略模板
  2. 反序列化为 StrategyDefinition
  3. 调用 ConfigManager 更新 user_config
  4. 触发信号管道热重载
  5. 回填 K 线状态（200+ 根）
    ↓
响应：{ success: true, message: "策略已应用" }
```

**关键实现点**:
- 使用 `asyncio.Lock()` 保护配置替换过程
- 原子操作：先创建新 Runner，再替换指针
- 状态回填：从交易所拉取历史 K 线

**信号标签动态化方案**:
```
旧流程:
  process_kline → _legacy_engine.get_ema_trend() → SignalResult(ema_trend="Bullish")

新流程:
  process_kline → 从 attempt.filter_results 提取通过的过滤器
               → 生成 tags = [{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}]
               → SignalResult(tags=...)
```

**热重载并发控制**:
```python
class SignalPipeline:
    def __init__(self):
        self._runner_lock = asyncio.Lock()  # 互斥锁
        self._attempts_queue = asyncio.Queue()  # 异步背压队列

    async def on_config_updated(self, new_config):
        async with self._runner_lock:
            # 重建 Runner
            self._runner = create_dynamic_runner(new_config)
            # 预热：用历史 K 线恢复状态
            await self._warmup_runner(self._kline_history)
        # 清空冷却缓存
        self._signal_cooldown_cache.clear()

    async def _flush_attempts_worker(self):
        """后台 Worker 批量落盘，避免阻塞主事件循环"""
        while True:
            attempts = await self._attempts_queue.get_batch()
            await self._repository.save_batch(attempts)
```

### 相关文件参考

- `docs/tasks/2026-03-25-子任务 B-策略工作台与 CRUD 接口开发.md` - 策略模板库设计
- `docs/tasks/2026-03-25-子任务 C-信号结果动态标签系统重构.md` - 信号标签动态化
- `docs/tasks/2026-03-25-子任务 A-实盘引擎热重载与稳定性重构.md` - 热重载机制
