# 任务计划 - P6-005 账户净值曲线可视化

> **创建日期**: 2026-03-31
> **负责人**: @frontend
> **优先级**: P1
> **预计工时**: 4 小时

---

## 任务目标

实现 v3.0 账户页面，显示账户余额、权益曲线、盈亏统计。

**相关文件**:
- **契约表**: `docs/designs/phase6-v3-api-contract.md` Section 2.5-2.6
- **类型定义**: `web-front/src/types/order.ts` - AccountBalance, AccountSnapshot
- **API 调用**: 依赖 P6-002 的 `fetchAccountBalance()`, `fetchAccountSnapshot()` 函数
- **现有页面**: `web-front/src/pages/Account.tsx` - 参考卡片布局模式

---

## 阶段分解

### 阶段 1: 基础组件创建 ✅

- [x] `AccountOverviewCards.tsx` - 账户概览卡片组件（4 张卡片）
- [x] `DateRangeSelector.tsx` - 日期范围选择器（7 天/30 天/90 天）

### 阶段 2: 图表组件创建 ✅

- [x] `EquityCurveChart.tsx` - 净值曲线图表（Recharts AreaChart）
- [x] `PositionDistributionPie.tsx` - 仓位分布饼图（Recharts PieChart）

### 阶段 3: 统计组件创建 ✅

- [x] `PnLStatisticsCards.tsx` - 盈亏统计卡片（日/周/月/总盈亏）

### 阶段 4: 主页面开发 ✅

- [x] `Account.tsx` - 主页面（/account）
- [x] 账户概览功能
- [x] 净值曲线图表（支持时间范围切换）
- [x] 盈亏统计卡片
- [x] 仓位分布饼图
- [x] 账户明细表格

### 阶段 5: 路由集成与测试 ✅

- [x] 添加路由到 App.tsx
- [x] TypeScript 编译验证
- [x] 页面功能自测

---

## 组件结构

```
web-front/src/pages/Account.tsx
web-front/src/components/v3/
├── AccountOverviewCards.tsx      # 账户概览卡片（总权益、可用余额、未实现盈亏、保证金占用）
├── EquityCurveChart.tsx          # 净值曲线图表（Recharts AreaChart）
├── PnLStatisticsCards.tsx        # 盈亏统计卡片
├── PositionDistributionPie.tsx   # 仓位分布饼图
└── DateRangeSelector.tsx         # 日期范围选择器（7 天/30 天/90 天）
```

---

## 技术栈

- React 19 + TypeScript + Vite 6.x
- TailwindCSS 4.x (Apple 风格设计)
- Recharts (图表库)
- SWR (数据获取)

---

## 验收标准

1. ✅ 账户概览卡片正确显示所有字段（总权益、可用余额、未实现盈亏、保证金占用）
2. ✅ 净值曲线图表正确绘制（支持时间范围切换）
3. ✅ 盈亏统计卡片颜色正确（正绿负红）
4. ✅ 仓位分布饼图显示各币种占比
5. ✅ TypeScript 类型检查通过
6. ✅ 响应式布局正常

---

## 进度记录

| 日期 | 完成工作 | 状态 |
|------|----------|------|
| 2026-03-31 | 阶段 1-2: 基础组件和图表组件 | ✅ 已完成 |
| 2026-03-31 | 阶段 3: 统计组件创建 | ✅ 已完成 |
| 2026-03-31 | 阶段 4: 主页面开发 | ✅ 已完成 |
| 2026-03-31 | 阶段 5: 路由集成与测试 | ✅ 已完成 |

---

## 交付清单

### 已创建的组件

