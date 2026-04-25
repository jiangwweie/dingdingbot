# Task Plan: 盯盘狗策略优化项目

> **Created**: 2026-04-15
> **Last updated**: 2026-04-25 22:35
> **Status**: 当前唯一主线已切到 Sim-1 自然模拟盘观察准备；冻结 runtime 为 `sim1_eth_runtime`（ETH 1h + 4h MTF, LONG-only）；研究链按路径 1 / 方案 A 收口，避免反向污染 runtime
> **Archive backup**: `docs/planning/archive/2026-04-23-planning-backup/task_plan.full.md`

---

## 当前阶段

### 阶段结论

第二阶段第一步已完成，模拟盘准入冒烟已通过：

1. ✅ `execution_recovery_tasks` 是 PG 正式恢复真源
2. ✅ `circuit_breaker` 由 PG active recovery tasks 重建（内存缓存）
3. ✅ SQLite `pending_recovery` 整条过渡链已移除
4. ✅ 恢复主链统一到 PG `execution_recovery_tasks`
5. ✅ recovery retry/backoff 策略已显式化
6. ✅ 准入级冒烟验证通过（mock/fake 层验证“可运行 + 可恢复 + 可拦截”）

### 当前真实状态

当前已经证明的是**执行恢复主链具备模拟盘准入条件**，但还没有证明真实模拟盘全链路已经跑通。

Sim-0 作为“受控验证阶段”已阶段性通过；当前主线已切换为 **Sim-1 ETH runtime config 收口 + 自然模拟盘观察准备**。

### 当前唯一主线

**Sim-1：以冻结的 `sim1_eth_runtime`（ETH 1h + 4h MTF, LONG-only）进入自然模拟盘观察窗口，并确保研究链（Backtest/Optuna）不会反向污染 runtime。**

阶段编号/引用规范：

- 跨文档阶段引用以 `docs/planning/sim-1-eth-runtime-config-plan.md` 的 `SIM1-R*` 为 SSOT。

### 设计前提（已锁定）

1. 当前主线已明确，不再并行展开回测/前端/API 新线
2. 只要属于执行、恢复、对账、熔断语义，设计时默认优先考虑 PG 主线
3. 非 PG 实现只允许作为明确标注的过渡态

### 当前明确不做

1. 不做回测精细化深挖
2. 不做前端扩张
3. 不做 API 面扩张
4. 不同时推进多条 PG 表迁移

### 本窗口策略沟通结论（2026-04-25）

本窗口只做策略沟通，不推进实现。当前新增结论如下：

1. **不应把 `2023` 的失效理解为“参数还没调对”**
   - 当前更合理的解释是：`LONG-only` 基准在 `2023` 所处 market regime 下不适配
   - 失效主因更接近 **regime mismatch**，而不是单一 `EMA` / `MTF` 参数问题

2. **不应把 `1h` 周期自动理解为“适配震荡”**
   - 当前基准策略虽然运行在 `1h`，但本体仍然是“顺大逆小抓趋势延续”
   - 因此 `1h` 只是触发节奏，不等于震荡市 alpha

3. **后续研究优先级应从“继续救 2023”切到“定义市场适用边界”**
   - 重点问题应改为：什么市场状态下该开，什么状态下不该开
   - 优先研究 `regime boundary / regime filter`
   - 暂不把 `15m`、新 exit 变体或 runtime 参数改动当作当前窗口的首要动作

4. **本轮策略沟通分析稿单独归档，不直接升级为 runtime 改动**
   - 参考文档：
     `docs/planning/2026-04-25-eth-baseline-market-regime-boundary-analysis.md`
   - 当前仅作为 Sim-1 观察期前的研究边界说明，不反向污染 `sim1_eth_runtime`

### 本窗口架构沟通结论（2026-04-25）

本窗口新增一条独立架构主线：**执行主线 PG 真源闭环**。

结论如下：

1. 本窗口目标只覆盖 runtime execution 主链，不扩大为“全库去 SQLite”。
2. 当前建议方案为保守版 `A'`：
   - `orders / execution_intents / execution_recovery_tasks / positions execution projection` 收口到 PG
   - `signals / signal_attempts` 继续保留在 SQLite
