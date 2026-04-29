# Progress Log

> Last updated: 2026-04-29 11:25
> Archive backup: `docs/planning/archive/2026-04-23-planning-backup/progress.full.md`

---

## 说明（阅读方式）

本文件是 append-only 的进度日志，条目可能按主题分组而不是严格时间序。
当需要还原精确执行顺序时，以 git history 为准（commit 时间戳是唯一可靠时间线）。

## 近期进行中

### 2026-04-29 -- P0修复：risk_calculator.py 敞口约束逻辑重构（集成测试已完成）

**任务背景：**
- 发现核心设计缺陷：敞口约束混在风险约束里，导致 exposure 参数几乎无效
- 正确设计：三层独立控制（风险约束 → 敞口约束 → 杠杆约束）

**当前状态：**
- ✅ 任务计划已创建（`docs/planning/task_plan.md`）
- ✅ T1: 后端实现已完成
- ✅ T2: 代码审查已完成
- ✅ T3: 集成测试已完成

**测试结果（2026-04-29 11:30 执行）：**
- 单元测试：52 passed, 0 failed
- 回归测试：63 passed, 0 failed（全部 risk 相关测试）
- 扩展回归测试：73 passed, 0 failed
- 覆盖率：89%（超过 80% 要求）
- 验证脚本：6/6 通过

**验证要点：**
- ✅ exposure 参数真正生效
- ✅ 三层约束独立工作（风险/敞口/杠杆各有限制场景）
- ✅ exposure=0 返回零仓位
- ✅ 超出敞口限制返回零仓位
- ✅ 无现有功能回归

**产出：**
- `src/domain/risk_calculator.py` — 三层独立约束实现
- `tests/unit/test_risk_calculator_exposure.py` — 专项测试（9 个用例）
- `scripts/verify_exposure_fix.py` — 验证脚本
- `docs/planning/2026-04-29-risk-calculator-integration-test.md` — 测试报告

---

## 近期完成

### 2026-04-27 -- Sim-1 已部署到 Mac mini Docker，进入自然模拟盘观察

1. ✅ Sim-1 准入级检查通过
   - `.env.local` 已补齐 PG / runtime profile 相关配置
   - `sim1_eth_runtime` 可解析、可冻结、可启动
   - runtime readonly 关键观察口可用
2. ✅ `.env` 已停止被 git 跟踪
   - 本地副本保留
   - `.env.local.example` 与 `docs/local-pg.md` 已同步安全说明
3. ✅ 当前阶段判断已切换：
   - 不再以“继续迁库”作为默认主线
   - 正式进入 “观察 + 策略研究 + 前端完善 + PG/边界治理后续减熵”

### 2026-04-27 -- Research Control Plane v1 方案文档已完成

1. ✅ 已新增实施规划概要：
   - `docs/planning/architecture/2026-04-27-research-control-plane-v1-plan.md`
2. ✅ 已新增详细设计文档：
   - `docs/planning/architecture/2026-04-27-research-control-plane-v1-detailed-design.md`
3. ✅ 当前设计结论：
   - 按 Research Control Plane 的架构做
   - 按 Backtest Workbench 的最小范围先落地
4. ✅ 当前明确边界：
   - research/candidate 不直接改 runtime
   - v1 不做一键 promote runtime
   - v1 不把 `config_profiles` 当 runtime 入口
5. ✅ 已补充决策记录：
   - `docs/planning/architecture/2026-04-27-research-control-plane-v1-decision-record.md`
6. ✅ 已完成 Claude 回测链路报告校准：
   - 保留“query chain 防脏数据 / job 化 / 状态化”作为有效输入
   - 剔除 `/api/backtest/run` 和 `BacktestRequest` 只能传 `strategy_id` 等过期判断
7. ✅ 已明确核心代码骨架由 Codex 实施，Claude 只接测试/fixture/文档盘点等杂活

### 2026-04-27 -- Research Control Plane v1 核心后端骨架已落地

1. ✅ 新增 domain models：
   - `src/domain/research_models.py`
   - `ResearchSpec / ResearchJob / ResearchRunResult / CandidateRecord`
2. ✅ 新增独立 research metadata repository：
   - `src/infrastructure/research_repository.py`
   - 默认 DB：`data/research_control_plane.db`
3. ✅ 新增 application service / runner contract：
   - `src/application/research_control_plane.py`
   - `ResearchJobService`
   - `LocalBacktestResearchRunner`
4. ✅ 新增 API shell：
   - `src/interfaces/api_research_jobs.py`
   - `POST /api/research/jobs/backtest`
   - `GET /api/research/jobs`
   - `GET /api/research/jobs/{job_id}`
   - `GET /api/research/runs/{run_result_id}`
   - `POST /api/research/candidates`
   - `GET/POST /api/research/candidate-records/*`
5. ✅ 已接入主 FastAPI app：
   - `src/interfaces/api.py`
6. ✅ 已执行轻量校验：
   - `py_compile` 通过
   - app 路由导入检查通过
   - research metadata 写读冒烟通过
7. ⚠️ 未执行完整 pytest；后续测试补齐适合交给 Claude

### 2026-04-27 -- Research Control Plane v1 骨架加固

1. ✅ Claude 已补 4 个定向测试文件：
   - `tests/unit/test_research_models.py`
   - `tests/unit/test_research_repository.py`
   - `tests/unit/test_research_control_plane_service.py`
   - `tests/unit/test_research_jobs_api.py`
2. ✅ 定向测试结果：
   - `84 passed`
3. ✅ Codex 已在审查后继续补强核心骨架：
   - 新增 `ResearchRunListResponse`
   - 新增 repository/service 层 `list_run_results()`
   - 新增 API：`GET /api/research/runs`
   - background job 异常现在会记录 logger.exception，便于 Sim/本地观察
4. ✅ 复跑定向测试：
   - `84 passed, 1 warning`
5. ⚠️ 新增 `GET /api/research/runs` 的专项测试尚未补齐，适合交给 Claude 作为下一轮测试杂活

### 2026-04-27 -- Research Control Plane v1 前端骨架已接入

1. ✅ 新增真实 API adapter：
   - `createResearchBacktestJob()`
   - `getResearchJobs()`
   - `getResearchJob()`
   - `getResearchRuns()`
   - `getResearchRun()`
   - `createCandidateRecord()`
   - `getCandidateRecords()`
2. ✅ 新增前端类型：
   - `ResearchSpec`
   - `ResearchJob`
   - `ResearchRunResult`
   - `CandidateRecord`
3. ✅ 新增页面：
   - `/research/new` 新建回测任务
   - `/research/jobs` 研究任务列表
   - `/research/runs/:run_result_id` run detail + candidate 标记入口
4. ✅ 更新导航：
   - 新建回测
   - 研究任务
   - 历史报告（保留旧 backtest reports）
5. ✅ 修复两个前端类型阻塞：
   - `Card` 支持标准 div props
   - `Health.tsx` startup marker badge 参数类型收紧
6. ✅ 前端 TypeScript 静态检查通过：
   - `npm run lint`

### 2026-04-27 -- Research Control Plane v1 前端尾巴已收口

1. ✅ Claude 已补 API adapter 测试：
   - `gemimi-web-front/src/services/api.test.ts`
   - 新增 13 个测试
   - `18 passed`
2. ✅ Codex 已补前端 adapter 小尾巴：
   - `getResearchJobs(status, limit, offset)`
   - `getResearchRuns(jobId, limit, offset)`
3. ✅ `mockApi.ts` 已镜像 Research Control Plane API：
   - create/list/get jobs
   - list/get runs
   - create/list candidate records
4. ✅ 验证：
   - `npm run lint` 通过
   - `npx vitest run src/services/api.test.ts` 通过，`18 passed`

### 2026-04-27 -- Signals PG Window groundwork 已落地并完成定向回归

1. ✅ 新增 `PgSignalRepository`
   - live `signals` / `signal_take_profits` 进入 PG
2. ✅ 新增 `HybridSignalRepository`
   - live signal 主路径 -> PG
   - `signal_attempts` / `config_snapshots` / backtest helpers -> SQLite
3. ✅ 新增 `create_runtime_signal_repository()` 并接入：
   - `main.py`
   - `api.py` standalone lifespan
4. ✅ `SignalPipeline` 已移除对 `repository._db` 的直连：
   - active signal cache rebuild 改走 `list_active_signals_for_cache_rebuild()`
   - opposing signal 查询改走 `get_signal_by_tracker_id()`
5. ✅ SQLite `SignalRepository` 已补最小兼容方法：
   - `get_signal_by_tracker_id()`
   - `list_active_signals_for_cache_rebuild()`
   - `save_signal()` 同步补 `take_profit_1` 持久化
6. ✅ 定向测试通过：
   - `test_signal_repository.py`
   - `test_runtime_config_signal_pipeline.py`
   - `test_console_runtime_routes.py`
   - `test_api_lifespan_runtime.py`
   - `test_signal_pipeline.py`
   - 合并跑：`113 passed`
7. ✅ 语法校验通过：
   - `pg_signal_repository.py`
   - `hybrid_signal_repository.py`
   - `signal_pipeline.py`
   - `api.py`
   - `main.py`
   - `core_repository_factory.py`
   - `signal_repository.py`
   - `pg_models.py`

### 当前剩余杂活

1. ~~`PgSignalRepository` 真实 PostgreSQL 集成测试~~ ✅ 已完成
   - `tests/integration/test_pg_signal_repo.py`
   - `33 passed`
2. ~~历史 `test_signal_repository_s6_2.py` fixture 现代化（旧 SQLite `:memory:` 连接语义）~~ ✅ 已完成
   - `12 passed`

### 2026-04-27 -- Signals PG Window 验证收口完成

1. ✅ `tests/integration/test_pg_signal_repo.py` 已新增并通过
   - 覆盖 live signals CRUD / query / stats / clear
   - 覆盖 `signal_take_profits` round trip
   - 覆盖 PG 约束与 FK cascade
2. ✅ `tests/integration/conftest.py` 已补 signal repo fixture 与表清理
3. ✅ 历史 `tests/unit/test_signal_repository_s6_2.py` 已修复并通过
   - 旧 SQLite `:memory:` fixture 适配当前连接获取方式
   - direction 大小写断言已与 v3 语义对齐
4. ✅ 当前 `signals` 窗口可判定为：
   - runtime signal 主路径已切 PG
   - `signal_attempts` 继续留 SQLite
   - 主线代码 + unit tests + PG integration tests 均已过

### 2026-04-27 -- Signals 窗口补充修复：direction 归一化与 save_signal 状态回退防护

1. ✅ `Direction` 已支持大小写无关归一化
   - `Direction._missing_()` / `Direction.normalize()` 新增
   - `SignalQuery.direction` / `SignalDeleteRequest.direction` 在模型层归一化
2. ✅ `PerformanceTracker` 不再依赖小写 `long/short`
   - pending signal 跟踪统一按 `LONG/SHORT` 语义执行
3. ✅ `PgSignalRepository.save_signal()` 已移除粗粒度 `merge()` 主路径
   - 改为按 `signal_id` 查已有行
   - 已存在时定向刷新字段
   - incoming `PENDING` 不会覆盖已推进状态
4. ✅ SQLite `SignalRepository` 的方向查询入口也已补归一化，保持 hybrid contract 一致
5. ✅ 本轮仅执行 `py_compile` 静态校验，未主动跑测试

### 2026-04-27 -- Signals 删除边界已收紧

1. ✅ live signals 现在不能通过 API 做物理删除
   - `DELETE /api/signals` 仅允许 `source=backtest`
   - `DELETE /api/signals/clear_all` 仅允许 `source=backtest`
2. ✅ 新增最小边界测试：
   - `tests/unit/test_signal_delete_boundary.py`
   - 结果：`4 passed`

### 2026-04-27 -- Runtime config 真源去 YAML 化主干已收口

1. ✅ `main.py` 启动已改为直接使用 `load_all_configs_async()`
   - 不再先走失效的同步 YAML 启动壳
2. ✅ `load_all_configs()` 已明确降级为 legacy helper
   - 用于 YAML fixture 测试 / 导入导出辅助
   - 调用时发出 `DeprecationWarning`
3. ✅ README 已改为：
   - SQLite 配置库 + runtime profile 是运行时真源
   - YAML 仅保留为导入导出/备份/测试 fixture

### 2026-04-27 -- Config Profile 边界已收紧为 legacy config domain

1. ✅ 明确 `ConfigProfileService` 是旧配置域管理，不是 runtime freeze 真源
2. ✅ `/api/config/profiles/*` 文义已收紧：
   - 管理旧配置域 active profile
   - 默认对后续启动 / 显式 reload 生效
   - 不代表热切当前 execution runtime
3. ✅ 当前决定：
   - 暂不删除 config profile 代码
   - 暂不继续给它加新运行时能力
   - 后续只做降噪/维护，不再当主路径建设

### 2026-04-25 -- 执行主线 PG 切换第一层代码骨架已落地

1. ✅ 已新增 execution 主线仓储显式入口：
   - `create_pg_order_repository()`
   - `create_pg_position_repository()`
2. ✅ 已新增 `PositionProjectionService`，作为 ENTRY 成交投影到 PG `positions` 的最小骨架
3. ✅ 已把 `PgPositionRepository` 从 ORM 骨架提升为可读写 domain `Position` 的最小实现，并新增 `list_active()`
4. ✅ 已把 `position_repo` 注入链打通：
   - `main.py -> api.set_dependencies() -> api_console_runtime.py -> RuntimePositionsReadModel`
5. ✅ 已移除 `ExecutionOrchestrator` 内两处直接访问 `_order_lifecycle._repository.save()` 的主链绕过点，统一改走 `OrderLifecycleService.register_created_order()`
6. ✅ 已把 `api.py` 的 runtime order repo fallback 改为统一工厂 `create_order_repository()`，不再固定直连 SQLite
7. ✅ 已完成快速静态校验：
   - `python3 -m py_compile ...` 通过
8. ✅ 已补齐即时 `full fill` 的 position projection 入口，并把 orchestrator 内剩余 `_order_lifecycle._repository` 直连清零
9. ✅ 已补齐 `ENTRY filled` 回调链：
   - WebSocket / 对账把 ENTRY 推进到 `FILLED` 时，也会回到 orchestrator 挂保护单并更新 position projection
   - 已增加“已有保护单则不重复挂载”的防重逻辑
10. ✅ 已补齐 `TP/SL filled` -> position projection 更新链：
   - exit filled 会更新 `current_qty / realized_pnl / total_fees_paid / is_closed / closed_at / watermark_price`
11. ✅ 已把 runtime execution 装配收口到显式 PG 工厂：
   - `main.py` runtime 主链不再走通用 order/position 工厂
   - `api.py` runtime lifespan 与 runtime order fallback 也显式走 PG runtime 工厂
