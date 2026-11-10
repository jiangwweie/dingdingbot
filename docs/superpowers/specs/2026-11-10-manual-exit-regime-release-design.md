# 首尔人工接管产品：MA50 与可配置 TP1／Runner 设计

## 1. 状态、来源与适配范围

**设计编号：MA-EXIT-REGIME-01；日期：2026-11-10（北京时间）。状态：按 Owner 本轮要求完成文档适配，待实现与独立认证；本轮不修改交易代码、不部署、不激活配置。**

基线为东京版 [TK-EXIT-REGIME-01 设计][A1]及[实施与上线方案][A2]。Owner要求把该方案适配到本人工接管工程，因此沿用其已明确的交易参数，目标改为**首尔 App 人工接管产品**。东京原文、代码、服务器、账户和授权保持各自边界；原东京实施授权不转化为首尔生产操作许可。本轮授权是写文档，未来实施与发布须结合本线程届时授权及行动时门禁，不重复询问已经确定的参数。

本版沿用原产品承诺：**默认 AUTO；确认有效外部干预后整笔永久 MANUAL；归属不明为 REVIEW_REQUIRED，不能等同于已确认人工接管。**新配置只调整未被接管时的自动策略。管理权、退出阶段、全局 ENTRY 和市场状态门槛分别持久化，互不冒充。（来源：[Owner决定][M1]、[运行模型][M2]。）

| 精确策略 | 方向 | 新 ENTRY 的 MA50 门槛 | TP1 价格基准／倍数 | 数量算法 |
|---|---|---|---|---|
| **CPM-RO-001** | LONG | BTC 完整闭合4h收盘严格大于 SMA50 | 实际完整入场 **1R** | 目标 **5%**；不足提升至最小可执行量，实际最高 **50%** |
| **MI-001** | LONG | 同上 | 实际完整入场 **1R** | 同上 |
| **MPG-001** | LONG | 同上 | 实际完整入场 **1R** | 同上；取代原数量合同仅限新绑定新票 |
| **BRF2-001** | SHORT | 不新增该门槛 | 实际完整入场 **1R** | 同上 |
| **SOR-1H-001** | LONG、SHORT | 不新增该门槛 | 实际完整入场 **1.2R** | 原绑定数量比例及原取整合同保持，不自动采用5%／最小量提升算法 |

**本版保留真实 TP1 订单与成交，不实施“无TP1／全仓虚拟盈利门槛”方案，不新增 ProfitThresholdReached 来替代真实成交。**所有 AUTO 交易须在冻结目标数量完整成交确认后才申请保本，保护替换确认后才可显示 Runner 已受保护。已确认 MANUAL 后即使原 TP1 自然成交也不恢复保本／Runner。旧 `SOR-001` 永久退休，SOR-US不属于本次范围。

本轮不改变 Detector、Selection 评分或币池，不新增资金池、杠杆、预算、加仓、重复 ENTRY、每日亏损熔断或人工操作评分。原来暂停的策略保持暂停；配置包包含该策略不代表恢复其交易权限。当前生产版本、控制选择、余额、仓位和验收状态只由[人工版路线图][M3]及行动时 PG／交易所证据维护，不复制为本文长期事实。

配套实施文档：[人工版实施、认证与首尔发布方案][P1]。本设计与配套计划共同构成人工版后续执行规格；原人工接管决定中“保留TP1／Runner”的承诺仍成立，变化是**未来新配置的真实TP1参数与可执行能力**。

## 2. 已知客观事实与待实现能力

### 2.1 本分支源码事实