| 组件 | 文件路径 | 说明 |
|------|----------|------|
| `AccountOverviewCards` | `web-front/src/components/v3/AccountOverviewCards.tsx` | 账户概览卡片（总权益、可用余额、未实现盈亏、保证金占用） |
| `EquityCurveChart` | `web-front/src/components/v3/EquityCurveChart.tsx` | 净值曲线图表（Recharts AreaChart） |
| `PnLStatisticsCards` | `web-front/src/components/v3/PnLStatisticsCards.tsx` | 盈亏统计卡片（日/周/月/总盈亏） |
| `PositionDistributionPie` | `web-front/src/components/v3/PositionDistributionPie.tsx` | 仓位分布饼图 |
| `DateRangeSelector` | `web-front/src/components/v3/DateRangeSelector.tsx` | 日期范围选择器 |
| `Account` | `web-front/src/pages/Account.tsx` | 主页面 |

### TypeScript 编译验证

```bash
npm run build
# ✓ 3425 modules transformed.
# ✓ built in 2.31s
```

**结果**: ✅ 编译通过，无错误

---

## 技术发现

详见 `docs/planning/findings.md` - P6-005 条目

---

# 任务计划 - P6-006: PMS 回测报告组件

> **创建日期**: 2026-03-31
> **负责人**: @frontend
> **优先级**: P0
> **预计工时**: 4 小时

---

## 任务目标

实现 v3.0 PMS 回测报告组件，展示回测结果、交易统计、盈亏分布。

**相关文件**:
- **契约表**: `docs/designs/phase6-v3-api-contract.md` - 回测端点（待补充）
- **类型定义**: `web-front/src/lib/api.ts` - PMSBacktestReport, PositionSummary
- **API 调用**: `runPMSBacktest()` 函数
- **现有组件**: `web-front/src/components/v3/backtest/` - 5 个回测报告组件

---

## 阶段分解

### 阶段 1: API 函数创建 ✅

- [x] `runPMSBacktest()` - PMS 模式回测 API 函数
- [x] PMSBacktestReport 类型定义（已存在）
- [x] PositionSummary 类型定义（已存在）

### 阶段 2: 组件集成 ✅

- [x] `BacktestOverviewCards` - 回测概览卡片（已存在）
- [x] `EquityComparisonChart` - 权益曲线对比图（已存在）
- [x] `TradeStatisticsTable` - 交易统计表格（已存在）
- [x] `PnLDistributionHistogram` - 盈亏分布直方图（已存在）
- [x] `MonthlyReturnHeatmap` - 月度收益热力图（已存在）

### 阶段 3: 主页面开发 ✅

- [x] `PMSBacktest.tsx` - 主页面（/pms-backtest）
- [x] 时间序列与资产维度配置
- [x] 初始资金配置
- [x] 策略组装工作台集成
- [x] 风控参数覆写
- [x] PMS 回测执行功能

### 阶段 4: 报告展示集成 ✅

- [x] 回测概览卡片组件集成
- [x] 权益曲线对比图集成
- [x] 交易统计表格集成
- [x] 盈亏分布直方图集成
- [x] 月度收益热力图集成

### 阶段 5: 路由集成与测试 ✅

- [x] 添加路由到 App.tsx
- [x] 添加导航菜单项到 Layout.tsx
- [x] TypeScript 编译验证
- [x] 页面功能自测

---

## 组件结构

```
web-front/src/pages/PMSBacktest.tsx
web-front/src/components/v3/backtest/
├── BacktestOverviewCards.tsx      # 回测概览卡片（4 张关键指标）
├── EquityComparisonChart.tsx      # 权益曲线对比图（Recharts LineChart）
├── TradeStatisticsTable.tsx       # 交易统计表格（12 项统计）
├── PnLDistributionHistogram.tsx   # 盈亏分布直方图（Recharts BarChart）
├── MonthlyReturnHeatmap.tsx       # 月度收益热力图（正绿负红）
└── index.ts                       # 组件统一导出
```

---

## 技术栈

- React 19 + TypeScript + Vite 6.x
- TailwindCSS 4.x (Apple 风格设计)
- Recharts (图表库)
- SWR (数据获取)

---

## 验收标准

1. ✅ 回测概览卡片正确显示所有指标（总收益率、最大回撤、夏普比率、胜率）
2. ✅ 权益曲线对比图正确绘制（策略净值 vs 基准）
3. ✅ 交易统计表格数据完整（12 项统计数据）
4. ✅ 盈亏分布直方图可视化正确
5. ✅ 月度收益热力图颜色正确（正绿负红）
6. ✅ TypeScript 类型检查通过
7. ✅ 路由和导航菜单正确配置

