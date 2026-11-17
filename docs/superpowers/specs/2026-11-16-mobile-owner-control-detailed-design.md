# 手机操作端：授权与执行详细设计

> **执行分支统一入口：** [人工操作后自动续管V1](2026-11-16-owner-cooperative-execution-v1.md)已纳入Owner避免并行退出的决定及撤TP/减仓失败恢复。本篇冲突减仓流程仅保留溯源，以该入口为准；未开始编码。

> **主动减仓规则更新（Owner已确认）：** 见[减仓替代原TP1数量退出](2026-11-16-owner-reduction-replaces-tp1-decision.md)。浮盈/浮亏均可减仓；取消原自动TP1待成交数量，保留原目标价作为后续管理条件，不再二次减仓。本文等比缩减、保持原TP绝对量及相关冲突拦截建议不再适用于该分支；独立人工TP另行处理。当前仅设计。

> **当前工程范围更新：** Owner将策略收益结构留待后续讨论，前两层按[执行可靠性与人工协作范围](../plans/2026-11-16-cooperative-control-engineering-scope.md)推进。实现必须适配当前真实TP/BE/Runner，不以无TP模式为前提；本稿相关假设在E0收敛后方可使用。

日期：2026-11-16。状态：**详细设计稿，原型已获Owner认可；不是实现、部署或参数激活授权。**

依据：[已确认交互](2026-11-16-mobile-owner-control-v1-design.md)、[交易与协作基线](2026-11-16-trend-cooperative-management-design-baseline.md)。文中接口、表名、期限为工程建议的首版规格；补充业务已确认记录集中在[决策与验收计划](../plans/2026-11-16-trend-mobile-design-review-and-acceptance.md)。

## 1. 设计决定

首版为同源HTTPS主屏幕Web；服务端长期授权，不需要TOTP；一个活动设备注册；客户端不保存交易所密钥、不直连交易所、不离线排队发送交易。

既有Kernel仍是唯一执行者。持仓操作是Owner给AUTO管理器的约束/命令，不视为外部App接管。MANUAL/REVIEW_REQUIRED票不开放新续管操作。

原型入口、风格及主要流程冻结；产品意图通过权限、状态和数量变化呈现，不增加教程式文案。对网络、成交和授权状态只显示必要反馈。

## 2. 当前源码事实与改造点

| 现有边界 | 源码事实 | 新设计 |
|---|---|---|
| 会话 | `interfaces/owner_console_http/auth.py`使用进程内单会话，默认4h空闲/12h绝对期限 | PG持久化可撤销设备会话，服务重启不要求重新绑定 |
| Owner授权 | `domain/owner_control.py`及PG约束只认session/totp_step_up | 新增真实`trusted_device_session`，按用途显式允许 |
| 控制入口 | `routes/controls.py`部分路由将TOTP强度写死 | 根据真实认证上下文生成授权，不改名冒充TOTP |
| 指令执行 | API不派发交易，Kernel耐久Command后发送 | 复用此边界，新增Owner持仓操作状态机 |
| Binance Hedge | adapter只设置positionSide，USD-M不发送reduceOnly | 不假设reduceOnly是安全证明；用精确协议、方向和余量核实保证只减仓 |

这不是仅修改Cookie期限或前端去掉输入框。当前生产合同继续有效，正式切换按发布程序进行。

## 3. 首次绑定、长期会话与撤销

### 3.1 独立绑定渠道

首版使用现有Owner控制的服务器管理终端运行专用本地管理命令；命令只能签发/撤销绑定资格，不生成entry_resume或交易指令。不是直接改数据库修复工具。Owner通过自己的受保护渠道取得绑定材料，不在聊天或日志打印。

- 一次性绑定令牌：256bit随机值，10分钟有效，PG仅存哈希；输入或二维码传递。
- 页面POST提交令牌及浏览器生成的P-256非导出公钥。禁止GET消费令牌；二维码可携带片段，脚本立即清除地址中的片段再POST，Referrer-Policy:no-referrer。
- 活动设备存在时普通绑定拒绝；换机必须经独立渠道签发`replace_device`资格。消费资格、撤销旧设备/会话、注册新设备在一个事务内完成。
- 失败统一响应、IP及令牌桶限流；5次失败/15分钟限制该来源。随机令牌不能退化为短数字密码。
- 首版“单设备”准确含义是单个活动浏览器注册凭据，不保证物理硬件唯一或不可复制。Safari与主屏容器存储行为需真机验证；建议先添加主屏，再在主屏实例绑定。清除存储/换浏览器需重新绑定。

### 3.2 长期使用

建议Cookie `__Host-brc_device_session`：Secure、HttpOnly、SameSite=Strict、Path=/；有效期180天，距上次续期7天后在有效使用时续至180天。无固定绝对强制重登期限；180天不使用或浏览器清理后重新绑定。此时自动交易不因手机退出登录停止。

