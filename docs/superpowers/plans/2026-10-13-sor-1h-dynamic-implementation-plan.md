---
title: SOR-1H Dynamic Implementation Plan
status: LOCAL_IMPLEMENTATION_PENDING_RELEASE_CERTIFICATION
created: 2026-10-13
design_authority: ../specs/2026-10-13-sor-1h-dynamic-design.md
active_execution_scope: LOCAL_CODE_TEST_ONLY
implementation_status: IN_PROGRESS
production_activation_status: NOT_AUTHORIZED_BY_THIS_DOCUMENT
---

# SOR-1H 多空动态选币执行文档

## 1. 目标与执行边界

**目标：**在现有Trading Kernel交付独立SOR-1H多空策略，复用旧SOR数值选币、Static
首次基线、continuity/previous fallback、Session审计及原15m退出，持续原Dynamic意图，
普通失败自动恢复/次日重试，条件不满足允许空仓等待。

**Owner已授权本地开发、测试与验证，并明确要求部署前等待确认。**本地已实施代码和
disposable PostgreSQL演练，正式部署和策略enable未执行。此前Generic上线授权不替代
本次部署确认，也不视为新Event实时交易权限。
执行前以Owner当时明确指令、AGENTS Standing Authorization与action-time facts为准，
不因计划写了部署步骤就执行交易。Owner不负责挑表字段、锁序、算法抽取或测试框架。

规范来源：[修订设计](../specs/2026-10-13-sor-1h-dynamic-design.md)。设计行为优先于本计划
函数命名示意。所有生产运行代码只在src/trading_kernel，schema只在migrations/trading_kernel。
旧SOR保持退役；退出、资本、杠杆、容量不扩展；无第二订单链或runtime compatibility。

## 2. 已知状态与工作区

1. **已有能力：**旧SOR Selector、数值Golden、双边物化、Session Audit、previous recovery、
   Static rollback、四常驻Worker、Ticket/Command/保护/结算链均存在，可从当前代码复用。
2. **历史证据：**旧SOR已实际完成Dynamic pair activation和真实Ticket交易；证据与范围见
   设计§2。新1h功能已有本地实现，不能借历史成功宣称新功能生产PASS。
3. **实现基线：**从[当前运行路线图](../../current/MAIN_CONTROL_ROADMAP.md)所指exact生产
   Kernel/Schema及已完成修复衔接，执行时刷新git、PG、systemd/exchange；不得把主目录
   较旧dev直接当runtime source。volatile版本仅在该路线图记录。
4. 文档当前在独立`codex/sor-1h-design`工作树；代码工作使用聚焦`codex/*`分支，保留主
   工作区与其他产品线。Registry、shared Selection及schema共享文件顺序修改，不并行抢写。
5. **当前缺口：**本地typed identity、Registry/PG proof、来源、Authority与runtime已接通；
   当前剩余正式发布认证，生产部署和激活未开始。

**分支基线规则：**代码开始前验证本分支包含当时exact production commit，检查差异文件。
dev/main若落后，不为了名字是integration就丢弃生产修复；生产若又前进，则先纳入最新
已认证变更再实施。当前聚焦分支已包含实施时的生产基线；部署前仍需刷新实际生产版本。

## 3. 依赖与交付阶段

**每卡一个实施负责人：当前主实施agent。**默认顺序执行，没有子agent/新线程委托要求。
局部纯函数可独立实现，但shared文件保持单写者。

| ID | 内容 | 前置 | 可验收产物 |
| --- | --- | --- | --- |
| H1-01 | typed身份、每日时钟与Static合同 | 无 | Python/DB一致的行为矩阵 |
| H1-02 | 数值核心复用 | 01 | 旧Golden不变、新旧数值一致 |
| H1-03 | Registry、多空Detector、原退出绑定 | 01 | 1h信号、01:00准备、15m退出 |
| H1-04 | 前向schema/Spec/proof与preservation | 01–03 | 真source迁移到单一head，所有guards有效 |
| H1-05 | 新Static双边基线与readiness | 03–04 | 新身份真实pair，paused准备无交易 |
| H1-06 | Daily Selector/Job/源数据handoff | 02、04 | 每日exact Job与immutable Snapshot |
| H1-07 | 正常pair物化与runtime宿主 | 05–06 | 双STAGED→atomic ACTIVE_NEW/NO_CHANGE |
| H1-08 | 小时Audit、恢复、持续授权与控制 | 07 | Static首次恢复、previous fallback、EMPTY/跨日可推进 |
| H1-09 | Entry/Lifecycle与全局恢复回归 | 08 | 新Signal到保护链，双方向/资金边界不变 |
| H1-10 | Owner API/页面最小适配 | 08–09 | exact控制、真实状态与双方向显示 |
| H1-11 | 整合、正式R4/R2/R1与切换准备 | 01–10 | clean exact candidate与真实source支持 |
| H1-12 | 获授权上线、启用与证据记录 | 11＋实际Owner权限＋hard gates | 部署、激活、交易三层证据分别声明 |

