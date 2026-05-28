# BRC-R5-002 Strategy Family Trial Admission Gate

## Funded Validation Admission System Specification

## 1. Purpose

`BRC-R5-002 Strategy Family Trial Admission Gate` defines how a strategy family becomes eligible to enter a bounded gated trial.

This is not a strict strategy approval committee.

This is a funded validation admission system.

Its purpose is to let the Owner place a strategy family into controlled testnet or live validation under explicit risk disclosure, risk acceptance, constraints, audit, and review.

The system should not try to prove that a strategy is already good enough before it can be tested. Instead, it should answer:

```text
Can this strategy family be tested under bounded risk?
If yes, under what env, stage, execution mode, constraints, and review requirements?
```

The preferred outcome for uncertainty is not immediate rejection. The preferred outcome is usually:

```text
Admit with Constraints
```

The gate should support practical iteration:

```text
try small
limit loss
record what happened
review
adjust
repeat or park
```

---

## 2. Non-goals

This system is not:

* a strategy ranking system
* an automatic strategy selector
* a market regime prediction engine
* a full risk engine
* a sizing engine
* a generic trading terminal
* a live execution bypass
* a replacement for Operation Layer
* a replacement for the existing Risk / Capital Module
* a place for LLM to make trading decisions
* a withdrawal / transfer interface

It must not introduce:

* unrestricted live execution
* arbitrary symbol / side / size orders
* withdrawal / transfer
* LLM direct execution
* execution without Operation Layer
* execution without audit
* execution without bounded constraints

---

## 3. Core Product Principle

The core principle is:

```text
Risk disclosure + Owner risk acceptance + bounded constraints + Operation execution + review.
```

The system should allow Owner-driven trial and error.

The Owner may choose to use disposable capital to validate a strategy family in live conditions, but the system must:

1. show the risk,
2. show the evidence gaps,
3. show the current account / reconciliation state,
4. show the calculated or proposed trial constraints,
5. record Owner risk acceptance,
6. install constraints through the proper execution path,
7. enforce or delegate enforcement to the correct risk/capital layer,
8. write audit and review evidence.

The gate should not block merely because a strategy is early, uncertain, or has incomplete evidence.

It should block when the system cannot safely bound, audit, or execute the trial.

---

## 4. Trial Environment and Trial Stage

The program model should support the same trial flow across environments.

```text
trial_env = testnet | live
```

The distinction between testnet and live is an environment distinction, not a separate program model.

The same high-level flow applies:

```text
Strategy family
-> Admission Gate
-> Trial constraints
-> Operation Layer
-> Runtime trial carrier
-> Audit / Review
```

### 4.1 Trial Env

#### `testnet`

Used for development validation, rehearsal, and non-fund-risk verification.

#### `live`

Used for funded validation with real capital risk.

### 4.2 Trial Stage

Use two stages initially:

```text
development_validation
funded_validation
```

Do not introduce `production_observation` as a separate stage.

If the system needs observation behavior, express that through `execution_mode = observe_only`.

### 4.3 Common Combinations

| trial_env | trial_stage            | Meaning                                            |
| --------- | ---------------------- | -------------------------------------------------- |
| testnet   | development_validation | Development validation / rehearsal                 |
| live      | funded_validation      | Real funded validation with disposable risk budget |

Other combinations may be allowed if useful, but they should be explicitly represented and audited.

---

## 5. Admission Decision Model

Admission decisions should use four states:

```text
admit
admit_with_constraints
reject
park
```

### 5.1 `admit`

The strategy family may enter a gated trial with standard constraints.

This should be relatively rare.

### 5.2 `admit_with_constraints`

The strategy family may enter a gated trial, but with tightened constraints.

This should be the primary expected outcome for early or uncertain strategies.

Examples:

* evidence incomplete
* regime uncertain
* Owner confidence medium / low
* single-symbol evidence
* small sample
* parameter stability not fully known
* strategy is exploratory but bounded

The system should lower risk instead of rejecting when uncertainty is containable.

### 5.3 `park`

The strategy family is not ready to consume a trial budget now, but the hypothesis is not rejected.

Use `park` when:

* the idea is still valuable,
* evidence is too unclear,
* Owner does not want to allocate risk now,
* current regime does not justify testing,
* the family definition is still too vague.

Parked families may be revised later.

### 5.4 `reject`

Reject should be reserved for system boundary failures or non-negotiable violations.

Examples:

