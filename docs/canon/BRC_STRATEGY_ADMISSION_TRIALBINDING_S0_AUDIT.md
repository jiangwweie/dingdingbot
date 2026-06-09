---
title: BRC_STRATEGY_ADMISSION_TRIALBINDING_S0_AUDIT
status: AUDIT_REPORT
authority: claude-semantic-audit
date: 2026-06-09
scope: S0 semantic debt audit of BRC strategy-family admission and trial-binding lifecycle
---

# BRC Strategy / Admission / TrialBinding S0 Audit

## 1. Executive Summary

**S0 verdict: S0_CONFIRMED**

S0 semantic debt is confirmed. The BRC admission lifecycle has accumulated
significant conceptual overlap, missing identity objects, and dual-track
authorization systems. The most critical gap is the absence of a first-class
`StrategyRuntimeInstance`, with `AdmissionTrialBinding` carrying implicit
runtime responsibilities it was not designed to hold.

---

## 2. Current Lifecycle As Implemented

The actual lifecycle in code:

```
StrategyFamily (brc_strategy_families)
  → StrategyFamilyVersion (brc_strategy_family_versions)
  → AdmissionEvidencePacket (brc_admission_evidence_packets)
  → AdmissionRequest (brc_admission_requests)
  → TrialConstraintSnapshot (brc_trial_constraint_snapshots)
  → AdmissionDecision (brc_admission_decisions)
  → OwnerRiskAcceptance (brc_owner_risk_acceptances)
  → AdmissionTrialBinding (brc_admission_trial_bindings)
  → BoundedRiskCampaign (brc_campaigns)  [created from binding]
  → TrialTradeIntent (brc_trial_trade_intents)  [non-executable evidence]
```

Parallel path (one-shot Owner execution, separate from admission):

```
OwnerRiskAcknowledgement (brc_owner_risk_acknowledgements)
  → BoundedLiveTrialAuthorizationDraft (brc_bounded_live_trial_auth_drafts)
  → BoundedLiveTrialAuthorization (brc_bounded_live_trial_authorizations)
  → ScopedRuntimeSafetyClearance (brc_scoped_runtime_safety_clearances)
  → FinalGate → Order
```

---

## 3. Concept Inventory

