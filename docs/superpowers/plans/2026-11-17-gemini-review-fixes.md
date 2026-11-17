# Gemini审查缺陷：本地修复与复审交接

日期：**2026-11-17，Asia/Shanghai**。状态：**已完成本批明确缺陷的本地修复，仍在整包认证与部署之前**。

## 1. 修复范围与授权

Owner要求修复Gemini审查中已确认的问题。保留手机Web、后台续管、事故修复与首尔资源配置最终联合上线的决定；本轮不上传、不部署、不重启、不迁移生产、不修改Owner策略、不执行交易所写入。整包Integration/Full-chain与发布认证仍未启动。

审查基线为`5ad82fc2`，复审差异使用`git diff 5ad82fc2..HEAD`。若连同第一轮检查则从`a30d388c`比较。

## 2. 已修复的问题

| 审查项 | 本地修复 | 对应验证 |
|---|---|---|
| **v1减仓后无法转保本** | 止损采集独立于精确TP开关；从原始REST解析，核对准确订单/账户/方向/数量/触发价/NEW状态，不用缺少terms的普通订单投影代替 | v1/v2正例；错client/数量/价格/终态反例；实际adapter输出进入PG maintenance，产生价格条件与BE请求 |
| **Runner及重复减仓证明冲突** | proof明确pre_tp/wait_price/runner来源，TP累计历史守恒；Runner无新TP价格条件；重复减仓沿已退休目标条件，不再次撤不存在的TP | 纯域正反例；真实原生命周期先进入Runner，再经签名操作/实际减量记录，阶段和BE保持 |
| **旧初始止损清理身份** | 新保护不同于旧保护时，proof必须提供旧单终态；UoW按evidence ID精确加载已落库撤销/过期证据，核对原Command身份、账户、侧及时间；只有已证实终态的旧ID才清除 | 没有证据不能清除；旧Stop已证实终态后清除；伪造/缺失证据被拒绝 |
| **减仓退出归因** | Review、交易列表、详情与closure都纳入owner_reduce；减少的数量继续计入完整成交账；同毫秒多类退出标记concurrent_exit_fills，不按trade ID猜最终触发源 | 减仓后止损、同毫秒混合退出、Owner归类；PG真实查询到列表/复盘展示共享归因 |
| **授权证据可改及no-op悬空** | 注册公钥与写请求原文由DB触发器禁止改写；API只获撤销列、一次性结果关联列权限；pending只能转一次authorized/no_change；无变更请求明确保存原返回值，重复查询不返回后来的状态 | DB权限实际查询；原文修改/取消撤销被拒；no_change有明确receipt；历史签名与真实目标绑定保持 |
| **绑定限流与手机入口** | Nginx对绑定限流；PG记录来源IP哈希及令牌哈希最近5次失败，15分钟封锁，来源/令牌切换不能直接绕过；失败事务提交后才回应403/429；手机目录URI内部转index.html并指定HTML类型 | API第6次429、不同token仍受来源限制、过期恢复；本地真实Nginx 1.28.3返回HTML与JS的200及正确MIME |
| **旧epoch阻塞导致新事件未落库** | 原始接收先独立事务提交再ACK；原事件仍在原stream_events表；新增receive_epochs仅记录接收顺序/水位与未完成分页，不另设应用水位；原feed_current继续唯一控制按序应用 | 旧头部阻塞时新epoch落库；清空内存后从PG按序恢复；130条旧接收分页未完成不能被新epoch越过；失败提交不ACK |
| **客户端超时后换新幂等键** | 发送前把同一签名请求保存在IndexedDB；超时、断网、5xx、408保留未知状态并禁新写；刷新只读查询原receipt；只有确认结果或已过期且未消费nonce才解除 | 执行真实app.js的Node VM故障测试：发送一次、第二次点击不出网、查询完成后解锁；服务端锁后重查时间，防止迟到请求拿旧时间复活 |

修复没有放宽成交、归属、保护或MANUAL约束。`OWNER_REDUCE`仍显式deferred；手机持仓写capability保持false。

## 3. 跨层测试的修正

原测试手工提供`active_stop_quantity`，掩盖了采集边界缺失。本轮新增的是**原始REST形状 → 现有解析器 → CcxtVenueAdapter → TicketLifecycleFacts → PG maintenance → Reducer/Command**的针对性连接验证，不再只给理想化末端字典。

