---
title: SOR_DYNAMIC_INSTRUMENT_SELECTION_TRADING_V0_DESIGN
status: DESIGN_APPROVED
date: 2026-08-23
phase: P3-X.2
design_id: sor-dynamic-instrument-selection-trading-v0
selection_spec_id: sor-dynamic-selection-v0
implementation_authority: SEE_IMPLEMENTATION_PLAN
production_authority: NONE
supersedes: 2026-08-20-sor-dynamic-selection-forward-shadow-design.md
---

# SOR Dynamic Instrument Selection & Trading V0 Detailed Design

## 1. Decision

本设计把已经通过 Historical Replay 的 **SOR Dynamic Selection V0** 直接接入正式
Crypto SOR 交易资格链，不再建设独立 Forward Shadow。

推荐架构冻结为三个通过 PostgreSQL durable handoff 解耦的 Plane：

```text
Selection Plane

Fixed Candidate Panel public data
-> SelectionCore
-> immutable SelectionSnapshot + exact 24 MemberDecisions
-> DB commit
-> END

================ durable PostgreSQL handoff ================

Runtime Materialization Plane

open current Selection Period at decision boundary
-> PRE_FENCE_CONTINUITY for exact previous pair
-> run/observe Selection durable handoff in parallel
-> claim latest unresolved Snapshot or terminal Selection failure
-> compare current runtime authority
-> VALID_EMPTY / NO_CHANGE / Desired Generation
-> Strategy Entry Vacuum when authority must change
-> drain unfinished ENTRY commands and venue orders
-> serial LONG warming -> staged
-> serial SHORT warming -> staged
-> audit any unauthorized closed-bar gap -> COMPLETE
-> atomic switch of both current pointers
   or explicit post-fence FALLBACK_PREVIOUS
-> immutable SelectionSessionAuthority
-> END

================ durable runtime authority ================

Observation / Entry / Lifecycle / Reconciliation

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

Deployment Plane

code/schema/capability classification
-> stop/migrate/deploy/start when required
-> recover durable runtime authority
-> reconciliation
-> readonly verification
-> DEPLOY COMPLETE
```

**Selection Plane 不拥有任何 Runtime mutation**；**Runtime Materialization Plane 不依赖
Selector 的 Python call stack**；**Deployment Plane 不同步等待某个 Dynamic Universe 完成
warming 或 activation**。

核心决策如下：

1. **`brc_strategy_universe_current` 继续作为 Instrument membership 的唯一运行时权威**；
   `SelectionSessionAuthority` 只冻结该 Session 哪一对 Universe 获得时间有界的新 ENTRY
   权限，`StrategyEntryVacuum` 只表达负向 fence，不建立第二套 member set；
2. **Selection Runner** 只领取 Selection Job、读取 Binance public data、运行纯
   `SelectionCore`，并原子提交 **SelectionSnapshot + exact 24 MemberDecisions**；提交
   `SNAPSHOT_READY` 后本次 Selection Job 结束；
3. Selector 不读取 current Universe、不判断 `VALID_EMPTY/NO_CHANGE/DESIRED`、不创建
   Generation、不打开 Vacuum、不 warming、不 activation、不 fallback；
4. 独立 **Materialization Coordinator** 从 PostgreSQL claim unresolved Snapshot，比较 current
   runtime authority，并拥有 Generation、Vacuum、ENTRY drain、warming、activation、fallback
   和 supersession；Selector 已退出或崩溃时仍可独立恢复；
5. 新增 **Selection Materialization Generation**，把 LONG/SHORT 两个 Desired Universe
   作为一个最终原子切换单元；Candidate Panel 与 Active StrategyUniverse 分离，24 个候选
   不会自动获得交易资格；
6. `Ready = 1..7` 时形成同等数量的 Desired members；`Ready = 0` 是合法
   **`VALID_EMPTY`**，整个有效周期无新增交易、不补位、不 fallback previous；
7. **任一 Candidate 缺少 Kline、窗口不完整或 source integrity 失败时，整个 Selection
   attempt 进入 `SOURCE_FAILED`**，不得把该 member 降级为普通 `INELIGIBLE`，也不得让后续
   Rank 被动补位；Product/Activity 等策略资格不合格仍是正常 `INELIGIBLE`；
8. 新 generation warming、认证、超时或双边 staging 失败时，只在全部 fallback gates通过后
   恢复切换前真实 Active Universe 的 new-ENTRY authority，并记录
   **`FALLBACK_PREVIOUS`**；这不是 Static7 fallback；
9. **每个已处于`dynamic_selection`的Selection Period**都在`D 01:00`decision boundary先建立
   **`PRE_FENCE_CONTINUITY` Authority**，使exact current pair从Authority period开始持续拥有new-ENTRY
   权限，直到普通`NO_CHANGE`替换它或Vacuum commit原子切断。它覆盖等待Selection、Selection
   source/compute失败和等待Materialization，不撤单、不打开Vacuum、不记fallback；只有Vacuum
   打开后的运行失败才可能进入正式`FALLBACK_PREVIOUS`；
10. LONG/SHORT 继续是两个 Universe，并复用现有 global warming queue 串行 warming；只有
   两边都 staged 后才原子切换，禁止方向半切换；
11. 新 Snapshot 与 current member set 相同且 current pair operationally valid 时，记录
   **`NO_CHANGE`**，不 fence、不 warming、不撤销 ENTRY；
12. 需要切换或进入 `VALID_EMPTY` 时，先建立数据库 **Strategy Entry Vacuum**；从该 commit
   起 FinalGate/ENTRY dispatch 禁止新增入场，并撤销旧 Universe 尚未完成的 ENTRY；
13. 真空撤单竞态中的部分成交只有在实际数量仍能按冻结 Exit Policy 形成合法的
    **TP1 + Runner 两条正数量腿**时才保留；否则执行安全 controlled flatten；删除
    `runner_only_partial`；普通未知/意外部分成交继续执行现有 controlled-flatten 语义；
14. 任何SOR交易Authority都必须证明从`eligibility_not_before_ms`到其
    `first_eligible_close_time_ms`之前不存在未授权且未审计的closed-bar区间。若eligible-close
    authority连续则无需audit；若存在gap，则必须在Authority commit前完成durable
    **Authority Gap Audit**并同时持久化positive suppression或checked-negative proof。该不变量
    统一覆盖late continuity、late`NO_CHANGE`、Dynamic activation、fallback和Pause Resume；
15. Owner Pause 优先于 Selection、warming、activation 和 fallback；暂停期间继续计算
    Snapshot，但不 materialize、不恢复旧交易权限；
16. 新合法 Selection 到来时，尚未生效的旧 Desired generation 进入
    **`SUPERSEDED`**，只处理最新合法 Selection；
17. **Selection Runner、Materialization Coordinator、Observation Runner** 是三个独立应用
    组件，使用独立 DB lease、transaction 和恢复入口；V0 不强制新增第五个 systemd Worker，
    允许托管于现有进程，但禁止通过同一 Python call stack 保存跨组件进度；
18. 发布必须显式分类为 `COMPATIBLE_RESTART` 或
    `REQUIRES_RUNTIME_REMATERIALIZATION`；前者恢复 persisted Active Universe 且不 warming，
    后者先 fence 再显式重新物化；
19. Vacuum reconfiguration的Authority Gap Audit scope固定为
    **previous pair members ∪ desired pair members**，确保新pair activation与旧pair fallback都
    不会交易gap期间的second cross；late continuity/late ordinary`NO_CHANGE`只audit实际将获权
    的current pair；
20. Generation只保存两个EventSpec target、side、expected member digest和materialization
    order。Dynamic Desired members直接来自immutable Snapshot Selected decisions；Static rollback
    members直接来自immutable baseline Universe。实际Universe在创建时写
    `materialization_generation_id`，不复制target-member表、不建立第二materialization linkage
    表，也不在Universe上重复保存direct Snapshot FK；
21. **Universe semantic digest 保持现有 membership-only 合同**，Selection provenance 只通过
    Generation/Authority FK 表达，不把 Snapshot、Session 或 Selection digest写入Universe
    digest；
22. 每个可交易Authority冻结明确的`first_eligible_close_time_ms`。Authority commit必须发生在
    该canonical close之前；若transaction跨越边界则rollback、扩展gap audit并选择后一close，
    Observation只处理`close_time_ms >= first_eligible_close_time_ms`；
23. 第一次`static_baseline -> pending dynamic_selection`不创建
    `PRE_FENCE_CONTINUITY`：existing static authority持续到首个Dynamic outcome commit；首次尝试
    失败则保持Static模式。本文只授权编写Implementation Plan，不授权编码、Migration、部署或
    生产切换；
24. `session_start_ms=D 00:00`只保留SOR Episode/Session身份；Selection/Authority Period从
    `D 01:00`decision boundary开始。`VALID_EMPTY`只从其Vacuum/Authority commit向前阻止new
    ENTRY，不追溯改写此前合法continuity事实；unfinished ENTRY仍按Vacuum drain处理，已成交或
    已保护Ticket继续正式Lifecycle。

### 1.1 Owner-frozen production semantics

| Question | Frozen Owner decision | Exact design interpretation |
| --- | --- | --- |
| New Universe switch failure | **Restore previous instruments** | Exact pre-materialization Active LONG/SHORT pair receives explicit `FALLBACK_PREVIOUS`; never silent Static7 |
| First Dynamic attempt post-fence failure | **Restore Static through transition Authority** | Reuse `FALLBACK_PREVIOUS` with `STATIC_BASELINE` source、exact failed Generation/Gap Audit/first eligible close；mode remains Static |
| `Ready < 7` | **Allow fewer than 7** | `Ready=1..7` all Selected；`Ready=0` is valid `VALID_EMPTY`，no new opportunity and no fallback |
| Candidate data | **Binance public market data** | Candidate Panel does not need StrategyUniverse/RuntimeScope/certification authority |
| Pre-fence period | **Previous instruments continue** | Every already-Dynamic Selection Period uses `PRE_FENCE_CONTINUITY` through Selection and materialization waiting；Vacuum commit is the exact cutover fence |
| Previous set stops new trades | **Immediately before warming** | Open Vacuum only after Snapshot and Desired members commit；do not fence during data fetch/calculation |
| LONG/SHORT shape | **Separate Universes, serial warming** | Reuse the single global warming queue；no direction receives Active authority during staging |
| Fact model | **Generic first** | Generic identity stores `decision_at/feature_cutoff_at/effective_from/selection_spec`；SOR details live in typed extension |
| Vacuum ENTRY handling | **Cancel unfinished ENTRY** | Unfilled orders are cancelled；vacuum-attributed partial fill retains actual exposure after exact remainder cancellation and protection |
| Owner Pause | **Highest priority** | Abandon materialization；never fallback；existing Position lifecycle continues |
| Newer Selection | **Newest valid wins** | Unactivated older Desired generation becomes `SUPERSEDED` |

（来源：Owner 在本次 active task 中明确冻结的生产语义。）

在这些 Owner 决策之上，本设计冻结 **整个 Selection generation 原子一致**：LONG/SHORT
可以串行 warming，但必须双边 staged 后一次性切换；任一侧失败则两侧都不切换。恢复
previous pair 还必须同时满足 Owner Enabled、previous pair operationally valid、Entry Vacuum
已经 drain 完成。该边界基于当前单-Universe activation 无法防止方向半切换的代码事实。

## 2. Known Facts

### 2.1 Historical evidence

Owner 提供的独立 Replay 已对冻结 V0 规则完成定量验证：

| Evidence | Dynamic | Comparison | Result |
| --- | ---: | ---: | ---: |
| Tail3 / 100 directional slot-days | **9.841** | Static **7.931** | **+24.1%** |
| Random envelope | **9.841** | Median **7.975** / P75 **8.117** / Max **8.384** | Dynamic above all 100 |
| Selection gradient | **9.841** | Near **8.295** / Not Selected **6.177** | Ordered |
| Complete 90-day blocks | — | — | **9 / 10** positive |
| LONG lift | — | Static | **+19.0%** |
| SHORT lift | — | Static | **+29.0%** |
| Tail3 / Trigger | **11.76%** | Static **9.78%** | **+20.2%** |
| Largest exclusive contributor | **8.6%** | Gate **50%** | Passed |
| Selection-ready range | **14–24** | EMPTY **0** | Passed |

这些数值保留独立Replay的原始研究证据。DS-00后来确认其Feature arithmetic使用binary64；本设计
已经要求生产Price geometry使用`Decimal`，因此961×24 Golden按precision 38 / `ROUND_HALF_EVEN`
冻结，并把7个相等OR/ATR cohort边界的float rounding差异显式记录在manifest中。Decimal Golden
的Dynamic Tail3为`1,323`而非`1,324`；这不是V1规则修改，不改变Feature、Activity floor、Top N、
Candidate Panel或Outcome。

该结果支持的是：

> 固定 24-symbol Panel 内，`UTC 01:00` 可知的 Dynamic Selection V0 在历史路径上提高了
> SOR v4 的 policy-qualified `+3R` opportunity supply。

它不证明真实净收益、未来稳定性或更高风险的合理性。（来源：Owner 提供的
`/Users/jiangwei/Downloads/REPORT.md`，SHA-256
`de8edc672552097ad6f9e3988e08254f75b46d33433ad2cd12fd1e56de59a298`）

### 2.2 Current StrategyUniverse facts

当前代码已经具备以下正式边界：

1. 一个 EventSpec 的 Universe 固定为 **1–10** 个成员；
2. Universe member immutable；
3. Warming scope 只读市场事实，不产生 Signal；
4. Active scope 才可产生 Signal；
5. Signal、CapacityClaim、Ticket 均冻结 `universe_version_id` 和
   `universe_semantic_digest`；
6. current pointer 切换受 global ENTRY lane fence 保护；
7. 现有 Schema 全局只允许一个 Warming Universe，适合 Owner 决定的 LONG/SHORT 串行
   warming，但缺少“warm 完成、尚未 Active”的 staged lifecycle；
8. SOR LONG 与 SHORT 是两个独立 EventSpec，现有单-Universe activation 不能保证双边
   generation 最终原子切换。

（来源：`src/trading_kernel/domain/strategy_universe.py`、
`src/trading_kernel/application/install_strategy_universe.py`、
`src/trading_kernel/infrastructure/pg_universe_repository.py`、
`migrations/trading_kernel/v4_schema.py`）

### 2.3 Current Observation and certification facts

| Boundary | Current behavior | Consequence for V0 |
| --- | --- | --- |
| Observation process | Persistent worker, **5s** poll, one due scope per tick | It may host V0 loops, but Selection/Materialization/Observation require separate entry points and leases |
| Universe warming | Each Warming scope independently fetches and freezes facts | LONG/SHORT must serially warm, then remain staged until one final switch |
| Certification target | Currently selected from Warming/Active RuntimeScopes | Add staged-generation targets for second-side warming；Candidate Panel itself still has no RuntimeScope |
| Certification owner | Reconciliation Worker | Reuse it for each Desired Universe；do not add a Selector certification worker |
| Public Kline model | Current `ClosedCandle` stores base `volume` only | V0 requires a separate typed source for Binance `quote_volume` |

（来源：`src/trading_kernel/interfaces/observation_worker.py`、
`src/trading_kernel/infrastructure/pg_signal_repository.py`、
`src/trading_kernel/infrastructure/pg_universe_repository.py`、
`src/trading_kernel/infrastructure/binance_public_market_source.py`）

### 2.4 Current post-Signal authority facts

当前实现会在 Signal issuance 和 ENTRY dispatch 时重新验证 current Active Universe。
Universe pointer 切换发生在 ENTRY command 为 `prepared`、`claimed` 或 `outcome_unknown`
期间时，会被数据库 ENTRY lane fence 拒绝；ENTRY 已 accepted 后，既有 Ticket 生命周期读取
冻结 Ticket authority，不再依赖新的 Universe。（来源：
`src/trading_kernel/application/issue_ready_signal.py`、
`src/trading_kernel/application/revalidate_entry_dispatch.py`、
`migrations/trading_kernel/versions/0001_trading_kernel_baseline_v4.py`、
`tests/trading_kernel/full_chain/test_crypto_universe_failure_recovery.py`）

### 2.5 Current partial-fill conflict

当前生产语义把任何 `EntryPartiallyFilled` 归为 `PARTIAL_FILL_INCIDENT`：先持久化并执行 exact
remainder cancel，确认撤单后创建 `CONTROLLED_FLATTEN` command，最终释放 ENTRY lane。现有
Ticket 的 TP1 quantity 也冻结于计划数量，不能直接用于更小的实际成交仓位。（来源：
`AGENTS.md`、`docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`、
`src/trading_kernel/domain/reducer.py`、`src/trading_kernel/domain/ticket.py`、
`src/trading_kernel/domain/exit_policy.py`、`src/trading_kernel/application/reconcile_ticket.py`）

Owner 最新规则要求：**仅当部分成交属于 Selection/Owner-control 交易真空的撤单竞态时，
且实际成交数量能够按冻结 Exit Policy 形成合法的正数量 **TP1 + Runner** 两腿时，保留实际
成交仓位、撤销剩余数量并继续保护生命周期。否则必须进入安全 controlled flatten，不允许
`runner_only_partial`。因此这不是现有语义的重新解释，而是一个有明确 `vacuum_id`、撤单
意图、实际成交计划和两腿可行性证明的新受控分支。普通 partial fill、无法证明归属于真空的
partial fill、保护方向错误、两腿数量不可物化或硬风险越界，仍走现有 Incident +
controlled-flatten 安全路径。

## 3. Analysis

### 3.1 Why StrategyUniverse remains the eligibility authority

纯 Selection Overlay 会新增第二套成员资格判断，并要求修改 RuntimeScope、Signal ingestion、
Ticket lineage、Entry preflight 和 Observation target generation。即使 Overlay 最终与
Universe 求交，生产代码仍需同时解释两套 current authority，形成双重权威和漂移风险。

复用 StrategyUniverse 的优点是：

1. Production Selected `1..7` 已满足现有 1–10 member contract；
2. Signal、Claim、Ticket 已完整冻结 Universe lineage；
3. Warming、certification、member immutability 和 ENTRY lane fence 已存在；
4. 既有 Ticket 的生命周期不会因 Universe replacement 被改写；
5. Admission 无需增加 Alpha filter，继续只负责风险、容量、账户、Netting 和 Owner Policy。