---

## 进度记录

| 日期 | 完成工作 | 状态 |
|------|----------|------|
| 2026-03-31 | 阶段 1: API 函数创建 | ✅ 已完成 |
| 2026-03-31 | 阶段 2: 组件集成 | ✅ 已完成 |
| 2026-03-31 | 阶段 3: 主页面开发 | ✅ 已完成 |
| 2026-03-31 | 阶段 4: 报告展示集成 | ✅ 已完成 |
| 2026-03-31 | 阶段 5: 路由集成与测试 | ✅ 已完成 |

---

## 交付清单

### 已创建/更新的文件

| 文件 | 修改内容 | 状态 |
|------|----------|------|
| `web-front/src/lib/api.ts` | 新增 `runPMSBacktest()` API 函数 | ✅ 已更新 |
| `web-front/src/pages/PMSBacktest.tsx` | 新建 PMS 回测主页面 | ✅ 已创建 |
| `web-front/src/App.tsx` | 添加 `/pms-backtest` 路由 | ✅ 已更新 |
| `web-front/src/components/Layout.tsx` | 添加 PMS 回测导航菜单项 | ✅ 已更新 |
| `docs/planning/findings.md` | 记录 P6-006 技术发现 | ✅ 已更新 |
| `docs/planning/task_plan.md` | 更新任务进度状态 | ✅ 已更新 |

### 已创建的组件

**本次任务前已存在**:
| 组件 | 文件路径 | 说明 |
|------|----------|------|
| `BacktestOverviewCards` | `web-front/src/components/v3/backtest/BacktestOverviewCards.tsx` | 回测概览卡片（总收益率、最大回撤、夏普比率、胜率） |
| `EquityComparisonChart` | `web-front/src/components/v3/backtest/EquityComparisonChart.tsx` | 权益曲线对比图（Recharts LineChart） |
| `TradeStatisticsTable` | `web-front/src/components/v3/backtest/TradeStatisticsTable.tsx` | 交易统计表格（12 项统计） |
| `PnLDistributionHistogram` | `web-front/src/components/v3/backtest/PnLDistributionHistogram.tsx` | 盈亏分布直方图（Recharts BarChart） |
| `MonthlyReturnHeatmap` | `web-front/src/components/v3/backtest/MonthlyReturnHeatmap.tsx` | 月度收益热力图（正绿负红） |

**本次任务创建**:
| 组件 | 文件路径 | 说明 |
|------|----------|------|
| `PMSBacktest` | `web-front/src/pages/PMSBacktest.tsx` | PMS 回测主页面 |

### TypeScript 编译验证

```bash
cd web-front && npm run build

> react-example@0.0.0 build
> vite build

✓ 3432 modules transformed.
✓ built in 2.02s
```

**结果**: ✅ 编译通过，无错误

---

## 技术发现

详见 `docs/planning/findings.md` - P6-006 条目

---

*最后更新：2026-03-31*

---

# 任务计划 - P6-005 账户净值曲线可视化

> **创建日期**: 2026-03-31
> **负责人**: @frontend
> **优先级**: P1
> **预计工时**: 4 小时

---

## 任务目标

实现 v3.0 仓位管理页面，显示持仓列表、详情、平仓操作。

**相关文件**:
- **契约表**: `docs/designs/phase6-v3-api-contract.md` Section 2.4
- **类型定义**: `web-front/src/types/order.ts` - PositionInfo, PositionResponse
- **API 调用**: P6-002 的 `fetchPositions()`, `closePosition()` 函数
- **参考页面**: `web-front/src/pages/Signals.tsx` - 表格组件模式

---

# 任务计划 - P6-007 多级别止盈可视化

> **创建日期**: 2026-03-31
> **负责人**: @frontend
> **优先级**: P1
> **预计工时**: 2 小时

