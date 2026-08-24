---
title: SOR_DYNAMIC_SELECTION_RESEARCH_V0_DESIGN
status: FROZEN_COMPLETED_RESEARCH_DESIGN
date: 2026-08-20
phase: P3-X.1
research_spec_id: sor-dynamic-selection-v0
implementation_authority: NONE
production_authority: NONE
replay_result: PASS
current_successor: 2026-08-20-sor-dynamic-instrument-selection-trading-v0-design.md
---

# SOR Dynamic Selection Research V0 Detailed Design

## Completion Notice

本文件是冻结的 Historical Replay 合同，不再拥有当前阶段顺序。独立 Replay 已通过全部
定量 Gate；其原始 decision 为 `ADVANCE_TO_FORWARD_SHADOW`。Owner 后续明确取消独立
Forward Shadow，当前 successor 是：

```text
2026-08-20-sor-dynamic-instrument-selection-trading-v0-design.md
```

本文件中关于 Forward Shadow 的条款只解释当时的研究判定，不授权当前实现。

## 1. Decision

本设计冻结一个 **本地、只读、可解释的 SOR Dynamic Selection V0**，用于回答：

> 在每天 **UTC 01:00**、Opening Range 已闭合但 SOR Trigger 尚未发生时，能否根据
> Point-in-Time Instrument State，从固定候选面板中选择当前更符合
> **Compression → Expansion** 语义的 Instrument，并提高
> **pre-TP1-policy-qualified `+3R` tail supply**。

V0 的核心规则是：

```text
Fixed 24-symbol Research Panel
-> Point-in-Time product/data qualification
-> fixed Activity floor
-> rank by pre-trigger OR Width / ATR14 ascending
-> Dynamic Selected 7
-> compare with Static 7 / Random Selection-ready 7 / All Selection-ready
-> Advance / Revise / Stop
```

本设计不建设生产 Selector，不修改 Active StrategyUniverse，不恢复 Crypto
`SOR-001`，不新增 Worker、Schema、API 或页面，也不产生 Ticket、Exchange Command、
模拟成交或真实 PnL。

## 2. Known Facts

### 2.1 Frozen Instrument Effect evidence

第一轮研究 **`SOR-INSTRUMENT-EFFECT-v1`** 已完成：

| Evidence | Verified result |
| --- | ---: |
| Main Events | **36,577** |
| Instruments | **24** |
| Complete-day rate | **100%** |
| Clustered Symbol Wald | `p = 0.03296` |
| Within-day Symbol permutation | `p = 0.02249` |
| Rolling OOS top-bottom Tail3 gap | **-0.15 pct** |
| OOS gap 95% CI | **[-0.89 pct, +0.59 pct]** |
| Positive OOS folds | **37.5%** |
| Adjacent half-year rank rho median | **0.02** |

冻结研究的正式分类是：

```text
IN_SAMPLE_HETEROGENEITY_BUT_WEAK_PERSISTENCE
```

因此当前证据支持继续研究 **Dynamic Instrument State**，但不支持维护静态“好币名单”。

来源：`SOR-INSTRUMENT-EFFECT-v1` 的 `study_manifest.json`、`headline.json`、
`decision.json`、`rolling_oos_bootstrap.json`、
`within_day_symbol_permutation.json`；归档 SHA-256：
`d5947191abe392553ba8bccddc6ba0d5c691af511d663100cfbbecd0866f0ea2`。

### 2.2 Source parity limitation

冻结研究包的 `source_semantic_check.json` 证明它匹配当时声明的源码快照，不证明三个
完整文件仍与当前生产候选逐字节一致。当前核对结果是：

| Source | Current finding | V0 requirement |
| --- | --- | --- |
| `SORDetector` | 完整文件哈希仍与冻结研究一致 | 运行时重新冻结 exact digest |
| Strategy Registry | 完整文件因后续 TradFi Contract 加入而变化；Crypto SOR v4 slice 未观察到语义变化 | 导入当前 Contract，并跑 exact Event identity/parity test |
| Exit Policy | 完整文件因后续 TradFi Exit Policy 加入而变化；Crypto SOR v4 slice 未观察到语义变化 | 重新认证 TP1、Reclaim、Session、96-bar 语义 |

因此 Instrument Effect v1 仍可作为提出 V0 假设的 **Development Evidence**，但其旧
full-file hash 不能充当 V0 的当前源码认证。V0 运行必须以本分支 exact tracked code 为准，
重新形成 source digest 与 semantic parity evidence。

### 2.3 Geometry evidence

原研究的 Trigger-time `OR Width / ATR14` 与 policy-attainable `+3R` 路径呈单调下降：

| Trigger-time OR/ATR cohort | Approximate Tail3 rate |
| --- | ---: |
| 最窄四分位 | **13.7%** |
| 第二四分位 | **10.9%** |
| 第三四分位 | **8.9%** |
| 最宽四分位 | **5.5%** |

这支持 SOR 的 **Compression → Expansion** Selection Thesis，但原指标在 Trigger 时计算，
不能直接作为事前选择输入。V0 必须构造 `UTC 01:00` 已知的 Pre-trigger 版本。

来源：冻结研究的 `events.csv.gz`、`RESEARCH_PROTOCOL.md` 和研究程序 ATR 定义。

### 2.4 Current SOR v4 semantics

当前 Crypto SOR v4 的稳定语义是：

1. UTC `00:00` 开始 Session；
2. 前四根 15m K 线形成 Opening Range；
3. Long：前一 Close 不高于 OR High，最新 Close 突破 OR High；
4. Short：前一 Close 不低于 OR Low，最新 Close 跌破 OR Low；
5. Long Stop 为 OR Low，Short Stop 为 OR High；
6. TP1 为 `+1R`；
7. TP1 前发生 OR reclaim 或 Session expiry 时退出；
8. EventSpec 的 Shadow horizon 为 **96 根 15m K 线**；
9. `episode_policy = session_reference`；
10. 同一 Instrument、Side、UTC Session 最多一个自然 Episode。

