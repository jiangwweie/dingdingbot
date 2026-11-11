# 首尔人工接管产品：实施、认证与服务器发布方案

> **后续执行记录（2026-11-11）**：Owner 已在本线程授权按文档编码，当前本地实现与认证进展见[实施证据](../plans/2026-11-11-manual-exit-regime-implementation-evidence.md)。下文“本轮仅文档”描述原交付阶段，不撤销后续授权；服务器状态仍以路线图及行动时证据为准。

## 1. 交付目标与执行地位

**唯一设计依据：[MA-EXIT-REGIME-01人工版设计][D1]；日期：2026-11-10（北京时间）。本轮只完成文档适配，以下实现／回放／认证／服务器步骤均未开始。**Owner已给出的交易参数直接沿用，不再次讨论5%／50%／SOR1.2R；目标为本人工接管工程的首尔独立产品，不对东京执行。

| 工作范围 | 冻结决定 | 人工版额外条件 |
|---|---|---|
| CPM／MI／MPG LONG | BTC完整闭合4h close>SMA50 | 只是新ENTRY资格，不改变旧票管理权 |
| 四策略TP1 | 实际完整入场1R，目标5%，最小提升且实际<=50% | 真实成交，AUTO完整目标成交后才BE／Runner |
| SOR-1H LONG／SHORT | 实际完整入场1.2R，原数量比例／原算法 | 不误套四策略最小量提升或MA50门槛 |
| 管理权 | 默认AUTO，外部有效干预永久MANUAL，未知REVIEW | 新计划、部分成交、保护写入及异常关闭全部遵守 |
| 资金／运行控制 | 继承届时有效Policy、方向、Selection与策略启停 | 不扩大风险，不恢复暂停策略，不自动交回MANUAL |
| 首次发布 | 独立首尔stopped／flat／preservation前向迁移 | 人工仓与残单由Owner管理，真实暂停／恢复与官方promoter各自有效 |

链条：**当前人工代码基线→数量与真实R→部分TP持续保护→管理权交错与只读收尾→MA50／控制台原子配置→精确补充回放→冻结候选认证→首尔行动时preflight→真实Owner暂停及自然Drain→停止所有writer并复核→保全迁移／安装→正式激活→官方promoter及真实Owner恢复→自然AUTO与App两类验收**。

当前代码／生产身份／控制／自然验收事实只从[人工路线图][M1]和实时PG／交易所获取。本轮未在线刷新首尔；历史数量报告和以前暂停／恢复答复都不能证明执行时可以停机或切换。

## 2. 复用与隔离边界

### 2.1 复用清单

| 现有能力 | 复用方式 | 本次新增／适配 |
|---|---|---|
| Profile／Binding／hash | 不可变合同、Owner控制和精确Ticket读取 | 数量算法与实际R元数据、新revision创建／预览／组合激活 |
| CapacitySizing／Claim | 原资金、方向、保证金和数量门禁 | 四策略最小TP提升、50%上限、SOR原算法分支 |
| Ticket／Aggregate／durable Command | 单票单ENTRY、短事务、幂等和未知结果恢复 | PostFillExitPlan、部分TP累计、保护及故障分支 |
| 管理证据／feed／基线 | 准确自身命令、外部事实、覆盖水位、接收健康 | 适配新比例／数量替换／条件子单，不重引固定50%默认条款 |
| MANUAL只读链 | 实际数量、残单、风险占用、Settlement／Review | 部分TP及在途保护结果在接管后仍可准确收尾 |
| Owner API／TOTP／前端 | 版本冲突、幂等、审计和操作确认 | TP可编辑字段、实际比例和管理权／保护状态分开展示 |
| 四持久Worker | Observation／Entry／Lifecycle／Reconciliation | MA50有界事实、新状态机；管理接收仍属于Reconciliation |
| 首尔发布与认证 | 精确产品/SHA/schema、writer停止和保全 | 新schema／Profile身份／配置版本纳入现有认证，静态版本也核对 |

### 2.2 文件、账户与执行者

