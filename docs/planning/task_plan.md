# 任务计划

> **当前迭代**: 2026-04-02 起  
> **最后更新**: 2026-04-02 (日期选择优化 + Orders.tsx 日期筛选修复完成)

---

## 📊 待办事项总览 (按优先级排序)

| 优先级 | 任务分类 | 任务数 | 预计工时 | 状态 |
|--------|----------|--------|----------|------|
| **P0** | PMS 回测问题修复 | 3 项 | 5h | ✅ 已完成 |
| **P0** | 前端导航重构 | 1 项 | 2h | ✅ 已完成 |
| **P0** | T1 接口拆分 | 1 项 | 2h | ✅ 已完成 |
| **P1** | Phase 7 收尾验证 | 3 项 | 5h | ✅ 已完成 |
| **P1** | 配置管理功能 - 版本化快照 | 7 项 | 8h | ✅ 已完成 |
| **P2** | 配置管理功能 | 2 项 | 4h | ☐ 搁置 |
| **P0** | Phase 8 自动化调参 | 已分解 | 40h | ⏳ 进行中 |
| **P0** | 用户需求 Bug 修复 (2026-04-02) | 7 项 | 8h | ✅ 已完成 |
| **P1** | 后续问题追踪 | 4 项 | 2h | ✅ 已完成 |

---

## 用户需求 Bug 修复 (2026-04-02) ✅

**任务来源**: 用户提出的 7 个需求/问题

| ID | 任务 | 优先级 | 状态 | 修复说明 |
|----|------|--------|------|----------|
| 1 | 配置快照创建验证失败 - version 格式问题 | P0 | ✅ 已完成 | 修复 API 和 Service 的 VERSION_PATTERN 不一致问题 |
| 2 | 持仓数据不一致问题排查 | P0 | ✅ 已完成 | 修复前后端字段名不一致 (items vs positions) |
| 3 | 策略参数可配置化分析与梳理 | P0 | ✅ 分析完成 | 技术任务已分解，待开发 |
| 4 | 订单详情页 K 线渲染 - 集成 TradingView 组件 | P1 | ☐ 待启动 | 待开发 |
| 5 | 回测列表盈亏计算和夏普比率修复 | P0 | ✅ 已完成 | 添加 sharpe_ratio 字段到数据库和 API |
| 6 | 订单管理级联展示功能 | P1 | ☐ 待启动 | 待开发 |
| 7 | 修复信号详情接口报错 (Legacy signal data) | P0 | ✅ 已完成 | 将错误返回改为 HTTPException |

**修改文件汇总**:
- `src/application/config_snapshot_service.py` - 修复版本验证模式
- `src/interfaces/api.py` - 修复配置快照 API 验证、信号详情接口错误处理、回测列表 sharpe_ratio 字段
- `src/infrastructure/backtest_repository.py` - 添加 sharpe_ratio 字段到数据库和查询
- `web-front/src/types/order.ts` - 修复 PositionsResponse 字段名
- `web-front/src/pages/Positions.tsx` - 修复字段名引用

---

## 后续问题追踪 (2026-04-02 新增)

| ID | 任务 | 优先级 | 状态 | 说明 |
|----|------|--------|------|------|
| 8 | 回测数据源降级逻辑修复 | P1 | ✅ 已完成 | DB 无数据时明确降级到 Exchange Gateway |
| 9 | 前端快照 version 格式修复 | P1 | ✅ 已完成 | 前端传参从 `"1"` 改为 `"v1.0.0"` 格式 |
| 10 | 回测页面日期选择组件优化 | P2 | ✅ 已完成 | 添加快捷日期范围选择功能 |
| 11 | Orders.tsx 日期筛选未传递给 API | P1 | ✅ 已完成 | 添加 start_date/end_date 参数到 URL |

---

## 策略参数可配置化 - 数据库存储方案 (2026-04-02 启动) ⭐

**项目概述**: 实现策略参数数据库存储方案，SQLite 持久化，YAML 仅用于导入导出备份。

**设计文档**: 
- `docs/products/p1-tasks-analysis-brief.md` - 产品需求文档
- `docs/planning/findings.md` - 存储方案决策

**状态**: ✅ 阶段 1 完成（后端核心 API 实现）