* requires withdrawal / transfer
* requires LLM direct execution
* requires bypassing Operation Layer
* requires unbounded live execution
* cannot be audited
* cannot be constrained
* account facts unavailable for live funded execution
* exchange unavailable for live funded execution
* unsupported executor required
* unknown unmanaged exposure prevents safe live execution

Reject is not for "strategy evidence is not perfect."

---

## 6. Execution Modes

Supported execution modes:

```text
auto_within_budget
owner_confirm_each_entry
observe_only
no_entry
```

`propose_only` is intentionally omitted to avoid semantic ambiguity.

### 6.1 `auto_within_budget`

Default mode for funded validation.

The strategy may execute automatically only within the installed trial constraints.

Constraints may include:

* allowed symbols
* max notional
* max leverage
* loss budget
* max attempts
* runtime state
* account facts / reconciliation requirements
* review requirements
* cooldowns

This is not unrestricted automatic trading.

It is bounded automatic execution within an accepted trial budget.

### 6.2 `owner_confirm_each_entry`

Reserved mode.

Each live entry would require Owner confirmation.

This mode should be defined in the domain model but not necessarily implemented in the first version.

### 6.3 `observe_only`

The strategy may record what it would have done, but no order is sent.

The system records trade intents such as:

* would enter
* would exit
* would reduce
* would cancel
* signal snapshot
* market facts snapshot
* risk state snapshot
* reason not executed

This mode is useful for validating signal behavior without trading.

### 6.4 `no_entry`

New entries are prohibited.

The system may monitor, record, review, or block attempted entries, but it must not create new exposure.

This mode is useful for:

* regime mismatch
* cooldown after failure
* post-trial review lock
* insufficient confidence
* Owner wants no new entries

---

## 7. Strategy Family Model

A strategy family is a hypothesis-level group of related strategies.

It should represent:

```text
market hypothesis
market structure exploited
signal family
risk shape
known failure modes
required data
required execution capabilities
```

It should not be a single parameter set.

Concrete parameters and exact execution behavior should belong to a playbook or playbook version.

### 7.1 Strategy Family Fields

Suggested fields:

```text
strategy_family_id
family_key
name
description
status
owner
created_at
updated_at
```

### 7.2 Strategy Family Version

Strategy family declarations must be versioned.

Suggested fields:

```text
strategy_family_version_id
strategy_family_id
version
hypothesis
market_structure
entry_logic_family
exit_logic_family
risk_model
supported_symbols
supported_timeframes
required_data
required_execution_capabilities
known_failure_modes
created_at
created_by
is_current
```

Admission decisions must reference the strategy family version used at decision time.

---

## 8. Regime Contract

The gate does not require market regime to be objectively proven by the system.

Instead:

1. the strategy family declares its regime contract,
2. the Owner inputs current market regime judgment,
3. the system checks consistency,
4. uncertainty produces constraints or degraded execution mode.

### 8.1 Strategy Family Regime Contract

Suggested fields:

```text
suitable_regimes
forbidden_regimes
degraded_regimes
uncertain_regime_behavior
mismatch_behavior
```

Example:

```json
{
  "suitable_regimes": ["trend", "breakout_expansion"],
  "forbidden_regimes": ["low_vol_chop"],
  "uncertain_regime_behavior": "observe_only",
  "mismatch_behavior": "no_entry"
}
```

### 8.2 Owner Market Regime Input

The Owner provides:

```text
current_regime
confidence
rationale
timestamp
optional market facts snapshot
```

The system does not need to prove that the Owner is correct. It should record the judgment and detect contradictions.

### 8.3 Regime Compatibility

Regime matching can be classified as:

```text
match
partial_match
uncertain
mismatch
```

Suggested behavior:

| Result        | Suggested behavior                                             |
| ------------- | -------------------------------------------------------------- |
| match         | admit or admit_with_constraints                                |
| partial_match | admit_with_constraints                                         |
| uncertain     | admit_with_constraints with degraded mode                      |
| mismatch      | no_entry / observe_only / park, unless safe degradation exists |

Regime uncertainty should usually reduce budget or execution permission, not directly reject.

---

## 9. Degradation Policy

A strategy family may declare a degradation policy.

Degradation policy does not directly mutate capital or leverage.

It expresses intent.

Examples:

```text
reduce_risk
observe_only
no_entry
stricter_review
lower_budget_profile
```

The Risk / Capital Module is responsible for converting degradation intent into concrete enforceable constraints.

### 9.1 Degradation Triggers

Possible triggers:

```text
regime_uncertain
regime_partial_match
regime_mismatch
owner_low_confidence
evidence_incomplete
volatility_high
symbol_coverage_narrow
post_failure_repeat
```