因此，本设计不建立 `Effective Universe = Universe ∩ Overlay` 的双 Authority。Selection
负责产生 **Desired Universe facts**，而正式生效仍只通过 StrategyUniverse current pointer。

### 3.2 Why a Materialization Generation is required

LONG 与 SHORT 使用同一个 Selected Set，但当前是两个 EventSpec。Owner 已冻结“继续分开
Universe、串行 warming”；如果 warm 完一个方向就立即激活：

```text
LONG B active
-> SHORT B warming failed
-> production becomes LONG B / SHORT A
```

就会出现同一 SelectionSnapshot 的方向半切换。本设计因此引入 generation identity，并把
Universe lifecycle 扩展为 `warming -> staged -> active`。LONG、SHORT 串行完成 warming，
但 staged Universe 没有 Signal authority。只有两边都 staged 后，最终 transaction 才同时：

1. 锁定两个 target Universe；
2. 验证同一个 SelectionSnapshot/generation；
3. 验证相同 exact Selected `1..7` member set；
4. 验证两边 certification 和 warm readiness；
5. retire 两个 previous Universe；
6. activate 两个 target Universe；
7. 更新两个 current pointers；
8. 激活 generation 并提交最终 SelectionSessionAuthority/current pointer。

### 3.3 Why FALLBACK_PREVIOUS is adopted

Owner 已冻结：materialization 失败后恢复**切换前真实 Active Universe**，而不是固定
Static7。该语义必须显式记录：

```text
generation B succeeded -> B becomes Active
generation B failed    -> previous generation A may regain new-ENTRY authority
                         with FALLBACK_PREVIOUS
```

旧 Universe 在 materialization 期间不 Retire、不改 current pointer，只由 exact Strategy Entry
Vacuum 暂停 new ENTRY。这样失败恢复不需要复活 retired row，也不会改写已有 Ticket。
`FALLBACK_PREVIOUS` 必须保存 previous LONG/SHORT Universe IDs、原因和时间，不能静默发生。

`Ready = 0` 是不同语义：合法 Snapshot 明确没有合格成员，所以本 Selection Period不再产生新机会，
不恢复 previous。对已经处于Dynamic mode的Session，Materialization Plane不等待Selection结果，
而是在`D 01:00`Selection decision boundary提交`SelectionSessionAuthority(PRE_FENCE_CONTINUITY)`，授权exact current
LONG/SHORT pair持续new ENTRY。Selection成功、失败、重试或Generation仍在PENDING/DESIRED都不
提前打断它；失败只通过更高sequence continuity reason记录
`SELECTION_SOURCE_FAILED/SELECTION_COMPUTE_FAILED`。只有Vacuum commit才原子切断该Authority。

只有Desired Generation已确定且Vacuum已打开后的materialization failure，才可能进入
`FALLBACK_PREVIOUS`，且仍须通过Owner Enabled、previous operational validity、Vacuum drained、
Authority Gap Audit complete和no-supersession gates。`PRE_FENCE_CONTINUITY`、`VALID_EMPTY`、
Owner Pause和supersession都不是fallback条件。

### 3.4 Why SelectionSessionAuthority is required

只依赖 `Ticket -> Universe -> Snapshot` 不能准确表达三种已冻结结果：

1. `NO_CHANGE`：今天产生了新 Snapshot，但 Universe version 没有变化；
2. `FALLBACK_PREVIOUS`：今天的交易权限来自故障恢复，而不是 previous Universe 原始
   Snapshot；
3. `PRE_FENCE_CONTINUITY`：不论Selection仍在计算、已经失败或正等待Vacuum，previous pair
   在pre-fence阶段被显式授权继续。

因此新增不可变 **`SelectionSessionAuthority`**。它冻结exact Snapshot或Selection Job/
attempt、Session、Owner control version、授权结果、LONG/SHORT Universe IDs、grant proof、
`effective_from_ms`、`first_eligible_close_time_ms`、`expires_at_ms`和semantic digest。Dynamic
Signal、Claim、Ticket必须冻结
`selection_authority_id`，从而永久区分 `ACTIVE_NEW`、`NO_CHANGE`、
`PRE_FENCE_CONTINUITY`、`FALLBACK_PREVIOUS`、`VALID_EMPTY` 和
`OWNER_PAUSED_NOT_MATERIALIZED`。

### 3.5 Why Strategy Entry Vacuum is required

只在 Signal producer 加 fence 无法阻止已存在 Signal、已发行 Ticket 或已准备 ENTRY command
继续成交。交易真空必须成为 PostgreSQL scoped authority，并在以下三个边界重复验证：

1. Signal/Readiness 到 Admission；
2. Ticket issuance；
3. durable ENTRY command dispatch preflight。

Vacuum 不是新执行链。它只是一条比 Universe membership 更高优先级的负向 ENTRY authority；
既有 Stop、TP1、Runner、Exit、Reconciliation、Settlement 和 Review command 不读取该 fence。

显式 Owner Static rollback 仍是另一条操作，不与 daily fallback 混淆。

### 3.6 Why three independent Planes are required

Selection、Runtime materialization 与 Deployment 的失败恢复时间不同：

| Plane | Durable completion | May continue after |
| --- | --- | --- |
| Selection | Snapshot + exact 24 decisions committed，or Job failure committed | Binance read/compute process has exited |
| Runtime Materialization | Generation/Authority/Vacuum reaches an explicit durable outcome | Selector is absent；worker/process restarts |
| Deployment | Exact code/schema capability is running and durable authority is recovered/read-only verified | Pending generation remains unresolved in background |

把三者放入同一 call stack 会让 Selection 成功依赖 warming，让部署成功依赖当日 Universe
切换，并使 crash recovery 无法从单一 durable boundary 继续。本设计因此要求三个独立应用
组件、三个 lease namespace 和短事务 handoff；它不要求 V0 立即增加第五个 systemd service。

### 3.7 Why Authority Gap Audit is grant readiness

Suppression row只能证明“发生过first trigger”，不能证明“已检查且没有trigger”。保护对象也
不能局限于Vacuum，因为late continuity或late ordinary`NO_CHANGE`同样可能在first-trigger
eligibility之后留下未授权closed-bar gap。正确不变量是：每个交易Authority必须冻结以下二选一
grant proof：

```text
CONTINUOUS_ELIGIBLE_CLOSES
or
AUDITED_AUTHORITY_GAP
```

前者证明自`eligibility_not_before_ms`以来每个可交易close都由predecessor Dynamic Authority或
首次切换前Static authority连续覆盖；后者引用durable Authority Gap Audit。只有audit
`COMPLETE`与exact scope/result digest同时成立，absence of suppression row才表示negative fact。
Authority冻结`first_eligible_close_time_ms`，audit只覆盖其前一canonical close，Observation只
处理该时间及之后的close。若final transaction到达close boundary，必须rollback、增量audit并把
first eligible移到后一close，禁止依赖毫秒竞态。

### 3.8 Why Pause Resume is not ordinary NO_CHANGE

普通`NO_CHANGE` fast path要求**不存在open Vacuum**。Owner Pause后即使Selected set仍等于
current pair，Resume也必须先完成unfinished ENTRY drain和current-pair Authority Gap Audit，
再在一个transaction中resolve Pause Vacuum并提交更高sequence的`NO_CHANGE` Authority。新的
Authority必须冻结audit之后的`first_eligible_close_time_ms`；若commit跨越该close boundary，
则rollback、扩展audit并顺延到下一canonical close。它不重新warming，因为membership和runtime
facts没有改变；但也不能直接复用Pause前Authority或绕过Vacuum。

## 4. Scope

### 4.1 In scope

1. Crypto `SOR-001` v4 LONG 与 SHORT；
2. 固定 24-member Binance USDⓈ-M perpetual Candidate Panel；
3. Frozen Selection V0 Feature、Qualification、Rank 和 Top 7；
4. PostgreSQL Selection Job、SelectionSpec、SelectionSnapshot、MemberDecision 和
   MaterializationGeneration；
5. Candidate Panel public market data acquisition and Desired-member certification；
6. `PRE_FENCE_CONTINUITY`、`VALID_EMPTY`、`NO_CHANGE`、`SUPERSEDED`、Owner Pause/Resume
   和 explicit fallback；
7. Strategy Entry Vacuum、FinalGate revalidation、未完成 ENTRY drain 和 durable cancel；
8. 真空撤单竞态 partial fill 的实际数量冻结、合法双腿检验、Initial Stop、TP1/Runner 派生
   和 Review 归因；
9. `UTC 01:00` 后的selection-before-signal production sequence、通用Authority Gap Audit、
   suppression与no-backfill cursor；
10. 双 EventSpec 原子 Universe activation；
11. Selection authority 到 Signal/Claim/Ticket 的稳定追溯；
12. Owner dynamic/static/disabled mode、`FALLBACK_PREVIOUS` 和 fix-forward rollback；
13. Desired Generation事实去重、Universe单一Generation FK和baseline immutable source引用；
14. Migration、release compatibility classification、测试、发布和 postdeploy readonly
    verification 设计。

### 4.2 Explicitly out of scope

- 调整 Selection Feature、Activity floor、Top N、Candidate Panel 或方向拆分；
- Dynamic/Static/Random 的实时 counterfactual outcome engine；
- 新的 Research Worker、Feature Store、模型平台或 AI 选币；
- 修改 SOR Detector、Trigger、Stop、TP1、Runner 或 Exit Policy；
- 修改单 Ticket 风险、杠杆、保证金、容量、Netting 或 capital Policy；
- 自动 resume/pause `SOR-001`；
- 自动修改 Binance leverage、margin mode、position mode 或任何 private account setting；
- CPM、BRF2、MPG、MI 或 TradFi selector；
- 前端产品化；
- 把 Historical Tail3 lift 称为真实 Net PnL。

“不修改 Stop/TP1/Runner/Exit Policy”指不改变其价格规则和策略语义。真空 partial fill 必须
按实际成交数量重新物化同一冻结 Exit Policy 的数量腿，这是本设计明确纳入的执行物化，
不是策略参数修改。

## 5. Frozen Selection V0 Contract

### 5.1 Candidate Panel

固定 24 个 canonical Instrument：

| Group | Symbols |
| --- | --- |
| Large / liquid | BTCUSDT、ETHUSDT、BNBUSDT、SOLUSDT、XRPUSDT、DOGEUSDT |
| Established alts | ADAUSDT、AVAXUSDT、LINKUSDT、LTCUSDT、BCHUSDT、DOTUSDT |
| Mid-cap / heterogeneous | NEARUSDT、ATOMUSDT、FILUSDT、ETCUSDT、APTUSDT、OPUSDT |
| Additional panel | ARBUSDT、INJUSDT、SUIUSDT、TRXUSDT、UNIUSDT、RUNEUSDT |

数据库使用 canonical identity：

```text
binance-usdm:<SYMBOL>:perpetual
```

### 5.2 Clock and input cutoff

每个 UTC Session `D`：

```text
session_start_ms = D 00:00:00 UTC
feature_cutoff_at_ms = D 01:00:00 UTC
selection_decision_boundary_ms = D 01:00:00 UTC
```

`session_start_ms`只标识SOR价格Session与Episode；它不是Authority rollover时刻。
**Selection Period / Authority Period**从`selection_decision_boundary_ms`开始，到下一日decision
boundary结束。实现不得在`D 00:00`提前创建、到期或替换当天Selection Authority。

任何 `open_time_ms >= feature_cutoff_at_ms` 的 Kline 均不得进入 Feature input。

每个 Instrument 使用截止 `01:00` 的 exact 96 根 closed 15m Kline：

| Use | Window |
| --- | --- |
| 24h Activity | `D-1 01:00 <= open_time < D 01:00`，96 bars |
| ATR previous close | `D-1 20:15` bar close |
| Pre-OR ATR14 | `D-1 20:30 <= open_time < D 00:00`，14 bars |
| Opening Range | `D 00:00 <= open_time < D 01:00`，4 bars |

### 5.3 Exact Feature

```text
or_high  = max(high of 00:00, 00:15, 00:30, 00:45 bars)
or_low   = min(low  of 00:00, 00:15, 00:30, 00:45 bars)
or_width = or_high - or_low

tr_i = max(
    high_i - low_i,
    abs(high_i - previous_close_i),
    abs(low_i - previous_close_i),
)

pre_or_atr14 = arithmetic_mean(last 14 pre-OR true ranges)
pre_or_width_atr14 = or_width / pre_or_atr14

trailing_24h_quote_volume = sum(quote_volume of exact 96 bars)
```

金融和价格计算使用 **`Decimal`**。生产实现必须冻结 Decimal context、canonical string 和
digest serialization，并通过 Historical Golden Parity 证明排序没有因表示方式变化。

### 5.4 Qualification and reasons

Selection Runner 先执行 **Snapshot-level source integrity gate**：24 个 Candidate 都必须取得
exact 96 根连续、唯一、顺序正确的 closed Kline，且 OHLC 为有限正数、Quote Volume 为有限
非负数。任一 Candidate 缺 Kline、窗口不完整、响应被截断、时间边界漂移、价格/成交量无效
或 source integrity 不成立时，整个 attempt 进入 `SOURCE_FAILED`，不得产出 Snapshot、不得
Rank、不得让 Rank 8 补入。

Source integrity 通过后，一个 Instrument 只有同时满足以下策略资格才是 Selection-ready：

1. 属于固定 Candidate Panel；
2. `or_high > or_low`；
3. `pre_or_atr14 > 0`；
4. `trailing_24h_quote_volume >= 20,000,000 USDT`。

Primary reason 顺序冻结为：

```text
INVALID_OR_GEOMETRY
INVALID_ATR
LOW_ACTIVITY
```

`OR_DATA_INCOMPLETE`、`PRE_CUTOFF_DATA_INCOMPLETE` 不再是正常 member-level
`INELIGIBLE` 原因；它们与 `INVALID_PRICE_OR_VOLUME` 都属于 Snapshot-level
`SOURCE_FAILED` reason code。

若固定Candidate因长期停牌、下架或数据源语义变化持续触发`SOURCE_FAILED`，Selection Plane
仍不得产出Snapshot或临时删除该member。Materialization Plane在continuity gates成立时为exact
current pair保持或追加`PRE_FENCE_CONTINUITY` reason revision；若Session continuity尚未建立且
gap audit不能完成则保持fail-closed。重复或耗尽重试预算时打开Incident，修复方式是Owner复核
后发布新的SelectionSpec version/Candidate Panel，不允许Runtime临时缩小Panel后继续V0 Rank。

### 5.5 Stable ranking and states

```text
1. pre_or_width_atr14 ASC
2. trailing_24h_quote_volume DESC
3. canonical exchange_instrument_id ASC
```

| Rank / result | Member state |
| --- | --- |
| Qualification failed | `INELIGIBLE` |
| Rank 1–min(7, Ready count) | `SELECTED` |
| Rank 8–14 | `NEAR_THRESHOLD` |
| Rank 15+ | `NOT_SELECTED` |
| Ready count = 0 | Snapshot `selected_count=0`; Materializer resolves `VALID_EMPTY`; no Desired Universe or fallback |

LONG 与 SHORT 共用同一个 Selected Set。本轮禁止修改 Feature、Top N、Activity floor、
Candidate Panel 或 separate-direction ranking。Historical Replay 中 `Ready < 7 -> EMPTY` 是
固定 7-slot 对照语义；生产 V0 的 `1..7` 可变成员数是后续 Owner 运行决策，不回写历史结果。

## 6. Authority Model

| Concern | Single authority | Must not own |
| --- | --- | --- |
| Selection algorithm/version | PostgreSQL `SelectionSpec` | Current Signal eligibility |
| Candidate Panel | Immutable SelectionSpec members | Active RuntimeScope |
| Selection scheduling/lease | Selection Job projection | Runtime materialization |
| Daily decision | Immutable SelectionSnapshot + 24 decisions | Ticket/risk |
| Pairing and materialization | Materialization Generation + Coordinator lease | Selection compute/strategy semantics |
| Session ENTRY authority | Immutable `SelectionSessionAuthority` | Instrument membership or risk |
| Negative ENTRY fence | PostgreSQL Strategy Entry Vacuum | Position lifecycle |
| Instrument membership | `brc_strategy_universe_current` | Session timing or Admission risk |
| Deployment compatibility | Frozen release manifest/classification | Daily Selection outcome |
| Owner strategy enable/pause | Existing Strategy Control | Selection ranking |
| Global new ENTRY | Owner Policy `new_entry_submit_enabled` | Candidate membership |
| Account/product safety | Existing certification and action-time facts | Alpha selection |
| Existing Ticket lifecycle | Frozen Ticket/Aggregate/Commands | Current selection |

Dynamic Selection 不自行改变 `SOR-001` 的 Owner enable/pause control。Owner pause 时仍按
计划计算并保存 Snapshot，但不创建/继续 warming、不 activation、不 fallback；若 Pause 发生
在 materialization 中，当前 generation 被 abandon，Vacuum 保持关闭新 ENTRY并继续 drain。
Resume 必须基于当前有效周期的最新合法 Snapshot重新 materialize，不能直接恢复暂停前旧
Universe。Selection 不能绕过 Owner pause。

## 7. PostgreSQL Data Model

### 7.1 `brc_instrument_selection_specs`

不可变、版本化的**通用 Selection identity**，不在通用表中写死 SOR 或 `01:00`：

| Column | Meaning |
| --- | --- |
| `selection_spec_id` | Stable immutable identity |
| `strategy_group_id` / `strategy_version_id` | Exact SOR version |
| `selection_version` | Positive integer |
| `selection_kind` | Typed strategy-specific implementation key；V0=`sor_dynamic_v0` |
| `algorithm_semantic_digest` | Canonical full rule digest |
| `status` | `active` / `retired` |
| `installed_at_ms` | Install time |

约束：

- unique `(strategy_group_id, selection_version)`；
- digest format `sha256:<64 hex>`；
- active SOR V0 spec 必须具有 exact 24 members 和 exact two SOR EventSpecs；
- UPDATE/DELETE forbidden after insert；retirement 只允许受控 status transition。

SOR-specific typed extension `brc_sor_dynamic_selection_specs_v0` 以
`selection_spec_id` 为主键，保存：

