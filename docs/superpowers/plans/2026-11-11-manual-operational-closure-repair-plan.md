# MA-OPS-CLOSURE-01：非数字格式缺陷补充修复与验证方案

## 1. 地位与范围

**Owner后续明确要求修复这些问题，F0—F5已进入本地实施，当前结果见配套实施证据。数字语义修复71bf139a已合入；部署及生产补账仍等待Owner明确确认。**未执行数据库迁移、生产补账或部署。Owner要求部署前等待确认仍然有效。已认证TP1／MA50候选不被本方案当作已覆盖这些缺陷；新SHA需独立重新认证。

本轮核对为本地源码、Git与另一工作区已有审计产物；没有重新在线读取首尔，审计中的生产数量与时间只作为对应窗口的历史证据，不声明当前持仓状态。无东京操作、无测试订单、无MANUAL代平／代撤。

## 2. 已知事实与证据边界

### 2.1 本轮源码核实

| 缺口 | 当前人工候选中的路径 | 判断 |
|---|---|---|
| App退出漏计 | `interfaces/reconciliation_worker.py` REVIEW_PENDING仅取`exchange_commands.list_order_references`；`domain/order_attribution.py`引用／成交都强制command身份 | 需扩展同一核算链的证据来源，不能伪造Command |
| 复盘告警振荡 | `application/reconciliation_health.py`按调用者阈值重算状态；core closure使用max(3次重试,review grace)，backlog复用worker failure window | 同一key存在不同阈值；updated_at又被当首次等待时间与通知时间 |
| 拒绝原因折叠 | `application/build_capacity_claim.py`健康失败和多种sizing失败返回budget_exhausted | 本次TP1数量算法保留部分refusal_reason，但没有覆盖所有health与sizing分支 |
| 止损提示失真 | `domain/manual_position.py`超量止损返回protected=0；`application/notice_policy.py`未将该原因映射unknown | 保守风险处理可保留；显示必须区分“存在但未核实”与“确定无保护” |
| 数字语义修复 | 已按Owner后续授权，以`c23d17ad`选择性cherry-pick原提交并保留当前schema | 初始36项及扩大回归2281项通过；Ruff／Mypy通过。原R4证书不自动适用于新SHA |
| 终态补证据 | `application/settle_ticket.py::revise_trade_review`与`ReviewRevised`已存在 | 复用追加revision，不改写历史、不二次Settlement |

### 2.2 生产窗口的历史证据

来源目录：`/Users/jiangwei/.codex/worktrees/manual-decimal-equality/final-manual/.local/nondecimal-audit-20261111/`。

- `review-replay.json`：原查询路径读取entry32811、系统TP退出16405，因缺App16406退出而抛`exit fill quantity does not equal Ticket quantity`。
- `health-replay.json`及`monitor-events.jsonl`：同一closure状态processing／needs_intervention交替，可由原函数本地重放。
- `findings.md`与`log-inventory.json`：DOGE认证／事实刷新传导、SOR新Session未就绪、废弃scope和Owner暂停分别分类。
- 1024次历史临时认证缺少逐次原因；19:00 BNB缺少原始sizing／health分支与行动事实。**不能靠代码修复恢复从未保存的历史。**最多用仍可取得的精确外部证据新增说明，不覆盖原缺口。

## 3. 修复原则

1. **交易管理权、订单执行结果、经济归属、流程终态、经济完整性分开。**MANUAL永久；经济补齐不恢复AUTO、不重新开仓。
2. 不把所有人工同品种成交归入Ticket；不使用“差多少就补多少”算法，不通过数量容差、账户盈亏差额或手续费填零掩盖缺口。
3. 网络读取在事务外；事实与决定在短事务原子提交。生产权威只来自PG与已核实venue证据；审计JSON仅用于本地回放。
4. 诊断证据逐次可追溯，告警按故障episode／实质变化去重。连续轮询不得重复创建相同故障通知。
5. 不新增服务、第二套核算链或schema fallback，不扩策略、预算、杠杆、Selection或自动操作权限。

## 4. 工作包与验收

### F0：数字语义修复集成与基线冻结（已合入，针对性回归通过）

