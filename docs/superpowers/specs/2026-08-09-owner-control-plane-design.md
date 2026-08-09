---
title: OWNER_CONTROL_PLANE_DESIGN
status: APPROVED_FOR_IMPLEMENTATION_PLANNING
approved_by: Owner
approved_at: 2026-08-09
---

# Owner Control Plane 设计

## 1. 决策

在现有只读 Owner Console 上新增一个独立的 **Owner Control Plane**，提供三项后端能力：

1. StrategyGroup 暂停与恢复；
2. 全局新 ENTRY 暂停与恢复；
3. 受控一键平仓全部当前活动 Ticket。

三个能力完成本地验证并部署后，才公开部署包含控制页面的前端。

Owner Control Plane 继续服从唯一 Trading Kernel 链：

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

Control API 不加载币安凭证，不直接调用交易所，不接受数量、价格、订单类型、账户、币种、方向或 Ticket 列表作为受控平仓输入。

## 2. 产品目标

Owner 每天可以通过一个公网 HTTPS 页面完成以下运营动作：

- 暂停或恢复任意已注册 StrategyGroup 的新准入；
- 暂停或恢复全部策略的新 ENTRY；
- 在明确授权后，请求退出全部当前活动 Ticket；
- 查看每项控制的配置状态、有效状态、阻断原因、授权身份和异步进度；
- 在不重启 Observation、Entry、Lifecycle 或 Reconciliation Worker 的情况下完成日常控制。

这些控制不改变策略语义、不创建另一条交易链，也不把 Owner 变成人工订单操作员。

## 3. 非目标

第一版不提供：

- 单 Ticket、单币种、单方向或自选列表平仓；
- 前端输入数量、价格、订单类型、reduce-only 参数或交易所订单 ID；
- Instrument 或 StrategyUniverse 原地修改；
- 杠杆、保证金模式、资金规模或风险比例修改；
- 暂停 Observation；
- systemd 启停按钮；
- API 直接访问币安私有接口；
- 自动刷新、WebSocket、SSE 或后台前端轮询；
- 自动恢复全局 ENTRY；
- 一键平仓后的自动重新开仓；
- 多 Owner、角色管理或审批流。

## 4. 已知基础

当前系统已有以下可复用能力：

| 需求 | 当前基础 | 本设计新增 |
| --- | --- | --- |
| 全局 ENTRY 控制 | Owner Policy `new_entry_submit_enabled` | 活动持仓期间的安全切换、API 和恢复门槛 |
| StrategyGroup 权威 | Registry、Runtime Scope、Ticket 冻结身份 | 独立运营控制 current/event 权威 |
| 受控退出 | `request_exit()`、Controlled Exit、deployment drain | Owner 授权、全局暂停联动、持久操作与页面进度 |
| 真实交易写入 | durable Exchange Command、Lifecycle | 不变；继续由 Lifecycle 独占 |
| 外部闭环 | Reconciliation、Settlement、Review | 控制操作完成状态投影 |
| 公网认证 | 密码、TOTP、Session | 写操作鉴权、TOTP step-up、CSRF 与幂等 |
| 公网入口 | 现有 Nginx HTTPS 域名 | `/trading/` 与 `/api/owner/v1/` 精确路径 |

## 5. 控制权威与优先级

### 5.1 单一权威

| 决策 | 权威 |
| --- | --- |
| 全局是否允许新 ENTRY | `brc_owner_policy_current.new_entry_submit_enabled` |
| 某 StrategyGroup 是否允许新 ENTRY | StrategyGroup Entry Control current projection |
| 是否允许交易所写入 | Runtime Fence、runtime capability、Worker 身份和当前安全事实 |
| 一键平仓授权 | 不可变 Owner Authorization |
| 一键平仓进度 | Owner Control Operation current projection、Ticket/Event/Command 当前事实 |
| 实际退出数量、方向和订单 | 冻结 Ticket 与 Lifecycle reducer |

不得使用前端状态、Nginx 配置、Session、文件或 systemd 服务状态替代 PostgreSQL 控制权威。

