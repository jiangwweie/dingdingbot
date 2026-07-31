---
title: SOR_V3_STRATEGY_GROUP_CAPACITY_COMPATIBLE_MIGRATION_DESIGN
status: OWNER_APPROVED_FOR_IMPLEMENTATION
date: 2026-07-31
---

# SOR v3、同策略两仓与 Flat 兼容迁移设计

## 决策

本次采用一个版本化、前向兼容的结构性修复：

1. 保留 **SOR Opening Range Breakout** 的有效突破交易逻辑；
2. 以 **`SOR-001 v3`** 替换 v2 的持续状态式 Signal 生产；
3. 仅对新的 v3 Ticket 增加 TP1 前 failed-breakout、Session invalidation 和 time-stop；
4. 在 Owner Policy、CapacityClaim、Entry Preflight 和 Ticket 原子提交四处共同执行 **同一 StrategyGroup 最多两个 Active Ticket**；
5. PostgreSQL 从当前 v4 schema 通过增量 Alembic revision 前向升级，不再要求清库重建；
6. PostgreSQL 中现有 Ticket、事件、Command、Reservation 和 Review lineage 全部保留；当前错误语义 exposure 必须在部署前通过官方 Lifecycle 全部终结，schema migration 只在 exchange/internal flat 状态执行；
7. 迁移后仍只有一条 Trading Kernel 执行链，不增加双写、旧表读取、schema fallback 或平行 worker。

本次不修改 Owner 已批准的账户资本边界：

```text
max_concurrent_tickets = 3
max_strategy_group_concurrent_tickets = 2
max_ticket_stop_risk_fraction = 0.03
max_gross_stop_risk_fraction = 0.06
max_ticket_initial_margin_fraction = 0.45
max_gross_initial_margin_utilization = 0.90
configured_exchange_leverage = 5
max_leverage = 10
margin_mode = cross
```

### Owner 持仓与历史证据决定

**数据库兼容迁移**与**活跃持仓兼容切换**是两个不同边界：

- schema 必须前向迁移，保留全部历史 Ticket 和 append-only lineage；
- Owner 所指的三笔当前 exposure 均来自错误的 SOR v2 持续状态语义，不作为
  SOR v3 有效入场样本，也不跨 schema 保留为活跃仓位；
- 部署前先 Entry fenced，再由官方 Lifecycle durable-command path 对仍活跃的
  exact Ticket 自然或受控终结；
- cutover 必须等待 position/order external flat、Ticket terminal、Reservation 和
  Netting Domain released、Settlement/Review complete、零 unresolved Command 和
  零 open Incident；
- 之前已经终结且具有 Runner/右尾价值的 BNB Ticket 作为历史证据原样保留，
  不重新建仓、不重写 Signal/Ticket identity；
- BNB 的入场只有在历史 closed candle 重建证明首次边沿穿越后，才可计入 SOR v3
  entry evidence；重建前只计入 Lifecycle/Runner/right-tail evidence；
- 当前三笔终结后的 Review 必须标记错误入场语义，并从 SOR v3 entry-alpha
  统计中排除，但继续保留执行、保护、退出和经济结果证据。

本次文档更新不授权立即平仓、撤单或修改任何现有保护订单；实际终结动作仍必须
经过部署执行计划和官方 durable-command Lifecycle 路径。

## 已知客观事实

### 当前 SOR v2 Signal

当前 detector 将以下持续状态识别为突破：

```python
latest.close > range_high and latest.close >= previous.close
```

它不要求上一根仍位于 Range 内，因此突破后的多根上涨 K 线均可产生新 Signal。生产事实已经出现同一 Session 中跨七个币种的重复 SOR-LONG Signal。

### 当前生命周期

`POSITION_PROTECTED` 且 TP1 尚未成交时，Lifecycle 直接返回 `NO_CHANGE`。市场失效和 time-stop 仅在 `RUNNER_PROTECTED` 阶段评估。

### 当前容量

Owner Policy 只有账户级 `max_concurrent_tickets=3`，没有 StrategyGroup 级限制。CapacityClaim 也没有冻结同策略当前数量和政策上限。

### 当前数据库与版本

当前 schema 只有 `0001_trading_kernel_baseline_v4`。Registry model 将所有 canonical contract 强制为 v2；`brc_event_specs.event_id` 全局唯一，使同一 Event ID 的 v2 和 v3 无法同时保留。Lifecycle 按 active Event Spec 读取 Exit Policy，不能在 Event 退休后继续维护旧 Ticket。

