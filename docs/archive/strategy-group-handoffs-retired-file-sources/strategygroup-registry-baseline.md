---
title: STRATEGYGROUP_REGISTRY_BASELINE
status: CURRENT_PILOT_BASELINE
authority: docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json
last_verified: 2026-06-20
---

# StrategyGroup Registry Baseline

## 目的

这份基线是 Owner/Codex 共用的 StrategyGroup 策略资产地图，用来说明每个 StrategyGroup 吃什么机会、怎么交易、当前层级、是否具备试运行资格，以及哪些证据会改变 keep / revise / promote / park / kill 决策。

它不是实时运行状态，也不回答当前能否交易；实时提交资格只能由运行时状态判断。

## 总览

| StrategyGroup | 策略含义 | 层级 | 可试运行 | 证据状态 |
| --- | --- | --- | --- | --- |
| `MPG-001` | 动量延续 | `L4` | `true` | `reviewed_handoff_plus_replay` |
| `CPM-RO-001` | CPM 回踩收复 | `L3` | `true` | `standalone_trial_asset_identity_closed` |
| `TEQ-001` | 类股权永续动量 | `L2` | `false` | `reviewed_handoff_partial_runtime_history` |
| `FBS-001` | 资金费率/基差压力 | `L3` | `false` | `reviewed_handoff_derivatives_heavy` |
| `SOR-001` | 开盘区间结构 | `L3` | `false` | `reviewed_handoff_session_conditional` |
| `PMR-001` | 贵金属制度覆盖 | `L1` | `false` | `reviewed_handoff_observe_overlay` |
| `BTPC-001` | 熊市回抽延续 | `L2` | `false` | `reviewed_l2_handoff_plus_proxy_replay_decision` |
| `VCB-001` | 波动压缩突破 | `L1` | `false` | `partial_replay_and_decision_evidence` |
| `LSR-001` | 流动性扫盘/短线复活 | `L1` | `false` | `partial_replay_and_decision_evidence` |
| `BRF-001` | 熊市反弹失败 | `L1` | `false` | `partial_replay_and_decision_evidence` |
| `RBR-001` | 区间边界回归 | `L1` | `false` | `partial_generated_decision_only` |

## 风险边界

| 风险类别 | Owner 是否可在既定策略范围内接受 | Registry 行为 |
| --- | --- | --- |
| `strategy_quality_risk` | 可以 | 策略和 replay 不确定性可用于 keep / revise / park / promote / kill 决策 |
| `fact_coverage_risk` | 观察和复盘层级内可以 | 实盘动作仍需要运行时新鲜事实 |
| `economic_risk` | 既定范围内可以 | 成本和滑点只影响策略判断，不构成提交权限 |
| `execution_safety_risk` | 不可以 | 事实过期、保护缺失、重复提交、冲突敞口必须运行时失败关闭 |
| `authority_risk` | 不可以 | 文档、replay、代理事实、观察证据永远不能授权实盘动作 |

## 当前策略组

### `MPG-001` 动量延续

- 策略边际: Capture clean momentum continuation after member and group-pool confirmation.
- 交易逻辑: Long-only continuation lane with exhaustion and concentration disables, protected by stop/exit plan.
- 适用市场结构: Directional crypto momentum with clean 1h persistence and acceptable liquidity.
- 层级 / 可试运行: `L4` / `true`
- 运行边界: 静态 registry 只定义策略资产，不授权运行时提交
- 晋级条件: Already current first live-trial lane; live action still depends on runtime state only.
- 降级 / 停放 / 淘汰: Downshift if momentum exhaustion, concentration, stale facts, or protection/account conflicts appear. / Park only after repeated no-edge reviews or Owner selects a different live lane. / Kill if live/replay outcomes show persistent false continuation after costs and protection.
- 风险缺口: strategy_quality_risk: false breakout, fast reversal, choppy no-trade regime; fact_coverage_risk: closed-candle and member-state freshness remain action-time runtime facts; economic_risk: fee, funding, fill-gap slippage, and min-size friction; execution_safety_risk: missing protection, stale account facts, open-order or active-position conflict; authority_risk: L4 tier still is not direct submit authority
- 下一证据: first allocated-subaccount live outcome when fresh signal and official runtime chain pass
- 证据引用: `docs/current/strategy-group-handoffs/MPG-001/handoff.json`, `docs/current/strategy-group-handoffs/MPG-001/replay/mpg-001-replay-corpus.json`, `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json`

