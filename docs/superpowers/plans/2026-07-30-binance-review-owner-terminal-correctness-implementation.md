# Binance Review 归因与 Owner 终态一致性实施计划

> 执行必须遵循 `superpowers:test-driven-development` 和
> `superpowers:verification-before-completion`。每个生产行为先产生 RED，再做
> GREEN 和结构重构。

## 执行结果

本计划已完成本地实现和认证：production-shaped Binance 协议、append-only
Review revision、全 terminal reducer projection effect、readonly 无副作用和
v4 clean baseline 均已落地。最终部署结论仍必须以本分支的完整质量门、
action-time Tokyo readonly facts 和正式 deployment state machine 为准。

## 1. 目标

在不改变交易策略、容量和风险政策的前提下，完成：

1. production-shaped Binance Algo Order 严格适配；
2. append-only Review revision；
3. Review/terminal/Owner completed 原子提交；
4. readonly Owner API 去写副作用；
5. v4 clean baseline 与本地部署演练。

设计权威：
`docs/superpowers/specs/2026-07-30-binance-review-owner-terminal-correctness-design.md`

测试权威：
`docs/superpowers/specs/2026-07-30-binance-review-owner-terminal-correctness-test-cases.md`

## 2. 执行顺序

```text
T0 文档与基线冻结
-> T1 Algo production-shaped RED/GREEN
-> T2 Review revision domain RED/GREEN
-> T3 PostgreSQL schema/repository RED/GREEN
-> T4 Owner terminal transaction RED/GREEN
-> T5 Readonly API RED/GREEN
-> T6 Worker/full-chain regression
-> T7 v4 clean baseline mechanical identity rotation
-> T8 local rebuild + full verification
-> T9 review + commit + deployability decision
```

## 3. T0：基线与文档

### Files

- Create：本设计、测试规格、实施计划。
- No production changes。

### Done

1. 精确 base 为 `0dc5dcea`；
2. 隔离分支为 `codex/review-owner-terminal-repair-20260730`；
3. 主候选 dirty worktree 未被修改；
4. 现有 18 个定向测试 GREEN，但 production payload 可复现失败。

## 4. T1：Binance typed protocol adapter

### Files

- Modify：`src/trading_kernel/infrastructure/binance_order_attribution.py`
- Modify：`tests/trading_kernel/unit/test_binance_order_attribution.py`

### RED

1. 将现有 fixture 改为 `orderType/algoStatus/quantity`；
2. 增加 canceled/no-actualQty fixture；
3. 增加 original quantity 和所有身份冲突矩阵；
4. 旧实现必须失败。

### GREEN/REFACTOR

1. 新增 frozen `BinanceAlgoOrderSnapshot`；
2. raw mapping 只在 parser 边界出现；
3. typed snapshot 完成状态分类和 exact validation；
4. 删除 `_require_exact_algo_field` 等基于任意 raw key 的旧 helper；
5. 异常不包含 raw payload。

## 5. T2：Review revision domain

### Files

- Modify：`src/trading_kernel/domain/events.py`
- Modify：`src/trading_kernel/domain/reducer.py`
- Modify：`src/trading_kernel/application/ports.py`
- Modify：`src/trading_kernel/application/settle_ticket.py`
- Modify：`tests/trading_kernel/unit/test_reducer.py`

### RED

1. terminal Aggregate 尚不接受 `ReviewRevised`；
2. `TradeReviewRecord` 尚无 revision chain；
3. 尚无 `revise_trade_review()`。

### GREEN/REFACTOR

1. 新增 `ReviewRevised`；
2. 严格 current pointer/supersedes 校验；
3. 初次 Review 固定 revision 1；
4. 修订 revision 由 current review 精确递增；
5. Review 修订无资本、命令或 Incident effect。

## 6. T3：PostgreSQL revision persistence

### Files

- Modify：`src/trading_kernel/infrastructure/pg_models.py`
- Modify：`src/trading_kernel/infrastructure/pg_repositories.py`
- Modify：schema/integration tests。

