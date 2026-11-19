# 手机协作可靠性修复：联合部署证据

日期：2026-11-19，Asia/Shanghai。本文记录过程和证据；**当前生产提交、标签、认证和Owner运行状态只由[主路线图](../../current/MAIN_CONTROL_ROADMAP.md)维护**。

## 授权与执行

Owner批准部署并要求先排查服务器／程序异常。只读检查覆盖独立主机／账户／数据库身份，五服务与日志，当前Feed、Ticket、命令、事故、预算、交易所仓位与订单，CPU／内存／磁盘／inode／压力／内核错误，PostgreSQL锁、长事务、冲突和时钟同步。

Owner完成真实暂停后，部署程序仅验证授权与当前状态。精确候选三证通过，再刷新空仓和无未决命令的门禁，设置维护围栏、停止五个writer并禁用Entry启动。停写备份在服务器和本地分别校验完整摘要及归档索引。

正式独立安装器执行同Schema联合升级，Kernel／API／桌面和手机前端一起切换；历史、Universe、Owner／策略／选币控制保持保全。安装后恢复数据库维护资源，进行已安装只读认证、Owner读取角色、HTTPS字节哈希、Feed与新进程日志检查，再由官方promoter准备真实Owner恢复。

## 预检发现与边界

| 对象 | 事实 | 处理 |
| --- | --- | --- |
| 当前运行 | 无失败服务、OOM／I/O错误／段错误；数据库无锁等待、长事务或死锁；Feed接收应用一致；账户空仓、无残单、未决命令和活动事故0 | 门禁通过后安装；不据此宣称穷尽所有未知缺陷 |
| 历史核算 | 旧XRP反复补证据失败仍存在 | 随本批窗口修复安装；正常worker后续生成预览，未直接改写历史Review |
| 旧SOR输入记录 | 输入不足仅来自已停用的SOR-001；启用的SOR-1H当前评估正常 | 保留历史，不误算为当前SOR-1H失效，不恢复旧策略 |
| 停用策略／历史票告警 | CPM开关暂停；若干旧票告警已有终态 | 不擅自恢复策略或删除历史，不将旧显示当作当前事故 |
| 保全性能 | 数据库容器0.5核，约9万行诊断历史的原始排序超过安装器5秒门槛 | 停写维护期间临时将DB CPU设为1.5核、管理员work_mem128MB；原查询约2.5秒通过且摘要相同。安装完成后恢复0.5核和默认4MB；不改变应用角色、超时、业务数据或风险门禁 |

## 认证与安装证据

证据目录为工作区忽略目录`.local/owner-repair-deploy-20261119/`，不纳入版本控制，也不作为运行时输入。

| 边界 | 证据 |
| --- | --- |
| 原部署前检查 | `patrol.json`、`resources.json`、`host-health.json`、`observation.json`、`http.json`、`venue.json` |
| 精确三证 | `certifications.json`及`kernel-certification.log`／`api-certification.log`／`static-certification.log` |
| 认证环境纠正 | 首次R4最后一步因漏配冻结缓存路径退出，未生成证书；失败日志保留。补齐已验证缓存后完整重跑正式R4，未拼接或伪造证书 |
| 包与备份 | `joint-artifact.json`、`server-stopped-backup.json`、`source-stopped.dump`、`source-stopped-restore-list.txt`、`backup.log` |
| 停写与临时资源 | `writers-stopped.json`、`database-resources-prepare.json`／`database-resources-restore.json`、`db-resource-read.json`、`preservation-maintenance.log` |
| 正式升级 | `stage-upgrade.json`、`activate-upgrade.json`、`install.log`；服务端root-owned进度journal完整结束 |
| 安装后核验 | `installed-postflight.json`、`installed-management-read.json`、`mobile-static-verification.json`、`static-preflight-check.json` |
| 真实采集与准备 | `promotion.json`：14轮真实只读事实采集及官方prepared_owner_paused |
| 核算修复现场 | `repair-verification.json`：旧XRP预览就绪、原Review仍保留，安装后核算错误0 |

## 验收边界

手机减仓和自动续管已有本地原始协议／PG／签名链路证据，安装字节及运行身份已核实；**没有为了实盘验收创建测试单或重新发送Owner此前失败的减仓**。下一笔自然持仓的实际操作、Stop交错和真机长期后台仍分别验收。

历史核算预览就绪不等于Review已修订；必须由既有正式Owner批准路径应用。通知平台接受不等于手机已读。本次没有改策略、风险、选币或凭据，没有删除诊断历史，没有直接SQL修Ticket、预算或消费水位，没有操作东京产品。
