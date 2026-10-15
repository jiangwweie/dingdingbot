# ALPHA-02A 实施与本地验收

## 范围与发布安排

**Owner 已确认 A+B 联合发布、独立验收，软件上线与研究采集启用分开。**
A 为已合入 dev 的 OBS-EFFICIENCY-01；B 从该 dev 新建 `codex/alpha-02a-signal-path`。
B 的交付是审查候选，不是生产发布。审查合入后，以最终精确提交重新分类并完成 R4 等
正式门槛；生产部署与生产采集额度均须后续 Owner 明确授权。本记录不替代主路线图的
生产状态，也不复用 A 的 R3 作为 A+B 认证。

## 已实现

| 能力 | 实现与事实边界 |
| --- | --- |
| 五策略路径 | CPM/MPG/MI/BRF2 与 SOR-1H 多空事件；有效 Signal 的官方生产事务冻结精确触发 1h close、Registry 原始 stop、24 根 horizon、事实/路径摘要和运行源码身份 |
| 指标 | Decimal MFE/MAE、极值所在封闭 bar、+1R/+3R/+5R 与初始 stop 首触 bar；同根标 ambiguous，不推断盘中先后；初始 stop 后行情仍属于全 horizon 路径证据 |
| 唯一身份 | 原有 UNIQUE(signal_event_id)；首次 Signal 创建样本，重复 Observation 不再采样；冻结输入与新类型终态由数据库触发器保护 |
| 配额与覆盖 | PostgreSQL 独立 control，初始 disabled / daily_limit=0；控制行锁和样本/每日计数同事务。按策略/UTC 小时保存 admitted/skipped 聚合，不生成第二张逐 Signal 研究账本 |
| 重试 | 领取时持久化 attempt_count、last_attempted_at；最多四次，退避 1/5/15 分钟，horizon 后两小时截止。失败、缺根和崩溃重领都受上限约束；旧版失败样本通过尝试时间排序让出研究机会 |
| 调度 | 复用 A 的 scope/Shadow 处理机会、8 tick/2 秒批预算；研究串行、每次最多一请求，新类型请求上限5秒；Legacy 协议保留其旧超时口径 |
| 真实 Review | 精确 Signal → AdmissionDecision → Ticket → Aggregate.review_id → Review 联接，只读事务；路径每单位 R0 与 Ticket 冻结总 stop risk、有效 Review revision/metrics 分别呈现，缺失为 null |
| 迁移与发布工具 | 0011→0012 单一前向链；精确旧列/旧行保全、flat/quiescent 检查、新 control 默认关闭。发布 postflight 对照停机前精确 Universe 数与成员摘要，不固定假设8个 |

**价格路径不能转译成成交或模拟收益。** 参考价没有填入后来 Admission 的 bid/ask 或
实际 fill。已接纳和预算拒绝 Signal 共用前瞻研究口径；采集开启时，Entry 拒绝不会绕开
已耗尽的研究额度再插入旧协议样本。原有 pending/terminal Shadow 保留旧版本和价格口径。
旧协议失败仍按原规则释放租约，但不会持续压住未尝试的新样本。

样本跳过数是明确的覆盖缺失；没有 Ticket 或 Review 的 Signal 不伪造净收益。Owner
Regime 不进入本版；普通暂停/恢复不回填成历史 Regime。

## Schema 与持久化

`0012_generic_signal_path_v1` 扩展既有 Shadow 表，新增冻结参考/源码/摘要、固定 JSONB
阈值摘要、尝试时间和重试预算。单样本路径摘要限制在4KiB，不保存原始K线数组。
三个小型研究控制表分别保存当前开关、append-only 控制修订和按 UTC 日的额度/覆盖计数；
策略/小时维度最多5×24组。历史表、Signal/Ticket/Review身份和经济字段不重写。