### 5.2 优先级

有效新 ENTRY 权限按以下顺序判定：

```text
Runtime Fence
> global new_entry_submit_enabled
> StrategyGroup Entry Control
> Runtime Scope
> StrategySignal / market facts
```

任一更高层级关闭，下面的 enabled 状态都不能绕过。

### 5.3 配置状态与有效状态

前后端同时区分：

- `configured_state`：该控制自身的值；
- `effective_state`：综合所有更高优先级控制后的最终结果；
- `first_blocker`：第一个阻止新 ENTRY 或控制操作的准确原因。

示例：

```text
SOR-001 configured_state = enabled
SOR-001 effective_state = paused_by_global_entry
```

## 6. 页面设计

### 6.1 一级导航

Owner Console 从四个一级页面扩展为五个：

```text
总览
信号
交易
复盘
控制
```

“控制”是唯一承载业务写操作的一级页面。Signals、Trades、Review 和 Ticket 因果详情保持只读。

### 6.2 总览页控制摘要

总览首屏增加一个紧凑的 **运行控制状态**区，不放危险操作按钮：

| 字段 | 示例 |
| --- | --- |
| 全局 ENTRY | 运行中 / 已暂停 |
| 已暂停策略 | SOR-001 / 无 |
| 活动仓位 | 2 |
| 受控平仓 | 无 / 等待 / 进行中 / 阻断 |
| 数据时间 | 最近手动刷新时间 |

整个区域链接至 `/controls`。总览不提供暂停、恢复或平仓按钮，避免首屏误触和视觉拥挤。

### 6.3 控制页面结构

控制页面按风险从低到高纵向排列：

```text
页面标题与数据时间
-> 全局 ENTRY 控制
-> StrategyGroup 控制表
-> 当前控制操作
-> 危险操作区：受控平仓全部仓位
-> 最近控制记录
```

页面继续使用已确认的币安式暗色 System B：紧凑密度、低饱和状态色、无 SaaS 阴影和装饰性图标卡。

### 6.4 全局 ENTRY 控制

卡片字段：

- configured state；
- effective state；
- Policy version；
- 最近变更时间；
- 最近变更原因；
- Entry Worker 只读状态；
- 活动 Ticket 数；
- 当前 blocker。

按钮：

- 运行中显示 `暂停新开仓`；
- 已暂停显示 `恢复新开仓`；
- 状态矛盾、请求进行中或缺少当前事实时按钮 disabled，并显示 blocker；
- 不提供 systemd 启停按钮。

### 6.5 StrategyGroup 控制表

每个当前注册 StrategyGroup 一行：

| 列 | 含义 |
| --- | --- |
| StrategyGroup | 精确 Registry identity 与显示名 |
| Event 摘要 | 当前 active Event 的 timeframe 与 side |
| configured state | enabled / paused |
| effective state | running / paused_by_strategy / paused_by_global / fenced |
| 活动 Ticket | 当前非终态数量 |
| 最近变更 | 时间与 reason |
| 操作 | 暂停或恢复 |

第一版以 StrategyGroup 为粒度。当前 SOR-001 的两个活动 Event 都是 15m，因此暂停 SOR-001 会同时暂停 LONG 与 SHORT 15m 新准入。

### 6.6 暂停确认

暂停是收缩权限，使用当前有效 Owner Session 和确认弹窗即可：

```text
暂停 SOR-001

暂停后不再允许该 StrategyGroup 创建新的 ENTRY。
Observation 和已有 Ticket 不受影响。

原因：Owner 手动暂停

[取消] [确认暂停]
```

暂停请求不使用乐观 UI。只有 API 事务提交成功后才更新页面状态。

### 6.7 恢复确认

恢复会扩大真实新 ENTRY 权限，必须执行 TOTP step-up：

```text
恢复 SOR-001

恢复后，新的有效信号可以创建 Ticket 和 ENTRY。

Google Authenticator 验证码
[      ]

[取消] [确认恢复]
```

