# BRC-ODR-01：Owner 方向风险偏好 V1 实施计划

日期：**2026-10-25**。状态：**本地实现已形成；发布认证、部署与激活未执行**。

## 目标与依据

将已批准的[设计](../specs/2026-10-25-owner-directional-risk-v1-design.md)
实现为单一 Kernel 内的持久化 Owner 控制和 Crypto 方向风险限制。
精确参数只在[实验风险契约](../../current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md)维护。
现有资金 Policy、策略与退出语义不被替换；运行状态归主控路线图与直接证据。

## 已知状态与最早缺口

现有代码具备方向预算、Owner 控制、全局 ENTRY lane、不可变 Ticket、durable Command
及发送前预检。此次实现已接入 Owner 方向选择的持久权威、出生证据与最终发送授权，
通过共享账户事务锁排序切换与发送。最初缺口是控制／发送协议，当前重点是完整回归
与冻结候选认证；不把既有生产结果当作新功能验证。

## 实施任务

任务由主工程负责人顺序执行；本计划不派发代理，不自动部署。
各任务遵循 test-first RED/GREEN/refactor，不在共享核心文件上并行修改。

| ID | 目标与依赖 | 允许范围 | RED／验证重点 | 完成条件 |
| --- | --- | --- | --- | --- |
| ODR-01 | 固定控制切换／发单协议，无前置 | 精确调用图、设计修订；对应 application/infrastructure 测试 | 切换发生在 claim、预检、发送授权、网络请求前后；旧进程停顿恢复 | PG 锁序、发送权、pending/effective、恢复边界有可执行证据，未发送与未知结果可区分 |
| ODR-02 | 持久权威与迁移，依赖 01 | domain、application ports、pg_models/pg_repositories、migrations/trading_kernel、相应测试 | 初始化 unset、缺失拒绝、CAS、幂等、唯一 pending、历史保全 | 单一 forward head；规则／选择／投影／出生与发送证据字段冻结；无旧表读取 |
| ODR-03 | 方向预算与准入闭合，依赖 02 | capacity_sizing、build_capacity_claim、issue_ticket、admission 边界及 PG 查询、相应测试 | 三档／两向、低余额、取整、最低仓位、存量超限、同账户其他产品占用 | 只收紧；不重复计本 Ticket；基础风险门完整；拒绝不造命令 |
| ODR-04 | 发送协调与恢复，依赖 01—03 | dispatch/revalidate、owner_control、必要 reducer/entry/reconciliation 边界、相应测试 | 两种交错顺序、授权后崩溃、超时未知、lease 到期、重启 | 未发命令正常终结并释放；不盲目重发；旧发送者不能越过已生效新版本 |
| ODR-05 | Owner API 与 V2 控制台，依赖 02—04 | owner_console_http、readonly projections、frontend/owner-console-v2、相应测试 | TOTP、旧页面 CAS、重复提交、超限提示、真实生效状态、提醒去重 | 账户与持仓可操作且可解释；不把 request accepted 标成 effective |
| ODR-06 | 归因最小证据与端到端，依赖 03—05 | 既有 Admission/Command/Shadow 关联及 readonly 查询、integration/full-chain | 出生／发送版本差异、多个 blocker、研究失败隔离、配额缺失、旧历史未知 | 每笔可追溯，不重写原 Decision/Review；无模拟盈利或第二执行链 |
| ODR-07 | 发布认证与运行验收，依赖 01—06 | 正式 release/certification/deploy 路径及 current 文档 | 精确 R4、停止空仓迁移保全、部署恢复、作用域与控制认证 | 同一候选全部硬门通过；软件安装、控制生效、自然生命周期分别报告 |

