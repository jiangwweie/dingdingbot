# MA-NATURAL-CLOSE-01：自然退出、审核收尾及诊断补全修复方案

日期：2026-11-11（Asia/Shanghai）。适用产品：首尔人工接管版。

## 1. 决策与本轮交付边界

**目标：自然止损／止盈已结束真实仓位后，准确识别系统退出，沿既有 Kernel 完成对账、结算、复盘和一次性预算释放；修复当前受阻票，并防止新票重现。**

本轮交付为方案与验证设计，未开始本方案编码、测试、部署或生产恢复。实时生产状态只由[主路线图][R]及行动时 PG／交易所事实确认，本文引用的巡检属于已记录窗口证据。

**不需要重新决定交易参数。**保持现有 TP1、MA50、资金／杠杆、策略启停、Selection 和人工接管规则。MANUAL 永久禁止程序改单／撤单／平仓；REVIEW_REQUIRED 禁止未证实归属的自动交易，但不能永久阻断已有确凿证据的只读收尾。

采用 **同 schema 修复与限定恢复模式 → 当前票收尾 → 正常运行身份恢复**。优先复用现有0021事件／诊断／命令／复盘存储，不添加第二套账本、服务或 SQL 补账程序。若实施时发现必须新增数据库结构，立即拆分阶段：先交付可在原 schema 安全收尾的最小恢复候选；只有全部真实及内部状态终态清洁后才另行前向迁移。禁止在活动票上顺便迁移。

## 2. 已知事实与尚未证明的内容

### 2.1 已知客观事实

来源：[巡检报告][E]、其中准确订单／成交、安装版本 GET-only 复现和纯本地事件回放；当前源码入口见§12。

| 边界 | 已确认事实 | 工程含义 |
|---|---|---|
| 实际退出 | ADA 原系统止损父单关联准确 MARKET 子单，四笔成交合计等于完整入场量；TP1未成交并自然 EXPIRED | 已有可核验自然退出证据，不能当成人工撤单 |
| 现存投影 | 内部 REVIEW_REQUIRED／position_protected 保留旧数量、保护字段和预算；存在账户级生命周期事故 | 新准入受到真实阻断，不是显示错误 |
| 管理证据 | 全票历史与当前覆盖完整；使用真实命令基线分类 TP 失效，stream／REST均为 NATURAL | 管理证据已到达，生命周期未使用同一结论 |
| 生命周期 | TP terminal/unfilled 默认归属 unknown，产生审核；空仓后强制读取持仓mark，准确抛出缺价错误 | 两个独立缺陷叠加 |
| 恢复路径 | REVIEW 对账直接 NO_CHANGE；clear白名单不包含本次reason | 仅修适配器不能释放现有票 |
| 下游影响 | 后续 SOL 候选被 account_health_blocked 拒绝；ADA认证和事实刷新连续失败 | 需验证整个账户／品种恢复，不能只让单个函数不抛错 |
| 发布工具 | 普通安装要求终态；旧单票恢复入口也要求无开放事故，旧closure用例要求外部退出 | 现有命令不能原样用于这次自然止损恢复 |

### 2.2 证据限制

- 当时并发读取的完整生命周期 HTTP 元组未保存。代码分支和实际事件支持“旧仓位响应＋新TP终态”的竞态路径，本地已复现；不能声称逐包还原了当时全部响应顺序。
- 毛实现损益可以由准确成交算出；全费用后净损益仍需 BNB 估值与资金费证据，不能填零。
- 历史 DOGE 的发送前 margin_drift 缺少当时完整数值；新代码只能补未来留存，不能补造过去。
- 早先成功开仓、止损和TP挂单不等于自然退出闭环通过。现有测试缺少本次跨接口竞态与已审核空仓收尾组合。

## 3. 设计选择

| 选项 | 可解决内容 | 风险／代价 | 决定 |
|---|---|---|---|
| 全面解除REVIEW或改成AUTO／MANUAL | 表面解除卡票 | 恢复不应有的写权限或伪造Owner干预 | 禁止 |
| 只去掉空仓缺价异常 | 降低一个报错 | 审核对账仍返回NO_CHANGE；旧票仍卡住 | 不充分 |
| 给旧BNB恢复加宽松例外 | 绕过安装阻塞 | 原路径只支持外部退出，且拒绝当前开放事故 | 不直接沿用 |
| 同一归属证据＋确证退出事件＋限定只读恢复 | 修复未来执行和当前卡票，保留权限与审计链 | 需增加纯域证明／事件、发布门禁及竞态验证 | **采用** |

