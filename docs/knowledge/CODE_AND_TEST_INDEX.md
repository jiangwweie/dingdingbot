# 代码阅读与测试证据索引

> **定位：解释性知识库** · [知识地图](README.md)。代码基准和标签定义见入口；本页的本地测试不证明生产状态，当前生产验收见 [MAIN_CONTROL_ROADMAP.md](../current/MAIN_CONTROL_ROADMAP.md)。

## 如何使用证据索引

**先找业务问题，再按入口 → 模型/事务 → 测试阅读。**链接中的 Python 行号指向基准实现的定义行，可由文档架构检查发现被移动的定义。测试文件存在表示覆盖可查；只有[本轮验收记录](MAINTENANCE.md)列出的命令才表示本轮实际执行。

## 主链路代码与测试

| 阅读单元 | 函数 / 类型入口 | 对应模型、接口或状态 | 关键验证入口 |
| --- | --- | --- | --- |
| **策略注册语义** | [registered_strategy_contracts](../../src/trading_kernel/domain/strategy_registry.py#L258) | RegisteredStrategyContract、required_facts、Event | [Registry unit](../../tests/trading_kernel/unit/test_strategy_registry.py)、[Registry parity](../../tests/trading_kernel/architecture/test_event_registry_parity.py) |
| **观察调度** | [run_observation_worker_once](../../src/trading_kernel/interfaces/observation_worker.py#L88) | scope 租约、observation_generation、收盘时间 | [真实观察到稳定 Signal](../../tests/trading_kernel/integration/test_observation_to_signal.py#L585) |
| **市场检测与事实** | [observe_strategy_scope](../../src/trading_kernel/application/observe_strategy_scope.py#L246) | MarketSnapshot、Fact、Warming、Episode | [未闭合尾部不产 Signal](../../tests/trading_kernel/integration/test_observation_to_signal.py#L528) |
| **Signal 生成** | [produce_strategy_signal](../../src/trading_kernel/application/produce_strategy_signal.py#L27) | StrategySignal、Episode、fact_digest | [重复信号幂等](../../tests/trading_kernel/integration/test_signal_to_ticket.py#L236) |
| **摄取与权限** | [ingest_signal](../../src/trading_kernel/application/ingest_signal.py#L806)、[validate_signal_authority](../../src/trading_kernel/application/ingest_signal.py#L844) | Readiness、Registry、scope/version、选择权限 | [权限矩阵](../../tests/trading_kernel/integration/test_signal_to_ticket.py#L287) |
| **候选仲裁** | [select_entry_candidate](../../src/trading_kernel/application/select_entry_candidate.py#L40) | bounded ready candidates、排序快照 | [arbitration](../../tests/trading_kernel/unit/test_arbitration.py)、[到期候选修复](../../tests/trading_kernel/integration/test_signal_to_ticket.py#L405) |
| **ENTRY 工作者** | [run_entry_worker_once](../../src/trading_kernel/interfaces/entry_worker.py#L108) | EntryFactsSource、EntryAdmissionSnapshot | [runtime fact workers](../../tests/trading_kernel/integration/test_runtime_fact_workers.py) |
| **最终准入** | [issue_ready_signal](../../src/trading_kernel/application/issue_ready_signal.py#L110) | AdmissionDecision、Policy、组合使用量、ExitBinding | [拒绝无交易权限](../../tests/trading_kernel/integration/test_signal_to_ticket.py#L500) |
| **定量与冻结 Claim** | [build_capacity_claim](../../src/trading_kernel/application/build_capacity_claim.py#L52)、[select_capacity_candidate](../../src/trading_kernel/domain/capacity_sizing.py#L172) | CapacityClaim、sizing 与 stress 证据 | [capacity sizing](../../tests/trading_kernel/unit/test_capacity_sizing.py)、[capacity claim integration](../../tests/trading_kernel/integration/test_capacity_claim_to_ticket.py) |
| **原子签发** | [issue_ticket](../../src/trading_kernel/application/issue_ticket.py#L97) | lane、account exposure、预算、域、Ticket、首命令 | [Decision 失败整体回滚](../../tests/trading_kernel/integration/test_signal_to_ticket.py#L1169)、[issue_ticket integration](../../tests/trading_kernel/integration/test_issue_ticket.py) |
| **命令派发** | [dispatch_one_command](../../src/trading_kernel/application/dispatch_exchange_command.py#L171) | VenuePort、ExchangeCommand、独立网络阶段 | [command dispatch](../../tests/trading_kernel/integration/test_command_dispatch.py)、[commands unit](../../tests/trading_kernel/unit/test_commands.py) |
| **派发前重查** | [revalidate_entry_dispatch](../../src/trading_kernel/application/revalidate_entry_dispatch.py#L152) | 冻结 Claim/Ticket 与 fresh facts | [entry preflight](../../tests/trading_kernel/unit/test_entry_dispatch_preflight.py) |
| **未知结果恢复** | [recover_unknown_command](../../src/trading_kernel/application/recover_unknown_command.py#L92) | VenueTruthSnapshot、精确 namespace/client ID | [重启后仍不重发](../../tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py#L190) |
| **持仓与保护确认** | [reconcile_ticket](../../src/trading_kernel/application/reconcile_ticket.py#L132) | PositionSnapshot、EntryFilled、InitialStopConfirmed | [完整保护和终态](../../tests/trading_kernel/full_chain/test_ticket_lifecycle.py#L158) |
| **退出规则** | [maintain_ticket_lifecycle](../../src/trading_kernel/application/maintain_ticket_lifecycle.py#L116) | TicketLifecycleFacts、冻结 ExitProfile、guards、Runner | [exit policy](../../tests/trading_kernel/unit/test_exit_policy.py)、[lifecycle maintenance](../../tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py) |
| **事件与副作用** | [reduce_event](../../src/trading_kernel/domain/reducer.py#L124)、[commit_reduction](../../src/trading_kernel/infrastructure/pg_unit_of_work.py#L193) | TradeAggregate、TradeEvent、KernelEffect | [reducer unit](../../tests/trading_kernel/unit/test_reducer.py)、[UoW integration](../../tests/trading_kernel/integration/test_pg_unit_of_work.py) |
| **结算和复盘** | [settle_ticket](../../src/trading_kernel/application/settle_ticket.py#L64)、[record_trade_review](../../src/trading_kernel/application/settle_ticket.py#L85) | BudgetSettled、ReviewRecorded、Aggregate.review_id | [完整闭合](../../tests/trading_kernel/full_chain/test_ticket_lifecycle.py#L158) |
| **只读研究** | [project_claimed_shadow_outcome](../../src/trading_kernel/application/project_shadow_outcome.py#L257) | Signal-owned Shadow、费用/真实 PnL 边界 | [generic Signal path](../../tests/trading_kernel/unit/test_generic_signal_path.py)、[research failure 不影响真实 Signal](../../tests/trading_kernel/integration/test_observation_to_signal.py#L1654) |

## 专题索引

| 阅读单元 | 代码入口 | 模型与持久化 | 验证入口 |
| --- | --- | --- | --- |
| **Generic 数学与来源** | [generic_selection_core](../../src/trading_kernel/domain/generic_selection_core.py)、[run_instrument_selection_once](../../src/trading_kernel/application/run_instrument_selection.py#L106) | Spec、完整窗口、排名、Snapshot | [generic_selection_core tests](../../tests/trading_kernel/unit/test_generic_selection_core.py)、[source tests](../../tests/trading_kernel/unit/test_generic_selection_source.py) |
| **物化与原子激活** | [coordinate_selection_materialization_once](../../src/trading_kernel/application/coordinate_selection_materialization.py#L495)、[advance_strategy_universe](../../src/trading_kernel/application/advance_strategy_universe.py#L290) | Generation、Vacuum、Universe、Authority | [materialization repository](../../tests/trading_kernel/integration/test_selection_materialization_repository.py) |
| **Normal 与 Recovery** | [prepare_generic_current_close_proof](../../src/trading_kernel/application/coordinate_selection_materialization.py#L1746)、[timing](../../src/trading_kernel/domain/dynamic_selection_timing.py) | close proof、epoch、Comparison / Episode rebase | [normal authority](../../tests/trading_kernel/unit/test_generic_normal_authority_contract.py)、[recovery proof](../../tests/trading_kernel/unit/test_generic_recovery_grant_proof.py) |
| **Vacuum drain** | [plan_vacuum_ticket_drain](../../src/trading_kernel/application/drain_strategy_entry_vacuum.py#L170) | Cancel、absence、partial retained / flatten | [drain unit](../../tests/trading_kernel/unit/test_drain_strategy_entry_vacuum.py)、[drain integration](../../tests/trading_kernel/integration/test_entry_vacuum_drain.py) |
| **SOR-1H session** | [OrbSessionSelectionSpec](../../src/trading_kernel/domain/orb_session_selection.py#L31)、[sor_1h detector](../../src/trading_kernel/domain/detectors/sor_1h.py) | 日 session、双向配对、小时 Gap Audit | [hourly recovery](../../tests/trading_kernel/unit/test_hourly_recovery_clock.py)、[ORB session](../../tests/trading_kernel/unit/test_orb_session_selection.py) |
| **Owner controls** | [set_global_entry_state](../../src/trading_kernel/application/owner_control.py#L244)、[set_strategy_entry_state](../../src/trading_kernel/application/owner_control.py#L150) | Authorization、Policy/Control current 与 events | [owner unit](../../tests/trading_kernel/unit/test_owner_control.py)、[control integration](../../tests/trading_kernel/integration/test_owner_control_plane.py) |
| **受控全平** | [begin_flatten_all](../../src/trading_kernel/application/owner_control.py#L763)、[consume_pending_flatten_once](../../src/trading_kernel/application/owner_control.py#L954) | Operation、目标 Ticket 与控制进度 | [全账户预览测试](../../tests/trading_kernel/unit/test_owner_control.py#L327)、[HTTP tests](../../tests/trading_kernel/interfaces/test_owner_console_http.py) |
| **退出绑定** | [switch_event_exit_profile](../../src/trading_kernel/application/owner_control.py#L539) | immutable binding、当前 pointer、Ticket frozen hash | [exit profile repository](../../tests/trading_kernel/integration/test_exit_profile_authority_repository.py) |
| **认证与读写分离** | [OwnerAuthService](../../src/trading_kernel/interfaces/owner_console_http/auth.py#L156)、[dependencies](../../src/trading_kernel/interfaces/owner_console_http/dependencies.py) | Session、step-up、read/control engine | [auth unit](../../tests/trading_kernel/unit/owner_console/test_auth.py)、[role grants](../../tests/trading_kernel/architecture/test_owner_console_control_grants.py) |
| **Owner 查询** | [owner_read_transaction](../../src/trading_kernel/infrastructure/pg_owner_read_repository.py#L153)、[performance](../../src/trading_kernel/application/owner_console/performance.py) | bounded readonly snapshot 与 fingerprint | [income integration](../../tests/trading_kernel/integration/test_owner_income_statistics.py)、[readonly architecture](../../tests/trading_kernel/architecture/test_owner_console_architecture.py) |
| **命令仓储与租约** | [PostgresExchangeCommandRepository](../../src/trading_kernel/infrastructure/pg_repositories.py#L740) | prepared、claimed、unknown、精确身份 | [command dispatch integration](../../tests/trading_kernel/integration/test_command_dispatch.py) |
| **运行隔离** | [runtime_writer_is_certified](../../src/trading_kernel/application/runtime_fence.py#L15) | certified commit/schema、Incident | [runtime workers](../../tests/trading_kernel/integration/test_global_runtime_workers.py) |
| **Reconciliation 公平性** | [run_reconciliation_worker_once](../../src/trading_kernel/interfaces/reconciliation_worker.py#L235) | unknown / critical / housekeeping、due claims | [reliability integration](../../tests/trading_kernel/integration/test_reconciliation_reliability.py)、[fairness unit](../../tests/trading_kernel/unit/test_reconciliation_worker_fairness.py) |
| **常驻与重启** | [run_worker_process_group](../../src/trading_kernel/interfaces/worker_process.py#L99) | independently hosted loops、stop signal、burst bounds | [selection hosting](../../tests/trading_kernel/unit/test_selection_runtime_hosting.py)、[shutdown](../../tests/trading_kernel/unit/test_worker_process_shutdown.py) |
| **发布分类与恢复** | [classify_changed_paths](../../scripts/classify_release.py#L83)、[deploy_tokyo_release](../../scripts/trading_kernel/deploy_tokyo_release.py#L321) | R0–R4、identity、preservation、阶段化恢复 | [deployment tests](../../tests/trading_kernel/unit/test_deploy_tokyo_release.py)、[release classification](../../tests/trading_kernel/unit/test_release_classification.py) |

## 用五个问题贯通验收

### 1. 有 Signal 为什么没有 Ticket

**结论：先判断是否到最终准入，再区分权限、事实、仲裁和容量阻断。**沿 `ingest_signal → select_entry_candidate → Entry facts → issue_ready_signal → issue_ticket` 追踪。验证包括[容量拒绝不创建权限](../../tests/trading_kernel/integration/test_signal_to_ticket.py#L500)和[Decision 写失败时全部回滚](../../tests/trading_kernel/integration/test_signal_to_ticket.py#L1169)。

### 2. 下单结果未知如何处理

**结论：未知状态持久化，按命令精确身份恢复，不盲目重发。**验证包括[重启后继续等待可见性](../../tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py#L190)、[权威不存在后不创建第二代](../../tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py#L152)。

### 3. 暂停新入场后持仓怎样继续

**结论：Policy 的新 ENTRY 开关与既有 Ticket 安全工作分离。**从 `set_global_entry_state` 到 ENTRY preflight，再从 Lifecycle/Reducer 追踪已暴露 Ticket。验证包括[暂停事务不拥有交易所权限](../../tests/trading_kernel/integration/test_owner_control_plane.py#L82)、[生命周期维护](../../tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py)。

### 4. 选币完成为什么还没激活

**结论：Snapshot、Generation、Vacuum、Warming 和 Authority 有不同完成条件。**按 [动态选币](DYNAMIC_SELECTION.md)查当期身份，验证包括[物化重启与租约](../../tests/trading_kernel/integration/test_selection_materialization_repository.py#L445)、[准入精确读取当前 Authority](../../tests/trading_kernel/integration/test_selection_entry_authority_repository.py#L39)。

### 5. 重启或发布失败怎样恢复

**结论：持久化恢复必须先区分实际 identity/schema 的来源、目标或未知状态。**验证包括[未知 identity 不重启旧写者](../../tests/trading_kernel/unit/test_deploy_tokyo_release.py#L2342)、[已迁移目标走 fix-forward](../../tests/trading_kernel/unit/test_deploy_tokyo_release.py#L565)、[信号安全关闭](../../tests/trading_kernel/unit/test_worker_process_shutdown.py)。

## 证据不能跨越的边界

1. **Unit** 证明纯规则或类型化替身下的编排，不证明 PostgreSQL 锁行为。
2. **Integration** 证明一次性本地数据库中的持久化和事务，不证明生产账户状态。
3. **Full chain** 证明所用入口和受控场景的闭合；从预制 Ticket/Claim 开始的测试不能独自证明真实 detector 到生产成交的全链。
4. **Architecture / 文档检查**保护模块、来源与链接约束，不验证策略盈利性和真实操作完成。
5. **本轮未运行的映射**仍可供代码阅读，但不能标记为本轮 PASS；精确执行清单见[维护与验收](MAINTENANCE.md)。
