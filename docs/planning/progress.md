# Progress Log

> Last updated: 2026-04-27 10:40
> Archive backup: `docs/planning/archive/2026-04-23-planning-backup/progress.full.md`

---

## 说明（阅读方式）

本文件是 append-only 的进度日志，条目可能按主题分组而不是严格时间序。
当需要还原精确执行顺序时，以 git history 为准（commit 时间戳是唯一可靠时间线）。

## 近期完成

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
