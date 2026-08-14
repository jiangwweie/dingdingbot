---
title: P2_1_TEST_PORTFOLIO_GOVERNANCE_DESIGN
status: OWNER_REVIEW_REQUIRED
date: 2026-08-14
phase: P2.1
---

# P2.1 测试资产治理设计

## 决策摘要

P2.1 不以“减少测试数量”为目标，也不通过跳过当前安全合同换取更短耗时。它把测试
从持续累加的历史记录改造成一个有所有权、可删除、可分层运行的工程资产组合：

```text
Current Contract / Failure Class
-> one primary test owner
-> shared production-shaped support
-> proportional verification tier
-> exact release-class certification
```

本阶段采用以下边界：

1. 保留 **Focused、Fast、Release、Periodic Audit** 四级验证语义；
2. 测试删除必须证明其当前合同已由另一项更直接的测试拥有，或者其语义已经退休；
3. 当前 Schema 行为测试使用隔离数据库，但不再由每个测试重复执行完整 Alembic；
4. Migration、Clean Rebuild、历史 Preservation 继续使用独立数据库和精确 Revision；
5. 共享 Helper 移入明确的 `tests/trading_kernel/support/**`，测试模块不得继续互相导入
   `test_*.py` 私有函数；
6. P2.1 定义 Release Class 对应的测试组合，P2.2 才负责将其接入发布分类、Manifest
   复用和部署阶段状态；
7. 不增加独立进度文档。设计状态由本文档、执行状态由 Git 和当前任务计划记录，稳定
   结果在阶段完成后回写 `docs/current/*`。

本文档是设计提案，不授权删除测试、修改认证命令或执行生产部署。

## 已知客观事实

以下为 2026-08-14 对当前工作树的静态审计。测试函数数字来自源代码中的
`test_*` 定义，不等同于参数化后的 Pytest collected case 数。

### 测试资产规模

| 层级 | 文件数 | 静态测试函数数 | 当前主要职责 |
| --- | ---: | ---: | --- |
| Unit | 79 | 576 | 纯领域、应用决策、Adapter 输入输出和脚本行为 |
| Architecture | 13 | 61 | 退休语义、文件权威、部署单元和依赖方向 |
| Integration | 52 | 386 | PostgreSQL、Schema、Repository、Worker 和部署边界 |
| Full Chain | 13 | 32 | 跨 Admission、Ticket、Command、Lifecycle、Closure 的完整故障类 |
| Interfaces | 1 | 21 | Owner HTTP 契约和只读事务 |
| **合计** | **158** | **1,076** | **67,813 行测试代码** |

来源：`tests/trading_kernel/**` 当前 tracked files 静态扫描。

### 最近一次完整 Release Certification

当前 Kernel 认证命令集依次运行 Unit+Architecture、Integration、Full Chain、Ruff、
Mypy 和 `git diff --check`。最近生产候选 Manifest 记录：

| 命令组 | 耗时 | 占完整认证比例 |
| --- | ---: | ---: |
| Unit + Architecture | 11.146 秒 | 1.8% |
| Integration | 524.033 秒 | 85.8% |
| Full Chain | 75.264 秒 | 12.3% |
| Ruff + Mypy + Diff | 0.640 秒 | 0.1% |
| **合计** | **611.083 秒，约 10.2 分钟** | **100%** |

来源：Git Common Directory 中当前生产候选的
`brc.trading_kernel.release_certification.v1` Manifest。该 Manifest 是认证证据，
不是运行时数据权威。

### 重复基础设施与耦合

| 现象 | 当前静态数量 | 影响 |
| --- | ---: | --- |
| 本地 `_run_alembic` 定义 | 16 | Migration 启动、错误处理和命令参数重复 |
| 使用 `_run_alembic` 的文件 | 30 | 当前 Schema 测试与 Migration 测试未形成统一 Harness |
| 使用 `create_async_engine` 的文件 | 34 | 数据库创建和销毁责任分散 |
| 使用 subprocess 的测试文件 | 25 | CLI、Alembic、Git、Docker 与部署 Fake 的边界分散 |
| 跨 `test_*.py` 导入 Helper 的代码行 | 92 | 私有 Fixture 成为非显式公共 API |
| 存在跨 test 模块导入的文件 | 47 | 修改一个大型测试模块可能影响多个测试层级 |
| 显式 module/session/class scope Fixture | 0 | 当前异步 Fixture 默认按函数创建，重复 Schema 初始化成本高 |