| 边界 | 当前源码事实 | 本次必须补齐 |
|---|---|---|
| Profile／数量 | TP1正比例、不可变Profile/hash、数量向下取整；TP与Runner都校验最小量／金额 | 显式数量算法版本、目标比例、实际比例上限与最小可执行提升 |
| 入场定价 | Claim按入场参考价和止损距离计算TP | 完整成交后冻结实际VWAP和一票唯一的执行计划 |
| 部分TP | 非零且未满目标时仍抛出 `partial TP1 fill is outside the registered exit policy` | 精确累计成交、余仓投影及连续保护，满额后一次性保本转换 |
| 管理权 | AUTO／REVIEW_REQUIRED／MANUAL、不可逆接管与派发写门已存在 | 新计划、部分成交、保护替换及故障收敛都接入这些门禁 |
| 管理证据 | 已有耐久原始订单输入、规范证据、准确命令基线、连接覆盖和健康租约 | 支持新TP实际数量／新保护数量，不能用预期默认值或固定50%重建“自身订单” |
| 配置／界面 | 已有Owner身份、TOTP、Profile读取／绑定、管理状态展示；readonly认证仍将Profile集合与编译catalog作exact比较 | 新参数编辑／预览／不可变版本、六退出绑定与三MA50绑定原子激活、实际比例展示，以及合法Owner新revision的认证解释 |
| 发布 | 首尔独立安装、精确身份与保全门禁；静态前端独立发布另有边界 | 新schema与运行能力认证，不能以纯前端热发布代替内核升级 |

来源：[退出模型][C1]、[数量校验][C2]、[Claim][C3]、[生命周期][C4]、[Reducer][C5]、[派发][C6]、[管理观察][C7]、[管理接收][C8]、[readonly认证][C12]。这些是本轮本地代码核对，不宣称已刷新首尔当前运行状态。

### 2.2 研究与数量证据的限度

东京方案引用的**+73.770443277025 USDT**基础模型结果与**+52.120972439325 USDT**压力结果，来自理想连续5%配SOR1.2R；前者不是增量。**+80.934135339525 USDT属于SOR1.5R，不是本版。**“最小可执行提升至最高50%”尚需精确算法回放，且自动回放没有证明人工接管后的实际收益。费用／滑点、资金费缺口、固定历史交易集合与容量未补位限制必须继承。（来源：[研究修订][R1]、[理想组合数据][R2]及[A1]。）

首尔历史[5%数量核实报告][R3]证明相应采样时的规则及尺寸边界，例如0.019 BTC可以考虑提升到0.001 BTC、0.007 BTC的最小量实际占14.286%。它不证明当前余额、完整准入、交易所接受或限价完整成交。Hedge Mode减仓金额豁免未充分证实，首发继续使用原程序保守金额校验，不将“不充分证据”包装成交易所确定豁免或确定禁止。

**工程通过不以回放必须盈利为门槛；身份、数量、保护、可恢复性、管理权和已有资金授权是硬门。**以下章节为待实现设计，不是已完成能力。

## 3. 管理权是全部新动作的前置条件

### 3.1 管理权与退出阶段正交

| 管理权／阶段 | TP／计划事实处理 | 允许的交易所处置 | 严禁的推断或动作 |
|---|---|---|---|
| **AUTO，完整入场及保护通过** | 可生成准确PostFillExitPlan并准备TP | 原Kernel的TP、保护替换、退出、残单清理 | 先TP后保护、绕过健康租约、第二ENTRY |
| **AUTO，TP部分成交** | 累计F、核对Q−F、保留pre-TP约束 | 有充分证据时保留或正式调整保护；安全关闭亦受原阶段权限约束 | 伪造满额成交、提前Runner、按原Q盲补保护 |
| **AUTO，TP完整成交** | 满额事件一次、冻结实际余量和费用 | 保本保护替换；确认后原Runner | 将已提交／未知替换直接显示为已保本 |
| **REVIEW_REQUIRED，已保护阶段** | 保存可确认的成交／命令结果，核实归属 | 只读核实已发请求；新增普通自动处置暂停 | 因盈利、MA50或新配置恢复AUTO；未知就取消／重发 |
| **MANUAL，任何退出阶段** | 只读同步实际仓位／挂单／成交、核算占用 | 交易所已有单由Owner管理；程序不新增写入 | 自动保本、Runner、时间／风险平仓、撤单、补单、补仓 |
| **MANUAL，零仓仍有残单／未知结果** | 继续只读归零与终态核实 | 无程序撤单；保守保留占用 | 仅凭零仓释放标的，或自动清理残单赶迁移 |

