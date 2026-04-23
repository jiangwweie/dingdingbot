# Findings Log

> Last updated: 2026-04-24 01:32
> Archive backup: `docs/planning/archive/2026-04-23-planning-backup/findings.full.md`

---

## 当前有效结论

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

1. `runtime_profiles` 采用 SQLite 窄表 + JSON profile 是当前最小可行方案。
   - 不破坏现有 `strategies / system_configs / risk_configs`
   - 不引入 PG config 迁移
   - 后续迁移只需替换 repository adapter

2. Resolver 必须在环境层做强校验。
   - 缺 `PG_DATABASE_URL`、交易所 key/secret、webhook 时直接失败
   - `CORE_EXECUTION_INTENT_BACKEND` 必须为 `postgres`
   - `CORE_ORDER_BACKEND` 当前默认保持 `sqlite`

3. 一次性脚本使用共享 SQLite 连接池时，必须在脚本结束前调用 `close_all_connections()`。
   - 否则 aiosqlite 后台线程可能导致脚本不退出
   - seed/verify 脚本已显式关闭连接池

4. Runtime profile 的 readonly 与 active 语义必须在仓储层强制。
   - `is_readonly=True` 不能只作为 UI/文档标记
   - 默认 upsert 必须拒绝覆盖 readonly profile
   - seed/维护脚本如需更新 readonly profile，必须显式传入 override 参数

5. `config_hash` 只应表达业务执行基准，不应混入纯基础设施变量。
   - DB DSN、backend port、repo backend switches 不进入 hash
   - `exchange_name / exchange_testnet` 会影响交易所执行环境，保留在 hash
   - secret 永远不进入 hash

6. `main.py` 的第一阶段接入必须先 observe-only。
   - 当前只在启动期解析 `sim1_eth_runtime`
   - 只保存 `RuntimeConfigProvider` 并打印脱敏 summary/hash
   - 不直接替换现有 `ConfigManager` 消费路径
   - 这样可以先证明 runtime profile 可解析、可审计、可追踪，再分模块切换消费方

7. Runtime config 消费切换应按模块逐步推进。
   - 第一刀只切 market scope，风险最低
   - 已让预热、订阅、资产轮询间隔从 `ResolvedRuntimeConfig.market` 获取
   - 第二刀只切 `SignalPipeline` 的 `RiskConfig`
   - `CapitalProtectionManager` 账户级熔断不随本刀切换，避免把仓位试算和账户保护混成一个变更
   - 第三刀切 `SignalPipeline` strategy runner，但必须同时锁定 ConfigManager 热重载回退路径
   - execution 暂不切，避免一次性改变保护单语义
   - 每切一个模块都应在日志中明确标记来源，便于 Sim-1 观察回溯

8. Runtime strategy 接入后，热重载必须遵守冻结 profile 边界。
   - runtime risk 已切入时，ConfigManager 热重载不能覆盖 `_risk_config`
   - runtime strategy 已切入时，ConfigManager 热重载不能覆盖 runner strategy / MTF EMA period
   - 如果未来要支持运行中变更 runtime profile，应通过新 profile + 重启或显式 reload 流程，而不是复用旧 ConfigManager observer 静默覆盖

9. execution 切换必须只保留一个实盘保护单策略入口。
   - runtime execution module 已转成 `OrderStrategy`
   - `SignalPipeline._build_execution_strategy()` 优先返回 runtime `OrderStrategy` 深拷贝
   - `SignalResult.take_profit_levels` 降级为展示/通知/研究语义，不再作为实盘 TP/SL 策略来源
   - `ExecutionIntent.strategy` 仍是后续 full-fill / partial-fill / recovery 保护单语义的一致性锚点

10. Runtime direction policy 必须在 attempt 持久化前落地。
   - 仅在执行前跳过 SHORT 不够，会污染 `signal_attempts` 审计语义
   - 不允许方向的 fired attempt 应转为 `FILTERED`
   - filter result 中记录 `runtime_direction_policy`，方便后续归因

11. Runtime execution config 必须拒绝非正数 TP 比例/目标。
   - `tp_ratios` 总和为 1.0 仍不够，`[-0.5, 1.5]` 这类输入会通过求和但语义非法
   - `tp_ratios` 每项必须 `> 0`
   - `tp_targets` 每项必须 `> 0`

12. Runtime strategy 应直接生成 `logic_tree`。
   - 新 runtime config 主线不应继续触发 `StrategyDefinition` deprecated triggers/filters 迁移路径
   - 可保留 `trigger/filters` 字段作为兼容和可读性辅助，但 `logic_tree` 必须显式生成

13. 本地 `.env` 已是历史遗留敏感文件，后续不应继续扩大其提交面。
   - 本轮没有修改 `.env`
   - PG 示例继续以 `docs/local-pg.md` / 示例文件为准
   - 若后续要彻底治理，需要单独安排 secret rotation + `.env` 脱离版本控制，不应混在 runtime config 接入任务中顺手做

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
