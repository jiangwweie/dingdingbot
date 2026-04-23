# Progress Log

> Last updated: 2026-04-23 23:20
> Archive backup: `docs/planning/archive/2026-04-23-planning-backup/progress.full.md`

---

## 近期完成

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
