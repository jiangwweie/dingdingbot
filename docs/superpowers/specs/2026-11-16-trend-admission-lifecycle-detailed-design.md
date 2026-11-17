# 趋势准入、局部试错与退出：详细设计

> **范围更新：** Owner要求先保留[趋势跟踪与减少磨损设计初版V0](2026-11-16-trend-following-low-churn-v0.md)供思考。当前不新增通用Regime或风险分档；MA50已上线且不属于本轮改动。本文保留此前设计过程，冲突内容以V0为准，不是开工清单。

日期：2026-11-16。状态：**首版技术定义V1，由工程方按Owner已确认取舍收敛；数值为确定的初始设计，不声称优化最优，不授权编码或激活。**

依据：[业务基线](2026-11-16-trend-cooperative-management-design-baseline.md)、[手机执行设计](2026-11-16-mobile-owner-control-detailed-design.md)。市场标签是确定规则，不是预测保证。A1历史回放未包含本稿完整准入/风险/局部试错，不能继承其收益结论。

## 1. 范围与不变项

保持当前批准风险上限、杠杆事实、容量、同标的双向禁入、无加仓、单Episode单Ticket单ENTRY。新增功能只能减少准入/风险或改变明确批准的新票退出计划。Owner方向偏好及既有禁用、健康、账户/品种、MA50等门禁取交集，不以新市场标签覆盖旧禁止。

首版改变SOR退出为无固定TP的结构趋势模式；BRF2保留既有小TP/小时Runner退出作为推荐基线；CPM/MI/MPG先保留已有退出，仅接入新准入与风险缩减。无成交样本不作为删除策略的理由。新ExitProfile选择只作用新票，所有策略的风险和人工权限都统一。

## 2. 数据、时间与市场标签

### 2.1 原始事实

BTC与候选币使用本venue同一合约成交价闭合K线：1h和4h。UTC开闭边界以close_exclusive_ms统一；在周期结束后至少5秒拉取并确认闭合，保存原始54根4h/64根1h窗口digest、价格源、fetch_at、close_at、规则version。ATR是TR的14期算术平均（复用当前公式），不是另换Wilder而仍用同一名字。

4h指标至少需要当前及3根前SMA50、ATR14，连续推进保留上一候选和当前状态；取最近54根完整4h供增量计算。1h指标需21根收盘价，另保留候选/趋势状态，拉取64根有界窗口。窗口长度满足指标计算，不等于可以每次从窗口尾部重新推断全部状态。数据有缺口/不连续/未来/错品种/未知修订：UNKNOWN，阻止相关新准入；已有venue保护保持，继续独立管理采集。

原始窗口初次冻结后不能让后来回取数据覆盖此前Signal/Claim证据。发现后修订只形成新snapshot revision，从后续判断生效，不倒写历史Signal。此前MA50窗口差异尚未唯一归因，首次实施应同时补齐此证据链。

### 2.2 大盘方向（BTC 4h）

令C为最近闭合价，M为SMA50，A为ATR14，S=M当前−M三根前。初始候选：

- BULL候选：C>M+0.25A且S>0；连续两个4h闭合候选成立，状态BULL。
- BEAR候选：C<M−0.25A且S<0；连续两个候选成立，状态BEAR。
- 其他：非方向候选。已有BULL只有C<M或S≤0连续两根才退到RANGE；BEAR镜像。相反方向连续两根完整成立可以直接切换。
- 首次建立且指标齐全时，以RANGE初始化；必须随后两个连续闭合候选才确认方向。指标不足为UNKNOWN。正常重启恢复PG状态和上一候选，不重置RANGE、不从截断窗口猜已有方向。长期数据缺口后必须重新累计连续证据，不能把间隔的两根当连续。

0.25ATR与两根确认是避免来回翻转的初始规格，代价是方向确认延迟，不与“最早抄底/摸顶”兼得。

### 2.3 单币趋势与突破确认（1h）

定义ER20=abs(C_t−C_t−20)/sum(abs(C_i−C_i−1))，分母为0则ER=0。它只衡量20小时净位移与总路径之比，不直接代表盈利概率。

状态为RANGE、PENDING_UP、PENDING_DOWN、UP、DOWN；数据不可用另为UNKNOWN。每根闭合K线只执行一个最高优先级转换，不能同根先失效再重新创建相反候选。

