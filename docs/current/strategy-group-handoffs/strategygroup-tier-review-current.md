---
title: STRATEGYGROUP_TIER_REVIEW_CURRENT
status: CURRENT
authority: docs/current/strategy-group-handoffs/strategygroup-tier-review-current.json
last_verified: 2026-06-20
---

# StrategyGroup Tier Review Current

## 目的

这份 review 把 StrategyGroup 从“策略资产是什么”推进到“下一步怎么走”。它消费 Registry Baseline、Runtime Tier Policy 和 Strategy Asset State，给每个策略组一条当前推进判断。

静态 review 不输出行级可下单字段。当前是否可以下单只能由运行时安全门根据新鲜信号、账户、保护、订单和交易所事实判断。

## 总览

| StrategyGroup | 当前层级 | 可试运行 | 当前判断 | 推荐策略检查点 | Owner 政策需求 |
| --- | --- | --- | --- | --- | --- |
| `MPG-001` | `L4` | `true` | `keep_observing` | `keep` | `false` |
| `TEQ-001` | `L2` | `false` | `keep_current_tier_no_promotion_evidence` | `keep` | `false` |
| `FBS-001` | `L3` | `false` | `keep_observing` | `keep` | `false` |
| `SOR-001` | `L3` | `false` | `keep_observing` | `keep` | `false` |
| `PMR-001` | `L1` | `false` | `keep_current_tier_no_promotion_evidence` | `keep` | `false` |
| `BTPC-001` | `L2` | `false` | `revise` | `revise` | `false` |
| `VCB-001` | `L1` | `false` | `keep_observing` | `keep` | `false` |
| `LSR-001` | `L1` | `false` | `revise` | `revise` | `false` |
| `BRF-001` | `L1` | `false` | `promote_review_only` | `promote_review_only` | `false` |
| `RBR-001` | `L1` | `false` | `park` | `park` | `false` |

## Owner 读法

- `wait_for_live_outcome`: 保持 P0 实盘链路待命，等待真实市场机会和后续结果。
- `keep`: 维持当前层级继续观察，不晋级。
- `revise`: 先修 facts / classifier / replay 证据，再谈层级变化。
- `park`: 暂停主动推进，除非出现新证据。
- `do_not_go_live`: 当前不进入实盘，缺少足够证据或政策基础。
- 策略不确定性不是执行安全 blocker；它只影响 revise、tier、观察或 Owner 风险接受路径。

## 分组判断

### `MPG-001` 动量延续

- 当前层级: `L4`
- 当前判断: `keep_observing`
- 晋级范围: `not_applicable`
- 晋级目标: `not_applicable`
- 推荐策略检查点: `keep`
- 判断来源: `None`
- Owner 政策需求: `false`
- 下一证据: no_action_visibility_and_routing_summary:MPG-001_no_action_visibility_and_routing_audit
- 暂不晋级原因: current Strategy Asset State supports continued observation, not tier promotion

### `TEQ-001` 类股权永续动量

- 当前层级: `L2`
- 当前判断: `keep_current_tier_no_promotion_evidence`
- 晋级范围: `not_applicable`
- 晋级目标: `not_applicable`
- 推荐策略检查点: `keep`
- 判断来源: `None`
- Owner 政策需求: `false`
- 下一证据: shadow outcomes and cost/session review before any L4 review
- 暂不晋级原因: strategy uncertainty is not an execution blocker, but there is no current decision evidence for promotion or live scope change; Equity-like perpetual momentum may prepare candidate evidence, but should not compete with the first MPG real-order closure.

### `FBS-001` 资金费率/基差压力

- 当前层级: `L3`
- 当前判断: `keep_observing`
- 晋级范围: `not_applicable`
- 晋级目标: `not_applicable`
- 推荐策略检查点: `keep`
- 判断来源: `None`
- Owner 政策需求: `false`
- 下一证据: no_action_visibility_and_routing_summary:FBS-001_no_action_visibility_and_routing_audit
- 暂不晋级原因: current Strategy Asset State supports continued observation, not tier promotion

### `SOR-001` 开盘区间结构

- 当前层级: `L3`
- 当前判断: `keep_observing`
- 晋级范围: `not_applicable`
- 晋级目标: `not_applicable`
- 推荐策略检查点: `keep`
- 判断来源: `None`
- Owner 政策需求: `false`
- 下一证据: no_action_visibility_and_routing_summary:SOR-001_no_action_visibility_and_routing_audit
- 暂不晋级原因: current Strategy Asset State supports continued observation, not tier promotion

### `PMR-001` 贵金属制度覆盖

- 当前层级: `L1`
- 当前判断: `keep_current_tier_no_promotion_evidence`
- 晋级范围: `not_applicable`
- 晋级目标: `not_applicable`
- 推荐策略检查点: `keep`
- 判断来源: `None`
- Owner 政策需求: `false`
- 下一证据: role-specific replay and fact maturity before tier review
- 暂不晋级原因: strategy uncertainty is not an execution blocker, but there is no current decision evidence for promotion or live scope change; Precious-metal overlay remains observe-only until role/session/mark facts are consistently ready.

### `BTPC-001` 熊市回抽延续

- 当前层级: `L2`
- 当前判断: `revise`
- 晋级范围: `not_applicable`
- 晋级目标: `not_applicable`
- 推荐策略检查点: `revise`
- 判断来源: `None`
- Owner 政策需求: `false`
- 下一证据: classifier_fact_source_revision_review:BTPC-001_classifier_fact_source_revision_review
- 暂不晋级原因: current Strategy Asset State requires revision before any tier change

### `VCB-001` 波动压缩突破

- 当前层级: `L1`
- 当前判断: `keep_observing`
- 晋级范围: `not_applicable`
- 晋级目标: `not_applicable`
- 推荐策略检查点: `keep`
- 判断来源: `None`
- Owner 政策需求: `false`
- 下一证据: VCB-001_continue_observe_only
- 暂不晋级原因: current Strategy Asset State supports continued observation, not tier promotion

### `LSR-001` 流动性扫盘/短线复活

- 当前层级: `L1`
- 当前判断: `revise`
- 晋级范围: `not_applicable`
- 晋级目标: `not_applicable`
- 推荐策略检查点: `revise`
- 判断来源: `None`
- Owner 政策需求: `false`
- 下一证据: classifier_fact_source_revision_review:LSR-001_classifier_fact_source_revision_review
- 暂不晋级原因: current Strategy Asset State requires revision before any tier change

### `BRF-001` 熊市反弹失败

- 当前层级: `L1`
- 当前判断: `promote_review_only`
- 晋级范围: `review_only`
- 晋级目标: `promotion_evidence_review_only`
- 推荐策略检查点: `promote_review_only`
- 判断来源: `None`
- Owner 政策需求: `false`
- 下一证据: promotion_evidence_review_only:BRF-001_forward_outcome_and_requiredfacts_review
- 暂不晋级原因: current Strategy Asset State does not provide live-scope authority

### `RBR-001` 区间边界回归

- 当前层级: `L1`
- 当前判断: `park`
- 晋级范围: `not_applicable`
- 晋级目标: `not_applicable`
- 推荐策略检查点: `park`
- 判断来源: `None`
- Owner 政策需求: `false`
- 下一证据: material_new_edge_evidence_before_reactivation
- 暂不晋级原因: current Strategy Asset State parks this StrategyGroup until new evidence

## 权限边界

本 review 只服务层级治理和策略学习，不授权下单、不修改实盘配置、不修改杠杆/仓位/订单大小默认值、不创建提现或划转动作。