### RED

1. 当前唯一 Ticket constraint 拒绝 v2；
2. repository 无 exact review get/latest；
3. schema 无 revision chain constraints。

### GREEN/REFACTOR

1. 实现 `(ticket_id, revision)` 唯一和 supersedes 约束；
2. `get(review_id)` exact；
3. `get_for_ticket()` 返回最新 revision；
4. 并发分叉由数据库 constraint/aggregate optimistic version 双重拒绝。

## 7. T4：Owner terminal transaction

### Files

- Modify：`src/trading_kernel/application/project_owner_state.py`
- Modify：`src/trading_kernel/application/settle_ticket.py`
- Modify：Owner/settlement/full-chain integration tests。

### RED

1. `record_trade_review()` 后 canonical Owner projection 缺失；
2. Monitor 写失败时当前代码可留下 terminal；
3. Ticket request 可使用任意 monitor key。

### GREEN/REFACTOR

1. 新增 `owner_ticket_monitor_key()`；
2. terminal projection 使用独立纯函数；
3. 初次和修订 Review 都在同一 UoW 物化 completed；
4. rollback test 证明原子性；
5. 不在基础设施层复制产品文案或状态推导。

## 8. T5：Readonly API

### Files

- Modify：`src/trading_kernel/interfaces/readonly_api.py`
- Modify/Create：readonly API tests。

### RED/GREEN

1. 先证明 read 会调用 `save_if_changed`；
2. 改为 canonical key exact get；
3. 缺失返回 `None`；
4. 删除 readonly -> command 的依赖；
5. 前后 Monitor current/event 均不变化。

## 9. T6：Worker 与 full-chain

### Files

- Modify：`tests/trading_kernel/full_chain/test_binance_actual_order_review.py`
- Modify：相关 Worker/Review integration tests。

### Done

1. production-shaped Algo response 形成 complete Review；
2. 不触发 external-exit-unavailable fallback；
3. 同 cadence Owner completed；
4. retry/idempotency 无重复 Review/Event/Monitor Event；
5. 所有 contradiction fail closed。

## 10. T7：v4 clean baseline identity

### Files

- Rename/Modify：唯一 Alembic baseline 为
  `0001_trading_kernel_baseline_v4`。
- Mechanical update：runtime seed、cutover、verify、scripts、tests、current
  stable schema references。

### Rules

1. 只做精确 v3 -> v4 identity rotation；
2. 不创建 `0002`、兼容 reader、dual write 或 upgrade fallback；
3. empty-schema upgrade 是唯一支持路径；
4. production deployment 必须 clean rebuild。

## 11. T8：验证顺序

1. focused Unit；
2. focused Integration；
3. full-chain Review/Ticket lifecycle；
4. schema baseline、metadata exact、clean rebuild；
5. 全部 `tests/trading_kernel`；
6. Ruff；
7. Mypy；
8. architecture/static；
9. `git diff --check`；
10. 本地 deploy rehearsal。

任何失败都回到对应 Task，不允许用 skip、放松断言或生产试错换取通过。

## 12. 部署计划

只有 T8 全部通过后才重新读取 action-time facts。部署步骤：

1. 停止并 fence Entry；
2. readonly 确认账户 flat、零 open order、零 unresolved command、零 open
   Incident；
3. 停 Observation/Lifecycle/Reconciliation；
4. 通过正式 deployment state machine 发布 exact commit；
5. clean rebuild v4 PostgreSQL；
6. seed Registry/Policy/Runtime identity，恢复 approved Universe；
7. 启动 Observation/Lifecycle/Reconciliation，Entry 保持 fenced；
8. readonly certification 和 postflight；
9. exact Promotion 后启动 Entry；
10. 更新 `MAIN_CONTROL_ROADMAP.md` 的 volatile production facts。

本计划不授权凭证修改、资金划转、提款、扩大交易范围或绕过 Kernel 的交易所
写入。
