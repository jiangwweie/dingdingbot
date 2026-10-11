---
title: CAPACITY_V0_OWNER_AMENDMENT
status: BUSINESS_SEMANTICS_FROZEN
task_id: CAP-01
implementation_status: LOCAL_ACCEPTED
authorized_execution_scope: CAP-01_GS-10_TO_GS-13_AND_STOPPED_FLAT_DEPLOYMENT
gs13_authority: OWNER_AUTHORIZED
production_authority: STOPPED_FLAT_DEPLOYMENT_AFTER_REQUIRED_GATES
---

# Capacity V0 — Owner Amendment / Task Card

## 1. 权威、目标与来源

**2026-10-11 最新授权覆盖下方历史等待边界。** Owner 已授权必要发布保证及本次统一 stopped-flat 部署；Policy B 仍由正式部署 authority 事务自动切换，不要求额外 Owner 操作。长期 soak 不再作为部署前置，明确未通过并延后生产观测，不豁免平仓、preservation、数值/角色/identity gate。SOR-001 的永久停用及原暂停围栏必须保全。最新范围以关联 Implementation Plan 开头的 Owner 部署决策为准。

**业务语义已由Owner在2026-10-10本任务明确冻结。** 本文件是Generic发布的独立补充任务，不是生产Policy，不替代当前PostgreSQL事实。Owner最新决定：本次上线默认切换新容量，不再需要部署后手动启用；当前仍仅允许本地代码/测试，GS-13和实际部署须另行确认。来源为本任务Owner确认及SOR停止补充说明；关联[Generic Implementation Plan](2026-09-06-generic-multi-strategy-dynamic-selection-v1-implementation-plan.md)。

目标：允许同一Strategy、同一方向同时承载两个不同Instrument的独立机会，消除long_continuation单槽垄断；不增加既有风险上限，不改变Selection、Detector或退出语义。

**SOR已由Owner停止，并决定不再启用。** 这是Owner提供的事实及未来范围决定，不冒充本轮东京只读实测。代码兼容、历史保全与回归测试继续；不能因通用Capacity能力、seed、migration、Policy revision或部署而恢复SOR ENTRY Authority。停止策略不意味着删除其历史或取消已有生命周期的安全处理能力。

## 2. 冻结业务合同

| 层 | Policy B目标 | 边界 |
| --- | --- | --- |
| Global | max_active_tickets=3 | 保持 |
| Gross | max_gross_stop_risk=6% | 保持 |
| Direction | max_directional_stop_risk=4% | 不另增方向Ticket数量上限 |
| Ticket | max_risk_per_ticket=2% | 上限，不保证每张满风险；不改变sizing/min materialization |
| Family | long_continuation=2 | 从1调整为2，CPM/MPG/MI共享，不预留策略槽 |
| Family | opening_range=2；rally_failure_short=1 | 保持；不构成SOR启用许可 |
| Strategy-side | max_same_strategy_side=2 | 支持该模型的策略统一上限，不覆盖更严格约束 |
| Netting Domain | 同venue/account/instrument/position_side最多1张 | 原域占用、外部position/order/hold校验保持 |

所有风险值是规划Stop Risk边界，不保证实际损失不超出；保证金、stress、杠杆及其他既有硬Gate不放松。

有效准入是所有Gate的交集，不把百分比与Ticket数量直接数值求min。Owner的effective_capacity=min(...)表达最严格约束优先，而非混合单位计算公式。

第二张同策略同方向Ticket必须是不同Instrument、不同Episode、不同Signal，独立满足全部Entry条件。一Episode最多一Ticket、一Ticket最多一ENTRY generation保持。不同Instrument不代表统计独立。

Dynamic模式下新Ticket必须属于当时有效且经正式Authority证明的membership；不能要求所有Static交易也拥有Dynamic Snapshot。已有Ticket掉出Universe后仍占Capacity，按原ExitProfile继续，不重写、不加仓、不强制腾位。