- 交易执行仅 `src/trading_kernel/**`，迁移仅 `migrations/trading_kernel/**`；本人工版的测试、Owner API及 `frontend/owner-console-v2/**` 为相应产品边界。
- 从最新**已核验人工基线**建立或复用focused `codex/manual-exit-regime-v1`。当前本地文档分支不自动成为生产候选；不得因manual-dev落后而覆盖已交付归属修复或前端。
- 本地使用本人工产品自己的 `.venv`、`scripts/local/manual_pytest.sh`、独立 `brc-manual-pg`。不得复用Tokyo DB、模板、证书、`.env`、账户或凭据。
- 通用算法／修复可在审查后选择性移植，必须核对人工版差异并独立验证；不整分支合并东京，不移植东京对外部干预的自动处置语义。
- 活跃研究及补充回放产物放 `final-strategy-research` 的独立人工版分析目录，明确source cohort与管理权；工程文档／源码／认证留在人工工程。研究JSON不进入生产权限。
- 一名主实现者按依赖推进；本计划不授权子代理，不并发编辑schema／reducer／dispatch。保留用户其他工作区和未提交改动。
- 本轮仅文档。未来执行依据Owner当时明确范围和现有授权；无凭据复制、提现、资金转移、测试单、伪造Signal或越过失败门禁。

## 3. 实施工作包

### ME-00：人工基线与合同冻结

**目标：**定位本人工版准确调用链和所有写入口，防止把东京代码清单当首尔完成证据。

- **依赖：**本设计与配套计划进入后续执行范围；业务参数无需重新设计。
- **允许：**仓库／源码／当前工具CLI／证据的只读检查，建立focused分支和最小失败用例。
- **工作：**核对Profile／Claim／完整ENTRY／初始保护／TP／管理观察／最终派发／MANUAL收尾链；列全四Worker、Reconciliation内部管理接收／通知及Owner API等writer。核对当前schema单线head、当前正式安装和promoter参数，不预占迁移编号。
- **RED／缺口：**准确复现当前partial TP异常、参考价不等实际VWAP、新5%提升无能力、catalog认证不接受Owner新revision等实际缺口；保留MANUAL不回AUTO测试。
- **完成：**来源差异、参数合同、允许文件、生命周期权限矩阵和验证映射固定；没有服务器变更。无API／参数新能力前不直接改Profile配置上线。

### ME-01：数量、Profile版本与forward数据合同

**目标：**同一纯算法同时约束Claim预校验和PostFillExitPlan，记录真实比例而不扩大Q。

- **依赖：**ME-00。
- **文件：**`domain/exit_policy.py`、`capacity_sizing.py`、Ticket/计划类型、Profile仓储、pg_models、单链迁移及相关unit/integration。
- **RED：**BTC0.019／0.007最小提升、0.002恰50%、0.001超过上限；大仓位floor略低于5%；minNotional使q_min超过一步；TP有效而Runner无效；maxQty／tick／规则过期；SOR未改算法；LONG／SHORT价格、Decimal精确边界；新增字段不改变旧hash。
- **实现：**设计第4节统一函数，返回目标／最小／采用TP量、Runner量、实际比例、提升与拒绝原因、规则摘要。定义新Profile能力版本及一票唯一计划／fill幂等／配置revision约束，冻结价格基准和数量算法。
- **认证合同：**源码种子catalog及其历史hash继续逐项验证；Owner新创建Profile需产品／账户scope、支持能力版本、typed参数范围、原Profile继承与创建／激活授权审计。补齐readonly certification／seed／部署保全的解释，不能删掉exact校验或任意信任PG JSON来让控制台可编辑。
- **迁移：**精确source表／列／行保全；旧终态新字段标明历史不可得，不填造实际R或执行计划。没有Signal／订单／策略Resume／Profile自动激活副作用；新旧writer不并存，无schema fallback。
- **完成：**纯函数、空库和终态生产形态升级通过，Owner受支持的新revision不要求换代码，未授权／未知Profile仍拒绝。

### ME-02：实际完整成交R与保护优先

**目标：**TP始终来自实际完整ENTRY及原始有效止损，而不是将计划参考价改名为实际R。

