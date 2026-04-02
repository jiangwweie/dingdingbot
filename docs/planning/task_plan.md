# 任务计划

> **当前迭代**: 2026-04-02 起  
> **最后更新**: 2026-04-02 (P1 问题系统性修复完成，84 个测试全部通过)

---

## 🎯 当前进行中的任务

### Phase 7: 回测数据本地化 (2026-04-02 启动)

**项目概述**: 将 SQLite 中的 K 线数据运用到回测程序，实现本地数据优先 + 自动补充架构

**状态**: ✅ Phase 7-1 已完成，✅ 回测订单 API 已完成，✅ 代码审查通过，✅ 单元测试通过

**架构设计**:
```
Backtester → HistoricalDataRepository → SQLite (本地优先)
                                      ↓
                              ExchangeGateway (自动补充)
```

**核心组件**:
| 组件 | 职责 | 状态 |
|------|------|------|
| `HistoricalDataRepository` | 数据仓库：统一数据源访问 | ✅ 已完成 |
| `Backtester._fetch_klines()` | 回测引擎：使用新数据仓库 | ✅ 已完成 |
| 回测订单 API | 订单列表/详情/删除 | ✅ 已完成 |

**预期效果**:
- 回测数据读取速度提升 50x (5s → 0.1s)
- Optuna 调参速度提升 60x (2 小时 → 2 分钟)
- 支持离线回测

**详细设计文档**: [2026-04-02-backtest-data-localization-design.md](../superpowers/specs/2026-04-02-backtest-data-localization-design.md)

**Phase 7-1 任务清单**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| T1 | 创建 HistoricalDataRepository | P0 | 2h | ✅ 已完成 |
| T2 | 修改 Backtester._fetch_klines() | P0 | 1h | ✅ 已完成 |
| T3 | 单元测试 | P0 | 2h | ✅ 已完成 (58 个用例，100% 通过) |

**Phase 7-2 任务清单**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| T4 | 集成 ExchangeGateway | P0 | 2h | ✅ 已完成 (降级逻辑) |
| T5 | 数据完整性验证 | P1 | 2h | ☐ 待执行 |
| T6 | 集成测试 | P1 | 2h | ✅ 已完成 (12 个集成测试) |

**Phase 7-3 任务清单**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| T7 | 性能基准测试 | P1 | 1h | ☐ 待执行 |
| T8 | MTF 数据对齐验证 | P1 | 2h | ☐ 待执行 |

**新增任务清单** (回测订单管理):
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| T9 | 回测订单列表 API | P0 | 2h | ✅ 已完成 |
| T10 | 回测订单详情 API | P0 | 1h | ✅ 已完成 |
| T11 | 回测订单删除 API | P1 | 1h | ✅ 已完成 |
| T12 | 订单生命周期流程图 | P1 | 1h | ✅ 已完成 |
| T13 | 代码审查问题修复 | P0 | 1h | ✅ 已完成 |

**P1 问题系统性修复** (2026-04-02):
| ID | 问题描述 | 修复方案 | 状态 |
|----|----------|----------|------|
| P1-001 | BacktestOrderSummary.direction 类型注解不完整 | 从 str 改为 Direction 枚举 | ✅ 已完成 |
| P1-002 | historical_data_repository 日志级别不当 | INFO 改为 DEBUG + 上下文 | ✅ 已完成 |
| P1-003 | 魔法数字 (10, 25) 硬编码 | 新增 BacktestConfig 常量类 | ✅ 已完成 |
| P1-004 | 时间框架映射不完整且多处定义 | 统一从 domain.timeframe_utils 获取 | ✅ 已完成 |
| P1-005 | 删除订单后未级联清理 | 支持 cascade 参数删除子订单 | ✅ 已完成 |
| P1-006 | ORM 风格不一致 (技术债) | 记录到技术债清单，待迁移 | 📝 已记录 |

**交付物**:
- ✅ `src/infrastructure/historical_data_repository.py`
- ✅ `docs/arch/backtest-order-lifecycle.md`
- ✅ API 端点 3 个（列表/详情/删除）
- ✅ 测试文件 4 个（58 个测试用例）
- ✅ 4 个文件修改，144 行新增，48 行删除

