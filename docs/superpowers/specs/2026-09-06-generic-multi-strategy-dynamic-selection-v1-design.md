---
title: GENERIC_MULTI_STRATEGY_DYNAMIC_SELECTION_V1_DETAILED_DESIGN
status: DESIGN_REVIEW_REQUIRED
date: 2026-09-06
design_authority: ALLOWED_FOR_ELIGIBLE_STRATEGIES
implementation_authority: NONE
production_authority: NONE
further_feature_research: CLOSED
---

# Generic Multi-Strategy Dynamic Selection V1 — Detailed Design

## 1. 设计结论与权限

**本设计让 CPM、MPG、MI、BRF2 分别拥有真实的 Dynamic TradableUniverse，复用 SOR 的 Selection → Materialization → Trading 权威链。** 每个策略可以独立保持 STATIC、申请 DYNAMIC、暂停新增交易或回到自己的 Static baseline。

本文是**待复核的目标设计**，不是已实现能力。冻结的研究算法、节奏、排名门槛不再搜索；接口形状、数据库归一化、失效与恢复机制属于本次工程设计。完成本文件不授予 Implementation、Tokyo deployment 或任何策略 activation 权限。

目标链始终为：

```text
Candidate market data → SelectionSnapshot → Materialization → StrategyUniverse
                                                                  ↓
Observation → StrategySignal → Readiness/Authority → CapacityClaim
→ immutable Ticket → durable Exchange Command → protected lifecycle
→ reconciliation → settlement → review
```

**SOR existing Golden behavior must remain exactly unchanged.** 泛化不得改变其 Candidate24、Decimal、OR/ATR、20M、Top7、Near7、UTC Session、01:00 decision、01:15 first eligible close、LONG/SHORT 原子切换、Vacuum retained-partial 与 first-natural-trigger suppression。

本期包含 Crypto `SOR-001`、`CPM-RO-001`、`MPG-001`、`MI-001`、`BRF2-001`。TradFi `SOR-US-EQ-PERP-001` 保持原能力；不自动给新增策略、其他 Venue 或其他 Candidate 开交易权限。Universe 数量不等于并发持仓数，仍使用既有 Policy、Exposure Family、Stop 风险与容量约束。

## 2. 证据、代码现状与推导的分界

### 2.1 已核实的研究输入

| Strategy | Selection semantic / feature | Entry / Retain | Cadence / nominal delay | 证据边界 |
| --- | --- | --- | --- | --- |
| SOR | Existing Dynamic V0 / pre-OR width ÷ ATR14 | 7 / 7 | 每日；01:00 决策，01:15 首根 | 独立 Decimal Golden；保持原合同 |
| CPM | Absolute Directional Efficiency V1 | 16 / 16 | 4h / 1h | TP1-first capture 62.6%，below floor；改善未被证明 |
| MPG | Persistent Leadership Score V1 | 12 / 16 | 1h / 1h | Top12 capture 86.5%；有区分度；Outcome 偏弱且稀疏 |
| MI | Positive Impulse Recency V0 | 16 / 16 | 1h / 1h | capture 86.7%；SPARSE；不称为 alpha evidence |
| BRF2 | Residual Extension V0 | 16 / 16 | 4h / 1h | capture 74.4%，below floor；质量差异基本中性 |

MPG Top12 Discovery/Holdout operational effect 为 **-0.040 / -0.621**，Excluded resolved N 为 **4 / 3**。未触发最小样本门槛下的 reject，不等于改善得到证明。12/16 hysteresis 的约 **36.2%** turnover 降幅仅是 membership 稳定性诊断，不能冒充 hysteresis 的新收益试验。

研究来源：Stage-3.1 results `f65d72fa92580de4b8c0323f4106d5975b97f4eb` 的报告、manifest、CSV 和 `core.py`；Owner 本轮提供的独立复核。完整 provenance 见 §19。

### 2.2 已核实的工程缺口

| 当前对象 | 当前代码事实 | 目标变化 |
| --- | --- | --- |
| StrategyUniverse | `MAX_UNIVERSE_MEMBERS = 10` | 支持本期最多 16 个可交易成员，仍逐 Spec 校验 |
| SelectionSnapshot / Job | SOR 固定 24/7、日 Session、时点约束 | 分离通用 period identity 与策略时钟 |
| Generation / Authority / baseline | 必需 previous LONG + SHORT，target trigger 要求正好两项 | 精确 Event binding 集合，可为 1 或 2 个 Event |
| Comparative projection | 使用当前交易 Universe 的 ID 与成员 | MPG/MI Dynamic 使用独立固定 Comparison24 |
| Selection worker | 按 SOR 01:00、单 Spec 调度 | 按 Spec 的 due period 调度，仍三个独立逻辑 lease |
| ExposureEpisode | domain key 不含 Universe ID | 保留这一身份；明确离开/重入的时序 |
| Owner activation | 已有 SOR 专用会话时间、TOTP 控制 | 每策略显式预览、激活、回退与状态页 |

来源：`src/trading_kernel/domain/{instrument_selection,selection_authority,strategy_universe,exposure_episode}.py`；`application/{observe_strategy_scope,project_comparative_universe,coordinate_selection_materialization,owner_control}.py`；`interfaces/selection_runtime_worker.py`；`migrations/trading_kernel/versions/0006_sor_dynamic_selection_v0.py`。

### 2.3 必须继承的近期修复

设计基线来自生产修复已合入的 `dev`，源码 provenance 见 §19；当前部署事实仍只由 `docs/current/MAIN_CONTROL_ROADMAP.md` 管理。

1. OWNER_PAUSED Vacuum 被新合法 Selection 接替时，保留原 fence/drain 事实，不制造第二个开放 Vacuum。
2. Vacuum 虽属于旧 period，但已指向本期 Generation 时，下一轮继续 materialization，不能重复 supersede 自己。
3. 临时 certification unavailable 是可重试，deadline 才决定 timeout；不能提前视为永久不合格。
4. Gap suppression ID 使用有界 canonical digest；不能拼接出超出数据库 ID 长度的键。
5. Deployment source-fence certification 与目标状态核对遵循已有修复；部署完成不等待 Dynamic warming。

来源：基线中的 `pg_instrument_selection_repository.py`、`coordinate_selection_materialization.py`、`scripts/trading_kernel/deploy_tokyo_release.py` 及对应 regression tests。

## 3. 三 Plane 与单一权限链

### 3.1 逻辑职责

| Plane / Owner | 输入 | 唯一输出与权限 | 禁止依赖 |
| --- | --- | --- | --- |
| Selection Runner | 已注册 Spec、固定数据窗口、前驱 SelectionSnapshot | 冻结候选排名与 Desired membership；提交 `SNAPSHOT_READY` | current Universe、Ticket、资金、Generation、Vacuum、Warming |
| Materialization Coordinator | committed Snapshot、控制版本、current Event set | continuity、Generation、Vacuum、drain、Warming、Authority grant/fallback | 在事务内网络请求；重算或调整分数 |
| Deployment | exact release certification、durable runtime | schema/identity/service 恢复与 postflight | 同步等待新 Snapshot 或 Universe warming 完成 |
| Observation | authority + actual Active Universe + required comparison facts | Detector、Fact、ExposureEpisode、合法 Signal | 给未选中或 STAGED 成员新增 Signal 权限 |
| Entry / Lifecycle / Reconciliation | 当前及冻结交易权限 | 原 Ticket/Command/保护/退出链 | 读取研究报告决定交易 |

