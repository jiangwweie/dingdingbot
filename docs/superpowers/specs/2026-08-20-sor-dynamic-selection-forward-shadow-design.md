---
title: SOR_DYNAMIC_SELECTION_FORWARD_SHADOW_DESIGN
status: SUPERSEDED
date: 2026-08-20
phase: P3-X.2
research_spec_id: sor-dynamic-selection-v0
forward_protocol_id: sor-dynamic-selection-forward-shadow-v0
implementation_authority: NONE
production_authority: NONE
superseded_by: 2026-08-20-sor-dynamic-instrument-selection-trading-v0-design.md
---

# SOR Dynamic Selection Forward Shadow Detailed Design

## Superseded Notice

**本路线已被 Owner 决策淘汰，不再实施。** Historical Replay 通过后，当前路线直接进入
PostgreSQL 权威的 **SOR Dynamic Instrument Selection & Trading V0** 生产设计。本文件只保留
为设计演进记录，不授权 CLI、外部 evidence store、W30/W60 gate、独立 Forward scheduler
或任何实现动作。

替代设计：

```text
2026-08-20-sor-dynamic-instrument-selection-trading-v0-design.md
```

## 1. Decision

本设计冻结一个 **SOR Dynamic Selection V0 Forward Shadow**，用于把已经通过 Historical
Replay 的选择规则转化为真正的 **Prospective Evidence**：每天在任何 SOR Trigger
发生前，事先冻结完整 SelectionSnapshot，随后只读观察同一批 Instrument 的真实未来
SOR v4 路径。

```text
UTC 01:00 closed-market cutoff
-> immutable SelectionSnapshot
-> Dynamic / Static / Random / Near / Not Selected controls
-> prospective exact SOR Event and Path Outcome
-> append-only Outcome revision
-> Forward Decision Ledger
-> Advance / Extend / Revise / Stop
```

Forward Shadow 不建设生产 Selector，不修改 Active StrategyUniverse，不恢复 Crypto
**`SOR-001`**，不产生 StrategySignal、AdmissionDecision、CapacityClaim、Ticket、Exchange
Command、Position、Settlement、Review 或模拟 PnL。

本设计的架构决策是：

> 使用一个 **仓库外、只读市场数据、追加式证据的独立研究 CLI**，由外部调度触发；
> 第一阶段不进入 Observation、Entry、Lifecycle 或 Reconciliation Worker，不写生产
> PostgreSQL，不初始化 private Venue client，也不部署 Tokyo 全市场 Research Worker。

本文件只授权外部复核，不授权编码、调度、部署或生产 Apply。

## 2. Known Facts

### 2.1 V0 Quantitative Replay result

Owner 提供的独立 Replay 已按冻结 V0 设计完成，正式结论是：

```text
ADVANCE_TO_FORWARD_SHADOW
```

| Evidence | Dynamic | Control / comparison | Result |
| --- | ---: | ---: | ---: |
| Tail3 / 100 directional slot-days | **9.841** | Static **7.931** | **+24.1%** |
| Random envelope | **9.841** | Median **7.975** / P75 **8.117** / Max **8.384** | Dynamic above all 100 |
| Selection gradient | Selected **9.841** | Near **8.295** / Not Selected **6.177** | Ordered |
| Complete 90-day blocks | — | — | **9 / 10** positive |
| LONG lift | — | Static | **+19.0%** |
| SHORT lift | — | Static | **+29.0%** |
| Tail3 / Trigger | **11.76%** | Static **9.78%** | **+20.2%** |
| Dynamic-exclusive Tail3 | **874** | **17** non-Static Instruments | Broad contribution |
| Largest Instrument share | **8.6%** | Gate **50%** | Passed |
| Selection-ready coverage | Min **14** / Max **24** | EMPTY **0** | Passed |

该结果证明的是固定 24-symbol Panel 内、事前可计算的 V0 Policy 在历史路径上具有选择
能力；它不证明真实净收益、未来稳定性或生产 Apply 安全性。

来源：Owner 提供的独立 Replay `REPORT.md`，SHA-256
`de8edc672552097ad6f9e3988e08254f75b46d33433ad2cd12fd1e56de59a298`；
`2026-08-20-sor-dynamic-selection-research-v0-design.md`。

### 2.2 V0 current gate state

当前阶段必须精确表述为：

| Gate | State |
| --- | --- |
| V0 Quantitative Replay | **PASS** |
| Forward Shadow detailed design | **READY FOR OWNER REVIEW** |
| V0 internal engineering certification | **OPEN** |
| Forward Shadow implementation | **NOT AUTHORIZED** |
| Production Apply | **NOT AUTHORIZED** |
| Crypto `SOR-001` resume | **NOT AUTHORIZED** |

`REPORT.md` 是结果摘要，不包含实现 Golden Parity 所需的完整成员级 Artifact。因此它足以
启动本设计，不足以单独认证 Forward 实现。

### 2.3 Current SOR code semantics

当前 tracked code 已确认：

1. Crypto SOR v4 使用四根 15m K 线形成 UTC Opening Range；
2. Trigger 由 closed-candle close-cross 形成；
3. Long Stop 为 OR Low，Short Stop 为 OR High；
4. Registry 使用 `episode_policy=session_reference`；
5. EventSpec `shadow_horizon_bars=96`；
6. pre-TP1 reclaim 与 Session exit reference 均由 Registry Fact 定义；
7. `evaluate_strategy_snapshot()` 是 Detector 的公共 Live/Replay 边界。

来源：`src/trading_kernel/domain/detectors/sor.py`、
`src/trading_kernel/domain/strategy_registry.py`、
`src/trading_kernel/application/produce_strategy_signal.py`、
`src/trading_kernel/domain/exit_policy.py`。

### 2.4 Existing Shadow Outcome boundary

当前 `ShadowOutcomeSpec` 必须拥有 `signal_event_id`，来源为 portfolio rejection 或
strategy observation。现有 `pending_shadow_spec_for_strategy_observation()` 也只为
TradFi `SOR-US-EQ-PERP-001` 创建 Signal-owned Observation。

现有 `evaluate_sor_path_observation()` 还包含 TradFi M5 的 **8-bar** time-stop 评价边界，
不能被直接复用成 Crypto SOR v4 的 **96-bar** Forward Endpoint。Forward 可以复用 official
Detector 和纯市场模型，但必须按冻结 V0 Outcome Contract 独立认证 Path 语义。

因此现有 Shadow Outcome 不能直接作为 Dynamic Selection Forward Evidence：

1. SelectionSnapshot 在 Signal 前产生；
2. 未选 Instrument 可能永远没有正式 Signal；
3. Dynamic、Static、Random、Near 和 Not Selected 是 Selection-owned cohort；
4. Forward V0 需要 `+3R / +5R`、完整分母和跨 Policy 比较，而不是模拟 Ticket。

来源：`src/trading_kernel/domain/shadow_outcome.py`、
`src/trading_kernel/application/project_shadow_outcome.py`。

