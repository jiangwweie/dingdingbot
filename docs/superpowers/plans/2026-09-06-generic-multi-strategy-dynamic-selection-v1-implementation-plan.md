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
owner_amendments: ACCEPTED_2026-09-21
---

# Generic Multi-Strategy Dynamic Selection V1 — Implementation Plan

## 1. 目标、权限与来源

**本计划将已批准设计拆成GS-00至GS-13共14张可验收Task Card；当前已经进入获授权的本地代码与测试阶段。** 初始独立复核只允许修订设计与计划，随后Owner明确授予本地实施权限；Tokyo操作、部署或策略activation仍未授权。实际完成度以§2.1证据台账为准。

规范来源为[详细设计](../specs/2026-09-06-generic-multi-strategy-dynamic-selection-v1-design.md)，特别是§4.7、§6.4、§8.4、§10.3四项amendment。设计§18记录条件批准及处理结果；研究出处见设计§19与Stage-3.1 provenance amendment。Task条款不得覆盖冻结Feature、N、cadence、SOR Golden、资金、ExitProfile或Owner控制边界。

```text
design_status = DESIGN_APPROVED / PLAN_ONLY
plan_status = PLAN_APPROVED
implementation_authority = CODE_AND_TEST_ONLY
active_execution_scope = GS-04_TO_GS-13
production_activation_authority = NONE
further_feature_research = CLOSED
```

独立复核已完成并由Owner在本任务明确授权按本计划执行本地代码与测试。GS-00至GS-03已有数值及domain组件证据，但不以早期摘要代替全部Task Done；Owner进一步授权连续完成GS-04至GS-13，当前目标聚焦GS-04至GS-09，在本地完整R4 candidate形成前不再逐卡等待确认。文本中的“执行/实现”是受本计划、Task依赖和Hard Stop约束的本地工作；不授权Tokyo操作、生产migration、部署或策略activation。

针对`4b2947e9f43fb3e2c4f165c91a957e0f20adb632`的独立复核已批准设计，并对Plan给出两项条件。strategy-scoped certification和Static migration neutrality已并入原卡，不新增Task、不修改已批准设计主体。Owner随后明确要求“按文档开始执行开发测试”，故本地实施范围正式开启；执行状态由本文件头和当前Task Card管理。

## 2. 工作区、基线与已知缺口

### Owner amendment（2026-09-21）

本轮接受Owner转交的A～D建议，不重设计架构，不回滚前置工作。当前源码已进入GS-04～09实施，不能按转交建议中的早期时间点重置为“刚进入GS-04”，也不能把GS-00～03的组件证据自动提升为全卡完成。`PLAN_APPROVED / CODE_AND_TEST_ONLY / production_authority=NONE`保持，完成度仍由下面台账及逐卡验收证据决定。

Owner提供的SOR事故链作为回归需求来源，而非本轮重新取得的生产事实：temporary certification被误判永久失败、过早Gap Audit、failed Audit卡住切换。其工程不变量现明确列入GS-07/08。Static migration neutrality、comparison rebase与24h-equivalent soak保持不变；实盘验证不能豁免工程安全验收。

### 2.1 当前实施证据校正（2026-09-21）

#### 1h+范围收缩建议审计（2026-09-21，双时钟已获Owner确认）

最新Owner附件提出以1h+单Event为主线、SOR仅保留兼容与历史保全。此处记录范围方向，不把附件中的“SOR已暂停”当成本轮生产实测事实，不执行pause/retire或删除策略代码。当前已经进入GS-04～09实施，不能回写成“GS-04尚未开始”。

| Amendment | 接受方向／实施边界 | 当前状态 |
| --- | --- | --- |
| AMEND-1 | Common numeric、shared authority、PG/Ticket/history preservation仍整体BLOCK；只有可证明隔离的SOR-specific失败才能标SOR_COMPAT_BLOCKED，不得通过skip把共享失败改名为隔离失败 | 接受分层方向；现有certifier/安装证书仍须显式修订并补隔离测试后才可采用新gate，不能仅凭本段放行 |
| AMEND-2 | 正常切换保留precommitted current-final-close；真正gap/materialization failure/recovery强制future-close-only + Episode rebase，不默认重放缺口 | OWNER_CONFIRMED；以设计§6.2 HOURLY_CLOSE_CONSUMPTION_RULE为准；实现验收尚未完成 |
| AMEND-3 | 300s queue/fence降为warning；timeout不刷新、无starvation、正确cancel、正常路径不漏close及恢复不追认仍为hard gate；vacuum duty阈值未取消 | OWNER_CONFIRMED；GS-12表已修订，禁止后续测后放宽其他硬约束 |
| AMEND-4 | Generic以single LONG/SHORT、1h观察为默认；SOR pair/session/15m为隔离策略subtype；Selection cadence仍CPM/BRF2 4h、MPG/MI 1h | 与既有实现方向一致，不将所有Selection cadence改成1h，不新建第二执行链 |
| AMEND-5 | 薄离线Evidence Contract已列GS-09/13；增加Comparison revision、Claim和terminal reason的明确追踪，默认采用1h closed path并保留同bar歧义 | 接受；不增加在线服务、不要求额外经济研究Gate |

**必须先解决的时钟冲突**：MPG/MI周期为`[t+1h,t+2h)`，现行切换在`e=t+1h`后开始fence/warm。若一律“grant后下一未来close”，例如05:00:08完成却等06:00，06:00已是本period expiry；连续小时切换会没有可交易close。单纯把300s降为warning不能修复此问题；不得自动延长source/Authority有效期、提前warming、降低cadence或从missed-close统计剔除真实遗漏。

Owner已确认：正常切换继续用已预提交Snapshot、最新fresh且未消费close的既有proof；**仅真正authority gap/失败恢复**采用future-close-only + authority-recovery revision rebase，失败period明确记录miss并在后续合法period恢复。其rebase不得伪造Comparison变更，非比较策略CPM/BRF2也必须有恢复身份；首次NOT_TRIGGERED必须来自恢复权限生效后的未来合法close。慢切换不等于gap；是否连续必须由durable transition/cursor/provenance证明，不能只看耗时或由调用方自报。时钟修改的等待解除，按此二分合同继续本地实现；部署继续无授权。

GS-09-LIVE-EVIDENCE-01补充：immutable链明确包括`Comparison revision（不适用策略标NOT_APPLICABLE）→Signal→CapacityClaim→Ticket`、terminal reason和费用/funding来源。1h path只给bar-level first passage；实际entry/exit时间必须用fill，不能把交易发生前的整根bar极值冒充持仓MAE/MFE。entry/exit所在bar缺更细路径时标边界不确定，退出后路径从明确cutoff/horizon观察，不虚构精确先后。

**GS-04～GS-09仍在实施中，未完成、未通过release certification。** 先前对GS-00～03的完成摘要仅对应首版component测试，不足以证明全部Task Done。本轮在继续GS-04时补齐并修复数值来源认证、Decimal排序精度、重复miss/absolute有效期、current-close时点、comparison revision回退与重试幂等问题；不能以旧摘要跳过这些前置。

#### 2026-10-09逐卡验收审计（替代下方早期表格的当前缺口解释）

本轮first Pause恢复末版验证：16项包含pre/post-fence、独立SQL错误Owner proof、整体rollback、幂等与真实future Trigger suppression；相邻首次失败/暂停56 passed。末版文档authority25、Ruff/diff通过，所有verification进程已结束；非完整Generic/非exact R4，不把下一轮Dynamic retry标Done，生产未修改。

2026-10-10 first Static→Dynamic Pause恢复增量（基于`bbd267df`，GS-08）：四策略首次Owner Dynamic intent、immutable Snapshot和DESIRED/DRAINING/warming/staged停点，正式Pause回收为ABANDONED、Resume后经旧Generation Coordinator恢复Static。RED复现NOT_ACTIONABLE永久停住；共享prepare/commit_generic_recovery现仅为exact first Static pending允许ABANDONED源，核对原TOTP Dynamic intent、正式Pause/Resume、已完成Vacuum drain与正确旧Static Event/Comparison/Policy/certification。DESIRED在materialization fence前暂停时不伪造Generation.fenced_at，保留source_generation_id=NULL的真正OwnerPause Vacuum；已post-fence的阶段引用原Generation。独立SQL同时校验pre-state proof和最终Control/Vacuum/Authority/checkpoints，故障注入证明整体回滚，错误failed_activation_authorization_id拒绝。恢复记录FALLBACK_PREVIOUS/static_baseline及AUTHORITY_GAP rebase，旧Generation及目标保持终态，Static Universe/Comparison不变，清pending/epoch；零Dynamic-mode Authority、零Exchange Command。重复old request复用同Authority ID；正式旧Static scope在first future Trigger被RECOVERY_REBASE_REQUIRED抑制且零Signal。16个阶段×策略末版passed，相邻首次失败/pause/DRAINING/warming56 passed；迁移/SOR/Vacuum163、Full-chain51、Unit/Architecture1327、Mypy161 files与Ruff/diff通过。上一轮112分支回归也已终态112 passed（621.03s），不是本轮exact R4。恢复后的新Owner Dynamic排期/新epoch/new target及其Static recovery来源兼容仍未验收，不把恢复Static视为整个retry链完成；prepared实际ENTRY交叉、其他source/epoch/SQL/evidence与逐卡缺口仍保留，无生产修改，GS-04～09未Done。

本轮deferred cleanup末版证据：新增Dynamic warming/staged/DRAINING24与Static/Dynamic DRAINING8（含损坏授权独立SQL/rollback）32 passed；迁移/SOR/Vacuum163 passed、Full-chain51 passed、Unit/Architecture1327 passed、Mypy161 files、末版文档25及Ruff/diff通过。包含旧暂停路径的112分支回归仍在运行，保留原process handle，不重新启动或将未终态进程当PASS；当前证据非完整Generic/非exact R4，GS-04～09仍未Done，无生产修改。

2026-10-10 Pause/Resume均先于cleanup增量（基于`d50737bf`，GS-08）：正式Owner在旧Generation warming/staged/DRAINING时先Pause再Resume，最后才调用Coordinator。RED复现仅看当前enabled状态继续旧TARGET_WARMING，未识别持久化Pause。现Generic Dynamic及Static非终态入口用bounded exact-generation/当前Resume及紧邻Pause的真实授权证明检测尚未cleanup的暂停，回收原目标、清lease并终态ABANDONED；不回写Pause时间，实际cleanup timestamp和Pause/Resume authorization IDs通过cleanup_deferred事件冻结。repository重新验证同一签名序列、generation创建早于Pause和控制时钟；SQL BEFORE ABANDONED event guard独立拒绝伪造Pause ID，整个target/Generation回收事务回滚。Resume早于terminal时恢复/后续drain只能使用exact deferred cleanup证据，不凭enabled或无证明flag放行。四策略×warming/staged/DRAINING×same/different-current24分支及Static/Dynamic DRAINING8分支，末版含SQL corruption/rollback共32 passed；随后最新Snapshot继续正式Recovery/new target/future-close-only rebase，原Generation保持终态。末版Generic migration/SOR/Vacuum163 passed、Full-chain51 passed、Unit/Architecture1327 passed、Mypy161 files、Ruff/diff通过。首次Static pending暂停/恢复、prepared实际ENTRY交叉、第二epochfault/source freshness、控制基线及Static SQL全矩阵、immutable evidence与逐卡认证仍未闭合，无生产修改、非exact R4。前述Resume不得早于terminal/drain只适用于无exact deferred/early completion证据的旧路径，本轮明确补齐正式控制交叉而非放松连续性证明。

本轮early Resume末版：暂停/earlyStatic/实际ENTRY drain矩阵80 passed，包含四策略24项early Resume真实Ticket链及Static/Dynamic无Ticket drain早Resume；旧Generation/目标仍ABANDONED，新非空只Recovery grant，EMPTY不fallback。末版迁移/SOR/Vacuum163 passed、Full-chain51 passed、Unit/Architecture1327 passed、源码+0008 Mypy161 files、文档authority25与Ruff/diff通过，集合重叠不相加。所有本轮verification进程已完成；非完整Generic/非exact R4，GS-04～09未Done，无生产修改。

2026-10-10 early Owner Resume/未完成drain增量（基于`797c425b`，GS-08/09）：四策略natural ENTRY→Pause cleanup/Generation ABANDONED之后，ENTRY仍未取消/partial仍未保护时正式TOTP Resume。RED复现旧Generation Coordinator在Owner enabled时直接NOT_ACTIONABLE、完成drain又要求Owner当前paused，导致Vacuum永久停住。Generic Dynamic与Static ABANDONED入口现在只推进原DRAINING/OWNER_PAUSED Vacuum安全drain，不复活Generation或target、不grant旧Authority。完成时repository对enabled Owner重验exact当前Resume、紧邻前一Pause、正式授权、原Vacuum/ABANDONED来源及时间，附加resumed_before_drain/owner_control_version/owner_resume_authorization_id；SQL BEFORE event guard独立拒绝伪造授权完成记录，rollback保持原Vacuum/Generation/Authority。共享恢复证明仅凭这份exact完结记录才允许Resume早于drained_at，不靠任意enabled状态或布尔flag授予新交易。四策略sent/unknown/partial×EMPTY/非空恢复24 passed；部分成交保护/stress/退出继续仅原Ticket、一ENTRY generation，最新非空目标仍future-close-only+rebase。Static早Resume RED同样复现旧terminal intent停drain；已补旧Static drain-only入口，恢复仍需正式Owner重授权。旧迁移/SOR/Vacuum163 passed、Unit/Architecture1327 passed、Mypy161 files、Ruff/diff通过；末版80分支暂停/earlyStatic/real drain及Full-chain正在回归，未以子集宣称整卡Done。Pause与Resume均发生在cleanup前、首次Static pending暂停及prepared交叉仍需核对；其他卡级缺口不变，无生产修改，非exact R4。

本轮generation-free恢复末版：28项新矩阵passed；旧unfenced/DRAINING/warming/staged/连续接管88 passed；Generic migration/SOR/Vacuum163 passed、Full-chain51 passed、Unit/Architecture1327 passed、源码+0008 Mypy161 files、末版文档authority25与Ruff/diff通过。集合重叠不相加；首次Static pending下Pause、Resume早于drain完成、prepared真实有单交叉及其余卡级要求仍未闭合，GS-04～09未Done、非exact R4。原462全模块已终止为462 passed、1967.32s，但不能绑定当前源码，所有verification进程已完成，无生产修改。

2026-10-10 generation-free Owner Pause非空恢复增量（基于`dba0446e`，GS-08）：正式Active Dynamic且尚无待切换Generation时Owner Pause创建OPEN Vacuum，经正式drain至OWNER_PAUSED，再TOTP Resume、下一effective Snapshot；RED复现Coordinator以source_generation_id=NULL直接BLOCKED。复用retarget_generic_gap_vacuum_with_generation，不建立第二队列/Authority链；OWNER_PAUSE_NO_GENERATION事件冻结原source Authority/原Vacuum和新Generation，原时间保全，新Generation只获得自己的materialization deadline。共用SQL resume证明核对OPEN OwnerPause来源、JSON booltrue完结事件、Pause/Resume连续版本及授权、Spec/epoch/control、source创建早于Pause、Resume不早于drain；同名单也不能NO_CHANGE清fence。恢复preparation和独立PG proof验算识别该source类型，原静态/有Generation路径保持；无Recovery Authority直接把Vacuum置RESOLVED_ACTIVE被数据库拒绝。四策略×same/different成员×normal/false/string加原CPM/BRF2 gap，共28 passed；false/string在绕过Python proof时独立SQL BEFORE handoff仍拒绝，原Vacuum/current与零新Generation保全。正向完成warming/staged/atomic new current、future-close-only rebase、重复request同Authority，首个未来TRIGGERED无Signal；MPG/MI使用完整fixed24比较缓存并保留实际revision。Unit/Architecture1327 passed、源码+0008 Mypy161 files、Generic migration/SOR/Vacuum163 passed、Ruff/diff通过；旧unfenced/DRAINING/有Generation接管88分支回归仍在运行。原全模块462 passed、零skip、1967.32s，但运行中source变更，不绑定末版exact candidate或R4。prepared等剩余交叉、第二epochfault/source边界、Static全SQL攻击、immutable evidence与逐卡认证仍未完成，无生产修改。

本轮paused DRAINING非空恢复末版：完整latest接管56分支passed（含旧warming/staged32、DRAINING正向8及false/string独立SQL攻击16）；真实ENTRY非空恢复12 passed、相邻EMPTY/real-drain/warming28 passed，集合重叠不相加。Generic migration/SOR materialization/ENTRY Vacuum163 passed、Full-chain51 passed、Unit/Architecture1327 passed、源码+0008 Mypy161 files、最终文档25及Ruff/diff通过。旧462全模块进程仍在运行且本轮源码变化，不作为末版exact candidate或R4；GS-04～09未Done，无生产修改。

2026-10-10 paused DRAINING非空恢复增量（基于`df70dbc7`，GS-08/09）：既有latest非空接管矩阵增加四策略DRAINING阶段Pause→ABANDONED→next tick正式drain→Resume→新Desired；RED复现共享brc_generic_vacuum_owner_resume_matches仍仅认warming/staged的OWNER_PAUSED同terminal来源。SQL函数现同时核对OWNER_PAUSE_REQUESTED同ABANDONED timestamp与完成OWNER_PAUSED=drained_at、JSON booltrue；Resume必须不早于terminal及drain二者，原fence/drain与旧终态保持。8个新DRAINING same/different-current分支正向通过；false/string损坏证明不仅被Python拒绝，还在刻意绕过Python scalar proof时被独立SQL BEFORE handoff拒绝，全事务回滚且无新Generation。完整warming/staged/DRAINING与连续接管56分支仍在收尾，不将先前8项当整卡Done。

同轮实际有单非空恢复：四策略natural ENTRY accepted→新Desired/更新Desired→Pause→exact cancel/unknown reconciliation/partial protection→完成drain→Resume，不再只以EMPTY结束，最新非空Desired继续正式warming/staged/ACTIVE_NEW。Recovery proof为AUTHORITY_GAP、first eligible严格未来且必须Episode rebase；原Generation保持ABANDONED，原Ticket不可变/仅一ENTRY generation，partial仍沿旧Ticket完成保护、退出、flat/Settlement/Review。三类sent/unknown/partial×四策略12 passed；MPG/MI用正式hourly comparison自然Signal/Runner而非手造Signal。相邻EMPTY/real-drain/warming28 passed、Full-chain51 passed、Unit/Architecture1327 passed、Mypy161 files及Ruff/diff通过；163项迁移/SOR/Vacuum回归仍在执行。generation-free非空pause恢复、prepared及其他交叉、第二epochfault/source freshness、Static SQL全矩阵、immutable evidence合同和逐卡认证仍未闭合，无生产修改、非exact R4。

本轮real-drain暂停末版：共享helper相邻26分支（CPM/BRF2原latest非空及10项Pause，MPG/MI 10项Pause）26 passed；72项相邻暂停/自然链组合在最终rank夹具修正前通过，不当成末版替代证据。由于Selection先做固定横截面排序再qualification，旧集合外qualified标的可能仍rank>TopN，初版夹具EMPTY失败；现CPM/BRF2用rank内单成员改变集合，MPG/MI用另一singleton且固定合法rank几何，不改变算法或backfill。源码/0008的163项迁移/SOR/Vacuum、Full-chain51、Unit/Architecture1327、Mypy161 files、最终文档25与Ruff/diff通过。测试集合重叠不相加，完整462进程仍在运行且非末版exact R4，无生产修改。

2026-10-10 real ENTRY drain中Owner Pause恢复增量（基于`4f9b6aa6`，GS-08/09）：四策略从正式Owner/Runner/natural producer产生Signal/Claim/Ticket/accepted ENTRY。新非空Desired在DRAINING阶段到达、更晚latest EMPTY提交；正式Pause使原Generation ABANDONED、lease清除但保留原Vacuum/ENTRY，随后unknown CANCEL不重发，exact order absence后二次position proof确认零成交或实际partial。partial在Owner Pause期间仍经durable INITIAL_STOP及actual-quantity stress保护，不释放其Reservation/Domain，后续同旧Generation Coordinator完成paused drain；Resume后最新EMPTY接管原Vacuum、无fallback、旧Generation不复活。RED复现原empty retarget只认warming/staged先drain后abandon，拒绝真实DRAINING先abandon后drain；Python和0008独立SQL现额外只接受OWNER_PAUSE_REQUESTED与ABANDONED同timestamp、完成OWNER_PAUSED恰等于drained_at且entry_drain_complete为JSON布尔true。false与字符串true的真实完结事件分别使repository/直接SQL handoff拒绝并全回滚，原负向Vacuum/current/history保留。CPM/BRF2十分支、MPG/MI十个正式hourly comparison producer分支各10 passed；MPG/MI经过自然comparison arm及Runner后续Snapshot，不伪造Signal。初版比较夹具选择相同singleton导致NO_CHANGE/无Vacuum，现MPG/MI singleton场景选择不同qualified成员并固定合法rank几何，CPM/BRF2保留rank内的单成员新集合，修正fixture而非强行fence。相邻Generic migration/SOR materialization/ENTRY Vacuum163 passed、Full-chain51 passed、Unit/Architecture1327 passed、Mypy161 files与Ruff/diff通过；共享helper末版相邻26分支正在复验。462项完整模块仍在运行且本轮修改了source，不能冒称末版exact candidate。generation-free/DRAINING非空恢复、prepared及其他pause交叉、第二epoch故障/source边界、Static SQL全矩阵与逐卡认证仍未完成；GS-04～09未Done，无生产修改。

本轮positive替换拒绝末版补验：Claim→Ticket四策略的claim零持久化断言4 passed；activated12与完整32矩阵重叠，不重复相加。最终文档authority25 passed、Ruff/diff通过；没有重跑全Unit/Mypy或exact R4（本轮tests/docs-only），全卡状态仍未完成。

2026-10-10 positive current替换后旧Signal/Claim拒绝增量（基于`1fa338c3`，GS-09）：正式Owner→Runner→首Dynamic→PRE_FENCE_CONTINUITY→自然Signal链扩展到四策略；MPG/MI用真实initial NOT_TRIGGERED完成comparison arm，fixed24 cache让交易成员成为rank leader，不以改checkpoint伪造Signal。三条activated分支分别在Claim前、Claim计算到Ticket签发之间、prepared ENTRY派发前，经正式Coordinator完成新Universe warming/staged/ACTIVE_NEW。新current已替换且Vacuum已解除，旧Signal/Claim仍未过期，旧scope/birth拒绝并零新Ticket；prepared ENTRY先由原正式drain supersede，确认原Reservation/Domain释放、原Ticket冻结字段不变及零position，再允许新Universe接管，之后dispatch为NO_COMMAND且零venue execute、一条ENTRY generation。目标成员与旧交易成员不同，避免用已消费close伪造正常新grant；不是证明可在claimed/unknown命令尚未drain时强行切current。与原Vacuum fence/dispatch-facts交叉扩至四策略共32 passed，末版activated12 passed；最终claim零持久化断言单独重验进行中。既有Full-chain/文档76 passed，Ruff/diff通过，仅tests/docs变化，无生产修改。原全Generic424项进程最终424 passed、零skip、1740.03s；从407f00d2启动后源码/迁移有增量，不能绑定当前exact candidate或作为R4。仍需generation-free/DRAINING非空pause恢复、有真实ENTRY的pause、第二epoch故障/source freshness、Static完整SQL攻击与逐卡验收；GS-04～09未Done。

本轮positive replacement竞态末版：四策略×Trigger/NotTriggered×activation-before-read/read-before-activation的16分支，与既有两种NO_CHANGE提交顺序8分支合计24 passed；实际PG blocking证据、旧Facts/Episode不变、新scope当前close可消费及comparison屏障均已assert。相邻Recovery/NO_CHANGE组合28 passed为增加反向提交顺序及NotTriggered之前的测试集合，不重复相加。末版证据仍非完整Generic模块或exact R4。

2026-10-10 positive replacement与Observation竞态增量（基于`407f00d2`，GS-06/08/09）：正式firstDynamic后在下一period建立PRE_FENCE_CONTINUITY，旧Observation在初始读取事务提交后暂停；Coordinator正常fence/drain/warming/staged/ACTIVE_NEW完成，再释放旧Observation。RED证明旧Signal虽被拒，旧Facts/Episode已先写入并消费新current的同close。Generic NORMAL现在与Recovery一样在第二事务先按Owner→Control→current→Episode顺序重验，再写Facts/cursor；Market I/O保持事务外，SOR普通路径未扩展该行为。另RED暴露0008 ACTIVE_NEW把普通continuity的continued_from_selection_authority_id误当recovery origin；SQL改为从continuity current_close_proof.origin_recovery_authority_id读取，真正Recovery仍要求exact armed provenance。反向顺序在activation transaction已写但未commit时启动旧scope Observation，用pg_blocking_pids证明等待真实writer，commit后拒绝旧scope；新scope继续消费同一个NORMAL first close，CPM/BRF2发新birth Signal，MPG/MI仍受comparison rebase。四策略×两种顺序8分支已通过；末版另增加Trigger/NotTriggered，要求旧Facts与Episode均不变，收尾24分支含已有NO_CHANGE并发矩阵正在执行。相邻Observation/Generic migration/SOR materialization118 passed、正式Static/二次Dynamic20 passed、Full-chain51 passed、Unit/Architecture1327 passed、Mypy161 files、Ruff/diff通过。完整424项Generic进程仍是407f00d2启动时的代码证据，不能冒称末版full-module或R4。旧Signal/Claim issuance/dispatch失效、generation-free非空pause恢复、有真实ENTRY的pause及逐卡验收仍未闭合，无生产修改。

本轮paused非空末版验证：32分支包含篡改handoff来源的独立SQL拒绝、rollback、same/different-current与连续接管，32 passed；与warming/staged EMPTY组合40 passed（重叠不相加）。Generic migration/SOR materialization/ENTRY Vacuum完整三模块163 passed、Full-chain51 passed、Unit/Architecture1327 passed、Mypy161 files、document authority25 passed、Ruff/diff通过。无skip，但不是末版完整Generic模块或exact R4；逐卡未完成状态不变。

2026-10-10 paused warming/staged非空接管增量（基于`5d94136e`）：四策略正式Dynamic→第二Generation warming/staged→Owner Pause回收→正式TOTP Resume→最新非空Snapshot接管原Vacuum；旧Generation保持ABANDONED，目标保持abandoned，原fence/drain时间不重置，新目标独立deadline。恢复proof以OWNER_PAUSE标记该来源并沿future-close-only+rebase，不使用NORMAL追认过去close。原Authority的Owner version保留历史值，只有同Vacuum已完成drain、精确ABANDONED/OwnerPause事实、当前resume与其前一pause的连续control version、正式授权及当前历史source完整匹配，才允许新Recovery Authority使用当前Owner version；不修改历史Authority。独立SQL BEFORE guard校验latest nonempty Desired及handoff来源；恢复proof函数再次核验，伪造source/未来resume/旧Owner version拒绝。测试扩展same/different-current名单、warming/staged、pause/no-pause与连续第二次接管，共32分支，初版先复现BLOCKED后补齐正式链；末版篡改materialization handoff metadata攻击及相关EMPTY回归正在执行，结果以随后追加证据为准。Full-chain51 passed、Unit/Architecture1327 passed、源码+0008 Mypy161 files、Ruff/diff通过。generation-free/DRAINING非空恢复、有真实ENTRY的pause交叉、positive activation并发与卡级认证仍未闭合；GS-04～09未Done、非exact R4，无生产修改。

2026-10-10 EMPTY接管末版验证：Generic/历史SOR migration、SOR materialization、ENTRY Vacuum四模块完整组合168 passed（修正前167 passed+1 frozen-schema fixture FAIL）；warming/staged pause→resume→EMPTY包含两类独立SQL攻击、rollback和终态重复请求same Authority ID，末版8 passed。generation-free pause/authority-gap EMPTY相关组合26 passed与本组重叠，不相加。Full-chain51 passed、Unit/Architecture1327 passed、源码与0008 Mypy161 files、document authority25 passed、Ruff/diff通过。此为局部修复证据，不是GS-04～09整卡认证或exact R4。

以下审计基于tracked source与正式入口tests，不把测试名或历史PASS摘要直接提升为Done。GS-04～09的本地卡级验收与GS-10～13的hosting/API/soak/最终R4交付分开，后者仍在完整计划内。

| 卡 | 当前可定位的实现／证据 | 尚需闭合的明确要求 |
| --- | --- | --- |
| GS-04 | `0008` source logical preservation、Static MPG/MI exact0007 producer差分、terminal/FALLBACK/EMPTY/pause保全、Owner role ACL、Spec失败拒绝、Event/epoch/deferred攻击已有真实PG测试；首次Generic授权实际Static rollback来源捕获和独立PG摘要验算已补 | 对全部显式约束与权限作卡级核对；既有低层epoch夹具不能代替Owner/完整回退入口验收 |
| GS-05 | 四策略Runner→immutable24-member Snapshot、缺源/未来/qualification、三次temporary retry、EXPIRED/SUPERSEDED、lease reclaim、response-loss幂等均有正式PG入口；Generic事务外I/O/禁止读交易面/Static及未安装短路、错误epoch隔离已重验 | 完整卡级命令/要求映射与SOR Core input parity复核；五策略resident due调度属于GS-10，不以Runner测试宣称hosting完成 |
| GS-06 | fixed24 production Observation、独立comparison cache身份、A→B→A/revision、未观察成员重入、首TRIGGERED抑制→NOT_TRIGGERED→后TRIGGERED已存在；Static recovery到Signal、连续Static NORMAL当前close消费/comparison屏障、再次Dynamic epoch/比较revision、NO_CHANGE consume/grant真实并发均有证据 | 第二次Dynamic后自然producer/入场fault、完整正常Static后续新ENTRY与全矩阵逐项核对仍需闭合 |
| GS-07 | single LONG/SHORT与SOR pair目标、trusted16/10/7 limits、global slot、staged无交易权限、retry不刷新deadline及事故路径真实Coordinator tests已有 | 卡级slot/lease/abandon/恢复及SOR子集全矩阵核对，不能仅用单次成功路径声明Done |
| GS-08 | ACTIVE_NEW/NO_CHANGE/VALID_EMPTY、firstStatic失败、future recovery、目标多阶段接管/同Vacuum历史保全已有PG证据；Static原子activation/rebase及二次epoch、所有末尾clock回滚、MPG/MI独立hour-only与8/30/120s正常延迟、有protected Ticket成功/timeout、warming/staged Pause回收、terminal重授权/连续失败恢复、Static SQL unarmed/armed/NO_CHANGE provenance以及四策略NO_CHANGE并发已验证 | Static完整source/lease/cursor独立攻击、非comparative独立hour-only补足、第二Dynamic自然入场、unfenced/DRAINING pause/恢复交叉、非NO_CHANGE atomic activation并发、更多partial/unknown/有仓交叉和整卡认证仍需闭合 |
| GS-09 | 四策略自然Selection→Signal→Claim/Ticket→durableENTRY→terminal、EMPTY/Static切换及timeout后的protected Ticket安全链、Unknown/partial/late-fill闭环已有证据；CPM/BRF2三段pause/freshness拒绝、正式nonempty Vacuum的claim/dispatch竞态及四策略Claim前stale拒绝已验证 | 新Universe current替换后的旧Signal/Claim全部矩阵、剩余source freshness和新Static/第二Dynamic自然ENTRY、最小immutable证据合同及整卡验收仍需核对，不把Vacuum fence等同positive current替换 |

本审计不重开Feature/经济研究，不执行生产操作。已终态Ticket后出现不可归因外部Exposure的既有账户Incident/Owner containment属于明确fail-closed边界，不通过复活terminal Ticket或新增平行订单链伪造自动恢复。

