# 数据库全表职责与内容目录

> **定位：解释性知识库** · [知识地图](README.md) · [数据库状态模型](DATA_MODEL.md)。本页保存代码结构与逐表解释，当前生产盘点及其核验时间统一见 [MAIN_CONTROL_ROADMAP.md](../current/MAIN_CONTROL_ROADMAP.md)。

## 数量与统计口径

**当前 tracked Kernel schema 定义 85 张业务表、1035 个业务字段。**此外，数据库有 **1 张 Alembic 版本表**；切换日志组件另定义 **2 张运维表**。这三个集合合并是 **88 张非系统持久表**的统计口径，不能把仅 public schema、仅 brc_ 前缀或包含 pg_catalog 的数量混为同一答案。

| 范围 | 数量 | 是否属于 Kernel metadata | 依据 |
| --- | --- | --- | --- |
| `public.brc_*` 业务表 | **85** | 是 | [pg_models](../../src/trading_kernel/infrastructure/pg_models.py) |
| `public.alembic_version` | **1** | 否，由 Alembic 管理 | [迁移环境](../../migrations/trading_kernel/env.py) |
| `brc_cutover_ops` 切换日志表 | **2** | 否，独立运维 journal | [PostgresCutoverJournal](../../scripts/trading_kernel/cutover_tokyo.py) |
| 以上三类合计 | **88** | 不能直接用 len(metadata.tables) 得到总数 | 当前实库一致性证据见 roadmap |

**范围约束**：不统计系统表、视图、索引、sequence、临时表，也不把其他数据库算入 Trading Kernel。代码结构仍为 `0012_generic_signal_path_v1`；实际安装身份以当前生产证据为准。本页不保存逐表实时行数、业务数据样例、账户值或生产 release 身份。

## 怎样读这份目录

1. **职责**说明“一行代表什么”；**主要内容**解释保存的是定义、当前状态、快照、任务还是沿革。
2. **主键与完整字段**从 tracked SQLAlchemy metadata 核对，字段按代码声明顺序列出，不承诺与实库物理列序相同；这些是结构名称，不是业务数据导出。时间字段一般为 epoch 毫秒，financial 类型及事务边界见数据库状态模型。
3. **维护与用途**说明主要读写路径，不声称只存在一个调用者；每组提供对应仓储来源，业务解释还要结合用例和迁移中的约束。
4. **current 不等于可随意覆盖，events 也不等于永不更新任何列**。命令、任务和尝试有状态推进；合同/结果/授权的不可变语义以对应仓储与约束为准。
5. **表存在不等于功能启用**：旧 SOR 参数、休眠币池、安装的 Spec、研究控制和切换日志都不自动授予新 ENTRY 权限。

## 功能分组导航

