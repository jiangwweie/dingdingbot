# StrategyGroup Regime Role Coverage Map

## 结论

- **当前 StrategyGroup 体系不是缺少熊市 / 震荡 / 做空语义，而是这些语义多数还不成熟。**
- **MI-001 / CPM-RO-001** 的近期机会更亮，容易让 Trial Pool 偏向多头或反弹动量；本盘点要求继续保留 **BRF / BTPC / LSR / RBR / FBS / SOR / VCB** 的弱市角色可见性。
- **真正需要 strategy-research bounded lane 的重点不是再造全部 short 策略，而是 range-reversion、false-breakout/compression-failure、derivatives-stress 的补证或替代语义。**

## 已知客观事实

- **输出 JSON**: `/Users/jiangwei/Documents/final/output/runtime-monitor/latest-strategygroup-regime-role-coverage-map.json`
- **Schema**: `brc.strategygroup_regime_role_coverage_map.v1`
- **Scope**: `local_review_only`
- **Active review groups**: `10`
- **Active review group source**: `portfolio_board.portfolio_summary.active_review_strategy_groups`
- **Missing in specs**: `[]`
- **Extra in specs**: `[]`
- **Role buckets**: `10`
- **External market refresh**: `False`

## 当前市场 regime 判断

- **P0 状态**: `waiting_for_market`
- **P0.5 状态**: `review_needed`
- **Strategy Capture Gap**: `True`
- **Gap 证据字段**: `audit_conclusion.strategy_capture_gap_supported`
- **判断来源**: `local_current_artifacts_only`
- **解释**: The latest local artifacts show no P0 executable fresh signal, but P0.5 strategy observation is active. Recent opportunity evidence is concentrated in MI and CPM long/rebound structures, while short, range, and derivatives-stress roles are covered mainly by immature or fact/classifier-blocked StrategyGroups.
- **限制**: This task did not refresh public Binance klines/funding/OI; it uses the current committed/generated artifacts as the review authority.

## StrategyGroup 角色覆盖表

| StrategyGroup | Owner Label | Tier | Evidence | Role | Buckets | Recent | Tradable | Blocker | Trial Pool | Next |
| --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- | --- |
| `MPG-001` | **动量延续** | `L4` | `trial_waiting` | selected long momentum trial lane | `trend_long` | 0 | 0 | `none_recorded` | `trial_waiting` | `MPG-001_no_action_visibility_and_routing_audit` |
| `BRF-001` | **熊市反弹失败** | `L1` | `promote_review` | bear rally failure promote-review lane | `bear_rally_failure_short` | 1 | 0 | `market_structure_not_confirmed` | `promote_review` | `BRF-001_forward_outcome_and_requiredfacts_review` |
| `BTPC-001` | **熊市回抽延续** | `L2` | `revise` | bear pullback continuation L2 shadow lane | `bear_pullback_continuation_short, derivatives_stress` | 0 | 0 | `stale_data_or_signal` | `revise` | `BTPC-001_classifier_fact_source_revision_review` |
| `LSR-001` | **流动性扫盘/短线复活** | `L1` | `revise` | liquidity sweep and short-revival rewrite lane | `liquidity_sweep_reversal, bear_pullback_continuation_short` | 2 | 2 | `no_action_other` | `revise` | `LSR-001_classifier_fact_source_revision_review` |
| `MI-001` | **动量冲击** | `unknown` | `identity_review` | high-signal momentum-impulse identity candidate | `momentum_impulse, unclear_or_identity_review` | 23 | 22 | `no_action_other` | `identity_review` | `MI-001_registry_identity_review` |
| `CPM-RO-001` | **CPM 回补观察** | `unknown` | `identity_review` | mild-trend pullback observation asset | `trend_long, unclear_or_identity_review` | 18 | 13 | `no_action_other` | `identity_review` | `CPM-RO-001_registry_identity_review` |
| `FBS-001` | **资金费率/基差压力** | `L3` | `coverage_visibility_review` | derivatives-stress armed observation lane | `derivatives_stress` | 0 | 0 | `none_recorded` | `not_in_trial_pool` | `FBS-001_no_action_visibility_and_routing_audit` |
| `SOR-001` | **开盘区间结构** | `L3` | `coverage_visibility_review` | session-structure armed observation lane | `session_structure` | 0 | 0 | `none_recorded` | `not_in_trial_pool` | `SOR-001_no_action_visibility_and_routing_audit` |
| `VCB-001` | **波动压缩突破** | `L1` | `observe` | volatility compression breakout observe lane | `false_breakout_or_compression_failure` | 2 | 2 | `classifier_threshold_not_met` | `not_in_trial_pool` | `VCB-001_continue_observe_only` |
| `RBR-001` | **区间边界回归** | `L1` | `park` | parked range-boundary vocabulary | `range_reversion` | 6 | 6 | `no_action_other` | `not_in_trial_pool` | `park_until_material_new_edge_evidence` |

