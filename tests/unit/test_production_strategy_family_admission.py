from __future__ import annotations

from src.application.production_strategy_family_admission import (
    API_BACKED_AUTHORIZATION_OPERATION_CHAIN,
    REQUIRED_OWNER_SCOPE_FIELDS,
    build_production_strategy_family_admission_state,
)


def test_production_strategy_family_admission_state_structures_three_families():
    state = build_production_strategy_family_admission_state(
        current_authorization_state={"status": "unknown"},
        now_ms=1770000000000,
    )

    by_family = {item.family: item for item in state.families}
    assert set(by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    assert by_family["Trend"].strategy_family_id == "TF-001-live-readonly-v0"
    assert by_family["Trend"].classification == "actionable"
    assert by_family["Trend"].admission_level_code == "L3"
    assert by_family["Trend"].strategy_group_mapping.evidence_method == "StrategyGroupMappingProposal"
    assert by_family["Trend"].strategy_group_mapping.strategy_group == (
        "Major trend continuation / trend following"
    )
    assert by_family["Trend"].carrier_candidate.status == "registered_metadata_only"
    assert by_family["Trend"].carrier_readiness_report.status == "candidate_registered_not_actionable"
    assert by_family["Trend"].observation_evidence.evidence_method == "TrendObservation"
    assert by_family["Trend"].observation_evidence.status == "observation_evidence_only"
    assert by_family["Trend"].risk_disclosure_contract.evidence_method == "RiskDisclosureDraft"
    assert "false continuation" in by_family["Trend"].risk_disclosure_contract.failure_modes
    assert by_family["Volatility expansion"].strategy_family_id == "VB-001-live-readonly-v0"
    assert by_family["Volatility expansion"].classification == "dry-run-only"
    assert by_family["Volatility expansion"].admission_level_code == "L2"
    assert by_family["Volatility expansion"].research_quality_status == "insufficient_research"
    assert "owner_risk_acceptance_required" in (
        by_family["Volatility expansion"].risk_disclosure_classifications
    )
    assert by_family["Volatility expansion"].carrier_readiness_report.status == (
        "observation_ready_not_actionable"
    )
    assert by_family["Volatility expansion"].carrier_candidate.status == "observation_candidate_only"
    assert by_family["Volatility expansion"].observation_evidence.evidence_method == (
        "CarrierReadinessReport"
    )
    assert by_family["Volatility expansion"].observation_evidence.status == "readiness_report_only"
    assert "fake breakout" in by_family["Volatility expansion"].risk_disclosure_contract.failure_modes
    assert by_family["Mean reversion"].strategy_family_id == "MR-001-live-readonly-v0"
    assert by_family["Mean reversion"].classification == "dry-run-only"
    assert by_family["Mean reversion"].admission_level_code == "L2"
    assert by_family["Mean reversion"].research_quality_status == "insufficient_research"
    assert "owner_risk_acceptance_required" in (
        by_family["Mean reversion"].risk_disclosure_classifications
    )
    assert by_family["Mean reversion"].carrier_readiness_report.status == (
        "observation_ready_not_actionable"
    )
    assert by_family["Mean reversion"].carrier_candidate.status == "observation_candidate_only"
    assert by_family["Mean reversion"].observation_evidence.evidence_method == "CarrierCandidate"
    assert by_family["Mean reversion"].observation_evidence.status == "candidate_metadata_only"
    assert "liquidity wick" in by_family["Mean reversion"].risk_disclosure_contract.failure_modes
    assert state.classification_counts == {"actionable": 1, "dry-run-only": 2}
    levels = {
        item.level: item for item in state.candidate_pipeline_standard.admission_levels
    }
    assert set(levels) == {"L0", "L1", "L2", "L3", "L4"}
    assert levels["L0"].live_action_allowed is False
    assert levels["L1"].action_candidate_allowed is True
    assert levels["L1"].live_action_allowed is False
    assert levels["L2"].action_candidate_allowed is True
    assert levels["L2"].live_action_allowed is False
    assert levels["L3"].live_action_allowed is True
    assert levels["L4"].autonomy_allowed is True
    assert levels["L4"].live_action_allowed is False
    policy = state.candidate_pipeline_standard.warning_hard_blocker_policy
    assert policy.weak_strategy_evidence_policy == "warning_not_hard_blocker"
    assert "weak strategy evidence" in policy.warning_items
    assert policy.l3_requires_owner_risk_acceptance is True
    assert "insufficient_research" in policy.owner_risk_acceptance_may_override
    assert "FinalGate" in policy.owner_risk_acceptance_never_overrides
    assert "missing Owner execute authorization" in policy.hard_blockers_for_live_action
    assert "ExecutionIntent" in policy.post_action_acceptance_outputs
    assert "Review" in policy.post_action_acceptance_outputs
    assert "Audit" in policy.post_action_acceptance_outputs
    family_specs = {item.family: item for item in state.strategy_family_specs}
    assert family_specs["Trend"].admission_level == "L3"
    assert family_specs["Volatility expansion"].admission_level == "L2"
    assert family_specs["Mean reversion"].admission_level == "L2"
    assert family_specs["Trend"].not_alpha_proof is True
    group_specs = {item.family: item for item in state.strategy_group_specs}
    assert group_specs["Trend"].selection_output == (
        "CarrierSpec + RiskDisclosureSpec + ActionCandidateSpec"
    )
    carrier_specs = {item.family: item for item in state.carrier_specs}
    assert carrier_specs["Trend"].action_registry_supported is True
    assert carrier_specs["Trend"].scope_template["symbol"] == "SOL/USDT:USDT"
    assert carrier_specs["Trend"].scope_template["quantity"] == "0.1"
    assert carrier_specs["Volatility expansion"].action_registry_supported is False
    assert carrier_specs["Mean reversion"].action_registry_supported is True
    assert carrier_specs["Mean reversion"].proposal_role == "range_candidate"
    assert carrier_specs["Mean reversion"].market_regime == "mean_reversion"
    assert carrier_specs["Mean reversion"].scope_template["symbol"] == "ETH/USDT:USDT"
    assert carrier_specs["Mean reversion"].scope_template["quantity"] is None
    assert carrier_specs["Mean reversion"].scope_template["target_notional_usdt"] == "22"
    assert carrier_specs["Mean reversion"].scope_template["max_notional"] == "25"
    assert carrier_specs["Mean reversion"].default_example["carrier_id"] == "MR-001-live-readonly-v0"
    assert carrier_specs["Mean reversion"].protection_template["mode"] == "single_tp_plus_sl"
    assert carrier_specs["Mean reversion"].review_template_ref == (
        "review-template:MR-001-live-readonly-v0"
    )
    risk_specs = {item.family: item for item in state.risk_disclosure_specs}
    assert risk_specs["Trend"].weak_strategy_evidence_is_warning is True
    assert "weak strategy evidence" in risk_specs["Trend"].hard_blockers_not_included
    review_templates = {item.family: item for item in state.review_templates}
    assert review_templates["Trend"].post_action_required is True
    assert "entry_result" in review_templates["Trend"].required_sections
    action_specs = {item.family: item for item in state.action_candidate_specs}
    assert action_specs["Trend"].admission_level == "L3"
    assert action_specs["Trend"].status == "owner_confirmed_candidate_blocked_final_gate"
    assert action_specs["Trend"].action_registry_supported is True
    assert action_specs["Trend"].may_execute_live is False
    assert action_specs["Volatility expansion"].status == "proposal"
    assert action_specs["Mean reversion"].status == "proposal"
    for item in action_specs.values():
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.places_order is False
        assert item.mutates_pg is False
        assert "ExecutionIntent" in item.post_action_acceptance_outputs
        assert "TP/SL" in item.post_action_acceptance_outputs
    console_output = {item.family: item for item in state.trading_console_candidate_output}
    assert console_output["Trend"].candidate_state == "bounded_live_candidate"
    assert console_output["Trend"].action_registry_supported is True
    assert console_output["Trend"].owner_action_enabled is False
    assert console_output["Trend"].may_execute_live is False
    assert console_output["Volatility expansion"].candidate_state == "proposal"
    assert console_output["Mean reversion"].candidate_state == "proposal"
    baseline = state.production_baseline_context
    assert baseline.status == "historical_bnb_context_not_action_permission"
    assert baseline.prior_scoped_carrier_id == "MI-001-BNB-LONG"
    assert baseline.prior_symbol == "BNB/USDT:USDT"
    assert baseline.prior_side == "LONG"
    assert baseline.prior_quantity == "0.01"
    assert baseline.prior_live_evidence_status == (
        "owner_authorized_bnb_execute_and_closeout_evidence_present"
    )
    assert baseline.post_close_state_status == (
        "reported_flat_requires_fresh_pg_exchange_validation_before_new_action"
    )
    assert "cannot authorize new Trend" in baseline.reuse_policy
    assert "historical_bnb_one_shot_context_retired" in baseline.evidence_refs
    assert "fresh_pg_exchange_validation_required_before_new_action" in baseline.evidence_refs
    assert baseline.reusable_for_strategy_family_authorization is False
    assert baseline.grants_execution_permission is False
    assert baseline.grants_order_permission is False
    assert baseline.owner_action_enabled is False
    assert baseline.requires_fresh_pre_action_pg_evidence is True
    assert baseline.requires_fresh_pre_action_exchange_evidence is True
    assert baseline.creates_authorization is False
    assert baseline.creates_execution_intent is False
    assert baseline.starts_runtime is False
    assert baseline.starts_strategy_execution is False
    assert baseline.places_order is False
    assert baseline.mutates_pg is False
    assert baseline.exchange_write_action is False
    completion_by_family = {item.family: item for item in state.family_completion_matrix}
    assert set(completion_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    assert completion_by_family["Trend"].completion_status == "actionable"
    assert completion_by_family["Trend"].strategy_group == (
        "Major trend continuation / trend following"
    )
    assert completion_by_family["Trend"].carrier_id == "TF-001-live-readonly-v0"
    assert "StrategyFamily" in completion_by_family["Trend"].completed_stages
    assert "BoundedLiveAuthorization" in completion_by_family["Trend"].blocked_stages
    assert "ActionCandidate" in completion_by_family["Trend"].evidence_methods
    assert "FinalGateDryRun" in completion_by_family["Trend"].evidence_methods
    assert completion_by_family["Volatility expansion"].completion_status == "dry_run_only"
    assert completion_by_family["Mean reversion"].completion_status == "dry_run_only"
    for item in completion_by_family.values():
        assert item.blocker_ids
        assert item.next_retry_conditions
        assert item.backend_actionable is False
        assert item.owner_action_enabled is False
        assert item.may_execute_live is False
        assert item.creates_execution_intent is False
        assert item.places_order is False
        assert item.mutates_pg is False
    risk_control_by_family = {item.family: item for item in state.admission_risk_control_matrix}
    assert set(risk_control_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    assert risk_control_by_family["Trend"].admission_level == "Owner-confirmed action-capable carrier"
    assert risk_control_by_family["Trend"].classification == "actionable"
    assert risk_control_by_family["Trend"].risk_disclosure_status == "draft_for_owner_review"
    assert risk_control_by_family["Trend"].budget_envelope_status == (
        "scope_incomplete_no_numbers_fabricated"
    )
    assert risk_control_by_family["Trend"].authorization_draft_status == "scope_required"
    assert risk_control_by_family["Trend"].bounded_live_authorization_status == (
        "blocked_scope_incomplete"
    )
    assert risk_control_by_family["Trend"].action_api_status == (
        "supported_by_current_official_action_api_but_not_actionable"
    )
    assert risk_control_by_family["Trend"].final_gate_status == "blocked"
    assert risk_control_by_family["Trend"].final_gate_reason == "production_scope_incomplete"
    assert risk_control_by_family["Trend"].protection_plan_status == (
        "draft_required_mandatory_tp_sl"
    )
    assert risk_control_by_family["Trend"].review_contract_status == (
        "draft_no_action_evidence"
    )
    assert risk_control_by_family["Trend"].audit_chain_status == (
        "gap_open_no_live_action_evidence"
    )
    assert risk_control_by_family["Volatility expansion"].classification == "dry-run-only"
    assert risk_control_by_family["Mean reversion"].classification == "dry-run-only"
    for item in risk_control_by_family.values():
        assert item.blocker_ids
        assert item.next_retry_conditions
        assert item.backend_actionable is False
        assert item.owner_action_enabled is False
        assert item.may_execute_live is False
        assert item.action_allowed is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
    capital_boundary_by_family = {
        item.family: item for item in state.production_capital_boundary_matrix
    }
    assert set(capital_boundary_by_family) == {
        "Trend",
        "Volatility expansion",
        "Mean reversion",
    }
    for item in capital_boundary_by_family.values():
        assert item.status == "scope_required"
        assert item.scope_review_status == "not_provided"
        assert item.required_scope_fields == REQUIRED_OWNER_SCOPE_FIELDS
        assert item.provided_scope_fields == []
        assert item.missing_scope_fields == REQUIRED_OWNER_SCOPE_FIELDS
        assert item.supported_symbols
        assert item.requested_symbol is None
        assert item.requested_quantity is None
        assert item.requested_max_notional is None
        assert item.numbers_source == "owner_scope_only_no_fabrication"
        assert item.scope_expansion_allowed is False
        assert item.symbol_expansion_allowed is False
        assert item.side_expansion_allowed is False
        assert item.quantity_expansion_allowed is False
        assert item.notional_expansion_allowed is False
        assert item.leverage_expansion_allowed is False
        assert item.max_attempts_expansion_allowed is False
        assert item.action_allowed is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
        assert item.exchange_write_action is False
    chain_rows_by_family = {}
    for item in state.full_chain_evidence_matrix:
        chain_rows_by_family.setdefault(item.family, []).append(item)
        assert item.required_evidence_refs
        assert item.backend_actionable is False
        assert item.owner_action_enabled is False
        assert item.may_execute_live is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
    assert len(state.full_chain_evidence_matrix) == 30
    assert set(chain_rows_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    trend_chain = {item.stage: item for item in chain_rows_by_family["Trend"]}
    assert [item.stage for item in chain_rows_by_family["Trend"]] == [
        "StrategyFamily",
        "StrategyGroup",
        "Carrier",
        "RiskDisclosure",
        "AuthorizationDraft",
        "BoundedLiveAuthorization",
        "ExecutionIntent",
        "Entry",
        "TP/SL",
        "Review",
    ]
    assert trend_chain["StrategyFamily"].stage_order == 1
    assert trend_chain["StrategyFamily"].status == "available"
    assert "strategy_family_registry_seed" in trend_chain["StrategyFamily"].required_evidence_refs
    assert trend_chain["AuthorizationDraft"].status == "proposal_only_scope_required"
    assert trend_chain["AuthorizationDraft"].evidence_method == "AuthorizationDraftProposal"
    assert trend_chain["AuthorizationDraft"].blocker_ids
    assert "complete_owner_scope" in trend_chain["AuthorizationDraft"].required_evidence_refs
    assert trend_chain["BoundedLiveAuthorization"].status == "blocked_scope_incomplete_or_unmatched"
    assert "backend_final_gate_actionable_true" in (
        trend_chain["BoundedLiveAuthorization"].required_evidence_refs
    )
    assert trend_chain["ExecutionIntent"].status == "not_created"
    assert "execution_intent" in trend_chain["ExecutionIntent"].required_evidence_refs
    assert trend_chain["Entry"].status == "not_executed"
    assert "pre_action_pg_snapshot" in trend_chain["Entry"].required_evidence_refs
    assert trend_chain["TP/SL"].status == "draft_required_mandatory_tp_sl"
    assert "mandatory_tp_sl_plan" in trend_chain["TP/SL"].required_evidence_refs
    assert trend_chain["Review"].status == "review_contract_draft"
    assert "post_action_review" in trend_chain["Review"].required_evidence_refs
    pra_by_family = {item.family: item for item in state.protection_review_audit_matrix}
    assert set(pra_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    trend_pra = pra_by_family["Trend"]
    assert trend_pra.protection_status == "draft_required_mandatory_tp_sl"
    assert trend_pra.required_protection_components == ["TP", "SL"]
    assert "complete_matched_owner_scope" in trend_pra.missing_protection_fields
    assert "take_profit_price" in trend_pra.missing_protection_fields
    assert "stop_loss_price" in trend_pra.missing_protection_fields
    assert trend_pra.unavailable_protection_fields["take_profit_price"] == (
        "not_fabricated_by_read_model"
    )
    assert trend_pra.review_status == "draft_no_action_evidence"
    assert "entry_order" in trend_pra.review_required_evidence
    assert "entry_order" in trend_pra.review_missing_evidence
    assert "audit_log_events" in trend_pra.review_missing_evidence
    assert trend_pra.audit_status == "gap_open_no_live_action_evidence"
    assert "authorization_draft_proposal" in trend_pra.audit_present_evidence
    assert "post_action_review" in trend_pra.audit_missing_evidence
    assert trend_pra.audit_sources_required == [
        "audit_logs",
        "campaign_events",
        "operation_results",
    ]
    assert trend_pra.blocker_ids
    assert trend_pra.next_retry_conditions
    for item in pra_by_family.values():
        assert item.action_allowed is False
        assert item.creates_order is False
        assert item.records_review is False
        assert item.creates_execution_intent is False
        assert item.places_order is False
        assert item.mutates_pg is False
    retry_by_family = {}
    for item in state.blocker_retry_matrix:
        retry_by_family.setdefault(item.family, []).append(item)
        assert item.blocker_id
        assert item.stage
        assert item.blocked_path
        assert item.evidence
        assert item.next_retry_condition
        assert item.retry_requires
        assert item.retry_ready is False
        assert item.action_allowed is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
    assert len(state.blocker_retry_matrix) == 19
    assert set(retry_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    trend_retry_by_id = {item.blocker_id: item for item in retry_by_family["Trend"]}
    assert "BRC-PROD-ADMIT-20260604-TREND-001" in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-SCOPE" in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-ACTION-API" not in trend_retry_by_id
    assert trend_retry_by_id[
        "BRC-PROD-ADMIT-20260604-TREND-001-FINAL-GATE"
    ].evidence_method == "FinalGateDryRun"
    assert trend_retry_by_id[
        "BRC-PROD-ADMIT-20260604-TREND-001-PROTECTION"
    ].evidence_method == "ProtectionPlanDraft"
    assert "take_profit_price defined by official service" in (
        trend_retry_by_id["BRC-PROD-ADMIT-20260604-TREND-001-PROTECTION"].retry_requires
    )
    artifact_by_family = {item.family: item for item in state.owner_authorization_artifact_matrix}
    assert set(artifact_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    trend_artifact = artifact_by_family["Trend"]
    assert trend_artifact.status == "scope_required"
    assert trend_artifact.owner_can_review is True
    assert trend_artifact.owner_scope_status == "not_provided"
    assert trend_artifact.risk_disclosure_status == "draft_for_owner_review"
    assert trend_artifact.budget_envelope_status == "scope_incomplete_no_numbers_fabricated"
    assert trend_artifact.authorization_draft_status == "scope_required"
    assert trend_artifact.confirmation_phrase_required == "I ACCEPT BOUNDED PRODUCTION RISK"
    assert trend_artifact.api_backed_flow_available is True
    assert trend_artifact.api_request_draft_names == [
        "create_admission_evidence",
        "create_owner_regime_input",
        "create_admission_request",
        "create_owner_risk_acceptance",
        "operation_preflight_create_gated_trial_from_admission",
    ]
    assert "POST /api/brc/admissions/requests" in trend_artifact.draft_endpoints
    assert "POST /api/brc/operations/preflight" in trend_artifact.draft_endpoints
    assert "admission_evidence_id" in trend_artifact.unresolved_refs
    assert "owner_current_regime" in trend_artifact.unresolved_refs
    assert "complete matched Owner scope" in trend_artifact.required_before_submit
    assert trend_artifact.blocker_ids
    assert trend_artifact.next_retry_conditions
    for item in artifact_by_family.values():
        assert item.not_authorization is True
        assert item.not_execution_permission is True
        assert item.not_order_permission is True
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
    handoff_by_family = {item.family: item for item in state.owner_review_handoff_matrix}
    assert set(handoff_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    trend_handoff = handoff_by_family["Trend"]
    assert trend_handoff.status == "review_ready_scope_required"
    assert trend_handoff.owner_can_review_risk_scope is True
    assert trend_handoff.owner_scope_status == "not_provided"
    assert trend_handoff.risk_disclosure_status == "draft_for_owner_review"
    assert "false continuation" in trend_handoff.risk_failure_modes
    assert trend_handoff.budget_envelope_status == (
        "scope_incomplete_no_numbers_fabricated"
    )
    assert trend_handoff.authorization_draft_status == "scope_required"
    assert trend_handoff.confirmation_phrase_required == (
        "I ACCEPT BOUNDED PRODUCTION RISK"
    )
    assert trend_handoff.read_only_review_endpoint == (
        "GET /api/trading-console/strategy-family-admission-state"
    )
    assert trend_handoff.api_backed_authorization_status == (
        "operation_layer_metadata_flow_available"
    )
    assert trend_handoff.operation_preflight_endpoint == "POST /api/brc/operations/preflight"
    assert trend_handoff.operation_confirm_endpoint == (
        "POST /api/brc/operations/{operation_id}/confirm"
    )
    assert trend_handoff.operation_step_count == len(API_BACKED_AUTHORIZATION_OPERATION_CHAIN)
    assert trend_handoff.first_operation_type == "create_gated_trial_from_admission"
    assert trend_handoff.last_operation_type == "record_trial_trade_intent_from_signal_evaluation"
    assert "POST /api/brc/admissions/requests" in trend_handoff.draft_endpoints
    assert "admission_evidence_id" in trend_handoff.unresolved_refs
    assert "complete matched Owner scope" in trend_handoff.required_before_submit
    assert trend_handoff.blocker_ids
    assert trend_handoff.next_retry_conditions
    for item in handoff_by_family.values():
        assert item.owner_action_enabled is False
        assert item.action_enablement_source == "official_action_state_only"
        assert item.not_authorization is True
        assert item.not_execution_permission is True
        assert item.not_order_permission is True
        assert item.read_model_submits_authorization is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
        assert item.exchange_write_action is False
    request_rows_by_family = {}
    for item in state.official_api_request_draft_matrix:
        request_rows_by_family.setdefault(item.family, []).append(item)
        assert item.status == "proposal_only_not_submitted"
        assert item.method == "POST"
        assert item.endpoint.startswith("POST /api/brc/")
        assert item.owner_scope_status == "not_provided"
        assert item.required_before_submit
        assert item.payload_template_keys
        assert item.not_submitted is True
        assert item.action_allowed is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
        assert item.mutates_exchange is False
    assert len(state.official_api_request_draft_matrix) == 15
    assert set(request_rows_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    for items in request_rows_by_family.values():
        assert [item.draft_name for item in items] == [
            "create_admission_evidence",
            "create_owner_regime_input",
            "create_admission_request",
            "create_owner_risk_acceptance",
            "operation_preflight_create_gated_trial_from_admission",
        ]
    trend_request_rows = {
        item.draft_name: item for item in request_rows_by_family["Trend"]
    }
    assert trend_request_rows["create_admission_request"].endpoint == (
        "POST /api/brc/admissions/requests"
    )
    assert "admission_evidence_id" in trend_request_rows[
        "create_admission_request"
    ].unresolved_refs
    assert "account_facts_snapshot_json" in trend_request_rows[
        "create_admission_request"
    ].payload_template_keys
    assert trend_request_rows[
        "operation_preflight_create_gated_trial_from_admission"
    ].endpoint == "POST /api/brc/operations/preflight"
    final_gate_by_family = {item.family: item for item in state.final_gate_readiness_matrix}
    assert set(final_gate_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    for item in final_gate_by_family.values():
        checks = {check.code: check for check in item.checks}
        assert item.status == "blocked"
        assert item.readiness_level == "scope_required"
        assert item.final_gate_endpoint == (
            "POST /api/brc/owner-trial-flow/live-execution-boundary/dry-run"
        )
        assert item.execute_endpoint == (
            "POST /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute"
        )
        assert item.final_gate_reason == "production_scope_incomplete"
        assert item.owner_scope_status == "not_provided"
        assert checks["owner_scope_complete"].status == "block"
        assert checks["official_action_api_candidate_supported"].status == (
            "pass" if item.family in {"Trend", "Mean reversion"} else "block"
        )
        assert checks["backend_final_gate_actionable"].status == "block"
        assert "BoundedLiveAuthorization" in item.blocking_stages
        assert "ExecutionIntent" in item.blocking_stages
        assert "Entry" in item.blocking_stages
        assert item.blocker_ids
        assert item.next_retry_conditions
        assert item.backend_actionable is False
        assert item.owner_action_enabled is False
        assert item.may_execute_live is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
        assert item.exchange_write_action is False
    decision_by_family = {item.family: item for item in state.production_action_result_matrix}
    assert set(decision_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    for item in decision_by_family.values():
        assert not hasattr(item, "decision")
        assert item.command_result == "do_not_execute"
        assert item.selection_status == "not_selected_for_live_action"
        assert item.reason == "owner_scope_incomplete_or_unmatched"
        assert item.owner_scope_status == "not_provided"
        assert item.action_api_status == (
            "supported_by_current_official_action_api_but_not_actionable"
            if item.family in {"Trend", "Mean reversion"}
            else "unsupported_by_current_official_action_api"
        )
        assert item.final_gate_reason == "production_scope_incomplete"
        assert "final_gate_actionable_true" in item.missing_evidence
        assert "execution_intent" in item.missing_evidence
        assert item.blocker_ids
        assert item.next_retry_conditions
        assert item.live_action_taken is False
        assert item.backend_actionable is False
        assert item.owner_action_enabled is False
        assert item.may_execute_live is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
        assert item.exchange_write_action is False
    eligibility_by_family = {item.family: item for item in state.live_action_eligibility_matrix}
    assert set(eligibility_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    for item in eligibility_by_family.values():
        checks = {check.code: check for check in item.checks}
        assert item.eligibility == "not_eligible"
        assert not hasattr(item, "decision")
        assert item.eligibility_result == "scope_incomplete_or_unmatched"
        assert checks["owner_scope_complete"].status == "block"
        assert checks["official_action_api_candidate_supported"].status == (
            "pass" if item.family in {"Trend", "Mean reversion"} else "block"
        )
        assert checks["backend_final_gate_actionable"].status == "block"
        assert checks["pre_action_pg_snapshot"].status == "required_before_live_action"
        assert checks["pre_action_exchange_snapshot"].status == "required_before_live_action"
        assert checks["mandatory_tp_sl_plan"].status == "draft_required"
        assert checks["execution_intent"].status == "not_created"
        assert checks["review_contract"].status == "draft_required"
        assert checks["audit_chain_ready"].status == "block"
        assert item.blocker_ids
        assert item.next_retry_conditions
        assert item.backend_actionable is False
        assert item.owner_action_enabled is False
        assert item.may_execute_live is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
    assert state.sprint_acceptance_outcome.status == "in_progress_pass_with_constraint"
    assert state.sprint_acceptance_outcome.completed_family_count == 0
    assert state.sprint_acceptance_outcome.dry_run_only_family_count == 2
    assert state.sprint_acceptance_outcome.blocked_family_count == 0
    assert state.sprint_acceptance_outcome.actionable_family_count == 1
    assert state.sprint_acceptance_outcome.live_execution_ready is False
    assert state.sprint_acceptance_outcome.owner_action_enabled is False
    family_report_by_family = {item.family: item for item in state.family_final_report_matrix}
    assert set(family_report_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    for item in family_report_by_family.values():
        assert item.status == "PASS_WITH_CONSTRAINT"
        assert item.completed_work_status == "PASS_WITH_CONSTRAINT"
        assert item.strategy_group_carrier_mapping_status == "PASS_WITH_CONSTRAINT"
        assert item.admission_risk_control_status == "PASS_WITH_CONSTRAINT"
        assert item.trading_console_authorization_status == "PASS_WITH_CONSTRAINT"
        assert item.live_action_status == "BLOCKED"
        assert item.pg_exchange_evidence_status == "BLOCKED"
        assert item.blocker_count > 0
        assert "ActionCandidate" in item.evidence_methods
        assert "FinalGateDryRun" in item.evidence_methods
        assert f"family_completion_matrix:{item.family}" in item.evidence_refs
        assert f"production_action_result_matrix:{item.family}" in item.evidence_refs
        assert f"evidence_collection_summary_matrix:{item.family}" in item.evidence_refs
        assert f"owner_review_handoff_matrix:{item.family}" in item.evidence_refs
        assert item.next_retry_conditions
        assert item.safety_flags == {
            "live_action_taken": False,
            "runtime_started": False,
            "backend_actionable": False,
            "owner_action_enabled": False,
            "places_order": False,
            "mutates_pg": False,
            "exchange_write_action": False,
        }
        assert item.live_action_taken is False
        assert item.runtime_started is False
        assert item.backend_actionable is False
        assert item.owner_action_enabled is False
        assert item.may_execute_live is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
        assert item.exchange_write_action is False
    assert state.final_report_package.status == "PASS_WITH_CONSTRAINT"
    group_by_name = {
        item.group: item for item in state.final_report_package.evidence_groups
    }
    assert set(group_by_name) == {
        "completed_work_by_family",
        "strategy_group_carrier_mappings",
        "admission_risk_control_changes",
        "trading_console_authorization_readiness",
        "live_actions_taken",
        "pg_exchange_evidence",
        "blocker_records_and_lifecycle_evidence_artifacts",
        "tests_checks",
        "next_retry_conditions",
        "safety_proof",
    }
    assert group_by_name["completed_work_by_family"].status == "PASS_WITH_CONSTRAINT"
    assert "family_completion_matrix" in group_by_name[
        "completed_work_by_family"
    ].evidence_refs
    assert "family_final_report_matrix" in group_by_name[
        "completed_work_by_family"
    ].evidence_refs
    assert "official_api_request_draft_matrix" in group_by_name[
        "trading_console_authorization_readiness"
    ].evidence_refs
    assert "owner_review_handoff_matrix" in group_by_name[
        "trading_console_authorization_readiness"
    ].evidence_refs
    assert "final_gate_readiness_matrix" in group_by_name[
        "trading_console_authorization_readiness"
    ].evidence_refs
    assert group_by_name["live_actions_taken"].status == "BLOCKED"
    assert "live_actions_taken=[]" in group_by_name["live_actions_taken"].evidence_refs
    assert "production_baseline_context" in group_by_name[
        "live_actions_taken"
    ].evidence_refs
    assert "production_action_result_matrix" in group_by_name[
        "live_actions_taken"
    ].evidence_refs
    assert "production_capital_boundary_matrix" in group_by_name[
        "admission_risk_control_changes"
    ].evidence_refs
    assert "objective_acceptance_audit_matrix" in group_by_name[
        "blocker_records_and_lifecycle_evidence_artifacts"
    ].evidence_refs
    assert "objective_acceptance_audit_matrix" in group_by_name[
        "tests_checks"
    ].evidence_refs
    assert group_by_name["pg_exchange_evidence"].status == "BLOCKED"
    assert "family_evidence_collection_matrix" in group_by_name[
        "pg_exchange_evidence"
    ].evidence_refs
    assert "evidence_collection_summary_matrix" in group_by_name[
        "pg_exchange_evidence"
    ].evidence_refs
    assert group_by_name["safety_proof"].status == "PASS"
    assert "production_baseline_context" in group_by_name["safety_proof"].evidence_refs
    assert state.final_report_package.live_actions_taken is False
    assert state.final_report_package.runtime_started is False
    assert state.final_report_package.pg_mutation is False
    assert state.final_report_package.exchange_write_action is False
    assert state.final_report_package.credentials_changed is False
    assert state.final_report_package.deploy_performed is False
    assert state.final_report_package.push_performed is False
    assert any(
        "test_production_strategy_family_admission.py" in command
        for command in state.final_report_package.required_validation_commands
    )
    audit_by_requirement = {
        item.requirement_id: item for item in state.objective_acceptance_audit_matrix
    }
    assert set(audit_by_requirement) == {
        "strategy_family_scope",
        "production_baseline_context",
        "full_chain_per_family",
        "trading_console_authorization_path",
        "strategy_group_carrier_alignment",
        "admission_and_risk_control",
        "production_capital_boundary",
        "live_action_result",
        "pg_exchange_evidence",
        "blocker_records_and_lifecycle_evidence",
        "final_report_package",
        "safety_proof",
    }
    assert audit_by_requirement["strategy_family_scope"].status == "PASS"
    assert audit_by_requirement["production_baseline_context"].status == (
        "PASS_WITH_CONSTRAINT"
    )
    assert audit_by_requirement["full_chain_per_family"].status == "PASS_WITH_CONSTRAINT"
    assert audit_by_requirement["trading_console_authorization_path"].status == (
        "PASS_WITH_CONSTRAINT"
    )
    assert audit_by_requirement["strategy_group_carrier_alignment"].status == (
        "PASS_WITH_CONSTRAINT"
    )
    assert audit_by_requirement["admission_and_risk_control"].status == (
        "PASS_WITH_CONSTRAINT"
    )
    assert audit_by_requirement["production_capital_boundary"].status == (
        "PASS_WITH_CONSTRAINT"
    )
    assert audit_by_requirement["live_action_result"].status == "BLOCKED"
    assert audit_by_requirement["pg_exchange_evidence"].status == "BLOCKED"
    assert audit_by_requirement["blocker_records_and_lifecycle_evidence"].status == (
        "PASS_WITH_CONSTRAINT"
    )
    assert audit_by_requirement["final_report_package"].status == "PASS_WITH_CONSTRAINT"
    assert audit_by_requirement["safety_proof"].status == "PASS"
    assert "owner_review_handoff_matrix" in audit_by_requirement[
        "trading_console_authorization_path"
    ].evidence_refs
    assert "production_baseline_context" in audit_by_requirement[
        "production_baseline_context"
    ].evidence_refs
    assert "production_action_result_matrix" in audit_by_requirement[
        "live_action_result"
    ].evidence_refs
    assert "live_actions_taken=[]" in audit_by_requirement[
        "live_action_result"
    ].evidence_refs
    assert audit_by_requirement["live_action_result"].blocker_ids
    assert "pg_exchange_evidence_matrix" in audit_by_requirement[
        "pg_exchange_evidence"
    ].evidence_refs
    for item in audit_by_requirement.values():
        assert item.next_retry_condition
        assert item.action_allowed is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
        assert item.exchange_write_action is False


def test_production_strategy_family_admission_state_preserves_no_action_boundary():
    state = build_production_strategy_family_admission_state(now_ms=1770000000000)

    assert state.live_actions_taken == []
    assert state.pg_exchange_evidence.live_pg_mutation is False
    assert state.pg_exchange_evidence.exchange_write_action is False
    evidence_keys = {
        (item.phase, item.source_type, item.source) for item in state.pg_exchange_evidence_matrix
    }
    assert ("pre_action", "pg_table", "orders") in evidence_keys
    assert ("pre_action", "pg_table", "positions") in evidence_keys
    assert ("post_action", "pg_table", "execution_intents") in evidence_keys
    assert ("pre_action", "exchange_read", "open_orders") in evidence_keys
    assert ("post_action", "exchange_read", "order_detail") in evidence_keys
    assert ("audit", "audit_source", "audit_logs") in evidence_keys
    assert len(state.pg_exchange_evidence_matrix) == 27
    for item in state.pg_exchange_evidence_matrix:
        assert item.status == "required_not_collected"
        assert item.collection_policy == "official_service_or_api_path_only_no_manual_pg_edits"
        assert item.evidence_ref is None
        assert item.next_retry_condition
        assert item.read_only is True
        assert item.mutates_pg is False
        assert item.exchange_write_action is False
        assert item.places_order is False
    family_evidence_keys = {
        (item.family, item.phase, item.source_type, item.source)
        for item in state.family_evidence_collection_matrix
    }
    assert len(state.family_evidence_collection_matrix) == 81
    assert ("Trend", "pre_action", "pg_table", "orders") in family_evidence_keys
    assert ("Trend", "post_action", "pg_table", "positions") in family_evidence_keys
    assert ("Trend", "pre_action", "exchange_read", "open_orders") in family_evidence_keys
    assert ("Trend", "post_action", "exchange_read", "order_detail") in family_evidence_keys
    assert ("Trend", "audit", "audit_source", "audit_logs") in family_evidence_keys
    assert ("Volatility expansion", "pre_action", "pg_table", "orders") in family_evidence_keys
    assert ("Mean reversion", "audit", "audit_source", "operation_results") in family_evidence_keys
    for item in state.family_evidence_collection_matrix:
        assert item.status == "required_not_collected"
        assert item.collection_policy == "official_service_or_api_path_only_no_manual_pg_edits"
        assert item.evidence_ref is None
        assert item.official_collection_path
        assert item.next_retry_condition
        assert item.read_only is True
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.exchange_write_action is False
        assert item.places_order is False
        assert item.mutates_pg is False
        if item.phase == "pre_action":
            assert item.required_for_stage == "Entry"
        else:
            assert item.required_for_stage == "Review"
    evidence_summary_by_family = {
        item.family: item for item in state.evidence_collection_summary_matrix
    }
    assert set(evidence_summary_by_family) == {
        "Trend",
        "Volatility expansion",
        "Mean reversion",
    }
    for item in evidence_summary_by_family.values():
        assert item.status == "blocked_required_not_collected"
        assert item.total_required == 27
        assert item.collected_count == 0
        assert item.required_not_collected_count == 27
        assert item.phase_counts == {"pre_action": 12, "post_action": 12, "audit": 3}
        assert item.source_type_counts == {
            "pg_table": 16,
            "exchange_read": 8,
            "audit_source": 3,
        }
        assert "official_action_service_pg_snapshot" in item.official_collection_paths
        assert "official_action_service_exchange_read_snapshot" in item.official_collection_paths
        assert "official_action_review_audit_chain" in item.official_collection_paths
        assert "pre_action:pg_table:orders" in item.missing_sources
        assert "post_action:exchange_read:order_detail" in item.missing_sources
        assert "audit:audit_source:audit_logs" in item.missing_sources
        assert item.collection_policy == "official_service_or_api_path_only_no_manual_pg_edits"
        assert item.next_retry_condition
        assert item.read_only is True
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.exchange_write_action is False
        assert item.places_order is False
        assert item.mutates_pg is False
    example_by_family = {item.family: item for item in state.scoped_dry_run_examples}
    assert set(example_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    assert example_by_family["Trend"].owner_scope_query["symbol"] == "SOL/USDT:USDT"
    assert example_by_family["Trend"].owner_scope_query["quantity"] == "0.1"
    assert example_by_family["Trend"].expected_final_gate_reason == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    assert example_by_family["Trend"].expected_action_api_status == (
        "supported_by_current_official_action_api_but_not_actionable"
    )
    legacy_eligibility_key = "expected_eligibility_" + "decision"
    assert not hasattr(example_by_family["Trend"], legacy_eligibility_key)
    assert example_by_family["Trend"].expected_eligibility_result == (
        "scope_complete_but_backend_final_gate_blocked"
    )
    assert example_by_family["Volatility expansion"].owner_scope_query["strategy_family_id"] == (
        "VB-001-live-readonly-v0"
    )
    assert example_by_family["Mean reversion"].owner_scope_query["carrier_id"] == (
        "MR-001-live-readonly-v0"
    )
    for item in example_by_family.values():
        assert item.expected_scope_status == "complete_dry_run_only"
        assert item.expected_authorization_draft_status == "scope_reviewed_dry_run_only"
        assert item.owner_scope_query["side"] == "long"
        if item.family == "Mean reversion":
            assert item.owner_scope_query["max_notional"] == "25"
        else:
            assert item.owner_scope_query["max_notional"] == "20"
        assert item.owner_scope_query["leverage"] == "1"
        assert item.owner_scope_query["max_attempts"] == 1
        assert item.owner_scope_query["protection_mode"] == "mandatory_tp_sl"
        assert item.not_owner_authorization is True
        assert item.action_allowed is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
    assert state.api_backed_authorization_flow.status == "operation_layer_metadata_flow_available"
    assert state.api_backed_authorization_flow.trading_console_direct_action_api is False
    assert state.api_backed_authorization_flow.creates_execution_intent is False
    assert state.api_backed_authorization_flow.places_order is False
    assert state.api_backed_authorization_flow.operation_steps[0].operation_type == (
        "create_gated_trial_from_admission"
    )
    assert state.api_backed_authorization_flow.operation_steps[-1].operation_type == (
        "record_trial_trade_intent_from_signal_evaluation"
    )
    assert all(
        step.creates_execution_intent is False and step.places_order is False
        for step in state.api_backed_authorization_flow.operation_steps
    )
    transition_by_name = {
        item.transition: item for item in state.official_transition_readiness_matrix
    }
    assert transition_by_name["create_admission_request"].status == "proposal_only"
    assert transition_by_name["create_admission_request"].endpoint == (
        "POST /api/brc/admissions/requests"
    )
    assert "admission_evidence_id" in transition_by_name["create_admission_request"].required_refs
    assert transition_by_name["create_owner_risk_acceptance"].status == "proposal_only"
    assert transition_by_name["create_gated_trial_from_admission"].status == (
        "metadata_available"
    )
    assert transition_by_name["create_gated_trial_from_admission"].endpoint == (
        "POST /api/brc/operations/preflight"
    )
    assert transition_by_name["final_gate_dry_run"].status == "blocked"
    assert transition_by_name["execute_authorization"].status == "blocked"
    assert transition_by_name["execute_authorization"].endpoint == (
        "POST /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute"
    )
    for item in transition_by_name.values():
        assert item.owner_confirmation_required is True
        assert item.action_allowed is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.starts_runtime is False
        assert item.starts_strategy_execution is False
        assert item.places_order is False
        assert item.mutates_pg is False
    assert state.official_action_api_inventory.trading_console_action_api_exposed is False
    assert state.official_action_api_inventory.owner_trial_flow_supported_carrier_ids == [
        "MI-001-BNB-LONG",
        "TF-001-live-readonly-v0",
        "MR-001-live-readonly-v0",
        "MR-001-BTC-live-readonly-v0",
    ]
    assert state.official_action_api_inventory.owner_bounded_execution_supported_carrier_ids == [
        "MI-001-BNB-LONG",
        "TF-001-live-readonly-v0",
        "MR-001-live-readonly-v0",
        "MR-001-BTC-live-readonly-v0",
    ]
    assert state.audit_chain_gap_report.evidence_method == "AuditChainGapReport"
    assert state.audit_chain_gap_report.live_action_evidence_present is False
    assert state.audit_chain_gap_report.creates_execution_intent is False
    assert state.audit_chain_gap_report.places_order is False
    assert state.audit_chain_gap_report.mutates_pg is False
    assert "execution_intent" in state.audit_chain_gap_report.missing_evidence
    assert "audit_log_events" in state.audit_chain_gap_report.missing_evidence
    assert state.pre_execution_blocked_review.status == "blocked"
    assert state.pre_execution_blocked_review.evidence_method == "PreExecutionBlockedReview"
    assert state.pre_execution_blocked_review.blocked_reason == (
        "no_family_candidate_is_pre_execution_actionable"
    )
    assert state.pre_execution_blocked_review.action_allowed is False
    assert state.pre_execution_blocked_review.owner_action_enabled is False
    assert state.pre_execution_blocked_review.creates_execution_intent is False
    assert state.pre_execution_blocked_review.places_order is False
    assert state.pre_execution_blocked_review.mutates_pg is False
    assert "BoundedLiveAuthorization" in state.pre_execution_blocked_review.blocking_stages
    assert state.pre_execution_blocked_review.unresolved_blocker_ids
    assert state.trading_console_authorization_readiness.owner_action_enabled is False
    for row in state.families:
        assert row.admission_outcome is not None
        assert row.risk_disclosure_contract.status == "draft_for_owner_review"
        assert row.risk_disclosure_contract.family == row.family
        assert row.risk_disclosure_contract.strategy_group == row.strategy_group
        assert row.risk_disclosure_contract.owner_acknowledgement_required is True
        assert row.risk_disclosure_contract.not_authorization is True
        assert row.risk_disclosure_contract.not_execution_permission is True
        assert row.risk_disclosure_contract.not_order_permission is True
        assert row.authorization_draft_proposal.risk_disclosure_contract is not None
        assert row.authorization_draft_proposal.risk_disclosure_contract.not_authorization is True
        assert row.strategy_group_mapping.family == row.family
        assert row.strategy_group_mapping.carrier_id == row.carrier_id
        assert row.strategy_group_mapping.creates_execution_intent is False
        assert row.strategy_group_mapping.places_order is False
        assert row.strategy_group_mapping.mutates_pg is False
        assert row.carrier_candidate.evidence_method == "CarrierCandidate"
        assert row.carrier_candidate.family == row.family
        assert row.carrier_candidate.strategy_family_id == row.strategy_family_id
        assert row.carrier_candidate.carrier_id == row.carrier_id
        assert row.carrier_candidate.starts_runner is False
        assert row.carrier_candidate.creates_signal is False
        assert row.carrier_candidate.creates_trade_intent is False
        assert row.carrier_candidate.creates_execution_intent is False
        assert row.carrier_candidate.places_order is False
        assert row.carrier_candidate.mutates_pg is False
        assert row.carrier_candidate.blockers
        assert row.carrier_readiness_report.family == row.family
        assert row.carrier_readiness_report.carrier_id == row.carrier_id
        assert row.carrier_readiness_report.backend_actionable is False
        assert row.carrier_readiness_report.owner_action_enabled is False
        assert row.carrier_readiness_report.creates_execution_intent is False
        assert row.carrier_readiness_report.places_order is False
        assert row.carrier_readiness_report.mutates_pg is False
        readiness_checks = {check["code"]: check for check in row.carrier_readiness_report.readiness_checks}
        assert readiness_checks["official_action_api_supported"]["status"] == (
            "pass" if row.family in {"Trend", "Mean reversion"} else "block"
        )
        assert readiness_checks["backend_actionable"]["status"] == "block"
        assert row.action_candidate.evidence_method == "ActionCandidate"
        assert row.action_candidate.family == row.family
        assert row.action_candidate.carrier_id == row.carrier_id
        assert row.action_candidate.status == (
            "supported_but_backend_not_actionable"
            if row.family in {"Trend", "Mean reversion"}
            else "unsupported_by_current_official_action_api"
        )
        assert row.action_candidate.action_allowed is False
        assert row.action_candidate.backend_actionable is False
        assert row.action_candidate.owner_action_enabled is False
        assert row.action_candidate.creates_authorization is False
        assert row.action_candidate.creates_execution_intent is False
        assert row.action_candidate.places_order is False
        assert row.action_candidate.mutates_pg is False
        assert "backend final gate returns actionable=true" in row.action_candidate.required_before_action
        assert "backend_final_gate_actionable_true_required" in row.action_candidate.blockers
        assert row.admission_outcome.may_execute_live is False
        assert row.admission_outcome.owner_action_enabled is False
        assert row.admission_outcome.remaining_requirements
        assert row.backend_actionable is False
        assert row.owner_action_enabled is False
        assert [stage.stage for stage in row.chain_stage_states] == [
            "StrategyFamily",
            "StrategyGroup",
            "Carrier",
            "RiskDisclosure",
            "AuthorizationDraft",
            "BoundedLiveAuthorization",
            "ExecutionIntent",
            "Entry",
            "TP/SL",
            "Review",
        ]
        assert row.pre_post_evidence_contract.status == (
            "required_before_live_action_not_collected_by_read_model"
        )
        assert row.audit_chain_gap_report.family == row.family
        assert row.audit_chain_gap_report.carrier_id == row.carrier_id
        assert row.audit_chain_gap_report.status == "gap_open_no_live_action_evidence"
        assert row.audit_chain_gap_report.evidence_method == "AuditChainGapReport"
        assert row.audit_chain_gap_report.live_action_evidence_present is False
        assert row.audit_chain_gap_report.creates_execution_intent is False
        assert row.audit_chain_gap_report.places_order is False
        assert row.audit_chain_gap_report.mutates_pg is False
        assert "authorization_draft_proposal" in row.audit_chain_gap_report.present_evidence
        assert "pre_action_pg_snapshot" in row.audit_chain_gap_report.missing_evidence
        assert "post_action_review" in row.audit_chain_gap_report.missing_evidence
        assert row.pre_execution_blocked_review.status == "blocked"
        assert row.pre_execution_blocked_review.evidence_method == "PreExecutionBlockedReview"
        assert row.pre_execution_blocked_review.family == row.family
        assert row.pre_execution_blocked_review.carrier_id == row.carrier_id
        assert row.pre_execution_blocked_review.action_allowed is False
        assert row.pre_execution_blocked_review.owner_action_enabled is False
        assert row.pre_execution_blocked_review.creates_execution_intent is False
        assert row.pre_execution_blocked_review.places_order is False
        assert row.pre_execution_blocked_review.mutates_pg is False
        pre_execution_checks = {check["code"]: check for check in row.pre_execution_blocked_review.checks}
        assert pre_execution_checks["backend_final_gate_actionable"]["status"] == "block"
        assert pre_execution_checks["pg_exchange_pre_evidence"]["status"] == (
            "required_before_live_action"
        )
        assert pre_execution_checks["mandatory_tp_sl_plan"]["status"] == "draft_required"
        assert row.pre_execution_blocked_review.unresolved_blocker_ids
        assert row.observation_evidence.required_before_live_action is True
        assert row.observation_evidence.starts_runner is False
        assert row.observation_evidence.creates_signal is False
        assert row.observation_evidence.creates_trade_intent is False
        assert row.observation_evidence.creates_execution_intent is False
        assert row.observation_evidence.places_order is False
        assert row.observation_evidence.mutates_pg is False
        assert row.pre_post_evidence_contract.mutation_allowed_by_read_model is False
        assert row.pre_post_evidence_contract.live_action_evidence_present is False
        assert "orders" in row.pre_post_evidence_contract.pre_action_pg_tables
        assert "positions" in row.pre_post_evidence_contract.post_action_pg_tables
        assert "open_orders" in row.pre_post_evidence_contract.pre_action_exchange_reads
        assert "order_detail" in row.pre_post_evidence_contract.post_action_exchange_reads
        assert [draft.name for draft in row.api_request_drafts] == [
            "create_admission_evidence",
            "create_owner_regime_input",
            "create_admission_request",
            "create_owner_risk_acceptance",
            "operation_preflight_create_gated_trial_from_admission",
        ]
        assert all(draft.not_submitted is True for draft in row.api_request_drafts)
        assert all(draft.places_order is False for draft in row.api_request_drafts)
        assert all(draft.creates_execution_intent is False for draft in row.api_request_drafts)
        assert row.action_api_compatibility.compatible is (
            row.family in {"Trend", "Mean reversion"}
        )
        assert row.action_api_compatibility.status == (
            "supported_by_current_official_action_api_but_not_actionable"
            if row.family in {"Trend", "Mean reversion"}
            else "unsupported_by_current_official_action_api"
        )
        if row.family in {"Trend", "Mean reversion"}:
            assert row.action_api_compatibility.blockers == []
        else:
            assert "candidate_carrier_not_supported_by_owner_trial_flow" in (
                row.action_api_compatibility.blockers
            )
        assert row.execution_intent_state == "not_created"
        assert row.entry_state == "not_executed"
        assert row.final_gate_dry_run.creates_execution_intent is False
        assert row.final_gate_dry_run.places_order is False


def test_production_strategy_family_admission_state_exposes_boundary_contracts():
    state = build_production_strategy_family_admission_state(now_ms=1770000000000)

    assert state.admission_contract.chain == [
        "StrategyFamily",
        "StrategyGroup",
        "Carrier",
        "RiskDisclosure",
        "AuthorizationDraft",
        "BoundedLiveAuthorization",
        "ExecutionIntent",
        "Entry",
        "TP/SL",
        "Review",
    ]
    assert state.admission_contract.required_owner_scope_fields == REQUIRED_OWNER_SCOPE_FIELDS
    assert "FinalGateDryRun" in state.lifecycle_evidence_artifacts
    assert "TrendObservation" in state.lifecycle_evidence_artifacts
    assert "ProtectionPlanDraft" in state.lifecycle_evidence_artifacts
    assert "ReviewContract" in state.lifecycle_evidence_artifacts
    assert "AuditChainGapReport" in state.lifecycle_evidence_artifacts
    acceptance_by_item = {item.item: item for item in state.acceptance_evidence_matrix}
    assert set(acceptance_by_item) == {
        "strategy_families_have_concrete_candidates",
        "strategy_group_carrier_mapping",
        "owner_risk_scope_review",
        "api_backed_authorization_flow",
        "owner_action_disabled_until_official_action_ready",
        "production_capital_boundary",
        "official_action_api_candidate_support",
        "backend_final_gate_preflight",
        "pg_exchange_pre_post_evidence",
        "mandatory_tp_sl_protection",
        "review_audit_contract",
        "live_action_execution",
    }
    assert acceptance_by_item["strategy_families_have_concrete_candidates"].status == "PASS"
    assert acceptance_by_item["strategy_group_carrier_mapping"].status == "PASS_WITH_CONSTRAINT"
    assert acceptance_by_item["owner_risk_scope_review"].status == "BLOCKED"
    assert "owner_review_handoff_matrix" in acceptance_by_item[
        "owner_risk_scope_review"
    ].evidence_refs
    assert acceptance_by_item["api_backed_authorization_flow"].status == "PASS_WITH_CONSTRAINT"
    assert "owner_review_handoff_matrix" in acceptance_by_item[
        "api_backed_authorization_flow"
    ].evidence_refs
    assert acceptance_by_item[
        "owner_action_disabled_until_official_action_ready"
    ].status == "PASS"
    assert acceptance_by_item["production_capital_boundary"].status == "PASS_WITH_CONSTRAINT"
    assert acceptance_by_item["official_action_api_candidate_support"].status == "BLOCKED"
    assert acceptance_by_item["backend_final_gate_preflight"].status == "BLOCKED"
    assert acceptance_by_item["pg_exchange_pre_post_evidence"].status == "BLOCKED"
    assert acceptance_by_item["mandatory_tp_sl_protection"].status == "DEFERRED"
    assert acceptance_by_item["review_audit_contract"].status == "BLOCKED"
    assert acceptance_by_item["live_action_execution"].status == "BLOCKED"
    assert "live_actions_taken=[]" in acceptance_by_item["live_action_execution"].evidence_refs
    assert acceptance_by_item["live_action_execution"].blocker_ids
    for item in acceptance_by_item.values():
        assert item.families == ["Trend", "Volatility expansion", "Mean reversion"]
        assert item.action_allowed is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.places_order is False
        assert item.mutates_pg is False
    by_projection_status = {item.evidence_method: item for item in state.lifecycle_evidence_statuses}
    assert set(by_projection_status) == set(state.lifecycle_evidence_artifacts)
    assert by_projection_status["TrendObservation"].status == "present"
    assert by_projection_status["TrendObservation"].families == ["Trend"]
    assert by_projection_status["StrategyGroupMappingProposal"].status == "present"
    assert by_projection_status["CarrierCandidate"].status == "mixed"
    assert by_projection_status["CarrierReadinessReport"].status == "mixed"
    assert by_projection_status["ActionCandidate"].status == "blocked"
    assert by_projection_status["RiskDisclosureDraft"].status == "draft"
    assert by_projection_status["AuthorizationDraftProposal"].status == "draft"
    assert by_projection_status["BudgetEnvelopeDraft"].status == "draft"
    assert by_projection_status["FinalGateDryRun"].status == "blocked"
    assert by_projection_status["PreExecutionBlockedReview"].status == "blocked"
    assert by_projection_status["ProtectionPlanDraft"].status == "draft"
    assert by_projection_status["ReviewContract"].status == "draft"
    assert by_projection_status["AuditChainGapReport"].status == "blocked"
    assert by_projection_status["BudgetEnvelopeDraft"].row_statuses == {
        "Trend": "scope_incomplete_no_numbers_fabricated",
        "Volatility expansion": "scope_incomplete_no_numbers_fabricated",
        "Mean reversion": "scope_incomplete_no_numbers_fabricated",
    }
    for item in by_projection_status.values():
        assert item.action_allowed is False
        assert item.creates_authorization is False
        assert item.creates_execution_intent is False
        assert item.places_order is False
        assert item.mutates_pg is False
        assert item.next_retry_condition
    assert len(state.blocker_records) > 3
    for row in state.families:
        gate_blocker_ids = {item.id for item in row.gate_blocker_records}
        assert f"{row.blocker_record.id}-SCOPE" in gate_blocker_ids
        if row.family in {"Trend", "Mean reversion"}:
            assert f"{row.blocker_record.id}-ACTION-API" not in gate_blocker_ids
        else:
            assert f"{row.blocker_record.id}-ACTION-API" in gate_blocker_ids
        assert f"{row.blocker_record.id}-FINAL-GATE" in gate_blocker_ids
        assert f"{row.blocker_record.id}-EVIDENCE" in gate_blocker_ids
        assert f"{row.blocker_record.id}-PROTECTION" in gate_blocker_ids
        assert f"{row.blocker_record.id}-REVIEW" in gate_blocker_ids
        assert row.required_scope_missing == REQUIRED_OWNER_SCOPE_FIELDS
        assert row.budget_envelope_draft.evidence_method == "BudgetEnvelopeDraft"
        assert row.budget_envelope_draft.required_scope_fields == REQUIRED_OWNER_SCOPE_FIELDS
        assert row.budget_envelope_draft.scope == {}
        assert row.budget_envelope_draft.provided_scope_fields == []
        assert row.budget_envelope_draft.missing_scope_fields == REQUIRED_OWNER_SCOPE_FIELDS
        assert row.budget_envelope_draft.numbers_source == "owner_scope_only_no_fabrication"
        assert row.budget_envelope_draft.quantity is None
        assert row.budget_envelope_draft.max_notional is None
        assert row.budget_envelope_draft.action_allowed is False
        assert row.budget_envelope_draft.creates_authorization is False
        assert row.budget_envelope_draft.creates_execution_intent is False
        assert row.budget_envelope_draft.places_order is False
        assert row.budget_envelope_draft.mutates_pg is False
        budget_checks = {check["code"]: check for check in row.budget_envelope_draft.validation_checks}
        assert budget_checks["owner_scope_complete"]["status"] == "block"
        assert budget_checks["candidate_scope_matched"]["status"] == "block"
        assert budget_checks["quantity_provided"]["status"] == "missing"
        assert budget_checks["max_notional_provided"]["status"] == "missing"
        assert row.authorization_draft_proposal.status == "scope_required"
        assert row.authorization_draft_proposal.budget_envelope.evidence_method == "BudgetEnvelopeDraft"
        assert row.authorization_draft_proposal.budget_envelope.places_order is False
        assert row.authorization_draft_proposal.not_authorization is True
        assert row.authorization_draft_proposal.not_execution_permission is True
        assert row.authorization_draft_proposal.not_order_permission is True
        assert row.authorization_draft_proposal.official_api_transition_plan.creates_authorization is False
        assert (
            row.authorization_draft_proposal.official_api_transition_plan.api_backed_authorization_endpoints[
                "operation_preflight"
            ]
            == "POST /api/brc/operations/preflight"
        )
        assert row.protection_plan_state == "draft_required_mandatory_tp_sl"
        assert row.protection_plan_draft.evidence_method == "ProtectionPlanDraft"
        assert row.protection_plan_draft.required_components == ["TP", "SL"]
        assert row.protection_plan_draft.status == "draft_required_mandatory_tp_sl"
        assert "complete_matched_owner_scope" in row.protection_plan_draft.missing_fields
        assert "take_profit_price" in row.protection_plan_draft.missing_fields
        assert "stop_loss_price" in row.protection_plan_draft.missing_fields
        assert row.protection_plan_draft.unavailable_fields["take_profit_price"] == (
            "not_fabricated_by_read_model"
        )
        assert row.protection_plan_draft.unavailable_fields["exchange_tp_order_id"] == (
            "not_created_by_read_model"
        )
        assert row.protection_plan_draft.action_allowed is False
        assert row.protection_plan_draft.creates_order is False
        assert row.protection_plan_draft.places_order is False
        assert row.protection_plan_draft.mutates_pg is False
        protection_checks = {check["code"]: check for check in row.protection_plan_draft.validation_checks}
        assert protection_checks["owner_scope_complete"]["status"] == "block"
        assert protection_checks["take_profit_defined"]["status"] == "missing"
        assert protection_checks["stop_loss_defined"]["status"] == "missing"
        assert row.authorization_draft_proposal.protection_plan.action_allowed is False
        assert row.review_contract.required is True
        assert row.review_contract.status == "draft_no_action_evidence"
        assert row.review_contract.evidence_method == "ReviewContract"
        assert row.review_contract.family == row.family
        assert row.review_contract.metrics
        assert "entry_order" in row.review_contract.required_evidence
        assert "entry_order" in row.review_contract.missing_evidence
        assert "audit_log_events" in row.review_contract.missing_evidence
        assert row.review_contract.promotion_allowed is False
        assert row.review_contract.records_review is False
        assert row.review_contract.creates_execution_intent is False
        assert row.review_contract.places_order is False
        assert row.review_contract.mutates_pg is False
        assert row.authorization_draft_proposal.review_contract.promotion_allowed is False
        assert row.blocker_record.id.startswith("BRC-PROD-ADMIT-20260604-")
        assert row.blocker_record.severity == "hard_blocker"


def test_generic_action_spec_and_action_entry_contract_preserve_safe_boundaries():
    state = build_production_strategy_family_admission_state(now_ms=1770000000000)

    assert state.generic_final_gate_adapter_contract.live_action_policy == (
        "fail_closed_until_official_final_gate_passes"
    )
    assert state.generic_final_gate_adapter_contract.may_execute_live is False
    assert state.generic_final_gate_adapter_contract.places_order is False
    assert "invalid GenericActionSpec" in (
        state.generic_final_gate_adapter_contract.hard_blockers_for_live_action
    )
    assert "weak strategy evidence" in (
        state.generic_final_gate_adapter_contract.warning_not_blocker
    )

    specs_by_family = {item.family: item for item in state.generic_action_specs}
    trend = specs_by_family["Trend"]
    assert trend.carrier_id == "TF-001-live-readonly-v0"
    assert trend.status == "valid_blocked_final_gate"
    assert trend.action_registry_supported is True
    assert trend.supported_symbols == [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
    ]
    assert trend.supported_sides == ["long"]
    assert trend.symbol == "SOL/USDT:USDT"
    assert trend.side == "long"
    assert trend.quantity == "0.1"
    assert trend.max_notional == "20"
    assert trend.leverage == "1"
    assert trend.max_attempts == 1
    assert trend.protection_mode == "single_tp_plus_sl"
    assert trend.may_execute_live is False
    assert trend.owner_action_enabled is False
    assert trend.creates_authorization is False
    assert trend.creates_execution_intent is False
    assert trend.places_order is False
    assert trend.mutates_pg is False

    assert specs_by_family["Volatility expansion"].status == "proposal_non_action"
    assert specs_by_family["Volatility expansion"].action_registry_supported is False
    mean_reversion = specs_by_family["Mean reversion"]
    assert mean_reversion.status == "proposal_non_action"
    assert mean_reversion.action_registry_supported is True
    assert mean_reversion.proposal_role == "range_candidate"
    assert mean_reversion.market_regime == "mean_reversion"
    assert mean_reversion.supported_symbols == ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    assert mean_reversion.supported_sides == ["long"]
    assert mean_reversion.symbol == "ETH/USDT:USDT"
    assert mean_reversion.side == "long"
    assert mean_reversion.quantity is None
    assert mean_reversion.target_notional_usdt == "22"
    assert mean_reversion.computed_quantity is None
    assert mean_reversion.max_notional == "25"
    assert mean_reversion.leverage == "1"
    assert mean_reversion.max_attempts == 1
    assert mean_reversion.protection_mode == "single_tp_plus_sl"
    assert mean_reversion.protection_template["mode"] == "single_tp_plus_sl"
    assert mean_reversion.review_template["template_id"] == (
        "review-template:MR-001-live-readonly-v0"
    )
    assert mean_reversion.may_execute_live is False
    assert mean_reversion.owner_action_enabled is False
    assert mean_reversion.places_order is False

    payloads_by_family = {
        item.family: item for item in state.action_entry_payload_contracts
    }
    trend_payload = payloads_by_family["Trend"]
    assert trend_payload.contract_status == "ready_for_final_gate_adapter"
    assert trend_payload.required_owner_scope["symbol"] == "SOL/USDT:USDT"
    assert trend_payload.required_owner_scope["quantity"] == "0.1"
    assert trend_payload.required_owner_scope["max_notional"] == "20"
    assert trend_payload.required_owner_scope["protection_mode"] == "single_tp_plus_sl"
    assert trend_payload.action_allowed is False
    assert trend_payload.may_execute_live is False
    assert trend_payload.owner_action_enabled is False
    mr_payload = payloads_by_family["Mean reversion"]
    assert mr_payload.contract_status == "proposal_only"
    assert mr_payload.required_owner_scope["symbol"] == "ETH/USDT:USDT"
    assert mr_payload.required_owner_scope["quantity"] is None
    assert mr_payload.required_owner_scope["target_notional_usdt"] == "22"
    assert mr_payload.required_owner_scope["max_notional"] == "25"
    assert mr_payload.required_owner_scope["protection_mode"] == "single_tp_plus_sl"
    assert mr_payload.action_allowed is False
    assert mr_payload.may_execute_live is False
    assert mr_payload.owner_action_enabled is False

    action_entry_by_family = {
        item.family: item for item in state.trading_console_action_entry_output
    }
    assert action_entry_by_family["Trend"].action_entry_state == (
        "ready_for_owner_scope_final_gate"
    )
    assert action_entry_by_family["Trend"].owner_action_enabled is False
    assert action_entry_by_family["Volatility expansion"].action_entry_state == (
        "proposal_only"
    )
    assert action_entry_by_family["Mean reversion"].action_entry_state == "proposal_only"


def test_complete_owner_scope_is_reviewed_but_not_made_actionable():
    state = build_production_strategy_family_admission_state(
        owner_scope={
            "family": "Trend",
            "strategy_family_id": "TF-001-live-readonly-v0",
            "carrier_id": "TF-001-live-readonly-v0",
            "symbol": "SOL/USDT:USDT",
            "side": "long",
            "quantity": "0.1",
            "max_notional": "20",
            "leverage": "1",
            "max_attempts": 1,
            "protection_mode": "mandatory_tp_sl",
            "review_requirement": "post_action_review_required_before_promotion",
        },
        now_ms=1770000000000,
    )

    trend = next(item for item in state.families if item.family == "Trend")
    assert state.scope_review.status == "complete_dry_run_only"
    assert state.scope_review.matched_candidate is True
    assert trend.scope_review.status == "complete_dry_run_only"
    risk_control_by_family = {item.family: item for item in state.admission_risk_control_matrix}
    trend_risk_control = risk_control_by_family["Trend"]
    assert trend_risk_control.scope_review_status == "complete_dry_run_only"
    assert trend_risk_control.budget_envelope_status == "scope_complete_dry_run_only"
    assert trend_risk_control.authorization_draft_status == "scope_reviewed_dry_run_only"
    assert trend_risk_control.bounded_live_authorization_status == (
        "blocked_backend_final_gate"
    )
    assert trend_risk_control.action_api_status == (
        "supported_by_current_official_action_api_but_not_actionable"
    )
    assert trend_risk_control.final_gate_reason == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    assert trend_risk_control.protection_plan_status == "scope_reviewed_draft_only"
    assert trend_risk_control.review_contract_status == "draft_no_action_evidence"
    assert trend_risk_control.audit_chain_status == "gap_open_no_live_action_evidence"
    assert trend_risk_control.backend_actionable is False
    assert trend_risk_control.owner_action_enabled is False
    assert trend_risk_control.action_allowed is False
    assert trend_risk_control.places_order is False
    capital_boundary_by_family = {
        item.family: item for item in state.production_capital_boundary_matrix
    }
    trend_boundary = capital_boundary_by_family["Trend"]
    assert trend_boundary.status == "scope_reviewed_dry_run_only"
    assert trend_boundary.scope_review_status == "complete_dry_run_only"
    assert trend_boundary.required_scope_fields == REQUIRED_OWNER_SCOPE_FIELDS
    assert trend_boundary.provided_scope_fields == REQUIRED_OWNER_SCOPE_FIELDS
    assert trend_boundary.missing_scope_fields == []
    assert trend_boundary.requested_symbol == "SOL/USDT:USDT"
    assert trend_boundary.requested_side == "long"
    assert trend_boundary.requested_quantity == "0.1"
    assert trend_boundary.requested_max_notional == "20"
    assert trend_boundary.requested_leverage == "1"
    assert trend_boundary.requested_max_attempts == 1
    assert trend_boundary.requested_protection_mode == "mandatory_tp_sl"
    assert trend_boundary.requested_review_requirement == (
        "post_action_review_required_before_promotion"
    )
    assert trend_boundary.numbers_source == "owner_scope_only_no_fabrication"
    assert trend_boundary.scope_expansion_allowed is False
    assert trend_boundary.symbol_expansion_allowed is False
    assert trend_boundary.notional_expansion_allowed is False
    assert trend_boundary.leverage_expansion_allowed is False
    assert trend_boundary.action_allowed is False
    assert trend_boundary.creates_authorization is False
    assert trend_boundary.creates_execution_intent is False
    assert trend_boundary.places_order is False
    assert trend_boundary.mutates_pg is False
    assert trend_boundary.exchange_write_action is False
    trend_chain = {
        item.stage: item
        for item in state.full_chain_evidence_matrix
        if item.family == "Trend"
    }
    assert trend_chain["AuthorizationDraft"].status == "scope_reviewed_dry_run_only"
    assert trend_chain["AuthorizationDraft"].blocker_ids == []
    assert trend_chain["BoundedLiveAuthorization"].status == (
        "blocked_backend_final_gate"
    )
    assert trend_chain["BoundedLiveAuthorization"].blocker_ids
    assert trend_chain["ExecutionIntent"].status == "not_created"
    assert trend_chain["ExecutionIntent"].places_order is False
    assert trend_chain["Entry"].status == "not_executed"
    assert trend_chain["Entry"].places_order is False
    pra_by_family = {item.family: item for item in state.protection_review_audit_matrix}
    trend_pra = pra_by_family["Trend"]
    assert trend_pra.protection_status == "scope_reviewed_draft_only"
    assert "complete_matched_owner_scope" not in trend_pra.missing_protection_fields
    assert "take_profit_price" in trend_pra.missing_protection_fields
    assert "stop_loss_price" in trend_pra.missing_protection_fields
    assert trend_pra.review_status == "draft_no_action_evidence"
    assert trend_pra.audit_status == "gap_open_no_live_action_evidence"
    assert trend_pra.action_allowed is False
    assert trend_pra.creates_order is False
    assert trend_pra.records_review is False
    assert trend_pra.places_order is False
    assert trend_pra.mutates_pg is False
    trend_retry_by_id = {
        item.blocker_id: item
        for item in state.blocker_retry_matrix
        if item.family == "Trend"
    }
    assert "BRC-PROD-ADMIT-20260604-TREND-001-SCOPE" not in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-ACTION-API" not in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-FINAL-GATE" in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-PROTECTION" in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-REVIEW" in trend_retry_by_id
    assert all(item.retry_ready is False for item in trend_retry_by_id.values())
    assert all(item.places_order is False for item in trend_retry_by_id.values())
    artifact_by_family = {item.family: item for item in state.owner_authorization_artifact_matrix}
    trend_artifact = artifact_by_family["Trend"]
    assert trend_artifact.status == "scope_reviewed_dry_run_only"
    assert trend_artifact.owner_scope_status == "complete_dry_run_only"
    assert trend_artifact.budget_envelope_status == "scope_complete_dry_run_only"
    assert trend_artifact.authorization_draft_status == "scope_reviewed_dry_run_only"
    assert trend_artifact.confirmation_phrase_required == "I ACCEPT BOUNDED PRODUCTION RISK"
    assert "strategy_family_version_id" not in trend_artifact.unresolved_refs
    assert "playbook_id" not in trend_artifact.unresolved_refs
    assert "admission_evidence_id" in trend_artifact.unresolved_refs
    assert "admission_decision_id" in trend_artifact.unresolved_refs
    assert "Owner risk acceptance is created through official API" in (
        trend_artifact.required_before_submit
    )
    assert trend_artifact.not_authorization is True
    assert trend_artifact.not_execution_permission is True
    assert trend_artifact.creates_authorization is False
    assert trend_artifact.creates_execution_intent is False
    assert trend_artifact.places_order is False
    handoff_by_family = {item.family: item for item in state.owner_review_handoff_matrix}
    trend_handoff = handoff_by_family["Trend"]
    assert trend_handoff.status == "review_ready_dry_run_only"
    assert trend_handoff.owner_scope_status == "complete_dry_run_only"
    assert trend_handoff.budget_envelope_status == "scope_complete_dry_run_only"
    assert trend_handoff.authorization_draft_status == "scope_reviewed_dry_run_only"
    assert "strategy_family_version_id" not in trend_handoff.unresolved_refs
    assert "playbook_id" not in trend_handoff.unresolved_refs
    assert "admission_evidence_id" in trend_handoff.unresolved_refs
    assert "admission_decision_id" in trend_handoff.unresolved_refs
    assert "Owner risk acceptance is created through official API" in (
        trend_handoff.required_before_submit
    )
    assert trend_handoff.owner_action_enabled is False
    assert trend_handoff.read_model_submits_authorization is False
    assert trend_handoff.creates_authorization is False
    assert trend_handoff.creates_execution_intent is False
    assert trend_handoff.places_order is False
    assert trend_handoff.mutates_pg is False
    trend_request_rows = {
        item.draft_name: item
        for item in state.official_api_request_draft_matrix
        if item.family == "Trend"
    }
    assert len(trend_request_rows) == 5
    assert trend_request_rows["create_admission_request"].owner_scope_status == (
        "complete_dry_run_only"
    )
    assert "strategy_family_version_id" not in trend_request_rows[
        "create_admission_request"
    ].unresolved_refs
    assert "playbook_id" not in trend_request_rows[
        "create_admission_request"
    ].unresolved_refs
    assert "admission_evidence_id" in trend_request_rows[
        "create_admission_request"
    ].unresolved_refs
    assert trend_request_rows["create_admission_request"].not_submitted is True
    assert trend_request_rows["create_admission_request"].creates_authorization is False
    assert trend_request_rows["create_admission_request"].creates_execution_intent is False
    assert trend_request_rows["create_admission_request"].places_order is False
    assert trend_request_rows[
        "operation_preflight_create_gated_trial_from_admission"
    ].starts_runtime is False
    final_gate_by_family = {item.family: item for item in state.final_gate_readiness_matrix}
    trend_final_gate = final_gate_by_family["Trend"]
    final_gate_checks = {check.code: check for check in trend_final_gate.checks}
    assert trend_final_gate.status == "blocked"
    assert trend_final_gate.readiness_level == "scope_reviewed_backend_final_gate_blocked"
    assert trend_final_gate.final_gate_reason == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    assert trend_final_gate.owner_scope_status == "complete_dry_run_only"
    assert final_gate_checks["owner_scope_complete"].status == "pass"
    assert final_gate_checks["official_action_api_candidate_supported"].status == "pass"
    assert final_gate_checks["backend_final_gate_actionable"].status == "block"
    assert "BoundedLiveAuthorization" in trend_final_gate.blocking_stages
    assert "ExecutionIntent" in trend_final_gate.blocking_stages
    assert trend_final_gate.backend_actionable is False
    assert trend_final_gate.owner_action_enabled is False
    assert trend_final_gate.may_execute_live is False
    assert trend_final_gate.creates_authorization is False
    assert trend_final_gate.creates_execution_intent is False
    assert trend_final_gate.starts_runtime is False
    assert trend_final_gate.starts_strategy_execution is False
    assert trend_final_gate.places_order is False
    assert trend_final_gate.mutates_pg is False
    assert trend_final_gate.exchange_write_action is False
    decision_by_family = {item.family: item for item in state.production_action_result_matrix}
    trend_decision = decision_by_family["Trend"]
    assert not hasattr(trend_decision, "decision")
    assert trend_decision.command_result == "do_not_execute"
    assert trend_decision.selection_status == "not_selected_for_live_action"
    assert trend_decision.reason == "backend_final_gate_not_actionable"
    assert trend_decision.owner_scope_status == "complete_dry_run_only"
    assert trend_decision.final_gate_reason == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    assert "final_gate_actionable_true" in trend_decision.missing_evidence
    assert "execution_intent" in trend_decision.missing_evidence
    assert trend_decision.live_action_taken is False
    assert trend_decision.backend_actionable is False
    assert trend_decision.owner_action_enabled is False
    assert trend_decision.may_execute_live is False
    assert trend_decision.creates_authorization is False
    assert trend_decision.creates_execution_intent is False
    assert trend_decision.starts_runtime is False
    assert trend_decision.starts_strategy_execution is False
    assert trend_decision.places_order is False
    assert trend_decision.mutates_pg is False
    assert trend_decision.exchange_write_action is False
    completion_by_family = {item.family: item for item in state.family_completion_matrix}
    assert completion_by_family["Trend"].completion_status == "actionable"
    assert "AuthorizationDraft" in completion_by_family["Trend"].completed_stages
    assert completion_by_family["Trend"].blocked_stage_statuses["BoundedLiveAuthorization"] == (
        "blocked_backend_final_gate"
    )
    assert "scope_review=complete_dry_run_only" in completion_by_family["Trend"].evidence_refs
    assert completion_by_family["Trend"].places_order is False
    eligibility_by_family = {item.family: item for item in state.live_action_eligibility_matrix}
    trend_eligibility = eligibility_by_family["Trend"]
    trend_checks = {check.code: check for check in trend_eligibility.checks}
    assert trend_eligibility.eligibility == "not_eligible"
    assert not hasattr(trend_eligibility, "decision")
    assert trend_eligibility.eligibility_result == "scope_complete_but_backend_final_gate_blocked"
    assert trend_checks["owner_scope_complete"].status == "pass"
    assert trend_checks["official_action_api_candidate_supported"].status == "pass"
    assert trend_checks["backend_final_gate_actionable"].status == "block"
    assert trend_eligibility.places_order is False
    acceptance_by_item = {item.item: item for item in state.acceptance_evidence_matrix}
    assert acceptance_by_item["owner_risk_scope_review"].status == "PASS_WITH_CONSTRAINT"
    assert acceptance_by_item["backend_final_gate_preflight"].status == "BLOCKED"
    assert acceptance_by_item["official_action_api_candidate_support"].status == "BLOCKED"
    assert acceptance_by_item["live_action_execution"].status == "BLOCKED"
    assert "scope_review.status=complete_dry_run_only" in (
        acceptance_by_item["owner_risk_scope_review"].evidence_refs
    )
    assert "owner_review_handoff_matrix" in (
        acceptance_by_item["owner_risk_scope_review"].evidence_refs
    )
    audit_by_requirement = {
        item.requirement_id: item for item in state.objective_acceptance_audit_matrix
    }
    assert audit_by_requirement["production_capital_boundary"].status == (
        "PASS_WITH_CONSTRAINT"
    )
    assert audit_by_requirement["live_action_result"].status == "BLOCKED"
    assert "scope_review.status=complete_dry_run_only" in audit_by_requirement[
        "production_capital_boundary"
    ].evidence_refs
    assert "production_action_result_matrix" in audit_by_requirement[
        "live_action_result"
    ].evidence_refs
    assert audit_by_requirement["live_action_result"].places_order is False
    assert audit_by_requirement["live_action_result"].mutates_pg is False
    by_projection_status = {item.evidence_method: item for item in state.lifecycle_evidence_statuses}
    assert by_projection_status["BudgetEnvelopeDraft"].row_statuses["Trend"] == (
        "scope_complete_dry_run_only"
    )
    assert by_projection_status["FinalGateDryRun"].row_statuses["Trend"] == "blocked"
    assert by_projection_status["PreExecutionBlockedReview"].row_statuses["Trend"] == "blocked"
    assert by_projection_status["ActionCandidate"].row_statuses["Trend"] == (
        "supported_but_backend_not_actionable"
    )
    assert trend.budget_envelope_draft.status == "scope_complete_dry_run_only"
    assert trend.budget_envelope_draft.evidence_method == "BudgetEnvelopeDraft"
    assert trend.budget_envelope_draft.scope["symbol"] == "SOL/USDT:USDT"
    assert trend.budget_envelope_draft.provided_scope_fields == REQUIRED_OWNER_SCOPE_FIELDS
    assert trend.budget_envelope_draft.missing_scope_fields == []
    assert trend.budget_envelope_draft.symbol == "SOL/USDT:USDT"
    assert trend.budget_envelope_draft.side == "long"
    assert trend.budget_envelope_draft.quantity == "0.1"
    assert trend.budget_envelope_draft.max_notional == "20"
    assert trend.budget_envelope_draft.leverage == "1"
    assert trend.budget_envelope_draft.max_attempts == 1
    assert trend.budget_envelope_draft.protection_mode == "mandatory_tp_sl"
    assert trend.budget_envelope_draft.review_requirement == (
        "post_action_review_required_before_promotion"
    )
    trend_budget_checks = {
        check["code"]: check for check in trend.budget_envelope_draft.validation_checks
    }
    assert trend_budget_checks["owner_scope_complete"]["status"] == "pass"
    assert trend_budget_checks["candidate_scope_matched"]["status"] == "pass"
    assert trend_budget_checks["quantity_provided"]["status"] == "pass"
    assert trend_budget_checks["numbers_source_owner_supplied"]["status"] == "pass"
    assert trend.budget_envelope_draft.not_authorization is True
    assert trend.budget_envelope_draft.not_execution_permission is True
    assert trend.budget_envelope_draft.action_allowed is False
    assert trend.budget_envelope_draft.creates_authorization is False
    assert trend.budget_envelope_draft.creates_execution_intent is False
    assert trend.budget_envelope_draft.places_order is False
    assert trend.budget_envelope_draft.mutates_pg is False
    assert trend.authorization_draft_proposal.status == "scope_reviewed_dry_run_only"
    assert trend.authorization_draft_proposal.scope["symbol"] == "SOL/USDT:USDT"
    assert trend.authorization_draft_proposal.budget_envelope.max_notional == "20"
    assert trend.authorization_draft_proposal.budget_envelope.quantity == "0.1"
    assert trend.authorization_draft_proposal.budget_envelope.action_allowed is False
    assert trend.protection_plan_draft.status == "scope_reviewed_draft_only"
    assert trend.protection_plan_draft.scope["symbol"] == "SOL/USDT:USDT"
    assert "complete_matched_owner_scope" not in trend.protection_plan_draft.missing_fields
    assert "take_profit_price" in trend.protection_plan_draft.missing_fields
    assert "stop_loss_price" in trend.protection_plan_draft.missing_fields
    trend_protection_checks = {
        check["code"]: check for check in trend.protection_plan_draft.validation_checks
    }
    assert trend_protection_checks["owner_scope_complete"]["status"] == "pass"
    assert trend_protection_checks["exchange_protection_orders_created"]["status"] == "not_created"
    assert trend.protection_plan_draft.action_allowed is False
    assert trend.protection_plan_draft.places_order is False
    assert trend.authorization_draft_proposal.protection_plan.status == "scope_reviewed_draft_only"
    assert trend.authorization_draft_proposal.protection_plan.places_order is False
    assert trend.authorization_draft_proposal.confirmation_phrase_required == (
        "I ACCEPT BOUNDED PRODUCTION RISK"
    )
    assert trend.authorization_draft_proposal.not_authorization is True
    assert trend.authorization_draft_proposal.not_execution_permission is True
    assert trend.authorization_draft_proposal.not_order_permission is True
    assert (
        trend.authorization_draft_proposal.official_api_transition_plan.authorization_endpoint
        == "deferred_until_backend_action_contract"
    )
    admission_request_draft = next(
        draft for draft in trend.api_request_drafts if draft.name == "create_admission_request"
    )
    assert admission_request_draft.payload_template["trial_env"] == "live"
    assert admission_request_draft.payload_template["requested_execution_mode"] == (
        "owner_confirm_each_entry"
    )
    account_facts = admission_request_draft.payload_template["account_facts_snapshot_json"]
    assert isinstance(account_facts, dict)
    assert account_facts["owner_scope"]["symbol"] == "SOL/USDT:USDT"
    assert "admission_evidence_id" in admission_request_draft.unresolved_refs
    assert "pre_action_account_facts_snapshot_ref" in admission_request_draft.unresolved_refs
    assert admission_request_draft.not_submitted is True
    assert admission_request_draft.places_order is False
    assert trend.final_gate_dry_run.reason == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    assert trend.pre_execution_blocked_review.blocked_reason == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    trend_pre_execution_checks = {
        check["code"]: check for check in trend.pre_execution_blocked_review.checks
    }
    assert trend_pre_execution_checks["owner_scope_complete"]["status"] == "pass"
    assert trend_pre_execution_checks["official_action_api_candidate_supported"]["status"] == "pass"
    assert trend.pre_execution_blocked_review.action_allowed is False
    assert trend.final_gate_dry_run.gates[0] == {
        "code": "owner_scope_complete",
        "status": "pass",
    }
    assert trend.final_gate_dry_run.gates[1] == {
        "code": "backend_final_gate_actionable",
        "status": "block",
    }
    assert trend.final_gate_dry_run.gates[2] == {
        "code": "official_action_api_candidate_supported",
        "status": "pass",
    }
    assert trend.action_api_compatibility.candidate_carrier_id == "TF-001-live-readonly-v0"
    assert trend.action_api_compatibility.compatible is True
    assert trend.action_candidate.candidate_carrier_id == "TF-001-live-readonly-v0"
    assert trend.action_candidate.action_allowed is False
    assert "complete_matched_owner_scope_required" not in trend.action_candidate.blockers
    assert "candidate_carrier_not_supported_by_owner_trial_flow" not in trend.action_candidate.blockers
    assert "backend_final_gate_actionable_true_required" in trend.action_candidate.blockers
    assert trend.admission_outcome is not None
    assert trend.admission_outcome.status == "blocked_backend_final_gate"
    assert trend.admission_outcome.may_execute_live is False
    assert "AuthorizationDraft" in trend.admission_outcome.completed_stages
    assert "BoundedLiveAuthorization" in trend.admission_outcome.blocked_stages
    trend_gate_blocker_ids = {item.id for item in trend.gate_blocker_records}
    assert f"{trend.blocker_record.id}-SCOPE" not in trend_gate_blocker_ids
    assert f"{trend.blocker_record.id}-ACTION-API" not in trend_gate_blocker_ids
    assert f"{trend.blocker_record.id}-FINAL-GATE" in trend_gate_blocker_ids
    assert f"{trend.blocker_record.id}-EVIDENCE" in trend_gate_blocker_ids
    by_stage = {stage.stage: stage for stage in trend.chain_stage_states}
    assert by_stage["AuthorizationDraft"].status == "scope_reviewed_dry_run_only"
    assert by_stage["BoundedLiveAuthorization"].status == "blocked_backend_final_gate"
    assert by_stage["ExecutionIntent"].status == "not_created"
    assert by_stage["Entry"].status == "not_executed"
    assert by_stage["TP/SL"].status == "draft_required_mandatory_tp_sl"
    assert trend.backend_actionable is False
    assert trend.owner_action_enabled is False
    assert trend.final_gate_dry_run.creates_execution_intent is False
    assert trend.final_gate_dry_run.places_order is False


def test_scoped_dry_run_examples_bind_all_families_without_actions():
    base_state = build_production_strategy_family_admission_state(now_ms=1770000000000)

    assert len(base_state.scoped_dry_run_examples) == 3
    for example in base_state.scoped_dry_run_examples:
        scoped_state = build_production_strategy_family_admission_state(
            owner_scope=example.owner_scope_query,
            now_ms=1770000000000,
        )

        row = next(item for item in scoped_state.families if item.family == example.family)
        assert scoped_state.scope_review.status == example.expected_scope_status
        assert scoped_state.scope_review.matched_candidate is True
        assert row.scope_review.status == example.expected_scope_status
        assert row.scope_review.matched_candidate is True
        assert row.budget_envelope_draft.status == "scope_complete_dry_run_only"
        assert row.authorization_draft_proposal.status == (
            example.expected_authorization_draft_status
        )
        assert row.protection_plan_draft.status == "scope_reviewed_draft_only"
        assert row.final_gate_dry_run.reason == example.expected_final_gate_reason
        assert row.action_api_compatibility.status == example.expected_action_api_status
        assert row.pre_execution_blocked_review.blocked_reason == (
            example.expected_final_gate_reason
        )
        assert row.backend_actionable is False
        assert row.owner_action_enabled is False
        assert row.authorization_draft_proposal.not_authorization is True
        assert row.authorization_draft_proposal.not_execution_permission is True
        assert row.authorization_draft_proposal.not_order_permission is True
        assert row.budget_envelope_draft.action_allowed is False
        assert row.budget_envelope_draft.creates_authorization is False
        assert row.budget_envelope_draft.creates_execution_intent is False
        assert row.budget_envelope_draft.places_order is False
        assert row.budget_envelope_draft.mutates_pg is False
        assert row.action_candidate.action_allowed is False
        assert row.action_candidate.backend_actionable is False
        assert row.action_candidate.owner_action_enabled is False
        assert row.action_candidate.creates_authorization is False
        assert row.action_candidate.creates_execution_intent is False
        assert row.action_candidate.places_order is False
        assert row.action_candidate.mutates_pg is False
        assert row.pre_execution_blocked_review.action_allowed is False
        assert row.pre_execution_blocked_review.owner_action_enabled is False
        assert row.pre_execution_blocked_review.creates_execution_intent is False
        assert row.pre_execution_blocked_review.places_order is False
        assert row.pre_execution_blocked_review.mutates_pg is False
        assert row.final_gate_dry_run.creates_execution_intent is False
        assert row.final_gate_dry_run.places_order is False
        assert row.execution_intent_state == "not_created"
        assert row.entry_state == "not_executed"
        gate_blocker_ids = {item.id for item in row.gate_blocker_records}
        assert f"{row.blocker_record.id}-SCOPE" not in gate_blocker_ids
        if example.family in {"Trend", "Mean reversion"}:
            assert f"{row.blocker_record.id}-ACTION-API" not in gate_blocker_ids
        else:
            assert f"{row.blocker_record.id}-ACTION-API" in gate_blocker_ids
        assert f"{row.blocker_record.id}-FINAL-GATE" in gate_blocker_ids
        eligibility = next(
            item for item in scoped_state.live_action_eligibility_matrix if item.family == example.family
        )
        checks = {check.code: check for check in eligibility.checks}
        assert eligibility.eligibility_result == example.expected_eligibility_result
        assert checks["owner_scope_complete"].status == "pass"
        assert checks["official_action_api_candidate_supported"].status == (
            "pass" if example.family in {"Trend", "Mean reversion"} else "block"
        )
        assert checks["backend_final_gate_actionable"].status == "block"
        assert eligibility.backend_actionable is False
        assert eligibility.owner_action_enabled is False
        assert eligibility.may_execute_live is False
        assert eligibility.creates_authorization is False
        assert eligibility.creates_execution_intent is False
        assert eligibility.starts_runtime is False
        assert eligibility.starts_strategy_execution is False
        assert eligibility.places_order is False
        assert eligibility.mutates_pg is False
        packet = next(
            item for item in scoped_state.owner_authorization_artifact_matrix if item.family == example.family
        )
        assert packet.status == "scope_reviewed_dry_run_only"
        assert packet.owner_scope_status == "complete_dry_run_only"
        assert packet.not_authorization is True
        assert packet.not_execution_permission is True
        assert packet.not_order_permission is True
        assert packet.creates_authorization is False
        assert packet.creates_execution_intent is False
        assert packet.places_order is False
        assert packet.mutates_pg is False


def test_incomplete_owner_scope_remains_blocked_with_missing_fields():
    state = build_production_strategy_family_admission_state(
        owner_scope={
            "family": "Mean reversion",
            "strategy_family_id": "MR-001-live-readonly-v0",
            "carrier_id": "MR-001-live-readonly-v0",
            "symbol": "ETH/USDT:USDT",
            "side": "long",
        },
        now_ms=1770000000000,
    )

    assert state.scope_review.status == "incomplete"
    assert "quantity" in state.scope_review.missing_fields
    assert "max_notional" in state.scope_review.missing_fields
    mr = next(item for item in state.families if item.family == "Mean reversion")
    assert mr.scope_review.status == "incomplete"
    assert mr.budget_envelope_draft.status == "scope_incomplete_no_numbers_fabricated"
    assert mr.budget_envelope_draft.scope["symbol"] == "ETH/USDT:USDT"
    assert mr.budget_envelope_draft.provided_scope_fields == ["symbol", "side"]
    assert "quantity" in mr.budget_envelope_draft.missing_scope_fields
    assert "max_notional" in mr.budget_envelope_draft.missing_scope_fields
    assert mr.budget_envelope_draft.quantity is None
    assert mr.budget_envelope_draft.max_notional is None
    incomplete_budget_checks = {
        check["code"]: check for check in mr.budget_envelope_draft.validation_checks
    }
    assert incomplete_budget_checks["owner_scope_complete"]["status"] == "block"
    assert incomplete_budget_checks["quantity_provided"]["status"] == "missing"
    assert incomplete_budget_checks["max_notional_provided"]["status"] == "missing"
    assert mr.budget_envelope_draft.action_allowed is False
    assert mr.pre_execution_blocked_review.blocked_reason == "owner_scope_incomplete_or_unmatched"
    assert mr.final_gate_dry_run.gates[0] == {
        "code": "owner_scope_complete",
        "status": "block",
    }


def test_mismatched_owner_scope_does_not_bind_to_unsupported_candidate():
    state = build_production_strategy_family_admission_state(
        owner_scope={
            "family": "Volatility expansion",
            "strategy_family_id": "VB-001-live-readonly-v0",
            "carrier_id": "VB-001-live-readonly-v0",
            "symbol": "BNB/USDT:USDT",
            "side": "long",
            "quantity": "0.01",
            "max_notional": "20",
            "leverage": "1",
            "max_attempts": 1,
            "protection_mode": "mandatory_tp_sl",
            "review_requirement": "post_action_review_required_before_promotion",
        },
        now_ms=1770000000000,
    )

    assert state.scope_review.status == "candidate_mismatch"
    vol = next(item for item in state.families if item.family == "Volatility expansion")
    assert vol.scope_review.status == "candidate_mismatch"
    assert "symbol not supported by candidate" in vol.scope_review.mismatches
    assert vol.backend_actionable is False


def test_product_backbone_represents_bnb_trend_mr_and_volatility_samples():
    state = build_production_strategy_family_admission_state(now_ms=1770000000000)

    assert state.product_backbone.version == "brc_product_backbone_v0_3"
    assert "ActionCandidate" in state.product_backbone.product_chain
    assert "FinalGate preview" in state.product_backbone.product_chain
    assert state.product_backbone.no_action_guarantee["places_order"] is False
    assert state.trading_console_candidate_action_read_model.product_surface == (
        "owner_action_entry"
    )
    assert "documentation_surface" in state.trading_console_candidate_action_read_model.never_show_as
    assert "code_explanation" in state.trading_console_candidate_action_read_model.never_show_as

    examples = {
        item.carrier_id: item for item in state.product_backbone.carrier_examples
    }
    assert set(examples) >= {
        "MI-001-BNB-LONG",
        "TF-001-live-readonly-v0",
        "MR-001-live-readonly-v0",
        "VB-001-live-readonly-v0",
    }
    assert examples["MI-001-BNB-LONG"].role == "historical_regression_sample"
    assert examples["MI-001-BNB-LONG"].admission_level == "L0"
    assert examples["MI-001-BNB-LONG"].symbol == "BNB/USDT:USDT"
    assert "fresh Owner authorization required" in examples["MI-001-BNB-LONG"].hard_blockers
    assert examples["TF-001-live-readonly-v0"].role == "owner_confirmed_candidate"
    assert examples["TF-001-live-readonly-v0"].symbol == "SOL/USDT:USDT"
    assert examples["MR-001-live-readonly-v0"].role == "budgeted_autonomy_sample"
    assert examples["MR-001-live-readonly-v0"].budgeted_autonomy_compatible is True
    assert examples["VB-001-live-readonly-v0"].role == "proposal_dry_run_candidate"
    for item in examples.values():
        assert item.may_execute_live is False
        assert item.owner_action_enabled is False

    actionability = {item.family: item for item in state.candidate_actionability}
    assert actionability["Trend"].actionability == "owner_scope_final_gate_ready"
    assert actionability["Trend"].final_gate_preview_available is True
    assert actionability["Trend"].owner_authorization_path_available is True
    assert actionability["Mean reversion"].actionability == "proposal_review"
    assert actionability["Mean reversion"].budget_envelope_compatible is True
    assert actionability["Volatility expansion"].actionability == "proposal_review"
    assert actionability["Volatility expansion"].owner_authorization_path_available is False
    for item in actionability.values():
        assert item.may_execute_live is False
        assert item.owner_action_enabled is False

    previews = {item.strategy_family: item for item in state.final_gate_preview_inputs}
    assert previews["Trend"].status == "ready_for_official_final_gate_preview"
    assert previews["Trend"].symbol == "SOL/USDT:USDT"
    assert "exact Owner execute authorization" in previews["Trend"].required_checks
    assert previews["Trend"].protection_template_id == (
        "protection-template:TF-001-live-readonly-v0"
    )
    assert previews["Mean reversion"].status == "proposal_only"
    assert previews["Mean reversion"].target_notional_usdt == "22"
    assert previews["Volatility expansion"].status == "proposal_only"
    for item in previews.values():
        assert item.operation_layer_required is True
        assert item.may_execute_live is False
        assert item.owner_action_enabled is False

    adapter_results = {item.candidate_id: item for item in state.final_gate_adapter_results}
    assert set(adapter_results) >= {
        "action-candidate:MI-001-BNB-LONG",
        "action-candidate:TF-001-live-readonly-v0",
        "action-candidate:MR-001-live-readonly-v0",
        "action-candidate:VB-001-live-readonly-v0",
    }
    assert adapter_results[
        "action-candidate:MI-001-BNB-LONG"
    ].final_gate_preview.status == "dry_run_only"
    assert adapter_results[
        "action-candidate:TF-001-live-readonly-v0"
    ].final_gate_preview.status == "needs_owner_authorization"
    assert adapter_results[
        "action-candidate:MR-001-live-readonly-v0"
    ].final_gate_preview.status == "needs_budget_authorization"
    assert adapter_results[
        "action-candidate:MR-001-live-readonly-v0"
    ].final_gate_preview.budget_required is True
    assert adapter_results[
        "action-candidate:MR-001-live-readonly-v0"
    ].action_spec.target_notional_usdt == "22"
    assert adapter_results[
        "action-candidate:VB-001-live-readonly-v0"
    ].final_gate_preview.status == "proposal_only"
    for item in adapter_results.values():
        assert item.final_gate_is_execution_gate is True
        assert item.strategy_independent is True
        assert item.no_action_guarantee["places_order"] is False
        assert item.action_spec.may_execute_live is False
        assert item.final_gate_preview.owner_action_enabled is False

    protection = {item.family: item for item in state.protection_templates}
    assert set(protection) == {"Trend", "Volatility expansion", "Mean reversion"}
    assert protection["Trend"].mode == "single_tp_plus_sl"
    assert protection["Mean reversion"].required_components == ["TP", "SL"]
    assert "missing or unknown protection" in (
        protection["Volatility expansion"].hard_blockers_for_live_action
    )
    warnings = {item.classification for item in state.warning_records}
    assert warnings == {
        "strategy_warning",
        "warning",
        "fragile_evidence",
        "insufficient_research",
        "owner_risk_acceptance_required",
    }
    assert state.hard_blocker_records == state.blocker_records
