---
title: DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_DESIGN
status: REMEDIATION_APPROVED_NOT_STARTED
authority: docs/current/DUAL_POSITION_HARD_CAP_ACCOUNT_RISK_MODEL_V0_DESIGN.md
owner_decision_date: 2026-07-14
implementation_state: DEEP_REVIEW_NO_GO_REMEDIATION_NOT_STARTED
integration_state: LOCAL_MERGE_DEEP_REVIEW_NO_GO
production_state: UNCHANGED
policy_activation: NOT_PERFORMED
exchange_write: 0
current_migration_head: 133_LOCAL_ONLY
planned_migration_head: 136
remediation_design: docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md
remediation_plan: docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_IMPLEMENTATION_PLAN.md
---

# Dual-Position Hard-Cap Account Risk Model V0

> **当前实施状态覆盖：**本文的 Owner 风险政策和目标模型继续有效；
> instrument identity、rule snapshot、Claim、ExposureEpisode 与 risk-cluster membership
> 继续由资产中立扩展定义。2026-07-17 深度审查已经撤销“本地合并已认证”结论；统一
> 修复设计与可执行计划分别以
> `DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_DESIGN.md` 和
> `DUAL_POSITION_ACCOUNT_RISK_V0_RELEASE_BLOCKER_REMEDIATION_IMPLEMENTATION_PLAN.md`
> 为当前实施权威。

## Deep-Review Status Override

**合并基线 `60bb7fed` 当前为功能性 NO-GO，方案 B 已获确认但修复尚未开始。**
此前的组件测试和本地合并证据保留为历史证据，不能再证明 release-ready。当前
migration head 仍为本地 `133`；计划只通过 forward migrations `134 -> 136` 修复，
生产部署、政策激活和 exchange write 均未发生。

### 可执行语义覆盖

本文继续拥有 **Owner 风险政策数值**，但以下工程语义已由统一 remediation 设计覆盖，
实现者不得从本文旧章节自行推导：

1. **容量事实**使用 `account_safe` / `account_capacity_base` 的版本化二选一引用，并在
   retention、canary、readmodel、FinalGate 与 Runtime Safety 全链守恒。
2. **历史 Ticket/Claim 哈希**使用冻结 V1 verifier；新增容量引用与
   `risk_calculation_kind` 只进入显式 V2，migration 不重算历史哈希。
3. **当前线性合约计算**必须包含正数 `contract_multiplier`；未知、inverse、quanto 或
   nonlinear 类型在 Claim 前 fail-closed。
4. **执行入口**唯一为统一 remediation 计划 T01-T12；本文后续历史任务、旧测试数量或
   migration 编号均不构成可执行指令。

## Decision Summary

**Owner 已确认采用“双仓位硬上限账户风险模型 V0”**，在保留当前单一
Action-Time 新建通道和完整安全链路的前提下，把账户从“必须全空仓”推进为
“最多同时持有两个独立交易仓位”。

本设计不是完整的机构级资产配置系统，也不是简单删除当前空仓门禁。它先建立：

```text
完整账户交易所快照
-> 订单/仓位归属与用途分类
-> Account Exposure Current
-> Account Budget Current
-> 原子容量预占
-> 单一新 Action-Time Lane
-> Ticket / Protected Submit / Lifecycle
-> 对账后释放容量
```

**单 Ticket 计划止损风险上限由 3% 调整为 2.5%**。这是目标政策，当前发布版本和
生产 PG 在代码实施、migration、影子认证与部署前仍保持已部署的 **3% 单仓位模式**。
设计文档本身不修改线上政策，不授予新增交易权限。

## 已知客观事实

以下事实来自当前发布基线 `2001644581cccc968ba695d3ff129960db6a7e84`、
当前代码、当前 PG 结构和 2026-07-14 的只读生产核验。