| Concept | Current Files / Models | Current Responsibility | State Fields | Parent / Child Links | Ambiguity | Tests | S0 Risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| StrategyFamily | `src/domain/brc_admission.py:100` `PGBrcStrategyFamilyORM` | Family identity and classification | `status`: active/intake/parked/rejected | Parent of StrategyFamilyVersion | Two competing status enums: `StrategyFamilyStatus` in admission (active/intake/parked/rejected) vs registry (registered_hypothesis_only/active_observation_candidate/live_readonly_observation/parked/retired) | Yes | MEDIUM |
| StrategyFamilyVersion | `src/domain/brc_admission.py:111` `PGBrcStrategyFamilyVersionORM` | Versioned strategy specification | `is_current: bool` | Child of StrategyFamily; parent of AdmissionEvidencePacket | `is_current` is mutable; no immutability enforcement after admission; `version_id` duplicates `family_id` in registry (e.g. "TF-001-live-readonly-v0") | Yes | HIGH |
| AdmissionDecision | `src/domain/brc_admission.py:197` `PGBrcAdmissionDecisionORM` | Admission gate pass/fail | `decision`: admit/admit_with_constraints/reject/park; `execution_mode`; `expires_at_ms` (optional) | Child of AdmissionRequest; links to EvidencePacket, RuleConfig, ConstraintSnapshot | No lifecycle status beyond initial decision; optional `expires_at_ms` but no enforcement; no supersession mechanism; acts like runtime permission when it should be admission pass only | Yes | HIGH |
| OwnerRiskAcceptance | `src/domain/brc_admission.py:225` `PGBrcOwnerRiskAcceptanceORM` | Owner acknowledgement of strategy runtime risk | None (immutable record) | Child of AdmissionRequest; sibling of AdmissionDecision | Confused with authorization; separate from OwnerRiskAcknowledgement in owner_trial_flow; no scope constraint (budget/leverage/TP-SL); reusable without explicit scope | Yes | HIGH |
| AdmissionTrialBinding | `src/domain/brc_admission.py:265` `PGBrcAdmissionTrialBindingORM` | Binding between admitted strategy version and trial scope | `binding_status`: planned/binding_reserved/cancelled/expired/invalidated/campaign_created/runtime_constraints_installed/runtime_installed | Links Decision, Acceptance, ConstraintSnapshot, Version | Overloaded: is it a binding record or a runtime instance? Accumulates campaign_id, runtime_carrier_id; lifecycle grows with each operation phase; no uniqueness constraints on active bindings | Yes | CRITICAL |
| TrialTradeIntent | `src/domain/brc_admission.py:297` `PGBrcTrialTradeIntentORM` | Non-executable evidence record for execution-mode enforcement | `decision`: recorded/blocked/unavailable | Child of campaign/binding | Explicitly non-executable; no link to StrategyRuntimeInstance; no lifecycle after creation; overlaps conceptually with ExecutionIntent in the target model | Yes | MEDIUM |
| OwnerRiskAcknowledgement | `src/application/owner_trial_flow.py:54` | One-shot owner warning acknowledgement | Immutable record | Standalone; links to carrier | Separate concept from OwnerRiskAcceptance; different system entirely | Yes | MEDIUM |
| BoundedLiveTrialAuthorizationDraft | `src/application/owner_trial_flow.py:79` | Draft authorization for one-shot live trade | Single-use, pending state | Links to acknowledgement | Parallel authorization system to admission | Yes | LOW |
| BoundedLiveTrialAuthorization | `src/application/owner_trial_flow.py:126` | Owner-activated live trade authorization | Single-use, owner-authorized state | Links to draft | Parallel authorization system to admission; is per-trade not per-strategy-runtime | Yes | LOW |
| BoundedRiskCampaign | `src/domain/bounded_risk_campaign.py:409` | Risk-budgeted campaign container | `status`: observe/trading/loss_locked/finalized | Parent of CampaignAttempt | Not linked to StrategyRuntimeInstance; lifecycle driven by BrcOperationService phases; no explicit binding-to-campaign 1:1 enforcement | Yes | MEDIUM |
| StrategyRuntimeInstance | **MISSING** | Running bounded strategy instance | N/A | N/A | Does not exist; AdmissionTrialBinding implicitly carries this role | No | CRITICAL |

---

## 4. Confirmed Semantic Debt

### S0-A-001: Missing First-Class StrategyRuntimeInstance

**Evidence:**
- `grep -rn "StrategyRuntimeInstance\|RuntimeInstance\|runtime_instance" src/` returns zero results.
- `docs/canon/BRC_TARGET_SEMANTICS.md:68`: "StrategyRuntimeInstance | missing | Does not exist in current code | Running bounded strategy instance that generates evaluations"
- `AdmissionTrialBinding` accumulates `campaign_id`, `runtime_carrier_id`, and progresses through 8 status states, effectively acting as a runtime identity.

**Why S0:**
The target architecture defines `StrategyRuntimeInstance` as the canonical
object binding an admitted strategy version to a concrete running scope
(family_version, symbol, timeframe, mode, admission_decision,
owner_risk_acceptance, trial_binding, lifecycle_status, activation time,
deactivation time, runtime config hash, evidence hash). Without it, downstream
systems (signal evaluation, order candidate, review, audit) lack a stable
runtime identity to reference.

**Affected concepts:** AdmissionTrialBinding, TrialTradeIntent, BoundedRiskCampaign, SignalEvaluation, Review

**Recommended canonical meaning:** A first-class runtime object representing an activated strategy version under a specific bounded scope. Must be the identity that signals, intents, orders, and reviews reference.

**Suggested fix direction:** Introduce `StrategyRuntimeInstance` as a new domain model with its own PG table, promoted from the implicit state accumulated by `AdmissionTrialBinding`.