### `CPM-RO-001` CPM 回踩收复

- 策略边际: Capture trend-intact pullback followed by reclaim, distinct from MPG momentum continuation.
- 交易逻辑: Long-only pullback-reclaim lane with trend break, failed reclaim, liquidity, funding, and action-time account disables.
- 适用市场结构: Bullish rebound or trend-continuation regime where pullback depth remains normal and reclaim confirms.
- 层级 / 可试运行: `L3` / `true`
- 运行边界: 静态 registry 只定义策略资产，不授权运行时提交
- 晋级条件: Armed observation only; real submit still depends on fresh signal, action-time RequiredFacts, FinalGate, and Operation Layer.
- 降级 / 停放 / 淘汰: Downshift if pullback/reclaim facts, action-time account facts, liquidity, or funding context become unavailable. / Park if identity evidence regresses or CPM becomes redundant with MPG after review. / Kill if replay/live review shows pullback-reclaim has persistent false continuation after costs and protection.
- 风险缺口: strategy_quality_risk: failed reclaim, trend break after pullback, choppy rebound regime; fact_coverage_risk: trend, pullback depth, reclaim, liquidity, funding, and action-time account facts; economic_risk: fee, funding, fill-gap slippage, and pullback continuation failure; execution_safety_risk: missing protection, stale account facts, open-order or active-position conflict; authority_risk: L3 armed observation is not real submit authority
- 下一证据: fresh CPM-LONG signal followed by non-executing candidate authorization and action-time rehearsal evidence
- 证据引用: `docs/current/strategy-group-handoffs/CPM-RO-001/handoff.json`, `output/runtime-monitor/latest-cpm-identity-routing-decision.json`, `output/runtime-monitor/latest-cpm-required-facts-mapping.json`, `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json`

### `TEQ-001` 类股权永续动量

- 策略边际: Capture theme or basket momentum in equity-like perpetual products.
- 交易逻辑: Long-only burst continuation with product eligibility, breadth, and overextension disables.
- 适用市场结构: Theme momentum where product/session and concentration risks are acceptable.
- 层级 / 可试运行: `L2` / `false`
- 运行边界: 静态 registry 只定义策略资产，不授权运行时提交
- 晋级条件: Post-MPG review or explicit Owner lane change plus replay/live evidence that product/session risk is controlled.
- 降级 / 停放 / 淘汰: Downshift if product eligibility, breadth, or session gap facts are unavailable. / Park while theme momentum evidence is thin or concentration risk dominates. / Kill if repeated review shows theme bursts fail after session and cost friction.
- 风险缺口: strategy_quality_risk: low-history product momentum, post-burst overextension, symbol concentration; fact_coverage_risk: theme breadth, product eligibility, and session gap context; economic_risk: session fill slippage and funding/mark review; execution_safety_risk: runtime account, protection, and exchange filters remain hard stops; authority_risk: L2 shadow candidate evidence cannot create real-order authority
- 下一证据: shadow outcomes and cost/session review before any L4 review
- 证据引用: `docs/current/strategy-group-handoffs/TEQ-001/handoff.json`, `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json`

### `FBS-001` 资金费率/基差压力