- **依赖：**ME-01。
- **文件：**Claim／ENTRY事实／初始保护／执行计划／原命令与仓储边界，最小domain/application改动。
- **RED：**VWAP异于参考价、多个／重复／乱序fill、post-fill d<=0、价格／金额／风险越界、计划落库失败、TP拒绝、初始保护失败、ENTRY partial／unknown；计划生成前后外部干预与management revision改变。
- **实现：**完整fills去重冻结E/Q/S→保障原初始保护及post-fill风险→短事务生成唯一PostFillExitPlan→AUTO准备TP durable Command。SOR采用1.2R，四策略1R；新计划冲突可解释且幂等。
- **权限：**仍AUTO且具安全职责才进入计划失败受控关闭；MANUAL保留只读事实不自动TP／平仓；REVIEW核实已发结果，不用异常抛错产生新写权限。交付前安全路径按原准确阶段职责独立验证。
- **完成：**Ticket不可变、无第二ENTRY、初始保护不等待TP、崩溃和提前干预不遗留被假称成功交付的仓位；不能仅返回准入拒绝遗留已成交AUTO持仓。

### ME-03：部分TP持续保护与满额后Runner

**目标：**修复现有partial异常，覆盖0／部分／完整／超量及保护执行序列。

- **依赖：**ME-02。
- **文件：**`maintain_ticket_lifecycle.py`、events/aggregate/effects/reducer、Lifecycle事实／venue适配器、fill仓储和测试。
- **RED：**`F=0`、`0<F<q_tp`、`F=q_tp`、`F>q_tp`；累计乱序／重复；最后fill在取消前后到达；TP和stop同时成交；TP终态但F未满额；pre-TP guards／TimeStop与满额同tick；保护accept／reject／unknown；原止损触发；数量不符；故障恢复。
- **实现：**精确F与实际Q−F、费用、保护覆盖一并持久化。部分不提前BE且不阻断原退出；满额一次TakeProfitFilled，保护替换确认后才RUNNER_PROTECTED。旧保护／新保护／撤旧单使用准确durable命令与结果。
- **外部证据：**证明首尔精确Hedge Mode下原止损能否安全覆盖减仓后的真实余量，以及必要替换序列。记录型fake证明控制流，官方协议／已存在准确订单证明venue语义；不提交测试订单或盲用reduceOnly参数。
- **完成：**AUTO无唯一保护先撤空窗、无反向开仓或重复BE／EXIT，已有更优止损不放松。不能证明AUTO安全保护时按既有有权路径收敛；MANUAL／REVIEW转交ME-04，不自动套用全自动强平分支。

### ME-04：管理权交错、订单归属与MANUAL只读收尾

**目标：**使新增退出能力完整服从已交付人工产品语义；这是人工版独立关键路径。

- **依赖：**ME-02／ME-03及现有管理证据链。
- **文件：**`observe_trade_management.py`、管理观察／feed、`trade_management.py`、`dispatch_exchange_command.py`、reducer、`reconcile_ticket.py`、相关PG仓储与回归。
- **RED：**1R前接管、部分TP后接管、满额同批接管；换保护准备／已claim未发／已发送未知／确认待撤旧单四时点；自然TP／stop／algo子单与真实外部单区别；同ID改回；重启后管理权；采集断流／坏schema／提交失败；人工全平残单／unknown／过期零仓。
- **实现：**准备时management revision与最后派发短事务重验；MANUAL使未发普通命令失效，REVIEW保持受限。已发命令结果只读记录，不链式触发后续自动撤单或BE。新5%—50%实际条款、部分保护数量替换仍由准确基线匹配为自身，不误认Owner。发送边界覆盖client市场加载／限速后的真实等待，不仅测试claim之前；已发请求不能承诺撤回。
- **只读收尾：**MANUAL成交累计与实际余仓、订单／风险占用继续投影；自己的原TP自然成交也不恢复AUTO；当前零仓／订单终态／命令已知才能Settlement／Review和一次释放。同标的相反侧在全部占用清洁前仍禁入。
- **完成：**本地真实协议形态／PG／发送前竞态测试证明MANUAL零新增venue写、REVIEW零新增普通自动处置、unknown不盲重发、原初始安全路径仍有效；不能用“测试通过”冒充真实App验收。

### ME-05：MA50事实、Admission与最终发送

**目标：**三LONG资格与Owner预算取交集，保持BRF2／SOR和旧仓语义。

