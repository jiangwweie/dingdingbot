# CLAUDE-TEST-MAP-001 Runtime Path Test Coverage Matrix

Generated: 2026-06-16
Branch: codex/owner-runtime-console-v1
Scope: StrategyGroup runtime-governance pilot path
Method: Read-only source/test scan (rg, find, file reads)

---

## Summary

The runtime path has **11 steps** from StrategyGroup selection through
notification/review. The codebase contains **372 source files** and **297 test
files** (all unit). Coverage is **deep in the middle of the pipeline**
(signal → prepare → FinalGate → submit) but has **gaps at the boundaries**
(admission bootstrap, notification/review, end-to-end product-state
propagation).

| Coverage Level | Steps |
|---|---|
| **Strong** (10+ tests, multiple angles) | RequiredFacts readiness, non-executing prepare, shadow candidate/authorization, FinalGate, Operation Layer submit |
| **Moderate** (5-9 tests) | StrategyGroup selection, armed observation, fresh signal, post-submit finalize |
| **Weak** (<5 tests, narrow scope) | runtime admission, reconciliation/budget settlement, notification/review |

**Key risk**: The admission→observation handoff and the post-settle→notification→review
tail are the least tested segments. A failure in admission bootstrap silently
blocks the entire pipeline; a failure in notification means the Owner never
learns a position closed.

---

## Matrix

### Step 1: StrategyGroup Selection

| Field | Value |
|---|---|
| **Runtime Step** | StrategyGroup selection |
| **Source Files** | `src/application/readmodels/trading_console.py`, `src/interfaces/api_trading_console.py`, `src/application/strategy_group_reviewability.py`, `src/application/strategy_group_forward_review.py` |
| **Existing Tests** | `test_strategygroup_runtime_goal_status.py` (goal status mapping), `test_strategygroup_runtime_pilot_status.py` (pilot status), `test_strategygroup_runtime_product_state_refresh.py` (product state refresh), `test_trading_console_readmodels.py` (readmodel completeness), `test_brc_console_api_surface.py` (console API surface) |
| **Missing Cases** | No test for invalid/unknown StrategyGroup id rejection. No test for StrategyGroup idempotent re-selection after pause→resume. No test for conflict policy (same-symbol same-side merge vs opposite-side block). No test for observe-only vs armed mode selection per handoff batch. |
| **Risk** | MEDIUM — incorrect selection silently routes to wrong observation mode or ignores conflict policy. |
| **Recommended Test File** | `test_strategy_group_selection_conflict_policy.py` |
| **Priority** | P2 |

### Step 2: Runtime Admission

| Field | Value |
|---|---|
| **Runtime Step** | runtime admission |
| **Source Files** | `src/application/brc_admission_service.py`, `src/application/brc_admission_risk_capital.py`, `src/application/production_strategy_family_admission.py`, `src/application/strategy_runtime_service.py`, `src/application/strategy_runtime_promotion_gate_service.py`, `src/application/strategy_runtime_fact_overlay_service.py`, `src/application/strategy_runtime_safety_readiness_service.py`, `src/application/strategy_trial_readiness.py`, `src/domain/brc_admission.py`, `src/domain/strategy_runtime.py`, `src/domain/strategy_runtime_promotion_gate.py`, `src/domain/strategy_runtime_safety_readiness.py`, `src/infrastructure/pg_strategy_runtime_repository.py`, `src/infrastructure/pg_strategy_family_registry_repository.py`, `src/infrastructure/pg_strategy_runtime_promotion_confirmation_repository.py`, `scripts/bootstrap_strategygroup_runtime_pilot.py` |
| **Existing Tests** | `test_brc_admission_phase1.py`, `test_brc_admission_api.py`, `test_b0_strategy_runtime_promotion_gate.py`, `test_b0_strategy_runtime_promotion_gate_service.py`, `test_b0_strategy_runtime_fact_overlay.py`, `test_strategy_runtime_safety_readiness.py`, `test_strategy_runtime_backbone.py`, `test_strategy_runtime_live_enablement.py`, `test_strategy_runtime_promotion_confirmation_api.py`, `test_strategy_runtime_promotion_confirmation_repository.py`, `test_strategy_trial_readiness.py`, `test_pg_strategy_family_registry_repository.py`, `test_bootstrap_strategygroup_runtime_pilot.py`, `test_production_strategy_family_admission.py`, `test_execute_runtime_profile_apply_plan.py` |
| **Missing Cases** | No test for admission with stale RequiredFacts (should block). No test for admission risk-capital cap enforcement. No test for admission when StrategyRuntimeInstance is already ACTIVE (duplicate guard). No test for promotion gate rejecting when safety readiness fails. No test for bootstrap script plan-only vs --execute mode boundary. |
| **Risk** | HIGH — admission is the gateway to the entire runtime path. A broken admission gate either blocks all automation or lets unsafe states through. |
| **Recommended Test File** | `test_admission_gate_stale_facts_and_duplicate_guard.py` |
| **Priority** | P1 |

