---
title: StrategyUniverse Stop-and-Rebuild Tokyo Deployment Plan
status: OWNER_APPROVED_DESIGN_EXECUTION_BLOCKED_UNTIL_IMPLEMENTED
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-29
revision: 1
design: ../specs/2026-07-29-strategy-universe-operability-repair-design.md
test_spec: ../specs/2026-07-29-strategy-universe-operability-repair-test-cases.md
---

# StrategyUniverse Stop-and-Rebuild Tokyo Deployment Plan

## 决策

本次东京发布采用 **停止四个 BRC Worker、清空 BRC 专用 PostgreSQL public
schema、从新基线重建、顺序安装六个 StrategyUniverse、最后启用 Entry**。

不执行：

- 当前 MPG 数据 backfill；
- 0003 原地升级；
- Active Ticket handover；
- BRC 数据备份或恢复；
- 手工 SQL 修复 Universe；
- 交易所 leverage、margin mode、position mode 修改；
- 凭证修改、资金划转或提款；
- 非 BRC 服务、容器或数据库变更。

执行当前被阻塞，直到修复设计和测试规格全部完成并形成新的 committed release。

## 适用前提

该方案只适用于 action-time 同时满足：

1. PostgreSQL 非终态 Ticket 为 0；
2. PostgreSQL active Position 为 0；
3. unresolved Exchange Command 为 0；
4. open Incident 为 0；
5. 交易所 position domain 为 0；
6. 交易所 open order domain 为 0；
7. Entry inactive、disabled、write-fenced；
8. 没有另一个 BRC writer 或旧服务能够写交易所。

任一条件不满足时停止，不删除数据库。

## 发布范围

### 删除和重建

| 对象 | 操作 | 恢复方式 |
| --- | --- | --- |
| brc_trading_kernel.public schema | DROP CASCADE 后重建 | 从 target release baseline 重建 |
| 当前 BRC runtime/trade/Universe 数据 | 全部删除 | 不恢复 |
| 旧 Alembic 0001/0002/0003 schema identity | 删除 | 新 baseline v2 |
| 旧 BRC current symlink | 切到 target release | fix-forward 重切 |
| 已确认无引用的旧 BRC release 目录 | 发布成功后删除 | Git commit/tag 可重建代码 |

### 必须保留

| 对象 | 处理 | 原因 |
| --- | --- | --- |
| /etc/brc/trading-kernel.env | 保留，不修改凭证 | 账户与数据库连接配置 |
| brc-trading-kernel-pg 容器 | 保留容器，只重建 public schema | 避免凭证和容器网络变化 |
| owner_ai_* 容器和数据 | 完全不触碰 | 非 BRC 范围 |
| Nginx、Docker daemon、主机 PostgreSQL 之外服务 | 完全不触碰 | 非量化服务 |
| Binance 账户、资金和配置 | 只读核对 | 禁止写设置和资金操作 |
| Git 历史和 production tag | 保留 | 代码来源证明，不作为数据库恢复 |

## 发布目标

### Runtime

部署目标仍为四个持久服务：

~~~text
brc-trading-kernel-observation-worker.service
brc-trading-kernel-entry-worker.service
brc-trading-kernel-lifecycle-worker.service
brc-trading-kernel-reconciliation-worker.service
~~~

Entry 最后启动。

### Schema

目标 Alembic revision：

~~~text
0001_trading_kernel_baseline_v2
~~~

新 release 不识别或升级旧 0003 数据库。部署脚本必须在 drop schema 前确认旧
revision 是已知被替换版本，drop 后只接受 baseline v2。

### StrategyUniverse

六个 Event：

| StrategyGroup | Event |
| --- | --- |
| CPM-RO-001 | CPM-LONG |
| MPG-001 | MPG-LONG |
| MI-001 | MI-LONG |
| SOR-001 | SOR-LONG |
| SOR-001 | SOR-SHORT |
| BRF2-001 | BRF2-SHORT |

每个 Event 使用同一首批七成员：

~~~text
binance-usdm:BTCUSDT:perpetual
binance-usdm:ETHUSDT:perpetual
binance-usdm:SOLUSDT:perpetual
binance-usdm:BNBUSDT:perpetual
binance-usdm:XRPUSDT:perpetual
binance-usdm:DOGEUSDT:perpetual
binance-usdm:ADAUSDT:perpetual
~~~

明确不包含 AVAX。

## 本地发布门

服务器操作前，target Commit 必须在本地完成：

1. 完整 pytest；
2. Ruff；
3. 全仓 Mypy；
4. architecture tests；
5. production runtime file-I/O audit；
6. git diff check；
7. 空 disposable PostgreSQL baseline rebuild；
8. 六 Event batch bootstrap；
9. 真实错峰 Observation worker 演练；
10. certification fairness 演练；
11. exact abandon/reinstall 演练；
12. incomplete manifest Entry promotion rejection；
13. happy-path fake Entry promotion；
14. 整个空库发布演练连续执行两次并收敛到相同状态。