| Column | V0 value |
| --- | ---: |
| `decision_offset_utc_seconds` | `3600` |
| `feature_cutoff_offset_utc_seconds` | `3600` |
| `eligibility_not_before_offset_utc_seconds` | `4500` (`01:15`) |
| `valid_until_next_decision_offset_seconds` | `86400` |
| `candidate_count` | `24` |
| `selected_count_max` | `7` |
| `near_count_max` | `7` |
| `activity_floor_quote_usdt` | `20000000` |
| `materialization_timeout_seconds` | `1800` |

以后其他策略复用通用 Snapshot/Decision/Generation，但必须使用自己的 typed spec extension，
不能把任意 JSON 参数变成生产权威。

### 7.2 `brc_instrument_selection_spec_events`

明确同一个 SelectionSpec 适用于：

```text
event_spec:SOR-001:SOR-LONG:v4
event_spec:SOR-001:SOR-SHORT:v4
```

Primary key：`(selection_spec_id, event_spec_id)`。

### 7.3 `brc_instrument_selection_spec_members`

固定 24-member Candidate Panel：

```text
PRIMARY KEY (selection_spec_id, exchange_instrument_id)
```

该表不创建 RuntimeScope，不进入 `brc_strategy_universe_current`，也不授予 Signal 或 ENTRY。

### 7.4 `brc_strategy_selection_control_current`

Owner-visible current control：

| Column | Meaning |
| --- | --- |
| `strategy_group_id` | Primary key |
| `selection_spec_id` | Current frozen Dynamic spec |
| `selection_mode` | `disabled` / `static_baseline` / `dynamic_selection` |
| `pending_selection_mode` | Nullable staged Owner change |
| `pending_effective_session_start_ms` | Exact Session where pending mode may take effect |
| `pending_authorization_id` | Durable OwnerAuthorization lineage |
| `control_version` | Optimistic version |
| `rollback_baseline_id` | Exact pre-Dynamic baseline |
| `updated_at_ms` | Current projection time |

该 control 只决定应使用 Dynamic、Static baseline 还是 no-new-signal disabled。它不替代
Strategy Control，也不改变风险 Policy。

### 7.5 `brc_strategy_selection_rollback_baselines`

在第一次 Dynamic activation 前冻结 exact pre-Dynamic LONG/SHORT membership：

| Column | Meaning |
| --- | --- |
| `rollback_baseline_id` | Immutable identity |
| `strategy_group_id` / `strategy_version_id` | Exact version |
| `source_long_universe_version_id` | Historical source identity |
| `source_short_universe_version_id` | Historical source identity |
| `semantic_digest` | Exact two source Universe identities + immutable member digests |
| `captured_at_ms` | Capture time |

不创建`brc_strategy_selection_rollback_baseline_members`。StrategyUniverse version和member rows
本身immutable、`ON DELETE RESTRICT`，baseline直接引用两个source Universe即可形成独立持久
身份。Rollback从source Universe复制成员到新的immutable Universe versions，不重新激活retired
Universe，也不复制第三份baseline member事实。

### 7.6 `brc_instrument_selection_jobs_current`

每个 spec/session 的 **Selection Plane scheduler、lease 和结果 projection**。它不得保存
Universe、Vacuum、Generation 或 Authority 状态：

| Column | Meaning |
| --- | --- |
| `selection_job_id` | Deterministic immutable identity |
| `selection_spec_id` / `session_start_ms` | Primary key |
| `scheduled_at_ms` | Exact due boundary |
| `feature_cutoff_at_ms` | Exact input cutoff；SOR V0=`01:00` |
| `state` | `DUE` / `CLAIMED` / `SNAPSHOT_READY` / `SOURCE_FAILED` / `COMPUTE_FAILED` |
| `selection_snapshot_id` | Required only for `SNAPSHOT_READY` |
| `first_blocker` | Stable source/compute reason；runtime blocker forbidden |
| `attempt_count` | Monotonic Selection attempt count |
| `next_retry_at_ms` | Nullable bounded retry schedule |
| `lease_owner` / `lease_expires_at_ms` | Selection Runner lease only |
| `projection_version` | Optimistic version |
| `updated_at_ms` | Current projection time |

合法 transition：

```text
DUE -> CLAIMED -> SNAPSHOT_READY
               -> SOURCE_FAILED -> CLAIMED   (bounded retry only)
               -> COMPUTE_FAILED -> CLAIMED  (bounded retry only)
```

`SNAPSHOT_READY` 对 Selection Plane 是 terminal。`SOURCE_FAILED/COMPUTE_FAILED` 在重试预算耗尽
后对本 Session terminal；**Selection Plane**不创建Authority、不打开Vacuum、不触发fallback。
terminal failed Job/attempt是Materialization Plane可claim的durable reason handoff；后者保持或
追加当前Session的`PRE_FENCE_CONTINUITY` reason revision，而不是等失败后才首次决定previous
pair能否交易。Runtime查询始终使用exact
`(selection_spec_id, session_start_ms)`，禁止`ORDER BY created_at DESC LIMIT 1`猜测当前Session。

### 7.7 `brc_instrument_selection_attempts`

Append-only attempt audit：

```text
selection_attempt_id
selection_spec_id
session_start_ms
worker_id
attempt_number
started_at_ms
completed_at_ms
outcome
reason_code
source_member_count
source_digest
```

仅 Selection source/compute 结果进入该 audit。网络失败、部分数据、source digest conflict 和
compute rejection 可审计；ENTRY lane busy、warming、activation conflict、fallback 等
Runtime Materialization 事实禁止写入 Selection attempt。

### 7.8 `brc_instrument_selection_snapshots`

一个 successful calculation 对应一个 immutable Snapshot：

| Column | Meaning |
| --- | --- |
| `selection_snapshot_id` | Deterministic identity |
| `selection_spec_id` | Frozen rule |
| `strategy_group_id` / `strategy_version_id` | Exact strategy |
| `session_start_ms` | UTC Session |
| `decision_at_ms` | Actual Snapshot decision/commit time |
| `feature_cutoff_at_ms` | Strategy-specific input cutoff；SOR V0=`01:00` |
| `eligibility_not_before_ms` | Strategy-specific earliest eligibility；SOR V0=`01:15` |
| `expires_at_ms` | Exact Session validity end |
| `candidate_count` | `24` |
| `ready_count` | `0..24` |
| `selected_count` | `0..7`；exact `min(7, ready_count)` |
| `source_observed_at_ms` | Bounded read completion |
| `source_semantic_digest` | Full 24-member input digest |
| `selection_semantic_digest` | Full decision digest |
| `created_at_ms` | Commit time |

Unique `(selection_spec_id, session_start_ms)`。Parent 和 24 decisions 在同一 transaction
提交，其他 transaction 不会读到半成品。

Canonical digest 明确排除 `decision_at_ms`、`source_observed_at_ms`、`created_at_ms`、lease、
attempt ID 和 worker ID 等运行时间字段。`source_semantic_digest` 只覆盖 exact input windows、
raw canonical OHLC/quote volume和source status；`selection_semantic_digest` 覆盖 Spec digest、
Session/cutoff/effective identity、ready/selected counts和排序后的24条MemberDecision digest。
因此同一输入重跑必须得到相同 digest，不会因 worker timing 漂移。

### 7.9 `brc_instrument_selection_member_decisions`

每个 Snapshot 固定 **24** 条：

```text
PRIMARY KEY (selection_snapshot_id, exchange_instrument_id)
```

至少保存：

- input window start/end；
- input window digest；
- source status；
- OR high / low / width；
- pre-OR ATR14；
- OR width / ATR14；
- trailing 24h quote volume；
- qualification booleans；
- primary reason；
- secondary reasons；
- stable rank；
- member state；
- selected boolean；
- member semantic digest。

Snapshot 和 MemberDecision 均由 DB immutability trigger 拒绝 UPDATE/DELETE。任何事后 Trigger、
PnL、Review 或人工判断都不能修改当天 Rank。

Snapshot 只陈述 Selection 事实，不陈述 Runtime outcome。`selected_count=0` 由 Materialization
Coordinator 解释为最终 `VALID_EMPTY`；Selector 本身不写 `VALID_EMPTY/NO_CHANGE/DESIRED`。

### 7.10 `brc_strategy_universe_materialization_generations`

Generation 是同一 Snapshot fan-out 到两个 EventSpec 的 desired/materialized identity：

| Column | Meaning |
| --- | --- |
| `materialization_generation_id` | Immutable identity |
| `selection_spec_id` | Exact Selection contract |
| `strategy_group_id` / `strategy_version_id` | Exact SOR version |
| `selection_mode` | `dynamic_selection` / `static_baseline` |
| `selection_snapshot_id` | Dynamic mode required；Static nullable |
| `rollback_baseline_id` | Static mode required；Dynamic nullable |
| `session_start_ms` | Dynamic exact session；Static nullable |
| `previous_long_universe_version_id` | Exact current LONG before fence |
| `previous_short_universe_version_id` | Exact current SHORT before fence |
| `desired_member_count` | `1..7` for Dynamic |
| `semantic_digest` | Generation/member/source digest |
| `lifecycle_state` | `PENDING` / `DESIRED` / `DRAINING_ENTRY` / `MATERIALIZING` / `STAGED` / `ACTIVE` / `FALLBACK_PREVIOUS` / `SUPERSEDED` / `ABANDONED` / `FAILED_CLOSED` |
| `fallback_reason_code` | Required only for `fallback_previous` |
| `lease_owner` / `lease_expires_at_ms` | Materialization Coordinator lease；independent from Selection/Observation |
| `projection_version` | Optimistic version |
| lifecycle timestamps | Desired/fence/activate/fallback/retire |

Desired intent只使用一个exact-two-row child table：

```text
brc_strategy_universe_materialization_targets
(materialization_generation_id, event_spec_id, position_side,
 expected_member_set_digest, materialization_order)
```

Dynamic Generation必须exact two target rows；两个`expected_member_set_digest`都必须等于其
immutable Snapshot Selected decisions的canonical digest。Static Generation的expected digest
来自rollback baseline引用的immutable source Universe members。`materialization_order`冻结，默认
LONG=1、SHORT=2；顺序只控制warming，不允许一个方向先获得Active authority。

不创建target-member复制表，也不创建`brc_strategy_universe_materializations`。实际Universe
install时，new immutable `brc_strategy_universe_versions` row直接写
`materialization_generation_id`；现有Universe member rows是actual materialized membership。
Unique `(materialization_generation_id, event_spec_id)`保证每个target最多创建一个Universe。
因此PENDING/DESIRED只存在expected digest，不存在nullable或预分配的假Universe identity。

`brc_strategy_universe_materialization_events` 追加记录：

```text
PENDING
DESIRED
ENTRY_VACUUM_OPENED
ENTRY_DRAIN_STARTED
ENTRY_DRAINED
LONG_WARMING
LONG_STAGED
SHORT_WARMING
SHORT_STAGED
ACTIVE
FALLBACK_PREVIOUS
SUPERSEDED
OWNER_PAUSED
ABANDONED
FAILED_CLOSED
```

Materializer 先用一个短 transaction 锁定 non-empty unresolved Snapshot、current runtime
authority和Vacuum。成员相同、current pair operationally valid且**不存在open Vacuum**时才直接
提交普通`NO_CHANGE` Authority，不创建Generation；若存在`OWNER_PAUSED` Vacuum则必须走10.10
Resume-NO_CHANGE。成员变化时才以unique `selection_snapshot_id` 创建并提交durable `PENDING`
Generation，冻结previous pair和Desired set，但不打开Vacuum。下一独立tick重锁并验证相同facts
后提交`DESIRED`；再下一tick才在Vacuum transaction转`DRAINING_ENTRY`。`VALID_EMPTY`不创建
Generation。任一pre-fence transaction失败时，current Runtime保持原状且没有fallback事实。

Generation 的identity、Snapshot、previous pair、Desired target digest和source identity永不可改；current
lifecycle projection 只允许 optimistic legal transition，terminal `ACTIVE`、
`FALLBACK_PREVIOUS`、`SUPERSEDED`、`ABANDONED` 或 `FAILED_CLOSED` outcome/reason 一旦写入不得
改写。该 event lineage 与独立 lease 是 Materializer crash/restart recovery 的正式依据。

### 7.11 Changes to `brc_strategy_universe_versions`

新增：

| Column | Meaning |
| --- | --- |
| `source_kind` | `manual` / `dynamic_selection` / `static_baseline` |
| `materialization_generation_id` | Generation FK；manual nullable |

Dynamic Universe semantic digest 保持当前代码已验证的 **membership-only** 合同，只包含：

```text
strategy_group_id
event_spec_id
canonical member set
```

`materialization_generation_id`是Universe唯一新增provenance FK，不属于Universe member/runtime
semantics，禁止进入`semantic_digest`。Dynamic追溯固定为
`Universe -> Generation -> Snapshot -> MemberDecision`；不再保存Universe direct Snapshot FK或
duplicate effective Session列，避免双路径一致性约束。

只有 Selected Set 与 current pair 不同时才创建新 Dynamic Universe identity。连续两天成员
完全相同时走 `NO_CHANGE`，复用 operationally valid current pair，但用新的
SelectionSessionAuthority 追溯当天 Snapshot。

Lifecycle 增加 `staged`：它表示 exact Universe 已完成 warming/certification，但尚未成为
current pointer，`entry_enabled=false`，不能产生 Signal。合法 Dynamic 路径是：

```text
warming -> staged -> active -> retired
warming -> abandoned
staged  -> abandoned
```

### 7.12 Warming ownership constraint

现有“全系统最多一条 Warming Universe”的 partial unique index继续保留。一个 generation
严格串行：

1. 创建并 warming LONG；
2. LONG ready 后转 `staged`，释放 global warming slot；
3. 创建并 warming SHORT；
4. SHORT ready 后转 `staged`；
5. 两边在一个 final transaction 中同时 Active。

任何时刻仍只有一条 Warming Universe；manual Universe install 与 Dynamic generation 共用
现有 global queue/advisory lock，不能并行抢占。

### 7.13 Candidate data and certification boundary

24-member Candidate Panel 直接读取 Binance public Kline，不创建 RuntimeScope、不领取
Universe certification lease，也不因此取得 Product/ENTRY 权限。只有 Snapshot 已选出的
`1..7` members 被安装为 Desired Warming Universe 后，才复用现有 Reconciliation
certification 和 warm-fact authority。

Selected member 若未通过现有 product/account/instrument safety certification，不以 Rank 8
补位；本 generation 被abandon，并按10.9 gates决定 `FALLBACK_PREVIOUS` 或fail-closed。

### 7.14 Foreign keys, unique constraints and runtime indexes

| Object | Required contract |
| --- | --- |
| SelectionSpec FK | `strategy_group_id`、`strategy_version_id` 必须指向同一 active Registry lineage；typed extension 使用 `ON DELETE RESTRICT` |
| Spec Event/Member FK | Parent `selection_spec_id` 使用 `ON DELETE RESTRICT`；EventSpec 和 Instrument 使用 canonical FK |
| Snapshot uniqueness | unique `(selection_spec_id, session_start_ms)`；unique `(selection_snapshot_id, selection_semantic_digest)` |
| Member cardinality | deferred constraint trigger 在 Snapshot commit 时要求 exact Candidate count；每个 parent exact 24 rows |
| Generation uniqueness | unique `(selection_spec_id, session_start_ms, selection_mode)`；exact two target rows；Dynamic expected digests equal immutable Snapshot Selected digest |
| Universe materialization linkage | Universe row owns the sole `materialization_generation_id` FK；unique `(materialization_generation_id, event_spec_id)`；no second linkage table；`ON DELETE RESTRICT` |
| Selection job claim | partial index `(state, scheduled_at_ms, next_retry_at_ms, lease_expires_at_ms)` where state in `DUE/CLAIMED/SOURCE_FAILED/COMPUTE_FAILED` |
| Unresolved Snapshot handoff | bounded anti-join/index from `SNAPSHOT_READY` to missing terminal Authority/current Materialization claim |
| Materialization claim | partial index `(lifecycle_state, lease_expires_at_ms)` where state in `PENDING/DESIRED/DRAINING_ENTRY/MATERIALIZING/STAGED` |
| Attempt audit | index `(selection_spec_id, session_start_ms, attempt_number)` |
| Ticket trace | index on Signal/Claim/Ticket `selection_authority_id`、Universe `materialization_generation_id` and MemberDecision `(selection_snapshot_id, exchange_instrument_id)` |
| Warming queue | retain one global partial unique index where Universe lifecycle=`warming` |

Snapshot、MemberDecision、Generation identity/terminal outcome 和 baseline semantic facts使用
DB trigger 拒绝 UPDATE/DELETE；Selection Job、Generation、Vacuum、Authority pointer 和 control
current projection各自采用 legal-state transition、独立 optimistic version 与独立 lease namespace，
并由对应 append-only facts 留痕。所有 FK 都禁止 cascade删除生产事实。

### 7.15 `brc_selection_session_authorities`

每次真正决定“当前有效周期能否产生新 ENTRY、由哪一对 Universe 产生”时，插入一条不可变
Authority fact。Pause 后 Resume 可在同一 Session 追加更高 sequence 的 Authority；旧 fact
不更新，由 current pointer 原子替换。

| Column | Meaning |
| --- | --- |
| `selection_authority_id` | Deterministic immutable identity |
| `selection_spec_id` / `session_start_ms` / `authority_sequence` | Exact SOR Session identity and Authority revision；period begins at `D 01:00` decision boundary |
| `selection_job_id` / `selection_attempt_id` | Optional continuity reason provenance；never required to open the Session |
| `selection_snapshot_id` | Required for Snapshot outcomes and Dynamic Generation fallback；nullable for continuity/pause outcomes |
| `continued_from_selection_authority_id` | Previous Dynamic Authority when grant continuity is inherited；nullable only for first Dynamic outcome or audited gap |
| `continuity_source_kind` | `SELECTION_AUTHORITY` / `STATIC_BASELINE` / `AUTHORITY_GAP_AUDIT` / `NONE` |
| `authority_gap_audit_id` | Required only when eligible-close authority was not continuous |
| `materialization_generation_id` | Required for `ACTIVE_NEW` and Generation-caused post-fence `FALLBACK_PREVIOUS`；nullable for continuity/empty/pause outcomes |
| `owner_control_version` | Exact Strategy Control version |
| `authority_outcome` | `PRE_FENCE_CONTINUITY` / `ACTIVE_NEW` / `NO_CHANGE` / `FALLBACK_PREVIOUS` / `VALID_EMPTY` / `OWNER_PAUSED_NOT_MATERIALIZED` |
| `authorized_long_universe_version_id` | Required only for trading-authorized outcomes |
| `authorized_short_universe_version_id` | Required only for trading-authorized outcomes |
| `effective_from_ms` | Actual DB action-time grant start；never backdated |
| `first_eligible_close_time_ms` | First canonical closed bar Observation may process under this grant；required for trading-authorized outcomes |
| `expires_at_ms` | Exact next Selection decision boundary |
| `reason_code` | Required for continuity/fallback/empty/pause |
| `semantic_digest` | Full immutable authority digest |
| `created_at_ms` | Commit time |