PG只存会话令牌哈希、device_id、device_epoch、issued/last_seen/expires/revoked。Cookie是随机不透明令牌，不把长期授权装进不可撤销JWT。续期只延长同一有效会话；定期令牌轮换需保留短期幂等重试，不让并发请求产生两套活动会话。

JS可持有非秘密CSRF令牌，设备私钥为IndexedDB非导出CryptoKey。写请求附服务端一次性nonce签名：method、path、body_digest、idempotency_key、nonce、device_epoch。nonce单次有效60秒；重复同幂等操作返回原结果，不重复写。GET不触发业务写操作。

服务端校验有效会话、活动device_epoch、签名、Origin/Host、CSRF与请求版本。非导出Web密钥是附加请求证明，不是硬件安全保证；同源XSS仍是重要风险，因此CSP禁止第三方脚本和inline生产脚本、无令牌localStorage、输出编码、依赖固定、API响应不缓存。

无需每次Face ID、密码或TOTP。用户确认是业务意图确认，不是密码学身份再次认证。Face ID不列为首版必需功能。

### 3.3 权限用途

| 用途 | 可信设备可授权 | 范围 |
|---|---|---|
| entry_pause/resume | 是 | 原全局ENTRY控制，真实Owner用途与事件 |
| strategy_pause/resume | 是 | 指定活跃策略，不恢复退休策略 |
| position_reduce/close | 是 | 精确AUTO票、原方向、只减仓 |
| protection_tighten | 是 | 精确AUTO票、只收紧 |
| manual_tp_set/cancel | 是 | 单个计划、剩余量内 |
| 风险预算增加、Universe/Selection、交易配置激活、历史Review修订 | 否 | 不因为移动登录扩展已有管理权限；保留其专用授权流程 |

既有历史TOTP授权不改写。新用途扩展domain、API、PG约束、runtime/promoter对真实授权的核验；不得用hardcode `totp_step_up`代替新证据。历史证书/审批不能因存在设备记录而被重新解释。

### 3.4 丢失设备和撤销

独立管理渠道撤销device_epoch，同时撤销会话及未消费nonce。客户端下一次请求401并清理本地显示。

已受理但尚未发送的Owner操作在发送门再次核实设备撤销状态，转`cancelled_authority_revoked`；已发送订单不假称撤销，继续对账并完成必要保护/收尾。设备撤销不是撤销所有既有AUTO交易权限，不取消交易所Stop。换机不恢复旧未发指令；新设备可读取已接受操作的结果。

## 4. 客户端与API合同

所有金额/数量用Decimal十进制字符串。客户端浮点仅用于非权威显示；执行预览与舍入以服务端为准。

| 提议接口 | 行为 |
|---|---|
| POST `/api/owner/v1/devices/bind` | 消费绑定资格，建立单活动注册 |
| GET `/api/owner/v1/mobile/session` | 返回设备/会话状态及必要nonce获取入口 |
| POST `/api/owner/v1/mobile/nonces` | 当前会话领取一次性写nonce，无交易副作用 |
| GET `/api/owner/v1/mobile/positions` | 有界AUTO/MANUAL持仓、保护、数据时点、可用动作 |
| GET `/api/owner/v1/mobile/orders` | 有界相关Stop/TP/未决操作，归属与可改权限 |
| GET `/api/owner/v1/mobile/controls` | Owner许可、实际可准入状态及首阻塞原因 |
| POST `/api/owner/v1/mobile/positions/{ticket}/preview` | 验证意图，生成服务端冻结预览，不下单 |
| POST `/api/owner/v1/mobile/operations` | 消费预览＋请求签名，原子生成授权和操作 |
| GET `/api/owner/v1/mobile/operations/{id}` | 返回已受理/处理中/部分完成/待核实/失败/完成 |
| 既有全局/策略控制接口 | 扩展认证用途校验，复用原Owner control应用服务 |

预览有效30秒，冻结account/Ticket/management_revision、position_qty、订单集合revision、输入、执行量/价、规则快照、操作后预期；百分比转绝对量向下取step，不把25%静默解释成提交时最新量的25%。确认时数量、管理权、TP订单或规则变化则409 `preview_stale`，重新展示。单纯报价变化不必逐tick作废，但保护/止盈价已越界或超过新鲜度则拒绝。服务端不提供误导性固定市价成交保证。

幂等键作用域Owner+purpose，唯一索引；相同key不同digest冲突。同一个已接受key即使预览过期，也返回同一个操作。一次票级写操作进行中，新请求409 `ticket_adjustment_in_progress`；其他票自动运行不阻塞。客户端5秒前台轮询，进入后台停止轮询；有未决操作回前台立即查询。操作超时不能视作失败并自动重发。