全局 ENTRY 恢复弹窗额外展示 Runtime Identity、Entry Worker、Incident、unknown Command、活动 Ticket 和已暂停 StrategyGroup 的当前检查结果。

### 6.8 危险操作区

受控平仓放在控制页面底部独立红色边界区域，不与普通暂停按钮混排：

```text
受控平仓全部仓位

暂停所有新 ENTRY，并请求退出全部当前活动 Ticket。
当前活动仓位：2

[受控平仓全部仓位]
```

页面其他位置不重复提供该按钮。

### 6.9 受控平仓三段式确认

#### 第一步：刷新权威事实

点击后发起一次明确的手动读取，页面缓存不能决定平仓范围。

#### 第二步：展示服务器冻结范围

服务器返回有界 Active Ticket 摘要和 snapshot digest：

```text
本次操作将处理 2 个活动 Ticket：

ADAUSDT · SHORT · protected
BTCUSDT · LONG · protected

操作后全局 ENTRY 将保持暂停。
```

前端不能编辑、勾选或移除 Ticket。

#### 第三步：重新授权

必须同时提交：

- 当前 snapshot digest；
- TOTP；
- 确认文本 `确认平仓全部持仓`；
- 独立 idempotency key。

确认按钮使用红色，TOTP 和确认文本不进入日志。

### 6.10 操作进度

一键平仓是异步 Operation，API 接受不等于外部已平：

```text
全局 ENTRY 已暂停
-> Owner Authorization 已提交
-> ExitRequested 已请求
-> EXIT Command 已接受
-> Exchange Flat 已确认
-> 残余保护单已清理
-> Budget / Domain 已释放
-> Settlement / Review 已完成
```

页面只在手动刷新时读取新进度，不轮询、不使用 SSE 或 WebSocket。

### 6.11 最近控制记录

控制页底部显示最近 20 条有界事件：

- operation kind；
- target；
- result；
- authorization identity；
- reason；
- created time；
- completed or blocked time；
- first blocker。

不显示 TOTP、Session、DSN、账户密钥或完整敏感 payload。

### 6.12 响应式边界

- 1280px 及以上使用紧凑表格；
- 小于 1280px 时 StrategyGroup 行改为上下两层，不产生页面横向滚动；
- 危险确认弹窗最大宽度有界；
- 操作按钮不得因长 reason 或 identity 被挤出视口；
- 控制页不增加右侧超长抽屉。

## 7. API 总体契约

### 7.1 路由

```http
GET  /api/owner/v1/controls

POST /api/owner/v1/controls/strategies/{strategy_group_id}/pause
POST /api/owner/v1/controls/strategies/{strategy_group_id}/resume

POST /api/owner/v1/controls/entry/pause
POST /api/owner/v1/controls/entry/resume

POST /api/owner/v1/controls/exposure/flatten-all/preview
POST /api/owner/v1/controls/exposure/flatten-all

GET  /api/owner/v1/control-operations/{authorization_id}
GET  /api/owner/v1/control-events
```

这些路由属于三项后端能力；preview、status 和 event list 是完成安全交互所需的只读辅助接口。

### 7.2 通用写请求字段

```json
{
  "expected_version": 5,
  "reason": "owner_manual_pause",
  "idempotency_key": "owner-request:..."
}
```

恢复和平仓额外包含 TOTP。TOTP 只存在于请求处理内存中，禁止持久化和日志记录。

### 7.3 通用写响应

```json
{
  "request_id": "owner-request:...",
  "authorization_id": "owner-authorization:...",
  "status": "committed",
  "configured_state": "paused",
  "effective_state": "paused",
  "version": 6,
  "first_blocker": null,
  "updated_at_ms": 1780000000000
}
```

写响应不返回数据库 DSN、账户身份、Session、TOTP、币安凭证或未经裁剪的内部 payload。

### 7.4 HTTP 状态

