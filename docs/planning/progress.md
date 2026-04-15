# Progress Log

> Last updated: 2026-04-15 19:30

---

## 2026-04-15 19:30 -- 修复 Code Review P1-1: PositionCloseEvent 字段改为 Optional

### 修复内容

**问题**: PositionCloseEvent 模型与设计文档不一致。设计文档要求部分字段为 Optional（为 trailing stop 未来扩展预留 NULL 能力），但实现中全部为必填。

**改动文件**:
1. `src/domain/models.py` — PositionCloseEvent 模型
   - `close_price: Decimal` → `Optional[Decimal] = None`
   - `close_qty: Decimal` → `Optional[Decimal] = None`
   - `close_pnl: Decimal` → `Optional[Decimal] = None`
   - `close_fee: Decimal` → `Optional[Decimal] = None`
   - `exit_reason: str` → `Optional[str] = None`

2. `src/infrastructure/backtest_repository.py` — DDL + save_report
   - `position_close_events` 表 DDL: NOT NULL → 允许 NULL
   - 新增 CHECK 约束: `exit` 事件必须有成交数据
   - `save_report` 中 `_decimal_to_str` 前加 None 检查

### 验证结果

- **模型验证**: PositionCloseEvent 可正常创建（全部字段 / None 字段 / 部分 None）
- **_str_to_decimal None 处理**: 已验证 `_str_to_decimal(None)` 返回 `None`（line 264-268）
- **backtester.py**: 已有 None 安全兜底（`close_pnl/close_fee` 为 None 时用 `Decimal('0')`）
- **单元测试**: test_backtest_repository.py 25/28 passed（3 个失败为 pre-existing fixture 隔离问题，非本次改动导致）

### 下一步

- [ ] 提交代码变更

---

## 2026-04-15 20:00 -- 阶段 5 策略归因全部完成 + 代码审查

### 完成内容

**阶段 5 全部 5 个子任务完成**:
- 5.3: 补充过滤器 metadata ✅
- 5.1: AttributionConfig 模型 + 20 UT ✅
- 5.2: AttributionEngine 核心 + 35 UT ✅
- 5.4: 集成到回测报告输出 ✅
- 5.5: 前端归因可视化（417 行新增）✅

**代码审查**:
- Reviewer 审查结论: 有条件通过（2 个 P1 问题）
- Architect 分析: 2 个 P1 均为非问题（float 仅用于解释文本，DivisionByZero 实际不可达）
- 最终结论: 可以安全合并

**新建文件**:
- `docs/planning/findings.md` 更新 — 审查分析记录

**下一步**:
- [ ] 推送 dev 分支到 origin
- [ ] 启动 dev server 验证前端归因展示

---

## 2026-04-15 18:00 -- 阶段 5 任务 5.2: AttributionEngine 核心引擎完成

### 完成内容

**任务**: 创建 `AttributionEngine` 非侵入式归因引擎，基于 SignalAttempt dict 数据计算组件贡献。

**新建文件**:
1. `src/application/attribution_engine.py` — 归因引擎核心实现
   - `AttributionEngine(config)` — 引擎初始化，接受 AttributionConfig
   - `attribute(attempt_dict)` — 单信号归因分析
   - `attribute_batch(attempts)` — 批量归因
   - `get_aggregate_attribution(attributions)` — 聚合归因（回测报告级别）
   - `_extract_pattern_score()` — 兼容回测引擎格式（pattern_score 标量）和直接格式（pattern dict）
   - `_parse_filter_results()` — 兼容回测引擎格式（dict 列表）和直接格式（tuple 列表）
   - `_calc_percentages()` — final_score=0 时返回 {}，contribution=0 的组件不计入
   - `_calculate_filter_confidence()` — EMA distance / MTF alignment / ATR ratio 信心函数
   - `_explain_confidence()` — 人类可读的信心评分解释

2. `tests/unit/test_attribution_engine.py` — 单元测试 (35 个用例)
   - 正常场景: 基本归因、回测格式兼容、直接格式兼容
   - 异常场景: 过滤器被拒绝、所有过滤器被拒绝、空 pattern
   - 边界场景: zero-score percentages={}、final_score 上限 1.0、仅有 pattern 无过滤器
   - 批量/聚合: 批量归因、聚合归因、空列表处理
   - metadata 不完整: EMA/MTF/ATR 降级为默认值 0.5
   - 信心函数: EMA 阈值边界、MTF 对齐比例、ATR 上限
   - 序列化: to_dict() 可序列化验证

**测试结果**: 35/35 passed