12. ✅ 已把 runtime overview 的 backend summary 改为优先显示实际装配结果，避免继续被历史 `.env` 值误导
13. ✅ 已增强 `_has_existing_protection_orders()` 防重判定：
   - `parent_order_id` 优先
   - 仅“未绑定 parent 的保护单”作为对账重建/脏数据场景的兜底
14. ✅ 已补齐 `Position.opened_at / closed_at`，移除 `project_exit_fill()` 对 `object.__setattr__` 的依赖
15. ✅ 已修复 `GET /api/v3/positions` 的 `offset` 双重切片 bug，fallback 分支不再因二次切片返回空数组
16. ✅ 未执行 pytest；按仓库红线，完整测试前仍需用户确认
### 2026-04-25 -- 研究链边界已补充并同步到 planning 文档

1. ✅ 已明确 SQLite + PG 双轨阶段后续研究主线继续推进 `Spec / Resolver / Reporter` 收口。
2. ✅ 已明确研究链必须保持 `research-only`：
   - 纯回测
   - Optuna
   - candidate 产物
   - 报告 / 解释分析
3. ✅ 已明确不得新增 runtime 直读 SQLite 的旁路。
4. ✅ 已明确所有研究产物只输出 `candidate`，不得直接影响 `sim1_eth_runtime`。
5. ✅ 已将“research 生成候选、runtime 承载冻结配置、candidate 进入 runtime 必须人工审查”补充到 `task_plan.md / findings.md`。

### 2026-04-25 -- 执行主线 PG 真源闭环窗口边界已补充并同步到规划文档

1. ✅ 已基于架构文档 `docs/arch/2026-04-25-执行主线PG真源闭环调研与架构设计.md` 补充 planning 摘要。
2. ✅ 已明确当前窗口只处理 runtime execution 主链，不扩大为“全库去 SQLite”。
3. ✅ 已明确 `signals / signal_attempts` 本窗口不迁：
   - 原因不是放弃迁移
   - 而是避免把 execution 主线闭环扩大成 runtime observability 全迁移
4. ✅ 已补充后续迁移顺序与准入条件：
   - 第 1 窗口：execution 主线 PG 闭环
   - 第 2 窗口：runtime observability 收口（优先 `signals / signal_attempts`）
   - 第 3 窗口：参数 / 策略配置域迁移
   - 第 4 窗口：backtest / research / 历史报表迁移
5. ✅ 已明确 `positions` 在本窗口中的定位：
   - 不是替代交易所事实真源
   - 而是 PG 本地 execution projection / read model
6. ✅ 当前仍停留在架构沟通与范围收口阶段，未进入代码实现，未执行测试。

### 2026-04-25 -- 后端只读 API 主线已确认，api 模块进入瘦身规划

1. ✅ 识别当前瓶颈已从“前端页面结构”转为“后端只读数据供给”。
2. ✅ 确认主模块仍依赖 `src/interfaces/api.py` 启动，因此短期采取“保留兼容入口 + 逐步拆路由”的策略。
3. ✅ 冻结当前后端主线方向：
   - 先做只读 API
   - 先做页面级聚合接口
   - Runtime / Research 分域推进
   - 前端 mock 作为临时垫层，逐页替换为真实后端数据
4. ✅ 已新增后端只读 API 主线规划文档：
   - `docs/planning/architecture/2026-04-25-backend-readonly-api-and-api-module-roadmap.md`
5. ✅ 已新增后端只读 API v1 合同文档：
   - `docs/planning/architecture/2026-04-25-console-readonly-api-v1-contract.md`
6. ✅ 已新增 Claude 杂活提示词：
   - `docs/frontend-handoff/claude-backend-readonly-api-mapping-prompt.md`
7. ✅ 已确认第一批实现范围：
   - `runtime/overview`
   - `runtime/portfolio`
   - `runtime/health`
   - `research/candidates`
8. ✅ 已开始第一阶段代码骨架：
   - 新增 console readmodels 和 console routers
   - `main.py -> api.py` 注入链已补 runtime config / recovery repo / startup reconciliation summary
   - `runtime/events` 明确延后，不进入第一批

### 2026-04-24 -- Sim-1 runtime cutover 非 I/O 冒烟已通过

1. ✅ 新增 `scripts/verify_sim1_runtime_cutover.py`
   - 不启动 `main.py`
   - 不连接交易所
   - 不启动 WebSocket / REST API
   - 不初始化 PG session

2. ✅ 验证内容
   - `RuntimeConfigResolver` 可解析 `sim1_eth_runtime`
   - market scope 为 `ETH/USDT:USDT` + `1h/4h`
   - risk config 为 `1% / 20x / 100% exposure / 10 trades`
   - strategy 可构建 `StrategyDefinition` 与 dynamic runner
   - execution 可构建 runtime `OrderStrategy`

3. ✅ 验证结果
   - `python3 scripts/verify_sim1_runtime_cutover.py`
   - 结果：通过，`config_hash=0279ca9c45b37fad`

### 2026-04-24 -- Runtime Config 单元测试已补齐并修复契约边界

1. ✅ 新增 `tests/unit/test_runtime_config_signal_pipeline.py`
   - 覆盖 `StrategyRuntimeConfig.to_strategy_definition()`
   - 覆盖 `ExecutionRuntimeConfig.to_order_strategy()`
   - 覆盖 `SignalPipeline._apply_runtime_direction_policy()`
   - 覆盖 `SignalPipeline._build_execution_strategy()`

2. ✅ 修复执行配置契约边界
   - `tp_ratios` 不允许 `0` 或负数
   - `tp_targets` 不允许 `0` 或负数
   - 防止非正数 TP 比例/目标进入保护单生成

3. ✅ Runtime strategy 改为生成 `logic_tree`
   - 避免新 runtime config 主线继续依赖 `StrategyDefinition` 的 deprecated triggers/filters 迁移路径
   - 保留 `trigger/filters` 字段用于兼容和测试可读性

4. ✅ 测试结果
   - `python3 -m pytest tests/unit/test_runtime_config_signal_pipeline.py -q`
   - 结果：27 passed

### 2026-04-24 -- Runtime direction policy 审计语义已修复

1. ✅ LONG-only direction policy 在持久化前生效
   - 不允许方向的 `SIGNAL_FIRED` attempt 会先改为 `FILTERED`
   - 追加 `runtime_direction_policy` filter result
   - 避免 SHORT attempt 被记录成已触发信号

2. ✅ 影响范围
   - 不改变下单行为
   - 只修正 signal attempt 审计语义
   - 保持 Sim-1 LONG-only 运行边界

### 2026-04-24 -- Runtime Config execution 已接入 SignalPipeline

1. ✅ execution `OrderStrategy` 已由 runtime execution module 构建
   - `tp_levels=2`
   - `tp_ratios=[0.5, 0.5]`
   - `tp_targets=[1.0, 3.5]`
   - `initial_stop_loss_rr=-1.0`
   - `trailing_stop_enabled=False`
   - `oco_enabled=True`

2. ✅ `SignalPipeline._build_execution_strategy()` 已优先返回 runtime strategy 快照
   - 不再从 `SignalResult.take_profit_levels` 派生实盘保护单策略
   - 每次 dispatch 前 `model_copy(deep=True)`，避免后续对象复用污染

3. ✅ 执行链冻结语义
   - `ExecutionOrchestrator.execute_signal()` 仍会在创建 `ExecutionIntent` 时再次深拷贝 strategy
   - full-fill / partial-fill / recovery 路径都继续依赖 `ExecutionIntent.strategy`

4. ✅ 已做轻量验证
   - `python3 -m py_compile` 通过
   - `scripts/verify_sim1_runtime_config.py` 通过
   - 未执行 pytest

### 当前边界

- `CapitalProtectionManager` 账户级熔断仍未切 runtime risk
- `SignalResult.take_profit_levels` 仍可用于展示/通知/研究，但不再作为执行保护单策略入口
- 下一步应做代码审查与启动级冒烟，不继续扩大配置面

### 2026-04-24 -- Runtime Config strategy 已接入 SignalPipeline

1. ✅ `SignalPipeline` 已支持 runtime strategy definitions
   - 从 `ResolvedRuntimeConfig.strategy` 构建 `StrategyDefinition`
   - 策略作用域限定为 `ETH/USDT:USDT:1h`
   - `4h` 仍作为 MTF 辅助周期，只用于状态与过滤

2. ✅ Sim-1 strategy 当前生效口径
   - trigger: `pinbar`
   - filters: `ema`, `mtf`, `atr(disabled)`
   - allowed directions: `LONG`
   - MTF EMA period: `60`

3. ✅ 补齐热重载边界
   - runtime risk 已锁定，ConfigManager 热重载不会覆盖 `_risk_config`
   - runtime strategy 已锁定，ConfigManager 热重载不会覆盖 runner strategy / MTF EMA period

4. ✅ 已做轻量验证
   - `python3 -m py_compile` 通过
   - `scripts/verify_sim1_runtime_config.py` 通过
   - 未执行 pytest

### 当前边界

- execution `OrderStrategy` 尚未从 runtime execution module 派生
- `_build_execution_strategy()` 仍从 `SignalResult.take_profit_levels` 派生保护单策略
- 下一刀应单独切 execution，因为它会直接改变 TP/SL 保护单语义

### 2026-04-24 -- Runtime Config risk 已接入 SignalPipeline

1. ✅ `SignalPipeline` 的 `RiskConfig` 已由 runtime risk module 构建
   - `max_loss_percent=0.01`
   - `max_leverage=20`
   - `max_total_exposure=1.0`
   - `daily_max_trades=10`

2. ✅ 保留旧配置 fallback
   - 若 provider 缺失，仍回退到 `user_config.risk`
   - 正常启动路径已经在 Phase 1.1 严格解析 runtime profile

3. ✅ 明确未切范围
   - `CapitalProtectionManager` 仍使用 `ConfigManager.build_capital_protection_config()`
   - execution TP/SL 仍未从 runtime execution module 消费

4. ✅ 已做轻量验证
   - `python3 -m py_compile` 通过
   - `scripts/verify_sim1_runtime_config.py` 通过
   - 未执行 pytest

### 2026-04-24 -- Runtime Config market scope 已小范围实切

1. ✅ `main.py` Phase 6/7/8 已消费 runtime market module
   - `symbols` 来自 `ResolvedRuntimeConfig.market.symbols`
   - `timeframes` 来自 `ResolvedRuntimeConfig.market.timeframes`
   - `warmup_bars` 来自 `ResolvedRuntimeConfig.market.warmup_history_bars`
   - `asset_polling_interval` 来自 `ResolvedRuntimeConfig.market.asset_polling_interval`

2. ✅ Sim-1 market 当前生效口径
   - symbol: `ETH/USDT:USDT`
   - timeframes: `1h`, `4h`
   - warmup bars: `100`
   - polling interval: `60s`

3. ✅ 保留旧配置 fallback
   - 若 provider 缺失，仍回退到 `ConfigManager`
   - 正常启动路径已经在 Phase 1.1 严格解析 runtime profile，因此 fallback 主要用于防御和后续测试替身

4. ✅ 已做轻量验证
   - `python3 -m py_compile` 通过
   - `scripts/verify_sim1_runtime_config.py` 通过
   - 未执行 pytest

### 当前边界

- `strategy` module 尚未驱动 `SignalPipeline`
- `risk` module 尚未驱动 `RiskConfig` / `CapitalProtectionConfig`
- `execution` module 尚未成为 `OrderStrategy` 唯一入口
- 当前只完成 market scope 实切，交易语义参数仍由现有路径驱动

### 2026-04-24 -- Runtime Config 已接入 main.py 启动期（observe-only）

1. ✅ 新增 `RuntimeConfigProvider`
   - 作为进程内只读 holder 保存 `ResolvedRuntimeConfig`
   - 当前只暴露 `resolved_config`、`config_hash`、`to_safe_summary()`

2. ✅ `main.py` 启动期新增 Phase 1.1
   - 默认解析 `RUNTIME_PROFILE=sim1_eth_runtime`
   - 成功后打印 profile / version / config_hash
   - 打印脱敏 safe summary
   - 明确日志标记为 observe-only，不改变现有执行消费路径

3. ✅ 已 seed 本地 `data/v3_dev.db`
   - 写入 `sim1_eth_runtime`
   - 当前 profile version: `1`
   - 当前 config hash: `0279ca9c45b37fad`

4. ✅ 已做轻量验证
   - `python3 -m py_compile` 通过
   - `scripts/verify_sim1_runtime_config.py` 通过
   - 未执行 pytest

### 当前边界

- `RuntimeConfigProvider` 尚未注入 `SignalPipeline`
- execution `OrderStrategy` 尚未从 runtime execution module 派生
- exchange secret / webhook 仍由现有 `ConfigManager` 路径消费
- 现有 `.env` 没有新增提交；后续不要再把本地 PG 示例或 secret 改动提交进 `.env`

### 2026-04-23 -- Runtime Config 骨架审查问题已修复

1. ✅ 收紧 strategy 契约
   - `StrategyRuntimeConfig.trigger` 改为 `TriggerConfig`
   - `StrategyRuntimeConfig.filters` 改为 `list[FilterConfig]`

2. ✅ 修复 config hash 污染
   - hash 中移除 `backend_port`
   - hash 中移除 repo backend switches
   - hash 只保留会影响业务执行语义的 `exchange_name / exchange_testnet` 与 profile payload

3. ✅ 修复 readonly profile 防覆盖
   - `RuntimeProfileRepository.upsert_profile()` 默认拒绝覆盖 `is_readonly=True` 的 profile
   - seed 脚本使用显式 `allow_readonly_update=True` 作为初始化/维护入口

4. ✅ 修复 active profile 切换事务问题
   - upsert 全流程包入 repo lock
   - active reset + upsert 使用 `BEGIN IMMEDIATE` / commit / rollback

5. ✅ 已做最小自检
   - 验证 `BACKEND_PORT` 变化不影响 `config_hash`
   - 验证 readonly profile 默认不可覆盖
   - 验证 trigger/filter 已解析为强类型模型
   - `python3 -m py_compile` 通过

### 当前边界

- 仍未接入 `main.py`
- 仍未写入正式 `data/v3_dev.db`
- 仍未执行 pytest

### 2026-04-23 -- Runtime Config 骨架已实现，尚未接入主程序

1. ✅ 新增 `ResolvedRuntimeConfig` 与五模块 Pydantic 模型
   - `EnvironmentRuntimeConfig`
   - `MarketRuntimeConfig`
   - `StrategyRuntimeConfig`
   - `RiskRuntimeConfig`
   - `ExecutionRuntimeConfig`