## 5. 操作数据与状态机

建议新增PG对象（正式migration编号实现时按当前链尾确定）：

- `brc_owner_device_registrations`：公钥、状态、epoch，单活动注册部分唯一索引。
- `brc_owner_device_sessions`、`brc_owner_binding_grants`、`brc_owner_request_nonces`：仅哈希令牌、有效期和使用事件。
- `brc_owner_position_operations`：kind、Ticket、preview_digest、authorization、device_epoch、expected_management_revision、目标变化、状态、唯一幂等键。
- `brc_owner_position_operation_events`：追加阶段、事实引用、错误码及重试/取消原因。
- `brc_owner_protection_constraints`：每票当前约束价/revision和追加事件引用。
- `brc_owner_take_profit_plans`：每票最多一个活动人工计划，原始数量、累计成交、剩余数量、精确订单身份与generation。

复用`brc_exchange_commands`及现有成交/管理证据，不形成第二账本。现有Owner授权表增加用途和真实认证强度；约束与operation、Command在短事务中原子提交。网络读/写均在事务外，返回后用expected_version提交事实。

操作状态：`accepted → validating → cancelling_conflicts? → dispatching → reconciling → restoring_protection → completed`。分支为`rejected_no_effect`、`partial_effect`、`outcome_unknown`、`needs_attention`、`cancelled_before_dispatch`。HTTP202仅表示受理；partial/unknown不能显示成功，也不能释放占用。

Lifecycle负责推进AUTO操作与保护，Reconciliation核实订单/部分成交/归零及未知；原有四worker拓扑不增加交易writer。前台不可通过GET推动状态。保护和结算动作遵循原冻出票权限，新增用户意图需要真实授权。

## 6. 逐项执行协议

### 6.1 市价减仓

1. 校验AUTO、准确方向/数量、保护已确认、无未知命令和外部干预。冻结精确减量Q；Q必须小于持仓，余量与既有待成交TP数量均合法。全退出使用close操作。
2. 获取票级operation锁，暂停该票新的Runner/TP策略派发；不是停止已挂交易所订单。
3. 已有数量范围内的获利退出可能与减仓竞争：取消所有该票待成交TP，保留计划语义，先确认取消终态和期间成交，再重新核对余量。变化影响原预览Q/计划则不发送减仓，恢复仍合法的计划并要求重确认。必要Stop始终保留。
4. 创建唯一`owner_reduce`Command，action-time核实精确剩余和Hedge侧的平仓方向。减量不会大于当前余仓；若已归零，按无新增减仓的终态事实完成/取消，不下反向订单。
5. 成交不明不重发；部分成交先对账，确认原订单终态后按已成交量形成partial_effect，不自动重发剩余Q。保护调整按真实余量进行。
6. 恢复实际余量的有效保护及仍合法原TP计划；新订单必须仍在有效目标价方向，越价不悄悄转市价，不重新卖掉部分。无法恢复获利单可报告部分完成，不能以此撤掉保护。
7. 操作completed要求减量结果明确、保护匹配、计划状态明确、无待核实命令。原风险预算按正式核算更新，不因名义保本无限释放。

**不采用“先减小Stop数量再减仓”**，因为会短暂留下未保护数量。Stop保持旧量期间与减仓竞态的安全性必须经USD-M Hedge协议确认；见§7硬验证门。

### 6.2 全平

锁定本票，禁止新保护策略调整；取消获利退出并查清成交，保留必要Stop；按剩余量生成一次平仓Command。若Stop先成交，查询准确事实，不盲发第二平仓。实际归零后取消并确认残单，再结算。零仓但残单或未知结果尚存，仍显示收尾中、保留占用。

### 6.3 收紧保护

方向比较取更严格者：多头max、空头min。预览必须相对当前已确认Stop有改善、距当前有效触发参考价合法；已经被价格穿过时不替换成隐式立即市价退出，返回`protection_already_crossed`让Owner明确选择全平。

先持久化Owner约束，再按正式replace_protection协议安装并核实更严格保护。只有交易所接受并回读条款一致才显示生效。Runner后来可进一步收紧，但永不放松已确认价。拒绝则显示“请求未生效”；持久化请求与已生效约束分开，不让失败请求伪造保护。已有更紧Stop即no_change确认，不另下重复单。

保护替换沿现有官方协议，验证新旧覆盖及取消竞态。若交易所无法同时挂新旧Stop且没有原子修改，不声称可无缝替换，列为实现阻塞，不能撤唯一保护来凑成功。

### 6.4 人工止盈（普通GTC限价，Owner已确认）

精确close侧/positionSide、数量≤可用余量。目标价必须在当前成交价的获利方向；提交前越价则重新预览，不以原请求静默立即成交。触价不保证满额成交。