2026-10-10 paused warming/staged至最新EMPTY接管增量（基于`755efdc3`）：新增四策略×warming/staged正式Owner Pause→resume→latest VALID_EMPTY入口先复现8 FAIL。共享empty retarget现允许具备精确原ENTRY_DRAINED、Owner Pause/Generation ABANDONED事件、同Spec/epoch/period、无lease/非abandoned目标/待drain Ticket的终态Dynamic源；不将ABANDONED改成SUPERSEDED，不复活旧目标，不重置原Vacuum fence/drain时间。0008 BEFORE guard独立验算同一来源和最新empty intent，并保留deferred原子negative Authority约束；篡改supersedes_owner_pause或只写终态Vacuum均使整事务回滚。相关pause/generation-free/authority-gap EMPTY组合26 passed；末版8分支再次通过，既有Full-chain51 passed、Unit/Architecture1327 passed。迁移组合同时暴露历史0006测试调用当前0008 repository而缺selection_epoch_id；改为exact0006 SQL验证Static mode、无pending授权及version=1，保持0005→0006 preservation/zero work全部断言，当前Schema正式Owner activation测试不删除。历史迁移模块单独5 passed。非空恢复接管、有真实ENTRY的pause交叉及卡级全矩阵仍未闭合；不宣称GS-04～09 Done或exact R4，无生产修改。

2026-10-09整模块重验（基于`b532e8f8`）：`pytest tests/trading_kernel/integration/test_generic_selection_snapshot_repository.py -q --tb=short --maxfail=3`完整358 passed、零skip，耗时1015.57s；本次没有用-k子集替代整模块，也不是最终Release tier。相邻Generic migration/Comparison/Observation/Universe install/eligibility/warming/activation-fault组合初轮68 passed+1 FAIL，原eligibility夹具在head库里仍冻结0007 capability schema，按CURRENT_SCHEMA_REVISION修正后末版69 passed；历史portfolio migration模块原head断言仍0007，明确更新为0008，冻结0003 target未变，末版22 passed。Unit/Architecture1327 passed；SOR Golden artifact integrity verified（961 Snapshot、23064 member rows、artifact_set_digest=sha256:5d8c701d2738daebc506921038b2afb5a8feeda4a25d9652866c9b41743d4e45），此命令未带raw cache/input flags，不能声称本轮重建Production Core raw-input parity。当前表已将此前closed切片移动至证据栏并保留实际未完成要求。仅tests/docs改动，Ruff、document authority25 passed、diff通过；集合重叠不合计，不标GS-04～09 Done/R4 PASS，无生产修改。

2026-10-09未完成非空目标接管增量（基于`a1d7fbd3`）：真实首次Owner授权、Selection Runner与Dynamic激活后，第二期目标停在MATERIALIZING/warming或STAGED；下一有效非空Snapshot通过同一Coordinator及repository事务abandon原目标、终态SUPERSEDED原Generation、取消原lease并接管同一已drained Vacuum。旧Active Universe与Authority不变，原Vacuum fence/drain时间不重置；新Generation有自己的有界materialization预算。新名单与旧Active相同也不能用NO_CHANGE绕过未解除围栏。连续第二次接管不再错误要求上一Generation的fence等于最初Vacuum fence。数据库恢复proof独立区分真实FAILED_CLOSED与UNFINISHED_MATERIALIZATION supersession，不制造失败事件；恢复激活沿原future-close-only与Episode rebase合同，不追认过去close。四策略×same/different-current-members×warming/staged的16分支覆盖提交前回滚、旧callback拒绝、连续接管、原timestamp保全、完整恢复proof/SQL验算/正式activation；这些包含在相关恢复与EMPTY组合40 passed中，不重复相加。Generic migration与SOR materialization99 passed、既有Full-chain51 passed、Unit/Architecture1315 passed、Mypy206 files、相关Ruff与diff通过。全部为本地Docker PG及recording venue；不构成exact R4或GS-08整卡Done，DESIRED/drain阶段接管、真实Static rollback及其余审计项仍未闭合。

2026-10-09早期目标接管增量（基于`ffca6506`）：四策略通过真实首次Owner授权/Runner/activation后，把下一Generation停在DESIRED或DRAINING_ENTRY，再提交更新非空Snapshot。未围栏PENDING/DESIRED在同一outcome事务被SUPERSEDED、原lease清除；已围栏但未完成drain时，最新Snapshot Coordinator只推进原正式drain，确认完成后再调用现有已drained retarget，不安装旧目标、不重置原fence、不授予新Authority。Owner pause及提交前故障均保留源状态。另复现CPM合法PRE_FENCE_CONTINUITY下最新NO_CHANGE已提交却遗留旧DESIRED的问题；NO_CHANGE、VALID_EMPTY和新Generation统一复用有界unfenced supersession。`0008` deferred guard独立拒绝新NO_CHANGE/EMPTY仍遗留旧actionable Generation，省略应用清理的故障测试为RED后转绿，不仅依赖Python。CPM LONG/BRF2 SHORT正式Observation→Claim/Ticket→唯一ENTRY派发后，第三期非空Runner结果到来时仍有原ENTRY未成交；Coordinator保持原DRAINING_ENTRY、零新target，原CANCEL准备期间继续等待，正式CANCEL接受及fresh双次零成交证明之后才沿同一Vacuum接管，Ticket frozen lineage及Reservation/Netting Domain终态释放不变。最新选择与原unknown/partial/protection等待的组合矩阵仍须补足，不能用existing drain用例替代该交叉证据。相关Generic状态机77 passed；Generic migration/SOR materialization/完整Entry Vacuum163 passed；Unit/Architecture1315 passed、Mypy206 files、Ruff/diff通过；最终focused early/NO_CHANGE/EMPTY/自然有单12分支重验。测试全部使用Docker PG与recording venue，无生产修改，不构成exact R4或GS-08整卡Done。真实Static rollback、consume/grant并发与其余GS逐卡验收继续未完成。

2026-10-09自然有单接管故障增量（基于`11cf6fb4`）：复用已有正式首次Owner→Runner→Observation→Claim/Ticket→durable ENTRY夹具，CPM LONG与BRF2 SHORT加入第三期非空Selection到来时的CANCEL unknown及partial-fill分支。unknown路径由recording venue在真实durable CLAIMED后丢失响应；Coordinator保持原Vacuum、旧Active/Authority、零新Generation/target，dispatcher再次调用为NO_COMMAND且venue调用数不增加。正式`recover_unknown_command`携带exact原取消订单、instrument/account/side，取得目标消失truth后才推进双次fresh零仓位确认，原Ticket终态释放占用并接管同一Vacuum，无第二ENTRY。partial路径保留原成交量、取消剩余；在PROTECTION_PENDING和POST_FILL_RISK_PENDING分别验证Coordinator仍等待，原Initial Stop及实际partial quantity的本地stress evidence完成后才允许retarget。原Ticket随后使用actual tp1_target_qty经TP1/Runner/外部flat、cleanup、Settlement与Review到TERMINAL；Reservation/Netting Domain/Incident闭合，出生Authority/Initial Stop/Profile/Ticket数量计划不重写、ENTRY generation仍唯一。风险输入、flat和Review数值均为本地fixture，不是实盘或经济结论。本次仅更新test/evidence、不修改production源码。接管/自然入口组合36 passed，完整自然入口12 passed；末版partial stress输入/terminal扩展4分支重验通过，原unknown/retained partial15 passed，Unit/Architecture1315 passed、Ruff/diff通过。计数重叠不相加，且不构成exact R4或GS-08/09整卡Done；Static rollback、MPG/MI交叉路径、入场fault矩阵及逐卡审计继续未完成。

2026-10-09Static rollback排期入口增量（基于`400d02f8`）：新增正式`stage_generic_static_selection_mode` application，要求exact current Dynamic epoch、固定rollback baseline、Control CAS版本、下一合法cutoff、reason/idempotency及TOTP Owner proof；同事务写authorization和现有Control pending字段，不创建Snapshot/Generation/Vacuum/Universe/Command，不复活retired Static source，不改变旧Active/Authority。未来intent的排期保留当前有效selection_control_version，pending与非重复请求通过Control row lock/条件UPDATE串行化；最终runtime围栏/activation负责后续版本变化。这样不能仅因排期就立即让旧birth-authority失效；该有效版本/未来pending边界为runtime实现细化，不是交易权限扩张。四策略正式Dynamic后独立读回source/pending、错误version/epoch/baseline/period/step-up拒绝、提交前故障回滚、重复幂等、两个相同或不同请求并发只有一个Owner fact；数据库独立验证Static target scope/冻结来源/原epoch/下个period，借旧Dynamic proof及篡改period均失败。MPG/MI复现future Static intent误挡此前合法PRE_FENCE_CONTINUITY，统一纯`permits_dynamic_period`判定及SQL proof边界后转绿；指定Static cutoff起Dynamic Job、Continuity及Snapshot handoff不能继续，直接SQL伪造新Dynamic VALID_EMPTY Authority也被deferred约束拒绝。最终相关Generic/Owner/Continuity/natural-entry组合46 passed、Generic migration/SOR materialization99 passed、Unit/Architecture1315 passed、Mypy206 files、Ruff/diff通过；首轮四处测试模型漏填nullable proof字段的失败已修正并重跑完整46项，不把旧失败运行当PASS。全部Docker PG，production_authority=NONE。**这只是Static rollback的授权/排期段，不是完整回退**：typed Static Generation、新Universe warming/certification、原子comparison/mode/authority/epoch转换及实际rebase仍须完成；Owner API/UI属于GS-11后续接线，不能把排期成功称作Static交易已恢复。

Static排期末版时间补强：在完成46项回归后，新RED证明请求时间小于Control.updated_at仍能排期。application与`0008` Static proof trigger均拒绝time moved backwards；末版四策略排期、双并发、MPG/MI Continuity共8分支复验，Ruff、受影响Mypy及diff检查。该补强不改变合法周期或有效Authority版本；46/99/1315为之前同一切片的广范围证据，不把它们冒充末版exact R4。

2026-10-09Static Generation source增量（基于`bbb46b1c`）：同一`coordinate_selection_materialization_once`增加仅StrategyGroup/worker ID的Static Owner request，exact-load当前pending proof并在其`t+1h`生效后创建PENDING Static Generation，早到NOT_DUE、Owner Pause不创建。新增frozen typed Static source模型，复用现有Generation parent、previous Event rows、target digest和第一条PENDING event；来源为Owner authorization+rollback baseline，`selection_snapshot_id/period_anchor_ms`保持NULL，真正effective period从原immutable Owner/PENDING lineage读取，不伪造Selector Snapshot，不复制成员，不新增table/service。repository冻结实际当前Universe/member/comparison及原epoch/control、从retired Static source exact-load1..10 target members；重复Owner intent不增加事件，真实commit后重读同源digest。0008独立重算Generation ID、canonical source digest、原Owner scope/时间与baseline/member来源，校验PENDING当前Owner/Control/previous Universe/comparison；伪造Python digest、遗漏首条source event、修改冻结parent均拒绝，提交前故障全部回滚。修正一个测试直接INSERT未列物理列导致的datatype failure后，独立缺源用例为真正DID_NOT_RAISE RED，再加DB guard转绿。SQL JSON `:null`被SQLAlchemy误当bind的问题仅发生于本地migration rehearsal，改为分段字面量后head rebuild通过。相关Owner/Static/Dynamic activation20 passed、Generic migration/SOR materialization99 passed、Unit/Architecture1319 passed、Mypy206 files及Ruff/diff通过；末版source event occurred_at绑定created_at后的四策略focused复验。**本段不是完整Static Materialization成功**：当前正式入口只完成PENDING durable source；DESIRED/fence/drain、共享warming slot上的新Static Universe、staged certification、failure/supersession、原子mode/comparison/authority/epoch及rebase仍须继续实现。生产未修改，不构成GS-08整卡Done或R4。

2026-10-09Static Generation preparation/staging增量（基于`e968ada7`）：正式Static Coordinator在同一materialization plane推进PENDING→DESIRED→DRAINING_ENTRY→MATERIALIZING→新Static Universe warming→STAGED。共用原Generation lease字段/epoch、Vacuum/open/drain函数、global install/warming slot及certification/staging，不建第二queue/取消链/成员权威；Static source codec提供原immutable Owner effective period，物理Generation.period仍NULL，Vacuum保存合法原period。每次claim/write核对当前Owner/Control/baseline/epoch/previous Universe/comparison，lease holder及错误token拒绝，正常tick释放相同fenced token；提交前fence/staging故障通过正式UoW全回滚。新目标UUID与retired baseline/旧Dynamic均不同，成员exact-load baseline并校验原digest，原Current/Authority/Control直到STAGED仍不切换；MPG/MI warming使用原Static集合的独立比较缓存。临时certification保持retry、不重置fenced_at/deadline；非transient原因不标retryable。正式Owner Pause后Coordinator无新动作/无grant。Static staging仅允许Generic来源，SOR路径保持原限制。首次广范围运行因新增previous-source检查误放到create函数而出现四处UnboundLocalError，已移动到正确current-check边界并完整重跑36 passed；共享Generic migration/SOR materialization/Entry Vacuum163 passed、Unit/Architecture1319 passed、Mypy206 files、Ruff/diff通过，末版四策略含lease/回滚/暂缺certification/正式Pause专项4 passed。全为Docker PG与recording facts，无交易所写入。**STAGED不是回退成功**：原子mode/comparison/authority/epoch activation、actual rebase、Static timeout/failure恢复及pause清理warming目标仍未完成；本段没有Ticket，因此不能代替Static回退期间有仓生命周期验收，不构成GS-08 Done或exact R4。

2026-10-09Static failure收敛增量（基于`737f69c3`）：新增lease/version-bound的Static failure操作，复用原Universe abandon、Generation/Vacuum及append-only events；MATERIALIZING/STAGED在原fenced_at+固定Spec timeout到达后，不再从install抛错并无限重试，而是在同事务abandon未生效targets、提交FAILED_CLOSED+terminal time、清lease并记录原deadline/reason。`CERTIFICATION_OWNER_ACTION_REQUIRED / NOT_ELIGIBLE`亦正式终态，temporary unavailable仍由原retry路径处理、不刷新预算。原Vacuum保持RECONFIGURING与原fence/drain时间、未resolved；旧Dynamic current/Authority/Control不改变，不凭失败恢复Entry。后续相同tick读取同一原因、不重复事件、不claim旧terminal Generation。四策略×正常/timeout/owner_action共12分支；MPG/MI permanent-case先通过现有make_warming_ready安装完整certification prerequisite，避免把CERTIFICATION_MISSING当永久拒绝。漏掉abandon的实际commit从DID_NOT_RAISE RED转绿：0008 deferred约束独立要求失败目标均abandoned、lease清除、exact failure event/deadline/terminal shape及仍围栏的原Vacuum。错误failure lease token另作末版检查，不能通过异常路径释放别人lease。相关Generic/恢复组合52 passed、Generic migration/SOR materialization99 passed、Unit/Architecture1319 passed、Mypy206 files、Ruff/diff通过；末版12分支重验。全部Docker PG，无生产修改。**FAILED_CLOSED不是fallback成功**：尚未实现failed Static intent的合法previous-Dynamic恢复/Owner supersession及重新排期，不复活failed Generation，不直接SQL清围栏；原子Static activation/rebase与其他GS审计要求继续未完成。本段没有Ticket，不能替代有仓Static回退链验收，不构成GS-08 Done或exact R4。

2026-10-09Static activation proof准备增量（基于`8ca5ef2a`）：新增frozen `GenericStaticActivationProof`，来源为exact Owner authorization/baseline/Static Generation/原Vacuum/目标binding与锁定cursor，不借用Snapshot或首次Dynamic失败fallback模型。PG prepare仅读取/锁定证据及再认证STAGED target，校验Owner/Control/lease/deadline、原drain、Policy、previous Authority/Universe/comparison及完整1..10 baseline覆盖，返回预期Static版本`current+1`；不写current、mode、Authority或rebase。NORMAL保留latest unconsumed current close，owner输入必须预提交；真实authority gap/Owner interruption/未闭合recovery provenance才future-close-only，并要求Episode rebase。正常自己这次已验证的materialization Vacuum不被误当成更早gap，默认交易检查仍看到全部fence，误给别的excluded ID仍识别interruption。已完成的历史recovery标签不会无条件把后续所有正常切换降级future-only，而是复用当前overlap rebase blocker。MPG/MI normal-path fixture仍缺中间period Authority，实际判断为AUTHORITY_GAP并选下一close；CPM/BRF2 current Authority连续到切换边界则保留当前close。四策略×两种规则8个domain分支覆盖已消费close、错误next-close及跨close输入；正式PG source路径覆盖错误lease、Policy关闭、已消费cursor NORMAL拒绝/RECOVERY不追認过去close、prepare无权限写入。相关Static/Dynamic/recovery/continuity38 passed、Unit/Architecture1327 passed、Mypy206 files、Ruff/diff通过；末版prepare时钟不能倒退等改动以四策略focused4分支重验。全为Docker PG，生产未修改。**准备证据不是Activation成功**：当前尚未persist独立Static activation authority/完成current+mode+comparison+epoch原子提交，也未把normal comparison rebase或recovery Episode rebase实际接入Static交易链；跨后续Static periods的权限延续与失败恢复仍须实现和验收，不构成GS-08 Done或exact R4。

2026-10-09Static atomic activation/rebase增量（基于`cf605733`）：正式Coordinator STAGED分支准备typed Owner/baseline proof，再由原Universe activation boundary的ACTIVATE_GENERIC_STATIC在短PG事务中重复derive proof并核对lease/current/Policy/drain/deadline/cursor。事务retire旧Dynamic scope及Universe、activate新Static版本、CAS current、切Static comparison Definition/revision/source指针、提交ACTIVE Generation及RESOLVED_ACTIVE Vacuum、清pending/epoch并令Control.version+1；旧immutable Dynamic Authority保留历史，仅清其current pointer。Static当前权限继续由原Control/current Universe拥有，切换proof存于既有immutable ACTIVE materialization Event，不创建第二Authority表或伪造Snapshot。commit末尾再次检查hourly close/monotonic时钟、原timeout和lease窗口。正常连续路径保留当前未消费close；真实gap的Static目标初始化原Episode recovery checkpoint，ENTRY resolver拒绝first eligible之前及尚未armed的交易；Observation复用原recovery/comparison reducer，在MPG/MI三根正式close中首TRIGGERED抑制、NOT_TRIGGERED armed、后TRIGGERED只产生一个Signal，后续Static小时不需要合成Selection Authority。复用existing first-activation fallback单位测试时补新port的None来源mock，不弱化其不得fall-through断言。四策略正式commit、提交前异常全回滚、误source proof拒绝、漏rebase PG commit拒绝、重复active tick零事件增长及正式Owner Pause已验证；原baseline仍retired、新目标UUID不同。0008 deferred constraints要求ACTIVE/current/mode/Vacuum/comparison原子一致并核对source identity、clock rule及恢复checkpoint完整性。首次recovery placeholder漏checkpoint列被真实PG state_shape拒绝，改为单INSERT写Episode+recovery facts后转绿。相关Generic/Static/恢复组合42 passed、Generic migration/SOR materialization/Observation118 passed、Unit/Architecture1327 passed、既有Full-chain51 passed、Mypy206 files、Ruff/diff通过；末版CAS/deadline/latest-close/source SQL补强按四策略focused重验。全部Docker PG与recording facts，production_authority=NONE。**仍非GS-08 Done**：需继续独立SQL pre-state proof/伪造NORMAL与cursor覆盖攻击、末尾deadline故障注入、完整Static NORMAL comparative路径、已有Ticket的Static cutover生命周期、Static再次Dynamic排期与epoch旋转、failed Static recovery/重试、pause释放warming目标及真实consume/grant并发；本段只到自然Signal不冒称新Static Ticket/ENTRY终态全链或exact R4。

2026-10-09Static→再次Dynamic epoch旋转增量（基于`4f24795c`）：四策略在正式Static rollback成功后，再走Owner/TOTP `stage_generic_dynamic_selection_mode`，新idempotency生成新epoch，原baseline pointer及immutable来源不重捕获、不改写。RED实际证明排期令Control.version+1/新epoch存在时，旧Static proof reader立即返回static_activation_control_changed；新增共享纯`permits_static_control`判断区分stable Static与exact下一版本的pending Dynamic intent，ENTRY/Observation/recovery reader均使用该规则。Owner排期不是已生效交易Universe切换，原Static current至正式fence前继续合法消费；MPG/MI在pending期间又经正式Observation消费一个最新NOT_TRIGGERED，不只检查mock permission。正式Runner取得新epoch首个24-member Snapshot、无previous Snapshot与hysteresis继承，旧epoch的同cutoff Job claim为None；现Coordinator从实际新Static current冻结previous baseline，经fence/drain/global warming/staging与atomic ACTIVE_NEW完成第二次Dynamic mode，Control版本与新epoch一致，target UUID不重用旧Dynamic或Static，比较从Static集合回fixed24并revision+1。原Static目标及原baseline均retired，PG只一份rollback baseline、零Exchange Command；Owner Pause仍经正式入口，不由Selection清除。相关Owner/Static/Dynamic/自然入口组合38 passed，Unit/Architecture1327 passed、Mypy206 files、Ruff/diff通过。全部Docker PG，无生产修改。**仍不是全矩阵Done**：第二次Dynamic后的实际rebase/Signal→Ticket及existing Ticket维护、failed Static intent恢复、暂停未生效target回收、normal comparative Static路径、SQL pre-state/cursor攻击和consume/grant并发继续未验收，不构成GS-04～09完成或exact R4。

2026-10-09Static SQL NORMAL/cursor攻击增量（基于`8c7a384b`）：对正式Owner→Dynamic→Static STAGED上下文，故意同时绕过Python prepare/require，将MPG/MI真实gap proof伪成合法typed NORMAL/current close；真实commit此前DID_NOT_RAISE，新增0008独立source-expiry、VALID_EMPTY、Owner版本及Owner/Policy pause/非本次Vacuum interruption验证后拒绝，不能只按“字段形状正确”承认NORMAL。CPM/BRF2连续路径另一RED伪造Episode版本/last cursor，同样绕过Python verifier进入正式cutover，PG此前接受；新增与真实Episode/comparison/recovery版本、最大consumed close的exact比对后拒绝。正常和恢复两类均独立要求cursor完整1..10 count、成员唯一、target members来源及canonical Episode key，四策略再于ACTIVE INSERT边界删掉所有cursor payload（实际proof仍完整）得到PG commit拒绝，证明不是仅domain构造器在拦截。正常prepare/activation、真实future recovery三close/rebase、再次Dynamic新epoch流程继续通过；所有失败事务回滚旧权威事实。相关Static/Dynamic/failed恢复36 passed、Generic migration/SOR materialization99 passed、Unit/Architecture1327 passed、migration Mypy、Ruff/diff通过；末版四策略payload攻击focused4 passed。不改Feature/参数/账户scope，不操作生产，不构成exact R4。**剩余**：recovery origin/尚未armed provenance与独立pre-state/source时点/lease proof还需完整SQL攻击矩阵；末尾close/deadline故障、有仓Static生命周期、normal comparative Static、failed intent合法恢复、pause target释放及consume/grant并发仍未闭合，GS-04～09不标Done。

2026-10-09Static末尾clock / CPM-BRF2入场fault验收增量（基于`58ea0325`）：四策略正式Static cutover已实际完成事务内mode/current切换之后，注入末尾clock为lease deadline、原fence+materialization deadline、倒退时点及下一hour边界；读取模式作为注入点证明故障发生在全部写入后的最终检查，不是简单在准备阶段早拒绝。正式UoW回滚旧Current/Authority/Control、STAGED目标、原RECONFIGURING Vacuum/fence/drain，清掉新recovery初始化且lease保持释放。hour-boundary fixture同时超过30s lease/timeout，拒绝原因deadline，不冒称独立hour-only证明；其余边界分别验证相应code。本轮生产实现本就有这些检查，仅新增验收。CPM LONG/BRF2 SHORT由真实Owner→Runner→Coordinator→Observation自然产出Signal后，共用原hourly入场fault helper；正式Owner pause分别在Claim之前、Claim与Ticket之间、ENTRY dispatch之前生效，零venue调用、前两者零Ticket/Command、后者prepared ENTRY superseded且释放占用。另action-time account/admission facts过期在dispatch前终态拒绝（command实际REJECTED，不误写成SUPERSEDED），零venue调用、唯一ENTRY generation及Reservation/Netting Domain释放。8个新自然fault分支通过；相邻Static/activation/failed恢复32 passed，最终自然入口+MPG/MI既有hourly fault组合32 passed、Unit/Architecture1327 passed、Ruff/diff通过。计数重叠不相加，无生产修改。本段不补经济研究、不扩Actor资本/账户scope；仍需switch/freshness矩阵、独立末尾close-only、已有Ticket Static cutover、failed intent恢复/pause target回收及全卡审计，不构成GS-04～09 Done或exact R4。

| 范围 | 当前已验证结果 | 仍需交付 |
| --- | --- | --- |
| 数值证据 | 96份原始1h ZIP哈希逐一验证；从冻结commit重建research函数并核对artifact完整排序；CPM/BRF2各463、MPG/MI各1852 cutoff的决策集合零差异；SOR961×24 Core verified | exact最终candidate再次认证，认证证据与受审安装集合绑定 |
| GS-01/03边界补强 | 跨comparison revision旧token拒绝、same-close checkpoint幂等；miss按period计算，可重放/跨缺失period；effective前及deadline后ENTRY拒绝 | runtime cursor/Owner/freshness全链集成 |
| GS-04迁移切片 | 本地0007→0008逐record logical manifest与Comparison来源保全；缺源在schema写入前STOP；exact0007→0008 MPG/MI四起点首根及后续Signal差分通过；terminal Ticket、PAUSE、VALID_EMPTY、FALLBACK及Gap Audit/Generation历史样本保全；Owner角色新增表SELECT-only实测；四策略Owner epoch授权与失败Spec拒绝的本地边界；Authority/Generation/Static baseline pair归一化；Job/Generation epoch与Snapshot复合FK；保留SOR≤7 | 完整source矩阵与非法shape/并发deferred攻击、Generic Generation完整状态机及整卡认证；Owner Console/API属于后续GS-11 |
| GS-04/05回归 | 最新相关PG139 passed；Generic迁移9 passed，后加旧SOR Job/Attempt逐字段保全1 passed；Unit+Architecture1169 passed；Golden来源/输入完整性与Core961×24 parity均通过；Ruff及源码/脚本Mypy通过 | 完整PG/Full-chain和source verifier升级，不是R4 PASS；分批数字有重叠，不能相加冒充完整release计数 |
| 纯Selection合同与持久化 | Candidate24/cutoff、公式、Desired predecessor/hysteresis；四策略exact roundtrip、EMPTY不补位；锁定Spec进行前驱CAS；共享Job lease/完成/失败逻辑；Generic commit再验Control version、epoch、lease、前驱与有效期；Static零Job；源失败不推进前驱，新epoch不继承旧Job；正式Runner Spec dispatch、raw public 1h OHLCV、Product资格事实与digest，取数在事务外 | Job EXPIRED/SUPERSEDED终态与bounded调度、source retry/lease fault完整认证；直接SQL并发分叉/跨事务链认证、三Plane调度；GS-05未完成 |
| GS-06～09 | 现有SOR读路径已随schema切片接线 | Generic comparison/Observation、Warming、Vacuum/authority、Claim/Ticket/dispatch完整集成未完成 |

GS-06比较边界准备：`ComparisonUniverseBinding`从独立definition/member/current表读取，不以TradableUniverse N构造Dynamic分母；Dynamic必须exact Candidate24及正transition revision，Static必须匹配其source Static Universe成员。安装已认证MPG/MI Spec只准备不可变fixed24定义，不改current binding、不触发rebase或activation。PG测试证明安装时binding为零、显式绑定后读到24、缩成23即拒绝。当前projection缓存仍按旧交易Universe key；Observation成员来源接线进展见下文，必须完成缓存身份迁移、绑定CAS及真实producer rebase后才能声称GS-06 Done。此准备切片相关PG58 passed、Unit/Architecture1185 passed，Ruff/Mypy通过，生产未修改。

GS-06缓存成员权威增量：比较projection读取及ready/unavailable回写均校验所属Universe和成员来源；Static不得缩小原比较集合，Generic warming必须使用所绑定已安装Spec的全部24个Candidate，而非Selected12/16。正式abandon后旧缓存及迟到回调均拒绝；读取在PostgreSQL只读事务内通过，不取得写锁。0007迁移来源夹具改为测试专用、显式0007列的插入，不调用0008比较仓储，也不增加runtime旧schema fallback。相关migration/projection/Generic repository组合61 passed；补充abandon/只读断言后projection模块3 passed；Unit/Architecture1185 passed。上述计数有重叠，不构成R4或GS-06 Done。cache revision/ABA、独立缓存key、真实Observation及Episode rebase接线仍待完成，Static source/target真实producer差分仍未完成。

GS-06真实warming Observation增量：`observe_strategy_scope`通过仓储解析比较成员，Generic MPG/MI由已安装Spec提供24币分母，Static沿用原Universe成员。修复Observation读路径遗留10成员硬上限：已受数据库Spec约束的Dynamic可读取至16，manual/Static仍最多10。生产入口测试覆盖12/16个目标scope共享一次24币比较抓取、缺少一个未入选Candidate也不能warm、重试后可warm、零Episode/Signal/Ticket/Command、current Static comparison Binding不变。该测试使用已安装目标及明确的Generation MATERIALIZING夹具，不宣称Coordinator/Vacuum完整。相关Generic repository、Observation、market bounds、comparison projection组合75 passed，Unit/Architecture1185 passed，全源码Mypy通过；不是R4。剩余：独立cache key/revision CAS、active comparison barrier及Episode checkpoint持久化、完整authority/materialization和source-target中性差分。

GS-06比较revision增量：抓取前冻结`ComparisonObservationSource`成员与transition revision；cache ready/unavailable模型及0008物理列持久化revision，旧0007缓存保留并初始化为0。读缓存、成功/失败回写均核对当前revision；名单相同但revision变化也拒绝旧结果，新revision可替换同close缓存。Observation提交Facts/Episode前再次在事务内锁定来源并核验，进程内抓取合并key也包含revision。PG回归证明旧ready、旧failure及旧缓存读取被拒绝，新revision正常保存。相关migration/Generic repository/Observation/market bounds/projection组合85 passed，Unit/Architecture1185 passed，全源码Mypy、Ruff通过。该切片没有完成独立于tradable Universe的cache主键，也没有完成active Episode checkpoint/barrier；完整ABA episode测试与GS-06 Done仍待后续，生产未修改。

GS-06独立缓存消费身份增量：runtime lookup及进程内抓取合并使用`EventSpec + member digest + transition revision + close`，不再以消费方TradableUniverse作为cache命中条件；EventSpec固定MPG8h/MI12h，仓储读写及producer均拒绝错误lookback。0008替换lookup index，原存储行及来源Universe主键保留以保全来源，不合并/删除旧行；返回消费方视图之前独立校验其Universe和comparison权威。跨Universe的相同输入回写使用事务级cache身份锁并复用既有ready记录，冲突价格窗口fail closed，失败回调不能降级ready。PG测试覆盖废弃来源无权限、新合法Universe复用、重复回写不增行、错误lookback、同key不同窗口冲突；不是把存储来源FK当新交易Authority。共享读取改动相关组合86 passed，随后增加幂等/冲突保护后的projection/market bounds/Generic repository组合61 passed、projection专项4 passed；计数重叠。active Episode checkpoint/rebase、完整Authority及Static source-target producer差分仍未完成，GS-06保持IN_PROGRESS。

GS-06正式Episode barrier接线增量：在原`brc_exposure_episode_current`行增加独立checkpoint version/CAS，不改变domain key。无旧Episode的新scope首次TRIGGERED持久化`comparison_rebase_required`且无Episode ID/arm；普通reducer不能直接从该状态TRIGGERED。已存在Episode的抑制只推进checkpoint，不改写旧Episode身份。正式Observation在positive comparison revision下调用comparison reducer并原子保存；首触发抑制、false armed、后续true发Signal，同close重复幂等，同digest新revision也重新rebase。PG组件覆盖MPG/MI × 无旧状态/旧ARMED/旧TRIGGERED六种起点、重开事务恢复及旧CAS拒绝；真实Observation入口覆盖两策略的上述序列和同close并发仅一次Signal。测试comparison Binding为显式安装的前置夹具，不代表Generic activation/Authority全链路完成，尚未证明旧Ticket保护及所有rollback/recovery场景。Unit/Architecture1186 passed，全源码Mypy通过；不据此标记GS-06或GS-04～09 Done。测试模板在失败migration留下空库后现可安全重建，仅限既有disposable Docker PG模板。

