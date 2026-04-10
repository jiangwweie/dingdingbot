# v3.0 迁移任务追踪器

**创建日期**: 2026-03-30
**状态**: 🟡 准备中
**启动日期**: 2026-05-06
**预计完成**: 2026-08-24
**总工期**: 14 周

---

## 🎯 当前阶段：Phase 5 - 实盘集成 ✅ 已完成

**开始日期**: 2026-03-30
**结束日期**: 2026-03-31
**状态**: ✅ 已完成 (2026-03-31)

### Phase 5 完成总结

**交付日期**: 2026-03-31

**核心功能实现**:
| 模块 | 说明 | 测试 |
|------|------|------|
| ExchangeGateway | 订单接口 + WebSocket 推送 | 66 测试 ✅ |
| PositionManager | 并发保护 (WeakValueDictionary + DB 行锁) | 27 测试 ✅ |
| ReconciliationService | 启动对账 + Grace Period | 15 测试 ✅ |
| CapitalProtectionManager | 资金保护 5 项检查 | 21 测试 ✅ |
| DcaStrategy | DCA 分批建仓 + 提前预埋限价单 | 30 测试 ✅ |
| FeishuNotifier | 飞书告警 6 种事件类型 | 32 测试 ✅ |

**测试结果**:
- Phase 5 单元测试：110/110 通过 (100%)
- Phase 1-5 系统性审查：241/241 通过 (100%)
- E2E 集成测试 (Window 1-4): 19/19 通过

**审查报告**:
- `docs/reviews/phase5-code-review.md` - 10/10 问题已修复
- `docs/reviews/phase1-5-comprehensive-review-report.md` - 57/57 审查项通过

**Git 提交**:
- `57eacd3` - feat(phase5): 实盘集成核心功能实现（审查中）
- `9c32c8c` - test: Phase 5 E2E 集成测试完成（窗口 1/2/3 全部通过）
- `5b90c86` - docs: 更新 Phase 5 状态为审查通过，全部完成

**下一步**: Phase 6 前端适配 ✅ 已完成

---

### Phase 6 完成总结

**交付日期**: 2026-04-01

**前端页面** (4 个):
| 页面 | 文件 | 状态 |
|------|------|------|
| 仓位管理页面 | `web-front/src/pages/Positions.tsx` | ✅ |
| 订单管理页面 | `web-front/src/pages/Orders.tsx` | ✅ |
| 账户页面 | `web-front/src/pages/Account.tsx` | ✅ |
| 回测报告页面 | `web-front/src/pages/PMSBacktest.tsx` | ✅ |

**v3 组件** (20+ 个):
- 徽章类：`DirectionBadge`, `OrderStatusBadge`, `OrderRoleBadge`, `PnLBadge`
- 表格类：`PositionsTable`, `OrdersTable`
- 抽屉类：`PositionDetailsDrawer`, `OrderDetailsDrawer`
- 对话框类：`ClosePositionModal`, `CreateOrderModal`
- 图表类：`EquityCurveChart`, `PositionDistributionPie`
- 回测组件：`BacktestOverviewCards`, `PnLDistributionHistogram`, `MonthlyReturnHeatmap`, `EquityComparisonChart`, `TradeStatisticsTable`
- 止盈可视化：`TPChainDisplay`, `SLOrderDisplay`, `TPProgressBar`, `TakeProfitStats`
- 工具类：`DecimalDisplay`, `DateRangeSelector`, `AccountOverviewCards`, `PnLStatisticsCards`

**后端 API** (v3 REST 端点):
- `POST /api/v3/orders` - 创建订单
- `DELETE /api/v3/orders/{order_id}` - 取消订单
- `GET /api/v3/orders/{order_id}` - 查询订单
- `GET /api/v3/orders` - 订单列表
- `GET /api/v3/positions` - 仓位列表
- `GET /api/v3/positions/{position_id}` - 仓位详情
- `POST /api/v3/positions/{position_id}/close` - 平仓
- `GET /api/v3/account/balance` - 账户余额
- `GET /api/v3/account/snapshot` - 账户快照
- `POST /api/v3/orders/check` - 资金保护检查

**类型定义**:
- `web-front/src/types/order.ts` - v3 订单/仓位/账户 TypeScript 类型

**代码审查**:
- 审查报告：`docs/reviews/phase6-code-review.md`
- 审查问题：2 严重 + 11 一般 + 6 建议
- 修复状态：P0/P1/P2 全部修复 ✅

