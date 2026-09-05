---
title: MULTI_STRATEGY_EVENTSPEC_FORWARD_SHADOW_V1_DESIGN
status: REVISED_FOR_FINAL_REVIEW
date: 2026-09-04
phase: P3-MSS-FS-V1
implementation_authority: NONE
production_authority: NONE
---

# Multi-Strategy EventSpec Forward Shadow V1 Detailed Design

## 1. Decision

本设计定义一个 **Multi-Strategy EventSpec Context Forward Shadow V1**。

它在现有 StrategySignal 已经合法持久化以后，为 CPM、BRF2、MPG 和 MI 创建独立、
只读、可恢复的 Selection Shadow Evidence：

```text
official Observation
-> official Detector
-> immutable StrategySignal
================ authoritative trading chain unchanged ================
-> Signal-owned Context Shadow Evaluation
-> hypothetical qualification_state / nullable would_select
-> 48h Signal-R first-passage Outcome
-> optional Capacity-entry sensitivity
-> bounded Forward Evidence review
```

V1 的唯一目的，是回答：

> 对已经由 current EventSpec 触发的 Event，事前冻结的 Context Hypothesis 在未来数据中，
> 是否继续对后续 Signal-R path quality 提供稳定分层。

本设计不改变 Detector、StrategyUniverse、SelectionSessionAuthority、Admission、Capacity、
Ticket、ExitProfile、风险、杠杆或交易所写入。

```text
retrospective_context_research = COMPLETE
forward_shadow_design = REVISED_FOR_FINAL_REVIEW
forward_shadow_implementation = NOT_AUTHORIZED
production_selection_gate = NONE
production_behavior_change = NONE
```

## 2. Critical Boundary: Event Qualification Is Not Universe Materialization

Stage-2 Protocol V2 的 primary estimand 是：

```text
conditional on EventSpec triggering at t
Market Context(t)
-> subsequent Signal-R path quality
```

所以当前证据直接支持的是 **Event-time Context Qualification**，不是：

```text
在 Event 发生以前
提前移除某 Instrument 的 Observation / StrategyUniverse membership
```

这两类选择必须严格区分：

| Capability | Decision time | Current authority | V1 scope |
| --- | --- | --- | --- |
| SOR Dynamic Instrument Selection | SOR Session decision boundary，Trigger 前 | Existing Selection Plane + StrategyUniverse | Unchanged |
| EventSpec Context Qualification | Event trigger close，Signal 后、Admission 前 | This design owns Shadow evidence only | In scope |
| Future production Context Gate | Signal 后、Admission 前 | Not designed or authorized | Out of scope |
| Future pre-Detector Universe for CPM/BRF2/MPG/MI | Earlier periodic boundary | No supporting V1 evidence | Out of scope |

因此本设计可以让所有目标 Strategy 使用同一套 **Selection Shadow architecture**，但不能声称：

> CPM、BRF2、MPG、MI 的生产 Dynamic StrategyUniverse 已经被设计或验证。

若 Forward Evidence 通过，下一阶段仍需独立决定：

1. 将 Context 作为 Signal-to-Admission 之间的 Production Gate；或
2. 另做具有正确 earlier cutoff 的 pre-Detector Dynamic Universe 研究。

不得把 Event-time cutoff 向前搬移后仍声称与 Stage-2 parity 等价。

### 2.1 Forward population limitation

V1 只观察由当前 Active StrategyUniverse 和当前 Owner/Policy authority 实际允许产生的
StrategySignal。固定 24-member Context Panel 只用于测量 market state，不会让 24 个成员都
获得 Signal authority。

因此 Forward claim 是：

> 在 Epoch 绑定的实际 Signal population 中，Context Hypothesis 是否保持分层。

它不是：

> 在 Stage-2 的完整 24 × hourly Detector grid 中再次得到同样结果。

每条 Forward Signal 已经冻结 `universe_version_id` 和 `universe_semantic_digest`。Epoch 激活
时进一步创建每个目标 EventSpec 的独立 population binding。若某一个 EventSpec 的 Universe
identity 在观察期间改变：

1. 真实交易继续遵循新 Universe；
2. 只关闭该 EventSpec 的旧 population binding；
3. 记录 `forward_population_drift`；
4. 其它 EventSpec bindings 与全局 Protocol Epoch 继续运行；
5. 如仍需继续观察该 Strategy，创建同一 Epoch 内的新 population binding。

这样避免 Universe change 与 Context effect 混入同一 Forward 分母。

## 3. Known Objective Facts

### 3.1 Current code boundary

1. `StrategySignal` 是不可变 detected Event，并明确不是 sizing 或 order instruction。
2. `observe_strategy_scope()` 使用 official Detector 和 current StrategyUniverse 产生 Signal。
3. `ingest_signal()` 之后才进入 Admission、CapacityClaim、Ticket 和 Command 链。
4. 当前 `ShadowOutcome` 已由 Observation Worker 处理，但一条 Signal 目前最多只能拥有一个
   Outcome，evaluation kind 只有 `fixed_horizon_excursion_v1` 和
   `sor_path_observation_v1`。
5. 当前 Observation Worker 在没有 due Observation Scope 时处理一个到期 Shadow Outcome，
   未部署第五个 Worker。
6. 现有 PublicMarketSource 支持 final `15m / 1h / 4h` Kline；Protocol V2 所需的 `1m`
   ambiguity drill-down 尚不是正式 port contract。

（来源：`src/trading_kernel/domain/signal.py`；
`src/trading_kernel/application/observe_strategy_scope.py`；
`src/trading_kernel/application/ingest_signal.py`；
`src/trading_kernel/domain/shadow_outcome.py`；
`src/trading_kernel/interfaces/observation_worker.py`；
`src/trading_kernel/application/market_ports.py`。）

### 3.2 Frozen research evidence

| Evidence | Frozen identity | Role |
| --- | --- | --- |
| Stage-2 Protocol V2 | `3e073c29a27621dcde8830af6a1a7cb8115ae83e` | Event/Context/Signal-R Replay |
| Stage-2.1 Cluster Audit | `337c5cd19e6837aa84d9eb49ed786beb2b156fce` | Trigger-hour、day/week cluster robustness |

Frozen artifact identities:

```text
Stage-2 Manifest SHA-256:
4efb9480ac3e254941f79fb318697cac9b2536535d8dc8960936abf684c094df

Stage-2 feature_screening.csv SHA-256:
a5d518e93191b7fe4a6773a7bd2986032762bfc00f250673a91ad46e44648653

Stage-2.1 Manifest SHA-256:
b63360b26b449dc7ee89efe3b5bce4809b0b231d544727fbb57bb187f2ccf16d

Stage-2.1 cluster_summary.csv SHA-256:
52a8fbe7b3c8ed17a44a6af5fcf91819f4e1ebc2ef10e1685e4070d10f89fb84
```

Stage-2.1 最终 evidence order：

| Hypothesis | Evidence tier | V1 role |
| --- | --- | --- |
| CPM × directional efficiency | A- | Core Shadow |
| BRF2 × market RV | B / B+ | Core Shadow |
| CPM × average correlation | C+ | Diagnostic Shadow |
| BRF2 × average correlation | C | Diagnostic Shadow |
| MPG | No supported V1 hypothesis | Semantic-only / UNSCORED |
| MI | No supported V1 hypothesis | Semantic-only / UNSCORED |

研究没有证明盈利、execution-adjusted edge、生产 Gate、最佳阈值或 pre-Detector Universe。

（来源：上述两个冻结 Commit 中的 `STAGE2_FULL_REPLAY_REPORT.md`、
`STAGE2_1_CLUSTER_ROBUSTNESS_REPORT.md`、Manifest 与 machine-readable artifacts。）

## 4. Scope

### 4.1 In scope

1. Crypto CPM、BRF2、MPG、MI current-dev EventSpec。
2. Versioned Selection Semantic Catalog。
3. 两条 Core Shadow Hypothesis。
4. 两条 Diagnostic Shadow Hypothesis。
5. MPG/MI `UNSCORED` semantic observation。
6. Exact frozen LOW/MID/HIGH cutoff。
7. Point-in-time feature calculation at trigger close。
8. Signal-R `+1R before -1R` 48-hour first passage。
9. `15m -> 1m -> AMBIGUOUS` path resolution。
10. Existing Ticket 存在时的 secondary Capacity-entry sensitivity。
11. PostgreSQL durable evidence、restart recovery 和 bounded Owner readonly view。
12. Minimum 30 calendar days、4 complete UTC weeks 的 Forward review contract。