原适配器的`_position_open_orders`只生成订单投影，没有携带terms；因此仅调整缩进不足以修复。本轮对保护单直接解析其原始REST条款并校验精确身份。条件价与保护标记价分开，身份或价格不符不进入BE。

## 4. 数据与权限变更

### 4.1 未部署的0024修订

- `brc_owner_device_write_evidence`增加`result_kind/result_payload`，区分pending、authorized、no_change；关联结果一次完成后不可修改。
- `brc_owner_binding_limits`保存有界失败时间数组及到期索引；每次绑定有界清理旧桶，不保存明文IP或令牌。
- `brc_management_receive_epochs`保存scope/epoch/ordinal、原始接收水位、连接/缺口/分页事实和完成时间；接收事实不等于管理授权。旧原始stream事件表与现有应用水位保持唯一权威。
- API不能INSERT接收epoch、不能签发绑定grant，不能UPDATE公钥、签名、请求体；内核和API都受证据不可变触发器约束。

**这些修改仅适用于尚未部署的0024本地候选。** 没有修改已部署0019/0023迁移，也没有为当前运行增加跨schema fallback。

### 4.2 恢复门禁不绕过

新增接收持久化属于0024产品能力，本批不能当作可直接塞回0023的热补丁。此前多票/错误namespace Command的正式只读终态恢复与迁移编排仍须独立闭合，不能为了装新代码删除Ticket、水位、预算或改Command payload。Owner没有批准改变联合上线范围。

## 5. 实际验证

| 检查 | 结果 | 证据 |
|---|---|---|
| 单元与架构 | **2333通过** | `.local/gemini-review-fixes-20261117/unit-architecture-final.log` |
| 受影响PG回归与既有Lifecycle | **65通过** | `pg-regression-final.log`；设备/权限/API/减量/迁移/Feed及原TP/Runner维护 |
| Owner Console真实查询归因 | **2通过** | `read-attribution.log`；不重复算入上述64 |
| 真实手机客户端故障函数 | **通过** | `pending-green.log`与单元测试；没有使用真实Cookie或交易所 |
| 本地Nginx HTTP | **通过** | `nginx-http.json`；/mobile/为200 text/html，app.js/sw.js为200 application/javascript |
| Ruff / Mypy / JS语法 / diff | **通过，Mypy 276源文件** | 本地命令输出；不产生发布认证manifest |
| 整包Integration / Full-chain / R4 / API / Static发布认证 | **未执行** | 遵守Owner代码审查门 |
| 服务器或交易所变更 | **零** | 本轮只修改本地代码和可丢弃数据库；本地Nginx验证容器已删除 |

测试集合存在重叠，不加总成一份产品认证；没有把本地fake撮合当Binance协议保证。

## 6. 仍未完成，不能冒称已修好整个产品

1. 完整operation runner、正式减仓准备/派发及实际fill ledger/保护采集尚未完成；当前拒绝真实减仓派发。
2. Hedge减仓与Stop交错期间的持续保护能力尚未取得充分协议证据；本轮没有采用“先减仓再尽快换Stop即可安全”的推断。
3. 发送前设备撤销检查、全部手机持仓操作/表单/结果通知与真机PWA持久性仍需完整交付；历史授权证明不替代当前发送授权。
4. 源0023多票终态恢复、待处理错误namespace Command及联合升级编排仍未完成；不能直接运行旧静态脚本的历史schema检查来部署本产品。
5. 本批只修已确认代码缺陷及相邻边界，不实施策略A、Regime、选币切换、放宽Stop、加仓或扩风险。

## 7. 复审重点

- 接收持久化与应用按序之间是否还有重连/分页/重启缺口，特别是pending原始事件不能被健康状态遮蔽。
- retired protection是否确实由原Command和已持久化终态证据绑定，不能只凭新Stop ID就删旧单身份。
- immutable触发器、列权限、no_change与原结果重放是否贯通；GET receipt不变更授权/nonce。
- 客户端unknown持久锁与服务端锁后时间复核是否共同阻止迟到请求复活。
- 存在明确关闭门的未实现能力不得被当作当前真实业务路径验收。

相关：[首轮审查交接](2026-11-17-owner-mobile-review-handoff.md)、[统一实施计划](2026-11-16-seoul-recovery-and-cooperation-implementation-plan.md)。