来源：`src/trading_kernel/domain/detectors/sor.py`、
`src/trading_kernel/domain/strategy_registry.py`、
`src/trading_kernel/application/produce_strategy_signal.py`。

## 3. Analysis And Research Hypothesis

### 3.1 Primary hypothesis

V0 的 Primary Hypothesis 是：

> 在相同 Session 和相同 SOR v4 语义下，Pre-trigger OR 相对近期正常波动越窄，后续
> Trigger 越可能保留足够的扩张空间，使 pre-TP1-policy-qualified `+3R` 事件在有限选择名额中
> 更集中。

形式化表达：

```text
lower pre_or_width_atr14
-> higher SOR tail opportunity density
```

V0 不假设“越窄越好”无限成立。Activity floor 用于排除没有最低交易能量的异常低活跃
状态，但 V0 不为多个特征建立综合 Score。

### 3.2 Evidence class limitation

`OR Width / ATR` 假设来自已观察历史数据，因此同一历史窗口上的 V0 Replay 属于：

```text
Development Evidence
```

它可以回答无未来信息的 Pre-trigger 版本是否仍具备机制一致性和历史区分度，但不能成为
真正独立的样本外证明。只有冻结 V0 后的 Forward Shadow 才属于 Prospective Evidence。

## 4. Scope

### 4.1 In scope

- Crypto `SOR-001` v4 的 LONG 与 SHORT Event；
- 24-symbol 固定 Research Panel；
- `2024-01-01` 至 `2026-08-18` 的 Historical Replay；
- `UTC 01:00` SelectionSnapshot；
- Point-in-Time OHLCV、Quote Volume 和数据完整性；
- Pre-trigger OR Width / ATR14；
- Dynamic、Static、Random、All Selection-ready、All Panel、Near、Not Selected 对照；
- exact SOR v4 Trigger 与 policy-aware Path Outcome；
- Forward Shadow 是否值得开始的 Advance/Revise/Stop 决策。

Historical Replay 的 exact Session range 是：

```text
2024-01-01T00:00:00Z <= session_start < 2026-08-19T00:00:00Z
```

`2026-08-19` 与 `2026-08-20` 不作为 V0 Selection Session；其 K 线仅可用于补全最后一个
Historical Session 的冻结 96-bar Path。冻结研究已声明第一个 prospective untouched day
为 **2026-08-21**，Forward Shadow 不得把已用于历史 Path 的日期重新称为未来证据。

### 4.2 Explicitly out of scope

- 生产 StrategyUniverse 自动切换；
- Crypto `SOR-001` pause/resume；
- Policy、风险、保证金、杠杆、并发或资金变更；
- Ticket、AdmissionDecision、CapacityClaim、Command、Position、Settlement 或 Review；
- 实际 Fill、手续费、Funding、Spread、Slippage 或 Net PnL；
- AI 选币、Owner 盘感二次排序、综合 Fit Score 或机器学习；
- 历史全市场 Point-in-Time Universe 重建；
- 全市场 Collector、Research Service、ETL 平台或 Research Registry；
- CPM、BRF2、MPG、MI 或 TradFi SOR；
- SOR Re-entry；
- Forward Shadow 的生产 Schema、Worker、API 和页面设计；
- Daily Universe Apply 的 `01:00 -> 01:15` 运行时切换实现。

## 5. Authority And Identity

### 5.1 Authority

| Concern | Authority |
| --- | --- |
| SOR strategy semantics | Current tracked Strategy Registry and `SORDetector` |
| Research rule | Frozen `SelectionSpec` in this design and exact run manifest |
| Historical market input | Binance official USDⓈ-M Kline archive/cache plus file digests |
| Research output | Disposable run artifacts; display and analysis only |
| Production Universe | PostgreSQL StrategyUniverse current pointer; unchanged by V0 |
| Production capital and Entry | Owner Policy and official Kernel; unchanged by V0 |

Markdown、JSON、CSV、Parquet、本地缓存和研究报告都不能成为生产运行时权威。

### 5.2 Exact identities

| Identity | Frozen value or rule |
| --- | --- |
| Research spec | `sor-dynamic-selection-v0` |
| StrategyGroup | `SOR-001` |
| StrategyVersion | `sgv:SOR-001:v4` |
| Long EventSpec | `event_spec:SOR-001:SOR-LONG:v4` |
| Short EventSpec | `event_spec:SOR-001:SOR-SHORT:v4` |
| Selection timezone | UTC |
| Selection time | `01:00:00` |
| SelectionSnapshot ID | `selection:sor-dynamic-selection-v0:<session_start_ms>` |
| Member decision ID | `<selection_snapshot_id>:<exchange_instrument_id>` |

LONG 与 SHORT 共用同一 Instrument SelectionSnapshot，但 Outcome 必须按方向分别统计。
这样保持 V0 特征的方向中立性，并避免在第一版同时搜索两套规则。

## 6. Candidate Panel

### 6.1 Frozen symbols

V0 固定复用 Instrument Effect v1 的 24-symbol panel：

| Group | Symbols |
| --- | --- |
| Large / liquid | BTCUSDT、ETHUSDT、BNBUSDT、SOLUSDT、XRPUSDT、DOGEUSDT |
| Established alts | ADAUSDT、AVAXUSDT、LINKUSDT、LTCUSDT、BCHUSDT、DOTUSDT |
| Mid-cap / heterogeneous | NEARUSDT、ATOMUSDT、FILUSDT、ETCUSDT、APTUSDT、OPUSDT |
| Additional panel | ARBUSDT、INJUSDT、SUIUSDT、TRXUSDT、UNIUSDT、RUNEUSDT |

候选列表在读取 V0 结果前不得增加、删除或替换。某个 Instrument 在具体 Session 是否
Qualified 由 Point-in-Time 数据决定，不通过事后删除 Symbol 处理坏结果。

