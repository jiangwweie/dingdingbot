# 2026-04-27 Signal 域定性与 Config Freeze / Research Isolation 实施计划

> 状态：执行中
> 目的：在 execution PG 主线完成后，明确 `signals / signal_attempts` 的真实角色，并给出配置冻结与研究链隔离的下一轮实施清单

---

## 1. 结论先行

### 1.1 `signals` 不是纯 observability

当前代码表明，`signals` 表承担的是 **pre-execution decision state**，而不只是观察日志：

1. `SignalPipeline.initialize()` 会从 `signals` 表恢复 `ACTIVE/PENDING` 信号到 `_signal_cache`
2. `_check_cover()` 依赖已持久化 signal 做同向覆盖判断
3. `_check_opposing_signal()` 依赖已持久化 signal 做反向信号冲突判断
4. `update_superseded_by()` 会把旧 signal 标记为 `superseded`
5. `PerformanceTracker.check_pending_signals()` 会基于 `pending_signals` 更新 `WON/LOST`

**结论**：`signals` 属于“执行前、但会影响后续信号决策与状态推进”的域，不应简单视为纯 console 观察数据。

### 1.2 `signal_attempts` 更接近 observability / diagnosis

当前代码表明，`signal_attempts` 主要用于：

1. `SignalPipeline.save_attempt()` 保存评估过程与 `final_result`
2. console 的 attempts 页面
3. `attribution_analyzer` / `attribution_engine`
4. backtest / diagnostics / semantic summary

它**不直接驱动 execution runtime 的状态推进**。

**结论**：`signal_attempts` 当前应归入 **runtime observability / diagnosis**，优先级低于 `signals`。

### 1.3 因此，后续不应把 “signals / signal_attempts 迁 PG” 当作一个原子任务

更合理的拆法应是：

1. **Signal decision state**
   - `signals`
   - `signal_take_profits`（需进一步复核其当前实义）
2. **Signal diagnostics / observability**
   - `signal_attempts`

---

## 2. 新的边界定性

### 2.1 Runtime execution truth

已定型对象：

1. `orders`
2. `execution_intents`
3. `positions`（execution projection）
4. `execution_recovery_tasks`

### 2.2 Runtime pre-execution state

当前应独立定义的一层：

1. `signals`
2. 可能包括 `signal_take_profits`

特征：

- 不属于 execution truth
- 但也不是纯 observability
- 会影响后续同向覆盖、反向冲突、pending 状态跟踪

### 2.3 Runtime observability / diagnosis

当前应明确归在这里：

1. `signal_attempts`
2. runtime console 的 signals/attempts 只读面
3. attribution / diagnostics / semantic summaries

### 2.4 Config / research / history

保持独立边界：

1. `runtime_profiles`
2. `config_entries_v2` 及配置域
3. backtest / replay / candidate / optuna
4. historical klines / reports

---

## 3. Config Freeze / Research Isolation 当前真实风险

### P0

1. `ConfigManager.set_instance()` 允许研究脚本污染全局单例
2. profile switch API 可直接切 active profile，缺少更硬确认
3. runtime 与 research 共享 `data/v3_dev.db`，使“旁路修改 runtime 配置”成为现实风险

### P1

1. Backtester 默认尝试读取 `ConfigManager.get_instance()`
2. 研究脚本直接写 `config_entries_v2`
3. `runtime_profiles` 虽然有 readonly 语义，但运行期治理边界尚未形成正式规范

---

## 4. 下一轮实施主线

### 主线 1：先钉死配置来源优先级

必须写清楚并在代码/文档中统一：

1. runtime execution 读取优先级
   - `ResolvedRuntimeConfig`
   - process-local provider
   - 明确允许的 fallback
2. research/backtest 读取优先级
   - request / spec / explicit override
   - 局部 config provider
   - 不允许隐式读取全局 runtime instance

### 主线 2：切断研究脚本污染 runtime 的最短路径

最先处理：

1. 清理研究脚本中的 `ConfigManager.set_instance()`
2. 给 profile switch API 增加确认门槛
3. Backtester 去掉对全局 `ConfigManager` 的隐式依赖

### 主线 3：把 `signals` 与 `signal_attempts` 拆成不同策略

1. `signals`
   - 先按 **pre-execution decision state** 处理
   - 后续是否迁 PG，取决于是否要消灭 execution 上游跨库边界
2. `signal_attempts`
   - 先按 observability / diagnosis 处理
   - 不默认进入下一轮 PG 迁移

---

## 5. 推荐的下一轮任务包

### 由 Codex / GPT 继续负责

1. 配置边界 SSOT 定义
2. `signals` / `signal_attempts` 的角色定性与迁移准入条件
3. runtime freeze / research isolation 的实施顺序

### 适合 Claude / GLM 的杂活

1. 清理研究脚本里的 `ConfigManager.set_instance()`
2. 为 profile switch API 增加 `confirm` 参数与测试
3. Backtester 去除 `ConfigManager.get_instance()` 隐式依赖的机械改造
4. 文档/注释中补 `list_active()` / `list_blocking()` 语义说明

---

## 6. 最终判断

当前阶段最重要的新认知是：

1. `signals` 不应被误判为“纯观察数据”
2. `signal_attempts` 才更像纯 observability
3. 因此下一步应优先做 **config freeze + research isolation**
4. 然后再决定是否把 `signals` 作为“execution 上游状态”迁入 PG
