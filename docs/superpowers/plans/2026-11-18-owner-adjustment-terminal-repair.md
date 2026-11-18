# 人工调整操作终态：两项复审修复交接

日期：**2026-11-18，Asia/Shanghai**。状态：**本地实现和回归完成，停在候选冻结前，等待 Owner 代码审查**。主成品基线仍为 `00b3dc60`，本批叠加在已有暂存实现上，没有提交、发布标签或正式认证。

## 1. 已核实问题与修复

| 问题 | 修复后的规则 | 实际效果与占用处理 |
| --- | --- | --- |
| **P1：重新预览提示后，旧 TP 意图仍能复活** | 记录不可撤销的 `end_requested`；推进和发送门都禁止旧意图继续。事实闭合后进入 `repreview_required` 终态，后续调用只返回已保存结果。 | 原 TP 已撤销时，按精确撤单证据记录退休，不恢复旧 TP、不伪造成交；确认余仓和 Stop 后释放调整占用。必须重新预览并签名确认，才能产生新的 TP 命令。 |
| **P2：确证未发送的过期命令永久 pending** | 收紧、保护转换和人工 TP 将 `SUPERSEDED`、`REJECTED`、`RECONCILED_ABSENT` 纳入明确结束分支。 | 核实保护和旧 TP 的真实效果后结束操作；未撤原 TP 则保留，已撤则明确记录。`CLAIMED`／`OUTCOME_UNKNOWN` 以及未确认保护转换仍保持占用，不将未知结果当成未执行。 |

（来源：下列当前源码、测试和本地执行日志；本批未查询生产状态。）

### 1.1 不可逆结束与事实落账

1. 共享收尾函数将结束意图持久化，存储层禁止删除或更改该意图；发送门拒绝它关联的新副作用。
2. 收尾核对 Ticket、管理权与修订、实际余量、Stop 身份和价格、全量覆盖及事实有效期。事实矛盾或结果未知时保持 `review_required`，结束意图仍保留。
3. `OwnerProfitPlanRetired` 经正常事件、Reducer 和 PG Unit of Work 校验落账，要求精确原 TP 命令及本 operation 的普通单撤销来源。使用 `retired_automatic` 显式区分已退役自动 TP，保留已有真实成交历史。
4. 仅退役确证仍为 `PREPARED` 的自有命令；完成时记录 `actual_effects`、结果和 `completed_at_ms`。释放的是调整占用，交易预算和标的占用仍由正式结算负责。
5. 手机结果显示旧 TP 是否已撤销以及已核实 Stop；不会只显示“未执行”而隐藏已发生的撤单或保护转换。

### 1.2 自动续管

取消的原 TP 不再作为当前活动 TP 参与余量推导。原失败／时间退出保留；终态失败操作不再挡住正常 Runner 更新。旧意图结束不代表交易结束，也不恢复已取消的独立计划。

## 2. 审查入口

| 边界 | 文件 |
| --- | --- |
| 结束意图、终态与实际效果 | [共享收尾](../../../src/trading_kernel/application/finish_owner_adjustment.py)、[操作推进](../../../src/trading_kernel/application/advance_owner_adjustment.py) |
| 存储和最终发送门 | [操作仓储](../../../src/trading_kernel/infrastructure/pg_owner_position_operations.py) |
| 原 TP 退休及来源约束 | [事件](../../../src/trading_kernel/domain/events.py)、[Reducer](../../../src/trading_kernel/domain/reducer.py)、[计划模型](../../../src/trading_kernel/domain/manual_profit_plan.py)、[Unit of Work](../../../src/trading_kernel/infrastructure/pg_unit_of_work.py) |
| 后续生命周期与展示 | [Lifecycle Worker](../../../src/trading_kernel/interfaces/lifecycle_worker.py)、[手机界面](../../../frontend/owner-mobile/app.js)、[通知](../../../src/trading_kernel/infrastructure/pg_notice_outbox.py)、[因果展示](../../../src/trading_kernel/application/owner_console/causality.py) |
| 故障路径和完整重新确认 | [终态 PG 专项](../../../tests/trading_kernel/integration/test_owner_adjustment_terminal_states.py)、[延迟回归](../../../tests/trading_kernel/integration/test_owner_delayed_recovery.py) |

## 3. 本地验证事实

日志目录：`.local/two-terminal-boundaries-20261117/`。日志为本地诊断产物，不作为运行时权威或发布认证。

| 检查 | 结果 | 日志／边界 |
| --- | --- | --- |
| 失败复现 | **先确认 RED** | `terminal-red.log` 复现两项原缺陷；`prepared-cross-red.log` 复现已准备 TP 越价后不结束。 |
| 新增终态专项 | **11 项通过** | 纳入最终 PG 批次：价格回落与预览过期均不能复活；新预览＋新签名确认可实际派发／安装新 TP；收紧和 TP 过期释放；保护转换未发送保留原计划；claimed／unknown 保持占用；未知撤单经原恢复器核实后结束；原退出和 Runner 不受遗留占用阻挡。 |
| 单元与架构 | **2,425 项通过** | `final-unit-architecture.log`，含修复源码定义锚点后的最终结果。 |
| 受影响 PostgreSQL 回归 | **71 项通过** | `final-pg.log`：终态、调整、延迟恢复、操作存储、生命周期、减仓、手机操作 API 和管理持久化。仅使用隔离 manual PG。 |
| Ruff／Mypy | **通过；248 个源码文件无类型错误** | `final-static.log`、`final-types.log`；既有未标注函数体的检查提示仍存在，不作为场景通过证据。 |
| 手机故障回归／JS 语法 | **通过** | `client-regression.log`：跨标签互斥、超时／未知回执、按身份清除、无效 200 正文；不等于 iPhone 真机验收。 |

不同轮测试不累加成正式认证数量。新增 PG 测试经真实仓储、Command ledger、派发与恢复路径验证，但交易所客户端仍为本地测试替身，没有真实下单。

## 4. 最终状态与保留边界

1. **两项操作终态缺陷已本地修复；原七项修复继续保留。** 本轮未改独立 0023 工具工作区。
2. 未修改策略、MA50、选币、风险／杠杆上限、加仓或放宽保护规则。
3. **未冻结候选、未提交／打标签、未执行正式集成或联合发布认证、未部署／重启服务、未修改生产数据库或写交易所。**
4. iPhone 主屏幕／后台回收、自然 Stop 与人工减仓的真实交错、实际通知送达、生产多票恢复及资源实际负载仍未验收。
5. 本批以暂存差异供审查，审查必须包含新增文件；Owner 审查完成前保持冻结前状态。
