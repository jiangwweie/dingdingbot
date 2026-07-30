---
title: TRADING_KERNEL_OPERABILITY_REPAIR_TEST_SPEC
status: CURRENT_SPEC
program_id: TKR-OPERABILITY-REPAIR
last_verified: 2026-07-30
---

# Trading Kernel 可运行性修复测试规格

## 1. 文档目的

本规格定义 **Trading Kernel 可运行性修复**的本地证据、回归边界和生产 readonly
验收。核心原则是：确定性程序缺陷必须优先暴露在本地；Tokyo 只验证当前外部事实，
不得作为发现调度、时间、schema、恢复或容量错误的首个环境。

本规格不记录当前测试数量、生产 commit、Ticket 或服务瞬时状态。当前生产证据仅由
`docs/current/MAIN_CONTROL_ROADMAP.md` 持有。

## 2. 测试原则

### 2.1 强制规则

1. 每个生产行为使用 **RED → GREEN → REFACTOR**；
2. 先删除或重写固化错误语义的测试，再实现新行为；
3. PostgreSQL 行锁、lease、`SKIP LOCKED`、due-at 和 schema 使用 disposable PostgreSQL；
4. 时间测试使用 production-shaped virtual clock，不使用 1ms 递增规避真实重新到期；
5. exchange adapter 使用 recording fake，区分 readonly read 与 mutation；
6. full-chain 测试从真实 producer boundary 进入，不允许直接插入下游 fixture 宣称链路完成；
7. 网络、SSH、subprocess、venue read 和未知结果必须覆盖 timeout；
8. 所有资金值使用 `Decimal`，核心模型使用 frozen named Pydantic models；
9. 不以 AST 调用次数、mock 调用存在或单个 happy path 代替行为证明；
10. 未通过本规格全部 hard gate，不得宣称可部署或已修复。

### 2.2 证据层级

| 层级 | 运行环境 | 证明内容 | 不能证明 |
| --- | --- | --- | --- |
| **Unit** | 纯 Python / virtual clock | domain 公式、scheduler 选择、状态机转换、失败分类 | PostgreSQL 锁、真实进程 cadence |
| **Integration** | disposable PostgreSQL | selector、lease、事务、schema、批次原子完成、并发 claim | 完整 producer-to-review 链 |
| **Full-chain** | disposable PostgreSQL + recording venue | Observation 到 Review、worker progression、Promotion、故障恢复 | Tokyo 当前账户事实 |
| **Architecture** | tracked repository | 单一执行链、单一 baseline、service 数量、无旧语义 | 运行时间公平性 |
| **Local rehearsal** | 空 PostgreSQL + release tooling | 停机重建、seed、batch、worker、fence、resume | 真实交易所状态 |
| **Tokyo readonly smoke** | 生产只读 | exact identity、账户模式、position/order/protection、worker state | 可替代本地 deterministic tests |

## 3. Traceability

| Requirement | 对应缺陷 | 主要测试层 | 通过条件 |
| --- | --- | --- | --- |
| **R-01 双 Lane 有界进度** | OR-P0-01、OR-P2-01 | Unit、Integration、Full-chain | Safety 连续存在时每类 Housekeeping 仍在 max wait 内完成 |
| **R-02 Protected Promotion** | OR-P0-02 | Unit、Integration、Full-chain | exact protected facts 可恢复 ENTRY；任一矛盾保持 fence |
| **R-03 多 Ticket 容量** | OR-P0-03 | Unit、Integration、Replay | 单 Ticket 与账户总风险/保证金上限同时生效 |
| **R-04 认证/admission 一致** | OR-P1-01 | Integration、Full-chain | stale certification 不入仲裁，恢复后未过期 Signal 可用 |
| **R-05 Certification Batch** | OR-P1-02 | Unit、Integration、Rehearsal | exact manifest 在 batch 有效窗口内完成并可 Promotion |
| **R-06 部署状态机** | OR-P1-03 | Unit、Rehearsal | 每个 phase failure 只执行允许的恢复动作 |
| **R-07 删除错误历史语义** | 全部 | Architecture、静态扫描 | 无旧字段、旧测试、旧 baseline、兼容 reader 或双写 |

## 4. RED 顺序

### 4.1 RED-1：持续 Safety 下的 Housekeeping 饥饿

新增 production-shaped virtual-clock 测试：

```text
process poll = 5s
active-position next due = now + 2s
duration >= 15m virtual time
active protected Tickets = 3
pending Settlement = 1
pending Review = 1
certification targets = 7
Fee Monitor due = true
```

