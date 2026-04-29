# 2026-04-27 Recovery / Profile Switch 语义澄清

> 状态：完成
> 目的：收掉当前窗口最后两个“不是功能 bug，而是语义容易被误解”的尾巴

---

## 1. `list_active()` vs `list_blocking()`

这两个名字都在表达“恢复任务还没结束”，但语义不同，必须分开理解。

### `list_active()`

表示：**当前可执行的 recovery tasks**

条件：

1. `status in ('pending', 'retrying')`
2. `next_retry_at is null` 或 `next_retry_at <= now`

适用场景：

1. startup reconciliation 扫描
2. 需要“现在就处理哪些任务”的执行流

### `list_blocking()`

表示：**当前仍应阻止新开仓的 recovery tasks**

条件：

1. `status in ('pending', 'retrying')`
2. 不关心 `next_retry_at` 是否到期

适用场景：

1. circuit breaker 重建
2. runtime health
3. “当前是否仍应阻止新开仓”的只读面

### 当前规则

1. startup reconciliation 用 `list_active()`
2. breaker rebuild / health / execution guard 用 `list_blocking()`

---

## 2. profile switch 的当前规则

### 已确认

1. profile switch 需要 `confirm=true`
2. profile switch 更新的是配置域中的 active profile

### 当前应如何理解

对当前运行中的 execution runtime：

1. runtime execution 配置由启动期的：
   - `ResolvedRuntimeConfig`
   - `RuntimeConfigProvider`
   冻结
2. 因此 profile switch 默认应理解为：
   - **对后续启动生效**
   - 或 **对显式 reload 流程生效**
3. 不应被理解为：
   - 静默热切当前 execution 主链

### 当前规则结论

> profile switch = 配置域 active profile 变更  
> runtime freeze = 当前 execution 主链不应被静默热切

---

## 3. 为什么要现在澄清

因为当前窗口已经从“主链补丁”进入“边界治理”阶段。

如果这两个语义不钉死，后面很容易再次出现：

1. 把 `list_active()` 错当成 breaker truth source
2. 把 profile switch 错当成当前 runtime 的热切入口

这两种误读都会让 execution PG 主线重新变得不可信。