不得跳过H1-04的DB约束，只在Python返回true；不得直接从H1-03 Detector向venue发单。

## 4. Task Cards

### H1-01：冻结新身份与每日时钟

**目标：**定义SOR-1H新合同，明确与旧SOR/Generic分别验证。

- **允许文件：**domain/selection_authority.py、strategy_entry_vacuum.py、instrument_selection.py、
  必要新`domain/orb_session_selection.py`、相应unit tests。
- **要求：**新group/version、LONG/SHORT Event、Spec kind，exact24/7；D Session、D+1h
  cutoff/prepare、最早D+2h、Snapshot D+25h expiry、当日grant截止D+24h、strict未来小时。
  Static基线采用原七币但独立identity；mode支持Static/Dynamic/disabled；持久epoch与原
  authorization以earliest Session校验，不只匹配首次那一天。
  exact identity路由，无SOR前缀/旧身份alias；旧group/Spec/epoch/timestamp proof不能进入
  新group，即使members相同。参见设计§3.2隔离矩阵。
- **RED：**新kind目前路由被当Generic拒绝；错误Event、旧epoch、错误period/cutoff不能
  通过。01:00 prepare与02:00 ENTRY资格必须是不同断言。
- **GREEN/DONE：**frozen Pydantic模型/unknown kind拒绝，双方向完整tuple、当前与新合同
  测试都通过；不会给Generic自动加daily/SOR语义。
- **禁止：**修改旧数值、退出/容量、认证默认值，造生产授权或持久化交易。

### H1-02：提取真实共用选币计算

**目标：**原15m数据同输入保持数值与成员一致，新策略不重写alpha。

- **允许文件：**domain/instrument_selection.py及最小新纯计算模块；unit/test_instrument_selection.py、
  test_dynamic_selection_numeric.py、新1h对照tests；必要Golden verifier接入。
- **要求：**96根15m、OR4、pre-OR ATR14、20M、Decimal38；按ratio/volume/instrument原次序；
  Ready0/1/7/>7、并列边界与source completeness；旧外层Spec/序列化/摘要不变。
- **RED：**新identity当前无法调用旧Spec；提取前写对照与边界用例，证明新入口不存在/不支持。
- **GREEN/DONE：**旧Golden verify与core parity通过；同输入features/rank/members相同，新
  Snapshot/Member身份独立。不可把不同策略完整digest要求相等。
- **禁止：**重建Golden artifacts掩盖差异，float、更换候选、retain hysteresis或新过滤因子。

### H1-03：Registry、多空小时Detector与混合周期

**目标：**两方向都有真实1h Signal，退出仍由原15m Profile执行。

- **允许文件：**domain/strategy_registry.py、detector.py、新detectors/sor_1h.py、
  application/observe_strategy_scope.py、produce_strategy_signal.py（仅必要Session接入）、
  ExitBinding/catalog路由与tests。
- **要求：**当日第一小时OR；LONG上穿/SHORT下穿；session-reference facts含OR、cross、
  eligibility、止损/Reclaim、session start/end；01:00单OR输出完整NOT_TRIGGERED Fact可warm，
  不生成Signal/消费Session；02:00新事实；Session最多一Ticket/方向/币；midnight不补发。
  新Event绑定原同方向Crypto ORB15m Profile，TP1/Runner/ATR/TimeStop不改。
- **RED：**1h Event目前无Detector route；01:00当前SOR要求5根15m；测试证明不应提前触发。
  两方向等号/穿越/未完成/缺口/乱序和旧15m回归合并为小矩阵。
- **GREEN/DONE：**Live/Replay数值与Signal身份一致，initial stop与reclaim方向正确；Profile
  runner.timeframe=15m；96bars仍按实际15m持有计数；旧Event/version不变。
- **禁止：**全局改INTERVAL_MS、legacy exit policy推导小时Runner，借旧SOR Fact ID。

### H1-04：单一前向迁移、payload与proof guards

**目标：**新kind在DB有不可绕过的来源、时间、身份及原子约束。

- **允许文件：**migrations/trading_kernel/versions下一唯一revision、infrastructure/pg_models.py、
  pg_*selection*、strategy_registry_seed.py、runtime_authority_seed.py、runtime_identity.py、
  scripts/trading_kernel/verify_schema.py与相关schema/migration tests。
- **要求：**一张必要immutable Spec payload＋existing tables；exact24/双Event、rank/time/kind、
  epoch/source FK、Static baseline、Authority active/empty、Audit/suppression、target count、
 角色最小grants；Registry/Owner scope/Seed/capability同步正式安装，策略paused。
  current normalized Event baseline复用；旧previous_long/short列不返回。