竞争沿用first eligible admission；无策略保留槽、强制分散、同close凑批、Dynamic rank调度、跨策略评分、抢占、correlation/cluster/beta新增Gate。Manual Regime仅决定strategy/side eligibility，不修改Capacity数值。

## 3. Policy身份与上线边界

**新容量是本次发布默认内容，正式部署时系统自动完成独立Policy revision A→B，不需要Owner额外按钮、TOTP或手工SQL。** 这是Owner已经明确的发布范围，不是migration默认扩大权限或Worker启动自行启用。安装Schema的Alembic仍只安装能力；正式stopped-flat且Entry fenced的部署authority/identity切换事务负责生成B和before/after证据，postflight确认B已生效。普通restart、no-signal tick和只安装Schema不改变Policy。没有额外经济Gate或Shadow等待期，GS-13执行和最终生产部署仍分别等待Owner确认。

Policy A为实际既有不可变Policy；部署前核验其内容、identity与digest并保全，不改写其历史。不能未经证据写成same_strategy_side=1：既有family=1只限制long_continuation，不等价于全策略strategy-side=1。若新增字段需为A显式表达保守旧行为，应先定义可证明的迁移映射与neutrality，不使用runtime旧schema reader/兼容适配器。

Policy B冻结long_continuation=2、max_same_strategy_side=2，其他风险边界不变。部署自动生成的revision绑定exact release、source Policy版本/digest和target身份；同一切换重试不得重复生成。每张Ticket/Claim/AdmissionDecision必须可追溯实际Policy版本与语义；已有Ticket冻结事实不变。Policy B不resume Global Entry或任何策略；SOR继续禁用。停止/flat证明、身份、preservation、postflight失败时保持ENTRY fenced并fix-forward，不靠降低Gate完成自动切换。

## 4. CAP-01 Task Card

### 4.1 执行范围与依赖

- Owner：当前工程任务；业务已冻结，Owner随后明确授权完成CAP-01与GS-10/11/12本地代码和测试；GS-13执行前必须停下等待Owner确认，不仅是部署前等待。production_authority=NONE保持。
- 前置：Generic GS-04～09本地签收；参考现有Owner Policy、admission与版本检查实现。
- 允许路径：`src/trading_kernel/**`、`migrations/trading_kernel/**`、`tests/trading_kernel/**`、`scripts/trading_kernel/**`及既有Owner Console tracked assets、相关设计/计划/runbook。
- 禁止：改SelectionSpec/Detector/ExitProfile、资金/杠杆/sizing扩张、SOR启用、生产DML/交易所写入、YAML维护Policy、第二资金链/旁路SQL控制、改写已签收历史证据。
- migration是否必要及exact revision在实现设计中按source/schema事实确定；不能直接改已发布migration。既有Generic最终schema/runbook若受影响，必须同步更新目标及forward preservation验证。

### 4.2 实施步骤

1. 盘点实际Policy模型、Owner mutation、四层ENTRY检查、锁域、active计数与Reservation/Netting释放；明确strategy稳定身份和side键，不按Display Name分组。
2. 先写RED：第二独立机会原family拒绝；新strategy-side超限；并发抢最后一槽；Policy切换穿越边界；部署误启容量/SOR。
3. 实现冻结字段、正式部署Policy revision和不可变证据；使用既有全局ENTRY serialization，跨策略跨Instrument同strategy-side不得超发。
4. Signal admission/Claim、Ticket issuance和dispatch分别核验适用Policy版本及占用；不只在UI或第一次检查生效。
5. Owner API/UI只读显示新容量、版本和拒绝原因，不新增本次容量启用按钮。默认启用通过正式stopped-flat/fenced部署authority事务，绑定source/target/version并保持幂等；migration或restart单独执行不切容量。
6. Docker PostgreSQL真实事务并发/full-chain验证；合入GS-10/11/12验收与GS-13 exact候选认证。

### 4.3 验收矩阵

