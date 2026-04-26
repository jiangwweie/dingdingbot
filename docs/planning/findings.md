# Findings Log

> Last updated: 2026-04-27 10:40
> Archive backup: `docs/planning/archive/2026-04-23-planning-backup/findings.full.md`

---

## 当前有效结论

### 0. Research 收口必须保持 research-only，且不得反向污染 runtime

新增结论：

1. 当前 SQLite + PG 双轨并行阶段，研究链的正确方向是继续推进 `Spec / Resolver / Reporter` 收口，而不是给 runtime 增加新的 SQLite 直读捷径。
2. `research-only` 边界必须固定：
   - 回测
   - Optuna
   - candidate 产物
   - 报告 / 解释分析
   这些都属于研究链，不属于 runtime 冻结链。
3. 所有研究产物只允许输出 `candidate`，不得直接改写 `sim1_eth_runtime`。
   - 不自动 promote runtime
   - 不通过脚本直接覆写 runtime profile
   - 研究结论进入 runtime 必须经过人工审查 + 显式冻结
4. 在双轨阶段，**不得新增 runtime 直读 SQLite 的旁路**。
   - runtime 侧继续按既有冻结链路读取
   - 研究链若需要便利入口，应在 `Spec / Resolver / Reporter` 内部收口，而不是把 runtime 拉回 SQLite
5. 因此，当前更合理的职责分工是：
   - `research` 负责候选、证据、比较
   - `runtime` 负责冻结配置、自然观察、执行链路稳定性
6. 当前研究链收口的最小目标不是“更快改 runtime”，而是“统一研究入口、统一 candidate 输出、保持人工 promote 边界”。

### 0. Execution 主线 PG 真源闭环应与其他域迁移拆窗处理

新增结论：

1. 本轮“PG 真源闭环”只应覆盖 runtime execution 主链，不应扩大成“全库去 SQLite”。
2. 当前最小闭环对象是：
   - `orders`
   - `execution_intents`
   - `execution_recovery_tasks`
   - `positions` 的 execution projection / read model
3. `signals / signal_attempts` 当前不迁的原因不是优先级低，而是它们属于 signal / observability 域；一旦进入本窗口，会同时牵动 console 查询、跨库观察口径、历史兼容和可能的 read model 设计，范围会从 execution 主链收口扩张为 runtime 观察链迁移。
4. 因此，当前允许保留的跨库边界是：
   - `Signal(SQLite) -> ExecutionIntent(PG)`
   - `Order(PG).signal_id -> Signal(SQLite)`
5. `signals / signal_attempts` 的迁移前置条件应为：
   - `orders / execution_intents / execution_recovery_tasks / positions projection` 已稳定在 PG
   - runtime execution API 不再误读 SQLite
   - 启动恢复 / 对账 / 订单生命周期不再依赖 SQLite 执行态
   - `positions` 投影模型已经过至少一轮联调或真实运行验证，不再频繁改表
6. 参数 / 策略配置域不应与 execution 主线同窗迁移。
   - 其迁移前置条件是 runtime config 的 SSOT、发布、快照、回滚、运行时装配边界已经稳定
   - 在此之前，SQLite 作为 config repository adapter 仍可接受
7. backtest / research / 历史报表应最后迁。
   - 它们属于历史分析型数据，不与 runtime execution 的一致性诉求同级
   - 只有当线上执行主链和观察链稳定后，再考虑统一分析底座
8. 推荐迁移顺序：
   - 窗口 1：execution 主线 PG 闭环
   - 窗口 2：runtime observability 收口（优先 `signals / signal_attempts`）
   - 窗口 3：参数 / 策略配置域迁移
   - 窗口 4：backtest / research / 历史报表迁移
9. `positions` 本次不应被表述为“替代交易所真源”，而应定义为本地 execution projection。
   - 交易所 `account_snapshot` 仍是外部事实源
   - PG `positions` 承担恢复、风控、console、保护单挂载所需的本地执行态读模型
10. `positions` 写入时机更适合挂在 `OrderLifecycleService` 的成交事件之后，由独立 projection/update 服务写 PG，而不是由 `ExecutionOrchestrator` 直接写仓位。
11. 当前代码骨架已先完成两条关键收口：
   - `ExecutionOrchestrator` 不再直接调用 `order_lifecycle._repository.save()` 持久化保护单，而是统一改走 `OrderLifecycleService.register_created_order()`
   - runtime API fallback 不再默认直接 `new OrderRepository()`，而是回到 `create_order_repository()` 统一装配入口
12. `positions` 已补出 execution projection 骨架：
   - 新增 `PositionProjectionService`
   - `PgPositionRepository` 从“只收 ORM”升级为“可收 Position domain model + 可列出 active positions”
   - `RuntimePositionsReadModel` 已具备 account snapshot 失效时回读 PG position projection 的 fallback 能力
   - 即时 `full fill` 主路径与 `partial fill` 增量保护路径都已接入 projection 入口
13. 当前仍未完成的部分是“投影语义完备化”，包括：
   - partial fill / reduce / close / fee / watermark 的精确更新
   - `v3 positions` API 是否改为 PG-first read model
14. `OrderLifecycleService -> ExecutionOrchestrator` 已新增 `ENTRY filled` 回调。
   - WebSocket / 对账把 ENTRY 推进到 `FILLED` 时，也会统一回到 orchestrator 挂保护单并更新 position projection
   - 新增“已有保护单则跳过重复挂载”的防重门槛，避免下单响应 immediate fill 之后又被 WebSocket 重放时重复生成 TP/SL
15. `TP/SL filled` 也已接入 position projection 回调链。
   - `OrderLifecycleService` 在 TP/SL 首次进入 `FILLED` 时会触发 exit-filled callback
   - `PositionProjectionService.project_exit_fill()` 会更新：
     - `current_qty`
     - `realized_pnl`
     - `total_fees_paid`
     - `is_closed / closed_at`
     - `watermark_price`
16. 当前剩余未补齐的 position projection 语义主要是：
   - 交易所侧真实手续费字段如何稳定映射到 `close_fee / fee_paid`
   - partial exit / repeated fill / out-of-order 回放的更严格幂等边界
   - `v3 positions` 读面虽已支持 PG fallback，但是否需要进一步做成明确的 PG-first execution read model 仍待决定