3. `signals / signal_attempts` 当前不迁，不是因为它们不重要，而是因为它们属于 runtime observability / signal 域，迁移它们会把本窗口从“执行主线闭环”扩大成“观察链整体迁移”。
4. 当前执行主线允许保留的跨库边界是：
   - `Signal(SQLite) -> ExecutionIntent(PG)`
   - `Order(PG).signal_id -> Signal(SQLite)`
5. 本窗口明确不动：
   - `runtime_profiles`
   - config repositories
   - backtest / research
   - reconciliation 独立 SQLite
   - 历史报表及非 execution console 面
6. 后续迁移顺序应固定为：
   - 第 1 窗口：execution 主链 PG 闭环
   - 第 2 窗口：runtime observability 收口（优先 `signals / signal_attempts`）
   - 第 3 窗口：参数 / 策略配置域迁移
   - 第 4 窗口：backtest / research / 报表域迁移

对应架构文档：

- `docs/arch/2026-04-25-执行主线PG真源闭环调研与架构设计.md`

### 本窗口研究链边界结论（2026-04-25）

本窗口新增一条独立研究主线边界：**双轨阶段继续推进 `Spec / Resolver / Reporter` 收口，但严格保持 `research-only`。**

结论如下：

1. 后续研究链默认继续做 `Spec / Resolver / Reporter` 收口。
2. 研究链必须保持 `research-only`，职责仅限：
   - 纯回测
   - Optuna 搜索
   - candidate 产物
   - 解释分析 / 报告
3. 在 SQLite + PG 双轨并行阶段，**不得新增 runtime 直读 SQLite 的旁路**。
   - runtime 真源继续按当前冻结链路执行
   - 研究便利性不能成为新增 runtime SQLite 直读入口的理由
4. 所有研究产物只允许输出 `candidate`，不允许直接影响 `sim1_eth_runtime`。
   - 不自动 promote runtime
   - 不通过脚本直接覆写 runtime profile
   - candidate → runtime 的切换必须经过人工审查与显式冻结
5. 研究链与 runtime 链的职责边界固定为：
   - `research`：生成候选、证据、报告
   - `runtime`：承载冻结配置、执行自然观察
6. 当前双轨阶段的推荐收口顺序是：
   - 先完成研究入口统一到 `Spec / Resolver / Reporter`
   - 再统一 candidate report / compare 口径
   - 不在本窗口内新增任何“研究结果直接改 runtime”的捷径

---

## 近期规划

### 目标

用真实模拟盘链路验证当前系统是否能稳定完成：

`行情/K线 -> SignalPipeline -> 策略/过滤器 -> 风控/仓位 -> ExecutionOrchestrator -> ExchangeGateway testnet 下单 -> WS 回写 -> OrderLifecycle -> StartupReconciliation -> PG recovery / breaker / 告警`

### Sim-1 启动定义（替代 Sim-0）

#### 阶段主题

**自然模拟盘观察准备（冻结 runtime + 可审计）**

#### 阶段目标

1. 证明 `sim1_eth_runtime` 的 effective snapshot/hash 可追溯且启动稳定
2. 证明 SignalPipeline 的 market/risk/strategy/execution 均来自 runtime snapshot（冻结不热改）
3. 证明启动对账/恢复/breaker 等强执行语义状态仍可用（PG 主线不回退）

#### 本阶段只做（Sim-1）

1. Sim-1 启动配置冻结（ETH 1h + 4h, LONG-only）
2. 主程序真实启动（runtime snapshot + safe summary）
3. 自然观察窗口（低频，不追求交易次数）
4. 仅在需要时进行最小研究脚本收口（方案 A：脚本薄化）

#### 本阶段不做（Sim-1 期间）

1. 不做回测精细化
2. 不做参数搜索扩展
3. 不做前端/工作台推进
4. 不做新的 API 面扩张
5. 不同时推进多张核心 PG 表的实切
6. 不在 Sim-1 运行中热改策略/风控/执行参数

#### 本阶段入口任务

