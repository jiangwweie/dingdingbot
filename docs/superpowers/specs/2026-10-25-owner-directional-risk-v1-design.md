# BRC-ODR-01：Owner 方向风险偏好 V1 设计

日期：**2026-10-25**（Asia/Shanghai）。
状态：**产品基线已获 Owner 同意；本地实现已形成；未部署、未激活**。

## 1. 决策与文档边界

**Owner Directional Risk V1** 将 Owner 的偏多／中性／偏空判断转换为 Crypto
新增 ENTRY 的方向风险约束。首版包含方向预算、持久化控制、并发切换、证据与控制台，
不再拆成只有策略开关的 V1 和方向预算 V1.1。

Owner 在本线程明确同意前述方案，并要求形成文档。该同意确认产品与实验基线；
本次交付是设计与实施计划，不把文档完成解释为运行权限已激活。
已有程序授权仍按 AGENTS.md 与行动时硬门执行，不增加额外逐单审批。

正式数值由[实验风险契约](../../current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md)
唯一维护；本文记录决策来源、技术设计与验收要求。当前运行事实仍只归
[主控路线图](../../current/MAIN_CONTROL_ROADMAP.md)及生产直接证据。
本文不是生产配置文件，不新增 docs/current 权威类别。

## 2. 已确认产品基线

1. **方向偏好**：偏多收紧空头、偏空收紧多头、中性无附加方向限制。
   顺向不扩大原硬上限；精确三档矩阵见实验风险契约。
2. **保留策略语义**：CPM、MPG、MI、BRF2、SOR-1H 按各自原始规则产生信号；
   不因偏空单独暂停 MPG，不镜像创建策略没有的方向。
3. **保持基础风险边界**：不修改总风险、单 Ticket 风险、最低有效仓位、
   保证金、杠杆、策略族、并发容量、Selection 或 ExitProfile。
4. **不改变已有仓位**：已有 Ticket 继续保护、退出、对账、结算和复盘。
   切换不自动平仓、不加仓、不修改止损，也不补发被拒绝的旧 Signal。
5. **持续有效**：Owner 修改前保持选择；24 小时提醒复核，不自动回中性。
   判断含义是未来约一天的新开仓风险意愿，不是逐小时操作任务。
6. **同时记录证据**：控制版本与准入、发送结果从首版保存；研究展示可以后置。
7. **首次研究复核窗口为 8 周**：这是运行与覆盖复核时间，不是收益显著性门槛，
   不设置强制研究等待期来阻塞已有授权范围内的工程验收。

以上来自本线程 Owner 对建议的明确同意。技术细化若改变这些语义，须重新复核。

## 3. 已知代码事实与研究依据

### 3.1 代码事实

| 边界 | 当前事实 | 对设计的约束 |
| --- | --- | --- |
| CPM | 标的较高周期趋势、回撤和恢复条件 | 方向 Overlay 不替代检测器 |
| MPG / MI | 均要求比较池第一；各有绝对动量条件 | 没有依据仅凭名称优先关闭 MPG |
| BRF2 | 标的反弹失败，并有自身强上涨禁用条件 | 不是整个 Crypto 市场的自动 Regime 检测器 |
| SOR-1H | 独立的小时多空开盘区间事件 | 按精确 Event 和 side 应用规则，不使用 SOR 前缀授权 |
| Capacity | 剩余方向预算会约束单笔预算；仍检查最低有效仓位 | 不设置倍数也可能改变仓位或拒绝机会 |
| 风险占用 | 同账户、venue、side 的非终结 Ticket 初始 risk_at_stop 求和 | 不把浮盈或移动止损当作新额度 |
| 发单 | 预检与 venue.execute 分开，网络在事务外 | 单次重新读取不能证明切换无竞态 |
| 研究 | Signal-owned 路径有配额与版本边界 | 不宣称完整机会总体或真实反事实利润 |

