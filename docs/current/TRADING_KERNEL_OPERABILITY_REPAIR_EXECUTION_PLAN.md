---
title: TRADING_KERNEL_OPERABILITY_REPAIR_EXECUTION_PLAN
status: CURRENT_PLAN
program_id: TKR-OPERABILITY-REPAIR
last_verified: 2026-07-30
---

# Trading Kernel 可运行性修复执行与部署计划

## 1. 执行结论

本次工作分成两个严格分离的交付：

1. **程序修复交付**：按测试优先完成双 Lane、Certification Batch、Admission、Protected
   Promotion、部署状态机和容量模型；
2. **生产部署交付**：因为目标 schema 会变化，保持 Entry fenced 并等待当前 exposure
   完成 **natural terminal closure**；随后执行 **Terminal-History Clean Rebuild**，通过
   **terminal-history transformer** 保留完整终态证据，在 `HISTORY_IMPORTED` 后继续 v3
   bootstrap。当前 release 不使用 active-position schema 热升级，也不为部署日程主动结束
   健康 Runner。

本计划是执行顺序和 gate 的权威，不记录生产瞬时 Ticket、SHA、标签或服务状态。执行前
必须从 `docs/current/MAIN_CONTROL_ROADMAP.md` 和 Tokyo readonly facts 重新获取当前状态。

## 2. 全局规则

### 2.1 允许

1. 在 focused `codex/*` branch 修改 Kernel、测试、单一 schema baseline 和部署工具；
2. 删除错误或过时的代码、测试、fixture、字段、migration 和文档语义；
3. 使用 disposable PostgreSQL 做 destructive local rebuild；
4. 在全部 hard gate 通过后执行 reviewed Tokyo Terminal-History Clean Rebuild；
5. 允许 Lifecycle 因策略、Stop 或独立安全条件沿 durable-command path 正常退出；
6. 使用 readonly exchange/account/position/order/rule facts 做 preflight/postflight。

### 2.2 禁止

1. 修改凭证、划转资金、提款、扩大交易所/账户/标的/策略范围；
2. 直接在服务器编辑源代码；
3. direct SQL 清理 active Ticket、Warming slot、Reservation 或 Incident；
4. 恢复旧 schema、旧 writer、兼容 reader、双写或平行执行链；
5. 绕过 Trading Kernel 或 durable Exchange Command 写交易所；
6. 为了让旧测试通过而削弱新语义；
7. 在 deterministic 本地失败仍存在时继续上服务器试错；
8. 在生产执行步骤中无限等待认证或 worker 偶然取得进度。
9. 为部署日程触发健康 Runner 的 controlled exit；
10. 把旧 Policy current、worker lease、Reservation、Domain hold、runtime identity 或其他
    current/control row 复制到 v3。

## 3. 工作流总览

```text
TC-00 决策与基线冻结
-> TC-01 Reconciliation 双 Lane
-> TC-02 Certification Batch + Admission
-> TC-03 Protected ENTRY Promotion
-> TC-04 Deployment State Machine
-> TC-05 Capacity + Schema
-> TC-06 删除旧语义与文档一致性
-> TC-07 Local Clean-Rebuild Rehearsal
-> TC-07A Terminal-History Transformer Rehearsal
-> RC Review / Verification
-> TC-08 Tokyo Terminal-History Clean Rebuild
-> Postflight / Main Control Roadmap 更新
```

任何 Task Card 未满足 Done 条件时，不得开始依赖它的后续卡。允许先写多个 RED，但
GREEN 和 refactor 必须保持每卡可审查、可回滚、无跨卡隐藏依赖。

## 4. Task Card 规范

每张卡都必须提交：

1. 目标与非目标；
2. 依赖；
3. 允许和禁止文件；
4. RED 证据；
5. 实现步骤；
6. Done 证据；
7. Hard Stop；
8. 删除清单；
9. 对 `TRADING_KERNEL_OPERABILITY_REPAIR_TEST_SPEC.md` 的 requirement 映射。

## 5. TC-00：决策与基线冻结

### 5.1 目标

建立一个可审查的 exact repair base，并记录 Owner 已批准的容量 policy identity。

### 5.2 依赖

无。

### 5.3 允许文件

```text
docs/current/TRADING_KERNEL_OPERABILITY_REPAIR_*.md
docs/current/PROJECT_INFORMATION_ARCHITECTURE.md
docs/README.md
README.md
AGENTS.md
tests/trading_kernel/architecture/test_current_document_authority.py
```

### 5.4 禁止文件

