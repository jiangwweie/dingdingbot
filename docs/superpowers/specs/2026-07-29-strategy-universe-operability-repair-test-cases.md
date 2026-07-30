---
title: StrategyUniverse Operability Structural Repair Test Cases
status: OWNER_APPROVED_FOR_IMPLEMENTATION
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-29
revision: 2
design: 2026-07-29-strategy-universe-operability-repair-design.md
deployment_plan: ../plans/2026-07-29-strategy-universe-stop-rebuild-deployment-plan.md
---

# StrategyUniverse Operability Structural Repair Test Cases

## 测试目标

本测试规格要求 **时间、状态机、调度、schema、批次配置和 Entry 部署门问题在
本地暴露**。东京服务器只执行最终外部事实核对，不承担发现确定性代码错误的
职责。

测试必须共同证明：

1. 系统完成时间与市场闭合时间不再混用；
2. Warming 可以受控 abandoned，且不会永久占用全局槽位；
3. 活跃 Ticket 不会永久饿死 certification；
4. 六个 Event 不完整时不可能启用 Entry；
5. Probe manifest 不能被操作者缩小；
6. 空数据库可以从一个新 baseline 完整重建；
7. 错误或过时测试、migration 和兼容路径已删除；
8. 本地生产形状演练覆盖实际 Worker cadence、错峰和故障恢复；
9. certification 和 warming 对交易所 mutation 次数始终为零；
10. 完整 pytest、Ruff、全仓 Mypy、architecture 和文件 I/O audit 通过。

## 测试原则

### 删除错误测试，而不是迁就

下列测试语义必须删除或重写：

- 给所有 Warming Scope 写入同一 warm_ready_at_ms；
- 断言 Worker 执行时间必须相同；
- 直接批量更新 Runtime Scope 来证明完整 producer 链；
- 只验证 0001 -> 0002 -> 0003 历史升级；
- 通过手工 instrument 参数缩小部署 Probe；
- 把 require-flat pass 当作 Entry ready；
- 只有 NO_WORK 才允许 certification；
- 为已删除字段、状态、migration 或 CLI 参数保留兼容断言。

测试不能成为历史错误语义的保护层。

### 生产形状优先

- PostgreSQL 行为使用 disposable PostgreSQL，不用 SQLite。
- Worker 测试使用显式虚拟时间推进，不使用真实 sleep。
- 同一 closed bar 的不同 Scope 使用不同 attempted/completed time。
- Full-chain 从正式 install、Observation、certification 和 activation 入口进入。
- Recording Venue 区分 readonly call 和 mutation call。
- 服务与部署脚本使用 recording system backend，不直接操作本机 systemd。
- Fault injection 在事务提交点、网络边界和进程恢复点执行。
- 测试结果不得依赖文件报告或服务器状态。

### RED 要求

每个新行为必须先观察到目标 RED：

- RED 必须由缺失或错误的生产行为导致；
- import 错误、fixture 错误、数据库未启动不算有效 RED；
- 删除旧测试不算 RED；
- RED 证据记录测试名、失败断言和对应缺陷；
- 完成前不得把测试改成只断言实现细节。

## 测试层级

| 层级 | 证明内容 | 允许替身 | 禁止替代 |
| --- | --- | --- | --- |
| Unit | 时间模型、状态转移、工作选择、manifest 纯验证 | frozen fixtures | PostgreSQL 原子性 |
| PostgreSQL Integration | schema、约束、selector、锁、CAS、重建 | recording Venue | SQLite |
| Worker Integration | cadence、错峰、租约、重启、公平性 | virtual clock | 同一 NOW_MS 批量写 |
| Full Chain | 空库到六 Active Universe 和 Entry promotion | fake exchange/systemd | 直写 Signal/Ticket |
| Architecture | 删除旧字段、migration、参数、fallback | AST/source/schema scan | 人工代码审查替代 |
| Tokyo Readonly | 外部 flatness、Cross、5x、服务状态 | 无 | 用服务器补本地测试缺口 |

## 计划测试文件