| Case | 必须结果 |
| --- | --- |
| CPM ETH LONG + CPM BTC LONG，全部Gate通过 | 两个不同机会合法，不重复ENTRY |
| CPM ETH LONG + 第二个ETH LONG，或复用Episode/Signal | 拒绝，零额外Ticket/Command，不加仓 |
| CPM LONG第三张不同Instrument | strategy-side拒绝，即使单张不足2% |
| CPM + MPG达到family两张，再有MI | family拒绝，不为策略预留 |
| BRF2第二张不同Instrument SHORT | family=1仍拒绝 |
| Global/方向/gross/margin/stress更严格 | 严格Gate优先，不被通用2覆盖 |
| 两请求竞争最后一个合法名额 | 至多一个成功，真实PG串行化证据 |
| prepared/sent/unknown/partial及未释放Reservation | 不漏算、不重复占用，走既有安全释放条件 |
| Policy修订发生在Claim/Ticket/dispatch之间 | 旧事实不穿透版本Gate，明确拒绝/撤销；unknown不重发 |
| 旧Ticket掉出Selection | 继续占Capacity，保护/TP1/Runner/Exit/Settlement/Review不变 |
| migration/restart | Policy A及历史不变，不自行激活B/SOR |
| 正式部署与重试 | 自动A→B，唯一release绑定revision，无额外Owner操作，SOR/ENTRY状态不自行恢复 |
| 相同输入不同Policy | Decision/Ticket明确追溯A/B，不改写旧链 |

### 4.4 Done与Hard Stop

#### 2026-10-10 首个实现切片（未整卡签收）

新增exact venue/account/StrategyGroup/side active Ticket计数port与PostgreSQL实现，复用已有nonterminal Ticket口径；真实claim→Ticket集成用例从持久化Ticket读取稳定Runtime StrategyGroup身份，验证exact count=1与其他account/strategy/反方向=0。初版测试错误引用Ticket顶层strategy字段已修正；随后正式RED为repository缺count_active_strategy_side_tickets，最小实现后完整test_capacity_claim_to_ticket.py为7 passed。未把该计数接入Policy/Claim/issuance/dispatch，尚未覆盖Reservation异常释放/并发全矩阵，不宣称容量规则已生效。

Done：卡级RED/GREEN、Docker PG并发、真实producer至terminal full-chain、Owner只读显示、部署默认Policy B原子身份/重试测试、migration neutrality/preservation、静态检查通过。GS-12后汇报完成证据并停止，GS-13及其完整R4须Owner另行确认后才能执行；之后全部变更绑定同一最终clean candidate。既有GS-04～09验收不替代本卡新增行为认证。

#### 2026-10-10 Policy/Claim/dispatch实施增量（未整卡签收）

新增Policy显式nullable max_same_strategy_side：NULL代表没有额外strategy-side Gate，保全A而不伪造上限1；Owner B设为2。CapacityUsage增加真实count，build Claim与issue_ticket均按新增前count>=limit拒绝，dispatch包含自己按count>limit拒绝；Policy/Claim值不一致仍POLICY_DRIFT。新Claim冻结limit/count进入digest，两项历史all-NULL从canonical payload剔除，原Claim hash不改写；不同标的共用同StrategyGroup/side计数，不混其他account/strategy/side。新的strategy_side_capacity_exhausted映射与Shadow拒绝原因接入。

独立0009_capacity_policy_v0接0008：exact source、flat/quiescent锁与检查先于DDL；仅安装Policy/Claim nullable字段、check和active count索引，既有Policy/Ticket/Controls不UPDATE。当前代码schema head更新为0009，0008原迁移保持。历史保全与源验证完整认证仍待补齐，不能据空库通过直接部署。

新增正式activate_capacity_policy_v0应用/repository：step-up、幂等、expected version、Policy锁/CAS与一条before/after immutable event；只改long_continuation与strategy-side，拒绝未知source或非冻结3/2%/6%/4%边界，不resume Entry/strategy。source真实role尚未认证，当前应用global lane lock调用须补齐最小权限路径；API/UI亦未交付，不能当作生产可用控制。