**Sim-1.1：启动配置冻结与验收。**

需要冻结：

1. `CORE_EXECUTION_INTENT_BACKEND=postgres`
2. `CORE_ORDER_BACKEND=sqlite`
3. testnet / 模拟盘环境
4. 单 symbol：`ETH/USDT:USDT`
5. 当前冻结策略参数
6. 飞书 webhook 开启

#### 已完成的前置验证

1. `docs/reports/2026-04-23-sim-trading-readiness-smoke-check.md`
2. 四个准入场景全部通过：
   - 正常链路冒烟
   - `replace_sl_failed` 异常链路冒烟
   - 启动恢复冒烟
   - 熔断拦截冒烟

Sim-0 详细任务拆分（归档参考）：

- `docs/planning/sim-0-real-chain-validation-plan.md`

### 近期事项（按优先级）

1. **Sim-1.1：冻结 runtime profile 并输出可审计 snapshot**
   - `sim1_eth_runtime` 固定：ETH `1h` + `4h`、LONG-only、ATR disabled、risk/execution 口径一致
   - 启动日志打印 `profile/version/hash` + safe summary

2. **Sim-1.2：自然模拟盘观察窗口**
   - 低频观察为主，不追求交易次数
   - 运行期间禁止热改 strategy/risk/execution（只允许写入“下次启动生效”配置）

3. **研究链收口（路径 1，方案 A）**
   - 迁移纯回测入口与 Optuna 入口到统一 Spec/Resolver/Reporter
   - 只产出 candidate，不自动 promote runtime
   - 不新增 runtime 直读 SQLite 的研究旁路

### 当前建议顺序

1. 先完成 Sim-1.1 冻结与验收（SIM1-R0..R5）
2. 再进入 Sim-1.2 自然观察窗口（SIM1-R8）
3. 观察期内按需做研究脚本收口（SIM1-R6..R7）

### 当前执行状态

- 模拟盘准入冒烟已通过
- Sim-0 真实 runtime 链路已阶段性通过（作为受控验证归档）
- 受控验证仓位/保护单已清理
- 下一步进入 Sim-1 自然模拟盘观察（ETH 1h，4h 作为 MTF 辅助）

### Sim-0 阶段性结果

1. ✅ 主程序真实启动通过
2. ✅ 受控 K 线触发真实信号
3. ✅ testnet ENTRY 市价成交
4. ✅ TP1 / TP2 / SL 保护单挂载成功
5. ✅ PG intent 落 `completed`
6. ✅ 重启对账通过：候选订单 0，对账失败 0
7. ✅ PG active recovery tasks 0，breaker 为空

报告：

- `docs/reports/2026-04-23-sim-0-real-chain-validation.md`

### 下一暂停点后的第一任务

✅ 已修复 `SignalPipeline` attempt flush 的 Decimal JSON 序列化问题。

修复结果：

1. `SignalRepository` 新增 Decimal/Enum 安全 JSON 序列化 helper
2. `signal_attempts.details` / `trace_tree` 可保存真实策略诊断里的 Decimal
3. `signals.tags_json` 也复用同一序列化入口
4. 新增回归用例覆盖 Decimal pattern details / score

下一步：

暂不直接进入自然模拟盘观察窗口。先完成 `config module` 收口，明确 `.env`、SQLite 配置库、历史 YAML、代码默认值、回测 runtime overrides、执行参数之间的真源边界，并将 Sim-1 目标切换为 ETH runtime profile。

新增规划：

- `docs/planning/sim-1-eth-runtime-config-plan.md`

---

## 后续规划

### A. 执行链方向

1. Sim-0 真实链路验证
2. Config module 真源梳理
3. Sim-1 前配置收口
4. Sim-0/Sim-1 自然观察复盘
5. 根据观察暴露问题决定是否补执行链或运维能力

### B. PG 迁移方向