### Step 3: Armed Observation

| Field | Value |
|---|---|
| **Runtime Step** | armed observation |
| **Source Files** | `src/application/strategy_group_readonly_observation_scheduler.py`, `src/application/strategy_group_live_readonly_observation.py`, `src/application/strategy_group_observation_case_queue.py`, `src/domain/strategy_family_signal.py`, `src/infrastructure/pg_strategy_group_observation_repository.py` |
| **Existing Tests** | `test_strategy_group_observation_script.py`, `test_strategy_group_readonly_preview_script.py`, `test_strategy_group_live_facts_readiness_packet.py`, `test_strategy_group_live_readonly_observation.py`, `test_strategy_signal_v2_observe_bootstrap.py`, `test_strategy_signal_v2_observe_writer.py`, `test_signal_pipeline_strategy_signal_v2_observe_wiring.py`, `test_runtime_active_observation_loop.py`, `test_runtime_active_observation_monitor.py`, `test_runtime_active_observation_status.py`, `test_runtime_active_observation_supervisor.py`, `test_runtime_active_observation_followup.py` |
| **Missing Cases** | No test for armed_observation → observe_only mode downgrade on mark/funding abnormality. No test for cadence enforcement (5m/15m/60m per StrategyGroup). No test for observation case queue overflow or dedup. No test for observation pause/resume propagation from Owner. |
| **Risk** | MEDIUM — broken observation means no fresh signals reach the pipeline. Silent failure = automation idle with no Owner notification. |
| **Recommended Test File** | `test_observation_mode_downgrade_and_cadence_enforcement.py` |
| **Priority** | P2 |

### Step 4: Fresh Strategy Signal

| Field | Value |
|---|---|
| **Runtime Step** | fresh strategy signal |
| **Source Files** | `src/application/runtime_strategy_signal_evaluation_service.py`, `src/application/runtime_strategy_signal_planning_service.py`, `src/application/runtime_strategy_signal_intent_draft_source_service.py`, `src/application/runtime_strategy_signal_scheduler_assembly.py`, `src/application/runtime_strategy_signal_scheduler_planning_service.py`, `src/application/signal_evaluation_shadow_service.py`, `src/application/signal_pipeline.py`, `src/application/signal_tracker.py`, `src/application/strategy_semantics_shadow_binding_service.py`, `src/application/strategy_evaluation_context_builder.py`, `src/application/pattern_strategy_signal_adapter.py`, `src/domain/signal_evaluation.py`, `src/domain/strategy_semantics.py`, `src/domain/strategy_candidate_semantics.py` |
| **Existing Tests** | `test_b0_runtime_strategy_signal_planning.py`, `test_b0_runtime_strategy_signal_scheduler_assembly.py`, `test_b0_strategy_evaluation_context_builder.py`, `test_b0_strategy_semantics_binding.py`, `test_strategy_family_signal_contract.py`, `test_runtime_strategy_signal_evaluation_service.py`, `test_runtime_strategy_signal_intent_draft_source.py`, `test_runtime_strategy_signal_watch_packet.py`, `test_runtime_strategy_signal_input_packet_script.py`, `test_runtime_fresh_signal_readiness_fixture.py`, `test_runtime_fresh_signal_readiness_bridge.py`, `test_runtime_fresh_signal_prepare_loop.py`, `test_runtime_live_signal_routing_packet.py`, `test_runtime_live_strategy_signal_selector.py`, `test_runtime_live_signal_shadow_planning_bridge.py`, `test_runtime_live_signal_operator_cycle.py`, `test_runtime_live_signal_operator_supervisor.py`, `test_pattern_strategy_signal_adapter.py`, `test_signal_pipeline_strategy_signal_v2_observe_wiring.py` |
| **Missing Cases** | No test for signal staleness beyond business validity window (15-30m). No test for signal conflict (same-symbol opposite-side from active position). No test for signal evaluator returning no-signal vs conflicting-signal distinction. No test for draft source readiness when intent draft repo is empty. |
| **Risk** | MEDIUM — stale or conflicting signals that pass through create downstream candidate/candidate-preparation failures or, worse, reach FinalGate. |
| **Recommended Test File** | `test_fresh_signal_staleness_and_conflict_detection.py` |
| **Priority** | P2 |