GS-07正式staging增量：共用`advance_strategy_universe(STAGE_DYNAMIC)`改为核对已安装Spec的exact Event set，不再把所有Generation都当成双目标；四个Generic单Event（含BRF2 SHORT）可将target与parent推进STAGED，SOR仍等待LONG/SHORT同时staged。MPG/MI staging正式验收完整24币比较projection，复用独立cache reader，移除旧的重复/仅交易名单缓存校验。Generic提交校验Control version/epoch、Snapshot period和worker lease owner/epoch/expiry；已staged的幂等返回也不能绕过这些校验。同worker lease reclaim后旧epoch拒绝，新epoch幂等，不增加第二STAGED event。临时certification不可用返回retryable原因并保持MATERIALIZING；staging不改变previous current、不创建Authority、不启用scope ENTRY。Generic stage event按已有序列追加，SOR保留冻结stage=5/activation=6协议。测试仍包含明确的MATERIALIZING与certification/warm prerequisites夹具，不证明Generic Coordinator fence/drain已经运行。第一组含activation/fault的PG155 passed；补齐Generic lease/control边界后repository/materialization组合131 passed及四策略专项4 passed，计数重叠；Unit/Architecture1186 passed，全源码Mypy通过。GS-07/08整体仍IN_PROGRESS，Generic Coordinator、Vacuum、atomic grant/fallback和recovery未完成。

2026-09-21实施补充：Universe表示层上界16，manual/Static及Owner配置入口仍限10；Generation-owned安装从已安装Spec、Snapshot及精确target解析limit/成员数量/有效期，SOR Dynamic仍限7，Generic按retain_rank≤16。PG member trigger保留原Product compatibility校验并从Generation/Spec解析同样的trusted limit，直接SQL扩充manual到11失败。四策略经正式installer生成warming Universe（12或16），不创建positive authority；测试中的MATERIALIZING为明确repository prerequisite，不能当作Vacuum/drain/Warming完成证据。

双时钟纯组件新增`HourlyRecoveryClosePlan`：恢复只规划严格未来且小于expiry的close，commit跨界拒绝；无可用close输出NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY，固定要求rebase。正常CurrentFinalCloseGrantProof不因8秒/30秒/2分钟延迟改变语义。尚未完成durable recovery revision、Episode rebase与Coordinator接线，不宣称GS-08-HOURLY-CLOCK-01全链已通过。

Recovery rebase纯组件补充：`AuthorityRecoveryCheckpoint`沿用原episode_domain_key，只记录独立recovery identity/revision及未来arming/cursor，不生成新Episode ID、不修改Comparison revision。它只决定是否可调用既有Episode reducer，不能替代当前Authority/Owner/epoch/freshness验证。已验证先TRIGGERED抑制、未来NOT_TRIGGERED解锁、更晚TRIGGERED、同close幂等/矛盾拒绝、revision回退/换代不能继承旧arm、无效输入与伪造arming拒绝；定向10 passed，完整Unit/Architecture1185 passed，Ruff/Mypy通过。PG checkpoint持久化与正式Observation接线尚未实现；后续还必须证明hourly失败period损失机会后能在合法后续period恢复，不能反复NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY造成永久暂停。

本轮验证使用Docker `dingdingbot-pg`的独立可处置测试库：Universe安装/Schema/Generic仓库组合51 passed；SOR Materialization与Generic migration87 passed；Unit/Architecture1180 passed，后补Owner请求上限和时钟专项24 passed（有重叠）；Ruff、源码/脚本Mypy通过。计划与设计双时钟冻结见提交`b025ac0d`。生产未修改，部署权限仍NONE。

2026-09-09 Generic Generation切片（父提交`4bf00b34`）：新增typed Generic Generation与previous Event baseline，明确Snapshot/epoch/control/period身份、comparison transition revision与不可变semantic digest；按原Generation/target/event表原子存储，不保存第二份Snapshot或成员集。四策略创建/精确读取/重复响应幂等已通过。PG在Generic分支校验Snapshot epoch、period、数量、effective时点和target member digest，SOR分支原约束保留。

本切片复用共享`_acquire_materialization_lease`，Generic通过递增`lease_epoch`拒绝同worker重复取得活跃lease，过期后旧token不能释放新lease；原SOR lease行为保持。新effective Snapshot可原子supersede尚未fence的PENDING，冻结previous set/hash不变；所有业务验证先于写入，新previous不合法时旧Generation保持PENDING。DESIRED及已fence的切换仍需后续Coordinator完成，不在此处猜测drain/fallback。当前Model/ports/repository已接线，尚未完成Generic Worker/activation链。

本次验证：`test_generic_selection_snapshot_repository.py + test_selection_materialization_repository.py + test_generic_dynamic_selection_migration.py`组合134 passed；后补同模块Generic Generation专项4 passed；`unit + architecture`1174 passed；typed Generation专项5 passed；Ruff与全生产源码Mypy通过。上述结果有重复，不能相加当作独立用例总量。新增测试证明epoch/ID绑定、单Event/比较shape、EMPTY不建Generation、幂等、过期period拒绝、token释放及失败supersession无副作用。GS-04～09整体仍未完成，无Tokyo或交易所动作。

此次只创建本地可处置PG并执行测试；无Tokyo或交易所动作。0008为未发布的工作中revision，不是部署候选。旧source读取代码仅为一次性migration certification，不能进入runtime cadence。上述测试数对应当时实际执行范围，后续修改必须重验受影响面。

本次Snapshot持久化切片以`d34f4f948e7d6adccb8e92bf213f8a70b2c48ebd`为父提交。测试命令为`.venv/bin/python -m pytest <targets> -q -o addopts=--tb=short`，targets分别是`test_generic_selection_snapshot_repository.py`、`test_generic_dynamic_selection_migration.py + test_selection_materialization_repository.py`、`test_instrument_selection_runner.py`及完整`unit + architecture`目录。共享测试输入已移至`tests/trading_kernel/support/generic_selection.py`，不让测试模块互相成为fixture API。

Generic Snapshot/member semantic digest改为固定Decimal38上下文中的数值规范化，消除PostgreSQL将`-0`读为`0`、指数形式转为普通数字导致的虚假digest冲突；负零、正指数及38位精度已有真实PG回归。仅未发布Generic事实编码发生修正，SOR Golden和研究artifact不改写，公式/排名/成员集不变；最终candidate仍必须重新认证。**时间字段偏差已在实现中修正：8张通用表只存`period_anchor_ms`，Control只存`pending_effective_period_anchor_ms`；没有旧列、双写或schema fallback。通用Job record、Generic Claim及Runner request采用period字段，SOR专属Snapshot/Authority/Claim在序列化边界保留冻结Session语义。**

后续Job/epoch切片以`96be356022cff59f680a28c2fbd3128b9f006f5d`为父提交，沿用上述PG targets并增加同模块内claim/complete/恢复测试。Generic与SOR复用`_claim_selection_job_row`、`_mark_snapshot_ready`、`_append_attempt`及原表，不增加第二条job队列。Generic Source失败保持明确失败结果，不能写为EMPTY；过期lease接管后旧callback被拒。这里的Dynamic Control测试是本地repository prerequisite，由隔离fixture建立，不是Owner API/TOTP/首次activation验收，也不形成任何交易授权。

源数据/Runner切片以`57fbc584`为父提交，替换未发布Generic的close-only输入：每个窗口绑定完整raw OHLCV（含base/quote volume）、venue/instrument、normalization version及明确资格事实。输入十进制规范化不执行算术，不受ambient precision影响；feature公式和排名仍使用冻结Decimal38。资格复用现有Event ProductCompatibility/Profile，并结合public exchangeInfo明确的contract/margin/status；缺失或未知事实整次SOURCE_FAILED，已知不合格取交集、不补位、不继承SOR 20M floor。资格事实及digest/reason保存在原member表的typed JSONB/列中；不是文件authority。Generic `input_window_start_ms`修正为完整首根K线的open boundary（cutoff减bars×1h），SOR96×15m合同不变。

`run_instrument_selection_once`通过epoch dispatch进入Generic分支，复用原UoW/Job/Attempt边界，独立加载Candidate Product profiles，不读Current Universe或Signal。四策略正式Runner→PG测试证明source I/O不在事务内、重放不再取数、终点只有Snapshot；另覆盖缺源、未知资格、有效空集、CPM path=0与source读取期间Control改变。计算失败冻结完整source digest及具体成员reason。当前9个Runner场景均通过，但尚未作为resident worker完整调度/交易链验收。组合152项命令覆盖`unit/test_binance_public_market_source.py`、`unit/test_generic_selection_source.py`及前述4个PG模块；全部测试本地运行，无外部行情请求或生产操作。

Event baseline归一化切片以`085ca0db`为父提交：Generation previous与Static rollback各自拥有不可变Event→Universe引用，不复制member rows；previous支持ACTIVE/EMPTY、member digest和必要comparison引用。原四个LONG/SHORT列已从物理Schema删除，SOR通过当前Event行还原其已有pair序列化，不读取旧schema。Root Generation的source identity不可改写，lease/lifecycle仍按原CAS推进。Static SOR baseline用冻结0006 helper在本地0007源构造，0008后逐字段还原含原semantic hash；错置方向的源引用在目标DDL前以`BASELINE_SOURCE_MISMATCH`拒绝。此证据仅覆盖所述baseline，不替代全量Generation/Ticket/History source manifest。

四个新策略均有单Event Schema正例与previous引用不可变负例，MPG/MI携带比较定义引用，BRF2没有伪造LONG。该测试的Active Universe是隔离schema prerequisite，不是Warming或Owner activation认证。Generic Generation暂不能由SOR pair decoder消费，显式拒绝，待通用运行时模型接线。旧“修改冻结previous pair”的测试已改为实际current Universe漂移；系统先以`DYNAMIC_PREDECESSOR_AUTHORITY_DRIFT`阻断，冻结的Generation引用保持不变，未放松生产约束。

Period迁移切片以`4ab456c2`为父提交。ALTER COLUMN保留原值、ID、hash、索引/约束关系；本地0007已有SOR失败Job/Attempt在0008后逐字段还原，新增epoch默认值仅为`sor-v0`，不新建Snapshot。PG模型及执行查询均不再引用旧物理Session列；SOR专属DTO通过显式值映射读写新列，既有SOR Owner API字段仍由其专属view输出。新Generic Claim放在`generic_selection_jobs.py`，与仍使用的SOR Claim共用一个Job表和lease实现，不形成第二执行链。

本次曾发现通用Job变更导致Golden整文件来源hash失败；未改写Golden或校验器。现将SOR `instrument_selection.py`保持为Golden所冻结的原始源码（其SOR Claim仍被正式路径使用），Generic Job类型独立，严格来源hash检查重新通过。`verify_sor_dynamic_selection_golden.py verify --verify-inputs`与`verify_sor_dynamic_selection_core_parity.py`均验证同一961×24 artifact；没有跳过来源门槛。Generic PG fixture改用现有每测试独立的head-template clone，保留隔离与全部断言，避免每个case重复执行完整迁移。

本轮139项PG命令覆盖Generic Snapshot/Job/Runner、SOR Runner、Materialization、Entry Authority和Vacuum drain；迁移与来源验证另跑。历史0005→0006测试中当前runtime对旧schema的调用仍需在source/release测试维护中分离，不增加旧schema运行兼容。上述结果不代替完整source manifest与GS-06～09的Generic运行时验收。

### 2.2 初始计划基线

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

2026-10-09首次Generic Static rollback来源冻结：原`stage_generic_dynamic_selection_mode`只提交pending epoch而遗漏rollback来源的四策略Docker PG RED已复现。现Owner application在同一事务从实际current Active Static Universe、完整1..10成员、当前原Static Comparison、Registry版本及已安装SelectionSpec构造typed不可变Baseline；parent和单Event row只引用原Universe/Comparison，不复制成员。Control CAS冻结baseline FK，原idempotency重放不再次捕获；首次授权失败/来源缺失/Comparison缺源/CAS失败完整回滚。0008 deferred trigger独立重算完整semantic digest和ID，校验当时current/source lifecycle、Spec/Universe时间及同事务Owner/TOTP authorization/pending Control链；直接SQL伪造digest、跨策略Control借用、清除已冻结pointer、更新Event和孤立baseline提交均拒绝。真实Dynamic激活后原Static Universe已retired，readonly exact-load仍重建相同Baseline。初轮Generic/SOR/migration广范围324 passed，随后最终source-time/Owner-atomicity/concurrency改动按17项来源专项、13项首次activation/Static失败恢复、migration全模块21 passed复验；Unit/Architecture1315 passed，Ruff、Mypy161 files/diff通过。初轮广范围结果不是最终exact R4。Owner ACL测试另修复共享Docker集群NOLOGIN角色清理竞态：测试仅清理自己的可处置数据库，避免删除其他template/并发数据库仍持有权限的共享角色。**该来源冻结不是Static rollback执行成功**；新Static目标的materialization、原子comparison/mode切换及rebase仍属于GS-08未完成要求。

0007→0008 source-preservation增量（基于`6a28b680`）：`verify_schema.py`新增exact0007物理表/列inventory与逐record logical manifest；0008侧只对period列重命名、Generation previous pair、Rollback baseline pair及Authority pair做可核验反投影，新Generic表/字段不伪装源数据。`--compatible-source-revision 0007_exit_profile_authority_v1`在只读事务内组合source shape、flat/quiescence gate、runtime/Registry/Policy/Control identity及所有Static MPG/MI Comparison provenance；缺证据返回FAIL，不触发migration。`--preserve-source-revision`可用原digest复核0008目标，篡改一条旧SOR Job即FAIL。Docker PG验证空/旧SOR Job+Attempt、Static rollback baseline、MPG/MI ARMED/TRIGGERED四种来源的迁移前后逐record digest相同；0007 inventory同真实Schema一致，缺Comparison来源在目标DDL前STOP。相关迁移/Source verifier组合20 passed，Unit/Architecture1257 passed，verify_schema Mypy、相关Ruff/diff通过；不是完整R4。该增量未证明完整GS-MIG-COMP-01的source/target首根与后续Signal差分、所有History与非交易Authority的production-shaped样本、role grants及Owner epoch控制转换，GS-04仍IN_PROGRESS，生产未修改。

0007→0008 Runtime Identity增量（基于`b7e55782`）：正式`deploy_compatible_upgrade_identity`原先拒绝0007来源，Docker PG的RED覆盖Entry原本disabled/enabled两种Flat source，并暴露迁移前越级旋转与0007来源请求错误目标修订；现将0007作为第三种exact capability source，要求Alembic已是0008且请求目标恰为0008，复用flat/quiescence、Registry/Policy/Seed/Capability核对，保留ExitProfile Catalog且不安装/激活Generic Selection。若源Policy允许新ENTRY，目标身份提交前沿既有受控升级路径fence Entry；已关闭则保持关闭。两种定向测试均证明Schema/Commit目标身份一致、Strategy Control不变，且零Job/Snapshot/Generation/Vacuum/Authority/Ticket/Command。Generic/ExitProfile迁移组合20 passed、Unit/Architecture1257 passed、生产源码Mypy158 files、相关Ruff/diff通过；不是R4。此为本地目标身份能力，不构成生产部署或GS-04整卡Done；迁移后的确切provenance、role grants及真实Static producer差分仍待验证。

Static迁移后producer续跑增量（基于`8e32bb02`）：0007来源先以MPG/MI×已有ARMED/TRIGGERED四种Episode状态及完整Comparison缓存形成可认证来源；0008迁移后经正式Runtime Identity旋转，测试显式执行Owner Global/Strategy Resume并将本地测试Instrument认证为active，再调用正式`observe_strategy_scope`。同一Static binding revision 0下，下一根NOT_TRIGGERED不产生假rebase或Signal，再下一根TRIGGERED只生成一条Signal、零Exchange Command。上述Owner/Instrument动作仅是隔离测试前置，不是migration副作用。迁移/Observation组合33 passed，Unit/Architecture1257 passed、Ruff、生产源码Mypy158 files及diff通过；不是完整R4。此证据尚未独立运行exact0007 source producer的相同后续输入、比较两边Detector/Episode/Signal逐字段结果，因此GS-MIG-COMP-01仍未闭合，GS-04继续IN_PROGRESS。

GS-MIG-COMP-01 source/target差分增量（基于`a1ab134c`）：测试只读归档冻结`dev@ee539609560fb006c77099efeb06ab01ad7cda22`的0007执行包，在可处置Docker PG的0007源库运行旧`observe_strategy_scope`，同一t0数据库克隆才升级0008并运行目标正式入口；source helper位于tests/support，不进入production package或旧schema runtime兼容路径。MPG/MI各以先前ARMED/TRIGGERED两种Episode状态开始，首根未来NOT_TRIGGERED、后续TRIGGERED；逐步核对完整market request/closed-candle response、旧Comparison payload及numeric strength、Detector status/reason、首根和后续Episode源字段、Signal ID/Fact digest/数量。目标侧仅允许新增`comparison_transition_revision=0`表示字段，正式Binding/Checkpoint保持revision0，零假rebase、suppression、Exchange Command。源缺Comparison证明时迁移仍在首个DDL前STOP。独立0007进程与0008克隆库的四场景定向4 passed，相关迁移/Owner/Observation组合39 passed、Unit/Architecture1257 passed、生产源码与verify_schema Mypy159 files、Ruff/diff通过；不是完整R4。该证据符合本地GS-MIG-COMP-01差分合同；GS-04剩余History/非交易Authority production-shaped保全、role grants及Owner epoch正式转换等仍未完成，生产未修改。

Owner角色及非交易Authority保全增量（基于`84484ffb`）：0008 migration只在角色已预配置时对七张新增Generic/Comparison/Event表授予`brc_owner_console`、`brc_owner_control`的SELECT，不授予INSERT/UPDATE；Docker PG测试核对真实ACL，临时Control角色在测试结束后清理。0007来源覆盖`OWNER_PAUSED_NOT_MATERIALIZED`与24-member/zero-ready Snapshot的`VALID_EMPTY`两种非交易Authority；0008迁移将每条Authority的两个方向显式归一化为EMPTY Event行，父行旧semantic digest和逐record 0007 manifest完全保持，Snapshot仍有24条原始Decision，零新增Job/Command。当前迁移/Owner PG组合24 passed、Unit/Architecture1257 passed、生产源码Mypy158 files、相关Ruff/diff通过；不是完整R4。现仍缺FALLBACK及terminal Ticket等更完整的production-shaped来源矩阵，GS-04保持IN_PROGRESS，生产未修改。

0007 terminal Ticket历史保全增量（基于`d5b3420c`）：本地只读归档冻结0007执行代码及原Full-chain fixture，在可处置Docker PG/recording venue经正式Ticket→durable ENTRY/保护/退出→Reconciliation→Settlement→Review形成一条已终态历史；再运行真实0007→0008 Alembic，目标对原0007逐record logical manifest digest完全一致，Terminal Ticket与原Command/Review数量及身份保留，迁移零新增Generation。该probe只存在于tests/integration，不作为生产旧schema adapter；最初放于tests/support触发测试资产架构RED，已迁移并复验。terminal Ticket专项1 passed，与四策略Static差分组合5 passed；受影响PG/Full-chain组合32 passed，Unit/Architecture1257 passed、相关Ruff、生产源码Mypy158 files与diff通过。仍需FALLBACK_PREVIOUS及相关Gap Audit/Generation等来源分支、Owner epoch控制转换和完整R4，GS-04继续IN_PROGRESS，生产未修改。

0007 FALLBACK历史保全增量（基于`7ccd1de5`）：冻结0007正式Materialization/Gap Audit测试先注入一次fallback commit失败并证明整体回滚，再在同一可处置Source DB重试提交并幂等读取`FALLBACK_PREVIOUS`；其已终态Generation、Gap Audit、旧Universe及Authority进入真实0007→0008迁移。目标逐record logical manifest与源一致，旧Authority semantic digest不变，LONG/SHORT恢复为两条ACTIVE Event binding，Generation previous Event baseline精确两行，Gap Audit/Generation数量保持。该source probe仅为tests/integration引用，不进入生产兼容路径。FALLBACK专项1 passed，相关Generic/SOR Materialization PG组合97 passed、Unit/Architecture1257 passed、生产源码Mypy158 files、相关Ruff/diff通过；不是R4。GS-04仍需剩余非法shape/并发约束、Owner epoch转换及失败Spec安装等逐项认证，不能据这一案例标整卡DONE，生产未修改。

Owner epoch与Spec资格增量（基于`0c89884c`）：四策略新增正式`stage_generic_dynamic_selection_mode`，一次TOTP step-up经Owner Authorization锁定Spec、下一合法decision period及由策略/Spec/idempotency确定的epoch；Control CAS同事务写pending，Selector只能以该exact epoch在due后claim Job。重复请求在pending或同epoch ACTIVE后幂等，不同payload冲突；Static安装自身仍零Job。0008 Control trigger拒绝无pending Owner证明直接Static→Dynamic、伪造epoch/授权范围及Dynamic中偷换epoch；Generic first activation NO_CHANGE/ACTIVE_NEW/VALID_EMPTY、Static recovery均核对新Owner scope。先前直接SQL设置epoch的测试夹具已改为带授权的合法状态转换，而不是放松触发器。另以BRF2 `SPEC_CERT=FAIL`检验仅其他三Spec可安装，BRF2 SelectionSpec/Control保持不存在，其既有Static交易Control不变。当前受影响Docker PG组合246 passed、Unit/Architecture1257 passed、生产源码Mypy158 files及相关Ruff/diff通过；本地应用/PG边界不等于GS-11 Owner API/Console，也不构成GS-04整卡或完整R4，生产未修改。

2026-10-08 Event binding deferred攻击补强：四个Generic策略各先经正式Repository提交`VALID_EMPTY` Authority及唯一EMPTY Event binding，再用直接SQL试图为同一Authority增加第二条SOR Event binding。PostgreSQL的`brc_validate_authority_event_bindings_v1`在攻击事务提交时拒绝`exact homogeneous Spec Event binding shape`，回滚后原绑定数仍为1、current仍为合法Empty。Generic migration加四策略专项25 passed、Ruff/diff通过。该测试明确验证父Authority和Spec Event cardinality由数据库执行，不仅是Python decoder；仍不代表所有并发/非法shape或GS-04整卡已认证，生产未修改。

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

实施记录：离线`verify_schema.py`的0003/0004/0005 source inventory明确排除0008新增Generic表及comparison列，修复从current metadata错误查询旧schema新增列的问题。真实Docker PostgreSQL逐表逐列集合比对覆盖上述三版；0003→head的Owner-control preservation测试通过，所在模块4 passed。此为source认证工具，不增加production旧schema reader或fallback。0006 source清单还涉及period字段改名及pair字段归一化，未由此证明闭合；完整0007→0008 logical preservation和以下Static producer差分仍待完成。

后续0006认证修复：source inventory显式还原0008改名前的period字段和被归一化的pair引用，并排除Generic新增表/列；真实0006数据库全表全列集合比对通过。0006→0007保全目标固定为`0007_exit_profile_authority_v1`，不随current head漂移；真实source verification→migration→preservation→identity rotation及篡改拒绝的专项测试通过。这不提供0008目标的保全授权，0007→0008完整logical preservation仍待实现和认证。

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

本轮Selection Plane末版相邻验证：Runner短路/响应丢失/claim身份/正式Static→第二Dynamic组合38 passed；独立SOR仓储/Runner/Core/source/architecture47 passed；既有Full-chain与文档76 passed，文档更新后25 passed、Ruff/diff通过。集合重叠不合计，本轮仅tests/docs，未跑最终R4。

2026-10-09Selection Plane审计增量（基于`0af16fd7`）：四Generic Runner复用真实PG commit-response-loss链，新增active transaction计数，Qualification与每个Kline调用均要求计数0；Selection repository代理只允许Spec/Job/产品输入/前驱Snapshot/完成写入方法，Universe/Ticket/Claim/Command代理任何访问即失败。成功及响应丢失后ALREADY_READY重试仍只一次Qualification+24 Kline、各一条Attempt/Snapshot、零Generation/Vacuum/Ticket/Command。新增四策略×installed Static无pending/未installed Spec的正式Runner短路8分支，NetworkForbidden源零调用，Job/Attempt/Snapshot/member/运行面事实均为0。整卡回归暴露两条旧低层epoch夹具直接Dynamic→Static或Dynamic内改epoch，被现有atomic cutover/epoch guard正确拒绝；删除这种正向夹具路径，不弱化PG约束。旧claim epoch矛盾改为明确不可信typed claim身份负向测试（模型规范化拒绝），未授权epoch claim不能复用已有Job；新epoch的Snapshot identity/无前驱/不继承hysteresis及跨epoch前驱拒绝单独验证。正向Owner epoch旋转/旧Job阻断继续以正式Static→第二Dynamic全链为证，不能将低层fixture改动当Owner操作。当前Selector矩阵47 passed、短路/I/O四策略12 passed、SOR仓储/Runner与Core/source/architecture独立组合47 passed。不是GS-05整卡Done或R4；source矩阵与全部显式约束仍需逐项收敛，resident due/三logical lease hosting属于GS-10。仅tests/docs变化，全部Docker PG，无生产修改。

Generic source retry增量（基于`70bf08e2`）：在原Job/Attempt权威链上仅将bounded transport timeout、ConnectionError及CCXT public NetworkError/RateLimitExceeded归类为temporary；失败attempt完整入库、同Job lease释放并记录`next_retry_at_ms`，固定backoff至少30秒，读取到数值或RFC7231 HTTP-date `Retry-After`时取较长等待（最长600秒），最多3次且不得跨Selection period expiry。重试前只返回原SOURCE_FAILED事实并零新market调用，到期重新claim同epoch/period；成功仍要求完整24 Candidate及原Snapshot唯一性。少一根K线、重复/未来bar、完整性和compute undefined仍终态失败，不把23币分母当EMPTY；网络永久超出预算后无第四次请求。Docker PG覆盖qualification/member timeout、限流45秒、三次预算、expiry及来源缺口；Binance adapter unit覆盖raw 1h/ExchangeInfo上的rate-limit/network typed failure与HTTP-date。当前受影响PG/Selection/market unit组合192 passed、Unit/Architecture1262 passed、生产源码Mypy158 files、相关Ruff/diff通过；不是完整R4。仍需真实Worker due调度及进程重启/lease-fault矩阵，GS-05保持IN_PROGRESS，生产未修改。

Job终态增量（基于`46b23b5f`）：未部署的0008为Generic Job增加`EXPIRED/SUPERSEDED`状态、带blocker/无Snapshot/无lease的结果形状，并用partial unique index保证同Spec/epoch最多一条`DUE/CLAIMED`；SOR旧状态集合仍由DB约束禁止使用新增终态。Generic领取入口在合法Dynamic控制下对过期period记录无source attempt的EXPIRED，对已有CLAIMED/可重试Job原子释放lease并标EXPIRED；新due period在同一Control锁域内将旧actionable claim标SUPERSEDED，旧Worker之后不能提交Snapshot；倒序请求旧period也只能得到SUPERSEDED，epoch切换终止旧live claim。Source/Compute失败完成不得超过period expiry，且重新核对current Control/epoch；Runner在市场I/O跨expiry时终止该Job并返回EXPIRED，不提交Snapshot或迟到失败，Static无pending继续零Job。RED先证明过期CLAIMED仍可留存、旧claim未被新due终止、晚到SOURCE_FAILED可落库、网络I/O跨expiry异常及倒序请求违反单actionable约束，随后Docker PG定向测试转绿。当前候选的迁移/SOR Selection/Generic Snapshot组合159 passed，Unit/Architecture1257 passed，生产源码Mypy 158 files、相关Ruff及diff通过；这些是受影响切片而非完整R4。此增量仅关闭Job终态，不代替source retry、Worker调度及GS-05整卡Done，生产未修改。

2026-10-08 Snapshot提交响应丢失幂等增量：四策略正式Selection Runner均经24 Candidate public source完成Snapshot事务提交后，由测试在成功响应交还前注入一次进程侧丢失；第二次同Spec/epoch/period调用直接读回原`SNAPSHOT_READY`，Qualification仅一次、Kline恰24次、Attempt/Snapshot各一条，Generation/Vacuum/Ticket/Exchange Command均为0。与已有lease到期reclaim/旧claim提交拒绝专项共5 passed；Generic Snapshot/Selection Core模块225 passed，Unit/Architecture1276 passed、Ruff/Mypy159 files/diff通过。此证据证明commit-response-loss的局部重启幂等，不替代真实Worker due调度/三个logical lease的hosting或GS-05整卡，生产未修改。

**目标**：每Spec按冻结cutoff产生immutable决定，结束于`SNAPSHOT_READY`。

**允许**：`run_instrument_selection.py`、market ports/adapters、PG Selection jobs/spec/snapshot/member repository、selection unit/integration/architecture tests。**禁止**：Runner读取current Universe、Claim/Ticket、Generation/Vacuum或调用warming。

**RED与要求**：完整24/缺源/未来bar/重复source、compute undefined；每策略独立due；static无pending时零Selector network/job/snapshot。MPG前驱来自Desired Snapshot链，同epoch更早且CAS；runtime failed/staged结果不能改变排名。0..N与valid empty准确分离，四新策略不追加20M或研究外筛选。

**验证**：recording market source+真实PG；网络调用不在事务内；同输入前驱rerun same digest；worker crash/lease expiry/post-commit response loss；fresh source和fresh actual membership不可混淆。

**Done**：同period唯一Snapshot及exact24 member rows、输入digest可回溯；无Universe/Generation/Vacuum/Ticket写入，Selector有独立lease；§3.4相关SOR子集PASS。未安装/认证失败策略不创建Selection Job或Snapshot。

### GS-06 — Comparison / Observation Episode barrier

MPG/MI三期自然rebase链增量（基于`d28fe872`）：首次Owner→Runner→Snapshot→ACTIVE_NEW后，第一根真实Hourly Detector TRIGGERED由正comparison revision suppress；下一due Snapshot由正式Runner沿同epoch前驱计算，NO_CHANGE只复用相同成员、不制造Generation，最新未消费close上的合法NOT_TRIGGERED完成rebase/arming；再下一due Snapshot同样正式提交并获得NO_CHANGE，后续TRIGGERED只产生一个Signal。两策略均经真实PostgreSQL比较缓存、Episode checkpoint与Observation producer，未把第一根抑制当作可交易信号，也未用超期close追认。该增量仍需旧Ticket持续保护、A→B→A及故障/rollback攻击矩阵等整卡验收。

2026-10-08 A→B→A producer屏障增量：MPG/MI在同一个Active交易Universe的隔离测试前置下，Comparison Binding先是原Static四成员A/revision1，再变为固定24成员B/revision2，最后回到同一个A Definition/revision3；每次使用正式`observe_strategy_scope`与真实PG comparison cache、Episode checkpoint。第三次A的首根TRIGGERED依然`COMPARISON_REBASE_REQUIRED`且零Signal，必须经历更晚合法NOT_TRIGGERED才armed，再后续TRIGGERED形成第三个不同Signal；整条链只保留原Episode domain key和一个current投影，零Ticket/Exchange Command。两策略定向2 passed，Observation模块19 passed，Unit/Architecture1276 passed、Ruff/Mypy159 files/diff通过。测试中的Binding转换由隔离PG夹具输入，不代表Owner Static rollback/Universe切换全链已认证；GS-06剩余Unselected重入与故障/rollback矩阵仍须逐项审计，生产未修改。

2026-10-08未观察成员重入补强：在上述A→B→A正式Observation路径中，原A成员OP此前没有Episode/checkpoint，回到A/revision3后首次为OP安装独立scope并以真实行情触发；第一根TRIGGERED只形成`COMPARISON_REBASE_REQUIRED`，后续NOT_TRIGGERED才armed，更晚TRIGGERED仅产生一个新Signal，原SOL Episode domain key未被替换，零Exchange Command。另在MPG/MI小时Authority gap后新Snapshot选入此前未选中的Candidate，正式future-close恢复的首根TRIGGERED仍被`RECOVERY_REBASE_REQUIRED`屏障抑制，不能以新入选直接发Signal。两处定向合计10 passed；迁移+Vacuum unknown/partial相邻组合51 passed，Ruff/diff通过。上述覆盖首次重入的抑制/armed序列与恢复首根抑制，尚不代替真实Owner rollback全链或完整GS-06/09认证；生产未修改。

**目标**：fixed24和GS-01 barrier接入真实producer，不只domain模拟。

**允许**：`project_comparative_universe.py`、`observe_strategy_scope.py`、PG comparison/Episode repository与ports、对应integration/producer tests。**禁止**：缩比较集合、Detector条件变更、给Excluded/STAGED创建可交易Signal、平行Episode键。