新全局配置、Owner方向、MA50变向、控制台Resume、重启或升级都不改变已确认MANUAL。后续独立新Ticket默认AUTO，但仍需新机会和全部准入门禁。不得把全局ENTRY暂停增加为每次App干预前的强制步骤。（来源：[Owner决定][M1]、[原人工详细设计][M4]。）

### 3.2 外部干预与同批事实的优先级

1. 外部有效减仓、全平、退出单新增／改单／撤单，按精确账户／标的／方向识别整笔接管；不等成交，不以App点击或被拒请求推断接管。
2. 已知自身TP／止损成交、系统保护替换／撤旧止损、准确关联的algo子单不算人工；自身订单按**实际确认条款和Command身份**证明，不按ID前缀、5%或50%默认值证明。
3. 同一采集批次同时包含外部干预与完整TP事实时，先确保管理权收敛；若已转MANUAL，TP仍进入真实成交／经济记录，但不再产生新的BE／Runner写入。已经合法提交的较早领域事件不倒写删除。
4. 已准备但未发送的命令，在短事务按当前management revision和Aggregate版本重验；MANUAL使不再适用的准备命令失效。REVIEW保持受限，不伪造拒绝或已成交。
5. 已发送／结果未知的命令不能承诺撤回，不能声称程序可观察Owner点击瞬间或阻止此前已离开发送边界的请求。保留命令、发送和确认时间，查询准确结果；在MANUAL中已知结果只记录事实，不链式触发撤旧单、下一次改保护或退出。
6. 私有流缺口、身份矛盾、采集坏schema不抹除已成立的单次外部动作或当前暴露事实。三类证明分别保存；保护写入需要当前管理权、接收健康和行动时事实共同成立；发送边界测试包含client加载／限速等真实await，不能用全同步fixture掩盖授权到实际发送之间的变化。

### 3.3 首次保护之前的异常

沿用原交付前部分ENTRY、未知ENTRY、初始止损失败及成交后风险安全处理，不能因新退出计划尚未生成就遗留无保护仓位。提前外部干预时先冻结不适用的原数量命令并核实真实事实，不能宣称已成功交付，也不自动套用已保护后的正常接管流程。交付前的原安全退出职责不授予接管后权限；任何受控关闭都必须证明届时阶段权限、真实剩余数量及命令结果。该路径单独验证，不盲补原Q，不把REVIEW_REQUIRED静默改回AUTO。（来源：[原详细设计首次保护之前][M4]。）

## 4. 数量算法与可执行性

### 4.1 四策略统一纯算法

**算法：target_floor_then_minimum；f=0.05，c=0.50；Decimal计算。**Q由原预算／保证金／方向／容量计算先确定，禁止增大Q凑TP。

```text
P = 先按盈利方向及tick规范化的TP限价
q_floor = floor(Q * f / s) * s
q_min = ceil(max(s, minQty, minNotional / P) / s) * s
q_tp = max(q_floor, q_min)
q_runner = Q - q_tp
actual_fraction = q_tp / Q
```

q_floor保留现有向下取整语义；足够大仓位的实际比例可略低于5%。不是全部仓位强制向上到5%，不是默认改成50%，也不逐个试33%／50%碰运气。Claim和完整成交后的执行计划必须调用同一版本的纯函数。

完整条件：Q／TP／Runner符合各自订单类型步长；TP满足限价minQty/maxQty、价格及金额规则；Runner符合原保护／受控退出路径的对应规则；`0<q_tp/Q<=0.50`且Runner>0。**恰好50%允许；q_min超过50%时拒绝，不截断成一个仍不合法的50%订单。**规则缺失／过期不默认放行，最小金额按实际TP价格而非当前展示报价计算。

| Q（BTC） | 示例q_min | q_tp | 实际比例 | 仅比例判定 |
|---:|---:|---:|---:|---|
| **0.019** | 0.001 | 0.001 | **5.263%** | 允许 |
| **0.007** | 0.001 | 0.001 | **14.286%** | 允许 |
| **0.002** | 0.001 | 0.001 | **50%** | 允许 |
| **0.001** | 0.001 | — | **100%** | 拒绝新入场 |

