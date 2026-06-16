# P0 Handoff Hardening Matrix

Status: ACTIVE_P0_REVIEW
Last updated: 2026-06-16

## Scope

This matrix reviews the 5 current StrategyGroup handoff packs and translates
their strongest evidence, weakest blockers, and next evidence tasks into a
main-control-readable queue.

It does not promote, deploy, register, or authorize any StrategyGroup.

## Summary

| StrategyGroup | Current Status | Research Interpretation | P0 Verdict |
| --- | --- | --- | --- |
| `MPG-001` | `handoff_ready` | Strongest current right-tail family, but drawdown and late-cycle disable remain unresolved. | Keep as first-batch armed observation candidate with strict disable facts. |
| `FBS-001` | `handoff_ready_facts_heavy` | Funding/crowding squeeze is valuable but fact-heavy. | Keep armed observation only when derivatives facts are fresh; otherwise degrade. |
| `TEQ-001` | `handoff_ready_low_history_blocked` | Short-history equity-like momentum is useful for discovery and observation. | Keep armed observation with low-history and product-availability blockers explicit. |
| `PMR-001` | `observe_only_overlay` | Metal weakness overlay is useful as context/filter, not a broad standalone action group. | Keep observe-only unless role split and fill/session facts improve. |
| `SOR-001` | `conditional_observation` | Session branch can produce right-tail windows but is narrow and decay-prone. | Keep conditional observation with strict branch/session gating. |

## P0 Gap Matrix

| StrategyGroup | Strongest Evidence | Primary Blocker | RequiredFacts Gap | Next Evidence Task |
| --- | --- | --- | --- | --- |
| `MPG-001` | Group-pool momentum persistence and bounded impulse rows preserve high right-tail windows; 12h and 72h horizons have different tradeoffs. | Full-sequence drawdown and late-cycle decay. | `mpg_late_cycle_disable_state`, `mpg_member_drawdown_forensic_state`, `mpg_member_disable_candidate_state`, `mpg_exit_horizon_tradeoff_state`, `fill_gap_slippage_state`, `real_margin_liquidation_model_state`. | Completed `mpg-member-drawdown-disable-addendum-20260616.md`: retrospective member drawdown attribution is separated from prefix-safe disable candidates. |
| `FBS-001` | TEQ negative-funding squeeze lane remains the strongest FBS lead. | Funding settlement, OI/long-short/top-trader facts, and concentration. | `negative_funding_crowding_state`, `funding_settlement_timing_state`, `open_interest_state`, `long_short_ratio_state`, `funding_squeeze_concentration_state`, `real_exchange_margin_liquidation_model`. | Completed `fbs-derivatives-facts-readiness-split-20260616.md`: fresh facts can keep armed observation, partial/stale facts downshift, missing facts block candidate prepare. |
| `TEQ-001` | Binance 2026 equity-like universe supports momentum and relative-strength discovery. | Low history, product availability, session gap, concentration, and real margin. | `expanded_tradfi_universe_manifest_state`, `product_eligibility_state`, `low_history_dataset_state`, `session_gap_context`, `mark_funding_review_state`, `exchange_margin_liquidation_state`. | Completed `teq-current-product-availability-refresh-20260616.md`: current TEQ handoff symbols are not visible in the refreshed USD-S exchangeInfo response, so cached evidence stays research-only until symbol availability is refreshed. |
| `PMR-001` | XAG-led short/weakness and PMR target-specific overlay can disable some continuation labels and support metal context. | Target-specific overlay policy, XAG concentration, external session/settlement, fill, and margin. | `pmr_role_branch_state`, `pmr_target_overlay_policy_state`, `xag_dominance_state`, `commodity_session_gap_state`, `mark_deviation_bound_state`, `real_margin_model_state`. | Completed `pmr-overlay-role-split-20260616.md`: PMR is split into NLPD disable overlay, TEQ support tag, XAG short watchlist, metal context, and blocked standalone branches. |
| `SOR-001` | Opening-range/session-transfer branches preserve narrow right-tail windows. | Second-half decay, branch narrowness, and session/fill ambiguity. | `sor_branch_eligibility_state`, `sor_time_stop_72h_state`, `session_open_range_state`, `post_open_decay_disable_state`, `tradfi_session_mapping_state`, `mark_funding_session_review_state`, `exchange_margin_liquidation_state`. | Completed `sor-branch-eligibility-time-stop-20260616.md`: SOR is split into TEQ short 72h candidate, PMR short support, TEQ long revival-only, PMR long blocked, and broad ORB blocked branches. |