17. runtime execution 装配已从“通用工厂 + 环境变量切换”进一步收口为“显式 PG runtime 工厂”。
   - `main.py` 的 execution 主链显式使用 PG order repo / PG position repo
   - `api.py` 的 runtime lifespan 与 `_get_order_repo()` fallback 也显式使用 PG runtime 工厂
   - backtest / research / 非主线场景仍可保留通用工厂或 SQLite 仓储，不在本窗口处理
18. runtime overview 的 backend summary 已改为优先反映实际装配结果，而不是只显示环境变量。
   - 这样即使 `.env` 中历史值仍是 `CORE_ORDER_BACKEND=sqlite`
   - runtime console 仍会展示 execution 主链当前实际是 `order=postgres / position=postgres`
19. `_has_existing_protection_orders()` 的防重判定已增强。
   - `parent_order_id == entry_order.id` 仍是第一优先级
   - 当对账重建或历史脏数据导致 `parent_order_id` 缺失时，仅把“未绑定 parent 的保护单”作为兜底命中，降低误判别的 ENTRY 子单的风险
20. `Position` domain model 已补齐 `opened_at / closed_at` 字段。
   - `project_exit_fill()` 不再需要通过 `object.__setattr__` 绕写 `closed_at`
   - projection 读写链与 PG `positions` 表的时间字段语义现在更一致
21. `GET /api/v3/positions` 的 `offset` 双重切片 bug 已修复。
   - 之前 exchange 分支和 PG fallback 分支之外还有一层公共二次切片
   - 当 fallback 分支已先切片时，`offset > 0` 会再次切片成空数组
   - 现在改为各分支各自切片一次，避免重复裁剪

### 0. Config Module 短中期保留 SQLite，Runtime 通过 Resolver 收口

新增结论：

1. Config 保留在 SQLite 问题不大，后续即使迁 PG，主要也是 repository adapter 的实现层迁移。
2. 当前不应为了 Sim-1 把 config 迁入 PG；PG 主线继续只承载强执行语义状态：
   - `execution_intents`
   - `execution_recovery_tasks`
   - breaker 派生状态
3. Sim-1 前真正需要解决的是 runtime config 真源分散，而不是数据库介质。
4. 推荐方案：
   - 新增 SQLite `runtime_profiles` 窄表
   - 新增 `ResolvedRuntimeConfig`
   - 新增 `RuntimeConfigResolver`
   - 启动时解析 `sim1_eth_runtime` 并生成 hash/snapshot
5. 当前执行 TP/SL 必须从 execution module 生成 `OrderStrategy`，不能继续以 `SignalResult.take_profit_levels` 作为实盘保护单真源。

对应设计稿：

- `docs/planning/architecture/2026-04-23-config-module-ssot-runtime-resolver-design.md`
- `docs/planning/architecture/2026-04-23-runtime-config-implementation-skeleton.md`

### 0.1 Runtime Config 骨架实现结论

R1. `runtime_profiles` 采用 SQLite 窄表 + JSON profile 是当前最小可行方案。
   - 不破坏现有 `strategies / system_configs / risk_configs`
   - 不引入 PG config 迁移
   - 后续迁移只需替换 repository adapter

R2. Resolver 必须在环境层做强校验。
   - 缺 `PG_DATABASE_URL`、交易所 key/secret、webhook 时直接失败
   - `CORE_EXECUTION_INTENT_BACKEND` 必须为 `postgres`
   - `CORE_ORDER_BACKEND` 当前默认保持 `sqlite`

R3. 一次性脚本使用共享 SQLite 连接池时，必须在脚本结束前调用 `close_all_connections()`。
   - 否则 aiosqlite 后台线程可能导致脚本不退出
   - seed/verify 脚本已显式关闭连接池

R4. Runtime profile 的 readonly 与 active 语义必须在仓储层强制。
   - `is_readonly=True` 不能只作为 UI/文档标记
   - 默认 upsert 必须拒绝覆盖 readonly profile
   - seed/维护脚本如需更新 readonly profile，必须显式传入 override 参数

R5. `config_hash` 只应表达业务执行基准，不应混入纯基础设施变量。
   - DB DSN、backend port、repo backend switches 不进入 hash
   - `exchange_name / exchange_testnet` 会影响交易所执行环境，保留在 hash
   - secret 永远不进入 hash

R6. `main.py` 的第一阶段接入必须先 observe-only。
   - 当前只在启动期解析 `sim1_eth_runtime`
   - 只保存 `RuntimeConfigProvider` 并打印脱敏 summary/hash
   - 不直接替换现有 `ConfigManager` 消费路径
   - 这样可以先证明 runtime profile 可解析、可审计、可追踪，再分模块切换消费方

R7. Runtime config 消费切换应按模块逐步推进。
   - 第一刀只切 market scope，风险最低
   - 已让预热、订阅、资产轮询间隔从 `ResolvedRuntimeConfig.market` 获取
   - 第二刀只切 `SignalPipeline` 的 `RiskConfig`
   - `CapitalProtectionManager` 账户级熔断不随本刀切换，避免把仓位试算和账户保护混成一个变更
   - 第三刀切 `SignalPipeline` strategy runner，但必须同时锁定 ConfigManager 热重载回退路径
   - execution 暂不切，避免一次性改变保护单语义
   - 每切一个模块都应在日志中明确标记来源，便于 Sim-1 观察回溯

R8. Runtime strategy 接入后，热重载必须遵守冻结 profile 边界。
   - runtime risk 已切入时，ConfigManager 热重载不能覆盖 `_risk_config`
   - runtime strategy 已切入时，ConfigManager 热重载不能覆盖 runner strategy / MTF EMA period
   - 如果未来要支持运行中变更 runtime profile，应通过新 profile + 重启或显式 reload 流程，而不是复用旧 ConfigManager observer 静默覆盖

R9. execution 切换必须只保留一个实盘保护单策略入口。
   - runtime execution module 已转成 `OrderStrategy`
   - `SignalPipeline._build_execution_strategy()` 优先返回 runtime `OrderStrategy` 深拷贝
   - `SignalResult.take_profit_levels` 降级为展示/通知/研究语义，不再作为实盘 TP/SL 策略来源
   - `ExecutionIntent.strategy` 仍是后续 full-fill / partial-fill / recovery 保护单语义的一致性锚点

R10. Runtime direction policy 必须在 attempt 持久化前落地。
   - 仅在执行前跳过 SHORT 不够，会污染 `signal_attempts` 审计语义
   - 不允许方向的 fired attempt 应转为 `FILTERED`
   - filter result 中记录 `runtime_direction_policy`，方便后续归因

