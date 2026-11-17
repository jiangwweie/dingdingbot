# 单Owner边界收敛：四项可靠性修复与复审

日期：**2026-11-17，Asia/Shanghai**。状态：**本地修复，等待复审；整包认证与部署未执行**。

## 1. 最新Owner决定与本批范围

Owner确认单人使用，服务器和API可信：**不把持有API数据库权限后恶意制造设备的攻击防护作为首版门禁，不重做权限架构**。已有一次性绑定、长期会话、签名/撤销和交易安全约束保留；不扩大交易所权限。

本批只修其余四项：旧Feed重放抹掉断线区间、联合升级中断无法续装、多标签页覆盖未决请求、重新绑定后旧未受理请求永久锁住。基线为`61c01f6d`，复审使用`git diff 61c01f6d..HEAD`。

本轮没有上传、生产部署/重启/迁移、Owner策略修改或交易所写入。手机Web与后台最终联合上线、完成后在整包认证之前停下等Owner审查的要求保持。

## 2. 修复与证据

| 问题 | 最小实现 | 已验证 |
|---|---|---|
| **旧epoch回放消除断线** | 接收epoch新增`connection_observed_at_ms`，仅实际接收器能提交该连接健康观察；应用旧事件采用replay_only，不能以处理时间延长连接覆盖 | 旧连接健康到1100、新连接10000、实际worker重放后，旧覆盖终点仍1100；`continuity_covers(2000,9000)`为False；当前连接有效区间仍可核实 |
| **中断安装拒绝续装** | root安装journal冻结候选/原来源、数据库与账户、保全基线、原环境和三个原链接；正式入口接受同一候选的明确中间身份；迁移/身份可前向幂等，环境及链接按实际状态继续 | 真实一次性PG执行迁移与身份更新，分别在8个阶段退出后通过正式preflight/activate继续；原基线逐项不变、最终schema/commit/env/链接一致 |
| **跨标签页覆盖未知结果** | nonce之前取得同源Web Locks互斥；未知记录保存在IndexedDB；成功/明确拒绝/查询终态只能按device+nonce+幂等键清除自己的记录 | 执行同一个真实app.js的两个VM页面共享同一锁/存储：只领取1个nonce、发1次写请求；未知结果保留，另一页面不能新发；过时完成不能删另一请求 |
| **换机/重绑后旧请求永久锁** | 同一Owner查询旧nonce所属会话及设备；只有无已受理证据且nonce未消费，并证实旧设备/会话撤销或失效才返回not_accepted | 重新绑定后未提交旧请求可明确结束；已提交返回原completed；已有受理证据但尚无终态仍pending，不能因为撤销就抹掉未知结果 |

## 3. Feed连续性边界

1. 原始接收和按序应用仍分开，原始事件只在原stream_events表保存；应用水位仍由feed_current唯一负责。
2. `connection_observed_at_ms`来自当前接收器的连接事实，不能用应用worker的clock补造。closed receiver batch明确不提供新的健康时间。
3. 切换epoch时保存旧连接已确认健康终点；重启后的处理时间只用于本次事务/退避/租约，不作为旧网络连接连续证据。
4. 原始事件尾部分页、旧头部阻塞、协议缺口、失败提交不ACK与重启恢复的旧约束保留。新字段修改只在未部署0024候选中，不修改已部署旧迁移。

源码：[Feed持久化](../../../src/trading_kernel/infrastructure/pg_management_feed.py)、[worker](../../../src/trading_kernel/interfaces/management_feed_worker.py)、[接收器状态输出](../../../src/trading_kernel/infrastructure/venue_adapter.py)。

## 4. 安装恢复机制

### 4.1 一个精确候选与原始基线

- `upgrade-progress.json`是root安装状态，仅安装脚本读取，不进入交易runtime权威。进度原子替换并fsync。
- 绑定原source、目标commit/schema及三份release路径、artifact摘要和product（已有字段时），再次调用必须匹配。
- 原保全快照只冻结一次。重试不能重建来源基线，也不能拿迁移后状态冒充原值。
- 数据库系统标识、库名与账户冻结并逐次复核；候选marker、Owner暂停、交易所空仓/无挂单、内部终态/命令门禁继续行动时检查。

