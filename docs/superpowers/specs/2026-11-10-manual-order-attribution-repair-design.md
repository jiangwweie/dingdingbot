# MA-R2：首尔订单归属、连续覆盖与收尾修复设计

日期：**2026-11-10，Asia/Shanghai**。状态：**方案待 Owner 确认；禁止据本文开始编码、测试执行、恢复写入、迁移或部署。**

Owner 已认可“真实协议回放、完整本地链路、发布前能力门禁、运行准确告警”四层方向，并要求先交付完整方案。本文件定义设计；配套[实施与验证方案](../plans/2026-11-10-manual-order-attribution-verification-plan.md)定义任务、测试和发布验收。**方向认可不等于本文尚未确认的实施/恢复例外已获批准。**

## 1. 目标与权威

**目标：默认自动交易在正常场景下持续自动管理；真实外部有效干预使整笔永久 MANUAL；真正未知保持明确受限，但不阻断已经有充分证据的只读账务与收尾。**

1. 沿用 **Observation → Signal → Readiness/Authority → CapacityClaim → Ticket → durable Command → Lifecycle → Reconciliation → Settlement → Review**。
2. 生产执行代码仅在 `src/trading_kernel/**`；数据库迁移仅在 `migrations/trading_kernel/**`。Reconciliation 继续拥有管理观察与持久化，不新增独立交易 Worker、第二账本或运行兼容适配链。
3. **PostgreSQL**存当前权威、不可变命令和追加事件；交易所只读事实证明外部真相。报告、fixture、Markdown、Git分支名和缓存不授予交易权限。
4. **MANUAL 不回 AUTO**。冻结退出、改单、撤单、补仓权限的业务规则保留；修改归属证明不改变策略、容量、杠杆、止损风险或 BNB 设置。
5. Tokyo 全自动工作区和账户不属于本方案的变更目标；可能共用的协议修复以后独立移植与认证，不整分支合并。

依据：[Owner运行模型](../../current/OWNER_RUNTIME_OPERATING_MODEL.md)、[Kernel设计](../../current/P0_TRADING_KERNEL_REBUILD_DESIGN.md)、[Owner原始决定](2026-11-06-app-manual-takeover-v1-owner-decisions.md)、[双工作区规则](../plans/2026-11-08-two-product-workspaces.md)。实时部署/策略/账户状态只由[路线图](../../current/MAIN_CONTROL_ROADMAP.md)与行动时证据管理。

## 2. 已知客观事实及证据边界

### 2.1 八类缺陷

下表源自 **2026-11-10 已完成诊断**，不是本轮重新采集的现场快照。A为生产已发生，B为真实记录离线重放，C为控制场景/一次性本地PG复现。全部代码改动仍未执行。

| 编号 | 已确认缺口 | 等级 | 设计落点 |
| --- | --- | --- | --- |
| F01 | CCXT REST数字字符串被仅接受int的时间/计数解析器拒绝 | A/C | 精确协议正规化；§4 |
| F02 | 系统期望硬编码reduceOnly=false、STP=NONE，与实际回显不同，可能误转MANUAL | B | 不可变系统订单基线；§5 |
| F03 | 重启/断流后用新连接证明整个旧Ticket历史，恢复要求无法满足 | C | 持久证据、区间和缺口；§6 |
| F04 | 完整条件单流已证明改价后改回，仍被REST疑点判整批不完整 | C | 订单级联合证据；§3/§6 |
| F05 | 其他历史缺口使明确外部全平成交也变成未知，REVIEW跳过只读收尾 | A/B/C | 独立退出证明及收尾；§7 |
| F06 | 命令历史超限、已知条款校验失败在保护try之前抛出，原AUTO可能保留 | C | 全阶段失败与独立写门；§8 |
| F07 | 非断线WS错误清空覆盖标记后，仅重试同socket，缺少恢复路径 | C | 连接代次、任务恢复；§6 |
| F08 | 采集错误不写管理健康投影，外层却包装为position_reconciled | A/C | 监控、通知和API；§9 |

