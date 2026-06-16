# Strategy Line Handoff Summary 2026-06-16

Status: ACTIVE_STRATEGY_LINE_HANDOFF_SUMMARY
Last updated: 2026-06-16

## 交接边界

这份文档是策略研究窗口交给主控窗口和 Owner 的可读交接摘要。

本次交付只说明 **策略语义**、**候选状态**、**证据位置**、**主控接入形态** 和
**后续研究方向**。它不是 runtime registry，不是收益榜，不是 FinalGate 输入，不是
Operation Layer 输入，不是 deploy 请求，不是实盘授权，也不是下单参数。

## 已知客观事实

| 项目 | 当前结果 |
| --- | --- |
| 工作区 | `/Users/jiangwei/Documents/final-strategy-research` |
| 分支 | `codex/strategy-research-20260613-goal` |
| 策略柜版本 | `2026-06-16-r1` |
| 策略柜登记 | `24` 个策略语义 |
| 主控可 review 的 handoff / observe-only handoff | `12` 个 |
| 当前主交接入口 | `strategy-group-handoffs/main-control-handoff-index.md` |
| 当前策略柜入口 | `strategy-cabinet/strategy-cabinet.md` 和 `strategy-cabinet/strategy-cabinet.json` |
| 当前研究入口 | `README.md` 和 `STRATEGY_RESEARCH_GUIDE.md` |

## 一句话理解本项目策略线

策略线不是在找一个全年稳定赚钱的万能策略，而是在维护一个 **小资金、低容量、可观察、可边界化的右尾策略池**。

每个策略的目标不是立刻证明自己可以实盘赚钱，而是回答四件事：

1. 它捕捉的市场结构是什么。
2. 什么条件下可以进入观察。
3. 什么条件下必须降级、阻止、停车或复活。
4. 它能否被主控转成 Strategy Picker / watcher / RequiredFacts / sample packet 可消费的对象。

## 策略分层

| 层级 | 策略 | 当前意义 |
| --- | --- | --- |
| 第一批实验候选 | `MPG-001`, `FBS-001`, `TEQ-001`, `PMR-001`, `SOR-001` | 原先 5 个核心 StrategyGroup，已经具备主控 review 所需 handoff pack。 |
| 新增 observe-only handoff | `VCB-001`, `RSR-001`, `NLPD-001`, `DMI-001`, `SCF-001`, `MASS-001`, `UO-001` | 新增 7 个可被主控 review 的观察态草案，不代表可 armed 或可执行。 |
| 保留但不 handoff 的右尾 / 事实候选 | `LCF-001`, `MDS-001`, `EFI-001` | 有研究价值，但当前缺事实管线、目标配对或回撤控制。 |
| 新增 P2 研究语义 | `TRIX-001`, `PSAR-001`, `ICH-001`, `CCI-001`, `AEB-001`, `STOCH-001` | 新增 6 个研究-only 语义；只进入策略柜，不进入 handoff。 |
| 暂缓 / 复活候选 | `RBR-001`, `HAT-001`, `LSR-001` | 不删除；保留语义、失败证据和复活条件。 |

## 原先 5 个策略组

| 策略 | 具体语义 | 当前状态 | 主控接入方式 | 关键边界 |
| --- | --- | --- | --- | --- |
| `MPG-001` | **动量持续策略族**。把 WPR、MFI、PPO、TSI、MHI、DMI 等震荡/动量指标统一成“强势持续”，不是传统反转。 | `handoff_ready` | 可进入实验性 `armed_observation` review。 | 回撤和后周期衰减仍重；3x 只能 stress，5x 禁用；成员禁用规则必须 prefix-safe。 |
| `FBS-001` | **资金费率 / 拥挤压力策略族**。重点不是“费率高就做空”，而是负费率挤压后的 TEQ long squeeze。 | `handoff_ready_facts_heavy` | 可作为事实重的 derivatives stress observer。 | 需要 funding、OI、long/short、top trader、mark、margin 等事实；事实缺失时应降级或 no-signal。 |
| `TEQ-001` | **Binance 2026 美股类 / ETF 类动量**。利用短历史 TradFi-like 产品在特定窗口里的趋势和相对强势。 | `handoff_ready_low_history_blocked` | 可作为低历史 experimental observer。 | 当前可见性、产品状态、session gap、集中度、真实保证金是主 blocker。 |
| `PMR-001` | **贵金属 regime overlay**。主要是 XAG / XAU / 金属弱势或错位对其他策略的支持或禁用，不是常开金属交易策略。 | `observe_only_overlay` | observe-only overlay。 | standalone PMR short 和 broad metal long 均不能直接提升；需要目标策略配对。 |
| `SOR-001` | **开盘区间 / session 分支策略**。保留狭窄的 TEQ decisive-breakdown short 72h 分支。 | `conditional_observation` | 分支级观察，不做 broad ORB。 | 只有特定 session 分支可观察；宽泛 ORB 和 TEQ long revival 不应混成执行候选。 |

## 新增 7 个可交给主控 review 的观察态草案

