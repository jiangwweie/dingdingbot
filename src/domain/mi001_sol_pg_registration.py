"""Dry-run PG registration payloads for MI-001 SOL long.

This module builds deterministic, PG-shaped metadata/admission records only. It
does not write PG, start trials, grant execution permission, create execution
intents, create orders, call exchange services, or touch runtime/live runner
paths.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.brc_admission import (
    AdmissionDecision,
    AdmissionDecisionValue,
    AdmissionEvidencePacket,
    AdmissionExecutionMode,
    AdmissionRequest,
    AdmissionRuleConfig,
    AdmissionTrialBinding,
    AdmissionTrialBindingStatus,
    OwnerMarketRegimeInput,
    OwnerRiskAcceptance,
    StrategyFamily,
    StrategyFamilyStatus as AdmissionStrategyFamilyStatus,
    StrategyFamilyVersion,
    TrialConstraintSnapshot,
    TrialConstraintSnapshotStatus,
    TrialEnv,
    TrialStage,
)
from src.domain.strategy_family_registry import (
    StrategyFamilyMetadata,
    StrategyFamilyPlaybookMetadata,
    StrategyFamilyStatus,
    StrategyFamilyType,
)
from src.domain.strategy_family_signal import SignalType


MI001_FAMILY_ID = "MI-001"
MI001_VERSION_ID = "MI-001-smoke-v0"
MI001_CANDIDATE_ID = "MI-001-SOL-LONG"
MI001_PLAYBOOK_ID = "MI-001-SOL-LONG-BT-001"
MI001_SYMBOL = "SOL/USDT:USDT"
MI001_SIDE = "long"

_ACCOUNT_FACTS_REF_REQUIRED = "account-facts:required-before-trial-start-checklist"
_ADMISSION_RULE_CONFIG_ID = "brc-admission-rules-default-v1"
_REPORT_ROOT = "reports/directional-opportunity-broad-smoke-20260529"


class Mi001SolRegistrationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PgRegistrationRecordStatus(Mi001SolRegistrationModel):
    record_type: str = Field(min_length=1, max_length=128)
    pg_table_or_repository: str = Field(min_length=1, max_length=256)
    status: str = Field(min_length=1, max_length=128)
    content_summary: str = Field(min_length=1, max_length=1024)
    runtime_effect: str = Field(min_length=1, max_length=512)
    notes: str = Field(default="", max_length=2048)


class Mi001SolPgRegistrationDryRun(Mi001SolRegistrationModel):
    mode: Literal["dry_run"] = "dry_run"
    strategy_family_metadata: StrategyFamilyMetadata
    playbook_metadata: StrategyFamilyPlaybookMetadata
    admission_strategy_family: StrategyFamily
    admission_strategy_family_version: StrategyFamilyVersion
    admission_rule_config: AdmissionRuleConfig
    evidence_packet: AdmissionEvidencePacket
    owner_market_regime_input: OwnerMarketRegimeInput
    admission_request: AdmissionRequest
    trial_constraint_snapshot: TrialConstraintSnapshot
    admission_decision: AdmissionDecision
    owner_risk_acceptance: OwnerRiskAcceptance
    trial_binding: AdmissionTrialBinding
    record_chain: list[PgRegistrationRecordStatus]
    source_of_truth_status: dict[str, str] = Field(default_factory=dict)
    apply_blockers: list[str] = Field(default_factory=list)
    safety_assertions: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_registration_boundaries(self) -> "Mi001SolPgRegistrationDryRun":
        if self.trial_binding.campaign_id is not None:
            raise ValueError("MI-001 dry-run trial binding must not reference a campaign")
        if self.trial_binding.runtime_carrier_id is not None:
            raise ValueError("MI-001 dry-run trial binding must not reference a runtime carrier")
        if self.trial_binding.binding_status != AdmissionTrialBindingStatus.PLANNED:
            raise ValueError("MI-001 dry-run trial binding must remain planned")
        if self.admission_decision.execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET:
            raise ValueError("MI-001 dry-run must not grant auto execution mode")
        if self.trial_constraint_snapshot.status != TrialConstraintSnapshotStatus.PENDING_RISK_CAPITAL_RESOLUTION:
            raise ValueError("MI-001 dry-run constraints must stay pending until fresh account facts resolve capital")
        return self


def build_mi001_sol_pg_registration_dry_run(*, now_ms: int) -> Mi001SolPgRegistrationDryRun:
    """Build deterministic dry-run payloads for MI-001 SOL long PG registration."""

    family = _strategy_family_metadata(now_ms=now_ms)
    playbook = _playbook_metadata(now_ms=now_ms)
    admission_family = _admission_strategy_family(now_ms=now_ms)
    admission_version = _admission_strategy_family_version(
        playbook_snapshot=playbook.model_dump(mode="json"),
        now_ms=now_ms,
    )
    rule_config = _admission_rule_config(now_ms=now_ms)
    evidence = _evidence_packet(now_ms=now_ms)
    regime = _owner_market_regime_input(now_ms=now_ms)
    request = _admission_request(
        playbook_snapshot=playbook.model_dump(mode="json"),
        now_ms=now_ms,
    )
    constraint = _trial_constraint_snapshot(now_ms=now_ms)
    decision = _admission_decision(
        playbook_snapshot=playbook.model_dump(mode="json"),
        constraints_snapshot=constraint.model_dump(mode="json"),
        now_ms=now_ms,
    )
    acceptance = _owner_risk_acceptance(now_ms=now_ms)
    binding = _trial_binding(
        playbook_snapshot=playbook.model_dump(mode="json"),
        now_ms=now_ms,
    )

    return Mi001SolPgRegistrationDryRun(
        strategy_family_metadata=family,
        playbook_metadata=playbook,
        admission_strategy_family=admission_family,
        admission_strategy_family_version=admission_version,
        admission_rule_config=rule_config,
        evidence_packet=evidence,
        owner_market_regime_input=regime,
        admission_request=request,
        trial_constraint_snapshot=constraint,
        admission_decision=decision,
        owner_risk_acceptance=acceptance,
        trial_binding=binding,
        record_chain=_record_chain(),
        source_of_truth_status={
            "strategy_family": "dry_run_pg_payload_ready",
            "playbook": "dry_run_pg_payload_ready",
            "candidate_admission": "dry_run_pg_payload_ready",
            "broad_smoke_evidence": "dry_run_pg_payload_ready",
            "owner_plan_preparation_approval": "dry_run_pg_payload_ready",
            "trial_constraints": "dry_run_policy_rule_payload_ready",
            "planned_binding": "dry_run_pg_payload_ready",
            "trial_start_approval": "not_granted",
        },
        apply_blockers=[
            "dry-run payload must be applied through an explicit repository transaction or apply helper",
            "separate Owner trial-start approval is still required",
        ],
        safety_assertions={
            "pg_write_performed": False,
            "trial_started": False,
            "exchange_connected": False,
            "real_account_api_called": False,
            "order_created": False,
            "execution_intent_created": False,
            "execution_permission_granted": False,
            "order_capable_record_created": False,
            "runtime_or_live_runner_touched": False,
        },
    )


def _strategy_family_metadata(*, now_ms: int) -> StrategyFamilyMetadata:
    return StrategyFamilyMetadata(
        family_id=MI001_FAMILY_ID,
        version_id=MI001_VERSION_ID,
        family_name="Momentum Impulse",
        family_type=StrategyFamilyType.TREND_FOLLOWING,
        status=StrategyFamilyStatus.ACTIVE_OBSERVATION_CANDIDATE,
        hypothesis=(
            "Strong recent close-to-close momentum may persist over 72h/7d, "
            "especially on high-beta assets."
        ),
        alpha_claim=False,
        carrier_validation=False,
        supported_symbols=[MI001_SYMBOL],
        primary_timeframe="1h",
        context_timeframes=["12h derived from 1h closes", "24h", "72h", "7d review"],
        input_requirements=[
            "1h OHLCV close",
            "open_time_ms",
            "symbol",
            "timeframe",
            "12h prior close",
            "bar-close confirmation",
            "broad smoke evidence packet",
            "Owner review evidence",
        ],
        allowed_signal_types=[SignalType.NO_ACTION, SignalType.WOULD_ENTER, SignalType.INVALID],
        reason_code_taxonomy={
            "mi001_no_action_threshold_not_met": "12h close-to-close impulse threshold is not met.",
            "mi001_would_enter_long_impulse": "12h close-to-close long impulse threshold is met.",
            "mi001_invalid_missing_close_context": "Required 1h close context is missing.",
        },
        review_metrics=[
            "signal_count",
            "24h_mean_forward_return",
            "24h_positive_rate",
            "72h_mean_forward_return",
            "72h_positive_rate",
            "72h_MFE",
            "72h_MAE",
            "7d_mean_forward_return",
            "7d_positive_rate",
            "evidence_completeness",
        ],
        known_failure_modes=[
            "high SOL volatility",
            "large adverse movement before follow-through",
            "right-tail dependency",
            "overlapping impulse signals",
            "momentum exhaustion",
            "no cost/slippage/funding/random-baseline/campaign replay in broad smoke",
        ],
        evidence_requirements=[
            "broad_smoke_summary",
            "Owner acceptance record",
            "bounded trial plan record",
            "not_order = true",
            "not_execution_intent = true",
        ],
        notes=(
            "Equivalent status: trial_candidate_with_known_risks; intended use: "
            "research and bounded trial candidate review only; not alpha proof, "
            "not production-ready, and not automatic execution permission."
        ),
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )


def _playbook_metadata(*, now_ms: int) -> StrategyFamilyPlaybookMetadata:
    return StrategyFamilyPlaybookMetadata(
        playbook_id=MI001_PLAYBOOK_ID,
        family_id=MI001_FAMILY_ID,
        version_id=MI001_VERSION_ID,
        playbook_name="MI-001 SOL Long Bounded Trial Preparation",
        playbook_status=StrategyFamilyStatus.ACTIVE_OBSERVATION_CANDIDATE,
        symbol_universe=[MI001_SYMBOL],
        primary_timeframe="1h",
        context_timeframes=["12h derived from 1h closes"],
        allowed_signal_types=[SignalType.NO_ACTION, SignalType.WOULD_ENTER, SignalType.INVALID],
        review_windows=["24h", "72h", "7d"],
        review_metrics=[
            "signal_count",
            "positive_rate",
            "mean_forward_return",
            "MFE",
            "MAE",
            "known_risk_acceptance",
        ],
        input_requirements=[
            "closed 1h bar",
            "current close",
            "close from 12 hours earlier",
            "historical broad smoke evidence",
        ],
        evidence_requirements=[
            "bar close timestamp",
            "computed 12h return pct",
            "Owner approval evidence",
            "Operation Layer gate evidence before any future trial start",
        ],
        parameter_profile={
            "profile_kind": "metadata_only",
            "candidate_id": MI001_CANDIDATE_ID,
            "variant_label": "12h close-to-close momentum impulse",
            "candidate_role": "bounded_trial_candidate",
            "current_stage": "owner_accepted_for_bounded_trial_plan",
            "signal_threshold_pct": "3",
            "lookback_hours": "12",
            "allowed_direction": MI001_SIDE,
            "bar_close_confirmed_only": True,
        },
        notes=(
            "No capital, order, routing, or execution fields are stored in this playbook metadata."
        ),
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )


def _admission_strategy_family(*, now_ms: int) -> StrategyFamily:
    return StrategyFamily(
        strategy_family_id=MI001_FAMILY_ID,
        family_key="mi001-momentum-impulse",
        name="Momentum Impulse",
        description="MI-001 12h close-to-close momentum impulse family.",
        status=AdmissionStrategyFamilyStatus.INTAKE,
        owner="owner",
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )


def _admission_strategy_family_version(
    *,
    playbook_snapshot: dict[str, Any],
    now_ms: int,
) -> StrategyFamilyVersion:
    return StrategyFamilyVersion(
        strategy_family_version_id=f"{MI001_CANDIDATE_ID}-admission-v1",
        strategy_family_id=MI001_FAMILY_ID,
        version=1,
        hypothesis="Large 12h close-to-close SOL impulse may continue over 72h/7d.",
        market_structure="High-beta SOL impulse continuation candidate from broad smoke.",
        entry_logic_family="Closed 1h bar; compare current close with close 12 hours earlier; long when return >= 3 percent.",
        exit_logic_family="Not defined by registration; future bounded trial review only.",
        risk_model="Dedicated-subaccount risk capital policy must be resolved from fresh account facts before trial start.",
        supported_symbols=[MI001_SYMBOL],
        supported_timeframes=["1h"],
        required_data=["1h OHLCV", "12h prior close", "bar-close timestamp"],
        required_execution_capabilities=[],
        known_failure_modes=[
            "high volatility",
            "large adverse movement",
            "overlapping signals",
            "momentum exhaustion",
            "broad smoke lacks cost/slippage/funding/random-baseline/campaign replay",
        ],
        regime_contract_json={
            "candidate_id": MI001_CANDIDATE_ID,
            "side": MI001_SIDE,
            "research_stage": "owner_accepted_for_bounded_trial_plan",
            "trial_start_approved": False,
        },
        safeguards_json=_safeguards(),
        degradation_policy_json={
            "missing_account_facts": "block_trial_start",
            "stale_account_facts": "block_trial_start",
            "operation_layer_gate_unavailable": "block_trial_start",
            "kill_switch_unavailable": "block_trial_start",
        },
        playbook_id=MI001_PLAYBOOK_ID,
        playbook_catalog_snapshot_json=playbook_snapshot,
        created_at_ms=now_ms,
        created_by="owner",
        is_current=True,
    )


def _admission_rule_config(*, now_ms: int) -> AdmissionRuleConfig:
    return AdmissionRuleConfig(
        admission_rule_config_id=_ADMISSION_RULE_CONFIG_ID,
        config_key="brc-mi001-sol-registration-dry-run",
        version=1,
        status="active",
        rule_details_json={
            "registration_mode": "dry_run",
            "requires_fresh_account_facts_before_trial_start_checklist": True,
            "requires_separate_trial_start_approval": True,
        },
        system_boundaries_json={
            "no_trial_start": True,
            "no_runtime_start": True,
            "no_order": True,
            "no_execution_intent": True,
            "no_exchange_call": True,
            "no_auto_execution": True,
        },
        relaxable_safeguards_json={},
        created_at_ms=now_ms,
        created_by="system",
    )


def _evidence_packet(*, now_ms: int) -> AdmissionEvidencePacket:
    return AdmissionEvidencePacket(
        evidence_packet_id=f"{MI001_CANDIDATE_ID}-broad-smoke-evidence-v1",
        strategy_family_version_id=f"{MI001_CANDIDATE_ID}-admission-v1",
        payload_json={
            "candidate_id": MI001_CANDIDATE_ID,
            "strategy_family_id": MI001_FAMILY_ID,
            "variant_label": "12h close-to-close momentum impulse",
            "symbol": MI001_SYMBOL,
            "side": MI001_SIDE,
            "source_reports": {
                "evidence": f"{_REPORT_ROOT}/evidence.md",
                "owner_acceptance": f"{_REPORT_ROOT}/owner_acceptance_mi001_sol_long.md",
                "bounded_trial_plan": f"{_REPORT_ROOT}/bounded_trial_plan_mi001_sol_long.md",
            },
            "broad_smoke_summary": {
                "signal_count": 8135,
                "24h_mean_forward_return": "0.6373",
                "24h_positive_rate": "0.5019",
                "72h_mean_forward_return": "1.9531",
                "72h_positive_rate": "0.5175",
                "72h_MFE": "10.2580",
                "72h_MAE": "-7.8922",
                "7d_mean_forward_return": "4.7372",
                "7d_positive_rate": "0.5398",
            },
            "limitations": [
                "no costs",
                "no slippage",
                "no funding",
                "no random baseline",
                "no campaign replay",
                "research-only",
            ],
            "not_order": True,
            "not_execution_intent": True,
        },
        mandatory_complete=True,
        created_at_ms=now_ms,
        created_by="owner",
    )


def _owner_market_regime_input(*, now_ms: int) -> OwnerMarketRegimeInput:
    return OwnerMarketRegimeInput(
        owner_market_regime_input_id=f"{MI001_CANDIDATE_ID}-owner-regime-v1",
        current_regime="high_beta_momentum_candidate",
        confidence="medium",
        rationale="Owner accepted MI-001 SOL long for bounded trial plan preparation only.",
        market_facts_snapshot_json={
            "source": "broad_smoke_review_artifacts",
            "reports_root": _REPORT_ROOT,
            "research_only": True,
        },
        created_at_ms=now_ms,
        created_by="owner",
    )


def _admission_request(
    *,
    playbook_snapshot: dict[str, Any],
    now_ms: int,
) -> AdmissionRequest:
    return AdmissionRequest(
        admission_request_id=f"{MI001_CANDIDATE_ID}-admission-request-v1",
        strategy_family_version_id=f"{MI001_CANDIDATE_ID}-admission-v1",
        evidence_packet_id=f"{MI001_CANDIDATE_ID}-broad-smoke-evidence-v1",
        owner_market_regime_input_id=f"{MI001_CANDIDATE_ID}-owner-regime-v1",
        trial_env=TrialEnv.LIVE,
        trial_stage=TrialStage.FUNDED_VALIDATION,
        requested_execution_mode=AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY,
        requested_risk_profile="dedicated_subaccount_micro",
        admission_rule_config_id=_ADMISSION_RULE_CONFIG_ID,
        account_facts_snapshot_ref=_ACCOUNT_FACTS_REF_REQUIRED,
        account_facts_snapshot_json={
            "source": "runtime_cached_account_snapshot_required_before_trial_start_checklist",
            "truth_level": "cached_exchange_read_required_before_trial_start_checklist",
            "account_status": "not_read_by_registration_dry_run",
            "reconciliation_status": {"status": "required_before_trial_start_checklist"},
            "unknown_unmanaged_counts": {
                "orders": "required_before_trial_start_checklist",
                "positions": "required_before_trial_start_checklist",
            },
            "account_equity_source": "cached AccountSnapshot.total_balance",
            "available_margin_source": "cached AccountSnapshot.available_balance",
            "real_account_api_called_by_registration": False,
            "risk_capital_policy": {
                "risk_policy_version": "mi001-dedicated-subaccount-v1",
                "capital_source": "dedicated_subaccount",
                "trial_risk_capital_rule": "current_dedicated_subaccount_equity",
                "max_total_loss_rule": "current_dedicated_subaccount_equity",
                "max_notional_rule": (
                    "min(current_dedicated_subaccount_equity * 5, "
                    "available_margin * 5, operation_layer_notional_cap_if_exists)"
                ),
                "max_leverage": 5,
                "max_attempts": 3,
                "concrete_amounts_resolved": False,
                "warnings": ["concrete capital must be resolved by the trial_start_checklist"],
                "limitations": ["trial start still requires separate Owner approval"],
            },
        },
        playbook_id=MI001_PLAYBOOK_ID,
        playbook_catalog_snapshot_json=playbook_snapshot,
        created_at_ms=now_ms,
        requested_by="owner",
    )


def _trial_constraint_snapshot(*, now_ms: int) -> TrialConstraintSnapshot:
    constraints = {
        "source": "mi001_sol_registration_dry_run",
        "candidate_id": MI001_CANDIDATE_ID,
        "capital_source": "dedicated_subaccount",
        "trial_risk_capital_rule": "current_dedicated_subaccount_equity",
        "max_total_loss_rule": "current_dedicated_subaccount_equity",
        "max_leverage": 5,
        "max_notional_rule": (
            "min(current_dedicated_subaccount_equity * 5, "
            "available_margin * 5 if available, operation_layer_notional_cap_if_exists)"
        ),
        "allowed_symbols": [MI001_SYMBOL],
        "allowed_symbol": MI001_SYMBOL,
        "allowed_side": MI001_SIDE,
        "allowed_candidate": MI001_FAMILY_ID,
        "max_attempts": 3,
        "one_active_trial_position": True,
        **_safeguards(),
        "blockers": [
            "fresh account facts required before trial_start_checklist",
            "Operation Layer cap required before trial start",
            "separate Owner trial-start approval required",
        ],
        "warnings": [
            "dry-run payload only; no PG write performed",
            "broad smoke has no cost/slippage/funding/random-baseline/campaign replay",
        ],
    }
    return TrialConstraintSnapshot(
        trial_constraint_snapshot_id=f"{MI001_CANDIDATE_ID}-trial-constraints-v1",
        admission_request_id=f"{MI001_CANDIDATE_ID}-admission-request-v1",
        status=TrialConstraintSnapshotStatus.PENDING_RISK_CAPITAL_RESOLUTION,
        risk_profile="dedicated_subaccount_micro",
        risk_policy_version="mi001-dedicated-subaccount-v1",
        constraints_json=constraints,
        risk_policy_snapshot_json={
            "source": "owner_confirmed_policy",
            "policy_status": "policy_rule_registered_pending_trial_start_facts",
            "capital_source": "dedicated_subaccount",
            "trial_risk_capital_source": "current_subaccount_equity",
            "account_equity_source": "cached AccountSnapshot.total_balance",
            "available_margin_source": "cached AccountSnapshot.available_balance",
            "max_total_loss_rule": "current_dedicated_subaccount_equity",
            "max_notional_rule": constraints["max_notional_rule"],
            "trial_start_requires_separate_owner_approval": True,
            "auto_top_up_allowed": False,
            "system_transfer_allowed": False,
            "system_withdrawal_allowed": False,
            "strategy_self_elevation_allowed": False,
        },
        adapter_result_json={
            "adapter": "MI001SolPgRegistrationDryRunBuilder",
            "resolution": "policy_rules_only_pending_trial_start_account_facts",
            "sizing_computed": False,
            "pg_write_performed": False,
            "order_capable": False,
        },
        created_at_ms=now_ms,
        expires_at_ms=None,
    )


def _admission_decision(
    *,
    playbook_snapshot: dict[str, Any],
    constraints_snapshot: dict[str, Any],
    now_ms: int,
) -> AdmissionDecision:
    return AdmissionDecision(
        admission_decision_id=f"{MI001_CANDIDATE_ID}-admission-decision-v1",
        admission_request_id=f"{MI001_CANDIDATE_ID}-admission-request-v1",
        decision=AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS,
        trial_env=TrialEnv.LIVE,
        trial_stage=TrialStage.FUNDED_VALIDATION,
        strategy_family_version_id=f"{MI001_CANDIDATE_ID}-admission-v1",
        playbook_id=MI001_PLAYBOOK_ID,
        playbook_catalog_snapshot_json=playbook_snapshot,
        owner_market_regime_input_id=f"{MI001_CANDIDATE_ID}-owner-regime-v1",
        evidence_packet_id=f"{MI001_CANDIDATE_ID}-broad-smoke-evidence-v1",
        admission_rule_config_id=_ADMISSION_RULE_CONFIG_ID,
        trial_constraint_snapshot_id=f"{MI001_CANDIDATE_ID}-trial-constraints-v1",
        risk_profile="dedicated_subaccount_micro",
        execution_mode=AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY,
        degradation_applied=False,
        risk_intent_json={
            "candidate_id": MI001_CANDIDATE_ID,
            "allowed_symbol": MI001_SYMBOL,
            "allowed_side": MI001_SIDE,
            "owner_approved_plan_preparation": True,
            "owner_approved_trial_start": False,
            "automatic_execution_approved": False,
        },
        degradation_intent_json={
            "if_account_facts_stale": "no_entry",
            "if_operation_layer_gate_unavailable": "no_entry",
            "if_kill_switch_unavailable": "no_entry",
        },
        blockers_json=[
            "fresh account facts required before trial-start checklist can resolve concrete capital",
            "Operation Layer cap required before trial start",
            "separate Owner trial-start approval required",
        ],
        warnings_json=[
            "Owner approval covers bounded trial plan preparation only",
            "broad smoke evidence is research-only",
        ],
        risk_disclosure_json={
            "known_risks_accepted_for_plan_preparation": True,
            "high_volatility_risk": True,
            "large_MAE_risk": True,
            "right_tail_dependency_risk": True,
            "overlapping_signal_risk": True,
            "not_alpha_proof": True,
            "not_live_ready_by_default": True,
        },
        known_gaps_json={
            "cost_model": "not in broad smoke evidence",
            "slippage_model": "not in broad smoke evidence",
            "funding_model": "not in broad smoke evidence",
            "random_baseline": "not in broad smoke evidence",
            "campaign_replay": "not in broad smoke evidence",
        },
        constraints_snapshot_json=constraints_snapshot,
        owner_risk_acceptance_id=f"{MI001_CANDIDATE_ID}-owner-risk-acceptance-v1",
        expires_at_ms=None,
        created_at_ms=now_ms,
    )


def _owner_risk_acceptance(*, now_ms: int) -> OwnerRiskAcceptance:
    return OwnerRiskAcceptance(
        owner_risk_acceptance_id=f"{MI001_CANDIDATE_ID}-owner-risk-acceptance-v1",
        admission_request_id=f"{MI001_CANDIDATE_ID}-admission-request-v1",
        admission_decision_id=f"{MI001_CANDIDATE_ID}-admission-decision-v1",
        strategy_family_version_id=f"{MI001_CANDIDATE_ID}-admission-v1",
        trial_env=TrialEnv.LIVE,
        trial_stage=TrialStage.FUNDED_VALIDATION,
        account_facts_snapshot_ref=_ACCOUNT_FACTS_REF_REQUIRED,
        risk_profile="dedicated_subaccount_micro",
        risk_policy_snapshot_json={
            "accepted_policy": "dedicated_subaccount_risk_capital",
            "capital_source": "dedicated_subaccount",
            "max_leverage": 5,
            "max_attempts": 3,
            "trial_start_approved": False,
            "automatic_execution_approved": False,
        },
        constraint_snapshot_id=f"{MI001_CANDIDATE_ID}-trial-constraints-v1",
        risk_disclosure_snapshot_json={
            "owner_approved_bounded_trial_plan_preparation": True,
            "owner_accepts_known_risks": True,
            "owner_accepts_dedicated_subaccount_capital_model": True,
            "owner_accepts_max_leverage_5x_policy": True,
            "owner_has_not_approved_trial_start": True,
            "owner_has_not_approved_automatic_execution": True,
        },
        known_gaps_snapshot_json={
            "broad_smoke_limitations": [
                "no costs",
                "no slippage",
                "no funding",
                "no random baseline",
                "no campaign replay",
                "research-only",
            ],
            "fresh_account_facts_required_before_trial_start_checklist": True,
        },
        owner_rationale="Owner accepted MI-001 SOL long for bounded trial plan preparation only.",
        confirmation_phrase="I ACCEPT MI-001 SOL PLAN PREPARATION RISK ONLY",
        confirmation_marker="owner_confirmed_plan_preparation_not_trial_start",
        confirmed_at_ms=now_ms,
        created_at_ms=now_ms,
        created_by="owner",
    )


def _trial_binding(
    *,
    playbook_snapshot: dict[str, Any],
    now_ms: int,
) -> AdmissionTrialBinding:
    return AdmissionTrialBinding(
        binding_id=f"{MI001_CANDIDATE_ID}-planned-binding-v1",
        admission_decision_id=f"{MI001_CANDIDATE_ID}-admission-decision-v1",
        owner_risk_acceptance_id=f"{MI001_CANDIDATE_ID}-owner-risk-acceptance-v1",
        trial_constraint_snapshot_id=f"{MI001_CANDIDATE_ID}-trial-constraints-v1",
        strategy_family_version_id=f"{MI001_CANDIDATE_ID}-admission-v1",
        playbook_id=MI001_PLAYBOOK_ID,
        playbook_catalog_snapshot_json=playbook_snapshot,
        trial_env=TrialEnv.LIVE,
        trial_stage=TrialStage.FUNDED_VALIDATION,
        execution_mode=AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY,
        binding_status=AdmissionTrialBindingStatus.PLANNED,
        campaign_id=None,
        runtime_carrier_id=None,
        created_by_operation_id="dry-run-operation-not-created",
        created_by_preflight_id="dry-run-preflight-not-created",
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )


def _safeguards() -> dict[str, Any]:
    return {
        "no_auto_top_up": True,
        "no_transfer": True,
        "no_withdrawal": True,
        "no_symbol_expansion": True,
        "no_side_expansion": True,
        "no_leverage_expansion_above_5x": True,
        "operation_layer_gate_required": True,
        "kill_switch_required": True,
        "trial_start_requires_separate_owner_approval": True,
        "bypass_operation_layer_allowed": False,
        "strategy_self_elevation_allowed": False,
    }


def _record_chain() -> list[PgRegistrationRecordStatus]:
    return [
        PgRegistrationRecordStatus(
            record_type="strategy_family",
            pg_table_or_repository="brc_strategy_family_registry / PgStrategyFamilyRegistryRepository",
            status="dry_run_payload_ready",
            content_summary="MI-001 metadata, hypothesis, SOL-only symbol universe, broad smoke review requirements.",
            runtime_effect="none",
            notes="No risk capital, order, routing, or runtime authority fields are stored here.",
        ),
        PgRegistrationRecordStatus(
            record_type="playbook",
            pg_table_or_repository="brc_strategy_family_playbooks / PgStrategyFamilyRegistryRepository",
            status="dry_run_payload_ready",
            content_summary="MI-001 SOL long playbook metadata with 12h close-to-close impulse definition.",
            runtime_effect="none",
            notes="Metadata only; not an executable strategy registration.",
        ),
        PgRegistrationRecordStatus(
            record_type="candidate/admission",
            pg_table_or_repository="brc_strategy_families, brc_strategy_family_versions, brc_admission_requests",
            status="dry_run_payload_ready",
            content_summary="MI-001-SOL-LONG candidate, live funded-validation request, owner-confirm-each-entry mode.",
            runtime_effect="none",
            notes="Requested mode is not automatic execution and does not grant permission.",
        ),
        PgRegistrationRecordStatus(
            record_type="evidence_packet",
            pg_table_or_repository="brc_admission_evidence_packets / PgBrcAdmissionRepository",
            status="dry_run_payload_ready",
            content_summary="Broad smoke summary with signal count and 24h/72h/7d outcome metrics.",
            runtime_effect="none",
            notes="Research evidence only; not alpha proof.",
        ),
        PgRegistrationRecordStatus(
            record_type="owner_approval",
            pg_table_or_repository="brc_owner_risk_acceptances / brc_review_decisions",
            status="dry_run_payload_ready",
            content_summary="Owner approved bounded trial plan preparation, not trial start or auto execution.",
            runtime_effect="none",
            notes="Requires PG apply after confirming account facts ref and Owner marker.",
        ),
        PgRegistrationRecordStatus(
            record_type="trial_constraint_snapshot",
            pg_table_or_repository="brc_trial_constraint_snapshots / PgBrcAdmissionRepository",
            status="dry_run_policy_rule_payload_ready",
            content_summary="Dedicated subaccount policy, max leverage 5, max attempts 3, no expansion rules.",
            runtime_effect="none",
            notes="Policy rules can be applied now; concrete capital values are resolved by trial_start_checklist.",
        ),
        PgRegistrationRecordStatus(
            record_type="trial_binding",
            pg_table_or_repository="brc_admission_trial_bindings / PgBrcAdmissionRepository",
            status="dry_run_payload_ready",
            content_summary="Planned binding only, no campaign, no runtime carrier, no order capability.",
            runtime_effect="none",
            notes="Binding remains planned and cannot imply runtime start.",
        ),
    ]