具体源码依据：[协议解析](../../../src/trading_kernel/infrastructure/binance_management_observation.py)、[命令匹配](../../../src/trading_kernel/application/management_intents.py)、[分类器](../../../src/trading_kernel/domain/trade_management.py)、[采集器](../../../src/trading_kernel/infrastructure/management_collector.py)、[观察Worker](../../../src/trading_kernel/interfaces/management_observation_worker.py)、[WS适配](../../../src/trading_kernel/infrastructure/binance_management_stream.py)、[只读收尾](../../../src/trading_kernel/application/reconcile_ticket.py)。

诊断原始材料在本工作区忽略目录 `.local/management-audit-20261110/` 和 `.local/bnb-forensics-20261110/`；说明仅用于人类审计，运行时不读取。现有 **71项相关单元测试通过**并未覆盖真实CCXT数据路径，不能据此宣称这些缺陷不存在。

### 2.2 未证实项

条件单历史分页协议、ALGO_UPDATE不同状态字段、最大受支持负载下整组采集时间尚需协议原文/真实脱敏样本验证。已知官方网页抓取曾返回防护响应；不把防护页、个人帖子或手写fixture当作权威协议。**协议来源缺失时对应能力不进入可用状态，不能假设分页参数和缺省值。**

## 3. 三类证明分开建模

以下为**拟议设计**，不是已完成能力。模型采用冻结命名Pydantic，身份含产品、venue、account、instrument、position_side及订单namespace，数值使用Decimal。

| 证明 | 内容和边界 | 可以支持 | 单独不能支持 |
| --- | --- | --- | --- |
| **AttributionProof：单次操作归属** | 某个具体订单/成交/改单；来源、event time、received time、准确Command匹配、未决命令集合、证据引用 | 自身动作、自然成交或已确认外部干预；必要时转MANUAL | 证明所有历史都没有人工干预；释放尚未知的残单占用 |
| **CurrentExposureProof：当前仓位及残单** | 同一有限采集窗口的仓位、全部相关普通/条件订单、准确订单终态、未决命令；明确完整性和有效期 | 只读数量/保护/风险更新；配合退出归属进行收尾 | 单靠零仓推定平仓价、操作者、完整收益或自动管理权 |
| **ContinuityProof：连续管理覆盖** | 有效连接代次、已持久事件水位、连续区间、准确缺口、REST可补齐部分；源和本地完整性分开 | 未干预AUTO持续运行或可恢复REVIEW解除 | 用重连/心跳/空REST列表补造缺口；反转MANUAL |

### 3.1 决策规则

1. **确切自身命令结果**是自身订单归属依据，brc前缀只能用于检索，不能作为授权。
2. **已确认外部新增/改单/撤单/减仓**可在与该动作无关的历史区间未知时成立，但必须排除该精确订单的自身在途/未知命令，并验证作用范围、来源与交易所结果。不得因为“没有匹配上”就认定外部。
3. **证明存在一次外部动作**与**证明从未有过外部动作**采用不同证据强度。前者可用准确订单/成交/改单；后者要求完整、有效的连续覆盖。
4. **当前快照完整性**只由该次仓位/订单查询及分页/终态校验产生；不能再被一个历史stream gap全局覆写为false。
5. 遇到真实冲突、缺分页、未知结果，相关证明保持unknown。保存确定事实，同时保留保守资金/标的占用，不能传播假零值。
6. 分类必须输出 `decision + reason_code + evidence_ids + affected_scope + retry/recovery_disposition`，不再用一个总 `complete` 布尔值承担所有语义。

### 3.2 管理状态与证明要求

| 当前状态与事实 | 管理结果 | 自动写入 | 只读对账/收尾 |
| --- | --- | --- | --- |
| AUTO，自身订单匹配且连续覆盖健康 | AUTO | 仍逐命令通过所有门禁 | 正常 |
| AUTO，归属无法核实或管理健康失效 | REVIEW_REQUIRED | 禁止新的普通自动管理写入 | 可收集并保存确定事实，不能伪造归属 |
| AUTO/REVIEW，确切外部有效操作且满足初始交付条件 | MANUAL | 全Ticket禁止自动管理写入 | 依当前证明刷新风险；充分证据时归零收尾 |
| REVIEW，完整缺口补齐、全为自身/自然且没有外部干预 | AUTO | 解除事件提交后按新状态重验 | 正常 |
| REVIEW，零仓但归属/残单/命令结果不明 | REVIEW_REQUIRED | 禁止 | 显示“当前零仓，归属或残单未核实”，保留占用 |
| MANUAL，历史细节不全但当前退出/零仓/残单/命令已充分证明 | MANUAL→Settlement/Review | 永不恢复AUTO | 允许可证明的合法收尾；未知经济字段显式缺失 |

