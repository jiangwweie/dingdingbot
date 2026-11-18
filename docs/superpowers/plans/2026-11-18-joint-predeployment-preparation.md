# 联合成品部署前置准备

日期：**2026-11-18，Asia/Shanghai**。Owner已通过两项终态修复的复审并允许准备部署前置步骤。**本文记录执行步骤，不声明认证或现场验收已经通过。**

## 1. 本次授权边界

1. 固定已审查的主成品与独立源0023恢复工具，分别使用本工作区精确提交、自己的解释器和认证清单。
2. 主成品执行Kernel **R4**、Owner API **R2**、静态资源 **R1**；源工具执行自己的Kernel **R4**。正式认证包括完整Integration、Full-chain、迁移／保全及Golden/core parity。
3. 隔离测试只使用manual本地PG `127.0.0.1:55434 / brc-manual-pg`；两个工作区的数据库认证顺序执行，不并发争用测试模板或Compose资源。
4. 全部证书验证后，使用原正式构建器生成本地联合安装包和GET-only恢复工具包，记录SHA-256，检查手机静态资源确实在包内。
5. 允许只读刷新首尔主机、服务、数据库、账户、实际持仓／残单、Feed和资源状态；旧诊断与路线图快照不得替代当前事实。
6. **部署前等待Owner确认。** 不上传、不写围栏、不暂停、不停服务、不执行生产恢复apply、不迁移／安装／重启、不执行交易所写入；不为验收下测试单。

## 2. 本地执行顺序与证据

| 阶段 | 正式入口 | 成功证据 |
| --- | --- | --- |
| 精确候选 | 两工作区检查暂存差异、diff、隔离环境后分别提交 | 干净HEAD、精确SHA、工作区与产品身份 |
| 主成品Kernel | `.venv/bin/python scripts/trading_kernel/certify_release_candidate.py --commit HEAD --release-level R4` | 精确提交R4 manifest，完整命令输出与耗时 |
| 主成品API／静态 | `scripts/owner_console/certify_release_candidate.py`、`scripts/owner_console/certify_static_release_candidate.py` | 同提交R2／R1 manifest；手机构建并入静态认证 |
| 0023恢复工具 | 源工作区自己的`certify_release_candidate.py --commit HEAD --release-level R4` | 源Schema、源Registry和命令集的独立精确认证 |
| 本地打包 | `install_manual_host.build_artifacts`、源`stage_manual_recovery_capsule.build_capsule` | 构建器重新验证证书；内含精确源码、元数据和手机静态资源，记录归档摘要 |
| 准备记录 | `scripts/trading_kernel/prepare_manual_release.py` | `deployment_authorized=false`；缺现场绑定明确保留 |

执行认证时显式设置manual测试Compose、容器和回环PG环境，先运行`check_manual_workspace.py`；不得读取兄弟自动产品环境或复用其证书。命令遇到失败即停止该候选，不手工生成PASS或缩减组合。若确需修代码，形成新候选后重做受影响正式认证。

日志、证书副本、归档和只读现场快照放在`.local/joint-predeployment-20261118/`，不纳入运行时权威或将生成文件提交到源码。正式证书仍由既有Git metadata路径管理。

## 3. 后续生产维护顺序

**以下仅为部署确认后的操作顺序，本次不执行。**

1. 刷新主机／账户／数据库精确身份，真实Owner暂停新开仓；当前持仓和在途命令按正式门禁处理，不能以旧flat快照推进。
2. 交易所实际flat且无残单、writer停止后，联合维护入口暂存精确认证的0023 GET-only工具；不切换current或改原运行身份。
3. 明确选择需恢复的Ticket，正式预览形成经济摘要，apply绑定同摘要；处理错误namespace的确证未发命令，按序重放Feed，核实结算和预算释放。
4. 源内部terminal-clean后，正式安装器执行0023→0024 forward迁移、历史保全、阶段journal和联合链接切换；手机Web、后台续管、事故修复及已批准资源一起安装。
5. 核对精确证书／运行身份／服务／Feed／保护与管理门禁，执行官方promoter；Owner恢复授权另行核实，不伪造Resume。

## 4. 仍需区分的验收证据

- 本地PG和协议替身不能证明真实自然Stop／减仓交错、生产多票恢复或未来自然交易完整闭环。
- 桌面移动视口不能替代iPhone主屏幕安装、长期会话、后台回收、正式域名Cookie和PWA更新。
- outbox路径通过不能替代手机实际通知送达；静态资源声明不能替代生产cgroup、父级限制、节流／OOM和整点负载测量。
- 正式认证通过仍不等于部署通过或ENTRY获准恢复；现场不满足门禁就保留阻塞，不绕过或直接改账。
