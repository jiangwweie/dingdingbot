---
title: SOR-1H Dynamic Engineering Design
status: REVISED_READY_FOR_IMPLEMENTATION_PLAN
created: 2026-10-13
reviewed: 2026-10-13
scope: Independent hourly SOR with inherited daily Dynamic and Static recovery contracts
---

# SOR-1H 多空动态选币设计

## 1. 目标、边界与设计决策

**新增独立 SOR-1H 多空策略，复用旧15m SOR的动态选币与每日恢复合同，只将入场确认
改为完整小时收盘，退出保持原15m Profile。**单人使用、中低频，允许空仓等待，不追求
SaaS高可用、边界毫秒级接管或每个周期都产生交易。

**本次交付是修订设计与执行文档，不执行代码、数据库、服务或新策略实盘变更。**此前
Dynamic修复部署的授权不被复制为新增策略启用权限；未来各阶段按实际Owner任务授权。

### 1.1 本轮收敛合同

| 项目 | 本版决定 | 来源/性质 |
| --- | --- | --- |
| 多空 | LONG和SHORT独立Event、Universe、Episode、退出绑定 | 复用旧SOR多空合同，Owner明确追问并要求考虑 |
| 选币 | 原24币母池、96根15m输入、每天UTC01:00计算、最多7币 | Owner要求复用已成功算法，不改alpha |
| 主运行模式 | Dynamic为主，Static用于首次切换前及失败恢复 | 不先交付固定池主版本；保留合法基线 |
| Static基线 | BTC/ETH/BNB/SOL/XRP/DOGE/ADA，双方向相同成员 | 工程默认沿用原七币；新策略独立安装/认证/授权 |
| 开盘区间 | 当日UTC00:00–01:00 | 原SOR一小时区间不变 |
| 入场 | 完整1h收盘cross，最早UTC02:00 | 本次明确行为变更 |
| 退出 | Initial Stop、TP1、Reclaim、Runner、ATR、TimeStop原规则 | Owner已明确保持原退出规则 |
| 迟到 | 可在合法未来小时接管，不设02:00全天停交易 | 适配旧strict-next-close与Session审计 |
| 授权 | 首次Dynamic原epoch/授权持续，失败后后续日自动尝试 | Owner已明确；不保留旧SOR首次Session失效限制 |
| 人工处理 | 普通失败自动恢复/等待；只报告明确事故或必须Owner操作 | Owner已明确，不要求每天Resume |
| 成员延续 | Dynamic已运行时按原合同延续/恢复真实previous members | 不一律回固定Static；不新增48h/一次miss限制 |
| 容量 | 原global、Family、strategy-side、止损/保证金边界 | 不扩容，不开第二资金池 |

