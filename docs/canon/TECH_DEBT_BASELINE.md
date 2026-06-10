---
title: TECH_DEBT_BASELINE
status: CURRENT_CANON
authority: owner-semantic-audit + code-verification
last_verified: 2026-06-10
source_of_truth:
  - docs/canon/PROJECT_BASELINE_CURRENT.md
  - docs/canon/BRC_TARGET_SEMANTICS.md
  - owner semantic audit 2026-06-09
---

# Technical Debt Baseline

This document classifies known technical debt in the BRC project.

---

## 1. Debt Classification

| Level | Name | Meaning |
| ----- | ---- | ------- |
| S0 | Target semantic debt | Current code semantics diverge from target architecture |
| S1 | Audit / execution semantic debt | Gaps in audit trail, execution semantics, or strategy integration |
| S2 | Maintainability / product interpretation debt | Naming confusion, large files, agent instruction drift |
| S3 | Cleanup debt | Low-priority cleanup, dead code, documentation |

---

## 2. Current S0 Debt

| Debt | Current Code Reality | Target Semantics | Notes |
| ---- | -------------------- | ---------------- | ----- |
| Owner authorizes trade vs runtime instance | Owner authorizes single trade via BoundedLiveTrialAuthorization | Owner should authorize bounded StrategyRuntimeInstance | Core semantic gap |
| StrategyFamilyVersion not executable | Strategy specification document, not bound to strategy implementation | Should be versioned executable strategy definition | Requires strategy runtime infrastructure |
| Strategy semantics partially bound locally | CPM / BRF / RMR / FCO are now identified as initial reference/backlog candidates, and a local B0 pure model, context builder, trusted runtime fact overlay, promotion gate, shadow binding service, plus non-executing runtime planning bridge defines StrategyImplementationBinding, RequiredFacts, StrategyEvaluationContext, EntryPolicy, ProtectionPolicy, ExitPolicy, right-tail review metrics, and Owner/Codex promotion blockers; it can map StrategyFamilySignalInput / StrategyFamilySignalOutput / optional StrategyRuntimeInstance snapshots into RequiredFacts, replace caller-provided account/position/market allow facts with trusted read-only overlays when configured, classify RMR closed-candle regime evidence, evaluate BRF closed-candle bear-rally-failure evidence with explicit short-squeeze facts, route raw CPM/BRF signal inputs through RuntimeStrategySignalEvaluationService, create semantically bound shadow OrderCandidates with entry / stop / TP1 1R partial / runner metadata, and reach RuntimeExecutionPlan / RuntimeExecutionIntentDraft; runtime planning now reads StrategySemantics RequiredFacts to require trusted funding/OI/crowding overlays when required; Binance USD-M public/read-only derivative fact reader infrastructure exists for funding/OI/crowding; Trading Console has an internal service factory, explicit opt-in public market fact hook, operator-auth non-executing shadow-plan POST for one signal input, and operator-auth manual scheduled-observation run POST; an explicit non-executing scheduler handoff and local CLI opt-in path can call the shadow planner only after READY_FOR_NON_EXECUTING_PLANNER, allow_shadow_candidate_creation=true, and a unique ACTIVE shadow runtime resolved from StrategyRuntimeInstanceService by StrategyRuntimeObservationResolver; a local in-memory rehearsal verifier now proves the real CPM scheduled-observation-to-shadow-candidate path without PG, exchange, ExecutionIntent, order, or OrderLifecycle calls; runtime promotion gate now separately blocks missing max-loss, notional, leverage, margin, liquidation-buffer, protection-readiness, stale-fact, account-fact, active-position, attempt/budget, BRF short-profile, and first-real-submit confirmations; runtime safety readiness now inspects concrete runtime boundary facts and reports which confirmations are still required, though Owner/Codex still must supply real confirmation values before promotion | Controlled runtime execution should be gated by Strategy Semantics / Entry-Exit Policy Binding | B0/Sprint 7 gate before real OrderLifecycle adapter or runtime submit |
| TrialBinding is not runtime instance | Audit binding record; StrategyRuntimeInstance now exists separately and can be Owner/Codex-gated from shadow into live-runtime flags locally | Should bind admitted strategy to running instance | Runtime identity exists, but executable submit integration is not complete |
| Admission does not create executable runtime | Admission pass can support shadow runtime draft/backbone work; live-runtime enablement now has a separate local mutation gate and 065 persistence support, but admission alone does not authorize execution | Admission should feed bounded StrategyRuntimeInstance governance | Runtime execution submit remains future work |

---

## 3. Current S1 Debt