- 按`71bf139a`准确差异移植三个边界：管理证据去重、手工订单投影比较、方向风险幂等请求。只忽略Decimal表达尺度，不忽略真实金额、价格、数量、时间／订单身份变化。
- 与新`PostFillExitPlan`、累计TP、actual-fill及管理revision交错验证，旧hash与原授权回执保全。
- **验收：**`16405`、`16405.0`、`16405.000`同值幂等；`16405`→`16406`是实质变化。原fingerprint不重写；同ID真实差异仍拒绝。

### F1：系统与外部退出统一只读核算

#### 数据与归属

- 在现有order_attribution／Review类型中引入显式来源：`system_command`或`verified_external_order`。来源为互斥typed分支；外部来源有evidence／核验身份，不需要也不得填造command_id。
- 外部候选从Ticket已绑定管理证据和准确venue只读订单获取；“该Ticket已MANUAL”本身不能证明该账户任意订单属于该Ticket。
- 每项至少证明：产品／venue／账户、instrument、positionSide、退出买卖方向、regular／conditional namespace、准确订单ID、订单创建与成交时间、对应Exposure Episode、管理证据ID和必要父子单链接。
- 系统已知订单后续由App改单／部分执行时，**同一真实订单只计一次**；执行归属与当前管理权分开。条件父单只证明实际子单身份，成交仅按实际子单计算。
- 按`venue+account+instrument+trade_id`去重并核对order／side；同键不同经济事实直接拒绝。跨源重叠不得双计。限制订单数、分页数、总行数和耗时；截断／冲突明确unavailable。

#### 计算与恢复

- 合并经核实的系统与外部退出fills，继续严格验证总退出量等于实际完整入场量；不修改该守恒校验。
- 手续费保留USDT／BNB原始数量与准确估值证据，资金费独立标记可得性；缺某项不能显示全费用后净收益完整。
- 活动／REVIEW_PENDING按原Reconciliation核算；已TERMINAL且economics不完整的票进入**有界、幂等补证据队列**，由既有Reconciliation负责，不扫描全部交易史。
- 先生成可复核补账差异：候选订单／trade IDs、旧新成交总量、手续费／资金费、旧新经济完整性和证据摘要。经准确事实核实后走`revise_trade_review`追加新revision，保留前版与完整来源。并发用expected current review及证据digest避免重复版本；不触发二次释放预算／二次Settlement。
- DOGE历史记录仅在上述身份、fills、费用与窗口检查全部满足时补齐；若外部订单／费用确实不可得，保留缺失。

**验收：**32811=16405+16406成立；新旧来源去重、外部改系统原单、多个App部分退出、迟到／重复／乱序／截断、条件父子单、错账户／symbol／side／时间／历史重叠、缺费用／资金费、已终态重复补齐均有反例。MANUAL过程中新增exchange write数为0。

### F2：统一复盘健康状态与通知语义

- 复盘closure采用**单一5分钟**窗口，沿用当前review economics grace；不再把通用worker的3分钟failure window传入closure。worker失联／死锁等独立故障仍保留自身阈值与key。
- 同一未解决故障episode：PROCESSING→NEEDS_INTERVENTION，未证实解决时不得回退PROCESSING；重启与两个入口交错不重置首次等待。
- 显式保存`first_wait_at`、`last_checked_at`、`escalated_at`、`resolved_at`及episode身份。通知使用实际状态变化时间，另显示已等待时长；不把首次等待冒充本次推送发生时间。
- 解决条件核对真实流程／证据，不以一次无候选或terminal状态直接表示经济完整。流程终态但经济缺失时文案为“交易已收尾，盈亏数据仍待补齐”；完整后才“盈亏核算已补齐”。一次恢复／补齐一次通知。
- monitor、持久化状态转换与outbox同事务；通知失败不影响交易权威，不制造重复state版本。

**验收：**在179／180／299／300／301秒交错调用两个入口，状态无振荡，同故障只升级一次；中断／重启不重置计时；升级／恢复通知时间准确；终态unavailable不被写成全恢复。

### F3：精确拒绝原因与行动时证据

