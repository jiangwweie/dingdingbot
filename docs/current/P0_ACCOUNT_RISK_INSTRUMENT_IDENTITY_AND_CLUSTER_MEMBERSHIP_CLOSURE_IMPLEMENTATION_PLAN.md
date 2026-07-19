---
title: P0_ACCOUNT_RISK_INSTRUMENT_IDENTITY_AND_CLUSTER_MEMBERSHIP_CLOSURE_IMPLEMENTATION_PLAN
status: OWNER_CONFIRMED_LOCAL_CERTIFIED_TOKYO_DEPLOY_PENDING
authority: docs/current/P0_ACCOUNT_RISK_INSTRUMENT_IDENTITY_AND_CLUSTER_MEMBERSHIP_CLOSURE_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-19 CST
---

# P0 账户风险品种身份与风险簇成员闭环执行方案

## 1. 目标与范围

本计划执行
`P0_ACCOUNT_RISK_INSTRUMENT_IDENTITY_AND_CLUSTER_MEMBERSHIP_CLOSURE_DESIGN.md`，目标是在当前
`codex/budget-model-review-20260714` 分支完成：

```text
6 canonical instruments
-> 22 versioned active candidate lanes
-> 6 fresh current V2 rule snapshots
-> 6 primary risk cluster memberships
-> 1 active Owner Account Risk Policy
-> natural Signal to Ticket acceptance
```

本计划不调整已确认的风险数值，不新增 StrategyGroup、symbol、side、venue、profile、
leverage 或 notional scope。

## 2. 当前基线

| 项目 | 当前状态 |
| --- | --- |
| 本地实现基线 | `92cce621` 上的未提交 P0 修复实现，待完成 commit/push |
| 东京 release | `brc-runtime-governance-ae0e0466-20260718T185000Z` |
| PG migration | **137** |
| Active lanes | **22** |
| Active mapped instruments | **6** |
| Canonical complete identities | **0** |
| Current V2 rule snapshots | **0** |
| Active Account Risk Policy | **0** |
| Active cluster memberships | **0** |
| lifecycle capability | 东京 exact-head certified enabled；部署切换时必须先 quiesce |

来源：当前 Git、东京 release manifest、东京 PG current 查询，2026-07-19。

### 2.1 本地完成与东京待执行边界

| 工作包 | 状态 | 结果 |
| --- | --- | --- |
| P0-ARIC-01 至 P0-ARIC-05 | **本地完成并认证** | 新增/更新测试均已通过；本地 PostgreSQL 完整走通 **106 → 138 → seed → rule projection → policy**。 |
| P0-ARIC-06 部署状态机 | **本地完成并认证** | writer fence 下的 migration 后，强制执行 GET-only rule projector 和 **22 lane / 6 identity / 6 rule** PG readiness certification。 |
| P0-ARIC-06 东京 apply | **待执行** | 仅在 commit/push 与本地全量验证通过后执行受控单事务部署。 |
| P0-ARIC-07 自然信号 | **待市场事件** | 不伪造 signal、Ticket 或交易所写入；自然新信号到来后只接受合法 Ticket 或精确 blocker。 |

## 3. 执行顺序

| 阶段 | 产出 | 允许副作用 | 硬停止条件 |
| --- | --- | --- | --- |
| 0. 基线冻结 | 当前 22 lane / 6 instrument / rule / policy 快照 | 只读 | 有 active real lifecycle、unknown command、unprotected position |
| 1. 共享语义实现 | typed identity/rule/membership builders | 本地代码与测试 DB | 需要放宽 FinalGate、Operation Layer 或 scope |
| 2. Migration 138 | 新 canonical identities 与 versioned scope generation | 测试 PG | 历史 lineage 会被重写或新旧 current 并存 |
| 3. Rule projector | 6 个 fresh V2 rule snapshots | read-only exchange GET + PG rows | 任一 exchange rule 缺失、歧义或超时 |
| 4. Policy transaction | 1 active policy + 6 current memberships | PG policy event/current | membership 数量不等于 6 或 scope/account 不匹配 |
| 5. 22-lane recertification | 新 identity coverage / detector / current projections | PG runtime current | 任一 lane 缺 exact identity 或 rule |
| 6. 东京部署验收 | current release + timers + monitor | release/systemd/PG | writer fence、capability、timer 状态不一致 |
| 7. 自然信号验收 | Signal → Ticket 或精确实时 blocker | 正式 pre-trade PG rows | stale fact、duplicate risk、missing protection、account conflict |

