# 管理采集与静态 Owner 恢复修复：正式部署验证记录

## 范围与权威

Owner 明确批准首尔人工接管产品部署，并通过控制台真实暂停新开仓。
当前版本、标签、schema、Owner姿态、现场数值与剩余验收仅见
[MAIN_CONTROL_ROADMAP](../../current/MAIN_CONTROL_ROADMAP.md)。
[修复与验证方案](2026-11-13-manual-management-recovery-v2.md)说明实现及测试边界。

## 已执行的正式链路

1. 刷新 host/product/account/PG/systemd 和交易所只读事实，核对真实暂停授权。
2. 停止所有 Runtime 与 Owner API writer，ENTRY disabled，并在真实暂停之后建立维护围栏。
3. 创建停止状态 custom-format 备份，验证 pg_restore 目录，下载本地并核对 SHA256。
4. 官方 install_manual_host stage-upgrade / activate-upgrade：精确证书/安装包绑定、空仓门禁、前向迁移、源列/行保留、运行身份切换。
5. 启动 Observation/Lifecycle/Reconciliation/API，由既有常驻流程完成管理连接及旧 CPM 围栏的正式排空/解除。
6. 核验旧 gap 不被补造成连续覆盖；实际 Owner 只读角色能读取管理就绪字段；公网 HTTPS 资源哈希与安装文件一致。
7. 通过安装代码执行真实 Entry admission/dispatch 两阶段 GET-only 事实采集，随后运行官方 promoter prepare-owner-resume。
8. 最终只读复核五服务、精确身份、认证、授权姿态、内部零占用、交易所无仓无残单及当前调用日志。

## 证据索引

本地证据根目录为 `.local/manual-management-deploy-20261113/`，属于显示和审计输出，生产不读取这些文件。

| 证据 | 所属边界 |
| --- | --- |
| artifact-preparation.json / certified-release.tar.gz | 官方 exact-candidate builder、认证及包摘要 |
| phase-a-preflight.json / phase-b-preflight.json | 真实暂停、行动时身份与停止前后事实 |
| stopped-writers.json / stopped-backup.json / private/source-stopped.dump | 停写、备份、保留与恢复材料 |
| stage-upgrade.json / activate-upgrade.json / preservation-summary.json | 官方安装与前向迁移保留证明 |
| installed-postflight.json | 安装认证、feed、CPM事件、服务、旧gap、角色权限和当前调用故障样本 |
| installed-management-read.json | 真实 Owner read role 与静态 HTTPS 文件校验 |
| promotion.json | 真实事实采集与官方 promoter |
| paused-final-verification.json | 暂停状态的最终就绪核对 |
| deployment-progress.json | 当前操作阶段；不是运行权威 |

## 授权与剩余验收

- 安装和暂停状态验收完成，真实 Owner Resume/TOTP 仍由 Owner 在控制台执行；程序不构造该授权。
- 原有策略、退出配置、资金风险合同和永久 MANUAL 行为保持；Tokyo 不变更，不创建测试订单。
- 已安装源码与本地验证证明能力边界；未来真实故障后的自动重连、自然新订单及手机通知接收仍需各自直接现场证据。
- 当前暂停状态和后续真实恢复的完成程度以路线图最新记录为准，不从此程序记录推断未来已恢复。