**Do-not-fix-yet notes:** This is a design-level debt item. Implementation should follow after audit is confirmed and canonical semantics are agreed.

---

### S0-A-002: AdmissionTrialBinding Overloaded as Runtime Identity

**Evidence:**
- `src/domain/brc_admission.py:265-294`: `AdmissionTrialBinding` domain model has 8 lifecycle states: `planned → binding_reserved → campaign_created → runtime_constraints_installed → runtime_installed → ...`
- `binding_status` field grows with each operation phase in `BrcOperationService`.
- `campaign_id` and `runtime_carrier_id` are added progressively.
- ORM table `brc_admission_trial_bindings` has no foreign key constraint to `brc_campaigns`, so the binding↔campaign relationship is soft.
- `PGBrcAdmissionTrialBindingORM:2559`: docstring says "This is a planning/carrier-binding fact only" but the lifecycle states contradict this.

**Why S0:**
A "binding" should be a static relationship record (admission decision ↔ trial slot). Instead it accumulates runtime state across 17+ operation phases (binding_reservation → campaign → constraints → carrier → start → handoff → strategy activation → signal loop → signal evaluation). This makes the binding record both a planning artifact and a runtime state machine, violating single responsibility.

**Affected concepts:** AdmissionTrialBinding, BoundedRiskCampaign, BrcOperationService

**Recommended canonical meaning:** AdmissionTrialBinding should bind one admission decision to one trial scope. Runtime state belongs on a StrategyRuntimeInstance.

**Suggested fix direction:** Extract runtime state (campaign_id, carrier_id, status progression) into StrategyRuntimeInstance. AdmissionTrialBinding becomes a static binding record.

**Do-not-fix-yet notes:** The 17-phase operation flow is well-tested and functional. Extraction should be incremental.

---

### S0-A-003: Two Parallel Risk Acceptance / Authorization Systems

**Evidence:**
- `src/domain/brc_admission.py:225`: `OwnerRiskAcceptance` — PG-backed, part of admission flow, no explicit scope (budget/leverage/TP-SL).
- `src/application/owner_trial_flow.py:54`: `OwnerRiskAcknowledgement` — separate model, carrier-scoped, for one-shot execution.
- `src/application/owner_trial_flow.py:126`: `BoundedLiveTrialAuthorization` — single-use, per-trade authorization with explicit max_notional/quantity/leverage/protection_plan.
- Both systems coexist in the same API (`api_brc_console.py` imports both).
- `OwnerRiskAcceptance.confirmation_phrase` is freeform text, while `BoundedLiveTrialAuthorization` has explicit numeric scope.
- The `OwnerTrialFlowCurrentResponse` explicitly asserts: `risk_acknowledgement_is_not_live_authorization: Literal[True] = True`.

**Why S0:**
Two systems exist for owner risk authorization, with different scopes, different persistence, and different downstream consumption. `OwnerRiskAcceptance` has no explicit budget/leverage/protection scope, meaning it could be reused across trades without constraint. `BoundedLiveTrialAuthorization` is well-scoped but only for one-shot execution, not the admission/trial path.

**Affected concepts:** OwnerRiskAcceptance, OwnerRiskAcknowledgement, BoundedLiveTrialAuthorization, BoundedLiveTrialAuthorizationDraft

**Recommended canonical meaning:** Owner risk acceptance should be scoped and versioned. One-shot authorization should eventually be a special case of a scoped acceptance.

**Suggested fix direction:** Unify risk acceptance semantics. `OwnerRiskAcceptance` needs explicit scope fields (budget, leverage, TP-SL). The one-shot path may remain as a special case.

**Do-not-fix-yet notes:** The one-shot path is well-tested and safe. Unification should not break the existing owner trial flow.

---

### S0-A-004: AdmissionDecision Lacks Lifecycle Status and Supersession

