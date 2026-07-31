---
title: TRADING_KERNEL_OPERABILITY_REPAIR_EXECUTION_PLAN
status: CURRENT_PLAN
last_verified: 2026-07-31
---

# Trading Kernel 可运行性修复执行与部署计划

## 1. 执行结论

本计划分成两类交付：

1. **程序修复**：Reconciliation 公平调度、Certification Batch、admission、容量、SOR v3、
   单向 schema migration、flat Entry Promotion 与 phase-aware deployment；
2. **生产部署**：所有旧 exposure 先由官方 Lifecycle/Reconciliation 终结，再执行 exact
   `0001_trading_kernel_baseline_v4 -> 0002_sor_v3_strategy_group_capacity`
   flat compatible upgrade，保留 terminal history。

部署不需要 active Ticket 兼容层。历史 BNB 与错误语义 Ticket 通过 PostgreSQL terminal lineage
和 append-only Review 保留；任何活跃仓位都必须在 migration 前结束。

## 2. 全局规则

### 2.1 允许

- focused `codex/*` branch 和本地 commit；
- production-shaped disposable PostgreSQL；
- 删除或重写错误代码、测试、fixture 和文档；
- reviewed Tokyo service/release/database operation；
- readonly exchange/account/position/order verification；
- hard gate 全通过后的 official Entry Promotion。

### 2.2 禁止

- active exposure schema handover；
- direct SQL 修改 Ticket/Aggregate 生命周期；
- 手工交易所撤单、反向单或绕过 durable Command；
- dual write、v4 reader、schema fallback、parallel worker；
- credential mutation、transfer、withdrawal 或范围扩大；
- 未验证的 `MAIN_CONTROL_ROADMAP.md` 生产事实更新。

## 3. 工作流总览

```text
TC-00 baseline and decisions
-> TC-01 Reconciliation dual lane
-> TC-02 Certification Batch and admission
-> TC-03 Flat Entry Promotion
-> TC-04 Deployment state machine
-> TC-05 Capacity and forward schema migration
-> TC-06 Retire old semantics
-> TC-07 Local rehearsal and RC review
-> TC-08 Tokyo flat compatible upgrade
```

每个 Task Card 遵循：**RED -> GREEN -> REFACTOR -> targeted tests -> proportional
regression -> architecture/static gates**。

## 4. TC-00：基线与决策冻结

### 目标

- 记录 Owner-approved 风险与容量参数；
- 固定 revision chain、deployment mode 和 active-exposure hard stop；
- 将 production volatile facts 留在 `MAIN_CONTROL_ROADMAP.md`。

### Done

- 账户容量 3、同策略容量 2；
- 3%/6%、45%/90%、5x/10x、cross 不变；
- compatible upgrade 只允许 flat；
- 历史通过 terminal lineage 保留，不维护 active v2 runtime。

## 5. TC-01：Reconciliation 双 Lane

### 目标

关闭 active-position Safety 持续到期时 Housekeeping starvation。

### 实现

1. Safety 与 Housekeeping 使用独立 selector/claim；
2. selector 只查询 bounded actionable current state；
3. virtual clock 还原 `2s/5s` cadence；
4. 证明 unknown、partial fill、protection 优先级不回退；
5. 证明 certification、Universe、Settlement、Review 不被永久排斥。

### Hard Stop

不得通过降低 Safety 优先级、增加 timer worker 或全历史扫描实现公平。

## 6. TC-02：Certification Batch 与 Admission

### 目标

统一部署能力证明、持续 certification 和 action-time admission。

### 实现

1. Batch 冻结 target identity 和 seven-member manifest digest；
2. member 独立状态、deadline、eligible count；
3. Warming 只读且零 Signal；
4. 全部通过后 Active pointer 原子切换；
5. pending Batch 与 current certification 各自 independently due；
6. ready query 连接 exact Active scope 和 fresh eligible certification；
7. failed Warming 只通过 exact audited abandon CLI 终结。

### Hard Stop

不得让部署脚本伪造 market facts、逐 Event 人工安装或把 Batch completion 当成永久 ENTRY
授权。

## 7. TC-03：Flat Entry Promotion

### 目标

用同一 official Promotion abstraction 在 **internal/exchange flat** 条件下恢复新 ENTRY。

### 实现

1. certification 只输出 flatness、Universe、Batch、Policy、capability 与 identity；
2. probe 只验证全账户 flat、零 open order、independent sides、cross 和七标的 5x；
3. 删除 protected Ticket manifest、CLI 参数和 runtime authority transition；
4. Policy version 只要求正整数和 current lineage，不固定为 v2；
5. Entry 在 fence 内启动；
6. final postflight 后才 remove fence；
7. 失败统一 restore fence 并停 Entry，safety workers 保持。

### Hard Stop

任何 active Ticket、position、order、Reservation、Domain、Command 或 Incident 都必须拒绝
Promotion。

## 8. TC-04：Deployment State Machine

### 目标

使 regular release 与 schema-compatible upgrade 具有明确 phase、journal 和 resume 语义。

### 阶段

```text
PREFLIGHT
-> FENCE_ENTRY
-> STOP_OLD_WRITERS
-> FINAL_FLAT_RECHECK
-> CAPTURE_HISTORY_MANIFEST
-> MIGRATE_APPLICATION_SCHEMA
-> VERIFY_HISTORY_PRESERVATION
-> TRANSITION_RUNTIME_AUTHORITY
-> ACTIVATE_RELEASE
-> START_SAFETY_WORKERS
-> BOOTSTRAP_UNIVERSES
-> FINAL_POSTFLIGHT
-> START_ENTRY_LAST
```

### Recovery

