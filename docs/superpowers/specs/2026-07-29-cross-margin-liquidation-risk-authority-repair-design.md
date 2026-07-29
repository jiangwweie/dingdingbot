---
title: Cross-Margin Liquidation Risk Authority Repair Design
status: PROPOSED_OWNER_REVIEW
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-29
revision: 1
---

# Cross-Margin Liquidation Risk Authority Repair Design

## 决策门

本文档定义 **Cross 保证金成交后清算风险权威修复**。本轮只完成设计与
测试设计，不授权生产代码修改、PostgreSQL 迁移、Tokyo 发布或重新启用
Entry。

Owner 审阅通过后，才可根据本文档编写实施计划并执行本地
RED/GREEN/REFACTOR。生产 Entry 必须保持 fenced，直到修复版本、本地验收、
平仓闭环、迁移前置条件和 Tokyo action-time 认证全部通过，并获得独立的
Owner 恢复确认。

当前代码、PostgreSQL 与交易所只读事实始终高于本文档。本文档是拟议设计，
不是生产运行权威。

## 核心结论

本次问题不是阈值过严，也不是 Hedge Mode 本身错误，而是系统同时存在两套
互不一致的清算风险权威：

1. Entry 前使用账户资金、当前仓位、标记价和维护保证金分档计算
   `projected_liquidation_price`。
2. Entry 成交后直接使用 Binance `positionRisk.liquidationPrice` 作为
   当前 Netting Side 的独立清算价。

第二套权威在当前 **Cross + independent sides** 账户模式下已经被实盘事实
证伪：

- ETH Long 返回 `0`，被适配器转换为 `None`；
- AVAX Long 返回约 `13.9..14.17`，高于约 `6.58..6.62` 的多头入场价；
- 两种输入均进入
  `liquidation_safety_degraded -> flatten_after_protection`；
- 程序先确认 Initial Stop，再主动提交 Controlled Flatten，并非市场触发
  Stop。

修复后只保留一个权威：

> **Trading Kernel 使用同一个纯 Domain Cross-margin 投影器完成 Claim、
> ENTRY dispatch 和成交后复核。交易所报告的 liquidationPrice 只作为原始
> 观测证据，不再授予自动平仓权限。**

## 已知客观事实

### 当前执行链

现有生产链保持不变：

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

策略代码仍结束于 `StrategySignal`。本修复不改变策略、Event、Universe、
币种池、ExitPolicy、预算比例、并发上限、固定 `5x`、Cross 保证金或
independent-sides 账户要求。

### 当前失败路径

```text
Reconciliation reads PositionSnapshot
-> adapter converts reported liquidationPrice
-> reconcile_ticket builds PostFillRiskRequest
-> assess_post_fill_risk requires reported price to be directional and non-null
-> EntryFilled freezes liquidation_safety_degraded
-> InitialStopConfirmed
-> reducer prepares ControlledFlatten
```

当前 `PositionSnapshot.liquidation_price` 混合了三个不同概念：

1. 交易所原始报告值；
2. 适配器对 `0`、空值和多行的解释；
3. Kernel 对一个 Netting Side 的清算风险结论。

这种混合导致适配器字段直接获得交易决策权。

### 事实来源