| HTTP | 语义 |
| ---: | --- |
| 200 | 幂等重复或已处于目标状态 |
| 201 | 新授权或新 Operation 创建 |
| 400 | 请求形状或确认文本无效 |
| 401 | 未登录或 Session 无效 |
| 403 | TOTP step-up 失败或权限不足 |
| 409 | expected version、snapshot digest 或当前状态冲突 |
| 422 | 当前权威事实完整，但操作被安全 blocker 阻断 |
| 429 | 登录、TOTP 或写操作限速 |
| 503 | 当前 PostgreSQL、Runtime Identity 或必需 Worker 事实不可用 |

所有错误使用稳定的外部 code，不把 SQL、路径、凭证、账户 identity 或异常堆栈暴露给浏览器。

## 8. 后端能力一：StrategyGroup 暂停与恢复

### 8.1 数据模型

新增：

```text
brc_strategy_entry_control_events
brc_strategy_entry_controls_current
```

Event 是 append-only，Current 是唯一有效投影。

建议字段：

#### Event

- `strategy_entry_control_event_id`
- `strategy_group_id`
- `control_version`
- `operation`: `pause | resume`
- `target_state`: `paused | enabled`
- `authorization_id`
- `reason`
- `payload`
- `created_at_ms`

#### Current

- `strategy_group_id`
- `entry_state`: `paused | enabled`
- `control_version`
- `last_event_id`
- `reason`
- `updated_at_ms`

每个 StrategyGroup 只有一个 Current row。缺少 Current row 的已注册 StrategyGroup 按 `enabled` 读取，但生产 seed 必须为每个当前 StrategyGroup 安装显式 enabled row，避免长期依赖缺省语义。

### 8.2 事务

```text
validate current Session / optional TOTP
-> lock exact StrategyGroup control row
-> validate Registry identity and expected_version
-> insert immutable Owner Authorization
-> append control Event
-> update Current projection
-> commit
```

事务内无网络 I/O。

### 8.3 Entry 执行点

Entry 在三个位置检查控制：

1. Ready Signal 候选选择前；
2. CapacityClaim / Ticket 原子提交前；
3. durable ENTRY Command 交易所派发前。

暂停提交后：

- 尚未创建 Claim 的 Signal 保持观察事实，但不准入；
- 尚未提交 Ticket 的候选生成拒绝 AdmissionDecision；
- 已有 Ticket 但 ENTRY Command 尚未派发时，最终重检阻断派发并走现有无暴露终态清理；
- 已经开始交易所派发的 Command 不能假装消失，必须由 Reconciliation 证明结果；
- 已有外部暴露继续安装保护并正常管理。

### 8.4 Owner 状态

StrategyGroup 暂停映射为 Owner 状态 `paused`，first blocker 使用精确控制 identity，不把暂停误报为市场无机会或 Runtime Incident。

## 9. 后端能力二：全局 ENTRY 暂停与恢复

### 9.1 权威复用

全局控制继续使用：

```text
brc_owner_policy_current.new_entry_submit_enabled
brc_owner_policy_events
```

不得新建第二个全局开关。

### 9.2 暂停

暂停允许在活动 Ticket 和非零仓位存在时提交，因为它只收缩新 ENTRY 权限。

事务：

```text
lock Owner Policy
-> validate expected policy version
-> create Owner Authorization
-> append monotonic Owner Policy Event
-> set new_entry_submit_enabled=false
-> increment policy version
-> commit
```

暂停不停止 Entry Worker，不创建 Runtime Fence，不改变 Observation、Lifecycle 或 Reconciliation。

### 9.3 恢复

恢复扩大真实资金权限，必须通过 TOTP step-up，并在同一时刻验证：

- Runtime commit、schema 和 seed identity 一致；
- exchange command capability 可用；
- Entry Worker active；
- 无 Runtime Fence；
- account mode 为 independent sides；
- margin mode 为 cross；
- 无 runtime-scoped open Incident；
- 无 unresolved 或 outcome_unknown ENTRY Command；
- 当前 Owner Policy 其他资本和风险字段未变化；
- 当前活动 Ticket 与 Reservation 未超过 Policy 限额。