**“未知归属但当前已平”的一般性释放**不在首版默认放行；先支持已有确切外部退出证据的路径（包括BNB）。如果后续要让Owner声明替代缺失外部证据，必须另立业务授权合同，不能藏在修复里。

## 4. F01：真实协议正规化

1. 在CCXT输出进入领域模型的唯一边界正规化普通REST、algo REST、改单历史与WS字段；禁止散落 `int()` 和默认0。
2. 整数允许非负Python int或非空ASCII十进制字符串；字段还须符合正值/零值及有界范围。明确拒绝bool、float、小数/指数/符号字符串、空值、负数、超长值；不可因orjson安装状态产生不同语义。
3. 金额/数量仅由十进制字符串或Decimal构造；JSON整数金额是否允许必须在字段协议中明确，禁止float参与金融计算。
4. 枚举与可选字段按**消息类型＋订单类型＋状态**定义；不能给缺失字段补上可能影响归属的默认值。协议不认识时形成具名缺口，不吞掉整个账户证据。
5. 保留安全的原字段类型、namespace、endpoint类别、schema版本及响应摘要；禁止保存凭据、签名URL、listenKey、认证headers到日志/fixture。

## 5. F02：系统订单的精确基线

### 5.1 来源与建立时机

每个订单身份冻结关联：**durable Command → 实际发送字段 → 确认回执或准确只读订单查询 → 规范条款基线**。

- 仅在command_id、clientOrderId、exchangeOrderId、namespace、账户/标的/方向和时间证据一致时建立。
- 应由命令确认/精确reconciliation路径写入，不允许管理扫描看到任意同前缀订单就登记为自身。
- 交易所回显默认值需可靠的源协议/原始回执证明。事后第一次查询可能已被Owner修改，不能将其价格/数量直接当原始基线。
- Command明确字段（价格、数量、方向、触发价、TIF等）必须匹配；不匹配保持unknown或依确切改单证据分类，不擅自“修正”历史命令。

### 5.2 字段分类

| 类别 | 示例 | 校验原则 |
| --- | --- | --- |
| 不可变身份 | account、instrument、position_side、namespace、orderId、clientOrderId | 必须准确一致，不跨namespace比较相同数字ID |
| Command明确意图 | side、quantity、limit/stop price、order type、TIF、close-position语义 | 比对实际发送意图及协议合法正规化结果 |
| 交易所回显/默认语义 | STP、hedge模式的reduceOnly回显、workingType缺省 | 依据已核实协议和确认回执冻结；不再硬编码NONE/false，也不全局忽略 |
| 正常生命周期变化 | status、executedQty、updateTime、algo触发子单 | 不作为Owner改单；须验证相应状态与成交/子单映射 |
| 可人工变更条款 | price、quantity、trigger、保护方式等 | 当前条款与准确基线比较，并结合改单/撤单/外部创建证据 |

同ID多次改单/改回原值保留事件序列，首次有效外部操作即永久MANUAL。触发子订单必须通过algo的准确actualOrderId与作用范围关联，不能将平台子单当作Owner新单。所有事件先处理自身未知命令，拒绝“未匹配＝外部”的捷径。

## 6. F03/F04/F07：持久事件与连续覆盖

### 6.1 结构与单一写入者

继续由 **Reconciliation** 内部已有异步管理观察任务拥有接收、持久化和归属处理；不新增systemd交易Worker。接收队列是传输缓冲，**内存deque和文件都不是覆盖authority**。

完整版本拟对当前schema做一条前向迁移。**本方案选择原始接收和规范事件分层，只有规范事件参与归属；原始层只负责耐久输入和重放证明。** 表结构不是第二条执行链，全部由同一Kernel/Reconciliation拥有。