**RED与要求**：MPG8h与MI12h使用fixed24；current-close比较key独立于tradable N且不共享错误lookback。原Static保持原comparison；新binding/revision不允许旧armed发Signal。Warm fact、旧cache、same-close false/true不能arm；unselected scope惰性checkpoint、rollback和A→B→A受barrier覆盖。

**验证**：真实Observation entrypoint→PG episode/Signal；先TRIGGERED只suppressed，NOT_TRIGGERED再later TRIGGERED才一次Signal；旧Ticket/退出身份保持。Missing one comparison member必须fail closed，rank3不因排除rank1变成rank1。

**Done**：producer级GS-COMP-01和INV-06/10通过，comparison FK/recording input可回溯；组件fixture不得被误报为完整activation链证据。

### GS-07 — Universe materialization / staged targets

**目标**：generalized Generation精确安装单Event或SOR pair，保持全局单warming slot。

**允许**：install/advance/abandon Universe应用边界、materialization repository/ports及tests。**禁止**：每策略复制warming队列、未通过proof先切current、retire previous后再尝试fallback。

**RED与要求**：target数与Spec一致；schema/domain支持single SHORT，BRF2实际安装路径仅在其SPEC_CERT PASS时可用，未安装时必须拒绝；16-member Dynamic合法但manual11/SOR8非法；请求自报source-kind不能增权。所需facts/certification齐全才能STAGED，全部staged前无positive grant。临时unavailable重试到deadline，timeout不因retry刷新；保留原Vacuum source retarget修复。

**GS-07-SOR-INCIDENT-01（必须显式验收）**：`temporarily_unavailable`属于retryable，不能压成`CERTIFICATION_NOT_ELIGIBLE`后立即fallback；`owner_action_required`属于non-transient，可进入受现有条件约束的fallback，不代表可越过Owner pause或drain。任何retry、重启或重新取得lease不得刷新原materialization deadline。测试需从真实certification结果经Coordinator到Generation/Vacuum断言状态及原deadline，而非只测枚举分类。

2026-10-08事故路径认证补强：Docker PostgreSQL先将真实Generation-owned LONG target认证置`temporarily_unavailable`，经正式Coordinator返回`LONG_WARMING / CERTIFICATION_TEMPORARILY_UNAVAILABLE`，Generation仍`MATERIALIZING`、Gap Audit为0，原fence时间不变；恢复认证后LONG进入STAGED/SHORT warming，换Worker在原`fence + 1800s`再次tick立即进入materialization timeout的Gap Audit pending，Vacuum blocker为`materialization_timeout`，仍无新增Session Authority。另有`owner_action_required`在首个合法close前建立pending Audit且recording replay调用为0的现有专项。本次是对既有代码补真正deadline与无提前授权的验收，不更改SOR语义。SOR materialization全模块78 passed、Ruff/diff通过；不是GS-07整卡或final R4，生产未修改。

**验证**：真实PG+recording venue；全局slot冲突、partial staging、resume/abandon/reclaim、duplicate callback；零warming Signal/Ticket/Command，source eligibility不得从研究数据读。

**Done**：targets可准确STAGED/ABANDONED并恢复，最终activation权限留给GS-08，无incremental warming/carry-forward新设计；§3.4相关SOR子集PASS。

### GS-08 — Continuity / Vacuum / Atomic Authority

Generic PRE_FENCE_CONTINUITY独立入口增量：新增不依赖Snapshot结果的exact period请求，使用原SelectionSessionAuthority parent/current/Event binding及一次miss的绝对freshness；旧Active Universe、Owner/Control、Comparison、boundary当根最新未消费close和完整Episode cursor在PG提交前后均需证明。四策略本地PG测试通过，含BRF2 SHORT及MPG/MI fixed24 Comparison；CPM在Selection尚无新Snapshot时由正式Observation产生Signal，行动时ENTRY Authority也有效。同period SOURCE_FAILED不撤销原合法continuity，也不创建Generation/Vacuum。旧Source Snapshot仍为成员来源，连续grant不刷新deadline；下一次连续miss拒绝，Owner Pause优先，伪造Source Authority的直接INSERT由DB拒绝。已消费close无法获取grant；4h策略若迟到至后续close则拒绝普通continuity，必须另走Gap/Recovery证明，不追认遗漏close。若本期新Snapshot成员相同，正式NO_CHANGE取代continuity；成员变化则先开启Vacuum并阻断旧ENTRY，再进入warming。Generic仓储189 passed、迁移/SOR materialization及既有Full-chain合计149 passed、Unit/Architecture1266 passed、Mypy158 files及相关Ruff/diff通过。此为应用/PG链，尚需候选级Worker调度、late Gap/Recovery正向路径、Recovery-origin Continuity、更多并发、完整GS-08/09和R4；生产权限NONE。

Recovery-origin Continuity补充：MPG/MI先经真实materialization failure→future-close recovery ACTIVE_NEW→多期NO_CHANGE rebase/Signal/Claim/Ticket/recording ENTRY，再让新period没有Selection结果。正式period入口以最近成功NO_CHANGE Snapshot建立GRACE continuity，proof冻结最初Recovery Authority ID；同Event、Universe、Comparison和Episode recovery checkpoint保持同一身份，正式Observation permission仍走recovery屏障，真实NOT_TRIGGERED推进原checkpoint，既有Ticket的出生Authority不变。两策略定向通过；这未覆盖未armed origin下的下一期可交易Signal或Recovery→Continuity的所有并发竞态，不能标GS-08/09 Done。

Recovery-origin下旧Ticket生命周期补强：上述MPG/MI recording ENTRY接受后，在下一period Continuity已经取代current Authority的条件下，同一冻结Ticket经正式Reconciliation确认fill、Initial Stop/TP1派发、Runner保护替换、external-flat残单取消、Settlement及Review到TERMINAL；每次venue fake派发前独立UoW核对Command已durable CLAIMED。终态Ticket保留出生Authority，Reservation与Netting Domain释放、无open Incident，Command数量与venue调用一致。外部flat/Post-fill Stress/Review经济值是本地fixture，不是实际收益；仍须unknown/partial和其余GS-09负向全链验收。

2026-10-07迟到Continuity的authority-gap前半链增量：在四策略同一Vacuum状态机中增加仅Generic可用的`RECOVERY_PENDING`。当period入口已错过scheduled首个close，先以原Authority/Control/Owner和旧Universe证明开scoped Vacuum，保持旧Authority历史指针不追认旧close；正式共享ENTRY drain完成后进入该非终态，持续阻断新ENTRY。未发布0008的状态CHECK、shape CHECK、open-scope唯一索引与直接SQL变更防绕过trigger同步；直接SQL企图把该gap Vacuum改成普通resolved或篡改first_blocker均被拒。**此处没有建立future-close grant、Episode rebase或`RESOLVED_CONTINUITY`解除态**，故不会把fail-closed准备误称为完整恢复。Docker PG受影响Generic/SOR仓储与Vacuum单测282 passed；最终trigger后的迁移与迟到路径专项22 passed、Unit/Architecture1270 passed；源码/迁移Mypy159 files、相关Ruff与diff通过，计数有重叠。GS-08/09及R4仍未完成，生产未修改，下一步需以独立PG pre/post proof、原子Authority/current/checkpoint/Vacuum commit闭合正向恢复，并补unknown/partial/Owner Pause与跨close攻击测试。

2026-10-07迟到Continuity的四小时正向恢复增量：CPM LONG与BRF2 SHORT从已drain的`RECOVERY_PENDING`经原Active Universe/Authority、Snapshot绝对freshness、Owner/Control/Policy、Comparison与Episode cursor准备`AUTHORITY_GAP` future-close proof；独立PostgreSQL函数逐字段重算。单事务提交`PRE_FENCE_CONTINUITY`恢复Authority、Event binding、逐成员Episode recovery checkpoint、current指针与`RESOLVED_CONTINUITY`，deferred guard核对完整后态。首个未来正式TRIGGERED被rebase屏障抑制，零Signal；之前close不追认。伪造Owner proof/direct SQL grant、Owner Pause、cursor漂移、跨first close以及checkpoint初始化异常均拒绝或整笔回滚，重复Coordinator调用复用同一Authority。小时策略在已错过本期唯一close后无合法future close时不能造grant。上述证明两种四小时方向的正向PG/Observation链及四策略pure proof shape，不代表MPG/MI跨期恢复或missed-close ledger已闭合。本轮本地Docker PG受影响Generic/SOR/migration组合287 passed；追加BRF2参数化正向专项2 passed；Unit/Architecture1274 passed、相关Ruff及Mypy159 files通过，计数有重叠；不是final exact R4，生产未修改，GS-08/09仍IN_PROGRESS。

2026-10-07合法新空集接管未完成gap增量：CPM LONG与BRF2 SHORT的`RECOVERY_PENDING`在新的、已生效且为最新的`VALID_EMPTY` Snapshot到来时，沿同一已drain Vacuum改为`VALID_EMPTY_INTENT`，保留原fence/drain时间；Coordinator随后原子提交负向Empty Authority，既不fallback previous，也不创建空Universe或Exchange Command。旧Active Universe保留为非交易生命周期事实，新ENTRY始终由Vacuum/Empty Authority阻断。Owner Pause、错误Control version、直接SQL跳过Intent、直接改成Active/提前Empty与commit中断均经Docker PG拒绝/回滚，重复调用复用同一Authority。该增量尚未解决**新的非空Snapshot接管generation-free gap**，也不把每小时失去close后的新期恢复当已完成。受影响迁移/SOR materialization组合98 passed，定向CPM/BRF2 2 passed、Unit/Architecture1274 passed、Ruff/Mypy159 files及diff通过；非最终R4，生产未修改，GS-08/09仍IN_PROGRESS。

2026-10-07新非空Desired接管原gap增量：CPM LONG与BRF2 SHORT从`RECOVERY_PENDING`接收同一epoch最新有效的非空Snapshot，以真实Generation接管原Vacuum；原OPEN gap事件与旧Authority是来源事实，不伪造失败Generation。新Generation从本次接管计独立1800秒timeout，Vacuum原fence/drain时间不刷新。staged后只允许`AUTHORITY_GAP` future-close `ACTIVE_NEW` proof，PostgreSQL从原OPEN/SUPERSEDED/Generation/Snapshot/成员/Owner/Comparison/cursor独立重算；原子切新Universe、Authority、Vacuum、Episode recovery checkpoint。首根真实TRIGGERED被抑制、零Signal；错误Source/Owner Pause/跨future-close、直接SQL普通RESOLVED_ACTIVE及事务中断均拒绝或完整回滚；重试复用同一Authority。该证据覆盖两种4h方向的新非空接管，不覆盖MPG/MI每小时跨期source、新Snapshot同名单gap NO_CHANGE、完整missed-close ledger或GS-08/09整卡。本地Docker PG受影响Generic/SOR/migration组合292 passed，Unit/Architecture1274 passed、Ruff/Mypy159 files通过；非final R4，生产未修改。

2026-10-07 gap-opening missed-close audit增量：当四小时Generic Continuity 已错过边界close，Vacuum原`OPEN`事件以原period时钟、source Authority和fence时间冻结所有已到达但不能获本期Authority的hourly close列表、数量与`AUTHORITY_GAP`原因；不推断Detector是否触发，也不估计经济损失。PostgreSQL函数按Spec cadence/原Vacuum fence独立重算列表，伪造数量的直接INSERT拒绝；后续同一Vacuum被VALID_EMPTY或新非空Generation接管仍保留原OPEN记录。该事实只覆盖gap开启时的closed bars，不是GS-12/13完整missed-close numerator/denominator，也未覆盖所有materialization失败/Owner Pause窗口。Unit/Architecture1275 passed，受影响迁移/SOR materialization/时钟专项110 passed，CPM/BRF2 gap专项2 passed，Ruff/Mypy159 files/diff通过；生产未修改，GS-08/09仍IN_PROGRESS。

2026-10-08小时策略过期Authority的新期恢复增量：MPG/MI在漏掉上一小时的唯一合法close后，新的有效Snapshot到来时，Snapshot Coordinator先以旧current Authority的实际expiry建立generation-free `AUTHORITY_GAP` Vacuum；OPEN事件冻结原过期period唯一close，并用纯算术的`uncovered_close_count`记录至发现时的累计小时缺口，避免长时间停机创建无界逐根事件。drain后最新非空Snapshot经真实Generation继承原Vacuum并在staged后使用未来合法period的`AUTHORITY_GAP` recovery proof，原旧Authority不因新Snapshot而被归类NORMAL；Universe/Authority/Comparison/逐成员Episode rebase原子提交。MPG/MI在漏1期与漏3期四种本地Docker PG场景里，首个未来正式TRIGGERED被抑制，零Signal；新结果为`VALID_EMPTY`时也先记录gap再提交负向Authority，不fallback previous。PostgreSQL拒绝伪造累计count。受影响Generic/SOR/migration组合298 passed，Unit/Architecture1276 passed，Ruff/Mypy159 files/diff通过；小时同名单新Snapshot的gap-rebase分支与完整missed-close numerator/denominator仍待完成，非final R4，生产未修改。

2026-10-08同名单gap恢复增量：前一Authority已有真实gap且原Vacuum未解时，最新Snapshot即使再次选中相同成员，也**不能**走普通`NO_CHANGE`/current-close proof。它保留原gap Vacuum与first-fence、经真实Generation重新认证相同member set，staged后仍须future-close recovery Authority及逐成员Episode rebase；正常连续、无Vacuum的`NO_CHANGE`路径不变。MPG/MI×漏1/3期×同/异名单共8组，CPM LONG/BRF2 SHORT×同/异名单共4组在Docker PG通过；受影响Generic/SOR/migration组合304 passed，Unit/Architecture1276 passed、Ruff/Mypy159 files通过。此项不引入平行Universe Authority，Extra Warming是故障恢复成本，不扩大正常路径。未覆盖所有Unknown/partial及完整missed-close numerator/denominator，GS-08/09仍IN_PROGRESS，生产未修改。

2026-10-08 `VALID_EMPTY`非追溯持仓全链证据：在四个Generic策略由正式Owner staging、Selection Runner、Snapshot、Materialization、Observation、Claim、Ticket与durable ENTRY到达受保护Position后，再提交下一期合法零成员Snapshot。CPM LONG/BRF2 SHORT与MPG/MI LONG均核对`VALID_EMPTY`只拒绝此后的新ENTRY，原Ticket出生Authority、原始Initial Stop及单一ENTRY Command保持冻结；旧Ticket继续经正式TP1、Runner、外部flat核对、Settlement、Review到TERMINAL，Reservation/Netting Domain释放，无未解Incident。小时两策略的空Snapshot也由正式Selection Runner读取完整24 Candidate，不直接插入；四策略相邻专项4 passed，小时全部fault矩阵加已有Full-chain组合67 passed，Unit/Architecture1276 passed，Ruff/Mypy159 files/diff通过。该本地recording venue/模拟外部flat证据不代表真实收益，不覆盖所有自然Unknown/partial、Live Evidence离线projector或GS-09整卡，生产未修改。

Dynamic post-fence fallback增量（接续`58775726`）：本地Docker PostgreSQL经CPM首次正式Dynamic激活、次期不同成员Snapshot、Coordinator fence/drain及Generation timeout，恢复exact previous-active 16-member Universe。恢复证明由原Authority、原Snapshot freshness与旧Universe锁定事实构造；单事务写入`FALLBACK_PREVIOUS`、16个future-close rebase checkpoint、Vacuum resolved事件和current Authority CAS，Control保留`dynamic_selection`且不刷新原membership有效期。PostgreSQL proof/pre-insert/deferred guard同时支持Static-first及Dynamic来源；Owner Pause、未清drain、来源不符或checkpoint不完整仍拒绝。错误来源ID测试被拒，重复Coordinator调用返回同一Authority。受影响Generic仓储集成169 passed，迁移/SOR materialization组合98 passed，Unit/Architecture1262 passed，全源码Mypy158 files、相关Ruff与diff通过；Owner Pause及drain攻击在后续同用例增补并单独复验通过。此证据不等于所有四策略的Dynamic失败矩阵、Live Evidence、GS-04～09整卡或R4认证；生产未修改。

四策略次期失败差分补充：CPM/BRF2在4h周期内经原名单freshness证明可恢复；MPG/MI在1h周期的30min materialization timeout后，无`< expiry`的未来合法close，顺延到下一period又超过一次miss预算，正式仓储拒绝恢复，Coordinator保持`BLOCKED`与未解决Vacuum，旧Authority虽保留历史指针却不取得新ENTRY权。四组真实Docker PG用例4 passed。这是已冻结future-close-only与绝对freshness的必然fail-closed结果，不通过延长deadline或重放过去close使hourly策略假恢复；后续新Snapshot/period的正式恢复链仍需单独认证。

此前待闭合项：原Generic Snapshot Coordinator遇到prior open Vacuum会返回`GENERIC_PRIOR_VACUUM_REQUIRES_SUPERSESSION`。下段增量已关闭“已失败Generation之后的新非空Snapshot无法接管旧Vacuum”这一局部卡点；其余未完成的Desired/Staged supersession、missed-close ledger、恢复型positive Authority及Episode rebase仍保留为GS-08验收项，不可宣布部署准备。

后续已实施的局部修复：新effective非空Snapshot可在同一PG事务接管先前`FAILED_CLOSED` Generation所留的已drain Vacuum；旧Generation仍终态，原Vacuum fence/drain时间不变，新Generation以本次接管时间计自己的固定1800秒期限，旧回调不再匹配Vacuum。四策略本地测试证明目标可进入warming；MPG/MI还能staged，但跨gap明确返回`GENERIC_RECOVERY_AUTHORITY_REQUIRED`，不能降级为普通current-close grant，原Authority指针仍无新交易权。Generic仓储172 passed，迁移/SOR materialization 98 passed，既有Full-chain51 passed，Unit/Architecture1262 passed，全源码Mypy158 files及相关Ruff/diff通过；这些组合不构成exact R4。**此切片未完成跨period future-close recovery grant、恢复型Episode rebase及missed-close ledger，仍不能解除Vacuum或宣称GS-08 Done。**冻结设计§6.2及本计划的05:30→下一period预规划提供后续恢复时钟输入；不新增提前Warming或追认过去close的业务例外。

重复失败后的有效空集补强：新Generation再次超时仍保留原Vacuum；下一个合法`VALID_EMPTY` Snapshot可以在同一Vacuum上终止失败目标、完成既有drain并提交空Authority，不fallback previous，也不授予过期旧名单交易权。MPG/MI真实PG定向两组通过。该非交易接续不替代非空新目标所需的跨period恢复型positive grant。

恢复型新目标纯领域合同：在既有`GenericRecoveryGrantProof/GenericRecoveryAuthority`中加入与`FALLBACK_PREVIOUS`互斥的`ACTIVE_NEW` proof形状，强制绑定target Snapshot、Source Authority、Generation、selected member digest、finite membership freshness和严格未来close；四策略RED→GREEN。此时0008 PostgreSQL的recovery grant CHECK/trigger仍仅允许`FALLBACK_PREVIOUS`，故`ACTIVE_NEW`只是不可交易的typed准备，未开通写入、Universe激活、Episode rebase或ENTRY。相应Unit/Architecture1266 passed，首次Static与Dynamic fallback的PG定向8 passed、全源码Mypy158 files和相关Ruff/diff通过；不把pure模型当成runtime恢复成功。

恢复型新目标只读PG proof增量：从旧FAILED_CLOSED Generation、旧Vacuum的SUPERSEDED事件、新STAGED目标、原current Authority、确切目标Snapshot/成员及Comparison中重建`ACTIVE_NEW/FUTURE_CLOSE_REBASE_REQUIRED`，在原period无合法未来close时预规划相邻period首个严格未来close，保留Snapshot绝对freshness与一次miss。Owner Pause或来源漂移不产生proof；四策略定向4 passed，当前仅是锁定读取，不写Authority/Universe/Checkpoint。正式commit仍由0008 CHECK/trigger拒绝，不能把proof准备误称恢复激活；后续必须补新目标的独立PG proof、deferred原子约束、current/Universe/Vacuum切换、Episode rebase、行动时拒绝和missed-close ledger。

独立PostgreSQL重算与commit前复核增量：0008新增`brc_generic_recovered_activation_proof_matches`，从Snapshot member rows、staged target、FAILED_CLOSED源事件、Vacuum supersession、current Authority、Owner/Selection Control、Comparison与Episode cursor重算完整JSON proof；错误Source/Snapshot/Owner/cursor、Owner Pause及越过首个未来close均返回false。正式repository再次取得锁定事实并核对最初proof，防止准备与提交之间TOCTOU。四策略真实PG定向4 passed、Generic仓储172 passed、迁移/SOR materialization98 passed、Unit/Architecture1266 passed、全源码Mypy158 files及相关Ruff/diff通过。**这仍然只是只读proof认证；0008 grant CHECK/trigger继续拒绝新目标`ACTIVE_NEW`，Universe/current/Vacuum/Checkpoint没有被切换，生产权限NONE。**

恢复型新目标原子激活增量：共享`ACTIVATE_GENERIC`事务现在区分普通current-close与真实gap recovery；后者先锁定并复核future-close proof，原子初始化目标成员Episode recovery checkpoints，再retire旧Universe、activate新目标、切Comparison/current Authority、resolve原Vacuum，并由独立deferred约束检查完整后态及事件。MPG/MI的下一period恢复成功，普通grant仍不能跨旧Vacuum；重复失败后VALID_EMPTY分支保留。提交响应丢失后的Coordinator重试返回同一Authority，不追加第二条grant；首个未来TRIGGERED由真实Observation抑制，零Signal/Ticket。该时点Generic仓储174 passed、Unit/Architecture1266 passed，Ruff/Mypy通过。后续NO_CHANGE起初仍拒绝Recovery Authority，见下段接续修复；故障回滚、missed-close ledger及其他GS-04～09验收未闭合。本增量不构成R4或部署授权。

恢复激活事务中断补强：MPG/MI在所有目标、Authority、Vacuum及checkpoint于事务内可见但提交前注入异常，外层UoW回滚后旧Authority/current Universe、STAGED目标和未解Vacuum保持原样，新recovery checkpoint零行；随后正式Coordinator重试成功且同一Authority只提交一次。该测试只覆盖这一commit边界，不替代全状态机多故障点或R4。

跨period Recovery successor增量：下一期同名单`NO_CHANGE`在immutable普通Authority上冻结原Recovery Authority ID，PG pre-insert从exact current及原Event binding验证来源；Observation和ENTRY共用原Episode recovery checkpoint/revision，不因period换代走普通Comparison reducer或跳过first-trigger suppression。MPG/MI真实链验证首个及次个TRIGGERED均无Signal、后续合法NOT_TRIGGERED重新armed、再晚一个period的TRIGGERED仅生成一个Signal；篡改checkpoint revision与未armed ENTRY被正式Gate拒绝。该Signal经正式`issue_ready_signal`产生Claim、Ticket与唯一durable prepared ENTRY Command，签发前篡改recovery revision则零Ticket/Command；recording venue经正式dispatcher在独立UoW核对durable CLAIMED后接受一次ENTRY，重复dispatch零新调用。Ticket已签发后再篡改revision，正式dispatch将唯一Command置为rejected/superseded且venue零调用。没有调用真实交易所。仍需保护/退出/Settlement/Review、更多连续NO_CHANGE后切成员的屏障、Owner Pause/故障注入、missed-close ledger及完整GS-08/09认证；生产权限NONE。

Recovery successor的PG拒绝补强：0008 normal Authority pre-insert在引用原Recovery ID时逐member核对其recovery checkpoint identity/revision/effective/first-close；即使绕开应用仓储直接INSERT，只要某个checkpoint漂移就拒绝，不生成新Authority。MPG/MI定向8场景通过（含正常dispatch、dispatch前漂移拒绝、重复失败VALID_EMPTY），仍须完整Schema/PG/Full-chain认证，生产不变。

后续P0验收边界：若某period的普通NO_CHANGE仍携带未完成的Recovery origin，而下一期Desired成员发生变化且保留部分旧成员，不能通过普通ACTIVE_NEW丢掉重叠成员的recovery checkpoint，也不能简单阻止新Selection后令旧Authority过期、Vacuum长期无法恢复。需以真实PG从NO_CHANGE→新Snapshot→Generation→staged target验证：未完成屏障触发future-close恢复型新目标proof/rebase，或提供等价且可持续的fail-closed连续性；不得追认当前/过去close。此项当前未证，GS-08未Done。

变更成员防越权切片：MPG/MI真实PG从已恢复的NO_CHANGE、未armed checkpoint、下一期重叠成员Desired走到STAGED目标，RED证实原路径错误返回普通ACTIVE_NEW。现Coordinator及正式Universe激活入口按重叠成员逐个锁定原recovery checkpoint，未armed或来源漂移拒绝；0008 normal Authority INSERT再以旧current Recovery lineage及target Snapshot overlap独立拒绝直接SQL绕行。同路径在正式NOT_TRIGGERED将checkpoint置ARMED后可完成新名单ACTIVE_NEW；若一直未armed，Generation按原fence+1800秒失败，下一期fresh Snapshot接管同一Vacuum并用新的future-close recovery proof激活，不复活旧名单。MPG/MI定向12场景通过（含原Static首激活及四策略失败分支）。仍需更多真实故障/Owner pause/unknown与missed-close ledger、完整全链验收，不能宣称GS-08 Done。

失去合法close的耐久证据：Generic `FAILED_CLOSED`事件在原reason、Vacuum及固定deadline之外，冻结当前period expiry、严格下一未来close及`no_eligible_close_before_expiry`。同一真实PG分支中MPG/MI小时period记true、CPM/BRF2四小时period记false；这只是可审计的机会缺口事实，不猜测未触发Signal或经济损失，也未完成GS-12/13所需的完整missed-close numerator/denominator。

NORMAL current-close行动时间修复（基于`646aedd8`）：正式Owner→Generic Runner→Snapshot→Activation测试在`close+30s`获得precommitted正常Authority后，`observe_strategy_scope`成功产生trigger但原Signal ingestion错误传入原close作为行动时间，导致FinalGate误判Authority尚未生效。RED先证明`selection_authority_invalid`且零Signal，随后统一以Observation的`attempted_at_ms`传给正式Signal ingestion；Signal自身trigger close仍冻结原closed bar，不追认gap/Recovery的过去close。CPM正常路径转绿，随后Generic/Observation/SOR集成切片176 passed、完整既有Full-chain51 passed、Unit/Architecture1257 passed、生产源码Mypy158 files及相关Ruff/diff通过；这仍不代替GS-08双时钟整卡验收或R4。

CPM首次Static恢复后的Ticket生命周期增量（接续`09ba3b8b`）：既有真实ClosedCandle→Detector→Recovery rebase→Signal→Claim/Ticket→durable ENTRY→recording venue acceptance测试，继续通过正式Reconciliation记录ENTRY fill，提交与该Ticket时钟一致的Post-fill Stress证据，派发Initial Stop/TP1，再推进TP1/Runner保护替换、外部flat的受控残单取消、Reconciliation matched、Settlement与Review。每次recording venue执行前独立UoW验证Command已durable CLAIMED；终态断言冻结Recovery Authority不变、Reservation释放、Netting Domain无active Ticket、无open Incident及Command种类/venue调用一一对应。旧测试helper硬编码`2_200ms`会制造当前恢复时钟下已过期的TP1 Command，故此处使用当前Ticket时间构造测试Post-fill Stress事件，而不修改生产代码。该增量只证明CPM首次Static恢复的本地闭环；模拟外部flat不是自然策略Exit，也不能替代Dynamic恢复、四策略完整Selection或GS-09全链验收。四策略Static恢复加dispatch拒绝专项5 passed，相关SOR旧Universe终态full-chain 1 passed，Unit/Architecture 1257 passed，文档authority 25 passed，Ruff、生产源码Mypy（158 files）及diff通过；完整PG/Full-chain/R4未运行，生产未修改，GS-04～09保持IN_PROGRESS。首次Unit/Architecture命令使用系统Python，因缺少`pyotp`在collect阶段中断，随后用仓库`.venv`重跑通过，不将前一次中断计为产品缺陷。

恢复CPM ENTRY dispatch证据（基于`402ab039`）：原真实行情→恢复Signal→Claim/Ticket测试继续调用正式dispatch_one_command，typed readonly账户/rules source与本地enabled capability为明确前置，recording venue通过独立UoW先读到durable CLAIMED再接受ENTRY。另起隔离case在Ticket签发后改变recovery revision，正式dispatch返回SUPERSEDED、durable Command REJECTED、venue调用为0，证明不能以Ticket已签发跳过行动时恢复权限。未调用真实交易所，未伪造Command或绕过dispatcher。

四策略恢复与新增CPM dispatch拒绝组合5 passed，相关Ruff/diff通过；本轮仅测试，不修改生产源码。证据止于ENTRY accepted/rejected，不含实际fill、Initial Stop、TP1/Runner、settlement/review，也不是所有策略自然Selector完整链，GS-04～09仍未完成，生产未修改。

恢复CPM Signal→Ticket证据（基于`e067f728`）：在既有真实ClosedCandle→Detector→恢复rebase→Signal场景后，通过正式issue_ready_signal签发Claim/AdmissionDecision/Ticket及唯一prepared ENTRY Command；Signal、Claim、Decision、Ticket的selection_authority_id均等于已提交Recovery Authority。行动时certification、instrument rules及账户快照为明确测试前置，未直接插入Claim/Ticket/Command。注入recovery revision漂移时正式签发返回selection_authority_invalid，零Ticket/Command，回滚该测试故障后正常签发通过。

四策略恢复专项4 passed（新增Claim/Ticket断言仅CPM）、相关Ruff/diff通过。此证据结束于prepared ENTRY，尚未dispatch、保护/退出/settlement/review；也未从Generic Selection Runner自然产生全部前置，不扩大为GS-09完整full-chain完成。生产未修改。

双barrier验证：Unit/Architecture1257 passed、四策略Static恢复PG专项4 passed、全源码Mypy、相关Ruff/diff、文档authority25 passed；positive comparison ENTRY拒绝矩阵来自pure组件，PG专项仍主要为Static revision0恢复，不将其扩称全部revision/full-chain认证。生产未修改，GS-04～09继续IN_PROGRESS。

Recovery ENTRY双barrier补强（基于`cb0e8bdc`）：新增recovery_comparison_entry_rejection并接入共享ENTRY resolver的Recovery分支，恢复checkpoint已armed不能替代comparison checkpoint；positive revision必须exact binding digest/revision/key、已armed且同Signal close的真实TRIGGERED晚于arm。Static revision0要求没有矛盾的positive checkpoint，不制造rebase。Observation权限不被该ENTRY-only门槛阻挡，可继续取得合法false；原纯recovery/comparison矩阵验证新comparison抑制与正常触发两种结果。未改Detector/参数或增加authority表，跨period与全链仍未完成。

其余策略恢复行情证据（基于`c08c3832`）：MPG/MI/BRF2补充正式observe_strategy_scope + ClosedCandle source + 原Detector的首trigger抑制验证，读取原Static比较集合，保存REBASE_REQUIRED/triggered checkpoint且无Signal。缺失行情返回INVALID，checkpoint仍无观察/无arm，不能伪装NOT_TRIGGERED。三策略使用共享真实PG事务与savepoint回滚以保留后续仓储负例，不是独立持久化或真实网络事务边界证明；CPM原独立事务三close生成唯一Signal回归保留。四策略专项4 passed、相关Ruff/diff通过。此轮仅测试，不修改生产源码；MPG/MI跨period恢复与完整Selector→Ticket链仍未完成，生产未修改。

恢复消费初步接线验证：Generic repository + 原Observation + Selection ENTRY authority组合155 passed；最终I/O后锁定再验证改动后CPM真实行情专项1 passed，BRF2 resolver补充专项1 passed；Unit/Architecture1257 passed，全源码Mypy、相关Ruff/diff、文档authority25 passed。组合启动后的小修订另以对应专项覆盖，不将其称为完整exact-R4；未执行自然Selector→Ticket→terminal全链，生产未修改。

正式恢复Observation/ENTRY授权接线（基于`7179d566`）：新增独立observation授权入口，与ENTRY共享Owner/Control/Vacuum/current/scope/binding/time检查；Recovery observation只要求exact已初始化checkpoint，允许Detector产生NOT_TRIGGERED完成rebase，ENTRY额外要求同recovery identity/revision/commit/first-close下已ARMED且当前记录为Signal close的TRIGGERED。删除旧runtime-not-installed占位拒绝；过期Recovery仍明确拒绝，不落回裸Static。normal/SOR原入口继续走原规则。

