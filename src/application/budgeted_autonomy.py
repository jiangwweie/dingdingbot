"""Budgeted Autonomy v0 loop evaluation.

This module is pure application logic. It evaluates whether a budgeted trading
loop is already active, closed/reviewed, or blocked before any further action.
It never creates authorizations, execution intents, orders, or PG mutations.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.application.budget_recommendation import BlockerRecord


LoopOutcome = Literal[
    "closed_reviewed",
    "protected_open_review_pending",
    "blocked_with_retry_condition",
]
Side = Literal["long", "short"]
PauseState = Literal["active", "paused"]


class BudgetedAutonomyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BudgetedAutonomyAuthorization(BudgetedAutonomyModel):
    budget_authorization_id: str
    allowed_carriers: list[str] = Field(default_factory=list)
    allowed_symbols: list[str] = Field(default_factory=list)
    allowed_sides: list[Side] = Field(default_factory=lambda: ["long"])
    max_notional_per_action: Decimal = Field(gt=Decimal("0"))
    daily_loss_cap: Decimal = Field(ge=Decimal("0"))
    max_active_positions: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    max_leverage: Decimal = Field(gt=Decimal("0"))
    valid_until_ms: int | None = None
    pause_state: PauseState = "active"
    revoked: bool = False
    review_required: Literal["post_action_review_required"] = "post_action_review_required"
    protection_mode: Literal["single_tp_plus_sl"] = "single_tp_plus_sl"
    auto_execution_enabled: Literal[False] = False
    live_ready: Literal[False] = False
    order_permission_granted: Literal[False] = False
    execution_permission_granted: Literal[False] = False
    metadata_only: Literal[True] = True
    action_allowed: Literal[False] = False
    grants_trading_permission: Literal[False] = False


class BudgetedAutonomyPositionEvidence(BudgetedAutonomyModel):
    carrier_id: str | None = None
    symbol: str
    side: Side
    quantity: Decimal | None = None
    notional: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    entry_price: Decimal | None = None
    exchange_position_present: bool = False
    exchange_verified_flat: bool = False
    pg_position_count: int = Field(ge=0, default=0)
    open_tp_count: int = Field(ge=0, default=0)
    open_sl_count: int = Field(ge=0, default=0)
    pg_open_order_count: int = Field(ge=0, default=0)
    retry_allowed: bool = False
    review_recorded: bool = False
    audit_recorded: bool = False

    @property
    def is_active(self) -> bool:
        return self.exchange_position_present or self.pg_position_count > 0

    @property
    def is_protected(self) -> bool:
        return self.open_tp_count > 0 and self.open_sl_count > 0


class BudgetedAutonomyCandidateInput(BudgetedAutonomyModel):
    candidate_id: str
    family: str
    carrier_id: str
    symbol: str
    side: Side
    status: str
    action_registry_supported: bool = False
    proposal_role: str | None = None
    quantity: Decimal | None = None
    target_notional_usdt: Decimal | None = None
    estimated_notional_usdt: Decimal | None = None
    max_notional: Decimal | None = None
    leverage: Decimal | None = None
    max_attempts: int | None = None
    protection_mode: str | None = None
    review_requirement: str | None = None
    warnings: list[str] = Field(default_factory=list)
    hard_blockers: list[str] = Field(default_factory=list)

    @field_validator("warnings", "hard_blockers", mode="before")
    @classmethod
    def _coerce_string_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]


class BudgetedAutonomyCandidateDecision(BudgetedAutonomyModel):
    candidate_id: str
    carrier_id: str
    symbol: str
    side: Side
    status: Literal["eligible_for_final_gate", "blocked"]
    estimated_notional_usdt: Decimal | None = None
    warnings: list[str] = Field(default_factory=list)
    blockers: list[BlockerRecord] = Field(default_factory=list)
    action_allowed: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


class BudgetedAutonomyLoopEvaluation(BudgetedAutonomyModel):
    loop_version: Literal["budgeted_autonomy_v0"] = "budgeted_autonomy_v0"
    outcome: LoopOutcome
    active_loop: bool
    active_position_count: int
    budget_authorization_id: str
    selected_candidate: BudgetedAutonomyCandidateDecision | None = None
    blocked_candidates: list[BudgetedAutonomyCandidateDecision] = Field(default_factory=list)
    active_positions: list[BudgetedAutonomyPositionEvidence] = Field(default_factory=list)
    budget_envelope_summary: dict[str, object] = Field(default_factory=dict)
    review_ledger: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    hard_blockers: list[BlockerRecord] = Field(default_factory=list)
    retry_condition: str
    action_allowed: Literal[False] = False
    backend_actionable: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    auto_execution_enabled: Literal[False] = False
    may_execute_live: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_pg: Literal[False] = False


def evaluate_budgeted_autonomy_loop(
    *,
    authorization: BudgetedAutonomyAuthorization,
    positions: list[BudgetedAutonomyPositionEvidence],
    candidates: list[BudgetedAutonomyCandidateInput],
    review_ledger: dict[str, object] | None = None,
    now_ms: int | None = None,
) -> BudgetedAutonomyLoopEvaluation:
    """Evaluate one budgeted autonomy loop without granting execution rights."""

    observed_now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    active_positions = [item for item in positions if item.is_active]
    active_count = len(active_positions)
    base_blockers = _authorization_blockers(
        authorization=authorization,
        now_ms=observed_now_ms,
    )
    ledger = dict(review_ledger or {})
    blocked_candidates: list[BudgetedAutonomyCandidateDecision] = []

    if active_count:
        mismatched_positions = [
            item for item in active_positions
            if item.exchange_verified_flat and item.pg_position_count > 0
        ]
        if mismatched_positions:
            mismatch_blocker = _blocker(
                blocker_id="BUDGETED-AUTONOMY-PG-EXCHANGE-MISMATCH",
                stage="BudgetedAutonomy",
                path="BudgetEnvelope -> PGPosition -> ExchangeEvidence",
                evidence=(
                    "PG still records active position/protection, but exchange "
                    "read-only evidence shows no active position and no open protection."
                ),
                severity="hard_blocker",
                bridge="Keep all new actions disabled while reconciliation/review cleanup is pending.",
                retry_condition=(
                    "Run official reconciliation/review cleanup so PG position, orders, "
                    "review ledger, and exchange evidence agree."
                ),
            )
            for candidate in candidates:
                blocked_candidates.append(
                    _candidate_decision(
                        authorization,
                        candidate,
                        blockers=[mismatch_blocker],
                        extra_warnings=["pg_exchange_cleanup_needed_blocks_new_action"],
                    )
                )
            return BudgetedAutonomyLoopEvaluation(
                outcome="blocked_with_retry_condition",
                active_loop=True,
                active_position_count=active_count,
                budget_authorization_id=authorization.budget_authorization_id,
                blocked_candidates=blocked_candidates,
                active_positions=active_positions,
                budget_envelope_summary=_budget_summary(authorization),
                review_ledger=ledger,
                warnings=["pg_exchange_cleanup_needed"],
                hard_blockers=[*base_blockers, mismatch_blocker],
                retry_condition=mismatch_blocker.retry_condition,
            )
        candidate_blocker = _blocker(
            blocker_id="BUDGETED-AUTONOMY-ACTIVE-POSITION",
            stage="BudgetedAutonomy",
            path="BudgetEnvelope -> ActivePosition -> CandidateSelector",
            evidence=(
                f"{active_count} active position(s) consume max_active_positions "
                f"{authorization.max_active_positions}."
            ),
            severity="hard_blocker",
            bridge="Hold further candidate execution while protected position remains open.",
            retry_condition="Position closes with PG/exchange evidence and review ledger is updated.",
        )
        for candidate in candidates:
            blocked_candidates.append(
                _candidate_decision(
                    authorization,
                    candidate,
                    blockers=[candidate_blocker],
                    extra_warnings=["active_budgeted_loop_consumes_position_budget"],
                )
            )
        protected_positions = [item for item in active_positions if item.is_protected]
        if protected_positions and all(not item.retry_allowed for item in protected_positions):
            return BudgetedAutonomyLoopEvaluation(
                outcome="protected_open_review_pending",
                active_loop=True,
                active_position_count=active_count,
                budget_authorization_id=authorization.budget_authorization_id,
                blocked_candidates=blocked_candidates,
                active_positions=active_positions,
                budget_envelope_summary=_budget_summary(authorization),
                review_ledger=ledger,
                warnings=["protected_open_position_requires_monitoring_until_tp_or_sl"],
                hard_blockers=[*base_blockers, candidate_blocker],
                retry_condition="Wait for TP/SL close evidence, then complete post-action review.",
            )
        return BudgetedAutonomyLoopEvaluation(
            outcome="blocked_with_retry_condition",
            active_loop=True,
            active_position_count=active_count,
            budget_authorization_id=authorization.budget_authorization_id,
            blocked_candidates=blocked_candidates,
            active_positions=active_positions,
            budget_envelope_summary=_budget_summary(authorization),
            review_ledger=ledger,
            warnings=["active_position_protection_or_retry_state_incomplete"],
            hard_blockers=[*base_blockers, candidate_blocker],
            retry_condition="Reconcile active position, TP/SL, retry safety, and review/audit evidence.",
        )

    if _ledger_closed_reviewed(ledger):
        return BudgetedAutonomyLoopEvaluation(
            outcome="closed_reviewed",
            active_loop=False,
            active_position_count=0,
            budget_authorization_id=authorization.budget_authorization_id,
            selected_candidate=None,
            blocked_candidates=[],
            budget_envelope_summary=_budget_summary(authorization),
            review_ledger=ledger,
            hard_blockers=base_blockers,
            retry_condition="No active loop remains; a fresh Owner-confirmed budgeted scope is required before any new action.",
        )

    candidate_decisions = [
        _candidate_decision(authorization, candidate, blockers=base_blockers)
        for candidate in candidates
    ]
    eligible = [item for item in candidate_decisions if item.status == "eligible_for_final_gate"]
    if eligible and not base_blockers:
        return BudgetedAutonomyLoopEvaluation(
            outcome="blocked_with_retry_condition",
            active_loop=False,
            active_position_count=0,
            budget_authorization_id=authorization.budget_authorization_id,
            selected_candidate=eligible[0],
            blocked_candidates=[item for item in candidate_decisions if item.status == "blocked"],
            budget_envelope_summary=_budget_summary(authorization),
            review_ledger=ledger,
            retry_condition="Run official Owner authorization and server-side FinalGate for the exact selected scope.",
        )

    blockers = [*base_blockers]
    for decision in candidate_decisions:
        blockers.extend(decision.blockers)
    return BudgetedAutonomyLoopEvaluation(
        outcome="blocked_with_retry_condition",
        active_loop=False,
        active_position_count=0,
        budget_authorization_id=authorization.budget_authorization_id,
        selected_candidate=None,
        blocked_candidates=candidate_decisions,
        budget_envelope_summary=_budget_summary(authorization),
        review_ledger=ledger,
        hard_blockers=_dedupe_blockers(blockers),
        retry_condition="Repair budget, scope, market-rule, or FinalGate readiness blockers before selecting a candidate.",
    )


def _candidate_decision(
    authorization: BudgetedAutonomyAuthorization,
    candidate: BudgetedAutonomyCandidateInput,
    *,
    blockers: list[BlockerRecord],
    extra_warnings: list[str] | None = None,
) -> BudgetedAutonomyCandidateDecision:
    candidate_blockers = list(blockers)
    candidate_blockers.extend(_candidate_blockers(authorization, candidate))
    status = "blocked" if candidate_blockers else "eligible_for_final_gate"
    return BudgetedAutonomyCandidateDecision(
        candidate_id=candidate.candidate_id,
        carrier_id=candidate.carrier_id,
        symbol=candidate.symbol,
        side=candidate.side,
        status=status,
        estimated_notional_usdt=candidate.estimated_notional_usdt,
        warnings=_dedupe_strings([*candidate.warnings, *(extra_warnings or [])]),
        blockers=_dedupe_blockers(candidate_blockers),
    )


def _authorization_blockers(
    *,
    authorization: BudgetedAutonomyAuthorization,
    now_ms: int,
) -> list[BlockerRecord]:
    blockers: list[BlockerRecord] = []
    if authorization.revoked:
        blockers.append(
            _blocker(
                blocker_id="BUDGETED-AUTONOMY-AUTH-REVOKED",
                stage="BudgetedAutonomy",
                path="BudgetEnvelope -> AutonomyAuthorization",
                evidence="Budgeted autonomy authorization is revoked.",
                severity="hard_blocker",
                bridge="Keep all candidate actions disabled.",
                retry_condition="Owner creates a fresh budgeted authorization.",
            )
        )
    if authorization.pause_state != "active":
        blockers.append(
            _blocker(
                blocker_id="BUDGETED-AUTONOMY-AUTH-PAUSED",
                stage="BudgetedAutonomy",
                path="BudgetEnvelope -> AutonomyAuthorization",
                evidence=f"pause_state={authorization.pause_state}.",
                severity="hard_blocker",
                bridge="Keep all candidate actions disabled while paused.",
                retry_condition="Owner explicitly resumes the budgeted authorization.",
            )
        )
    if authorization.valid_until_ms is not None and now_ms > authorization.valid_until_ms:
        blockers.append(
            _blocker(
                blocker_id="BUDGETED-AUTONOMY-AUTH-EXPIRED",
                stage="BudgetedAutonomy",
                path="BudgetEnvelope -> AutonomyAuthorization",
                evidence=f"now_ms {now_ms} exceeds valid_until_ms {authorization.valid_until_ms}.",
                severity="hard_blocker",
                bridge="Expire all candidate actions.",
                retry_condition="Owner creates a fresh budgeted authorization with a new validity window.",
            )
        )
    if authorization.max_active_positions < 1:
        blockers.append(
            _blocker(
                blocker_id="BUDGETED-AUTONOMY-AUTH-NO-ACTIVE-POSITIONS",
                stage="BudgetedAutonomy",
                path="BudgetEnvelope -> AutonomyAuthorization",
                evidence="max_active_positions is 0.",
                severity="hard_blocker",
                bridge="Keep all candidate actions disabled.",
                retry_condition="Owner creates a fresh budgeted authorization allowing one active position.",
            )
        )
    return blockers


def _candidate_blockers(
    authorization: BudgetedAutonomyAuthorization,
    candidate: BudgetedAutonomyCandidateInput,
) -> list[BlockerRecord]:
    blockers = [
        _blocker(
            blocker_id=f"BUDGETED-AUTONOMY-CANDIDATE-{index + 1}",
            stage="BudgetedAutonomy",
            path="ActionCandidate -> GenericActionSpec -> FinalGate",
            evidence=reason,
            severity="hard_blocker",
            bridge="Keep candidate disabled in Owner Action Flow.",
            retry_condition="Regenerate candidate after the listed blocker is repaired.",
        )
        for index, reason in enumerate(candidate.hard_blockers)
    ]
    if candidate.status != "valid_blocked_final_gate":
        blockers.append(
            _blocker(
                blocker_id="BUDGETED-AUTONOMY-CANDIDATE-STATUS",
                stage="BudgetedAutonomy",
                path="ActionCandidate -> GenericActionSpec",
                evidence=f"GenericActionSpec status is {candidate.status}.",
                severity="hard_blocker",
                bridge="Keep candidate as proposal/non-action.",
                retry_condition="Candidate must become valid_blocked_final_gate before FinalGate.",
            )
        )
    if not candidate.action_registry_supported:
        blockers.append(
            _blocker(
                blocker_id="BUDGETED-AUTONOMY-CANDIDATE-NOT-REGISTERED",
                stage="BudgetedAutonomy",
                path="ActionCandidate -> OfficialActionRegistry",
                evidence="Carrier is not supported by the official action registry.",
                severity="hard_blocker",
                bridge="Do not use unofficial action paths.",
                retry_condition="Register carrier in the official action registry and retest.",
            )
        )
    if candidate.carrier_id not in authorization.allowed_carriers:
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-CARRIER",
                evidence=f"{candidate.carrier_id} is outside allowed_carriers.",
                retry_condition="Owner confirms an authorization containing this exact carrier.",
            )
        )
    if candidate.symbol not in authorization.allowed_symbols:
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-SYMBOL",
                evidence=f"{candidate.symbol} is outside allowed_symbols.",
                retry_condition="Owner confirms an authorization containing this exact symbol.",
            )
        )
    if candidate.side not in authorization.allowed_sides:
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-SIDE",
                evidence=f"{candidate.side} is outside allowed_sides.",
                retry_condition="Owner confirms an authorization containing this exact side.",
            )
        )
    effective_notional = (
        candidate.estimated_notional_usdt
        or candidate.target_notional_usdt
        or candidate.max_notional
    )
    if effective_notional is None:
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-NOTIONAL-MISSING",
                evidence="Candidate does not provide estimated_notional_usdt, target_notional_usdt, or max_notional.",
                retry_condition="Regenerate candidate with exact budgeted notional sizing.",
            )
        )
    elif effective_notional > authorization.max_notional_per_action:
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-NOTIONAL",
                evidence=(
                    f"candidate notional {effective_notional} exceeds "
                    f"max_notional_per_action {authorization.max_notional_per_action}."
                ),
                retry_condition="Lower candidate size or create a new Owner-approved budget envelope.",
            )
        )
    if (
        candidate.max_notional is not None
        and candidate.max_notional > authorization.max_notional_per_action
    ):
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-MAX-NOTIONAL",
                evidence=(
                    f"candidate max_notional {candidate.max_notional} exceeds "
                    f"max_notional_per_action {authorization.max_notional_per_action}."
                ),
                retry_condition="Lower candidate max_notional or create a new Owner-approved budget envelope.",
            )
        )
    if candidate.leverage is None:
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-LEVERAGE-MISSING",
                evidence="Candidate leverage is missing.",
                retry_condition="Regenerate candidate with exact leverage.",
            )
        )
    elif candidate.leverage > authorization.max_leverage:
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-LEVERAGE",
                evidence=f"candidate leverage {candidate.leverage} exceeds max_leverage {authorization.max_leverage}.",
                retry_condition="Lower leverage or create a new Owner-approved budget envelope.",
            )
        )
    if candidate.max_attempts is None:
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-ATTEMPTS-MISSING",
                evidence="Candidate max_attempts is missing.",
                retry_condition="Regenerate candidate with exact max_attempts.",
            )
        )
    elif candidate.max_attempts > authorization.max_attempts:
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-ATTEMPTS",
                evidence=f"candidate max_attempts {candidate.max_attempts} exceeds {authorization.max_attempts}.",
                retry_condition="Lower max_attempts or create a new Owner-approved budget envelope.",
            )
        )
    if candidate.protection_mode != authorization.protection_mode:
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-PROTECTION",
                evidence=(
                    f"candidate protection_mode {candidate.protection_mode} "
                    f"does not match {authorization.protection_mode}."
                ),
                retry_condition="Regenerate candidate with matching TP/SL protection.",
            )
        )
    if candidate.review_requirement != authorization.review_required:
        blockers.append(
            _scope_blocker(
                blocker_id="BUDGETED-AUTONOMY-SCOPE-REVIEW",
                evidence=(
                    f"candidate review_requirement {candidate.review_requirement} "
                    f"does not match {authorization.review_required}."
                ),
                retry_condition="Regenerate candidate with matching review requirement.",
            )
        )
    return blockers


def _scope_blocker(
    *,
    blocker_id: str,
    evidence: str,
    retry_condition: str,
) -> BlockerRecord:
    return _blocker(
        blocker_id=blocker_id,
        stage="BudgetedAutonomy",
        path="BudgetEnvelope -> OwnerScope -> ActionCandidate",
        evidence=evidence,
        severity="hard_blocker",
        bridge="Keep candidate disabled in Owner Action Flow.",
        retry_condition=retry_condition,
    )


def _ledger_closed_reviewed(ledger: dict[str, object]) -> bool:
    lifecycle = ledger.get("lifecycle_status")
    review = ledger.get("review_decision")
    review_status = review.get("status") if isinstance(review, dict) else None
    closed_lifecycles = {
        "closed_from_pg_exit_order",
        "closed_external_exchange_flat_unresolved",
    }
    return lifecycle in closed_lifecycles and review_status not in {None, "pending", "not_recorded"}


def _budget_summary(authorization: BudgetedAutonomyAuthorization) -> dict[str, object]:
    return {
        "budget_authorization_id": authorization.budget_authorization_id,
        "allowed_carriers": list(authorization.allowed_carriers),
        "allowed_symbols": list(authorization.allowed_symbols),
        "allowed_sides": list(authorization.allowed_sides),
        "max_notional_per_action": str(authorization.max_notional_per_action),
        "daily_loss_cap": str(authorization.daily_loss_cap),
        "max_active_positions": authorization.max_active_positions,
        "max_attempts": authorization.max_attempts,
        "max_leverage": str(authorization.max_leverage),
        "valid_until_ms": authorization.valid_until_ms,
        "pause_state": authorization.pause_state,
        "revoked": authorization.revoked,
        "review_required": authorization.review_required,
        "protection_mode": authorization.protection_mode,
        "auto_execution_enabled": False,
        "action_allowed": False,
        "grants_trading_permission": False,
    }


def _blocker(
    *,
    blocker_id: str,
    stage: str,
    path: str,
    evidence: str,
    severity: Literal["hard_blocker", "warning", "deferred"],
    bridge: str,
    retry_condition: str,
) -> BlockerRecord:
    return BlockerRecord(
        id=blocker_id,
        stage=stage,
        path=path,
        evidence=evidence,
        severity=severity,
        bridge=bridge,
        retry_condition=retry_condition,
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _dedupe_blockers(values: list[BlockerRecord]) -> list[BlockerRecord]:
    result: list[BlockerRecord] = []
    seen: set[str] = set()
    for value in values:
        if value.id in seen:
            continue
        seen.add(value.id)
        result.append(value)
    return result