| 数据 / 拟定表 | 最小字段与键 | 写入与作用 |
| --- | --- | --- |
| **`brc_management_stream_events`**：耐久原始输入 | event_id；scope_key=product+venue+account；epoch_id；receive_sequence；received_at_ms；exchange_event_at_ms（解析前可空）；message_kind；safe_payload；payload_digest；unique(epoch_id,receive_sequence) | 追加不变，原始事件保存成功才推进持久接收水位；只保存允许的订单协议字段，剔除listenKey等Secrets |
| **既有 `brc_management_order_evidence`**：唯一规范订单证据 | 保留evidence_id/Ticket关联；增加source_event_id/source_kind、canonical_schema_version、规范payload及源摘要；同一来源事件幂等 | 供归属分类消费；坏schema可保留原始输入并记gap，但不能造规范成功事件 |
| **`brc_order_command_baselines`**：系统订单基线 | baseline_id；command_id FK；scope+instrument+side+namespace+order_id唯一；client_id；request_digest；confirmed_terms；protocol_version；acceptance_evidence_ref；confirmed_at_ms | 确认路径追加，不覆盖。请求意图与确认回显同时保留，后续条款不能自我认证 |
| **`brc_management_coverage_events`**：连接/区间/缺口事实 | coverage_event_id；scope_key；epoch_id；kind（connected/subscribed/checkpoint/gap/gap_resolved/closed）；from/to；receive_watermark；evidence_refs；reason；occurred_at_ms | 追加不变；恢复不能删除gap，只追加准确解决证明；不伪造交易所未提供的序列号 |
| **`brc_management_feed_current`**：当前接收健康 | scope_key PK；epoch_id；owner_worker_id；runtime_commit/schema；lease_until_ms；connection_state；persisted/applied_watermark；last_successful_at_ms；health_reason；revision | 当前投影，按CAS更新；事实来源是上面持久事件。新租约/重启必须重新证明就绪 |
| **既有 `brc_management_observation_current`**：Ticket观察投影 | ticket_id PK；attribution/current_exposure/continuity证明引用及各自status/deadline；gap引用；last_successful_at_ms；revision | 替换原单一complete判定；身份、管理权事件和投影在短事务中重验并更新 |

所有索引围绕 `scope+epoch+receive_sequence`、`ticket+observed_time`、`namespace+orderId`、`command_id`、未解决gap及到期租约；热路径禁止按全部历史扫描。接收队列达到容量上限应记录lost interval并限制新准入，不能无声覆盖；数据库无法写时本地立刻停止推进，租约到期提供其他进程可见的fail-closed。

**迁移规则**：保留原事件、Ticket、Command、Review与原始证据payload；可精确转换的规范字段按一次性前向迁移转换，补充来源标记，旧证据未知项仍unknown。旧单一complete列退出运行判定，其原值以迁移审计记录保留；当前新模型不读取旧列或遇到异常回退。终态交易不补造连续覆盖，标识为历史终态、不参与当前准入。R1切换时必须没有非终态Ticket，避免活动状态跨证明模型交接。最终DDL须与本表一致；若实现需要改变此权威划分或迁移边界，先回到方案复核。

### 6.2 连续性和重启

1. 使用本地严格递增接收序号和连接epoch，不把exchange timestamp当全局唯一顺序号；同毫秒不同事件以完整身份/正文摘要区分。
2. 覆盖水位只能推进到**已事务提交的事件和接收屏障**。进程活着、收到pong、订阅成功分别只是运行/传输证据，不能单独证明无漏单。
3. 崩溃前收到未落库、队列溢出、连接断开、解码失败、worker身份改变必须形成准确gap。重连只开始新epoch，不抹掉旧gap。
4. 按实际缺口和相关订单做有界REST回补；接口不能证明同ID改回时，保留此项未知，不强制自动恢复。
5. 持久证据已覆盖的旧区间不再反复从Ticket出生重查。真实不可恢复缺口有明确状态和受控只读收尾出口，不靠无期限重试。
6. 单个坏订单隔离为该订单/标的缺口；涉及账户整体或未知暴露范围时才扩大阻塞范围。强证据不得被不相关缺口抹成unknown。
7. F04使用订单级REST/WS联合求证：完整外部修改序列使其MANUAL，最终价格相同不能擦除操作；同样不能因最终相同再宣布已证明的序列缺失。
8. 无事件时仅有界更新健康/水位投影，不产生Markdown/JSON文件，不逐tick追加重复事件。