| 事实对象 | 当前状态 | 设计含义 |
| --- | --- | --- |
| **Action-Time 并发** | PG 唯一部分索引 `uq_brc_lane_single_open_real` 限制同一时刻最多一个开放的 `real_submit_candidate` Lane | V0 保留“每次只新建一个交易意图”，不把双仓位误做成双 Lane 并发提交 |
| **Ticket 原子性** | fact refresh、promotion、reservation、lane、Ticket 已在一个有 savepoint 的短事务中提交 | 新容量仲裁必须嵌入现有原子边界，不能另建第二条 Ticket 主链 |
| **当前账户门禁** | 只检查 `live_submit_allowed` 候选币种集合中的 position 和普通 open order，并要求集合内全空 | 它实际是 `authorized_live_symbol_regular_order_flat_gate`，不是完整账户风险模型 |
| **条件单可见性** | 现有 pre-entry collector 未读取 Binance `openAlgoOrders`；Ticket 生命周期的 `fetch_all_open_orders` 已有普通单和条件单合并能力 | 账户级风险快照必须同时覆盖普通单和条件/Algo 单 |
| **网络事务边界** | 当前 `account_safe_facts.main` 在 `engine.begin()` 内执行 signed GET | V0 必须改为“短 PG 读 identity -> 事务外网络并发读取 -> 短 PG 写 projection”，避免网络延迟持有数据库事务 |
| **预算预占** | `brc_budget_reservations` 已有 planned stop risk、notional、leverage、margin 和 Ticket 绑定 | 复用 reservation 轴，不创建一套平行的“新预算票据” |
| **预算释放缺口** | 48 个已过期 Ticket 的 reservation 仍为 `consumed`；清理任务只处理 `active` reservation | Account Budget Current 上线前必须修复状态转换守恒，否则可用容量会被永久低估 |
| **真实仓位样本** | 当前存在一个 PG Ticket 归属明确、SL/TP1 完整、对账一致的 ETHUSDT LONG 真实仓位 | 可作为影子投影的第一个真实现有 exposure 样本，不需要制造生产仓位 |
| **目标表** | 生产 PG 尚无 `brc_account_exposure_current` 和 `brc_account_budget_current` | V0 需要新增 PG current projection，而不能读取 JSON/MD 报告替代 |
| **已部署风险政策** | 3% planned Stop risk、90% initial margin utilization、10x leverage ceiling | 2.5% 是待实施 Owner 目标；90% 与 10x 继续保留 |

事实来源：当前跟踪代码、Alembic migrations 086/103/115、当前 PG 只读查询、
Binance USD-M signed GET 只读核验。

## 基于事实的分析

### 当前门禁为何不能直接放宽

当前门禁把“账户中存在任何已授权币种仓位或普通订单”直接等价为“不可新建
Ticket”。它在单仓位阶段有效，但没有回答双仓位所需的四个问题：

1. 现有订单或仓位是否属于系统内某个 Ticket。
2. 订单是新开仓、止损、TP1、Runner Stop，还是未知外部订单。
3. 已用风险、待提交预占风险和交易所实际风险是否被重复累计。
4. 第二个 Ticket 加入后是否仍满足账户、风险簇、保证金和仓位数量硬上限。

因此，直接删除 `active_position_clear` / `open_orders_clear` 会把安全门禁变成盲区；
完整 Capital Allocation V1 又会过早引入策略 sleeve、动态相关性、Kelly、回撤乘数等
尚无真实样本支持的复杂度。V0 选择两者之间的窄而完整边界。

## Owner 已确认政策

| 政策维度 | V0 数值/规则 | 精确定义 |
| --- | --- | --- |
| **最大并存仓位数** | **2** | 账户内可归属且未平仓的 instrument exposure，加已取得容量但尚未形成仓位的 pending Ticket claim，最多占用两个 instrument slot |
| **新 Action-Time Lane 数** | **1** | 任一时刻仍只允许一个开放的 `real_submit_candidate` Lane |
| **单 Ticket 计划止损风险** | **2.5%** | `total_wallet_balance * 0.025`，是目标值和单 Ticket 硬上限；只能自动缩量，不能利用组合余量放大到 2.5% 以上 |
| **组合 open risk 硬上限** | **6%** | 账户当前 held risk 总和不得超过 `total_wallet_balance * 0.06` |
| **单风险簇 open risk 硬上限** | **4%** | 同一 versioned risk cluster 的 held risk 总和不得超过 `total_wallet_balance * 0.04` |
| **组合 initial margin 硬上限** | **90%** | 交易所 initial margin 与交易所尚未体现的本地 pending reservation margin 合计不得超过 `total_wallet_balance * 0.90` |
| **杠杆上限** | **10x** | 最终杠杆取 Owner 上限与交易所 instrument 上限的较小值，并选择满足保证金容量的最低充分杠杆 |
| **同 instrument 第二 Ticket** | **禁止** | 即使交易所处于 Hedge Mode，也不允许同一 `account_id + exchange_instrument_id` 同时存在第二个非终态 Ticket claim |
| **自动缩量** | **启用** | 第二个 Ticket 按单 Ticket、组合、风险簇、保证金四种剩余容量的最小值缩量；只有最小有效数量仍超限才阻断 |
| **未知事实处理** | **全局 fail-closed** | 未归属仓位/订单、身份冲突、保护未知、对账 mismatch、账户预算投影过期时，阻断所有新 ENTRY；既有保护、退出、恢复继续运行 |
| **开仓前费用储备** | **禁用** | fee、slippage、funding 不进入开仓 size 预算；成交后进入 Live Outcome 真实计算 |
| **回滚仓位上限** | **1** | 通过版本化 Owner policy 恢复单仓位；不强平既有第二仓，只停止新 ENTRY，直到占用回到上限以内 |