### 6.2 Fixed-panel limitation

该面板是今天冻结的长期存续 Instrument 集，不是每个历史日期的完整 Binance 市场。
因此 V0 只允许声称：

> 固定 24-symbol panel 内的动态状态选择结果。

不允许声称：

> 历史全市场 Dynamic Universe 的收益或最优 Selector。

## 7. Selection Clock And Data Cutoff

### 7.1 Clock

每个 UTC Session `D` 的 Selection Clock 为：

```text
D 01:00:00 UTC
```

此时以下四根 Opening Range K 线已经闭合：

```text
[00:00, 00:15)
[00:15, 00:30)
[00:30, 00:45)
[00:45, 01:00)
```

任何 `open_time >= D 01:00:00` 的 K 线、Trigger、Path、未来 Volume、未来产品状态或
Outcome 都不得进入 Selection Feature。

### 7.2 Point-in-Time input window

每个 Instrument 的选择输入最多读取：

| Input | Exact closed window |
| --- | --- |
| Opening Range | `D 00:00 <= open_time < D 01:00` |
| Pre-OR ATR bars | `D-1 20:30 <= open_time < D 00:00` 的最后 14 根 15m K 线 |
| ATR previous close | `D-1 20:15` K 线 Close |
| Trailing activity | `D-1 01:00 <= open_time < D 01:00` 的 96 根 15m K 线 |
| Optional pre-session extension | `D-1 20:00` Close 到 `D 00:00` Close |

所有输入均必须在 Selection Clock 前闭合。

## 8. Feature Contract

### 8.1 Primary feature: Pre-trigger OR Width / ATR14

Opening Range：

```text
or_high  = max(high of four OR bars)
or_low   = min(low of four OR bars)
or_width = or_high - or_low
```

True Range：

```text
tr_i = max(
    high_i - low_i,
    abs(high_i - previous_close_i),
    abs(low_i - previous_close_i),
)
```

Pre-OR ATR14：

```text
pre_or_atr14 = arithmetic_mean(last 14 pre-OR true ranges)
```

Primary Feature：

```text
pre_or_width_atr14 = or_width / pre_or_atr14
```

要求：

- ATR 不包含四根 OR K 线；
- ATR 不包含任何 Trigger K 线；
- `pre_or_atr14 > 0`；
- Price geometry 使用 `Decimal`；
- Statistical aggregate 可在冻结明细基础上使用 `float`。

### 8.2 Activity feature

```text
trailing_24h_quote_volume =
sum(quote_volume for the 96 bars ending at UTC 01:00)
```

V0 固定最低 Activity：

```text
trailing_24h_quote_volume >= 20,000,000 USDT
```

该值是宽松、固定、金额可解释的最低门槛，不是从 Tail Outcome 优化得到的最佳阈值。
低于该值的 Instrument 标记为 `status=INELIGIBLE`、`primary_reason=LOW_ACTIVITY`，但其
未来 Outcome 仍可作为 All Panel Diagnostic 记录，不能从数据集中删除。

### 8.3 Shadow-only diagnostics

以下 Feature 必须计算或预留，但不参与 V0 Qualification、排序或名额：

| Feature | Definition or boundary | V0 use |
| --- | --- | --- |
| Pre-session signed extension / ATR | `(close_00:00 - close_previous_20:00) / pre_or_atr14` | Diagnostic only |
| Pre-session absolute extension / ATR | signed extension 的绝对值 | Diagnostic only |
| OR quote volume | 四根 OR K 线 Quote Volume 总和 | Diagnostic only |
| Relative OR volume | OR Quote Volume / 前 20 个可用 Session 的 OR Volume 中位数 | Diagnostic only |
| Trigger-time OR/ATR | 复现 Instrument Effect v1 指标 | Outcome-side diagnostic only |
| Trigger hour | Trigger Close 所在 UTC 小时 | Outcome-side diagnostic only |
| BTC regime | 不在 V0 定义具体算法 | Reserved, not computed unless separately frozen |
| Market breadth | 不在 V0 定义具体算法 | Reserved, not computed unless separately frozen |

任何 Shadow-only Feature 在看到 V0 结果后加入排序，都必须创建新的
`sor-dynamic-selection-v1`，不得覆盖 V0。

`Relative OR volume` 在不足 20 个历史完整 Session 时输出 `null` 与明确原因，不触发
INELIGIBLE，也不要求为 V0 首批日期额外下载更早数据。

## 9. Qualification Contract

### 9.1 Hard qualification

一个 Instrument 在 Session `D` 只有同时满足以下条件才进入 Selection-ready Set：

1. Instrument 在冻结 24-symbol panel 中；
2. Selection Clock 前所需 15m K 线连续、唯一、顺序正确；
3. 四根 OR K 线完整；
4. ATR previous close 和 14 根 Pre-OR K 线完整；
5. Trailing 24h 的 96 根 K 线完整；
6. OHLC、Quote Volume 均为有限、非负且价格为正；
7. `or_high > or_low`；
8. `pre_or_atr14 > 0`；
9. `trailing_24h_quote_volume >= 20,000,000 USDT`。

历史数据无法完整重建 Bid/Ask Spread 和所有 Contract Status 变化，因此它们不能被伪造
成 Historical Qualification。Forward Shadow 可额外记录当前 Product/Spread 异常，
但必须单独标明 `forward_operational_invalidation`，不能回填历史。

上述 **Selection-ready** 定义只属于 Dynamic、Random 和 All Selection-ready Policy。
它不是 Static 7 的准入规则。Static 7 的成员身份始终固定；只要对应 Session 的 exact
SOR v4 Detector 与 Outcome 输入完整，就保留其计划 Slot。Static 成员低于 `20M` 时仍是
Static Slot，同时在诊断字段中记录 `below_dynamic_activity_floor=true`。这可以防止
Dynamic 的资格规则把 Static 基线事后改造成另一套策略。

### 9.2 Member statuses

每个面板成员必须得到且只能得到一个状态：