| 功能组 | 表数 | 阅读内容 |
| --- | --- | --- |
| **[策略与事实语义](#catalog-registry)** | **5** | 定义策略“是什么”，不授予当前下单权限。 |
| **[标的、产品与市场规则](#catalog-product)** | **5** | 描述交易产品、市场状态、精度及最小下单约束。 |
| **[退出方案及版本绑定](#catalog-exit)** | **4** | 不可变方案与可切换绑定分离；Ticket 冻结签发时的方案。 |
| **[Owner 政策、授权与控制](#catalog-owner)** | **7** | 控制允许范围和异步操作，不直接写交易所。 |
| **[运行配置、认证身份与元数据](#catalog-runtime)** | **5** | 区分运行身份、能力开关、scope 和发布兼容证据。 |
| **[交易币池与标的认证](#catalog-universe)** | **6** | 维护版本化币池、当前指针、预热与只读资格认证。 |
| **[比较集合与相对强度投影](#catalog-comparison)** | **4** | MPG/MI 的比较基础独立于允许交易的币池。 |
| **[选币算法、任务与结果](#catalog-selection)** | **11** | 算法安装、Owner 模式意图、计算执行与不可变结果分别保存。 |
| **[物化过程与恢复基础](#catalog-materialization)** | **6** | 把 Snapshot 变成实际 Universe，并保存切换前基础与审计沿革。 |
| **[ENTRY Vacuum、时间权限与缺口审计](#catalog-authority)** | **8** | 阻止切换期间的违规 ENTRY，明确允许消费哪些收盘。 |
| **[观察事实、机会与就绪状态](#catalog-signal)** | **5** | 从收盘观察保存事实、机会去重身份及待准入信号。 |
| **[准入、容量、执行与生命周期](#catalog-trade)** | **11** | 交易主链路的准入结果、资金占用、订单意图和执行事实。 |
| **[只读路径研究与采集配额](#catalog-research)** | **4** | 研究记录与真实成交、资金及净收益分开。 |
| **[事故、Owner 投影与维护记录](#catalog-health)** | **4** | 记录安全阻断、可读状态和显式维护操作。 |
| **[迁移与切换运维](#catalog-operations)** | **3** | Alembic 版本及 cutover run/phase journal；独立于业务 metadata |

<a id="catalog-registry"></a>

## 策略与事实语义

**范围**：定义策略“是什么”，不授予当前下单权限。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/strategy_registry_seed.py)。）

### `brc_strategy_groups`

**职责**：一行一个策略族。

**主要内容**：稳定策略 ID、显示名、当前策略版本指针与状态。

**主键**：`strategy_group_id`

**维护与用途**：Registry seed 安装/核对，Signal 与 Owner 页面读取；active_version_id 不等同于 Owner 已启用。

<details>
<summary>完整字段（5 列）</summary>

**字段清单**：`strategy_group_id`、`display_name`、`active_version_id`、`status`、`updated_at_ms`

</details>

### `brc_strategy_versions`

**职责**：一行一个策略语义版本。

**主要内容**：归属策略族、版本号、semantics JSON、状态与创建时间。

**主键**：`strategy_version_id`

**维护与用途**：Registry seed 写入，准入核对精确版本；同一 Group 的版本号唯一。

<details>
<summary>完整字段（6 列）</summary>

**字段清单**：`strategy_version_id`、`strategy_group_id`、`version`、`semantics`、`status`、`created_at_ms`

</details>

### `brc_event_specs`

**职责**：一行一个方向和周期的策略事件定义。

**主要内容**：策略版本、event_id、方向、时间周期、新鲜度、入场类型、保护事实和执行语义。

**主键**：`event_spec_id`

**维护与用途**：Registry seed 维护，detector/ingestion/ENTRY 校验读取；注册不是资金授权。

<details>
<summary>完整字段（13 列）</summary>

**字段清单**：`event_spec_id`、`strategy_version_id`、`event_id`、`position_side`、`timeframe`、`freshness_window_ms`、`event_time_authority`、`entry_order_type`、`protection_reference_fact_definition_id`、`exit_policy_id`、`execution_semantics`、`status`、`created_at_ms`

</details>

### `brc_fact_definitions`

**职责**：一行一种事实的定义。

**主要内容**：事实名、boolean/decimal 类型、新鲜度窗口与验证契约。

**主键**：`fact_definition_id`

**维护与用途**：Registry seed 维护；为当前 Fact 和 Signal 冻结事实提供同一语义身份。

<details>
<summary>完整字段（5 列）</summary>

**字段清单**：`fact_definition_id`、`fact_name`、`value_type`、`freshness_ms`、`validation`

</details>

### `brc_event_required_facts`

**职责**：一行一个 Event 与 Fact 定义的绑定。

**主要内容**：事实在该 Event 的角色及是否必需。

**主键**：`event_spec_id`、`fact_definition_id`

**维护与用途**：Registry seed 维护，观察和摄取按绑定读取事实，区分条件、保护、身份等用途。

<details>
<summary>完整字段（4 列）</summary>

**字段清单**：`event_spec_id`、`fact_definition_id`、`role`、`required`

</details>

<a id="catalog-product"></a>

## 标的、产品与市场规则

**范围**：描述交易产品、市场状态、精度及最小下单约束。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_signal_repository.py)。）

### `brc_instruments`

**职责**：一行一个交易所标的身份。

**主要内容**：venue、资产类别、交易所 symbol、合约种类和状态。

**主键**：`exchange_instrument_id`

**维护与用途**：Universe 安装/标的目录路径维护，交易和查询按精确 instrument ID 关联。

<details>
<summary>完整字段（6 列）</summary>

**字段清单**：`exchange_instrument_id`、`venue_id`、`asset_class`、`venue_symbol`、`contract_kind`、`status`

</details>

### `brc_event_product_compatibility`

**职责**：一行一个 Event 的产品兼容契约。

**主要内容**：产品族、资产类、合约/底层类型、保证金币种和语义摘要。

**主键**：`event_spec_id`

**维护与用途**：Registry seed 安装；Universe 安装和产品准入读取，防止 Crypto 与 TradFi 互相误用。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`event_spec_id`、`product_family`、`asset_class`、`contract_type`、`underlying_type`、`margin_asset`、`semantic_digest`、`created_at_ms`

</details>

### `brc_instrument_product_profiles`

**职责**：一行一个标的的产品 Profile。

**主要内容**：产品语义、ENTRY session 策略、价差与 mark/index 偏离上限、语义摘要。

**主键**：`exchange_instrument_id`

**维护与用途**：[pg_product_current](../../src/trading_kernel/infrastructure/pg_product_current.py) 和正式产品/Universe 路径维护；不保存账户资金权限。

<details>
<summary>完整字段（12 列）</summary>

**字段清单**：`exchange_instrument_id`、`product_family`、`asset_class`、`contract_type`、`underlying_type`、`margin_asset`、`entry_session_policy`、`status`、`max_entry_spread_bps`、`max_mark_index_deviation_bps`、`semantic_digest`、`updated_at_ms`

</details>

### `brc_instrument_product_current`

**职责**：一行一个标的的当前产品/市场快照。

**主要内容**：交易与 session 状态、开闭市时间、mark/index、funding、盘口、corporate event、来源与有效期。

**主键**：`exchange_instrument_id`

**维护与用途**：当前产品事实刷新写入，特别用于 TradFi 行动时 gate；时效不合格不能当作可交易。

<details>
<summary>完整字段（17 列）</summary>

**字段清单**：`exchange_instrument_id`、`product_status`、`session_state`、`regular_session_open_ms`、`regular_session_close_ms`、`mark_price`、`index_price`、`funding_rate`、`best_bid`、`best_ask`、`best_bid_quantity`、`best_ask_quantity`、`corporate_event_status`、`observed_at_ms`、`valid_until_ms`、`source_ref`、`projection_version`

</details>

### `brc_instrument_rules_current`

**职责**：一行一个 venue + instrument 的当前交易规则。

**主要内容**：数量步长、价格 tick、最小量/名义、杠杆上限、维持保证金阶梯及有效期。

**主键**：`venue_id`、`exchange_instrument_id`

**维护与用途**：pg_signal_repository 更新；定量、退出双腿可执行性及压力校验读取。

<details>
<summary>完整字段（15 列）</summary>

**字段清单**：`venue_id`、`exchange_instrument_id`、`quantity_step`、`price_tick`、`min_quantity`、`min_notional`、`exchange_max_leverage`、`maintenance_margin_brackets`、`maintenance_margin_brackets_digest`、`notional_coefficient`、`notional_coefficient_certified`、`session_and_settlement`、`observed_at_ms`、`valid_until_ms`、`projection_version`

</details>

<a id="catalog-exit"></a>

## 退出方案及版本绑定

**范围**：不可变方案与可切换绑定分离；Ticket 冻结签发时的方案。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_exit_profile_repository.py)。）

### `brc_exit_policies`

**职责**：一行一个已注册退出策略/Profile。

**主要内容**：退出规则 JSON、方向、语义 hash、状态；profile_schema_version 区分 typed Profile 形状。

**主键**：`exit_policy_id`

**维护与用途**：Registry seed 与 ExitProfile repository 维护；保留旧行形状不代表 runtime fallback。

<details>
<summary>完整字段（9 列）</summary>

**字段清单**：`exit_policy_id`、`exit_policy_version`、`event_spec_id`、`profile_schema_version`、`position_side`、`policy`、`semantic_hash`、`status`、`created_at_ms`

</details>

### `brc_event_exit_profile_bindings`

**职责**：一行一个 Event 的不可变退出绑定版本。

**主要内容**：Event、Profile ID/hash、binding_version/hash、激活原因和创建时间。

**主键**：`exit_binding_id`

**维护与用途**：正式绑定变更追加；Claim/Ticket 冻结该身份，已有 Ticket 不跟随新绑定重写。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`exit_binding_id`、`binding_version`、`event_spec_id`、`exit_profile_id`、`exit_profile_semantic_hash`、`binding_semantic_hash`、`activation_reason`、`created_at_ms`

</details>

### `brc_event_exit_profile_binding_current`

**职责**：一行一个 Event 的当前退出绑定指针。

**主要内容**：当前 binding ID/hash、投影版本和激活时间。

**主键**：`event_spec_id`

**维护与用途**：ExitProfile repository 在 authority lock/CAS 下推进；新 Claim 读取并重查。

<details>
<summary>完整字段（5 列）</summary>

**字段清单**：`event_spec_id`、`exit_binding_id`、`binding_semantic_hash`、`projection_version`、`activated_at_ms`

</details>

### `brc_event_exit_profile_binding_events`

**职责**：一行一个退出绑定操作事件。

**主要内容**：绑定版本、operation、授权来源、可空 Owner authorization、原因和时间。

**主键**：`binding_event_id`

**维护与用途**：seed 或正式控制事务追加，解释一次绑定切换由谁、为何发生。

<details>
<summary>完整字段（9 列）</summary>

**字段清单**：`binding_event_id`、`event_spec_id`、`exit_binding_id`、`binding_version`、`operation`、`authorization_source`、`owner_authorization_id`、`reason`、`created_at_ms`

</details>

<a id="catalog-owner"></a>

## Owner 政策、授权与控制

**范围**：控制允许范围和异步操作，不直接写交易所。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_repositories.py)。）

### `brc_owner_policy_current`

**职责**：一行一套 Owner 当前资金政策。

**主要内容**：允许范围、全局新 ENTRY、Ticket/Family/策略侧容量、风险及保证金比例、杠杆与 margin mode。

**主键**：`owner_policy_id`

**维护与用途**：runtime seed、正式 Owner 控制按版本推进；Entry/Claim/签发读取当前值。

<details>
<summary>完整字段（21 列）</summary>

**字段清单**：`owner_policy_id`、`policy_version`、`enabled`、`new_entry_submit_enabled`、`priority_rank`、`max_concurrent_tickets`、`max_strategy_group_concurrent_tickets`、`family_ticket_limits`、`max_same_strategy_side`、`max_ticket_stop_risk_fraction`、`max_gross_stop_risk_fraction`、`max_ticket_initial_margin_fraction`、`max_gross_initial_margin_utilization`、`directional_stop_risk_limit_fraction`、`min_materialization_ratio`、`max_leverage`、`supported_margin_mode`、`post_stop_stress_multiple`、`max_post_fill_stop_risk_overrun_fraction`、`scope`、`updated_at_ms`

</details>

### `brc_owner_policy_events`

**职责**：一行一个 Policy 版本的变更事实。

**主要内容**：Policy ID/版本、operation、payload 与时间。

**主键**：`owner_policy_event_id`

**维护与用途**：政策事务追加，用于追溯当时授权边界；不能用旧事件代替当前 Policy。

<details>
<summary>完整字段（6 列）</summary>

**字段清单**：`owner_policy_event_id`、`owner_policy_id`、`policy_version`、`operation`、`payload`、`created_at_ms`

</details>

### `brc_strategy_entry_controls_current`

**职责**：一行一个策略族的当前 ENTRY 控制。

**主要内容**：enabled/paused、control_version、最后事件 ID、原因与时间。

**主键**：`strategy_group_id`

**维护与用途**：正式 Owner 控制维护；准入 fail-closed，旧 SOR-001 不会因存有行而恢复权限。

<details>
<summary>完整字段（6 列）</summary>

**字段清单**：`strategy_group_id`、`entry_state`、`control_version`、`last_event_id`、`reason`、`updated_at_ms`

</details>

### `brc_strategy_entry_control_events`

**职责**：一行一个策略控制版本事件。

**主要内容**：操作、目标状态、授权 ID、原因、payload 与时间。

**主键**：`strategy_entry_control_event_id`

**维护与用途**：控制事务追加；与 current 的最后事件关联解释暂停/恢复沿革。

<details>
<summary>完整字段（9 列）</summary>

**字段清单**：`strategy_entry_control_event_id`、`strategy_group_id`、`control_version`、`operation`、`target_state`、`authorization_id`、`reason`、`payload`、`created_at_ms`

</details>

### `brc_owner_authorizations`

**职责**：一行一个已验证的 Owner 授权事实。

**主要内容**：purpose、Owner identity、认证强度、请求摘要、目标范围、幂等键与时间。

**主键**：`authorization_id`

**维护与用途**：正式控制用例写入；不保存密码、TOTP 原码，也不是交易所凭据库。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`authorization_id`、`purpose`、`owner_identity`、`authentication_strength`、`request_digest`、`target_scope`、`idempotency_key`、`authorized_at_ms`

</details>

### `brc_owner_control_operations_current`

**职责**：一行一个异步 flatten-all Operation 的当前进度。

**主要内容**：授权身份、账户范围、目标 Ticket 集、snapshot_digest、状态/版本、租约及 blocker。

**主键**：`authorization_id`

**维护与用途**：Owner 提交后由 Lifecycle 消费、Reconciliation 推进；HTTP 成功不是 Operation 完成。

<details>
<summary>完整字段（14 列）</summary>

**字段清单**：`authorization_id`、`operation_kind`、`state`、`version`、`runtime_profile_id`、`venue_id`、`account_id`、`target_ticket_ids`、`snapshot_digest`、`first_blocker`、`claimed_by`、`lease_until_ms`、`created_at_ms`、`updated_at_ms`

</details>

### `brc_owner_control_operation_events`

**职责**：一行一个 Operation 版本的进度事件。

**主要内容**：authorization_id、operation_version、状态、blocker、payload 与时间。

**主键**：`control_operation_event_id`

**维护与用途**：正式操作进度事务追加，用于追溯卡在哪一阶段。

<details>
<summary>完整字段（7 列）</summary>

**字段清单**：`control_operation_event_id`、`authorization_id`、`operation_version`、`state`、`first_blocker`、`payload`、`created_at_ms`

</details>

<a id="catalog-runtime"></a>

## 运行配置、认证身份与元数据

**范围**：区分运行身份、能力开关、scope 和发布兼容证据。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/runtime_authority_seed.py)。）

### `brc_runtime_profiles`

**职责**：一行一套运行账户/环境 Profile。

**主要内容**：venue、account、environment、position_mode 和状态。

**主键**：`runtime_profile_id`

**维护与用途**：runtime seed 与正式配置维护；Scope 引用它，而非从 Markdown 读取账户。

<details>
<summary>完整字段（7 列）</summary>

**字段清单**：`runtime_profile_id`、`venue_id`、`account_id`、`environment`、`position_mode`、`status`、`updated_at_ms`

</details>

### `brc_runtime_scopes_current`

**职责**：一行一个具体 Event/标的/方向/Universe 的运行范围。

**主要内容**：Policy/Profile 绑定、观察与入场开关、版本、预热水位/有效期、due、租约和 observation_generation。

**主键**：`runtime_scope_id`

**维护与用途**：Universe repository 安装/切换，Observation 领取和更新；主链路精确定位入口。

<details>
<summary>完整字段（23 列）</summary>

**字段清单**：`runtime_scope_id`、`strategy_group_id`、`strategy_version_id`、`event_spec_id`、`runtime_profile_id`、`owner_policy_id`、`exchange_instrument_id`、`position_side`、`universe_version_id`、`universe_semantic_digest`、`lifecycle_state`、`observation_enabled`、`entry_enabled`、`scope_version`、`warm_closed_bar_time_ms`、`warm_completed_at_ms`、`warm_readiness_digest`、`warm_valid_until_ms`、`next_observation_due_at_ms`、`lease_expires_at_ms`、`lease_owner`、`observation_generation`、`updated_at_ms`

</details>

### `brc_runtime_capabilities_current`

**职责**：一行一个受认证的运行能力。

**主要内容**：capability_key、enabled、certified_commit、schema_revision、certification 与时间。

**主键**：`capability_key`

**维护与用途**：正式运行身份/认证路径维护；Runtime Fence 检查写者与其是否一致。

<details>
<summary>完整字段（6 列）</summary>

**字段清单**：`capability_key`、`enabled`、`certified_commit`、`schema_revision`、`certification`、`updated_at_ms`

</details>

### `brc_schema_metadata`

**职责**：一行一个 schema/runtime/seed 元数据键。

**主要内容**：metadata_key/value 和更新时间；值域由部署及 seed 代码解释。

**主键**：`metadata_key`

**维护与用途**：bootstrap/runtime_authority_seed 维护，发布与验证读取；不是任意参数仓库。

<details>
<summary>完整字段（3 列）</summary>

**字段清单**：`metadata_key`、`metadata_value`、`updated_at_ms`

</details>

### `brc_runtime_release_compatibility_facts`

**职责**：一行一次精确来源到目标的发布兼容事实。

**主要内容**：来源/目标 commit 与 schema、分类、理由、兼容依据及认证 manifest 摘要。

**主键**：`release_compatibility_id`

**维护与用途**：正式发布经 [Selection repository](../../src/trading_kernel/infrastructure/pg_instrument_selection_repository.py)持久化；恢复区分 compatible restart 与需要 rematerialization 的升级。

<details>
<summary>完整字段（10 列）</summary>

**字段清单**：`release_compatibility_id`、`from_commit`、`to_commit`、`from_schema_revision`、`to_schema_revision`、`classification`、`compatibility_basis_digest`、`reason_codes`、`certification_manifest_digest`、`created_at_ms`

</details>

<a id="catalog-universe"></a>

## 交易币池与标的认证

**范围**：维护版本化币池、当前指针、预热与只读资格认证。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_universe_repository.py)。）

### `brc_strategy_universe_versions`

**职责**：一行一个 Event 的币池版本。

**主要内容**：成员语义摘要、warming/staged/active 等生命周期、来源 generation 与安装/激活/退役时间。

**主键**：`universe_version_id`

**维护与用途**：Universe repository 与物化协调器维护；有版本记录不代表当前生效。

<details>
<summary>完整字段（13 列）</summary>

**字段清单**：`universe_version_id`、`strategy_group_id`、`event_spec_id`、`universe_version`、`semantic_digest`、`lifecycle_state`、`source_kind`、`materialization_generation_id`、`installed_at_ms`、`activated_at_ms`、`retired_at_ms`、`abandoned_at_ms`、`abandon_reason_code`

</details>

### `brc_strategy_universe_members`

**职责**：一行一个币池版本与标的的成员关系。

**主要内容**：universe_version_id 和 exchange_instrument_id。

**主键**：`universe_version_id`、`exchange_instrument_id`

**维护与用途**：正式安装路径写入；成员是集合，不在本表表达排名、权重或资金份额。

<details>
<summary>完整字段（2 列）</summary>

**字段清单**：`universe_version_id`、`exchange_instrument_id`

</details>

### `brc_strategy_universe_current`

**职责**：一行一个 Event 的当前币池指针。

**主要内容**：Universe ID/digest、生命周期、activation_generation 和激活时间。

**主键**：`event_spec_id`

**维护与用途**：原子激活事务切换；Observation/新 ENTRY 查当前成员，已有 Ticket 保留冻结版本。

<details>
<summary>完整字段（6 列）</summary>

**字段清单**：`event_spec_id`、`universe_version_id`、`semantic_digest`、`lifecycle_state`、`activation_generation`、`activated_at_ms`

</details>

### `brc_instrument_certification_current`

**职责**：一行一个 Profile + 标的的当前只读认证。

**主要内容**：eligible/暂不可用/Owner action、blocker、账户模式/杠杆事实摘要、有效期、调度与租约。

**主键**：`runtime_profile_id`、`exchange_instrument_id`

**维护与用途**：Reconciliation 认证循环更新；认证没有交易所写权限。

<details>
<summary>完整字段（16 列）</summary>

**字段清单**：`runtime_profile_id`、`exchange_instrument_id`、`status`、`blocker_code`、`facts_digest`、`product_rules_digest`、`configured_leverage`、`margin_mode`、`position_mode`、`observed_at_ms`、`valid_until_ms`、`next_check_at_ms`、`lease_owner`、`lease_expires_at_ms`、`lease_universe_version_id`、`projection_version`

</details>

### `brc_instrument_certification_batches`

**职责**：一行一批绑定精确目标身份的认证任务。

**主要内容**：commit/schema/seed、Policy 版本、manifest digest、批次状态和最短有效期。

**主键**：`certification_batch_id`

**维护与用途**：certification_batch 与 Universe repository 维护；用于发布与 ENTRY 恢复 gate。

<details>
<summary>完整字段（14 列）</summary>

**字段清单**：`certification_batch_id`、`runtime_profile_id`、`target_commit`、`target_schema_revision`、`target_seed_identity`、`owner_policy_id`、`owner_policy_version`、`manifest_digest`、`status`、`started_at_ms`、`minimum_valid_until_ms`、`completed_at_ms`、`valid_until_ms`、`blocker_code`

</details>

### `brc_instrument_certification_batch_members`

**职责**：一行一批认证中的一个标的结果。

**主要内容**：资格状态、blocker、facts/rules digest、观察时间和有效期。

**主键**：`certification_batch_id`、`exchange_instrument_id`

**维护与用途**：认证批次推进写入，与批次身份一起构成完整覆盖证明。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`certification_batch_id`、`exchange_instrument_id`、`status`、`blocker_code`、`facts_digest`、`product_rules_digest`、`observed_at_ms`、`valid_until_ms`

</details>

<a id="catalog-comparison"></a>

## 比较集合与相对强度投影

**范围**：MPG/MI 的比较基础独立于允许交易的币池。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_instrument_selection_repository.py)。）

### `brc_comparison_universe_definitions`

**职责**：一行一个不可变比较集合定义。

**主要内容**：comparison_universe_id、member_set_digest、member_count。

**主键**：`comparison_universe_id`

**维护与用途**：Selection repository 维护；用于 MPG/MI 相对强弱，不是允许交易列表。

<details>
<summary>完整字段（3 列）</summary>

**字段清单**：`comparison_universe_id`、`member_set_digest`、`member_count`

</details>

### `brc_comparison_universe_members`

**职责**：一行一个比较集合的标的成员。

**主要内容**：比较集合 ID 与标的 ID。

**主键**：`comparison_universe_id`、`exchange_instrument_id`

**维护与用途**：比较基础安装写入；参与相对强弱的市场来源读取。

<details>
<summary>完整字段（2 列）</summary>

**字段清单**：`comparison_universe_id`、`exchange_instrument_id`

</details>

### `brc_comparison_binding_current`

**职责**：一行一个 Event 当前比较集合绑定。

**主要内容**：comparison ID、transition revision、来源 Static Universe。

**主键**：`event_spec_id`

**维护与用途**：正式比较切换更新；revision 变化需要相应 Episode/检测 rebase，不能复用旧 arming。

<details>
<summary>完整字段（4 列）</summary>

**字段清单**：`event_spec_id`、`comparison_universe_id`、`comparison_transition_revision`、`source_static_universe_version_id`

</details>

### `brc_comparative_projection_current`

**职责**：一行一个 Event + Universe 的当前相对强度投影。

**主要内容**：收盘水位、成员摘要、成功/失败原因、强度 projection、有效期及比较 revision。

**主键**：`event_spec_id`、`universe_version_id`

**维护与用途**：comparative projection 用例经 Universe repository 写入；MPG/MI detector 读取同一期证据。

<details>
<summary>完整字段（11 列）</summary>

**字段清单**：`event_spec_id`、`universe_version_id`、`closed_bar_time_ms`、`member_set_digest`、`projection_status`、`failure_reason`、`projection`、`observed_at_ms`、`valid_until_ms`、`projection_version`、`comparison_transition_revision`

</details>

<a id="catalog-selection"></a>

## 选币算法、任务与结果

**范围**：算法安装、Owner 模式意图、计算执行与不可变结果分别保存。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_instrument_selection_repository.py)。）

### `brc_instrument_selection_specs`

**职责**：一行一个选币算法的安装主记录。

**主要内容**：策略族/版本、selection_kind、算法摘要、状态与安装时间。

**主键**：`selection_spec_id`

**维护与用途**：Selection repository 安装并校验；参数在各族扩展表，安装不等于 Owner 启用。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`selection_spec_id`、`strategy_group_id`、`strategy_version_id`、`selection_version`、`selection_kind`、`algorithm_semantic_digest`、`status`、`installed_at_ms`

</details>

### `brc_generic_dynamic_selection_specs_v1`

**职责**：一行一个 Generic Spec 的冻结参数扩展。

**主要内容**：周期、entry/retain rank、窗口长度、延迟、Decimal 精度、miss 和物化时限。

**主键**：`selection_spec_id`

**维护与用途**：Generic Spec 安装写入，runner 校验与纯计算读取；参数受冻结契约约束。

<details>
<summary>完整字段（10 列）</summary>

**字段清单**：`selection_spec_id`、`cadence_hours`、`entry_rank`、`retain_rank`、`window_bars`、`delay_ms`、`decimal_precision`、`decimal_rounding`、`max_consecutive_selection_miss`、`materialization_timeout_ms`

</details>

### `brc_orb_session_selection_specs_v1`

**职责**：一行一个 SOR-1H session Spec 的 typed payload。

**主要内容**：selection_spec_id 与 payload JSON；其内部形状由 OrbSessionSelectionSpec 定义。

**主键**：`selection_spec_id`

**维护与用途**：ORB 安装路径维护；独立于旧 SOR-001 的日内算法身份。

<details>
<summary>完整字段（2 列）</summary>

**字段清单**：`selection_spec_id`、`payload`

</details>

### `brc_sor_dynamic_selection_specs_v0`

**职责**：一行一个旧 SOR 日内选币参数扩展。

**主要内容**：日内决策/cutoff/资格偏移、候选/选中数量、activity floor 和物化时限。

**主键**：`selection_spec_id`

**维护与用途**：保留旧选择语义与历史验证用途；表存在不能恢复旧 SOR-001 ENTRY。

<details>
<summary>完整字段（10 列）</summary>

**字段清单**：`selection_spec_id`、`decision_offset_utc_seconds`、`feature_cutoff_offset_utc_seconds`、`eligibility_not_before_offset_utc_seconds`、`valid_until_next_decision_offset_seconds`、`candidate_count`、`selected_count_max`、`near_count_max`、`activity_floor_quote_usdt`、`materialization_timeout_seconds`

</details>

### `brc_instrument_selection_spec_events`

**职责**：一行一个 Spec 与 Event/方向绑定。

**主要内容**：selection_spec_id、event_spec_id、position_side。

**主键**：`selection_spec_id`、`event_spec_id`

**维护与用途**：Selection Spec 安装写入；配对或单 Event 物化据此解析精确目标。

<details>
<summary>完整字段（3 列）</summary>

**字段清单**：`selection_spec_id`、`event_spec_id`、`position_side`

</details>

### `brc_instrument_selection_spec_members`

**职责**：一行一个 Spec 的候选标的。

**主要内容**：Spec ID 与标的 ID。

**主键**：`selection_spec_id`、`exchange_instrument_id`

**维护与用途**：Spec 安装维护固定候选集合；候选不是本期选中，也不是当前 tradable 成员。

<details>
<summary>完整字段（2 列）</summary>

**字段清单**：`selection_spec_id`、`exchange_instrument_id`

</details>

### `brc_strategy_selection_control_current`

**职责**：一行一个策略族的当前选币模式与 Owner 意图。

**主要内容**：static/dynamic/disabled、pending 模式与生效期、授权、epoch、版本、rollback baseline。

**主键**：`strategy_group_id`

**维护与用途**：Owner 控制写入，物化原子消费 pending；失败 Job 不应无故撤销原 intent。

<details>
<summary>完整字段（10 列）</summary>

**字段清单**：`strategy_group_id`、`selection_spec_id`、`selection_epoch_id`、`selection_mode`、`pending_selection_mode`、`pending_effective_period_anchor_ms`、`pending_authorization_id`、`control_version`、`rollback_baseline_id`、`updated_at_ms`

</details>

### `brc_instrument_selection_jobs_current`

**职责**：一行一个 Spec/epoch/period 的计算任务。

**主要内容**：调度与 cutoff、前序结果摘要、当前 state/blocker、attempt_count、retry、租约。

**主键**：`selection_job_id`

**维护与用途**：Selection runner 领取并推进；只管理计算，不直接变更 Universe。

<details>
<summary>完整字段（18 列）</summary>

**字段清单**：`selection_job_id`、`selection_spec_id`、`selection_epoch_id`、`selection_control_version`、`predecessor_snapshot_id`、`predecessor_member_digest`、`period_anchor_ms`、`scheduled_at_ms`、`feature_cutoff_at_ms`、`state`、`selection_snapshot_id`、`first_blocker`、`attempt_count`、`next_retry_at_ms`、`lease_owner`、`lease_expires_at_ms`、`projection_version`、`updated_at_ms`

</details>

### `brc_instrument_selection_attempts`

**职责**：一行一次选币计算尝试。

**主要内容**：Job/epoch/period、worker、attempt_number、开始/结束、结果/原因与来源摘要。

**主键**：`selection_attempt_id`

**维护与用途**：runner 记录尝试及完成结果；失败尝试保留，不能被新重试抹掉。

<details>
<summary>完整字段（16 列）</summary>

**字段清单**：`selection_attempt_id`、`selection_job_id`、`selection_spec_id`、`selection_epoch_id`、`selection_control_version`、`predecessor_snapshot_id`、`predecessor_member_digest`、`period_anchor_ms`、`worker_id`、`attempt_number`、`started_at_ms`、`completed_at_ms`、`outcome`、`reason_code`、`source_member_count`、`source_digest`

</details>

### `brc_instrument_selection_snapshots`

**职责**：一行一期成功的不可变选币结果。

**主要内容**：Spec/epoch、cutoff/资格/失效时间、候选/合格/选中数、来源及结果摘要、前序 Snapshot。

**主键**：`selection_snapshot_id`

**维护与用途**：计算成功提交；物化读取，Snapshot 自身不是交易 Authority。

<details>
<summary>完整字段（20 列）</summary>

**字段清单**：`selection_snapshot_id`、`selection_spec_id`、`strategy_group_id`、`strategy_version_id`、`period_anchor_ms`、`decision_at_ms`、`feature_cutoff_at_ms`、`eligibility_not_before_ms`、`expires_at_ms`、`candidate_count`、`ready_count`、`selected_count`、`source_observed_at_ms`、`source_semantic_digest`、`selection_semantic_digest`、`created_at_ms`、`selection_epoch_id`、`selection_family`、`predecessor_snapshot_id`、`predecessor_member_digest`

</details>

### `brc_instrument_selection_member_decisions`

**职责**：一行一个 Snapshot 中一个候选的完整决策。

**主要内容**：输入窗口与摘要、资格证据、特征、排名、retained/selected、拒绝理由及 OR/ATR 字段。

**主键**：`selection_snapshot_id`、`exchange_instrument_id`

**维护与用途**：Selection 提交结果时写入；多算法共享表，字段应按 selection_family 解释，不能假定全部非空。

<details>
<summary>完整字段（31 列）</summary>

**字段清单**：`selection_snapshot_id`、`member_decision_id`、`selection_spec_id`、`period_anchor_ms`、`feature_cutoff_at_ms`、`input_window_start_ms`、`input_window_end_ms`、`exchange_instrument_id`、`input_window_digest`、`source_status`、`selection_family`、`feature_value`、`retained`、`qualification_fact`、`qualification_semantic_digest`、`or_high`、`or_low`、`or_width`、`pre_or_atr14`、`pre_or_width_atr14`、`trailing_24h_quote_volume`、`or_geometry_valid`、`atr_valid`、`activity_valid`、`selection_ready`、`primary_reason`、`secondary_reasons`、`stable_rank`、`member_state`、`selected`、`member_semantic_digest`

</details>

<a id="catalog-materialization"></a>

## 物化过程与恢复基础

**范围**：把 Snapshot 变成实际 Universe，并保存切换前基础与审计沿革。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_instrument_selection_repository.py)。）

### `brc_strategy_selection_rollback_baselines`

**职责**：一行一个 Owner Static 回切的冻结基础。

**主要内容**：策略族/版本、语义摘要与捕获时间。

**主键**：`rollback_baseline_id`

**维护与用途**：Selection 控制/安装路径保存；其 Event/Universe 内容在 rollback_baseline_events。

<details>
<summary>完整字段（5 列）</summary>

**字段清单**：`rollback_baseline_id`、`strategy_group_id`、`strategy_version_id`、`semantic_digest`、`captured_at_ms`

</details>

### `brc_selection_rollback_baseline_events`

**职责**：一行一个 rollback baseline 对应的 Event 基础。

**主要内容**：方向、冻结 Universe 与 ComparisonUniverse ID。

**主键**：`rollback_baseline_id`、`event_spec_id`

**维护与用途**：正式 Static rollback 构建新目标时读取；不是恢复旧 schema 或旧程序。

<details>
<summary>完整字段（5 列）</summary>

**字段清单**：`rollback_baseline_id`、`event_spec_id`、`position_side`、`universe_version_id`、`comparison_universe_id`

</details>

### `brc_strategy_universe_materialization_generations`

**职责**：一行一个将结果变成运行币池的物化代次。

**主要内容**：Snapshot/epoch/control、目标成员数、生命周期、fallback、fence、租约 owner/epoch、各阶段时间。

**主键**：`materialization_generation_id`

**维护与用途**：物化协调器推进；独立于 Selection Job，超时不能靠重试无限延长。

<details>
<summary>完整字段（24 列）</summary>

**字段清单**：`materialization_generation_id`、`selection_spec_id`、`selection_epoch_id`、`selection_control_version`、`lease_epoch`、`strategy_group_id`、`strategy_version_id`、`selection_mode`、`selection_snapshot_id`、`rollback_baseline_id`、`period_anchor_ms`、`desired_member_count`、`semantic_digest`、`lifecycle_state`、`fallback_reason_code`、`lease_owner`、`lease_expires_at_ms`、`projection_version`、`created_at_ms`、`desired_at_ms`、`fenced_at_ms`、`activated_at_ms`、`fallback_at_ms`、`terminal_at_ms`

</details>

### `brc_materialization_generation_event_baselines`

**职责**：一行一个 generation 切换前 Event 的冻结交易基础。

**主要内容**：grant_state、Universe/成员摘要、Comparison 与 revision。

**主键**：`materialization_generation_id`、`event_spec_id`

**维护与用途**：物化准备时保存；恢复按真实先前授权基础判断，休眠物理行不自动成为 fallback。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`materialization_generation_id`、`event_spec_id`、`position_side`、`grant_state`、`universe_version_id`、`member_set_digest`、`comparison_universe_id`、`comparison_transition_revision`

</details>

### `brc_strategy_universe_materialization_targets`

**职责**：一行一个 generation 需要安装的目标 Event。

**主要内容**：方向、期望成员摘要、物化顺序。

**主键**：`materialization_generation_id`、`event_spec_id`

**维护与用途**：协调器安装/校验，支持有序配对物化；actual Universe 行另存。

<details>
<summary>完整字段（5 列）</summary>

**字段清单**：`materialization_generation_id`、`event_spec_id`、`position_side`、`expected_member_set_digest`、`materialization_order`

</details>

### `brc_strategy_universe_materialization_events`

**职责**：一行一次物化进度事件。

**主要内容**：generation、event_sequence、event_type、payload 与时间。

**主键**：`materialization_event_id`

**维护与用途**：协调器/Universe 原子转移追加，解释 desired→drain→warming→activation 的沿革。

<details>
<summary>完整字段（6 列）</summary>

**字段清单**：`materialization_event_id`、`materialization_generation_id`、`event_sequence`、`event_type`、`payload`、`occurred_at_ms`

</details>

<a id="catalog-authority"></a>

## ENTRY Vacuum、时间权限与缺口审计

**范围**：阻止切换期间的违规 ENTRY，明确允许消费哪些收盘。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_instrument_selection_repository.py)。）

### `brc_strategy_entry_vacuums_current`

**职责**：一行一次策略 ENTRY 切换栅栏的当前状态。

**主要内容**：Spec/period、来源 generation、open/draining/reconfiguring/终态、fence/drain 时间与 blocker。

**主键**：`entry_vacuum_id`

**维护与用途**：物化和 drain 用例推进；阻止新 ENTRY，不关闭已有 Ticket 保护/退出。

<details>
<summary>完整字段（11 列）</summary>

**字段清单**：`entry_vacuum_id`、`strategy_group_id`、`selection_spec_id`、`period_anchor_ms`、`source_generation_id`、`state`、`fenced_at_ms`、`drained_at_ms`、`resolved_at_ms`、`first_blocker`、`projection_version`

</details>

### `brc_strategy_entry_vacuum_events`

**职责**：一行一次 Vacuum 状态事件。

**主要内容**：vacuum ID、序号、类型、payload 与时间。

**主键**：`entry_vacuum_event_id`

**维护与用途**：正式 drain/切换事务追加，保留排空与解决过程。

<details>
<summary>完整字段（6 列）</summary>

**字段清单**：`entry_vacuum_event_id`、`entry_vacuum_id`、`event_sequence`、`event_type`、`payload`、`occurred_at_ms`

</details>

### `brc_selection_authority_gap_audits_current`

**职责**：一行一次授权缺口审计的当前进度。

**主要内容**：缺口类型/来源、无授权区间、审计到的收盘、首个合格收盘、范围/结果摘要与状态。

**主键**：`authority_gap_audit_id`

**维护与用途**：Gap Audit 用例写入；恢复前证明不能补吃缺口中的自然触发。

<details>
<summary>完整字段（16 列）</summary>

**字段清单**：`authority_gap_audit_id`、`selection_spec_id`、`period_anchor_ms`、`gap_kind`、`source_entry_vacuum_id`、`source_generation_id`、`proposed_authority_outcome`、`unauthorized_from_close_time_ms`、`audited_through_close_time_ms`、`first_eligible_close_time_ms`、`audit_scope_digest`、`audit_result_digest`、`detector_semantic_digest`、`state`、`first_blocker`、`projection_version`

</details>

### `brc_selection_authority_gap_audit_events`

**职责**：一行一次 Gap Audit 进度事件。

**主要内容**：audit ID、序号、事件类型、payload 与时间。

**主键**：`authority_gap_audit_event_id`

**维护与用途**：审计路径追加；current 可推进，事件保留过程。

<details>
<summary>完整字段（6 列）</summary>

**字段清单**：`authority_gap_audit_event_id`、`authority_gap_audit_id`、`event_sequence`、`event_type`、`payload`、`occurred_at_ms`

</details>

### `brc_selection_session_authorities`

**职责**：一行一次不可变的时间受限选择授权。

**主要内容**：epoch/control、Snapshot/Job/Attempt、grant proof、continuity/recovery、成员新鲜度、有效收盘/到期及语义摘要。

**主键**：`selection_authority_id`

**维护与用途**：正式物化/连续/恢复提交写入；Generic 与 ORB 分支的 proof 形状不同，不能只看行存在。

<details>
<summary>完整字段（31 列）</summary>

**字段清单**：`selection_authority_id`、`selection_spec_id`、`selection_epoch_id`、`selection_control_version`、`activation_authorization_id`、`current_close_proof`、`recovery_grant_proof`、`membership_freshness`、`comparison_universe_id`、`comparison_transition_revision`、`period_anchor_ms`、`decision_boundary_ms`、`authority_sequence`、`selection_mode`、`selection_job_id`、`selection_attempt_id`、`selection_snapshot_id`、`continued_from_selection_authority_id`、`continuity_source_kind`、`authority_gap_audit_id`、`materialization_generation_id`、`owner_control_version`、`authority_outcome`、`grant_proof_kind`、`grant_predecessor_authority_id`、`effective_from_ms`、`first_eligible_close_time_ms`、`expires_at_ms`、`reason_code`、`semantic_digest`、`created_at_ms`

</details>

### `brc_selection_authority_event_bindings`

**职责**：一行一个 Authority 对 Event 的具体授予。

**主要内容**：方向、grant_state、Universe ID、member_set_digest。

**主键**：`selection_authority_id`、`event_spec_id`

**维护与用途**：授权事务写入；支持配对 Event，也可表示不给成员授权的合法结果。

<details>
<summary>完整字段（6 列）</summary>

**字段清单**：`selection_authority_id`、`event_spec_id`、`position_side`、`grant_state`、`universe_version_id`、`member_set_digest`

</details>

### `brc_selection_authority_current`

**职责**：一行一个 Spec 的当前 Authority 指针。

**主要内容**：Authority ID、projection_version 和更新时间。

**主键**：`selection_spec_id`

**维护与用途**：授权原子提交推进；新 Signal/ENTRY 结合事件绑定、Vacuum 和 proof 重查。

<details>
<summary>完整字段（4 列）</summary>

**字段清单**：`selection_spec_id`、`selection_authority_id`、`projection_version`、`updated_at_ms`

</details>

### `brc_strategy_trigger_suppressions`

**职责**：一行一个需要压制的历史自然触发身份。

**主要内容**：audit/Vacuum/generation、Event/标的/session、首次自然触发时间、原因和 detector 摘要。

**主键**：`trigger_suppression_id`

**维护与用途**：缺口审计生成，观察/权限解析读取，防止恢复时把已错过机会重新当新信号。

<details>
<summary>完整字段（11 列）</summary>

**字段清单**：`trigger_suppression_id`、`authority_gap_audit_id`、`entry_vacuum_id`、`materialization_generation_id`、`event_spec_id`、`exchange_instrument_id`、`session_reference`、`first_natural_trigger_at_ms`、`reason_code`、`detector_semantic_digest`、`created_at_ms`

</details>

<a id="catalog-signal"></a>

## 观察事实、机会与就绪状态

**范围**：从收盘观察保存事实、机会去重身份及待准入信号。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_signal_repository.py)。）

### `brc_facts_current`

**职责**：一行一个 scope 的一种最新事实。

**主要内容**：value、satisfied、observed_at、valid_until 和 projection_version。

**主键**：`fact_current_id`

**维护与用途**：Observation 更新；Signal 摄取校验当前事实与冻结事实完全一致及未过期。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`fact_current_id`、`runtime_scope_id`、`fact_definition_id`、`value`、`satisfied`、`observed_at_ms`、`valid_until_ms`、`projection_version`

</details>

### `brc_exposure_episode_current`

**职责**：一行一个 Episode domain 的当前检测记忆。

**主要内容**：armed/triggered、当前 Episode、触发/重置时间；Comparison/Authority recovery 的 revision、checkpoint 与 arming 水位。

**主键**：`episode_domain_key`

**维护与用途**：观察与 rebase 路径更新；避免连续真条件或恢复后的旧触发重复签发。

<details>
<summary>完整字段（26 列）</summary>

**字段清单**：`episode_domain_key`、`event_spec_id`、`exchange_instrument_id`、`position_side`、`episode_policy`、`state`、`exposure_episode_id`、`triggered_at_ms`、`rearmed_at_ms`、`last_observed_at_ms`、`projection_version`、`comparison_binding_digest`、`comparison_transition_revision`、`comparison_source_evidence_digest`、`comparison_armed_at_ms`、`comparison_last_observed_at_ms`、`comparison_last_detector_status`、`comparison_checkpoint_version`、`authority_recovery_id`、`authority_recovery_revision`、`authority_recovery_effective_from_ms`、`authority_recovery_first_eligible_close_time_ms`、`authority_recovery_armed_at_ms`、`authority_recovery_last_observed_at_ms`、`authority_recovery_last_detector_status`、`authority_recovery_checkpoint_version`

</details>

### `brc_signal_events`

**职责**：一行一个不可变 StrategySignal。

**主要内容**：Episode、scope/version、策略/Event、Universe/出生 Authority、标的/方向、fact_digest 与时效。

**主键**：`signal_event_id`

**维护与用途**：ingest_signal 写入，Entry/研究/Owner 查询读取；Signal 没有金额授权。

<details>
<summary>完整字段（16 列）</summary>

**字段清单**：`signal_event_id`、`exposure_episode_id`、`runtime_scope_id`、`runtime_scope_version`、`strategy_group_id`、`strategy_version_id`、`event_spec_id`、`universe_version_id`、`selection_authority_id`、`universe_semantic_digest`、`exchange_instrument_id`、`position_side`、`fact_digest`、`occurred_at_ms`、`observed_at_ms`、`expires_at_ms`

</details>

### `brc_signal_fact_snapshots`

**职责**：一行一个 Signal 使用的一种冻结事实。

**主要内容**：事实定义、role、值/满足状态、观察/到期时间和当时投影版本。

**主键**：`signal_event_id`、`fact_definition_id`

**维护与用途**：ingest_signal 同事务写入；解释当时为何触发，不随 facts_current 更新。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`signal_event_id`、`fact_definition_id`、`role`、`value`、`satisfied`、`observed_at_ms`、`valid_until_ms`、`projection_version`

</details>

### `brc_readiness_current`

**职责**：一行一个 scope 的当前就绪解释。

**主要内容**：ready/blocked 等状态、first_blocker、关联 Signal、fact_summary 与版本。

**主键**：`runtime_scope_id`

**维护与用途**：观察和准入维护；这是当前解释，不是某笔历史拒绝的永久证据。

<details>
<summary>完整字段（7 列）</summary>

**字段清单**：`runtime_scope_id`、`readiness_state`、`first_blocker`、`signal_event_id`、`fact_summary`、`updated_at_ms`、`projection_version`

</details>

<a id="catalog-trade"></a>

## 准入、容量、执行与生命周期

**范围**：交易主链路的准入结果、资金占用、订单意图和执行事实。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_repositories.py)。）

### `brc_admission_decisions`

**职责**：一行一个 Signal 的最终准入结果。

**主要内容**：admitted/rejected、排序集合摘要、组合占用、首个 blocker/约束、Policy/Scope、可空 Claim/Ticket。

**主键**：`admission_decision_id`

**维护与用途**：issue_ready_signal 原子提交；拒绝事实不创建命令，早期 readiness 阻断可尚无最终 Decision。

<details>
<summary>完整字段（32 列）</summary>

**字段清单**：`admission_decision_id`、`signal_event_id`、`exposure_episode_id`、`strategy_group_id`、`strategy_version_id`、`event_spec_id`、`universe_version_id`、`selection_authority_id`、`universe_semantic_digest`、`runtime_profile_id`、`runtime_scope_id`、`runtime_scope_version`、`owner_policy_id`、`owner_policy_version`、`venue_id`、`account_id`、`exchange_instrument_id`、`position_side`、`exposure_family`、`candidate_rank`、`candidate_count`、`candidate_set_digest`、`candidate_set_summary`、`portfolio_usage`、`decision_status`、`first_blocker`、`binding_constraint`、`capacity_claim_id`、`ticket_id`、`entry_admission_snapshot_digest`、`decision_digest`、`decided_at_ms`

</details>

### `brc_capacity_claims`

**职责**：一行一次准入定量的不可变声明。

**主要内容**：完整账户/规则/权限摘要、占用、政策比例、数量、止损/保证金、压力证明、退出绑定和失效时间。

**主键**：`capacity_claim_id`

**维护与用途**：issue_ticket 持久化，Ticket/ENTRY preflight 校验；比 Ticket 多保留大量“当时如何计算”的事实。

<details>
<summary>完整字段（86 列）</summary>

**字段清单**：`capacity_claim_id`、`ticket_id`、`signal_event_id`、`exposure_episode_id`、`strategy_group_id`、`strategy_version_id`、`event_spec_id`、`universe_version_id`、`selection_authority_id`、`universe_semantic_digest`、`runtime_profile_id`、`owner_policy_id`、`owner_policy_version`、`runtime_scope_id`、`runtime_scope_version`、`account_id`、`venue_id`、`exchange_instrument_id`、`position_side`、`netting_domain_key`、`fact_digest`、`exit_policy_id`、`exit_policy_semantic_hash`、`exit_binding_id`、`exit_binding_semantic_hash`、`exit_binding_authority_version`、`entry_admission_snapshot_digest`、`account_entry_health_digest`、`instrument_entry_health_digest`、`instrument_rules_projection_version`、`account_capacity_domain_key`、`leverage_domain_key`、`total_wallet_balance_at_claim`、`total_margin_balance_at_claim`、`total_initial_margin_at_claim`、`total_maintenance_margin_at_claim`、`available_margin_at_claim`、`mark_price_at_claim`、`position_mode_at_claim`、`margin_mode_at_claim`、`active_ticket_count_at_claim`、`remaining_slots_at_claim`、`active_strategy_group_ticket_count_at_claim`、`max_strategy_group_concurrent_tickets`、`remaining_strategy_group_slots_at_claim`、`exposure_family`、`active_family_ticket_count_at_claim`、`family_ticket_limit`、`max_same_strategy_side`、`active_strategy_side_ticket_count_at_claim`、`gross_risk_at_stop_at_claim`、`directional_risk_at_stop_at_claim`、`current_reserved_margin_at_claim`、`max_ticket_stop_risk_fraction`、`max_gross_stop_risk_fraction`、`directional_stop_risk_limit_fraction`、`max_ticket_initial_margin_fraction`、`max_gross_initial_margin_utilization`、`min_materialization_ratio`、`minimum_stop_risk_budget`、`planned_stop_risk_budget`、`max_post_fill_stop_risk_overrun_fraction`、`post_fill_stop_risk_limit`、`post_stop_stress_multiple`、`ticket_margin_budget`、`required_leverage`、`selected_leverage`、`configured_leverage_at_claim`、`leverage_change_required`、`exchange_max_leverage`、`reserved_margin`、`cross_margin_stress_evidence`、`entry_reference_price`、`quantity`、`notional`、`risk_at_stop`、`entry_order_type`、`entry_limit_price`、`initial_stop_price`、`pre_tp1_reclaim_price`、`exposure_session_end_ms`、`take_profit_prices`、`take_profit_quantities`、`decision_digest`、`created_at_ms`、`expires_at_ms`

</details>

### `brc_trade_tickets`

**职责**：一行一份不可变执行合同及有限生命周期索引。

**主要内容**：Signal/Episode、冻结政策/Universe/Authority/退出绑定、数量/价格/风险、活动域键及 terminal 时间。

**主键**：`ticket_id`

**维护与用途**：签发事务创建；终态仅推进状态/释放活动域等索引，不重算合同或给现有持仓加仓。

<details>
<summary>完整字段（60 列）</summary>

**字段清单**：`ticket_id`、`exposure_episode_id`、`signal_event_id`、`strategy_group_id`、`strategy_version_id`、`event_spec_id`、`universe_version_id`、`selection_authority_id`、`universe_semantic_digest`、`runtime_profile_id`、`owner_policy_id`、`owner_policy_version`、`runtime_scope_id`、`runtime_scope_version`、`account_id`、`venue_id`、`exchange_instrument_id`、`position_side`、`netting_domain_key`、`active_netting_domain_key`、`exposure_family`、`active_family_ticket_count_at_claim`、`family_ticket_limit`、`directional_risk_at_stop_at_claim`、`directional_stop_risk_limit_fraction`、`min_materialization_ratio`、`minimum_stop_risk_budget`、`exit_policy_id`、`exit_policy_semantic_hash`、`exit_binding_id`、`exit_binding_semantic_hash`、`exit_binding_authority_version`、`entry_reference_price`、`quantity`、`notional`、`capacity_claim_id`、`planned_stop_risk_budget`、`post_fill_stop_risk_limit`、`selected_leverage`、`leverage_change_required`、`reserved_margin`、`risk_reservation_basis`、`margin_mode`、`cross_margin_stress_model_id`、`post_stop_stress_multiple`、`claim_stress_proof_digest`、`risk_at_stop`、`entry_order_type`、`entry_limit_price`、`initial_stop_price`、`pre_tp1_reclaim_price`、`exposure_session_end_ms`、`take_profit_prices`、`take_profit_quantities`、`fact_digest`、`decision_digest`、`status`、`created_at_ms`、`expires_at_ms`、`terminal_at_ms`

</details>

### `brc_trade_aggregates`

**职责**：一行一个 Ticket 的当前生命周期投影。

**主要内容**：status/version/sequence、实仓、保护/TP1/Runner/退出订单 ID、实际风险、清理状态、Review 指针和 due。

**主键**：`ticket_id`

**维护与用途**：commit_reduction CAS 推进，Worker 调度读取；不是不可变合同。

<details>
<summary>完整字段（34 列）</summary>

**字段清单**：`ticket_id`、`status`、`version`、`last_event_sequence`、`entry_lane_held`、`position_qty`、`average_fill_price`、`actual_stop_risk`、`venue_reported_liquidation_price`、`post_fill_risk_status`、`post_fill_disposition`、`post_fill_stress_status`、`post_fill_stress_proof_digest`、`protected_qty`、`entry_exchange_order_id`、`initial_stop_exchange_order_id`、`active_stop_exchange_order_id`、`active_stop_price`、`tp1_exchange_order_id`、`tp1_target_qty`、`tp1_filled_qty`、`break_even_floor_price`、`pending_replaced_stop_exchange_order_id`、`pending_stop_price`、`pending_stop_watermark_ms`、`runner_stop_watermark_ms`、`pending_cancel_exchange_order_id`、`entry_vacuum_id`、`entry_materialization_kind`、`exit_exchange_order_id`、`review_id`、`lifecycle_due_at_ms`、`reconciliation_due_at_ms`、`updated_at_ms`

</details>

### `brc_trade_events`

**职责**：一行一个 Ticket 的领域事件。

**主要内容**：ticket、连续 sequence、event_type、payload 与发生时间。

**主键**：`event_id`

**维护与用途**：UoW reduction 追加，记录状态为何变化；不由只读页面补写。

<details>
<summary>完整字段（6 列）</summary>

**字段清单**：`event_id`、`ticket_id`、`sequence`、`event_type`、`payload`、`occurred_at_ms`

</details>

### `brc_exchange_commands`

**职责**：一行一个 Ticket/kind/generation 的持久化外部写意图。

**主要内容**：幂等键、client order ID、请求/结果 payload、状态、owner/lease、deadline 与完成时间。

**主键**：`command_id`

**维护与用途**：UoW 先创建，dispatcher/恢复更新状态；ENTRY 仅一代，unknown 不回退成可盲重发。

<details>
<summary>完整字段（15 列）</summary>

**字段清单**：`command_id`、`ticket_id`、`command_kind`、`generation`、`idempotency_key`、`venue_client_order_id`、`status`、`quantity`、`request_payload`、`result_payload`、`claim_owner`、`lease_until_ms`、`created_at_ms`、`deadline_at_ms`、`completed_at_ms`

</details>

### `brc_positions_current`

**职责**：一行一个 Netting Domain 的当前外部持仓投影。

**主要内容**：Ticket、venue/account/instrument/side、数量、均价、清算价及其可用性、观察时间。

**主键**：`netting_domain_key`

**维护与用途**：Reconciliation 依据交易所只读事实更新；数据库投影不能代替行动时外部核验。

<details>
<summary>完整字段（12 列）</summary>

**字段清单**：`netting_domain_key`、`ticket_id`、`venue_id`、`account_id`、`exchange_instrument_id`、`position_side`、`quantity`、`average_entry_price`、`venue_reported_liquidation_price`、`venue_reported_liquidation_observation_status`、`observed_at_ms`、`projection_version`

</details>

### `brc_budget_reservations`

**职责**：一行一个 Ticket 的预算预留及释放记录。

**主要内容**：预留名义、止损风险、margin、计划预算、依据、状态与释放时间。

**主键**：`budget_reservation_id`

**维护与用途**：签发占用、闭合 reduction 释放；不是可花现金余额表。

<details>
<summary>完整字段（13 列）</summary>

**字段清单**：`budget_reservation_id`、`ticket_id`、`owner_policy_id`、`venue_id`、`account_id`、`reserved_notional`、`reserved_risk`、`reserved_margin`、`planned_stop_risk_budget`、`risk_reservation_basis`、`status`、`created_at_ms`、`released_at_ms`

</details>

### `brc_account_exposure_current`

**职责**：一行一个 venue + account 的组合占用投影。

**主要内容**：gross notional、总止损风险、reserved margin、活动 Ticket 数和版本。

**主键**：`venue_id`、`account_id`

**维护与用途**：准入/释放事务原子推进，配合全局 lane 避免并发超占。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`venue_id`、`account_id`、`gross_notional`、`gross_risk_at_stop`、`current_reserved_margin`、`active_ticket_count`、`projection_version`、`updated_at_ms`

</details>

### `brc_trade_reviews`

**职责**：一行一个 Ticket 的 Review 修订。

**主要内容**：revision、supersedes_review_id、outcome、metrics、decision_impact 与时间。

**主键**：`review_id`

**维护与用途**：record/revise_trade_review 追加，Aggregate.review_id 指向当前有效版；经济缺失要明示而非补零。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`review_id`、`ticket_id`、`revision`、`supersedes_review_id`、`outcome`、`metrics`、`decision_impact`、`created_at_ms`

</details>

### `brc_entry_lane_current`

**职责**：一行全局新 ENTRY 的串行所有权。

**主要内容**：lane_id、当前 Ticket/Signal、idle/占用状态、claim_owner、lease 与版本。

**主键**：`lane_id`

**维护与用途**：签发时锁定并领取，保护后或终结时由 reducer effects 释放；已有 Ticket 安全维护不占用新的准入顺序。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`lane_id`、`ticket_id`、`signal_event_id`、`status`、`claimed_at_ms`、`lease_until_ms`、`claim_owner`、`version`

</details>

<a id="catalog-research"></a>

## 只读路径研究与采集配额

**范围**：研究记录与真实成交、资金及净收益分开。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_repositories.py)。）

### `brc_shadow_outcomes_current`

**职责**：一行一个 Signal 的只读路径研究任务与结果。

**主要内容**：来源/evaluation kind、冻结参考价/止损、观察区间、配额后任务租约/重试、MAE/MFE 与覆盖/不可用原因。

**主键**：`shadow_outcome_id`

**维护与用途**：Observation 及 projector 维护；不产生模拟 Ticket 或真实净收益，读取它为空也不能证明 Signal 不存在。

<details>
<summary>完整字段（50 列）</summary>

**字段清单**：`shadow_outcome_id`、`signal_event_id`、`admission_decision_id`、`source_kind`、`status`、`evaluation_kind`、`exchange_instrument_id`、`position_side`、`timeframe`、`entry_reference_price`、`initial_stop_price`、`initial_risk_per_unit`、`take_profit_price`、`opening_range_boundary_price`、`session_exit_deadline_ms`、`mark_price`、`index_price`、`funding_rate`、`best_bid_price`、`best_ask_price`、`best_bid_quantity`、`best_ask_quantity`、`spread_bps`、`mark_index_deviation_bps`、`horizon_start_ms`、`horizon_end_ms`、`reference_at_ms`、`price_basis`、`path_spec_digest`、`source_runtime_commit`、`path_metrics`、`last_attempted_at_ms`、`attempt_count`、`next_attempt_at_ms`、`retry_deadline_ms`、`claim_owner`、`claim_token`、`lease_until_ms`、`max_favorable_price`、`max_adverse_price`、`mfe_r`、`mae_r`、`observed_through_ms`、`completion_reason`、`first_path`、`first_path_at_ms`、`observed_bar_count`、`projection_version`、`created_at_ms`、`completed_at_ms`

</details>

### `brc_research_collection_control`

**职责**：一行研究采集控制。

**主要内容**：enabled、daily_limit、control_version。

**主键**：`control_id`

**维护与用途**：正式 [research-only 控制脚本](../../scripts/trading_kernel/configure_research_collection.py)维护；软件部署不自动打开采集。

<details>
<summary>完整字段（4 列）</summary>

**字段清单**：`control_id`、`enabled`、`daily_limit`、`control_version`

</details>

### `brc_research_collection_events`

**职责**：一行一次研究采集政策修订。

**主要内容**：版本、开关、配额、Owner identity、原因与时间。

**主键**：`event_id`

**维护与用途**：[configure_research_collection](../../scripts/trading_kernel/configure_research_collection.py) 追加；研究授权不扩大交易资本和策略范围。

<details>
<summary>完整字段（7 列）</summary>

**字段清单**：`event_id`、`control_version`、`enabled`、`daily_limit`、`owner_identity`、`reason`、`occurred_at_ms`

</details>

### `brc_research_collection_daily`

**职责**：一行一个 UTC 日的配额/覆盖计数。

**主要内容**：admitted_count、skipped_count、coverage_counts。

**主键**：`day_start_ms`

**维护与用途**：研究 admission 原子领取预算并更新；超过配额的 skipped 不能当作全体机会统计。

<details>
<summary>完整字段（4 列）</summary>

**字段清单**：`day_start_ms`、`admitted_count`、`skipped_count`、`coverage_counts`

</details>

<a id="catalog-health"></a>

## 事故、Owner 投影与维护记录

**范围**：记录安全阻断、可读状态和显式维护操作。（来源：[表定义](../../src/trading_kernel/infrastructure/pg_models.py)、[主要仓储/安装路径](../../src/trading_kernel/infrastructure/pg_repositories.py)。）

### `brc_runtime_incidents`

**职责**：一行一个运行事故及其当前解决状态。

**主要内容**：可空 Ticket、incident_kind、first_blocker、entry_block_scope/key、details 和开/关时间。

**主键**：`incident_id`

**维护与用途**：reducer/fence/恢复/健康路径维护；作用域可为单域、账户或全局，不能只数行判断安全。

<details>
<summary>完整字段（10 列）</summary>

**字段清单**：`incident_id`、`ticket_id`、`incident_kind`、`status`、`first_blocker`、`entry_block_scope`、`entry_block_key`、`details`、`opened_at_ms`、`resolved_at_ms`

</details>

### `brc_monitor_current`

**职责**：一行一个 Owner 可读监控投影。

**主要内容**：owner_status、summary/intervention、Ticket/Incident 引用、版本和时间。

**主键**：`monitor_key`

**维护与用途**：project_owner_state 与健康监控更新；终态投影必须在交易转移事务内完成。

<details>
<summary>完整字段（8 列）</summary>

**字段清单**：`monitor_key`、`owner_status`、`summary`、`intervention`、`ticket_id`、`incident_id`、`updated_at_ms`、`projection_version`

</details>

### `brc_monitor_events`

**职责**：一行一个监控投影变化事件。

**主要内容**：monitor_key、event_type、payload 与时间。

**主键**：`monitor_event_id`

**维护与用途**：监控仓储按变化追加；健康 idle tick 不应重复制造无意义事件。

<details>
<summary>完整字段（5 列）</summary>

**字段清单**：`monitor_event_id`、`monitor_key`、`event_type`、`payload`、`created_at_ms`

</details>

### `brc_retention_runs`

**职责**：一行一次显式清理/重置操作的统计记录。

**主要内容**：scope、deleted_rows、started/completed 时间。

**主键**：`retention_run_id`

**维护与用途**：当前直接写入证据为 [reset_flat_runtime.sql](../../scripts/trading_kernel/reset_flat_runtime.sql)；未发现独立常驻 retention worker，不据表名虚构自动清理策略。

<details>
<summary>完整字段（5 列）</summary>

**字段清单**：`retention_run_id`、`scope`、`deleted_rows`、`started_at_ms`、`completed_at_ms`

</details>

<a id="catalog-operations"></a>

## 迁移与切换运维

这些表不是 `pg_models.metadata` 中的业务表。Alembic 使用迁移框架的版本表；cutover journal 源码在独立 schema 中创建操作日志。这是既有切换机制的解释，不是恢复历史破坏性重建的授权。（来源：[Alembic env](../../migrations/trading_kernel/env.py)、[PostgresCutoverJournal](../../scripts/trading_kernel/cutover_tokyo.py)。）

### `public.alembic_version`

**职责**：记录 Alembic 当前安装的迁移 head。

**主要内容**：`version_num`，不保存生产 commit、认证结果或账户状态。

**主键**：`version_num`

**维护与用途**：只由正式迁移推进；运行身份检查读取。不能手工改版本号冒充完成迁移。

**字段清单**：`version_num`

### `brc_cutover_ops.cutover_runs`

**职责**：一行一次 cutover 的操作总身份与总进度，位于业务 public schema 之外。

**主要内容**：目标 server/database/venue/account/Profile、application schema、目标 commit/schema/seed/release、状态和时间。

**主键**：`cutover_id`

**维护与用途**：PostgresCutoverJournal 保留切换沿革；不是当前交易权限，也不是现行常规发布的唯一进度来源。源码建表定义可解释下列字段；实库额外 `exchange_instrument_ids_json` 列的来源尚未从当前建表源码证明，按已观测字段保留名称、不推断用途或恢复其旧语义。

**字段清单**：`cutover_id`、`server_id`、`database_identity`、`venue_id`、`account_id`、`runtime_profile_id`、`application_schema`、`target_commit`、`target_schema_revision`、`target_seed_identity`、`target_release_id`、`status`、`created_at_ms`、`updated_at_ms`、`exchange_instrument_ids_json`

### `brc_cutover_ops.cutover_phases`

**职责**：一行一次 cutover 中的一个执行阶段。

**主要内容**：阶段名与顺序、状态、尝试数、开始/完成时间及 last_error；cutover_id 关联 cutover_runs。

**主键**：`cutover_id`、`phase`

**维护与用途**：journal 开始/失败/完成阶段时更新；支持幂等判断和恢复定位，不能证明交易当前已启用。

**字段清单**：`cutover_id`、`phase`、`phase_order`、`status`、`attempt_count`、`started_at_ms`、`completed_at_ms`、`last_error`

## 沿交易链读表

| 问题 | 推荐读取顺序 | 关键区别 |
| --- | --- | --- |
| 策略是什么 | groups → versions → event_specs → required_facts / product_compatibility | 语义定义与 Owner 资金授权分开 |
| 当前能观察什么 | Universe current/members → runtime_scope → certification → facts | Snapshot 选中与 active member 不同 |
| 为什么有信号没交易 | signal + fact snapshots → readiness → admission_decision → lane / Policy | 未到最终准入可没有 Decision |
| 当时如何定量 | admission_decision → capacity_claim → Ticket → reservation/exposure | Claim 保存推导依据，Ticket 保存冻结执行合同 |
| 命令有没有发出去 | exchange_commands → trade_events / aggregate → 外部真相 | prepared / accepted / filled / protected 不同 |
| 为什么选币未生效 | selection control/job/snapshot → generation/Vacuum → certification/warming → Authority/current | 有结果不是有交易权限 |
| 平仓后为何没结束 | positions → 清理 commands → aggregate → budget release → Review/current monitor | flat、结算、Review 和经济完整度分别判断 |
| 谁改变了开关 | policy / strategy current → events → Owner authorization → Operation | 配置状态与有效可执行状态不同 |

以上是**基于仓储与用例的阅读分析**，不是生产 SQL 执行结果；具体身份、事务与查询界限见 [DATA_MODEL](DATA_MODEL.md)和[代码与测试索引](CODE_AND_TEST_INDEX.md)。

## 如何重新核对数量与防止漏表

**代码侧**：在仓库根目录运行以下只读 Python，输出的是 tracked metadata 的业务表数量与字段数，不连接服务器。

```bash
.venv/bin/python - <<'CHECK'
from src.trading_kernel.infrastructure.pg_models import metadata
print(len(metadata.tables), sum(len(table.columns) for table in metadata.tables.values()))
CHECK
```

**数据库侧**：在已授权的只读连接中运行；查非系统持久表目录，不扫描业务历史、不统计实时行数。

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SELECT n.nspname AS schema_name,
       count(*) AS table_count,
       count(*) FILTER (WHERE c.relname LIKE 'brc\_%' ESCAPE '\') AS brc_prefix_count
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT LIKE 'pg_%'
  AND n.nspname <> 'information_schema'
GROUP BY n.nspname ORDER BY n.nspname;
COMMIT;
```

**持续检查**：[知识库架构测试](../../tests/trading_kernel/architecture/test_project_knowledge.py)逐一比对 85 张业务表的章节、主键、全部字段及顺序，发现新增/漏表/字段漂移时失败；不会为了保持旧数量阻止 schema 正常演进。新增结构时同步更新目录、分组数量、来源说明和该处数量摘要，当前实库事实另更新唯一 roadmap。