### 6% 组合上限的语义

**6% 不是第三个仓位的授权，也不是把某一 Ticket 放大到 3% 的授权。**

在两个 Ticket 都按 2.5% 计划时，正常计划风险合计不超过 **5%**。多出的 **1%**
只吸收以下已知运行漂移：

- 真实成交价偏离计划 entry，导致实际 stop distance 变大；
- 部分成交和剩余 working entry 同时存在；
- 仓位在止损单完成确认前处于短暂 conservative hold；
- 交易所事实与 PG 事实跨两个快照收敛时的最坏已知占用。

若实际 held risk 已达到或超过 6%，系统只允许保护、减仓、退出、对账和恢复，不允许
新 ENTRY。已知超限是 **new-entry capacity blocker**；未知归属或对账冲突才是
**global fail-closed safety blocker**。

当前加密永续 instrument 若统一配置到 `crypto_usd_beta` 风险簇，则两个加密仓位首先受
**4% cluster cap** 约束：第一笔实际占用 2.5% 时，第二笔同簇最多只取得 1.5%。
**6% portfolio cap** 主要为跨风险簇和未来贵金属/美股合约等不同 cluster 保留组合边界，
它不会绕开当前 crypto cluster cap。

## 风险与保证金计算

### 动态账户基数

V0 不使用硬编码 450U、600U 或 20U。每次 Action-Time 都读取新鲜账户事实：

```text
risk_capital_base = total_wallet_balance
exchange_available_balance = available_balance
```

**止损风险基数使用 `total_wallet_balance`**，避免未实现浮盈自动放大下一笔风险；
**保证金可用性使用 `available_balance`**，确保交易所当前实际可用资金参与约束。

### 单 Ticket 计划风险

```text
ticket_risk_budget = total_wallet_balance * 0.025
risk_calculation_kind = linear_quote_settled
per_unit_stop_risk = abs(entry_reference_price - protective_stop_price) * contract_multiplier
risk_limited_qty = floor_to_step(ticket_risk_budget / per_unit_stop_risk)
```

`contract_multiplier` 来自绑定 Claim 的 versioned Instrument Rule Snapshot，必须为正数；
不能缺省为 `1`。未知 calculation kind 不进入 sizing。

### 组合与风险簇剩余容量

```text
portfolio_risk_limit = total_wallet_balance * 0.06
cluster_risk_limit = total_wallet_balance * 0.04

portfolio_remaining = max(0, portfolio_risk_limit - current_portfolio_held_risk)
cluster_remaining = max(0, cluster_risk_limit - current_cluster_held_risk)

allowed_new_ticket_risk = min(
    ticket_risk_budget,
    portfolio_remaining,
    cluster_remaining,
)
```

### 组合保证金容量

```text
portfolio_margin_limit = total_wallet_balance * 0.90
exchange_reflected_entry_qty = exact_owned_position_qty + exact_owned_remaining_entry_order_qty
unreflected_qty = max(planned_qty - min(exchange_reflected_entry_qty, planned_qty), 0)
unreflected_pending_margin = reserved_margin * unreflected_qty / planned_qty

portfolio_margin_remaining = max(
    0,
    portfolio_margin_limit
    - exchange_total_initial_margin
    - unreflected_pending_margin,
)

action_time_margin_remaining = min(
    exchange_available_balance,
    portfolio_margin_remaining,
)
```

