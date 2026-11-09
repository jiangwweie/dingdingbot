# 部署拓扑、发布与故障恢复

> **定位：解释性知识库** · [知识地图](README.md)。本页解释受版本管理的配置及流程；机器现状、部署 SHA、标签和验收结果只查 [MAIN_CONTROL_ROADMAP.md](../current/MAIN_CONTROL_ROADMAP.md)，执行操作前仍需刷新直接事实。

## 人工接管产品的发布边界

本分支属于 **首尔 App人工接管产品**，集成分支 `manual-dev`，与Tokyo全自动产品分开演进、账户和数据库独立。
Kernel、API和静态证书均绑定编译产品身份；运行环境还必须声明相同产品身份。
旧Tokyo SSH发布后端在构造任何远程命令前拒绝执行，不能通过改SSH别名绕过。
`prepare_manual_release.py`只校验本地精确证书和可选目标身份比较，不发SSH、不安装、
不启用ENTRY。正式安装/升级使用 `install_manual_host.py` 的产品绑定路径；前向schema迁移、Owner控制和历史保全仍须通过当前硬门槛。
软件发布、真实 Owner ENTRY、自然接单/保护、App 接管与通知送达分别核验；Owner已批准自然交易中验收App，不为验收制造订单。
（来源：[产品身份](../../src/trading_kernel/domain/product_identity.py)、
[准备入口](../../scripts/trading_kernel/prepare_manual_release.py)、
[当前状态](../current/MAIN_CONTROL_ROADMAP.md)）

## 接管状态跨重启与发布保留

**MANUAL 是持久化、不可逆的整笔管理权**，不是进程内标志。重启、升级、清理任务或 Owner 全局恢复都不能回 AUTO，也不能重发已终态拒绝的 ENTRY。
恢复先核对身份、覆盖历史与未知结果，再按当前管理权运行；MANUAL 只读，REVIEW_REQUIRED 继续核实，AUTO 才能走原自动生命周期。

发布仍要求正式空仓停写窗口，不能以人工接管为理由迁移活动仓、强平、撤残单或绕过全部写入者互斥。
独立 Owner API 也是停写清单的一部分；原密码/TOTP/Google、Owner配置及通知出口不得被 Tokyo 配置替代。
（来源：[管理权约束](../../src/trading_kernel/domain/trade_management.py)、[人工安装](../../scripts/trading_kernel/install_manual_host.py)、[官方升级](../../scripts/trading_kernel/manual_same_schema_upgrade.py)、[当前状态](../current/MAIN_CONTROL_ROADMAP.md)。）

## 拓扑：进程与逻辑角色分别看

```mermaid
flowchart TB
    Browser[Owner 浏览器] --> Nginx[Nginx HTTPS]
    subgraph Seoul[首尔人工接管产品部署视图]
        Nginx --> Static[独立 V2 静态 release]
        Nginx -->|Unix socket| API[独立 Owner API service]
        subgraph Kernel[Kernel systemd slice]
            subgraph Obs[Observation 单一 OS 进程]
                OL[观察与研究投影 loop]
                SL[各策略 Selection loop]
                ML[各策略 Materialization loop]
                FL[各策略 current facts loop]
            end
            EL[Entry service]
            LL[Lifecycle service]
            RL[Reconciliation service]
        end
        PG[(PostgreSQL 共同状态权威)]
        API -->|read / control 连接| PG
        Obs --> PG
        EL --> PG
        LL --> PG
        RL --> PG
    end
    Market[公开市场源] --> Obs
    Exchange[交易所只读真相] --> EL
    Exchange --> LL
    Exchange --> RL
    EL -->|ENTRY 写| Exchange
    LL -->|安全命令写| Exchange
    Local[本地人工产品发布控制] -->|SSH 与人工产品正式脚本| Seoul
```

