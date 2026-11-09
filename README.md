# BRC App 人工接管交易系统

## 本分支的产品定位

**首尔人工接管产品**帮助 Owner 发现机会并自动入场；Owner 可以通过**币安 App**接管单笔交易。
**默认全自动，人工干预后整笔永久转人工管理**。未干预时保留初始止损、TP1、Runner 与现有自动退出规则；本产品不承诺盈利，也不把“只负责初始止损”作为最终方案。

本目录为 `/Users/jiangwei/Documents/final-manual`，集成分支 **`manual-dev`**，任务分支为 `codex/manual-*`。
Tokyo 全自动产品位于独立目录与 `dev` 分支，两线使用不同服务器、子账户、凭据、数据库和发布证据，不共享实时账本、不自动整分支合并。
（来源：[Owner 决策](docs/superpowers/specs/2026-11-06-app-manual-takeover-v1-owner-decisions.md)、[工作区规则](docs/superpowers/plans/2026-11-08-two-product-workspaces.md)。）

## 人工干预怎样生效

### 管理权状态

| 状态 | 触发事实 | 系统职责 | Owner 职责 |
| --- | --- | --- | --- |
| **AUTO** | 初始状态，外部变化可解释为系统命令或自然成交 | 正式入场、保护、TP1、Runner、自动退出与对账 | 观察；等待初始止损确认后可在 App 干预 |
| **REVIEW_REQUIRED** | 订单归属、观察覆盖或命令结果无法证明 | 暂停该笔新的自动处置，继续核实；不盲重发 | 关注待核实事实，不把它当已确认接管 |
| **MANUAL** | 交易所确认有效的外部退出操作 | 只读跟踪仓位/订单、风险占用、结算与复盘 | 管理整笔剩余仓位以及原有 TP1、止损和残单 |

- **不必成交才接管**：外部新增退出挂单、改止盈止损、撤单、部分或全部减仓，均按已核实事实识别。
- **接管整笔而非一部分**：只动一档订单也接管整笔；改回原价、重启、升级或原 TP1 成交都不恢复 AUTO。
- **现存订单留在交易所**：程序不再自动移动止损、Runner、平仓或撤残单；Owner 决定保留、修改和撤销。
- **未提交/被拒绝的 App 操作不算有效干预**；系统自己的命令、TP1/止损自然成交不误判为人工动作。
- **新独立 Ticket 默认仍为 AUTO**，但必须满足新机会、现有 rearm、预算和标的占用条件。

（来源：[管理权模型](src/trading_kernel/domain/trade_management.py)、[干预识别](src/trading_kernel/application/observe_trade_management.py)、[生命周期归约](src/trading_kernel/domain/reducer.py)。）

### 范围与风险边界

**首次开仓只能由程序发出**；首版不支持人工加仓、自行重开或反手，程序不补回手动减掉的数量。
同一账户、同一标的不能同时持有多空或两个非终态 Ticket；交易所仍须提供独立多空模式。
人工仓继续占用额度，止损缺失、覆盖不明或事实陈旧会限制新增自动开仓，程序不擅自修正人工仓。
**全平不等于结束**：残单、未知命令和账务尚未核实前不能声称标的或风险占用已经释放。
不新增每日亏损熔断，Owner 自行决定关闭 ENTRY。
（来源：[Owner 运行模型](docs/current/OWNER_RUNTIME_OPERATING_MODEL.md)、[风险与退出](docs/knowledge/RISK_AND_EXIT.md)。）

## 同一条交易主链

```text
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
```

人工接管改变**已有 Ticket 的后续写权限**，不另造交易链。Kernel、PostgreSQL 和交易所事实仍分别拥有执行、内部沿革和外部真相。
Observation、Entry、Lifecycle、Reconciliation 为四个常驻 Worker；Owner API 独立运行。
管理观察和通知隔离循环复用 Reconciliation 进程，不新增第五个交易 Worker。
（来源：[设计](docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md)、[总体设计](docs/knowledge/SYSTEM_OVERVIEW.md)。）

## 通知与验收

**首尔使用独立飞书群和机器人**。通知展示管理权、实际余仓、入场、已核实止损及覆盖、策略语义和北京时间；未知事实明确待核实，不以旧自动订单冒充当前保护。
事务末尾冻结快照并写入 **Transactional Outbox**，隔离投递、有限重试、过时抑制；平台接受不等于已读，未知网络结果可能重复。
（来源：[通知计划](docs/superpowers/plans/2026-11-09-manual-notification-templates-v1.md)。）

**软件实现、发布认证、真实自然接单与初始保护、App 接管、飞书送达是不同证据**。
Owner 已同意在自然交易中验证真实 App 操作；不伪造 Signal/Ticket、不下测试订单、不发飞书测试消息。
已部署版本、当前 ENTRY、方向、余额和剩余验收只记录在[正式路线图](docs/current/MAIN_CONTROL_ROADMAP.md)，本文不复制快照。

## 项目文档入口

| 文档 | 职责 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 本产品工程、隔离与安全规则 |
| [文档索引](docs/README.md) | 现行契约与历史设计导航 |
| [Owner 决策](docs/superpowers/specs/2026-11-06-app-manual-takeover-v1-owner-decisions.md) | 已确认的 App 干预业务边界 |
| [详细设计](docs/superpowers/specs/2026-11-06-app-manual-takeover-v1-detailed-design.md) | 管理权、证据、写权限、风险及收尾设计 |
| [实施计划](docs/superpowers/plans/2026-11-06-app-manual-takeover-v1-implementation-plan.md) | 任务与验证顺序；当时阶段保留为历史 |
| [运行模型](docs/current/OWNER_RUNTIME_OPERATING_MODEL.md) | 控制台政策与 App 单笔接管职责 |
| [知识地图](docs/knowledge/README.md) | 当前代码的中文阅读路径 |
| [正式路线图](docs/current/MAIN_CONTROL_ROADMAP.md) | 本产品生产身份与直接验收事实的唯一文档入口 |

## 本地验证与发布

使用本目录的 `.venv` 和独立 PostgreSQL，禁止借用 Tokyo 开发环境：

```bash
scripts/local/manual_pytest.sh tests/trading_kernel/unit tests/trading_kernel/architecture -q
.venv/bin/ruff check src/trading_kernel tests/trading_kernel scripts/trading_kernel
.venv/bin/python scripts/audit_production_runtime_file_io.py
```

生产执行代码在 `src/trading_kernel/**`，schema 在 `migrations/trading_kernel/**`。
人工产品使用正式 `install_manual_host.py` 安装/升级路径和产品绑定证书；继承的 Tokyo SSH 部署入口拒绝本产品。
文档更新不修改线上代码或交易权限；发布必须重新核验精确候选与行动时硬门槛。
