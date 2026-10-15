# OBS-EFFICIENCY-01 与 ALPHA-02A 实施设计

## 结论与范围

**本轮交付 Observation 效率补丁及 ALPHA-02A 设计，不部署、不启动通用研究采集。**
开发基线为 `origin/dev` 的 `de73f2791a01a14ba77e842da0a3ecadbdbc1069`。
当前生产身份仍只由 [主路线图](../../current/MAIN_CONTROL_ROADMAP.md) 管理。

**建议分开发版**：效率补丁无迁移；ALPHA-02A 涉及 Shadow 冻结输入、指标语义、额度和
Schema 变更，需单独实现、验收与停止/平仓/前向迁移门槛。将两者合并会使调度收益和
研究负载无法分辨，也扩大审查范围。本轮无发布授权。

## 已知事实与根因

1. **固定等待是可证明的排队成本**：现有 Observation 每次最多处理一个 scope，之后等待
   5 秒；106 个同时到期 scope，仅相邻任务间等待就有 105×5=525 秒。真实延迟还包括
   网络、CPU、数据库和其他逻辑循环，不能把它们全部归因于轮询。
2. **Shadow 缺少繁忙期执行机会**：旧实现只有 scope 领取为空时才领取 Shadow；持续
   scope 积压可以造成研究饥饿。
3. **重复协调仍有必要的权限校验**：Generic ACTIVE 分支检查 Owner、Control、当前
   Authority、数据库时钟、Universe，不能跳过。它之前的 Continuity 和 Snapshot 转发
   对精确同一 ACTIVE Generation 是重复工作。首次激活、未完成 Generation、Vacuum、
   pending mode 仍走原路径。
4. **日志分类混淆**：首次 ACTIVE_NEW 和已经提交的 ACTIVE_NEW 都曾映射为 advanced；
   已消费 Close 属于等待下一合法机会，不能再按每两秒错误输出。认证异常仍保持 blocked。

来源：本基线 `interfaces/observation_worker.py`、`interfaces/worker_process.py`、
`interfaces/selection_runtime_worker.py`、`application/coordinate_selection_materialization.py`，
以及 [10 月 15 日历史容量调查](2026-10-15-tokyo-resource-capacity-assessment.md)。历史调查
不是本轮生产测量；本轮未连接 Tokyo 或交易所。

## OBS-EFFICIENCY-01 改动

### Materialization

- 在已有“确实已经提交”的返回点增加 `TERMINAL_AUTHORITY_ALREADY_COMMITTED`，映射为
  `unchanged`；首次激活仍为 `advanced`。Static、Generic NO_CHANGE、连续性和 SOR
  已提交结果沿用相同表达。
- 已暂停且本轮无需清理/推进的结果用 `OWNER_PAUSED_NO_CHANGE`。真正创建暂停 Authority、
  放弃 Generation、执行 drain 的结果仍保留进展；错误及认证异常不纳入 idle。
- `GENERIC_CURRENT_CLOSE_ALREADY_CONSUMED` 的应用 disposition 保持原样；worker 将它
  归入 waiting，下一次仍重读数据库，不缓存关闭时间或授权事实。
- 对 ready Job 的精确 ACTIVE Generation，在无 unfinished Generation、Vacuum、pending
  mode 时直接进入 Generation 协调。内部仍重新校验权限；与 Owner 操作竞态时不能获得
  新权限。没有新增 Repository 查询语义、SQL 写入或锁顺序。
- 常驻进程仅节流**完全相同**的 idle payload；首次、身份/原因变化、错误后恢复立即记录。
  每个逻辑循环只保留上一个 payload，不保存授权缓存。

### Observation 调度

- 仅 Observation 循环在 `observed` 或 `shadow_completed` 后连续处理。
  每批最多 **8 次**，经过 **2,000ms** 后不再继续新 tick；批内每次 `asyncio.sleep(0)`
  让出事件循环，批末恢复原有 5 秒等待。
- 2 秒是**启动下一 tick 的预算**，不是中断事务/请求的硬截止；单个任务继续受既有请求
  timeout 和 Lease 约束。慢任务最多让这一批超出一个 tick 的时间，数据库阻塞仍依赖
  既有数据库超时配置。本轮不声称任何硬实时 SLA。
- 真实 scope 累计处理 8 次后，下次先尝试一个 Shadow；无研究任务时立即回到原 scope
  selector，不重复执行第二次 Shadow 空查询。研究失败返回原重试结果，恢复正常等待。
- 所有领取仍调用原 Repository 的排序、`SKIP LOCKED`、Lease 和版本校验；无并行预领取、
  无无限循环、无新服务、无 systemd/CPU/内存配置变化。
