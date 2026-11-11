# MA-EXIT-REGIME-01 编码与验证记录

## 目标与执行范围

**Owner 已于本线程授权“按照文档实施编码”。**本记录对应[人工版设计](../specs/2026-11-10-manual-exit-regime-release-design.md)和[实施方案](2026-11-10-manual-exit-regime-release-implementation-plan.md)，实现工作区为人工产品独立分支。生产身份、安装状态仍只由[路线图](../../current/MAIN_CONTROL_ROADMAP.md)维护。

本轮本地编码、测试、离线回放，不执行服务器安装、策略恢复或交易所写入。首次安装仍需真实 Owner 暂停、自然终态清洁、停止全部 writer、单线保全迁移、配置 TOTP、正式 promoter 和真实 Resume，不能把本地通过当现场授权。

## 已落地的软件边界

| 工作包 | 实现与验证入口 | 对外语义 |
|---|---|---|
| ME-00 | 本地人工基线、工作区检查、正式安装器与命令行启动测试 | 沿人工独立分支，不修改东京 |
| ME-01 | `exit_execution.py`、`exit_configuration.py`、`0020_manual_exit_regime_v1` | Decimal 最小量提升及50%上限；新 Profile 显式 execution；旧终态 hash不补造 |
| ME-02 | `reconcile_post_fill_stress`、`PostFillExitPlan`、PG唯一计划表／投影 | 初始保护先确认，完整 ENTRY 的准确 command／order／trade集合冻结实际VWAP与原始S |
| ME-03 | TP累计成交事件、连续保护、原期限／guards、精确余仓退出 | 部分不保本；满额只申请新保护，确认后才Runner；未知先对账；不能证明部分成交后保护安全则AUTO按真实余量安全退出 |
| ME-04 | 管理权与派发最后门禁、CCXT transport context、归属回归 | MANUAL零新增写；REVIEW暂停；已发结果只读记账；不盲重试 |
| ME-05 | `exit_regime.py`、Observation共享刷新、PG快照／指针 | 三LONG使用50根原生闭合4h；新边界失效；矛盾窗口保留快照并撤回许可 |
| ME-06 | 参数预览／TOTP／原子配置／请求回执／数量示例、每票计划API与前端 | 六Event退出与三Gate一次提交；原策略暂停／Owner方向／资金不变；旧票冻结 |
| ME-07 | 独立research目录中的离散回放及baseline逐行比较 | AUTO反事实与人工真实结果分开；不贷记未来返现，不重演动态补位 |
| ME-08 | 固定候选完整认证、源码审查、迁移和反例验证 | 认证结果以实际完成证据为准，下表持续登记 |

### 部分成交的保守边界

**首发不假定超配固定数量止损在精确 Hedge Mode 下必然仍可执行。**读到准确当前止损恰好覆盖真实余量时继续保留；仅在替换安全已被证明时使用正式先挂后撤序列。无法证明安全覆盖／替换时，仍有AUTO权限的交易走原 durable安全退出，数量为真实余量；保留旧保护，实际退出后再按原收尾清理。该保守分支是设计第6.2节允许的失败收敛，不把“部分成交”本身声明为Owner接管。

MANUAL与REVIEW不继承上述AUTO关闭权限。TP提前终态且归属未知时进入明确REVIEW，不把外部撤单猜成程序故障后强平。已确认外部动作仍由管理证据链永久MANUAL。只有真实完整目标成交才有保本资格。

### 现场与自然证据

本地记录型／协议／PG反例证明软件边界，不能证明未来限价单必然成交、手机已收到通知或真实App已接管。首尔账户准确仓位／挂单／规则及Hedge Mode保护序列仍在部署时读取；自然AUTO和真实App闭环分别待现场事件留证，不制造订单。

## 主要反例与证据

- BTC0.019／0.007最小TP0.001，实际比例5.263%／14.286%；恰50%允许，超过拒绝，Q保持不变。
- 实际ENTRY均价60010而Ticket参考60000，SOR TP使用实际1.2R=61222；Ticket原字段不变，一票只生成一计划。缺准确fills时保留保护并AUTO安全收敛。
- 部分TP累计单调、重复／旧累计不重复减仓；绝对期限与完整TP同轮只按真实余仓退出，无重复BE／EXIT。
- CCXT市场加载／限速等待后转MANUAL，transport门禁阻止实际发送；请求已发送后禁止底层自动重试并保留unknown。
- 配置第六个绑定失败全部回滚；初始参数固定；后续仅改变某Event参数，其他Event继承原值；配置不恢复暂停策略。
- readonly认证保全exact seed，并验证额外Owner revision的类型范围、源绑定、继承、产品／账户、preview及授权摘要，非法额外Profile不通过。
- 0019→0020的源列逐表保全；Owner仍暂停；新增权威表为空；残余lane／资金占用也拒绝迁移。

## 研究来源与限制

[人工版离散TP1验证报告](/Users/jiangwei/Documents/final-strategy-research/analysis/2026-11-10-manual-exit-regime-discrete-validation/验证报告.md)及同目录`provenance.json`、`quantity_audit.json`、`summary.json`。

