"""Backend-owned Candidate-to-Action product loop contract.

This module composes existing ActionCandidate, ActionSpec, FinalGate preview,
Operation Layer handoff, protection, and review read-model artifacts into a
single non-live product loop for the Owner console. It is pure application
logic: it does not read PG, call exchanges, submit Operation Layer requests,
create authorizations, create execution intents, place orders, or mutate state.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class CandidateActionProductLoopModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductLoopStageStatus(CandidateActionProductLoopModel):
    stage: str
    label: str
    status: str
    summary: str


class ProductLoopFactBinding(CandidateActionProductLoopModel):
    code: str
    label: str
    status: Literal[
        "ready",
        "missing_fact",
        "stale",
        "blocked",
        "warning",
        "unavailable",
        "not_applicable",
    ]
    evidence_ref: Optional[str] = None
    retry_condition: Optional[str] = None


class ProductLoopAuthorizationDraft(CandidateActionProductLoopModel):
    mode: Literal[
        "owner_authorization",
        "budget_envelope",
        "historical_dry_run",
        "proposal_only",
        "disabled_by_policy",
    ]
    draft_status: str
    authorization_status: str
    authorization_required: bool
    budget_required: bool
    draft_ref: Optional[str] = None
    official_preflight_endpoint: str = "POST /api/brc/operations/preflight"
    confirmation_required: bool = True
    required_before_submit: list[str] = Field(default_factory=list)
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class ProductLoopBudgetDraft(CandidateActionProductLoopModel):
    status: str
    budget_envelope_ref: Optional[str] = None
    budget_authorization_status: str
    risk_tier: str
    max_notional_per_action: Optional[str] = None
    total_budget: Optional[str] = None
    max_attempts: Optional[int] = None
    owner_confirmation_required: bool = True
    missing_facts: list[str] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)
    action_allowed: Literal[False] = False


class ProductLoopActionSpecDraft(CandidateActionProductLoopModel):
    action_spec_id: str
    status: str
    normalized_status: str
    symbol: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[str] = None
    target_notional_usdt: Optional[str] = None
    computed_quantity: Optional[str] = None
    estimated_notional_usdt: Optional[str] = None
    max_notional: Optional[str] = None
    leverage: Optional[str] = None
    max_attempts: Optional[int] = None
    validation_issues: list[dict[str, Any]] = Field(default_factory=list)
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    places_order: Literal[False] = False


class ProductLoopFinalGateReadiness(CandidateActionProductLoopModel):
    status: str
    preview_status: str
    preview_id: str
    product_message: str
    disabled_reason: str
    required_checks: list[str] = Field(default_factory=list)
    fact_bindings: list[ProductLoopFactBinding] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    stale_facts: list[str] = Field(default_factory=list)
    conflicting_facts: list[str] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    official_final_gate_boundary: str = "official_final_gate_only"
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False


class ProductLoopOperationPreflight(CandidateActionProductLoopModel):
    status: str
    kind: Literal["operation_layer_preflight"] = "operation_layer_preflight"
    operation_type: str = "create_gated_trial_from_admission"
    preflight_endpoint: str = "POST /api/brc/operations/preflight"
    confirm_endpoint: str = "POST /api/brc/operations/{operation_id}/confirm"
    final_gate_dry_run_endpoint: str = (
        "POST /api/brc/owner-trial-flow/live-execution-bridge/dry-run"
    )
    auditable: Literal[True] = True
    not_submitted: Literal[True] = True
    disabled_reason: str
    input_payload_summary: dict[str, Any] = Field(default_factory=dict)
    expected_result_visibility: str = (
        "Operation preflight response and Trading Console refresh"
    )
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    cancels_order: Literal[False] = False
    closes_position: Literal[False] = False
    mutates_exchange: Literal[False] = False


class ProductLoopProtectionDraft(CandidateActionProductLoopModel):
    status: str
    template_id: Optional[str] = None
    mode: Optional[str] = None
    required_components: list[str] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)
    retry_condition: str
    may_execute_live: Literal[False] = False
    places_order: Literal[False] = False


class ProductLoopReviewPlan(CandidateActionProductLoopModel):
    status: str
    template_id: Optional[str] = None
    strategy_family: str
    review_requirement: Optional[str] = None
    required_sections: list[str] = Field(default_factory=list)
    family_review_focus: list[str] = Field(default_factory=list)
    post_action_required: bool = True
    missing_items: list[str] = Field(default_factory=list)


class ProductLoopPostActionReadiness(CandidateActionProductLoopModel):
    status: str
    intent_count: int = 0
    entry_order_count: int = 0
    protection_order_count: int = 0
    review_count: int = 0
    audit_event_count: int = 0
    review_ledger_status: str
    retry_safety: Optional[str] = None


class CandidateActionReadinessLoop(CandidateActionProductLoopModel):
    loop_id: str
    candidate_id: str
    family: str
    carrier_id: Optional[str] = None
    strategy_family_id: Optional[str] = None
    admission_level: Optional[str] = None
    proposal_role: str
    candidate_state: str
    candidate_reason: str
    symbol: Optional[str] = None
    side: Optional[str] = None
    suggested_notional: Optional[str] = None
    max_notional: Optional[str] = None
    leverage: Optional[str] = None
    risk_tier: str
    readiness_state: str
    confirmable_state: Literal[
        "owner_confirmable",
        "budget_confirmable",
        "proposal_only",
        "dry_run_only",
        "blocked",
        "disabled",
    ]
    disabled_reason: str
    next_recommended_action: str
    warnings: list[str] = Field(default_factory=list)
    research_quality_status: str = "warning"
    risk_disclosure_classifications: list[str] = Field(default_factory=list)
    owner_risk_acceptance_required: bool = True
    owner_risk_acceptance_status: str = "required"
    owner_risk_acceptance_may_override: list[str] = Field(default_factory=list)
    owner_risk_acceptance_never_overrides: list[str] = Field(default_factory=list)
    owner_risk_acceptance_cannot_override_execution_safety_gates: bool = True
    hard_blockers: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    stage_statuses: list[ProductLoopStageStatus] = Field(default_factory=list)
    authorization_draft: ProductLoopAuthorizationDraft
    budget_draft: ProductLoopBudgetDraft
    action_spec_draft: ProductLoopActionSpecDraft
    final_gate_readiness: ProductLoopFinalGateReadiness
    operation_layer_preflight: ProductLoopOperationPreflight
    protection_draft: ProductLoopProtectionDraft
    review_plan: ProductLoopReviewPlan
    post_action_readiness: ProductLoopPostActionReadiness
    backend_actionable: Literal[False] = False
    may_execute_live: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False
    exchange_write_action: Literal[False] = False


class CandidateActionProductLoopBundle(CandidateActionProductLoopModel):
    status: Literal["non_live_product_loop_ready"] = "non_live_product_loop_ready"
    loop_version: str = "candidate_action_product_loop_v0_1"
    candidate_action_readiness_loop: list[CandidateActionReadinessLoop]
    selected_candidate_action_readiness_loop: Optional[CandidateActionReadinessLoop] = None
    no_action_guarantee: dict[str, bool] = Field(
        default_factory=lambda: {
            "creates_authorization": False,
            "creates_execution_intent": False,
            "places_order": False,
            "cancels_order": False,
            "closes_position": False,
            "starts_runtime": False,
            "mutates_pg": False,
            "exchange_write_action": False,
        }
    )


def build_candidate_action_product_loop(
    *,
    owner_market_input: dict[str, Any],
    budget_recommendation: dict[str, Any],
    selected_candidate: dict[str, Any],
    candidate_output: list[dict[str, Any]],
    generic_action_specs: list[dict[str, Any]],
    action_entry_payload_contracts: list[dict[str, Any]],
    action_entry_output: list[dict[str, Any]],
    final_gate_adapter_results: list[dict[str, Any]],
    post_action_state: dict[str, Any],
    fact_context: dict[str, Any],
) -> CandidateActionProductLoopBundle:
    """Build the Owner-facing product loop from backend-owned read-model data."""

    risk_tier = str(
        (budget_recommendation.get("risk_tier") or {}).get("tier")
        or owner_market_input.get("risk_tier")
        or "tiny"
    )
    loops: list[CandidateActionReadinessLoop] = []
    selected_carrier_id = _optional_str(selected_candidate.get("carrier_id"))
    selected_family = _optional_str(selected_candidate.get("family"))

    for adapter_result in final_gate_adapter_results:
        action_spec = dict(adapter_result.get("action_spec") or {})
        preview = dict(adapter_result.get("final_gate_preview") or {})
        carrier_id = _optional_str(action_spec.get("carrier_id"))
        family = str(action_spec.get("family") or "Unknown")
        candidate = _match_by_carrier_or_family(candidate_output, carrier_id, family)
        generic_spec = _match_by_carrier_or_family(generic_action_specs, carrier_id, family)
        payload_contract = _match_by_carrier_or_family(
            action_entry_payload_contracts,
            carrier_id,
            family,
        )
        action_entry = _match_by_carrier_or_family(action_entry_output, carrier_id, family)
        loop = _build_candidate_loop(
            adapter_result=adapter_result,
            action_spec=action_spec,
            preview=preview,
            candidate=candidate,
            generic_spec=generic_spec,
            payload_contract=payload_contract,
            action_entry=action_entry,
            budget_recommendation=budget_recommendation,
            post_action_state=post_action_state,
            fact_context=fact_context,
            risk_tier=risk_tier,
        )
        loops.append(loop)

    selected_loop = _first_loop_match(loops, selected_carrier_id, selected_family)
    return CandidateActionProductLoopBundle(
        candidate_action_readiness_loop=loops,
        selected_candidate_action_readiness_loop=selected_loop,
    )


def _build_candidate_loop(
    *,
    adapter_result: dict[str, Any],
    action_spec: dict[str, Any],
    preview: dict[str, Any],
    candidate: dict[str, Any],
    generic_spec: dict[str, Any],
    payload_contract: dict[str, Any],
    action_entry: dict[str, Any],
    budget_recommendation: dict[str, Any],
    post_action_state: dict[str, Any],
    fact_context: dict[str, Any],
    risk_tier: str,
) -> CandidateActionReadinessLoop:
    candidate_id = str(adapter_result.get("candidate_id") or action_spec.get("candidate_id"))
    family = str(action_spec.get("family") or candidate.get("family") or "Unknown")
    carrier_id = _optional_str(action_spec.get("carrier_id") or candidate.get("carrier_id"))
    preview_status = str(preview.get("status") or "final_gate_not_ready")
    budget_required = bool(preview.get("budget_required"))
    authorization_required = bool(preview.get("authorization_required"))
    warnings = _dedupe(
        [
            *[str(item) for item in adapter_result.get("warnings") or []],
            *[str(item) for item in generic_spec.get("warnings") or []],
            *[
                str(item)
                for item in generic_spec.get("risk_disclosure_classifications") or []
            ],
        ]
    )
    hard_blockers = _dedupe(
        [
            *[str(item) for item in adapter_result.get("hard_blockers") or []],
            *[str(item) for item in generic_spec.get("hard_blockers") or []],
        ]
    )
    authorization = _authorization_draft(
        candidate_id=candidate_id,
        carrier_id=carrier_id,
        preview_status=preview_status,
        action_spec=action_spec,
        preview=preview,
        payload_contract=payload_contract,
    )
    budget = _budget_draft(
        action_spec=action_spec,
        preview=preview,
        budget_recommendation=budget_recommendation,
        risk_tier=risk_tier,
    )
    action_spec_draft = _action_spec_draft(action_spec, generic_spec)
    final_gate = _final_gate_readiness(
        action_spec=action_spec,
        preview=preview,
        hard_blockers=hard_blockers,
        warnings=warnings,
        fact_context=fact_context,
        budget_recommendation=budget_recommendation,
    )
    operation_preflight = _operation_preflight(
        candidate_id=candidate_id,
        carrier_id=carrier_id,
        action_spec=action_spec,
        preview=preview,
        final_gate=final_gate,
    )
    protection = _protection_draft(action_spec)
    review = _review_plan(action_spec)
    post_action = _post_action_readiness(post_action_state)
    readiness_state = _readiness_state(preview_status)
    confirmable_state = _confirmable_state(preview_status, authorization_required, budget_required)
    disabled_reason = str(
        preview.get("disabled_reason")
        or operation_preflight.disabled_reason
        or "Official authorization, FinalGate, Operation Layer, protection, and review are required."
    )

    return CandidateActionReadinessLoop(
        loop_id=f"candidate-action-loop:{candidate_id}",
        candidate_id=candidate_id,
        family=family,
        carrier_id=carrier_id,
        strategy_family_id=_optional_str(
            action_spec.get("strategy_family_id") or candidate.get("strategy_family_id")
        ),
        admission_level=_optional_str(
            action_spec.get("admission_level") or candidate.get("admission_level")
        ),
        proposal_role=str(action_spec.get("proposal_role") or "unknown"),
        candidate_state=str(candidate.get("candidate_state") or preview_status),
        candidate_reason=str(
            candidate.get("owner_decision_text")
            or preview.get("product_message")
            or "Candidate awaits Owner review."
        ),
        symbol=_optional_str(action_spec.get("symbol")),
        side=_optional_str(action_spec.get("side")),
        suggested_notional=_optional_str(
            action_spec.get("target_notional_usdt")
            or action_spec.get("estimated_notional_usdt")
            or generic_spec.get("recommended_max_notional")
            or action_spec.get("max_notional")
        ),
        max_notional=_optional_str(action_spec.get("max_notional")),
        leverage=_optional_str(action_spec.get("leverage")),
        risk_tier=risk_tier,
        readiness_state=readiness_state,
        confirmable_state=confirmable_state,
        disabled_reason=disabled_reason,
        next_recommended_action=_next_recommended_action(preview_status, family),
        warnings=warnings,
        research_quality_status=str(generic_spec.get("research_quality_status") or "warning"),
        risk_disclosure_classifications=[
            str(item) for item in generic_spec.get("risk_disclosure_classifications") or []
        ],
        owner_risk_acceptance_required=bool(
            generic_spec.get("owner_risk_acceptance_required", True)
        ),
        owner_risk_acceptance_status=str(
            generic_spec.get("owner_risk_acceptance_status") or "required"
        ),
        owner_risk_acceptance_may_override=[
            str(item) for item in generic_spec.get("owner_risk_acceptance_may_override") or []
        ],
        owner_risk_acceptance_never_overrides=[
            str(item) for item in generic_spec.get("owner_risk_acceptance_never_overrides") or []
        ],
        owner_risk_acceptance_cannot_override_execution_safety_gates=bool(
            generic_spec.get(
                "owner_risk_acceptance_cannot_override_execution_safety_gates",
                True,
            )
        ),
        hard_blockers=hard_blockers,
        evidence_refs=_evidence_refs(
            candidate_id=candidate_id,
            action_spec=action_spec,
            preview=preview,
            action_entry=action_entry,
        ),
        stage_statuses=_stage_statuses(
            readiness_state=readiness_state,
            authorization=authorization,
            final_gate=final_gate,
            operation_preflight=operation_preflight,
            protection=protection,
            review=review,
        ),
        authorization_draft=authorization,
        budget_draft=budget,
        action_spec_draft=action_spec_draft,
        final_gate_readiness=final_gate,
        operation_layer_preflight=operation_preflight,
        protection_draft=protection,
        review_plan=review,
        post_action_readiness=post_action,
    )


def _authorization_draft(
    *,
    candidate_id: str,
    carrier_id: Optional[str],
    preview_status: str,
    action_spec: dict[str, Any],
    preview: dict[str, Any],
    payload_contract: dict[str, Any],
) -> ProductLoopAuthorizationDraft:
    authorization_required = bool(preview.get("authorization_required"))
    budget_required = bool(preview.get("budget_required"))
    if preview_status == "proposal_only":
        mode = "proposal_only"
        draft_status = "proposal_only_not_authorizable"
    elif preview_status == "dry_run_only":
        mode = "historical_dry_run"
        draft_status = "dry_run_only_not_authorizable"
    elif budget_required:
        mode = "budget_envelope"
        draft_status = "budget_envelope_draft_ready"
    elif authorization_required:
        mode = "owner_authorization"
        draft_status = "authorization_draft_ready"
    else:
        mode = "owner_authorization"
        draft_status = "authorization_attached_or_not_required"

    return ProductLoopAuthorizationDraft(
        mode=mode,  # type: ignore[arg-type]
        draft_status=draft_status,
        authorization_status=preview_status,
        authorization_required=authorization_required,
        budget_required=budget_required,
        draft_ref=(
            f"authorization-draft:{carrier_id or candidate_id}"
            if mode in {"owner_authorization", "budget_envelope"}
            else None
        ),
        confirmation_required=mode in {"owner_authorization", "budget_envelope"},
        required_before_submit=_dedupe(
            [
                *[str(item) for item in payload_contract.get("required_pre_action_facts") or []],
                "Owner risk review",
                "Official Operation Layer preflight",
                "Official FinalGate pass",
            ]
        ),
    )


def _budget_draft(
    *,
    action_spec: dict[str, Any],
    preview: dict[str, Any],
    budget_recommendation: dict[str, Any],
    risk_tier: str,
) -> ProductLoopBudgetDraft:
    envelope = dict(budget_recommendation.get("budget_envelope") or {})
    budget_required = bool(preview.get("budget_required"))
    preview_status = str(preview.get("status") or "unknown")
    if preview_status == "proposal_only":
        status = "proposal_only_budget_preview"
    elif preview_status == "dry_run_only":
        status = "dry_run_only_budget_preview"
    elif budget_required:
        status = "budget_draft_ready"
    else:
        status = str(envelope.get("status") or "budget_context_not_available")
    blockers = [
        str(item.get("id") or item.get("stage") or item.get("evidence"))
        for item in budget_recommendation.get("blockers") or []
        if isinstance(item, dict) and item.get("severity") == "hard_blocker"
    ]
    return ProductLoopBudgetDraft(
        status=status,
        budget_envelope_ref=_optional_str(
            action_spec.get("budget_envelope_ref") or envelope.get("envelope_id")
        ),
        budget_authorization_status=(
            "needs_budget_authorization" if budget_required else "not_applicable"
        ),
        risk_tier=risk_tier,
        max_notional_per_action=_optional_str(envelope.get("max_notional_per_action")),
        total_budget=_optional_str(envelope.get("total_budget")),
        max_attempts=_optional_int(envelope.get("max_attempts")),
        missing_facts=[str(item) for item in budget_recommendation.get("missing_facts") or []],
        hard_blockers=blockers,
    )


def _action_spec_draft(
    action_spec: dict[str, Any],
    generic_spec: dict[str, Any],
) -> ProductLoopActionSpecDraft:
    return ProductLoopActionSpecDraft(
        action_spec_id=str(action_spec.get("action_spec_id") or "action-spec:unknown"),
        status=str(generic_spec.get("status") or action_spec.get("status") or "unknown"),
        normalized_status=str(action_spec.get("status") or "unknown"),
        symbol=_optional_str(action_spec.get("symbol")),
        side=_optional_str(action_spec.get("side")),
        quantity=_optional_str(action_spec.get("quantity")),
        target_notional_usdt=_optional_str(action_spec.get("target_notional_usdt")),
        computed_quantity=_optional_str(action_spec.get("computed_quantity")),
        estimated_notional_usdt=_optional_str(action_spec.get("estimated_notional_usdt")),
        max_notional=_optional_str(action_spec.get("max_notional")),
        leverage=_optional_str(action_spec.get("leverage")),
        max_attempts=_optional_int(action_spec.get("max_attempts")),
        validation_issues=[
            dict(item) for item in action_spec.get("validation_issues") or []
            if isinstance(item, dict)
        ],
    )


def _final_gate_readiness(
    *,
    action_spec: dict[str, Any],
    preview: dict[str, Any],
    hard_blockers: list[str],
    warnings: list[str],
    fact_context: dict[str, Any],
    budget_recommendation: dict[str, Any],
) -> ProductLoopFinalGateReadiness:
    fact_bindings = _fact_bindings(
        action_spec=action_spec,
        preview=preview,
        hard_blockers=hard_blockers,
        fact_context=fact_context,
        budget_recommendation=budget_recommendation,
    )
    return ProductLoopFinalGateReadiness(
        status=_final_gate_readiness_status(str(preview.get("status") or "unknown")),
        preview_status=str(preview.get("status") or "unknown"),
        preview_id=str(preview.get("preview_id") or "final-gate-preview:unknown"),
        product_message=str(preview.get("product_message") or ""),
        disabled_reason=str(preview.get("disabled_reason") or "Official FinalGate pass required."),
        required_checks=[str(item) for item in preview.get("required_final_gate_checks") or []],
        fact_bindings=fact_bindings,
        missing_facts=[item.code for item in fact_bindings if item.status == "missing_fact"],
        stale_facts=[item.code for item in fact_bindings if item.status == "stale"],
        conflicting_facts=[item.code for item in fact_bindings if item.status == "blocked"],
        hard_blockers=hard_blockers,
        warnings=warnings,
    )


def _fact_bindings(
    *,
    action_spec: dict[str, Any],
    preview: dict[str, Any],
    hard_blockers: list[str],
    fact_context: dict[str, Any],
    budget_recommendation: dict[str, Any],
) -> list[ProductLoopFactBinding]:
    symbol = _optional_str(action_spec.get("symbol"))
    pg_positions = [
        item for item in fact_context.get("pg_positions") or []
        if not symbol or item.get("symbol") == symbol
    ]
    pg_open_orders = [
        item for item in fact_context.get("pg_open_orders") or []
        if not symbol or item.get("symbol") == symbol
    ]
    account = dict(fact_context.get("account") or {})
    guards = dict(fact_context.get("guards") or {})
    environment = dict(fact_context.get("environment") or {})
    budget_envelope = dict(budget_recommendation.get("budget_envelope") or {})
    completed_counts = dict(fact_context.get("completed_intents_today_by_symbol") or {})
    max_attempts = _optional_int(action_spec.get("max_attempts")) or _optional_int(
        budget_envelope.get("max_attempts")
    )
    completed_for_symbol = int(completed_counts.get(symbol or "", 0) or 0)
    daily_attempt_status = (
        "blocked" if max_attempts is not None and completed_for_symbol >= max_attempts
        else "ready"
    )

    return [
        _fact(
            "account_facts",
            "Account facts",
            "missing_fact" if preview.get("account_facts_required") else _ready_if_available(account),
            account.get("source"),
            "Refresh account facts through an approved read path.",
        ),
        _fact(
            "reconciliation_facts",
            "Reconciliation facts",
            "missing_fact" if preview.get("reconciliation_facts_required") else "ready",
            fact_context.get("reconciliation_ref"),
            "Refresh reconciliation evidence before FinalGate.",
        ),
        _fact(
            "budget_status",
            "Budget status",
            "missing_fact"
            if budget_envelope.get("status") in {None, "degraded_missing_account_facts"}
            else "ready",
            budget_envelope.get("envelope_id"),
            "Provide fresh account facts and Owner/BudgetEnvelope confirmation.",
        ),
        _fact(
            "daily_attempts",
            "Daily attempts",
            daily_attempt_status,
            f"{completed_for_symbol}/{max_attempts}" if max_attempts is not None else None,
            "Wait for the next attempt window or revise the budget envelope.",
        ),
        _fact(
            "active_position",
            "Active position conflict",
            "blocked" if pg_positions or "active_position_conflict" in hard_blockers else "ready",
            str(len(pg_positions)),
            "Resolve active position before opening another bounded action.",
        ),
        _fact(
            "open_orders",
            "Open order conflict",
            "blocked" if pg_open_orders or "open_order_conflict" in hard_blockers else "ready",
            str(len(pg_open_orders)),
            "Resolve open order conflict through the official path.",
        ),
        _fact(
            "market_metadata",
            "Market metadata",
            "ready" if action_spec.get("symbol") and action_spec.get("max_notional") else "missing_fact",
            action_spec.get("symbol"),
            "Attach min quantity, min notional, precision, and current-price evidence.",
        ),
        _fact(
            "runtime_guard",
            "Runtime / GKS guard",
            "blocked" if "runtime_or_gks_guard_blocked" in hard_blockers else _guard_status(guards),
            guards.get("source"),
            "Clear runtime guard and GKS evidence before FinalGate.",
        ),
        _fact(
            "environment_profile",
            "Environment / profile",
            "ready" if environment else "unavailable",
            environment.get("trading_env") or environment.get("profile"),
            "Expose environment/profile evidence before official action.",
        ),
        _fact(
            "operation_layer",
            "Operation Layer handoff",
            "missing_fact" if "operation_layer_required" in hard_blockers else "ready",
            preview.get("official_final_gate_boundary"),
            "Submit through Operation Layer preflight; never bypass it.",
        ),
        _fact(
            "protection_template",
            "Protection template",
            "blocked"
            if "missing_or_incomplete_protection_template" in hard_blockers
            else "ready",
            (action_spec.get("protection_template") or {}).get("template_id"),
            "Complete TP/SL price plan and reduce-only recording evidence.",
        ),
        _fact(
            "review_template",
            "Review template",
            "ready" if action_spec.get("review_template") else "missing_fact",
            (action_spec.get("review_template") or {}).get("template_id"),
            "Attach ReviewTemplate before promotion/revise/park decisions.",
        ),
    ]


def _operation_preflight(
    *,
    candidate_id: str,
    carrier_id: Optional[str],
    action_spec: dict[str, Any],
    preview: dict[str, Any],
    final_gate: ProductLoopFinalGateReadiness,
) -> ProductLoopOperationPreflight:
    preview_status = str(preview.get("status") or "unknown")
    if preview_status in {"proposal_only", "dry_run_only"}:
        status = "disabled_by_policy"
        disabled_reason = str(preview.get("product_message") or "Candidate is not authorizable.")
    elif preview_status in {"needs_owner_authorization", "needs_budget_authorization"}:
        status = "official_preflight_path_available_after_authorization"
        disabled_reason = str(preview.get("disabled_reason") or "Authorization is required first.")
    elif final_gate.missing_facts or final_gate.conflicting_facts:
        status = "official_preflight_path_available_blocked_by_facts"
        disabled_reason = "FinalGate facts are missing, stale, or conflicting."
    else:
        status = "official_preflight_path_available_execution_disabled"
        disabled_reason = "Official FinalGate and explicit live authorization are still required."
    return ProductLoopOperationPreflight(
        status=status,
        disabled_reason=disabled_reason,
        input_payload_summary={
            "candidate_id": candidate_id,
            "carrier_id": carrier_id,
            "action_spec_id": action_spec.get("action_spec_id"),
            "symbol": action_spec.get("symbol"),
            "side": action_spec.get("side"),
            "quantity": action_spec.get("quantity"),
            "target_notional_usdt": action_spec.get("target_notional_usdt"),
            "max_notional": action_spec.get("max_notional"),
            "leverage": action_spec.get("leverage"),
            "protection_mode": action_spec.get("protection_mode"),
            "review_requirement": action_spec.get("review_requirement"),
            "read_model_submitted": False,
        },
    )


def _protection_draft(action_spec: dict[str, Any]) -> ProductLoopProtectionDraft:
    template = dict(action_spec.get("protection_template") or {})
    blockers = [str(item) for item in template.get("hard_blockers") or []]
    if not template:
        status = "missing_fact"
    elif blockers:
        status = "blocked_incomplete_template"
    else:
        status = "ready_for_final_gate_preview"
    mode = _optional_str(template.get("mode") or action_spec.get("protection_mode"))
    return ProductLoopProtectionDraft(
        status=status,
        template_id=_optional_str(template.get("template_id")),
        mode=mode,
        required_components=_protection_components(mode),
        hard_blockers=blockers,
        retry_condition=(
            "Attach concrete TP/SL prices and reduce-only protection recording."
            if status != "ready_for_final_gate_preview"
            else "Recheck protection facts at official FinalGate."
        ),
    )


def _review_plan(action_spec: dict[str, Any]) -> ProductLoopReviewPlan:
    template = dict(action_spec.get("review_template") or {})
    family = str(action_spec.get("family") or "Unknown")
    missing = [] if template else ["review_template"]
    return ProductLoopReviewPlan(
        status="ready_for_post_action_review" if template else "missing_fact",
        template_id=_optional_str(template.get("template_id")),
        strategy_family=family,
        review_requirement=_optional_str(action_spec.get("review_requirement")),
        required_sections=[str(item) for item in template.get("required_sections") or []],
        family_review_focus=_family_review_focus(family),
        post_action_required=bool(template.get("post_action_required", True)),
        missing_items=missing,
    )


def _post_action_readiness(post_action_state: dict[str, Any]) -> ProductLoopPostActionReadiness:
    review_ledger = dict(post_action_state.get("review_ledger") or {})
    return ProductLoopPostActionReadiness(
        status=str(post_action_state.get("status") or "empty"),
        intent_count=int(post_action_state.get("intent_count") or 0),
        entry_order_count=int(post_action_state.get("entry_order_count") or 0),
        protection_order_count=int(post_action_state.get("protection_order_count") or 0),
        review_count=int(post_action_state.get("review_count") or 0),
        audit_event_count=int(post_action_state.get("audit_event_count") or 0),
        review_ledger_status=str(review_ledger.get("lifecycle_status") or "not_started"),
        retry_safety=_optional_str(post_action_state.get("retry_safety")),
    )


def _stage_statuses(
    *,
    readiness_state: str,
    authorization: ProductLoopAuthorizationDraft,
    final_gate: ProductLoopFinalGateReadiness,
    operation_preflight: ProductLoopOperationPreflight,
    protection: ProductLoopProtectionDraft,
    review: ProductLoopReviewPlan,
) -> list[ProductLoopStageStatus]:
    return [
        ProductLoopStageStatus(
            stage="candidate_authorization_final_gate_readiness",
            label="Candidate -> Authorization -> FinalGate",
            status="implemented",
            summary=(
                f"{authorization.draft_status}; FinalGate readiness={final_gate.status}; "
                f"loop={readiness_state}"
            ),
        ),
        ProductLoopStageStatus(
            stage="owner_confirmed_console_action_entry",
            label="Owner-confirmed Console Action Entry",
            status="implemented",
            summary="Trading Console consumes backend loop state and keeps action disabled.",
        ),
        ProductLoopStageStatus(
            stage="operation_layer_dry_run_preflight",
            label="Operation Layer dry-run/preflight",
            status="implemented"
            if operation_preflight.status != "disabled_by_policy"
            else "disabled_by_policy",
            summary=operation_preflight.status,
        ),
        ProductLoopStageStatus(
            stage="protection_review_operational_loop",
            label="Protection + Review",
            status="implemented"
            if protection.status != "missing_fact" and review.status != "missing_fact"
            else "partial",
            summary=f"protection={protection.status}; review={review.status}",
        ),
    ]


def _readiness_state(preview_status: str) -> str:
    return {
        "ready_for_final_gate": "final_gate_ready_but_execution_disabled",
        "needs_owner_authorization": "authorization_draft_ready",
        "needs_budget_authorization": "needs_budget_authorization",
        "proposal_only": "proposal_only",
        "dry_run_only": "dry_run_only",
        "blocked_before_final_gate": "blocked_before_final_gate",
        "needs_account_facts": "final_gate_not_ready",
        "needs_reconciliation_facts": "final_gate_not_ready",
        "blocked_by_position_conflict": "blocked_before_final_gate",
        "blocked_by_open_order_conflict": "blocked_before_final_gate",
        "blocked_by_missing_protection_template": "final_gate_not_ready",
        "blocked_by_scope_mismatch": "blocked_before_final_gate",
    }.get(preview_status, "final_gate_not_ready")


def _confirmable_state(
    preview_status: str,
    authorization_required: bool,
    budget_required: bool,
) -> Literal[
    "owner_confirmable",
    "budget_confirmable",
    "proposal_only",
    "dry_run_only",
    "blocked",
    "disabled",
]:
    if preview_status == "proposal_only":
        return "proposal_only"
    if preview_status == "dry_run_only":
        return "dry_run_only"
    if budget_required:
        return "budget_confirmable"
    if authorization_required:
        return "owner_confirmable"
    if preview_status == "ready_for_final_gate":
        return "disabled"
    return "blocked"


def _final_gate_readiness_status(preview_status: str) -> str:
    if preview_status == "ready_for_final_gate":
        return "final_gate_ready_but_execution_disabled"
    if preview_status in {"proposal_only", "dry_run_only"}:
        return preview_status
    if preview_status.startswith("needs_"):
        return preview_status
    if preview_status.startswith("blocked_"):
        return "blocked_before_final_gate"
    return "final_gate_not_ready"


def _next_recommended_action(preview_status: str, family: str) -> str:
    if preview_status == "needs_owner_authorization":
        return "Review warnings, confirm Owner scope, then use official Operation Layer preflight."
    if preview_status == "needs_budget_authorization":
        return "Review BudgetEnvelope scope, confirm budget authorization, then use official Operation Layer preflight."
    if preview_status == "proposal_only":
        return "Keep this candidate in proposal review; do not authorize live action."
    if preview_status == "dry_run_only":
        return "Use this as historical or dry-run evidence only; create a fresh scoped candidate before authorization."
    if family == "Volatility expansion":
        return "Keep Volatility disabled until its carrier is explicitly upgraded."
    return "Resolve hard blockers and missing FinalGate facts before any official action."


def _evidence_refs(
    *,
    candidate_id: str,
    action_spec: dict[str, Any],
    preview: dict[str, Any],
    action_entry: dict[str, Any],
) -> list[str]:
    return _dedupe(
        [
            candidate_id,
            str(action_spec.get("action_spec_id") or ""),
            str(preview.get("preview_id") or ""),
            str(action_entry.get("carrier_id") or ""),
            str((action_spec.get("protection_template") or {}).get("template_id") or ""),
            str((action_spec.get("review_template") or {}).get("template_id") or ""),
        ]
    )


def _fact(
    code: str,
    label: str,
    status: str,
    evidence_ref: Any,
    retry_condition: str,
) -> ProductLoopFactBinding:
    allowed = {
        "ready",
        "missing_fact",
        "stale",
        "blocked",
        "warning",
        "unavailable",
        "not_applicable",
    }
    normalized = status if status in allowed else "unavailable"
    return ProductLoopFactBinding(
        code=code,
        label=label,
        status=normalized,  # type: ignore[arg-type]
        evidence_ref=_optional_str(evidence_ref),
        retry_condition=None if normalized == "ready" else retry_condition,
    )


def _ready_if_available(value: dict[str, Any]) -> Literal["ready", "missing_fact"]:
    return "ready" if value and value.get("status") == "available" else "missing_fact"


def _guard_status(guards: dict[str, Any]) -> Literal["ready", "unavailable"]:
    if not guards:
        return "unavailable"
    if guards.get("gks_status") in {"blocked", "engaged"}:
        return "unavailable"
    return "ready"


def _protection_components(mode: Optional[str]) -> list[str]:
    if mode == "manual_review_required":
        return ["manual_review"]
    if mode in {"single_tp_plus_sl", "fixed_percent_tp_sl", "atr_based_tp_sl", "range_reversion_stop"}:
        return ["TP", "SL"]
    return []


def _family_review_focus(family: str) -> list[str]:
    if family == "Trend":
        return ["trend continuation", "false breakout", "pullback behavior", "TP/SL outcome"]
    if family == "Mean reversion":
        return ["snapback", "failed reversion", "trend break against position", "TP/SL outcome"]
    if family == "Volatility expansion":
        return ["true expansion", "failed expansion", "reversal after breakout", "TP/SL outcome"]
    return ["entry validity", "TP/SL behavior", "residual order cleanup", "post-close result"]


def _match_by_carrier_or_family(
    items: list[dict[str, Any]],
    carrier_id: Optional[str],
    family: Optional[str],
) -> dict[str, Any]:
    for item in items:
        if carrier_id and item.get("carrier_id") == carrier_id:
            return dict(item)
    for item in items:
        if family and item.get("family") == family:
            return dict(item)
    return {}


def _first_loop_match(
    loops: list[CandidateActionReadinessLoop],
    carrier_id: Optional[str],
    family: Optional[str],
) -> Optional[CandidateActionReadinessLoop]:
    for loop in loops:
        if carrier_id and loop.carrier_id == carrier_id:
            return loop
    for loop in loops:
        if family and loop.family == family:
            return loop
    return loops[0] if loops else None


def _optional_str(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result