---

### PMS 回测问题修复项目 (2026-04-01 启动)

**项目概述**: PMS 回测系统深度问题分析与修复

**当前阶段**: ✅ 阶段 B 已完成，✅ 阶段 C T7 已完成

**阶段 A 完成情况** (后端核心修复):
| 任务 | 状态 | 提交 | 测试 |
|------|------|------|------|
| T1: 修复 MTF 未来函数 | ✅ 已完成 | `36c7563` | 10/10 通过 |
| T2: 修复止盈撮合 (添加滑点) | ✅ 已完成 | - | 18/18 通过 |

**阶段 B 完成情况** (数据持久化):
| 任务 | 状态 | 提交 | 测试 |
|------|------|------|------|
| T3: 创建 orders 表 Alembic 迁移 | ✅ 已完成 | - | 15/15 通过 |
| T4: 实现订单保存逻辑 | ✅ 已完成 | 824bb67 | 17/17 通过 |
| T5: 创建 backtest_reports 表 | ✅ 已完成 | - | 16/16 通过 |
| T6: 实现回测报告保存 | ✅ 已完成 | - | 16/16 通过 |

**阶段 B 交付成果**:
- 迁移文件：004 (orders 表补充字段), 005 (backtest_reports 表)
- Repository: OrderRepository (扩展), BacktestReportRepository (新增)
- 测试覆盖率：90%+ (64 个测试用例)
- 审查报告：`docs/reviews/phaseB-code-review.md` ✅ 批准合并

**阶段 C 完成情况** (前端展示):
| 任务 | 状态 | 提交 | 测试 |
|------|------|------|------|
| T7: 回测记录列表页面 | ✅ 已完成 | `7b2f9b5` | 类型检查通过 |
| T8: 订单详情与 K 线图渲染 | ✅ 已完成 | 前端组件完成 | 构建通过 |
| T9: 回测 API 持久化修复 | ✅ 已完成 | `9b4dc61` | - |

**阶段 C 交付成果**:
- 后端 API: GET /api/v3/backtest/reports (列表), GET /api/v3/backtest/reports/{id} (详情), DELETE /api/v3/backtest/reports/{id} (删除), POST /api/backtest (执行回测 + 保存)
- 前端组件：BacktestReportsTable, BacktestReportsFilters, BacktestReportsPagination
- 前端页面：BacktestReports.tsx
- 类型定义：web-front/src/types/backtest.ts

**完整任务清单**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| T1 | 修复 MTF 未来函数 | P0 | 1h | ✅ 已完成 |
| T2 | 修复止盈撮合 (添加滑点) | P0 | 1h | ✅ 已完成 |
| T3 | 创建 orders 表 Alembic 迁移 | P0 | 0.5h | ✅ 已完成 |
| T4 | 实现订单保存逻辑 | P0 | 2h | ✅ 已完成 |
| T5 | 创建 backtest_reports 表 | P0 | 1h | ✅ 已完成 |
| T6 | 实现回测报告保存 | P0 | 2h | ✅ 已完成 |
| T7 | 回测记录列表页面 | P0 | 3h | ✅ 已完成 |
| T8 | 订单详情与 K 线图渲染 | P0 | 3h | ✅ 已完成 |
| ~~T9~~ | ~~时间段分页获取 (CCXT)~~ | ~~P1~~ | ~~2h~~ | ☐ **可选** |
| ~~T10~~ | ~~删除功能 (单条/批量)~~ | ~~P1~~ | ~~1h~~ | ☐ **可选** |
| ~~T11~~ | ~~同时同向持仓限制~~ | ~~P2~~ | ~~1h~~ | ☐ **可选** |
| ~~T12~~ | ~~权益金检查修复~~ | ~~P2~~ | ~~1h~~ | ☐ **可选** |

**相关文档**:
- [PMS 回测修复计划](pms-backtest-fix-plan.md)
- [PMS 回测需求规格](pms-backtest-requirements.md)

---

## ✅ Phase 6 - 前端适配 (已完成)

**完成日期**: 2026-04-01
**状态**: ✅ 编码完成，审查问题全部修复，E2E 测试通过

