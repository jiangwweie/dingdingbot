---
title: SOR_V3_STRATEGY_CAPACITY_FLAT_COMPATIBLE_MIGRATION_IMPLEMENTATION_PLAN
status: IN_PROGRESS
date: 2026-07-31
design: docs/superpowers/specs/2026-07-31-sor-v3-strategy-group-capacity-compatible-migration-design.md
---

# SOR v3、同策略两仓与 Flat 兼容迁移实施计划

## 实施目标

在唯一 `src/trading_kernel/**` 执行链内完成以下结构性演进：

1. 以 SOR v3 首次边沿穿越和 Session Episode 替换 v2 持续状态 Signal；
2. 将 TP1 前 reclaim、Session expiry 和 time-stop 作为冻结的 Ticket 生命周期计划；
3. 在 Policy、Claim、Entry Preflight、Ticket 原子提交四层实施同 StrategyGroup 最多两个 Active Ticket；
4. 将 PostgreSQL 从冻结的 v4 baseline 前向升级到 `0002_sor_v3_strategy_group_capacity`，保留 terminal history；
5. 增加 official flat compatible-upgrade 部署模式，不实现 active-position schema handover；
6. 通过本地 unit、integration、production-shaped migration、全链和静态检查暴露问题。

## 不可变边界

- 不修改账户总容量、止损风险、保证金、杠杆和 cross margin 生产参数；
- 不在开发阶段访问服务器或执行任何交易所写操作；
- 不增加双写、旧 schema reader、fallback、并行 worker 或 SOR Entry 特判；
- 不兼容维护 active SOR v2 Ticket；部署前必须由官方 Lifecycle 终结并达到 internal/exchange flat；
- 语义错误或仅服务旧模型的代码和测试直接删除或重写；
- 每一项生产行为严格执行 RED -> GREEN -> REFACTOR，并保留可复现命令。

## Task 1：SOR v3 Registry、Fact Role、Detector 与 Episode

### 修改文件

- `src/trading_kernel/domain/strategy_registry.py`
- `src/trading_kernel/domain/signal.py`
- `src/trading_kernel/domain/detectors/sor.py`
- `src/trading_kernel/domain/detectors/registry.py`
- `src/trading_kernel/application/observe_strategy_scope.py`
- `src/trading_kernel/application/issue_ready_signal.py`
- `src/trading_kernel/infrastructure/pg_models.py`
- `src/trading_kernel/infrastructure/pg_signal_repository.py`
- `tests/trading_kernel/unit/test_strategy_registry.py`
- `tests/trading_kernel/unit/test_signal.py`
- `tests/trading_kernel/unit/detectors/test_registered_detectors.py`
- `tests/trading_kernel/unit/detectors/test_detector_negative_matrix.py`
- `tests/trading_kernel/integration/test_observation_to_signal.py`
- `tests/trading_kernel/integration/test_live_replay_detector_parity.py`

### TDD 步骤

- [ ] RED：断言 SOR Active contract 为 v3，其他五个 Event 保持 v2。
- [ ] RED：断言 `identity_reference`、`lifecycle_reference` 只接受 Decimal，且不参与 boolean condition 判定。
- [ ] RED：Long/Short 首次穿越触发，持续位于 Range 外、开放 K 线、时间错位均不触发。
- [ ] RED：同 instrument/event/side/session 生成稳定 `exposure_episode_id`，expiry 为 occurrence + 900000ms。
- [ ] RED：同 Episode 第二次 ingest 幂等，不产生第二条 Signal lineage。
- [ ] GREEN：实现版本化 Registry identity、Fact contract、纯 detector result 与 Episode builder。
- [ ] GREEN：Observation/Signal 只翻译 contract role，不按 Fact 名称推断语义。
- [ ] REFACTOR：删除 SOR v2 持续状态 producer 和只覆盖第五根立即突破的过时 fixture。

### 验证命令

```bash
pytest -q tests/trading_kernel/unit/test_strategy_registry.py tests/trading_kernel/unit/test_signal.py tests/trading_kernel/unit/detectors
pytest -q tests/trading_kernel/integration/test_observation_to_signal.py tests/trading_kernel/integration/test_live_replay_detector_parity.py
```

## Task 2：冻结 Exit Policy 与 TP1 前退出计划

### 修改文件