## 熊市 / 震荡 / 做空语义缺口

| Bucket | Meaning | Coverage | Groups | Gap Classes | Final Need | Research Need |
| --- | --- | --- | --- | --- | --- | --- |
| `trend_long` | **多头趋势 / 动量延续** | `covered_in_trial_review` | `MPG-001, CPM-RO-001` | `classifier_gap, identity_gap, maturity_gap, visibility_gap` | Keep MPG P0 standby; close CPM identity and no-action visibility before adding long-trend trial scope. | `no_research_needed` |
| `momentum_impulse` | **短期动量冲击 / 反弹动量** | `covered_in_trial_review` | `MI-001` | `identity_gap` | Resolve MI identity, overlap, concentration, and tier unknown status inside final. | `no_research_needed` |
| `bear_rally_failure_short` | **熊市反弹失败做空** | `covered_in_trial_review` | `BRF-001` | `fact_source_gap, maturity_gap` | Complete BRF forward outcome, squeeze classifier, and RequiredFacts review. | `no_research_needed` |
| `bear_pullback_continuation_short` | **熊市回抽延续做空** | `covered_in_trial_review` | `BTPC-001, LSR-001` | `classifier_gap, fact_source_gap, maturity_gap` | Attach BTPC fact sources and close LSR side-specific range-context rewrite. | `no_research_needed` |
| `range_reversion` | **区间边界回归** | `covered_parked_or_weak` | `RBR-001` | `maturity_gap, true_research_gap` | Keep RBR parked unless new edge evidence appears; define active range-quality evidence standard. | `bounded_research_recommended` |
| `liquidity_sweep_reversal` | **扫盘 / reclaim / rejection** | `covered_in_trial_review` | `LSR-001` | `classifier_gap, maturity_gap` | Complete LSR range-context facts and side-specific rewrite quality review. | `no_research_needed` |
| `false_breakout_or_compression_failure` | **假突破 / 压缩失败** | `covered_low_maturity` | `VCB-001` | `classifier_gap, maturity_gap` | Review VCB compression/false-breakout classifier and cost sensitivity. | `bounded_research_recommended` |
| `derivatives_stress` | **funding / OI / basis / squeeze risk** | `covered_in_trial_review` | `BTPC-001, FBS-001` | `classifier_gap, fact_source_gap, visibility_gap` | Attach funding, basis, OI, and squeeze-risk fact sources before promotion. | `research_required_before_trial` |
| `session_structure` | **session range / 开盘结构** | `covered_but_not_trial_ready` | `SOR-001` | `maturity_gap, visibility_gap` | Expose SOR no-action/session attribution and session-window readiness. | `bounded_research_recommended` |
| `unclear_or_identity_review` | **身份未定** | `covered_in_trial_review` | `MI-001, CPM-RO-001` | `classifier_gap, identity_gap` | Resolve registry identity before runtime or trial interpretation. | `no_research_needed` |

## 哪些在 final 内补