### 4.2 Explicitly out of scope

1. 修改任何 Detector 或 threshold。
2. 修改 SOR Dynamic Selection V0。
3. 为 CPM/BRF2 直接创建或切换 Dynamic StrategyUniverse。
4. 为 MPG/MI 发明 feature、threshold 或 `would_select`。
5. Composite score、factor weight、AND/OR factor combination、ML 或优化。
6. Context Gate 对 Admission、Ticket 或 exchange dispatch 产生影响。
7. 模拟 Fill、Fee、Funding、Slippage 或 Net PnL。
8. 修改 ExitProfile、Capacity、Policy、Leverage、Margin 或资金范围。
9. 新增第五个 Worker、timer Worker、Research daemon 或文件型 runtime authority。
10. YAML/YML 配置、JSON/Markdown/Parquet runtime input。
11. SOR-US、US Equity 或其它 Venue。
12. 历史阈值重估、日期重切分或 retrospective optimization。

## 5. Vocabulary

### 5.1 Selection Semantic

Selection Semantic 定义：

> 一个 Strategy 的 Selector 理论上希望识别什么增量环境。

它不是 feature，不是 threshold，也不是 production permission。

### 5.2 Hypothesis Spec

Hypothesis Spec 是一个可计算、版本化、冻结 evidence provenance 的 Shadow 假设：

```text
feature identity
+ exact cutoff
+ bucket rule
+ expected effect direction
+ Core / Diagnostic role
+ research evidence digest
```

### 5.3 Context Evaluation

Context Evaluation 是一条 Signal 在其 trigger close 时，针对一个 Hypothesis 得到的
point-in-time immutable observation。

### 5.4 Selection Shadow Decision

Selection Shadow Decision 是每条 Signal 的唯一 Core summary：

```text
HIGH -> qualification_state = PREFERRED   -> would_select = true
MID  -> qualification_state = NEUTRAL     -> would_select = null
LOW  -> qualification_state = DISFAVORED  -> would_select = false

no supported Hypothesis
     -> qualification_state = UNSCORED    -> would_select = null

invalid Core input
     -> qualification_state = INVALID     -> would_select = null
```

Diagnostic Hypothesis 不拥有最终 `would_select` Authority。

`would_select` is a nullable projection of the three-state Core qualification, not an independently
researched `HIGH vs MID+LOW` policy. Forward primary evidence always compares `PREFERRED` with
`DISFAVORED`; `NEUTRAL` remains a separate cohort.

### 5.5 Signal-R Outcome

Signal-R Outcome 使用 trigger final close 作为 research anchor，使用 exact Detector
`protection_reference` 作为 -1R，不是 production entry、actual fill 或 realized PnL。

## 6. Architecture Options

| Option | Advantage | Defect | Decision |
| --- | --- | --- | --- |
| 把 Context 值加入 StrategySignal | lineage 简单 | 污染 detected Event；使 Signal 承载 Selector 语义 | Reject |
| 直接扩展 SOR Instrument Selection Plane | 可复用 Materialization | Stage-2 是 Event-time estimand，不支持 earlier Universe decision | Reject |
| 让 Admission 读取 Shadow table | 少一个未来改造步骤 | Shadow 直接获得交易权，违反研究边界 | Reject |
| 独立文件/CLI 收集 Forward | 不改 DB | 无生产 cadence、恢复和 Signal identity 保证 | Reject |
| 新建第五个 Shadow Worker | ownership 清楚 | 增加生产服务和资源面 | Reject |
| PostgreSQL Selection Shadow facts + existing Observation Worker | 单一 Signal lineage、durable、无交易影响 | 需要 forward Schema 和 bounded worker work-kind | **Adopt** |

## 7. Adopted Architecture

```text
                         official trading authority
                         ==========================
Market data
    |
    v
Observation Worker
-> Detector
-> StrategySignal commit
-> Admission / Capacity / Ticket continue unchanged

                         selection shadow evidence
                         =========================
same Signal identity
    |
    +-> Selection Semantic lookup
    |      |
    |      +-> Core Context Evaluation
    |      +-> Diagnostic Context Evaluation
    |      `-> UNSCORED semantic-only result
    |
    +-> Signal-R Outcome Plan
            |
            `-> due after 48h
                 -> 15m path
                 -> optional exact 1m drill-down
                 -> terminal first-passage evidence
```

The Shadow path cannot call:

```text
build_capacity_claim
issue_ticket
request_exit
dispatch command
StrategyUniverse materialization
SelectionSessionAuthority mutation
```

## 8. Single Authorities

| Concern | Single authority |
| --- | --- |
| Event occurrence | Existing immutable StrategySignal |
| Detector and protection fact | Current Strategy Registry + Detector facts |
| Tradable Instrument membership | Existing StrategyUniverse only |
| SOR Dynamic Instrument selection | Existing SOR Selection Plane only |
| Selection Semantic Catalog | Versioned typed source catalog seeded into PostgreSQL |
| Active Forward protocol epoch | PostgreSQL Forward Shadow Epoch |
| Context panel membership | PostgreSQL immutable Context Panel Spec |
| Market Context Snapshot | Immutable PostgreSQL projection over exact public Klines |
| Core would-select | Signal Selection Shadow Decision |
| Diagnostic observation | Hypothesis Context Evaluation only |
| Signal-R path | `signal_r_first_passage_v1` Shadow Outcome |
| Real execution economics | Existing Ticket, fills, Settlement and Review |
| Current production identity | `docs/current/MAIN_CONTROL_ROADMAP.md` only |

Repository documents and research artifacts explain provenance but never act as runtime input.

## 9. Frozen Semantic Catalog

### 9.1 CPM

```text
selection_semantic_id = CPM_DIRECTIONAL_CONTINUATION_COMPATIBILITY_V0
semantic_defined = true
```

#### Core

```text
hypothesis_spec_id = CPM_CTX_DE_V1
feature = directional_efficiency_24h
role = CORE

LOW  <= 0.1016505239587715
MID  <= 0.23203331067591773
HIGH >  0.23203331067591773

qualification_state:
HIGH -> PREFERRED
MID  -> NEUTRAL
LOW  -> DISFAVORED

would_select:
PREFERRED   -> true
NEUTRAL     -> null
DISFAVORED  -> false
expected_effect_direction = HIGH_MINUS_LOW_POSITIVE
```

#### Diagnostic

```text
hypothesis_spec_id = CPM_CTX_CORR_V1
feature = avg_cross_asset_corr_24h
role = DIAGNOSTIC

LOW  <= 0.3933068154009093
MID  <= 0.4746936301499299
HIGH >  0.4746936301499299

hypothesis_match = (bucket == LOW)
expected_effect_direction = HIGH_MINUS_LOW_NEGATIVE
produces_core_qualification = false
```

Correlation 的语义是观察 high-correlation common-move 环境是否继续损害 CPM；它不与
Directional Efficiency 做组合判断。

### 9.2 BRF2

```text
selection_semantic_id = BRF2_HIGH_VOLATILITY_REVERSAL_COMPATIBILITY_V0
semantic_defined = true
```

#### Core

```text
hypothesis_spec_id = BRF2_CTX_RV_V1
feature = market_rv_24h
role = CORE

LOW  <= 0.018675901617112554
MID  <= 0.020946788428373938
HIGH >  0.020946788428373938

qualification_state:
HIGH -> PREFERRED
MID  -> NEUTRAL
LOW  -> DISFAVORED

would_select:
PREFERRED   -> true
NEUTRAL     -> null
DISFAVORED  -> false
expected_effect_direction = HIGH_MINUS_LOW_POSITIVE
```

该规则只表示 HIGH RV Context；不得解释成 RV 连续增加时 BRF2 quality 单调提高。

#### Diagnostic

```text
hypothesis_spec_id = BRF2_CTX_CORR_V1
feature = avg_cross_asset_corr_24h
role = DIAGNOSTIC

LOW  <= 0.3933068154009093
MID  <= 0.4746936301499299
HIGH >  0.4746936301499299

hypothesis_match = (bucket == HIGH)
expected_effect_direction = HIGH_MINUS_LOW_POSITIVE
produces_core_qualification = false
```