三个 Plane 通过 PostgreSQL handoff。进程继续复用四个常驻 Worker；Selection、Materialization、Observation 是独立调度单元，互不嵌套为一条等待链。**不增加全局 `ALL_CRYPTO_DYNAMIC` 开关。**

### 3.2 五种 Universe/权限对象

| 对象 | 回答的问题 | 成员 authority | 能否直接产生 Signal |
| --- | --- | --- | --- |
| CandidateUniverse | 本 Spec 从哪里选择 | 当前 Spec 的冻结 24-member definition | 否 |
| ComparisonUniverse | MPG/MI 的 rank 相对谁计算 | 精确比较集合及独立 digest | 否 |
| Desired set | 本次决策想选择谁 | immutable Snapshot 的 member decisions | 否 |
| StrategyUniverseVersion | 已经安装、预热并 Active 的成员是谁 | 现有 Universe current pointer | 还需有效 Selection/Owner/Fact authority |
| SelectionAuthority | 何时、凭哪条 proof 可以使用这个 Event set | time-bounded immutable grant/current pointer | 只作为正式 Signal/Entry 链的必要条件 |

CandidateUniverse 是 Spec membership 的概念名，复用 `brc_instrument_selection_spec_members`，本期不另建一套 Discovery 成员数据库。ComparisonUniverse 是比较权限对象，不能伪装成拥有交易权限的 24-member StrategyUniverse。

## 4. 冻结的 SelectionSpec 与算法

### 4.1 Candidate、参数与配置归属

Candidate 使用既有 canonical `binance-usdm:<SYMBOL>:perpetual`：

```text
BTC ETH BNB SOL XRP DOGE ADA AVAX LINK LTC BCH DOT
NEAR ATOM FIL ETC APT OP ARB INJ SUI TRX UNI RUNE
```

全部使用 USDT perpetual；canonical 顺序按完整 instrument ID 升序。不能根据当天返回数量缩减分母，也不能自动补第 25 个币。

策略配置由**类型化 Python Spec catalog → 受审 forward migration/安装事务 → PostgreSQL immutable Spec**维护；Owner UI 只选择已安装版本和模式。**不新增 YAML/YML 配置，不从 Markdown、研究 JSON、CSV、缓存或环境变量加载选币阈值。** 修改 Feature、窗口、TopN、Candidate 或时钟都必须新 Spec 版本及另行批准，不提供在线优化编辑器。

本期 Event bindings：

| StrategyGroup | EventSpec | Dynamic Spec family | Comparison |
| --- | --- | --- | --- |
| CPM-RO-001 | `event_spec:CPM-RO-001:CPM-LONG:v3` | `CPM_ABSOLUTE_DIRECTIONAL_EFFICIENCY_V1` | 无 |
| MPG-001 | `event_spec:MPG-001:MPG-LONG:v3` | `MPG_PERSISTENT_LEADERSHIP_SCORE_V1` | fixed24，8h return rank |
| MI-001 | `event_spec:MI-001:MI-LONG:v3` | `MI_POSITIVE_IMPULSE_RECENCY_V0` | fixed24，12h return rank |
| BRF2-001 | `event_spec:BRF2-001:BRF2-SHORT:v3` | `BRF2_RESIDUAL_EXTENSION_V0` | Selector 的 market24；Detector 无 comparative rank |
| SOR-001 | 现有 SOR-LONG:v4 / SOR-SHORT:v4 | `sor-dynamic-selection-v0` | 无 |

Registry Detector 的条件、Event ID、版本、方向、Stop reference、Exposure Family、ExitProfile 不因 Selection 改变。MPG/MI 比较集合的切换是显式输入权限变更，见 §7，不可声称它与 Static Event 流完全相同。

### 4.2 CPM V1

25 个连续 final 1h closes，`C_0 = close(t-24h)`，`C_24 = close(t)`：

```text
path = Σ[j=1..24] abs(C_j - C_(j-1))
score = abs(C_24 - C_0) / path
```

高分优先。使用绝对位移，不能恢复已被 Stage-3.1 替代的 signed efficiency，也不能额外要求涨幅、SMA、reclaim 更强。`path=0` 属于 undefined feature，不能造一个可排序的 NaN。

### 4.3 MPG V1

在 `t-5h ... t` 的六个 final 1h boundary，分别对**完整 24 币**计算生产 8h return 排名。每个 rank 使用 9 closes；联合窗口需 `t-13h ... t` 共 14 closes：

```text
strength_j = (25 - rank_j) / 24
score = Σ[j=1..6] strength_j / 6
```

高分优先；生产比较函数中的 return DESC / instrument ID ASC tie-break 保持。Selection rank 与 Detector 当前 comparative rank 分别记录，不得相互代用。

### 4.4 MI V0

13 个 final 1h closes形成 12 个 simple returns，从最旧到最新编号 `j=0..11`：

```text
r_j = C_(j+1) / C_j - 1
p_j = max(r_j, 0)
score = Σ[(j/11) × p_j] / Σ[p_j]
if Σ[p_j] == 0: score = 0
```

高分优先。零正收益是已定义的 0 分，不是 `VALID_EMPTY`，也不自动新增“必须正收益”的过滤条件。

### 4.5 BRF2 V0

使用全部 24 币、每币 73 个 final 1h closes，形成 72 个 log returns：

```text
r_i,j = ln(C_i,j / C_i,j-1)
m_j = Σ[i in fixed24] r_i,j / 24
beta_i = Σ[(r_i,j - mean(r_i)) × (m_j - mean(m))]
         / Σ[(m_j - mean(m))²]
alpha_i = mean(r_i) - beta_i × mean(m)
e_i,j = r_i,j - alpha_i - beta_i × m_j
score_i = Σ[last24] e_i,j / sqrt(Σ[last24] e_i,j²)
```

高分优先。必须保留 **alpha/intercept**、等权 market（包含候选自身）、72h 拟合、最近24 residual 分母与平方和定义；不能改为无截距、leave-one-out、sample std、简单 return 或 abs(score)。market variance 或 residual 分母为 0 时走 undefined feature。

公式来源：Stage-3.1 `selection.py/core.py` 与其引用的 Stage-3 `features.py/selection.py`；以实际冻结实现为准，早期对话中的简化公式不覆盖它。

### 4.6 数值、源失败与 qualification

1. 原始价格/成交额字符串直接进入 Decimal；拒绝先 float 再 Decimal。
2. SOR 复用原 **prec=38 / ROUND_HALF_EVEN**、运算顺序、canonical strings、Golden digest。
3. 新 Spec 同样采用固定 Decimal context 38/HALF_EVEN，`ln/sqrt` 使用 Decimal。浮点仅允许研究 aggregate，不进入排名。
4. Stage-3.1 CPM/MPG/MI 使用 Decimal，BRF2 原研究有 binary64 log/OLS/sqrt。工程精度升级不能假装逐值与旧 float 完全一致。实施首个 evidence card 冻结数值合同和逐-member diff；不重跑 Outcome、调阈值或重选 N。任何 membership 差异必须单列并复核，不能悄悄改写研究结果。
5. `source_semantic_digest` 绑定 venue、instrument、时间窗、每根 canonical OHLCV、数据归一化版本；Snapshot 冻结 cutoff、observed/committed time、Spec/algorithm/input digests。
6. 任一所需 Candidate 缺 K 线、重复、未来 candle、断档或不一致 → 整次 `SOURCE_FAILED`；不可把失败币当 REJECT 后缩分母。
7. 完整输入上遇到 CPM path=0、BRF2 undefined/non-finite → 整次 `COMPUTE_FAILED`，记录 exact member/reason；不依据任意 epsilon 调序。
8. 四个新 Spec **不继承 SOR 的 20M floor**，不增加 Activity、pre-extension 等研究外 alpha gate。可交易资格使用已有明确 Product/Instrument facts，来源失败和明确不合格严格分开。
9. 先对完整24计算 feature/rank，再与已知合格集合取交集。明确不合格成员不补位；未知资格阻塞这次 Selection，不被解释为有效零。
10. 所需源完整、特征有定义且资格事实明确，而选中交集为0 → `VALID_EMPTY`。安全资格差异单独记录；历史 capture 数据未证明这些生产过滤的经济效果。