| 文件 | 操作 | 覆盖 |
| --- | --- | --- |
| unit/test_warm_readiness.py | 新增 | 双时间语义与 digest |
| unit/test_strategy_universe.py | 重写相关部分 | abandoned 状态机 |
| unit/test_reconciliation_work_selection.py | 新增 | 安全优先和 certification 公平性 |
| unit/test_bootstrap_strategy_universes.py | 新增 | 六 Event manifest 纯验证 |
| unit/test_promote_entry.py | 新增 | Entry promotion 决策 |
| integration/test_strategy_universe_schema.py | 重写 | 单 baseline 与新约束 |
| integration/test_universe_warming.py | 重写 | 真实错峰 Worker |
| integration/test_strategy_universe_activation.py | 重写 | closed bar 一致性 |
| integration/test_strategy_universe_abandon.py | 新增 | 精确退出和槽位释放 |
| integration/test_universe_certification_worker.py | 重写 | 活跃 Ticket 公平性 |
| integration/test_strategy_universe_batch_bootstrap.py | 新增 | 六 Event 顺序幂等安装 |
| integration/test_entry_promotion_gate.py | 新增 | 六 Event 完整门 |
| integration/test_clean_baseline_rebuild.py | 新增 | 空库生产形状重建 |
| full_chain/test_strategy_universe_local_release_rehearsal.py | 新增 | 完整本地发布演练 |
| architecture/test_strategy_universe_operability_architecture.py | 新增 | 删除旧语义和兼容路径 |
| unit/test_deploy_tokyo_release.py | 重写相关部分 | DB-derived Probe manifest |

## A. 旧语义删除

| ID | 检查 | 必须断言 | 禁止残留 |
| --- | --- | --- | --- |
| DEL-001 | source scan | warm_ready_at_ms 不存在 | alias、property、双写 |
| DEL-002 | schema scan | 旧列不存在 | nullable legacy column |
| DEL-003 | migration directory | 只存在 0001_trading_kernel_baseline_v2 | 0001/0002/0003 历史链 |
| DEL-004 | test scan | 无全 Scope 相同 NOW_MS 的激活假设 | synchronized fixture |
| DEL-005 | deployment parser | 无 exchange-instrument-id 参数 | 手工缩小 Probe |
| DEL-006 | reconciliation worker | 无 result == NO_WORK 后才认证 | 隐藏 starvation |
| DEL-007 | certification assertions | flatness 与 entry readiness 分离 | require-flat 暗含 Entry |
| DEL-008 | compatibility scan | 无 legacy decoder/fallback/dual read | 历史包袱 |
| DEL-009 | test suite | 不再测试旧 migration upgrade | 为删除的路径维护 fixture |
| DEL-010 | repository source | 状态机不散落多个隐式 update | god repository |

## B. WarmReadiness 时间语义

| ID | 场景 | 必须断言 | 禁止结果 |
| --- | --- | --- | --- |
| TIME-001 | closed bar 相同、completed time 不同 | digest 中 market identity 一致 | completed time 进入 market key |
| TIME-002 | completed time 早于 closed bar | validation error | 接受不可能时序 |
| TIME-003 | valid until 不晚于 completed | validation error | 零长度 readiness |
| TIME-004 | Facts observed time 与 closed bar 不同 | not ready | 使用 request time 覆盖 |
| TIME-005 | direct Event 七 Scope 错峰 5 秒 | 最终共享一个 closed bar | 要求 completed time 相等 |
| TIME-006 | MPG 七 Scope 错峰 5 秒 | 最终激活 | 永久 warming |
| TIME-007 | MI 七 Scope 错峰且 projection ready | 最终激活 | len(completed_times)==1 |
| TIME-008 | projection closed bar 不同 | 不激活 | 混合 comparative 周期 |
| TIME-009 | bootstrap 跨过新 bar | 旧 Scope 被重新预热到新 bar | 混合两个周期激活 |
| TIME-010 | readiness 过期 | 清除或替换旧 readiness | 沿用 stale digest |
| TIME-011 | Warming detector 触发 Signal 条件 | 只持久化 readiness | Signal 写入 |
| TIME-012 | Active 后下一次 observation | 正常 Signal 语义 | 回放 warming trigger |