Focused末版：unit capacity、dispatch、Owner control + Docker PG capacity Owner/claim-to-ticket共50 passed；初版Owner PG测试使用通用ingest fixture的8 engineering slots被正确硬Gate拒绝，fixture恢复合同3 slots后通过。此前Fast回归在schema head变更后520 passed/1 failed（regular deploy测试硬编码0008；其余未执行），不是整套PASS，不改写GS-04～09原签收。GS-10/11/12尚未开始，GS-13保持WAIT_OWNER_CONFIRMATION；无生产修改。

Hard Stop：旧Policy事实不明、占用计数遗漏/重复、版本竞态、旧Ticket改写、未知结果重发、正式部署之外自行切容量、超出冻结B的风险扩张/SOR恢复、风险Gate放松、source preservation失败。当前生产仍未授权；最终部署前等待Owner确认。

### 最新Owner amendment优先级

此前已开发的手动step-up启用B路径与相关purpose/锁函数/测试只属于上一版增量，不再是交付目标；必须删除或替换为正式部署集成，不能留作必经步骤或第二Authority。下面历史测试证据保留来源，但不证明当前默认部署合同已完成。

### 默认发布切换实施证据（2026-10-10，仍未整卡签收）

手动Capacity启用application/repository、authorization purpose、专用Owner锁/权限和测试均已移除；不新增Owner必点按钮或伪造TOTP。0009 Schema仍不UPDATE任何Policy。原deploy_compatible_upgrade_identity在正式flat/fenced事务中验证exact0007/0008来源或已安装0009修复来源，源Policy风险/scope完全匹配、SOR-001真实Control paused、时间单调后，原子写入一条compatible_capacity_policy_v0、Policy B和runtime identity。事件绑定source commit/schema/seed、source Policy version/digest与target commit/schema；相同target重试不重复B revision。后续arm保留B的family/strategy-side，不把旧family=1写回。

0009新增BEFORE UPDATE独立PG guard：裸SQL改limit从RED DID_NOT_RAISE修复为拒绝；只允许匹配同事务release event、exact schema/runtime metadata时间、flat/exchange command/internal facts、SOR paused和其余字段保全的A→B。源码side count改成current hold集合UNION去重，考虑未终态Ticket、未释放Netting Domain/Reservation及未解决Command；增加当前hold索引，避免相关全历史扫描。人为terminal标记但Reservation未释放的RED count=0现为1，事务rollback不污染正常链。

末版默认发布focused11 passed：来源0007/0008/0009，原ENTRY enabled/disabled、SOR保持、回滚、重复target、风险/ENTRY/time非法源拒绝。独立冻结9589d0c9的0008源码进程在真实0008库完成Registry/Policy/正式SOR Pause，再升级0009，逐表原列原数据完全一致、Policy仍A；正式identity后才B，此案例包含在11内。旧0004/0005/0006/0007 source inventory被新增列污染的RED已修正，独立4项全通过；这是CAP影响修复，不是GS-13完整preservation/R4执行。

自然CPM BNB/DOGE/SOL三次Observation→正式EntryWorker：前两张不同Instrument/Episode/Signal均dispatched并protected，第三个Signal被原family/directional约束拒绝，新Claim limit/count正确，1项通过。该新用例尚未让两张Ticket都到terminal Review，不作为全卡Done。相邻Unit/Ticket/PG dispatch/unknown共103 passed，原完整Full-chain51 passed（新capacity用例另列，且verify_schema运行期间有独立CAP修订，不绑定exact R4）；末版Mypy163 files/Ruff/diff通过。regular-deploy测试从旧target0008改为当前head后80 passed。

剩余：真实last-slot并发与Policy交叉、双Ticket到terminal及Generic自然membership链、0009更完整nonterminal/非法源/role/provenance测试、Owner只读展示与最终CAP签收；GS-10/11/12尚未开始，GS-13 WAIT_OWNER_CONFIRMATION，production_modified=NO。

