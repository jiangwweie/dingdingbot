# 研究发现

## P6-003: 仓位管理页面开发 (2026-03-31)

### 组件清单

**新建组件**:
| 组件 | 路径 | 功能 |
|------|------|------|
| `PositionsTable` | `web-front/src/components/v3/PositionsTable.tsx` | 仓位列表表格 |
| `PositionDetailsDrawer` | `web-front/src/components/v3/PositionDetailsDrawer.tsx` | 仓位详情抽屉 |
| `ClosePositionModal` | `web-front/src/components/v3/ClosePositionModal.tsx` | 平仓确认对话框 |
| `TPChainDisplay` | `web-front/src/components/v3/TPChainDisplay.tsx` | 止盈订单链展示 |
| `SLOrderDisplay` | `web-front/src/components/v3/SLOrderDisplay.tsx` | 止损订单展示 |

**现有组件复用**:
- `DirectionBadge` - 方向徽章（LONG/SHORT）
- `PnLBadge` - 盈亏徽章
- `DecimalDisplay` - Decimal 格式化显示
- `OrderStatusBadge` - 订单状态徽章

**页面**:
- `Positions.tsx` - 主页面（/v3/positions）

### 技术实现

1. **API 集成**:
   - `fetchPositions()` - 获取仓位列表
   - `closePosition()` - 平仓操作

2. **筛选功能**:
   - 币种对筛选（BTC/ETH/SOL/BNB）
   - 仓位状态筛选（持仓中/已平仓）

3. **平仓功能**:
   - 支持全部平仓和部分平仓（25%/50%/75%/100%）
   - 订单类型选择（MARKET/LIMIT）
   - 限价单价格输入
   - 资金保护检查提示

4. **账户概览**:
   - 账户权益
   - 未实现盈亏
   - 保证金占用
   - 已实现盈亏

### 路由配置

- App.tsx: 添加 `/positions` 路由
- Layout.tsx: 添加导航菜单项（仓位）

### TypeScript 编译验证

```bash
npm run build
# ✓ 2781 modules transformed.
# ✓ built in 1.44s
```

### 设计亮点

1. **Apple 风格 UI**: 渐变卡片、圆角、阴影
2. **响应式布局**: 适配桌面和移动端
3. **交互优化**:
   - 悬停效果
   - 加载动画
   - 空状态提示
4. **信息层级**:
   - 账户概览卡片（顶部）
   - 筛选器（中部）
   - 数据表格（主体）

### 依赖 P6-002

- `fetchPositions()` API 函数
- `closePosition()` API 函数
- `PositionInfo`, `PositionResponse` 类型定义

---

## 🔴 关键 Bug 修复：MTF 过滤器 K 线闭合判断错误 (2026-03-31)

### 问题描述
系统运行 4 小时，76 次尝试记录，0 个信号产生。所有 15 次 Pinbar 形态检测通过后，均被 MTF 过滤器以 `higher_tf_data_unavailable` 为由拦截。

### 根因分析
**文件**: `src/domain/timeframe_utils.py:91-148`
**函数**: `get_last_closed_kline_index()`

**错误逻辑** (修复前):
```python
elif kline_period == current_period:
    if kline.timestamp == current_timestamp:
        break  # 当前 K 线，不可用
    else:
        best_index = i  # ❌ 错误！同周期但 timestamp 不同的 K 线可能也未闭合
        break
```

**问题场景**:
- 当前时间 20:15（15m K 线闭合）
- 查找 1h 高周期 K 线
- `current_period = 20:15 // 1h = 20:00 周期`
- `kline.timestamp = 20:00` → `kline_period = 同周期`
- 代码错误地认为这根 1h K 线可用，但它在 21:00 才闭合！

### 修复方案
**正确逻辑** (修复后):
```python
period_ms = parse_timeframe_to_ms(timeframe)
best_index = -1
for i, kline in enumerate(klines):
    # Calculate when this kline ends
    kline_end_time = kline.timestamp + period_ms

    if kline_end_time <= current_timestamp:
        # This kline has closed, it's safe to use for MTF analysis
        best_index = i
    else:
        # This kline hasn't closed yet, and neither do any after it
        break

return best_index
```

### 测试覆盖
新增 3 个边界场景测试：
1. `test_critical_bug_15m_uses_1h_not_yet_closed` - 验证 20:15 时不使用 20:00 的 1h K 线
2. `test_1h_kline_just_closed` - 验证 21:00 时可使用刚闭合的 20:00 的 1h K 线
3. `test_multiple_closed_klines_uses_latest` - 验证使用最新闭合的 K 线

