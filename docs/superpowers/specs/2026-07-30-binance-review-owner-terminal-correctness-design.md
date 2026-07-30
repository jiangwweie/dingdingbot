---
title: Binance Review Attribution and Owner Terminal Correctness Design
status: IMPLEMENTATION_AUTHORIZED
authority: IMPLEMENTATION_DELTA
date: 2026-07-30
revision: 1
---

# Binance Review 归因与 Owner 终态一致性修复设计

## 1. 设计结论

本次修复关闭同一条终态链上的三个结构性缺口：

1. **Binance Algo Order 协议适配错误**：生产响应字段为 `orderType`、
   `algoStatus`、`quantity`，未触发终态允许没有 `actualQty`；当前代码却读取
   `type`、`status` 并无条件要求 `actualQty`。
2. **Owner Ticket 投影没有事务内物化**：`ReviewRecorded` 可以把 Aggregate
   推进为 `TERMINAL`，但正常 Worker 链不会同步写入 `completed` 投影。
3. **Review 不可修订**：当前 `ticket_id` 唯一约束把一次暂缺或错误归因永久
   固化，无法在保留旧事实的同时追加正确经济结果。

修复后的权威链为：

```text
Binance raw response
-> frozen BinanceAlgoOrderSnapshot
-> exact frozen-command identity validation
-> ResolvedOrderIdentity
-> exact trade.orderId attribution
-> append-only TradeReview revision
-> ReviewRecorded / ReviewRevised
-> Aggregate effective review pointer
-> canonical owner:ticket:<ticket_id> projection
```

这不是 Binance 字段别名补丁，也不是终态后单独补写一行 Monitor。协议、事实
修订、Aggregate 指针和 Owner 投影必须分别落在清晰边界内。

## 2. 权威与范围

### 2.1 已知客观事实

1. 实现基线为 `codex/strategy-universe-operability-repair-20260729` 的精确提交
   `0dc5dcead40db4b9c6b35342475e4c0a12ce2083`。
2. 生产脱敏 Algo 响应使用 `orderType`、`algoStatus`、`quantity`；触发后可能
   包含 `actualOrderId` 和 `actualQty`，未触发取消时可能没有 `actualQty`。
3. 当前 `derive_owner_projection()` 已能把 `AggregateStatus.TERMINAL` 解释为
   `MonitorOwnerStatus.COMPLETED`，但只有显式调用投影命令时才会持久化。
4. 当前 `brc_trade_reviews` 对 `ticket_id` 有唯一约束，Aggregate 仅保存一个
   `review_id`。
5. 项目数据库合同是**单一 clean baseline、空库重建、forward-only**，不维护
   旧 schema 兼容链。

生产 Ticket、当前服务状态和部署 commit 属于
`docs/current/MAIN_CONTROL_ROADMAP.md` 的高波动事实，本设计不复制它们。

### 2.2 基于事实的设计判断

1. Algo 响应必须先由基础设施层建模，Application/Domain 不得读取 Binance
   原始字段。
2. 未触发终态缺少 `actualQty` 是合法协议分支，但只有在全部冻结身份和原始
   `quantity` 精确一致时才可归类为 `not_triggered`。
3. Review 的“当前有效版本”必须可变，Review 事实本身必须追加不可变；最小
   正确模型是**版本化 Review + Aggregate current pointer**。
4. Ticket 终态对 Owner 是确定性事实，不应依赖 policy/readiness 二次查询；
   因此必须在终态事务中直接物化 canonical Ticket 投影。
5. Schema 内容变化必须产生新的 schema identity；沿用 v3 revision 会破坏
   Runtime Fence 的可信度。

## 3. 目标与非目标

### 3.1 目标

1. 正确解析生产形状的 Binance USD-M Algo Order 响应。
2. 对 `algoId`、`clientAlgoId`、`symbol`、`side`、`positionSide`、
   `orderType`、`quantity` 做精确校验。