| 策略 | 具体语义 | 当前状态 | 交付物 | 关键边界 |
| --- | --- | --- | --- | --- |
| `VCB-001` | **波动压缩后的真突破观察器**。核心是区分 true breakout 和 false breakout。 | `observe_only` | `strategy-group-handoffs/VCB-001/` | replay 中 true-breakout 标签有效，但它是 post-entry 标签，不能直接作为入场事实。 |
| `RSR-001` | **相对强弱轮动评分器**。用于支持 TEQ 排名和 Strategy Picker 提示，不是独立下单策略。 | `observe_only_scorer` | `strategy-group-handoffs/RSR-001/` | second-half decay 和 session/fill/product/margin 事实未解决。 |
| `NLPD-001` | **新上市 / 合约事件 / 低历史价格发现观察器**。研究刚上市或短历史标的的 first-window 行为。 | `observe_only` | `strategy-group-handoffs/NLPD-001/` | 低历史、幸存者偏差、流动性、产品状态和可执行方向不够。 |
| `DMI-001` | **ADX/DMI 方向点火观察器**。当前最清晰语义是 equity ADX-rising long + 24h time stop。 | `observe_only` | `strategy-group-handoffs/DMI-001/` | 成本敏感、metal 拖累、generic DMI 和 short-side 都不成立。 |
| `SCF-001` | **session confluence 结构确认器**。给 TEQ 提供 regular-session 强势 + 结构共振确认。 | `observe_only` | `strategy-group-handoffs/SCF-001/` | 需要 prefix-safe confluence、12h/72h time-stop 取舍、fill/session/margin 事实。 |
| `MASS-001` | **Mass Index 区间扩张后的反转观察器**。Mass Index 本身不带方向，必须绑定方向上下文。 | `observe_only` | `strategy-group-handoffs/MASS-001/` | long reversal 相对干净；continuation、short-side、金属泛化都要降级。 |
| `UO-001` | **Ultimate Oscillator bullish divergence 观察器**。只保留价格走弱后的 bullish divergence long。 | `observe_only` | `strategy-group-handoffs/UO-001/` | generic midline 和 short-side 都失败；需要 divergence-quality、session/fill/product/margin facts。 |

## 保留但不交给主控的候选

| 策略 | 具体语义 | 当前状态 | 为什么保留 | 为什么不 handoff |
| --- | --- | --- | --- | --- |
| `LCF-001` | **清算级联跟随**。用强平、OI、positioning、ADL、深度等事实识别强制流。 | `facts_pipeline_required` | 右尾潜力高，符合小资金抢局部冲击的方向。 | 没有 force order / liquidation cluster / OI / ratio / depth / margin 的 replay-aligned 数据管线。 |
| `MDS-001` | **金属错位 / session mismatch overlay**。给 NLPD、TEQ、PMR 等目标策略加支持或禁用标签。 | `overlay_candidate` | PMR-adjacent 的目标配对语义有价值。 | 还不是独立 activation/disable pair，目标覆盖不足。 |
| `EFI-001` | **Elder Force Index 负量价力衰竭后的 long reversal**。 | `right_tail_candidate` | `efi_negative_exhaustion_reversal_long_72h` 分支右尾很强。 | 候选池 DD 2x `-91.431725%`，3x/5x 崩溃，短边失败，缺 disable classifier 和 live-like facts。 |

## 新增 P2 研究语义

| 策略 | 具体语义 | 当前状态 | 为什么保留 | 为什么不 handoff |
| --- | --- | --- | --- | --- |
| `TRIX-001` | **TRIX zero-cross long**。三重 EMA 动量从负转正后的薄样本机会。 | `right_tail_candidate` | `8` 个事件，full 2x `117.088679%`，DD 2x `-1.881580%`；边界已固定在 `trix-thin-sample-concentration-boundary-20260616.md`。 | 样本太薄，INTC/CRCL 贡献集中，broad persistence 失败，不 handoff。 |
| `PSAR-001` | **Parabolic SAR bullish flip burst**。只保留 bullish flip 后的短爆发，不做 stop-reverse 系统。 | `right_tail_candidate` | best-90d 2x `124.602670%`，且 `0/0` 2x/5x proxy liquidation；边界已固定在 `psar-whipsaw-stop-reverse-boundary-20260616.md`。 | DD 2x `-57.821226%`，HOOD 单笔极端亏损，continuation 和 short-side 失败，不 handoff。 |
| `ICH-001` | **Ichimoku cloud breakout revival**。明确 no-future-cloud policy，不允许 forward cloud / Chikou 变成入场事实。 | `research_candidate` | cloud breakout long 有 best-90d 2x `296.354715%`；边界已固定在 `ich-no-future-cloud-decay-boundary-20260616.md`。 | full 2x `-78.421778%`，DD 2x `-85.398509%`，5 月 2x 到 `-100%`，不 handoff。 |
| `CCI-001` | **CCI trend escape / failure revival**。重点是 precious-metal +100 failure short。 | `research_candidate` | 金属 failure short full 2x `72.496535%`，best-90d 2x `105.400734%`。 | DD 2x `-74.614868%`，generic CCI 和权益 reclaim 衰减严重。 |
| `AEB-001` | **ATR expansion breakout short-window revival**。ATR24 equity expansion 的短窗口爆发。 | `research_candidate` | best-30d 2x `218.708454%`。 | best-90d 2x 只有 `31.950523%`，false-breakout 风险大。 |
| `STOCH-001` | **Stochastic range persistence / whipsaw vocabulary**。 | `parked_or_research_vocab` | 保留 30d/60d bullish range-persistence 语义。 | 90d gate 未过，full 2x `-90.790585%`，DD 2x `-95.696757%`。 |