**架构决策** (2026-04-02):
- **配置存储**: SQLite 数据库 (`config_entries` 表) 替代 YAML 文件
- **YAML 角色**: 仅用于导入导出备份，不作为运行态存储
- **优势**: 启动无需加载外部文件、事务支持、与快照系统无缝集成

**今日完成 (2026-04-02)**:
- ✅ B1: config_entries 表结构创建（config_snapshot_repository.py）
- ✅ B2: StrategyParams 等 Pydantic 模型创建（models.py）
- ✅ B3: GET /api/strategy/params 实现
- ✅ B4: PUT /api/strategy/params + 热重载集成
- ✅ B5: POST /api/strategy/params/preview 实现

**任务清单**:

**后端任务 (10h)**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| B1 | 调整 config_entries 表结构为新设计 | P0 | 1h | ✅ 已完成 |
| B2 | 创建 StrategyParams Pydantic 模型 | P0 | 1h | ✅ 已完成 |
| B3 | 实现 GET /api/strategy/params | P0 | 1h | ✅ 已完成 |
| B4 | 实现 PUT /api/strategy/params + 热重载集成 | P0 | 2h | ✅ 已完成 |
| B5 | 实现 POST /api/strategy/params/preview | P0 | 1h | ✅ 已完成 |
| B6 | 实现 YAML 导入导出 API | P1 | 2h | ☐ 待启动 |

**前端任务 (11h)**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| F1 | 创建 API 函数封装（api.ts） | P0 | 1h | ☐ 待启动 |
| F2 | 实现 StrategyParamPanel 主容器 | P0 | 2h | ☐ 待启动 |
| F3 | 实现 PinbarParamForm 组件 | P0 | 2h | ☐ 待启动 |
| F4 | 实现 EmaParamForm / FilterParamList | P0 | 2h | ☐ 待启动 |
| F5 | 实现 ParamPreviewModal 预览对话框 | P1 | 2h | ☐ 待启动 |
| F6 | 实现 TemplateManager 模板管理 | P1 | 3h | ☐ 待启动 |

**测试任务 (6h)**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| T1 | StrategyParams 模型单元测试 | P0 | 1h | ☐ 待启动 |
| T2 | 策略参数 API 集成测试 | P0 | 2h | ☐ 待启动 |
| T3 | 参数验证边界测试 | P0 | 1h | ☐ 待启动 |
| T4 | 前端 E2E 测试 | P1 | 2h | ☐ 待启动 |

**执行阶段**:
- **阶段 1**: B1-B3（数据库表 + ORM+Repository） - 预计 4h
- **阶段 2**: B4-B5（ConfigManager 集成 + 迁移脚本） - 预计 4h
- **阶段 3**: B6（导入导出 API） - 预计 2h
- **阶段 4**: F1-F6（前端核心） - 预计 11h
- **阶段 5**: T1-T4（测试验证） - 预计 6h
**详细说明**:

### 任务 8: 回测数据源降级逻辑修复

**修改位置**: `src/application/backtester.py:418-419`

**当前代码**:
```python
logger.info(f"Fetched {len(klines)} candles from local DB for {request.symbol} {request.timeframe}")
return klines
```

**修改为**:
```python
logger.info(f"Fetched {len(klines)} candles from local DB for {request.symbol} {request.timeframe}")
if klines:
    return klines
# DB 无数据时，继续降级到 Exchange Gateway
logger.info("DB has no data, falling back to Exchange Gateway...")
```

**优点**: 充分利用降级逻辑，提高数据获取成功率  
**缺点**: 增加 Exchange API 调用频率  
**预估工时**: 0.5h

### 任务 9: 前端快照 version 格式修复

**修改位置**: 前端配置管理页面/回测报告页面

**当前代码**:
```javascript
{"version": "1", "description": ""}
```

**修改为**:
```javascript
{"version": "v1.0.0", "description": ""}
// 或使用时间戳格式
{"version": `v${new Date().toISOString().replace(/[-:]/g, '').slice(0, 8)}.${...}`, "description": ""}
```

**优点**: 符合后端 API 要求，无需修改后端代码  
**缺点**: 需要前端修改代码  
**预估工时**: 0.5h