**运行所有权：**Lifecycle仍负责AUTO保护和退出命令；Reconciliation负责准确退出证据、只读收尾、结算与Review；管理观察保留归属采集职责。维护恢复入口只调用同一收尾用例，不成为第二个长期worker或第二套核算器。

## 4. 正常运行修复

### 4.1 统一TP终态的归属与处置

替换目前 `tp1_terminal_attribution='unknown'` 默认值驱动管理权变化的方式。建立冻结的 typed 终态事实，至少包含：

- product／venue／account／instrument／positionSide；Ticket、管理revision、配置／Profile冻结身份。
- durable Command、regular／conditional namespace、clientOrderId、准确父子订单及持久基线引用。
- 订单状态、累计成交量、最后事件时间、采集时间／有效期、分页完整性、证据摘要。
- 分开表达 **归属**（system／natural／external／unresolved）和 **处置**（仍在持仓、待复查、已确证退出）。

复用 `command_rows_for_order`、`system_intents_for`、`child_system_intents`、`classify_order_evidence`；不能在Lifecycle复制一套更宽松分类器，也不能只凭 `brc-` 前缀或 expired 字样认领。

| 实际状态 | 允许结果 |
|---|---|
| 自身TP自然终态、退出证据尚在到达 | 保留已存在保护，安排有界新鲜读取／对账；不因一次非原子组合认定人工干预 |
| 自身止损／其他准确退出已全量成交，空仓无残单 | 进入§4.3确证只读收尾；不补挂TP、不改止损 |
| 自身TP终态、仍有真实余仓且归属已证实 | 按冻结策略与已有AUTO故障处置合同处理；保护持续有效，任何新增写仍走durable Command及最终管理权核验 |
| 已确认外部改／撤／退出 | 永久MANUAL，保留现有只读核算／收尾；禁止自动补TP／平仓 |
| 证据缺失、订单身份冲突或未知结果 | REVIEW并禁止自动写；保存具体阻塞原因，继续精确只读核验 |

### 4.2 空仓与持仓事实要求分开

`read_lifecycle_facts`先识别真实持仓数量及证据完整性，再按用途采集：

1. **非零仓位**：保护／Runner所需价格、规则、费用边界保持严格；缺价仍明确拒绝，不回退为0或过期价格。
2. **零仓位候选**：无需从不存在的持仓行提取mark；读取准确退出成交、普通／条件订单、未知命令及当前仓位证明，交给Reconciliation核实。
3. 一次zero或空列表不是完整关闭证明。缺分页、超时、错误account／side、未解决命令、残单、迟到成交均阻止释放。
4. 并发接口分别带采样时间。position、TP、stop返回跨退出时点时，结论为 `exit_snapshot_inconsistent`／待重新核验，不立即改变管理权。准确订单状态和仓位重新读取得到一致证据后才推进。
5. 网络I/O全部在PG事务外；不通过延长TTL或放宽数量守恒让矛盾通过。

### 4.3 统一“已核实退出”证明与事件

在现有Kernel内增加 **VerifiedExitClosureProof**（工作名）及唯一收尾用例；运行与维护恢复复用。不是把旧外部单closure校验直接删除，也不是新建平行运行链。

**证明必须包含并校验：**

- 精确产品／账户／净额域／Ticket及expected aggregate version、management revision。
- 完整真实入场与退出fills，准确trade IDs、订单身份／父子链接、方向、窗口及来源；严格数量守恒、跨源去重、重复冲突拒绝。
- natural_system_exit、verified_external_exit等明确证据来源；管理权不由损益或“少了多少仓”推断。
- 所有已接受命令订单及其实际子单的终态清单；当前普通／条件残单为空；prepared／claimed／dispatch_started／outcome_unknown均已解决。
- 订单原始委托量和实际成交量分开。TP部分成交后止损可能只退出余量，不能把“止损actualQty必须等于最初全仓委托量”当作通用关闭条件；原命令条款身份仍须完整匹配，最终以所有准确退出fills总量守恒判定。不得简单放宽现有algo解析器而取消身份／数量验证。
- 新鲜、完整、相互一致的最终仓位读取；限定恢复阶段还需全账户空仓／无订单。确认退出后再采集最终仓位与残单，提交前验证有效期；任一新活动／证据变化使证明失效。
- 具体准许解决的因果Incident IDs／kind／Ticket／旧版本与新证据，拒绝不相关事故。不能笼统清空事故表。
- 先前管理原因和证据引用、采集范围、hash及每个失败阶段，保证后续能重放为什么允许收尾。