### 4.2 可恢复阶段

1. Alembic完成而身份尚未切换：接受`source commit + target schema`，重跑幂等前向迁移/身份安装。
2. 身份已提交而文件未切换：接受`target commit + target schema`，保持原保全基线进行对比。
3. 环境已写或部分链接已切换：只接受原环境/链接或精确目标；完成目标不可被旧身份检查误拒绝。遗留pending链接仅在属于该候选时接续。
4. 配置/服务启动阶段：只有journal明确已进入starting_services、全部发布链接和数据库均是精确目标，才允许停止已由本次候选启动的服务后续装；ENTRY服务始终不能在该恢复分支活跃。
5. 完成后的journal保留；下一次不同候选安装先归档上轮完整记录，不能因长期旧journal阻止未来升级。未完成时禁止重stage覆盖。

### 4.3 本轮未扩大的范围

仍不允许活仓schema迁移，不提供旧schema runtime适配或downgrade。此前源0023多张受阻票/历史错误namespace Command的正式终态恢复路径仍待完成，不能借此journal豁免。恢复限定精确stopped-flat安装，不擅自平仓或改预算、水位。

源码：[journal](../../../scripts/trading_kernel/manual_upgrade_journal.py)、[原正式activate](../../../scripts/trading_kernel/manual_same_schema_upgrade.py)、[原preflight](../../../scripts/trading_kernel/manual_host_bootstrap.py)。

## 5. 手机并发与重新绑定

- 保持一个浏览器注册、一个未决写意图。Web Locks在nonce领取之前跨页面串行化；页面崩溃会释放锁，已持久化的未知请求仍保留。
- IndexedDB使用同一读写事务核对请求身份再清除，避免过时结果误删新记录；没有增加离线交易队列或自动重发。
- 不支持Web Locks的浏览器明确拒绝写操作，需要支持的新版Safari；这是低复杂度首版约束，尚未当作已完成真机兼容验收。
- 新会话只能在同一Owner范围核实旧nonce。已有write evidence优先，无结果继续pending；无证据且旧授权明确失效才返回not_accepted。
- 服务器查询与受理仍通过同一短事务锁串行；旧请求不能在撤销后复活。重新绑定不会直接无条件清掉本地unknown记录。

源码：[手机请求管理](../../../frontend/owner-mobile/app.js)、[回执接口](../../../src/trading_kernel/interfaces/owner_console_http/routes/mobile.py)、[双页面故障测试](../../../tests/trading_kernel/unit/mobile_pending_write.cjs)。

## 6. 实际验证

| 集合 | 结果 | 证据 |
|---|---|---|
| 单元与架构 | **2354通过** | `.local/four-boundary-fixes-20261117/unit-architecture.log` |
| 本地PG专项 | **40通过** | `pg-regression-final.log`；8阶段安装、Feed、API、迁移及原控制保全；不等于整包Integration |
| 重绑与pending保留追加 | **7通过** | `rebind-final.log`；与上述API集合有重叠 |
| 双页面实际客户端模块 | **通过** | Node VM使用真实WebCrypto和app.js；模拟锁/IndexedDB，不冒充Safari真机 |
| 静态检查 | **Ruff / Mypy通过；277源文件** | 本地命令输出；JS语法与diff检查通过 |
| 整包Integration / Full-chain / R4 / API / Static发布认证 | **未执行** | Owner复审门保持 |
| 生产操作、交易所订单 | **零** | 未上传、部署、重启、迁移或下单 |

测试集合有重叠，不将总数当产品完成证明。升级专项使用真实本地PG迁移/身份和临时文件/链接；交易所只读事实、systemd和Nginx命令在测试中替换为本地记录器，现场行为尚待正式验收。

## 7. 本批最终边界

这四项代码修复完成后等待复审。完整operation runner、Hedge Stop/减仓交错持续保护、全部手机写操作与表单、真机PWA，以及源账户多票正式恢复仍待完成；持仓交易capability与OWNER_REDUCE派发继续关闭。策略、MA50、选币、杠杆和风险配置未改变。

相关：[上一轮交接](2026-11-17-followup-review-fixes.md)、[统一实施计划](2026-11-16-seoul-recovery-and-cooperation-implementation-plan.md)。