R11. Runtime execution config 必须拒绝非正数 TP 比例/目标。
   - `tp_ratios` 总和为 1.0 仍不够，`[-0.5, 1.5]` 这类输入会通过求和但语义非法
   - `tp_ratios` 每项必须 `> 0`
   - `tp_targets` 每项必须 `> 0`

R12. Runtime strategy 应直接生成 `logic_tree`。
   - 新 runtime config 主线不应继续触发 `StrategyDefinition` deprecated triggers/filters 迁移路径
   - 可保留 `trigger/filters` 字段作为兼容和可读性辅助，但 `logic_tree` 必须显式生成

R13. Runtime cutover 需要独立的非 I/O 冒烟脚本。
   - 单纯 resolver verify 只能证明配置可解析
   - 还需要证明 main.py 会使用的 market/risk/strategy/execution 派生对象能组装成功
   - `scripts/verify_sim1_runtime_cutover.py` 负责这个边界，不启动交易所和 WebSocket

R14. 本地 `.env` 已是历史遗留敏感文件，后续不应继续扩大其提交面。
   - 本轮没有修改 `.env`
   - PG 示例继续以 `docs/local-pg.md` / 示例文件为准
   - 若后续要彻底治理，需要单独安排 secret rotation + `.env` 脱离版本控制，不应混在 runtime config 接入任务中顺手做

R15. Runtime risk 的 `daily_max_loss_percent` 已确定采用“启动权益冻结金额，缺快照则百分比回退”的双态策略。
   - 启动时若能拿到账户权益快照，则派生 `daily.max_loss_amount = equity * daily_max_loss_percent`
   - 这样当日熔断阈值在本次进程内固定，不会随盘中权益波动漂移
   - 若启动瞬间尚无账户快照，则不伪造金额，保留 `daily.max_loss_percent` 百分比口径
   - 这比强行要求固定 base equity 更适合当前 Sim-1 / 低频实盘准备阶段

R16. Optuna 的“candidate only”边界需要有真实产物，而不只是文档约定。
   - 仅靠 `best_trial` 内存对象不利于跨机器审查和次日回看
   - 现已在 `StrategyOptimizer` 中补齐 `build_candidate_report()` / `write_candidate_report()`
   - 输出包含 source profile hash、best params、fixed params、resolved request summary
   - 仍不自动写入 runtime profile，保持人工审查后 promote 的边界

R17. 旧的最小验证脚本若继续调用已删除私有方法，会在你以为“只是验证”时制造假阻塞。
   - `scripts/verify_fixed_params_minimal.py` 曾调用已删除的 `_build_backtest_request()`
   - 这类脚本属于研究链入口，也必须跟上主契约演进
   - 现已改为验证 `_build_trial_backtest_inputs()` + resolver + runtime overrides

### 1. 执行恢复状态已完全进入 PG 主线

- ✅ `ExecutionIntent` 是 PG 主真源
- ✅ `execution_recovery_tasks` 是 PG 正式恢复真源
- ✅ SQLite `pending_recovery` 过渡链已移除
- ✅ `circuit_breaker` 由 PG active recovery tasks 重建（内存缓存）

### 2. 恢复工单独立成表是当前最合理的正式方案

不推荐：

1. 长期保留 SQLite `pending_recovery`
2. 把恢复语义塞进 `orders`
3. 直接把复杂 recovery graph 塞进 `execution_intents`

推荐：

- 独立 PG 表 `execution_recovery_tasks`

### 3. 执行链当前已经具备最小恢复闭环

当前已成立：

1. partial-fill 增量保护
2. 单一 SL 约束
3. 撤旧挂新保证交易所侧覆盖全仓
4. 撤旧 SL 失败 -> pending recovery + 熔断 + 告警
5. 启动对账 -> resolved / retrying / failed

### 4. 测试分层必须保持

对当前执行恢复链：

1. unit test 用 mock/stub 验证业务语义
2. 真实 PG 连通性验证改用脚本，不放进 `pytest tests/unit`

当前正式脚本：

- `scripts/verify_pg_execution_recovery_repo.py`

### 5. 当前剩余问题不是主线阻塞，而是阶段收尾

- P1 级问题已收口
- 剩余问题主要是：
  - 默认主链路径已闭合
  - 个别自定义注入/初始化一致性问题只保留为 P2 级约束

### 6. 模拟盘准入冒烟通过，但真实全链路尚未实证

当前已经通过的是准入级冒烟验证：

1. 正常执行链路可运行
2. `replace_sl_failed` 能创建 PG recovery task、触发 breaker、发送告警
3. 启动恢复能推进 PG recovery task
4. breaker 能拒绝同 symbol 新信号

但这不等于真实模拟盘全链路已经跑通。

尚需 Sim-0 验证：

`真实/模拟行情 -> SignalPipeline -> 策略/过滤器 -> 风控/仓位 -> testnet 下单 -> WS 回写 -> OrderLifecycle -> StartupReconciliation -> PG recovery / breaker`

---

## 当前阶段最重要的判断

**现在不该继续横向扩张，而应进入 Sim-0 真实全链路验证。**

也就是：

1. 模拟盘运行配置必须冻结
2. 离线优化可以并行，但不能热改 Sim-0 配置
3. Sim-0 只验证执行链稳定性，不做策略参数优化
4. 其他事情只保留在 backlog，不进入执行态

---

## 第二阶段已完成议题

1. `circuit_breaker` 是否 PG 真源化：已完成，结论是不单独建表，作为 PG recovery task 的派生状态
2. SQLite `pending_recovery` 的退役路径：已完成，系统未上线，无历史包袱，直接移除
3. recovery task 的 retry/backoff：已完成，指数退避策略显式化

### 当前收敛结论

第二阶段不再并行展开多条线，而是采用“分层处理全局问题”的方式推进：

1. 全局上看到后续还有 PG、运维、回测等多条线
2. 当前层只允许锁定一个主线入口
3. 当前入口已切换为：Sim-0 真实全链路验证

这条原则的目的不是缩小视野，而是避免主线再次分裂。

### 当前补充结论

1. 主线已经明确：
   - 当前不是回测阶段
   - 不是前端/API 扩张阶段
   - 而是执行恢复状态收敛阶段
2. 后续设计默认先判断是否应进入 PG 主线
3. 第二阶段现阶段只锁方向，不提前展开实现

