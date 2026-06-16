# SOR-001 Branch Eligibility And Time-Stop Split

Status: P0_HANDOFF_SUPPLEMENT_READY
Last updated: 2026-06-16

## Scope

This document turns `SOR-001` from a broad opening-range idea into explicit
branch-level observation semantics for main-control intake.

It is research-only. It does not register runtime behavior, authorize orders,
change risk sizing, modify FinalGate, touch Operation Layer, or request deploy.

## Known Objective

`SOR-001` should be observed branch-by-branch. The current evidence does not
support treating all opening-range breakouts as one alpha family.

The useful posture is:

1. Keep PMR short 72h as observe/conditional support.
2. Keep TEQ decisive-breakdown short 72h as the narrowest armed-observation
   candidate branch after RequiredFacts pass.
3. Keep TEQ long as revival-only despite large best windows.
4. Block PMR long and broad metal long.
5. Treat 3x/5x as stress vocabulary, not promotion evidence.

## Branch Eligibility Table

| SOR Branch | Side | Horizon | Evidence Basis | Eligibility |
| --- | --- | ---: | --- | --- |
| `sor_pmr_us_open_short_72h` | `short` | `72h` | Full 2x `33.825028%`, best-90d 2x `126.853890%`, `0` 2x/5x liquidation-proxy events in the base replay. | `conditional_observation_support` |
| `sorcls_pmr_short_prior_weakness_72h` | `short` | `72h` | Full 2x about `77.200972%`, best-90d 2x about `117.597324%`, but second-half 2x negative. | `conditional_observation_support_decay_unresolved` |
| `sorcls_teq_short_decisive_breakdown_72h` | `short` | `72h` | Reslot row: accepted `57`, full 2x `1.999826%`, second-half 2x `6.842896%`, best-90d 2x `119.963254%`, `0` 2x liquidation-proxy events, `2` 5x liquidation-proxy events. | `narrow_armed_observation_candidate_after_facts` |
| `sorcls_teq_short_volume_confirmed_72h` | `short` | `72h` | Reslot full 2x `-21.654537%` despite best-90d 2x `201.714413%`. | `window_revival_only` |
| `sor_teq_us_open_long_48h` | `long` | `48h` | Best-window evidence exists, but full 2x `-97.636922%`. | `revival_only` |
| `sorcls_teq_long_volume_confirmed_72h` | `long` | `72h` | Best-90d remains high after reslot, but full 2x `-36.122176%` and 5x proxy risk appears. | `revival_only` |
| `sor_pmr_us_open_long_72h` | `long` | `72h` | Full 2x `-65.533119%`. | `blocked_negative_evidence` |
| `sor_broad_opening_range` | `both` | `any` | No broad ORB evidence clears full-sequence, decay, and RequiredFacts gates. | `blocked_no_broad_alpha` |

## Time-Stop Semantics

| State | Meaning | Main-Control Behavior |
| --- | --- | --- |
| `sor_time_stop_72h_required` | Current useful SOR short branches are 72h-specific. | Block candidate prepare if the signal lacks a versioned 72h exit plan. |
| `sor_shorter_exit_tradeoff_state` | Shorter exits can reduce decay but may lose right-tail payoff. | Keep as review note; do not auto-reslot. |
| `sor_reslot_capacity_state` | Raw-pool reslot changes accepted events and capital rejects. | Require reslot evidence before promotion claims. |
| `sor_high_leverage_proxy_risk_state` | 5x proxy risk appears in TEQ short 72h candidates. | Keep 3x/5x stress-only and disabled for promotion. |

## RequiredFacts Deltas

| RequiredFact | Meaning | Missing Behavior |
| --- | --- | --- |
| `sor_branch_eligibility_state` | Names the exact SOR branch, side, and promotion class. | `block_candidate_prepare` |
| `sor_time_stop_72h_state` | Confirms the branch is using the tested 72h time stop. | `block_candidate_prepare` |
| `sor_teq_short_decisive_breakdown_state` | TEQ short decisive-breakdown branch classifier. | `no_signal` |
| `sor_teq_short_volume_downgrade_state` | Explicit downgrade for the volume-confirmed short branch after raw-pool reslot. | `revival_only` |
| `sor_teq_long_revival_state` | Explicit revival-only status for TEQ long ORB. | `block_long_candidate_prepare` |
| `sor_pmr_short_decay_state` | PMR short second-half decay and post-open decay context. | `conditional_observation_only` |
| `sor_broad_orb_block_state` | Blocks broad opening-range alpha claims. | `block_broad_sor_candidate` |
| `sor_5x_proxy_risk_state` | High-leverage proxy liquidation risk. | `block_leverage_promotion` |

## Sample Branch Packet

```json
{
  "strategy_group_id": "SOR-001",
  "version": "2026-06-16-branch-split-r0",
  "status": "branch_observation_candidate",
  "symbol": "MUUSDT",
  "direction": "short",
  "branch": "sorcls_teq_short_decisive_breakdown_72h",
  "exit_horizon": "72h",
  "freshness_window_seconds": 120,
  "required_facts_state": {
    "session_open_range_state": "present",
    "session_breakout_trigger_state": "present",
    "sor_branch_eligibility_state": "narrow_armed_observation_candidate_after_facts",
    "sor_time_stop_72h_state": "present",
    "tradfi_session_mapping_state": "required_before_candidate",
    "mark_funding_session_review_state": "required_before_candidate",
    "exchange_margin_liquidation_state": "required_before_candidate"
  },
  "main_control_hint": "candidate_prepare_requires_all_runtime_facts",
  "reason": "SOR TEQ decisive-breakdown short is the narrow 72h branch that survived raw-pool reslot, but high-leverage and session/fill facts still constrain promotion."
}
```

## Research Conclusion

`SOR-001` remains worth keeping because it encodes session structure that can
find narrow right-tail windows. Its correct handoff posture is:

```text
observe named SOR branches
require closed open range and closed trigger
require explicit 72h time stop for current short leads
keep TEQ long revival-only
keep PMR short conditional
block broad ORB promotion
block 3x/5x promotion
```

This gives main control a usable branch table without inflating a narrow
session edge into a broad always-on strategy.