## 3. Analysis And Evidence Claim

### 3.1 Primary Forward hypothesis

Forward V0 只检验一个已冻结假设：

> 在固定 24-symbol Panel 中，每天 UTC 01:00 使用相同的 Point-in-Time 数据资格、
> `20M USDT` Activity floor 和 `pre_or_width_atr14` 升序排名选择 7 个 Instrument，
> 是否继续比 Static、Random 和未选集合提供更高的 SOR policy-qualified `+3R` 机会密度。

Forward 期间禁止修改 Candidate Panel、Feature、Activity floor、Top N、排序、对照、
Outcome 口径或 Decision Gate。

### 3.2 Evidence class

| Evidence | Meaning | Allowed claim |
| --- | --- | --- |
| Historical Replay | Development Evidence | 规则在历史上有解释力 |
| Forward Shadow | Prospective Path Evidence | 冻结规则在未来路径上是否保持方向 |
| Small-capital Apply | Real execution evidence | 真实 Fill、费用、Funding、生命周期和 Net R |

Forward Shadow 的 Endpoint 仍是 **Tail Opportunity Supply**，不是可实现收益。即使 Forward
通过，也只能进入独立的 Small-capital Apply 设计，不能直接恢复真实 ENTRY。

### 3.3 No statistical-proof claim

首个 Forward 窗口只有 30–60 个 Session，本设计不要求传统显著性检验，也不把它称为
机构级因果证明。当前目标是用低成本、事前冻结的证据排除以下高风险解释：

- Historical lift 主要来自未来信息泄漏；
- Historical lift 主要来自实现或数据版本差异；
- V0 在未来立即失去方向；
- Dynamic 只增加低质量 Trigger；
- Combined 改善掩盖单方向明显恶化；
- 选择梯度在未来完全倒置。

## 4. Scope

### 4.1 In scope

- Crypto `SOR-001` v4 LONG 与 SHORT；
- 冻结 24-symbol Research Panel；
- 每天 UTC 01:00 的事前 SelectionSnapshot；
- Binance USDⓈ-M public market facts；
- V0 exact Qualification、Feature、排名和 Cohort；
- Dynamic 7、Static 7、Random 0–99、Near、Not Selected、All Selection-ready 和
  All Panel Diagnostic；
- exact SOR first natural Trigger；
- Signal-basis formal Stop、TP1、Reclaim、Session expiry、`+3R / +5R`、MFE/MAE 和
  first-passage diagnostics；
- 30-Session 与最多 60-Session 的 Forward Decision；
- 运行时延迟、数据缺口、Source drift、重复执行和 Artifact 完整性证据。

### 4.2 Explicitly out of scope

- 修改 Active StrategyUniverse；
- Crypto `SOR-001` pause/resume；
- Policy、风险、杠杆、保证金、并发或资金变更；
- Ticket、Command、模拟成交、费用、Funding、Slippage 或 Net PnL；
- 生产 PostgreSQL Schema 或 Migration；
- Owner API、前端页面或通用 Selector Service；
- 新增第五个 Kernel Worker；
- systemd timer 或 timer-based Kernel cold start；
- 全市场 Collector、Research Registry、Feature Store、机器学习或综合 Score；
- CPM、BRF2、MPG、MI 或 TradFi SOR；
- 观察结果后调整 V0 阈值；
- 把事后补算的 Snapshot 冒充 ON_TIME prospective evidence。

## 5. Architecture Decision

### 5.1 Options considered

| Option | Identity fit | Production isolation | Cost | Decision |
| --- | --- | --- | --- | --- |
| 扩展现有 PostgreSQL Shadow Outcome | 差：Signal-owned，Selection 在 Signal 前 | 中 | 高，需 Schema/Worker | Reject for V0 |
| 加入 Observation Worker | 可实现 | 差：研究 cadence 进入 Kernel | 中 | Reject for V0 |
| Tokyo 新 Research Worker / timer | 可实现 | 差：新增生产运行概念 | 高 | Reject |
| 本地 Notebook 手工每天运行 | 弱：时钟、幂等和审计不足 | 高 | 低 | Reject as evidence path |
| 独立只读 CLI + 外部调度 + append-only artifacts | 强 | **高** | **低** | **Adopt** |

### 5.2 Adopted boundary

```text
External Scheduler
        |
        v
Read-only Forward CLI
        |
        +-> Binance public market data
        +-> current tracked SOR detector import
        +-> pure Selection / Outcome evaluation
        +-> repository-external append-only evidence store

No PostgreSQL
No private Venue client
No Exchange write
No Kernel Worker ownership
No StrategyUniverse mutation
```

### 5.3 Logical components

实施应保持一个小型、可删除的研究包，不建设平台。逻辑组件为：

| Component | Responsibility | Forbidden responsibility |
| --- | --- | --- |
| `SelectionSpec` | 冻结 V0 参数与 digest | 读取 Outcome 后改规则 |
| `SelectionCore` | 纯计算 Qualification、Feature、Rank、Cohort | 网络、文件、DB |
| `PublicMarketSource` | Binance public time/Kline/product facts | API key、签名、下单 |
| `SelectionRunner` | 截止时间、重试、Snapshot 原子提交 | 生产策略切换 |
| `SorForwardEvaluator` | official Detector Trigger + frozen path endpoint | 模拟 Fill/PnL |
| `EvidenceStore` | write-once Snapshot、Outcome revision、digest chain | 运行时权威 |
| `ForwardSummarizer` | 有界聚合、Checkpoint Decision | 修改历史 Artifact |

研究实现不得放入 `src/trading_kernel` 的生产执行路径。建议后续执行文档将代码放在
`scripts/research/sor_dynamic_selection/`，测试放在
`tests/research/sor_dynamic_selection/`；最终精确文件清单由执行文档拥有。

## 6. Authority And Identity

### 6.1 Authority table

| Concern | Single authority |
| --- | --- |
| SOR Trigger semantics | Current tracked `SORDetector` / `evaluate_strategy_snapshot()` |
| StrategyVersion、EventSpec、Fact role | Current tracked Strategy Registry |
| Forward Selection rule | Frozen `selection_spec.json` + exact digest |
| Forward Protocol | Frozen `forward_protocol.json` + exact digest |
| Point-in-Time market input | Binance public response captured before cutoff deadline |
| Selection membership | First valid immutable SelectionSnapshot |
| Outcome | Append-only latest valid Outcome revision |
| Forward Decision | Derived Decision Ledger entry over immutable evidence |
| Production Universe、Policy、Ticket | Existing PostgreSQL / Kernel authority; unchanged |

Markdown、JSON、CSV、Parquet、cache 和 Forward artifacts 都是研究证据，不是生产运行时
事实来源。

### 6.2 Frozen identities