### 第二阶段入口议题结论（已分析）

`circuit_breaker` 当前最合理的收敛方式不是单独新增 PG 表，而是：

1. 继续以 `execution_recovery_tasks` 作为恢复真源
2. 把 `circuit_breaker` 定位为 active recovery tasks 的派生保护状态
3. 运行时保留内存 breaker 集合作为快速判断缓存
4. 启动后由 PG active recovery tasks 重建 breaker

对应设计稿：

- `docs/planning/architecture/2026-04-23-circuit-breaker-pg-analysis.md`

### Sim-0 当前结论

1. Sim-0 受控 runtime 链路已阶段性跑通
2. 但暂不应直接进入自然模拟盘观察窗口
3. Sim-0 不是策略优化阶段，而是执行系统稳定性验证阶段
3. 建议范围：
   - testnet / 模拟盘
   - 单 symbol：`BTC/USDT:USDT`
   - 当前冻结主线策略
   - `CORE_EXECUTION_INTENT_BACKEND=postgres`
   - `CORE_ORDER_BACKEND=sqlite`
4. 通过标准：
   - 至少一笔真实 testnet ENTRY 链路可追溯
   - ENTRY / TP / SL / WS 回写 / 对账状态一致
   - PG recovery task 无异常 pending/failed
   - breaker 无误触发/漏触发

对应计划：

- `docs/planning/sim-0-real-chain-validation-plan.md`

### Config module 已成为下一阶段首要梳理对象

当前发现的核心问题不是“某个参数该取多少”，而是系统配置真源没有被清晰分层：

1. `.env` 已被确定为当前运行入口
2. YAML 已废弃，不应再作为运行配置来源
3. 但主程序仍从 SQLite 配置库读取 exchange / notification / system / risk / strategies
4. Sim-0 为了跑通，会把 `.env` 同步进 SQLite 兼容配置库
5. 策略参数、风控参数、执行 TP/SL 参数、回测参数、研究文档基准之间存在多套口径
6. PG 迁移原则已经明确用于强执行语义状态，但 config module 是否迁移 PG、如何迁移，尚未设计

下一阶段应先输出：

1. 配置真源矩阵
2. 配置分层原则
3. Sim-1 前最小收口方案
4. 中期 PG config 方案
5. YAML / SQLite 兼容路径的退役边界

### Sim-1 ETH runtime config 已形成规划口径

1. Sim-1 不沿用当前 SQLite BTC 受控配置；该配置只作为 `sim0_controlled_btc` 归档。
2. ETH 1h LONG-only 是当前研究基准，主真源为 `docs/planning/backtest-parameters.md`。
3. 配置应先按模块划分，再按场景加载：
   - `environment`
   - `market`
   - `strategy`
   - `risk`
   - `execution`
4. Sim-1 已确认参数：
   - `symbol=ETH/USDT:USDT`
   - 主周期 `1h`
   - MTF 辅助周期 `4h`
   - `direction=LONG-only`
   - EMA50 + MTF
   - ATR 保留字段但 `enabled=false`
   - `max_loss_percent=0.01`
   - `max_leverage=20`
   - `max_total_exposure=1.0`
   - `daily_max_loss_percent=0.10`
   - TP ratio `[0.5, 0.5]`
   - TP target `[1.0, 3.5]`
   - BE off / trailing off / OCO on
5. `.env` 负责 secret/env/backend；DB 负责非 secret business config；PG 继续负责 execution state / recovery / breaker。
6. Sim-1 前不做 PG config SSOT 大迁移，不做热改能力，不做 Optuna 一键应用。

规划文档：

- `docs/planning/sim-1-eth-runtime-config-plan.md`

### Backtest config 不应直接跟随 Sim/Live runtime profile

回测链路当前可以独立运行，但在 Sim-1 runtime config 收口后，必须避免把回测默认值直接绑定到 `sim1_eth_runtime`。原因：

1. Sim/Live runtime profile 是模拟盘/实盘冻结快照，强调启动一致性和审计。
2. Backtest profile 是实验基线，允许 request / Optuna / runtime_overrides 做单次覆盖。
3. Backtest engine 参数如 slippage、fee、same-bar policy 只存在于回测域，不应进入 Sim/Live runtime。
4. 若回测默认直接读取 mutable runtime profile，会导致历史研究结果随运行配置漂移。

已落地决策：

1. 新增独立 `backtest_eth_baseline` profile。
2. 新增 `ResolvedBacktestConfig` 作为回测配置消费对象。
3. 保留优先级：`runtime_overrides > request > backtest profile > code defaults`。
4. 新增显式可注入参数契约 `BACKTEST_INJECTABLE_PARAMS`，当前 25 个参数。
5. 将可注入参数按模块划分为 `market / strategy / risk / execution / engine / diagnostic`。
6. 通过 `optimizer_safe` 标记 Optuna 可搜索参数，防止搜索空间误覆盖 secret、backend、runtime profile 等非回测参数。
7. `StrategyOptimizer` 已接入 `BacktestConfigResolver`，trial request / strategy / risk / execution 不再由 Optuna 内部硬编码。
8. Optuna parameter space 必须命中 `optimizer_safe=True` 字段；fixed params 必须命中可注入参数契约。
9. Optuna 不写 runtime DB，不自动应用模拟盘。
10. Optuna trial 每次只允许解析一次 backtest profile；风控覆盖在已解析 request 上叠加，避免搜索阶段重复 I/O。
11. `StrategyOptimizer` 不允许直接 import 具体 baseline profile 常量，所有 baseline fallback 必须来自当前 resolver 结果。

后续接线：

1. 回测 API 暂缓，当前不做 Web。
2. 后续只按需整理仍会继续使用的研究脚本入口。
3. 前端回测重构时只展示该契约允许注入的字段。
4. 真实 Optuna 小规模搜索运行前单独确认。

### 前端重构采用方案 A（分域控制台）

已确认：

1. 当前前端重构不做“大而全工作台”，先做统一控制台的信息架构。
2. 采用方案 A：一级导航拆为 `Runtime` / `Research` 两个域。
3. 第一版以只读为主：
   - 不做配置编辑
   - 不做策略热改
   - Candidate review 第一版只展示
   - Runtime 页面第一版手动刷新，不做 SSE / websocket UI
4. Backtest Studio 作为二期并入 `Research` 域，本次先纳入架构，不进第一版实现范围。

当前建议页面树：

