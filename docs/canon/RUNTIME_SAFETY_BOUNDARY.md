---
title: RUNTIME_SAFETY_BOUNDARY
status: CURRENT_CANON
authority: owner-instruction + code-verification + ADR-0009 + ADR-0012
last_verified: 2026-06-10
source_of_truth:
  - docs/adr/0009-non-real-live-execution-authorization-boundary.md
  - docs/adr/0012-bounded-risk-campaign-system.md
  - docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md
  - docs/canon/PROJECT_BASELINE_CURRENT.md
---

# Runtime Safety Boundary

This document defines the runtime safety boundaries for the BRC project.

---

## 1. Current Safety Principle

- Current code can reach the exchange order path through OwnerBoundedExecutionService.
- All execution work must respect Owner authorization and FinalGate.
- Runtime governance shadow/preview work must not create ExecutionIntent
  submit-ready records, orders, exchange writes, or runtime execution triggers
  unless a later task explicitly changes that boundary.
- RuntimeExecutionPlan, RuntimeExecutionIntentDraft, RuntimeExecutionIntent
  adapter preview, source-native recorded ExecutionIntent, and
  RuntimeExecutionSubmitReadiness / RuntimeExecutionSubmitAuthorization /
  RuntimeExecutionControlledSubmitPlan /
  RuntimeExecutionControlledSubmitPreflight /
  RuntimeExecutionControlledSubmitResult /
  RuntimeExecutionAttemptReservationPreview /
  RuntimeExecutionAttemptReservation /
  RuntimeExecutionAttemptMutation /
  RuntimeExecutionProtectionPlanPreview /
  RuntimeExecutionProtectionPlan /
  RuntimeExecutionOrderLifecycleHandoffDraft /
  RuntimeExecutionOrderLifecycleAdapterPreview /
  RuntimeExecutionOrderRegistrationDraftPreview /
  RuntimeExecutionSubmitAdapterPreview /
  RuntimeExecutionSubmitRehearsal are non-submitting bridge layers. They
  may record draft/intent/submit authorization/controlled-submit result/pending
  attempt reservation/attempt mutation/protection plan/OrderLifecycle handoff
  draft audit facts where explicitly scoped, and may preview whether an
  authorized intent is ready for a future controlled submit adapter, or
  aggregate existing previews into one non-mutating rehearsal result.
  Draft and source-native intent audit payloads must preserve candidate entry,
  risk, and protection snapshots.
  The pre-submit FinalGate check uses local active-position facts and must not rely on owner-supplied
  active-position counts as an allow signal. Controlled submit result recording
  must consume that submit-time preflight and record `blocked` if it is not
  ready. The attempt reservation preview may compute attempts/budget before and
  after without mutating state. The pending attempt reservation audit record may
  persist that intent to reserve as `pending_runtime_mutation`, but it must not
  mutate runtime budget, consume an attempt, change ExecutionIntent status,
  create orders, or call exchange. The attempt mutation may apply a pending
  reservation to runtime state by incrementing `attempts_used` and
  `budget_reserved`, but it must not change ExecutionIntent status, create
  orders, call OwnerBoundedExecution, call OrderLifecycle, or call exchange.
  The runtime protection plan preview/record is runtime-native and must not
  reuse one-shot OwnerBounded authorization semantics as hidden execution
  authority, create orders, or create exchange payloads. The submit adapter
  readiness preview may expose missing concrete protection/OrderLifecycle inputs, but it must not mutate runtime budget,
  consume attempts, or change ExecutionIntent status. The OrderLifecycle
  handoff draft may freeze future adapter input facts and
  Order-model-compatible draft snapshots, but it must keep
  `order_lifecycle_adapter_implemented=false`, `order_created=false`,
  `order_lifecycle_called=false`, and `exchange_called=false`. The
  OrderLifecycle adapter preview may verify those facts, but it must keep
  `local_order_registration_enabled=false`,
  `local_order_registration_executed=false`, `order_created=false`,
  `order_lifecycle_called=false`, and `exchange_called=false`. The typed local
  order registration draft preview may validate entry/protection registration
  draft facts, but it must keep `order_objects_constructed=false`,
  `local_order_registration_executed=false`, `order_created=false`,
  `order_lifecycle_called=false`, and `exchange_called=false`. The submit adapter
  rehearsal may summarize readiness and blockers across these gates, but it
  must not record reservations, apply attempt mutations, record protection
  plans, record OrderLifecycle handoff drafts, or call order/exchange services.
  The submit adapter boundary can reach dry-run readiness, but real order
  placement remains disabled until a separate OrderLifecycle adapter enablement
  gate; it must not call OwnerBoundedExecution, call OrderLifecycle, submit
  orders, or call exchange.