### 6.3 预算和可达性

- 保留有界分页、连接队列和查询限制；旧的“最多200条全历史命令”替换为活跃相关订单＋准确命令查询，较长历史由持久cursor分批推进。
- 队列溢出应明确gap并限制相关新准入，不静默丢失。初始容量/时间参数是工程提案，不能把现有2048、200、16或5秒当保证能满足生产需求。
- 对条件历史cursor、消息字段缺省和合法查询窗口先获得权威协议或真实样本；验证失败时对应能力不可用。
- 整组预算包括排队、网络、解析、持久化，不能只量HTTP。先测量既有Reconciliation预算下是否可达；无法达标先分批/调度，若必须修改全局预算须列具体差异复核，不能顺手扩大。


### 6.4 时间、锁与保留策略

- 使用UTC毫秒存储，界面显示北京时间；采集开始/完成、交易所动作和本地接收分别记录，使用monotonic计算耗时。禁止把完成时刻覆盖为新的采样起点来延长事实寿命。
- 延续当前已批准Entry10秒/30秒事实及5秒最终发送窗口。本方案不直接把Reconciliation5秒扩大；先验证每批可在原预算内完成，历史较大时拆分为可续跑的有界批次。
- 网络I/O始终在事务外；短事务按统一锁序（账户健康/覆盖代次→Ticket→准确Command/证据→投影）重验revision。锁超时不能转成功，作用域外数据不能被更新。
- 新接收事件先耐久写入，规范化/归属后原子更新applied watermark；persisted与applied是两个数，不能用前者掩盖后者积压。
- 健康租约、采集cadence、积压上限和操作检测延迟上限须在MA-00形成数值合同，再由MA-07按部署负载验证。选择必须满足“健康期限包含一次正常采集＋调度余量，且不超过已批准的写入证据期限”，达不到则优化设计或列参数复核，不默默放宽。
- 非终态Ticket、未解决gap、未结算经济引用到的原始/规范事件不得清理。终态后按审计保留策略归档/删除原始体，保留稳定摘要/引用和交易事件；该策略在迁移/retention工具中明确版本化，不依赖运行报告文件。任何清理不能破坏可恢复性或让旧gap变成已覆盖。

## 7. F05：当前事实和收尾独立推进

### 7.1 常规路径

1. 即使管理历史仍有缺口，也保存已核实的当前仓位、当前保护及读取时间；账本明确区分“原Ticket数量”“最新外部已核实数量”“待核实占用”。不覆盖不可变Ticket。
2. **外部全平归属证明**至少包含准确外部成交/订单终态、账户/方向/时间与Ticket关联、与已成交ENTRY数量的对齐、相应自身命令无在途或未知结果；client前缀或用户口述不能独自满足。
3. 有确切外部操作，依法追加 `ManualTakeoverConfirmed`，保留原REVIEW事件与原始原因；不是改回AUTO后再假装正常退出。
4. 全平但普通或条件残单未终态，进入MANUAL_FLAT_PENDING_ORDERS并保留必要占用。未经证明不发撤单；Owner管理MANUAL残单。
5. 当前零仓、所有相关订单终态、账户同标的两侧无冲突且自身命令已全部解析后，在唯一应用路径中更新数量/保护、释放可证明的Reservation和Netting Domain，继续Settlement与Review。
6. 本地事务原子化事件、Aggregate、当前投影、释放和通知outbox。崩溃重试幂等：不得重复释放、重复消费Signal或追加第二ENTRY generation。
7. 经济数据独立核算。用准确fills、手续费资产及资金费形成完整净结果；不能用价格差当净损益。为外部退出建立带准确订单/成交ID的只读 `ExternalExitReference`，与系统Command来源明确区分，**不得伪造Exchange Command来挂接Owner成交**。手续费BNB换算依据也须可追溯；暂缺字段走既有显式unavailable及后续追加修订，不将缺失写成0。

### 7.2 初始保护与在途写入