- **依赖：**ME-01；最后认证与ME-02—04统一。
- **文件：**typed Regime纯核心、Observation／public source、统一Admission快照／Claim／ENTRY preflight／final-send／Owner解释及相关测试。
- **RED：**49根／缺失／重复／未闭合／未来／错市场／close==SMA；bar available时间；新4h到达前旧允许失效；Claim允许后跨边界；绑定／Owner切换与发单竞态；BRF2／SOR免本Gate但仍被人工仓风险未知或预算阻断；全局暂停不被MA50覆盖。
- **实现：**50完整4h／UTC／Decimal／严格大于，准确规则revision及窗口／到达摘要，有界共享去重和原四Worker调度；不自动写Owner方向，不抹原Signal。
- **完成：**资格／Claim／Ticket／最终签名一致，拒绝无新票，绑定与发送锁序有明确反例。MA50变向不能停止已有AUTO冻结退出，也不能自动处置MANUAL。

### ME-06：Owner可配置版本、UI与通知

**目标：**日后已支持参数能通过控制台正式创建和激活新版本，同时清楚显示真实管理权与比例。

- **依赖：**ME-01—05。
- **文件：**Owner application／Profile与Gate仓储／controls API、`frontend/owner-console-v2/**`、outbox／解释和对应API/UI测试。
- **RED：**未授权／TOTP无效／跨账户／错误Event、越界参数、重复request、expected revision冲突、源规则过期、六绑定或三Gate任一步失败、事务中止、原暂停策略被恢复、MANUAL旧票因全局配置改变被改写。
- **实现：**TP受支持范围／算法／真实比例预览→diff→TOTP→不可变revision→一次事务全部激活；服务端从准确原Profile继承Runner／guards／BE，不接收任意全量JSON放宽这些字段。初始参数固定于设计表，SOR不得误套5%算法。
- **显示：**目标／实际比例、提升原因、R基准、TP累计／剩余量、保护申请／确认、AUTO／REVIEW／MANUAL分开；MANUAL标明自动计划停用，原计划仍供审计。预览不是成交承诺，配置切换不是App接管或Global Resume。
- **通知：**原人工版独立outbox使用事务最终事实，部分／完整成交与接管准确去重；20%返现只计已实际入账合资格金额，不预先降低保护成本；平台accepted与手机到达分别声明。
- **完成：**版本、capability／readonly certification与UI一致；参数变更不破坏运行身份；没有直接SQL或前端自行计算后写权威配置的路径。

### ME-07：离散数量补充回放与人工版分层

**目标：**不把理想5%的旧结果当本次算法／人工产品收益。

- **依赖：**ME-01纯函数冻结，使用ME-02／03最终执行语义。
- **范围：**现有分钟路径／成本假设复用，研究输出只进入research独立人工版目录；本地工程仅使用脱敏fixture，不重新建设研究平台或扩Shadow配额。
- **对照：**原基线、理想连续5%、严格floor5%、目标5%且最小提升<=50%；SOR均按本次1.2R并明确原基线。实际门槛触发／限价成交／采集延迟不等于分钟模型，不能调参数硬拟合。
- **强制输出：**逐票Q／目标／最小／实际TP／Runner／提升与拒绝原因；<=5%、>5%—10%、>10%—25%、>25%—50%分桶；共同可执行样本的参数变化与新增／排除样本构成分开。
- **人工分层：**全程AUTO与发生接管／归属未知的样本分列，记录接管前阶段／仓位和在途命令。人工后真实收益不能当自动Runner收益；自动反事实单独标示，不虚构Owner何时会干预。
- **经济输出：**真实与模型费用／资金费／实收返现分开，净额、未闭合／缺失、亏损、最大单笔损失、右尾、占仓及原SOR贡献。禁止把固定历史交易集合当已重演动态容量补位。
- **完成：**baseline复现、无未来数据、同根顺序／数据缺口披露、所有数量差异解释清楚；亏损不自动否决有界实盘，数量／权限／保护错误必须阻止发布。

### ME-08：固定候选认证、审查与发布准备

**目标：**人工版独立精确证据，不复用东京SHA／schema／账户证书。

