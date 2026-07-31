---
title: TRADING_KERNEL_OPERABILITY_REPAIR_DESIGN
status: CURRENT
last_verified: 2026-07-31
---

# Trading Kernel 可运行性修复设计

## 1. 文档定位

本文件定义 **StrategyUniverse、持续认证、运行时调度、Entry Promotion、容量与部署迁移**
的当前目标语义。实际生产 commit、tag、schema、Ticket 和服务状态只由
`MAIN_CONTROL_ROADMAP.md` 记录。

本修复不增加第二执行链。错误或过时的控制流、测试、fixture、部署参数和文档语义
直接删除或重写，不通过兼容 adapter、旧表 reader、双写或 fallback 延续。

## 2. 产品与架构目标

动态 StrategyUniverse 的目标是让六个 Strategy Event 共享一套可认证、可切换、可冻结
lineage 的标的范围，而不是让操作员逐 Event、逐标的等待部署。目标链保持：

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

生产继续由四个常驻 worker 分工：

| Worker | 唯一职责 | 并发语义 |
| --- | --- | --- |
| Observation | closed-candle Facts、detector、Signal、Universe warming observation | bounded polling，无文件输出 |
| Entry | readiness、arbitration、Claim、Ticket、ENTRY dispatch | 新 ENTRY 全局串行 |
| Lifecycle | Initial Stop、TP1、Runner、受控 EXIT | 按 Ticket 并发 |
| Reconciliation | exchange truth、unknown outcome、closure、Settlement、Review、certification housekeeping | Safety 与 Housekeeping 双 lane |

不新增第五个认证 worker，不恢复 timer 冷启动，也不让部署脚本代替正常 runtime 生产
Signal 或执行生命周期。

## 3. 缺陷与结构性修复

| ID | 根因 | 结构性修复 | 验收结果 |
| --- | --- | --- | --- |
| **OR-P0-01** | active-position Safety 工作永久排斥 Housekeeping | Reconciliation 使用独立 lane、独立 claim 与公平调度 | protected Ticket 存在时 certification、monitor、closure 仍推进 |
| **OR-P0-02** | 发布语义混合了 active exposure 与 schema 迁移 | schema change 仅允许 **internal/exchange flat compatible upgrade** | 任何 active Ticket、position 或 open order 均 fail-closed |
| **OR-P1-01** | 部署认证与 candidate admission 使用不同 freshness 语义 | Certification Batch 证明 release 能力；action-time certification 决定 admission | stale/failed scope 不进入仲裁 |
| **OR-P1-02** | 单标的 TTL 被误作整批完成窗口 | Batch 拥有独立 deadline、member 状态与 manifest digest | 七标的一次有界部署，不要求操作员逐项安装 |
| **OR-P1-03** | 部署失败恢复不区分 phase | PostgreSQL operation journal + phase-aware resume | 每个 phase 只执行允许的恢复动作 |
| **OR-P1-04** | 账户并发上限不能保证多策略机会共存 | 账户容量 **3**、同 StrategyGroup 容量 **2**，Claim/Preflight/Issue 四层重验 | 两个 SOR 与一个其他策略可竞争账户容量 |

## 4. Certification 与 Admission

### 4.1 持续认证

每个 `runtime_profile + exchange_instrument_id` 的 current certification 使用有界 upsert。
认证记录至少冻结：

- instrument rules 与 configured leverage；
- account mode、margin mode 与 readonly scope；
- observation/certification 时间；
- eligibility、blocker 与 valid-until；
- target commit、schema、seed 与 profile identity。

部署认证不是长期交易授权。Signal admission、CapacityClaim 与 ENTRY dispatch 都必须按各自
动作时刻重新读取 current facts。

### 4.2 Certification Batch

一次发布或显式重认证创建一条 Batch，并冻结：

- target commit、schema、seed、runtime profile 与 Owner Policy version；
- 六个 Event、七个 approved instrument 的 canonical manifest digest；
- member 总数、eligible 数量、开始时间、deadline、完成状态；
- 每个 member 的独立结果和稳定 blocker code。

PostgreSQL 可以内部串行 Warming slot，但 operator 只发起一次 bounded bootstrap。Warming
scope 只读市场与账户事实并且产生零 StrategySignal；全部 member 通过后才原子切换 Active
pointer。

### 4.3 Candidate Admission

Ready candidate 查询必须连接 exact current Universe、scope lifecycle 和 fresh eligible
certification。部署 Batch 完成不能替代 action-time admission，stale、retired、warming 或
identity-mismatch scope 均不得进入 arbitration。

## 5. Reconciliation 双 Lane

Safety lane 处理 unknown outcome、partial fill、protection、exit 和 active Ticket
reconciliation；Housekeeping lane 处理 certification、Universe、monitor、Settlement 和
Review closure。两条 lane 使用独立 claim identity 和 bounded selector，任何一条持续有工作
都不能永久饿死另一条。

公平性以 production-shaped virtual clock 验证，不使用同步 fixture 消除真实 `5s/2s`
cadence 竞争。

## 6. 容量与风险语义

Owner-approved production policy 保持：