- migration 前失败：source schema 未变时可恢复 source safety workers；
- migration transaction 失败：确认 rollback 后按 source 恢复；
- migration 后失败：Entry 保持 fenced，只在 target schema fix-forward；
- Entry start 后 postflight 失败：restore fence、disable Entry、保留 safety workers。

### Hard Stop

同一 operation 不得重复不可逆阶段；旧 writer 未全部停止不得执行 final flat recheck 或
migration。

## 9. TC-05：Capacity、Policy 与 Forward Migration

### 容量实现

1. Owner Policy 新增 `max_strategy_group_concurrent_tickets=2`；
2. Claim 冻结 strategy-group usage 与 decision digest；
3. ENTRY Preflight 重新读取；
4. Ticket issue transaction 在 global Entry Lane 内最终计数；
5. rejection 不创建 Ticket、Reservation、Command 或 Incident。

### Schema 实现

1. 冻结 migration-owned v4 schema snapshot；
2. revision graph 形成 `0001 -> 0002`；
3. 实现 event version coexistence、Episode、Exit Policy、capacity columns 与索引；
4. production-shaped v4 rows 精确回填；
5. downgrade 在 v3 row 出现后 fail-closed；
6. verify-schema 计算 exact v4-column canonical digest；
7. runtime authority 单调切换 Registry、Policy、metadata 与 capability identity。

### Hard Stop

不得用 `DROP SCHEMA`、`IF NOT EXISTS`、old-table reader 或 compatibility adapter 掩盖迁移
错误。

## 10. TC-06：删除旧语义与全局一致性

### 删除范围

- active-position deployment handover 与 fixture；
- protected deployment probe/promotion 参数；
- 固定 Policy v2 的 promotion 假设；
- SOR v2 persistent-state producer；
- rebuild-only schema authority；
- “migration 目录只能有一个文件”的测试；
- current 文档中的正向 active handover 描述；
- 任何 runtime Markdown/JSON authority。

### 验证

运行 source scan、current-document architecture test、revision graph test、Ruff、Mypy 和
`git diff --check`。

## 11. TC-07：Local Rehearsal 与 RC Review

### 执行

1. empty PostgreSQL base-to-head；
2. production-shaped v4-to-head preservation；
3. compatible source gate 与 final flat recheck；
4. state-machine failure injection；
5. Registry/Policy/runtime identity transition；
6. safety workers first；
7. one bounded six-Event Universe bootstrap；
8. Entry last；
9. recording venue 零 mutation；
10. complete tests、architecture、Ruff、Mypy、diff checks。

### RC Hard Gate

只有全部 fresh evidence 通过、diff 范围清晰且无 P0/P1 finding 时，才能创建 deployment
commit 和 immutable tag candidate。

## 12. TC-08：Tokyo Flat Compatible Upgrade

### 12.1 部署前事实刷新

必须直接读取：

- current production commit、tag、revision、seed、Policy；
- PostgreSQL active Ticket、Reservation、Domain、Command、Incident、Review；
- exchange full-account positions 与 open orders；
- account mode、cross mode、七 instrument configured leverage；
- four systemd workers、write fence、release paths、disk/memory。

### 12.2 Exposure Closure

若存在 active Ticket：

1. 写 Entry fence 并停止 Entry；
2. 保持 Observation、Lifecycle、Reconciliation；
3. 使用 official lifecycle 自然或受控终结 exact Ticket；
4. 等待 exchange flat、零 residual order；
5. 等待 internal terminal、Reservation/Domain released、Settlement/Review complete；
6. 禁止 direct SQL、手工 cancel、反向 order 或 schema mutation。

### 12.3 Plan

Plan 只读并输出 exact operation identity、source/target revision、release commit、history
manifest target 和所有 hard gate。任一矛盾时不执行 stop、migration 或 service switch。

### 12.4 Apply

```text
stage exact commit
-> source readonly preflight
-> fence Entry
-> stop four workers
-> final flat recheck
-> capture v4 history digest
-> alembic 0001 -> 0002
-> verify same v4-column digest
-> compatible runtime authority transition
-> activate release
-> start Observation/Lifecycle/Reconciliation
-> bootstrap six v3 Universes
-> final readonly postflight
-> start Entry last when explicitly enabled
```

### 12.5 Postflight

- production commit/schema/seed/Policy exact；
- history digest unchanged；
- zero active v2 Ticket；
- exchange zero position/open order；
- six v3 Universes、42 scopes、seven approved instruments exact；
- four workers stable、zero new restart growth；
- zero open Incident、zero unknown Command；
- healthy cadence zero JSON/Markdown output。

### 12.6 耗时边界

部署耗时由 bounded readonly reads、单一 Alembic revision、一次 authority transaction、一次
Universe bootstrap 和 worker startup 决定，不应随策略数量乘法增长到几十小时。超过各阶段
hard timeout 时保持 Entry fenced，记录 phase/blocker 并 fix-forward。

## 13. 最终命令

```bash
pytest -q tests/trading_kernel
ruff check src/trading_kernel scripts/trading_kernel tests/trading_kernel
mypy src/trading_kernel scripts/trading_kernel
git diff --check
git status --short
```

## 14. 完成定义

程序修复与部署只有在以下全部成立时完成：

1. 本地所有 hard gate 通过；
2. RC diff 已审查且提交；
3. Tokyo preflight 证明 internal/exchange flat；
4. history preservation 精确通过；
5. target identity 与 Universe 激活完成；
6. Entry 最后启动且 final postflight 通过；
7. `MAIN_CONTROL_ROADMAP.md` 用直接证据更新生产 commit、tag、schema 和 runtime snapshot；
8. 无 retired code、test、schema path、service 或 document authority 残留。
