---
title: GENERIC_MULTI_STRATEGY_DYNAMIC_SELECTION_V1_IMPLEMENTATION_PLAN
status: PLAN_APPROVED
independent_review: CONDITIONALLY_APPROVED
required_plan_amendments: COMPLETE
owner_confirmation: GRANTED_2026-09-06
date: 2026-09-06
design_authority: ../specs/2026-09-06-generic-multi-strategy-dynamic-selection-v1-design.md
implementation_plan_authority: ALLOWED
implementation_authority: CODE_AND_TEST_ONLY
active_execution_scope: GS-04_TO_GS-13
production_authority: NONE
further_feature_research: CLOSED
---

# Generic Multi-Strategy Dynamic Selection V1 — Implementation Plan

## 1. 目标、权限与来源

**本计划将已批准设计拆成GS-00至GS-13共14张可验收Task Card。当前只编写计划，全部Task均未开始执行。** Owner转交的独立复核允许四项P0修订落实后进入Plan；不授予CODE_AND_TEST、Tokyo操作或策略activation。

规范来源为[详细设计](../specs/2026-09-06-generic-multi-strategy-dynamic-selection-v1-design.md)，特别是§4.7、§6.4、§8.4、§10.3四项amendment。设计§18记录条件批准及处理结果；研究出处见设计§19与Stage-3.1 provenance amendment。Task条款不得覆盖冻结Feature、N、cadence、SOR Golden、资金、ExitProfile或Owner控制边界。

```text
design_status = DESIGN_APPROVED / PLAN_ONLY
plan_status = PLAN_APPROVED
implementation_authority = CODE_AND_TEST_ONLY
active_execution_scope = GS-04_TO_GS-13
production_activation_authority = NONE
further_feature_research = CLOSED
```

独立复核已完成并由Owner在本任务明确授权按本计划执行本地代码与测试。GS-00至GS-03已完成；Owner进一步授权连续完成GS-04至GS-13，在本地完整R4 candidate形成前不再逐卡等待确认。文本中的“执行/实现”是受本计划、Task依赖和Hard Stop约束的本地工作；不授权Tokyo操作、生产migration、部署或策略activation。

针对`4b2947e9f43fb3e2c4f165c91a957e0f20adb632`的独立复核已批准设计，并对Plan给出两项条件。strategy-scoped certification和Static migration neutrality已并入原卡，不新增Task、不修改已批准设计主体。Owner随后明确要求“按文档开始执行开发测试”，故本地实施范围正式开启；执行状态由本文件头和当前Task Card管理。

## 2. 工作区、基线与已知缺口

| 项目 | 直接检查的事实 | 实施含义 |
| --- | --- | --- |
| 集成源码 | `dev@71757d7422a36bfbe13c214fd33b3cb3a07807cc`，含已收回的SOR恢复修复 | 实施启动重新fetch并核对新增修复；不在旧研究分支开发 |
| 设计原稿 | `a3c1e5c495376321e076a064a33eaee5fbbc5e9d`；本轮四项amendment在同设计分支 | 以修订后的设计和本Plan为规范，不只读原稿 |
| 研究 | results `f65d72fa92580de4b8c0323f4106d5975b97f4eb`；amendment `42957b2091b988c53d6e03cb24639c17c54229b5` | 保持独立，不merge research或生产import研究模块 |
| Schema/Domain | 源码head为0007；Selection多处写死SOR day/pair/Top7，Universe表示上限10 | 先冻结通用domain，再一次forward演进原表 |
| Comparative/Episode | comparison依赖交易Universe；Episode reducer无comparison provenance | 必须把binding transition barrier接在创建Episode/Signal之前 |
| 文档基线测试 | 23 passed / 2 failed；tag pending与旧Policy v15断言不同步 | 发布认证前作为显式maintenance子项处理，不隐藏/skip |
| 生产状态 | 本轮没有刷新实盘PG/Binance/systemd | 本计划不声明当前实盘平仓、运行模式或部署资格 |

实施获批后从含全部必要hotfix的已集成基线建立独立 `codex/*` worktree，提交粒度按Task；保留主工作区用户文件。设计分支只交文档。当前生产身份仍只由`docs/current/MAIN_CONTROL_ROADMAP.md`及行动时direct facts拥有。

## 3. Task依赖与统一执行规则

### 3.1 顺序

| Task | 成果 | 依赖 | 完成边界 |
| --- | --- | --- | --- |
| GS-00 | Common/SOR与各策略numeric认证矩阵 | 代码实施授权 | common baseline与每策略PASS/FAIL分开记录 |
| GS-01 | Comparison-transition Episode纯domain | GS-00 common baseline ready | 不能跨comparison继承armed |
| GS-02 | Generic Authority / EMPTY / membership policy纯domain | GS-01 | single/pair/non-trading精确shape |
| GS-03 | Staleness / period / current-close纯domain | GS-02 | grace有界；hourly可交易且无追认 |
| GS-04 | Forward schema与PG保全/约束 | GS-00 common baseline ready；GS-01..03 DONE；被安装Spec各自CERT PASS | 全family schema；只安装合格Spec；Static migration neutrality |
| GS-05 | Generic Selection Plane | GS-04 | 截止于immutable Snapshot handoff |
| GS-06 | Comparison与Episode Observation集成 | GS-04/05 | fixed24及rebase权威生效 |
| GS-07 | Universe targets / Warming materialization | GS-04/05 | targets STAGED，无提前grant |
| GS-08 | Continuity / Vacuum / authority状态机 | GS-03/06/07 | proof先于grant；atomic activate/fallback |
| GS-09 | Signal→Claim→Ticket→dispatch全链 | GS-08 | 四个ENTRY边界不可绕过 |
| GS-10 | Worker hosting / recovery / bounded reads | GS-09 | 三logical lease、公平单warming slot |
| GS-11 | Owner API与Console | GS-08/10 | 策略独立、TOTP与可读进度 |
| GS-12 | ≥24h equivalent churn soak | GS-09..11 | 冻结性能/机会供给门槛通过 |
| GS-13 | Migration rehearsal / release certification /交付 | GS-00 common/SOR PASS；GS-01..12 common及本candidate安装策略路径DONE | generic core R4 + strategy matrix、零生产动作 |