2. ✅ 新增 `RuntimeConfigResolver`
   - 从 `.env` / shell env 读取 environment
   - 从 SQLite runtime profile 读取 market / strategy / risk / execution
   - 生成 `config_hash`
   - 输出脱敏 `safe_summary`

3. ✅ 新增 SQLite `RuntimeProfileRepository`
   - 新表：`runtime_profiles`
   - profile 以 JSON 形式保存五模块配置
   - 支持 upsert / get / active / list

4. ✅ 新增工具脚本
   - `scripts/seed_sim1_runtime_profile.py`
   - `scripts/verify_sim1_runtime_config.py`

5. ✅ 已做最小自检
   - `python3 -m py_compile` 通过
   - 使用临时 SQLite + fake env 验证 resolver 可解析 `sim1_eth_runtime`，并可正常退出

### 当前边界

- 本轮没有改 `main.py`
- 本轮没有让运行时真实消费 resolver
- 本轮没有修改现有 SQLite config tables
- 本轮没有执行 pytest

### 下一步

1. 审查 Runtime Config 骨架
2. 决定是否执行 seed 写入本地 `data/v3_dev.db`
3. 下一轮再接 `main.py`：
   - exchange secret / webhook 从 resolver environment 读取
   - 启动日志打印 resolved runtime summary/hash
   - 再后续切 SignalPipeline / execution OrderStrategy 消费

---

### 2026-04-28 H6a Donchian 20-bar Breakout Proxy

**完成**: Donchian 20-bar LONG-only 独立 proxy 回测

**产出**:
- `scripts/run_donchian_h6a_proxy.py` — 独立撮合 proxy（不修改 src）
- `reports/research/donchian_h6a_proxy_2026-04-28.json` — 年度结果 JSON
- `docs/planning/2026-04-28-h6a-donchian-breakout-proxy.md` — 完整分析报告

**关键发现**:
- 3yr PnL = **-17,305**（vs Pinbar +9,067）
- 信号过频：年均 648 signals，年均 424 trades（Pinbar 67 trades）
- WR 36.7%（高于 Pinbar 27.5%）但被 turnover 和紧止损杀死
- 2025 极端：31 trades, 25 SL, WR 19.4%, MaxDD 74%
- 2024 唯一正收益 (+504)，但 MaxDD 65.4%

**判定**: **CLOSE** — Donchian 20 LONG 关闭，不进入参数搜索，不进入 H6b

**根因**: 20-bar 1h 通道太窄，ETH 波动下频繁假突破，whipsaw 模式主导。Breakout 家族在 ETH 1h 20-bar 上无 alpha 痕迹。

### 2026-04-28 M0 Strategy Ecology Map — Pinbar 市场状态诊断

**完成**: 市场状态 × Pinbar 表现映射，10 特征 tercile 分桶分析

**产出**:
- `scripts/run_strategy_ecology_m0.py` — 独立撮合 + 特征计算 + 分桶
- `reports/research/strategy_ecology_m0_2026-04-28.json` — 完整结果 JSON
- `docs/planning/2026-04-28-strategy-ecology-map-m0.md` — 完整分析报告

**关键发现**:
- **6+ 特征有显著解释力**（spread > 5,000 USDT）
- **Pinbar = 反趋势策略**: 低 ema slope + 低 volatility 环境赚钱
- **近期涨幅是毒药**: 72h return 高 → Pinbar WR 从 18.8% 降到 7.3%
- **高波动杀死 Pinbar**: atr_percentile 高 → PnL 从 -1,584 降到 -7,750
- **2023 ATR percentile 0.625 vs 2024/25 0.531** — 2023 波动更高
- **Donchian 距离互补**: Pinbar 在 Donchian 通道顶部最差（正是 breakout 入场位）

**判定**: **PASS** — M0 有价值，下一步优先做 regime filter（不是新 entry）

**下一步**:
1. 给 Pinbar 加 regime filter（ema_4h_slope / atr_percentile 阈值）
2. 验证过滤后 2023 亏损是否显著减少
3. 暂停新 entry 策略（Donchian / Breakout / Engulfing）

### 2026-04-23 -- Config Module SSOT / Runtime Resolver 架构设计已启动

1. ✅ 已审查 Sim-1 ETH runtime config 规划
   - 确认 Sim-1 目标为 `ETH/USDT:USDT`
   - 主周期 `1h`
   - MTF 辅助周期 `4h`
   - LONG-only / EMA50 / MTF / ATR disabled
   - Execution TP `[1.0, 3.5]`、ratio `[0.5, 0.5]`

2. ✅ 已核验当前代码配置事实
   - `ConfigManager` 仍以 SQLite 为主配置库
   - exchange key/secret 与 webhook 当前仍能从 SQLite 被读取
   - `SignalPipeline._build_execution_strategy()` 当前仍从 `SignalResult.take_profit_levels` 派生执行策略
   - Backtest / Optuna / runtime 参数仍存在多套默认与覆盖路径

3. ✅ 已确认架构决策
   - Config 短中期继续保留 SQLite
   - PG 继续只承载 execution state / recovery / breaker
   - Config 后续即使迁 PG，也属于 repository adapter 实现层迁移，不阻塞 Sim-1

4. ✅ 已新增架构文档
   - `docs/planning/architecture/2026-04-23-config-module-ssot-runtime-resolver-design.md`
   - `docs/planning/architecture/2026-04-23-runtime-config-implementation-skeleton.md`

5. 下一步
   - 进入 Runtime Config 骨架实现：
     - SQLite `runtime_profiles` 仓储
     - `ResolvedRuntimeConfig` 模型
     - `RuntimeConfigResolver`
     - `sim1_eth_runtime` seed / verify 脚本
   - 暂不改完整运行逻辑，先完成可解析、可 hash、可审计的配置骨架

### 2026-04-23 -- Sim-0 真实链路阶段性通过

1. ✅ 完成 Sim-0.2 主程序真实启动验证
   - PG execution intent/recovery 初始化成功
   - Phase 4.3 启动对账通过
   - Phase 4.4 breaker 重建通过
   - SignalPipeline warmup 成功

2. ✅ 完成 Sim-0.3 信号到 testnet ENTRY 验证
   - 受控 K 线进入真实 runtime
   - 冻结策略触发 `LONG` 信号
   - CapitalProtection 通过
   - testnet ENTRY 市价成交

3. ✅ 完成 Sim-0.4 ENTRY 后保护单验证
   - TP1 / TP2 / SL 均提交成功
   - PG intent 最终状态为 `completed`
   - 未产生 active recovery task
   - breaker 为空

4. ✅ 完成 Sim-0.5 重启对账验证
   - 清理受控验证仓位和保护单后重启
   - 启动对账候选订单 0
   - 对账失败 0
   - PG active recovery tasks 0
   - breaker 重建为空

5. ✅ 验证期间修复 4 个真实链路问题
   - `SignalPipeline._calculate_risk()` 未 await
   - 市价 ENTRY 缺失成交均价时保护单挂载失败
   - PG intent 状态枚举写入格式错误
   - PG intent/order 跨库外键与当前双轨配置冲突

报告：

- `docs/reports/2026-04-23-sim-0-real-chain-validation.md`

当前暂停点：

1. Sim-0 已阶段性通过
2. testnet 验证仓位/保护单已清理
3. attempt flush 的 Decimal JSON 序列化问题已修复
4. 暂不直接进入自然模拟盘观察窗口
5. 下一步新开窗口，专门梳理 `config module` 与配置真源

### 2026-04-23 -- Sim-0 后置缺口修复

1. ✅ 修复 `SignalPipeline` attempt flush 失败
   - 问题：真实 runtime 中 `SignalRepository.save_attempt()` 遇到 `Decimal` 诊断字段时报 `Object of type Decimal is not JSON serializable`
   - 影响：不阻断 ENTRY / TP / SL，但会丢失信号尝试诊断记录
   - 修复：`SignalRepository` 增加 Decimal/Enum 安全 JSON 序列化 helper
   - 覆盖：`details`、`trace_tree`、`tags_json`

2. ✅ 补充回归测试
   - 新增用例：`test_save_attempt_serializes_decimal_diagnostics`
   - 验证 Decimal pattern details 和 Decimal score 可正常落库

3. ✅ 验证结果
   - `./venv/bin/python3 -m pytest tests/unit/test_signal_repository.py -v`
   - 结果：26 passed

### 2026-04-23 -- 下一阶段入口调整：config module 梳理

1. ✅ 已确认问题重心
   - 表面问题是“模拟盘参数不知道怎么配”
   - 实际问题是 config module 的真源边界不清
   - 需要先梳理 `.env`、SQLite 配置库、历史 YAML、代码默认值、回测 runtime overrides、执行参数之间的职责

2. ✅ 已形成新窗口背景
   - 新窗口不是继续修执行链代码
   - 也不是先讨论哪套交易参数更优
   - 目标是系统分析 config module：哪些配置归 `.env`，哪些归 DB，哪些只应作为代码默认值，哪些应废弃

3. ✅ 当前初步事实
   - `.env` 已确定为运行入口
   - YAML 已废弃，不应作为运行配置依据
   - 主程序当前仍通过 `ConfigManager` 从 `data/v3_dev.db` 读取 exchange / notification / system / risk / strategies
   - Sim-0 验证脚本曾将 `.env` 同步进 SQLite 兼容配置库
   - 配置库中的真实参数与研究文档中的历史基准存在不一致

4. 下一步
   - 新开专门窗口做 config module 架构梳理
   - 先输出配置真源矩阵和分层原则
   - 再决定 Sim-1 前最小收口方案与中期 PG config 方案

### 2026-04-23 -- Sim-1 ETH runtime config 规划

1. ✅ 明确 Sim-1 使用 ETH，而非 Sim-0 BTC 受控配置
   - 当前 BTC 配置标记为 `sim0_controlled_btc`
   - ETH baseline 以 `docs/planning/backtest-parameters.md` 为主真源

2. ✅ 明确五模块配置模型
   - `environment`
   - `market`
   - `strategy`
   - `risk`
   - `execution`

3. ✅ 明确 Sim-1 关键参数
   - `ETH/USDT:USDT`
   - 主周期 `1h`
   - MTF 辅助订阅 `4h`
   - LONG-only
   - EMA50 + MTF
   - ATR disabled
   - `max_loss_percent=0.01`
   - `max_leverage=20`
   - `max_total_exposure=1.0`
   - `daily_max_loss_percent=0.10`
   - TP `[1.0, 3.5]` / ratio `[0.5, 0.5]`
   - BE off / trailing off / OCO on

4. ✅ 明确任务边界
   - Sim-1 前不做 PG config 大迁移
   - 模拟盘期间不允许热改 strategy / risk / execution
   - Optuna 只输出 candidate，不自动应用 runtime
   - `.env` 管 secret/env/backend，DB 管非 secret business config

5. ✅ 新增规划文档
   - `docs/planning/sim-1-eth-runtime-config-plan.md`

### 2026-04-23 -- 第二阶段第一步完成

1. ✅ 实现 PG 驱动的 circuit breaker 重建
   - ExecutionOrchestrator 新增 `rebuild_circuit_breakers_from_recovery_tasks()`
   - main.py 新增 Phase 4.4 调用 breaker 重建
   - 单元测试全部通过（4/4）

2. ✅ 移除 SQLite `pending_recovery` 过渡链
   - 删除 `src/infrastructure/pending_recovery_repository.py`
   - 收口 ExecutionOrchestrator（删除 `_pending_recovery_repository` 和 `_pending_recovery`）
   - 收口 StartupReconciliationService（删除阶段 2.5）
   - 收口 main.py（删除 `_pending_recovery_repo` 初始化和 shutdown）
   - 删除 3 个过渡测试文件

3. ✅ 恢复主链统一到 PG `execution_recovery_tasks`
   - 恢复真源：PG `execution_recovery_tasks`
   - 派生缓存：内存 `circuit_breaker_symbols`（由 PG 重建）

4. ✅ recovery retry/backoff 策略显式化
   - 最大重试次数：3
   - 基础延迟：60s
   - 延迟上限：900s
   - 规则：指数退避

5. ✅ 模拟盘准入冒烟验证通过
   - 报告：`docs/reports/2026-04-23-sim-trading-readiness-smoke-check.md`
   - 场景 A：正常链路冒烟通过
   - 场景 B：`replace_sl_failed` 异常链路冒烟通过
   - 场景 C：启动恢复冒烟通过
   - 场景 D：熔断拦截冒烟通过

### 当前定性

第二阶段第一步完成，SQLite `pending_recovery` 过渡链已完全移除，恢复主链统一到 PG。

模拟盘准入冒烟已通过，但真实模拟盘全链路尚未实证。下一步进入 Sim-0。

---

## 当前状态

### 已完成

1. ✅ `ExecutionIntent` PG SSOT
2. ✅ `execution_recovery_tasks` PG 正式恢复真源
3. ✅ SQLite `pending_recovery` 过渡链已移除
4. ✅ Circuit breaker 由 PG active recovery tasks 重建
5. ✅ 最小执行恢复闭环
6. ✅ 模拟盘准入冒烟

### 未完成但不阻塞

1. 少量 P2 级初始化/注入一致性收尾
2. 真实模拟盘全链路验证尚未执行

### 2026-04-24 -- Backtest config 抽象层完成

1. ✅ 新增回测配置抽象层
   - 文件：`src/application/backtest_config.py`
   - 新增 `BacktestConfigResolver`
   - 新增 `ResolvedBacktestConfig`
   - 新增 `BacktestProfileProvider` / `StaticBacktestProfileProvider`
   - 新增独立 profile：`backtest_eth_baseline`

2. ✅ 回测配置边界明确
   - Backtest 不直接读取 `sim1_eth_runtime`
   - Backtest 使用独立基线 profile
   - 优先级保持：`runtime_overrides > request > backtest profile > code defaults`
   - Backtest engine 参数不进入 Sim/Live runtime

3. ✅ 可注入参数契约已显式化
   - 新增 `BACKTEST_INJECTABLE_PARAMS`
   - 当前共 25 个可注入参数
   - 模块：`market / strategy / risk / execution / engine / diagnostic`
   - 已标记 `optimizer_safe`，供 Optuna/前端回测后续消费

4. ✅ 小范围验证通过
   - `python3 -m pytest tests/unit/test_backtest_config_resolver.py tests/unit/test_backtest_params_resolution.py -q`
   - 结果：20 passed
   - `python3 scripts/verify_backtest_config_resolver.py`
   - 结果：解析 `backtest_eth_baseline` 成功，无 exchange / PG / historical data I/O

5. ⏭️ 后续事项
   - 回测 API 暂缓，当前不做 Web
   - 按需将仍会使用的研究脚本入口接入 `BacktestConfigResolver`
   - 前端回测重构时读取同一份可注入参数契约
   - 真实回测执行前再单独确认是否跑耗时测试