默认release末版扩到11项PASS，补原ENTRY enabled的0007/0008源：正式identity先pause原Policy，再生成B，两个revision可同一事务时点但原source时间必须严格更早；0009安装后仅ENTRY已fenced的修复路径允许切B。冻结0008真实源逐表保全仍PASS，Mypy163/Ruff/diff通过。相邻103与Full-chain51是增量前结果，不冒称当前exact candidate；新自然双CPM测试复用原portfolio模块内部helper，架构禁止跨test模块导入的RED已通过把测试合并原模块消除，非skip。旧forward chain test补0009及typed revision声明；Fast曾1346/1349 passed后各有明确RED，不算全套通过，末版Fast正在验证。无Tokyo动作、GS-13未执行。

本轮最终checkpoint：Fast Unit/Architecture **1351 passed，12.56s**；focused默认发布/Claim-to-Ticket/自然双CPM共19 passed（自然测试随后仅移动到原portfolio模块以修复跨test import，移动后自然+architecture3 passed）；Mypy163 files、tracked Ruff与diff PASS。源码仍是本地部分实施checkpoint，不是CAP-01 Done或exact R4；部署脚本的source/target/postflight适配还需与默认B统一，不能据identity组件测试宣称整个真实部署命令已经可用。待完成项维持上一段，目标保持active。

### 双Ticket终态、并发及Owner只读增量（2026-10-10，基于250f8777）

自然CPM用例不再停在protected：两个Ticket各通过原request_exit/durable EXIT、exact TP/Stop CANCEL、flat/ReconciliationMatched、BudgetSettled和ReviewRecorded到terminal。immutable Ticket字段保全、Reservation/Netting释放、strategy-side占用2→1→0；Review显式structural_test_only，不冒充真实venue经济数据。并发分支让两个正式Entry Worker在action-facts读取汇合，原first-eligible arbitration竞争同head Signal仅一个dispatched，另一个不超发；lane释放后剩余不同Instrument Signal被family/strategy风险Gate拒绝。这里证明实际Worker竞争，不冒充两个不同Claim同时越过rank仲裁的独立issue_ticket race；后者仍需补充。

AdmissionPortfolioUsage补nullable limit/count，B的拒绝也冻结strategy-side证据；历史all-null字段从canonical digest排除，旧Decision解析保持digest。readonly Owner controls返回actual max/count，界面显示容量但无启用按钮；OpenAPI生成器重新生成typed客户端，固定pnpm lock安装在本worktree而非复用主工作区不完整依赖。Controls3 tests、全部前端38 tests/13 files、tsc及vite build PASS，chunk>500k为现有warning，不放宽工程Gate。Owner API interfaces35 tests PASS，实际role/浏览器全GS-11仍未签收。

Postflight新增必验B，缺max=2/family exact则fence；81项deploy unit PASS，readonly certifier只接受exact A或B组合，0009 target要求B，16项focused PASS。旧0007→0008 identity专项被当前0007/0008→0009默认发布11项取代；Generic迁移模块目标改current0009，Static source的arm/pause走冻结0007源码进程，目标仍当前源码。27→25不是skip，而是移除两项已被默认B当前合同替代的旧identity测试。0007 source各record/negative/quiescence/Static comparison差分等25项全PASS（79.68s）；seeder exact-row只SELECT自身compare_keys，不因无关新增字段污染source setup，不新增schema fallback。

末版focused capacity/Claim/Decision/portfolio模块60 passed（含sequential/concurrent终态）；MPG/MI额外正式Owner/Selector/Materializer/rebase/Observation→Ticket→Review Policy B自然链2 passed，Claim明确limit=2与family=2。Fast+architecture+interfaces最后1393 passed对应readonly target-B检查加入前源码；末版正在重验，不作为final R4。Mypy164 source/tools、Ruff/diff PASS；GS-13未执行、production_modified=NO。剩余CAP独立不同Claim并发、policy交叉与complete signed acceptance，随后GS-10/11/12；不把本段升级为整卡Done。

