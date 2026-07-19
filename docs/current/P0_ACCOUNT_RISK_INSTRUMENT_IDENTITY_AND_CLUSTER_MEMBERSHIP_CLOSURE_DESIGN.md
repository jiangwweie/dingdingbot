---
title: P0_ACCOUNT_RISK_INSTRUMENT_IDENTITY_AND_CLUSTER_MEMBERSHIP_CLOSURE_DESIGN
status: IMPLEMENTED_TOKYO_CERTIFIED_NATURAL_SIGNAL_PENDING
authority: docs/current/P0_ACCOUNT_RISK_INSTRUMENT_IDENTITY_AND_CLUSTER_MEMBERSHIP_CLOSURE_DESIGN.md
last_verified: 2026-07-19 CST
---

# P0 账户风险品种身份与风险簇成员闭环设计

## 1. 决策摘要

### 1.1 核心结论

当前故障不是单一 `asset_class` 字符串遗漏，而是 **Candidate Scope、Instrument
Registry、Instrument Rule Snapshot 与 Risk Cluster Membership 四个层级尚未形成同一
权威链**。

仅删除 `candidate.asset_class = 'crypto'` 可以让 Account Risk Policy 写入继续向下执行，
但不能恢复真实交易能力。东京 PG 当前还存在以下事实：

1. **22 条 active candidate lane** 的 `asset_class` 为 `crypto_usdm_perp`；
2. **6 个 active exchange instrument** 的 `asset_class` 同样为 `crypto_usdm_perp`；
3. 这些 instrument 的 `instrument_type`、`settlement_asset`、`margin_asset` 均为空；
4. `brc_instrument_rule_snapshots` 当前为 **0 行**；
5. `brc_account_risk_policy_current` 与 active risk cluster membership 当前均为 **0 行**。

因此推荐采用 **规范身份替换 + 规则事实投影 + 精确 scope membership 生成 + 原子 policy
写入**。本设计不修改 Owner 已确认的风险参数，不扩大 StrategyGroup、symbol、side、profile、
杠杆、名义金额或资金范围。（来源：东京 PG current 查询，2026-07-19；当前 tracked code。）

### 1.2 设计目标

恢复并证明以下链路：

```text
Active Candidate Scope
-> exact canonical exchange_instrument_id
-> complete InstrumentRiskIdentity
-> one fresh current InstrumentRuleSnapshotRefV2
-> one current primary RiskClusterMembershipSnapshot
-> active Account Risk Policy
-> Account Capacity
-> Action-Time Ticket
```

完成标准不是“policy 脚本不报错”，而是 22 条 active lane 对应的 6 个 instrument 都能
加载完整 `InstrumentRiskFacts`，并在自然信号出现时到达合法 Ticket 或精确的实时安全
blocker。

### 1.3 已确认实施状态

| 项目 | 当前状态 | 证据 |
| --- | --- | --- |
| Owner 决策 | **已确认** | Owner 已授权在当前合并分支完成修复并继续受控部署。 |
| 本地实现 | **已完成** | migration **138**、canonical seed、PG-only V2 rule projector、exact-scope membership service 已在当前分支实现。 |
| 本地 PostgreSQL 认证 | **通过** | revision **106 → 138**：**6** canonical identities、**22** active lanes、**6** V2 rules、**6** memberships、**1** active policy。 |
| 部署状态机 | **已加固** | migration/seed 后必须完成 V2 rule projection 与 **22/6** PG readiness certification，才允许 pointer switch 或恢复 watcher。 |
| 东京生产 | **已认证运行** | release **1aa05462**、revision **138**、6 canonical identities、22 lanes、6 V2 rules、1 active policy、6 primary memberships、enabled lifecycle 已验收；writer fence 已移除。 |

### 1.4 东京部署反馈与前向修复

**已知客观事实：**首次东京部署事务
`ad3a2e3d85ee4983aeab33588c33ca8e` 在 migration 后的 read-only V2 rule projection 阶段返回
`claim_notional_leverage_bracket_invalid`。对 Binance signed GET
`/fapi/v1/leverageBracket` 的只读复核显示，`BTCUSDT` 与 `ETHUSDT` 的首档
`initialLeverage` 为 **150x**，而 six candidate scopes 的 Owner policy `max_notional`
均为 **20 USDT**、`max_leverage` 均为 **10x**。（来源：东京 deployment journal 与 Binance
USD-M signed GET，2026-07-19。）

