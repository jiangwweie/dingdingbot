---
title: STRATEGYGROUP_QUALITY_WAVE_CURRENT
status: CURRENT
authority: docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json
last_verified: 2026-06-20
---

# StrategyGroup Quality Wave Current

## 目的

这份质量治理波次不是单策略报告。它把 BTPC / VCB / LSR / BRF / RBR 的 registry、tier review、Decision Ledger、handoff、replay、RequiredFacts 和本地 monitor 覆盖合并成一张可推进矩阵。

静态质量治理不授权实盘。Owner 风险接受可以影响 trial 或 tier policy 路径，但不能把 `actionable_now` 置为 true，也不能绕过运行时安全门。

## 总览

| StrategyGroup | Tier | Decision | System can continue | Primary gap | Next checkpoint |
| --- | --- | --- | --- | --- | --- |
| `BTPC-001` | `L2` | `revise` | `true` | `fact_source_gap` | `complete_fact_source_and_classifier_revision_guard` |
| `VCB-001` | `L1` | `keep_observing` | `true` | `stale_or_missing_artifact_gap` | `create_or_accept_explicit_missing_handoff_boundary_for_VCB-001` |
| `LSR-001` | `L1` | `keep_observing` | `true` | `stale_or_missing_artifact_gap` | `create_or_accept_explicit_missing_handoff_boundary_for_LSR-001` |
| `BRF-001` | `L1` | `keep_observing` | `true` | `stale_or_missing_artifact_gap` | `create_or_accept_explicit_missing_handoff_boundary_for_BRF-001` |
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
- 系统可继续工程化: `true`
- Owner policy action required: `false`
- 主要 gap / 次要 gap: `fact_source_gap` / `classifier_gap`
- 下一证据: feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_decision
- 不晋级原因: current ledger requires revision before any tier change
- 下一工程 checkpoint: `complete_fact_source_and_classifier_revision_guard`

### `VCB-001` 波动压缩突破

- 吃的机会: Capture compression breakout when true breakout evidence survives false-breakout disable review.
- 当前层级 / 决策: `L1` / `keep_observing`
- 系统可继续工程化: `true`
- Owner policy action required: `false`
- 主要 gap / 次要 gap: `stale_or_missing_artifact_gap` / `replay_quality_gap`
- 下一证据: tier_review_after_post_revision_quality
- 不晋级原因: current ledger supports continued observation, not tier promotion
- 下一工程 checkpoint: `create_or_accept_explicit_missing_handoff_boundary_for_VCB-001`

### `LSR-001` 流动性扫盘/短线复活

- 吃的机会: Capture liquidity sweep or short-revival setups after side-specific rewrite quality is proven.
- 当前层级 / 决策: `L1` / `keep_observing`
- 系统可继续工程化: `true`
- Owner policy action required: `false`
- 主要 gap / 次要 gap: `stale_or_missing_artifact_gap` / `replay_quality_gap`
- 下一证据: tier_review_after_post_revision_quality
- 不晋级原因: current ledger supports continued observation, not tier promotion
- 下一工程 checkpoint: `create_or_accept_explicit_missing_handoff_boundary_for_LSR-001`

### `BRF-001` 熊市反弹失败

- 吃的机会: Capture short continuation after a bear-market rally fails instead of shorting early breakdowns.
- 当前层级 / 决策: `L1` / `keep_observing`
- 系统可继续工程化: `true`
- Owner policy action required: `false`
- 主要 gap / 次要 gap: `stale_or_missing_artifact_gap` / `replay_quality_gap`
- 下一证据: tier_review_after_post_revision_quality
- 不晋级原因: current ledger supports continued observation, not tier promotion
- 下一工程 checkpoint: `create_or_accept_explicit_missing_handoff_boundary_for_BRF-001`

### `RBR-001` 区间边界回归

- 吃的机会: Range-boundary reversion vocabulary kept only if materially new edge evidence appears.
- 当前层级 / 决策: `L1` / `park`
- 系统可继续工程化: `false`
- Owner policy action required: `false`
- 主要 gap / 次要 gap: `parked_low_priority_gap` / `replay_quality_gap`
- 下一证据: material_new_edge_evidence
- 不晋级原因: current ledger parks this StrategyGroup until new evidence
- 下一工程 checkpoint: `keep_parked_until_material_new_edge_evidence`

## 权限边界

本波次只服务 StrategyGroup 质量治理，不部署、不下单、不修改实盘配置、不修改杠杆/仓位/订单大小默认值、不创建提现或划转动作。