### 9.2 Degradation Outcomes

Possible outcomes:

```text
execution_mode = observe_only
execution_mode = no_entry
risk_profile = micro
risk_profile = small
max_attempts reduced
review_required_after_each_attempt = true
cooldown_after_failure = true
```

---

## 10. Relaxable Safeguards vs System Boundaries

The system must distinguish relaxable safeguards from non-negotiable system boundaries.

### 10.1 Relaxable Safeguards

These may be edited by strategy family configuration or admission rule configuration.

Examples:

```text
require_regime_match
require_high_owner_confidence
require_multi_symbol_evidence
require_large_sample_backtest
require_parameter_stability
require_multi_timeframe_validation
```

Relaxing these safeguards should result in compensating constraints.

Examples:

```text
lower risk profile
observe_only
no_entry
fewer attempts
mandatory review
cooldown
```

### 10.2 Non-negotiable System Boundaries

These must not be disabled by strategy family configuration.

Examples:

```text
Operation Layer required
audit required
Owner risk acceptance required
no withdrawal / transfer
no LLM direct execution
no unbounded live execution
no bypass of account facts for live funded execution
no bypass of reconciliation requirements for live funded execution
no unsupported executor
```

For live funded validation, if account facts are unavailable, the system must reject or block execution.

This represents exchange/account unavailability, not a risk the Owner can simply accept.

---

## 11. Risk / Capital Module Delegation

BRC-R5-002 should not become a second sizing engine.

The system already has or is expected to have a unified Risk / Capital Module.

Admission Gate should output:

```text
risk intent
degradation intent
requested risk profile
execution mode
review requirements
```

The Risk / Capital Module should compute:

```text
max notional
max leverage
loss budget
max attempts
exposure limit
symbol allocation
```

Operation Layer should install and enforce the resulting constraints.

### 11.1 Responsibility Split

| Component                  | Responsibility                                                                      |
| -------------------------- | ----------------------------------------------------------------------------------- |
| Admission Gate             | decide whether a strategy family can enter a trial; produce risk/degradation intent |
| Risk / Capital Module      | compute concrete budget and capital constraints                                     |
| Operation Layer            | install constraints and execute trial creation                                      |
| Runtime / Strategy Carrier | run only within installed constraints                                               |
| Review System              | evaluate outcome and update eligibility                                             |

### 11.2 Constraint Snapshot

Even if the Risk / Capital Module computes the final values, the admission decision must store the resulting constraint snapshot.

This is required for auditability and reproducibility.

---

## 12. Owner Risk Acceptance

Owner risk acceptance is a first-class concept.

The Owner does not need to manually enter account size.

Account size and available capital should be loaded from account facts / exchange read model.

The Owner confirms the resulting calculated or proposed budget and constraints.

Suggested fields:

```text
owner_risk_acceptance_id
admission_request_id
strategy_family_version_id
trial_env
trial_stage
account_facts_snapshot_ref
risk_profile
risk_policy_snapshot
computed_constraints_snapshot
risk_disclosure_snapshot
known_gaps_snapshot
owner_rationale
confirmation_phrase
confirmed_at
created_at
```

Owner risk acceptance means:

```text
The Owner reviewed the risks, gaps, budget, and constraints, and accepted the bounded trial.
```

It does not mean the system may bypass hard system boundaries.

---

## 13. Admission Evidence

The evidence packet should support informed trial admission.

It should not require perfect proof.

### 13.1 Mandatory Evidence

Minimum evidence should include:

```text
strategy hypothesis
market structure exploited
suitable / forbidden regimes
risk boundary
known failure modes
review contract
required data
required execution capabilities
```

### 13.2 Recommended Evidence

Recommended evidence may include:

```text
backtest summary
symbol coverage
timeframe coverage
fee/slippage assumptions
stress period examples
parameter sensitivity
manual observation notes
prior testnet/shadow/live trial results
failure examples
```

### 13.3 Missing Evidence

Missing evidence should usually lead to:

```text
admit_with_constraints
park
observe_only
no_entry
lower risk profile
```

It should not automatically cause reject unless the missing evidence prevents bounded execution.

---

## 14. Admission Workflow

High-level flow:

```text
1. Owner selects strategy family.
2. Owner selects strategy family version or draft.
3. Owner selects trial_env and trial_stage.
4. Owner inputs market regime judgment and confidence.
5. System loads strategy family contract.
6. System loads evidence packet.
7. System loads account facts and system readiness.
8. Admission Gate evaluates evidence, regime compatibility, and system boundaries.
9. Admission Gate produces admission decision.
10. Risk / Capital Module computes concrete constraints if applicable.
11. Owner reviews risk disclosure and calculated constraints.
12. Owner confirms risk acceptance.
13. Operation Layer creates / activates the gated trial.
14. Runtime carrier runs under installed constraints.
15. Post-trial review is mandatory.
```