- scope 的 `retry_scheduled`、`superseded`、Shadow 重试以及异常均不触发连续处理。
  一次性 CLI 默认行为保持原先“一任务”的语义。

## 验证与可复现性能证据

### 调度对比（本地虚拟时钟，不是生产性能）

相同 106 个 scope 和 12 个 Shadow 同时到期；无新增任务；耗时为每 tick 固定输入，
使用真实常驻循环及实际脚本的公平性计数，数据库/行情服务以确定性队列替代。
P50/P95 使用 nearest-rank，计入排队与任务耗时；所有时间单位秒。

| 情景 | scope P50 | scope P95 | scope 最后完成 | 首个 Shadow | Shadow P95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 基线，100ms/tick | 265.3 | 510.1 | 535.6 | 540.7 | 596.8 |
| 补丁，100ms/tick | 40.9 | 81.3 | 81.8 | 5.9 | 75.8 |
| 基线，1500ms/tick | 339.5 | 651.5 | 684.0 | 690.5 | 762.0 |
| 补丁，1500ms/tick | 233.5 | 449.5 | 467.0 | 33.5 | 427.0 |

每种情景共 121 次任务调用（118 个任务、3 次空轮询），空闲等待均保留 5 秒，
没有用减少任务、跳过失败或删去 Shadow 来制造收益。慢场景因时间上限生效，收益较小。
该基准不能推导 CPU 百分比、真实 K 线 API 速率或东京 P95。

### PostgreSQL 与日志

使用正式 Selector、物化、激活路径创建 CPM ACTIVE 状态，再对同一数据库运行基线和
补丁 worker 各 5 次。SQLAlchemy `before_cursor_execute` 计数包括实际 SELECT/锁语句，
不包括协议级 BEGIN/COMMIT；测量区间无 INSERT/UPDATE/DELETE。

| 指标 | 基线 | 补丁 | 解释 |
| --- | ---: | ---: | --- |
| 5 tick 顶层协调调用 | 10 | 5 | 省去重复 Continuity 调度 |
| 5 tick 实际 SQL 语句 | 220 | 130 | 减少 40.9%，保留 Generation 内所有校验 |
| 150 次相同终态检查日志 | 150 | 2 | 首次进展、首次重复确认；随后 300 秒 heartbeat |

SQL 结果只代表**精确 ACTIVE 快路**，不外推到所有状态。额外精确 Generation 探测可能
为无 Generation 的 ready Job 增加一次读查询；不对恢复、首次接管或已消费 Close 的
数据库成本作未经测试的减幅承诺。日志基准为单组件合成状态序列，不是历史 821 条的重放。

复现命令（仓库 `.venv`，默认本地 disposable PostgreSQL）：

```bash
.venv/bin/pytest -q -s tests/trading_kernel/unit/test_observation_efficiency.py
.venv/bin/pytest -q -s tests/trading_kernel/integration/test_generic_selection_snapshot_repository.py -k efficiency
.venv/bin/pytest -q tests/trading_kernel/integration/test_shadow_outcome_projection.py -k fair_shadow
```

基线 loader 只在测试中读取上述精确 Git commit；两版使用相同数据库和当前未变更的
Repository/Schema。基线 coordinator 同时加载，避免将新 reason code 混入旧版本。
生产模块不读取 Git、文件或测试报告。

### 验证范围与限制

- 新行为先运行失败测试：idle 身份/恢复日志、批次次数/时间限制、Shadow 优先领取、
  ACTIVE 路由；随后实现并转绿。
- 单元和架构、实际 OS SIGTERM、首次激活/重启、同 Close 并发、现有 Observation/Shadow、
  SOR 物化回归；新增真实 PostgreSQL 研究 Claim 排他、网络异常/超时重试。
- CPU/内存压力和远端 API 限流的生产收益仍未实测；没有新增并发，但串行批次会改变
  短时请求密度。发布前需精确候选认证，发布后另行比较同等负载下的延迟/请求/资源指标。
- 当前 Shadow 最老样本持续缺数据可能阻塞其他研究样本；本轮解决的是 scope 对研究类别
  的饥饿。单样本 retry/backoff/终止期限列入 ALPHA-02A Schema 设计，不在本轮偷改。
- 全库类型检查及最终测试计数记录于本文末尾；未通过的门槛不包装成发布认证。

## ALPHA-02A：待实施设计