历史基线652条结果逐行复现，0差异；最终纯函数重新核对316条可执行拆分。四策略134个数量样本中10个需要提升，实际<=50%。当前规则为历史研究代理，不能作为首尔当前资格。新价格按保存的交易所tick规范化，旧理想5%模型采用成交精度推测tick，两者不当作完全相同输入。收益是固定历史集合AUTO反事实、模型费用后资金费前金额，不代表人工接管收益；不为达到正收益调整已确认参数。

## 验证账本

| 层次 | 当前证据 | 边界 |
|---|---|---|
| Focused RED/GREEN | 新数量、v2合同、部分TP、实际R、发送竞态、原子配置和迁移门禁分别观察失败并修复 | 各项日志在本地 `.local/manual-exit-*`，测试数量不是自然交易证明 |
| Unit／architecture | Unit／architecture／Owner interfaces 2178项阶段通过；最终计数见正式候选日志 | 未冻结SHA前不冒充正式证书 |
| Integration | 旧fixture已补真实配置与成交前置条件；全量结果以固定候选认证日志为准 | 通过后再完成ME-08 |
| Full-chain | 75项完整回归通过；新六Event完整退出合同单独通过 | 后续行为变化使相关旧证据失效，按最终候选复核 |
| Owner API／UI | API鉴权／TOTP反例、OpenAPI生成、TypeScript／生产构建与前端141项回归通过 | 与Kernel的精确候选证据分别维护 |
| 静态／R4／Golden | 最终冻结候选必须由正式工具认证，结果存原生manifest | 不复用生产旧证书 |
| 首尔安装／激活／Owner恢复 | **本轮未执行** | 需要部署时真实Owner操作与现场门禁 |
| 自然AUTO／真实App／手机回执 | **本轮未验证** | 保留真实事件证据，不制造Signal／订单 |

### 最终候选认证前排查

首次R4未完成：完整integration记录两项失败并在尾部出现锁等待，未生成Kernel认证manifest，不能用于发布。已删除管理权测试夹具重复初始化；相关23项回归通过，schema尾部37项及Universe相关50项通过。逐项重跑前326项通过后主动停止，以便把修正纳入新SHA并直接运行正式认证；此次中断不作为全量通过证据。Ruff、Mypy（253个源文件）及diff检查通过。

周期性资源审计与标准R4分开：首次并发运行撞到单实例资源锁；串行`four_processes`在本机600秒预算内未完成，由watchdog停止，尚未通过。未扩大预算或绕过锁，不能据此宣称资源审计完成。最终正式认证结果以精确SHA对应的原生manifest及日志为准。

锁等待已由单个`activated_between_claim_ticket-CPM-RO-001`稳定复现：入场fixture在同一事务首次创建Owner配置／EventExitBinding，持有Event FK锁，再同步等待独立Universe事务的`FOR UPDATE`，形成测试自身等待。已将Owner配置作为已提交前置条件移到入场事务之前；四策略claim／Ticket间切换、已激活替换和Owner暂停共20项通过，原竞态断言保留，生产锁和门禁未改。旧失败缓存中仍存在的两项可选正式测试也复跑通过。此前新SHA的R4再次中断且无证书；Owner API／static证书不替代Kernel认证。

### 实际采集与协议补充验证

新增`test_ma50_refresh_lifecycle.py`经实际refresh函数和PG验证50根闭合4h采集、窗口复用、跨边界旧许可失效、不可用30秒节流和恢复。RED显示持续失败每次重试产生2条重复monitor事件（2→4）；修正为保留当前健康语义、只刷新尝试时间，只有实际状态变化才追加事件。相关配置集成13项、采集恢复与调度组合79项通过。

新增`test_actual_fill_protocol.py`：原始USD-M userTrades→当前安装CCXT4.5.56的`parse_trade`→实际适配器→CompleteEntryFills；6项覆盖多笔VWAP、重复／乱序、超过JS安全整数的订单／成交ID、错订单／方向／时间／数量和冲突重复，全部通过。不是直接向kernel提供理想化统一dict。

周期性`capacity_v0_resource_safety`串行两项已通过（MPG／MI，54.41秒）；四进程资源演练仍单独核实，不因这两项通过声称整个资源portfolio通过。发现并停止本工作区早先中断遗留的本地资源容器，保留其有界日志；未操作其他产品PG或服务器。

四进程资源重查补充：当前正式Observation对到期Dynamic交接的旧Static close返回`selection_activation_pending_current_close`并重试；旧资源用例却等待旧Static已经消费close后的`GENERIC_CURRENT_CLOSE_ALREADY_CONSUMED`。普通集成已有`static_observer_first`反例，明确要求旧close不得被消费。因此本次有界重查在采集日志／PG零Ticket、零Command、零开放Incident后主动停止；未放松运行时交接门禁、未扩600秒预算，也未把旧资源断言超时记作通过。该周期性资源用例的合同更新与完整资源认证仍未完成，不能由标准R4替代。

完整候选integration最终1903通过／1失败，无锁等待。唯一失败为`test_runtime_fact_workers::test_lifecycle_worker_reads_tp1_facts_and_replaces_runner_protection`：记录型fixture使用1008ms等合成时间，新增真实派发门禁却默认采样当前墙钟，正确拒绝过期lease／命令，返回DEFERRED。已只在该测试显式注入逐轮推进的同一合成时钟，原Initial Stop／TP／Runner／撤旧保护断言均保留；单项GREEN。未修改真实运行时间、命令有效期或发送校验。完整R4需对修正后SHA重新执行，前次失败不签证书。
