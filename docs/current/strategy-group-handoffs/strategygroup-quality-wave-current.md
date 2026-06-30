---
title: STRATEGYGROUP_QUALITY_WAVE_CURRENT
status: CURRENT
authority: docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json
last_verified: 2026-06-20
---

# StrategyGroup Quality Wave Current

## 目的

这份质量治理波次不是单策略报告，也不是主判断源。它把 BTPC / VCB / LSR / BRF / RBR 的 registry、tier review、Strategy Asset State、handoff、replay、RequiredFacts 和本地 monitor 覆盖整理为质量证据 provenance。

当前策略资产判断以 `strategy_asset_state.asset_rows` 为主；本波次只保留质量证据、gap 分类和审计覆盖。静态质量治理不授权实盘。Owner 风险接受可以影响 trial 或 tier policy 路径，但不能绕过运行时安全门。

## 总览

| StrategyGroup | Tier | Decision | System can continue | Primary gap | Next checkpoint |
| --- | --- | --- | --- | --- | --- |
| `BTPC-001` | `L2` | `revise` | `true` | `fact_source_gap` | `complete_fact_source_and_classifier_revision_guard` |
| `VCB-001` | `L1` | `keep_observing` | `true` | `stale_or_missing_artifact_gap` | `create_or_accept_explicit_missing_handoff_boundary_for_VCB-001` |
| `LSR-001` | `L1` | `revise` | `true` | `stale_or_missing_artifact_gap` | `create_or_accept_explicit_missing_handoff_boundary_for_LSR-001` |
| `BRF-001` | `L1` | `promote_review_only` | `true` | `stale_or_missing_artifact_gap` | `create_or_accept_explicit_missing_handoff_boundary_for_BRF-001` |
| `RBR-001` | `L1` | `park` | `false` | `parked_low_priority_gap` | `keep_parked_until_material_new_edge_evidence` |

## 关闭或测试守护的 gap findings

| Closure | StrategyGroup | Gap | Type | Shared |
| --- | --- | --- | --- | --- |
| `quality-wave-shared-source-drift-guard` | `ALL_INCLUDED` | `authority_boundary_gap` | `machine_checkable_test` | `true` |
| `quality-wave-vcb-001-stale_or_missing_artifact_gap` | `VCB-001` | `stale_or_missing_artifact_gap` | `explicit_classification` | `false` |
| `quality-wave-vcb-001-fact_source_gap` | `VCB-001` | `fact_source_gap` | `explicit_classification` | `false` |
| `quality-wave-rbr-001-stale_or_missing_artifact_gap` | `RBR-001` | `stale_or_missing_artifact_gap` | `explicit_classification` | `false` |

## 分组质量判断

### `BTPC-001` 熊市回抽延续

- 吃的机会: Capture bear-trend pullback continuation when weak rally loses structure and derivatives/crowding context is reviewable.
- 当前层级 / 决策: `L2` / `revise`
- 晋级范围 / 目标: `not_applicable` / `not_applicable`
- 系统可继续工程化: `true`
- Owner policy action required: `false`
- 主要 gap / 次要 gap: `fact_source_gap` / `classifier_gap`
- 下一证据: classifier_fact_source_revision_review:BTPC-001_classifier_fact_source_revision_review
- 不晋级原因: capture_gap_audit:BTPC remains blocked by stale/fact-source attribution despite Signal Observation priority; would_enter:0 high_priority_no_action:169 would_enter_forward_positive:0 missed_no_action_forward_positive:155; source_recommendation:revise
- 下一工程 checkpoint: `complete_fact_source_and_classifier_revision_guard`

### `VCB-001` 波动压缩突破

- 吃的机会: Capture compression breakout when true breakout evidence survives false-breakout disable review.
- 当前层级 / 决策: `L1` / `keep_observing`
- 晋级范围 / 目标: `not_applicable` / `not_applicable`
- 系统可继续工程化: `true`
- Owner policy action required: `false`
- 主要 gap / 次要 gap: `stale_or_missing_artifact_gap` / `replay_quality_gap`
- 下一证据: VCB-001_continue_observe_only
- 不晋级原因: capture_gap_audit:current windows mostly fail compression breakout; keep classifier redesign as P1; would_enter:0 high_priority_no_action:0 would_enter_forward_positive:0 missed_no_action_forward_positive:0; source_recommendation:keep_observing
- 下一工程 checkpoint: `create_or_accept_explicit_missing_handoff_boundary_for_VCB-001`

### `LSR-001` 流动性扫盘/短线复活

- 吃的机会: Capture liquidity sweep or short-revival setups after side-specific rewrite quality is proven.
- 当前层级 / 决策: `L1` / `revise`
- 晋级范围 / 目标: `not_applicable` / `not_applicable`
- 系统可继续工程化: `true`
- Owner policy action required: `false`
- 主要 gap / 次要 gap: `stale_or_missing_artifact_gap` / `replay_quality_gap`
- 下一证据: classifier_fact_source_revision_review:LSR-001_classifier_fact_source_revision_review
- 不晋级原因: capture_gap_audit:side-specific rewrite remains the dominant blocker; would_enter:2 high_priority_no_action:167 would_enter_forward_positive:2 missed_no_action_forward_positive:0; source_recommendation:revise
- 下一工程 checkpoint: `create_or_accept_explicit_missing_handoff_boundary_for_LSR-001`

### `BRF-001` 熊市反弹失败

- 吃的机会: Capture short continuation after a bear-market rally fails instead of shorting early breakdowns.
- 当前层级 / 决策: `L1` / `promote_review_only`
- 晋级范围 / 目标: `review_only` / `promotion_evidence_review_only`
- 系统可继续工程化: `true`
- Owner policy action required: `false`
- 主要 gap / 次要 gap: `stale_or_missing_artifact_gap` / `replay_quality_gap`
- 下一证据: promotion_evidence_review_only:BRF-001_forward_outcome_and_requiredfacts_review
- 不晋级原因: capture_gap_audit:official live_market windows produced BRF would_enter; review RequiredFacts and squeeze classifier before any tier change; would_enter:7 high_priority_no_action:162 would_enter_forward_positive:5 missed_no_action_forward_positive:134; source_recommendation:promote_review
- 下一工程 checkpoint: `create_or_accept_explicit_missing_handoff_boundary_for_BRF-001`

### `RBR-001` 区间边界回归

- 吃的机会: Range-boundary reversion vocabulary kept only if materially new edge evidence appears.
- 当前层级 / 决策: `L1` / `park`
- 晋级范围 / 目标: `not_applicable` / `not_applicable`
- 系统可继续工程化: `false`
- Owner policy action required: `false`
- 主要 gap / 次要 gap: `parked_low_priority_gap` / `replay_quality_gap`
- 下一证据: material_new_edge_evidence_before_reactivation
- 不晋级原因: capture_gap_audit:parked vocabulary lane unless materially new positive forward evidence appears; would_enter:0 high_priority_no_action:0 would_enter_forward_positive:0 missed_no_action_forward_positive:0; source_recommendation:park
- 下一工程 checkpoint: `keep_parked_until_material_new_edge_evidence`

## 权限边界

本波次只服务 StrategyGroup 质量治理，不部署、不下单、不修改实盘配置、不修改杠杆/仓位/订单大小默认值、不创建提现或划转动作。