### 真实错峰基准场景

Worker Integration 必须至少使用：

~~~text
scope 1 completed = T + 0s
scope 2 completed = T + 5s
scope 3 completed = T + 10s
scope 4 completed = T + 15s
scope 5 completed = T + 20s
scope 6 completed = T + 25s
scope 7 completed = T + 30s
closed bar          = T - fixed market offset
~~~

不得把七个 completed time 归一为同一个值。

## C. Universe 状态机与 Abandon

| ID | 场景 | 必须断言 | 禁止结果 |
| --- | --- | --- | --- |
| LIFE-001 | warming -> active | activated time 存在 | abandoned time 存在 |
| LIFE-002 | active -> retired | retired time >= activated | current 仍指向 retired |
| LIFE-003 | warming -> abandoned | abandoned time/reason 完整 | activated time 存在 |
| LIFE-004 | abandoned -> active | 数据库和领域均拒绝 | 复活旧版本 |
| LIFE-005 | retired -> active | 拒绝 | 复活旧版本 |
| LIFE-006 | abandon exact warming | Scope 两权限 false | Signal/Entry 仍可用 |
| LIFE-007 | abandon 清除租约 | lease owner/expiry 均 null | 永久 claim |
| LIFE-008 | abandon 非 current Monitor | current resolved | 删除历史 event |
| LIFE-009 | abandon 后安装新集合 | 新 version 可 warming | 全局槽位仍占用 |
| LIFE-010 | abandon 后重装同一集合 | 创建新 version identity | 复用 abandoned row |
| LIFE-011 | 对 active 调用 abandon | 稳定拒绝码 | retire 或关闭 current |
| LIFE-012 | 并发 activate 与 abandon | 仅一个状态转移提交 | 半 active/abandoned |

## D. Certification 公平调度

| ID | 场景 | 必须断言 | 禁止结果 |
| --- | --- | --- | --- |
| FAIR-001 | 存在 unknown command 和 certification | unknown 优先 | certification 抢占 |
| FAIR-002 | 存在保护缺口和 certification | 保护优先 | 延迟安全写 |
| FAIR-003 | routine Ticket 每 2 秒到期、Worker 每 5 秒 | certification 60 秒内被 claim | 永久 starvation |
| FAIR-004 | certification 未超过 max wait | routine 可先执行 | 认证每轮抢占 |
| FAIR-005 | certification 超过 max wait | certification 优先于 routine | 继续普通对账 |
| FAIR-006 | Worker 重启 | max wait 从 PostgreSQL 恢复 | 进程内计数归零 |
| FAIR-007 | certification claim 后崩溃 | lease 到期重试 | 永久 claimed |
| FAIR-008 | Venue timeout | bounded next check | tight loop |
| FAIR-009 | 每 cadence | 网络 work <= 1 | 一轮多次 Venue 请求 |
| FAIR-010 | network instrumentation | claim 事务已提交 | 锁内 I/O |
| FAIR-011 | 长期活跃 Ticket + 7 targets | 所有 target 最终 eligible | 只完成第一个 |
| FAIR-012 | critical work 持续存在 | certification 可继续延迟并暴露指标 | 为公平性牺牲安全 |

FAIR-012 明确允许真正的连续安全事故阻塞认证；测试必须区分 critical safety
work 与 routine reconciliation。

## E. Batch Bootstrap

