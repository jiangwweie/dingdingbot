---
title: Binance Review Attribution and Owner Terminal Correctness Test Cases
status: CERTIFIED_LOCAL
authority: IMPLEMENTATION_DELTA
date: 2026-07-30
revision: 2
design: 2026-07-30-binance-review-owner-terminal-correctness-design.md
---

# Binance Review 归因与 Owner 终态一致性测试规格

## 1. 测试目标

本规格要求问题优先暴露在本地，并证明修复关闭的是问题类别，而不是一个生产
payload 特例。

| 层级 | 核心证明 | 主要替身 |
| --- | --- | --- |
| Unit | Binance 协议模型、身份矩阵、Reducer revision 不变量 | production-shaped typed/raw fixture |
| PostgreSQL Integration | Review revision、Aggregate pointer、Owner 投影原子性 | disposable PostgreSQL |
| Adapter/Worker | exact Algo identity 能产生完整 Review | recording Binance client |
| Full-chain | terminal Review 与 canonical Owner completed 同链形成 | 四 Worker 等价调用链 |
| Architecture | readonly 无写、单一 baseline、无兼容路径 | source/schema scan |
| Deployment rehearsal | v4 空库重建、seed、fence、postflight | disposable PostgreSQL + recording ops |

## 2. RED-1：生产形状 Algo 响应

必须先增加以下 production-shaped fixture，并确认旧实现失败：

```json
{
  "algoId": "4000001795783472",
  "clientAlgoId": "brc-runner",
  "symbol": "BTCUSDT",
  "side": "SELL",
  "positionSide": "LONG",
  "orderType": "STOP_MARKET",
  "quantity": "0.0005",
  "algoStatus": "FINISHED",
  "actualOrderId": "1085699838084",
  "actualQty": "0.0005"
}
```

旧实现必须因错误读取 `type/status` 产生 RED。

## 3. Unit 测试矩阵

### 3.1 Algo parser 与 resolution

| Case | 输入差异 | 预期 |
| --- | --- | --- |
| Triggered | production-shaped 全字段 | `executable` + exact actual order id |
| Canceled untriggered | 无 `actualOrderId`、无 `actualQty` | `not_triggered` |
| Canceled explicit zero | `actualQty=0` | `not_triggered` |
| Working without actual id | `algoStatus=WORKING` | fail closed |
| Finished without actual id | `algoStatus=FINISHED` | fail closed |
| Triggered missing actualQty | actual id 非空、actualQty 缺失 | fail closed |
| Triggered wrong actualQty | 与 frozen quantity 不同 | fail closed |
| Wrong original quantity | `quantity` 与 frozen quantity 不同 | fail closed |
| Invalid quantity | 负数、NaN、Infinity、0 | fail closed |
| Identity contradiction | algo/client/symbol/side/positionSide/orderType 任一错误 | fail closed |
| Extra response fields | 增加无关官方字段 | 合法字段解析不受影响 |

所有异常消息只指出字段类别，不输出完整 raw response。

### 3.2 Review reducer

1. `REVIEW_PENDING + ReviewRecorded(v1)` 进入 `TERMINAL`。
2. `TERMINAL + ReviewRevised(v2, supersedes=v1)` 保持 `TERMINAL` 并更新
   `review_id`。
3. 非 terminal Aggregate 拒绝 `ReviewRevised`。
4. supersedes 不等于 current `review_id` 时拒绝。
5. 空 new/supersedes identity 拒绝。
6. 修订不产生 budget、capacity、lane、incident 或 exchange effect。

### 3.3 Owner key 与只读语义

1. `owner_ticket_monitor_key("ticket-1") == "owner:ticket:ticket-1"`。
2. 空 Ticket identity 拒绝。
3. Ticket request 使用非 canonical key 拒绝。
4. terminal projection 始终为 `completed`、`无需操作`。
5. readonly API 只调用 repository `get`，不调用 `save_if_changed`。
6. leverage rejection、ENTRY rejection 和 reconciled absence 同样通过 reducer
   effect 原子物化 canonical completed 投影。