| Status | Meaning |
| --- | --- |
| `INELIGIBLE` | 数据、几何或 Activity 最低条件失败 |
| `SELECTED` | Selection-ready 排名进入前 7 |
| `NEAR_THRESHOLD` | Selection-ready 排名第 8–14 |
| `NOT_SELECTED` | Selection-ready 但排名低于 14，或因 Snapshot EMPTY 未分配名额 |

每个 `INELIGIBLE` 决策必须冻结一个 Primary Reason：

```text
OR_DATA_INCOMPLETE
PRE_CUTOFF_DATA_INCOMPLETE
INVALID_PRICE_OR_VOLUME
INVALID_OR_GEOMETRY
INVALID_ATR
LOW_ACTIVITY
```

Primary Reason 使用上述顺序的第一个命中项。实现可以同时保存排序后的
`secondary_reasons`，但不得因 Outcome 或人工判断改变 Primary Reason。四根 OR K 线缺失、
重复或时间不连续归为 `OR_DATA_INCOMPLETE`；ATR/Activity 所需的其他 Pre-cutoff K 线缺失、
重复或时间不连续归为 `PRE_CUTOFF_DATA_INCOMPLETE`。

### 9.3 EMPTY semantics

V0 的目标集合大小固定为 7。若 Selection-ready Instrument 少于 7 个：

```text
empty = true
selected_count = 0
empty_reason = INSUFFICIENT_SELECTION_READY_INSTRUMENTS
```

V0 不在该 Session 强行选择少于 7 个 Instrument，因为 V0 冻结的问题就是“固定容量 7
相对 Static 7 和 Random 7 是否更好”。虽然 Directional Slot-day 可以归一化不同集合
大小，但允许 `k=1..6` 仍会改变容量暴露、Random 抽样和研究 Policy。所有合格成员保留为
`NOT_SELECTED`，原因记录为 `SNAPSHOT_EMPTY`。

`EMPTY` 是 fail-closed 的研究策略语义，不删除该 Session。Static 7、All Panel 以及所有
可计算的未来 Outcome 仍须保留；Dynamic/Random 的计划 Slot 记录为未分配，EMPTY Session
进入 EMPTY rate 和 Coverage 报告，但不进入非 EMPTY 的 paired Primary lift。

## 10. Selection Policy

### 10.1 Ranking

Selection-ready Instrument 使用以下稳定排序：

```text
1. pre_or_width_atr14 ascending
2. trailing_24h_quote_volume descending
3. canonical exchange_instrument_id ascending
```

排序规则禁止使用历史 Symbol 表现、未来 Trigger、未来 Path、未来 Volume 或人工判断。

### 10.2 Cohorts

```text
rank 1..7   -> SELECTED
rank 8..14  -> NEAR_THRESHOLD
rank 15..N  -> NOT_SELECTED
```

V0 不使用综合分数，不对各 Feature 设置权重，不把 NEAR/NOT_SELECTED 称为不可交易标的。

### 10.3 Shared LONG/SHORT selection

V0 对 LONG 与 SHORT 使用同一 Selected Set，原因是：

1. OR Width、ATR 和 Activity 是 Instrument/Session 状态，不依赖未来方向；
2. SOR LONG/SHORT 使用相同 Opening Range，只是突破方向不同；
3. 分方向建模会增加搜索空间和 Researcher Overfitting 风险；
4. Outcome 仍按 LONG、SHORT 和 Combined 三层分别呈现。

## 11. Control Policies

### 11.1 Dynamic Selected 7

V0 正式实验组，每个非 EMPTY Session 固定 7 个 Instrument。

### 11.2 Current Static 7

冻结为当前 Crypto 第一批成员：

```text
BTCUSDT
ETHUSDT
SOLUSDT
BNBUSDT
XRPUSDT
DOGEUSDT
ADAUSDT
```

Static 7 不因历史表现或 V0 结果更换成员。

Static 7 不应用 Dynamic 的 `20M` Activity floor、OR/ATR 排名或 Selection-ready 状态。
每个 Session 固定计划 7 个成员；成员 Outcome 缺失时标记 `INCOMPLETE`，不得换入其他
Instrument。只有 exact SOR Outcome 输入缺失才使该 Static Slot 不可评价。

### 11.3 Random Selection-ready 7

Random Control 只能从同一 Session 的 Selection-ready Set 中无放回抽取 7 个 Instrument。

为避免 Python PRNG 或 library version 改变成员，V0 不调用 `random.shuffle()`。每个
Instrument 计算以下 canonical UTF-8 framed identity 的 SHA-256，并选择 digest
字典序最小的 7 个：

```text
sha256(
    canonical_json([
        research_spec_id,
        session_start_ms,
        random_replicate_id,
        exchange_instrument_id
    ])
)
```

`canonical_json` 精确定义为 UTF-8 编码、数组字段顺序固定、整数使用十进制 JSON number、
`ensure_ascii=false`、`separators=(",", ":")` 且无额外空白。

Historical Replay 生成：

- `random_replicate_id = 0` 的 `random_reference_7`，用于逐 Session 检查；
- `random_replicate_id = 0..99` 的 **100 个** deterministic Random 7 replicates，形成
  随机选择结果分布；ID 0 同时就是 reference，不额外生成第 101 个样本。

随机对照只判断“任意选 7 个”是否已经足够，不承担因果证明。

### 11.4 All Selection-ready

同一 Session 的全部 Selection-ready Instrument，表达通过 V0 最低资格后的机会供给。
它不是 24-symbol 面板的完整机会供给上限，正式 Policy ID 为：

```text
all_selection_ready
```

### 11.5 All Panel Diagnostic

所有冻结 Panel 成员只要 exact SOR Outcome 输入完整，就记录未来 Outcome，包括低于
Activity floor 的 Instrument。它只用于诊断资格规则丢失了多少机会，正式 Policy ID 为：

```text
all_panel_diagnostic
```