- **依赖：**ME-01—07；ME-04是强制前置，不以自动版partial测试替代。
- **工具：**当前人工版 `certify_release_candidate.py`、Owner API／static认证、独立manual安装与promoter。调用前读当前CLI／合同，不猜测生产参数。
- **验证：**Focused→Fast→冻结一次完整Release；unit/integration/full-chain/architecture/Ruff/Mypy/diff、现行Golden／parity、空库重建、终态源forward保全、实际调度／lease／故障演练、API/UI配置验证。无新行为时复用同SHA证据，不每个小改跑完整R4。
- **审查：**所有新交易所写经过同一管理权与耐久命令门禁；旧hash／Owner控制保全；六退出＋三Gate原子；真实R与50%上限；MANUAL不可逆；首次保护安全、残单不误释放、无第二ENTRY／账本／运行fallback。
- **交付：**候选清单、源／目标结构、参数包、账号／服务作用域、完整测试与保全结果、部署／失败恢复步骤。代码变更后旧证书失效；数量和存在的文件不构成通过。
- **完成：**全部软件门禁有准确证据，剩余自然触发与Owner真实控制单列；本轮文档中的复选项不提前勾完成。

## 4. 关键测试矩阵

### 4.1 数量与真实R

| ID | 场景 | 必须成立的结果 |
|---|---|---|
| **V01** | BTC0.019／0.007 floor为0 | 最小合法提升，实际5.263%／14.286%被准确显示 |
| **V02** | q_tp恰50%／超过50% | 恰好允许，超过拒绝，不截成不合法50% |
| **V03** | minNotional／maxQty／步长／tick／Runner不合法 | 使用正确类型当前规则，结构化拒绝；不扩大Q |
| **V04** | ETH／BNB足够大、SOR原比例 | 不做无必要提升；SOR只改1.2R，不改算法 |
| **V05** | 参考价不同VWAP、LONG／SHORT | 新TP准确实际1／1.2R；原Ticket不改 |
| **V06** | 重复／乱序完整ENTRY fills、重启、计划落库失败 | 一票一计划；不重复TP／ENTRY；AUTO安全收敛 |
| **V07** | ENTRY partial／unknown、初始保护失败／提前干预 | 原交付前安全职责与管理权均被验证，无盲补原Q |

### 4.2 部分TP与管理权

| ID | 场景 | 必须成立的结果 |
|---|---|---|
| **V08** | F=0／部分／完整 | 部分不BE且原guards继续；完整一次事件，新保护确认后Runner |
| **V09** | partial后保护数量超配、stop与TP并发 | AUTO保留／替换有真实依据，无唯一保护先撤空窗 |
| **V10** | 1R前、partial后、满额同批确认外部操作 | 全票永久MANUAL，真实TP可记账但无新增BE／Runner |
| **V11** | 命令准备后／claim未发时接管 | 不适用命令失效；零新增venue写 |
| **V12** | 替换已发送未知／确认待撤旧单时接管 | 精确结果只读归档，不盲重发／撤旧单；Owner拥有残单 |
| **V13** | 系统TP／stop／algo子单、新实际比例与保护数量 | 由准确Command／基线证明，不误判为Owner |
| **V14** | 真外部同ID改单再改回、未成交外部退出单 | 有效动作即永久接管，不靠最终价格相同洗回AUTO |
| **V15** | 采集失败／重连／PG提交失败／健康租约失效 | 不伪造连续性或应用成功；新增普通自动写受限 |
| **V16** | REVIEW后到价／配置激活／Owner Resume | 不因这些事实恢复自动处置或宣称已人工 |
| **V17** | MANUAL零仓＋残单／unknown／过期零仓 | 占用保留；无自动清理；准确新证明后只读收尾 |
| **V18** | 接管后旧TP自然满额、重启、配置回退 | 只记真实fill／经济，不恢复AUTO；释放恰一次 |
| **V19** | 原止损／系统退出部分成交、F超目标／余量矛盾 | 自身执行对账与真实外部干预分开，不把减仓都当Owner |

### 4.3 MA50、控制与首尔发布