### Step 5: RequiredFacts Readiness

| Field | Value |
|---|---|
| **Runtime Step** | RequiredFacts readiness |
| **Source Files** | `src/application/runtime_executable_submit_readiness_service.py`, `src/application/runtime_early_readiness_fact_collector.py`, `src/application/runtime_execution_trusted_submit_facts_service.py`, `src/application/runtime_execution_trusted_submit_fact_readers.py`, `src/application/runtime_persisted_draft_source_readiness_bridge_service.py`, `src/application/strategy_runtime_fact_overlay_service.py`, `src/application/binance_usdt_futures_account_facts.py`, `src/application/strategy_trial_preflight_facts.py`, `src/domain/runtime_executable_submit_readiness.py`, `src/domain/runtime_execution_trusted_submit_facts.py`, `src/infrastructure/binance_usdm_derivative_market_fact_source.py` |
| **Existing Tests** | `test_runtime_strategy_required_facts_readiness_packet.py`, `test_runtime_executable_submit_readiness.py`, `test_runtime_executable_submit_readiness_service_api.py`, `test_runtime_executable_submit_readiness_api_flow.py`, `test_runtime_executable_submit_readiness_from_reports.py`, `test_runtime_early_readiness_fact_collector.py`, `test_runtime_execution_trusted_submit_facts.py`, `test_runtime_execution_trusted_submit_facts_api.py`, `test_runtime_execution_trusted_submit_facts_service.py`, `test_runtime_persisted_draft_source_readiness_bridge.py`, `test_runtime_fresh_attempt_readiness_packet.py`, `test_runtime_live_attempt_readiness_packet.py`, `test_runtime_operator_live_fact_packet.py`, `test_runtime_readiness_evidence_source_map.py`, `test_runtime_real_signal_readiness_evidence_resolver.py`, `test_collect_strategy_group_live_facts_readonly.py`, `test_binance_usdm_derivative_market_fact_source.py`, `test_b0_strategy_runtime_fact_overlay.py`, `test_strategy_group_live_facts_readiness_packet.py`, `test_exchange_credential_preflight.py` |
| **Missing Cases** | No test for partial RequiredFacts (e.g. market OK but account stale). No test for RequiredFacts readiness class priority ordering (market→strategy→derivatives→risk→account→exchange). No test for fact freshness timeout per class. No test for exchange fact source returning degraded/partial data. |
| **Risk** | HIGH — RequiredFacts is the single largest gate. Missing or stale facts must block candidate preparation. A false-positive readiness allows unsafe execution. |
| **Recommended Test File** | `test_required_facts_partial_staleness_and_priority_ordering.py` |
| **Priority** | P1 |

### Step 6: Non-Executing Prepare Records

| Field | Value |
|---|---|
| **Runtime Step** | non-executing prepare records |
| **Source Files** | `src/application/runtime_next_attempt_strategy_planning_service.py`, `src/application/runtime_execution_planning_service.py`, `src/application/runtime_execution_intent_adapter_service.py`, `src/application/runtime_strategy_signal_intent_draft_source_service.py`, `src/application/runtime_execution_first_real_submit_evidence_preparation_service.py`, `src/domain/runtime_execution_intent_adapter.py`, `src/domain/runtime_execution_intent_local_order_binding.py`, `src/domain/runtime_execution_intent_local_order_linkage.py`, `src/domain/runtime_execution_order_registration_draft.py`, `src/domain/runtime_execution_plan.py`, `src/infrastructure/pg_runtime_execution_intent_draft_repository.py` |
| **Existing Tests** | `test_runtime_next_attempt_strategy_planning.py`, `test_runtime_next_attempt_strategy_plan_api_flow.py`, `test_runtime_next_attempt_gate_strategy_planning_verifier.py`, `test_runtime_next_attempt_observation_api_prepare_flow.py`, `test_runtime_observation_api_prepare_ready_rehearsal.py`, `test_runtime_observation_operator_packet.py`, `test_runtime_observation_wakeup_packet.py`, `test_runtime_strategy_signal_intent_draft_source.py`, `test_runtime_persisted_draft_source_readiness_bridge.py`, `test_runtime_ready_signal_prepare_handoff_contract.py`, `test_runtime_ready_signal_shadow_planning_contract_fixture.py`, `test_runtime_real_signal_pipeline_fixture.py`, `test_runtime_execution_first_real_submit_enablement_packet.py`, `test_runtime_execution_first_real_submit_evidence_preparation_service.py` (if exists), `test_order_candidate_usage_readmodel.py` |
| **Missing Cases** | No test that prepare records are truly non-mutating (no order placed, no exchange call). No test for prepare record cleanup on StrategyGroup pause/kill. No test for prepare conflict when two signals arrive for same symbol simultaneously. No test for prepare record TTL expiry. |
| **Risk** | HIGH — if prepare records accidentally trigger execution, real funds are at risk. The non-executing invariant is the most critical safety boundary in this step. |
| **Recommended Test File** | `test_prepare_record_non_mutating_invariant_and_cleanup.py` |
| **Priority** | P0 |