### 2026-04-24 -- Optuna 隔离完成

1. ✅ `StrategyOptimizer` 接入 `BacktestConfigResolver`
   - 默认 profile：`backtest_eth_baseline`
   - trial request 从 profile resolver 生成
   - strategy / risk / execution 不再在 Optuna 内部硬编码

2. ✅ Optuna 参数注入白名单化
   - parameter space 只能使用 `optimizer_safe=True` 字段
   - fixed params 必须命中 `BACKTEST_INJECTABLE_PARAMS`
   - 防止 secret / backend / runtime profile 被误作为搜索参数

3. ✅ 覆盖语义保留
   - runtime overrides 仍为最高优先级
   - request 覆盖仍只影响单次 trial
   - backtest profile 作为低优先级基线
   - Optuna 不写 runtime DB，不自动应用模拟盘

4. ✅ 小范围验证通过
   - `python3 -m pytest tests/unit/test_strategy_optimizer.py tests/unit/test_optuna_runtime_overrides.py tests/unit/test_backtest_config_resolver.py -q`
   - 结果：58 passed
   - `python3 -m compileall -q src/application/strategy_optimizer.py src/application/backtest_config.py`

5. ⏭️ 后续事项
   - 真实 Optuna 小规模搜索运行前单独确认
   - 如继续使用旧研究脚本，再逐个迁入 `BacktestConfigResolver`
   - API/Web 仍暂缓

### 2026-04-24 -- 两个 P1 收口

1. ✅ `.env` 本地 PG 配置移除
   - 已从已跟踪 `.env` 删除 `PG_DATABASE_URL` / `CORE_EXECUTION_INTENT_BACKEND` / `CORE_ORDER_BACKEND`
   - `docs/local-pg.md` 改为推荐 shell 环境变量
   - 文档明确不要把本地 PG 连接串写入已跟踪 `.env`

2. ✅ Standalone lifespan reset 防线复核
   - 当前 `src/interfaces/api.py` shutdown 已重置 `_exchange_gateway` / `_capital_protection` / `_account_service` / `_execution_orchestrator`
   - 修正 `tests/unit/test_api_lifespan_runtime.py` 的 mock 目标，避免测试依赖 `.env` 或过期模块属性

3. ✅ 验证
   - `python3 -m pytest tests/unit/test_api_lifespan_runtime.py tests/unit/test_strategy_optimizer.py tests/unit/test_optuna_runtime_overrides.py tests/unit/test_backtest_config_resolver.py -q`
   - 结果：68 passed

### 2026-04-24 -- Optuna QA 二次审查修复

1. ✅ 删除 dead code
   - 移除 `StrategyOptimizer._build_backtest_request()`
   - 清除 `StrategyOptimizer` 对 `BACKTEST_ETH_BASELINE_PROFILE` 的直接依赖

2. ✅ Trial resolver 解析次数收口
   - `_build_trial_backtest_inputs()` 每个 trial 只调用一次 `BacktestConfigResolver.resolve()`
   - 风控覆盖在已解析出的 `BacktestRequest` 上叠加，不再二次 resolve

3. ✅ `BacktestRuntimeOverrides` 构建 DRY 化
   - 删除手写 if-else 梯子
   - 使用 `BacktestRuntimeOverrides.model_fields` 过滤后交给 Pydantic 构造
   - fixed params 仍高于 sampled params

4. ✅ engine fixed params 补齐
   - `initial_balance`
   - `slippage_rate`
   - `tp_slippage_rate`
   - `fee_rate`

5. ✅ 风控 fallback 强制来自当前 profile
   - `_build_risk_overrides()` 不再回退 ETH baseline 常量
   - 未传当前 profile fallback 时直接报错

6. ✅ 验证
   - `python3 -m pytest tests/unit/test_strategy_optimizer.py tests/unit/test_optuna_runtime_overrides.py tests/unit/test_backtest_config_resolver.py -q`
   - 结果：58 passed
   - `python3 -m pytest tests/unit/test_api_lifespan_runtime.py tests/unit/test_strategy_optimizer.py tests/unit/test_optuna_runtime_overrides.py tests/unit/test_backtest_config_resolver.py -q`
   - 结果：68 passed

### 2026-04-24 -- Runtime risk / Optuna candidate 收口

1. ✅ Runtime risk 已进入 `CapitalProtectionManager` 派生链
   - 新增 `RiskRuntimeConfig.to_capital_protection_config()`
   - `main.py` 启动时优先尝试读取账户快照
   - 若拿到启动权益，则冻结 `daily.max_loss_amount = equity * daily_max_loss_percent`
   - 若拿不到快照，则保留 `daily.max_loss_percent` 百分比口径回退
   - 单笔风控与账户最大杠杆均随 runtime risk 对齐

2. ✅ Optuna candidate report 已落盘能力化
   - 新增 `StrategyOptimizer.build_candidate_report()`
   - 新增 `StrategyOptimizer.write_candidate_report()`
   - 默认输出到 `reports/optuna_candidates/`
   - 仅生成 candidate JSON，不自动 promote runtime profile

3. ✅ Optuna / 研究脚本入口同步收口
   - `scripts/verify_fixed_params_minimal.py` 改为走 `_build_trial_backtest_inputs()`
   - 移除对已删除 `_build_backtest_request()` 的依赖
   - `scripts/run_optuna_eth_1h.py` / `scripts/run_optuna_narrow_search.py` 完成后会输出 candidate report 路径

4. ✅ 单元测试补齐
   - `tests/unit/test_runtime_config_signal_pipeline.py`
     - 新增 runtime risk -> capital protection 派生测试
   - `tests/unit/test_strategy_optimizer.py`
     - 新增 candidate report 构建/落盘测试

5. ✅ 验证
   - `python3 -m pytest tests/unit/test_runtime_config_signal_pipeline.py tests/unit/test_strategy_optimizer.py tests/unit/test_optuna_runtime_overrides.py -q`
   - 结果：79 passed

6. ✅ 决策记录：研究脚本收口选方案 A（先行）
   - 目标：路径 1 轻量级收口，优先消除脚本口径漂移与不可复现
   - 决策：保留现有脚本入口，但脚本薄化为 Spec + Resolver + Reporter
   - 约束：candidate only；Sim-1 期间不允许自动 promote runtime profile
   - 方案 B（统一 CLI + registry）延后到 Sim-1 稳定后演进

7. ✅ 方案 A 前置骨架已落地（等待脚本迁移接入）
   - 新增 `OptunaStudySpec` / `BacktestJobSpec`（统一脚本装配入口）
   - candidate report 补齐 `git` 与 `reproduce_cmd` 字段
   - 新增 dry-run replay 脚本：`scripts/replay_optuna_candidate.py`
   - 新增契约文档：`docs/planning/optuna-candidate-report-contract.md`

---

## 下一步

### Sim-0：真实模拟盘全链路验证

下一步不是继续扩功能，而是执行 Sim-0：

1. Sim-0.1：启动配置冻结
2. Sim-0.2：主程序真实启动
3. Sim-0.3：信号到 testnet 下单链路验证
4. Sim-0.4：WS 回写与保护单验证
5. Sim-0.5：重启对账与恢复验证

具体任务拆分：

- `docs/planning/sim-0-real-chain-validation-plan.md`

---

## 2026-04-24

### 前端重构规划已收口为方案 A

1. ✅ 已确认当前前端重构不走“大杂烩 dashboard”，采用分域控制台方案：
   - `Runtime`
   - `Research`
2. ✅ 四个关键边界已冻结：
   - 第一版只读为主
   - Candidate review 第一版只展示，不写回
   - Runtime 页面第一版手动刷新
   - Backtest Studio 二期并入
3. ✅ 规划文档已新增：
   - `docs/planning/architecture/2026-04-24-frontend-runtime-monitor-and-research-console-plan.md`
4. ✅ 当前页面树已冻结：
   - `Runtime / Overview`
   - `Runtime / Signals`
   - `Runtime / Execution`
   - `Runtime / Health`
   - `Research / Candidates`
   - `Research / Candidate Detail`
   - `Research / Replay`
5. ✅ 当前接口优先级已冻结：
   - P0：runtime overview / signals / attempts / intents / orders / health
   - P1：candidate list / candidate detail / replay
   - P2：backtests / compare / review 写回
6. ✅ 前端规划补充约束已收口：
   - Runtime 页面加入 freshness / heartbeat 设计
   - Console 默认本地 / 内网访问
   - Replay 第一版按 replay context 理解
   - Candidates 第一版默认目录扫描，后续如规模增长再补索引缓存
   - breaker / recovery summary 在接口语义上拆分
7. ✅ 前端页面补充方案 A 已冻结：
   - `Runtime / Portfolio`
   - `Runtime / Positions`
   - `Runtime / Events`
   - `Config / Snapshot`（只读）
   - `Research / Candidate Review`（只读）
8. ✅ 当前页面补充方向已明确：
   - 按量化使用者日常观察路径补页
   - 仍保持只读 + mock-first
   - 暂不进入配置写回与 runtime 操作页
9. ✅ 前端扩展主线已切换到方案 B：
   - 基于 `gemimi-gemimi-web-front` 现有骨架继续扩展
   - 目标是完整控制台
   - 已新增方案 B 主规划文档

### Config 重构第三轮审计收口（方案 A）

1. 修复 `StrategyOptimizer._build_profile_seed_request()` 丢失 `tp_slippage_rate` 的透传问题。
2. 为 `run_coroutine_threadsafe(...).result()` 增加单 trial 超时保护；超时后取消 future 并 prune 当前 trial，避免 worker 线程长期阻塞。
3. 为 `coerce_decimal_list_fields()` 增加非 list/tuple 输入防御，避免把字符串逐字符转 Decimal 的隐性坏数据。
4. 新增 `tests/unit/test_validators.py`，直接覆盖 shared validators 的边界行为。
5. 记录 `stable_config_hash()` 的 hash schema 语义升级点，明确旧 hash 仅在审计语义上失效，不影响运行查询链路。

### Candidate review 规则落盘

1. ✅ candidate 链闭环已验证
   - candidate JSON 可写出、可 replay
   - `best_trial` 与 `top_trials[0]` 指标一致
   - `sortino_ratio` 不再固定为 `0` / `null`

2. ✅ 当前评审状态已冻结
   - `PASS_STRICT`
   - `PASS_STRICT_WITH_WARNINGS`
   - `PASS_LOOSE`
   - `REJECT`

3. ✅ 当前 `Strict v1` 已落地文档
   - `docs/planning/optuna-candidate-review-rubric.md`
   - 当前硬门槛：
     - `total_trades >= 100`
     - `sharpe_ratio >= 1.0`
     - `total_return >= 0.30`
     - `max_drawdown <= 0.25`
     - `win_rate >= 0.45`
     - `params_at_boundary == false`

4. ✅ 当前 warning-only 项明确保留
   - `sortino_ratio` 异常时先 warning，不直接 fail
   - `trade_concentration`
   - `profit_concentration`
   - `max_consecutive_losses`

### 2026-04-25 PG 执行主线第二轮修复

- 已直接修复用户确认的执行一致性主干问题：
  - `PositionProjectionService` 加仓位级锁
  - exit projection 改为累计值 -> delta 幂等投影
  - `OrderLifecycleService` 增加 exit progressed callback
  - protection order 按 `placement_result.status` 推进本地状态
  - SL 替换后新单失败补 recovery / circuit breaker / notifier
  - `ExecutionIntent` 增加最小状态前进约束
- 已同步 `Position` / `PgPositionRepository` 的 projection payload 字段：
  - `projected_exit_fills`
  - `projected_exit_fees`
- 已执行 `python3 -m py_compile` 静态校验，通过。
- 未运行 pytest；继续遵守“测试前先用户确认”的项目红线。

### 2026-04-26 单实例执行一致性补强

- 已按用户确认的方案 A 完成单实例补强：
  - `PositionProjectionService` 清理空闲锁
  - `ExecutionOrchestrator` 清理终态 intent 锁
  - 去掉 EXIT 双回调，只保留 exit progressed 投影链
  - 替换 SL 失败时先 best-effort 补挂旧 SL
  - 首次/增量 SL 失败时先做一次同步立即重试
  - 修复 SL 同步重试成功后 `sl_order` 仍指向原失败单的问题，改为回传真实 retry order
  - `project_entry_fill()` 修复 `is_closed=False` 但 `closed_at!=None` 的僵尸 position
  - breaker 重建改为读取 blocking recovery tasks
  - `api.py` 独立 uvicorn 模式补齐 PG recovery repo / position projection / startup reconciliation / breaker 重建，避免 runtime 主线在不同入口下语义漂移
  - `api.py` shutdown 补齐 `PositionRepository` / `ExecutionRecoveryRepository` 关闭
- 在 5 份审计报告基础上继续自动收口：
  - `database.py` 为 PG 引擎补 `pool_pre_ping` / `pool_recycle`
  - 新增 `probe_pg_connectivity()`，runtime health / overview 不再永远返回 `DEGRADED`
  - `api_console_runtime.py` 为独立 uvicorn 模式补 `_account_getter` 兜底
  - `RuntimePositionsReadModel` 改为 PG projection 优先，交易所 snapshot 仅做价格/PnL/杠杆补强
  - `/api/v3/positions` 改为 PG projection 优先，交易所持仓作为 enrich/fallback
  - `PgPositionRepository` 新增 `list_positions()`
  - `PgOrderRepository` 补齐 `get_orders` / `get_order_tree` / `get_order_chain_by_order_id` / `delete_orders_batch` 等 API 主路径方法
  - runtime orders 前后端契约补齐 `order_role` / `type`，避免把 BUY/SELL 误当 TP/SL
  - `seed_sim1_runtime_profile.py` 去掉 `allow_readonly_update=True`，避免只读 runtime profile 被脚本静默改写
- 已执行 `python3 -m py_compile src/application/position_projection_service.py src/application/execution_orchestrator.py src/infrastructure/pg_execution_recovery_repository.py src/application/readmodels/runtime_health.py`，通过。
- 已执行 `python3 -m py_compile src/interfaces/api.py src/application/position_projection_service.py src/application/execution_orchestrator.py src/infrastructure/pg_execution_recovery_repository.py src/application/readmodels/runtime_health.py`，通过。
- 已执行 `python3 -m py_compile src/infrastructure/database.py src/application/readmodels/runtime_health.py src/application/readmodels/runtime_overview.py src/application/readmodels/runtime_positions.py src/application/readmodels/runtime_orders.py src/interfaces/api_console_runtime.py src/interfaces/api.py src/infrastructure/pg_position_repository.py src/infrastructure/pg_order_repository.py`，通过。
- 外部 Claude 已完成本轮定向测试：
  - 共 90 个测试通过，0 失败
  - 新增/修改测试覆盖：
    - runtime health / overview PG probe
    - console runtime `_get_account_snapshot` 回退逻辑
    - runtime positions PG-first + snapshot enrich
    - `/api/v3/positions` PG-first
    - `/api/v3/orders` / `/api/v3/orders/tree` / `/api/v3/orders/batch`