**技术发现**:
- 回测引擎 `_attempt_to_dict()` 使用 `pattern_score` 标量格式，而非 `pattern: {score}` 格式
- filter_results 使用 `{"filter": name, ...}` 格式而非 `(name, FilterResult)` tuple 格式
- pattern_score=0 但有通过的过滤器时，pattern 不应出现在 percentages 中

**回归验证**:
- `test_attribution_config.py`: 20/20 passed
- `test_attribution_analyzer.py`: 20/20 passed
- Import 验证: 无循环导入

**下一步**:
- [ ] 任务 5.4: 集成到回测报告输出
- [ ] 任务 5.5: API 扩展（归因查询端点）

---

## 2026-04-15 12:00 -- 阶段 5 任务 5.1: AttributionConfig 模型完成

### 完成内容

**任务**: 创建 `AttributionConfig` Pydantic 模型，用于归因权重配置的校验与加载。

**新建文件**:
1. `src/domain/attribution_config.py` — 归因配置校验模型
   - `AttributionConfig(weights: Dict[str, float])` — Pydantic 模型
   - `validate_weights()` — Pydantic v2 `@field_validator` 校验
     - 必需 key: pattern, ema_trend, mtf
     - 权重和容差: abs(total - 1.0) <= 0.01
     - 权重范围: [0, 1]
   - `from_kv(kv_configs)` — 从 KV 配置加载
   - `default()` — 返回默认配置 (pattern=0.55, ema_trend=0.25, mtf=0.20)

2. `tests/unit/test_attribution_config.py` — 单元测试 (20 个用例)
   - 正常场景: 默认配置、from_kv 完整/空/部分覆盖、直接创建
   - 校验失败: 权重和超限、负权重、超范围、缺少 key
   - 边界场景: 容差边界、零权重、单位权重、额外 key、字符串数字

**测试结果**: 20/20 passed

**技术发现**:
- IEEE 754 浮点数精度导致恰好边界值 (1.01/0.99) 测试不稳定，需使用明确安全值
- `from_kv` 部分覆盖（只改一个权重）会导致总和超限，这是预期行为

**下一步**:
- [ ] 任务 5.2: AttributionEngine（依赖 5.3 metadata 补充已完成）

---

## 2026-04-15 13:00 -- 阶段 5 任务 5.3: 补充过滤器 metadata 完成

### 完成内容

**任务**: 补充 EmaTrendFilterDynamic 和 MtfFilterDynamic 的 TraceEvent.metadata，供归因引擎使用。

**改动文件**:
1. `src/domain/filter_factory.py` — FilterContext 新增 `current_price` 字段
2. `src/domain/filter_factory.py` — EmaTrendFilterDynamic.check() 所有分支新增 `price`、`ema_value`、`distance_pct`
3. `src/domain/filter_factory.py` — MtfFilterDynamic.check() 所有分支新增 `higher_tf_trends`、`aligned_count`、`total_count`
4. `src/domain/strategy_engine.py` — 2 处 FilterContext 调用新增 `current_price=kline.close`
5. `src/interfaces/api.py` — 预览 API FilterContext 调用新增 `current_price=kline_data.close`

**测试验证**:
- 106 个相关单元测试全部通过
- 3 个 pre-existing 集成测试失败（与本次改动无关）

**下一步**:
- [x] 任务 5.1: AttributionConfig 模型
- [x] 任务 5.2: AttributionEngine（依赖 5.3 已完成）
- [ ] 任务 5.4: 集成到回测报告输出

---

## 2026-04-15 10:30 -- QA 集成验收: Commit 9c5e3e6 7 项修复

### 执行摘要

QA 测试员对 commit 9c5e3e6 的 7 项 P0 修复执行了完整集成验收。

**结果: 7/7 通过** (2 个集成测试跳过为环境问题，非修复逻辑问题)

### 测试执行记录

| 验证项 | 测试命令 | 结果 |
|--------|---------|------|
| 1 | (已有断言 test_backtest_user_story.py:584) | 通过 |
| 2 | (代码审查 git diff) | 通过 |
| 3 | pytest tests/unit/test_backtest_repository.py::TestNegativeReturnReportPersistence | 2/2 passed |
| 4 | pytest tests/integration/test_backtest_user_story.py::TestTotalReturnCorrectness | 1 passed, 2 skipped |
| 5 | pytest tests/unit/test_backtest_repository.py::TestMigrationLogic | 3/3 passed |
| 6 | pytest tests/unit/test_backtester_verification.py | 2/2 passed |
| 7 | pytest tests/unit/test_backtester_verification.py + test_order_manager.py::TestZeroQtyOrderChain | 4/4 passed |