**以下是设计决策与待批准预算，不是现有能力或生产配置。**
复用 `domain/shadow_outcome.py`、`application/project_shadow_outcome.py`、
`interfaces/observation_worker.py` 和现有 PostgreSQL 表；不新增研究 Worker、交易账本、
历史全量 K 线回补或模拟成交。

### 统一冻结口径与身份

**采用 Signal 收盘价口径**：在 `observe_strategy_scope` 已得到有效 detector 结果、
通过 ingest 校验并持久化 Signal 的同一事务内，使用本次已取得的精确触发封闭 K 线 close
冻结 `entry_reference_price`。不额外拉报价，不把后来 Admission 的 ask/bid、实际成交价
或后续价格倒填成信号时刻参考价。Signal 模型当前没有通用 close 字段，因此把价格与
`reference_at_ms`、`price_basis=signal_closed_bar`、K 线来源/digest 写入 Shadow 冻结输入，
不修改 detector 条件或 Signal 经济语义。

- `initial_stop_price` 取 Signal 中唯一且符合 Registry 的 protection_reference；
  Decimal 风险单位 `R0 = abs(reference - original_stop)`，校验 long stop<reference、
  short stop>reference。缺失、方向不合法或 R0=0 生成显式 unavailable 原因，不伪造数值。
- `horizon_start_ms=signal.occurred_at_ms`，只观察之后完整封闭 K 线；`observed_at_ms`
  单独保留用于量化调度迟到，不以实际处理时刻延长 horizon。
- `path_spec_digest` 冻结 Signal ID/fact digest、评估版本、参考价/原始 stop、周期、
  horizon、价格源及阈值。唯一身份仍为 `signal_event_id`；新 Shadow ID 从 Signal ID
  确定性构造，禁止以 horizon 或版本为理由为同一 Signal 新增第二个 Outcome。
- Entry 是否接纳不影响样本身份。只读关联 AdmissionDecision 得到 admitted/rejected/
  pending 等标签；只纳入有效 Signal，不把无 Signal 的 readiness failure 当作机会。

| 策略 | Registry 观察周期/根数 | 原始 stop fact | 设计 horizon |
| --- | --- | --- | --- |
| CPM-RO-001 | 1h / 24 | pullback_low_reference | Signal close + 24 根 |
| MPG-001 | 1h / 24 | momentum_floor_reference | 同上 |
| MI-001 | 1h / 24 | impulse_invalidation_reference | 同上 |
| BRF2-001 | 1h / 24 | rally_high_reference | 同上 |
| SOR-1H-001 LONG/SHORT | 1h / 24 | opening_range_low/high_reference_1h_v1 | 同上；Session exit 另作标签 |

来源：`domain/strategy_registry.py` 当前 event contract。**24 根是当前 Registry 的
shadow_horizon_bars 事实，但启用五策略通用采集仍待本设计实现和授权**。SOR-1H 的
路径 horizon 不自动截断为实际 Session/TimeStop；持续观察潜在右尾，不能解释为能够
继续持仓。SOR-US 现有 15m/8 根且受 Session 截断的协议保持独立版本，不并入五策略样本。

### MFE、MAE 与首触

1. 对完整 `[start+interval, end]` 封闭序列一次投影：long 的 MFE=max(0,max(high)-P)/R0、
   MAE=max(0,P-min(low))/R0；short 反向。记录正数幅度、极值价与所处 K 线 close 时间。
2. +1R/+3R/+5R 和原始 stop 分别保存首次触及 bar 的 close 时间，未触及为 null；不把
   OHLC close 时间宣称为真实成交/盘中触及时间。每一阈值与 stop 比较为 threshold_first、
   stop_first、same_bar_ambiguous、neither；同根双触不臆测先后。
3. 阈值可以在初始 stop 已触及之后达到，仍记录全 horizon MFE/MAE；另列 stop 前证据与
   首触顺序。不可将 stop 后 MFE 当作本次交易可获收益。
4. 缺根、重复、乱序、越界、未封闭根沿用完整性校验；部分窗口不能标 completed。
   超过重试/补取期限后 unavailable，保留原因和 coverage，不能把缺根当零波动。
5. SOR-US 的 OR failure/TimeStop/Session exit 投影保留其版本；通用投影只共用 Candle
   完整性、Decimal excursion 与首触基础计算，不复制交易退出状态机。

### 已接纳、被拒与旧样本

- 新功能生效后，五策略合法 Signal 在同一 Signal 事务插入通用 path，沿用
  `UNIQUE(signal_event_id)` 与 `ON CONFLICT` 幂等边界。重复观察/双 worker/重启均只有一行。