- 当前剩余缺口：
  - `PositionInfo` 缺少 `current_price` / `mark_price`，导致 positions enrich 不完整
  - `PgOrderRepository` / 其他 PG repo 仍缺真实 PostgreSQL 集成测试
- 未运行 pytest。

### 2026-04-27 PG Repository 集成验证完成

- 外部 Claude 已完成 4 个 PG Repository 的真实 PostgreSQL 集成测试：
  - `tests/integration/test_pg_order_repo.py`
  - `tests/integration/test_pg_execution_intent_repo.py`
  - `tests/integration/test_pg_position_repo.py`
  - `tests/integration/test_pg_execution_recovery_repo.py`
- 本轮集成测试结果：
  - 90 passed, 0 failed, 0 skipped
- 两轮合计：
  - 180 passed, 0 failed
- 当前状态更新：
  - execution PG 主线的代码修复、只读观测面修复、以及 4 个 PG Repository 的真实 PG 验证均已完成
  - 剩余项降为非阻塞增强：
    - `PositionInfo.current_price / mark_price` 语义补齐
    - `list_active()` / `list_blocking()` 语义澄清

### 2026-04-27 后续方向收敛

- 已根据最新判断把后续优先级从“继续迁库”调整为“边界治理优先”：
  1. 固化 execution PG 主线已完成的边界定义
  2. 收紧 runtime observability 口径
  3. 推进配置冻结与参数链防污染
  4. 收紧 research / runtime 隔离
  5. 最后再评估 `signals / attempts` 是否需要迁 PG
- 当前不再默认把 `signals` / `signal_attempts` / config 表迁移当作下一步主任务。

### 2026-04-27 五份审计报告已并入主线重排

1. ✅ 已重新通读并筛选以下 5 份文档的当前有效风险：
   - `2026-04-26-full-db-source-audit.md`
   - `2026-04-26-runtime-observation-audit.md`
   - `sqlite-retirement-design.md`
   - `2026-04-26-pg-execution-mainline-verification-assets.md`
   - `2026-04-26-research-chain-audit-and-config-freeze-design.md`
2. ✅ 已识别哪些风险仍然有效，哪些已被最新代码/测试解除：
   - 继续有效：边界未冻结、config 可被研究链污染、signals/attempts 角色未定型
   - 已解除或需按最新代码复核：orders API fallback、PG health 永久降级、PG repo 无验证、PgOrderRepository 主路径不完整
3. ✅ 已新增主线汇总文档：
   - `docs/planning/2026-04-27-boundary-governance-mainline-plan.md`
4. ✅ 已把当前主线重新定义为“边界治理优先”：
   - execution truth
   - observability
   - config freeze / parameter governance
   - research / runtime isolation
5. ✅ 已明确当前不再默认继续推进：
   - `signals` 直接迁 PG
   - config 全域迁 PG
   - backtest / klines / history 迁 PG
   - 多实例 / 分布式语义扩展

### 2026-04-27 `signals` / `signal_attempts` 角色已重新定性

1. ✅ 已重新核对 `SignalPipeline` / `SignalRepository` / `PerformanceTracker` 代码路径。
2. ✅ 新结论：
   - `signals` 当前不是纯 observability，而是 **runtime pre-execution state**
   - `signal_attempts` 当前仍主要属于 observability / diagnosis
3. ✅ 这意味着后续不再把“signals / attempts 是否迁 PG”当作一个打包问题，而是拆成两条判断线：
   - `signals`：是否要消灭 execution 上游跨库边界
   - `signal_attempts`：是否值得为 observability 统一技术栈
4. ✅ 已同步新增汇总文档：
   - `docs/planning/2026-04-27-signal-domain-and-config-freeze-boundary-plan.md`

### 2026-04-27 Config Freeze / Research Isolation 下一轮实施项已明确

1. ✅ 已确认下一轮真正优先的是切断 runtime 被研究链污染的最短路径：
   - `ConfigManager.set_instance()`
   - profile switch API
   - Backtester 对全局 `ConfigManager` 的隐式依赖
2. ✅ 已把下一轮实施重点从“继续迁库”改为：
   - 配置来源优先级
   - active profile 切换门槛
   - 研究脚本与 runtime 的单例/共享配置隔离

### 2026-04-27 研究链污染最短路径已完成前两步

1. ✅ 外部 Claude 已完成 8 个研究/验证脚本的最小止血改造：
   - 仍保留 `ConfigManager.set_instance(config_manager)`
   - 但统一改为 `try/finally`，结束后执行 `ConfigManager.set_instance(None)`
   - 这意味着单例污染已从“持久残留”降为“仅在脚本执行期间存在”
2. ✅ 外部 Claude 已为 profile switch API 增加显式确认门槛：
   - `confirm != true` 时返回 `409`
   - `confirm=true` 才允许真正切换 active profile
3. ✅ 当前判断：
   - 这两步已经完成“最短污染路径切断”
   - 但 `Backtester -> ConfigManager.get_instance()` 的隐式依赖仍在，下一步应继续去掉

### 2026-04-27 Backtester 去全局单例依赖已完成

1. ✅ 外部 Claude 已对 `src/application/backtester.py` 做最小改造：
   - `Backtester.__init__()` 新增 `config_manager=None`
   - `run_backtest()` 优先使用 `self._config_manager`
   - 仅在未注入时才 fallback 到 `ConfigManager.get_instance()`
2. ✅ 对应的 8 个研究/验证脚本已同步改为显式注入 `config_manager=config_manager`
   - 不再需要 `ConfigManager.set_instance()`
3. ✅ 外部 Claude 已补最小测试：
   - `test_backtester_config_injection.py`
   - 连同既有相关测试共 46 passed
4. ✅ 当前判断：
   - runtime 被 research 链污染的三条最短路径已经全部切断：
     - 脚本级 `set_instance()` 残留污染
     - profile switch 无确认切换
     - Backtester 对全局 `ConfigManager` 的隐式依赖
   - 剩余工作转入“来源优先级正式化”和“边界文义固化”

### 2026-04-27 Runtime / Research 配置来源优先级 SSOT 已落盘

1. ✅ 已新增：
   - `docs/planning/2026-04-27-runtime-and-research-config-source-priority-ssot.md`
2. ✅ 已正式写清两条配置消费链：
   - runtime execution：`ResolvedRuntimeConfig` / `RuntimeConfigProvider`
   - research/backtest：显式 request/spec -> overrides -> 局部注入 -> research KV/defaults -> code defaults
3. ✅ 已把 `ConfigManager.get_instance()` 重新定性为：
   - 兼容保留
   - `legacy_fallback`
   - 非推荐路径
4. ✅ 当前这条边界治理子线已从“急性风险收口”推进到“规则固化”

### 2026-04-27 Backtester `legacy_fallback` 语义已显式化

1. ✅ 外部 Claude 已继续收口 `Backtester` 的兼容 fallback：
   - `ConfigManager.get_instance()` 保留
   - 但已被明确标记为 `legacy_fallback`
   - 仅在未显式注入 `config_manager` 时触发
2. ✅ 已补最小测试：
   - 显式注入时不触发 `legacy_fallback`
   - fallback 分支日志包含 `legacy_fallback`
3. ✅ 当前判断：
   - `Backtester` 这条链路已从“隐式全局依赖”收口到“显式注入优先 + 兼容 fallback 可见化”

### 2026-04-27 Runtime config snapshot 的真源提示已收紧

1. ✅ 外部 Claude 已补强 `runtime_config_snapshot.py` 的 `source_of_truth_hints`
2. ✅ 当前 hints 规则已覆盖：
   - `runtime_profile:{name}`
   - `{section}:resolved_from_profile`
   - `backend:environment`
   - `no_provider`
   - `provider_error`
   - `legacy_fallback`
3. ✅ 相关测试已通过（32/32）
4. ✅ 当前判断：
   - runtime config readonly 面现在已能更明确表达“配置从哪里来”

### 2026-04-27 `signals` 迁移策略已从“是否迁”调整为“何时有资格迁”

1. ✅ 已补充对 `signals` / `signal_attempts` / `signal_take_profits` 的进一步定性：
   - `signals` = runtime pre-execution state
   - `signal_attempts` = observability / diagnosis
   - `signal_take_profits` = signal 域附属观测数据
2. ✅ 已新增：
   - `docs/planning/2026-04-27-signals-migration-gate-and-domain-split.md`
3. ✅ 当前结论：
   - 不直接启动 `signals` 迁移
   - 先定义它进入下一窗的准入条件
   - 不再把 `signals / signal_attempts` 当成一个打包迁移对象

### 2026-04-27 Positions enrich 的最后已知缺口已修复

1. ✅ 外部 Claude 已完成 `PositionInfo.mark_price` 语义补齐：
   - `src/domain/models.py` 为 `PositionInfo` 新增 `mark_price`
   - `ExchangeGateway` 构造 `PositionInfo` 时捕获 CCXT `markPrice`
   - `RuntimePositionsReadModel` 改读 `mark_price`
   - `/api/v3/positions` 的 enrich 路径也改读 `mark_price`
2. ✅ 对应测试已通过：
   - 本轮 101 passed, 0 failed
   - positions enrich 的 PG+snapshot、snapshot-only、exchange enrich、exchange fallback 路径均已覆盖
3. ✅ 当前判断：
   - `positions` 读面的价格 enrich 断裂点已全部修复
   - 当前 execution PG 主线与 observability/config freeze 子线都已无已知 P0/P1 主阻塞

### 2026-04-27 最后两个语义尾巴已收口

1. ✅ `list_active()` / `list_blocking()` 的职责边界已补入代码注释与规划文档：
   - `list_active()` = 当前可执行任务
   - `list_blocking()` = 当前阻止新开仓的任务
2. ✅ profile switch 的规则已在接口 docstring 和规划文档中固定：
   - 更新配置域 active profile
   - 默认对后续启动 / 显式 reload 生效
   - 不应被理解为静默热切当前 execution runtime
3. ✅ 当前窗口从“主线修复”到“边界治理收口”的最后两个尾巴已完成

### 2026-04-27 PG 闭环窗口新增立即修复已完成

1. ✅ 已直接修复 `positions` dust 残余导致的僵尸仓位风险
   - `src/application/position_projection_service.py`
   - 新增 `POSITION_CLOSE_DUST_LIMIT`
   - 对应测试已补，相关 suite 通过
2. ✅ 已直接修复 PG 持锁区内 DB I/O 长时间悬挂的低成本硬化项
   - `src/infrastructure/database.py`
   - 新增 PG command / statement / lock / idle tx / pool timeout 配置
   - 新增 `tests/unit/test_pg_database_timeouts.py`
3. ✅ 本轮验证结果
   - `tests/unit/test_position_projection_service.py`：41 passed, 1 skipped
   - `tests/unit/test_pg_database_timeouts.py`：3 passed
   - `tests/unit/test_runtime_health_overview_probe.py`：7 passed
   - `tests/unit/test_v3_positions_api.py`：9 passed
4. ✅ 当前决策
   - 不在本窗口继续迁 `signals / signal_attempts`
   - 继续把它们视为下一窗的独立域决策，而不是顺手并进 execution PG 闭环

### 2026-04-27 Signals PG Window 准备工作已完成并开始落骨架

1. ✅ 已新增 `docs/planning/2026-04-27-signals-pg-window-design.md`
   - 明确两套方案
   - 当前选定 Hybrid 路线
2. ✅ 已开始代码骨架：
   - `src/infrastructure/pg_signal_repository.py`
   - `src/infrastructure/hybrid_signal_repository.py`
   - `src/infrastructure/pg_models.py` 新增 PG `signals` / `signal_take_profits` ORM
   - `src/infrastructure/core_repository_factory.py` 新增 `create_runtime_signal_repository()`
3. ✅ 已切掉 `SignalPipeline` 对 `repository._db` 的直接依赖
   - 改为仓储方法驱动的 cache rebuild / opposing signal lookup
4. ✅ `main.py` / `api.py` runtime 装配已切到 runtime signal factory
5. 🟡 当前测试状态
   - `py_compile` 通过
   - `test_console_runtime_routes.py -k signals` 通过
   - `test_signal_repository.py` 通过
   - `test_signal_pipeline.py` 有 1 个旧的 dedup key 大小写断言失败（与当前迁移骨架无直接关系）
   - `test_signal_repository_s6_2.py` 有 8 个 SQLite in-memory 连接旧问题（pre-existing / fixture 风格问题）

### 2026-04-27 19:45 Research Control Plane 默认基线漂移已修复

1. ✅ 根据外部 RCA 确认：
   - 前端默认跑 2025 年回测与旧基线不一致，主因是默认参数漂移，而不是 Research Control Plane 链路断裂
2. ✅ 已完成核心修复：
   - `ResearchEngineCostSpec` / `EngineCostSpec` 默认成本改为旧 BNB9 口径
   - `LocalBacktestResearchRunner` 对 `backtest_eth_baseline` / `sim1_eth_runtime` 解析出显式 baseline runtime overrides
   - `LocalBacktestResearchRunner` 从解析后的 overrides 派生显式 `OrderStrategy`，防止未来全局默认值再次影响 Research 基线
   - run artifact 的 `spec_snapshot` 记录 `resolved_runtime_overrides` 与 `resolved_order_strategy`
   - Research backtest adapter 显式注入 `api._config_manager`
   - `NewBacktest.tsx` 默认成本对齐，时间输入/输出改为 UTC 语义
3. ✅ 已补针对性测试：
   - baseline profile 自动解析 runtime overrides
   - 显式 runtime overrides 优先于 profile 默认
   - unknown profile 不自动发明 overrides
   - research 默认成本断言
4. ✅ 已执行验证：
   - `./venv/bin/python -m pytest tests/unit/test_research_models.py tests/unit/test_research_repository.py tests/unit/test_research_control_plane_service.py tests/unit/test_research_jobs_api.py -v` → 108 passed
   - `cd gemimi-web-front && npm run lint` → passed
   - `cd gemimi-web-front && npx vitest run src/services/api.test.ts` → 18 passed
   - `./venv/bin/python -m pytest tests/unit/test_research_control_plane_service.py -v` → 22 passed
5. 下一步建议：
   - 外部测试窗口重跑旧脚本与 Research Control Plane 同一窗口对比，确认剩余差异是否来自数据源、成交模型或旧脚本特殊逻辑

