---
title: StrategyUniverse Operability Structural Repair Design
status: OWNER_APPROVED_FOR_IMPLEMENTATION
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-29
revision: 1
related_design: 2026-07-28-crypto-strategy-universe-design.md
test_spec: 2026-07-29-strategy-universe-operability-repair-test-cases.md
deployment_plan: ../plans/2026-07-29-strategy-universe-stop-rebuild-deployment-plan.md
---

# StrategyUniverse Operability Structural Repair Design

## 决策

本修复保留 **静态 Strategy Registry + PostgreSQL StrategyUniverse + 单一
Trading Kernel** 的总体方向，但删除或重写已经证明语义错误、容易误导或只为
历史兼容存在的实现。

最终采用以下结构：

1. **保留全系统一个 Warming Universe**，继续限制小型东京主机的瞬时负载。
2. 用两个字段分别表达 **系统完成时间** 和 **市场闭合时间**。
3. 为 Warming 增加 **abandoned** 终态和精确受控退出。
4. Reconciliation 采用安全优先且有最大等待时间的公平工作选择，不再只有
   NO_WORK 时才允许 certification。
5. 六个 Event 使用一个完整批次配置入口顺序安装；批次本身可重入、幂等且不
   成为运行时权威。
6. Entry 启用前精确证明 Owner Policy 的六个 Event 全部具有 Active current
   Universe。
7. 当前生产无 Ticket、仓位、命令和 Incident，因此部署采用 **停止并重建
   BRC 专用数据库**，不保留现有 Warming 数据。
8. 删除三段历史 migration，重写为一个新的干净数据库基线
   **0001_trading_kernel_baseline_v2**；不提供从旧 0003 原地升级的兼容路径。

本文档只定义修复语义。实现完成前，当前代码、当前 PostgreSQL 和交易所只读
事实继续优先。

## Owner 确认的工程原则

### 结构性删除优先

**语义错误或过时的代码、测试、迁移、fixture、字段和部署分支能删尽删，能按
当前语义重写就重写。**

禁止为以下目的增加技术债：

- 让表达错误语义的旧测试继续通过；
- 保留含糊字段名或旧状态值；
- 支持不会再次执行的旧数据库升级路径；
- 兼容当前已经准备删除的 Tokyo BRC 数据；
- 同时维护新旧 Warming 判定；
- 为一次性重建保留双写、fallback、nullable legacy 字段或转换 Adapter。

Git 历史保留来源证明；运行代码和测试只保留当前语义。

### 故障优先暴露在本地

**确定性程序问题必须尽可能在本地自动化验证中暴露，而不是依赖东京服务器发现。**

本地测试必须覆盖：

- 真实 Worker 错峰时间；
- 租约、重启、退避和 cadence；
- disposable PostgreSQL 约束、锁和事务；
- 从空数据库创建 schema、seed、配置、预热、激活和 Entry promotion；
- recording Venue 对只读和写入调用的精确计数；
- 迁移或服务中断后的 fail-closed 行为；
- 部署 manifest 缺失、重复、漂移和手工缩小。

东京只做当前外部事实核对、资源观察和最终发布，不作为基础程序逻辑的主要测试
环境。

## 已知客观事实

| 事实 | 当前状态 | 来源 |
| --- | --- | --- |
| 部署 Commit | c3b933ef841abf17a3c94add1159475eba5cb19f | Tokyo release marker |
| 部署 Schema | 0003_cross_margin_stop_stress | PostgreSQL/runtime identity |
| 交易账本 | Ticket、Position、Command、Incident 均为 0 | Tokyo readonly certification |
| Entry | inactive、disabled、write-fenced | systemd 和 fence |
| CPM-LONG | Active，7 members | PostgreSQL |
| MPG-LONG | Warming，7 members 全部 warm-ready | PostgreSQL |
| 其余 Event | 尚无 Universe | PostgreSQL |
| MPG 系统完成时间 | 7 个不同值，相差约 56.7 秒 | PostgreSQL |
| MPG 市场闭合时间 | 所有 Facts 和 comparative projection 均为 1785330000000 | PostgreSQL |
| 当前认证结果 | require-flat 返回 pass，但只存在 1 个 current Universe | certify_readonly.py |

## 问题分类