## 问题模型

当前失败链如下：

```text
UTC Session Market Snapshot
-> price remains above Opening Range High
-> persistent state is mislabeled as a new breakout Event
-> repeated StrategySignal
-> earliest global arbitration
-> multiple SOR CapacityClaims across instruments
-> SOR consumes all three account Ticket slots
-> late entry still uses old Opening Range Low as hard Stop
-> TP1-before lifecycle cannot exit on failed breakout or Session invalidation
```

根因位于 Strategy Event 语义，但完整关闭问题还需要修复版本、Ticket 策略冻结、容量政策和数据库演进边界。

## 备选方案

| 方案 | 内容 | 优点 | 不接受原因 |
| --- | --- | --- | --- |
| 修改 SOR v2 一行条件 | 将 `>` 改为首次穿越 | 改动最小 | 静默改变现有 v2 Ticket 的 Event 语义，缺少版本、Episode 和生命周期闭环 |
| 在 Entry 层过滤重复 SOR | 保留错误 Signal，Entry 特判 | 不改 detector | 策略逻辑泄漏到资本层，Signal lineage 继续错误 |
| **SOR v3 + 通用容量政策 + 兼容迁移** | 新版本 Event、冻结策略、同策略容量、增量 DDL | 单一权威、可审计、可保仓部署 | 推荐方案 |

## 产品语义

### SOR v3 Session

首版保持当前已被生产使用的 Session 锚点，不在修复中重新选择市场时区：

```text
session_start = UTC 00:00
opening_range = session 内前四根已关闭的 15m K 线
opening_range_end = UTC 01:00
session_end = 下一 UTC 00:00
signal_freshness = 15m
```

Session 起止必须进入版本化 detector 结果和 Signal lineage，不再仅作为 `_load_market_snapshot()` 内部整数除法。

### SOR-LONG v3

一个 Long Event 仅在全部条件成立时触发：

```text
opening_range 已由四根已关闭 15m K 线形成
previous.close <= opening_range_high
latest.close > opening_range_high
latest 是 trigger_candle_close_time_ms 对应的已关闭 K 线
trigger 位于同一 UTC Session
该 instrument + side + event_spec + session 尚无 Signal Episode
```

### SOR-SHORT v3

一个 Short Event 仅在全部条件成立时触发：

```text
opening_range 已形成
previous.close >= opening_range_low
latest.close < opening_range_low
latest 是已关闭 trigger candle
trigger 位于同一 UTC Session
该 instrument + side + event_spec + session 尚无 Signal Episode
```

### Signal 有效期

Signal 的 occurrence 是突破 K 线关闭时间，expiry 是 occurrence 后 **900,000ms**。Entry Lane 忙、政策不允许或其他事实导致 Signal 过期后，不允许使用同一 Session 的持续状态追价。

### Exposure Episode

新的 StrategySignal 必须冻结：

```text
exposure_episode_id = sha256(
  event_spec_id
  + exchange_instrument_id
  + position_side
  + session_start_ms
)
```

`brc_signal_events.exposure_episode_id` 建立唯一约束。CapacityClaim 和 Ticket 直接继承 Signal 的 Episode，不再由 Ticket ID 反向生成 Episode。

对于迁移前的 Signal，migration 使用：

```text
legacy:signal:<signal_event_id>
```

完成无冲突、非空、可追溯的精确回填。现有 Ticket 已冻结的旧 Episode ID 不重写。

## SOR v3 Fact Contract

SOR-LONG v3 Required Facts：

| Fact | 类型 | 角色 | 含义 |
| --- | --- | --- | --- |
| `opening_range_defined_v3` | boolean | condition | 四根 Opening Range 已关闭 |
| `breakout_edge_crossed_v3` | boolean | condition | 上一根未在区间上方，当前收盘首次穿越 |
| `opening_range_high_reference_v3` | decimal | lifecycle_reference | failed-breakout reclaim 边界 |
| `opening_range_low_reference_v3` | decimal | protection_reference | 交易所初始硬 Stop |
| `session_start_ms_v3` | decimal | identity_reference | UTC Session 身份组成部分 |
| `session_end_ms_v3` | decimal | lifecycle_reference | 最晚 Session invalidation 时间 |

SOR-SHORT v3 对称使用：