| Identity | Rule |
| --- | --- |
| Research spec | `sor-dynamic-selection-v0` |
| Forward protocol | `sor-dynamic-selection-forward-shadow-v0` |
| StrategyGroup | `SOR-001` |
| StrategyVersion | `sgv:SOR-001:v4` |
| Long EventSpec | `event_spec:SOR-001:SOR-LONG:v4` |
| Short EventSpec | `event_spec:SOR-001:SOR-SHORT:v4` |
| Session timezone | UTC |
| Snapshot ID | `selection:sor-dynamic-selection-v0:<session_start_ms>` |
| Member ID | `<snapshot_id>:<exchange_instrument_id>` |
| Outcome ID | `<snapshot_id>:<exchange_instrument_id>:<side>` |
| Execution epoch | `<protocol_id>:<activation_utc>:<host_fingerprint>` |

LONG 与 SHORT 共用一个 SelectionSnapshot，但拥有独立 Outcome。

### 6.3 Exact source identity

Activation Manifest 必须冻结：

- exact Git commit；
- Selection implementation digest；
- Forward evaluator digest；
- `sor.py` digest；
- Strategy Registry digest；
- Exit Policy digest；
- `selection_spec.json` digest；
- `forward_protocol.json` digest；
- Python 与 dependency versions；
- public endpoint base URL；
- evidence root canonical path label；
- scheduler/host fingerprint。

任一 source digest 漂移时，后续 Session 必须标记 `SOURCE_DRIFT` 并停止产生 Primary
Evidence，直到创建新的认证 Execution Epoch。不得静默继续。

Git commit 变化但 Selection、Forward evaluator、SOR Detector、Registry/Exit Policy
相关 slice 与 Spec digest 完全不变时，可经机械认证创建 `SOURCE_REBASE_ONLY` Execution
Epoch，前后 Evidence 仍可合并。若 Relevant Source digest 变化：

1. 证明行为和 Golden 输出完全相同时，只能在新 Epoch 下继续；
2. SOR EventSpec、Selection 或 Outcome 语义发生变化时，当前 Forward Protocol 终止，必须
   新建设计/版本，不能把两种语义合并为同一个 W30/W60 窗口。

## 7. Golden Parity And Activation Gate

### 7.1 Required independent Replay bundle

Forward 实施认证前必须获得独立 Replay 的以下成员级 Artifact：

| Artifact | Required use |
| --- | --- |
| `selection_spec.json` | 冻结精确 V0 参数、枚举和 canonicalization |
| `selection_snapshots.csv.gz` | Session 级 EMPTY、ready count、Selected identity |
| `member_decisions.csv.gz` | 24-member Feature、status、rank、reason |
| `run_manifest.json` | Source、input、code 和 environment identity |
| `qc.json` | Cutoff、data、determinism、coverage evidence |
| `decision.json` | Gate 计算与最终 Replay Decision |

`REPORT.md` 不能替代这些 Artifact。

### 7.2 Golden membership parity

Forward `SelectionCore` 必须在历史 **961 个 Session** 上重放成员决策，并逐字段达到：

```text
session identity                 exact
member status                   exact
primary reason                  exact
rank                            exact
Selected / Near membership      exact
EMPTY                           exact
SelectionSnapshot digest        exact after agreed canonicalization
```

若独立 Replay Artifact 的字段或 canonical digest 无法支持上述比较，必须先形成一次明确的
Artifact Compatibility Note；只能补足序列化差异，不能改变 Selection 规则。

### 7.3 Source and outcome parity

Golden Certification 还必须证明：

1. 相同 MarketSnapshot 通过当前 `evaluate_strategy_snapshot()` 得到相同 Trigger；
2. first natural Episode identity 与独立 Replay 一致；
3. TP1、formal Stop、Reclaim、Session expiry、Tail3、Tail5 和 ambiguity 标签一致；
4. LONG/SHORT 方向与 denominator 一致；
5. Source/data dtype 归一化不会改变 OHLCV、Quote Volume 或成员状态。

### 7.4 First prospective session

V0 历史研究已经使用的 Path 数据不得重新称为未来证据。Forward 的第一个可接受 Session
为：

```text
max(
    2026-08-21T00:00:00Z,
    first UTC Session after Golden Certification and Activation Manifest commit
)
```

Certification dry-run、手工试跑和 Activation 前 Session 只能标记 `DRY_RUN`。

## 8. Selection Clock And Timeliness

### 8.1 Exact cutoff

每个 UTC Session `D`：

```text
feature_cutoff_at = D 01:00:00.000 UTC
```

允许输入的最后一根 OR K 线为：

```text
open_time  = D 00:45:00
close_time = D 01:00:00
```

任何 `open_time >= D 01:00:00` 的 K 线、Trigger、未来 Volume、未来产品状态或 Outcome
不得进入 Selection。

### 8.2 Timing windows

| Window | Exact boundary | Evidence meaning |
| --- | --- | --- |
| Preferred execution | `01:00:05 <= commit < 01:05:00` | `ON_TIME` |
| Late pre-trigger window | `01:05:00 <= commit < 01:15:00` | `LATE` diagnostic only |
| Hard missed boundary | `commit >= 01:15:00` or no commit | `MISSED` |

`01:15:00` 是第一根 OR 后 15m K 线闭合时刻。该边界为左闭：在 `01:15:00` 或之后提交的
Snapshot 已可能观察到第一根 Trigger bar，因此不能进入 Prospective Primary Evidence。

### 8.3 Bounded retry

SelectionRunner 应在 `01:00:05` 后开始：

1. 获取 public server time 并记录 host offset；
2. 批量读取 24-symbol 所需 closed Kline；
3. 对网络 timeout、429 或暂时缺少 final OR bar 做有界 retry；
4. 推荐每次 request timeout **10 秒**、最多 **3 次**、并发不超过 **4**；
5. `01:05:00` 后即使成功也标为 `LATE`；
6. `01:15:00` 后禁止创建可冒充 prospective 的 Snapshot。

重试参数属于 Forward Protocol，实施前冻结；改变后创建新 Execution Epoch。

### 8.4 Clock integrity

Host clock 与 Binance public server time 的绝对偏差超过 **2 秒**时，Session 标记
`CLOCK_DRIFT`，不得进入 Primary Evidence。不得通过修改本地时间戳把 Late/Missed
Snapshot 改成 ON_TIME。

## 9. Session Evidence State

### 9.1 Orthogonal states

每个 Session 必须同时保存多个维度，不能用一个字符串掩盖不同故障：

| Dimension | Values |
| --- | --- |
| Timeliness | `ON_TIME / LATE / MISSED / DRY_RUN` |
| Source integrity | `VALID / SOURCE_DRIFT / SPEC_DRIFT / CLOCK_DRIFT / CONFLICT` |
| Data integrity | `COMPLETE / DATA_INCOMPLETE / FETCH_FAILED` |
| Selection state | `NON_EMPTY / EMPTY / NOT_COMPUTED` |
| Outcome state | `PENDING / PARTIAL / COMPLETE / UNAVAILABLE` |

