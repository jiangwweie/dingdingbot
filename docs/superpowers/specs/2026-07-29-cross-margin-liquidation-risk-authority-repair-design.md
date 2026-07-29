---
title: Cross-Margin Stop-Stress Authority Repair Design
status: PROPOSED_OWNER_REVIEW
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-29
revision: 2
supersedes_revision: 1
---

# Cross-Margin Stop-Stress Authority Repair Design

## 决策门

本文档是对 revision 1 的完整替换。它采用 Owner 已确认的审查结论：

> **删除“内部清算价求根”，改为账户级 Cross Margin Stop 压力证明。**

本轮只修改设计和测试设计，不授权生产代码、PostgreSQL、Tokyo 服务或交易所
写入。文档仍是 `PROPOSED_OWNER_REVIEW / NOT_CURRENT_AUTHORITY`。Owner 确认
本次修订后，才能编写实施计划并进入本地 RED/GREEN/REFACTOR。

生产 Entry 必须保持 fenced，直到本地完整验收、旧持仓闭环、flat-only 迁移
前置条件、Tokyo action-time 认证全部通过，并获得独立的 Owner 恢复确认。

## 核心结论

当前 P0 的根因是把 Binance `positionRisk.liquidationPrice` 当成当前 Hedge
Side 的独立、可直接决策的清算价。ETH 返回 `0`、AVAX Long 返回高于入场价的
正数，均导致程序在 Initial Stop 确认后主动 Controlled Flatten。

修复后的唯一风险决策是：

```text
同一 AccountRiskSnapshot + InstrumentRulesFacts
-> 同一 CrossMarginStressProof
-> CapacityClaim
-> ENTRY dispatch
-> post-fill recheck
```

压力证明不猜测交易所真实清算价。它回答一个更直接、可验证的问题：

> 在其他合约价格保持 action-time snapshot 不变时，当前账户能否从当前价格
> 承受到 Initial Stop，并继续承受到 Policy 指定的 Stop 外压力边界，而始终
> 保持 margin balance 大于 maintenance margin。

Binance 报告的 liquidation price 只保留为原始仓位观测，不能创建任何
Exchange Command。

## 已知客观事实

### 当前错误链

```text
PositionSnapshot.liquidation_price
-> PostFillRiskRequest.current_liquidation_price
-> liquidation_safety_degraded
-> InitialStopConfirmed
-> ControlledFlatten
```