保全校验读取的是现有官方部署路径的源版本清单，生产 Worker 不读旧 Schema，不使用
文件权威、fallback 或双写。历史0010源事实测试由精确已认证的0011源码在独立进程生成；
不让新仓库类尝试读取缺少研究表的旧库。该历史测试需要完整Git中的精确源提交，缺失明确
报错；普通 A 性能回归的浅克隆独立性不因此改变。

配置命令独立于 ENTRY/策略控制。以下是命令形状，**不是生产额度或启用授权**：

```bash
.venv/bin/python scripts/trading_kernel/configure_research_collection.py --show
.venv/bin/python scripts/trading_kernel/configure_research_collection.py \
  --expected-version <current-version> --daily-limit <Owner-approved-limit> \
  --enabled --owner-identity <Owner> --reason <approved-reason>
.venv/bin/python scripts/trading_kernel/read_signal_path.py --signal-event-id <exact-signal-id>
```

不带 `--enabled` 的控制修订暂停新研究采样和领取；已在途只读投影可结束，已存在的经济链
不受研究控制影响。`--show --day-start-ms <UTC-midnight-ms>` 读取指定日覆盖记录。
CLI 使用现有数据库环境变量、不输出连接信息，不配置或读取交易所凭据。

## 验证与资源影响

本地测试覆盖五策略冻结口径、多空首触/同根歧义、去重/额度并发、关闭后停止领取、
错误/缺根退避、老坏样本公平性、四次尝试终止、源码与指标保全、伪终态/冻结输入修改拒绝，
以及真实自然 Ticket 终态 Review 的只读关联。相关行为先观察 RED，再完成 GREEN。

A+B 合成积压使用真实常驻脚本的调度逻辑：106 个 scope、200 个研究任务和6次研究失败，
验证真实观察与研究均完成且scope P95受给定模拟预算约束。它不声称包含真实网络或CPU耗时。
独立真实PG测试验证一次24根投影、持久退避和无交易写入。

**最终代码的1CPU/1GiB 有界容器 smoke：6 passed，3.37s；容器峰值141.58MiB；OOM/OOM-kill为0。**
容器同时运行合成调度和真实PG定向研究测试；数据库在现有本机容器外。该短时结果不等于
四个生产Worker联合长期内存验收或Tokyo峰值保证。没有新增服务或修改生产资源额度。

初期生产额度仍待Owner批准；50/200/1000样本日是设计/压测场景。每成功样本通常一轮24根
只读行情请求，另计最多三次重试；日配额持久化，不能通过重启突破。原始路径仅驻留在单任务
内存中，最终摘要留存；不全量回补历史，不逐根写库，不引入通用常驻行情缓存。

正式候选应保留A全部回归。下面是本地开发验证记录，**不是一次完整Integration或联合R4**。
原始日志复制保留在本地忽略目录 `.local/alpha-02a-review-evidence/`，不作为运行权威。

| 验证范围 | 直接测量结果 | 原始日志文件名 |
| --- | --- | --- |
| 全部Unit与Architecture，最终重跑 | 1711 passed / 18.27s | brc-alpha-final-fast-freeze.log |
| 受影响的Integration模块 | 148 passed、1 failed / 308.35s；唯一失败为新迁移拒绝降级文案缺少fix-forward，已修复 | brc-alpha-final-broad-integration.log |
| 失败所在完整迁移模块重跑 | 22 passed / 41.65s | brc-alpha-final-observability-migration.log |
| 新研究Repository全16项、Domain全7项与上述失败节点 | 24 passed / 13.79s | brc-alpha-final-core-repair.log |
| Generic Selection并发、续期、Snapshot与0010保全切片 | 17 passed / 68.23s | brc-alpha-final-selection-slice.log |
| TradFi源版本升级加Domain重验 | 8 passed / 5.07s | brc-alpha-additional-source-check.log |
| 全部Full-chain | 58 passed / 88.46s | brc-alpha-final-fullchain2.log |
| 有效Review revision2与冻结Ticket risk后续断言 | 2 passed / 8.65s | brc-alpha-effective-review-final.log |
| 最终受限资源smoke | 6 passed / 3.37s；峰值148459520 bytes | brc-alpha-final-resource-smoke.log |
| 正式Mypy口径 | 199 source files PASS | brc-alpha-final-mypy-freeze.log |
| Ruff、运行阻断文件权威/高频写入审计、diff检查 | PASS | brc-alpha-final-ruff-freeze.log、brc-alpha-final-file-io-gates.json |

