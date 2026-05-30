# Strategy Group Shelf Result

## 1. Summary

Owner Console 已从单一 MI-001 SOL 候选视角扩展为策略组货架 / 策略组选择器视角。Owner 现在可以在 `/strategy-groups` 看到当前主链路、强候选、备用候选、Owner 特批观察线、research pool 和 Tier 1 数据族。

本次只实现只读展示与前端 view-model 聚合，不启动 trial，不创建 execution intent，不下单，不修改 execution permission。

## 2. Path Chosen

Path C：在现有 Owner Console 前端页面直接新增 Strategy Group Shelf section。

原因：
- 现有 PG / report / console readiness 已足够支持 Owner-readable 货架视图。
- 当前任务目标是 Owner 可见策略组地图，不需要修改 PG schema。
- 状态枚举先在 UI view-model 层映射，不强行改变后端 enum。
- 不新增交易、runtime、order 或 permission 能力。

## 3. Strategy Group Shelf

| strategy_group_id | strategy_group_name | representative_candidates | current_status | evidence_summary | key_risks | next_recommended_action |
| --- | --- | --- | --- | --- | --- | --- |
| MI-001 | Momentum Impulse | MI-001 SOL long; MI-001 BNB long | primary_chain_candidate / strong_smoke_candidate | SOL 是当前主链路；BNB broad smoke 数字强，历史覆盖短只是 confidence flag，不是淘汰理由。 | 高波动、MAE 大、右尾依赖、动量耗尽、BNB 覆盖期较短 | 继续完成 MI-001 SOL Owner 控制台验收；BNB 保留为强 smoke 备选。 |
| VI-001 | Volume Impulse | VI-001 ETH long | backup_trial_candidate | ETH long broad smoke positive，延续性相对 SOL 更温和。 | volume spike chasing、成交量质量未知、缺 taker/OI/funding 确认 | 保留为 backup trial candidate，不进入当前主链路。 |
| CPM-RO-001 | Owner Special Observation | CPM read-only observation | owner_special_observation | CPM historical OOS 2021/2022 negative；不作为 proven alpha。Owner 认为其较温和，适合当前市场 validation 和 bounded review。 | 2021/2022 OOS negative、不是 proven alpha、适用边界未验证、不能自动 runtime eligible | 建立只读观察记录，不自动提升为 runtime eligible。 |
| TB | Trend Breakout | TB-001; TB-002 | research_pool / keep_for_later | TB-002 BNB broad smoke rank #2；SOL/ETH 也有正向参考。 | false breakout、late entry、BNB coverage comparability、缺成本/滑点/资金费率确认 | keep_for_later，等待 MI/VI 路径决策后再复盘。 |
| PC | Pullback Continuation | PC-001; PC-002 | research_pool | PC-002 SOL rank #8；保留 pullback-continuation family，不重新打开 CPM rescue。 | 泛化成 long-beta continuation、MAE 大、入场时点模糊、可能与 CPM 问题重叠 | parked in research_pool，不做 trial。 |
| VB | Volatility Breakout | VB-001 | research_pool | Broad smoke 有正向 long rows，但排名低于 MI/VI/TB 参考线。 | 追在扩张尾部、缺 volatility-quality filter、缺 funding/OI/cost replay | keep_for_later，当前不新增变体。 |
| MR/RB | Mean Reversion / Range Boundary | MR-001; RB-001 | weak_or_secondary / needs better variant | RB-001 SOL/ETH 有次级正向行；MR 当前没有 trial candidate，需要更好的变体假设。 | 逆趋势接刀、边界质量差、adverse path risk、short rows broadly weak | parked until better variant is proposed。 |
| Tier1-Data-Families | Tier 1 Data Families | Funding; OI; Taker flow; Long-short ratio; Basis / premium; Attention / search | data_request_ready / not downloaded / not admitted | Tier 1 数据请求已准备；未下载，未入库，未 admission。 | provider semantics、timestamp alignment、lookahead、normalization/revision risk | 等待 Owner 单独确认是否下载 Tier 1 数据。 |

## 4. Implemented Changes

- 新增 Owner Console `/strategy-groups` 策略组货架卡片区。
- 新增策略组详情选择器，展示 Owner-facing 字段：
  - strategy_group_id
  - strategy_group_name
  - plain_language_summary
  - market_regime_it_eats
  - market_regime_it_hates
  - representative_candidates
  - current_status
  - evidence_summary
  - key_risks
  - owner_action_options
  - next_recommended_action
  - not_allowed_now
- 新增策略组列表表格，便于 Owner 横向比较。
- 前端测试覆盖 MI-001 SOL、MI-001 BNB、VI-001 ETH、CPM 特批观察、research pool、Tier 1 data families。

## 5. Owner Console Flow

Owner 登录后进入 `/strategy-groups`：
1. 先看策略组货架，确认当前有哪些策略组。
2. 点击任一策略组卡片查看它吃什么行情、怕什么行情、证据摘要、风险和下一步。
3. 通过策略组列表快速横向比较主链路、强候选、备用候选和 research pool。
4. MI-001 SOL 仍是当前主链路候选。
5. MI-001 BNB 是强 smoke 候选，历史覆盖短仅作为 confidence flag。
6. CPM-RO-001 仅用于 Owner special observation / market validation / bounded review，不作为 proven alpha。

## 6. Safety Check

- 没有启动 trial。
- 没有创建 execution intent。
- 没有创建 order。
- 没有启动 runtime。
- 没有修改 execution permission 语义。
- 没有修改 leverage、transfer、withdraw、flatten、cancel order 路径。
- 没有修改 exchange gateway、execution orchestrator、order lifecycle、live runner。
- UI 文案明确：策略组货架是观察与复盘入口，不是自动选择策略，也不是交易入口。

## 7. Next Recommended Task

Owner 手工验收 `/strategy-groups` 策略组货架，并确认是否为 CPM-RO-001 建立只读 observation evidence packet。