**后续优化（技术债）**:
- 版本格式验证统一化为工具函数，前后端共用
- 添加 K 线数据可用性检查接口，前端在回测前可先检查数据范围

**预防措施**:
- 添加回测集成测试，覆盖不同时间范围场景
- 前端表单添加 version 格式验证，与后端保持一致

---

### 任务 10: 回测页面日期选择组件优化 ✅ 已完成

**完成日期**: 2026-04-02

**优化内容**:
- ✅ 添加常用快捷按钮（始终可见）:
  - 今天 | 最近 7 天 | 最近 30 天
- ✅ 添加扩展快捷按钮（点击"更多"展开）:
  - 3 天 | 14 天 | 3 个月 | 6 个月 | 今年至今 | 自定义
- ✅ 优化自定义日期范围输入体验:
  - 使用 HTML5 datetime-local 输入框
  - 支持精确到分钟的日期选择
- ✅ 改进交互体验:
  - 常用选项和扩展选项分层展示
  - 选中状态高亮显示（黑色背景）
  - 实时显示选中时间范围和持续时长
  - 使用 date-fns 简化日期计算

**修改文件**:
- `web-front/src/components/QuickDateRangePicker.tsx` - 重构日期选择组件

**涉及页面**:
- `web-front/src/pages/Backtest.tsx` - 信号回测页面（自动应用）
- `web-front/src/pages/PMSBacktest.tsx` - PMS 回测页面（自动应用）

**UI 效果**:
- 常用选项区：今天 | 最近 7 天 | 最近 30 天 | [更多 ▸]
- 扩展选项区（点击"更多"后展开）：3 天 | 14 天 | 3 个月 | 6 个月 | 今年至今 | 自定义
- 时间范围显示：蓝色渐变背景，显示起止时间和持续时长（如 "30 天"、"3 个月"）

---

## 📋 代码审查与测试验证总结

### T1 接口拆分代码审查 ✅

**审查项目** | **状态** | **备注**
-------------|----------|-----------
端点实现正确性 | ✅ 通过 | 两个新端点 `/api/backtest/signals` 和 `/api/backtest/orders` 实现正确
模式验证 | ✅ 通过 | 自动强制 mode 参数（v2_classic/v3_pms）
Repository 初始化 | ✅ 通过 | 正确初始化和关闭资源
向后兼容性 | ✅ 通过 | 保留 `/api/backtest` 端点，添加 DeprecationWarning
前端 API 函数 | ✅ 通过 | `runSignalBacktest()` 和 `runPMSBacktest()` 已更新
类型注解 | ✅ 通过 | 完整类型标注
文档注释 | ✅ 通过 | 中英文双语文档

### 回测系统测试验证 ✅

**测试汇总**:
- 总测试数：72 个
- 通过：71 个 (98.6%)
- 跳过：1 个（预期跳过）
- 失败：0 个

**按模块分类**:
| 模块 | 测试数 | 通过率 | 状态 |
|------|--------|--------|------|
| Repository 层 | 16 | 100% | ✅ |
| API 端点层 | 13 | 100% | ✅ |
| 数据源选择 | 12 | 100% | ✅ |
| MTF 时间对齐 | 10 | 100% | ✅ |
| 集成测试 | 10 | 100% | ✅ |
| E2E 测试 | 11 | 91% | ✅ |

**结论**: 回测系统功能完备，T1 接口拆分验证通过 ✅

---

## 🎯 当前进行中的任务

### Phase 8: 自动化调参 (Optuna 集成) ⭐

**项目概述**: 集成 Optuna 参数优化框架，实现自动化策略参数寻优，支持夏普比率、收益回撤比等多目标优化。

**设计文档**: 
- `docs/designs/phase8-optimizer-contract.md` - API 契约与设计
- `docs/designs/phase8-test-plan.md` - 测试计划

**状态**: 🔄 进行中 (后端 + 前端完成，单元测试通过)

**预计工期**: 2 周

**核心功能**:
| 功能 | 说明 | 优先级 |
|------|------|--------|
| Optuna 目标函数 | 支持夏普比率、PnL/MaxDD、索提诺比率等优化目标 | P0 ✅ |
| 参数空间定义 | EMA 周期、Pinbar 阈值、止损比例等参数范围配置 | P0 ✅ |
| 持久化研究历史 | SQLite 存储试验历史，支持断点续研 | P0 ✅ |
| 可视化分析 | 参数重要性、优化路径、平行坐标图 | P1 ✅ |