编号是依赖顺序，不强制每张只能有一个commit；前四卡的common/SOR与通用domain条件未完成，不进入Schema。**单个新Selector认证FAIL不等于common baseline FAIL**；后续各卡的共同实现及已通过策略分支可以继续，失败策略分支保持BLOCKED_NOT_INSTALLED。Task的GS编号与设计验收INV编号分开，追踪表见§5。

### 3.2 每卡统一合同

- **Owner**：获实现授权后的主实施者；当前无已委派agent。共享schema、ports、Owner controls不并发写。
- **范围**：每卡允许文件路径为边界，不是授权现在编辑。新生产模块只在`src/trading_kernel/**`；测试在`tests/trading_kernel/**`；migration只在唯一现行Alembic链。
- **RED**：先在生产形状输入上证明失败原因；不能只增加和实现同构的assert或把关键不变量mock掉。
- **GREEN/Refactor**：最小实现关闭本卡边界；删除被替代的错误通用假设，保留SOR-specific测试。中间commit不作为可部署release。
- **Evidence**：记录exact code SHA、测试命令与结果、fixture/source/spec digests、剩余blocker。`PARTIAL/BLOCKED`不标DONE；无测试skip偷过关。
- **统一禁止**：Tokyo写入/部署、生产SQL、exchange writes、自动resume/activation、Feature/N/cadence搜索、资金/ExitProfile扩张、YAML配置、双写或旧schema reader。
- **Done**：卡内证据齐全、相关Fast检查通过、`git diff --check`通过，才进入依赖卡。Release tier只在最终exact candidate跑一次。

### 3.3 Strategy-scoped certification与DAG（P0-PLAN-1）

GS-00输出以下完整矩阵，PASS/FAIL均须有exact candidate、输入及数值合同digest、checked范围、命令和reason；未评估不得伪装成PASS：

```text
COMMON_NUMERIC_AUTHORITY = PASS | FAIL
SOR_GOLDEN = PASS | FAIL
CPM_SPEC_CERT = PASS | FAIL
MPG_SPEC_CERT = PASS | FAIL
MI_SPEC_CERT = PASS | FAIL
BRF2_SPEC_CERT = PASS | FAIL
```

common包含共用输入identity/canonical arithmetic/序列化/确定性和独立expected fixture来源的可信性；若shared输入digest损坏影响全部策略，不能伪称BRF2-only问题。单策略窗口/算法/集合parity失败可以归入该策略。归因必须有证据。

| 结果 | 依赖后果 | 安装/运行后果 |
| --- | --- | --- |
| COMMON FAIL或SOR_GOLDEN FAIL | 整体STOP，不能进入GS-04或release | 不安装新能力 |
| Common/SOR PASS，某新Spec FAIL | common baseline ready；继续common与其他已认证策略的GS-01..13 | 失败Spec不安装、不允许activation；保留该策略原Static行为 |
| Common/SOR PASS，目标Spec PASS | 允许推进该Spec后续实施与认证分支 | 只可安装初始STATIC控制，实盘activation仍独立授权 |
| PG/source neutrality/shared runtime回归FAIL | 共同runtime或该source cutover STOP | 不能用排除单个Selector绕过共享安全失败 |

**能力支持family ≠ 安装某个Spec ≠ 批准activation。** 本Plan选择“不安装失败Spec”方案，不新增看似可用的CERTIFICATION_BLOCKED runtime Spec。失败状态保存在认证证据和只读可用性展示；现有Static StrategyGroup/Universe/交易控制继续保全。API须明确拒绝其Dynamic activation，不能自动补seed、Job或SelectionControl来绕过。

每张卡可分别报告`common=DONE`、各策略`DONE/BLOCKED_NOT_INSTALLED`；失败项始终可见，不称“四策略全通过”。`GS-00_COMMON_BASELINE_READY`要求common/SOR PASS及四个策略评估矩阵已明确记录，并不要求四个SPEC_CERT全PASS。

candidate的installed Spec集合、Spec digests及证据绑定在release freeze前固定，由受审typed installation定义落入PG，不是production读取报告/JSON/YAML、也不是调用方传入跳过认证的开关。更改安装集合建立新candidate，重做受影响的seed/migration/runtime/认证证据。

### 3.4 逐卡SOR回归子集（P1）

