# 盯盘狗系统整体进度与后续规划总览

**统计日期**: 2026-03-31
**当前版本**: v2.0 (多交易所支持完成)
**下一版本**: v3.0 (PMS 仓位中心模型) - Phase 1-5 已完成

---

## 一、系统整体进度总览

### 1.1 已完成功能模块

| 模块 | 功能 | 状态 | 成熟度 | Git 提交 |
|------|------|------|--------|---------|
| **数据采集** | WebSocket 实时 K 线 (Binance/Bybit/OKX) | ✅ 完成 | 成熟 | `0e214af` |
| **策略引擎** | 递归逻辑树 (AST) + 多策略并行 | ✅ 完成 | 成熟 | `6943b80` |
| **触发器** | Pinbar, Engulfing, Doji, Hammer | ✅ 完成 | 成熟 | - |
| **过滤器** | EMA, MTF, ATR, Volume Surge, Volatility, Time, Price Action | ✅ 完成 | 成熟 | `3c60ae2` |
| **风控计算** | 止损计算、多级别止盈、仓位试算 | ✅ 完成 | 成熟 | `1aa9619` |
| **信号覆盖** | 更优信号自动替代旧信号 | ✅ 完成 | 成熟 | `da0ffd3` |
| **回测沙箱** | 历史回测、策略预览、时间范围支持 | ✅ 完成 | 成熟 | `4ae99ce` |
| **通知推送** | 飞书/企业微信/Telegram 多模板 | ✅ 完成 | 成熟 | `20588f9` |
| **信号持久化** | SQLite 存储、全生命周期跟踪 | ✅ 完成 | 成熟 | - |
| **前端工作台** | 递归表单渲染、策略拼装 | ✅ 完成 | 成熟 | - |
| **配置管理** | 热重载、快照版本化 | ✅ 完成 | 成熟 | `4f0cff2` |
| **日志系统** | 文件轮转、脱敏、溯源追踪 | ✅ 完成 | 成熟 | - |
| **容器化** | Docker Compose 一键部署 | ✅ 完成 | 成熟 | `bf7c139` |
| **多交易所** | Binance/Bybit/OKX 配置驱动切换 | ✅ 完成 | 成熟 | `0e214af` |

### 1.2 测试覆盖状态

| 测试类型 | 通过数 | 失败数 | 覆盖率 | 状态 |
|---------|--------|--------|--------|------|
| 单元测试 | 400+ | 0 | 90%+ | ✅ 优秀 |
| 集成测试 | 90+ | 0 | 85%+ | ✅ 优秀 |
| E2E 测试 | 待补充 | - | - | ⏳ 待完善 |

---

## 二、待完成功能规划

### 2.1 🚫 P0/P1/P2 优先级任务（全部废弃）

**状态**: ❌ **全部废弃** - 2026-03-30

**废弃说明**: 除 v3 迁移外，所有待办事项全部废弃。团队资源集中投入到 v3.0 迁移。

| 优先级 | 任务 | 状态 | 整合到 v3 阶段 |
|--------|------|------|--------------|
| ~~P0~~ | ~~止盈追踪逻辑~~ | ❌ 已废弃 | v3 Phase 3: 风控状态机 |
| ~~P1~~ | ~~可视化 - 逻辑路径~~ | ❌ 已废弃 | v3 Phase 6: 前端适配 |
| ~~P1~~ | ~~可视化 - 资金监控~~ | ❌ 已废弃 | v3 Phase 6: 前端适配 |
| ~~P2~~ | ~~性能统计~~ | ❌ 已废弃 | v3 Phase 6: 前端适配 |

---

### 2.2 🎯 v3.0 迁移（当前首要目标）

**状态更新 (2026-03-31)**: Phase 1-5 已完成，系统性审查 100% 通过