---

## 15. Admission Decision Output

Admission decision should include:

```text
admission_decision_id
admission_request_id
decision
trial_env
trial_stage
strategy_family_version_id
playbook_version_id if available
owner_market_regime_input_id
evidence_packet_id
rule_config_version
risk_profile
execution_mode
degradation_applied
risk_intent
degradation_intent
blockers
warnings
risk_disclosure
constraints_snapshot
owner_risk_acceptance_id
expires_at
created_at
```

### 15.1 Decision Bias

Default decision bias should be:

```text
admit_with_constraints
```

when uncertainty can be contained.

Reject should be reserved for system boundary failures.

---

## 16. Playbook Binding

Admission is strategy-family focused, but trial execution requires a concrete playbook.

Recommended rule:

```text
Admission may evaluate a strategy family.
Creating a gated trial must bind a playbook_version.
```

The admission decision should either:

1. include an approved playbook version, or
2. require Operation Layer preflight to select and pin one before creating the trial.

---

## 17. Operation Layer Integration

Admission Gate should not directly execute trial creation.

It produces an admission decision.

Operation Layer performs state-changing actions.

Example Operation:

```text
create_gated_trial_from_admission
```

Operation preflight should verify:

```text
admission decision exists
admission decision not expired
decision is admit or admit_with_constraints
Owner risk acceptance exists if required
account facts still valid
constraints snapshot exists
Operation Layer available
audit writable
trial env allowed
playbook version pinned
```

Operation confirm should:

```text
create trial / campaign
install constraints
switch runtime carrier if needed
write audit
link admission decision
link owner risk acceptance
link strategy family version
```

---

## 18. Runtime Trial Carrier

The runtime carrier should run according to installed execution mode.

### 18.1 `auto_within_budget`

Strategy may auto-execute only within installed constraints.

If any constraint would be exceeded, risk module / operation guard must block.

### 18.2 `observe_only`

Strategy records trade intents but does not send orders.

Events may include:

```text
would_enter
would_exit
would_reduce
would_cancel
signal_snapshot
not_executed_reason = observe_only
```

### 18.3 `no_entry`

New entries are blocked.

Events may include:

```text
entry_blocked_by_trial_constraint
not_executed_reason = no_entry
```

### 18.4 `owner_confirm_each_entry`

Reserved for future implementation.

---

## 19. PG-backed Configuration Model

All production admission configs and constraints should be PG-backed.

YAML is allowed only for:

```text
seed defaults
test fixtures
exports
```

It must not be the production source of truth.

### 19.1 Suggested PG-backed Tables

Suggested domain tables:

```text
strategy_families
strategy_family_versions
strategy_family_regime_contracts
strategy_family_safeguards
strategy_family_degradation_policies
admission_rule_configs
admission_safety_boundaries
admission_requests
owner_market_regime_inputs
admission_evidence_packets
admission_decisions
trial_constraint_snapshots
owner_risk_acceptances
admission_audit_log
post_trial_reviews
```

### 19.2 Version Pinning

Every admission decision must pin:

```text
strategy_family_version_id
admission_rule_config_id
evidence_packet_id
owner_market_regime_input_id
risk_policy_version if available
constraint_snapshot_id
```

This allows future review to reconstruct why a decision was made.

---

## 20. Admission Rule Config

Admission rules should be configurable and versioned.

They should support:

```text
warnings
blockers
admit_with_constraints
park
reject
degradation profile selection
risk profile request
override policy
```

Rules should be auditable and queryable.

### 20.1 Override Model

Rules should specify whether they are:

```text
non_overridable_system_boundary
global_admission_policy
strategy_family_safeguard
trial_stage_constraint
owner_runtime_override
```

Only relaxable safeguards can be overridden.

System boundaries cannot be disabled by strategy family configuration.

---

## 21. Post-Trial Review

Every funded validation trial must produce a review before repeat or promotion.

Review outcome:

```text
promote
repeat_with_constraints
revise_family
park
reject
```

Review should evaluate:

```text
hypothesis supported?
market regime matched?
playbook adhered?
risk boundary worked?
execution issue?
account fact issue?
unexpected failure mode?
evidence gap?
PnL outcome?
```

PnL alone must not determine success.