**任务分解**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| B1 | Optuna 集成与目标函数实现 | P0 | 4h | ✅ 已完成 |
| B2 | 参数空间定义与验证 | P0 | 3h | ✅ 已完成 |
| B3 | 研究历史持久化 (SQLite) | P0 | 3h | ✅ 已完成 |
| B4 | 优化结果 API 端点 | P0 | 4h | ✅ 已完成 |
| B5 | PerformanceCalculator 实现 | P0 | 2h | ✅ 已完成 |
| B6 | StrategyOptimizer 实现 | P0 | 4h | ✅ 已完成 |
| F1 | API 函数封装 | P0 | 1h | ✅ 已完成 |
| F2 | 参数配置 UI 组件 | P0 | 3h | ✅ 已完成 |
| F3 | 优化进度监控页面 | P0 | 3h | ✅ 已完成 |
| F4 | 可视化图表组件 | P1 | 4h | ✅ 已完成 |
| T1 | Optuna 目标函数单元测试 | P0 | 2h | ✅ 已完成 (29 用例) |
| T2 | 参数空间验证测试 | P0 | 2h | ✅ 已完成 (34 用例) |
| T3 | StrategyOptimizer 单元测试 | P0 | 2h | ✅ 已完成 (22 用例) |
| T4 | API 集成测试 | P0 | 2h | ⏳ 待前后端联调 |
| T5 | E2E 测试 | P1 | 4h | ⏳ 待前后端联调 |

**今日完成 (2026-04-02)**:
- ✅ 后端：StrategyOptimizer + PerformanceCalculator 实现
- ✅ 后端：Optuna 集成（optuna>=3.5.0 已安装）
- ✅ 后端：5 个优化 API 端点
- ✅ 前端：参数配置 UI + 进度监控 + 结果可视化
- ✅ 前端：API 函数封装（runOptimization 等）
- ✅ 测试：86 个单元测试，100% 通过
  - test_strategy_optimizer.py: 22/22 ✅
  - test_optimization_models.py: 35/35 ✅
  - test_performance_calculator.py: 29/29 ✅

**Git 提交**:
- `06677a2` - fix(phase8): 修复 Phase 8 测试和数据模型
- `91085ca` - feat(phase8): 集成 Optuna 自动化调参框架 (后端实现)
- `eb3f4bd` - feat(phase8): 前端实现 - 自动化调参 UI

**待完成**:
- ⏳ T4: API 集成测试 - 待前后端联调
- ⏳ T5: E2E 测试 - 待前后端联调

---

### T1: 信号回测与订单回测接口拆分 ✅

**项目概述**: 将原 `/api/backtest` 接口拆分为两个独立接口，明确区分信号回测和 PMS 订单回测。

**状态**: ✅ 已完成

**交付物**:
| 端点 | 模式 | 用途 |
|------|------|------|
| `POST /api/backtest/signals` | v2_classic | 信号回测 - 仅统计信号触发和过滤器拦截情况 |
| `POST /api/backtest/orders` | v3_pms | PMS 订单回测 - 包含订单执行、滑点、手续费、止盈止损模拟 |
| `POST /api/backtest` | 自动 | 已弃用 - 保留向后兼容性，添加 DeprecationWarning |

**Git 提交**:
- `02b6068` - feat: 拆分信号回测与订单回测接口 (T1)
- `fdc8bf5` - docs: 更新进度日志 - T1 接口拆分完成

**代码审查结果**:
- ✅ 后端 API 端点实现正确
- ✅ 前端 API 函数封装完整
- ✅ 向后兼容性保留（deprecated 警告）
- ✅ 类型注解和文档完整

**测试结果**:
| 测试文件 | 通过率 | 说明 |
|----------|--------|------|
| test_backtest_repository.py | 16/16 ✅ | 仓库 CRUD 操作 |
| test_backtest_orders_api.py | 13/13 ✅ | 订单 API 端点 |
| test_backtester_data_source.py | 12/12 ✅ | 数据源选择逻辑 |
| test_backtester_mtf.py | 10/10 ✅ | MTF 时间对齐 |
| test_backtest_data_integration.py | 10/10 ✅ | 端到端集成测试 |
| test_api_backtest.py | 10/11 ✅ | E2E 回测执行 (1 skipped) |
| **总计** | **71/72 (98.6%)** | 回测系统功能完备 ✅ |