1. **首根有效突破**：RANGE时，收盘严格高于此前4根high最大值则PENDING_UP，低于此前4根low最小值则PENDING_DOWN。冻结此次边界和候选K线时点，首根不要求ER≥0.35，允许被原策略Signal选中后按半风险尝试。只有影线越界不成立。
2. **确认趋势**：随后第1或第2根完整1h，收盘仍严格位于被冻结边界同侧，且ER20≥0.35，转UP/DOWN。不是要求后续每根都刷新移动新高/低，也不是把首根当自我确认。
3. **候选失败**：任一后续收盘回到边界或穿回区间，立即RANGE；到第2根仍未满足效率条件也RANGE。清除当根不重新建立候选，下一闭合根才可尝试新突破。
4. **已确认趋势保持**：UP直到收盘低于此前4根low，或ER20<0.20连续两根才回RANGE；DOWN镜像。ER回到≥0.20即重置低效率计数。此处失效只改变新准入上下文，不直接平掉已有票。
5. **事实期限**：snapshot包括闭合时点、可用时点、下一周期截止；下一周期已结束但新事实未完成时，准入UNKNOWN，不沿用过期标签。至少5秒只是采集下限，实际fetch_at可能更晚；只有真实已获取的事实能授权。

初始指标齐全时从RANGE开始，之后顺序持久推进。恢复必须载入PG候选边界/时间、趋势状态和低效率计数；缺状态不可靠最近两根猜测。新增币至少完成指标warmup和正常状态推进才准入。

这些标签不独立产生Signal；策略原始事件仍由Registry/detector负责。市场标签只形成admission context，不把不同策略的入场逻辑合成一个通用突破系统。

## 3. 策略矩阵与风险乘数

首版类别：CPM/MPG/MI为趋势延续；SOR-1H为方向敏感的开盘区间突破；BRF2为反弹失败反转。SOR原Event与当前Registry方向不变；退休SOR/TradFi范围不启用。

| 策略/候选方向 | BTC同向＋单币已确认同向 | BTC同向＋单币BREAKOUT_PENDING | BTC RANGE或反向 |
|---|---:|---:|---|
| CPM/MPG/MI LONG | 1.0 | 0.5 | 拒绝；仍须原MA50条件 |
| SOR-1H LONG/SHORT | 1.0 | 0.5 | 拒绝 |
| BRF2 SHORT | 1.0（BTC BEAR且单币DOWN） | 0.5 | 0.5且须原反弹失败条件；原strong_uptrend_disable成立仍拒绝 |

所有单币UNKNOWN拒绝。趋势延续/开盘突破遇单币RANGE或逆向拒绝；BRF2只要其已确认反转Event满足，可在单币尚未DOWN时按0.5，不将新标签强制替代反转检测。

**逆大盘允许低风险，不等于取消BRF2既有强上升趋势禁用。** 如要放宽该禁用需另立业务决定，本稿不做。

### 3.1 定量落地

**风险档位是目标风险，不是保证成交量。** 正常档1.0、试错档0.5、禁止档0。已有0.5票后续确认趋势不加仓；更好的行情只改变新的独立机会。

有效单票计划风险T=行动时wallet×Owner单票风险上限×multiplier。总/方向限额仍是Owner原值与已有overlay的最小值，usage计所有未终态及人工风险，不因乘数变小释放旧票预算。

最低materialization比例0.50作用于有效目标T；例如试错档的目标为原单票风险上限50%，受保证金等限制时实际可低至该有效目标50%（原上限25%），界面显示实际计划风险，不能把目标50%冒充固定半仓。不能错误地仍以未缩减目标计算而全拒绝。最小交易量导致实际风险>T则拒绝，不向上提高风险。保证金按原分配与剩余总额约束；乘数只缩减风险目标，不通过放宽Stop或提升杠杆实现规模。

Signal/Claim冻结snapshot及乘数。发送前重读当前标签：新条件更严格或UNKNOWN则终止该ENTRY，不盲重试，不在dispatch阶段改quantity；更宽松也不提高冻结尺寸。按照原有权威拒绝终态与新信号语义处理。

## 4. 同一结构试错与局部暂停

### 4.1 身份与创建

新增MarketStructure不是Exposure Episode的替代：它跨多次新Episode识别同一币种/方向的一段区间，所有策略共用该局部风险上下文。domain=`product+account+venue+instrument+side`；同标的跨方向互斥仍原规则。

首次合格候选出现时，用**信号K线之前20根完整1h**冻结区间H/L、ATR14、anchor_close_ms，生成structure_id；不每小时滚动改身份，不因信号false→true或换策略就重置试错次数。结构状态、创建原因和数据digest持久化。

### 4.2 尝试与失败

一次实际ENTRY开始成交才计一次尝试；发送前拒绝、无成交撤单不计市场试错。部分ENTRY事故单独计执行事故，不当作市场失败；原事故门禁仍有效。

失败定义：该票最终flat，且满足下列任一：原初始Stop或明确策略invalidated/time-before-trend退出；或按实际成交毛额扣已知费用/保守未确认费用后经济≤0。资金费/费用未知可能影响正负时标记outcome_pending，局部不放行新的尝试，不能以缺数据当盈利解除。