---

## 任务目标

在仓位详情页实现多级别止盈（TP1-TP5）可视化展示和 SL 止损订单展示。

**相关文件**:
- **契约表**: `docs/designs/phase6-v3-api-contract.md` Section 2.4 PositionInfo
- **类型定义**: `web-front/src/types/order.ts` - OrderInfo, Tag
- **依赖组件**: P6-003 已创建的 `PositionDetailsDrawer.tsx`

---

## 阶段分解

### 阶段 1: 基础组件创建 ✅

- [x] `TPProgressBar.tsx` - 单个 TP 订单进度条组件（成交进度、盈亏比例）
- [x] `TakeProfitStats.tsx` - 止盈统计卡片组件（已实现/未实现/总目标止盈）

### 阶段 2: 详情组件增强 ✅

- [x] `TPChainDisplay.tsx` - 集成 TPProgressBar 和 TakeProfitStats，支持 TP1-TP5 可视化
- [x] `SLOrderDisplay.tsx` - 新增止损距离百分比、止损进度条可视化

### 阶段 3: 与仓位详情页集成 ✅

- [x] `PositionDetailsDrawer.tsx` - 已集成 TPChainDisplay 和 SLOrderDisplay 组件

### 阶段 4: TypeScript 编译验证 ✅

- [x] TypeScript 编译验证通过

---

## 组件结构

```
web-front/src/components/v3/
├── TPChainDisplay.tsx          # 止盈订单链展示（TP1-TP5 列表 + 进度条）
├── SLOrderDisplay.tsx          # 止损订单展示（触发价、距离、进度条）
├── TPProgressBar.tsx           # 单个 TP 订单进度条
├── TakeProfitStats.tsx         # 止盈统计卡片
├── PositionDetailsDrawer.tsx   # 仓位详情抽屉（已集成上述组件）
└── ...其他组件
```

---

## 技术栈

- React 19 + TypeScript + Vite 6.x
- TailwindCSS 4.x (Apple 风格设计)
- Lucide React (图标)

---

## 验收标准

1. ✅ TP1-TP5 订单信息正确显示
2. ✅ 止盈进度条可视化正确（0-100%）
3. ✅ 止损距离百分比计算正确
4. ✅ 止盈统计数据显示完整
5. ✅ TypeScript 类型检查通过
6. ✅ 与仓位详情页无缝集成

---

## 进度记录

| 日期 | 完成工作 | 状态 |
|------|----------|------|
| 2026-03-31 | 阶段 1-2: 基础组件和详情组件增强 | ✅ 已完成 |
| 2026-03-31 | 阶段 3: 与仓位详情页集成 | ✅ 已完成 |
| 2026-03-31 | 阶段 4: TypeScript 编译验证 | ✅ 已完成 |

---

## 交付清单

### 已创建/增强的组件

| 组件 | 文件路径 | 说明 |
|------|----------|------|
| `TPProgressBar` | `web-front/src/components/v3/TPProgressBar.tsx` | 单个 TP 订单进度条（成交进度、盈亏比例） |
| `TakeProfitStats` | `web-front/src/components/v3/TakeProfitStats.tsx` | 止盈统计卡片（已实现/未实现/总目标止盈） |
| `TPChainDisplay` (增强) | `web-front/src/components/v3/TPChainDisplay.tsx` | 集成 TPProgressBar 和 TakeProfitStats |
| `SLOrderDisplay` (增强) | `web-front/src/components/v3/SLOrderDisplay.tsx` | 新增止损距离百分比、止损进度条 |

### TypeScript 编译验证

```bash
npm run build
# ✓ 3425 modules transformed.
# ✓ built in 2.36s
```

**结果**: ✅ 编译通过，无错误

---

## 技术发现

详见 `docs/planning/findings.md` - P6-007 条目

---

## 阶段分解

### 阶段 1: 基础组件创建 ✅