| Debt | Impact | Notes |
| ---- | ------ | ----- |
| EntryPolicy / ExitPolicy not connected to BRC execution | Strategy exit decisions are ad-hoc, not part of strategy semantics | StrategyContractV2 is a candidate asset |
| RequiredFacts / freshness / missing-fact behavior need runtime source integration | Local B0 semantics declare and test missing/stale behavior, the local context builder maps existing signal/runtime snapshots into RequiredFacts, and the trusted runtime fact overlay can fail closed on unavailable account/position sources or missing/stale trusted funding/OI/crowding facts; runtime planning now automatically requires a trusted market-fact overlay for strategy-required funding/OI/crowding facts; Trading Console internal assembly can inject PG positions, cached account facts, and an explicitly enabled Binance public derivative market fact source; scheduler-level readiness plus explicit operator-auth non-executing handoffs can invoke shadow planning for either one signal input or one manual scheduled-observation run; the scheduled read-only observation runner now persists full signal input snapshots and can optionally hand observed signals to the non-executing shadow planner only after StrategyRuntimeObservationResolver resolves a unique ACTIVE shadow runtime from StrategyRuntimeInstanceService; the local CLI has an explicit `--shadow-plan` wiring path, but missing trusted account facts still block candidate planning; Tokyo autonomous triggering and deployment-backed FCO coverage are not fully wired | Each StrategyImplementation must declare required_facts, optional_facts, freshness_requirement, and missing_fact_behavior |
| ProtectionPolicy and ExitPolicy are not yet integrated into execution binding | Local B0 semantics separates ProtectionPolicy and ExitPolicy, but real execution/protection handoff still needs controlled integration | ProtectionPolicy must bound loss; ExitPolicy must express profit-taking, runner, trailing, invalidation, time-stop, and lifecycle exits |
| Short-side BRF profile not yet fully confirmed | Doing short-side price action with long-side defaults would understate squeeze risk; the promotion gate blocks BRF promotion until a conservative short-side profile is confirmed. A non-executing 30U experimental profile proposal can now suggest a conservative BRF/short envelope, but it is not Owner/Codex confirmation or live-profile enablement | BRF must start with lower leverage, smaller notional, mandatory hard stop, strict max_active_positions, and runtime-bounded automatic attempts after profile confirmation rather than Owner-confirm-each-entry |
| Leverage / margin / liquidation checks not fully productized | Runtime FinalGate preview now carries max margin / liquidation-buffer runtime fields and candidate margin / liquidation facts, blocks leveraged candidates missing those facts, and blocks margin excess or insufficient stop-vs-liquidation buffer without creating execution authority; the promotion gate blocks runtime promotion until max-loss, notional, active-position, leverage, margin usage, liquidation-buffer, protection-readiness, and stale-fact behavior are explicitly confirmed; runtime safety readiness now checks whether those boundary facts are present on the runtime before confirmation; real runtime execution still needs live source orchestration, profile templates, account/symbol margin facts, and submit adapter integration | Leverage must not expand loss budget; FinalGate should require loss budget, notional, leverage, margin usage, liquidation buffer, and protection readiness to pass together |
| Runtime profile proposals are not confirmed runtime profiles | A pure ExperimentalRuntimeProfileProposal model and Trading Console preview endpoint now convert the 30U small-capital objective into reviewable boundary values and confirmation keys; promotion confirmation records can freeze an accepted proposal snapshot as structured evidence. These records do not create StrategyRuntimeInstance records, mutate live config, authorize submit, or call exchange | Owner/Codex must still confirm profile values before runtime creation/promotion and before any first real submit |
| RMR classifier could become an over-strong filter | Local RMR classifier now emits closed-candle regime evidence with `hard_filter=false` and `not_execution_authority=true`; live reader orchestration and confidence/freshness productization still need care so it cannot silently suppress strategies | RMR starts as regime evidence / observe-only downgrade input, not execution authority |
| attempt / budget confirmation partially specified locally | Runtime reservation/mutation now prefers concrete max-loss evidence for `budget_reserved` and falls back to notional only when loss-budget evidence is missing; the promotion gate blocks runtime promotion and first-real-submit review until max-loss, notional, leverage, margin, liquidation-buffer, protection readiness, stale-fact behavior, attempt, reservation, release/consume, duplicate-submit, protection-failure, account facts, active-position facts, and deployment confirmations are present | First real submit must confirm attempt consumption, budget reservation/release, protection failure handling, duplicate-submit blocking, account facts, active-position facts, stale-fact behavior, and deployment readiness |
| Authorization is single-use | Cannot express multi-attempt strategy runtime | Current BoundedLiveTrialAuthorization is one-shot |
| runtime semantic IDs only partially propagated | Review cannot yet trace full runtime chain end-to-end | Nullable IDs and source-native recorded ExecutionIntent audit exist in the local working tree; order, review, and position records now carry local semantic IDs, but automated source orchestration from order/position/exchange facts into review packets remains incomplete |
| SignalPipeline and BRC StrategyFamily are dual-track | Legacy signal system not connected as an executable StrategyRuntimeInstance trigger | SignalPipeline is candidate for SignalEvaluation engine |
| Runtime-aware FinalGate has preview-only fact gaps | Runtime execution cannot safely rely on user-supplied active position counts; local signal-to-draft bridge and trusted fact overlay block when local active-position facts are unavailable, but live/runtime source orchestration is not yet productized | Active position facts must come from local projection/reconciliation or block when unavailable/stale |
| Recorded runtime ExecutionIntent is not live-submit integrated | In tracked code, runtime candidate can become an audit intent, Owner submit authorization, controlled-submit plan, submit-time FinalGate preflight, preflight-gated disabled/blocked/order-lifecycle-disabled result, non-mutating attempt reservation preview, pending attempt reservation audit record, controlled runtime attempt mutation record, runtime-native protection plan preview/record, runtime OrderLifecycle handoff draft record, non-executing OrderLifecycle adapter preview gate, typed local order registration draft preview, default-disabled OrderLifecycle adapter result skeleton, dry-run-only submit adapter preview, and non-mutating submit rehearsal aggregate; deployment state must be verified from the current release manifest and postdeploy reports, not inferred from this row. A local pre-live packet verifier proves the technical non-executing rehearsal can reach the dry-run submit adapter boundary while StrategyRuntimeLiveEnablementPreview separately blocks live-runtime enablement on missing current-head deployment, Owner live-runtime enablement authorization, Owner real-submit authorization, forbidden execution flags, or a missing dry-run submit adapter; StrategyRuntimeLiveEnablementMutation plus migration 065 can now flip only runtime governance flags after a ready preview and explicit authorization IDs, migration 066 lets controlled-submit audit record the OrderLifecycle-disabled stop gate, migration 067 aligns the historical orders table status check with local `Order(status=CREATED)` registration readiness, migration 068 adds a PG-backed adapter-result table whose unique `authorization_id` is the persistent duplicate-submit lock for future local registration, and migration 069 lets adapter-result rows persist fail-closed local registration failures when entry/protection registration only partially completes. The adapter result skeleton can construct local `Order(status=CREATED)` objects from typed registration drafts and call `OrderLifecycleService.register_created_order` only when adapter enablement, local registration enablement, a READY first-real-submit local-registration gate, and the persistent lock are present; duplicate calls replay the stored adapter result, including failed partial-registration results. The post-registration audit state is the adapter result status `registered_created_local_orders` or fail-closed `local_order_registration_failed`; source-native `ExecutionIntent` remains `recorded` until a later exchange-submit stage explicitly designs otherwise. By default it remains disabled, and it still cannot submit an order, call exchange, change ExecutionIntent status, or provide live runtime authority | This is intentional until exchange-stage ExecutionIntent/order linkage, explicit real-submit enablement, and reconciliation closure are explicitly designed |
| BRC TP/SL exit projection may be incomplete | Protection logic exists but may not cover all edge cases | Needs audit when strategy runtime path is built |
| Review lacks full right-tail and capital-base productization | Local domain/application review can classify Owner manual withdrawal, manual profit extraction, capital injection, and capital-base reset against read-only account-equity facts without creating withdrawal/transfer/order/exchange instructions. Productized slices now persist Owner capital adjustment facts and account-equity/capital-base baseline snapshots, expose BRC record/list APIs for both, let Trading Console `review-state` / `owner-capital-review` use the latest baseline snapshot for missing previous-equity / starting-base inputs, compute/display right-tail trade-path metrics from explicit `live_lifecycle_review.metadata.right_tail_trade_path` facts via `review-state` / `right-tail-review`, generate non-executing closed-trade semantic review packets from lifecycle review records, and propagate local runtime semantic IDs through position projection/readmodels. Automatic scheduled baseline capture and automated order/position/exchange-to-review source orchestration remain incomplete | Review should track MFE/MAE, payoff asymmetry, tail wins, bounded max loss, manual withdrawals, capital base adjustments, baseline snapshots, and unresolved equity deltas separately from strategy performance |