每项任务均禁止修改无关用户文件、退休执行链、凭据、提款转账、策略算法、退出参数、
杠杆配置、研究配额和其他产品授权。实际编辑前固定该任务的精确文件清单；若需跨界，
先更新设计与范围，不用兼容层绕开缺口。研发分支为 focused codex/*，dev 仅用于集成。

## 必须覆盖的场景

### 产品与预算

1. 所有三档状态与合法 Event side 都取基础风险与 Overlay 更严格者。
2. 中性和 unset 执行无附加限制，但审计身份不同；缺失／不可读不等于二者。
3. 逆向仍有合法机会；MPG 不被特殊暂停；SOR-001 永久禁用；TradFi 不直接套用 Overlay。
4. 初始风险占用覆盖非终结 Ticket，含已发行未发送者；计量在各阶段不重不漏。
5. 已有占用超过新上限时禁止新增、保护不变；浮盈和移动止损不释放新额度。
6. 基础策略族、strategy-side、Netting Domain、总风险、margin、最低仓位继续约束。

### 并发与失败

1. 切换先提交：没有旧版新发送权；待发命令重验或正式收尾。
2. 发送权先提交：准确旧命令可完成；切换保持 pending，不能提前声明生效。
3. 网络调用前暂停进程再恢复、进程死亡、连接丢失、结果未知、超时与 lease 失效。
4. 同幂等键重试、不同请求竞争、陈旧预期版本、重启后的持久恢复。
5. 权威存储失败阻止新增；研究可恢复失败保持既有隔离规则。
6. 拒绝／部分成交／未知结果保留原 Kernel 分类；已成交 Ticket 不误走无暴露释放。
7. 未发送 Ticket 终结释放所有 hold、reservation、lane，不制造另一 ENTRY generation。

### 证据与界面

1. 规则、选择、准入、发送身份串联；历史空值保留未知。
2. 维护暂停不被选择覆盖；UI 预览不是行动时事实。
3. 当前选择与实际持仓方向分开展示；无空头不被标成偏空控制失败。
4. 24 小时仅提醒，不自动改变控制；没有新的聊天或外部消息自动化。
5. 配额、失败、未采集样本明确披露；路径与实际 Net R 不混用。

## 验证层级和证据

- **Focused**：每个行为先 RED，再实现；真实 PG 并发用屏障控制，不用顺序 fixture 代替。
- **Fast**：受影响单元、接口、集成、架构及静态检查；UI 验证实际 V2。
- **Release**：冻结精确候选后按正式 R4 执行，复用该 SHA 证据，不在每次小改后全量重复。
- **Production**：发布时刷新 code/schema、PG、systemd 与 exchange readonly 事实；
  保全验证和真实控制生效单独记证据，不用文档宣称当前空仓或当前授权。

任何失败均保留真实原因；不强造 Signal、不调参、不手工 SQL 修补来制造验收。
旧版本历史和 Review 保留；迁移后失败走 fix-forward，不降 schema 或恢复退休运行层。

## 工程完成与研究复核分别验收

**工程完成**要求设计的行为和失败边界均有证据、运行权限符合正式门槛、
生产验收范围明确；自然 Ticket 的完整闭合必须来自自然机会，不承诺时限。

**经济复核**沿用独立研究工作区，8 周首次检查不等于收益证明。精确观察窗口、
广度口径、停止／修订准则应在分析前冻结；无新研究配额或外部调度的隐式授权。
不是先赚到钱才允许证明软件正确，也不是软件 PASS 就证明 Owner alpha。

## 当前待办与阻塞

- **已闭合**：Owner 对方向偏好、首版预算、保留逆向机会与不改持仓的产品选择。
- **本地能力**：规则／控制／事件／准入证据／发送授权、方向预算、HTTP/TOTP/幂等回执、V2 控制卡片均已实现。
- **协议证据**：真实 PG 验证两种交错顺序；CCXT 签名保持固定时间戳；已确认成交立即保护，未知缺席须有交易所时钟关闭窗口的证据。
- **当前工程验收**：完整回归、候选冻结与精确发布认证按实际结果记录，不能把中间成功计数当最终 PASS。
- **研究未知**：参数优劣与择时增益，允许结果为证据不足或否定假设。
- **生产待验**：行动时事实与正式发布门槛，本次未执行。


## 本地实现落点

| 能力 | 代码／证据 | 状态边界 |
| --- | --- | --- |
| 三档规则和范围 | `domain/directional_risk.py`、不可变 rules/scope 摘要 | 无任意参数编辑器 |
| 控制与审计 | `pg_directional_risk_repository.py`、0013 迁移 | CAS、幂等请求回执、显式 unset |
| 预算与签发 | `build_capacity_claim.py`、`issue_ready_signal.py`、`issue_ticket.py` | 既有硬门保留，出生证据独立关联 |
| 发送与恢复 | `dispatch_exchange_command.py`、`recover_unknown_command.py`、`recover_directional_transition.py` | 固定签名窗口，成交保护与控制完成独立 |
| Owner HTTP | `/controls/directional-risk` 与准确请求回执 GET | 真实 Session/TOTP、受限 PG 角色已定向验证 |
| V2 交互 | `DirectionalRiskCard.tsx` | 当前／切换中、快照口径、超时身份、24h 提醒 |
| 数据与知识 | 全源保全用例、数据库目录和定义锚点 | 代码目标结构与生产盘点分开 |

本地浏览器验收使用合成数据和生产构建样式，覆盖偏空确认、状态回读与 390px 无横向溢出。
截图和 CLI 记录位于忽略的 `output/playwright/owner-directional-risk-v1/`；不作为运行权威提交。
完整测试结果以冻结候选后的实际记录为准，本文不把局部成功合成生产 PASS。