`brc_selection_authority_current` 以 `selection_spec_id` 为主键，只保存 exact current
`selection_authority_id` 和 optimistic version。只有`PRE_FENCE_CONTINUITY`、`ACTIVE_NEW`、
`NO_CHANGE`、`FALLBACK_PREVIOUS`且Owner/Policy/Vacuum当前允许时，才可能授权new ENTRY。

`PRE_FENCE_CONTINUITY`在每个already-Dynamic Selection Period的`D 01:00`decision boundary由Materializer主动提交，不等待
Selection Job outcome。它只能在以下gates全部成立时提交：

```text
selection_mode == dynamic_selection
AND no Strategy Entry Vacuum has opened for this Session
AND exact current LONG/SHORT pair is operationally valid
AND Owner Strategy Control is ENABLED
AND no terminal current-Session Authority supersedes continuity
```

首条reason=`AWAITING_SELECTION`；Selection失败后可追加更高sequence
`SELECTION_SOURCE_FAILED/SELECTION_COMPUTE_FAILED` reason revision，但失败不是continuity的
创建条件。Snapshot成功且members相同，由`NO_CHANGE`继承continuous grant；Snapshot成功且需要
变化或`VALID_EMPTY`时，continuity持续到Vacuum commit，并在该transaction被negative fence
原子切断。若continuity在`eligibility_not_before_ms`前commit，首个可交易close直接为该时间；
若更晚，必须先完成current pair的Authority Gap Audit，再提交continuity。旧fact保持immutable。

每个trading-authorized Authority必须满足以下二选一约束：

```text
continuity_source_kind in (SELECTION_AUTHORITY, STATIC_BASELINE)
AND authority_gap_audit_id IS NULL
AND predecessor coverage proves no missing eligible close

OR

continuity_source_kind == AUTHORITY_GAP_AUDIT
AND authority_gap_audit_id references COMPLETE exact-scope audit
```

首次Dynamic activation不创建`PRE_FENCE_CONTINUITY`，因此不存在impossible predecessor FK；
其首个`ACTIVE_NEW/NO_CHANGE/VALID_EMPTY`之前由existing `static_baseline` authority继续负责。

该 current pointer 是“本 Selection Session 是否拥有 new-ENTRY authority”的唯一最终投影。
Selection Job 与 Generation 不得再用 `active` 字段表达相同事实；Generation 的 `ACTIVE` 只表示
materialization operation 已成功完成，正式时间有界授权仍由 SelectionSessionAuthority 单独拥有。

### 7.16 `brc_strategy_entry_vacuums_current` and events

Vacuum scope 是 exact StrategyGroup + SelectionSpec，不作用于账户内其他策略：

| Column | Meaning |
| --- | --- |
| `entry_vacuum_id` | Immutable generation/control operation identity |
| `strategy_group_id` / `selection_spec_id` | Scoped authority |
| `session_start_ms` | Target Selection period |
| `source_generation_id` | Nullable for `VALID_EMPTY` or Owner Pause |
| `state` | `OPEN` / `DRAINING_ENTRY` / `RECONFIGURING` / `RESOLVED_ACTIVE` / `RESOLVED_FALLBACK` / `VALID_EMPTY` / `OWNER_PAUSED` / `SUPERSEDED` / `FAILED_CLOSED` |
| `fenced_at_ms` | FinalGate fence start |
| `drained_at_ms` | All pre-fence ENTRY outcomes resolved |
| `resolved_at_ms` | Terminal resolution time |
| `first_blocker` | Stable reason |
| `projection_version` | Optimistic version |

`brc_strategy_entry_vacuum_events` 追加记录 open、pending-command supersede、cancel request、
cancel result、partial retained、unknown outcome、drained、warming、activation、fallback、pause、
supersession 和 terminal outcome。任何 exchange cancel
仍必须先成为 durable Exchange Command，网络 I/O 在 transaction 外。

Vacuum只拥有negative ENTRY fence与drain，不再拥有trigger audit projection。会重新开放new
ENTRY的Vacuum outcome必须引用通用Authority Gap Audit；`VALID_EMPTY`和保持Pause不开放交易，
不要求audit。

### 7.17 `brc_selection_authority_gap_audits_current` and events

该projection证明任意SOR Authority grant之前的**未授权eligible-close区间**，不绑定Vacuum：

| Column | Meaning |
| --- | --- |
| `authority_gap_audit_id` | Deterministic identity for one proposed Authority sequence |
| `selection_spec_id` / `session_start_ms` | Exact Session |
| `gap_kind` | `LATE_PRE_FENCE_CONTINUITY` / `LATE_NO_CHANGE` / `ENTRY_VACUUM` / `OWNER_PAUSE` |
| `source_entry_vacuum_id` | Required for Vacuum/Pause gap；nullable for late pre-fence gap |
| `source_generation_id` | Nullable；exact Desired generation when applicable |
| `proposed_authority_outcome` | Exact grant being prepared |
| `unauthorized_from_close_time_ms` | First eligible close lacking continuous Authority；inclusive |
| `audited_through_close_time_ms` | Last audited closed bar；inclusive |
| `first_eligible_close_time_ms` | First later close the proposed Authority may process |
| `audit_scope_digest` | Canonical instrument-side AuditSet |
| `audit_result_digest` | Canonical positive suppressions + checked-negative results |
| `detector_semantic_digest` | Exact SOR v4 semantics |
| `state` | `PENDING` / `COMPLETE` / `FAILED` |
| `first_blocker` / `projection_version` | Recovery state |

`brc_selection_authority_gap_audit_events`记录start、incremental extension、positive suppression、
checked-negative、complete和failed。Network/market reads在transaction外；结果commit重验exact
Session、pair、generation、Vacuum和Owner identity。`COMPLETE`后scope/result/time字段不可改；若
又闭合eligible bar，创建增量revision或更高sequence audit，不原地篡改完成事实。

AuditSet规则：

| Grant path | Exact AuditSet |
| --- | --- |
| Late `PRE_FENCE_CONTINUITY` | Current previous LONG/SHORT pair |
| Late ordinary `NO_CHANGE` without continuous predecessor | Current pair |
| `ACTIVE_NEW` / `FALLBACK_PREVIOUS` after Vacuum | Previous pair UNION Desired pair |
| Pause Resume same members | Current pair |

如果predecessor Authority或首次切换前Static authority连续覆盖所有eligible closes，则不创建audit。
否则Final Authority transaction必须验证audit=`COMPLETE`、scope/result digest一致，并冻结相同
`first_eligible_close_time_ms`。该时间是`audited_through_close_time_ms`之后的canonical 15m close；
transaction必须在其之前commit。若进入发布保护窗口时不能保证commit在该close前完成，则不更新
Authority pointer，等待下一close、扩展audit并选择后一个first eligible close。

### 7.18 Signal, Claim, Ticket and retained-fill lineage

Dynamic Signal、CapacityClaim、AdmissionDecision 和 Ticket 新增冻结
`selection_authority_id`；Static/manual 历史 lineage 保持 nullable，不伪造旧 Selection fact。
同一动态链的四个对象必须引用同一 Authority，并与 Universe/EventSpec/Instrument 一致。

真空 partial fill 不改写 immutable Ticket quantity。追加 Trade Event 冻结：

```text
entry_vacuum_id
selection_authority_id
requested_qty
final_filled_qty
average_fill_price
quantity_step
effective_tp1_qty
effective_runner_qty
materialization_kind = VACUUM_PARTIAL_RETAINED
```

Aggregate projection保存实际 `position_qty` 和 effective quantity plan；后续 Initial Stop、TP1、
Runner、Exit、Settlement 和 Review 使用该实际计划。原 Ticket/Reservation 仍保留完整计划风险
占用直到 Episode terminal，不因小量成交释放后再补仓。

`VACUUM_PARTIAL_RETAINED` 还必须冻结 `tp1_qty > 0`、`runner_qty > 0` 且两者之和等于
step-aligned actual quantity 的证明。任一腿为零、rounding 后总量不守恒或保护不可提交时，
不得写 retained event，必须沿现有 Incident + controlled flatten 路径收敛。

### 7.19 `brc_strategy_trigger_suppressions`

任意Authority gap中已发生的SOR first natural trigger必须成为不可变runtime fact，避免恢复后
把后续cross当作首次Episode：

| Column | Meaning |
| --- | --- |
| `trigger_suppression_id` | Deterministic immutable identity |
| `authority_gap_audit_id` | Required exact gap proof lineage |
| `entry_vacuum_id` / `materialization_generation_id` | Optional reconfiguration lineage |
| `event_spec_id` / `exchange_instrument_id` | Exact side and member |
| `session_reference` | Exact SOR Session Episode identity |
| `first_natural_trigger_at_ms` | Trigger observed during fenced interval |
| `reason_code` | `TRIGGER_DURING_AUTHORITY_GAP` |
| `detector_semantic_digest` | Exact SOR v4 semantics used for replay |
| `created_at_ms` | Commit time |

Unique `(event_spec_id, exchange_instrument_id, session_reference)`；UPDATE/DELETE forbidden。它
不创建 StrategySignal、ExposureEpisode、Ticket 或 Shadow Outcome，只告诉 Observation：该
Session 的 first-trigger opportunity 已被 fenced period 消耗。若 lower-bound facts不足以证明
是否发生 Trigger，保持该 scope fail-closed并记录 blocker，不能假定“未触发”。

Audit从`unauthorized_from_close_time_ms`覆盖到`audited_through_close_time_ms`，对7.17定义的
AuditSet每个instrument-side/session运行exact SOR v4 first-trigger语义。Positive result插入
suppression；全部positive/negative result进入`audit_result_digest`。Final Authority transaction
必须验证：

```text
gap_audit.state == COMPLETE
AND stored scope digest == recomputed exact grant scope digest
AND gap_audit.first_eligible_close_time_ms == Authority.first_eligible_close_time_ms
AND gap_audit.audited_through_close_time_ms < Authority.first_eligible_close_time_ms
```

Observation还必须验证`close_time_ms >= first_eligible_close_time_ms`。因此无论gap来自Session
rollover、late NO_CHANGE、Vacuum还是Pause，都不存在Authority commit与audit之间抢跑second
cross的窗口。

### 7.20 `brc_runtime_release_compatibility_facts`

Deployment Plane必须把release classification记录为**现有Release Certification manifest的薄
immutable projection**，而不是依赖发布脚本内存或Markdown：

| Column | Meaning |
| --- | --- |
| `release_compatibility_id` | Immutable identity |
| `from_commit` / `to_commit` | Exact code identities |
| `from_schema_revision` / `to_schema_revision` | Exact Schema identities |
| `classification` | `COMPATIBLE_RESTART` / `REQUIRES_RUNTIME_REMATERIALIZATION` |
| `compatibility_basis_digest` | Canonical digest of existing manifest identities used by the decision |
| `reason_codes` | Bounded frozen vocabulary；no independent rules engine |
| `certification_manifest_digest` | Frozen release evidence identity |
| `created_at_ms` | Commit time |

该fact复用现有manifest中的commit、Schema、StrategyVersion、EventSpec/Detector、required
facts、warm contract和RuntimeScope identities，只保存分类结果与证据digest。它不新增release
engine、classifier framework、deployment orchestrator或第二套manifest。该fact也不拥有
Universe、Vacuum或Selection Authority；若分类要求rematerialization，正式release fence仍由
Runtime authority创建并由Materialization Coordinator解析，Migration不得代替它产生业务副作用。

## 8. Selection-to-Ticket Trace

本轮不在 Signal、CapacityClaim 和 Ticket 复制 Selection Feature，只传播一个不可变
`selection_authority_id`。稳定链路是：

```text
Ticket.selection_authority_id
-> SelectionSessionAuthority
   -> Snapshot outcome:
      authorized Universe pair / materialization generation
      -> SelectionSnapshot
      -> MemberDecision(snapshot_id, ticket.exchange_instrument_id)

   -> PRE_FENCE_CONTINUITY:
      authorized continued pair
      -> continued_from_selection_authority_id
      -> optional Selection Job/attempt or Snapshot reason provenance
      -> prior Dynamic Snapshot/Generation lineage
```

Signal、Claim、Ticket 同时冻结 Universe ID/digest和Selection authority，因此该 FK 链能够
永久回答：

- 使用哪个 SelectionSpec；
- 本Session是Snapshot decision还是pre-fence continuity；
- Snapshot outcome下当天哪个Snapshot、Instrument rank、Feature和Selected原因；
- continuity outcome下是在等待Selection、记录失败还是等待Materialization，以及从哪个Authority延续；
- LONG/SHORT 使用哪个 Universe version。
- 本次是 `ACTIVE_NEW`、`NO_CHANGE`、`PRE_FENCE_CONTINUITY` 还是
  `FALLBACK_PREVIOUS`；
- 该 Ticket 是否来自真空 partial-retained materialization。

不复制 Feature 字段可以避免 Selection 口径漂移；复制 Authority identity 是解决
`NO_CHANGE`/continuity/`FALLBACK_PREVIOUS` 无法从Universe version反推本Session授权事实的
必要lineage。早于Snapshot的Continuity Ticket没有当天MemberDecision，禁止伪造Snapshot或Rank。

## 9. Runtime Ownership

### 9.1 Selection Runner

Selection Runner 只拥有 Selection Plane：

```text
claim Selection Job lease
-> fetch exact public data outside transaction
-> validate full-panel source integrity
-> run pure SelectionCore
-> commit Snapshot + 24 decisions + SNAPSHOT_READY
   or SOURCE_FAILED / COMPUTE_FAILED
-> release/expire Selection lease
-> END
```

它不得读取 current Universe/Authority/Vacuum，不得创建 Generation，不得调用 Materializer。
`SNAPSHOT_READY` 后，即使托管进程继续运行，也必须通过新的 DB claim 才能进入其他组件。

### 9.2 Materialization Coordinator

Materialization Coordinator 是独立应用组件，使用独立 lease namespace 和 transaction boundary：

```text
open current Selection Period continuity from exact current pair
-> observe latest Selection Job/Snapshot reason handoff
-> read current runtime authority
-> resolve PRE_FENCE_CONTINUITY / VALID_EMPTY / NO_CHANGE / DESIRED
-> own Generation + Vacuum + drain + warming + staging
-> prove continuous eligible closes or complete Authority Gap Audit before any grant
-> atomic activation or gated post-fence fallback
-> commit final SelectionSessionAuthority
-> END
```

它必须能在 Selection Runner 不存在、已经退出或已经崩溃时，仅从 PostgreSQL current/event
facts 完成恢复。任何跨 tick 进度都写入 Generation/Vacuum/Authority，禁止保存在内存 coroutine
或 Selection Runner call stack。

### 9.3 Observation Runner

Observation Runner 继续只拥有正式策略观察：

```text
claim due RuntimeScope
-> load exact current Universe + SelectionSessionAuthority + Vacuum
-> observe one bounded scope
-> persist cursor / StrategySignal
-> END
```

它不负责 Selection schedule，也不推进 Materialization。Dynamic scope 只有在 exact Active
Universe、有效 SelectionSessionAuthority 和无 open Vacuum 时才可产生 Signal。

### 9.4 Entry, Reconciliation And Lifecycle Workers

Entry Worker 继续拥有唯一 new-ENTRY dispatch。它必须在 Ticket issuance 和每次 ENTRY/
SET_LEVERAGE dispatch preflight 读取 exact current SelectionAuthority + EntryVacuum version。
Vacuum 已打开时：

- prepared/claimed but not dispatched command terminally supersede；
- venue 已存在 ENTRY order 时不盲目重发，转入 durable cancel/drain；
- `outcome_unknown` 保持未知并交给 Reconciliation；
- Stop/TP1/Runner/Exit/controlled-flatten command 不受 Vacuum 阻断。

Reconciliation Worker 不对 24-member Candidate Panel 建立常驻 certification lease。只有
Materializer 已经创建 Desired LONG/SHORT Universe 后，才按现有方式处理：

```text
active StrategyUniverse members
UNION
the one current warming StrategyUniverse
UNION
staged members of the current materialization generation
```

它还负责解析 Vacuum 前已 dispatch 的 ENTRY、确认 exact remainder cancellation、冻结 final
filled quantity，并把 `outcome_unknown` 解析为 absent/open/partial/full。Lifecycle Worker 继续
执行实际仓位的 Initial Stop、TP1、Runner 和 Exit；Selection membership 变化不停止已有 Ticket。

### 9.5 Process Hosting And Worker Count

V0 必须实现三个独立 application entry point、三个 DB lease namespace 和三组 bounded tick：

| Logical component | Allowed V0 host | Forbidden coupling |
| --- | --- | --- |
| Selection Runner | Existing Observation process or later dedicated service | Direct call to Materializer after Snapshot commit |
| Materialization Coordinator | Existing Observation/Reconciliation process or later dedicated service | Depend on Selection in-memory result |
| Observation Runner | Existing Observation systemd service | Advance Selection Job/Generation in observation call stack |

因此本设计**不强制第五个 systemd Worker**，但也不再声明三类工作“使用同一个 Worker
identity”。如果共用 OS process，仍必须是独立 loop/entry point、独立 lease owner identity、
独立 timeout 和独立 crash recovery。禁止 timer-based cold start、Research Worker、per-strategy
process 或 repository-external scheduler。

## 10. Exact Runtime Sequence

### 10.1 Selection Sequence

Candidate Panel 只提供 canonical public-market discovery scope。Candidate 不需要进入
StrategyUniverse，也不因为出现在 Panel 获得 Product、Signal 或 ENTRY 权限。

在 `D 01:00` 后，Selection Runner 独立执行：