### 2026-04-27 Research UI 可用性增强第一阶段

1. ✅ 已完成现有页面盘点并确认路线：
   - 不废弃重做
   - 不新增研究首页抢主入口
   - 先增强 `/research/new`、`/research/jobs`、`/research/runs/:id`
2. ✅ 已新增方案文档：
   - `docs/planning/architecture/2026-04-27-research-ui-usability-enhancement-plan.md`
3. ✅ 已新增后端只读端点：
   - `GET /api/research/runs/{run_result_id}/report`
   - 读取 `result.json` artifact，用于前端展示权益曲线和逐笔交易
4. ✅ 已增强前端：
   - 导航 `研究任务` -> `回测历史`
   - `/research/new` 中文化，并说明默认 ETH 基线
   - `/research/jobs` 增加概览统计、参数摘要、收益/回撤/胜率/交易数
   - `/research/runs/:id` 展示实际生效参数、权益曲线、逐笔交易、候选策略入口
5. ✅ 已执行验证：
   - `./venv/bin/python -m py_compile src/application/research_control_plane.py src/interfaces/api_research_jobs.py` -> passed
   - `./venv/bin/python -m pytest tests/unit/test_research_control_plane_service.py tests/unit/test_research_jobs_api.py -v` -> 45 passed
   - `cd gemimi-web-front && npm run lint` -> passed
   - `cd gemimi-web-front && npx vitest run src/services/api.test.ts` -> 18 passed
6. 待补杂活：
   - API adapter 测试补 `getResearchRunReport`
   - 后端 API 单测补 `/runs/{id}/report`
   - 浏览器冒烟确认权益曲线和逐笔交易渲染

### 2026-04-27 Research UI v2.0 PRD 已沉淀

1. ✅ 已根据 PM 版 PRD 更新研究台 UI 规划：
   - `docs/planning/architecture/2026-04-27-research-ui-usability-enhancement-plan.md`
2. ✅ 已调整优先级：
   - Phase 1：Clone & Tweak、回测历史资产化、详情页策略诊疗室
   - Phase 2：正式图表能力（ECharts 优先）与端到端验证
   - Phase 3：候选策略资产化
   - Phase 4：策略对比与研究资产管理
3. ✅ 当前执行策略：
   - 由 Codex 负责产品/架构规划与验收标准
   - 前端页面 v2 改造属于明确实施任务，可交 Claude 执行
   - 技术选型服务产品体验，不再把图表库争论放在主线中心

### 2026-04-27 Runtime Cockpit PRD 已纳入规划

1. ✅ 已根据 Runtime 模块产品 PRD 新增规划文档：
   - `docs/planning/architecture/2026-04-27-runtime-cockpit-experience-upgrade-plan.md`
2. ✅ 已明确 Runtime 与 Research 的产品边界：
   - Research = 实验室，回答策略是否值得继续研究
   - Runtime = 驾驶舱，回答资金和执行链是否安全
3. ✅ 已确认 Runtime 优先级：
   - 先做资金/风险/告警/环境隔离
   - 再做信号到执行的因果链
   - 最后分期做人工接管能力
4. ✅ 已明确安全降级：
   - 第一阶段不直接做一键清仓
   - 先规划暂停新开仓和单仓平仓
   - 所有危险动作必须依赖后端幂等、审计与状态确认

### 2026-04-27 前端双轨并行已定稿

1. ✅ 已确认 Research 和 Runtime 两条前端产品线可以并行：
   - 页面目录天然隔离
   - 用户目标不同
   - 数据域不同
   - 第一阶段 Runtime 不做危险写操作
2. ✅ 已新增执行计划：
   - `docs/planning/architecture/2026-04-27-frontend-dual-track-execution-plan.md`
3. ✅ 已完成当前页面勘察：
   - Research 页面集中在 `gemimi-web-front/src/pages/research/*`
   - Runtime 页面集中在 `gemimi-web-front/src/pages/runtime/*`
   - `/signals` 和 `/execution` 当前独立页面已存在，可作为 Runtime 因果链窗口处理
4. 下一步：
   - 交给 Claude 分两个窗口并行实施
   - Codex 后续做二次审查和产品验收

### 2026-04-28 前端双轨改造审查与修复

1. ✅ 已完成 Research / Runtime 前端改造的第一轮审查。
2. ✅ 已修复明确缺陷：
   - `RunDetail` 路由参数从错误的 `id` 改回 `run_result_id`
   - `RunDetail` 图表和逐笔交易改为优先使用 `/api/research/runs/{id}/report` artifact 数据
   - `加入候选策略`按钮从空转改为真实调用 `createCandidateRecord`
   - Runtime 状态中文映射兼容大写/小写状态值
   - Execution intent 映射兼容后端 `side` / `quantity` 字段
   - `SIM-1` 环境识别修正为 SIM
   - 回测历史的“对比这些回测”不再跳转到未接入的假闭环，改为禁用提示
   - 清理 `.next` / `next-env.d.ts` / `tsconfig.tsbuildinfo` 生成物污染
3. ✅ 本地验证：
   - `npm run lint` 通过
   - `npx vitest run src/services/api.test.ts src/pages/runtime/Execution.test.tsx` → 22 passed
   - `npm run build` 通过
   - `pytest tests/unit/test_research_jobs_api.py -v` → 26 passed
   - `pytest tests/unit/test_console_runtime_routes.py tests/unit/test_console_runtime_readmodels.py -v` → 47 passed
   - `pytest tests/unit/test_runtime_positions_pg_projection.py tests/unit/test_v3_positions_api.py -v` → 27 passed
4. ⚠️ 本地完整后端联调受限：
   - `python -m src.main` 在 Phase 4 初始化 Binance gateway 时被 `demo-dapi.binance.com` 返回 451 地区限制
   - 因此真实 API + 页面浏览器联调需要在 Mac mini Docker / Sim-1 环境执行
5. 待 Mac mini 验证：
   - `/research/new`
   - `/research/jobs`
   - `/research/runs/{id}`
   - `/runtime/overview`
   - `/runtime/portfolio`
   - `/signals`
   - `/execution`

### 2026-04-28 Mac mini 联调反馈收敛

1. ✅ 已吸收 Mac mini / Sim-1 前端联调报告：
   - 11 个页面均可渲染
   - 0 个 API 失败
   - 0 个阻塞性 console error
2. ✅ 已修复 D1：Runtime Overview enrichment 缺口
   - `RuntimeOverviewResponse` 新增：
     - `active_positions`
     - `active_signals`
     - `pending_intents`
     - `pending_recovery_tasks`
     - `total_equity`
     - `unrealized_pnl`
   - `RuntimeOverviewReadModel` 从 account snapshot / signal repo / intent repo / recovery repo 尽力聚合
   - 聚合失败时返回 `None`，不影响 overview 主响应
3. ✅ 已修复 D3：Signal status null 处理
   - 前端 adapter 不再把 `null` status 强制改成 `"--"`
   - `signalStatusLabel` 支持空值
   - Signals 页可正确显示“当前接口未提供结局状态”
4. ✅ 已修复 D2：Research 回测最大回撤区间高亮数据缺口
   - Backtester 已有 `debug_max_drawdown_detail.peak_ts/trough_ts`
   - `LocalBacktestResearchRunner._extract_summary_metrics()` 透传为：
     - `max_drawdown_start_ms`
     - `max_drawdown_end_ms`
   - `RunDetail` 的 ECharts 最大回撤 markArea 可以使用 summary metrics 渲染
5. ✅ 本轮验证：
   - `pytest tests/unit/test_console_runtime_readmodels.py tests/unit/test_console_runtime_routes.py -v` → 48 passed
   - `npm run lint` → passed
   - `npx vitest run src/services/api.test.ts src/pages/runtime/Execution.test.tsx` → 22 passed
   - `npm run build` → passed
   - `pytest tests/unit/test_research_control_plane_service.py tests/unit/test_research_jobs_api.py -v` → 48 passed

### 2026-04-28 -- Research UI v2.0 前端产品化改造完成

1. ✅ `/research/new` 新建回测页改造：
   - 表单分区：基础信息、时间窗口、策略与资金、高级设置（折叠）
   - 时间窗口快捷按钮：最近 1 个月、最近半年、2025 全年
   - "本次回测摘要"自然语言说明
   - clone_run 场景展示"已从某次回测复用配置"
   - 提交按钮 loading/disabled 状态
2. ✅ `/research/jobs` 回测历史页改造：
   - 隐藏 rj/rr hash ID，名称+备注为主身份
   - 金融色彩：盈利绿色、亏损红色、回撤红色
   - 增加筛选：状态、交易对、基线配置、收益区间
   - 支持 2-4 条勾选，底部浮出"对比这些回测"按钮
   - 操作列增加"复制配置"快捷入口
3. ✅ `/research/runs/:id` 回测详情页改造（策略诊疗室）：
   - 顶部动作：基于此配置新建回测、加入候选策略
   - KPI 增加：年化收益率、盈亏比 Profit Factor、最大连续亏损
   - ECharts 权益曲线 + 回撤水下图（替代临时 SVG）
   - 逐笔交易表：入场/出场时间、方向、价格、平仓原因、手续费、净盈亏
   - 实际生效参数：resolved_runtime_overrides + resolved_order_strategy 人话展示
   - 调试信息折叠：artifact 路径、raw JSON、run ID
4. ✅ `/research/candidates` 候选策略页改造：
   - 机器状态翻译：PASS_STRICT→严格通过、REJECT→不建议等
   - 警告翻译：sortino_missing_or_suspect→索提诺比率异常等
   - 隐藏 git hash，名称截断+tooltip
5. ✅ `/research/compare` 策略对比页改造：
   - 选择器 option 显示短名称+状态标记
   - 差异列 0 值用低对比度显示（不再大量 --）
   - 基准/候选名称截断展示
6. ✅ ECharts 安装：echarts@6.0.0 + echarts-for-react@3.0.6
7. ✅ 类型追加：ResearchRunResult 增加 debug_equity_curve/positions/artifact_path/git_commit
8. ✅ research-format.ts 新增工具函数：computeProfitFactor、computeMaxConsecutiveLosses、computeAnnualizedReturn、directionLabel/Variant、pnlRatioClass、warningLabel、reviewLabel
9. ✅ 验证结果：
   - npm run lint → EXIT: 0
   - npx vitest run → 22 passed
   - npm run build → 成功

### 2026-04-28 -- Research 重复回测 report_id 冲突修复

1. ✅ 根因确认：
   - `backtest_reports.id` 原公式为 `rpt_{strategy_id}_{backtest_start}_{parameters_hash[:8]}`
   - 同一策略、同一窗口、同一参数组合被不同 Research job 复跑时会生成相同 report_id
   - SQLite 主键触发 `UNIQUE constraint failed: backtest_reports.id`
2. ✅ 修复策略：
   - `parameters_hash` 继续表达“同一参数组合”，用于聚类和历史对比
   - `report_id` 改为每次保存唯一：追加短 UUID 后缀
   - 不改变 `save_report()` 签名，避免影响旧 `/api/backtest/run` 和既有集成测试
3. ✅ 增补测试：
   - `test_duplicate_parameter_runs_create_distinct_reports`
   - 验证同参数复跑能保存两条报告，且两条报告：
     - `id` 不同
     - `parameters_hash` 相同
4. ✅ 验证：
   - `pytest tests/unit/test_backtest_repository.py -v` → 29 passed
   - `pytest tests/unit/test_research_control_plane_service.py tests/unit/test_research_jobs_api.py -v` → 48 passed

### 2026-04-28 H3a Follow-through Feature Check

**完成**: H3a 入场前特征预测低 follow-through 实验

**产出**:
- `scripts/run_h3a_followthrough_feature_check.py` — 特征计算 + 分桶分析脚本
- `reports/research/h3a_followthrough_feature_check_2026-04-28.json` — 实验结果
- `docs/planning/2026-04-28-h3a-followthrough-feature-check.md` — 分析报告

**关键发现**:
- 5 个特征有 >=20pp 统计区分度（price_dist_ema_1h 最佳 27.9pp）
- 但绝对水平重叠：2023 B3 HFT=45% ≈ 2024 B1 HFT=50%
- Skip-B1 过滤器：2023 +19/+156，2024 -6539/-6395
- 2023 悖论：高 FT 桶 PnL 更差

**判定**: H3a 不通过，H3 动态退出方向关闭

**研究链总结**: H0→H1→H2→H3→H3a 全链完成。2023 亏损是市场环境不匹配，不是参数可调优的。建议接受 -3924 为 2024/2025 alpha 的固有成本。

### 2026-04-28 M1 Pinbar Toxic State Avoidance — 4/4 单因子 filter 全部 PASS

**完成**: M1 toxic state avoidance 实验，测试 4 个单因子 regime filter

**产出**:
- `scripts/run_pinbar_toxic_state_m1.py` — 独立撮合 + 4 实验 + verdict 逻辑
- `reports/research/pinbar_toxic_state_m1_2026-04-28.json` — 完整结果 JSON
- `docs/planning/2026-04-28-pinbar-toxic-state-avoidance-m1.md` — 分析报告

**关键结果**:
- E0 baseline: 3yr PnL = -2,158
- E1 ema_4h_slope: 3yr PnL = **+1,314** (2023 loss ↓51.2%, 2024 profit ↑88%)
- E2 recent_72h: 3yr PnL = **+1,200** (2025 loss -1,499 → -29)
- E3 volatility: 3yr PnL = **+1,034** (trade reduction 最低 17.6%)
- E4 donchian_dist: 3yr PnL = **+1,042** (2023 loss ↓71.3%, MaxDD 18.04%)
- **所有 4 实验 PASS 全部 5 项标准**

**研究链推进**: M0 诊断"问题在 regime" → M1 证明"跳过 toxic regime 解决问题"。因果链闭合。

### 2026-04-28 M1b Pinbar Toxic State Parity Check — E4 PASS, E1 FAIL

**完成**: M1b parity check，在官方 Backtester 口径下验证 E1/E4 filter

**产出**:
- `scripts/run_pinbar_toxic_state_m1b_parity.py` — Parity 撮合引擎（匹配官方参数）
- `reports/research/pinbar_toxic_state_m1b_parity_2026-04-28.json` — 完整结果 JSON
- `docs/planning/2026-04-28-pinbar-toxic-state-m1b-parity.md` — 分析报告

**关键结果**:
- E0 parity: 3yr PnL = -14,886（vs official +9,066，差距来自 concurrent positions + compounding）
- E1 ema_4h_slope: 3yr PnL = -10,027 (+4,860)，2023 loss ↓15.4% → **FAIL**
- E4 donchian_dist: 3yr PnL = -8,695 (+6,191)，2023 loss ↓32.6% → **PASS**