修正 1 个错误预期：
- `test_15m_signal_uses_1h_closed` - 原预期错误地认为 10:15 时可使用 10:00 的 1h K 线

### 影响范围
- 修复后 MTF 过滤器能正确获取高周期趋势数据
- 信号产生流程恢复正常
- 预计信号产生率从 0% 提升到正常水平（约 15-20% 的 Pinbar 通过率）

### 相关文件
- `src/domain/timeframe_utils.py` - 修复逻辑
- `tests/unit/test_timeframe_utils.py` - 测试覆盖

---

## Phase 6: 前端适配 - 架构分析报告 (2026-03-31)

### 1. 类型定义完整性报告

#### 1.1 已完成类型定义

**文件**: `web-front/src/types/order.ts`

| 类型/接口 | 状态 | 说明 |
|-----------|------|------|
| `Direction` | ✅ | LONG/SHORT 枚举 |
| `OrderType` | ✅ | MARKET/LIMIT/STOP_MARKET/STOP_LIMIT |
| `OrderRole` | ✅ | ENTRY/TP1-5/SL (7 角色精细定义) |
| `OrderStatus` | ✅ | 7 状态机 (PENDING/OPEN/FILLED/CANCELED/REJECTED/EXPIRED/PARTIALLY_FILLED) |
| `Tag` | ✅ | 动态标签接口 |
| `OrderRequest` | ✅ | 下单请求 (14 字段) |
| `OrderResponse` | ✅ | 订单响应 (20 字段) |
| `OrderCancelResponse` | ✅ | 取消订单响应 (7 字段) |
| `PositionInfo` | ✅ | 持仓信息 (20 字段) |
| `PositionResponse` | ✅ | 持仓列表响应 |
| `AccountBalance` | ✅ | 账户余额信息 |
| `AccountResponse` | ✅ | 账户信息响应 (13 字段) |
| `ReconciliationRequest` | ✅ | 对账请求 |
| `ReconciliationReport` | ✅ | 对账报告 |
| `PositionMismatch` | ✅ | 仓位不匹配记录 |
| `OrderMismatch` | ✅ | 订单不匹配记录 |
| `CapitalProtectionCheckResult` | ✅ | 资金保护检查结果 (14 字段) |

**结论**: 前端类型定义与后端 `src/domain/models.py` 完全对齐，无需补充。

#### 1.2 v3.0 核心模型 (`web-front/src/types/v3-models.ts`)

| 类型 | 状态 | 说明 |
|------|------|------|
| `Direction` | ✅ | LONG/SHORT |
| `OrderStatus` | ✅ | 6 状态 (与 order.ts 略有差异，需对齐) |
| `OrderType` | ✅ | 4 类型 (缺 TRAILING_STOP) |
| `OrderRole` | ⚠️ | 仅 ENTRY/TP1/SL (缺 TP2-5) |
| `Account` | ✅ | 资产账户 |
| `Signal` | ✅ | 策略信号 |
| `Order` | ✅ | 交易订单 |
| `Position` | ✅ | 核心仓位 |
| `V3Entity` | ✅ | 多态联合类型 |

**建议**: Phase 6 优先使用 `types/order.ts`，该文件字段更完整。

---

### 2. API 调用层缺失清单

**文件**: `web-front/src/lib/api.ts`

#### 2.1 已完成 API 调用

| 函数 | 端点 | 状态 |
|------|------|------|
| `fetchSystemConfig` | GET /api/config | ✅ |
| `updateSystemConfig` | PUT /api/config | ✅ |
| `fetchStrategyMetadata` | GET /api/strategies/meta | ✅ |
| `previewStrategy` | POST /api/strategies/preview | ✅ |
| `applyStrategy` | POST /api/strategies/{id}/apply | ✅ |
| `fetchSnapshots` | GET /api/config/snapshots | ✅ |
| `createSnapshot` | POST /api/config/snapshots | ✅ |
| `deleteSnapshot` | DELETE /api/config/snapshots/{id} | ✅ |
| `applySnapshot` | POST /api/config/snapshots/{id}/activate | ✅ |
| `getSignalStatus` | GET /api/signals/{id}/status | ✅ |
| `listSignalStatuses` | GET /api/signals/status | ✅ |
| `runBacktest` | POST /api/backtest | ✅ |
| `fetchBacktestSignals` | GET /api/backtest/signals | ✅ |

#### 2.2 缺失 API 调用 (Phase 6 需实现)

