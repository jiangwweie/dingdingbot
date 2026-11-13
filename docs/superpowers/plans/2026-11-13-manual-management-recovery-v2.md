# 首尔管理采集与静态策略暂停恢复修复及验证

## 1. 授权、目标与交付边界

Owner 在当前任务明确批准修复：管理采集时钟误判、静默期间重连失效、CPM 暂停围栏残留、运行健康展示不足。此文记录本地实现与验证；生产身份、部署证据与当前姿态仅由 [MAIN_CONTROL_ROADMAP](../../current/MAIN_CONTROL_ROADMAP.md) 持有。

**本轮交付本地代码、测试及前向迁移；部署前提交 Owner 复核。** 不产生测试订单，不修改东京，不生成 Owner Resume/TOTP，不代替自然交易验收。既有 5x、钱包分配、风险上限、策略退出参数及永久 MANUAL 规则不变。

## 2. 事实与根因

| 问题 | 已确认依据 | 修复落点 |
| --- | --- | --- |
| 合法接收误判 | 脱敏真实 ALGO_UPDATE：tick=1794547055266、receipt=1794547055267、transaction=1794547055248；接收发生在等待认证/锁期间，比旧轮次起点晚 1ms | 持有采集所有权锁后重新采时，按实际处理时点校验；拒绝真正未来的接收/交易时间 |
| 协议 gap 无法自动恢复 | 当前 CCXT `Client.close()` 取消 `watch_orders` 等待的 Future；旧 loop 将其当作整个任务退出，start 又只检查 task 是否为 None | 单一接收 loop 拥有重连；Event 主动唤醒静默 watch，区分子 Future 取消与宿主取消，有界关闭并移除确切旧 client |
| CPM 已恢复但围栏残留 | static 无 pending 的 Materialization cadence 提前返回；旧 OPEN 围栏未被推进；旧状态机没有静态 Owner Resume 的合法解除终态 | 常驻 Materialization cadence 推进 OPEN→DRAINING_ENTRY→OWNER_PAUSED→RESOLVED_OWNER_RESUME，数据库验证真实授权及排空 |
| “运行中”掩盖交易阻塞 | feed gate 拒绝时 Entry 仅返回 facts_unavailable；overview 依赖 Monitor；认证顶层 pass 主要表示完整性 | 共享 feed 判定，Overview/V2/认证输出独立就绪状态与原因/时间/水位；Entry 返回 detail 并保存信号 readiness 事实 |

事实依据为本次只读生产采样、原条件复现与当前代码。原始采样保存在本地 `.local/manual-health-20261113/`，不提交为生产权威。脱敏协议片段纳入 `tests/trading_kernel/fixtures/manual_management_recovery/receive_clock_event.json`，保留时间差，替换订单身份。

## 3. 实现约束

### 3.1 时钟、接收与主动恢复

1. 通过既有 Runtime Fence 后取得消息快照；按 scope 持有管理接收 advisory lock 和当前 feed 行锁，再采样实际处理时间。
2. 不添加“允许晚几毫秒”的容差；`transaction > receipt` 或 `receipt > processing` 仍是协议错误。
3. 原始输入及水位必须提交后才 ACK；有错误的 epoch 不得通过后来正常轮次清洗成 ready。
4. 私有管理连接主动重建，不等待下一条订单消息。关闭超时、失败、内部 Future 取消均保持门禁并进入有界重试；宿主任务取消仍停止。
5. 同 epoch 重连请求幂等，已结束的接收任务可以重建；旧 client 的迟到连接、关闭、消息回调不得污染新连接。
6. 未确认旧 epoch 队列满时背压，不通过 deque 淘汰未持久化批次。新 epoch 不补造旧间断区间的覆盖证明。

### 3.2 静态 Owner 暂停恢复

适用于 CPM／MPG／MI／BRF2 的 **generation-free、static_baseline、无 pending** Owner 暂停围栏；不替代已有 Dynamic/ORB/Authority Gap 恢复流程。