表中不代表其他数量／金额／风险门禁通过。最小提升下的Runner可能只剩50%，UI／回放必须展示实际比例和剩余数量，不能仍宣称固定95%Runner。

### 4.2 SOR与失败归属

SOR-1H采用**原绑定比例＋原向下取整合同**，仅TP阈值改为实际1.2R；不因四策略新增算法而获最小量提升。原SOR不可执行的小仓位仍按原尺寸门禁处理。

准入阶段不合法返回 `exit_plan_unexecutable` 及zero/minQty/minNotional/fraction_cap/runner_size/rule_stale等细因，不创建Claim/Ticket/Command。已成交后才发现计划不合法时，不得只返回准入拒绝；按第5节和当前管理权收敛。拒绝、提升、实际比例与算法版本均留审计。

## 5. 实际成交R与PostFillExitPlan

### 5.1 不可变计划

完整ENTRY的准确fills去重后，冻结实际VWAP E、实际完整数量Q及原始有效初始止损S；LONG要求S<E，SHORT要求S>E。`d=abs(E−S)`，`initial_R_quote=Q*d`。以后人工或自动移动止损都不重算原始R。

LONG TP=`E+k*d`向盈利方向上取tick；SHORT TP=`E−k*d`向盈利方向下取tick。四策略k=1，SOR-1H k=1.2。记录舍入后的实际R倍数、价格规则与适用时间；价格非正或不合法失败。

一票唯一、不可变的**PostFillExitPlan**至少包含：Ticket身份、E/Q/S及初始风险、ENTRY命令与fill集合摘要、Profile ID/hash及原绑定revision、目标倍数、目标比例、最大实际比例、数量算法、TP价格／目标量、初始Runner量、实际比例／提升原因、订单规则摘要及生成时间。执行计划和后续真实成交是两类事实；Ticket原签发计划不覆写。

同输入重跑返回原计划；同Ticket不同计划冲突创建准确Incident。新生命周期／TP命令消费者统一读取已认证的新计划，禁止字段缺失时猜模式或回读旧schema。旧终态Ticket/Profile/hash/事件原样保留，缺新字段明确历史不可得。新版Profile显式记录价格基准及数量算法，不让新增默认字段静默改变旧hash。

### 5.2 保护顺序与管理权

1. Claim以参考价预校验，保存当时规则和允许证据；最终TP不是参考价承诺。
2. 完整ENTRY后先保障初始止损与原成交后风险检查，初始保护不等待控制台／研究／TP建单。禁止移动初始止损扩大风险以凑计划。
3. 在短事务重验AUTO、Aggregate版本、管理证据和配置冻结身份，提交唯一计划，再准备准确TP durable Command；发出前重验权限。网络I/O在事务外。
4. **仍属AUTO且有明确安全处置权限**时，计划不合法、实际风险越界或规则不可得，进入明确Incident与原受控关闭链，保留能用的保护，处理准确残单并先解决unknown。
5. **已确认MANUAL**时，不创建可执行新计划／TP／故障平仓，保留只读的成交与占用事实；计划未生成可标明接管导致未执行，不伪装为需要自动关闭的故障。
6. **归属待核实**时，不把计划失败变成新的普通自动写许可；核实已发请求及真实保护，保守处理新增资格。首次保护前按第3.3节独立安全职责处理。
7. ENTRY部分成交沿原取消余单、确认、受控关闭流程；不是正常完整入场计划。任何已知外部干预和阶段权限都须复核，不按原Q盲关闭。

旧活动交易不跨schema交接；首次迁移等待所有AUTO／REVIEW／MANUAL交易终态清洁。软件安装后若原绑定不属于新执行能力已认证可运行组合，ENTRY继续受限，不能让“安装默认未激活”期间产生缺执行合同的新票。后续配置回退只能指向当前schema内显式可运行且已认证的Profile／Gate组合，不以历史Profile名称伪装恢复了相同语义。

## 6. TP1部分成交、保本与Runner

### 6.1 成交身份与分支

F为冻结TP1目标的累计真实成交，必须由精确Command／namespace／订单／venue trade ID证明，重复／乱序幂等。不得用账户总减仓或“价格到过1R”代替F。