| ID | 场景 | 必须断言 | 禁止结果 |
| --- | --- | --- | --- |
| BATCH-001 | 六 Event × 七成员完整 manifest | 预验证成功 | 第一个写入前遗漏未知 |
| BATCH-002 | 缺一个 Event | 整批拒绝 | 部分安装 |
| BATCH-003 | 多一个未知 Event | 拒绝 | 扩大 Owner scope |
| BATCH-004 | 一个 Event 含 AVAX | 拒绝本次批准 manifest | 静默接入 |
| BATCH-005 | 含美股或第二 Venue | 拒绝 | 创建 pending instrument |
| BATCH-006 | Event 成员重复 | 整批拒绝 | 自动去重后继续 |
| BATCH-007 | CPM already-active | 幂等继续 MPG | 新 CPM version |
| BATCH-008 | MPG already-warming | 等待/推进该版本 | 安装第二 warming |
| BATCH-009 | 当前 warming abandoned | 创建新 version 后继续 | 复活旧 row |
| BATCH-010 | 批次进程第三 Event 后崩溃 | 重跑从 current 状态收敛 | 本地文件 checkpoint |
| BATCH-011 | deterministic blocker | 停止并输出 exact blocker | 自动跳过 Event |
| BATCH-012 | transient failure | bounded retry | abandon 或 owner action 误报 |
| BATCH-013 | 成功结束 | 六 current Active、42 Active Scope | Warming 残留 |
| BATCH-014 | 输出检查 | terminal text，无敏感值 | JSON/Markdown 文件 |

## F. Entry Promotion 与部署门

| ID | 场景 | 必须断言 | 禁止结果 |
| --- | --- | --- | --- |
| GATE-001 | 仅 CPM Active | entry_promotion_pass=false | flat pass 代替完整性 |
| GATE-002 | CPM Active + MPG Warming | false | 认为 warm-ready 等于 active |
| GATE-003 | 五 Event Active | false + missing exact Event | 启 Entry |
| GATE-004 | 六 Event Active、一个 certification stale | false | 使用旧认证 |
| GATE-005 | 六 Event Active、Scope count 41 | false | 忽略成员缺失 |
| GATE-006 | 六 Event Active、存在 Warming | false | 双版本更新中启 Entry |
| GATE-007 | Policy allowed Events 与 current 不同 | false | 扩大或缩小范围 |
| GATE-008 | operator 试图提供较小 Probe list | parser 不存在该能力 | 缩小检查 |
| GATE-009 | DB-derived manifest | exact 7 instruments | 重复为 42 |
| GATE-010 | active Ticket instrument 已移出 Universe | manifest 仍包含它 | 无法保护旧 Ticket |
| GATE-011 | Entry service 已 active | promotion 拒绝 | 重复启动 |
| GATE-012 | Fence 缺失 | promotion 拒绝并恢复 Fence | 带写能力认证 |
| GATE-013 | Policy 或 capability 已 true 但 identity 不匹配 | promotion 拒绝 | 兼容未知 armed 状态 |
| GATE-014 | 所有条件满足 | Policy 与 capability 原子 true，Entry 带 Fence 启动，Fence 最后移除 | 先移除 Fence |
| GATE-015 | system start 失败 | Fence 始终存在、Entry inactive | 无 Fence 的半启用 |
| GATE-016 | authority 已 armed、service fenced | 重认证后可恢复启动 | 创建回退 Policy |
| GATE-017 | 同一 release 已完整 promoted | 返回 already-promoted exact state | 要求制造新 commit |

## G. 干净数据库基线

| ID | 场景 | 必须断言 | 禁止结果 |
| --- | --- | --- | --- |
| BASE-001 | migration inventory | 只有 baseline v2 | 历史 revision 文件 |
| BASE-002 | 空 PostgreSQL upgrade head | 全 schema 创建成功 | 依赖旧 migration |
| BASE-003 | alembic revision | exact baseline v2 | 0001/0002/0003 |
| BASE-004 | table allowlist | 与 SQLAlchemy metadata 相同 | legacy table/view |
| BASE-005 | WarmReadiness columns | closed/completed/digest/valid 完整 | warm_ready_at_ms |
| BASE-006 | lifecycle constraints | 四状态和时间组合正确 | 无效组合 |
| BASE-007 | global warming unique | 第二 Warming 被数据库拒绝 | 仅应用层保证 |
| BASE-008 | clean seed | Registry/Policy/Capability 一致 | Universe member seed |
| BASE-009 | 非空旧 0003 DB 尝试使用新 release | fail closed | 当成 baseline v2 |
| BASE-010 | downgrade disposable baseline | 清理完整或明确不支持 | 部分表残留 |
| BASE-011 | 第二次空库重建 | 相同 seed/schema identity | 非确定性 |
| BASE-012 | schema source scan | 无 nullable compatibility | dual semantics |