1. `ExecutionIntent` 已切通
2. `execution_recovery_tasks` 已接通
3. 新增独立窗口：执行主线 PG 真源闭环（`orders / positions execution projection`）
4. `signals / signal_attempts` 不并入当前窗口，待 execution 主链稳定后再迁
5. 参数 / 策略配置域迁移必须等 runtime config SSOT 稳定后再评估
6. backtest / research / 历史报表迁移放在最后，不进入当前与下一窗口
7. 当前窗口第一层代码骨架已完成：
   - order repo fallback 已统一回到工厂
   - `ExecutionOrchestrator -> OrderLifecycleService` 的保护单 created 持久化绕过点已收口
   - `positions` 的 PG projection service / repository / runtime read fallback 已打通最小骨架
   - 即时 `full fill` 与 `partial fill` 两条主路径都已接入 projection 入口
   - WebSocket / 对账把 ENTRY 推到 `FILLED` 的场景也已通过 callback 串回 orchestrator
   - `TP/SL filled` 也已接入 projection 更新链，开始具备本地持仓执行态收缩能力
   - runtime execution 装配已显式切到 PG order/position runtime 工厂，不再依赖通用工厂的环境变量切换
   - runtime overview 已能展示实际 execution backend，而不是仅显示历史环境变量
8. 当前窗口下一步应进入：
   - fee 映射、幂等、防重放、乱序回放下的 position projection 语义加固
   - 针对 PG order/position 路径的定向单测与集成验证

### C. 研究/回测方向（非当前主线）

1. 回测精细化
2. 参数继续搜索
3. `backtest-studio` 独立前端

这些事项保留 backlog，不进入当前阶段执行。

### D. Config module 方向（下一主线入口）

1. 梳理当前配置来源：
   - `.env`
   - SQLite config tables
   - 历史 YAML
   - 代码默认值
   - 回测 runtime overrides / KV
   - PG execution state
2. 梳理配置读取路径：
   - exchange
   - notification
   - system symbols/timeframes
   - strategy definitions
   - risk config
   - execution order strategy / TP/SL
   - backtest params
   - recovery / breaker
3. 输出近期最小收口：
   - 明确哪些配置只看 `.env`
   - 哪些配置继续暂存 SQLite
   - 哪些配置只允许代码默认值兜底
   - YAML 只作为废弃技术债处理
4. 输出中期方案：
   - 是否迁移 config module 到 PG
   - 如迁移，表设计和阶段切换顺序

### E. Sim-1 ETH runtime config 方向（当前规划）

1. 使用五模块模型整理配置：
   - `environment`
   - `market`
   - `strategy`
   - `risk`
   - `execution`
2. Sim-1 标的切换为 `ETH/USDT:USDT`
3. 主周期为 `1h`，MTF 辅助订阅 `4h`
4. ETH baseline 以 `docs/planning/backtest-parameters.md` 为主真源
5. 当前 BTC 配置仅作为 `sim0_controlled_btc` 归档
6. 模拟盘期间禁止热改 strategy / risk / execution config
7. Optuna 只输出 candidate，不自动应用 runtime

详细规划：

- `docs/planning/sim-1-eth-runtime-config-plan.md`

### F. Config Module SSOT / Runtime Resolver 方向（当前执行）

1. 已确认架构决策：
   - Config 短中期继续保留 SQLite
   - PG 继续只管 execution state / recovery / breaker
   - 后续 config 迁 PG 不是 Sim-1 前置条件
2. 已新增设计文档：
   - `docs/planning/architecture/2026-04-23-config-module-ssot-runtime-resolver-design.md`
   - `docs/planning/architecture/2026-04-23-runtime-config-implementation-skeleton.md`
3. 推荐下一步实现骨架：
   - ✅ 新增 SQLite `runtime_profiles` 窄表
   - ✅ 新增 `ResolvedRuntimeConfig` Pydantic 模型
   - ✅ 新增 `RuntimeConfigResolver`
   - ✅ 新增 `sim1_eth_runtime` seed / verify 脚本
4. 当前不做：
   - 不迁 Config 到 PG
   - 不扩前端
   - 不允许模拟盘期间热改 strategy / risk / execution
5. 关键后续收口：
   - `.env` 成为 exchange secret / webhook 真源
   - execution 模块成为实盘 TP/SL 的唯一真源
   - `SignalResult.take_profit_levels` 降级为 preview / notification / research 语义