**Evidence:**
- `src/domain/brc_admission.py:197-222`: `AdmissionDecision` has `decision` (admit/reject/park) and optional `expires_at_ms` but no lifecycle status field.
- No mechanism to supersede or expire a decision programmatically.
- `AdmissionDecision.owner_risk_acceptance_id` is optional, meaning a decision can exist without owner acceptance.
- `AdmissionDecision.execution_mode` (`auto_within_budget`/`owner_confirm_each_entry`/`observe_only`/`no_entry`) is set at evaluation time and cannot be changed.

**Why S0:**
An admission decision is currently a one-time evaluation result. In a full lifecycle, decisions need states like: active → superseded → expired → revoked. Without this, there is no way to invalidate an old admission when a new version is admitted, and no way to expire a decision that was valid for a limited time window.

**Affected concepts:** AdmissionDecision, AdmissionTrialBinding, OwnerRiskAcceptance

**Recommended canonical meaning:** AdmissionDecision should have lifecycle states (active/expired/superseded/revoked), a validity window, and a clear link to the specific immutable version it admits.

**Suggested fix direction:** Add lifecycle status to AdmissionDecision. Add expiry enforcement. Add supersession chain.

**Do-not-fix-yet notes:** Current single-admission-per-request flow works. Supersession matters only when multiple versions of the same family are admitted concurrently.

---

### S0-A-005: TrialTradeIntent Is Non-Executable But Carries Execution Mode

**Evidence:**
- `src/domain/brc_admission.py:297-320`: Docstring says "This is not an order, execution intent, or runtime command."
- Yet it carries `execution_mode` (auto_within_budget, owner_confirm_each_entry, observe_only, no_entry).
- `decision` field: recorded/blocked/unavailable — suggests some intents should be executable.
- In `test_brc_operation_layer.py`, `evaluate_trial_trade_intent` tests verify that `auto_within_budget` produces `decision=RECORDED` while `observe_only` produces `decision=BLOCKED`.
- No link to `StrategyRuntimeInstance` — only `campaign_id` and optional `binding_id`.

**Why S0:**
The intent model occupies an ambiguous zone: it is explicitly non-executable, but its `execution_mode` field and `decision` semantics (recorded vs blocked) suggest it is designed to track what *would* happen if execution were enabled. This creates confusion about whether it is:
1. A pure read-only observation record (current docstring claim), or
2. A would-be execution command that is gated (current semantic implication), or
3. A future ExecutionIntent that just hasn't been connected yet.

**Affected concepts:** TrialTradeIntent, ExecutionIntent, StrategyRuntimeInstance

**Recommended canonical meaning:** Separate read-only would-trade evidence (always non-executable, for observation mode) from executable trade intents (gated by FinalGate, for live/trial mode). The current model conflates both.

**Suggested fix direction:** Either rename to `WouldTradeEvidence` for clarity, or split into `SignalWouldTrade` (observation) and `TrialExecutionIntent` (gated execution).

**Do-not-fix-yet notes:** Current non-executable semantics are safe. The confusion is semantic, not behavioral.

---

### S0-A-006: Dual StrategyFamily Status Enums

**Evidence:**
- `src/domain/brc_admission.py:62`: `StrategyFamilyStatus` with values: `active`, `intake`, `parked`, `rejected`.
- `src/domain/strategy_family_registry.py:26`: `StrategyFamilyStatus` with values: `registered_hypothesis_only`, `active_observation_candidate`, `live_readonly_observation`, `parked`, `retired`.
- Both are named `StrategyFamilyStatus` but have different values and different semantics.
- The admission version is for the PG-backed admission flow.
- The registry version is for the metadata-only observation registry.

**Why S0:**
Two enums with the same name but different semantics will cause import confusion and inconsistent status tracking. A strategy family could be `active` in admission but `registered_hypothesis_only` in the registry.

**Affected concepts:** StrategyFamily, StrategyFamilyMetadata

**Recommended canonical meaning:** Unify into a single status model or clearly namespace them (e.g., `AdmissionFamilyStatus`, `RegistryFamilyStatus`).

**Suggested fix direction:** Rename one or both to avoid collision. Consider whether the two systems should share a single status lifecycle.