| 边界 | 值 | 含义 |
| --- | ---: | --- |
| 账户并发 Ticket | **3** | 全账户上限 |
| 同 StrategyGroup 并发 Ticket | **2** | 跨 side、instrument 合并计数；venue/account 隔离 |
| 单 Ticket stop risk | **3%** | action-time 上限 |
| 账户 gross stop risk | **6%** | Reservations 后的总上限 |
| 单 Ticket initial margin | **45%** | action-time 上限 |
| 账户 gross initial margin | **90%** | Reservations 后的总上限 |
| configured leverage | **5x** | exchange readonly exact fact |
| leverage safety ceiling | **10x** | 绝对上限，不是 Ticket selector |
| margin mode | **cross** | 账户固定模式 |

容量不按三个固定等额 slot 分配。前两个 Ticket 可各自达到单 Ticket 上限，第三个只能使用
剩余风险、保证金和 venue minimum 允许的容量。StrategyGroup 计数必须在 Owner Policy、
CapacityClaim、ENTRY Preflight 和 Ticket issue transaction 四层一致重验。

## 7. Entry Promotion

Entry Promotion 只有 **flat 模式**：

1. Entry service inactive/disabled，write fence 存在；
2. PostgreSQL 零 active Ticket、non-flat position、active Reservation、held Netting Domain、
   unresolved Command 和 open Incident；
3. exchange readonly 零 position domain 和零 open-order domain；
4. exact Active Universe、Certification Batch、runtime profile、Owner Policy、commit、schema、
   seed 和 capability identity 全部一致；
5. Observation、Lifecycle、Reconciliation active/stable；
6. Owner Policy 以正整数版本单调前进，Entry 在 fence 内启动；
7. final postflight 重复全部门后才移除 fence。

任何 active exposure 都必须先通过官方 Lifecycle/Reconciliation 达到 terminal、reviewed、
internal/exchange flat。部署工具不接管仓位，不通过 manifest 复用旧 Ticket，也不重新解释
v2 Ticket。

## 8. Schema 与部署模型

### 8.1 Revision authority

唯一 revision chain 为：

```text
0001_trading_kernel_baseline_v4
-> 0002_sor_v3_strategy_group_capacity
```

`0001` 是 migration-owned frozen v4 snapshot；current `pg_models.py` 只表示 head。禁止
`has_column`、`IF NOT EXISTS` 或 runtime metadata 猜测迁移顺序。

### 8.2 Regular release

Regular release 不改变 schema。它要求当前 revision 已等于 target，完成 flat preflight、
release switch、identity rotation、安全 worker 启动、readonly postflight，并在显式授权时
最后启动 Entry。

### 8.3 Flat compatible upgrade

Schema change 只接受 exact `0001 -> 0002`：

1. stage exact committed release；
2. 验证 source revision、历史 terminal/reviewed、Reservation/Domain released；
3. 验证 PostgreSQL 与 exchange flat、零 residual order、Command、Incident；
4. fence Entry，停止四个旧 writer，再原子重复 flat checks；
5. 对每张 v4 表的 exact v4 columns 计算 canonical SHA-256 manifest；
6. 执行单一 certified Alembic revision，不删除 schema；
7. 用相同表与列集合重算并精确比较 digest；
8. 同一事务切换 SOR v3 Registry、创建 `current policy version + 1`、更新 commit/schema/seed
   capability identity；
9. 启动三个 safety worker，完成一次 six-Event Universe bootstrap；
10. final database/history/exchange/Universe/worker/identity postflight 后 Entry 最后启动。

迁移成功后若 postflight 失败，系统保持 Entry-fenced 并在 target schema 上 fix-forward；不得
用旧 runtime 访问新 schema。迁移前失败且数据库仍处于 source revision 时，才允许恢复旧
安全 worker。

## 9. 数据与事务边界

- Registry 定义 Strategy/Event 语义；StrategyUniverse 定义 current member scope；
- Owner Policy 定义允许范围与资本边界；
- PostgreSQL 存 current truth 与 append-only lineage；
- exchange readonly facts 存外部真相；
- 每个 exchange mutation 必须先持久化 durable Exchange Command；
- network I/O 始终位于数据库事务外；
- runtime 查询使用 exact identity 或 bounded actionable selector；
- healthy idle cadence 创建零 JSON/Markdown 文件。

## 10. 退休清单

必须删除或保持不存在：

- active-position schema deployment handover；
- protected Ticket promotion manifest 与 CLI 参数；
- dual write、v4 runtime reader、schema fallback、平行 execution chain；
- “只能有一个 migration 文件”的旧断言；
- schema-changing deployment 中的 `DROP SCHEMA`；
- SOR v2 持续状态 producer 与 active execution compatibility；
- 固定 `policy_version == 2` 的 Promotion 假设；
- 逐 Event/逐标的人工部署步骤；
- 让 server 首次暴露确定性程序错误的测试缺口。

## 11. 完成定义

本修复只有在以下全部成立时可判断 deployable：

1. Reconciliation Safety 与 Housekeeping 无饥饿；
2. Batch、Warming、Active pointer 与 candidate admission 语义一致；
3. 账户容量 3、同策略容量 2 在四层重验；
4. base-to-head 与 production-shaped v4-to-v5 均通过；
5. v4-column preservation digest 完全一致；
6. regular 与 compatible-upgrade 使用同一 flat safety boundary；
7. dry-run/rehearsal 对 recording venue 产生零 exchange mutation；
8. targeted、PostgreSQL、full-chain、architecture、Ruff、Mypy 和 diff checks 全绿；
9. current 文档不存在矛盾的旧部署语义；
10. Tokyo 部署前重新读取实际 PostgreSQL、systemd 与 exchange readonly facts。