**订单管理**:
```typescript
// POST /api/v3/orders
async function createOrder(payload: OrderRequest): Promise<OrderResponse>

// GET /api/v3/orders?symbol=...&status=...
async function fetchOrders(params?: OrderQuery): Promise<Order[]>

// GET /api/v3/orders/{order_id}
async function fetchOrder(orderId: string): Promise<OrderResponse>

// DELETE /api/v3/orders/{order_id}
async function cancelOrder(orderId: string): Promise<OrderCancelResponse>

// POST /api/v3/orders/check (资金保护检查)
async function checkOrderCapital(payload: OrderRequest): Promise<CapitalProtectionCheckResult>
```

**仓位管理**:
```typescript
// GET /api/v3/positions
async function fetchPositions(symbol?: string): Promise<PositionResponse>

// GET /api/v3/positions/{position_id}
async function fetchPosition(positionId: string): Promise<PositionInfo>

// POST /api/v3/positions/{position_id}/close (主动平仓)
async function closePosition(positionId: string): Promise<OrderResponse>
```

**账户管理**:
```typescript
// GET /api/v3/account/balance
async function fetchAccountBalance(): Promise<AccountResponse>

// GET /api/v3/account/snapshot (实时快照)
async function fetchAccountSnapshot(): Promise<AccountSnapshot>
```

**对账服务**:
```typescript
// POST /api/v3/reconciliation
async function runReconciliation(payload: ReconciliationRequest): Promise<ReconciliationReport>
```

**PMS 回测**:
```typescript
// POST /api/v3/backtest/pms
async function runPmsBacktest(payload: PmsBacktestRequest): Promise<PmsBacktestReport>

// GET /api/v3/backtest/pms/{report_id}
async function fetchPmsBacktestReport(reportId: string): Promise<PmsBacktestReport>
```

#### 2.3 后端 API 端点状态 (`src/interfaces/api.py`)

| 端点 | 状态 | 说明 |
|------|------|------|
| GET /api/account | ✅ | 账户快照 (Phase 5 简化版) |
| GET /api/strategies | ✅ | 策略模板列表 |
| POST /api/backtest | ✅ | 回测执行 |
| **POST /api/v3/orders** | ❌ | Phase 6 待实现 |
| **GET /api/v3/positions** | ❌ | Phase 6 待实现 |
| **GET /api/v3/account/balance** | ❌ | Phase 6 待实现 |

---

### 3. 页面组件结构建议

#### 3.1 现有页面组件分析

**`Dashboard.tsx`**:
- 账户概览卡片（3 个指标）
- 系统状态网格（4 个指标）
- 最新信号列表
- 诊断摘要

**`StrategyWorkbench.tsx`**:
- 策略模板列表（左侧）
- 策略编辑器（右侧）
- 预览控制面板
- Trace Tree 可视化

**组件模式**:
- 使用 `useApi<T>()` Hook (SWR 封装) 获取数据
- TailwindCSS 4.x Apple 风格设计
- Lucide React 图标库
- 响应式网格布局

#### 3.2 Phase 6 新增页面结构建议

**页面 1: 订单管理 (`/v3/orders`)**
```tsx
// web-front/src/pages/V3Orders.tsx
components:
  - OrdersTable: 订单列表表格（支持分页/筛选/排序）
  - OrderStatusBadge: 状态徽章组件
  - OrderDetailsDrawer: 订单详情侧滑抽屉
  - CreateOrderModal: 下单弹窗（选填：市价/限价/止损）
  - CancelOrderConfirm: 取消订单确认对话框
```

**页面 2: 仓位管理 (`/v3/positions`)**
```tsx
// web-front/src/pages/V3Positions.tsx
components:
  - PositionsTable: 持仓列表表格
  - PositionPnLChart: 未实现盈亏迷你图
  - ClosePositionModal: 平仓确认弹窗
  - LeverageSlider: 杠杆倍数调节器
  - StopLossTakeProfitEditor: 止损止盈编辑器
```

**页面 3: 账户详情 (`/v3/account`)**
```tsx
// web-front/src/pages/V3Account.tsx
components:
  - AccountOverview: 账户总览卡片
  - BalanceDistributionPie: 余额分布饼图
  - EquityCurve: 净值曲线图
  - DailyPnLChart: 每日盈亏柱状图
  - CapitalProtectionStatus: 资金保护状态面板
```

**页面 4: PMS 回测报告 (`/v3/backtest/pms`)**
```tsx
// web-front/src/pages/V3BacktestPms.tsx
components:
  - BacktestConfigForm: 回测配置表单
  - PerformanceMetricsTable: 绩效指标表格
  - EquityCurveChart: 净值曲线
  - TradeDistributionChart: 交易分布图
  - DrawdownAnalysis: 回撤分析
  - TradeLogTable: 交易明细日志
```