恢复可以在已有受保护仓位存在时执行；活动仓位本身不是 blocker。Entry 后续仍按当前容量、Family、方向和 Netting Domain 规则决定是否准入。

### 9.4 Policy 版本

每次 pause/resume 都单调增加 Policy version。已形成但未提交的 Claim 因 Policy version 过期而失效，不能沿用旧权限派发 ENTRY。

## 10. 后端能力三：受控一键平仓

### 10.1 产品语义

`flatten-all` 表示：

```text
暂停全局新 ENTRY
并请求退出当前 Runtime Profile + Venue + Account 下的全部活动 Ticket
```

一键平仓不是同步交易所 RPC，也不承诺 API 返回时已经外部全平。

### 10.2 API 与交易写入隔离

Control API 只持久化：

- Owner Authorization；
- 全局 ENTRY pause；
- 冻结的 Active Ticket 集合和 snapshot digest；
- pending Owner Control Operation。

Control API 不直接写 Exchange Command，也不调用币安。现有 Lifecycle Worker 消费 pending Operation，调用 Kernel `request_exit()` 边界并生成 durable reduce-only EXIT Command。

### 10.3 Owner Authorization

新增不可变：

```text
brc_owner_authorizations
```

字段：

- `authorization_id`
- `purpose`
- `owner_identity`
- `authentication_strength`: `session | totp_step_up`
- `request_digest`
- `target_scope`
- `idempotency_key`
- `authorized_at_ms`

受控平仓 purpose 固定为：

```text
owner_flatten_all
```

Authorization 保存 Runtime Profile、Venue、Account 控制范围和 preview digest。
阶段 B 冻结的 Ticket ID 集合属于 Operation Current，不回写不可变
Authorization。两者都不保存账户密钥、TOTP、Session 或币安凭证。

### 10.4 Operation 权威

新增：

```text
brc_owner_control_operation_events
brc_owner_control_operations_current
```

Operation 状态：

```text
validating
-> pending
-> claimed
-> exits_requested
-> exit_in_progress
-> reconciliation_pending
-> settlement_pending
-> review_pending
-> completed
```

异常终态：

```text
blocked
needs_intervention
```

Current row包含有界 `target_ticket_ids`、snapshot digest、first blocker、version 和更新时间；Event 保存全部状态变更。

### 10.5 Preview

`flatten-all/preview` 是只读接口，读取：

- 当前全局 ENTRY；
- Entry lane；
- 活动 Ticket；
- Aggregate status；
- protected quantity；
- unresolved Command；
- open Incident；
- 当前 Runtime Identity。

返回有界显示摘要和 `snapshot_digest`。Preview 不创建 Authorization 或 Operation。

### 10.6 两阶段提交

提交时服务器重新计算完整 snapshot，不信任前端 Ticket 列表。一个 HTTP 请求执行
两个有界 PostgreSQL 事务，确保即使平仓被阻断，全局 ENTRY 仍然保持暂停。

#### 阶段 A：先提交权限收缩

```text
validate Session + TOTP + confirmation text
-> recompute and compare preview snapshot digest
-> lock Owner Policy
-> set global new_entry_submit_enabled=false if needed
-> append Owner Policy Event if changed
-> insert immutable owner_flatten_all Authorization
-> insert validating Control Operation and Event
-> commit
```

#### 阶段 B：冻结平仓范围

```text
lock exact Control Operation and global Entry lane
-> recompute current bounded Active Ticket set
-> reject unresolved ENTRY dispatch / unknown outcome / blocking Incident
-> classify every Ticket
-> freeze target Ticket identities and target digest
-> move Operation to pending or blocked
-> append Operation Event
-> commit
```

阶段 B 失败或被安全规则阻断时，阶段 A 不回滚。Operation 持久化为
`blocked` 并记录 first blocker，全局 ENTRY 保持暂停。两个事务内都没有交易所
I/O。

### 10.7 Ticket 分类

