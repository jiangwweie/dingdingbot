# 任务计划 - P6-003 仓位管理页面开发

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