```text
src/trading_kernel/**
migrations/trading_kernel/**
scripts/trading_kernel/**
deploy/systemd/**
```

### 5.5 RED

Current-document authority test 先要求三份 repair 文档存在并保持 volatile facts free；文档
尚未创建时测试必须失败。

### 5.6 Done

1. 三份文档进入 current allowlist 与文档入口；
2. 设计、测试、执行范围无冲突；
3. 当前 branch/base commit 已记录在工作日志而非稳定文档；
4. **D-CAP-01** 已批准为单 Ticket `3%`、账户总风险 `6%`、单 Ticket 保证金 `45%`、
   账户总保证金 `90%`、最多三个 Ticket；批准尚不代表生产已生效。

### 5.7 Hard Stop

若后续 Replay 暴露 venue minimum 或策略假设冲突，TC-05 必须把证据报告为 blocker，
不得自行调整 Owner 已批准参数。

## 6. TC-01：Reconciliation 双 Lane

### 6.1 目标

在保持四个 persistent workers 的前提下，让 Safety 优先且 Housekeeping 有确定性最大
等待保证，关闭 OR-P0-01 与 OR-P2-01。

### 6.2 依赖

TC-00。

### 6.3 允许文件

```text
src/trading_kernel/interfaces/reconciliation_worker.py
src/trading_kernel/interfaces/worker_process.py
src/trading_kernel/application/ports.py
src/trading_kernel/infrastructure/pg_*repositor*.py
src/trading_kernel/infrastructure/pg_models.py
scripts/trading_kernel/run_reconciliation_worker_once.py
deploy/systemd/brc-trading-kernel-reconciliation-worker.service
tests/trading_kernel/unit/test_reconciliation_*.py
tests/trading_kernel/integration/test_reconciliation_*.py
tests/trading_kernel/full_chain/test_reconciliation_*.py
```

如需新 scheduler 纯 domain/application 模块，只能放在 `src/trading_kernel` 当前分层中，
不得创建 alternate worker package。

### 6.4 禁止文件

```text
策略 detector
Capacity/ENTRY dispatch
Universe Registry seed
部署 cutover 工具
新 systemd service 或 timer
```

### 6.5 RED

按测试规格 RED-1 与 RED-6 构造 **5 秒 poll、2 秒重新到期、15 分钟 virtual time**。
旧实现必须出现 Housekeeping overdue 或 Fee Monitor 假推进。

### 6.6 实现步骤

1. 抽出 frozen scheduler input/result；
2. 将 Safety selector 与 Housekeeping selector 分离；
3. Housekeeping 按 earliest deadline + stable identity claim；
4. 一个 process cycle 最多执行一个 Safety 和一个 Housekeeping action；
5. 保持 venue I/O 在 transaction 外；
6. 实际完成 Fee Monitor 后才推进 due-at；
7. 增加 lane metrics/monitor state；
8. 删除旧 single-return 公平性假设和 AST 调用计数测试。

### 6.7 Done

1. R-01、R-07 对应 unit/integration/full-chain GREEN；
2. 三 active Tickets 连续存在时 Settlement、Review、Certification、Fee Monitor 均不超
   规格上界；
3. Unknown/post-fill/active-position 安全优先级未回退；
4. systemd service 数仍为四；
5. no-signal tick 零文件输出。

### 6.8 Hard Stop

若实现需要通过新增第五 worker、timer 或长事务取得公平性，停止该方案并回到设计评审。

## 7. TC-02：Certification Batch 与 Admission

### 7.1 目标

统一部署认证、持续 certification 和 candidate admission 的语义，关闭 OR-P1-01 与
OR-P1-02。

### 7.2 依赖

TC-01。

### 7.3 允许文件

```text
src/trading_kernel/domain/instrument_certification.py
src/trading_kernel/application/certify_universe_instrument.py
src/trading_kernel/application/ingest_signal.py
src/trading_kernel/application/ports.py
src/trading_kernel/infrastructure/pg_signal_repository.py
src/trading_kernel/infrastructure/pg_universe_repository.py
src/trading_kernel/infrastructure/pg_models.py
scripts/trading_kernel/certify_readonly.py
scripts/trading_kernel/bootstrap_strategy_universes.py
scripts/trading_kernel/read_strategy_universe_status.py
tests/trading_kernel/**/test_*certification*.py
tests/trading_kernel/**/test_*universe*.py
tests/trading_kernel/**/test_*signal*.py
```

### 7.4 禁止文件

```text
exchange mutation adapters
ENTRY command dispatch
策略 Registry Event 含义
approved instrument manifest 内容
```