只有本地门全部通过才能创建 target production tag。

## 阶段 0：形成不可变目标

1. 目标修复分支完成 review。
2. 工作树 clean。
3. 所有本地门通过。
4. 创建 exact committed release。
5. 创建新的 annotated Tokyo production tag。
6. 记录 target Commit、Schema 和 seed semantic hash。
7. Stage release 到新的、与 Commit 前 12 位绑定的目录。

该阶段不连接交易所写接口，不修改东京 current release。

## 阶段 1：Action-time 只读确认

在停止服务和删除 schema 之前，从当前 release 和交易所读取：

### PostgreSQL

~~~text
nonterminal_ticket_count = 0
active_position_count = 0
unresolved_command_count = 0
open_incident_count = 0
active_budget_reservation_count = 0
active_netting_domain_count = 0
~~~

### Exchange

~~~text
account = exact owner subaccount
venue = binance-usdm
position_mode = independent_sides
position_count = 0
open_order_count = 0
~~~

七个 instrument 同时验证：

~~~text
product_status = trading
margin_mode = cross
configured_leverage = 5
rules = complete and positive
~~~

### Host

~~~text
target release exists and markers match
Entry service inactive and disabled
write fence present
only the four exact BRC worker units are in mutation scope
protected non-BRC containers remain present
~~~

任何事实缺失、超时或矛盾均停止。

## 阶段 2：停止 BRC

顺序：

1. 再次创建 Entry Fence。
2. 将 Owner Policy 的 new_entry_submit_enabled 保持或重建为 false。
3. 停止并 disable Entry。
4. 停止 Observation、Lifecycle、Reconciliation。
5. 确认四个服务均 inactive。
6. 确认没有残留 BRC Python worker 进程。
7. 再次读取交易所零仓位和零订单。

第二次交易所读取通过后，才进入数据库删除阶段。

## 阶段 3：清空并重建 BRC 数据库

只对容器 **brc-trading-kernel-pg** 内的数据库
**brc_trading_kernel** 执行：

~~~sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public AUTHORIZATION brc_kernel;
~~~

随后从 target release 运行：

1. bootstrap schema；
2. 验证 exact baseline v2；
3. 验证 table allowlist；
4. seed Registry；
5. seed Runtime Profile；
6. seed Owner Policy，new_entry_submit_enabled=false；
7. seed Runtime Capability，exchange command capability disabled；
8. 写 target runtime commit/schema/seed identity。

不创建数据库 dump，不恢复旧数据。

## 阶段 4：切换 Release 并启动 Safety Workers

1. 安装 target systemd units。
2. current symlink 切到 target release。
3. systemctl daemon-reload。
4. Entry 继续 disabled。
5. Entry Fence 继续存在。
6. 启动 Observation、Lifecycle、Reconciliation。
7. 验证三个服务 active、restart count 为 0。
8. 验证 Worker runtime commit/schema 与 target 一致。

Lifecycle 在零 Ticket 状态下应正常空闲；保留启动是为了部署后运行模型完整。

## 阶段 5：顺序 Bootstrap 六个 Universe

运行新的 batch bootstrap 入口，一次提交完整六 Event manifest。入口内部保持
全局一个 Warming，并按固定 Event 顺序推进：

~~~text
CPM-LONG
-> MPG-LONG
-> MI-LONG
-> SOR-LONG
-> SOR-SHORT
-> BRF2-SHORT
~~~

每个 Event 的状态推进：

~~~text
install warming
-> readonly certification
-> staggered Observation warming
-> DB-only atomic activation
-> verify exact Active current
-> continue next Event
~~~

批次单 Event 默认等待上限为 5 分钟；超时不会自动 abandon。它停止并输出 exact
当前状态。确定性错误可以通过 exact abandon 操作清理后重跑批次。

正常七成员、5 秒 Observation cadence 下，六 Event 应在约 5–10 分钟完成，
而不是等待数小时。

## 阶段 6：Bootstrap 后只读检查

PostgreSQL 必须精确满足：

~~~text
Universe version count = 6 active versions plus any explicit abandoned history
current Universe count = 6
active Universe count = 6
warming Universe count = 0
active Scope count = 42
entry-enabled Scope count = 42
certification target count = 7
temporarily unavailable certification count = 0
unresolved Monitor blocker count = 0
Ticket/Position/Command/Incident count = 0
Owner Policy new_entry_submit_enabled = false
~~~

交易所 Probe manifest 必须从 PostgreSQL 派生并精确得到七个 instrument。禁止
操作者输入或减少列表。