- **RED：**source→target尚不支持新kind；错误proof、跨Spec/epoch/方向、重复payload、错误
  cutoff/first/expiry、一个方向activation必须被DB拒绝；单纯SQL伪造Python结果不能成功。
- **GREEN/DONE：**disposable真实source升级与blank→head通过，source原列preservation精确
  不变；新增事实仅是声明的新安装结果；新路径停写/flat guard存在。旧SOR/Generic guards
  和旧proof digests不被宽松OR放过。
- **禁止：**编辑历史migration、运行时旧表reader、dual writes、schema fallback、破坏旧控制/票据。

### H1-05：新策略Static基线与正常准备

**目标：**有可证明的新策略Static previous，不能为复用而造旧SOR假来源。

- **允许文件：**application/strategy_universe_batch_manifest.py、现有install/bootstrap use cases、
  scripts/trading_kernel/bootstrap_strategy_universes.py、pg_universe_repository.py、
  entry_restoration_certification.py、certify_readonly.py、相应tests。
- **要求：**只新增新两Event的独立七币Universe/scope/current/immutable baseline，现有四
  家族current不重建、不回Static。paused状态可经正式只读准备，01:00之前未ready则安全
  等待；fresh cert/OR/readiness满足后才建立该策略Static资格，仍受Owner enable。
- **RED：**当前batch没有新Event；新scope若借旧UID/未完整prepare仍不能ready。
  paused prep不得产生任何Signal/Exchange Command；新策略未ready不伪装成生产grant。
- **GREEN/DONE：**new pair及source refs精确，Actor/Policy不自动resume，global restoration/
  readonly certifier/promoter一致依据current facts；合法EMPTY状态由Authority否决ENTRY，
  不按旧bootstrap总数或当前selection_mode误判成功。
- **禁止：**无Static来源直接清Vacuum、把整个批次existing Dynamic重新bootstrap成Static。

### H1-06：Daily Selector与immutable handoff

**目标：**一次Spec/epoch/D Job完成真实来源校验与新身份Snapshot。

- **允许文件：**application/run_instrument_selection.py、interfaces/selection_runtime_worker.py、
  infrastructure/binance_public_market_source.py（仅必要输入规范化）、pg_instrument_selection_repository.py、
  相关runner/repository tests。
- **要求：**每日01:00 due；same epoch earliest D允许后续日；24完整窗口，rank/readiness准确。
  Selector不读取current成员作alpha、不造Generation/Vacuum/Authority；claim→PG外I/O→CAS
  提交Attempt/Snapshot，temporarily unavailable有限重试、确定性错误不无限重抓。
- **RED：**新kind现在进错误Generic/legacy branch；测试重复poll/进程重启、old lease迟到结果、
  missing candidate、quoted timestamps与未来bars不得重复结果或假降资格。
- **GREEN/DONE：**一个immutable成功Snapshot＋exact24 decisions；旧owner无提交权限；
  failure结果与runtime failure分离；次日新Job自动态，原Owner intent不被clear。
  00:00可做历史输入/客户端/基线维护准备；完整排序仍以01:00截止96根为准。可选预取
  不新增强制cache框架，不把92根历史或未完成OR当成最终Snapshot；最后4根及volume
  必须重验。00:00结果与01:00完整请求应有数值一致性负/正例，旧算法Golden不变。
- **禁止：**读旧SOR Snapshot当新授权、网络I/O占PG事务、追加本地JSON运行文件。

### H1-07：正常pair物化与常驻宿主

**目标：**新Strategy通过同一single warming slot完成双边接管。

- **允许文件：**application/coordinate_selection_materialization.py、install/advance universe use cases、
  pg_universe_repository.py、pg_instrument_selection_repository.py、interfaces/selection_runtime_worker.py、
  scripts/trading_kernel/run_observation_worker_once.py、相关tests。
- **要求：**Static→pending Dynamic；PENDING/DESIRED等待不提前Fence，due且slot合法才
  Vacuum/drain/serial warm；STAGED cert与行情readiness过期后warm-only刷新，不开放权限。
  双current＋Authority＋Selection control＋事件＋Vacuum resolve原子。NO_CHANGE不重warm
  或取消合法birth Signal。1800s从原fence计，restart/retarget不重置。
- **RED：**一个方向ready另一个失败；cert/Fact stale；global slot busy/无效队首；pause/control
  CAS变化；atomic commit响应丢失再tick，均不能半切换或重复激活。
- **GREEN/DONE：**真实PG producer链从新Snapshot到两Universe和ACTIVE_NEW，first小时正确，
  真current读取证明完成；15m旧SOR/四Generic相关queue与cert回归保持通过。
- **禁止：**新daemon/第二slot、直接SQL补ARMED、借Generic consumed-close重算Session Signal。

### H1-08：小时Audit、失败恢复与持续Owner控制