| ID | 场景 | 必须成立的结果 |
|---|---|---|
| **V20** | 50根不足／缺／重／未来／未闭合／相等 | 三LONG无新增许可，数据错误与非bullish分开 |
| **V21** | Owner偏多但MA失败，偏空但MA通过 | 前者仍拒绝；后者继续原收紧预算，不生成SHORT |
| **V22** | 新4h边界／规则切换／签名过期 | 最新有效事实与当前版本重验，不能陈旧发送 |
| **V23** | BRF2／SOR／人工仓未知风险／同标的相反侧 | 只免MA，其他预算／管理风险／互斥仍生效 |
| **V24** | 预览后版本变化、六绑定／三Gate中途失败 | TOTP／expected revision／幂等正确，原子全成或全败 |
| **V25** | 已有AUTO／MANUAL票时仅切新参数 | 老Profile／计划／管理权不变；暂停策略不恢复 |
| **V26** | Owner创建合法新Profile／非法PG额外Profile | 合法受支持revision不破坏认证，非法／越界仍拒绝 |
| **V27** | 初次迁移仍有AUTO／REVIEW／MANUAL持仓 | 不迁移、不交接；保留准确旧源责任 |
| **V28** | MANUAL残单挡Drain、维护fence代替Owner暂停 | 无代平／代撤、无伪Owner授权；说明实际阻塞 |
| **V29** | 终态源／Owner审计／hash保全、旧writer误启动 | 历史保全、身份fence、单writer；不放宽门禁 |
| **V30** | UI显示14.286%／接管／保护未知／缺费用 | 不显示固定5%／95%、不虚报保本／净收益；平台接受不等于已读 |
| **V31** | 无信号、稳定MANUAL／健康接收 | 有界当前投影、无重复事件刷屏、零运行JSON／Markdown |
| **V32** | 全程AUTO闭环和实际App接管闭环 | 分别留准确自然证据，无测试订单／伪造事件；未出现即未验证 |

重复、stale、拒绝、unknown、partial、timeout、wrong identity和提交点崩溃按受影响边界注入，不机械复制同类用例。每个有状态场景同时验证一票一ENTRY、MANUAL不可逆、同标的跨侧互斥、预算无重复释放。

## 5. 首尔服务器发布手册

### S0：只读preflight与资格

通过人工产品正式只读通路核实目标host/product/account/venue/PG/system、代码／schema／依赖／seed、Owner策略与方向／Selection／预算、当前Profile／Gate、所有非终态票／预留／命令／Incident，以及交易所双侧仓位与普通／条件订单、交易规则。区分AUTO／REVIEW／MANUAL的退出责任，读取真实在途命令。

核对当前人工候选认证与source兼容，现有前端独立版本及API契约不被旧候选覆盖；不复制东京凭据／证书／迁移编号，也不把15:23样本或历史余额写成当前配置。当前部署快照只更新[人工路线图][M1]。

### S1：真实Owner暂停及自然Drain

1. 沿人工版正式控制要求取得**真实Owner暂停新入场**及其PG授权／版本证据；已有有效暂停就核对复用，不重复询问。维护写围栏、停Entry进程或直接改库不能代替Owner暂停。
2. 保存原控制与恢复意图，按正式协调器设置维护fence。Observation、Lifecycle、Reconciliation及其管理接收继续；AUTO旧票按原冻结合同保护／退出，MANUAL只读同步，REVIEW核实。不能关掉接收后继续允许普通AUTO写。
3. 不为赶发布强平、伪造Signal、人工标终态、将MANUAL改AUTO、自动撤人工残单。**MANUAL仓位的自然结束依赖Owner真实管理**；若确有人工仓／残单阻塞，提供准确对象／事实／所需操作，仅请求Owner关闭或清理其自身管理范围。
4. 原Owner受控全平也不能绕过MANUAL禁令，不能把发布Drain伪装成新全平功能。退出后PG与venue残单／命令／占用／结算均需核实。
5. 若源版本已有partial TP／unknown／归属缺口阻塞，先依原正式恢复路径解决。需要同schema工程修复时单独定义及认证，并遵守该源版本安装门禁；**不泛化旧MA-R2精确外部flat白名单恢复例外**。没有合法路径就保持围栏和旧保护责任，不能以新schema交接活动仓位。

### S2：最终终态清洁、停止writer与保全

PG与交易所同时证明：所有产品相关仓位0、普通／条件残单0、非终态Ticket0、活动预留／标的占用0、未知／待执行命令已收敛、必要Settlement／Review完整、开放Incident已按准确事实处理。经济缺口可以如实unavailable，不能以填零消除门禁。

