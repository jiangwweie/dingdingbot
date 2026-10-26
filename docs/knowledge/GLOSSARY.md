# 领域术语表

> **定位：解释性知识库** · [知识地图](README.md)。当前生产状态见 [MAIN_CONTROL_ROADMAP.md](../current/MAIN_CONTROL_ROADMAP.md)。

## 业务、身份与准入

**本表的含义来自当前模型与实现**，不表示任何指定策略当前获得资金权限。

| 术语 | 中文理解与边界 | 定义来源 |
| --- | --- | --- |
| **StrategyGroup / Version / EventSpec** | 策略族、语义版本、某个方向和周期的可执行事件定义；注册不是启用 | [Registry](../../src/trading_kernel/domain/strategy_registry.py#L106) |
| **RuntimeProfile / RuntimeScope** | 账户与环境配置；具体 Event、币种、Universe 和 Policy 的运行范围 | [ports](../../src/trading_kernel/application/ports.py)、[pg_models](../../src/trading_kernel/infrastructure/pg_models.py) |
| **Observation / Fact** | 收盘行情观察与条件/保护参考事实；事实不直接占用资金 | [观察](../../src/trading_kernel/application/observe_strategy_scope.py#L246) |
| **Exposure Episode** | 一次连续合格机会的身份；上升沿或 session 决定重置与去重 | [exposure_episode](../../src/trading_kernel/domain/exposure_episode.py) |
| **StrategySignal** | 冻结 Event、币种、方向、时间、Episode、事实与出生权限的机会记录 | [StrategySignal](../../src/trading_kernel/domain/signal.py#L80) |
| **Readiness / first_blocker** | 当前 scope 的可准入判断及第一个阻断解释，随当前事实变化 | [ingest_signal](../../src/trading_kernel/application/ingest_signal.py#L806) |
| **AdmissionDecision** | 某个 Signal 的最终准入或拒绝事实，记录当时组合占用与原因 | [admission_decision](../../src/trading_kernel/domain/admission_decision.py) |
| **CapacityClaim** | 在当时账户快照、规则、风险和权限下冻结的一次容量声明 | [CapacityClaim](../../src/trading_kernel/domain/capacity.py#L233) |
| **Ticket** | 不可变执行合同，冻结资金、入场与退出规则及来源身份；不是订单回执 | [TradeTicket](../../src/trading_kernel/domain/ticket.py#L38) |
| **Netting Domain** | `venue + account + instrument + position_side`；同方向同域最多一个活动 Ticket | [NettingDomain](../../src/trading_kernel/domain/identities.py#L24) |
| **Exposure Family / Capacity B** | 跨策略风险家族与策略侧容量政策；成员数量不等于可持仓数量 | [exposure_family](../../src/trading_kernel/domain/exposure_family.py)、[capacity](../../src/trading_kernel/domain/capacity.py) |
| **ENTRY lane** | 全局新入场串行所有权；保护完成前不能按“已发请求”提前释放 | [Reducer](../../src/trading_kernel/domain/reducer.py#L124)、[issue_ticket](../../src/trading_kernel/application/issue_ticket.py#L97) |

## 执行、保护与闭合

| 术语 | 中文理解与边界 | 定义来源 |
| --- | --- | --- |
| **Exchange Command / generation** | 先持久化再派发的外部写意图；ENTRY 只允许一代 | [commands](../../src/trading_kernel/domain/commands.py) |
| **Aggregate / Reducer / Effect** | 当前生命周期投影；纯事件转移；待由持久化层实现的副作用描述 | [aggregate](../../src/trading_kernel/domain/aggregate.py)、[reducer](../../src/trading_kernel/domain/reducer.py)、[effects](../../src/trading_kernel/domain/effects.py) |
| **Unit of Work（UoW）** | 一组本地数据库改动的提交或回滚边界，不包含网络请求 | [PostgresKernelUnitOfWork](../../src/trading_kernel/infrastructure/pg_unit_of_work.py#L133) |
| **Initial Stop / TP1 / Runner** | 初始保护、第一段止盈、余仓管理；均由 Ticket 冻结的规则约束 | [exit_policy](../../src/trading_kernel/domain/exit_policy.py) |
| **ExitProfile / EventExitBinding** | 不可变退出方案；版本化的 Event→方案绑定；切换只影响新签发 | [ExitProfile](../../src/trading_kernel/domain/exit_policy.py#L183)、[绑定切换](../../src/trading_kernel/application/owner_control.py#L539) |
| **OUTCOME_UNKNOWN** | 请求可能已到交易所而结果不明；不能当作拒绝或安全重发 | [未知恢复](../../src/trading_kernel/application/recover_unknown_command.py#L93) |
| **Incident / Runtime Fence** | 安全异常与其阻断范围；版本或 schema 不匹配时隔离写者 | [incident_blocking](../../src/trading_kernel/domain/incident_blocking.py)、[runtime_fence](../../src/trading_kernel/application/runtime_fence.py) |
| **Reconciliation** | 依据外部订单、成交和持仓核对内部状态并推进清理 | [reconcile_ticket](../../src/trading_kernel/application/reconcile_ticket.py#L132) |
| **Settlement / Review** | 结算资源及完成复盘；Review 可追加修订，当前指针只有一个 | [settle_ticket](../../src/trading_kernel/application/settle_ticket.py) |
| **Shadow Outcome** | Signal 所属的只读市场路径研究；不是模拟 Ticket、真实交易或实际净收益 | [shadow_outcome](../../src/trading_kernel/domain/shadow_outcome.py)、[projector](../../src/trading_kernel/application/project_shadow_outcome.py) |

## 选币与控制

| 术语 | 中文理解与边界 | 定义来源 |
| --- | --- | --- |
| **Selection Spec / Job / Snapshot** | 算法契约、某一期有租约的计算任务、不可变选币结果 | [generic_selection_spec](../../src/trading_kernel/domain/generic_selection_spec.py)、[run_instrument_selection](../../src/trading_kernel/application/run_instrument_selection.py) |
| **Epoch / Generation** | 一次 Owner 模式意图的代际；将某个结果安装成运行币池的物化过程 | [selection_authority](../../src/trading_kernel/domain/selection_authority.py)、[generic_materialization](../../src/trading_kernel/domain/generic_materialization.py) |
| **StrategyUniverse / current pointer** | Event 的版本化交易成员集合；当前指针决定新信号来源 | [strategy_universe](../../src/trading_kernel/domain/strategy_universe.py) |
| **ComparisonUniverse** | MPG/MI 的相对强弱比较集合，独立于允许交易的成员集合 | [comparison_universe](../../src/trading_kernel/domain/comparison_universe.py) |
| **Warming / Certification** | 收盘事实预热与只读可执行条件认证；预热期间不产生新 Signal | [observe_strategy_scope](../../src/trading_kernel/application/observe_strategy_scope.py)、[certify_universe_instrument](../../src/trading_kernel/application/certify_universe_instrument.py) |
| **Selection Authority** | 有时间和 Event/Universe 边界的选币交易权限；Snapshot 本身不是权限 | [selection_authority](../../src/trading_kernel/domain/selection_authority.py) |
| **ENTRY Vacuum** | 币池切换时阻止新入场并排空未完成 ENTRY 的持久化栅栏 | [strategy_entry_vacuum](../../src/trading_kernel/domain/strategy_entry_vacuum.py) |
| **Normal / Recovery Transition** | 连续权限下的正常交接；真实缺口后的未来收盘恢复及 rebase | [dynamic_selection_timing](../../src/trading_kernel/domain/dynamic_selection_timing.py)、[coordinator](../../src/trading_kernel/application/coordinate_selection_materialization.py) |
| **Owner Authorization / Operation** | 认证后不可变授权记录；异步受控动作及其进度投影 | [owner_control](../../src/trading_kernel/domain/owner_control.py) |

## 阅读分析：最容易混淆的关系

1. **有 Signal 不等于有 Ticket**：中间仍有当前 Authority、账户事实和容量准入。
2. **有 Command 不等于已成交**：PREPARED、派发结果、成交和持仓事实是不同阶段。
3. **已平仓不等于已终态**：余单、资源释放、结算和 Review 仍可能未完成。
4. **选币完成不等于交易权限生效**：Snapshot、物化、预热及 Authority 分别取证。

这些关系分别由[主链路](TRADE_LIFECYCLE.md)、[动态选币](DYNAMIC_SELECTION.md)和[数据模型](DATA_MODEL.md)展开。
