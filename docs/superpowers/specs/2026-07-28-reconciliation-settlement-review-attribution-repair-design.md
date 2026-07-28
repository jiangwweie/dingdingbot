---
title: Reconciliation Settlement Fairness and Binance Order Attribution Repair Design
status: IMPLEMENTATION_AUTHORIZED_LOCAL_ONLY
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-28
revision: 2
---

# Reconciliation Settlement Fairness and Binance Order Attribution Repair Design

## 决策门

本文档描述 **Reconciliation 调度公平性、Binance 订单成交归因和未终态
Ticket 闭环接管** 的完整修复设计。

Owner 已授权从 RED 测试开始修改本地生产代码、测试代码和 disposable
PostgreSQL 验收。该授权不包含 Tokyo PostgreSQL、Tokyo systemd 服务、真实
交易所状态或 BNB 转入；closure-only 发布仍需独立 Owner 确认与 action-time
认证。

当前代码、当前 PostgreSQL 与交易所只读事实、`docs/current/*` 仍是运行
权威。本文档记录的 Tokyo 状态来自 Owner 在 **2026-07-28** 提供的现场
观察，本轮没有重新连接 Tokyo 复核；生产动作前必须重新读取 action-time
事实。

## 核心结论

本次不是两个局部 `if` 修补，而是收口为四个有明确边界的能力：

1. **Fair Reconciliation Scheduler**：活跃仓位仍优先获得安全对账，但
   `SETTLEMENT_PENDING` 和 `REVIEW_PENDING` 在有其他活跃 Ticket 时也有
   有界进展。
2. **Exact Order Attribution**：统一建立
   `durable command -> submitted order/algo -> actualOrderId -> trade.orderId`
   的精确身份链，禁止再依赖 `trade.clientOrderId`。
3. **Closure-only Handover**：允许一个已平仓、已释放资金和
   Netting Domain、但仍处于 Settlement/Review 的精确 Ticket 跨版本继续
   闭环；该模式强制 Entry fenced，不能成为普通部署绕过口。
4. **Exit/Fee Semantics**：初始止损与 runner 继续使用
   **STOP_MARKET**，TP1 明确升级为 **LIMIT + GTX Maker-only**；实际手续费
   同时支持 `USDT` 和 `BNB`，统一换算成带证据的 USDT 价值。

修复后的目标链如下：

```text
durable Exchange Command
-> persisted accepted exchange identity
-> regular orderId
   or conditional algoId/clientAlgoId -> actualOrderId
-> exact userTrades(orderId)
-> immutable Review attribution evidence
-> ReviewRecorded
-> terminal Ticket
```

**BTC 的真实收益不重算、不手填、不以 DML 伪造终态。** 目标版本必须读取
既有 Command、Event 和 Binance 只读事实，通过正常
`BudgetSettled -> ReviewRecorded` 事件链形成完整 Review。

## 范围

### 本次包含

1. 多活跃 Ticket 下 Settlement/Review 的有界公平调度。
2. Binance 普通订单和条件订单的精确成交归因。
3. Lifecycle 入场手续费、未知命令恢复、终态 Review 三个消费者统一迁移。
4. 条件订单 `algoId/clientAlgoId -> actualOrderId` 的严格解析。
5. 交易成交按 `trade.orderId` 精确归属，按 `tradeId` 去重。
6. BTC pending closure 的正常事件回放与完整 Review 验收。
7. 无 schema 变化的 P1 修复版本 closure-only 部署门。
8. Entry 保持 inactive/disabled/fenced，后续正式发布才显式
   `--enable-entry`。
9. BNB fee discount 的只读状态和余额观察。
10. `commissionAsset=BNB` 的 native fee 保存与 USDT 估值。
11. TP1 Maker-only 的命令语义、Adapter 映射和拒绝路径。

### 本次不包含

1. StrategyUniverse schema、生产标的播种或加密标的切换。
2. 美股合约数据、策略或交易执行。
3. 相关性、聚类、拒绝或动态降仓。
4. 交易所杠杆、保证金模式或 position mode 自动写入。
5. 历史 Ticket 批量修复、手工成交导入或通用账本重建平台。
6. Web 控制台、推送平台或第五个 Worker。
7. 已经 terminal 且 Review 不完整的就地覆盖。
8. 自动购买 BNB、自动划转 BNB、自动开启 fee burn。
9. 把 BNB 计入保证金、Owner capital、Capacity 或风险预算。
10. 依赖 BNB 折扣降低未来 STOP_MARKET 的风险/成本预算。

## 已知客观事实

### Owner 提供的当前运行事实

1. **BTC 的交易所闭环已成功**，真实盈利未受影响。
2. BTC 内部当前停在 `settlement_pending`。
3. SOL、AVAX 等剩余仓位仍由现有保护和 runner 管理。
4. Entry 当前是：

```text
ActiveState = inactive
UnitFileState = disabled
Owner Policy new_entry_submit_enabled = true
```

5. 全部平仓不会自动启动 Entry；下一次允许交易的正式发布必须显式使用
   `--enable-entry`。

这些是 Owner 提供的现场事实，不在本文档中冒充本轮实时认证结果。

### 本地代码确认的调度事实

`run_reconciliation_worker_once()` 当前先选择
`_POSITION_RECONCILIATION_STATUSES`。只要选到一个活跃 Aggregate，完成一次
position reconciliation 后就在同一轮立即返回。Settlement 和 Review
选择器位于该返回之后。
（来源：[`reconciliation_worker.py`](../../../src/trading_kernel/interfaces/reconciliation_worker.py)）

PostgreSQL repository 的每次 `get_next_for_statuses()` 都只在调用方给出的
status 集合中选最早一条。Repository 本身不知道 position、settlement 和
review 之间的公平性目标。
（来源：[`pg_repositories.py`](../../../src/trading_kernel/infrastructure/pg_repositories.py)）

现有 fairness 测试只证明 pending unknown command 不会永久阻塞 position
reconciliation，没有覆盖活跃 position 与 Settlement/Review 之间的竞争。
（来源：[`test_reconciliation_worker_fairness.py`](../../../tests/trading_kernel/unit/test_reconciliation_worker_fairness.py)）

### 本地代码确认的资金释放事实

`ReconciliationMatched` 在 Aggregate 进入 `SETTLEMENT_PENDING` 时已经产生：