- 新被拒 Signal 的已有 rejection hook 必须显式识别新协议已有样本，仅验证身份、不覆盖
  冻结输入。AdmissionDecision 的拒绝原因和预算快照只读关联；不把“忽略冲突”当成可以
  接受输入漂移，发现不同 path digest 应报告冲突。
- 历史 `fixed_horizon_excursion_v1` 的价格来自拒绝时 ask/bid，与新 Signal close 不同；
  **保持原值、版本与 horizon**。已完成旧样本可展示已有 MFE/MAE，缺失阈值标 unknown，
  不重写终态、不追加第二个 Outcome、不为补齐指标全量回补。
- 对切换前仍 pending 的旧样本继续原版本投影。研究报表按 evaluation_kind/price_basis/
  策略版本分层；不跨口径合并胜率。新的 admitted/rejected 同属新口径，支持前瞻比较。
- 历史/当前资格仍受现有信号与 Registry 合同约束；不扩大拒绝类型以制造样本。

### Signal → Path → Ticket → Review

通过 `signal_event_id` 关联 AdmissionDecision 的 `ticket_id`，再精确读取 Ticket 和
当前有效 Review revision。导出记录 source commit、窗口、版本、cutoff、有效 Review
revision 和缺失经济字段；没有 Ticket 或 Review 时显式 null，不补零。

MFE/MAE 是**价格路径证据**；真实 net R、费用、funding、TP1/Runner 收益来自正式 Review。
Path R0 与 Ticket 的冻结初始风险分别显示，禁止混用分母或由价格阈值生成模拟成交收益。
已完成 Path 与尚未完成 Ticket 可以并存，后续只读关联无需重写 Path。
收益评价仍遵循 [策略实验评估合同](../../current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md)。

### 有界负载、重试与保留

- 沿用本补丁的 8 个 scope 后一个研究机会和总批次预算；单个研究 Claim 串行，行情 I/O
  在事务外，默认一次请求读取冻结窗口，终态一次更新。MVP 不逐根持久化，不保证“零新增 API”。
- 新增持久化 `next_attempt_at_ms`、`attempt_count` 和 `retry_deadline_ms`；失败按退避到期
  重新排序，不立即占据最老样本队首。期限耗尽终态 unavailable，恢复/重启不清空计数。
- 拟议初期研究请求 timeout=5s、每样本最多4次尝试（首次及3次重试）、重试间隔1/5/15分钟、horizon 后最长2小时
  补取窗口；租约需大于单次请求及 DB 收尾预算。具体值须在实现验收后冻结，不能由本设计
  静默成为生产默认值。TTL 到期只影响研究，不改变 ENTRY。
- **50 样本/日**仅作容量情景，另以 200/1000 做离线压力测试。实际样本创建额度必须在
  PostgreSQL 中持久化、跨重启有效。若触顶，记录按策略/小时聚合的 skipped_budget 数，
  报表披露缺失与按时间截断偏差；不报告“覆盖全部信号”。正式上限尚未批准。
- 行情限制由共享 client 的现有限流与研究请求预算共同控制，研究最多一个在途请求；
  可按 exact instrument/timeframe/horizon 做批内有界复用，但不建立常驻全市场缓存。
- 最终摘要长期保留并通过小规模试运行测量真实字节/行；原始 K 线不落库，内存投影后释放。
  重试错误仅存计数/最后类型；拟议明细诊断保留30天。终态摘要删除或归档需另定 retention
  合同，不能删除 Signal/Admission/Ticket/Review 以回收研究空间。
- 监测 due backlog、oldest_due_age、完成延迟、请求数/超时、unavailable/skipped 数；指标
  进入既有日志/状态输出，不产生周期 JSON/Markdown 文件，不新设监控服务。

### Schema 与预计改动范围

| 范围 | 可复用 | 必须改变 |
| --- | --- | --- |
| domain/shadow_outcome.py | Spec/Claim/Projection、Decimal、完整序列校验 | 新 generic_signal_path_v1，冻结 reference/source/digest，固定阈值结果模型 |
| application/project_shadow_outcome.py | 终态投影与不可用处理 | 通用 spec builder、typed evaluator 分派、版本冲突检查 |
| application/observe_strategy_scope.py | 正式 Signal 事务、已有 Candle | 在成功 ingest 后原子插入研究样本与额度检查 |
| application/issue_ready_signal.py | AdmissionDecision 单一事实链 | rejection hook 识别同 Signal 通用样本；不改准入结果 |
| interfaces/observation_worker.py | 有界、公平、串行 Claim 与 timeout | 研究专用重试预算；不得重复建立调度进程 |
| pg_models.py / pg_repositories.py / ports.py | shadow_outcomes_current、Signal UNIQUE、Lease token/version | 扩展 kind/source/shape check、结果与 provenance 列、retry 选择器 |
| migrations/trading_kernel | 单一前向迁移链 | 新迁移保留所有旧样本；到期索引加入 next_attempt；持久研究额度/遗漏计数 |
| 只读研究查询/导出 | Signal/Ticket/Review 精确关联 | 新字段、缺失/版本分层、样本覆盖计数 |

