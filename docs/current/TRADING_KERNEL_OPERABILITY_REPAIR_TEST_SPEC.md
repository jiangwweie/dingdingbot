---
title: TRADING_KERNEL_OPERABILITY_REPAIR_TEST_SPEC
status: CURRENT
last_verified: 2026-07-31
---

# Trading Kernel 可运行性修复测试规格

## 1. 测试目的

本规格把可运行性修复的每个业务与部署不变量转换为本地可重复的观察断言。确定性问题
必须优先在本地 unit、disposable PostgreSQL、production-shaped virtual time 和 recording
venue 中暴露；Tokyo 只验证当前外部事实，不承担程序调试职责。

未通过本规格全部 hard gate，不得声明 **fixed、deployable 或 production-ready**。

## 2. 强制原则

1. 每个生产行为先观察 RED，再实现 GREEN，最后 REFACTOR；
2. 删除编码过时语义的测试，不为旧测试增加 compatibility；
3. PostgreSQL 行为只使用 disposable PostgreSQL；
4. migration 测试同时覆盖 empty base-to-head 与 production-shaped v4-to-head；
5. recording venue 必须证明 rehearsal 零 exchange mutation；
6. 时间、公平性、lease、crash/resume 使用虚拟时钟和独立 cadence；
7. 网络 I/O 不进入数据库事务；
8. full-chain fixture 不得绕过真实 producer 或 durable Command boundary；
9. stable current documents 不复制生产 commit、tag、Ticket 或 transient test count；
10. `MAIN_CONTROL_ROADMAP.md` 未经真实部署证据不得更新生产身份。

## 3. Traceability

| Requirement | Defect | 最低证据 | Pass 条件 |
| --- | --- | --- | --- |
| **R-01 Reconciliation fairness** | OR-P0-01 | Unit + production-shaped full-chain | Safety 持续有工作时 Housekeeping 仍按 deadline 推进 |
| **R-02 Flat Entry Promotion** | OR-P0-02 | Unit + Integration + Architecture | active exposure 不能 promotion；flat exact identity 可恢复 Entry |
| **R-03 Certification/Admission** | OR-P1-01/02 | Unit + PostgreSQL + full-chain | Batch 完成且 action-time fresh eligible 才进入 arbitration |
| **R-04 Multi-ticket capacity** | OR-P1-04 | Domain + PostgreSQL race | 账户 3、同策略 2；第三个同策略 fail-closed |
| **R-05 Forward migration** | schema evolution | PostgreSQL migration + digest | exact `0001 -> 0002`，v4 columns 完全保留 |
| **R-06 Deployment recovery** | OR-P1-03 | Unit + state-machine rehearsal | 每个 phase failure 只执行允许恢复动作 |
| **R-07 Retirement** | architecture drift | Source/document scans | 无 active-position deployment surface、fallback 或旧 reader |

## 4. RED/GREEN 规格

### 4.1 Scheduler fairness

构造三个不同 Netting Domain 的 active protected Ticket，并让 Safety lane 每 **2 秒**持续
到期；同时让 certification/Universe/monitor Housekeeping 每 **5 秒**到期。RED 必须证明
旧排他 selector 会饿死 Housekeeping，GREEN 必须证明：

- 两条 lane 各自 claim；
- Safety 不退化；
- Housekeeping 在 bounded delay 内推进；
- duplicate current upsert 不产生 append-only 噪声。

这里的 active position 只验证正常 runtime 调度，不授权 deployment handover。

### 4.2 Certification Batch

必须覆盖：

1. 六 Event、七 instrument manifest digest 稳定；
2. member success/failure/timeout 独立记录；
3. Warming scope 产生零 StrategySignal；
4. 全部 eligible 后一次原子 Active pointer switch；
5. 一个 member stale/failed 时 Batch 不完成；
6. exact Warming 可由官方 abandon CLI 终结并释放 slot；
7. direct SQL 或匿名 slot clearing 不存在；
8. repeated bootstrap 对 exact completed state 幂等。

### 4.3 Candidate Admission

Ready query 必须连接 exact current Universe、Active scope 和 fresh eligible certification。
覆盖 stale、retired、warming、identity mismatch、temporarily unavailable、duplicate Signal 和
Batch-complete-but-action-time-stale。

### 4.4 Capacity

必须证明：

- Owner Policy 只接受正整数 `max_strategy_group_concurrent_tickets=2`；
- 0/1 个同策略 active Ticket 允许，2 个时第三个 Claim 返回
  `strategy_group_capacity_exhausted`；
- SOR Long/Short 与不同 instrument 合并计数；
- venue/account 隔离；
- 两个 SOR + 一个 MI 可达到账户总容量 3；
- Claim 后计数变化时 ENTRY Preflight fail-closed；
- Ticket issue transaction 再次计数，拒绝不创建 Ticket、Reservation、Command 或 Incident；
- 3%/6%、45%/90%、5x/10x、cross 参数不发生扩大。

### 4.5 Entry Promotion

RED 必须覆盖：

1. active Ticket、non-flat internal position、exchange position、open order 任一存在；
2. active Reservation、held Netting Domain、unresolved Command、open Incident 任一存在；
3. Universe、Batch、Policy、commit、schema、seed 或 capability identity 不一致；
4. Entry 未 fenced、旧 writer 未停或 safety worker 不稳定；
5. final postflight facts 漂移；
6. Policy version 为零、负数、布尔值或固定历史版本假设。

GREEN 必须证明 exact flat state 可按以下顺序完成：

```text
preflight
-> readonly exchange rules/flatness
-> safety workers stable
-> monotonic Owner Policy arm when needed
-> Entry start while fenced
-> final postflight
-> remove fence
```

### 4.6 Schema compatible migration

