---
title: TRADEABILITY_DECISION_CONTRACT
status: CURRENT
authority: docs/current/TRADEABILITY_DECISION_CONTRACT.md
last_verified: 2026-07-01
---

# Tradeability Decision Contract

## Purpose

The Tradeability Decision is the main-control answer to one product question:

```text
Can this StrategyGroup trade now?
If not, what is the first blocker, who owns it, and what exact action removes it?
```

It exists because the project goal is not more governance artifacts. The goal is
bounded-aggressive small-capital trading experimentation:

```text
experiment-worthy strategy asset
-> final-owned admission
-> scoped policy / risk envelope
-> armed observation
-> fresh signal and RequiredFacts
-> official FinalGate and Operation Layer
-> protected submit
-> reconciliation, settlement, and review
```

The decision is a thin read model. It is not a ledger, strategy registry, policy
store, FinalGate input, Operation Layer input, or exchange-write authority.

Blocker classification follows
`docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`. Tradeability rows may use
product-level decisions such as `not_tradable_market_wait`, but the
`first_blocker_class` must be a precise contract class.

## Core Rule

Every active or newly absorbed StrategyGroup candidate must have exactly one
current tradeability decision:

```text
tradable_now
or
not_tradable with one first blocker
```

The first blocker must be the earliest missing state on the path to trading. Do
not collapse unrelated blockers into `waiting_for_market`. A missing fresh
signal is the first blocker only after the strategy asset is admitted, scoped,
armed, detector-attached, watcher-fed, fact-computed, blocker-classified, and
ready to continue to action-time facts when a signal appears.

## Decision Values

| Decision | Meaning | First owner |
| --- | --- | --- |
| `tradable_now` | Current fresh signal may continue through the official real-order chain | Runtime |
| `not_tradable_market_wait` | Strategy is admitted, scoped, armed, detector-attached, watcher-fed, fact-computed, action-time-path ready, and only lacks a fresh eligible signal | Market |
| `not_tradable_asset_admission` | Strategy is not yet a final-owned runtime asset or trial candidate | Engineering |
| `not_tradable_policy` | Owner capital, profile, symbol/side, leverage scenario, risk unit, attempt cap, or stage policy is missing | Owner |
| `not_tradable_facts` | RequiredFacts, source mapping, freshness, or fact validation is missing before action-time gating can be trusted | Engineering |
| `not_tradable_execution_gate` | FinalGate, Operation Layer, protection, account, position, order, exchange, or reconciliation readiness blocks real submit | Runtime |
| `not_tradable_strategy_quality` | Strategy is not experiment-worthy or its failure/loss envelope cannot be expressed | Strategy review |
| `not_tradable_safety_stop` | A hard safety or authority boundary forbids execution | Runtime / safety |

## Required Artifact Shape

The current main-control artifact should be generated as:

```text
output/runtime-monitor/latest-strategygroup-tradeability-decision.json
output/runtime-monitor/latest-strategygroup-tradeability-decision.md
```

The `tradeability-decision` file path is the direct generated view path. The
payload identity must be `brc.strategygroup_tradeability_decision.v1`, and
active consumers must expose this read model as `tradeability_decision`.

Each row should contain:

| Field | Meaning |
| --- | --- |
| `strategy_group_id` | Stable StrategyGroup id |
| `stage` | Current lifecycle stage, such as `tiny_live_intake_candidate`, `trial_asset_admission_candidate`, `admitted_trial_asset`, `armed_observation`, `tiny_live_ready`, or `live_submit_ready` |
| `decision` | One of the decision values above |
| `first_blocker_class` | Machine-readable blocker class |
| `first_blocker_detail` | One concise technical reason |
| `blocker_owner` | `engineering`, `owner`, `market`, `runtime`, `strategy_review`, or `safety` |
| `next_action` | The exact next engineering, policy, runtime, or review action |
| `after_next_state` | Expected state after the next action succeeds |
| `policy_scope` | Capital, profile, symbol, side, leverage scenario, attempt cap, and loss unit if applicable |
| `required_facts_status` | `ready`, `missing`, `stale`, `not_applicable`, or `action_time_only` |
| `runtime_scope_status` | Registry, tier, watcher, and runtime admission status |
| `runtime_safety_reference` | Pointer to Runtime Safety State live-submit readiness for this StrategyGroup |
| `authority_boundary` | Why this decision does or does not authorize real orders |

## Lifecycle Progression

The main-control path from research to trading is:

```text
research_candidate
-> tiny_live_intake_candidate
-> trial_asset_admission_candidate
-> admitted_trial_asset
-> armed_observation
-> tiny_live_ready
-> live_submit_ready
-> real_order_submitted
-> review_recorded
```

| Stage | Meaning | May do | Must not do |
| --- | --- | --- | --- |
| `tiny_live_intake_candidate` | Research output is worth main-control review | Intake review, final-owned snapshot, Tradeability Decision row | Runtime observation or submit authority |
| `trial_asset_admission_candidate` | Main control is preparing a scoped trial asset | Draft registry, tier, policy, facts, and risk envelope | Set `actionable_now=true` |
| `admitted_trial_asset` | The StrategyGroup exists as a final-owned trial asset | Be included in monitor, policy, and tier review | Submit real orders without action-time gates |
| `armed_observation` | Runtime may watch the strategy as a scoped non-executing or trial-eligible asset | Detect fresh signals and assemble facts | Bypass FinalGate / Operation Layer |
| `tiny_live_ready` | Non-executing readiness is closed for a scoped small-capital trial | Wait for fresh signal and action-time facts | Treat readiness as a live signal |
| `live_submit_ready` | Current action-time state may proceed through official real-order path | Call official FinalGate and Operation Layer | Bypass protection, scope, or exchange facts |

