# 人工续管四工作包：编码审查交接

日期：**2026-11-17，Asia/Shanghai**。状态：**开发与本地针对性验证；停止在候选冻结前，等待Owner审查**。

> **七项复审追加修复：** [本批根因、修复与故障路径验证](2026-11-17-seven-review-boundaries-repair.md)记录矛盾快照、新价格发送门、Runner与自然成交组合、恢复阶段、延迟全平及多票证明时效。候选冻结、最终集成认证和部署前等待要求保持。

## 1. 范围及停止位置

本批基线为`00b3dc60`，继续实现Owner认可的四项工作：受控减仓与自动续管、其他持仓操作、手机Web真实操作、生产恢复及联合升级编排。此前复审修复为基线，不重新宣称为本批新增。

**未创建发布tag、未冻结候选、未运行整包Integration/Full-chain或R4/API/Static认证、未上传/部署/重启服务器、未修改生产数据库/策略/资源、未执行交易所写入。** 本文测试均为本地单元/架构或明确列名的数据库专项；不是发布认证。

入场、MA50、策略收益结构、Static/Dynamic选择、杠杆和风险上限保持本批范围之外。设备DB角色持有者恶意伪造不作为首版防护范围；正常签名、撤销和单Owner绑定仍检查。

## 2. 四项实现

| 工作包 | 已实现的本地行为 | 主要源码 |
|---|---|---|
| **减仓续管** | 持久operation、原阶段保护转换、普通TP精确撤销、唯一减仓Command、实际成交/余仓/保护核实、余仓原价格条件续管、完成释放调整占用 | [操作推进](../../../src/trading_kernel/application/advance_owner_position_operation.py)、[事实采集](../../../src/trading_kernel/infrastructure/owner_reduction_source.py) |
| **其他持仓操作** | 收紧止损保留原阶段；普通LIMIT GTC人工TP设置/修改/取消；全平交原退出/清理/结算；准确受理回执与结果查询 | [其他操作推进](../../../src/trading_kernel/application/advance_owner_adjustment.py)、[单计划状态](../../../src/trading_kernel/domain/manual_profit_plan.py)、[预览规则](../../../src/trading_kernel/domain/owner_position_operation.py) |
| **手机Web** | 服务器采集事实生成预览、数量/比例输入、确认、签名提交、处理中/失败/未知结果、重新打开后恢复查询、主控与策略开关；结果通知复用outbox | [手机入口](../../../frontend/owner-mobile/app.js)、[真实API](../../../src/trading_kernel/interfaces/owner_console_http/routes/mobile.py)、[操作存储](../../../src/trading_kernel/infrastructure/pg_owner_position_operations.py) |
| **恢复与升级** | 独立0023维护工具处理受阻票及错误namespace未发命令、原始Feed顺序重放；原身份/当前release不变，内部terminal后才走0024原安装器；联合包修正遗漏的手机静态文件 | [联合维护入口](../../../scripts/trading_kernel/manual_joint_recovery.py)、[联合安装器](../../../scripts/trading_kernel/install_manual_host.py)、[恢复工具说明](2026-11-17-source-schema-maintenance-capsule.md) |

### 2.1 减仓保护

1. 首次受控减仓先将当前Stop转换为明确的`closePosition=true`全仓条件止损，同价、不放宽。保留旧Stop，确认新Stop后才撤旧Stop。
2. 内部Command仍冻结当时保护数量；**全仓Stop的HTTP请求不发送quantity或reduceOnly**。regular与conditional、固定数量与close-all分别建模。
3. 转换、手工收紧不应提前进入Runner，持久化原管理阶段；后续BE/Runner替换保留已选择的全仓模式。
4. 减仓真实成交独立于TP成交。原TP数量退出退休，余仓保留原目标合约价条件；原失败/时间退出继续存在。
5. partial/unknown不盲补发；Stop竞态只进入真实核实/收尾，不伪造MANUAL。外部App介入仍按原管理权合同处理。

### 2.2 操作及恢复

- 预览由worker获取当前交易所事实，API不允许客户端提交“已核实成交/保护”来生成执行事实。预览30秒，受理与发送分别核对版本、设备撤销、管理权与事实。
- 新写入始终走现有Exchange Command ledger。未知结果保留原命令身份，经原核实器恢复；过期且确证从未开始的prepared命令才可supersede。
- 原TP撤销但减仓未执行，合法时恢复原批准TP；目标已穿越、事实或授权不明时保留Stop并明确待核实，不擅自市价兑现或恢复独立人工计划。
- 手工TP采用单一普通限价计划；实际完整成交才沿原BE/Runner。取消人工计划不恢复旧自动TP；历史成交继续保存在原订单与Review来源中。
- 操作完成/拒绝持久化终态并释放单票调整占用；交易本身的预算、标的占用仍由正式终态结算释放。
- 通知为展示结果，不是交易权威；重复待核实状态按操作/状态去重，传输失败继续原outbox机制。