**目标：**复用旧SORdaily决策，小时审计与长期意图不会互相卡住。

- **允许文件：**domain/selection_authority.py、strategy_entry_vacuum.py、application/owner_control.py、
  coordinate_selection_materialization.py、interfaces/authority_gap_audit_source.py、pg_selection/owner repositories、tests。
- **要求：**首次source失败Static继续；首次post-fence失败恢复真实Static；已Dynamic按
  PRE_FENCE_CONTINUITY继续current，post-fence失败FALLBACK_PREVIOUS恢复真实previous。
  VALID_EMPTY成功不补位；日后nonempty按真实EMPTY basis/物理current区别接管。小时Audit
  union/current范围、positive suppression/negative、严格未来first、跨first clock rollback。
  Static恢复使用Session proof，不套Generic rising-edge ARMED。Pause最高优先。
- **RED：**首次授权错过日/失败后原epoch丢失、自动fallback固定Static、小时gap被15m结果
  替代、second-cross补票、Owner pause中fallback、unknown未清就resolve；均失败。
  连续NO_CHANGE要保留合法birth，同Session真实失权则不得恢复旧Signal。
- **GREEN/DONE：**首次失败与次日成功沿同original authorization；正常ordinary failure不
  需要人再TOTP；原fence/lease/history保留，新due能正式supersede/retarget并解决负向状态。
  terminal FAILED_CLOSED不能被当作不blocking直接删除。无合法future close则明确等待。
- **禁止：**额外Generic一次miss/48h规则、02:00全天截止、清unknown、假TOTP或Owner Pause版本。

### H1-09：Admission、保护与操作恢复回归

**目标：**两方向都通过既有Ticket链，当前安全预算不变。

- **允许文件：**application/ingest_signal.py、build_capacity_claim.py、issue_ticket.py（仅新Event接入）、
  interfaces/lifecycle_worker.py（必要Profile路由）、runtime seed/restoration/verifier、affected tests。
- **要求：**exact Registry/scope/current/birth lineage、original Fact TTL、same Session/方向；
  原Netting Domain、Family和global serialization；Profile binding在Claim/Ticket冻结。
  新long/short保留各自保护参考与15m退出；已成交Ticket不因selection变化重写/主动flatten。
- **RED：**跨策略/方向grant、stale事实、同域重复、当日第二Ticket、latest-ID误伤合法birth；
  新策略Scene复用recording fake证明所有bootstrap/warm/cert/Audit零venue mutation。
- **GREEN/DONE：**两方向local production-shaped链通过；durable-before-dispatch、拒绝终态、
  unknown不重发、既有partial处理回归；global恢复依据与API显示同一事实，不无条件豁免。
- **禁止：**为新策略调整风险Reducer/退出、扩预算、生产强制下单产生验收样本。

### H1-10：Owner API与页面最小适配

**目标：**一个Owner可读懂新策略多空、Selection结果和接管状态，无内部手工操作。

- **允许文件：**application/owner_console/strategies.py、interfaces/owner_console_http/routes/
  strategies.py与controls.py、相关schema、frontend现有StrategyPage/SelectionControlPanel及tests。
- **要求：**Static/Dynamic/disabled、pending intent、source/selection ages、pair readiness、
  Authority outcome/first close、稳定first blocker；显示1h entry/15m exit、多空独立状态。
  继承真实purpose/scope/version/idempotency/TOTP；不把Snapshot ready显示为active。
  新策略显示SOR-1H（1h入场/15m退出），旧SOR显示15m及已退役；日志/历史/P&L查询用
  exact group/version/事件来源，不以SOR前缀混合统计，不重标旧Ticket为新策略。
- **RED：**新Spec hardcoded不支持；unknown/current mismatch、Snapshot成功但pair未ready、
  valid empty、paused状态；显示不得启用旧SOR或要求Owner操作租约/审核每单。
- **GREEN/DONE：**只需既有页面局部接入，API/UI一致；普通故障显示自动等待，明确事故
  才要求Owner处理。读接口无数据库写入、无Actor/Policy副作用。
- **禁止：**重做Owner Console、SaaS多租户/审批流程、复制控制API或绕过正式Kernel入口。

### H1-11：精确版本认证与切换准备

**目标：**完成一套真正支持新source→target的正式发布方案，不在Tokyo试错。

- **允许文件：**scripts/trading_kernel/deploy_tokyo_release.py、verify_schema.py、seed_runtime_authority.py、
  release/profile/registry verification（必要新source支持）、相应deployment tests与current docs。
- **要求：**当前部署脚本的compatible source allowlist并非任意head；增加本次actual source
  的stopped-flat-forward verifier、source column preservation、registry/scope扩展与exact
  runtime compatibility分类。不可强传旧source revision过关。正式install/基线准备继续只读
  且策略paused，global Policy/Owner Resume的实际新版本正确，旧策略控制/历史完整。
