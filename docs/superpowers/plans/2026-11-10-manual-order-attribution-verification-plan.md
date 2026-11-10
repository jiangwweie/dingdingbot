# MA-R2：实施任务、四层验证与发布验收方案

日期：**2026-11-10，Asia/Shanghai**。状态：**Owner于2026-11-10明确“同意，实施”，已解除此前编码和测试执行等待；R0/R1按本计划及当前硬门禁推进。**

设计唯一入口：[订单归属修复设计](../specs/2026-11-10-manual-order-attribution-repair-design.md)。本文件没有批准执行任何任务。下文命令、时间预算和证据都是待执行要求，不能记为已有PASS。

## 1. 完成定义与顺序

**完成的对象是交易链行为与证据，不是测试条数。**

1. 确认设计和R0恢复例外；冻结任务文件边界、协议来源、三证明模型及数据迁移草案。
2. 保留F01—F08反例RED，完成真实协议合同与最小正确分类。
3. 从当前schema形成独立R0恢复候选，不引入R1新表/运行兼容模式。完成本地BNB收尾演练及精确认证；获明确执行范围后才可在真实暂停/外部平仓条件下恢复旧Ticket。
4. 完成连续覆盖、健康门禁和监控；只从terminal-clean源状态做R1前向迁移与完整发布。
5. 将工程安装、历史BNB收尾、自然AUTO生命周期、自然App接管、手机通知分别验收，不能相互替代。

原生产实时状态以[路线图](../../current/MAIN_CONTROL_ROADMAP.md)和行动时证据为准；本计划不复制持续变化的持仓/Owner控制快照。

## 2. 验证分层

| 层 | 输入与执行路径 | 必须证明 | 不足以证明 |
| --- | --- | --- | --- |
| **L1 真实协议合同** | 脱敏HTTP/WS原文→实际CCXT解码→生产解析/规范模型→准确Command匹配 | 字段类型、默认回显、身份与自然变化的正确处理 | 当前网络健康、实盘自动交易 |
| **L2 完整本地链路** | 独立一次性PG＋正式生产UoW/Worker/Reducer；仅传输使用记录型venue | AUTO/MANUAL/REVIEW、未知/崩溃/重启、释放/Review的真实状态变化 | 实际账户当前授权和已部署性能 |
| **L3 发布前能力门禁** | 精确提交/依赖/config；真实已有订单历史GET-only；管理接收健康/持久化门禁 | 安装身份、读取预算、采集能力和门禁的生产适用性 | 未发生的新自然订单/App行为 |
| **L4 运行与自然验收** | 正式系统处理新自然Signal/Owner实际App操作；PG、交换所及平台证据 | accepted ENTRY＋Initial Stop、后续AUTO路径、真实接管与收尾 | 用fixture制造“自然验收成功” |

## 3. L1真实协议语料与版本约束

### 3.1 必须采集/保存的合同

| 类别 | 必需样本 | 正确断言 |
| --- | --- | --- |
| 普通订单 | MARKET/LIMIT，NEW/PARTIAL/FILLED/CANCELED/EXPIRED/EXPIRED_IN_MATCH/REJECTED | 规范类型、身份和状态；平台自然变化不成为Owner动作 |
| Algo订单 | STOP_MARKET/TP、触发前/中/后、撤销、actualOrderId，合法closePosition | regular/conditional ID不混；子单可准确追踪；缺关键字段明确unknown |
| 订单修改历史 | 单次、多次、改回、同毫秒、跨日、满页 | 修改count/time/string精确解析；首次有效外部动作不被最终条款覆盖 |
| WS普通/条件事件 | 原始E/T及订单时间、重复/乱序、条件NEW/激活/触发/自然取消 | 实际消息级可选字段规则；不猜不存在的schema |
| 命令回执 | ENTRY、stop、TP1、replace、cancel、未知/拒绝 | 已确认规范条款与durable命令绑定；STP/hedge回显不误判 |
| 数据异常 | 空字段、bool数值、浮点、超长ID、错账户/side/namespace | fail-closed并明确原因；不污染同账户其他已证明事实 |

### 3.2 真实与合成样本分别标识