### 9.3 MPG

```text
selection_semantic_id = MPG_LEADERSHIP_PERSISTENCE_V0
semantic_name = Persistent Leader Environment
evidence_status = NO_SUPPORTED_HYPOTHESIS_V1
evaluation_status = UNSCORED
would_select = null
production_gate = none
```

Semantic dimensions are documentation-only in V1:

```text
durable leadership
non-chaotic rank rotation
directional persistence
idiosyncratic rather than pure beta move
continuation room
```

No runtime feature is calculated from those dimensions in V1.

### 9.4 MI

```text
selection_semantic_id = MI_IMPULSE_PHASE_COMPATIBILITY_V0
semantic_name = Fresh Impulse / Impulse Phase Compatibility
evidence_status = NO_SUPPORTED_HYPOTHESIS_V1
evaluation_status = UNSCORED
would_select = null
production_gate = none
```

Concept vocabulary is retained only as future research language:

```text
FRESH_IMPULSE
MATURE_IMPULSE
LATE_EXTENSION
```

No actual Event receives one of these phase labels until a separate Measurement Contract is
researched and approved.

## 10. Context Panel

### 10.1 Identity

Market-level Hypotheses use one immutable context-only panel:

```text
context_panel_id = BINANCE_USDM_CRYPTO_CONTEXT_24_V1
candidate_count = 24
member_set = exact Stage-2 CandidateUniverse
member_set_digest = sha256:1570f50d916fc01a103c1d781740cebe2979625badf83438694c5d0a12d23e75
```

Canonical sorted members:

```text
binance-usdm:ADAUSDT:perpetual
binance-usdm:APTUSDT:perpetual
binance-usdm:ARBUSDT:perpetual
binance-usdm:ATOMUSDT:perpetual
binance-usdm:AVAXUSDT:perpetual
binance-usdm:BCHUSDT:perpetual
binance-usdm:BNBUSDT:perpetual
binance-usdm:BTCUSDT:perpetual
binance-usdm:DOGEUSDT:perpetual
binance-usdm:DOTUSDT:perpetual
binance-usdm:ETCUSDT:perpetual
binance-usdm:ETHUSDT:perpetual
binance-usdm:FILUSDT:perpetual
binance-usdm:INJUSDT:perpetual
binance-usdm:LINKUSDT:perpetual
binance-usdm:LTCUSDT:perpetual
binance-usdm:NEARUSDT:perpetual
binance-usdm:OPUSDT:perpetual
binance-usdm:RUNEUSDT:perpetual
binance-usdm:SOLUSDT:perpetual
binance-usdm:SUIUSDT:perpetual
binance-usdm:TRXUSDT:perpetual
binance-usdm:UNIUSDT:perpetual
binance-usdm:XRPUSDT:perpetual
```

This panel is:

- not a StrategyUniverse;
- not a ComparisonUniverse for MPG/MI Detector;
- not an Entry allowlist;
- not a current active-member set;
- not affected by SOR Dynamic Selection outcome.

It exists only to define the population used by `avg_cross_asset_corr_24h` and
`market_rv_24h`.

### 10.2 Why it cannot point to the SOR SelectionSpec

The same 24 Instruments currently appear in SOR Dynamic Selection, but the semantic owner differs:

| Member set use | Meaning |
| --- | --- |
| SOR SelectionSpec members | candidates eligible for SOR ranking/materialization |
| Context Panel members | fixed measurement population for multi-strategy market state |

Directly referencing the SOR SelectionSpec would make a future SOR spec retirement silently change
CPM/BRF2 Shadow semantics. V1 therefore freezes an independent Context Panel identity while an
architecture test proves its initial member digest equals the approved Stage-2 digest.

## 11. Feature Contracts

### 11.1 Shared temporal input

For a Signal with:

```text
trigger_candle_close_time_ms = t
```

all V1 Context features use exactly:

```text
25 contiguous final 1h closes
ending at t
```

Expected close boundaries are:

```text
t - 24h, t - 23h, ..., t
```

Any future close, missing close, duplicate boundary, non-positive price or non-canonical Instrument
identity invalidates the affected Hypothesis.

### 11.2 CPM directional efficiency

Only the Signal candidate is used:

```text
directional_efficiency_24h
= abs(close_t - close_t_minus_24h)
  / sum(abs(close_j - close_j_minus_1), j=1..24)
```

Requirements:

- source prices enter from strings into Decimal;
- denominator must be positive;
- no smoothing, resampling or alternate horizon;
- calculation is candidate-local and can remain valid when a market-level Diagnostic is invalid.

### 11.3 Market realized volatility

For every exact panel member:

```text
log_return_i,j = ln(close_i,j / close_i,j-1)
rv_i_24h = sqrt(sum(log_return_i,j ^ 2, j=1..24))
ordered_rv = sort(rv_i_24h across exact 24 members ascending)
market_rv_24h = (ordered_rv[11] + ordered_rv[12]) / 2
```

All 24 members must be complete. There is no 23/24 fallback.

### 11.4 Average cross-asset correlation

Build the exact `24 × 24` correlation matrix from the same 24 hourly log-return vectors:

```text
avg_cross_asset_corr_24h
= mean(all 276 valid upper-triangle pair correlations)
```

For each pair of 24-return vectors `x` and `y`, freeze Pearson as:

```text
mean_x = fsum(x) / 24
mean_y = fsum(y) / 24
dx_j = x_j - mean_x
dy_j = y_j - mean_y

corr_xy
= fsum(dx_j * dy_j)
  / sqrt(fsum(dx_j^2) * fsum(dy_j^2))

avg_corr = fsum(all corr_xy in canonical member-pair order) / 276
```

Requirements:

- exact candidate count = 24;
- valid pair count = 276;
- missing pair count = 0;
- zero-variance or non-finite pair invalidates this Hypothesis;
- invalid correlation does not invalidate candidate-local Directional Efficiency.

### 11.5 Numeric representation

Source prices remain Decimal. Statistical log, square root and correlation use the frozen pure-Python
algorithm above with `math.log`, `math.sqrt` and `math.fsum`; production runtime does not add NumPy or
Pandas.

Cross-host economic authority is **not** the last binary64 bit. V1 freezes two layers:

```text
raw audit value:
    float.hex()                    display/debug only

canonical authority value:
    Decimal(repr(binary64_value))
    quantize(Decimal("0.000000000001"), ROUND_HALF_EVEN)
```

Cutoffs are loaded from their exact frozen decimal strings and quantized by the same `1e-12` rule.
LOW/MID/HIGH comparison uses only canonical authority values. The snapshot semantic digest includes:

```text
source window digest
algorithm identity
canonical quantized feature value
canonical quantized cutoff identities
bucket
```

It excludes raw `float.hex()`. Therefore a harmless cross-host one-ULP difference does not create a
digest conflict when canonical value and bucket are unchanged. A canonical value or bucket drift is
an authority conflict.

Stage-2 artifact audit found the nearest observed Feature-to-cutoff distances were:

| Feature | Minimum observed distance |
| --- | ---: |
| `avg_cross_asset_corr_24h` | `4.0180051501470526e-05` |
| `market_rv_24h` | `8.54239751196112e-07` |
| `directional_efficiency_24h` | `4.322376925797178e-06` |

These are audit facts, not a future guard band. They show the frozen Golden bucket assignments are
not dependent on `1e-12` quantization.

Before implementation may continue, **FS-00 Golden** must prove against Stage-2 artifacts:

1. exact 744 market Context cutoff identities;
2. exact 17,856 candidate Context identities;
3. exact LOW/MID/HIGH bucket parity for all four Hypotheses;
4. deterministic canonical authority digest equality;
5. macOS and Linux exact bucket parity;
6. machine-readable raw numeric diff and distance-to-cutoff for every non-byte-equal value.

If source-window, formula, canonical value or bucket parity differs, implementation stops. A raw
binary64 difference alone is non-blocking only when canonical value, cutoff distance and bucket remain
identical. The old research result is retained and any accepted economic-semantic correction requires
an explicit Protocol amendment; implementation may not silently choose the prettier result.