- OPEN 和 DRAINING_ENTRY 按既有正式 drain 路径推进，未知 ENTRY 结果与未结束保护安装仍阻塞。
- 解除需真实原始 pause、当前 latest resume 及其前一 pause 的授权记录和控制版本相互匹配；Resume 必须为 `totp_step_up`。
- Selection 配置自原围栏以来未变，无待生效切换、未完成 Materialization、未决 Command、缺失 Aggregate 或 entry-drain blocker。
- 支持 worker 尚未处理时的连续真实暂停/恢复；保留最初 fence 与所有真实控制历史，不伪造新授权。
- 追加 `RESOLVED_OWNER_RESUME` 事件后以版本 CAS 更新投影。数据库 BEFORE guard 验证精确 proof、不可变字段及事件；延迟约束禁止只写事件不完成投影。
- 已解除记录不可改写；不创建 Selection Authority，不修改已有 Ticket、MANUAL、订单或预算。解除只是恢复原静态基线的一个门禁，其他准入条件继续独立核验。

### 3.3 健康与日志

`ManagementFeedReadiness` 独立表达 required、ready、connection_state、blocker_code、blocked_since、last_success、lease、epoch、persisted/applied 水位。

- Overview 在同一只读事务通过精确 scope/current epoch 查询；新增覆盖索引，避免账户全历史扫描。
- V2 主控概览显示“管理采集受限／新开仓受阻”、原因及已持续分钟数；接收 ready 也不表示其他准入门禁已经通过。
- ENTRY 在外部行情/账户查询前保存具体 first_blocker 和有界 feed 事实，日志带同一 detail。
- 认证继续保留完整性 `status`，另行输出 `management_feed`；`entry_recovery_ready` 仍严格依赖 feed ready，官方 promoter 门禁不放宽。

## 4. 0023 前向迁移

**0022_wallet_margin_allocation → 0023_management_recovery**。新增一个覆盖查询索引、Vacuum 状态/形状约束及授权/事件守卫函数；不改写任何历史业务行。

迁移要求 stopped、Owner 真实暂停、空仓、内部票终态、无挂单/未决 Command/事故/预留、Entry lane idle。数据库硬门禁与官方安装器各自核验；降级被拒绝。维护围栏不能代替 Owner 暂停。

安装器与 runtime identity 的精确升级路径纳入本地测试。新增版本继续保持管理采集、退出配置、通知及钱包分配合同，不回退或隐式失去既有能力。

## 5. 验证矩阵

| 边界 | 正向验收 | 必须拒绝或保留的情况 |
| --- | --- | --- |
| 接收时钟 | 真实消息在 tick 起点之后到达仍持久化并应用 | 真未来 receipt/transaction 仍 gap，durable 后 ACK，再发起重连 |
| 私有流恢复 | fake 及实际 CCXT watch/Future/close 无新订单即可换 epoch | 关闭挂起、迟到旧回调、重复重连、队列背压、宿主停止 |
| Owner 静态恢复 | 四策略 × 先恢复/先排空；连续两次暂停恢复；重复 cadence 幂等 | 未 Resume、未 drain、pending Selection、伪造 proof/event、孤立解除事件 |
| 数据库升级 | 全部源列/源行原值保留；精确身份部署 | ENTRY 开启时拒绝；forward-only；运行身份/采集合同保持 |
| 展示与追溯 | 零 Incident 也显示 feed blocker；ENTRY 原因可读可回放 | 不能把完整性 pass/服务 alive/feed ready 等同于全部交易正常 |
| 回归 | Unit/Architecture、Integration、完整交易链、Ruff/Mypy、V2 tests/build | 永久 MANUAL 禁写、未知结果不重发、历史缺口不补造 |

按 test-first 先保留对应 RED，再实施 GREEN。完整执行命令、数量及失败修正记录在本地证据目录 `.local/manual-management-recovery-20261113/`。正式精确版本认证与生产安装验收属于发布阶段，未以本地 fixture 代替。

## 6. 发布后验收与失败处理