不能把 exchange 已计入 `totalInitialMargin` 或已从 `availableBalance` 扣除的 open order
margin 再次当作本地 pending margin 扣减。`unreflected_pending_margin` 只覆盖计划数量中
尚未被 exact owned position / remaining Entry order 反映的部分；无法证明精确数量和 lineage
时进入 `unknown` 并阻断新 ENTRY，不能猜测比例。

### 最终数量

```text
risk_qty = floor_to_step(allowed_new_ticket_risk / per_unit_stop_risk)
margin_qty = floor_to_step(
    action_time_margin_remaining * selected_leverage
    / (entry_reference_price * contract_multiplier)
)
intended_qty = min(risk_qty, margin_qty)
```

若 `intended_qty` 小于交易所 `min_qty`、`min_notional / price` 和 step quantization
共同决定的最小有效数量，则阻断并记录准确原因：

- `minimum_executable_quantity_exceeds_available_stop_risk_capacity`；或
- `minimum_executable_quantity_exceeds_available_margin_capacity`。

## 三轴状态模型

V0 不把所有状态塞进 `brc_budget_reservations.status`。系统分别维护三个正交轴：

| 状态轴 | 主对象 | 回答的问题 | 允许状态 |
| --- | --- | --- | --- |
| **Reservation** | `brc_budget_reservations` | 计划容量是否仍被 Ticket claim | `active`, `consumed`, `released`, `expired`, `invalidated` |
| **Exposure** | `brc_account_exposure_current` | 交易所当前真实风险和 instrument slot 占用是多少 | `flat`, `reserved`, `working_entry`, `open_unprotected`, `open_protected`, `partially_exited`, `runner_active`, `exiting`, `unknown` |
| **Reconciliation** | exposure/budget current 字段 | PG、Ticket 与交易所事实是否一致 | `matched`, `pending`, `mismatch`, `unknown` |

`consumed` 只表示 reservation 已绑定 Ticket，不能独立证明仓位仍存在，也不能与实际
exposure 简单相加。

## 容量占用守恒

### Held Risk 规则

| 生命周期阶段 | 风险占用 | 释放条件 |
| --- | --- | --- |
| **Lane 已预占、未提交 ENTRY** | planned reservation risk | Ticket 终止且确认无 exchange write，或 reservation 到期并被统一转换服务释放/失效 |
| **ENTRY working / 部分成交** | `max(planned reservation, filled actual risk + remaining working-entry risk)` | ENTRY 终态且完整 exposure/protection 事实已确认 |
| **ENTRY 全成、保护确认** | 当前 position 到已确认 stop 的 directional risk | 后续 position/stop 变化后重算 |
| **TP1 已成、Runner Stop 未确认** | 不释放 TP1 对应容量，保留最近 worst-known hold | Runner Stop 确认且 remaining qty 对账一致 |
| **Runner Stop 已确认** | remaining qty 到 runner stop 的 directional risk | 下一次一致快照继续重算 |
| **仓位 flat、对账 matched** | 0 | reservation 转为 `released`，instrument slot 释放 |
| **事实 unknown / mismatch** | worst-known hold，且新 ENTRY 全局 fail-closed | 归属、保护和对账全部恢复 matched |

### 当前 directional risk

```text
long_risk = max(0, actual_average_entry_price - confirmed_stop_price)
            * abs(position_qty)
short_risk = max(0, confirmed_stop_price - actual_average_entry_price)
             * abs(position_qty)
```

V0 用真实加权成交均价而不是 mark price 计算“到止损时相对入场资本的损失”，避免把
尚未实现的右尾浮盈回撤误当作新增本金风险，也不允许浮盈自动放大下一 Ticket 预算。
当 Runner Stop 已锁定正收益时，directional risk 可降到 0；但只有 stop 在交易所可见、
订单身份归属确定、数量覆盖正确且 reconciliation matched 时才能释放容量。

## 账户级交易所快照

### 读取范围

**Full-Account Exchange Snapshot 必须覆盖整个已绑定子账户**，不能再按候选 symbol
集合过滤后决定账户是否安全。