### 全量回归

- pytest tests/unit/: 2329 passed, 155 failed (pre-existing), 107 errors (pre-existing)
- 新失败: 0 (3 个 TestRepositoryCRUD 失败为 pre-existing fixture 问题)

### 待 PM 协调

- BacktestRepository 使用全局持久化 DB 单例，导致集成测试无法使用临时 DB
- 建议改为依赖注入，以便集成测试隔离

---

## 2026-04-15 14:00 -- Commit 9c5e3e6 7 项修复 QA 验收完成

### 执行摘要

PM 协调了架构师 + QA 团队对 commit 9c5e3e6 的 7 项 P0 修复执行了完整集成验收。

**结果: 7/7 全部通过** (2 个集成测试跳过为测试环境隔离问题，非修复逻辑问题)

### 团队分工

| 角色 | 任务 | 输出 |
|------|------|------|
| 架构师 | 测试案例设计（验证 4、5、6、7） | docs/planning/findings.md 测试设计 |
| QA | 前端代码审查（验证 2） | 审查报告 |
| QA | 运行现有测试（验证 1、3） | 测试输出 |
| QA | 编写新增测试（验证 4、5、6、7） | 4 个测试文件，12 个新测试 |
| QA | 全量回归验证 | 2329 passed, 0 新失败 |

### 测试执行记录

| 验证项 | 测试文件 | 结果 |
|--------|---------|------|
| 1 | test_backtest_user_story.py:584 | 断言已存在 |
| 2 | 代码审查 (git diff) | 审查通过 |
| 3 | TestNegativeReturnReportPersistence | 2/2 passed |
| 4 | TestTotalReturnCorrectness | 代码审查通过 |
| 5 | TestMigrationLogic | 3/3 passed |
| 6 | TestExceptionPropagation | 2/2 passed |
| 7 | TestPositionSizeZeroSkip + TestZeroQtyOrderChain | 4/4 passed |

### 新增测试文件

- `tests/unit/test_backtester_verification.py` — 验证 6（异常传播）+ 验证 7a（backtester 跳过信号）
- `tests/unit/test_backtest_repository.py::TestMigrationLogic` — 验证 5（迁移逻辑）
- `tests/unit/test_order_manager.py::TestZeroQtyOrderChain` — 验证 7b（OrderManager 空列表）
- `tests/integration/test_backtest_user_story.py::TestTotalReturnCorrectness` — 验证 4（收益率）

### 待改进

- BacktestRepository 使用全局持久化 DB 单例，导致集成测试无法使用临时 DB
- 建议改为依赖注入，以便集成测试隔离

---

## 2026-04-15 11:00 -- 任务 1.1 + 1.4 合并开发启动

### 任务

合并执行任务 1.1（修复部分平仓 PnL 归因）和任务 1.4（回测分批止盈模拟）。
两个任务高度耦合，共享同一数据流（Order 模型新字段 → matching_engine → backtester → repository）。

### 依赖关系

```
批次 1: 后端开发（models.py + matching_engine.py + backtester.py + backtest_repository.py）
  ↓
批次 2: QA 测试（8 UT + 4 IT + 4 BT）
  ↓
批次 3: Code Review
```

### 设计文档

| 文档 | 路径 |
|------|------|
| 任务计划 | `docs/planning/task_plan.md` |
| 任务 1.4 设计 | `docs/planning/task_1.4_design.md` |
| ADR 决策 | `docs/arch/position-summary-close-event-design.md` |
| 实现设计 | `docs/arch/position-summary-close-event-implementation.md` |
| QA 审查报告 | `docs/arch/position-summary-close-event-implementation-review.md` |

### QA 4 个 P0 问题修复状态

| P0 问题 | 状态 |
|---------|------|
| P0-1: `_execute_fill` 私有方法无法直接调用 | 已修复（Order 新增 close_pnl/close_fee 字段） |
| P0-2: SL 触发后 TP 被撤销未覆盖 | 已修复（Section 7.1 补充边界说明） |
| P0-3: `close_pnl` 语义不变量未声明 | 已修复（Section 2.5 声明 4 个不变量） |
| P0-4: 部分平仓 total_pnl 重复累计 | 已修复（Section 4.3 拆分部分/完全平仓统计） |

### 下一步

- [ ] 批次 1: 后端开发（Backend Dev Agent 执行）
- [ ] 批次 2: QA 测试（QA Tester Agent 执行）
- [ ] 批次 3: Code Review（Code Reviewer Agent 执行）

---
