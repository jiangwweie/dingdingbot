# 人工续管本地编码：首批交付记录

日期：2026-11-16。Owner已授权“剩下开始编码测试”，未授权部署或开启真实操作。

## 2026-11-17 Gemini审查修复

[复审交接](2026-11-17-gemini-review-fixes.md)记录已确认缺陷的修复、实际测试与仍未完成的operation runner/正式恢复边界。本地修复不代表完整手机产品已可启用。

## 2026-11-17 当前状态入口

**已进入本地编码，尚未完成完整手机产品，也未进行整包集成认证或部署。** 当前包含设备长期会话与签名请求、操作预览/受理持久化、减仓事实及价格条件生命周期、手机真实读取/主控接口、联合静态打包；动作派发和全部手机持仓操作尚待完成。Owner要求本批收尾后等待代码审查。

[本批审查交接及完整未完成清单](2026-11-17-owner-mobile-review-handoff.md)为当前编码状态入口。以下保留11月16日首批记录，不代表后来未新增实现。

## 本批实际完成

- `domain/owner_reduction.py`：冻结预览与纯状态决策，先撤精确原TP、数量/价格/保护/管理权检查、未知结果不重复准备减仓、部分成交、Stop竞态、价格条件和序列化恢复。
- `application/preview_owner_reduction.py`：从现有UoW读取精确Ticket和版本生成预览，不创建命令、不修改PG状态。
- `application/evaluate_owner_reduced_lifecycle.py`：匹配冻结ExitProfile身份和hash；复用现有pre-TP失败/时间退出及BE计算，真实减量后价格条件满足不再扣TP数量，原失败退出优先。
- 纯域/应用场景测试与真实本地PG只读预览测试；辅助夹具位于support，避免测试间依赖。

## Stop交错与“人工接管”

Owner提出Stop先发生后转人工作为降复杂度方向。当前实现不把自然Stop视为外部接管证据：有余仓转review_required决策并停止新动作；已归零先核实在途命令/残单再要求正式closure proof。确认实际余仓和原操作结果后，若需要真实Owner接管，走有授权的独立交接流程。

状态改成MANUAL不能撤回已发送请求，也不能替代核算。该问题不是让Owner替系统处理未知账务。人工交接API本批未实现，不宣称该建议已完整落地。

## 验证

初始测试确认模块缺失RED；新增已有减仓在途场景先RED后修复。回归：**190项通过**（新域/应用、原Reducer/管理权/部分TP、全architecture及一项PG预览）；Ruff通过，Mypy三源文件通过。中途发现测试文件互相导入违反架构，已改至support后重跑通过。

## 明确未完成

这批是预览和纯决策能力，**没有运行中调用方消费这些决策**。未新增Schema、操作持久化/事件归并、真实Owner授权校验、command准备/派发接入、网络facts采集、价格条件事件落库、API或手机真实写接口；未实现Close-All保护转换或可信设备认证。

不能把本批`record_reduction`/`request_break_even`等decision当已写入交易事件。后续必须在同一Kernel短事务中提交operation revision、真实证据与Command，核实授权、命令归属及capability，然后派发。不得单独运行此纯状态机作为第二执行链。

Hedge减仓与Stop完整交错仍为真实启用门禁；JSON状态往返测试仅证明序列化不丢阶段，不代替PG重启恢复验收。未运行完整release认证，未部署、未下真实或测试单，未修改生产策略。

## 后续顺序

1. 持久化operation与精确已发命令/成交证据、领域事件，接入原Reducer与维护流程。
2. 新增可信设备授权、真实能力门禁；所有写意图经原Command链，禁止新网络执行器。
3. 协议故障集成与全链验证，手机API接入；真实写能力在证据门通过前关闭。

参考：[技术可行性核验](2026-11-16-cooperative-control-feasibility-and-task-cards.md)、[统一执行设计](../specs/2026-11-16-owner-cooperative-execution-v1.md)。