| 类别 | 根因 | 结果 |
| --- | --- | --- |
| 时间语义 | warm_ready_at_ms 同时承担系统时间和市场时间 | MPG/MI 激活条件不可达 |
| 状态机 | warming 只能 active，不能合法失败退出 | 一个坏 Universe 阻塞所有后续安装 |
| 调度 | certification 只在 reconciliation NO_WORK 时运行 | 活跃 Ticket 可永久饿死认证 |
| 部署权威 | Probe instruments 由操作者手工提供 | 可以缩小验证范围 |
| 完整性门 | certification pass 不要求六 Event 全 Active | 不完整系统可能启 Entry |
| 发布工具 | 同一 release 无独立 Entry promotion | 被迫手工拆 Fence 或重新部署 |
| 测试模型 | fixture 给全部 Scope 同一 NOW_MS | 真实错峰故障未在本地暴露 |
| Schema 历史 | 0001、0002、0003 为已经完成且准备重建的演进路径 | 继续维护只增加测试和迁移负担 |

## 方案比较

| 方案 | 代码处理 | 数据处理 | 复杂度 | 风险 | 结论 |
| --- | --- | --- | --- | --- | --- |
| 服务器手工 SQL 修补 | 保留当前错误语义 | 修改现有 MPG 行 | 低表面成本 | 无本地证明、未来复发 | 拒绝 |
| 增加 0004 兼容 migration | 新旧字段并存或原地转换 | 保留现有 Universe | 中 | 继续维护旧升级路径 | 不采用 |
| 结构性重写 + 停机重建 | 删除错误字段、测试和 migrations | 删除 BRC DB 后空库重建 | 一次性改动较大 | 边界最清晰、最易本地证明 | 采用 |
| 每 Event 并行 Warming | 扩大 selector 和查询上界 | 可并行 bootstrap | 高 | 对个人小服务器收益有限 | 暂不采用 |

## 权威与边界

### 唯一执行链

~~~text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
~~~

Universe 配置、certification、warming、abandon 和 activation 均不得创建
Ticket、Exchange Command 或交易所写入。

### 数据权威

| 决策 | 唯一权威 |
| --- | --- |
| Strategy/Event/side/Facts/exit 语义 | Strategy Registry |
| Owner 允许的 Event、资本和 Entry authority | Owner Policy |
| Universe 版本、成员、状态、current pointer | PostgreSQL |
| Warming 完成与市场闭合身份 | PostgreSQL Runtime Scope |
| 产品规则、Cross、5x、independent sides | PostgreSQL current certification + exchange readonly facts |
| Ticket、命令、仓位、Settlement、Review | PostgreSQL Trading Kernel |
| 发布目标 Commit 和 Schema | committed release + runtime identity |

配置 CLI 输入不是持久权威；成功提交后 PostgreSQL 是唯一成员事实。

## WarmReadiness 重写

### 新模型

~~~python
class WarmReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_scope_id: str
    universe_version_id: str
    warm_closed_bar_time_ms: int
    warm_completed_at_ms: int
    warm_readiness_digest: str
    warm_valid_until_ms: int
~~~

旧字段 **warm_ready_at_ms** 删除，不保留 alias、兼容 property 或双写。

### 字段语义

| 字段 | 语义 | 禁止用途 |
| --- | --- | --- |
| warm_closed_bar_time_ms | 本次 readiness 对应的闭合市场周期 | 不表达 Worker 执行时间 |
| warm_completed_at_ms | readiness 成功写入 PostgreSQL 的系统时间 | 不用于 comparative projection key |
| warm_valid_until_ms | readiness 的系统有效期 | 不替代市场 freshness |
| warm_readiness_digest | Facts、Universe、closed bar 的确定性摘要 | 不包含写入时间 |

### Ready 条件

一个 Scope 只有同时满足以下条件才能持久化 WarmReadiness：

1. exact Warming Universe 和 member identity 匹配；
2. 所需 market window 完整；
3. 最新 bar 已闭合；
4. Facts typed 构造成功；
5. Facts 的 observed time 等于 warm_closed_bar_time_ms；
6. comparative Event 的 projection key、member digest 和 closed bar 完全一致；
7. warm_completed_at_ms 小于 warm_valid_until_ms；
8. Warming 路径 SignalRepository 写入次数为零。

### 激活一致性

一个 Universe 激活时：