Derived Primary eligibility：

```text
primary_evidence_eligible =
    timeliness == ON_TIME
    and source_integrity == VALID
    and data_integrity == COMPLETE
    and selection_state == NON_EMPTY
    and outcome_state == COMPLETE
```

EMPTY 仍是一个有效、事前冻结的 Selection 结果，进入 EMPTY 与 Coverage 报告，但不进入
Dynamic vs Static 的 non-EMPTY paired lift。

### 9.2 Data completeness rule

Forward V0 对数据采集故障采取保守边界：

- LOW_ACTIVITY 或合法的几何资格失败属于 Member Qualification，不使 Session
  `DATA_INCOMPLETE`；
- 任一 Panel member 因 fetch failure、重复、gap 或不连续而无法重建 exact pre-cutoff
  输入时，Session 标记 `DATA_INCOMPLETE`；
- 仍可输出 Diagnostic Selection，但不得进入 Primary Evidence；
- 不允许因为某个本应排名靠前的 Instrument 缺数据而自动换入后续成员，并把该 Session
  称为完整 Dynamic Policy。

该规则比 Historical Replay 更严格，目的是避免 Forward 运行故障形成选择性缺失。

## 10. Public Market Data Contract

### 10.1 Allowed source

Forward CLI 只允许访问配置中冻结的 **Binance USDⓈ-M public market endpoints**：

- server time；
- 15m Kline；
- public exchange/product status；
- 可选的 public 1m Kline ambiguity window，仅在 Protocol 明确启用时。

禁止：

- API key；
- signed request；
- account、position、order 或 balance endpoint；
- private ccxt client；
- production credential environment；
- order create/cancel/modify。

### 10.2 Captured source evidence

每次 Selection fetch 至少冻结：

| Field | Meaning |
| --- | --- |
| Endpoint and parameters | Exact public request identity |
| Request start / response time | Timeliness audit |
| Binance server time | Clock audit |
| HTTP status / retry count | Operational evidence |
| Raw response SHA-256 | Input identity |
| First/last open time | Cutoff audit |
| Row count / duplicate / gap count | Data integrity |
| Parsed OHLCV/Quote Volume digest | Semantic input identity |

原始响应或其无损压缩副本保存在仓库外 evidence root。不得把今天重新下载的数据冒充当时
01:00 已知的响应；事后下载只允许用于 Outcome 或独立 QC，并必须标明 fetch time。

### 10.3 Product diagnostics

Forward 可记录：

- contract status；
- product type；
- onboard/delivery date；
- price/quantity precision；
- public spread snapshot，如果单独实现。

这些字段在 V0 只属于 `forward_operational_diagnostic`，不得改变历史冻结的 Selection
排序或补位。若发现 Instrument 非 USDⓈ-M perpetual 或 status 明确不可交易，记录
`forward_operational_invalidation`；V0 Primary 仍保留原计划 Slot 与缺失 Outcome，不能
事后换币。

## 11. Frozen Selection Contract

### 11.1 Candidate Panel

Forward 必须复用 V0 的 24-symbol Panel：

| Group | Symbols |
| --- | --- |
| Large / liquid | BTCUSDT、ETHUSDT、BNBUSDT、SOLUSDT、XRPUSDT、DOGEUSDT |
| Established alts | ADAUSDT、AVAXUSDT、LINKUSDT、LTCUSDT、BCHUSDT、DOTUSDT |
| Mid-cap / heterogeneous | NEARUSDT、ATOMUSDT、FILUSDT、ETCUSDT、APTUSDT、OPUSDT |
| Additional panel | ARBUSDT、INJUSDT、SUIUSDT、TRXUSDT、UNIUSDT、RUNEUSDT |

Forward V0 期间不得增删或替换 Symbol。Listing、delisting 或 data loss 通过状态表达。

### 11.2 Exact features

```text
or_width = max(high of D 00:00..01:00 bars)
         - min(low  of D 00:00..01:00 bars)

pre_or_atr14 = arithmetic mean(
    true range of the last 14 bars before D 00:00,
    using the prior close required by TR
)

pre_or_width_atr14 = or_width / pre_or_atr14

trailing_24h_quote_volume =
    sum(96 closed 15m quote-volume bars ending at D 01:00)
```

ATR 不包含 OR bars 或 Trigger bars。Financial geometry 使用 `Decimal`。

### 11.3 Qualification and ranking

Selection-ready 必须满足 V0 的 exact data、geometry 和 Activity 条件：

```text
trailing_24h_quote_volume >= 20,000,000 USDT
```

稳定排序：

```text
1. pre_or_width_atr14 ascending
2. trailing_24h_quote_volume descending
3. canonical exchange_instrument_id ascending
```

### 11.4 Member states and cohorts

| Rank / condition | State |
| --- | --- |
| Qualification failed | `INELIGIBLE` |
| Rank 1–7 | `SELECTED` |
| Rank 8–14 | `NEAR_THRESHOLD` |
| Rank 15–N | `NOT_SELECTED` |
| Ready count < 7 | Snapshot `EMPTY`; select none |

Member Primary Reason、tie-break 和 EMPTY 语义完全继承 V0 Detailed Design。

### 11.5 Frozen controls

每个 ON_TIME Snapshot 同时冻结：

1. `dynamic_selected_7`；
2. `static_7`：BTC、ETH、SOL、BNB、XRP、DOGE、ADA；
3. `random_7` replicate `0..99`；
4. `near_threshold`；
5. `not_selected`；
6. `all_selection_ready`；
7. `all_panel_diagnostic`。

Random membership 使用 V0 已冻结的 canonical SHA-256 排序，不调用运行时 PRNG。

## 12. Immutable SelectionSnapshot

### 12.1 Snapshot header

每个 Snapshot 至少包含：

| Field group | Required fields |
| --- | --- |
| Identity | Snapshot ID、Session start/end、Protocol/Spec digest、Execution Epoch |
| Timing | cutoff、request start、commit time、timeliness、server-time offset |
| Source | endpoint identity、raw/parsed digests、source status |
| Selection | ready count、EMPTY、Selected/Near/Not Selected member IDs |
| Controls | Static 7、Random 0–99、All Selection-ready、All Panel |
| Integrity | previous ledger digest、payload digest、writer identity |
| Status | source/data/selection state and reason codes |

### 12.2 Member decision

每个 Panel member 至少冻结：

- exchange instrument identity；
- exact input-window boundaries；
- OR high/low/width；
- pre-OR ATR14；
- OR/ATR；
- trailing 24h Quote Volume；
- optional diagnostics；
- Qualification booleans；
- primary/secondary reasons；
- stable rank；
- member state；
- selected Policy memberships；
- raw input digest；
- operational diagnostics。

### 12.3 Write-once and idempotency

Snapshot 提交必须使用：

```text
temporary file
-> flush/fsync
-> atomic rename to immutable final path
-> digest sidecar / ledger append
```

重复调用规则：