每票一个活动人工TP。替换旧计划先取消、确认期间成交，再按最新余量检查新计划；失败则旧单可能已取消，显示真实partial_effect，不声称恢复。必要Stop持续有效。

对于保留内置TP的模式，**Owner已确认Q2（2026-11-16）**：人工TP替换该票尚未成交的自动获利退出计划，不叠加两套TP。取消旧单先核实期间成交，冻结新的manual_profit_target_id与目标量；原内置TP的历史累计成交保留，不能与新目标混算。新的人工计划目标完整真实成交后，生成`OwnerProfitTargetCompleted`，由明确的共享“获利兑现后保护”用例申请原profile的费用感知BE及Runner；不伪造旧目标已满额或原`TakeProfitFilled`事件。

人工计划部分成交只更新真实余量/费用和保护；取消计划则转`owner_profit_plan_cancelled`，不恢复旧TP，也不启动未获真实满额证明的BE/Runner。仍保留已有更紧Stop及原阶段适用的失效/时间退出；Owner可再设唯一计划或全平。若原票已在Runner，新增/取消人工计划不倒退阶段或放松保护。

该分支未实现并通过验收前，保留内置TP的票不开放人工TP替换，只提供现有计划展示及已支持的减仓/收紧/全平。界面能力必须来自服务端准确capability。

原型所用未来无固定TP模式则没有该冲突；其人工TP成交只生成真实减量事实，不影响已确认趋势状态。取消人工TP不取消Stop。结构退出先发生时清理TP，未确认残单不释放标的。

## 7. Binance协议硬验证门

当前adapter对USD-M不设置reduceOnly，这是Hedge Mode实现现实。低频串行只能减少本系统命令竞争，不能阻止交易所Stop先成交。

在实现前以官方协议/当前CCXT映射、原始HTTP/WS回放验证：close侧＋positionSide在余量变化/为零时的接受、拒绝、部分成交和超量请求行为；Stop触发子单与market减仓的顺序；旧量Stop在减仓后是否实际覆盖余量；已归零是否可能产生新暴露。不能仅凭内存Fake断言安全，也不下真实测试订单。

若精确合约不能证明旧Stop与减仓竞态只会减仓，则选择交易所支持的真正close-position保护能力并正式设计/认证，或不开放该动作。禁止冒险撤掉Stop、放松归属校验、自动对冲补偿或盲重发。当前设计给出执行协议与失败边界，不把尚未核实的交易所特性当成已完成能力。

## 8. 撤销、人工应急及错误策略

- 外部App有效介入：沿原规则永久MANUAL；停止后续Owner operation写入，不撤销已在途事实。核实并记录部分效果，后续只读收尾。
- REVIEW_REQUIRED：保持已有venue保护，不写新订单，精确补证据后才恢复；不能把未知当接管。
- API掉线/响应丢失：按幂等键查询原操作；不可生成新键自动重发。
- Worker重启：持久化阶段/command identity恢复；不得重新执行“第一个步骤”。
- Owner关新开仓：不取消持仓operation；全局Resume仍需真实授权，不由手机上线自动产生。
- 多请求：全平可以在尚未发送减仓前取消其未发意图，但已发送减仓必须先核实；不同时发两个close命令。

## 9. PWA、缓存与通知

同源部署，独立mobile入口但复用后台。Service Worker只缓存带版本静态壳；`/api/**`、认证、预览、订单与持仓一律network-only/no-store。不使用Background Sync重发交易。离线可显示带时点的旧界面，但所有写操作禁用；恢复联网先刷新版本与事实。

系统推送可选，绑定设备而非账号任意终端。先复用Transactional Outbox，新增Web Push目的地；仅Owner同意后注册订阅。绑定码、Cookie、订单详情不进入锁屏通知默认正文。去重按operation/event identity；通知失败不影响交易、不开新风险门禁；页面恢复以PG结果为准。

iOS主屏Web通知支持与权限须真机验收；不支持则展示页面结果并保留已配置通知通道，不伪称已投递。原有通知不在首版擅自删除。App封装后设备注册/会话和推送需迁移设计。

## 10. 读写性能与验收范围

首版规模单Owner、有限并发票：positions/orders默认50条、硬上限100；operation事件每页50，按id游标；API不全历史扫描。写事务建议1秒上限、避免网络；worker以既有周期推进，单票未决不阻塞其他票。nonce/preview定期按过期索引清理，授权和operation事件按审计保留，不清除未结操作。

验证矩阵与发布顺序见[验收计划](../plans/2026-11-16-trend-mobile-design-review-and-acceptance.md)。本稿不声称普通限价成交保证、浏览器物理设备证明、永久不掉登录、保护无条件无缝替换或完整真实交易验收。
