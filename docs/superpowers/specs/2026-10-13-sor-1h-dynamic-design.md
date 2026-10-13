---
title: SOR-1H Dynamic Engineering Design
status: DESIGN_DRAFT
created: 2026-10-13
scope: Independent hourly opening-range strategy in the existing Trading Kernel
---

# SOR-1H 动态选币与小时入场设计

## 1. 结论与范围

**第一版新增独立 SOR-1H 策略，复用旧 SOR 动态选币计算，仅将入场确认改为完整小时收盘。**
交易成员按每日 Selection 变化；不先上线固定交易成员版本。退出继续采用现有 Crypto ORB
15m ExitProfile 的实际语义，执行、资金与生命周期继续由现有 Kernel 持有。

**本文是可评审设计，不是生产权限，也不宣称功能已经实现。**新策略的安装、启用和实盘权限
必须经过各自正式边界。工程选择由实现者负责，以下默认产品行为是设计假设，不冒充 Owner
已逐项确认的冻结决策。

### 1.1 已明确的需求与默认假设

| 项目 | 本版设计 | 依据与状态 |
| --- | --- | --- |
| 策略方向 | 新建独立小时策略，支持 long / short | 原对话要求与既有多空 SOR 语义 |
| 选币 | 复用原资格、特征、排序和每天计算一次的规则 | Owner 明确要求复用旧动态选币 |
| 交易成员 | 每日动态选择，最多7个；候选母池仍沿用旧算法的24币 | 不把候选母池误称为固定交易池 |
| 开盘区间 | UTC 00:00–01:00 | 沿用原一小时区间定义 |
| 入场 | 1h 收盘穿越，最早 UTC 02:00 | 本次核心行为变更 |
| 退出 | Reclaim、TP1、Runner、ATR、TimeStop 采用原 Profile | 默认假设：Owner 未要求一起改变退出 |
| 重复触发 | 同币、同方向、同 UTC Session 最多一张 Ticket | 沿用 session-reference Episode 与终态拒绝语义 |
| 容量与资本 | 复用现有 Policy 与 opening_range Family，不增加额度 | 不创建独立资金池或额外容量 |