会修改共享SOR runtime的GS-02、GS-04、GS-05、GS-07、GS-08、GS-09、GS-10，Done必须包含`relevant SOR Golden / regression subset = PASS`。每卡在修改前固定受影响子集，失败不得拖到GS-13；GS-00/13仍分别保留完整Golden及最终认证，不要求每次小编辑重复全量Release。

| 卡 | 最低相关SOR子集 |
| --- | --- |
| GS-02 | typed pair/EMPTY、旧hash roundtrip、Top7/member policy |
| GS-04 | 0007 SOR lineage preservation、daily/pair约束、无migration新grant |
| GS-05 | 原SelectionCore Golden切片、96×15m/cutoff、source failure |
| GS-07 | LONG/SHORT serial warming、staged无权限、global slot |
| GS-08 | atomic pair、first-close/Gap Audit、Owner-Pause retarget/fallback四类修复 |
| GS-09 | SOR birth authority、Vacuum cancel/partial/unknown、existing Ticket保护 |
| GS-10 | daily 01:00/01:15、三lease恢复、静态短路与SOR调度 |

## 4. Task Cards

### GS-00 — Numeric / semantic authority fixtures

**目标**：把冻结研究和生产数值实现之间的authority差异先暴露出来，避免Schema和runtime写完后才发现BRF2不能保持原Spec。

**允许**：现有selection纯domain及新增typed numeric模块；`tests/trading_kernel/unit/`内numeric fixtures/tests；本地认证工具`verify_*selection*`；设计provenance引用。**禁止**：PG runtime、migration、研究算法/Outcome/report/manifest改写。

**要求与RED**：

1. exact-load Stage-3.1全部冻结输入/cutoff集及manifest，缺源、hash corruption、少一个cutoff必须失败。只允许生成隔离test fixture，不能把研究目录作为production依赖。
2. 研究BRF2 reference按其原math.log/fsum/sqrt二进制合同重建并匹配原Top16 artifacts；生产candidate使用设计Decimal上下文。同cutoff原始输入相同，逐个比较raw Top16，资格过滤前比较。
3. 注入rank16/17边界membership差异，即使aggregate相同也触发`BRF2_NUMERIC_PARITY_GATE=FAIL`；score文字不同但集合一致可通过。
4. CPM/MPG/MI确定性numeric fixtures冻结计算顺序、canonical字符串、ties与undefined行为；不得从candidate反向生成expected ranks。
5. SOR沿用既有961×24 Decimal Golden、语义hash/serialization与1323 diagnostic；证明未来data mutation不影响cutoff前结果。

**验证**：focused pure tests、full frozen BRF2 cutoff parity、SOR Golden integrity、production import architecture。数值parity不是新经济Replay；禁止运行新的Outcome/参数选择。

**Done**：输出§3.3的common/SOR/四策略认证矩阵、完整checked cutoff清单及digests和确定性结果。某Spec的PASS要求其证据完整且0missing；BRF2另要求全部cutoff raw Top16 parity100%。Common/SOR任一FAIL整体STOP；仅BRF2 FAIL时标`BRF2_SPEC_CERT=FAIL / BLOCKED_NOT_INSTALLED`，common baseline ready后允许CPM/MPG/MI及通用GS-01..13继续。失败的BRF2不能被报告成PASS，也不能安装或activation。选择research numeric或新translation Spec仍需另行明确authority，无自动替代方案。

### GS-01 — Comparison-transition Episode contract

**目标**：先解决P0-1；comparison改变不能成为假的自然rising edge。

**允许**：`domain/exposure_episode.py`及pure comparison-transition模型；对应unit tests。**禁止**：schema、PG写面、Detector阈值或Episode key变更、历史rebase服务。

**RED矩阵**：旧ARMED→新comparison首根TRIGGERED；旧TRIGGERED→新comparison；Static rollback；A→B→A；未选中后重入；missing/INVALID；restart；同close不同结果。

**实现合同**：在普通reducer前检查target digest和transition revision。REBASE_REQUIRED时TRIGGERED只观察/抑制；首次valid NOT_TRIGGERED保存target arming proof；严格后续close的TRIGGERED才创建一个Episode。保持原Event/instrument/side key，原Ticket lineage不变；same comparison membership change不重复rebase。

**验证**：`GS-COMP-01`所有分支，NOT_TRIGGERED之前Episode/Signal数为0，之后exactly one；无历史arming token复用。验证连续两根TRIGGERED不发第二Episode。

**Done**：pure状态转移表及typed checkpoint明确，domain无SQL/network/import research；SOR session reducer不受影响。本卡不把unit通过称为runtime已接入。

### GS-02 — Generic Authority / VALID_EMPTY / trusted limits

**目标**：P0-3和trusted membership policy先成为不可表示非法状态的domain合同。

**允许**：`domain/selection_authority.py`、`domain/strategy_universe.py`、typed Spec模型及unit tests。**禁止**：安装migration、让调用者传max_members、在旧pair旁新增第二套authority链。

**RED矩阵**：single LONG、single SHORT、SOR exact pair；缺Event/重复/错side；mixed ACTIVE/EMPTY；EMPTY带Universe、wrong empty digest；0-member Universe；manual11、SOR8、新Dynamic17、伪造Spec/source-kind/max999。