| 事实面 | 读取内容 | 完整性要求 |
| --- | --- | --- |
| **Account** | wallet、available、total initial margin、canTrade | 新鲜、账户身份匹配 |
| **Positions** | 所有非零 position rows，包括 position mode/bucket | 不允许只看当前五个 StrategyGroup 的 symbol |
| **Regular Orders** | 所有普通 open orders | 订单 identity、side、positionSide、reduceOnly、qty、price 完整 |
| **Conditional/Algo Orders** | 所有 stop / take-profit / algo open orders | `algoId`、actual order lineage、trigger、reduceOnly、positionSide 完整 |
| **Account Mode** | one-way / hedge | 与 Ticket 冻结事实和当前事实一致 |
| **Instrument Rules** | 当前候选 instrument 的 qty/price/min notional/leverage rules | Action-Time 有效期内新鲜 |

所有网络读取在 PG 事务外执行，必须并发、整体 timeout-bounded、失败即不生成可交易
的 Account Budget Current。

## 归属与用途分类

### 订单归属

每一个普通单和条件单必须被分类为：

```text
owned_by_ticket
owned_by_other_known_ticket
external_unowned
identity_conflict
mode_or_side_ambiguous
```

### 订单用途

已归属订单还必须被分类为：

```text
working_entry
initial_stop
take_profit
runner_stop
final_exit
external_unknown
```

用途来自 PG `ticket_bound_exchange_commands`、protection orders、protected submit
attempt 和 conditional parent/actual lineage，不能只根据 `reduceOnly` 猜测。任何
external/unowned、identity conflict、用途未知但会影响 exposure 的订单，都阻断新 ENTRY。

### 仓位归属

非零 position row 必须按以下证据绑定 Ticket：

1. `account_id + exchange_instrument_id + position_mode + position_bucket` 精确匹配。
2. Ticket 已有已确认 ENTRY fill 或受保护 submit attempt。
3. 不存在两个非终态 Ticket 同时声称同一 instrument。
4. position qty、entry fill、已知退出量可在允许误差内对账。

不能唯一归属时标记 `unknown`，不自动猜测最接近的 Ticket。

## PG Current Projection 设计

### `brc_account_risk_policy_events/current`

账户组合上限属于 **账户级 Owner policy**，不能复制到 22 个 candidate policy 后再依赖
“所有行恰好相同”。新增 append-only `brc_account_risk_policy_events` 和单行 current
projection `brc_account_risk_policy_current`，以 `account_id + runtime_profile_id` 为唯一作用域。

current 行保存 `planned_stop_risk_fraction=0.025`、`max_concurrent_positions=2`、
`max_portfolio_open_risk_fraction=0.06`、`max_cluster_open_risk_fraction=0.04`、
`max_portfolio_initial_margin_fraction=0.90`、`max_leverage=10`、
`max_new_action_time_lanes=1`、自动缩量、未知事实策略和 `risk_model_version`。

现有 `brc_owner_policy_current` 继续拥有 StrategyGroup/symbol/side 的准入、tier 和交易
范围，但其旧 `planned_stop_risk_fraction` 在 V0 激活后不再是新 Ticket sizing authority。
历史 Ticket 仍保留原 policy/version 值用于审计，不能回写改造。

### `brc_account_exposure_current`

每个 `account_id + exchange_instrument_id + position_mode + position_bucket` 最多一行：

| 字段组 | 核心字段 | 语义 |
| --- | --- | --- |
| **Identity** | `account_exposure_current_id`, `account_id`, `exchange_id`, `exchange_instrument_id`, `exchange_symbol`, `position_mode`, `position_bucket`, `netting_domain_key` | 账户与交易所仓位域的稳定身份 |
| **Ownership** | `owner_ticket_id`, `ownership_state`, `position_slot_claimed` | 当前风险是否可唯一归属以及是否占用 position slot |
| **Exposure** | `exposure_state`, `position_qty`, `mark_price`, `entry_price`, `confirmed_stop_price`, `working_entry_qty` | 当前交易所仓位与未完成 ENTRY |
| **Capacity** | `planned_reserved_risk`, `actual_directional_risk`, `held_risk`, `exchange_initial_margin`, `unreflected_pending_margin` | Account Budget Current 的逐 instrument 输入 |
| **Protection** | `protection_state`, `stop_covered_qty`, `tp1_open_qty`, `runner_stop_open_qty` | 保护完整性和容量释放依据 |
| **Truth** | `reconciliation_state`, `first_blocker`, `source_snapshot_id`, `observed_at_ms`, `valid_until_ms`, `projection_version`, `updated_at_ms` | 对账、新鲜度和 CAS 依据 |

