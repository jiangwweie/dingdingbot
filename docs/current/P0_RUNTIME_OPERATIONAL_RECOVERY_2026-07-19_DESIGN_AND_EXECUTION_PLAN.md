---
title: P0_RUNTIME_OPERATIONAL_RECOVERY_2026-07-19_DESIGN_AND_EXECUTION_PLAN
status: PROPOSED_PENDING_OWNER_CONFIRMATION
authority: docs/current/P0_RUNTIME_OPERATIONAL_RECOVERY_2026-07-19_DESIGN_AND_EXECUTION_PLAN.md
last_verified: 2026-07-19
---

# P0 生产运行链路恢复设计与执行方案

## 1. 决策摘要

### 1.1 建议结论

采用 **前向修复 + 受控恢复**，不回退生产数据库、不伪造信号、票据或订单，也不绕过 **FinalGate**、**Operation Layer**、保护和对账。

本方案的目标不是“强制产生一笔交易”，而是恢复以下可验证能力：

```text
持续观察
-> 自然新鲜信号
-> PG 当前投影
-> Promotion Candidate
-> Action-Time Ticket
-> FinalGate
-> 官方 Operation Layer
-> 保护 / 对账 / 结算
```

自然信号未出现时，系统应准确呈现 `market_wait_validated` 或 `computed_not_satisfied`；它不能用 `waiting_for_market` 掩盖工程故障。

### 1.2 当前是否具备真实交易能力

**结论：当前不具备可持续的真实交易能力，不能作为生产可用状态验收。**

原因不是策略参数或市场没有机会，而是生产的三个定时器都处于 **`enabled` 但 `inactive`** 状态，且没有下一次触发时间；观察、服务端监控和票据生命周期均未自动运行。（来源：东京 `systemctl status` 与 `systemctl list-timers`，2026-07-19 01:28 CST）

### 1.3 修复方向对比

| 方案 | 做法 | 优点 | 不接受的风险 | 结论 |
| --- | --- | --- | --- | --- |
| A. 手工启动定时器 | 立即在东京执行 `systemctl start` | 恢复最快 | 不能修复下次失败后的静默停摆，也没有证明 Action-Time 错误被正确分类 | 仅可作为受控恢复动作的一部分，不单独接受 |
| B. 回退到旧 release | 恢复旧代码和服务 | 操作表面简单 | 会重新引入已确认的 HTTP 400、投影和 typed identity 缺口，且 PG 已迁移至 137 | **拒绝** |
| C. 前向修复并受控恢复 | 修正部署收敛、Action-Time 诊断和当前分支基线，再按正式部署流程恢复 timers | 保留 fail-closed 安全边界，形成可重复验收和回滚路径 | 需要完成集中测试与一次受控部署 | **推荐** |

## 2. 已知客观事实

### 2.1 分支与部署事实

| 对象 | 已确认状态 | 影响 |
| --- | --- | --- |
| 当前合并工作分支 | `codex/budget-model-review-20260714`，HEAD `20016445` | 与东京运行的修复提交并非祖先/后代关系，不能假设修复已自然包含 |
| 东京当前代码 | `1a055bac`，迁移版本 **137** | 已包含 watcher coverage 的 `exchange_instrument_id` 写入修复 |
| P0-FRR 修复线 | `codex/dual-position-account-risk-remediation-v1`，HEAD `1a055bac` | 包含 `92cb6ceb` 至 `1a055bac` 的观察、投影、identity 与修复脚本改动 |
| PG 当前权威 | PostgreSQL current tables | 不能以 JSON、Markdown 或旧 handoff 文件补偿或替代运行时状态 |

（来源：本地 `git worktree list`、`git merge-base`、东京 release 路径与项目 `AGENTS.md`。）

### 2.2 已被修复、但尚未完成当前分支对齐的历史缺陷