## 12. Temporal Contract

### 12.1 Feature cutoff

```text
feature_cutoff_at_ms = signal.occurred_at_ms
```

All target EventSpecs are 1h current contracts. The trigger final close is known at this boundary.

### 12.2 Signal anchor

```text
signal_anchor_price = trigger final 1h candle close
signal_stop_reference = exact Signal protection_reference fact
```

No action-time bid/ask is used for primary Shadow selection or Signal-R Outcome.

### 12.3 Forward path start

The trigger candle is excluded.

```text
first eligible 15m bar:
open_time_ms >= trigger_candle_close_time_ms
```

### 12.4 Forward horizon

```text
horizon_end_ms = trigger_candle_close_time_ms + 48h
primary 15m bars = exactly 192
```

The 24-bar Registry Shadow horizon currently used by `fixed_horizon_excursion_v1` is not reused as
the new primary Protocol V2 horizon.

### 12.5 Prospective epoch boundary

A Forward Shadow Epoch must be committed before its first eligible Event:

```text
activated_at_ms < effective_from_ms
effective_from_ms aligned to a final 1h boundary
```

Only Signals whose `occurred_at_ms >= effective_from_ms` belong to the Forward dataset. No historical
Signal may be backfilled and presented as prospective evidence.

Recovery may reconstruct missing Shadow rows for an already eligible in-epoch Signal, because the
Signal identity and exact historical Kline cutoff were frozen before its outcome existed.

## 13. Domain Model

### 13.1 SelectionSemanticSpec

```text
selection_semantic_id
strategy_group_id
strategy_version_id
semantic_version
semantic_name
strategy_evidence_state
semantic_digest
status
installed_at_ms
```

Allowed `strategy_evidence_state`:

```text
HAS_CORE_SHADOW_HYPOTHESIS_V1
NO_SUPPORTED_HYPOTHESIS_V1
```

One Strategy may have one active Semantic version.

### 13.2 SelectionHypothesisSpec

```text
hypothesis_spec_id
selection_semantic_id
event_spec_id
hypothesis_version
role = CORE | DIAGNOSTIC
feature_kind
context_panel_id nullable
low_cutoff
high_cutoff
preferred_bucket = HIGH
neutral_bucket = MID
disfavored_bucket = LOW
expected_effect_direction
produces_core_qualification
evidence_tier
stage2_evidence_digest
stage2_1_evidence_digest
hypothesis_semantic_digest
status
installed_at_ms
```

Invariants:

- Core must set `produces_core_qualification=true`;
- Diagnostic must set it false;
- `evidence_tier` records independent research review strength and is not a numeric weight;
- no Strategy has more than one active Core V1 Hypothesis;
- threshold, role or feature changes require a new Hypothesis version;
- retiring a Hypothesis never rewrites historical Evaluations.

### 13.3 ForwardShadowEpoch

```text
forward_shadow_epoch_id
protocol_id = MULTI_STRATEGY_EVENTSPEC_FORWARD_SHADOW_V1
catalog_semantic_digest
context_panel_digest
activated_at_ms
effective_from_ms
status = ACTIVE | CLOSED
closed_at_ms nullable
close_reason nullable
created_by_release_commit
epoch_semantic_digest
```

Only one V1 epoch may be ACTIVE. Closing the epoch stops new Shadow enrollment but does not stop due
Outcome resolution.

Each Epoch owns sequential EventSpec population bindings:

```text
forward_population_binding_id
forward_shadow_epoch_id
event_spec_id
strategy_group_id
strategy_version_id
universe_version_id
universe_semantic_digest
binding_sequence
effective_from_ms
status = ACTIVE | CLOSED
closed_at_ms nullable
close_reason nullable
binding_semantic_digest
```

There is at most one ACTIVE binding per Epoch and EventSpec. A RuntimeScope or Universe pointer
change closes only the affected binding and never rewrites it. The successor receives the next
`binding_sequence`; evidence aggregation cannot mix different `forward_population_binding_id`
values.

### 13.4 Explicit Epoch Hypothesis Bindings

Epoch runtime never resolves “the current active Hypothesis.” It freezes exact immutable Specs:

```text
forward_shadow_epoch_id
event_spec_id
selection_semantic_id
hypothesis_spec_id nullable for Semantic-only
binding_role = CORE | DIAGNOSTIC | SEMANTIC_ONLY
hypothesis_semantic_digest nullable for Semantic-only
binding_semantic_digest
```

CPM and BRF2 each own one Core and one Diagnostic row. MPG and MI each own one `SEMANTIC_ONLY` row.
Installing a later Catalog or `CPM_CTX_DE_V2` does not affect an existing Epoch.

### 13.5 SignalSelectionShadow

One Signal receives one row per Epoch:

```text
signal_selection_shadow_id
forward_shadow_epoch_id
forward_population_binding_id
signal_event_id
selection_semantic_id
processing_status = PENDING | CLAIMED | COMPLETED
evaluation_status nullable until completed
qualification_state nullable until completed
would_select nullable
core_hypothesis_spec_id nullable
invalid_reason nullable
claim_owner / claim_token / lease_until_ms
attempt_count
next_retry_at_ms nullable
source_grace_end_ms
projection_version
input_semantic_digest nullable
decision_semantic_digest nullable
created_at_ms
completed_at_ms nullable
```

Terminal `evaluation_status`:

| Status | `would_select` | Meaning |
| --- | --- | --- |
| EVALUATED | TRUE / NULL / FALSE | Core is PREFERRED / NEUTRAL / DISFAVORED |
| UNSCORED | NULL | Semantic exists but no supported V1 Hypothesis |
| INVALID | NULL | Core should have been evaluated but exact inputs were invalid/unavailable |

Terminal shape:

| `evaluation_status` | `qualification_state` | `would_select` |
| --- | --- | --- |
| EVALUATED | PREFERRED | TRUE |
| EVALUATED | NEUTRAL | NULL |
| EVALUATED | DISFAVORED | FALSE |
| UNSCORED | UNSCORED | NULL |
| INVALID | INVALID | NULL |

### 13.6 SignalContextEvaluation

One row per Signal and Hypothesis:

```text
signal_context_evaluation_id
signal_selection_shadow_id
hypothesis_spec_id
evaluation_role
evaluation_status = EVALUATED | INVALID
feature_cutoff_at_ms
feature_value_decimal nullable
feature_value_binary64_hex nullable
bucket nullable
hypothesis_match nullable
market_context_snapshot_id nullable
input_window_digest nullable
evaluation_semantic_digest
invalid_reason nullable
created_at_ms
```

The Context child rows are immutable. A source repair before the parent becomes terminal creates the
first valid row; it does not update an already completed Evaluation.

Parent completion requires the exact active child cardinality frozen by the Catalog:

```text
CPM / BRF2 = one Core + one Diagnostic child
MPG / MI   = zero Hypothesis children + parent UNSCORED
```

### 13.7 MarketContextSnapshot

```text
market_context_snapshot_id
context_panel_id
feature_cutoff_at_ms
candidate_count = 24
valid_pair_count
missing_pair_count
market_rv_status
market_rv_24h nullable
market_rv_binary64_hex nullable
correlation_status
avg_cross_asset_corr_24h nullable
avg_corr_binary64_hex nullable
source_window_digest
snapshot_semantic_digest
created_at_ms
```

Unique key:

```text
context_panel_id + feature_cutoff_at_ms
```

If two computations for the same key produce different source or semantic digests, the Shadow lane
records terminal `market_context_snapshot_digest_conflict` evidence and does not choose one silently.
Trading remains unaffected.

## 14. PostgreSQL Schema Design

Implementation, if later authorized, uses one forward revision:

```text
0007_exit_profile_authority_v1
-> 0008_multi_strategy_eventspec_forward_shadow_v1
```

Proposed new tables:

```text
brc_selection_semantic_specs
brc_selection_hypothesis_specs
brc_market_context_panels
brc_market_context_panel_members
brc_forward_shadow_epochs
brc_forward_shadow_population_bindings
brc_forward_shadow_epoch_hypothesis_bindings
brc_signal_selection_shadow_current
brc_signal_context_evaluations
brc_market_context_snapshots
brc_shadow_capacity_entry_sensitivity
```