当前已经存在 `owner_console_support.py`、`universe_activation_support.py`、
`universe_certification_support.py` 和 Full Chain lifecycle support，证明显式 Support
模块是已接受方向；但大部分 Ticket、Command、Migration 和 Venue Fixture 仍从
`test_*.py` 互相导入。

## 问题定义

### 1. 测试增长没有退休机制

新增 Schema、部署路径和策略能力时不断增加测试，但旧代际被替换后，没有强制执行：

- 删除退休期望；
- 合并重复故障类；
- 将共享 Fixture 从测试模块抽离；
- 重新判断该证明属于 Release 还是 Periodic Audit。

结果是测试数量成为历史活动量，而不是当前合同的最小证据集。

### 2. Integration 耗时由基础设施重复主导

完整认证本身约 10.2 分钟，并不是数小时部署的全部原因；但 Integration 占其中
85.8%。当前 30 个文件执行 Alembic 相关启动，且没有显式非函数级 Fixture。每个测试
独立数据库是正确的隔离目标，但“独立数据库”不要求每次都从空库执行完整当前 Head
Migration。

### 3. 测试模块承担了公共 Fixture API

Full Chain、Integration 和 Unit 测试大量从其他 `test_*.py` 导入 `_ticket`、`_issue`、
`_seed_policy`、Fake Exchange 和迁移 Helper。这会造成：

- 测试所有权不清；
- 重命名或删除一个测试文件时出现级联影响；
- Pytest collection 模块同时承担 Fixture library；
- 退休测试难以删除，因为其他测试依赖其私有实现。

### 4. Release Certification 未按发布级别表达风险

Kernel `certify_release_candidate.py` 当前对任意 Kernel Candidate 运行完整 Unit、
Architecture、Integration 和 Full Chain。R3 同 Schema 改动与 R4 Schema/Authority
Upgrade 使用同一测试组合。P2.1 需要先定义测试组合，P2.2 再确保文件分类器将共享或
未知变更升级到更重的 Release Class。

## 目标

1. 每项当前业务合同或生产形状故障类只有一个清楚的主要测试所有者；
2. 删除退休、重复、只证明内部实现细节且没有独立风险价值的测试；
3. 当前 Head PostgreSQL 测试继续隔离，但复用一次构建的可信 Schema Template；
4. Migration 和历史 Preservation 测试继续从精确 Source Revision 独立升级；
5. 消除测试模块之间的私有 Helper 依赖；
6. 形成明确、可审计的验证层级和 Release Class 测试组合；
7. 完整 Release Suite 只在冻结候选上运行一次，等待外部条件时不重复运行；
8. 为后续 P2.2 提供稳定的 Certification Command Set 输入。

## 非目标

- 不修改 Trading Kernel 业务行为；
- 不调整策略、风险、资本、Universe、Venue 或 Exchange 写入边界；
- 不修改 PostgreSQL 生产 Schema；
- 不通过 Mock 替换必须由 disposable PostgreSQL 证明的行为；
- 不把 Integration 测试全部降级为 Unit；
- 不为了达到测试数量指标删除独立故障类；
- 不在 P2.1 内改变生产部署状态；
- 不建设自动猜测代码 Diff 对应测试的复杂系统。

## 方案比较

| 方案 | 维护成本 | 运行成本 | 安全证据 | 结论 |
| --- | ---: | ---: | ---: | --- |
| 只删除大文件或旧测试 | 低 | 短期下降 | 高风险，容易删掉唯一证明 | 拒绝 |
| 只增加 Fast 命令，测试结构不变 | 低 | 日常下降 | Release 仍持续膨胀 | 不充分 |
| 大规模重写全部测试 | 极高 | 不确定 | 迁移过程中风险大 | 拒绝 |
| **合同所有权 + Support 抽离 + PG Template + 分级组合** | 中 | 可持续下降 | 保留唯一故障类 | **采用** |

## 推荐设计

### 1. Test Contract Ownership

每个测试文件必须能归入以下一个主要所有权：