3. 对 triggered 与 terminal-not-triggered 分支 fail closed。
4. 允许 Review 以 append-only revision 修正，不覆盖旧事实。
5. 初次 Review、终态 Aggregate 和 Owner `completed` 投影原子提交。
6. Owner Ticket 投影使用唯一 canonical key；只读接口只读。
7. 用 production-shaped fixture、Disposable PostgreSQL 和 full-chain 测试在
   本地暴露问题。

### 3.2 非目标

1. 不改变策略、动态标的、容量、杠杆、止损或保证金政策。
2. 不新增 Worker、timer、并行 Review 账本或兼容 reader。
3. 不自动扫描所有 terminal Ticket 重算历史 Review。
4. 不通过 direct DML 覆盖生产 Review、Aggregate 或 Monitor。
5. 不在本次实现中连接 Tokyo、写交易所或执行部署。

## 4. Binance 协议适配设计

### 4.1 冻结协议模型

`src/trading_kernel/infrastructure/binance_order_attribution.py` 定义：

```python
class BinanceAlgoOrderSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="ignore")

    algo_id: str = Field(alias="algoId")
    client_algo_id: str = Field(alias="clientAlgoId")
    symbol: str
    side: str
    position_side: str = Field(alias="positionSide")
    order_type: str = Field(alias="orderType")
    quantity: Decimal
    algo_status: str = Field(alias="algoStatus")
    actual_order_id: str | None = Field(alias="actualOrderId", default=None)
    actual_quantity: Decimal | None = Field(alias="actualQty", default=None)
```

`extra="ignore"` 只用于外部协议扩展容忍；模型内所有被消费字段仍是 frozen、
typed，并由显式 validator 规范化。解析失败统一转换为基础设施异常，不把
Pydantic 或 raw payload 泄露到上层。

### 4.2 精确身份校验

所有状态分支都必须先校验：

| 字段 | 校验规则 | 失败结果 |
| --- | --- | --- |
| `algoId` | 等于 durable submitted exchange id | fail closed |
| `clientAlgoId` | 等于 frozen venue client id | fail closed |
| `symbol` | 等于 canonical instrument symbol | fail closed |
| `side` | 等于 frozen command side | fail closed |
| `positionSide` | 等于 frozen position side | fail closed |
| `orderType` | 等于 frozen conditional order type | fail closed |
| `quantity` | finite、正数、等于 frozen quantity | fail closed |

### 4.3 状态分支

| 状态形状 | 合法结果 | 附加约束 |
| --- | --- | --- |
| `actualOrderId` 非空 | `executable` | `actualQty` 必须存在、finite、正数并等于 frozen quantity |
| `actualOrderId` 为空，`algoStatus` 为 `CANCELED/EXPIRED/REJECTED` | `not_triggered` | `actualQty` 可缺失；如存在必须为 0 |
| `actualOrderId` 为空，其他状态 | 无结果 | fail closed，不能猜测订单身份 |

`ResolvedOrderIdentity` 仍是 Domain 可见的唯一结果。Domain 不新增 Binance
字段、状态或客户端依赖。

## 5. Review 版本化设计

### 5.1 数据模型

`TradeReviewRecord` 增加：

```text
revision: positive integer
supersedes_review_id: nullable review identity
```

不变量：

1. revision 1 必须没有 `supersedes_review_id`；
2. revision > 1 必须有 `supersedes_review_id`；
3. `(ticket_id, revision)` 唯一；
4. 每个 Review 最多被一个下一版本 supersede；
5. superseded Review 永不更新或删除；
6. Aggregate `review_id` 指向当前有效 Review。

### 5.2 事件语义

保留初次闭环事件：

```text
REVIEW_PENDING + ReviewRecorded(v1) -> TERMINAL
```

新增修订事件：

```text
TERMINAL + ReviewRevised(vN, supersedes=vN-1) -> TERMINAL
```

Reducer 必须要求 `supersedes_review_id == current.aggregate.review_id`。修订只
更新 Aggregate current pointer 和 event/version，不重新占用预算、Netting
Domain 或 Entry lane。