### 14.1 Existing Shadow Outcome evolution

The existing `brc_shadow_outcomes_current` remains the single Signal path-evidence projection. It is
extended rather than replaced.

Changes:

1. Remove unique `signal_event_id`.
2. Add unique `(signal_event_id, evaluation_kind)`.
3. Preserve unique `admission_decision_id` where non-null.
4. Add `source_kind = selection_shadow`.
5. Add `evaluation_kind = signal_r_first_passage_v1`.
6. Add Protocol V2 fields:

```text
signal_anchor_price
signal_stop_reference
signal_risk_per_unit
signal_tp1_price
signal_path_label
time_to_first_path_minutes
mfe_signal_r
mae_signal_r
resolved_by_12h
resolved_by_24h
resolved_by_48h
ambiguous_15m_open_time_ms
ambiguity_resolution
source_grace_end_ms
```

Existing `entry_reference_price / initial_stop_price / mfe_r / mae_r` semantics remain unchanged for
the two existing evaluation kinds. New Signal-R rows do not reuse those column names.

New Signal-R labels:

```text
SIGNAL_TP1_FIRST
SIGNAL_STOP_FIRST
NEITHER
AMBIGUOUS
```

### 14.2 Domain type separation

The shared persistence table does not imply one giant nullable Domain model. Domain and repository
ports use an explicit tagged union:

```text
LegacyExcursionSpec
LegacyExcursionProjection

SorPathObservationSpec
SorPathObservationProjection

SignalRFirstPassageSpec
SignalRFirstPassageProjection
```

Each type owns only its valid fields and mathematical invariants. In particular:

```text
LegacyExcursionProjection.mae_r >= 0          # adverse magnitude
SignalRFirstPassageProjection.mae_signal_r <= 0  # signed adverse excursion
```

The PostgreSQL adapter maps the tagged union to the shared row shape. Repository methods remain
evaluation-specific:

```text
add_legacy_excursion_pending(...)
add_sor_path_pending(...)
add_signal_r_first_passage_pending(...)

complete_legacy_excursion(...)
complete_sor_path(...)
complete_signal_r_first_passage(...)
```

No caller constructs a thirty-field generic `ShadowOutcomeProjection` and relies on cascading
`if evaluation_kind` validation.

FS-02 and FS-06 must audit every model, repository, query, Owner read model and test that currently
assumes:

```text
signal_event_id -> exactly one Shadow Outcome
```

and replace it with:

```text
(signal_event_id, evaluation_kind) -> at most one Shadow Outcome
```

### 14.3 Capacity sensitivity table

`brc_shadow_capacity_entry_sensitivity` owns the optional secondary comparison:

```text
shadow_outcome_id PK / FK
signal_event_id
ticket_id unique / FK
capacity_entry_reference_price
capacity_initial_stop_price
capacity_anchor_delta_signal_r
capacity_basis_path_label
classification_same
sensitivity_semantic_digest
created_at_ms
```

It exists only when the Signal owns a formal Ticket and the Signal-R Outcome is terminal. It is not
Settlement、Review、realized execution or simulated PnL.

### 14.4 Preservation

Migration must preserve every existing Shadow row byte-for-byte across all pre-existing columns.
Before DDL, all writers are stopped and the count of
`brc_shadow_outcomes_current.status='claimed'` must be zero. Pending、completed and unavailable rows
are preserved and remain readable/resumable under the new release.
It performs no backfill of old Signals into the new Forward Epoch and creates:

```text
zero active Epoch
zero Selection Shadow row
zero Context Evaluation
zero Market Context Snapshot
zero Signal-R Outcome
zero Ticket
zero Exchange Command
```

### 14.5 Why a new outcome table is rejected

Creating `brc_signal_r_outcomes` would establish a second Signal path evidence family with separate
claim, lease, retry and Owner-read semantics. Evolving the existing table keeps one evidence concept
while allowing one Signal to own one row per explicit evaluation basis.

## 15. Enrollment And Transaction Boundaries

### 15.1 Signal authority transaction

The authoritative Signal transaction remains unchanged in success criteria:

```text
lock official scope/episode
-> persist Facts
-> validate SelectionSessionAuthority if applicable
-> insert StrategySignal
-> update Readiness
-> commit
```

Shadow DML must not be able to roll back or reject this transaction.

### 15.2 Best-effort immediate materialization

Observation may retain a typed in-memory `ShadowSeed` built from the same final MarketSnapshot:

```text
signal identity
trigger close anchor
protection reference
candidate 25-close window when available
```

After the Signal transaction commits, Observation attempts a separate short Shadow transaction.
Failure affects only Shadow evidence and must not change the returned Signal status or Admission path.

### 15.3 Durable recovery without dual write

No Shadow job must commit atomically with StrategySignal. Recovery uses a bounded query:

```text
find oldest in-epoch target StrategySignal
where no SignalSelectionShadow exists
limit 1
```

The query is supported by exact Epoch time, target StrategyGroup and Signal identity indexes. This is
not a second Signal producer or compatibility path; it only reconstructs missing evidence from an
already immutable Signal.

### 15.4 Enrollment eligibility

A Signal is enrolled only when:

```text
active Epoch exists
AND signal.occurred_at_ms >= epoch.effective_from_ms
AND StrategyGroup in {CPM, BRF2, MPG, MI}
AND Signal StrategyVersion/EventSpec equals the catalog binding
AND signal.exchange_instrument_id belongs to BINANCE_USDM_CRYPTO_CONTEXT_24_V1
AND signal.universe_version_id / universe_semantic_digest equals the Epoch population binding
```

A later StrategyVersion is not silently evaluated by a V1 Hypothesis. It becomes `INVALID` with
`strategy_version_not_bound`, or waits for a separately installed catalog version.

If a Signal carries a new valid Universe identity for an otherwise bound EventSpec:

```text
exclude the drift Signal from both old and new population evidence
-> close only the old EventSpec population binding at that Signal boundary
-> create successor binding effective at the next final 1h boundary
-> retain the same exact Epoch Hypothesis bindings
```

The successor operation is one transaction and is idempotent for the exact old/new Universe pair.

An out-of-panel Signal is outside the frozen research population. It is reported in Epoch coverage
as `instrument_outside_frozen_context_panel`, but receives no V1 Hypothesis evaluation and no V1
Signal-R Outcome. Supporting it requires a new Context Panel and evidence version; the runtime must
not silently widen the panel.

## 16. Selection Shadow Evaluation Flow

### 16.1 MPG and MI

No market fetch is required for Selection scoring:

```text
Signal
-> active Semantic exists
-> no active Hypothesis
-> COMPLETED / UNSCORED / would_select=NULL
```

They still receive an independent Signal-R Outcome plan so future research can observe baseline path
evidence without pretending a Selector exists.

### 16.2 CPM

1. Fetch or reuse exact candidate 25-close 1h window at trigger cutoff.
2. Calculate Directional Efficiency Core.
3. Complete Core three-state qualification from the frozen bucket.
4. Independently fetch or reuse exact MarketContextSnapshot for correlation Diagnostic.
5. If panel correlation is invalid, write Diagnostic `INVALID`; do not invalidate valid Core.

### 16.3 BRF2

1. Fetch or reuse exact MarketContextSnapshot at trigger cutoff.
2. Market RV Core must be valid to complete the parent as `EVALUATED`.
3. Correlation Diagnostic is evaluated independently.
4. If exact 24-member RV cannot be produced before source grace expiry, parent becomes `INVALID`.

### 16.4 Parent decision rule

```text
active Core evaluated
-> parent EVALUATED
-> qualification_state = PREFERRED / NEUTRAL / DISFAVORED
-> would_select = true / null / false respectively

no active Core by approved Semantic
-> parent UNSCORED
-> qualification_state = UNSCORED
-> would_select = NULL

Core invalid after bounded source grace
-> parent INVALID
-> qualification_state = INVALID
-> would_select = NULL
```

Diagnostic status never changes parent `would_select`.

### 16.5 Context source grace

```text
context_source_grace_end_ms = signal.occurred_at_ms + 72h
retry interval = 15m
```

Before grace expiry, timeout or incomplete public Kline input returns the parent to `PENDING` with
`next_retry_at_ms`. After grace expiry, required Core input becomes terminal `INVALID`. Diagnostic
input becomes terminal Diagnostic `INVALID` without changing an otherwise valid Core result.