All Panel 不参与 Dynamic 名额、Random 抽样或 Primary Advance Gate。

### 11.6 Near And Not Selected

必须继续计算未来 SOR Outcome，用于回答：

- Selected 是否优于 Near；
- Near 是否优于 Not Selected；
- Selection 是否只是在不同标签间随机移动结果；
- 多少 Tail Event 被留在 Selected 之外。

## 12. Exact SOR Replay

### 12.1 Detector ownership

实现必须直接导入当前 tracked `SORDetector` 或公共
`evaluate_strategy_snapshot()` 边界，不复制 Trigger 公式。

每个运行 Manifest 冻结：

- exact git commit；
- SOR detector file SHA-256；
- Strategy Registry file SHA-256；
- Exit Policy file SHA-256；
- SelectionSpec digest；
- input file digests；
- research code digest；
- Python 和 library versions。

Source drift 时运行失败，除非先形成新的语义审查和 Research Spec 版本。

### 12.2 Episode rule

每个 Instrument、Side、UTC Session：

- 最多接受第一个自然 SOR Trigger；
- 后续同 Session 再次突破不形成第二个 Episode；
- LONG 与 SHORT 独立；
- `23:45–24:00` K 线不能为旧 Session 创建新 Trigger。

### 12.3 Signal-basis Entry

```text
entry_reference = trigger candle close
formal_stop     = opposite OR boundary
formal_r        = abs(entry_reference - formal_stop)
```

这是 **Signal-basis Path R**，不是 action-time quote、实际 Fill、Ticket R、Net R 或 PnL。

### 12.4 Policy-aware endpoints

Primary Endpoint 延续冻结研究语义：

```text
policy_tail3_cons
```

它要求：

1. Episode 在 formal stop、TP1 前 closed-candle OR reclaim 或 Session expiry 前先达到
   `+1R`；
2. 随后或同时在冻结 96-bar horizon 内、原始 formal stop 前达到 `+3R`；
3. 未被更低周期顺序证明的 same-bar target/stop ambiguity 按保守失败处理。

该指标只把真实 **pre-TP1 Reclaim / Session / Stop** 约束带入 `+1R` 资格，然后观察
原始 formal stop 前是否存在 `+3R` 价格路径。它不模拟 TP1 后 Break-even Floor、
Structural ATR Runner、真实成交、费用或资金费。因此正式含义是：

```text
pre-TP1-policy-qualified tail opportunity supply
```

它不是完整生命周期的“可实现 Runner 收益”，也不是 Net PnL。

同时输出：

- policy-attainable `+1R`；
- policy-attainable `+5R`；
- raw `+1R / +3R / +5R before -1R`；
- MFE_R / MAE_R；
- time-to-level；
- reclaim-before-TP1；
- formal stop first；
- Session expiry；
- `ambiguous_same_bar`；
- incomplete path。

### 12.5 Same-bar ambiguity

若一根 15m K 线同时触达 favorable target 与 formal stop：

1. 有对应 1m 数据时按 1m 顺序解析；
2. 若同一 1m K 线仍同时触达，则保留 ambiguity；
3. 没有 1m 数据时保留 ambiguity；
4. Primary 结果按 conservative failure；
5. Optimistic bound 单独输出，不能替代 Primary。

## 13. Comparison Denominators

### 13.1 Directional slot-day

一个 Policy 在一个完整 UTC Session 为一个 Instrument 的一个 Side 分配观察名额，定义为：

```text
directional slot-day
```

Dynamic、Static 和 Random 的目标均为每个 Side **7 directional slot-days/session**；
LONG 与 SHORT 合并结果的计划分母为 **14 directional slot-days/session**。一个完整、
无 Trigger 的 directional slot-day 必须进入分母，不能只统计已触发 Event。该定义保证
Combined Rate 仍具有单一、可比较的分母，不把两个方向的 Event 除以 7 个 Instrument-day。

### 13.2 Complete outcome

Selection 时只使用 Pre-cutoff Data。Selection 后路径缺失不能反向改变资格：

```text
selection remains frozen
outcome_complete = false
```

Outcome completeness 的 exact 语义是：

- 无自然 Trigger：该 UTC Session 的 96 根 15m K 线完整，才能声明 complete no-trigger；
- 有自然 Trigger：除完整 Session 外，还必须存在 Trigger 之后连续、唯一的 96 根 15m
  Path K 线；
- `23:45` open 的最后一根 Session K 线不允许创建旧 Session Trigger，但仍属于 no-trigger
  completeness 和前序 Path 数据。

Primary paired comparison 只使用以下 Session：

1. Dynamic Snapshot 非 EMPTY；
2. Dynamic 7 与 Static 7 的 exact SOR Outcome 均完整；
3. LONG、SHORT 两个方向均可评价。

所有计划 Directional Slot、Incomplete Slot、EMPTY 和排除原因必须单独报告，不得把
缺失结果按 0 或失败处理。Standalone complete-case 指标可以输出，但 Advance Gate 只读取
同一组 paired Sessions。

为防止 complete-case selection bias，以下任一条件成立时不得 Advance：

- paired Session coverage 低于所有非 EMPTY 计划 Session 的 **98%**；
- Dynamic 与 Static 的 complete directional-slot coverage 相差超过 **1 percentage point**；
- Incomplete 原因与 Dynamic rank、Instrument 或 Outcome cohort 呈明显集中，且无法由
  数据边界解释。

Random envelope 使用同一批 Primary paired Sessions。每个 replicate 若在其中存在
Incomplete selected Directional Slot，则该 replicate 不进入 percentile，且整个运行不得
Advance，直到 coverage 问题被修复或进入 V1。

### 13.3 Paired time blocks

Aggregate 之外，从 `2024-01-01T00:00:00Z` 开始切分冻结的连续
**90-calendar-day blocks**，边界采用左闭右开。最后不足 90 天的 Block 保留但标记
`partial_block=true`，不进入 60% 稳定性门槛。