- **RED：**wrong source/commit/schema、停止API遗漏、source前后变化、unreviewed terminal或
  active Ticket/Command/Incident、migration响应unknown、target identity错误均拒绝。
- **GREEN/DONE：**本地disposable source rehearsal PASS；candidate clean，exact R4/R2/R1
  manifest与内容一致，无dirty/旧commit借证书；发布分类正确。文档只把volatile事实记录
  MAIN_CONTROL_ROADMAP，不提前宣称Tokyo启用。
- **禁止：**long soak前置、历史suite重复整跑、降级migration、old-schema writer恢复、手工改PG。

### H1-12：实际获授权部署、启用与分层验收

**目标：**在权限及hard gates满足后完成官方发布与新策略自然运行验收。

- **允许范围：**正式deployment/Owner API发布、readonly probes、官方Owner控制/promoter；
  PG/交易所只读及MAIN_CONTROL_ROADMAP事实记录。
- **前置：**H1-11全部PASS；Owner已授权本次新策略scope/部署/启用；action-time正确account/
  venue/profile/Policy/schema、独立多空、无敞口残单/unknown/Incident/Reservation或未完成迁移。
  若持仓阻塞报告Owner，不自动flatten；保护/退出保持原writer直到合法停止。
- **步骤：**fresh source→stop API/所有writer＋Fence→second authoritative preservation baseline→
  forward migration/identity→new paused Static pair正式prepare/认证→target preservation/controls→
  API部署→实际Owner Scope/Selection/strategy/global Resume→official promoter→readonly检查。
  prepare不等于enable；策略enable与Dynamic首激活分开记录。
- **DONE证据：**exact deploy/schema/Registry/Seed/tag、四Worker/API及Fence、Owner真实版本；
  新strategy actual Snapshot→双Universe current→Authority→合法first小时；自然Ticket的
  protection→exit→exchange flat→Reconciliation/Settlement/Review→预算/domain释放分别记录。
  双方向local证据完整；生产自然只出现单方向时另一方向标为未自然观测，不强造交易。
- **Hard Stop：**任何live hard gate失败立即停止相关venue写；未知identity不能假定回滚。
  新策略暂停可继续已有Ticket保护；跨schema故障fix-forward，不降级/偷跑旧writer。

## 5. 最小验收矩阵与测试分层

| 断言ID | 行为 | 覆盖任务 |
| --- | --- | --- |
| A01 | 新旧同输入features/rank/members一致，旧Golden不变 |02、11 |
| A02 | LONG/SHORT方向、Session一次Episode、02:00前无入场 |01、03、09 |
| A03 |01:00可warm且无Signal；Profile仍15m/96bars |03、05、09 |
| A04 | Static首激活前继续，首次失败恢复Static且原授权保留 |05、07、08 |
| A05 | 已Dynamic source失败走continuity，switch失败恢复previous |07、08 |
| A06 | 双边atomic、single slot、cert及warming path fresh |04、07 |
| A07 | 迟到未来小时＋小时Audit；连续NO_CHANGE合法birth保留 |01、07、08、09 |
| A08 | VALID_EMPTY不补位，new due可supersede，FAILED_CLOSED不偷清 |04、08 |
| A09 | Pause/TOTP/epoch目的明确；旧SOR不恢复 |04、08、10 |
| A10 | Same-domain/global/Family/风险限制与原保护不变 |09 |
| A11 | Source preservation、paused install、schema/身份与role guards |04、11、12 |
| A12 | 一轮必要混合due验证bounded I/O、lease、loop与零运行文件 |06、07、11 |
| A13 | 新旧identity/授权/记录严格隔离，UI/日志/统计清晰，旧SOR保持退役 |01、03–04、08–10 |
| A14 | 00:00准备无grant；01:00完整96根与原排名一致；02:00合法小时信号 |02–03、06–08 |

### 5.1 日常开发

每次生产行为改动先最小RED，再GREEN/refactor。只运行改动边界与必要negative/fault回归，
共享代码变化再扩大受影响旧SOR/Generic范围；不为每卡启动全量认证。
local/disposable tests不碰生产，不用研究report作为runtime authority，不重建Golden。

可复用的现有测试入口（实现新增用例后按实际node选择）：

```bash
.venv/bin/python -m pytest tests/trading_kernel/unit/test_instrument_selection.py tests/trading_kernel/unit/test_selection_authority.py -q
.venv/bin/python -m pytest tests/trading_kernel/integration/test_selection_materialization_repository.py tests/trading_kernel/integration/test_selection_entry_authority_repository.py -q
.venv/bin/python -m pytest tests/trading_kernel/architecture/test_current_document_authority.py tests/trading_kernel/architecture/test_project_skill_authority.py -q
```

不假装这些既有文件已经包含新1h验收；implementation ledger记录实际新增node、RED/GREEN
输出和commit。测试数量不是验收质量证据。