**基于事实的修复判断：**当前实现错误地把“交易所规则事实”的最大值限制为 **125x**，使真实
150x 事实被当作不存在。该限制不能应用到 venue metadata。修复将 exchange rule fact 的有界
上限设为 **200x**，同时保持 Owner policy、runtime config、sizing selection 的 **125x**
policy 上限；最终 selected leverage 仍取 `min(policy, exchange)`，本次仍不超过 **10x**。

部署失败已触发 **`failed_contained`**：backend、watcher、monitor、lifecycle timers 均已停止，
writer fence 与 disabled lifecycle capability 保持，未创建 policy、membership、Ticket 或订单。
随后通过 predecessor transaction 前向修复部署 release **`87e5236a`**，并完成 **138**、6/22/6
identity-rule readiness、只读 canary 与 activation commit；writer fence 已移除，backend 与全部
production timers 已恢复。（来源：东京 deployment journal、只读 deploy probe，2026-07-19。）

**闭环完成：**正式 deploy certification 已恢复 lifecycle capability 为 `enabled`；官方 policy
operation 已原子写入 **1** current Account Risk Policy 和 **6** current primary memberships。当前
22 条 active lane 均能 join 至 complete canonical identity 与 fresh V2 rule，容量、Ticket、
FinalGate、Operation Layer、保护及 lifecycle 的既有 fail-closed 边界没有被放宽。

### 1.5 激活后自然观察验收

Policy 激活后的第一个完整 watcher 窗口为 **2026-07-19 11:55–12:00 CST**：PG 记录 **110** 条
watcher coverage，`live_signal_events=0`、`promotion_candidates=0`、`action_time_lane_inputs=0`、
`action_time_tickets=0`，watcher 与 monitor oneshot 均以 `Result=success` 结束。因此该窗口可确认
为 `no_detected_signal_with_coverage`：系统健康运行但没有满足策略条件的新自然信号。（来源：东京
`query_runtime_signal_forensics.py`、PG current 与 systemd，2026-07-19。）

这个结论只覆盖上述窗口；下一项 live validation 是等待新的自然信号，然后验证
`Signal → Promotion → Lane → Ticket` 或记录精确实时 safety blocker。不得伪造 signal、Ticket
或交易所写入来缩短该验证。

## 2. 已知客观事实

### 2.1 东京 PG 当前状态

| 对象 | 当前值 | 数量 | 影响 |
| --- | --- | ---: | --- |
| Active candidate scope | `asset_class=crypto_usdm_perp` | **22** | 旧 `asset_class='crypto'` 条件命中 0 |
| Active exchange instrument | `exchange_id=binance_usdm`、`asset_class=crypto_usdm_perp` | **6** | 不满足资产中立身份合同 |
| Instrument type | `NULL` | **6** | `InstrumentRiskIdentity` 校验失败 |
| Settlement / margin asset | `NULL` | **6** | 无法证明线性、同币种结算风险语义 |
| Current V2 rule snapshot | 无 | **0** | 容量链路必然报 `instrument_rule_snapshot_invalid` |
| Account Risk Policy current | 无 | **0** | 当前第一 policy blocker 仍然有效 |
| Active cluster membership | 无 | **0** | 无法计算同风险簇已占用风险 |

来源：东京生产 PG 的
`brc_strategy_group_candidate_scope`、`brc_exchange_instruments`、
`brc_symbol_instrument_mappings`、`brc_instrument_rule_snapshots`、
`brc_account_risk_policy_current`、`brc_risk_cluster_memberships` 只读查询，
**2026-07-19 08:25–08:30 CST**。

### 2.2 当前代码失败条件

`scripts/ops/set_account_risk_policy.py:200-233` 当前执行：

```text
active candidate
-> symbol mapping
-> active exchange instrument
-> candidate.asset_class = 'crypto'
-> exchange_id = 'binance_usdm'
-> zero rows
-> active_crypto_binance_instrument_registry_empty
```

Policy event、current projection 与 membership replacement 位于同一个
`engine.begin()` 事务。两次生产尝试均在异常时整体回滚，因此当前不存在半写入 policy 或
membership。（来源：东京 traceback 与 `policy_current=0`、`membership_active=0` 查询。）

### 2.3 当前合同与实际数据的差距

| 维度 | 当前权威合同 | 东京实际 | 差距 |
| --- | --- | --- | --- |
| Candidate scope | 直接绑定 exact `exchange_instrument_id` | 已直接绑定，但保留复合 legacy asset class | scope 身份可用，分类语义未规范化 |
| Instrument asset class | `crypto`、`equity`、`precious_metal` 等经济类别 | `crypto_usdm_perp` | venue/product 被编码进 asset class |
| Instrument type | `perpetual`、`future` 等产品结构 | `NULL` | 产品结构缺失 |
| Settlement / margin | 明确且版本内稳定 | `NULL` | 合约风险语义不完整 |
| Rule snapshot | one fresh current V2 row | 0 rows | 容量与 sizing 无事实来源 |
| Membership source | exact instrument identity + versioned policy | symbol mapping + candidate asset-class literal | 使用了非权威别名与过时常量 |