observe_strategy_scope在行情I/O前使用observation权限，I/O后按Owner/Control/current锁顺序再次核验，随后调用正式PG advance_recovery_observation；抑制结果仅更新Facts/readiness，不生成Signal；合法Episode继续原produce/ingest链。CPM真实ClosedCandle输入经正式Detector验证首TRIGGERED抑制→下一NOT_TRIGGERED→再TRIGGERED生成唯一Signal，零Exchange Command。原Static Universe/恢复前置仍由fixture建立，这不是自然Selector→Ticket full-chain；BRF2额外验证仓储推进后只有TRIGGERED的exact-birth ENTRY resolver通过。MPG/MI跨period接续、Dynamic recovery、四ENTRY边界与全部策略真实行情链继续未完成。

Recovery最新close修复收尾：Static recovery PG专项4 passed、Unit/Architecture1257 passed，全源码Mypy、相关Ruff/diff、文档authority25 passed；未重复完整PG/Full-chain/R4。正式恢复Observation/ENTRY消费和其余GS-04～09交付仍未完成，生产未修改。

Recovery Observation最新close补强（基于`c1ba6ac7`）：RED证明恢复仓储可在下一小时消费过时的NOT_TRIGGERED并arming；现入事务要求observed close等于数据库时钟的最新hourly close，写入后再次检查同close窗口与时间不倒退，越界/倒退由内部savepoint回滚。四策略恢复专项4 passed；4h策略覆盖过时close拒绝，四策略覆盖末次clock倒退回滚及无checkpoint副作用。此入口仍未接正式Observation producer，不修改普通切换05:00:08消费最新05:00的合法规则，生产未修改。

恢复Observation仓储收尾：Generic repository + 原Observation模块151 passed；Unit/Architecture1257 passed，全源码Mypy、相关Ruff/diff、文档authority25 passed。组合包括新增恢复checkpoint真实持久化与原观察并发回归，不替代Generic自然producer/ENTRY full-chain，生产未修改，GS-04～09保持IN_PROGRESS。

恢复Observation原子仓储增量（基于`7d793b9e`）：新增advance_recovery_observation，以exact scope/current Recovery Authority读取Owner/Control/Policy、Vacuum、Universe成员、comparison及已初始化checkpoint，拒绝过期/错误birth/time/身份及中断历史；复用纯recovery+comparison+Episode reducer，在同savepoint内写普通Episode、comparison checkpoint和recovery版本CAS，末次DB时钟过期整段回滚。首个真实但被抑制的观察推进authority_rebase_required占位的last_observed与版本，仍无Episode ID/arm；与grant-time无观察占位明确区分。重复close不重复写入。

四策略经正式恢复commit后首TRIGGERED抑制、重连读取、重复tick、错Authority、expiry中途回滚通过；4h策略另验证未来NOT_TRIGGERED→再后续TRIGGERED的ARMED及新Episode，1h窗口没有额外close时不延长period。该仓储入口尚未由observe_strategy_scope调用，Detector结果仍为显式typed前置，不是自然行情producer full-chain；hourly跨period接续、Dynamic恢复及四ENTRY边界继续未完成，runtime-not-installed门槛仍保留。相关专项4 passed，全源码Mypy及Ruff/diff通过。

Static恢复幂等comparison补强（基于`bcb45dc9`）：RED证明已提交恢复后comparison revision变化，commit重试仍返回原Authority成功。现幂等分支锁定并校验comparison ID/revision及source_static_universe_version_id，漂移明确拒绝。四策略恢复PG专项4 passed（MPG/MI负例），全源码Mypy、相关Ruff/diff通过；该修正只保护已提交操作的重复读取，未开放Observation/ENTRY恢复消费，GS-04～09仍未完成，生产未修改。

首次Static恢复Coordinator验证：Generic repository + SOR materialization组合211 passed；四策略专项4 passed；Unit/Architecture1257 passed，全源码Mypy、相关Ruff/diff、文档authority25 passed。测试证明正式Coordinator独立提交/重复tick及重连读取，不代表恢复Observation/ENTRY已开放，未执行完整R4，生产未修改。

首次Static恢复Coordinator接线（基于`829e4b4a`）：FAILED_CLOSED分支在Owner pause之后读取Control/current/Vacuum；exact Static pending且尚无current时调用DB prepare→atomic commit，返回FALLBACK_PREVIOUS及原Vacuum；已有同Generation Recovery current则走正式幂等commit读取原Authority。应用层新增SelectionPersistenceConflict端口异常基类，PG原SelectionJobConflict继承它，Coordinator不导入PG模块、不吞SQL错误。准备事实冲突不写grant，保留原failure blocker等待后续合法事实；Dynamic recovery仍保持原显式阻断。

四策略首次recovery专项将原“直接仓储提交”改为正式Coordinator入口，独立UoW commit、重复tick同Authority、重连读回及不重复事件通过。ENTRY recovery消费者未接线，现有runtime-not-installed gate仍拒绝发单，不把DB恢复写入视为自然Signal→Ticket完成；计划GS-04～09仍IN_PROGRESS，生产未修改。

Static恢复SQL提交最终验证：Docker恢复后Generic repository + Generic migration + SOR materialization组合223 passed；最终幂等Universe/expiry及事件不重复断言以四策略专项4 passed复验；Unit/Architecture1257 passed，全源码Mypy、相关Ruff/diff、文档authority25 passed。成功入口已完成真实独立UoW提交并重连exact-read；负例在延迟约束处拒绝半提交。未完成Coordinator调用、recovery Observation/ENTRY消费及Dynamic恢复，不声明GS-08/09完成，不构成R4或部署授权。

2026-09-28恢复提交接续验证：前轮PG进程handle已丢失，不能推定通过；重跑发现Docker daemon关闭/5432拒绝连接，启动本机Docker Desktop后既有dingdingbot-pg恢复healthy，未使用其他PG或生产数据库。首次环境错误批次（8 failed/213 errors）不作为代码验证结果，后续重新执行受影响组合。

Static恢复commit新增exact-current幂等分支，按Owner→Control→current锁顺序核验原Recovery proof、Control静态/清epoch/无pending、Vacuum已RESOLVED_FALLBACK及原resolution时间、current Universe仍相同、未过expiry；返回原Authority而不重复事件。首次四策略独立提交/dispose/reconnect后重试成功，改proof/过期重试拒绝。幂等返回是已完成操作的读取，不授予新交易；ENTRY runtime-not-installed仍保留。前轮SQL成功提交测试、current/Control/Vacuum/checkpoint破坏负例及comparison漂移负例仍纳入验证。

首次Static恢复SQL提交（基于`c45e37eb`）：未部署0008将临时recovery非NULL全面禁止替换为Static专属shape、BEFORE源事实核验和deferred完整提交校验。源proof必须匹配原failed Generation/pending授权/Vacuum/current/游标，parent时间/source/mode字段必须与proof一致；提交末要求Static Control清pending/epoch且version递增、exact current Authority/Event binding、Vacuum RESOLVED_FALLBACK、完整pending checkpoint及两类commit events。Dynamic恢复仍未支持，SOR原fallback约束仅在其subtype维持，不以Generic绕过。

四策略经正式commit_generic_static_recovery首次成功写入并强制执行全部deferred约束；破坏current、Control、Vacuum、checkpoint分别拒绝并由savepoint回滚。测试随后独立UoW提交、dispose连接池重连读回恢复Authority/checkpoint，旧Generation保持FAILED_CLOSED，不复活旧target。仍无Coordinator调用和正式recovery ENTRY消费；共享resolver的runtime-not-installed阻断保留，因此不能据此声明已恢复交易。commit重试幂等、完整跨period生命周期、其他故障/多成员矩阵仍待完成。

Static恢复事务组装（基于`8db4d283`）：新增commit_generic_static_recovery仓储实现草案，内部savepoint串联proof再验证、Authority/binding INSERT、pending checkpoint初始化、Static Control清pending/epoch并递增version、current CAS、Vacuum RESOLVED_FALLBACK及事件，最终DB clock再检；旧FAILED_CLOSED Generation保留终态并追加恢复事件，不复活目标。尚未对应用端口/Coordinator开放，现有SQL grant gate仍拒绝INSERT，后续成功写入分支必须经恢复专属pre/post SQL约束和故障测试后才能开放。

本轮四策略PG只证明该入口在当前Schema拒绝时完整回滚且外层事务可继续：Authority=current无新增、Control/Vacuum不变；不证明其INSERT后的各步骤已运行或成功commit，更不代表恢复交易。相关专项4 passed、全源码Mypy及Ruff/diff通过。成功分支、幂等重启和完整恢复消费链继续未完成，生产未修改。

newest Selection排除条件验证：四策略recovery PG专项4 passed、Generic migration12 passed、Unit/Architecture1257 passed，全源码Mypy、相关Ruff/diff、文档authority25 passed；未运行完整PG/Full-chain/R4，未部署。GS-04～09仍IN_PROGRESS。

恢复与newest Selection优先级（基于`d8d9b920`）：Static recovery prepare新增共用Spec lineage锁及有界同epoch查询，存在较新、已commit、effective已到且未expired的Snapshot时拒绝旧恢复提案，交回supersession分支；SQL proof checker也按checked-at执行相同否定条件。future Snapshot尚未生效不提前阻断恢复，expired Snapshot不被冒充有效替代。四策略测试提交future VALID_EMPTY后旧提案仍可核验；到effective后优先返回newer effective Selection blocker而非先尝试旧Universe认证。此为恢复准备的必要排除条件，尚不代表所有supersession/Static新period控制语义已接通，正式Recovery grant仍关闭。

初始化旧Episode保全证据（基于`abd8a3bf`）：四策略Static recovery PG探针新增旧armed及旧triggered起点，正式reducer创建原Episode后重新准备proof再初始化，断言普通Episode对象全部字段精确不变、旧close作为高水位保留、新recovery无Detector结果/无arm；初始旧proof因cursor变更被拒绝，不得沿用。外层savepoint回滚清除测试初始化。本轮仅增加测试与证据，四策略专项4 passed、相关Ruff/diff通过；多成员故障与正式恢复commit/消费链仍未完成，无生产改动。

Pending checkpoint原子初始化组件（基于`6afe0242`）：PG Selection仓储新增initialize_generic_recovery_checkpoints，先经完整locked proof/app/SQL再验证，按原Episode key/canonical member顺序初始化原表recovery字段；无旧Episode只建无观察、无ID、未armed占位，有旧Episode保留其普通字段和comparison字段。写入使用Episode/recovery版本CAS，并在内部savepoint末尾再次校验DB future-close窗口，异常整体撤回；最终恢复事务仍应包围此组件及Authority/Control/Vacuum提交。未接Coordinator、不创建恢复Authority、不清pending、不解除Vacuum；正式grant仍被DB禁止，不能单独以组件成功授予交易。

四策略真实failed-generation proposal专项4 passed，含最终clock跨close自动回滚、成功初始化读回、外层rollback恢复无checkpoint及Control/current不变；测试尚无已有Episode与多成员故障矩阵，不能宣称该矩阵完成。Unit/Architecture1257 passed，全源码Mypy、相关Ruff/diff通过。本轮未执行完整PG/Full-chain/R4，生产未修改，GS-04～09仍IN_PROGRESS。

2026-09-27既有full-chain审计（exact code `cdb2eff0`）：运行`.venv/bin/python -m pytest tests/trading_kernel/full_chain -q -o addopts=--tb=short`，51 passed，94.29s。本轮未修改生产源码，全部本地Docker PostgreSQL/recording venue。直接检查`test_registered_event_reaches_terminal_review_from_closed_market_input`确认从正式Observation Worker进入；`test_official_replacement_keeps_old_runner_ticket_to_terminal_review`验证旧Ticket冻结身份跨Universe替换继续生命周期。后者从已签发Ticket前置开始，两者均未走Generic Selection/恢复Authority完整producer路径，不能作为GS-09 Generic full-chain完成证明，也不是R4或部署授权。

下一必需交付仍为：解除临时recovery写入禁止之前，完整实现并验证Static恢复原子commit（Control/current/Vacuum/pending rebase）、正式Observation消费及四ENTRY边界；Dynamic recovery与非空supersession、source/target Static migration neutrality、Generic自然Selection→Ticket→terminal evidence均不得以该51项既有回归替代。GS-04～09维持IN_PROGRESS。

Pending初始化因果补强（基于`254617f9`）：RED证明无观察pending checkpoint可用更高revision把effective/first-close倒退到过去；同revision幂等返回也会忽略非法latest-consumed cursor。现初始化先验证positive hourly cursor，再要求effective时间不早于现有recovery，保留真实close高水位及已armed幂等状态。此为正式checkpoint原子写入前的pure边界补强，未开放数据库Recovery写入或ENTRY消费。

本轮Unit/Architecture1257 passed、全源码Mypy、相关Ruff/diff及文档authority25 passed；无Schema或PG变更，未重复运行PG/R4，生产未修改，GS-04～09仍未完成。

Recovery current读取收尾：Generic repository + Selection ENTRY authority组合138 passed；Unit/Architecture1257 passed，追加current JSON subtype roundtrip断言后的recovery专项24 passed；全源码Mypy、相关Ruff/diff、文档authority25 passed。数据库恢复写入约束未开放，运行消费仍明确fail closed；未进行完整R4或生产动作。

Recovery current读取准备（基于`b5879a70`）：原CurrentGenericSelectionAuthority支持normal/Recovery两种frozen值，仍读取原current表/指针；PG按recovery_grant_proof是否存在调用各自严格codec，没有第二Authority链。Recovery公共身份/period/binding属性由proof推导。shared ENTRY resolver在正式rebase消费未接通前明确拒绝Recovery子类型，包括Static且已过期的记录，禁止落回裸Static放行；NO_CHANGE/ACTIVE_NEW的Recovery successor同样明确阻塞，避免新normal grant跳过恢复首close/rebase。相关暂存保护必须在正式消费者及其回归完成时替换，不能作为最终运行语义交付。

纯模型和resolver定向24 passed，覆盖Dynamic/Static以及未过期/过期四种读入后全部fail closed。此时数据库仍禁止recovery proof非NULL写入，因此尚无正式恢复current实盘记录或可用ENTRY恢复，不把typed读取支持当作恢复成功。

Static comparison组件收尾：Unit/Architecture1253 passed，全源码Mypy、相关Ruff/diff及文档authority25 passed；本轮无PG/Schema变更，未重复跑数据库或R4，不扩大为整卡完成，生产未修改。

Static recovery comparison组件（基于`b2abbcf5`）：恢复组合reducer改用frozen ComparisonUniverseBinding及明确current selection_mode/Universe ID，删除只接收digest/revision的旧参数，不保留双入口。Dynamic仍由binding合同强制fixed24；Static恢复原bounded比较集合（可含Dynamic panel之外的原合法成员），source_static_universe_version_id必须匹配实际current Universe。Static revision0不伪造comparison transition/checkpoint，仍执行recovery rebase；Static正revision继续走原comparison barrier，不能通过回退revision继承旧arm。CPM/BRF2不构造comparison。

MPG/MI × Static revision0/2验证首TRIGGERED抑制、真实NOT_TRIGGERED arming、后续唯一Episode，以及错误mode/Universe拒绝；原四策略Dynamic矩阵保留。定向23 passed，全源码Mypy通过。尚未接入正式Observation，绑定事实仍须由应用层DB核验后提供；不能把pure分支支持宣称Static恢复已上线。

Pending rebase验证：四策略pending/observed checkpoint PG专项8 passed；Generic repository + migration + Observation组合首次162 passed/1 failed，暴露新增Episode校验复制对象导致same-close重放被误判成新保存。现只校验不替换原对象，完整Observation模块重跑17 passed；最终Unit/Architecture1249 passed，全源码及verify_schema Mypy（159 files）、相关Ruff/diff、文档authority25 passed。初次组合失败不改写为全绿；schema/read准备仍不等于正式recovery commit，生产未修改。

Pending recovery rebase表示（基于`742a997c`）：新增`begin_authority_recovery_rebase`，在future close前冻结REBASE_REQUIRED，而不伪造Detector结果或观察时间。无历史时last_observed/status均NULL；重开恢复时保留真实已消费close高水位、清除新revision的arming，status保持未观察。重复同identity初始化返回原checkpoint，不重置已推进的arm；旧revision/矛盾identity拒绝。`advance_authority_recovery_rebase`在幂等判断前先检查future eligible close，不能借保留的旧cursor绕过first-close。

原Episode DTO与未部署0008允许仅`authority_rebase_required`且有完整pending recovery证据的行保持NULL last_observed；普通armed/triggered仍要求真实时间，comparison行为不放宽。LockedObservationCursor识别这种“行已存在但未观察”的状态，不将其解释为已消费bar；原rising-edge reducer拒绝从pending直接TRIGGERED，真实NOT_TRIGGERED才能推进。PG getter和四策略重连存储测试覆盖NULL pending；源0007 provenance对缺观察明确SOURCE_PROVENANCE_INSUFFICIENT，不猜测历史。此处仍为model/schema/read准备，尚无正式初始化写入口或恢复grant解锁。

Static recovery SQL验证收尾：Generic repository + Generic migration组合142 passed；最后补Gen Dynamic来源/未曾active以及failure原因白名单后四策略专项4 passed；Unit/Architecture1247 passed，全源码Mypy、相关Ruff/diff、文档authority25 passed。数字重叠不相加，未运行完整R4；仍保留recovery_grant_proof非NULL写入禁用约束，生产未修改。

Static恢复proof SQL核验（基于`3de95b2c`）：未部署0008新增read-only函数`brc_generic_static_recovery_proof_matches`，由failed Generation、pending Control、TOTP Owner事实、RECOVERY_REQUIRED事件、未解决且已drain的Vacuum、exact previous current/member/comparison、Policy开关及原Episode游标重建完整JSON。拒绝额外字段、错误版本/来源/归因/成员/cursor、非法时间和跨future-close。恢复revision取真实checkpoint最大revision+1，不能由调用方自报。`require_generic_recovery_grant_proof`在原应用层锁定/认证再验证之后，要求该SQL核验也为TRUE；SQL不替代应用层完整certification/readiness检查。

新增RED证明Owner control updated_at位于核验时间未来仍会通过，现应用/SQL同步拒绝Owner和Selection Control的时间因果倒置。恢复写入禁用约束没有解除，本函数不写current、Control或Vacuum，正式恢复事务/Observation/ENTRY接线仍未完成，不能据此宣布恢复生产授权。

Recovery ENTRY rebase gate组件（基于`bba6e91e`）：新增pure `recovery_rebase_entry_rejection`，要求checkpoint精确匹配Episode key、recovery ID/revision、冻结恢复commit时间和first eligible close；必须已ARMED且当前记录为严格晚于arming close的TRIGGERED，并与Signal close相等。缺checkpoint、旧恢复身份、只有NOT_TRIGGERED或过时trigger均拒绝。此门槛仅用于ENTRY，不能放在Observation前阻止建立NOT_TRIGGERED rebase；当前scope/time eligibility仍是另一项必需检查，不可单独视为可发单。

四策略×三种旧Episode起点的组合测试接上此gate，另验证缺失/错误身份/错误时间与stale trigger。Unit/Architecture1247 passed；追加组合断言后的recovery/proof定向37 passed，全源码Mypy、相关Ruff/diff通过。正式PG checkpoint写入、Authority current/rebase读取和四ENTRY边界接线仍未完成，本轮无Schema或PG变更，不把pure测试当作恢复full-chain。生产未修改。

Recovery再验证收尾：Generic repository完整模块130 passed；追加failure-time倒退拒绝后Static recovery四策略专项4 passed；Unit/Architecture1246 passed，全源码Mypy、相关Ruff/diff、文档authority25 passed。模块在最后时钟因果guard前启动，最终guard以四策略专项复验；未执行完整R4，计数不相加，生产未修改。

Recovery proof提交前再验证准备（基于`74c2779b`）：新增`require_generic_recovery_grant_proof`，在数据库时钟和原准备入口锁域下重建全部事实，只容许同一future-close窗口内evaluated/checked时间前进；其余proof字段逐项精确比对，Owner/Control/Vacuum/time篡改拒绝。再次检查Pause、Policy、certification及future-close；时钟倒退拒绝。另一个RED证明首次prepare可在DB时钟倒退至已记录failure之前时构造提案，现增加`now >= generation.terminal_at_ms`的因果校验。

该入口当前仅支持首次Static失败的DB绑定，返回checked-at时间，不写Authority、不清pending、不解Vacuum。未来正式commit须同一UoW调用，不能把返回值当作独立、可重放的授权；Dynamic恢复、current union、SQL grant验证和Observation rebase仍待实施。

Recovery Authority/codec准备验证：Generic repository + SOR materialization + Generic migration组合219 passed；完整Unit/Architecture1246 passed，后补nullable列缺失必须拒绝的RED/GREEN后proof/recovery/normal codec专项40 passed。全源码及verify_schema Mypy（159 files）、相关Ruff/diff、文档authority25 passed。PG明确证明recovery_grant_proof的None绑定为SQL NULL，任何非NULL normal插入被暂存fail-closed约束拒绝；未伪称恢复grant写入已认证，未执行完整R4，生产未修改。

Recovery Authority/codec准备（基于`08e2044e`）：新增frozen `GenericRecoveryAuthority`，只允许FALLBACK_PREVIOUS，确定性ID绑定完整Recovery Grant Proof摘要和authority_sequence；字段投影由proof推导，不能用重写字段伪装normal ACTIVE_NEW/NO_CHANGE。恢复专用pure ENTRY判定验证Control/mode、exact成员及Event/Universe、birth、future eligible close和absolute expiry；Static首次失败证据保留attempt epoch，但恢复后Control必须清epoch。该判定不替代PG current/rebase检查，尚未被正式ENTRY resolver调用。

原Authority表新增nullable recovery_grant_proof JSONB，normal/SOR仍写NULL；当前0008约束明确禁止非NULL，直到完整Recovery grant SQL验证/原子commit安装，不能用准备代码提前写入grant。新codec映射原parent全部列和唯一Event binding，逐字段/digest比对，拒绝错误proof-kind/mode/source/时间/授权混入；不新增Authority/current表，不将source引用写成双重predecessor链。source0006保全清单排除新增列。测试聚合到原recovery proof模块，不保留跨测试模块fixture依赖。

本次仅完成模型、codec及fail-closed存储准备，未开放recovery current读取、fallback事务、Vacuum解除、checkpoint原子写入或Observation消费；GS-04～09整体继续未完成。pure proof/Authority/normal codec专项40 passed，PG与静态检查结果见后续台账。

DB recovery提案准备验证：Generic repository + SOR materialization组合207 passed，首次Static提案四策略专项4 passed（含Owner/Policy/Control/certification/clock负例）；完整Unit/Architecture1237 passed，全源码Mypy、相关Ruff/diff、文档authority25 passed。cursor准备与normal cursor共用读取也通过原覆盖回归。计数重叠不相加；没有正式Recovery Authority写入、没有解锁ENTRY，没有完整R4或自然交易全链认证，生产未修改。

首次Static恢复提案DB准备（基于`67f6ac11`）：`prepare_generic_recovery_grant_proof`仅接收Generation ID，锁定Owner/Control/failed Generation/Vacuum，核验pending授权purpose/TOTP/exact period、RECOVERY_REQUIRED事件归因、drain已清、目标已abandoned、previous current/member/comparison未变、current认证及Policy开关；不允许替代既有Dynamic Authority。由数据库时钟选择本周期或相邻下一period的future close，从真实Episode/comparison/recovery cursor推导新recovery revision，末次DB clock跨界拒绝。方法无业务写入，不清pending、不解Vacuum、不创建current Authority；尚未由Coordinator调用，正式commit必须再次核验并原子持久化。

共享cursor读取新增recovery入口：保留已消费close作为证据而非normal路径直接拒绝，但拒绝相对evaluated time位于未来的cursor；Static最多10个previous成员且不被Candidate24重定义，Dynamic按Spec上界/面板校验。normal/recovery共用原Episode advisory/row lock读取，不新增游标表或写链。四策略PG用实际失败Generation及显式previous readiness前置生成Static proposal，验证无Control/Generation/Vacuum/Authority变更；Owner Pause、Policy关闭、Control漂移、认证暂不可用及末次时钟跨界拒绝。Dynamic source恢复、正式commit、非空supersession与自然交易链仍未完成，不能将准备入口视为交易恢复授权。

Recovery proof验证：四策略Static/Dynamic、stale deadline、无合法close、previous Static面板外成员及各scope/version/time/comparison负例共11个测试；完整Unit/Architecture1237 passed，全源码Mypy（158 files）、相关Ruff/diff通过，文档authority25 passed。此次未改PG或runtime接线，不重复跑PG/R4，不将组件证据上升为整卡完成；生产未修改。

Recovery Grant Proof合同准备（基于`0152b45c`）：新增frozen `GenericRecoveryGrantProof`，与normal current-close proof分开；绑定原Vacuum/fence、恢复原因与revision、未来close、完整previous member cursor、Owner/Control版本及原source引用。Dynamic形态要求已有source Authority和真实membership freshness，按目标period精确匹配0/1 miss、绝对deadline不变，首个close不能到达或超过deadline；首次Static fallback要求失败的Dynamic Owner授权及Generation引用，不伪造Dynamic source。MPG/MI分别保留Static comparison集合或Dynamic fixed24；交易成员digest与comparison definition digest采用各自规范化键，不能互换。Static previous set不被Candidate24偷偷重定义，仍须后续DB/venue证明其合法性。

本组件只表示待核验恢复证据，尚未加入current Authority union、PG codec/constraints或grant入口；不能用模型构造成功作为恢复交易授权。后续必须将引用绑定真实DB current及source记录，并与Vacuum/Control/Episode checkpoint原子写入。非空supersession和恢复全链继续未完成。

EMPTY supersession收尾验证：Generic repository + SOR materialization + ENTRY Vacuum drain组合233 passed；追加Owner/Control/Vacuum旧版本及未到effective拒绝后的supersession专项8 passed；Unit/Architecture1226 passed，全源码Mypy、相关Ruff/diff、文档authority25 passed。计数重叠不相加，未执行完整R4或自然Signal→Ticket全链；所有PG验证在本地Docker，生产未修改。

Generic VALID_EMPTY supersession增量（基于`9b868587`）：已复现新zero-member Snapshot被旧failed Vacuum永久挡在GENERIC_EMPTY_REQUIRES_SUPERSESSION。现同一Coordinator在Owner/Control及Spec lineage锁下确认最新due、未过期、exact epoch的空Snapshot，复用原Vacuum追加VALID_EMPTY_INTENT；旧MATERIALIZING/STAGED目标经正式abandon并标SUPERSEDED，已FAILED_CLOSED父行保持原终态/时间/版本。Vacuum转移到新period/intent但保留原ID、fence及已完成drain时间；统一empty提交读取最新追加intent，不改写旧OPEN事件，不新建空Universe/Generation、不fallback。旧Generation仍DRAINING时先继续正式drain，未清空不能跳过；Owner Pause优先。

四策略×staged/failed八场景验证同Vacuum原子EMPTY提交、Owner pause拒绝、commit前中断整体回滚、保留原fence/drain和失败父行、重试不重复intent。测试仍为明确Static baseline与无Ticket的materialization前置，不替代已有Position/Ticket非追溯full-chain。非空supersession、跨epoch/Owner-Pause恢复和正式fallback Authority仍未完成。

Generic empty drain边界修复：直接无Ticket drain会调用SOR专属get_snapshot_disposition的RED已复现。现Generic generation-free empty drain仅验证drain blockers并返回GENERIC_EMPTY_AUTHORITY_COMMIT_REQUIRED，保持DRAINING_ENTRY且不生成Authority；仍由Coordinator原子提交EMPTY。首次/普通empty四策略回归显式断言零SOR Snapshot读取，覆盖Ticket在外层查询后清空时会到达的同一无Ticket分支，不声称已做真实并发Ticket全链。empty/supersession定向组合16 passed。

失败handoff验证：Generic repository + SOR materialization组合195 passed；补充真实DB deadline前拒绝超时后的失败专项14 passed（四策略timeout/permanent/expired及两条首次Static失败），覆盖wrong lease、commit前中断全回滚、target/旧current/Control/Vacuum/零Command与重复失败事件幂等。最终activation直接入口的6场景额外验证final-clock跨close、跨deadline、跨lease均回滚。Unit/Architecture1226 passed，全源码Mypy、相关Ruff/diff、文档authority25 passed。数字重叠不相加，未执行完整R4，生产未修改。

Generic失败handoff（基于`5715f215`）：四策略到原fence+1800s仍返回TARGET_WARMING的RED已复现。现MATERIALIZING/STAGED在超时或period expiry时停止目标；认证owner_action_required/not_eligible走同一负向失败入口，temporary unavailable在deadline前仍重试。入口核对Owner/Control/epoch、worker lease、Generation/Vacuum版本及drain，用正式Universe abandon清理未生效target并释放warming资源；同事务Generation变FAILED_CLOSED且terminal、清lease，Vacuum保留RECONFIGURING及原fence/drain，不写resolved时间，追加RECOVERY_REQUIRED及失败原因/deadline。已有previous Universe、Selection Control、Ticket/Command不变，没有伪造FALLBACK_PREVIOUS或positive Authority。相同Generation重试读取原blocker，不追加失败事件。

已fenced的DRAINING_ENTRY/MATERIALIZING/STAGED允许period过期后获取cleanup lease，以便继续既有drain并终止过期目标；这是负向收尾，不延长Snapshot/ENTRY资格。pre-fence过期仍拒绝，新的目标安装/直接STAGE/CERTIFY/ACTIVATE仍校验period及原deadline，ACTIVATE最终DB clock还检查close边界、deadline与lease expiry，任一失败整事务回滚。原lease-reclaim fixture改为deadline内15min lease；不能保留“30min deadline后仍可staged成功”的旧断言。expiry/failure之后的恢复Authority、Static失败清pending、supersession及global-slot-before-fence完整排序仍待后续，不将本handoff标成fallback全链完成。

本轮收尾验证：相关PG108 passed、首次/普通激活专项10 passed；时钟/rebase/timing专项34 passed，最终Unit/Architecture1226 passed；全源码Mypy、相关Ruff/diff及文档authority25 passed。计数重叠不相加，不替代GS-09自然生产链或完整R4；未部署、无交易所写入。

首次激活ENTRY接线修复（基于`ad916ed4`）：正式resolver新增四策略RED，证明首次ACTIVE_NEW的Generation pending版v与Authority committed版v+1被旧等号误判selection_generation_not_active。现仅在immutable Authority携带首次Owner授权引用时接受exact +1，普通激活仍exact相等；不放宽为任意大于关系。真实commit/reconnect后检验current-as-birth和exact-birth两种resolver入口，并注入上下漂移版本继续拒绝。首次/普通/比较集合独立切换专项10 passed；Generic repository + Selection ENTRY authority组合108 passed，仍不是自然Signal→Ticket全链。

Hourly恢复下一period预规划：原pure planner要求evaluated>=scheduled_effective，导致1h每个period都只能得到NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY。RED证明05:30为下一[06:00,07:00) period规划被错误拒绝。现仅在相邻period cutoff已到时允许预规划，first=max(period nominal effective,严格下一future close)；05:30可计划06:00，06:00及之后提交仍拒绝，不能提前计划尚未到cutoff的更远period。没有改正常05:00:08消费05:00规则，没有延长expiry、更新membership source或实际grant。该计划是Recovery Authority/Coordinator后续实现的输入，不是新增交易授权；真正恢复仍需DB事实、Owner、drain、source freshness及恢复rebase完整原子链，不能据此声称runtime liveness已验收。时钟/rebase/原timing专项34 passed。

Recovery存储准备验证：Generic repository + SOR materialization + Generic migration组合193 passed；新增8字段NULL保全断言后Static source migration专项4 passed；追加伪造recovery cursor版本拒绝后proof专项14 passed。Unit/Architecture1225 passed，源码及verify_schema脚本Mypy（159 files）、相关Ruff/diff、文档authority25 passed。计数重叠不相加；使用Docker PG，未执行完整Full-chain/R4，生产未修改。