**实现合同**：完整Event bindings。ACTIVE要求real Universe非NULL；EMPTY要求NULL与`selected_member_set_digest(())`，parent区分VALID_EMPTY/stale/Owner pause，不伪造成功Snapshot。非交易first eligible/grant proof为NULL。请求不拥有policy；trusted installed Spec/Generation/source_kind决定actual limit。

**验证**：纯shape/hash/serialization roundtrip；SOR旧交易pair与非交易None的canonical hash无差异；symbol级不合格不补rank17。

**Done**：新的通用表示和SOR subtype边界清楚，无dummy pair，无扩大manual/TradFi/SOR权限。旧错误通用类型的最终替换路径记录，禁止成为永久双读兼容；§3.4相关SOR Golden/regression子集PASS。

### GS-03 — Selection staleness / period clock

**目标**：P0-2与hourly current-final-close在纯domain层可证明。

**允许**：pure Spec clock、selection authority、freshness policy及unit tests。**禁止**：读取系统时间隐藏依赖、生产轮询/DB、改SOR时钟。

**RED矩阵**：

1. 1h/4h首个miss可grace、第二miss及deadline相等时blocked；关闭Coordinator后action time跨deadline仍blocked。
2. fresh不同Desired连续warming失败，source Snapshot仍旧，不能无限续命；NO_CHANGE真正确认才刷新membership来源。
3. 重复tick、重启、epoch前驱变化不重复累计miss、不重置deadline；VALID_EMPTY不恢复旧名单。
4. 新fresh Snapshot不自动清Owner pause；runtime成功可清系统stale抑制；首次Static失败不制造Dynamic source。
5. t Selection→e=t+1h；05:00:08完成但Snapshot已在05:00前提交的fresh未消费close可处理；迟到Snapshot、已消费close、跨commit边界拒绝；SOR仍strict-next-close。

**验证**：table/property tests覆盖每个boundary的`-1/equal/+1ms`，parent proof与source字段不可伪造，grant expiry≤absolute membership deadline；current-close proof不可传入SOR。

**Done**：`GS-STALE-01`、INV-03纯域通过；对每个period有明确cutoff/effective/expiry/source identity/系统blocker，无无界续期或hourly永久零close。

### GS-04 — Forward Schema / PostgreSQL constraints

**目标**：在原authority表上落地已验证domain，保全source逻辑身份。

**允许**：唯一forward migration（起草前核对head）、PG metadata/repository结构、exact source preservation/revision verifier及integration tests。**禁止**：migration内启动Selector、写Job/Snapshot/Generation/Vacuum/Authority parent、运行Owner activation、Tokyo migration。

**RED与要求**：

1. 从production-shaped 0007 source，包括SOR交易与非交易authority、History、empty/pause/fallback、baseline/event lineage升级；source logical manifest逐record还原验证，不只count。
2. pair字段归一化到exact event rows，非交易补EMPTY row；旧semantic hashes不重写。拆除旧day/pair/Top7通用constraint，保留SOR-specific CHECK强度。
3. source current comparison与checkpoint映射不能凭NULL猜armed；迁移不发起comparison transition，也不能因缺provenance在部署后自动rebase。必须通过下述GS-MIG-COMP-01；member limit由trusted FK/constraint检查。
4. parent Spec/Event/side外键、exact event cardinality deferred trigger、ACTIVE/EMPTY状态一致、Digest匹配；攻击事务后必须rollback。
5. Epoch/job/snapshot predecessor、source freshness、comparison checkpoint、唯一open Vacuum、单warming slot、bounded due indexes；role grants按现有Owner API真实role验收。
6. Schema支持全部approved family，但按§3.3仅seed/install策略前置认证PASS的Spec及初始STATIC Selection controls。BRF2 FAIL时不安装其production Selection Spec/control，不改变其已有Static交易控制；SOR current/pending/source lineage保持，无新的pending activation。源若有nonterminal control operation，要求明确quiescence，不删除它来通过。

**GS-MIG-COMP-01 — Static migration neutrality（P0-PLAN-2）**：

在相同Static TradableUniverse、Static ComparisonUniverse、原Episode state且无Owner mode change条件下，对迁移前source和迁移后target重放**相同的第一根及后续合法Observation输入**，分别断言：

```text
Detector input parity = exact
Episode transition parity = exact
Signal creation parity = exact
capability migration causes zero comparison transition / rebase / suppression
```

测试至少覆盖Static MPG ARMED、MPG TRIGGERED、MI ARMED、MI TRIGGERED，交叉覆盖`last_observed_at_ms < current runtime start`和restart。对后续false/true序列校验domain key、Episode ID、armed/triggered状态和时间、Signal创建/不创建与数量；新增provenance字段不得改变原语义字段。不能只验证迁移行数或直接调target新reducer自比。

source expected结果由隔离、可处置的exact0007 reference环境实际取得，与target的同输入结果比较；旧source runner仅用于本地迁移测试，不能成为生产old-schema reader。source provenance必须有可核验的输入/比较成员/版本链，**不能仅凭last_observed早于runtime start、NULL默认值或当前名单相等推定来源**。

任一已有Static MPG/MI scope缺少充分来源证据，source certification返回 **STOP / SOURCE_PROVENANCE_INSUFFICIENT**，在任何目标schema/authority写入前拒绝授权该source升级；不得猜checkpoint、迁移后自动进入REBASE_REQUIRED，或静默改写旧Episode。改变这种行为必须另行明确授权。