### 7.5 RED

1. expired certification 的 ready Signal 仍被 query 返回；
2. 七条独立 certification 在 batch 总耗时内不能稳定满足旧 60 秒瞬时 gate；
3. batch identity 变化后旧 evidence 仍可能被计数。

### 7.6 实现步骤

1. 增加 Certification Batch domain model、ports 和 PostgreSQL projections；
2. batch member 使用 exact manifest digest 与 target runtime identity；
3. continuous certification 使用 10 分钟有效期、5 分钟刷新目标、2 分钟调度最大等待；
4. ready candidate query 加 exact current certification join；
5. stale certification 只暂停仲裁，不改变未过期 Signal 的 terminal state；
6. `certify_readonly.py` 的 Promotion gate 改为 exact completed batch 或唯一 direct-successor
   ENTRY-arm policy stage，不硬编码 `v1 -> v2`；
7. bootstrap 一次请求 approved manifest，六个 Universe 自动串行推进；
8. local recording adapter 证明零 exchange mutation。

### 7.7 Done

1. R-04、R-05 全部 GREEN；
2. 七标的 batch 在 local rehearsal timeout 内完成；
3. expired/recovered certification full-chain 不丢 Signal；
4. direct SQL、手工 abandon 和逐 Event 人工安装不是正常路径；
5. blocker/timeout 保持 bounded、可读、可重试。

### 7.8 Hard Stop

若 Promotion 仍通过“current 表中恰有七条 fresh”判断，或 batch 需要 runtime 读取文档/
JSON manifest，Task Card 不得完成。

## 8. TC-03：Protected ENTRY Promotion

### 8.1 目标

让 exact protected exposure 在代码 release 后可通过官方路径恢复新 ENTRY，同时不放松
任何保护、identity 或 unknown-outcome gate，关闭 OR-P0-02。

### 8.2 依赖

TC-02。

### 8.3 允许文件

```text
scripts/trading_kernel/promote_entry.py
scripts/trading_kernel/certify_readonly.py
scripts/trading_kernel/probe_production_runtime.py
scripts/trading_kernel/seed_runtime_authority.py
src/trading_kernel/application/production_runtime.py
src/trading_kernel/infrastructure/pg_*repositor*.py
tests/trading_kernel/unit/test_promote_entry.py
tests/trading_kernel/unit/test_production_runtime.py
tests/trading_kernel/integration/test_production_cutover_adapter.py
tests/trading_kernel/full_chain/test_*promotion*.py
```

### 8.4 禁止文件

```text
手工 Ticket allowlist 作为正常 Promotion 输入
Lifecycle protection 例外
direct exchange order
放松 unresolved command/open incident gate
```

### 8.5 RED

一个 exact protected Ticket 完成 protected release 后，当前 `promote_entry.py` 因 flatness
失败。RED 同时断言原 Ticket 的 protection 未丢失。

### 8.6 实现步骤

1. 定义 flat/protected 两种 promotion snapshot；
2. 自动从 PostgreSQL 枚举全部 active protected Tickets；
3. 对每个 Ticket 比较 internal/exchange exact position 与 protection facts；
4. 拒绝未归属 position/order、unknown、incident、release identity drift；
5. 原子 arm new-entry policy/capability；
6. postflight 只承认 exact Batch policy version，或
   `current_policy_version = batch_policy_version + 1` 的唯一 ENTRY-arm direct successor；
   拒绝复用历史 version、跳级和其他 policy drift；
7. Entry while fenced 启动并做无 mutation smoke；
8. final postflight 后移除 fence；
9. 任一失败 refence + stop Entry；
10. 重写 protected-handover 永久禁止 Entry 的旧测试。

### 8.7 Done

1. R-02 full-chain GREEN；
2. flat 与 protected 模式使用同一 Promotion abstraction；
3. 既有 Ticket 生命周期不因新 ENTRY authority 改变；
4. exact idempotent retry 通过；
5. 无 Owner 手工拼内部 Ticket 清单。

### 8.8 Hard Stop

只要出现未归属 exposure/order、缺失 protection、identity mismatch、unknown command 或
open incident，ENTRY 必须保持 fenced。

## 9. TC-04：Deployment State Machine

### 9.1 目标

把 release/cutover 从隐式 try/except 分支改成有 phase、journal、precondition、resume 和
phase-aware recovery 的正式状态机，关闭 OR-P1-03。

### 9.2 依赖

TC-03。

### 9.3 允许文件