## H. 本地生产形状演练

| ID | 场景 | 必须经过 | 最终断言 |
| --- | --- | --- | --- |
| REH-001 | happy path | empty DB -> baseline -> seed -> batch -> workers -> promote | 六 Active、Entry promoted |
| REH-002 | MPG 错峰 | actual Observation worker loop | 不在东京复现才发现 |
| REH-003 | Worker 中途重启 | lease expiry + resume | 最终状态相同 |
| REH-004 | 第三个 Event market timeout | retry 后继续 | 无手工 DB 修复 |
| REH-005 | 一个 Event deterministic blocker | batch 停止、Entry fenced | 其余状态可解释 |
| REH-006 | exact abandon 后重跑 | 新 version 激活 | 全局槽位释放 |
| REH-007 | manifest 少一个 instrument | 本地 gate fail | 服务器才发现 |
| REH-008 | schema identity 不一致 | Worker fenced | exchange mutation |
| REH-009 | fake exchange 报 position | rebuild/promotion fail | 删除内部所有权后启 Entry |
| REH-010 | fake exchange 报 open order | fail | 自动取消 |
| REH-011 | repeated full rehearsal | 结果可重复 | 残留文件/随机 identity |
| REH-012 | recording fake audit | readonly calls 有界，mutations=0 | certification/warming 写交易所 |

## I. 性能与资源结构

| ID | 负载 | 必须断言 | 上界 |
| --- | --- | --- | ---: |
| PERF-001 | 6 Event × 10 Active | indexed due selector | 60 Scope |
| PERF-002 | 加 1 个 10-member Warming | indexed selector | 70 Scope |
| PERF-003 | Observation cadence | claim 一 Scope | 1 |
| PERF-004 | Reconciliation cadence | network work | 1 |
| PERF-005 | activation | members/scopes scan | 各 10 |
| PERF-006 | comparative 10 members | market reads | 10 |
| PERF-007 | healthy cadence | JSON/Markdown writes | 0 |
| PERF-008 | Monitor repeated blocker | append event 增长有界 | 只记录变化 |
| PERF-009 | six seven-member bootstrap | virtual elapsed time | 分钟级，不永久等待 |
| PERF-010 | full local rehearsal | process/task count | 不增加第五 Worker |

PERF-009 不使用真实 wall-clock 基准作为唯一判断；主要断言每 Scope/target 的
处理次数、due time 推进和最终收敛。

## J. 架构反回归

| ID | 检查 | 必须断言 | 禁止模式 |
| --- | --- | --- | --- |
| ARC-001 | domain imports | 纯 Python/Pydantic/Decimal | SQLAlchemy/Venue/filesystem |
| ARC-002 | application imports | use case 不依赖 systemd/SSH | 部署泄漏进领域 |
| ARC-003 | repository review | persistence 按职责拆分 | generic Manager/Facade |
| ARC-004 | Worker source | 只编排 selectors 和 I/O | 复制状态机 |
| ARC-005 | services | 四个持久 Worker | Universe 第五 Worker |
| ARC-006 | exchange mutations | command kinds 无新增 | certification 设置 leverage |
| ARC-007 | runtime files | 零文件权威 | batch checkpoint file |
| ARC-008 | Registry | 无成员列表 | candidate compatibility |
| ARC-009 | Policy | 只保存 allowed Event ids | 具体成员重复权威 |
| ARC-010 | deployment | Probe manifest 来自 PostgreSQL | operator subset |
| ARC-011 | asset scope | 仅 Binance USD-M USDT perpetual | 美股、spot、第二 Venue |
| ARC-012 | static typing | 全仓 Mypy 零错误 | 只检查 production package |
| ARC-013 | tests | 不含 retired semantics | 为旧 fixture 加 ignore |
| ARC-014 | docs | repair docs 不冒充 runtime authority | Markdown runtime input |