| AUTO下的事实 | 必须记录与核对 | 退出／保护语义 |
|---|---|---|
| **F=0** | 原Q、准确TP、初始保护 | pre-TP guards／TimeStop继续 |
| **0<F<q_tp** | 累计成交、实际余仓Q−F、费用及保护覆盖 | 不进入保本Runner；pre-TP退出不能被部分成交等待阻断 |
| **F=q_tp** | 准确余仓、均价、费用、全部数量相符 | 一次TakeProfitFilled；申请BE，新保护确认后Runner |
| **F>q_tp或自身成交矛盾** | 准确订单／fill冲突和当前暴露 | Incident／Reconciliation，不伪造满额事件 |
| **外部有效减仓／改单／撤单** | 先确认管理权与真实余仓 | 永久MANUAL，后续只读；不是一概当工程事故 |
| **余仓变化无法归属** | 保存独立可确认事实和缺口 | REVIEW_REQUIRED；不能冒充TP成交或Owner动作 |

自身止损的部分／完整成交走原系统执行对账，不因“仓位减少”误转MANUAL。部分TP事实处理不得把其他仍合法AUTO交易一概停管理。

**事件优先级冻结：**先记准确venue成交／结果并核对管理权；已确认MANUAL优先停止后续自动动作，REVIEW保持受限。仍AUTO时，原有退出意图、止损已触发／零仓、unknown待对账及ABSOLUTE到期优先于新的BE申请；没有这些状态且F已完整时才进入满额转换，pre-TP专属条件随该阶段结束。F仍部分时pre-TP guards／期限继续。不能因满额与期限同tick生成两个EXIT／BE，也不倒写实际较早已经提交的事实。

若原TP已确认终态而F仍未满额，不能无限等待、不降低冻结目标或填造满额成交。准确外部撤改走MANUAL，原系统退出走既有退出收敛；其余自身订单异常按已认证恢复合同处理，仍AUTO且无法合法恢复时保留能用的保护并进入准确的安全关闭。未知结果先对账，不借此另起补单脚本。

### 6.2 部分成交期间的连续保护

AUTO必须证明旧止损对实际Q−F仍有效且不会反向开仓；可以安全覆盖时保留，否则通过一条正式durable保护命令调整数量。新保护未确认前不能撤掉唯一有效保护；未知结果先准确查询，不盲重发。Hedge Mode参数及余量覆盖需要首尔适配器／真实订单规则证据，不能凭reduce-only名称推定安全。

**上述自动调整／安全关闭仅适用于仍有AUTO处置权限的路径。** MANUAL即使保护缺失、数量超配或费用未知，也只读核实、告警与保守占用，不自动换止损／撤余单／平仓。REVIEW无新增普通处置；已发结果继续收敛。无法证明AUTO安全覆盖／替换时走原明确安全关闭路径，而不是保留不明保护或将其假装转人工。

### 6.3 保本与Runner的真实性

费用修正保本使用剩余仓位分摊的实际入场费、保守退出taker费及原tick缓冲；已实现TP利润不用于放松剩余止损，未来返现不预扣。费用币种无法可靠估值时不能记零，使用明确保守估计并显示质量；资金费／跳空／滑点不承诺净零损失。

LONG保护只上移，SHORT只下移；已有更优保护不回退。现价已穿越拟议保本价时，**AUTO**走可执行的受控退出并记录真实价格，**MANUAL**不自动退出，**REVIEW**继续核实；不虚构保本价成交。pre-TP期限、保本申请和既有退出意图必须有确定优先级，避免同tick重复EXIT／BE；已进入退出收敛时不追发BE。

管理观察要接受目标5%到实际50%的合法计划变化、部分TP后合法保护数量替换和algo子单身份。所有自身写入由准确durable Command与已确认条款证明；计划变化不等于人工改单。

## 7. BTC4h SMA50与Owner控制

### 7.1 数据与时效

BTCUSDT USD-M永续、UTC原生4h边界、连续50根**完整闭合**bar，含最新闭合收盘，Decimal均值。指定三个LONG Event只在close>SMA50时通过；相等不通过。缺根、重复、未来、未闭合、错误市场或未覆盖决策时应闭合bar产生unavailable，不伪造bearish／neutral。