```text
scripts/trading_kernel/deploy_tokyo_release.py
scripts/trading_kernel/cutover_tokyo.py
scripts/trading_kernel/verify_flat_cutover.py
scripts/trading_kernel/verify_schema.py
scripts/trading_kernel/certify_readonly.py
tests/trading_kernel/unit/test_deploy_tokyo_release.py
tests/trading_kernel/unit/test_cutover_tokyo.py
tests/trading_kernel/integration/test_production_cutover_adapter.py
tests/trading_kernel/full_chain/test_*deployment*.py
```

### 9.4 禁止文件

```text
ad hoc SSH shell workflow 作为唯一实现
服务器源代码编辑
无 journal destructive action
schema rollback 到旧 generation
```

### 9.5 RED

对 STAGED、QUIESCED、IDENTITY_ROTATED、READONLY_WORKERS_STARTED、TARGET_CERTIFIED、
LIFECYCLE_STARTED、ENTRY_STARTED_FENCED、ENTRY_UNFENCED 逐阶段注入失败，当前统一恢复
逻辑必须至少在一个阶段失败。

### 9.6 实现步骤

1. 扩展现有 `cutover_tokyo.py` ops journal，不另建文件 authority；
2. 为 regular release 与 flat rebuild 定义共享 phase enum/predicates；
3. 每个 phase 实现 `apply_phase()` 与 `phase_satisfied()`；
4. 恢复动作按 schema/identity/service/fence 当前事实决定；
5. Observation/Reconciliation 先启动，Certification Batch 后启动 Lifecycle；
6. Entry 始终先 while fenced 启动；
7. 删除任意异常后无条件恢复同一 SAFETY_SERVICES 的分支；
8. 所有错误输出脱敏、bounded。

### 9.7 Done

1. R-06 failure matrix 与 crash/resume 全 GREEN；
2. 重复 apply 不重复 destructive action；
3. schema 删除后旧 writer 无法恢复；
4. Entry 任一未知状态 inactive/disabled/fenced；
5. 非 BRC 服务与数据始终不在 mutation scope。

### 9.8 Hard Stop

若 phase 恢复需要人工猜测“上次执行到哪一步”，或需要直接改 symlink/DB row 才能继续，
状态机未完成。

## 10. TC-05：Capacity、Policy 与 Clean Baseline

### 10.1 目标

把并发数量、单 Ticket 风险、账户总风险、单 Ticket 保证金和账户总保证金变成显式
Owner Policy 与纯 domain sizing，关闭 OR-P0-03。

### 10.2 依赖

TC-00 已关闭的 **D-CAP-01 Owner 决策**，以及 TC-04。

### 10.3 允许文件

```text
src/trading_kernel/domain/capacity.py
src/trading_kernel/domain/capacity_sizing.py
src/trading_kernel/application/build_capacity_claim.py
src/trading_kernel/application/issue_ticket.py
src/trading_kernel/infrastructure/pg_models.py
src/trading_kernel/infrastructure/pg_repositories.py
scripts/trading_kernel/seed_runtime_authority.py
scripts/trading_kernel/certify_readonly.py
migrations/trading_kernel/versions/*.py
tests/trading_kernel/**/test_*capacity*.py
tests/trading_kernel/integration/test_schema_baseline.py
docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md
docs/current/OWNER_RUNTIME_OPERATING_MODEL.md
```

### 10.4 禁止文件

```text
旧 policy 字段兼容 reader
双写旧/新字段
in-place production migration
float 金额
扩大 Owner 未确认的资本边界
```

### 10.5 RED

1. tight stop 使第一个 Ticket 使用全部 remaining margin；
2. `gross_risk_at_stop` 变化不影响 sizing；
3. 两个旧 usage snapshot 可能同时超过账户总风险；
4. 旧 schema 仍包含模糊 policy 字段。

### 10.6 实现步骤

1. 将 policy 替换为显式 ticket/gross risk 与 ticket/gross margin 字段；
2. `CapacityUsage` 增加 current reserved margin；
3. pure sizing 按设计公式选择 min quantity；
4. Claim/Ticket 冻结实际 budget、limit 与 usage snapshot；
5. Ticket 原子提交时锁 account exposure 并重验；
6. 更新 seed、readonly certification、review lineage；
7. 保留历史 `policy-main:v2` 的不可变 identity，新 v3 seed 从未占用的后续 version 开始；
8. 将 acceptance/full transition 改为单调 direct successor，不硬编码 `v1 -> v2 -> v3`；
9. 创建下一版唯一 clean baseline，删除旧 baseline；
10. 删除旧字段、fixture、tests 和兼容语义；
11. 更新 experiment profile 与 Owner operating model 中已确认的最终值。