代码来源：
[CPM](../../../src/trading_kernel/domain/detectors/cpm.py)、
[MPG](../../../src/trading_kernel/domain/detectors/mpg.py)、
[MI](../../../src/trading_kernel/domain/detectors/mi.py)、
[BRF2](../../../src/trading_kernel/domain/detectors/brf2.py)、
[SOR-1H](../../../src/trading_kernel/domain/detectors/sor_1h.py)、
[Capacity](../../../src/trading_kernel/domain/capacity_sizing.py)、
[PG 风险汇总](../../../src/trading_kernel/infrastructure/pg_repositories.py)、
[发单](../../../src/trading_kernel/application/dispatch_exchange_command.py)。
这是本地代码核查，不是生产状态认证。

### 3.2 研究事实与适用边界

| 机构论文来源 | 支持的研究方向 | 不支持的直接推论 |
| --- | --- | --- |
| Liu / Tsyvinski，[Risks and Returns of Cryptocurrency](https://www.nber.org/papers/w24877) | 样本内加密资产存在时间序列动量证据 | BRC 小时级策略必然有效 |
| Liu / Tsyvinski / Wu，[Common Risk Factors in Cryptocurrency](https://www.nber.org/papers/w25882) | 市场、规模、动量共同因子的研究动机 | 不同币种或策略名称意味着独立风险 |
| Moreira / Muir，[Volatility Managed Portfolios](https://www.nber.org/papers/w22208) | 可独立研究风险配置与信号 | 波动管理证明人工方向择时有效 |
| Daniel / Moskowitz，[Momentum Crashes](https://www.nber.org/papers/w20439) | 动量风险与市场状态相关，反弹风险不可忽略 | 熊市必须关闭 BRC MPG |
| Harvey / Liu / Zhu，[… and the Cross-Section of Expected Returns](https://www.nber.org/papers/w20592) | 多重试验需要控制筛选偏差 | 一次最佳回测足以确认参数 |

这些机构摘要在本线程已查阅；不是对文献的全面复现或系统综述。
**分析判断**：先统一约束共享方向风险，比同时优化策略开关、仓位倍数和排序更易解释。
逆向额度是结合当前最小仓位门槛选择的实验起点，不是论文最优参数。

## 4. 范围、额度与行为

### 4.1 精确作用范围

仅作用于 Owner 已授权账户／venue 下 CPM-RO-001、MPG-001、MI-001、BRF2-001、
SOR-1H-001 的合法 Crypto Events。每次仍校验 StrategyVersion、Event、产品与 side。
旧 SOR-001 永久禁用，TradFi 不获得也不丢失直接准入权限。未来新策略不自动继承。

**技术细化**：沿用当前账户级方向占用查询；若同账户存在其他产品的同向 Ticket，
它也占用 Crypto 新 ENTRY 计算时看到的方向风险。Overlay 不在 TradFi 准入上执行，
但共享资金和基础 Capacity 的间接竞争保持不变；不新增 Crypto 专属资金池。

### 4.2 计算口径

```text
E = action-time total_wallet_balance
D = same-account/venue/side nonterminal Ticket risk_at_stop sum
L = min(current base directional limit, selected overlay directional limit)
remaining_directional_risk = max(E * L - D, 0)
```

单笔再受既有总风险、单笔风险、margin、minimum materialization 等约束。
用 Decimal；D 包括已发行但未发送的 Ticket，不能漏算预留，也不能再次加上已计入的本 Ticket。
Claim/issuance 按现有阶段使用权威占用；发送前按包含本 Ticket 的占用重新检查。

存量超过新上限时，新额度为零，不改变已有仓位。方向上限是计划止损风险预算，
不是账户净敞口目标、投资比例或真实损失保证；多空不能抵扣。未发送 Ticket 不能被
当作已经持仓从而绕过新规则。高于新额度的未发送 Ticket 走正式终结与释放路径，
不得原地改写其冻结数量或生成第二次 ENTRY。

## 5. PostgreSQL 权威和身份

以下为目标逻辑模型；物理表名、索引与字段复用由 ODR-01 任务冻结。

1. **不可变规则事实**：rule_id/version/digest、精确适用范围与两个方向上限。
   首版不提供任意额度编辑器；更换规则版本必须显式授权和审计。
2. **Owner 选择 Journal**：账户／venue、view、规则身份、Owner、简短原因、请求时间、
   幂等身份、预期控制版本、requested/effective 时间、变更结果和认证证据引用。
3. **Current 控制投影**：唯一有效版本、待处理变更与切换状态；PostgreSQL 为唯一权威。
   初装显式写入 unset，效果无附加限制，不伪造 Owner 曾选择 neutral。
4. **准入和发送证据**：AdmissionDecision/Claim/Ticket 保存出生时的有效身份；
   durable Command 的发送授权事件追加实际采用的版本及校验结果。
   两次身份不同也必须可解释，不重写不可变 Ticket 或原准入决定。
5. **已有历史**：缺失出生身份记为历史未知，不按当前选择回填；不改旧 Review 收益。

正常 unset 是显式存在且已验证的控制记录。预期记录缺失、读取失败、未知版本、
身份矛盾均阻止受影响的新 ENTRY，不能默认 neutral；保护退出继续运行。
研究采样失败按既有隔离契约处理，不能吞掉控制／准入权威写入失败。

## 6. 切换生效与发单并发

### 6.1 产品保证

控制台区分**请求已保存／切换中／已生效／需介入**，不得把 HTTP 接收成功视为已生效。
每个 ENTRY 必须被准确归入旧版已授权发送或新版校验，不存在无版本的中间区。
切换请求提交后不再发放旧版的新发送权；新发行 Ticket 暂停至切换完成。

### 6.2 推荐协议与必须验证的缺口

1. Owner API 使用当前版本 CAS、幂等键及既有 TOTP step-up 提交持久化变更，
   与最终 ENTRY 发送授权在同一数据库协调边界上排序。
2. Entry 在短事务内冻结准确 Command 的最终发送授权、规则版本和唯一发送者；
   事务提交后才允许网络 I/O。不能把 claim_one_prepared 的租约等同于最终发送权。
3. 若旧版已有发送权，切换保持 pending；该准确命令按原授权完成发送及结果处理，
   不盲目撤销、不重新发送。等待发送者不可能再发出旧请求、结果已确定或按正式
   恢复流程闭合后，才提交新的 effective 版本。
4. 若切换先取得协调权，旧版不得获得最终发送授权；未发送命令按新上限校验或终结，
   正式释放预算、Netting Domain 和 Entry lane。
5. 未知结果、进程失联、租约到期不能单凭超时推定未发送。必须排除旧发送者继续执行
   的可能性并查询准确外部身份。未解决时维持 pending／ENTRY fenced，不阻塞已有保护。

**工程待验证项**：当前锁序、租约和 Worker 生命周期能否提供上述保证；暂停后复活的
旧进程如何失去发送权；实际发送授权的持久字段与恢复状态。ODR-01 必须用真实 PG
屏障及 recording venue 证明，不能用“发单前再查一次”替代协议证明。
这里不承诺数据库事务与交易所请求原子，不允许持数据库事务跨网络 I/O。

### 6.3 本地实现选择

账户／venue 级 `pg_advisory_xact_lock` 排序控制变更、签发和最终发送授权；网络 I/O
始终位于短事务之外。`brc_entry_send_authorizations` 冻结准确 Command、发送者、
控制版本和 5 秒签名窗口，期限不晚于原 Command deadline。CCXT 的 timestamp /
recvWindow 采用该冻结值，不因旧线程恢复或库内部重新签名而刷新。

**保证的边界是交易所接受权限**：进程可能在任意指令暂停，本地无法撤回已在网络中的
字节；固定窗口关闭后，迟到的旧签名不再具有有效接受权限。控制不能只凭本地超时
宣称生效。发送调用获得确定结果后可结束自己的授权；其他恢复路径须先读 Binance
USD-M serverTime，再读取准确订单事实来证明旧窗口已关闭。

**已经确证的成交／订单接受立即进入原保护流程**，即使旧窗口仍未关闭；方向切换
继续 pending。未知缺席在窗口关闭前不释放。已由其他安全流程判定结果的命令，
由现有 Reconciliation 的空闲 cadence 有界关闭发送授权，避免控制永久 pending。
恢复从不重发 ENTRY，也不创建第二命令 generation。数据库规则摘要包含精确 Event
范围；不允许通过只改策略名称或版本前缀继承权威。

同一控制同时只允许一条 pending 变更；重复同幂等键返回原操作，陈旧页面或竞争请求
显式冲突。变更失败不能悄悄变成 neutral，且不能覆写 Owner 维护暂停。

## 7. 控制台和运行所有权

主界面位于现有 **账户与持仓**，不用新建顶层导航。展示当前选择、effective 时间、
24 小时复核提醒、当前两向额度与占用、存量超限状态以及 pending 原因。
切换预览明确不平已有仓位、实际持仓可能继续净多／净空、逆向仍可交易。
预览是时点事实；提交使用 CAS，真正 ENTRY 仍取行动时账户事实。

Owner API 只写控制权威，不接触交易所凭据。Entry 执行变更协调与新增准入；
Observation 保持观察、研究原有配额；Lifecycle 与 Reconciliation 继续现有安全工作。
提醒复用现有 Owner 投影／Monitor，按有效版本去重，不增加 Worker 或外部消息渠道。
本次文档不创建聊天自动提醒。常规 tick 不输出 JSON/Markdown，不扫描全历史。

## 8. 探索性研究与经济解释

### 8.1 冻结假设

**保留逆向机会、收紧逆向风险，是否改善可接受回撤与右尾机会之间的关系。**
第一轮固定规则、策略参数、退出与排序；必要修复另记版本，不能悄悄混入同一组。
完整的最小控制／准入审计必须保存；市场路径样本继续受现有配额管理，披露缺失。

### 8.2 评价层次

| 层次 | 证据 | 边界 |
| --- | --- | --- |
| 判断 | 事前选择、理由、时间；随后固定窗口的 BTC 与市场广度 | 描述性预测关联，不直接等于收益因果 |
| 机会 | Signal 原始语义、有效控制、实际限制原因、路径 MFE/MAE 与大幅有利机会 | 路径不是成交或盈利；第一 blocker 不等于唯一 blocker |
| 组合 | 真实 Ticket 的净收益、回撤、成本、占用、最大赢家贡献 | 观察性前后比较不独立识别 Owner alpha |
| 反事实 | 未来有界离线模型按时间重放容量与订单假设 | 不能相加所有拒绝信号路径作为可执行组合收益 |

一期不增加第二实时仿真交易链，不自动扩大研究配额。经济分析／模型产物遵循独立
Strategy Research 工作区边界；本仓库文档只定义接口、证据需求和验收语义。
研究指标的精确窗口、广度成员和样本划分在分析前冻结，不事后按结果挑选。

首次 8 周复核检查覆盖、切换质量、机会损失和运行成本；缺少独立状态阶段就保留
“证据不足”。重复错失主要右尾且无相应风险改善、频繁追随行情反转、碎片额度拒绝
过多，均可触发修订评审，不自动更改生产参数或恢复中性。
经济解释遵循[评价契约](../../current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md)。

## 9. 上线与验收边界

这是 **R4 运行权威变更**，预计需要单一 forward migration。
停止、空仓、quiescent、历史保全、精确认证与 fix-forward 遵循
[部署契约](../../current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md)。
不进行持仓 schema 交接、双写、旧表 fallback、隐式 Resume 或自动选择偏多／偏空。
文档批准不代表生产门槛通过，软件安装与 Owner 正式控制生效分别验收。

工程完成需证明：精确矩阵、现有安全约束、真实 PG 竞态／崩溃恢复、未发命令释放、
未知结果不重发、维护暂停优先、Scope 隔离、历史不可变、证据可追溯、UI 真生效状态。
收益为负不自动否定工程正确性；工程 PASS 也不能证明经济有效。

## 10. 不确定性清单

| 项目 | 当前结论 | 闭合责任 |
| --- | --- | --- |
| 控制语义和首版范围 | Owner 已确认，不再保留先前 TODO | 按基线实现 |
| 逆向参数最优性、Owner 择时增益 | 未验证，不是开发阻塞 | 有界前瞻研究 |
| 切换与发送协调、旧进程恢复 | 本地实现与定向证据已有，完整回归和精确认证仍独立 | ODR-01/04/07 |
| 精确表／字段／锁序／索引 | 已在 0013 迁移、metadata 和仓储落实 | ODR-02/07 |
| 生产账户事实、实际发布时机 | 本次未刷新，不推断 | 发布阶段直接证据 |

只有涉及资金边界扩大、强制平仓、额外产品范围、改变逆向许可等产品语义变化时
回到 Owner 决策；常规技术实现由工程闭合。
