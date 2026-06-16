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
| `MPG-001` | Group-pool momentum persistence and bounded impulse rows preserve high right-tail windows; 12h and 72h horizons have different tradeoffs. | Full-sequence drawdown and late-cycle decay. | `mpg_late_cycle_disable_state`, `mpg_member_drawdown_contribution_state`, `mpg_exit_horizon_state`, `fill_gap_slippage_state`, `real_margin_liquidation_model_state`. | Build a member-level drawdown-to-disable table that does not use future attribution as signal input. |
| `FBS-001` | TEQ negative-funding squeeze lane remains the strongest FBS lead. | Funding settlement, OI/long-short/top-trader facts, and concentration. | `negative_funding_crowding_state`, `funding_settlement_timing_state`, `open_interest_state`, `long_short_ratio_state`, `funding_squeeze_concentration_state`, `real_exchange_margin_liquidation_model`. | Completed `fbs-derivatives-facts-readiness-split-20260616.md`: fresh facts can keep armed observation, partial/stale facts downshift, missing facts block candidate prepare. |
| `TEQ-001` | Binance 2026 equity-like universe supports momentum and relative-strength discovery. | Low history, product availability, session gap, concentration, and real margin. | `expanded_tradfi_universe_manifest_state`, `product_eligibility_state`, `low_history_dataset_state`, `session_gap_context`, `mark_funding_review_state`, `exchange_margin_liquidation_state`. | Refresh current exchangeInfo/product availability and map cached symbols to current symbols before further promotion language. |
| `PMR-001` | XAG-led short/weakness and PMR target-specific overlay can disable some continuation labels and support metal context. | Role split, XAG concentration, external session/settlement, fill, and margin. | `xag_dominance_state`, `metal_role_split_state`, `commodity_session_gap_state`, `mark_deviation_bound_state`, `real_margin_model_state`. | Separate PMR into disable-overlay, support-tag, and standalone-short branches. |
| `SOR-001` | Opening-range/session-transfer branches preserve narrow right-tail windows. | Second-half decay, branch narrowness, and session/fill ambiguity. | `session_open_range_state`, `post_open_decay_disable_state`, `time_stop_exit_horizon_state`, `tradfi_session_mapping_state`, `mark_funding_session_review_state`, `exchange_margin_liquidation_state`. | Produce branch eligibility table: TEQ short 72h, PMR short support, long revival-only, and disable branches. |

## Admission Guidance For Main Control

| StrategyGroup | Default Display | Observation Mode | Candidate Preparation Guidance |
| --- | --- | --- | --- |
| `MPG-001` | First-batch candidate. | `armed_observation` after RequiredFacts pass. | Prepare candidate only when late-cycle, member drawdown, exit horizon, and protection facts are present. |
| `FBS-001` | First-batch but facts-heavy. | `armed_observation` when derivatives facts are fresh; degrade to observe-only when stale. | Do not prepare without current funding/mark/OI context. |
| `TEQ-001` | First-batch low-history lane. | `armed_observation` with low-history warning. | Do not treat cached 2026 data as current product eligibility. |
| `PMR-001` | Overlay / context. | `observe_only`. | Prepare only after role split and target-specific overlay behavior is explicit. |
| `SOR-001` | Conditional branch. | `conditional_observation`. | Prepare only for named branches with session and time-stop facts. |

## FBS-001 Readiness Split

| State | Meaning | Main-Control Behavior |
| --- | --- | --- |
| `fbs_derivatives_facts_fresh` | Funding, mark, premium/basis, OI, global long-short, top-trader ratio, and symbol rules are current. | Keep `armed_observation` if the fresh signal and all main-control gates pass. |
| `fbs_derivatives_facts_partial` | Funding and mark are current, but OI or crowding ratios are absent or field-shape-only. | Keep observe-only context; block candidate prepare from research semantics alone. |
| `fbs_derivatives_facts_stale` | Funding, mark, OI, or crowding facts are outside the watcher freshness policy. | Emit stale packet and block candidate prepare. |
| `fbs_derivatives_facts_missing` | Primary funding, mark, or exchange symbol facts are missing. | Emit no-signal or facts-missing packet and block candidate prepare. |
| `fbs_margin_model_missing` | Real margin/liquidation model is absent. | Keep 1x default and block leverage promotion. |

## Leverage Boundary

| StrategyGroup | Default | Allowed Research Lane | Disabled / Stress Lane |
| --- | ---: | --- | --- |
| `MPG-001` | `1x` | `2x` for the 12h tradeoff lane after protection facts. | `3x` stress-only, `5x` disabled. |
| `FBS-001` | `1x` | `2x` only after funding, mark, and margin facts. | `5x` disabled. |
| `TEQ-001` | `1x` | `2x` research-only after product and margin facts. | `3x/5x` disabled. |
| `PMR-001` | `1x` | `2x` only as research stress after role split. | `3x/5x` disabled. |
| `SOR-001` | `1x` | `2x` only for named narrow branches. | `3x/5x` disabled. |

## P0 Next Actions

1. Add a small P0 evidence addendum for `MPG-001` that maps member drawdown
   attribution to disable candidates without turning retrospective attribution
   into an entry signal.
2. Keep `FBS-001` readiness split current after
   `fbs-derivatives-facts-readiness-split-20260616.md`; next evidence task is
   historical OI/ratio capture rather than new runtime logic.
3. Add a `TEQ-001` current-product availability refresh task before any further
   right-tail interpretation.
4. Add a `PMR-001` overlay role split between disable, support, and standalone
   branches.
5. Add a `SOR-001` branch table for session eligibility and time-stop behavior.
