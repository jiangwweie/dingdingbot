# 手机Web与人工续管：代码审查交接

日期：**2026-11-17，Asia/Shanghai**。状态：**本批本地实现收尾，等待Owner代码审查；不是完成的上线候选**。

> **Gemini复审更新：** [已确认缺陷的本地修复及新验证](2026-11-17-gemini-review-fixes.md)已补齐，首轮测试数量和待办保留为历史记录。完整产品、整包认证与部署仍未完成。

> **追加审查更新：** [升级路由、可信提前恢复与条件价故障隔离已完成本地修复](2026-11-17-followup-review-fixes.md)，前轮数字保留为当批证据；整包认证与部署仍未执行。

## 1. 当前授权与停止位置

1. Owner要求手机Web、后台人工操作后自动续管、Feed事故修复和首尔资源配置**最终一起上线**。修复模块可单独审查，不能提前单独部署。
2. Owner最新要求**完成手头任务，在集成认证前停下等待代码审查**。本批只做静态、单元/架构和受影响数据库边界的针对性回归，不启动完整Integration/Full-chain与R4/API/Static发布认证。
3. 当前没有生产上传、部署、重启、迁移、资源应用、Owner策略变更、交易所测试单或实盘写入。历史现场快照不作为本次生产健康声明。
4. 基线与范围以[统一实施计划](2026-11-16-seoul-recovery-and-cooperation-implementation-plan.md)为准。策略A、Regime、加仓、风险上限扩张、放宽止损不包含在本批。

## 2. 本批代码边界

| 模块 | 已实现的本地代码 | 尚未完成的产品能力 |
|---|---|---|
| **Feed事故修复** | 已有提交`4724fc51`；零仓只读收尾、regular/conditional清理、有界诊断与顺序消费 | 生产恢复及安装前内部多票终态路径 |
| **可信手机设备** | 一次性独立绑定、单设备epoch、持久会话、P256请求签名、nonce、撤销、签名请求体/动作/目标关联 | 真机绑定/恢复、角色权限与完整恢复场景的最终验收 |
| **手机主控** | 真实全局与策略启停API及手机确认交互；仍调用既有恢复门禁 | 可信Resume贯通promoter、Static/Dynamic各权限分支的完整验收 |
| **人工减仓事实** | 预览、版本/幂等、操作及追加历史；真实减量独立事件；原TP数量退出退休、保留价格条件 | 完整操作runner、正式Command准备、交易所实际成交/保护采集、发送前复核与恢复 |
| **减仓后续管** | 接入现有maintenance；原失效/时间退出优先；原目标合约价满足后申请BE；无第二次减仓和假TP成交 | 配合完整减仓执行链的端到端验收；Stop交错协议证据 |
| **手机持仓与委托** | 真实只读数据；委托区分空/缺失/过时；未接通动作capability保持关闭 | 减仓、收紧、手动TP设置/修改/取消、全平的真实表单和动作API/执行/结果查询 |
| **联合静态产物** | 手机壳纳入原桌面产物的`mobile/`；允许清单、缓存版本、同源Nginx入口、离线不重发 | 最终联合安装编排、真实浏览器/手机交互、通知与离线/网络未知结果验收 |
| **Schema与资源** | `0024_owner_cooperation`前向迁移及保全边界；首尔资源独立profile已有实现 | 完整角色权限、所有Source→0024升级路径及三票恢复；正式安装和资源实测 |

**不得把上述已实现模块当作完整手机交易产品。** `OWNER_REDUCE`当前保留显式deferred门，Lifecycle尚无完整operation runner；手机持仓交易按钮capability全部关闭。页面里没有可用的减仓、改保护、手动止盈或全平写入口。

## 3. 建议审查顺序及源码入口

### 3.1 授权与迁移

- [设备域合同](../../../src/trading_kernel/domain/owner_device_authority.py)、[签名协议](../../../src/trading_kernel/infrastructure/owner_device_credentials.py)。
- [设备仓储](../../../src/trading_kernel/infrastructure/pg_owner_device_repository.py)、[签名来源校验](../../../src/trading_kernel/infrastructure/owner_device_authorization_evidence.py)、[操作仓储](../../../src/trading_kernel/infrastructure/pg_owner_position_operations.py)。
- [0024迁移](../../../migrations/trading_kernel/versions/0024_owner_cooperation.py)、[新增表定义](../../../src/trading_kernel/infrastructure/owner_cooperation_schema.py)、[API数据库权限](../../../deploy/owner-console/postgresql/owner-console-control-role.sql)。

重点：凭证只存摘要；同签名重放只能返回同一请求；用途/目标/请求体必须一致；撤销阻止新动作并保留历史授权证据。完整最小权限、签名证据不可变约束和发送前撤销检查仍须结合未完runner审查，不能凭当前针对性测试视为最终安全验收。

### 3.2 数量、保护与生命周期