| 所有权 | 应证明的内容 | 不应重复证明 |
| --- | --- | --- |
| Domain Unit | Reducer、Identity、Policy 纯决策 | PostgreSQL 与进程行为 |
| Application Unit | Use Case、Port 调用、拒绝和 Effect | Adapter 内部 SQL |
| Adapter Unit | Venue payload、协议冻结、错误映射 | 完整 Ticket 生命周期 |
| PostgreSQL Integration | Schema constraint、事务、Repository 和 exact current query | 已由 Domain Unit 完整证明的分支表 |
| Runtime Integration | Worker cadence、lease、timeout、restart-safe progression | 全部策略样本矩阵 |
| Full Chain | 跨边界唯一高风险路径和 fault recovery | 每个低层参数组合 |
| Architecture | 禁止的依赖、文件、服务、旧语义和 Authority | 业务结果计算 |
| Deployment | Release Class、Manifest、阶段恢复和 Writer overlap | 领域生命周期公式 |

实现阶段先形成机器可读的显式测试组合和审查清单，不创建新的运行时 JSON 或报告
文件。合同所有权属于 tracked code 和测试，不属于生成的审计输出。

### 2. 四级验证

| Tier | 触发时机 | 组合 |
| --- | --- | --- |
| **Focused** | 一项行为开发或修复 | 精确 RED 测试、相邻当前合同、一个回归 |
| **Fast** | 日常提交前 | Unit、Architecture、静态检查、受影响 Integration Slice |
| **Release** | 精确冻结候选 | 按 R1/R2/R3/R4 的显式命令集认证一次 |
| **Periodic Audit** | 最终审计、Schema 治理或显式维护 | 历史跨版本 Migration、Clean Rebuild、退休语义全库扫描和昂贵全程序证明 |

P2.1 只建立组合与测试结构。**在 P2.2 的 Release Class 分类器能够可靠升级共享、
Schema、Authority 和未知改动之前，现有 Kernel 完整认证命令不得提前削弱。**

### 3. PostgreSQL Test Harness

新增显式 Support Harness，责任如下：

```text
attest disposable local PostgreSQL
-> create current-head template database once
-> clone one unique isolated database per test
-> connect with asyncpg/SQLAlchemy
-> test
-> close connections
-> drop exact disposable database
```

边界：

1. Template 只用于“当前 Head 行为”测试；
2. 每个测试仍拥有唯一数据库，不共享业务行；
3. Migration 测试不得从 Head Template 开始；
4. Migration 测试显式指定 `base/0002/0003/0004/head` Source Revision；
5. Harness 必须验证本地 disposable PostgreSQL 身份，禁止连接 Tokyo 或非预期数据库；
6. 创建、Clone、Drop 失败必须显式失败，不保留模糊可复用状态；
7. 不使用文件快照代替 PostgreSQL Schema Authority。

### 4. Shared Test Support

目标结构：

```text
tests/trading_kernel/support/
├── identities.py
├── tickets.py
├── signals.py
├── commands.py
├── venues.py
├── postgres.py
├── migrations.py
└── lifecycle.py
```

现有专用 Support 模块可保留在其领域目录，或者在引用范围扩大时迁入统一 Support。
禁止 Support 模块包含 `test_*` 函数，禁止其成为生产代码依赖。

阶段完成后，tracked tests 中不得再从其他 `test_*.py` 导入私有 Helper。

### 5. 重复与退休规则

满足以下任一条件时，测试可以删除或合并：

1. 期望语义已经退休，且当前合同明确禁止恢复；
2. 同一输入、同一故障类、同一可观察结果已由另一更直接层级拥有；
3. 测试只断言内部调用顺序或字符串布局，产品合同对此没有要求；
4. 测试因共享 Fixture 被复制，抽离 Support 后可参数化合并；
5. 一个 Full Chain 测试仅重复 Integration 已完整证明的低层参数矩阵；
6. 旧 Schema 测试不再属于任何可升级 Source Revision 或 Preservation 合同。

以下情况不能删除：

- Unknown Outcome、Partial Fill、same-domain exclusion、global ENTRY serialization；
- Initial Stop、TP1、Runner、Controlled Exit 和 exact closure；
- current forward-only Migration 与 Preservation；
- Runtime Identity、Writer overlap、Entry Fence 和 postflight；
- Owner read-only、no file authority 和 no exchange mutation；
- 当前支持的每个 Strategy Event producer 的 Live/Replay 语义。