## Research Intake Rule

Strategy research artifacts belong in:

```text
/Users/jiangwei/Documents/final-strategy-research
```

Main control must not make the runtime monitor depend unconditionally on a
sibling worktree absolute path. Before a research candidate becomes part of the
main runtime sequence, it must be copied, reviewed, or normalized into a
final-owned intake snapshot or structured artifact.

Research intake may advance:

- `paper_observation_candidate`;
- `tiny_live_intake_candidate`;
- `trial_asset_admission_candidate`;
- `role_only_intake_candidate`;
- `classifier_enhancement`;
- `StrategyGroup_revision_evidence`.

It must not directly create:

- `actionable_now=true`;
- `real_order_authority=true`;
- live RequiredFacts;
- FinalGate input;
- Operation Layer input;
- exchange write.

## Promotion Scope

Do not use a generic `promote` label when the scope is narrower than live
eligibility.

Promotion decisions must carry a scope:

| Scope | Meaning |
| --- | --- |
| `intake_only` | Promote from research review into main-control intake only |
| `trial_admission` | Promote into trial asset admission preparation |
| `armed_observation` | Promote into runtime observation without real-order authority |
| `tiny_live_ready_review` | Promote for non-executing tiny-live readiness closure |
| `l4_eligibility_review` | Promote for Owner-scoped L4 eligibility review |

`promote` without scope is ambiguous and should be treated as invalid for new
artifacts.

## Blocker Mapping

Tradeability product decisions must map to blocker classes before planning or
task acceptance:

| Decision | Valid blocker classes |
| --- | --- |
| `not_tradable_market_wait` | `market_wait_validated`, `computed_not_satisfied` |
| `not_tradable_asset_admission` | `artifact_missing`, `schema_invalid`, `scope_not_attached` |
| `not_tradable_policy` | `policy_scope_missing` |
| `not_tradable_facts` | `artifact_missing`, `schema_invalid`, `detector_not_attached`, `watcher_tick_missing`, `computed_not_satisfied`, `replay_live_rule_mismatch` |
| `not_tradable_execution_gate` | `runtime_profile_scope_missing`, `action_time_boundary_not_reproduced`, `active_position_resolution` |
| `not_tradable_strategy_quality` | `review_only_warning`, `replay_live_rule_mismatch` |
| `not_tradable_safety_stop` | `hard_safety_stop` |

Do not emit a detector-missing class when the detector artifact exists, watcher
input is present, and computed facts are false. That state is
`computed_not_satisfied` unless replay/live rules disagree.

## Owner Boundary

The Owner controls:

- whether a strategy may become a trial asset;
- capital, profile, symbol/side, leverage scenario, loss unit, and attempt cap;
- promotion, downshift, pause, park, kill, and production-stage transition;
- scoped acceptance of strategy-quality or economic risk.

The Owner does not manually operate:

- RequiredFacts assembly;
- fresh signal validation;
- candidate / authorization evidence;
- FinalGate;
- Operation Layer;
- protection placement;
- reconciliation;
- ordinary in-boundary submit steps.

Owner policy may move a strategy toward trial eligibility. Owner policy must not
set `actionable_now=true` or override action-time safety facts.

## BRF2 Reference Interpretation

For a research-side short candidate such as `BRF2-001`, the correct current
shape is:

```json
{
  "strategy_group_id": "BRF2-001",
  "stage": "tiny_live_intake_candidate",
  "decision": "not_tradable_asset_admission",
  "first_blocker_class": "strategy_group_not_admitted_as_final_trial_asset",
  "blocker_owner": "engineering",
  "next_action": "build_trial_asset_admission_proposal",
  "after_next_state": "trial_asset_admission_candidate",
  "runtime_safety_reference": {
    "state_source": "runtime_safety_state",
    "live_submit_ready_for_strategy": false,
    "execution_attempt_required_for_lifecycle_entry": true
  }
}
```

This means the strategy has not been rejected. It means the first blocker is
asset admission, not market waiting. The next engineering step is to convert the
intake candidate into a scoped final-owned trial asset proposal.

## Acceptance Rules

A Tradeability Decision implementation is accepted only when:

| Requirement | Rule |
| --- | --- |
| One current decision | Every active selected, admitted, or intake candidate has exactly one current decision |
| First blocker | Each non-tradable row names one first blocker and one owner |
| Market wait precision | `not_tradable_market_wait` is used only after admission, scope, policy, detector, watcher input, facts, classification, and action-time path readiness are closed |
| Blocker contract | `first_blocker_class` maps to `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md` |
| Owner boundary | Owner intervention is true only for policy, risk, scope, promotion, downshift, pause, park, kill, or abnormal recovery |
| No authority leakage | Research, replay, paper, decision, and policy rows never emit legacy `actionable_now` or `real_order_authority` mirror fields |
| Monitor integration | Local monitor sequence surfaces the decision without turning internal gate names into the primary Owner interface |
| Cross-worktree safety | Runtime monitor does not require an external strategy-research absolute path to run |

## Boundary

This contract does not authorize:

- real-order submission;
- FinalGate bypass;
- Operation Layer bypass;
- stale-fact execution;
- missing protection;
- duplicate submit;
- conflicting active exposure;
- live-profile mutation;
- sizing-default expansion;
- withdrawal or transfer;
- credential mutation.

It only defines how main control should answer whether a StrategyGroup can
trade, why it cannot, and what concrete step moves it closer to trading.