初始 RED 必须证明当前实现中至少一类 Housekeeping 超过 max wait，而不是通过 mock
直接返回认证成功。

建议替换测试：

```text
tests/trading_kernel/unit/test_reconciliation_scheduler.py
tests/trading_kernel/integration/test_reconciliation_lane_claims.py
tests/trading_kernel/full_chain/test_reconciliation_production_cadence.py
```

### 4.2 RED-2：protected 部署后的 ENTRY dead end

构造一个 exact `position_protected` Ticket，完成 release protected handover 后调用正式
Promotion。当前代码应因 flat gate 失败形成 RED；测试必须同时证明 exposure 的 Lifecycle
仍可维护 Stop。

### 4.3 RED-3：认证过期仍进入仲裁

插入一个仍未过期的 `candidate_ready` Signal，并将 exact instrument certification 设为
expired。当前 ready query 会返回候选，测试形成 RED。随后将同一 certification 刷新，
同一 Signal 应重新可见且不产生第二个 SignalEvent。

### 4.4 RED-4：一个 Ticket 吞掉容量

在三 Ticket policy 下构造 tight-stop 候选，使现有 sizing 使用接近全部 remaining margin。
RED 必须证明第二个不同 Netting Domain 因第一个 reservation 而 `budget_exhausted`，尽管
account gross risk 仍低于目标总上限。

### 4.5 RED-5：部署 failure recovery 不分阶段

对 release state machine 每个阶段注入一次异常。当前实现会对多个阶段执行相同
`start_services(SAFETY_SERVICES)`，测试形成 RED。

### 4.6 RED-6：Fee Monitor 假完成

构造 Safety action 每 tick 都执行、Fee Monitor due。当前 runner 会推进进程内 observed
时间但 source 未被调用，测试形成 RED。

## 5. Unit 测试规格

### 5.1 Reconciliation Scheduler

| Case | 输入 | 期望 | 禁止结果 |
| --- | --- | --- | --- |
| Safety only | Unknown 或 active position due | 选择 exact Safety action | 选择 Routine 替代 Safety |
| Housekeeping only | Settlement/Review/Certification/Fee due | earliest deadline + stable identity | 固定 if 顺序长期偏置 |
| Both due | Safety 与 Housekeeping 同时 due | 同 cycle 先 Safety、后 Housekeeping，各最多一个 | Safety 永久排他 |
| Safety timeout | position read timeout | exact work 重排；Housekeeping deadline 仍评估 | 整个 process state 假死 |
| Fee not executed | Safety 执行但 Fee 未进入 action list | Fee next due 不推进 | 记录虚假 observed-at |
| Runtime fence | commit/schema mismatch | 禁止 mutation；记录/遵循 fence | 继续 dispatch 或 protection mutation |

Scheduler result 必须是 named model，至少包含：

```text
safety_action
housekeeping_action
started_at_ms
completed_at_ms
next_due_at_ms
deadline_breach
```

### 5.2 Certification Batch

必须覆盖：

1. exact 七标的 manifest 全部 eligible 后 batch 原子 complete；
2. manifest digest 或 runtime identity 变化后旧 batch 不可 Promotion；
3. 任一成员 transient unavailable 时 batch 保持 pending；
4. 任一成员 owner action required 时 batch terminal blocked；
5. 最早 `valid_until` 不覆盖 promotion window 时 batch 不完成；
6. 重试创建新 batch，不修改旧 batch 成员；
7. batch source 发生 timeout 时 lease 可恢复；
8. local batch 执行记录 **零 exchange mutation**。

### 5.3 Candidate Admission

必须覆盖以下状态组合：

| Signal | Certification | Candidate 结果 | Readiness 结果 |
| --- | --- | --- | --- |
| fresh | eligible + fresh | 可参与仲裁 | 保持 `candidate_ready` |
| fresh | eligible + expired | 暂不可参与 | 不终态拒绝 |
| fresh | temporarily unavailable | 暂不可参与 | 暴露 temporary blocker |
| fresh | owner action required | 不可参与 | 暴露 intervention blocker |
| expired | eligible + fresh | 不可参与 | 进入 stale closure |
| fresh | wrong instrument/profile | 不可参与 | scope/identity mismatch |

### 5.4 Protected Promotion

Unit 测试必须逐项拒绝：

