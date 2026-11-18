# 七项复审问题：本地修复与验证

日期：**2026-11-17，Asia/Shanghai**。状态：**本地修复；继续停在候选冻结前，等待Owner复审**。主成品基线`00b3dc60`，0023工具基线`4724fc51`；本批在上轮暂存修改上追加，不将上轮代码再次计为新增修复。

## 1. 已核实根因与修复

| 审查问题 | 原失败条件 | 修复后行为与直接证据 |
|---|---|---|
| **P1：较新未结单快照缺Stop仍声称覆盖** | 只检查未知订单，继续引用更早的NEW查询 | 两个采集器共同要求最新条件单页包含唯一、同身份/方向/数量模式/触发价/参考价/状态的Stop；缺失、变化、重复、触发子单或时间回退均拒绝保护证明。事实有效期从本次采集开始计，避免将历史读取时间重标为结束时间。原始协议测试覆盖空页、撤销、数量/价格/客户号/参考价变化与重复单。 |
| **P1：TP/新Stop发送前未查新价格** | 仅比较旧Stop，较长转换/撤单后新TP成为可立即成交单 | 创建人工TP前和真实PG发送门均检查新命令本身的限价/触发价；多空与等价边界分别验证。已越目标不创建新TP，进入明确重新预览分支；已准备命令越价则发送门拒绝。收紧Stop同样检查拟安装价格。 |
| **P1：人工计划挡住Runner** | 未完全成交时提前返回，Runner评估不可达 | TP记账与原Runner评估组合；未成交、部分成交仍按原阶段追踪，原绝对时间退出继续生效。保持TP单身份，未伪造完成。真实PG链从Runner安装人工计划后，再验证原自动保护推进。 |
| **P1：自然TP和人工operation互等** | operation要求旧预览不变，maintenance又因operation跳过记账 | 自然成交胜出时先supersede确证未发人工命令，再终结operation并交回原生命周期；尚未发的保护/全平请求可恢复原阶段。若存在claimed/unknown/已发送退出，则不假定其完成，单独用`NaturalTakeProfitRecorded`及精确耐久TP/逐笔成交证据记账，保留在途核实与占用。重复读取不重复扣量；发送未知结果不被跳过或重发。 |
| **P2：恢复原TP阶段被覆盖** | TP1_PENDING被泛化成closure_pending，序列化门拒绝恢复命令 | 保持`restoring_original_tp`，刷新事实、保留恢复命令白名单；事实读取超时也不覆盖专门阶段。撤单已证明后的原计划恢复使用新的Command generation，而非将旧accepted命令视作失败重试。恢复受理/明确失败各自处理，终态释放调整占用；未发过期/越价仍保留核实。 |
| **P2：全平等待期间不刷新事实** | EXIT_PENDING提前返回，5秒发送窗口持续过期 | 同一未发EXIT在EXIT_PENDING仍采集当前事实，不重建命令。重启并延迟超过5秒后可刷新并派发原ID；若期间原TP成交，则退役未发全平并交回生命周期，不能按旧数量发送。 |
| **P2：多票证明先后过期** | 逐票历史采集和账户/主机核验消耗首票TTL | 全部历史完成、再次账户/主机核验后，集中GET整账户positions/orders/algos/mode，基于全新的空仓/无残单证据生成共同有效窗口，历史经济内容保持相同。最终事务提交前再次检查共同期限；不直接延长旧快照。实际维护脚本用虚拟时钟验证三票各20秒加核验延迟。 |

（来源：本批修改源码、失败测试与本地PG/协议回归，见下列入口和本地日志；无生产状态推断。）

## 2. 主要审查入口

### 2.1 主成品