Recovery持久化/读取准备（基于`0109d26c`）：未部署0008在原`brc_exposure_episode_current`增加8个nullable recovery字段（identity/revision、effective/first-close、armed/last-close/status、checkpoint version），没有新增Episode或恢复状态表。SQL约束与typed checkpoint一致，拒绝不完整字段、非未来first-close、无效status/version、trigger自证arming及非Generic Event；新的`authority_rebase_required`占位状态没有Episode ID和arm，原rising-edge reducer禁止从该状态直接TRIGGERED。typed readonly getter重连还原checkpoint。

`LockedObservationCursor`及PG proof函数同时冻结recovery checkpoint version，并以普通Episode/comparison/recovery三个游标最大值判断已消费close。四策略存储探针证明：即使普通Episode游标落后，recovery已消费的close仍在仓储和SQL proof两层拒绝；仅移除fixture recovery字段时同一proof才可通过，排除其他条件误挡。新字段全部从0006/0007来源保全清单排除，旧Static迁移要求8字段全NULL。测试采用显式SQL存储前置，不冒充正式恢复写入；尚无runtime checkpoint写入口、CAS或Recovery Authority绑定，尚未完成Observation接线及恢复全链，正常/故障二分完整验收仍待后续。

Recovery/Episode组合准备（基于`1aa3ce80`）：新增纯`advance_recovery_bound_exposure_episode`及frozen结果模型，将既有recovery checkpoint gate与正式rising-edge/comparison reducer组合，未复制Detector或Episode算法。四策略×无旧Episode/旧armed/旧triggered验证：首个未来TRIGGERED只抑制，未来NOT_TRIGGERED正式arm，再后续TRIGGERED创建唯一新Episode；重复close不推进、不重复Signal。新recovery revision不得继承旧arm，也不伪造Comparison revision；MPG/MI在recovery已armed后发生comparison变更，仍由原comparison barrier抑制。输入校验在抑制分支也拒绝错误scope、已消费close和无效Detector时间；typed组合结果不能伪造Signal或绕过comparison arming。

该增量的checkpoint尚未落PG、未被正式Observation调用；下一步仍需原Episode表持久化/版本CAS、恢复Authority绑定及Observation原子保存，不能据此声称GS-08/09 recovery full-chain完成。当前定向recovery+原Episode29 passed，生产无改动。

Recovery组合验证：完整Unit/Architecture1225 passed，全源码Mypy（158 files）、相关Ruff/diff、文档authority25 passed；追加typed结果不能夹带未armed comparison checkpoint的断言后定向29 passed。此次未修改Schema/PG/运行接线，未重复跑PostgreSQL或R4，不将纯组件测试替代数据库证据。

首次NO_CHANGE验证收尾：Generic repository + SOR materialization + Generic migration组合189 passed；最后补current指针约束后覆盖三个首次结果/normal proof/MPG-MI comparison-only的专项32 passed。Unit/Architecture1213 passed，全源码Mypy、相关Ruff/diff及文档authority25 passed。组合在最后一处约束修订前启动，最终修订以32项受影响路径复验，不冒充完整exact-R4；计数重叠不相加，生产未修改。

首次NO_CHANGE约束补强：额外RED证明同事务删掉Authority current指针后仍可提交首次mode转换；共享首次激活deferred guard现要求exact current pointer与Authority一起存在。该约束同时保护ACTIVE_NEW/VALID_EMPTY，不靠应用层顺序掩盖半套提交。未增加新Authority表或第二条mode写入链。

首次NO_CHANGE增量（基于`78eecc45`）：正常Snapshot Coordinator不再仅因Static pending拒绝同输入；仍先验证exact pending period/epoch、实际tradable/comparison输入不变、current认证、Owner/Policy及完整DB current-close proof。首次NO_CHANGE在原事务冻结Owner授权引用、切Dynamic/清pending并写递增后Control版本的Authority/current，不创建Generation/Vacuum。三个首次outcome复用同一PG Owner proof核验函数及deferred授权/mode约束；旧SOR不携带Generic授权字段。CPM/BRF2首次同名单RED已复现并修复；final-clock跨界整体回滚且pending Control完全不变，遗漏mode写入被PG拒绝，缺少pending授权引用拒绝。成功commit后dispose连接池再读证明模式/Authority持久化，exact ENTRY resolver允许该grant。Static scope和Owner proof仍为显式前置，不是Owner API自然链验收。

当前定向`prepare_generic_proof / empty_snapshot_coordinator / commits_and_restarts`组合30 passed；MPG/MI首次同名单但比较集合变化另加正式materialization回归，不把它们算成NO_CHANGE。后续仍须完成首次失败Static恢复、Generic恢复/continuity/supersession、birth successor和自然交易链等整卡验收；不将三个成功outcome接通扩大为GS-08 DONE。

首次空选择最终验证：Generic repository + SOR materialization + Generic migration完整组合185 passed；Unit/Architecture1213 passed，追加授权ID/semantic-digest篡改与非法ID断言后normal Authority专项20 passed；全源码Mypy、相关Ruff/diff、文档authority25 passed。上述数字有重叠，不相加，不替代整卡full-chain或完整R4；全部为Docker PG本地验证。

首次VALID_EMPTY增量（基于`5bb131bc`）：四策略RED复现首次空Authority写入但mode仍Static，expiry后resolver错误返回static_baseline允许ENTRY。现Coordinator为首次空选择冻结pending Owner授权和递增后的Control版本；empty事务校验exact pending/epoch/period、Owner proof、空Snapshot、Vacuum intent/drain/current后，同事务切Dynamic、清pending、写EMPTY Authority/current及VALID_EMPTY Vacuum。原Static Universe不被伪造成新授予目标，不创建Generation或Command；expiry后继续拒绝ENTRY，不fallback。共享0008首次授权deferred约束扩展到VALID_EMPTY，nullable唯一授权FK仍复用原表，SOR shape不变。

首次/普通空选择及非空激活专项16 passed：四策略新增省略mode更新在真实commit失败、提交前异常全回滚、重连保持原pending+无Authority+DRAINING_ENTRY、随后成功清pending、版本及授权引用准确、重复调用幂等、expiry仍无新交易。原Static scope与Owner授权仍为明确fixture；本测试无已有Ticket，不替代nonretroactive lifecycle full-chain。首次NO_CHANGE、失败恢复、跨period恢复等仍未完成；GS-04～09继续IN_PROGRESS，production_authority=NONE。

首次激活增量验证：Generic repository + SOR materialization + Generic migration组合首次为177 passed/4 failed，四失败均为新增测试SQL字面量`:wrong`被SQLAlchemy解释为缺失绑定参数；改用`:suffix`绑定后，覆盖全部失败的首次/普通激活专项8 passed（同时覆盖新增漏mode提交负例）。Unit/Architecture1213 passed，全源码Mypy、verify_schema脚本Mypy、相关Ruff/diff通过，文档authority专项25 passed。未伪称组合原始运行全绿，未执行完整R4；上述测试证据有重叠。

首次非空changed-set激活增量（基于`fc2cd0dd`）：STAGED Coordinator允许exact Static pending Dynamic period进入原ACTIVATE_GENERIC事务，而非放宽所有Static请求。Generation保留创建时Control版本；首次成功Authority冻结递增后的Control版本及`activation_authorization_id`，其FK引用已有Owner authorization，不复制Owner事实、不增加Authority表。验证purpose=selection_mode_change、totp_step_up、exact策略/目标mode/period及授权时间；mode转换、清pending、Universe/comparison/current、Generation/Vacuum及Authority同事务提交。0008仍未部署，新增nullable唯一授权引用及deferred约束，要求first activation的Generation→Authority版本恰好+1、最终Control及Owner proof一致；ordinary Dynamic版本仍相等。SOR不允许携带该字段，0006来源保全清单排除新增字段。

四策略首次及普通激活共8场景通过：错误purpose拒绝；人为省略mode更新在真实commit时被PG约束拒绝；提交前异常保留原Static pending/Control版本、旧Universe及STAGED目标；重连后成功变Dynamic并冻结新版本/授权，重复worker调用不增事件。授权行与原Static baseline仍为明确测试前置，不是Owner API/TOTP交互验收。首次VALID_EMPTY、首次NO_CHANGE、失败Static恢复与跨periodsupersession尚未接线；不得将本增量称作首次激活所有分支完成，GS-04～09及production_authority状态不变。

持久化增量最终回归：完整`integration/test_generic_selection_snapshot_repository.py`与`architecture/test_current_document_authority.py`组合113 passed；追加target状态/ACTIVE事件回滚断言后四策略专项4 passed，Ruff和diff检查通过。本次只修改测试与证据台账，不改变production实现、不重复声称完整R4。

2026-09-26持久化验收增量（基于`c487665c`）：四策略新增真实UoW独立提交测试，复用原Snapshot→Generation→fence/drain→warming/staging准备流程；Active baseline与certification仍为明确前置。Coordinator执行完但commit前注入异常，由正式UoW回滚；dispose连接池、创建新仓储后确认无Authority、Generation仍STAGED且无lease、旧current及RECONFIGURING Vacuum保留。再次正式激活真实commit后再dispose/read，验证ACTIVE Generation、exact Authority/current、RESOLVED_ACTIVE Vacuum；更换worker重复调用不增materialization事件、不产生Exchange Command。四策略故障+持久化专项4 passed；增加故障前的原六场景+四策略提交组合10 passed，计数不相加。该证据关闭正常激活的独立事务/连接重建缺口，不代表进程强杀、首次Static pending、timeout fallback、跨period恢复或自然Signal→Ticket验收；DB时钟仍为受控fixture。

本轮验证命令沿用`.venv/bin/python -m pytest <targets> -q -o addopts=--tb=short`：`integration/test_generic_selection_snapshot_repository.py + integration/test_selection_materialization_repository.py`共161 passed；最终锁顺序修订后Generic Generation专项6 passed；`unit + architecture`1213 passed，文档authority专项25 passed。全源码Mypy（158 files）、相关Ruff与diff检查通过；测试数字重叠、不相加，不构成整卡或R4认证。全部使用本地Docker PG，生产未修改。

2026-09-26 Coordinator接线增量（基于`5d3b8729`）：已DYNAMIC的STAGED Generation经共享Coordinator重新认证、构造DB current-close proof，并调用正式ACTIVATE_GENERIC原子入口；重复ACTIVE tick按Owner→Control→current Authority顺序核验DB时钟、epoch/version及真实Universe后返回同一Authority，不再claim或重复写事件。四策略及MPG/MI comparison-only场景验证Coordinator到ENTRY resolver的exact-birth正向读取；仍使用显式认证前置、受控DB时钟和外层rollback，不代表独立事务durable restart或自然Signal→Ticket全链。MPG比较缓存丢失在STAGED错误返回BLOCKED的RED已复现，统一Generic两阶段retryable分类后修复；临时certification不可用保持TARGET_WARMING，owner_action_required保持BLOCKED，无positive Authority且lease释放。SOR分类不变。首次pending mode、durable restart、fallback/recovery/supersession和其余整卡验收仍未完成，下面早期增量中的“尚待Coordinator接线”由本段更新，不将整卡标DONE。

已DYNAMIC的ACTIVE_NEW原子入口增量：advance_strategy_universe新增typed ACTIVATE_GENERIC请求绑定Authority/Generation/target/lease，先锁Owner/Control再进入共用Universe锁。正式入口复核STAGED readiness、Policy、drain、previous Universe/member/comparison/Authority、完整Episode覆盖及DB proof；同事务retire旧scope/Universe、启用target、CAS current、切comparison revision、提交ACTIVE Generation/RESOLVED_ACTIVE Vacuum及事件、Authority parent/binding/current，最终DB clock越界整体回滚，成功释放Generation lease。同ID/内容/current返回ALREADY_ACTIVE，不重复事件。六场景测试将原SQL切换探针替换为正式入口，保留受控时钟与外层rollback，覆盖错误lease/Owner版本、最终clock越界回滚、成功及幂等；不是实际生产部署或自然Worker全链路。仅允许selection_mode已DYNAMIC；首次pending mode、Coordinator STAGED分支接线、fallback/recovery及其余GS验收继续未完成。

STAGED再认证准备：现有advance_strategy_universe增加CERTIFY_STAGED操作，要求exact staged target和Generation，Generic仍核验Control/epoch/period/lease；重新运行原certification/warm/comparison readiness，不使用STAGED幂等快捷返回。只返回readiness，不修改target/Generation/current或授予ENTRY。四策略及comparison-only六场景验证正常就绪、temporary unavailable拒绝、WARMING冒用入口拒绝；旧STAGE_DYNAMIC行为保留。相关PG161 passed、Unit/Architecture1213 passed，全源码Mypy通过。该操作尚待最终ACTIVE_NEW原子应用事务调用，不代表运行时activation完成。

**目标**：把前三类domain约束组合成durable新交易authority状态机。

Generic正常Authority合同增量：现有`selection_authority.py`新增纯typed Generic正常/VALID_EMPTY模型，复用单Event binding、GenericSelectionPeriod、CurrentFinalCloseGrantProof与DynamicMembershipFreshness，校验Spec/cadence/Event/side、Snapshot/Generation/epoch身份、实际commit时间、固定24 comparison及正revision、fresh source一致性。ACTIVE_NEW必须绑定Generation；VALID_EMPTY只允许EMPTY binding且无positive proof；fallback/continuity/recovery不能冒充本合同。保留原SOR subtype与原Event-set测试。四策略合同专项与既有Event-set合计12 passed，完整Unit/Architecture1195 passed。该模型尚未接入PG原子grant、current指针或FinalGate，不产生任何生产授权，fallback/continuity typed证明仍待扩展。

Authority映射复核修正：Generic VALID_EMPTY明确禁止materialization_generation_id，与既有数据库valid_empty_shape及“零选择不建Generation”合同一致；四策略负向回归通过。当前PG仍有SOR-specific time/proof/grant constraints，Generic持久化尚未完成，不能直接把本纯模型写入现有行后解除Vacuum。

Authority epoch schema增量：未部署0008在原Authority表添加epoch/control version，旧SOR行默认sor-v0/NULL，不重写历史digest；复合FK绑定Snapshot ID+Spec+epoch。特别保留Authority period与来源Snapshot period分离，不能把continuity/fallback前期来源强制等同当前period；最初过严FK已由SOR回归暴露并修正。Spec subtype trigger禁止SOR携带Generic epoch及Generic冒用sor-v0，source0006清单排除新增字段。相关PG93 passed、Unit/Architecture1195 passed；完整Generic time/proof/grant schema、PG codec和原子activation仍未完成，此切片不是正向grant授权。

Authority proof storage准备：原Authority表增加current_close_proof、membership_freshness JSON对象列以及comparison definition FK/revision，旧SOR默认NULL；SOR subtype trigger拒绝携带Generic proof。JSON对象/完整comparison引用shape由PG约束，source0006保全清单明确排除新增列。相关migration/SOR materialization/source inventory PG93 passed、Unit/Architecture1195 passed。仅存储结构已准备，未放松原SOR time/proof/grant constraints，未实现Generic正向行提交、codec或current pointer切换；不能把此次结构测试当作完整proof语义认证。

Authority codec增量：现有PG Selection repository增加Generic parent row编码/解码，父表全部字段映射与唯一Event binding、installed Spec、typed proof/freshness及semantic digest交叉核验；拒绝错误epoch/period/first-close/proof-kind、错属或重复binding、额外历史引用及digest篡改。四策略正常/VALID_EMPTY roundtrip通过。两个JSON proof列显式none_as_null，真实Docker PG绑定测试证明None为SQL NULL而非JSON null，避免VALID_EMPTY插入形状冲突。Unit/Architecture1203 passed，全源码Mypy通过。此处尚无Generic INSERT/current CAS接口，原子activation和数据库Generic time/proof/grant语义约束继续未完成；不得使用codec单测替代PG写入/完整交易链认证。

Generic VALID_EMPTY存储验收：0008保留SOR原time表达式，仅Generic分支按已安装Spec校验1h/4h period及实际commit边界。VALID_EMPTY触发器要求同Spec/epoch/period的zero-member Snapshot、已提交来源以及无positive proof。四策略真实PG写入parent+EMPTY binding并经codec还原通过，错误epoch/expiry、非零Snapshot伪造empty及夹带proof均拒绝；current pointer/Command保持零。Generic正向proof合同未落库期间显式拒绝非VALID_EMPTY行，防止借用SOR旧proof；此为未完成实现阶段的fail-closed边界，不是最终功能。Generic repository62 passed，Unit/Architecture1203 passed；正式empty commit/current CAS/Vacuum resolution及正常activation仍待完成。

Generic empty原子repository增量：`commit_generic_valid_empty`锁定Owner/Selection Control与exact Vacuum/current，核对Snapshot、OPEN intent来源、版本及顺序，复用ENTRY drain blockers完成Vacuum VALID_EMPTY，并原子写Authority+EMPTY binding+current CAS。四策略PG测试覆盖Owner Pause拒绝、current写入故障导致整个事务回滚、同请求重试不重复写入；retry精确读终态Vacuum而非误用进行中查询。无Generation、无Exchange Command。该方法尚未接入Coordinator VALID_EMPTY分支和Generic FinalGate/current reader，不能据repository测试认定整个周期无ENTRY链路已验证；正常activation/fallback继续未完成。Unit/Architecture1203 passed。

Generic empty Coordinator/read增量：共享current表提供typed Generic exact reader及可选current锁，读取父行、唯一Event binding和installed Spec经codec/digest校验，真实readonly事务通过。Snapshot Coordinator空选择分支现在创建负向intent Vacuum、推进drain、无blocker后调用原子empty提交，再次tick复用同一current；四策略完成无Ticket场景且不创建Generation/Command。已有其他Vacuum明确要求supersession，不静默替换；待撤Ticket时仅推进正式drain单步。相关PG173 passed，empty/read专项8 passed，Unit/Architecture1203 passed。Generic ENTRY resolver/FinalGate仍未接线（原resolver依赖SOR pair），首次pending mode落地、真实有仓continuity与supersession仍未完成，不能据此宣布GS-08/09完成或部署。

Generic负向ENTRY resolver接线：共享resolve_selection_entry_authority按Generic control读取typed current，不再将单Event传给SOR pair解码器。Owner/Policy优先、进行中Vacuum阻断、live VALID_EMPTY拒绝、Dynamic缺失/过期拒绝；正向Generic行仍显式拒绝至完整Event-set verifier完成，Static仅在没有live grant且无birth authority时沿用baseline。锁定检查按Owner→Control→Vacuum→current顺序。四策略真实Observation入口证明VALID_EMPTY在市场抓取前拒绝且无Signal；同场景锁定resolver也拒绝，expiry不恢复Dynamic ENTRY。该切片未证明完整Claim/Ticket/dispatch链及正向grant可用。Unit/Architecture1203 passed，全源码Mypy通过。

Generic精确birth正向resolver增量：正常Authority的domain检查核对Control/Owner版本、epoch、Event/side/Universe、精确birth、最新合法hourly close与freshness；application读取当前ACTIVE Universe完整成员、真实Snapshot commit/member/epoch、ACTIVE Generation及唯一ACTIVE target、当前comparison revision和authority中断事实后才允许。NO_CHANGE successor兼容链尚未实现，当前仅精确birth或正式producer允许current-as-birth路径；不拿不完整continuity当兼容证据。四策略端口隔离测试覆盖可允许情形以及STAGED、missing target、Snapshot成员漂移、comparison变更和interruption拒绝；相关PG87 passed、Unit/Architecture1211 passed、Mypy通过。数据库仍拒绝Generic正向grant写入，尚未通过真实PG ACTIVE_NEW→ENTRY验收；本实现不代表原子activation或GS-09完成。

Generic grant coverage准备：原Signal repository按canonical selected成员顺序取得与Observation相同的Episode advisory/row锁，连不存在的Episode也锁定；读取正式Episode及comparison checkpoint最新close/版本，任一已消费或rebase抑制的close都拒绝授予，返回typed只读cursor证据且不创建Episode/arm。四策略PG验证已消费close拒绝、后续close可读证据；CPM双连接lock_timeout证明与Observation互斥，MPG/MI checkpoint分支证明抑制触发不能重新授权。专项10 passed。该coverage方法尚未接入最终grant事务及proof的完整coverage digest，不等于已证明commit跨close或atomic activation；相关工作仍待完成。

Generic proof coverage绑定：删除未部署CurrentFinalCloseGrantProof的单observation_cursor_version，替换为完整typed observation_cursors，要求1..16个canonical唯一成员/episode key及未消费close。Authority进一步验证coverage成员digest恰好等于目标成员、所有成员属于Candidate及exact Event/side domain key；完整集合参与既有semantic digest，无另存重复digest。缺成员/重复/错key/已消费close拒绝，不存在Episode不能伪造版本或last close。正常延迟切换与recovery专项37 passed，PG coverage/checkpoint专项10 passed，Unit/Architecture1211 passed。当前没有生产Generic正向Authority，故不提供旧scalar alias；最终PG grant事务仍未接通。

Generic proof事务准备：现有repository通过clock_timestamp读取真实DB毫秒时钟（非BEGIN固定的now()/transaction_timestamp）；只读事务测试证明时钟随事务推进。共享Coordinator模块提供prepare_generic_current_close_proof：精确Snapshot/Spec读取、首读clock确定latest close、完整Episode coverage加锁、二读clock构造proof；跨close或过期拒绝，不追认旧close。NORMAL最终commit纯校验拒绝时钟倒退/跨close/expiry，保留8秒/30秒/2分钟正常延迟语义。四策略真实PG proof准备与消费拒绝、clock跨界注入通过，相关专项8 passed；Unit/Architecture1211 passed，全源码Mypy通过。函数不写Authority，不证明continuity；最终activation必须在同事务调用并在提交前重验，尚未实现，不能把该函数当正向grant入口。

Generic proof数据库语义校验：0008增加无写入的brc_generic_close_proof_matches函数，由真实Snapshot/Spec、selected member行和原Episode/checkpoint重建完整JSON并逐字段比较，exact domain key按既有canonical算法计算；不接受缺成员、旧close、假commit、伪造cursor版本或额外字段。prepare_generic_current_close_proof在已持有Episode锁的同事务调用该校验，消费close后重新验证旧proof拒绝。该函数不获取grant权限、不改current、不代替Owner/Vacuum/target/continuity检查；正向Authority插入仍保持拒绝，最终activation接线未完成。Unit/Architecture1213 passed，全源码Mypy通过。

Generic正常freshness数据库校验准备：0008增加brc_generic_freshness_matches，从immutable Snapshot、Spec cadence和selected member行重建ACTIVE/zero-miss freshness JSON。四策略实际PG比较通过，延长membership_valid_until、更换member digest、将GRACE/miss混入正常grant均拒绝。该函数仍需由正式正常grant约束调用，尚未开放Generic正向INSERT；本切片不代表完成正常activation、staleness continuity或fallback。

Generic NO_CHANGE父行存储合同：0008在保留SOR原表达式的前提下，为Generic NO_CHANGE安装正常proof/grant形状约束；触发器调用exact PostgreSQL close-proof/freshness校验，核对Snapshot epoch/period及comparison current，延迟约束要求binding是exact当前ACTIVE Universe且成员digest等于冻结Snapshot。NO_CHANGE明确无Generation，domain同步拒绝携带Generation。四策略真实parent+binding插入/codec还原通过，proof/freshness/first-close/proof-kind篡改及current指针消失拒绝；测试不写Authority current，不授予ENTRY。相关迁移/SOR PG89 passed，Unit/Architecture1213 passed。Generic ACTIVE_NEW/fallback/continuity仍拒绝，NO_CHANGE正式current CAS/Owner控制/提交时钟最终重验尚未接通，不是完整生产授权。

NO_CHANGE就绪检查准备：现有Universe activation入口增加CERTIFY_CURRENT，只允许exact ACTIVE target，复用同一Registry/member/scope/certification/warm/comparison readiness检查并返回ALREADY_ACTIVE，不写current或scope状态；Dynamic source可使用该只认证分支，但不能据此激活WARMING/STAGED。PG测试证明ready replacement仍拒绝、现有ACTIVE认证无状态变化、temporary unavailable返回原blocker。该操作不授予Selection Authority，尚需由NO_CHANGE原子current提交事务调用，不能据此标记NO_CHANGE链完成。Unit/Architecture1213 passed。

ACTIVE comparison读取修正：ACTIVE比较输入改由独立current Comparison Binding决定，而非Universe历史source_kind推断；读取先核对exact current Universe，再复用typed binding reader的definition/member/digest/Static来源验证。WARMING/STAGED仍由目标Generation Spec确定输入，未提前切current。测试覆盖沿用Static来源Universe但当前合法fixed24绑定时读取24、current Universe消失拒绝；相关PG123 passed。旧activation query-bound测试更新为正式MAX_UNIVERSE_MEMBERS+1而非已废弃的11，仍要求每个相关查询有精确LIMIT。Unit/Architecture1213 passed。NO_CHANGE原子current提交仍未完成，不能把此次读取修复当作交易授权。

NO_CHANGE原子repository增量：commit_generic_no_change在Owner/Selection Control、Vacuum/current锁下验证版本/epoch，复用CERTIFY_CURRENT及Policy ENTRY检查，读取真实Snapshot与当前成员、comparison、Episode coverage并核验DB proof。拒绝从negative/不连续历史grant直接续期；记录parent+binding+current CAS后再次读取DB时钟，越界失败由调用方事务回滚；相同ID/内容/current支持幂等。四策略PG专项覆盖旧Owner/current版本拒绝、最终时钟跨界导致全部写回滚、成功重试与同current版本复用，并调用真实ENTRY resolver接受该精确grant且零Ticket/Command。此处ACTIVE Universe、certification/warm与mode是显式测试前置，不证明首次mode切换或自然Coordinator NO_CHANGE分支已经接通；successor兼容链、ACTIVE_NEW/fallback仍未完成。Unit/Architecture1213 passed，全源码Mypy通过。

NO_CHANGE Coordinator接线：已处于dynamic_selection且Tradable/comparison输入不变时，正式Snapshot Coordinator分支读取current、认证当前Universe、构造锁定coverage/DB clock proof和freshness，再调用原子NO_CHANGE current提交。相同Snapshot/current重复tick复用，不写第二revision；数据库实际expiry或Owner/Control版本漂移拒绝重试。首次static pending仍明确FIRST_ACTIVATION_REQUIRED，不静默跳过mode转换。四策略真实PG借用已持coverage锁的同一事务调用正式Coordinator，验证成功、幂等、expiry重试拒绝及ENTRY resolver；仍使用显式active/certification前置，不证明首次activation或worker自动调度。Unit/Architecture1213 passed；ACTIVE_NEW/fallback、continuity/successor及其余GS验收仍未完成。

ACTIVE_NEW Schema合同：Generic正常proof/grant shape现接受带Generation的ACTIVE_NEW，仍保留SOR原约束。提交时延迟校验要求exact current ACTIVE成员、comparison、同Snapshot/Spec/epoch/Control的ACTIVE Generation、同effective时间的Universe activation/Generation terminal/Vacuum RESOLVED_ACTIVE、同fence身份及Authority current，并要求previous ACTIVE baseline已retired。六种场景（四策略及两种comparison-only）通过同事务SQL探针，篡改Generation activation/fence时间、遗漏Vacuum resolution或current任一项均拒绝。探针成功后刻意rollback，避免污染后续staging负向用例；不是正式应用activation接口，也不代表真交易。相关迁移/SOR PG89 passed、Unit/Architecture1213 passed。Owner/Policy/live clock最终检查及正常应用原子切换仍待接通，fallback/continuity继续未实现。

Generic准备事务增量：现有Selection repository新增typed `PENDING→DESIRED` 写边界，锁定Control/Generation并校验epoch、Control version、source period、lease owner/epoch/expiry，CAS更新并追加唯一DESIRED event。四策略集成用例开始通过正式claim→desired，不再跳过该步骤；错误lease拒绝、重复调用保持首次desired时间。后续MATERIALIZING仍是明确标注的测试前置，不能据此宣称fence/drain或Coordinator已完成。

Generic fence事务增量：复用`open_generation_entry_vacuum`及原Vacuum/event表，Generic分支要求DESIRED、exact Control/epoch/period与worker lease，原子保存OPEN/DRAINING_ENTRY事件和Generation DRAINING_ENTRY/fenced_at。四策略用例开始走真实claim→desired→fence；错误epoch在写Vacuum前拒绝，跨事务读回负向fence及Generation状态通过。SOR调用签名保留默认无Generic token路径，不增加第二drain链。当前仍未把Generic drain completion与Coordinator完整接通，测试中的MATERIALIZING转换仍明确标为前置，不能宣称GS-08完成或授权生产。

Generic空ENTRY drain增量：共享`mark_entry_vacuum_drained`按真实Generation类型读取单Event或SOR subtype，并在任何drain更新前锁定、核对完整Vacuum行，拒绝伪造/过时输入。四策略测试已改为正式`drain_strategy_entry_vacuum_once→RECONFIGURING/MATERIALIZING→install`，删除直接UPDATE MATERIALIZING前置；无新的drain链。此处没有待撤ENTRY，不能代替Generic有单取消/部分成交/未知结果/旧Ticket保护的full-chain验收，也不等于Coordinator自动调度或最终Authority完成。四策略专项4 passed；Unit/Architecture1190 passed，全源码Mypy通过，生产未修改。

Generic Coordinator准备接线：同一`coordinate_selection_materialization_once`入口接受typed Generic Generation request（仅DB Generation ID及worker ID，不接收成员名单），读取Owner control、取得fenced lease、分步推进PENDING→DESIRED→Vacuum fence→空ENTRY drain。每步释放本次lease；Owner Pause返回无新增fence，已有lease返回GENERATION_LEASE_HELD等待状态。四策略集成改为调用该正式入口而非直接串联准备仓储；直接仓储负向测试仍保留。仅已提交Generation的准备阶段已接线：Snapshot→Generation发现/创建、MATERIALIZING目标安装/预热自动分支、STAGED atomic activation/fallback及Worker hosting仍未完成；后续状态显式BLOCKED，不产生正向Authority。Unit/Architecture1191 passed，全源码Mypy通过。

Generic Coordinator目标接线增量：MATERIALIZING先验证同Generation的RECONFIGURING Vacuum，再由DB Spec/Snapshot及正式安装上下文确定target，通过现有install/stage入口推进。全局warming槽被占时返回TARGET_WARMING/GLOBAL_WARMING_SLOT_BUSY，不另建队列；就绪后返回GENERATION_STAGED，保留当前Universe及负向fence。临时认证/比较缺源与非transient失败分别等待/阻塞，未实现fallback的失败不伪造成功。四策略测试经Coordinator安装和stage，保留底层负向lease/Control测试；相关PG135 passed、Unit/Architecture1191 passed、全源码Mypy通过。Snapshot→Generation发现创建、deadline失败回收、atomic activation/fallback及hosting仍待完成，GS-07/08不标Done。

Generic Snapshot handoff增量：同一Coordinator入口新增仅Snapshot ID/worker ID的typed request，自动读取DB Current Universe/member和Comparison Binding冻结previous baseline并提交PENDING Generation；调用方不再提供baseline。已存在的Generation按原身份进入准备/安装分支，不重写baseline；首次调用校验mode、epoch、生效/expiry/commit时间。Static模式不创建Generation，过早调用NOT_DUE。Generator ID构造收敛到domain单一函数，原ID/digest不变。四策略用例改走此handoff；已有负向Vacuum的supersession、NO_CHANGE及VALID_EMPTY最终Authority仍未实现，分别明确阻塞/intent，不据此授予交易。Unit/Architecture1191 passed；不代表自动发现due Snapshot的hosting或GS-08完成。

comparison-only切换修复：NO_CHANGE分类现在同时核对Tradable members与comparison输入；MPG/MI名单相同但Static比较子集→fixed24仍创建Generation并走预热。0008的current-digest唯一索引按ACTIVE/待切换两类区分，允许旧ACTIVE与一个同digest warming/staged目标并存，但同类重复继续拒绝；全局单warming及单ACTIVE约束保留，旧Universe不提前retire。新增两策略同名单场景经handoff→fence/drain→warming→staged通过，直接重复STAGED插入仍失败。Coordinator失败不再在aborted transaction释放lease遮蔽原错误，故障注入证明claim/目标同事务回滚且可重试。相关六场景PG专项6 passed，Unit/Architecture1213 passed。此修复不等于comparison atomic activation/rebase全链路完成；NO_CHANGE Authority本身仍待实现。