Observation以原有有界调度维护不可变snapshot及current pointer，每个4h闭合更新，网络在事务外，不新增服务。记录规则revision/hash、源窗口／摘要、bar结束／到达／available时间、close／SMA50、有效期和状态。旧bullish许可到下一4h边界失效；新bar未到时有限重试，持续不可得则限制该三Event，不覆盖Owner意图、不要求每天人工恢复。

### 7.2 准入与最终发送

资格为**原Detector／Strategy／Selection＋MA50（指定Event）＋Owner方向和资金预算＋账户／数量／管理风险门禁的交集**。Signal原始机会保留；拒绝只记录原因，不创建Claim／Ticket／Command。MA50原因区分not_bullish、unavailable、stale，与Owner暂停／方向预算分别解释。

Claim／Ticket前在短事务冻结准确规则与允许证据；final-send重读当前绑定、最新应闭合snapshot、Owner／runtime身份与短时发送授权。跨4h边界必须有新有效事实；不能沿用过期admission或签名，不重发原ENTRY。Gate／Owner配置切换与既有final-send采用同一明确锁序／版本纪律，网络不进事务。

MA50不自动修改Owner偏多／中性／偏空，不生成反手，不调整任何现有AUTO或MANUAL退出。BRF2／SOR免的是本MA50门槛，**不豁免人工仓风险未知、账户／标的占用、全局或策略暂停、预算和同标的跨方向互斥**。

## 8. 控制台配置、显示与通知

### 8.1 可编辑能力

首发开放认证过的TP倍数、目标比例、最小量提升开关及实际比例上限；四策略限制`0<f<=c<=0.50`，初始f/c固定5%／50%。SOR首发仅将倍数设1.2R，原数量比例／算法保持，界面不把四策略提升开关错误应用给SOR。TP倍数编辑校验采用**0.1—5.0R、0.1R步长**作为待实现能力合同，须先完成边界测试和认证；不是允许自动寻优或默认改变初始1／1.2R。

Runner／BE／guards／TimeStop首发只读展示原值及语义，不顺手开放未认证表达式。市场状态Gate有独立版本与受支持开关；关闭Gate是正式Owner控制动作，不由短期收益自动触发。

流程：选精确Event／方向→编辑→服务端预览→新旧diff与尺寸示例→TOTP→不可变Profile／规则revision→原子激活。预览不保证成交；确认时重验expected revisions、源规则时间与账户身份。策略退出配置修改**不等于某笔App接管**，也不重置现有Ticket的管理权或退出计划。

### 8.2 组合激活与展示

一次短事务创建／核对配置包，原子更新**六个Event退出绑定**（四单向＋SOR双向）、**三个MA50绑定**及activation审计。包内冻结product/account/venue、事件清单、profile hashes、规则revision、Owner决定引用、expected revisions；任一冲突整体失败。源码／当前行情不是Owner权限，禁止直接SQL修改活动JSON。

**版本认证也须适配可编辑能力。**种子catalog的Profile／hash继续逐项保全；Owner新建revision必须符合已认证的类型／参数范围、精确产品账户scope、原Profile继承规则及创建／激活审计。读取／部署认证验证当前绑定和这些合法revision，不能只因新增合法Profile就报错，也不能靠删除exact校验或信任任意JSON来放行。服务端只允许受支持TP字段，Runner／guards／BE等从准确原Profile继承。

未签发Claim遇绑定变化失效重评；已签发Ticket保持原冻结合同，待发送ENTRY仍受当前Owner授权和最新MA50约束。若Owner明确要求阻止旧待发票，走正式fence/drain，不修改原Ticket。未来当前schema内已支持的参数切换只作用于新票，无需反复部署或平旧仓。

每笔至少显示：目标TP比例、实际TP比例及提升原因、TP目标／累计成交／余量、实际R、计划版本、管理权与保护确认状态。MANUAL仍显示原计划供审计，同时明确**自动计划已停止执行**；自身TP后来成交不显示自动BE。REVIEW显示待核实，不能显示已人工接管或已完整保护。已确认保护、申请中、未知、缺失分别呈现。

