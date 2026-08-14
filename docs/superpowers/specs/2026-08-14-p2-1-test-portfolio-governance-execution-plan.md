---
title: P2_1_TEST_PORTFOLIO_GOVERNANCE_EXECUTION_PLAN
status: OWNER_REVIEW_REQUIRED_NO_IMPLEMENTATION
date: 2026-08-14
phase: P2.1
design: 2026-08-14-p2-1-test-portfolio-governance-design.md
---

# P2.1 测试资产治理执行计划

## 目标

在不修改生产行为、Schema、Policy、Registry、Worker 或 Exchange 写入边界的前提下，
完成测试合同所有权、共享 Support、PostgreSQL Harness、重复测试退休和分级验证组合。

本计划必须在 Owner 复核设计后才能执行。当前状态不授权修改测试代码。

## 当前基线

| 指标 | 基线 |
| --- | ---: |
| tracked 测试文件 | 158 |
| 测试代码行 | 67,813 |
| 静态测试函数 | 1,076 |
| 跨 test 模块 Helper 导入 | 92 行 / 47 文件 |
| 本地 `_run_alembic` 定义 | 16 |
| 最近完整认证 | 611.083 秒 |
| Integration | 524.033 秒 |

这些数字用于审计变化，不构成必须追求的数量指标。

## 允许修改范围

- `tests/trading_kernel/**`
- `pytest.ini`
- `scripts/trading_kernel/certify_release_candidate.py`
- `scripts/owner_console/certify_release_candidate.py`
- 新增的非运行时 verification/support 脚本
- P2.1 设计、执行和稳定权威文档

如需修改其他文件，必须停下并重新审查任务边界。

## 禁止修改范围

- `src/trading_kernel/domain/**`
- `src/trading_kernel/application/**`
- `src/trading_kernel/infrastructure/**`
- `src/trading_kernel/interfaces/**`
- `migrations/trading_kernel/**`
- `deploy/systemd/**`
- Strategy Registry、Owner Policy、RuntimeProfile 和 Universe Seed
- Tokyo 服务、生产 PostgreSQL、Nginx 和 Exchange

如果现有测试只能通过修改生产逻辑才能继续，P2.1 必须报告该测试或生产缺陷，不能在
测试治理任务中顺带修复业务行为。

## 实施顺序

### Task 1：建立测试合同清单

#### 操作

1. 按 Domain、Application、Adapter、PostgreSQL、Runtime、Full Chain、Architecture、
   Deployment 对所有测试文件分组；
2. 为每个文件记录主要当前合同、负向故障类和相邻重复文件；
3. 建立三类处理结论：`keep`、`merge/move`、`delete_retired`；
4. 对 Migration 测试额外记录 Source Revision、Target Revision 和 Preservation 责任；
5. 对 Deployment 测试额外记录 R1/R2/R3/R4 责任。

#### 产出

- 经过人工审查的 tracked Test Portfolio 定义或代码常量；
- 删除候选及其替代所有者清单；
- 不生成运行时 JSON/Markdown 报告。

#### 验证

- 当前关键合同均至少有一个主要所有者；
- 未出现“为了保留测试而保留退休语义”。

### Task 2：建立 Shared Test Support

#### 操作

1. 创建 `tests/trading_kernel/support/**`；
2. 优先移动被多层使用的 Ticket、Signal、Command、Venue、Policy 和 Lifecycle Builder；
3. 将 Migration、Issue Ticket、Command Dispatch 等共享 Helper 从 `test_*.py` 移出；
4. 更新引用，每完成一个 Helper Cluster 即运行受影响测试；
5. 删除原测试模块中的重复私有 Helper。

#### 首批处理 Cluster

| Cluster | 当前主要来源 | 主要消费者 |
| --- | --- | --- |
| Ticket identity/builders | `unit/test_ticket.py`、`integration/test_issue_ticket.py` | Unit、Integration、Full Chain |
| Command/dispatch fixtures | `integration/test_command_dispatch.py` | Lifecycle、Reconciliation、Full Chain |
| Venue fake | `unit/test_venue_adapter.py` | Adapter、Dynamic Routing、Full Chain |
| Lifecycle progression | `integration/test_ticket_lifecycle_maintenance.py` | Controlled Exit、Fault、Closure |
| Migration source builders | `test_sor_v3_compatible_migration.py` 等 | Portfolio migration、R4 rehearsal |

#### 验证

- 每个 Cluster 只运行受影响文件；
- `rg` 确认跨 `test_*.py` import 逐批下降；
- 不运行全量套件。

### Task 3：建立 PostgreSQL Test Harness

#### 操作

1. 复用现有 Owner Console disposable PostgreSQL 身份认证规则；
2. 建立 current-head Template Database；
3. 每个当前行为测试 Clone 唯一数据库；
4. 每个测试结束后关闭连接并删除精确数据库；
5. 将散落的 URL、Create/Drop 和 Alembic Helper 迁移到 Support；
6. Migration/Clean Rebuild 测试保持精确 Source Revision，不使用 Head Template；
7. 为异常退出增加可重复清理和确定性命名。

#### RED / GREEN

1. RED：Harness 拒绝非预期 Docker/PostgreSQL 身份；
2. RED：两个测试数据库不能看到对方业务行；
3. RED：Migration Test 不能误用 Head Template；
4. GREEN：代表性 Unit+PG Integration、Universe 和 Full Chain 测试使用新 Harness 通过。