有单drain审计补充：现有`support/selection_vacuum.py`的Spec来源固定SOR，不能只换StrategyGroup就当作Generic验收。共享Vacuum模型现明确拒绝SOR Spec与非SOR group混用，SOR有单drain与Vacuum单测合计21 passed。Generic有单测试必须安装对应真实Spec、使用合法Ticket身份，仍待补齐，不计为已验收。

Generic prepared-ENTRY验收增量：CPM/MPG/MI/BRF2使用对应注册Event、ExitProfile Binding、方向（含BRF2 SHORT）与正式安装的Generic Spec，先经issue_ticket签发，再设置明确的负向Vacuum前置并调用正式drain。prepared ENTRY变为SUPERSEDED，Ticket进入entry_rejected，Reservation/lane/Netting Domain释放，冻结Ticket字段（除状态）保持不变。保留原SOR分支，五分支专项通过。测试从已签发Ticket开始，未证明Selection/Coordinator自然产出该Ticket；未覆盖Generic已发送未成交、部分成交及unknown cancel，不能升级为GS-08/09 full-chain完成。

Generic已发送零成交验收增量：同一合法Ticket/Spec前置扩展为五策略×prepared/sent两种状态，合并原独立SOR零成交用例，避免重复覆盖。sent路径经正式ENTRY派发、Vacuum CANCEL持久化、CANCEL派发、订单消失事实、ZERO_FILL_CLOSED，随后释放Reservation/Netting Domain；每Ticket仅一条ENTRY及一条CANCEL，冻结字段除状态外不变。相关drain模块17 passed。此处venue为recording/fake、Vacuum为明确前置，不是生产实盘或Selection→Ticket自然链证据；Generic partial/unknown cancel仍待验收。

Generic unknown-cancel增量：上述矩阵加入unknown分支并合并旧独立SOR用例；五策略经过CANCEL派发超时、WAITING_UNKNOWN_OUTCOME、正式recover_unknown_command确认target仍open、随后才生成CANCEL generation 2。unknown期间再次调用dispatcher得到NO_COMMAND且禁止任何venue execute，SHORT使用sell事实。该分支证明安全重试边界，不声明第二次取消后的最终关闭或部分成交保护已经验收；Generic partial与自然producer→Ticket仍待完成。

Generic drain闭环补充：unknown分支现继续派发generation 2、确认订单消失、ZERO_FILL_CLOSED并验证Reservation/Netting Domain释放及冻结Ticket字段保全。合法Ticket/Spec构造抽为复用夹具，部分成交保留和Initial Stop拒绝分支扩展至四个Generic及SOR；保护前原占用不释放，保护后仓位/Reservation保留，未保护或拒绝进入受控退出。MPG按冻结33% TP1比例，0.002成交/0.001步长无法拆分，单独断言精确数量CONTROLLED_FLATTEN且不释放占用；合法保留夹具改为0.006请求/0.004成交，不改变策略参数。测试仍从已签发Ticket与显式Vacuum前置开始，不等于自然Selection→Ticket或最终Generic activation验收。

**实施增量（未Done）**：共享`StrategyEntryVacuum`模型及调用方统一使用`period_anchor_ms`，与现有物理字段一致，无旧名alias/双字段；SOR保留day边界，Generic校验已冻结Spec的1h/4h cadence。四策略非midnight Vacuum经现有Owner-pause repository写入及读回通过，不建立第二Vacuum/drain路径。此证据不等于Generic Coordinator的DESIRED→fence→drain已接通。受影响回归另外暴露历史0003 source verifier从当前metadata误读取新增comparison列；仍需修复准确的source manifest，不允许以旧schema runtime fallback绕过。生产未修改，全部GS完成状态不变。

**允许**：materialization coordinator、authority/Vacuum/audit repos、typed proof/ports、Owner pause integration及状态机tests。**禁止**：Network I/O置于DB transaction；不经官方grant直接改Universe current。

**RED与要求**：

1. continuity在Selection outcome之前可执行，且新策略受绝对stale deadline；source失败不直接授权fallback，fresh未生效Desired不能续旧名单。
2. due与future正确区分，global slot就绪后fence；只有snapshot确定后才关闭旧新交易权限。drain确认先于warming，audit/proof先于Observation。
3. fresh target atomically切Event set/comparison/authority/mode/transition revision；SOR LONG成功SHORT失败全组回退。NO_CHANGE不能跳过rebase/stale/未解Vacuum。
4. EMPTY完整Event shape、无零成员Universe，不fallback，旧合法Ticket不追溯撤销；stale/Owner pause EMPTY parent原因明确。
5. firstStatic失败保持mode Static和原comparison checkpoint；已Active后Static rollback是真comparison transition。Owner pause最高，普通fallback不清pause/refresh年龄。
6. 老Vacuum已指向本期Generation则继续materialization；新effective Snapshot、empty、old lease callback、period过期严格supersede；source过期无合法proof保持blocked。

7. **GS-08-SOR-INCIDENT-01**：`now < first eligible close`时Gap Audit不得调用market replay，保持pending；用recording source证明零调用，不能靠构造4根OR后的空path绕过。
8. **GS-08-SOR-INCIDENT-02**：expired session不得伪造retroactive Authority。首次Dynamic失败只走正式recovery/supersession，保留previous Static pair及`selection_mode=static_baseline`；failed Audit不能无限卡住后续合法恢复。测试覆盖failed Audit、重启、新period与Owner pause交叉路径，禁止以直接SQL修复作为运行方案。

2026-10-08 failed Audit跨Session接管补强：在旧Generation的真实Gap Audit先变成`AUTHORITY_GAP_SOURCE_INTEGRITY_FAILED`、当前Session仍零新增Authority之后，提交下一Session的有效Snapshot；正式Coordinator将旧Generation设`SUPERSEDED`、旧Audit保留原失败原因、新Generation继续接管同一Vacuum，旧Session Authority数量不增加。与原pending Audit被新Snapshot合法supersede的分支参数化复验2 passed；Owner Pause和expired窗口仍由独立现有测试覆盖，不用直接SQL修复旧Audit。SOR materialization全模块78 passed、Ruff/diff通过；不把这一条扩称全部GS-08或R4完成。
9. **GS-08-HOURLY-CLOCK-01**：NORMAL证明完整时，05:00:08可消费05:00最新未消费close；8秒/30秒/2分钟延迟不能仅按耗时变成RECOVERY。迟到Snapshot、已消费close、freshness失效、commit越界拒绝。RECOVERY原因一旦成立，禁止恢复后降级NORMAL追认；future-close-only与独立recovery revision rebase必须覆盖四策略，先未来合法NOT_TRIGGERED再更晚TRIGGERED。首个未来close不小于expiry时记录NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY及miss，零新Signal/Ticket；下一合法period才能恢复。SOR保持专属Gap Audit路径。

**验证**：PG并发事务/barrier测试+recording network；current-close先consume或先switch两种顺序、crash每个commit点、重试terminal authority；SOR近期四类bug regression。

**Done**：全部新authority可trace proof/source/epoch/Event set，positive grant不能绕过rebase/stale/EMPTY/Owner；existing Ticket未变；§3.4相关SOR子集PASS。

### GS-09 — Signal / Claim / Ticket / ENTRY dispatch

本轮comparative第二Dynamic末版回归：Static/二次epoch/Generic activation28 passed（含四策略正式二次epoch natural Ticket）；既有Full-chain/文档76 passed、文档更新后25 passed、Ruff/diff通过。仅tests/docs，未跑全Unit/Mypy或最终R4，集合重叠不合计。

2026-10-09MPG/MI第二Dynamic epoch自然交易增量（基于`ee864869`，GS-06/08/09关联）：已有正式Static→新Owner Dynamic→新epoch首Snapshot→新Active Universe链继续到comparative producer。选择一个实际new selected member，以该member trigger path与其他候选flat path构建真实fixed24 comparison cache、保持exact revision，不缩为当前tradable成员；新epoch首TRIGGERED只COMPARISON_REBASE_REQUIRED。随后两个hourly cutoff由正式Runner读取完整Candidate24、提交同新epoch及exact前驱Snapshot，same-members NO_CHANGE grant各自最新未消费close，合法NOT_TRIGGERED完成comparison arm、更晚TRIGGERED只产生新Signal。Signal/Claim/AdmissionDecision/Ticket冻结最终new epoch Authority/Snapshot/Universe，经唯一durable ENTRY/recording acceptance、保护/Runner/flat/Settlement/Review至terminal；旧Static Signal未被挑选为新Ticket，旧Job epoch不能claim。四策略完整Static/二次Dynamic成功专项4 passed，MPG/MI三期Snapshot cardinality/epoch/predecessor与首根suppression已明确assert。仅tests/docs变化，本地market/fill/economics不是实盘收益证据；第二epoch拒绝/unknown/partial与positive activation并发、pause非空恢复及逐卡认证仍未闭合，GS-04～09未Done、非exact R4、production_modified=NO。

本轮non-comparative第二Dynamic交易末版回归：正式Static/二次epoch/Generic activation组合28 passed；既有Full-chain/文档76 passed、台账更新后25 passed、Ruff/diff通过。仅tests/docs，未跑全Unit/Mypy或最终R4，集合重叠不合计。

2026-10-09CPM/BRF2第二Dynamic epoch自然交易增量（基于`c6a44741`，GS-06/08/09关联）：既有正式Owner首次Dynamic→Static rollback→再次Owner Dynamic排期/新epoch→Runner首Snapshot→新Universe activation链，继续在新Active non-comparative scope以合法NOT_TRIGGERED及更晚TRIGGERED closed bars完成自然Signal/Claim/AdmissionDecision/Ticket/durable ENTRY→recording venue→保护/Runner/flat/Settlement/Review终态链。Snapshot无旧epoch前驱，原rollback baseline唯一且不重捕获，原Static目标retired；新交易冻结新epoch Authority/Snapshot/Universe，初版fixture在正常activation commit前attempted close+1被拒，按真实created_at+1动作时间修正而非放松authority effective gate。CPM LONG/BRF2 SHORT专项通过，旧Job epoch阻断仍在同链断言；末尾正式Owner Pause改为在新交易完整terminal后，避免时钟倒退。当前不代表MPG/MI第二Dynamic comparison rebase及小时后续新Snapshot/入场fault完整矩阵，也不是有仓切换认证。仅tests/docs补强，fill/flat/Review为local fixture，GS-04～09未Done、非exact R4、production_modified=NO。

本轮Static新ENTRY fault末版回归：正向/四fault20 passed；既有Full-chain/文档76 passed、台账更新后文档25 passed、Ruff/diff通过。本轮tests/docs-only，未跑完整Generic、Unit/Mypy或最终R4，集合重叠不合计。

2026-10-09新Static自然ENTRY拒绝矩阵（基于`74302aff`，GS-09关联）：四策略复用正式Dynamic旧Ticket终态→Owner Static cutover→comparison/recovery合法arming→新自然Signal链，分别在Claim前、已计算Claim到Ticket之间、prepared ENTRY dispatch之前正式Owner Pause，以及dispatch前action-time account/admission facts过期。前两类按新signal精确查询零Ticket/Command，避免将已存在的旧terminal历史当作本次副作用；后两类prepared唯一ENTRY拒绝/超越且recording venue无新execute，Reservation/Netting Domain释放，原历史不改。Claim→Ticket间Pause来自独立Owner UoW，非修改mock布尔；Static birth仍NULL，不伪造Dynamic Authority。四策略×四fault16分支PASS，与四策略正向第二Static Ticket继续共享同一helper，新的Review/order/episode identity不重用首笔；测试中新账户事实/fill/Review为local fixture，非收益声明。仅tests/docs补强、无生产行为改动，不代表第二Dynamic epoch或所有positive Universe switch/freshness矩阵已完成，GS-04～09未Done、非exact R4，production_modified=NO。

本轮comparative Static新交易末版回归：四策略专项4 passed；自然入口/hourly faults60 passed；既有Full-chain/文档76 passed、更新文档后25 passed、Ruff/diff通过。仅tests/docs，未跑全Unit/Mypy或R4，集合重叠不合计。

2026-10-09MPG/MI Static recovery后新自然交易增量（基于`d3fae989`，GS-06/08/09关联）：将已有Static后第二Ticket链扩展到两个comparative策略，在旧Dynamic Ticket终态后exact-load新Static Universe、冻结Static activation proof及其comparison revision，比较输入使用实际baseline成员而非强行fixed24。首个future close给真实TRIGGERED，由RECOVERY_REBASE_REQUIRED抑制；更晚NOT_TRIGGERED沿正式Observation同时完成合法recovery/comparison arming，再更晚TRIGGERED只产生一个新Signal。该Static Signal经正式issue_ready_signal/Claim/AdmissionDecision/Ticket、durable唯一ENTRY和recording venue/protection/Runner/flat/Settlement/Review至terminal，birth Selection Authority=NULL而不伪造Dynamic权限。四策略Static后续交易专项4 passed，最终每策略两笔terminal Ticket/不同Episode/不同Entry order ID，旧Dynamic历史来源保持。生产代码未改，无SQL写入Signal/checkpoint，无alpha参数变动；本地模拟fill/费用/Review不作为实盘收益证明。第二Dynamic epoch交易与完整拒绝/并发矩阵仍待闭合，GS-04～09未Done、非exact R4，production_modified=NO。

本轮新Static natural ENTRY末版回归：自然入口/hourly faults60 passed（含两条新增Static第二Ticket终态链与不同order/episode身份断言）；既有Full-chain/文档76 passed、文档更新后25 passed、Ruff/diff通过。本轮仅tests/docs，未跑全Unit/Mypy或最终R4，集合重叠不合计。

2026-10-09CPM/BRF2 Static切换后新自然交易增量（基于`730d5bbe`，GS-06/08/09关联）：在原正式Owner→Runner→Dynamic自然Signal/Ticket链、原Ticket protected时完成正式Static cutover并让原Ticket终态关闭后，新的Active Static scope分别消费合法NOT_TRIGGERED与更晚TRIGGERED closed bars，再由原issue_ready_signal/Claim/Ticket/durable ENTRY/recording venue/reconcile/protect/TP1/Runner/exit/Settlement/Review闭环。不直接写Signal或checkpoint；两策略各最终2条terminal Ticket、2个不同Exposure Episode与2条ENTRY、2个不同accepted Entry order ID。Static Signal/Claim/AdmissionDecision/Ticket不伪造Dynamic Selection Authority（birth字段NULL），而是原Control/current Universe与已冻结Static activation proof；新Ticket仍冻结同Event/Universe/Initial Stop/Exit Binding，旧Ticket lineage不改。复用原入场helper时给每条Ticket独立Review/venue ID，避免第二笔复用首笔fixture身份。CPM LONG/BRF2 SHORT专项2 passed；这不是MPG/MI comparative新Static Entry或第二Dynamic epoch交易认证。所有fill/flat/费用与Review经济值为本地fixture，非实盘/收益证明；GS-04～09未Done、非exact R4，production_modified=NO。

本轮Pause EMPTY atomicity末版验证：EMPTY/Gap/early Pause28 passed；Generic migration/SOR materialization/ENTRY Vacuum163 passed；源码+0008 Mypy161 files、文档25 passed、Ruff/diff通过。集合重叠不合计，未跑最终R4或全Unit/Generic。

2026-10-09Pause→EMPTY最终原子性补强（基于`3f15b519`，GS-04/08关联）：在四策略×PENDING/DESIRED暂停后合法resume/latest EMPTY上下文，故障替换commit_generic_valid_empty，使应用只把已retarget的Vacuum写VALID_EMPTY/resolve而不insert负向Authority/current；真实PG此前DID_NOT_RAISE八分支RED。现扩展既有brc_validate_generic_gap_empty_resolution deferred guard到supersedes_owner_pause=true的EMPTY intent，要求最终同Spec/current/目标Snapshot/period/resolved timestamp的VALID_EMPTY negative Authority原子存在；无新表/平行linkage。非法事务整体回滚，正确正式commit随后继续PASS。初版测试误以为empty handoff分两次tick，实际无单路径同一事务已能完成，已在正确commit边界注入而非人为拆生产事务；没有修改EMPTY业务规则。四策略负向/正向复验包含在相邻EMPTY/Gap组合中，仍不能替代非空pause恢复/新Universe activation并发或完整GS-04～09认证。全部Docker PG，无生产修改，非exact R4。

本轮generation-free Pause/EMPTY末版回归：20分支PASS；Generic migration/SOR materialization/ENTRY Vacuum163 passed；Unit/Architecture1327 passed、Mypy161 files、Ruff/diff、文档25 passed。集合重叠不合计，未跑最终R4或末版完整Generic模块。

2026-10-09generation-free Pause→最新EMPTY接管增量（基于`f52b9a01`，GS-08关联）：四策略PENDING/DESIRED正式Pause终态后完成无单drain，再正式Owner Resume并提交下一有效zero-member Snapshot；RED复现OWNER_PAUSED Vacuum永久返回GENERIC_EMPTY_REQUIRES_SUPERSESSION。现在沿原retarget_generic_empty_vacuum接管同一原fence/drain，要求Owner enabled且exact version/control/epoch、latest effective EMPTY、generation-free已完成且无unresolved drain/Ticket；仅接受精确booltrue/相同drain time的完成事件。VALID_EMPTY_INTENT在Vacuum更新前提交，0008 BEFORE trigger独立核验原状态/time/version/完成proof、新Source latest/expiry/Spec/control及Owner，不能只信Python。篡改supersedes_owner_pause flag在真实PG拒绝，原Vacuum与Authority整体回滚；合法步骤随后提交唯一VALID_EMPTY负向Authority，旧ABANDONED Generation/原Universe不改，原Vacuum ID/fence/drain保留为VALID_EMPTY终态，零新Ticket/Command、无fallback previous。四策略×两early状态8条恢复链及Static/Gap/原EMPTY相邻组合20 passed。本轮不声称暂停后的非空warming/staged/DRAINING接管或有单恢复已完成，GS-04～09未Done、非exact R4，全部Docker PG，无生产修改。

本轮Static unfenced Pause末版回归：early/draining/正式Static链52 passed；SOR materialization/ENTRY Vacuum/既有Full-chain193 passed；Unit/Architecture1327 passed、Mypy160 files、文档25 passed、Ruff/diff通过。集合重叠不合计，非exact R4。

2026-10-09Static未围栏Owner Pause增量（基于`5de58b6f`，GS-08关联）：已有Dynamic early-pause矩阵扩展到正式Owner Static intent创建的PENDING/DESIRED Generation，四策略Static八分支RED复现仍可行动。Static Coordinator现与Dynamic共用原Owner-created OPEN Vacuum、mark_entry_vacuum_draining及abandon_generation_for_owner_pause，不新增取消表/队列或来源；旧Static intent终态ABANDONED、terminal time/lease清理，Generation.fenced_at仍NULL，不伪造已materialize。下一同Coordinator tick允许generation-free Owner-paused drain完成且保持fence/Current/Authority；仅OwnerPause持有负向权限，没有fallback/grant。Dynamic/Static×PENDING/DESIRED×四策略16分支PASS，语义digest/原Universe与Authority/零目标均保全。此处仍为无Ticket场景；generation-free Pause后的新Owner Static授权、Dynamic最新Selection恢复/空集、prepared/sent/unknown/partial交叉仍需闭合。全为Docker PG，无生产修改，GS-04～09未Done、非exact R4。

本轮unfenced Pause末版回归：未围栏Pause/DRAINING Pause/Generic activation32 passed；SOR materialization/ENTRY Vacuum142 passed；Unit/Architecture1327 passed、Mypy160 files、Ruff/diff、文档25 passed。集合重叠不合计，不构成exact R4。

2026-10-09Generic未围栏请求Owner Pause增量（基于`f930f030`，GS-08关联）：四策略真实后续Generation处于PENDING/DESIRED时正式Owner Pause，RED复现旧请求仍可行动。Dynamic Coordinator现复用Owner已开的OPEN Vacuum（没有才沿原Owner Pause边界创建），推进原drain状态，再沿既有shared abandon函数终态ABANDONED并清lease；Generation没有materialization fenced_at，不伪装进入warming。后续同tick入口对ABANDONED且Owner-paused的generation-free Vacuum完成无单drain，保持原Vacuum/fence，旧Current/Authority及目标列表不变、不grant。初版误用不存在的drain方法名及仅处理新建Vacuum，按实际mark_entry_vacuum_draining接口和Owner Pause已有OPEN事实修复。共享成功夹具中原临时raw Pause/re-enable会与新终态语义冲突，改为独立savepoint全回滚的negative probe；正式Pause→恢复测试仍单独验收，不绕过真实Owner状态。四策略×两状态8分支PASS、源码Mypy160 files、Ruff/diff及Unit/Architecture1327 passed；现有无单DRAINING/Static恢复相邻重验。仍缺Static未围栏取消、generation-free OwnerPaused Vacuum在resume后的合法supersession、新ENTRY/有单交叉，不标GS-04～09 Done或exact R4。全部Docker PG，无生产修改。

本轮non-comparative hour-only末版验证：四策略hour-only4 passed；自然入口/hourly faults60 passed；既有Full-chain/文档76 passed，更新文档后25 passed，Ruff/diff通过。本轮tests/docs-only，未重跑全Unit/Mypy或R4，集合重叠不合计。

2026-10-09CPM/BRF2独立hour-only末尾回滚增量（基于`60b9f45c`，GS-08/09关联）：把既有正式protected Ticket→Static cutover事务末尾跨close测试扩展到两个non-comparative策略。测试明确crossed时间仍早于本次30s lease及原1800s materialization deadline，故障发生于事务内mode/current已经切Static后的最终clock check，返回STATIC_ACTIVATION_COMMIT_CROSSED_CLOSE而非DEADLINE。四策略独立hour-only4分支均验证Current/Authority/Control/STAGED Generation/原Vacuum/完整Ticket/Aggregate/Reservation/保护Command回滚，随后旧Ticket在Selection-read-forbidden安全链内继续至terminal。新增CPM/BRF2并不伪造hourly PRE_FENCE_CONTINUITY；它们以本策略的4h source contract建立合法准备状态，不改变NORMAL/RECOVERY判定。本轮仅tests/docs补强，未改生产逻辑，仍需实际positive Universe activation并发、新Static/第二Dynamic自然Entry及完整卡级证据，GS-04～09未Done、非exact R4。全部Docker PG，无生产修改。

本轮暂停drain证明末版回归：16分支PASS；Generic migration/SOR materialization/ENTRY Vacuum163 passed；源码+0008 Mypy161 files、文档25 passed、Ruff/diff通过。集合重叠不合计，未跑最终R4。

2026-10-09暂停drain完成证明类型攻击补强（基于`58ef3be7`，GS-08关联）：四策略在正式Static paused-drain completion的INSERT边界分别注入entry_drain_complete=false和JSON字符串"true"，再经正式Owner Resume/新授权及到期Coordinator handoff。false已被既有独立SQL拒绝；string_true四分支RED证明旧->>/astext文本比较把字符串当布尔true，能够commit新retry。现Python repository与0008 SQL handoff predicate统一精确JSONB布尔true比较，普通暂停、false、string均不能证明完成drain；正常booltrue仍沿原恢复activation成功。攻击失败事务保持原OWNER_PAUSED Vacuum/Current Authority，零新Generation；没有修改真实drain判定或新交易范围。Dynamic/Static正常与两类损坏证明共16分支PASS，源码+0008 Mypy161 files、Ruff/diff通过；全部Docker PG、无生产修改。不代表有单drain证据或GS-04～09 Done，非exact R4。

本轮paused-drain Static恢复验证：8个Dynamic/Static分支PASS，末版Generic migration/SOR materialization/ENTRY Vacuum163 passed、源码+0008 Mypy161 files、文档authority25 passed、Ruff/diff通过。集合重叠不合计，未跑最终R4或末版完整Generic模块。

2026-10-09Static暂停drain后的重新授权恢复增量（基于`c0c7b1a1`，GS-08关联）：四策略正式Static Generation在DRAINING阶段Pause→终态ABANDONED→下一Coordinator tick确认无Ticket drain并记OWNER_PAUSED后，正式Owner Resume再用新TOTP授权排期，复用既有terminal reauthorization/handoff/activation全链。RED复现Python/独立SQL原drain provenance仅认ENTRY_DRAINED，拒绝实际上由正式drain产生的OWNER_PAUSED + entry_drain_complete=true。现两个边界都只额外接受同Vacuum、occurred_at恰等于原drained_at且明确完成flag的该事件；普通OwnerPause事件不能冒充完成drain，无直接SQL清fence、无终态revival。正式重授权仍保持旧source/Control/原Vacuum直到新操作到期；相同原fence/drain被保留，新目标重新warming/staged，typed RECOVERY proof/未来close/rebase及PG payload攻击仍有效。四策略Static成功恢复加Dynamic原pause drain合计8分支PASS；不代表有单cancel/unknown/partial恢复、unfenced pause或全部GS-08认证完成。全为Docker PG，无生产修改、无真实exchange写入，GS-04～09未Done、非exact R4。

本轮Generic drain-pause末版验证：Dynamic/Static无单drain暂停及warming/staged相邻16 passed；Unit/Architecture1327 passed、源码Mypy160 files、Ruff/diff、文档25 passed。193个Vacuum/SOR/Full-chain为next-tick接线前相邻证据，未冒称末版完整Release，集合不合计。

2026-10-09Owner Pause Generic DRAINING增量（基于`66142e94`，GS-08关联）：真实四策略Generation到DRAINING_ENTRY后正式Owner Pause，RED复现Coordinator只返回OWNER_PAUSED但Generation仍可行动；现Dynamic/Static两个正式入口均沿共享abandon边界终态ABANDONED、清lease，原DRAINING_ENTRY Vacuum仅标Owner pause而保留fence与source，不提前resolve或切current。后续同Coordinator tick对已ABANDONED来源继续调用现有正式drain；无Ticket分支完成后进入OWNER_PAUSED，旧Active Universe/Authority不改、零targets/Command。共享mark_owner_pause_vacuum_drained按SOR/Generic Dynamic/Generic Static exact source decoder分派，不再把Generic父解析为SOR pair。四策略×Dynamic/Static8分支含提交前全回滚、原fence保全、终态源与正式next-tick drain完成；加已有warming/staged pause16分支PASS。仅证明无Ticket drain完成，不能代替prepared/sent/unknown/partial交叉、unfenced PENDING/DESIRED暂停或后续resume/supersession恢复链；这些仍为GS-08缺口。相邻ENTRY Vacuum/SOR Materialization/既有Full-chain193 passed为next-tick接线前代码，末版16分支及Unit/Architecture/Mypy另重验。全部Docker PG与recording facts，无生产修改，不标GS-04～09 Done或exact R4。

本轮Static延迟末版验证：delay/normal/hour-only10 passed，既有Full-chain与文档76 passed，更新台账后文档25 passed、Ruff/diff通过。本轮仅tests/docs，未跑全Unit/Mypy或R4，集合重叠不合计。

2026-10-09正常Static跨tick延迟验收增量（基于`cf717c30`，GS-03/06/08关联）：在已有MPG/MI连续Authority、正式Static预排期与protected Ticket链中，将已STAGED目标的下一个activation tick分别推迟8000/30000/120000ms；真实Coordinator重新claim本次tick lease，原Generation materialization_started/fenced时间不改变且仍在原1800s deadline内，不能靠重设timeout通过。三档均生成NORMAL_TRANSITION，first eligible保持原hourly close，不因超过单次30s lease窗口误造AUTHORITY_GAP/RECOVERY；真实新Static Observation消费原close但保留comparison rebase抑制，重复close幂等，已有Ticket在Selection-read-forbidden安全链中至终态。新delay6分支加既有normal/末尾独立hour-only4分支共10 passed。此处只模拟跨tick时间推进，不宣称真实network耗时/Worker cadence/24h soak已完成；没有修改生产时钟或配置，仍需实际activation并发及逐卡认证，GS-04～09未Done、非exact R4。全部Docker PG与recording venue，production_modified=NO。

本轮Static recovery provenance末版验证：Static/fallback/正常comparative组合38 passed；迁移/SOR materialization/既有Full-chain150 passed；Unit/Architecture1327 passed、源码+0008 Mypy161 files、文档authority25 passed、Ruff/diff通过。集合重叠不合计，非exact R4；末版组合已重跑，不引用初版物理字段错误或Arming fixture时钟错误产生的失败作为PASS证据。

2026-10-09Static NORMAL独立recovery provenance SQL补强（基于`6bdfe185`，GS-08关联）：从正式CPM/BRF2首次Dynamic→后续Generation timeout→正式FALLBACK_PREVIOUS及未armed Episode checkpoint建立Static Owner排期/STAGED上下文；在不发生Owner/policy interruption且source expiry恰好等于Static effective boundary的情况下，Python正常prepare明确RECOVERY_PROVENANCE。刻意绕过prepare/require两层并提供typed NORMAL/current-close proof，真实PG此前DID_NOT_RAISE并可commit非法Static NORMAL。0008现独立从持久化recovery proof或continuity/current前驱精确解析origin；检查Spec/epoch/control/comparison与Event binding一致，target/previous重叠成员的checkpoint ID/revision/effective/first eligible全部等于origin、且armed非NULL，否则拒绝Static NORMAL cannot skip recovery provenance。来源只存在历史recovery标签但实际已armed时不无条件降级：正式未来NOT_TRIGGERED Observation后合法Static NORMAL仍可activate。另通过新真实same-members Snapshot的NO_CHANGE延续unarmed recovery，证明物理continued_from_selection_authority_id路径也不能绕过barrier。CPM/BRF2×unarmed/armed/NO_CHANGE-continued六分支PASS，非法commit回滚后仍可用正确RECOVERY proof正式activate。初版错用了不存在的领域别名continued_from_recovery_authority_id物理列和漏mock Recovery Observation动作时钟，按实际codec/PG时钟修正并重验；未增加compatibility字段或放松约束。仍须更多完整source/lease/cursor与独立recovery provenance攻击矩阵、第二Dynamic自然入场和逐卡认证，GS-04～09未Done、非exact R4。全部本地Docker PG，无生产修改。

本轮NO_CHANGE consume/grant末版验证：四策略真实并发8分支PASS；自然入口/hourly faults/continuity/并发组合62 passed；既有Full-chain与文档76 passed，更新台账后文档25 passed，Ruff/diff通过。仅tests/docs变化，未跑最终R4，集合重叠不合计。

2026-10-09NO_CHANGE grant/Observation真实事务并发增量（基于`ff3f19a8`，GS-03/06/08关联）：四策略在正式首次Owner→Runner→Activation后，下一预提交same-members Snapshot与正式PRE_FENCE_CONTINUITY处于同一close。MPG/MI先用真实NOT_TRIGGERED Observation完成comparison arming，并提供fixed24/exact revision缓存，不写checkpoint。分别让Observation在Signal/close消费已写但未commit时持锁等待，以及NO_CHANGE Authority/current已写但未commit时持锁等待；第二条独立PG连接并发推进另一正式应用入口，第三连接查询pg_blocking_pids，确证第二事务被第一事务锁阻塞，不用sleep或串行结果冒充并发。consume先commit时后续grant精确拒绝Generic grant close was already consumed且零NO_CHANGE Authority；grant先commit时真实Signal冻结新NO_CHANGE Authority。两种顺序均一条Signal、零Ticket/Command，重复同close不新增Signal；current与Signal birth Authority逐项一致。四策略×两种顺序8分支PASS，无生产行为改动。这只补NO_CHANGE/continuity的同close排序，不代替新Universe atomic activation、更换comparison、Owner pause/Vacuum接管及Signal→Ticket全部并发矩阵，GS-04～09未Done、非exact R4。全部本地Docker PG与recording市场输入，production_modified=NO。

本轮连续Static/独立hour-only末版验证：自然入口/hourly faults52 passed，最后添加same-close幂等断言后4个新分支另PASS；既有Full-chain与文档76 passed，更新文档后25 passed，Ruff/diff通过。本轮仅tests/docs，未重跑全Unit/Mypy或R4，集合重叠不合计。