| Existing state | New result | Required behavior |
| --- | --- | --- |
| No Snapshot | Valid payload | Commit once |
| Same ID and same digest | Same payload | Return idempotent success |
| Same ID and different digest | Any payload | Record `CONFLICT`; never overwrite |
| LATE/MISSED diagnostic exists | Later recalculation | New diagnostic revision only; never ON_TIME |

任何人工编辑都会破坏 digest chain；修复必须创建新的 Execution Epoch，旧证据保留。

## 13. Runtime Orchestration

### 13.1 CLI modes

实现应提供四个窄命令，而不是常驻平台：

| Mode | Purpose | Mutation boundary |
| --- | --- | --- |
| `certify` | Golden parity、source/spec/determinism checks | 只写 certification artifacts |
| `select-session` | 当前 Session 事前 SelectionSnapshot | 只写一个 immutable Snapshot |
| `finalize-due` | 完成已到期的 SOR Outcome revisions | 只追加 Outcome |
| `summarize` | 生成有界 checkpoint metrics/decision | 只追加 Summary/Decision |

### 13.2 External scheduling

第一阶段推荐节奏：

```text
Daily UTC 01:00:05
    select-session --session current

Daily UTC 00:05
    finalize-due --through now

On checkpoint / manual readonly inspection
    summarize --as-of now
```

`finalize-due` 可晚于 Outcome 到期执行，因为它只读取已经闭合的未来价格路径；延迟不会
把 Selection 变成事后选择。所有 fetch time 仍须记录。

外部调度可在本地 Mac 或隔离 research host 上运行，但必须满足：

- 只有一个 active writer；
- 从专用、已认证的冻结 worktree/commit 运行，不跟随日常 `dev` 工作区变化；
- 不使用生产 `.env`；
- 不由四个 Kernel Worker 调用；
- 不创建 Tokyo systemd timer；
- host 切换前先终止旧 writer，并创建新 Execution Epoch；
- laptop sleep 或网络中断形成真实 LATE/MISSED，不允许事后洗白。

### 13.3 Concurrency and lock

每个 evidence root 使用单 writer lock。锁中只包含本地 Artifact 提交，不包含网络等待。
相同 Session 的并发执行必须有一个成功、其余幂等读取或 `CONFLICT`；不能生成两个合法
Snapshot。

## 14. Prospective SOR Outcome Contract

### 14.1 Trigger ownership

Forward 必须直接调用 current tracked `evaluate_strategy_snapshot()` / `SORDetector`，不得
复制 breakout/breakdown 公式。

每个 Instrument、Side、UTC Session：

- 最多接受第一个自然 Trigger；
- LONG 与 SHORT 独立；
- 同 Session 后续再次突破不创建第二个 Episode；
- `23:45–24:00` open bar 不为旧 Session 创建新 Trigger；
- Selection membership 不影响 Detector 是否被评价。

最后一条保证 Selected、Near、Not Selected 和 All Panel 都使用相同 Event truth。

### 14.2 Signal-basis geometry

```text
entry_reference = trigger candle close
formal_stop     = opposite Opening Range boundary
formal_r        = abs(entry_reference - formal_stop)
```

Trigger candle 的 high/low 发生在 entry_reference 之前，不进入 entry 后 first-passage。

### 14.3 Primary path endpoint

Primary 继续使用 V0 的：

```text
policy_tail3_cons
```

要求：

1. Trigger 后先在 formal Stop、closed-candle OR reclaim 或 Session expiry 前达到 `+1R`；
2. `+1R` 后或同一后续 Bar 内，在 Trigger 后最多 96 根 15m K 线中、原始 formal Stop
   前达到 `+3R`；
3. 未能证明先后顺序的 target/stop same-bar 按 conservative failure；
4. Pre-TP1 reclaim 只由 closed-candle close 判断；
5. Session expiry 只阻断尚未达到 TP1 的 Episode；
6. Outcome 不模拟 TP1 partial Fill、Break-even Floor 或 Structural ATR Runner。

### 14.4 Required diagnostics

| Diagnostic | Required meaning |
| --- | --- |
| Natural Trigger | 是否形成 first natural Episode |
| TP1 attainable | pre-TP1 policy 下是否达到 `+1R` |
| Tail3 / Tail5 | 原始 formal R 下的 policy-qualified tail |
| Raw first passage | `+0.5R / +1R / +2R / +3R / +5R / -1R` |
| Time to level | 从 Trigger close 到 first-passage |
| MFE_R / MAE_R | 固定 96-bar signal-basis excursion |
| Reclaim | TP1 前 closed-candle reclaim |
| Session expiry | TP1 前到 Session end |
| Same-bar ambiguity | 目标和 Stop 同 Bar，顺序未知 |
| Outcome completeness | Path 是否连续、唯一并覆盖所需 Horizon |

只有预注册的 Primary/Guardrail Metric 进入 Forward Decision；其他字段只用于解释，不能在
W30/W60 后被改造成 V0 新 Gate。

### 14.5 Same-bar policy

Forward Protocol 必须明确冻结 `ambiguity_resolution_mode`：

```text
CONSERVATIVE_15M
```

V0 Primary 默认不依赖事后补抓 1m K 线；同一 15m Bar 同时触达 target 与 formal Stop 时
标记 `ambiguous_same_bar` 并按失败处理。Activation 前必须由 Golden Artifact 证明其正式
Primary 与 `CONSERVATIVE_15M` 一致；若独立 Replay 实际使用了 1m resolver，本设计必须先
修订并重新复核，实施不得在运行时自行选择模式。

### 14.6 Outcome due and revision

一个 Session 的统一最晚 Outcome due boundary 为：

```text
session_start_ms + 48 hours
```

该边界覆盖 Session 内最晚合法 Trigger 后的 96 根 15m K 线。`finalize-due` 可在该时间后
读取所有闭合路径并形成 COMPLETE revision。

Outcome 只能追加 revision：

| Revision state | Meaning |
| --- | --- |
| `PENDING` | Snapshot 已存在，未来 Path 未到期 |
| `PARTIAL` | 部分 closed data 可见，但不得进入 Decision |
| `COMPLETE` | 所需 Path 完整，指标冻结 |
| `UNAVAILABLE` | 经重试仍无法形成合法路径，原因明确 |

后续数据修复只能新增更高 revision；不得覆盖旧 revision。Decision 只使用 `as_of` 前最新
valid COMPLETE revision。

## 15. Evidence Store And Digest Chain

### 15.1 Repository-external root

建议路径：

```text
~/research/sor-dynamic-selection-forward-v0/
```

建议结构：

```text
spec/
certification/
epochs/<execution_epoch>/
  activation_manifest.json
  source/
  snapshots/<session_start_ms>/snapshot.json
  outcomes/<session_start_ms>/<instrument>/<side>/revision-<n>.json
  ledger/records.jsonl
  summaries/<checkpoint_id>/
```