6. 当前实现状态：
   - Runtime Config 骨架已完成
   - 审查提出的 hash / readonly / transaction / strategy 契约问题已修复
   - 已 seed 本地正式 `data/v3_dev.db` 的 `sim1_eth_runtime`
   - 已接入 `main.py` Phase 1.1 启动解析
   - market scope 已实切：
     - `symbols=ETH/USDT:USDT`
     - `timeframes=1h,4h`
     - `warmup_bars=100`
     - `asset_polling_interval=60s`
   - SignalPipeline risk 已实切：
     - `max_loss_percent=0.01`
     - `max_leverage=20`
     - `max_total_exposure=1.0`
     - `daily_max_trades=10`
   - SignalPipeline strategy 已实切：
     - `trigger=pinbar`
     - `filters=ema,mtf,atr(disabled)`
     - `allowed_directions=LONG`
     - `scope=ETH/USDT:USDT:1h`
     - `mtf_ema_period=60`
   - execution `OrderStrategy` 已实切：
     - `tp_levels=2`
     - `tp_ratios=0.5,0.5`
     - `tp_targets=1.0,3.5`
     - `initial_stop_loss_rr=-1.0`
     - `trailing_stop_enabled=False`
     - `oco_enabled=True`
   - LONG-only direction policy 已在 attempt 持久化前落地：
     - 不允许方向的 fired attempt 转为 `FILTERED`
     - 追加 `runtime_direction_policy` filter result
   - Runtime config / SignalPipeline 单元测试已补齐：
     - `tests/unit/test_runtime_config_signal_pipeline.py`
     - 27 passed
   - Runtime cutover 非 I/O 冒烟已补齐：
     - `scripts/verify_sim1_runtime_cutover.py`
     - 验证 market/risk/strategy/execution 四模块可按 main.py 切换语义组装
   - Backtest config 抽象层已补齐：
     - 新增 `src/application/backtest_config.py`
     - 新增独立 `backtest_eth_baseline` profile，不直接读取 `sim1_eth_runtime`
     - 保留优先级：`runtime_overrides > request > backtest profile > code defaults`
     - 新增 `ResolvedBacktestConfig`
     - 新增显式可注入参数契约 `BACKTEST_INJECTABLE_PARAMS`
     - 当前可注入参数 25 个，覆盖 market / strategy / risk / execution / engine / diagnostic
     - 标记 `optimizer_safe` 参数，供 Optuna/前端回测后续使用
   - Backtest config 小范围验证已通过：
     - `tests/unit/test_backtest_config_resolver.py`
     - 10 passed
     - `scripts/verify_backtest_config_resolver.py`
     - 无 exchange / PG / historical data I/O
   - Optuna 隔离已完成：
     - `StrategyOptimizer` 默认使用 `backtest_eth_baseline`
     - 参数空间必须命中 `optimizer_safe=True` 白名单
     - fixed params 必须命中 `BACKTEST_INJECTABLE_PARAMS`
     - trial request / strategy / risk / execution 由 `BacktestConfigResolver` 生成
     - 不写 runtime DB，不自动应用模拟盘
     - 已消除 Optuna 内部 ETH baseline TP/risk/strategy 硬编码
   - Optuna / Backtest config 小范围验证已通过：
     - `tests/unit/test_strategy_optimizer.py`
     - `tests/unit/test_optuna_runtime_overrides.py`
     - `tests/unit/test_backtest_config_resolver.py`
     - 58 passed
   - Optuna QA 二次审查问题已收口：
     - 删除 `_build_backtest_request()` dead code
     - 每个 trial 只执行一次 resolver
     - `BacktestRuntimeOverrides` 使用 Pydantic 字段过滤构造
     - engine fixed params 已覆盖 `initial_balance/slippage_rate/tp_slippage_rate/fee_rate`
     - 风控 fallback 强制来自当前 profile，不再 import ETH baseline 常量
   - 两个 P1 已收口：
     - `.env` 已移除本地 PG 连接串和 backend 切换值
     - `api.py` standalone shutdown reset 防线已由 `test_api_lifespan_runtime.py` 覆盖
     - 合并验证：68 passed
   - 执行配置边界已加固：
     - `tp_ratios` 必须全部为正数
     - `tp_targets` 必须全部为正数
   - `CapitalProtectionManager` 已接入 runtime risk 派生：
     - `single_trade.max_loss_percent` 跟随 runtime `risk.max_loss_percent`
     - `daily.max_loss_percent` 跟随 runtime `daily_max_loss_percent`
     - 启动时若拿到账户权益快照，则冻结派生 `daily.max_loss_amount`
     - 若启动时尚无账户快照，则保留百分比口径回退，不伪造金额
   - Optuna candidate report 已落地：
     - `StrategyOptimizer.write_candidate_report()`
     - 输出目录：`reports/optuna_candidates/`
     - 只产出 candidate JSON，不自动 promote runtime profile
   - Candidate review rubric 已落地：
     - `docs/planning/optuna-candidate-review-rubric.md`
     - 当前口径：`Strict v1 / Loose v1 / Warning-only checks`
     - 当前评审状态：`PASS_STRICT / PASS_STRICT_WITH_WARNINGS / PASS_LOOSE / REJECT`
   - 研究/验证脚本最小入口已收口：
     - `scripts/verify_fixed_params_minimal.py` 已切到 resolver trial inputs
