---
title: STRATEGYGROUP_TIER_REVIEW_CURRENT
status: CURRENT
authority: docs/current/strategy-group-handoffs/strategygroup-tier-review-current.json
last_verified: 2026-06-20
---

# StrategyGroup Tier Review Current

## 目的

这份 review 把 StrategyGroup 从“策略资产是什么”推进到“下一步怎么走”。它消费 Registry Baseline、Runtime Tier Policy 和 Decision Ledger，给每个策略组一条当前推进判断。

静态 review 不代表当前可以下单。`actionable_now` 只能由运行时根据新鲜信号、账户、保护、订单和交易所事实判断，因此这里始终为 `false`。

## 总览

| StrategyGroup | 当前层级 | 可试运行 | 当前判断 | 推荐动作 | Owner 需决策 |
| --- | --- | --- | --- | --- | --- |
| `MPG-001` | `L4` | `true` | `preserve_p0_live_lane_waiting_for_market` | `wait_for_live_outcome` | `false` |
| `TEQ-001` | `L2` | `false` | `keep_current_tier_no_promotion_evidence` | `keep` | `false` |
| `FBS-001` | `L3` | `false` | `keep_current_tier_no_promotion_evidence` | `keep` | `false` |
| `SOR-001` | `L3` | `false` | `keep_current_tier_no_promotion_evidence` | `keep` | `false` |
| `PMR-001` | `L1` | `false` | `keep_current_tier_no_promotion_evidence` | `keep` | `false` |
| `BTPC-001` | `L2` | `false` | `revise` | `revise` | `false` |
| `VCB-001` | `L1` | `false` | `keep_observing` | `keep` | `false` |
| `LSR-001` | `L1` | `false` | `keep_observing` | `keep` | `false` |
| `BRF-001` | `L1` | `false` | `keep_observing` | `keep` | `false` |
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
- 当前判断: `preserve_p0_live_lane_waiting_for_market`
- 推荐动作: `wait_for_live_outcome`
- 判断来源: `registry_and_p0_runtime_policy`
- Owner 需决策: `false`
- 下一证据: fresh selected signal plus first allocated-subaccount live outcome
- 暂不晋级原因: already_l4_live_trial_lane; no further tier promotion is needed

### `TEQ-001` 类股权永续动量

- 当前层级: `L2`
- 当前判断: `keep_current_tier_no_promotion_evidence`
- 推荐动作: `keep`
- 判断来源: `registry_and_tier_policy`
- Owner 需决策: `false`
- 下一证据: shadow outcomes and cost/session review before any L4 review
- 暂不晋级原因: strategy uncertainty is not an execution blocker, but there is no current decision evidence for promotion or live scope change; Equity-like perpetual momentum may prepare candidate evidence, but should not compete with the first MPG real-order closure.

### `FBS-001` 资金费率/基差压力

- 当前层级: `L3`
- 当前判断: `keep_current_tier_no_promotion_evidence`
- 推荐动作: `keep`
- 判断来源: `registry_and_tier_policy`
- Owner 需决策: `false`
- 下一证据: derivatives source reliability and cost-survival review
- 暂不晋级原因: strategy uncertainty is not an execution blocker, but there is no current decision evidence for promotion or live scope change; Funding/basis stress remains observable, but requires stricter derivatives facts before any promotion.

### `SOR-001` 开盘区间结构

- 当前层级: `L3`
- 当前判断: `keep_current_tier_no_promotion_evidence`
- 推荐动作: `keep`
- 判断来源: `registry_and_tier_policy`
- Owner 需决策: `false`
- 下一证据: session replay/outcome review before any higher-tier decision
- 暂不晋级原因: strategy uncertainty is not an execution blocker, but there is no current decision evidence for promotion or live scope change; Session-window observer; armed only inside its session/structure conditions.

### `PMR-001` 贵金属制度覆盖

- 当前层级: `L1`
- 当前判断: `keep_current_tier_no_promotion_evidence`
- 推荐动作: `keep`
- 判断来源: `registry_and_tier_policy`
- Owner 需决策: `false`
- 下一证据: role-specific replay and fact maturity before tier review
- 暂不晋级原因: strategy uncertainty is not an execution blocker, but there is no current decision evidence for promotion or live scope change; Precious-metal overlay remains observe-only until role/session/mark facts are consistently ready.

### `BTPC-001` 熊市回抽延续

- 当前层级: `L2`
- 当前判断: `revise`
- 推荐动作: `revise`
- 判断来源: `decision_ledger`
- Owner 需决策: `false`
- 下一证据: feed_btpc_proxy_replay_quality_into_l2_keep_revise_or_fact_source_decision
- 暂不晋级原因: current ledger requires revision before any tier change

### `VCB-001` 波动压缩突破

- 当前层级: `L1`
- 当前判断: `keep_observing`
- 推荐动作: `keep`
- 判断来源: `decision_ledger`
- Owner 需决策: `false`
- 下一证据: tier_review_after_post_revision_quality
- 暂不晋级原因: current ledger supports continued observation, not tier promotion

### `LSR-001` 流动性扫盘/短线复活

- 当前层级: `L1`
- 当前判断: `keep_observing`
- 推荐动作: `keep`
- 判断来源: `decision_ledger`
- Owner 需决策: `false`
- 下一证据: tier_review_after_post_revision_quality
- 暂不晋级原因: current ledger supports continued observation, not tier promotion

### `BRF-001` 熊市反弹失败

- 当前层级: `L1`
- 当前判断: `keep_observing`
- 推荐动作: `keep`
- 判断来源: `decision_ledger`
- Owner 需决策: `false`
- 下一证据: tier_review_after_post_revision_quality
- 暂不晋级原因: current ledger supports continued observation, not tier promotion

### `RBR-001` 区间边界回归

- 当前层级: `L1`
- 当前判断: `park`
- 推荐动作: `park`
- 判断来源: `decision_ledger`
- Owner 需决策: `false`
- 下一证据: material_new_edge_evidence
- 暂不晋级原因: current ledger parks this StrategyGroup until new evidence

## 权限边界

本 review 只服务层级治理和策略学习，不授权下单、不修改实盘配置、不修改杠杆/仓位/订单大小默认值、不创建提现或划转动作。