- [最新Stop确认](../../../src/trading_kernel/infrastructure/owner_stop_snapshot.py)、[减仓采集](../../../src/trading_kernel/infrastructure/owner_reduction_source.py)、[其他操作采集](../../../src/trading_kernel/infrastructure/owner_position_source.py)。
- [新指令价格规则](../../../src/trading_kernel/domain/owner_command_prices.py)、[真实PG发送门](../../../src/trading_kernel/infrastructure/pg_owner_position_operations.py)。
- [自然成交交还](../../../src/trading_kernel/application/handoff_owner_operation.py)、[生命周期组合](../../../src/trading_kernel/application/maintain_ticket_lifecycle.py)、[事实事件及Reducer](../../../src/trading_kernel/domain/events.py)。
- [受控减仓/恢复](../../../src/trading_kernel/application/advance_owner_position_operation.py)、[其他操作/全平](../../../src/trading_kernel/application/advance_owner_adjustment.py)、[同事务事实约束](../../../src/trading_kernel/infrastructure/pg_unit_of_work.py)。
- [延迟及成交竞态PG验证](../../../tests/trading_kernel/integration/test_owner_delayed_recovery.py)、[Runner及未知结果组合](../../../tests/trading_kernel/unit/test_cooperative_lifecycle_composition.py)。

### 2.2 源0023工作区

`/Users/jiangwei/.codex/worktrees/manual-recovery-prelude/final-manual`：

- `infrastructure/batch_closure_source.py::refresh_batch_closure_proofs`，`scripts/trading_kernel/recover_manual_trade_batch.py`。
- `tests/trading_kernel/unit/test_batch_closure_freshness.py`：共同新快照、历史不变、changed/slow/truncated/mode等反例。
- `tests/trading_kernel/integration/test_batch_closure_workflow.py`：执行实际run编排，三票各20秒并附加账户/主机延迟；确认刷新在历史与核验之后。

## 3. 实际验证

### 3.1 主成品

- 对应7项先补失败用例并确认RED，之后验证GREEN。本地目录：`.local/seven-boundaries-20261117/`。
- 原始协议/新价格测试**29项通过**（`protocol-price-final.log`）。
- 单元/架构**2425项通过**（`owner-review-final-unit.log`）。
- 受影响PG专项**59项通过**（`owner-review-final-pg.log`）；另有最后追加的恢复结果释放和来源故障路径单独重跑记录，不将不同轮计数相加为认证。
- Ruff通过；Mypy **247个source文件通过**；JS语法、真实app.js双页面/未知结果回归通过。既有`owner_operation_expiration.py`未标注函数体提示不是本轮新增失败；不将静态检查冒充场景验收。

### 3.2 源0023工具

- 单元/架构**2229项通过**。
- 集中刷新、实际三票编排、批量结算与Feed专项**23项通过**（`final-targeted.log`）。
- Ruff、Mypy **222个source文件**及diff检查通过。

测试采用本地隔离PG、原始协议形状和虚拟时钟，没有真实交易所订单。最终日志记录实际执行范围，测试数量不代替故障路径证据。

## 4. 范围与保留边界

后续复审发现的“旧TP意图复活”和“未发过期命令永久pending”已另行修复，终态、实际效果及最新验证见[两项操作终态修复交接](2026-11-18-owner-adjustment-terminal-repair.md)。本文件的测试数量保留为前轮记录，不代表后续批次或发布认证。

1. **不修改策略入场、MA50、风险/杠杆、选币、人工放宽保护等业务选择。**
2. 未知在途命令仍需真实核实；只记录已证明自然成交，不因此宣称未知结果已解决。不把自然Stop或系统成交伪造为人工接管。
3. 源工具仍为停止writer后的GET与正常Kernel结算，不改变0024迁移门禁、Feed覆盖边界或生产预算。
4. **未冻结候选、未生成发布tag/正式认证、未上传/部署/重启、未改生产数据库或执行交易所写入。**
5. iPhone真机、自然Stop/减仓交错、通知送达、生产多票恢复及实际资源负载仍未验收。

本批修改会重新加入两份暂存diff；HEAD仍分别为原基线，审查需包含工作区和新增文件，不能只看提交区间。