### `brc_account_budget_current`

每个 `account_id + runtime_profile_id + risk_policy_version` 一行：

| 字段组 | 核心字段 | 语义 |
| --- | --- | --- |
| **Capital** | `total_wallet_balance`, `available_balance`, `exchange_total_initial_margin` | 动态账户事实 |
| **Risk Used** | `reserved_risk`, `working_entry_risk`, `open_directional_risk`, `unknown_held_risk`, `portfolio_held_risk` | 去重后的账户风险占用 |
| **Margin Used** | `exchange_initial_margin`, `unreflected_pending_margin`, `portfolio_margin_used` | 去重后的保证金占用 |
| **Capacity** | `ticket_risk_limit`, `portfolio_risk_limit`, `portfolio_risk_remaining`, `portfolio_margin_limit`, `portfolio_margin_remaining` | 下一 Ticket 容量上限 |
| **Slots** | `claimed_position_slots`, `pending_ticket_claims`, `max_concurrent_positions` | 双仓位硬上限 |
| **Safety** | `reconciliation_state`, `new_entry_allowed`, `first_blocker` | 新 ENTRY 的账户级结论 |
| **Concurrency** | `source_snapshot_id`, `source_watermark`, `valid_until_ms`, `projection_version`, `updated_at_ms` | 短事务锁与版本检查 |

### 风险簇映射

新增版本化 PG 映射 `brc_risk_cluster_memberships`：

```text
risk_policy_version
+ exchange_instrument_id
-> risk_cluster_id
```

V0 只使用 Owner 明确配置的静态 cluster。它不计算动态 correlation，不从 symbol
字符串猜资产类别，也不让回放结果自行修改生产映射。未映射 instrument 在 live submit
阶段 fail-closed。

V0 初始映射规则固定为：PG Registry 中当前 active 且 `asset_class='crypto'` 的 Binance
USD-M instrument 全部显式写入 `crypto_usd_beta`。该映射在 activation event 中版本化
落库；以后新增贵金属、美股合约或其他 instrument 时必须先写入明确 cluster，不能依赖
运行时代码按 symbol 猜测。

### 事件与审计

新增 `brc_account_risk_projection_events` 和 `brc_budget_reservation_events`，仅在语义状态、
held risk、归属、保护或 reconciliation 发生实质变化时追加。current 表原地更新；健康
无信号 tick 不写 JSON/MD，不为相同快照反复追加业务事件。

## 原子容量仲裁

### 事务边界

```text
PG 事务外：完整账户交易所读取 + typed snapshot 构建

PG 短事务内：
1. upsert exposure current
2. project budget current
3. SELECT account budget current FOR UPDATE
4. 校验 source_snapshot_id / valid_until_ms / projection_version
5. 校验 position slot、same instrument、portfolio、cluster、margin 容量
6. 计算 auto-downsize 后数量
7. 写 allocation decision + reservation + lane + Ticket
8. projection_version += 1
9. commit
```

事务内禁止网络调用和历史大表扫描。第二个并发事务必须在获得同一账户预算行锁后重新
读取 capacity；版本或 watermark 变化时重算或失败，不能使用锁前数量继续提交。

### 与当前单 Lane 的关系

V0 不删除 `uq_brc_lane_single_open_real`。双仓位指“已有一个受保护仓位时，可以创建
第二个合规 Ticket”，不指“同时让两个 fresh signal 并发进入 exchange submit”。

## Reservation 状态守恒修复

### 已确认缺口

当前 Ticket expiry 会把 Ticket 置为 `expired`，但不会释放已绑定后变成 `consumed` 的
reservation；周期清理只处理仍为 `active` 的 reservation。该缺口在当前生产数据中留下
**48 个 expired Ticket + consumed reservation**。

### 统一转换规则

新增单一 `transition_budget_reservation` 服务，所有 Ticket expiry、FinalGate reject、
invalidated、lifecycle close、external close 和 repair migration 都通过相同验证与事件写入：