## 5. 排名、Hysteresis 与确定性

### 5.1 排序和状态

新 Spec：`feature DESC, canonical instrument ID ASC`；不使用随机、交易次数、币价或额外 volume tie-break。SOR 保留 `OR/ATR ASC, quote volume DESC, ID ASC`。

完整24 stable rank 为 1..24。成员分别记录 `rank_band`、`qualified`、`selected` 和 `selection_reason`，不能用旧固定 Top16 state 表达 MPG hysteresis。

```text
admit = qualified ∩ {rank <= entry_rank}
retain = prior_selected ∩ qualified ∩ {rank <= retain_rank}
desired = admit ∪ retain
```

MPG 在完整合格面板上成员数可为 **12..16**，不是固定12；无16之外补位。CPM/MI/BRF2 是最多16。少于额定数允许形成实际 Universe；0 走 valid-empty authority，不创建零成员 Universe。

### 5.2 Hysteresis 前驱归属

**前驱来自 Selection Plane 的上一条已提交 Snapshot 的 Desired set，而不是运行中的 Active Universe。** 这是对研究 `simulate_hysteresis(prior_selected, ranks)` 的工程落位，必须在设计复核中确认。

Snapshot 冻结 `selection_epoch_id`、`predecessor_snapshot_id`、`predecessor_member_digest`；同 epoch 内按 decision cutoff 单调提交。首次 activation epoch 前驱为空；不会把 Static7 自动当成 MPG retention 12..16 的成员。source/compute 失败不推进前驱；下一合法 Snapshot 继承最近合法 Desired。迟到结果不能插入到已提交后继之前。

Materialization failure 不改变 Selection 前驱：已提交但未生效的 Desired 仍属于确定性 policy 历史。审计分别记录 Desired/actual active；不得让 worker 时序反过来改变 feature ranking。回到 STATIC 后再发起全新 DYNAMIC activation，建立新 epoch、前驱为空。ordinary period 失败、暂停或 worker restart 不隐式重置 epoch。

如果暂停期间仍为 dynamic，则允许按既有 control-neutral Selection 语义继续更新 Snapshot，但不能 materialize 或恢复 ENTRY。若经历缺失 period，不补造未运行过的 hysteresis 状态。

该选择确保 Selection Runner 不读 current Universe，也无需与 Warming 成败共用事务；前驱版本和唯一性由 DB 防并发。Snapshot semantic digest 必须包含前驱身份，不能仅 hash score。

## 6. 时钟与新旧 Selection 的生效顺序

### 6.1 通用字段

`selection_period_key` 是 typed identity `(spec, selection_epoch, cutoff t)`；另存：

```text
decision_at_ms           逻辑决策时点 t
feature_cutoff_at_ms     最晚允许的源数据时间 t
scheduled_effective_at_ms 名义生效下界 e
period_expires_at_ms     下一名义生效边界
source_observed_at_ms    实际获取完成
committed_at_ms          Snapshot 提交
first_eligible_close_time_ms  Authority 最终冻结的首个可交易 close
```

对新策略：1h cadence 的 t 为每小时整点；4h cadence 的 t 为 UTC 00/04/08/12/16/20 点。`e=t+1h`；周期为 `[e, e+cadence)`。统一使用 exchange candle 的 exclusive close boundary，不混入 Binance 的 end-minus-1ms。

SOR 保留 `session_start_ms=D00:00`、decision/cutoff=D01:00、period end=D+1 01:00、first eligible≥D01:15。**不能把新策略的一小时延迟套到 SOR。**

### 6.2 正常时序与实际延迟

```text
t: close完成 → Selection开始 → Snapshot commit
t .. e: Snapshot仅为future Desired；旧authority继续
e: 建立当前period continuity；未来Snapshot成为due
   → materialization取得全局slot
   → fence / drain / warming / certification
   → grant: 新策略按本节current-final-close规则；SOR按原strict-next-close规则
```

新策略不在 `e` 之前开启切换 Vacuum；Selection 预取是纯市场数据准备，不是 StrategyUniverse Warming。这样冻结的一小时延迟不被提前交易消除，也不会人为制造整小时交易真空。

**小时策略不能机械使用SOR的“grant之后下一个close”公式。** 例如05:00:08完成后把首个close推到06:00，同时05:00这一period在06:00到期，会让每次小时切换都没有可交易close。新策略采用下述明确的工程规则，SOR原逻辑不变。

新策略允许授权**最新且仍fresh的final close `c`**，即正常Worker在close之后处理这根刚收完的K线，而实际Signal/ENTRY始终在grant commit之后发生。需要全部成立：

1. `e <= c < period_expires`，`c`是此时最新final 1h close；Detector数据未过其既有freshness window，实际grant/action time也未超过period expiry。
2. `feature_cutoff=t <= c-1h`，Desired Snapshot及其前驱在`c`之前已经immutable commit；不能看见该触发close后再产生选择结果并追认。
3. 无其他operation拥有的open Vacuum；本Generation的Vacuum已drained，并在grant同事务内resolve；target全部certified、Owner/Policy合法、当前比较窗口exact且完整。
4. 对同Event/instrument的正式Observation cursor/episode version加锁，证明`c`未被旧authority或其他comparison binding正式处理。若已处理，不能在同close换输入重算Signal，也不能造第二episode。
5. `first_eligible_close_time_ms=c`，`effective_from_ms=实际grant commit边界`；proof明确记录`PRECOMMITTED_SELECTION_CURRENT_CLOSE`及Snapshot commit、coverage/cursor版本。它不伪造在`c`时已经active的历史权限。

示例：04:00:10 Snapshot已提交；05:00:08完成切换，05:00 close尚未正式观察且仍fresh，则可在05:00:08之后处理05:00 close。Snapshot若迟至05:00:10才提交，不能使用05:00 close；只能选择下一合法close。若该close已超出period，则结果记`NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY`并结束此次未激活Desired，不创建零有效期grant。

period continuity是另一种proof：在精确旧set、Owner、comparison、episode coverage持续合法时，允许在boundary后的正常Worker tick为尚未处理的当前close建立continuity，不依赖新Snapshot。若同close已有旧Signal，其birth authority只按既有兼容规则处理；不能由新名单追认。VACUUM、Owner pause、comparison变化或unknown gap排除该连续proof。

grant事务必须使用新鲜数据库时钟，commit临近next-close边界时重新检查；越界则回滚并重取proof。统计同时保留nominal effective、first eligible close、实际grant和首次ENTRY时间，不能把这些时间合并后声称Live与Replay完全一致。

同一close的continuity Observation与switch争用同一组authority/cursor锁，只有一方可提交该close的正式输入。若旧authority先处理，switch不可撤销其Ticket或重算该close；可能因此错过本period，按明确expiry路径恢复。该竞态必须在GS-03/GS-13验证，不能靠测试强制worker固定顺序掩盖。

