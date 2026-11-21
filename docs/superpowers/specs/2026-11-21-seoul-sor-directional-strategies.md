# 首尔小时 SOR 多空独立策略设计

**2026-11-21 · 设计规格。** Owner 已确定两项业务规则：小时 SOR 拆为两个普通策略组；BTC 4h MA50 是多头新开仓的固定门槛。下文的新 ID、选币身份和迁移顺序是本设计选取的工程方案。配套验收见[关键负面测试案例](2026-11-21-seoul-sor-directional-strategies-negative-tests.md)。

## 1. Owner 实际使用的两个策略

| 控制台条目 | 新 ENTRY 条件 | 开启／暂停 |
|---|---|---|
| **SOR-多（小时）** | 本币小时收盘向上穿越开盘区间上沿，且 BTC 最近闭合 4h 收盘严格高于 SMA50；其余准入条件全部满足 | 沿用普通策略组控制 |
| **SOR-空（小时）** | 本币小时收盘向下穿越开盘区间下沿；其余准入条件全部满足 | 沿用普通策略组控制 |

操作路径与 MPG 相同。暂停持续至 Owner 主动恢复。现有全局 ENTRY 控制、普通策略恢复授权和最终发送检查继续适用。开启仅授予参与准入的资格。BTC 均线翻转和暂停均只影响新 ENTRY，已有 AUTO 票继续执行冻结的止损、TP1 与 Runner；已确认外部接管的 MANUAL 票由 Owner 管理，系统继续观察、结算与复盘。首版范围仅首尔小时 SOR；同小时限一笔、自动收紧预算及向空头增加均线过滤均属其他策略决策。（依据：[策略控制接口](../../../src/trading_kernel/interfaces/owner_console_http/routes/controls.py)、[首尔管理权约束](../../../AGENTS.md)。）

## 2. 身份、归属和共享边界

### 2.1 Registry 与历史

以下为待注册技术 ID。版本按既有 `sgv:<group>:v1`、`event_spec:<group>:<event>:v1` 形式生成；生产路由只接受 Registry 中登记的完整身份。

| 对象 | StrategyGroup | Event／方向 | 归属 |
|---|---|---|---|
| 新多头 | `SOR-1H-LONG-001` | `SOR-1H-LONG`／long | 独立控制、信号、准入、Ticket 和收益统计 |
| 新空头 | `SOR-1H-SHORT-001` | `SOR-1H-SHORT`／short | 独立控制、信号、准入、Ticket 和收益统计 |
| 原小时组 | `SOR-1H-001` | 原有两个完整 Event Spec | 历史可查，停止产生新 ENTRY，禁止经控制台或 API 恢复 |
| 原日内旧组 | `SOR-001` | 原有事件 | 保持既有退役状态 |

新旧 Event 短名可相同，完整 Event Spec、策略版本与绑定必须有别。两个新组共享 `opening_range` Exposure Family、账户总预算、同方向预算及首尔同账户同品种互斥。拆组不会给任一方向预留独占仓位。现有方向风险规则的事件作用域、Owner Policy 允许范围、RuntimeScope、回放和研究识别名单均须显式登记新 ID；不能依赖名称前缀继承许可。（现状：[Registry 合同](../../current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md)、[方向风险作用域](../../../src/trading_kernel/domain/directional_risk.py)。）

### 2.2 选币、交易日和首次突破

保留 **UTC 00:00—01:00** 首小时区间、原闭合 K 线连续性校验与上下穿越算法。多头使用区间低点作初始止损参考，上沿作 TP1 前收回边界；空头相反。选币可以共享纯计算和相同截止时点的行情输入，各方向的成员物化、Scope、选择版本、Authority 及缺口审计要绑定各自的新组和 Event。现有 Static 和 Dynamic 路径都须能解析新身份；同输入、同模式的成员结果应与原规则一致。一个方向暂停、切换或重新建立权限，只能更新该方向的控制和消费记录。（现状：[小时检测器](../../../src/trading_kernel/domain/detectors/sor_1h.py)、[现有成对物化与快照身份](../../../src/trading_kernel/domain/orb_session_selection.py)。）

同一交易日、同币、同方向的首次触发仍遵循既有小时规则。MA50 拒绝、未获准入或恢复策略都不额外派发第二次机会。暂停或维护期间的输入由普通恢复／缺口审计机制核验；已消费或缺口内已出现的首次触发不得追单。切换当天，即使新策略 ID 从未产生过票，也要从当前会话闭合路径和旧方向已知消费事实建立新权限；不能将换 ID 当作新交易日。无法证明连续性时，该方向等待既有恢复条件或下一合格会话，不因此阻塞证据完备的另一侧。历史记录保留原身份。

### 2.3 实现者需要替换的三个旧假设