## 17. Signal-R Outcome Protocol

### 17.1 Geometry

LONG:

```text
signal_risk_per_unit = anchor - stop
signal_tp1_price = anchor + signal_risk_per_unit
```

SHORT:

```text
signal_risk_per_unit = stop - anchor
signal_tp1_price = anchor - signal_risk_per_unit
```

Risk must be positive. Invalid geometry creates an `unavailable` Signal-R Outcome with exact reason;
it does not alter StrategySignal or Ticket eligibility.

### 17.2 Primary 15m path

Fetch exactly the contiguous final 15m bars whose opens are:

```text
t, t+15m, ..., t+47h45m
```

No trigger 1h candle excursion may enter the path.

### 17.3 Same-bar ambiguity

When one 15m bar touches both TP1 and Stop:

1. Fetch exact 15 final 1m bars for that 15m interval.
2. Use the first 1m bar touching either level.
3. If the same first-touch 1m bar touches both levels, label `AMBIGUOUS`.
4. Missing/irregular 1m evidence does not guess direction; keep the claim retryable until source grace.

At most one 1m request is needed per Outcome because the first dual-touch 15m bar terminates the
path-order question.

### 17.4 Excursion

Across the complete 48h window:

```text
mfe_signal_r >= 0
mae_signal_r <= 0
```

The sign convention deliberately matches Protocol V2 research and is distinct from the legacy
`mae_r` magnitude field.

### 17.5 Resolution flags

```text
resolved_by_12h
resolved_by_24h
resolved_by_48h
```

Only TP1_FIRST and STOP_FIRST are resolved. `AMBIGUOUS` and `NEITHER` are reported separately.

### 17.6 Source grace

```text
source_grace_end_ms = horizon_end_ms + 72h
```

Before grace expiry, incomplete public Kline data releases the claim back to Pending. After grace
expiry, it becomes `unavailable` with one exact reason. This 72-hour value is an operational evidence
retention parameter, not Alpha, and changes require a new Forward protocol version.

## 18. Capacity-Entry Sensitivity

If the Signal later owns a formal Ticket, the resolver may calculate a secondary comparison using:

```text
capacity_anchor = Ticket.entry_reference_price
capacity_stop = Ticket.initial_stop_price
```

Persist:

```text
capacity_anchor_delta_signal_r
capacity_basis_path_label
classification_same
```

The correct name is **Capacity-entry sensitivity**, not actual fill or execution-adjusted outcome.
Ticket fills, fee, funding, slippage and realized economics remain owned by Settlement and Review.

Absence of a Ticket is normal and leaves sensitivity fields null.

## 19. Runtime Ownership And Fairness

No fifth Worker is added.

The existing Observation Worker owns official Observation plus two bounded evidence work kinds:

```text
1. due Strategy Scope Observation
2. missing/pending Signal Selection Shadow materialization
3. due Shadow Outcome resolution
```

### 19.1 Deadline-aware start gate

Before claiming Shadow work, the Worker reads the exact earliest scheduled official Observation:

```text
next_official_due_at_ms = MIN(due_at_ms for actionable official scopes)
```

V1 freezes typed code constants, not YAML/YML or Owner-maintained configuration:

```text
SHADOW_OFFICIAL_GUARD_MS = 30_000
SHADOW_CONTEXT_BUDGET_MS = 20_000
SHADOW_OUTCOME_BUDGET_MS = 10_000
SHADOW_DB_ONLY_BUDGET_MS = 2_000
```

Shadow network I/O may start only when:

```text
available_shadow_budget_ms
= next_official_due_at_ms - now_ms - SHADOW_OFFICIAL_GUARD_MS

available_shadow_budget_ms >= required_budget_for_exact_work_kind
```

Otherwise the Worker does not claim Shadow work and returns `NO_SHADOW_BUDGET`.

The complete attempt deadline is:

```text
shadow_deadline_at_ms
= min(
    now_ms + required_budget_for_exact_work_kind,
    next_official_due_at_ms - SHADOW_OFFICIAL_GUARD_MS,
)
```

If no official due time exists, the exact work-kind budget remains the timeout cap.

### 19.2 Recheck after claim

The Worker re-reads `next_official_due_at_ms` after acquiring a Shadow claim and before the first
network call. If the available budget no longer passes the start gate:

```text
release claim to PENDING
next_retry_at_ms = official due boundary + one worker poll interval
perform zero Shadow network call
```

### 19.3 Timeout and isolation

The complete 24-member Context batch or `15m -> optional 1m` Outcome sequence shares one outer
deadline. Individual calls cannot restart or extend the budget. Deadline expiry:

```text
cancel all outstanding Shadow public calls
release claim to PENDING
next_retry_at_ms >= next_official_due_at_ms + 5_000
return SHADOW_YIELDED_TO_OFFICIAL
```

The Shadow source uses a separate public-only client and dedicated bounded executor/semaphore from
the official Observation market source. A synchronous CCXT call that cannot be physically cancelled
may finish only inside that isolated Shadow executor; it cannot serialize or acquire the official
market client. No later Shadow job starts while timed-out Shadow futures remain outstanding.

The Worker exposes one bounded repository operation:

```text
read_next_official_observation_due_at_ms()
```

Implementation acceptance uses a production-shaped clock:

```text
Shadow Context starts shortly before a new official boundary
-> outer deadline yields/cancels Shadow work
-> official Scope is claimed on the next poll
-> official close-boundary latency <= baseline SLO + 5 seconds
```

Checking official priority only at iteration start does not satisfy this contract.

### 19.4 Scheduling rules

1. A due official Strategy Scope has strict priority at its closed-bar deadline.
2. Between official boundaries, Selection Shadow initialization and Outcome resolution use bounded
   round-robin fairness.
3. One worker iteration claims at most one non-Observation work item.
4. Shadow work never receives a timeout extending into `SHADOW_OFFICIAL_GUARD_MS`.
5. Claim leases are PostgreSQL durable and restart-safe.
6. The normal persistent Worker poll interval remains at most 5 seconds.

The Worker does not perform all 24 public calls inside a database transaction.

## 20. Market I/O And Caching

### 20.1 Market Context computation

The first CPM/BRF2 Signal at an hourly cutoff may require up to:

```text
24 Instruments × one 25-bar 1h request
```

Requests are timeout-bounded and use maximum concurrency `4`. The resulting immutable
MarketContextSnapshot is reused by every Signal at the same cutoff.

### 20.2 Signal-R resolution

Each due Outcome requires:

```text
one 192-bar 15m request
+ zero or one 15-bar 1m request
```

### 20.3 Port design

Do not expand Detector `MarketSnapshot.Timeframe` semantics merely to support path drill-down.
Add a dedicated public path request:

```text
PathCandleRequest
timeframe = 15m | 1m
since_ms
closed_at_ms
expected_bars
```

The port validates exact canonical boundaries and complete cardinality. It remains public-only and
loads no exchange credentials.

## 21. Idempotency And Recovery

| Failure | Required state |
| --- | --- |
| Duplicate Observation of same Signal | Same Shadow identities; zero duplicate row |
| Crash after Signal commit, before Shadow insert | Recovery query enrolls exact Signal |
| Crash after claim, before network response | Lease expires; another tick reclaims |
| Crash after MarketContextSnapshot insert | Immutable snapshot reused |
| Two computations produce same digest | Idempotent success |
| Same key produces different digest | Evidence Incident; no overwrite |
| Temporary public Kline failure | Pending until grace expiry |
| Core input permanently incomplete | Parent INVALID; trading unchanged |
| Diagnostic input invalid | Diagnostic INVALID; Core decision retained |
| No supported Hypothesis | UNSCORED, not INVALID |
| Outcome 1m unresolved in same bar | AMBIGUOUS |
| Outcome never touches either level | NEITHER |
| Epoch closed | No new enrollment; pending Outcomes continue |
| Worker release restart | Recover from PostgreSQL claims and exact release identity |

## 22. Trading Isolation

The following invariants are mandatory architecture tests:

1. Admission does not import or query Selection Shadow tables.
2. CapacityClaim does not import or query Selection Shadow tables.
3. Ticket issuance and ENTRY dispatch do not read `would_select`.
4. Shadow status cannot change Strategy Readiness.
5. Shadow failure cannot open a Strategy Entry Vacuum.
6. Shadow failure cannot change StrategyUniverse or SelectionSessionAuthority.
7. Shadow cannot create Reservation、Netting Domain hold、Ticket、Command or any Runtime Incident
   that fences a trading writer.
8. Owner Pause and Runtime Fence continue to govern trading independently.
9. Existing protected Ticket lifecycle continues even if its Shadow is Pending, Invalid or Ambiguous.

An evidence inconsistency is persisted as Shadow `INVALID/unavailable` reason and may emit an Owner
alert. V1 does not reuse `brc_runtime_incidents` for Shadow evidence failures.

## 23. Forward Shadow Epoch Activation

Migration installs Catalog and Panel but creates no ACTIVE Epoch.

Later software deployment, if independently approved, performs:

```text
deploy 0008 capability while stopped and flat
-> verify migration preservation
-> start existing workers with Shadow enrollment disabled
-> verify zero unexpected Shadow facts
-> commit one immutable Epoch activation
-> create exact Epoch Hypothesis bindings
-> create one future-effective population binding per EventSpec
```

Epoch activation:

- is not a Strategy resume;
- does not require exchange credentials;
- does not change Entry or Policy;
- is idempotent for exact protocol/catalog/effective boundary;
- cannot be backdated;
- is recorded through one reviewed application command, never ad-hoc SQL.

A population binding successor is scoped to one EventSpec. It closes the previous binding at a
future final 1h boundary and creates the new exact Universe binding in the same transaction. Other
EventSpec bindings are not changed.

Whether Owner API exposes this command is an Implementation Plan decision. No TOTP is required by
this design because the operation cannot expand exchange-write authority; authentication and exact
idempotency are still required if an HTTP surface is added.

## 24. Owner Readonly Surface

The bounded Owner surface must show:

### 24.1 Epoch status

```text
protocol identity
active / closed
input/catalog digests
exact Epoch Hypothesis binding IDs
```

### 24.2 Population binding status

For every target EventSpec:

```text
forward_population_binding_id
UniverseVersion / Universe digest
effective from / closed at
elapsed calendar days
complete UTC weeks
population drift reason
```

### 24.3 Strategy status

```text
selection semantic
Core / Diagnostic / Semantic-only
EVALUATED / UNSCORED / INVALID / PENDING counts
PREFERRED / NEUTRAL / DISFAVORED counts
would_select true / null / false counts
```

### 24.4 Evidence counts

For every Core Hypothesis and bucket:

```text
event_count
resolved_event_count
ambiguous_count
neither_count
unique_context_hour_count
unique_context_day_count
unique_context_week_count
```

### 24.5 Outcome statistics

```text
TP1_FIRST rate
STOP_FIRST rate
net_path_rate
median MFE Signal-R
median MAE Signal-R
median time-to-first-path
event-weighted effect
trigger-hour-weighted effect
LODO / LOWO sign stability
```

Queries are bounded by exact Epoch、population binding、Strategy and Hypothesis. No dashboard performs
an unbounded full-history scan, mixes population binding IDs or computes a new threshold.

## 25. Forward Decision Contract

### 25.1 Minimum evidence gate

A Core Hypothesis and one exact `forward_population_binding_id` cannot be reviewed for promotion
before all conditions hold:

```text
elapsed >= 30 calendar days
complete UTC weeks >= 4
HIGH resolved Events >= 30
LOW resolved Events >= 30
HIGH and LOW unique context hours >= 10 each
HIGH and LOW represented on >= 4 UTC days each
HIGH and LOW represented in >= 2 complete UTC weeks each
```

Time conditions take precedence over Event count. High Event volume in one market shock cannot finish
the experiment early.

`NEUTRAL` is never merged into `DISFAVORED` for the primary estimand. A future Production Gate may
choose to admit MID or reject MID only after a separate design and evidence decision.

### 25.2 Frozen review classification

After minimum evidence is met, each Core Hypothesis receives one of:

```text
FORWARD_SUPPORTED_FOR_PRODUCTION_DESIGN
EXTEND_FORWARD_SHADOW
FORWARD_CONTRADICTED
```

#### FORWARD_SUPPORTED_FOR_PRODUCTION_DESIGN

All must hold:

1. direction-adjusted event-weighted HIGH-minus-LOW effect is at least `+0.10`;
2. direction-adjusted trigger-hour-weighted effect is at least `+0.05`;
3. at least 75% valid LODO effects preserve sign;
4. at least 75% valid LOWO effects preserve sign;
5. no identity/source integrity failure;
6. if at least 20 matched Tickets exist, Capacity-entry classification parity is at least 80%.

This classification authorizes only a separate Production Gate design. It does not activate a Gate.

#### FORWARD_CONTRADICTED

Either:

1. event-weighted and trigger-hour-weighted effects both reverse; or
2. fewer than 40% of valid LODO or LOWO effects preserve expected sign.

#### EXTEND_FORWARD_SHADOW

All other results, including insufficient regime coverage, wide cluster uncertainty, mixed signs or
too few matched Tickets.

### 25.3 Checkpoints and maximum duration

The first eligible review occurs only after the minimum evidence gate. Checkpoints are measured from
the exact population binding `effective_from_ms`:

```text
30 calendar days
60 calendar days
90 calendar days hard maximum enrollment
```

If evidence remains insufficient or mixed at 90 days, that EventSpec population binding closes to new
enrollment and the Hypothesis is recorded as `FORWARD_INCONCLUSIVE` for that exact binding. Other
EventSpec bindings continue. Existing pending Outcomes still complete. Continuing with a changed
Feature、cutoff、panel or rule requires a new Protocol/Epoch Hypothesis binding; changing only the
StrategyUniverse creates a new population binding and cannot merge evidence with its predecessor.

### 25.4 Diagnostic and UNSCORED rules

- Diagnostic Hypotheses never independently receive Production Design authority.
- MPG/MI remain `NO_SUPPORTED_HYPOTHESIS_V1` regardless of observed raw outcomes.
- New MPG/MI research requires a separate prospective or replay protocol; this Forward run cannot
  mine its own observations for thresholds and retroactively relabel them.

## 26. Test Contract

### 26.1 Golden and feature tests

1. Exact Stage-2 Candidate Panel digest.
2. Exact 25-close point-in-time window.
3. Future close rejection.
4. Missing/duplicate close rejection.
5. CPM Directional Efficiency parity.
6. Market RV parity.
7. Average Correlation parity and exact 276 pairs.
8. Exact frozen cutoff and bucket parity.
9. HIGH/MID/LOW map exactly to PREFERRED/NEUTRAL/DISFAVORED.
10. MID produces `would_select=NULL`, never false.
11. Diagnostic cannot produce parent qualification or `would_select`.
12. MPG/MI are UNSCORED with no Context Feature row.
13. macOS/Linux raw values may differ only when canonical `1e-12` value and bucket remain equal.
14. Explicit 24-member RV median and Pearson formula parity.

### 26.2 Signal and transaction tests

1. Signal commits when Shadow insert fails.
2. Shadow insert occurs only after Signal authority commit.
3. Crash-gap recovery finds the exact missing Signal once.
4. Duplicate Signal/Observation creates zero duplicate evidence.
5. StrategyVersion drift becomes explicit INVALID.
6. Pre-Epoch and backdated Signals are excluded.
7. Closed Epoch stops enrollment but not Outcome completion.
8. Epoch freezes exact Hypothesis FKs and ignores a later active Catalog version.
9. CPM population drift closes/replaces only CPM binding; BRF2/MPG/MI remain active.
10. Evidence queries reject mixed `forward_population_binding_id` inputs.

### 26.3 First-passage tests

1. LONG TP first.
2. LONG Stop first.
3. SHORT TP first.
4. SHORT Stop first.
5. Trigger candle excluded.
6. Exactly 192 final 15m bars.
7. Same 15m dual touch drills down to 1m.
8. Earliest 1m TP resolution.
9. Earliest 1m Stop resolution.
10. Same 1m dual touch remains AMBIGUOUS.
11. Missing 1m stays retryable before grace.
12. Missing source becomes unavailable after grace.
13. NEITHER, 12h/24h/48h flags and excursion signs.