| Fact | 类型 | 角色 | 含义 |
| --- | --- | --- | --- |
| `opening_range_defined_v3` | boolean | condition | 四根 Opening Range 已关闭 |
| `breakdown_edge_crossed_v3` | boolean | condition | 上一根未在区间下方，当前收盘首次穿越 |
| `opening_range_low_reference_v3` | decimal | lifecycle_reference | failed-breakdown reclaim 边界 |
| `opening_range_high_reference_v3` | decimal | protection_reference | 交易所初始硬 Stop |
| `session_start_ms_v3` | decimal | identity_reference | UTC Session 身份组成部分 |
| `session_end_ms_v3` | decimal | lifecycle_reference | Session invalidation 时间 |

数值型时间以整数毫秒字符串进入 Decimal Fact validation，生产业务逻辑转换为正整数时必须验证无小数部分。

### Fact Role 扩展

当前 Registry 将 `condition` 和 `disable` 限定为 boolean，将
`protection_reference` 限定为 decimal。本次以通用、可复用的角色扩展代替
SOR 特判：

```text
condition             -> boolean，决定 Event 是否成立
disable               -> boolean，决定 Event 是否禁用
protection_reference  -> decimal，唯一初始硬保护参考
identity_reference    -> decimal，组成版本化 Event/Episode 身份
lifecycle_reference   -> decimal，冻结给 Ticket 生命周期使用
```

Registry validator 必须继续要求每个 Event 恰好一个
`protection_reference`；新角色不得被 detector 当作 boolean 满足条件，也不得被
Entry 层按 Fact 名称猜测。Contract 明确声明角色，Signal、Claim 和 Ticket 只按
版本化 Contract 翻译。

## Registry 版本边界

### Active contract

`registered_strategy_contracts()` 仍返回恰好六个当前 Active Event：

```text
CPM-LONG v2
MPG-LONG v2
MI-LONG v2
SOR-LONG v3
SOR-SHORT v3
BRF2-SHORT v2
```

### Retired historical contract

本次不新增 `retained_ticket_strategy_contracts()`。部署 hard gate 已要求所有 SOR v2
Ticket 在 migration 前 terminal、Settlement/Review complete，因此 target runtime
不需要加载 v2 detector 或 v2 lifecycle contract。

PostgreSQL 中现有 v2 Strategy Version、Event Spec、Exit Policy、Signal、Ticket、
Command、Settlement 和 Review 行继续作为 immutable history 保留。它们：

- 不参与新 Runtime Scope、Universe、Observation、Entry 或 Lifecycle；
- 不进入 Owner Policy `allowed_event_spec_ids`；
- 不被 target seed 删除、覆盖或重新解释；
- 终结后的通用 Trade Review revision 仍可按 Ticket/Review identity 追加，不需要
  恢复 v2 detector 或策略执行代码。

这保留的是数据 lineage，不是旧 runtime compatibility surface。

### PostgreSQL Registry 状态

迁移后：

| 对象 | v2 SOR | v3 SOR |
| --- | --- | --- |
| Strategy Version | `retired` | `active` |
| Event Spec | `retired` | `active` |
| Exit Policy | `retired`，仅历史审计读取 | `active` |
| Strategy Universe | 当前 v2 Universe 受控退休 | v3 从 Warming 原子切换 Active |
| New Signal | 禁止 | 允许 |
| Active Ticket lifecycle | migration 前必须为零 | 允许 |
| Terminal Review revision | 允许 | 允许 |

`brc_event_specs.event_id` 的全局唯一约束改为：

```text
UNIQUE(strategy_version_id, event_id)
```

## Exit Policy 冻结

当前 Ticket 只冻结 Event Spec，没有冻结 Exit Policy semantic hash。本次迁移增加：

```text
CapacityClaim.exit_policy_id
CapacityClaim.exit_policy_semantic_hash
TradeTicket.exit_policy_id
TradeTicket.exit_policy_semantic_hash
```

现有 terminal Claim/Ticket 通过 Event Spec 精确关联当前已有 Exit Policy 回填，
用于 immutable audit。新 Ticket 在 Claim 阶段冻结 exact policy identity/hash；
Lifecycle 必须按 Ticket 冻结值读取，不按 Registry 当前 active 状态猜测。这项冻结
解决未来 v3 -> v4 演进问题，不为已终结 v2 恢复运行时代码。

## SOR v3 Lifecycle

### 初始硬保护

保持既有 SOR 结构：