1. **观察 API HTTP 400**：此前全部活跃 runtime instance 失败；P0-FRR 分支已通过真实只读观察把运行结果恢复为 HTTP 200，并持久化 detector decisions。
2. **控制状态读取遗漏 `strategy_runtime_instances`**：capability reducer 因此误报 `runtime_instance_missing`；修复提交为 `282a4cef`。
3. **watcher coverage identity 不完整**：coverage 未持久化 `exchange_instrument_id`，Action-Time 的 typed identity 校验按设计拒绝；修复提交为 `1a055bac`。
4. **终态仓位投影脚本的生产兼容性**：已修复直接运行的 `sys.path` 和 `positions.is_closed` 的 `0/1` 数据形态。

（来源：`codex/dual-position-account-risk-remediation-v1` 提交 `92cb6ceb`、`97e601b6`、`f6bb49e4`、`282a4cef`、`1a055bac` 及对应单元测试。）

### 2.3 当前生产阻塞事实

| 优先级 | 现象 | 已确认的直接证据 | 正确分类 |
| --- | --- | --- | --- |
| P0-1 | 三个定时器停止 | `brc-runtime-signal-watcher.timer`、`brc-runtime-monitor.timer`、`brc-ticket-lifecycle-maintenance.timer` 均为 `enabled/inactive`，`Trigger: n/a` | `runtime_data_gap` / 部署运行性缺口 |
| P0-2 | 失败后的停摆未被显式围栏表达 | `/home/ubuntu/brc-deploy/control-plane/production-writers.blocked` 不存在，但 timers 已被停止 | 部署状态机不变量缺口 |
| P0-3 | Action-Time 失败缺乏可操作根因 | watcher 日志只保留 `action_time_ticket_sequence_rolled_back`，服务以非零退出；初始具体 blocker 未作为结构化字段落库/输出 | `engineering_handoff_gap` |
| P1 | 修复后尚无新的自然 fresh signal 完成全链路重验 | 最近 BTC long 信号发生在旧 coverage identity 缺失时，PG outcome 为 `runtime_lane_identity_mismatch:coverage_typed_identity` | 历史 fail-closed 记录，不可删除或伪造 |
| P1 | 一个 runtime 报 `NEXT-ATTEMPT-POSITION-ORDER-CONFLICT` | 2026-07-19 01:17 watcher 输出 | Action-Time 安全阻塞；不应阻断其它 lane 的只读观察 |

（来源：东京 `journalctl`、`systemctl cat/status`、`brc_runtime_process_outcomes`、`brc_live_signal_events`，2026-07-19。）

## 3. 根因分析

### 3.1 触发链

```text
自然 SOR-001 BTC long 信号
-> 创建 Action-Time invocation
-> 旧 coverage 行缺少 exchange_instrument_id
-> typed identity 校验拒绝
-> Action-Time Ticket sequence 回滚
-> watcher 子步骤返回非零
-> 部署恢复阶段检测到 timer-owned watcher service 失败
-> 外层失败收敛停止 watcher / monitor / lifecycle timers
-> 未保留 production-writers.blocked fence
-> 三条自动运行链路全部静止
```

**根因一：部署失败收敛的状态表达不完整。** `execute_tokyo_runtime_governance_git_deploy.py` 的失败收敛会停止 timers 并禁用 lifecycle capability，但未建立与该状态一致的生产 writer fence；这留下“服务已停止、fence 不存在、系统表面仍 enabled”的不一致状态。（来源：`scripts/execute_tokyo_runtime_governance_git_deploy.py:514-546`，东京 unit 状态。）

**根因二：Action-Time 原子序列的可观测性不足。** `materialize_action_time_ticket_sequence` 在 savepoint 回滚后只把概括性 status 交给脚本的普通 stdout，而 systemd 链路没有强制输出其结构化 `blockers`。因此生产日志可知“回滚”，却无法从同一条运行记录得到最先失败的精确条件。（来源：`src/application/action_time/ticket_materialization_sequence.py:112-326`、东京 watcher journal。）

