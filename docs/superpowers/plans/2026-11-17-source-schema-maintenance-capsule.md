# 源Schema维护工具与联合升级顺序

日期：**2026-11-17**。**本地实现说明，未冻结候选、未认证或部署**。

## 1. 目的

生产源0023可能同时存在多张已经在交易所平仓、内部未终态的Ticket，以及错误命名空间的prepared清理命令。0024迁移继续要求源版本terminal-clean，不能通过增加旧Schema runtime读取或修改迁移门禁绕开。

## 2. 工程安排

- **独立源码工作区**：`/Users/jiangwei/.codex/worktrees/manual-recovery-prelude/final-manual`，分支`codex/manual-recovery-prelude`，基于`4724fc51`。
- **维护目录**：正式执行时为`/opt/brc/maintenance/<精确工具commit>`；current的运行版本和数据库runtime身份保留原值。
- **使用目的**：仅停止writer后的GET取证、正常Kernel结算与Feed历史重放，不提供交易所写接口、不启动后台交易或手机服务。
- **共同交付**：联合发布确认后，主分支的`manual_joint_recovery.py`先验证主成品R4/API/Static及源工具独立认证，再完成维护暂存/预览/apply。三阶段不会自行迁移、恢复ENTRY或切换current。

## 3. 入口

源工具：

1. `scripts/trading_kernel/stage_manual_recovery_capsule.py`：精确认证源码归档、摘要、受控解包、独立venv、持久完成标记；不改运行链接。
2. `scripts/trading_kernel/recover_manual_trade_batch.py`：1..16个明确Ticket，独立账户核实、完整闭环经济证明、事务预览/绑定摘要apply、按序重放。
3. `application/recover_closed_trade_batch.py`：只用正常Command supersession及VerifiedExitClosed/settlement/review方法，禁止直接修改预算、Ticket数量或消费水位。

主成品入口：[联合维护控制器](../../../scripts/trading_kernel/manual_joint_recovery.py)。只有维护成功并重新通过正式stopped-flat preflight，才允许原[联合安装器](../../../scripts/trading_kernel/install_manual_host.py)进行forward升级。

## 4. 审查与验收

源工具自己的单元/架构、数据库专项与静态检查先完成；工具源码与手机成品共同交Owner审查。**本轮不运行正式发布认证，不生成工具或主成品的冻结候选**。

现场apply依然要求真实Owner暂停、精确主机/账户/数据库身份、flat无残单、writer全部停止、相同预览经济摘要。任何未决claimed/unknown、范围外事故或不守恒成交均停止，不做自动猜测或修表。