### 5.2 最终候选与必要发布检查

冻结clean候选后使用当前official command set，一次exact R4含unit/architecture/integration/
full_chain、Ruff/Mypy/diff以及旧SOR Golden/core parity。API实际变更需R2，前端变更需R1。

```bash
.venv/bin/python scripts/trading_kernel/certify_release_candidate.py --release-level R4
.venv/bin/python scripts/owner_console/certify_release_candidate.py
```

R4已包含Golden与core parity，不在认证前后无理由再重复整跑。core parity若缺本地只读
官方输入缓存，核对可用位置/显式路径并报告实际阻塞，不能跳过或生成伪PASS；缓存非
生产输入。短混合due场景不变成long soak、资源压测或上线前额外等待。

来源：[verification portfolios](../../../scripts/trading_kernel/verification_portfolios.py)。

## 6. 状态台账与完成口径

**Owner已授权本地开发、测试和验证，要求部署前等待确认。**实现正在进行；未完成卡不标
DONE，不把定向通过当作完整R4或生产验收。所有Tokyo写、部署、迁移和enable仍待Owner确认。

| 阶段 | 实际证据 | 当前状态 |
| --- | --- | --- |
| 文档 | 修订设计、12张依赖卡、引用与diff检查、84项architecture检查通过 | COMPLETE_DOCUMENTATION_ONLY |
| 代码/DB本地 | 身份/时钟、多空Detector、共用数值、Spec/Snapshot、恢复与完整交易链已有本地证据 | LOCAL_IMPLEMENTED |
| 发布认证 | H1-11 exact R4/R2/R1；首轮R4失败已定位并修复，等待最终候选认证 | IN_PROGRESS |
| Tokyo部署 | H1-12 hard gates、正式deploy、paused基线prepare | NOT_STARTED |
| 新策略启用/双边接管 | 真实Owner控制、PG双current＋Authority | NOT_STARTED |
| 自然交易终态 | 实际Ticket保护、flat/settlement/review、释放证据 | NOT_STARTED |

执行后在各卡追加真实commit、节点、失败原因、done evidence；不改写旧事实或给未执行
项标PASS。若本地认证全过但自然信号未出现，分别报“工程/部署完成、自然交易待观测”；
允许等待，不强行开仓。相应当前状态仅在MAIN_CONTROL_ROADMAP记录。

## 7. 安全证明与不变边界

- **一条Kernel链、一Ticket/Episode、一ENTRY generation、全球串行新入场。**
- **新多空隔离、不加仓、不扩资金/杠杆/Family/单策略或global容量。**
- **durable command先于venue写、unknown不盲重发、初始保护与partial处理原规则。**
- **原SOR永久退役；新Static/Dynamic事实不借旧身份或权限。**
- **网络事务外、cert/warm/Owner/clock proof全部真实、原fence/deadline不延长。**
- **stopped-flat-forward与preservation，不downgrade，不dual write，不手工SQL repair。**
- **原授权与下一日自动态持续；正常空仓等待可接受，明确事故才让Owner处理。**

本文件结束于可执行依赖与可检验完成条件，不制造新审批层或交易盈利前置要求。


### 本地实施证据（2026-10-13，未部署）

- 身份/每日时间/严格未来close/原epoch跨日，以及小时Authority拒绝旧15m证明已观察RED/GREEN。
- 多空Detector、01:00准备、错误clock/Session/path及原15m Profile绑定有定向证据。
- 当前核心对旧961个Snapshot、23,064成员决策完整Core parity PASS；数值csv.gz未重生成，
  manifest仅增加前后源SHA与该次parity provenance。原Golden verify随后PASS。
- 新0011 migration在local Docker disposable PG创建独立Spec payload；新Spec安装paused，
  Candidate24/双Event、Snapshot完整来源/rank检查、保存/读回/immutability定向测试通过。
- 首次fast inventory 1640 PASS、2个catalog/migration清单断言需同步；它不是最终认证。
- Job/Static基线/runtime materialization/小时Audit/Owner接入、完整migration preservation/
  release tooling仍在开发，H1-11 exact R4尚未执行。当前分支不可部署。

### 本地链路接线证据（2026-10-14，仍未部署）