1. `Runtime`
   - `Overview`
   - `Signals`
   - `Execution`
   - `Health`
2. `Research`
   - `Candidates`
   - `Candidate Detail`
   - `Replay`
   - `Backtests`（二期）
   - `Compare`（二期）

当前接口优先级：

1. P0：Runtime 观察接口
   - `GET /api/runtime/overview`
   - `GET /api/runtime/signals`
   - `GET /api/runtime/attempts`
   - `GET /api/runtime/execution/intents`
   - `GET /api/runtime/execution/orders`
   - `GET /api/runtime/health`
2. P1：Research 只读接口
   - `GET /api/research/candidates`
   - `GET /api/research/candidates/{candidate_name}`
   - `GET /api/research/replay/{candidate_name}`
3. P2：Backtest Studio / 对比与写回接口
   - `GET /api/research/backtests`
   - `GET /api/research/backtests/{report_id}`
   - `POST /api/research/compare/candidates`
   - `POST /api/research/compare/backtests`
   - `POST /api/research/candidates/{candidate_name}/review`（后续如开放人工写回）

SSOT 文档：

- `docs/planning/architecture/2026-04-24-frontend-runtime-monitor-and-research-console-plan.md`

本轮补充确认：

1. `Runtime / Overview` 必须加入 freshness / heartbeat 字段；手动刷新模式下，没有陈旧度提示的“健康页面”不可接受。
2. Console 默认仅限本地 / 内网访问；若跨机器访问，至少加 Basic Auth 或反向代理鉴权。
3. `Research / Replay` 第一版语义应按 replay context / reproduce context 理解，不承诺 K 线图表。
4. `Research / Candidates` 第一版允许基于 `reports/optuna_candidates/` 扫描，但需显式记录后续文件索引缓存演进点。
5. `breaker summary` 与 `recovery summary` 必须在接口语义上拆开，避免把运行时保护状态与 PG 恢复工单状态混成同一个聚合数字。

页面补充决策（方案 A）：

1. 从量化使用者视角，当前最值得补齐的页面不是配置编辑，而是：
   - `Runtime / Portfolio`
   - `Runtime / Positions`
   - `Runtime / Events`
   - `Config / Snapshot`
   - `Research / Candidate Review`
2. `Config / Snapshot` 只允许作为 frozen runtime 的只读预览页存在，不允许演进为配置编辑器。
3. `Research / Candidate Review` 只做评审聚合展示，不做状态写回。
4. 当前前端补页的核心原则仍然是：
   - 先补可见性
   - 再补研究辅助
   - 不突破只读边界

前端扩展新主线（方案 B）：

1. `gemimi-gemimi-web-front` 已证明可以作为完整控制台的起点，不需要推倒重来。
2. 方案 B 的目标不是单独补几个页，而是把前端扩展成完整的量化观察与研究控制台。
3. 已新增主规划文档：
   - `docs/planning/architecture/2026-04-25-frontend-console-plan-b.md`
4. 方案 B 的优先级更偏向：
   - Runtime 观察
   - Portfolio / Positions 风险视图
   - Events 事件时间线
   - Candidate Review 聚合判断
   - Config Snapshot 只读预览

### `.env` 不能承载本地 PG 示例或 backend 切换值

已跟踪 `.env` 仍包含真实交易所 key / webhook，不能再混入本地 PG 连接串或 backend 切换示例。否则后续提交时容易把个人本地运行环境和敏感配置一起带入版本历史。

已落地：

1. 从 `.env` 移除 `PG_DATABASE_URL`、`CORE_EXECUTION_INTENT_BACKEND`、`CORE_ORDER_BACKEND`。
2. 本地 PG 启动说明保留在 `docs/local-pg.md`。
3. 推荐使用 shell 环境变量启动 PG 初始化链。
4. API lifespan 测试不再隐式依赖 `.env` 中存在 PG 配置。

### Sim-0 真实 runtime 验证新增发现

1. `SignalPipeline._calculate_risk()` 必须是 async
   - 真实信号触发后会进入 `RiskCalculator.calculate_signal_result()`
   - 该方法是 async，未 await 会让后续 executor 拿到 coroutine
   - 已修复

2. 市价单 `create_order()` 返回 `FILLED` 不等于一定有成交均价
   - Binance testnet 中 ENTRY 直接成交，但响应可能缺少 `average`
   - 保护单生成必须基于真实成交均价
   - 已补充 `fetch_order()` 兜底

3. `ExecutionIntent` PG 真源与 `Order` SQLite 真源并行时，不能对 `order_id` 建 PG 外键
   - 当前冻结配置是 `CORE_EXECUTION_INTENT_BACKEND=postgres` + `CORE_ORDER_BACKEND=sqlite`
   - 因此 PG `execution_intents.order_id` 只能是跨库逻辑引用
   - 已移除对应 PG 外键

4. 受控验证后必须清理 testnet 仓位
   - Sim-0 runtime check 会真实下 testnet ENTRY 和保护单
   - 验证完成后必须取消保护单并 reduce-only 平仓
   - 本次已完成清理，交易所侧 open orders / position 均为空

5. attempt flush Decimal JSON 序列化已闭合
   - 真实 runtime 日志中复现：`Object of type Decimal is not JSON serializable`
   - 不阻断 ENTRY / TP / SL 主链
   - 但影响 signal attempt 诊断记录完整性
   - 根因：`SignalRepository.save_attempt()` 直接 `json.dumps()` 策略诊断 payload，真实策略计算会携带 `Decimal`
   - 修复：仓储层统一使用 Decimal/Enum 安全 JSON helper，覆盖 `details` / `trace_tree` / `tags_json`
   - 验证：`tests/unit/test_signal_repository.py` 全部通过

---

## 历史说明

旧版详细 findings、研究链历史结论、回测参数长链路、PG 迁移早期推理已备份到：

- `docs/planning/archive/2026-04-23-planning-backup/findings.full.md`

主文档今后只保留仍然影响当前阶段决策的结论。 

---

## 2026-04-24 -- 决策记录：研究脚本收口选方案 A（先行），方案 B（延后）

### 背景

当前目标是 Sim-1 启动与模拟盘期间的稳定性，且明确约束：

- 模拟盘期间策略/风控不允许热改
- Optuna 最优参数只生成 candidate，不允许一键应用到 runtime profile
- 研究参数必须可复现、可审计、可对比，避免脚本各自拼装导致口径漂移

### 决策