**根因三：旧信号与新 identity 契约的时间错位。** BTC 信号的 invocation 发生在 coverage 写入 `exchange_instrument_id` 之前，因此新契约正确拒绝旧数据。`1a055bac` 修复 writer 后，不能通过修改历史信号来证明成功；必须等待或采集新的自然信号。（来源：`src/application/action_time/promotion_action_time_lane.py:730-801`、东京 `brc_runtime_process_outcomes`。）

### 3.2 排除项

| 假设 | 结论 | 证据 |
| --- | --- | --- |
| 最近没有市场机会 | **排除** | 曾有自然 BTC/ETH/SOL 信号；当前 timers 停止后观察覆盖失效，不能用无新记录推断无机会 |
| 交易所写入或真实订单造成停摆 | **排除** | 相关 watcher / lifecycle 输出均为 `exchange_write_called=false`、`order_created=false` |
| writer fence 导致 timer Condition 失败 | **排除** | fence 文件不存在，且 unit `ConditionResult=yes` |
| 一个 lane 的仓位/订单冲突应停止所有观察 | **排除** | `NEXT-ATTEMPT-*` 在观察层被设计为 action-time-only blocker；观察仍应覆盖其它 lane |

（来源：东京 unit drop-in、watcher journal、`scripts/runtime_active_observation_monitor.py:1331-1341`。）

## 4. 目标架构与不变量

### 4.1 运行状态模型

```text
healthy_running
  = timers active + next trigger known + fresh coverage + PG current projection

safe_contained
  = timers stopped + writer fence present + lifecycle capability disabled
    + Owner/monitor state explicitly reports temporarily_unavailable

invalid_split_state
  = timers stopped + writer fence absent
    + no explicit recovery receipt
```

本次修复后，**`invalid_split_state` 必须不可达**。任何部署失败只能进入 `safe_contained`；任何移除 fence 的动作必须在所有需要恢复的 timer 已恢复、并且其首次运行结果已验证之后完成。

### 4.2 责任边界

| 层级 | 本次应做 | 本次禁止做 |
| --- | --- | --- |
| Watcher | 只读获取事实、写 PG current、生成自然 signal | 伪造信号、直接提交订单 |
| Action-Time | 对自然 signal 生成可审计的 promotion/lane/ticket，保留精确 blocker | 放宽 typed identity、跳过 TTL 或安全事实 |
| Deploy | 在失败时保持明确围栏，在成功时按 prepolicy 恢复 | 以“enabled”替代“active + trigger 可用”验收 |
| Lifecycle | 对已有票据做受限保护/对账维护 | 在无 ticket 或无 capability 时创建新订单 |
| Owner 状态 | 报告运行、等待、暂不可用或需干预 | 将内部 ticket / gate 名称变成日常人工操作 |

## 5. 实施设计

### 5.1 工作包 A：当前合并分支的最小前向对齐

1. 从 `1a055bac` 识别并移植 **P0-FRR 必需变更**，而非盲目合并整条高耦合分支。
2. 每个移植提交都在当前合并分支重放并审查依赖：migration 137、runtime repository、coverage writer、Action-Time identity、capability reducer、终态投影脚本与对应 tests。
3. 若当前合并分支已有等价实现，以行为测试替代重复代码；不得同时保留两套 projector 或 file fallback。

**验收**：当前分支能在隔离 PostgreSQL 下证明 22 条活跃 lane 均拥有 typed coverage identity、detector decision 与 capability certification。

### 5.2 工作包 B：Action-Time 回滚的精确诊断与分类

1. 将 sequence 的 `status`、`first_blocker`、`blockers`、`action_time_invocation_id`、lane identity 写入 PG `runtime_process_outcomes` 的现有结构化列和 systemd 可检索日志。
2. 将“业务性 fail-closed”（例如活跃仓位/订单冲突、TTL 过期、identity mismatch）与“工程失败”（异常、PG 写入失败、超时）分开处理。
3. watcher 对业务性 Action-Time 拒绝应保持观察 timer 存活；仅真实进程健康失败才可进入部署/运行 containment。
4. 将 `action_time_ticket_sequence_rolled_back` 作为内部实现状态，不得作为唯一的对外 blocker。