**持久化与状态转换：**

- 使用现有 `brc_trade_events` 的append-only payload保存冻结证明与摘要，复用既有管理证据／命令／Review。新事件名工作名为 `VerifiedExitClosed`，由纯域校验器校验证明，由原UnitOfWork提交reduction。
- 新事件仅在证明全量退出、无残单、无未知命令时推进到 `SETTLEMENT_PENDING`，更新已证实归零的仓位、保护及订单投影；复用 `ReleaseCapitalAuthorities` 的原子一次性释放，并仅解决准确因果事故。
- 当前 `ResolveTicketIncidentsAtClosure` 具有按票批量解决语义；新恢复路径必须改用包含准确事故IDs与expected状态的typed effect，不能复用它来清理未证明相关的事故。提交前锁定并比对事故集合，新出现的无关事故使事务拒绝。
- **AUTO／MANUAL／REVIEW管理模式均不因收尾恢复为另一模式。**记录closed证据引用；旧审核原因保留在不可变前序事件与证明中。收尾不会生成交易所命令。
- reducer对REVIEW只允许经过该证明事件、正确前置状态与证据引用的 `BudgetSettled／ReviewRecorded` 等纯会计后续；不通过放开总的management guard使其他事件通过。
- 证明引用落在现有可存储字段／事件链；禁止只给内存Aggregate加字段却不持久化。实施前核对从PG加载与事件重放两条路径一致。若无法在原schema准确承载，按§1先完成同schema最小恢复阶段，另立终态后迁移，禁止运行fallback。
- 原 `ExternalFlatDetected` 会生成撤保护命令，**不能作为已无残单的REVIEW只读收尾捷径**。已有AUTO残单清理继续按旧权限处理；MANUAL／REVIEW残单不代撤。
- 定位并修正 `review_window`、退出归因和Owner完成投影的事件识别，防止新事件已终态但经济计算窗口／止损原因再次丢失。

**幂等／并发：**同一Ticket与证明摘要、expected predecessor在短事务内原子校验；锁票后重核命令和事故集合。重复调用返回已提交结果；不同证据不能覆盖原证明。崩溃／并发时不能重复事件、结算或预算释放。

### 4.4 经济完整性与流程终态分别处理

- 当前未终态ADA首次Review属于正常收尾，不伪造历史修订。准确系统stop子单进入既有order_attribution／Review计算，不伪造Command。
- 原始BNB费用、准确时点估值、资金费归属使用既有核算合同；缺失时终态明确 `economics incomplete`，不填0、不拿当前BNB价代替历史费用价。
- 最终空仓与订单／命令完全解决后，费用不可得不应永久占用风险预算；但UI必须写明“交易已收尾，经济证据未完整”。
- 已终态旧票的Review revision仍需准确预览及真实Owner批准；本方案不批量重写以前的四笔缺口。
- 现有自动补证据入队只识别 `external_exit_unavailable`。新增自然退出的费用／资金费缺项必须纳入同一typed完整性与有界队列选择规则，避免改了reason后永久不再补证据；队列只生成预览，任何已终态经济revision仍需原审批。

## 5. 诊断、调度和展示补全

### 5.1 具体原因留存

复用0021 `brc_failure_diagnostics` 与现有命令结果，不新建日志权威。生命周期、管理归属、退出确认、发送前拒绝各有稳定stage／reason_code，禁止仅存RuntimeError或把异常类别一律视为业务矛盾。

建议代码：`protective_mark_missing_nonzero`、`exit_snapshot_inconsistent`、`known_tp_terminal_pending_reconciliation`、`exit_identity_unproven`、`closure_residual_orders`、`closure_unknown_command`、`closure_quantity_mismatch`。最终枚举由代码合同统一，不由前端猜异常文本。

发送前margin_drift保留冻结reserved_margin和三个action-time限制：单票margin limit、available margin、gross remaining margin及命中子限制；钱包、policy／rule／snapshot版本、采样时间、父信号／Ticket／Command作为因果引用。失败结果与诊断同事务提交，事务前采集网络事实；不以较早admitted的AdmissionDecision冒充发送前拒绝快照。