选择方案 A：保留现有脚本入口，但将脚本逻辑薄化为：

- CLI args -> `StudySpec` / `BacktestJobSpec`
- 统一走 `BacktestConfigResolver` 解析 baseline + overrides + window + seed
- 统一走 `CandidateReporter` 落盘 `reports/optuna_candidates/`（candidate only）

方案 B（统一 CLI + TaskRegistry）延后到 Sim-1 稳定后演进。

### 选择方案 A 的理由（与当前阶段最强相关）

1. 变更面最小，能最快消除“脚本口径漂移/不可复现/难对比”的核心风险。
2. 更容易在代码结构层面保证 “candidate only，不触碰 runtime profile”，符合 Sim-1 冻结约束。
3. 并行友好：脚本可逐个迁移，不会因为统一入口/registry 设计争议阻塞整体研究链。
4. 方案 A 的底座（Resolver/Spec/Reporter）可作为后续方案 B 的基础，不会推倒重来。

### 此时不直接上方案 B 的反对点（时机风险）

1. 容易超出“路径 1 轻量级收口”边界（CLI/registry/handler 契约会膨胀成框架工程）。
2. 引入新的单点依赖：入口/registry 不稳会导致所有研究任务被阻塞。
3. 更容易把研究与 runtime 边界混合，后续出现隐性“apply to runtime”的风险面。
4. 短期收益不如 A：当前痛点是口径与复现，不是入口数量。

### 后续演进策略（兼容方案 B）

先把 A 的 “Resolver + Spec + Reporter + candidate output contract” 固化为真源；
待 Sim-1 稳定后，再把脚本逐步收敛为统一 CLI/registry（方案 B）。

---

## 2026-04-24 -- Config Hash 语义升级记录

- `stable_config_hash()` 从 `3e9de20` 起引入 `hash_schema_version` 包装层。
- 影响：同一业务 payload 在新实现下会产生不同于旧实现的 `config_hash`。
- 当前判断：这不会阻塞运行链路，因为 `config_hash` 主要用于审计/日志，不作为 profile 查询键。
- 运维含义：旧日志/旧 seed 产生的 hash 与新版本不可直接混比；如需重新对齐，应以新版本重新 seed/runtime resolve 为准。

---

## 2026-04-24 -- Candidate 评审口径已冻结为 Strict v1

- 当前 candidate 链已经满足：
  - `best_trial` 与 `top_trials[0]` 指标一致
  - `sortino_ratio` 不再固定为 `0` / `null`
  - replay 可稳定读取 candidate JSON
- 因此评审体系不再依赖临场口头判断，当前冻结为：
  - `PASS_STRICT`
  - `PASS_STRICT_WITH_WARNINGS`
  - `PASS_LOOSE`
  - `REJECT`

### Strict v1（当前人工评审池入口）

- `total_trades >= 100`
- `sharpe_ratio >= 1.0`
- `total_return >= 0.30`
- `max_drawdown <= 0.25`
- `win_rate >= 0.45`
- `params_at_boundary == false`

### 当前 warning-only 项

- `sortino_ratio` 缺失/异常
- `trade_concentration` 未补齐
- `profit_concentration` 未补齐
- `max_consecutive_losses` 未补齐

### 决策含义

- `PASS_STRICT` / `PASS_STRICT_WITH_WARNINGS` 才进入人工评审池。
- `PASS_LOOSE` 只保留为对照候选，不进入后续 runtime 讨论。
- `REJECT` 不进入后续评审链路。

---

## 2026-04-25 -- 后端只读 API 成为当前主线扩展

### 背景

Gemini 生成的前端骨架已经覆盖 Runtime / Research / Config 的主要只读页面，mock 数据也已经能支撑第一轮体验。当前新的瓶颈不再是“有没有页面”，而是“前端是否有稳定、可对齐的后端只读数据源”。

### 关键判断

1. 主模块仍依赖 `src/interfaces/api.py` 启动，因此 API 模块短期不能一刀切删除，只能逐步瘦身。
2. 前端控制台的下一步价值不在继续加页，而在把 mock-first 页面逐步对接为真实只读数据。
3. Sim-1 仍然是 runtime 真源，后端 read model 必须围绕 Sim-1 真实运行状态来组织，而不是反向让前端直接读表。

### 决策

1. 先做只读 API，不做写接口。
2. 先做页面级聚合接口，不先直出数据库表。
3. `api.py` 先保留兼容入口，再逐步把控制台相关路由拆出去。
4. 前端 mock 数据继续保留为临时垫层，最终逐页替换成真实后端数据。

### 当前优先级

- P0：`runtime/overview`、`runtime/portfolio`、`runtime/positions`、`runtime/events`、`runtime/health`
- P1：`runtime/signals`、`runtime/attempts`、`runtime/execution/intents`、`runtime/execution/orders`
- P1：`research/candidates`、`research/candidates/{candidate_name}`、`research/candidates/{candidate_name}/review-summary`、`research/replay/{candidate_name}`
- P2：`research/backtests`、`research/backtests/{report_id}`、`research/compare/*`、`config/snapshot`

### 待办步骤

1. 冻结前端页面契约和 mock 字段命名。
2. 第一批实现固定为：
   - `runtime/overview`
   - `runtime/portfolio`
   - `runtime/health`
   - `research/candidates`
3. 第二批实现固定为：
   - `runtime/positions`
   - `runtime/signals`
   - `runtime/attempts`
   - `runtime/execution/orders`
   - `runtime/execution/intents`
4. 第三批实现固定为：
   - `research/candidates/{candidate_name}`
   - `research/replay/{candidate_name}`
   - `research/candidates/{candidate_name}/review-summary`
   - `config/snapshot`
5. `runtime/events` 延后，避免在事件聚合方案未稳定时过早绑定接口语义。
6. 第一阶段模块落点已确认：
   - `src/application/readmodels/runtime_overview.py`
   - `src/application/readmodels/runtime_portfolio.py`
   - `src/application/readmodels/runtime_health.py`
   - `src/application/readmodels/candidate_service.py`
   - `src/interfaces/api_console_runtime.py`
   - `src/interfaces/api_console_research.py`
7. 用 Sim-1 真实数据逐页校验 mock 与后端差异。

### 说明

这条线的重点不是“把 API 全部重写”，而是建立一个稳定的只读数据层，让前端控制台先能看清，再逐步替换 mock。

### 当前新增 SSOT