- `active -> consumed`：Ticket 原子创建。
- `active -> expired/invalidated`：Ticket 未创建且 reservation 失效。
- `consumed -> released`：Ticket 已终止，且已证明无 exchange write / position risk；或
  lifecycle 已 flat 且 reconciliation matched。
- 其他逆向转换全部拒绝。

历史修复只能处理“终态 pre-submit Ticket + 无 exchange write + 无 position exposure”的
reservation；当前真实 submitted Ticket 的 `consumed` reservation 必须保留。

## Gate 替换策略

### 影子阶段

1. 保持生产 `max_concurrent_positions=1` 和旧 flat gate 为实际决策。
2. 同时生成完整账户 snapshot、Exposure Current、Budget Current 和 V0 shadow decision。
3. 当前 ETH 真实仓位必须被唯一归属、识别为 protected、占用一个 slot，且 shadow
   decision 不得把 SL/TP1 误判为冲突订单。
4. 对比旧 gate 与新模型；任何未知订单、漏条件单、重复容量或 reservation 泄漏都先修复。

### 激活阶段

影子验收通过后，在一个版本化 **Account Risk Policy** 事件中：

```text
planned_stop_risk_fraction = 0.025
max_concurrent_positions = 2
risk_model_version = dual_position_hard_cap_v0
```

同时让 account-safe fact 消费 `brc_account_budget_current.new_entry_allowed`，删除旧
`active_position_clear/open_orders_clear` 作为 live submit 决策条件。不能长期保留两套
门禁并让任一方单独授予交易资格。

## 故障处理

| 故障 | 新 ENTRY | 既有保护/退出 | 恢复动作 |
| --- | --- | --- | --- |
| **完整账户快照超时/不完整** | 全局阻断 | 继续 Ticket-bound lifecycle 只读/风险降低动作 | 重读快照，保持 worst-known hold |
| **未知仓位或订单** | 全局阻断 | 不取消、不接管未知对象 | 归属修复或 Owner 异常介入 |
| **身份冲突** | 全局阻断 | 已知 Ticket 只做 fail-closed 风险降低动作 | 对账 command/actual/algo identity |
| **保护缺失/数量不足** | 全局阻断 | 立即进入现有 protection recovery | 保护恢复并再次对账 |
| **已知组合风险超限** | 阻断新 ENTRY | 继续保护、TP、Runner、退出 | 市场/减仓/止损使风险回落 |
| **最小数量超过剩余容量** | 仅阻断该候选 | 不影响既有 Ticket | 记录准确 capacity blocker |
| **PG row lock / CAS 冲突** | 当前 Action-Time 失败并重试新鲜事实 | 不影响既有 lifecycle | 重新读取快照与预算，不复用旧 sizing |
| **Budget Current 过期** | 全局阻断 | 继续风险降低动作 | 触发新的完整账户投影 |

## 性能与文件 I/O 边界

| 维度 | V0 要求 | 禁止行为 |
| --- | --- | --- |
| **网络** | 账户、position、regular order、algo order、mode 读取并行；整体 timeout-bounded | PG 事务内等待交易所网络 |
| **PG** | current 表按账户/instrument 原地 upsert；只在语义变化时追加事件 | 每 tick 扫描完整历史 lifecycle 或 event 表 |
| **Watcher** | 无 fresh signal 时可刷新轻量账户 current；Action-Time 前强制新鲜 snapshot | 每个 no-signal tick 运行重型报表 builder |
| **文件** | 生产 no-signal tick 创建 **0 个 JSON/MD 文件** | repo/output/report 文件作为风险或交易 authority |
| **保留** | current 表单行/逐 instrument；事件按 retention policy 有界保留 | 动态路径 evidence sidecar、JSONL trace 或周期 MD 报告 |

发布前必须运行 `scripts/audit_production_runtime_file_io.py`，且生产 cadence 的
`performance_risk.status` 必须为 `clear`。

## 替代方案

| 方案 | 优点 | 拒绝原因 |
| --- | --- | --- |
| **A. 只放宽 flat gate** | 改动小、很快出现第二仓 | 无法处理条件单、归属、风险去重、并发预占；会把未知账户事实当安全 |
| **B. 双仓位硬上限账户风险模型 V0** | 保留单 Lane 和生命周期；建立最小完整账户事实、容量与对账闭环 | **已选定**；工程量中等，但每项都是双仓位所需必要复杂度 |
| **C. 完整 Capital Allocation V1** | 可支持 StrategyGroup sleeve、质量乘数、动态 cluster、drawdown | 当前真实样本不足，会把交易反馈目标推迟到过度工程化之后 |