- Documentation work must not run the project or call the exchange unless the
  active task explicitly includes bounded read-only verification.
- Real live trading / real-funds order placement requires separate explicit
  Owner authorization for each action.
- Budgeted small losses can be acceptable under Owner-approved experimental
  risk capital. System failure is budget breach, runaway behavior, missing
  auditability, boundary expansion, or unauthorized exchange write.
- Experimental runtime profile proposals can suggest small-capital boundaries
  for Owner/Codex review, but they are not confirmed runtime profiles, not
  StrategyRuntimeInstance records, not live-profile changes, not submit
  authorization, and not exchange/order authority.
- Promotion confirmation records may store an accepted profile proposal
  snapshot as structured audit evidence. That snapshot is not a live config
  mutation, not a runtime mutation, and not submit authorization.
- Risk control targets loss of control, not every losing trade. Runtime safety
  must bound max single-attempt loss, max attempts, max active positions,
  notional, leverage, duplicate submits, stale account facts, missing
  protection, and unauditable orders.
- Leverage must not expand the loss budget. It may be used only when loss,
  notional, leverage, margin usage, liquidation distance, active-position,
  account-fact, and protection checks all pass together. Runtime risk and
  FinalGate must treat leverage as an amplifier of uncontrolled-loss risk, not
  as permission to increase `max_loss_budget` or skip hard stops.

---

## 2. Execution Paths

| Path | Current Meaning | Status |
| ---- | --------------- | ------ |
| SignalPipeline -> ExecutionOrchestrator | Legacy real-time signal path | Legacy path; not connected to BRC StrategyFamily chain |
| OwnerTrialFlow -> OwnerBoundedExecution | One-shot Owner-authorized trade execution | Active; current primary execution path |
| TrialBinding + confirmed RuntimeProfileProposal -> StrategyRuntimeInstance draft | Shadow runtime boundary materialization | Active in local working tree; creates only a shadow runtime draft with execution_enabled=false / shadow_mode=true; no candidate, intent, order, OrderLifecycle call, or exchange call |
| StrategyRuntimeInstance shadow lifecycle API | Shadow status control | Active in local working tree; can activate/pause/revoke shadow runtime status only; execution_enabled remains false, shadow_mode remains true, and no candidate/intent/order/exchange path is invoked |
| StrategyRuntimeInstance -> SignalEvaluation -> OrderCandidate -> Runtime FinalGate preview | Runtime governance shadow / dry-run inspection | Active in local working tree; non-executable; not deployed; includes max-loss-first budget checks plus conjunctive max leverage / max margin / stop-vs-liquidation buffer checks when those runtime/candidate facts are present or required |
| RuntimeExecutionPlan -> RuntimeExecutionIntentDraft -> RuntimeExecutionIntent adapter preview -> ExecutionIntent(recorded) -> SubmitReadiness preview -> SubmitAuthorization(recorded) -> ControlledSubmitPlan preview -> SubmitPreflight preview -> ControlledSubmitResult(default-disabled) -> AttemptReservationPreview -> AttemptReservation(recorded pending mutation) -> AttemptMutation(applied/blocked) -> ProtectionPlanPreview -> ProtectionPlan(recorded) -> OrderLifecycleHandoffDraft(recorded) -> OrderLifecycleAdapterPreview -> SubmitAdapterPreview -> SubmitRehearsal aggregate | Non-submitting bridge toward future execution | Active in local working tree; not deployed; records audit intent, Owner submit authorization, controlled-submit preview, submit-time FinalGate preflight, disabled/blocked/not-implemented adapter result, non-mutating attempt/budget readiness, pending reservation audit fact, controlled runtime attempt/budget mutation fact, runtime-native protection readiness/record, runtime OrderLifecycle handoff draft, non-executing local order registration gate, non-executing adapter readiness, and non-mutating rehearsal aggregation only; result consumes submit-time preflight before any adapter boundary status |
| Dev/test controlled paths | Testnet rehearsal and controlled testing | Active for scoped verification; no real funds |
| Scripts direct exchange paths | Research / admin scripts | Not integrated; untracked |
| Readmodel / preview paths | CandidateAction, BudgetedAutonomy, policy evaluation | Read-only; not executable |

---

## 3. Hard Red Lines

The following are prohibited unless Owner explicitly authorizes a specific task:

- Order placement (any exchange write)
- Order cancel / close / replace
- Exchange connection for live operations
- Database mutation (beyond what task card allows)
- Runtime server start
- Script execution against exchange
- Secret output (API keys, tokens, credentials, private keys, DB URLs)
- Withdrawal or transfer
- Strategy self-elevation
- Operation Layer bypass
- FinalGate bypass
- Unscoped symbol / side / leverage / notional expansion

---

## 4. Readmodel / Metadata / Execution Distinction

| Component | Classification | Basis |
| --------- | -------------- | ----- |
| CandidateAction | readmodel | No executable path in tracked code; display and policy evaluation only |
| BudgetedAutonomy | readmodel / design-only | `auto_within_budget_enabled=False`, `auto_execution_enabled=False` (hardcoded) |
| Operation Layer metadata steps | metadata | Not runtime execution unless code creates an executable object |
| TrialTradeIntent | non-executable evidence | Evidence record, not an execution trigger |
| StrategyFamilyVersion | metadata | Strategy specification document; not bound to executable code |
| AdmissionDecision | metadata | Classification and evidence; not an execution gate |
| StrategyRuntimeInstance | shadow governance | Runtime identity and boundaries; execution_enabled=false / shadow_mode=true in current code, including drafts created from confirmed profile proposals |
| ExperimentalRuntimeProfileProposal | preview / proposal | Reviewable 30U small-capital boundary proposal only; not a confirmed runtime profile, runtime record, ExecutionIntent, order, or exchange authority |
| SignalEvaluation | shadow governance | Per-runtime signal evaluation record; not an order and not an execution intent |
| OrderCandidate | shadow governance | Pre-authorization candidate; candidate_executable=false and not_execution_intent=true |
| RuntimeFinalGatePreview | dry-run inspection | Runtime-aware checks only; no mutation, no order, no exchange call |

If code changes create executable paths for any of these, reclassify them.

---

## 5. FinalGate Meaning

- FinalGate is required before any execution.
- FinalGate preview / dry-run is not execution.
- Passing FinalGate does not automatically place orders; the Operation Layer
  must route the action.
- FinalGate should verify: Owner authorization, environment, account,
  symbol, side, quantity, leverage, budget, attempts, active exposure,
  margin usage, liquidation distance versus hard stop with buffer, open
  orders, fresh account facts, reconciliation, market rules, protection plan,
  GKS/runtime guard state, and Operation Layer path.
- Strategy evidence weakness is a warning, not a FinalGate hard blocker,
  after Owner acknowledgement.
- Runtime execution must not rely on owner/user-supplied active position counts
  as an allow signal. Active position facts must come from trusted local
  projection / reconciliation / account-fact sources; unavailable or stale
  facts must block execution.
- Runtime budget checks must distinguish exposure from loss budget:
  `max_notional_per_attempt` checks candidate notional, while runtime budget
  remaining prefers concrete max-loss evidence and falls back to notional only
  when loss-budget evidence is missing.
- Runtime leverage checks must be conjunctive, not substitutive:
  `max_loss_reference`, intended notional, proposed leverage, margin required,
  liquidation buffer, and protection readiness must all pass. Passing one of
  those checks must never compensate for failing another.

Before the first real runtime submit, the following must be explicitly
confirmed:

- symbol, side, max_notional_per_attempt, max_attempts, max_loss_budget,
  max_leverage, max margin usage / max_margin_per_attempt, liquidation buffer
  requirement, and max_active_positions;
- budget reservation basis: prefer concrete max-loss evidence for
  `budget_reserved`, and use notional only as a conservative fallback when
  loss-budget evidence is missing;
- the runtime confirmation mode. The target mode for the isolated experimental
  subaccount is budget/runtime-bounded automatic attempts, not
  Owner-confirm-each-entry, after the runtime/profile boundaries are confirmed;
- when an attempt is consumed;
- when budget reservation is released or confirmed consumed;
- how protection order creation failure is handled;
- how duplicate submit is blocked and audited;
- active position / account fact source and stale-fact behavior;
- deployment readiness, including whether the path is still local-only or tokyo
  has been verified.

BRF / short-side runtime profiles must be more conservative than long-only CPM
profiles until explicitly upgraded: lower leverage, smaller notional, mandatory
hard stop, stricter max active positions, and confirmed runtime-bounded
automatic attempts rather than per-entry Owner confirmation.

---

## 6. Agent Documentation Safety

When doing documentation / analysis work:

- Do not run the project, tests, or scripts.
- Do not connect to exchange, database, Redis, WebSocket, or external services.
- Do not output any secrets or secret-adjacent information.
- Use only read-only commands (ls, find, grep, cat, git status, git diff).
- Changes must be limited to explicitly allowed files in the task card.