### Step 7: Shadow Candidate / Runtime Grant / Authorization Evidence

| Field | Value |
|---|---|
| **Runtime Step** | shadow candidate / runtime grant / authorization evidence |
| **Source Files** | `src/application/runtime_fresh_submit_authorization_resolution_service.py`, `src/application/runtime_fresh_submit_authorization_binding_service.py`, `src/application/runtime_official_submit_handoff_service.py`, `src/application/runtime_execution_first_real_submit_enablement_packet_service.py`, `src/application/runtime_execution_first_real_submit_evidence_preparation_service.py`, `src/application/runtime_final_gate_preview_service.py`, `src/application/action_spec_final_gate_adapter.py`, `src/application/candidate_action_product_loop.py`, `src/application/multi_carrier_budget_authorization.py`, `src/domain/runtime_fresh_submit_authorization_binding.py`, `src/domain/runtime_fresh_submit_authorization_resolution.py`, `src/domain/runtime_final_gate_preview.py`, `src/domain/runtime_execution_submit_authorization.py`, `src/domain/runtime_execution_first_real_submit_enablement_packet.py`, `src/domain/runtime_execution_first_real_submit_evidence_preparation.py`, `src/domain/runtime_execution_submit_prerequisite_evidence_proof.py`, `src/domain/runtime_official_submit_handoff.py`, `src/infrastructure/pg_runtime_execution_submit_authorization_repository.py`, `src/infrastructure/pg_runtime_execution_exchange_submit_action_authorization_repository.py`, `src/infrastructure/pg_runtime_execution_local_registration_action_authorization_repository.py` |
| **Existing Tests** | `test_runtime_fresh_submit_authorization_binding.py`, `test_runtime_fresh_submit_authorization_resolution.py`, `test_runtime_fresh_authorization_official_handoff_fixture.py`, `test_runtime_official_submit_handoff.py`, `test_runtime_official_submit_handoff_api_flow.py`, `test_runtime_official_submit_handoff_from_readiness.py`, `test_runtime_official_submit_handoff_service_api.py`, `test_runtime_official_submit_adapter_preview_proof.py`, `test_runtime_official_submit_disabled_smoke_from_handoff.py`, `test_runtime_official_fresh_candidate_final_gate_preflight_proof.py`, `test_runtime_official_fresh_candidate_runtime_cycle_handoff_proof.py`, `test_runtime_official_evidence_chain_from_binding.py`, `test_runtime_first_real_submit_action_authorization_packet.py`, `test_runtime_first_real_submit_exchange_arm_authorization_packet.py`, `test_runtime_first_real_submit_local_registration_authorization_packet.py`, `test_runtime_first_real_submit_final_review_packet.py`, `test_runtime_first_real_submit_owner_packet.py`, `test_runtime_first_real_submit_archive_namespace.py`, `test_runtime_first_real_submit_api_flow.py`, `test_runtime_execution_first_real_submit_enablement_packet.py`, `test_runtime_ready_shadow_candidate_boundary.py`, `test_runtime_scoped_local_registration_proof_from_evidence.py`, `test_runtime_official_scoped_local_registration_proof.py`, `test_runtime_submit_prerequisite_evidence_repositories.py`, `test_runtime_submit_rehearsal_pre_live_packet.py`, `test_runtime_execution_submit_rehearsal.py`, `test_candidate_action_product_loop.py`, `test_action_spec_final_gate_adapter.py` |
| **Missing Cases** | No test for authorization evidence chain break (missing intermediate record). No test for authorization expiry between prepare and FinalGate. No test for budget authorization rejection when carrier budget exhausted. No test for shadow candidate boundary enforcement (shadow must not reach exchange). |
| **Risk** | HIGH — this is where shadow-path governance meets real-execution intent. A boundary leak here means unauthorized order submission. |
| **Recommended Test File** | `test_shadow_candidate_boundary_and_authorization_expiry.py` |
| **Priority** | P0 |