- `docs/planning/architecture/2026-04-25-backend-readonly-api-and-api-module-roadmap.md`
- `docs/planning/architecture/2026-04-25-console-readonly-api-v1-contract.md`

### 2026-04-25 Execution 风险修复发现

1. `project_exit_fill()` 原实现默认把 `exit_order.filled_qty` 当作“本次增量”，这在重放/补偿链路里不是安全语义；已改为按 `order_id` 记录累计已投影成交量与手续费，只投影 delta。
2. 仅在 `EXIT -> FILLED` 时投影仓位，会漏掉 `PARTIALLY_FILLED -> CANCELED` 的真实减仓；已把 exit projection 触发点前移到“成交量前进”。
3. protection order 的本地状态推进原先比 ENTRY 主单更弱，会把真实 `FILLED/PARTIALLY_FILLED` 误记成 `OPEN`；已统一改为按交易所返回状态推进。
4. 增量补挂 SL 的真正 P0 不只是“撤旧挂新有真空期”，而是“撤旧成功后新单失败/进程崩溃没有 recovery”；这一分支已补 recovery + 熔断 + 告警。
5. `ExecutionIntent` 原先是 last-write-wins；已补一层最小状态前进约束，先阻止明显的晚到事件回退。

### 2026-04-26 单实例补强新增发现

1. `main.py` 启动期其实已经有 breaker 重建链路，但原先调用的是 `list_active()`，语义只覆盖“当前到期可执行”的 recovery task，不足以表达“仍应阻止新开仓”的 blocking task。
2. 单实例下，`SL` 替换失败最优先的不是更复杂的分布式协调，而是同步 best-effort 抢救，把旧 `SL` 或新的 `SL` 立即补回去，尽量缩小裸奔时间窗。
3. `project_entry_fill()` 若允许 `current_qty > 0` 与 `closed_at != None` 并存，会在后续回测/对账里形成时序悖论；单实例阶段应优先保证本地投影记录自洽。
4. `SL` 同步重试若成功，主流程必须回传“真实成功的 retry order”，不能继续把原始失败单当作 `sl_order` 往下游传，否则返回结果和后续读面会指向一张已失败的保护单。
5. `api.py` 的独立 uvicorn 模式原先只起了一个“缩水版” execution runtime：缺少 `PG execution recovery repo`、`position projection service`、启动对账与 breaker 重建。若不补齐，同一套 runtime 在不同启动入口下会出现执行语义漂移。
6. `RuntimePositionsReadModel` / `/api/v3/positions` 如果继续把交易所 snapshot 放在第一优先级，会让前端在交易所抖动时看见“空仓”，但 PG execution projection 其实还在。对 Sim-1 来说，这比“实时 PnL 不够精确”更危险，因为它会直接误导执行态判断。
7. `PgOrderRepository` 之前只够支撑 lifecycle/orchestrator 写链，不够支撑 `/api/v3/orders`、`/api/v3/orders/tree`、`/api/v3/orders/batch` 这些查询/管理链。若不补齐，orders 虽然主写入在 PG，观察与管理面仍会在运行时掉回“不可信”状态。
8. PG sessionmaker “失败后永久损坏”的高风险，在单实例阶段最直接的低成本缓解不是大改 factory，而是先启用 `pool_pre_ping` / `pool_recycle` 并加真实 `SELECT 1` 探针，把最常见的失活连接问题压下去。
9. `seed_sim1_runtime_profile.py` 里 `allow_readonly_update=True` 实际等于给只读 runtime profile 留了后门；把它去掉虽然只是 1 行，但能立刻降低“观察期配置被静默改掉”的概率。

### 2026-04-27 PG 主线观测/只读面测试回收结论

1. 基于外部 Claude 测试结果，runtime health / overview / positions / v3 orders 这一轮新增修复已通过 90 个定向测试，说明“主线代码补丁”与“只读观测面”目前没有明显回归冲突。
2. 当前剩余最真实的缺口已经从“逻辑没测”收缩为两类：
   - ~~**模型语义缺口**：`PositionInfo` 缺少 `current_price` / `mark_price`~~（已修复，positions enrich 断裂点已关闭）
   - ~~**PG repo 真库验证缺口**~~（已由真实 PostgreSQL 集成测试解除）
3. 这意味着当前窗口现在已经可以把“代码实现 + 定向单测 + 真实 PG 验证”三层闭环视为成立。

### 2026-04-27 PG Repository 真库验证回收结论

1. 外部 Claude 已完成 4 个 PG Repository 的真实 PostgreSQL 集成测试，新增/补齐 25 个 integration tests，累计两轮 180 个测试通过、0 失败、0 跳过。
2. 这意味着当前窗口里“真实 PG 语义未被证实”的核心阻塞已经解除：
   - `PgOrderRepository`
   - `PgExecutionIntentRepository`
   - `PgPositionRepository`
   - `PgExecutionRecoveryRepository`
   的 CRUD / JSONB / 约束 / 查询语义均已有真实 PG 证据。
3. 当前剩余项已从“主线闭环阻塞”收缩为“边缘增强/语义澄清”：
   - **P1**：`PositionInfo` 缺少 `current_price`，导致 positions enrich 不完整
   - **P2**：`list_active()` vs `list_blocking()` 语义需要文档澄清
4. `PgPositionRepository` 缺少 `list_positions()` 的结论已不再成立；当前代码已补该方法，应以现有 src 为准。

### 2026-04-27 后续阶段判断：边界治理优先于继续迁库

1. execution PG 主线既然已经通过代码补强 + 真实 PG 集成验证，后续最值钱的工作不再是“继续迁表”，而是把系统边界正式定型。
2. `signals / signal_attempts` 当前更像 **observability / diagnosis** 候选，而不是自动升级为“必须立刻迁 PG”的对象；是否迁移应取决于它们是否仍参与执行判断、恢复、风控、状态推进。
3. 配置链优先级高于 signals 迁移，因为它直接决定 runtime 是否会被污染：
   - `runtime_profiles`
   - 参数表
   - resolver / provider / ConfigManager 来源优先级
   - runtime freeze 后的不可变边界
4. research 链与 runtime 的隔离必须进入主计划：
   - research 产物可以生成 candidate
   - candidate 进入 runtime 必须经过显式发布/冻结动作
5. 因此后续路线应从“继续迁库”切换为“边界治理”：
   - runtime execution truth
   - runtime observability
   - config / research / history
   三类边界先钉死，再决定迁移策略。

