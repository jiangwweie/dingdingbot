# AMT-01 前置实现交付与完整验证确认点

> **阅读说明**：本文保留设计/实施时的决策、缺口、分支与阶段证据。起始功能分支 `codex/app-manual-takeover-v1` 已作为历史保留，人工产品集成分支为 `manual-dev`。文中的“未部署”“待确认”属于当时阶段，不能覆盖后续Owner授权或当作当前未完成清单。当前代码、生产身份、Owner状态与自然App验收统一见[正式路线图](../../current/MAIN_CONTROL_ROADMAP.md)；Owner允许在自然交易中完成真实App验收，不能据旧阶段重新要求测试订单。

日期：**2026-11-07，Asia/Shanghai**。
分支：**`codex/app-manual-takeover-v1`**。
状态：**前置程序路径已接入并完成受影响验证；等待 Owner 确认进入完整验证与发布隔离。不是发布候选。**

依据：[Owner 决策](../specs/2026-11-06-app-manual-takeover-v1-owner-decisions.md)、
[设计](../specs/2026-11-06-app-manual-takeover-v1-detailed-design.md)、
[计划](2026-11-06-app-manual-takeover-v1-implementation-plan.md)。
Owner本轮明确要求完成前置步骤，进入完整验证与发布隔离之前等待确认。
本文只记录本地证据，不代替账户实际行为验证。

## 1. 本轮程序范围

| 边界 | 已接入内容 | 代码证据 |
| --- | --- | --- |
| 采集与干预识别 | Reconciliation内原始账户订单事件缓存、普通/条件订单历史、精确旧订单查询、普通订单修改历史、覆盖水位及去重 | `binance_management_stream.py`、`management_collector.py`、`management_observation_worker.py`、`pg_management_repository.py` |
| 管理权 | 外部有效订单操作不等成交；整笔永久接管；同ID条款修改；自然TP成交/条件单子订单不直接当Owner操作 | `management_intents.py`、`trade_management.py`、`observe_trade_management.py` |
| 人工仓只读收尾 | 部分数量更新、保护覆盖、全平待残单、Owner清理后基础结算；不调用自动撤单/平仓 | `reconcile_ticket.py`、`ManualPositionObserved` reducer |
| 风险与准入 | 保守初始风险下限、真实拉远stop的额外风险、实际减仓占用、未知/陈旧事实阻断、账户两方向标的唯一占用 | `manual_position.py`、PG admission/exposure、instrument health、ENTRY preflight、0017唯一索引 |
| 自动写入检查 | Command发送、生命周期、reducer、UoW effects、post-fill、Vacuum、Owner退出与部署drain入口；MANUAL不派生自动写入 | 原有Kernel路径，不新增交易写Worker |
| 展示与通知 | DTO/查询包含管理权与订单事实；人工卡片不继续显示自动TP/Runner进度；初始保护、接管、风险变化及待核实通知 | Owner API/V2、`feishu_notice.py`、事务后通知 |

新数据结构为0017前向迁移：管理观察current、append-only订单证据、Aggregate当前风险/订单字段、
同一账户/标的非终态Ticket唯一约束。0016管理权不可逆和事件原子约束保留。
新服务器防错部署、新产品身份正式认证属于下一阶段，本轮没有执行或宣称完成。

## 2. 已验证的重要反例

- 未成交人工挂单可接管；普通同ID改价后改回仍有独立修改证据。
- 程序自己的TP1创建不接管；条件单触发生成的实际订单不直接误判人工。
- 首次保护已被Runner正常替换时，仍能进入人工接管。
- 观察断档冻结该笔自动动作；补齐整笔历史且所有变化可解释才可解除待核实；
  MANUAL即使随后恢复事实也不能回AUTO。
- 人工部分减仓不补量、不要求固定TP1数量；原TP/stop继续在交易所，程序不清理。
- 仓位零但有残单/未完整分页时不释放标的；确认清理后结算且MANUAL标签留存。
- 拉远stop增加风险占用，保本不变成零风险；固定stop数量超过剩余仓位不盲认保护有效。
- 人工全平释放后，风险overlay不留下负值或幽灵占用。
- 原同标的多空允许测试改为新分支拒绝语义；容量测试使用不同标的并保留原风险断言。
- 关闭/平仓入口不会把人工仓恢复为自动，未知命令结果不生成Runner后继命令。
- 接管通知在事务提交后发出，同一次接管重试不重复通知。
- 前端人工/待核实交易不沿用自动“保护已安装”徽标。

## 3. 本地验证证据

证据目录：`.local/app-manual-takeover-v1/remaining/`，被Git忽略，不是运行authority。

| 范围 | 实际结果 |
| --- | --- |
| 单元与架构 | 1875 passed，`fast-reviewed.log` |
| 核心受影响集成切片 | 117 passed，`affected-final2.log`；包括准入、未知命令、原自动生命周期和接管链 |
| Owner查询/因果详情 | 132 passed，`owner-final.log`；包含单元与集成，不与上一行加总 |
| 历史迁移保全切片 | 3 passed，`migration-slice.log` |
| 额外边界切片 | `boundary-slice.log`、`oversize-green.log`、`buffer-test.log`、`source-own.log`后续修正以`system-tp3.log`为准 |
| 静态检查 | Ruff、Mypy219源文件；均PASS，`lint-reviewed.log`、`types-reviewed.log` |
| 前端 | TypeScript通过；`test_manual_management.mjs`通过，未运行正式静态发布认证 |

保留RED和失败定位日志。早期失败包含旧双向语义测试、fixture时间/订单TIF不匹配、
新增状态DTO遗漏和文档锚点；未弱化资金、发送窗口或安全断言来通过。
本地PostgreSQL仅使用仓库可丢弃测试环境；没有使用Tokyo数据库、凭据或交易所测试下单。

## 4. 下一阶段必须核验的边界

**前置验证通过不等于所有交易所行为已经被证明。**以下明确留给Owner确认后的完整验证：

1. 新独立账户真实App普通/条件订单消息形态、条件单原地改单/换ID行为、重连与SDK订阅覆盖。
2. 条件单没有已证明的独立修改历史接口；发现可能“改回原值”且缺少可证明过程时，
   当前实现保持待核实并限制准入，不声称未干预，也不把未知原因伪装为Owner。
3. 历史超过保留窗口、超过有界两页/修改查询预算、事件缓存溢出时明确保留gap，
   不丢弃分页后自动授信。需要用真实工作量确认容量和恢复可用性，不能承诺无限历史补采。
4. 多张重叠止损/非市价stop/部分覆盖无法证明风险上限时保守阻断新开仓，仍允许Owner在App管理。
5. 本地合成协议和Recording Source不等于供应商对所有App动作的保证；运行时只依据可核实变化。
6. 完整全链路、全部集成组合、终态经济明细、新产品配置/权限最小化、错服务器部署拒绝、
   精确R4/API/Static认证以及新环境真实postflight尚未执行。
7. 历史独立partial TP1缺陷不因人工接管而自动变成已修复；完整验证需继续揭示其真实边界。

如下一阶段发现无法覆盖Owner已允许的操作，必须报告具体技术缺口，不静默改业务规则。
这不要求Owner重新决定已确认的交易分工。

## 5. 停止点

**停在进入完整验证与发布隔离之前。**没有运行full_chain目录或完整R4认证，没有推送、
合入原`dev`、改Tokyo、采购/部署新服务器或使用真实账户做操作验收。
当前代码需经下一阶段验证和审查才能形成候选，不能直接部署。
