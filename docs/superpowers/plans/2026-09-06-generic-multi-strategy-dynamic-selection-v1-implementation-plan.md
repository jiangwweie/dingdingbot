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