### 6.3 Continuity、supersession 和迟到

1. 已处于 DYNAMIC 的每个 authority period 到达 `e` 时，独立于 Selection outcome 取得 exact-current-set 的 `PRE_FENCE_CONTINUITY`；上一 period authority 到期不等于允许静默用旧 grant。
2. continuity需证明实际覆盖；迟到时按策略gap policy取得合法eligible close：SOR strict-next-close，新策略按§6.2对仍fresh且未正式处理的current close证明，否则推进到future close。Selection source失败只记录原因，不取得交易决策权。
3. 新 Snapshot 在 `t` commit、但 `e` 未到，不 supersede 正在本期 materialize 的 Generation。只有 **effective 已到的更新 Selection** 才可接管。
4. 同期输入冻结后不覆盖 Snapshot；发现原数据修订记 integrity incident，不改成员和 digests。
5. 新 due Snapshot supersede 未生效旧 Desired；保留同一个 open Vacuum 和原 previous-active set。已成功生效的 Universe 不是 SUPERSEDED Desired。
6. 新 due 结果为 VALID_EMPTY：仍须 drain 未完成 ENTRY，随后 empty authority；不能通过旧 generation fallback 恢复交易。
7. 回调必须携带 epoch、period、control version、Generation lease/version。旧结果只可审计，不能激活。
8. 停机后不补发过期close的Signal；新策略仅可能按§6.2处理最新fresh且未消费的close。每轮source/compute只处理最新due cutoff及已存在待完成工作；过期period明确`EXPIRED/SUPERSEDED`，禁止无界扫描。
9. 上一 period 为 VALID_EMPTY，则下一 period continuity 保持空，不从 dormant Universe current pointer 复活成员。新的非空成功 Selection 才能重新获得新交易权限。

## 7. ComparisonUniverse 与 Detector 输入权限

### 7.1 固定24排名

Dynamic MPG 的六次历史 rank 和 event-time 8h rank、Dynamic MI 的 event-time 12h rank，都使用 exact fixed24。Selection 的 cutoff rank不替代 Trigger close 的 rank。市场数据可共享，8h/12h 两种 projection 不能混用。

现有 `project_comparative_universe.py` 的纯排序公式复用，projection identity 改为 `event_spec_id + comparison_universe_id/digest + close + lookback + source_digest`。加载范围独立于 TradableUniverse；保存前重新校验 authority 所要求的比较 binding，过时请求不能覆盖新 current projection。

**缺任一比较成员的必要窗口 → comparison unavailable，阻塞该 Event 的新 Signal。** 不在16个或返回的23个里重排，不能让原来 rank3 因筛选变成rank1。

### 7.2 STATIC 与首次切换

现有 MPG/MI Static 比较输入取其原 Universe，未必是24。能力部署时不能悄悄把 Static rank 分母改成24。

新增 immutable Comparison definition/binding：Static 从现有原比较集合构造精确引用，Dynamic绑定fixed24。最终原子activation同时切换 `Tradable Event set + comparison binding + SelectionAuthority + mode`。首次Dynamic失败完整恢复原Static比较集合；ordinary Dynamic fallback保留fixed24。回到Static使用冻结Static baseline的原比较身份。

固定24的研究 rank parity 证明 Dynamic内部没有缩分母；不证明 Static与Dynamic产生同一Event流。认证分别对两种输入范围证明纯 Detector输出 parity，审计显示切换前后 comparison digest。

CPM/BRF2 不构造虚假的 Detector comparative payload。BRF2 market24只是 Selection feature输入。

## 8. 通用 Authority 与 PostgreSQL 设计

### 8.1 复用及替换原则

复用原 selection spec/job/attempt/snapshot/member、generation/target/event、vacuum/audit/authority、Universe及交易lineage表。泛化它们的 period 与 Event shape，**不新建第二套 generic runtime chain**。SOR 专属参数继续放在现有 subtype；新增四种 typed Spec payload，不在原 SOR 表塞 nullable 任意参数包。

`UniverseAuthorityPair` 替换为有序 `EventUniverseSet`：每项是 `(event_spec_id, position_side, universe_version_id)`；集合恰好等于 Spec event bindings。SOR仍两项且LONG先SHORT；CPM/MPG/MI一LONG；BRF2一SHORT。不能用“空SHORT”或重复LONG ID伪造pair。

### 8.2 Schema 对象与约束

下表是实施迁移的目标定义，**表名与字段尚未在本轮实现**。

| 对象 | 保留/新增数据 | 约束与索引 |
| --- | --- | --- |
| `brc_instrument_selection_specs` | family/version、算法/数值digest；typed payload FK | immutable identity；每family有效payload恰好1；同group/version唯一 |
| Spec payload / event / member tables | cadence、delay、entry/retain、fixed24、comparison policy | exact family参数CHECK；member唯一、恰好24；Event精确绑定及方向匹配 |
| Comparison definitions + members | immutable比较ID、member digest、24或原Static集合 | 独立于交易Universe；精确成员FK；不拥有Active/Warming权限 |
| `brc_strategy_selection_control_current` | epoch、pending period、mode、baseline、control_version | 同group唯一；pending shape原子；Owner授权FK；mode与epoch一致 |
| Selection job/attempt | 通用period、cutoff、due/retry/deadline、lease/version | `(spec,epoch,period)`唯一；due/state索引；过期lease不能提交 |
| Selection snapshot | 通用时间、Spec/input/前驱digests、counts | 一period一immutable成功结果；前驱必须同epoch更早；effective≥cutoff |
| Member decisions | 保留来源identity；typed feature；rank/qualified/selected/reason | `(snapshot,instrument)`唯一；exact24 deferred约束；rank1..24唯一；完整分区 |
| Snapshot payload | SOR geometry /新策略feature payload | 同family恰好一种；canonical Decimal文本可精确还原，不让 MONEY scale截断分数 |
| Generation / targets | 前驱实际Event set、expected target digests、deadline | target count=Spec event count；1或2；single newest actionable pergroup；有界claim索引 |
| Authority / authority-event bindings | 通用period、first close、策略typed proof、实际Event set、comparison binding | immutable authority revision；current pointer一条；grant必须有exact proof与完整Event set；新current-close proof不能被SOR接受 |
| Baseline / baseline-event bindings | 原Static Universe引用与比较引用 | 不复制member rows；按group/version immutable；退回目标与previous-active分开 |
| Vacuum / Gap Audit | 通用period、epoch、source Generation、策略gap kind | 同group最多1open Vacuum；lease/version；audit覆盖时间与目标集合digest必须匹配 |
| Universe versions/current | 沿用member-only semantic digest与Generation FK | 新Dynamic成员≤16且逐Spec限定，SOR≤7；manual原上限不扩；current Event唯一 |
| Signal / Claim / Ticket | 沿用 birth `selection_authority_id`、Universe版本；新增必要comparison identity | exact immutable lineage；历史nullable只给升级前数据，新Dynamic不可缺省 |

归一化 Event bindings分别从其父对象拥有关系：Generation baseline rows、Authority grant rows、Static baseline rows只存必要的Event→Universe引用。原 LONG/SHORT列通过受审迁移搬入对应行后删除；不同时维护两条写路径。现有 `materialization_targets` 继续是唯一target定义；不另造 linkage，实际Universe仅有Generation FK，没有Universe→Snapshot直连。