此检查覆盖所有已有Static MPG/MI scope，**与该策略的新Selector是否通过认证/是否被安装无关**。即使BRF2-only或CPM-only capability候选，也不能借未安装MPG/MI Selector而跳过共享schema的Static行为保全。

**验证**：空库到head与exact0007升级、GS-MIG-COMP-01、provenance不足源的pre-write拒绝、preservation corruption/非法shape RED、真实PG并发/deferred constraints、权限least privilege；测试BRF2证书FAIL但其余PASS的合法seed集合，以及失败Spec被强行安装时拒绝。

**Done**：forward-only migration及source verifier本地通过，GS-MIG-COMP-01三类exact parity均PASS，缺源STOP可证明；仅安装认证合格Spec，migration无运行副作用；无双写/old-table reader；§3.4相关SOR子集PASS。当前生产操作权限仍NONE。

### GS-05 — Selection Plane / Snapshot handoff

**目标**：每Spec按冻结cutoff产生immutable决定，结束于`SNAPSHOT_READY`。

**允许**：`run_instrument_selection.py`、market ports/adapters、PG Selection jobs/spec/snapshot/member repository、selection unit/integration/architecture tests。**禁止**：Runner读取current Universe、Claim/Ticket、Generation/Vacuum或调用warming。

**RED与要求**：完整24/缺源/未来bar/重复source、compute undefined；每策略独立due；static无pending时零Selector network/job/snapshot。MPG前驱来自Desired Snapshot链，同epoch更早且CAS；runtime failed/staged结果不能改变排名。0..N与valid empty准确分离，四新策略不追加20M或研究外筛选。

**验证**：recording market source+真实PG；网络调用不在事务内；同输入前驱rerun same digest；worker crash/lease expiry/post-commit response loss；fresh source和fresh actual membership不可混淆。

**Done**：同period唯一Snapshot及exact24 member rows、输入digest可回溯；无Universe/Generation/Vacuum/Ticket写入，Selector有独立lease；§3.4相关SOR子集PASS。未安装/认证失败策略不创建Selection Job或Snapshot。

### GS-06 — Comparison / Observation Episode barrier

**目标**：fixed24和GS-01 barrier接入真实producer，不只domain模拟。

**允许**：`project_comparative_universe.py`、`observe_strategy_scope.py`、PG comparison/Episode repository与ports、对应integration/producer tests。**禁止**：缩比较集合、Detector条件变更、给Excluded/STAGED创建可交易Signal、平行Episode键。

**RED与要求**：MPG8h与MI12h使用fixed24；current-close比较key独立于tradable N且不共享错误lookback。原Static保持原comparison；新binding/revision不允许旧armed发Signal。Warm fact、旧cache、same-close false/true不能arm；unselected scope惰性checkpoint、rollback和A→B→A受barrier覆盖。

**验证**：真实Observation entrypoint→PG episode/Signal；先TRIGGERED只suppressed，NOT_TRIGGERED再later TRIGGERED才一次Signal；旧Ticket/退出身份保持。Missing one comparison member必须fail closed，rank3不因排除rank1变成rank1。

**Done**：producer级GS-COMP-01和INV-06/10通过，comparison FK/recording input可回溯；组件fixture不得被误报为完整activation链证据。

### GS-07 — Universe materialization / staged targets

**目标**：generalized Generation精确安装单Event或SOR pair，保持全局单warming slot。

**允许**：install/advance/abandon Universe应用边界、materialization repository/ports及tests。**禁止**：每策略复制warming队列、未通过proof先切current、retire previous后再尝试fallback。

**RED与要求**：target数与Spec一致；schema/domain支持single SHORT，BRF2实际安装路径仅在其SPEC_CERT PASS时可用，未安装时必须拒绝；16-member Dynamic合法但manual11/SOR8非法；请求自报source-kind不能增权。所需facts/certification齐全才能STAGED，全部staged前无positive grant。临时unavailable重试到deadline，timeout不因retry刷新；保留原Vacuum source retarget修复。

**验证**：真实PG+recording venue；全局slot冲突、partial staging、resume/abandon/reclaim、duplicate callback；零warming Signal/Ticket/Command，source eligibility不得从研究数据读。

**Done**：targets可准确STAGED/ABANDONED并恢复，最终activation权限留给GS-08，无incremental warming/carry-forward新设计；§3.4相关SOR子集PASS。

### GS-08 — Continuity / Vacuum / Atomic Authority

**目标**：把前三类domain约束组合成durable新交易authority状态机。

**允许**：materialization coordinator、authority/Vacuum/audit repos、typed proof/ports、Owner pause integration及状态机tests。**禁止**：Network I/O置于DB transaction；不经官方grant直接改Universe current。

**RED与要求**：