#### 聚焦验证

- Harness 单元测试；
- `test_pg_unit_of_work.py`；
- `test_issue_ticket.py` 的代表性事务分支；
- 一个 Universe Integration；
- 一个 Full Chain Closure。

### Task 4：逐 Cluster 合并和删除重复测试

#### 顺序

1. Deployment/Certification；
2. Schema Bootstrap/Migration；
3. StrategyUniverse；
4. Owner Console read stack；
5. Ticket/Command/Lifecycle；
6. Full Chain fault matrix。

#### 删除门禁

每个删除项必须在 Diff 审查中说明：

```text
deleted test
-> retired or duplicated contract
-> replacement owner
-> exact focused verification command
```

只允许合并相同故障类，不允许将 Unknown Outcome、Partial Fill、Protection、Closure 或
Identity Mismatch 压缩成只走 happy path 的测试。

### Task 5：定义验证组合

#### 操作

1. 在 tracked verification code 中定义 Fast、R1、R2、R3、R4 和 Periodic Audit
   Command Set；
2. Command Set 使用显式路径或 module-level marker，不使用自动 Diff 猜测；
3. Certification Manifest 继续绑定精确 Commit、Schema 和 Command Set digest；
4. P2.1 阶段保持当前 Kernel Release Certification 完整组合有效；
5. 仅为 P2.2 提供未来按 Release Class 选择 Command Set 的接口，不在本阶段改变生产
   部署分类行为。

#### 验证

- Unit 测试证明 Command Set 稳定、无重叠和 digest 可重复；
- Owner API Certification 继续只包含 Owner API 边界；
- Kernel Certification 在 P2.2 前仍能执行完整当前组合。

### Task 6：最终验证与审查

#### 验证顺序

1. 对最后一个变更 Cluster 运行 Focused Tests；
2. 运行 Fast Tier；
3. 冻结精确候选 Commit；
4. **只运行一次完整 Kernel Release Certification**；
5. 运行一次文档权威测试；
6. 执行 `git diff --check`；
7. 审查删除清单、Support 边界、Command Set 和耗时变化。

不在实现过程中反复运行 Integration 或 Full Chain 全目录。

## 测试策略

| 改动 | 必要验证 | 明确不运行 |
| --- | --- | --- |
| 单个 Builder 移动 | 直接消费者测试 | 全 Integration |
| PG Harness | Harness + 代表性 PG/Full Chain | 所有 Adapter Unit |
| 单个 Cluster 合并 | 该 Cluster Focused | 其他 Cluster |
| Command Set | Certification Unit | 真实部署 |
| 最终候选 | 完整 Release Certification 一次 | Periodic Audit 的额外重复运行 |

## 提交拆分

建议形成以下可独立回退的提交：

1. `test: establish shared trading-kernel support`
2. `test: centralize disposable postgres harness`
3. `test: consolidate current contract coverage`
4. `test: define proportional verification portfolios`
5. `docs: close p2.1 test portfolio governance`

每个提交只包含一个可审查目的。测试删除与生产代码修改不得出现在同一提交。

## 性能与资源

- Template Database 只存在于本地 disposable PostgreSQL；
- 每个测试仍使用唯一 Clone，避免共享业务状态；
- 并发执行不是首期目标，避免给本地 PostgreSQL 和 2C4G 生产资源模型引入额外假设；
- 不在 Tokyo 运行测试治理；
- 不增加生产 Worker、Timer、文件输出或缓存。

## 风险与控制

| 风险 | 控制 |
| --- | --- |
| 误删唯一故障类 | 删除项必须指定 replacement owner |
| Template 泄漏业务行 | 每测试唯一 Clone + 隔离 RED 测试 |
| Migration 测试误用 Head | Harness 类型和显式 Source Revision 拒绝 |
| Shared Helper 变成第二生产实现 | Support 只能建模输入和 Fake，不复制 reducer/use case |
| Release 组合过早变轻 | P2.2 分类器完成前保持当前完整 Kernel Certification |
| 为追求耗时扩大改造 | 不设强制百分比；到达边界后记录剩余成本 |

## 预计工作量

| 工作包 | 净开发时间 |
| --- | ---: |
| 合同清单与删除审查 | 0.5–1 天 |
| Shared Support 抽离 | 1–2 天 |
| PostgreSQL Harness | 1–2 天 |
| Cluster 合并和退休 | 1–2 天 |
| Test Portfolio、最终验证和文档 | 0.5–1 天 |
| **合计** | **4–8 个净开发日** |

## 完成条件

P2.1 只有在以下条件全部满足时完成：

1. 跨 `test_*.py` Helper import 为零；
2. 当前 Head PostgreSQL 测试使用统一 Harness；
3. Migration/Clean Rebuild 测试继续证明精确 Source Revision；
4. 删除和合并项具有 replacement owner；
5. 四级验证和 Release Class Command Set 已定义；
6. 当前完整 Kernel Release Certification 对最终候选只运行一次并通过；
7. 文档权威测试与 `git diff --check` 通过；
8. 无生产代码、Schema、Policy、Registry、Worker、Exchange 或 Tokyo 变化；
9. P2.1 稳定结论回写当前权威文档；
10. Owner 收到变更、删除、未运行测试和剩余风险的明确审查报告。