通过后停止所有会写PG／venue的四Worker及其内部循环、Owner API和其他已定位writer，确认不在运行。**停止后重新读取账户／PG／控制／订单及源版本**；生成全源表／列／行保全摘要和现行合同所需可核验备份／恢复材料。当前新外部订单、Owner操作或身份漂移使快照失效，即停止迁移。

### S3：单线前向迁移与独立安装

使用[人工独立安装器][C1]及其经本次适配的正式phase，新增迁移从人工工程实际head开始；扩展结构转换与保全清单，不编辑旧迁移或用东京发布器。保留终态交易、不可变Profile／绑定、管理权、订单证据、Owner授权／控制和已知命令历史。

source／target保全比较通过才提交runtime identity，核对product/account/commit/schema/capability一致，旧writer不能同时可写。先安装能力和未激活候选配置，Owner仍暂停，先恢复具有准确身份的四Worker／Owner API及管理接收，验证权限与新epoch／应用水位。源绑定尚不属于目标已认证可运行组合时继续阻止新票。

本次涉及内核／schema／Owner API，不能用[纯静态前端发布器][C2]冒充整包升级；同时保留已有前端成果。代码、API与静态产物各有精确版本／证书和兼容证据，不能把UI版本误写为交易内核身份。

### S4：组合正式激活与真实恢复

按本人工版冻结参数通过Owner正式预览／TOTP／幂等控制，原子提交**六退出绑定＋三MA50绑定**及配置包审计；读回每个hash、规则revision、scope和算法。操作只激活新配置，不改变原策略暂停、方向、Selection、预算或旧票管理权；原暂停策略标明“配置就绪、策略未运行”。

管理接收ready且持久／应用水位、就绪事实、风险与账户／代码schema门禁全部通过后，执行官方promoter准备恢复；**真实Owner Resume／TOTP**单独成立，程序不得代为生成。此前有恢复授权也要确认它适用当前政策／控制版本；不得拿旧已暂停的Policy授权放行。

Owner恢复后只读核实授权、当前policy与运行状态；如果尚无自然信号，说明资格已恢复、自然链路未观测，不强制下单或重放暂停期间的close。未来受支持同schema仅切参数绑定不重复停机迁移，但仍需正式版本／授权及行动时验证。

### S5：自然AUTO与实际App分开验收

| 验收层 | 允许声明 | 必须证据／边界 |
|---|---|---|
| 文档适配 | 人工版设计与计划完成 | 本文、设计及链接／边界检查；不是运行能力 |
| 工程认证 | 精确候选可发布 | 独立SHA/schema证书、迁移／故障／管理权交错完整测试 |
| 安装／配置／恢复 | 首尔已安装、配置激活、Owner恢复 | 三者各自现场身份／原子绑定／真实授权及控制保全，不合并猜测 |
| 自然AUTO闭环 | 该自然新模式交易已自动闭环 | E/Q/S→计划→实际比例→准确TP fills→BE确认→Runner→残单清理→终态／释放／Review |
| 实际App接管 | 该真实交易已接管并合法只读闭环 | 外部有效操作证据、MANUAL永久、后续无自动写、实际余量／残单／命令终态与一次释放 |
| 策略经济／通知 | 前瞻结果或平台接受／手机到达 | 实际成本覆盖、自动／接管分层；平台与手机证据分别成立 |

自然样本没有partial、未触及TP、Owner未实际干预或通知手机回执不可得时，逐项保留未观测／未验证。本地完整反例不依赖真实资金制造故障；也不因未发生自然App操作就额外要求先下测试单，或恢复旧的“App验收前不得开放ENTRY”序列。

## 6. 中止、故障与参数回退

| 状态 | 合法处置 | 禁止处置 |
|---|---|---|
| 迁移前失败 | 保留ENTRY围栏；符合原身份／源schema时恢复旧安全worker责任，继续AUTO保护及MANUAL只读 | 隐式恢复新ENTRY、改管理权或放宽源门禁 |
| 迁移后失败 | 保持受限，准确目标schema下fix-forward，核实当前保护与责任 | schema降级、启动旧schema writer、清库或第二链 |
| AUTO数量／保护错误 | 原准确Incident、Reconciliation及有权安全关闭；限制新增风险 | 重发unknown、先撤唯一保护、扩仓追回 |
| MANUAL数量／保护／残单异常 | 只读记录、告警、保守占用；需要时说明Owner准确操作 | 程序代平、代撤、重挂或恢复AUTO |
| REVIEW／结果未知 | 核实准确订单与已发结果，保留缺口和受限状态 | 以到价／配置／时间流逝补造许可 |
| 配置效果不佳 | 正式新revision切回已认证可运行组合或显式关闭Gate；新旧票分离 | 偷改旧计划、自动取消MA50、持仓临时改TP比例 |

