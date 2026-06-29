# StrategyGroup Owner Policy Package

## Summary

- Status: `owner_policy_package_incomplete`
- Closed problem: Strategy observations are now converted into Owner-ready policy items with default recommendations, counterevidence, risks, and next system actions.
- Capability unlocked: Owner can confirm strategy policy direction without reading raw would_enter/no_action rows or replay evidence.
- Next bottleneck: Owner policy confirmation is required before promote, park, kill, registry admission, tier policy, member live scope, or live-profile changes.
- Live permission change: `false`

## Strategy Quality Snapshot

| StrategyGroup | Owner state | System found | Next step | Policy ready |
| --- | --- | --- | --- | --- |
| `MPG-001` | 等待机会 | P0 selected lane has no executable fresh signal; member review is active. | `MPG-001_no_action_visibility_and_routing_audit` | `true` |
| `BRF-001` | 等待机会 | observed 7 would_enter events | `BRF-001_forward_outcome_and_requiredfacts_review` | `true` |
| `BTPC-001` | 待调整 | observed 155 missed no_action forward positives | `BTPC-001_classifier_fact_source_revision_review` | `true` |
| `LSR-001` | 待调整 | observed 2 would_enter events | `LSR-001_classifier_fact_source_revision_review` | `true` |
| `MI-001` | 身份待定 | observed 17 would_enter events | `MI-001_registry_identity_review` | `true` |
| `CPM-RO-001` | 身份待定 | observed 18 would_enter events | `CPM-RO-001_registry_identity_review` | `true` |
| `RBR-001` | 已暂停 | observed 9 would_enter events | `park_until_material_new_edge_evidence` | `false` |
| `VCB-001` | 等待机会 | observed 2 would_enter events | `VCB-001_continue_observe_only` | `false` |

## Closure Tracks

| Track | Status | Policy item | Default recommendation |
| --- | --- | --- | --- |
| `signal-observation-A` Strategy Quality Snapshot | `ready` | `-` | `-` |
| `signal-observation-B` BRF squeeze / RequiredFacts / forward outcome review | `ready_for_owner_policy` | `BRF-001:owner_policy_choice` | `approve_promote_review_without_live_scope_change` |
| `signal-observation-C` BTPC stale / fact-source / classifier attribution closure | `ready_for_owner_policy` | `BTPC-001:owner_policy_choice` | `keep_l2_shadow_and_revise_fact_classifier_inputs` |
| `signal-observation-D` LSR side-specific rewrite evidence closure | `ready_for_owner_policy` | `LSR-001:owner_policy_choice` | `formalize_short_revival_rewrite_without_live_scope_change` |
| `signal-observation-E` MI-001 identity review | `ready_for_owner_policy` | `MI-001:owner_policy_choice` | `open_formal_candidate_review_and_overlap_check` |
| `signal-observation-F` CPM-RO-001 identity review | `ready_for_owner_policy` | `CPM-RO-001:owner_policy_choice` | `keep_as_observation_asset_and_run_merge_review` |
| `signal-observation-G` MPG member role / exit-decay / risk boundary review | `ready_for_owner_policy` | `MPG-001:member_policy_decision` | `approve_member_role_split_without_live_scope_expansion` |

## Owner Policy Items