### 6. Release Class Test Portfolio

P2.1 定义但不提前激活以下组合：

| Release Class | 必须验证 | 不需要验证 |
| --- | --- | --- |
| R1 Static | Frontend build、route/assets、public HTTPS smoke | Kernel、PostgreSQL、Exchange |
| R2 Owner API | Owner application/API、read repository contract、Schema compatibility、read-only boundary | Kernel full chain、Migration rehearsal |
| R3 Same-Schema Kernel | Unit、Architecture、current-head Integration、Full Chain、Ruff、Mypy、Diff | 历史 cross-version Migration，前提是分类器能证明未触碰 Schema/Authority |
| R4 Schema/Authority | R3 全部 + exact source upgrade、Preservation、Clean Rebuild、cutover recovery | 无 |
| Periodic Audit | 全历史 source-path、退休扫描和昂贵 whole-program proof | 不参与普通等待或重复部署 |

Command Set 必须以 tracked code 的不可变常量存在，并进入 Certification Manifest digest。
P2.2 负责将 Release Class、Candidate Commit 和该 Command Set 绑定。

### 7. 性能度量

不以“测试数量下降”作为验收指标。阶段实施使用现有生产 Certification Manifest 作为
初始耗时基线，不为获得 baseline 再运行一次完整套件。

最终冻结候选只运行一次完整 Release Certification，并记录：

- 每个 command group duration；
- Integration 和 Full Chain 总耗时；
- PostgreSQL Database Create、Clone、Drop 次数；
- Test collection 数量；
- 删除、合并和移动的测试所有权。

若耗时没有下降，必须指出剩余主要成本，但不为了追求比例继续扩大改造范围。

## 数据、事务与运行时归属

| Concern | 归属 |
| --- | --- |
| 测试组合 | tracked verification code |
| 测试结果 | CLI stdout 和 Certification Manifest，仅作为构建证据 |
| PostgreSQL Test Database | 本地 disposable PostgreSQL |
| Production PostgreSQL | P2.1 禁止访问和修改 |
| Exchange | Recording Fake；P2.1 不调用真实 Exchange |
| Worker | P2.1 不启动或修改 Tokyo Worker |
| Runtime authority | 完全不变 |

## 失败与恢复

- Support 抽离导致测试行为变化：回退该独立提交，不能修改生产逻辑迁就测试；
- Template Clone 发现隔离不完整：保留原独立 Alembic 路径并修复 Harness；
- 删除后发现唯一合同缺失：恢复测试或以更直接的当前合同测试替代；
- Final Release Suite 失败：修复后候选 Commit 变化，只对新的冻结候选重新运行一次；
- P2.1 不涉及 Schema 或生产 Cutover，因此采用普通 Git fix-forward。

## 验收条件

1. 当前合同和故障类拥有明确的测试层级和主要所有者；
2. `tests/trading_kernel/**` 中跨 `test_*.py` Helper 导入归零；
3. 当前 Head PostgreSQL 测试使用一个统一的隔离 Harness；
4. `_run_alembic`、database URL 和 create/drop 逻辑集中到明确 Support，Migration 特例
   保持可识别；
5. 重复或退休测试的删除清单逐项记录替代所有者；
6. Focused、Fast、R1/R2/R3/R4、Periodic Audit 组合有 tracked 定义；
7. 当前完整 Kernel Release Certification 在最终冻结候选上通过一次；
8. Architecture、Ruff、Mypy 和 `git diff --check` 通过；
9. 无生产代码行为、Schema、Policy、Registry、Worker 或 Exchange 写入变化；
10. `AI_AGENT_CONSTRAINTS.md`、Deployment Contract 和路线图在实施完成后反映最终稳定
    测试组合，不记录瞬时测试数量或耗时。

## Owner 复核重点

本设计建议 Owner 采纳以下三个判断：

1. 允许删除或合并没有独立当前合同所有权的测试；
2. 允许当前 Head 测试通过 PostgreSQL Template Clone 保持隔离并减少重复 Alembic；
3. 同意 P2.1 先定义 Release Class 测试组合，但在 P2.2 分类器完成前不削弱当前完整
   Kernel Certification。