1. continuity在Selection outcome之前可执行，且新策略受绝对stale deadline；source失败不直接授权fallback，fresh未生效Desired不能续旧名单。
2. due与future正确区分，global slot就绪后fence；只有snapshot确定后才关闭旧新交易权限。drain确认先于warming，audit/proof先于Observation。
3. fresh target atomically切Event set/comparison/authority/mode/transition revision；SOR LONG成功SHORT失败全组回退。NO_CHANGE不能跳过rebase/stale/未解Vacuum。
4. EMPTY完整Event shape、无零成员Universe，不fallback，旧合法Ticket不追溯撤销；stale/Owner pause EMPTY parent原因明确。
5. firstStatic失败保持mode Static和原comparison checkpoint；已Active后Static rollback是真comparison transition。Owner pause最高，普通fallback不清pause/refresh年龄。
6. 老Vacuum已指向本期Generation则继续materialization；新effective Snapshot、empty、old lease callback、period过期严格supersede；source过期无合法proof保持blocked。

**验证**：PG并发事务/barrier测试+recording network；current-close先consume或先switch两种顺序、crash每个commit点、重试terminal authority；SOR近期四类bug regression。

**Done**：全部新authority可trace proof/source/epoch/Event set，positive grant不能绕过rebase/stale/EMPTY/Owner；existing Ticket未变；§3.4相关SOR子集PASS。

### GS-09 — Signal / Claim / Ticket / ENTRY dispatch

**目标**：所有新入口真实使用GS-08权限，维持既有保护、退出和unknown恢复。

**允许**：Signal admission、CapacityClaim/issuance/submit authority、durable cancel/drain/lifecycle必要接线、integration/full-chain tests。**禁止**：更改资金和退出参数、添加ENTRY generation、直接exchange调用、随名单更换平仓。

**RED与要求**：Claim后switch、Ticket前pause、dispatch前stale deadline、comparison rebase、valid empty；四边界都必须判同一权威。undispatched ENTRY取消；partial仅在现有Vacuum归因/拆分/保护条件下保留，其他按原Incident controlled flatten。Unknown先核对，不能retry重发。

**验证**：从正式Selection/Observation到Ticket/Command的full-chain，不仅直接插入fixture Ticket。保留已暴露Position的Initial Stop/TP1/Runner/Exit/Settlement/Review；cancel unknown和late fill攻击测试。

**Done**：unauthorized Signal/Ticket/dispatch=0、每episode最多一个Ticket、netting独立、已有退出不读取Selector；failures终态和Incident边界可复核；§3.4相关SOR子集PASS。

### GS-10 — Worker hosting / restart / bounded status

**目标**：复用四常驻Worker，三个logical lease独立，恢复不等于重启整个切换。

**允许**：`selection_runtime_worker.py`、`observation_worker.py`、runtime/reconciliation bounded状态读取、status CLI/Owner read repos及tests。**禁止**：新增第五service、periodic cold start、单巨大call stack、runtime全历史扫描。

**RED与要求**：五策略同时due；MPG连续变化/SOR高优先时点；慢请求/429/failover不能starve Safety Worker。显示latest-successful与actual-membership-source两组age，stale mode仍Dynamic；read-only不可创建Job/刷新权限。

**验证**：job/Generation lease独立claim及过期回调、global queue aging、source retry预算、process restart恢复cursor/rebase/stale deadline；healthy cadence零JSON/Markdown输出。暂停一个策略不影响其他策略或已有Ticket。

**Done**：有界读写与独立tick被真实调用证明；三个plane无等待链；静态无pending及未安装Selector短路真实生效；§3.4相关SOR子集PASS。

### GS-11 — Owner API / Console

**目标**：Owner在界面独立控制每策略，看到实际交易权限与等待原因。

**允许**：现有Owner HTTP/application/read models、已tracked Console资产、权限tests与前端测试。启动时先定位tracked前端路径，不触碰主工作区未跟踪`frontend/`。**禁止**：API-only交付、SQL绕过、全局Crypto开关、YAML阈值编辑。

**RED与要求**：STATIC/DYNAMIC预览/激活/回退，typed时间；version/idempotency由UI维护，TOTP在正式应用边界验证。错误step-up不跳登录，401仅真正session失效；409刷新状态但不自动提交新权限。双击/刷新返回同operation。

**验证**：实际role的API integration与浏览器UI测试；每策略independent activation、Owner pause并发、source freshness/deadline/missed-periods、EMPTY原因、comparison rebase状态、MPG12..16说明；不得绿色DYNAMIC掩盖stale或rebase阻断。认证失败未安装策略显示Dynamic不可用，原Static保持，activation被拒且零side effect；不能将“不安装”显示成已认证STATIC Selector。

**Done**：Owner无需curl或手填version即可完成操作并观察active/fallback/stale/pause；TOTP secrets不进入日志，0意外logout；不实际操作生产。

### GS-12 — Hourly churn production-shaped soak

**目标**：量化full-set Warming真实成本，确认小时策略仍有可交易close。保持当前simple materialization架构。

**允许**：本地soak harness、recording source/venue、可处置PG及worker测试、display-only evidence。**禁止**：真实exchange写、为通过测试缩N/cadence、临时加入incremental warming、把业务deadline随加速比例缩放。

**Workload冻结**：