#### 3.3 可复用组件建议

**通用组件** (`web-front/src/components/v3/`):
```
├── DecimalDisplay.tsx      # 统一 Decimal 格式化（支持精度/货币符号）
├── PnLBadge.tsx            # 盈亏徽章（红绿配色）
├── OrderRoleBadge.tsx      # 订单角色徽章
├── DirectionBadge.tsx      # 方向徽章（多/空）
├── StatusBadge.tsx         # 通用状态徽章
├── DateTimeDisplay.tsx     # 时间格式化显示
├── ConfirmationModal.tsx   # 通用确认对话框
└── LoadingSkeleton.tsx     # 加载骨架屏
```

---

### 4. 技术发现

#### 4.1 架构优势

1. **类型安全**: 前端 TypeScript 类型与后端 Pydantic 模型完全对齐
2. **Schema 驱动**: 策略编辑器已实现递归逻辑树 Schema 驱动
3. **组件复用**: TailwindCSS 提供一致的 Apple 风格设计系统
4. **数据获取**: SWR 提供自动缓存/重试/焦点重新验证

#### 4.2 待解决技术债

| 问题 | 影响 | 优先级 | 解决方案 |
|------|------|--------|----------|
| OrderStatus 枚举差异 | v3-models.ts 缺 EXPIRED/PARTIALLY_FILLED | 中 | 对齐 order.ts |
| OrderRole 定义不完整 | v3-models.ts 缺 TP2-5 | 中 | 对齐 order.ts |
| API 调用层缺失 | 无法调用 v3 订单/仓位 API | 高 | 补充 12 个调用函数 |
| 后端 REST 端点缺失 | 前端无数据源 | 高 | 后端 Phase 6 优先实现 |

#### 4.3 推荐实施顺序

1. **后端优先**: 先实现 REST API 端点 (`/api/v3/orders`, `/api/v3/positions`, `/api/v3/account/balance`)
2. **前端 API 层**: 补充 `api.ts` 中的调用函数
3. **页面开发**: 按订单 → 仓位 → 账户 → 回测顺序实施
4. **组件抽象**: 在开发过程中提取通用组件

---

## Phase 1-5 完成技术总结 (2026-03-31)

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

## Phase 6 P6-002: 前端 API 调用层扩展完成 (2026-03-31)

### 实现内容

**文件**: `web-front/src/lib/api.ts`

#### 已实现的 12 个 API 调用函数

**订单管理 API (5 个)**:
| 函数 | 端点 | 状态 |
|------|------|------|
| `createOrder(request: OrderRequest)` | POST /api/v3/orders | ✅ |
| `fetchOrders(params?: {...})` | GET /api/v3/orders | ✅ |
| `fetchOrder(orderId: string)` | GET /api/v3/orders/{id} | ✅ |
| `cancelOrder(orderId: string, symbol: string)` | DELETE /api/v3/orders/{id} | ✅ |
| `checkOrderCapital(request: OrderCheckRequest)` | POST /api/v3/orders/check | ✅ |

**仓位管理 API (3 个)**:
| 函数 | 端点 | 状态 |
|------|------|------|
| `fetchPositions(params?: {...})` | GET /api/v3/positions | ✅ |
| `fetchPosition(positionId: string)` | GET /api/v3/positions/{id} | ✅ |
| `closePosition(positionId: string, request?: ClosePositionRequest)` | POST /api/v3/positions/{id}/close | ✅ |

**账户管理 API (2 个)**:
| 函数 | 端点 | 状态 |
|------|------|------|
| `fetchAccountBalance()` | GET /api/v3/account/balance | ✅ |
| `fetchAccountSnapshot()` | GET /api/v3/account/snapshot | ✅ |

**对账服务 API (1 个)**:
| 函数 | 端点 | 状态 |
|------|------|------|
| `runReconciliation(symbol: string)` | POST /api/v3/reconciliation | ✅ |

### 技术调整

1. **返回类型修正**:
   - `fetchPositions`: `PositionResponse` → `PositionsResponse` (带分页的列表响应)
   - `fetchAccountBalance`: `AccountResponse` → `AccountBalance` (单一余额对象)

2. **函数命名统一**:
   - `fetchPositionDetails` → `fetchPosition` (与 `fetchOrder` 命名风格对齐)
   - `fetchOrderDetails` → `fetchOrder`
   - `checkOrder` → `checkOrderCapital` (避免与 `createOrder` 语义混淆)

3. **类型来源**:
   - 所有类型从 `web-front/src/types/order.ts` 导入
   - 与后端 `src/domain/models.py` Pydantic 模型完全对齐

