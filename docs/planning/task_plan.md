# Task Plan: 盯盘狗策略优化项目

> **Created**: 2026-04-15
> **Last updated**: 2026-04-24 01:45
> **Status**: Sim-0 受控链路通过，Runtime Resolver 已接入 main.py，market/risk/strategy/execution 已实切到 SignalPipeline
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

下一步不是继续开发大功能，而是进入 **Sim-0：真实模拟盘全链路验证**。

### 当前唯一主线

**Sim-0：验证真实链路从行情/信号管道到 testnet 下单、WS 回写、启动对账、PG recovery、breaker 的闭环。**

### 设计前提（已锁定）

1. 当前主线已明确，不再并行展开回测/前端/API 新线
2. 只要属于执行、恢复、对账、熔断语义，设计时默认优先考虑 PG 主线
3. 非 PG 实现只允许作为明确标注的过渡态

### 当前明确不做

1. 不做回测精细化深挖
2. 不做前端扩张
3. 不做 API 面扩张
4. 不同时推进多条 PG 表迁移

---

## 近期规划

### 目标

用真实模拟盘链路验证当前系统是否能稳定完成：

`行情/K线 -> SignalPipeline -> 策略/过滤器 -> 风控/仓位 -> ExecutionOrchestrator -> ExchangeGateway testnet 下单 -> WS 回写 -> OrderLifecycle -> StartupReconciliation -> PG recovery / breaker / 告警`

### Sim-0 启动定义

#### 阶段主题

**真实模拟盘全链路验证**

#### 阶段目标

1. 证明真实信号管道能触发 testnet 下单
2. 证明 ENTRY / TP / SL / WS 回写 / 对账链路能闭合
3. 证明 PG recovery task 和 breaker 在真实启动/重启链路中可用

#### 本阶段只做

1. Sim-0 启动配置冻结
2. 主程序真实启动
3. 信号到下单链路验证
4. WS 回写与保护单验证
5. 启动对账与恢复验证

#### 本阶段不做

1. 不做回测精细化
2. 不做参数搜索扩展
3. 不做前端/工作台推进
4. 不做新的 API 面扩张
5. 不同时推进多张核心 PG 表的实切
6. 不在 Sim-0 运行中热改策略参数

#### 本阶段入口任务

**Sim-0.1：启动配置冻结。**

需要冻结：

1. `CORE_EXECUTION_INTENT_BACKEND=postgres`
2. `CORE_ORDER_BACKEND=sqlite`
3. testnet / 模拟盘环境
4. 单 symbol：`BTC/USDT:USDT`
5. 当前冻结策略参数
6. 飞书 webhook 开启

#### 已完成的前置验证

1. `docs/reports/2026-04-23-sim-trading-readiness-smoke-check.md`
2. 四个准入场景全部通过：
   - 正常链路冒烟
   - `replace_sl_failed` 异常链路冒烟
   - 启动恢复冒烟
   - 熔断拦截冒烟

详细 Sim-0 任务拆分见：

- `docs/planning/sim-0-real-chain-validation-plan.md`

### 近期事项（按优先级）

1. **Sim-0.1 启动配置冻结**
   - 锁定环境变量、symbol、策略、PG/SQLite backend 开关

2. **Sim-0.2 主程序真实启动**
   - 验证 PG 初始化、Phase 4.3、Phase 4.4、ExchangeGateway、WS、SignalPipeline

3. **Sim-0.3 信号到下单链路验证**
   - 证明真实/模拟行情能触发 SignalPipeline 并进入 testnet 下单

### 当前建议顺序

1. 先完成 Sim-0 配置冻结
2. 再真实启动主程序
3. 再观察至少一笔信号触发到 testnet 下单
4. 再做重启对账验证

### 当前执行状态

- 模拟盘准入冒烟已通过
- Sim-0.2 ~ Sim-0.5 真实 runtime 链路已阶段性通过
- 受控验证仓位/保护单已清理
- 下一步进入分阶段自然模拟盘观察，不再连续无停顿推进

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
3. `orders / positions` 是否继续切 PG，不属于 Sim-0 前置动作
4. `CORE_ORDER_BACKEND=postgres` 等 Sim-0 观察后再评估

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
   - 不扩回测/Optuna
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
   - 执行配置边界已加固：
     - `tp_ratios` 必须全部为正数
     - `tp_targets` 必须全部为正数
   - `CapitalProtectionManager` 账户级熔断仍暂用原 ConfigManager 派生配置
7. 下一步切换边界：
   - 先做 runtime config 切换后的代码审查
   - 再做真实启动级冒烟验证
   - 不继续扩大配置面，避免把账户级熔断、API、前端一起卷入

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