| 阶段 | 名称 | 工期 | 开始日期 | 结束日期 | 核心交付物 | 状态 |
|------|------|------|----------|----------|-----------|------|
| Phase 0 | v3 准备 | 1 周 | 2026-05-06 | 2026-05-13 | Alembic 选型、Schema 设计 | ⏳ 待启动 |
| Phase 1 | 模型筑基 | 2 周 | 2026-03-28 | 2026-03-30 | Order/Position/Account 模型 | ✅ 已完成 |
| Phase 2 | 撮合引擎 | 3 周 | 2026-03-30 | 2026-03-30 | MockMatchingEngine、回测对比 | ✅ 已完成 |
| Phase 3 | 风控状态机 | 2 周 | 2026-03-30 | 2026-03-30 | DynamicRiskManager、Trailing Stop | ✅ 已完成 |
| Phase 4 | 订单编排 | 2 周 | 2026-03-30 | 2026-03-30 | OrderManager、SignalToOrderAdapter | ✅ 已完成 |
| Phase 5 | 实盘集成 | 3 周 | 2026-03-30 | 2026-03-31 | CCXT 订单管理、WebSocket 推送 | ✅ 已完成 |
| Phase 6 | 前端适配 | 2 周 | 2026-08-11 | 2026-08-24 | 仓位管理页面、净值曲线 | ⏳ 待启动 |

**Phase 1-5 审查结果**:
- 审查项：57/57 通过 (100%)
- 单元测试：241/241 通过 (100%)
- 审查报告：`docs/reviews/phase1-5-comprehensive-review-report.md`

**总工期**: 14 周（3.5 个月）- Phase 1-5 提前完成

---

### 2.3 🎯 Phase 5 实盘集成（2026-03-31 完成）

**状态**: ✅ 编码完成，系统性审查 100% 通过

**审查报告**:
- ✅ `docs/reviews/phase1-5-comprehensive-review-report.md` - Phase 1-5 系统性审查 (57 项 100% 通过)
- ✅ `docs/reviews/phase5-code-review.md` - Phase 5 专项审查 (10 个问题全部修复)

**核心交付物**:
| 模块 | 文件 | 测试数 | 状态 |
|------|------|--------|------|
| ExchangeGateway | `src/infrastructure/exchange_gateway.py` | 66 | ✅ |
| PositionManager | `src/application/position_manager.py` | 27 | ✅ |
| CapitalProtection | `src/application/capital_protection.py` | 21 | ✅ |
| DcaStrategy | `src/domain/dca_strategy.py` | 30 | ✅ |
| Reconciliation | `src/application/reconciliation.py` | 15 | ✅ |
| Pydantic 模型 | `src/domain/models.py` | 27 | ✅ |
| 前端类型 | `gemimi-web-front/src/types/order.ts` | 45 | ✅ |

**核心设计决策**:
| 决策项 | 决策结果 |
|--------|----------|
| 交易所支持 | Binance (测试网 + 生产网) |
| 数据库策略 | SQLite (开发) / PostgreSQL (测试 + 生产) |
| 服务器位置 | 东京 AWS (预留香港切换) |
| 告警渠道 | 飞书 Webhook |
| DCA 分批建仓 | Phase 5 实现 (2-5 批次) |
| 资金保护 | 单笔 2% / 每日 5% / 仓位 20% |
| 并发保护 | Asyncio Lock + DB 行锁 (双层) |

**Gemini 审查问题修复**: 4 个关键问题全部修复 ✅
- G-001: asyncio.Lock 释放后使用 → WeakValueDictionary
- G-002: 市价单价格缺失 → fetch_ticker_price
- G-003: DCA 限价单吃单陷阱 → place_all_orders_upfront
- G-004: 对账幽灵偏差 → 10 秒 Grace Period

**测试结果**:
- Phase 5 单元测试：110/110 通过 (100%)
- Phase 1-5 总计：241/241 通过 (100%)

**用户确认事项**:
- ✅ 测试网 API 密钥已准备好
- ✅ 东京 AWS 服务器已备好
- ⏳ 飞书 Webhook URL 待配置
- ⏳ Binance Testnet E2E 集成测试待执行

---

## 三、架构升级对比

### 3.1 v2.0 vs v3.0 核心差异

| 维度 | v2.0 (当前) | v3.0 (目标) | 变化说明 |
|------|------------|------------|---------|
| **核心抽象** | SignalResult | Order + Position | 新增执行层和状态层 |
| **账户模型** | AccountSnapshot (只读) | Account (主动累积) | 从快照变为记账 |
| **回测引擎** | 简化胜率模拟 | 极端悲观撮合 | 增加滑点/手续费模拟 |
| **止盈处理** | take_profit_levels 字段 | 独立 Order_TP1 订单 | 字段→实体 |
| **止损处理** | 简化止损距离判断 | Order_SL 条件单 + Trailing | 静态→动态 |
| **仓位追踪** | 无 | Position.current_qty 动态缩减 | 新增 PMS |
| **盈亏追踪** | 无 | Position.realized_pnl 累积 | 新增 PMS |

