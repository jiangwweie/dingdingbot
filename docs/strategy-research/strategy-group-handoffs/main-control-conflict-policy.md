# Main-Control Conflict Policy

Status: HANDOFF_SUPPLEMENT_READY
Last updated: 2026-06-14

## Purpose

This document defines research-side recommendations for resolving conflicts
between StrategyGroup handoff signals.

It does not authorize execution. It only tells main-control how to block,
downshift, or request review before candidate preparation.

## Global Rules

| Conflict Type | Default Rule | Main-Control Meaning |
| --- | --- | --- |
| `same_symbol_long_vs_short` | `block_all_and_require_review` | Do not prepare a candidate until conflict is resolved. |
| `same_symbol_same_direction_duplicate` | `merge_context_and_prepare_one_candidate_only` | Avoid duplicate candidates for the same symbol and side. |
| `armed_vs_observe_only` | `prefer_observe_only_until_facts_pass` | Downshift rather than forcing armed observation. |
| `fresh_signal_vs_stale_context` | `fresh_requires_all_required_facts_pass` | Fresh signal cannot override stale required facts. |
| `strategy_signal_vs_account_conflict` | `block_candidate_prepare` | Same-symbol position/open order blocks candidate prep. |
| `facts_support_signal_but_mark_abnormal` | `block_armed_observation` | Mark/last abnormality blocks perps. |
| `high_leverage_request` | `block_or_downshift_to_research_lane` | 3x/5x cannot be promoted from this batch. |

## Strategy Pair Rules

| Pair | Example | Recommended Rule |
| --- | --- | --- |
| `MPG-001` vs `TEQ-001` | Same symbol long from momentum and TEQ. | Allow observation; merge into one candidate review if same symbol/side. |
| `MPG-001` vs `PMR-001` | Equity/metal long context conflicts with PMR short. | Block same-symbol long/short; require operator review. |
| `TEQ-001` vs `FBS-001` | TEQ long and negative-funding squeeze long. | Allow only if both facts pass; mark as funding-supported TEQ candidate. |
| `TEQ-001` vs `SOR-001` | TEQ long but SOR short exception. | Block same-symbol direction conflict; SOR short exception requires explicit branch review. |
| `PMR-001` vs `SOR-001` | PMR short and SOR PMR short. | Allow merge if both are XAG-led short and session facts pass. |
| `FBS-001` vs `PMR-001` | Funding stress conflicts with metal mark/funding warnings. | Prefer block armed observation until mark/funding facts resolve. |

## Same-Symbol Policy

| Case | Policy |
| --- | --- |
| Same strategy group, same symbol, same side | Keep latest fresh signal if RequiredFacts pass; discard stale duplicate. |
| Different strategy groups, same symbol, same side | Merge context and prepare at most one candidate. |
| Different strategy groups, same symbol, opposite side | Block candidate preparation and require review. |
| Observe-only signal plus armed signal | Downshift to observe-only unless armed signal has all RequiredFacts and no opposing context. |
| Stale signal plus fresh signal | Fresh signal can proceed only if all RequiredFacts pass and stale signal is not an opposing-side warning. |

## Facts Conflict Policy

| Facts Conflict | Policy |
| --- | --- |
| Funding supports long, but mark deviation is abnormal | Block armed observation. |
| Momentum supports long, but FBS marks crowding unsafe | Require operator review or observe-only. |
| Session branch fires, but session mapping is missing | Block SOR candidate preparation. |
| PMR short fires, but role split is mixed | Observe-only. |
| TEQ momentum fires, but concentration is unbounded | Require operator review before candidate preparation. |
| Exchange rules missing for supported symbol | Block candidate preparation. |
| Account position/open order exists on same symbol | Block candidate preparation. |

## Priority In Conflict Resolution

| Priority | Rule |
| ---: | --- |
| `1` | Account and exchange hard stops override every strategy signal. |
| `2` | Stale facts and stale signals cannot prepare candidates. |
| `3` | Opposite-side same-symbol conflicts block all candidates. |
| `4` | Mark/funding abnormalities block armed observation for perps. |
| `5` | Observe-only mode wins over armed mode when facts are incomplete. |
| `6` | Same-side multi-strategy agreement can merge into one review candidate. |

## Strategy-Specific Conflict Notes

### `MPG-001`

`MPG-001` can merge with `TEQ-001` when both are long and same-symbol. It must
not override FBS or mark/funding blockers.

### `FBS-001`

`FBS-001` can support TEQ long candidates when negative funding facts pass. It
can also downshift momentum candidates when funding, mark, or crowding facts are
unsafe.

### `TEQ-001`

`TEQ-001` is long-side only in this batch. Same-symbol TEQ short requests should
route through `SOR-001` exception lanes or be blocked.

### `PMR-001`

`PMR-001` starts observe-only. It should not block unrelated TEQ/MPG equity
signals unless the same symbol or an explicit overlay target relationship is
present.

### `SOR-001`

`SOR-001` is branch-specific and session-specific. It should not override
always-on candidates outside its session window.

## Boundary

Conflict policy is a candidate-preparation policy. It does not decide FinalGate,
Operation Layer submit, budget settlement, reconciliation, or real execution.