## Admission Guidance For Main Control

| StrategyGroup | Default Display | Observation Mode | Candidate Preparation Guidance |
| --- | --- | --- | --- |
| `MPG-001` | First-batch candidate. | `armed_observation` after RequiredFacts pass. | Prepare candidate only when late-cycle, prefix-safe member disable, exit horizon, and protection facts are present; do not blacklist members from forensic attribution alone. |
| `FBS-001` | First-batch but facts-heavy. | `armed_observation` when derivatives facts are fresh; degrade to observe-only when stale. | Do not prepare without current funding/mark/OI context. |
| `TEQ-001` | First-batch low-history lane. | `armed_observation` with low-history warning. | Do not treat cached 2026 data as current product eligibility. |
| `PMR-001` | Overlay / context. | `observe_only`. | Do not prepare standalone candidates; allow target-specific disable/support annotation only after PMR role branch and target policy facts are explicit. |
| `SOR-001` | Conditional branch. | `conditional_observation`. | Prepare only for named eligible branches with closed range/trigger, 72h time-stop, session, mark/funding, fill, margin, and protection facts. |

## FBS-001 Readiness Split

| State | Meaning | Main-Control Behavior |
| --- | --- | --- |
| `fbs_derivatives_facts_fresh` | Funding, mark, premium/basis, OI, global long-short, top-trader ratio, and symbol rules are current. | Keep `armed_observation` if the fresh signal and all main-control gates pass. |
| `fbs_derivatives_facts_partial` | Funding and mark are current, but OI or crowding ratios are absent or field-shape-only. | Keep observe-only context; block candidate prepare from research semantics alone. |
| `fbs_derivatives_facts_stale` | Funding, mark, OI, or crowding facts are outside the watcher freshness policy. | Emit stale packet and block candidate prepare. |
| `fbs_derivatives_facts_missing` | Primary funding, mark, or exchange symbol facts are missing. | Emit no-signal or facts-missing packet and block candidate prepare. |
| `fbs_margin_model_missing` | Real margin/liquidation model is absent. | Keep 1x default and block leverage promotion. |

## MPG-001 Member Drawdown Disable Split

| State | Meaning | Main-Control Behavior |
| --- | --- | --- |
| `mpg_member_drawdown_forensic_state` | WPR/TSI/Junes/symbol attribution explains historical drawdown after the fact. | Review-only warning; do not blacklist members or symbols. |
| `mpg_member_disable_candidate_state` | A member-level disable hypothesis is present and versioned. | Can be reviewed, but cannot filter until it is prefix-safe and tested. |
| `mpg_member_recent_loss_cluster_state` | Rolling loss cluster from already-known outcomes. | Downshift member only after current realized records support it. |
| `mpg_signal_extension_state` | Signal-time body/prior-return impulse extension. | Block late-cycle candidate prepare when the current closed-candle signal is overextended. |
| `mpg_exit_horizon_tradeoff_state` | Separates 12h cleaner tradeoff from 72h right-tail revival. | Block candidate prepare if horizon is missing or ambiguous. |
| `mpg_high_leverage_disable_state` | 5x disabled and 3x stress-only. | Block leverage promotion. |

## TEQ-001 Current Availability Split

| State | Meaning | Main-Control Behavior |
| --- | --- | --- |
| `teq_current_product_visible` | Research symbol is visible in current exchangeInfo and exchange rules are present. | Allow armed observation only after all other RequiredFacts pass. |
| `teq_cached_research_only` | Research symbol has cached 2026 evidence but is not visible in current exchangeInfo. | Keep in strategy picker/research context; block candidate prepare. |
| `teq_symbol_mapping_unclear` | Cached symbol may have changed or is not directly mappable to a current symbol. | Require mapping review before watcher binding. |
| `teq_low_history_event_only` | bStocks or recent symbols have too little history for promotion. | Event-study observation only. |

