# 联合部署过程与证据索引

日期：**2026-11-18，Asia/Shanghai**。**联合安装、三票正式收尾及真实Owner恢复已完成**。当前生产提交、标签、Policy和运行快照只由[正式路线图](../../current/MAIN_CONTROL_ROADMAP.md)维护；本文记录过程、证据位置与未验收边界。

## 1. 正式执行顺序

1. 验证主成品三证、独立源Schema工具R4、两个干净工作区和归档摘要，刷新独立主机／账户／PG及交易所GET事实。
2. Owner通过原控制台真实暂停新开仓。部署只验证现有授权，没有生成Owner身份或修改其授权强度。
3. 围栏、停五writer并禁用Entry启动；创建停写备份，验证归档，再复制本地并核对完整摘要。首次复制超时后仅补传剩余字节，最终摘要及归档解析通过。
4. 正式暂存独立GET-only维护工具，回滚预览守恒与Feed顺序应用；历史窗口问题先在本地补RED/GREEN、独立重认证并再次暂存，未在服务器热改源码、篡改时间或放宽当前证明有效期。
5. 预览通过后用完全相同经济摘要apply，经正式Kernel事件／结算／Review释放三票及预算，按序重放原Feed。未知结果不盲发，错误namespace原payload保留。
6. 源terminal-clean后正式安装器暂存与forward升级，保全原始列和历史数据。保全排序超时在原门槛内通过临时维护管理员排序内存处理，随后恢复原配置；未改运行源码、Kernel权限或交易参数。
7. 启动安全服务，核实新Feed ready、三证身份、真实资源、HTTPS字节哈希、Owner只读权限及14轮真实事实采集；官方promoter先完成paused准备，Owner再真实Resume，最后只读验证新Policy授权和实际准入。

## 2. 本地证据索引

证据位于工作区忽略目录 **`.local/manual-cooperation-deploy-20261118/`**，是诊断与审计产物，不是运行时输入。

| 边界 | 证据文件 |
| --- | --- |
| 候选／归档与授权 | `local-bindings.json`、`owner-paused.log`、`writers-stopped.json`；原主成品三证与归档在前置准备目录 |
| 停写备份 | `server-stopped-backup.json`、`source-stopped.dump`、`source-stopped-restore-list.txt` |
| 历史窗口诊断／修复 | `ticket-ages.json`、`history-availability.json`、`fill-availability.json`、`recovery-preview-diagnostic.json`；源工具工作区`.local/history-window-{red,green,r4}.log` |
| 工具归档与R4 | `source-history-fix-r4-certificate.json`、`source-history-fix-capsule.tar.gz`、`stage-history-fix.log` |
| 正式预览／apply | `recovery-preview-history-fix.log`、`recovery-apply.log`、`source-terminal-preflight.log`、`source-terminal-feed.log` |
| 安装／保全／续装 | `stage-upgrade.json`、`install.log`、`upgrade-diagnostic.json`、`upgrade-timeout-diagnostic.log`、`preservation-query-plan.json`、`upgrade-sort-memory.log` |
| 临时管理员配置保全 | `db-memory-original.json`、`admin-sort-memory-prepare.json`、`admin-sort-memory-restore.json` |
| 安装后运行／静态 | `installed-postflight.json`、`installed-management-read.json`、`mobile-static-verification.json`、`resources.json` |
| 官方恢复与Owner授权 | `promotion.json`、`owner-resumed-chain.json`、`owner-restored-live-preflight.json`、`owner-restored-installed-postflight.json` |
| 当前准入／遗留显示 | `current-entry-authority.json`、`sor-entry-authority.json`、`intervention-monitors.json`、`monitor-scope.json` |
| 最终状态 | `final-deployment-summary.json`、`deployment-progress.json` |

## 3. 未被本次部署证明的能力

- **iPhone首次绑定、主屏幕安装、长期会话、后台回收及PWA更新**尚待真实设备验收；HTTPS文件和未认证401不能代替这些证据。
- **真实通知送达和自然Stop／减仓交错**仍待自然机会验证，未发测试单。
- **完整净收益**继续受手续费／资金费证据完整性约束，正式闭仓不把缺失费用当成零。
- **旧Universe告警显示**仍保留，当前账户事实、当前认证、官方恢复及准入通过不等于旧显示已清理。
- **整点压力和长期负载**未由本次资源静态值或短时OOM计数代替。

本次没有交易所写入、策略或Selection切换、加仓、杠杆／风险扩张，也没有直接SQL修Ticket、预算或消费水位。恢复使用正式维护工具，迁移使用正式安装器；之后的自然运行仍按既有批准策略和全部风险门禁执行。