| Policy item | Question | Default | Evidence for | Evidence against |
| --- | --- | --- | --- | --- |
| `BRF-001:owner_policy_choice` | 是否允许 BRF-001 进入下一层 promote review，而不是直接进入实盘。 | `approve_promote_review_without_live_scope_change` | would_enter observed: 7<br>missed no_action forward positives: 134<br>BRF replay sample count: 5 | latest would_enter forward outcome is still pending<br>squeeze-risk replay sample recommends revise before promotion<br>RequiredFacts review is not a live-authority artifact |
| `BTPC-001:owner_policy_choice` | 是否保持 BTPC-001 为 L2 shadow，并继续修 fact-source 与 classifier，而不是放松 stale gate 或停车。 | `keep_l2_shadow_and_revise_fact_classifier_inputs` | high-priority stale-blocked no_action count: 169<br>missed no_action forward positives: 155<br>proxy reviewable would_enter count: 0<br>classifier rule review count: 2 | live RequiredFacts gaps remain: 8<br>source attachments pending: 8<br>relaxing stale gate now would be a policy and safety risk |
| `LSR-001:owner_policy_choice` | 是否把 LSR-001 的 short-revival 语义正式化为复核方向，并保持 observe-only。 | `formalize_short_revival_rewrite_without_live_scope_change` | would_enter observed: 2<br>would_enter forward positives: 2<br>LSR replay sample count: 5 | sample size is small<br>long preview and short-revival semantics still conflict<br>range-context RequiredFacts are not yet formal live authority |
| `MI-001:owner_policy_choice` | MI-001 应作为正式候选、MPG 子能力、观察资产，还是停车。 | `open_formal_candidate_review_and_overlap_check` | would_enter observed: 17<br>would_enter forward positives: 12<br>forward positive ratio: 12/17 | strategy identity is not in current registry<br>overlap with MPG / TEQ is not yet resolved<br>symbol concentration and semantic explanation still need review |
| `CPM-RO-001:owner_policy_choice` | CPM-RO-001 应独立、合并、作为观察资产，还是停车。 | `keep_as_observation_asset_and_run_merge_review` | would_enter observed: 18<br>would_enter forward positives: 13<br>forward positive ratio: 13/18 | strategy identity is not in current registry<br>forward quality is mixed relative to MI<br>merge target across CPM/RBR/momentum family is unresolved |
| `MPG-001:member_policy_decision` | 是否接受 MPG member 角色拆分与 exit/decay 复核方向，且不扩实盘范围。 | `approve_member_role_split_without_live_scope_expansion` | MPG replay sample count: 0<br>six member roles are present in the quality closure wave<br>exit horizons and decay controls are present before any live expansion | current package does not prove which member should receive live scope<br>member-level evidence remains review-only and not action-time live facts |

## Policy Options

### BRF-001:owner_policy_choice

- Owner summary: BRF 已看到熊市反弹失败 short 结构，但 squeeze 与 RequiredFacts 仍要先复核。
- Why not live: registry-baseline rows are strategy assets only and cannot authorize execution

| Option | Meaning | Tradeoff |
| --- | --- | --- |
| `approve_promote_review` 进入晋级复核 | 允许系统继续做 squeeze、RequiredFacts、forward outcome 复核。 | 不会增加实盘权限，但会把 BRF 放入更高优先级策略治理。 |
| `keep_l1_observe` 继续 L1 观察 | 保留 BRF 观察，不进入下一层晋级复核。 | 降低误升风险，但可能继续错过 bear-rally failure 结构学习。 |
| `park_until_squeeze_review` 暂缓 | 先不推进 BRF，除非 squeeze 风险材料更清楚。 | 最保守，但会延后 BRF 捕获质量闭合。 |

### BTPC-001:owner_policy_choice

- Owner summary: BTPC 不是简单没机会，而是 stale/fact-source/classifier 阻断过强，当前适合保持 L2 shadow 并修输入。
- Why not live: registry-baseline rows are strategy assets only and cannot authorize execution

| Option | Meaning | Tradeoff |
| --- | --- | --- |
| `keep_l2_shadow_revise` 保持 L2 并修输入 | 继续 L2 shadow，不改实盘权限，补事实源与分类器归因。 | 保留右尾学习机会，但需要继续投入事实源修复。 |
| `wait_fact_source` 等事实源 | 不做策略方向判断，先等 live derivatives / margin 事实源接完。 | 证据更稳，但当前 169 次 stale 误杀无法快速收敛。 |
| `relax_gate_after_false_positive_review` 有条件放松 | 只在 false-positive 风险复核完成后讨论 stale gate 放松。 | 可能提高捕获率，但不能在当前包内直接落地。 |
| `park_btpc` 停车 | 停止 BTPC 近期推进。 | 减少治理复杂度，但放弃当前最多的 missed no-action 正向窗口。 |

### LSR-001:owner_policy_choice

- Owner summary: LSR 有 2 个 would_enter 且 forward outcome 为正，适合继续做 side-specific rewrite。
- Why not live: registry-baseline rows are strategy assets only and cannot authorize execution

| Option | Meaning | Tradeoff |
| --- | --- | --- |
| `formalize_short_revival` 正式化 short-revival | 把 short-revival 作为 LSR 下一轮主复核语义。 | 可捕获已出现的正向窗口，但要解决 long/short 语义冲突。 |
| `keep_observe` 继续观察 | 不正式化 rewrite，只保留 L1 观察。 | 安全但会延迟 LSR 捕获质量闭合。 |
| `park_lsr` 停车 | 暂停 LSR 复核。 | 减少维护，但放弃已有正向样本。 |

### MI-001:owner_policy_choice

- Owner summary: MI-001 的 would_enter 和 forward positive 很强，不能继续只当 smoke lane。
- Why not live: strategy-asset-state evidence is review-only and cannot authorize execution