预算内亏损不是软件失败。遵守当前有效实验资金／期限边界，不新增全账户永久每日熔断；无新授权不扩大资本或杠杆。参数回退不能把MANUAL交回AUTO；当前schema内恢复“原参数”必须明确其价格基准和算法，不把历史hash套入不同执行语义。

## 7. 研究与运行证据

复用东京方案的**首批10笔／30笔终态及30日**作为可选报告观察点，分别统计全程AUTO和接管样本；它不是显著性条件、自动停机条件、强制凑单任务或本轮创建的监控。若已有有效期限／损失边界更早，沿用其规则，不凭文档发明亏损额度。

记录MA50拒绝与原始Signal、Owner方向／预算阻塞、配置revision、实际R与比例桶、TP后反转、Runner尾部、保护／unknown时长、残单、gross／fees／funding／实收返现及证据完整性。接管时间／阶段／成交／在途命令单列；不能把人工最终盈亏全部归给自动退出策略。

上线前后比较、同cohort反事实与组合样本变化各自披露；研究数据不准反向授予资金权限。经济负值／证据不足可以成为合理结果，工程正确性不能由少数盈利替代。

## 8. 工作完成与证据账本

- [ ] **ME-00** 人工基线、来源差异与所有写入口冻结。
- [ ] **ME-01** 数量／版本／执行计划数据合同与终态forward保全。
- [ ] **ME-02** 实际完整入场R、初始保护、管理权前置及计划失败职责。
- [ ] **ME-03** TP部分／满额、连续保护和Runner故障恢复。
- [ ] **ME-04** 管理权交错、自身基线、MANUAL只读闭环与不可逆性。
- [ ] **ME-05** 三MA50资格及Owner／final-send交集。
- [ ] **ME-06** 参数预览／TOTP／六退出三Gate原子激活、UI／通知。
- [ ] **ME-07** 精确最小提升50%算法回放与人工版分层。
- [ ] **ME-08** 独立固定候选、完整Release／迁移／API／静态认证。
- [ ] **S0—S3** 首尔现场身份、真实暂停、自然Drain、最终flat和安装保全。
- [ ] **S4** 组合配置读回、原控制保留、官方promoter与真实Owner恢复。
- [ ] **S5** 对应自然AUTO／App／经济／通知证据分别登记。

**本轮均未执行以上复选项。**仅交付文档和引用／权威边界检查，代码、测试新增、数据迁移、服务器部署与参数激活均不因本文自动发生。未来状态只在[人工路线图][M1]更新，单项产物附其真实来源和局限。

## 9. 来源

[D1]: ../specs/2026-11-10-manual-exit-regime-release-design.md
[M1]: ../../current/MAIN_CONTROL_ROADMAP.md
[C1]: ../../../scripts/trading_kernel/install_manual_host.py
[C2]: ../../../scripts/owner_console/deploy_manual_static.py

- [人工版设计与源码／研究来源索引][D1]。
- [东京原实施方案（只作适配来源）](/Users/jiangwei/Documents/final-strategy-research/analysis/2026-11-10-tokyo-exit-regime-release/实施方案.md)。
- [人工Owner运行模型](../../current/OWNER_RUNTIME_OPERATING_MODEL.md)、[工程约束](../../current/AI_AGENT_CONSTRAINTS.md)、[主链实施合同](../../current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md)。
- [原人工业务决定](../specs/2026-11-06-app-manual-takeover-v1-owner-decisions.md)、[MA-R2归属与收尾设计](../specs/2026-11-10-manual-order-attribution-repair-design.md)。
- [双产品工作区政策](2026-11-08-two-product-workspaces.md)、[首尔独立安装方案](2026-11-08-manual-new-host-installation.md)。继承的[部署安全基线](../../current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md)不授权东京操作。