沿用既有大小界限和字段白名单，不输出DSN、API keys、签名URL或第三方原始异常。后续成功不能覆盖失败历史；历史缺失继续unknown。

### 5.2 审核票调度与反复失败

- 管理模式检查前移。REVIEW／MANUAL不再重复调用仅为AUTO改止损所需的完整市场／费用采集；由同一个Reconciliation cadence收集恢复／收尾必需事实。
- 每次有界处理一票，准确ID查询；命令unknown及真实非零仓安全职责优先。当前保护／仓位采集频率不因告警降噪而放慢。
- 对已证明flat但证据尚缺的重复历史取数，按故障类型使用现有调度机制与封顶退避；新stream证据、管理revision或unknown结果变化立即唤醒。相同状态不重复产生Owner告警／新事故。
- 不通过停止整个Reconciliation、吞错误或删诊断降低失败次数。后台查询、每票订单／分页／交易条数与timeout采用当前已认证界限，超限返回explicit incomplete。

### 5.3 运行状态与通知

统一展示四个不同事实：**交易所实际仓位／残单、内部流程／预算、采集连续性、管理权／收尾阻塞**。本次形态应显示“交易所已平仓，内部收尾待恢复”，不能显示仍受保护的真实仓位。

`position_reconciled`不再覆盖实际NO_CHANGE／REVIEW阻塞；事件／状态无进展时显示对应原因。通知按实质转换：一次待审核、一次确证关闭、一次经济补齐；只有证据证明后才报恢复，通道accepted不等于手机收件。

将本地5412950b的配置GET只读连接和升级SELECT刷新纳入候选验证；作用域限定原声明读取权限，写授权／TOTP不扩张。

## 6. 当前受阻票的安全恢复与上线

### 6.1 为什么旧恢复命令不能直接用

源码核对：`require_stopped_upgrade`和`_require_management_recovery_activity`拒绝所有开放Incident；本次有准确因果事故。`recover_readonly_closure`又要求外部exit且通过外部证据推进MANUAL，无法用于自然系统止损。**不得直接运行旧脚本、清事故来过门禁，或把自然退出伪装成人工退出。**

本方案审批项包括下面的**新限定恢复合同**。这是待编码认证的能力，现阶段尚不存在可直接使用的安全命令。

### 6.2 R0：本地候选与真实源演练

1. 单实现者复用focused人工分支；保存原窗口脱敏HTTP／WS及真实事件，先RED再实现。Tokyo不在写入范围。
2. 在独立manual PG恢复一份新的只读生产导出，保留原非终态票／事故／数量／预算，不人工清理源状态。
3. 候选same-schema安装演练保留全部源列／行；只有进入新的限定恢复模式后，由§4.3同一用例正常提交新事件和投影。
4. 显式传入本次准确Ticket、净额域、source／target SHA、schema、expected version及精确因果Incident IDs。**CLI票号不是通行证**：还必须匹配下述业务证据。
5. 完整认证与演练通过后提供安装／恢复预览。此阶段生产只读，不提交命令或会计变更。

### 6.3 R1：行动时门禁与限定安装

必须同时满足：

- 当前首尔host／product／account／DB system ID、源SHA／schema与证书准确；目标固定SHA三证齐全。
- 真实Owner暂停新ENTRY有效；Policy仍开但被incident阻塞不满足此条。
- 全账户venue双侧仓位0、普通／条件订单0；仅有目标准确非终态票；内部旧非零仓位全部归属于该票且与故障证明对应，不能把其余仓位忽略。
- 已知原止损父子单、完整退出与入场量守恒；TP未成交自然终态；无外部人工干预证据或其他归属冲突。
- 未决命令0、lane idle；开放事故集合**只能是预览绑定的本票本故障因果事故**，且具体事故原因由新证据说明如何解决。任何额外／变更事故拒绝；源事故一直保留到reduction确证关闭时。
- 先设置ENTRY维护围栏，停止全部写进程，停后重复PG＋venue核对；生成最终备份、源表／列／行及控制摘要。远端最终读取或源版本漂移即停止。
- 同schema正式独立安装器支持**限定恢复模式**，capabilities全部disabled，记录准确恢复scope；不启动普通worker／API，不借旧通用开关放行真实持仓升级。仍复用现有正式安装锁及身份／保全检查。
- 新合同明确区分“有源事故的精确flat恢复”与原普通升级；普通升级门禁保持原样，不删去全局incidents检查。
- 恢复scope中的Ticket、事故集合、source／target身份及expected版本在正式身份事务中绑定并持久化；本地参数／报告本身不能授予权限。恢复执行再次从PG读取该绑定并与新鲜venue事实核对。