### Step 8: Action-Time FinalGate

| Field | Value |
|---|---|
| **Runtime Step** | action-time FinalGate |
| **Source Files** | `src/application/action_spec_final_gate_adapter.py`, `src/application/runtime_final_gate_preview_service.py`, `src/application/runtime_execution_planning_service.py`, `src/domain/runtime_final_gate_preview.py`, `src/domain/runtime_executable_submit_readiness.py`, `src/domain/standing_authorization.py`, `src/domain/runtime_execution_controlled_submit.py`, `src/application/budgeted_autonomy.py`, `src/application/budgeted_autonomy_v01.py` |
| **Existing Tests** | `test_generic_final_gate_probe.py`, `test_td4_runtime_final_gate_preview.py`, `test_runtime_official_final_gate_preflight_proof.py`, `test_runtime_official_fresh_candidate_final_gate_preflight_proof.py`, `test_runtime_next_attempt_gate_blocker_classification.py`, `test_runtime_next_attempt_gate_packet_script.py`, `test_runtime_next_attempt_gate_strategy_planning_verifier.py`, `test_runtime_execution_trusted_submit_facts.py`, `test_brc_execution_bypass_hardening.py`, `test_action_spec_final_gate_adapter.py`, `test_runtime_official_submit_action_time_bridge_verifier.py`, `test_runtime_official_flat_next_attempt_end_to_end_proof.py`, `test_runtime_official_next_attempt_strategy_continuation_proof.py`, `test_budgeted_autonomy.py` |
| **Missing Cases** | No test for all 6 gate classes (waiting_for_market, missing_fact, deployment_issue, active_position_resolution, hard_safety_stop, review_only_warning) in a single consolidated test. No test for FinalGate behavior when blocker is resolved mid-cycle. No test for FinalGate with stale authorization evidence. No test for FinalGate bypass attempt detection (hard_safety_stop must never be bypassed). |
| **Risk** | CRITICAL — FinalGate is the last safety barrier before real order submission. Any bypass or misclassification directly risks real funds. |
| **Recommended Test File** | `test_final_gate_all_blocker_classes_and_bypass_detection.py` |
| **Priority** | P0 |

### Step 9: Official Operation Layer Gateway Action

| Field | Value |
|---|---|
| **Runtime Step** | official Operation Layer gateway action |
| **Source Files** | `src/application/brc_operation_layer.py`, `src/application/runtime_official_submit_handoff_service.py`, `src/application/runtime_execution_intent_adapter_service.py`, `src/application/order_lifecycle_service.py`, `src/application/execution_orchestrator.py`, `src/infrastructure/exchange_gateway.py`, `src/infrastructure/pg_brc_operation_repository.py`, `src/domain/runtime_execution_submit_adapter.py`, `src/domain/runtime_execution_exchange_submit_packet.py`, `src/domain/runtime_execution_exchange_submit_enablement.py`, `src/domain/runtime_execution_exchange_submit_action_authorization.py`, `src/domain/runtime_execution_order_lifecycle_handoff.py`, `src/domain/runtime_execution_order_lifecycle_adapter.py` |
| **Existing Tests** | `test_brc_operation_layer.py`, `test_runtime_official_controlled_gateway_action_proof.py`, `test_runtime_official_exchange_submit_boundary_proof.py`, `test_runtime_official_exchange_submit_execution_result_boundary_proof.py`, `test_runtime_order_lifecycle_adapter_result.py`, `test_order_lifecycle_adapter_enablement_packet.py`, `test_order_lifecycle_service_pending_updates.py`, `test_runtime_execution_submit_idempotency.py`, `test_runtime_execution_submit_outcome_review.py`, `test_runtime_execution_protection_failure_policy.py`, `test_td5_runtime_execution_plan.py`, `test_runtime_cycle_executable_submit_handoff.py`, `test_runtime_executable_submit_readiness.py`, `test_runtime_official_submit_handoff_service_api.py` |
| **Missing Cases** | No test for exchange gateway timeout/retry behavior during submit. No test for Operation Layer rejection when exchange returns insufficient margin. No test for duplicate-submit detection at the gateway level. No test for order lifecycle adapter handling partial fill during submit. No test for exchange gateway readiness check before submit. |
| **Risk** | CRITICAL — this is where real money moves. Exchange interaction failures, duplicate submits, or margin rejections need explicit handling. |
| **Recommended Test File** | `test_operation_layer_exchange_failure_and_duplicate_submit.py` |
| **Priority** | P0 |

