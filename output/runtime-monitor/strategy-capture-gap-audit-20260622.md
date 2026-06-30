# Strategy Capture Gap Audit

## 结论

- **结论**: 当前不能只归因为没有 fresh signal；官方公开行情滑窗审计支持 **Strategy Capture Gap**。
- **P0 状态**: 主链路保持 `waiting_for_market`，不是执行链故障。
- **Signal Observation 状态**: 至少有一个 StrategyGroup 需要进入捕获质量与 forward outcome 复核。
- **权限边界**: 本产物只读官方公开行情，不调参、不改 tier、不改 live profile、不调用 FinalGate / Operation Layer。

## 已知客观事实

- **官方时间**: `2026-06-26T07:32:46.274000+00:00`。
- **审计窗口**: 最近 `168` 小时，步长 `1` 小时。
- **评估窗口数**: `169`。
- **would_enter 总数**: `55`。
- **would_enter 样本**: `30` sampled / `25` omitted。
- **high-priority no_action 总数**: `665`。
- **high-priority no_action 样本**: `30` sampled / `635` omitted。

### Audit Contract

| Event class | Total | Sampled | Omitted | Sample limit |
| --- | ---: | ---: | ---: | ---: |
| **would_enter** | 55 | 30 | 25 | 30 |
| **high_priority_no_action** | 665 | 30 | 635 | 30 |

### Forward Outcome Summary

| Class | Window | Completed | Pending | Unavailable | Not applicable | Tradable MFE after cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| **would_enter** | 12h | 47 | 8 | 0 | 0 | 31 |
| **would_enter** | 24h | 43 | 12 | 0 | 0 | 34 |
| **would_enter** | 4h | 51 | 4 | 0 | 0 | 31 |
| **missed_no_action** | 12h | 465 | 45 | 0 | 155 | 373 |
| **missed_no_action** | 24h | 430 | 92 | 0 | 143 | 379 |
| **missed_no_action** | 4h | 487 | 15 | 0 | 163 | 306 |

### Owner 可见性状态

| Field | Value |
| --- | --- |
| **p0_state** | `waiting_for_market` |
| **signal_observation_state** | `review_needed` |
| **observation_active** | `True` |
| **review_needed_strategy_groups** | `['BRF-001', 'BTPC-001', 'CPM-RO-001', 'LSR-001', 'MI-001']` |
| **no_live_permission** | `True` |
| **owner_intervention_required** | `False` |

### Phase Closure

| Phase | Status / Groups |
| --- | --- |
| **Phase 1 Audit Contract** | `ready` |
| **Phase 2 Priority Lines** | `BTPC-001:revise, LSR-001:revise, BRF-001:promote_review` |
| **Phase 3 Identity Review** | `MI-001:identity_review, CPM-RO-001:identity_review` |
| **Phase 4 Visibility Review** | `MPG-001:coverage_visibility_review, SOR-001:coverage_visibility_review, FBS-001:coverage_visibility_review` |

### 官方市场结构

| Symbol | 24h | 72h | 7d | 72h range | 7d pos | 72h trend | 12h/72h vol |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **BTCUSDT** | -2.261% | -4.144% | -4.082% | 8.590% | 0.300 | 0.493 | 0.897 |
| **ETHUSDT** | -5.024% | -7.163% | -7.607% | 11.770% | 0.221 | 0.521 | 0.945 |
| **SOLUSDT** | 0.792% | -0.441% | 1.834% | 9.317% | 0.545 | 0.493 | 0.987 |
| **BNBUSDT** | -1.176% | -2.903% | -1.770% | 7.516% | 0.385 | 0.535 | 0.803 |
| **AVAXUSDT** | -5.050% | 1.282% | 3.310% | 11.038% | 0.591 | 0.521 | 0.705 |
| **LINKUSDT** | -3.297% | -5.496% | -7.843% | 9.913% | 0.236 | 0.535 | 0.735 |
| **XRPUSDT** | -4.009% | -6.166% | -7.921% | 10.403% | 0.231 | 0.479 | 0.934 |
| **ADAUSDT** | -3.140% | -6.149% | -9.714% | 12.207% | 0.257 | 0.394 | 0.814 |

### 衍生品结构

| Symbol | 72h OI change | 72h funding sum |
| --- | ---: | ---: |
| **BTCUSDT** | 8.596 | 0.0077% |
| **ETHUSDT** | 1.260 | -0.0017% |
| **SOLUSDT** | 2.478 | -0.0654% |
| **BNBUSDT** | -2.381 | 0.0000% |
| **AVAXUSDT** | -10.590 | 0.0050% |
| **LINKUSDT** | 6.163 | 0.0069% |
| **XRPUSDT** | 0.084 | -0.0541% |
| **ADAUSDT** | 9.342 | -0.0977% |

## StrategyGroup 期望与实际观察