`session_start_ms` 从通用身份字段退出，迁移为 `period_anchor_ms`；SOR subtype保留真实Session语义并按原序列化公式还原其旧identity。不能把新1h/4h period冒充UTC Session。现有 SOR ID/hash原样保存，不能为了改名重写历史authority或birth lineage。

新 hash identity 采用固定前缀+SHA-256（不级联嵌入长ID），所有键验长度。通用 audit/authority 校验根据 frozen Spec clock，不再统一要求DAY对齐。旧 SOR序列化与Golden合同属于同一当前版本支持的策略语义，不是旧schema reader。

### 8.3 事务与并发

所有 core request/result为 frozen named Pydantic、`extra=forbid`；domain无SQL/network/filesystem依赖。

1. **Selection**：短事务claim job和前驱；事务外拉源/计算；短事务CAS job lease、control epoch、前驱cursor，原子提交Snapshot+24members+job完成+前驱推进。当前Universe不参与。
2. **Materialization**：claim、读取、fence/drain intent、install、staged、activate各为可恢复短事务；每步网络结果带request identity后CAS。
3. **控制锁顺序**：沿用现有kernel ENTRY serialization顺序；新增控制写统一按 strategy group → selection control → generation → vacuum → Event current（ID升序）取锁。实现前用调用图验证不会反转现有ENTRY/dispatch锁顺序；Owner pause、activation与fallback走同一权威边界。
4. **Activation**：锁control、generation、vacuum、所有Event current；重新验证Owner/Policy、epoch、due/latest、drain、certification、Gap proof、时钟；一次commit切整个Event set和comparison、authority及mode。
5. **ENTRY**：Claim与issuance的version/CAS仍有效；dispatch在官方submit authority中重核Vacuum/Owner/current identity。control-plane锁不能替代ENTRY热路径CAS。
6. 唯一性/shape采用FK、CHECK、deferred constraint trigger与CAS共同保证；不靠日志“确认成功”。

## 9. Materialization 状态机与恢复

### 9.1 正常切换

```text
SNAPSHOT_READY → waiting_effective → PENDING/DESIRED
→ claim global warming slot → fence previous new-signal/ENTRY authority
→ DRAINING_ENTRY → MATERIALIZING → all targets STAGED
→ coverage/certification proof → atomic ACTIVE
```

在Snapshot commit并确定Desired之后才允许fence；取得slot前队列等待保持合法continuity。fence提交之后旧对象仍保留为可恢复previous-active，直到新activation成功才retire旧Universe。queue waiting、drain、warming分别显示耗时；不得在每次retry重设deadline。

新Spec operational materialization timeout固定为**1800秒**（工程默认，非alpha参数），从fence commit计；队列等候不计算为已进入Vacuum的timeout，但超过该Selection period后必须supersede/expire。SOR保留已有1800秒合同与起算实现。网络timeout10秒、retry backoff至少30秒；认证临时失败在deadline内重试。

### 9.2 NO_CHANGE 与 VALID_EMPTY

NO_CHANGE要求：Desired集合等于实际集合，exact current Universes可用、comparison binding一致、无未解决Vacuum、Spec/Owner授权合法、coverage proof成立。只因成员相同不能跳过首次comparison switch或Owner pause恢复。

VALID_EMPTY是成功计算的有效结果：先fence和取消未完成ENTRY，再提交empty authority；不Warming、不创建空Universe、不fallback previous。此前合法已成交Ticket继续完整生命周期。对新ENTRY的影响从fence/empty commit向后生效，不能追溯抹去合法成交。

### 9.3 Drain、已有Ticket与Partial fill

继续复用已实现的Vacuum cancel/drain路径：未成交ENTRY全撤；部分成交撤剩余并核对实际成交量；仅在**已有Vacuum归因、零unknown、exact remainder取消确认、合法正数TP1/Runner拆分及保护计划**下保留成交部分。其他partial fill仍按现有Incident/controlled-flatten合同。

网络写仍必须是durable Exchange Command，unknown不能盲重发；drain unresolved/Incident不允许以“warming失败恢复旧名单”绕过。Existing Position/Ticket的Stop、TP1、Runner、Exit、reconciliation、settlement、review不读取新selection分数，也不因掉出名单主动平仓。

### 9.4 Fallback、Static rollback与Pause

| 情况 | 行为 | 结果权限 |
| --- | --- | --- |
| pre-fence source/compute失败 | 原合法current/continuity继续 | 不冒充new activation或post-fence fallback |
| post-fence warming永久失败/timeout | drain已清、旧set仍合法、gap proof完成后恢复 | `FALLBACK_PREVIOUS`，exact previous-active及comparison |
| 首次Static→Dynamic失败 | 恢复原Static set+comparison，产生transition-scoped proof | mode仍static；清理失败pending；不能自动重复首激活 |
| 一个Event staged、另一个失败 | 废弃未生效targets，恢复整个previous set | SOR不能LONG新/SHORT旧 |
| rollback到Static | 使用冻结baseline创建新的Materialization operation | 与ordinary fallback不同；不能复活retired Universe来交易 |
| Owner pause或全局Entry暂停 | 最高优先级阻止新ENTRY授权 | fallback不得清除pause或自动resume |
| previous非法 / drain未清 / gap缺源 | 保持Vacuum，记录首个blocker | FAILED_CLOSED，现有保护继续 |
| 新due VALID_EMPTY覆盖旧Desired | 终止旧targets、drain、empty authority | 不走旧失败fallback |

Static rollback使用baseline成员与comparison定义创建/认证新Universe版本，保留源baseline引用，不能把已经retired的旧current直接翻回ACTIVE。ordinary failed-switch previous仍未retire，可恢复权限，无须再复制成员。

若timeout/`NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY`发生时原period已不能容纳合法close，不能在原period写`effective >= expires`的grant。旧Generation终止新目标但保留Vacuum恢复工作；Coordinator先按最新due有效Selection判定supersession/VALID_EMPTY，否则以当前period的transition-scoped recovery proof恢复exact previous set。该恢复不伪造新Snapshot或Dynamic成功，不复活过期Desired；Owner pause、drain和comparison规则继续优先。无法取得当前period合法proof时保持FAILED_CLOSED，不能无条件清Vacuum。

### 9.5 崩溃、重启与supersession

恢复从durable job、Generation、target、Vacuum、authority current读取。已committed步骤幂等；过期lease只能重新claim，不能借旧token提交。外部unknown先Reconciliation，不能重置为prepared。

恢复对照至少覆盖：Snapshot commit后、fence后、cancel发出后、LONG staged后、所有targets staged后、activation commit响应丢失后、fallback audit完成后。最后一种必须exact-load已提交terminal authority，不能再造一次fallback。

Owner-Pause recovery保留 §2.3 已修复路径；旧Vacuum已指向当前Generation时必须继续当前Generation，不能按Vacuum旧period反复自我supersede。所有归因保留原fence时间及最新target身份。

## 10. ExposureEpisode 与 Gap Audit 的策略差异

### 10.1 SOR

SOR继续整个UTC Session的first natural episode语义。Gap Audit先于grant、先于可交易Observation；有正suppression和checked-negative proof。切换审计 `previous ∪ desired`，普通continuity审计current；first close跨界则回滚grant、延长audit、推进到下个close。不能复用尚未到达01:15时的不完整OR后窗口。

### 10.2 CPM / MPG / MI / BRF2

这些Event是 **rising_edge**，不是SOR的session_reference。研究replay在未选中期间跳过Detector，保留last episode state；不重置Universe absence/re-entry。本设计按这一边界落地：