- [x] `DirectionBadge.tsx` - 方向徽章组件（已存在）
- [x] `PnLBadge.tsx` - 盈亏徽章组件（已存在）
- [x] `PositionsTable.tsx` - 仓位列表表格组件
- [x] `ClosePositionModal.tsx` - 平仓确认对话框组件

### 阶段 2: 详情组件创建 ✅

- [x] `PositionDetailsDrawer.tsx` - 仓位详情抽屉组件
- [x] `TPChainDisplay.tsx` - 止盈订单链展示组件
- [x] `SLOrderDisplay.tsx` - 止损订单展示组件

### 阶段 3: 主页面开发 ✅

- [x] `Positions.tsx` - 主页面（/v3/positions）
- [x] 仓位列表功能
- [x] 筛选器（币种对、已平仓/未平仓）
- [x] 点击仓位 ID 查看详情

### 阶段 4: 平仓功能集成 ✅

- [x] 平仓 API 调用集成
- [x] 支持全部平仓和部分平仓
- [x] 平仓订单类型选择（MARKET/LIMIT）
- [x] 平仓结果反馈（成功/失败）

### 阶段 5: 路由集成与测试 🔄

- [ ] 添加路由到 App.tsx
- [ ] TypeScript 编译验证
- [ ] 页面功能自测

---

## 组件结构

```
web-front/src/pages/Positions.tsx
web-front/src/components/v3/
├── PositionsTable.tsx
├── PositionDetailsDrawer.tsx
├── ClosePositionModal.tsx
├── TPChainDisplay.tsx
├── SLOrderDisplay.tsx
├── PnLBadge.tsx         # 已存在
└── DirectionBadge.tsx   # 已存在
```

---

## 技术栈

- React 19 + TypeScript + Vite 6.x
- TailwindCSS 4.x (Apple 风格设计)
- SWR (数据获取)
- Lucide React (图标)

---

## 验收标准

1. ✅ 仓位列表正确显示所有字段
2. ✅ 盈亏和方向徽章颜色正确
3. ✅ 平仓功能完整（确认→下单→结果反馈）
4. ✅ TypeScript 类型检查通过
5. ✅ 响应式布局正常

---

## 进度记录

| 日期 | 完成工作 | 状态 |
|------|----------|------|
| 2026-03-31 | 阶段 1-2: 基础组件和详情组件 | ✅ 已完成 |
| 2026-03-31 | 阶段 3: 主页面开发 | ✅ 已完成 |
| 2026-03-31 | 阶段 4: 平仓功能集成 | ✅ 已完成 |
| 2026-03-31 | 阶段 5: 路由集成与测试 | ✅ 已完成 |

---

## 交付清单

### 已创建的组件

| 组件 | 文件路径 | 说明 |
|------|----------|------|
| `PositionsTable` | `web-front/src/components/v3/PositionsTable.tsx` | 仓位列表表格组件 |
| `PositionDetailsDrawer` | `web-front/src/components/v3/PositionDetailsDrawer.tsx` | 仓位详情抽屉组件 |
| `ClosePositionModal` | `web-front/src/components/v3/ClosePositionModal.tsx` | 平仓确认对话框 |
| `TPChainDisplay` | `web-front/src/components/v3/TPChainDisplay.tsx` | 止盈订单链展示 |
| `SLOrderDisplay` | `web-front/src/components/v3/SLOrderDisplay.tsx` | 止损订单展示 |
| `Positions` | `web-front/src/pages/Positions.tsx` | 主页面 |

### 已更新的文件

| 文件 | 修改内容 |
|------|----------|
| `web-front/src/App.tsx` | 添加 `/positions` 路由 |
| `web-front/src/components/Layout.tsx` | 添加导航菜单项（仓位） |
| `docs/planning/findings.md` | 记录 P6-003 技术发现 |
| `docs/planning/task_plan.md` | 更新进度状态 |

### TypeScript 编译验证

```
✓ 2781 modules transformed.
✓ built in 1.44s
```

**结果**: ✅ 编译通过，无错误

---

## 技术发现

详见 `docs/planning/findings.md` - P6-003 条目

---

*最后更新：2026-03-31*