- 每份语料记录来源、采集时间、endpoint/message类别、适用依赖版本、脱敏映射摘要和覆盖局限；不保存密钥、签名、listenKey。
- 昨天BNB真实数据是基准；复原某状态的反事实变体必须标记“derived/synthetic”，不能冒充原始生产消息。
- 必须过 `CCXT.on_json_response` 或实际WS解码链，禁止直接跳到完整 `ManagementScan` 来替代L1/L2。
- Python、CCXT、Pydantic、可选JSON解码器及相关配置进入测试环境清单；测试orjson有/无的输入形状，生产固定其中明确支持的组合。实现不依赖可选包偶然改变类型。
- 官方协议缺口作为具名BLOCKED项，不能靠增加fixture字段变PASS。接口没有文档保证的分页/修改证据不宣称完整。

## 4. L2验收矩阵：RED、GREEN与拒绝条件

下表覆盖必须自动化的关键场景；测试组织应复用当前support并删除退役断言，不能机械复制一批仅镜像实现的测试。

| ID | 场景 / 反例 | 必须达到的GREEN结果 | 关联 |
| --- | --- | --- | --- |
| V01 | CCXT数字字符串：time/updateTime/gtd/amend-count | 精确int，领域校验一致；bool/小数/空值等继续拒绝 | F01 |
| V02 | 真实BNB系统ENTRY回显STP=EXPIRE_MAKER | 仍为自身/自然，不判外部加仓 | F02 |
| V03 | 自身Stop/TP1回显reduceOnly=true、自然到期 | 未发生人工时AUTO；准确持久基线可复核 | F02 |
| V04 | 新建基线前Owner已经修改了同ID价格/数量 | 不能将修改后条款当原基线，不能错误SYSTEM | F02 |
| V05 | 不同namespace同数字orderId、wrong-account/side | 不串单；缺身份明确拒绝 | F01/F02 |
| V06 | 无干预完整ENTRY→Stop→TP1→Runner→退出 | AUTO持续，所有venue写有唯一durable Command | 全链 |
| V07 | 系统换止损、撤旧止损、algo触发子单 | 不误转MANUAL；未知结果准确对账，不盲重发 | F02/F06 |
| V08 | Owner新增未成交退出单/改单/撤单/部分减仓 | 有充分单次证据即整笔MANUAL，不等待成交 | F02/F04 |
| V09 | Owner改价后改回，最终REST条款与原相同 | 首次外部干预保留；有完整流时不误报历史缺口 | F04 |
| V10 | 非相关订单历史缺口＋确切外部全平fills | 可确认该外部动作；当前残单未清不得释放 | F05 |
| V11 | REVIEW＋零仓，但仅快照、无退出归属/结果证明 | 仍受限，不伪造MANUAL或收益，不直接释放 | F05 |
| V12 | REVIEW＋确切外部全平＋无残单＋全部命令已解析 | 正式MANUAL/归零/Settlement/Review，释放一次且幂等 | F05 |
| V13 | MANUAL归零，但一个条件残单或未知Command | MANUAL_FLAT_PENDING_ORDERS或明确阻塞，保留占用 | F05 |
| V14 | 系统TP1部分成交、自然全平、Owner提前退出 | 分别按已批准规则处理；不混淆自然/人工/事故 | F02/F05 |
| V15 | REST超时、坏schema、返回时间未来/过期 | 保存阶段错误，受影响管理权/健康受限；无假完整 | F01/F06 |
| V16 | 准备阶段命令>200、known terms非法、PG读取失败 | 不让有效AUTO写权限在未知事实下继续；明确缺口与可重试性 | F06 |
| V17 | PG写入失败/事件落库失败 | 不推进覆盖水位、不发后续新写；租约失效能阻止继续授权 | F06 |
| V18 | 收到WS事件后、提交前进程崩溃 | 重启不能宣称该区间完整；幂等重放/确切gap | F03 |
| V19 | 真断流→重连；Ticket早于新连接 | 只承认新epoch；旧缺口需证明，不能直接AUTO恢复 | F03/F07 |
| V20 | watch解析错误但socket仍打开 | 不陷入无恢复标记；按错误类别重建/重新就绪，旧缺口保留 | F07 |
| V21 | 同毫秒多事件、重复、乱序、迟到、源时间漂移 | 无丢失/重复接管；基于身份和接收水位归并，不虚构源顺序 | F03/F04 |
| V22 | 队列2048边界、历史200边界、16改单边界、跨日/3天 | 有界分页和持久cursor；不足证据明确BLOCKED，无静默截断 | F03/F06 |
| V23 | 历史有缺口但当前单页完整；反向当前页截断 | 两种完整性分别表达；不得互相冒充 | F05 |
| V24 | 采样中MANUAL/Owner政策/策略/运行身份改变 | 短事务与发送前准确重验，MANUAL无新管理写 | 全链 |
| V25 | 初始部分ENTRY/未知ENTRY/初始保护失败 | 原安全恢复路径不被普通管理门禁误堵；不增加第二ENTRY | 全链 |
| V26 | 稳定无交易/稳定MANUAL持仓 | 有界健康更新，零JSON/Markdown运行输出；无重复事件刷库 | F03/F08 |
| V27 | collector失败而服务active、Incident0 | Owner显示管理受限及具体原因；不能报告同步成功 | F08 |
| V28 | 恢复真实证明到达 / 只是时间流逝 | 前者可按状态机恢复，后者不能自动变绿 | F03/F08 |
| V29 | outbox超时、平台拒绝、重试、乱序通知 | 业务事务与消息事实正确；无额外交易权限变化 | F08 |
| V30 | 同一恢复步骤重跑、每个事务提交点崩溃 | 历史事件追加一致、资金/标的释放一次；原Signal消费不变 | R0 |
| V31 | 终态历史账户做升级 / 真实仓位仍存在 | 前者保留验证后允许；后者拒绝外部已平恢复/迁移路径 | R0/R1 |
| V32 | 管理数据迁移后旧writer启动、candidate/schema/config不匹配 | Runtime Fence阻止写；不读取旧schema或双写 | R1 |