1. exact-key 创建/锁定 `(selection_spec_id, session_start_ms)` Selection Job；
2. 验证 SelectionSpec、clock 和 Selection control允许计算；不读取或冻结 current Universe；
3. 领取 Selection lease并 commit；
4. transaction 外读取 Binance official USDⓈ-M Kline response，保留
   `quote_asset_volume`；24 Instrument × exact 96 closed 15m bars，bounded concurrency默认6；
5. 先验证 full-panel source integrity；任一 Candidate 缺 Kline、窗口不完整、open/future bar、
   response partial或 source digest矛盾，整个 attempt=`SOURCE_FAILED`，不运行 Rank、不提交
   Snapshot、不 Rank补位；
6. source完整后运行纯 `SelectionCore`，输出 Snapshot candidate + exact 24 decisions；Product/
   Activity/geometry不合格可成为正常 member `INELIGIBLE`；
7. 一个短 transaction重锁Job/lease/spec，验证cardinality/digest，原子insert Snapshot + exact
   24 decisions，更新 Job=`SNAPSHOT_READY`，append attempt并commit；
8. source/compute失败则只提交Job=`SOURCE_FAILED/COMPUTE_FAILED`与append-only attempt；
9. Selection Runner 结束。它不判断 continuity、`VALID_EMPTY/NO_CHANGE/DESIRED`。

所有网络 I/O 在 PostgreSQL transaction 外。SelectionCore 不读 DB、网络、文件、Ticket、
Position、Outcome、Owner pause 或 current Universe。

### 10.2 Runtime Materialization Handoff And Claim

Materialization Coordinator用独立lease处理三个durable阶段。

**A. Selection-Period pre-fence continuity**：

1. 在exact `D 01:00`Selection decision boundary后claim“current Selection Period尚无Authority”工作，
   不等待Selection完成；`session_start_ms`仍保存`D 00:00` Episode identity；
2. 锁定Strategy Control、Selection control、prior/current Authority、current LONG/SHORT pointers
   和open Vacuum projection；
3. 验证`selection_mode=dynamic_selection`、Owner Enabled、current pair operationally valid、
   本Session未打开Vacuum；
4. 计算SOR `eligibility_not_before_ms`和canonical `first_eligible_close_time_ms`；若当前时间已造成
   eligible-close gap，先按10.7完成current pair Gap Audit；
5. insert `SelectionSessionAuthority(PRE_FENCE_CONTINUITY, reason=AWAITING_SELECTION)`，引用
   prior Dynamic Authority和exact current pair，`expires_at_ms=D+1 01:00`；
6. 原子替换Authority current pointer；不创建Snapshot、Generation、Vacuum或cancel；commit。

Selection失败时Materializer可追加同outcome更高sequence reason revision，引用exact failed
Job/attempt；Selection成功并进入PENDING/DESIRED时可追加`AWAITING_MATERIALIZATION` revision并
引用Snapshot。上述revision都继承continuous eligible-close proof，不重新打开或关闭交易。

**B. First pending Dynamic activation special case**：

若current mode仍为`static_baseline`且`pending_selection_mode=dynamic_selection`，跳过A。existing
Static pair和Static new-ENTRY authority持续有效，直到首个Dynamic terminal outcome transaction。
Selection失败或pre-fence materializer失败不创建Dynamic continuity，也不改变Static mode。

**C. Committed Snapshot disposition**：

1. claim latest unresolved `SNAPSHOT_READY`，锁定Snapshot、Strategy Control、Selection control、
   current Authority/current LONG/SHORT pointers和Vacuum；
2. 拒绝stale/expired Snapshot；
3. Owner pause时提交`OWNER_PAUSED_NOT_MATERIALIZED` Authority，不创建Generation、不fallback；
4. `selected_count=0`时进入`VALID_EMPTY`；
5. selected set与current pair完全相同、pair operationally valid且**没有open Vacuum**时提交普通
   `NO_CHANGE` Authority；
6. selected set相同但存在`OWNER_PAUSED` Vacuum时进入10.10 Resume-NO_CHANGE流程；
7. 非空且变化时原子创建Generation=`PENDING`，冻结previous pair与Desired targets；
8. commit durable PENDING handoff；下一Materializer tick重验current pair后提交`DESIRED`；再
   下一tick才允许打开Vacuum。

普通`NO_CHANGE`仍产生当天新的SelectionSessionAuthority，但不创建Universe、Vacuum或
Generation。already-Dynamic路径通常从`PRE_FENCE_CONTINUITY`连续继承，不需要audit；若continuity
缺失或晚于eligible close，必须先完成current pair Authority Gap Audit。首次pending Dynamic路径
从Static authority连续继承。所有pre-fence runtime facts必须显式表达，绝不能依赖expired
Authority或写`FALLBACK_PREVIOUS`。

`PENDING -> DESIRED` 是另一个无网络I/O的短transaction：重锁Snapshot、Generation、controls
和current pair，验证Snapshot仍latest、Owner未Pause、previous pair未漂移后提交。失败只会
使Generation进入`ABANDONED`并保持previous pointers不变；这本身不隐含新Session交易授权，
也不产生fallback。Materializer必须按exact durable state重试或等待更高优先级Snapshot/
Owner outcome。already-Dynamic Session的`PRE_FENCE_CONTINUITY`持续有效；首次pending Dynamic的
Static authority持续有效。`DESIRED`直到10.3 Vacuum commit才撤销旧new-ENTRY authority。

### 10.3 Open Strategy Entry Vacuum

需要 `VALID_EMPTY` 或新 Desired generation 时，一个 transaction：

1. 重锁Snapshot、control、current Authority/current pair和Generation（如有）；
2. 要求Generation已经durable `DESIRED`，并验证current pair仍等于其冻结的previous pair；若
   漂移则pre-fence `ABANDONED`，不fallback、不fence；
3. insert/update exact Strategy Entry Vacuum=`OPEN/DRAINING_ENTRY`；
4. Generation `DESIRED -> DRAINING_ENTRY`；
5. 原子撤销该StrategyGroup的new Admission/Ticket/ENTRY-dispatch authority；
   `PRE_FENCE_CONTINUITY`或Static authority从该commit起被Vacuum覆盖；
6. commit。

禁止在Snapshot和Desired set确定前提前fence。该commit后旧Universe rows/pointers仍保留，但
旧、新Universe都没有new ENTRY authority；既有Position lifecycle继续。

### 10.4 Drain Unfinished ENTRY

Vacuum 只处理 fence 前已经存在的 ENTRY lineage：

| ENTRY state at/after fence | Required action |
| --- | --- |
| Signal exists, no Ticket | Admission records terminal `selection_entry_vacuum` blocker；no Ticket |
| Ticket + prepared command, no venue dispatch | Command terminally superseded；release Reservation/Domain/ENTRY lane through official reducer |
| Command claimed, preflight not passed | Re-read Vacuum；terminal supersede before network I/O |
| Venue ENTRY open, zero fill | Persist `CANCEL_ORDER(selection_vacuum_entry)`；dispatch outside transaction；confirm absence before terminal closure |
| Venue ENTRY fully filled | Treat as existing Position；protect and continue lifecycle |
| Venue ENTRY partially filled | Persist exact remainder cancel；after cancel/absence and final position read, freeze actual quantity plan and protect retained fill |
| ENTRY `outcome_unknown` or dispatch already in flight | Reconciliation resolves external truth；never blind resend；Vacuum remains `DRAINING_ENTRY` |

只有以下条件全部成立，Vacuum 才能写 `ENTRY_DRAINED`：

1. 没有该 StrategyGroup 的 prepared/claimed/in-flight ENTRY command；
2. 没有未解析 `outcome_unknown`；
3. 没有仍在 Venue open 的 ENTRY order；
4. 每个实际 fill 已进入 Initial Stop/保护链；
5. global ENTRY lane state与Ticket aggregate一致。

若 Snapshot `selected_count=0`，drain完成后的同一 transaction 插入
`SelectionSessionAuthority(VALID_EMPTY)`、更新 current Authority并把Vacuum终结为
`VALID_EMPTY`；不创建Generation、不warming、不fallback。

`VALID_EMPTY`从该Vacuum/Authority transaction commit起向前生效，不追溯撤销此前合法
`PRE_FENCE_CONTINUITY`下的Signal、AdmissionDecision、Ticket或成交事实。commit时仍未完成的
ENTRY继续按本节drain/cancel；已经形成实际Position或已进入保护链的Ticket继续Initial Stop、
TP1、Runner、Exit、Reconciliation、Settlement和Review，不因后续`VALID_EMPTY`被平仓或重分类。

### 10.5 Vacuum Partial Fill Retained Branch

只有 Ticket 已写入 exact `entry_vacuum_id` drain intent，才可进入该分支：

```text
observe partial fill
-> durable cancel exact remainder
-> reconcile cancel/absence and final filled quantity
-> freeze VACUUM_PARTIAL_RETAINED materialization event
-> assess actual stop risk using frozen Ticket stop
-> durable Initial Stop for exact actual quantity
-> derive positive TP1 + positive Runner quantities from the same frozen ExitPolicy fraction
-> continue protected lifecycle
```

数量派生使用 current certified `quantity_step`。只有标准 split 能形成两个 positive legs，且
`tp1_qty + runner_qty == final_filled_qty` 时才保留 actual TP1 + actual Runner。实际数量只允许
一个 step、任一腿round为零、保护方向错误、actual stop risk超过Ticket hard limit、无法提交
reduce-only protection或external quantity矛盾时，均执行Incident + controlled flatten。
`runner_only_partial` 被明确删除；Owner 的“保留部分成交”不绕过已有硬安全边界。

### 10.6 Serial LONG Then SHORT Warming

Vacuum `ENTRY_DRAINED` 后才开始 warming：

1. 通过现有 global queue 安装 LONG Desired Universe；
2. 创建Universe row时原子写LONG `materialization_generation_id`和member rows；
3. 从 exact cutoff input 构建 typed `MarketSnapshot`并完成正式 certification；
4. ready 后 `warming -> staged`，释放 global warming slot；
5. 对SHORT重复Universe creation、Generation FK、certification和staging；
6. 两个staged Universes必须引用同一generation，member digest必须等于Snapshot Selected digest。

任一方向失败、timeout或被新 Snapshot supersede，都不得让单侧获得 Active authority。

### 10.7 Pre-Authority Eligible-Close Proof

任何会授予new ENTRY的outcome，在Authority commit前必须先判断eligible-close authority是否连续：

```text
if predecessor/static authority covers every eligible close:
    proof = CONTINUOUS_ELIGIBLE_CLOSES
    no audit
else:
    AuditWindow = [first unauthorized eligible close,
                   close immediately before first_eligible_close_time_ms]

    for each exact grant AuditSet scope:
        replay exact SOR v4 first-natural-trigger semantics
        positive -> immutable trigger suppression
        negative -> include checked-negative result in audit digest

    commit AuthorityGapAudit=COMPLETE
    + scope/result digest
    + first_eligible_close_time_ms
```

Grant与scope：

| Outcome | Audit requirement/scope |
| --- | --- |
| On-time `PRE_FENCE_CONTINUITY` before first eligible close | Continuous proof；no audit |
| Late `PRE_FENCE_CONTINUITY` | Previous/current pair |
| Ordinary `NO_CHANGE` after continuous pre-fence authority | Continuous proof；no audit |
| Late `NO_CHANGE` without continuity | Current pair |
| `ACTIVE_NEW` / `FALLBACK_PREVIOUS` after Vacuum | Previous pair UNION Desired pair |
| Owner Pause → Resume `NO_CHANGE` | Current pair |

Vacuum路径对union全集执行，避免提前猜测最终使用新pair还是fallback旧pair。Audit source读取在
transaction外；结果commit是短transaction并验证Authority predecessor、Vacuum、Generation、
Owner identity未漂移。任一scope缺facts或Detector digest不一致时写`FAILED`并保持无授权状态。

### 10.8 Final Atomic Activation Transaction

一个短 PostgreSQL transaction：

1. 锁定 global Universe install authority；
2. 锁定 Session、Control、Snapshot、Generation、Vacuum和24 decisions；
3. 锁定 previous pair pointers和两个 staged targets；
4. 验证 Owner Enabled、Vacuum已drained、exact members/certification/Registry/Runtime identity；
5. 重算union AuditSet并验证Authority Gap Audit=`COMPLETE`、scope/result digest一致，且
   `audited_through_close_time_ms`是`first_eligible_close_time_ms`前一canonical close；
6. 同时 retire previous LONG/SHORT Universes/scopes；
7. 同时 activate target LONG/SHORT Universes/scopes并更新两个 current pointers；
8. insert immutable `SelectionSessionAuthority(ACTIVE_NEW)`，冻结Gap Audit和
   `first_eligible_close_time_ms`；transaction必须在该close前commit，Observation只处理该close
   及之后的bar；
9. 更新 Authority current pointer、Generation/Vacuum terminal projection；
10. commit。

任何一步失败全部 rollback。外部永远看不到“LONG 新、SHORT 旧”或 pointer 已切但 Authority
尚未建立的状态。

### 10.9 Keep-Previous Versus Explicit FALLBACK_PREVIOUS

失败语义以 Vacuum commit 为硬边界：

| Failure point | Outcome |
| --- | --- |
| Before Vacuum commit, Selection pending/success/failure | `PRE_FENCE_CONTINUITY` remains authoritative；never record fallback |
| Before Vacuum commit, transient materializer conflict | Retry without changing continuity/Static authority；never record fallback |
| After Vacuum commit | Remain no-trade until drain/reconciliation；then fallback only if all gates pass |

Vacuum 后 warming、certification或restart recovery失败时，只有同时满足下列条件才允许
fallback：

```text
Owner Strategy Control == ENABLED
AND previous LONG/SHORT pair exact and operationally valid
AND Vacuum ENTRY drain complete
AND Authority Gap Audit(previous UNION desired) == COMPLETE and exact
AND no newer valid Snapshot supersedes this generation
```

fix-forward transaction abandon new warming/staged targets，保持previous pointers/lifecycle，重验
Gap Audit COMPLETE/exact，insert `SelectionSessionAuthority(FALLBACK_PREVIOUS)`并冻结
`first_eligible_close_time_ms`，更新current Authority并解析Vacuum。若transaction未能在该close
前commit，则rollback、扩展audit并选择后一close。
`VALID_EMPTY`、Owner Pause、unresolved ENTRY outcome、invalid previous pair 都禁止 fallback；
此时保持 no-trade并记录 `FAILED_CLOSED` 或对应非交易结果。

**首次Static-to-Dynamic post-fence失败不新增Authority outcome。**它复用同一
`FALLBACK_PREVIOUS`，但transaction必须同时满足：

```text
continuity_source_kind = STATIC_BASELINE
authorized pair = exact pre-fence Static LONG/SHORT pair
selection_snapshot_id = exact first-attempt Snapshot
materialization_generation_id = exact failed first-attempt Generation
authority_gap_audit_id = COMPLETE exact union audit
selection_mode remains static_baseline
pending_selection_mode = NULL after terminal fallback commit
pending_effective_session_start_ms = NULL
pending_authorization_id = NULL
```

这条transition-scoped Authority只恢复本Selection Period剩余时间的Static new-ENTRY资格并冻结
Gap Audit、trigger suppression与`first_eligible_close_time_ms`；它不是首个Dynamic activation成功
事实。Static Observation在该Authority到期前必须验证exact pair、first eligible close、suppression、
Owner/Policy与Vacuum；下一decision boundary后回到正常Static baseline authority。不得只resolve
Vacuum后依赖旧Static pointer，也不新增`FIRST_ACTIVATION_FALLBACK_STATIC`第二状态。

### 10.10 Owner Pause, Resume And Supersession

Owner Pause：立即保持/打开 ENTRY Vacuum，abandon 当前 generation，不 activation、不 fallback，
继续 drain pending ENTRY、解析 unknown outcome和保护已成交仓位；Selection Runner仍按周期
计算Snapshot，`OWNER_PAUSED_NOT_MATERIALIZED` 只能由Materialization Coordinator写入。
Resume 只读取当前有效周期最新合法 Snapshot：

- non-empty且members变化：复用现有Pause Vacuum/drain，创建Desired Generation并继续warming；
- non-empty且members等于current pair：**不得走普通NO_CHANGE fast path**；先确认Pause Vacuum
  ENTRY_DRAINED，执行10.7 pause-window Gap Audit（current pair），再原子resolve
  Vacuum并提交更高sequence `NO_CHANGE` Authority；不warming；
- `selected_count=0`：保持无交易；
- 无当前合法 Snapshot：保持 disabled。

Resume-NO_CHANGE transaction必须同时验证exact Owner Resume authorization、Gap Audit
COMPLETE/exact、current pair operationally valid，并冻结`first_eligible_close_time_ms`；如果不能
在该close前commit则重试后一close。Pause前Authority永不重新启用。

更新 Snapshot 在旧 Desired 尚未 Active 时到达：旧 generation写 `SUPERSEDED`，warming/staged
targets被abandon，Vacuum保持打开，latest-valid-selection从10.2继续。不能短暂 fallback旧 pair
再开始新一轮切换。

### 10.11 Crash Recovery

Crash recovery 使用 exact Session/Generation/Vacuum/Authority state：

| Last durable state | Recovery |
| --- | --- |
| Selection decision boundary passed, no continuity Authority | Commit on-time continuity or audit late gap before grant |
| Snapshot committed, no Vacuum | Materializer reacquires its lease；re-evaluate 10.2 branch |
| Vacuum open / ENTRY draining | Resume exact command reconciliation/cancel；no warming |
| ENTRY drained, no target | Continue latest valid Desired or resolve VALID_EMPTY |
| LONG staged / SHORT warming | Resume exact latest generation；failure falls back only if 10.9 gates pass |
| Both staged, gap audit pending/failed | Complete/retry exact union audit；no Authority |
| Gap Audit COMPLETE, no Authority | Verify first eligible close remains future；otherwise extend audit and select later close |
| Owner paused | Abandon materialization；continue drain only；never fallback |
| SUPERSEDED | Never activate old targets；continue newest valid Snapshot |
| PRE_FENCE_CONTINUITY/ACTIVE_NEW/NO_CHANGE/FALLBACK_PREVIOUS/VALID_EMPTY committed | Idempotent read；never duplicate Authority |