新增普通AUTO健康门禁不得遮断既有“部分ENTRY成交、结果未知、初始保护失败”等安全恢复流程；由原阶段状态机和准确命令结果决定。**MANUAL写禁令仍优先**。采集过程中状态变化必须在短事务和最终dispatch授权点重验management revision、连接epoch及门禁。

已发到交易所的请求不能假装撤回；通过durable Command核实结果。方案不承诺App点击瞬间与系统发送之间的零延迟原子切换，仍遵循原产品认可的观测边界。

## 8. F06：从准备到提交的失败都进入明确控制

1. 覆盖读取Aggregate/命令、构造known terms、请求网络、解析、归属、持久化全过程的异常分类；不要用一个catch吞掉业务矛盾。
2. DB可写时记录精确失败阶段、reason及受影响scope，建立REVIEW/健康受限状态。不能以 `position_reconciled` 表示管理采集失败。
3. DB不可写时无法可靠记录状态，**依靠健康租约过期和发送侧门禁阻止新授权**，而非假设可以更新Aggregate成功；服务报告失败并保留未知命令，不盲重发。
4. 新ENTRY同时检查当前管理采集能力；普通自动管理写入检查当前Ticket/账户管理健康。门禁存在统一Kernel路径，不能各Worker自设不同绕行规则。
5. 健康阈值必须由完整tick预算、最大支持负载和实际调度证明；Owner不需要逐笔审批或手工拼接事实。

## 9. F08：可观察性与告警

### 9.1 正确分层

分别展示：**服务状态、采集健康、订单归属、当前外部持仓、历史覆盖、资金占用、结算进度**。不得以0个Incident、position_protected标签、通知通道正常或单一freshness推导全部正常。

### 9.2 输出与通知

- 结构化日志包含 phase、精确Ticket/Command/订单namespace、规范reason、队列/HTTP/总耗时及最后成功时间；禁止认证数据和签名URL。
- 新错误/影响范围变化立即输出；同一错误限频汇总，长期未恢复持续可见；恢复必须引用真实证明，不按定时器自动变绿。
- 状态变化通知沿用现有transactional outbox；通知失败不反过来授予/撤销交易权限。
- REVIEW产生应有当前管理健康投影；手工全平未收尾应显示真实零仓与仍占用原因，不能继续笼统标“自动保护正常”。
- 新增对坏数据、历史上限和恢复时间的运维指标；指标仅展示，不建立第二套authority。

## 10. BNB旧Ticket：两阶段恢复与发布顺序

### 10.1 为什么不能直接用现有升级入口

当前[安装门禁](../../../scripts/trading_kernel/manual_host_bootstrap.py)的 `require_stopped_upgrade` 用全表 `EXISTS(Ticket/Command)` 限定新账户，并仅允许同schema或特定旧迁移。BNB已有真实交易，且内部非终态；即使交易所已平，也不能直接通过。不能清表、删除历史、直接置终态或绕过Runtime Fence。

### 10.2 阶段 R0：同schema、恢复专用切换（需要在方案复核中明确接受）

**只为“交易所已平、所有挂单已终态、内部仍占用”的准确白名单Ticket提供恢复专用模式；不是带真实仓位升级。**