- **MPG-001**: MPG-001_no_action_visibility_and_routing_audit。缺口：`visibility_gap, maturity_gap`。
- **BRF-001**: BRF-001_forward_outcome_and_requiredfacts_review。缺口：`maturity_gap, fact_source_gap`。
- **BTPC-001**: BTPC-001_classifier_fact_source_revision_review。缺口：`classifier_gap, fact_source_gap`。
- **LSR-001**: LSR-001_classifier_fact_source_revision_review。缺口：`classifier_gap, maturity_gap`。
- **MI-001**: MI-001_registry_identity_review。缺口：`identity_gap`。
- **CPM-RO-001**: CPM-RO-001_registry_identity_review。缺口：`identity_gap, classifier_gap`。
- **FBS-001**: FBS-001_no_action_visibility_and_routing_audit。缺口：`fact_source_gap, visibility_gap`。
- **SOR-001**: SOR-001_no_action_visibility_and_routing_audit。缺口：`visibility_gap, maturity_gap`。
- **VCB-001**: VCB-001_continue_observe_only。缺口：`classifier_gap, maturity_gap`。
- **RBR-001**: park_until_material_new_edge_evidence。缺口：`maturity_gap, true_research_gap`。

## 哪些需要 strategy-research bounded lane

| Role Bucket | Decision | Reason |
| --- | --- | --- |
| `trend_long` | `no_research_needed` | Current final assets cover the role enough for engineering closure before new research. |
| `momentum_impulse` | `no_research_needed` | Current final assets cover the role enough for engineering closure before new research. |
| `bear_rally_failure_short` | `no_research_needed` | Current final assets cover the role enough for engineering closure before new research. |
| `bear_pullback_continuation_short` | `no_research_needed` | Current final assets cover the role enough for engineering closure before new research. |
| `range_reversion` | `bounded_research_recommended` | RBR exists but is parked; a trial-quality weak-range lane needs bounded research evidence. |
| `liquidity_sweep_reversal` | `no_research_needed` | Current final assets cover the role enough for engineering closure before new research. |
| `false_breakout_or_compression_failure` | `bounded_research_recommended` | VCB exists but classifier quality is not enough; bounded research can test failure/rejection variants. |
| `derivatives_stress` | `research_required_before_trial` | FBS requires derivatives facts and stress semantics before trial; research should stay bounded and fact-first. |
| `session_structure` | `bounded_research_recommended` | SOR exists but is narrow and visibility-poor; bounded research can expand session structures after final visibility is fixed. |
| `unclear_or_identity_review` | `no_research_needed` | Current final assets cover the role enough for engineering closure before new research. |

## 对 Trial Candidate Pool 的影响

- **Trial candidate count**: `5`
- **Trial eligible count**: `1`
- **Actionable now count**: `0`
- **结论**: The current trial pool is useful, but opportunity evidence is skewed toward MI/CPM and MPG-style long or rebound momentum. Weak-market and range roles should remain visible as review lanes so the system does not overfit the next trial pool to recent long-side brightness.
- **新增候选触发条件**:
  - RBR replacement or revision shows repeatable positive range-reversion outcomes after costs
  - FBS derivatives RequiredFacts are attached and produce reviewable stress/squeeze packets
  - BTPC stale/fact-source blockers are resolved and false-negative review remains positive
  - BRF forward outcome plus squeeze classifier supports L2 review without live scope expansion

## 安全边界

| Invariant | Value |
| --- | --- |
| `real_order_authority` | `false` |
| `actionable_now` | `false` |
| `calls_finalgate` | `false` |
| `calls_operation_layer` | `false` |
| `calls_exchange_write` | `false` |
| `order_created` | `false` |
| `live_profile_changed` | `false` |
| `tier_policy_changed` | `false` |
| `strategy_parameters_changed` | `false` |
| `registry_authority_changed` | `false` |
| `server_files_mutated` | `false` |

## Registry-only 说明

- **PMR-001** / **贵金属制度覆盖**: Registry-only in this wave: precious-metal overlay remains L1 observe-only and is not part of the active Portfolio Board / Trial Candidate Pool.
- **TEQ-001** / **类股权永续动量**: Registry-only in this wave: equity-like momentum is L2 shadow-capable, but this task focuses on active review board gaps, not broad long-theme expansion.