### 10.7 Done

1. R-03 unit/integration/replay 全 GREEN；
2. 三个不同 Netting Domain 可在政策允许时共存；
3. 第四个 Ticket、总风险耗尽、总保证金耗尽分别有明确 blocker；
4. account usage race 不能超额提交；
5. empty schema rebuild、forward-only downgrade rejection、metadata exact 通过；
6. migrations 目录只有一个 current baseline；
7. terminal historical policy version 与新 current policy lineage 不冲突。

### 10.8 Hard Stop

Replay 若证明已批准参数普遍无法满足 venue minimum 或破坏策略假设，停止 TC-05 并
记录 exact evidence；不在代码或 seed 中偷调默认值。

## 11. TC-06：删除旧语义与全局一致性

### 11.1 目标

删除本次修复替代的所有错误历史包袱，并校准 current docs、architecture tests 与运行合同。

### 11.2 依赖

TC-01 至 TC-05。

### 11.3 允许文件

```text
tests/trading_kernel/**
docs/current/**
README.md
docs/README.md
AGENTS.md
受替换生产模块中的 dead code
```

### 11.4 禁止文件

```text
新增 compatibility package
archive 代码重新进入 current imports
生成 runtime report 文件
```

### 11.5 RED

Architecture scan 明确列出仍存在的旧字段、旧 baseline、旧 test contract、timer、第五 worker、
兼容 reader 或过时 current document reference。

### 11.6 实现步骤

1. 删除旧 fairness/AST/deployment expectation tests；
2. 删除旧 policy/schema/seed names；
3. 清理 dead branch、unused adapter 和过时 CLI option；
4. 更新 current document allowlist 与 authority index；
5. 更新 deployment contract，引用本 repair 结果但不复制 volatile facts；
6. 执行 repository-wide retired-semantics scan。

### 11.7 Done

1. R-07 GREEN；
2. `rg` 和 architecture tests 均找不到已列退役语义；
3. 文档、代码、schema、systemd、测试对四 worker 与新 policy 含义一致；
4. `git diff --check` 通过。

## 12. TC-07：Local Clean-Rebuild Rehearsal

### 12.1 目标

在不连接生产 exchange mutation 的环境中完整演练下一版 empty rebuild、batch bootstrap、
worker progression、fenced Entry start、Promotion 和 crash/resume。

### 12.2 依赖

TC-01 至 TC-06 全部 Done。

### 12.3 允许文件

```text
scripts/trading_kernel/cutover_tokyo.py
scripts/trading_kernel/bootstrap_schema.py
scripts/trading_kernel/bootstrap_strategy_universes.py
scripts/trading_kernel/promote_entry.py
tests/trading_kernel/full_chain/**
tests/trading_kernel/integration/**
```

### 12.4 禁止文件

```text
生产 SSH mutation
真实 exchange mutation
跳过测试 gate 的 local-only flag
```

### 12.5 执行

1. 创建 disposable PostgreSQL；
2. 从空 application schema 安装唯一 baseline；
3. seed exact Registry/Policy/Capability/identity；
4. 一次 bootstrap approved manifest；
5. Observation/Reconciliation 推进 Certification Batch 与六 Universe；
6. Lifecycle flat smoke；
7. Entry while fenced smoke；
8. final Promotion；
9. 每个 phase 注入 crash 并 resume；
10. 重复整个 operation 验证 idempotency；
11. 检查 recording venue mutation count = 0。

### 12.6 Done

1. `TRADING_KERNEL_OPERABILITY_REPAIR_TEST_SPEC.md` 全部 local gates 通过；
2. 完整 suite、Ruff、Mypy、file-I/O、diff checks 通过；
3. rehearsal 没有无限等待，所有 phase 有 timeout；
4. requirement audit 无空项；
5. 形成可部署 exact committed release candidate。

### 12.7 Hard Stop

任何 deterministic failure 只能在 Tokyo 复现、任何 phase 需要人工 direct SQL、或任何 local
场景产生 exchange mutation，都阻止 RC。

## 13. TC-07A：Terminal-History Transformer Rehearsal

### 13.1 目标

在当前 exposure 自然终态前，使用 production-shaped v2 fixture 完成 transformer 工程；在
自然终态后，只读导出 exact production snapshot 并重复同一 rehearsal。证明终态历史可进入
v3 canonical schema，同时旧 current/control 状态不会成为新运行权威。

### 13.2 依赖