### 6.4 R2：限定只读收尾

1. 一个维护调用负责串行执行；停止服务后才运行，transport强制仅GET，无可用venue write port。
2. 先preview：新鲜取证，返回准确订单／成交、将追加的事件、将解决的事故、预算／内部数量变化、费用缺口与原策略控制保持结果。预览不保存生效结果。
3. 正式apply必须重新收集有效证据并匹配expected source version／scope／preview语义，不使用本地JSON作为运行权威。若状态已变，重新预览；不忽略未知变化。
4. 通过§4.3用例追加退出确证事件，正常推进原settlement／review，精确解决因果事故；无新ENTRY、撤单、改单、平仓或测试订单。
5. 验证目标terminal、真实与内部仓位0、无残单／unknown、预算与域释放一次、开放因果事故0、自然stop归因正确、原Owner及配置不变。
6. 每一阶段可重入，旧版本冲突拒绝；已完成返回原结果。任何失败保留ENTRY围栏与Owner暂停，不直接回写源状态。

### 6.5 R3：正常身份与运行恢复

全部终态清洁后，沿原正式runtime identity转换恢复正常运行能力（仍Owner暂停）；清除限定恢复标识须由同一正式身份流程完成，不手改capability JSON。启动正常服务并验证：

- 同一精确候选SHA／schema、源数据与Owner配置保全、仅一个writer集合；管理接收ready及持久／应用水位一致。
- ADA重新认证与事实刷新恢复，账户健康通过；新诊断不再持续追加同故障，未知历史不被改写。
- 配置v1六退出与三Gate哈希保全，无需Owner重新激活或重新选择参数；原策略暂停、Selection、方向、预算保持。
- 原正式只读认证、已安装事实探针和官方promoter通过；之后才请真实Owner Resume／TOTP。
- Owner恢复后只读核验新政策／授权／运行状态。旧被拒SOL／DOGE不重试，不重放错过的Signal；等待新的自然机会。

### 6.6 失败处理

| 失败阶段 | 保留状态与处理 |
|---|---|
| 本地认证／源演练失败 | 不安装；修正后冻结新候选独立认证 |
| 停机后发现新仓／残单／未知或额外事故 | 不迁移、不恢复收尾，展示准确新阻塞；不得代平／代撤 |
| staging／identity失败、尚无目标语义事件 | 保持Owner暂停与围栏；仅在源身份及恢复契约证明安全时恢复源责任，不隐式开启ENTRY |
| 已追加新证明／退出事件后失败 | fix-forward或同候选幂等续跑；旧代码未必识别新事件，禁止盲切旧symlink或整库恢复覆盖新事实 |
| 已收尾但经济缺项 | 终态和预算释放保留；经济明确不完整，后续准确revision走原授权流程 |
| promoter／Resume后门禁不通过 | 保持／恢复官方围栏并报告具体原因；不改Owner权限以强行放行 |

## 7. 实施工作包与顺序

| 工作包 | 具体产物 | 依赖 | 完成标准 |
|---|---|---|---|
| N0 源证据与反例 | 真实事件／HTTP／WS脱敏fixture、跨接口响应顺序、原函数RED |本方案批准 |复现三条根因与旧恢复拒绝，不清理源数据 |
| N1 归属与空仓采集 |统一typed终态事实、准确归属复用、zero分支及采样一致性 |N0 |自然／人工／未知分别正确，非零缺价仍拒绝 |
| N2 确证退出与恢复 |冻结证明、纯域事件、同一reconcile→settlement→Review用例 |N1 |AUTO／REVIEW／MANUAL无越权，一次释放；当前票可只读收尾 |
| N3 诊断与调度 |lifecycle／dispatch stage-code-basis、mode-aware采集、准确UI／通知 |N1–N2 |不丢具体失败，安全检查不降频，持续失败无状态振荡 |
| N4 限定发布合同 |same-schema精确票＋因果事故门禁、preview／apply／正常身份恢复 |N2 |错对象／额外事故全部拒绝，安装前保全、恢复后可重入 |
| N5 组合验证 |包括5412950b，完整Release认证＋实际源演练＋安全复核 |N1–N4 |精确候选所有门禁通过，给出实际结果与剩余自然验收 |
| N6 现场收尾与恢复 |R1–R3证据、路线图更新 |Owner部署确认、暂停及所有行动时门禁 |正确终态、账户恢复、真实Resume且无测试单 |