- 策略边际: Capture funding, basis, and crowding stress where derivatives pressure creates asymmetric continuation or unwind.
- 交易逻辑: Observe derivatives stress; long lane is primary while short side remains disable/redesign-only.
- 适用市场结构: Derivative crowding, negative funding, basis/premium stress, and settlement timing regimes.
- 层级 / 可试运行: `L3` / `false`
- 运行边界: 静态 registry 只定义策略资产，不授权运行时提交
- 晋级条件: Derivatives facts and margin/liquidation mapping must support a Strategy Asset State promote/go-live review after P0 closure or Owner lane change.
- 降级 / 停放 / 淘汰: Downshift if derivatives facts are stale or settlement timing invalidates the setup. / Park if crowding stress is absent or derivatives source quality is too weak. / Kill if stress signals repeatedly fail after funding, basis, and liquidation costs.
- 风险缺口: strategy_quality_risk: crowding stress may unwind before runtime capture, short lane needs redesign; fact_coverage_risk: OI, long/short, top-trader, settlement, and margin/liquidation facts are heavy; economic_risk: funding, basis reversal, spread, and liquidation envelope; execution_safety_risk: protection, account, open-order, and exchange filter facts remain hard stops; authority_risk: L3 armed observation cannot place real orders without separate L4 eligibility
- 下一证据: derivatives source reliability and cost-survival review
- 证据引用: `docs/current/strategy-group-handoffs/FBS-001/handoff.json`, `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json`

### `SOR-001` 开盘区间结构

- 策略边际: Capture opening-range structure after session-specific breakout or revival conditions.
- 交易逻辑: Session-window short lane with long-revival branch only when branch conditions are satisfied.
- 适用市场结构: TradFi-linked session opens with closed range bars, trigger bar, and post-open decay control.
- 层级 / 可试运行: `L3` / `false`
- 运行边界: 静态 registry 只定义策略资产，不授权运行时提交
- 晋级条件: Session branch evidence and post-open decay review must support tier review; no L4 before P0 closure or Owner lane change.
- 降级 / 停放 / 淘汰: Downshift outside valid session/structure window or when trigger bars are not closed. / Park if session conditions cannot be mapped reliably. / Kill if session breakouts repeatedly reverse after gap/fill and time-stop review.
- 风险缺口: strategy_quality_risk: session false breakout, post-open decay, branch-specific long revival uncertainty; fact_coverage_risk: closed open range, trigger bar, and session mapping must be fresh; economic_risk: session gap fill, mark/funding, slippage around session open; execution_safety_risk: closed-bar freshness, protection, account, and exchange filters remain hard stops; authority_risk: L3 conditional observation is not live submit authority
- 下一证据: session replay/outcome review before any higher-tier decision
- 证据引用: `docs/current/strategy-group-handoffs/SOR-001/handoff.json`, `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json`

### `PMR-001` 贵金属制度覆盖

- 策略边际: Use precious-metal regime behavior as an overlay or selected directional context.
- 交易逻辑: Short lane is primary; long is context-only until target-specific role and facts mature.
- 适用市场结构: Commodity-style regimes, silver/gold dominance splits, and regular-session breakdowns.
- 层级 / 可试运行: `L1` / `false`
- 运行边界: 静态 registry 只定义策略资产，不授权运行时提交
- 晋级条件: Clarify target-specific role and attach reliable session/mark facts before L2 review.
- 降级 / 停放 / 淘汰: Remain observe-only when overlay role or session facts are unclear. / Park if it only provides context and does not change runtime decisions. / Kill if overlay signals fail to improve StrategyGroup decisions or outcomes.
- 风险缺口: strategy_quality_risk: overlay may not translate into standalone trade edge, long side is context-only; fact_coverage_risk: metal role split, XAG dominance, and commodity session gap facts; economic_risk: session fill slippage and mark deviation; execution_safety_risk: account, protection, and exchange facts remain hard stops; authority_risk: L1 observe-only cannot create candidates or orders
- 下一证据: role-specific replay and fact maturity before tier review
- 证据引用: `docs/current/strategy-group-handoffs/PMR-001/handoff.json`, `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json`

### `BTPC-001` 熊市回抽延续