- 新 Static 双边基线可正式安装/激活；Owner 原始 intent 与同 epoch 在后续日领取 Job，源失败完成后原控制不变。
- 真实 PG 的成功 Job/Attempt/Snapshot 路径已接到独立 pair Coordinator，正常 NO_CHANGE 与 changed-member ACTIVE_NEW 跑通；新两侧 current、旧成员退休、Vacuum 与 Authority/模式切换原子提交。
- first post-fence timeout 恢复实际 previous pair，保留 Static 与原 Dynamic 授权/epoch/control，未清空原 intent；合法 VALID_EMPTY 完成 drain 后不补币。
- 小时 Gap Audit 使用 exact 新 pair/detector digest 和真实 1h 行情路径；01:00 准备可证明零 eligible gap，迟到使用严格未来小时，23:00 后不跨 Session 授予入场。
- 已验证 next-day PRE_FENCE_CONTINUITY、Owner pause negative fence。Entry resolver 已按新 pair 精确解码；local seed 仍关闭全局 ENTRY，未宣称真实 Ticket 链通过。
- 中间定向检查 126 passed（日志 `/tmp/brc-orb-incremental-validation.log`），后续修改仍需重新验证；不是最终 Release/R4。
- 仍需完成：generation-free pause/resume、EMPTY→nonempty、Static rollback control、数据库 Audit/Owner proof/direct-SQL negative coverage、staged-hour freshness、宿主及 Owner API/UI、migration preservation/source0010/release tooling、双方向完整 Ticket 链和最终 exact candidate 审查。
- 本轮所有操作仅限本地工作树/disposable PostgreSQL。服务器部署、数据库升级、启用与交易所写入均未执行；候选仍不可部署。

### 接线阶段检查点（2026-10-14）

- 无 Generation Owner pause →正式 resume →小时审计→RESOLVED_CONTINUITY 已完成真实 PG 正向验证；直接 SQL 伪造 Audit COMPLETE、无 Audit 解除暂停围栏均被拒绝。
- Audit ledger 校验 exact 新 Event、每成员结果、scope/result digest、Session/1h window与suppression；Generation来源要求实际成功 Job/Attempt及24成员。
- 新 NO_CHANGE 接管前正式 CERTIFY_CURRENT：过期当前 pair 不授予 Authority，刷新后恢复推进。
- 共享旧 pair PG 回归加上述新路径：204 passed / 48.14s，日志 `/tmp/brc-orb-pair-regression.log`。
- 改动的7个生产模块 Mypy PASS；局部 Ruff与diff check PASS。此检查点不含全部QA/Release，也不代表部署候选已完成。

### 宿主与只读/Owner 接线检查点（2026-10-14，未部署）

- 新 group 的 Selection/Materialization/Facts 常驻逻辑循环接入既有 Observation service，不增加systemd进程或冷启动timer。
- exact staged 1h readiness refresh 复用Observation事实链；完整新pair14 scope正向验证不生成Signal/ENTRY，前后重新核验epoch/Generation/Vacuum/Owner/runtime identity，原30min deadline不延长。
- 当前pair NO_CHANGE须CERTIFY_CURRENT；过期pair拒绝，正式刷新后继续。迟到首次NO_CHANGE由小时Audit接管，未来close与suppression落库。
- API Dynamic activate新身份单独路由；旧SOR仍拒绝。新只读Job使用当前epoch，独立Preview明确UTC01准备/UTC02资格与1h入场/15m退出，不套Generic missed/staleness字段。
- 历史CLAIMED Job被当前日正式Job supersede，保留原Owner intent；Session过期禁止源读取，错误计算记录失败。
- 相关Slice 152 passed / 15.23s，`/tmp/brc-orb-host-final-slice.log`；8个生产/宿主模块Mypy通过。仍不含最终Release/R4、Frontend/R2、source0010 preservation或新Ticket完整链。

### Owner界面与正式角色检查点（2026-10-14，未部署）

- 新SOR-1H使用独立控制面板与Preview，显示每日01:00准备/02:00最早资格、当日Job/选择数/Authority；旧SOR-001明确退役。未安装/读失败/pending时禁止Dynamic提交，不借Generic staleness与missed字段。
- Dynamic HTTP重复请求在原authorization/idempotency下返回当前control，首次请求仍先version后TOTP；旧SOR激活仍拒绝。
- 正式brc_owner_control按发布role SQL可冻结独立双边Static基线；lock-only SECURITY DEFINER函数限exact新Spec/Static状态，仅锁两current，不授权Owner更新Universe/交易表。直接更新current被拒绝。
- Owner HTTP＋真实PG Slice 55 passed / 15.32s，`/tmp/brc-orb-owner-pg-slice.log`；控制页相关19 tests passed；前端TypeScript typecheck通过。
- 本地未执行部署/迁移/启用/真实订单。仍需完成手动Static rollback、完整1h源到Ticket保护/退出链、cross-hour deadline与source0010 preservation、official release验证与最终审查。

### 本地候选冻结前证据（2026-10-14，未部署）