测试数包含不同轮次的重复节点，不累计成一次全套通过的数字。正式类型检查命令是
`.venv/bin/mypy src/trading_kernel scripts/trading_kernel`；此前未指定目标的全库Mypy
1398个既存错误属于不同口径，不能替代或否定本次199文件的PASS。
Unit/Architecture使用 `.venv/bin/python -m pytest tests/trading_kernel/unit tests/trading_kernel/architecture`；
Full-chain使用 `.venv/bin/python -m pytest tests/trading_kernel/full_chain`。
文件I/O门槛使用 `scripts/audit_production_runtime_file_io.py --max-blocking-cleanup-required 0 --max-frequent-report-write 0`。
额外全脚本 `--fail-on-risk` 严格扫描仍FAIL：未改动的一次性
`verify_sor_dynamic_selection_golden.py` 工具有1处报告写入；阻断运行文件权威与高频写入均为0。
该既存工具债务未扩入本轮，原始宽口径结果保留在 `brc-alpha-final-file-io.json`。
本分支未签署联合R4或生产验收，未执行24h soak；发布后效率与研究质量仍需各自测量。

## P1：集成测试耗时归因

先读既有 `2026-10-12-r4-certification-performance-amendment.md`，确认初始化模板、独立克隆、
移除重复迁移调用、流式输出和资源审计分层都已存在。本轮没有重做这些工作。

既存完整R3日志：1697 passed / 3545.68s；最慢30个 phase **均为Call**，合计249.96s，
约占总时长7.0%。这能定位慢场景，不能解释全部剩余55分钟。没有机器压力曲线，不能把
未归因时间冒称磁盘或数据库饱和。

对4个相同慢节点追加一次临时、未提交的pytest观测；不改测试/fixture与通过标准：

| 节点 | Setup | Call | Teardown | 父进程业务 SQL / 耗时 |
| --- | ---: | ---: | ---: | --- |
| CPM resident renewal | 2.92s冷模板 | 13.38s | 0.11s | 2187 / 1.13s |
| BRF2 resident renewal | 0.09s | 12.61s | 0.04s | 2187 / 1.04s |
| 22-member wrong-mode | <0.005s | 7.32s | <0.005s | 4585 / 2.84s |
| MPG unknown recovery | 0.09s | 8.62s | 0.05s | 9525 / 5.10s |

4 passed / 46.93s。SQL事件只覆盖父进程，独立Worker和迁移子进程不在该计数内；因此不能
把 Call减SQL 的差值全称为固定等待。冷模板Setup另有717条父进程SQL/0.28s，其余包含
迁移/克隆/独立进程/I/O。热模板Setup已很小；慢节点主要承担实际状态机、多次真实SQL、
进程启动和事件等待。未发现可直接删除且能可靠省15–20分钟的固定等待。

**结论：本轮不做提速补丁。** 已有充分局部证据表明继续缓存Setup不是显著收益的保证，
压缩完整故障链或并行化需要扩大隔离证明。保留完整Integration/R4、并发与迁移覆盖；
没有删测试、跳慢测试、全局xdist、提高资源配额或以45–60分钟作为发布门槛。
未来只在同范围前后测量证实收益时实施，不阻塞B交付。

## 最终边界

本分支交付后先审查，再决定合入dev。合入后的最终精确A+B候选需要正式分类、R4及其它
必要认证；生产部署与研究启用另行确认。Owner ENTRY、Dynamic Authority、策略算法、
资金、止损、TP1和Runner规则没有新增授权或参数变更。