- health拒绝分别输出账户管理风险、账户事实缺失、品种占用、订单冲突、认证／规则失效等真实typed原因。
- sizing保留count、gross／ticket stop risk、directional risk、margin、venue minimum、minimum materialization、exit split等原始码，不统一包装budget_exhausted。
- AdmissionDecision保留`stage`、`reason_code`、`source_reason_code`和有界typed basis：policy／configuration／规则版本、wallet／available margin、各风险额度与使用量、slot、Q与TP可执行性、health结论及对应证据IDs、observed／valid时间与运行身份。
- 证据在拒绝发生的同一事务写入；不能只存无法逆向恢复的hash。payload限制字段与大小，禁止密钥／签名URL／原始账户响应，无额外网络查询或事务内网络。
- UI／通知明确区分管理风险、仓位占用与资金限制；历史只有budget_exhausted的记录显示“旧记录未留具体原因”，不批量改成猜测原因。

**验收：**同一个账户分别因管理风险、margin、slot、最小订单量拒绝时，各有不同准确原因，持久化basis可重放得到同一拒绝分支；预算数值、身份、版本错配仍拒绝。BNB19:00原记录继续标明无法唯一还原。

### F4：保护存在性、可核实覆盖与风险分开

- 超量止损保留准确订单ID／数量／价格与最新余仓；显示“止损订单存在，数量不匹配，覆盖待核实”。
- `protected_quantity`仅代表已核实覆盖量；额外显式字段表达`protection_status=unknown`、`stop_present`、`reason`及venue声明量，不能把保守计量的0渲染成已确认无止损。
- 数量超过余仓、多个重叠单、未知条件子单、过期／不完整订单分别有reason；真正查明无有效止损才显示无保护。closePosition与定量止损分开。
- 在Hedge Mode超量语义获得准确证据前，维持保守风险／占用及新ENTRY门禁；该展示修复不授予撤单、改量或自动平仓权限。
- API、前端、飞书及aggregate投影使用同一typed状态映射。

**验收：**原止损32811／余仓16406显示存在且unknown；等量有效、数量不足、无单、多个单、事实缺失及closePosition分别正确；MANUAL无写，风险不因文字调整降低。

### F5：诊断保全与正常等待分类

- 认证、facts refresh、Signal ingest和Admission各边界保存每次失败的稳定stage／code／错误类型、直接原因及上游因果引用，包含准确runtime scope、product／account／symbol／side、policy／runtime identity、当前版本与有界数量事实。
- 保留current投影；新失败诊断是append-only事件，不以稍后成功覆盖。健康常态不追加流水；失败尝试有唯一attempt ID可追溯，完整错误basis按digest复用，连续错误可另作聚合显示，通知仍去重。
- 诊断事件与业务拒绝／认证结果原子保存；有界查询／索引、数据长度、分页与保留策略进入设计和迁移测试，避免每tick日志或反复大JSON。
- 源异常以固定错误码及已脱敏类型保存，不直接记录含密钥的第三方异常文本。unknown新异常有明确unclassified码，不丢失发生阶段。
- SOR新Session无闭合小时K线归类`session_not_ready`；不改session／首个合法入场时点。废弃scope从当前异常聚合排除但保留历史；真实误调度废弃scope仍视为缺陷。Owner已暂停标记控制原因；不恢复退休SOR或暂停CPM。
- DOGE认证矛盾→instrument受限→facts refresh无权威的传导保存cause reference，与网络timeout分开；不为恢复行情通过而强制设instrument.active。

**验收：**同一instrument先仓位矛盾、再网络timeout、后恢复，三个事实各可追溯；拒绝码在成功后仍存在；utc00:00无小时K为等待且首个合法时点不提前；abandoned scope不进入活跃告警；连续故障不产生重复通知。

## 5. 数据与迁移

- 外部退出来源证据、诊断basis、终态补齐队列及健康时间字段纳入现有Kernel数据权威；根据编码前当前head确定一个新前向迁移，不预占或改写已认证0020。
- 新源类型取代“所有fill都必须command_id”的假设，禁止把外部单写入Exchange Command；旧系统来源保全准确command lineage。历史缺失证据保持NULL／unavailable，不回填虚假历史。
- 复用既有Review revision链，旧review_id、hash、terminal_at、settlement、budget release及Owner审计逐表保全。
- 首次结构升级沿用stopped／flat／Owner暂停及全部writer停止、保全验证的合同；不能升级接手活动MANUAL仓或撤其残单。不创建schema fallback／双writer。

## 6. 实施顺序