- Long Initial Stop = Opening Range Low；
- Short Initial Stop = Opening Range High；
- TP1 = 1R，数量 50%；
- TP1 后使用成本调整 Break-even；
- Runner 使用 confirmed structure + 0.5 ATR buffer；
- 禁止固定 TP2。

### Ticket 冻结的 TP1 前退出计划

CapacityClaim 和 Ticket 新增：

```text
pre_tp1_reclaim_price: Decimal | None
exposure_session_end_ms: int | None
```

对 SOR v3 两字段必须非空：

- Long reclaim price = Opening Range High；
- Short reclaim price = Opening Range Low；
- session end = Signal Fact 中的 UTC Session end。

对旧 Event 两字段为 `None`，保持现有语义。

### POSITION_PROTECTED 决策

TP1 尚未成交时，SOR v3 在每个新关闭 15m K 线执行：

```text
Long: latest.close <= pre_tp1_reclaim_price -> EXIT failed_breakout_reclaimed
Short: latest.close >= pre_tp1_reclaim_price -> EXIT failed_breakdown_reclaimed
observed_at_ms >= exposure_session_end_ms -> EXIT sor_session_expired
holding_bars >= 96 -> EXIT time_stop_hit
otherwise -> NO_CHANGE
```

优先级为：

1. venue position/TP1 truth reconciliation；
2. 完整 TP1 fill 转换 Runner；
3. Session expiry；
4. reclaim failure；
5. time stop；
6. no change。

TP1 已完整成交时先记录 `TakeProfitFilled` 并进入 Runner replacement；同一 tick 不再创建第二个 EXIT Command。

### RUNNER_PROTECTED 决策

现有 Break-even、structural ATR 和 96-bar time-stop 逻辑保留。**Session expiry
只适用于 TP1 前的 `POSITION_PROTECTED` 阶段**；TP1 后已证明至少一次 1R
follow-through，继续由 Break-even、结构失效、ATR Runner 和原有 Runner
time-stop 管理，不因 UTC Session 切换截断右尾。其他策略不获得 SOR reclaim
或 Session 规则。

## 同 StrategyGroup 两仓容量

### Owner Policy

新增：

```text
max_strategy_group_concurrent_tickets = 2
```

它按以下域计算：

```text
venue_id + account_id + strategy_group_id
```

Long/Short 和不同 instrument 合并统计。同一 StrategyGroup 的两个 Active Ticket 允许，第三个新 Claim 拒绝；其他 StrategyGroup 仍可使用账户第三个槽位。

### Capacity Usage

新增：

```text
active_strategy_group_ticket_count
remaining_strategy_group_slots
```

当数量达到上限时返回：

```text
CapacityClaimStatus.STRATEGY_GROUP_CAPACITY_EXHAUSTED
IssueTicketStatus.STRATEGY_GROUP_CAPACITY_EXHAUSTED
EntryDispatchPreflightStatus.STRATEGY_GROUP_CAPACITY_EXHAUSTED
```

Blocker Contract 使用：

```text
strategy_group_capacity_exhausted
```

这是正常策略组合容量阻塞，不创建 Incident、不要求 Owner 临时介入、不影响已有 Ticket 生命周期。

### Claim 冻结

CapacityClaim 新增：

```text
active_strategy_group_ticket_count_at_claim
max_strategy_group_concurrent_tickets
remaining_strategy_group_slots_at_claim
```

这些字段进入 decision digest。Entry Preflight 在交易所写之前重新读取当前计数。Ticket 发行事务持有 global Entry Lane 后再次执行 exact count，防止陈旧 Claim 越过上限。

### 查询与索引

使用精确有界查询：

```sql
SELECT count(*)
FROM brc_trade_tickets
WHERE venue_id = :venue_id
  AND account_id = :account_id
  AND strategy_group_id = :strategy_group_id
  AND terminal_at_ms IS NULL;
```

新增索引：

```text
(venue_id, account_id, strategy_group_id, terminal_at_ms)
```

网络 I/O 不进入数据库事务；该检查只读取 PostgreSQL 当前权威。

## Schema 兼容迁移

### Revision chain

新增：

```text
0001_trading_kernel_baseline_v4
-> 0002_sor_v3_strategy_group_capacity
```

### 冻结历史 baseline