- [减仓决策](../../../src/trading_kernel/domain/owner_reduction.py)、[减仓证明](../../../src/trading_kernel/domain/owner_reduction_proof.py)、[实际减量记录](../../../src/trading_kernel/application/record_owner_reduction.py)。
- [Reducer](../../../src/trading_kernel/domain/reducer.py)、[UoW](../../../src/trading_kernel/infrastructure/pg_unit_of_work.py)、[维护分支](../../../src/trading_kernel/application/maintain_ticket_lifecycle.py)。
- [行情适配](../../../src/trading_kernel/infrastructure/venue_adapter.py)、[Lifecycle worker](../../../src/trading_kernel/interfaces/lifecycle_worker.py)、[派发关闭门](../../../src/trading_kernel/application/dispatch_exchange_command.py)。

重点：实际减量不计TP成交；保本只针对余仓，不追回已实现亏损；条件价使用合约成交价而不是标记价；新鲜度30秒且晚于已核实减仓时间，不回填断线期间历史触价；旧失败/时间退出保留；MANUAL永久性不变。当前填充proof还需要由完整采集链绑定实际trade ledger和受保护余仓，测试输入不等于现场证明。

### 3.3 手机与产物

- [手机API](../../../src/trading_kernel/interfaces/owner_console_http/routes/mobile.py)、[客户端](../../../frontend/owner-mobile/app.js)、[Service worker](../../../frontend/owner-mobile/sw.js)。
- [静态打包](../../../scripts/owner_console/build_mobile.py)、[联合静态构建](../../../scripts/owner_console/deploy_release.py)、[Nginx入口](../../../deploy/owner-console/nginx/owner-console.locations.conf)。

重点：页面关闭后操作必须仍可查询，当前operation执行/结果展示未完；API不缓存、不离线队列；请求超时不盲发新意图；网络错误不能显示“暂无委托”；IndexedDB保留签名私钥、绑定中断可核对pending公钥。

## 4. 实际验证与证据范围

| 检查 | 本批最后结果 | 证据与限制 |
|---|---|---|
| **单元与架构** | **2312通过** | `.local/cooperative-feasibility-20261116/review-unit-architecture-final.log`；非发布认证 |
| **受影响PG边界** | **19通过** | `review-pg-final.log`；设备、授权、API读取、操作仓储、减量记录/价格条件、前向保全；不是完整Integration suite |
| **既有Lifecycle针对性回归** | **28通过** | `continuation-green.log`；含新减量条件与原TP/Runner维护路径，计数与其他集合重叠 |
| **Ruff / Mypy** | **通过；276源文件** | 未运行发布certifier；静态检查不证明交易所协议 |
| **JS语法 / 手机壳打包** | **通过** | `node --check`两文件；构建写入本地`.local`；尚无真实手机交互验收 |
| **整包Integration / Full-chain / R4 / API / Static认证** | **本批未启动** | Owner代码审查门前停止，旧候选的认证不得复用为联合成品认证 |

红绿过程中修复过：新事件未进入因果阶段映射、proof变量类型冲突、缺少签名目标绑定、委托缺失被显示为空、原目标价不应使用标记价、静态清单缺少手机壳、知识目录/迁移链未同步。测试数量不相加作为完整产品结论。

## 5. 审查后仍需完成的实施工作

1. **操作runner与实际协议闭合**：同票串行、原TP精确取消/成交重核、实际减量采集、保护确认、未知/部分/Stop竞态、设备撤销后发送前阻断；全部通过既有耐久Command链。
2. **其他手机交易操作**：收紧止损、单一普通限价人工计划替换/取消、全平及残单清理；对应操作预览、受理、持久结果和通知。
3. **真实手机前端**：操作表单、确认后的执行进度/部分/拒绝/未知结果，手机安装与重连流程。当前原型通过不等于真实产品完成。
4. **发布恢复路径**：当前正式工具单票恢复能力不能直接处理此前快照中的三张非终态票及错误namespace待执行命令；必须补齐正式停止/flat/只读证明与终态路径，不手改预算、水位、Ticket或Command payload。行动时重新读取生产事实。
5. **最终最小权限、迁移/历史保全与联合安装编排**：三项精确认证、手机静态与后台能力匹配、同一成品可回溯；旧静态独立脚本还保留历史schema硬编码，不能直接当本次联合发布工具。
6. **Owner审查后才恢复整包认证工作**；最终是否部署仍单独等Owner确认。本批未建立任何“认证已通过”或“可部署”的结论。

## 6. 审查快照

- 分支：`codex/manual-management-recovery-v2`。
- 已提交事故模块：`4724fc51`。
- 人工续管与手机代码属于本批本地待审查修改，完整程度以本文表格和源码为准。
- 新增/修改的代码、测试、迁移及设计文件保留在当前工作区；`.local`证据不纳入生产代码与运行权威。

本交接只陈述本地实现与验证，未改变生产系统。