## PMR-001 Overlay Role Split

| State | Meaning | Main-Control Behavior |
| --- | --- | --- |
| `pmr_disable_overlay_for_nlpd` | PMR state has historically toxic overlap with `NLPD-001` continuation labels. | Allow observe-only disable/downshift annotation for NLPD; do not emit PMR standalone signal. |
| `pmr_teq_support_tag` | PMR state has positive overlap with TEQ evidence but TEQ remains the primary signal source. | Annotate TEQ context only; do not activate TEQ from PMR alone. |
| `pmr_regular_xag_short_watchlist` | XAG-led regular-session short/weakness branch has right-tail windows but unresolved drawdown. | Observe-only watchlist; no candidate prepare without session, mark, fill, and margin facts. |
| `pmr_metal_dislocation_context` | Metals dislocation describes relative weakness or session mismatch. | Context fact for PMR/MDS; not standalone action. |
| `pmr_standalone_short_blocked` | Broad standalone PMR short promotion remains blocked. | Block candidate prepare. |
| `pmr_broad_long_blocked` | Broad metal-long momentum is negative evidence. | Block long-side metal momentum claims. |

## SOR-001 Branch Eligibility Split

| State | Meaning | Main-Control Behavior |
| --- | --- | --- |
| `sorcls_teq_short_decisive_breakdown_72h` | Narrow TEQ short branch that survived raw-pool reslot with a 72h exit. | Eligible for armed observation only after all RequiredFacts pass. |
| `sor_pmr_us_open_short_72h` | PMR short opening-range breakdown support branch with right-tail windows but decay unresolved. | Conditional observation/support; no broad PMR short promotion. |
| `sor_teq_long_revival_only` | TEQ long ORB has large best windows but negative full sequence. | Keep revival-only; block long candidate prepare. |
| `sor_teq_short_volume_revival_only` | TEQ short volume-confirmed row degraded after raw-pool reslot. | Keep as window revival evidence only. |
| `sor_pmr_long_blocked` | PMR long ORB full sequence is negative. | Block long-side metal session claims. |
| `sor_broad_orb_blocked` | Broad opening-range alpha is not supported. | Block broad SOR candidate prepare. |

## Leverage Boundary

| StrategyGroup | Default | Allowed Research Lane | Disabled / Stress Lane |
| --- | ---: | --- | --- |
| `MPG-001` | `1x` | `2x` for the 12h tradeoff lane after protection facts. | `3x` stress-only, `5x` disabled. |
| `FBS-001` | `1x` | `2x` only after funding, mark, and margin facts. | `5x` disabled. |
| `TEQ-001` | `1x` | `2x` research-only after product and margin facts. | `3x/5x` disabled. |
| `PMR-001` | `1x` | `2x` only as research stress after role split. | `3x/5x` disabled. |
| `SOR-001` | `1x` | `2x` only for named narrow branches. | `3x/5x` disabled. |

## P0 Next Actions

1. Keep `MPG-001` member drawdown disable addendum current after
   `mpg-member-drawdown-disable-addendum-20260616.md`; next evidence task is
   testing prefix-safe member loss-cluster and signal-extension disable facts.
2. Keep `FBS-001` readiness split current after
   `fbs-derivatives-facts-readiness-split-20260616.md`; next evidence task is
   historical OI/ratio capture rather than new runtime logic.
3. Keep `TEQ-001` current-product availability refresh active after
   `teq-current-product-availability-refresh-20260616.md`; do not treat cached
   2026 symbols as current runtime symbols without exchangeInfo visibility.
4. Keep `PMR-001` overlay role split current after
   `pmr-overlay-role-split-20260616.md`; next evidence task is target-specific
   overlay policy testing with current session, fill, mark, and margin facts.
5. Keep `SOR-001` branch eligibility split current after
   `sor-branch-eligibility-time-stop-20260616.md`; next evidence task is
   current session/fill/mark/margin readiness for the TEQ short 72h branch.