### 2026-04-27 五份审计报告的有效风险重排

1. 当前 5 份报告里，真正还会影响主线的不是“还能迁哪些表”，而是以下 3 类风险：
   - **边界未正式冻结**：execution truth / observability / config / research 仍容易被混写
   - **runtime 配置可被旁路污染**：`ConfigManager.set_instance()`、profile 切换入口、共享 `data/v3_dev.db`
   - **signals / attempts 角色未定型**：若它们仍参与执行判断，就不能继续被默认为“纯观察层”
2. 以下旧风险应视为“已缓解或需按最新代码复核”，不能原样继承到下一主线：
   - orders API fallback 继续读 SQLite
   - runtime health / overview 永远 DEGRADED
   - `PgOrderRepository` 主路径方法不完整
   - “PG repo 无真实验证”
3. 因此下一阶段主线应重排为：
   - **P0**：正式定义 `runtime execution truth`
   - **P0**：正式定义 `runtime observability`
   - **P0**：收紧 config freeze / parameter governance
   - **P1**：research / runtime 隔离落成架构事实
   - **P1**：在完成以上边界后，再判断 `signals / signal_attempts` 是否进入 PG 迁移窗
4. 当前仍值得保留的实现级剩余项：
   - `list_active()` / `list_blocking()` 语义澄清
   - profile switch “对当前进程还是下次启动生效”的文义进一步明确
5. 当前不再推荐把“继续迁更多表”当作默认下一步，因为 execution PG 主线已经通过代码、只读面和真实 PG 验证三层闭环。

### 2026-04-27 `signals` 与 `signal_attempts` 不应再被打包视作同一类对象

1. 代码显示 `signals` 当前具有真实的 **pre-execution state** 语义，而不只是观测：
   - startup 时会重建 active/pending signal cache
   - 新 signal 发出前会查 cover / opposing signal
   - superseded / pending / won/lost 状态会被后续流程更新
2. 因此 `signals` 的下一步判断标准不是“是否要统一技术栈”，而是：
   - 它是否仍然构成 execution 上游的状态依赖
   - 若是，则它迟早要从跨库边界里被拿出来单独处理
3. 相比之下，`signal_attempts` 当前更接近 **observability / diagnosis**：
   - attempts 页面
   - attribution / diagnostics
   - backtest / evaluation summary
   它不直接推进 execution runtime 状态
4. 这意味着后续不应再用“signals / attempts 一起迁不迁 PG”来讨论，而应拆成：
   - `signals`：execution 上游状态域
   - `signal_attempts`：观测/诊断域

### 2026-04-27 Config Freeze / Research Isolation 的下一主线判断

1. 当前最需要切断的不是新的数据库介质，而是 runtime 被研究链反向污染的最短路径：
   - `ConfigManager.set_instance()`
   - profile switch API
   - Backtester 对 `ConfigManager.get_instance()` 的隐式依赖
2. 因此 config freeze 的首轮实施不应是“大迁移”，而应是：
   - 收紧来源优先级
   - 去掉全局单例污染入口
   - 给 active profile 切换增加确认门槛
3. 只有在 runtime freeze 与 research isolation 形成架构事实后，才适合重新评估 `signals` 是否迁 PG。

### 2026-04-27 当前最短污染路径的修复状态

1. 研究脚本中的 `ConfigManager.set_instance()` 目前已通过 `try/finally -> set_instance(None)` 做到**执行期内临时占用、结束后强制清理**。
   - 这不是终局方案
   - 但已经足以把“脚本结束后污染 runtime 全局单例”的风险降下来
2. profile switch API 已新增显式确认门槛。
   - active profile 切换不再是无确认直接执行
3. 因此当前剩下的真正核心耦合点已经收敛到一个：
   - `Backtester.run_backtest()` 对 `ConfigManager.get_instance()` 的隐式依赖
4. 这也意味着下一步不该继续撒网，而应直接做：
   - backtester 去全局单例依赖
   - runtime / research 配置来源优先级的正式化

### 2026-04-27 Backtester 依赖已从“隐式全局”降为“显式注入优先”

1. `Backtester` 现在已经可以显式接受 `config_manager` 注入。
2. `ConfigManager.get_instance()` 仍保留为向后兼容 fallback，但不再是研究链脚本的默认路径。
3. 这意味着 config freeze 这条线的性质发生了变化：
   - 已不再是“运行期会被最短路径直接污染”的急性问题
   - 剩下的是“配置来源优先级是否足够清晰”的治理问题
4. 因此下一步应从代码救火切到规则固化：
   - runtime 配置来源优先级
   - research/backtest 配置来源优先级
   - 哪些入口允许 fallback，哪些入口必须显式注入

### 2026-04-27 Runtime / Research 配置来源优先级最终判断

1. runtime execution 与 research/backtest 必须被视为两条不同的配置消费链，而不是同一套配置源的不同调用者。
2. runtime execution 的业务真源应固定为：
   - `ResolvedRuntimeConfig`
   - `RuntimeConfigProvider`
3. runtime environment 的真源应固定为：
   - `.env` / process env
4. research/backtest 的正确优先级应为：
   - 显式 request/spec
   - 显式 overrides
   - 显式注入的局部 config provider / manager
   - research KV/defaults
   - code defaults
5. `ConfigManager.get_instance()` 仍可作为兼容 fallback，但必须被标记为 `legacy_fallback`，并逐步缩小使用面。
6. 这套优先级一旦不清晰，就会重新把“runtime freeze”退化回“谁最后写进 SQLite 谁赢”的隐式系统。

### 2026-04-27 `signals` 的下一步不应是“默认开迁”，而应先满足准入条件

1. `signals` 当前的合理定性是 **runtime pre-execution state**：
   - 会影响 cache rebuild
   - 会影响 cover/opposing signal 判断
   - 会影响 pending signal 状态推进
2. `signal_attempts` 当前更接近 observability / diagnosis，应与 `signals` 拆开决策。
3. `signal_take_profits` 当前不应被重新升级为 execution truth；它更像 signal 原始 TP 建议的附属持久化。
4. 因此，`signals` 若进入下一窗，前提应是：
   - execution truth 边界已稳定
   - config freeze / research isolation 已稳定
   - 业务上继续确认 `signals` 仍然承担 execution 上游状态语义
5. 这意味着当前最合理动作不是“继续迁表”，而是先把 `signals` 作为独立域命名清楚，再判断是否迁移。