通用阈值摘要可用有固定 key/类型约束的 JSONB 列，禁止无限路径数组。现有列/check constraints
不能直接容纳 generic kind 与 nullable Admission；需要新迁移，**不能只改 Pydantic**。
研究额度可使用一张小型按日/策略计数表（仅研究负载，不是资金/交易账本），其更新与插入样本
同事务，重复 Signal 不重复扣额度。旧行新字段允许 legacy-null，历史身份/值保持不变；新 kind
严格验证。这是数据保留迁移，不添加旧 Schema runtime reader 或双写。

### 实施顺序与验收

1. 冻结 v1 口径、typed models、side/阈值/同根歧义/完整性纯函数测试。
2. 前向迁移与真实 PostgreSQL 去重、重启、并发 Claim、额度及旧行 preservation 回归。
3. 在官方 Signal 事务创建一个 Path，连接 rejection hook；记录 admitted/rejected 共有
   Signal close 口径，零新 Ticket/Command/venue mutation。
4. 接入研究 retry/backoff 与只读 Review 联接，压力下验证 scope 和研究双向有界进展；
   单个坏样本不能阻塞其他研究样本。测试 source timeout、DB failure、lease loss、进程重启。
5. 精确 release candidate 全套认证及单独发布审批。无历史全量回补。

**Owner Regime 不进入 MVP**：普通 Pause/Resume 不能还原完整市场方向/作用域/有效时间
Journal。未来真实 Gate 存在时，新增冻结 gate ID/version 或显式 absent 标签，在当时的
Admission/Signal 边界产生；不能用当前 Owner 状态回填历史样本，也不修改 Review 经济。

## 最终本地验证记录

以下均为本地结果；没有执行全套 Release 认证或生产验收。

| 检查 | 结果 | 可复现命令/范围 |
| --- | --- | --- |
| Unit + Architecture | 1,697 passed | `.venv/bin/pytest -q tests/trading_kernel/unit tests/trading_kernel/architecture` |
| 定向集成 | 167 passed | 下方完整命令；含实际 PostgreSQL |
| 新增 Shadow 并发/timeout/network | 3 passed | `test_shadow_outcome_projection.py -k fair_shadow` |
| ACTIVE SQL/到期/Owner 变化复核 | 1 passed | `test_generic_selection_snapshot_repository.py -k efficiency` |
| 已暂停 SOR 无变化分类 | 1 passed | `test_selection_materialization_repository.py -k owner_pause_opens_durable` |
| Full-chain | 58 passed | `.venv/bin/pytest -q tests/trading_kernel/full_chain` |
| Ruff | PASS | `.venv/bin/ruff check src/trading_kernel tests/trading_kernel scripts/trading_kernel` |
| Mypy（全库） | FAIL：1,398 个既存错误，72 文件；本轮新增0 | `.venv/bin/mypy`；与隔离导出的精确基线归一化行号后逐条比较 |
| 文件 I/O 审计 | PASS，118 occurrences，suspicious=0，frequent_report_write=0 | `.venv/bin/python scripts/audit_production_runtime_file_io.py` |
| Diff | PASS | `git diff --check` |

```bash
.venv/bin/pytest -q \
  tests/trading_kernel/integration/test_observation_to_signal.py \
  tests/trading_kernel/integration/test_shadow_outcome_projection.py \
  tests/trading_kernel/integration/test_selection_materialization_repository.py \
  tests/trading_kernel/integration/test_generic_selection_snapshot_repository.py \
  -k 'not resource and not owner_staged_runner and (observation or shadow or materialization or same_close or activation_commits or continuity_is_replaced or paused_failed_selection or efficiency)'
```

167 项集成运行早于最后补充的 Shadow 三项和日志分类断言；随后相关定向复核独立通过，
不把重跑数量累加为不重复测试数。最终 Unit/Architecture 覆盖最后的认证日志分类变更。
Mypy 的既存测试类型债务是发布门槛的明确限制；本轮没有弱化类型检查或修改无关测试消除数字。
未新增服务、未改 CPU/内存/策略/预算/退出参数、未迁移生产、未执行交易所写操作。