## 14. Metrics

### 14.1 Primary policy metric

```text
Tail3 events per 100 directional slot-days
= 100 * policy_tail3_cons_count / complete_directional_slot_days
```

它同时惩罚：

- 选择了没有 Trigger 的 Instrument；
- Trigger 频率不足；
- Trigger 无法产生合法 `+3R` Path；
- 强行每天填满名额但没有机会。

### 14.2 Guardrail metric

```text
Tail3 per Trigger
= policy_tail3_cons_count / natural_trigger_count
```

用于防止 Dynamic 仅靠增加低质量 Trigger 数量提高 slot-day 结果。

### 14.3 Required metrics

| Metric | Required grouping |
| --- | --- |
| Complete directional slot-days | Policy、Direction、Time Block |
| Natural Triggers / 100 directional slot-days | Policy、Direction、Time Block |
| TP1 / Trigger | Policy、Direction、Time Block |
| Tail3 / Trigger | Policy、Direction、Time Block |
| Tail5 / Trigger | Policy、Direction、Time Block |
| Tail3 / 100 directional slot-days | Policy、Direction、Time Block |
| Tail events / Session | Policy、Direction |
| Reclaim rate | Policy、Direction |
| Median/P90 MFE_R | Policy、Direction |
| Median/P90 MAE_R | Policy、Direction |
| Static capture | Static Tail3 / All Panel Tail3 |
| Dynamic capture | Dynamic Tail3 / All Panel Tail3 |
| Selection-ready capture | All Selection-ready Tail3 / All Panel Tail3 |
| Selection opportunity loss | Non-selected Selection-ready Tail3 / All Selection-ready Tail3 |
| Qualification opportunity loss | Ineligible-but-evaluable Tail3 / All Panel Tail3 |
| Contribution concentration | Instrument、Time Block、Direction |
| EMPTY rate | Session |
| Data/incomplete rate | Instrument、Session、Reason |

## 15. Decision Contract

V0 Replay 只决定是否值得进入 **Forward Shadow**，不决定生产 Apply。

除非条款明确写 Direction，Advance/Revise/Stop 的 Primary、Random、Block、贡献和梯度
判定均使用 **Combined directional slot-days**；LONG 与 SHORT 必须分别报告，不能用
Combined 隐藏方向性恶化。

### 15.1 ADVANCE_TO_FORWARD_SHADOW

必须同时满足：

1. Dynamic 的 Primary Metric 相对 Static 提升至少 **10%**，计算为
   `(dynamic_rate - static_rate) / static_rate`；
2. Dynamic Primary Metric 高于同一 paired Sessions 上 Random 100-replicate 分布的
   **75th percentile**；
3. Dynamic 相对 Static 的 Primary Metric 在至少 **60% 的完整 90-day blocks** 为正；
4. Dynamic-exclusive Tail3 Event 来自至少 **3 个 Instrument**；
5. Dynamic-exclusive Tail3 Event 来自至少 **3 个完整 Time Block**；
6. 单一 Instrument 不贡献超过 **50%** 的 Dynamic-exclusive Tail3；
7. Static `Tail3/Trigger > 0` 时，Dynamic / Static 的 Tail3/Trigger ratio 不低于
   **0.90**；Static 为 0 时并列报告绝对计数，不因该 Guardrail 单独阻止 Advance；
8. LONG 与 SHORT 各自的 Dynamic Primary Metric 不得比同方向 Static 低超过 **20%**；
   某方向 Static 为 0 时并列报告绝对计数，不因该条单独阻止 Advance；
9. Combined Selected Primary Metric 同时高于 Near 与 Not Selected；
10. paired Session coverage 与 policy coverage difference 通过 13.2 的门槛；
11. Source parity、cutoff audit、determinism 和数据 QC 全部通过。

`Dynamic-exclusive Tail3` 指 paired Session 中由 Dynamic 选择、Static 未选择且产生
`policy_tail3_cons=1` 的 Directional Slot。Static-exclusive Tail3 必须并列报告；总体
10% lift 继续基于两套 Policy 的净计数差，不能用 exclusive 计数替代。

相对提升在 Static Primary Metric 为 0 时不计算；此时要求 Dynamic 至少产生 3 个独立
Tail3 Event，并由绝对差、Random 分布和贡献分散共同判断。

### 15.2 REVISE_ONCE

满足以下任一情况时进入一次性 Revise：

- Aggregate 优于 Static/Random，但 Time Block 稳定性不足；
- Selected 优于 Static，但不优于 Random 75th percentile；
- Primary 正向，但结果由单一 Instrument 或单一 Block 过度集中；
- Activity floor 导致大量 EMPTY 或异常 Opportunity Loss；
- Pre-trigger OR/ATR 有方向性，但 Near/Not Selected 梯度不清晰；
- Combined 优势掩盖 LONG 或 SHORT 方向超过 20% 的反向恶化；
- Coverage 低于 98%、Policy coverage 差异超过 1 percentage point，或缺失分布存在
  可修复的数据边界问题。

Revise 只能修改一个明确假设，例如 Activity floor、Top N 或加入一个 Shadow-only
Feature。修改后必须创建 **V1**、新的 SelectionSpec digest 和新的结果目录，不能重写 V0。

### 15.3 STOP

满足以下任一情况时停止当前 V0 方向：

- Dynamic Primary Metric 同时不优于 Static 和 Random median；
- Dynamic Tail3/Trigger 相对 Static 下降超过 **20%**；
- Selected 不优于 Near/Not Selected，且没有可解释梯度；
- 优势仅来自一个 Instrument、一个 Block 或少数 ambiguous outcome；
- Pre-trigger Feature 无法复现 Trigger-time Geometry 方向；
- 数据或实现无法证明 cutoff、detector parity 或 deterministic output。

STOP 后优先返回 SOR Geometry/EventSpec 诊断，不直接搜索更多 Feature。

## 16. Data And File Ownership

### 16.1 Input