---

## 4. Current S2 Debt

| Debt | Impact | Notes |
| ---- | ------ | ----- |
| Runtime Profile / TrialBinding / Authorization boundary sources unclear | Agent confusion about which authorization source applies | Need clear authority chain doc |
| CandidateAction / BudgetedAutonomy naming suggests execution | Agents may treat readmodel as executable | Naming is S2 debt; classification is in canon |
| Large API / readmodel files | Maintainability risk | Not blocking current work |
| Old docs / agent instructions can mislead agents | Stale instructions in docs/ops/ and .claude/ | Phase 3c will quarantine high-risk agent instructions |
| docs/ops/ ~155 files with mixed authority | Hard to determine which are current | Canon establishment (this phase) addresses this |

---

## 5. Non-goals

These are explicitly not current work:

- Do not delete one-shot execution path (OwnerBoundedExecutionService).
- Do not delete SignalPipeline.
- Do not delete Admission metadata chain.
- Do not large-refactor OrderLifecycle.
- Do not batch-delete historical docs.
- Do not promote shadow StrategyRuntimeInstance / SignalEvaluation /
  OrderCandidate records into execution authority without an explicit Codex
  task card and Owner-gated execution boundary.
- Do not design automatic withdrawal, transfer, or fund movement.

These items may become future work when Codex promotes them.