1. 未枚举到的 active Ticket；
2. 未归属 position 或 open order；
3. internal/exchange quantity 不同；
4. Stop 缺失、数量不足、side 错误或非 reduce-only；
5. `runner_protected` 缺 TP1 fill lineage；
6. unresolved command；
7. open incident；
8. Reservation 或 Netting Domain 已错误释放；
9. batch、policy、schema、commit、seed 任一 mismatch；
10. Entry 未在 fence 下启动；
11. final postflight 后 service 异常；
12. Promotion 重试不是 exact idempotent state。

Batch policy 测试必须证明：exact current version 可用；仅直接 `v1 -> v2` 且 ENTRY 已
arm 的 successor 可继续使用；`v1 -> v3`、`v2 -> v3`、未 arm 的 v2 或其他版本漂移
全部拒绝。

### 5.5 Capacity Sizing

参数化测试至少覆盖：

| 维度 | Case | 断言 |
| --- | --- | --- |
| Ticket stop risk | 低于、等于、高于 `3%` budget | quantity 不超过单 Ticket 风险预算 |
| Gross stop risk | 当前为 `0%`、`3%`、`6%`、超过 `6%` | remaining gross risk 正确；耗尽时拒绝 |
| Ticket margin | tight stop 需要超过 `45%` margin | quantity 被单 Ticket margin cap 截断 |
| Gross margin | 已使用 `0%`、`60%`、`90%` | 总 margin cap 生效 |
| Count | active Ticket 为 0、1、2、3 | 第四个被 count gate 拒绝 |
| Venue rules | step、minimum、TP1/Runner boundary | rounding 后仍可执行，否则明确拒绝 |
| Leverage | configured 5、超过 policy、规则缺失 | 采用 5x readonly fact；不产生 leverage mutation |
| Decimal | 极小余额、极窄 stop、重复小数 | 无 float、无负值、无向上越权 rounding |

Owner 已批准的 exact policy 为单 Ticket `3%`、账户总风险 `6%`、单 Ticket 保证金
`45%`、账户总保证金 `90%`、最多三个 Ticket。测试必须同时证明两个完整风险 Ticket
通常可共存、第三个 Ticket 只能使用剩余风险和保证金；在 repair 部署前不得把 GREEN
误写成生产已生效。

### 5.6 Deployment State Machine

状态机 Unit 测试对每个 phase 检查：

1. allowed predecessor；
2. exact completion predicate；
3. retry/idempotency；
4. permitted services；
5. fence state；
6. failure recovery；
7. target identity conflict；
8. ops journal attempt count 与 sanitized error。

## 6. PostgreSQL Integration 规格

### 6.1 Lane Claims

Disposable PostgreSQL 中同时准备：

1. 三个 active protected aggregate；
2. 一个 Settlement pending；
3. 一个 Review pending；
4. 七个 due certification targets；
5. 一个 due Fee Monitor；
6. 可选 Unknown Command 与 post-fill risk case。

并发启动两个 Reconciliation process 模拟器，必须证明：

1. 同一 work 不被双 claim；
2. `SKIP LOCKED` 只防重复，不成为公平性的偶然来源；
3. 每类 Housekeeping 在 max wait 内被一个 worker 完成；
4. transaction 在 venue read 前提交；
5. lease timeout 后 exact work 可恢复；
6. stable ordering 在重复运行中一致。

### 6.2 Certification Batch 原子性

必须验证：

1. 六个成员完成、一个成员未完成时 batch 不 complete；
2. 最后成员与 batch completion 在同一 transaction；
3. 两个 process 竞争最后成员只能完成一次；
4. failed/blocked batch 不被 current upsert 反向改成 complete；
5. batch identity 与 current certification identity 交叉不污染。

### 6.3 Capacity 原子重验

两个不同 Signal 并发构建 Claim，随后在全局 ENTRY lane 中依次提交。第二个提交必须读取
第一个已经更新的 account exposure/reservation，并重新计算或拒绝；禁止两个 Claim 都按
同一旧 usage 成功占用总风险或总保证金。

### 6.4 Schema Baseline

Schema test 必须证明：

1. `migrations/trading_kernel/versions` 只有下一版单一 clean baseline；
2. 空 schema 可以 upgrade 到 head；
3. downgrade 明确 fail-closed，并要求从新的空 schema 重建；
4. 表、索引、constraint 与 metadata exact；
5. 旧 policy 字段、旧 baseline、兼容 view、trigger、reader 和双写不存在；
6. ops journal schema 与 application schema 的删除边界清晰。

## 7. Full-chain 规格

### 7.1 Production-shaped 15 分钟虚拟运行

建立 **15 分钟**虚拟时间，process poll 固定 **5 秒**。输入包含 BTC、ETH、SOL、BNB、
XRP、DOGE、ADA 七个认证目标以及三个不同 Netting Domain 的 active protected Tickets。