**这张图表达仓库声明的逻辑部署关系，没有声称本轮核对了机器上的进程、数据库安装方式或网络端点。**共同数据库的具体服务位置以机器配置为准。（来源：[systemd Observation](../../deploy/systemd/brc-trading-kernel-observation-worker.service)、[API service](../../deploy/owner-console/systemd/brc-owner-console-api.service)、[Nginx](../../deploy/owner-console/nginx/owner-console.locations.conf)、[启动装配](../../scripts/trading_kernel/run_observation_worker_once.py#L97)）

## 服务、入口与配置责任

| 服务 / 组件 | 代码或配置入口 | 配置与恢复边界 |
| --- | --- | --- |
| **Observation** | [service](../../deploy/systemd/brc-trading-kernel-observation-worker.service)、[脚本](../../scripts/trading_kernel/run_observation_worker_once.py) | 常驻运行；scope/Job/Generation 有独立租约；进程内部多个 loop |
| **Entry** | [service](../../deploy/systemd/brc-trading-kernel-entry-worker.service)、[脚本](../../scripts/trading_kernel/run_command_worker_once.py) | 命令与 lane 持久化；当前运行身份和账户事实仍需校验 |
| **Lifecycle** | [service](../../deploy/systemd/brc-trading-kernel-lifecycle-worker.service)、[use case](../../src/trading_kernel/interfaces/lifecycle_worker.py) | 既有安全工作；不能用暂停新 ENTRY 替代生命周期运行 |
| **Reconciliation** | [service](../../deploy/systemd/brc-trading-kernel-reconciliation-worker.service)、[脚本](../../scripts/trading_kernel/run_reconciliation_worker_once.py) | unknown/critical/housekeeping；管理观察和通知隔离loop复用该进程 |
| **Owner API** | [service](../../deploy/owner-console/systemd/brc-owner-console-api.service)、[run_api](../../scripts/owner_console/run_api.py) | 独立目录、venv、socket、read/control DB role；认证凭据由 systemd credential 载入 |
| **V2 静态站** | [发布脚本](../../scripts/owner_console/deploy_release.py)、[frontend package](../../frontend/owner-console-v2/package.json) | 独立 dist release 与 symlink，不随意重启 Kernel |

**Kernel 环境变量**主要包括数据库 URL、runtime commit、schema revision、Worker identity、lease/timeout、market/venue factory；真实值不写入知识库。市场、账户、密钥等加载边界见 [production_runtime](../../src/trading_kernel/infrastructure/production_runtime.py)，这里只记录配置名称与责任，不读取 `.env` 或 credential 内容。

## 发布先分类

| 级别 | 改动边界 | 应用路径 | 主要验证与恢复 |
| --- | --- | --- | --- |
| **R0** | 文档、测试等 | 本地评审与提交 | 文档检查与适当测试；无需生产动作 |
| **R1** | V2 静态前端 | Owner deploy `static` | 精确构建/资源 hash；失败恢复静态 symlink |
| **R2** | Owner API / auth / 展示查询 | Owner deploy `api` | 精确 API certification、schema 与 healthz；仅恢复 API release/unit |
| **R3** | 同 schema Kernel 行为 | Kernel regular release | flat、当前事实、认证与运行身份；按失败阶段 fence / fix-forward |
| **R4** | Schema / Registry / Policy / authority | preservation-gated compatible upgrade | 停写、flat、精确来源、保留证明、前向迁移与目标恢复 |

来源：[classify_changed_paths](../../scripts/classify_release.py#L84)、[部署契约](../current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md)、[Owner 发布实现](../../scripts/owner_console/deploy_release.py#L112)。混合改动按最高级别，不能仅因有文档文件便归为 R0。

## 人工产品正式发布顺序

### 同 schema 或获准的精确前向升级

1. **冻结候选及精确认证**：按最高受影响等级执行 Kernel、API/static 检查；每个证书绑定产品、commit、schema，不能复用另一个分支或SHA。
2. **刷新行动时事实**：独立host/account/database身份、真实Owner政策、内部/交易所空仓、残单/unknown/Incident、风险占用和当前scope；旧报告不代替当前核验。
3. **围栏并停止全部写者**：包括四个Worker与Owner API，验证真实进程停止；不得以MANUAL绕过活动仓发布硬门槛。
4. **正式stage**：`install_manual_host.py --phase stage-upgrade`校验独立机器、产品、精确证书和支持的schema路径后接收归档。
5. **正式activate**：`install_manual_host.py --phase activate-upgrade`经`manual_same_schema_upgrade.py`再次核对停止条件和交易所事实，保存并比较源表及Owner控制，再按允许路径更新运行身份、Kernel/API/static。
6. **当前目标postflight**：确认服务、实际PG/schema、账户、Universe/控制保全及独立认证/通知配置；任何未知提交先只读确认，不直接回退旧写者。
7. **官方promote_entry**：只解除已证明安全的维护围栏、恢复服务就绪。Owner暂停意图保留；真实ENTRY恢复仍由控制台记录Owner/TOTP授权，软件安装不代替它。

**不是任意schema都能升级**。正式人工工具只支持其显式列出的同schema或精确前向迁移；未支持的来源须先设计、测试和审查，不能直接`upgrade head`。
不携带活动仓跨schema、不双写、不用旧schema reader、不downgrade。初始Tokyo无备份重建仅为历史授权。
（来源：[人工安装入口](../../scripts/trading_kernel/install_manual_host.py)、[host边界](../../scripts/trading_kernel/manual_host_bootstrap.py)、[升级](../../scripts/trading_kernel/manual_same_schema_upgrade.py)、[promoter](../../scripts/trading_kernel/promote_entry.py)、[安装测试](../../tests/trading_kernel/unit/test_manual_host_installation.py)。）

继承[Tokyo部署契约](../current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md)与旧部署测试保留共同的安全和历史参考；其SSH后端拒绝本产品，不可当作首尔发布命令。

## 失败阶段决定恢复方向

```mermaid
flowchart TD
    Fail[发布失败] --> Phase{身份与 schema 是否已改变}
    Phase -->|尚未改变且来源可证| Source[保留 ENTRY fence 按来源阶段恢复安全服务]
    Phase -->|结果未知| Inspect[只读确认实际 identity / schema]
    Inspect -->|仍未知| Stop[保持停止和 fence 等待明确事实]
    Inspect -->|确认来源| Source
    Inspect -->|确认目标| Target[目标 fix-forward]
    Phase -->|确认目标已改变| Target
    Target --> Cert[目标精确认证与 preservation 校验]
    Cert --> Safety[恢复目标安全 Worker]
    Safety --> Post[当前事实 postflight]
    Post --> Promote[独立官方 ENTRY promotion]
```

**回滚不是跨阶段统一动作**：R1/R2 可恢复其独立 symlink；Kernel identity/schema 已轮换后，不能因为界面“失败”就启动旧版本。来源、目标和未知三类事实决定恢复方向。（来源：[部署恢复实现](../../scripts/trading_kernel/deploy_tokyo_release.py)、[unknown identity 测试](../../tests/trading_kernel/unit/test_deploy_tokyo_release.py#L2345)、[目标 fix-forward 测试](../../tests/trading_kernel/unit/test_deploy_tokyo_release.py#L568)）

## Worker 重启如何继续

1. **正常停止**：常驻 loop 处理 SIGINT/SIGTERM 并退出；systemd restart-on-failure。多个逻辑 loop 在 Observation 进程中独立调度，并隔离单个 tick 异常。（来源：[worker_process](../../src/trading_kernel/interfaces/worker_process.py)）
2. **持久化恢复**：Scope、Command、Generation、Operation 的 due/lease/版本在 PostgreSQL；内存游标不赋予交易权限。
3. **租约到期**：重新领取前验证代次或 lease epoch，命令写结果不明时进入 unknown，不能把 lease 过期当作无外部副作用。（来源：[pg_repositories](../../src/trading_kernel/infrastructure/pg_repositories.py)、[pg_signal_repository](../../src/trading_kernel/infrastructure/pg_signal_repository.py)）
4. **身份不符**：旧 Worker 的 commit/schema 不能执行外部变更；隔离问题写者并由认证身份恢复，不修改 fence 来“让它跑起来”。（来源：[runtime_fence](../../src/trading_kernel/application/runtime_fence.py)）

## 故障诊断手册：先找哪条证据

**以下是只读取证顺序，不是自动执行生产变更的指令。**

| 症状 | 按顺序查证 | 定位实现 | 禁止用来代替证据 |
| --- | --- | --- | --- |
| 有 Signal 没 Ticket | Signal 冻结身份 → Readiness → Decision → lane → 账户快照 | [Entry](../../src/trading_kernel/interfaces/entry_worker.py)、[read_signal_path](../../src/trading_kernel/interfaces/read_signal_path.py) | 旧图表、另一个币种的 readiness |
| Snapshot 完成未激活 | epoch/pending → Job → Generation/Vacuum → 认证/预热 → proof/current | [selection runtime](../../src/trading_kernel/interfaces/selection_runtime_worker.py) | 只看 selected_count |
| 命令卡住 | 精确 Command → 租约及 status → venue client ID/namespace → truth | [unknown recovery](../../src/trading_kernel/application/recover_unknown_command.py) | 再发一张订单试探 |
| 已平仓未终态 | 外部 flat → 自有余单 → unknown → Aggregate → settlement/review | [Reconciliation](../../src/trading_kernel/interfaces/reconciliation_worker.py) | 手动改 terminal 或释放预算 |
| 服务 active 但没进度 | commit/schema fence → due/lease → tick_failed → retry/backlog | [reconciliation_health](../../src/trading_kernel/application/reconciliation_health.py)、[worker_process](../../src/trading_kernel/interfaces/worker_process.py) | systemd active 单一状态 |
| 控制提交冲突 | expected_version → 幂等键绑定 → snapshot_digest → Operation | [owner_control](../../src/trading_kernel/application/owner_control.py) | 重放旧 TOTP 或改数据库 current |

`read_signal_path` 只关联已有 Shadow 记录的 Signal；普通 Signal 的存在性与 blocker 应以 Owner signals/Readiness/Decision 为准，不能把该研究查询的空结果当作没有信号。

### 可复用的本地只读入口

在仓库根目录可先读 `--help` 确认参数。下列命令需要调用者已配置的只读连接；本知识库没有运行它们访问生产。

```bash
.venv/bin/python scripts/trading_kernel/read_signal_path.py --signal-event-id '<exact-signal-id>'
.venv/bin/python scripts/trading_kernel/read_selection_runtime_status.py \
  --strategy-group-id CPM-RO-001 \
  --selection-spec-id CPM_ABSOLUTE_DIRECTIONAL_EFFICIENCY_V1
```

时区解释：算法 session 以代码的 **UTC** 边界为准，Owner 页面业务时间使用接口声明的时区；不能按本机日期重建 session 身份。

## 验证与操作边界

本页从配置和代码验证流程，针对部署故障、身份未知和重启的本地测试见[代码与测试索引](CODE_AND_TEST_INDEX.md)。本轮没有执行部署、迁移、服务操作或生产控制变更；自然交易验收仍独立于文档交付。