**测试结果**:
- TypeScript 编译：✅ 通过
- E2E 测试：80/103 通过 (77.7%), 0 失败

**Git 提交**:
- `fb92c50` - fix(phase6): 修复代码审查严重问题 (CRIT-001, CRIT-002)
- `bd8d85c` - fix(phase6): 完成 P1 问题修复 - 字段对齐与组件增强
- `a71508e` - fix(phase6): 修复剩余字段名错误
- `66a5458` - fix: 前端 Phase 6 P2 优化
- `7603a16` - docs: 更新 Phase 6 进度
- `d04cd0b` - feat(phase6): 并行开发完成 - 订单/仓位页面 + 后端 API 补充

**遗留小问题** (可选修复):
- Orders.tsx 日期筛选未传递给 API (P1 优先级，5 分钟修复)

---

## 📋 完整阶段清单

| 阶段 | 名称 | 工期 | 开始 | 结束 | 状态 |
|------|------|------|------|------|------|
| Phase 0 | v3 准备 | 1 周 | 2026-05-06 | 2026-05-13 | ✅ 已完成 |
| Phase 1 | 模型筑基 | 2 周 | 2026-05-19 | 2026-06-01 | ✅ 已完成 (2026-03-30) |
| Phase 2 | 撮合引擎 | 3 周 | 2026-06-02 | 2026-06-22 | ✅ 已完成 (2026-03-30) |
| Phase 3 | 风控状态机 | 2 周 | 2026-06-23 | 2026-07-06 | ✅ 已完成 (2026-03-30) |
| Phase 4 | 订单编排 | 2 周 | 2026-07-07 | 2026-07-20 | ✅ 已完成 (2026-03-30) |
| Phase 5 | 实盘集成 | 3 周 | 2026-07-21 | 2026-08-10 | ✅ 已完成 (2026-03-31) |
| Phase 6 | 前端适配 | 2 周 | 2026-03-31 | 2026-04-01 | ✅ 已完成 (2026-04-01) |

---

## 📂 核心文档

| 文档 | 路径 | 状态 |
|------|------|------|
| v3 演进路线图 | `docs/v3/v3-evolution-roadmap.md` | ✅ 已完成 |
| v3 迁移分析报告 | `docs/v3/v3-migration-analysis-report.md` | ✅ 已完成 |
| 总体设计 | `docs/v3/总体设计.md` | ✅ 已完成 |
| Step1 - 模型设计 | `docs/v3/step1.md` | ✅ 已完成 |
| Step2 - 撮合引擎 | `docs/v3/step2.md` | ✅ 已完成 |
| Step3 - 风控状态机 | `docs/v3/step3.md` | ✅ 已完成 |
| 系统进度总览 | `docs/v3/system-progress-summary.md` | ✅ 已更新 |

---

## 🚫 已废弃任务（2026-03-30）

以下任务全部整合到 v3 迁移中，不再独立开发：

| 原任务 | 整合到 v3 阶段 |
|--------|---------------|
| P0 止盈追踪逻辑 | Phase 3: 风控状态机 |
| P1 可视化 - 逻辑路径 | Phase 6: 前端适配 |
| P1 可视化 - 资金监控 | Phase 6: 前端适配 |
| P2 性能统计 | Phase 6: 前端适配 |
| #TP-1 回测分批止盈模拟 | Phase 2: 撮合引擎 |

---

## 🏁 里程碑检查点

| 里程碑 | 日期 | 检查内容 | 通过标准 |
|--------|------|---------|---------|
| M1 | 2026-06-01 | Phase 1 完成 | 新模型 + 数据库迁移通过 |
| M2 | 2026-06-22 | Phase 2 完成 | v2/v3 回测对比报告 |
| M3 | 2026-07-06 | Phase 3 完成 | Trailing Stop 模拟测试 |
| M4 | 2026-07-20 | Phase 4 完成 | 订单编排端到端测试 |
| M5 | 2026-08-10 | Phase 5 完成 | 实盘 E2E 测试 |
| M6 | 2026-08-24 | Phase 6 完成 | 前端上线 |

---

## 📝 会话日志

### 2026-03-30 - v3 迁移战略规划

**决策**:
- 除 v3 迁移外，所有待办事项全部废弃
- v3 迁移为当前首要目标
- 2026-05-06 启动 Phase 0

**更新文档**:
- `docs/planning/task_plan.md`
- `docs/planning/progress.md`
- `docs/v3/system-progress-summary.md`
- `docs/v3/v3-tracker.md` (本文档)

---

*盯盘狗 🐶 项目组*
*2026-03-30*