TC-01 至 TC-07 全部 Done；最终 production rehearsal 还依赖 natural terminal closure、
Settlement、Review、exchange flat 和零 residue。

### 13.3 允许文件

```text
scripts/trading_kernel/transform_terminal_history.py
scripts/trading_kernel/verify_terminal_history_snapshot.py
src/trading_kernel/application/terminal_history.py
src/trading_kernel/infrastructure/pg_terminal_history.py
tests/trading_kernel/unit/test_terminal_history_transformer.py
tests/trading_kernel/integration/test_terminal_history_import_postgres.py
tests/trading_kernel/full_chain/test_terminal_history_clean_rebuild.py
```

实现必须位于现有 Kernel/Application/PostgreSQL 边界内；不得新增 runtime worker、旧 schema
reader service 或长期兼容 package。

### 13.4 输入与输出合同

输入：

1. exact v2 schema/seed/runtime identity；
2. writers 全停后的 PostgreSQL snapshot；
3. table/row counts、source checksum 和 terminal closure manifest；
4. exchange-flat/no-order readonly proof；
5. Ticket terminal、Reservation/Domain release、Settlement、Review 和 zero Incident proof。

输出：

1. v3 canonical terminal Signal/Claim/Ticket/Event/Command/Settlement/Review lineage；
2. 每个派生字段的 source identity、公式与 digest；
3. 历史 `policy-main:v2` identity 与未占用的新 current policy version；
4. 明确的 excluded current/control table 清单；
5. 一个可在空 v3 target transaction 内执行的 deterministic import operation。

部署不得依赖未提交的 loose SQL/DML 文件作为 authority。transformer 读取 exact snapshot，
通过版本控制代码直接写入 disposable/target PostgreSQL；snapshot 和 manifest 只是受控部署
输入，导入完成后 PostgreSQL v3 才成为 current authority。

### 13.5 RED 与实现

1. RED：旧 Claim 因新显式 ticket/gross policy 字段无法直接载入；
2. RED：历史 `policy-main:v2` 与硬编码新 v2 acceptance policy 冲突；
3. RED：直接复制 current rows 会产生 active Reservation/Exposure 或错误 runtime identity；
4. 实现 claim-time gross risk/reserved margin 的确定性重建；
5. 实现旧 per-Ticket policy + concurrency ceiling 到历史 gross ceiling 的可审计派生；
6. 将新 policy seed/promotion 改为未占用 version 的 direct-successor lineage；
7. 单事务写入完整 terminal episode，任何 parity/constraint 失败整笔回滚；
8. 删除所有 temporary export、partial import 和默认值分支。

### 13.6 Done

1. synthetic fixture 与 exact production snapshot 两次 rehearsal 都通过；
2. source/target Ticket、Event、Command、Settlement、Review identity 与 digest parity exact；
3. v3 domain 可读取历史终态 Claim/Ticket；
4. 零 active Ticket selector、Reservation、Domain hold、Exposure、due Command、open Incident；
5. 新 Policy/Universe/runtime current authority 只来自 v3 seed；
6. `HISTORY_IMPORTED` crash/rollback/retry 全部通过；
7. transformer 产生零 exchange mutation、零 loose runtime authority 文件；
8. 完整 suite、Ruff、Mypy、architecture、file-I/O 和 diff checks 通过。

### 13.7 Hard Stop

任一字段需要猜测、默认值、伪造 policy 含义、partial Ticket import，或必须让 v3 runtime
读取 v2 表时，TC-07A 不得完成，Tokyo 保持旧版本和 Entry fence。

## 14. Release Candidate Review

### 14.1 Review 维度

| 维度 | 必查内容 | 阻断条件 |
| --- | --- | --- |
| Architecture | 单一 Kernel、四 worker、双 Lane、无兼容链 | alternate runtime 或第五 worker |
| Domain | Decimal、frozen models、显式 policy、纯 sizing | I/O/ORM 泄漏到 domain |
| PostgreSQL | exact locks、bounded selector、单一 baseline | race、full-history scan、旧 reader |
| Exchange safety | durable command、unknown、partial fill、protection | 任何 bypass 或盲重发 |
| Deployment | phase、journal、resume、fence | failure 后状态不确定 |
| Test quality | production-shaped time、real producer boundary | fixture-only completion |
| Operability | max wait、timeout、metrics、Owner state | 无限 waiting 或内部 gate 需人工操作 |
| Documentation | authority ownership、无 volatile duplication | current docs 冲突 |

### 14.2 RC Hard Gate

只有全部 review finding 关闭、完整验证从 clean checkout 重跑通过后，才能 commit/tag 并进入
TC-08。