- 所有成员 certification 必须 eligible 且未过期；
- 所有 Scope 必须具有未过期 WarmReadiness；
- 所有 Scope 的 warm_closed_bar_time_ms 必须相同；
- MPG/MI projection 的 closed_bar_time_ms 必须与该值相同；
- direct Event 不创建 comparative projection；
- 激活事务只访问 PostgreSQL。

如果安装期间跨过市场周期，较早 Scope 会在下一 cadence 更新到共同的新闭合
周期；系统不得混合两个市场周期激活。

## Universe 生命周期重写

### Version 状态

~~~text
warming -> active -> retired
    |
    +------> abandoned
~~~

| 状态 | activated_at_ms | retired_at_ms | abandoned_at_ms |
| --- | --- | --- | --- |
| warming | null | null | null |
| active | non-null | null | null |
| retired | non-null | non-null | null |
| abandoned | null | null | non-null |

### Scope 权限

| Version/Scope 状态 | observation_enabled | entry_enabled |
| --- | ---: | ---: |
| warming | true | false |
| active | true | true |
| retired | false | false |
| abandoned | false | false |

### 受控退出

新增应用用例：

~~~text
abandon_strategy_universe(
    exact universe_version_id,
    expected lifecycle_state=warming,
    stable reason_code,
    attempted_at_ms
)
~~~

单事务完成：

1. 锁定 exact Warming version；
2. 确认它不是 current Active；
3. 将 version 置为 abandoned；
4. 将其 Scope 权限全部关闭；
5. 清除 observation/certification lease；
6. 关闭该版本 Monitor current；
7. 记录稳定 reason code；
8. 释放全局 Warming 唯一槽位。

Abandon 不删除成员、certification、Facts 或审计行。

### 不自动超时 abandon

市场数据缺口、限流和交易所暂时不可用可以恢复，因此时间到期只使 readiness
失效并重新预热，不自动 abandon。Abandon 只允许：

- 稳定的不可恢复身份或配置冲突；
- Owner/运维对 exact Universe 的明确操作；
- 部署批次在确定性失败后的受控清理。

## Warming 并发决策

本次继续保留：

~~~text
全系统最多一个 Warming Universe
~~~

原因：

- 东京主机资源有限；
- 六 Event × 七成员顺序 bootstrap 的正常时间为分钟级；
- 当前长期阻塞来自时间 bug 和缺少失败退出，不来自正常串行成本；
- 保留一个 Warming 可维持最多 60 Active + 10 Warming = 70 Scope；
- 不需要调整到 120 Scope、扩大 query limit 或增加并发激活故障面。

未来只有在真实运行数据证明顺序更新无法满足业务时，才单独设计每 Event 并行
Warming；不得在本修复中提前实现。

## Reconciliation 公平调度

### 当前错误结构

~~~text
run normal reconciliation
-> only when result == NO_WORK
-> certification
~~~

这使 routine reconciliation 可以无限期阻塞 certification。

### 新选择模型

每个 cadence 最多推进一个网络工作，优先级为：

1. unknown command、保护缺口、外部事实冲突等 critical safety work；
2. 已超过 certification_max_wait_ms 的 certification；
3. 普通到期 Ticket reconciliation；
4. 尚未超过最大等待时间的 certification；
5. NO_WORK。

Repository 提供三个有界 selector，不由 Worker 扫描历史：

- claim_next_critical_reconciliation_work；
- claim_next_due_certification；
- claim_next_routine_reconciliation_work。

certification_max_wait_ms 使用固定运行合同值，初始为 **60000 ms**。时间与租约
写入 PostgreSQL，不能依赖进程内 tick 计数。

网络 I/O 始终在 claim 事务提交后执行。

## 批次配置与启动

新增一个只用于运维编排的批次入口：

~~~text
bootstrap_strategy_universes
-> validate the complete six-Event manifest
-> install one Event idempotently
-> wait boundedly for active or deterministic blocker
-> continue with the next Event
-> emit terminal text only
~~~

批次必须在写入第一个 Event 前验证：

- 六个 exact event_spec_id 全部存在且与 Registry 匹配；
- 每个 Event 成员为 1..10 个不同 canonical USDT perpetual；
- 本次首批六个 Event 均使用 BTC、ETH、SOL、BNB、XRP、DOGE、ADA；
- 不含 AVAX；
- 没有美股或第二 Venue；
- Owner Policy allowed Event 集合与批次完全一致。