## 阶段 7：短稳定观察

本次个人小资金部署不要求长时间等待，只进行 **2–5 分钟**短观察：

- Safety Workers 保持 active；
- restart count 不增长；
- 无 runtime fence Incident；
- 无 Monitor blocker；
- 无 JSON/Markdown runtime 文件；
- CPU、memory、tasks 无持续异常；
- 六个 current pointer 不漂移；
- 交易所仍为零仓位、零订单。

该观察用于发现服务器环境差异，不替代本地测试。

## 阶段 8：Entry Promotion

运行独立 promote-entry：

1. 重跑 entry_promotion_pass；
2. 再次核对交易所零仓位和零订单；
3. 在一个 PostgreSQL 事务内创建 Owner Policy 新版本并启用
   exchange_commands capability；
4. 保持 Entry Fence，enable 并启动 Entry；
5. 确认 Entry active 且 runtime identity 一致；
6. 最后移除 Entry Fence；
7. 确认四 Worker runtime identity 一致；
8. 确认没有立即产生 Incident 或未知命令。

不要求等待自然 Signal 才宣布部署完成。真实交易生命周期是部署后的运行验收，
不是发布脚本的一部分。

## 阶段 9：发布后清理

部署稳定后：

1. 删除已确认无引用的旧 BRC release 目录；
2. 删除退役一次性 migration/cutover 测试产生的本地临时资源；
3. 更新 MAIN_CONTROL_ROADMAP 的 current Commit、Tag、Schema、Universe 和服务
   状态；
4. 更新 current architecture/implementation/deployment 文档中的稳定语义；
5. 不复制临时 Ticket 或短期运行事实到稳定文档。

## 失败恢复

### 删除 schema 前失败

处理：

- 保持 Entry fenced；
- 修复 target release 或服务器前置条件；
- 必要时重新启动当前 release 的 Safety Workers；
- 不启 Entry。

### 删除 schema 后、baseline 完成前失败

旧数据不恢复。处理：

~~~text
Entry fenced
-> keep all Workers stopped
-> fix-forward target release
-> repeat DROP/CREATE public schema
-> rerun clean rebuild
~~~

### Baseline 完成后、Universe bootstrap 失败

处理：

- Safety Workers 可继续运行；
- Entry 保持 fenced；
- transient failure 等待 bounded retry；
- deterministic exact Universe 使用 controlled abandon；
- 重跑幂等 batch。

### Entry promotion 失败

处理：

- 恢复 Entry Fence；
- disable/stop Entry；
- 如果数据库 authority 已 armed，保留 exact armed 状态并保持 Fence；
- Safety Workers 保持 active；
- 修复后对同一 release 重跑 promotion，识别并恢复
  authority-armed/service-fenced 状态。

## 明确禁止

- 在服务器手工 UPDATE WarmReadiness；
- 手工 INSERT current pointer；
- 手工把 warming 改成 active；
- 通过删除单行绕过 FK 或唯一约束；
- 用较小 Probe list 获得 pass；
- 为保留旧 0003 数据增加兼容 migration；
- 从旧数据库 dump 恢复 retired semantics；
- 启动 Entry 后再验证六 Event；
- 修改 API key、secret、账户 owner、保证金模式或杠杆；
- 操作非 BRC 容器、数据库、release 或 systemd unit。

## 预计时间

| 阶段 | 预计时间 |
| --- | ---: |
| Action-time readonly | 2–5 分钟 |
| 停止服务和重建 schema | 3–5 分钟 |
| Seed、identity、Safety Workers | 2–5 分钟 |
| 六 Event Universe bootstrap | 5–10 分钟 |
| 短稳定观察 | 2–5 分钟 |
| Entry promotion | 1–2 分钟 |
| 总计 | 约 15–30 分钟 |

时间显著超过 30 分钟时应视为 blocker 或程序/环境故障，而不是继续无限等待。

## 执行完成标准

部署只有在以下条件全部满足时完成：

1. current release 指向 exact target Commit；
2. schema 为 baseline v2；
3. Registry/Policy/Capability seed identity 匹配；
4. 六个 Event 全部 Active；
5. 42 Active Scope、0 Warming；
6. 七个 instrument certification eligible；
7. 交易所 Cross、5x、independent sides；
8. PostgreSQL 和交易所均无发布前残留；
9. 四个 Worker active、restart count 不增长；
10. Entry promotion 通过并移除 Fence；
11. 非 BRC 服务和数据未变化；
12. MAIN_CONTROL_ROADMAP 已按当前事实更新。

## Owner 确认状态

该部署设计所需产品与安全边界已经确认，没有额外阻塞项。

实际执行时只需要刷新 action-time 事实；事实核对不是新的产品决策，也不会扩大
交易范围。