### 4.1 交易与资金不可变断言

每个有状态场景同时检查：Ticket/Signal/Episode唯一性；ENTRY generation最多一次；所有命令durable-before-dispatch；unknown不重发；MANUAL永久；同标的相反方向不重叠；不加仓；释放无重复；真实零仓与残单/Review分别验证。

### 4.2 证明强度断言

- 缺证据不能被变成成功；充分证据不能被不相关缺口无差别清空。
- CURRENT数量可以是0而占用仍保守；必须显示二者原因，不能为了让界面归零而修改账本。
- 管理历史完整与经济完整分开。没有费用换算/资金费证据时，Review指标显示缺失且可追加修订。

## 5. 本地执行与证据产物（确认后）

### 5.1 环境

使用首尔产品工作区自己的 `.venv`、`scripts/local/manual_pytest.sh`、`brc-manual-pg`／127.0.0.1:55434。隔离真实生产DSN/API key；记录型venue捕获全部写意图，默认不允许真实网络。不得使用Tokyo测试模板/凭据/证书。

### 5.2 命令与测试组合

以下为执行计划，**本轮不运行**：

```bash
scripts/local/manual_pytest.sh -q tests/trading_kernel/unit/test_binance_management_observation.py tests/trading_kernel/unit/test_management_collector.py tests/trading_kernel/unit/test_binance_management_stream.py tests/trading_kernel/unit/test_trade_management.py
scripts/local/manual_pytest.sh -q tests/trading_kernel/integration/test_management_worker.py tests/trading_kernel/integration/test_observe_trade_management.py tests/trading_kernel/integration/test_manual_position_reconciliation.py tests/trading_kernel/integration/test_trade_management_write_fence.py tests/trading_kernel/integration/test_manual_risk_projection.py
```

真实协议回放、新恢复入口、连接持久化、迁移及端到端场景的新增测试文件在各任务中固定。开发循环只运行关联测试；冻结一个候选后再执行仓库规定的完整R4、Ruff、Mypy、架构/迁移/Golden/parity和受影响API/static认证。不提前登记测试总数、不拿前一SHA证书替代新候选。

### 5.3 每阶段必须留存

- 精确SHA、schema、依赖/config摘要、测试命令与版本、实际RED原因和GREEN结果。
- 语料来源、脱敏校验和，原始与规范事件映射，分类/状态预期与实际差异。
- PostgreSQL事件/投影/Command/Reservation、记录型venue效果计数；异常与重试后的不变量证明。
- 负载、冷启动/暖机样本数及耗时分布；小样本只报实测最大值，不能称P99。
- 缺证据/BLOCKED/未执行单独列出，不允许通过跳过断言或硬编码complete=true掩盖。