- 关闭 Ticket Incident；
- 释放 budget/capital authority；
- 释放 account capacity；
- 释放 Netting Domain。

`BudgetSettled` 只把 Aggregate 推进到 `REVIEW_PENDING`；
`ReviewRecorded` 才把 Aggregate 推进到 `TERMINAL`。
（来源：[`reducer.py`](../../../src/trading_kernel/domain/reducer.py)）

因此当前问题会延迟实验账本终态，但不会重新占用已经释放的资金或
Netting Domain。

### 本地代码确认的成交归因事实

当前 `read_review_economics()`：

1. 按每个 `venue_client_order_id` 调用 `fetch_my_trades()`；
2. 再要求返回的每条 trade 也包含相同 `clientOrderId`；
3. 缺少该字段的真实 trade 被直接丢弃。

相同假设还出现在：

- Lifecycle 入场手续费读取；
- unknown command 的 `matching_fill_quantity`；
- Review 的 entry/exit fill 分类。

（来源：[`venue_adapter.py`](../../../src/trading_kernel/infrastructure/venue_adapter.py)）

当前测试 fake 会主动把 `clientOrderId` 填回 trade row，因此测试验证的是
fake 合同，不是 Binance 实际协议合同。

### 本地代码确认的订单与手续费事实

当前命令生成已经把：

- 初始止损生成为 `stop_market`；
- runner protection replacement 生成为 `stop_market`；
- TP1 生成为 `limit`。

但是当前 `OrderCommandPayload` 没有 time-in-force/maker-only 字段，Venue
Adapter 也没有为 TP1 发送 `GTX` 或等价 post-only 参数。因此当前 TP1
只能证明是 **LIMIT**，不能证明一定是 **Maker**。
（来源：[`pg_unit_of_work.py`](../../../src/trading_kernel/infrastructure/pg_unit_of_work.py)、
[`venue_adapter.py`](../../../src/trading_kernel/infrastructure/venue_adapter.py)）

当前 fee parser 要求 `fee.currency == settlement_asset`。生产所有 USD-M
合约的 settlement asset 固定映射为 `USDT`，因此一旦 Binance 使用 BNB
扣费，Lifecycle 和 Review 都会把真实成交判为 fee asset 不匹配。
（来源：[`production_runtime.py`](../../../src/trading_kernel/infrastructure/production_runtime.py)、
[`venue_adapter.py`](../../../src/trading_kernel/infrastructure/venue_adapter.py)）

### Binance 官方协议事实