---

### 配置管理功能 - 版本化快照方案 B (2026-04-02 启动) ⭐

### 配置管理功能 - 版本化快照方案 B (2026-04-02 启动) ⭐

**项目概述**: 实现配置的版本化快照管理，支持导出/导入 YAML 配置、手动/自动快照创建、快照列表查看、回滚和删除功能。

**设计文档**: `docs/designs/config-management-versioned-snapshots.md`

**状态**: ✅ 已完成

**任务清单**:

**后端任务 (8h)**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| B1 | 创建 ConfigSnapshot Pydantic 模型 | P0 | 0.5h | ✅ 已完成 |
| B2 | 实现 ConfigSnapshotRepository | P0 | 2h | ✅ 已完成 |
| B3 | 实现 ConfigSnapshotService | P0 | 2h | ✅ 已完成 |
| B4 | 实现 API 端点（导出/导入） | P0 | 1.5h | ✅ 已完成 |
| B5 | 实现 API 端点（快照 CRUD） | P1 | 1.5h | ✅ 已完成 |
| B6 | 集成自动快照钩子到 ConfigManager | P0 | 0.5h | ✅ 已完成 |

**前端任务 (10h)**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| F1 | 创建 API 函数封装 | P0 | 1h | ✅ 已完成 |
| F2 | 配置页面重构 | P0 | 2h | ✅ 已完成 |
| F3 | 导出按钮组件 | P0 | 0.5h | ✅ 已完成 |
| F4 | 导入对话框组件 | P0 | 1.5h | ✅ 已完成 |
| F5 | 快照列表组件 | P1 | 2h | ✅ 已完成 |
| F6 | 快照详情抽屉 | P1 | 1.5h | ✅ 已完成 |
| F7 | 快照操作组件（回滚/删除） | P1 | 1.5h | ✅ 已完成 |
| F7 | 快照操作组件（回滚/删除） | P1 | 1.5h | ☐ 待启动 |

**测试任务 (6h)**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| T1 | Repository 单元测试 | P0 | 1.5h | ✅ 已完成 (14/14 通过) |
| T2 | Service 单元测试 | P0 | 2h | ⏸️ 待补充 |
| T3 | API 集成测试 | P0 | 1.5h | ⏸️ 待补充 |
| T4 | 前端 E2E 测试 | P1 | 1h | ⏸️ 待补充 |

**执行阶段**:
- **阶段 1**: B1-B3, B6（后端核心）
- **阶段 2**: B4-B5（后端 API）
- **阶段 3**: F1-F4（前端核心，与阶段 2 并行）
- **阶段 4**: F5-F7（前端 UI）
- **阶段 5**: T1-T4（测试验证）

---

### PMS 回测系统问题修复 (2026-04-02 新增) ✅

**项目概述**: PMS 回测系统存在多项问题需要排查修复

**状态**: ☐ 待启动

**待办事项**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| ~~T1~~ | ~~信号回测与订单回测接口拆分~~ | P0 | ~~2h~~ | ✅ **已完成** |
| ~~T2~~ | ~~回测记录列表展示确认~~ | P0 | ~~0.5h~~ | ✅ **已完成** |
| ~~T3~~ | ~~订单详情 K 线图渲染确认~~ | P0 | ~~0.5h~~ | ✅ **已完成** |
| ~~T4~~ | ~~回测指标显示错误排查~~ | P0 | ~~3h~~ | ✅ **已完成** |
| ~~T5~~ | ~~回测 API 接入本地数据源~~ | P0 | ~~0.5h~~ | ✅ **已完成** |

**详细说明**:

**T1: 信号回测与订单回测接口拆分** ✅ 已完成
- 状态：信号回测和订单回测逻辑已拆分到两个独立接口
- 新接口:
  - `POST /api/backtest/signals` - 信号回测（v2_classic 模式）
  - `POST /api/backtest/orders` - PMS 订单回测（v3_pms 模式）