## 3. 0023维护工具边界

源Schema工具位于独立工作区`codex/manual-recovery-prelude`，基于已有事故修复`4724fc51`。它使用自己的`.venv`和0023源码，不给0024运行代码添加旧Schema reader/fallback。

1. 停止新入场、自然/Owner自主flat、停全部writer，账户身份/真实空仓无残单/Owner真实暂停通过。
2. 同一联合发布在维护目录暂存精确认证的0023工具，**不切换current、不启动服务、不修改runtime身份**。
3. 逐票签名GET形成完整守恒证明，允许系统部分TP与已核实外部退出合并。每个父/子订单、成交、时间和域分别核对。
4. 仅目标订单已终态的`prepared reconciliation_cleanup`可以由正式ledger方法退役；payload及错误namespace保留。claimed/unknown仍阻断，不直接改账务或跳事件。
5. 批量结算和旧Feed重放同事务；预览rollback，apply绑定相同经济内容摘要。任何一票失败，整批回滚。外部退出证据用于账务归属，保留原管理模式，不伪造“人工持仓接管”事件。
6. 原始事件仍经正式解析/按序应用；历史连接的应用时间不延长连续覆盖，不标记Feed ready。
7. 源Schema内部终态清洁后，原forward安装器执行0023→0024，保全/中断续装门禁不放松。最终手机、后台与资源配置一起上线。

## 4. 本地验证及证据边界

- 主分支单元/架构：**2395项通过**，最终记录见`.local/cooperation-build-20261117/owner-review-unit-architecture.log`。
- 主分支数据库专项：47项，覆盖operation store、减仓事实、手机API、真实Command操作链、8阶段续装、0024前向保全及准确退出，见`owner-review-targeted-pg.log`。发送前撤销/过期事实专项4项通过；后续边界追加测试单独记录，不累加为发布认证。
- 源0023单元/架构：2223项通过；批量恢复专项覆盖错误namespace未发命令、原子回滚、保留事件重放/覆盖不延长、混合外部退出经济来源，见独立工作区`.local/prelude-validation/`。
- Node执行真实app.js：跨标签页锁、未知结果、无效200正文、原身份清除、持仓回执身份核对、精确比例数量。
- 桌面真实浏览器390×844：本地fixture已走减仓输入/预览/签名受理/进度。截图在`output/playwright/owner-reduction-confirm-20261117.png`与`owner-operation-accepted-20261117.png`。**fixture不连接交易所，不是真iPhone或实盘验收**。
- Ruff、Mypy、JS语法及diff检查分别执行；最终数量以实际日志为准。

### 4.1 未宣称通过

**iPhone主屏幕安装/后台回收、正式域名cookie与PWA更新、自然Stop/减仓交错的真实交易所结果、实际通知送达、生产三票恢复、资源cgroup/整点负载、最终联合认证与发布仍待后续验收。** 没有用测试单补这些证据。

## 5. 审查重点

1. 一切新写操作的预览→受理→发送→实际事实→终态及故障恢复是否完整。
2. 未知结果、撤销授权、部分成交、Stop先触发与原策略退出竞态是否保持保守边界。
3. 原阶段/人工计划、close-all模式及真实成交账务是否跨重启/后续Runner保持一致。
4. 0023维护工具与0024运行程序是否保持源版本隔离；CLI是否在缺认证/缺暂停/非flat时停止。
5. 手机有效回执、比例数量、受理与生效的区别、关闭页面后的可查询性。

## 6. 审查代码获取

后续修复记录：[七项边界修复](2026-11-17-seven-review-boundaries-repair.md)、[两项操作终态修复](2026-11-18-owner-adjustment-terminal-repair.md)。最新本地验证以对应交接文档为准，仍未进入候选冻结或正式认证。

本批代码以**未提交的暂存diff**交付审查，新文件一并纳入；`HEAD`仍为基线，不能只审查提交范围而漏掉工作区。

```bash
git diff --cached HEAD --stat
git diff --cached HEAD -- src/trading_kernel migrations frontend/owner-mobile scripts/trading_kernel tests/trading_kernel
```

独立0023工作区也使用暂存diff，基线为`4724fc51`。两份工作区都没有新发布tag或认证产物。

**Owner审查完成前，不冻结任何发布候选或运行最终集成认证。**