## 15. TC-08：Tokyo Terminal-History Clean Rebuild

### 15.1 选择此路径的原因

本 repair 包含 schema identity 变化。**Protected Promotion**是未来 regular code release
和无 schema 变化的 protected handover 能力，不用于本次 active-schema 热升级。因此本次
生产采用：

```text
Entry 保持 fenced
-> 既有 Ticket natural terminal closure
-> Settlement/Review 完成
-> exchange/internal flat
-> 停四 worker
-> final v2 snapshot + manifest/checksum
-> BRC application schema clean rebuild
-> terminal-history transformer
-> HISTORY_IMPORTED
-> batch bootstrap
-> safety workers
-> Entry fenced start
-> final postflight
-> unfence
```

### 15.2 前置事实刷新

执行当日从当前代码、PostgreSQL、systemd 和 exchange readonly facts 重新验证：

1. target commit 已提交且本地全部 gate 通过；
2. immutable target tag 计划尚未占用；
3. 当前 release/runtime/schema/seed exact；
4. Entry fence 和 service 状态 exact；
5. active Ticket、position、order、protection、command、incident exact；
6. account 为 independent sides、cross，approved instruments configured leverage exact；
7. TC-07A 已用 production-shaped snapshot 完成 transformer rehearsal；
8. 新 Policy version 不复用历史 Ticket 的 frozen version；
9. 无旧 writer 或非 BRC 数据进入 deletion scope。

### 15.3 Exposure Closure

若执行时仍有 active Ticket：

1. 保持 Entry fenced；
2. Observation、Lifecycle、Reconciliation 继续运行；
3. 等待策略、Stop、Runner trailing 或正常 Lifecycle 产生 natural exit；
4. 不直接撤单、不手工下反向单、不 direct SQL 改 terminal state；
5. 等待 exchange flat、零 residual order；
6. 等待 budget/domain release、Reconciliation matched、Settlement、Review；
7. 确认零 open Incident、零 unknown command；
8. 若 deployment window 到达但 Ticket 仍健康 active，取消该窗口并继续旧 safety runtime，
   不为部署触发 controlled exit。

### 15.4 Cutover Plan 命令合同

TC-04 完成后，先使用现有 cutover controller 的 plan 模式。以下为命令结构，实际 identity
必须从当日 readonly preflight 注入，禁止使用文档中的默认猜测：

```bash
python3 scripts/trading_kernel/cutover_tokyo.py \
  --plan \
  --adapter-factory <tokyo-adapter-module:factory> \
  --cutover-id <exact-operation-id> \
  --server-id <exact-server-id> \
  --database-identity <exact-database-id> \
  --venue-id binance-usdm \
  --account-id <exact-account-id> \
  --runtime-profile-id <exact-runtime-profile-id> \
  --application-schema public \
  --target-commit <exact-40-hex-commit> \
  --target-schema-revision <target-clean-baseline-revision> \
  --target-seed-identity <exact-seed-digest> \
  --target-release-id <exact-release-id> \
  --terminal-history-manifest <exact-snapshot-manifest>
```

`--plan` 必须返回 pass 后，才允许使用同一组 exact identity 执行 `--apply`。任何参数变化
都创建新的 operation identity，不复用旧 journal。

### 15.5 Apply 阶段

1. **STAGED**：上传 committed release、transformer 与 markers；
2. **TERMINAL_CERTIFIED**：重验 natural terminal closure、Settlement/Review、exchange flat、
   零 residual order/Incident/unknown；
3. **QUIESCED**：确认 Entry fence，停止四 workers，确认无进程；
4. **FINAL_TERMINAL**：writers 全停后再次读取 PostgreSQL/exchange terminal facts；
5. **HISTORY_EXPORTED**：取得 exact v2 snapshot、table/row manifest 与 checksum；
6. **REBUILD**：只删除 BRC application schema，保留 ops journal 与非 BRC 数据；
7. **SEED**：安装唯一 v3 baseline，seed Registry/新 Policy lineage/Capability/runtime identity；
8. **HISTORY_IMPORTED**：terminal-history transformer 单事务导入完整 terminal episode，验证
   identity/digest parity 与零 active state；
9. **READONLY START**：启动 Observation 与 Reconciliation；
10. **TARGET CERTIFIED**：完成 exact Certification Batch 与六 Universe Active pointers；
11. **LIFECYCLE START**：启动 Lifecycle，执行 flat/no-residue/terminal-history smoke；
12. **ENTRY FENCED START**：启动 Entry，确认 fence 仍存在且零 mutation；
13. **FINAL POSTFLIGHT**：重验 commit/schema/seed/policy/history/batch/account/rules/flatness；
14. **UNFENCE**：原子 arm authority 后移除 fence；
15. **TAG/ROADMAP**：验证 immutable tag，并将瞬时证据写入 Main Control Roadmap。

