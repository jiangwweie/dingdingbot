# Findings Log

> Last updated: 2026-04-23 16:22
> Archive backup: `docs/planning/archive/2026-04-23-planning-backup/findings.full.md`

---

## 当前有效结论

### 1. 执行恢复状态应优先进入 PG 主线

- `ExecutionIntent` 已是 PG 主真源
- `execution_recovery_tasks` 已作为 PG 正式恢复真源接入主链
- SQLite `pending_recovery` 仅保留过渡兼容

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

---

## 当前阶段最重要的判断

**现在不该继续横向扩张，而应进入“第二阶段范围冻结”。**

也就是：

1. 先明确第二阶段只做什么
2. 再从其中选一个入口任务推进
3. 其他事情只保留在 backlog，不进入执行态

---

## 第二阶段候选议题

1. `circuit_breaker` 是否 PG 真源化
2. SQLite `pending_recovery` 的退役路径
3. recovery task 的 retry/backoff / 运维操作面

### 当前收敛结论

第二阶段不再并行展开多条线，而是采用“分层处理全局问题”的方式推进：

1. 全局上看到后续还有 PG、运维、回测等多条线
2. 当前层只允许锁定一个主线入口
3. 当前入口已收敛为：`circuit_breaker` 是否 PG 真源化

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

---

## 历史说明

旧版详细 findings、研究链历史结论、回测参数长链路、PG 迁移早期推理已备份到：

- `docs/planning/archive/2026-04-23-planning-backup/findings.full.md`

主文档今后只保留仍然影响当前阶段决策的结论。 