| Ticket 状态 | 一键平仓处理 |
| --- | --- |
| `position_protected` | eligible |
| `runner_protected` | eligible |
| 已在 EXIT / Reconciliation / Settlement / Review | in_progress，纳入 Operation |
| terminal | 不属于 Active set |
| 未保护暴露、unknown outcome、异常部分成交 | blocked |
| 当前事实矛盾 | blocked |

任一活动 Ticket blocked，则整个 Operation 不提交 Exit request，并进入
`blocked`。页面必须清楚显示“ENTRY 已暂停，平仓未启动”。

如果阶段 B 发现活动 Ticket 集合已经为空，Operation 直接进入 `completed`，
外部语义为 `already_flat`，全局 ENTRY 仍保持暂停。

### 10.8 Lifecycle 消费

Lifecycle 使用当前 certified runtime identity 领取 pending Operation：

```text
lock exact Operation
-> lock frozen target Aggregates in stable Ticket identity order
-> revalidate every target
-> atomically append ExitRequested for every eligible target
-> persist durable EXIT effects
-> move Operation to exits_requested
-> commit
```

该事务只处理最多 Policy `max_concurrent_tickets` 个 Ticket，当前模型上限有界。网络派发继续发生在事务提交之后。

如果领取后任一目标变为 blocked，不允许只请求部分新 EXIT；Operation 进入 `blocked`，已有 independently in-progress Ticket 继续正常运行。

### 10.9 Reconciliation 完成条件

Operation 只有在全部目标同时满足以下条件时才能 `completed`：

- exchange position flat；
- 无残余 ENTRY、STOP、TP、EXIT 或 cancel order；
- Ticket terminal；
- Budget Reservation released；
- Netting Domain released；
- Reconciliation matched；
- Settlement complete；
- Review complete；
- 零 open Incident；
- 零 unresolved 或 outcome_unknown Command。

### 10.10 完成后的 ENTRY 状态

一键平仓完成后 `new_entry_submit_enabled` 保持 false。Owner 必须通过独立的全局 ENTRY Resume API 才能恢复新开仓。

## 11. 鉴权与 Web 安全

### 11.1 操作强度

| 操作 | Session | TOTP step-up | 说明 |
| --- | ---: | ---: | --- |
| StrategyGroup pause | 必须 | 否 | 收缩权限 |
| Global ENTRY pause | 必须 | 否 | 收缩权限 |
| StrategyGroup resume | 必须 | 必须 | 扩大权限 |
| Global ENTRY resume | 必须 | 必须 | 扩大真实资金权限 |
| Flatten all | 必须 | 必须 | 会间接产生真实 EXIT |

### 11.2 请求防护

- Session Cookie 使用 Secure、HttpOnly、SameSite=Strict；
- 写请求验证 exact Origin 和 Host；
- 写请求要求 `Content-Type: application/json`；
- 每次写请求有 canonical idempotency key；
- TOTP 使用最小时间窗口并防止同一验证码重复用于高风险操作；
- Nginx 对登录、TOTP resume 和 flatten-all 分别限速；
- 请求 body、TOTP、Cookie 和 Authorization 不进入 access/error log；
- 新登录继续使旧 Session 失效；
- API 重启或 Session key 轮换继续使所有 Session 失效。

### 11.3 PostgreSQL 最小权限

Owner API 使用两个数据库身份：

1. Read role：现有只读页面与控制状态查询；
2. Control role：仅允许精确 Owner Control、Strategy Control、Owner Policy transition 和 Authorization/Operation 写入。

Control role 无权直接写 Exchange Command、Position、Settlement 或 Review。Lifecycle/Reconciliation 继续使用 Kernel runtime identity 完成这些写入。

## 12. Nginx 与部署路径

### 12.1 公网路径

复用现有 HTTPS 域名：

```text
https://jiaoyingpan.cloud/trading/
https://jiaoyingpan.cloud/api/owner/v1/
```

现有其他服务路径不变。Nginx 使用更精确的 location：

```text
/trading/       -> static Owner Console
/api/owner/v1/  -> Unix Socket Owner API
/                -> existing gateway
```

### 12.2 前端 base path