不并发编辑reducer、schema、dispatch等共享权威文件；本方案不授权子代理。只使用本工作区`.venv`、`scripts/local/manual_pytest.sh`及独立manual PG。

## 8. 必须通过的验证矩阵

| 编号 | 场景／输入 | 必须观察的结果 |
|---|---|---|
| V01 |本次真实stop父／子单、四fills、TP EXPIRED，经当前CCXT |准确自然退出；无人工归属、无重复fill |
| V02 |旧position＋新TP终态；随后zero；先zero再晚到stop／TP |允许等待与重新取证；不永久误REVIEW，不伪造一致快照 |
| V03 |空仓position列表空／缺mark；非零缺mark |前者可取确证关闭证据；后者明确阻断保护写 |
| V04 |本次原前6events→误审核→完整自然退出证据 |原函数RED；修复后由原链terminal，管理模式不变，预算一次释放 |
| V05 |MANUAL且有确证退出／残单／unknown |只有flat清洁才只读收尾；交易所写次数0 |
| V06 |错account／symbol／side／namespace／client ID／父子链接 |拒绝；无投影／预算／事故变化 |
| V07 |成交重复／乱序／冲突／数量不守恒／截断／超时 |准确去重或明确incomplete；不按差额补成交 |
| V08 |stop部分成交，TP部分／完整，同tick；真实余仓非零 |不误终态；保护权限与生命周期依冻结策略；不重复BE或反向开仓 |
| V09 |人工撤TP／改单／外部退出与自身自然状态交错 |永久MANUAL；unknown不是Owner证据，不能用expired统统跳过 |
| V10 |获取证明后新残单、版本变更、命令unknown或proof过期 |提交拒绝／重新核验，不放宽TTL |
| V11 |在证据写入、投影更新、事故解决、预算释放、settle、review处崩溃 |短事务回滚或同候选续跑；事件与释放恰一次，无丢审计 |
| V12 |两个worker同时尝试关闭／恢复脚本重复apply |expected-version冲突或同一结果；无双释放／重复Review |
| V13 |相同RuntimeError外形但不同真实原因；随后成功 |typed stage/code可区分，历史留存；成功不覆盖失败 |
| V14 |dispatch分别命中三类margin限制、其他health gate |同事务准确子码与bounded basis；不影响原交易判定 |
| V15 |事件／UI／通知：实际flat、内部待收尾、经济待补齐 |四种状态分别显示；每实质转换通知一次，不宣称全恢复 |
| V16 |实际生产形态原schema导出，保留活动票及因果事故 |普通安装RED；新限定恢复只对准确scope通过；全部无关行保全 |
| V17 |额外票／额外事故／wrong commit/schema／Owner未暂停／旧writer活跃 |限定安装拒绝，不能变成通用例外 |
| V18 |恢复transport注入任何POST／PUT／DELETE |硬失败；真实及模拟exchange writes0 |
| V19 |旧终态票、原哈希、配置1、策略启停／Selection／方向／预算 |安装及恢复后保全；MANUAL不回AUTO，退休SOR不恢复 |
| V20 |真实read/control PG角色HTTP：读取／预览／TOTP／回执与升级后授权 |覆盖此前权限缺口；无TOTP拒绝，写权限不扩大 |
| V21 |完成全部终态、事故／预算释放后，正常身份／promoter |原认证与venue规则通过；真实Resume独立，旧拒绝不重发 |
| V22 |BNB费用有／无准确估值，资金费重叠／缺失，旧Review补齐 |经济完整性如实，无法估值不填0；历史修订需原Owner批准 |

**认证分层：**Focused RED/GREEN → Fast单元／架构／受影响PG／API → 冻结候选一次完整R4、API、静态认证、Ruff/Mypy/diff及现有数值一致性 → 精确实际源恢复演练。若复现暴露新行为变更，冻结新SHA重新认证。涉及调度的资源边界检查保持原CPU／内存／时限，不用放宽预算让测试通过；不对每次小改重跑整套。