末版追加：readonly 0009 target必须max_same_strategy_side=2（A仅作为源合同识别，不可在新目标冒充已默认启用），deployment postflight对应负向81项PASS；随后包含target-B检查的Unit/Architecture/API完整1393 passed、17.44s，Mypy164、Ruff/diff PASS。所有本轮verification进程均已终态，未进入GS-13。前端包安装未改package/lock、未修改主工作区依赖；生成d.ts只新增两个readonly Capacity字段。当前仍IN_PROGRESS，不能把测试数量当作缺项已完成证明。

### CAP-01 本地行为签收（2026-10-10）

**CAP-01 = LOCAL_ACCEPTED。** 本签收覆盖冻结容量行为及本地集成，不是GS-13 exact R4、东京部署或最终生产source/postflight授权。Scope仍CAP-01→GS-10→GS-11→GS-12，GS-13开始前等待Owner确认。

| 合同 | 直接证据 |
| --- | --- |
| 同策略两个独立Instrument/Episode/Signal；第三个拒绝 | CPM sequential/concurrent自然Observation→Entry Worker→protected→退出/CANCEL→Reconciliation/Settlement/Review；冻结Ticket及2→1→0释放；新Claim/Decision绑定limit/count |
| 独立不同Claim抢最后一槽 | real PG issue_ticket同时提交不同MI Claim（不是同head Signal），一ISSUED一ENTRY_LANE_OCCUPIED；保留原Ticket/Reservation/Netting占用后重试第三个仍family拒绝；lane reset是隔离inner-admission fixture，不冒充venue推进 |
| Policy版本、限额身份、Pause交叉 | 三个inner issuance负向零Ticket/Claim/Reservation/Command；单位dispatch计数含自身使用>limit及Policy/Claim限额漂移拒绝；原Command/unknown全模块回归 |
| Family更严格 | 自然BRF2 ETH SHORT protected后SOL SHORT独立Signal拒绝，policy strategy-side=2而family=1；拒绝Decision冻结count=1，不能以通用上限覆盖Family |
| Universe/Authority与旧生命周期不变 | MPG/MI Policy B正式Selector/Materializer/rebase/Observation→Ticket→terminal两项自然链；旧Signal/Universe/Binding冻结、原Full-chain组合仍覆盖退出与未知/partial；未修改Selector/ExitProfile/Regime |
| 默认B及source保全 | frozen0008 executable source→0009逐表旧列保全；仅identity事务切B，source/target/version/digest、rollback/retry/风险非法源/裸SQL拒绝；deployment postflight明确B，否则fence |
| Owner只读、无启用按钮 | actual brc_owner_control四策略读字段/count无runtime UPDATE权限；API/OpenAPI、生成客户端、Controls与全前端测试/build；完整Generic浏览器交互继续属GS-11 |
| 边界 | global3、single2%、gross6%、direction4%、Family2/2/1、Netting1；无rank调度/加仓/抢占；SOR需paused才可部署默认B，现有控制不被恢复 |

Focused acceptance：`test_issue_ticket.py`27、`test_capacity_default_release.py`11、`test_capacity_claim_to_ticket.py`7、`test_command_dispatch.py`27、`test_unknown_outcome_reconciliation.py`15与完整Full-chain54，单次组合**141 passed，143.27s**；real Owner字段/count4 passed；最后Unit/Architecture/API**1393 passed，17.04s**；Mypy164 files、Ruff/diff PASS。Generic迁移25、Generic B自然链2及前端38/build证据见前段，不相加、不用测试数量替代合同。

**Readonly与release Gate分层校正**：通用readonly诊断识别合法A或B，Schema安装未自动切B的合法阶段不得因此变成伪数据；原sole-0009-B readonly硬判把合法source/certification/warming回归误报fail，已移除，仅保留exact A/B组合检查。它不授予默认容量或交易权；本次正式release postflight仍硬要求B，未安装B不得发布成功。第一次141回归在该readonly耦合上101 passed/1 fail，不当PASS；解除错误耦合后完整141通过，未放松实际release B Gate。

截至签收所有本轮验证终态，production_modified=NO；未执行R4 certifier、GS-13准备子项或Tokyo操作。下一卡GS-10 resident hosting独立leases/ticks、restart/bounded status与fairness，再GS-11/12。