### 5.3 Application 服务

`record_trade_review()` 只创建 revision 1。`revise_trade_review()` 只接受
terminal Aggregate，并在同一 UoW 中：

1. 锁定/读取 current Aggregate；
2. 读取被 supersede 的 exact Review；
3. 追加下一 revision；
4. 追加 `ReviewRevised`；
5. 更新 Aggregate effective pointer；
6. 保持 canonical Owner projection 为 `completed`。

本次不增加自动历史扫描。需要修正历史事实时，必须由 exact Ticket 的正式
应用调用提供重新计算后的 typed Review 内容。

## 6. Owner Ticket 投影设计

### 6.1 Canonical key

唯一 Ticket Owner 投影键为：

```text
owner:ticket:<ticket_id>
```

任何携带 `ticket_id` 的 `OwnerProjectionRequest` 都必须使用该 key。策略、账户、
认证和费用 Monitor 保持各自 namespace，不得冒充 Ticket 主状态。

### 6.2 事务一致性

初次 `record_trade_review()` 的一个 PostgreSQL UoW 必须原子包含：

```text
insert TradeReview v1
append ReviewRecorded
update Aggregate -> TERMINAL, review_id=v1
mark Ticket terminal
upsert owner:ticket:<ticket_id> -> completed
```

任一步失败，整个事务回滚。禁止 Worker 先提交 terminal，随后依赖另一个
cadence 或只读请求补投影。

### 6.3 只读边界

`interfaces/readonly_api.get_owner_projection()` 只按 canonical key 读取
`brc_monitor_current`，不调用投影命令、不更新时间、不追加 Monitor Event。

`project_owner_state()` 仍是显式写模型命令，用于非终态 policy/readiness
投影；它不再由 readonly API 隐式触发。

## 7. PostgreSQL 与 schema identity

`brc_trade_reviews` 从“每 Ticket 一行”改为“每 Ticket 多 revision”：

1. 删除 `UNIQUE(ticket_id)`；
2. 新增 `revision BIGINT NOT NULL CHECK (revision > 0)`；
3. 新增 nullable `supersedes_review_id`；
4. 新增 `UNIQUE(ticket_id, revision)`；
5. 新增 `UNIQUE(supersedes_review_id)`；
6. 新增 revision/supersedes 一致性约束。

项目仍保持一个 Alembic clean baseline。新 metadata 必须使用新的 v4 schema
identity，从空 schema 重建；不添加旧 v3 reader、dual write 或 in-place
fallback。

## 8. 失败语义

| 失败 | 行为 | 禁止行为 |
| --- | --- | --- |
| Algo payload 缺字段/类型错误 | Review facts unavailable，按现有有界重试 | 猜测 actual order id |
| 任一 frozen identity 冲突 | fail closed | 只校验 algo/client id |
| 未触发终态缺 `actualQty` | 合法 `not_triggered` | 强制伪造 0 字段 |
| triggered 缺 `actualQty` | fail closed | 用原始 `quantity` 冒充 actual quantity |
| Review revision 链冲突 | UoW rollback | 覆盖旧 Review |
| Owner 投影写失败 | Review/terminal 同事务 rollback | 留下 terminal + processing 分裂态 |
| readonly projection 缺失 | 返回 `None` | 在读请求中写数据库 |

## 9. 部署含义

本设计完成并通过全部本地 gate 后，代码层才可判定为 deployment candidate。
由于 schema identity 变化，部署方式是：

```text
Entry fenced/stopped
-> readonly 确认账户 flat、零 open order、零 unresolved command
-> 停四 Worker
-> clean rebuild v4 schema
-> seed/runtime identity/universe restore
-> 启动 Observation/Lifecycle/Reconciliation，Entry 保持 fenced
-> readonly postflight
-> 明确 Promotion 后启 Entry
```

如果 action-time 发现持仓、订单或 unresolved command，不执行 clean rebuild。