1. **基线**：新focused人工修复分支，保持已认证TP1／MA50提交可追溯；移植并验证F0。
2. **先复现**：冻结DOGE脱敏原协议、300s／180s交错、health误标和超量止损四组RED；补F5历史缺失的未来留存验收。
3. **同一核算链**：typed外部来源→确证／去重→计算→终态revision／幂等→通知完整性。
4. **可观测性**：统一closure健康；精确Admission／认证原因及basis→API／UI一致表达。
5. **集成**：与实际R、5%最小提升50%、部分TP、发送竞态、MANUAL永久及新MA50配置完整交错。
6. **验证收尾**：修正此前周期性四进程资源用例的旧合同，保留当前“交接时点旧Static不得消费close”语义；在原1CPU／1GiB及600秒本机预算内验证，不延长预算或放松生产门禁。
7. **冻结新候选**：Focused RED/GREEN→Fast→一次完整R4＋API＋静态认证，独立保存原生manifest。旧候选证书不能证明新SHA。
8. **等待部署确认**：提供最终差异、验证结果、残余缺口和部署影响后，等待Owner明确部署确认；本方案不执行服务器或生产补账。

## 7. 验证矩阵

| 层次 | 必须证据 | 拒绝冒充的结果 |
|---|---|---|
| 真实协议 | 脱敏HTTP／WS JSON经当前CCXT再入适配器；常规／条件父子单与BNB费 | 理想化统一dict不能代替协议边界 |
| 纯域 | Decimal同值、真实差异、严格数量守恒、保护unknown、health状态单调 | 容差、补零、以MANUAL状态认领全部成交 |
| PG集成 | 原子证据／决定／outbox、revision链、重复与并发、失败回滚、重启与迟到 | 只看页面或mock仓储 |
| 完整生命周期 | AUTO→真实TP部分→App外部退出→MANUAL只读→flat／残单／unknown→settle／review→晚到补齐 | 终态等于经济完整；预算重复释放 |
| 数据迁移 | 空库及原终态生产形态前向保全、活动票／残单／wrong identity拒绝 | 清库或持仓交接迁移 |
| 前端与通知 | 同一typed状态、准确时间／原因／缺失项、请求未知不重发、旧票冻结 | “流程恢复”冒充完整净收益 |
| 发布 | 新SHA R4、API、static及资源边界证据 | 旧SHA证书、未过资源用例或自然交易证明 |

## 8. Owner决策与完成标准

**无须重新选择TP1、MA50、资金或人工接管规则。**推荐保留现有5分钟复盘宽限并统一入口；程序级错误修复不扩交易权限。

本轮交付为可复核方案。后续编码后的本地完成要求：F0—F5及交错反例通过、历史DOGE补账差异可复核、严格unknown保留、最新候选认证齐全、资源用例未通过则明确阻塞／范围。生产安装及生产Review补齐作为后续行动分别提供证据，部署仍等待Owner确认。

历史1024次认证与BNB19:00原因缺口会保留在报告中；未来诊断留存能防止再次丢失，不能倒推制造过去证据。

## 9. 源码入口

- `src/trading_kernel/domain/order_attribution.py`、`domain/review.py`、`domain/manual_position.py`。
- `src/trading_kernel/application/settle_ticket.py`、`reconciliation_health.py`、`build_capacity_claim.py`、`issue_ready_signal.py`、`certify_universe_instrument.py`、`notice_policy.py`。
- `src/trading_kernel/interfaces/reconciliation_worker.py`、Observation／Signal／facts refresh相关现有入口。
- `src/trading_kernel/infrastructure/pg_management_repository.py`、`pg_repositories.py`、`pg_models.py`、`venue_adapter.py`、`pg_notice_outbox.py`。
- 现有人工版接口／前端、测试、单线迁移及首尔独立安装保全工具。

### 后续单项实施记录

Owner明确要求合入71bf139a后，在当前分支以`c23d17ad`保留原提交来源的cherry-pick完成。仅六个原修复文件；唯一冲突为完整链测试旧schema常量，保留本分支CURRENT_SCHEMA_REVISION。先导入原反例测试，在未修源码上复现command baseline identity collision，随后应用修复，原36项回归通过；扩大单元／架构／全部完整链／相关集成2281项通过（93.45秒），Ruff、Mypy通过。该段为单项合入时记录；后续F1—F5已授权并实施，最终候选认证结果以新实施证据与精确SHA manifest为准。
