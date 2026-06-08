"""Generic ActionCandidate to FinalGate preview adapter.

This module defines the non-live backend boundary between candidate review,
normalized ActionSpec drafting, and official FinalGate input preparation. It is
pure application logic: it does not read PG, call exchanges, create
authorizations, create execution intents, place orders, or mutate state.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


FinalGatePreviewStatus = Literal[
    "ready_for_final_gate",
    "blocked_before_final_gate",
    "needs_owner_authorization",
    "needs_budget_authorization",
    "needs_account_facts",
    "needs_reconciliation_facts",
    "blocked_by_position_conflict",
    "blocked_by_open_order_conflict",
    "blocked_by_missing_protection_template",
    "blocked_by_scope_mismatch",
    "proposal_only",
    "dry_run_only",
]

ACTION_SPEC_REQUIRED_FIELDS = [
    "carrier_id",
    "symbol",
    "side",
    "max_notional",
    "leverage",
    "max_attempts",
    "protection_mode",
    "review_requirement",
]

STRATEGY_WARNING_CODES = {
    "weak strategy evidence",
    "fragile_evidence",
    "insufficient_research",
    "owner_risk_acceptance_required",
    "weak current alpha proof",
    "regime uncertainty",
    "false continuation",
    "fake breakout",
    "news wick",
    "low-volume breakout",
    "catching falling knife",
    "range break into trend",
    "liquidity wick",
    "incomplete signal markers",
    "fee/funding/slippage gaps",
    "incomplete review UI",
    "non-core read-model degradation",
}


class ActionSpecFinalGateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionCandidateAdapterInput(ActionSpecFinalGateModel):
    candidate_id: Optional[str] = None
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    admission_level: Optional[str] = None
    candidate_status: Optional[str] = None
    action_registry_supported: bool = False
    proposal_role: str = "unknown"
    dry_run_only: bool = False
    warnings: list[str] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ActionSpecDraftInput(ActionSpecFinalGateModel):
    action_spec_id: Optional[str] = None
    status: Optional[str] = None
    family: Optional[str] = None
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    admission_level: Optional[str] = None
    action_registry_supported: bool = False
    proposal_role: str = "unknown"
    market_regime: Optional[str] = None
    sizing_mode: str = "fixed_quantity"
    action_candidate_ref: Optional[str] = None
    exact_scope_required: bool = True
    supported_symbols: list[str] = Field(default_factory=list)
    supported_sides: list[str] = Field(default_factory=list)
    symbol: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[str] = None
    target_notional_usdt: Optional[str] = None
    computed_quantity: Optional[str] = None
    estimated_notional_usdt: Optional[str] = None
    market_rule_snapshot: dict[str, Any] = Field(default_factory=dict)
    validation_result: dict[str, Any] = Field(default_factory=dict)
    suggested_minimum_notional_usdt: Optional[str] = None
    suggested_quantity: Optional[str] = None
    max_notional: Optional[str] = None
    leverage: Optional[str] = None
    max_attempts: Optional[int] = None
    protection_mode: Optional[str] = None
    review_requirement: Optional[str] = None
    budget_envelope_ref: Optional[str] = None
    owner_authorization_ref: Optional[str] = None
    sizing_source: Optional[str] = None
    recommended_quantity: Optional[str] = None
    recommended_max_notional: Optional[str] = None
    recommended_total_budget: Optional[str] = None
    budget_owner_confirmation_required: bool = True
    budget_recommendation_status: Optional[str] = None
    protection_template: dict[str, Any] = Field(default_factory=dict)
    review_template: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    research_quality_status: str = "warning"
    risk_disclosure_classifications: list[str] = Field(default_factory=list)
    owner_risk_acceptance_required: bool = True
    owner_risk_acceptance_status: str = "required"
    owner_risk_acceptance_may_override: list[str] = Field(default_factory=list)
    owner_risk_acceptance_never_overrides: list[str] = Field(default_factory=list)
    owner_risk_acceptance_cannot_override_execution_safety_gates: bool = True
    hard_blockers: list[str] = Field(default_factory=list)
    final_gate_adapter_ref: Optional[str] = None
    action_entry_payload_ref: Optional[str] = None
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False


class FinalGateFactInput(ActionSpecFinalGateModel):
    owner_authorization_ref: Optional[str] = None
    budget_authorization_ref: Optional[str] = None
    account_facts_ref: Optional[str] = None
    reconciliation_facts_ref: Optional[str] = None
    operation_layer_ref: Optional[str] = None
    runtime_guard_ref: Optional[str] = None
    active_position_conflict: bool = False
    open_order_conflict: bool = False
    pg_exchange_disagreement: bool = False
    account_facts_stale: bool = False
    reconciliation_facts_stale: bool = False
    gks_blocked: bool = False
    operation_layer_bypass_detected: bool = False


class ActionSpecValidationIssue(ActionSpecFinalGateModel):
    code: str
    severity: Literal["warning", "hard_blocker"]
    field: Optional[str] = None
    message: str
    retry_condition: str


class NormalizedActionSpec(ActionSpecFinalGateModel):
    action_spec_id: str
    candidate_id: str
    family: str
    strategy_family_id: Optional[str] = None
    carrier_id: Optional[str] = None
    admission_level: Optional[str] = None
    status: Literal["valid", "proposal_only", "dry_run_only", "invalid"]
    action_registry_supported: bool
    proposal_role: str
    symbol: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[str] = None
    target_notional_usdt: Optional[str] = None
    computed_quantity: Optional[str] = None
    estimated_notional_usdt: Optional[str] = None
    max_notional: Optional[str] = None
    leverage: Optional[str] = None
    max_attempts: Optional[int] = None
    protection_mode: Optional[str] = None
    review_requirement: Optional[str] = None
    budget_envelope_ref: Optional[str] = None
    owner_authorization_ref: Optional[str] = None
    protection_template: dict[str, Any] = Field(default_factory=dict)
    review_template: dict[str, Any] = Field(default_factory=dict)
    validation_issues: list[ActionSpecValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    research_quality_status: str = "warning"
    risk_disclosure_classifications: list[str] = Field(default_factory=list)
    owner_risk_acceptance_required: bool = True
    owner_risk_acceptance_status: str = "required"
    owner_risk_acceptance_may_override: list[str] = Field(default_factory=list)
    owner_risk_acceptance_never_overrides: list[str] = Field(default_factory=list)
    owner_risk_acceptance_cannot_override_execution_safety_gates: bool = True
    hard_blockers: list[str] = Field(default_factory=list)
    official_final_gate_required: Literal[True] = True
    operation_layer_required: Literal[True] = True
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False


class FinalGatePreview(ActionSpecFinalGateModel):
    preview_id: str
    action_spec_id: str
    candidate_id: str
    status: FinalGatePreviewStatus
    product_message: str
    disabled_reason: str
    authorization_required: bool
    budget_required: bool
    account_facts_required: bool
    reconciliation_facts_required: bool
    protection_required: bool
    warnings: list[str] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)
    validation_issues: list[ActionSpecValidationIssue] = Field(default_factory=list)
    required_final_gate_checks: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    official_final_gate_boundary: str = "official_final_gate_only"
    operation_layer_required: Literal[True] = True
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False


class ActionSpecFinalGateAdapterResult(ActionSpecFinalGateModel):
    adapter_id: str = "action_spec_final_gate_adapter_v0_1"
    candidate_id: str
    action_spec: NormalizedActionSpec
    final_gate_preview: FinalGatePreview
    warnings: list[str] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)
    disabled_actionable_state: Literal["disabled_until_official_final_gate"] = (
        "disabled_until_official_final_gate"
    )
    final_gate_is_execution_gate: Literal[True] = True
    strategy_independent: Literal[True] = True
    no_action_guarantee: dict[str, bool] = Field(
        default_factory=lambda: {
            "creates_authorization": False,
            "creates_execution_intent": False,
            "places_order": False,
            "starts_runtime": False,
            "mutates_pg": False,
            "exchange_write_action": False,
        }
    )


class ActionSpecFinalGateAdapterService:
    """Build a non-live ActionSpec and FinalGate preview from a candidate."""

    def adapt(
        self,
        *,
        candidate: ActionCandidateAdapterInput | dict[str, Any],
        action_spec: ActionSpecDraftInput | dict[str, Any],
        facts: FinalGateFactInput | dict[str, Any] | None = None,
    ) -> ActionSpecFinalGateAdapterResult:
        candidate_input = (
            candidate
            if isinstance(candidate, ActionCandidateAdapterInput)
            else ActionCandidateAdapterInput.model_validate(candidate)
        )
        spec_input = (
            action_spec
            if isinstance(action_spec, ActionSpecDraftInput)
            else ActionSpecDraftInput.model_validate(action_spec)
        )
        fact_input = (
            facts
            if isinstance(facts, FinalGateFactInput)
            else FinalGateFactInput.model_validate(facts or {})
        )
        normalized = self._normalize_action_spec(
            candidate=candidate_input,
            action_spec=spec_input,
        )
        preview = self._build_preview(
            candidate=candidate_input,
            action_spec=normalized,
            facts=fact_input,
        )
        return ActionSpecFinalGateAdapterResult(
            candidate_id=normalized.candidate_id,
            action_spec=normalized,
            final_gate_preview=preview,
            warnings=preview.warnings,
            hard_blockers=preview.hard_blockers,
        )

    def _normalize_action_spec(
        self,
        *,
        candidate: ActionCandidateAdapterInput,
        action_spec: ActionSpecDraftInput,
    ) -> NormalizedActionSpec:
        candidate_id = (
            candidate.candidate_id
            or candidate.carrier_id
            or action_spec.carrier_id
            or candidate.family
        )
        action_spec_id = action_spec.action_spec_id or f"action-spec:{candidate_id}"
        issues = _validate_action_spec_fields(action_spec)
        warnings = _dedupe([*candidate.warnings, *action_spec.warnings])
        hard_blockers = _dedupe(
            [
                *candidate.hard_blockers,
                *action_spec.hard_blockers,
                *[
                    issue.code
                    for issue in issues
                    if issue.severity == "hard_blocker"
                ],
            ]
        )
        status = _normalized_action_spec_status(
            candidate=candidate,
            action_spec=action_spec,
            issues=issues,
        )
        return NormalizedActionSpec(
            action_spec_id=action_spec_id,
            candidate_id=str(candidate_id),
            family=action_spec.family or candidate.family,
            strategy_family_id=action_spec.strategy_family_id or candidate.strategy_family_id,
            carrier_id=action_spec.carrier_id or candidate.carrier_id,
            admission_level=action_spec.admission_level or candidate.admission_level,
            status=status,
            action_registry_supported=(
                action_spec.action_registry_supported
                or candidate.action_registry_supported
            ),
            proposal_role=action_spec.proposal_role or candidate.proposal_role,
            symbol=action_spec.symbol,
            side=action_spec.side,
            quantity=action_spec.quantity,
            target_notional_usdt=action_spec.target_notional_usdt,
            computed_quantity=action_spec.computed_quantity,
            estimated_notional_usdt=action_spec.estimated_notional_usdt,
            max_notional=action_spec.max_notional,
            leverage=action_spec.leverage,
            max_attempts=action_spec.max_attempts,
            protection_mode=action_spec.protection_mode,
            review_requirement=action_spec.review_requirement,
            budget_envelope_ref=action_spec.budget_envelope_ref,
            owner_authorization_ref=action_spec.owner_authorization_ref,
            protection_template=dict(action_spec.protection_template),
            review_template=dict(action_spec.review_template),
            validation_issues=issues,
            warnings=warnings,
            research_quality_status=action_spec.research_quality_status,
            risk_disclosure_classifications=list(
                action_spec.risk_disclosure_classifications
            ),
            owner_risk_acceptance_required=action_spec.owner_risk_acceptance_required,
            owner_risk_acceptance_status=action_spec.owner_risk_acceptance_status,
            owner_risk_acceptance_may_override=list(
                action_spec.owner_risk_acceptance_may_override
            ),
            owner_risk_acceptance_never_overrides=list(
                action_spec.owner_risk_acceptance_never_overrides
            ),
            owner_risk_acceptance_cannot_override_execution_safety_gates=(
                action_spec.owner_risk_acceptance_cannot_override_execution_safety_gates
            ),
            hard_blockers=hard_blockers,
        )

    def _build_preview(
        self,
        *,
        candidate: ActionCandidateAdapterInput,
        action_spec: NormalizedActionSpec,
        facts: FinalGateFactInput,
    ) -> FinalGatePreview:
        warnings = _dedupe(
            [
                *[
                    item
                    for item in action_spec.warnings
                    if _is_strategy_warning(item)
                ],
                *[
                    issue.code
                    for issue in action_spec.validation_issues
                    if issue.severity == "warning"
                ],
            ]
        )
        hard_blockers = _dedupe(
            [
                *action_spec.hard_blockers,
                *_fact_hard_blockers(action_spec=action_spec, facts=facts),
            ]
        )
        status = _preview_status(
            candidate=candidate,
            action_spec=action_spec,
            facts=facts,
            hard_blockers=hard_blockers,
        )
        return FinalGatePreview(
            preview_id=f"final-gate-preview:{action_spec.candidate_id}",
            action_spec_id=action_spec.action_spec_id,
            candidate_id=action_spec.candidate_id,
            status=status,
            product_message=_product_message(status),
            disabled_reason=_disabled_reason(status, hard_blockers),
            authorization_required=(
                action_spec.owner_authorization_ref is None
                and action_spec.budget_envelope_ref is None
            ),
            budget_required=action_spec.budget_envelope_ref is not None,
            account_facts_required=facts.account_facts_ref is None or facts.account_facts_stale,
            reconciliation_facts_required=(
                facts.reconciliation_facts_ref is None
                or facts.reconciliation_facts_stale
            ),
            protection_required=True,
            warnings=warnings,
            hard_blockers=hard_blockers,
            validation_issues=action_spec.validation_issues,
            required_final_gate_checks=[
                "exact authorization or BudgetEnvelope scope",
                "account/subaccount freshness",
                "symbol/side/quantity/notional/leverage scope match",
                "budget and daily attempt availability",
                "active position and open order conflict checks",
                "PG/exchange reconciliation agreement",
                "mandatory protection template and price plan",
                "runtime/environment/GKS guard state",
                "Operation Layer handoff",
            ],
            evidence={
                "candidate_id": action_spec.candidate_id,
                "carrier_id": action_spec.carrier_id,
                "family": action_spec.family,
                "strategy_family_id": action_spec.strategy_family_id,
                "action_spec_status": action_spec.status,
                "candidate_status": candidate.candidate_status,
                "account_facts_ref": facts.account_facts_ref,
                "reconciliation_facts_ref": facts.reconciliation_facts_ref,
                "operation_layer_ref": facts.operation_layer_ref,
                "runtime_guard_ref": facts.runtime_guard_ref,
            },
        )


def _validate_action_spec_fields(
    action_spec: ActionSpecDraftInput,
) -> list[ActionSpecValidationIssue]:
    issues: list[ActionSpecValidationIssue] = []
    for field in ACTION_SPEC_REQUIRED_FIELDS:
        if getattr(action_spec, field) in (None, ""):
            issues.append(
                _hard_blocker(
                    code=f"missing_{field}",
                    field=field,
                    message=f"ActionSpec is missing {field}.",
                    retry_condition=f"Regenerate ActionSpec with exact {field}.",
                )
            )
    if not (
        action_spec.quantity
        or action_spec.computed_quantity
        or action_spec.target_notional_usdt
    ):
        issues.append(
            _hard_blocker(
                code="missing_quantity_or_notional",
                field="quantity",
                message="ActionSpec requires quantity, computed_quantity, or target_notional_usdt.",
                retry_condition="Regenerate ActionSpec with exact quantity or notional sizing.",
            )
        )
    if action_spec.side not in (None, "", "long", "short"):
        issues.append(
            _hard_blocker(
                code="invalid_side",
                field="side",
                message="ActionSpec side must be long or short.",
                retry_condition="Use an official carrier side.",
            )
        )
    if action_spec.symbol and action_spec.supported_symbols and action_spec.symbol not in action_spec.supported_symbols:
        issues.append(
            _hard_blocker(
                code="symbol_outside_carrier_scope",
                field="symbol",
                message="ActionSpec symbol is outside carrier supported_symbols.",
                retry_condition="Use an allowed carrier symbol or create a separately governed carrier.",
            )
        )
    if action_spec.side and action_spec.supported_sides and action_spec.side not in action_spec.supported_sides:
        issues.append(
            _hard_blocker(
                code="side_outside_carrier_scope",
                field="side",
                message="ActionSpec side is outside carrier supported_sides.",
                retry_condition="Use the carrier side or create a separately governed carrier.",
            )
        )
    if not action_spec.review_template:
        issues.append(
            _warning(
                code="review_template_not_attached",
                message="ReviewTemplate is not attached to the ActionSpec.",
                retry_condition="Attach ReviewTemplate before promotion decisions.",
            )
        )
    return issues


def _normalized_action_spec_status(
    *,
    candidate: ActionCandidateAdapterInput,
    action_spec: ActionSpecDraftInput,
    issues: list[ActionSpecValidationIssue],
) -> Literal["valid", "proposal_only", "dry_run_only", "invalid"]:
    if candidate.dry_run_only:
        return "dry_run_only"
    if (
        action_spec.status == "proposal_non_action"
        or candidate.candidate_status == "proposal"
        or not (action_spec.action_registry_supported or candidate.action_registry_supported)
    ):
        return "proposal_only"
    if any(issue.severity == "hard_blocker" for issue in issues):
        return "invalid"
    return "valid"


def _fact_hard_blockers(
    *,
    action_spec: NormalizedActionSpec,
    facts: FinalGateFactInput,
) -> list[str]:
    blockers: list[str] = []
    if action_spec.status == "invalid":
        blockers.append("invalid_action_spec")
    if action_spec.status == "proposal_only":
        blockers.append("proposal_only_candidate")
    if action_spec.status == "dry_run_only":
        blockers.append("dry_run_only_candidate")
    if action_spec.owner_authorization_ref is None and action_spec.budget_envelope_ref is None:
        blockers.append("missing_owner_authorization")
    if action_spec.budget_envelope_ref is not None and facts.budget_authorization_ref is None:
        blockers.append("missing_budget_authorization")
    if facts.account_facts_ref is None:
        blockers.append("missing_account_facts")
    if facts.account_facts_stale:
        blockers.append("stale_account_facts")
    if facts.reconciliation_facts_ref is None:
        blockers.append("missing_reconciliation_facts")
    if facts.reconciliation_facts_stale:
        blockers.append("stale_reconciliation_facts")
    if facts.active_position_conflict:
        blockers.append("active_position_conflict")
    if facts.open_order_conflict:
        blockers.append("open_order_conflict")
    if facts.pg_exchange_disagreement:
        blockers.append("pg_exchange_disagreement")
    if _protection_template_incomplete(action_spec.protection_template):
        blockers.append("missing_or_incomplete_protection_template")
    if facts.gks_blocked:
        blockers.append("runtime_or_gks_guard_blocked")
    if facts.operation_layer_bypass_detected or facts.operation_layer_ref is None:
        blockers.append("operation_layer_required")
    return _dedupe(blockers)


def _preview_status(
    *,
    candidate: ActionCandidateAdapterInput,
    action_spec: NormalizedActionSpec,
    facts: FinalGateFactInput,
    hard_blockers: list[str],
) -> FinalGatePreviewStatus:
    if action_spec.status == "proposal_only":
        return "proposal_only"
    if action_spec.status == "dry_run_only" or candidate.dry_run_only:
        return "dry_run_only"
    if any(code in hard_blockers for code in _scope_blocker_codes()):
        return "blocked_by_scope_mismatch"
    if action_spec.owner_authorization_ref is None and action_spec.budget_envelope_ref is None:
        return "needs_owner_authorization"
    if action_spec.budget_envelope_ref is not None and facts.budget_authorization_ref is None:
        return "needs_budget_authorization"
    if facts.account_facts_ref is None or facts.account_facts_stale:
        return "needs_account_facts"
    if facts.reconciliation_facts_ref is None or facts.reconciliation_facts_stale:
        return "needs_reconciliation_facts"
    if facts.active_position_conflict:
        return "blocked_by_position_conflict"
    if facts.open_order_conflict:
        return "blocked_by_open_order_conflict"
    if "missing_or_incomplete_protection_template" in hard_blockers:
        return "blocked_by_missing_protection_template"
    if hard_blockers:
        return "blocked_before_final_gate"
    return "ready_for_final_gate"


def _scope_blocker_codes() -> set[str]:
    return {
        "missing_carrier_id",
        "missing_symbol",
        "missing_side",
        "missing_max_notional",
        "missing_leverage",
        "missing_max_attempts",
        "missing_quantity_or_notional",
        "invalid_side",
        "symbol_outside_carrier_scope",
        "side_outside_carrier_scope",
        "owner_symbol_not_supported_by_carrier",
        "owner_side_not_supported_by_carrier",
        "owner_max_notional_exceeds_budget_envelope",
        "owner_leverage_exceeds_budget_envelope",
        "owner_max_attempts_exceeds_budget_envelope",
        "owner_protection_mode_not_supported",
    }


def _protection_template_incomplete(template: dict[str, Any]) -> bool:
    if not template:
        return True
    if template.get("mode") not in {"single_tp_plus_sl", "fixed_percent_tp_sl", "atr_based_tp_sl", "range_reversion_stop"}:
        return True
    blockers = [str(item) for item in template.get("hard_blockers") or []]
    return any(
        item in blockers
        for item in [
            "TP/SL plan unavailable",
            "protection price source unavailable",
            "reduce-only protection recording unavailable",
        ]
    )


def _product_message(status: FinalGatePreviewStatus) -> str:
    return {
        "ready_for_final_gate": (
            "This candidate can be converted to an ActionSpec, but execution is "
            "disabled until official FinalGate passes."
        ),
        "blocked_before_final_gate": "This candidate is blocked before FinalGate.",
        "needs_owner_authorization": (
            "This candidate can be converted to an ActionSpec, but execution is "
            "disabled until Owner confirmation and official FinalGate pass."
        ),
        "needs_budget_authorization": (
            "This candidate needs BudgetEnvelope authorization before FinalGate."
        ),
        "needs_account_facts": "This candidate is blocked because account facts are missing.",
        "needs_reconciliation_facts": (
            "This candidate is blocked because reconciliation facts are missing."
        ),
        "blocked_by_position_conflict": (
            "This candidate is blocked because an active position conflict exists."
        ),
        "blocked_by_open_order_conflict": (
            "This candidate is blocked because an open order conflict exists."
        ),
        "blocked_by_missing_protection_template": (
            "This candidate is blocked because protection template is incomplete."
        ),
        "blocked_by_scope_mismatch": "This candidate is blocked by ActionSpec scope mismatch.",
        "proposal_only": "This candidate is proposal-only and cannot be authorized for live action.",
        "dry_run_only": "This candidate is dry-run only and cannot be authorized for live action.",
    }[status]


def _disabled_reason(status: FinalGatePreviewStatus, hard_blockers: list[str]) -> str:
    if status == "ready_for_final_gate":
        return "Official FinalGate pass is still required before any execution."
    if hard_blockers:
        return "; ".join(hard_blockers[:5])
    return _product_message(status)


def _is_strategy_warning(value: str) -> bool:
    text = value.strip().lower()
    return text in STRATEGY_WARNING_CODES or any(
        warning in text for warning in STRATEGY_WARNING_CODES
    )


def _warning(
    *,
    code: str,
    message: str,
    retry_condition: str,
    field: Optional[str] = None,
) -> ActionSpecValidationIssue:
    return ActionSpecValidationIssue(
        code=code,
        severity="warning",
        field=field,
        message=message,
        retry_condition=retry_condition,
    )


def _hard_blocker(
    *,
    code: str,
    message: str,
    retry_condition: str,
    field: Optional[str] = None,
) -> ActionSpecValidationIssue:
    return ActionSpecValidationIssue(
        code=code,
        severity="hard_blocker",
        field=field,
        message=message,
        retry_condition=retry_condition,
    )


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result