必须证明：

1. revision graph 精确为
   `0001_trading_kernel_baseline_v4 -> 0002_sor_v3_strategy_group_capacity`、
   单 head、无分叉；
2. `0001` 使用 frozen v4 snapshot，head metadata 变化不改变 v4 创建结果；
3. empty PostgreSQL 严格执行 base-to-head；
4. production-shaped v4 只执行 `0002`；
5. migration 不删除或终结 Ticket；部署 preflight 负责要求 flat；
6. 所有 v4 table/exact v4 columns 的 canonical SHA-256 在迁移前后相同；
7. 任一 v4 原始值被改变时 preservation gate 失败；
8. `alembic_version` 和 v5-only columns 不进入 preservation digest；
9. 出现 v3 runtime row 后 downgrade 明确拒绝；
10. 无 `DROP SCHEMA`、dual write、old-table reader 或 schema fallback。

### 4.7 Runtime authority transition

必须证明：

- v2 SOR Registry/Policy scope 单调切换到 v3；
- Owner Policy 使用 `current_version + 1`，资本参数保持不变；
- metadata、capability、commit、schema、seed 同事务更新；
- source revision 或 source policy 不精确时 fail-closed；
- 未改变业务语义的非 SOR v2 Event 必须精确接受 frozen v4 Contract 字段集合计算出的
  历史 `event_semantic_hash`，任意其他 hash 仍 fail-closed，且 migration 不重写历史行；
- active Ticket、position、Reservation、Domain、unreviewed terminal Ticket、Command 或
  Incident 会拒绝 compatible transition；
- closure-only 与 recovery identity 的既有安全路径不被误删。

## 5. Deployment State Machine Fault Matrix

| 注入点 | 数据库期望 | Worker 期望 | Entry 期望 | 恢复 |
| --- | --- | --- | --- | --- |
| source preflight 前 | source revision 未变 | 旧 worker 原状态 | fenced/不扩大 | 修复事实后重试 |
| stop workers 后、migration 前 | source revision 未变 | 全停 | fenced | 可恢复 source safety workers |
| migration transaction 内 | rollback 到 source | 全停 | fenced | 查明 DDL 后重试 |
| migration 后、identity 前 | target revision | 全停 | fenced | target fix-forward |
| identity 后、Universe 前 | target identity | safety workers 可启动 | fenced | 重试 bootstrap |
| Entry start while fenced 后 | target exact | safety workers stable | active but fenced | final postflight 或 restore fence |
| unfence 后异常 | target exact | safety workers继续 | 立即恢复 fence | readonly diagnosis + fix-forward |

每个 phase 必须写 journal，重复执行只允许 exact-idempotent resume，不允许重新运行已经完成的
破坏性或不可逆阶段。

## 6. Local Rehearsal

### 6.1 环境

- disposable PostgreSQL；
- committed release-shaped filesystem adapter；
- fake systemd state；
- recording readonly venue；
- virtual clock；
- 禁止真实 SSH 与交易所 mutation。

### 6.2 必须完成

1. empty base-to-head bootstrap；
2. production-shaped v4 preservation fixture；
3. source gate 与 final flat recheck；
4. exact migration 与 digest comparison；
5. v3 Registry/Policy/runtime identity transition；
6. safety workers first；
7. one bounded six-Event Universe bootstrap；
8. Entry last；
9. crash/resume 覆盖每个 journal phase；
10. recording venue mutation list 为空。

## 7. Static 与架构门

必须运行：

```bash
pytest -q tests/trading_kernel
pytest -q tests/trading_kernel/architecture
ruff check src/trading_kernel scripts/trading_kernel tests/trading_kernel
mypy src/trading_kernel scripts/trading_kernel
git diff --check
```

架构扫描必须证明：

- production execution 只在 `src/trading_kernel/**`；
- schema 只在 `migrations/trading_kernel/**`；
- revision chain 精确且单 head；
- deployment authority 无 protected Ticket manifest/CLI/promotion；
- current 文档无矛盾的 rebuild-only 或 active handover 正向语义；
- no-signal cadence 无文件增长；
- 无 timer worker、retired table、compatibility module 或 parallel chain。

## 8. Tokyo Readonly Smoke

部署前重新读取：

1. exact production commit/tag/schema/seed；
2. PostgreSQL Ticket、Reservation、Domain、Command、Incident、Review；
3. exchange account mode、margin mode、configured leverage；
4. full-account position 与 open order truth；
5. systemd worker 与 write fence；
6. available disk/memory 与 release paths。

部署后重复以上事实，并验证 v3 Registry/Universe、preserved history digest、四 worker、Entry
状态和零 exchange residue。Tokyo smoke 是 release acceptance，不替代本地测试。

## 9. Release Candidate 判定

### 9.1 Pass

只有以下全部成立才允许形成部署 commit：

- 所有 targeted 与 proportional regression 通过；
- PostgreSQL preservation 与 empty upgrade 通过；
- state-machine crash/resume 通过；
- recording venue 零 mutation；
- architecture、Ruff、Mypy、diff checks 全绿；
- diff 中无未解释范围扩大；
- current 文档与代码一致；
- 未修改 `MAIN_CONTROL_ROADMAP.md` 的未部署生产事实。

### 9.2 Hard Fail

以下任一情况直接阻止部署：

- active exposure 被 schema migration 接管；
- history digest 不一致；
- old/new writer 可能重叠；
- Entry 在 final postflight 前 unfence；
- Policy 资本参数被扩大；
- unknown outcome 可重发；
- exchange mutation 没有 durable Command；
- 通过 fallback、旧 reader、direct SQL 或手工 exchange order 完成迁移；
- 只运行 targeted tests 就宣称 deployable。