通知复用本产品独立事务outbox：新计划／保护事实、TP部分／完整成交、接管及关键风险变化只按业务变化产生，不刷屏；平台accepted不等于手机到达。金额／数量／管理权取事务最终事实，不能因名义5%隐藏实际14.286%。通知和界面都不触发新交易权限。

## 9. 只读收尾、风险占用与经济证据

MANUAL部分减仓、原TP／stop自然成交、人工全平都只读同步实际仓位与订单；保留原E/Q/S／风险／计划，不把人工改单价重算为初始R。不补回减仓量，不因“已保本”释放无限新增风险。

零仓仍有残单、未知命令或过期暴露事实时，不宣称终态或释放标的。保守占用人工风险未知的仓位，Owner管理残单；系统在当前零仓／残单终态／已知命令结果均有准确证据时，经原Kernel推进Reconciliation／Settlement／Review及一次释放。对确凿外部全平，不因不相关历史缺口清空单次动作与当前收尾证明。（来源：[MA-R2设计][M5]。）

Review只计真实fills／fees／funding及实际合资格入账返现。TP计划、到过1R或预计20%返现都不是收入。自动闭环与接管交易分别呈现：全程AUTO、发生接管、归属／经济证据不足。记录接管时阶段、已成交量、已确认保护和在途命令，避免用最终人工收益评价未运行的自动Runner。不是新增人工操作评分或获利建议产品。

补充回放必须使用本次离散数量算法、SOR1.2R、成本和压力假设，输出目标／最小／实际量、实际比例、Runner、拒绝原因及分桶。四种对照为原基线、理想连续5%、严格floor5%、本版最小量提升且<=50%。固定自动路径与人工接管截断样本分开，不把研究数据缺失填零，不增加第二套真实风险做A/B。

## 10. 数据、事务与首尔发布

PostgreSQL唯一保存Profile／绑定、Regime事实、PostFillExitPlan、累计成交及管理权／生命周期事件；生成JSON只作诊断展示。复用现有订单／成交账本；唯一性约束覆盖一票一执行计划、fill幂等、配置revision、Aggregate版本及durable Command，不另建交易链。

保护、TP、退出、撤单等每次venue写必须先持久化Command，行动时再核对管理权、接收健康、准确数量及代码／schema。计划需关联准备时的management revision，接收结果同时记录当时管理权，不能把旧AUTO许可跨MANUAL复用。允许的交付前安全路径按准确阶段权限验证，不被普通盈利门禁误堵。

首次升级预计涉及schema。首尔必须经**真实Owner暂停新入场→保持Observation／AUTO保护／Reconciliation与管理接收→自然Drain→PG和交易所终态清洁→停止所有writer并重新核实→保全门控单链前向迁移→精确安装／身份→运行就绪→组合正式激活→官方promoter与真实Owner恢复**。管理接收仍由现有Reconciliation进程拥有，不另开写入服务。

**MANUAL仓不会因发布而被程序自动平掉。**等待期间Owner继续管理仓位和残单；只有现场仍有人工仓／人工残单阻塞时，才说明准确证据并请求Owner配合。不把人工改回AUTO、直接改终态SQL或强平当迁移捷径。退出配置升级不能使用前端纯静态发布路径。

软件安装默认不激活新参数，不恢复暂停策略，不重置方向／Selection／预算／账号。原冻结终态、管理权事件、命令结果、配置hash和Owner授权必须保全；迁移不假造历史PostFillExitPlan或新订单。迁移后只fix-forward，不降级schema、不活动仓位交接、不双写或运行旧表fallback。首尔正式入口沿用并扩展 `install_manual_host.py`，禁止改用东京发布器或临时SQL绕门。（来源：[双产品政策][M6]、[首尔安装计划][M7]、[独立安装器][C11]。）

当前源码、账户、schema及自然业务验收状态在执行时重新读取，不能由本方案或旧证书证明。后续版本控制与当时有效Owner授权沿原操作模型，不把历史维护暂停／恢复答复当永久授权。