- Vite base：`/trading/`；
- React Router basename：`/trading`；
- SPA fallback：`/trading/index.html`；
- fingerprinted assets：`/trading/assets/`；
- API client base：`/api/owner/v1/`；
- 不启用 CORS。

### 12.3 独立 release

Owner Console 不再依赖 Kernel `/opt/brc/current`：

```text
/opt/brc/owner-console/releases/<commit>
/opt/brc/owner-console/current
```

Owner API 继续使用独立 Unix Socket、systemd service 和 resource slice。静态前端无 Node.js 常驻进程。

### 12.4 凭证

目标主机使用 root-owned、mode 0600 的 systemd credential source 和 `LoadCredential=`。凭证不得进入 Git、环境文件、命令行、日志或 Nginx 配置。

## 13. 性能边界

- Owner API 一个进程；
- Read pool 最多 2 个连接；
- Control pool 最多 1 个连接；
- API 无后台轮询；
- Lifecycle 复用现有 cadence 消费 pending Operation；
- 控制查询 exact key 或有界列表；
- StrategyGroup 列表受 Registry 当前数量上限约束；
- Control event list 默认 20、最大 100；
- Active Ticket target 数不超过当前 Policy capacity；
- 前端只在登录、导航、手动刷新或明确写操作时请求；
- 不增加 Redis、WebSocket、SSE、文件输出或独立控制 Worker。

## 14. 故障与恢复

### 14.1 API 在控制事务前失败

无数据库状态变化，Owner 可使用同一 idempotency key 重试。

### 14.2 API 在提交后响应丢失

同一 idempotency key 返回已提交 Authorization 或 Operation，不重复追加控制事件。

### 14.3 Pause 与 ENTRY 并发

以 PostgreSQL 提交和最终派发重检为准。已经进入未知交易所结果的 Command 交给 Reconciliation，禁止盲目重发或假装暂停已追溯生效。

### 14.4 Flatten Operation 被 Lifecycle 领取后进程退出

Operation lease 到期后可由同一 certified Lifecycle runtime 继续；ExitRequested 和 durable Command 的幂等身份阻止重复 EXIT。

### 14.5 EXIT rejected 或 outcome unknown

沿用现有 Incident 和 Reconciliation 语义。Operation 进入 `needs_intervention`，全局 ENTRY 保持暂停。

### 14.6 Owner API 不可用

四个 Kernel Worker 不受影响。已提交控制继续生效，已提交 Operation 继续由 Lifecycle/Reconciliation 推进。

### 14.7 Nginx 或前端回退

回退 Console 不回退 PostgreSQL 控制事实，也不恢复 ENTRY。Owner Control Plane 的运行权威不依赖网页是否可访问。

## 15. Migration 与首次上线

### 15.1 计划 Migration

新增一个前向 revision：

```text
0004_owner_control_plane
```

它只新增 Owner Control 相关表、约束和索引，不重写历史 Ticket、Command、Position、Settlement 或 Review。

### 15.2 首次发布必须全平

首次引入新 schema 和 Entry/Lifecycle 行为仍服从当前 stopped、flat、forward-only 发布契约：

- zero nonterminal Ticket；
- zero non-flat position；
- zero residual order；
- zero active Reservation；
- zero unresolved Command；
- zero open Incident。

功能首次上线不是 active-position handover。上线后日常 pause、resume 和 flatten-all 才是无需停 Worker 的运行态操作。

### 15.3 推荐首次部署顺序

```text
完成设计与实施计划
-> 本地实现和聚焦验证
-> 临时全局 Entry Fence 或等待自然形成全平窗口
-> 全平预检
-> 部署 0004 + 新 Kernel
-> 通过服务器本地 Unix Socket 验证三个 Control API 能力
-> 验证四个 Worker 与 Runtime Identity
-> 部署 Owner Console 独立 release
-> Nginx 加入 /trading/ 与 /api/owner/v1/
-> 公网认证与控制验收
```

后端三个能力未完成服务器内部验收前，不公开控制页面。