A losing trial can still support a hypothesis.

A profitable trial can still fail review if it violated process or risk boundaries.

---

## 22. Frontend Workflow

Suggested pages:

```text
Strategy Families
Strategy Family Detail
Admission Request
Evidence Packet
Market Regime Input
Admission Decision
Owner Risk Acceptance
Trial Constraints
Parked Families
Post-Trial Review
```

### 22.1 Admission Request UI

Should show:

```text
strategy family declaration
strategy family version
evidence completeness
Owner market regime input
regime compatibility
risk disclosure
requested trial env/stage
execution mode
risk profile recommendation
known gaps
```

### 22.2 Admission Decision UI

Should show:

```text
decision
reason
warnings
blockers
degradation applied
execution mode
risk intent
computed constraints if available
Owner risk acceptance requirement
Operation Layer next action
```

### 22.3 Owner Risk Acceptance UI

Should show:

```text
account facts source / truth level
computed budget / constraints
known evidence gaps
what the system will allow
what the system will block
review requirement
confirmation phrase
```

---

## 23. API Contract Draft

Do not implement before project analysis.

Possible API groups:

```text
GET    /api/brc/strategy-families
POST   /api/brc/strategy-families
GET    /api/brc/strategy-families/{id}
POST   /api/brc/strategy-families/{id}/versions

POST   /api/brc/admissions/requests
GET    /api/brc/admissions/requests/{id}
POST   /api/brc/admissions/requests/{id}/evaluate

GET    /api/brc/admissions/decisions/{id}
GET    /api/brc/admissions/decisions

POST   /api/brc/admissions/evidence-packets
POST   /api/brc/admissions/owner-regime-inputs
POST   /api/brc/admissions/risk-acceptances

POST   /api/brc/operations/preflight
       operation_type=create_gated_trial_from_admission
```

Actual endpoint names should follow existing project conventions.

---

## 24. Implementation Dependency: Project Analysis Required

Before implementation, Codex must analyze the current project to determine:

```text
current Risk / Capital Module location
current risk envelope model
current sizing / capital budget model
Operation Layer constraint installation path
runtime carrier state model
where execution_mode should be enforced
where observe_only trade intents should be recorded
where no_entry should block entries
how strategy family maps to playbook version
how review/evidence should link to admission decision
```

Do not implement BRC-R5-002 before this analysis.

---

## 25. Test Requirements

Tests should cover:

```text
PG-backed versioning
strategy family version pinning
rule config version pinning
relaxable safeguards
system boundary cannot be disabled
Owner regime input
regime mismatch -> constraints
evidence incomplete -> constraints or park
account facts unavailable -> live funded validation reject/block
trial_env=testnet behavior
trial_env=live behavior
auto_within_budget constraints
observe_only records intent and sends no order
no_entry blocks entry
Owner risk acceptance required
admission decision expires
create_gated_trial_from_admission Operation preflight
post-trial review required before repeat
```

---

## 26. Out of Scope

Initial BRC-R5-002 should not implement:

```text
automatic market regime detection
automatic strategy selection
strategy pool auto-routing
unrestricted live execution
withdrawal / transfer
LLM direct execution
generic exchange terminal
complete sizing engine if Risk / Capital Module already exists
actual strategy runner changes before project analysis
```

---

## 27. Open Questions for Codex Analysis

Codex should answer:

```text
1. Where is the existing Risk / Capital Module?
2. How does current BRC risk envelope map to capital constraints?
3. Is there already a risk profile or budget profile model?
4. Should Admission Gate output constraints directly or risk intent only?
5. Where should execution_mode be enforced?
6. How should observe_only trade intents be stored?
7. How should no_entry be enforced?
8. How should strategy_family_version map to playbook_version?
9. How should admission_decision_id link to campaign/trial/review?
10. What PG tables already exist that can be reused?
```

---

## 28. Summary

BRC-R5-002 should be built as a funded validation admission system.

The system should make it possible to test strategy families with bounded risk, not prevent experimentation.

It should prefer:

```text
Admit with Constraints
```

when uncertainty can be contained.

It should reject only when the system cannot safely bound, audit, or execute the trial.

Final responsibility split:

```text
Admission Gate:
risk disclosure, admission decision, risk intent, degradation intent, Owner risk acceptance

Risk / Capital Module:
actual budget, notional, leverage, exposure, attempt constraints

Operation Layer:
trial creation, constraint installation, runtime carrier transition

Runtime:
execute, observe, or block according to installed execution_mode

Review:
evaluate outcome and determine next eligibility
```
