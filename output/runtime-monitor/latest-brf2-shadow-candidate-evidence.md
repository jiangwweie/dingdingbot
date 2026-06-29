## BRF2 Shadow Candidate Evidence

- Status: `brf2_shadow_candidate_evidence_waiting_for_fresh_signal`
- Generated: `2026-06-28T19:14:04.566103+00:00`
- Output JSON: `/Users/jiangwei/Documents/final-system-refactor-20260623/output/runtime-monitor/latest-brf2-shadow-candidate-evidence.json`
- StrategyGroup: `BRF2-001`
- Shadow candidate evidence ready: `否`
- Signal state: `blocked_by_disable_fact`
- First blocker: `short_squeeze_risk_state_disable_active` / `market`
- Next runtime step: `continue_brf2_armed_observation_until_disable_clears`
- Fact authority: `readonly_proxy_not_action_time_required_fact`
- Action-time RequiredFacts satisfied: `否`

## Boundary

- This evidence artifact is non-executing and local/read-model only.
- It preserves read-only signal context without converting it into action-time RequiredFacts.
- It does not call FinalGate, Operation Layer, or exchange write.
- It can only prepare the next official candidate/authorization evidence step.