| 客观事实 | 当前代码证据 |
| --- | --- |
| `EntryFilled` 直接把 `snapshot.liquidation_price` 送入成交后风险判断 | [`reconcile_ticket.py`](../../../src/trading_kernel/application/reconcile_ticket.py#L103) |
| 缺失或方向不正确的 liquidation 值会被判为不安全 | [`post_fill_risk.py`](../../../src/trading_kernel/domain/post_fill_risk.py#L140) |
| Adapter 当前把原始 `0` 归为 missing | [`venue_adapter.py`](../../../src/trading_kernel/infrastructure/venue_adapter.py#L1681) |
| Claim 与 dispatch 分别实现了一套清算公式 | [`capacity_sizing.py`](../../../src/trading_kernel/domain/capacity_sizing.py#L407)、[`revalidate_entry_dispatch.py`](../../../src/trading_kernel/application/revalidate_entry_dispatch.py#L380) |
| Aggregate 当前仍保存含义混合的 `actual_liquidation_*` 字段 | [`0001_initial.py`](../../../migrations/trading_kernel/versions/0001_initial.py#L620) |

### 当前已有可复用能力

当前代码已经具备以下正确基础：

- `EntryAdmissionSnapshot` 提供 Cross 账户的
  `total_margin_balance`、`total_maintenance_margin`、全部当前持仓、
  标记价、账户模式和事实摘要；
- `InstrumentRulesFacts` 提供版本化维护保证金分档及其摘要；
- `CapacityClaim` 冻结 Entry 前的账户事实、分档身份、投影清算价、距离和
  比率；
- ENTRY dispatch 会从新鲜 action-time 事实再次验证清算距离；
- Initial Stop、Controlled Flatten、Incident、Entry blocking scope 和
  durable Exchange Command 已存在；
- Reconciliation worker 已拥有读取外部仓位事实并推进 Ticket 的职责。

修复必须复用这些边界，不创建第二个风险服务、第二条订单链或文件型证明。

## 方案比较

| 方案 | 能否解决 P0 | 对现有架构影响 | 决策 |
| --- | --- | --- | --- |
| 只禁止同一合约同时 Long/Short | 不能保证；Cross 账户语义仍存在 | 改变策略能力但不关闭字段权威错误 | 拒绝 |
| 将交易所账户切换为 one-way | 可能减少 Side 歧义，但不能证明 Cross 清算风险 | 需要重写 Netting Domain、保护和对账语义 | 拒绝 |
| 将 `0` 或方向错误的报告值视为安全 | 隐藏矛盾，可能放过真实风险 | 小改动但不安全 | 拒绝 |
| 删除成交后清算检查 | 消除误平仓，但丢失实际成交后的风险复核 | 简单但不完整 | 拒绝 |
| 统一账户级 Cross 投影，并将 venue 值降为观测 | 关闭根因并保留成交后安全检查 | 有界的 Domain/Application/Adapter/Schema 改造 | 采用 |

## 最终业务语义

### 保留的账户与持仓模型

```text
position mode = independent_sides
margin mode   = cross
leverage      = exchange configured fixed 5x
Netting Domain = venue + account + instrument + position_side
```

Long 和 Short 仍是独立 Netting Domain，同一合约的两边可以在 Owner Policy、
预算、健康度和保护条件允许时共存。清算投影必须把同一合约的两个 Side 都
纳入价格变化函数，而不能把相反 Side 当作不变的账户背景。

### 权威与非权威

| 信息 | 新语义 | 能否触发自动平仓 |
| --- | --- | --- |
| `venue_reported_liquidation_price` | Binance 原始观测；`0` 必须原样保留 | 否 |
| `cross_margin_risk_snapshot` | 一次带时间、账户、合约、Side、分档身份和摘要的只读事实 | 不能单独触发 |
| `cross_margin_liquidation_proof` | Kernel 纯 Domain 计算结果 | 可以 |
| `actual_stop_risk` | 实际成交数量、均价与冻结 Initial Stop 的损失 | 可以 |
| Owner Policy 阈值 | `min_liquidation_distance_to_stop_distance_ratio` | 与 proof 联合决定 |

交易所报告值与 Kernel 计算值必须使用不同字段、不同名称和不同审计身份。
不得再使用 `actual_liquidation_price` 这种无法区分来源的名称。

## 统一 Cross-Margin 投影模型

### Domain 边界

新增一个纯 Domain 模块：

```text
src/trading_kernel/domain/cross_margin_liquidation.py
```

它不依赖 SQLAlchemy、CCXT、文件、网络、环境变量或 wall clock，只消费冻结
的 Pydantic 模型和 `Decimal`。

拟议核心类型：

```python
class CrossMarginPosition(BaseModel):
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    quantity: Decimal
    average_entry_price: Decimal


class CrossMarginRiskSnapshot(BaseModel):
    venue_id: str
    account_id: str
    account_risk_mode: Literal["standard_futures_single_asset"]
    settlement_asset: Literal["USDT"]
    position_mode: Literal["independent_sides"]
    margin_mode: Literal["cross"]
    exchange_instrument_id: str
    mark_price: Decimal
    total_margin_balance: Decimal
    total_maintenance_margin: Decimal
    instrument_positions: tuple[CrossMarginPosition, ...]
    maintenance_margin_brackets: tuple[MaintenanceMarginBracket, ...]
    maintenance_margin_brackets_digest: str
    observed_at_ms: int
    valid_until_ms: int
    snapshot_digest: str


class CrossMarginLiquidationProof(BaseModel):
    model_id: Literal["cross-margin-liquidation-v1"]
    snapshot_digest: str
    maintenance_margin_brackets_digest: str
    status: Literal[
        "proved_safe",
        "proved_safe_no_adverse_root",
        "proved_unsafe",
        "facts_contradictory",
    ]
    projected_liquidation_price: Decimal | None
    liquidation_distance: Decimal | None
    liquidation_distance_to_stop_distance_ratio: Decimal | None
```

`facts_unavailable` 不由纯 Domain 伪造。网络超时、缺行和无法读取属于
Application/Interface 的事实采集结果；只有完整且自洽的 snapshot 才能调用
Domain 投影器。

本模型只认证 **标准 USD-M 单资产 USDT 全仓账户**。Multi-Assets Mode、
Portfolio Margin、非 USDT 结算或其他会改变 collateral haircut、账户权益和
维护保证金含义的账户类型必须拒绝产生 snapshot，并进入
`post_fill_risk_facts_contradictory`。BNB 只参与最终手续费换算，不进入
margin balance、maintenance margin、抵押物或 liquidation proof。

交易所原始 liquidation observations 不属于 `CrossMarginRiskSnapshot`，
不参与 `snapshot_digest` 或 proof。它们由 `PositionSnapshot` /
`EntryFilled` 作为独立审计字段保存。改变一个 raw observation 不能改变
canonical snapshot digest。

### 维护保证金函数

适配器将 Binance 分档中的：

```text
notionalFloor
notionalCap
maintMarginRatio
cum
```

解析为版本化 `MaintenanceMarginBracket`。统一模型按每个价格区间使用：

```text
maintenance_margin(notional)
    = notional * maintenance_margin_rate - maintenance_amount
```

其中 `maintenance_amount` 对应原始 `cum`。任何影响分档的额外系数必须进入
typed facts 和 digest；适配器遇到不能表达的分档结构时拒绝产生 proof，不得
静默忽略。

该减法语义以 Binance 官方
[Clearing Procedures](https://bin.bnbstatic.com/static/cms/cg08ou2ak0tn7mcplvfg/file/53197b612332da02c20b5b7d19b81ff53ee5f4938c6330c72a30a1ca4f91049f.pdf)
中的维护保证金公式为外部依据。实现验收仍必须使用 action-time 账户模式、
真实 bracket payload 和本地脱敏回放证明适配器映射正确，不能仅凭文档公式
宣称通过。

维护保证金不得为负。分档必须连续、无重叠、按 floor 排序，并且候选
notional 必须恰好匹配一个分档。

### 账户函数

对于被评估的精确合约，将当前账户事实拆成：

```text
base_margin_balance
    = total_margin_balance
      - 当前该合约全部 Long/Short 的未实现盈亏

base_maintenance_margin
    = total_maintenance_margin
      - 当前该合约全部 Long/Short 的维护保证金
```

对于候选合约价格 `P`：

```text
long unrealized PnL  = quantity * (P - average_entry_price)
short unrealized PnL = quantity * (average_entry_price - P)

account_margin_balance(P)
    = base_margin_balance
      + 该合约全部 Long/Short 在 P 的未实现盈亏

account_maintenance_margin(P)
    = base_maintenance_margin
      + 该合约全部 Long/Short 在 P 的维护保证金
```

清算根满足：

```text
account_margin_balance(P) = account_maintenance_margin(P)
```

这是一个 **单因子 action-time 投影**：只令当前候选合约的价格变化为 `P`，
其余合约的 mark price、未实现盈亏和维护保证金保持 snapshot 时刻不变。
它用于证明“在其他账户事实不变时，当前 Ticket 的 Initial Stop 是否先于账户
维护保证金边界”，不是交易所承诺的真实清算价，也不证明多个相关资产同时
剧烈波动时账户绝不会清算。

该边界与 Owner 已决定暂缓的组合相关性治理一致。未来如引入多资产联合压力
测试，应作为独立 portfolio-risk admission policy 消费同一账户 facts，不得
悄悄改变 `cross-margin-liquidation-v1` 的既有语义。

由于价格变化可能跨越维护保证金分档，投影器必须枚举由
`notionalFloor / quantity` 和 `notionalCap / quantity` 形成的确定性价格区间，
在每个区间内解线性根并验证根仍位于该区间。禁止使用二进制浮点或依赖迭代
次数的近似结果。

### 方向与安全距离

对 Long Ticket，只搜索从当前价格向下的 adverse root；对 Short Ticket，只
搜索向上的 adverse root。

```text
Long distance  = initial_stop_price - liquidation_root
Short distance = liquidation_root - initial_stop_price

stop_distance = abs(actual_or_reference_entry_price - initial_stop_price)
ratio = liquidation_distance / stop_distance
```

判断：

| 结果 | 条件 |
| --- | --- |
| `proved_safe` | root 在 Initial Stop 之外，且 ratio 不低于 Ticket 冻结阈值 |
| `proved_safe_no_adverse_root` | adverse 方向所有合法分段均无清算根，且当前账户已经满足 margin balance > maintenance margin |
| `proved_unsafe` | root 在错误方向、侵入 Stop，或 ratio 低于冻结阈值 |
| `facts_contradictory` | 当前账户已不满足保证金不变量、分档不唯一、计算出的基础维护保证金为负，或 typed facts 互相矛盾 |

`proved_safe_no_adverse_root` 是显式业务状态，不得用虚构的无限价格或超大
数字代替。

## 三次使用同一个投影器

### CapacityClaim

Entry 前将 `EntryAdmissionSnapshot` 中该合约当前的所有 Long/Short 行，加上
拟议新 Ticket 的数量、Side 和参考入场价，构造 hypothetical
`CrossMarginRiskSnapshot`。

缺失账户事实、分档或唯一匹配时，CapacityClaim 返回
`LIQUIDATION_PROOF_FAILED`，不创建 Ticket 或 Exchange Command。

### ENTRY Dispatch

真正提交 ENTRY 前读取新的 action-time snapshot，用当前盘口、当前账户与
相同 Ticket 数量重建 proof。

如果 proof 与 Ticket、Claim、Policy、Side、分档 digest 或最低比率不一致，
ENTRY 终态拒绝。该路径必须调用同一个 Domain 投影器，删除
`revalidate_entry_dispatch.py` 中的重复公式。

### 成交后复核

成交后不再把 `PositionSnapshot.liquidation_price` 传给
`assess_post_fill_risk`。Reconciliation 使用实际成交数量、实际成交均价、
当前账户事实、当前同合约 Long/Short 仓位和当前分档产生新的 proof。

成交后 proof 决定是否继续 TP1/runner 或进入受控平仓。

## 成交后生命周期重排

### 为什么必须重排

如果把“读取完整账户风险事实”作为记录 Entry Fill 的前置条件，短暂网络故障
可能阻止系统确认仓位，从而延迟 Initial Stop。保护优先级必须高于清算投影。

因此拆分：

```text
EntryFilled
-> actual stop-risk decision
-> Initial Stop durable command
-> InitialStopConfirmed
-> POST_FILL_RISK_RECHECK_PENDING
-> canonical Cross-margin proof
-> TP1/runner OR Controlled Flatten
```

### EntryFilled

`EntryFilled` 只冻结：

- 实际成交数量；
- 实际成交均价；
- 实际 Stop Risk；
- Stop 方向；
- 交易所报告的原始 liquidation observation；
- 原始 position observation 时间。

它不再声称已经获得账户级清算 proof。

### Initial Stop 优先

| 成交后 Stop 结果 | 动作 |
| --- | --- |
| Stop 方向错误 | 保留现有 `FLATTEN_IMMEDIATELY`；无效 Stop 不能作为保护 |
| 实际 Stop Risk 超过硬上限 | 先安装 Initial Stop，再 Controlled Flatten |
| 实际 Stop Risk 在上限内 | 安装 Initial Stop，然后进入清算风险复核 |

### 新状态与事件

新增 Aggregate 状态：

```text
post_fill_risk_recheck_pending
```

新增 append-only Trade Events：

```text
PostFillRiskEvidenceUnavailable
PostFillLiquidationRiskConfirmed
PostFillLiquidationRiskDegraded
```

事件语义：

| Event | Aggregate/Effect |
| --- | --- |
| `InitialStopConfirmed` 且需复核 | 保留 Entry Lane，进入 `post_fill_risk_recheck_pending`，不准备 TP1 |
| `PostFillRiskEvidenceUnavailable` | 状态不变；打开 account-capacity Incident；保持 Stop、Entry Lane 和无 TP1 |
| `PostFillLiquidationRiskConfirmed` | 冻结 proof；解决同类 Incident；释放 Entry Lane；准备 TP1 |
| `PostFillLiquidationRiskDegraded` | 冻结 proof；解决 unavailable Incident；准备 Controlled Flatten；不准备 TP1 |

同一轮事实不可用只允许产生一个开放 Incident 和一个 Event。后续重试只更新
`due_at_ms` 和 Monitor 当前状态，不产生重复 append-only 事件。

### 事实不可用

成交已经发生后，系统无法“拒绝这次 Entry”。正确行为是：

```text
保留已确认 Initial Stop
-> 不提交 TP1
-> 不提交新的 ENTRY
-> PostgreSQL Incident/Monitor 显示原因
-> Reconciliation 有界重试
```

不得因为事实缺失直接 Controlled Flatten，也不得把缺失 proof 解释为安全。

如果事实恢复并证明安全，Ticket 继续正常 TP1/runner；如果事实恢复并证明
不安全，才通过 durable Controlled Flatten Command 平仓。

## Adapter 与事实采集

### 新端口

在 `application/runtime_facts.py` 增加：

```python
class CrossMarginRiskSnapshotRequest(BaseModel):
    ticket_id: str
    netting_domain: NettingDomain
    observed_at_ms: int
    valid_for_ms: int


class CrossMarginRiskSnapshotSource(Protocol):
    async def read_cross_margin_risk_snapshot(
        self,
        request: CrossMarginRiskSnapshotRequest,
    ) -> CrossMarginRiskSnapshot: ...
```

该端口是只读事实端口，不具备任何下单、平仓、改变杠杆或切换账户模式的
权限。

### 有界网络调用

Adapter 对一次成交后复核只读取：

- Futures account balance/margin facts；
- 标准 Futures / Multi-Assets / Portfolio Margin 的账户模式事实；
- 精确合约的 Long/Short position rows；
- 精确合约标记价；
- 账户 position mode；
- 精确合约维护保证金分档。

读取在 PostgreSQL 事务外并发执行，统一受 worker timeout 控制。它不扫描
历史成交，不读取全部 Universe K 线，不生成 JSON/Markdown 文件。

同一次底层 position response 中的原始 liquidation observations 可以作为
独立返回值交给审计层，但不得加入 canonical risk snapshot 或 proof digest。

完整 snapshot 成功后才进入一个短 PostgreSQL 事务，锁定精确 Ticket，
复核 expected aggregate version，然后提交一个 Trade Event、Aggregate
projection、Incident effect 和最多一个 durable Exchange Command。

### 原始 liquidationPrice

Adapter 必须：

- 保留原始 `0` 为 `Decimal("0")`；
- 保留方向不合理但可解析的正数；
- 使用精确合约和 `positionSide` 归属原始行；
- 缺行时记录 observation unavailable；
- 不再通过 `or` 将 `0` 转成 `None`；
- 不对原始值取绝对值、倒数、方向修正或阈值修正。

这些值只进入 Event/Monitor 审计，不进入
`CrossMarginLiquidationProof` 的计算输入。

## 持久化与迁移

### 新 Schema Head

Owner 已明确当前部署会等待持仓、订单、Incident、Settlement 和 Review
闭环，新版本不承担旧活跃 Ticket 兼容。因此采用一笔 forward-only、
flat-only 迁移：

```text
0003_cross_margin_liquidation_authority
```

`0002_crypto_strategy_universe` 已要求 runtime/trade tables 全部为空；
`0003` 延续同一无包袱门禁并独立复核这些表为空。即使只剩 terminal Ticket
或历史 Event，迁移也必须拒绝，直到官方 flat-runtime reset 在外部和内部闭环
证明后清理旧实验事实。它不翻译旧 Event，不为历史 Ticket 合成 proof。

### Aggregate Projection

删除旧的：

```text
actual_liquidation_price
actual_liquidation_distance
actual_liquidation_distance_to_stop_distance_ratio
```

新增：

```text
post_fill_risk_snapshot_digest
liquidation_model_id
post_fill_projected_liquidation_price
post_fill_liquidation_distance
post_fill_liquidation_distance_to_stop_distance_ratio
post_fill_liquidation_proof_status
```

这些字段只保存 Kernel proof。交易所原始 liquidation observation 保存在
append-only `EntryFilled` Event payload 中，不复制成第二个当前权威。

### 身份与审计

每个 proof 至少冻结：

```text
ticket_id
netting_domain_key
model_id
snapshot_digest
maintenance_margin_brackets_digest
owner_policy_version
actual fill quantity
actual fill price
initial stop price
result status
projected root / distance / ratio
observed_at_ms
```

因此 Review 可以解释“这笔仓位为什么继续运行或为什么受控平仓”，而不需要
读取 Markdown、旧代码或当前交易所状态。

## Incident 与 Monitor

新增 Incident kind：

```text
post_fill_risk_evidence_unavailable
post_fill_risk_facts_contradictory
```

两者的 `entry_block_scope` 都是 `account_capacity`，key 为精确
`venue_id:account_id`。它们阻止新 ENTRY，但不移除既有 Ticket 的保护、退出、
Reconciliation、Settlement 或 Review 权限。

Monitor 至少区分：

| Monitor code | 含义 | Owner 动作 |
| --- | --- | --- |
| `venue_liquidation_observation_zero` | 原始报告为 `0`，不用于风险决策 | 无立即动作 |
| `venue_liquidation_observation_direction_invalid` | 原始报告与当前 Side 方向矛盾 | 无立即动作；保留审计 |
| `post_fill_risk_evidence_unavailable` | 完整账户级 proof 暂时不可得 | Entry 自动阻断；代理汇报 |
| `post_fill_risk_facts_contradictory` | 完整 facts 自相矛盾 | Owner action required |
| `post_fill_liquidation_proof_unsafe` | 权威计算证明不安全 | 系统受控平仓 |

不建设推送平台。Monitor 写入 PostgreSQL，由代理在运行复核时汇报。
`direction_invalid` 仅表示该观测**不能作为当前 Side 的方向性清算证据**，
不宣称 Binance 返回数据损坏。

## 性能边界

### 频率

额外账户级读取只发生在：

- 新 CapacityClaim；
- ENTRY dispatch 前；
- 每个完整 Entry Fill 后的一次复核；
- 复核事实不可用时的有界重试。

正常 protected、TP1、runner、Settlement 和 Review 不重复计算清算 proof。

### 限制

```text
post_fill snapshot timeout <= worker timeout
post_fill retry interval >= reconciliation poll interval
one actionable Ticket per reconciliation tick
exact instrument position rows only
zero history scan
zero runtime report file
```

分段求根复杂度由单一合约的两个 Side 和维护保证金分档数决定，不随 Ticket
历史、Universe 成员数或交易记录数量增长。

## 删除与替换

实施时必须删除或替换：

1. `PostFillRiskRequest.current_liquidation_price`；
2. `PostFillRiskDecision.actual_liquidation_*`；
3. `PositionSnapshot.liquidation_price` 作为风险权威的语义；
4. `_position_details()` 中将 `0` 转成 missing 的逻辑；
5. `capacity_sizing.py` 与 `revalidate_entry_dispatch.py` 内重复的清算公式；
6. 测试中的 `safe_liquidation_price()` 人工夹具；
7. “missing reported liquidation -> flatten” 的旧测试语义；
8. 聚合表中的旧 `actual_liquidation_*` projection。

不得增加：

- `legacy`、`compat` 或历史字段 alias；
- 双读、双写或新旧公式 fallback；
- 将 one-way/isolated 作为事故修补路径；
- 直接数据库 DML 伪造 proof 或 Ticket 终态；
- 第二个风险 worker、第二条订单链或文件证明。

## 失败矩阵

| 失败 | 新 ENTRY | 已成交 Ticket | Exchange mutation |
| --- | --- | --- | --- |
| Claim 前账户事实缺失 | 拒绝 | 不存在 | 无 |
| Dispatch 前 proof 缺失/矛盾 | 终态拒绝 | 尚未成交 | 无 ENTRY |
| 账户为 Multi-Assets、Portfolio Margin 或非 USDT 单资产模式 | 拒绝 | 保持现有 Stop；打开账户级 Incident | 无新增 mutation |
| Entry outcome unknown | 保持现有 unknown recovery | 精确对账 | 禁止盲重发 |
| Entry 完整成交，Stop 事实正常 | 暂由 Entry Lane 阻断 | 先安装 Stop | durable Initial Stop |
| Stop 方向错误 | 阻断 | 立即平仓 | durable Controlled Flatten |
| Stop Risk 超硬上限 | 阻断 | 先保护后平仓 | Stop 后 durable Flatten |
| Stop 已确认，risk snapshot 超时 | account-capacity block | 保持保护，无 TP1 | 无新增 mutation |
| Snapshot facts contradictory | account-capacity block | 保持保护，无 TP1 | 无新增 mutation |
| Canonical proof unsafe | account-capacity block | 保护后受控平仓 | durable Controlled Flatten |
| Canonical proof safe | 正常释放 Entry Lane | 进入 TP1/runner | durable TP1 |
| Venue raw price 为 `0` 或方向错误 | 不单独阻断 | 按 canonical proof 行动 | raw 值不能产生 command |

## 发布与 Fix-Forward

本修复与 StrategyUniverse、Settlement/Review 公平性、订单归因、GTX 和 BNB
费用修复组成同一个候选版本，但各自保留独立测试证据。

发布必须满足：

1. 生产 Entry 保持 fenced；
2. 所有持仓与订单外部闭环；
3. 所有 Ticket、Incident、Settlement 和 Review 内部闭环；
4. 外部与内部闭环证据满足后，通过官方 flat-runtime reset 清理旧实验事实；
5. `0002` 与 `0003` 的 empty-runtime schema preflight 通过；
6. 旧 worker 全部停止，目标 commit/schema 唯一；
7. 先启动 Observation、Lifecycle、Reconciliation；
8. PostgreSQL、账户模式、Cross、固定 `5x`、Universe 和服务身份只读认证；
9. Owner 单独确认后才允许以 `--enable-entry` 启动 Entry。

账户模式认证必须明确证明
`standard_futures_single_asset + USDT settlement + independent_sides + cross`；
只证明 Hedge Mode、Cross 或 `5x` 中的任意一项都不充分。

Schema 与 Event 语义是 forward-only。发布失败时保持 Entry fence，恢复三个
安全 worker 的目标或已认证源版本进行 fix-forward；不回退到依赖
`positionRisk.liquidationPrice` 的旧 Entry-capable 版本。

## 设计验收标准

本文档被 Owner 确认前，不开始编码。确认后的实现必须证明：

1. ETH `liquidationPrice = 0` 不再直接生成 Controlled Flatten；
2. AVAX 方向错误的正数不再直接生成 Controlled Flatten；
3. Claim、dispatch 和 post-fill 使用同一 Domain 投影器；
4. 实际 canonical proof 不安全时仍能保护后平仓；
5. risk facts unavailable 时 Initial Stop 保留、Entry 阻断、TP1 不提交；
6. Long/Short 同合约共存时两个 Side 都进入账户函数；
7. 每个决定可由 snapshot/model/bracket/policy/fill/stop 身份复算；
8. 无新执行链、无兼容胶水、无运行文件权威；
9. PostgreSQL 集成、完整生命周期、多仓位、失败恢复、性能和静态门全部通过；
10. Multi-Assets、Portfolio Margin 和非 USDT 单资产账户 fail closed；
11. BNB 始终只作为手续费资产，不进入 liquidation proof；
12. Tokyo Entry 仅在独立 Owner 确认后恢复。
