# 两条产品线的分支与固定工作目录

日期：2026-11-08。Owner已授权实施本地分支和目录管理；本轮不部署服务器。

## 固定映射

| 产品 | 集成分支 | 固定工作目录 | 本地测试环境 |
| --- | --- | --- | --- |
| Tokyo 全自动 | `dev` | `/Users/jiangwei/Documents/final` | 原 `.venv`、`dingdingbot-pg`、5432 |
| App 人工接管 | `manual-dev` | `/Users/jiangwei/Documents/final-manual` | 独立 `.venv`、`brc-manual-pg`、127.0.0.1:55434 |

同一个Git仓库通过worktree检出，工作文件、索引和分支独立；Git对象、标签与远程配置仍共享。
原功能分支 `codex/app-manual-takeover-v1` 保留，作为首轮实现历史；纳入 `manual-dev`
不代表完成完整验证或获得发布批准。研究及其他已有worktree不修改。

## 日常工作

1. 全自动功能从 `dev` 建 `codex/auto-*`；人工功能从 `manual-dev` 建 `codex/manual-*`。
2. 在固定目录运行工具和测试，避免使用另一个目录的 `.venv`、node_modules或生成物。
3. 公共修复使用独立提交，选择性cherry-pick到另一产品、分别验证；不例行整分支合并。
4. 策略、风险与账户授权各自决定，人工接管语义不回流 `dev`。
5. 发布标签各自区分：全自动保留 `tokyo-runtime-*`，人工版未来使用 `manual-runtime-*`。
6. 已核实当前认证工具通过 `git rev-parse --git-path` 解析证书位置：主目录使用
   `.git/brc-release-certifications`，人工worktree使用其独立Git管理子目录下的同名目录。
   不复制原证书；文件存在仍不是可用证明，必须核对产品、精确SHA、schema及命令集。
   后续产品身份和旧SSH入口拒绝的实现与证据见[发布准备记录](2026-11-08-manual-validation-release-preparation.md)。

## 环境隔离

- 人工目录只复制本任务脱敏开发证据；原副本保留可追溯，不复制 `.env*`、SSH、API凭据、
  生产DSN、账户授权、活动交易数据或旧认证文件。
- 人工Compose固定项目名 `brc-manual-local`，独立容器/卷/loopback端口；全自动Compose不变。
- 人工测试默认地址指向55434，并保留Owner测试的容器、标签、配置内容及系统标识核验。
- 人工推荐执行 `scripts/local/manual_pytest.sh <pytest参数>`；入口先检查目录、分支、venv
  和已有环境覆盖，发现指向其他项目时拒绝，不加载任何.env。
- 两边测试账户密码只是仓库已有本地开发值，不是交易所或生产凭据。
- 独立服务器/账户的绑定、安装及当前状态统一见本产品路线图；本规则不保留实时环境快照。

## 本地Git防误用

每个固定worktree通过worktree级 `core.hooksPath` 使用自己的本地钩子，不覆盖其他worktree。
提交检查当前目录和分支归属；推送检查目标分支/标签归属，人工目录拒绝推送 `dev`，
全自动目录拒绝推送 `manual-dev`。这是本地操作提醒，不是服务端保护，`--no-verify`
可以绕过，不能代替代码审查、发布身份校验或远程权限。

钩子放在各目录忽略的 `.local/project-isolation/hooks/`，切分支后仍存在。
删除或迁移目录前应先记录worktree配置，避免误清理依赖它的工作区。

## 检查命令

```bash
git -C /Users/jiangwei/Documents/final status --short --branch
git -C /Users/jiangwei/Documents/final-manual status --short --branch
git worktree list
```

人工环境检查：

```bash
cd /Users/jiangwei/Documents/final-manual
.venv/bin/python scripts/local/check_manual_workspace.py
docker compose -f docker-compose.pg.yml ps
```

## 当前授权边界

目录隔离阶段当时只落实Git、固定目录和开发环境。Owner现已授权完整本地验证与发布准备；
实际安装和当前Owner授权按后续明确决定及路线图核验，不能把目录建立阶段的授权边界当作当前禁止；历史见[发布准备记录](2026-11-08-manual-validation-release-preparation.md)。
任何“最新分支”“已同步远程”均不表示程序已认证、已部署或交易权限已开启。
Tokyo生产状态只从其产品工作区的路线图与行动时事实核实。