当前 `0001_trading_kernel_baseline_v4` 动态导入
`src.trading_kernel.infrastructure.pg_models.metadata`。一旦 application metadata
演进到 v5，空库执行 `0001 -> 0002` 会先按最新 metadata 建表，再由 `0002`
重复加列或约束，因此它不是可继续演进的历史 revision。

本次必须先把 `0001` 所需的 **v4 exact schema snapshot** 冻结在
`migrations/trading_kernel/**` 下，并让 `0001` 只读取该冻结定义。该快照只服务
历史 revision，不被生产 runtime import；`pg_models.py` 继续表示当前 head
metadata。禁止用 `has_column`、`IF NOT EXISTS` 或运行时 metadata 猜测来掩盖
迁移顺序错误。

迁移架构测试必须证明：

- `0001` 的 schema 与当前生产 v4 fixture 完全一致；
- 修改 head metadata 不会改变 `0001` 创建结果；
- 空库严格执行 `0001 -> 0002`；
- 生产形状数据库严格执行 `0002`；
- Alembic revision graph 是单 head、无分叉的前向链。

架构测试不再断言“只能存在一个 migration 文件”，改为断言：

- migration revision 唯一；
- `down_revision` 形成一条无分叉链；
- head 与 runtime identity 完全一致；
- 没有平行 schema generation 或旧表 reader。

### DDL

`0002` 执行：

1. 删除 `brc_event_specs.event_id` 全局唯一约束；
2. 新增 `(strategy_version_id, event_id)` 唯一约束；
3. `brc_signal_events` 新增非空 `exposure_episode_id`，先以 legacy identity 回填，再建立唯一约束；
4. `brc_owner_policy_current` 新增非空 `max_strategy_group_concurrent_tickets`，现有 policy 回填为 **2**；
5. `brc_capacity_claims` 新增策略组计数字段和 Exit Policy 冻结字段；
6. `brc_trade_tickets` 新增 Exit Policy 冻结字段、`pre_tp1_reclaim_price`、`exposure_session_end_ms`；
7. 通过 existing Event Spec -> Exit Policy 精确关联回填旧 Claim/Ticket policy identity/hash；
8. 通过 Ticket 时间窗口计算旧 Claim 的同策略历史计数并回填；
9. 新增 active strategy-group count 索引；
10. 所有可回填字段完成后设为 `NOT NULL`；v3-only reclaim/session 字段保持 nullable，由 domain/version validator 约束。

所有 Registry、Lifecycle 和 Repository 查询必须以 `event_spec_id` 或 Ticket
冻结的 policy identity 为唯一键。解除 `event_id` 全局唯一后，任何把
`event_id` 当成版本唯一身份的 lookup 都必须删除或重写，禁止使用“优先 active
版本”的隐式选择。

### 旧 Claim 策略计数回填

对每个 Claim，在其 `created_at_ms` 时刻计算同 venue/account/strategy 下满足以下条件的既有 Ticket：

```text
other.created_at_ms < claim.created_at_ms
other.terminal_at_ms IS NULL
OR other.terminal_at_ms > claim.created_at_ms
```

若同毫秒存在多个 Ticket，则按 `ticket_id` 确定稳定次序。Migration 本身不删除
或终结任何 Ticket；official cutover preflight 必须证明活跃 Ticket、Reservation、
position、open order、unresolved Command 和 open Incident 全部为零。发现任一活跃
exposure 时部署保持 Entry fenced 并停止，不通过 schema mutation 代替 Lifecycle
终结。

### Downgrade 与 fix-forward

在 v3 Registry/Signal/Claim/Ticket 尚未写入前，`0002` 可以回退至 v4。出现任一 v3 runtime row 后，downgrade 必须明确拒绝，生产进入 fix-forward。拒绝 downgrade 不删除任何 Ticket 或事件。

## Authority 与事务

| 决策 | 单一权威 | 原子边界 |
| --- | --- | --- |
| SOR v3 Event 语义 | Strategy Registry + pure detector | 无数据库事务 |
| Episode 唯一性 | PostgreSQL Signal Event unique identity | Signal ingest transaction |
| StrategyGroup 上限 | Owner Policy | Claim read + Ticket issue revalidation |
| Ticket exit plan | Immutable CapacityClaim/Ticket | Ticket issue transaction |
| Exchange ENTRY/EXIT | Durable Exchange Command | Command commit 后网络 I/O |
| Historical semantic classification | Append-only Trade Review revision | terminal Ticket review transaction |
| 外部仓位和订单 | Exchange readonly truth | Reconciliation transaction |