### Step 10: Post-Submit Finalize / Reconciliation / Budget Settlement

| Field | Value |
|---|---|
| **Runtime Step** | post-submit finalize / reconciliation / budget settlement |
| **Source Files** | `src/application/runtime_post_submit_finalize_service.py`, `src/application/periodic_reconciliation.py`, `src/application/reconciliation.py`, `src/application/reconciliation_lock.py`, `src/application/startup_reconciliation_service.py`, `src/application/runtime_exchange_submit_projection_recovery_service.py`, `src/application/runtime_exchange_close_projection_recovery_service.py`, `src/application/runtime_closed_trade_lifecycle_review_service.py`, `src/application/runtime_closed_trade_review_facts_service.py`, `src/application/runtime_position_exit_plan_service.py`, `src/application/runtime_live_position_monitor_service.py`, `src/domain/runtime_post_submit_finalize.py`, `src/domain/runtime_execution_post_submit_budget_settlement.py`, `src/domain/runtime_execution_exchange_submit_recovery_resolution.py`, `src/domain/runtime_exchange_close_projection_recovery.py`, `src/domain/runtime_closed_trade_review_facts.py`, `src/domain/runtime_live_position_monitor.py`, `src/domain/runtime_position_exit_plan.py`, `src/infrastructure/pg_runtime_execution_post_submit_budget_settlement_repository.py`, `src/infrastructure/pg_reconciliation_read_model_repository.py`, `src/infrastructure/reconciliation_repository.py` |
| **Existing Tests** | `test_runtime_post_submit_finalize.py`, `test_runtime_post_submit_finalize_api_flow.py`, `test_runtime_post_submit_finalize_loop_verifier.py`, `test_runtime_post_submit_finalize_probe.py`, `test_runtime_post_submit_next_attempt_cycle.py`, `test_runtime_official_post_submit_finalize_proof.py`, `test_runtime_closed_trade_lifecycle_review.py`, `test_runtime_closed_trade_review_facts.py`, `test_runtime_closed_trade_review_facts_script.py`, `test_runtime_exchange_submit_projection_recovery.py`, `test_runtime_exchange_submit_recovery_resolution.py`, `test_runtime_exchange_close_projection_recovery.py`, `test_runtime_refresh_reconciliation_read_model.py`, `test_runtime_post_close_followup.py`, `test_runtime_post_close_followup_script.py`, `test_runtime_position_lifecycle_exit_readiness_packet.py`, `test_runtime_live_position_monitor.py`, `test_ls003a_reconciliation_read_model.py`, `test_ls003b_periodic_reconciliation.py`, `test_ls003d_reconciliation_read_model_persistence.py`, `test_startup_reconciliation_service.py`, `test_runtime_active_position_resolution.py`, `test_runtime_active_position_resolution_from_reports.py` |
| **Missing Cases** | No test for budget settlement when order partially fills. No test for reconciliation mismatch detection and recovery flow. No test for post-submit finalize when exchange returns unexpected status. No test for projection recovery when exchange API is temporarily unavailable. No test for closed-trade review facts completeness after finalize. |
| **Risk** | HIGH — incomplete finalize or settlement leaves the system in an inconsistent state. Budget drift accumulates silently. |
| **Recommended Test File** | `test_post_submit_partial_fill_settlement_and_reconciliation_mismatch.py` |
| **Priority** | P1 |

### Step 11: Notification / Review