所有生成物禁止进入 Git、`docs/current`、生产 output authority 或 PostgreSQL。

### 15.2 Canonical digest

Canonical payload 使用：

- UTF-8；
- object key lexicographic order；
- compact separators；
- integer timestamp milliseconds；
- Decimal 使用规范十进制字符串；
- enum 使用冻结 lowercase/uppercase value；
- 不包含本地绝对路径或随机 UUID；
- SHA-256 前缀 `sha256:`。

### 15.3 Ledger record

每条 Ledger record 包含：

```text
record_type
record_identity
payload_digest
previous_record_digest
recorded_at_ms
writer_identity
record_digest
```

Hash chain 用于发现意外覆盖或删改，不宣称具备数字签名或外部不可抵赖性。Checkpoint 时
应将当前 chain head 与整个 evidence root archive SHA-256 一并输出。

### 15.4 Partial run

进程崩溃后遗留的 temporary file、缺少 digest sidecar 或 ledger 未提交状态统一标记
`PARTIAL_RUN`。它们不能参与 Summary。恢复时只能完成同 payload 的原子提交或写入失败
记录，不能复用 partial 内容生成另一个 ON_TIME timestamp。

## 16. Metrics And Denominators

### 16.1 Primary denominator

沿用 V0：

```text
Tail3 events per 100 directional slot-days
= 100 * policy_tail3_cons_count / complete_directional_slot_days
```

每个 Instrument、Side、Session 是一个 directional slot-day。完整无 Trigger Slot 必须进入
分母。

### 16.2 Primary paired evidence

Forward comparison 只使用：

1. ON_TIME；
2. Source/Data integrity valid；
3. Dynamic Snapshot 非 EMPTY；
4. Dynamic、Static 和 Random control 的所需 Outcome 完整；
5. LONG 与 SHORT 均可评价。

Selection 后 Path 缺失不能反向改变 membership，也不能按 0 或失败处理。

### 16.3 Required Forward metrics

| Metric | Required grouping |
| --- | --- |
| Tail3 / 100 directional slot-days | Policy、Direction、10-session Block |
| Trigger / 100 directional slot-days | Policy、Direction、Block |
| TP1 / Trigger | Policy、Direction、Block |
| Tail3 / Trigger | Policy、Direction、Block |
| Tail5 / Trigger | Policy、Direction、Block |
| Reclaim / Trigger | Policy、Direction |
| MFE/MAE median and P90 | Policy、Direction |
| Selected / Near / Not Selected gradient | Combined、Direction |
| Random median / P75 / max | Combined、Direction |
| Dynamic-exclusive contribution | Instrument、Block、Direction |
| Static-exclusive contribution | Instrument、Block、Direction |
| ON_TIME / LATE / MISSED | Calendar Session |
| EMPTY / ready count | Session |
| Source/data/outcome completeness | Session、Instrument、Reason |
| Opportunity capture/loss | Dynamic、Selection-ready、All Panel |

Random 分布使用冻结的确定性定义：100 个 replicate 按 metric 升序排列，`P75` 使用
nearest-rank 的第 **75** 个值；Median 使用第 50、51 个值的算术平均。所有 Policy rate
先从整数 count/denominator 形成精确比率，再展示小数，不能先四舍五入后比较 Gate。

## 17. Forward Observation Window

### 17.1 Fixed checkpoints

Forward V0 使用两个预注册检查点：

| Checkpoint | Window | Purpose |
| --- | --- | --- |
| **W30** | Activation 后前 **30 个连续 UTC calendar Sessions** | 强方向证据可开始 Apply 设计，否则延长 |
| **W60** | 同一起点前 **60 个连续 UTC calendar Sessions** | 最终 V0 Continue/Revise/Stop |

不通过跳过坏日、重置起点或只累计“看起来完整”的 Session 改变窗口。所有 LATE、MISSED、
EMPTY 和 DATA_INCOMPLETE 都保留在固定窗口中。

Checkpoint 必须等窗口内所有可到期 Outcome 至少经过一次 `finalize-due` 后生成。

### 17.2 Operational readiness gate

W30/W60 进入 Alpha 判断前必须满足：

| Gate | W30 | W60 |
| --- | ---: | ---: |
| ON_TIME + valid Snapshot | 至少 **27 / 30** | 至少 **54 / 60** |
| Accounted calendar Sessions | **30 / 30** | **60 / 60** |
| 每个固定 10-session Block 的 valid Snapshot | 至少 **8 / 10** | 至少 **8 / 10** |
| Paired directional-slot Outcome coverage | 至少 **98%** | 至少 **98%** |
| Dynamic vs Static coverage difference | 不超过 **1 pct point** | 不超过 **1 pct point** |
| Source/Spec conflict | **0** | **0** |

未通过 Operational Gate 时，结论只能是 `REPAIR_EVIDENCE_PIPELINE`，不能把运行失败解释为
Selector 无效或有效。规则不变的可靠性修复可以继续当前 V0；任何 Feature/Policy 改动必须
创建 V1。

固定 Block 以 calendar Session 切分，不能因 LATE/MISSED 改边界。Block 内的 lift 使用该
Block 中 Primary-eligible paired Session；valid Snapshot 少于 8 个时该 Block 不合格，
整个 Operational Gate 失败。

## 18. Forward Decision Contract

### 18.0 Zero-denominator and tie semantics

- 所有“高于”均为严格 `>`；相等不算通过；
- Static Primary 为 0 时不计算相对 lift，Dynamic 必须有正 Tail3 count，并继续通过
  Random、Block、concentration 和 direction Gate；
- Static `Tail3/Trigger` 为 0 时不计算 ratio，以 Dynamic/Static 的 Tail3 与 Trigger 绝对
  count 并列判断，该项不单独否决；
- 某方向 Static Primary 为 0 时不计算“低 20%”，Dynamic 该方向若也为 0则记 Warning，
  若大于 0则通过该方向 Guardrail；
- Near 或 Not Selected 在整个 Checkpoint 没有完整 directional-slot denominator 时，梯度
  Gate 不可评价：W30 只能 Extend，W60 只能 Revise/Stop，不能 Advance。

### 18.1 W30 strong advance

W30 只有同时满足以下条件，才输出：

```text
ADVANCE_TO_SMALL_CAPITAL_APPLY_DESIGN
```

1. Dynamic Primary Metric 高于 Static；
2. Dynamic 高于 100 个 Random replicates 的 **75th percentile**；
3. 固定三个 10-session Block 中至少 **2 / 3** 的 Dynamic > Static；
4. Combined `Selected > Near > Not Selected`；
5. Dynamic / Static `Tail3 per Trigger` ratio 不低于 **0.90**；
6. LONG 与 SHORT 各自的 Dynamic Primary 不得比同方向 Static 低超过 **20%**；
7. Dynamic-exclusive Tail3 来自至少 **3 个 Instrument**；
8. 单一 Instrument 不贡献超过 **50%**；
9. Operational Gate 全部通过。