- 策略边际: Capture bear-trend pullback continuation when weak rally loses structure and derivatives/crowding context is reviewable.
- 交易逻辑: Short-only L2 shadow lane using pullback structure loss, strong-uptrend disable, squeeze review, and derivatives facts.
- 适用市场结构: Downtrend continuation after weak rally or pullback, excluding strong upside reclaim regimes.
- 层级 / 可试运行: `L2` / `false`
- 运行边界: 静态 registry 只定义策略资产，不授权运行时提交
- 晋级条件: Complete live derivatives fact-source mapping, classifier review, and Strategy Asset State revise resolution before higher-tier review.
- 降级 / 停放 / 淘汰: Downshift if strong-uptrend conflict, stale signal, squeeze risk, or derivatives facts invalidate review. / Park if proxy replay or live derivatives source review shows no durable right-tail edge. / Kill if bear-pullback would-enter cases fail after derivatives, squeeze, freshness, and cost review.
- 风险缺口: strategy_quality_risk: strong-uptrend conflict, stale signal handling, short squeeze classifier quality; fact_coverage_risk: historical OI, global long/short, top-trader ratio, live margin/liquidation model; economic_risk: funding, spread, slippage, leverage survival, liquidation envelope; execution_safety_risk: live facts, protection, account state, and exchange filters remain runtime-only; authority_risk: L2 proxy/replay evidence cannot authorize L4, FinalGate, Operation Layer, or order submit
- 下一证据: execute BTPC L2 fact-source and classifier review tasks locally
- 证据引用: `docs/current/strategy-group-handoffs/BTPC-001/handoff.json`, `docs/current/strategy-group-handoffs/BTPC-001/replay/btpc-001-l2-replay-corpus.json`, `output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-review.json`, `output/runtime-monitor/latest-strategy-asset-state.json`

### `VCB-001` 波动压缩突破

- 策略边际: Capture compression breakout when true breakout evidence survives false-breakout disable review.
- 交易逻辑: Observe long-side breakout candidates; revise false-breakout disable and cost review before L2.
- 适用市场结构: Volatility compression, breakout close, and volume expansion regimes.
- 层级 / 可试运行: `L1` / `false`
- 运行边界: 静态 registry 只定义策略资产，不授权运行时提交
- 晋级条件: False-breakout disable and economic replay must remain stable before L2 review.
- 降级 / 停放 / 淘汰: Keep at L1 or park when replay, facts, classifier, or cost evidence is insufficient. / Park when evidence is weak, negative, low-priority, or not tied to right-tail opportunity. / Kill if replay/live outcomes repeatedly contradict the edge after facts and costs are reviewed.
- 风险缺口: strategy_quality_risk: false breakout reversal, breakout close confirmation fragility; fact_coverage_risk: compression context, volume expansion, disable state; economic_risk: cost m2m, fee, slippage, funding, fill-slot assumptions; execution_safety_risk: runtime facts and protection remain hard stops; authority_risk: L1 observe-only evidence cannot create shadow candidate or real order
- 下一证据: post-revision stage review before any tier change
- 证据引用: `docs/current/strategy-group-handoffs/VCB-001/replay/vcb-001-l1-observe-replay-corpus.json`, `output/runtime-monitor/latest-strategy-asset-state.json`

### `LSR-001` 流动性扫盘/短线复活

- 策略边际: Capture liquidity sweep or short-revival setups after side-specific rewrite quality is proven.
- 交易逻辑: Observe sweep/reclaim cases; keep short-revival rewrite and cost review as promotion prerequisites.
- 适用市场结构: Liquidity sweep, reclaim, and short-revival structures where range context is known.
- 层级 / 可试运行: `L1` / `false`
- 运行边界: 静态 registry 只定义策略资产，不授权运行时提交
- 晋级条件: Side-specific classifier rewrite and economic replay must support non-executing L2 review.
- 降级 / 停放 / 淘汰: Keep at L1 or park when replay, facts, classifier, or cost evidence is insufficient. / Park when evidence is weak, negative, low-priority, or not tied to right-tail opportunity. / Kill if replay/live outcomes repeatedly contradict the edge after facts and costs are reviewed.
- 风险缺口: strategy_quality_risk: lookahead proxy failure, short-revival classifier fragility, range context missing; fact_coverage_risk: liquidity sweep confirmation, reclaim context, disable state; economic_risk: fee, slippage, funding, fill-slot, leverage survival; execution_safety_risk: runtime facts and protection remain hard stops; authority_risk: L1 observe-only evidence cannot create shadow candidate or real order
- 下一证据: post-revision stage review before any tier change
- 证据引用: `docs/current/strategy-group-handoffs/LSR-001/replay/lsr-001-l1-observe-replay-corpus.json`, `output/runtime-monitor/latest-strategy-asset-state.json`