| 事实 | 当前代码证据 |
| --- | --- |
| `EntryFilled` 直接消费仓位 snapshot 的 liquidation 值 | [`reconcile_ticket.py`](../../../src/trading_kernel/application/reconcile_ticket.py#L103) |
| 缺失或不在 Stop 外的值被判为不安全 | [`post_fill_risk.py`](../../../src/trading_kernel/domain/post_fill_risk.py#L140) |
| Adapter 当前把原始 `0` 转成 missing | [`venue_adapter.py`](../../../src/trading_kernel/infrastructure/venue_adapter.py#L1681) |
| Claim 和 dispatch 各自实现清算公式 | [`capacity_sizing.py`](../../../src/trading_kernel/domain/capacity_sizing.py#L407)、[`revalidate_entry_dispatch.py`](../../../src/trading_kernel/application/revalidate_entry_dispatch.py#L380) |
| Aggregate 保存含义混合的 `actual_liquidation_*` | [`0001_initial.py`](../../../migrations/trading_kernel/versions/0001_initial.py#L620) |

### 当前可复用边界

当前 Kernel 已经具备：

- `EntryAdmissionSnapshot` 的账户余额、保证金、持仓、账户模式和摘要；
- `InstrumentRulesFacts` 的维护保证金分档和 digest；
- action-time Claim 与 dispatch 双重复核；
- Initial Stop、TP1、runner、Controlled Flatten 和 durable Command；
- account-capacity Incident 和全局 Entry serialization；
- Reconciliation 的持仓读取、due-at 调度和 closure starvation guard；
- PostgreSQL Event、Aggregate、Command、Settlement 和 Review 链。

本设计只替换风险事实和风险决策，不创建第二条执行链。

## 方案选择

| 方案 | 风险语义 | 复杂度 | 决策 |
| --- | --- | ---: | --- |
| 继续计算 projected liquidation root | 容易被误解为交易所清算价 | 高 | 拒绝 |
| 只保留实际 Stop Risk | 无成交后账户级压力复核 | 低 | 拒绝 |
| **Stop 外压力区间证明** | 直接验证策略所需安全空间 | 中 | **采用** |
| 禁止 Hedge Mode 或改 one-way | 不能关闭 Cross 字段权威错误 | 高 | 拒绝 |

## 不改变的业务语义

```text
position mode  = independent_sides
margin mode    = cross
leverage       = exchange configured fixed 5x
Netting Domain = venue + account + instrument + position_side
```

- 一个 Exposure Episode 对应一个 immutable Ticket；
- 禁止向已有仓位加仓；
- 一个 Ticket 只有一个 ENTRY generation；
- 新 Entry 全局串行；
- Long/Short 是独立 Netting Domain，可以同时存在；
- Existing Ticket 的保护、退出、Reconciliation、Settlement、Review 并发；
- raw venue liquidation observation 不拥有交易权限；
- 相关性和多资产联合压力测试仍不属于本次范围。

## 权威模型

### 单一账户风险事实

新增一个冻结的 Domain 边界模型：

```python
class AccountRiskPosition(BaseModel):
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    quantity: Decimal
    average_entry_price: Decimal
    current_unrealized_pnl: Decimal
    current_maintenance_margin: Decimal


class AccountRiskSnapshot(BaseModel):
    venue_id: str
    account_id: str
    account_risk_mode: Literal["standard_usdm_single_asset"]
    settlement_asset: Literal["USDT"]
    position_mode: Literal["independent_sides"]
    margin_mode: Literal["cross"]
    exchange_instrument_id: str
    mark_price: Decimal
    total_margin_balance: Decimal
    total_maintenance_margin: Decimal
    current_instrument_positions: tuple[AccountRiskPosition, ...]
    observed_at_ms: int
    valid_until_ms: int
    snapshot_digest: str
```

事实语义：

1. `total_*` 来自同一次账户快照；
2. 当前精确合约 Long/Short 的 UPNL 和 maintenance margin 也来自该快照；
3. 不使用本地公式反推需要从账户总值中扣除的当前仓位值；
4. raw `liquidationPrice` 不进入 snapshot 或 digest。

Typed invariants：

- quantity、entry、mark 必须 finite 且为正；
- current unrealized PnL 和 total margin balance 允许 finite signed value；
- current/total maintenance margin 必须 finite 且非负；
- 同一 instrument+Side 只能有一行；
- 当前仓位 maintenance sum 大于账户 total maintenance、扣减后的 base
  maintenance 为负或 identity/quantity 交叉验证不一致，均为
  `facts_contradictory`；
- 当前 `margin_surplus <= 0` 是真实 `failed`，不能伪装成 facts unavailable。

维护保证金 bracket 继续由现有 `InstrumentRulesFacts/InstrumentRulesSource`
负责。账户事实和产品规则各有一个权威，Domain Request 显式组合二者，禁止
把规则复制进 Account Snapshot。`InstrumentRulesFacts` 增加
`notional_coefficient`，其 rules digest 同时绑定 coefficient 和 bracket
payload。

Binance USD-M Account API 提供 `multiAssetsMargin`、账户总保证金以及仓位级
`unrealizedProfit / maintMargin`。这些字段是 Adapter 映射的外部依据：
[Binance USD-M Account API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account#account-information-v2)。

### 账户模式硬边界

该模型只接受：

```text
adapter identity  = standard Binance USD-M Futures
multiAssetsMargin = false
settlement asset  = USDT
position mode     = independent_sides
margin mode       = cross
```

热路径不得额外调用高权重 Multi-Assets 查询来重复确认同一事实：

- `multiAssetsMargin` 从已经读取的 USD-M Account response 获取；
- Portfolio Margin 由 Adapter/runtime profile 身份排除，不调用 Portfolio
  API 猜测；
- settlement asset 从已认证 Instrument Rules/Catalog 获取；
- Position Mode 复用现有 action-time 读取；
- 精确合约 margin mode 和固定 `5x` 复用现有 symbol facts。

Multi-Assets、Portfolio Margin、非 USDT settlement、One-way、Isolated 或
非 `5x` 均 fail closed。BNB 余额和手续费折扣不进入 margin balance、抵押物或
压力证明。

账户模式、margin mode 和 leverage mismatch 只写 PostgreSQL
Incident/Monitor 并由代理提醒 Owner；本修复不自动切换模式、设置杠杆、
购买 BNB 或执行资产划转。

### Adapter 读取计划

一次 AccountRiskSnapshot 使用有界、明确的只读来源：

| 来源 | 用途 |
| --- | --- |
| `/fapi/v2/account` | 同一 response 的 `multiAssetsMargin`、账户 totals、目标合约各 Side UPNL/MM |
| 精确 symbol `positionRisk` | mark、entry、quantity、Side、Cross、leverage、raw liquidation observation |
| Position Mode endpoint | `independent_sides` |
| InstrumentRulesSource | settlement、bracket、coefficient、rules digest |

Adapter 必须交叉验证 account position 与精确 `positionRisk` 的 symbol、Side、
quantity 和 entry。任何不一致都属于 facts contradictory。不得使用
`fetch_balance + fetch_positions` 分别拼出两个时间窗口，再假装它们是同一次
账户基准。

## Stop 压力证明

### Policy 语义

删除旧字段：

```text
min_liquidation_distance_to_stop_distance_ratio
```

新增：

```text
post_stop_stress_multiple
```

当前批准数值继续为 `2.0`，但语义改为：

> 账户不仅要承受到 Initial Stop，还要能继续承受两个 Stop Distance 的不利
> 价格变化。

这不是历史字段 alias，也不存在双读。flat-only seed 只写新字段。

### 压力边界

```text
stop_distance = abs(reference_entry_price - initial_stop_price)

Long raw_stress_price
    = initial_stop_price - post_stop_stress_multiple * stop_distance

Short stress_price
    = initial_stop_price + post_stop_stress_multiple * stop_distance
```

Long 的原始压力价格低于零时，将最终边界限制在自然价格下界 `0`，并在 proof
中冻结 `stress_boundary_clamped_to_zero=true`。不使用极小正数、无限价格或
虚构 liquidation root。

### 当前与候选仓位分离

`AccountRiskSnapshot.current_instrument_positions` 是交易所当前事实。
`CrossMarginStressRequest.projected_instrument_positions` 表示本次决策需要评估
的精确合约仓位：

- Claim：当前相反 Side 加拟议新仓位；
- Dispatch：当前相反 Side 加 Ticket 数量和 action-time entry reference；
- Post-fill：交易所实际 Long/Short 仓位，目标 Side 必须与 fill quantity 和
  average fill price 一致。

因此基准为：

```text
base_margin_balance
    = total_margin_balance
      - sum(current exact-instrument unrealized PnL)

base_maintenance_margin
    = total_maintenance_margin
      - sum(current exact-instrument maintenance margin)
```

对于候选价格 `P`：

```text
projected_long_upnl  = quantity * (P - average_entry_price)
projected_short_upnl = quantity * (average_entry_price - P)

account_margin_balance(P)
    = base_margin_balance + sum(projected exact-instrument UPNL)

account_maintenance_margin(P)
    = base_maintenance_margin
      + sum(projected exact-instrument maintenance margin at P)

margin_surplus(P)
    = account_margin_balance(P) - account_maintenance_margin(P)
```

拟议纯 Domain 输入为：

```python
class StressPosition(BaseModel):
    position_side: Literal["long", "short"]
    quantity: Decimal
    average_entry_price: Decimal


class CrossMarginStressRequest(BaseModel):
    account_snapshot: AccountRiskSnapshot
    maintenance_margin_brackets: tuple[MaintenanceMarginBracket, ...]
    maintenance_margin_brackets_digest: str
    notional_coefficient: Decimal
    evaluated_side: Literal["long", "short"]
    reference_entry_price: Decimal
    initial_stop_price: Decimal
    post_stop_stress_multiple: Decimal
    projected_instrument_positions: tuple[StressPosition, ...]
```

`InstrumentRulesFacts` 属于 Application 事实边界，纯 Domain 不导入
Application。Application 只把其中已经 typed 的 bracket、digest 和 coefficient
作为明确字段传入 request，不创建第二个规则 DTO。

### 维护保证金

```text
maintenance_margin(notional)
    = notional * maintenance_margin_rate - maintenance_amount
```

`maintenance_amount` 对应 Binance bracket `cum`。该公式以 Binance 官方
[Clearing Procedures](https://bin.bnbstatic.com/static/cms/cg08ou2ak0tn7mcplvfg/file/53197b612332da02c20b5b7d19b81ff53ee5f4938c6330c72a30a1ca4f91049f.pdf)
为外部语义依据。

Adapter 必须保存并认证任何影响 bracket 的 symbol-level coefficient。Domain
只消费 Adapter 已认证的有效 bracket schedule，不自行猜测 coefficient 如何
变换 floor/cap/cum。没有官方语义和真实只读 payload 回放证明的非默认
coefficient 必须使 Instrument Certification 进入 `OWNER_ACTION_REQUIRED`。
gap、重叠、未排序或不唯一 bracket 同样拒绝，禁止静默忽略。

### 有限检查点

Domain 不求根。它只计算：

1. 当前 mark price；
2. Initial Stop；
3. 最终 stress price；
4. 当前 mark 到 stress price 之间，每个 projected Side 的所有 bracket
   floor/cap 对应价格。

每个 bracket 区间内 `margin_surplus(P)` 是线性的，因此区间最小值一定出现在
端点。所有候选点按 `Decimal` 精确计算、去重和排序。

通过条件：

```text
当前 mark 位于 Initial Stop 的保护侧
AND 当前账户 margin_surplus > 0
AND 区间内每个检查点 margin_surplus > 0
```

### Proof

```python
class CrossMarginStressProof(BaseModel):
    model_id: Literal["cross-margin-stop-stress-v1"]
    snapshot_digest: str
    maintenance_margin_brackets_digest: str
    status: Literal["passed", "failed", "facts_contradictory"]
    stress_price: Decimal
    stress_boundary_clamped_to_zero: bool
    minimum_margin_surplus: Decimal | None
    minimum_margin_surplus_price: Decimal | None
    evaluated_point_count: int
    proof_digest: str


class CrossMarginStressEvidence(BaseModel):
    request: CrossMarginStressRequest
    proof: CrossMarginStressProof
```

`facts_unavailable` 不是 Domain 结果。超时、缺行和外部读取失败由 Application
表示；只有完整 typed snapshot 才能调用 Domain。

`proof_digest` 绑定完整 request 和 result。CapacityClaim 与
`PostFillStressAssessed` 保存 exact `CrossMarginStressEvidence` JSONB，而不是
只保存无法复算的 digest。Repository 必须按精确 Pydantic schema
serialize/deserialize，禁止任意字典。

`facts_contradictory` 不授予继续交易或平仓权限。它保持 Initial Stop，阻止新
Entry 并等待 Owner action/retry。

`minimum_margin_surplus` 仅在 `passed/failed` 时存在；contradictory proof
只保存矛盾原因和 digest，不输出虚构数值。

## 三次复用

| 阶段 | 输入 | 失败语义 |
| --- | --- | --- |
| CapacityClaim | 当前账户事实 + hypothetical position + reference entry | 不创建 Ticket/Command |
| ENTRY dispatch | 新鲜 action-time facts + Ticket quantity | ENTRY 终态拒绝 |
| Post-fill | 实际 fill + 当前实际仓位 + 已确认 Initial Stop | 保持 Stop 或保护后 Flatten |

三处必须调用同一个 `evaluate_cross_margin_stress()`。禁止在
`capacity_sizing.py`、`revalidate_entry_dispatch.py` 或 Reconciliation 中
复制公式。

## 共享事实端口

### 边界

在 `application/runtime_facts.py` 定义：

```python
class AccountRiskSnapshotRequest(BaseModel):
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    observed_at_ms: int
    valid_for_ms: int


class AccountRiskSnapshotSource(Protocol):
    async def read_account_risk_snapshot(
        self,
        request: AccountRiskSnapshotRequest,
    ) -> AccountRiskSnapshot: ...
```

Ticket identity 属于 Application 调度上下文，不进入外部账户事实请求或
snapshot digest。

`EntryAdmissionSnapshot` 组合：

```text
AccountRiskSnapshot
+ quote
+ open orders
```

Kernel ownership、Incident 和 readiness 仍由 Application 从 PostgreSQL
分别读取，不塞入 venue snapshot。`EntryAdmissionSnapshot` 不再复制账户
balance、mode 和 position 字段。Claim 和 Dispatch 使用组合 snapshot；
Post-fill 并发读取窄的 AccountRiskSnapshot port 与现有 InstrumentRules port。

Infrastructure 只能有一个 `_read_account_risk_snapshot()` 解析实现。Entry
composite reader 和 Post-fill reader复用它，不允许两个 DTO、两个账户字段
映射或 Application 层 copy adapter。

### I/O 与事务

网络读取发生在 PostgreSQL 事务外，受统一 timeout 控制。成功后：

```text
lock exact Ticket
-> verify expected Aggregate version/status
-> append at most one result Event
-> update Aggregate
-> resolve/open exact Incident
-> persist at most one durable Command
-> commit
```

随后才允许 dispatch Exchange Command。

## Post-Fill 生命周期

### 顺序

```text
EntryFilled
-> actual Stop Risk
-> durable Initial Stop
-> InitialStopConfirmed
-> POST_FILL_RISK_PENDING
-> AccountRiskSnapshot
-> PostFillStressAssessed
-> TP1 OR Controlled Flatten
```

`EntryFilled` 冻结：

- fill quantity 和 average fill price；
- actual Stop Risk 和 Stop 方向；
- raw `venue_reported_liquidation_price`；
- position observation time。

它不包含 Cross Margin Stress Proof。

### 状态与事件

只新增一个 Aggregate 状态：

```text
post_fill_risk_pending
```

只新增一个 Trade Event：

```text
PostFillStressAssessed(status = passed | failed)
```

完整 evidence 作为冻结 Pydantic payload 持久化。事实暂不可用或矛盾不会创建
Trade Event，因为 Ticket 生命周期没有发生变化。

### 决策

| 输入 | Ticket 行为 | Entry 权限 |
| --- | --- | --- |
| Stop 方向错误 | 立即 durable Controlled Flatten | 保持阻断 |
| actual Stop Risk 超硬上限 | 先 Stop，后 durable Flatten | 保持阻断 |
| facts unavailable | 保持 Stop、无 TP1、重试 | account-capacity Incident |
| facts contradictory | 保持 Stop、无 TP1、Owner action | account-capacity Incident |
| stress passed | 释放 Entry Lane，准备 TP1 | 正常恢复 |
| stress failed | 保持 Stop，准备 durable Flatten | 直到 external flat 持续阻断 |

`post_fill_stress_failed` Incident 必须在 Controlled Flatten 全部闭环、外部 flat、
无 residual order 后才解决。不能在创建 Flatten Command 时提前释放账户风险
阻断。

### 暂时失败不是 Event

facts unavailable/contradictory 使用一个短事务：

```text
lock exact pending Aggregate
-> idempotent upsert Incident
-> upsert PostgreSQL Monitor current state
-> schedule reconciliation_due_at_ms
-> commit
```

没有 Event spam，没有 Command，没有 Aggregate version伪推进。恢复后
`PostFillStressAssessed` 与 Incident resolve 在结果事务中原子提交。

## Reconciliation 调度

Post-fill risk 继续由现有 Reconciliation worker 负责：

- `post_fill_risk_pending` 加入现有 `RECONCILIATION_POSITION_STATUSES`；
- 只使用现有 `get_next_reconciliation_work()`；
- 复用 `reconciliation_due_at_ms`、`FOR UPDATE SKIP LOCKED` 和精确 Ticket；
- facts unavailable 的 retry interval 不短于 worker poll interval；
- overdue Settlement/Review 继续由 `closure_starvation_limit_ms` 获得更高
  priority；
- 不新增 worker、queue、timer 或 worker 内第二个提前返回调度器。

## 原始 liquidation observation

将含义混合的 `PositionSnapshot.liquidation_price` 重命名为：

```text
venue_reported_liquidation_price
```

Adapter 必须原样保留可解析值：

- `"0"` 保存为 `Decimal("0")`；
- 方向与当前 Side 不一致的正数原样保存；
- 缺失与非法数字明确区分；
- 不取绝对值、不翻转方向、不用 fallback 修正。

raw observation 缺失或无法解析只产生审计 Monitor；只要同一 position row 的
Side、quantity、entry、mark、margin mode 和 leverage 仍可认证，就不能阻止
canonical AccountRiskSnapshot 或 stress proof。

该字段可进入 Position current projection、`EntryFilled` 和 Monitor，但不能
进入 AccountRiskSnapshot、Proof digest、reducer command effect 或 Entry
readiness。

## PostgreSQL 与审计

### Flat-only migration

新增拟议 schema head：

```text
0003_cross_margin_stop_stress
```

Owner 已明确新版本部署前等待外部和内部闭环，旧 Ticket 历史无需兼容。因此
迁移要求 runtime/trade tables 全空：

- 活跃或 terminal Ticket 均阻断；
- Event、Command、Position、Incident、Settlement、Review 任一存在均阻断；
- 官方 flat-runtime reset 后迁移；
- 不 backfill、不翻译 Event、不保留旧字段 alias。

### 删除

删除所有：

```text
actual_liquidation_*
projected_liquidation_*
min_liquidation_distance_to_stop_distance_ratio
PostFillRiskRequest.current_liquidation_price
safe_liquidation_price test helpers
```

### 最小持久化

| 位置 | 保存内容 |
| --- | --- |
| Owner Policy | `post_stop_stress_multiple` |
| CapacityClaim | 完整 pre-entry `CrossMarginStressEvidence` payload |
| Ticket | model id、stress multiple、Claim proof digest |
| Aggregate | `post_fill_stress_status`、`post_fill_stress_proof_digest` |
| `PostFillStressAssessed` | 完整 post-fill evidence、fill、Stop、Policy 身份 |
| Position/Event | raw venue liquidation observation，仅审计 |

Evidence payload 使用 exact Pydantic schema 序列化；禁止任意 `dict`、Markdown
或本地文件作为审计权威。

## Incident 与 Monitor

| Kind/code | 类型 | 行为 |
| --- | --- | --- |
| `post_fill_risk_facts_unavailable` | Incident + Monitor | 自动重试，阻止 account Entry |
| `post_fill_risk_facts_contradictory` | Incident + Monitor | Owner action，阻止 account Entry |
| `post_fill_stress_failed` | Incident + Monitor | 保护后平仓，flat 后解决 |
| `venue_liquidation_observation_zero` | Monitor warning | 仅审计 |
| `venue_liquidation_observation_not_side_directional` | Monitor warning | 仅表示不能作为 Side 权威 |
| `venue_liquidation_observation_unavailable` | Monitor warning | raw 字段缺失，仅审计 |
| `venue_liquidation_observation_invalid` | Monitor warning | raw 字段无法解析，仅审计 |

不建设推送平台。Monitor 写入 PostgreSQL，由代理汇报。

## 性能边界

| 项目 | 约束 |
| --- | --- |
| Domain CPU | O(projected sides + bracket boundaries) |
| Claim/Dispatch | 每次各一个 bounded AccountRiskSnapshot |
| Post-fill | 正常只读取一次；失败按 due-at 有界重试 |
| Account mode | 从同一次 account response 读取，不增加 Multi-Assets 热路径调用 |
| PostgreSQL | 精确 Ticket lock；无历史扫描 |
| Runtime | 不新增 worker/timer/queue |
| 文件 | 正常和 retry cadence 零 JSON/Markdown |

Universe 目标 8、硬上限 10 不改变风险证明复杂度。计算只与当前精确合约的
两个 Side 和 bracket 数量相关。

## 删除与禁止

实施必须删除旧公式和旧测试语义，不允许：

- legacy/compat module 或 alias；
- 双读、双写、旧 schema fallback；
- root solver 与 stress proof 并存；
- 独立 Post-fill Adapter 字段映射；
- unavailable Trade Event；
- 第二个 Reconciliation selector；
- DML 伪造 Ticket、Proof 或终态；
- 以 one-way/isolated 规避本问题；
- raw liquidation observation 创建 Command。

## 发布与 Fix-Forward

发布顺序保持：

1. Entry fenced；
2. 旧持仓、订单、Incident、Settlement、Review 全部闭环；
3. 外部 flat、无 residual order；
4. 官方 flat-runtime reset；
5. `0002`、`0003` empty-runtime preflight；
6. 停旧 writer，切换唯一 commit/schema；
7. 先启动 Observation、Lifecycle、Reconciliation；
8. 只读认证账户 identity、standard USD-M single-asset、USDT settlement、
   independent sides、Cross、固定 `5x`、Universe 和 Instrument Rules；
9. Entry 继续 fenced；
10. Owner 独立确认后才允许 `--enable-entry`。

发布失败保持 Entry fence 并 fix-forward。不得回退到 raw
`positionRisk.liquidationPrice` 可触发平仓的 Entry-capable 版本。

## 设计验收标准

实现前，本设计必须被 Owner 再次确认。实现完成必须证明：

1. ETH raw `0` 和 AVAX not-side-directional 值不能创建 Flatten；
2. Claim、Dispatch、Post-fill 使用同一 AccountRiskSnapshot 和 stress
   evaluator；
3. 当前仓位基准使用交易所 UPNL/MaintMargin，不混用本地反算；
4. Stress failed 仍能 Initial Stop 后受控平仓；
5. facts unavailable/contradictory 保持 Stop、阻止 Entry、无 Event spam；
6. Long/Short 同合约共存时两个 Side 都进入压力函数；
7. Reconciliation 公平调度不回归 Settlement/Review 饥饿；
8. Aggregate 只保存最小当前投影，完整证据保存在 immutable Claim/Event；
9. 无 root solver、无旧 liquidation authority、无兼容胶水、无第二执行链；
10. PostgreSQL、完整生命周期、多仓位、失败恢复、性能和静态门全部通过；
11. Tokyo 部署与恢复 Entry 分别等待 Owner 确认。