W30 Advance 只授权编写 Apply 设计。Forward Shadow 应继续运行；真实 Apply 仍需独立 Owner
批准、生产认证和小资金边界。

### 18.2 W30 early stop

满足以下任一硬失败时输出：

```text
STOP_FORWARD_V0
```

- Dynamic 同时不高于 Static 和 Random median，且 Selected 不高于 Not Selected；
- Dynamic `Tail3 per Trigger` 低于 Static 的 **80%**；
- Source/cutoff/determinism 证明失败且无法恢复 exact prospective identity；
- 结果主要由未解决 same-bar ambiguity 或已知实现错误产生。

其余混合结果统一输出：

```text
EXTEND_TO_W60
```

W30 后不得根据中间结果修改 V0。

### 18.3 W60 final advance

若 W30 未强通过，W60 需要同时满足以下条件才进入 Apply 设计：

1. Dynamic Primary 高于 Static；
2. Dynamic 高于 Random median；
3. 同时满足以下至少一项：
   - Dynamic 高于 Random P75；
   - Dynamic 相对 Static lift 至少 **10%**；
4. 六个固定 10-session Block 中至少 **4 / 6** 的 Dynamic > Static；
5. Selected 高于 Not Selected；
6. Dynamic / Static `Tail3 per Trigger` ratio 不低于 **0.90**；
7. LONG 与 SHORT 各自不比 Static 低超过 **20%**；
8. Dynamic-exclusive Tail3 来自至少 3 个 Instrument，单一 Instrument 不超过 50%；
9. Operational Gate 全部通过。

Near 没有严格位于 Selected 与 Not Selected 之间时必须记录为 Warning，但在 W60 不单独
否决；原因是 Near 只有 7 个成员，短窗口梯度容易受离散 Event 数影响。Selected 不高于
Not Selected 仍是硬失败。

### 18.4 W60 revise or stop

W60 未 Advance 时：

| Evidence shape | Decision |
| --- | --- |
| Primary 正向，但一个已预注册 Diagnostic 清楚解释唯一失败门 | `REVISE_ONCE_AS_V1` |
| Dynamic 不优于 Static/Random，或梯度倒置 | `STOP_FORWARD_V0` |
| 运行可靠性不足 | `REPAIR_EVIDENCE_PIPELINE` |
| 结论仍混合且没有单一可解释修订 | `STOP_FORWARD_V0` |

V1 只能修改一个明确假设，例如 Activity floor、Top N 或加入一个预先存在的 Diagnostic。
W30/W60 已观察数据只能作为 V1 Development Evidence；V1 必须拥有新的未来起点，不能在
同一窗口上调参后宣称 prospective 通过。

## 19. Failure Semantics

| Failure | Required outcome | Production effect |
| --- | --- | --- |
| Source/Spec digest drift | `SOURCE_DRIFT / SPEC_DRIFT`; stop Primary | None |
| Host clock >2s | `CLOCK_DRIFT` | None |
| OR final bar not available by 01:05 | Retry then `LATE` | None |
| Commit at/after 01:15 | `MISSED`; diagnostic only | None |
| One Panel member fetch gap | `DATA_INCOMPLETE`; no Primary | None |
| Ready count <7 with valid data | `EMPTY` | None |
| Duplicate Snapshot same digest | Idempotent success | None |
| Duplicate Snapshot different digest | `CONFLICT`; never overwrite | None |
| Outcome path incomplete | Append `PARTIAL/UNAVAILABLE` | None |
| Same-bar unresolved | Ambiguous; conservative failure | None |
| Public endpoint outage | Preserve retry/failure evidence | None |
| Private endpoint/credential use attempt | Fail architecture certification | None |
| PostgreSQL access attempt | Fail architecture certification | None |
| Kernel Worker/systemd integration attempt | Design violation | None |
| Partial artifact write | `PARTIAL_RUN`; exclude | None |

Forward 失败不创建生产 Incident，因为它不是生产 Runtime。若未来 Apply 采用同一逻辑，
其 Incident、fence 和 fail-closed 语义必须在 Apply 设计中重新定义。

## 20. Transactions, I/O And Performance

### 20.1 Transaction ownership

Forward V0 不打开 PostgreSQL 事务。网络 I/O 与本地 Artifact 提交严格分离：

```text
bounded public network reads
-> pure validation and computation
-> short local file lock
-> atomic artifact commit
```

锁内禁止网络等待。

### 20.2 Bounded resource envelope

| Resource | Boundary |
| --- | --- |
| Candidate Panel | **24** Instruments |
| Selection Kline input | 每 Symbol 约 **96 + 19** 根 15m bars |
| Public concurrency | 最多 **4** |
| Request attempts | 最多 **3** |
| Request timeout | 推荐 **10 秒** |
| Daily Selection writes | 1 Snapshot + 24 Member decisions + source evidence |
| Random controls | 100 membership sets；不复制 100 份 Path data |
| Outcome cadence | Daily bounded finalization；非高频 |

实现不得默认占满本机 CPU，不得把 24-symbol 数据复制为 100 个完整 DataFrame，不得在
2C4G Tokyo production host 上运行全市场研究任务。

### 20.3 No-signal file semantics

Forward 本身每天都需要写一个 SelectionSnapshot，因此不适用生产 Kernel 的“无 Signal
零文件”规则。该文件写入只发生在仓库外 Research Evidence Root，不属于生产 runtime
output，也不能被 Kernel 读取。

## 21. Necessary Tests And Certification

### 21.1 Selection unit tests

| Test | Observable assertion |
| --- | --- |
| Cutoff | 任何 `open_time >= 01:00` 输入均被拒绝 |
| OR | 精确四根 15m K 线 |
| ATR14 | 只使用 OR 前 14 TR 和 prior close |
| Activity | 精确 96 根、截止 01:00 |
| Qualification | 每类失败有唯一 Primary Reason |
| Ranking | OR/ATR、Volume、Instrument tie-break 稳定 |
| Cohort | 7 Selected、7 Near、其余 Not Selected |
| EMPTY | Ready <7 时 select none |
| Random | 100 replicates 跨进程稳定 |
| Decimal | 序列化重读不改变 rank/digest |

### 21.2 Time and evidence tests

| Test | Observable assertion |
| --- | --- |
| ON_TIME | 01:05 前提交进入 prospective eligibility |
| LATE | 01:05–01:15 只作 diagnostic |
| MISSED | 01:15 起永不升级为 ON_TIME |
| Clock drift | >2s fail closed |
| Retry | bounded attempts，不跨 hard deadline |
| Idempotency | 同 digest 重放不新增合法 Snapshot |
| Conflict | 不同 digest 永不覆盖 |
| Atomic write | 崩溃只留下 PARTIAL，不污染 final |
| Hash chain | 删除、重排、编辑可被检测 |
| Epoch switch | 双 writer 不能同时提交 |

### 21.3 SOR semantic tests

