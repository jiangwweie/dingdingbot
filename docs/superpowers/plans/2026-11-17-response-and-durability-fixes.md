# 复审追加：有效回执与安装持久化顺序

日期：**2026-11-17，Asia/Shanghai**。状态：**本地修复完成后等待复审；未进入整包认证或部署**。

## 1. 本批范围

基线为`825151b6`。只修两项确认的问题：HTTP 200正文错误被当成功，以及journal/环境文件在replace前未同步临时内容。前轮Feed、续装、跨页面互斥与同Owner重绑查询保持，不重复计为未修复问题。

按Owner单人使用前提，不新增DB权限持有者恶意造设备的首版防护门禁。没有更改策略、MA50、风险、杠杆或交易capability。

## 2. 有效回执后才解除未知

### 2.1 已修复

- `request()`不再吞掉正文读取/JSON解析错误；null、数组或非对象响应拒绝，不返回伪成功空对象。
- `sendSigned()`在清除pending前调用按路径的结果校验。全局控制核对布尔目标与原预览版本或下一版本；策略控制核对strategy ID、目标状态、版本及必要事件字段。
- “HTTP头已到、正文失败”和“JSON可解析但缺字段/错类型/错目标/错版本”都保留同一签名请求，继续unknown，只读核实回执，不显示状态已更新。
- 查询`completed`也校验内嵌原结果；空/无效completed不能清除unknown。`not_accepted`沿服务端已有同Owner、未受理证据路径结束。
- 未来新增持仓写接口必须同时提供预期回执校验，未知路径默认拒绝假成功；本轮未开放这些接口。

### 2.2 验证

执行真实app.js的双页面Node VM测试：200正文流中断、JSON截断、空对象、null、数组、错误字段类型、错误目标、错误版本均抛出unknown并保留原请求身份；无效completed回执不解锁，随后正确回执才解除。正常成功控制仍清除自己的pending；策略结果的币种策略身份不符被拒。原timeout、跨页面锁和过时清除回归保留。

源码：[手机客户端](../../../frontend/owner-mobile/app.js)、[客户端故障测试](../../../tests/trading_kernel/unit/mobile_pending_write.cjs)。本地VM不是iOS真机验证。

## 3. 文件持久化顺序

### 3.1 已修复

统一`write_private()`的顺序：

```text
创建同目录临时文件
→ 写入并flush
→ fsync临时文件
→ os.replace到正式路径
→ fsync父目录
→ 返回成功
```

journal与环境写入直接使用该共同入口，不再依赖“替换之后再打开正式文件fsync”的补救。内容相同且默认不覆写的重试，也先同步正式文件及父目录再返回，避免上次目录fsync失败后误报已稳定保存。

同目录临时文件保留原权限约束，异常继续向上传播，未发布临时文件会清理；不可变候选/保全基线及安装前暂停/空仓门禁不放宽。

### 3.2 验证与证据边界

- 对journal与环境路径记录真实文件操作顺序，断言临时文件已flush且读取完整，顺序必须为file fsync→replace→directory fsync。
- 注入文件fsync失败：原正式内容保留、临时文件清理。
- 注入replace失败：原正式内容保留，临时文件清理。
- 注入目录fsync失败：错误明确抛出，不假报成功；新文件内容完整。
- 对真实UpgradeJournal.save及环境更新重复验证所有出版操作都沿相同顺序。
- 原8阶段真实本地PG中断续装测试继续通过。

**没有进行真实文件系统断电/硬件故障实验。** 本轮证明的是代码遵循正确的同步顺序与故障处理；不将进程异常注入包装成真实断电保证。

源码：[原子私有写入](../../../scripts/trading_kernel/manual_host_bootstrap.py)、[journal调用](../../../scripts/trading_kernel/manual_upgrade_journal.py)、[同步顺序与故障测试](../../../tests/trading_kernel/unit/test_atomic_private_writes.py)。

## 4. 验证记录

| 集合 | 本轮结果 | 证据 |
|---|---|---|
| 单元与架构 | **2362通过** | `.local/response-durability-fixes-20261117/unit-architecture-final.log` |
| 受影响单元专项 | **65通过** | `focused-final2.log`；与完整单元集合有重叠 |
| 原升级续装/控制保全PG专项 | **9通过** | `upgrade-pg.log` |
| 真实客户端模块 | **通过** | 双页面与无效200正文/回执故障覆盖，纳入单元 |
| Ruff / Mypy / JS语法 / diff | **通过；277源文件** | 本地命令输出 |
| 整包Integration / Full-chain / R4 / API / Static认证 | **未执行** | Owner代码审查门保持 |
| 生产／交易所操作 | **零** | 未上传、部署、重启、迁移或下单 |

## 5. 剩余边界

本批不声明完整手机产品完成。多票生产恢复编排、完整operation runner、Hedge Stop与减仓交错持续保护证据、真机PWA及联合发布认证仍待完成。手机持仓写capability与OWNER_REDUCE派发继续关闭，完成本批后等待Owner复审。

相关：[前轮四项边界交接](2026-11-17-four-boundary-fixes.md)、[统一实施计划](2026-11-16-seoul-recovery-and-cooperation-implementation-plan.md)。