来源：[原需求对话](codex://threads/01a1341c-4275-75b3-b806-99a9e0f96fe0)与本对话后续确认；
[旧SOR冻结决策](2026-08-20-sor-dynamic-instrument-selection-trading-v0-design.md)；
[原七币安装清单](../../../src/trading_kernel/application/strategy_universe_batch_manifest.py)。

### 1.2 覆盖此前草案

**删除Dynamic-only、首次无Static来源、强制02:00截止、禁止昨日成员、额外48h寿命、
强制singleflight/LRU/executor与跨全部Selector并发改造。**这些不是旧SOR合同，也不是
本次核心需求。只对新增策略做有界接入，明确保留有代价的合法空仓等待。

不包含新选币因子、小时退出、盈利审批流程、参数搜索、long soak、强制交易、恢复旧SOR。
旧SOR数值Golden与terminal历史保留；它当前退役，不因复用算法恢复交易。

## 2. 已知事实与复用分析

### 2.1 已知代码与历史证据

| 事实 | 设计影响 | 来源 |
| --- | --- | --- |
| 旧Selector输入96根15m、OR4、pre-OR ATR14、quote volume，Decimal38 | 共用纯计算，新策略自己的结果身份 | domain/instrument_selection.py |
| 旧Spec、Session timing、Audit绑定SOR-001/v4及15m | 解除精确绑定，增加小时typed contract | domain/selection_authority.py、interfaces/authority_gap_audit_source.py |
| 旧双边串行warming、atomic pair与previous fallback已实现 | 复用现有协调链，不复制另一套状态机 | application/coordinate_selection_materialization.py |
| Session Episode依Event/币/方向/Session确定 | 同日重复cross不创建第二Ticket | application/produce_strategy_signal.py |
| Lifecycle由冻结Profile.runner.timeframe读取数据 | 可以1h入场、15m退出 | interfaces/lifecycle_worker.py |
| 0008已有Event baseline/binding的ACTIVE/EMPTY形状；旧pair列已移除 | 用真实Event引用，不重建旧列/表 | migrations/trading_kernel/versions/0008_generic_dynamic_selection_v1.py |
| 0010保留Generic首次原授权跨周期 | 新SOR-1H采用持久意图原则，但独立日Session proof | migrations/trading_kernel/versions/0010_dynamic_intent_v1.py |

**历史成功证据：**2026-10-13的服务器只读核对，旧SOR在2026-09-07至09-21 UTC有15个
ACTIVE_NEW Authority、15个ACTIVE Generation，每个均有双边Universe激活记录；41张
Dynamic授权出生的终态Ticket均有EntryFilled及有效Review。该证据证明历史工程链成功，
不证明新1h策略已实现，也不自动授予其权限。数据来源为生产PG的Authority、Generation、
Universe、Ticket、Trade Event及Aggregate关联查询；不以当前selection_mode代替历史成功。

当前生产身份、Schema、四Generic实际状态以[MAIN_CONTROL_ROADMAP](../../current/MAIN_CONTROL_ROADMAP.md)
和执行时实时PG/systemd/exchange为准。本设计不复制volatile生产版本。

### 2.2 选择的架构

**共用纯计算、现有Selection/Materialization/Authority持久化及交易Kernel，独立持有新策略
身份与小时proof。**不改旧SOR周期，不复制完整Selector/物化/订单链，不套用CPM等新评分。

```text
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
```

来源：[Kernel设计](../../current/P0_TRADING_KERNEL_REBUILD_DESIGN.md)；[AGENTS](../../../AGENTS.md)。

## 3. 身份、多空与成员权威

### 3.1 新身份

以下是**拟新增身份**，不是已经安装的Registry记录。

| 对象 | 新设计身份 | 含义 |
| --- | --- | --- |
| StrategyGroup | SOR-1H-001 | 独立Crypto小时ORB |
| StrategyVersion | sgv:SOR-1H-001:v1 | 小时入场、原选币、15m退出 |
| LONG Event | event_spec:SOR-1H-001:SOR-1H-LONG:v1 | 上穿OR高点 |
| SHORT Event | event_spec:SOR-1H-001:SOR-1H-SHORT:v1 | 下穿OR低点 |
| SelectionSpec | SOR_1H_OR_ATR_DYNAMIC_V1 | 每日24选最多7，双Event |
| Selection kind | orb_session_dynamic_v1 | 有epoch的每日Session多空合同 |
| Exposure Family | opening_range | 现有Family预算 |
| Episode | session_reference | Event+币+方向+UTC日 |

1. 两方向共用一次Selection，分别持有Universe/Signal/Episode及相应ExitBinding；一Generation
   串行准备两边，全部STAGED后一次性激活。任一侧失败不能半切换。
2. 同币多空是独立Netting Domain，可并存，但仍受Policy限制；同币同方向与其他策略占用
   冲突仍拒绝，不能按StrategyGroup另开domain。
3. 新LONG/SHORT各自绑定现有同方向Crypto ORB15m Profile，不复制Profile内容。Ticket
   冻结实际binding、profile、Universe和birth Authority，掉出名单不主动平仓。
4. Static基线名单是新策略的PG事实；不能把旧SOR Universe ID、授权、Spec、Snapshot或
   epoch绑定给新策略。Dynamic与Static不是两条交易执行链。
5. 新Registry/catalog、Owner scope映射、capability及Seed digest必须在正式R4安装事务
   同步，保留既有四家族控制/身份/历史。不把新策略权限隐含加入旧Policy。

### 3.2 新旧SOR必要隔离

**旧SOR-001/v4的历史与退役状态不变；新SOR-1H-001/v1不存在旧身份别名。**隔离不要求
第二数据库、服务、资金池或订单链，要求每个事实与控制有准确identity。

| 边界 | 新策略必须持有/显示 | 必要负例 |
| --- | --- | --- |
| Registry/Detector/Fact | 新group/version、双1h Event、自己的Fact IDs | 旧15m Event/Fact不被新Detector或Signal接受 |
| Job/Snapshot/Generation/Universe | 新Spec/kind/epoch与双Event FK | 旧Snapshot/UID即使同成员也不能成为新source/grant |
| Owner Policy/Control/Authorization | 新group/Spec/Event scope和purpose/version | 新Resume不改变旧SOR paused/retired；旧TOTP不可消费到新group |
| Authority/Audit/suppression | 新Event、小时Session proof与typed schema | 旧15m审计/first close/抑制记录不提供新1h资格 |
| Ticket/Command/Review | exact新Event与冻结profile/binding来源 | 同币方向也不能把旧Ticket历史重标为新策略 |
| API/页面/日志/统计 | SOR-1H（1h入场/15m退出）；旧SOR（15m，已退役） | 不按SOR前缀合并、别名重定向、混合P&L或隐藏退出周期 |

共用只有无策略authority的纯features/ranking与同方向immutable ExitProfile；新Event各自
创建binding。读取与查询用exact group/version/Event/Spec/epoch；禁止startswith('SOR')
做授权、profile或统计路由。同account/instrument/side的Netting Domain仍按既有全局规则
共享占用，不能为了隔离身份绕过冲突或给新策略额外预算。

## 4. 时钟、输入与入场

令D为UTC当日00:00，H=3,600,000ms。入场/审计K线用exclusive close boundary；
Binance end-minus-1ms在adapter归一化，不能混入proof。退出保持既有协议与watermark。

| 对象/字段 | 精确边界 | 行为 |
| --- | --- | --- |
| Session / period_anchor_ms | D | Job唯一键Spec+epoch+D；Owner earliest按日对齐 |
| feature_cutoff / decision | D+H | 96根15m窗口为[D-23H,D+H) |
| OR | [D,D+H) | 当日第一根完整1h |
| prepare | Snapshot提交后，最早D+H | 准备不等于交易 |
| first eligible close | 最早D+2H；新/恢复grant取严格未来整小时 | 不追认已过去cross |
| 新ENTRY交易窗口 | close及action time均在当日合法区间，close<D+24H | 最晚23:00触发；Signal不跨午夜 |
| Selection源期 | 至D+25H | 下一日01:00后不能用过期Snapshot新建Desired |
| 当日交易Authority | expires_at=D+24H | 次日重建Session授权，不沿用昨日OR |
| materialization timeout | 原fence+1800s | 排队不启动timeout；重试/重启/retarget不重置 |
| 退出数据 | 完整15m与原保护 cadence | 不改成1h、4h或96小时 |

### 4.0 为什么最终选币不能提前到00:00

**01:00是原算法数据完整的最早时点，不是任意挑选的定时。**排序核心需要当日
00:00–01:00的OR.width/pre-OR ATR14；96根输入最后4根正是该小时。00:00时ATR与历史
部分已知，当日OR与截至01:00的24h quote volume尚不完整，不能提交同算法的最终排名。

| 可执行时点（UTC） | 已知数据/可提前的工作 | 禁止产生的结果 |
| --- | --- | --- |
| 00:00及之前 | 客户端/连接准备、Static维护、历史窗口完整性及开盘前ATR所需数据准备 | 当日最终OR、selected set或假Snapshot |
| 00:00–01:00 | 可选预取已完成历史15m部分，待最后4根补齐 | 用未完成OR、上一日OR或临时排名授予交易 |
| 01:00之后 | 获取截至01:00的完整96根、重新核对来源与quote volume、提交Snapshot、物化 | 把prefetch当作authority或改cutoff |
| 02:00及之后 | 依真实Authority判断小时cross；迟到走future close/Audit | 追认未授权的过去突破 |

原窗口为[D-23H,D+H)：00:00前最多先准备92根历史15m，最后4根需等01:00。预取并非
首版强制新缓存框架；若采用，完整输入仍须按同cutoff重新校验，quote volume计算包含
最后4根，读取修订/重复/缺口不得被缓存掩盖。00:00认证事实到01:00可能已过期，持续
认证照原cadence刷新，activation与ENTRY仍重新验freshness。

把最终决策直接改00:00会改成前一小时OR、昨日OR或开盘前另一个选币指标，属于**算法
输入与策略语义变更**，不能再声称同输入复用原Golden。UTC00/01/02对应北京时间08/09/10。
来源：[原特征计算](../../../src/trading_kernel/domain/instrument_selection.py)，其klines[92:96]
为当日OR，78:92为开盘前ATR14输入。

新kind不能套Generic的cutoff=anchor或current-close授权规则。Snapshot有效期、历史成员
provenance及当日交易Authority是不同谓词。旧Snapshot可以在daily continuation中作为
成员来源历史引用，但过期trading grant、昨日OR/Signal绝不作为今日权限。

### 4.1 Detector与01:00准备

1. 线上使用官方完整1h序列，从当日D至trigger close连续对齐，不跨Session、不超过24根；
   缺失、乱序、重复、未来/未完成bars明确invalid。
2. LONG：previous.close<=OR.high且current.close>OR.high；SHORT：previous.close>=OR.low
   且current.close<OR.low。小时内刺穿无Signal。02:00之前和24:00边界不生成当日Signal。
3. **01:00单根OR可warm。**保持DetectorStatus.NOT_TRIGGERED、occurred=None，输出精确
   Registry全部Fact，时间资格/cross为false；不新增NOT_DUE Detector状态。
   warm-only/refresh只保存OR/保护参考与readiness，不生成Signal、不消费Session。
4. OR.low为多头Initial Stop，OR.high为多头Reclaim；空头反向。Detector不产生quantity/
   budget/Ticket。02:00重新读取真实市场事实，不能把01:00准备facts续期为触发facts。
5. Signal取Fact、Session与适用Authority最小expiry；Fact TTL从真实close开始。
   同日同币同方向一个Session Episode，终态Admission拒绝不重试，不因Universe或暂停
   变化造第二张Ticket。
6. NO_CHANGE继承已证明连续覆盖与原first，不因为latest ID变化误伤合法出生Signal。
   Vacuum/Pause/EMPTY切断后的旧Signal不能恢复；Entry复核exact birth/current lineage。

### 4.2 退出规则保持不变

| 项目 | 采用规则 | 生命周期来源 |
| --- | --- | --- |
| Initial Stop | OR另一侧，原保护与量化规则 | 成交后立刻走现有durable保护路径 |
| TP1 | 1R、50%、limit_gtc及现有两腿条件 | 冻结Profile |
| Reclaim | TP1前15m完整close回到OR内，原等号边界 | 冻结Reclaim reference |
| Runner | rolling extreme，15m lookback4，ATR14，buffer0.50 | 冻结Profile |
| TimeStop | ABSOLUTE 96根15m实际持有bars，约24h | 原成交起点/计数规则 |
| Session expiry | TP1前原Session guard；TP1后原Runner/absolute | 冻结Ticket deadline |
| Break-even与费用 | 原Profile参数 | 不因1h入场改变 |

不得用legacy exit policy根据contract.timeframe推导新规则；Lifecycle从Ticket Profile
取15m请求，不随Strategy timeframe变大。UI显示1h入场/15m退出，但无需前端重写。

来源：[ExitProfile](../../../src/trading_kernel/domain/exit_policy.py)；
[Lifecycle](../../../src/trading_kernel/interfaces/lifecycle_worker.py)。

## 5. Selector数值复用与真实交易来源

### 5.1 共用纯计算

保持原96×15m窗口、pre-OR ATR14、OR4、20M quote volume门槛；排序按OR.width/ATR14
升序、quote volume降序、instrument identity升序；Decimal38/ROUND_HALF_EVEN。
24候选必须有完整来源，一币缺K线是whole-attempt SOURCE_FAILED，不作为普通INELIGIBLE
被动补位。Ready1..7全选、>7取7、near最多7、Ready0发布VALID_EMPTY。

提取无策略identity依赖的features/rank纯函数；旧run_sor_dynamic_selection_v0调用共用核心
但保留旧输入校验、序列化和digest。新Spec生成自己的Job/Snapshot/Member IDs与摘要。
**同输入数值/排名/成员一致，不要求跨策略Snapshot身份或摘要相等。**Golden只verify，
不能重新生成artifact来掩盖差异。生产不读取研究fixtures/cache。

### 5.2 前一次成员与Static区别

| 来源 | 含义 | 自动使用条件 |
| --- | --- | --- |
| 原Static baseline | 初次Dynamic之前的新策略七币集合 | 新策略独立安装、warm/cert和当日Static grant有效 |
| previous-active set | 某次实际切换前的current集合 | 未被retire；当日Owner/认证/continuity或fallback proof成立 |
| 昨日Dynamic Snapshot | 选出previous集合的immutable来源 | 只提供成员provenance，不自动提供今日grant |
| frozen Static rollback baseline | Owner明确回Static的目标引用 | 需新的合法materialization、认证和授权，不复活retired UID |
| VALID_EMPTY | 成功计算但无成员 | 本Period不得拿Static或previous补位 |

**普通failed-switch恢复previous，不一律回Static。**首次切换的previous本来是Static，
所以首次失败可恢复Static；进入Dynamic后的previous通常是上一套Dynamic成员。

## 6. 首次安装、启用与持续意图

### 6.1 Static基线建立

1. 安装新Registry/Event/Product及同方向ExitBindings，新Strategy Control=paused；以新
   策略身份在PG冻结七币baseline与双Event引用，Selection Control=static_baseline。
   安装名单不是交易授权，不造Owner Resume/TOTP，不让新策略因seed默认enabled。
2. 复用正式bootstrap/Universe安装与readiness路径，建立新LONG/SHORT各自实际Universe、
   scope及current。暂停期间可执行**只读准备**；不得产生Signal/ENTRY。
   daily OR未形成时只是未ready，允许等待至01:00，不用昨日数据装作今日OR。
3. Static当日grant需新Owner scope/策略控制、真实当日OR、fresh cert和Session时钟；
   迟到首次enable/Resume按未来小时及Session Audit，不追认过去的突破。
4. 基线完成与新策略启用分别记录。新策略未曾安装current且paused只能在精确bootstrap
   状态下展示未ready，不为global promoter绕过现有Universe/identity要求。
5. 首次Dynamic Stage冻结真实pre-Dynamic双Static baseline，不复制旧SOR current，不
   以另一个策略的UID填充。既有Event baseline表表示ACTIVE/EMPTY，旧pair列不恢复。

七币采用沿用旧安装清单的工程默认值；若实际新scope或venue qualification有不一致，
实现显式报告，不能偷偷换币/扩池。除正式配置变更，baseline不可变。

### 6.2 一次Owner意图跨失败保留

正常起点static_baseline→pending dynamic，原authorization、epoch与earliest Session长期
保留。失败或错过第一日不清pending、不更epoch、不要求每日TOTP。首个ACTIVE_NEW/
NO_CHANGE/VALID_EMPTY在原子事务中消费exact原授权、更新mode并清pending；源Snapshot
仍须同epoch、current Session/版本/freshness与实际Owner控制匹配。

先静态运行不等于增加一张固定池主产品任务：基线是正式Dynamic切换的前置与恢复来源。
首次选币source failure保持Static合法运行；真正post-fence失败需恢复proof后才能重开
Static新ENTRY。已有Ticket无论Static/Dynamic都按自己的冻结Profile继续。

Selection支持static_baseline/dynamic_selection/disabled的既有操作；Owner手动回Static是
显式rollback，不与每日failure混淆。ordinary resume不改变长期Selection intent；Owner
明确取消/改变intent才撤销/更新epoch。global Resume及strategy_resume/selection mutation
保持现有TOTP与不同purpose目标边界，可聚合UI操作但不可伪造或借用授权。

## 7. 每日协调、晚接管与失败恢复

### 7.1 决策矩阵

| 场景 | 新ENTRY行为 | 记录与条件 |
| --- | --- | --- |
| 首次pending，source失败或尚在队列 | 原合法Static继续 | 不创建Dynamic成功、不提前Vacuum |
| 首次post-fence准备失败 | 恢复真实Static previous | drain/cert/Owner与小时Audit完成，FALLBACK_PREVIOUS；mode仍Static，intent保留 |
| 已Dynamic，source失败或新Desired排队 | 真实current继续 | PRE_FENCE_CONTINUITY独立于Selector结果；新日OR/cert/grant合法 |
| 已Dynamic，成员变化准备失败 | 恢复真实previous pair | FALLBACK_PREVIOUS；不自动返回固定七币 |
| members相同 | 连续NO_CHANGE | 不fence、不改已有Ticket，continuity与facts仍需证明 |
| Ready0 | 本Period无新ENTRY | drain后VALID_EMPTY；不补位、不fallback |
| previous无效/Owner暂停/drain未清/缺口数据不足 | 该策略等待 | first blocker与实际状态明确；已有Ticket保护不停 |
| 新due Snapshot到达 | 替代未生效旧Desired | SUPERSEDED、原Vacuum/fence/previous/durable drain保留 |

**不引入Generic一次miss/48h成员寿命规则。**旧SORdaily合同的source失败只追加原因，
并不自动切回Static或禁止上一套Dynamic成员。每个日Session重新证明Owner、cert、OR及
coverage；历史Snapshot年龄只读显示，continuity不伪造新Selection或改写源时间。
有效证据不足可以空仓等待，不为提高可用性放宽认证、资格、初始止损或未知结果处理。

### 7.2 准备与两边原子切换

从01:00以后领取due Job，commit Snapshot后建立PENDING/DESIRED。只有due合法来源、
控制版本、single warming slot与可行动前置满足才开启Vacuum。queue不抢占future slot，
等待不改变旧合法current；LONG/SHORT串行warming且只读，无Signal。

1800s原timeout从第一次fence开始；retarget、重启、lease retry不延长。warming/staged
证书持续刷新，过期行情readiness需受控warm-only更新，不能把STAGED改回warming或
开启observation/entry。完成两边后同事务：锁current/控制/Generation→重验cert、facts、
Audit、wall clock→切换两Universe+Authority+mode→resolve Vacuum→追加事件。
任一步失败全部rollback。实际切换前previous保留为恢复来源，成功后才retire。

01:00只有OR时可准备，01:30不是承诺完成时点。迟到不等于自动失败或放弃当日。

### 7.3 小时资格与Gap Audit

1. 01:00–02:00之间commit的新/恢复grant first=02:00；commit在02:00之后，first为
   严格未来整小时。**02:00是最早入场，不是全天准备截止。**已连续合法NO_CHANGE继承
   证明覆盖的first，不因sequence刷新作废合法birth Signal。
2. 不能套Generic当前未消费close可授权规则；Session审计使用新1h Detector。存在未授权
   eligible小时，则在grant前记录positive suppression或checked-negative。
3. activation/fallback审计previous∪desired、最多14币×2Event；late continuity/NO_CHANGE
   审计实际要获权的current pair。每币共享同份完整小时path，方向分别评价。
4. gap出现过首次cross则同Event/币/Session后续cross受抑制，不能补票；已有连续Authority
   合法处理的close属于正式覆盖，不重消费/重造Signal。补齐遗漏窗口不能推断negative。
5. Audit抓数据/重放在PG事务外；冻结scope/source版本→外部I/O→CAS提交proof；grant
   事务重验Owner、pair、cert/Fact freshness、scope/digest及commit时钟。跨过规划first则
   rollback、扩展Audit、顺延first，不保留一个已经过去的授权边界。
6. midnight后的新日有自己的OR与Session grant；昨日Signal不跨日。23:00之后提交新grant
   无当日未来close，记录等待下一Session，不授权24:00旧Session。
7. 不使用rising-edge NOT_TRIGGERED→ARMED恢复代替SOR Session审计；Static首次/恢复也
   必须有精确小时覆盖或审计，不因Static成员固定而跳过。

来源：[旧SOR恢复与审计](2026-08-20-sor-dynamic-instrument-selection-trading-v0-design.md)；
[既有审计入口](../../../src/trading_kernel/interfaces/authority_gap_audit_source.py)。

### 7.4 VALID_EMPTY、过期和supersession

成功VALID_EMPTY从fence/commit向后禁止本Period新ENTRY；之前合法出生/成交不被追溯
抹去，但尚未完成ENTRY按Vacuum durable drain处理，保护Ticket继续。下一Period不能从
dormant current偷偷恢复Static或previous：先保持EMPTY，直到合法新Selection重新获权。

物理current Universe可保留供历史/认证，**与当前交易grant区别表达**。从EMPTY到非空时
新Generation有明确非交易EMPTY basis与物理待替换pair；不能把不可交易旧pair当可fallback
来源。现有Event baseline的NULL/empty digest可复用；新kind数据库验证此差别。

首日有真实Static previous，因此ordinary首次失败沿正常Static recovery。真正previous
EMPTY/不合法时，保持FAILED_CLOSED负向Fence；禁止“无previous就直接删除Vacuum”。
新的due Snapshot可走正式supersession/retarget，保留原drain/unknown证据与fence时间，
在新的合法Audit及atomic active/empty结果后解决负向状态。无未来close则次日自动推进。
现有terminal FAILED_CLOSED仍blocks_new_entry，不能把terminal误认为无Fence。

terminal source/compute结果按其有限重试合同停当日Job；同epoch下一日创建新Job自动
重试。确定性完整性失败不无限重抓，transient读取可有限重试；物化timeout不能复活旧
Generation。同一Snapshot的物化Generation按唯一身份幂等；同一Ticket只能有一个ENTRY
command generation，但一个Snapshot可以为不同合法成员产生各自的Ticket。只有明确事故或hard gate需
人工处理时报告，普通失败由既有Coordinator/Reconciliation推进。

### 7.5 Static rollback与暂停

手动Static rollback从已冻结的新策略baseline成员/版本创建新的materialization，实际
cert/warm及小时Audit通过后atomic切换；不能把retired Static Universe直接翻回active。
不需要每天配置名单。Owner Pause/全局ENTRY暂停优先，不fallback/自动Resume；新
Daily Snapshot的只读计算可按既有合同继续，但不开启新交易grant。

unknown取消、ENTRY/保护结果由既有Reconciliation处理；不盲重发、不清prepared来补票。
Vacuum归因partial fill仍沿用原认证的两腿/保护规则；普通partial incident原规则不变。
本任务不修改Reducer、订单风险或退出算法来满足新策略测试。

## 8. 数据、事务与单人性能边界

### 8.1 单一权威

Registry定义策略；Owner Policy定义允许范围与资本；PG存Spec、Control、Job、Snapshot、
Generation/Event baseline、Universe current、Authority、Audit/suppression和交易事实；
exchange readonly核对外部真相。文档、研究缓存与报告均非运行授权。

用现有表、typed ports和协调入口，按**installed Spec kind**精确分派；新kind的不可变
payload可有一张必要Spec扩展表，不另建Job/Snapshot/Authority-current/Ticket链。
所有epoch=sor-v0或non-sor=Generic推断需替换成已冻结精确kind路由，但旧路径数据/
数值/历史proof保持原值。未知kind显式拒绝。

### 8.2 事务与锁

I/O在事务外。短事务持有exact identity/CAS lease epoch与控制版本；Instrument按
canonical instrument先锁、Certification按profile/instrument后锁。single warming slot
既有全局serialized gate保留，queue跳过不可行动head。双边activation/fallback与current
指针、Authority、模式、事件、Vacuum原子一致，故障响应丢失后exact-load而非重复提交。

STAGED行情更新走受控warm-only操作，expected Generation/scope version/lease/close
变化则discard；无Signal、无Session推进、scope权限不打开。cert refresh是独立既有路径。

### 8.3 必要性能范围

| 工作 | 规模/约束 | 首版实现 |
| --- | --- | --- |
| Daily Selector | 一Job/Spec/epoch/日；24×96=2304bars/attempt | 复用已有timeout、有限并发与source retry；不修改四Generic budgets |
| 正式Observation | 7币×2方向；每scope/latest-close一次PG消费 | 小时边界数据，可在同一工作批次复用path |
| Static/current事实准备 | 七币双边，01:00完整OR | 只在新close/过期时刷新，不因2s tick重复取数据 |
| late Audit | union最多14币×2Event，单path最多24根1h | 按币抓取，方向分别计算，有限lease/版本与重试 |
| Certification | 同profile/instrument复用证书，覆盖warming/staged/active | 原5min检查、10minTTL和overdue公平性 |
| 运行 | 原四常驻Worker、一个Observation engine、原slice约束 | 不新增daemon、进程池、engine或全局连接池扩容 |

1. **不预先重构全局limiter、singleflight/LRU或executor。**首先使用成熟请求路径、有限
   batch/concurrency及现有rate limit。共用同一批只读输入不代表共享跨策略交易Authority。
2. Job市场读取的最坏有界耗时必须小于lease有效期（含排队/提交余量）；若不能满足，
   使用既有exact claim/renew/CAS协议，而非把deadline加大。lease失效旧owner结果discard。
   不强制60s/20s heartbeat，也不把materialization30s lease当市场attempt预算。
3. Selector每日due/finite retry，terminal或未到boundary只进行低频current检查；Coordinator
   有drain/progression时沿用现有cadence，仅等新close/slot时延后next_due。允许错过边界
   后安全接管，不新增一分钟级策略调度，不减慢已有Ticket保护/对账。
4. 每次SQL基于exact keys/actionable indexes，pair14scope、union28Event上界；网络I/O不
   占PG连接，不history full scan。shared源epoch/purpose明确，unknown不能为了吞吐跳过。
5. 只做一轮必要的01:00混合due/late Audit短场景，检查请求计数、lease、loop响应及
   既有保护处理无回归。数值上界不是Tokyo CPU/RSS benchmark；实测确有问题才在本任务
   范围添加最小优化，并验证受影响旧family。不开long soak/压测/性能等待部署gate。
6. 不扩现有CPU100%、Memory1GiB、Tasks128边界。正常idle零JSON/Markdown，重复blocked
   日志限频；无新authority事实不重复append事件。不引入SaaS多租户/HA/分布式调度。

来源：[常驻宿主](../../../scripts/trading_kernel/run_observation_worker_once.py)；
[Job runner](../../../src/trading_kernel/application/run_instrument_selection.py)；
[资源合同](../../current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md)。

## 9. 接入与迁移

| 边界 | 必要接入 | 不变部分 |
| --- | --- | --- |
| Selector数值 | 纯核心、新Spec/结果身份 | 旧Golden与旧摘要 |
| Registry/Detector | 新双Event、facts、factory、hourly Session | 既有策略Detector与退出Profile |
| Observation | 01:00prepare、1hpath、Static/current/staged refresh | PG facts/Signal单链与cursor原则 |
| Authority/Vacuum | 新kind、持续epoch、小时coverage/Audit、Static recovery | old SOR/Generic各自合同 |
| PG | 新Spec payload、kind/proof/epoch/time guards、真实Static baseline | 既有normalized Event binding、terminal lineage |
| Runtime/Owner | daily双Event路由、Static/Dynamic controls、状态显示 | 四常驻Worker、TOTP purpose、资金限制 |
| Release | Registry/Policy scope/Seed、source preservation与verifier | stopped-flat-forward，无旧schema运行 |

**R4前向迁移必需。**新Registry/Spec、proof及Owner Event scope改变运行权威。revision序号
按实现时唯一head确定，建议名称orb_session_1h_v1。要扩展当前只支持较早source的正式
compatible_upgrade verifier/部署边界，认证本次真实source→target，不能套用不支持的flag。

迁移/安装：新kind payload恰好一项、exact24与双Event、rank/时间/epoch、Static基线/FK、
Authority active/empty及其父shape、immutable guard、role最小grant、catalog/binding/source
preservation一致。paused安装与真正策略enable分开，不造TOTP/grant/交易。

全局Entry恢复、readonly certifier、promoter必须共用exact当前Event/Universe依据；新增
paused未bootstrap状态明确未ready，生产按正式基线流程准备后再恢复，不要求为了可用性
跳过当前existing Universe认证。VALID_EMPTY保留物理current时仍认证实际成员，并由
Authority否决新ENTRY；不得把纯成功Snapshot视为已经ready。

需要停止API及四Writer、Entry Fence、fresh PG/exchange空仓且无残单/unknown/Incident/
活跃Reservation、无未完成Generation/warming/lease或未解决维护Vacuum，再取来源manifest。
完成迁移/identity/baseline准备、source preservation/target证明后，按实际新Policy版本进行
Owner Resume及新策略配置。此前Dynamic repair部署授权不替代新策略scope授权。
如果已有敞口，报告并保持保护，不自动flatten。失败保持Fence、fix-forward；不down
migration、双写或启动旧schema writer。当前生产事实只更新MAIN_CONTROL_ROADMAP。

来源：[部署合同](../../current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md)；
[Owner模型](../../current/OWNER_RUNTIME_OPERATING_MODEL.md)。

## 10. 必要验证与验收

| 边界 | 最小证据 | 首要错误 |
| --- | --- | --- |
| 数值复用 | 旧Golden不变；同输入新旧features/rank/members一致 | 算法漂移或重做Golden |
| 多空Detector |02:00/迟到/午夜、等号、invalid path，Live/Replay一致 | 方向反转、提前/跨日触发 |
| prepare与混合退出 |01:00全Fact可warm无Signal；Ticket lifecycle取15m | 30min必然timeout、退出放大 |
| Static→Dynamic首激活 | 独立Static双pair→新Snapshot→ACTIVE_NEW，原授权跨失败/次日 | 借旧SOR身份或意图失效 |
| 双边切换/STAGED | 一侧失败全组不切；cert及warming path过期后正确刷新 | 半切换/认证漂移 |
| source failure/continuity | 首次Static继续；已有Dynamic当前继续，非强制Static7 | 把失败当VALID_EMPTY/新激活 |
| post-fence fallback | 恢复exact actual previous，小时union Audit有效 | 不合法回Static/缺证明 |
| NO_CHANGE与birth | 连续coverage和合法birth Signal保留 | 每次latest ID都顺延/作废 |
| VALID_EMPTY/restart | 不补位、不追溯成交；new due supersession、旧Fence不得删 | dormant成员复活、永久队首 |
| lease/性能 | 有界网络+PG外I/O、旧owner弃结果，一轮混合due | stale CAS成功、改变旧family预算 |
| 迁移/Owner/安全 | preserved source、新双binding、paused seed、旧SORdisabled、资金不变 | 假TOTP、Scope泄漏、历史损坏 |

按test-first写最小RED后GREEN，相关PG/接口/完整链路回归；不为新名称复制所有成熟订单
测试。冻结exact候选后执行一次正式R4与所需R2/R1认证，不每小编辑重跑全套。
生产激活与自然交易验收分别记录；Snapshot/fixture/Worker active不能替代双Universe+
Authority成功，也不强制下单制造Ticket。真实终态需保护/退出、flat无残单、settlement/
有效Review和预算/domain释放证据。

## 11. 实施状态与执行文档

**修订设计已与本轮澄清一致，可按**[执行文档](../plans/2026-10-13-sor-1h-dynamic-implementation-plan.md)
**开始后续获授权的代码工作。**本次仅交付文档，任何Task没有实现PASS或生产启用PASS。
函数名、模块拆分、DB列与锁序由实施者负责，不转交Owner工程选择。

允许空仓等待不等于可以永久卡任务；普通故障必须有可审计的恢复/下一日推进。
Static七币是沿用原名单的工程默认，而非本次实际配置或交易授权；实装时以Owner scope
与可交易资格证据确定。性能只按必要证据优化，不增加盈利或长期soak审批。