Selector 已退出、Selection host process重启或Deployment已完成，都不改变上述恢复入口；
Materializer只依赖 durable PostgreSQL事实。

### 10.12 Authority-Gap First-Natural-Trigger Suppression

仅把observation cursor设为Authority action time不足以保护SOR语义。任何未授权eligible-close gap
内发生的first natural trigger，都会使恢复后的后续cross可能被错误当作first trigger。
Materializer必须在Authority前持久化bounded Gap Audit/suppression facts：

```text
for each instrument-side in exact grant AuditSet
inspect every unauthorized eligible close before first_eligible_close_time_ms
if first natural trigger occurred during the gap:
    mark session_reference trigger_consumed_while_unauthorized
    advance cursor beyond that episode
    prohibit later cross from becoming first trigger
```

该检查复用正式SOR v4 Detector语义和point-in-time facts，不产生Signal、不创建Ticket。
Observation不负责补audit，只消费Authority冻结的grant proof、first eligible close和suppression。
`trigger_consumed_while_unauthorized`的Instrument/side在该Session不得再产生首个Episode。系统不
回扫补单、不追单，也不悄悄加入Re-entry语义。

## 11. Timing Contract

| Boundary | Contract |
| --- | --- |
| SOR Session identity | `session_start_ms = D 00:00`；only Episode/session identity |
| Selection/Authority Period start | `selection_decision_boundary_ms = D 01:00` |
| Earliest job start | `D 01:00:00 UTC` after four OR bars are closed |
| Normal target | Snapshot + Vacuum drain + materialization resolved by **01:14** |
| Correctness boundary | No ENTRY while Vacuum unresolved；not “must activate before 01:15” |
| Per-generation wall clock | **1800 seconds** from Vacuum open，excluding unresolved exchange outcome |
| Earliest Signal | Exact `Authority.first_eligible_close_time_ms`；Observation uses `close_time_ms >=` |
| Late activation | Allowed within current validity window；no downtime backfill or chase |
| Validity end | Next Selection decision boundary (`D+1 01:00`) |
| Pre-fence interval | `PRE_FENCE_CONTINUITY` covers already-Dynamic current pair until Vacuum；Selection result does not stop it |
| Late grant | Audit every unauthorized eligible close；freeze later `first_eligible_close_time_ms` |

**01:14 现在是运行 SLO，不是 correctness hard stop**。例如01:18完成Gap Audit和Authority，
系统冻结下一canonical eligible close，不以01:18毫秒时间作为bar边界。超过30分钟materialization timeout时，
可在10.9 gates满足后 fallback；若 exchange outcome仍未知，则保持 fail-closed，timeout不能把
未知事实变成可恢复旧交易权限。

## 12. Selection-Before-Signal Enforcement

### 12.1 Dynamic Selection-Period gate

现有 Universe current pointer 需要增加一个 bounded validation：

```text
current selection control mode == dynamic_selection
AND exact current SelectionSessionAuthority exists
AND now in [effective_from_ms, expires_at_ms)
AND observed close_time_ms >= Authority.first_eligible_close_time_ms
AND no open Strategy Entry Vacuum
AND (
      Authority.outcome == ACTIVE_NEW
      AND current Universe belongs to the exact generation
      AND MemberDecision.state == SELECTED
      AND Authority freezes continuous-close proof or exact COMPLETE Gap Audit
    OR
      Authority.outcome == NO_CHANGE
      AND current Universe IDs equal the authorized pair
      AND Authority freezes continuous-close proof or exact COMPLETE Gap Audit
    OR
      Authority.outcome == PRE_FENCE_CONTINUITY
      AND current Universe IDs equal the authorized continued pair
      AND no Vacuum was opened for this Session
      AND Authority freezes continuous-close proof or exact COMPLETE Gap Audit
    OR
      Authority.outcome == FALLBACK_PREVIOUS
      AND current Universe IDs equal the authorized previous pair
      AND Authority freezes exact COMPLETE Gap Audit
    )
AND no matching trigger_suppression for EventSpec + Instrument + session_reference
```

该验证至少同时存在于：

1. Observation 产生 Signal 前；
2. Signal ingestion current-authority revalidation；
3. Admission/Ticket issuance；
4. ENTRY command dispatch preflight。

Selection Job=`CLAIMED/SNAPSHOT_READY`、Generation=`DESIRED/DRAINING_ENTRY/MATERIALIZING/STAGED`、
`VALID_EMPTY`、`OWNER_PAUSED_NOT_MATERIALIZED`或unresolved failure都不能**单独**产生new ENTRY；
只有上述完整Dynamic Selection-Period gate通过才有授权。
`FALLBACK_PREVIOUS` 只有在显式 Authority transaction commit 后才恢复旧成员资格，不能把
“current pointer 仍是旧值”本身当成 fallback authority。

因此Selection source/compute outcome不会控制previous pair是否继续：already-Dynamic Session在
Selection开始前已有`PRE_FENCE_CONTINUITY`。若continuity迟到，必须先audit gap并从冻结的
`first_eligible_close_time_ms`开始，不能回溯补发。Snapshot outcome可原子替换continuity；
`NO_CHANGE`继承连续证明，Vacuum路径重新建立Gap Audit证明。

### 12.2 Unselected Instrument

`ACTIVE_NEW` outcome 下，Unselected Instrument 不属于新的 Active Universe，因此没有新的
Active RuntimeScope。`NO_CHANGE/PRE_FENCE_CONTINUITY/FALLBACK_PREVIOUS` 下，只允许
Authority冻结的pair成员；Candidate Panel 或 MemberDecision 本身永远不授予 Signal authority。

### 12.3 Owner pause and Policy

Selection session gate 通过后，现有 Owner Strategy Control 和 Policy 仍继续生效：

```text
Selection eligible
does not imply
Owner enabled / Policy enabled / Capacity available / Netting free
```

Admission 不新增 Selection filter。

Owner Pause transaction 还必须打开/保持 Strategy Entry Vacuum并触发 unfinished ENTRY drain，
避免已经 accepted/open 的 ENTRY order 在暂停后继续成交。它不撤销已有保护单或退出单。

### 12.4 Static and disabled modes

`static_baseline` 不要求每日 Selection Session，但 exact current LONG/SHORT pair 必须匹配：

1. Migration 时冻结的原 Active baseline；或
2. 后续 Owner rollback 成功 materialize 的 exact Static generation。

首次Dynamic activation在Vacuum后失败时，Static路径还必须在transition-scoped
`FALLBACK_PREVIOUS`到期前验证：`continuity_source_kind=STATIC_BASELINE`、exact Static pair、
COMPLETE Gap Audit、`close_time_ms >= first_eligible_close_time_ms`、无trigger suppression且无open
Vacuum。该Authority只约束失败当期恢复边界，不把`selection_mode`改成`dynamic_selection`。

`disabled` 对 Crypto SOR new Signal fail closed。无论Dynamic ACTIVE、NO_CHANGE、
`PRE_FENCE_CONTINUITY`或`FALLBACK_PREVIOUS`，现有Owner Strategy Control pause和Global
Entry policy始终具有更高优先级；continuity/fallback绝不能恢复被Owner pause的ENTRY authority。

## 13. Existing Signal, Ticket And Position Semantics

### 13.1 Existing Signal

Selection activation不得删除或修改已持久化 Signal，但 Vacuum 打开后，尚未取得 final
ENTRY authority 的 Signal必须形成 terminal Admission blocker `selection_entry_vacuum`，不能
继续成为 Ticket。Crypto SOR Signal freshness 为一个15m window，前一 Session 的 Signal 在
下一日 `01:00` selection boundary 前已经失效；本设计不增加跨 Session Signal carry。

若未来其他 selector 可能在 Signal 有效期内切换，必须单独设计 Signal handoff，不把本 V0
的日边界语义泛化。

### 13.2 Ticket before ENTRY dispatch

Vacuum commit 后，prepared/claimed but undispatched ENTRY terminal supersede并通过正式 reducer
释放 Reservation/Domain/ENTRY lane。已 dispatch 或 `outcome_unknown` 不能直接 supersede；
必须由 Reconciliation 解析外部事实并按10.4 drain。Universe activation不再被动等待一条
可能继续成交的旧 ENTRY，而是先主动完成有界 drain。

### 13.3 Accepted ENTRY and protected lifecycle

ENTRY 已 accepted 后，Universe replacement 可以发生；既有 Ticket、Position、Protection、
TP1、Runner、Exit、Reconciliation、Settlement 和 Review 全部继续使用冻结 Ticket authority。

若 accepted ENTRY 在 Vacuum drain 中最终为 partial fill，实际仓位使用 immutable retained-fill
materialization plan；它仍属于原 Ticket/Exposure Episode，不创建第二 Ticket、不补足 planned
quantity、不释放空间后加仓。

第二天 Instrument 不再 Selected 时，禁止：

- cancel Ticket；
- flatten Position；
- 修改 Stop；
- 停止 Runner；
- 释放未终结 ownership；
- 改写 Settlement/Review。

上述“不得 flatten”不覆盖现有硬安全异常：保护方向错误、hard stop-risk overrun、无法保护、
external quantity矛盾仍执行 controlled flatten。Selection本身不能因为标的被移除而平仓。

Selection 只控制新的 SOR Signal eligibility。

## 14. Failure Semantics

| Failure | Production outcome | Incident / monitor |
| --- | --- | --- |
| Same Selection Job, same digest duplicate | Idempotent return existing Snapshot | No Incident |
| Same identity, different digest | Reject conflict；never overwrite | Open identity-drift Incident |
| Any Candidate Kline gap/window/source-integrity failure | Whole attempt `SOURCE_FAILED`；no Snapshot/Rank；existing `PRE_FENCE_CONTINUITY` remains and may receive failure reason revision | Incident on repeated/budget exhaustion；never fallback |
| Product/Activity/geometry ineligible, Ready 1..7 | Select exact Ready count；no substitution | Expected member reasons |
| Ready = 0 | Snapshot `selected_count=0`；Materializer commits Authority `VALID_EMPTY` after required drain；no new ENTRY | Expected business result；never fallback |
| Selected set exactly current, no open Vacuum | Authority `NO_CHANGE`；no Vacuum/warming/cancel | Expected fast path |
| Resume with same members and OWNER_PAUSED Vacuum | Drain + current-pair Gap Audit + resolve Vacuum + new `NO_CHANGE` revision；no warming | Required resume path |
| Selected member certification stale/unsafe | No substitution；bounded retry；then gated FALLBACK_PREVIOUS | Blocker；Incident if systemic/repeated |
| PG unavailable before Session continuity commit | No durable Dynamic Authority；bounded retry；audit any later eligible-close gap | Cannot invent continuity；monitor until DB returns |
| Binance transport/source outage | Commit SOURCE_FAILED；do not convert outage to INELIGIBLE | Existing Session continuity remains；never call this fallback |
| Materializer failure before continuity/Vacuum commit | Previous committed continuity or first-activation Static authority remains | Retry exact handoff；never `FALLBACK_PREVIOUS` |
| Prepared ENTRY at Vacuum | Terminal supersede and official resource release | Expected drain event |
| Venue ENTRY open, zero fill | Durable exact cancel then confirm absence | Incident on reject/unknown beyond retry |
| Vacuum-attributed partial fill with valid TP1+Runner split | Cancel remainder；freeze actual plan；protect retained fill | Temporary Incident until cancel + protection complete |
| Vacuum-attributed partial fill without valid TP1+Runner split | Cancel remainder；controlled flatten actual fill | Hard safety outcome；no runner-only branch |
| Ordinary/unattributed partial fill | Existing cancel + controlled flatten | Existing hard Incident |
| ENTRY cancel outcome unknown | Keep Vacuum and reconcile external truth | Hard blocker；no fallback/activation |
| Authority Gap Audit incomplete/failed | No trading Authority grant；Vacuum remains when present | Hard readiness blocker |
| Audit COMPLETE but first eligible close is no longer future | Extend audit and select a later canonical close | Expected retry；no Observation race |
| LONG staged, SHORT failed | Abandon both targets | Gated FALLBACK_PREVIOUS；no partial switch |
| Previous pointer drift during materialization | Do not guess or restore another pair；keep new Signal fenced | Split-authority Incident；Owner action |
| Materialization after 01:14 | Continue within bounded timeout；opportunity gap accepted | SLO warning, not correctness failure |
| Materialization exceeds 1800s | Abandon generation | Gated fallback；unknown ENTRY still stays fail-closed |
| Worker crash before Snapshot commit | Lease expires；full retry | No partial facts |
| Worker crash after Snapshot/Vacuum | Resume exact drain/latest generation | No duplicate Snapshot/Cancel |
| Worker crash after final commit | Idempotent Authority result | No duplicate activation |
| New valid Selection during warming | Old generation `SUPERSEDED`；Vacuum remains；newest wins | Expected supersession |
| First natural trigger occurs during any Authority gap | Persist suppression；no later cross promoted as first trigger | Expected missed opportunity；no Signal/Ticket |
| Old dynamic pointer before explicit Authority | Vacuum/session gate blocks new ENTRY | `selection_materializing` readiness |
| Owner pause | Abandon materialization；continue Snapshot + ENTRY drain；never fallback | `OWNER_PAUSED_NOT_MATERIALIZED` |
| Resume without current valid Snapshot | Remain no-trade | Owner-visible blocker |

`PRE_FENCE_CONTINUITY`、`VALID_EMPTY`、`NO_CHANGE` 和 `SUPERSEDED` 是业务结果，不是系统
Incident。Identity conflict、split authority、digest drift、无法drain ENTRY和无法保护retained
fill是生产异常。
`FALLBACK_PREVIOUS` 是可审计的 **post-fence** 恢复结果而非默认兜底；它必须满足10.9全部
gates。Pre-fence Selection结果不改变已建立continuity，也不创建fallback Authority/Event。

## 15. Owner Control And Rollback

### 15.1 Control-neutral Selection

Dynamic Selection 不自行 resume 或 pause `SOR-001`。Owner 当前允许策略运行时，Selection
决定 Instrument eligibility；Owner pause 时，Selection不能产生真实ENTRY authority。

Owner Pause transaction 必须：

1. 先写 durable OwnerAuthorization / Strategy Control version；
2. 打开或保持 Strategy Entry Vacuum；
3. abandon未生效Generation并写 `OWNER_PAUSED_NOT_MATERIALIZED`；
4. 阻止Admission、Ticket issuance和ENTRY dispatch；
5. 继续撤销unfinished ENTRY、解析unknown outcome和保护已有fill；
6. 不在Pause transaction中提前运行Gap Audit；Resume准备授权时再创建exact audit；
7. 不 retire最后一个Active Universe，不 fallback，不停止既有Position lifecycle。

Pause期间Selection照常计算并入库。Resume不是“重新打开旧Universe”，而是允许当前有效
Snapshot materialize；当前Snapshot `selected_count=0`时继续无交易，无合法Snapshot时继续
禁用。若Snapshot members与current pair相同，必须完成Pause Vacuum drain、pause-window
current-pair Gap Audit并提交新的`NO_CHANGE` revision后才解析Vacuum；不warming、不复活Pause前
Authority。

`static_baseline` 模式继续使用 exact current LONG/SHORT pointers，但必须与冻结 rollback
baseline 或后来 materialized Static generation 一致。Migration 安装后不会改变现有 Static
Signal eligibility。`dynamic_selection` 的 Owner 开启采用 pending effective Session，不在操作瞬间
制造跨 Session 的无意停机。

### 15.2 Explicit rollback operation

Owner-visible rollback：

```text
Dynamic Selection OFF
-> selection mode becomes disabled immediately
-> no new SOR Signal eligibility
-> open/drain Strategy Entry Vacuum
-> clone frozen rollback baseline into new LONG/SHORT Universe versions
-> serially certify and warm exact Static generation
-> atomically activate both Static pointers
-> selection mode becomes static_baseline
```

该操作必须：

- 使用 durable OwnerAuthorization；
- 使用 exact expected control version；
- 使用 idempotency key；
- 不直接 DML current pointers；
- 不 re-activate retired Universe；
- 撤销 unfinished ENTRY，但不影响已有 protected Ticket/Position；
- 失败时保持 `disabled`，不回到不确定 Dynamic。

### 15.3 No schema downgrade

Rollback 是业务行为 fix-forward，不 downgrade Migration、不恢复旧代码、不双写、不读取旧表。

## 16. Migration Design

### 16.1 Revision

建议新增单一 forward revision：

```text
0006_sor_dynamic_instrument_selection_v0
```

### 16.2 Preservation boundary

Migration 必须：

1. 保留所有 Registry、Policy、Signal、AdmissionDecision、Claim、Ticket、Command、Position、
   Incident、Settlement 和 Review lineage；
2. 将现有 Universe rows 标记 `source_kind=manual`；
3. 不修改 existing Universe member/digest；
4. 创建generic Selection Job、Selection tables、SOR typed spec extension、Generation exact-two
   target table、Universe sole Generation FK、constraints、indexes和immutability triggers；不创建
   target-member copy、second materialization linkage或Universe direct Snapshot FK；
5. 创建SelectionSessionAuthority、Authority current pointer、Strategy Entry Vacuum/current events、
   Authority Gap Audit current/events；
6. 为 Dynamic Signal/AdmissionDecision/Claim/Ticket 增加 nullable historical-safe
   `selection_authority_id`，新 Dynamic lineage强制一致；
7. 扩展 Ticket Aggregate/Event/Command projection，支持
   `selection_vacuum_entry` cancel和`VACUUM_PARTIAL_RETAINED`实际数量计划；
8. 为Universe lifecycle增加无Signal authority的`staged`状态，并创建通用
   `brc_selection_authority_gap_audits_current/events`与`brc_strategy_trigger_suppressions`；
9. seed frozen SelectionSpec、two Event bindings 和 24 Candidate members；
10. seed selection control 为 `static_baseline`，不自动启用 Dynamic；
11. 捕获只引用exact immutable source LONG/SHORT Universes的pre-Dynamic rollback baseline；不复制
    baseline members；
12. 保留现有 global single-Warming constraint；
13. 创建复用现有Release Certification manifest的薄release compatibility projection；
14. 不创建 active Dynamic Snapshot、Authority、Vacuum或Generation。

Migration 只拥有 Schema、约束、不可变 Spec seed 和 preservation projection。它明确禁止：