### 验收状态

- [x] 12 个 API 调用函数全部实现
- [ ] TypeScript 编译验证 (待运行)
- [x] 与后端 API 契约表对齐 (`docs/designs/phase6-v3-api-contract.md`)
- [x] 代码风格与现有 `api.ts` 一致 (使用 `fetcher` 错误处理模式)

### 下一步

1. 运行 TypeScript 编译检查 (`npm run build` 或 `tsc --noEmit`)
2. 如有类型错误，修复
3. 更新 `progress.md` 记录进度

---

## Phase 6: 后端 REST API 端点实现 (2026-03-31)

### 1. 已实现端点列表

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/api/v3/orders` | POST | ✅ | 创建订单（支持 MARKET/LIMIT/STOP_MARKET/STOP_LIMIT） |
| `/api/v3/orders/{order_id}` | DELETE | ✅ | 取消订单 |
| `/api/v3/orders/{order_id}` | GET | ✅ | 查询订单详情 |
| `/api/v3/orders` | GET | ✅ | 查询订单列表（待实现 OrderRepository） |
| `/api/v3/positions` | GET | ✅ | 查询持仓列表 |
| `/api/v3/positions/{position_id}` | GET | ✅ | 查询持仓详情（待实现 PositionRepository） |
| `/api/v3/account/balance` | GET | ✅ | 查询账户余额 |
| `/api/v3/account/snapshot` | GET | ✅ | 查询账户快照 |
| `/api/v3/reconciliation` | POST | ✅ | 启动对账服务 |

### 2. 依赖注入模式

v3 API 使用以下依赖注入：

```python
# 现有依赖（Phase 1-5）
set_dependencies(
    repository: SignalRepository,
    account_getter: Callable[[], Any],
    config_manager: Optional[Any],
    exchange_gateway: Optional[Any],
    signal_tracker: Optional[Any],
)

# v3 新增依赖
set_v3_dependencies(
    position_manager: Optional[Any],      # PositionManager
    capital_protection: Optional[Any],    # CapitalProtectionManager
    account_service: Optional[Any],       # AccountService
)
```

### 3. 异常处理映射

| 异常类 | HTTP 状态码 | 错误码 | 说明 |
|--------|-------------|--------|------|
| `OrderNotFoundError` | 404 | F-012 | 订单不存在 |
| `OrderAlreadyFilledError` | 400 | F-013 | 订单已成交（无法取消） |
| `RateLimitError` | 429 | C-010 | API 频率限制 |
| `InvalidOrderError` | 400 | F-011 | 订单参数错误 |
| `InsufficientMarginError` | 400 | F-010 | 保证金不足 |
| CapitalProtection 拒绝 | 400 | SINGLE_TRADE_LOSS_LIMIT 等 | 资金保护检查失败 |

### 4. 订单角色映射逻辑

v3 API 使用精细订单角色 (`ENTRY`/`TP1-5`/`SL`)，需要映射到 CCXT 的 `side` 参数：

```python
# LONG + ENTRY -> "buy" (开多)
# LONG + TP/SL -> "sell" (平多)
# SHORT + ENTRY -> "sell" (开空)
# SHORT + TP/SL -> "buy" (平空)

is_entry = request.role == OrderRole.ENTRY
if request.direction == Direction.LONG:
    side = "buy" if is_entry else "sell"
else:  # SHORT
    side = "sell" if is_entry else "buy"
```

### 5. 资本保护检查

下单前必须通过资本保护检查（`CapitalProtectionManager.pre_order_check`）：

- 单笔交易损失检查（默认 2% of balance）
- 仓位占比检查（默认 20% of balance）
- 每日亏损检查（默认 5% of balance）
- 每日交易次数检查（默认 50 次）
- 最低余额检查（默认 100 USDT）

### 6. ExchangeGateway 扩展

新增方法：

```python
# 获取账户余额
async def fetch_account_balance(self) -> Optional[AccountSnapshot]

# 获取持仓列表
async def fetch_positions(self, symbol: Optional[str] = None) -> List[PositionInfo]
```

### 7. 测试覆盖

**文件**: `tests/unit/test_v3_api_endpoints.py`

12 个测试用例全部通过 ✅

### 8. 待办事项

1. **OrderRepository**: 实现订单持久化，支持订单列表查询和历史记录
2. **PositionRepository**: 实现仓位持久化，支持仓位详情查询
3. **完整对账逻辑**: 当前对账端点返回简化版本，需要实现完整的本地 vs 交易所对比逻辑
4. **订单状态 WebSocket 推送**: 集成 `watch_orders` WebSocket 推送