1. Owner 复核候选；精确 committed HEAD 完成 Kernel R4、Owner API 与 V2 static 认证。
2. 刷新首尔 host/account/PG/systemd/交易所只读身份与现场事实，执行真实 Owner pause、自然 flat/terminal-clean、停写、源数据保留证明及正式安装。
3. 只读确认新 epoch ready、租约新鲜、persisted=applied、旧 gap 保留；CPM 原围栏经正式 cadence 排空并由既有 Resume 授权解析为解除终态。
4. 完成规定事实读取与官方 promoter。Owner 真实 Resume/TOTP 后核验当前授权与接收就绪，等待自然信号验证；不制造订单。
5. 迁移/认证/身份/保护门禁失败则保持暂停；迁移后禁止恢复旧 schema writer。网络持续不可用仍受阻并明确告警，不承诺外部依赖永不失败。

## 7. 本轮验证结果

### 7.1 候选冻结前验证

| 检查 | 实际结果 |
| --- | --- |
| Unit / Architecture | 2217 通过；先前发现的迁移清单、代码锚点及跨测试文件 helper 引用已修正 |
| 全量 Integration 初轮 | 1971 通过，1 项旧查询数量断言失败；共享 feed 读取合并后查询预算固定为 10，新断言已定向通过。此轮不标记为全量 PASS |
| 新增/变更边界 | 真实时钟输入与未来拒绝、恢复/状态机/迁移/认证/ENTRY及只读 Overview 按最终源码复测；最终数量以实际日志为准 |
| 完整交易链 | 77 通过 |
| 前端 | 148 通过、V2 production build 通过 |
| 静态与数值 | Ruff、Mypy 263、diff check、Golden 961 snapshots / 23064 rows、core parity 通过 |

源代码冻结后运行正式精确候选认证。此前失败及修正均保留在本地日志，不能用定向通过改写原全量运行结果。本地验证不构成生产恢复或安装成功声明。


### 7.2 精确候选正式认证完成

| 检查 | 最终实际结果 |
| --- | --- |
| Kernel R4 | PASS：Unit/Architecture **2217**，Integration **1982**，完整交易链 **77**；Ruff、Mypy **263**、diff check、Golden/core parity **961 snapshots / 23064 decisions** 全部通过 |
| Owner API / V2 static | 两份正式认证 PASS，并与 Kernel 绑定相同精确候选；V2 **148** 项测试及 production build 通过 |
| 独立资源约束组 | **4** 项串行通过，保留原资源限制 |
| 变更边界集成 | 最终源码 **94** 项通过，另补认证强度不足拒绝用例通过；该新增用例也已纳入精确 R4 全量集合 |
| 真实历史源演练 | 之前已导出的首尔终态快照恢复到本产品可丢弃 PG；**102 表 / 29939 行**迁移原值保留，Owner/Command/Ticket 不改写；旧 CPM 围栏用已有真实 Resume 授权完成正式状态机解除，重复执行幂等 |
| 本地发布准备 | 三份认证精确身份校验及官方 prepare_manual_release 通过；输出明确 deployment_authorized=false，不等于生产安装 |

首轮全量集成的失败和后续定向修正仍保留；最终完整重跑为 **1982/1982 PASS**。精确候选身份见路线图。认证期间源码冻结，后续记录文档提交不替代该 runtime 候选。

### 7.3 最终状态与验收边界

- **本地修复、回归、三项正式认证完成；尚未部署。**
- 当前任务的生产操作均为只读，生产写入 **0**，无服务重启、策略控制、数据库修补或交易所写入。
- 首尔只读复核仍能观察到旧版管理采集 gap 与 CPM OPEN 围栏；交易所核验空仓且无普通/条件订单。采样时刻及当前运行身份仅由路线图记录。
- 没有新增业务参数决策；部署复核、真实 Owner 暂停/恢复与安装后的现场门禁仍须完成。外部网络、交易所持续不可用时会保持受阻；本地认证不承诺外部依赖永远正常。
- 历史快照演练仅证明该历史授权与数据库状态可由正式路径恢复，不代表生产已执行或已观察到自然交易验收。