1. 至少连续24h等效正常段，按candidate已认证安装集合冻结：被安装MPG24个hourly periods、MI24、CPM/BRF2各6，包含同期SOR due。固定Candidate24，MPG安装时用冻结rank/hysteresis trace驱动约0.77 additions/removals每小时的变化量级，记录实际change count，不能以全部NO_CHANGE掩盖成本。未安装策略保留Static负载，并验证零Dynamic任务；指标逐策略标明NOT_INSTALLED，不能当成已通过Dynamic soak。不得为躲避soak失败临时删掉已声明安装的策略。
2. 合法source、足够但原Policy边界内的测试账户facts；正式Worker、真实PG、global warming slot、t→t+1延迟、signed command recording。配置snapshot在close前提交，comparison先经过实际rebase流程。控制性设置触发/不触发用于工程验证，不生成经济结论。
3. 独立故障段覆盖长期缺1币、第二miss、fresh不同Desired连续warm失败、cancel unknown、Owner pause、Warming临时失败/timeout、restart、SOR single-leg staged、Static rollback。故障段单独报告，不混进健康p95。
4. 加速逻辑市场时间而非把I/O/事务时延抹掉；冻结recorded request latency/timeout trace，用实际wall-time服务成本测queue/fence latency。施加与部署契约同等的1CPU/1GiB Worker资源预算（PG独立）。不具备等效资源约束时报告性能证据不充分，不用高速开发机直接宣称Tokyo SLO通过。

**八项指标及本Plan预先冻结的健康段通过线**：

| 指标 | 定义 | 通过条件 |
| --- | --- | --- |
| `selection_period_change_rate` | Desired与上一Desired不同的periods / 成功periods | 与冻结workload一致；必须覆盖真实非空changes |
| `generation_rate` | new Generation / due periods | 与状态机预期一致；同snapshot不重复generation，NO_CHANGE不制造generation |
| `p95 queue_wait` | due且可执行到取得global slot的实际等待，报告样本N | ≤300秒；全体健康请求无starvation |
| `p95 fence→grant latency` | 首次fence到合法grant的实际elapsed，deadline不重设 | ≤300秒；所有健康切换在1800秒timeout及period expiry内完成 |
| `vacuum_duty_cycle` | 每策略健康观察区间open Vacuum的时间并集 / 该区间 | 每策略≤10%；报告逻辑时间与实际elapsed计量映射 |
| `NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY rate` | 此原因未激活的due target periods / 健康target periods | =0；各策略至少实际处理一个有权close，不能全程只有计划时间 |
| `selection-caused ENTRY cancellation count` | exact Vacuum归因的ENTRY cancel命令/结果计数 | 等于workload中命中条件的预期数，无重复取消/无unrelated command；已暴露保护不被取消 |
| `missed eligible close count` | 健康数据/控制下因Selection工程延迟未处理的目标Event close数 | =0；逐close ledger，预期rebase抑制/自然NOT_TRIGGERED另列，不能用其掩盖延迟 |

300秒/10%是**本计划提出的工程验收预算**，不来自研究alpha、不表示已测通过；计划复核前公开固定，执行时不得看结果后放宽。恢复/故障段要求stale按精确deadline触发、保护与Reconciliation按原契约推进，不要求故障期间假装零遗漏。

另验证部署契约resource门槛：共享Worker≤1GiB上限、idle memory<80%、代表性idle CPU<10%及原5s/2s/2s/5s cadence、无旧新writer重叠。分别记录正常业务tick延迟与注入网络等待，不将poll间隔错误等同于所有网络操作完成时间。

**Done**：exact workload/candidate/环境身份、八项指标及source/close/command ledger齐全，全部预冻结门槛通过。失败先分析simple架构实现瓶颈；若需carry-forward等架构变化，回设计amendment，不扩大本卡范围。

### GS-13 — Preservation rehearsal / exact release certification

**目标**：把可复核实现收敛成一个本地通过R4的candidate，交付未来部署runbook。

**允许**：release certification/source verifier工具、migration rehearsal/fault tests、当前文档/测试portfolio同步、runbook。**禁止**：维护窗口操作、Tokyo migration/deploy、resume或activation；不把软件PASS写成生产授权。

**准备子项（必须在final freeze之前完成）**：

1. 本地0007 source→唯一target revision；空库与有terminal history、SOR正负authority、comparison/static baseline、pending quiescence案例；logical preservation/reconstruction，corruption/incompatible source拒绝。对所有已有Static MPG/MI scope重复GS-MIG-COMP-01；来源不足必须SOURCE_PROVENANCE_INSUFFICIENT，不能靠部署后rebase保持表面可运行。
2. exact Owner角色权限、STATIC零Job/Snapshot/new Authority parent、无implicit Dynamic activation、兼容restart零Universe warming；升级失败target schema fix-forward，不启动旧schema runtime。
3. 关闭设计§20的两项基线document authority失败：测试从硬编码旧Policy值改为实际合同的可验证结构/一致性；pending tag必须有明确未封版状态，不能被当作sealed release。不能通过改写生产事实、伪造tag、skip或删除有效assert解决。
4. 清理被替代的错误通用day/pair/max10 tests、维护current文档与引用；保留SOR Golden和独特fault覆盖。完成Owner UI/API与新schema源码变化的release classification。
5. 编写stopped-flat部署runbook，明确fresh advisory→停止writers→fresh authoritative facts、source/target证据、quiescence、原SOR状态保全、postflight和失败fix-forward；未来每策略activation单独Owner控制。

**最终freeze与认证**：全部代码、测试、runbook修改提交成exact clean candidate C，然后执行一次完整Unit/Architecture、PG Integration、Full-chain、Ruff、Mypy、diff、Owner API/UI、source preservation/GS-MIG-COMP-01、SOR Golden/Core parity，以及candidate已安装策略的numeric/runtime/GS-12认证。manifest绑定C、schema/Registry/Policy、installed Spec集合及每项数值合同、命令集、输入/artifact digests和未安装原因，不能复用pre-fix candidate结果。