### `BRF-001` 熊市反弹失败

- 策略边际: Capture short continuation after a bear-market rally fails instead of shorting early breakdowns.
- 交易逻辑: Observe rally failure and squeeze-risk cases; require context and classifier quality before L2.
- 适用市场结构: Bear rally failure, rejection, and structure-extreme regimes.
- 层级 / 可试运行: `L1` / `false`
- 运行边界: 静态 registry 只定义策略资产，不授权运行时提交
- 晋级条件: Rally context, squeeze-risk classifier, and cost replay must be attached before L2 review.
- 降级 / 停放 / 淘汰: Keep at L1 or park when replay, facts, classifier, or cost evidence is insufficient. / Park when evidence is weak, negative, low-priority, or not tied to right-tail opportunity. / Kill if replay/live outcomes repeatedly contradict the edge after facts and costs are reviewed.
- 风险缺口: strategy_quality_risk: rally failure context may be weak, short squeeze risk; fact_coverage_risk: rally high/rejection context and squeeze-risk classifier; economic_risk: cost/fill/leverage boundary missing; execution_safety_risk: runtime facts and protection remain hard stops; authority_risk: L1 observe-only evidence cannot create shadow candidate or real order
- 下一证据: post-revision stage review before any tier change
- 证据引用: `docs/current/strategy-group-handoffs/BRF-001/replay/brf-001-l1-observe-replay-corpus.json`, `output/runtime-monitor/latest-strategy-asset-state.json`

### `RBR-001` 区间边界回归

- 策略边际: Range-boundary reversion vocabulary kept only if materially new edge evidence appears.
- 交易逻辑: Currently parked vocabulary; do not allocate active review until new evidence changes decision.
- 适用市场结构: Calm range boundary rejection regimes, currently weak or negative in review.
- 层级 / 可试运行: `L1` / `false`
- 运行边界: 静态 registry 只定义策略资产，不授权运行时提交
- 晋级条件: Materially new positive replay or live-observation evidence is required before unpark.
- 降级 / 停放 / 淘汰: Keep at L1 or park when replay, facts, classifier, or cost evidence is insufficient. / Park when evidence is weak, negative, low-priority, or not tied to right-tail opportunity. / Kill if replay/live outcomes repeatedly contradict the edge after facts and costs are reviewed.
- 风险缺口: strategy_quality_risk: weak edge evidence, negative or low-priority review, range-quality uncertainty; fact_coverage_risk: trend invalidation and range quality facts missing; economic_risk: calm-range m2m failed and cost survival uncertain; execution_safety_risk: runtime facts and protection remain hard stops; authority_risk: parked L1 vocabulary has no candidate or order authority
- 下一证据: new edge evidence strong enough to reopen active review
- 证据引用: `output/runtime-monitor/latest-strategy-asset-state.json`

## Boundary Detail

This registry does not authorize runtime start, candidate creation, FinalGate, Operation Layer, exchange write, real order, live-profile mutation, order-sizing mutation, withdrawal, transfer, or credential mutation.

A real order remains runtime-only and requires selected StrategyGroup scope, allocated subaccount/profile boundary, fresh signal, fresh facts, candidate/auth evidence, action-time execution checks, official submission path, protection, reconciliation, settlement, and review capture.
