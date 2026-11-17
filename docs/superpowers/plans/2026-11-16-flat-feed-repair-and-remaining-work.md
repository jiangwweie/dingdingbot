# 零仓位订单流阻塞修复与人工续管剩余工作

> 剩余工作的统一顺序、依赖与验收见[实施计划](2026-11-16-seoul-recovery-and-cooperation-implementation-plan.md)。本篇保留范围或修复证据，不能作为另一份冲突的开工清单。

日期：2026-11-16。Owner明确要求修复并纳入工程。**本轮本地修复与验证，不部署、不修改生产消费水位、不跳过事件。**

## 1. 输入事实与当前边界

Owner提供另一工作区诊断：生产BNB162、XRP163为平仓收尾期间Stop取消，内部qty0、REVIEW_REQUIRED；旧观察函数将其转ManualTakeoverConfirmed，Reducer拒绝零仓位人工持仓，事务持续回滚。另有普通TP用conditional撤单缺陷。

生产BTC0.039及保护65776.5等数据仅为所提供11月16日18:58:53快照，本轮未重新查询，不能称当前现场状态。当前HEAD仍含触发路径，git历史定位管理观察基线来自bd4e8029等，d70e0b6d保留该路径。

诊断来源：`/Users/jiangwei/.codex/worktrees/manual-decimal-equality/final-manual/.local/feed-transition-20261116/diagnosis.md`及state.jsonl。原文“external”是归属分类，不证明具体是谁操作。

## 2. 本地修复

### 零仓位只读路径

`observe_trade_management`增加明确`is_flat_closure_observation`：仅qty0且处于reconciliation/cancel/settlement/review/terminal/manual_flat阶段。保存原证据、安排正常只读对账，不生成ManualTakeoverConfirmed，不改归属、不释放预算、不关闭Incident，不写交易所。

不是对所有qty0一概跳过：未成交ENTRY不满足该路径。feed callback和management scan使用同一前置判断，避免来源不同出现不同结果。原Reducer零仓位MANUAL保护保留。

### 正确撤单命名空间

PositionFlatConfirmed和ExternalFlatDetected创建cleanup effect时，精确已知TP身份为regular，Stop身份为conditional。保护替换的旧Stop取消仍conditional。旧错误测试期望已修订，不把错误语义当回归合同。

### 有界失败与顺序恢复

每个待消费事件的observer应用使用PG savepoint。确定性的ValueError/TypeError/KeyError失败回滚其副作用，但外层保留原始输入及追加diagnostic。诊断包含ticket、event、epoch、sequence、payload digest、runtime/schema、attempt与retry_at，不记录秘密或异常消息。

同精确运行版本最多3次：第一次失败后5秒，第二次后30秒，第三次后阻塞；500ms轮询只查询现有诊断，不重复调用故障函数或追加同样日志。applied不前移，后续事件不跳过，feed不ready。

候选新代码由runtime认证门确认后，在旧未消费epoch上使用新的application runtime identity允许重新有界应用；成功后追加resolved记录再推进对应序号。旧诊断不覆盖。

重连或换epoch前，必须处理旧epoch全部已持久化未应用事件。start_feed拒绝直接丢弃旧未消费记录；worker先按旧事件顺序应用，再建立新epoch。新epoch本身不证明旧覆盖完整；既有gap连续性规则保留。

协议解析失败仍按既有protocol_invalid fail-closed规则，不声称本次实现了任意未知异常的自动修复。数据库不可用/连接断开仍使外层失败，不能为了记录诊断吞掉破坏事务的错误。

## 3. 验证与证据

本地使用保存的真实BNB162/XRP163字段构造原Aggregate，旧ManualTakeoverConfirmed路径仍准确复现原异常；新应用函数保存证据、安排readonly reconcile，保持REVIEW_REQUIRED，0个新增交易命令。该重放未连接生产。

本地PG新增场景：

- flat取消不人工接管、不新建Command；事件保存，预算占用保持。
- 合成162/163序列在同一事务按序应用到163，不凭订单取消释放预算。
- observer更新后抛错，savepoint回滚副作用，原始事件与3次诊断耐久；applied仍为0。
- 同版本重启不重置次数，新候选显式应用后记录resolved。
- 旧epoch待处理时不能直接重置。
- 普通TP cleanup使用regular，Stop使用conditional；旧MANUAL和真实活跃接管不变。

最终合并回归见`.local/feed-transition-fix-20261116/final-regression.log`；另40项边界/派发回归通过，Ruff通过、Mypy五个修改源文件通过。测试集有重叠，不重复累加为独立认证。

未进行完整Release三证、现场安装、生产事件重放或自然BTC管理验收。代码已修不等于生产已恢复。

## 4. 部署后的正式验收（尚未执行）

1. 实时核实账户/host/commit/schema、Owner暂停与活动BTC/订单事实，依既有升级/发布合同确定可执行路径；不能为了修feed绕过持仓门禁。
2. 精确认证候选安装后，由正式feed worker处理旧epoch162、163；不直接UPDATE applied或删除事件。
3. 生产已经生成的错误namespace命令不会被代码修复追溯改写；必须核实准确regular订单及当前残单，通过正式命令核实/终态路径处理，不直接改payload或盲重发。对BNB/XRP用真实仓位/订单/成交/命令事实完成原只读closure路径，确认终态、预算与占用释放，不手工改Ticket。
4. 单独复核BTC当前仓位、有效保护、完整管理历史、REVIEW原因及恢复条件；不能因feed ready就强制清除BTC待核实。
5. 重新检查Entry门禁和真实Owner恢复授权。历史事故与失败诊断保留。

## 5. 手机续管未完成清单

| 部分 | 当前实际状态 | 剩余工作 |
|---|---|---|
| 预览与纯决策 | 已有本地代码/测试，PG预览只读验证 | 完整事实采集、精确授权/Command身份绑定 |
| 操作持久化 | 尚未实现 | operation/事件/唯一幂等、事务提交、重启推进 |
| Reducer与余仓续管 | 现有规则计算可复用，尚未接运行写链 | 真实Owner减量事件、TP退休、价格条件事件、保护确认后Runner |
| 交易所执行 | 协议初步核验；Hedge交错未完全证明 | 安全保护方式、取消/部分成交/未知结果与归零收尾 |
| 可信设备授权 | 设计完成，代码未实现 | 绑定/撤销、长期会话、真实无TOTP用途校验与发送门 |
| 手机API/客户端 | 静态原型通过；无真实接口 | 后台状态、能力门禁、确认/操作API、关键通知 |
| 迁移与正式认证 | 未开始 | 前向保全、原AUTO/MANUAL全链、精确release及联合发布 |

策略A、新Regime、局部两次失败暂停不属于本轮手机工程依赖。按2026-11-17 Owner最新决定：缺陷优先完成本地修复模块，生产与手机Web及完整后台续管联合发布；当前在集成认证前等待代码审查。

## 6. 历史问题与资源建议更新

人工退出核算、健康拒绝码及统一等待/单调告警属于部署版本已有修复实现，不再列作当前未修复；历史补账与自然验收单独评价。首尔资源读取与专属限额建议见[只读核验记录](2026-11-16-seoul-resource-review-and-repair-scope.md)。本轮仍无生产写入。