**R4聚合规则**：`generic core R4 PASS + strategy-specific certification matrix`；不要求4/4 Selector通过才可发布Generic capability。安装集合中每个策略的完整前置和runtime证据都必须PASS；未安装BRF2可以保留numeric FAIL/BLOCKED，不把失败改写成PASS，但必须证明其Spec/control未安装、Dynamic activation拒绝且既有Static行为保持。BRF2被安装时，GS-00全frozen cutoffs Top16 parity100%仍是强制gate，不能因common R4通过而豁免。

GS-12 soak若不是C运行，必须证明测试生产面与依赖未变，并由certifier验证规范允许的复用；否则重跑exact C。任何代码/配置/影响测试语义的变化建立新candidate并重跑受影响证据；整套最终认证不能把失败略去。

**Done**：clean candidate C、generic core exact PASS manifest、完整strategy certification/installation矩阵、所有安装策略分支PASS、全部共享runtime与Static migration neutrality PASS。未安装策略的已解释认证失败独立披露，不吞掉shared测试失败。runbook与perstrategy边界明确。认证结果置于既有worktree外release evidence位置，后续纯交付摘要不变更C；不得在认证后改HEAD却宣称manifest仍对同一candidate。

最终仅可声明`GENERIC_CORE_LOCAL_CERTIFIED + exact installed_strategy_set + strategy_certification_matrix / production_authority=NONE`；未安装分支不标实现完成。实际部署、flat facts、Owner activation在后续明确授权动作中处理。

## 5. 设计 → Task 覆盖索引

| 设计不变量 / Review finding | 首次RED/GREEN | PG / Runtime证据 | 最终Gate |
| --- | --- | --- | --- |
| P0-PLAN-1 strategy-scoped certification/DAG | GS-00 common/SOR + perSpec matrix | GS-04合格Spec安装；GS-05..12各策略分支 | GS-13 common R4 + installation/cert matrix |
| P0-PLAN-2 / GS-MIG-COMP-01 Static neutrality | GS-04 source/target differential RED | GS-04/06 preservation及producer | GS-13所有已有Static MPG/MI scope |
| P0-4 / BRF2_NUMERIC_PARITY_GATE | GS-00 | GS-05已认证安装BRF2路径或未安装拒绝 | GS-13安装时exact全cutoff parity，否则显式BLOCKED_NOT_INSTALLED |
| P0-1 / GS-COMP-01 | GS-01 | GS-06/08/09 | GS-12/13 |
| P0-3 / INV-04/08 EMPTY shape | GS-02 | GS-04/08/09 | GS-13 preservation |
| P0-2 / GS-STALE-01 | GS-03 | GS-05/08/09/10 | GS-12/13 |
| P1 trusted limit / INV-05 | GS-02 | GS-04/07/11 | GS-13 |
| INV-01/02 formula/Desired hysteresis | GS-00 | GS-05 | GS-12/13 |
| INV-03 current close | GS-03 | GS-06/08/09 | GS-12 hourly ledger |
| INV-06 comparison24 | GS-00/01 | GS-06 | GS-13 |
| INV-07/11/12 fallback/SOR recovery/crash | GS-02/03 | GS-07/08/10 | GS-13 |
| INV-09/10/13 Ticket/episode/dispatch | GS-01/03 | GS-06/08/09 | GS-12/13 |
| INV-14 fairness/resource | GS-03期限 | GS-10 | GS-12 |
| INV-15 Owner | GS-02/03 authority | GS-11 | GS-13 API/UI |
| INV-16/17 migration/deploy | GS-04 | GS-10/13 | GS-13 |
| INV-18 import/file authority | GS-00 | 每卡architecture检查 | GS-13 |

## 6. 计划审阅与执行终止条件

本轮交付仅为文档，未实际执行GS-00 numeric translation、domain测试开发、migration或soak。独立复核已接受设计、14卡结构与既定soak方向；两项Plan amendment已并入§3.3、GS-00/04/13，非阻塞SOR子集建议并入§3.4及对应Done条件。已批准设计主体不改。

实现后每个策略可以独立STATIC/DYNAMIC，但不能用“独立”绕过未通过该策略numeric、rebase、freshness或runtime Gate。BRF2 mismatch只阻塞其安装/activation分支；common/SOR失败、Static provenance/neutrality失败、preservation失败、shared unknown盲重发、Owner pause被恢复等仍阻塞整体core/source发布。某安装策略hourly无合法close不能被“common PASS”掩盖。

common任务及candidate安装策略的相关分支全部DONE后才能冻结本地release candidate；失败未安装分支须显式列出，不伪造四策略全完成。R4通过也不自动授权生产。

当前 **PLAN_APPROVED / required_plan_amendments=COMPLETE / owner_confirmation=GRANTED_2026-09-07 / implementation_authority=CODE_AND_TEST_ONLY / active_execution_scope=GS-04_TO_GS-13**。GS-00至GS-03的提交、测试与证据已完成；GS-04至GS-13按依赖连续执行。生产部署、Tokyo migration和任何策略 activation继续无授权。