## 4. 工作包与任务卡

### 4.1 Task P0-ARIC-01：失败分类与测试基线

**Goal**：用测试锁定当前三类失败，不先改生产逻辑。

**Allowed files**：

- `tests/unit/test_set_account_risk_policy.py`
- `tests/unit/test_instrument_risk_facts.py`
- `tests/integration/test_account_capacity_postgres.py`
- 新的 scoped PostgreSQL integration test

**Forbidden files**：

- Core execution files；
- live profile、credentials、sizing defaults；
- `output/**`。

**Requirements**：

1. 证明 `crypto_usdm_perp` active scope 在旧查询下返回 0 membership；
2. 证明删除该过滤后仍会因 incomplete identity 失败；
3. 证明 identity 补齐但无 rule 时失败为 `instrument_rule_snapshot_invalid`；
4. 证明整个 policy transaction 回滚，不留下 event/current/membership；
5. 证明非 active scope、foreign venue、ambiguous mapping 不进入新 current set。

**Done When**：RED 测试分别命中三个精确 blocker，没有泛化为 policy missing 或 waiting
market。

### 4.2 Task P0-ARIC-02：Canonical Identity 与 Seed 替换

**Goal**：删除新路径对 `crypto_usdm_perp` 的生产依赖，并创建规范 instrument identity。

**Allowed files**：

- `scripts/seed_runtime_control_state_foundation.py`
- instrument identity application/domain builder；
- seed tests；
- migration 138；
- 必要的 PG repository/service。

**Requirements**：

1. 新 seed 使用 `asset_class=crypto`、`instrument_type=perpetual`、
   `settlement_asset=margin_asset=USDT`；
2. 新 canonical ID 由一个稳定 opaque builder 产生，业务代码不得解析 ID；
3. 旧 6 identity 保留但 retired；
4. 新建 22 个 versioned candidate scope rows，旧 scope retired；
5. event bindings、runtime scope bindings 与 Owner policy binding 精确迁移；
6. 不迁移旧 signal 的 freshness，不改历史 Ticket/outcome identity；
7. migration preflight 要求当前恰为预期 22 lane / 6 instrument，数量不同立即失败；
8. migration 使用 `lock_timeout=5s`、`statement_timeout=60s`。

**Negative tests**：

- 新旧 identity 同时 active；
- 一个 symbol 映射到两个 active canonical instrument；
- active lane 未完成 binding；
- settlement/margin 空值；
- migration 中断后的 current generation 不完整。

**Done When**：隔离 PG 中 22/22 lane 只绑定 6 个新 canonical identity，旧 identity/scope
只作为 provenance。

### 4.3 Task P0-ARIC-03：Instrument Rule Projector

**Goal**：从真实 read-only exchange metadata 生成 PG current V2 rules。

**Allowed files**：

- 新的 application projector/service；
- `scripts/fetch_binance_usdm_public_facts.py` 中可复用的纯解析逻辑；
- `scripts/collect_strategy_group_live_facts_readonly.py` 中可复用的 leverage/rule parsing；
- 新的 PG-only ops entrypoint；
- focused tests。

**Architecture constraint**：解析逻辑应抽到可复用 typed application/domain 模块，不能让新
projector 读取旧 JSON/Markdown 文件或调用旧 artifact CLI。

**Requirements**：

1. Binance `exchangeInfo` 提供 price tick、quantity step、min qty、min notional；
2. leverage bracket 或现有受信事实提供 claim-notional leverage ceiling；
3. `contract_multiplier=1` 只在 exchange contract facts 明确证明线性 quote-settled 时写入；
4. 生成 `rule_schema_version=v2`、`risk_calculation_kind=linear_quote_settled`；
5. Decimal 端到端，不使用 float；
6. source fact ID、validity、semantic hash 完整；
7. semantic hash 未变时零新增 row；
8. 更新时在一个事务中 supersede old + insert new；
9. 单次最多 6 个 instrument，timeout ≤ 30s；
10. `exchange_write_called=false`、0 files written。

