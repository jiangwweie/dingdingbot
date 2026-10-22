# 来源、权威与有效性清单

> **定位：解释性知识库** · [知识地图](README.md)。生产实时状态请查 [MAIN_CONTROL_ROADMAP.md](../current/MAIN_CONTROL_ROADMAP.md)。

## 已知规则：一个事实只有一个责任来源

**Owner 当前明确决定 → 当前受版本管理代码与机器配置 → 当前 PostgreSQL 和交易所只读事实 → 现行文档 → 明确要求恢复时的历史资料**，是来源冲突时的取证顺序。（来源：[AGENTS](../../AGENTS.md)、[信息架构](../current/PROJECT_INFORMATION_ARCHITECTURE.md)）

| 来源 | 负责内容 | 有效性如何判断 | 关联实现或核验入口 |
| --- | --- | --- | --- |
| 当前代码 | 实际分支、校验和副作用 | 固定阅读提交，确认函数仍存在 | [Kernel 源码入口](../../src/trading_kernel/__init__.py) |
| Strategy Registry | Group、Version、Event、事实及方向语义 | 精确版本和语义摘要匹配 | [registered_strategy_contracts](../../src/trading_kernel/domain/strategy_registry.py#L258) |
| Owner Policy / Controls | 允许范围、资本边界、暂停与模式意图 | 数据库 current 与版本、授权记录 | [owner_control](../../src/trading_kernel/application/owner_control.py) |
| PostgreSQL current | 当前投影、租约、权限、持仓与进度 | action-time 精确身份读取 | [pg_models](../../src/trading_kernel/infrastructure/pg_models.py) |
| PostgreSQL events / facts | 信号快照、已签发身份、生命周期和授权沿革 | 不可变身份、事件序号、版本链 | [PostgresKernelUnitOfWork](../../src/trading_kernel/infrastructure/pg_unit_of_work.py#L115) |
| 交易所只读事实 | 账户模式、外部订单、成交和持仓 | 实时读取、时效与身份一致 | [venue_adapter](../../src/trading_kernel/infrastructure/venue_adapter.py) |
| `docs/current` | 稳定契约及各自负责的状态记录 | 白名单、责任范围、与代码核对 | [文档权威测试](../../tests/trading_kernel/architecture/test_current_document_authority.py) |
| 历史设计、发布记录 | 解释决策背景与当时证据 | 按日期和被替代关系阅读 | [docs 导航](../README.md) |
| 本知识库与导出材料 | 阅读、导航、解释和诊断展示 | 引用可解析，结论有证据标记 | [维护规则](MAINTENANCE.md) |

## 现行文档盘点

**下表覆盖当前权威白名单**；“现行”表示职责有效，不表示其中每个描述都已与代码逐项一致。（来源：[白名单定义](../../tests/trading_kernel/architecture/test_current_document_authority.py)）

| 文档 | 用途与适用范围 | 关联代码 / 专题 |
| --- | --- | --- |
| [PROJECT_INFORMATION_ARCHITECTURE](../current/PROJECT_INFORMATION_ARCHITECTURE.md) | 来源分类、责任归属、禁止重复事实 | 本清单、数据模型 |
| [OWNER_RUNTIME_OPERATING_MODEL](../current/OWNER_RUNTIME_OPERATING_MODEL.md) | Owner 决策与系统运行职责 | owner_control、Owner 专题 |
| [AI_AGENT_CONSTRAINTS](../current/AI_AGENT_CONSTRAINTS.md) | 工程、验证与安全边界 | 架构测试、验证分层 |
| [P0 设计](../current/P0_TRADING_KERNEL_REBUILD_DESIGN.md) | 领域不变量与单链路架构 | domain、application、主链路 |
| [P0 实施计划](../current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md) | 工程阶段与验收要求 | full_chain、integration |
| [MULTI_ASSET_STRATEGYGROUP_ROADMAP](../current/MULTI_ASSET_STRATEGYGROUP_ROADMAP.md) | 产品扩展阶段和依赖，不代表启用状态 | product、strategy_registry |
| [MAIN_CONTROL_ROADMAP](../current/MAIN_CONTROL_ROADMAP.md) | 唯一生产版本、快照、验收和阻断记录 | 生产直接证据，本轮未刷新 |
| [TOKYO_RUNTIME_DEPLOYMENT_CONTRACT](../current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md) | 发布、迁移、恢复、资源契约 | deploy 脚本与 systemd |
| [RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE](../current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md) | 资本、容量、杠杆、保证金边界 | capacity_sizing、runtime_authority_seed |
| [Registry Contract](../current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md) | 策略 Event 与版本语义 | strategy_registry、detectors |
| [STRATEGY_EXPERIMENT_EVALUATION_CONTRACT](../current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md) | 策略评估与研究证据边界 | review、shadow_outcome |
| [STRATEGY_ENGINEERING_INTAKE_CONTRACT](../current/STRATEGY_ENGINEERING_INTAKE_CONTRACT.md) | 策略接入 Kernel 的接口边界 | detector、produce_strategy_signal |
| [TRADEABILITY_DECISION_CONTRACT](../current/TRADEABILITY_DECISION_CONTRACT.md) | 可交易判断的条件与证据 | ingest_signal、issue_ready_signal |
| [BLOCKER_CLASSIFICATION_CONTRACT](../current/BLOCKER_CLASSIFICATION_CONTRACT.md) | blocker 分类和可读解释 | owner_console/entry_scope、readiness |

## 历史材料如何使用

| 类别与示例 | 正确用途 | 不能由其证明 |
| --- | --- | --- |
| [Generic Selection 详细设计](../superpowers/specs/2026-09-06-generic-multi-strategy-dynamic-selection-v1-design.md) | 参数来源、正常与恢复转移设计背景 | 当前币池与当前 Authority |
| [Owner 控制设计](../superpowers/specs/2026-08-09-owner-control-plane-design.md) | 控制面的决策背景 | 现行全部接口和前端布局 |
| [Reconciliation 修复设计](../superpowers/specs/2026-10-14-reconciliation-reliability-repair-design.md) | 调度、公平性和锁顺序背景 | 当前生产健康程度 |
| [联合发布复盘](../releases/2026-10-15-brc-joint-release-retrospective.md) | writer 盘点与 preflight 经验 | 本次发布已执行或通过 |
| `docs/history-archive-2026-06-15-pre-governance.tar.gz` | 明确要求历史恢复时的材料 | 现行模块、表结构和运行权限 |

本轮未解包历史归档，也未进行历史体系的逐文件重建；历史材料按职责分类并以相关设计作索引。核心行为的最终依据仍是当前实现。

## 已发现的差异及处理

| 编号 | 直接观察 | 解释与处理 | 证据 |
| --- | --- | --- | --- |
| D1 | README / AGENTS 的 Crypto 家族摘要只列 CPM/MPG/MI/BRF2；Registry 另有 SOR-1H | 概览文字不足以覆盖代码能力；独立列出 SOR-1H，旧 SOR-001 仍永久禁入；不推断当前启用 | [README](../../README.md)、[Registry](../../src/trading_kernel/domain/strategy_registry.py#L258)、[策略准入硬边界](../../src/trading_kernel/application/owner_control.py#L1094) |
| D2 | P0 设计正文列出的迁移链到 0011，实施计划部分到 0010；代码身份已到 0012 | 数据模型以迁移源码及 runtime_identity 为准；不将其写成部署版本 | [runtime_identity](../../src/trading_kernel/infrastructure/runtime_identity.py)、[0012](../../migrations/trading_kernel/versions/0012_generic_signal_path_v1.py) |
| D3 | `docs/README` 部分历史栏目仍写“implementation not claimed” | 它只适合作历史导航；实现有无查代码，生产状态查唯一 roadmap | [docs 索引](../README.md)、[Reconciliation Worker](../../src/trading_kernel/interfaces/reconciliation_worker.py#L232) |
| D4 | `observation_process_component_map` 描述三个角色；启动脚本还安装各策略 facts 刷新循环 | 角色映射不是完整 OS 进程内任务清单；部署图按启动脚本标明 | [角色映射](../../src/trading_kernel/application/runtime.py#L126)、[启动装配](../../scripts/trading_kernel/run_observation_worker_once.py#L97) |
| D5 | AGENTS 对部分 ENTRY 成交写的是撤余量并 flatten；Vacuum drain 代码存在 `VacuumPartialRetained` 分支 | 分别描述普通部分成交事故与切换撤单后的受验证余仓；契约是否需要补充这一特例尚待裁定，本轮不改交易行为 | [plan_vacuum_ticket_drain](../../src/trading_kernel/application/drain_strategy_entry_vacuum.py#L170)、[对应测试](../../tests/trading_kernel/unit/test_drain_strategy_entry_vacuum.py#L69) |
| D6 | 架构扫描发现两处既有 test 模块直接导入其他 test 模块 | 已用阅读基准的原始文件重现；本轮不移动无关夹具，不把全部架构检查写成 PASS | [共享测试边界检查](../../tests/trading_kernel/architecture/test_test_support_boundaries.py#L21)、[验收记录](MAINTENANCE.md) |

**分析结论：现行文档的权威职责与其局部文字的新鲜度需要分别判断。**本轮增加可追溯解释与差异记录，不批量重写原有契约，也不把差异直接认定为生产故障。

## 未核实边界

1. **本轮生产状态**：未读取机器、数据库或交易所；不能确认当前运行版本、账户、权限、持仓和币池。
2. **完整长期与经济验收**：测试覆盖和文档记录不等同于长期自然交易或完整成本归因；其状态仍由 roadmap 与直接证据负责。
3. **历史叙述完整性**：不承诺全部历史方案都已重读；本库覆盖当前主链路和五个指定专题。