## Runtime 所有权

### Observation Worker

- 读取 UTC Session closed candles；
- 计算 v3 edge crossing 和 Episode；
- v2 Universe 退休后不再产生 v2 Signal；
- healthy no-signal tick 不创建文件。

### Entry Worker

- 执行全局串行仲裁；
- 检查账户总容量和 StrategyGroup 容量；
- 冻结 v3 exit plan；
- 不解释 SOR 市场语义。

### Lifecycle Worker

- 按 Ticket 冻结 Exit Policy 读取当前 active Ticket 的精确行为；
- v3 POSITION_PROTECTED 读取 closed 15m market facts；
- 所有 EXIT 必须先产生 durable Command。

### Reconciliation Worker

- 继续处理 v3 Ticket、未知 outcome、Settlement 和 Review；
- migration 前负责把所有 v2 Ticket 推进到 terminal、Settlement/Review complete；
- migration 后允许对 terminal 历史 Ticket 追加通用 Review revision，但不重新执行
  v2 策略生命周期；
- 不负责策略容量或 Session 判断。

## Failure 语义

| 场景 | 结果 |
| --- | --- |
| 同 Session 重复位于 Range 外 | `NOT_TRIGGERED`，不产生 Signal |
| 同 Episode 重复 ingest | 唯一约束下幂等返回，不产生第二条 lineage |
| 两个同策略 Ticket 已活跃 | `strategy_group_capacity_exhausted` |
| 其他策略存在可用第三槽位 | 正常参与仲裁 |
| v3 failed breakout | durable EXIT Command |
| EXIT authoritative rejection | 现有 terminal rejection 语义，不重试 |
| EXIT unknown outcome | Reconciliation 解析，不盲目重发 |
| migration 失败 | PostgreSQL DDL transaction rollback，旧 release 可恢复 |
| migration 成功但 target postflight 失败 | Entry 保持 fenced，target safety workers 优先恢复，fix-forward |
| preflight 发现 active v2 Ticket | migration 不开始；Entry 保持 fenced，官方 Lifecycle/Reconciliation 先完成 terminal、Review 与 internal/exchange flat |

## 本地优先测试

### Detector RED/GREEN

必须证明：

1. 第五根首次穿越触发；
2. 第 69、70、83 根持续位于 Range 外不触发；
3. previous 已在 Range 外时不触发；
4. 先回到 Range 内、同 Session 再次穿越时 Episode 唯一约束阻止第二个 Signal；
5. Long/Short 边界完全对称；
6. 开放 K 线和 trigger 时间不一致 fail-closed；
7. Live/Replay 产生相同 Event、Facts、Episode 和 expiry。

### Lifecycle RED/GREEN

必须证明：

1. v3 TP1 前 Long reclaim 产生 EXIT；
2. v3 TP1 前 Short reclaim 产生 EXIT；
3. v3 Session end 产生 EXIT；
4. v3 96-bar time-stop 在 POSITION_PROTECTED 生效；
5. migration/deployment preflight 在任一 v2 active Ticket 存在时 fail-closed；
6. TP1 fill 和失效同时出现时只产生 Runner transition；
7. 其他五个 Event 不获得 SOR reclaim/session 行为；
8. EXIT durable-before-dispatch、rejection、unknown outcome 回归通过。

### Capacity RED/GREEN

必须证明：

1. 同 StrategyGroup 0/1 个 Ticket 时允许；
2. 已有 2 个时第三个 Claim 拒绝；
3. 两个 SOR + 一个 MI 允许账户达到 3 个；
4. SOR Long + SOR Short 合并计数；
5. 不同 account/venue 不互相计数；
6. Claim 后计数变化时 Entry Preflight 拒绝；
7. global lane 下 Ticket issue 原子重检；
8. 阻塞不创建 Ticket、Reservation、Command 或 Incident。

### Compatible migration RED/GREEN

生产形状 fixture 必须包含：

- v4 Registry、Policy、Universe；
- 一个已经 terminal、具有 TP1 -> Break-even -> structural Runner -> terminal
  lineage 的历史 BNB SOR v2 Ticket；
- 三个已经 terminal、被归类为错误持续状态入场的 SOR v2 Ticket；
- 四个 Ticket 的 Signal、Claim、Reservation、Aggregate、Command、fill、Settlement、
  Review 和 Owner projection 完整 lineage；