| Option | Meaning | Tradeoff |
| --- | --- | --- |
| `formal_candidate_review` 正式候选复核 | 进入策略柜候选复核，但不进入实盘。 | 最大化学习价值，但需要补语义、重叠和集中度证据。 |
| `mpg_support_capability` MPG 子能力 | 作为 MPG 的动量冲击 member/scorer 复核。 | 减少独立策略复杂度，但可能掩盖 MI 自身 edge。 |
| `observe_asset` 观察资产 | 保留信号观察，不进入正式候选。 | 治理轻，但强样本无法进入主学习闭环。 |
| `park` 停车 | 认为语义不足或过拟合风险高，暂不推进。 | 最保守，但与当前 23/22 正向证据冲突。 |

### CPM-RO-001:owner_policy_choice

- Owner summary: CPM-RO 有 would_enter 与正向 outcome，但质量混杂且注册身份不清。
- Why not live: strategy-asset-state evidence is review-only and cannot authorize execution

| Option | Meaning | Tradeoff |
| --- | --- | --- |
| `independent_strategy_review` 独立策略复核 | 作为独立策略组候选继续做 handoff / RequiredFacts。 | 可能保留新 edge，但会增加策略柜复杂度。 |
| `merge_into_existing_family` 合并 | 合并进 CPM/RBR/momentum 相关家族。 | 治理更简洁，但需要确认不会损失独立语义。 |
| `observe_asset` 观察资产 | 保留观察，不进入正式候选。 | 适合当前 13/18 的混杂质量。 |
| `park` 停车 | 暂不推进，除非后续 forward quality 改善。 | 减少噪声，但可能错过中等质量机会。 |

### MPG-001:member_policy_decision

- Owner summary: MPG 主线仍等 fresh signal，但 member 风险差异已经足够进入政策复核。
- Why not live: MPG member review is policy evidence only and cannot expand L4 live scope

| Option | Meaning | Tradeoff |
| --- | --- | --- |
| `approve_member_role_split` 接受 member 角色拆分 | 按 TSI/MHI/PPO/DMI/WPR/MFI 的默认角色继续复核。 | 能降低 MPG 黑盒风险，但仍不授权任何 member 实盘扩围。 |
| `keep_mpg_as_single_l4_box` 保持 MPG 单一黑盒 | 暂不拆 member 角色。 | 治理简单，但无法解释收益强与回撤重的来源。 |
| `freeze_member_review` 冻结 member 复核 | 暂不推进 MPG member 层。 | 避免过度治理，但会保留当前 member 风险不透明问题。 |

| Member | Default recommendation | Live scope now |
| --- | --- | --- |
| `TSI-001` 保留核心候选 | `keep_core_candidate_with_decay_control` | `false` |
| `MHI-001` 降权或停车复核 | `downshift_or_park_before_live_expansion` | `false` |
| `PPO-001` 保留支持 member | `keep_support_member` | `false` |
| `DMI-001` 身份边界复核 | `resolve_member_vs_independent_identity` | `false` |
| `WPR-001` 保留确认器 | `keep_confirmation_member` | `false` |
| `MFI-001` 保留为 scorer / risk damper | `keep_scorer_not_primary` | `false` |

## Owner Confirmation Boundary

- Owner policy confirmation required: `true`
- Runtime Owner intervention required: `false`
- Owner policy policy_item count: `6`
- Hard stop: Do not promote, park, kill, change registry authority, change tier policy, change live profile, expand MPG member live scope, or expand real-order scope without Owner confirmation.

## Safety

| Field | Value |
| --- | --- |
| `local_review_only` | `true` |
| `server_interaction` | `false` |
| `server_files_mutated` | `false` |
| `strategy_parameters_changed` | `false` |
| `registry_authority_changed` | `false` |
| `tier_policy_changed` | `false` |
| `live_profile_changed` | `false` |
| `mpg_member_live_scope_expanded` | `false` |
| `l4_real_order_scope_expanded` | `false` |
| `shadow_candidate_created` | `false` |
| `final_gate_called` | `false` |
| `operation_layer_called` | `false` |
| `order_created` | `false` |
| `exchange_write_called` | `false` |
| `preview_or_replay_treated_as_live_signal` | `false` |
| `runtime_started` | `false` |

## Output

- JSON: `output/runtime-monitor/latest-strategygroup-owner-policy-package.json`
- Markdown: `output/runtime-monitor/latest-strategygroup-owner-policy-package.md`