- 已完成手动Static rollback的独立Owner intent、frozen baseline、新双边materialization、cert/warm/小时Audit及atomic mode commit；旧UID不复活。Static失败恢复实际previous，保留original Static intent在下一日重试；再次Dynamic创建新epoch。
- 已覆盖EMPTY→nonempty的重新物化；失败不能复活dormant physical members。Generation冻结previous grant disposition/Authority引用，negative recovery保留EMPTY与fence，新日结果合法重定向而不重写FAILED terminal事实。
- Audit ID包含epoch/Generation/Vacuum来源；UTC23后不创建新交易grant。Selector宿主lease至少120s，物化原1800s deadline不延长。
- 新LONG/SHORT的Static与Dynamic生产形状链，从真实closed market/Selector至Ticket、初始保护、TP1、runner、reconciliation、settlement、Review均有本地定向证据；未使用真实交易所写。
- core admission/dispatch共同拒绝永久retired SOR-001；当前入场基础fixtures迁到活跃新策略，历史数值与源schema probes保留。
- exact0010 source真实terminal Generic Ticket与Owner修改的ExitProfile Binding参与保留验证；DDL前后原行digest一致。identity初始化只新增指定pair，保持新group/globalENTRY paused，保留已有Exit选择。
- 新pair-only bootstrap经正式Reconciliation certification与Observation warming验证，仅安装两个new current、zero Command；现有Dynamic组不重装。
- 生产readonly刷新仍为原0010版本；本分支包含其commit，主工作区未改。本地full静态检查Ruff/Mypy通过（195 sources），Fast1664通过，接线/Admission/chain affected Slice89通过，Frontend控制19通过。最终exact R4/R2/R1尚未执行，不能将这些Slice作为Release PASS。


### exact Release 候选冻结（2026-10-14）

- H1-01..H1-10的本地实现已有目标边界RED/GREEN和PG/producer/full-chain证据；新Static/Dynamic双侧复用原15m退出，永久旧SOR ENTRY core/dispatch禁止，正常恢复沿原授权。
- 源0010含真实terminal Generic Ticket、Owner变更后的ExitBinding；DDL前后旧行hash一致，identity只扩指定新pair、保持global/newgroup paused、保留其他Owner退出选择。
- pair-only bootstrap通过正式certification/warming producer，zero Command；仓库全静态Ruff/Mypy（195文件）及Fast1664通过，前端相关19 tests通过。
- 本次冻结后执行official exact R4 / R2 / R1。任何失败都修复后重新冻结；不得把定向数字视为最终认证。
- H1-12未开始。没有部署、生产升级、策略启用或exchange写。最终结果必须与生产自然Dynamic/交易证据分开声明。


### 正式认证失败收敛（2026-10-14）

- 首轮R4 Integration返回91 failed / 2 errors，候选未通过。按根因修复，不将该次部分通过记录解释为认证通过。
- 来源Registry/Policy/shape按exact来源版本，旧0003/0004/0008 inventory排除0011新表；0009历史capacity安装和同schemaidentity不隐含新增策略。
- 修复readonly bootstrap核验，将新独立双Event/七成员纳入初装清单，同时保留原批次认证、Registry/Policy/seed、flat和Ownerproof守卫。
- 当前ENTRY fixture使用SOR-1H；历史SOR的bounded chain/unknown birth/Owner pause测试仍保留只读语义，禁止新ENTRY。原旧SOR dispatch-acceptance测试删除，其运行中Authority变更拒绝由Generic真实rebase/dispatch回归及新SOR完整链覆盖。
- 新SOR Dynamic/Static授权页面覆盖未知响应同意图重试、冻结baseline/epoch及409阻断；公共promotion harness复用，删除test内重复实现。
- 组合回放采用SOR-1H-SHORT小时Session，保留三Ticket/资金/方向容量断言；新LONG/SHORT Static/Dynamic正式producer到terminalReview链无真实venue写。
- 定向修复已GREEN；最终exactcommit认证仍待执行。生产未改动，H1-12仍NOT_STARTED。


### 0010→0011部署后检查补齐（2026-10-14）

- `2c39c798`已取得完整R4/R2/R1 PASS，但最终人工源码复核发现旧postflight固定8 Binding与全Universe假设不适合新策略首次安装，因此该候选不作为最终部署交付。
- 官方0010 cutover现在显式识别新pair独立paused/not-prepared状态：原8个Universe完整且digest与停止时baseline一致，新Spec已安装、exact Static control无pending/epoch、策略paused、global ENTRY关闭，无warming。软件升级PASS不宣称新pair已ready，也不授予任何ENTRY。
- 原ExitProfiles数量不增加；当前Binding精确10，允许保留Owner已产生的额外immutable Binding/Activation历史，仍要求catalog/current/reference/event完整性通过。
- 真PG全8个来源Universe场景验证paused/not-prepared可完成软件postflight但Entry恢复仍为false；Owner退出切换后11个Binding事实保留；新策略enabled则postflight拒绝。
- 新负向覆盖错误成员／历史digest、missing Binding、pending intent和提前enabled，维持Fence。随后只准备SOR-1H新pair，不重装Generic Dynamic。
- 必要部署定向回归通过后重新冻结候选与exact正式认证；H1-12保持未开始。
