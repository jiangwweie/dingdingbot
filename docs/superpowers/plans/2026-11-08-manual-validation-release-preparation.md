# App 人工接管：完整本地验证与发布准备

日期：2026-11-08。产品：**brc-app-manual-v1**。Owner已授权本地实现、缺陷修复、完整验证与
精确提交认证；**实际部署与实盘启用仍需后续确认**。此前交付文档的停止点已被本轮授权取代。

## 1. 项目边界

- 固定工作目录 `/Users/jiangwei/Documents/final-manual`，集成分支 `manual-dev`。
- 本轮修复分支 `codex/manual-validation-release-isolation`。不把人工接管提交合入`dev`。
- 本地测试只使用独立`brc-manual-pg`、127.0.0.1:55434、人工目录的venv与前端依赖。
- 不采购、不连接新服务器；不读取/复制Tokyo凭据、账户数据或证书；不操作交易所订单。
- 原自动产品状态由`dev`工作区的路线图与行动时事实负责。本分支保留的Tokyo记录仅为历史。

## 2. 完整验证发现与修复

| 边界 | 失败条件 | 修复与证据方向 |
| --- | --- | --- |
| 对账与占用 | 将已释放Netting Domain与未终态的结算hold混为一谈 | 分开active domain与instrument hold；准入继续跨两方向保守排斥 |
| 方向风险 | INNER JOIN排除缺少Aggregate投影的非终态Ticket | OUTER JOIN保留原Ticket风险；不能因投影缺失少算风险 |
| 待核实恢复 | 空历史通过all(empty)后错误恢复AUTO | 完整Ticket窗口、全部可解释事件、所有已接单订单身份覆盖同时满足才可恢复 |
| 条件单覆盖 | REST最终相同条款被当作没有漏掉App改单 | 必须证明私有连接覆盖整个窗口；启动任务不算连接，重连不能覆盖之前缺口 |
| 缓存溢出 | 丢失旧事件后既可能误报完整，也可能永久阻断新Ticket | 记录丢失水位；旧窗口不完整，更晚新窗口可独立核实；MANUAL仍不可逆 |
| 跨日补采 | 总窗口可达三天，单次amendment接口只接受一天 | 拆成有界日窗口；满页、超预算、超保留期继续明确gap |
| 风险变化通知 | 先直接改current再提交事件，使通知看不到前后差别 | 变化经原子reduction更新；未变化时仅刷新观察水位；通知在提交后产生 |
| 观察身份 | 错Ticket/side/time的batch在冻结前抛错 | 在采集验证边界记录gap并冻结自动动作；不借未来接收时间扩展授权 |
| 多Ticket调度 | 顶层扫描与实际选中的Ticket不同，后者漏过干预扫描 | 选中Ticket在旧position对账前也做管理观察；确认AUTO后才继续原对账 |
| 发布身份 | 证书没有产品身份、旧入口默认Tokyo | Kernel/API/Static证书绑定产品；运行env及PG capability同产品校验；旧SSH入口拒绝执行 |

本轮没有提高风险、增加策略、改变Owner原有控制、伪造时钟/信号/订单或弱化发送窗口。
旧双向同标的测试已改为人工产品的拒绝语义；仍保留不同标的多空与多持仓并发验证。
旧迁移测试的源数据在取保全快照前按暂停前提准备，未放宽0016停写、空仓、暂停门槛。

## 3. 验证范围与证据分级

所有脱敏日志保存在忽略目录`.local/app-manual-takeover-v1/validation-20261108/`。
日志是展示证据，不能作为运行authority。

- RED/GREEN：空历史、连接缺口、缓存溢出、跨日查询、风险通知、身份矛盾、选中Ticket顺序、
  错产品运行与旧发布入口均有最小失败与修复验证。
- 全链路用例从Observation产出真实测试Signal，经准入、Ticket、durable ENTRY、初始保护和TP1，
  分别覆盖未成交新增、改单、撤单、人工成交接管，再到减仓、零仓残单hold、Owner清理与终态。
  使用Recording边界，无真实订单；缺少退出明细的基础Review明确unavailable，不伪造收益。
- 完整Kernel认证按官方R4命令集运行；Owner API与Static单独认证。证书仅能证明本地精确SHA，
  不证明真实新账户/App能力。最终结果以本worktree独立Git证书和认证日志为准。