首轮优先复用 `SOR-INSTRUMENT-EFFECT-v1` 的冻结 Binance 15m Cache，避免重复下载和
数据版本漂移。若需要 1m ambiguity resolver，只下载精确的 ambiguous 15m windows。

所有输入文件必须记录：

- canonical path label；
- size；
- SHA-256；
- first/last open time；
- row count；
- duplicate/gap count。

### 16.2 Output location

生成物必须位于仓库外，例如：

```text
~/research/sor-dynamic-selection-v0/runs/<run_id>/
```

不得写入 `docs/current`、`src/trading_kernel`、PostgreSQL 或生产服务器。

### 16.3 Required artifacts

| Artifact | Purpose |
| --- | --- |
| `selection_spec.json` | 冻结所有规则和参数 |
| `run_manifest.json` | Git/source/input/code/environment digests |
| `selection_snapshots.csv.gz` | 每个 Session 的 Snapshot 与 EMPTY 状态 |
| `member_decisions.csv.gz` | 每个 Instrument 的 Feature、状态、排名和原因 |
| `sor_events.csv.gz` | exact SOR v4 Event/Path 明细 |
| `policy_daily.csv.gz` | Dynamic/Static/Random/All Selection-ready/All Panel/Near/Not Selected 的日级结果 |
| `random_envelope.csv.gz` | 100 个 Random replicates 的分布 |
| `time_block_summary.csv` | 90-day block 稳定性 |
| `contribution_summary.csv` | Instrument/Block/Direction 贡献集中度 |
| `qc.json` | Cutoff、gap、duplicate、parity、ambiguity 和 coverage |
| `decision.json` | Advance/Revise/Stop 与逐条门槛结果 |

运行结束后归档整个 run directory 并输出 SHA-256。生成物不进入 Git。

## 17. Failure Semantics

| Failure | Required outcome |
| --- | --- |
| Source hash drift | Fail run before reading outcomes |
| SelectionSpec mismatch | Fail run |
| Pre-cutoff candle gap | Instrument `INELIGIBLE`; preserve reason |
| Duplicate/irregular candle | Instrument `INELIGIBLE`; preserve reason |
| Fewer than 7 ready Instruments | Snapshot `EMPTY`; select none |
| Post-cutoff path incomplete | Preserve Selection; Outcome `INCOMPLETE` |
| Same-bar unresolved | Preserve ambiguity; conservative Primary |
| Random seed nondeterminism | Fail determinism test and run |
| Detector parity failure | Fail run |
| Network/download failure | Preserve existing cache; no partial run claim |
| PostgreSQL or exchange access attempt | Fail architecture test |
| Partial output directory | Mark run `INCOMPLETE`; never publish Decision |

研究失败不产生生产 Incident，因为 V0 不属于生产 Runtime；但失败原因必须进入 `qc.json`
和本地运行日志。

## 18. Runtime, Transaction And Performance Boundary

### 18.1 Runtime ownership

V0 是一次性本地 CLI/研究程序，不属于 Observation、Entry、Lifecycle 或
Reconciliation Worker。

### 18.2 Transactions and network

- 不打开生产 PostgreSQL 事务；
- 不读取生产 PostgreSQL 作为研究输入；
- 不初始化 Venue trading client；
- 不调用任何 Binance private endpoint；
- 不进行 exchange write；
- Public historical data download 发生在研究计算之外或显式 download step；
- 研究计算只读冻结文件并写仓库外结果目录。

### 18.3 Bounded resource envelope

当前输入约为 24 个 Instrument、约 2.5 年 15m K 线和约 100 MB 量级缓存。实现应：

- 按 Symbol 或日期块处理，不复制多份完整 DataFrame；
- Random 100 replicates 只保存成员和聚合结果，不复制 Event 明细；
- 不启动并行全核任务作为默认；
- 不在生产 2C4G 主机运行；
- 不创建常驻进程或定时任务。

## 19. Necessary Tests

只增加保护当前研究合同的测试，不运行 Trading Kernel Release 全量认证。

### 19.1 Unit tests

| Test | Assertion |
| --- | --- |
| Selection cutoff | Feature 不读取 `open_time >= UTC 01:00` |
| OR geometry | 精确使用四根 OR K 线 |
| Pre-OR ATR | ATR 使用 OR 前 14 根 TR，明确排除 OR bars |
| Activity window | Quote Volume 精确覆盖截止 01:00 的 96 根 K 线 |
| Qualification | 每类失败产生唯一 Primary Reason |
| Stable ranking | OR/ATR、Volume、Instrument ID tie-break 正确 |
| Cohorts | Top 7、Near 7、Not Selected 正确且互斥 |
| EMPTY | Ready count < 7 时无 Selected 成员 |
| Random determinism | 相同 Spec/Session/replicate 得到相同成员 |
| LONG/SHORT sharing | 同一 Session 使用同一 SelectionSnapshot |

### 19.2 Semantic tests

| Test | Assertion |
| --- | --- |
| Detector import | 实现导入 official SOR detector，不复制 Trigger 公式 |
| Live/Replay parity | 相同 MarketSnapshot 得到相同 DetectorResult |
| Episode identity | 每 Symbol/Side/Session 最多一个自然 Event |
| Policy TP1/Reclaim | TP1 前 reclaim、stop、session expiry 顺序正确 |
| Tail direction | LONG/SHORT `+1R/+3R/+5R` 方向正确 |
| Same-bar ambiguity | 1m resolver 与 conservative/optimistic 边界正确 |
| Zero Trigger denominator | 完整无 Trigger slot-day 进入 Primary 分母 |
| Incomplete outcome | 不反向修改 Selection，不按失败或 0 处理 |
| Static baseline independence | Static 成员不因 Dynamic Activity floor 或排名被替换/删除 |
| All-policy boundary | All Selection-ready 与 All Panel Diagnostic 口径不混淆 |
| Directional denominator | Combined 分母为 LONG/SHORT directional slots 之和 |
| Coverage gate | paired coverage 与 policy coverage difference 超界时禁止 Advance |