1. **一个选币配置固定输出一对 Event。** 为新组各建一个有独立身份的选币 Spec，指向同一计算实现。新 Spec 的目标事件集合只有本组的一个 Event；生成 Snapshot、物化 Generation、加载当前成员和处理缺口时，用同一组／Spec／epoch／session 链校验归属。Static 来源版本和 Dynamic 模式意图分别保留来源依据，不能把旧组待处理的激活任务改名后继续执行。（现有入口：[小时选币](../../../src/trading_kernel/domain/orb_session_selection.py)。）
2. **“配置中找不到事件”可以按无过滤继续。** 将新多头列为必须具备正式配置和绑定的 Event。预览、激活、运行时检查分别验证强制过滤属性；对于新多头，配置不存在、缺该事件、无证明或提交关闭均不得放行。旧配置修订保留原有成员和摘要，当前修订通过正式配置链绑定新事件。（现有入口：[配置预览](../../../src/trading_kernel/application/exit_configuration.py)、[运行时检查](../../../src/trading_kernel/application/exit_regime.py)。）
3. **只有旧组 ID 才使用小时选币和控制台展示。** 控制、启动、选币预览、历史过滤及认证使用显式支持的策略身份。两个新事件都进入方向风险的版本化作用域；迁移保留 Owner 原方向选择、账户限额和历史准入证明，按新规则身份生成当前证明。（现有入口：[方向规则](../../../src/trading_kernel/domain/directional_risk.py)、[控制与选币 API](../../../src/trading_kernel/interfaces/owner_console_http/routes/controls.py)。）

## 3. MA50 的唯一口径与执行位置

**数据源**为 BTCUSDT USD-M 原生 4h 成交 K 线。以动作时点之前最近的 UTC 四小时闭合边界为末端，取连续、完整的 **50 根**收盘价，包含末根，以 Decimal 计算算术平均。有效区间沿用 `observed_at_ms <= now_ms < valid_until_ms`。末根 `close > SMA50` 才放行；相等、低于、缺根、重复、断档、未闭合、过期均不能授权新的多头 ENTRY。空头只检查自身适用门槛。均线是准入条件，小时突破仍按原检测器记录。（依据：[均线快照与边界](../../../src/trading_kernel/domain/exit_regime.py)、[共享准入检查](../../../src/trading_kernel/application/exit_regime.py)。）

| 阶段 | 目标行为与权威证据 |
|---|---|
| 配置与绑定 | 当前配置以两个新方向事件替代旧组的两项，其他事件原样保留。新多头强制 MA50、新空头不启用。固定名单、默认值、参数模型、配置预览和激活同时更新。绑定和 Profile 按各方向原**生效参数**派生，保留策略触发和退出数值口径。 |
| 准入与发票 | 复用现有 MA50 数据源与检查；记录 Event、配置修订、快照时间、窗口摘要及判定原因。新多头配置缺项、绑定错配、配置关闭均应阻断。现有通用检查对未列出的 Event 可能返回无门槛，实施时必须显式覆盖新多头。 |
| 最终发送 | 用当前有效授权、绑定和 MA50 证据复核。已有 Claim 或准备中的 Command 不能凭旧快照发送。失败按已有拒绝／对账路径处理，保持 durable Command 单次发送语义。 |
| 已持仓 | 初始止损、TP1、Runner、到期退出及手工接管按 Ticket 冻结绑定与管理模式执行；生命周期无需读取当前 BTC 均线来授权退出。 |

缺失、过期、有效但不偏多分别沿用 `ma50_unavailable`、`ma50_stale`、`ma50_not_bullish` 等现有原因。配置身份错误应单独报配置或绑定问题。界面允许同时显示“策略已开启”和“本次新开仓被 MA50 拦截”。（实现入口：[退出配置](../../../src/trading_kernel/domain/exit_configuration.py)、[发票复核](../../../src/trading_kernel/application/issue_ticket.py)。）

## 4. 前向迁移、界面与交付

1. **切换前**按首尔发布流程冻结源身份和认证证据，核对账户／数据库、当前两侧的成员来源、选择意图、有效退出参数、配置修订、共享预算和历史摘要。执行分支从核实后的首尔 Kernel 基线建立。涉及内核、数据库及 API，走对应的完整发布路径。
2. **在既有停写、空仓、保留校验条件下迁移。** 先封住旧小时组的所有新 ENTRY 路径。新实体、退出配置修订、绑定、Scope 和控制按前向迁移创建；两个新组初始均暂停，由既有 Owner 启用流程分别恢复。保留原控制／配置修订、旧 Snapshot、Ticket、Command、Review 及其引用。迁移只建身份与权限基础，不能制造信号、开仓或复制旧在途操作。中断后按实际提交边界恢复；可见状态须满足旧新不能同时获得开仓权限。失败时保持 ENTRY 受限并前向修复。
3. **策略列表与历史查询**沿用现有桌面／移动控制接口，策略状态按真实组 ID 读取。交易筛选、统计、详情、因果链与旧链接用 Ticket 原生组 ID；默认现役列表显示两个新组，历史查询可选原小时组。核对 UI 中枚举、显示名、选币路由及生成的 API 类型，退出参数保存须往返不丢失其他策略配置。
4. **交付次序**为 Registry／迁移与保留校验 → 单方向选币、会话与权限 → 配置、准入与发送 → 控制台与报表 → 首尔发行认证。每一层先建立配套规格里的失败用例再实现；生产阶段以正式认证、发布和自然事件为证据。上线后的首个自然多／空机会按实际证据记录，尚未发生的情形保留为待验证。（依据：[工程运行约束](../../../AGENTS.md)、[Owner 运行模型](../../current/OWNER_RUNTIME_OPERATING_MODEL.md)、[首尔实施基线](../plans/2026-11-06-app-manual-takeover-v1-implementation-plan.md)。）

**交付判据**：任一方向可以独立启停；新多头两个开仓检查点都需要有效且偏多的 MA50；空头原策略仍可运行；组合风险、冻结票生命周期和历史统计保持一致。具体 Given／When／Then 与验证层见[关键负面测试案例](2026-11-21-seoul-sor-directional-strategies-negative-tests.md)。