1. Episode key继续为 `EventSpec + instrument + side`，不能加Snapshot、Universe、Generation或每小时period来制造新episode。
2. 未选中期间保留既有episode state，既不伪造NOT_TRIGGERED rearm，也不新增全24的可交易Detector循环。
3. 重入时首个有权限的当前close，用正式Detector和保留state推进；仍TRIGGERED则沿用episode、不得第二Ticket；真实NOT_TRIGGERED后才能由后续rising edge形成新episode。
4. 从未观察的成员，按现有首个合法观察规则建立state；不能声称拥有缺失历史的全路径first-trigger proof。
5. 资格/数据INVALID不能当NOT_TRIGGERED；保持state，等待当前合法观察。
6. Warming只产生就绪Fact与certification，不发布Signal、不消耗正式episode状态；warm结束只能在§6.2合法close上正式观察，不能补发过期或早于eligible close的Signal。

Generic Gap Audit记录 `RISING_EDGE_PRESERVE_STATE` coverage proof：fence interval、last authoritative observation/version、candidate set、数据完整性、实际first eligible close、comparison binding。使用current close时另附§6.2的precommitted Selection proof；**不套用SOR的“当天首次cross已发生”抑制规则**。对未选中期间的Detector结果无虚构审计结论。

MPG/MI comparison binding切换可能改变Detector布尔输入；这也是正式输入权限改变，Episode identity仍不重置。新comparison不可在相同close重新写出与已committed observation矛盾的结果；activation仅在§6.2证明未被消费的合法close生效。

## 11. Signal → Claim → Ticket → Dispatch 的权限验证

新Dynamic Signal freezes：Spec/epoch/period、birth selection authority、实际Event Universe/version/digest、comparison identity（适用时）、close、Fact与Episode lineage。authority FK可追到Snapshot/Generation/proof，无需再造平行完整复制。

| 边界 | 必须重核 | 失败后 |
| --- | --- | --- |
| Observation/Signal commit | current ACTIVE成员、close覆盖、comparison、Owner pause、无Vacuum | 无新增Signal；记录bounded原因 |
| Claim | Signal birth/当前兼容authority、Scope、Account/风险/Domain、Binding | 正式Admission拒绝，无资金预留 |
| Ticket issuance | Claim全部authority版本及current pointers的CAS | `authority_changed`，不发Ticket |
| ENTRY dispatch | runtime/schema、最新Owner/fence/Vacuum、exact command | 官方取消/terminal路径；unknown先核对 |
| Existing exposed Ticket | frozen Ticket、ExitProfile、command与venue事实 | 按现有保护/退出链处理 |

authority successor只有显式连续、同Event set/比较身份/合法period覆盖时才可兼容；不同成员、epoch、mode或comparison不能用新authority给旧Signal追认。跨period新Signal需本期grant；短时合法birth如何接受同period successor复用现有规则并加generic测试。

## 12. Worker 调度、数据成本与公平性

### 12.1 资源边界

四个常驻Worker不变。Observation hosting内Selection、Materialization、Observation各有独立logical lease/next_due。每tick按due索引取有限条任务并释放控制，不能for每个策略一直等到warming结束。

建议运行界限（需本地production-shaped认证，不是已测事实）：

| 项目 | 有界值/策略 | 超限行为 |
| --- | --- | --- |
| 新策略selection频率 | MPG/MI每小时；CPM/BRF2每4小时 | 同period只一次成功Snapshot |
| 公共1h输入 | 每小时24币；最大窗口73 closes，共1752条；失败分批重试 | cache按exact cutoff/digest复用；不触发24×每Detector重复请求 |
| SOR输入 | 既有24×96根15m窗口 | 原source合同及Golden不变 |
| fetch并行 | 全host最多4个in-flight market requests | 限流/backoff；尊重429 retry-after |
| due job批次 | 每tick至多5个group描述符；单次工作预算有界 | 未完成lease可续或让出，不阻塞其他plane |
| Warming | 继续全局1个slot；每次最多16成员、SOR每target最多7 | deadline/有界轮询；禁止策略自建独占worker |
| 排队 | due时间+aging；SOR时点任务纳入fairness | 无策略永久饿死；队列耗时可观察 |
| 输出 | healthy cadence零JSON/Markdown文件 | PG exact current/upsert；诊断为按需导出 |

静态无pending的新策略不创建Selection Job/Snapshot、不拉Selector专用24币数据。正常Static Detector所需市场/比较请求不算Selector请求；不能用“zero Selection network”承诺全系统零行情I/O。

source adapter读public market data，不持交易权限；Candidate不先加入StrategyUniverse。market cache仅performance用途，漏失可重建且有checksum/cutoff验证，不能代替PG Spec/Authority。一个策略的源失败不会取消其他策略已合法提交的Snapshot。

### 12.2 实际成本必须认证

Top16扩大的是Observation/Warming scope，不是资金。full enabled状态最多 `4×16 + SOR14 = 78` 个Crypto tradable Event-scopes，另加现有TradFi；comparison24数据复用，不再创建24个交易scope。

验收量化Selection耗时、queue/fence/warm耗时、event-time projection请求数、Observation延迟、Lifecycle/Reconciliation heartbeat、DB transaction duration和内存。若共享host不能满足原服务SLO，必须修复调度/批次，不缩Candidate或改cadence来“通过”。

## 13. Owner API、Console 与控制体验

### 13.1 每策略独立控制

页面展示五个策略卡：当前STATIC/DYNAMIC、pending生效时间、Spec/证据标记、Desired与actual members、首个eligible close、运行失败原因、pause状态。MPG解释“入选门槛12、保留门槛16，实际最多16”；不显示错误的固定Top12容量。

用户流程：**选择策略 → 预览下一可用生效时间/名单来源/比较集合变化 → 激活或回到STATIC → 输入一次TOTP → 看操作进度**。control version、唯一idempotency key由前端获取/生成；Owner不手填内部ID、SQL或请求体，不要求通过终端curl操作。

| 接口（拟定，归入现有Owner controls） | 输入/结果 | 权限 |
| --- | --- | --- |
| GET `/api/owner/v1/controls/strategies/{id}/selection` | current+pending、installed Spec、baseline、运行状态 | authenticated readonly |
| POST `.../{id}/selection/preview` | target mode/Spec、下一可用decision/effective、comparison变化 | 只读预览，不写授权 |
| POST `.../{id}/selection/dynamic/activate` | Spec、expected control version、effective period、reason、idempotency、TOTP | exact `selection_mode_change` Owner authorization |
| POST `.../{id}/selection/static/activate` | exact baseline/period及相同控制字段 | 明确Static rollback，独立授权 |
| existing strategy pause/resume | 原正式API | Owner优先级保持；resume不等于Dynamic activation |

SOR已发布activate路径与session参数语义保留；handler在boundary解析为SOR typed schedule，新策略只接收其typed period，不把UTC00:00字段伪装为每小时调度。内部调用共用同一application授权边界，无SQL快捷激活。

### 13.2 时间、重试与错误

新策略首激活只允许未来decision cutoff及其 `e=t+1h`；迟到提交必须重新预览下一合法period，不回填历史Selection。SOR仍按现有下一Session Owner合同。提交成功只代表scheduled，UI继续显示warming/active/fallback/failed状态。