### 19.3 Architecture tests

| Test | Assertion |
| --- | --- |
| No production DB | 研究模块不导入 Kernel PostgreSQL repositories |
| No trading client | 不导入 private Venue adapter 或 Exchange Command |
| No runtime files | 不向生产 runtime/output authority 路径写文件 |
| Generated output ignored | 结果目录不进入 Git |
| Source freeze | Source/Spec/Input digest drift 时 fail closed |

### 19.4 Proportional verification

实施阶段只需要：

1. 新增研究 unit/semantic/architecture tests；
2. 现有 `test_live_replay_detector_parity.py`；
3. 当前文档权威测试；
4. `ruff` 仅检查新增研究代码；
5. `mypy` 仅检查新增研究代码；
6. `git diff --check`。

不运行 Kernel 全量 unit/integration/full-chain Release certification，因为 V0 不改变生产
Kernel、Schema、Policy、Worker 或部署分类。

## 20. Future Production Boundary

> **Historical clause only:** 本节记录 Replay 冻结时尚未发生的架构判断。Owner 后续已取消
> 独立 Forward Shadow，并在生产设计中冻结 `Ready=1..7`、serial LONG/SHORT warming、
> atomic pair switch 与 explicit `FALLBACK_PREVIOUS`。当前权威 successor 见文首链接。

V0 Replay 通过后，Forward Shadow 仍需独立设计。未来生产概念必须满足：

```text
Owner Allowed Universe
∩ Point-in-Time Tradeability
∩ approved Selected Set
-> Effective Tradable Set
```

Selection 必须位于 **StrategySignal 之前**，不能放进 Admission。未选 Instrument 可能
没有 Signal，因此未来 SelectionSnapshot 必须拥有独立身份，不能只通过
`signal_event_id` 关联。

若最终进入 Apply：

1. Selected Set 形成新的 Desired StrategyUniverse Version；
2. 复用 Warming、Certification 和原子 Activation；
3. 不原地修改 Active Universe；
4. 不改变已存在 Signal、Claim 或 Ticket；
5. 不增加新的资金 Policy 或单 Ticket 风险参数；
6. 异常时复用 StrategyGroup pause；
7. Crypto `SOR-001` resume 仍需 Owner 明确授权。

当前未解决的生产问题是：

```text
UTC 01:00 Selection
-> Desired Universe
-> Warming / Certification / Activation
-> earliest 01:15 Trigger close
```

当前能力是否能在 15 分钟窗口内稳定完成尚无直接证据。该问题不阻塞 Replay，但在
Forward Shadow 后、任何 Apply 设计前必须单独验证。

## 21. Options Considered

下表是 Replay 设计冻结时的 options，不代表当前阶段决策；其中 “Production Selector
immediately = Reject” 已被后续 Owner 小资金生产实验路线取代。

| Option | Benefit | Cost / risk | Decision |
| --- | --- | --- | --- |
| Static good-symbol list | 最简单 | 已无 OOS persistence 支持 | Reject |
| AI/LLM daily selection | 表达灵活 | 不稳定、难复现、难审计 | Reject for V0 |
| Multi-feature weighted score | 可排序 | 权重高度可过拟合 | Reject for V0 |
| Rule tree with absolute thresholds | 可解释、允许 EMPTY | 多阈值仍可能过拟合 | Only Activity floor adopted |
| Relative OR/ATR Top 7 | 简单、跨 Regime、自适应 | 每天会选择，除非池不足 | Adopt |
| Cross-sectional Activity percentile | 自适应 | 每天人为淘汰固定比例，资格语义漂移 | Reject for V0 |
| Fixed Activity floor | 金额可解释、可复现 | 阈值仍需 Forward 检验 | Adopt |
| Separate LONG/SHORT selectors | 可能提高方向适配 | 增加搜索空间和样本切分 | Defer |
| Production Selector immediately | 快速实盘反馈 | 研究与执行同时变化，无法归因 | Reject |

## 22. Completion Criteria

详细设计完成并可进入执行文档阶段，需要：

1. Owner 或复核模型确认 Selection Clock、Candidate Panel、Feature、Activity floor、
   Top N、对照和 Decision Contract；
2. 当前路线图与本设计阶段顺序一致；
3. 本设计不包含生产授权；
4. 文档权威测试通过；
5. `git diff --check` 通过；
6. 所有研究假设、已知限制和未来生产问题均显式记录。

实施完成的 Done 条件将由后续 Execution Plan 定义。本设计本身不授权开始编码。

## 23. Review Focus

外部复核应重点挑战以下问题：

1. **Primary Feature**：Pre-OR ATR 是否应排除 OR bars；
2. **Activity Floor**：固定 `20M USDT / 24h` 是否足够宽松且可解释；
3. **Top N**：固定 7 是否是与现有 Static Universe 最公平的选择；
4. **Static fairness**：Static 不应用 Dynamic Activity floor 是否是正确基线；
5. **EMPTY**：Ready count < 7 时全空，而不是选择更小集合是否合理；
6. **Primary Metric**：Tail3 / 100 directional slot-days 是否比 Tail3 / Trigger 更适合选择问题；
7. **Random Control**：100 replicates 与 75th percentile 是否足够且不过度；
8. **Decision Gate**：10% lift、60% blocks、3 Instrument/3 Block 和 50% concentration
   是否适合个人小资金实验；
9. **Direction guard**：Combined 优势下单方向最多允许 20% 反向恶化是否合理；
10. **Coverage bias**：98% paired coverage 与 1 percentage point 差异门槛是否充分；
11. **Historical limitation**：固定 24-symbol panel 的结论是否被准确限制；
12. **Production separation**：Replay 是否彻底避免了 Universe、Policy 和 Entry 权威；
13. **Apply timing**：`01:00 -> 01:15` 是否需要未来不同于 Daily Universe switching
    的运行抽象。