1. Owner通过真实控制台暂停新ENTRY。行动时重新核实独立账户/主机/数据库、所有仓位为零、普通/条件订单为空、准确退出fills及自身命令已知；若任何真实敞口/残单/未知结果存在，停止此路径。
2. 五个写入服务全部停止，维护围栏建立；保存完整历史与控制摘要。正常路径必须terminal-clean；例外路径仅接受精确Ticket集合及其证明摘要，其他未决Ticket/Incident必须解释且不得扩大白名单。
3. 通过**增强后的正式 manual 安装入口**切换到精确认证的同schema R0候选。身份更新与恢复模式应原子记录于现有PG能力/身份边界；新ENTRY和交易所写能力保持关闭。不能让新代码冒充旧commit运行。
4. R0是单独认证的**同schema恢复候选提交**，仅包含必要协议正规化、准确Command身份/外部退出归属、当前收尾证明、失败控制及单次Kernel维护入口。它不依赖R1新增表，不声称已具备完整AUTO订单基线能力。只使用现有持久Command和已核实退出事实关闭白名单交易，不运行普通Collector/交易Workers。R1是其后的完整候选，不能把R1新schema代码以兼容模式放到R0运行。
5. 恢复入口只能调用GET/read-only venue端口和Kernel的UoW/Reducer/Settlement/Review；没有execute/cancel/transfer方法。每步事务校验精确产品、账户、schema、代码、白名单、Owner暂停、旧写入者停止和事实期限。
6. 先生成只读决策预览，展示会追加的事件、预算释放和经济字段完整性；实际应用重新读现场事实，不能把JSON预览文件当执行授权。
7. 对BNB重读原ENTRY/stop/TP1、确切外部全平成交、止损撤销及当前无残单，追加真实MANUAL与只读归零/Settlement/Review链；保留原7个事件和3个Command，不重放信号。
8. 原有账本与权威表的变化仅限预览允许的Ticket、相关事件/投影/释放/复盘/通知；其他行和所有Owner控制摘要保持一致。失败保留围栏、停止，已提交步骤按幂等键续做。
9. 到terminal、占用释放、命令无未知结果、Review可读且经济缺失正确标明后，形成**终态清洁来源**，才能进入R1 schema升级。

**R0的例外切换合同尚未实现、也未因方向认可而获自动放行。它需要针对性验收和明确复核；若无法满足，则本阶段保持阻塞，不能换用直接SQL或未认证sidecar。**

### 10.3 阶段 R1：完整修复及前向迁移

1. 冻结完整F01—F08及三证明模型，完成R4/接口/静态认证、空库和带已认证终态历史的前向迁移演练。
2. 从R0形成的terminal-clean状态，在五写入者停止、真实无仓无单下迁移。具体revision取实施时实际HEAD的唯一下一号，不在方案预占并行编号。
3. Migration只迁移必要投影和新增规范证据结构；不可将缺失原始事件回填为完整，不重算或覆盖历史净收益，不建立旧schema运行reader/双写。
4. 正式升级门禁从“从未有过Ticket”改为“所有既有交易终态且无未决债务/占用”，并加入逐表/关键行保留验证。准确允许的新增数据变化与身份变化另列，不能只比较总行数。
5. 启动原四Worker/API，先验证管理采集准备与持久化、两类只读探针及当前门禁。仍由正式promoter处理维护围栏，Owner真实Resume/TOTP决定恢复新ENTRY。
6. 新信号只经正式链路运行，保留自然AUTO、实际App干预和手机收件未完成项直到直接观察。

### 10.4 失败与恢复

- **R0失败**：保持旧写入者停止/新交易禁止，按已提交恢复步骤幂等续做；禁止为快速恢复将BNB改AUTO。
- **迁移前失败**：在现有门禁允许、相同schema且精确认证的条件下恢复明确版本；仍暂停ENTRY，不能恢复已知缺陷版本后宣称可交易。
- **R1迁移提交后失败**：forward-fix；不降级、不还原旧DB，不启动旧schema writer。
- 任一时点发现真实敞口或新挂单：退出“外部已平恢复”路径，保留真实保护/占用，形成单独处理事实；不为了部署强制平仓。

## 11. 复核点与交付状态

| 决定 | 推荐 | 当前状态 |
| --- | --- | --- |
| 三证明分类及“确切外部退出可收尾、未知不可恢复AUTO” | 接受§3/§7 | **待本方案确认** |
| 持久管理证据、基线、连接/gap和健康投影的前向schema演进 | 接受§6已选定的数据权威划分；DDL按此冻结 | **待本方案确认** |
| R0外部已平、内部非终态Ticket的恢复专用正式切换 | 按§10精确白名单、GET-only、禁止正常交易 | **需明确确认此例外范围** |
| 新ENTRY与普通自动管理的管理健康门禁 | 按§8，保持初始安全恢复及MANUAL约束 | **待本方案确认** |
| Tokyo变更、风险/资金/BNB/策略扩张 | 不纳入 | 无实施授权 |

**本轮只交付设计与验证文档。编码、测试执行、恢复写入、迁移和部署全部等待Owner下一次明确确认。**
