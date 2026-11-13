# MA-CAPITAL-01 首尔部署证据

## 状态

**已获Owner部署授权，正式安装及真实Owner Resume恢复已完成，并通过恢复后只读核验。**
[路线图](../../current/MAIN_CONTROL_ROADMAP.md)唯一记录生产精确提交、tag、schema和当前授权状态。
[计算设计](../specs/2026-11-12-manual-capital-allocation-calculation-design.md)与[本地验证](2026-11-12-manual-wallet-allocation-implementation-evidence.md)解释行为及历史证据边界。

## 已完成

1. 只读核实独立主机、产品、PG system ID、账户、当前代码/schema及交易所独立双边模式。Owner真实暂停后检查授权记录，不用维护围栏代替。
2. 发现源ADA零仓票尚未终态；故障诊断确认完整closure采集持续被5秒整体预算取消。GET-only较长有界采集证明原系统入场、退出、全部终结订单及数量守恒。
3. 在隔离manual PG恢复实际暂停源，验证原Kernel收尾、重复执行及Owner/Command不变。单独给生产对账服务设置15秒采集预算并重启，该已认证源Worker自然完成终态和完整Review；未直接改票、未改变管理模式或扩大风险。
4. 真实终态源复演发现正式安装器控制摘要仍用SELECT-star，0022新增Policy字段会导致假保留失败。补红绿回归与安装器原字段投影，原字段篡改仍失败；重新完成最终精确提交R4/API/static认证。
5. 重新核对暂停/空仓/终态/无订单/无未知Command/无开放Incident；五写入服务停止，服务器和本地停止备份哈希一致，保留可恢复原始数据。
6. 正式stage-upgrade和activate-upgrade完成0021→0022前向升级；保留原字段/history、Policy数值和策略/Selection控制。没有复制东京凭据或变更东京。
7. 安装后认证PASS；14轮真实GET采集PASS；官方promoter prepared_owner_paused；五服务active/running，管理采集ready，无占用或事故。
8. 公网HTML/JS/CSS的状态和SHA256逐项与实际安装文件匹配。真实Owner Resume/TOTP及匹配的Policy事件授权已核实，非程序代为生成。
9. 恢复后完整认证、运行身份、五服务、管理采集、无围栏及实际持仓/挂单/未决命令/事故均通过只读核验，非新开仓数值和退出配置保留；恢复后尚无自然信号或新票，未强制下单。

## 证据与边界

本轮证据在 `.local/manual-wallet-deploy-20261113/`：

- `runtime-preflight.json`、`venue-preflight.json`、`owner-paused-preflight.json`：现场身份、仓位、真实暂停。
- `closure-diagnosis.json`、`closure-time-budget.json`、`reconciliation-budget-readback.json`、`ada-terminal-readback.json`：精确GET证据、超时预算、自然终态。
- 初次只读诊断调用了带FOR UPDATE的Incident读取，被只读事务拒绝；已改为纯SELECT，未变更生产。初次预算操作后的即时进程断言未通过，后续独立读取证明15秒已生效且源Worker完成终态；没有盲目重复写操作。
- `actual-source-rehearsal.json`、`terminal-source-rehearsal.json`、`final-source-rehearsal.log`、`installer-red.log`及green日志：源复演与保留校验回归。
- `r4-7c8179ad.log`、`api-7c8179ad.log`、`static-7c8179ad.log`：最终三证；旧候选证书不代替最终提交。
- `stopped-backup.json`、`private/source-stopped.dump`：停止备份；原始dump仅私有0600保存，不提交仓库、不输出内容。
- `stage-upgrade.json`、`activate-upgrade.json`、`final-paused-postflight.json`、`promotion.json`及`public-artifacts.json`：正式安装、保留、14轮事实及恢复准备。

0022通过认证与安装不等于新自然订单已经验证，也不保证每个信号必开仓。当前部署及真实恢复均已完成，Policy仍由真实Owner控制。历史旧Review缺口没有借本次迁移强行补齐；源ADA新票由正常链计算出的完整经济记录予以保留。

## 恢复后证据

`owner-restoration-verified.json`保存真实授权、服务、账户和风险不变的最终断言，`owner-resumed-chain.json`保存当前调用实例日志及交易所七品种只读事实，`owner-resumed-postflight.json`保存恢复后安装认证。具体Policy版本和时点由路线图统一拥有。当前没有本部署要求Owner继续操作的步骤，未宣称新版本自然成交验收已完成。