验收断言：

1. 每个 active position 按安全 cadence 被 reconcile；
2. Settlement 在 60 秒内至少取得一次执行机会，并按事实从 pending 前进或重排；
3. Review 在 60 秒内至少取得一次执行机会，并在 configured economics visibility grace
   内完成或以明确 unavailable 前进；
4. 七个 certification 均按 refresh/max-wait 合同前进；
5. Fee Monitor 在 10 分钟边界内真实读取并持久化；
6. 没有 Ticket 丢失 Stop、TP1 或 Runner protection；
7. 没有额外 Exchange Command、Incident 或文件输出；
8. virtual clock 使用真实 due-at，不通过手工解锁行制造进度。

### 7.2 Signal stale/recovery 链

```text
Observation
-> fresh StrategySignal
-> readiness candidate_ready
-> certification expires
-> Entry arbitration skips Signal
-> certification refreshes
-> same Signal participates
-> CapacityClaim/Ticket issued once
```

必须证明没有 duplicate Signal、没有 terminal rejection、没有第二代 ENTRY command。

### 7.3 Protected Promotion 链

```text
protected Ticket + exact Stop/TP1
-> deploy target identity with Entry fenced
-> Certification Batch complete
-> exact internal/external protected snapshot
-> Entry starts while fenced
-> final postflight
-> unfence
-> different Netting Domain can issue one Ticket
-> original Ticket protection remains unchanged
```

同一测试还要注入一次 postflight mismatch，证明失败分支 refence Entry 且原 Ticket 的
Lifecycle/Reconciliation 仍工作。

### 7.4 Fault Chain 保留

修复不得破坏以下已有硬语义：

1. unknown exchange outcome 不盲目重发；
2. partial ENTRY fill 取消 exact remainder 并 controlled flatten；
3. authoritative rejection 不创建下一 ENTRY generation；
4. same Netting Domain 不重复占用；
5. long/short independent sides 可并存；
6. runtime identity mismatch 禁止 exchange mutation；
7. Initial Stop 缺失时 fail-closed；
8. Settlement/Review 只在 exchange-flat 与内部释放后完成。

## 8. Deployment Failure Matrix

### 8.1 注入点

| 注入阶段 | 故障 | 期望 Fence | 期望 Worker | 数据恢复 |
| --- | --- | --- | --- | --- |
| STAGED | release marker 不一致 | 保持原状态 | 旧 runtime 不变 | 丢弃 stage |
| QUIESCED | worker 未全部停止 | present | 不启动 target | 不改 schema/identity |
| IDENTITY_ROTATED | identity transaction 失败 | present | 全停 | ops journal 可重试 |
| READONLY_WORKERS_STARTED | Observation 或 Reconciliation crash | present | 只保留 identity 正确者 | 不启动 Lifecycle/Entry |
| TARGET_CERTIFIED | 一个 member blocked/timeout | present | readonly workers | 新 batch 重试，旧 batch 不改 |
| LIFECYCLE_STARTED | smoke 失败 | present | Observation/Reconciliation | 停 Lifecycle |
| ENTRY_STARTED_FENCED | Entry 启动失败 | present | 三个 safety workers | 停 Entry |
| ENTRY_UNFENCED | final postflight 或 service health 失败 | 立即恢复 | 三个 safety workers，Entry 停 | 不回滚旧 schema |

### 8.2 Crash/Resume

对每个阶段模拟 process 在“动作完成、journal 未标记完成”和“journal 标记开始、动作未完成”
两个位置 crash。重新运行必须通过 `phase_satisfied()` 从当前事实判断，不重复 destructive
动作，不启动旧 writer，不删除非 BRC 数据。

## 9. Local Clean-Rebuild Rehearsal

### 9.1 环境

Rehearsal 使用 disposable PostgreSQL、临时 release root、fake systemd backend 和 recording
Binance USD-M readonly adapter。禁止使用生产凭证执行 mutation。

### 9.2 必须完成的链路

1. 从空 application schema 开始；
2. 安装唯一 baseline；
3. seed Registry、Owner Policy、Capability、runtime identity；
4. 一次安装 approved seven-instrument manifest；
5. 启动 Observation/Reconciliation 模拟器；
6. 完成 Certification Batch；
7. 自动推进六个 Universe 到 Active；
8. 启动 Lifecycle 并完成 flat smoke；
9. 启动 Entry while fenced；
10. 执行 final postflight 并 unfence；
11. 重跑同一 operation，证明 exact idempotency；
12. 全程记录 exchange mutation count = 0。