## 16. 回退与 Fix-forward

- 前端或 Nginx 问题：回退 Owner Console release，不改变控制事实；
- Owner API 问题：停止独立 API service，Kernel 继续运行；
- Control API 已暂停 ENTRY 后失败：保持暂停，修复后由 Owner 明确恢复；
- 0004 已迁移后不降级 schema，采用 fix-forward；
- Lifecycle/Reconciliation 问题：保持全局 ENTRY 暂停并修复 certified runtime；
- 不恢复旧 schema Reader、双写、兼容 adapter 或手工 lifecycle DML。

## 17. 聚焦测试与验收

### 17.1 后端核心

1. StrategyGroup pause 阻止新 Claim/Ticket/ENTRY；
2. StrategyGroup resume 在 TOTP 和当前事实通过后恢复准入；
3. Global pause 在活动受保护 Ticket 存在时成功；
4. Global resume 对 Runtime Fence、Incident 和 unknown Command fail closed；
5. Pause 与 ENTRY 派发竞态按提交顺序处理；
6. 旧 Policy version Claim 不能派发；
7. Flatten preview 不产生写入；
8. Flatten submit 冻结服务器当前 Ticket set；
9. 任一活动 Ticket blocked 时不产生部分新 ExitRequested；
10. Lifecycle crash/resume 不重复 EXIT；
11. Reconciliation 完成前 Operation 不显示 completed；
12. Flatten 完成后 Global ENTRY 保持 paused。

### 17.2 HTTP 与认证

- 未登录写请求拒绝；
- pause 使用有效 Session；
- resume 和 flatten 要求 TOTP step-up；
- TOTP、Cookie 和请求 secret 不进入日志；
- idempotency 重试不重复事件；
- expected version 和 snapshot digest 冲突返回 409；
- Origin、Host、Content-Type 和限速正确。

### 17.3 前端

- Overview 只显示摘要，不出现危险按钮；
- Controls 显示 configured/effective state；
- Pause、Resume、Flatten 对话框内容准确；
- Flatten 不提供 Ticket 选择、数量、价格或订单类型；
- blocker 明确显示；
- 不使用乐观 UI；
- 不自动轮询；
- 1280、1440、1920 三个视口无横向溢出；
- 原有 Signals、Trades、Ticket、Review 路由无视觉回归。

### 17.4 生产验收

- 三项能力先通过 Unix Socket 内部调用；
- Nginx exact paths 不影响现有 gateway；
- Owner API 不加载 Binance credentials；
- Control role 不能直接写 Exchange Command；
- 四个 Worker 保持 active 且无 restart growth；
- Console 资源保持在独立 slice 预算内；
- 一次 pause/resume 非资金演练和一次受控真实 flatten 需分别由 Owner 明确授权。

## 18. 已拒绝方案

- API 直接执行 `systemctl stop/start Entry` 作为正常控制；
- 修改 Strategy Registry status 表示运营暂停；
- 修改 Active StrategyUniverse 或 Runtime Scope 模拟暂停；
- 新建第二个全局 ENTRY 开关；
- 前端直接写 PostgreSQL；
- Control API 持有币安 API Key；
- Control API 直接构造 EXIT order；
- 前端提交 Ticket、币种、方向、数量、价格或订单类型；
- 一键平仓后自动恢复 ENTRY；
- 按钮使用乐观成功状态；
- 自动刷新、WebSocket、SSE 或新的控制 Worker；
- 为首次上线引入 active-position handover、双写或兼容 Reader。

## 19. Owner 已确认范围

- StrategyGroup 暂停与恢复都必须实现；
- 全局 ENTRY 暂停与恢复都必须实现；
- 受控一键平仓全部当前活动 Ticket 必须实现；
- 一键平仓不提供单笔选择和订单参数；
- 一键平仓后全局 ENTRY 保持暂停；
- 新增独立 Controls 一级页面；
- Overview 只增加控制摘要；
- 复用现有 HTTPS 域名和 Nginx 路径代理；
- 三个后端能力完成后再公开部署前端。
