# 2026-04-27 Signals 迁移准入条件与域拆分

> 状态：执行中
> 目的：在不直接启动迁移的前提下，明确 `signals` 是否、何时、以什么边界进入下一轮主线

---

## 1. 当前定性

### 1.1 `signals`

当前 `signals` 表承担的是 **runtime pre-execution state**：

1. startup 时重建 signal cache
2. 同向 signal covering
3. opposing signal conflict check
4. superseded 状态推进
5. pending signal performance tracking

结论：

- 它不是 execution truth
- 但也不是纯 observability
- 它是 execution 上游的状态域

### 1.2 `signal_attempts`

当前 `signal_attempts` 更接近：

1. observability
2. diagnosis
3. attribution
4. semantic summary

结论：

- 它不直接驱动 runtime execution 状态推进
- 不应和 `signals` 绑定为同一迁移任务

### 1.3 `signal_take_profits`

当前 `signal_take_profits` 主要是 signal 原始 TP 建议的持久化附属表：

1. 随 signal 一起写入
2. 用于 signal context / 通知 / 回看
3. 当前 execution 主链已经转向 `OrderStrategy` / `ExecutionIntent.strategy`

结论：

- 它不应再被视为 execution protection truth
- 更接近 signal 域附属观测数据

---

## 2. 为什么现在不应直接迁 `signals`

不是因为它不重要，而是因为：

1. 当前更紧急的是边界治理，不是继续迁库
2. `signals` 属于 execution 上游状态域，迁移它需要同时回答：
   - runtime signal cache 如何重建
   - cover/opposing 查询如何建索引
   - signal 与 order/intent 的逻辑引用如何正式化
3. 如果现在直接开迁，很容易把下一窗重新带回“大迁库模式”

---

## 3. `signals` 进入下一窗的准入条件

只有在以下条件满足后，`signals` 才应进入下一轮主任务：

### G1. Execution truth 边界已经冻结

必须已明确：

1. `orders`
2. `execution_intents`
3. `positions projection`
4. `execution_recovery_tasks`

是 runtime execution truth，且后续不再反复改口径。

### G2. Config freeze / research isolation 已基本稳定

至少要满足：

1. 最短污染路径已切断
2. 配置来源优先级已有 SSOT
3. runtime 不再被 research 脚本轻易污染

### G3. `signals` 在业务上仍被确认属于执行上游状态

需要再次确认：

1. 是否仍保留 signal cache rebuild
2. 是否仍保留 cover / opposing signal 逻辑
3. 是否仍保留 pending signal performance tracking

如果这些能力未来被别的 execution 上游状态模型替代，则 `signals` 迁移优先级可能下降。

### G4. 迁移目标必须只覆盖 `signals`，不顺手捆绑 `signal_attempts`

下一窗若做，应该拆成：

1. `signals`（可能含必要的 signal 状态附属表）
2. `signal_attempts` 保持独立决策

---

## 4. 推荐的下一窗切法

### 方案 A（推荐）

只把 `signals` 作为 **pre-execution state** 迁移候选评估，不立即实施。

先完成：

1. 查询模式审计
2. 索引需求整理
3. signal/order/intent 逻辑引用关系梳理
4. 与 `signal_attempts` 解耦的迁移切面设计

优点：

1. 风险更小
2. 不会把 observability 一起卷进去
3. 更符合当前边界治理优先的主线

### 方案 B（不推荐）

把 `signals / signal_attempts / signal_take_profits` 整包拉进 PG 迁移窗。

缺点：

1. 范围过大
2. 容易把 observability、diagnostics、research 回放一起卷进来
3. 又会回到“表迁移优先”的旧轨道

---

## 5. 当前最合理的判断

1. `signals` 迟早可能进入下一轮主线，但前提是：
   - 它被继续确认属于 execution 上游状态
   - 边界治理先完成
2. `signal_attempts` 不应跟着一起被自动升级优先级
3. 当前最合理动作不是“开迁”，而是：
   - 先把它作为独立域正式命名
   - 再决定是否纳入下一窗