- 认证前冻结干净候选；未通过命令不生成PASS证书，失败修复后必须重新认证精确候选。

## 4. 发布隔离及准备入口

编译产品身份来自`domain/product_identity.py`，不从Git分支名、目录名或本地JSON授信。
Kernel seed摘要及PG capability certification绑定产品；live环境必须显式声明
`TRADING_KERNEL_PRODUCT_ID=brc-app-manual-v1`。Worker与最终ENTRY preflight检查同一产品身份。

Kernel/API/Static精确提交证书各自带`product_id`，证书仍存各worktree独立Git管理目录。
旧`deploy_tokyo_release.py`、Owner Console旧SSH发布后端与旧drain桥接均在任何SSH发出前拒绝；
更换`--target`或SSH别名不能使这些入口变成人工版安装器。

`prepare_manual_release.py`只读取精确R4/API/Static证书，输出本地准备记录。可比较预计与
观测的完整目标绑定：产品、SSH目标、machine-id、venue、账户逻辑ID及真实UID、PG库名与
system_identifier、commit、schema。任一不匹配即拒绝。它不执行SSH、不信任本地绑定是
当前远程事实、不安装、不启用ENTRY；输出始终`deployment_authorized=false`。

## 5. 新环境仍须完成的验收

1. **新服务器与账户绑定**：真实主机、固定出口IP、独立Binance账户及API、独立PG/预算/证书。
   绑定必须从当时机器、PG和交易所只读事实核验，不能填写想象值或复制Tokyo身份。
2. **真实App协议覆盖**：普通/条件订单新增、取消、修改、改回、部分减仓、全平残单、重连。
   SDK合成测试无法证明App端实际形态。条件单原地改单历史仍无已核实补采接口；缺口不得自行恢复。
3. **新服务器安装器与演练**：这是独立空环境安装，不是Tokyo活动持仓迁移。收到实际目标后
   需要完成独立配置、最小权限、无写探测、安装演练、服务身份及postflight；旧发布器保持封闭。
4. **发布确认和开启**：Owner确认后才进行实际安装；ENTRY初始关闭。自然接单、保护、终态
   是上线后的独立证据，不用测试订单来伪装恢复完成。

没有新增业务决策要求。以上是外部信息与工程验收门槛，不能写成“已可上线”。

## 6. 候选认证过程记录

首个冻结候选的Unit/Architecture为1907 PASS，配套API/Static精确认证PASS；Kernel认证
在本地测试模板因中断删除而处于PG invalid database状态时失败，未生成Kernel PASS证书。
本地可丢弃模板现可识别该状态并删除重建；没有修改生产schema、跳过任何测试或安全断言。
随后补齐普通/条件单namespace+ID的整笔历史覆盖，避免相同数字ID跨namespace误抵消。

恢复后42项产品隔离、模板、管理观察与恢复正反例通过。后续冻结提交必须重新运行整套
精确认证；此前候选API/Static证书不能转移给后续提交。最终结果仍只由对应SHA的证书和
完整日志证明，本文不预先承诺PASS，也不授予部署权限。

第二个冻结候选的完整集成结果为1840 PASS、4 FAIL，因此未取得Kernel R4证书。
其中三项为历史迁移测试：两项源ENTRY未按新人工schema先暂停，一项断言旧降级报错文案；
调整测试源前提和对应Policy版本期望，保全快照仍覆盖迁移前后全部源行。
第四项为5001候选的Owner复盘查询在八进程并发下触发既有statement_timeout，单独运行通过；
后续认证改用四进程，保留全部测试范围、查询超时、候选上限及安全断言。

第三次完整集成为1843 PASS、1 FAIL，剩余失败仍是大候选复盘查询。进一步执行EXPLAIN
发现根因不是JIT，也不能靠降低并发解决：尚未ANALYZE的统计信息会选择终态status局部索引，
对每张Ticket反复扫描Aggregate。最小回归直接测实际执行计划：原路径访问Aggregate约12527505行，
新路径按Ticket主键有界LATERAL读取，最多5001行。相同本地数据测得2965ms→194ms，
固定3秒statement_timeout、候选上限、全部事实校验和分页语义不变；测试模拟统计尚未刷新
而非运行ANALYZE来掩盖问题。此变动在人工分支完成，未修改自动产品。