**验收**：针对每类回滚，单次 journal/PG 查询可获得精确 `first_blocker`；没有以泛化 `rolled_back` 替代根因的状态。

### 5.3 工作包 C：部署状态机的 timer / fence 原子不变量

1. 抽象 `RuntimeWriterState`，统一表示：每个 timer 的 prepolicy、当前 active 状态、writer fence、lifecycle capability 与恢复 receipt。
2. 在任意 deploy/recovery 异常路径中，先建立或保留 fence，再停止生产 writer units；不得先停服务后失去状态标识。
3. 成功恢复时，按既有受控顺序恢复：monitor/lifecycle → watcher；每个 timer 必须同时满足 `active`、`Trigger` 非 `n/a`、第一次 service result 合格。
4. 若 watcher 首次运行因业务 blocker 退出非零，恢复代码不得把它误判为基础设施故障而停止所有 timers；应以结构化分类决定保活或 containment。
5. deploy summary 与 server monitor 都必须把 `invalid_split_state` 报为 `temporarily_unavailable`，而不是 `waiting_for_opportunity`。

**验收**：故障注入测试覆盖 fence 创建失败、timer 启动失败、watcher 业务性 blocker、watcher 工程性异常、恢复中断；每种路径都结束于 `healthy_running` 或 `safe_contained`。

### 5.4 工作包 D：受控生产恢复与自然信号验证

1. 在代码、迁移、focused tests 和 file-I/O audit 通过后，按东京部署合同执行一次 deploy apply。
2. 恢复 timer 前，读取 PG 的活动仓位、开放订单、未决 exchange command、保护状态和 lifecycle capability；任何真实风险未闭合则保持 `safe_contained`。
3. 仅在 `healthy_running` 验收通过后，恢复 watcher。恢复阶段不调用 FinalGate、Operation Layer 或交易所写接口。
4. 等待**新产生的自然信号**。它必须使用修复后的 coverage row；信号到 ticket 的验证不改变策略、scope、profile、leverage、notional 或资金。
5. 只有在 ticket、fresh action-time facts、FinalGate、Operation Layer、保护、重复提交防护和对账均通过时，系统才能按既有 Owner policy 进入真实提交；本工作包不人为触发提交。

## 6. 执行顺序与停机边界

| 阶段 | 输入 | 产出 | 允许的副作用 | 硬停止条件 |
| --- | --- | --- | --- |
| 0. 基线审计 | 当前合并分支、P0-FRR 分支、东京只读状态 | 可移植变更清单与冲突矩阵 | 无 | 基线无法重放或 migration 不兼容 |
| 1. 代码修复 | 阶段 0 清单 | 工作包 A-C 的代码与测试 | 本地文件、测试 PG | 发现需修改策略/风险/凭证 |
| 2. 本地认证 | focused unit + PostgreSQL integration + file-I/O audit | 可部署认证报告 | 临时测试数据库 | typed identity、timer/fence 不变量任一失败 |
| 3. 东京部署 | 经认证的 current branch commit | migration、release、systemd 受控切换 | Tokyo release/systemd/PG 当前投影 | active position/open order/unknown command/protection异常 |
| 4. 恢复验证 | 已部署 release | 3 timers active、触发时间有效、coverage fresh | 只读 watcher/monitor 与 PG 投影 | 任一 timer 无 next trigger 或 runtime health 失败 |
| 5. 自然信号链路验证 | 新鲜自然信号 | signal → candidate → lane → ticket 的真实证据 | 仅官方预交易 PG 行 | 事实过期、identity 不匹配、任何安全 blocker |
| 6. 真实交易能力验收 | 阶段 5 + 实际 policy | `live_submit_ready` 或精确安全 blocker | 正式链路仅在所有 gates 通过时 | 禁止绕过 FinalGate / Operation Layer / protection |

## 7. 测试与生产验收

### 7.1 必须新增或重放的测试