Owner减仓/全平的负结果计局部消耗；Owner主动盈利退出不计失败。策略失效退出即使小赚也计failed_attempt，因为本结构未按预期发展。结算事件唯一消费，每个Ticket最多一次；不同Review补充不重复扣计。

**Owner已确认首版：同一结构两次失败后暂停（2026-11-16）。** 采用累计失败数，不因中间一个小赢家清零，防止频繁付费。首版不增加全账户日亏熔断、跨币累计现金额度或固定冷却时间。

### 4.3 新结构恢复

局部暂停后，继续只读观察；需满足两种新结构之一，且引用的K线都晚于最后失败确认：

1. 确认脱离旧区间：同向连续两个1h闭合价在旧H+1×旧ATR（做多）或旧L−1×旧ATR（做空）之外，ER20≥0.35。
2. 区间重新形成：至少6根新1h闭合后，最近6根range包含于旧区间、宽度≤旧区间宽度50%，且其上/下边界与旧边界至少一侧相差≥0.5×旧ATR；连续两次观察得到相同6根已完成的候选区间身份不可简单滚动认定，采用首次满足的6根作为冻结候选，随后一根仍收在该候选区间确认。

恢复时新structure_id、failure_count=0，旧结构RESOLVED，新事实只影响随后新的Signal；不回放此前被拒绝的旧Signal，不自动下单。既有策略rearm必须独立满足，严禁重用原Episode。

无有效突破/新收敛区间则持续暂停，可能错过快速V形或起步段，是本方案降低震荡磨损的显式代价。Owner可暂停/启用策略，但“启用策略”不清空局部失败账；首版手机不提供强制清零按钮。

暂停信号与Owner策略暂停、数据UNKNOWN、事故门禁分别存储；解除局部门禁不解除其他门禁。已有仓位不因局部暂停被强平。

## 5. SOR趋势退出：新计划V3

### 5.1 明确类型

ExitPlan采用带判别字段的冻结模型：`fixed_tp_then_runner`保留现有真实TP模式；`structure_trend_no_tp`表示无固定TP/无强制BE。不向原take_profit_quantity塞0，不伪造TakeProfitFilled。

输入包含实际完整入场VWAP、初始Stop、初始风险R0、quantity、原session/失效参考、观察周期与trend规则。真实部分入场仍原事故处置，不能借新模式接管半成品。

阶段：`PROTECTED_PROBATION → TREND_PROTECTION_PENDING → TREND_ACTIVE → EXIT_PENDING → TERMINAL`。PROBATION有明确失败/时间退出；TREND没有自动保本和固定TP减量。Owner获利退出单独记减量事件，不扮演趋势里程碑。

### 5.2 进入趋势

沿A1可解释起点：SOR在入场后完整1h收盘，按方向达到1.2×abs(entry−initialStop)；同一时点最近4根闭合1h的结构价±0.5ATR14，较当前Stop改善至少2tick且触发位置合法。

先检查原SOR pre-TP reclaim/session/绝对24小时失败条件；命中则退出优先。否则形成TrendProtectionRequested，正式保护替换确认后才进入TREND_ACTIVE。Pending期间原失败规则仍有效，确认后不因回落到里程碑以下自动降回PROBATION。

原15m失效/会话与1h结构更新时间分离。旧96×15m时限用明确UTC期限表达，不能变为96×1h。Trend确认后不再按原session/24小时单独清仓；结构、实际风险/强平距离、市场可交易性及Owner退出仍有效。

### 5.3 趋势保护

多头结构候选=min(last4 lows)−0.5ATR14；空头=max(last4 highs)+0.5ATR14；价格按保守tick方向取整。多头有效Stop=max(initial,current,Owner_floor,candidate)，空头min。仅闭合事实有新watermark且改善≥2tick才改单。

若候选保护已被当前价穿过，不挂一个会立即触发而语义不明的新Stop，按明确`trend_structure_crossed`生成正式退出请求；保留原保护直到执行核实。

每小时动作不表示每小时才执行止损，venue已有Stop按其触发参考价实时保护。费用感知盈亏只用于展示/会计，不再无条件添加entry价附近的BE夹持。

### 5.4 时间、资金费与缺数据

Trend阶段首版不新增任意最大持仓小时数或资金费自动平仓阈值；仍核算每次funding，持续占用容量/风险，Owner可结束。停牌/下架等原有效venue约束不取消。成本或状态变化发送必要异常信息，但不能借提醒自动触发未经定义的平仓。

市场数据过期不放宽/撤Stop，也不假造结构；停止新的结构改单并报告事实缺失。管理归属不明继续现有REVIEW路径。恢复后使用最后已生效Stop和新闭合结构，不重放所有旧改单。

## 6. BRF2及其他策略

BRF2首版维持批准的小TP、原真实成交BE及小时Runner；接入市场风险乘数与局部试错。原因是A1回放中该组未改善，不用SOR表现覆盖BRF2特性。CPM/MI/MPG同样先保留已冻结退出。