### 3.2 兼容性策略

| 模块 | 兼容性 | 迁移方式 |
|------|--------|---------|
| Pydantic v2 + Decimal | ✅ 完全兼容 | 无需修改 |
| KlineData/StrategyEngine | ✅ 完全兼容 | 直接复用 |
| SignalResult | ⚠️ 部分兼容 | 保留用于通知，新增 Signal 实体 |
| Direction 枚举 | ⚠️ 需迁移 | 数据库 UPDATE + Alembic |
| SignalRepository | ⚠️ 需扩展 | 新增 orders/positions/accounts 表 |

---

## 四、技术债务清单

| 编号 | 问题 | 严重性 | 修复计划 | 状态 |
|------|------|--------|---------|------|
| #TP-1 | 回测分批止盈模拟未实现 | 低 | v3 Phase 2 | ❌ 整合到 v3 |
| #2 | 立即测试无高周期数据预热 | 中 | deferred | ⏸️ 暂缓 |
| #3 | 冷却缓存固定 4 小时 | 中 | 已废弃 (S6-2 替代) | ❌ 已废弃 |

---

## 五、风险与缓解措施

| 风险 | 概率 | 影响 | 等级 | 缓解措施 | 负责人 |
|------|------|------|------|---------|--------|
| 并发脏写 | 高 | 高 | 🔴 高 | Asyncio Lock + 数据库行级锁 | 后端 |
| 实盘订单状态不同步 | 中 | 高 | 🟡 中 | 启动时对账 + WebSocket 心跳 | 后端 |
| 回测结果差异过大 | 中 | 中 | 🟡 中 | 双模式对比 + 差异分析报告 | QA |
| 迁移工期超期 | 中 | 中 | 🟡 中 | 每周进度 Review + 灵活调整 | PM |
| 前端用户体验降级 | 低 | 中 | 🟢 低 | 灰度发布 + 用户反馈收集 | 前端 |

---

## 六、里程碑检查点

| 里程碑 | 日期 | 检查内容 | 通过标准 | 状态 |
|--------|------|---------|---------|------|
| ~~M-P0~~ | ~~2026-04-07~~ | ~~止盈追踪完成~~ | ❌ **已废弃** (整合到 v3 Phase 3) | ❌ |
| M1 | 2026-03-30 | Phase 1 完成 | 新模型 + 数据库迁移通过 | ✅ 已完成 |
| M2 | 2026-03-30 | Phase 2 完成 | MockMatchingEngine、回测对比 | ✅ 已完成 |
| M3 | 2026-03-30 | Phase 3 完成 | DynamicRiskManager、Trailing Stop | ✅ 已完成 |
| M4 | 2026-03-30 | Phase 4 完成 | OrderManager、订单编排端到端测试 | ✅ 已完成 |
| M5 | 2026-03-31 | Phase 5 完成 | 实盘集成代码 + 系统性审查 100% 通过 | ✅ 已完成 |
| M6 | 2026-08-11 | Phase 6 前端适配 | 仓位管理页面、净值曲线 | ⏳ 待启动 |
| M7 | 2026-05-05 | Phase 0 v3 准备 | Alembic 选型、数据库 Schema 设计 | ⏳ 待启动 |
| M8 | 2026-08-24 | E2E 集成测试 | Binance Testnet 实盘模拟 | ⏳ 待启动 |

---

## 七、团队分工

| 角色 | Phase 1-3 | Phase 4-5 | Phase 6 |
|------|----------|----------|--------|
| 后端开发 | 2 人 | 2 人 | 0.5 人 |
| 前端开发 | 0 | 0.5 人 | 1 人 |
| QA 测试 | 0.5 人 | 1 人 | 1 人 |
| 架构师 | 0.5 人 | 0.5 人 | 0.5 人 |

---

## 八、质量保障要求

### 8.1 代码审查红线

| 检查项 | 标准 | 工具 |
|--------|------|------|
| 领域层纯净性 | domain/ 无 I/O 依赖 | grep ccxt/aiohttp |
| 金融精度 | 所有金额用 Decimal | 类型检查 |
| 并发安全 | 仓位修改加锁 | Code Review |
| 日志脱敏 | API 密钥 mask_secret() | 日志审计 |

### 8.2 测试覆盖要求