| Test | Observable assertion |
| --- | --- |
| Official detector import | 不复制 Trigger 公式 |
| First Episode | 每 Symbol/Side/Session 最多一个 |
| Trigger candle exclusion | entry 前 high/low 不计 Path |
| TP1/Stop | LONG/SHORT 方向正确 |
| Reclaim | 只使用 closed close，且仅 pre-TP1 |
| Session expiry | 未 TP1 时正确阻断 |
| 96-bar horizon | 边界无 off-by-one |
| Same-bar | conservative failure |
| No Trigger | 完整 Slot 进入 denominator |
| Tail3/Tail5 | 与 Golden Artifact 一致 |

### 21.4 Golden and architecture tests

| Test | Observable assertion |
| --- | --- |
| 961-Session parity | Member status/rank/cohort exact |
| Source digest | drift before outcome read fails closed |
| Live/Replay detector parity | same Snapshot -> same DetectorResult |
| No PostgreSQL | research modules不导入 repository/UoW/SQLAlchemy |
| No private Venue | 不导入 Command、private adapter、credential signer |
| No runtime integration | 不进入四 Worker 或 systemd deploy files |
| External output | artifacts 不进入 Git/current docs |

### 21.5 Proportional verification

实施阶段只运行：

1. 新增 research unit/semantic/architecture tests；
2. exact Golden parity test；
3. existing Live/Replay detector parity；
4. current document authority test；
5. Ruff/Mypy 仅覆盖新增 research code；
6. `git diff --check`。

Forward Shadow 不修改 Kernel、Schema、Policy 或部署，因此不触发全量 Trading Kernel
Release certification。未来 Apply 设计进入生产代码后重新分类。

## 22. Implementation And Deployment Impact

| Area | Forward V0 impact |
| --- | --- |
| `src/trading_kernel` | **None** expected |
| PostgreSQL Schema/Data | **None** |
| Four systemd Workers | **None** |
| Owner API / frontend | **None** |
| Active StrategyUniverse | **None** |
| Crypto `SOR-001` control | remains paused |
| Exchange account | no access |
| Git tracked changes | research code/tests/docs only after approval |
| Generated evidence | repository-external only |

若实施发现必须修改 `src/trading_kernel` 才能获得公共纯函数，应先暂停并重新审查边界；不得
为便利而把 Forward Evidence 接入生产运行链。

## 23. Rollout, Pause And Recovery

### 23.1 Rollout

```text
Design review
-> Execution Plan
-> RED tests
-> SelectionCore + evidence store
-> Golden parity
-> dry-run Session
-> Activation Manifest
-> first prospective ON_TIME Session
```

### 23.2 Pause

停止外部调度即可暂停 Forward。因为没有生产写入，暂停不会影响 Ticket、Position、Worker
或 StrategyUniverse。暂停期间的 calendar Session 必须记录 `MISSED`；恢复不能重置起点。

### 23.3 Recovery and fix-forward

- Artifact corruption：保留坏文件和 digest evidence，创建新 Execution Epoch；
- Source semantic change：完成新 parity review 后创建新 Epoch；
- Selection rule change：创建 V1，不是新 Epoch；
- Host move：停止旧 writer、冻结 chain head、创建新 Epoch；
- Scheduler outage：保留 MISSED，不做事后 ON_TIME backfill；
- Public data later repaired：只追加 Outcome revision，不改 SelectionSnapshot。

## 24. Future Small-capital Apply Boundary

Forward 通过后，下一份设计才允许讨论：

```text
Owner Allowed Universe
∩ Point-in-Time Tradeability
∩ approved Dynamic Selected Set
-> Desired StrategyUniverse Version
-> Warming
-> Certification
-> atomic Activation before first eligible Trigger
```

Apply 设计必须单独解决：

1. `UTC 01:00 -> 01:15` 内能否完成 Universe Warming/Certification/Activation；
2. Snapshot 迟到、数据缺失或 Selector failure 时使用 Static fallback 还是 fail closed；
3. Active Ticket、已有 Signal 和当前 Netting Domain 是否完全不受 Universe 切换影响；
4. ComparisonUniverse 与 Tradable StrategyUniverse 的长期边界；
5. Owner 前端如何 Preview、Approve、Pause 和审计；
6. 小资金风险边界、退出和回滚；
7. 真实 Fill、Fees、Funding、Slippage 与 Net R 的评价合同。

Forward Shadow 不预先回答这些生产问题，也不把本地 Artifact 直接提升为 Runtime
StrategyUniverse authority。

## 25. Deleted Or Rejected Concepts

本设计明确不引入：

- `SelectorSignal`；
- 模拟 Ticket；
- `shadow_strategy_universe` 生产表；
- 第五个 Kernel Worker；
- research systemd timer；
- Markdown/JSON runtime authority；
- 动态原地修改 Active membership；
- Outcome-driven 人工补选；
- 观察后修改 V0；
- AI/Owner 每日二次排名；
- Static fallback 的隐式生产语义。

## 26. Design Completion Criteria

本详细设计可进入执行文档阶段，需要：

1. Owner 或复核模型确认 Clock、Deadline、Evidence State 和 30/60 Session Gate；
2. 独立 Replay 成员级 Artifact 可获得，或明确补件计划；
3. Golden Parity、source digest、cutoff 和 determinism 门完整；
4. Existing Signal-owned Shadow 与 Selection-owned Forward Evidence 边界清楚；
5. 不包含生产授权、Schema、Worker、API、页面或 Universe Apply；
6. 文档权威测试通过；
7. `git diff --check` 通过。

实现 Done 条件由后续 Execution Plan 拆成可复核批次。本文件本身不授权开始编码。

## 27. External Review Focus

外部复核应重点挑战：

1. **Golden Parity**：961 Session exact membership 是否足以认证独立实现；
2. **Clock**：01:05 soft deadline、01:15 hard deadline 和 2 秒 clock drift 是否合理；
3. **Data completeness**：任一 Panel fetch gap 使整个 Session 退出 Primary 是否过严；
4. **Artifact model**：文件型追加证据在非生产研究阶段是否足够；
5. **Outcome parity**：Trigger candle exclusion、pre-TP1 Session expiry 和 96-bar Tail
   是否与独立 Replay 完全一致；
6. **Ambiguity**：`CONSERVATIVE_15M` 是否与 Golden Artifact 匹配；
7. **W30 gate**：Random P75、2/3 Blocks 和完整梯度是否对 30 Session 过严；
8. **W60 gate**：Random median + P75/10% 二选一是否足以支持小资金 Apply 设计；
9. **Operational gate**：27/30、54/60 和 98% coverage 是否合理；
10. **Research isolation**：外部 CLI 是否彻底不触碰生产 DB、Worker、Policy 和 Universe；
11. **Evidence claim**：文档是否避免把 Tail Supply 写成 PnL 或生产有效性；
12. **Future Apply**：是否正确把 `01:00 -> 01:15` Universe activation 留给独立设计。