- released Budget Reservation 和 Netting Domain；
- 零 active Ticket、Position、open order 和 unresolved Command；
- 零 open Incident。

升级到 `0002` 后验证：

- 所有 row count 和 exact identity 保留；
- v2 Ticket policy hash 正确回填；
- terminal v2 Ticket 不进入 target Lifecycle actionable selector；
- 历史 BNB 和三笔错误语义 Ticket 可追加 append-only Review revision；
- Owner Policy 上限为 2；
- schema head 和 metadata 一致；
- v3 Registry 可插入且 v2/v3 同 Event ID 共存；
- migration 期间 recording venue 收到零 mutation；
- clean empty database 从 base 一次升级到 head 同样通过。

## 历史证据分类

### 已终结 BNB

历史 BNB Ticket、Review 和经济结果原样保留。通过现有 append-only Trade Review
revision 增加：

```text
entry_semantics = unverified_against_sor_v3_edge
evidence_scope = lifecycle,tp1_transition,break_even,structural_runner,right_tail
entry_alpha_inclusion = excluded_until_candle_reconstruction
```

随后使用其 exact Signal occurrence 和历史 closed candle 重建：

- 满足 `previous.close <= range_high && latest.close > range_high` 时，Review 新修订
  可标记为 `sor_v3_edge_compatible_historical_example`；
- 不满足时仍保留 Runner/right-tail 价值，但不得进入 SOR v3 entry-alpha 样本。

Review revision 不修改旧 Signal、Ticket、Event、Command 或原 Review row。

### 三笔错误语义 Ticket

三笔 exposure 终结并完成 Review 后，追加或生成如下 decision impact：

```text
entry_semantics = invalid_sor_v2_persistent_state
entry_alpha_inclusion = excluded
execution_evidence = retained
lifecycle_evidence = retained
economics_evidence = retained
```

它们用于量化错误语义成本、滑点、保护、退出和资金占用，不与 SOR v3 新样本混合。

## 部署设计

### 正式部署契约演进

当前 `TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` 的 regular release 禁止 schema
change，而 destructive rebuild 会删除有价值的历史 BNB 和其他 Ticket lineage。
实现必须增加一个 **official flat compatible-upgrade mode**，并同步更新该 CURRENT
合同；禁止用手工 SSH、临时 SQL 或复用 protected-ticket 参数绕过合同。

该模式只接受：

```text
0 active Ticket
0 non-flat position domain
0 open-order domain
0 unresolved Command
0 open Incident
all historical Tickets terminal and reviewed
```

它提供的是 flat 数据保留迁移，不是 active-position schema hot upgrade。

该模式只允许：

- exact certified migration chain 的前向升级；
- 全部 terminal Ticket/lineage 的行级保留和字段回填；
- Registry/Owner Policy 的版本化 seed；
- target release 和 runtime identity 的原子切换。

它仍禁止在 migration 内撤单、平仓、修改凭证、改资金、改账户模式、扩大标的
范围以及在新旧 writer 并存时继续。Exposure closure 必须在 migration 前由官方
Lifecycle 完成；preservation certification 和 exchange readonly flat
certification 是 Entry 解封前硬门。

### Exposure closure

1. 在任何仓位释放容量前先写入 Entry fence，禁止旧 SOR v2 再次建立 Ticket；
2. Observation、Lifecycle 和 Reconciliation 保持运行，Entry 停止；
3. 从当日 PostgreSQL 与 exchange readonly facts 解析所有 exact active Ticket；
4. 对仍活跃的错误语义 Ticket 使用官方 `ExitRequested -> durable EXIT Command`
   路径自然或受控终结；
5. 不直接撤单、不手工反向下单、不 direct SQL 修改 Ticket/Aggregate；
6. 等待 exchange flat、零 residual order、内部 Ticket terminal、Reservation/Domain
   released、Settlement/Review complete；
7. 历史 BNB terminal Ticket 不执行任何 exchange action，只保留 lineage。

### Preflight

1. 读取 exact production commit/schema；
2. 读取 PostgreSQL active Ticket、Command、Incident；
3. authenticated readonly 验证 position/order truth 为全账户 flat；
4. 验证无 unknown command outcome；
5. 验证所有历史 Ticket terminal、Reservation/Domain released、Settlement/Review
   complete；
6. Entry fence 保持存在，记录 exact historical-preservation manifest。

### Migration and release switch