### 26.4 PostgreSQL tests

1. `0007 -> 0008` preservation.
2. Empty rebuild to one head.
3. Old Shadow rows remain exact.
4. Same Signal may own different evaluation kinds.
5. Same Signal cannot duplicate one evaluation kind.
6. Context Snapshot digest conflict fails closed.
7. Parent/child Evaluation shape constraints.
8. Claim/lease/CAS recovery.
9. Epoch active uniqueness and no backdating.
10. Exact one ACTIVE population binding per Epoch/EventSpec.
11. Population binding successor preserves predecessor and sequence.
12. Epoch Hypothesis binding cardinality and immutable FK identity.

### 26.5 Full-chain and architecture tests

1. Natural Signal -> independent Shadow -> normal Admission/Ticket path.
2. Rejected Signal -> Signal-R plus existing rejection Outcome coexist.
3. Admitted Signal -> Signal-R plus Capacity sensitivity coexist.
4. Shadow source failure -> Ticket path unchanged.
5. No Shadow import below Admission/Capacity/Ticket/Command boundaries.
6. No private Venue client, exchange mutation or credential loading.
7. No fifth Worker, timer, YAML/YML or file authority.
8. No pre-Detector Universe claim from Event-time evidence.
9. Shadow started before an official boundary yields within its work-kind budget.
10. Official close-boundary latency remains within baseline SLO plus 5 seconds.
11. Signal-R uses separate Domain types and repository methods from legacy excursion/SOR path.
12. Full-repository audit removes every one-Shadow-per-Signal assumption.

## 27. Migration And Deployment Classification

This capability changes Schema and runtime evidence semantics, so its eventual release class is
**R4**, even though it cannot trade.

Deployment requirements:

1. exact stopped-flat `0007 -> 0008` forward migration;
2. preserve all existing Signal、Admission、Shadow、Ticket、Command、Settlement and Review lineage;
3. Entry remains under the current Owner/Policy state and is never implicitly resumed or paused;
4. migration creates no active Epoch and no new trading activity;
5. compatible restart restores existing workers without waiting for Shadow materialization;
6. after `0008` commits, failure is fix-forward only;
7. rollback means closing/not activating the Shadow Epoch, not schema downgrade.

## 28. Performance Envelope

| Work | Bound |
| --- | --- |
| Missing Signal enrollment claim | 1 per Worker iteration |
| Pending Selection Shadow claim | 1 per Worker iteration |
| Due Outcome claim | 1 per Worker iteration |
| Market Context source | 24 members × 25 1h closes per unique needed cutoff |
| Market source concurrency | Maximum 4 |
| Signal-R primary path | 192 × 15m bars |
| Ambiguity drill-down | Maximum 15 × 1m bars once |
| Context Snapshot reuse | Exact panel + cutoff key |
| PostgreSQL runtime query | Exact key or ordered `LIMIT 1` actionable selector |
| Runtime files | Zero |
| Exchange writes | Zero |
| Official due-time lookup | One bounded minimum query before each Shadow start and after cancellation |
| Shadow official guard | 30 seconds |
| Context / Outcome total budget | 20 seconds / 10 seconds |

Observation close-boundary latency remains the primary SLO. Shadow work yields immediately when a
new official Scope becomes due.

## 29. Security And Data Boundary

1. Only Binance public Kline endpoints are used.
2. No API key, private account source, signing key or withdrawal/transfer capability is loaded.
3. Ticket identity may be joined inside PostgreSQL but bounded Owner exports use digest/reference or
   authenticated exact Ticket links.
4. Research Parquet and reports are never copied to Tokyo as runtime input.
5. Cutoffs and Hypothesis identities are PostgreSQL seeded facts from typed source code, not YAML.
6. Logs mask connection strings and never print full credentials.

## 30. Documentation Impact

This design remains under `docs/superpowers/specs` while under review. It does not enter
`docs/current` and does not change current production authority.

If implementation is later approved, the same release must update the existing canonical documents
rather than create a second current authority:

- `PROJECT_INFORMATION_ARCHITECTURE.md` — PostgreSQL evidence ownership;
- `P0_TRADING_KERNEL_REBUILD_DESIGN.md` — Signal-owned multi-basis Shadow evidence;
- `P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md` — completed capability summary;
- `STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md` — one Outcome per Signal per evaluation kind;
- `TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` — `0007 -> 0008` stopped-flat procedure;
- `MAIN_CONTROL_ROADMAP.md` — only after exact deployment/activation facts exist.

The existing statement “one Signal may own at most one Shadow Outcome” must be replaced with:

> One Signal may own at most one Shadow Outcome per explicit evaluation kind; evidence bases remain
> separate and cannot overwrite one another.

## 31. Implementation Plan Handoff

After independent design approval, the Implementation Plan should use these batches:

| Task | Scope | Exit condition |
| --- | --- | --- |
| FS-00 | Golden, arithmetic and bucket parity | Exact Stage-2 identity and zero bucket drift |
| FS-01 | Domain Catalog and separate projection types | Pure typed invariants GREEN |
| FS-02 | `0008` Schema、one-per-kind repository audit and preservation | Disposable PostgreSQL migration GREEN |
| FS-03 | Epoch、Hypothesis binding、per-EventSpec population lifecycle and Signal enrollment | Independent transaction + scoped recovery GREEN |
| FS-04 | Context panel and feature projection | Exact 24-member/cache/cutoff parity GREEN |
| FS-05 | Selection Shadow parent/children | Three-state Core、Diagnostic、UNSCORED semantics GREEN |
| FS-06 | Signal-R Outcome and 1m drill-down | Full 48h first-passage contract GREEN |
| FS-07 | Capacity-entry sensitivity | Exact Ticket join without execution claim |
| FS-08 | Observation Worker deadline/fairness/recovery | Preemptive budget proof、no boundary delay、no fifth Worker |
| FS-09 | Owner readonly evidence surface | Bounded Epoch/Hypothesis/block counts |
| FS-10 | Certification and deployment package | R4 evidence; no active Epoch |
| FS-11 | Separately authorized Forward activation | Future boundary committed; production trading unchanged |

## 32. Done Contract For This Design

The design is ready for independent review when all are explicit:

```text
Event-time estimand != pre-Detector Universe claim
Core / Diagnostic / Semantic-only separation
PREFERRED / NEUTRAL / DISFAVORED evidence semantics
MPG / MI UNSCORED semantics
exact frozen features and cutoffs
point-in-time and numeric parity contract
explicit Epoch Hypothesis bindings
per-EventSpec population binding lifecycle
PostgreSQL identities and schema ownership
Signal transaction isolation
Observation Worker bounded ownership
deadline-aware Shadow preemption budget
Signal-R 15m -> 1m first passage
separate Signal-R Domain projection and repository API
Capacity-entry secondary-only terminology
minimum Forward duration and cluster counts
no trading authority
R4 stopped-flat future deployment boundary
```

## 33. Final Authority State

```text
design_status = REVISED_FOR_FINAL_REVIEW
implementation_authority = NONE
forward_epoch_activation_authority = NONE
production_context_gate_authority = NONE
production_universe_change_authority = NONE
exchange_write_authority_change = NONE
```

## 34. Independent Review Amendment Closure

| Review item | Final design response |
| --- | --- |
| P0 binary HIGH vs all | Core is PREFERRED / NEUTRAL / DISFAVORED; MID remains neutral and primary evidence remains HIGH vs LOW |
| P0 global population coupling | Protocol Epoch remains global, but EventSpec population bindings have independent lifecycle and evidence cannot mix binding IDs |
| P0 worker preemption | Exact due-time query、work-kind budgets、30-second guard、outer cancellation deadline and production-shaped SLO test are frozen |
| P1 aggregate Catalog authority | Epoch owns explicit immutable Semantic/Hypothesis FK bindings |
| P1 cross-host binary64 fragility | Raw float is audit-only; quantized `1e-12` canonical value and exact bucket own economic authority |
| P1 generic nullable projection | Shared DB table remains, but three separate Domain Spec/Projection types and evaluation-specific repository APIs are required |

All amendments preserve:

```text
implementation_authority = NONE
production_authority = NONE
production_behavior_change = NONE
```