### 9.3 时间预算

本地 fake rehearsal 应在秒级完成；带真实 readonly Binance sandbox/recorded latency 的
rehearsal 必须有明确总 timeout。任何测试不得允许“等待几十小时”作为正常结果。

## 10. Static 与质量门

### 10.1 必跑命令

```bash
python3 -m pytest -q tests/trading_kernel/unit
python3 -m pytest -q tests/trading_kernel/integration
python3 -m pytest -q tests/trading_kernel/full_chain
python3 -m pytest -q tests/trading_kernel/architecture
python3 -m pytest -q tests/trading_kernel
python3 -m ruff check src/trading_kernel tests/trading_kernel scripts/trading_kernel
python3 -m mypy src/trading_kernel scripts/trading_kernel
python3 scripts/audit_production_runtime_file_io.py
git diff --check
```

若仓库当前 Mypy 入口由项目配置定义，则使用该入口的 repository-wide 命令，不通过缩小
扫描范围绕过失败。

### 10.2 Architecture Gate

必须证明：

1. 生产执行代码只在 `src/trading_kernel/**`；
2. migration 只有一个 current baseline；
3. systemd 仍只有四个 worker service；
4. 不存在 timer worker；
5. 不存在旧 policy 字段、旧 test name contract、兼容 adapter、旧表 reader 或双写；
6. current docs allowlist、入口引用和 volatile fact ownership 正确；
7. 正常 no-signal cadence 不写 JSON/Markdown。

## 11. Tokyo Readonly Smoke

### 11.1 部署前

Tokyo 只读检查必须重新获取：

1. exact release、commit、schema、seed；
2. Entry fence 与四个 services；
3. active Tickets、Reservations、Commands、Incidents；
4. exchange account mode、margin mode、configured leverage；
5. positions、open orders、protection ownership；
6. approved manifest 与 current Universe pointers；
7. database/exchange flatness 或 exact protected facts。

### 11.2 部署后

必须验证：

1. target identity 与 immutable tag；
2. Certification Batch exact complete；
3. 三个 safety workers 稳定且 restart 不增长；
4. Entry 在 fence 下先启动；
5. final postflight 后才移除 fence；
6. 无 unknown command、open incident、未归属 order/position；
7. 一个代表性 idle window 内 lane metrics 无 deadline breach；
8. 结果写入 `MAIN_CONTROL_ROADMAP.md`，不复制到稳定设计文档。

## 12. 通过与失败判定

### 12.1 Release Candidate Pass

只有以下全部成立才允许生成部署 commit：

1. 所有 RED 已先在旧实现中复现；
2. 新实现 GREEN，且旧错误测试已删除或重写；
3. unit、integration、full-chain、architecture 全部通过；
4. schema empty rebuild 与 repeatability 通过；
5. local deployment failure matrix 全部通过；
6. full-chain recording venue mutation count 符合场景；
7. Ruff、Mypy、file-I/O、diff checks 通过；
8. requirement-to-test traceability 无空项；
9. D-CAP-01 的 exact 值与 profile、schema、seed、certification 和 tests 一致。

### 12.2 Hard Fail

以下任一情况直接阻止部署：

1. 只能通过延长服务器等待来通过；
2. 只能通过 direct SQL、手工清 slot 或手工拼 Ticket 清单恢复；
3. 测试依赖 fixture 注入下游状态绕过真实 producer；
4. active position 下 Housekeeping 仍无最大等待保证；
5. protected Promotion 需要放松 unknown/incident/protection gate；
6. 新 schema 需要旧表 reader、兼容 migration 或双写；
7. 本地无法复现或验证 deterministic deployment phase；
8. 任何测试或脚本发生未授权 exchange mutation。

## 13. 交付证据格式

每个 Task Card 完成时提交一份简短、可复核的证据表：

| 字段 | 内容 |
| --- | --- |
| Requirement | 对应 R-ID 与 defect ID |
| RED | 旧实现失败的测试名和失败原因 |
| GREEN | 新实现通过的测试名 |
| Refactor | 删除的旧代码、旧测试和旧字段 |
| Database | disposable PostgreSQL revision 与重建结果 |
| Exchange boundary | readonly/mutation 调用计数 |
| Static gates | Ruff、Mypy、architecture、file-I/O、diff |
| Remaining uncertainty | 尚未由本卡证明的内容 |

仅有“测试通过”而没有 production-shaped 场景、数据库证据和 exchange boundary 计数，不
构成本规格的完成证据。