## 9. 完成定义

### 9.1 本地工程完成

全部根因反例及§8通过；无旧错误语义测试、兼容读库／双写／第二执行链；候选证书精确匹配。当前票证明与恢复预览可审计，普通升级与限定恢复门禁分别有反例。

### 9.2 当前现场恢复完成

目标票terminal，真实和内部仓位0、无残单／未知命令，预算／净额域释放一次，准确因果事故解决；stop退出归因及Review证据完整或如实注明费用缺项。ADA认证／事实刷新与账户门禁恢复。原控制与配置保全，服务身份一致、无新增该故障，官方promoter与真实Owner Resume通过。

### 9.3 后续自然验收边界

本次恢复能证明“本票可安全收尾”；协议回放可证明已覆盖故障矩阵。新票自然止损／TP1部分与完整／BE／Runner／人工接管／终态及实际手机收件按真实发生分别记录，不用下测试单凑验收，不提前声称完整自然覆盖。

## 10. Owner需要确认或配合的事项

1. **业务参数无需再次决策。**本方案不修改TP1、MA50、预算、杠杆或人工接管规则。
2. **方案批准范围须明确包含N4限定恢复合同**：仅准确票及因果事故、真实全账户flat、same schema、全部writer停止、capabilities disabled、交易所GET-only。当前既有程序不能直接执行这一能力。
3. 本轮只出方案。批准实施后执行编码和本地验证；**生产安装／本票恢复apply前提交具体候选、证书、实际源演练和恢复预览供复核**。不把本方案文字当作已完成安装批准。
4. 发布前真实Owner暂停新ENTRY；完成收尾、认证与promoter后真实Resume／TOTP。已有动作须核对当前版本，未过期的有效授权不重复索取；代理不生成授权。
5. 按已记录巡检，venue无仓无残单，不需要Owner再平／撤。行动时若事实变化，提供准确对象与责任，不以旧截图推断。
6. 已终态历史Review修订仍逐票预览／批准；本次修复首次收尾不自动批准旧账重写。

## 11. 证据与权威关系

- [主路线图][R]：唯一生产身份、当前状态和剩余关键路径权威。
- [巡检报告与修复清单][E]：截至该窗口的现场事实、协议证据与复现；行动时须刷新。
- [前次运营修复方案](2026-11-11-manual-operational-closure-repair-plan.md)：本次补齐其未覆盖的生命周期／dispatch边界，不重开已冻结业务选择。
- [人工退出实施方案](2026-11-10-manual-exit-regime-release-implementation-plan.md)：参数、人工权限及正式发布／Owner控制基础合同。
- [双产品工作区政策](2026-11-08-two-product-workspaces.md)、[AI约束](../../current/AI_AGENT_CONSTRAINTS.md)：隔离、认证、单权威和权限边界。

## 12. 主要实现与审查入口

| 边界 | 文件／目录 |
|---|---|
| typed归属、证明、事件、Reducer | `src/trading_kernel/domain/trade_management.py`、`readonly_closure.py`、`events.py`、`aggregate.py`、`reducer.py` |
| 生命周期与收尾 | `application/maintain_ticket_lifecycle.py`、`reconcile_ticket.py`、`readonly_closure_recovery.py`、`settle_ticket.py`、`review_window.py` |
| collector／CCXT与准确订单 | `infrastructure/venue_adapter.py`、`binance_order_attribution.py`、`management_collector.py`、`readonly_closure_source.py`、`pg_management_repository.py` |
| 采集与调度／失败诊断 | `interfaces/lifecycle_worker.py`、`management_observation_worker.py`、`reconciliation_worker.py`、`application/lifecycle_facts_health.py`、`dispatch_exchange_command.py`、`domain/operational_evidence.py` |
| 恢复身份与正式安装 | `infrastructure/runtime_authority_seed.py`、`scripts/trading_kernel/install_manual_host.py`、`manual_host_bootstrap.py`、`manual_same_schema_upgrade.py`、`recover_manual_closed_trade.py`、`promote_entry.py` |
| 状态／通知／API | 现有Owner投影与notice policy、`interfaces/owner_console_http`、`frontend/owner-console-v2` |

[R]: ../../current/MAIN_CONTROL_ROADMAP.md
[E]: ../../../.local/manual-production-patrol-20261111-2024/巡检报告与修复清单.md