来源：
`DUAL_POSITION_ACCOUNT_RISK_V0_ASSET_NEUTRAL_IDENTITY_EXTENSION_DESIGN.md`、
`PRE_TRADE_RUNTIME_CONTRACT.md`、当前东京 PG。

## 3. 根因分析

### 3.1 根因树

```text
Owner 已确认 Account Risk Policy
-> set_account_risk_policy.py
   -> 通过 symbol mapping 推导 instrument
   -> 使用 candidate.asset_class='crypto' 过滤
      -> 实际 candidate.asset_class='crypto_usdm_perp'
      -> zero memberships
      -> transaction rollback

即使删除过滤条件
-> policy + membership 可写
-> Action-Time load_instrument_risk_facts
   -> InstrumentRiskIdentity 必填字段为空
      -> instrument_identity_schema_invalid
   或
   -> current V2 rule snapshot 不存在
      -> instrument_rule_snapshot_invalid
```

### 3.2 第一根因

**Membership builder 使用了错误的分类层和过时 literal。**

风险簇成员应从 active Candidate Scope 已持久化的 exact
`exchange_instrument_id` 出发，再验证对应 Instrument Registry 与 Rule Snapshot。当前脚本
却重新经由 `symbol mapping` 解析身份，并使用 Candidate Scope 的 `asset_class` 字符串判断
instrument 类型。这违反 Candidate Scope 精确绑定合同，也使 `crypto`、
`crypto_perpetual`、`crypto_usdm_perp` 三套词汇发生漂移。

### 3.3 第二根因

**Foundation seed 仍生成 legacy composite asset class。**

`scripts/seed_runtime_control_state_foundation.py` 同时把 symbol、instrument 和 candidate
scope 写成 `crypto_usdm_perp`，而资产中立设计已经把语义拆为：

```text
asset_class = crypto
instrument_type = perpetual
exchange_id = binance_usdm
settlement_asset = USDT
margin_asset = USDT
```

迁移 132 只在部分下游字段为空时把 legacy 值映射为 `crypto + perpetual`，没有把当前
Instrument Registry 和 active Candidate Scope 转换为新的规范身份。

### 3.4 第三根因

**没有生产 current V2 Instrument Rule Snapshot。**

迁移 136 只能扩展或克隆已存在的 rule snapshot；当前东京没有任何 rule row，因此迁移
合法完成但没有产生可消费的规则事实。`load_instrument_risk_facts()` 按合同要求 one current
V2 row，不允许从 repo 默认值、Candidate Scope、旧 instrument nullable 列或 JSON 报告回退。

### 3.5 排除项

| 假设 | 结论 | 证据 |
| --- | --- | --- |
| Owner 风险参数不合法 | **排除** | 失败发生在 membership 查询，尚未进入容量计算 |
| PG 写入留下半成品 | **排除** | 单事务回滚；policy/current membership 均为 0 |
| lifecycle capability 阻止 policy | **排除** | lifecycle capability 已 exact-head 认证 enabled；policy 是独立前置权威 |
| 交易所或账户不安全 | **排除** | 本次路径未调用交易所写接口；此前账户只读事实安全 |
| 只改 `crypto` 为 `crypto_usdm_perp` 即可完成 | **排除** | identity 必填字段与 current rule snapshot 仍缺失 |

## 4. 方案比较

| 方案 | 做法 | 优点 | 主要风险 | 结论 |
| --- | --- | --- | --- | --- |
| A. 修改一个 literal | `crypto` 改为 `crypto_usdm_perp` | 最快 | 固化错误分类；policy 后立即停在 identity/rule blocker | **拒绝** |
| B. 删除 asset-class 条件 | 仅按 active mapping + exchange 选择 | 可生成 6 个 membership | 仍使用 symbol mapping 重选身份；identity/rule 不完整 | **拒绝作为最终方案** |
| C. 原地改 6 个 instrument 字段 | 把现有 ID 的元数据改为规范值 | 迁移较短 | 违反 immutable identity 规则；历史 lane/signal 语义被改写 | **拒绝** |
| D. 规范身份替换并闭合规则事实 | 新 identity/version、active scope 切换、V2 rule projector、exact-ID membership builder | 满足当前链路和未来资产类型边界 | 需要受控 migration、22-lane recertification 和一次生产切换 | **推荐** |