**交付页面** (4 个):
| 页面 | 文件 | 状态 |
|------|------|------|
| 仓位管理页面 | `web-front/src/pages/Positions.tsx` | ✅ |
| 订单管理页面 | `web-front/src/pages/Orders.tsx` | ✅ |
| 账户页面 | `web-front/src/pages/Account.tsx` | ✅ |
| 回测报告页面 | `web-front/src/pages/PMSBacktest.tsx` | ✅ |

**v3 组件** (20+ 个):
- 徽章类、表格类、抽屉类、对话框类、图表类、回测组件、止盈可视化组件

**后端 API** (v3 REST 端点):
- 订单管理：创建/取消/查询/列表
- 仓位管理：列表/详情/平仓
- 账户管理：余额/快照/历史快照
- 资金保护：订单预检查

**代码审查**:
- 审查报告：`docs/reviews/phase6-code-review.md`
- 审查问题：2 严重 + 11 一般 + 6 建议
- 修复状态：P0/P1/P2 全部修复 ✅

**测试结果**:
- TypeScript 编译：✅ 通过
- E2E 测试：80/103 通过 (77.7%), 0 失败

**Git 提交**:
- `fb92c50` - 修复代码审查严重问题 (CRIT-001, CRIT-002)
- `bd8d85c` - 完成 P1 问题修复 - 字段对齐与组件增强
- `a71508e` - 修复剩余字段名错误
- `66a5458` - 前端 Phase 6 P2 优化
- `d04cd0b` - 并行开发完成 - 订单/仓位页面 + 后端 API 补充

**遗留小问题** (可选修复):
- Orders.tsx 日期筛选未传递给 API (P1 优先级，5 分钟修复)

---

## ✅ Phase 5 - 实盘集成 (已完成)

**完成日期**: 2026-03-31
**状态**: ✅ 编码完成，审查通过，测试 100% 通过

**交付功能**:
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
- `57eacd3` - feat(phase5): 实盘集成核心功能实现
- `9c32c8c` - test: Phase 5 E2E 集成测试完成
- `5b90c86` - docs: 更新 Phase 5 状态为审查通过，全部完成

---

## ✅ 今日完成事项 (2026-04-01)

### Agentic Workflow 与 MCP 配置

**1. MCP 服务器配置 (8 个)**:
- ✅ sqlite, filesystem, puppeteer, time, duckdb (完全配置)
- ⚠️ telegram, ssh, sentry (需填写真实信息)

**2. 项目技能注册 (7 个)**:
| 技能 | 命令 | 用途 |
|------|------|------|
| team-coordinator | /coordinator | 任务分解与调度 |
| backend-dev | /backend | 后端开发 |
| frontend-dev | /frontend | 前端开发 |
| qa-tester | /qa | 测试专家 |
| code-reviewer | /reviewer | 代码审查 |
| tdd-self-heal | /tdd | TDD 闭环自愈 ⭐ |
| type-precision-enforcer | /type-check | 类型精度检查 ⭐ |

**3. 团队角色技能更新 (5 个)**:
- `team-coordinator/SKILL.md` - MCP 调用指南
- `backend-dev/SKILL.md` - TDD、类型检查
- `frontend-dev/SKILL.md` - UI 设计、E2E 测试
- `qa-tester/SKILL.md` - 测试技能、数据库查询
- `code-reviewer/SKILL.md` - 类型检查、审查脚本

**4. 创建的文档 (5 个)**:
- `.claude/MCP-ORCHESTRATION.md` - MCP 编排配置
- `.claude/MCP-QUICKSTART.md` - MCP 快速开始
- `.claude/MCP-ENV-CONFIG.md` - MCP 环境变量
- `.claude/TEAM-SETUP-SUMMARY.md` - 配置总结
- `.claude/team/QUICK-REFERENCE.md` - 团队速查表

**5. 创建的检查脚本 (2 个)**:
- `scripts/check_float.py` - float 污染检测 (发现 34 处)
- `scripts/check_quantize.py` - TickSize 格式化检查 (通过)

**6. Agentic Workflow 技能设计 (2 个)**:
- `tdd-self-heal/SKILL.md` - TDD 闭环自愈
- `type-precision-enforcer/SKILL.md` - 类型精度宪兵