1. 停止四个 worker；
2. 再次验证没有旧 writer；
3. 从 target committed release 执行 `alembic upgrade head`；
4. 运行 migration preservation certification；
5. seed v3 Registry 与新 Owner Policy version；
6. runtime identity 原子更新到 target commit/schema/seed；
7. 切换 release symlink；
8. 启动 Observation、Lifecycle、Reconciliation；
9. PostgreSQL preservation 与 exchange flat readonly certification；
10. 安装 v3 Warming Universe；
11. 完成七标的 certification/warming；
12. 原子退休 v2 Universe、激活 v3 Universe；
13. Entry 最后启动并解除 fence。

### Postflight

- exchange 保持零 position/open order；
- 历史 BNB、三笔错误语义 Ticket 及其 terminal lineage 与 preflight exact digest
  一致；
- v2 terminal Ticket 不进入 Lifecycle actionable set；
- v3 Event/Universe identity 唯一且 Active；
- 新 Signal 只来自 v3；
- 同策略两个活跃 Ticket 后 Tradeability 显示 `strategy_group_capacity_exhausted`；
- 四个 worker active、零 restart growth；
- 零 open Incident、零 unknown Command；
- no-signal cadence 创建零 JSON/Markdown 文件。

### Current 文档同步

实现提交必须同步更新以下权威文档，删除与新事实冲突的 rebuild-only 语义：

- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`：schema authority 改为
  单 head 前向 revision chain；
- `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md` 与 implementation plan：
  completed rebuild 仍是历史事实，但不再禁止未来兼容迁移；
- `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`：加入 official flat
  compatible-upgrade mode；
- `docs/current/MAIN_CONTROL_ROADMAP.md`：只在实际部署后记录 production commit、
  schema head、certification 和 runtime snapshot。

测试规格、执行计划和部署脚本必须引用这些 CURRENT 文档，不复制易变生产事实。

## 退休与删除

本次实现删除或重写：

- v2 SOR 持续状态式 detector 作为新 Signal producer；
- `RegisteredStrategyContract` 强制全系统只能使用 v2 的 validator；
- `event_id` 全局唯一、阻止版本并存的 schema 约束；
- Lifecycle 只按 active Exit Policy 读取的错误假设；
- Ticket 自己生成 Exposure Episode、忽略 Signal Episode 的实现；
- 只覆盖第五根立即突破的旧 SOR fixture 语义；
- 只在 Runner 测试 SOR time-stop 的旧测试语义；
- “只能有一个 migration 文件”的架构测试；
- active-position protected schema handover 和相关 fixture；
- `retained_ticket_strategy_contracts()` 或任何等价的 v2 runtime compatibility
  概念。

v2 PostgreSQL history 保留；v2 detector、Lifecycle contract 和 active execution
support 不进入 target runtime。

## 非目标

本次不包含：

- 改变 UTC Session 锚点；
- 优化 SOR 盈利参数或承诺回报；
- 新增 Retest/Continuation Event；
- 改变 3%/6% 风险政策；
- 改变 45%/90% 保证金政策；
- 改变固定 5x exchange leverage；
- 手工移动现有 Stop、TP1 或平仓；
- 修改凭证、划转或提款；
- 绕过 StrategySignal -> Claim -> Ticket -> Command 链。

## 验收标准

设计和实现只有在全部条件满足时才可判断为 deployable：

1. SOR v3 只在首次边沿突破产生一个 Session Episode；
2. 持续位于区间外不会重复 Signal；
3. v3 TP1 前 reclaim、Session 和 time-stop 能产生 durable EXIT；
4. migration 前所有 v2 exposure 通过官方链终结，exchange/internal flat；
5. 同一 StrategyGroup 最多两个新 Active Ticket；
6. 其他 StrategyGroup 可使用账户剩余第三槽位；
7. v4 production-shaped database 可无损升级到 `0002`；
8. base -> head clean upgrade 和 v4 -> head compatible upgrade 均通过；
9. targeted、integration、full-chain、Ruff、Mypy、architecture audit 和 `git diff --check` 全部通过；
10. deployment dry-run 与 flat compatible-upgrade rehearsal 不产生 exchange mutation；
11. 没有 dual write、old-schema reader、fallback 或第二执行链；
12. direct readonly postflight 能证明历史 BNB/错误语义 Ticket lineage 保留、v2
    actionable Ticket 为零、PG 与 exchange 均 flat；
13. BNB Review 与三笔错误语义 Review 使用 append-only revision 完成证据隔离。
