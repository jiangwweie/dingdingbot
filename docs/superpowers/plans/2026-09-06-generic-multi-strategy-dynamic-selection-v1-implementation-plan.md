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

| 范围 | 当前已验证结果 | 仍需交付 |
| --- | --- | --- |
| 数值证据 | 96份原始1h ZIP哈希逐一验证；从冻结commit重建research函数并核对artifact完整排序；CPM/BRF2各463、MPG/MI各1852 cutoff的决策集合零差异；SOR961×24 Core verified | exact最终candidate再次认证，认证证据与受审安装集合绑定 |
| GS-01/03边界补强 | 跨comparison revision旧token拒绝、same-close checkpoint幂等；miss按period计算，可重放/跨缺失period；effective前及deadline后ENTRY拒绝 | runtime cursor/Owner/freshness全链集成 |
| GS-04迁移切片 | 本地0007→0008比较来源保全；缺源在schema写入前STOP；Authority、Generation previous及Static baseline的pair列迁至Event引用行后删除；8张通用表迁为`period_anchor_ms`；Job/Generation epoch与Snapshot复合FK；Generation Source count/time与target digest校验、Generic单actionable索引；保留SOR≤7 | 完整logical preservation、真实source/target首根及后续Signal差分、role grants、Owner epoch正式转换边界；Generic Generation完整状态机 |
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

**GS-07-SOR-INCIDENT-01（必须显式验收）**：`temporarily_unavailable`属于retryable，不能压成`CERTIFICATION_NOT_ELIGIBLE`后立即fallback；`owner_action_required`属于non-transient，可进入受现有条件约束的fallback，不代表可越过Owner pause或drain。任何retry、重启或重新取得lease不得刷新原materialization deadline。测试需从真实certification结果经Coordinator到Generation/Vacuum断言状态及原deadline，而非只测枚举分类。

**验证**：真实PG+recording venue；全局slot冲突、partial staging、resume/abandon/reclaim、duplicate callback；零warming Signal/Ticket/Command，source eligibility不得从研究数据读。

**Done**：targets可准确STAGED/ABANDONED并恢复，最终activation权限留给GS-08，无incremental warming/carry-forward新设计；§3.4相关SOR子集PASS。

### GS-08 — Continuity / Vacuum / Atomic Authority

**目标**：把前三类domain约束组合成durable新交易authority状态机。

Generic准备事务增量：现有Selection repository新增typed `PENDING→DESIRED` 写边界，锁定Control/Generation并校验epoch、Control version、source period、lease owner/epoch/expiry，CAS更新并追加唯一DESIRED event。四策略集成用例开始通过正式claim→desired，不再跳过该步骤；错误lease拒绝、重复调用保持首次desired时间。后续MATERIALIZING仍是明确标注的测试前置，不能据此宣称fence/drain或Coordinator已完成。

Generic fence事务增量：复用`open_generation_entry_vacuum`及原Vacuum/event表，Generic分支要求DESIRED、exact Control/epoch/period与worker lease，原子保存OPEN/DRAINING_ENTRY事件和Generation DRAINING_ENTRY/fenced_at。四策略用例开始走真实claim→desired→fence；错误epoch在写Vacuum前拒绝，跨事务读回负向fence及Generation状态通过。SOR调用签名保留默认无Generic token路径，不增加第二drain链。当前仍未把Generic drain completion与Coordinator完整接通，测试中的MATERIALIZING转换仍明确标为前置，不能宣称GS-08完成或授权生产。

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
9. **GS-08-HOURLY-CLOCK-01**：NORMAL证明完整时，05:00:08可消费05:00最新未消费close；8秒/30秒/2分钟延迟不能仅按耗时变成RECOVERY。迟到Snapshot、已消费close、freshness失效、commit越界拒绝。RECOVERY原因一旦成立，禁止恢复后降级NORMAL追认；future-close-only与独立recovery revision rebase必须覆盖四策略，先未来合法NOT_TRIGGERED再更晚TRIGGERED。首个未来close不小于expiry时记录NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY及miss，零新Signal/Ticket；下一合法period才能恢复。SOR保持专属Gap Audit路径。

**验证**：PG并发事务/barrier测试+recording network；current-close先consume或先switch两种顺序、crash每个commit点、重试terminal authority；SOR近期四类bug regression。

**Done**：全部新authority可trace proof/source/epoch/Event set，positive grant不能绕过rebase/stale/EMPTY/Owner；existing Ticket未变；§3.4相关SOR子集PASS。

### GS-09 — Signal / Claim / Ticket / ENTRY dispatch

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