批次进程崩溃后重跑时：

- already-active 返回成功；
- already-warming 继续等待；
- abandoned 创建新版本；
- 不重复成员、不修改已 Active 版本；
- 不从本地文件恢复隐藏状态。

## Entry Promotion

新增独立、可对当前同一 release 执行的 promote-entry：

1. Entry service inactive、disabled 且 write-fenced；
2. new_entry_submit_enabled 当前为 false；
3. exchange_commands capability 当前为 false；
4. runtime commit/schema/seed 与当前 release 完全一致；
5. Owner Policy 的六个 Event 全部存在 exact Active current Universe；
6. 共有 42 个 Active Scope、0 个 Warming Scope；
7. certification 均 eligible 且新鲜；
8. PostgreSQL 零 Ticket、Position、unresolved Command、Incident；
9. 交易所零仓位、零开放订单；
10. 七个去重 instrument 均为 trading、Cross、5x、independent sides；
11. Safety Workers active 且 restart count 不增长。

通过后按顺序执行：

~~~text
atomically create the new Owner Policy version and enable exchange_commands
-> enable and start Entry while the write fence is still present
-> verify exact service/runtime identity and active state
-> remove the write fence as the final mutation
-> verify Entry remains active
~~~

任一步失败都保持或恢复 Fence，并保持 Safety Workers。若数据库 authority 已经
原子切换但 Entry 启动失败，重跑必须识别 exact
authority-armed/service-fenced 状态，重新认证后继续；不得创建兼容 Policy 或
回写旧版本。

## 部署 Manifest 权威

交易所 Probe instruments 必须由 PostgreSQL 派生：

~~~text
members of active Universes
UNION members of the one Warming Universe
UNION instruments of active Tickets
~~~

操作者不得通过较小的命令行列表缩小 Probe 范围。命令行 instrument 参数删除。

最终 Entry manifest 必须精确等于：

~~~text
Owner Policy allowed Event ids
<-> six Active current Universes
<-> six sets of seven approved members
~~~

只读 certification 的 pass 状态拆分为：

- database_integrity_pass；
- flatness_pass；
- universe_bootstrap_pass；
- entry_promotion_pass。

数据库完整性或全平通过不再暗示 Entry 可启用。

## PostgreSQL 基线重写

### 删除

实现时删除：

- migrations/trading_kernel/versions/0001_initial.py；
- migrations/trading_kernel/versions/0002_crypto_strategy_universe.py；
- migrations/trading_kernel/versions/0003_cross_margin_stop_stress.py；
- 所有只验证 0001 -> 0002 -> 0003 历史升级路径的测试；
- warm_ready_at_ms 字段和所有兼容引用；
- 只在 NO_WORK 后认证的 Worker 分支；
- deployment 手工 exchange-instrument-id 参数；
- 把 require-flat pass 当作 Entry pass 的断言。

### 新基线

创建一个文件：

~~~text
migrations/trading_kernel/versions/0001_trading_kernel_baseline_v2.py
revision = 0001_trading_kernel_baseline_v2
down_revision = None
~~~

它直接包含最终：

- Trading Kernel 全部 current/event tables；
- StrategyUniverse versions/members/current；
- certification 和 comparative projection；
- 新 WarmReadiness 字段；
- abandoned 生命周期约束；
- cross-margin stop stress 字段；
- 所有当前唯一约束、FK 和 bounded selector indexes。

不提供旧数据库原地升级能力。任何现有 0001/0002/0003 数据库都必须 fail
closed，并要求按部署方案删除后重建。

## 代码结构

| 模块 | 处理 |
| --- | --- |
| domain/strategy_universe.py | 重写 WarmReadiness 和完整生命周期纯函数 |
| application/observe_strategy_scope.py | 明确生成 closed-bar time 与 completed time |
| application/advance_strategy_universe.py | 只编排 DB-only activate |
| application/abandon_strategy_universe.py | 新增精确受控退出 |
| application/select_reconciliation_work.py | 新增安全优先和公平选择 |
| infrastructure/pg_universe_repository.py | 拆分 version/current、readiness、certification persistence |
| interfaces/reconciliation_worker.py | 删除 NO_WORK-only certification 分支 |
| scripts/trading_kernel/bootstrap_strategy_universes.py | 新增六 Event 幂等批次入口 |
| scripts/trading_kernel/promote_entry.py | 新增独立 Entry promotion |
| scripts/trading_kernel/certify_readonly.py | 拆分 integrity/flat/bootstrap/promotion gates |
| scripts/trading_kernel/deploy_tokyo_release.py | 删除手工 instrument probe 参数 |

