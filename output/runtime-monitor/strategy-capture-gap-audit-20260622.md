# Strategy Capture Gap Audit

## 结论

- **结论**: 当前不能只归因为没有 fresh signal；官方公开行情滑窗审计支持 **Strategy Capture Gap**。
- **P0 状态**: 主链路保持 `waiting_for_market`，不是执行链故障。
- **P0.5 状态**: 至少有一个 StrategyGroup 需要进入捕获质量与 forward outcome 复核。
- **权限边界**: 本产物只读官方公开行情，不调参、不改 tier、不改 live profile、不调用 FinalGate / Operation Layer。

## 已知客观事实

- **官方时间**: `2026-06-22T04:56:16.166000+00:00`。
- **审计窗口**: 最近 `168` 小时，步长 `1` 小时。
- **评估窗口数**: `169`。
- **would_enter 总数**: `52`。
- **would_enter 样本**: `30` sampled / `22` omitted。
- **high-priority no_action 总数**: `671`。
- **high-priority no_action 样本**: `30` sampled / `641` omitted。

### Audit Contract

| Event class | Total | Sampled | Omitted | Sample limit |
| --- | ---: | ---: | ---: | ---: |
| **would_enter** | 52 | 30 | 22 | 30 |
| **high_priority_no_action** | 671 | 30 | 641 | 30 |

### Forward Outcome Summary

| Class | Window | Completed | Pending | Unavailable | Not applicable | Tradable MFE after cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| **would_enter** | 12h | 49 | 3 | 0 | 0 | 44 |
| **would_enter** | 24h | 48 | 4 | 0 | 0 | 44 |
| **would_enter** | 4h | 51 | 1 | 0 | 0 | 39 |
| **missed_no_action** | 12h | 469 | 47 | 0 | 155 | 394 |
| **missed_no_action** | 24h | 433 | 94 | 0 | 144 | 376 |
| **missed_no_action** | 4h | 493 | 15 | 0 | 163 | 314 |

### Owner 可见性状态

| Field | Value |
| --- | --- |
| **p0_state** | `waiting_for_market` |
| **p0_5_observation_state** | `review_needed` |
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
| **BTCUSDT** | -0.720% | 1.897% | -2.974% | 3.935% | 0.339 | 0.479 | 1.360 |
| **ETHUSDT** | -0.444% | 1.927% | 0.534% | 4.694% | 0.330 | 0.479 | 1.419 |
| **SOLUSDT** | -0.136% | 6.447% | 3.203% | 9.677% | 0.684 | 0.521 | 1.258 |
| **BNBUSDT** | -0.064% | 2.087% | -4.516% | 4.277% | 0.315 | 0.606 | 1.347 |
| **AVAXUSDT** | -0.511% | 1.302% | -7.928% | 11.197% | 0.393 | 0.521 | 0.576 |
| **LINKUSDT** | -1.305% | -0.178% | -4.028% | 3.268% | 0.119 | 0.465 | 1.380 |
| **XRPUSDT** | -1.706% | -0.817% | -4.812% | 3.241% | 0.063 | 0.521 | 1.561 |
| **ADAUSDT** | -2.769% | -2.469% | -12.804% | 5.633% | 0.056 | 0.479 | 1.619 |

### 衍生品结构

| Symbol | 72h OI change | 72h funding sum |
| --- | ---: | ---: |
| **BTCUSDT** | 1.344 | 0.0318% |
| **ETHUSDT** | -0.754 | 0.0169% |
| **SOLUSDT** | 3.049 | 0.0064% |
| **BNBUSDT** | -1.103 | 0.0116% |
| **AVAXUSDT** | 10.413 | -0.0753% |
| **LINKUSDT** | -2.455 | 0.0239% |
| **XRPUSDT** | 2.539 | -0.0202% |
| **ADAUSDT** | 11.567 | -0.1293% |

## StrategyGroup 期望与实际观察