**结论修正**:
- E1 降级为 proxy-only（parity 口径下优势减弱）
- E4 保留，可在正式 backtester 验证

### 2026-04-28 C1 Pinbar + T1 Portfolio Proxy — CONDITIONAL PASS

**完成**: C1 组合价值验证，Pinbar baseline (E0) + T1-R 在 5 种权重下组合分析

**产出**:
- `scripts/run_c1_pinbar_t1_portfolio.py` — 组合分析脚本
- `reports/research/c1_pinbar_t1_portfolio_proxy_2026-04-28.json` — 完整结果 JSON
- `docs/planning/2026-04-28-c1-pinbar-t1-portfolio-proxy.md` — 分析报告

**关键结果**:
- Pinbar: 3yr PnL +435, MaxDD 33.6%, 2023 -3,180
- T1-R: 3yr PnL +2,039, 2023 +1,358, Top 3 winners 108.4% (fragile)
- Correlation (weekly MTM): 0.195（弱正相关）
- P60_T40: 3yr PnL +1,077, MaxDD 19.5%, 2023 -1,365 (改善 57%)
- P50_T50: 3yr PnL +1,237, MaxDD 17.8%, 2023 -911 (改善 71%)
- 移除 T1 Top 3 后 P60_T40 仍为 +193（组合不依赖 T1 大赢家）

**判定**: CONDITIONAL PASS — 组合改善显著，但 T1 fragility 需 OOS 验证

**建议下一步**:
- 在正式 Backtester v3_pms 中验证 P60_T40 权重组合
- T1 需要 OOS 验证（fragility 在 OOS 中可能更严重）
- 需要更真实的 MTM equity curve（当前 proxy 有仓位模型简化）

### 2026-04-29 P0 / R1b 收口：E4 official 验证与资金参数审计

**完成**:
- P0 `Pinbar + E4 donchian_distance` 已走通 official `v3_pms + dynamic strategy` 路径。
- R1b capital allocation 二次审计已完成，纠正 R1 原始 MaxDD 口径错误，并确认在 `MaxDD <= 35%` 约束下存在 2 组可行配置。

**P0 关键结果**:
- E4 确认真实生效：`rejection_stats` 中出现 `donchian_distance` 拦截。
- 2023 亏损显著降低：约 `-4518 -> -1903`，loss reduction 约 `57.9%`。
- 但 2024/2025 收益被过度过滤，3yr PnL 从 `+3789` 降为 `-1924`。
- 判定：`FAIL`。E4 是有效风险因子，但当前固定阈值不适合作为硬过滤器进入组合或 runtime。

**R1b 关键结果**:
- R1 原报告 MaxDD 严重低估，`report.max_drawdown` 不能作为真实回撤约束指标。
- R1 首轮 audit 也过度悲观：只审 3 组配置，并把 realized curve 误称为 mark-to-market。
- R1b 基于 `debug_equity_curve` 审计完整 56 组配置，确认 2 组满足 `MaxDD <= 35%`：
  - `exposure=1.25, risk=0.5%`: PnL `+2346`, MaxDD `33.74%`
  - `exposure=1.0, risk=0.5%`: PnL `+2113`, MaxDD `32.42%`

**当前感受/判断**:
- 这份资金参数报告不够“激励”，不是因为收益目标错，而是因为 `MaxDD <= 35%` 在当前 Pinbar baseline 上非常强约束。
- 2023 亏损年决定了资金上限；为了守住 35% 回撤，risk 只能压到 `0.5%`，自然无法复现此前看到的 2024/2025 高收益。
- 这说明后续应把研究拆成两条线：`稳健约束线` 和 `激励上限线`，不要用同一个约束同时追求心理激励与实盘准入。

**产出**:
- `scripts/run_p0_pinbar_e4_official.py`
- `docs/planning/2026-04-29-p0-pinbar-e4-official-validation.md`
- `reports/research/p0_pinbar_e4_official_validation_2026-04-29.json`
- `scripts/run_r1b_capital_allocation_audit_v2.py`
- `docs/planning/2026-04-29-r1b-capital-allocation-audit-v2.md`
- `reports/research/r1b_capital_allocation_audit_v2_2026-04-29.json`

**下一步**:
- P0a：对 E4 被过滤交易做收益来源切片，确认 2024/2025 被过滤部分是否为主要盈利来源。
- R2：设计激励型资金上限实验，不再使用 `MaxDD <= 35%` 作为唯一约束，可改用分年度、分阶段或收益/回撤分层目标。
- 组合线暂缓：不直接推进 `Pinbar(E4) + T1`，先解决 E4 硬过滤过度牺牲收益的问题。

### 2026-04-28 C2 Pinbar + T1 Portfolio Official Parity Check — CONDITIONAL FAIL

**完成**: C2 官方口径组合验证，Pinbar via Backtester v3_pms + T1-R matched compounding

**产出**:
- `scripts/run_c2_pinbar_t1_portfolio_parity.py` — 组合验证脚本
- `reports/research/c2_pinbar_t1_portfolio_parity_2026-04-28.json` — 完整结果 JSON
- `docs/planning/2026-04-28-c2-pinbar-t1-portfolio-parity.md` — 分析报告

**关键结果**:
- Pinbar (official continuous): 3yr PnL +75 (vs C1 proxy +435)
- Pinbar (yearly sum): 3yr PnL +1,492, 2023 -5,233, 2024 +3,701, 2025 +3,024
- Pinbar MaxDD: 67.94% (vs C1 proxy 33.6%)
- T1-R: 3yr PnL +2,039 (unchanged), Top 3 = 108.4%
- Correlation (weekly MTM): 0.050 (接近零相关, vs C1 0.195)
- P60_T40: 3yr PnL +861, MaxDD 39.36%, 2023 -2,931 (49% 改善)
- P50_T50: 3yr PnL +1,057, MaxDD 32.65%, 2023 -2,216 (62% 改善)
- **移除 T1 Top 3 后**: P60_T40 = -24 (变负!), P50_T50 = -48 (变负!)
- P80_T20/P70_T30 移除 Top 3 后勉强正 (+26/+1)

**判定**: CONDITIONAL FAIL — 组合 PnL↑/DD↓ 仍成立，但移除 T1 Top 3 后 P60_T40/P50_T50 变负

**核心问题**:
- Pinbar continuous PnL (+75) 太低 — compounding 下 2023 大亏严重拖累复利
- T1 fragility 在 official 口径下更致命 — 组合对 T1 Top 3 依赖度从 C1 的可控变为 C2 的致命
- 没有权重组合同时满足 "2023 改善 >=40%" 和 "移除 T1 Top 3 后不崩"

### 2026-04-28 M1c E4 Donchian Distance Official Check — PASS

**完成**: M1c E4 Donchian distance toxic filter 在 official/continuous 口径下验证

**产出**:
- `scripts/run_m1c_donchian_distance_official_check.py` — M1c 实验脚本
- `reports/research/m1c_donchian_distance_official_check_2026-04-28.json` — 完整结果 JSON
- `docs/planning/2026-04-28-m1c-donchian-distance-official-check.md` — 分析报告

**关键结果**:
- E0 (baseline continuous): 3yr PnL -7,230, MaxDD MTM 72.89%, trades 203
- E4 (filter continuous): 3yr PnL -4,024, MaxDD MTM 40.48%, trades 148
- 3yr PnL Δ: +3,206 (44.4% 改善)
- 2023 loss reduction: 34.7% (>= 25%)
- 2024/25 loss reduction: 58.1% (E0 baseline negative)
- Trade reduction: 27.1% (<= 40%)
- MaxDD MTM: 72.89% → 40.48% (-32.41pp)
- Skipped trades (69): counterfactual PnL -2,886, avg -41.83 (确认有毒)
- Sharpe: -2.517 → -1.961, Sortino: -2.154 → -1.831

**判定**: PASS — 全部 5 项标准通过

**跨口径一致性**: E4 在 M1 (proxy), M1b (parity year-by-year), M1c (parity continuous) 三种口径下均 PASS

**下一步**:
- 在正式 Backtester 中实现 donchian distance filter（当前 backtester 不支持）
- 用 official backtester 跑 E4 continuous baseline
- 如果 official E4 continuous PnL > 0，做 Pinbar(E4) + T1 组合验证

### 2026-04-28 -- M1d Donchian Distance Filter 实现设计（design-only）

1. ✅ 探索阶段：两个 Agent 子任务完成
   - Agent 1: Filter 架构探索 — FilterContext 无 N-bar 历史，有状态 filter 通过 update_state() 积累内部状态
   - Agent 2: Backtester 信号流探索 — kline_history 在 run_all() 中存在但只传给策略不传给过滤器
2. ✅ 设计文档完成: `docs/planning/2026-04-28-m1d-donchian-distance-implementation-design.md`
   - A: 推荐 — 有状态通用 filter `donchian_distance`，内部维护滚动窗口
   - B: 三个备选方案（修改 FilterContext / Pinbar 专用 / 预计算），均不推荐
   - C: 只需修改 `filter_factory.py`（新增 class + registry + create 分支）+ 新增测试文件
   - D: 数据流设计（update_state 积累 high → check 时排除当前 bar 计算 dc_high）
   - E: 参数模型（lookback=20, threshold=-0.016809, direction_aware=True, enabled=False）
   - F: 未来函数防护（排除当前 K 线，只用前 N 根历史 high 计算 Donchian 上轨）
   - G: 测试计划（10 单元 + 3 集成 + 2 回归 + 1 对齐）
   - H: 建议现在实现，分两步（research/backtest 可用 → Pinbar(E4)+T1 组合验证）
3. ✅ 关键设计决策:
   - 不修改 FilterContext（不破坏现有架构）
   - 不修改 strategy_engine.py / backtester.py（完全向后兼容）
   - enabled=False 安全默认（sim1_eth_runtime 不受影响）
   - 排除当前 K 线计算 Donchian（比 M1c 脚本更保守，防止未来函数）

**下一步**:
- 用户 review 设计文档
- 确认后实施第一步（filter_factory.py 新增 DonchianDistanceFilterDynamic，~2h）

### 2026-04-29 -- R2 资金配置搜索（参数注入修复 + 全量运行）

**背景**:
- R1 搜索结果异常：所有 168 组配置返回完全相同的结果
- 根因：脚本层参数注入错误（使用 `BacktestRuntimeOverrides` 传递风险参数，但该类不包含这些字段）
- 历史 bug 已修复：cb06ea0 (positions=[])、96f0328 (三层约束)、44e9694 (risk_overrides 消费)

**修复内容**:
1. ✅ 使用 `RiskConfig` 传递风险参数（而非 `BacktestRuntimeOverrides`）
2. ✅ Sanity check 验证通过（2023 年 4 组配置，参数正确生效）
3. ✅ Risk 参数生效：PnL 差异 2,789.82 USDT
4. ✅ Exposure 参数生效：Trades 差异 11 笔
5. ✅ 结果多样性验证通过（4 组结果完全不同）

**Sanity Check 结果** (2023 年 4 组):
| Exposure | Risk | PnL (USDT) | MaxDD | Trades |
|----------|------|------------|-------|--------|
| 1.0 | 0.5% | -4,594.20 | 46.00% | 315 |
| 1.0 | 2.0% | -7,384.02 | 73.91% | 288 |
| 3.0 | 0.5% | -4,733.14 | 47.62% | 326 |
| 3.0 | 2.0% | -9,104.93 | 91.09% | 311 |

**全量搜索启动**:
- 进程 ID: 31313
- 配置数: 168 组（2023/2024/2025 各 56 组）
- 监控: 每 5 分钟汇报进度
- 预估耗时: ~82 分钟

**下一步**:
- 等待全量搜索完成
- 生成年度最优配置报告
- 对比 R1 结果，验证修复效果


**R2 搜索完成** (2026-04-29 13:01):
- ✅ 总配置数: 168 组（2023/2024/2025 各 56 组）
- ✅ 总耗时: ~25 分钟
- ✅ 错误数: 0
- ✅ 参数注入修复成功验证

**年度最优配置**:
| 年份 | Exposure | Risk | PnL (USDT) | MaxDD | Trades | WinRate |
|------|----------|------|------------|-------|--------|---------|
| 2023 | 1.0 | 0.50% | -4,594.20 | 46.00% | 315 | 34.3% |
| 2024 | 1.0 | 0.50% | -4,634.37 | 48.89% | 610 | 33.9% |
| 2025 | - | - | - | - | - | 无可行配置 |

**关键发现**:
1. 参数注入修复成功（Risk/Exposure 参数正确生效）
2. 2023/2024 最优配置相同（exposure=1.0, risk=0.5%）
3. 2025 年风险过高，所有配置 MaxDD > 50%
4. 与 R1 对比：R1 所有结果相同，R2 所有结果不同

**输出文件**: `reports/research/r2_capital_allocation_search_2026-04-29.json` (90KB)

### 2026-04-29 01:05 CST -- PG 全状态迁移窗口编码骨架

**完成**
- 切到 `codex/pg-full-migration`，已快进到最新 `dev`。
- 新增/修改 PG 默认仓储路由：默认运行态/研究态仓储在 `PG_DATABASE_URL` 存在且 `MIGRATE_ALL_STATE_TO_PG=true` 时走 PG；显式传入 SQLite `db_path` 或 `connection` 的测试/脚本继续走 SQLite。
- 新增 PG 仓储文件：
  - `pg_runtime_profile_repository.py`
  - `pg_config_entry_repository.py`
  - `pg_config_profile_repository.py`
  - `pg_config_snapshot_repository.py`
  - `pg_research_repository.py`
  - `pg_historical_data_repository.py`
  - `pg_backtest_repository.py`
  - `pg_reconciliation_repository.py`
- 扩展 `pg_signal_repository.py`，覆盖 `signal_attempts` 和 backtest signal id 查询。
- 扩展 `pg_models.py`，覆盖剩余主要状态/观察表的 ORM。
- 新增 `scripts/migrate_sqlite_state_to_pg.py`，用于明早执行 SQLite -> PG 数据搬迁。

**验证**
- `python3 -m py_compile` 覆盖新增/修改仓储模块，通过。
- `import src.infrastructure.pg_models` 通过。
- fake PG DSN 下默认仓储路由检查通过：Backtest/ConfigEntry/Profile/Snapshot/Historical/Reconciliation/Research/RuntimeProfile/Signal/Order 均返回 PG 实现。
- 轻量 SQLite 回归：runtime profile + research repository 通过；`test_config_profile.py` 有旧测试连接池隔离失败，需单独处理或在清理连接池后重跑。

**下一步**
- 明早优先跑真实 PG 初始化与 `scripts/migrate_sqlite_state_to_pg.py`。
- 再跑 PG 仓储集成测试和 API 冒烟。
- 旧配置管理 `config_repositories.py` 全套 CRUD 仍是机械大块，建议单独 Claude 窗口补齐 PG 版本或明确退役。