## 11. 关键未决证据与完成标准

| 项目 | 已确定内容 | 待完成工程／现场证据 | 是否需重复设计业务参数 |
|---|---|---|---|
| 目标与参数 | 首尔人工版、三MA50、四策略1R／目标5%／实际<=50%、SOR1.2R原数量 | 精确Profile／规则与原子配置包 | 否 |
| 数量／真实R | 本文算法、实际完整成交VWAP及原始S | 纯函数、执行计划、规则时间与故障验证 | 否 |
| 部分TP | 完整前不BE，AUTO持续保护 | Hedge Mode序列、成交和重启证据 | 否 |
| 管理权交错 | MANUAL永久、REVIEW不新增普通处置、已发结果只读 | 跨采集／提交／发送／确认的反例与新基线 | 否 |
| 首尔行动时状态 | 本轮不作实时声明 | 主机／账户／PG／当前票／订单／控制／预算核实 | 否，冲突即停止 |
| 人工仓Drain | 不自动处置人工仓或残单 | 现场Owner自然清理与只读终态证明 | 仅仍有真实阻塞时请求配合 |
| 金额豁免 | 首发不依赖未证实豁免 | 官方协议或已有准确订单证据 | 否，不放宽 |
| 策略经济 | 新离散算法尚需回放，自动与接管分层 | 精确补充回放、前瞻净值／费用／资金费 | 否，不要求必须盈利 |

完成状态必须分开：**文档适配、工程认证、首尔安装、配置激活、Owner恢复、自然AUTO闭环、实际App接管及只读闭环、经济证据、通知平台接受／手机到达**。没有相应自然事件就保留未验证，不制造Signal／订单，不把方案或测试数当生产能力。

## 12. 来源与执行入口

[A1]: /Users/jiangwei/Documents/final-strategy-research/analysis/2026-11-10-tokyo-exit-regime-release/设计方案.md
[A2]: /Users/jiangwei/Documents/final-strategy-research/analysis/2026-11-10-tokyo-exit-regime-release/实施方案.md
[P1]: ../plans/2026-11-10-manual-exit-regime-release-implementation-plan.md
[M1]: 2026-11-06-app-manual-takeover-v1-owner-decisions.md
[M2]: ../../current/OWNER_RUNTIME_OPERATING_MODEL.md
[M3]: ../../current/MAIN_CONTROL_ROADMAP.md
[M4]: 2026-11-06-app-manual-takeover-v1-detailed-design.md
[M5]: 2026-11-10-manual-order-attribution-repair-design.md
[M6]: ../plans/2026-11-08-two-product-workspaces.md
[M7]: ../plans/2026-11-08-manual-new-host-installation.md
[R1]: /Users/jiangwei/Documents/final-strategy-research/analysis/2026-11-10-configurable-exit-evaluation/综合评估与设计修订.md
[R2]: /Users/jiangwei/Documents/final-strategy-research/analysis/2026-11-10-configurable-exit-evaluation/results/ideal_combination.json
[R3]: /Users/jiangwei/.codex/worktrees/manual-management-r1/final-manual/.local/tp1-five-percent-20261110/核实结果.md
[C1]: ../../../src/trading_kernel/domain/exit_policy.py
[C2]: ../../../src/trading_kernel/domain/capacity_sizing.py
[C3]: ../../../src/trading_kernel/application/build_capacity_claim.py
[C4]: ../../../src/trading_kernel/application/maintain_ticket_lifecycle.py
[C5]: ../../../src/trading_kernel/domain/reducer.py
[C6]: ../../../src/trading_kernel/application/dispatch_exchange_command.py
[C7]: ../../../src/trading_kernel/interfaces/management_observation_worker.py
[C8]: ../../../src/trading_kernel/interfaces/management_feed_worker.py
[C9]: ../../../src/trading_kernel/infrastructure/pg_exit_profile_repository.py
[C10]: ../../../src/trading_kernel/interfaces/owner_console_http/routes/controls.py
[C11]: ../../../scripts/trading_kernel/install_manual_host.py
[C12]: ../../../scripts/trading_kernel/certify_readonly.py