## K. 东京只读验收

东京部署前后仅执行以下现场事实检查：

| ID | 事实 | 通过条件 |
| --- | --- | --- |
| TOK-001 | exchange position | 0 |
| TOK-002 | exchange open order | 0 |
| TOK-003 | account mode | independent_sides |
| TOK-004 | margin mode | cross |
| TOK-005 | leverage | 七 instrument 均 5 |
| TOK-006 | runtime identity | exact target Commit + baseline v2 |
| TOK-007 | service state before promotion | Safety active，Entry fenced |
| TOK-008 | Universe | 六 Active、42 Active Scope、0 Warming |
| TOK-009 | certification | 七 instrument eligible/fresh |
| TOK-010 | runtime residue | Ticket/Position/Command/Incident 均 0 |
| TOK-011 | service restarts | 不增长 |
| TOK-012 | after promotion | Entry active，Fence absent，identity 未漂移 |

东京不执行：

- 手工更新 WarmReadiness；
- 手工改 Universe lifecycle；
- 手工插 current pointer；
- 用服务器循环等待发现逻辑是否能收敛；
- 真实下单作为程序正确性测试。

## RED/GREEN 顺序

1. DEL-* 静态删除门；
2. TIME-* 双时间语义；
3. LIFE-* 状态机和 abandon；
4. FAIR-* 公平调度；
5. BASE-* 新数据库基线；
6. BATCH-* 六 Event bootstrap；
7. GATE-* Entry promotion；
8. REH-* 本地生产形状演练；
9. PERF-*、ARC-*；
10. TOK-* 只读现场核对。

### Cutover 发布顺序回归

| ID | 场景 | 必须断言 | 禁止结果 |
| --- | --- | --- | --- |
| TOK-CUT-001 | target release 初始不存在 | `STAGE_EXACT_RELEASE` 在其 readonly preflight 前完成并写 exact identity marker | 预检先访问不存在的 release |
| TOK-CUT-002 | 旧 `0003` schema 仍在 | preflight 使用 committed seven-instrument cutover manifest | 使用新 DB-derived Universe query 预检旧 schema |
| TOK-CUT-003 | operator 试图指定单个 instrument | parser 拒绝，不存在可缩小范围参数 | 以不完整交易范围获得 flat pass |
| TOK-CUT-004 | release id 与 SHA 前 12 位不符 | stage 拒绝 | 任意目录接收 Git archive |

## 本地验证命令

~~~bash
python3 -m pytest -q \
  tests/trading_kernel/unit \
  tests/trading_kernel/integration \
  tests/trading_kernel/full_chain \
  tests/trading_kernel/architecture

python3 -m ruff check \
  src/trading_kernel \
  tests/trading_kernel \
  scripts/trading_kernel

python3 -m mypy

python3 scripts/audit_production_runtime_file_io.py

git diff --check
~~~

完整 Mypy 必须使用 mypy.ini 的全仓 files 配置，不得只运行
**mypy src/trading_kernel** 代替。

## 通过定义

本测试规格只有在以下条件全部为真时通过：

1. 所有新增行为均有有效 RED 记录；
2. 所有适用用例均自动化且未使用 Tokyo；
3. 旧语义测试和 migration 测试已经删除或重写；
4. 关键 full-chain 不直接写 readiness、current pointer、Signal、Ticket 或
   Exchange Command；
5. 完整 pytest 零失败、零未解释 skip；
6. Ruff、全仓 Mypy、architecture、文件 I/O、git diff 检查全部通过；
7. 本地空库生产形状演练至少连续运行两次并得到相同最终状态；
8. recording exchange 在 certification/warming 阶段 mutation count 为 0；
9. 六 Event 不完整的所有组合均无法通过 Entry promotion；
10. Tokyo 只承担最终只读核对。