**Done When**：6/6 canonical instrument 恰有一个 fresh current V2 rule，typed loader 全部
通过。

### 4.4 Task P0-ARIC-04：Exact-Scope Membership Builder

**Goal**：从 exact active scope 与完整 instrument facts 生成 6 个 primary membership。

**Allowed files**：

- `scripts/ops/set_account_risk_policy.py`
- `src/application/action_time/account_risk_policy.py`
- 新的 scoped membership service；
- focused unit/integration tests。

**Requirements**：

1. 删除 `_active_crypto_binance_memberships()`；
2. 新 service 直接读取 Candidate Scope 的 `exchange_instrument_id`；
3. 不通过 symbol mapping 重选 live identity；
4. 验证 canonical identity 和 current rule；
5. 6 个 instrument 均映射 primary `crypto_usd_beta`；
6. 返回数量不是 6、存在 duplicate/foreign/incomplete row 时 fail-closed；
7. policy event/current/membership 同一事务；
8. operation ID 幂等；
9. policy 参数仍全部显式，无默认值。

**Done When**：已确认的 Owner policy 在测试 PG 中产生 1 current policy、6 current
membership snapshots，任何负例均产生 0 committed policy rows。

### 4.5 Task P0-ARIC-05：全链路 PostgreSQL 认证

**Goal**：证明修复不止让 policy 命令成功，还能进入 Account Capacity 与 Ticket。

**Tests**：

1. 22 lane identity conservation；
2. 6 instrument identity + V2 rule + membership typed loading；
3. account budget current 与 policy version 对齐；
4. same cluster held risk 正确累计；
5. two concurrent positions、6% portfolio、4% cluster、90% initial margin、10x ceiling；
6. automatic downsize 只能缩小，不能扩大 base sizing；
7. missing/stale/changed rule 或 membership 在 Ticket 前 fail-closed；
8. missing FinalGate ticket ID 和 missing Operation Layer pass ID 继续拒绝；
9. no exchange write full-chain fixture；
10. production file-I/O audit clear。

**Done When**：合法 fixture 到达 Ticket；所有负例留下精确 blocker；无测试通过直接插入
下游 ready rows 伪造能力。

### 4.6 Task P0-ARIC-06：东京部署与 Policy Apply

**Predeploy hard stop**：

```text
active unsafe lifecycle > 0
or unknown exchange command > 0
or unprotected real attempt > 0
or current position/open order identity ambiguous
```

**Deploy sequence**：

```text
readonly preflight
-> engage production writer fence
-> stop watcher/monitor/lifecycle/backend
-> disable lifecycle mutation capability
-> apply migration 138
-> publish 6 canonical identities and 22 current scopes
-> run read-only rule projector
-> certify 6/6 rules and 22/22 lane identities in PG
-> exact-head lifecycle phase-two certification
-> publish current projections
-> remove fence and restore timers
-> postdeploy readonly verifier
```

Policy apply 必须在 postdeploy accepted 后单独执行：

```text
set_account_risk_policy.py --mode activate
-> 1 Owner policy event/current
-> 6 current primary cluster memberships
-> read-only verification
```

部署与 policy apply 都不得产生 signal、Ticket 或订单作为人为副作用。

### 4.7 Task P0-ARIC-07：自然信号验收

等待新的自然 fresh signal，并验证：

```text
Signal
-> Invocation exact new lane identity
-> fresh account capacity base
-> current Account Risk Policy
-> current Instrument Rule V2
-> current primary cluster membership
-> reservation
-> Promotion Candidate
-> Action-Time Lane
-> Ticket
```

若任一步失败，只接受精确 blocker。禁止复用历史信号、修改 event time、伪造 Ticket 或手工
调用交易所。

## 5. 预计修改文件