## 5. 目标架构

### 5.1 权威链

```text
PG StrategyGroup Candidate Scope
  exact exchange_instrument_id
        |
        v
PG Instrument Registry
  exchange_id + asset_class + instrument_type
  settlement_asset + margin_asset + identity_schema_version
        |
        v
PG Current Instrument Rule Snapshot V2
  tick + step + min_qty + min_notional + multiplier
  leverage ceiling + source + valid_until + semantic_hash
        |
        v
Policy-scoped Risk Cluster Membership Snapshot
        |
        v
Account Capacity -> Ticket -> FinalGate -> Operation Layer
```

### 5.2 Instrument Identity 决策

1. 现有 6 个 legacy identity 保留为历史 provenance，并转为 `retired`；不得删除或改写其
   已发生的 signal、coverage、invocation、outcome 或 Ticket lineage。
2. 为同一 6 个 venue contract 登记 **6 个新的 opaque canonical identity**。ID 通过稳定
   identity builder 生成，不允许消费者解析字符串获得业务语义。
3. 新 identity 的固定语义为：

| 字段 | Binance USD-M perpetual V0 值 |
| --- | --- |
| `exchange_id` | `binance_usdm` |
| `asset_class` | `crypto` |
| `instrument_type` | `perpetual` |
| `settlement_asset` | `USDT` |
| `margin_asset` | `USDT` |
| `instrument_identity_schema_version` | 新的明确版本 |
| `status` | `active` |

4. 22 条 current Candidate Scope 不能原地改变 immutable lane identity。迁移创建新的
   versioned candidate scope rows及其 event/runtime binding，旧 scope 转为 retired。
5. 新的 runtime instance、coverage 和 detector decision 必须从新 scope 重新产生；禁止把
   旧 signal 或 generated timestamp 转成新 identity 的 fresh signal。

### 5.3 Instrument Rule Snapshot 决策

新增或补全一个 **PG-only Instrument Rule Projector**：

1. 输入是 active canonical instrument set；
2. 通过现有 Binance `/fapi/v1/exchangeInfo` 与账户允许的 leverage bracket read-only 路径
   获取真实市场规则；
3. 生成 `InstrumentRuleSnapshotRefV2` 所需全部字段；
4. 同一 instrument 同时最多一个 `status=current` snapshot；
5. semantic hash 相同则幂等，不新增 row；语义变化时 supersede 旧 snapshot 并创建新 row；
6. 所有 Decimal 字段禁止使用 float；
7. 网络请求整体 timeout 不超过 **30 秒**，每次最多处理当前 6 个 instrument；
8. 不写 JSON/Markdown 文件，不在 no-signal watcher tick 重建规则。

规则刷新触发条件：

```text
deploy/bootstrap explicit trigger
or current rule near expiry
or exchange metadata semantic hash changed
```

它不是每 30 秒运行的 watcher 子步骤。

### 5.4 Risk Cluster Membership 决策

将 `_active_crypto_binance_memberships()` 替换为 application service，例如：

```text
build_runtime_scope_primary_cluster_memberships(
    conn,
    runtime_profile_id,
    risk_policy_version,
)
```

服务必须：

1. 直接读取 active Candidate Scope 的 exact `exchange_instrument_id`，不再通过 symbol
   mapping 重选 live-submit 身份；
2. 去重为 6 个 instrument；
3. 验证每个 instrument 是 active canonical identity；
4. 验证每个 instrument 恰有一个 fresh current V2 rule snapshot；
5. V0 对 `exchange_id=binance_usdm + asset_class=crypto + instrument_type=perpetual +
   settlement_asset=margin_asset=USDT` 生成 primary `crypto_usd_beta`；
6. 任一 instrument 缺失、歧义或不合格时整体 fail-closed，不生成部分 membership；
7. 返回 typed `RiskClusterMembership`，由现有
   `replace_risk_cluster_memberships()` 生成 versioned snapshot。

### 5.5 Policy 原子性

正式 policy 写入保持一个数据库事务：

```text
verify exact account + runtime profile scope
-> verify six canonical instrument identities
-> verify six fresh V2 rules
-> build six cluster memberships
-> append Owner policy event
-> replace current policy projection
-> replace membership snapshots
-> commit
```

任一步失败必须回滚全部写入。重试使用显式 `operation_id`，同一 operation 不得生成不同
policy payload。

## 6. Blocker 与 Owner 状态

新增或复用精确 blocker，不得归为 `waiting_for_market`：