7. 下一步切换边界：
   - 回测 API 暂缓，当前不做 Web
   - 按需将仍会使用的研究脚本入口接入 `BacktestConfigResolver`（决策：先行方案 A，脚本薄化；方案 B 延后）
   - 真实 Optuna 小规模搜索运行前单独确认
   - warning-only 评审项后续补齐：
     - trade concentration
     - profit concentration
     - max consecutive losses
   - 再做真实启动级冒烟验证
   - 前端重构已进入规划阶段，但当前只推进方案 A：
     - 一级导航拆为 `Runtime` / `Research`
     - 第一版只读为主
     - Candidate review 第一版只展示，不写回
     - Runtime 页面第一版使用手动刷新
     - Backtest Studio 作为二期并入
   - 前端规划 SSOT：
     - `docs/planning/architecture/2026-04-24-frontend-runtime-monitor-and-research-console-plan.md`
   - 前端第一阶段目标：
     - 先做 Runtime Monitor MVP
     - 再接 Research 的 candidate / replay 只读页
     - 不做配置编辑，不做 runtime 热改
   - 前端规划新增补充边界：
     - `Runtime / Overview` 必须展示 freshness / heartbeat
     - 默认只允许本地 / 内网访问
     - `Replay` 第一版按 replay context 理解，不承诺 K 线图表
     - `Candidates` 第一版允许目录扫描，后续视规模补文件索引缓存
   - 前端页面补充方案 A 已确认：
     - `Runtime / Portfolio`
     - `Runtime / Positions`
     - `Runtime / Events`
     - `Config / Snapshot`（只读）
     - `Research / Candidate Review`（只读）
   - 页面补充方案 A 的目标：
     - 更贴近量化值班者使用场景
     - 先补观察 / 理解能力
     - 仍不引入写操作
   - 当前前端扩展主线已切换为方案 B：
     - 基于 `gemimi-gemimi-web-front` 现有骨架继续扩展
     - 目标是完整控制台，而不是单点补页
     - 新的主文档：
       - `docs/planning/architecture/2026-04-25-frontend-console-plan-b.md`

### G. 后端只读 API 方向（当前主线扩展）

1. 方向判断：
   - 前端骨架和 mock 数据已经足够支撑下一步推进
   - 当前真正的瓶颈已转为“后端只读数据供给”
   - 主模块仍依赖 `src/interfaces/api.py` 启动，因此 API 需要先瘦身而不是一次性重写
2. 关键决策：
   - 先做只读 API，不做写接口
   - 先做页面级聚合接口，不先直出数据库表
   - `api.py` 继续作为兼容入口，但逐步把控制台相关路由拆出去
   - 运行主线以 Sim-1 真实数据为真源，前端 mock 只作为临时垫层