| StrategyGroup | 期望行为 | would_enter | high-priority no_action | WE 正向 | missed NA 正向 | 主要阻断 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| **BRF-001** | bear-rally failure short; rally extension plus rejection should produce observe-only would_enter | 1 | 168 | 0 | 136 | market_structure_not_confirmed:85, no_action_other:63, classifier_threshold_not_met:20, observe_only_would_enter:1 |
| **BTPC-001** | bear-trend pullback continuation; stale/fact/classifier gaps may block L2 progression | 0 | 169 | 0 | 152 | stale_data_or_signal:169 |
| **CPM-RO-001** | not documented in current expectation map | 18 | 0 | 13 | 0 | no_action_other:87, classifier_threshold_not_met:64, observe_only_would_enter:18 |
| **FBS-001** | funding/basis/crowding stress; missing derivatives facts are attribution, not live authority | 0 | 0 | 0 | 0 | none |
| **LSR-001** | liquidity sweep or short-revival rewrite; side-specific rewrite gaps are expected blockers | 2 | 167 | 2 | 0 | no_action_other:167, observe_only_would_enter:2 |
| **MI-001** | not documented in current expectation map | 23 | 0 | 22 | 0 | no_action_other:315, observe_only_would_enter:23 |
| **MPG-001** | clean long momentum persistence; selected P0 lane only reacts to eligible mainline symbols | 0 | 0 | 0 | 0 | none |
| **RBR-001** | range-boundary rejection vocabulary; parked unless material new edge appears | 6 | 0 | 6 | 0 | no_action_other:163, observe_only_would_enter:6 |
| **SOR-001** | session range breakout/revival; repeated no_action should remain visible, not just waiting | 0 | 0 | 0 | 0 | none |
| **VCB-001** | volatility compression breakout; compression plus breakout should enter review | 2 | 167 | 2 | 135 | classifier_threshold_not_met:162, no_action_other:5, observe_only_would_enter:2 |

## Would-Enter Forward Outcome

| Time UTC | StrategyGroup | Symbol | Side | 4h MFE/MAE | 12h MFE/MAE | 24h MFE/MAE |
| --- | --- | --- | --- | ---: | ---: | ---: |
| 2026-06-22T03:00:00+00:00 | **BRF-001** | BTC/USDT:USDT | short | pending | pending | pending |
| 2026-06-21T23:00:00+00:00 | **CPM-RO-001** | ETH/USDT:USDT | short | 0.012 / -3.108 | pending | pending |
| 2026-06-21T18:00:00+00:00 | **CPM-RO-001** | ETH/USDT:USDT | long | 0.223 / -1.971 | pending | pending |
| 2026-06-21T10:00:00+00:00 | **LSR-001** | XRP/USDT:USDT | short | 0.767 / -0.174 | 2.492 / -0.287 | pending |
| 2026-06-20T22:00:00+00:00 | **CPM-RO-001** | ETH/USDT:USDT | long | 0.026 / -0.524 | 0.026 / -1.129 | 0.026 / -2.417 |
| 2026-06-20T14:00:00+00:00 | **MI-001** | SOL/USDT:USDT | long | 1.015 / -1.182 | 3.311 / -1.182 | 3.491 / -1.182 |
| 2026-06-20T14:00:00+00:00 | **CPM-RO-001** | ETH/USDT:USDT | long | 0.945 / -0.736 | 0.945 / -0.736 | 0.945 / -0.967 |
| 2026-06-20T14:00:00+00:00 | **RBR-001** | ADA/USDT:USDT | long | 0.865 / -1.112 | 1.236 / -1.112 | 1.236 / -1.298 |
| 2026-06-20T10:00:00+00:00 | **MI-001** | SOL/USDT:USDT | long | 0.712 / -1.703 | 3.671 / -1.703 | 3.853 / -1.703 |
| 2026-06-20T09:00:00+00:00 | **MI-001** | SOL/USDT:USDT | long | 0.769 / -1.147 | 1.552 / -1.524 | 3.860 / -1.524 |
| 2026-06-20T08:00:00+00:00 | **MI-001** | SOL/USDT:USDT | long | 1.066 / -0.210 | 1.851 / -1.234 | 4.165 / -1.234 |
| 2026-06-20T07:00:00+00:00 | **MI-001** | SOL/USDT:USDT | long | 0.713 / -0.559 | 1.495 / -1.579 | 3.802 / -1.579 |

## 决策建议

| StrategyGroup | Decision | Reason | Next checkpoint |
| --- | --- | --- | --- |
| **BRF-001** | `promote_review` | official live_market windows produced BRF would_enter; review RequiredFacts and squeeze classifier before any tier change | `BRF-001_forward_outcome_and_requiredfacts_review` |
| **BTPC-001** | `revise` | BTPC remains blocked by stale/fact-source attribution despite P0.5 priority | `BTPC-001_classifier_fact_source_revision_review` |
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
| **real_order_authority** | `false` |
| **preview_or_replay_treated_as_live_signal** | `false` |

## 输出

- **JSON**: `output/runtime-monitor/strategy-capture-gap-audit-20260622.json`
- **Markdown**: `output/runtime-monitor/strategy-capture-gap-audit-20260622.md`