| 文件/区域 | 预期动作 |
| --- | --- |
| `scripts/seed_runtime_control_state_foundation.py` | 删除新 seed 的 legacy composite asset class |
| `scripts/ops/set_account_risk_policy.py` | 使用 exact-scope membership service |
| `src/application/action_time/account_risk_policy.py` | 保留 versioned snapshot owner，必要时增加 typed orchestration |
| 新 instrument identity service | 生成/验证 opaque canonical identity |
| 新 rule projector service | 真实 GET facts → PG current V2 rule |
| migration 138 | 规范 identity 与 versioned 22-lane scope cutover |
| `tests/unit/*`、`tests/integration/*` | identity、rule、membership、policy、capacity、Ticket 负例/正例 |
| current contracts | 记录 canonical classification 与 cutover 状态 |

默认不修改 AGENTS.md 列出的 execution、gateway、reconciliation core 文件。若真实 GET rule
producer 无法复用现有 read-only source，必须先停在架构审查，不得顺手扩展 ExchangeGateway
写路径。

## 6. 测试矩阵

| 测试层 | 必须覆盖 | 通过标准 |
| --- | --- | --- |
| Domain | identity/rule hash、Decimal、cluster semantics | 纯逻辑、无 I/O |
| Unit | selector、projector parsing、policy atomicity | 正负例均精确 blocker |
| SQLite fixture | 仅轻量 shape | 不作为 PG 锁/事务证明 |
| PostgreSQL integration | migration、unique current、row lock、rollback | 全部原子不变量成立 |
| Production-shaped | 22 lane / 6 instrument / policy / Ticket | `exchange_write_called=false` |
| Deploy state machine | fence、capability、timer restore | 终态只能 healthy 或 safe-contained |
| Tokyo readonly | release、migration、PG counts、monitor | current truth 与目标一致 |

## 7. 回滚计划

### 7.1 Migration 前失败

保持旧 release、旧 PG current、原 timers；不执行 policy apply。

### 7.2 Migration 后、activation 前失败

保持 writer fence、timers stopped、lifecycle capability disabled；执行前向修复或迁移提供的
受控 current-generation rollback，不删除 append-only identity/scope provenance。

### 7.3 Activation 后 verifier 失败

进入 `safe_contained`。若 schema 兼容，恢复 previous release pointer；否则继续前向修复。
禁止重新激活 legacy `crypto_usdm_perp` 作为长期 current authority。

### 7.4 Policy apply 失败

事务整体回滚；生产继续观察但 Ticket fail-closed。不得手工插 policy/current/membership row。

## 8. 验收清单

- [ ] 新 seed 不再产生 `crypto_usdm_perp` current identity；
- [ ] 旧 6 identity 与旧 22 scopes 保留 provenance 且 retired；
- [ ] 新 6 canonical identities 字段完整；
- [ ] 新 22 active scopes 直接绑定 exact canonical identity；
- [ ] 6/6 current V2 rule snapshots fresh；
- [ ] 规则 semantic hash 幂等且更新可 supersede；
- [ ] policy apply 原子产生 1 current policy + 6 memberships；
- [ ] Account Capacity 按 portfolio/cluster/position/margin limits 工作；
- [ ] 22/22 lane exact-head certification；
- [ ] watcher/monitor/lifecycle timers healthy；
- [ ] file-I/O audit `performance_risk.status=clear`；
- [ ] no signal/ticket/order/exchange write during deploy；
- [ ] 新自然 signal 到达 Ticket 或精确安全 blocker。

## 9. 完成定义

本计划只有在以下条件同时满足时完成：

1. 生产 current identity 和 rule facts 满足资产中立合同；
2. Owner 已确认 policy 成为 PG current authority；
3. 6 个 instrument 的 cluster membership 完整且 versioned；
4. 22 条 active lane 经过新 identity recertification；
5. 自然 signal 能进入合法 Ticket 或留下实时安全 blocker；
6. 所有 FinalGate、Operation Layer、protection、duplicate-submit、reconciliation 边界保持
   fail-closed。

## 10. 当前停止点

Owner 已确认实施与受控部署。东京 apply 前仍必须满足本计划的 predeploy hard stop；任何
migration、rule projection、22/6 readiness certification 或 lifecycle certification 失败都保持
writer fence、lifecycle capability disabled、Ticket fail-closed，不能恢复 watcher 或 policy apply。