来源：[需求对话](codex://threads/01a1341c-4275-75b3-b806-99a9e0f96fe0)；
[Registry](../../../src/trading_kernel/domain/strategy_registry.py)；
[Signal Episode 生成](../../../src/trading_kernel/application/produce_strategy_signal.py)。

### 1.2 交付边界

1. **包含：**身份、Detector、动态选币、双边 Universe、Authority、Owner 控制、每日调度、
   缺口审计、认证、保护接入、数据库前向迁移与必要验收。
2. **不包含：**新选币因子、小时退出变体、扩容、盈利评审流程、参数搜索、长期资源审计、
   强制产生实盘交易或恢复退役 SOR。
3. 不创建独立交易服务、第二订单链、文件授权、运行时兼容适配或旧 schema fallback。

## 2. 已知事实与设计分析

### 2.1 当前代码已知事实

| 边界 | 当前事实 | 设计影响 |
| --- | --- | --- |
| SOR Detector | 使用当日连续15m序列，前4根定义 OR | 新增小时 Detector，不能只改 Registry timeframe |
| 旧 Selector | 96根15m；OR4；开盘前 ATR14；24h quote volume；Decimal38 | 算法计算可以原样提取，不把输入一起改成1h |
| SOR Spec / Period | 硬绑定 SOR-001/v4、多空 Event、01:15 eligibility | 新策略必须持有独立身份和小时资格时钟 |
| Generic Spec | 仅冻结 CPM/MPG/MI/BRF2；单 Event；rank/retain 语义不同 | 不把 SOR-1H 塞进某个既有 Generic 家族 |
| Session Episode | Signal身份由 Event、币、方向、Session事实决定 | 小时内多次穿越不能创建第二日内 Episode |
| Lifecycle | 数据周期取冻结 Profile.runner.timeframe | 1h Entry 与15m退出可以明确分离 |
| 认证 | warming、staged、active 均可刷新，Instrument先于Certification锁 | 新双边物化必须使用同一认证路径 |
| 表约束 | Selection kind、epoch、时间、成员数和proof均有DB校验 | 新策略需要前向迁移，不能只新增Python配置 |

来源：[旧 Detector](../../../src/trading_kernel/domain/detectors/sor.py)；
[Selector](../../../src/trading_kernel/domain/instrument_selection.py)；
[Generic Spec](../../../src/trading_kernel/domain/generic_selection_spec.py)；
[Authority](../../../src/trading_kernel/domain/selection_authority.py)；
[Lifecycle Worker](../../../src/trading_kernel/interfaces/lifecycle_worker.py)；
[Universe Repository](../../../src/trading_kernel/infrastructure/pg_universe_repository.py)；
[0008迁移](../../../migrations/trading_kernel/versions/0008_generic_dynamic_selection_v1.py)。

**当前部署身份与 Generic 实际接管进度只由**
[MAIN_CONTROL_ROADMAP](../../current/MAIN_CONTROL_ROADMAP.md)**记录**。实现从该运行基线衔接，
不把主目录较旧的 dev HEAD 当作生产代码。本文不复制 volatile 生产身份。

### 2.2 方案比较与选择

| 方案 | 计算复用 | 身份与时钟 | 主要代价 | 结论 |
| --- | --- | --- | --- | --- |
| 修改旧SOR周期 | 高 | 覆盖退役策略语义与历史 | 破坏历史身份和授权边界 | 拒绝 |
| 复制全部SOR实现 | 低 | 可独立但易漂移 | 两套排序、恢复、物化逻辑 | 拒绝 |
| 共用纯计算与现有物化链，增加精确小时契约 | 高 | 独立身份，冻结时钟 | 一次解除Event/15m常量绑定，补DB proof | **采用** |

**只抽取真实共用计算与流程，不引入可配置任意算法的框架。**支持集合由 Registry 和冻结
Selection 契约列举，未知身份显式拒绝。旧 Golden 输出与持久化摘要保持原值。

## 3. 新策略身份与权威

### 3.1 建议冻结的身份

以下为**新设计命名**，不是已经存在的 Registry 记录：

| 对象 | 建议身份 | 语义 |
| --- | --- | --- |
| StrategyGroup | `SOR-1H-001` | 独立Crypto小时ORB |
| StrategyVersion | `sgv:SOR-1H-001:v1` | 小时入场、旧选币、15m退出 |
| LONG Event | `event_spec:SOR-1H-001:SOR-1H-LONG:v1` | 小时上穿 |
| SHORT Event | `event_spec:SOR-1H-001:SOR-1H-SHORT:v1` | 小时下穿 |
| SelectionSpec | `SOR_1H_OR_ATR_DYNAMIC_V1` | 每日24选最多7；双边使用同一成员集合 |
| Selection kind | `orb_session_dynamic_v1` | 每日Session、有epoch的双Event契约 |
| Exposure Family | `opening_range` | 复用现有Family限制 |
| Episode | `session_reference` | Event+币+方向+UTC日 |

1. Snapshot、Job、Generation、Universe、Authority、Gap Audit和Signal均携带新身份；
   旧 Spec、旧 epoch、旧授权、旧 Universe不能为新策略提供交易权限。
2. 新 LONG/SHORT拥有两个Universe，但一个每日成员集合、一个Generation、一套原子接管。
3. 同币同方向仍共用现有 `venue + account + instrument + position_side` Netting Domain；
   SOR-1H与其他策略发生占用冲突时，现有Admission拒绝，不另开domain。
4. 使用现有Crypto RuntimeProfile和sole Owner Policy；是否纳入具体Event scope由正式
   安装/启用边界持有，不由名称推断。不增加资本、杠杆、Family或Ticket限制。
5. 新Event各自绑定现有相同方向的Crypto ORB15m ExitProfile。无需复制Profile内容，
   新EventExitBinding有自己的身份与摘要，Ticket冻结实际binding和profile。

## 4. 四个时钟分别定义

令 `D` 为UTC当日00:00，`H=3,600,000ms`。**行情输入统一采用exclusive close boundary**；
Binance end-minus-1ms仅在adapter边界归一化。退出既有watermark逻辑保持自己的协议。

| 时钟 | 冻结边界 | 所属权威 |
| --- | --- | --- |
| Selection输入 | `[D-23H, D+H)` 的96根15m | SelectionSpec与不可变Snapshot |
| OR | `[D, D+H)` | Detector与冻结保护/退出参考事实 |
| Selection cadence | D+H计算，每UTC日一次 | 持久化Job及epoch |
| 新成员准备 | Snapshot commit后即可准备，最早D+H | Generation；不等于可以入场 |
| 第一入场close | D+2H；此后整小时 | 新Event与Authority |
| 当日新ENTRY截止 | `close < D+24H`，最晚23:00 | Session与Signal/ENTRY重验 |
| Selection源期截止 | D+25H，即下一日01:00 | 下一次每日Selection边界 |
| 退出数据 |15m完整收盘；保护单不等待小时 | Ticket冻结ExitProfile |

**Selection Period与交易Session不是同一个截止时间。**00:00–02:00不能用昨日OR或昨日
Signal交易，即使旧成员membership仍有来源记录。下个Session必须形成自己的OR和Authority。

**正常时序：**01:00取得完整输入 → Snapshot提交 → 串行warming/认证 → 两边STAGED →
原子激活/提交Authority → 第一合法入场close为02:00。允许在02:00之前激活，但Authority
必须显式冻结 `first_eligible_close_time_ms=02:00`，提前发Signal或ENTRY均拒绝。

## 5. Detector、Episode与退出

### 5.1 小时入场

1. 新Detector读取从D开始至当前触发close的**连续完整1h K线**，范围不超过当日24根。
   第一根定义OR，至少两根才能计算首次突破。线上读取官方1h数据；必要的15m区间一致性
   校验只比较已完成数据，不用未完成小时聚合或补造缺失K线。
   **01:00单根OR是合法准备输入，不是数据缺失。**时间资格条件为false，Detector可以
   返回明确的NOT_DUE/非触发事实，warm-only路径形成完整OR与保护参考readiness；它不能
   推断未来cross、推进正式Session消费或Recovery状态。这样可以在01:00–01:30完成准备，
   不必等02:00而必然触发30min超时。Active Observation在02:00重新取得实际两根或更多
   小时序列，初次warming事实不能代替新Signal事实，也不靠延长freshness等待。
2. LONG：`previous.close <= OR.high && current.close > OR.high`。
3. SHORT：`previous.close >= OR.low && current.close < OR.low`。
4. high/low触碰或小时内穿越不算入场；02:00之前、非整小时、乱序、缺失、重复、跨Session、
   当前未完成K线均拒绝。24:00属于新Session边界，不能继续产生前一日Signal。
5. 产出新v1事实：OR已定义、当前方向cross、结构止损参考、Reclaim参考、session_start与
   session_end。Fact freshness从真实close开始，不能靠轮询不断延长。
6. 多头Initial Stop参考OR.low、Reclaim参考OR.high；空头反向。价格量化、最小数量、
   费用与保护可行性由现有Claim/Protection执行，不由Detector分配quantity。
7. 同日后续cross复用既有Session Episode，不能因Universe、Authority、部署或暂停恢复
   创建新Episode；已拒绝的Admission同样不重试。多空为独立Episode和Netting Domain。
8. Signal expiry取Fact有效期、Session截止与适用Authority限制的最小值；Entry仍重验
   当前Universe、birth Authority与action-time facts，不因1h Signal放宽交易事实TTL。

来源：[旧cross逻辑](../../../src/trading_kernel/domain/detectors/sor.py)；
[Signal身份](../../../src/trading_kernel/application/produce_strategy_signal.py)；
[现有策略链](../../current/P0_TRADING_KERNEL_REBUILD_DESIGN.md)。

### 5.2 保持退出实际语义

| 项目 | 本版行为 | 时钟/限制 |
| --- | --- | --- |
| Initial Stop | OR另一侧，现有保护路径 | 成交后保护，无小时等待 |
| TP1 | 1R，原50%数量与limit_gtc规则 | 按实际成交与两腿可物化条件 |
| Reclaim | TP1前完整15m close回到OR内即退出 | 使用当前Profile的等号边界 |
| Runner | 当前rolling extreme + ATR规则 |15m、lookback4、ATR14、buffer0.50 |
| TimeStop | ABSOLUTE，96根15m实际持有bars | 约24h，不变成96h |
| Session expiry | TP1前执行现有Session guard | 当前日结束；TP1后按Runner/absolute规则 |
| Break-even与费用 | 冻结Profile原规则 | 不因入场周期改变 |

实现不可使用 `_legacy_source_exit_policy(contract)` 推断新退出周期。Lifecycle只从Ticket
冻结的Profile取15m数据，时间止损依真实成交起点及现有bar计数。UI应显示“1h入场 / 15m退出”。
选择母池的96根数据与TimeStop96根是两种含义，不能共用窗口或watermark。

来源：[ExitProfile](../../../src/trading_kernel/domain/exit_policy.py)；
[Lifecycle数据请求](../../../src/trading_kernel/interfaces/lifecycle_worker.py)；
[adapter持有bars](../../../src/trading_kernel/infrastructure/venue_adapter.py)。

## 6. 动态选币复用

### 6.1 纯计算共用边界

建议提取冻结 `OpeningRangeSelectionFeatures` 与排序结果，输入仅包含规范化15m窗口、
候选identity和资格事实，输出特征、资格reason、stable rank与selected状态。

1. 保留原96根、前置close、14个true range、最后4根OR、24h quote volume及20M活跃门槛。
2. 排序保持 `OR.width / pre_OR_ATR14` 升序、quote volume降序、instrument identity升序；
   保留Decimal38/ROUND_HALF_EVEN，禁止float。
3. Ready1..7全选；Ready>7取前7；near最多7。Ready0为 **VALID_EMPTY**，不自动补位或fallback。
4. 任一候选缺K线或完整性错误是whole-attempt SOURCE_FAILED，不能降级为普通资格不合格。
   来源临时不可用与确定性计算失败分别记录，不无限重试，不跨输入cutoff续写结果。
5. 旧 `run_sor_dynamic_selection_v0` 保留旧typed输入、旧Spec校验、旧输出字段/摘要，内部调用
   共用数值函数；新调用在自身输入校验后生成自己的Snapshot/Member identities。
6. 新旧**相同输入得到相同数值特征、rank和members，但不是相同Snapshot ID或摘要**。
   算法核心数值契约与新策略完整语义digest分别持有。

既有抓取、规范化、资格与source integrity校验继续复用。两个strategy不共享可变authority，
也不通过读旧SOR当天的交易Snapshot偷渡新资格。

### 6.2 数据模型与流程复用

采用新冻结 `OrbSessionSelectionSpecV1` 和 `OrbSessionPeriodV1`，明确双Event、每日cadence、
输入15m、entry1h与first close。不是把Generic Spec rank/retain限制随意放宽。
在已有ports、Job lease、Snapshot/decisions、Generation、Universe、Vacuum、Authority、
Audit和suppression表上扩展typed处理；一个协调入口按**已安装Spec kind**精确分派。

现有 `EventUniverseSet / AuthorityEventBinding` 表达两个真实Event。新proof显式携带
契约schema/Spec identity，旧proof原字段与旧摘要不改写；数据库按安装kind验证新proof。
禁止通过epoch是否等于`sor-v0`猜算法类型，所有现有二选一分支必须审计。

## 7. 首次启动与每日状态机

### 7.1 首次启动无固定池

新策略安装后没有合法历史成员来源。**不复制旧SOR Universe、不安装Static7、不造空
Universe占位。**Initial basis是新双Event显式 **EMPTY binding**，universe_version_id为空。
这是“尚无交易grant”，不是一个READY=0 Selection结果。

1. 安装Strategy Control=paused，Selection Control=disabled；不创建交易授权或伪造TOTP。
2. Owner正式选择Dynamic并启用新策略后，持久化epoch、original authorization及最早每日
   activation Session。失败、超时或错过首日不会使这项长期意图自动过期。
3. 当日Job使用真实24币输入；第一非空Snapshot产生Generation，previous basis为双EMPTY。
   两边全部STAGED、认证与审计通过后才提交首个ACTIVE_NEW；控制版本CAS同时切换。
4. 首次VALID_EMPTY发布双EMPTY Authority，保留Dynamic意图，次日重新计算；不存在
   “fallback previous”可交易集合。首次物化失败也不借旧策略产生fallback权限。
5. 全球Entry恢复检查需要识别**已安装但明确paused/disabled且双EMPTY的bootstrap状态**。
   精确证明无scope、无交易Authority、无signal、无Reservation/Command且未成为可入场Event；
   不能对已有active、Owner-enabled或来源不明的Event忽略Universe认证。
6. 新策略启用后，缺失Universe/认证继续在该策略Admission处fail-closed；Entry promoter
   只处理现有操作Fence，不为新策略创建Policy范围、Selection grant或Owner授权。

这需要扩展Generation previous-baseline与source guard的显式EMPTY表示；不使用另一策略
的UID填满当前非空previous_long/short字段。既有历史SOR的真实pair字段保持不变。

### 7.2 正常切换与连续性

| 阶段 | 可以做什么 | 不可以做什么 |
| --- | --- | --- |
| 01:00 Selection | 提交只读市场结果 | 创建Ticket、自动grant或假定成功 |
| PENDING / DESIRED | 等当前slot和来源前置条件 | 提前占位、阻断其他策略、延长deadline |
| DRAINING_ENTRY | Vacuum与durable取消unfinished ENTRY | 直接取消venue、改已成交Ticket |
| MATERIALIZING | 沿用全局single warming slot，双边串行 | 两方向独立抢slot或半切换 |
| STAGED | 持续只读认证，两边等待atomic grant | 正式Signal、停止认证刷新 |
| ACTIVE_NEW / NO_CHANGE | 当前Session、小时close资格内交易 | 覆盖旧Ticket的membership或退出绑定 |
| FALLBACK_PREVIOUS | 恢复真实previous pair且有显式proof | 恢复固定池、抹掉失败、放宽Owner Pause |
| VALID_EMPTY | 前向阻止该Period新ENTRY，已有Ticket继续 | 用previous members补位 |

已运行Dynamic的每日边界独立建立PRE_FENCE_CONTINUITY；只延续exact previous members，
不继承昨日OR、Signal或当日交易资格。等待Selector、source failure与DESIRED本身不开Vacuum。
同members且current pair合法，使用NO_CHANGE；变化才fence/drain/serial warm/atomic switch。
01:00–02:00准备窗口内没有合法小时入场close，但仍要处理旧unfinished ENTRY的durable结果。

新小时策略采用**strict-next-hour grant**：正常commit在02:00之前，first=02:00；若在
02:00或之后提交，first为strictly future整小时。秒级延迟也不追认刚过去cross。这继承SOR
Session审计语义，不使用Generic当前close可消费proof。前一Version不存在的假continuity
不可作为证据。超过原物化30分钟必须进入正式失败/恢复，不能顺延deadline。

### 7.3 缺口审计与触发抑制

1. 从当日02:00起、grant first close之前，若存在未授权close，需要完整Gap Audit。
   采用相同新1h Detector重放每根完整小时数据，不读取15m cross作为小时策略触发。
2. activation/fallback审计 `previous members ∪ desired members` 的两Event；late continuity/
   late NO_CHANGE审计将获权的实际current pair。首次EMPTY previous只审计desired。
3. 每Event/币/Session若任何未授权小时出现cross，记录positive suppression；否则记录
   checked-negative。两者与Authority原子提交。晚些时候的第二次cross不能补回第一次机会。
   已有连续Authority合法消费的close属于正式覆盖，不重复消费或制造新Signal；目标新增
   成员没有该覆盖时仍须审计。positive suppression按新Event的整个Session持有，members
   离开再进入、NO_CHANGE、fallback或新authority sequence均不能清除它。
4. 截至commit重验Audit覆盖、source digest、Owner/control版本、两边pair、cert与wall clock。
   跨过规划first close则回滚、扩展audit、重新计算future first；不提前伪造审计。
5. **不使用CPM/MPG/MI/BRF2的NOT_TRIGGERED→ARMED rising-edge恢复门槛。**新策略为每日
   session-reference，恢复依据是Session path审计与一次机会的suppression。两类proof必须
   精确分开，不能共用一个返回true的宽松恢复函数。
6. 日内无任何未来合格close时，明确NO_ELIGIBLE_CLOSE_BEFORE_SESSION_END，待次日；
   23:00之后commit不能授权24:00入场。数据缺口保持失败，禁止推断negative。

来源：[原SOR Gap Audit](../../../src/trading_kernel/interfaces/authority_gap_audit_source.py)；
[旧Session设计](2026-08-20-sor-dynamic-instrument-selection-trading-v0-design.md)；
[Generic与SOR时钟区别](2026-09-06-generic-multi-strategy-dynamic-selection-v1-design.md)。

### 7.4 失败、暂停与来源寿命

| 情形 | 持久化结果 | 后续行为 |
| --- | --- | --- |
| 源/计算失败 | SOURCE_FAILED / COMPUTE_FAILED | 当前合法continuity独立运行；首次无previous则无新ENTRY |
| 切换后warming/认证/timeout失败 | terminal Generation与failure reason | 仅真实previous存在、cert有效、已drain、审计完成且Owner允许时fallback |
| 未知ENTRY/取消结果 | 现有unknown command/Incident | 外部readonly确认前不重发，不发新grant |
| Vacuum竞态partial fill | 原vacuum归因事实与durable保护/退出 | 沿用已认证TP1+Runner两腿或controlled-flatten；不新增runner-only |
| Owner Pause | paused control、Vacuum/cleanup历史 | 最高优先级，不fallback、不新激活；已有Ticket继续保护 |
| Resume | 新正式Owner版本与proof | Session审计重做，不能复活旧grant |
| lease到期/重启 | exact Job/Generation lease epoch | 从PG current恢复，原first/deadline不改 |

**成员年龄与当前Authority有效期分别记录。**设计默认最多容忍一次未完成每日Selection：
previous source最多覆盖源Session及紧接的一个日Session；连续第二次miss暂停新ENTRY。
成功Snapshot仅计算完成并不重置实际current members的来源年龄；切换失败恢复也不重置。
VALID_EMPTY覆盖当前有效Period，不能因旧成员尚在年龄预算内继续交易。

这个**一次miss寿命是新策略的设计默认值**，不是宣称旧SOR已有同样限制。状态与DB proof
必须冻结，禁止每次CONTINUITY更新expiry而无限续旧members。首次原Owner意图可长期保留，
但每日Snapshot、成员来源与交易grant不能长期保留。

## 8. 数据、事务与运行所有权

### 8.1 数据所有权

| 对象 | 唯一owner | 新增/扩展 |
| --- | --- | --- |
| Detector与Spec语义 | 版本化Registry、冻结代码契约 | 新Event与orb_session_dynamic_v1 payload |
| Owner允许范围与控制 | PostgreSQL Policy/Control/Authorization | 新策略范围、paused bootstrap、持续epoch |
| Selection输入证据与结果 | Job/Attempt/Snapshot/Member事实 | 新identity与kind，不双写旧Snapshot |
| current成员与grant | Universe current / Authority current | 双Event atomic set、EMPTY初始来源 |
| missed-close证据 | Gap Audit与suppression | 小时Session proof，已有表扩展kind guard |
| Ticket与交易结果 | 现有Ticket/Command/Aggregate/Event/Review | 只增加新冻结Event/binding来源 |
| 文档及UI | 显示与解释 | 不参与运行决策 |

可增加**一张不可变新Spec payload表**，使用 existing selection_spec_id FK；不得另建
Job、Snapshot、authority current、order或Ticket链。proof schema字段和规范序列化严格
校验；缺字段、错误kind、旧epoch、跨策略或跨方向证明均拒绝。

### 8.2 事务边界与锁

1. Job领取/lease提交 → PG事务外抓市场数据 → 短事务CAS提交唯一Attempt/Snapshot。
2. DESIRED持有exact控制与来源事实，检查可行动条件后进入single slot；无效队首不阻塞
   eligible队列，继续保留各策略lease与single-slot数据库锁。
3. Vacuum创建与停止新ENTRY提交原子；每次venue写先持久化exact Exchange Command，
   I/O后单独事务记录。unknown不盲重发。
4. 两边STAGED后，在一个事务内：锁双current pointers/控制/Generation → 重验新fresh cert、
   Audit与clock → retire旧pair、activate新pair → Authority/current及控制版本 → resolve
   Vacuum → append事件。任一步失败全部rollback。
5. Instrument按canonical instrument顺序先锁，Certification按profile/instrument顺序后锁；
   认证Writer采用同序。STAGED继续刷新readonly cert，不能把过期当成无需重验。
6. Generation不承诺未来必然有可用close；timeout与source/session expiry均使用最初事实。
   锁顺序应在所有新增共用入口一致，不以捕获deadlock并无限重试代替。

### 8.3 常驻运行与有界成本

| Worker | 新增责任 | 工作上界 |
| --- | --- | --- |
| Observation | 每日Selector、Coordinator、小时Detector/事实 | 一Job/epoch/日；24×96输入；每币每天最多24小时bars |
| Entry | 新Event通过既有Admission并串行发Ticket | 原single-lane、Policy与Netting Domain约束 |
| Lifecycle | 新Ticket的15m Profile与保护 | 原Ticket cadence，无新daemon |
| Reconciliation | staged cert、unknown、保护与结算 | 原有bounded claim与exact identities |

复用现有网络并发上限；Gap每日最多24根/币、union最多14币×2Event，可按币共用一次只读
path抓取。无需为两个方向重复下载同一窗口。正常idle零JSON/Markdown，日志只显示reason与
必要身份，不包含credential。生产不会读取本设计或本地缓存作为授权。

## 9. 接入点与删除范围

| 文件/模块 | 必要改动 | 禁止的捷径 |
| --- | --- | --- |
| `domain/instrument_selection.py`及新纯计算模块 | 提取数值计算，新独立Spec/结果组装 | 修改旧冻结Spec或Golden摘要 |
| `domain/detectors/sor_1h.py`（建议）与Registry | 新小时Event、facts与factory路由 | 全局把15m常量改1h |
| `application/observe_strategy_scope.py` | 小时当日path、warm vs active、session边界 | 用warm数据发Signal |
| `domain/selection_authority.py` | 双Event每日契约、proof、EMPTY basis、epoch | 把unknown family当作Generic或old SOR |
| `run_instrument_selection.py` / `selection_runtime_worker.py` | kind精确分派、新daily Job | 从旧SOR grant读新strategy资格 |
| `coordinate_selection_materialization.py` | 共用exact pair流程、first start、小时audit | 新并行物化程序或半切换 |
| `pg_*selection*` / `pg_universe_repository.py` | bounded selectors、atomic commit及cert | 直接SQL修数据、schema fallback |
| `authority_gap_audit_source.py` | contract取1h、Session path、suppression | 复用15m missed-cross结果 |
| `owner_control.py`与Owner Console | 新身份允许列表、Dynamic意图、真实时钟显示 | Seed自动resume或恢复旧SOR |
| `runtime_authority_seed.py` / entry readiness | 新策略paused/bootstrap及scope核验 | 所有新增策略默认enabled |
| ExitBinding、release/schema verifier与migrations | 独立binding、forward identity与preservation | 复制Profile或重写历史Ticket |

删除/替换仅限活跃共用入口中无依据的old-SOR常量绑定与epoch二选一推断。保留旧算法
Golden、历史策略/Spec/Profile/terminal lineage及旧方向规则；不清理与本次无关的代码。
如果shadow path尚不支持新小时Session事实，应明确显示unsupported/data unavailable，
不能冒用旧15m path或伪造Review；它不作为新ENTRY前置解锁流程。

## 10. 前向迁移与上线边界

### 10.1 迁移范围

**需要R4前向迁移。**新增Registry/Selection语义、DB constraints与proof改变了运行权威，
不是仅R3 Detector发布。建议下一可用revision名称 `orb_session_1h_v1`，序号在实现时依据
实际唯一迁移head确定，不在设计中抢占编号。

迁移/正式安装需包含：

1. 新Registry、facts、Product Compatibility、Event-to-profile映射及双ExitBindings。
2. 新immutable Spec payload，允许精确kind、双Event、daily/epoch；同一行只匹配一个payload。
3. Snapshot/decision/source/job、Generation、Authority、Audit proof的family-specific guards；
   明确EMPTY来源、首日preparing窗口、小时eligibility、Session截止与source寿命。
4. 改造默认`sor-v0`分支只服务旧身份；新身份必须显式epoch。新proof不能穿过旧/Generic
   放宽的constraint OR分支；必须有安装kind与proof交叉验证的DB trigger。
5. 角色最小grants、immutable保护、readiness与schema allowlist同步。
6. 新策略初始paused、Selection disabled；迁移不造Signal/Ticket/grant，不自动授予策略交易。

### 10.2 切换与恢复

停止Owner API及四Writer，Entry Fence，刷新PG/exchange flat、无未知指令/Incident、无
未完成warming/Generation/Vacuum/Job lease，取得来源preservation manifest，再执行forward
migration与正式identity切换。保留现有策略控制、原Dynamic intents、Profile与terminal lineage。

新范围/控制通过实际Owner授权写入。若R4流程生成了新的暂停Policy版本，旧Resume不能
冒充新版本Owner proof；只使用官方Console Resume/TOTP与正式promoter。**本次写设计文档
不要求Owner现在操作这些授权**。

新策略安装与启用分开记录：已有四家族的运行恢复不等于新策略激活。若flat条件不满足，
先报告实际敞口与必要条件，不自动要求或派发flatten。

不执行down migration，不回退旧schema，跨schema故障保持Fence并fix-forward。功能问题
可暂停新策略而保持已有Ticket保护；未知identity结果时所有可能旧/新Writer保持停写，
直到正式读证据确认。不得用旧SOR作为临时兜底策略。

来源：[部署合同](../../current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md)；
[运行模型](../../current/OWNER_RUNTIME_OPERATING_MODEL.md)；[AGENTS](../../../AGENTS.md)。

## 11. 必要验证与交付验收

### 11.1 定向RED/GREEN

| 测试边界 | 最小证据 | 捕获的实际风险 |
| --- | --- | --- |
| 共用数值核心 | 原Golden unchanged；新旧同输入features/rank/members一致 | 数值/排序/并列漂移 |
| 小时Detector |02:00首次、等号cross、多空、midnight、残缺/未完成bars | 提前或错Session入场 |
| 01:00准备 | 单根真实OR可warm/stage；无Signal、无Session消费；02:00用新事实 | 等首个cross导致必然timeout |
| 混合时钟 | 新Signal1h，但Lifecycle请求15m，Profile/96bars保持 | 退出时间被放大 |
| 首日无成员 | EMPTY→真实双staged→ACTIVE_NEW；失败/EMPTY无伪fallback | 偷渡Static7或旧授权 |
| atomic pair | 一边失败另一边不切换；cert到期再刷新 | 半切换与CERTIFICATION_STALE |
| 延迟/重启 | 跨02:00、30min超时、跨first close、23:00后无未来close | 追认突破或延长deadline |
| Gap Audit | 小时positive suppression / negative；union与current范围 | second-cross补票、漏审 |
| 控制/寿命 | 一次Owner意图跨首日失败；Pause优先；连续miss预算 | 授权次日丢失或旧成员无限续期 |
| 交易边界 | Session单Ticket、全局串行、domain占用、unknown/partial | 复制交易通道或弱化保护 |
| forward迁移 | 真实来源preservation、角色约束、old SOR保持disabled | 历史损坏或旧策略复活 |

共用成熟执行链的用例只覆盖新增接入边界，不为每个新名称复制整套保护测试。必要PG
并发测试覆盖slot与锁顺序；不增加无关soak、经济回测或调参。

### 11.2 冻结版本发布与生产证据

1. 冻结exact候选后执行正式R4认证及实际变更所需R2检查，不在每个小编辑后跑全套。
2. 正式停止/flat/preservation/身份切换与postflight，Owner控制保持精确声明。
3. 新策略实际Job→Snapshot→双current Universe→Authority→首次允许close有PG证据。
4. 下一个正常日、失败/EMPTY/晚接管的可重复路径由本地production-shaped用例证明；
   不以生产当天刚好没有数据异常推断所有恢复正确。
5. 自然触发的Signal、Ticket及保护/终态证据单独报告；测试fake、Snapshot成功、DESIRED
   和Worker active不能替代实际激活或交易验收。没有自然交易时不强制下单。

## 12. 设计状态与决策边界

**工程方案已经明确，可据此编写实施任务。**本文完成架构边界设计，代码、迁移、正式
认证及生产启用尚未执行。实现可调整函数名与模块拆分，但不能隐含改变上述行为。

仅以下属于产品行为默认假设：**退出维持现有15m Profile、每日单Episode、多空支持、
strict-next-hour晚接管、成员最多一次daily miss**。特别是新的成员寿命预算需在实施冻结
时显式列明；不能说“复用旧逻辑”而隐藏这个新增限制。工程实现、DB字段、锁序、Golden
和迁移方案不转交Owner选择。

本设计不把盈利证据作为额外开发审批门槛，不扩大已有资金边界，也不把本次设计请求
视为新策略的实盘启用授权。