| 条件 | first blocker | 分类 |
| --- | --- | --- |
| active scope 没有 exact instrument | `runtime_lane_identity_mismatch` | `runtime_data_gap` |
| instrument 仍是 legacy/incomplete | `instrument_identity_schema_invalid` | `engineering_handoff_gap` |
| current rule 缺失 | `instrument_rule_snapshot_invalid` | `runtime_data_gap` |
| rule 过期 | `instrument_rule_snapshot_stale` | `runtime_data_gap` |
| membership 不完整 | `risk_cluster_membership_missing_or_changed` | `engineering_handoff_gap` |
| Owner policy 未提交 | `account_risk_policy_missing_or_changed` | `policy_scope_missing` |

工程修复期间 Owner product state 应为 `temporarily_unavailable` 或
`needs_intervention`（仅 policy 数值未确认时）。本次 Owner 已确认风险数值，因此 identity、
rule 和 membership 缺口均为工程责任，不再要求 Owner 决策。

## 7. 关联影响面

| 层级 | 修改或重认证 | 不允许发生 |
| --- | --- | --- |
| Foundation seed | 停止创建 `crypto_usdm_perp` legacy identity | 不保留双 current identity |
| Candidate Scope | 创建新 versioned scope 并切换 bindings | 不原地改写历史 lane identity |
| Runtime instance / coverage | 对 22 lane 重新 bootstrap 和 certification | 不复用旧 signal freshness |
| Instrument rules | PG current V2 projector | 不从代码默认值或文件回退 |
| Account risk policy | 原子写 policy + membership | 不写半套 membership |
| Capacity / Ticket | 读取 exact identity/rule/cluster snapshot | 不放宽 FinalGate 或 sizing |
| Monitor / forensics | 显示精确 identity/rule blocker | 不显示普通 waiting market |

## 8. 性能与文件 I/O

| 项目 | 目标边界 |
| --- | --- |
| No-signal tick 文件增长 | **0 JSON/MD files** |
| Rule refresh cadence | explicit/near-expiry only，不进入每 tick 重建 |
| 单次网络范围 | 6 active instruments，整体 timeout ≤ 30s |
| PG current row 数 | 每 instrument 最多一个 current identity、一个 current rule、每 policy 一个 current primary membership |
| 历史 row 增长 | 仅 identity/rule/policy 语义变化时 append |
| CPU-heavy trigger | deploy/manual PG trigger，禁止 watcher broad rebuild |
| Archive | 手工、Owner scoped、retention bounded |

## 9. 安全、不变量与回滚

### 9.1 不变量

1. 不调用 FinalGate 或 Operation Layer 作为迁移/规则 bootstrap 的副作用。
2. 不调用交易所写接口，不创建订单，不改变凭证、profile 或 sizing defaults。
3. migration/cutover 期间 lifecycle capability disabled，production writer fence engaged。
4. 新 identity、rules、22-lane certification 与 current projection 未全部通过前，不恢复
   watcher 的 action-time ticket progression。
5. 任何历史 signal、ticket、order、position lineage 保留旧 identity，不重写 provenance。

### 9.2 回滚

若新 identity 或 rule certification 失败：

```text
keep writer fence engaged
-> keep lifecycle mutation disabled
-> restore previous release pointer if schema allows
-> retire incomplete new current scope generation
-> preserve all append-only audit rows
-> report temporarily_unavailable with exact blocker
```

不得回滚到 JSON/MD authority，也不得临时把 legacy identity 当作 current rule fact。

## 10. Live Enablement 状态迁移

```text
chain_position: action_time_boundary
strategy_group_id: all five active StrategyGroups
symbol: BTCUSDT, ETHUSDT, SOLUSDT, AVAXUSDT, SUIUSDT, OPUSDT
stage: account_risk_instrument_fact_readiness
first_blocker: instrument_identity_schema_invalid
evidence: Tokyo PG has 6 legacy crypto_usdm_perp identities with null dimensions and 0 rule snapshots
next_action: implement canonical identity replacement and current V2 rule projection before policy retry
stop_condition: all 22 lanes bind 6 complete canonical identities, each has one fresh V2 rule, and policy+membership transaction succeeds
owner_action_required: false
authority_boundary: design and future migration do not authorize exchange write, FinalGate bypass, Operation Layer bypass, scope expansion, or sizing expansion
signal_event_id: none required for engineering closure
promotion_candidate_id: none
action_time_lane_input_id: none
ticket_id: none
```

## 11. 架构决定

采用 **方案 D：规范身份替换并闭合规则事实**。这是对现有资产中立核心合同的落实，不是
新增兼容层。旧 `crypto_usdm_perp` seed 和 symbol-mapping membership builder 在新路径
验收后必须删除或失效，不能长期双轨运行。