### P0-005 Binance Testnet 完整验证
| 任务 | 说明 | 状态 |
|------|------|------|
| P0-005-1 | 测试网连接与基础接口验证 | ✅ 已完成 |
| P0-005-2 | 完整交易流程验证 | ✅ 已完成 |
| P0-005-3 | 对账服务验证 | ✅ 已完成 |
| P0-005-4 | WebSocket 推送与告警验证 | ✅ 已完成 |

**测试结果**:
- Window1 (订单执行): 7/7 通过
- Window2 (DCA + 持仓): 7/7 通过
- Window3 (对账 + WS): 7/7 通过 ✅
- Window4 (全链路): 9/9 通过

**修复项**:
- 订单 ID 混淆问题 (exchange_order_id vs internal UUID)
- leverage 字段 None 处理
- cancel_order 参数问题

### P6-008 Phase 6 E2E 集成测试确认
| 任务 | 说明 | 状态 |
|------|------|------|
| 前端组件检查 | 5 大组件 100% 完成 | ✅ 已完成 |
| E2E 测试验证 | 80/103 通过 (77.7%)，0 失败 | ✅ 已完成 |

**测试结果**:
- 总测试用例：103
- 通过：80 (77.7%)
- 跳过：23 (因 window 标记过滤)
- 失败：0

**前端组件完成度**:
- ✅ 仓位管理页面 (Positions.tsx)
- ✅ 订单管理页面 (Orders.tsx)
- ✅ 回测报告组件 (PMSBacktest.tsx)
- ✅ 账户页面 (Account.tsx)
- ✅ 止盈可视化 (TPChainDisplay + SLOrderDisplay)

### REC-001/002/003 对账 TODO 实现
| 任务 | 说明 | 状态 |
|------|------|------|
| REC-001 | 实现 `_get_local_open_orders` 数据库订单获取 | ✅ 已完成 |
| REC-002 | 实现 `_create_missing_signal` Signal 创建逻辑 | ✅ 已完成 |
| REC-003 | 实现 `order_repository.import_order()` 导入方法 | ✅ 已完成 |

### E2E 集成测试
- **测试结果**: 22/22 通过 (100%)
- **修复**: `quantity_precision` 类型判断 bug

### P1/P2 问题修复
- **P1 级**: 3 个严重问题修复（trigger_price 零值风险、STOP_LIMIT 价格偏差检查、trigger_price 字段提取）
- **P2 级**: 3 个优化改进（魔法数字配置化、类常量配置化、重复代码重构）
- **测试结果**: 295/295 通过 (100%)

### P0 事项 1-4 完成
- P0-001: SQLite WAL 模式 ✅
- P0-002: 日志轮转配置 ✅
- P0-003: 重启对账流程 ✅
- P0-004: 订单参数合理性检查 ✅

---

## 📋 历史任务索引（已完成）

| 任务名称 | 优先级 | 完成日期 | 归档位置 |
|----------|--------|----------|----------|
| P1/P2 问题修复 | P1/P2 | 2026-04-01 | [archive/2026-03/p1-p2-fix-plan.md](archive/2026-03/p1-p2-fix-plan.md) |
| P0-001/002 基础设施加固 | P0 | 2026-04-01 | [archive/2026-03/p0-001-002-code-review.md](archive/2026-03/p0-001-002-code-review.md) |
| P0-003/004 资金安全加固 | P0 | 2026-04-01 | [archive/2026-03/p0-summary-2026-04-01.md](archive/2026-03/p0-summary-2026-04-01.md) |
| P6-005 账户净值曲线可视化 | P1 | 2026-03-31 | - |
| P6-006 PMS 回测报告组件 | P0 | 2026-03-31 | - |
| P6-007 多级别止盈可视化 | P1 | 2026-03-31 | - |
| P6-008 E2E 集成测试 | P0 | 2026-04-01 | - |

---

## 📁 文档说明

- **当前任务计划** 在此文件中维护
- **历史任务详情** 已归档至 `archive/` 目录
- **进度日志** 见 [`progress.md`](progress.md)
- **技术发现** 见 [`findings.md`](findings.md)

---

*最后更新：2026-04-01*