- `src/trading_kernel/domain/capacity.py`
- `src/trading_kernel/domain/ticket.py`
- `src/trading_kernel/domain/exit_policy.py`
- `src/trading_kernel/application/build_capacity_claim.py`
- `src/trading_kernel/application/issue_ticket.py`
- `src/trading_kernel/application/maintain_ticket_lifecycle.py`
- `src/trading_kernel/application/ports.py`
- `src/trading_kernel/infrastructure/pg_repositories.py`
- `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- `src/trading_kernel/infrastructure/pg_models.py`
- `tests/trading_kernel/unit/test_capacity.py`
- `tests/trading_kernel/unit/test_ticket.py`
- `tests/trading_kernel/unit/test_exit_policy.py`
- `tests/trading_kernel/integration/test_capacity_claim_to_ticket.py`
- `tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py`

### TDD 步骤

- [ ] RED：CapacityClaim/Ticket 必须冻结 exact `exit_policy_id` 和 semantic hash。
- [ ] RED：SOR v3 必须冻结 `pre_tp1_reclaim_price` 与 `exposure_session_end_ms`，其他 Event 必须为 `None`。
- [ ] RED：Claim/Ticket 继承 Signal Episode，禁止按 Ticket ID 重新生成 Episode。
- [ ] RED：POSITION_PROTECTED 阶段 Long/Short reclaim、Session expiry、96-bar time-stop 产生 EXIT 决策。
- [ ] RED：TP1 fill 与失效同 tick 时只处理 TP1 -> Runner transition，不创建第二个 EXIT。
- [ ] RED：Session expiry 不影响 RUNNER_PROTECTED；其他策略不获得 SOR 规则。
- [ ] GREEN：以通用冻结字段贯穿 Signal -> Claim -> Ticket -> Lifecycle。
- [ ] GREEN：Lifecycle 按 Ticket 冻结 policy identity/hash 读取，不按 current active Registry 猜测。
- [ ] REFACTOR：删除“POSITION_PROTECTED 且 TP1 未成交恒为 NO_CHANGE”的过时语义。

### 验证命令

```bash
pytest -q tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/unit/test_ticket.py tests/trading_kernel/unit/test_exit_policy.py
pytest -q tests/trading_kernel/integration/test_capacity_claim_to_ticket.py tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py
```

## Task 3：同 StrategyGroup 两仓四层容量门

### 修改文件

- `src/trading_kernel/domain/capacity.py`
- `src/trading_kernel/domain/capacity_sizing.py`
- `src/trading_kernel/application/build_capacity_claim.py`
- `src/trading_kernel/application/revalidate_entry_dispatch.py`
- `src/trading_kernel/application/issue_ticket.py`
- `src/trading_kernel/application/ports.py`
- `src/trading_kernel/infrastructure/pg_repositories.py`
- `src/trading_kernel/infrastructure/pg_models.py`
- `src/trading_kernel/infrastructure/production_runtime.py`
- `tests/trading_kernel/unit/test_capacity.py`
- `tests/trading_kernel/unit/test_capacity_sizing.py`
- `tests/trading_kernel/unit/test_entry_dispatch_preflight.py`
- `tests/trading_kernel/integration/test_issue_ticket.py`
- `tests/trading_kernel/integration/test_signal_to_ticket.py`
- `tests/trading_kernel/integration/test_owner_projection.py`

### TDD 步骤

- [ ] RED：Policy 新增正整数 `max_strategy_group_concurrent_tickets=2`。
- [ ] RED：Usage/Claim 冻结策略组当前数量、上限和剩余槽位并进入 decision digest。
- [ ] RED：0/1 个同策略 Ticket 允许，2 个时第三个 Claim 返回 `strategy_group_capacity_exhausted`。
- [ ] RED：SOR Long/Short 和不同 instrument 合并计数；不同 venue/account 隔离。
- [ ] RED：两个 SOR + 一个 MI 可达到账户总容量 3。
- [ ] RED：Claim 后计数变化时 Entry Preflight fail-closed。
- [ ] RED：global Entry Lane 下 Ticket issue 再次精确计数，拒绝不创建 Ticket、Reservation、Command、Incident。
- [ ] GREEN：实现统一 status/blocker contract 和有界 PostgreSQL count query。
- [ ] REFACTOR：容量层只使用 StrategyGroup identity，不解释 SOR 市场语义。

### 验证命令

```bash
pytest -q tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/unit/test_capacity_sizing.py tests/trading_kernel/unit/test_entry_dispatch_preflight.py
pytest -q tests/trading_kernel/integration/test_issue_ticket.py tests/trading_kernel/integration/test_signal_to_ticket.py tests/trading_kernel/integration/test_owner_projection.py
```

## Task 4：冻结 v4 Baseline 与实现 0002 兼容迁移

### 修改文件

- `migrations/trading_kernel/v4_schema.py`
- `migrations/trading_kernel/versions/0001_trading_kernel_baseline_v4.py`
- `migrations/trading_kernel/versions/0002_sor_v3_strategy_group_capacity.py`
- `src/trading_kernel/infrastructure/pg_models.py`
- `src/trading_kernel/infrastructure/runtime_identity.py`
- `scripts/trading_kernel/bootstrap_schema.py`
- `scripts/trading_kernel/verify_schema.py`
- `tests/trading_kernel/integration/test_schema_baseline.py`
- `tests/trading_kernel/integration/test_bootstrap_schema.py`
- `tests/trading_kernel/integration/test_clean_baseline_rebuild.py`
- `tests/trading_kernel/integration/test_sor_v3_compatible_migration.py`
- `tests/trading_kernel/architecture/test_strategy_universe_operability_architecture.py`

### TDD 步骤

- [ ] RED：修改 head metadata 不得改变 `0001` 创建结果。
- [ ] RED：revision graph 必须为唯一链 `0001 -> 0002`、单 head、无分叉。
- [ ] RED：空库严格执行 base -> head，metadata/schema identity 完全一致。
- [ ] RED：production-shaped v4 fixture 升级后所有历史 identity/row count/lineage 保留。
- [ ] RED：回填 legacy Signal Episode、Policy 上限、Claim strategy count、Claim/Ticket Exit Policy identity/hash。
- [ ] RED：v2/v3 相同 `event_id` 可按不同 strategy version 共存，所有 lookup 只使用 `event_spec_id`。
- [ ] RED：active Ticket、Reservation、Command、Incident 不由 migration 删除或终结。
- [ ] GREEN：复制 exact v4 metadata 到 migration-owned snapshot，`0001` 不再导入 runtime metadata。
- [ ] GREEN：实现显式、事务化 `0002` DDL 与受保护 downgrade。
- [ ] REFACTOR：删除“只能有一个 migration 文件”的过时架构断言和 rebuild-only schema 假设。

### 验证命令

```bash
pytest -q tests/trading_kernel/integration/test_schema_baseline.py tests/trading_kernel/integration/test_bootstrap_schema.py tests/trading_kernel/integration/test_clean_baseline_rebuild.py tests/trading_kernel/integration/test_sor_v3_compatible_migration.py
pytest -q tests/trading_kernel/architecture/test_strategy_universe_operability_architecture.py
```

## Task 5：Registry Seed、Universe 切换与历史 Review 分类

### 修改文件

- `src/trading_kernel/infrastructure/pg_strategy_registry.py`
- `src/trading_kernel/infrastructure/pg_repositories.py`
- `src/trading_kernel/domain/trade_review.py`
- `scripts/trading_kernel/seed_strategy_registry.py`
- `scripts/trading_kernel/seed_runtime_authority.py`
- `scripts/trading_kernel/bootstrap_strategy_universes.py`
- `scripts/trading_kernel/classify_sor_v2_history.py`
- `tests/trading_kernel/integration/test_strategy_registry_seed.py`
- `tests/trading_kernel/integration/test_runtime_authority_seed.py`
- `tests/trading_kernel/integration/test_strategy_universe_activation.py`
- `tests/trading_kernel/integration/test_sor_v2_history_classification.py`

### TDD 步骤

- [ ] RED：seed 退休 v2 SOR、激活 v3 SOR，不删除或覆盖 v2 history。
- [ ] RED：v2 Universe 受控退休，v3 Universe 只能经 Warming -> Active 原子切换。
- [ ] RED：BNB 仅追加 unverified entry semantics Review revision，保持原 lineage。
- [ ] RED：三笔错误语义 Ticket 仅追加 excluded entry-alpha classification，保留 execution/lifecycle/economics evidence。
- [ ] GREEN：实现幂等 seed 和 append-only exact-ticket Review classification command。
- [ ] REFACTOR：禁止 runtime 读取文档或生成报告作为权威。

### 验证命令

```bash
pytest -q tests/trading_kernel/integration/test_strategy_registry_seed.py tests/trading_kernel/integration/test_runtime_authority_seed.py tests/trading_kernel/integration/test_strategy_universe_activation.py tests/trading_kernel/integration/test_sor_v2_history_classification.py
```

## Task 6：Official Flat Compatible-Upgrade 部署模式

### 修改文件

- `scripts/trading_kernel/deploy_tokyo_release.py`
- `scripts/trading_kernel/verify_flat_cutover.py`
- `scripts/trading_kernel/verify_schema.py`
- `tests/trading_kernel/unit/test_deploy_tokyo_release.py`
- `tests/trading_kernel/integration/test_production_cutover_adapter.py`
- `tests/trading_kernel/integration/test_cutover_state_machine.py`
- `tests/trading_kernel/integration/test_sor_v3_flat_compatible_deployment.py`

### TDD 步骤

- [x] RED：compatible-upgrade 在 active Ticket、position、open order、unresolved Command、open Incident 任一非零时 fail-closed。
- [x] RED：要求历史 Ticket terminal/reviewed、Reservation/Domain released、Entry fenced、旧 writer 全停。
- [x] RED：只运行 certified migration chain、preservation certification、seed、runtime identity switch、worker restart 和 v3 Universe warming。
- [x] RED：recording venue 在 dry-run/rehearsal 中收到零 exchange mutation。
- [x] RED：regular release 仍禁止 schema change；compatible-upgrade 不复用 protected-ticket handover。
- [x] GREEN：增加显式 deployment mode、preflight manifest、postflight preservation digest 和 schema head 参数。
- [x] REFACTOR：删除 active-position schema handover、临时 SQL 和 rebuild-only 分支。

### 验证命令

```bash
pytest -q tests/trading_kernel/unit/test_deploy_tokyo_release.py
pytest -q tests/trading_kernel/integration/test_production_cutover_adapter.py tests/trading_kernel/integration/test_cutover_state_machine.py tests/trading_kernel/integration/test_sor_v3_flat_compatible_deployment.py
```

## Task 7：CURRENT 文档与操作证据

### 修改文件

- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`
- `docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md`
- `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`
- `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`（仅实际部署后更新生产易变事实）
- `docs/superpowers/specs/2026-07-31-sor-v3-strategy-group-capacity-compatible-migration-design.md`
- 本计划