### 15.6 超时与耗时边界

以下是基于阶段数量和 bounded readonly calls 的**执行估算**，不是当前生产事实：

| 阶段 | 目标时间 | Hard timeout | 超时动作 |
| --- | ---: | ---: | --- |
| Final flat recheck + stop | 1–3 分钟 | **5 分钟** | 保持旧状态或全部 fenced，停止 cutover |
| Snapshot export + checksum | 1–3 分钟 | **5 分钟** | 不删除 schema，重新导出或恢复旧 safety workers |
| Schema rebuild + seed | 2–5 分钟 | **10 分钟** | 不恢复旧 writer，fix-forward target |
| Terminal history import + parity | 1–5 分钟 | **10 分钟** | 整笔回滚，保持全停和 Entry fenced |
| Certification Batch + Universe activation | 2–8 分钟 | **15 分钟** | 保持 Entry fenced，记录 exact blocker |
| Lifecycle/Entry fenced smoke | 1–3 分钟 | **5 分钟** | 停止失败 worker，保留安全可运行集合 |
| Final postflight + unfence | 1–3 分钟 | **5 分钟** | refence Entry |

在 exchange 已 flat 的前提下，目标生产停机窗口为约 **15–35 分钟**。超过 hard timeout
不是“继续等几十小时”，而是进入明确 blocked/fix-forward 状态。

### 15.7 部署后观察

1. 四 workers active，restart count 不增长；
2. Entry fence 已按 final gate 状态正确存在或移除；
3. Certification Batch 与 current certifications 新鲜；
4. 六 Active Universe、approved scopes 与 manifest exact；
5. 零 active Ticket 时 exchange 零 position/order；
6. 历史 terminal Ticket/Event/Command/Settlement/Review parity exact，且不进入 active selector；
7. 零 unresolved command、open incident、orphan reservation/domain；
8. 一个代表性 idle window 中 Safety/Housekeeping 无 deadline breach；
9. no-signal cadence 零生成文件；
10. Main Control Roadmap 更新 current commit、tag、schema、certification、snapshot 和剩余路径。

## 16. Fix-forward 与恢复规则

### 16.1 Rebuild 前失败

如果 application schema 尚未删除、旧 release identity 仍 exact，可保持 Entry fenced并恢复
旧 safety workers。snapshot/manifest 不一致时必须在旧 schema 上重新导出，不得自动
unfence Entry。

### 16.2 Rebuild 后失败

application schema 一旦删除，旧 runtime 不再是 rollback authority：

1. Entry 保持 fenced；
2. 只运行 target identity 下已经通过对应 phase 的 workers；
3. 从 ops journal resume；
4. `HISTORY_IMPORTED` 未完成时保持全部 target workers 停止，修复 transformer 后重新
   rebuild/import；
5. 修复 target release 并继续 forward；
6. v2 snapshot 是审计与受控恢复输入，不自动恢复成 production runtime；
7. 不恢复旧 schema、旧数据或旧 writer。

### 16.3 Unfence 后异常

立即恢复 Entry fence 并停止 Entry；既有 exposure 若已经产生，Lifecycle 与 Reconciliation
继续使用 durable safety authority。随后按 exact Ticket/command/position facts诊断，不盲目
重发 ENTRY。

## 17. 最终完成定义

程序修复与部署只有在以下全部成立时完成：

1. 三份 repair 文档为 current authority 且引用一致；
2. TC-01 至 TC-07A 全部 Done；
3. 完整 local verification 从 clean state 重跑通过；
4. Owner 批准的 D-CAP-01 exact 值已进入 profile、seed、schema、certification 和测试；
5. Tokyo Terminal-History Clean Rebuild 每个 phase 从 direct evidence 完成；
6. 四 workers、fence、identity、schema、seed、policy、manifest、batch exact；
7. exchange 与 PostgreSQL 无未归属或矛盾 runtime state；
8. 生产 observation window 无 lane starvation、假 monitor 进度或文件输出回归；
9. terminal history source/target identity、count、digest parity exact，且零 active-state 污染；
10. 错误旧代码、测试、schema 和部署分支已删除；
11. `MAIN_CONTROL_ROADMAP.md` 持有唯一当前生产结果与剩余关键路径。