- 拉取 Binance market data；
- 计算当天 Selection；
- 打开 Strategy Entry Vacuum；
- 创建当日 Materialization Generation；
- warming/certification/activation Universe；
- 写 `SelectionSessionAuthority`。

### 16.3 Cutover rule

该 revision 修改 Schema、Observation/FinalGate eligibility、Ticket/Command reducer和Universe
activation，必须遵循 current **stopped、flat、forward-only、preservation-gated** deployment。
禁止 active-position schema handover、dual read、dual write、old-schema fallback 或 mixed
writers。Migration 完成只说明数据库结构可供新代码使用，不表示 Selection 或 Universe 已完成
业务切换。（来源：`AGENTS.md`、`docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`）

## 17. Deployment And First Activation

### 17.1 Release Compatibility Classification

每个 exact release candidate 在部署前必须冻结一条 compatibility fact：

| Classification | Exact meaning | Restart behavior |
| --- | --- | --- |
| `COMPATIBLE_RESTART` | StrategyVersion、EventSpec/Detector semantics、Universe membership semantics、required Fact contract、warm/certification contract、RuntimeScope identity 和 Schema data contract 对 persisted Active Universe 均兼容 | Directly recover existing Active Universe/pointers/Authority；do not warm |
| `REQUIRES_RUNTIME_REMATERIALIZATION` | 上述任一 identity/semantic contract 改变，使旧 warm/certification/RuntimeScope facts不再证明新代码可运行 | Persist release fence；start new runtime fail-closed；Materializer explicitly re-certifies/re-materializes in background |

分类必须保存exact from/to commit、from/to schema、classification、bounded reason codes、
compatibility basis digest和existing certification manifest digest。它直接复用现有manifest
已有StrategyVersion/EventSpec/Detector/fact/warm/RuntimeScope identities，不建设第二release
engine、classifier framework或deployment orchestrator。不能根据“本次文件改动不多”推断兼容，
也不能把Schema migration本身自动等同于rematerialization。

本次首次 `0006` release 在保持 Crypto SOR v4 Detector、EventSpec、required facts、warm contract
和既有 Static membership语义不变的前提下，预期可分类为 **`COMPATIBLE_RESTART`**：迁移仍按
stopped-and-flat执行，但 restart后直接恢复 persisted Static Active Universe，不重新 warming。
最终分类必须由 exact release certification 证明，而不是由本文预先授权。

### 17.2 Software Deployment Sequence

1. 冻结 exact release candidate、Schema revision和Release Compatibility fact；
2. 完成 production-grade Release certification；
3. 读取 Tokyo current commit/schema/Policy/systemd/DB/exchange facts；
4. 若为 `REQUIRES_RUNTIME_REMATERIALIZATION`，在旧 writers 停止前通过正式控制面写 durable
   release fence；若当前 Schema尚无该能力，则该release不能声称支持后台rematerialization；
5. 等待当前 revision要求的 stopped-and-flat preservation gate；
6. 停止四个 Worker；
7. forward migrate to `0006`；Migration仅创建Schema/Spec/preservation facts；
8. 部署 exact code并写 exact release marker/classification；
9. 启动四个 Worker及三个逻辑组件的独立 loop/lease；
10. runtime从PostgreSQL恢复Job、Generation、Vacuum、Authority、Universe pointers和Ticket
    lifecycle；先Reconciliation，再允许任何new ENTRY；
11. readonly verify commit/schema/classification/service identity、preserved lineage和DB/exchange
    consistency。

### 17.3 Software Deployment Completion

**Software Deployment Complete ≠ Dynamic Universe Materialization Complete**。

Deployment 完成条件是：

1. exact code/schema/release classification一致；
2. 四个systemd Worker active/enabled且无身份漂移；
3. Selection/Materialization/Observation三个逻辑lease entry point可运行；
4. persisted current authority已恢复，Reconciliation无未解释内外部矛盾；
5. `COMPATIBLE_RESTART` 已直接复用exact Active Universe且未warming；或
   `REQUIRES_RUNTIME_REMATERIALIZATION` 的release fence仍fail-closed且后台Generation可恢复；
6. 无Migration副作用创建的Snapshot、Vacuum、Generation、Authority或exchange command。

Deployment script不得同步等待当日Dynamic warming、双边staging或activation。若数据库已有
unresolved Snapshot/Generation，Materialization Coordinator在服务恢复后自行claim并继续；其
最终业务结果由单独readonly monitor报告。

### 17.4 Candidate Readiness Gate

Dynamic mode 前对固定 24-member Panel 做一次 readonly operational audit：

- canonical active/pending product identity；
- contract available；
- current instrument rules；
- compatible independent-side account mode；
- approved configured leverage；
- approved margin mode；
- no unresolved ownership contradiction。

该 audit 不给 Candidate 交易权限，也不建立 RuntimeScope；目的是避免规则频繁选中一个必然
无法通过正式 warming 的产品。系统不自动修改 leverage 或 account settings。未通过时 Owner
看到 exact blocker，Dynamic activation 不开始；任何需要扩大已配置 Instrument scope 的动作
保持独立 Owner 生产授权。

### 17.5 First Dynamic Activation

第一次 Dynamic activation 是单独 Owner-reviewed action：

1. exact control version 写入 `pending_selection_mode=dynamic_selection` 和下一个明确 UTC Session；
2. 不修改 Strategy Control 和 Policy；
3. 在首个Dynamic outcome前，current mode保持`static_baseline`，existing Static Universe和
   authority持续负责new ENTRY；不创建`PRE_FENCE_CONTINUITY`或伪造
   `continued_from_selection_authority_id`；
4. 在目标Session `01:00`由Selection Runner只提交正式Snapshot；Materialization Coordinator
   再从DB handoff独立推进；
5. 只有exact SelectionSessionAuthority `ACTIVE_NEW/NO_CHANGE/VALID_EMPTY` transaction才把
   current mode切到`dynamic_selection`；Selection/pre-fence失败保持Static。若Vacuum后的首次
   materialization失败并恢复previous pair，则提交transition-scoped
   `SelectionSessionAuthority(FALLBACK_PREVIOUS, continuity_source_kind=STATIC_BASELINE)`，冻结
   exact failed Generation、union Gap Audit、trigger suppression和first eligible close；current mode
   仍保持Static。它恢复当期Static交易资格，但不表示首个Dynamic Session已经成功；
6. postflight readonly验证Snapshot、24 decisions、Authority/first eligible close、Vacuum/Gap
   Audit terminal state、two
   pointers、`0..14` active scopes、zero split和exact outcome。

## 18. Performance And Resource Contract

| Resource | Bound |
| --- | --- |
| Candidate count | Exact **24** |
| Kline count per member | Exact **96** 15m bars |
| Network concurrency | Default max **6** |
| Selection frequency | Once per UTC Session plus bounded retries |
| Snapshot rows | 1/day/spec |
| Member rows | Exact 24/day |
| Active SOR scopes | **2..14** for Dynamic Selected 1..7, two sides |
| Transition scope ceiling | Previous Active max 14 + staged LONG max 7 + warming/staged SHORT max 7 = **28** bounded scopes |
| Vacuum drain | Exact StrategyGroup unfinished ENTRY set；normally 0 or 1 because global new-ENTRY is serialized |
| Materialization timeout | **1800 seconds** per generation；unknown exchange outcome remains separately fail-closed |
| Runtime files | Zero JSON/Markdown/CSV authority files |
| New persistent workers | Zero |
| Logical runtime components | Exact **3**：Selection Runner、Materialization Coordinator、Observation Runner |
| Lease namespaces | Exact **3** and mutually independent |

查询使用 exact session/spec keys 和 bounded 24-member sets，不在 runtime cadence 扫描全历史。
生产无 Signal cadence 不生成报告文件。

## 19. Test And Certification Matrix

### 19.1 SelectionCore unit tests

- exact 24-member source integrity gate；one missing/gapped member rejects whole attempt；
- source failure produces zero Snapshot/MemberDecision and zero Rank substitution；
- exact UTC session/cutoff；
- exact 96-bar continuity；
- OR 4-bar semantics；
- ATR previous-close and 14-bar semantics；
- quote-volume 96-bar semantics；
- Activity boundary equal/below/above `20M`；
- Decimal context and canonical digest；
- stable three-key ranking；
- all Primary Reasons；
- Ready `0` => Snapshot `selected_count=0`；Runtime `VALID_EMPTY`由Materializer覆盖；
- Ready `1..6` => exact variable Selected count；
- Ready `7` and `24` => capped Top 7；
- Selected/Near/Not Selected exact ranks；
- LONG/SHORT shared set。

### 19.2 Historical Golden parity

生产 SelectionCore 上线前必须对 **961 Sessions × 24 members** 比较：

- session identity；
- input qualification；
- primary reason；
- OR/ATR/Activity canonical values；
- rank；
- Selected/Near/Not Selected；
- historical EMPTY；
- snapshot/member digests；
- deterministic rerun。

Replay 的 961 Sessions 实际 `Ready=14..24`，因此 production `1..7` 语义不会改变这些 Golden
memberships。该 gate只证明 production implementation 在相同输入区域等于产生 Historical
Replay结果的 V0，不重新调参；`Ready<7` 由独立 synthetic production tests覆盖，并明确不是
历史 Decision Contract 的重写。

当前本地只有 `REPORT.md` 摘要，没有完整 member-level Golden Artifact；实施前必须取得冻结
artifact 或由相同冻结输入重新生成并归档 exact digest。该缺口不阻塞本设计复核，但阻塞
implementation certification。

### 19.3 PostgreSQL integration tests

- Spec exact 24 members/two events；
- Selection Job only permits DUE/CLAIMED/SNAPSHOT_READY/SOURCE_FAILED/COMPUTE_FAILED；
- Selection Job cannot store Generation/Vacuum/Authority/current Universe fields；
- Selection、Materialization、Observation leases cannot claim or renew each other；
- Snapshot + 24 decisions atomicity；
- SNAPSHOT_READY ends Selection Plane；Materializer can resolve it after Selector exits；
- Selection Period creates PRE_FENCE_CONTINUITY at `D 01:00`, not `D 00:00`, without waiting for Selection Job/Snapshot；
- Selection SOURCE_FAILED/COMPUTE_FAILED changes continuity reason, not its existence；
- SelectionSessionAuthority immutable insert/current-pointer replacement；
- PRE_FENCE_CONTINUITY/ACTIVE_NEW/NO_CHANGE/FALLBACK_PREVIOUS/VALID_EMPTY/
  OWNER_PAUSED exact shape；
- PRE_FENCE_CONTINUITY permits optional Job/attempt/Snapshot reason provenance, requires exact
  current pair and predecessor or Gap Audit proof, and creates no Generation/Vacuum/cancel/fallback；
- later same-Session Snapshot outcome supersedes continuity through a higher Authority sequence；
- first pending Dynamic activation keeps Static authority and requires no predecessor SelectionAuthority；
- first activation post-fence failure commits FALLBACK_PREVIOUS with STATIC_BASELINE source、exact
  failed Generation/Gap Audit/first eligible close while selection mode remains Static and all pending
  activation fields clear atomically；
- Authority effective-from/first-eligible-close/expires-at bounds；
- Authority cannot become current if its first eligible close is no longer future after Gap Audit；
- continuous predecessor and audited-gap proof are mutually exclusive and exhaustive for trading grants；
- Dynamic Signal/Claim/Decision/Ticket exact same `selection_authority_id`；
- immutable update/delete rejection；
- exact-key idempotency；
- conflicting duplicate rejection；
- Selection lease and Materialization lease expiry/reclaim independently；
- one global warming authority；
- Generation exact two EventSpecs and serial order；
- Generation targets contain expected digest/order but no copied target members or `universe_version_id`；
- Dynamic target digest must equal immutable Snapshot Selected digest；Static target digest must equal
  immutable baseline source Universe digest；
- target Universe identity cannot be allocated while Generation is PENDING/DESIRED；
- Universe row owns the sole Generation linkage；no linkage table or direct Snapshot FK exists；
- unique `(materialization_generation_id, event_spec_id)` rejects a second target Universe；
- rollback baseline references immutable source Universes and has no copied baseline-member table；
- LONG `warming -> staged` releases global slot before SHORT warming；
- staged Universe cannot emit Signal；
- two pointers atomic switch；
- activation generation increment；
- previous two Universes retired；
- failed generation preserves previous two Active rows/pointers；
- FALLBACK_PREVIOUS requires Owner enabled + previous operationally valid + Vacuum drained + exact
  COMPLETE union Authority Gap Audit and future first eligible close；
- VALID_EMPTY opens/drains Vacuum but never fallbacks；
- VALID_EMPTY is non-retroactive：unfinished ENTRY drains, while previously filled/protected Ticket
  lifecycle continues and no earlier valid fact is rewritten；
- ordinary NO_CHANGE requires no open Vacuum and creates new Authority without new
  Universe/warming/Vacuum；
- Pause Resume with identical members requires ENTRY_DRAINED + COMPLETE current-pair Gap Audit,
  resolves the Pause Vacuum and commits a new NO_CHANGE sequence without warming；
- Selection pending/success/failure leaves PRE_FENCE_CONTINUITY active until Vacuum commit；
- late PRE_FENCE_CONTINUITY audits from first unauthorized eligible close before granting；
- late ordinary NO_CHANGE without continuous predecessor also requires current-pair Gap Audit；
- SUPERSEDED generation cannot later activate；
- one current Strategy Entry Vacuum per scoped strategy；
- Vacuum state/event idempotency and crash recovery；
- Authority Gap Audit only permits PENDING/COMPLETE/FAILED legal transitions；
- absence of suppression rows without exact COMPLETE audit is never a checked-negative fact；
- Vacuum activation/fallback audit scope is exact previous pair members UNION desired pair members；
- late continuity/NO_CHANGE audit scope is exact current pair；
- COMPLETE audit stores positive suppressions and checked-negative results in one canonical result digest；
- crossing `first_eligible_close_time_ms` before commit forces incremental audit and a later close；
- ACTIVE_NEW/FALLBACK_PREVIOUS/Pause-Resume NO_CHANGE cannot commit without continuous proof or
  exact COMPLETE Gap Audit as applicable；
- selected certifications exact/fresh；
- no Rank 8 substitution；
- same member set on next day preserves membership-only Universe digest and creates no new Universe identity；
- Selection provenance remains reachable through Universe -> Generation -> Snapshot and Authority；
- trigger suppression immutable/idempotent exact-key insert；
- release compatibility fact is a thin immutable projection of the existing Release Certification
  manifest and cannot own an independent rule engine, manifest or deployment state machine；
- Candidate public-data membership does not create RuntimeScope/certification lease；
- migration preserves terminal lineage。

### 19.4 Observation/Signal integration tests

- Selection Runner cannot invoke Materializer in the same call stack；
- Observation Runner cannot advance Selection Job or Generation state；
- Materializer progresses SNAPSHOT_READY with Selection Runner stopped；
- Materializer creates PRE_FENCE_CONTINUITY before Selection completes and records later failed-Job reason；
- no open/future Kline consumed；
- Dynamic session mismatch blocks Signal；
- materializing state fences previous new-Signal authority；
- open Vacuum blocks Admission、Ticket issuance and ENTRY dispatch；
- lifecycle Stop/TP1/Runner/Exit bypasses only this new-ENTRY fence；
- FALLBACK_PREVIOUS exact pair can produce current-session Signal；
- first-activation Static FALLBACK_PREVIOUS is honored by the Static path only at/after its frozen
  first eligible close and never changes selection mode to Dynamic；
- PRE_FENCE_CONTINUITY exact pair remains eligible while Snapshot progresses PENDING/DESIRED；
- on-time continuity permits the first `01:15` close；late continuity cannot process a pre-grant close；
- VALID_EMPTY cannot produce new Signal/ENTRY；
- NO_CHANGE authorizes only exact current pair；
- ordinary NO_CHANGE is rejected while any scoped Vacuum remains open；
- selected member can produce normal Signal；
- unselected member cannot create new SOR Signal；
- first natural trigger during any Authority gap writes suppression and later cross produces no Signal；
- checked-negative gap permits the first close at/after `first_eligible_close_time_ms`；
- absence of suppression without COMPLETE audit keeps Observation fail-closed；
- suppression replay uses exact SOR v4 Detector digest and remains restart-safe；
- previous-only member gap trigger is suppressed before FALLBACK_PREVIOUS can reopen it；
- desired-only member gap trigger is suppressed before ACTIVE_NEW can open it；
- continuous PRE_FENCE_CONTINUITY -> NO_CHANGE path requires no audit and creates no observation gap；
- stale old Dynamic pointer cannot authorize new Session；
- Owner pause abandons materialization、blocks fallback and drains pending ENTRY；
- Resume uses current latest valid Snapshot；same-member Resume drains/audits/resolves Pause Vacuum
  before a new NO_CHANGE Authority；no Snapshot remains disabled；
- global `new_entry_submit_enabled=false` overrides Selection；
- Admission/risk logic receives no new Alpha filter；
- same Snapshot drives LONG and SHORT。

### 19.5 Ticket/lifecycle full-chain tests

- Signal-before-Vacuum becomes terminal AdmissionDecision blocker；
- prepared/claimed-undispatched ENTRY is superseded before network I/O；
- venue open zero-fill ENTRY creates durable exact cancel and terminal no-position closure；
- outcome_unknown keeps Vacuum unresolved and is never blindly resent；
- full fill during drain is protected and continues normal lifecycle；
- vacuum-attributed partial fill cancels remainder and retains exact actual position；
- ordinary partial fill still controlled-flattens；
- retained partial requires step-aligned positive TP1 + positive Runner and quantity conservation；
- one-step/zero-leg partial fill controlled-flattens；`runner_only_partial` cannot be persisted；
- retained partial hard risk/protection failure still controlled-flattens；
- Vacuum cannot resolve before cancel/unknown/protection completion；
- existing Ticket survives next-day deselection；
- protected Position continues Stop/TP1/Runner；
- lifecycle Command dispatch ignores new Selection membership；
- Reconciliation/Settlement/Review retain frozen Universe lineage；
- rollback does not flatten or cancel existing exposure。

### 19.6 Fault tests