| Field | Value |
|---|---|
| **Runtime Step** | notification / review |
| **Source Files** | `src/infrastructure/notifier.py`, `src/infrastructure/notifier_feishu.py`, `src/application/llm_event_autopublisher.py`, `src/application/llm_advisory_plane.py`, `src/application/llm_advisory_cards.py`, `src/application/llm_advisory_eval.py`, `src/application/llm_advisory_safety.py`, `src/application/strategy_group_forward_review.py`, `src/application/runtime_closed_trade_lifecycle_review_service.py`, `src/application/runtime_closed_trade_review_facts_service.py`, `src/domain/runtime_closed_trade_review_facts.py`, `src/domain/live_lifecycle_review.py`, `src/domain/forward_outcome_review.py`, `src/domain/right_tail_review.py`, `src/infrastructure/pg_live_lifecycle_review_repository.py`, `src/infrastructure/pg_strategy_group_forward_review_repository.py` |
| **Existing Tests** | `test_runtime_closed_trade_lifecycle_review.py`, `test_runtime_closed_trade_review_facts.py`, `test_runtime_closed_trade_review_facts_script.py`, `test_live_lifecycle_review_repository.py`, `test_right_tail_review.py`, `test_llm_advisory_plane.py`, `test_runtime_semantic_review_packet.py`, `test_runtime_coverage_review_packet.py` |
| **Missing Cases** | No test for Feishu notification delivery on position close. No test for notification suppression when state does not materially change. No test for review outcome propagation to StrategyGroup status. No test for notification on reconciliation mismatch. No test for notification on protection health regression. No test for forward review facts completeness. No test for review decision (保留/调整/暂停/停用) persistence. |
| **Risk** | MEDIUM — broken notifications mean the Owner operates blind. Silent failures here don't lose money but destroy the supervision model. |
| **Recommended Test File** | `test_notification_delivery_and_review_outcome_propagation.py` |
| **Priority** | P1 |

---

## Fast Unit Tests Candidates

These tests are pure domain logic, no I/O, no DB, no exchange — fast to write
and fast to run:

| Test | Runtime Step | Why Fast |
|---|---|---|
| `test_strategy_runtime_status_transition_rules` | Admission | Pure enum transition validation |
| `test_conflict_policy_same_symbol_same_side_merge` | Selection | Pure policy logic |
| `test_conflict_policy_opposite_side_block` | Selection | Pure policy logic |
| `test_required_facts_readiness_class_priority` | RequiredFacts | Pure ordering logic |
| `test_signal_staleness_window_per_strategy_group` | Fresh Signal | Pure time comparison |
| `test_gate_class_blocker_classification_all_six` | FinalGate | Pure enum/classification |
| `test_prepare_record_non_mutating_flag` | Prepare Records | Pure invariant check |
| `test_shadow_candidate_must_not_reach_exchange` | Shadow/Authorization | Pure boundary assertion |
| `test_authorization_expiry_check` | Shadow/Authorization | Pure time comparison |
| `test_budget_settlement_decimal_precision` | Post-Submit | Pure Decimal arithmetic |
| `test_review_outcome_allowed_values` | Review | Pure enum validation |
| `test_observation_cadence_per_strategy_group` | Armed Observation | Pure config lookup |

---

## Integration/Smoke Candidates

These require DB fixtures or mocked exchange but validate cross-step wiring:

| Test | Runtime Steps Covered | Why Integration |
|---|---|---|
| `test_admission_to_observation_handoff` | 1→2→3 | Admission creates runtime instance, observation attaches |
| `test_signal_to_prepare_to_finalgate_flow` | 4→5→6→7→8 | Full candidate pipeline without exchange |
| `test_prepare_to_submit_to_finalize_flow` | 6→7→8→9→10 | Mock exchange, verify post-submit state |
| `test_reconciliation_mismatch_recovery` | 10 | DB fixture + mock exchange discrepancy |
| `test_notification_on_state_change` | 11 | Mock Feishu, verify message on position close |
| `test_full_next_attempt_submit_cycle` | 4→5→6→7→8→9→10 | Already exists; extend with notification check |
| `test_product_state_propagation_after_watcher_tick` | 1→3→4 | Watcher tick → product state → console readmodel |

---

## Tests Not Recommended Yet

These areas are either too early in implementation, require live exchange
integration, or depend on unmerged features:

| Area | Reason |
|---|---|
| Live exchange submit with real Binance testnet | Requires testnet credentials and is covered by existing `scripts/runtime_full_next_attempt_submit_cycle.py` |
| Multi-symbol concurrent observation | Multi-symbol isolation is P2; current pilot is single-symbol per StrategyGroup |
| LLM advisory auto-publish to Feishu | LLM advisory layer is not in the critical runtime path |
| Tokyo deploy/rollback integration | Deployment governance is a separate concern from runtime path testing |
| Historical research sampling integration | Research path is separate from runtime execution path |

---

## Suggested Follow-up Task Cards

### CLAUDE-TEST-PREPARE-001 — Prepare Record Non-Mutating Invariant Tests

```text
Task ID: CLAUDE-TEST-PREPARE-001
Goal: Verify prepare records never trigger exchange calls or order placement
Why: Prepare step is the most critical safety boundary; a leak means unauthorized execution
Allowed files: tests/unit/test_prepare_record_non_mutating_invariant.py
Forbidden files: src/**, docs/**
Requirements:
  - Test that prepare service returns plan/intent without calling exchange_gateway
  - Test that prepare record cleanup works on StrategyGroup pause/kill
  - Test that prepare conflict blocks when two signals for same symbol arrive
Tests: 4-6 unit tests
Done When: All tests pass, prepare invariant is provably enforced
Hard Stop: Do not modify any source file
Priority: P0
```

### CLAUDE-TEST-FINALGATE-001 — FinalGate Blocker Classification Coverage

```text
Task ID: CLAUDE-TEST-FINALGATE-001
Goal: Consolidated test for all 6 gate blocker classes + bypass detection
Why: FinalGate is the last safety barrier; each class must be independently verified
Allowed files: tests/unit/test_final_gate_all_blocker_classes.py
Forbidden files: src/**, docs/**
Requirements:
  - Test each blocker class produces correct classification
  - Test that hard_safety_stop can never be bypassed
  - Test that review_only_warning does not block execution
  - Test blocker resolution mid-cycle
Tests: 8-12 unit tests
Done When: All 6 classes verified, bypass detection confirmed
Hard Stop: Do not modify any source file
Priority: P0
```

### CLAUDE-TEST-BOUNDARY-001 — Shadow Candidate Boundary Enforcement

```text
Task ID: CLAUDE-TEST-BOUNDARY-001
Goal: Verify shadow-path records never leak into real execution path
Why: Shadow governance is the core architectural boundary; leak = unauthorized order
Allowed files: tests/unit/test_shadow_candidate_boundary_enforcement.py
Forbidden files: src/**, docs/**
Requirements:
  - Test that shadow candidate records have no exchange_gateway reference
  - Test that authorization evidence chain is complete before FinalGate pass
  - Test that authorization expiry blocks submission
  - Test budget authorization rejection when carrier budget exhausted
Tests: 6-8 unit tests
Done When: Boundary is provably enforced
Hard Stop: Do not modify any source file
Priority: P0
```

### CLAUDE-TEST-NOTIFY-001 — Notification and Review Outcome Tests

```text
Task ID: CLAUDE-TEST-NOTIFY-001
Goal: Verify notification delivery and review outcome propagation
Why: Broken notifications = Owner operates blind, defeating the supervision model
Allowed files: tests/unit/test_notification_delivery_and_review_outcome.py
Forbidden files: src/**, docs/**
Requirements:
  - Test notification on material state change
  - Test notification suppression on non-material change
  - Test review outcome persistence and propagation to StrategyGroup status
  - Test notification on reconciliation mismatch
Tests: 6-8 unit tests
Done When: Notification contract is verified
Hard Stop: Do not modify any source file
Priority: P1
```

### CLAUDE-TEST-ADMISSION-001 — Admission Gate Stale Facts and Duplicate Guard

```text
Task ID: CLAUDE-TEST-ADMISSION-001
Goal: Verify admission blocks on stale facts and duplicate StrategyRuntimeInstance
Why: Admission is the gateway; broken gate blocks all automation or allows unsafe states
Allowed files: tests/unit/test_admission_gate_safety_guards.py
Forbidden files: src/**, docs/**
Requirements:
  - Test admission rejection when RequiredFacts are stale
  - Test admission rejection when StrategyRuntimeInstance already ACTIVE
  - Test promotion gate rejection when safety readiness fails
  - Test bootstrap script plan-only vs --execute boundary
Tests: 6-8 unit tests
Done When: Admission safety guards verified
Hard Stop: Do not modify any source file
Priority: P1
```

---

*End of report. 297 test files scanned, 372 source files indexed, 11 runtime
steps mapped.*
