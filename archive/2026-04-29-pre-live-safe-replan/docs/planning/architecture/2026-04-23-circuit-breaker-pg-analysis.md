# Circuit Breaker PG 归属分析

> 日期：2026-04-23
> 阶段：Phase 2 启动分析
> 结论类型：架构判断（不含实现）

---

## 1. 问题定义

当前 `circuit_breaker` 的行为是：

1. 在 `ExecutionOrchestrator` 中以进程内 `set(symbol)` 存在
2. 当 `replace_sl_failed` 发生时触发
3. `execute_signal()` 在入口处检查是否熔断
4. `StartupReconciliationService` 在待恢复问题清除后解除熔断

当前问题不是“功能缺失”，而是：

**它是否应该像 `ExecutionIntent` / `execution_recovery_tasks` 一样进入 PG 主线。**

---

## 2. 当前业务语义判断

`circuit_breaker` 并不是一个独立业务事实，它更像：

1. 对执行恢复问题的保护性投影
2. 一个“禁止继续开新仓”的运行态结论
3. 它的触发前提来自恢复任务
4. 它的解除前提也来自恢复任务是否已收敛

所以它和 `execution_recovery_tasks` 的关系不是并列，而是：

**`circuit_breaker` 更像恢复工单的派生状态（derived state），不是第一性真源。**

---

## 3. 方案对比

### 方案 A：把 `circuit_breaker` 单独做成 PG 表

例如新增：

- `execution_circuit_breakers`

字段可能包括：

- `symbol`
- `reason`
- `related_task_id`
- `status`
- `created_at`
- `updated_at`
- `cleared_at`

#### 优点

1. 语义直观
2. 跨进程可见
3. 便于单独查询和手工操作

#### 缺点

1. 会引入一份新的执行状态真源
2. 和 `execution_recovery_tasks` 高度重复
3. 容易出现：
   - recovery task 已 resolved
   - breaker 表却忘了 clear
   - 或 breaker 已 clear 但 task 仍 active
4. 需要维护两套状态一致性

#### 结论

**不推荐。**

它把一个“派生保护状态”提升成了新的主事实，成本高，而且容易制造一致性问题。

---

### 方案 B：不单独建 PG breaker 表，改为从 `execution_recovery_tasks` 派生

做法：

1. `execution_recovery_tasks` 继续作为恢复真源
2. `circuit_breaker` 不单独持久化成新表
3. 运行时的 breaker 仍可保留为内存投影/热缓存
4. 重启后由 PG active recovery tasks 重建 in-memory breaker 集合

#### 优点

1. 真源单一
   - 恢复问题只在 `execution_recovery_tasks` 里
2. breaker 是派生状态，语义更干净
3. 不新增新表，不扩大 PG 核心面
4. 启动恢复逻辑天然可重建 breaker
5. 更符合当前 Phase 2 的“向 PG 收敛，但不制造新状态分叉”

#### 缺点

1. breaker 查询会依赖 recovery task 状态解释
2. 若未来 breaker 语义扩展到“非恢复类原因”，需要重新评估是否独立成表

#### 结论

**推荐。**

---

## 4. 推荐架构结论

### 正式结论

**`circuit_breaker` 不应单独 PG 真源化为新表。**

更合理的方案是：

1. `execution_recovery_tasks` 作为恢复真源
2. `circuit_breaker` 作为从 active recovery tasks 派生出来的保护状态
3. 运行时保留内存集合，仅作为快速判断缓存
4. 启动时由 PG active recovery tasks 重建 breaker 集合

---

## 5. 对当前链路的具体影响

### 保留的

1. `execute_signal()` 入口检查 breaker
2. 运行时 `set(symbol)` 形式的快速判断
3. 告警语义保持不变

### 将来应调整的

1. breaker 的来源不再以 SQLite `pending_recovery` 为准
2. breaker 的重建和清理应转向：
   - `execution_recovery_tasks.status in ('pending', 'retrying')`
3. 启动时：
   - 不只是“清理 pending_recovery”
   - 还应根据 active recovery tasks 重建 breaker

---

## 6. 阶段性实施建议

### 本阶段建议只做两步

1. **先把 breaker 的真源逻辑改判定为“来自 PG recovery tasks”**
   - 不新增表
   - 不做大运维面

2. **再逐步削弱 SQLite `pending_recovery` 对 breaker 的影响**
   - 让它只作为过渡兼容
   - 最终退出主链

---

## 7. 当前不做

1. 不新增 `execution_circuit_breakers` 表
2. 不做 API 管理面
3. 不做复杂人工工单后台
4. 不在本轮扩展 breaker 到非恢复类原因

---

## 8. 最终一句话

**第二阶段入口任务虽然叫“`circuit_breaker` 是否 PG 真源化”，但更准确的架构结论是：它不应作为独立 PG 真源，而应作为 `execution_recovery_tasks` 的派生保护状态收敛进 PG 主线。**