这意味着“完整Runner”首轮不是全策略替换。Owner对所有AUTO票的减仓/收紧通过统一操作协议；人工TP与保留内置TP的冲突需显式分支，不允许两套超量获利退出并存。详见手机执行设计§6.4。

## 7. 数据模型与进程归属

建议新增：

- `brc_market_regime_snapshots/events/current`：symbol、timeframe、kind、rule_digest、raw_window_digest、close/fetched/valid times、state transition。
- `brc_market_structures`及`brc_structure_trial_events`：冻结区间身份/生命周期、Ticket outcome唯一引用。
- `brc_local_entry_gates_current`：精确domain、reason、source structure、pause/recovery事实，不改Owner策略控制。
- Signal/admission context及Claim/Ticket附冻结regime、structure和effective_risk_target引用。Ticket不可变，新增变化写事件。
- ExitProfile V3、Aggregate趋势阶段/Owner约束引用及新增事件，复用Exchange Commands和保护事实。

Observation生产有界闭合行情及市场标签，策略detector仍生产原Signal；Entry在现有串行准入内消费有效上下文并冻结Claim；Lifecycle只处理持仓阶段/Owner操作；Reconciliation完成真实成交归属、终态和一次trial outcome结算。不得把市场趋势判断放到venue adapter里，也不能由手机直接修改局部门禁。

事务只写PG，不夹网络。snapshot按唯一(symbol,rule,close,revision)幂等；Structure按domain行锁，failure settlement按Ticket唯一键；暂停与失败计数原子。新标签落地和在途ENTRY由dispatch最终门检查，不靠UI缓存。

## 8. 有界成本与重启恢复

每小时每个有效币拉取一次64根1h窗口，BTC每4小时一次54根4h；复用已核实同源采集，禁止每票重复全历史请求。最大币种范围仍受现行Registry/Universe约束。重试限3次后记录data_gap，下一正常周期继续，不无限热循环。

Current查询走domain/active索引；每次Reconciliation最多处理50条待结trial事件；超时不吞证据。raw窗口去重按digest存储，保留支持实际Signal/Claim与已成交Ticket的证据，不写生产Markdown/JSON。

重启从PG恢复阶段、结构、暂停来源与最后watermark。启动不重置失败数，不把UNKNOWN当neutral，不按文档或配置文件生成新授权。

## 9. 与收益目标的关系及未决验证

理论目标是限制非趋势损耗、提高趋势捕获；不是强制账户收益达到市场幅度2倍。较严格的准入和局部恢复会减少机会；持仓更久会排挤后续机会；逆势半风险也可能连亏。

本稿参数是完整可回放候选，不与A1历史结果混同。需重新跑时间顺序全Signal/准入、变化后wallet/保证金/方向容量、手续费/资金费与停止/恢复，单票固定入场不能验收本稿组合行为。

代码和协议测试用于证明行为正确；经济回放用于展现取舍，不以“先证明稳定盈利”阻塞设计结论。具体性能/安全/数据保全与放行边界见[验收计划](../plans/2026-11-16-trend-mobile-design-review-and-acceptance.md)。

## 10. 定义层面核验与证据边界（2026-11-16）

在计算前冻结“固定突破边界确认”修订原因，使用此前截至11月14日13:27的已保存官方行情，对14笔原真实入场做状态映射。不是新增全Signal/资金顺序回测，也不计算新方案净收益。

| 资格结果 | 旧稿严格连续创新极值 | 本稿固定边界确认 |
|---|---:|---:|
| 正常风险资格 | 1 | 3 |
| 半风险资格（含反转策略仍需原门禁） | 5 | 7 |
| 大盘方向不符 | 1 | 1 |
| 单币结构未满足 | 7 | 3 |

14笔只代表原成交样本，不是所有Signal。旧稿比较采用一致的闭合ER门槛实现，其中原稿PENDING保留曾有文字歧义；不是已运行过的生产版本。所有资格还需原Signal/健康/Owner/资金门禁，不能据表声称必然成交。

本稿仍会过滤11月10日ETH、11月12日ADA、11月14日XRP等原入场；不为保留这些历史赢家事后取消门槛。11月14日BNB和ETH落入半风险，不能沿用A1固定原数量的盈利。

定义核验覆盖未来数据追加不改变已分类历史、合法状态、ER范围、14入场事实时点、平坦市场不制造趋势、单调涨跌镜像。历史可用时点用闭合后5秒模型值，不是封存的每次真实HTTP到达时间；这项近似在正式历史/前瞻准入验证中必须单列。

[核验说明与结果](/Users/jiangwei/Documents/final-strategy-research/analysis/2026-11-16-trend-definition-review/定义核验.md)。生产实现仍待另行授权；这里没有改动执行代码或策略参数。