Binance USD-M 的 **Account Trade List** 支持使用 `symbol + orderId` 精确
查询；响应包含 `id`、`orderId`、数量、价格、手续费、realized PnL、
position side 和时间，但不声明 `clientOrderId`。
（来源：[Binance USD-M Account Trade List](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade#account-trade-list)）

Binance USD-M 的 **Query Algo Order** 接受 `algoId` 或 `clientAlgoId`，
响应提供 `algoId`、`clientAlgoId` 和 `actualOrderId`；未触发时
`actualOrderId` 为空，触发后它是实际订单的 `orderId`。
（来源：[Binance USD-M Query Algo Order](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade#query-algo-order)）

Binance USD-M 的 **New Order** 把 `GTX` 列为 LIMIT order 可用的
`timeInForce`，并要求 LIMIT 同时提供 `timeInForce`、quantity 和 price。
（来源：[Binance USD-M New Order](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade#new-order)）

Binance USD-M 提供只读 `GET /fapi/v1/feeBurn`，响应中的 `feeBurn=true`
表示 BNB fee discount 已开启；对应的变更接口是一个独立的交易写请求。
本项目只允许调用前者。
（来源：[Binance USD-M Get BNB Burn Status](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account#get-bnb-burn-status)）

Binance 官方资料说明 BNB 可用于 Futures 交易手续费折扣，但具体折扣率会受
产品、账户等级和平台规则影响。因此程序不得硬编码一个“永远有效”的折扣
百分比，最终账本只采用每条真实 trade 返回的 `commission` 和
`commissionAsset`。
（来源：[Binance Academy: Transaction Fees](https://academy.binance.com/en/articles/how-to-calculate-transaction-fees-on-binance)）

Binance USD-M 还提供 `BNBUSDT` 的 **Index Price Kline**，支持 1 分钟
interval 和时间区间查询，可作为 BNB 手续费的可复算 USDT 估值源。
（来源：[Binance USD-M Index Price Kline](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#index-price-klinecandlestick-data)）

## 根因分析

### 问题一：Settlement/Review 调度饥饿

| 维度 | 预期语义 | 当前行为 | 直接根因 | 结果 |
| --- | --- | --- | --- | --- |
| Position | 按固定 cadence 持续对账 | 每轮优先处理一条 | position selector 位于最前 | 本身正确 |
| Settlement | 平仓释放后有界推进 | 只有本轮无 position 才处理 | position 分支提前 `return` | 可无限等待 |
| Review | Settlement 后有界归因 | 只有无 position、无 settlement 才处理 | 串行优先级且无 aging | 可无限等待 |
| 测试 | 证明多 Ticket 公平性 | 主要覆盖单 Ticket | 缺少竞争矩阵 | 回归未被发现 |

完整因果链为：

```text
每个活跃 Ticket 周期性到期
-> position selector 每轮总能选中一个 Aggregate
-> position reconciliation 后立即 return
-> settlement/review selector 不可达
-> pending closure 等到所有 position 都不再到期
```

这不是 PostgreSQL 锁、Reducer 或资金释放错误，而是
**Reconciliation Worker 的跨 work-kind 调度策略错误**。

### 问题二：Review 使用了错误的身份字段

| 维度 | 正确事实 | 当前假设 | 直接根因 | 结果 |
| --- | --- | --- | --- | --- |
| Trade 身份 | `tradeId + orderId` | trade 必须有 `clientOrderId` | 把下单身份误当成交字段 | 真实 fill 被丢弃 |
| 普通订单 | accepted `orderId` 可直接匹配 | 只保留 client id 作为查询语义 | Application request 身份不足 | 无法精确归因 |
| 条件订单 | `algoId -> actualOrderId` | algo/client id 直接匹配 trade | 未建 namespace 转换 | runner fill 丢失 |
| 测试 fake | 应复现 Binance 字段 | 人工返回 `clientOrderId` | fixture 偏离协议 | false green |

完整因果链为：

```text
durable command 有 client order identity
-> conditional acceptance 返回 algo identity
-> Binance 触发后创建 actual order
-> userTrades 只返回 actual orderId
-> 当前代码仍过滤 clientOrderId
-> entry_fills/exit_fills 为空
-> ReviewEconomicsUnavailable 或不完整 Review
```

### 同类问题回扫

本轮按字段假设而不是按函数名回扫后，确认三个消费者共享同一缺陷：

| 消费者 | 当前用途 | 缺陷影响 | 本次处理 |
| --- | --- | --- | --- |
| Lifecycle | 分配 entry fee | 费用可能被算成 0 | 迁移到 exact orderId |
| Unknown recovery | 判断 matching fill | 消歧事实可能错误为 0 | 迁移到统一 resolver |
| Review | 终态收益归因 | entry/exit fills 可能为空 | 迁移到统一 resolver |

只修 Review 会保留两个相同的不合规口子，因此不采用。

### 问题三：手续费模型错误地等同于 settlement asset

| 维度 | 正确语义 | 当前行为 | 直接根因 | 结果 |
| --- | --- | --- | --- | --- |
| Native fee | 保存真实 amount + asset | 只接受 USDT | fee model 只有 `fee_quote` | BNB fee 被拒绝 |
| USDT 价值 | 明确估值方法和价格证据 | 直接把 native amount 当 USDT | 无 conversion model | 无法审计 |
| Discount | 读取 account 状态与真实 commission | 依赖固定费率配置 | 执行预算与实收费用混在一起 | 折扣不可证明 |
| Capital | BNB 只是 fee asset | 无显式边界 | 余额模型没有 fee/capital 分类 | 未来可能误计权益 |

完整因果链为：

```text
Owner 手工转入 BNB + feeBurn enabled
-> Binance trade commissionAsset 可能变为 BNB
-> 当前 parser 要求 commissionAsset == USDT
-> Lifecycle fee facts / Review facts unavailable
-> runner floor 延迟或 Review 无法完成
```

因此 BNB 支持必须在启用 BNB 扣费前随 exact order attribution 一起落地，
不能先转入 BNB、后补记账。

### 历史形成原因

1. **`e3e8961a`** 拆分四 Worker 时形成了 position-first 的顺序执行结构。
2. **`d2784a30`** 增加 Review economics 时把 client order identity 直接
   延伸成 trade 过滤字段。
3. **`4fd6f808`** 修复了 pending unknown 对 position 的饥饿，但测试范围
   没有继续覆盖 position 对 closure 的反向饥饿。
4. **`d50bad0f`** 增加外部平仓 Review fallback，但没有改变 Binance
   order-to-trade 身份解析。

这些提交分别解决了当时的局部目标；本次修复补齐跨 Ticket 和真实 Binance
协议矩阵，不恢复旧实现，也不增加兼容分支。

## 目标职责与模块边界

### 职责划分

| 模块 | 唯一职责 | 允许依赖 | 明确禁止 |
| --- | --- | --- | --- |
| `domain/order_attribution.py` | 订单引用、解析结果、fill 与 evidence 不变量 | Pydantic、Decimal | SQLAlchemy、CCXT、网络 |
| `domain/fee_valuation.py` | native fee、USDT 估值和证据不变量 | Pydantic、Decimal | Venue client、系统时钟 |
| Reconciliation selector | 在现有 Worker 中选择一个有界工作项 | Aggregate status/due time | 交易所字段解析 |
| PostgreSQL repository | 精确读取 command/result 与公平选择候选 | SQLAlchemy、typed models | 决定 Binance 协议语义 |
| `binance_order_attribution.py` | Binance namespace 解析和 trade parsing | CCXT port、官方字段 | Ticket 状态迁移、DB |
| `binance_fee_valuation.py` | BNBUSDT index price 读取与估值 | Binance readonly market API | 余额划转、折扣开关 |
| Lifecycle/Unknown/Review application | 选择用途、校验 Ticket 因果关系 | typed resolver port | 自己解析原始 dict |
| Deployment script | 精确认证并接管 closure Ticket | readonly certification | 修改 Ticket 终态、启用 Entry |

### 不建设通用事件总线

公平调度仍属于现有 **Reconciliation Worker**。本次不增加第五个服务、不引入
队列平台、不拆出 Settlement daemon，也不让 Review 绕过 Ticket Aggregate。

### 不在 `venue_adapter.py` 继续堆 helper

Binance 订单身份解析是一个有业务不变量、被三个消费者复用的协议组件，不是
简单字段映射。实现应放入独立的
`src/trading_kernel/infrastructure/binance_order_attribution.py`，生产 Venue
Adapter 通过明确 port 委托它。这样能缩小现有大文件，并避免三处复制
`actualOrderId` 判断。

## 设计一：Fair Reconciliation Scheduler

### Work item

```python
class ReconciliationWorkKind(StrEnum):
    POSITION = "position"
    SETTLEMENT = "settlement"
    REVIEW = "review"


class ReconciliationWorkItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    kind: ReconciliationWorkKind
    status: AggregateStatus
    due_at_ms: int
    status_entered_at_ms: int
```

Selector 每轮最多返回一个 Aggregate work item。网络 I/O 仍在 PostgreSQL
事务外，Reducer/UoW 的现有乐观并发约束保持不变。

### 公平规则

建议固定以下运行语义：

1. unknown command recovery 仍先执行。
2. unknown 已得到 terminal decision 时，本轮返回，不混合第二个状态写入。
3. unknown 仍处于 visibility pending/lookup failed 时，继续公平选择普通工作。
4. closure work 只有在自身 due time 到达后才有资格。
5. 若最老的 due closure 已等待至少 **30,000 ms**，选择最老 closure。
6. 否则选择最早到期的 position reconciliation。
7. 若无 due position，选择最老的 due closure。
8. 无工作时才返回 pending unknown result 或 `NO_WORK`。

其中 closure 定义为：

```text
SETTLEMENT_PENDING
or REVIEW_PENDING
```

`status_entered_at_ms` 使用 Aggregate 进入当前状态时写入的
`updated_at_ms`；`schedule_next_check()` 不改写它。`due_at_ms` 使用
`coalesce(reconciliation_due_at_ms, updated_at_ms)`。

### 时间边界

在不存在 unresolved terminal unknown、Worker 持续健康且单次调用不超时的
前提下：

- closure 被选中的等待目标不超过
  **30 秒 + 1 个 Worker poll interval**；
- 当前默认 poll 为 5 秒时，目标选择延迟为 **不超过 35 秒**；
- 该边界是调度选择 SLO，不把 Binance 网络响应时间伪装成硬实时保证。

### 失败重试

1. position facts 失败：按现有 idle poll 重试。
2. settlement DB transaction 失败：事务回滚，由下一 cadence 重试。
3. Review facts 失败：使用独立 **30 秒 closure retry interval**，不在每个
   5 秒 poll 反复占用网络。
4. 失败重试不改变 `status_entered_at_ms`；到达 retry due 后仍按 aging
   获得机会。
5. 任何一条反复失败的 Review 不得让 due position 连续失去所有 cadence。

### 方案比较

| 方案 | 公平性 | 单轮网络上界 | 服务复杂度 | 持久状态 | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| 保持 position-first | 无 | 1 | 低 | 无 | 拒绝 |
| 每轮 position 后再 closure | 有 | 2 | 低 | 无 | 拒绝，放大安全 cadence |
| 新增 Settlement/Review Worker | 有 | 1/Worker | 高 | 新 service ownership | 拒绝 |
| age-aware 单 selector | 有界 | 1 | 中且有界 | 复用 due/update time | 采用 |

### 查询与性能

Repository 新增一个
`get_next_reconciliation_work(now_ms, closure_starvation_limit_ms)` typed
方法；Lifecycle 的 selector 不受影响。

SQL 必须：

- 只读取 active Aggregate status；
- 使用 status/due 索引；
- `ORDER BY` 使用明确 CASE，不依赖物理行顺序；
- `LIMIT 1`；
- 保留 `FOR UPDATE SKIP LOCKED`；
- PostgreSQL integration 中用 `EXPLAIN` 证明不做完整历史扫描。

本次不新增 scheduler 表、lease 表或全局计数器。

## 设计二：Exact Order Attribution

### 领域模型

```python
class OrderNamespace(StrEnum):
    REGULAR = "regular"
    CONDITIONAL = "conditional"


class OrderRole(StrEnum):
    ENTRY = "entry"
    EXIT = "exit"


class TicketOrderReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    command_kind: ExchangeCommandKind
    role: OrderRole
    namespace: OrderNamespace
    venue_client_order_id: str
    submitted_exchange_order_id: str


class ResolvedOrderIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: TicketOrderReference
    resolution_status: Literal["executable", "not_triggered"]
    actual_order_id: str | None
    resolved_at_ms: int


class AttributedTradeFill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_trade_id: str
    exchange_order_id: str
    command_id: str
    role: OrderRole
    quantity: Decimal
    price: Decimal
    fee: ValuedFee
    realized_pnl_quote: Decimal
    occurred_at_ms: int
```

`AttributedTradeFill` 不再包含由 trade row 提供的 client order identity。
client identity 只存在于 Command 到 Order 的桥接证据中。

### PostgreSQL 命令事实

`brc_exchange_commands.result_payload` 已保存 accepted
`ExchangeCommandResult`，其中顶层 `exchange_order_id` 可作为：

- 普通订单的 `orderId`；
- 条件订单的 `algoId`。

新增 repository 方法必须直接从 exact Ticket 的 accepted/
reconciled-accepted command rows 构建 `TicketOrderReference`。不得把
`result_payload` 的任意 dict 暴露给 domain/application。

Namespace 由 command payload 的 `order_type` 严格决定：

- `market`、`limit` -> `regular`；
- `stop_market`、`take_profit_market` -> `conditional`。

Cancel 和 SetLeverage command 不进入成交归因集合。

### 普通订单解析

1. `submitted_exchange_order_id` 就是 `actual_order_id`。
2. 必须是非空 Binance order id。
3. 读取 trade 时使用 `symbol + orderId`。
4. 返回 trade 的每个 `orderId` 必须与请求完全相同。

### 条件订单解析

1. 使用已持久化 `algoId` 查询 conditional namespace。
2. 同时校验 `clientAlgoId == venue_client_order_id`。
3. 校验 symbol、side、positionSide、order type 与 Ticket/Command 一致。
4. 若 terminal `CANCELED/EXPIRED` 且 `actualOrderId` 为空，
   `resolution_status=not_triggered`，该命令贡献零 fill。
5. 若已触发或已成交，`actualOrderId` 必须是非空的实际 `orderId`。
6. 状态、`actualQty` 和 `actualOrderId` 互相矛盾时 fail closed。
7. 不允许把 `algoId` 当作 `trade.orderId`，也不允许用字符串模糊匹配。

BTC 已知 runner 示例应按以下方式进入测试 fixture，而不是写进生产分支：

```text
algoId        = 4000001795783472
clientAlgoId  = brc-e4196bb182b923bc00907be6d93d
actualOrderId = 1085699838084
actualPrice   = 63363.6
actualQty     = 0.005
```

### Trade 读取与解析

每个 executable `actual_order_id` 使用 exact `orderId` 查询 Account Trade
List。解析规则为：

1. symbol、positionSide、orderId 和 Ticket exposure window 必须一致。
2. `tradeId`、时间、数量、价格、`commission` 和 `commissionAsset` 必须完整。
3. 数量和价格必须大于 0；native fee amount 必须大于或等于 0，所有值使用
   `Decimal`。
4. `realizedPnl` 作为交易所对账证据保存，但 Review 的独立 PnL 公式仍由
   domain 使用价格、数量和方向计算。
5. 同一 `tradeId` 重复且内容相同则幂等去重；内容冲突则 fail closed。
6. entry 与 exit 角色来自 resolved command reference，不来自 trade 猜测。
7. entry fill quantity 和全部 exit fill quantity 必须分别精确等于 Ticket
   executed entry quantity。
8. 恰好达到 API page limit 且数量不能被 order/expected quantity 证明完整
   时，视为 facts unavailable，不能静默截断。

### Review attribution evidence

Review metrics 新增一个由 frozen model 生成的不可变证据块：

```text
attribution_version = binance_order_id_v1
resolved_orders[]
entry_trade_ids[]
exit_trade_ids[]
attribution_digest
```

`attribution_digest` 对 canonical、排序后的 resolved order identities 和
fills 计算 SHA-256。它用于证明 Review 使用了哪组订单和成交，不取代原始
Command/Event/PostgreSQL/交易所证据。

### 提交响应的最小证据

`_safe_response_payload()` 应保留经过 allowlist 和类型校验的：

```text
status
clientOrderId
algoId
clientAlgoId
actualOrderId
actualPrice
actualQty
```

敏感字段和未知原始响应仍不得落库。历史 BTC 不依赖新增字段，因为现有顶层
`exchange_order_id` 已可用于 exact algo query；新增字段只改善未来审计。

## 设计三：退出订单语义与 BNB 手续费估值

### 退出订单合同

三类退出订单的长期语义固定如下：

| 订单角色 | Exchange command | Time in force | 目标 | 是否允许降级 |
| --- | --- | --- | --- | --- |
| 初始止损 | **STOP_MARKET** | 不适用 | 确定性限制左尾 | 否 |
| TP1 | **LIMIT** | **GTX** | Maker-only 部分止盈 | 不允许自动降级为 taker |
| Runner protection | **STOP_MARKET** | 不适用 | 确定性保护剩余右尾 | 否 |

`OrderCommandPayload` 增加显式字段：

```python
time_in_force: Literal["GTC", "GTX"] | None
```

并在 frozen model 中强制：

1. `LIMIT` 必须声明 `time_in_force`。
2. TP1 只允许 `LIMIT + GTX`。
3. `MARKET`、`STOP_MARKET` 和 `TAKE_PROFIT_MARKET` 禁止携带
   `time_in_force`。
4. Venue Adapter 必须把 TP1 精确映射为 Binance
   `timeInForce=GTX`，并在 accepted/readback facts 中核对 type、
   origType 和 timeInForce。
5. 任何 command retry 都复用同一 immutable payload，不能在重试时改变
   GTX 语义。

### TP1 Maker 拒绝语义

若冻结的 TP1 价格在提交时已经会立即成交，Binance 可以拒绝 GTX。此时：

1. 不调整 TP1 价格；
2. 不自动重发为 GTC LIMIT；
3. 不自动重发为 MARKET；
4. 不把 rejected TP1 伪装为成功保护；
5. 保留已经确认的初始 STOP_MARKET；
6. 记录精确 ExchangeCommand 终态和 Incident，由代理通过 PostgreSQL
   Monitor 汇报；
7. Lifecycle 继续对初始止损和真实持仓进行安全对账。

这条规则把 **Maker TP1** 定位为收益优化，不允许它削弱
**STOP_MARKET 的确定退出能力**。后续如需“重新计算一个新的 maker 价格”，
必须另行定义新的 command generation 语义，不能藏在 Adapter fallback 中。

### 原生手续费模型

```python
class NativeFee(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset: Literal["USDT", "BNB"]
    amount: Decimal


class FeeValuationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal[
        "native_usdt",
        "binance_usdm_bnbusdt_review_index_snapshot",
    ]
    rate_usdt_per_asset: Decimal
    price_pair: str | None
    observed_at_ms: int | None
    valued_at_ms: int


class ValuedFee(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    native: NativeFee
    usdt_value: Decimal
    evidence: FeeValuationEvidence
```

每条 `AttributedTradeFill` 保存一个 `ValuedFee`。一个 Ticket 内允许不同成交
分别使用 USDT 和 BNB 扣费；Review 汇总的是每条 `usdt_value`，同时保留
每条 native amount、asset 和估值证据。

### BNB 到 USDT 的唯一估值规则

为避免不同消费者各选一个价格，本项目只允许以下 convention：

1. `commissionAsset=USDT`：`rate=1`，method=`native_usdt`。
2. `commissionAsset=BNB`：只在最终 **Review** 读取一次 Binance USD-M
   `BNBUSDT` public index price snapshot；同一 Ticket 的所有 BNB fee
   使用这一份冻结快照。
3. `method=binance_usdm_bnbusdt_review_index_snapshot`，必须保存
   `price_pair=BNBUSDT`、`rate_usdt_per_asset` 与 `observed_at_ms`。
4. 该数值明确是 **Review-time estimate**，不是成交时刻的历史精确汇率；
   原始 `commission`、`commissionAsset`、`tradeId` 与 `orderId` 始终保留。
6. 使用 `Decimal` 计算：

```text
usdt_value = native_bnb_amount * bnbusdt_index_close
```

7. 价格缺失、非正数或读取时间无效时返回
   `FACTS_UNAVAILABLE`，不得把 fee 写成 0，也不得读取本地缓存价格或人工
   输入补位。
8. Lifecycle、Unknown recovery、Initial Stop、runner floor 与所有 Entry
   admission 均不读取 BNB price；它们继续使用配置中的非折扣 taker fee
   上界。BNB 估值失败只影响 Review 的经济数据完整性，不影响交易安全。

这个 USDT 数值是项目的**可复算 Review 快照估值**，不是声称 Binance 在
成交回执中直接提供了 USDT 等值，也不声称它等于成交时刻的历史汇率。

### BNB 只读能力事实

新增 frozen `FeeDiscountCapabilityFacts`：

```text
fee_burn_enabled
bnb_futures_wallet_balance
observed_at_ms
source = binance_usdm_readonly
```

只允许读取：

- `GET /fapi/v1/feeBurn`；
- USD-M account balance 中的 BNB wallet balance；
- public `BNBUSDT` index price snapshot。

明确禁止：

- 调用 fee burn 变更接口；
- 自动购买、兑换或卖出 BNB；
- 自动 Spot/Futures/Internal transfer；
- Multi-Assets Mode 或 BNB margin；
- 把 BNB 余额并入 `OwnerCapitalFacts`、可用保证金、CapacityClaim、仓位
  sizing、Initial Stop risk 或 liquidation evidence。

### 执行预算与真实费用分离

1. Lifecycle 不将原生 BNB fee 换算为 USDT；它与所有执行风险公式均使用
   配置的非折扣 taker fee 上界。
2. Review 的 entry/exit BNB fee 使用一个冻结的 Review-time index snapshot
   估值，并保留每条真实 native fee。
3. runner floor 对未来 STOP_MARKET 的费用估计继续使用配置中的
   **非折扣 taker fee 上界**。
4. 预算、Initial Stop 和 liquidation safety 不假设 BNB 一定存在，也不
   假设 fee burn 一定开启。
5. 因此 BNB 折扣只构成结果端的正向差异，不会扩大仓位或降低安全余量。

### Owner 人工操作边界

生产顺序固定为：

```text
AVAX 与其余持仓全部平仓
-> 部署已经支持 native BNB fee + USDT valuation 的新版本
-> 完成只读认证且 Entry 仍按发布计划受控
-> Owner 在交易所人工转入少量 BNB
-> Agent 只读复核 feeBurn + BNB balance
-> PostgreSQL Monitor 记录能力状态并由代理汇报
```

程序不提交转入指令，也不把“Owner 将会转入”当成部署认证已经通过的事实。
`fee_burn_enabled=false`、BNB 余额为 0 或低于后续 Owner 固定的观察阈值，
只产生**成本优化 warning**，不阻止保护、退出、Settlement、Review 或新的
Entry。Binance 若继续以 USDT 扣费，统一 fee model 仍能正常归因。

## 设计四：三个消费者统一迁移

### Lifecycle

`LifecycleFactsRequest` 不再只接收 entry client id，而是接收 typed
`entry_order_reference`。

入场手续费通过 entry 的 exact regular `orderId` 读取并保留 native fee。
runner floor 继续采用配置的非折扣 taker fee 上界，不读取 BNB valuation。
TP1 状态仍使用现有正确 namespace 的 exact order lookup。费用事实不可得时
保持 `FACTS_UNAVAILABLE`，不得把 0 当作“已证明零手续费”。

### Unknown command recovery

unknown outcome 尚无 accepted order id，因此 resolver 使用
`venue_client_order_id` 做一次精确订单查询：

- regular 使用 `origClientOrderId`；
- conditional 使用 `clientAlgoId`/conditional namespace。

若订单可见，先得到 submitted/actual order identity，再用 `orderId` 查询
成交。`matching_fill_quantity` 只来自 exact orderId fills。

仍保持现有不变量：

- unknown outcome 永不盲目重发；
- identity contradiction 创建 Incident 并 fail closed；
- visibility deadline 前不把未见当成不存在；
- position/open order/current state 事实继续共同参与决策。

### Review

Reconciliation application 从 repository 取得 exact Ticket 的
`TicketOrderReference` 集合并构建 `ReviewAttributionRequest`。Adapter 返回
typed resolved orders、entry fills、exit fills 和 funding facts。

Review 不再接收：

```text
entry_venue_client_order_id
exit_venue_client_order_ids
```

作为最终成交过滤条件。

## 设计五：BTC 正常事件闭环

### 前置状态

本设计处理的 BTC 必须在切换时仍处于：

```text
SETTLEMENT_PENDING
or REVIEW_PENDING
```

并同时满足：

- exchange position quantity = 0；
- exchange open regular/conditional orders = 0；
- protected quantity/order residue = 0；
- unresolved command = 0；
- open Incident = 0；
- budget/capital/account capacity/netting domain 已释放；
- Ticket 仍具有完整 Event 与 Command lineage。

### 正常回放

若状态是 `SETTLEMENT_PENDING`：

```text
existing ReconciliationMatched
-> settle_ticket()
-> append BudgetSettled
-> REVIEW_PENDING
-> exact order attribution
-> calculate_review_economics()
-> insert TradeReview
-> append ReviewRecorded
-> TERMINAL
```

若状态已经是 `REVIEW_PENDING`，从 exact order attribution 开始，不重复
Settlement。

整个流程使用现有 UoW、Reducer、Event、Review repository 和 optimistic
version。不得：

- UPDATE Aggregate 到 terminal；
- INSERT 一个脱离 Event 的 Review；
- 手工写 trade/order id；
- 用 BTC 专用代码分支；
- 把 Owner 提供的示例值当生产输入。

### 终态验收

BTC 只有同时满足以下事实才算完成：

1. Aggregate status = `terminal`。
2. 事件链存在且只存在一次 `BudgetSettled` 和一次 `ReviewRecorded`。
3. TradeReview `economics_completeness = complete`，或仅 funding 因交易所
   明确不可得而使用既有 `funding_unavailable` 语义。
4. entry/exit quantity 均精确等于 Ticket executed quantity。
5. runner actual order id 与 exit trade `orderId` 精确一致。
6. 每笔 trade fee 的 native asset/amount、USDT valuation、gross/net PnL
   和 R multiple 可由保存的 facts 重算。
7. Ticket、command、position、incident、budget、capacity 和 netting
   projections 全部闭合。

### 状态漂移硬门

如果部署前 BTC 已变为 `TERMINAL` 且保存的是不完整 Review，本设计不允许
覆盖现有唯一 Review，也不允许 DML reopen。此时 closure-only 流程必须
fail closed，另行设计 append-only Review correction/revision 语义。

这是 action-time 状态分支，不在当前 pending Ticket 修复中预建复杂历史
修订平台。

## 设计六：Closure-only Handover

### 为什么现有两种发布门都不适用

| 发布模式 | 数据库要求 | 交易所要求 | BTC pending closure 是否满足 |
| --- | --- | --- | ---: |
| Flat release | active tickets/commands/positions/incidents 全为 0 | 全平、无单 | 否，Ticket 未 terminal |
| Protected handover | 每个 Ticket 有非零 position 和完整保护单 | 精确非零仓位与保护单 | 否，BTC 已平 |
| Closure-only handover | 精确 pending closure Ticket，零风险权威 | 全平、无单 | 是 |

因此若不增加第三个严格模式，会形成：

```text
修复代码能闭环 BTC
-> 但 flat gate 因 BTC 未 terminal 拒绝部署
-> protected gate 又因 BTC 已 flat 拒绝部署
-> 修复版本无法到达唯一需要它的 Ticket
```

### CLI 与计划模型

新增：

```text
--closure-ticket-id <exact-ticket-id>
```

`DeploymentPlan` 约束：

1. `closure_ticket_id` 必须非空、精确；本次模式只允许一个 Ticket，不能使用
   通配符、状态选择器或集合扩展。
2. closure、protected、regular flat 三种模式互斥。
3. closure mode 与 `--enable-entry` 互斥。
4. closure mode 不允许 schema revision 变化。
5. closure mode 不扩大 venue/account/instrument/policy/leverage 范围。

本次实际发布只允许当前精确 BTC Ticket，不使用通配符、status-only 或“所有
pending Ticket”选择器。

### 只读认证

closure certification 对每个 exact Ticket 输出 typed manifest：

```text
ticket_id
aggregate_status
aggregate_version
last_event_sequence
netting_domain_key
position_quantity
protected_quantity
owned_order_residue_count
unresolved_command_count
open_incident_count
budget_reservation_status
account_capacity_released
netting_domain_released
review_presence
```

同时要求账户级：

- exchange non-flat domain count = 0；
- regular/conditional open order count = 0；
- configured leverage = **5x**；
- cross margin、independent long/short 不变；
- runtime commit/schema/seed identity 完整；
- Entry write fence 存在；
- Entry `ActiveState=inactive` 且 `UnitFileState=disabled`。

`feeBurn` 和 BNB 余额属于成本能力事实，不属于 closure safety gate。它们
缺失或未开启不能阻塞已经平仓 Ticket 的 Settlement/Review，但若历史成交
实际以 BNB 扣费，则 BNBUSDT 估值事实必须可得，Review 才能声明经济数据
完整。

### 无竞态切换顺序

```text
安装 committed target release
-> 旧版本只读 closure preflight
-> 停止全部四个 Worker
-> 写入/确认 Entry fence，并 disable --now Entry
-> 确认所有 Worker 已停
-> 再次读取 DB + exchange + systemd exact facts
-> 对 exact closure Ticket 旋转 runtime identity
-> 激活 target symlink/markers
-> target 只读 closure postflight
-> 启动 Observation/Lifecycle/Reconciliation
-> 确认 Entry inactive + disabled + fenced
-> Reconciliation 正常推进 closure
-> 最终 flat certification
```

第二次认证必须在旧 Worker 停止后执行，防止 BTC 在 preflight 和 identity
rotation 之间从 Settlement 变化到不允许的状态。

### 失败恢复

1. identity rotation 前失败：旧 release/identity 保持权威，Entry 仍 fenced；
   恢复旧安全 Worker。
2. identity rotation 后失败：不得启动旧 commit writer；保持 target Entry
   fenced，只启动与新 identity 匹配的 target safety Worker，或全部保持
   stopped 并明确阻塞。
3. 任一状态矛盾：不尝试自动改 Ticket、Position、Order 或 Review。
4. 部署 result 必须记录 mode、exact ticket ids、pre/post identity 和 Entry
   service/fence 状态，但不写生成式 Markdown/JSON 到 runtime cadence。

### 不是新的不合规口子

Closure-only mode 只有同时满足“精确 Ticket、已平、无单、无 unresolved、
无 Incident、已释放权威、状态仅 Settlement/Review、Entry fenced、schema
不变”才成立。

它不能用于：

- 带仓位发布；
- 带未确认订单发布；
- 绕过 Review；
- 迁移 schema；
- 启动 Entry；
- 泛化接管任意 active Ticket；
- 手工改变历史终态。

## Entry 启动语义

### P1 修复发布

本次 closure-only P1 发布：

```text
Observation = active/enabled
Lifecycle = active/enabled
Reconciliation = active/enabled
Entry = inactive/disabled
Write fence = present
```

即使 BTC terminal、全部持仓 flat、Owner Policy
`new_entry_submit_enabled=true`，也不会自动启动 Entry。

### 后续正式统一发布

只有完成：

1. P1 修复本地验收；
2. BTC 正常 Review 闭环；
3. 所有 runtime activity 为 0；
4. StrategyUniverse 实现、迁移、播种与认证；
5. action-time PostgreSQL、exchange、schema、commit、service 认证；

之后，正式部署才显式携带 `--enable-entry`。部署脚本必须先启动
Observation/Lifecycle/Reconciliation，最后独立执行：

```text
systemctl enable --now brc-trading-kernel-entry-worker.service
```

postflight 同时验证 `ActiveState=active` 和 `UnitFileState=enabled`。

Owner 的 BNB 人工转入发生在支持 native BNB fee 的版本部署完成之后。该
人工动作不会触发 Entry 启停，也不会改变 `--enable-entry` 的显式发布门。

## 一致性、审计与追溯

### 持仓和订单证据链

本次补强后的主要审计路径为：

```text
Ticket
-> ExchangeCommand(command_id, kind, client id)
-> accepted result(submitted orderId/algoId)
-> conditional resolution(actualOrderId)
-> Binance trade(tradeId, orderId)
-> native fee(asset, amount)
-> BNBUSDT Review-time index snapshot when required
-> AttributedTradeFill + valued fee evidence
-> Review attribution digest
-> ReviewRecorded
```

该链直接服务于 Owner 已确认的重点：**持仓与订单审计**，不建设运维操作
审计平台。

### 不可变性

1. 原 Ticket、Event、Command 和 accepted result 不重写。
2. Review 只在 `REVIEW_PENDING` 创建一次。
3. attribution evidence 与 economics 一起冻结。
4. 重试读取相同交易所事实时产生相同 canonical digest。
5. fee valuation evidence 记录 pair、method、rate 和 snapshot observed time，不能只
   保存最终 USDT 数值。
6. Universe 将来仍只通过 Ticket 关联 Review，不影响本次订单归因。

## 可观测性

不新增推送平台。持续的 closure facts unavailable 使用现有 PostgreSQL
Monitor 投影表达：

```text
monitor_key = ticket:<ticket_id>:closure
owner_status = processing | temporarily_unavailable | completed
summary = stable summary
intervention = empty or exact blocker
```

仅在超过 starvation limit、重复 attribution failure 或 identity
contradiction 时写 Monitor Event，避免每个 5 秒 cadence 产生噪声。代理从
PostgreSQL 读取并汇报。

BNB 能力状态使用独立、稳定的 Monitor key：

```text
monitor_key = account:<account_id>:bnb-fee-capability
owner_status = available | unavailable | low_balance | unknown
summary = fee burn status + observed BNB balance
intervention = Owner-only manual action or empty
```

余额阈值只用于 Owner 提醒，不参与交易 admission。Monitor 不保存凭证，
也不发起购买、划转或 fee burn 变更。

## 安全与性能预算

### 安全不变量

1. P1 attribution、估值与认证不新增任何 exchange write；TP1 仍只通过
   现有 durable Exchange Command 官方写路径提交。
2. 所有新归因、fee capability 和估值交易所调用均为 readonly。
3. 网络 I/O 不进入数据库 transaction。
4. unresolved outcome 不重发。
5. identity contradiction fail closed。
6. closure handover 永远保持 Entry fenced。
7. 不改变 5x、Cross、independent sides、budget 或 Netting Domain 语义。
8. TP1 GTX 拒绝不降级成 taker order。
9. BNB 不进入 capital、margin、sizing、stop risk 或 liquidation truth。
10. BNB 缺失不会削弱 STOP_MARKET，也不会阻止既有仓位退出。

### 性能边界

1. 每个 Reconciliation cadence 最多选择一个 normal work item。
2. 每个 exact order lookup 和 trade query 使用单 Ticket、单 symbol、单
   order identity。
3. trade page limit 最大 **1000**，禁止无界全账户历史扫描。
4. Review order references 只读取 exact Ticket，不扫描其他 Ticket。
5. 条件订单解析并发度固定且很小；不能按账户全部 algo order 做全量抓取。
6. 30 秒 Review retry 避免持续失败时每 5 秒重复打 Binance。
7. PostgreSQL selector 使用 active status/due 索引并 `LIMIT 1`。
8. 一个 Review 最多读取一次 BNBUSDT public index snapshot，且仅在存在 BNB
   native fee 时读取。

## 代码规范与可维护性

1. financial value 全部使用 `Decimal`。
2. core boundary 使用 frozen named Pydantic model。
3. raw Binance dict 只存在于 infrastructure parser 内。
4. status/namespace/role 使用 Enum/Literal，不传魔法字符串。
5. 不使用 `get(... ) or ...` 串联多个身份字段做模糊 fallback。
6. 不增加 legacy reader、dual write、schema fallback 或 BTC 特例。
7. fixture 必须复现官方字段，不得给 user trade 伪造 `clientOrderId`。
8. 一个 resolver 被三个消费者复用，但每个消费者仍保有自己的业务校验。
9. `venue_adapter.py` 只编排，不复制 order attribution parser。
10. native fee、valuation evidence 和 order TIF 使用明确类型；BNB 估值只在
    Review 编排层发生，不能散落到 Lifecycle、Unknown 或 runner 公式中。
11. Adapter 不实现 GTC/MARKET fallback，不在错误处理层改变策略订单语义。
12. 所有 API method/endpoint 使用 allowlist port；生产依赖图中不得出现
    fee burn POST、purchase、convert 或 transfer capability。

## 与 StrategyUniverse 的发布关系

两项工作保持独立提交和独立验收：

```text
P1 fairness/order attribution 代码
-> schema 仍为 0001
-> 等待 SOL/AVAX 等剩余交易所持仓与订单自然全平
-> closure-only 发布且 Entry fenced
-> BTC terminal Review 完整
-> flat certification
-> StrategyUniverse 代码与 migration
-> 最终生产标的清单固定
-> normal flat deployment
-> safety services
-> explicit --enable-entry
```

不得把 P1 修复、BTC closure、Universe migration 和生产播种打成一个不可
分辨的发布包。

## 已确认的 Owner 决策

| 决策 | 已确认语义 | 工程约束 |
| --- | --- | --- |
| 初始止损 | **STOP_MARKET** | 不因手续费优化改变 |
| TP1 | **LIMIT Maker-only** | 实现为 LIMIT + GTX，不做 taker fallback |
| Runner | **STOP_MARKET** | 保留确定退出能力 |
| BNB 接入时点 | AVAX 平仓且支持版本部署后 | Owner 人工转入少量 BNB |
| 自动化边界 | 不自动购买、划转或启用 BNB 扣费 | Agent 只读认证并汇报 |
| 资金边界 | BNB 不作保证金或风险资产 | 不进入 capital、sizing、Capacity |
| BNB 估值 | **Review 单次指数快照估值** | 保留 native fee；不进入执行风险链 |

## 仍需 Owner 确认的设计参数

| 决策 | 推荐值 | 影响 | 未确认时状态 |
| --- | --- | --- | --- |
| Closure starvation limit | **30 秒** | 关闭最长等待与 position cadence 插队频率 | 不编码 |
| Review retry interval | **30 秒** | Binance 失败重试负载 | 不编码 |
| BTC 接管方式 | **closure-only、Entry fenced** | 解除现有 flat/protected 双门闭锁 | 不部署 |
| BTC 状态漂移 | terminal incomplete 时单独设计 correction | 避免覆盖唯一 Review | fail closed |
| 同类缺陷范围 | Lifecycle + Unknown + Review 一次收口 | 增加测试面，消除重复错误口 | 不做局部补丁 |
| BNB 提醒阈值 | 生产播种前由 Owner 固定，只作为 warning | 影响提醒频率，不影响交易 admission | 不硬编码 |

## 完成定义

本设计对应实现只有同时满足以下条件才可声明本地完成：

1. 多 Ticket PostgreSQL integration 证明 closure 不饥饿。
2. Binance 官方形状的普通/条件订单归因测试全部通过。
3. Lifecycle、Unknown recovery、Review 不再依赖
   `trade.clientOrderId`。
4. BTC fixture 通过正常 Event/Reducer/UoW 形成完整 Review。
5. closure-only deployment 测试证明 Entry 不能被启用。
6. 初始止损和 runner 始终为 STOP_MARKET，TP1 始终为 LIMIT + GTX。
7. GTX 拒绝测试证明不会产生 GTC、MARKET 或调价 fallback command。
8. USDT、BNB、混合 fee asset、Review snapshot 缺失/非正数全矩阵通过；BNB
   估值不进入 Lifecycle 或 runner 风险链。
9. BNB 不进入 sizing/capital/margin 的 architecture 与 integration gate
   通过。
10. 禁止自动购买、划转、fee burn 变更的静态能力审计通过。
11. 完整 unit/integration/full-chain/architecture suite 通过。
12. Ruff、Mypy、runtime file-I/O audit、`git diff --check` 通过。
13. 没有生产代码、测试或脚本中的 BTC 专用分支。
14. Tokyo 动作仍停在独立 Owner 确认门前。