## 6. 任务卡与文件边界

所有任务默认由当前Codex执行，**不自动派发其他agent**。生产操作只在后续明确授权和实际硬门禁通过后执行。每卡均继承“禁止Tokyo mutation、测试单、风险扩张、直接改表绕过、旧schema兼容”的硬停止条件。

| 卡 | 目标 / 依赖 | 允许文件范围 | 必须交付和完成条件 |
| --- | --- | --- | --- |
| MA-00 合同冻结 | 方案确认后第一步 | 本设计/计划、协议fixture目录及support | 协议来源、模型字段、ER/迁移草案、R0能力矩阵确定；未证实接口保持BLOCKED |
| MA-01 协议与系统基线 | MA-00 | `binance_management_observation.py`、`management_intents.py`、`trade_management.py`、准确回执适配/事件模型、相关测试 | F01/F02反例RED→GREEN；真实默认回显不误认Owner，价格/数量篡改仍阻断 |
| MA-02 全阶段失败与单次退出证明 | MA-01 | `management_observation_worker.py`、`observe_trade_management.py`、`reconcile_ticket.py`、`reducer.py`、`events.py`、`ports.py`、相关仓储/测试 | F05/F06、V10—17/24—25通过；足够外部退出证据可安全收尾 |
| MA-03 R0恢复专用发布 | MA-01/02的同schema恢复子集，R0例外明确确认 | `manual_host_bootstrap.py`、`manual_same_schema_upgrade.py`、`install_manual_host.py`、Kernel恢复用例、恢复CLI、发布身份/测试 | 普通路径不放宽；外部平仓白名单、恢复模式、精确身份、全历史保留、GET-only与每步幂等；R4与本地演练完成 |
| MA-04 BNB受控收尾 | MA-03及真实Owner暂停/外部flat等现场门禁 | 正式恢复命令的调用及路线图证据 | 不变原历史；合法追加MANUAL/Flat/Settlement/Review；占用一次释放，订单已终态；不足证据不写 |
| MA-05 持久接收与区间恢复 | MA-00/01，DDL评审完成 | `binance_management_stream.py`、`management_collector.py`、规范模型、`pg_models.py`、management仓储、唯一后继迁移、相关测试 | F03/F04/F07、V18—23通过；无内存/文件authority、无虚假覆盖，终态迁移保留 |
| MA-06 门禁/监控/API | MA-02/05 | Entry/dispatch/Reconciliation现有门禁、monitor/notice、Owner读取与必要UI、相关测试 | V16—17/24—29；服务健康不掩盖管理失败，新准入和普通AUTO写入使用同一当前证明 |
| MA-07 完整候选认证 | R1全量实现、本地R0已演练；真实R0完成是发布前置 | 认证工具、tests、必要文档 | 一次冻结候选完整R4/API/static、空库与终态前向迁移、长时故障/负载、证据清单全通过 |
| MA-08 R1独立升级与验收 | MA-04/07；当前全部硬门禁 | 正式manual安装/promoter、路线图 | stopped/flat/terminal-clean来源、preservation、单写者、新epoch准备、真实参数和只读探针PASS；ENTRY保持Owner暂停 |
| MA-09 自然业务验收 | MA-08及真实Owner Resume/TOTP | 只读观察、既有运行系统、Owner实际App行为 | 分别记录新自然AUTO、App接管/不回AUTO、零仓残单、Settlement/Review/额度释放及通知回执；没有事件就保留未验证 |

**禁止文件**：`dev`上的人工语义、Tokyo配置/凭据/账本、其他用户工作区未提交改动、真实Secrets、任意生成报告作为运行authority。需要扩大卡的文件边界时先修改并复核卡，不隐式跨产品。R0与R1分别冻结提交/依赖/schema/证书，R0不导入R1新表；MA-01/02的AUTO全量能力和MA-05只在R1相应schema下运行。

## 7. 发布准入与阶段验收

### 7.1 工程PASS条件