pg_universe_repository.py 当前职责过大。实现中按稳定职责拆分，但禁止创建
generic Manager、Facade 或一表一 Repository 的机械包装。

## 事务与故障边界

| 操作 | 原子提交 | 网络 I/O |
| --- | --- | --- |
| Universe install | version + members + warming scopes | 无 |
| Warm readiness | exact scope Facts + readiness projection | market read 在事务外 |
| Certification | certification + instrument rules + Monitor | exchange readonly 在事务外 |
| Activation | old/new scopes + pointer + version states | 无 |
| Abandon | version + scopes + leases + Monitor resolution | 无 |
| Entry promotion | Policy version 后再处理 service fence | exchange probe 在 Policy 事务前 |

Worker 崩溃只通过 PostgreSQL lease 恢复，不读取文件缓存。

## 性能边界

| 项目 | 上界 |
| --- | ---: |
| Active Scope | 60 |
| Warming Scope | 10 |
| 总可调度 Scope | 70 |
| 单 Universe member | 10 |
| 单 activation members/scopes scan | 各 10 |
| 单 cadence network work | 1 |
| certification 最大普通等待 | 60 秒 |
| 健康 cadence 文件输出 | 0 |

Comparative Projection 继续保持每 Event、每 closed bar、每成员最多一次行情读取。

## 本地优先验收

实现不以单点 unit test 为完成条件。必须在本地执行一次完整生产形状演练：

~~~text
empty disposable PostgreSQL
-> new baseline
-> Registry/Policy/Capability seed
-> six-Event batch install
-> recording exchange readonly certification
-> staggered Observation worker progression
-> six Active Universes
-> readonly deployment certification
-> promote-entry against fake system backend
~~~

该演练必须证明：

- 不依赖 synchronized NOW_MS；
- 不访问 Tokyo；
- certification/warming 零 exchange mutation；
- 任何缺失 Event、错 closed bar、Worker crash 或 manifest 缩小均在本地失败；
- 从空库重复执行得到同一最终身份；
- 完整 pytest、Ruff、全仓 Mypy、architecture 和 runtime file-I/O audit 通过。

## 明确不做

- 不接入美股运行时；
- 不增加新 Strategy Event；
- 不增加第五个 Worker；
- 不实现每 Event 并行 Warming；
- 不自动设置 leverage、margin mode 或 position mode；
- 不保留现有 Tokyo BRC 业务数据；
- 不提供 0003 -> 新基线的兼容 migration；
- 不保留 warm_ready_at_ms alias；
- 不用 YAML、JSON 或 Markdown 作为运行时 Universe 权威；
- 不实现通用工作流引擎或部署平台。

## 完成标准

程序修复只有在以下条件全部满足时完成：

1. 错峰 Worker 对同一 closed bar 可以激活 MPG/MI；
2. Warming 可以精确 abandoned 并释放全局槽位；
3. 活跃 Ticket 下 certification 在有界时间内完成；
4. 六 Event 不完整时 entry_promotion_pass 必须失败；
5. 手工缩小 Probe instrument 范围已不可能；
6. 同一 release 可以独立 promote Entry；
7. 新数据库只有一个干净 baseline migration；
8. 错误旧字段、旧 migrations、旧测试和兼容路径已删除；
9. 本地空库生产形状演练完整通过；
10. Tokyo 部署前 Entry 保持 fenced。

## Owner 决策状态

当前没有阻塞实现或文档的 Owner 决策。

以下边界已经确定：

- 保留全局一个 Warming；
- 首批七币种为 BTC、ETH、SOL、BNB、XRP、DOGE、ADA；
- 不含 AVAX；
- 不接入美股；
- 允许停止服务并删除、重建 BRC 专用数据库；
- 不修改凭证、不划转或提款、不影响非 BRC 服务；
- 六 Event 全 Active 前不启用 Entry；
- 删除和重写优先于兼容历史语义；
- 确定性故障优先在本地自动化验证中暴露。