## 4. PostgreSQL Integration

### 4.1 初次 Review 原子终态

在 disposable PostgreSQL 建立 `REVIEW_PENDING` Ticket，调用
`record_trade_review()` 后一次事务内断言：

1. `brc_trade_reviews` 有 revision 1；
2. `brc_trade_events` 有且仅有一个 `ReviewRecorded`；
3. Aggregate 为 `terminal` 且指向 v1；
4. Ticket 为 terminal；
5. `brc_monitor_current[owner:ticket:<id>]` 为 `completed`；
6. 对应 Monitor Event 只追加一次。

注入 Monitor 写失败，事务必须回滚 Review、Event、Aggregate 和 Ticket terminal。

### 4.2 Review revision

1. 追加 v2 后 v1 仍存在且内容不变；
2. v2 `supersedes_review_id=v1`；
3. Aggregate effective pointer 指向 v2；
4. `get_for_ticket()` 返回 v2；
5. 重复 `(ticket_id, revision)` 被数据库拒绝；
6. 同一 v1 竞争产生两个 v2 时最多一个提交成功；
7. v2 失败时 v1 仍是 current pointer；
8. Owner projection 保持 completed，不产生语义版本噪声。

### 4.3 Readonly 无副作用

读取 canonical Owner projection 前后断言：

1. `brc_monitor_current` 行内容和 `updated_at_ms` 不变；
2. `brc_monitor_events` count 不变；
3. 缺失 projection 返回 `None`，不自动创建行。

## 5. Adapter 与 Worker 契约

1. Query Algo Order 只使用 exact `algoId`。
2. Triggered 后只用 `actualOrderId` 查询 `userTrades`。
3. 未触发 terminal 返回零 fill 语义，不查询不存在的 actual order。
4. Trade row 不要求 `clientOrderId`。
5. symbol/orderId/side/positionSide/quantity 任一矛盾时 Review 不完成。
6. 真实 production-shaped exit payload 能生成完整 exit attribution、PnL、funding
   和 commission metrics。
7. Worker 写 Review 后 canonical Owner projection 同 cadence 已 completed。

## 6. Full-chain

构造一条 external-flat Ticket：

```text
EntryFilled
-> protected lifecycle
-> ExternalFlatDetected
-> cleanup/reconciliation
-> BudgetSettled
-> production-shaped Algo resolution
-> exact fills/economics
-> ReviewRecorded
-> terminal
-> owner:ticket:<id> completed
```

断言：

1. `economics_completeness=complete`；
2. 不进入 `external_exit_unavailable` fallback；
3. order attribution digest 稳定；
4. Review、Aggregate、Ticket、Owner projection 一致；
5. 第二个 cadence 不重复 Review/Event/Monitor Event；
6. 零 exchange mutation、零文件输出。

## 7. Schema 与部署测试

1. `migrations/trading_kernel/versions` 只有一个 v4 clean baseline。
2. 空 schema upgrade 到 head 成功。
3. metadata 与真实表 exact。
4. `brc_trade_reviews` 不再 `UNIQUE(ticket_id)`。
5. revision 与 supersedes constraints 生效。
6. downgrade fail closed。
7. runtime fence、seed、deploy/certify 默认 revision 全部使用 v4。
8. local clean rebuild 完整跑过 schema、seed、Universe、四 Worker smoke 和
   Entry fenced postflight。

## 8. 全量完成门

实现完成前必须执行并记录：

1. focused Unit；
2. focused PostgreSQL Integration；
3. Binance actual-order full-chain；
4. Ticket lifecycle/full-chain；
5. schema baseline 与 clean rebuild；
6. 全部 `tests/trading_kernel`；
7. Ruff；
8. Mypy；
9. architecture/static tests；
10. `git diff --check`。

任何失败、跳过的关键测试或未完成的 migration rehearsal 都使结论保持
**禁止部署**。