| 门禁 | PASS证据 | 失败处理 |
| --- | --- | --- |
| 源/目标身份 | product/account/host/PG/schema/精确SHA/配置和依赖一致 | 不安装、不启动写入者 |
| 数据与占用 | 正常R1要求终态清洁；R0仅精确外部flat恢复白名单 | 保持围栏，列准确阻塞，不清表 |
| 历史保留 | 原Ticket、Command、Trade Event、Review、Owner控制摘要不变；允许新增恢复事件逐项审计 | 拒绝继续；不得“修摘要”通过 |
| 单写者 | 旧四Worker/API停止，目标writer身份与schema认证一致 | 禁止切换/放行 |
| 管理能力 | 正确规范协议＋自身基线＋持久接收/水位＋健康租约；不相关缺口隔离 | 新ENTRY不能开启 |
| 实际预算 | 部署参数下既有历史完整采集与准确分类；限速/取消/负载场景达标 | 回到设计优化；不自动扩大超时/TTL |
| 决策预览与应用 | 预览可复核；应用重新读取事实、核对修订和期限 | 预览过期/漂移即拒绝，无第二authority |
| 恢复授权 | 官方promoter与真实Owner Resume/TOTP分别成立 | 已安装仍可保持暂停，不能代Owner恢复 |

### 7.2 自然验收声明

- **工程修复完成**：上述软件、迁移、只读和正式运行门禁通过。
- **BNB收尾完成**：准确旧交易已依法终态，预算/标的释放，Review字段可解释。
- **自然AUTO通过**：新自然入场受保护、无人工时继续自动生命周期；不能用旧BNB替代。
- **实际App接管通过**：Owner真实有效外部操作后整笔MANUAL，后续无自动管理写入、重启不回AUTO，最终合法收尾。
- **通知通过**：事务事实与平台accepted可核对；手机到达/已读需单独直接确认，平台accepted不等于用户已读。

每类状态分别记录。无需为了消除“未验收”标记制造订单或诱导Owner立即操作。

## 8. BNB恢复验收明细

仅使用此前已诊断的准确Ticket定位，实际执行重新查证，不把旧报告作为权限。

1. 原系统ENTRY、Stop、TP1与确切外部全平成交及残单终态全部准确关联；无命令未知、无真实仓位和普通/条件挂单，账户同标的两侧均检查。
2. 原始Ticket参数、原7条事件和原3条Command均保留；变更仅追加必要证据/管理权/归零/结算事件，按实际采集时间记录，保留原交易所动作时间。
3. 归属证明足够时进入MANUAL而非AUTO；当前零仓、保护0、残单0、持久命令已知。
4. Reservation、标的/账户容量释放一次；不会因重跑产生负预算、重复释放或消除其他Ticket占用。
5. Settlement/Review存在且可查询；费用资产BNB和资金费按准确证据核算，缺失明确声明，不能把价格差结果叫净收益。
6. 当前管理阻塞消除的依据是终态证据；全局ENTRY仍保持Owner暂停，R1准备和真实Resume另外验收。
7. 对比恢复前后非目标表/控制，确认零无关改变、零交易所写、零订单伪造。

## 9. 失败演练与恢复承诺

**必须在本地验证**停止后/身份切换后/证据持久化后/管理事件后/释放后/Review后/迁移后各崩溃点。可重复执行必须得到同一终态，未提交事实不能进入authority。

- 外部事实变化、来源不完整或证明过期：立即中止该次应用；保持准确缺口和保守占用。
- R0途中：保留恢复专用模式，不启动一般交易；已提交步骤按精确幂等键恢复。
- R1迁移前：同schema已认证恢复路径必须仍满足无真实仓位等门禁；不把回退当作恢复新ENTRY。
- R1迁移后：只允许forward-fix，禁止旧writer/旧表读取/双写/降级。
- 真正丢失的条件改单历史不能凭新连接或最终相同价格补造。恢复不了AUTO不等于无法证明已知外部退出并依法收尾，但后者也必须独立证明。

## 10. 本轮交付与下一步授权边界

**本轮仅写文档并检查本地引用和差异。没有编写生产修复、执行新测试、恢复BNB、迁移或部署。**

Owner确认前，MA-00及之后任务均不开始。确认时需覆盖设计文档§11，尤其是**R0外部flat/内部非终态的恢复专用正式切换范围**；无此明确范围就只保留方案，不以现有站立授权解释为可绕过当前升级门禁。