同idempotency同payload返回同operation；不同payload冲突。version冲突返回409并刷新预览，不能自动替用户提交新范围。TOTP失效返回可在原页面重试的step-up错误，**不得清除有效登录session或跳登录**；只有登录session确实失效才走401登录。异步处理中不保存TOTP，不反复索取同一已授权operation的验证码。

Owner pause与activate并发时，pause优先；activate可以记录pending意图，但不能恢复交易。等待中的用户操作被新操作替代时保留SUPERSEDED审计及两条authorization ID，不静默篡改上一请求。

### 13.3 Static baseline与安全资格

每策略第一次申请Dynamic时原子捕获其实际Static Event set、comparison binding、Registry/Spec版本作为rollback baseline，不写死Static7字符串。baseline只引用历史immutable Universe成员。

激活预览可读Candidate Product/账户支持状态；实际warming和ENTRY仍需fresh独立side/Cross/leverage/risk facts。不因新Candidate缺杠杆事实而自动写交易所配置。Source failure、Owner pause、资金不足分别显示，不能统称“Selector未选中”。

## 14. Audit 与可解释性

一条完整追踪：`Owner authorization → Selection epoch/Spec → Job attempt/input digest → Snapshot/member/predecessor → Generation/targets → Vacuum/drain → proof → Authority → Universe/comparison → Signal → Claim/Ticket/Command`。

每个member显示feature canonical值、rank、资格理由、admitted/retained/excluded、previous Desired状态。每个period显示理论Desired与实际Active差异、queue/warm latency、错过的close数量、fallback原因、当前first blocker及系统下一动作。

研究evidence status为展示元数据，绝不成为运行时gate字段。运行Outcome沿用既有Signal/Ticket/Review证据；本期不实现新的Event-time Context Shadow，不生成Rejected虚拟Ticket，不把Stage-2/3文件放到生产目录做决策。需要进一步结果分析时用只读bounded export。

关键运营指标：source/compute失败率、VALID_EMPTY/NO_CHANGE/ACTIVE/FALLBACK数量、Desired/actual turnover、retained member数、Snapshot/authority延迟、Comparison缺源、Universe重入duplicate episode、未授权Signal/Ticket为0。展示不允许改写冻结append-only事实。

## 15. Migration 与 Release

### 15.1 Forward-only capability升级

预期从当前源码schema链头添加**一个新的forward revision**，建议名 `0008_generic_dynamic_selection_v1`；实施开始先确认链头，不能预占其他已批准迁移序号。本设计不创建或执行migration。

迁移必须stopped、flat、preservation-gated：保存exact source schema logical manifest，转换period/Event bindings结构；原SOR语义、历史ID、semantic hashes、Snapshot内容、Ticket/Command/Profile/Binding lineage保持。结构化转换要证明每个原LONG/SHORT/Session字段可从新归一化事实无损还原；不能只比较总行数，不能假称结构改变后全表字节hash自然相同。

新增四策略immutable Spec与初始STATIC controls、Comparison definitions、必要索引/权限。**零新增Job、Snapshot、Generation、Vacuum、Authority、Ticket、Command、Dynamic pending activation**。SOR已有current/pending/authority保持exact映射；源若有nonterminal materialization，则capability迁移另需该控制面quiescence证明，不能只看仓位flat就删除其durable状态。

原day/pair/top7约束改为typed-family约束；去掉旧列/错误trigger，同时保持SOR分支约束强度。不得双写新旧表、部署旧schema reader或原地修改已提交历史migration。Owner role grants必须包含新增表的exact用途；readonly role仅SELECT、控制role仅正式控制事务所需权利，补production-shaped权限测试。

### 15.2 软件发布与交易切换分别验收

此次涉及schema/runtime authority，按 **R4** 认证。Exact candidate冻结后一次完整certification，复用manifest；实际维护窗口fresh PG/Binance/systemd facts再授权cutover。兼容重启不要求Universe warming；新Spec首次materialization是runtime工作，不加入deploy call stack。

迁移commit后只允许target-schema fix-forward；不会以“rollback Static”名义降schema或换回旧runtime。软件安装默认保留原策略模式；各新Dynamic首次activation经独立Owner API执行，production resume和activation均不从文档状态推导。

## 16. 实施改造面与删除项

| 位置 | 拟改造 | 必须避免 |
| --- | --- | --- |
| `domain/instrument_selection.py` | pure通用fact envelope与typed SOR/新算法payload | 调整SOR arithmetic/digest、生产import research |
| `domain/selection_authority.py` | period policy、EventUniverseSet、clock/proof kind | dummy pair、所有策略套SOR Session |
| `domain/strategy_universe.py` | materialization可16、逐Spec约束 | manual/TradFi无条件扩Universe权限 |
| `application/run_instrument_selection.py` | Spec dispatch、前驱CAS、source契约 | Runner读取current Universe |
| `application/coordinate_selection_materialization.py` | Event targets循环、effective due、atomic集合、recovery | 每个策略复制coordinator或独立warming queue |
| `application/project_comparative_universe.py` / `observe_strategy_scope.py` | 独立Comparison身份、exact current输入核对 | 从Selected N重排rank |
| PG repositories / schema metadata | 原表泛化、normalized Event引用、comparison facts | 第二materialization linkage、历史双写 |
| Owner API / Console | typed perstrategy controls、预览、TOTP与可视进度 | API-only交付、自动全开、认证错误跳登录 |
| release/certification scripts | new schema source verifier、保全证据、bounded静态postflight | deployment等Dynamic warming、复用旧candidate manifest |
| tests | 替代写死pair/day/max10的通用假设；保留SOR专属回归 | 删除SOR Golden来迎合新实现 |

删除的是错误通用假设与重复权威路径，不删除历史已认证证据。现有ExitProfile、资金Policy、Detector策略条件、Lifecycle退出参数不在本期修改面。

## 17. 测试与认证合同

### 17.1 必须先有RED的工程不变量

| ID | 情景 | 必须证明 |
| --- | --- | --- |
| GS-01 | 四Spec公式、排序、ties、undefined、原始字符串 | frozen数值合同、无未来值、rank可重建 |
| GS-02 | MPG前驱重试、并发、failed/superseded Desired | 相同前驱与输入必同members；12..16；不读current Universe |
| GS-03 | hourly/4h时钟、t与t+1、future Snapshot、05:00:08正常完成/迟到Snapshot | 不提前交易、不提前supersede当前due；合法current close可用；迟到选择和已消费close不能追认；hourly不永远零eligible |
| GS-04 | 单LONG、单SHORT、SOR双Event materialization | target集合exact；不能出现mixed SOR pair |
| GS-05 | 16成员、15成员、0成员、rank17补位诱因 | 精确数量与空规则，manual上限不被顺带扩大 |
| GS-06 | MPG/MI rank1被排除、仅有16/23个比较窗口 | rank不重排；missing24 fail closed；8h/12h键隔离 |
| GS-07 | Static→Dynamic→fallback/Static rollback | comparison与tradable原子切换；初次失败仍Static |
| GS-08 | NO_CHANGE+open Pause Vacuum / latest VALID_EMPTY | 不能跳drain/proof；empty不fallback，不追溯改Ticket |
| GS-09 | 未成交、partial、full、cancel unknown、late fill | 复用官方Vacuum保护分支；unknown无盲重发 |
| GS-10 | 离开/重入、trigger未rearm、INVALID窗口 | Episode identity保留，最多1Ticket，不伪造rearm |
| GS-11 | SOR first-close前audit、跨close commit、旧Vacuum retarget | 近期生产bug回归全覆盖，bounded suppression ID |
| GS-12 | Snapshot commit/每个warming阶段/activation响应丢失重启 | durable幂等、lease隔离、timeout不刷新、terminal不复活 |
| GS-13 | Signal→Claim→Ticket→dispatch期间switch/pause | authoritative CAS/fence生效，保护退出继续 |
| GS-14 | 5策略due竞争、慢源、429、crash | 3 logical leases独立，global queue公平，Safety Worker SLO不退化 |
| GS-15 | Owner无TOTP/过期码/409/双击/reload | 无绕过、无错误登出、同idempotency同operation |
| GS-16 | 0007→目标schema保全及角色权限 | 逐logical record无损、SOR语义一致、seed无dynamic副作用 |
| GS-17 | capability deploy与compatible restart | 不等待dynamic warming，static zero Selection job/network |
| GS-18 | production import/path审计 | 无research/cache/Markdown authority，无YAML维护面 |