- PG unavailable before/after Snapshot commit；
- Binance timeout/partial member failure makes whole attempt SOURCE_FAILED with zero Rank/Snapshot；
- Selection Runner crash and Selection lease recovery；
- Materialization Coordinator crash and independent Generation/Vacuum recovery；
- Observation Runner crash without changing Selection/Generation state；
- 01:14 SLO miss without correctness failure；
- 1800-second materialization timeout；
- LONG staged / SHORT readiness failure；
- crash between LONG staged and SHORT warming；
- fallback previous reason/idempotency；
- source digest drift；
- activation conflict；
- duplicate process；
- restart after Generation ACTIVE commit；
- crash after Vacuum open / before cancel dispatch；
- crash after cancel accepted / before final quantity freeze；
- Pause and new Snapshot race with generation activation；
- crash at Selection decision boundary before continuity Authority commit；
- process wakeup at `D 00:00` cannot create the `D 01:00` Selection-Period Authority early；
- first activation fails after Vacuum, then crashes before/after Static FALLBACK_PREVIOUS commit；
- crash after continuity Authority commit / before current-pointer acknowledgement；
- same-Session Snapshot supersedes committed continuity without duplicate Authority；
- Gap Audit crash before COMPLETE and after suppression insert；
- final Authority transaction reaches first eligible close and must rollback/extend audit；
- LONG/SHORT Universe row creation with Generation FK is transactionally atomic；
- duplicate target Universe creation conflicts on exact Generation/EventSpec unique key；
- first pending Dynamic Selection failure leaves Static mode/authority unchanged；
- latest valid Selection supersedes older warming/staged generation；
- rollback baseline activation failure remains disabled；
- `COMPATIBLE_RESTART` directly recovers persisted Active Universe with zero warming；
- `REQUIRES_RUNTIME_REMATERIALIZATION` remains fenced until explicit materialization；
- release compatibility projection cannot diverge from its referenced certification manifest；
- deployment reaches DEPLOY COMPLETE while pending Generation continues in background；
- Migration creates no Snapshot/Vacuum/Generation/Authority/exchange command。

### 19.7 Verification tiers

| Tier | Required scope |
| --- | --- |
| Focused | SelectionCore, repository method, exact failing boundary |
| Fast | Unit, architecture, affected PG integration, Ruff, Mypy |
| Release | Complete unit/integration/full-chain, migration, three-Plane architecture, release classification, Ruff, Mypy, diff |
| Postdeploy | Exact schema/commit/spec/classification, 24 Candidate public identities, worker/component state, no split pointers, zero unexpected Signal/Command |
| Live readonly | First Snapshot, 24 decisions, exact Authority/Vacuum/Gap Audit outcome, `first_eligible_close_time_ms`, `0..14` scopes, Binance position/order agreement |

本次触及 Schema、Observation/FinalGate eligibility、Ticket/Command/Lifecycle reducer和
new-Signal path，因此不能按 research-only 发布；
但无需为 Selection 改动重复无关的长期性能研究。Release certification 对 frozen exact
candidate 运行一次，部署复用其 manifest。

## 20. Minimal Production Change Surface

### 20.1 New production modules

建议最小逻辑边界：

```text
src/trading_kernel/domain/instrument_selection.py
src/trading_kernel/domain/selection_authority.py
src/trading_kernel/domain/strategy_entry_vacuum.py
src/trading_kernel/application/run_instrument_selection.py
src/trading_kernel/application/coordinate_selection_materialization.py
src/trading_kernel/application/drain_strategy_entry_vacuum.py
src/trading_kernel/infrastructure/pg_instrument_selection_repository.py
```

`run_instrument_selection.py` 与 `coordinate_selection_materialization.py` 禁止互相直接调用；
Selection-to-Materialization的唯一handoff是committed Snapshot/Job state。Coordinator必须独立
从durable current pair建立或修订Selection-Period`PRE_FENCE_CONTINUITY`，不能等Selector返回值或
失败回调才创建continuity。若最终共用一个systemd process，也必须暴露两个独立bounded tick入口
和lease identity。

### 20.2 Existing modules requiring change

| Boundary | Required change |
| --- | --- |
| `domain/strategy_universe.py` | Add `staged` lifecycle and legal transition invariants |
| `application/ports.py` | Selection repository/source typed ports |
| `application/install_strategy_universe.py` / advance boundary | Support generation-owned warming-to-staged without granting Active authority |
| Worker interfaces | Host independent Selection/Materialization ticks without merging them into Observation call stack |
| `infrastructure/binance_public_market_source.py` | Exact typed quote-volume Kline source |
| `infrastructure/pg_universe_repository.py` | staged lifecycle, serial generation install/readiness, atomic pair activation/fallback |
| `infrastructure/pg_signal_repository.py` | Dynamic session/current authority validation |
| `application/observe_strategy_scope.py` | Selection-before-Signal gate |
| `application/ingest_signal.py` | Exact dynamic session revalidation |
| `application/issue_ready_signal.py` / `issue_ticket.py` | Vacuum + SelectionAuthority FinalGate and terminal blocker |
| `application/revalidate_entry_dispatch.py` | Add exact Vacuum/Authority preflight status |
| `application/dispatch_exchange_command.py` | Supersede undispatched ENTRY；new durable cancel purpose |
| `application/reconcile_ticket.py` / `recover_unknown_command.py` | Resolve vacuum ENTRY absent/open/partial/full without blind resend |
| `domain/reducer.py` / `domain/aggregate.py` / `domain/events.py` | Narrow retained-partial branch and actual quantity plan；ordinary partial remains flatten |
| `domain/exit_policy.py` | Derive step-aligned positive TP1 + positive Runner plan or reject retained materialization |
| SOR Observation cursor/episode boundary | Enforce Authority first eligible close and gap suppression without creating Signal |
| Signal/Claim/Ticket models and repositories | Freeze `selection_authority_id` for Dynamic lineage |
| `infrastructure/pg_models.py` | New Schema models |
| `migrations/trading_kernel/**` | `0006` forward revision |
| Release/deployment boundary | Freeze COMPATIBLE_RESTART vs REQUIRES_RUNTIME_REMATERIALIZATION and recover durable authority asynchronously |
| Owner control boundary | Dynamic/static/disabled operation；no direct SQL |

不修改 Alpha、Stop price、TP1 price、Runner rule、capital sizing或Netting semantics；但本设计
明确修改 Ticket lineage、Command cancel purpose、Lifecycle reducer和ENTRY exchange-write
preflight，以实现 Owner冻结的交易真空与部分成交保留语义。

## 21. Reusable Primitive Vs SOR-Specific Logic

| Reusable primitive | SOR-specific V0 |
| --- | --- |
| SelectionSpec version/identity | UTC 01:00 clock |
| Candidate Panel membership | Fixed 24 Crypto instruments |
| Selection Job/attempt/snapshot handoff | OR 4-bar geometry |
| Immutable MemberDecision | Pre-OR ATR14 |
| Independent Materialization lease/Generation | 20M quote-volume floor |
| Generation expected member digest + sole Universe FK | Top 7 / Near 7 |
| Universe lineage and atomic pointers | Shared LONG/SHORT set |
| SelectionSessionAuthority + Entry Vacuum + Authority Gap Audit | SOR first-natural-trigger suppression |
| Explicit static rollback | SOR v4 warm facts |

未来 CPM/BRF2 可复用 Snapshot、Decision、Generation、lineage 和 rollback，但必须有新的
SelectionSpec 和 Feature semantics。MPG/MI 仍需先分离 ComparisonUniverse 与 Tradable
StrategyUniverse，不能直接复制本 V0。

## 22. Rejected Alternatives

| Alternative | Rejection reason |
| --- | --- |
| Independent Forward Shadow first | Owner route changed；Historical gates already support direct small-capital production experiment |
| Selection Overlay at Admission | Alpha placed too late；pollutes risk boundary；creates dual authority |
| Overlay before Signal plus unchanged Universe | Still requires two current membership authorities |
| Selector creates DesiredGeneration or opens Vacuum | Crosses Selection/Runtime boundary and prevents DB-only handoff/recovery |
| One Selection-to-activation call stack | Couples Binance/compute success to warming and hides cross-component progress in memory |
| Deployment waits for Dynamic materialization | Makes software release duration depend on market/runtime state；pending Generation must resume asynchronously |
| Sequential LONG then SHORT activation | Serial warming is adopted, but serial activation is rejected because it allows split-direction production state |
| Static7 as automatic fallback | Owner requires exact previous Active pair, which may itself be Dynamic |
| New `FIRST_ACTIVATION_FALLBACK_STATIC` outcome | Duplicates post-fence recovery semantics；reuse `FALLBACK_PREVIOUS` with `STATIC_BASELINE` source while keeping mode Static |
| Silent previous-pointer reuse | Current pointer alone is not authority；fallback requires explicit Session outcome and reason |
| Create continuity only after Selection failure | Leaves a gap during successful Selection/PENDING/DESIRED；every Dynamic Session requires `PRE_FENCE_CONTINUITY` before Selection outcome |
| Bind first-trigger audit only to Vacuum | Late continuity and late NO_CHANGE can also miss first trigger；audit owns any unauthorized eligible-close gap |
| Absence of trigger-suppression row as a negative result | Cannot distinguish checked-negative from audit-not-run；Authority Gap Audit must own durable COMPLETE/digests |
| Audit only Desired members | Fallback could reopen a previous-only member after its first trigger was consumed；scope must be previous UNION desired |
| Pre-allocate target `universe_version_id` in PENDING Generation | Couples Desired intent to a runtime object that does not exist；immutable Universe creation transaction writes the sole Generation FK directly |
| Copy Snapshot Selected members into Generation target members | Duplicates immutable Desired facts and adds a consistency path；expected digest plus Snapshot FK is sufficient |
| Keep both Universe Generation FK and a materialization linkage table | Duplicates the same ownership fact；Universe Generation FK is the sole linkage |
| Store direct Snapshot FK on Universe | Duplicates `Universe -> Generation -> Snapshot` provenance and can drift |
| Copy rollback baseline members | Source Universe/member rows are immutable and restricted from deletion；pair references are sufficient |
| Build a second release classifier/orchestrator | Release compatibility is only a thin projection of the existing certification manifest |
| Rank 8 substitution for unsafe Selected member | Changes frozen Top-7 policy after Selection |
| Candidate source failure as member INELIGIBLE | Silently changes cross-sectional ranks and lets lower-ranked members enter because of missing data |
| Mandatory fifth systemd Worker in V0 | Logical components need independent leases/entry points, but may initially share an existing persistent process |
| Current CCXT OHLCV volume | It is base volume, not required quote volume |
| Reactivate retired Static Universe | Violates immutable lifecycle；rollback must clone into new versions |
| Copy all Selection feature fields to Signal/Claim/Ticket | Redundant and drift-prone；only immutable `selection_authority_id` propagates |
| Treat every partial fill as retained | Rejected；only exact Vacuum-attributed cancellation race gets the new branch |
| `runner_only_partial` | Violates frozen TP1 + Runner Exit Policy geometry；insufficient actual quantity must controlled-flatten |
| Selection provenance inside Universe digest | Breaks existing membership-only semantic identity and creates false Universe changes |
| Activate while unfinished ENTRY remains | Rejected；authority would be ambiguous and a late fill could cross generations |
| Repository-external JSON/CSV authority | Violates PostgreSQL runtime authority |

## 23. Exact Answers To Review Questions

| Question | Answer |
| --- | --- |
| Production Selection authority | Snapshot/Decisions own ranking；StrategyUniverse owns members；SelectionSessionAuthority owns time-bound ENTRY permission；Vacuum owns negative fence；no Job/Generation duplicates Active authority |
| Three Plane handoff | Materializer opens Session continuity independently；Selection ends at committed Snapshot or failed Job；Deployment recovers both planes from DB and never waits for warming |
| New DB objects | Generic specs、typed extension、Selection Jobs/attempts/snapshots/decisions、Generation exact-two target digests、Selection Authorities、Strategy Entry Vacuum/events、Authority Gap Audit/events、trigger suppressions、thin release compatibility projection；Universe sole Generation FK and Signal/Claim/Ticket linkage |
| Candidate Panel vs Universe | Panel is 24-member public-data discovery scope；Active Universe is exact Selected `1..7` per EventSpec |
| Selected set active before 01:15 | **01:14 is SLO only**；previous pair remains under pre-fence continuity until Vacuum；any late grant audits its eligible-close gap |
| Runtime ownership | Selection Runner、Materialization Coordinator、Observation Runner use independent application entry points and DB leases；V0 may share an OS process |
| Observation integration | Observation reads only durable Active Universe/Authority/Vacuum/audit/suppression；it does not advance Selection/Materialization |
| Signal ordering proof | Authority + Universe + Vacuum + first eligible close + continuous/audited gap proof + suppression validation at Signal, ingestion, Ticket issuance and dispatch preflight |
| Failure choice | `PRE_FENCE_CONTINUITY` is independent of Selection success/failure and lasts to Vacuum；post-fence failure may explicit FALLBACK_PREVIOUS only after drain and union Gap Audit |
| First activation fallback | Reuse transition-scoped `FALLBACK_PREVIOUS` with `STATIC_BASELINE` source、exact failed Generation/Gap Audit/first eligible close；selection mode remains Static |
| Session vs Authority clock | `session_start_ms=D 00:00` owns SOR identity；Selection/Authority Period starts at `D 01:00` decision boundary |
| VALID_EMPTY timing | Forward-only from Vacuum/Authority commit；unfinished ENTRY drains, filled/protected Ticket lifecycle continues |
| Ready < 7 | Ready `1..7`全部 Selected；Ready `0` is VALID_EMPTY，no new opportunity and no fallback |
| Candidate source failure | Whole Selection attempt SOURCE_FAILED；zero Snapshot/Rank/Rank substitution |
| Existing Position | Ticket-frozen lifecycle continues；only unfinished ENTRY is drained；Selection removal itself never flattens |
| Ticket trace | Snapshot outcome: Ticket → Authority → Universe/Generation → Snapshot → MemberDecision；continuity outcome: Authority → predecessor + optional Job/Snapshot reason provenance |
| Partial ENTRY at Vacuum | Retain only if actual quantity forms legal positive TP1 + Runner；otherwise controlled flatten；ordinary partial fill unchanged |
| Universe digest | Existing strategy/event/canonical-members membership-only digest；provenance remains in FK columns |
| Release compatibility | Thin projection of existing Release Certification manifest；compatible restart reuses persisted Active Universe without warming；semantic invalidation requires explicit fenced rematerialization |
| Historical parity | 961 × 24 exact Golden certification |
| Rollback | Disable selection, clone frozen Static baseline, warm/certify, atomic two-pointer activation |
| Future strategies | Reuse Selection primitive and Generation；new typed strategy-specific SelectionSpec required |
| Generic vs SOR-specific | Generic identity/decision time/cutoff/effective time/snapshot/generation；SOR-specific clock/features/rank |
| Smallest change | Three independent application components + Selection/Authority/Vacuum primitives + bounded Observation/Universe/FinalGate/Command/Lifecycle extensions；no second execution chain |

## 24. Review State

本设计已经完成最后一轮targeted revision：Selection-Period`PRE_FENCE_CONTINUITY`覆盖Selection
成功、失败与materialization等待；通用Authority Gap Audit覆盖所有未授权eligible-close区间；
`first_eligible_close_time_ms`消除15m boundary竞态；Generation/Universe/rollback baseline删除重复
事实路径；首次Static-to-Dynamic activation保留Static authority直至首个Dynamic outcome。实施
澄清进一步冻结：Authority Period从`D 01:00`decision boundary开始；首次post-fence失败复用
`FALLBACK_PREVIOUS + STATIC_BASELINE`且mode保持Static；`VALID_EMPTY`只向前生效。

架构与Owner业务语义已经定型，当前状态为`DESIGN_APPROVED`。后续implementation authority、
active execution scope与逐卡证据只由**Implementation Plan**记录；本设计不授权Migration执行、
部署、策略resume或真实资金动作。Implementation Plan位于
`docs/superpowers/plans/2026-08-23-sor-dynamic-instrument-selection-trading-v0-implementation-plan.md`，
其当前状态与下一Gate应从该文档读取，禁止在本设计复制易漂移的Task状态。

外部复核应重点挑战：

1. Selector 是否彻底终止于 `SNAPSHOT_READY`，且不读取/改变任何 Runtime authority；
2. Materializer 是否能在 Selector 已退出时仅从 PostgreSQL 独立恢复；
3. Selection Job、Generation、Authority 是否不再重复表达“当前 Active”；
4. serial warming + staged lifecycle 是否保持 one-global-warming contract，并彻底禁止
   LONG/SHORT 半切换；
5. previous Universe 未 Retire时，Entry Vacuum 是否在Signal、Ticket和dispatch三层可靠撤销权限；
6. `PRE_FENCE_CONTINUITY`是否在Selection结果前建立并一直持续到Vacuum，与post-fence
   `FALLBACK_PREVIOUS`是否严格分离，且fallback全程低于Owner pause；
7. source integrity failure 是否必然 whole-attempt失败、零Rank补位；
8. 任意Authority gap的first natural trigger是否在grant前完成exact-scope durable audit，
   checked-negative与suppression是否均可证明，且不引入隐式Re-entry；
9. Vacuum partial-retained是否只允许合法TP1+Runner双腿，并彻底删除runner-only路径；
10. Universe digest是否严格保持membership-only，provenance是否只通过FK表达；
11. Desired facts是否只来自Snapshot/baseline immutable source和expected digest，Universe sole
    Generation FK是否消除target members、linkage table与direct Snapshot FK重复；
12. Pause Resume同成员是否drain、audit、resolve Vacuum后才提交新`NO_CHANGE`，且不复活旧Authority；
13. compatible restart是否直接恢复persisted Active Universe，release fact是否只是既有manifest
    的薄投影，invalidating release是否显式fence；
14. Deployment是否能在pending Generation继续后台运行时独立完成；
15. durable cancel、unknown outcome、实际数量计划和Initial Stop是否形成可恢复链；
16. `first_eligible_close_time_ms`与final transaction publish window是否消除15m boundary竞态；
17. 01:14 SLO与1800秒timeout是否能在当前2C4G runtime验证且不饿死global warming queue；
18. rollback baseline和Golden Artifact缺口是否在实施前被关闭。

本设计永久保持`production_authority: NONE`；实现、Migration、部署与首次Dynamic activation继续
遵循Implementation Plan和Owner逐卡授权。