3. 当前页面对应的 API 优先级：
   - P0：`runtime/overview`、`runtime/portfolio`、`runtime/positions`、`runtime/events`、`runtime/health`
   - P1：`runtime/signals`、`runtime/attempts`、`runtime/execution/intents`、`runtime/execution/orders`
   - P1：`research/candidates`、`research/candidates/{candidate_name}`、`research/candidates/{candidate_name}/review-summary`、`research/replay/{candidate_name}`
   - P2：`research/backtests`、`research/backtests/{report_id}`、`research/compare/*`、`config/snapshot`
   - P3：`runtime/alerts`、`research/runs`、`research/artifact-explorer`
4. 当前待办步骤：
   1. 冻结前端页面契约和 mock 字段命名，避免后端接口反复改口径。
   2. 将第一批实现固定为 4 个接口：
      - `GET /api/runtime/overview`
      - `GET /api/runtime/portfolio`
      - `GET /api/runtime/health`
      - `GET /api/research/candidates`
   3. 第二批固定为：
      - `GET /api/runtime/positions`
      - `GET /api/runtime/signals`
      - `GET /api/runtime/attempts`
      - `GET /api/runtime/execution/orders`
      - `GET /api/runtime/execution/intents`
   4. 第三批固定为：
      - `GET /api/research/candidates/{candidate_name}`
      - `GET /api/research/replay/{candidate_name}`
      - `GET /api/research/candidates/{candidate_name}/review-summary`
      - `GET /api/config/snapshot`
   5. `GET /api/runtime/events` 延后到后续批次，待事件聚合设计稳定后再实现。
   6. 第一阶段模块落点已确认：
      - `src/application/readmodels/runtime_overview.py`
      - `src/application/readmodels/runtime_portfolio.py`
      - `src/application/readmodels/runtime_health.py`
      - `src/application/readmodels/candidate_service.py`
      - `src/interfaces/api_console_runtime.py`
      - `src/interfaces/api_console_research.py`
   7. 用 Sim-1 真实数据逐页校验 mock 与后端的差异。
5. 当前 SSOT 文档：
   - `docs/planning/architecture/2026-04-25-backend-readonly-api-and-api-module-roadmap.md`
   - `docs/planning/architecture/2026-04-25-console-readonly-api-v1-contract.md`
6. 非目标：
   - 不做配置编辑
   - 不做 runtime 热改
   - 不做 review 写回
   - 不做一口气重写 `api.py`

---

## 约束提醒

1. 强执行语义状态优先向 PG 收敛
2. SQLite 只允许作为明确标注的过渡态
3. 新增执行状态真源前，先复核表设计
4. 测试执行前遵守项目红线，先用户确认

---

## 历史说明

旧版完整任务计划、历史阶段、研究冻结记录、长期 backlog 已备份到：

- `docs/planning/archive/2026-04-23-planning-backup/task_plan.full.md`

主文档今后只保留：

1. 当前阶段
2. 近期规划
3. 后续规划

---

## 2026-04-25 执行一致性补丁

当前正在收口执行主线 PG 闭环后的第二层风险修复，范围只限 runtime execution 主链：

1. `PositionProjectionService`
   - 增加同仓位投影锁，降低并发脏写概率
   - `project_exit_fill()` 改为按 `exit_order.id` 的累计成交量/手续费做幂等增量投影
   - 不再只适配“首次 FILLED”单次扣减
2. `OrderLifecycleService`
   - 新增 exit progressed callback
   - `TP/SL` 只要成交量前进，就回调 position projection
   - 修复 `partial fill -> canceled` 不入本地仓位的问题
3. `ExecutionOrchestrator`
   - protection order 不再盲目 `confirm_order()->OPEN`
   - 改为按 `placement_result.status` 推进本地状态
   - 替换 SL 后新 SL 提交失败/异常时，统一触发 recovery + 熔断 + 告警
   - 为 `ExecutionIntent` 增加状态前进约束，阻止 `COMPLETED -> PARTIALLY_PROTECTED` 之类回退

测试仍未由 Codex 本地执行；如需 pytest，继续遵守项目红线，先由用户确认。