## 暂缓 / 复活候选

| 策略 | 具体语义 | 当前状态 | 复活条件 |
| --- | --- | --- | --- |
| `RBR-001` | **range boundary reversion / calm range vocabulary**。 | `parked_or_research_vocab` | 只有出现 materially different 的 reclaim/range classifier，且能避免趋势破位尾部风险时复活。 |
| `HAT-001` | **Heikin-Ashi 平滑趋势复活 lane**。 | `research_candidate` | 需要更强 exit/disable、stop-fill/gap、session/product 和 margin 事实。 |
| `LSR-001` | **流动性扫单后 upper-range rejection short**。 | `research_candidate` | 需要解决 full-sequence collapse、cost/fill、slot M2M 和 classifier 质量。 |

## 本次推进的实际成果

| 方向 | 进展 |
| --- | --- |
| 文档治理 | 建立策略研究入口、策略柜 Markdown / JSON、P0/P1/P2 队列、主控 handoff index。 |
| 原 5 策略组 | 为 `MPG/FBS/TEQ/PMR/SOR` 补了低歧义边界：drawdown、facts readiness、product availability、overlay role、branch/time-stop。 |
| 新策略接入 | 把 `VCB/RSR/NLPD/DMI/SCF/MASS/UO` 转成 observe-only handoff 草案，可供主控 review。 |
| 策略池扩展 | 把 `LCF/MDS/EFI/HAT/LSR/RBR` 以及 `UO/TRIX/PSAR/ICH/CCI/AEB/STOCH` 放入策略柜，明确保留、阻止或复活条件。 |
| RequiredFacts | 对每个可交付策略固定了需要的 market/account/exchange/strategy facts 和 facts-missing 行为。 |
| 风险边界 | 统一了 `1x` 默认、`2x` 研究、`3x` stress、`5x` 默认禁用的杠杆语义。 |
| 证据口径 | 保留右尾窗口，但禁止把窗口收益直接当成全年稳定 alpha 或实盘可执行证明。 |

## 主控接手方式

主控窗口不需要从研究过程文档里猜策略。推荐只消费这些入口：

| 入口 | 用途 |
| --- | --- |
| `strategy-group-handoffs/main-control-handoff-index.md` | 主控 review handoff 的总入口。 |
| `strategy-group-handoffs/*/handoff.json` | 系统可读策略组字段。 |
| `strategy-group-handoffs/*/handoff.md` | 人读策略语义、RequiredFacts、hard stops、sample packets。 |
| `strategy-cabinet/strategy-cabinet.json` | 策略柜结构化登记。 |
| `strategy-cabinet/strategy-cabinet.md` | Owner / reviewer 可读策略语义登记。 |
| `p0-handoff-hardening-matrix-20260616.md` | 原 5 策略组补强状态。 |
| `p1-next-handoff-queue-20260616.md` | 下一批 handoff / non-handoff 处理顺序。 |
| `p2-strategy-pool-expansion-queue-20260616.md` | 后续策略池扩展和复活规则。 |

## 主控接入建议

| 接入优先级 | 策略 | 建议 |
| --- | --- | --- |
| 第一批可接手 | `MPG-001`, `FBS-001`, `TEQ-001`, `PMR-001`, `SOR-001` | 作为实验性 StrategyGroup / overlay / conditional observation 进入主控 review。 |
| 第二批观察态草案 | `VCB-001`, `RSR-001`, `NLPD-001`, `DMI-001`, `SCF-001`, `MASS-001`, `UO-001` | 先进入 Strategy Picker 词汇和 watcher 探索，不直接 armed 或 execute。 |
| 只保留研究 | `LCF-001`, `MDS-001`, `EFI-001`, `HAT-001`, `LSR-001`, `RBR-001` | 保留在策略柜，等待事实管线、disable classifier 或语义重构。 |

## 当前结论

这次策略线已经从“很多编号和研究片段”推进成一个可以交给主控 review 的策略柜：

```text
24 个策略语义登记
12 个 handoff / observe-only handoff
5 个原始核心策略组补强
7 个新增观察态策略草案
12 个保留 / 暂缓 / 复活 / 研究语义候选
```

主控可以从这批交付中接走的是 **策略语义、RequiredFacts、hard stops、sample packets、观察态边界和策略柜登记**。主控不应把研究收益数字直接解释为已集成能力或已授权实盘能力。