2026-10-09MPG/MI连续Static current-close与独立hour-only增量（基于`8b9cf4f8`，GS-03/06/08/09关联）：在两策略自然三期Selection/rebase/Signal及原Ticket已保护上下文，正式Owner排期Static之前的最后Dynamic period由正式Period Coordinator授予PRE_FENCE_CONTINUITY，不用SQL补Authority。比较缓存保持fixed24及exact revision，当前Authority连续到Static decision boundary；正式materialization/atomic cutover在close后数秒完成，proof为NORMAL_TRANSITION、first eligible保持当前close、无authority recovery rebase，但Static comparison变化仍需comparison barrier。新Static scope用真实Observation与1h/4h模板消费这根close，返回COMPARISON_REBASE_REQUIRED而非RECOVERY_REBASE_REQUIRED；PG comparison_last_observed确为该close，旧Signal计数仍1，重复同close不推进checkpoint或造新Signal。已有Ticket继续在Selection-read-forbidden安全UoW中至terminal，冻结来源不改。另把同一合法Static准备链整体放到hour末尾不足10ms，末尾mode/current写入后才让DB clock跨close，明示仍早于本次30s lease和materialization deadline；实际拒绝为STATIC_ACTIVATION_COMMIT_CROSSED_CLOSE而非deadline，完整回滚Current/Authority/Control/Generation/Vacuum及Ticket/Reservation/保护Command，原持仓继续退出。MPG/MI×正常/末尾close故障4分支PASS。初版Market只返回1h漏MPG4h及误读不存在的RuntimeScope cursor字段，按实际生产输入/PG checkpoint修正，没有修改生产时钟规则；本轮仅测试补强，不证明future Static/第二Dynamic的新ENTRY全矩阵或consume/grant真实并发已闭合。全部Docker PG与recording venue，production_modified=NO，GS-04～09未Done、非exact R4。

本轮有仓Static切换最终验证：四策略成功/timeout8分支PASS；自然入口与hourly fault组合48 passed，末版单独要求terminal status后8分支重验；既有Full-chain与文档检查76 passed、文档更新后25 passed、Ruff/diff通过。初版末尾错误地比较包含合法mutable status的整Ticket而导致回归失败，按TradeTicket既有immutable合同改为全部字段exclude status逐项相等并额外要求status=terminal，未改生产行为。仅测试与台账变化，未重跑全Unit/Mypy或R4；集合有重叠不合计。

2026-10-09已保护Dynamic Ticket跨Static切换增量（基于`e3661a17`，GS-08/09关联）：复用四策略真实Owner→Runner→Coordinator→Observation→Claim/Ticket→durable ENTRY→Protection的自然入口，原Ticket保持POSITION_PROTECTED时正式Owner排期Static baseline。Static Generation的PENDING/Desired/fence/drain/warming/staged/atomic activation每一步均检查同一Ticket、Aggregate、Reservation、Netting Domain占用、既有Initial Stop/TP1 Command完全不变；成功retire旧交易Universe，切Static current/mode且清Dynamic current Authority，但保留Ticket frozen birth Authority/Universe/Exit Binding。另同源warming timeout只abandon新target并保留未resolved原Vacuum，旧protected仓位与占用/保护同样不改。在成功/timeout两类之后，把所有后续Lifecycle/Dispatch/Reconcile/Settlement/Review UoW的Selection repository换成任何读取即失败的test guard；原Ticket继续TP1/Runner保护替换/外部flat/Reconciliation/Settlement/Review至TERMINAL，released预算及Netting Domain、零open Incident，每个Command仍同一TicketIdentity且仅一条ENTRY generation，终态Ticket全部冻结字段仍等于原Ticket。模拟fill/flat/Review经济值仅为本地fixture，不表示收益或实盘。四策略×成功/timeout8分支PASS，无生产行为改动；初版夹具误用ticket.ticket_id，已改为正式ticket.identity.ticket_id。不能据此宣称未保护/partial/unknown、在warming期间并发推进Runner或新Static/第二Dynamic自然Entry全部覆盖。GS-04～09未Done、非exact R4，全部Docker PG与recording venue，无生产修改。

本轮连续Static失败末版验证：Static20分支PASS（新增wrong-scope断言后4个连续timeout分支另PASS）、Generic migration/SOR materialization/既有Full-chain150 passed、Unit/Architecture1327 passed、源码+0008 Mypy161 files、文档authority25 passed、Ruff/diff通过。集合重叠不合计，非exact R4。

2026-10-09连续Static timeout与历史链重验增量（基于`e713e1e2`，GS-08关联）：四策略原Static失败→Owner重授权→同Vacuum第一次retry→该retry再次timeout→再次正式Owner授权→下一retry恢复激活，逐次检查旧Generation exact终态未改、原Vacuum ID/fence/drain不重置、新Generation各自deadline、future-close recovery/rebase仍成立，旧retry callback不能重新claim。RED复现`brc_static_retry_handoff_matches_v1`把旧terminal handoff与最新Vacuum source pointer绑定，合法后继后历史predicate失效；继而对两条旧FAILED_CLOSED父记录做no-op update，真实deferred guard再RED，因为它要求历史失败的Vacuum永久保持旧source/unresolved。现新增有界SQL successor proof：只接受同Vacuum的immutable STATIC_RETRY handoff、新PENDING精确previous link、exact Static author-derived Generation ID、TOTP purpose/scope/time、baseline/epoch/control/previous Event-comparison、旧targets全abandoned及原OWNER_REAUTHORIZED event；当前actionable操作仍必须匹配current pointer，只有terminal历史可以用正式后继证明保全。无后继/错Vacuum不能让历史predicate通过，也不能把closed Vacuum冒充恢复授权。四策略重复失败后的旧父/中间retry deferred重验和wrong scope负向检查PASS。修复DDL两个CREATE FUNCTION同execute导致asyncpg prepared拒绝的本地fixture错误，末版迁移重新认证；不加schema fallback或第二恢复链，不直接SQL清围栏。仍不能以此宣称已穷尽所有永久失败/Pause/有仓交叉矩阵或GS-04～09 Done；source/consume-grant/full-card审计继续未完成。全部Docker PG，无生产修改。

本轮Static恢复末版回归：Generic migration/SOR materialization/文档检查124 passed；共享Generic activation/fallback20 passed；末版Static正式分支20 passed；Unit/Architecture1327 passed、源码+0008 Mypy161 files、Ruff/diff通过。计数重叠不合计，不构成exact R4；既有Full-chain150组合是较早相邻验证，原drain provenance末版后未再全量重跑Full-chain。

2026-10-09Static重授权同围栏接管/恢复激活增量（基于`8d328f9c`，GS-08关联）：正式Owner重新排期到期后，原Static Coordinator创建新的source-bound Generation并接管原drained Vacuum，旧FAILED_CLOSED/ABANDONED Generation和已放弃目标保持终态；原Vacuum ID/fenced_at/drained_at不变，只有source/period/version切向新操作，当前交易Universe/Authority在新activation前不变。接管exact-load旧terminal source、Owner重授权event、epoch/control/baseline/previous Event/comparison及未解决drain blockers；新Generation的fenced_at是本操作materialization预算起点，普通retry不刷新。typed StaticActivationProof显式分开原fenced_at/drained_at与materialization_started_at_ms，NORMAL拒绝继承旧drain，正式retry固定RECOVERY_TRANSITION/future-close-only，沿原atomic Static activation初始化完整Episode rebase，不追认过去close。新增0008独立SQL handoff predicate核对旧终态/新Owner/link/原OPEN与ENTRY_DRAINED/新materialization/event，不只信Python；篡改handoff previous ID与省略Activation预算字段均在真实PG commit拒绝。source失败在新操作中仍保留围栏：测试中的永久certification blocker须用明确更新的本地资格事实解除，Owner重授权本身不把not-eligible伪装为eligible。过程中修复MPG/MI测试在activation后仍写旧comparison projection、certification next_check早于更新observed时点及recovery checkpoint字段名错误；没有弱化生产约束。四策略×正常/timeout/permanent/warming-pause/staged-pause20分支PASS，包含重授权并发/幂等、handoff提交前全回滚、SQL payload攻击、正式activation/future checkpoint以及过去close入场拒绝。Unit/Architecture1327 passed、源码+0008 Mypy161 files、Ruff/diff通过；migration/SOR/既有Full-chain150 passed为增加末版original-drain provenance校验之前的相邻证据，末版迁移/SOR另重验。仍需重复失败/多次handoff历史保全与恢复后实际Observation→ENTRY、有仓Static lifecycle、consume/grant并发和逐卡认证；不能据此标GS-04～09 Done或exact R4。全部本地Docker PG，无Tokyo或生产migration，无真实exchange写入。

本轮重授权最终相邻验证：Generic migration/SOR materialization/既有Full-chain150 passed，末版Owner Pause优先16分支PASS，repository锁序末版4个timeout重授权分支PASS，文档authority25 passed；集合有重叠，不合计，非release认证。

2026-10-09终态Static Owner重授权增量（基于`69df7d1a`，GS-08关联）：四策略Static timeout/permanent certification/Owner Pause warming/Owner Pause staged沿原正式Owner入口重新排期，RED复现旧pending intent永久拒绝新授权。现`stage_generic_static_selection_mode`仅在旧pending Static对应exact Generation为FAILED_CLOSED/ABANDONED时允许替换；Owner→Control→Generation锁序与Coordinator一致，仍要求TOTP、exact version/epoch/baseline、下一cadence anchor、合法time。repository独立核对旧终态、所有targets已abandoned、原drained且未resolved Vacuum、仍为原Active Universe/comparison，以及新immutable Owner proof的purpose/strength/完整target_scope/authorized_at。仅CAS替换pending authorization/anchor，effective Control version与epoch不变；在原Generation append-only event记录OWNER_REAUTHORIZED及新authorization/原Vacuum，旧Generation terminal/source/目标、原围栏和current Authority都不改。正式PG验证提交前全回滚、6类非法参数、Pause优先、两个并发Owner请求exactly-one committed、winner幂等且只有一条关联event、loser无authorization泄漏、新pending非终态不可再次覆盖。**此切片只完成新Owner intent重授权，不构成Static recovery成功**：到期的新Generation仍须实现原Vacuum handoff、完整独立SQL proof/timeout及future-close rebase；不能直接清围栏、复活旧terminal、借旧Dynamic authority恢复交易或宣称GS-08 Done。既有Static排期/continuity/activation组合26 passed与重授权16分支PASS，末版Pause拒绝专项另复验；Unit/Architecture1327 passed、源码Mypy160 files、Ruff/diff通过。无新增表、无生产migration、无交易所写入，GS-04～09与R4状态不变。

2026-10-09Owner Pause目标回收增量（基于`3d10d3e1`，GS-08/07关联）：真实PG RED复现四Generic策略在正式Owner Pause后warming/staged目标被Coordinator原样保留，继续占global slot。正式Dynamic与Static Coordinator现在将已围栏的MATERIALIZING/STAGED未生效目标沿原abandon_strategy_universe及abandon_generation_for_owner_pause单事务回收，共用原Generation/Vacuum/event表，不新增取消链或queue。共享repository按typed SOR/Generic Dynamic/Generic Static source分派exact decoder，Generic另锁当前Owner Pause、校验动作时间并要求所有目标已abandoned；终态ABANDONED清lease/terminal time、保持immutable来源，原已drained Vacuum转OWNER_PAUSED且fence/drain时间不变。旧Current Universe、immutable Authority及Selection Control均不改、不fallback、不授予Entry；重复paused tick零事件增长，outstanding旧lease不能释放新状态。四策略×Dynamic warming/staged先RED后GREEN，Static warming亦先RED后GREEN，Static staged通过同一正式入口验证；恢复Owner后旧Generation callback仍BLOCKED，Static不再因terminal intent抛不可行动claim异常。Dynamic和Static提交前异常完整回滚，省略target abandon被repository拒绝。证据仅涵盖已围栏warming/staged回收，不冒称unfenced/DRAINING有单pause、paused supersession/resume recovery或failed Static新授权重试完成；这些仍在GS-08缺口。相关28个Static/target组合PASS、末版16个pause/resume组合PASS，Static末版rollback/省略abandon断言另定向复验；Generic migration/SOR materialization/既有Full-chain150 passed、Unit/Architecture1327 passed、源码Mypy160 files、Ruff/diff通过，集合重叠不相加。全部Docker PG与recording facts，无生产修改，GS-04～09未Done、非exact R4。

2026-10-09正常非空切换Vacuum入场竞态增量（基于`a9a4611e`）：既有CPM continuity→新Desired fence测试改为CPM LONG/BRF2 SHORT共用正式Runner生成下一期非空且不同成员Snapshot，不再手写第二Snapshot。原Active Universe通过PRE_FENCE_CONTINUITY与正式Observation自然产Signal，在同一个未过期close窗口由正式Snapshot Coordinator提交Generation/DESIRED/DRAINING_ENTRY围栏；旧Universe及current Authority仍保持，Signal与Authority到检查时均未过期。分别在Claim之前、已计算Claim→issue_ticket之间、prepared ENTRY dispatch之前及durable CLAIMED后读取action-time Admission facts期间，从独立UoW提交实际fence。前两类返回selection_entry_vacuum且零Ticket/Command，拒绝Decision保留原Authority及明确Vacuum blocker；派发两类零recording venue调用，唯一ENTRY generation终态SUPERSEDED，EntryVacuumSuperseded绑定真实Vacuum/Command，Reservation与Netting Domain释放。共享链加无Ticket resolver基线共10分支通过；仅补测试，无生产实现修改。本增量证明正常切换的negative Vacuum boundary及派发取数窗口二次验证，不冒称新Universe activation后的正向current replacement/concurrent consume-grant或全部策略fault matrix完成。failed Static恢复、pause target释放、已有Ticket Static切换及逐卡验收仍未闭合，GS-04～09与exact R4状态不变，全部Docker PG与recording venue、production_modified=NO。

本轮切换验收验证：自然入口/既有hourly fault/新switch组合50 passed；新增Decision及EntryVacuumSuperseded exact payload断言后，末版10分支另行复验。既有Full-chain与文档权威组合76 passed，更新台账后文档检查25 passed，Ruff/diff通过。组合命令带`-k`，其中Full-chain与文档项被deselect，不把50计为Full-chain证据；76来自单独无`-k`命令。集合重叠不相加，未跑完整release认证。

上一Claim freshness/未来Static intent增量验证：自然入口与hourly fault组合40 passed；既有Full-chain与文档权威组合76 passed（含25项文档检查）；最终文档检查另跑25 passed，Ruff及diff通过。集合有重叠，不合计；未重跑全Unit/Mypy或最终release suite，不能据此标R4 PASS。

2026-10-09 Claim freshness与未来Static排期并发增量（基于`d07245fd`）：复用四策略正式Owner→Runner→Coordinator→Observation自然Signal入口（MPG/MI含三期comparison/rebase），不直接插入Signal或Ticket。Claim前输入已过期的typed AccountRisk/Admission Snapshot，正式issue_ready_signal拒绝，零CapacityClaim/Ticket/Exchange Command；immutable REJECTED AdmissionDecision冻结原Selection Authority和实际被拒绝的admission digest，无Claim/Ticket链接。另一分支在Claim已计算、issue_ticket尚未执行时，由独立Owner UoW经正式TOTP边界排期未来Static rollback；pending intent保持当前Dynamic Control有效版本、当前Authority/Universe与Claim一致，正式Ticket继续签发并经原ENTRY/protection/TP1/Runner/Settlement/Review终态链。两类×四策略8分支通过。这是future intent尚未生效的正向并发证据，**不是实际Universe/Authority replacement后旧Claim拒绝证据**；不以未来period导致旧Signal自然过期冒充switch专属阻断，也不以直接SQL改current造正向authority。相邻自然入口/fault组合36 passed是在最终两个MPG/MI pending-intent分支加入前运行，最终8分支另行复验，计数重叠不相加。本轮仅测试补强、无生产行为修改；GS-09仍缺真正switch/剩余freshness交叉矩阵，GS-04～09未完成，非exact R4、生产未修改。

MPG/MI交易权限负向矩阵增量（基于`f56c8498`）：在同一三期自然Selection→rebase→Signal输入上，分别注入Comparison revision在Claim前切换、Owner Pause在Issue前、Claim已计算与Ticket签发之间、Ticket签发与ENTRY dispatch之间。首期Comparison rebase仍零Signal；Claim前switch返回`selection_authority_invalid`且零Ticket/Command；Issue前Owner Pause返回`scope_or_policy_mismatch`且零Ticket/Command；Claim→Ticket间真实Owner Pause返回`strategy_paused`且零Ticket/Command；dispatch前Pause使唯一durable ENTRY Command进入`superseded`，recording venue零调用。两策略正常分支仍完成同源terminal Ticket。相关Generic/Observation/Dispatch/Full-chain组合257 passed，Unit/Architecture1257 passed、生产源码Mypy158 files及相关Ruff/diff通过；不把这些测试扩称Unknown/partial/VALID_EMPTY/Source-stale全部验收，也不等于完整R4。

MPG/MI小时策略自然终态增量（基于`d28fe872`）：在上述三期正式Selection/NO_CHANGE/rebase序列后，第三期Signal各自通过正式CapacityClaim、AdmissionDecision、Ticket与唯一durable ENTRY Command；recording venue独立UoW确认CLAIMED后接受，随后同源Ticket经Reconciliation、Initial Stop、TP1、Runner、外部flat、Settlement、Review到TERMINAL，冻结Authority及Budget/Netting Domain/Incident闭合。测试账户、Post-fill Stress、模拟flat及Review数值为本地事实，不代表经济结论。受影响Generic/Observation/Full-chain组合222 passed，Unit/Architecture1257 passed、生产源码Mypy158 files、相关Ruff/diff通过；不是完整R4。四策略自然交易链已有正向样本，但GS-08/09四边界异常、Unknown/partial、Existing Ticket与Live Evidence projector仍不能由正向样本替代。

自然Selection→terminal增量（基于`646aedd8`）：四策略首次Owner staging的exact epoch由正式Selection Runner读取24 Candidate并提交immutable Snapshot，再由现有Coordinator完成Generation、Vacuum、Warming和ACTIVE_NEW，测试不直接写Snapshot；旧Static Universe与认证仍是明确测试前置。CPM LONG及BRF2 SHORT进一步在同一真实签发链上产生原Detector Signal、CapacityClaim、AdmissionDecision、唯一prepared ENTRY，经独立UoW确认durable CLAIMED后由recording venue接受，随后正式Reconciliation/Initial Stop/TP1/Runner/外部flat/Settlement/Review到TERMINAL，冻结Selection Authority、Reservation、Netting Domain和Incident断言一致。模拟flat、Post-fill Stress与Review经济值是fixture事实，不是真实交易收益。相关集成/部分Full-chain切片176 passed、既有完整Full-chain51 passed、Unit/Architecture1257 passed；计数有重叠，不相加为R4。MPG/MI完成Owner→Runner→Active及Candidate24 Warming，但rebase后跨hourly period的自然Signal/Ticket、四边界攻击矩阵与Live Evidence projector仍未完成；GS-09不能标Done，生产未修改。

2026-10-08 Dynamic Ticket immutable来源追踪补强：四策略自然Selection→terminal测试以真实Ticket的`selection_authority_id`逐级回查Authority、epoch、Snapshot和对应member的selected/qualified、Decimal feature、stable rank、input/qualification digest；Signal的trigger close与Fact digest和Ticket冻结值一致。Ticket冻结原始Initial Stop及Exit Binding ID/hash/version；终态Trade Event包含EntryFilled、TP1、Runner保护、BudgetSettled与ReviewRecorded，Aggregate Review指针指向本次Review。CPM/BRF2与MPG/MI共4条自然场景定向通过，小时完整fault参数矩阵加既有Full-chain共67 passed，Unit/Architecture1276 passed、Ruff/Mypy159 files/diff通过。此证据证明PostgreSQL lineage可追踪，不将本地模拟fill视为真实逐笔交易所fill/手续费；独立离线MAE/MFE/realized R projector仍属GS-13交付，不由本测试冒充，GS-09整卡与R4仍未完成，生产未修改。

2026-10-08 `VALID_EMPTY`未成交ENTRY及late-fill安全增量：CPM LONG/BRF2 SHORT由正式Owner staging、24 Candidate Selection Runner、Coordinator、Observation、Claim/Ticket、durable ENTRY与recording venue acceptance自然抵达下一期合法空集；Vacuum经durable CANCEL_ORDER、外部零仓位/无订单确认，才以`ENTRY_RECONCILED_ABSENT`释放Reservation/Netting Domain并提交`VALID_EMPTY`。六参数场景通过，其中两条新自然取消链。另以真实Docker PG红灯证实：终态`ENTRY_RECONCILED_ABSENT`后若再次输入正仓位，原`reconcile_ticket`静默返回`NO_CHANGE`；现被动读到该事实时创建账户级ENTRY阻断Incident与Owner Monitor，不复活终态Ticket、不写正仓位投影、不产生无授权Command，重复事实幂等；比最终零仓位观测更旧的正仓位Snapshot不误报Incident。当前Admission account-health对终态Ticket不再持有的外部正仓位会判`UNOWNED_POSITION`并阻断同账户新ENTRY，即使交易标的不同；新增纯domain回归5 passed。受影响Generic/Vacuum仓储组合245 passed，Unit/Architecture1276 passed，相邻Full-chain fault matrix 4 passed，Ruff、源码Mypy158 files与diff通过；最后新增的stale-fact测试另做定向复验，因此上述计数不可合并为最终exact R4。**这不等于late-fill全链闭合**：常驻Reconciliation Worker目前只claim非终态Position状态与Settlement/Review，无法主动重新发现该终态Ticket的晚到正仓位；安全恢复也不能通过现有Controlled Exit把终态Ticket当Active处理。GS-09须继续补可界定成本的主动发现与官方durable受控恢复；在此之前不标GS-09 Done或R4 PASS。

2026-10-08 late-fill主动发现增量：现有Reconciliation常驻Worker按持久化Monitor每60秒形成一次只读Binance账户仓位审计的due candidate，与现有Settlement/Review/Certification/Fee共享有界deadline调度，不新增Service或YAML参数；Venue适配仅读取已配置的唯一USD-M账户，解析最多64个非零独立Side。审计在外部I/O后单个短PG事务内，以账户事务锁和0008部分唯一索引核对当前Active Ticket Netting Domain；无主正仓位留下账户级阻断Incident与Owner Monitor，终态Ticket/Command/Position投影不被复活或改写，合法Active Ticket Domain不误报。超时、无效时点或Source错误只记录暂时不可用并按固定间隔重试，不能伪装为健康；重复或并发审计不增加第二个open Incident。外部仓位后来消失不会仅凭账户仓位读数自动解除Incident，因为该读数不证明历史订单/命令已完整核对。Docker PG的终态后无主仓位、按期重试、来源失败与并发场景转绿；受影响Vacuum/0008迁移/full-chain组合62 passed、Unit/Architecture1278 passed，源码/脚本/迁移Mypy160 files及相关Ruff/diff通过。这些为受影响切片而非exact R4。**仍未完成的安全恢复**：需在原Kernel持久化Command与Owner控制边界内取得精确Entry订单/成交归因、外部仓位及残单证明，才能决定保护或受控清仓，并闭合Incident；不能把主动发现冒称自动Flatten或GS-09 Done。

2026-10-08 Vacuum终态二次核对增量：原`ENTRY_VACUUM_CANCELLED / position_qty=0`可在订单消失事件后的下一事务不再读取外部事实而直接提交`ENTRY_RECONCILED_ABSENT`，本地Docker PG红灯复现五个SOR/Generic分支。现在必须由Reconciliation提供**晚于前次订单消失快照**且不早于本次动作时间的exact Netting Domain仓位/订单快照；缺失或陈旧事实保持`POSITION_FACTS_REQUIRED`，新正仓位或重现订单提交账户级Incident并保留原Ticket、Reservation、Netting Domain及Vacuum Fence，后续零快照不自动抹掉Incident。生产Reconciliation Worker改为按部分索引读取所有正在drain且有非终态Entry Ticket的SOR/Generic scope（硬上界8），略过尚待Command或已被Incident围栏的scope，再从可执行scope选择一个，不再只扫描SOR；新测试覆盖两方向Generic和SOR终态二次读取、无Ticket旧Vacuum不饥饿后续scope、正仓位与重现订单双攻击，并经正式Worker验证矛盾事实触发围栏。受影响Vacuum、自然Selection、0008迁移、Full-chain组合81 passed；Selection materialization/Worker fairness等相邻组合86 passed；Unit/Architecture1278 passed，Ruff、Mypy160 files、文档authority25 passed及diff通过，测试集合有重叠，不构成exact R4。本切片只缩小终态误闭合窗口，不证明未来永不出现late fill；真实迟到成交后的保护/受控Flatten仍按上一段未完成边界处理。

2026-10-08 late-fill精确归因与原Ticket恢复增量：`recover_vacuum_late_fill`仅处理仍非终态、保留Reservation/Netting Domain、原Vacuum仍DRAINING且存在post-absence Incident的Ticket。仓位和原ENTRY订单/成交读取在事务外；原Command必须唯一且已被权威接受，订单ID、client ID、instrument、Side、请求数量、关闭状态、完整逐笔成交数量/VWAP和当前仓位数量/均价逐项一致，才提交`VacuumLateFillAttributed`。成交价格缺失、交易ID缺失、错误订单、重复矛盾或100行页上限不能伪装完整证据；相同trade ID的相同明细只计一次。金融VWAP使用固定Decimal38；归因digest对原始Decimal数值采用无舍入字符串规范化，不受ambient context影响。原Ticket随后复用既有full/partial保护及不合法拆分时的CONTROLLED_FLATTEN，始终只有一个ENTRY generation。若精确原订单、零成交与新零仓位/无订单证明同时成立，`VacuumPostAbsenceNoFillVerified`在同事务解除原Incident、终态关闭并释放占用，不凭单独的零仓位快照放行。提交重新检查并锁定runtime capability，按Vacuum→Aggregate锁序/CAS核对Incident、命令及当前事实；monotonic窗口拒绝暂停进程后过期证明。正式Worker对无法归因的事实按独立持久化Monitor每30秒retry，成功后关闭retry Monitor；Owner causality stage映射包括两种新增事实。Docker PG验证SOR/CPM LONG/BRF2 SHORT full fill至Initial Stop/TP1/Runner/外部flat/Settlement/Review，MPG不可拆分late partial至durable Flatten及terminal closure；partial合法保留、wrong identity、runtime drift、并发仅一次、exact no-fill幂等亦通过。测试经济值及外部flat是本地fixture，不是实际收益。受影响Vacuum/自然Selection/Unknown/Command组合112 passed，完整既有Full-chain51 passed，Unit/Architecture1311 passed，源码/脚本/迁移Mypy162 files与Ruff/diff通过；不合并重复计数，不宣称exact R4或GS-09整卡Done。已终态Ticket出现外部矛盾仍由账户Incident/Owner containment处理，不自动复活旧Ticket或新建第二条交易链。

**目标**：所有新入口真实使用GS-08权限，维持既有保护、退出和unknown恢复。

**允许**：Signal admission、CapacityClaim/issuance/submit authority、durable cancel/drain/lifecycle必要接线、integration/full-chain tests。**禁止**：更改资金和退出参数、添加ENTRY generation、直接exchange调用、随名单更换平仓。

**RED与要求**：Claim后switch、Ticket前pause、dispatch前stale deadline、comparison rebase、valid empty；四边界都必须判同一权威。undispatched ENTRY取消；partial仅在现有Vacuum归因/拆分/保护条件下保留，其他按原Incident controlled flatten。Unknown先核对，不能retry重发。

**验证**：从正式Selection/Observation到Ticket/Command的full-chain，不仅直接插入fixture Ticket。保留已暴露Position的Initial Stop/TP1/Runner/Exit/Settlement/Review；cancel unknown和late fill攻击测试。

**Done**：unauthorized Signal/Ticket/dispatch=0、每episode最多一个Ticket、netting独立、已有退出不读取Selector；failures终态和Incident边界可复核；§3.4相关SOR子集PASS。

#### GS-09-LIVE-EVIDENCE-01 — 最小实盘证据合同

本卡核对并补足immutable lineage，不建立新交易链、不新增GS-14。每个新Dynamic Ticket应可exact追溯：SelectionSpec/版本、Snapshot及member feature/rank/资格、Signal及trigger close、entry Command/实际fill时间价格数量、原始Initial Stop、冻结ExitProfile/Binding、TP1/Runner/Exit/Settlement时间与数量、terminal time。复用现有FK与append-only事实，不为展示复制一套authority。缺失历史字段明确标记`EVIDENCE_INCOMPLETE`，禁止猜测或改写旧Ticket。

独立离线projector在GS-13交付：`Ticket immutable facts + closed market path → MAE/MFE、0.5/1/2/3/5R first passage、time_to_levels、realized R、runner capture`。不读未来行情作交易输入，不参与实时ENTRY/FinalGate，不阻塞保护/退出；projection失败不得暂停交易。复用已有market-path/projector能力，先盘点再补最小缺口；不新增常驻service、研究调参或Shadow上线等待。

计算合同必须可复算：R分母固定为实际entry VWAP到原始Initial Stop的方向化距离，禁止用移动止损重设R；realized R包含实际fill、费用和可取得的funding并明确缺项。first passage使用exclusive closed-bar时间；同一根K同时触及止损和盈利level标记`AMBIGUOUS_INTRABAR`，不猜先后。数据缺口/截尾明确标注；退出后path horizon为显式versioned参数并记录cutoff，未观察满窗口不当成未触及。runner理论excursion与实际runner净收益分开展示，capture分母/剩余数量明确，零分母为未定义。输出绑定Ticket、path/source digest、projector version、horizon，rerun确定性相同；报告为display-only。

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
| `p95 queue_wait` | due且可执行到取得global slot的实际等待，报告样本N | 300秒为SLO warning；hard gate仍为无starvation、正常路径不漏合法close |
| `p95 fence→grant latency` | 首次fence到合法grant的实际elapsed，deadline不重设 | 300秒为SLO warning；原1800秒timeout、freshness及period expiry仍为hard gate |
| `vacuum_duty_cycle` | 每策略健康观察区间open Vacuum的时间并集 / 该区间 | 每策略≤10%；报告逻辑时间与实际elapsed计量映射 |
| `NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY rate` | 此原因未激活的due target periods / 健康target periods | =0；各策略至少实际处理一个有权close，不能全程只有计划时间 |
| `selection-caused ENTRY cancellation count` | exact Vacuum归因的ENTRY cancel命令/结果计数 | 等于workload中命中条件的预期数，无重复取消/无unrelated command；已暴露保护不被取消 |
| `missed eligible close count` | 健康数据/控制下因Selection工程延迟未处理的目标Event close数 | =0；逐close ledger，预期rebase抑制/自然NOT_TRIGGERED另列，不能用其掩盖延迟 |

300秒原为工程预算，Owner于2026-09-21明确降为performance SLO warning；不作为额外release硬闸门，不因该指标单独引入并行warming/incremental materialization。vacuum duty 10%及其他未修改预算仍保留，执行时不得看结果后放宽。正常路径仍要求零遗漏合法close，恢复/故障段按真实ledger记录机会损失并要求零过去close追认；stale按精确deadline触发，保护与Reconciliation按原契约推进，不要求故障期间假装零遗漏。

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
6. 交付GS-09-LIVE-EVIDENCE-01的最小离线projector及测试：LONG/SHORT、partial fill、TP1/Runner、费用、同bar双触及、缺口、窗口截尾和退出后右尾；从正式Ticket链读取，不仅用手填收益fixture。保证每笔样本具有可重建事实，不宣称已实现自动持续行情采集或额外研究服务。

**技术可激活边界（无额外经济Gate）**：对目标策略，`SPEC_CERT PASS + generic runtime PASS + exact R4 PASS + authorized deployment/postflight PASS`意味着`TECHNICALLY_ELIGIBLE_FOR_OWNER_LIVE_ACTIVATION`。Owner可在既有资金/风险边界内直接小资金Dynamic实盘，不另要求经济评审、盈利显著性、追加Replay或等待一段Shadow。Owner activation/TOTP是防误操作的正式控制动作，不是第二次研究审批；不能自动激活，不能越过fresh action-time facts、stopped-flat部署、Owner pause或其他交易硬闸门。本任务仍在部署前等待Owner确认，计划文字不构成部署授权。

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

当前 **PLAN_APPROVED / required_plan_amendments=COMPLETE / owner_confirmation=GRANTED_2026-09-07 / implementation_authority=CODE_AND_TEST_ONLY / active_execution_scope=GS-04_TO_GS-13**。当前执行目标为GS-04至GS-09；各卡完成度以§2.1及卡内Done验收为准，不以初始组件摘要宣称全卡完成。生产部署、Tokyo migration和任何策略 activation继续无授权。