**Do-not-fix-yet notes:** Currently manageable because the two systems are in different modules. Import conflicts are the main risk.

---

### S0-A-007: Weak Audit Traceability Across the Chain

**Evidence:**
- `AdmissionAuditLog` (`src/domain/brc_admission.py:252`) tracks events but has no foreign key to `StrategyRuntimeInstance` (which doesn't exist).
- `TrialTradeIntent.audit_refs_json` is unstructured JSON, not typed references.
- `BoundedRiskCampaign` has `metadata_json` for unstructured data.
- No single audit chain links: FamilyVersion → AdmissionDecision → OwnerRiskAcceptance → TrialBinding → Campaign → Intent → Order.
- `src/domain/brc_admission.py:89`: `ADMISSION_TRIAL_TRADE_INTENT_EVALUATED` event type exists but references are loose.

**Why S0:**
Without a stable runtime identity and typed audit references, the review/audit chain cannot programmatically trace from a trade intent back to the exact strategy version, evidence packet, admission decision, and owner acceptance that authorized it.

**Affected concepts:** AdmissionAuditLog, TrialTradeIntent, AdmissionTrialBinding, BoundedRiskCampaign

**Recommended canonical meaning:** Every artifact in the chain must carry typed references to its upstream objects. Review should be able to traverse the full chain programmatically.

**Suggested fix direction:** Add typed foreign keys. Introduce StrategyRuntimeInstance as the stable identity. Deprecate JSON blob references.

**Do-not-fix-yet notes:** Current audit log is functional for manual review. Programmatic traceability is a future requirement.

---

### S0-A-008: Missing Uniqueness and Cardinality Constraints

**Evidence:**
- `PGBrcAdmissionTrialBindingORM` has no unique constraint on `(admission_decision_id, binding_status)` — multiple active bindings for the same decision are possible.
- `PGBrcAdmissionDecisionORM` has no unique constraint on `(strategy_family_version_id, decision)` — multiple admit decisions for the same version are possible.
- `PGBrcOwnerRiskAcceptanceORM` has no uniqueness constraint — multiple acceptances for the same request are possible.
- In `test_brc_admission_phase1.py:316`, a test verifies that duplicate active bindings are rejected at the service level, but not at the DB level.

**Why S0:**
Without DB-level uniqueness constraints, the system relies on application-level checks that could be bypassed by direct DB access or concurrent requests. In a single-user system this is lower risk, but it still creates potential for orphaned records.

**Affected concepts:** AdmissionTrialBinding, AdmissionDecision, OwnerRiskAcceptance

**Recommended canonical meaning:** Add DB-level unique constraints where cardinality is known (e.g., one active binding per decision).

**Suggested fix direction:** Add partial unique indexes or DB constraints for known invariants.

**Do-not-fix-yet notes:** Service-level checks are currently sufficient for single-user operation.

---

## 5. Proposed Canonical Semantics

### StrategyFamily
A strategy classification identity. Contains: `family_id`, `family_key`, `name`, `description`, `status`, `owner`. Does not contain executable logic. Status lifecycle: intake → active → parked/rejected.

### StrategyFamilyVersion
An immutable versioned specification of a strategy family. Contains: `version`, `hypothesis`, `market_structure`, `entry_logic_family`, `exit_logic_family`, `risk_model`, `supported_symbols`, `supported_timeframes`, `regime_contract`, `safeguards`, `degradation_policy`. Once admitted, a version must be treated as immutable. Evidence packets are tied to a specific version.

### AdmissionDecision
A formal pass/fail evaluation result for a specific strategy family version. Contains: `decision`, `execution_mode`, `trial_env`, `trial_stage`, `risk_profile`, `expires_at_ms`. Must have lifecycle states: `active` → `expired`/`superseded`/`revoked`. Must target an immutable version. Should not be reused as execution authorization.

### OwnerRiskAcceptance
A scoped owner acknowledgement of strategy runtime risk. Must be tied to a specific admission decision and version. Should include: budget scope, leverage scope, TP/SL requirements, review requirements. Must not silently authorize execution. Is consumed when a trial binding is created and must be re-accepted for new bindings.

### TrialBinding
A static relationship record binding one admission decision to one trial scope. Contains: `admission_decision_id`, `owner_risk_acceptance_id`, `strategy_family_version_id`, `trial_env`, `trial_stage`, `execution_mode`. Status lifecycle: `planned` → `binding_reserved` → `active` → `retired`/`cancelled`/`expired`. Must not accumulate runtime state. Runtime state belongs on StrategyRuntimeInstance.

### StrategyRuntimeInstance (NEW)
A concrete activated strategy version under a specific runtime scope. This is the canonical runtime identity object. Contains:
- `runtime_instance_id` (stable identity)
- `family_id`, `family_version_id`
- `admission_decision_id`
- `owner_risk_acceptance_id`
- `trial_binding_id`
- `campaign_id`
- `symbol`, `timeframe`, `market`
- `mode`: read_only / paper / testnet / bounded_live
- `lifecycle_status`: pending → starting → running → paused → completed → terminated
- `activation_time_ms`, `deactivation_time_ms`
- `runtime_config_hash`, `evidence_version_hash`

Must be the identity that signals, intents, orders, and reviews reference. Downstream modules: runtime runner, owner console, review/audit, order ledger, signal ledger, strategy shelf, live/read-only observation, bounded trial authorization.

### TrialTradeIntent
A non-executable evidence record for audit and observation. Must not carry `execution_mode` unless it is explicitly a would-trade record for observation mode. Must reference `runtime_instance_id`. For executable scenarios, a separate `ExecutionIntent` (part of the target chain) should be used.

---

## 6. Proposed Invariants

1. **AdmissionDecision must target an immutable StrategyFamilyVersion.**
   Once a version is admitted, its specification must not change.

2. **OwnerRiskAcceptance must be scoped and cannot silently authorize execution.**
   Risk acceptance must reference a specific admission decision, version, and scope. It does not grant order permission.

3. **TrialBinding must bind one admitted strategy version to one trial scope.**
   A binding is a static relationship record. Runtime state belongs on StrategyRuntimeInstance.

4. **TrialTradeIntent must reference a stable runtime identity or binding.**
   Every intent must be traceable back to a StrategyRuntimeInstance or, in the current interim, an AdmissionTrialBinding.

5. **Live executable intent must not be confused with read-only would-trade intent.**
   Read-only observation uses non-executable evidence records. Live execution uses gated ExecutionIntents with FinalGate.

6. **Bounded live execution still requires explicit owner authorization and FinalGate.**
   Even with StrategyRuntimeInstance, no trade is executed without passing FinalGate and owner authorization.

7. **Review/audit must trace back to strategy version, evidence, binding, and runtime identity.**
   Every review record must be programmatically traceable to the full chain.

8. **One strategy version can have multiple bindings, but only one active binding per (version, symbol, timeframe, mode) tuple.**
   Prevents duplicate runtime instances for the same scope.

---

## 7. Minimal Follow-up Patch Plan

### Window A1: Canonical Docs / Model Semantics Only
- Finalize this audit report.
- Update `docs/canon/BRC_TARGET_SEMANTICS.md` with confirmed semantics.
- Update `docs/canon/TECH_DEBT_BASELINE.md` with S0 debt items.
- No code changes.

### Window A2: Introduce or Formalize StrategyRuntimeInstance
- Add `StrategyRuntimeInstance` domain model to `src/domain/`.
- Add `PGBrcStrategyRuntimeInstanceORM` to `src/infrastructure/pg_models.py`.
- Add migration.
- No downstream integration yet.

### Window A3: Tighten TrialBinding Lifecycle
- Add explicit cardinality constraints to `AdmissionTrialBinding`.
- Add unique index on `(admission_decision_id, binding_status)` for active states.
- Clarify that `campaign_id` and `runtime_carrier_id` are transitional and will move to StrategyRuntimeInstance.

### Window A4: Separate Read-Only TrialTradeIntent from Executable Intent
- Rename `TrialTradeIntent` to `WouldTradeEvidence` if it remains non-executable.
- OR add a `TrialExecutionIntent` model for the executable path.
- Ensure clear docstring separation.

### Window A5: Add Tests and Invariants
- Add invariant tests for: immutability of admitted versions, uniqueness of active bindings, traceability of intents.
- Add DB-level constraint tests.

### Window A6: API/Read-Model Adjustments for Console
- Update API response models to reflect new semantics.
- Add `runtime_instance_id` to relevant API responses.

---

## 8. Tests / Commands Run

| Command | Result |
| --- | --- |
| `git status` | Clean working tree, branch `codex/brc-product-backbone-sprint`, 4 commits ahead of origin |
| `rg -n "StrategyFamily\|StrategyFamilyVersion\|AdmissionDecision\|OwnerRiskAcceptance\|TrialBinding\|TrialTradeIntent\|StrategyRuntimeInstance\|RuntimeInstance\|Admission\|RiskAcceptance\|Trial" src tests docs alembic migrations` | 500+ matches across admission models, ORM tables, tests, API endpoints, and docs |
| `grep -rn "StrategyRuntimeInstance\|RuntimeInstance\|runtime_instance" src/` | Zero results — confirmed missing |
| Inspected `src/domain/brc_admission.py` (336 lines) | Full admission domain model — all 10 concepts present |
| Inspected `src/infrastructure/pg_models.py` (ORM definitions) | All admission ORM tables present |
| Inspected `src/application/brc_admission_service.py` (4400+ lines) | BrcAdmissionService with 60+ methods covering all 17 operation phases |
| Inspected `src/application/brc_operation_layer.py` (4000+ lines) | BrcOperationService with 17+ execution phases |
| Inspected `src/application/owner_trial_flow.py` (766 lines) | Parallel OwnerTrialFlowService with separate risk acceptance |
| Inspected `src/domain/strategy_family_registry.py` (406 lines) | Separate StrategyFamilyStatus enum with different values |
| Inspected `src/domain/bounded_risk_campaign.py` | BoundedRiskCampaign model with campaign lifecycle |
| Inspected `tests/unit/test_brc_admission_phase1.py` | Admission phase 1 tests — all passing |
| Inspected `tests/unit/test_brc_operation_layer.py` | Operation layer tests — 17 phases tested |
| Inspected `docs/canon/BRC_TARGET_SEMANTICS.md` | Confirms StrategyRuntimeInstance is missing |

---

## 9. Top 5 Confirmed Debts

1. **S0-A-001**: StrategyRuntimeInstance missing — CRITICAL
2. **S0-A-002**: AdmissionTrialBinding overloaded as runtime identity — CRITICAL
3. **S0-A-003**: Two parallel risk acceptance/authorization systems — HIGH
4. **S0-A-004**: AdmissionDecision lacks lifecycle status and supersession — HIGH
5. **S0-A-005**: TrialTradeIntent non-executable but carries execution mode — MEDIUM

---

## 10. StrategyRuntimeInstance Verdict

**StrategyRuntimeInstance is missing, not implicit or unnecessary.**

`AdmissionTrialBinding` is currently carrying implicit runtime responsibilities
(campaign_id, runtime_carrier_id, status progression through 8 states) but was
designed as a planning/binding fact. A first-class `StrategyRuntimeInstance` is
needed to:

- Provide a stable identity for signals, intents, orders, and reviews
- Separate planning (binding) from execution (runtime instance)
- Enable proper lifecycle management (pending → running → paused → terminated)
- Support multiple runtime instances per strategy version (e.g., same strategy on different symbols)
- Clean up the overloaded AdmissionTrialBinding

The `BoundedRiskCampaign` is a campaign-level risk container, not a strategy
runtime identity. It manages risk budget, attempts, and P&L — not strategy
activation, signal evaluation, or runtime lifecycle.

**Status in `docs/canon/BRC_TARGET_SEMANTICS.md`: confirmed "missing".**