## 明确不在 V0 范围

- 第三个及更多并存仓位。
- 同 instrument 多 Ticket 或同 instrument 双向对冲。
- StrategyGroup sleeve 和动态优先级权重。
- Kelly、VaR/ES、动态相关性矩阵、波动率 targeting。
- 日/周回撤乘数和自动策略降级。
- fee、slippage、funding 的开仓前 reserve。
- 强制平仓作为风险模型回滚动作。
- 新 asset class 的交易所适配；V0 数据模型保持 instrument/venue 中立。
- 前端重构。

上述能力继续属于后续 **Capital Allocation V1** 或 **Multi-Asset Execution Kernel**，
不得混入本轮验收。

## Live Enablement 状态变化

### 实施前

```text
一个受保护真实仓位存在
-> account-safe flat gate = blocked
-> 任何其他 StrategyGroup fresh signal 都不能创建第二 Ticket
```

### 实施后

```text
一个受保护、归属明确、对账一致的真实仓位存在
-> account exposure / budget current 新鲜且 matched
-> 第二候选通过 same-instrument / slot / portfolio / cluster / margin 检查
-> 必要时自动缩量
-> 仍只开放一个新 Action-Time Lane
-> 创建第二 Ticket 并走同一 Protected Submit / Lifecycle
```

### 能力解锁

**五个 StrategyGroup 的不同 instrument 机会不再因为账户已有一个健康仓位而全部丢失**；
系统可以在可解释、可对账、可回滚的硬边界内获得第二个并存右尾收益机会。

## 验收标准

1. 旧 3% 单仓位生产路径在影子阶段不变。
2. 当前真实 ETH Ticket/position/SL/TP1 被唯一归属并投影为一个 protected exposure。
3. 48 个 terminal pre-submit reservation 泄漏通过受审计规则修复，真实 submitted reservation 不受影响。
4. 普通单和 Algo/条件单均进入账户快照与 ownership/purpose 分类。
5. 两个不同 instrument Ticket 可在 2.5%/6%/4%/90%/10x 边界内顺序创建。
6. 同 instrument 第二 Ticket 被阻断。
7. 同 cluster 第二 Ticket 在剩余 1.5% 风险内自动缩量；最小数量仍超限时准确阻断。
8. 两个不同事务不能基于同一旧容量同时超额预占。
9. TP1 后 Runner Stop 未确认不释放容量；确认后按 remaining qty 重算。
10. unknown/mismatch/unprotected/stale account budget 全局阻断新 ENTRY，但不阻断风险降低动作。
11. 关闭并对账 matched 后，reservation、risk 和 slot 恰好释放一次。
12. 生产无信号 cadence 创建 0 个 JSON/MD 文件，runtime file-I/O audit clear。
13. `max_concurrent_positions=1` 回滚后不强平，只停止新 ENTRY，现有 lifecycle 正常闭环。

## 实施停止条件

发生以下任一情况时，停止 live activation，但继续可安全完成的非执行诊断：

- 不能唯一归属当前真实仓位、普通单或条件单。
- Account Budget Current 对同一风险产生 reservation + exposure 双重累计。
- PG 短事务无法证明账户级串行预占。
- 第二 Ticket 需要绕过 FinalGate、Operation Layer、保护或 reconciliation。
- 影子模型把当前受保护 ETH 仓位判为安全，但遗漏任何真实 exchange order surface。
- 文件/报告重新成为生产风险 authority。

## 回滚

回滚只追加版本化 **Account Risk Policy** 事件并更新其 current projection：

```text
max_concurrent_positions = 1
risk_model_version = dual_position_hard_cap_v0
```

回滚后：

- 不创建新的第二 Ticket；
- 不取消保护单；
- 不强制平仓；
- 两个已存在仓位继续由原 Ticket lifecycle 管理；
- 当 slot 占用回到 0 或 1 后，系统恢复单仓位新 ENTRY 能力；
- Exposure/Budget Current 和审计事件继续运行，避免重新退化为 symbol-filtered flat gate。