- 原 `/api/backtest` 端点标记为 deprecated
- 前端更新:
  - `runSignalBacktest()` - 信号回测 API 调用
  - `runPMSBacktest()` - PMS 回测 API 调用
  - `runBacktest()` - 标记为 deprecated
- 修改文件:
  - `src/interfaces/api.py` - 新增两个端点，原端点标记为 deprecated
  - `web-front/src/lib/api.ts` - 更新 API 调用
  - `web-front/src/pages/Backtest.tsx` - 使用 runSignalBacktest

**T2: 回测记录列表展示确认** ✅ 已完成
- 后端：`/api/v3/backtest/reports` 已实现（支持筛选、排序、分页）
- 前端：`BacktestReports.tsx` 页面已实现
- 修复：添加 `fetchBacktestOrder()` API 函数到 `web-front/src/lib/api.ts`

**T3: 订单详情 K 线图渲染确认** ✅ 已完成
- 后端：`/api/v3/backtest/reports/{report_id}/orders/{order_id}` 已实现（包含 K 线数据）
- 前端：`OrderDetailsDrawer.tsx` 已集成 K 线图组件
- 数据流：从 `HistoricalDataRepository` 获取订单前后各 10 根 K 线

**T4: 回测指标显示错误排查** ✅ 已完成
- 问题：后端返回小数形式 (0.0523)，前端展示时未乘以 100 转换为百分比
- 修复文件:
  - `BacktestOverviewCards.tsx`: 总收益率、胜率、最大回撤
  - `TradeStatisticsTable.tsx`: 胜率、最大回撤
  - `EquityComparisonChart.tsx`: 总收益率
- 修复内容：所有百分比字段乘以 100 后再展示

**T5: 回测 API 接入本地数据源** ✅ 已完成
- 问题：`/api/backtest` 端点创建 `Backtester` 时未传入 `HistoricalDataRepository`
- 现状：回测时直接从交易所获取 K 线数据（降级逻辑）
- 目标：初始化并传入 `HistoricalDataRepository`，优先使用本地 SQLite
- 修复位置：`src/interfaces/api.py:893`

**T6: 回测 K 线数据源确认** ✅ 已确认
- 结论：`Backtester._fetch_klines()` 代码已实现本地数据库优先逻辑
- 代码位置：`src/application/backtester.py` L393-419
- 逻辑：优先使用 `HistoricalDataRepository` 查询本地 SQLite，降级使用 `ExchangeGateway`

---

### 前端导航重构 (2026-04-02 完成) ✅

**项目概述**: 当前 Web 前端一级页面过多 (10 个)，展示不下，需要合理分类，设计二级层级导航结构。

**状态**: ✅ 已完成

**修改文件**: `web-front/src/components/Layout.tsx`

**实现功能**:
- ✅ 将 10 个一级导航项分类为 4 个二级菜单
- ✅ 实现下拉菜单 UI 组件
- ✅ 添加展开/收起交互
- ✅ 响应式适配

**分类方案**:
```
📊 监控中心      → 仪表盘、信号列表、尝试溯源
💼 交易管理      → 仓位管理、订单管理
🧪 策略回测      → 策略工作台、回测沙箱、PMS 回测
⚙️ 系统设置      → 账户、配置快照
```

**待办事项**:
| ID | 任务名称 | 优先级 | 预计工时 | 状态 |
|----|----------|--------|----------|------|
| ~~T1~~ | ~~分析当前导航结构~~ | P0 | ~~0.5h~~ | ✅ 已完成 |
| ~~T2~~ | ~~识别所有一级导航项~~ | P0 | ~~0.5h~~ | ✅ 已完成 |
| ~~T3~~ | ~~设计分类方案~~ | P0 | ~~1h~~ | ✅ 已完成 |
| ~~T4~~ | ~~实现导航组件改造~~ | P0 | ~~2h~~ | ✅ 已完成 |

**待实现**:
- [ ] 修改 `Layout.tsx` 导航数据结构
- [ ] 实现二级菜单 UI 组件
- [ ] 添加展开/收起交互
- [ ] 移动端响应式适配

---

## 📋 完整任务分类汇总

### 一、P0 级 - 紧急重要 (立即执行)

