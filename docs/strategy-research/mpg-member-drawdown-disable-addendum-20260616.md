# MPG-001 Member Drawdown Disable Addendum

Status: P0_HANDOFF_SUPPLEMENT_READY
Last updated: 2026-06-16

## Scope

This document converts `MPG-001` drawdown attribution into a prefix-safe
disable-fact design.

It is research-only. It does not register runtime behavior, authorize orders,
change risk sizing, modify FinalGate, touch Operation Layer, or request deploy.

## Known Objective

`MPG-001` is the strongest current right-tail StrategyGroup family, but it
remains drawdown-blocked. The goal is not to delete the losing members after
seeing outcomes. The goal is to record which facts are retrospective forensics
and which can become signal-time disable or downshift facts.

## Evidence Base

| Evidence Item | Result | Research Meaning |
| --- | --- | --- |
| `mpg_lcd_body_le_1p5` | Full 2x `337.940592%`, best-90d 2x `1433.147820%`, max DD 2x `-75.753763%`. | Strong right-tail candidate, still drawdown-blocked. |
| `mpg_bounded_impulse` `72h` | Full 2x `353.763739%`, best-90d 2x `1204.646317%`, DD 2x `-79.542358%`. | Largest right-tail lane; promotion blocked by drawdown. |
| `mpg_equity_regular_proxy` `12h` | Full 2x `20.247817%`, best-90d 2x `163.583761%`, DD 2x `-56.620905%`, `0` 2x/5x proxy liquidation events. | Cleaner tradeoff lane; lower return, not broad promotion evidence. |
| Max-DD phase | `2026-06-04T16:00:00Z` to `2026-06-12T20:00:00Z` for `mpg_lcd_body_le_1p5`. | Retrospective phase fact, not a future signal. |
| Max-DD member drag | `WPR-001` phase sum 2x `-65.423048%`; `TSI-001` phase sum 2x `-34.759354%`. | Member attribution for future disable design, not immediate blacklist. |
| Worst event | `WPR-001` / `WDCUSDT` event 2x `-31.232806%`. | Loss-event forensic fact, not symbol blacklist. |

## Forensic Versus Signal-Time Split

| Fact Type | Examples | Allowed Use | Forbidden Use |
| --- | --- | --- | --- |
| `forensic_only` | Worst month, max-DD phase, worst member phase sum, worst symbol after the fact. | Explain drawdown and generate future hypotheses. | Directly exclude June, WPR, TSI, or named symbols without a prefix-safe rule. |
| `prefix_safe_candidate` | Signal candle body, prior 72h return, volume ratio, session bucket, member state, accepted classifier lane. | Build future disable facts because values exist before entry. | Tune thresholds only to remove known losing events without out-of-sample review. |
| `runtime_required_fact` | Member signal state, group-pool selection, exit horizon, late-cycle state, high-leverage state, fill/gap state. | Main-control readiness and candidate-preparation gating. | Skip because historical right-tail evidence is large. |

## Member Drawdown Interpretation

| Member | Current Evidence | Disable Interpretation |
| --- | --- | --- |
| `WPR-001` | Phase drag is worst in June 2026, but total right-tail evidence remains valuable. | Do not blacklist. Require `wpr_member_recent_loss_cluster_state` and `wpr_signal_extension_state` before downshift. |
| `TSI-001` | Second-largest phase drag, but member-level evidence has strong right-tail rows. | Do not blacklist. Require `tsi_member_phase_drag_state` and `tsi_signal_extension_state` before downshift. |
| `DMI-001` | Contributes phase losses but has strong total full evidence. | Keep as eligible; use only group-level late-cycle facts. |
| `MFI-001` | Negative worst event exists, but phase sum is positive. | Keep as eligible; no member-specific disable from current evidence. |
| `MHI-001` | Small sample in current group row. | Keep as support member; require sample-size disclosure. |
| `PPO-001` | Sparse in current group-pool rows. | Keep as support member; require sample-size disclosure. |

## Prefix-Safe Disable Candidates

| Disable Candidate | Signal-Time Inputs | Intended Behavior |
| --- | --- | --- |
| `mpg_member_recent_loss_cluster_state` | Same member's recent closed-candle signal outcomes in a bounded rolling window after they are known. | Downshift member confidence; do not remove the whole group. |
| `mpg_signal_extension_state` | Signal candle body, prior 24h/72h return, and impulse rank available before entry. | Block late-cycle overextension candidates. |
| `mpg_member_substitution_state` | Current member, group classifier, and capital-slot competition state. | Prefer cleaner members only when current facts justify substitution. |
| `mpg_exit_horizon_tradeoff_state` | Versioned `12h` or `72h` lane selected before entry. | Keep 12h cleaner tradeoff separate from 72h right-tail revival. |
| `mpg_drawdown_phase_watch_state` | Rolling drawdown from already-closed MPG observation records, not future event paths. | Pause or downshift observation after realized strategy drawdown breaches boundary. |
| `mpg_high_leverage_disable_state` | Leverage lane, proxy liquidation history, and real margin model availability. | Keep 5x disabled and 3x stress-only. |

## RequiredFacts Deltas

| RequiredFact | Meaning | Missing Behavior |
| --- | --- | --- |
| `mpg_member_drawdown_forensic_state` | Retrospective member/symbol/month attribution is attached for review. | `review_only_warning` |
| `mpg_member_disable_candidate_state` | Prefix-safe member-level disable hypothesis is present and versioned. | `do_not_member_filter` |
| `mpg_member_recent_loss_cluster_state` | Rolling member loss cluster using only already-known outcomes. | `no_member_downshift` |
| `mpg_signal_extension_state` | Signal-time body/prior-return impulse extension state. | `block_late_cycle_candidate_prepare` |
| `mpg_drawdown_phase_watch_state` | Realized observation drawdown watch state. | `observe_only_or_pause_review` |
| `mpg_exit_horizon_tradeoff_state` | `12h` tradeoff versus `72h` revival lane selected before entry. | `block_candidate_prepare` |
| `mpg_high_leverage_disable_state` | 3x/5x stress and disable boundary. | `block_leverage_promotion` |

## Sample Disable Context Packet

```json
{
  "strategy_group_id": "MPG-001",
  "version": "2026-06-16-member-dd-r0",
  "status": "disable_context_only",
  "symbol": "INTCUSDT",
  "direction": "long",
  "source_member": "WPR-001",
  "classifier_id": "mpg_lcd_body_le_1p5",
  "required_facts_state": {
    "mpg_member_drawdown_forensic_state": "present_review_only",
    "mpg_member_disable_candidate_state": "candidate_not_promoted",
    "mpg_signal_extension_state": "required_before_candidate",
    "mpg_exit_horizon_tradeoff_state": "required_before_candidate",
    "mpg_high_leverage_disable_state": "5x_disabled"
  },
  "main_control_hint": "do_not_blacklist_member_from_forensics_only",
  "reason": "MPG right-tail evidence is strong, but WPR/TSI drawdown attribution is retrospective and must be converted into prefix-safe disable facts before member filtering."
}
```

## Research Conclusion

`MPG-001` should stay first-batch and right-tail relevant, but the drawdown
addendum changes the promotion language:

```text
keep MPG alive
do not blacklist members from retrospective attribution
require prefix-safe disable facts before member filtering
separate 12h tradeoff from 72h revival
keep 5x disabled
keep drawdown as review blocker, not execution-safety bypass
```

This preserves the strongest right-tail family while preventing drawdown
forensics from becoming an overfit runtime rule.