| StrategyGroup | 期望行为 | would_enter | high-priority no_action | WE 正向 | missed NA 正向 | 主要阻断 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| **BRF-001** | bear-rally failure short; rally extension plus rejection should produce observe-only would_enter | 7 | 162 | 5 | 134 | market_structure_not_confirmed:107, classifier_threshold_not_met:55, observe_only_would_enter:7 |
| **BTPC-001** | bear-trend pullback continuation; stale/fact/classifier gaps may block L2 progression | 0 | 169 | 0 | 155 | stale_data_or_signal:169 |
| **CPM-RO-001** | not documented in current expectation map | 18 | 0 | 13 | 0 | no_action_other:91, classifier_threshold_not_met:60, observe_only_would_enter:18 |
| **FBS-001** | funding/basis/crowding stress; missing derivatives facts are attribution, not live authority | 0 | 0 | 0 | 0 | none |
| **LSR-001** | liquidity sweep or short-revival rewrite; side-specific rewrite gaps are expected blockers | 2 | 167 | 2 | 0 | no_action_other:167, observe_only_would_enter:2 |
| **MI-001** | not documented in current expectation map | 17 | 0 | 12 | 0 | no_action_other:321, observe_only_would_enter:17 |
| **MPG-001** | clean long momentum persistence; selected P0 lane only reacts to eligible mainline symbols | 0 | 0 | 0 | 0 | none |
| **RBR-001** | range-boundary rejection vocabulary; parked unless material new edge appears | 9 | 0 | 5 | 0 | no_action_other:160, observe_only_would_enter:9 |
| **SOR-001** | session range breakout/revival; repeated no_action should remain visible, not just waiting | 0 | 0 | 0 | 0 | none |
| **VCB-001** | volatility compression breakout; compression plus breakout should enter review | 2 | 167 | 2 | 133 | classifier_threshold_not_met:160, no_action_other:7, observe_only_would_enter:2 |

## Would-Enter Forward Outcome

| Time UTC | StrategyGroup | Symbol | Side | 4h MFE/MAE | 12h MFE/MAE | 24h MFE/MAE |
| --- | --- | --- | --- | ---: | ---: | ---: |
| 2026-06-26T06:00:00+00:00 | **MI-001** | SOL/USDT:USDT | long | pending | pending | pending |
| 2026-06-26T04:00:00+00:00 | **MI-001** | SOL/USDT:USDT | long | pending | pending | pending |
| 2026-06-26T04:00:00+00:00 | **BRF-001** | BTC/USDT:USDT | short | pending | pending | pending |
| 2026-06-26T03:00:00+00:00 | **RBR-001** | ADA/USDT:USDT | long | pending | pending | pending |
| 2026-06-26T02:00:00+00:00 | **VCB-001** | LINK/USDT:USDT | short | 0.652 / -3.161 | pending | pending |
| 2026-06-26T01:00:00+00:00 | **MI-001** | SOL/USDT:USDT | long | 1.768 / -2.125 | pending | pending |
| 2026-06-26T01:00:00+00:00 | **MI-001** | BNB/USDT:USDT | long | 0.927 / -1.471 | pending | pending |
| 2026-06-25T23:00:00+00:00 | **BRF-001** | BTC/USDT:USDT | short | 2.483 / -0.592 | pending | pending |
| 2026-06-25T16:00:00+00:00 | **BRF-001** | BTC/USDT:USDT | short | 0.286 / -0.828 | 1.680 / -1.621 | pending |
| 2026-06-25T13:00:00+00:00 | **CPM-RO-001** | ETH/USDT:USDT | short | 0.001 / -3.685 | 0.001 / -3.685 | pending |
| 2026-06-25T12:00:00+00:00 | **RBR-001** | ADA/USDT:USDT | long | 0.338 / -6.752 | 0.338 / -6.752 | pending |
| 2026-06-25T07:00:00+00:00 | **MI-001** | SOL/USDT:USDT | long | 0.014 / -2.075 | 0.014 / -7.781 | pending |

## 观察建议

| StrategyGroup | Observation Recommendation | Reason | Next checkpoint |
| --- | --- | --- | --- |
| **BRF-001** | `promote_review` | official live_market windows produced BRF would_enter; review RequiredFacts and squeeze classifier before any tier change | `BRF-001_forward_outcome_and_requiredfacts_review` |
| **BTPC-001** | `revise` | BTPC remains blocked by stale/fact-source attribution despite Signal Observation priority | `BTPC-001_classifier_fact_source_revision_review` |
| **CPM-RO-001** | `identity_review` | CPM emits repeated would_enter events but is not documented in the current expectation map | `CPM-RO-001_registry_identity_review` |
| **FBS-001** | `coverage_visibility_review` | mainline no_action reasons should stay visible when waiting_for_market is reported | `FBS-001_no_action_visibility_and_routing_audit` |
| **LSR-001** | `revise` | side-specific rewrite remains the dominant blocker | `LSR-001_classifier_fact_source_revision_review` |
| **MI-001** | `identity_review` | MI emits repeated would_enter events but is still treated like a smoke lane; classify as smoke, MPG sub-capability, or formal candidate | `MI-001_registry_identity_review` |
| **MPG-001** | `coverage_visibility_review` | mainline no_action reasons should stay visible when waiting_for_market is reported | `MPG-001_no_action_visibility_and_routing_audit` |
| **RBR-001** | `park` | parked vocabulary lane unless materially new positive forward evidence appears | `park_until_material_new_edge_evidence` |
| **SOR-001** | `coverage_visibility_review` | mainline no_action reasons should stay visible when waiting_for_market is reported | `SOR-001_no_action_visibility_and_routing_audit` |
| **VCB-001** | `keep_observing` | current windows mostly fail compression breakout; keep classifier redesign as P1 | `VCB-001_continue_observe_only` |

## 安全边界

| 项目 | 值 |
| --- | --- |
| **read_only_official_public_market_data** | `true` |
| **uses_local_sqlite_for_recent_market** | `false` |
| **calls_finalgate** | `false` |
| **calls_operation_layer** | `false` |
| **calls_exchange_write** | `false` |
| **places_order** | `false` |
| **creates_execution_intent** | `false` |
| **server_files_mutated** | `false` |
| **strategy_parameters_changed** | `false` |
| **tier_policy_changed** | `false` |
| **live_profile_changed** | `false` |
| **preview_or_replay_treated_as_live_signal** | `false` |

## 输出

- **JSON**: `output/runtime-monitor/strategy-capture-gap-audit-20260622.json`
- **Markdown**: `output/runtime-monitor/strategy-capture-gap-audit-20260622.md`