#### 1.1 PMS 回测问题修复 ⭐
| 任务 | 工时 | 说明 |
|------|------|------|
| ~~信号回测与订单回测接口拆分~~ | ~~2h~~ | ✅ 已确认：接口已分离 |
| ~~回测记录列表展示确认~~ | ~~0.5h~~ | ✅ 已完成 |
| ~~订单详情 K 线图渲染确认~~ | ~~0.5h~~ | ✅ 已完成 |
| ~~回测指标显示错误排查~~ | ~~3h~~ | ✅ 已完成 |
| ~~回测 API 接入本地数据源~~ | ~~0.5h~~ | ✅ 已完成 |
| **小计** | **已完成** | 所有 PMS 回测问题已修复 |

#### 1.2 前端导航重构 ⭐
| 任务 | 工时 | 说明 |
|------|------|------|
| 导航组件实现 | 2h | 二级菜单 UI+ 交互 |
| **小计** | **2h** | 1 个子任务 |

**P0 级总计**: 已完成 (5 个子任务全部完成)

---

### 二、P1 级 - 重要 (本周完成)

#### 2.1 Phase 7 回测数据本地化 - 收尾验证 ✅
| 任务 | 工时 | 状态 |
|------|------|------|
| T5: 数据完整性验证 | 2h | ✅ 已完成 |
| T7: 性能基准测试 | 1h | ✅ 已完成 |
| T8: MTF 数据对齐验证 | 2h | ✅ 已完成 |
| **小计** | **5h** | 3 个子任务 |

#### 2.2 配置管理功能 (搁置)
| 任务 | 工时 | 说明 |
|------|------|------|
| 配置导入导出 API | 2h | YAML 备份/恢复 |
| **小计** | **2h** | 用户决策：产品成熟前不迁移 |

**P1 级总计**: 7h (3 个核心 +1 个搁置)

---

### 三、P2 级 - 次要 (时间允许)

#### 3.1 配置管理功能 (搁置)
| 任务 | 工时 | 说明 |
|------|------|------|
| 配置 Profile 管理 | 2h | 多环境配置切换 |
| 配置审计与治理 | 2h | 配置变更日志 |
| **小计** | **4h** | 用户决策：产品成熟前不迁移 |

**P2 级总计**: 4h (2 个子任务)

---

### 四、已完成任务 (近期)

#### 4.1 Phase 7 回测数据本地化 - 核心功能 ✅
- [x] HistoricalDataRepository 创建
- [x] Backtester 数据源切换
- [x] 单元测试 (58 用例 100% 通过)
- [x] ExchangeGateway 集成 (降级逻辑)
- [x] 集成测试 (12 个测试)
- [x] 回测订单 API (列表/详情/删除)
- [x] 代码审查问题修复

#### 4.2 P1 问题系统性修复 ✅
- [x] 类型注解不完整
- [x] 日志级别不当
- [x] 魔法数字硬编码
- [x] 时间框架映射不完整
- [x] 删除订单后未级联清理
- [x] ORM 风格不一致 (已记录技术债)

#### 4.3 PMS 回测修复阶段 A/B/C ✅
- [x] MTF 未来函数修复
- [x] 止盈撮合滑点修复
- [x] 数据持久化 (orders/backtest_reports 表)
- [x] 前端展示页面 (回测记录列表/订单详情 K 线图)

#### 4.4 Phase 6 前端适配 ✅
- [x] 4 个核心页面
- [x] 20+ v3 组件
- [x] 后端 API 端点
- [x] E2E 测试 80/103 通过

#### 4.5 Phase 5 实盘集成 ✅
- [x] ExchangeGateway 订单接口
- [x] PositionManager 并发保护
- [x] ReconciliationService 对账
- [x] CapitalProtectionManager 资金保护
- [x] DcaStrategy 分批建仓
- [x] FeishuNotifier 飞书告警

---

## 📅 建议执行顺序

| 顺序 | 任务分类 | 理由 |
|------|----------|------|
| 1-5 | PMS 回测问题修复 | ✅ 全部已完成 |
| 6 | 前端导航重构 | 用户体验提升 |
| 7 | Phase 7 收尾验证 | 性能优化，非阻塞 |
| 8 | 配置管理功能 | 搁置，待用户决策 |
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