### 2026-04-29 07:23 CST -- PG 全状态迁移二次验收收口

**完成**
- 验收 Claude 的旧 config repositories PG 收尾结果。
- 发现并修复入口问题：Claude 初版只有 `StrategyConfigRepository` 直接接入默认构造路径，其他 6 个 repository 只存在工厂函数，`main.py/api.py` 直接构造时仍可能落 SQLite。
- 已补齐默认构造 PG 路由：
  - `RiskConfigRepository`
  - `SystemConfigRepository`
  - `SymbolConfigRepository`
  - `NotificationConfigRepository`
  - `ConfigSnapshotRepositoryExtended`
  - `ConfigHistoryRepository`
- 修正 `config_repository_factory.py`，统一调用 `should_use_pg_for_default_repository()`，避免未配置 `PG_DATABASE_URL` 时仅因 `MIGRATE_ALL_STATE_TO_PG=true` 误切 PG。
- 修复 `test_config_profile.py` 的 SQLite connection pool 隔离问题。

**验证**
- `python3 -m py_compile src/infrastructure/config_repository_factory.py src/infrastructure/repositories/config_repositories.py src/infrastructure/pg_config_repositories.py src/infrastructure/pg_models.py scripts/migrate_sqlite_state_to_pg.py` 通过。
- `MIGRATE_ALL_STATE_TO_PG=false python3 -m pytest tests/unit/test_runtime_profile_repository.py tests/unit/test_research_repository.py tests/unit/test_config_profile.py -q` 通过：60 passed。

**剩余**
- 未跑真实 PG 数据搬迁。
- 未跑全量测试。
- 需要在 PG 环境执行迁移脚本并抽样核对表计数/关键行。

### 2026-04-29 08:10 CST -- Docker PG 真实迁移验证

**完成**
- 使用 Docker 中的 `dingdingbot-pg` 执行真实 PG 初始化与 SQLite -> PG 搬迁。
- 修复 `scripts/migrate_sqlite_state_to_pg.py` 的实库兼容问题：
  - 支持直接运行脚本时自动加入项目根目录到 `sys.path`。
  - `signal_take_profits` 旧 SQLite 数字 FK 映射到 PG 业务 `signal_id`。
  - `runtime_profiles.profile_json` 映射为 PG `profile_payload`。
  - `research_jobs.spec_json` 映射为 PG `spec_payload`，并支持从 `spec_ref` artifact 兜底读取。
  - `research_run_results` 的 `*_json` 字段映射到 PG JSONB 字段。
  - `candidate_records.risks_json` 映射为 PG `risks`。
  - 清洗历史脏数据：`backtest_reports.sharpe_ratio` 中的 JSON positions 迁移到 `positions_summary`，避免 Decimal/数值字段污染。
  - JSONB 字段通过 raw SQL 批量插入时统一序列化为 JSON 字符串。
  - `klines` 改为批量插入并分批提交，避免 82 万行逐行迁移过慢。
- 迁移脚本执行完成：`[done] migration copy attempted rows=831594`。

**Docker PG 表计数抽样**
- `orders`: 6686
- `signals`: 280
- `signal_take_profits`: 560
- `runtime_profiles`: 1
- `config_entries_v2`: 23
- `config_profiles`: 1
- `backtest_reports`: 35
- `position_close_events`: 512
- `klines`: 823128
- `config_snapshot_versions`: 1
- `research_jobs`: 6
- `research_run_results`: 5
- `candidate_records`: 1
- `optimization_history`: 343

**验证**
- `python3 -m py_compile scripts/migrate_sqlite_state_to_pg.py` 通过。
- 非破坏性 PG smoke 通过：
  - PG connectivity probe: `True`
  - active runtime profile: `sim1_eth_runtime`
  - research jobs/runs/candidates 可查询
  - backtest reports 计数可查询
  - ETH/USDT:USDT 1h kline range: `(1609459200000, 1774998000000)`
  - signals/orders 可查询
- 显式 SQLite 路径回归仍通过：
  - `MIGRATE_ALL_STATE_TO_PG=false python3 -m pytest tests/unit/test_runtime_profile_repository.py tests/unit/test_research_repository.py tests/unit/test_config_profile.py -q`
  - 60 passed

**注意**
- `tests/integration/conftest.py` 对核心 PG 表有 `TRUNCATE` autouse fixture，因此本次没有在已迁移数据上直接跑这些集成测试，避免擦掉迁移结果。
- 未执行全量测试。

### 2026-04-29 08:35 CST -- PG 迁移审查问题修复

**审查结论**
- 误切 PG：审查指出的旧注释确实过期；本窗口目标已从“小范围 intent PG”推进到“PG 全状态迁移”。但 `OrderRepository()` 默认构造此前会被全局 `MIGRATE_ALL_STATE_TO_PG` 拉入 PG，可能绕过 `CORE_ORDER_BACKEND=sqlite` 的细粒度控制，已修复。
- SQLite engine reset：`close_db()` 只 dispose `_engine` 但不复位，虽然 SQLAlchemy disposed engine 通常可重连，但热重载语义不够清晰，已改为 dispose 后清空 `_engine` 和默认 sessionmaker。
- 双轨路由：核心订单仓储现在按 `CORE_ORDER_BACKEND`；非核心状态仓储继续按 `MIGRATE_ALL_STATE_TO_PG`。职责边界已收紧。
- Numeric 精度：`NUMERIC(30, 8)` 对长尾币价格/数量不够宽，已扩展为 `NUMERIC(36, 18)`。
- active position 幂等：新增 PG 部分唯一索引 `uq_positions_active_symbol_direction`，约束同一 `symbol + direction` 只能存在一个未关闭仓位。

**改动**
- `src/infrastructure/database.py`
  - 删除过期“小范围实切”注释。
  - `close_db()` 复位 SQLite `_engine` 和默认 sessionmaker，PG engine/sessionmaker 继续复位。
- `src/infrastructure/order_repository.py`
  - 默认构造 PG 路由改为尊重 `get_core_backend_settings()["order"]`，避免 `CORE_ORDER_BACKEND=sqlite` 时误切 PG。
- `src/infrastructure/pg_models.py`
  - 所有 `Numeric(30, 8)` 扩展为 `Numeric(36, 18)`。
  - 新增 `uq_positions_active_symbol_direction` partial unique index。
- `db_scripts/2026-04-22-pg-core-baseline.sql`
  - 同步扩展 numeric 精度。
  - 同步新增 active position partial unique index。
- Docker PG 实库已执行 ALTER：
  - 所有 public schema 中 `numeric(30,8)` 列扩展为 `numeric(36,18)`。
  - 已创建 `uq_positions_active_symbol_direction`。

**验证**
- `python3 -m py_compile src/infrastructure/database.py src/infrastructure/order_repository.py src/infrastructure/pg_models.py scripts/migrate_sqlite_state_to_pg.py` 通过。
- `MIGRATE_ALL_STATE_TO_PG=false python3 -m pytest tests/unit/test_runtime_profile_repository.py tests/unit/test_research_repository.py tests/unit/test_config_profile.py -q`：60 passed。
- 路由 smoke：
  - `CORE_ORDER_BACKEND=sqlite` + `MIGRATE_ALL_STATE_TO_PG=true` -> `OrderRepository`
  - `CORE_ORDER_BACKEND=postgres` + `MIGRATE_ALL_STATE_TO_PG=true` -> `PgOrderRepository`
- Docker PG schema smoke：
  - numeric columns 已显示 `precision=36, scale=18`
  - `uq_positions_active_symbol_direction` 存在
- `close_db()` smoke：SQLite engine/sessionmaker 均可复位重建，PG probe OK。

### 2026-04-29 09:05 CST -- PG 架构审查 P1 收口

**输入**
- 架构审查报告：`docs/planning/pg_migration_architecture_review.md`
- 结论：整体 B+，合并前需处理 HybridSignalRepository backtest 边界和 repository 路由模式一致性。

**完成**
- `HybridSignalRepository` 增加 backtest source 安全边界：
  - `save_signal(source="backtest")` 在无 `legacy_repo` 时抛明确 `RuntimeError`，避免 backtest 信号误写 PG live signals。
  - `get_signals(source="backtest")` 在无 `legacy_repo` 时抛明确 `RuntimeError`，避免误读 PG live/backtest 混合数据。
  - `delete_signals(source="backtest")` 在无 `legacy_repo` 时抛明确 `RuntimeError`，避免误删 PG 生产信号。
  - `clear_all_signals()` 改为仅走显式注入的 legacy repo；无 legacy repo 时拒绝执行。
- `StrategyConfigRepository` 与其他旧 config repositories 对齐为默认构造 `__new__` 替换模式：
  - 默认 PG 路由时直接返回 `PgStrategyConfigRepository`。
  - `use_pg=False` 或显式 SQLite 路径仍保留 SQLite 实例。
- 迁移脚本增强 P2 防御：
  - `signal_take_profits` 支持已是业务 `sig_*` 的 `signal_id`，并对无法映射记录打 warning。
  - `backtest_reports.sharpe_ratio` 增加空字符串/非法数值清洗。
  - JSONB 字段非法 JSON 时记录 warning 并置空，避免 PG JSONB 插入失败。
  - 记录 SQLite 字段被 PG 忽略的字段差异。
  - 记录 `ON CONFLICT DO NOTHING` 造成的 conflict/no-op 数量。
  - `research_jobs` artifact 为空/缺失时记录 warning。

**验证**
- `python3 -m py_compile src/infrastructure/hybrid_signal_repository.py src/infrastructure/repositories/config_repositories.py scripts/migrate_sqlite_state_to_pg.py` 通过。
- `MIGRATE_ALL_STATE_TO_PG=false python3 -m pytest tests/unit/test_hybrid_signal_repository.py tests/unit/test_runtime_profile_repository.py tests/unit/test_research_repository.py tests/unit/test_config_profile.py -q`
  - 65 passed
- Config repository route smoke:
  - 默认：`StrategyConfigRepository` -> `PgStrategyConfigRepository`
  - 默认：`RiskConfigRepository` -> `PgRiskConfigRepository`
  - `StrategyConfigRepository(use_pg=True)` -> PG
  - `StrategyConfigRepository(use_pg=False)` -> SQLite wrapper

**边界**
- 未重新执行整库迁移；迁移脚本增强已做语法检查，下一次可在独立测试库用 `--truncate` 做迁移演练。

### 2026-04-29 09:20 CST -- PG 验证失败项修复

**输入**
- 验证报告：`docs/planning/pg_migration_validation_report.md`
- 初始结果：迁移演练成功；PG 集成测试 `105 passed, 4 failed`；repository smoke 脚本存在调用契约错误。

**修复**
- `tests/integration/test_pg_signal_repo.py`
  - `update_superseded_by` 断言改为 PG 规范的大写 `SUPERSEDED`。
- `tests/integration/test_pg_position_repo.py`
  - 适配 active position partial unique index。
  - 多活跃仓位列表/分页测试改用不同 `symbol`，避免同 `symbol + direction` 的未关闭仓位违反业务约束。
- `scripts/pg_smoke_test.py`
  - 修正 `PgResearchRepository.list_*` 返回 `(items,total)` 的契约。
  - 修正 `PgBacktestReportRepository.list_reports(page_size=...)` 调用。
  - 修正 `PgHistoricalDataRepository.get_kline_range(symbol,timeframe)` 调用。
  - 修正 `PgOrderRepository.get_orders()` 返回 dict 的处理。

**验证**
- 独立 PG 测试库集成测试：
  - `PG_DATABASE_URL=...dingdingbot_migration_test?... python3 -m pytest tests/integration/test_pg_order_repo.py tests/integration/test_pg_signal_repo.py tests/integration/test_pg_position_repo.py tests/integration/test_pg_execution_intent_repo.py tests/integration/test_pg_execution_recovery_repo.py -q`
  - 109 passed
- `scripts/pg_smoke_test.py` 在独立测试库执行通过，无异常。
- SQLite 显式路径回归仍通过：
  - 65 passed

**说明**
- 集成测试会清理测试库核心表，因此 smoke 中 signals/orders 为 0 是预期结果，不代表主库迁移数据缺失。

### 2026-04-29 -- PG 全状态迁移合入 dev

**完成**
- 将 `origin/codex/pg-full-migration` 合入本地 `dev`。
- 仅 `docs/planning/progress.md` 存在追加式文档冲突，已保留 R2 资金配置搜索记录与 PG 迁移窗口记录。
- 代码层无 merge conflict。

**合并后验证**
- `python3 -m py_compile src/infrastructure/database.py src/infrastructure/hybrid_signal_repository.py src/infrastructure/pg_models.py scripts/migrate_sqlite_state_to_pg.py scripts/pg_smoke_test.py` 通过。
- SQLite 显式路径回归：
  - `MIGRATE_ALL_STATE_TO_PG=false python3 -m pytest tests/unit/test_hybrid_signal_repository.py tests/unit/test_runtime_profile_repository.py tests/unit/test_research_repository.py tests/unit/test_config_profile.py -q`
  - 65 passed
- 独立 PG 测试库集成测试：
  - `PG_DATABASE_URL=...dingdingbot_migration_test?... python3 -m pytest tests/integration/test_pg_order_repo.py tests/integration/test_pg_signal_repo.py tests/integration/test_pg_position_repo.py tests/integration/test_pg_execution_intent_repo.py tests/integration/test_pg_execution_recovery_repo.py -q`
  - 109 passed

**注意**
- 第一次 PG 集成测试遇到 Docker PG 刚重启后的短暂 connection refused；容器 healthy 后复跑通过。

### 2026-04-29 14:20 CST -- PG 窗口文档收口与剩余歧义归档

**完成**
- 更新 `docs/planning/pg_migration_validation_report.md`：
  - 明确“首次验证快照”与“后续已修复/已合并”的边界
  - 将早期“暂不合并”结论降级为历史建议
- 更新 `docs/planning/pg_migration_architecture_review.md`：
  - 标注 P1 问题已修复
  - 标注该文档仅用于架构追溯，不再代表当前阻塞状态
- 更新 `docs/planning/pg_migration_completion_report.md`：
  - 补充已合入 `dev` 与最终验证结论
- 更新 `docs/planning/task_plan.md` 与 `docs/planning/findings.md`：
  - 明确 PG 全状态迁移窗口已完成
  - 记录剩余非阻塞歧义：repository 返回形状、status 大小写、迁移/ smoke 脚本契约

**结论**
- PG 全状态迁移窗口已正式收口。
- 当前不再需要为 PG 迁移补阻塞性测试。
- 后续若继续处理 PG 相关事项，应归类为“减熵”而非“迁移主线”。