1. `watcher coverage`：缺少或错误 `exchange_instrument_id` 必须阻止 Action-Time；字段存在且匹配时允许继续。
2. `repository projection`：`strategy_runtime_instances` 必须进入 monitor control state；缺失时 capability reducer 明确失败。
3. `Action-Time outcome`：每种 savepoint rollback 都持久化精确 blocker，不只输出 `rolled_back`。
4. `timer/fence state machine`：所有异常路径都不能形成 `enabled + inactive + fence absent`。
5. `watcher continuation`：单 lane 的 `NEXT-ATTEMPT-POSITION-ORDER-CONFLICT` 不会停止其它 lane 的观察。
6. `full-chain fixture`：自然信号的 typed identity 从 coverage → signal → invocation → ticket 保持一致；fixture 不调用交易所写接口。
7. `production file I/O`：`python3 scripts/audit_production_runtime_file_io.py` 的 `performance_risk.status=clear`，无新 JSON/MD 运行时权威或周期性写入。

### 7.2 生产成功标准

| 验收维度 | 成功标准 |
| --- | --- |
| 服务运行 | watcher、monitor、lifecycle 三个 timers 为 `active`，且 `list-timers` 提供下一次触发时间 |
| 观察覆盖 | 全部 active lanes 有新鲜 PG coverage；每行带 canonical `exchange_instrument_id` |
| 检测 | 每个 lane 有已计算 decision 或明确 `computed_not_satisfied`；无 HTTP 400 批量失败 |
| 投影 | capability certification 与 current readmodel 不遗漏 runtime instance |
| Action-Time | 新鲜自然信号能生成精确失败/成功结果；失败时能定位 blocker，成功时生成合法 ticket |
| 安全 | 无 FinalGate bypass、Operation Layer bypass、重复提交、缺少保护、未知交易所结果、转账或提现 |
| 运行性能 | no-signal tick 不生成 JSON/MD 文件；所有网络/API 与 subprocess 调用有 timeout；PG rows 为有界 current/append-only audit 语义 |

## 8. 回滚与恢复

### 8.1 软件回滚

不得回退到会重引入 migration 137 前数据模型或 typed identity 缺口的旧 release。若新 release 不通过认证，保持 **`safe_contained`**：writer fence 存在、timers 停止、lifecycle capability disabled、Owner 状态为 `temporarily_unavailable`。

### 8.2 运行恢复

前向修复成功后，使用部署状态机移除 fence 并恢复 timer，不通过手工修改 PG、删除历史 process outcome 或伪造 coverage/signal/ticket。历史 `runtime_lane_identity_mismatch` 应保留为审计记录，由新的自然信号及成功的 current projection 覆盖当前 readmodel 状态。

## 9. Owner 确认边界

本方案不需要 Owner 改变策略、资金、symbol/side scope、杠杆、名义金额、runtime profile、凭证或真实交易授权。

执行前需要的确认仅限于以下工程边界：

1. **确认以当前合并分支为唯一修复目标**，将 P0-FRR 的必需修复按最小依赖集前向移植，而不整体回退或切回旧 release 分支。
2. **确认允许一次受控东京部署与 timer 恢复**；部署仅会更新 release、systemd、migration/PG 当前投影，不会调用交易所写接口。
3. **确认允许等待自然新鲜信号做链路验证**；不会人为制造 Ticket 或订单，真实提交仍完全受既有 FinalGate、Operation Layer 和 Owner policy 约束。

## 10. 计划完成定义

本计划完成不以“产生盈利交易”为条件，而以以下条件同时成立为准：

1. 当前合并分支已包含并验证 P0-FRR 必需修复；
2. 东京不再存在 `invalid_split_state`；
3. 三条 timer 驱动链路持续正常，且监控能如实报告异常；
4. 新鲜自然 signal 的 pre-trade 链路要么到达合法 ticket，要么留下精确的、安全分类 blocker；
5. 所有真实提交安全边界保持 fail-closed，未发生越权订单、转账、提现、凭证或风险配置变更。