### 步骤

- [x] 更新 schema authority 为单 head 前向 revision chain。
- [x] 更新 Policy 参数语义，明确账户总容量 3、同 StrategyGroup 容量 2。
- [x] 增加 official flat compatible-upgrade 合同和 hard gates。
- [x] 删除与 compatible migration 冲突的 rebuild-only 和 active handover 描述。
- [x] 扫描 TODO/TBD、旧 SOR v2 producer、旧 schema head、旧容量语义和文档重复权威。
- [x] 未实际部署前不修改 MAIN_CONTROL_ROADMAP 的生产 commit、schema、tag 或 runtime snapshot。

## Task 8：全量自测、架构审查与 Deployable 判定

### Fresh verification

- [x] Targeted unit tests 全部通过。
- [x] Targeted PostgreSQL integration tests 全部通过。
- [x] Production-shaped v4 -> 0002 preservation 测试通过。
- [x] Empty database base -> head 测试通过。
- [x] Full Trading Kernel test suite 通过。
- [x] Architecture tests 通过。
- [x] Ruff 通过。
- [x] Mypy 通过。
- [x] `git diff --check` 通过。
- [x] migration/deployment recording venue 证明零 exchange mutation。

### 审查维度

- [x] 设计验收条目逐条映射到代码和测试。
- [x] Domain 保持纯净，无 SQLAlchemy、venue client、filesystem 或 subprocess 泄漏。
- [x] 金融数值继续使用 `Decimal`，核心边界继续使用 frozen named Pydantic models。
- [x] 网络 I/O 不进入数据库事务；所有 exchange write 仍 durable-before-dispatch。
- [x] Runtime 查询使用 exact identity 和 bounded current-state query。
- [x] 无 dual write、fallback、old-table reader、平行 worker、active v2 compatibility surface。
- [x] 无语义过时测试、占位符、跳过关键门或静默降级。
- [x] 分支 diff 仅包含本次批准范围。

### 最终命令

```bash
pytest -q tests/trading_kernel
ruff check src/trading_kernel scripts/trading_kernel tests/trading_kernel
mypy src/trading_kernel scripts/trading_kernel
git diff --check
git status --short
```

## 提交策略

按可独立审查的结构提交：

1. `docs(kernel): plan SOR v3 flat compatible migration`
2. `feat(kernel): define SOR v3 signal episodes`
3. `feat(kernel): freeze SOR v3 lifecycle policy`
4. `feat(kernel): enforce strategy group ticket capacity`
5. `feat(kernel): migrate v4 history to SOR v3 schema`
6. `feat(kernel): add flat compatible deployment mode`
7. `docs(kernel): align current SOR v3 deployment authority`
8. 必要时独立提交由全量验证暴露的结构性修复。