### 17.2 Golden不是新一轮Feature研究

实施首卡冻结：研究输入/Spec/protocol/correction/result hashes、Decimal数值合同、exact member fixtures、SOR原Golden。新策略逐cutoff/member验证features、rank、state、前驱、digests；BRF2 float→Decimal差异单列，零掩盖。该工程parity不重跑参数搜索、收益比较、TopN或hypothesis research。

SOR沿用既有 **961×24** Production Decimal Golden、Tail3 diagnostic **1323**，并另跑runtime/迁移测试。Generic化可以改变内部normalized表示，不能改变SOR选择结果与旧hash公式、时序、failure/entry authority行为。

Stage-3.1 fixed-N Replay与hysteresis模拟是不同测试面；不能声称生产12/16状态机已获得相同fixed-Top12 Outcome认证。新增hysteresis fixture只证明实现遵守冻结union规则。

### 17.3 验证分层与最终交付

详细设计本轮：文档引用、authority allowlist、diff及证据digest检查。Implementation阶段：逐card focused red/green，然后Fast；exact release阶段：全Unit/Architecture、PG integration、Full-chain、migration、Ruff/Mypy、Owner UI/API、resource envelope与R4 manifest。

设计批准后另出Task Cards，建议按“数值/identity evidence → generic domain/schema → Selection → Comparison/Observation → Materialization/authority → Owner Console → fault/migration/release certification”排序。该顺序不授予现在编码。

## 18. 待复核的工程决策与完成标准

研究参数已冻结，不再提请选择。以下是本文件提出的具体工程取舍，复核可直接给出条款修订：

1. **Hysteresis前驱使用Desired Snapshot链**，保持Selection与Runtime解耦；实际materialization差异公开审计。
2. **Generic materialization不早于nominal effective，并采用precommitted Selection的current-final-close proof**；保留一小时延迟、不追认迟到选择或已消费close，避免每小时切换永远无eligible close。SOR strict-next-close完全保持。
3. **Single Event/Pair统一成精确Event集合**，归一化原表而不复制SOR整套runtime。
4. **rising-edge保留离场state**，不额外引入全天全24 Detector或SOR式first-cross gate。
5. **BRF2 Decimal实现需独立工程parity**，研究binary64原报告不改写；membership差异须审计后才能作为生产Golden。

完成详细设计复核要求：以上选择无歧义，§17覆盖实施可验收边界，SOR不回退，Owner UI具备独立可用流程。随后才可标 `DESIGN_APPROVED / PLAN_ONLY` 并编写Implementation Plan；当前为 `DESIGN_REVIEW_REQUIRED`。

## 19. 源码与研究 provenance 索引

### 19.1 冻结设计输入（不是当前生产状态副本）

| 输入 | Identity |
| --- | --- |
| 设计源码基线 | `71757d7422a36bfbe13c214fd33b3cb3a07807cc`，已快进合入dev的修复与文档 |
| Stage-3 authority | `28b47e6d219acf2a008aacce92be1bd140b98964` |
| Stage-3.1 protocol | `9907153b94b2603535c9c846611ed90b0a2ea112` |
| Stage-3.1 pre-result correction | `46d7fecc9222bbbf1e85308410be2924b34cfdff` |
| Stage-3.1 result | `f65d72fa92580de4b8c0323f4106d5975b97f4eb` |
| Result manifest SHA-256 | `289c75428742c1bebfa8b6585aaed82a8af0ae7b1b1feefcc482f017911f305e` |

### 19.2 可复核来源

- [SOR生产详细设计](2026-08-20-sor-dynamic-instrument-selection-trading-v0-design.md)：沿用其冻结业务合同及基线已修复代码。
- [研究总览](2026-08-18-eventspec-instrument-fit-research-overview.md)：研究阶段与当前设计状态导航。
- [Stage-3.1原报告](https://github.com/jiangwweie/dingdingbot/blob/f65d72fa92580de4b8c0323f4106d5975b97f4eb/research/semantic_dynamic_selection_stage3_1/artifacts/STAGE3_1_FINAL_SEMANTIC_REVISION_REPORT.md)。
- [Stage-3.1原manifest](https://github.com/jiangwweie/dingdingbot/blob/f65d72fa92580de4b8c0323f4106d5975b97f4eb/research/semantic_dynamic_selection_stage3_1/artifacts/stage3_1_replay_manifest.json)。
- [Pre-result correction diff](https://github.com/jiangwweie/dingdingbot/commit/46d7fecc9222bbbf1e85308410be2924b34cfdff)。
- [独立复核与Provenance amendment](https://github.com/jiangwweie/dingdingbot/blob/42957b2091b988c53d6e03cb24639c17c54229b5/research/semantic_dynamic_selection_stage3_1/STAGE3_1_PROVENANCE_AMENDMENT.md)：独立研究分支追加的审计说明。

CPM/BRF2 Top16 fallback并非原Protocol文本单独推出。独立复核接受其pre-result correction且要求补审计：`TOP16_FALLBACK_CAPTURE_BELOW_FLOOR`不能改称80%门槛通过。独立research分支追加 `research/semantic_dynamic_selection_stage3_1/STAGE3_1_PROVENANCE_AMENDMENT.md`，不改原Protocol/report/manifest，不把research分支合入dev。

当前生产commit、tag、PG/control/service事实只看 `docs/current/MAIN_CONTROL_ROADMAP.md` 并在生产动作前重新核验。本文不声明任何部署、resume或activation已发生。

## 20. 本次文档交付验证

本轮只提交设计、研究总览和文档入口；另在独立research分支追加provenance amendment。`src/`、`migrations/`、`scripts/`、`tests/`、`deploy/`相对集成基线无本轮修改；未执行生产操作。

`test_current_document_authority.py`在**未改动的dev基线**及**设计worktree**均为23 passed / 2 failed，失败完全相同：

| 既有失败 | 基线证据 | 本轮处理 |
| --- | --- | --- |
| `test_runtime_state_document_matches_the_deployed_kernel` | roadmap写Production tag pending，测试要求已有正式tag | 不凭文档工作伪造tag/发布事实 |
| `test_stable_policy_v4_contract_defers_deployed_identity_to_roadmap` | 测试仍写死Policy v15 paused；roadmap已记录后续状态 | 保留原测试与运行事实，列为既有文档/测试同步事项 |

allowlist、当前引用、retired-semantics等其余文档测试通过；新文档相对链接及code fence/heading检查通过。此记录不把23/25描述成完整Release认证通过，也不阻止对本设计文本进行独立复核。两项基线问题需在后续发布认证前通过正式维护解决。
