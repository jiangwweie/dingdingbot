# 人工续管：技术可行性核验与编码任务

日期：2026-11-16。授权范围：只读资料、离线协议与本地测试、接入设计。**未修改生产执行代码、未向交易所发测试单、未改生产状态。**

## 1. 结论

**可继续实施前设计与本地工程准备；不能宣称减仓/Stop竞态已经全部验证，更不能据本轮结果放行真实资金操作。**

已证明：当前CCXT能构造Hedge对应平仓方向和Close-All条件Stop；真实历史解码REST证据能经过当前解析器；现有未知命令、取消超时、重启保持与原生命周期回归通过。已定位新功能必须增加的命令/阶段/事件，不能直接调用现有TP完成路径。

未证明：本账户“原固定量Stop已超过余量”“Stop先平完再到达市价减仓”的完整自然交错行为。历史语料缺原始HTTP字节和真实当日WS，不以合成数据补造。

## 2. 官方协议证据

Binance文档网页本轮返回HTTP202空内容；不能作为已读来源。改读Binance官方新版Python SDK固定提交：

`6a75e7e5744904380ab0bfbd0bd3433b997010f5`

[官方trade_api.py](https://github.com/binance/binance-connector-python/blob/6a75e7e5744904380ab0bfbd0bd3433b997010f5/clients/derivatives_trading_usds_futures/src/binance_sdk_derivatives_trading_usds_futures/rest_api/api/trade_api.py)。本地保存对应原文及哈希。

明确合同：

- Hedge必须指定LONG/SHORT；不能发送reduceOnly。
- STOP_MARKET/TAKE_PROFIT_MARKET `closePosition=true`触发时关闭当时全部对应仓位；不得同时指定quantity或reduceOnly。
- Close-All的Hedge方向仅SELL+LONG、BUY+SHORT；不是BUY+LONG或SELL+SHORT。

**文档没有给出本轮所需的所有超量/零仓市价请求和两订单竞态处理保证。** 错误码存在也不能证明每一种竞态都会命中该错误而不会产生其他效果。

## 3. CCXT与Kernel证据

当前工作区CCXT为4.5.56。零网络构造探针验证：MARKET BUY+SHORT / SELL+LONG带数量、无reduceOnly；STOP_MARKET closePosition=true同方向，转换为triggerPrice/clientAlgoId且无quantity/reduceOnly。

| 接入点 | 结果 | 必要改动 |
|---|---|---|
| CCXT request builder | 四种参数形状通过 | 不是venue接受/成交证明 |
| Kernel OrderCommandPayload | 不支持close_position，且quantity必为正 | 若采用Close-All，显式判别quantity模式；不能塞0绕过 |
| OrderTerms管理域模型 | 已能表达close_position且quantity=None | REST/WS真实字段可能为0/空/缺失，必须按官方证据严格支持，不猜测 |
| 当前REST解析 | _string固定读取quantity/origQty，0归一为None | Close-All缺字段形状尚无本账户真实样本，不能声称全覆盖 |
| 当前maintenance | synthetic人工减半、TP成交0，真实函数抛`TP1 venue quantity differs from exact cumulative projection` | Owner减量必须有自己的事件和数量投影 |
| 取消原TP | 原代码对终态未满量可能退出或进入归属核实 | 显式标记系统主动退休的TP目标，不能当作异常终态或外部接管 |
| 部分TP保护 | 默认无安全证明时进入原受控退出 | 不得把人工减仓塞进部分TP事件造成意外全平 |

Close-All是**建议的保护能力候选**，有助于降低减仓后Stop旧数量不匹配问题；仍须精确归属、替换、零仓残单清理以及pending market close竞态验证。不要把它包装成全部竞态的自动解药，也不直接改变所有当前Stop。

## 4. 回放与测试清单

| 类别 | 本轮结果 | 证据等级 |
|---|---|---|
| 管理协议/归属、真实退出、部分TP、collector、发送窗口 | 78通过 | 包含真实解码REST、合成故障、纯域测试；不是全部真实原始协议 |
| 取消超时、取消拒绝、未知结果与重启集成 | 5通过（24未选） | 手动产品本地PG，记录Fake venue效果，证明持久化/不重发逻辑 |
| lifecycle maintenance及management full-chain | 25通过 | 23集成＋2生产形状链路，包含CCXT解码和派生WS；不是现场自然验收 |
| CCXT请求构造 | 4种形状通过，零network transport | 纯请求构造 |
| 历史BNB解析 | 4条解码REST通过 | 历史真实字段经脱敏重编码，不是原始HTTP字节 |
| 派生部分成交/撤单 | 两个状态均保留executedQty=0.50 | synthetic，不证明真实cancel/fill交错 |
| 生命周期缺口探针 | 准确复现数量不一致异常 | synthetic input调用现有真实函数，零写入 |

测试总数**108项通过**，不能把文档/探针附加成生产认证数量。

历史语料来源：[provenance](../../../tests/trading_kernel/fixtures/management_protocol_v2/provenance.md)。ADA条件单child响应在夹具中明确为derived，必须保留该标签。当前没有补齐真实原始WS和超量市价竞态证据。

## 5. 明确编码任务及依赖

当前仅形成任务，是否启动生产功能编码由后续指令决定。

### C0 保护与平仓协议能力

- 固定当前CCXT/venue版本；建立fixed_quantity与close_all显式命令条款、精确条件单归属、请求/回读一致校验。
- 验证Close-All触发保护、取消、已归零残单和同域复用禁入；不允许旧残单影响新票。
- 对market close超量/零仓、stop先触发场景建立官方合同及可追溯协议语料，不能用模拟匹配引擎自证。
- 证据不足的真实写能力保持关闭。可进行本地故障测试，但未获自然/受控验收不能标live accepted；不新增真实测试单授权。

### C1 Owner操作与事实事件

- 新增OwnerReductionRequested/Observed等精确累计实际减量事件与operation引用；利润正负不影响允许的业务含义。
- 成交唯一键、重复/乱序输入、pending/rejected/partial/unknown明确状态；真实部分成交不重复扣量。
- 在PG原子记录意图、管理revision与Command，网络事务外；API只创建意图不发交易。

### C2 原TP退休与价格条件

- 显式profit_plan_source及`retired_by_owner_reduction`；不再把取消原TP认作未满额异常退出。
- 原目标价保留，起算点为实际减量核实；持久记录满足价格事实，不伪造TakeProfitFilled。
- 价格条件后调用共享BE规划，但不扣第二次TP数量；保护确认后原Runner。
- 已有Runner不退回；归零走终态；无人干预时原TP全链保持原样。

### C3 串行操作与恢复

- 票级锁、预览失效、撤原TP期间成交优先核实、减仓拒绝时合法恢复旧计划、未知时不重发。
- 部分成功维护真实余量保护，返回partial_effect；Stop交错、外部App介入、device撤销、重启均有确定结果。
- 正常业务避免并行不免除上述竞态；不能撤唯一保护来消除竞争。

### C4 其他操作与经济核算

- 收紧保护、人工TP单计划替换/取消、全平与残单；与C2的原TP退休来源区分。
- 真实减量进入Review及资金/风险投影；余仓保本不宣称整票保本，不把浮亏减仓当止盈。
- 手动移除TP数量限制不允许增加新ENTRY/预算或放宽现有止损。

### C5 授权、客户端和验收

- 依已确认手机设计落可信设备/长期会话/无TOTP真实授权、幂等预览、撤销；不得伪造totp_step_up。
- 已通过原型接真实capability和operation；该票调整中禁用重复写，其他票独立运行。
- 红绿测试、集成/协议故障、原AUTO与永久MANUAL回归、前向迁移保全及完整认证；部署另行授权。

## 6. 当前唯一未闭合的关键证据

**完整的Hedge market close与Stop交错行为尚未被当前可得官方合同及本账户原始语料共同覆盖。** 当前通过测试不能消除这项缺口。下一阶段可以实现不触及真实账户的领域/持久化/客户端，并继续补协议证据；真实减仓入口在门禁关闭前不得启用。

本报告不要求Owner重新选择已确定业务，只说明工程证据边界。若官方合同或后续真实语料证明目标行为不可安全实现，再给出具体限制和替代方式。

## 7. 本地证据

证据目录：`.local/cooperative-feasibility-20261116/`，包含sources、固定官方SDK原文、probe-results、lifecycle-probe、测试日志及manifest。生成材料不作为运行权威，不提交生产读取。