| 模块 | 覆盖率要求 | 测试类型 |
|------|-----------|---------|
| 撮合引擎 | 100% | 单元测试 + 边界 case |
| 风控状态机 | 100% | 单元测试 + 状态转移 |
| 订单编排 | 95% | 单元测试 + 集成测试 |
| 实盘集成 | 90% | E2E 测试 + 模拟盘 |

---

## 九、文档索引

| 文档 | 位置 | 状态 |
|------|------|------|
| Gemini 讨论技术文档 | `docs/GEMINI_DISCUSSION_DOC.md` | ✅ 已完成 |
| v3 迁移分析报告 | `docs/v3/v3-migration-analysis-report.md` | ✅ 已完成 |
| v3 演进路线图 | `docs/v3/v3-evolution-roadmap.md` | 🔄 待更新 |
| 任务计划 | `docs/planning/task_plan.md` | 🔄 待更新 |
| 进度日志 | `docs/planning/progress.md` | ✅ 已更新 |
| Phase 1 完成报告 | `docs/v3/v3-phase1-complete-report.md` | ✅ 已完成 |
| Phase 2 完成报告 | `docs/v3/v3-phase2-complete-report.md` | ✅ 已完成 |
| Phase 3 完成报告 | `docs/v3/v3-phase3-complete-report.md` | ✅ 已完成 |
| Phase 4 完成报告 | `docs/v3/v3-phase4-complete-report.md` | ✅ 已完成 |
| Phase 1-5 审查报告 | `docs/reviews/phase1-5-comprehensive-review-report.md` | ✅ 已完成 |
| Phase 5 审查报告 | `docs/reviews/phase5-code-review.md` | ✅ 已完成 |

---

## 十、Git 提交历史（最近 20 条）

```
11bba9a docs: Phase 1-5 系统性代码审查完成（57 项 100% 通过）
cd2c0af docs: 更新 2026-03-31 进度日志
054e8b1 docs: 更新契约表 OrderRole 枚举为 v3.0 PMS 精细定义
38ae1a9 docs: 更新 Phase 5 审查报告状态为全部修复
9b611d6 docs: 更新 Phase 1-4 验证完成状态
dc76346 fix(v3): 更新 CHECK 约束以匹配演化的枚举值
63d9514 feat(phase5): 审查问题修复 - 补充契约表定义的模型和类型 (P5-001~P5-007)
b9939f0 docs: 将 planning-with-files 标准写入 agent 准则
3db2d03 docs: 更新 Phase 5 进度日志（编码完成，待审查修复）
57eacd3 feat(phase5): 实盘集成核心功能实现（审查中）
8e1d1cd misc: 添加测试覆盖率和记忆文件
b73892d misc: 异常体系扩展、CLAUDE.md 更新、依赖修正
3f9878e feat(v3): Phase 1 模型筑基 - ORM 模型与数据库迁移
6efb3fd docs: v3 迁移文档补充
ae8ae06 docs: Phase 5 实盘集成设计完成 (v1.3)
c2b22f3 feat(v3): Phase 4 订单编排实现
bd6ddc8 docs: 创建 Phase 3 完成报告
629c759 feat(v3): Phase 3 风控状态机实现
8680bdb feat(v3): Phase 2 撮合引擎实现
af6fc56 docs: 整合 v3 规划到统一项目计划
```

---

## 十一、下一步行动

### 🎯 当前首要目标：Binance Testnet E2E 集成测试

**Phase 1-5 已完成**,系统性审查 100% 通过，下一步执行实盘集成测试：

- [ ] Binance Testnet API 密钥配置
- [ ] 飞书 Webhook URL 配置
- [ ] E2E 测试场景设计
  - [ ] 入场开仓 → TP1 止盈 → 剩余打损
  - [ ] 入场开仓 → SL 止损
  - [ ] 多单并行处理
  - [ ] 并发保护验证（TP1/SL 同时触发）
- [ ] 对账服务验证
- [ ] 飞书告警推送验证

### Phase 0: v3 迁移准备（2026-05-06 启动）

- [ ] Alembic 技术调研
- [ ] 数据库 Schema 设计（orders/positions/accounts 表）
- [ ] Phase 1 详细任务分解
- [ ] 开发环境搭建（SQLite + PostgreSQL）

---

**当前状态**: 🟢 v3 迁移准备中

**下次审查日期**: 2026-05-05（v3 启动前）

---

*盯盘狗 🐶 项目组*
*2026-03-30*
